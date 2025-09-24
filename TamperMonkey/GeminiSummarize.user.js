// ==UserScript==
// @name         Gemini Summarize
// @namespace    http://tampermonkey.net/
// @version      1.15
// @description  Add a button to YouTube videos to summarize them with Gemini.
// @author       You
// @match        https://www.youtube.com/*
// @match        https://m.youtube.com/*
// @require      https://cdn.jsdelivr.net/npm/marked/marked.min.js
// @grant        GM_xmlhttpRequest
// @grant        GM.addStyle
// @grant        unsafeWindow
// ==/UserScript==

(function() {
    'use strict';

    const BASE_URL = 'http://localhost:5000'; // Replace with your actual base URL
    const PASTEBIN_URL = 'https://shz.al/';
    const API_KEY = 'YOUR_API_KEY_HERE'; // <--- IMPORTANT: SET YOUR API KEY HERE
    const GEMINI_MODEL = "gemini-1.5-flash-latest";
    const OBSIDIAN_FOLDER = "";

    const conversations = []; // To store conversation status
    let markdownPolicy; // To hold the Trusted Types policy

    // --- UTILS ---
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    const obsidianUtils = {
        async saveToObsidian(fileContent, noteName) {
            const vault = ""; // Optional: specify your vault name here
            const isDailyNote = false; // Or implement logic to determine this
            let obsidianUrl;

            if (isDailyNote) {
                obsidianUrl = `obsidian://daily?`;
            } else {
                const formattedNoteName = noteName.replace(/[\\/:"*?<>|]/g, '-');
                obsidianUrl = `obsidian://new?file=${OBSIDIAN_FOLDER}${encodeURIComponent(formattedNoteName)}`;
            }

            obsidianUrl += `&content=${encodeURIComponent(fileContent)}`;
            if (vault) {
                obsidianUrl += `&vault=${encodeURIComponent(vault)}`;
            }

            window.open(obsidianUrl, '_top');
        }
    };

    // --- UI COMPONENTS ---
    class UI {
        static createSummarizeButton() {
            const button = document.createElement('button');
            button.textContent = '✨';
            button.style.fontSize = '18px';
            button.style.border = 'none';
            button.style.background = 'transparent';
            button.style.cursor = 'pointer';
            button.setAttribute('class', 'gemini-summarize-button');
            return button;
        }

        static setButtonState(button, state, conversationId = null) {
            if (!button) return;
            button.dataset.state = state;
            if(conversationId) {
                button.dataset.conversationId = conversationId;
            }
            switch (state) {
                case 'pending':
                    button.textContent = '🕒';
                    button.style.animation = '';
                    break;
                case 'loading':
                    button.textContent = '⏳';
                    button.style.animation = 'spin 1s linear infinite';
                    break;
                case 'success':
                    button.textContent = '✅';
                    button.style.animation = '';
                    break;
                case 'error':
                    button.textContent = '❌';
                    button.style.animation = '';
                    break;
                default:
                    button.textContent = '✨';
                    button.style.animation = '';
                    break;
            }
        }

        static createConversationListModal() {
            const modal = document.createElement('div');
            modal.id = 'gemini-conversation-list-modal';

            const modalContent = document.createElement('div');
            modalContent.className = 'modal-content';

            const closeButton = document.createElement('span');
            closeButton.className = 'close-button';
            closeButton.textContent = '×';

            const title = document.createElement('h2');
            title.textContent = 'Conversation List';

            const list = document.createElement('div');
            list.id = 'gemini-conversation-list';

            modalContent.appendChild(closeButton);
            modalContent.appendChild(title);
            modalContent.appendChild(list);
            modal.appendChild(modalContent);
            document.body.appendChild(modal);

            closeButton.addEventListener('click', () => {
                modal.style.display = 'none';
            });
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.style.display = 'none';
                }
            });
            return modal;
        }

        static updateConversationList(listElement, conversations) {
            while (listElement.firstChild) {
                listElement.removeChild(listElement.firstChild);
            }
            conversations.forEach(conv => {
                const item = document.createElement('div');
                item.className = 'conversation-item';
                conv.ui.listItem = item; // Associate the list item element

                const title = document.createElement('span');
                title.className = 'conversation-title';
                title.textContent = conv.title;

                const statusIcon = document.createElement('span');
                statusIcon.className = 'conversation-status-icon';

                item.appendChild(title);
                item.appendChild(statusIcon);

                listElement.appendChild(item);

                // Set the initial UI state (icon, cursor, click event)
                updateUIForConversation(conv);
            });
        }

        static createChatModal() {
            const modal = document.createElement('div');
            modal.id = 'gemini-chat-modal';

            const modalContent = document.createElement('div');
            modalContent.className = 'modal-content';

            const closeButton = document.createElement('span');
            closeButton.className = 'close-button';
            closeButton.textContent = '×';

            const chatHistory = document.createElement('div');
            chatHistory.id = 'gemini-chat-history';

            const commonQuestions = document.createElement('div');
            commonQuestions.id = 'gemini-common-questions';

            const inputContainer = document.createElement('div');
            inputContainer.id = 'gemini-chat-input-container';

            const input = document.createElement('input');
            input.type = 'text';
            input.id = 'gemini-chat-input';
            input.placeholder = 'Ask a follow-up question...';

            const sendButton = document.createElement('button');
            sendButton.id = 'gemini-chat-send';
            sendButton.textContent = 'Send';
            sendButton.className = 'yt-spec-button-shape-next yt-spec-button-shape-next--filled yt-spec-button-shape-next--mono yt-spec-button-shape-next--size-m';


            const exportButton = document.createElement('button');
            exportButton.id = 'gemini-export-obsidian';
            const obsidianIcon = document.createElement('img');
            obsidianIcon.src = 'https://obsidian.md/favicon.svg';
            exportButton.appendChild(obsidianIcon);
            exportButton.className = 'yt-spec-button-shape-next yt-spec-button-shape-next--tonal yt-spec-button-shape-next--mono yt-spec-button-shape-next--size-s yt-spec-button-shape-next--icon-button';

            const exportPastebinButton = document.createElement('button');
            exportPastebinButton.id = 'gemini-export-pastebin';
            const pastebinIcon = document.createElement('img');
            pastebinIcon.src = 'https://sharzy.in/favicon-32x32.png';
            exportPastebinButton.appendChild(pastebinIcon);
            exportPastebinButton.className = 'yt-spec-button-shape-next yt-spec-button-shape-next--tonal yt-spec-button-shape-next--mono yt-spec-button-shape-next--size-s yt-spec-button-shape-next--icon-button';

            const openYoutubeLink = document.createElement('a');
            openYoutubeLink.id = 'gemini-open-youtube';
            openYoutubeLink.target = '_blank';
            openYoutubeLink.title = 'Open YouTube video in new tab';
            const youtubeIcon = document.createElement('img');
            youtubeIcon.src = 'https://www.youtube.com/s/desktop/271635d3/img/logos/favicon_32x32.png';
            openYoutubeLink.appendChild(youtubeIcon);
            openYoutubeLink.className = 'yt-spec-button-shape-next yt-spec-button-shape-next--tonal yt-spec-button-shape-next--mono yt-spec-button-shape-next--size-s yt-spec-button-shape-next--icon-button';

            const exportButtonContainer = document.createElement('div');
            exportButtonContainer.id = 'gemini-export-button-container';
            exportButtonContainer.appendChild(openYoutubeLink);
            exportButtonContainer.appendChild(exportPastebinButton);
            exportButtonContainer.appendChild(exportButton);

            const shareUrlContainer = document.createElement('div');
            shareUrlContainer.id = 'gemini-share-url-container';
            shareUrlContainer.style.display = 'none';
            const shareUrlInput = document.createElement('input');
            shareUrlInput.type = 'text';
            shareUrlInput.id = 'gemini-share-url';
            shareUrlInput.readOnly = true;

            const shareUrlPreviewButton = document.createElement('a');
            shareUrlPreviewButton.id = 'gemini-share-url-preview';
            shareUrlPreviewButton.textContent = '🔗';
            shareUrlPreviewButton.target = '_blank';
            shareUrlPreviewButton.title = 'Open link in new tab';

            shareUrlContainer.appendChild(shareUrlInput);
            shareUrlContainer.appendChild(shareUrlPreviewButton);
            exportButtonContainer.appendChild(shareUrlContainer);

            inputContainer.appendChild(input);
            inputContainer.appendChild(sendButton);

            modalContent.appendChild(closeButton);
            modalContent.appendChild(chatHistory);
            modalContent.appendChild(commonQuestions);
            modalContent.appendChild(exportButtonContainer);
            modalContent.appendChild(inputContainer);

            modal.appendChild(modalContent);
            document.body.appendChild(modal);

            closeButton.addEventListener('click', () => {
                modal.style.display = 'none';
            });
             modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.style.display = 'none';
                }
            });
            return modal;
        }
    }

    // --- API ---
    class GeminiAPI {
        static createConversation(url) {
            return new Promise((resolve, reject) => {
                GM_xmlhttpRequest({
                    method: 'POST',
                    url: `${BASE_URL}/conversations`,
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${API_KEY}`
                    },
                    data: JSON.stringify({ urls: [url] , model: GEMINI_MODEL}),
                    onload: (response) => {
                        if (response.status >= 200 && response.status < 300) {
                            resolve(JSON.parse(response.responseText));
                        } else {
                            reject(new Error(response.statusText));
                        }
                    },
                    onerror: (error) => reject(error)
                });
            });
        }

        static getConversation(conversationId) {
             return new Promise((resolve, reject) => {
                GM_xmlhttpRequest({
                    method: 'GET',
                    url: `${BASE_URL}/conversations/${conversationId}/json`,
                    headers: {
                        'Authorization': `Bearer ${API_KEY}`
                    },
                    onload: (response) => {
                        if (response.status >= 200 && response.status < 300) {
                            resolve(JSON.parse(response.responseText));
                        } else {
                            reject(new Error(response.statusText));
                        }
                    },
                    onerror: (error) => reject(error)
                });
            });
        }

        static sendMessage(conversationId, message) {
            return new Promise((resolve, reject) => {
                GM_xmlhttpRequest({
                    method: 'POST',
                    url: `${BASE_URL}/conversations/${conversationId}/messages`,
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${API_KEY}`
                    },
                    data: JSON.stringify({ message: message }),
                    onload: (response) => {
                        if (response.status >= 200 && response.status < 300) {
                            resolve(JSON.parse(response.responseText));
                        } else {
                            reject(new Error(response.statusText));
                        }
                    },
                    onerror: (error) => reject(error)
                });
            });
        }

        static getConversationMarkdown(conversationId) {
            return new Promise((resolve, reject) => {
                GM_xmlhttpRequest({
                    method: 'GET',
                    url: `${BASE_URL}/conversations/${conversationId}/markdown`,
                    headers: {
                        'Authorization': `Bearer ${API_KEY}`
                    },
                    onload: (response) => {
                        if (response.status >= 200 && response.status < 300) {
                            resolve(response.responseText);
                        } else {
                            reject(new Error(response.statusText));
                        }
                    },
                    onerror: (error) => reject(error)
                });
            });
        }

        static publishToPastebin(markdownContent) {
            const formData = new FormData();
            formData.append('c', markdownContent);
            formData.append('e', '3d');

            return new Promise((resolve, reject) => {
                GM_xmlhttpRequest({
                    method: 'POST',
                    url: PASTEBIN_URL,
                    data: formData,
                    onload: (response) => {
                        if (response.status >= 200 && response.status < 300) {
                            resolve(JSON.parse(response.responseText));
                        } else {
                            reject(new Error(`${response.statusText}: ${response.responseText}`));
                        }
                    },
                    onerror: (error) => reject(error)
                });
            });
        }
    }


    // --- MAIN LOGIC ---
    const requestQueue = [];
    let isProcessing = false;

    function updateUIForConversation(conversation) {
        if (!conversation) return;

        const status = conversation.status;
        const statusToIcon = {
            pending: '🕒',
            loading: '⏳',
            success: '✅',
            error: '❌'
        };

        // Update the button on the video
        if (conversation.ui.button) {
            UI.setButtonState(conversation.ui.button, status, conversation.id);
        }

        // Update the item in the conversation list
        if (conversation.ui.listItem) {
            const item = conversation.ui.listItem;
            const iconElement = item.querySelector('.conversation-status-icon');

            if (iconElement) {
                iconElement.textContent = statusToIcon[status] || '';
            }

            // Reset behavior
            item.onclick = null;
            item.style.cursor = 'default';

            // Apply new behavior based on state
            if (status === 'success') {
                item.style.cursor = 'pointer';
                item.onclick = () => openChatModal(conversation.id);
            } else if (status === 'error') {
                item.style.cursor = 'pointer';
                item.onclick = () => {
                    const conversationToRetry = conversations.find(c => c.url === conversation.url);
                    if (conversationToRetry) {
                        conversationToRetry.status = 'pending';
                        requestQueue.push({ url: conversationToRetry.url });
                        updateUIForConversation(conversationToRetry); // Update UI to pending
                        processQueue();
                    }
                };
            }
        }
    }

    function processQueue() {
        if (isProcessing || requestQueue.length === 0) {
            return;
        }
        isProcessing = true;
        const { url } = requestQueue.shift();
        const conversationEntry = conversations.find(c => c.url === url);

        if (!conversationEntry) {
            isProcessing = false;
            processQueue();
            return;
        }


        conversationEntry.status = 'loading';
        updateUIForConversation(conversationEntry);

        const defaultPrompt = '请根据视频字幕总结主持人的主要观点';

        GeminiAPI.createConversation(url)
            .then(data => {
                const conversationId = data.conversation_id;
                conversationEntry.id = conversationId;
                return GeminiAPI.getConversation(conversationId);
            })
            .then(conversationHistory => {
                if (conversationHistory.length > 2) {
                    return Promise.resolve(); // Skip sending message
                } else {
                    return GeminiAPI.sendMessage(conversationEntry.id, defaultPrompt);
                }
            })
            .then(() => {
                // This will run for both cases (skipped or sent message)
                conversationEntry.status = 'success';
                updateUIForConversation(conversationEntry);
            })
            .catch(error => {
                // Catches errors from any of the steps
                console.error('Error during conversation processing:', error);
                conversationEntry.status = 'error';
                updateUIForConversation(conversationEntry);
            })
            .finally(() => {
                isProcessing = false;
                processQueue(); // Process the next item in the queue
            });
    }

    function addSummarizeButton(videoElement) {
        const videoUrl = getVideoUrl(videoElement);
        if (!videoUrl) return;

        const existingButton = videoElement.querySelector('.gemini-summarize-button');
        if (existingButton) {
            if (existingButton.dataset.url === videoUrl) {
                // Correct button already exists, just ensure state is synced
                const conversation = conversations.find(c => c.url === videoUrl);
                if (conversation) {
                    conversation.ui.button = existingButton; // Re-associate
                    updateUIForConversation(conversation);
                }
                return;
            } else {
                // Stale button from recycled element, remove it
                existingButton.remove();
            }
        }

        const button = UI.createSummarizeButton();
        button.dataset.url = videoUrl; // Store URL on the button
        const videoTitle = getVideoTitle(videoElement);


        button.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();

            const currentState = button.dataset.state;
            if (currentState === 'loading' || currentState === 'pending') return;

            if (currentState === 'error' || !currentState) {
                 // Check if a conversation for this URL already exists
                let conversation = conversations.find(c => c.url === videoUrl);
                if (!conversation) {
                    conversation = {
                        title: videoTitle,
                        url: videoUrl,
                        status: 'pending',
                        id: null,
                        ui: { button: button, listItem: null }
                    };
                    conversations.push(conversation);
                } else {
                    conversation.ui.button = button; // Re-associate button if it was re-rendered
                    conversation.status = 'pending';
                }

                requestQueue.push({ url: videoUrl });
                updateUIForConversation(conversation);
                processQueue();
            } else if (currentState === 'success') {
                openChatModal(button.dataset.conversationId);
            }
        });

        const target = findInsertionPoint(videoElement);
        if (target && target.parentElement) {
            target.parentElement.appendChild(button);
        }
    }

    function getVideoUrl(element) {
        if ((element.tagName == 'YTM-SLIM-VIDEO-ACTION-BAR-RENDERER' || element.tagName == 'YTD-WATCH-METADATA') && window.location.pathname === '/watch') {
            return window.location.href;
        }
        let anchor = element.querySelector('a#yt-lockup-metadata-view-model-wiz__title') || element.querySelector('a#thumbnail') || element.querySelector('a#video-title') || element.querySelector('a.compact-media-item-metadata-content') || element.querySelector('a.media-item-thumbnail-container') || element.querySelector('a');
        return anchor && anchor.href ? new URL(anchor.href).href : null;
    }

    function getVideoTitle(element) {
        if ((element.tagName == 'YTM-SLIM-VIDEO-ACTION-BAR-RENDERER' || element.tagName == 'YTD-WATCH-METADATA') && window.location.pathname === '/watch') {
            return document.title;
        }
        let titleElement = element.querySelector('h3.title-and-badge') || element.querySelector('h4.compact-media-item-headline') || element.querySelector('#video-title') || element.querySelector('h3.yt-lockup-metadata-view-model-wiz__heading-reset') || element.querySelector('h3.yt-lockup-metadata-view-model__heading-reset'); 
        return titleElement ? titleElement.textContent.trim() : 'Unknown Title';
    }


    function findInsertionPoint(element) {
        // Desktop
        let target = element.querySelector('#menu') || element.querySelector('.yt-spec-button-view-model') || element.querySelector('.yt-lockup-metadata-view-model-wiz__menu-button') || element.querySelector('ytm-bottom-sheet-renderer') || element.querySelector('button-view-model') || element.querySelector('.yt-lockup-metadata-view-model__menu-button');
        if (target) return target;

        // Mobile
        target = element.querySelector('.compact-media-item-menu') || element.querySelector('ytm-menu');
        if(target) return target;

        target = element.querySelector('ytm-slim-video-action-bar-renderer .slim-video-action-bar-actions');
        if(target) {
            const shareButton = target.querySelector('ytm-button-renderer[button-renderer-style="SHARE_BUTTON_STYLE_TYPE_DEFAULT"]');
            if(shareButton) {
                 return shareButton.parentElement;
            }
            return target;
        }


        return null;
    }


    // --- OBSERVER & SCANNER ---
    const videoSelectors = [
        'ytd-rich-item-renderer', 'ytd-grid-video-renderer',
        'ytd-playlist-video-renderer', 'ytd-video-renderer',
        'ytm-rich-item-renderer', 'ytm-compact-video-renderer',
        'ytm-playlist-video-renderer', 'ytd-watch-metadata',
        'ytm-slim-video-action-bar-renderer', 'yt-lockup-view-model',
        'ytm-rich-item-renderer', 'ytm-video-with-context-renderer'
    ];
    const videoSelectorString = videoSelectors.join(', ');

    function scanPageForVideos() {
        document.querySelectorAll(videoSelectorString).forEach(addSummarizeButton);
    }

    function scanForGlobalButton() {
        if (document.getElementById('gemini-global-button')) {
            return; // Already exists
        }
        const topbarSelectors = ['ytd-topbar-menu-button-renderer', '.topbar-menu-button-avatar-button'];
        const topbarElement = document.querySelector(topbarSelectors.join(', '));
        if (topbarElement) {
            addGlobalButton(topbarElement);
        }
    }

    function scanPage() {
        scanForGlobalButton();
        scanPageForVideos();
    }

    const debouncedScan = debounce(scanPage, 250);

    const observer = new MutationObserver(() => {
        debouncedScan();
    });


    function addGlobalButton(topbarElement) {
        const globalButton = document.createElement('button');
        globalButton.id = 'gemini-global-button';
        globalButton.textContent = '📜';
        globalButton.style.fontSize = '24px';
        globalButton.style.border = 'none';
        globalButton.style.background = 'transparent';
        globalButton.style.cursor = 'pointer';

        const modal = UI.createConversationListModal();
        const listElement = modal.querySelector('#gemini-conversation-list');

        globalButton.addEventListener('click', () => {
            UI.updateConversationList(listElement, conversations);
            modal.style.display = 'block';
        });

        topbarElement.parentElement.insertBefore(globalButton, topbarElement);
    }

    function addMessageToChat(chatHistory, role, content) {
        const messageElement = document.createElement('div');
        const displayRole = (role === 'model') ? 'assistant' : role;
        messageElement.className = `gemini-chat-message message-role-${displayRole}`;

        // Use the Trusted Types policy to safely set the HTML
        messageElement.innerHTML = markdownPolicy.createHTML(content);

        chatHistory.appendChild(messageElement);
    }

    async function openChatModal(conversationId) {
        const modal = document.getElementById('gemini-chat-modal');
        const chatHistory = modal.querySelector('#gemini-chat-history');
        const commonQuestions = modal.querySelector('#gemini-common-questions');
        const sendButton = modal.querySelector('#gemini-chat-send');
        const input = modal.querySelector('#gemini-chat-input');
        const exportButton = modal.querySelector('#gemini-export-obsidian');
        const exportPastebinButton = modal.querySelector('#gemini-export-pastebin');
        const openYoutubeLink = modal.querySelector('#gemini-open-youtube');
        const shareUrlContainer = modal.querySelector('#gemini-share-url-container');
        const shareUrlInput = modal.querySelector('#gemini-share-url');
        const shareUrlPreviewButton = modal.querySelector('#gemini-share-url-preview');

        // Click outside to hide share URL container
        modal.addEventListener('click', (e) => {
            // If the click is inside the modal but outside the share container and not on the pastebin button
            if (!shareUrlContainer.contains(e.target) && e.target !== exportPastebinButton && !exportPastebinButton.contains(e.target)) {
                shareUrlContainer.style.display = 'none';
            }
        });

        while (chatHistory.firstChild) {
            chatHistory.removeChild(chatHistory.firstChild);
        }
        chatHistory.textContent = 'Loading...';
        modal.style.display = 'block';
        shareUrlContainer.style.display = 'none'; // Hide on open

        const conversation = await GeminiAPI.getConversation(conversationId);
        chatHistory.textContent = ''; // Clear "Loading..."
        conversation.forEach(msg => {
            const messageContent = msg.parts.filter(part => typeof part === 'string').join(' ');
            if (messageContent.trim() !== '') {
                addMessageToChat(chatHistory, msg.role, messageContent);
            }
        });

        const questions = [
            '请根据字幕总结视频的主要内容',
            '请根据视频字幕总结嘉宾和主持人的主要议题，各方观点以及结论',
            '请用中文回答',
            '如何评价主持人的观点',
            '如何评价各方观点'
        ];

        while (commonQuestions.firstChild) {
            commonQuestions.removeChild(commonQuestions.firstChild);
        }
        questions.forEach(q => {
            const button = document.createElement('button');
            button.textContent = q;
            button.className = 'yt-spec-button-shape-next yt-spec-button-shape-next--tonal yt-spec-button-shape-next--mono yt-spec-button-shape-next--size-xs';
            button.addEventListener('click', () => {
                input.value = q;
            });
            commonQuestions.appendChild(button);
        });

        const conv = conversations.find(c => c.id === conversationId);
        if (conv && conv.url) {
            openYoutubeLink.style.display = 'inline-flex';
            openYoutubeLink.href = conv.url;
        } else {
            openYoutubeLink.style.display = 'none';
        }

        sendButton.onclick = async () => {
            const message = input.value;
            if (!message) return;

            sendButton.classList.add('gemini-breathing');
            sendButton.disabled = true;
            input.disabled = true;

            input.value = '';
            addMessageToChat(chatHistory, 'user', message);
            try {
                const response = await GeminiAPI.sendMessage(conversationId, message);
                addMessageToChat(chatHistory, 'assistant', response.response);
            } catch (e) {
                console.error('Error sending message:', e);
                addMessageToChat(chatHistory, 'assistant', 'Sorry, an error occurred while sending the message.');
                input.value = message; // Restore input if sending failed
            } finally {
                sendButton.classList.remove('gemini-breathing');
                sendButton.disabled = false;
                input.disabled = false;
                input.focus();
            }
        };

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendButton.click();
            }
        });

        exportButton.onclick = async () => {
            const markdown = await GeminiAPI.getConversationMarkdown(conversationId);
            const title = conv ? conv.title : 'YouTube Summary';
            const source = conv ? conv.url : '';
            const created = new Date().toISOString().slice(0, 10);

            const frontmatter = `---
title: "${title.replace(/"/g, '\"')}"
source: "${source}"
created: ${created}
tags:
  - "YouTube"
---

`;
            const fileContent = frontmatter + markdown;
            obsidianUtils.saveToObsidian(fileContent, title);
        };

        exportPastebinButton.onclick = async () => {
            try {
                exportPastebinButton.classList.add('gemini-bounce');
                shareUrlContainer.style.display = 'none'; // Hide previous result/error
                const markdown = await GeminiAPI.getConversationMarkdown(conversationId);
                const result = await GeminiAPI.publishToPastebin(markdown);
                const url = result.url.replace(PASTEBIN_URL, PASTEBIN_URL + 'a/');
                shareUrlInput.value = url;
                shareUrlPreviewButton.href = url;
                shareUrlContainer.style.display = 'flex';
                shareUrlInput.select();
            } catch (error) {
                console.error('Error publishing to pastebin:', error);
                shareUrlInput.value = 'Error: Failed to publish content.';
                shareUrlPreviewButton.href = '#';
                shareUrlContainer.style.display = 'flex';
            } finally {
                exportPastebinButton.classList.remove('gemini-bounce');
            }
        };
    }

    function startApp() {
        console.log('Gemini Summarize: Key element found, starting app.');

        // --- Create Trusted Types Policy ---
        if (window.trustedTypes && window.trustedTypes.createPolicy) {
            markdownPolicy = window.trustedTypes.createPolicy('gemini-summarizer#markdown', {
                createHTML: (string) => marked.parse(string)
            });
        } else {
            // Fallback for browsers that don't support Trusted Types
            markdownPolicy = {
                createHTML: (string) => marked.parse(string)
            };
        }


        GM.addStyle(`
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            @keyframes gemini-bounce {
                0%, 100% { transform: translateY(0); }
                50% { transform: translateY(-5px); }
            }
            @keyframes gemini-breathing {
                0%, 100% { background-color: #0f0f0f; }
                50% { background-color: #0f0f0fa1; }
            }
            .gemini-bounce {
                animation: gemini-bounce 0.5s ease-in-out infinite;
            }
            .gemini-breathing {
                animation: gemini-breathing 1.5s ease-in-out infinite;
            }
            #gemini-conversation-list-modal, #gemini-chat-modal {
                display: none;
                position: fixed;
                z-index: 10000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                overflow: auto;
                background-color: rgba(0,0,0,0.6) !important;
            }
            #gemini-conversation-list {
                max-height: 80vh;
                overflow-y: scroll;
            }
            #gemini-conversation-list-modal {
                z-index: 10000;
            }
            #gemini-chat-modal {
                z-index: 10001;
            }
            .modal-content {
                background-color: var(--yt-spec-base-background, var(--yt-spec-surface, #fff)) !important;
                color: var(--yt-spec-text-primary);
                margin: 5% auto !important;
                padding: 10px !important;
                border: 1px solid var(--yt-spec-divider-subtle) !important;
                border-radius: 12px;
                //width: 85%;
                //height: 85%;
                max-width: 95vw;
                max-height: 95vh;
            }
            .conversation-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 8px !important;
                border-bottom: 1px solid var(--yt-spec-divider-subtle);
                cursor: pointer;
                font-size: 1.6rem;
            }
            .conversation-item:hover {
                background-color: var(--yt-spec-badge-chip-background);
            }
            .conversation-title {
                flex-grow: 1;
                margin-right: 16px;
            }
            .conversation-status-icon {
                font-size: 2rem;
            }
            .close-button {
                color: var(--yt-spec-text-secondary);
                float: right;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
            }
            #gemini-chat-history {
                max-height: 70vh;
                overflow-y: auto;
                margin-bottom: 12px !important;
                //padding-right: 8px;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .gemini-chat-message {
                padding: 8px 18px !important;
                border-radius: 18px;
                max-width: 90%;
                font-size: 1.5rem;
                line-height: 1.45;
            }
            .message-role-user {
                align-self: flex-end;
                border: 1px solid !important;
                background-color: var(--yt-spec-brand-background-primary) !important;
                color: var(--yt-spec-brand-text-solid);
            }
            .message-role-assistant {
                align-self: flex-start;
                background-color: var(--yt-spec-badge-chip-background);
                color: var(--yt-spec-text-primary);
            }
            #gemini-common-questions .yt-spec-button-shape-next {
                display: inline-block !important;
                margin: 4px !important;
            }
            @media (max-width: 640px) {
                #gemini-common-questions {
                    overflow-x: auto;
                    padding-bottom: 8px;
                    gap: 8px; /* Add spacing between buttons */
                    scrollbar-width: none; /* Firefox */
                }
                #gemini-common-questions::-webkit-scrollbar {
                    display: none; /* Chrome, Safari */
                }
                #gemini-common-questions .yt-spec-button-shape-next {
                    flex-shrink: 0; /* Prevent buttons from shrinking */
                    margin: 0; /* Reset margin for flex layout */
                }
                ul {
                    padding-inline-start: 10px;
                }
                ol {
                    padding-inline-start: 20px;
                }
                .gemini-chat-message {
                    padding: 4px 8px;
                }
                .modal-content{
                    height: 90vh;
                }
            }
            #gemini-export-button-container {
                position: relative;
                display: flex !important;
                justify-content: flex-end;
                gap: 4px;
                margin-bottom: 8px !important;
            }
            #gemini-export-obsidian.yt-spec-button-shape-next {
                flex: none;
            }
            #gemini-export-button-container img {
                width: 16px;
                height: 16px;
            }
            #gemini-share-url-container {
                position: absolute;
                bottom: 100%;
                right: 0;
                margin-bottom: 8px;
                padding: 8px;
                background-color: var(--yt-spec-badge-chip-background);
                border-radius: 6px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                z-index: 1;
                width: 250px; /* Or adjust as needed */
                display: flex;
                gap: 4px;
                align-items: center;
            }
            #gemini-share-url-preview {
                text-decoration: none;
                font-size: 20px;
                color: var(--yt-spec-text-primary);
            }
            #gemini-share-url {
                width: 100%;
                box-sizing: border-box;
                background-color: var(--yt-spec-brand-background-solid);
                color: var(--yt-spec-text-primary);
                border: 1px solid var(--yt-spec-divider-subtle);
                border-radius: 6px;
                padding: 8px;
            }
            #gemini-chat-input-container {
                display: flex;
                gap: 8px;
                margin-bottom: 12px !important;
            }
            #gemini-chat-input {
                flex-grow: 1;
                background-color: var(--yt-spec-brand-background-solid);
                color: var(--yt-spec-text-primary);
                border-radius: 6px;
                padding: 8px;
            }
            #gemini-chat-send {
                flex-grow: 0.1 !important;
                flex-shrink: 0 !important;
            }
        `);

        UI.createConversationListModal();
        UI.createChatModal();

        // Initial scan for buttons
        scanPage();

        // Start observing for future changes
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    // --- INITIALIZATION ---
    function init() {
        const keyElements = [
            'ytd-rich-grid-renderer',
            'ytd-playlist-video-list-renderer',
            'ytd-item-section-renderer',
            'ytd-watch-flexy',
            'ytm-browse-response',
            'ytm-section-list-renderer',
            'ytm-slim-video-action-bar-renderer',
            'ytm-rich-item-renderer',
            'ytm-video-with-context-renderer'
        ];

        const selector = keyElements.join(', ');

        const timeout = setTimeout(() => {
            clearInterval(interval);
            console.log('Gemini Summarize: Timed out waiting for key element.');
        }, 30000);

        const interval = setInterval(() => {
            if (document.querySelector(selector)) {
                clearInterval(interval);
                clearTimeout(timeout);
                startApp();
            }
        }, 250);
    }

    init();
})();
