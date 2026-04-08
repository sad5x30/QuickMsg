const searchInput = document.getElementById("search");
const searchResults = document.getElementById("search-results");
const chatList = document.getElementById("chat-list");
const sidebarStatus = document.getElementById("sidebar-status");
const chatEmptyState = document.getElementById("chat-empty-state");
const chatView = document.getElementById("chat-view");
const chatTitle = document.getElementById("chat-title");
const chatSubtitle = document.getElementById("chat-subtitle");
const messagesRoot = document.getElementById("messages");
const messageForm = document.getElementById("message-form");
const messageInput = document.getElementById("message-input");
const notificationCenter = document.getElementById("notification-center");
const swapButton = document.getElementById("swap-button");

const isAuthenticated = document.body.dataset.authenticated === "true";

const state = {
    activeChatId: null,
    activeParticipantId: null,
    chats: [],
    currentUser: null,
    messageIds: new Set(),
    shownNotificationIds: new Set(),
    unreadNotificationCount: 0,
    notificationSocket: null,
    searchRequestId: 0,
    socket: null,
    statusSocket: null,
};

const THEME_STORAGE_KEY = "quickmsg-theme";

function applyTheme(theme) {
    const isDarkTheme = theme === "dark";
    document.body.classList.toggle("dark-theme", isDarkTheme);

    if (!swapButton) {
        return;
    }

    swapButton.textContent = isDarkTheme ? "☀️" : "🌙";
    swapButton.setAttribute(
        "aria-label",
        isDarkTheme ? "Переключить на светлую тему" : "Переключить на темную тему"
    );
}

function initThemeToggle() {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    applyTheme(savedTheme === "dark" ? "dark" : "light");

    if (!swapButton) {
        return;
    }

    swapButton.addEventListener("click", () => {
        const nextTheme = document.body.classList.contains("dark-theme") ? "light" : "dark";
        localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
        applyTheme(nextTheme);
    });
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => (
        {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
        }[char]
    ));
}

function formatTime(value) {
    if (!value) return "";

    return new Intl.DateTimeFormat("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
    }).format(new Date(value));
}

function formatRelativeDate(value) {
    if (!value) return "";

    return new Intl.DateTimeFormat("ru-RU", {
        day: "2-digit",
        month: "short",
    }).format(new Date(value));
}

function setSidebarStatus(message) {
    sidebarStatus.textContent = message;
}

function getNotificationTitle(notification) {
    const author = notification.data?.sender_username;
    return author
        ? `Новое сообщение от @${author}`
        : "Новое сообщение";
}

function getNotificationAccent(notification) {
    const source = notification.data?.sender_username || notification.text || "Q";
    return String(source).trim().charAt(0).toUpperCase() || "Q";
}

function renderNotificationToast(notification) {
    if (!notificationCenter) {
        return;
    }

    if (notification.id && state.shownNotificationIds.has(notification.id)) {
        return;
    }

    if (notification.id) {
        state.shownNotificationIds.add(notification.id);
    }

    const toast = document.createElement("article");
    toast.className = "notification-toast";

    const preview = notification.data?.text || notification.text || "Новое уведомление";
    const author = notification.data?.sender_username
        ? `@${notification.data.sender_username}`
        : "QuickMsg";

    toast.innerHTML = `
        <div class="notification-toast-header">
            <span class="notification-toast-title">Новое уведомление</span>
            <button type="button" class="notification-toast-close" aria-label="Закрыть">×</button>
        </div>
        <p class="notification-toast-text">${escapeHtml(notification.text || "Новое сообщение")}</p>
        <p class="notification-toast-meta">${escapeHtml(author)}: ${escapeHtml(preview)}</p>
    `;

    const removeToast = () => {
        if (!toast.isConnected) {
            return;
        }

        toast.classList.add("is-hiding");
        window.setTimeout(() => {
            toast.remove();
        }, 220);
    };

    toast.querySelector(".notification-toast-close").addEventListener("click", removeToast);

    if (notification.data?.chat_id) {
        toast.addEventListener("click", async (event) => {
            if (event.target.closest(".notification-toast-close")) {
                return;
            }

            removeToast();
            await openChat(Number(notification.data.chat_id));
        });
    }

    notificationCenter.prepend(toast);
    window.setTimeout(removeToast, 4500);
}

function refreshSidebarStatus() {
    if (!isAuthenticated) {
        setSidebarStatus("Войдите, чтобы открыть чаты");
        return;
    }

    if (!state.chats.length) {
        setSidebarStatus(
            state.unreadNotificationCount
                ? `Новых уведомлений: ${state.unreadNotificationCount}`
                : "Создайте первый чат через поиск"
        );
        return;
    }

    const unreadSuffix = state.unreadNotificationCount
        ? ` • новых уведомлений: ${state.unreadNotificationCount}`
        : "";
    setSidebarStatus(`Диалогов: ${state.chats.length}${unreadSuffix}`);
}

function renderSearchMessage(message) {
    searchResults.innerHTML = `<p class="search-message">${escapeHtml(message)}</p>`;
}

function renderSearchResults(users) {
    if (!users.length) {
        renderSearchMessage("Ничего не найдено.");
        return;
    }

    searchResults.innerHTML = users
        .map((user) => {
            const isSelf = state.currentUser && user.id === state.currentUser.id;
            const button = isSelf
                ? '<span class="search-chip">Это вы</span>'
                : `<button type="button" class="search-action" data-chat-user-id="${user.id}" data-chat-username="${escapeHtml(user.username)}">Открыть чат</button>`;

            return `
                <article class="search-item">
                    <div>
                        <strong>${escapeHtml(user.username)}</strong>
                        <p>Найденный пользователь</p>
                    </div>
                    ${button}
                </article>
            `;
        })
        .join("");
}

function renderChatList() {
    if (!state.chats.length) {
        chatList.innerHTML = `
            <div class="chat-list-empty">
                <p>Пока нет диалогов.</p>
                <span>Начните новый чат через поиск выше.</span>
            </div>
        `;
        return;
    }

    chatList.innerHTML = state.chats
        .map((chat) => {
            const isActive = chat.id === state.activeChatId;
            const preview = chat.last_message || "Диалог создан. Можно писать первым.";
            const meta = chat.last_message_created_at || chat.updated_at;

            return `
                <button type="button" class="chat-list-item ${isActive ? "is-active" : ""}" data-chat-id="${chat.id}">
                    <div class="chat-list-row">
                        <strong>${escapeHtml(chat.title)}</strong>
                        <span>${escapeHtml(formatRelativeDate(meta))}</span>
                    </div>
                    <p>${escapeHtml(preview)}</p>
                </button>
            `;
        })
        .join("");
}

function scrollMessagesToBottom() {
    messagesRoot.scrollTop = messagesRoot.scrollHeight;
}

function renderMessages(messages) {
    state.messageIds = new Set(messages.map((message) => message.id));

    if (!messages.length) {
        messagesRoot.innerHTML = `
            <div class="messages-empty">
                <p>Сообщений пока нет.</p>
                <span>Напишите первое сообщение, чтобы начать диалог.</span>
            </div>
        `;
        return;
    }

    messagesRoot.innerHTML = messages
        .map((message) => renderMessageBubble(message))
        .join("");

    scrollMessagesToBottom();
}

function renderMessageBubble(message) {
    return `
        <article class="message-bubble ${message.is_own ? "is-own" : ""}" data-message-id="${message.id}">
            <p>${escapeHtml(message.text)}</p>
            <span>${escapeHtml(formatTime(message.created_at))}</span>
        </article>
    `;
}

function appendMessage(message) {
    if (state.messageIds.has(message.id)) {
        return;
    }

    state.messageIds.add(message.id);

    const isEmpty = messagesRoot.querySelector(".messages-empty");
    if (isEmpty) {
        messagesRoot.innerHTML = "";
    }

    messagesRoot.insertAdjacentHTML("beforeend", renderMessageBubble(message));
    scrollMessagesToBottom();
}

function formatLastSeen(dateString) {
    if (!dateString) {
        return "не в сети";
    }

    const date = new Date(dateString);
    const now = new Date();

    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return "был только что";
    if (diff < 3600) return `был ${Math.floor(diff/60)} мин назад`;
    if (diff < 86400) return `был ${Math.floor(diff/3600)} ч назад`;

    return date.toLocaleDateString();
}

function getStatusText(data) {
    if (!data) {
        return "статус недоступен";
    }

    if (data.status === "online") {
        return "в сети";
    }

    return formatLastSeen(data.last_seen);
}

function setChatSubtitle(chat, statusText = null) {
    if (!chat) {
        return;
    }

    chatSubtitle.textContent = statusText
        ? `@${chat.participant.username} - ${statusText}`
        : `Чат с @${chat.participant.username}`;
}

function teardownStatusSocket() {
    if (!state.statusSocket) {
        return;
    }

    state.statusSocket.onmessage = null;
    state.statusSocket.onclose = null;
    state.statusSocket.close();
    state.statusSocket = null;
}

function getStatusWsUrl(userId) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws/status/${userId}`;
}

function connectToStatus(userId) {
    teardownStatusSocket();

    if (!userId) {
        return;
    }

    const socket = new WebSocket(getStatusWsUrl(userId));
    state.statusSocket = socket;

    socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        const activeChat = state.chats.find((item) => item.id === state.activeChatId);

        if (!activeChat || state.activeParticipantId !== userId) {
            return;
        }

        setChatSubtitle(activeChat, getStatusText(payload));
    };

    socket.onclose = () => {
        if (state.statusSocket === socket) {
            state.statusSocket = null;
        }
    };
}

function show_status(data) {
    return getStatusText(data);
    let user_status 

    if (data.status === "online") {
        user_status = "в сети 🟢";
    } else {
        user_status = formatLastSeen(data.last_seen);
    }
}

function showChat(chat) {
    state.activeChatId = chat.id;
    state.activeParticipantId = chat.participant?.id ?? null;
    chatTitle.textContent = chat.title;
    chatSubtitle.textContent = `Чат с @${chat.participant.username}`;
    setChatSubtitle(chat);
    connectToStatus(state.activeParticipantId);
    chatEmptyState.classList.add("hidden");
    chatView.classList.remove("hidden");
    renderChatList();
}

function teardownSocket() {
    if (state.socket) {
        state.socket.onmessage = null;
        state.socket.onclose = null;
        state.socket.close();
        state.socket = null;
    }
}

function teardownNotificationSocket() {
    if (state.notificationSocket) {
        state.notificationSocket.onmessage = null;
        state.notificationSocket.onclose = null;
        state.notificationSocket.close();
        state.notificationSocket = null;
    }
}

function getWsUrl(chatId) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/chats/ws/chat/${chatId}`;
}

function getNotificationsWsUrl() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/notifications/ws`;
}

function upsertChatPreview(message) {
    const chat = state.chats.find((item) => item.id === message.chat_id);
    if (!chat) {
        loadChats();
        return;
    }

    chat.last_message = message.text;
    chat.last_message_created_at = message.created_at;
    chat.updated_at = message.created_at;
    state.chats.sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at));
    renderChatList();
    refreshSidebarStatus();
}

function connectToChat(chatId) {
    teardownSocket();

    const socket = new WebSocket(getWsUrl(chatId));
    state.socket = socket;

    socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        const message = {
            ...payload,
            is_own: state.currentUser && payload.sender_id === state.currentUser.id,
        };

        if (payload.chat_id === state.activeChatId) {
            appendMessage(message);
        }

        upsertChatPreview(message);
    };

    socket.onclose = () => {
        if (state.socket === socket) {
            state.socket = null;
        }
    };
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });

    if (!response.ok) {
        let detail = "Request failed";

        try {
            const data = await response.json();
            detail = data.detail || detail;
        } catch (error) {
            console.error(error);
        }

        throw new Error(detail);
    }

    return response.json();
}

async function loadCurrentUser() {
    state.currentUser = await fetchJson("/chats/me");
}

async function loadChats() {
    state.chats = await fetchJson("/chats");
    renderChatList();
    refreshSidebarStatus();
}

async function loadNotifications() {
    const notifications = await fetchJson("/notifications");
    const unreadNotifications = notifications.filter((item) => !item.is_read);
    state.unreadNotificationCount = unreadNotifications.length;
    refreshSidebarStatus();
    return unreadNotifications;
}

function showUnreadNotificationToasts(notifications) {
    notifications
        .slice()
        .reverse()
        .forEach((notification) => {
            renderNotificationToast(notification);
        });
}

async function markNotificationsRead(chatId = null) {
    const url = chatId ? `/notifications/read?chat_id=${chatId}` : "/notifications/read";
    await fetchJson(url, {
        method: "POST",
    });
    if (chatId) {
        await loadNotifications();
        return;
    }

    state.unreadNotificationCount = 0;
    refreshSidebarStatus();
}

function connectToNotifications() {
    teardownNotificationSocket();

    const socket = new WebSocket(getNotificationsWsUrl());
    state.notificationSocket = socket;

    socket.onmessage = async (event) => {
        const notification = JSON.parse(event.data);
        const messageData = notification.data || {};

        if (!notification.is_read) {
            state.unreadNotificationCount += 1;
            refreshSidebarStatus();
            renderNotificationToast(notification);
        }

        if (messageData.chat_id) {
            await loadChats();

            if (messageData.chat_id === state.activeChatId) {
                await markNotificationsRead(messageData.chat_id);
            }
        }
    };

    socket.onclose = () => {
        if (state.notificationSocket === socket) {
            state.notificationSocket = null;
        }
    };
}

async function openChat(chatId) {
    const chat = state.chats.find((item) => item.id === chatId);
    if (!chat) {
        return;
    }

    showChat(chat);
    const messages = await fetchJson(`/chats/${chatId}/messages`);
    renderMessages(messages);
    connectToChat(chatId);
    await markNotificationsRead(chatId);
}

async function createDirectChat(userId) {
    const chat = await fetchJson(`/chats/direct/${userId}`, {
        method: "POST",
    });

    const existingIndex = state.chats.findIndex((item) => item.id === chat.id);
    if (existingIndex >= 0) {
        state.chats[existingIndex] = chat;
    } else {
        state.chats.unshift(chat);
    }

    state.chats.sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at));
    renderChatList();
    refreshSidebarStatus();
    await openChat(chat.id);
}

let searchDebounceTimer = null;

async function handleSearchInput() {
    const query = searchInput.value.trim();
    const requestId = ++state.searchRequestId;

    if (!query) {
        searchResults.innerHTML = "";
        return;
    }

    if (query.length < 2) {
        renderSearchMessage("Введите минимум 2 символа.");
        return;
    }

    try {
        const users = await fetchJson(`/users/search?query=${encodeURIComponent(query)}`);
        if (requestId !== state.searchRequestId) {
            return;
        }
        renderSearchResults(users);
    } catch (error) {
        console.error(error);
        renderSearchMessage("Не удалось выполнить поиск.");
    }
}

function updateGuestState() {
    setSidebarStatus("Войдите, чтобы открыть чаты");
    chatList.innerHTML = `
        <div class="chat-list-empty">
            <p>Чаты доступны после авторизации.</p>
            <span>Можно войти в аккаунт и сразу начать переписку.</span>
        </div>
    `;
    renderSearchMessage("Чтобы начать чат, сначала войдите в аккаунт.");
}

async function initAuthenticatedApp() {
    try {
        await loadCurrentUser();
        await loadChats();
        const unreadNotifications = await loadNotifications();
        showUnreadNotificationToasts(unreadNotifications);
        connectToNotifications();

        if (state.chats.length) {
            await openChat(state.chats[0].id);
        } else {
            refreshSidebarStatus();
        }
    } catch (error) {
        console.error(error);
        setSidebarStatus("Не удалось загрузить чаты");
        chatList.innerHTML = `
            <div class="chat-list-empty">
                <p>Ошибка загрузки.</p>
                <span>Проверьте авторизацию и перезагрузите страницу.</span>
            </div>
        `;
    }
}

searchInput.addEventListener("input", () => {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(handleSearchInput, 220);
});

searchResults.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-chat-user-id]");
    if (!button) {
        return;
    }

    if (!isAuthenticated) {
        window.location.href = "/login";
        return;
    }

    try {
        await createDirectChat(Number(button.dataset.chatUserId));
        searchResults.innerHTML = "";
        searchInput.value = "";
    } catch (error) {
        console.error(error);
        renderSearchMessage("Не удалось открыть чат.");
    }
});

chatList.addEventListener("click", async (event) => {
    const item = event.target.closest("[data-chat-id]");
    if (!item) {
        return;
    }

    try {
        await openChat(Number(item.dataset.chatId));
    } catch (error) {
        console.error(error);
    }
});

messageForm.addEventListener("submit", (event) => {
    event.preventDefault();

    const text = messageInput.value.trim();
    if (!text || !state.socket || state.socket.readyState !== WebSocket.OPEN) {
        return;
    }

    state.socket.send(text);
    messageInput.value = "";
});

window.addEventListener("beforeunload", teardownSocket);
window.addEventListener("beforeunload", teardownNotificationSocket);
window.addEventListener("beforeunload", teardownStatusSocket);

if (isAuthenticated) {
    initAuthenticatedApp();
} else {
    updateGuestState();
}

