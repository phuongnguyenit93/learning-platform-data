# Building Conditions from Optional Filters Without Unintended Query Expansion

In a Spring Data Relational R2DBC application, search screens often let users enter several optional filters: name, status, time range, assignee, or a list of IDs. A user might provide just one filter, combine multiple filters, or leave some fields blank.

Queries must be constructed so that each filter affects only the exact scope of data requested by the user. An inadvertently skipped condition can broaden results beyond expectations. For read queries, this bug can expose out-of-scope data. For UPDATE or DELETE, the consequence can be bulk modification of records.

The core principle is: **clearly define the meaning of each filter state, append only permitted predicates, bind values instead of concatenating inputs into SQL, and validate query scope before execution**.

## 1. What Are Optional Filters?

Suppose a customer search screen has the following fields:

- Name or partial name.
- Active status.
- Assignee.
- Creation date from and to.
- A list of customer IDs.

A user might filter solely by status, or combine status with creation date. The application needs to generate the corresponding WHERE clause.

Example filtering only by status:

~~~sql
SELECT id, name, status
FROM customer
WHERE status = :status;
~~~

When filtering by both status and assignee:

~~~sql
SELECT id, name, status
FROM customer
WHERE status = :status
  AND owner_id = :ownerId;
~~~

When filtering only by creation date:

~~~sql
SELECT id, name, status
FROM customer
WHERE created_at >= :createdFrom;
~~~

Unprovided conditions do not appear in WHERE. However, omitting a condition widens the result scope. Therefore, the application must identify which fields are genuinely optional and which are mandatory conditions such as tenant, organization, or access control.

## 2. Distinguishing Absent, Null, Empty, False, and 0

A common mistake is treating all "contentless" values alike. In reality, they can carry distinct meanings.

| Input state | Example | Possible meaning |
|---|---|---|
| Field omitted | No status key | User did not request filtering by status |
| Null sent | status = null | May mean no filter, or request to find SQL NULL values depending on contract |
| Empty string | name = "" | Usually normalized to no filter; occasionally searches for empty string |
| Empty list | ownerIds = [] | May mean no owner selected, i.e., zero results |
| Boolean false | active = false | Valid filter value, not a missing state |
| Number 0 | priority = 0 | Can be a valid filter value |

Avoid writing conditions based on generic truthy/falsy checks. For example, writing:

~~~java
if (filter.active()) {
    // add predicate
}
~~~

causes false to be skipped, even when the user wants to find inactive customers.

For optional Booleans, use the wrapper type:

~~~java
if (filter.active() != null) {
    // false is still added to the query and bound
}
~~~

Similarly, for numbers that can equal 0, check against null instead of greater-than-0 if 0 is a valid value.

### Choosing a Clear API Convention

A common convention:

- Omitted field or null sent: do not apply the corresponding predicate.
- Whitespace-only string: normalize to no filter.
- Boolean false and number 0: remain valid filter values.
- Null list: do not apply list filter.
- Empty list: return no results, or reject input per the API contract.

If searching for rows with an SQL NULL column is needed, express that intent explicitly—for instance via a dedicated filter mode or an isNull flag—and emit a column IS NULL predicate. You cannot use a column = :value comparison with a null value as a substitute for IS NULL, because in SQL comparing against NULL yields UNKNOWN.

## 3. Modeling Filters Before Generating SQL

Group search criteria into a dedicated data type instead of passing many loose parameters across layers.

~~~java
public record CustomerFilter(
    String name,
    String status,
    Boolean active,
    Long ownerId,
    Instant createdFrom,
    Instant createdTo,
    List<Long> ownerIds
) {
}
~~~

This type only describes search input. It is not a persistence entity and should not be saved to the customer table.

Before building the query, normalize and validate the filter:

- Trim name strings and convert blank strings to absent if the contract specifies so.
- Check that createdFrom is not after createdTo.
- Limit search string length.
- Limit the number of elements in ID lists.
- Validate that IDs and statuses fall within valid domains.
- Do not skip Boolean false or number 0.

Example validating a time range:

~~~java
if (filter.createdFrom() != null
        && filter.createdTo() != null
        && filter.createdFrom().isAfter(filter.createdTo())) {
    throw new IllegalArgumentException(
        "createdFrom must not be after createdTo"
    );
}
~~~

Validation should happen before calling the database. An invalid filter must not be silently ignored, since ignoring it can cause the query to return more data than intended.

## 4. Composing Predicates with AND

In many search screens, independent filters combine with AND: a row must satisfy all provided conditions.

For example:

~~~sql
SELECT id, name, status
FROM customer
WHERE status = :status
  AND active = :active
  AND created_at >= :createdFrom;
~~~

If the user sends only status and active, the created_at predicate is not added. Do not create placeholders for every filter and bind null indiscriminately.

A controllable approach is maintaining separately:

- A list of fixed SQL clauses generated by the application.
- A map holding parameter names and values to bind.

Then join predicates with AND and bind each value.

## 5. DatabaseClient Example with Optional Filters

The following example builds a SELECT statement from filters. The tenant condition is mandatory, while name, status, active, owner, and timestamps are optional.

~~~java
public Flux<CustomerSummary> search(
        Long tenantId,
        CustomerFilter filter) {

    List<String> predicates = new ArrayList<>();
    Map<String, Object> parameters = new LinkedHashMap<>();

    // Mandatory scope condition, must never be omitted.
    predicates.add("c.tenant_id = :tenantId");
    parameters.put("tenantId", tenantId);

    if (filter.name() != null && !filter.name().isBlank()) {
        predicates.add("LOWER(c.name) LIKE :name");
        parameters.put(
            "name",
            "%" + filter.name().trim().toLowerCase(Locale.ROOT) + "%"
        );
    }

    if (filter.status() != null) {
        predicates.add("c.status = :status");
        parameters.put("status", filter.status());
    }

    if (filter.active() != null) {
        predicates.add("c.active = :active");
        parameters.put("active", filter.active());
    }

    if (filter.ownerId() != null) {
        predicates.add("c.owner_id = :ownerId");
        parameters.put("ownerId", filter.ownerId());
    }

    if (filter.createdFrom() != null) {
        predicates.add("c.created_at >= :createdFrom");
        parameters.put("createdFrom", filter.createdFrom());
    }

    if (filter.createdTo() != null) {
        predicates.add("c.created_at < :createdTo");
        parameters.put("createdTo", filter.createdTo());
    }

    String sql =
        "SELECT c.id, c.name, c.status " +
        "FROM customer c " +
        "WHERE " + String.join(" AND ", predicates) +
        " ORDER BY c.created_at DESC";

    DatabaseClient.GenericExecuteSpec spec =
        databaseClient.sql(sql);

    for (Map.Entry<String, Object> entry : parameters.entrySet()) {
        spec = spec.bind(entry.getKey(), entry.getValue());
    }

    return spec.map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("status", String.class)
    )).all();
}
~~~

In this example:

1. The tenant predicate is always added, guaranteeing the query never crosses tenant boundaries.
2. Each optional filter adds a predicate only when a valid value is present.
3. Filter values are placed in a map and bound separately.
4. Only code-controlled SQL clauses are concatenated into the string.
5. The query returns a Flux because multiple rows may match.

This is an implementation pattern. Imports, CustomerSummary type, DatabaseClient, and repository belong to the specific application. Named parameter syntax is handled by Spring DatabaseClient according to parameter expansion rules and the corresponding R2DBC driver.

### Why Not Write One Fixed SQL Statement for All Filters?

A common pattern is:

~~~sql
SELECT id, name
FROM customer
WHERE (:status IS NULL OR status = :status)
  AND (:ownerId IS NULL OR owner_id = :ownerId);
~~~

This pattern can work in some cases, but has drawbacks to consider:

- Nulls must be bound with the proper driver type.
- Predicates are always present, even when filters are not supplied.
- OR expressions can make it harder for optimizers to utilize indexes on some databases.
- It fails to clearly distinguish "skip filter" from "find rows where column is NULL".
- With many filters, SQL bloats and becomes hard to read.

Dynamic predicate composition is usually clearer when there are many optional conditions. If using a fixed SQL statement, define null semantics clearly and measure execution plans on the target database.

## 6. Binding Values Instead of Concatenating Inputs into SQL

Never concatenate user data directly into SQL statements:

~~~java
String sql =
    "SELECT id, name FROM customer WHERE name = '" +
    request.name() + "'";
~~~

If input contains quotes or SQL syntax, the query can be altered unintentionally. This poses an SQL injection risk.

Use placeholders and bind:

~~~java
databaseClient.sql(
        "SELECT id, name FROM customer WHERE name = :name"
    )
    .bind("name", request.name())
    .map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("status", String.class)
    ))
    .all();
~~~

Bind parameters protect data values from being interpreted as SQL syntax. However, binding does not replace business validation and cannot be applied to every SQL construct.

### What Can and Cannot Be Bound

Typically bindable:

- Strings.
- Numbers.
- Booleans.
- Dates and times.
- UUIDs.
- Values supported by R2DBC driver codecs.

Cannot use bind parameters to replace:

- Table names.
- Column names.
- ASC or DESC keywords.
- SQL operators.
- Arbitrary ORDER BY fragments.

The following example does not work as expected:

~~~sql
SELECT * FROM customer ORDER BY :columnName;
~~~

The parameter here is a value, not an identifier. To sort dynamically by a field, pick from a fixed list of identifiers allowed by the application.

## 7. Building IN Clauses with Optional Lists

A filter may contain multiple IDs:

~~~java
List<Long> ownerIds = filter.ownerIds();
~~~

Do not assume you can bind an entire collection to one placeholder as though every R2DBC driver automatically expands lists for IN clauses. Create one bind marker per element or use an abstraction that supports collection expansion in your framework version.

Example creating indexed markers:

~~~java
if (filter.ownerIds() != null) {
    List<Long> ids = filter.ownerIds();

    if (ids.isEmpty()) {
        // Convention: an empty list means no owner is selected.
        predicates.add("1 = 0");
    } else {
        List<String> markers = new ArrayList<>();

        for (int i = 0; i < ids.size(); i++) {
            String parameterName = "ownerId" + i;
            markers.add(":" + parameterName);
            parameters.put(parameterName, ids.get(i));
        }

        predicates.add(
            "c.owner_id IN (" + String.join(", ", markers) + ")"
        );
    }
}
~~~

Placeholder names are generated from code-controlled indices. Actual ID values remain bound, never concatenated into SQL.

Clear semantics must be chosen for the list:

| ownerIds value | Meaning chosen in example |
|---|---|
| null | Do not apply owner filter |
| Empty list | No results, predicate always false |
| Non-empty | Return only owners in the list |

If the API defines an empty list as "no filter", implement that exact convention. Never let behavior depend accidentally on whether SQL emits IN () or whether the driver accepts that syntax.

Limit the number of elements in the list to avoid oversized SQL statements and exceeding database bind parameter limits.

## 8. Combining AND and OR Without Incorrect Scope Expansion

AND and OR operators have different precedence. When assembling dynamic conditions, missing parentheses can cause the query to return more rows than intended.

Suppose business logic wants customers belonging to the current tenant and satisfying either status ACTIVE or assigned to the current user.

Correct condition:

~~~sql
WHERE tenant_id = :tenantId
  AND (status = 'ACTIVE' OR owner_id = :currentUserId)
~~~

If written without parentheses:

~~~sql
WHERE tenant_id = :tenantId
  AND status = 'ACTIVE'
   OR owner_id = :currentUserId
~~~

Because AND is evaluated before OR, the second query is equivalent to:

~~~sql
WHERE (tenant_id = :tenantId AND status = 'ACTIVE')
   OR owner_id = :currentUserId
~~~

As a result, rows with owner_id matching the current user may be returned even if they belong to another tenant. This is a data scope expansion bug.

When building dynamic OR groups, always wrap the group in parentheses:

~~~java
predicates.add(
    "(c.status = :status OR c.owner_id = :ownerId)"
);
~~~

If an OR branch is optional, explicitly handle how the group is built when only one branch remains. Never leave an empty branch or drop parentheses in a way that alters outer conditions.

### Example of Intentional Grouping

~~~sql
WHERE tenant_id = :tenantId
  AND deleted = false
  AND (
       status = :status
       OR priority >= :minimumPriority
  )
  AND created_at >= :createdFrom
~~~

In this example, tenant and non-deleted checks are always mandatory. The OR group only governs the inner business rule; it cannot bypass tenant or deleted.

## 9. String Filters and Wildcard Characters

Parameterizing values prevents SQL injection, yet LIKE wildcard characters still retain search meaning:

- % matches a string of any length.
- _ matches a single character.

If a user inputs %, a LIKE query can match very many rows. That is not SQL injection, though it may be unintended result expansion.

If the goal is literal string matching, escape %, _, and the escape character per database syntax, then add an appropriate ESCAPE clause. Escaping rules can differ across vendors, so verify against your dialect/database.

In addition:

- Normalize case according to business requirements.
- Limit input length.
- Consider collation and how the database compares Vietnamese diacritics.
- Do not add wildcards automatically if business logic requires exact matching.
- Avoid unintended empty-string searches turning into %%.

## 10. Dynamic Sorting and Pagination

Users may choose to sort by name, creation date, or status. Column names cannot be bound as values, so never concatenate raw sort strings from requests directly.

Use a whitelist:

~~~java
public enum CustomerSortField {
    NAME("c.name"),
    CREATED_AT("c.created_at"),
    STATUS("c.status");

    private final String sqlExpression;

    CustomerSortField(String sqlExpression) {
        this.sqlExpression = sqlExpression;
    }

    public String sqlExpression() {
        return sqlExpression;
    }
}
~~~

Sort direction should also come from an enum or validated boolean:

~~~java
String direction =
    requestedDirection == SortDirection.ASC ? "ASC" : "DESC";

String orderBy =
    sortField.sqlExpression() + " " + direction;
~~~

Only values taken from the whitelist are appended to SQL. Never use raw sort strings sent by clients.

For pagination:

- Cap maximum page size.
- Validate page and offset are non-negative.
- Use database-appropriate LIMIT/OFFSET syntax or a dialect-aware abstraction.
- Always include a deterministic ORDER BY, ideally adding ID as a tie-breaker.
- Never allow users to choose sort fields outside the permitted list.

A non-deterministic sort order can cause records to repeat or be skipped across pages when data changes.

## 11. Do Not Let Missing Filters Unintentionally Expand Queries

This point requires special care. When all optional filters are absent, the predicate list can become empty. If code concatenates strings like:

~~~java
String sql = "SELECT * FROM customer WHERE "
    + String.join(" AND ", predicates);
~~~

it can produce invalid SQL. Alternatively, omitting WHERE entirely results in querying the whole table. Sometimes a full-table query is valid, but it should not happen implicitly just because a user omitted filters.

Decide policy explicitly:

| Context | Behavior when no optional filter is provided |
|---|---|
| Public paginated list | May allow listing within permitted scope |
| Large dataset search | Require at least one criterion or tight limits |
| Multi-tenant data | Always apply mandatory tenant predicate |
| User-scoped data | Always apply access-control predicate |
| UPDATE or DELETE | Do not execute if mandatory scope conditions are missing |

Example guarding a search query:

~~~java
if (selectedOptionalFilterCount == 0
        && !filter.allowUnfilteredSearch()) {
    return Flux.error(
        new IllegalArgumentException(
            "At least one search filter is required"
        )
    );
}
~~~

If unfiltered queries are permitted, require an explicit choice or enforce pagination/result limits and access-control predicates.

### Mandatory Conditions Must Be Separated from Optional Ones

For instance, tenant_id must not be treated as an optional filter if users may only view their own tenant's data:

~~~java
predicates.add("c.tenant_id = :tenantId");
parameters.put("tenantId", authenticatedTenantId);
~~~

The tenant value must come from a verified authentication context, not by trusting an arbitrary tenantId in the client's query string. User-supplied filters may only narrow scope within the dataset they are authorized to access.

## 12. Dynamic Filters for UPDATE and DELETE Need Stricter Guards

With SELECT, dropping all filters may return all data within authorized scope. With UPDATE or DELETE, dropping a predicate can alter or delete records in bulk.

Dangerous example:

~~~java
String sql = "DELETE FROM customer";

if (filter.status() != null) {
    sql += " WHERE status = :status";
}
~~~

If status is omitted, the statement deletes the entire customer table.

Build mandatory conditions first:

~~~java
List<String> predicates = new ArrayList<>();
Map<String, Object> parameters = new LinkedHashMap<>();

predicates.add("tenant_id = :tenantId");
parameters.put("tenantId", tenantId);

if (filter.customerId() == null
        && filter.status() == null) {
    return Mono.error(
        new IllegalArgumentException(
            "A customer ID or status filter is required"
        )
    );
}

if (filter.customerId() != null) {
    predicates.add("id = :customerId");
    parameters.put("customerId", filter.customerId());
}

if (filter.status() != null) {
    predicates.add("status = :status");
    parameters.put("status", filter.status());
}

String sql =
    "DELETE FROM customer WHERE " +
    String.join(" AND ", predicates);
~~~

This example illustrates the guard principle. Execution still requires binding all parameters and checking affected row counts. Dangerous operations should also have business limits, auditing, and appropriate confirmation mechanisms.

Never rely on a client-supplied allowAll flag to bypass all conditions. If an administrative bulk action exists, that permission must be enforced separately at the authorization layer with a distinct API/command.

## 13. Dynamic Queries via Repository, Criteria, and DatabaseClient

Multiple abstraction levels exist for constructing queries:

| Approach | When suitable | Considerations |
|---|---|---|
| Derived query method | Few stable condition combinations | Many filters can cause method count to explode |
| @Query | Fixed SQL, easy to express | Complex optional filters can be hard to represent |
| R2dbcEntityTemplate and Criteria | Dynamic queries needing entity mapping and supported predicates | Specific APIs/operators depend on Spring Data version |
| DatabaseClient | Dynamic SQL, joins, projections, and custom queries | Application manages SQL structure, binding, and mapping |

Derived query example:

~~~java
Flux<Customer> findByStatusAndActive(
    String status,
    boolean active
);
~~~

This is a straightforward choice when both conditions are mandatory. If each condition can be independently absent across many combinations, creating numerous methods like findByStatus, findByOwner, findByStatusAndOwner... becomes hard to maintain.

With Spring Data Relational's Criteria or Query abstraction, supported conditions can be assembled per filter. Use the exact API of your deployed Spring Data version and check which operators the dialect/database supports. For custom SQL with multiple joins or specialized logic, DatabaseClient gives clearer statement control.

## 14. Data Scope Control and Security

Optional filters are part of a query, but must not be used in place of authorization. A client sending ownerId or tenantId does not prove permission to read the corresponding data.

Divide conditions into two groups:

**Mandatory scope conditions**

- Current user's tenant or organization.
- Ownership or permitted data scope.
- Soft-delete condition if the application always hides deleted records.
- System data partitioning constraints.

**Optional search conditions**

- Name, status, creation date.
- Assignee ID.
- Value ranges or category groups.
- Search keywords.

Always join mandatory scope conditions with AND outside user-chosen OR groups. Never let an OR predicate nullify tenant or access restrictions.

For example:

~~~sql
WHERE tenant_id = :tenantId
  AND deleted_at IS NULL
  AND (
       status = :status
       OR owner_id = :ownerId
  )
~~~

If a query has multiple condition groups, write each group clearly with parentheses and name variables after their intent. Avoid creating a long expression with deeply nested ORs that are hard to reason about.

## 15. Performance of Dynamic Queries

Dynamic queries include only necessary predicates in SQL, yet the number of filter combinations can be large. Points to consider:

- Create indexes on columns frequently filtered and sorted based on actual workload.
- Do not mechanically create an index for every filter combination.
- Inspect execution plans for common and high-cost query combinations.
- Avoid applying functions to columns in WHERE if that prevents normal index usage, such as LOWER(column), unless a matching functional index exists.
- Cap page sizes and IN lists.
- Select only needed columns instead of SELECT *.
- Consider dedicated queries for special combinations instead of one overly complex catch-all SQL.
- Use metrics/logs to observe which filters users actually apply.

An SQL query with fewer predicates is not always faster. Speed depends on selectivity, indexes, statistics, joins, row counts, and the database optimizer.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using if(boolean) for optional Booleans | Filter value false is skipped | Check against null |
| Using if(number > 0) when 0 is valid | Filter value 0 is skipped | Check null and validate separately |
| Treating empty list like null list | Returns too much data or emits IN () | Define separate semantics for null and empty |
| Concatenating inputs into SQL | SQL injection | Bind all values |
| Binding column names or ORDER BY | Does not act as an identifier | Use a whitelist |
| Joining OR without parentheses | Bypasses tenant or mandatory conditions | Group OR inside parentheses |
| Omitting WHERE when no filter is given | Unintended full-table SELECT | Require filters, pagination, or explicit option |
| UPDATE/DELETE without guards | Bulk modification/deletion | Mandatory conditions and pre-execution checks |
| Using null to search for SQL NULL | Predicate yields unexpected results | Use explicit IS NULL |
| LIKE with uncontrolled wildcards | Unintended broad results | Escape wildcards when literal matching is needed |
| Forgetting tenant predicate | Cross-tenant access | Add scope condition from auth context |
| Too many IN elements | Oversized SQL, exceeds bind limits | Cap size, batch, or use a database-appropriate strategy |

## 17. Workflow for Building a Safe Dynamic Query

You can follow this sequence for a search screen:

1. Identify mandatory filters and optional filters.
2. Explicitly define absent, null, empty string, empty list, false, and 0.
3. Normalize and validate inputs before generating SQL.
4. Add mandatory scope predicates such as tenant and access control.
5. Add optional predicates according to defined semantics.
6. Group AND/OR conditions with clear parentheses.
7. Bind all values; concatenate only identifiers or SQL fragments from a fixed whitelist.
8. Check the no-filter case and decide whether broad queries are permitted.
9. Apply pagination, limits, and deterministic ordering.
10. Test filter combinations, especially empty, false, 0, empty-list, and OR cases.

For UPDATE or DELETE, add a dedicated guard step rejecting the operation when safe scope conditions are missing. Never reuse a SELECT builder for mutations if that builder allows all optional predicates to disappear.

## 18. Key Takeaways

- Optional filters need clear semantics; null, empty string, empty list, false, and 0 are not inherently identical.
- Use wrapper Boolean and null checks to preserve false filter values.
- Assembling dynamic predicates via a condition list and bind map keeps SQL manageable.
- Concatenate only fixed SQL fragments controlled by code; never concatenate user input.
- Bind parameters are for values, not for substituting column names, table names, operators, or sort directions.
- For IN, explicitly define null list and empty list behavior; generate individual placeholders or use framework-supported expansion.
- Group OR clauses with parentheses and keep tenant/authorization predicates outside OR groups.
- Never let missing filters silently drop WHERE; decide explicitly when full-scope queries are allowed.
- UPDATE/DELETE must have guards and mandatory scope predicates to prevent unintended bulk changes.
- Use DatabaseClient for complex dynamic SQL; use repositories or Criteria when those abstractions adequately express requirements.
