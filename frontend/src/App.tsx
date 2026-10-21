import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { addPantry, ApiError, deletePantry, getPantry } from './api';
import type { BatchResponse, PantryItem } from './api';
import { RecipeRequirements } from './RecipeRequirements';

function PantryDrawing() {
  return <svg className="pantry-drawing" viewBox="0 0 240 160" fill="none" aria-hidden="true">
    <path d="M28 135h184M42 93h156" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <rect x="52" y="42" width="43" height="49" rx="10" fill="#e1b58d" />
    <path d="M56 42v-7h35v7" stroke="currentColor" strokeWidth="3" />
    <path d="M65 57h17v20H65z" stroke="currentColor" strokeWidth="2" />
    <path d="M132 90c-28-18-15-39-3-30 12-22 30 1 3 30Z" fill="#8fa984" />
    <path d="m132 90 2-35m0 8c-15-6-15-20-6-24 10 7 11 17 6 24Z" stroke="currentColor" strokeWidth="2" />
    <path d="M157 72c0-20 28-20 28 0v18h-28Z" fill="#d9a75a" />
    <path d="m166 65 7 6m-7 5 7 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <rect x="76" y="106" width="57" height="27" rx="8" fill="#8fa984" />
    <path d="M83 114h43" stroke="currentColor" strokeWidth="2" />
    <ellipse cx="157" cy="122" rx="12" ry="10" fill="#e1b58d" />
  </svg>;
}

function ErrorNotice({ error, id }: { error: ApiError; id: string }) {
  return <div className="error-notice" id={id} role="alert">
    <p>{error.message}</p>
    {error.requestId && <details><summary>Request details</summary><code>{error.requestId}</code></details>}
  </div>;
}

export function App() {
  const [items, setItems] = useState<PantryItem[]>([]);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<ApiError | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<BatchResponse | null>(null);
  const [status, setStatus] = useState('Loading your pantry…');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const pantryHeadingRef = useRef<HTMLHeadingElement>(null);
  const saveInFlight = useRef(false);
  const busy = loading || saving || deletingId !== null;

  useEffect(() => {
    let active = true;
    getPantry().then(data => {
      if (active) { setItems(data.items); setStatus(''); }
    }).catch((error: ApiError) => {
      if (active) { setLoadError(error); setStatus(''); }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function refresh() {
    if (saveInFlight.current || loading) return;
    setLoading(true);
    setLoadError(null);
    setDeleteError(null);
    setStatus('Loading your pantry…');
    try {
      const data = await getPantry();
      setItems(data.items);
      setStatus('Pantry refreshed.');
    } catch (error) {
      setLoadError(error as ApiError);
      setStatus('');
    } finally { setLoading(false); }
  }

  async function remove(item: PantryItem) {
    if (saveInFlight.current || loading) return;
    saveInFlight.current = true;
    setDeletingId(item.id);
    setDeleteError(null);
    setResult(null);
    setStatus(`Deleting ${item.display_name}…`);
    try {
      const data = await deletePantry(item.id);
      setItems(data.items);
      setStatus(`${item.display_name} deleted from your pantry.`);
      pantryHeadingRef.current?.focus();
    } catch (error) {
      setDeleteError(error as ApiError);
      setStatus('');
    } finally {
      setDeletingId(null);
      saveInFlight.current = false;
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saveInFlight.current || loading) return;
    saveInFlight.current = true;
    setSaving(true);
    setSaveError(null);
    setResult(null);
    setStatus('Saving your ingredients…');
    try {
      const data = await addPantry(text);
      setItems(data.items);
      setLoadError(null);
      setResult(data);
      setText('');
      setStatus(`${data.added_count} added to your pantry. ${data.skipped_count} ${data.skipped_count === 1 ? 'duplicate' : 'duplicates'} skipped.`);
    } catch (error) {
      setSaveError(error as ApiError);
      setStatus('');
    } finally {
      setSaving(false);
      saveInFlight.current = false;
      inputRef.current?.focus();
    }
  }

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="site-header">
      <a className="brand" href="/" aria-label="Fridgi home"><span className="brand-icon" aria-hidden="true">f.</span>fridgi<span className="brand-dot">.</span></a>
      <span className="header-note">Good food starts with what you have.</span>
      <span className="local-badge"><span aria-hidden="true" />Your personal pantry</span>
    </header>
    <main id="main">
      <section className="intro" aria-labelledby="page-title">
        <p className="eyebrow">LESS REMEMBERING. MORE COOKING.</p>
        <h1 id="page-title">A little pantry.<br /><span>A good place to start.</span></h1>
        <p className="intro-copy">The staples, the leftovers, that something from the market.<br className="desktop-break" /> Add what you have. We’ll keep it here for you.</p>
      </section>
      <div className="workspace">
        <section className="entry-panel" aria-labelledby="add-title">
          <span className="section-kicker">MAKE YOURSELF AT HOME</span>
          <h2 id="add-title">What’s in your kitchen?</h2>
          <p>One ingredient or a whole grocery bag. Names are all you need.</p>
          <form onSubmit={submit} aria-busy={saving}>
            <label htmlFor="ingredients">Ingredients</label>
            <textarea id="ingredients" data-testid="ingredient-input" ref={inputRef}
              value={text} readOnly={saving} rows={6}
              onChange={event => { setText(event.target.value); setSaveError(null); setResult(null); setStatus(''); }}
              aria-describedby={`ingredient-help ingredient-limits${saveError ? ' save-error' : ''}`}
              aria-invalid={saveError?.field === 'text' || undefined}
              placeholder={'eggs, spinach, rice\nleftover roast chicken\nhomemade tomato sauce'} />
            <p id="ingredient-help" className="field-help">Separate ingredients with commas or new lines. Duplicates are skipped.</p>
            <p id="ingredient-limits" className="field-limit">Up to 50 entries · 100 characters per name · 10,000 total</p>
            {saveError && <ErrorNotice error={saveError} id="save-error" />}
            <button className="primary-button" type="submit" disabled={busy} data-testid="add-ingredients">
              {saving ? 'Adding ingredients…' : 'Add to my pantry'}<span aria-hidden="true">↗</span>
            </button>
          </form>
          <div className="status" role="status" aria-live="polite" aria-atomic="true">{status}</div>
          {result && result.skipped_count > 0 && <details className="duplicate-details">
            <summary>See skipped duplicates ({result.skipped_count})</summary>
            <ul>{result.results.filter(entry => entry.outcome === 'skipped_duplicate').map(entry =>
              <li key={entry.entry_index}>Entry {entry.entry_index}: {entry.original_input.trim()} — already saved as {entry.display_name}</li>
            )}</ul>
          </details>}
          <div className="entry-footnote"><span aria-hidden="true">✳</span><p>Homemade, hard to pronounce, or simply “leftover pasta.”<br />There’s room for it here.</p></div>
        </section>
        <section className="pantry-panel" aria-labelledby="pantry-title" aria-busy={busy}>
          <div className="pantry-heading"><div><span className="section-kicker">A LITTLE LESS TO REMEMBER</span><h2 id="pantry-title" ref={pantryHeadingRef} tabIndex={-1}>Your pantry <span className="item-count" aria-label={`${items.length} ingredients`}>{items.length}</span></h2></div>
            <button className="refresh-button" type="button" onClick={refresh} disabled={busy} aria-label="Refresh pantry">Refresh</button>
          </div>
          {deleteError && <ErrorNotice error={deleteError} id="delete-error" />}
          {loadError ? <ErrorNotice error={loadError} id="load-error" /> : loading ?
            <p className="loading-copy">Opening your pantry…</p> : items.length === 0 ?
            <div className="empty-pantry"><PantryDrawing /><h3>A fresh start.</h3><p>Your pantry is ready for its first ingredients.<br />Start with a few things you already have.</p></div> :
            <ul className="ingredient-list" data-testid="pantry-list">{items.map((item, index) =>
              <li key={item.id} data-testid="pantry-item"><span className="ingredient-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span><div><span className="ingredient-name">{item.display_name}</span>
                {item.ingredient_id !== null && item.original_input.trim() !== item.display_name && <span className="original-name">Entered as “{item.original_input.trim()}”</span>}
              </div><button className="delete-button" type="button" onClick={() => remove(item)}
                disabled={busy} aria-label={`Delete ${item.display_name}`} data-testid="delete-ingredient">
                {deletingId === item.id ? 'Deleting…' : 'Delete'}
              </button></li>
            )}</ul>}
          <p className="pantry-note">Saved on this computer. Here when you come back.</p>
        </section>
      </div>
      <RecipeRequirements items={items} pantryBusy={busy} pantryError={loadError} onRefresh={refresh} />
    </main>
    <footer><span>fridgi · a little less food forgotten</span><span>Built one useful step at a time.</span></footer>
  </>;
}
