# Handling Optional Conditions When Building Filter Forms

Search forms often contain many fields that users are not required to fill out completely: keyword, status, category, price range, date range, or creator. When submitting the form, the application must include only the conditions actually provided in the Elasticsearch query.

Spring Data Elasticsearch provides `Criteria` and `CriteriaQuery` to build queries condition by condition. You can add criteria when values are present, combine them using AND/OR, and then execute with `ElasticsearchOperations.search(...)`.

The key point is distinguishing **no condition provided** from **a provided value to search for**. For example, `minPrice = 0` is a valid condition; an empty string usually means the user did not enter a keyword; an empty category list usually means do not filter by category.

## 1. From Form to CriteriaQuery

Suppose a product search screen has these fields:

- Keyword in the product name.
- Publication status.
- Category.
- Minimum and maximum price.
- Creation date from and to.

Users might enter only a keyword, or only select a status, or combine multiple fields. If you build a fixed query with every condition, null/empty values can cause erroneous queries or narrow results unexpectedly.

The processing flow should look like this:

~~~mermaid
flowchart TD
    A["Filter form from user"] --> B["Validate and normalize input"]
    B --> C["Create Criteria for conditions with values"]
    C --> D["Combine AND / OR"]
    D --> E["Create CriteriaQuery"]
    E --> F["Add pageable and sort"]
    F --> G["ElasticsearchOperations.search"]
    G --> H["Returned SearchHits"]
~~~

For example, if the user only selects status `PUBLISHED` and minimum price `100000`, the query only needs those two conditions. Do not add a product name condition with an empty string or a maximum price bound with null.

## 2. What Are Criteria and CriteriaQuery?

`Criteria` describes a condition on an Elasticsearch field. Some commonly used operations:

| Operation | Meaning |
|---|---|
| `is(value)` | Matches value |
| `isNot(value)` | Does not equal value |
| `greaterThan(value)` | Greater than |
| `greaterThanEqual(value)` | Greater than or equal to |
| `lessThan(value)` | Less than |
| `lessThanEqual(value)` | Less than or equal to |
| `between(from, to)` | Within range |
| `in(values)` | Belongs to a set of values |
| `matches(text)` | Text search via match mechanism |
| `contains(text)` | Substring search with Criteria semantics |
| `exists()` | Field exists |
| `isNull()` | Field has no indexed value per Elasticsearch semantics |

`CriteriaQuery` wraps Criteria into a query that Spring Data Elasticsearch can execute.

Simple example:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("status").is("PUBLISHED")
        .and("price").greaterThanEqual(100000);

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

Here, both conditions are combined with AND: the product must have status `PUBLISHED` and price greater than or equal to `100000`.

`CriteriaQuery` is a Spring Data abstraction for building queries. It is neither the JPA Criteria API nor a SQL string.

## 3. Designing a DTO for Filter Conditions

Do not accept loose individual parameters and build queries in multiple places. Group them into a filter DTO:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record ProductFilter(
        String keyword,
        String status,
        List<String> categories,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Instant createdFrom,
        Instant createdTo
) {
}
~~~

The DTO represents optional conditions. A `null` value means the user did not supply the corresponding condition.

Before building the query, normalize the input:

- Trim leading/trailing whitespace from keywords.
- Treat empty strings as no condition.
- Remove duplicate values from lists.
- Verify that status and categories belong to valid value sets.
- Verify that minimum price is not greater than maximum price.
- Verify that start date is not after end date.

Do not use a check like `if (minPrice > 0)` to decide whether a price was entered. The value `0` can still be a valid condition. Check `minPrice != null`.

## 4. Adding Criteria Only When a Value Is Present

Suppose `tenantId` is a mandatory condition for every query. We can use it as the root Criteria and append optional conditions.

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.util.StringUtils;

public CriteriaQuery buildQuery(
        String tenantId,
        ProductFilter filter
) {
    // tenantId is a mandatory condition and must not be omitted.
    Criteria criteria = new Criteria("tenantId").is(tenantId);

    if (StringUtils.hasText(filter.keyword())) {
        criteria = criteria.and("name").matches(
                filter.keyword().trim()
        );
    }

    if (StringUtils.hasText(filter.status())) {
        criteria = criteria.and("status").is(
                filter.status().trim()
        );
    }

    if (filter.categories() != null
            && !filter.categories().isEmpty()) {
        criteria = criteria.and("category").in(
                filter.categories()
        );
    }

    if (filter.minPrice() != null) {
        criteria = criteria.and("price").greaterThanEqual(
                filter.minPrice()
        );
    }

    if (filter.maxPrice() != null) {
        criteria = criteria.and("price").lessThanEqual(
                filter.maxPrice()
        );
    }

    if (filter.createdFrom() != null) {
        criteria = criteria.and("createdAt").greaterThanEqual(
                filter.createdFrom()
        );
    }

    if (filter.createdTo() != null) {
        criteria = criteria.and("createdAt").lessThanEqual(
                filter.createdTo()
        );
    }

    return new CriteriaQuery(criteria);
}
~~~

In this example:

- `tenantId` is always applied to scope data by tenant.
- `keyword` is added only when it has text.
- `status` is added only when the user selects a status.
- `categories` is added only when the list is non-empty.
- Each price and date bound is added independently, so the user can enter only a minimum price or only a maximum price.

`criteria = criteria.and(...)` appends a new condition to the current Criteria chain. All conditions in the example are combined with AND.

Note: field names in Criteria must be Elasticsearch field names matching the entity's mapping. If a Java property uses a different name from the index field due to mapping configuration, use the exact name Spring Data maps to.

## 5. When No Optional Conditions Are Provided

Some forms allow users to click search without entering any filter. The desired behavior must be defined explicitly.

The example above has a mandatory `tenantId`, so even if the user enters no filters, the query remains scoped to the tenant. This differs from querying all data across the index.

If there is no mandatory condition and the filter list is empty, the application should explicitly choose one of these approaches:

- Return a validation error requiring at least one condition.
- Return an empty list if unfiltered search is disallowed.
- Intentionally allow a broad query, while always capping page size and enforcing access permissions.

Do not accidentally construct an empty query and let default behavior dictate data scope. In multi-tenant systems or with sensitive data, tenant/permission filters must be added from the authenticated context, never taken arbitrarily from the form.

## 6. Distinguishing null, Empty Strings, Zero, and Empty Lists

A common mistake when handling forms is treating all "empty-looking" values the same way.

| Input | Common interpretation | How to handle |
|---|---|---|
| `keyword = null` | No keyword entered | Skip condition |
| `keyword = ""` | Empty string | Trim, then skip |
| `minPrice = null` | No minimum price set | Skip lower bound |
| `minPrice = 0` | Minimum price equals 0 | Add range condition |
| `categories = null` | No list sent | Skip condition |
| `categories = []` | No category selected | Usually skip condition |
| `status = "PUBLISHED"` | A status selected | Add exact condition |
| `includeArchived = false` | User selected false | Still handle as a provided value if the filter is meaningful |

For boolean checkboxes, if you need to distinguish "unselected" from "selected false", use a nullable `Boolean` or a stateful representation. Primitive `boolean` cannot distinguish these two cases.

### When Users Want to Find Documents Missing a Field

Do not confuse `null` in the DTO with a request to find documents without a value. `null` in a filter usually means skip the condition; whereas if the user actively selects "no status yet", add a corresponding query condition, such as `exists` or `isNull` according to the field's mapping and semantics.

In Elasticsearch, a field with JSON `null` is generally not indexed as a term. If the mapping uses `null_value`, representation and querying will differ. Check the actual mapping before designing filters for null/missing values.

## 7. Building Price Ranges and Date Ranges

Price ranges typically have two independent bounds. Do not require users to enter both.

Example:

~~~java
if (filter.minPrice() != null) {
    criteria = criteria.and("price")
            .greaterThanEqual(filter.minPrice());
}

if (filter.maxPrice() != null) {
    criteria = criteria.and("price")
            .lessThanEqual(filter.maxPrice());
}
~~~

If both bounds are present, the condition is equivalent to:

~~~json
{
  "range": {
    "price": {
      "gte": 100000,
      "lte": 500000
    }
  }
}
~~~

Use `greaterThanEqual` and `lessThanEqual` when both endpoints should be inclusive. If business rules call for a half-open interval, pick `greaterThan` or `lessThan` accordingly.

For dates and times, use `Instant` or a date-time type with an explicit timezone/offset. For instance, if the form selects dates in a local timezone, convert day boundaries into instants in the business timezone before constructing the query. This prevents discrepancies when server and user are in different timezones.

Before creating the query, validate:

~~~java
if (filter.minPrice() != null
        && filter.maxPrice() != null
        && filter.minPrice().compareTo(filter.maxPrice()) > 0) {
    throw new IllegalArgumentException(
            "minPrice must be less than or equal to maxPrice"
    );
}
~~~

Do not silently swap the two bounds if the user enters them reversed. Returning a clear error lets the form display the exact cause.

## 8. Text Search and Exact Filter Conditions

A form often combines full-text search with exact filters.

Example:

- Keyword `wireless keyboard`: search on field `name`.
- Status `PUBLISHED`: exact filter on `status`.
- Category `ACCESSORIES`: exact filter on `category`.

In the Criteria API:

~~~java
Criteria criteria = new Criteria("name").matches("wireless keyboard")
        .and("status").is("PUBLISHED")
        .and("category").is("ACCESSORIES");

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

`matches(...)` is used for text search; `is(...)` is typically suited for keyword fields and value equality conditions.

The mapping must align:

~~~java
@Field(type = FieldType.Text)
private String name;

@Field(type = FieldType.Keyword)
private String status;

@Field(type = FieldType.Keyword)
private String category;
~~~

Do not use the same field type for every need. If status is mapped as `text`, an analyzer can alter tokens; if product name is only keyword, word-based searching may not behave as expected.

If product name has a multi-field, use the main `name` field for full-text and a sub-field such as `name.keyword` for exact matching or sorting.

## 9. Combining AND and OR

Typically, independent filters in a form are combined with AND: status must match, category must match, and price must fall within the range.

Example:

~~~text
status = PUBLISHED
AND category = ACCESSORIES
AND price >= 100000
AND price <= 500000
~~~

Some forms have multiple choices within the same group and want to match any one of the values. On the same field, `in(...)` is usually clearer than multiple OR conditions:

~~~java
Criteria criteria = new Criteria("category")
        .in(List.of("ACCESSORIES", "KEYBOARD"));
~~~

This corresponds to the condition that category belongs to one of the two values.

For OR logic across different fields, express the condition group clearly. For example, business rules want products with status `FEATURED` or label `PROMOTED`. You can use a Criteria OR chain or switch to a query builder supporting explicit bool queries:

~~~java
Query query = Query.of(q -> q
        .bool(b -> b
                .should(s -> s
                        .term(t -> t
                                .field("status")
                                .value("FEATURED")
                        )
                )
                .should(s -> s
                        .term(t -> t
                                .field("label")
                                .value("PROMOTED")
                        )
                )
                .minimumShouldMatch("1")
        )
);
~~~

This example uses the Elasticsearch Java API Client to express OR inside a bool group. If a query has multiple nested AND/OR groups, `NativeQuery` or `BoolQueryBuilder` is better suited when exact control over DSL structure is needed. Do not chain loose Criteria in ways that obscure AND/OR precedence.

## 10. Adding Pagination and Sorting

A filter form usually needs paging and sorting. `CriteriaQuery` accepts a pageable:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

CriteriaQuery query = new CriteriaQuery(criteria);

query.setPageable(
        PageRequest.of(
                0,
                20,
                Sort.by(Sort.Direction.DESC, "createdAt")
        )
);
~~~

Then execute:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
~~~

Notes:

- Page index is zero-based (`0`).
- Page size should be capped at a reasonable limit.
- Sort fields must have suitable mappings, usually keyword or numeric/date.
- Do not sort directly on text fields by default.
- For large result sets, consider `search_after` instead of deep pagination with `from`/`size`.

If users are allowed to pick a sort column, map the form selection against an allowlist of permitted fields. Do not pass arbitrary client-supplied field names directly into the query.

## 11. Complete Service for a Filter Form

A service can consolidate validation, Criteria construction, and search execution:

~~~java
import java.util.Optional;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(
            String tenantId,
            ProductFilter filter,
            int page,
            int size
    ) {
        validate(filter);

        Criteria criteria = new Criteria("tenantId").is(tenantId);

        if (StringUtils.hasText(filter.keyword())) {
            criteria = criteria.and("name")
                    .matches(filter.keyword().trim());
        }

        if (StringUtils.hasText(filter.status())) {
            criteria = criteria.and("status")
                    .is(filter.status().trim());
        }

        if (filter.categories() != null
                && !filter.categories().isEmpty()) {
            criteria = criteria.and("category")
                    .in(filter.categories());
        }

        if (filter.minPrice() != null) {
            criteria = criteria.and("price")
                    .greaterThanEqual(filter.minPrice());
        }

        if (filter.maxPrice() != null) {
            criteria = criteria.and("price")
                    .lessThanEqual(filter.maxPrice());
        }

        if (filter.createdFrom() != null) {
            criteria = criteria.and("createdAt")
                    .greaterThanEqual(filter.createdFrom());
        }

        if (filter.createdTo() != null) {
            criteria = criteria.and("createdAt")
                    .lessThanEqual(filter.createdTo());
        }

        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(
                PageRequest.of(
                        page,
                        size,
                        Sort.by(Sort.Direction.DESC, "createdAt")
                )
        );

        return operations.search(query, ProductDocument.class);
    }

    private void validate(ProductFilter filter) {
        if (filter.minPrice() != null
                && filter.maxPrice() != null
                && filter.minPrice().compareTo(filter.maxPrice()) > 0) {
            throw new IllegalArgumentException(
                    "minPrice must be less than or equal to maxPrice"
            );
        }

        if (filter.createdFrom() != null
                && filter.createdTo() != null
                && filter.createdFrom().isAfter(filter.createdTo())) {
            throw new IllegalArgumentException(
                    "createdFrom must not be after createdTo"
            );
        }
    }
}
~~~

This example illustrates service structure. In real applications, validate non-negative page/size, cap page size, normalize category lists, obtain tenant from the security context, and ensure fields are mapped with proper types.

`SearchHits` contains metadata and results. If an API DTO is needed, map `hits.getSearchHits()` to a response model instead of exposing Spring Data types externally.

## 12. When Should You Switch from CriteriaQuery to NativeQuery?

`CriteriaQuery` fits filter forms with relatively simple structures:

- Basic AND/OR.
- Exact matching.
- Range queries.
- Value sets.
- Standard text search.
- Pagination and sorting.

`NativeQuery` fits when advanced DSL expressiveness or finer control is needed:

- Multi-group nested bool queries.
- Nested queries.
- Function score.
- Script queries.
- Complex aggregations.
- Query DSL features not conveniently expressed by the Criteria abstraction.

There is no need to switch to NativeQuery solely because a form has many optional fields. You can continue building Criteria conditionally. Only switch abstractions when query structure or required features go beyond what the Criteria API expresses cleanly.

## 13. Common Pitfalls When Handling Optional Filters

### Adding Conditions with null

Calling `is(null)` when the user omitted a value is not equivalent to skipping the filter. Check for null before adding Criteria.

### Not Trimming Strings

The string `"   "` passes a `!= null` check yet contains no useful search text. Use `StringUtils.hasText(...)` or equivalent normalization.

### Treating Zero as Missing

`minPrice = 0` can be a valid condition. Use a null check instead of checking greater than 0.

### Querying terms with an Empty List

An empty list usually means the user has not selected a filter. Skip the condition rather than creating `in(emptyList)`, as its semantics or generated query may not behave as expected.

### Combining Everything with OR

If status, category, and price are simultaneously required filters, using OR returns documents matching just one condition. Clarify business logic before building the query.

### Using the Wrong Field Type

`term` on an analyzed text field may not match the raw value. Use keyword for statuses/codes and text for content requiring full-text search.

### Not Capping Page Size

Users can send a very large page size, causing memory- and resource-heavy requests. Enforce server-side limits rather than trusting form input.

### Allowing Clients to Pick Arbitrary Fields

Field names in Criteria are query metadata. Permit only application-defined fields, especially for dynamic sorting and filtering.

### Skipping Permission Filters

Tenant, owner, or data-scope filters must be added from the security context. Never allow users to bypass them by sending null or tampering with requests.

## 14. Workflow for Building a Filter Form

When implementing a search form with CriteriaQuery:

1. Design a DTO with clear data types for each condition.
2. Distinguish unprovided inputs from valid values like 0 or boolean false.
3. Normalize strings and lists before constructing the query.
4. Validate price ranges, dates, and value lists.
5. Create Criteria only for present conditions.
6. Always add mandatory tenant/access filters from a trusted source.
7. Combine conditions with AND/OR per business requirements.
8. Create CriteriaQuery and add bounded pageable/sort.
9. Execute with `ElasticsearchOperations.search`.
10. When complex DSL is needed, consider NativeQuery.
11. Verify field mappings and actual queries across various filter combinations.

## Conclusion

Handling optional conditions with CriteriaQuery is the process of turning normalized form inputs into Criteria that appear only when users actually supply them. Use AND for filters that must hold simultaneously, use OR or `in` sets for alternatives, and always keep mandatory authorization conditions. Then create a `CriteriaQuery`, attach pagination/sorting, and execute via `ElasticsearchOperations.search(...)`.
