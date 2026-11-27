# Optional Filters, Null Values, and Condition Combination Rules

A search API typically offers multiple filters that callers may omit: status, category, price range, brand, update time, and keywords. The challenge is not adding each clause into Query DSL, but deciding precisely **when a condition applies, when it is skipped, and when it means searching for missing or null values**.

If code only performs truthy/falsy checks, valid values like `false`, `0`, or empty strings may be mishandled. If every filter is added even when its value is null, the query might match documents missing the field instead of skipping the condition. If OR branches are combined without explicit logical grouping, results can be broader or narrower than expected.

This lesson explains how to design optional filters in Spring Data Elasticsearch, normalize inputs, handle null/empty values, combine AND/OR/NOT using bool queries, and test condition combinations. The guiding principle is: **business rules determine filter semantics; the query builder simply translates those semantics into Query DSL**.

## 1. What are optional filters?

Suppose a product search API supports:

~~~http
GET /api/products/search?q=keyboard&category=ACCESSORIES&minPrice=100000&maxPrice=2000000&status=PUBLISHED
~~~

Callers may pass only a subset of conditions:

~~~http
GET /api/products/search?category=ACCESSORIES
~~~

or:

~~~http
GET /api/products/search?q=keyboard
~~~

A filter is optional when omitting its value means the corresponding condition is not applied. For instance, if `category` is omitted, results can belong to any category the user is allowed to view.

However, "omitted" is not always the same as "passed null", "empty string", "empty list", or `false`. The API must define distinct semantics for each data type.

Filter requests should be interpreted according to a contract:

| Input | Possible chosen meaning | Handling |
|---|---|---|
| `category` omitted | Do not filter by category | Do not add clause |
| `category = ACCESSORIES` | Only this category | Add term filter |
| `minPrice` omitted | No lower price bound | Do not add lower bound |
| `minPrice = 0` | Price must be greater than or equal to 0 | Keep value 0 |
| `active = false` | Only inactive documents | Add term filter `false` |
| `brands` omitted | Do not filter brands | Do not add clause |
| `brands = []` | Per contract: no filter, no results, or invalid input | Choose explicitly |
| `status = null` | Per contract: no filter or find null/missing field | Do not guess |

Do not apply a blanket "skip if null/empty" rule across every input type without defining business meaning.

## 2. Designing Search Criteria independent of HTTP

Controllers should convert requests into strongly typed criteria. Criteria should not contain raw Query DSL or arbitrary client-supplied field names.

Example:

~~~java
public record ProductSearchCriteria(
        String tenantId,
        String text,
        String category,
        List<String> brands,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Boolean active,
        String status,
        Boolean hasDescription
) {
}
~~~

Separate criteria can be created from a request DTO after validation and normalization:

~~~java
public record ProductSearchRequest(
        String q,
        String category,
        List<String> brands,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Boolean active,
        String status,
        Boolean hasDescription
) {
}
~~~

Separating the two types helps ensure:

- The request DTO reflects the HTTP contract.
- Criteria express business intent.
- Tenant scope can be added from the authenticated principal.
- Defaults and empty/null rules are handled in one place.
- The query builder does not care whether requests arrived via query parameters or JSON body.

Never place a client-chosen `tenantId` into internal criteria unless the caller is authorized to choose tenants. The service should obtain the tenant from an authentication/authorization provider.

## 3. Distinguishing absent, null, blank, and empty

These four states are frequently conflated by mistake:

- **Absent**: the field does not appear in the request.
- **Null**: the field appears with JSON `null`, or a parameter binds to null.
- **Blank**: a string is present but empty or contains only whitespace.
- **Empty collection**: a list is present but contains zero elements.

Example JSON:

~~~json
{
  "category": null,
  "status": "",
  "brands": [],
  "active": false,
  "minPrice": 0
}
~~~

Some binding frameworks collapse the difference between absent and explicit null if a DTO only uses nullable fields. If the API needs to distinguish both states, use a request model with a presence marker, wrapper, or appropriate JSON node representation.

Recommended rules for search APIs:

| State | String | Number | Boolean | Collection |
|---|---|---|---|---|
| Absent | Skip filter | Skip bound | Skip filter | Skip filter |
| Null | Skip or find missing per contract | Usually skip | Usually skip | Usually skip |
| Blank/empty | Trim then skip or reject | N/A | N/A | N/A |
| Empty list | No filter or match-none per contract | N/A | N/A | Must define explicitly |
| Valid value | Add clause | Add range/term | Add term including `false` | Add terms |

This is only a sample policy. An administrative endpoint might need different semantics, such as explicit null meaning find documents without a value.

## 4. Do not use truthy/falsy checks for filters

A common mistake:

~~~java
if (criteria.minPrice() != null
        && criteria.minPrice().doubleValue() > 0) {
    // Add price filter
}
~~~

This condition drops `0` even though `minPrice = 0` may be a valid input.

Similarly:

~~~java
if (Boolean.TRUE.equals(criteria.active())) {
    // Add active filter
}
~~~

This code applies the filter only when `active` is true; `false` is ignored. If `false` means finding inactive documents, this is a bug.

Check presence/null instead:

~~~java
if (criteria.minPrice() != null) {
    // Add lower bound, including zero.
}

if (criteria.active() != null) {
    // Add active=true or active=false.
}
~~~

For strings:

~~~java
if (criteria.text() != null && !criteria.text().isBlank()) {
    // Add full-text query.
}
~~~

For collections:

~~~java
if (criteria.brands() != null && !criteria.brands().isEmpty()) {
    // Add terms filter, subject to the API's empty-list policy.
}
~~~

Do not use `if (value)` or `if (!value)` on Boolean/Number values when `false` and `0` must be distinguished.

## 5. Normalizing inputs before building queries

The query builder should receive normalized data or invoke a pure Java normalization component.

Example:

~~~java
public final class ProductSearchNormalizer {

    private ProductSearchNormalizer() {
    }

    public static ProductSearchCriteria normalize(
            ProductSearchCriteria criteria
    ) {
        String text = normalizeText(criteria.text());
        String category = normalizeCode(criteria.category());

        List<String> brands = criteria.brands() == null
                ? null
                : criteria.brands().stream()
                        .filter(Objects::nonNull)
                        .map(String::trim)
                        .filter(value -> !value.isEmpty())
                        .distinct()
                        .toList();

        return new ProductSearchCriteria(
                criteria.tenantId(),
                text,
                category,
                brands,
                criteria.minPrice(),
                criteria.maxPrice(),
                criteria.active(),
                normalizeCode(criteria.status()),
                criteria.hasDescription()
        );
    }

    private static String normalizeText(String value) {
        if (value == null) {
            return null;
        }

        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized;
    }

    private static String normalizeCode(String value) {
        if (value == null) {
            return null;
        }

        String normalized = value.trim();
        return normalized.isEmpty() ? null : normalized.toUpperCase(Locale.ROOT);
    }
}
~~~

This example chooses the policy: blank text/codes become absent; collections strip null/blank elements and deduplicate. Another API might return a validation error when given blank strings or empty lists. Pick a consistent behavior and document it in the API contract.

Do not blindly lowercase all search text. Analyzers and languages govern case handling; normalizing query strings should align with mappings and semantics.

## 6. Validating relationships between filters

Criteria may contain individually valid values whose combination is invalid.

For example:

- `minPrice` greater than `maxPrice`.
- `startDate` after `endDate`.
- A status list containing unsupported values.
- A filter requiring text when text is blank.
- An endpoint requiring at least one of SKU or keyword.

Example validation:

~~~java
public void validate(ProductSearchCriteria criteria) {
    if (criteria.minPrice() != null
            && criteria.maxPrice() != null
            && criteria.minPrice().compareTo(criteria.maxPrice()) > 0) {
        throw new InvalidSearchCriteriaException(
                "minPrice must not exceed maxPrice"
        );
    }

    if (criteria.brands() != null
            && criteria.brands().size() > 50) {
        throw new InvalidSearchCriteriaException(
                "Too many brand filters"
        );
    }
}
~~~

Validation should run before the query builder constructs Query DSL. The query builder should not have to guess how to deal with inverted ranges or oversized filter lists.

Do not silently swap `min`/`max` to "fix" a request unless the API contract specifies doing so. Rejecting invalid input is usually clearer than silently altering the caller's intent.

## 7. AND rules: every condition must hold

In product search, common conditions are:

- Tenant must match.
- Status must be `PUBLISHED`.
- If category is given, category must match.
- If price range is given, price must fall within bounds.
- If brands are given, brand must be in the list.

This is an AND relationship. Elasticsearch bool queries typically use `filter` for constraints that do not need relevance scoring.

~~~text
tenant = tenant-42
    AND status = PUBLISHED
    AND category = ACCESSORIES
    AND price >= 100000
    AND price <= 2000000
    AND brand IN (ACME, CONTOSO)
~~~

Example Query DSL:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "PUBLISHED" } },
        { "term": { "category": "ACCESSORIES" } },
        { "range": { "price": { "gte": 100000, "lte": 2000000 } } },
        { "terms": { "brand": ["ACME", "CONTOSO"] } }
      ]
    }
  }
}
~~~

`filter` does not affect relevance scores and suits exact matches, numeric/date ranges, and tenant scoping.

When an optional filter has no value, omit its clause. The remaining filters still combine with AND.

## 8. OR rules: only one branch needs to match

Suppose we search for products where:

- Name contains the keyword; or
- SKU matches exactly; or
- Barcode matches exactly.

This is an OR group. Use `should` and explicitly specify `minimum_should_match`:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "PUBLISHED" } }
      ],
      "should": [
        { "match": { "name": "keyboard" } },
        { "term": { "sku": "keyboard" } },
        { "term": { "barcode": "keyboard" } }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Tenant/status conditions remain ANDed with the entire OR group. That means:

~~~text
tenant matches
AND status is PUBLISHED
AND (name matches OR sku matches OR barcode matches)
~~~

If a bool query has `must` or `filter`, `should` defaults to merely boosting score and is not required to match. Therefore, whenever business logic requires at least one OR branch, set `minimum_should_match: 1` explicitly.

## 9. NOT rules: excluding conditions

`must_not` excludes documents matching a condition.

Example excluding discontinued products:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } }
      ],
      "must_not": [
        { "term": { "status": "DISCONTINUED" } }
      ]
    }
  }
}
~~~

Meaning:

~~~text
tenant matches
AND NOT(status = DISCONTINUED)
~~~

Distinguish "not `DISCONTINUED`" from "`status` must exist and differ from `DISCONTINUED`". A document missing `status` can still satisfy `must_not term(status = DISCONTINUED)`.

If the field is required to exist, combine `exists` inside `filter`:

~~~json
{
  "bool": {
    "filter": [
      { "exists": { "field": "status" } }
    ],
    "must_not": [
      { "term": { "status": "DISCONTINUED" } }
    ]
  }
}
~~~

Express business semantics accurately: "different from value X" and "has a value, and that value differs from X" are not identical when documents can omit fields.

## 10. Combining condition groups with logical parentheses

When a query combines AND and OR, write out the business expression first before translating it to a bool query.

Example:

~~~text
tenant matches
AND status = PUBLISHED
AND (
      category = ACCESSORIES
      OR brand = ACME
    )
AND (
      price < 500000
      OR price > 5000000
    )
~~~

Each OR group should be a nested bool query:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "PUBLISHED" } },
        {
          "bool": {
            "should": [
              { "term": { "category": "ACCESSORIES" } },
              { "term": { "brand": "ACME" } }
            ],
            "minimum_should_match": 1
          }
        },
        {
          "bool": {
            "should": [
              { "range": { "price": { "lt": 500000 } } },
              { "range": { "price": { "gt": 5000000 } } }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
~~~

Do not dump all clauses into a single `should` list if they belong to separate OR groups. The query builder must preserve the logical parenthesization of the business expression.

A good practice is naming each condition group in code, such as `availabilityFilter`, `priceBandFilter`, and `textMatchQuery`. Meaningful names help reviewers understand the logic without parsing a massive bool expression manually.

## 11. Null in Elasticsearch is not SQL NULL

Elasticsearch does not follow SQL semantics. When `_source` contains a JSON `null`, the field usually produces no indexed value and does not match `exists`. However, `_source` may still retain the key with a `null` value if `_source` is enabled.

Example:

~~~json
{
  "productId": "P-1001",
  "description": null
}
~~~

Normally, the query:

~~~json
{
  "query": {
    "exists": {
      "field": "description"
    }
  }
}
~~~

does not match the document above.

Keep in mind:

- Field absent from source: normally no indexed value.
- Field with `null` value: normally no indexed value.
- Field with empty array: no values to index.
- Field with `null_value` in mapping: explicit null can be indexed as a substitute sentinel value.
- Field ignored due to `ignore_above` or `ignore_malformed`: may have no indexed value even though source holds a value.

Thus, `exists` checks whether an indexed value exists, not strictly whether the JSON key exists in `_source`.

## 12. Finding documents missing a field or having null

To find documents with no indexed value for `description`, use `must_not exists`:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

This can include documents without the key, documents with explicit `null`, empty arrays, and other cases that produce no indexed value.

If the mapping uses `null_value`, explicit `null` is indexed with the sentinel and can match `exists`. Semantics change accordingly.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "keyword",
        "null_value": "__NULL__"
      }
    }
  }
}
~~~

A document with `"description": null` can be indexed with the sentinel `__NULL__`. Querying for explicit null via sentinel:

~~~json
{
  "query": {
    "term": {
      "description": "__NULL__"
    }
  }
}
~~~

`null_value` does not alter `_source`; it only substitutes the indexed value for querying. Choose a sentinel that cannot occur as valid data and ensure every writer adheres to the same mapping.

If the business must distinguish three states—absent, explicit null, and normal value—a clearer approach is usually storing an extra status field like `descriptionState` with values `MISSING`, `NULL`, `PRESENT`. An `exists` query alone cannot distinguish absent from explicit null under default behavior.

## 13. Filtering null/missing with exists and must_not

You can build distinct semantics:

| Requirement | Query |
|---|---|
| Field has an indexed value | `exists(field)` |
| Field has no indexed value | `must_not exists(field)` |
| Field equals a specific value | `term(field, value)` |
| Field is explicit null with `null_value` mapping | `term(field, sentinel)` |
| Field differs from value X and must exist | `exists(field) AND must_not term(field, X)` |

Do not write `term field = null` to find nulls as in SQL. A term query expects an indexed term/value; `null` is not a regular term.

If the API offers a `descriptionState` filter, model it with an enum:

~~~java
public enum NullFilter {
    ANY,
    PRESENT,
    MISSING,
    EXPLICIT_NULL
}
~~~

The builder then maps each enum value to its corresponding query. `ANY` adds no condition; `PRESENT` uses `exists`; `MISSING` uses `must_not exists`; `EXPLICIT_NULL` requires mappings/presence markers designed to support it.

## 14. Empty strings and whitespace

Strings `""`, `"   "`, and an absent field are distinct states in source. On a `keyword` field, an empty string can be an indexed value; on a `text` field, the analyzer may produce zero tokens from an empty/whitespace string.

If the search API does not treat empty strings as a filter condition, trim and skip them before building queries:

~~~java
String text = criteria.text();

if (text != null && !text.isBlank()) {
    // Add match or multi_match query.
}
~~~

If the API needs to find documents containing empty strings, it must define explicit mappings and semantics. You cannot use `isBlank()` for that requirement because it intentionally collapses empty strings and whitespace into absent.

Do not automatically trim every keyword value. For identifiers, trimming may be right; for tokens/codes where whitespace is significant, define a dedicated policy.

## 15. Empty lists and terms queries

A `terms` query matches any one of the provided values:

~~~json
{
  "query": {
    "terms": {
      "brand": ["ACME", "CONTOSO"]
    }
  }
}
~~~

If the list is empty, do not rely on implicit behavior or let the query builder emit an ambiguous clause. Pick one of three policies:

1. **Empty means no filter**: skip the condition when the list is empty.
2. **Empty means no matches**: emit match-none or return empty results per use case.
3. **Empty is invalid**: return a validation error.

Example helper for the "empty means no filter" policy:

~~~java
if (criteria.brands() != null && !criteria.brands().isEmpty()) {
    filters.add(termsQuery("brand", criteria.brands()));
}
~~~

If an endpoint has semantics "the user selected an empty list, meaning they may view zero products", skipping the filter is a serious security/business bug. Represent this policy with a dedicated enum/command rather than inferring it solely from an empty collection.

Also distinguish an absent list from an empty list if the API needs to support both states. An ordinary DTO may need a presence marker to preserve that distinction.

## 16. Boolean false and numeric 0 are valid values

Boolean filters typically have three states:

- `true`: active only.
- `false`: inactive only.
- `null`: do not filter by `active`, if the API picks those semantics.

Query:

~~~json
{
  "query": {
    "term": {
      "active": false
    }
  }
}
~~~

Similarly, the range `price >= 0` must keep the lower bound of 0:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 0
      }
    }
  }
}
~~~

Do not write `if (active)` or `if (minPrice.doubleValue() > 0)`. Check `!= null`.

## 17. Price ranges: inclusive, exclusive, and inverted ranges

Elasticsearch range queries support the operators:

| Operator | Meaning |
|---|---|
| `gt` | Greater than |
| `gte` | Greater than or equal to |
| `lt` | Less than |
| `lte` | Less than or equal to |

If the API defines a closed price interval on both ends, use `gte` and `lte`. If it requires "over 100,000", use `gt`.

When only min is present:

~~~json
{
  "range": {
    "price": {
      "gte": 100000
    }
  }
}
~~~

When only max is present:

~~~json
{
  "range": {
    "price": {
      "lte": 2000000
    }
  }
}
~~~

When both are present:

~~~json
{
  "range": {
    "price": {
      "gte": 100000,
      "lte": 2000000
    }
  }
}
~~~

If min exceeds max, return a validation error. Never send an inverted range and expect Elasticsearch to guess intent.

For monetary amounts, standardize units and storage types. You can store minor units as integer/long to avoid floating-point inaccuracy; if mappings use `double`, understand precision behavior and how `BigDecimal` converts to query values.

## 18. Date filters and timezones

Date filters commonly have optional start/end bounds:

~~~java
public record DateRangeCriteria(
        Instant from,
        Instant to
) {
}
~~~

When using `Instant`, values already represent a UTC point in time. If the API accepts local date/time, resolve the timezone before converting to `Instant`.

Example range:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "2026-01-01T00:00:00Z",
      "lt": "2026-02-01T00:00:00Z"
    }
  }
}
~~~

Time intervals are usually easiest to define as inclusive start and exclusive end: `[from, to)`. This avoids constructing `"23:59:59.999..."` for the end of a day.

If `from` or `to` is null, add only the present bound. Validate `from <= to`. Never let the CI machine's default timezone dictate the meaning of search dates.

## 19. Building dynamic bool queries with Spring Data Elasticsearch

With modern Spring Data Elasticsearch, you can construct `Query` objects using the Elasticsearch Java API Client and attach them to `NativeQuery`. The example below shows a builder that only adds clauses when criteria provide values.

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query as SpringQuery;
~~~

Java does not support import alias syntax like `Query as SpringQuery`. Therefore, in real code, use the fully qualified name for one of the two types or avoid colliding imports. The builder example below uses the Elasticsearch Java Client `Query` type and returns `NativeQuery`:

~~~java
public NativeQuery build(ProductSearchCriteria criteria) {
    List<co.elastic.clients.elasticsearch._types.query_dsl.Query> filters =
            new ArrayList<>();

    filters.add(term("tenantId", criteria.tenantId()));
    filters.add(term("status", "PUBLISHED"));

    if (criteria.category() != null) {
        filters.add(term("category", criteria.category()));
    }

    if (criteria.active() != null) {
        filters.add(term("active", criteria.active()));
    }

    if (criteria.minPrice() != null || criteria.maxPrice() != null) {
        filters.add(priceRange(
                criteria.minPrice(),
                criteria.maxPrice()
        ));
    }

    if (criteria.brands() != null && !criteria.brands().isEmpty()) {
        filters.add(terms("brand", criteria.brands()));
    }

    List<co.elastic.clients.elasticsearch._types.query_dsl.Query> must =
            new ArrayList<>();

    if (criteria.text() != null && !criteria.text().isBlank()) {
        must.add(multiMatch(criteria.text()));
    }

    co.elastic.clients.elasticsearch._types.query_dsl.Query boolQuery =
            co.elastic.clients.elasticsearch._types.query_dsl.Query.of(q ->
                    q.bool(b -> {
                        b.filter(filters);
                        if (!must.isEmpty()) {
                            b.must(must);
                        }
                        return b;
                    })
            );

    return NativeQuery.builder()
            .withQuery(boolQuery)
            .build();
}
~~~

Helper methods `term`, `terms`, `priceRange`, and `multiMatch` encapsulate Java API Client calls. Example `term` helpers:

~~~java
private Query term(String field, String value) {
    return Query.of(q -> q.term(t -> t
            .field(field)
            .value(FieldValue.of(value))
    ));
}

private Query term(String field, boolean value) {
    return Query.of(q -> q.term(t -> t
            .field(field)
            .value(FieldValue.of(value))
    ));
}
~~~

`tenantId` and `status` are mandatory conditions. Category, active, price, and brands are optional. `false` is not skipped because the builder checks for null, not true.

Specific imports and helpers must match your project's Elasticsearch Java API Client/Spring Data version. Do not mix `org.springframework.data.elasticsearch.core.query.Query` with `co.elastic.clients.elasticsearch._types.query_dsl.Query` without clearly distinguishing their names.

## 20. Helpers for range and terms

A range helper can build a numeric range with one or two bounds:

~~~java
private Query priceRange(BigDecimal min, BigDecimal max) {
    return Query.of(q -> q.range(r -> r.number(n -> {
        n.field("price");

        if (min != null) {
            n.gte(min.doubleValue());
        }

        if (max != null) {
            n.lte(max.doubleValue());
        }

        return n;
    })));
}
~~~

Terms helper:

~~~java
private Query terms(String field, List<String> values) {
    List<FieldValue> terms = values.stream()
            .map(FieldValue::of)
            .toList();

    return Query.of(q -> q.terms(t -> t
            .field(field)
            .terms(v -> v.value(terms))
    ));
}
~~~

Invoke the `terms` helper only when the list has elements per the chosen policy. Do not pass null or empty lists into the builder and let behavior depend on client version.

If using `BigDecimal` for money, verify the mapping and storage unit. Converting via `doubleValue()` is only illustrative for `double` mappings; applications storing minor-unit longs should convert to `long` using the defined currency scale.

## 21. OR groups with nested bool queries

For example, searching by name or SKU when both come from an optional text filter:

~~~java
private Query textOrSku(String text) {
    Query byName = Query.of(q -> q.match(m -> m
            .field("name")
            .query(text)
    ));

    Query bySku = Query.of(q -> q.term(t -> t
            .field("sku")
            .value(FieldValue.of(text))
    ));

    return Query.of(q -> q.bool(b -> b
            .should(byName)
            .should(bySku)
            .minimumShouldMatch("1")
    ));
}
~~~

When a keyword is present, the builder adds this OR group to `must` or `filter` depending on scoring requirements. When no keyword is given, the OR group is omitted.

If OR semantics are needed across multiple exact filters, put a nested bool query inside `filter`. If relevance scoring from name and description is wanted, place the nested bool inside `must` or `should` per semantics.

Do not add OR branches as separate `filter` entries: multiple separate filters in a bool query combine with AND, not OR.

## 22. Combining null filters with other filters

Suppose the API supports `descriptionState`:

- `ANY`: no filter.
- `PRESENT`: `description` has an indexed value.
- `MISSING`: `description` has no indexed value.
- `EXPLICIT_NULL`: supported only if mappings/presence markers distinguish this state.

Builder example:

~~~java
private Query descriptionStateFilter(NullFilter state) {
    return switch (state) {
        case ANY -> null;
        case PRESENT -> Query.of(q -> q.exists(e ->
                e.field("description")
        ));
        case MISSING -> Query.of(q -> q.bool(b -> b
                .mustNot(m -> m.exists(e ->
                        e.field("description")
                ))
        ));
        case EXPLICIT_NULL -> Query.of(q -> q.term(t -> t
                .field("descriptionState")
                .value(FieldValue.of("NULL"))
        ));
    };
}
~~~

In this example, `descriptionState` is an application-maintained presence marker field. Without a marker or an appropriate `null_value`, default `exists` alone cannot distinguish explicit null from missing.

Do not add `null` to the filter list. `ANY` is an explicit state telling the builder to skip the condition.

## 23. Complete query builder with optional filters

A builder can be organized by groups:

~~~java
@Component
public class ProductSearchQueryBuilder {

    public NativeQuery build(ProductSearchCriteria criteria) {
        List<Query> filters = new ArrayList<>();
        List<Query> must = new ArrayList<>();

        // Mandatory scope and business visibility.
        filters.add(term("tenantId", criteria.tenantId()));
        filters.add(term("status", "PUBLISHED"));

        addCategoryFilter(criteria, filters);
        addActiveFilter(criteria, filters);
        addPriceFilter(criteria, filters);
        addBrandFilter(criteria, filters);
        addDescriptionFilter(criteria, filters);

        if (hasText(criteria.text())) {
            must.add(textOrSku(criteria.text().trim()));
        }

        Query query = Query.of(q -> q.bool(b -> {
            b.filter(filters);
            if (!must.isEmpty()) {
                b.must(must);
            }
            return b;
        }));

        return NativeQuery.builder()
                .withQuery(query)
                .build();
    }

    private void addCategoryFilter(
            ProductSearchCriteria criteria,
            List<Query> filters
    ) {
        if (hasText(criteria.category())) {
            filters.add(term(
                    "category",
                    criteria.category().trim()
            ));
        }
    }

    private void addActiveFilter(
            ProductSearchCriteria criteria,
            List<Query> filters
    ) {
        if (criteria.active() != null) {
            filters.add(term("active", criteria.active()));
        }
    }

    private void addPriceFilter(
            ProductSearchCriteria criteria,
            List<Query> filters
    ) {
        if (criteria.minPrice() != null
                || criteria.maxPrice() != null) {
            filters.add(priceRange(
                    criteria.minPrice(),
                    criteria.maxPrice()
            ));
        }
    }

    private void addBrandFilter(
            ProductSearchCriteria criteria,
            List<Query> filters
    ) {
        if (criteria.brands() != null
                && !criteria.brands().isEmpty()) {
            filters.add(terms("brand", criteria.brands()));
        }
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
~~~

This is an illustrative structure; helpers and `Query` types must consistently use your project's version of the Elasticsearch Java API Client. Helpers can be extracted into a shared component if used across multiple use cases.

Notable points:

- Tenant/status filters are always added.
- Category filter is added only when text is present.
- Active filter is added even when its value is `false`.
- Price range preserves min equal to 0.
- Empty brand lists are skipped per chosen policy.
- Full-text/SKU is grouped as OR and added only when a keyword is present.
- The query builder does not call Elasticsearch.

## 24. Mandatory filters and optional filters must be clearly separated

A critical mistake is putting all filters in the same optional bucket. Certain conditions must never be skipped:

- Tenant scope.
- Visibility permissions.
- Soft-delete conditions.
- Allowed display statuses.
- Region/organization boundaries.

Example:

~~~java
filters.add(term("tenantId", authenticatedTenantId));
filters.add(term("deleted", false));
~~~

Optional user filters are added afterward:

~~~java
if (criteria.category() != null) {
    filters.add(term("category", criteria.category()));
}
~~~

Never let `tenantId == null` skip the tenant filter. If tenant is mandatory, the service must reject requests lacking an authenticated tenant.

For multi-tenant admin use cases, create a separate explicitly named and authorized service method/permission. Never use `null` to represent "admin can search everything".

## 25. Possibly missing fields and negation filters

Understand how `must_not` behaves on documents missing a field.

For example, the requirement "not discontinued":

~~~json
{
  "bool": {
    "must_not": [
      {
        "term": {
          "status": "DISCONTINUED"
        }
      }
    ]
  }
}
~~~

Documents without `status` can still be returned because they do not match the excluded term.

If the requirement is "status exists and is not discontinued":

~~~json
{
  "bool": {
    "filter": [
      {
        "exists": {
          "field": "status"
        }
      }
    ],
    "must_not": [
      {
        "term": {
          "status": "DISCONTINUED"
        }
      }
    ]
  }
}
~~~

This is an important distinction in indices containing older documents, migrated data, or fields introduced in newer application versions.

When schemas evolve, explicitly decide how documents missing a field are treated: default value, invalid, or a separate bucket.

## 26. Empty lists: no filter, match-none, or validation error?

Consider a concrete example: an API has an `allowedCategories` filter derived from user permissions.

If the list is empty because the user is permitted to view zero categories, skipping the filter would return every category—an authorization vulnerability.

Conversely, if the client sends `brands=[]` to mean "no brand filter selected", skipping the filter can be correct.

Thus, empty-list semantics depend on data source and intent:

| List source | Possible meaning of empty | Behavior |
|---|---|---|
| Optional user filter | User selected none | Skip filter |
| Authorization allowlist | Permitted to view zero items | Match-none or deny |
| Required command input | Missing required input | Validation error |
| Internal batch selection | No items to process | Do not send request or complete empty |

Never share the same `addTermsIfPresent` helper between user filters and authorization allowlists if their semantics differ.

## 27. Conditionally dependent filters

Some filters are only valid when another condition holds.

For example:

- If `includeOutOfStock=true`, the user needs the corresponding authority.
- If `supplierId` is present, only admin roles can filter by internal supplier.
- If `ADVANCED` mode is chosen, at least one advanced condition must be present.
- If `dateField=UPDATED_AT` is selected, the range must be interpreted against `updatedAt`.

Place these rules in the validation/policy layer:

~~~java
if (criteria.includeOutOfStock()
        && !authorization.canViewOutOfStock()) {
    throw new AccessDeniedException(
            "Not allowed to include out-of-stock products"
    );
}
~~~

The query builder only receives authorized criteria. Never let the builder make authorization decisions just by inspecting a request Boolean.

## 28. Avoiding unintended empty or match-all queries

If all optional filters are absent, the query may retain only mandatory filters. That can be valid or dangerous depending on the endpoint.

For example, browsing all published products in a tenant can be a valid use case. However, an endpoint requiring a keyword should never silently run `match_all` when text is blank.

The service can require at least one condition:

~~~java
if (!hasText(criteria.text())
        && !hasText(criteria.category())
        && criteria.minPrice() == null
        && criteria.maxPrice() == null
        && (criteria.brands() == null || criteria.brands().isEmpty())) {
    throw new InvalidSearchCriteriaException(
            "At least one search filter is required"
    );
}
~~~

If the endpoint permits browsing everything within the tenant, do not reject it. Still enforce bounded page sizes and mandatory tenant/visibility filters.

Do not let the builder default to `match_all` on an empty filter list without reviewing endpoint policy.

## 29. Sorting and pagination are not filters

Query conditions determine which documents match. Sorting and pagination determine ordering and which slice of results is returned.

They can be configured separately:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(boolQuery)
        .withPageable(PageRequest.of(
                criteria.page(),
                criteria.size(),
                allowedSort(criteria.sort())
        ))
        .build();
~~~

Do not leave client-passed page size or sort fields unbounded. Use a sort-field allowlist, maximum page size, and deterministic tie-breakers.

When using `from/size`, bound depth. For deep pagination, use `search_after` with a deterministic sort and PIT when snapshots are needed.

Changing page or sort should never alter filter semantics. Separating these components lets each part be tested independently.

## 30. Testing filter combinations

Because query builders have many branches, test them using a combination matrix. Unit tests should verify query structure or serialize to Query DSL to compare semantics.

Example matrix:

| Criteria | Expected clause |
|---|---|
| `category` null | No category term |
| `category` blank | Skipped or validated per policy |
| `category = ACCESSORIES` | Category term present |
| `active = true` | Active term `true` present |
| `active = false` | Active term `false` present |
| `active = null` | No active term |
| `minPrice = 0` | `gte 0` present |
| `maxPrice = 0` | `lte 0` present |
| `minPrice > maxPrice` | Validation error |
| `brands` null | No terms clause |
| `brands` empty | Per empty-list policy |
| `brands` with 2 elements | Terms contains both values |
| `text` blank | No full-text clause |
| `text` has value | Text/SKU OR group present |
| `tenant` null | Rejected before building query |

Unit tests must check both "clause omitted" and "clause included with `false`/`zero`". Testing only happy paths with truthy values misses common bugs.

## 31. Testing null/missing on real Elasticsearch

Unit-testing query objects does not prove how mappings and `exists` behave. Integration tests against Elasticsearch are needed to verify:

- Fields absent from source.
- Fields with explicit `null`.
- Fields with empty strings.
- Fields with empty arrays.
- Fields with `null_value`.
- Fields ignored due to `ignore_above` or `ignore_malformed` if used by the application.
- Nested/object fields.
- Mappings across old and new index versions.

Example test data:

~~~json
{"productId":"P-1"}
{"productId":"P-2","description":null}
{"productId":"P-3","description":""}
{"productId":"P-4","description":[]}
{"productId":"P-5","description":"Keyboard"}
~~~

Then execute `exists(description)` and `must_not exists(description)` and assert actual results under the mapping. If `null_value` is used, add tests for the sentinel.

Never assume Elasticsearch behaves like relational `IS NULL`.

## 32. Testing AND/OR/NOT with truth tables

For complex queries, write out a truth table first:

| Tenant matches | Status published | Name match | SKU match | Result |
|---|---|---|---|---|
| No | Yes | Yes | Yes | No |
| Yes | No | Yes | Yes | No |
| Yes | Yes | Yes | No | Yes |
| Yes | Yes | No | Yes | Yes |
| Yes | Yes | No | No | No |

Corresponding expression:

~~~text
tenantCorrect
AND statusPublished
AND (nameMatch OR skuMatch)
~~~

Tests should seed documents representing each row of the table and execute integration queries. This catches bool default `should` bugs or missing tenant filters much better than assertions merely checking whether query JSON contains certain strings.

## 33. Common mistakes

### Using truthy checks for Booleans

`false` gets treated as absent. Check `value != null`.

### Using greater-than-zero checks for numbers

Minimum price `0` gets skipped. Check null, not truthiness.

### Conflating absent and explicit null

The API may need to distinguish skipping a filter from searching for null fields. Use presence-aware request models or enum semantics.

### Sending term null

Elasticsearch does not treat `null` like a SQL term. Use `exists`/`must_not exists` or presence markers.

### Assuming exists checks keys in _source

`exists` checks indexed values. Explicit nulls, empty arrays, and ignored fields may not match.

### Neglecting empty-list policies

Empty lists can accidentally drop authorization filters or yield overly broad results. Choose no-filter, match-none, or invalid explicitly.

### Forgetting minimum_should_match

A bool query with `filter`/`must` makes `should` optional by default. Set `minimum_should_match` when an OR requires at least one branch to match.

### Putting all conditions into should

AND conditions turn into ORs. Group mandatory conditions inside `filter` and optional choices in nested bool queries.

### Using must_not without checking exists

Documents missing the field are also returned. If the field must exist, add `exists`.

### Making the tenant filter optional

A `null` tenant can open searches across the whole index. Tenant scope must be mandatory in the service/policy layer.

### Reusing the same helper for user filters and authorization filters

An empty user filter may mean no-filter, whereas an empty authorization allowlist must mean deny/match-none. Separate their semantics.

### Reading SecurityContext inside the query builder

Hidden dependencies make unit testing difficult and can leave background jobs without tenant scope. Pass verified scope via criteria.

### Producing match-all on empty inputs without checking use case

This can accidentally run overly broad queries. Decide whether the endpoint allows full in-scope browsing or requires at least one filter.

## 34. Process for designing optional filters

When adding a filter to a search API:

1. Define what absent, explicit null, blank, and empty mean.
2. Determine whether the filter is mandatory, optional, or permission-dependent.
3. Normalize strings, codes, collections, and timezones before building queries.
4. Preserve Boolean `false` and numeric `0`.
5. Validate relationships such as min/max and from/to.
6. Specify whether an empty list means no-filter, match-none, or invalid.
7. Use `filter` for non-scoring AND conditions.
8. Use nested `bool`/`should` for OR groups with an explicit `minimum_should_match`.
9. Use `must_not` for negated conditions; add `exists` if the field must have a value.
10. Use `exists`/`must_not exists` for indexed presence without assuming SQL `NULL` semantics.
11. If absent must be distinguished from explicit null, design an appropriate presence marker or `null_value`.
12. Keep tenant/visibility/soft-delete scopes in mandatory conditions.
13. Use server-controlled field names and sort fields.
14. Bound page size and pagination depth.
15. Unit-test the null/empty/false/zero matrix and AND/OR/NOT combinations.
16. Integration-test `exists`/`null_value`/mappings and actual query results.
17. Monitor query latency and avoid logging raw criteria containing sensitive data.

## References

- [Elasticsearch — Boolean query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html)
- [Elasticsearch — Exists query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-exists-query.html)
- [Elasticsearch — Term query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-term-query.html)
- [Elasticsearch — Terms query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-terms-query.html)
- [Elasticsearch — Range query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-range-query.html)
- [Elasticsearch — Null value mapping parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/null-value.html)
- [Elasticsearch — Mapping source field](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-source-field.html)
- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/query-methods.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

## Conclusion

Optional filters require clear semantics for absent, null, blank, and empty before being translated into Query DSL. Use null checks rather than truthy/falsy checks to preserve Boolean `false` and numeric `0`; validate ranges and collections; use `filter` for AND, nested `bool`/`should` for OR, and `must_not` for NOT. In Elasticsearch, `exists` checks indexed values rather than matching SQL `IS NULL`; explicit nulls normally produce no indexed value by default, whereas `null_value` or presence markers can express specialized semantics. Tenant and visibility scopes must always be mandatory. Unit-testing combination matrices and integration-testing against real mappings ensure queries faithfully reflect business rules.
