export interface PantryItem {
  id: number;
  ingredient_id: number | null;
  original_input: string;
  display_name: string;
  normalized_key: string;
  normalization_version: number;
  created_at: string;
}

export interface PantryResponse { items: PantryItem[] }
export interface BatchResponse extends PantryResponse {
  added_count: number;
  skipped_count: number;
  results: {
    entry_index: number;
    original_input: string;
    display_name: string;
    item_id: number;
    outcome: 'added' | 'skipped_duplicate';
  }[];
}

export interface RequirementsResponse {
  must_use: PantryItem[];
  prefer_to_avoid: { original_input: string; display_name: string; normalized_key: string }[];
  excluded: { original_input: string; display_name: string; normalized_key: string }[];
  warnings: { code: string; item_id: number; display_name: string; message: string }[];
  check_scope: 'reviewed_name_overlap_only';
  recipe_generated: false;
}

export interface RecipeIngredient { name: string; quantity: number; unit: string }
export interface RecipeMatch extends RecipeIngredient { normalized_key: string; pantry_item_id: number | null }
export interface SuggestionsResponse {
  source: 'sample' | 'openai' | 'groq';
  check_scope: 'structure_and_ingredient_names_only';
  rejected: { candidate_index: number; codes: string[] }[];
  recipes: {
    recipe: { title: string; servings: number; prep_minutes: number; cook_minutes: number;
      ingredients: RecipeIngredient[]; instructions: string[] };
    in_pantry: RecipeMatch[];
    missing: RecipeMatch[];
    warnings: { code: string; ingredient_name: string; message: string }[];
  }[];
}

export class ApiError extends Error {
  constructor(message: string, public requestId?: string, public field?: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit,
  kind: 'pantry' | 'requirements' | 'recipes' | 'capabilities' = 'pantry'): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), kind === 'recipes' ? 50000 : 15000);
  try {
    const response = await fetch(path, { ...init, signal: controller.signal });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(
        payload?.error?.message ?? `Fridgi could not complete the request (HTTP ${response.status}).`,
        response.headers.get('X-Request-ID') ?? undefined,
        payload?.error?.field,
      );
    }
    const valid = kind === 'recipes'
      ? payload && Array.isArray(payload.recipes) && Array.isArray(payload.rejected)
        && ['sample', 'openai', 'groq'].includes(payload.source)
        && payload.check_scope === 'structure_and_ingredient_names_only'
      : kind === 'capabilities'
      ? payload && typeof payload.live_available === 'boolean' && payload.sample_available === true
        && ['openai', 'groq'].includes(payload.live_source)
      : kind === 'requirements'
      ? payload && Array.isArray(payload.must_use) && Array.isArray(payload.prefer_to_avoid)
        && Array.isArray(payload.warnings) && payload.check_scope === 'reviewed_name_overlap_only'
        && payload.recipe_generated === false
      : payload && Array.isArray(payload.items);
    if (!valid) {
      throw new ApiError('Fridgi returned an unexpected response. Please retry.');
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      controller.signal.aborted
        ? kind !== 'pantry' ? 'The request took too long. Please wait before trying again.'
          : 'The request took too long. Refresh the pantry to check whether the change was saved before retrying.'
        : 'Could not connect to your pantry. Check that the backend is running, then refresh before retrying.',
    );
  } finally {
    window.clearTimeout(timer);
  }
}

export const getPantry = () => request<PantryResponse>('/api/pantry');
export const deletePantry = (id: number) => request<PantryResponse>(`/api/pantry/${id}`, {
  method: 'DELETE',
});
export const addPantry = (text: string) => request<BatchResponse>('/api/pantry/bulk', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text }),
});

export const checkRequirements = (mustUseItemIds: number[], preferToAvoidText: string, excludedText = '') =>
  request<RequirementsResponse>('/api/recipe-requests/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ must_use_item_ids: mustUseItemIds, prefer_to_avoid_text: preferToAvoidText, excluded_text: excludedText }),
  }, 'requirements');

export const getRecipeCapabilities = () => request<{ sample_available: true; live_available: boolean; live_source: 'groq' | 'openai' }>(
  '/api/recipes/capabilities', undefined, 'capabilities');

export const suggestRecipes = (mustUseItemIds: number[], preferToAvoidText: string, source: 'sample' | 'openai' | 'groq', excludedText = '') =>
  request<SuggestionsResponse>('/api/recipes/suggestions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ must_use_item_ids: mustUseItemIds, prefer_to_avoid_text: preferToAvoidText, excluded_text: excludedText, source }),
  }, 'recipes');
