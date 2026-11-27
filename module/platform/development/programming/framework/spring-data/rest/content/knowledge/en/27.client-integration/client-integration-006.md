# Managing Pagination, Projections, and Data State in the UI with Spring Data REST

## Objectives

A UI consuming Spring Data REST must keep multiple pieces of state synchronized: which page the collection is on, which filters and sorting are active, which projection is selected, whether a request is in flight or finished, whether the data is empty or errored, and whether results are still fresh relative to the server.

If a client tracks only a page index and builds URLs manually, it can easily drop query parameters, land on an invalid page after changing filters, or keep rendering stale navigation links. If a client guesses projection names, it may request a representation the server has not published.

A reliable approach is to treat HAL responses as the source of navigation, manage query state separately from data state, and update items, metadata, and links together from a single consistent response. This guide explains how to coordinate pagination, projections, filters/sorting, loading/error/empty states, browser URLs, and data refreshes after writes.

## 1. Client-side state model

A Spring Data REST collection response typically has three key sections:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/api/people?page=1&size=20"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/people"
    }
  },
  "_embedded": {
    "people": [
      {
        "id": 42,
        "displayName": "Ada Lovelace"
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 51,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Separate state into distinct groups:

| State | Contents | Purpose |
|---|---|---|
| Query | Filter, sort, page size, projection. | Defines the active query. |
| Navigation | first/prev/self/next/last hrefs. | Navigates according to the server. |
| Page metadata | number, size, totalElements, totalPages. | Displays position and counts. |
| Data | Received items. | Renders tables or lists. |
| Request | idle, loading, success, empty, error. | Controls spinners and messages. |
| Freshness | Fetch timestamp or stale flag. | Detects when data needs refreshing. |
| Selection | Selected item IDs. | Preserves interactions across renders. |

When query state changes, previous data and navigation state may become invalid. When a new response arrives, update items, page metadata, and links atomically so the UI never ends up half-old, half-new.

## 2. Reading HAL collections and metadata

Example collection-fetching helper:

~~~javascript
async function fetchHal(url, signal) {
  const response = await fetch(url, {
    headers: { Accept: "application/hal+json" },
    signal
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  return response.json();
}
~~~

After receiving JSON, extract items by relation from _embedded and metadata from page:

~~~javascript
function readCollectionState(hal, relation) {
  const links = hal._links ?? {};
  const embedded = hal._embedded ?? {};
  const items = embedded[relation] ?? [];
  const page = hal.page ?? {};

  return {
    items,
    page: {
      number: page.number ?? 0,
      size: page.size ?? items.length,
      totalElements: page.totalElements ?? items.length,
      totalPages: page.totalPages ?? 0
    },
    navigation: {
      first: links.first?.href ?? null,
      prev: links.prev?.href ?? null,
      self: links.self?.href ?? null,
      next: links.next?.href ?? null,
      last: links.last?.href ?? null
    }
  };
}
~~~

The relation name in _embedded depends on the collection name published by Spring Data REST. Do not assume the relation is always items or an English plural of the entity name. Discover the relation from the API root/profile or repository configuration.

Some endpoints return unpaged collections without page metadata. Clients must support that case rather than accessing hal.page.number directly.

## 3. Navigating via server-provided hrefs

Common pagination relations:

- first: first page.
- prev: immediately preceding page.
- self: current page.
- next: next page.
- last: last page.

The UI enables/disables buttons based on link presence:

~~~javascript
const canGoPrevious = navigation.prev !== null;
const canGoNext = navigation.next !== null;
~~~

When the user clicks Next, fetch the received href:

~~~javascript
async function goToNextPage(state) {
  const href = state.navigation.next;
  if (!href) return null;
  return fetchHal(href);
}
~~~

Do not compute page + 1 manually when the response already provides a next link. The href can preserve sort, filter, page size, and custom query parameters. Constructing URLs manually easily drops part of that context.

Similarly, follow the href of first, prev, and last. If a relation is absent, that navigation action is currently unavailable per the response. Never fabricate a URL to force navigation.

### Displaying page numbers

The API typically uses a 0-based page index, whereas UIs display 1-based page numbers:

~~~javascript
const displayedPage = page.number + 1;
const displayedTotalPages = page.totalPages;
~~~

If totalPages equals 0, show an empty/no-results state instead of "Page 1 / 0". For responses without page metadata, do not render pagination controls by assumption.

## 4. Managing filters, sorting, and page size

Query state might include:

~~~javascript
const queryState = {
  searchText: "",
  status: "ACTIVE",
  sort: "lastName,asc",
  size: 20,
  projection: "personSummary"
};
~~~

When the user changes a filter or sort, it becomes a new query. Clients typically reset to page 0 because page 2 of the previous result set may not exist or make sense in the new result set.

Example initial search URL:

~~~text
/api/people/search/findByStatus?status=ACTIVE&page=2&size=20&sort=lastName,asc
~~~

If status changes to INACTIVE, initiate a new query with page=0. You can use URLSearchParams to build the initial URL:

~~~javascript
function buildInitialSearchUrl(baseUrl, state) {
  const url = new URL(baseUrl, window.location.origin);
  url.searchParams.set("status", state.status);
  url.searchParams.set("page", "0");
  url.searchParams.set("size", String(state.size));
  url.searchParams.set("sort", state.sort);

  if (state.projection) {
    url.searchParams.set("projection", state.projection);
  }

  return url.toString();
}
~~~

This is the query initialization URL. After the first response, use HAL hrefs for pagination steps. If the API uses a search resource, keep the search path and query criteria; do not fall back to the collection root and accidentally drop filters.

## 5. Projections: choosing the right representation for each screen

Projections allow clients to request a selective view. Example:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
~~~

The client can request:

~~~http
GET /api/people?projection=personSummary&page=0&size=20
Accept: application/hal+json
~~~

The projection value must match the annotation's name attribute, not necessarily the interface name. Projections can reduce the number of fields returned for list screens.

### Projections must be published by the server

Clients cannot arbitrarily request a Java interface simply by knowing its class name. The projection must be discovered by Spring Data REST under package rules or explicitly registered. Clients can discover metadata via profile/ALPS and use the exact published name.

If the server does not publish the requested projection, the request cannot produce the desired representation. The client must handle errors or fall back according to the defined API contract. Never treat projections as an authorization mechanism: the server must still enforce which fields a user is allowed to read.

### Choosing projections per screen

| Screen | Suggested projection | Needed data |
|---|---|---|
| Person list | personSummary | Name and short identifying fields. |
| Person detail | personDetail | Detailed fields permitted for reading. |
| Admin list | personAdminView | Administrative fields the user is authorized to view. |
| Person picker in form | personOption | ID, display name, and searchable value. |

Avoid using one oversized projection for every screen. Choose representations based on actual read requirements while enforcing read permissions on the server.

## 6. Combining pagination and projections

Pagination and projections can appear together in a query:

~~~http
GET /api/people?page=0&size=20&sort=lastName,asc&projection=personSummary
Accept: application/hal+json
~~~

When navigating, hrefs returned by the server should preserve projection, sort, and page size. The client does not need to append projection to the next link if the server already includes that parameter in the href.

When the user switches projections, treat it as a new query and typically reset to page 0. The representation may change fields or associations; old page state should not be assumed to remain valid.

Keep the current projection in query state so the UI displays the active selection, but after each response inspect the self href and metadata to know what query the server actually executed.

## 7. Loading, success, empty, and error states

The request lifecycle can be modeled as:

~~~text
idle
  |
  | user opens page or changes query
  v
loading
  |
  +---- response with items ------> success
  |
  +---- response without items --> empty
  |
  +---- HTTP/network failure ----> error
~~~

Sample state:

~~~javascript
const state = {
  status: "idle",
  items: [],
  page: null,
  navigation: null,
  error: null
};
~~~

Meaning of each state:

- Loading: waiting for response. Navigation buttons can be disabled to prevent duplicate requests.
- Success: received valid items and metadata.
- Empty: request succeeded but no matching items exist.
- Error: request failed; retain enough context for the user to retry or adjust the query.
- Stale: showing previous data while refreshing or after a mutation that may affect the collection.

Do not display an empty state before the request completes. Initializing items as an empty array and rendering "No data" prior to receiving the response misleads users during loading.

## 8. Preventing stale responses from overwriting newer queries

A common bug when users change filters rapidly:

1. Request A loads status ACTIVE.
2. User switches to INACTIVE and request B is sent.
3. B finishes before A.
4. A finishes later and overwrites the UI with ACTIVE data.

Use AbortController to cancel outdated requests:

~~~javascript
let activeController;

async function loadQuery(url, onSuccess, onError) {
  activeController?.abort();

  const controller = new AbortController();
  activeController = controller;

  try {
    const hal = await fetchHal(url, controller.signal);
    if (controller.signal.aborted) return;
    onSuccess(hal);
  } catch (error) {
    if (error.name === "AbortError") return;
    onError(error);
  }
}
~~~

Another approach is tracking a request sequence number and accepting a response only if its request ID is still the latest. Both techniques can be combined.

When query state changes, clear or mark old navigation links as stale. Do not let users click Next from an old response while a new query is loading.

## 9. Syncing query state with the browser URL

If the user refreshes or shares a URL, the UI should restore the necessary filter, sort, page size, and projection.

Example updating the UI page's query string:

~~~javascript
function writeUiStateToUrl(state) {
  const url = new URL(window.location.href);
  url.searchParams.set("status", state.status);
  url.searchParams.set("sort", state.sort);
  url.searchParams.set("size", String(state.size));

  if (state.projection) {
    url.searchParams.set("projection", state.projection);
  } else {
    url.searchParams.delete("projection");
  }

  window.history.replaceState({}, "", url);
}
~~~

On application startup, read the query string to restore state. When the user clicks Back/Forward, listen for popstate and reload the corresponding query.

Distinguish the UI page URL from API hrefs. The UI URL stores view state; HAL hrefs are server-published URIs for calling the API. Never treat these two URLs as the same.

## 10. Selection and item action state

A list may preserve selection across page changes or projection switches. Decide explicitly whether selection:

- Belongs only to the current page.
- Persists across pages.
- Persists under the current filter.
- Clears when the query context changes.

When allowing multi-page selection, store stable IDs rather than full response objects. Representations can change when projections change or when the server refreshes data.

~~~javascript
const selectedIds = new Set();

function toggleSelection(id) {
  if (selectedIds.has(id)) {
    selectedIds.delete(id);
  } else {
    selectedIds.add(id);
  }
}
~~~

When executing bulk actions, the server must still verify permissions for every ID. Client-side UI selection does not prove the user is authorized to act on all selected items.

## 11. Refreshing data after write operations

After creating, editing, or deleting an item, the current collection may no longer be accurate:

- A newly created item may belong on the first page under the current sort.
- An edited item may no longer match the active filter.
- A deleted item may leave the last page invalid.
- Association changes may affect projections or search results.

You can update an item from the write response if the API contract returns enough data, then refresh the collection using the appropriate href. If the server returns Location or new links, use those URIs to load the resource.

After deleting the last item on the last page, you may need to navigate back to prev or first if updated metadata indicates the current page is no longer valid. Read links and metadata after refreshing rather than guessing from the previous item count.

### Optimistic updates

The UI may apply temporary updates for responsiveness, but must roll back if the request fails. For changes affecting sorting, filtering, or pagination, a server refresh is usually needed to avoid keeping items in the wrong position.

Do not present optimistic data as server-confirmed while the request is still pending. Indicate saving status and display errors if the server rejects the change.

## 12. Data shifting between paginated requests

Offset pagination can shift when records are inserted, deleted, or change sort keys between requests.

Example:

1. Client loads page 0, size 10.
2. A new record is inserted at the top of the list.
3. Client follows the next link to page 1.
4. An item may repeat or be skipped because record positions shifted.

HAL links preserve the query context and page position at the time the response was generated, but do not guarantee an immutable snapshot across multiple requests.

To mitigate this:

- Use deterministic sorting.
- If the sort key is not unique, add a unique key as a secondary tie-breaker when supported by the API.
- Refresh the collection after write operations that affect the result set.
- Account for the possibility that lists may change between fetches.
- For rapidly changing data or strict traversal consistency, consider cursor/keyset pagination if supported by the backend.

## 13. Updating the UI when the API returns errors

The UI should classify errors by HTTP status or error code:

| Error | Recommended UI behavior |
|---|---|
| 400 Bad Request | Display input/filter validation errors and keep the query editable. |
| 401 Unauthorized | Prompt for login or refresh the session. |
| 403 Forbidden | Show permission denied; hide or disable unauthorized actions. |
| 404 Not Found | Resource may have been deleted; refresh the collection or return to the list. |
| 409 Conflict | Inform the user data changed or the workflow is no longer valid; reload the resource. |
| 429 Too Many Requests | Reduce request rate and honor Retry-After if sent by the server. |
| 5xx | Show a system error message and allow controlled retries. |

If the response uses Problem Details, the client can read title, detail, status, and extension codes. Prefer machine-readable codes for UI logic; never match against localized message strings to branch behavior.

## 14. Example state reducer

The following code illustrates a simple state container for a collection:

~~~javascript
const initialState = {
  status: "idle",
  items: [],
  page: null,
  navigation: null,
  error: null
};

function reducer(state, action) {
  switch (action.type) {
    case "LOAD_START":
      return {
        ...state,
        status: "loading",
        error: null
      };

    case "LOAD_SUCCESS":
      return {
        status: action.items.length ? "success" : "empty",
        items: action.items,
        page: action.page,
        navigation: action.navigation,
        error: null
      };

    case "LOAD_ERROR":
      return {
        ...state,
        status: "error",
        error: action.error
      };

    case "CLEAR":
      return initialState;

    default:
      return state;
  }
}
~~~

When a response arrives, dispatch a single action carrying items, page metadata, and navigation links. That ensures the UI never ends up with updated items while the Next button still points to the previous query.

If you want to keep previous items visible while refreshing, add an isRefreshing flag and mark data as stale. Do not use status success to mask that a new request is still running.

## 15. Implementation workflow

1. Discover collection relations and search resources from the API root/profile.
2. Identify the _embedded relation and actual page metadata structure.
3. Discover published projections and use exact annotation or ALPS names.
4. Separate query state from data, navigation, and request state.
5. Build the initialization URL for filter, sort, page size, and projection.
6. After responses, store first/prev/self/next/last hrefs and follow them to navigate.
7. When filter, sort, size, or projection changes, start a new query and usually reset to page 0.
8. Cancel or discard stale responses to prevent race conditions.
9. Sync query state with the UI URL if refresh and Back/Forward support are needed.
10. Update selection according to an explicit policy.
11. Refresh the collection after write operations that may affect membership, ordering, or page counts.
12. Handle loading, empty, error, stale, and conflict states independently.
13. Test against real HAL responses from the active Spring Data REST version.

## 16. Common mistakes

1. **Calculating next page manually and building URLs.** Risks dropping sort, filter, projection, or query parameters.
2. **Assuming embedded relation names are always fixed.** Read the actual relation published by the server.
3. **Assuming every response includes page metadata.** Unpaged endpoints may omit the page object.
4. **Confusing API page index with UI page number.** APIs are typically 0-based while UIs display 1-based numbers.
5. **Changing filters while keeping the old page index.** The new result set may have fewer pages; restart from the first page.
6. **Using the interface name instead of the projection name.** Clients must send the annotation's name value.
7. **Assuming any projection can be requested arbitrarily.** The server must discover or register the projection.
8. **Using projections for authorization.** Projections do not replace data-read permissions.
9. **Showing empty state while the request is still loading.** Declare empty only after a successful response.
10. **Old responses overwriting newer queries.** Use AbortController or request sequence tracking.
11. **Keeping stale navigation links when query changes.** Clear or mark links stale before fetching new results.
12. **Not refreshing after writes.** Items can change position, drop out of filters, or alter page counts.
13. **Storing full objects for selection.** Use stable IDs and verify permissions on the server.
14. **Treating optimistic updates as persisted data.** Roll back whenever the server rejects the change.
15. **Assuming pagination is a snapshot.** Offset pagination can duplicate or skip items when data mutates.
16. **Handling all HTTP errors with one message.** Distinguish 401, 403, 404, 409, 429, and 5xx.
17. **Using message text to drive UI logic.** Use stable error codes.
18. **Skipping tests for refresh or Back/Forward URLs.** Restore query state from the UI URL and reload the API with the right context.

## 17. Implementation checklist

- Read the correct collection relation and _embedded key.
- Read page metadata and handle unpaged responses.
- Store navigation hrefs from _links.
- Use server-provided hrefs for first/prev/next/last.
- Preserve filter, sort, size, and projection across pages.
- Reset to the first page when query context changes.
- Use server-published projection names.
- Never use projections as a substitute for authorization.
- Separate query, navigation, data, and request state.
- Handle loading, empty, error, and stale states distinctly.
- Prevent stale responses from overwriting newer queries.
- Define whether selection persists across pages or filters.
- Refresh collections after writes that affect results.
- Handle conflicts and data shifts between requests.
- Sync the UI URL if refresh or Back/Forward is required.
- Test API responses and UI states across edge cases.

## Summary

A Spring Data REST client should manage pagination, projections, and UI state as related yet independent concerns. Page metadata indicates position and counts; HAL links determine navigation; projections select the requested representation; query state holds the active filter, sort, page size, and projection.

Follow server-returned hrefs, reset pages when query context changes, prevent stale responses from overwriting fresh data, and represent loading/empty/error/stale states clearly. After writes, refresh the collection whenever membership, sort order, or page count may have changed. With offset pagination, data can shift between requests; metadata and links do not guarantee an immutable snapshot.

## References

- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring HATEOAS — HAL Support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [MDN — Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API)
- [MDN — AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
