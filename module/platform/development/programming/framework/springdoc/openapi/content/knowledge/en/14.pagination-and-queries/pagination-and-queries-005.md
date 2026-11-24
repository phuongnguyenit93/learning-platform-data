# Multiple Sort Criteria and Repeated `sort` Parameters

A list API often needs to sort by multiple criteria at once. For example, a list of books might be sorted by creation date descending, then by title ascending so records from the same day have a stable order. Spring Data supports passing multiple `sort` values in the query string; Springdoc can document `sort` as a query parameter array in OpenAPI so integrators know to repeat the parameter name.

Typical request:

```http
GET /api/books?page=0&size=20&sort=createdAt,desc&sort=title,asc HTTP/1.1
Accept: application/json
```

Each occurrence of `sort` represents one criterion. The order of criteria matters: the server prioritizes `createdAt DESC`, then uses `title ASC` to sort records sharing the same creation timestamp.

## 1. Spring Data's Multi-Criteria Syntax

Spring Data Web supports the `sort` query parameter when binding a request to `Sort` or `Pageable`. Each value typically has the form:

```text
property,direction
```

Where:

- `property` is a sortable property of the entity or a property supported by the repository.
- `direction` is `asc` or `desc`.
- If direction is omitted, Spring Data defaults to `ASC`.

Examples:

| Query string | Meaning |
| --- | --- |
| `?sort=title` | Sort by `title ASC` |
| `?sort=createdAt,desc` | Sort by `createdAt DESC` |
| `?sort=createdAt,desc&sort=title,asc` | Prioritize `createdAt DESC`, then `title ASC` |
| `?sort=category,asc&sort=price,desc&sort=id,asc` | Sort by three criteria in the exact order provided |

With multiple criteria having different directions, the clearest approach is repeating the `sort` parameter, one value per property. Avoid packing multiple property/direction pairs into an arbitrary single string because comma parsing can become ambiguous.

## 2. Why Repeat the Same Query Parameter Name?

A URL can contain multiple key/value pairs with the same name:

```text
/api/books?sort=createdAt,desc&sort=title,asc
```

This is the standard encoding for an array query parameter. In OpenAPI 3, a query parameter can be declared as an array with `style: form` and `explode: true`:

```yaml
name: sort
in: query
required: false
style: form
explode: true
schema:
  type: array
  items:
    type: string
  example:
    - createdAt,desc
    - title,asc
```

`style: form` defines how the query parameter is serialized; `explode: true` specifies that each item is represented as a separate query parameter pair. Therefore, two elements produce `sort=createdAt,desc&sort=title,asc`.

If `explode: false` is used, array items are typically joined within a single parameter by commas. That produces a different representation and may not match the repeated `sort` syntax expected by the Spring Data resolver. With Spring Data `Pageable`, use the repeated `sort` form and verify the OpenAPI spec states `style: form`, `explode: true`.

## 3. Receiving Multiple Criteria with `Pageable`

In a Spring MVC application using Spring Data, the convenient approach is accepting `Pageable`. Spring Data Web automatically reads the pagination and sorting parameters:

- `page`: page index, starting from `0` by default.
- `size`: number of records per page.
- `sort`: one or more sorting criteria.

Example controller:

```java
package com.example.books;

import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.web.SortDefault;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping
    public Page<BookResponse> list(
            @ParameterObject
            @PageableDefault(size = 20)
            @SortDefault.SortDefaults({
                @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
                @SortDefault(sort = "id", direction = Sort.Direction.ASC)
            })
            Pageable pageable) {

        return bookService.findAll(pageable);
    }
}
```

Springdoc's `@ParameterObject` flattens `Pageable` into query parameters for OpenAPI documentation. In this example, `@PageableDefault(size = 20)` sets the default page size; `@SortDefault.SortDefaults` supplies two default criteria in the declared order when the client does not send custom sorting.

The example uses Spring Boot 3 and Springdoc 2.x. With Springdoc 1.x, packages for some Springdoc annotations may differ. Use imports matching your project's library version.

## 4. Sending Repeated Sort Parameters When Calling the API

Calling the endpoint with curl:

```bash
curl -G "http://localhost:8080/api/books" \
  --data-urlencode "page=0" \
  --data-urlencode "size=20" \
  --data-urlencode "sort=createdAt,desc" \
  --data-urlencode "sort=title,asc"
```

`curl -G` puts `--data-urlencode` values into the query string. Two `sort` options produce two key/value pairs with the same name. You can inspect the equivalent URL:

```text
http://localhost:8080/api/books?page=0&size=20&sort=createdAt%2Cdesc&sort=title%2Casc
```

Commas are URL-encoded as `%2C` in the example above. The server decodes query parameters before Spring Data parses the values.

## 5. Describing `sort` in OpenAPI with Array and Explode

Springdoc supports `Pageable` via `@ParameterObject` and generates `page`, `size`, and `sort` parameters. After generating the documentation, inspect `/v3/api-docs` to confirm `sort` is accurately represented as an array of strings with proper serialization.

If you need to explicitly declare parameter repetition in the contract, you can describe `sort` using `@Parameter`:

```java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.Explode;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.enums.ParameterStyle;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "List books",
    parameters = @Parameter(
        name = "sort",
        in = ParameterIn.QUERY,
        description = "Can be repeated to specify multiple criteria in priority order",
        style = ParameterStyle.FORM,
        explode = Explode.TRUE,
        array = @ArraySchema(
            schema = @Schema(
                type = "string",
                example = "createdAt,desc"
            )
        )
    )
)
```

Place this metadata on an operation accepting `Pageable`. If Springdoc already generates `sort`, inspect the output to avoid creating two parameters with the same name and location. When an already-generated parameter needs adjustment, use `OpenApiCustomizer` to update the existing parameter instead of adding a duplicate.

The annotations above only describe serialization in OpenAPI. They do not alter how Spring Data parses requests; the controller must still accept `Pageable` or an appropriate data structure.

## 6. Expected OpenAPI Structure

The `sort` parameter in the specification can look like:

```yaml
parameters:
  - name: sort
    in: query
    description: Can be repeated to specify multiple criteria in priority order
    required: false
    style: form
    explode: true
    schema:
      type: array
      items:
        type: string
      example:
        - createdAt,desc
        - title,asc
```

Swagger UI may render an array parameter as multiple input fields or an expandable list field, depending on the UI version. What matters is that client generators and HTTP tools serialize the array into repeated `sort` keys.

When inspecting `/v3/api-docs`, verify:

1. `name` is `sort` and `in` is `query`.
2. `schema.type` is `array` and `items.type` is `string`.
3. `style` is `form`.
4. `explode` is `true`.
5. Examples contain multiple items, each using `property,direction` syntax.

If documentation presents `sort` as a single string, integrators may misunderstand how to pass multiple criteria. In that case, adjust Springdoc metadata and re-check the URLs built by Swagger UI or client generators.

## 7. Multi-Criteria Default Sorting

Default order can be configured with `@SortDefault.SortDefaults`:

```java
@GetMapping
public Page<BookResponse> list(
        @ParameterObject
        @PageableDefault(size = 20)
        @SortDefault.SortDefaults({
            @SortDefault(sort = "createdAt", direction = Sort.Direction.DESC),
            @SortDefault(sort = "title", direction = Sort.Direction.ASC),
            @SortDefault(sort = "id", direction = Sort.Direction.ASC)
        })
        Pageable pageable) {
    return bookService.findAll(pageable);
}
```

When the client omits `sort`, the resolver uses the configured defaults. When the client passes custom criteria, Spring Data uses the request's sort values according to resolver behavior. Test both cases—without `sort` and with `sort`—to confirm the application's desired behavior.

`@PageableDefault(sort = ..., direction = ...)` can also be used for one or more properties sharing the same direction. When each criterion needs a different direction, `@SortDefault.SortDefaults` expresses it more clearly.

Do not confuse default sort with OpenAPI examples. `@SortDefault` affects how Spring Data constructs `Pageable` when a request lacks sort; examples in `@Parameter` merely illustrate requests clients can send.

## 8. Priority Order and Pagination Stability

Multi-criteria sorting is applied in sequence:

```sql
ORDER BY created_at DESC, title ASC, id ASC
```

The first criterion determines the primary order. If multiple records share the same value on that criterion, the next criterion breaks the tie. Therefore, include a sufficiently stable secondary criterion—typically a unique key like `id`—to make paginated results predictable.

If sorting only by `createdAt` when multiple records share the same timestamp, their relative order may be non-deterministic. As a client moves from one page to the next, records may appear duplicated or skipped if data changes between requests. Adding a unique key as the final criterion creates a more stable total order.

Stable sorting does not prevent every shift caused by new inserts or updates between two requests. For systems traversing continuously changing datasets, consider cursor/keyset pagination rather than relying solely on offset pagination.

## 9. Restricting Allowed Sort Properties

Clients should not be allowed to pass arbitrary internal entity property names. Some properties are meaningless to API consumers, unindexed, or unsuitable for sorting. With JPA repositories, a nonexistent property can trigger query construction errors.

Publish a list of allowed sort fields, for example:

| Public sort name | Underlying data property | Allowed directions |
| --- | --- | --- |
| `title` | `Book.title` | `asc`, `desc` |
| `createdAt` | `Book.createdAt` | `asc`, `desc` |
| `price` | `Book.price` | `asc`, `desc` |

If public names differ from entity property names, map from the allowlist to internal properties before calling the repository. Never concatenate client-supplied sort strings directly into SQL or JPQL statements. Avoid using `JpaSort.unsafe` with untrusted input.

With `Pageable`, you can validate `pageable.getSort()` before passing it down to the service/repository:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "title", "createdAt", "price", "id"
);

private void validateSort(Pageable pageable) {
    pageable.getSort().forEach(order -> {
        if (!ALLOWED_SORTS.contains(order.getProperty())) {
            throw new IllegalArgumentException(
                "Sorting is not supported by: " + order.getProperty()
            );
        }
    });
}
```

In a real application, translate this error into a `400 Bad Request` response with a consistent error code and message. OpenAPI documentation should describe supported properties in the description or use an enum if the list is stable enough and fits the parameter representation.

## 10. Limiting Page Size and Controlling Queries

Multi-criteria sorting typically accompanies pagination. Beyond controlling sort fields, the API must limit page size to prevent clients from requesting too many records in one call.

Default configuration example:

```java
@PageableDefault(size = 20)
Pageable pageable
```

This is a default size, not necessarily a maximum cap. Configure the page size limit on the resolver or validate `pageable.getPageSize()` in the appropriate layer. When the limit is exceeded, the API can reject the request or clamp to the maximum according to published policy.

Clearly document in OpenAPI:

- Whether `page` starts at `0` or `1`.
- Default `size` and maximum limit.
- Whether `sort` can be repeated.
- Supported sort fields.
- Default direction when clients supply only the property name.
- Default criteria when clients omit sort.

Ensure documentation reflects how the resolver is configured in the application, since parameter names, defaults, and limits can all be customized.

## 11. Testing Multi-Criteria Sorting

Test both how Spring binds the query string and the ordering of returned data.

Example request:

```bash
curl -G "http://localhost:8080/api/books" \
  --data-urlencode "sort=createdAt,desc" \
  --data-urlencode "sort=title,asc"
```

Verify these cases:

1. No `sort`: server applies default order.
2. One `sort`: server applies one criterion.
3. Multiple `sort`: server preserves exact priority order and each criterion's direction.
4. Property name only: server uses default `ASC` direction per resolver.
5. Invalid direction: API returns an understandable error.
6. Unsupported property: API rejects or handles per published policy.
7. Multiple records with same primary value: secondary criterion provides stable ordering.

In Spring MVC tests, MockMvc can send the same parameter name multiple times:

```java
mockMvc.perform(get("/api/books")
        .param("sort", "createdAt,desc")
        .param("sort", "title,asc"))
    .andExpect(status().isOk());
```

This test verifies a request with two `sort` values reaches the endpoint. Add assertions on the results or verify `Pageable` passed to the service has `createdAt DESC`, `title ASC`.

## 12. Common Issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Only the last sort criterion applies | Client or proxy overwrites duplicate query parameter keys | Send multiple `sort` keys and inspect `getSort()` |
| All criteria unexpectedly share one direction | Packed multiple properties into one string or relied on shared default direction | Repeat one `property,direction` value per criterion |
| Swagger UI sends only one sort value | OpenAPI describes `sort` as string or wrong `explode` | Describe array with `style: form`, `explode: true` |
| OpenAPI shows two `sort` parameters | Added explicit parameter while Springdoc already generated one from Pageable | Update existing parameter via customizer, avoid duplicates |
| Sort fails on desired property | Public name is not a valid entity/repository property | Map allowlist to underlying data property |
| Invalid sort direction returns confusing error | Direction value unvalidated or exception unhandled | Validate `asc`/`desc` and return consistent 400 error |
| Page results duplicate or omit records | Sort lacks unique tie-breaker or data mutated between calls | Add unique key as tie-breaker; consider keyset pagination |
| Default sort does not appear | `@SortDefault` misplaced or request already sent custom sort | Check bound `Pageable` and resolver configuration |

## 13. Checklist for Documenting Repeated Sort

- [ ] API accepts `Pageable` or a sort structure capable of handling multiple values.
- [ ] Each criterion uses `property,direction` syntax.
- [ ] Query string repeats the same `sort` name for each criterion.
- [ ] OpenAPI describes `sort` as a string array when repetition is supported.
- [ ] `style: form` and `explode: true` accurately reflect serialization.
- [ ] `@ParameterObject` is used so Springdoc recognizes `Pageable`.
- [ ] Default page size and sort are clearly documented.
- [ ] Sort properties are allowlisted and safely mapped.
- [ ] A unique secondary criterion stabilizes ordering across pages.
- [ ] Inspected `/v3/api-docs`, Swagger UI, and repeated curl/test requests.
- [ ] Invalid directions and properties are handled as consistent API errors.

Spring Data allows passing multiple criteria by repeating the `sort` query parameter. Springdoc must document this accurately as a query parameter array serialized with `form` style and `explode: true`. When the contract, resolver, and repository agree on property names, sort directions, and priority order, clients can combine multiple criteria while receiving predictable paginated results.
