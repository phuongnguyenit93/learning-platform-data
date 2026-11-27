# Pagination Metadata: number, size, totalElements, and totalPages

When a Spring Data REST endpoint returns a paginated list, the response typically includes a metadata block named `page`. The four fields `number`, `size`, `totalElements`, and `totalPages` describe the current page position, the page size, and the scale of the entire query result.

Reading these fields accurately helps clients display pagination controls, record counts, and last-page state without guessing from the number of visible elements.

## 1. Where Is Metadata Located in the Response?

Spring Data REST uses HAL by default for REST resources. For a paginated repository resource, the response has the following general form:

~~~http
GET /people?page=1&size=25
Accept: application/hal+json
~~~

~~~json
{
  "_embedded": {
    "people": [
      { "id": 26, "firstName": "An", "lastName": "Nguyen" },
      { "id": 27, "firstName": "Binh", "lastName": "Tran" }
    ]
  },
  "_links": {
    "first": { "href": "http://localhost:8080/people?page=0&size=25" },
    "prev": { "href": "http://localhost:8080/people?page=0&size=25" },
    "self": { "href": "http://localhost:8080/people?page=1&size=25" },
    "next": { "href": "http://localhost:8080/people?page=2&size=25" },
    "last": { "href": "http://localhost:8080/people?page=3&size=25" }
  },
  "page": {
    "size": 25,
    "totalElements": 82,
    "totalPages": 4,
    "number": 1
  }
}
~~~

In this response:

- `_embedded` holds the elements of the current page. Relation names like `people` depend on the resource name and application configuration.
- `_links` provides navigation links. Some links only appear when the corresponding action makes sense.
- `page` holds the pagination metadata.

The example above only illustrates the structure. Actual collection relation names, URLs, links, and numbers depend on the endpoint, data, configuration, and application version.

## 2. Meaning of the Four Fields

| Field | Meaning | Client Usage |
|---|---|---|
| `number` | Current page number, starting from 0 | Determine the position of the page being viewed |
| `size` | Applied page size, i.e., maximum expected elements on a page | Display page size selection and compute record ranges |
| `totalElements` | Total elements matching the query across all pages | Display total result count |
| `totalPages` | Total pages calculated from total elements and page size | Determine page count and last-page state |

### number — current page, starting from 0

`number` is the current page index using a zero-based system.

- The first page has `number = 0`.
- The second page has `number = 1`.
- The third page has `number = 2`.

This is a common source of bugs when communicating between an API and a UI. Users typically see pages 1, 2, 3, while the API accepts and returns indices 0, 1, 2.

For example, if the UI displays page numbers starting from 1:

~~~javascript
const displayPageNumber = page.number + 1;
~~~

When sending a request to the API, use the zero-based index expected by the API. Do not send the user-facing page number directly without subtracting 1.

### size — applied page size

`size` indicates the maximum number of elements a page is allowed to hold under the current pagination configuration. It does not necessarily equal the actual number of elements in the `_embedded` array.

For example:

- `size = 25` means each page can hold at most 25 elements.
- The first and middle pages usually have 25 elements if enough data remains.
- The last page might contain only 7 elements, yet the metadata still has `size = 25`.

Therefore, do not use the length of the content array to infer `size`. In particular, when the last page has fewer elements, the page size remains unchanged.

Clients can request a page size via the `size` query parameter, but the server may apply a default value or enforce a maximum size limit. Read `page.size` in the response to know the actual size that was applied.

### totalElements — total elements matching the query

`totalElements` is the total number of records matching the query condition across the entire result set, not just the number of elements on the current page.

Suppose the API returns a page with 25 elements and:

~~~json
{
  "page": {
    "size": 25,
    "totalElements": 82,
    "totalPages": 4,
    "number": 1
  }
}
~~~

The client is viewing the second page, while the total number of matching results is 82. The number 25 is the content limit of one page, whereas 82 is the count across all pages.

If the request has a filter, `totalElements` reflects the count after applying that filter. It does not necessarily equal the total number of rows in the entire database table.

### totalPages — total number of pages

When the page size is greater than 0, the number of pages is calculated by the formula:

~~~text
totalPages = ceil(totalElements / size)
~~~

Where `ceil` is the ceiling rounding operation.

Example with `size = 25`:

| totalElements | totalPages | Interpretation |
|---:|---:|---|
| 0 | 0 | No results |
| 1 | 1 | One page with 1 element |
| 25 | 1 | One full page of 25 elements |
| 26 | 2 | Second page has 1 element |
| 50 | 2 | Two full pages of 25 elements |
| 82 | 4 | Three full pages of 25 elements and a last page with 7 elements |

With an empty result and a valid page size greater than 0, `totalPages` equals 0. Do not force it to 1 to display a populated page state; the UI can display “No results”.

## 3. Example Calculating Each Page's Data

Suppose the API returns:

~~~json
{
  "page": {
    "size": 10,
    "totalElements": 23,
    "totalPages": 3,
    "number": 1
  }
}
~~~

The current page is the second page for the user because `number` starts from 0.

If pages are numbered sequentially and the data is stable, the record position range for this page is:

- Starting position: `number * size + 1 = 11`.
- Ending position: `min((number + 1) * size, totalElements) = 20`.

The pages have the following ranges:

| number from API | Displayed Page | Record Positions | Max Elements |
|---:|---:|---:|---:|
| 0 | 1 | 1–10 | 10 |
| 1 | 2 | 11–20 | 10 |
| 2 | 3 | 21–23 | 10 |

This range formula is useful for a UI displaying “11–20 of 23 results”. Only calculate it when there are results and valid metadata; for an empty page or an out-of-range page index, display an appropriate empty state instead of producing a non-existent record range.

## 4. Sending Pagination and Sorting Requests

Spring Data REST commonly uses these query parameters:

- `page`: page index, starting from 0.
- `size`: maximum elements per page.
- `sort`: sort property and sort direction.

Example fetching the second page, 25 elements per page, sorted by last name ascending:

~~~http
GET /people?page=1&size=25&sort=lastName,asc
Accept: application/hal+json
~~~

You can pass multiple sort criteria by repeating `sort`:

~~~http
GET /people?page=0&size=10&sort=lastName,asc&sort=firstName,asc
~~~

Sort order affects the order of elements within a page. When filters or query conditions change, `totalElements` and `totalPages` can also change. When only the sort order changes, the total number of results usually stays the same.

Default query parameter names can be configured in Spring Data REST. If the application renames parameters, clients must use the configured names rather than assuming they are always `page`, `size`, and `sort`.

## 5. Using HAL Links for Navigation

Metadata tells you the page state; HAL links tell you where the client can go next.

Common relations:

- `first`: link to the first page.
- `prev`: link to the previous page, if available.
- `self`: link to the current resource/page.
- `next`: link to the next page, if available.
- `last`: link to the last page.

On the first page, `prev` is usually absent. On the last page, `next` is usually absent. With an empty dataset, navigation links may differ from a dataset with multiple pages.

Prefer reading the links returned by the server rather than concatenating URLs or incrementing/decrementing query parameters manually. Links can preserve filters, sorts, and other parameters that the client needs to keep. This approach also reduces coupling to the endpoint's internal URL structure.

HAL-oriented handling example:

~~~javascript
const page = response.page;
const links = response._links ?? {};

const canGoPrevious = Boolean(links.prev);
const canGoNext = Boolean(links.next);

const currentPageForDisplay = page.number + 1;
const totalPages = page.totalPages;
const totalElements = page.totalElements;
~~~

When the user selects the next page, the client follows `_links.next.href` if the link exists. Do not issue a next-page request when the link is not provided.

## 6. Impact of Filters, Sorts, and Data Changes

Metadata reflects the result of the current request. Therefore, clients must refresh metadata when query conditions change.

**When a filter changes**

For example, searching for all users with status ACTIVE, then changing the filter to INACTIVE. `totalElements` and `totalPages` must be re-read from the new response. The current page may no longer be valid for the new result set; normally, you should return to the first page when the filter changes.

**When sort changes**

The order of elements can change, so the client should send a new request and use the content and links from the new response. With data that can be updated concurrently, an element may shift across pages after re-sorting.

**When data is added or deleted**

`totalElements` and `totalPages` can change between two requests. If a record is deleted on the last page, that page may no longer have enough data or may no longer exist. Clients should process the new response and HAL links instead of caching a hardcoded total page count from an older response.

**When data changes while a user is paging**

Offset/page pagination is not an immutable snapshot. If records are inserted or deleted before the current offset position, elements between two requests may be duplicated or skipped. For continuously changing data requiring stable traversal, consider cursor/keyset pagination design at the appropriate API layer; this cannot be solved by these four metadata fields alone.

## 7. Distinguishing Page from Slice

In Spring Data, `Page<T>` and `Slice<T>` serve two different needs:

- `Page<T>` provides information about the total number of elements and total number of pages. Therefore, it is suitable when the UI needs to display total results and page counts.
- `Slice<T>` focuses on knowing whether more data exists ahead, typically via `hasNext()`. It does not require knowing the total elements or total pages.

To supply `totalElements` and `totalPages`, the query layer typically needs count information for the total results. With large datasets, a count query can incur significant cost. Choose the result type suited to UI and performance requirements; if you only need a “Load more” button, querying the total page count is not strictly necessary.

The exact representation of a Spring Data REST endpoint depends on the return type and resource configuration. Do not assume every collection response contains all four of these fields.

## 8. Configuring Page Size

Spring Data REST has a default page size and a maximum limit. A Spring Boot application can configure these values in `application.yml`:

~~~yaml
spring:
  data:
    rest:
      default-page-size: 20
      max-page-size: 100
~~~

In this example:

- If the client does not send `size`, the server uses the default size of 20.
- If the client requests a size larger than the limit, the server applies the configured cap.
- The `page.size` value in the response is what you should use to understand the actual applied page size.

Clients should not be allowed to request arbitrarily huge page sizes. Overly large pages increase network payload size, memory needed to process the response, and database query cost.

Exact property names and configuration capabilities should be verified against the Spring Boot / Spring Data REST version used by the project.

## 9. Example Defining Client-Side Data Types

You can define a metadata type so the client uses it consistently:

~~~typescript
interface PageMetadata {
  number: number;
  size: number;
  totalElements: number;
  totalPages: number;
}
~~~

Example helper function for display information:

~~~typescript
function getPageSummary(page: PageMetadata) {
  if (page.totalElements === 0) {
    return {
      currentPage: 0,
      totalPages: 0,
      totalElements: 0,
      start: 0,
      end: 0
    };
  }

  const currentPage = page.number + 1;
  const start = page.number * page.size + 1;
  const end = Math.min((page.number + 1) * page.size, page.totalElements);

  return {
    currentPage,
    totalPages: page.totalPages,
    totalElements: page.totalElements,
    start,
    end
  };
}
~~~

The data type above describes the numeric fields in metadata. If the client needs HAL navigation, also read `_links` and check the existence of each relation before displaying or enabling navigation buttons.

## 10. Common Mistakes

| Mistake | Cause | Solution |
|---|---|---|
| UI displays page 0 | Using `number` directly as the user-facing page number | Display `number + 1` |
| Last page shows wrong page size | Treating actual element count as `size` | Use `page.size` |
| Total results equal current page element count | Reading `_embedded` array length instead of total results | Use `page.totalElements` |
| Off-by-one missing the last page | Using integer floor division | Use `totalPages` metadata or ceiling division |
| No data yet still displays page 1/1 | Clamping `totalPages` to at least 1 | Handle the `totalElements = 0` case separately |
| Switching pages drops filter or sort | Building a new URL and omitting old query parameters | Follow the HAL links returned by the server |
| Stale metadata after changing filter | Not fetching or reading the new response | Send a new request and update both content and metadata |
| Total page count changes between loads | Data added/deleted or query conditions changed | Use the latest metadata and handle pages that are no longer valid |

## 11. Checklist When Reading Paginated Responses

1. Confirm the endpoint actually returns paginated results and includes the `page` block.
2. Read `number` as zero-based; add 1 when displaying to users.
3. Use `size` from metadata rather than inferring it from the actual element count.
4. Use `totalElements` to display the total results after filtering.
5. Use `totalPages` to determine the page count; handle empty datasets separately.
6. Rely on `_links.prev`, `_links.next`, `_links.first`, and `_links.last` for navigation.
7. Reload content and metadata when filters or sorts change.
8. Do not retain an old total page count after data may have changed.
9. Consider the cost of count queries if the API does not genuinely need total elements.
10. Test the first page, middle pages, last page, empty pages, and out-of-range page index requests.

When these four metadata fields are understood correctly, the client can accurately display the current page position, page size, total results, and total pages. Combining metadata with HAL links keeps navigation aligned with what the server actually provides.
