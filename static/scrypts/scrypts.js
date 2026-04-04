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

const isAuthenticated = document.body.dataset.authenticated === "true";

const state = {
    activeChatId: null,
    chats: [],
    currentUser: null,
    messageIds: new Set(),
    searchRequestId: 0,
    socket: null,
};

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

function showChat(chat) {
    state.activeChatId = chat.id;
    chatTitle.textContent = chat.title;
    chatSubtitle.textContent = `Чат с @${chat.participant.username}`;
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

function getWsUrl(chatId) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/chats/ws/${chatId}`;
}

function upsertChatPreview(message) {
    const chat = state.chats.find((item) => item.id === message.chat_id);
    if (!chat) return;

    chat.last_message = message.text;
    chat.last_message_created_at = message.created_at;
    chat.updated_at = message.created_at;
    state.chats.sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at));
    renderChatList();
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
    setSidebarStatus(
        state.chats.length
            ? `Диалогов: ${state.chats.length}`
            : "Создайте первый чат через поиск"
    );
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

        if (state.chats.length) {
            await openChat(state.chats[0].id);
        } else {
            setSidebarStatus("Выберите пользователя через поиск");
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

if (isAuthenticated) {
    initAuthenticatedApp();
} else {
    updateGuestState();
}
