# Designing Valid Filters and Controlling User-Supplied Field Names

In applications using **Spring Data Relational JDBC (Spring Data JDBC)**, dynamic queries often begin from a search screen where users choose a status, customer, date range, minimum value, or sort order. Those selections are sent to the server via query parameters or JSON and translated into query conditions.

A critical point of control is that **filter values** and **field names/identifiers** are fundamentally different. Values such as customer IDs or creation dates can be bound as SQL parameters. Column names, property names, operators, and sort directions determine the query structure itself; they must be selected from an application-defined allowlist. Never pass client-supplied field names directly into Criteria, Sort, or SQL strings.

This lesson explains how to design typed filter DTOs, allowlist fields and operators, build Criteria/Query, construct safe dynamic SQL, handle NULL/IN/LIKE, and control sorting and pagination.

## 1. Separating Input Data from Query Structure

Suppose an order search API receives these options:

~~~http
GET /api/orders?status=OPEN&customerId=101&createdFrom=2026-01-01&sortBy=createdAt&direction=DESC&page=0&size=20
~~~

Values like OPEN, 101, and the start date are **data**. The server can validate their types and value domains, then bind them into conditions. sortBy=createdAt is a **requested identifier**; it is not an ordinary SQL value. If the server concatenates that string straight into ORDER BY, clients can request columns or expressions outside what the application allows.

Distinguish three groups:

| Group | Example Sent by Client | Handling |
|---|---|---|
| Filter values | status=OPEN, customerId=101 | Parse into Java types, validate, and bind as parameters |
| Field names | sortBy=createdAt, field=customerId | Look up in allowlist and map to fixed properties/columns |
| Operators/sort directions | operator=GTE, direction=DESC | Convert into enums or predefined code branches |

~~~mermaid
flowchart TB
    Request["HTTP request<br/>filter, sort, page"]
    Parse["Parse into typed DTO"]
    Validate["Validate values<br/>field, operator, sort, limits"]
    Allow["Allowlist<br/>field/property/SQL column"]
    Build["Build Criteria or SQL"]
    Bind["Bind values"]
    DB[("Database")]
    Result["Query results"]
    Request --> Parse --> Validate --> Allow --> Build --> Bind --> DB --> Result
~~~

Core principle: **clients choose from options published by the server; clients must never define SQL structure**.

## 2. Why Can't Column Names Be Bound Like Values?

Prepared statements bind values into parameter positions:

~~~sql
SELECT id, status
FROM sales_orders
WHERE status = :status;
~~~

Here :status is a value placeholder. The JDBC driver sends the value separately from the SQL structure, so user-entered strings are treated strictly as data.

However, parameters do not represent identifiers. For example:

~~~sql
SELECT id, status
FROM sales_orders
ORDER BY :sortColumn;
~~~

If you bind sortColumn = 'created_at', the database usually treats it as a constant literal used for sorting, not the column to sort by. The statement does not perform the intended dynamic sort.

The alternative is direct concatenation:

~~~java
String sql = "SELECT id, status FROM sales_orders ORDER BY "
    + request.sortBy();
~~~

This is dangerous because clients can send unexpected identifiers, expressions, or syntax. Bind parameters cannot protect strings concatenated into SQL structure.

Therefore:

- **Values** use bind parameters.
- **Identifiers** are selected strictly from a server-side allowlist.
- **Operators** are mapped from an enum to fixed SQL operators.
- **Directions** accept only ASC or DESC from an enum/code branch.

## 3. Designing Typed Filter DTOs

When a search screen has a fixed set of fields, a typed DTO is usually clearer and safer than a generic structure holding field, operator, and Object value.

Example:

~~~java
package com.example.sales.order;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderSearchRequest(
    String status,
    Long customerId,
    LocalDateTime createdFrom,
    LocalDateTime createdTo,
    BigDecimal minimumAmount,
    OrderSortField sortBy,
    SortDirection direction,
    Integer page,
    Integer size
) {}

public enum OrderSortField {
    CREATED_AT,
    STATUS,
    CUSTOMER_ID,
    TOTAL_AMOUNT
}

public enum SortDirection {
    ASC,
    DESC
}
~~~

The DTO does not accept arbitrary SQL column names. OrderSortField allows only published enum values. When a client sends a value outside the enum, the framework can reject the request right at binding time.

### Validating Value Domains

A filter should validate at least:

- status belongs to the valid business status set.
- customerId is positive.
- createdFrom is not after createdTo.
- minimumAmount is non-negative and within business limits.
- page is non-negative.
- size is greater than 0 and does not exceed the maximum page size.
- sortBy and direction belong to published choices.

Example service validation:

~~~java
private static final int DEFAULT_PAGE_SIZE = 20;
private static final int MAX_PAGE_SIZE = 100;

private static int validatedPage(Integer page) {
    int value = page == null ? 0 : page;
    if (value < 0) {
        throw new IllegalArgumentException("Page must be non-negative");
    }
    return value;
}

private static int validatedSize(Integer size) {
    int value = size == null ? DEFAULT_PAGE_SIZE : size;
    if (value < 1 || value > MAX_PAGE_SIZE) {
        throw new IllegalArgumentException(
            "Page size must be between 1 and " + MAX_PAGE_SIZE
        );
    }
    return value;
}

private static void validateDateRange(
        LocalDateTime from,
        LocalDateTime to) {
    if (from != null && to != null && from.isAfter(to)) {
        throw new IllegalArgumentException(
            "createdFrom must not be after createdTo"
        );
    }
}
~~~

In Spring MVC applications, Bean Validation (@Min, @Max, @Positive, @NotNull, custom validators) can map failures to HTTP 400. Whether validated in controllers or services, keep domain rules in one reusable place without assuming clients behave properly.

## 4. Allowlisting Field Names and Mapping to Properties/Columns

If an API needs generic filters, never let clients pass arbitrary entity property names. Define an enum or fixed map:

~~~java
public enum OrderFilterField {
    STATUS,
    CUSTOMER_ID,
    CREATED_AT,
    TOTAL_AMOUNT
}
~~~

The server decides which operators and data types are permitted for each field:

| API Field | Java Property | SQL Column | Value Type | Allowed Operators |
|---|---|---|---|---|
| STATUS | status | status | String/enum | EQ, IN |
| CUSTOMER_ID | customerId | customer_id | Long | EQ, IN |
| CREATED_AT | createdAt | created_at | LocalDateTime | GTE, LTE, BETWEEN |
| TOTAL_AMOUNT | totalAmount | total_amount | BigDecimal | GTE, LTE |

The three names across the three layers can differ:

- API name is the client contract.
- Java property is used in Criteria/Sort according to Spring Data mapping.
- SQL column is the identifier used in custom SQL.

Do not assume a client-sent string can be used directly across all three layers.

### Mapping Sort with switch

~~~java
private static String toOrderProperty(OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> "createdAt";
        case STATUS -> "status";
        case CUSTOMER_ID -> "customerId";
        case TOTAL_AMOUNT -> "totalAmount";
    };
}
~~~

Returned names are known Java properties in source code. If sort field is omitted, use a default:

~~~java
OrderSortField sortField = request.sortBy() == null
    ? OrderSortField.CREATED_AT
    : request.sortBy();

Sort.Direction direction =
    request.direction() == SortDirection.ASC
        ? Sort.Direction.ASC
        : Sort.Direction.DESC;

Sort sort = Sort.by(
    new Sort.Order(direction, toOrderProperty(sortField)),
    Sort.Order.desc("id")
);
~~~

id acts as a fixed tie-breaker keeping order deterministic when multiple orders share the same primary sort value. If the API allows multi-column sorting, cap the number of sort fields, validate each one, and append a unique key at the end if deterministic ordering is needed.

## 5. Using Criteria and Query with Allowed Fields

Spring Data JDBC provides Criteria and Query to construct conditions without manually concatenating SQL. Properties passed into Criteria are still identifiers; therefore use only property names from code/allowlists.

Example DTO with fixed fields:

~~~java
public record OrderFilter(
    String status,
    Long customerId,
    LocalDateTime createdFrom,
    LocalDateTime createdTo
) {}
~~~

Building Criteria:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

public List<Order> search(OrderFilter filter, int page, int size) {
    Criteria criteria = null;

    if (filter.status() != null) {
        criteria = append(criteria,
            Criteria.where("status").is(filter.status()));
    }
    if (filter.customerId() != null) {
        criteria = append(criteria,
            Criteria.where("customerId").is(filter.customerId()));
    }
    if (filter.createdFrom() != null) {
        criteria = append(criteria,
            Criteria.where("createdAt").greaterThanOrEquals(
                filter.createdFrom()));
    }
    if (filter.createdTo() != null) {
        criteria = append(criteria,
            Criteria.where("createdAt").lessThanOrEquals(
                filter.createdTo()));
    }

    Query query = criteria == null
        ? Query.empty()
        : Query.query(criteria);

    query = query
        .sort(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(size)
        .offset((long) page * size);

    return StreamSupport.stream(
        template.findAll(query, Order.class).spliterator(), false
    ).toList();
}

private static Criteria append(Criteria current, Criteria next) {
    return current == null ? next : current.and(next);
}
~~~

This snippet demonstrates chaining optional conditions with AND. Property names such as status, customerId, and createdAt are hardcoded on the server. If clients may choose fields, convert the API value into an enum and map it to an allowed property before building Criteria.

Method names like greaterThanOrEquals, lessThanOrEquals, Query.empty, Criteria.and overloads, and return types should be checked against your project's Spring Data Relational version. If your version uses different APIs, keep the allowlist principle intact and use the matching API instead of passing raw client strings.

### Counting with the Same Conditions

If you need the count of roots matching the same filter:

~~~java
long count = criteria == null
    ? template.count(Order.class)
    : template.count(Query.query(criteria), Order.class);
~~~

Do not load all aggregates and call size() just to count. Note that count has no page bounds; it returns the total number of matching roots.

## 6. Generic Filters: Allowlisting Fields, Operators, and Value Types

An advanced search API might accept a list of conditions:

~~~json
{
  "filters": [
    { "field": "STATUS", "operator": "IN", "values": ["OPEN", "CONFIRMED"] },
    { "field": "CUSTOMER_ID", "operator": "EQ", "value": 101 },
    { "field": "CREATED_AT", "operator": "GTE", "value": "2026-01-01T00:00:00" }
  ],
  "sort": { "field": "CREATED_AT", "direction": "DESC" },
  "page": 0,
  "size": 20
}
~~~

Do not accept Object value and blindly trust client data. Before building a query, validate:

1. field exists in the enum/allowlist.
2. operator is allowed for that field.
3. value has a type compatible with the field.
4. For IN, values is a non-empty list and every element has the right type.
5. For BETWEEN, both endpoints are present and in valid order.
6. Filter count, string lengths, and list sizes stay within bounds.

Example operator model:

~~~java
public enum FilterOperator {
    EQ, IN, GTE, LTE, BETWEEN, CONTAINS, IS_NULL, IS_NOT_NULL
}
~~~

A server configuration can define:

~~~java
public record FieldRule(
    String sqlColumn,
    Class<?> valueType,
    Set<FilterOperator> allowedOperators
) {}

private static final Map<OrderFilterField, FieldRule> RULES = Map.of(
    OrderFilterField.STATUS,
    new FieldRule(
        "o.status",
        String.class,
        Set.of(FilterOperator.EQ, FilterOperator.IN)
    ),
    OrderFilterField.CUSTOMER_ID,
    new FieldRule(
        "o.customer_id",
        Long.class,
        Set.of(FilterOperator.EQ, FilterOperator.IN)
    ),
    OrderFilterField.CREATED_AT,
    new FieldRule(
        "o.created_at",
        LocalDateTime.class,
        Set.of(
            FilterOperator.GTE,
            FilterOperator.LTE,
            FilterOperator.BETWEEN
        )
    )
);
~~~

sqlColumn strings are server-defined constants. Never pass request field values into sqlColumn.

## 7. Building Safe Dynamic SQL with NamedParameterJdbcTemplate

When you need flexible operators, complex ORs, or queries returning projections, Spring JDBC can be used. The key is concatenating only server-controlled SQL fragments while binding every value via MapSqlParameterSource.

Simple example for a filter condition:

~~~java
private static String columnFor(OrderFilterField field) {
    return switch (field) {
        case STATUS -> "o.status";
        case CUSTOMER_ID -> "o.customer_id";
        case CREATED_AT -> "o.created_at";
        case TOTAL_AMOUNT -> "o.total_amount";
    };
}

private static String operatorSql(FilterOperator operator) {
    return switch (operator) {
        case EQ -> "=";
        case GTE -> ">=";
        case LTE -> "<=";
        default -> throw new IllegalArgumentException(
            "Operator is not supported for this expression");
    };
}
~~~

Builder:

~~~java
List<String> predicates = new ArrayList<>();
MapSqlParameterSource params = new MapSqlParameterSource();

for (int i = 0; i < request.filters().size(); i++) {
    FilterCondition filter = request.filters().get(i);
    FieldRule rule = RULES.get(filter.field());

    if (rule == null ||
            !rule.allowedOperators().contains(filter.operator())) {
        throw new IllegalArgumentException("Unsupported filter");
    }

    String column = columnFor(filter.field());
    String parameter = "p" + i;
    String operator = operatorSql(filter.operator());

    predicates.add(column + " " + operator + " :" + parameter);
    params.addValue(parameter, convertAndValidate(filter, rule));
}

String where = predicates.isEmpty()
    ? ""
    : " WHERE " + String.join(" AND ", predicates);

String sql = """
    SELECT o.id, o.customer_id, o.status, o.created_at
    FROM sales_orders o
    """ + where + """
    ORDER BY o.created_at DESC, o.id DESC
    """;
~~~

This is an illustrative skeleton; FilterCondition, convertAndValidate, and request checks must be implemented for your actual DTOs and types. columnFor and operatorSql return strictly server-defined strings. Parameter names are server-generated (p0, p1...), while values are bound.

Never allow arbitrary operators like = 1 OR 1=1 -- into operatorSql. Never allow arbitrary fields like o.status) OR ... into columnFor. Both safeguards are just as critical as parameter binding.

### IN Requires List Handling

NamedParameterJdbcTemplate can expand collections for IN clauses:

~~~java
predicates.add(column + " IN (:statuses)");
params.addValue("statuses", List.of("OPEN", "CONFIRMED"));
~~~

Empty lists must be handled before building SQL. Depending on your API contract, either reject the request with a validation error or short-circuit to an empty result; never allow IN () to be generated, as syntax support is inconsistent across databases.

Cap list sizes to avoid queries with excessive bind parameters. For very large lists, consider temporary tables, table-valued parameters (if supported by the DB), batching, or an appropriate join strategy.

## 8. NULL Requires Dedicated Operators

In SQL, NULL cannot be matched using = NULL or <> NULL. Those comparisons evaluate to UNKNOWN rather than TRUE or FALSE.

Wrong:

~~~sql
WHERE shipped_at = NULL
~~~

Right:

~~~sql
WHERE shipped_at IS NULL
~~~

For generic filters, define IS_NULL and IS_NOT_NULL operators that take no value:

~~~java
String predicate = switch (filter.operator()) {
    case IS_NULL -> column + " IS NULL";
    case IS_NOT_NULL -> column + " IS NOT NULL";
    default -> column + " " + operatorSql(filter.operator())
        + " :" + parameter;
};
~~~

Do not create a bind parameter for IS NULL. For the remaining operators, reject null values unless the API contract explicitly defines their meaning.

Distinguish:

| Input | Meaning |
|---|---|
| Omit shippedAt filter | Add no condition on shippedAt |
| IS_NULL | Return only rows with shipped_at IS NULL |
| IS_NOT_NULL | Return only rows with shipped_at IS NOT NULL |
| EQ with date value | Compare for equality with a specific timestamp |

Do not conflate "no filter" with "match NULL rows"; the two requirements are distinct.

## 9. LIKE, CONTAINS, and Wildcard Characters

Bind parameters prevent values from becoming SQL syntax, yet with LIKE, % and _ still act as wildcards. While not SQL injection, this can widen search results beyond what the user intended.

If CONTAINS must search for a literal string, escape wildcard characters before wrapping with % on both ends. Choose an explicit escape character such as !:

~~~java
private static String containsPattern(String input) {
    String escaped = input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
    return "%" + escaped + "%";
}
~~~

SQL:

~~~sql
WHERE c.display_name LIKE :pattern ESCAPE '!'
~~~

Bind:

~~~java
params.addValue("pattern", containsPattern(userInput));
~~~

If a product wants users to supply wildcards intentionally, document those semantics and restrict usage appropriately. Do not confuse LIKE with full-text search; on large datasets, %term% rarely uses standard B-tree indexes efficiently and may require full-text indexes or a search engine.

## 10. Controlling Sort Field Names

Sorting is a common source of risk because column names and ASC/DESC are part of SQL structure. Never do:

~~~java
String sql = "SELECT ... ORDER BY "
    + request.sortBy() + " " + request.direction();
~~~

Convert the request into an enum and map it:

~~~java
private static String sortColumn(OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> "o.created_at";
        case STATUS -> "o.status";
        case CUSTOMER_ID -> "o.customer_id";
        case TOTAL_AMOUNT -> "o.total_amount";
    };
}

private static String sortDirection(SortDirection direction) {
    return switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };
}
~~~

After validation:

~~~java
String orderBy = " ORDER BY "
    + sortColumn(request.sortBy()) + " "
    + sortDirection(request.direction())
    + ", o.id DESC";
~~~

Here the concatenated strings are identifiers and keywords **chosen by the server via switch**, not free-form client strings. Filter values remain bound via parameters as usual.

With Spring Data Sort, also allowlist properties:

~~~java
Sort sort = Sort.by(
    new Sort.Order(direction, toOrderProperty(sortField)),
    Sort.Order.desc("id")
);
~~~

Never pass Sort.by(request.sortBy()) directly when sortBy is an arbitrary string. Sort accepts property paths; allowing clients to pass unvalidated paths can expose internal fields, trigger mapping errors, or produce unintended queries.

## 11. Do Not Let Clients Choose Arbitrary Property Paths

Some APIs allow fields such as:

~~~text
sortBy=customer.address.city
~~~

Nested property paths can expand query scope and leak unintended data. In Spring Data JDBC, aggregate relationships do not behave like arbitrary lazy ORM paths; even so, accepting unrestricted paths is an unsafe, hard-to-maintain API design.

Publish only fields required for the use case. For example:

| Client Key | Allowed Property | Sortable? |
|---|---|---|
| createdAt | createdAt | Yes |
| status | status | Yes |
| customerId | customerId | Yes |
| internalNote | Not published | No |
| customer.passwordHash | Not published | No |

Do not use reflection to access any client-requested field (getDeclaredField, BeanWrapper with arbitrary names) and turn it into a query condition. Reflection is not a substitute for an allowlist.

## 12. Combining AND/OR and Capping Complexity

A filter can have multiple conditions. Example:

~~~sql
WHERE status = :status
  AND customer_id = :customerId
  AND (created_at >= :fromTime OR priority = :priority)
~~~

When permitting AND/OR groups:

- Define a bounded filter structure; never accept raw SQL fragments or arbitrary expressions.
- Allow only published fields and operators.
- Use parentheses to preserve logical meaning.
- Limit condition count, nesting groups, and expression depth.
- Validate data types per field.

Do not convert JSON filters to SQL by directly concatenating field, operator, and value. A parser must transform every node into a validated structure before building Criteria or SQL.

Example simple tree model:

~~~java
public sealed interface FilterNode
        permits FilterGroup, FilterCondition {}

public record FilterGroup(
    LogicalOperator operator,
    List<FilterNode> children
) implements FilterNode {}

public record FilterCondition(
    OrderFilterField field,
    FilterOperator operator,
    Object value
) implements FilterNode {}

public enum LogicalOperator {
    AND, OR
}
~~~

Object value here is only a generic transport shape. Before building the query, the parser must convert it to the concrete type dictated by OrderFilterField and reject any mistyped value. Never pass this raw object straight into the persistence layer.

## 13. Filters Must Respect Access Permissions

Field and operator allowlists protect query structure, but they are not enough to ensure users see only data they are authorized to view.

For example, a user may view only Orders belonging to their own Customer. The server must enforce the access-scope condition from the authenticated identity:

~~~java
Criteria criteria = Criteria.where("customerId")
    .is(currentUserCustomerId);

if (filter.status() != null) {
    criteria = criteria.and("status").is(filter.status());
}
~~~

currentUserCustomerId must come from the authenticated security context/session, never trusting a client-supplied customerId to determine authorization. If a user can access multiple Customers, the server loads the permitted ID list or applies the appropriate authorization predicate.

Rules:

- Client-requested filters only narrow results within the permitted scope.
- Tenant/owner conditions must be added by the server.
- Never allow clients to bypass or override authorization conditions.
- Never return sensitive fields simply because a client listed them in filters/sorts.

## 14. Pagination and Resource Control

Dynamic queries must limit result sizes and enforce stable sorting:

~~~java
int page = validatedPage(request.page());
int size = validatedSize(request.size());
long offset = (long) page * size;

Query query = Query.query(criteria)
    .sort(sort)
    .limit(size)
    .offset(offset);
~~~

When using custom SQL, LIMIT/OFFSET or the corresponding pagination clause must be built from validated integers. Use long when computing offset to avoid 32-bit integer overflow.

Additional safeguards:

- Cap maximum page size.
- Cap maximum date search ranges if reports can scan large datasets.
- Cap filter counts and IN list sizes.
- Configure appropriate query timeouts.
- Add indexes supporting common filter and sort conditions.
- Consider keyset pagination when offsets are deep or data changes frequently.

Never allow clients to trigger an unbounded query simply by omitting page/size. Enforce defaults and maximums on the server.

## 15. Complete Service Example with Fixed Filters

The following example uses JdbcAggregateTemplate and fixed properties. It demonstrates combining validation, Criteria, and a sort allowlist in one use case:

~~~java
package com.example.sales.order;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderSearchService {

    private static final int DEFAULT_SIZE = 20;
    private static final int MAX_SIZE = 100;

    private final JdbcAggregateTemplate template;

    public OrderSearchService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional(readOnly = true)
    public List<Order> search(
            String status,
            Long customerId,
            Integer requestedPage,
            Integer requestedSize,
            OrderSortField requestedSort,
            SortDirection requestedDirection) {

        int page = requestedPage == null ? 0 : requestedPage;
        int size = requestedSize == null ? DEFAULT_SIZE : requestedSize;

        if (page < 0) {
            throw new IllegalArgumentException("Invalid page");
        }
        if (size < 1 || size > MAX_SIZE) {
            throw new IllegalArgumentException("Invalid page size");
        }
        if (customerId != null && customerId <= 0) {
            throw new IllegalArgumentException("Invalid customer ID");
        }

        Criteria criteria = null;
        if (status != null) {
            if (!List.of("DRAFT", "OPEN", "CONFIRMED", "CANCELLED")
                    .contains(status)) {
                throw new IllegalArgumentException("Invalid status");
            }
            criteria = append(criteria,
                Criteria.where("status").is(status));
        }
        if (customerId != null) {
            criteria = append(criteria,
                Criteria.where("customerId").is(customerId));
        }

        Sort.Direction direction =
            requestedDirection == SortDirection.ASC
                ? Sort.Direction.ASC
                : Sort.Direction.DESC;

        OrderSortField sortField = requestedSort == null
            ? OrderSortField.CREATED_AT
            : requestedSort;

        String property = switch (sortField) {
            case CREATED_AT -> "createdAt";
            case STATUS -> "status";
            case CUSTOMER_ID -> "customerId";
        };

        Sort sort = Sort.by(
            new Sort.Order(direction, property),
            Sort.Order.desc("id")
        );

        Query query = criteria == null
            ? Query.empty()
            : Query.query(criteria);

        query = query.sort(sort)
            .limit(size)
            .offset((long) page * size);

        Iterable<Order> result = template.findAll(query, Order.class);
        List<Order> orders = new ArrayList<>();
        result.forEach(orders::add);
        return orders;
    }

    private static Criteria append(Criteria current, Criteria next) {
        return current == null ? next : current.and(next);
    }
}
~~~

OrderSortField in this example includes only fields actually permitted. If the entity does not have createdAt, status, or customerId properties, adjust the enum and mapping to match your actual model. The example does not accept arbitrary property names from requests.

If the application needs to return hasNext, total count, or DTOs instead of List<Order>, construct the appropriate response. Query.limit/offset alone does not create pagination metadata like Slice/Page.

## 16. Safe Dynamic SQL Example for Filters and Sorting

For reports needing flexible filter fields/operators, the server can construct SQL clauses from allowlists:

~~~java
String column = switch (filter.field()) {
    case STATUS -> "o.status";
    case CUSTOMER_ID -> "o.customer_id";
    case CREATED_AT -> "o.created_at";
};

String operator = switch (filter.operator()) {
    case EQ -> "=";
    case GTE -> ">=";
    case LTE -> "<=";
    default -> throw new IllegalArgumentException("Unsupported operator");
};

String parameterName = "filterValue";
String predicate = column + " " + operator + " :" + parameterName;

MapSqlParameterSource parameters = new MapSqlParameterSource()
    .addValue(parameterName, typedValue);

String sortColumn = switch (sortField) {
    case CREATED_AT -> "o.created_at";
    case STATUS -> "o.status";
    case CUSTOMER_ID -> "o.customer_id";
};

String sortDirection = direction == SortDirection.ASC ? "ASC" : "DESC";

String sql = """
    SELECT o.id, o.customer_id, o.status, o.created_at
    FROM sales_orders o
    WHERE %s
    ORDER BY %s %s, o.id DESC
    """.formatted(predicate, sortColumn, sortDirection);
~~~

In this example, column, operator, sortColumn, and sortDirection all come from server-side switch expressions. typedValue is validated according to field and bound into parameters. Never replace switch with filter.field().toString() or request.sortBy().

When multiple filters are used, generate server-assigned parameter names (p0, p1...) and add each value to MapSqlParameterSource. Avoid reusing the same parameter name for conditions that hold different values.

## 17. Testing Filters and Allowlists

Test both valid inputs and rejected inputs:

| Input | Expected Outcome |
|---|---|
| status=OPEN | Parsed and filtered by OPEN status |
| customerId=101 | Parsed as Long and bound |
| sortBy=CREATED_AT | Mapped to allowed property/column |
| direction=DESC | Converted to DESC sort direction |
| sortBy=passwordHash | Rejected because it is not in allowlist |
| field=customer.passwordHash | Rejected unpublished property path |
| operator=DROP_TABLE | Rejected unsupported operator |
| customerId=abc | Rejected with type parse error |
| page=-1 | Rejected negative page |
| size=100000 | Rejected or capped per API contract |
| IN with empty list | Rejected or returns empty per defined rule |
| IS_NULL | Generates IS NULL condition, does not bind = NULL |
| LIKE string with %/_ | Escaped if contract specifies literal search |

Useful security tests:

- Send SQL-like strings in filter values and verify they are bound strictly as data.
- Send unknown column names in field/sort and verify requests are rejected before building SQL.
- Send invalid operators and verify those strings never appear in SQL.
- Send sort directions other than ASC/DESC and verify rejection.
- Send valid filters belonging to another Customer and verify owner/tenant conditions still apply.

Do not merely test that the query succeeds without throwing; verify it never returns data outside the authorized scope.

## 18. Common Design Mistakes

| Mistake | Risk / Consequence | Fix |
|---|---|---|
| Concatenating client field names into SQL | SQL injection via identifiers or unexpected queries | Allowlist and map via enum/switch |
| Binding column names with :column | Database treats it as a literal value, not an identifier | Use server-side fixed identifiers |
| Calling Sort.by(request.sortBy()) unchecked | Clients can request unpublished properties | Map sort fields from an enum |
| Allowing free-form string operators | Allows injecting SQL syntax | Use enum and switch to fixed operators |
| Using Object value without parsing | Type mismatches, mapping failures, or wrong comparison logic | Parse according to field type and validate |
| Using = NULL | Does not match NULL rows as expected | Use IS NULL/IS NOT NULL |
| IN with empty list | Invalid SQL or unclear semantics | Reject or return empty per contract |
| Not escaping LIKE wildcards | Results broader than user intended | Escape %, _ when literal search is intended |
| Allowing arbitrary property paths | Exposes internal fields and creates complex uncontrollable queries | Publish explicit fields in an allowlist |
| Not capping page size / filter count | Resource exhaustion or overly complex queries | Enforce server-side limits |
| Trusting client customerId for authorization | Enables accessing other users' data | Obtain owner/tenant from security context |
| Sharing exact API, property, and column names without mapping | Confusion when schema or domain changes | Decouple API keys, Java properties, and SQL identifiers |

## 19. Practice Exercises

1. Create OrderSearchRequest with status, customerId, date range, sort field, direction, page, and size.
2. Create enum OrderSortField allowing only CREATED_AT, STATUS, and CUSTOMER_ID.
3. Write a function mapping the enum to Java properties and apply Sort with ID as a tie-breaker.
4. Use Criteria to add conditions only when their corresponding filter has a value.
5. Add validation checking createdFrom <= createdTo, positive customerId, and max page size 100.
6. Design FilterField, FilterOperator, and a rule table for field/operator/type.
7. Use NamedParameterJdbcTemplate to build dynamic SQL, concatenating only allowlisted identifiers/operators and binding all values.
8. Add IN, IS_NULL, IS_NOT_NULL, and CONTAINS; define explicit behavior for empty lists and wildcards.
9. Send sortBy=customer.passwordHash and verify the server rejects it.
10. Send SQL syntax inside a filter value and verify it is treated purely as data.
11. Add a tenant/owner condition sourced from the security context and verify clients cannot override it.
12. Write tests for mistyped filters, invalid operators, invalid date ranges, and oversized page sizes.

## 20. Takeaways

Designing safe dynamic queries starts by separating **data values** from **query structure**. Filter values are parsed, validated, and bound as parameters. Field names, properties, SQL columns, operators, and sort directions must be selected from server-defined allowlists.

With Spring Data JDBC, use Criteria/Query when filters align with aggregate property mappings; use NamedParameterJdbcTemplate when complex dynamic SQL or dedicated projections are needed. In both cases, never pass raw client-supplied field names directly to persistence APIs. Combine allowlists with type validation, resource bounds, authorization predicates, and explicit handling of NULL/IN/LIKE so filters stay both flexible and tightly controlled.
