# The `page`, `size` Parameters and the 0-Based Page Index Convention

## Objectives

After finishing this lesson, you will be able to:

- Call a Spring Data REST collection endpoint using the `page` and `size` parameters.
- Identify the first page, next page, and last page according to the 0-based numbering convention.
- Correctly read pagination information in the response, especially `page.number` and `page.totalPages`.
- Avoid off-by-one page errors when connecting a user interface to the API.

## 1. What Do the Two Parameters Mean?

Spring Data REST supports pagination for collection resources. With the default configuration, clients pass pagination information through the query string:

- **`page`**: the index of the page to retrieve. This is a **0-based** index.
- **`size`**: the maximum number of elements the client wants to receive in a single page.

Example:

~~~http
GET /people?page=0&size=20
~~~

The request above asks for the first page of the `people` collection, with up to 20 elements.

Convention to remember:

| `page` Value | Requested Page | Meaning |
|---:|---|---|
| `0` | First page | Starts from the first element |
| `1` | Second page | Skips the first page |
| `2` | Third page | Skips the first two pages |
| `3` | Fourth page | Skips the first three pages |

Therefore, **`page=0` is the first page**. If you send `page=1`, the API returns the second page, not the first page.

`size` is not the total number of records in the collection. It is only the limit on the number of elements returned in a single response. For example, `size=10` means each page has at most 10 elements; a collection with 95 elements still requires multiple requests to read completely.

## 2. Understanding the Data Position of Each Page

You can visualize the starting position of a page using the formula:

**Starting position (offset) = `page × size`**

Example with `size=10`:

| Request | Offset | 1-Based Element Positions |
|---|---:|---|
| `page=0&size=10` | 0 | 1–10 |
| `page=1&size=10` | 10 | 11–20 |
| `page=2&size=10` | 20 | 21–30 |
| `page=3&size=10` | 30 | 31–40 |

Offset is the 0-based starting position in technical representation. Clients **do not pass the offset into the `page` parameter**. For example, to fetch the group of elements from position 21 to 30 in normal counting, send `page=2&size=10`, not `page=20`.

## 3. Default Values and Limits

If the client omits `page`, Spring Data typically interprets it as page index 0. If `size` is omitted, the server uses the configured default page size. Spring Data REST usually has a default page size of 20, though the application can change this value.

The server can also set a maximum page size limit. Therefore:

- Explicitly send `page` and `size` when the client needs predictable results.
- Use a non-negative integer for `page` and a positive integer for `size`.
- Do not assume the server accepts every `size` value the client sends.
- When you need to know the actual applied value, read the pagination metadata in the response.

The parameter names `page` and `size` are the common defaults in Spring Data REST. Applications can configure different parameter names or page sizes, so clients should follow the API contract published by the server.

## 4. Reading Pagination Metadata in the Response

A Spring Data REST HAL response usually has three notable sections:

- `_embedded`: contains the elements of the collection on the current page.
- `_links`: contains navigation links such as `first`, `prev`, `self`, `next`, and `last` when applicable.
- `page`: contains an overview of pagination details.

Illustrative example: a collection has 12 people, with up to 5 people per page. The response to `GET /people?page=1&size=5` may have the following structure:

~~~json
{
  "_embedded": {
    "people": [
      { "name": "Person 6" },
      { "name": "Person 7" },
      { "name": "Person 8" },
      { "name": "Person 9" },
      { "name": "Person 10" }
    ]
  },
  "_links": {
    "first": { "href": "/people?page=0&size=5" },
    "prev": { "href": "/people?page=0&size=5" },
    "self": { "href": "/people?page=1&size=5" },
    "next": { "href": "/people?page=2&size=5" },
    "last": { "href": "/people?page=2&size=5" }
  },
  "page": {
    "size": 5,
    "totalElements": 12,
    "totalPages": 3,
    "number": 1
  }
}
~~~

Meaning of the fields inside `page`:

| Field | Meaning |
|---|---|
| `size` | Applied page size |
| `totalElements` | Total number of elements across the entire result set |
| `totalPages` | Total number of pages |
| `number` | 0-based index of the current page |

In the example, `number=1` means the response is on the **second page**. `totalPages=3` means there are three pages, with valid indices 0, 1, and 2 respectively. Do not use `totalPages` as the index of the last page; the last page index is `totalPages - 1` when there is at least one page.

The last page may contain fewer elements than `size`. With 12 elements and `size=5`, the three pages contain 5, 5, and 2 elements respectively. That does not mean the page size has changed.

## 5. Calling the API Page by Page

Suppose a repository is exposed at the `/people` endpoint and the server allows 5 elements per page:

~~~http
GET /people?page=0&size=5
GET /people?page=1&size=5
GET /people?page=2&size=5
~~~

If there are 12 elements in total:

- The first request receives up to the first 5 elements.
- The second request receives up to the next 5 elements.
- The third request receives the remaining 2 elements.

You can change `size` without changing the convention for `page`. For example, `page=0&size=10` retrieves up to the first 10 elements; `page=1&size=10` retrieves up to the next 10 elements.

When the response provides navigation links in `_links`, prefer using those links. They help the client preserve the parameters the server has applied, including sorting or filtering parameters if the API uses them.

## 6. Connecting to a User Interface

Many UI libraries display page numbers starting from 1 so they are intuitive for users, whereas Spring Data uses 0-based indices. When integrating, convert explicitly:

- UI is on page 1 → send `page=0`.
- UI is on page 2 → send `page=1`.
- Response has `page.number=1` → display page 2 on the UI.

The conversion rules can be expressed as follows:

~~~text
apiPage = uiPage - 1
uiPage  = apiPage + 1
~~~

A few notes when managing pagination state on the client:

1. Initialize the API page at index 0.
2. Keep `page` and `size` in screen state so the exact page can be reloaded.
3. When the user changes `size`, usually reset `page` to 0. The currently selected page may no longer be valid with the new size.
4. When changing filters shrinks the result set, re-check metadata and return the user to a valid page if the current page exceeds the last page.
5. When building URLs manually, preserve the required sort and filter parameters. If the API already returns `_links`, prefer using those URLs.

## 7. Common Mistakes

**Sending `page=1` to fetch the first page**

This is a common off-by-one error. Under the 0-based convention, `page=1` is the second page. Start with `page=0`.

**Confusing `page` with offset**

With `size=20`, the third page has `page=2`, not `page=40`. Offset is calculated from `page × size`; it is not the value to send in the `page` parameter.

**Confusing `totalPages` with the last page index**

If `totalPages=3`, the pages have indices 0, 1, 2. The last page has index 2.

**Treating `size` as the total number of records**

`size=10` only limits the number of elements on one page. It does not ask the server to find only 10 records in the entire collection.

**Treating `page.number` as a 1-based page number**

In Spring Data metadata, `number` also uses a 0-based index. When using it directly in the UI, add 1 to display it to the user.

**Requesting an out-of-range page**

If the client sends a page index greater than the last page, the result may be empty. Rely on `totalPages` and the navigation links in the response to control page transitions.

## 8. Self-Check Exercise

An endpoint returns a total of 23 records. The client sends `size=10`.

1. Which request retrieves the first 10 records?
2. Which request retrieves records 11 through 20?
3. What is the `page` index of the last page?
4. What does `totalPages` equal?
5. If the UI is displaying page number 3, what `page` value should the client send?

**Answers:**

1. `page=0&size=10`.
2. `page=1&size=10`.
3. The last page index is 2.
4. `totalPages=3`.
5. Send `page=2`, because the UI numbers from 1 while the API numbers from 0.

## Key Takeaways

- `page` is the page index, starting from **0**.
- `size` is the maximum number of elements in a single page.
- A page's starting position is calculated as `page × size`.
- `page.number` in metadata is also a 0-based index.
- `totalPages` is the number of pages; the last page index is `totalPages - 1` when the result has pages.
- Prefer the navigation links returned by Spring Data REST to follow the API contract properly.

Reference: [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html).
