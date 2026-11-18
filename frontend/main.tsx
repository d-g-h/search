import { StrictMode, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Listing = {
  id: string;
  source: string;
  address: string;
  city: string;
  state: string;
  zip: string;
  price: number;
  bedrooms: number;
  bathrooms: number;
  sqft: number;
  listedDate: string;
  status: string;
  description: string;
  relevanceScore: number;
};

type SearchResponse = {
  items: Listing[];
  total: number;
  page: number;
  totalPages: number;
};

type Results =
  | { status: 'loading' }
  | { status: 'ready'; data: SearchResponse }
  | { status: 'error'; message: string };

const defaultPageSize = '6';
const initialSearch = { filters: new URLSearchParams({ pageSize: defaultPageSize }), page: 1 };
const filterFormId = 'search-filters';

const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});
const integer = new Intl.NumberFormat('en-US');
const dateOptions: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeZone: 'UTC' };
const labelClass = 'block text-sm font-medium';
const controlClass =
  'mt-1 block w-full min-w-0 rounded-sm border border-line bg-surface px-2 py-2 text-sm font-normal text-ink placeholder:text-muted user-invalid:border-danger';
const secondaryButtonClass =
  'rounded-sm border border-line bg-surface px-3 py-2 text-sm enabled:cursor-pointer enabled:hover:bg-canvas disabled:opacity-50';

function App() {
  const [search, setSearch] = useState(initialSearch);
  const [results, setResults] = useState<Results>({ status: 'loading' });
  const [formError, setFormError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setResults({ status: 'loading' });

    const params = new URLSearchParams(search.filters);
    params.set('page', String(search.page));

    async function load() {
      try {
        const response = await fetch(`/api/listings?${params}`, { signal: controller.signal });
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.error?.message ?? `Search failed (HTTP ${response.status}).`);
        }
        const data: SearchResponse = await response.json();
        if (!controller.signal.aborted) setResults({ status: 'ready', data });
      } catch (cause) {
        if (controller.signal.aborted) return;

        let message = 'Search failed. Please try again.';
        if (cause instanceof TypeError) {
          message = 'Could not reach the search service. Check that the Python API is running.';
        } else if (cause instanceof Error) {
          message = cause.message;
        }
        setResults({ status: 'error', message });
      }
    }

    void load();
    return () => controller.abort();
  }, [search]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const filters = new URLSearchParams();
    for (const [name, value] of new FormData(event.currentTarget)) {
      if (typeof value !== 'string') continue;
      const trimmed = value.trim();
      if (trimmed) filters.set(name, trimmed);
    }

    const minimum = filters.get('minPrice');
    const maximum = filters.get('maxPrice');
    if (minimum !== null && maximum !== null && Number(minimum) > Number(maximum)) {
      setFormError('Minimum price must be less than or equal to maximum price.');
      return;
    }
    setFormError('');
    setSearch({ filters, page: 1 });
  }

  function reset() {
    setFormError('');
    setSearch({ ...initialSearch });
  }

  const data = results.status === 'ready' ? results.data : null;

  return (
    <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <h1 className="mb-5 text-2xl font-semibold">Search</h1>

      <div className="grid items-start gap-6 md:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="border border-line bg-surface p-4" aria-labelledby="filter-title">
          <div className="mb-4 flex items-center justify-between">
            <h2 id="filter-title" className="font-semibold">
              Filters
            </h2>
            <button
              type="reset"
              form={filterFormId}
              className="cursor-pointer text-sm text-accent underline"
            >
              Reset
            </button>
          </div>
          <form
            id={filterFormId}
            className="space-y-4"
            onSubmit={submit}
            onReset={reset}
            onInput={() => setFormError('')}
          >
            <label className={labelClass}>
              City
              <input
                name="city"
                className={controlClass}
                placeholder="e.g. Springfield"
                maxLength={200}
              />
            </label>

            <label className={labelClass}>
              Description keyword
              <input
                name="keyword"
                className={controlClass}
                placeholder="e.g. fenced yard"
                maxLength={300}
              />
            </label>

            <fieldset className="min-w-0">
              <legend className="mb-1 text-sm font-medium">Price range</legend>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-muted">
                  Minimum ($)
                  <input
                    name="minPrice"
                    className={controlClass}
                    type="number"
                    min="0"
                    step="any"
                    placeholder="No min"
                  />
                </label>
                <label className="text-xs text-muted">
                  Maximum ($)
                  <input
                    name="maxPrice"
                    className={controlClass}
                    type="number"
                    min="0"
                    step="any"
                    placeholder="No max"
                  />
                </label>
              </div>
            </fieldset>

            <label className={labelClass}>
              Minimum bedrooms
              <input
                name="minBedrooms"
                className={controlClass}
                type="number"
                min="0"
                step="1"
                placeholder="Any"
              />
            </label>

            <div>
              <label className={labelClass}>
                Target budget ($)
                <input
                  name="targetBudget"
                  className={controlClass}
                  type="number"
                  min="0.01"
                  step="any"
                  placeholder="e.g. 500000"
                  aria-describedby="budget-hint"
                />
              </label>
              <p id="budget-hint" className="mt-1 text-xs text-muted">
                Used for ranking. Use maximum price to set a limit.
              </p>
            </div>

            <label className={labelClass}>
              Results per page
              <select name="pageSize" className={controlClass} defaultValue={defaultPageSize}>
                <option value="3">3</option>
                <option value="6">6</option>
                <option value="12">12</option>
              </select>
            </label>

            {formError && (
              <p className="text-sm text-danger" role="alert">
                {formError}
              </p>
            )}
            <button
              className="w-full cursor-pointer rounded-sm bg-accent px-3 py-2 text-sm font-medium text-surface hover:bg-accent-hover"
              type="submit"
            >
              Search listings
            </button>
          </form>
        </aside>

        <section className="min-w-0" aria-labelledby="results-title">
          <h2 id="results-title" className="mb-2 text-lg font-semibold wrap-anywhere">
            {search.filters.get('city') || 'All locations'}
          </h2>

          {results.status === 'loading' && (
            <p className="text-sm text-muted" role="status">
              Loading listings…
            </p>
          )}
          {results.status === 'error' && (
            <div className="space-y-2 border border-line bg-surface p-4 text-sm" role="alert">
              <h3 className="font-medium text-danger">Couldn’t load listings</h3>
              <p>{results.message}</p>
              <button className={secondaryButtonClass} onClick={() => setSearch({ ...search })}>
                Try again
              </button>
            </div>
          )}
          {data?.items.length === 0 && (
            <div className="space-y-2 border border-line bg-surface p-4 text-sm">
              <p role="status">No listings match this search</p>
              <button type="reset" form={filterFormId} className={secondaryButtonClass}>
                Clear filters
              </button>
            </div>
          )}

          {data && data.items.length > 0 && (
            <>
              <p className="mb-3 text-sm text-muted" role="status">
                {data.total} {data.total === 1 ? 'listing' : 'listings'} · Sorted by relevance
              </p>
              <ul className="divide-y divide-line border border-line bg-surface" role="list">
                {data.items.map((listing) => (
                  <li className="space-y-2 p-4 text-sm" key={`${listing.source}:${listing.id}`}>
                    <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                      <h3 className="font-semibold">{listing.address}</h3>
                      <p className="font-semibold">{currency.format(listing.price)}</p>
                    </div>
                    <p className="text-muted">
                      {listing.city}, {listing.state} {listing.zip}
                    </p>
                    <div className="flex flex-wrap gap-x-3 gap-y-1">
                      <span>{listing.bedrooms} beds</span>
                      <span>{listing.bathrooms} baths</span>
                      <span>{integer.format(listing.sqft)} sq ft</span>
                    </div>
                    <p>{listing.description}</p>
                    <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-muted">
                      <p>
                        <span className="capitalize">{listing.status}</span> · {listing.source} ·
                        Listed{' '}
                        <time dateTime={listing.listedDate}>
                          {new Date(`${listing.listedDate}T00:00:00Z`).toLocaleDateString(
                            'en-US',
                            dateOptions,
                          )}
                        </time>
                      </p>
                      <p>
                        Relevance score{' '}
                        <strong className="text-ink">
                          {listing.relevanceScore.toFixed(2)} / 100
                        </strong>
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
              <nav
                className="mt-4 flex flex-wrap items-center gap-3 text-sm"
                aria-label="Search result pages"
              >
                <button
                  className={secondaryButtonClass}
                  disabled={data.page <= 1}
                  onClick={() => setSearch({ ...search, page: data.page - 1 })}
                >
                  Previous page
                </button>
                <span>
                  Page <strong>{data.page}</strong> of {data.totalPages}
                </span>
                <button
                  className={secondaryButtonClass}
                  disabled={data.page >= data.totalPages}
                  onClick={() => setSearch({ ...search, page: data.page + 1 })}
                >
                  Next page
                </button>
              </nav>
            </>
          )}
        </section>
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
