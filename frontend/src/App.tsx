
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import {
  FileText, Plus, Search, Share2, Upload, Trash2,
  Bold, Italic, Underline as UnderlineIcon, List, ListOrdered,
  Heading1, Heading2, Save, Users, Clock3, ChevronLeft,
  LogOut, LockKeyhole
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type Doc = {
  id: number;
  title: string;
  content: any;
  owner_id: number;
  owner_name: string;
  access: string;
  updated_at: string;
};

type User = {
  id: number;
  name: string;
  email: string;
};

const EMPTY_DOC = {
  type: 'doc',
  content: [{ type: 'paragraph' }]
};

async function request(path: string, options: RequestInit = {}) {
  const isForm = options.body instanceof FormData;

  const res = await fetch(API + path, {
    ...options,
    credentials: 'include',
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers
    }
  });

  const data = await res.json().catch(() => ({
    detail: 'Unexpected server response'
  }));

  if (!res.ok) {
    throw new Error(data.detail || 'Request failed');
  }

  return data;
}

export default function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);

  const [owned, setOwned] = useState<Doc[]>([]);
  const [shared, setShared] = useState<Doc[]>([]);
  const [active, setActive] = useState<Doc | null>(null);
  const [users, setUsers] = useState<User[]>([]);

  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('All changes saved');
  const [error, setError] = useState('');

  const [shareOpen, setShareOpen] = useState(false);
  const [shareEmail, setShareEmail] = useState('alex@example.com');
  const [permission, setPermission] = useState('viewer');

  const [email, setEmail] = useState('tarun@example.com');
  const [password, setPassword] = useState('TarunDemo!2026');
  const [authError, setAuthError] = useState('');
  const [busy, setBusy] = useState(false);

  // Autosave tracking
  const revisionRef = useRef(0);
  const savedRevisionRef = useRef(0);
  const timerRef = useRef<number | null>(null);

  // All saves are serialized through this promise.
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());

  const [revision, setRevision] = useState(0);

  const editor = useEditor(
    {
      extensions: [StarterKit, Underline],
      content: active?.content || EMPTY_DOC,
      editable: active?.access !== 'viewer',

      onUpdate: () => {
        revisionRef.current += 1;
        setRevision(revisionRef.current);
        setStatus('Unsaved changes');
      }
    },
    [active?.id, active?.access]
  );

  async function load() {
    const d = await request('/api/documents');

    setOwned(d.owned);
    setShared(d.shared);
    setUsers(await request('/api/users'));
  }

  // Authentication
  useEffect(() => {
    request('/api/auth/me')
      .then(async (u: User) => {
        setCurrentUser(u);
        await load();
      })
      .catch(() => setCurrentUser(null))
      .finally(() => setAuthChecked(true));
  }, []);

  // Synchronize the editor when opening another document.
  useEffect(() => {
    if (!active || !editor) return;

    editor.commands.setContent(active.content || EMPTY_DOC, false);
    editor.setEditable(active.access !== 'viewer');

    revisionRef.current = 0;
    savedRevisionRef.current = 0;

    setRevision(0);
    setStatus('All changes saved');
  }, [active?.id, active?.access, editor]);

  // Mark title changes as unsaved.
  function markDirty() {
    revisionRef.current += 1;
    setRevision(revisionRef.current);
    setStatus('Unsaved changes');
  }

  // Save the current document with retries and serialized requests.
  const saveNow = useCallback(async (): Promise<boolean> => {
    if (!active || !editor || active.access === 'viewer') {
      return true;
    }

    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const documentId = active.id;
    const currentRevision = revisionRef.current;

    // Nothing new to save.
    if (currentRevision === savedRevisionRef.current) {
      return true;
    }

    const payload = {
      title: active.title,
      content: editor.getJSON()
    };

    setStatus('Saving…');

    const savedDocument: { result: Doc | null } = { result: null };

    const operation = saveQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        let lastError: unknown;

        // Initial attempt + two retries.
        for (let attempt = 0; attempt < 3; attempt++) {
          try {
            savedDocument.result = await request(
                `/api/documents/${documentId}`,
                {
                    method: 'PATCH',
                    body: JSON.stringify(payload)
                }
                ) as Doc;

            return;
          } catch (err) {
            lastError = err;

            if (attempt < 2) {
              await new Promise<void>(resolve => {
                window.setTimeout(resolve, 700 * (attempt + 1));
              });
            }
          }
        }

        throw lastError instanceof Error
          ? lastError
          : new Error('Unable to save document');
      });

    saveQueueRef.current = operation;

    try {
      await operation;

      if (savedDocument.result) {
        const updated = savedDocument.result;

        // Update document cards without replacing editor content.
        setOwned(previous =>
          previous.map(d =>
            d.id === documentId
              ? { ...d, title: updated.title, updated_at: updated.updated_at }
              : d
          )
        );

        setShared(previous =>
          previous.map(d =>
            d.id === documentId
              ? { ...d, title: updated.title, updated_at: updated.updated_at }
              : d
          )
        );
      }

      savedRevisionRef.current = Math.max(
        savedRevisionRef.current,
        currentRevision
      );

      if (revisionRef.current === currentRevision) {
        setStatus('All changes saved');
      } else {
        setStatus('Unsaved changes');
      }

      return true;

    } catch (err) {
      if (revisionRef.current === currentRevision) {
        setStatus('Save failed');
        setError(
          err instanceof Error ? err.message : 'Unable to save document'
        );
      } else {
        setStatus('Unsaved changes');
      }

      return false;
    }
  }, [active, editor]);

  // Debounced autosave.
  useEffect(() => {
    if (
      !active ||
      active.access === 'viewer' ||
      revision === savedRevisionRef.current
    ) {
      return;
    }

    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
    }

    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      void saveNow();
    }, 800);

    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [revision, active?.id, active?.access, saveNow]);

  // Save before leaving the editor.
  async function closeEditor() {
    const saved = await saveNow();

    if (saved) {
      setActive(null);
      setShareOpen(false);
    }
  }

  // Authentication actions.
  async function signIn(event: FormEvent) {
    event.preventDefault();

    setBusy(true);
    setAuthError('');

    try {
      const user = await request('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });

      setCurrentUser(user);
      await load();

    } catch (e: any) {
      setAuthError(e.message);

    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    try {
      await request('/api/auth/logout', { method: 'POST' });

      setCurrentUser(null);
      setActive(null);
      setOwned([]);
      setShared([]);

    } catch (e: any) {
      setError(e.message);
    }
  }

  // Create document.
  async function create() {
    try {
      const d = await request('/api/documents', {
        method: 'POST',
        body: JSON.stringify({ title: 'Untitled document' })
      });

      await load();
      setActive(d);
      setError('');

    } catch (e: any) {
      setError(e.message);
    }
  }

  // Delete document (owner only).
  async function deleteDocument(id: number) {
    const doc = owned.find(d => d.id === id);

    if (!doc) return;

    const confirmed = window.confirm(
      `Are you sure you want to permanently delete "${doc.title}"? This action cannot be undone.`
    );

    if (!confirmed) return;

    try {
      await request(`/api/documents/${id}`, {
        method: 'DELETE'
      });

      setOwned(previous =>
        previous.filter(d => d.id !== id)
      );

      setError('');
    } catch (e: any) {
      setError(e.message || 'Unable to delete document');
    }
  }

  // Rename document.
  function rename(title: string) {
    if (!active || active.access === 'viewer') return;

    setActive(previous =>
      previous ? { ...previous, title } : previous
    );

    markDirty();
  }

  // Import file.
  async function upload(file?: File) {
    if (!file) return;

    const form = new FormData();
    form.append('file', file);

    try {
      const d = await request('/api/import', {
        method: 'POST',
        body: form
      });

      await load();
      setActive(d);

    } catch (e: any) {
      setError(e.message);
    }
  }

  // Share document.
  async function share() {
    if (!active) return;

    try {
      await request(`/api/documents/${active.id}/shares`, {
        method: 'POST',
        body: JSON.stringify({
          email: shareEmail,
          permission
        })
      });

      setShareOpen(false);
      setError('');

    } catch (e: any) {
      setError(e.message);
    }
  }

  const docs = useMemo(
    () => [...owned, ...shared].filter(d =>
      d.title.toLowerCase().includes(query.toLowerCase())
    ),
    [owned, shared, query]
  );

  // Loading screen.
  if (!authChecked) {
    return (
      <div className="auth-screen">
        <div className="auth-card">Loading Draftly…</div>
      </div>
    );
  }

  // Login screen.
  if (!currentUser) {
    return (
      <div className="auth-screen">
        <form className="auth-card" onSubmit={signIn}>
          <div className="brand-mark auth-mark">
            <FileText />
          </div>

          <h1>Welcome to Draftly</h1>
          <p>Sign in to your workspace to continue.</p>

          <label>Email address</label>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
          />

          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />

          <div className="demo-hint">
            <LockKeyhole size={15} />
            <span>Demo: tarun@example.com · TarunDemo!2026</span>
          </div>

          {authError && (
            <div className="auth-error">{authError}</div>
          )}

          <button className="primary auth-submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    );
  }

  // Document editor.
  if (active) {
    return (
      <div className="editor-shell">
        <header className="topbar">
          <button className="icon-btn" onClick={() => void closeEditor()}>
            <ChevronLeft />
          </button>

          <FileText className="brand-icon" />

          <input
            className="title-input"
            value={active.title}
            disabled={active.access === 'viewer'}
            onChange={e => rename(e.target.value)}
          />

          <span className="save-state">
            <span className="dot" />
            {active.access === 'viewer'
              ? 'Read-only access'
              : status}
          </span>

          {active.access === 'owner' && (
            <button
              className="secondary"
              onClick={() => setShareOpen(true)}
            >
              <Share2 size={16} /> Share
            </button>
          )}

          {active.access !== 'viewer' && (
            <button
              className="primary"
              onClick={() => void saveNow()}
            >
              <Save size={16} /> Save
            </button>
          )}
        </header>

        <main className="page-wrap">
          <div className="paper">
            <div className="toolbar">
              {[
                [Bold, 'Bold',
                  () => editor?.chain().focus().toggleBold().run(),
                  () => editor?.isActive('bold')],
                [Italic, 'Italic',
                  () => editor?.chain().focus().toggleItalic().run(),
                  () => editor?.isActive('italic')],
                [UnderlineIcon, 'Underline',
                  () => editor?.chain().focus().toggleUnderline().run(),
                  () => editor?.isActive('underline')],
                [Heading1, 'Heading 1',
                  () => editor?.chain().focus().toggleHeading({ level: 1 }).run(),
                  () => editor?.isActive('heading', { level: 1 })],
                [Heading2, 'Heading 2',
                  () => editor?.chain().focus().toggleHeading({ level: 2 }).run(),
                  () => editor?.isActive('heading', { level: 2 })],
                [List, 'Bullets',
                  () => editor?.chain().focus().toggleBulletList().run(),
                  () => editor?.isActive('bulletList')],
                [ListOrdered, 'Numbered list',
                  () => editor?.chain().focus().toggleOrderedList().run(),
                  () => editor?.isActive('orderedList')]
              ].map(([Icon, label, fn, activeFn]: any) => (
                <button
                  disabled={active.access === 'viewer'}
                  title={label}
                  className={
                    'tool-btn ' + (activeFn() ? 'selected' : '')
                  }
                  onClick={fn}
                  key={label}
                >
                  <Icon size={17} />
                </button>
              ))}
            </div>

            <EditorContent editor={editor} />
          </div>
        </main>

        {shareOpen && (
          <div className="modal-backdrop">
            <div className="modal">
              <h3>Share document</h3>
              <p>Invite a teammate to collaborate.</p>

              <label>Email address</label>
              <select
                value={shareEmail}
                onChange={e => setShareEmail(e.target.value)}
              >
                {users.map(u => (
                  <option key={u.id} value={u.email}>
                    {u.name} · {u.email}
                  </option>
                ))}
              </select>

              <label>Permission</label>
              <select
                value={permission}
                onChange={e => setPermission(e.target.value)}
              >
                <option value="viewer">Can view</option>
                <option value="editor">Can edit</option>
              </select>

              <div className="modal-actions">
                <button
                  className="secondary"
                  onClick={() => setShareOpen(false)}
                >
                  Cancel
                </button>

                <button className="primary" onClick={share}>
                  Share
                </button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="toast" onClick={() => setError('')}>
            {error} ×
          </div>
        )}
      </div>
    );
  }

  // Main dashboard.
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <FileText />
          </div>
          <span>draftly</span>
        </div>

        <button className="new-doc" onClick={create}>
          <Plus size={18} /> New document
        </button>

        <div className="nav-label">WORKSPACE</div>

        <div className="nav-item active">
          <FileText size={17} /> All documents
        </div>

        <div className="nav-item">
          <Users size={17} /> Shared with me
          <span className="count">{shared.length}</span>
        </div>

        <div className="sidebar-bottom">
          <div className="avatar">
            {currentUser.name[0].toUpperCase()}
          </div>

          <div className="profile">
            <b>{currentUser.name}</b>
            <small>{currentUser.email}</small>
          </div>

          <button
            className="icon-btn"
            title="Sign out"
            onClick={signOut}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="main-header">
          <div>
            <div className="eyebrow">YOUR WORKSPACE</div>
            <h1>Documents</h1>
            <p>Capture ideas, shape thoughts, and work better together.</p>
          </div>

          <label className="upload-btn">
            <Upload size={16} /> Import file
            <input
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              onChange={e => {
                void upload(e.target.files?.[0]);
                e.target.value = '';
              }}
            />
          </label>
        </header>

        <div className="search-row">
          <div className="search">
            <Search size={17} />
            <input
              placeholder="Search documents..."
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </div>

          <span className="doc-count">
            {docs.length} documents
          </span>
        </div>

        <section>
          <div className="section-head">
            <h2>My documents</h2>
            <span>{owned.length} items</span>
          </div>

          <div className="doc-grid">
            {docs
              .filter(d => d.access === 'owner')
              .map(d => (
                <DocCard
                  key={d.id}
                  doc={d}
                  open={() => setActive(d)}
                  onDelete={() => void deleteDocument(d.id)}
                />
              ))}

            <button className="create-card" onClick={create}>
              <div className="plus-circle">
                <Plus />
              </div>
              <b>Create a document</b>
              <span>Start with a blank page</span>
            </button>
          </div>
        </section>

        <section className="shared-section">
          <div className="section-head">
            <h2>Shared with me</h2>
            <span>{shared.length} items</span>
          </div>

          {shared.length ? (
            <div className="doc-grid">
              {docs
                .filter(d => d.access !== 'owner')
                .map(d => (
                  <DocCard
                    key={d.id}
                    doc={d}
                    open={() => setActive(d)}
                  />
                ))}
            </div>
          ) : (
            <div className="empty-shared">
              <Users size={22} />
              <b>No shared documents yet</b>
              <span>Documents shared with you will appear here.</span>
            </div>
          )}
        </section>

        <footer>
          Draftly · A calmer space for collaborative work
        </footer>
      </main>

      {error && (
        <div className="toast" onClick={() => setError('')}>
          {error} ×
        </div>
      )}
    </div>
  );
}

function DocCard({
  doc,
  open,
  onDelete
}: {
  doc: Doc;
  open: () => void;
  onDelete?: () => void;
}) {
  return (
    <div className="doc-card-wrap">
      <button className="doc-card" onClick={open}>
        <div className="card-top">
          <div className="file-icon">
            <FileText />
          </div>
        </div>

        <b>{doc.title}</b>

        <span>
          {doc.access === 'owner'
            ? 'Owned by you'
            : `Shared by ${doc.owner_name}`}
        </span>

        <div className="card-foot">
          <span>
            <Clock3 size={13} />
            {new Date(doc.updated_at).toLocaleDateString()}
          </span>

          <span className={'access ' + (doc.access === 'owner' ? 'owned' : '')}>
            {doc.access === 'owner' ? 'Owner' : doc.access}
          </span>
        </div>
      </button>

      {doc.access === 'owner' && onDelete && (
        <button
          className="delete-doc-btn"
          title="Delete document"
          aria-label={`Delete ${doc.title}`}
          onClick={onDelete}
        >
          <Trash2 size={16} />
        </button>
      )}
    </div>
  );
}
