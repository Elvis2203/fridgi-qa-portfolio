import type { RecipeMatch, SuggestionsResponse } from './api';

function IngredientList({ items, empty }: { items: RecipeMatch[]; empty: string }) {
  return items.length ? <ul>{items.map(item => <li key={item.normalized_key}>
    {item.quantity} {item.unit} {item.name}
  </li>)}</ul> : <p>{empty}</p>;
}

export function RecipeResults({ result }: { result: SuggestionsResponse }) {
  return <section className="recipe-results" aria-label="Recipe suggestions" data-testid="recipe-results">
    <h3>{result.source === 'sample' ? 'Fixed sample recipe' : 'Your recipe suggestions'}</h3>
    <p>{result.source === 'sample'
      ? 'This is a fixed example, not an AI-generated or personalized recipe.'
      : `Generated using ${result.source === 'groq' ? 'Groq' : 'OpenAI'}; Fridgi checked the structure and ingredient names.`}</p>
    {result.rejected.length > 0 && <p role="status">{result.rejected.length} {result.rejected.length === 1 ? 'candidate was' : 'candidates were'} omitted because they did not pass the recipe checks.</p>}
    {result.recipes.map((checked, index) => <article className="recipe-card" key={index}>
      <h4>{checked.recipe.title}</h4>
      <p>{checked.recipe.servings} {checked.recipe.servings === 1 ? 'serving' : 'servings'} · {checked.recipe.prep_minutes} min preparation · {checked.recipe.cook_minutes} min cooking</p>
      <div className="recipe-ingredients">
        <div><h5>In your pantry</h5><IngredientList items={checked.in_pantry} empty="None of these ingredient names match your pantry." /></div>
        <div><h5>Missing ingredients</h5><IngredientList items={checked.missing} empty="All ingredient names match your pantry." /></div>
      </div>
      <p className="field-help">Pantry matches are by ingredient name. Check that you have enough for these quantities.</p>
      {checked.warnings.length > 0 && <div className="requirement-warning"><h5>Preference warnings</h5>
        <ul>{checked.warnings.map((warning, i) => <li key={i}>{warning.message}</li>)}</ul>
      </div>}
      <h5>Instructions</h5>
      <ol>{checked.recipe.instructions.map((step, i) => <li key={i}>{step}</li>)}</ol>
    </article>)}
    <p className="field-help">These checks do not verify cooking instructions, food safety, nutrition, compound-food contents, or allergens. Dietary and allergy restrictions are not supported in this version.</p>
  </section>;
}
