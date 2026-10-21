import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, checkRequirements, getRecipeCapabilities, suggestRecipes } from './api';
import type { PantryItem, RequirementsResponse, SuggestionsResponse } from './api';
import { RecipeResults } from './RecipeResults';

interface Props {
  items: PantryItem[];
  pantryBusy: boolean;
  pantryError: ApiError | null;
  onRefresh: () => Promise<void>;
}

export function RecipeRequirements({ items, pantryBusy, pantryError, onRefresh }: Props) {
  const [selected, setSelected] = useState<PantryItem[]>([]);
  const [avoid, setAvoid] = useState('');
  const [excluded, setExcluded] = useState('');
  const [checking, setChecking] = useState(false);
  const [pendingAction, setPendingAction] = useState('Checking requirements…');
  const [recipes, setRecipes] = useState<SuggestionsResponse | null>(null);
  const [liveAvailable, setLiveAvailable] = useState(false);
  const [liveSource, setLiveSource] = useState<'groq' | 'openai'>('groq');
  const [result, setResult] = useState<RequirementsResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const requestVersion = useRef(0);
  const inFlight = useRef(false);
  const missing = selected.filter(item => !items.some(current => current.id === item.id));
  const disabled = checking || pantryBusy || pantryError !== null;

  useEffect(() => {
    let active = true;
    getRecipeCapabilities().then(data => { if (active) {
      setLiveAvailable(data.live_available);
      setLiveSource(data.live_source);
    } })
      .catch(() => { if (active) setLiveAvailable(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    // Ignore a pending response if the pantry changes or the component unmounts.
    requestVersion.current += 1;
    inFlight.current = false;
    setChecking(false);
    setResult(null);
    setRecipes(null);
    setError(null);
    return () => { requestVersion.current += 1; };
  }, [items, pantryBusy, pantryError]);

  function toggle(item: PantryItem) {
    setSelected(current => current.some(entry => entry.id === item.id)
      ? current.filter(entry => entry.id !== item.id) : [...current, item]);
    setResult(null);
    setRecipes(null);
    setError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run('check');
  }

  async function run(action: 'check' | 'sample' | 'openai' | 'groq') {
    if (disabled || inFlight.current) return;
    inFlight.current = true;
    const version = ++requestVersion.current;
    setChecking(true);
    setPendingAction(action === 'check' ? 'Checking requirements…' : action === 'sample' ? 'Checking the sample…' : 'Preparing recipe suggestions…');
    setResult(null);
    setRecipes(null);
    setError(null);
    try {
      if (action === 'check') {
        const checked = await checkRequirements(selected.map(item => item.id), avoid, excluded);
        if (version === requestVersion.current) setResult(checked);
      } else {
        const suggestions = await suggestRecipes(selected.map(item => item.id), avoid, action, excluded);
        if (version === requestVersion.current) setRecipes(suggestions);
      }
    } catch (failure) {
      if (version === requestVersion.current) setError(failure as ApiError);
    } finally {
      if (version === requestVersion.current) {
        inFlight.current = false;
        setChecking(false);
      }
    }
  }

  return <section className="requirements-panel" aria-labelledby="requirements-title">
    <span className="section-kicker">BEFORE WE START COOKING</span>
    <h2 id="requirements-title">What would you like to use?</h2>
    <p>Choose what matters for your next meal. Check your requirements, try a sample, or request recipe ideas.</p>
    <p className="field-help">All fields are optional. Reloading clears this form; your pantry stays saved.</p>
    {pantryError && <p role="alert">Your pantry could not be loaded. Refresh the pantry selections to try again.</p>}
    <button className="refresh-button" type="button" onClick={onRefresh} disabled={pantryBusy || checking}>
      Refresh pantry selections
    </button>
    <form onSubmit={submit} aria-busy={checking}>
      <fieldset disabled={disabled} aria-describedby={`must-use-help${missing.length ? ' missing-selections' : ''}${error?.field?.startsWith('must_use_item_ids') ? ' requirements-error' : ''}`}>
        <legend>Must use</legend>
        <p id="must-use-help" className="field-help">Select up to 50 pantry ingredients. Add anything missing to your pantry first.</p>
        {pantryBusy ? <p>Updating your pantry…</p> : !pantryError && items.length === 0 && <p>Your pantry is empty. You can still check avoidance preferences.</p>}
        <div className="requirement-choices">
          {items.map(item => <label key={item.id}>
            <input type="checkbox" checked={selected.some(entry => entry.id === item.id)}
              onChange={() => toggle(item)} value={item.id} />
            <span>{item.display_name}</span>
          </label>)}
        </div>
        {missing.length > 0 && <div id="missing-selections" className="requirement-warning" role="alert">
          <p>These selected ingredients are no longer in your pantry. Uncheck them, or add them again and select the new entries.</p>
          {missing.map(item => <label key={item.id}>
            <input type="checkbox" checked onChange={() => toggle(item)} value={item.id} />
            <span>{item.display_name} (no longer available)</span>
          </label>)}
        </div>}
      </fieldset>
      <label htmlFor="prefer-to-avoid">Prefer to avoid</label>
      <textarea id="prefer-to-avoid" rows={3} value={avoid} disabled={disabled}
        onChange={event => { setAvoid(event.target.value); setResult(null); setRecipes(null); setError(null); }}
        aria-describedby={`avoid-help avoid-limits${error?.field?.startsWith('prefer_to_avoid_text') ? ' requirements-error' : ''}`}
        aria-invalid={error?.field?.startsWith('prefer_to_avoid_text') || undefined}
        placeholder="Foods you would rather skip, separated by commas or new lines" />
      <p id="avoid-help" className="field-help">These are preferences. If a food is also required, must-use takes priority. Dietary and allergy restrictions are not evaluated here.</p>
      <p id="avoid-limits" className="field-limit">Up to 50 entries · 100 characters per name · 10,000 total</p>
      <label htmlFor="do-not-use">Do not use</label>
      <textarea id="do-not-use" rows={3} value={excluded} disabled={disabled}
        onChange={event => { setExcluded(event.target.value); setResult(null); setRecipes(null); setError(null); }}
        aria-describedby={`exclude-help exclude-limits${error?.field === 'excluded_text' ? ' requirements-error' : ''}`}
        aria-invalid={error?.field === 'excluded_text' || undefined}
        placeholder="Ingredients to exclude, separated by commas or new lines" />
      <p id="exclude-help" className="field-help"><strong>Ingredient-name check only.</strong> Matching names block a recipe. Contents of sauces, leftovers and branded foods, cooking instructions, diets and allergens are not verified. This is not an allergy safety check.</p>
      <p id="exclude-limits" className="field-limit">Up to 50 entries · 100 characters per name · 10,000 total</p>
      {error && <div id="requirements-error" className="error-notice" role="alert">
        <p>{error.message}</p>
        {error.requestId && <details><summary>Request details</summary><code>{error.requestId}</code></details>}
      </div>}
      <button className="primary-button" disabled={disabled} type="submit">
        Check requirements
      </button>
      <div className="recipe-actions">
        <button className="refresh-button" type="button" disabled={disabled} onClick={() => run('sample')}>Try a sample recipe</button>
        <p className="field-help">Fixed example: Greek yogurt, apple, and oats. No AI call. It must still match your must-use selections.</p>
        <button className="primary-button" type="button" disabled={disabled || !liveAvailable} onClick={() => run(liveSource)}>Generate recipe suggestions</button>
        <p className="field-help">{liveAvailable
          ? liveSource === 'groq'
            ? 'Sends pantry ingredient names and requirements to Groq. Stay on the Groq Free plan to avoid API charges; usage limits apply. Fridgi cannot verify your billing plan.'
            : 'Sends pantry ingredient names and requirements to OpenAI. Uses your configured API account; charges may apply.'
          : 'Live generation is not available. Configure it in the backend and reload this page; the sample works without an API key.'}</p>
      </div>
    </form>
    <div className="status" role="status" aria-live="polite" aria-atomic="true">
      {checking ? pendingAction : recipes ? `${recipes.recipes.length} ${recipes.source === 'sample' ? 'sample recipe' : 'recipe suggestions'} ready. ${recipes.rejected.length} candidates omitted.` : result ? `Requirements checked. ${result.warnings.length} preference ${result.warnings.length === 1 ? 'warning' : 'warnings'}.` : ''}
    </div>
    {result && <div className="requirements-result" data-testid="requirements-result">
      <h3>Your requirements</h3>
      <h4>Must use</h4>
      {result.must_use.length ? <ul>{result.must_use.map(item => <li key={item.id}>{item.display_name}</li>)}</ul> : <p>No required ingredients.</p>}
      <h4>Prefer to avoid</h4>
      {result.prefer_to_avoid.length ? <ul>{result.prefer_to_avoid.map(item => <li key={item.normalized_key}>{item.display_name}</li>)}</ul> : <p>No avoidance preferences.</p>}
      <h4>Do not use</h4>
      {result.excluded.length ? <ul>{result.excluded.map(item => <li key={item.normalized_key}>{item.display_name}</li>)}</ul> : <p>No excluded ingredients.</p>}
      {result.warnings.length > 0 && <div className="requirement-warning"><h4>Preference warnings</h4>
        <ul>{result.warnings.map(warning => <li key={warning.item_id}>{warning.message}</li>)}</ul>
      </div>}
      <p className="field-help">Only name overlap between these lists was checked, using reviewed aliases. Compound-food contents, diets, and allergens were not checked. No recipe has been generated.</p>
    </div>}
    {recipes && <RecipeResults result={recipes} />}
  </section>;
}
