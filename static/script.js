const chatForm = document.getElementById('chatForm');
const chatWindow = document.getElementById('chatWindow');
const messageInput = document.getElementById('messageInput');
const conversationList = document.getElementById('conversationList');
const newChatBtn = document.getElementById('newChatBtn');

if (chatForm && chatWindow && messageInput && conversationList && newChatBtn) {
  let currentConversationId = null;

  function createMessage(role, text) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    if (role === 'bot') {
      const avatar = document.createElement('img');
      avatar.className = 'avatar';
      avatar.src = '/static/logo-ruang-tenang.jpeg';
      avatar.alt = 'Logo Ruang Tenang';
      row.appendChild(avatar);
    }

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    row.appendChild(bubble);

    chatWindow.appendChild(row);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  function startNewChat() {
    currentConversationId = null;
    chatWindow.replaceChildren();
    createMessage('bot', 'Apa ada yang bisa saya bantu?');
    renderConversationList();
  }

  async function loadConversations() {
    const response = await fetch('/api/conversations');
    if (!response.ok) {
      throw new Error('Riwayat percakapan gagal dimuat.');
    }
    return response.json();
  }

  async function renderConversationList() {
    conversationList.replaceChildren();

    try {
      const conversations = await loadConversations();
      if (conversations.length === 0) {
        conversationList.textContent = 'Belum ada percakapan.';
        return;
      }

      for (const conversation of conversations) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'conversation-item';
        button.textContent = conversation.title;
        button.classList.toggle('active', conversation.id === currentConversationId);
        button.addEventListener('click', () => openConversation(conversation.id));
        conversationList.appendChild(button);
      }
    }
    catch (error) {
      console.error('Gagal memuat riwayat:', error);
      conversationList.textContent = 'Riwayat tidak dapat dimuat.';
    }
  }

  async function openConversation(conversationId) {
    try {
      const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Percakapan gagal dibuka.');
      }

      currentConversationId = data.id;
      chatWindow.replaceChildren();
      for (const message of data.messages) {
        createMessage(message.role === 'assistant' ? 'bot' : 'user', message.content);
      }
      await renderConversationList();
    } catch (error) {
      console.error('Gagal membuka percakapan:', error);
      createMessage('bot', 'Percakapan gagal dibuka. Silakan coba lagi.');
    }
  }

  async function sendMessageToBackend(message) {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message,
        conversation_id: currentConversationId,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Pesan gagal dikirim.');
    }
    return data;
  }

  newChatBtn.addEventListener('click', startNewChat);

  chatForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const text = messageInput.value.trim();
    if (!text) return;

    createMessage('user', text);
    messageInput.value = '';

    const sendBtn = chatForm.querySelector('button');
    sendBtn.disabled = true;
    sendBtn.textContent = 'Mengirim...';

    try {
      const data = await sendMessageToBackend(text);
      currentConversationId = data.conversation_id;
      createMessage('bot', data.response || 'Maaf, tidak ada jawaban dari server.');
      await renderConversationList();
    } catch (error) {
      console.error('Pesan gagal dikirim:', error);
      createMessage('bot', error.message || 'Pesan gagal dikirim. Silakan coba lagi.');
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = 'Kirim';
    }
  });

  startNewChat();
}

const authDialog = document.getElementById('authDialog');
const openAuthBtn = document.getElementById('openAuthBtn');
const profileDialog = document.getElementById('profileDialog');
const accountMenu = document.getElementById('accountMenu');
const accountName = document.getElementById('accountName');
const accountAvatar = document.getElementById('accountAvatar');

if (authDialog && openAuthBtn && profileDialog && accountMenu) {
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const forgotPasswordForm = document.getElementById('forgotPasswordForm');
  const authMessage = document.getElementById('authMessage');
  const profileForm = document.getElementById('profileForm');
  const passwordForm = document.getElementById('passwordForm');
  const profileMessage = document.getElementById('profileMessage');
  const passwordMessage = document.getElementById('passwordMessage');

  function getCsrfToken() {
    const cookie = document.cookie.split('; ').find((item) =>
      item.startsWith('csrf_token=') || item.startsWith('__Host-csrf_token='),
    );
    return cookie ? decodeURIComponent(cookie.substring(cookie.indexOf('=') + 1)) : '';
  }

  function setMessage(element, message, kind = '') {
    element.replaceChildren();
    element.className = `form-message ${kind}`.trim();
    if (message) element.append(document.createTextNode(message));
  }

  function setMessageLink(element, message, url, linkText) {
    setMessage(element, message, 'success');
    if (!url) return;
    const link = document.createElement('a');
    link.href = url;
    link.textContent = ` ${linkText}`;
    link.className = 'header-link';
    element.append(link);
  }

  function setAccountName(username) {
    accountName.textContent = username;
    accountAvatar.textContent = username.trim().charAt(0).toUpperCase() || 'R';
  }

  function showAuthTab(tab) {
    loginForm.hidden = tab !== 'login';
    registerForm.hidden = tab !== 'register';
    forgotPasswordForm.hidden = true;
    for (const button of document.querySelectorAll('[data-auth-tab]')) {
      button.classList.toggle('active', button.dataset.authTab === tab);
    }
    setMessage(authMessage, '');
  }

  function showForgotPassword() {
    loginForm.hidden = true;
    registerForm.hidden = true;
    forgotPasswordForm.hidden = false;
    for (const button of document.querySelectorAll('[data-auth-tab]')) {
      button.classList.remove('active');
    }
    setMessage(authMessage, '');
  }

  async function responseData(response) {
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Permintaan gagal. Silakan coba lagi.');
    }
    return data;
  }

  async function loadAccount() {
    const response = await fetch('/api/Users/me');
    if (!response.ok) {
      accountMenu.hidden = true;
      openAuthBtn.hidden = false;
      return null;
    }

    const user = await response.json();
    setAccountName(user.username);
    profileForm.elements.username.value = user.username;
    profileForm.elements.email.value = user.email;
    accountMenu.hidden = false;
    openAuthBtn.hidden = true;
    return user;
  }

  openAuthBtn.addEventListener('click', () => {
    showAuthTab('login');
    authDialog.showModal();
  });

  for (const button of document.querySelectorAll('[data-auth-tab]')) {
    button.addEventListener('click', () => showAuthTab(button.dataset.authTab));
  }

  document.getElementById('forgotPasswordBtn').addEventListener('click', showForgotPassword);
  document.getElementById('backToLoginBtn').addEventListener('click', () => showAuthTab('login'));

  for (const button of document.querySelectorAll('[data-close-dialog]')) {
    button.addEventListener('click', () => button.closest('dialog').close());
  }

  for (const dialog of [authDialog, profileDialog]) {
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
  }

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(authMessage, '');
    const formData = new FormData(loginForm);
    try {
      const response = await fetch('/api/Users/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          username: formData.get('username'),
          password: formData.get('password'),
        }),
      });
      await responseData(response);
      await loadAccount();
      authDialog.close();
    } catch (error) {
      setMessage(authMessage, error.message, 'error');
    }
  });

  registerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(authMessage, '');
    const formData = new FormData(registerForm);
    const payload = Object.fromEntries(formData.entries());
    try {
      const response = await fetch('/api/Users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      await responseData(response);
      await loadAccount();
      authDialog.close();
      registerForm.reset();
    } catch (error) {
      setMessage(authMessage, error.message, 'error');
    }
  });

  forgotPasswordForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(authMessage, '');
    const email = new FormData(forgotPasswordForm).get('email');
    try {
      const response = await fetch('/api/Users/password/forgot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const data = await responseData(response);
      setMessageLink(authMessage, data.message, data.reset_url, 'Atur ulang password');
    } catch (error) {
      setMessage(authMessage, error.message, 'error');
    }
  });

  document.getElementById('profileBtn').addEventListener('click', async () => {
    const user = await loadAccount();
    if (!user) {
      authDialog.showModal();
      return;
    }
    setMessage(profileMessage, '');
    setMessage(passwordMessage, '');
    profileDialog.showModal();
  });

  profileForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(profileMessage, '');
    const payload = Object.fromEntries(new FormData(profileForm).entries());
    try {
      const response = await fetch('/api/Users/me', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify(payload),
      });
      const data = await responseData(response);
      setAccountName(data.username);
      profileForm.elements.username.value = data.username;
      profileForm.elements.email.value = data.email;
      setMessage(profileMessage, 'Profil berhasil diperbarui.', 'success');
    } catch (error) {
      setMessage(profileMessage, error.message, 'error');
    }
  });

  passwordForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(passwordMessage, '');
    const payload = Object.fromEntries(new FormData(passwordForm).entries());
    try {
      const response = await fetch('/api/Users/me/password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCsrfToken(),
        },
        body: JSON.stringify(payload),
      });
      const data = await responseData(response);
      profileDialog.close();
      await loadAccount();
      showAuthTab('login');
      setMessage(authMessage, data.message, 'success');
      authDialog.showModal();
      passwordForm.reset();
    } catch (error) {
      setMessage(passwordMessage, error.message, 'error');
    }
  });

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    try {
      const response = await fetch('/api/Users/logout', {
        method: 'POST',
        headers: { 'X-CSRF-Token': getCsrfToken() },
      });
      await responseData(response);
      await loadAccount();
    } catch (error) {
      console.error('Gagal keluar:', error);
    }
  });

  loadAccount().catch((error) => console.error('Gagal memuat akun:', error));

  const authParams = new URLSearchParams(window.location.search);
  if (authParams.has('forgot_password') || authParams.has('login')) {
    if (authParams.has('forgot_password')) {
      showForgotPassword();
    } else {
      showAuthTab('login');
    }
    authDialog.showModal();
    window.history.replaceState({}, '', window.location.pathname);
  }
}

const resetPasswordForm = document.getElementById('resetPasswordForm');
if (resetPasswordForm) {
  const resetPasswordMessage = document.getElementById('resetPasswordMessage');
  const resetLoginLink = document.getElementById('resetLoginLink');

  resetPasswordForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    resetPasswordMessage.textContent = '';
    resetPasswordMessage.className = 'form-message';
    const payload = Object.fromEntries(new FormData(resetPasswordForm).entries());

    try {
      const response = await fetch('/api/Users/password/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Password gagal diubah. Silakan coba lagi.');
      }

      resetPasswordForm.hidden = true;
      resetPasswordMessage.textContent = data.message;
      resetPasswordMessage.classList.add('success');
      resetLoginLink.hidden = false;
    } catch (error) {
      resetPasswordMessage.textContent = error.message;
      resetPasswordMessage.classList.add('error');
    }
  });
}
