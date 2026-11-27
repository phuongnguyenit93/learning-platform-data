# Grouping AND/OR Conditions by Search Requirements in Spring Data JDBC

## 1. Why Group Search Conditions?

A search screen typically has multiple optional filters. Users may enter a keyword, choose a status, date range, city, or product group. Not every filter always has a value; some filters also need to combine multiple choices with OR.

For example, a customer search request might mean:

- The customer belongs to the logged-in tenant.
- The customer is active.
- The keyword matches name **or** email **or** customer code.
- If the user selects a location, the customer belongs to the selected city **or** district.

Logical expression:

\[
tenant \land active \land (name \lor email \lor code) \land (city \lor district)
\]

If parentheses are omitted or conditions are combined incorrectly, the results can be broader than expected. For example:

~~~sql
WHERE tenant_id = :tenantId
  AND active = TRUE
  AND display_name LIKE :keyword
   OR email_address LIKE :keyword
~~~

In SQL, AND has higher precedence than OR. The expression above is equivalent to:

~~~sql
WHERE (tenant_id = :tenantId AND active = TRUE
       AND display_name LIKE :keyword)
   OR email_address LIKE :keyword
~~~

A customer in another tenant could still appear if their email matches the keyword. The right way is to group the OR choices in parentheses:

~~~sql
WHERE tenant_id = :tenantId
  AND active = TRUE
  AND (
      display_name LIKE :keyword
      OR email_address LIKE :keyword
  )
~~~

In Spring Data JDBC, you can build dynamic condition groups with Spring Data Relational's Criteria API, then pass Query to JdbcAggregateTemplate. When fully custom SQL is needed, you can use NamedParameterJdbcTemplate and construct parameterized predicate groups yourself.

## 2. What Do AND and OR Express?

- **AND** requires all combined conditions to be true.
- **OR** requires at least one condition in the group to be true.
- **NOT** negates a condition or group of conditions.

| Expression | Meaning |
|---|---|
| `status = 'ACTIVE' AND city = 'Hue'` | Customer is both active and in Hue |
| `city = 'Hue' OR city = 'Da Nang'` | Customer is in Hue or Da Nang |
| `tenant_id = ? AND (name LIKE ? OR email LIKE ?)` | Correct tenant and matching name or email |
| `(status = 'ACTIVE' OR status = 'PENDING') AND tenant_id = ?` | Either status while still belonging to the tenant |
| `NOT (status = 'DELETED' OR status = 'BLOCKED')` | Neither of the two excluded statuses |

In a search requirement, groups are typically combined with AND, while alternatives inside a group are combined with OR.

## 3. Derived Queries Fit Fixed Condition Combinations

Spring Data JDBC supports derived queries, where the framework parses repository method names to generate predicates:

~~~java
List<Customer> findByStatusAndCity(
        CustomerStatus status,
        String city
);

List<Customer> findByStatusOrCity(
        CustomerStatus status,
        String city
);

List<Customer> findByStatusAndCityOrStatusAndCity(
        CustomerStatus firstStatus,
        String firstCity,
        CustomerStatus secondStatus,
        String secondCity
);
~~~

This approach fits when the number of condition combinations is small and stable. However, when each request can toggle many filters on or off, the number of methods to define grows rapidly. With 6 optional filters, each either present or absent, the number of possible combinations is:

\[
2^6 = 64
\]

Do not create dozens of methods just to cover every combination. For dynamic conditions, build predicates at runtime using the Criteria API or custom SQL.

One note: derived queries use Java properties, such as `findByCustomerCode`. The Criteria API works with relational column names in query mapping. Use column names consistent with the schema and entity `@Column` mappings.

## 4. Criteria API in Spring Data Relational

Spring Data Relational provides `Criteria` and `Query` to express query conditions in Java. This is a suitable choice when you need to assemble AND/OR groups based on request filters.

Common imports:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
~~~

`Criteria.where("column")` starts a condition on a column. Comparisons such as `is`, `like`, `greaterThan`, `between`, and `isNull` create predicates. Conditions can be chained with `and(...)` and `or(...)`.

Example:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("city").is("Hue");
~~~

This condition corresponds to:

~~~sql
WHERE status = 'ACTIVE'
  AND city = 'Hue'
~~~

OR group:

~~~java
Criteria criteria = Criteria.where("city").is("Hue")
        .or("city").is("Da Nang");
~~~

Corresponds to:

~~~sql
WHERE city = 'Hue'
   OR city = 'Da Nang'
~~~

You can pass another Criteria into `and(...)` or `or(...)` to combine an entire group as a single logical unit. This is how parentheses are created for nested expressions.

## 5. Nesting an OR Group Inside an AND Condition

Suppose we need to find customers belonging to the current tenant, who are active, and whose name or email matches a keyword.

Desired SQL:

~~~sql
SELECT id, tenant_id, customer_code, display_name, email_address, status
FROM customers
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      display_name LIKE :pattern
      OR email_address LIKE :pattern
  );
~~~

Using Criteria:

~~~java
Criteria textMatch = Criteria.where("display_name").like(pattern)
        .or("email_address").like(pattern);

Criteria criteria = Criteria.where("tenant_id").is(tenantId)
        .and("status").is("ACTIVE")
        .and(textMatch);
~~~

Here `textMatch` is an independent OR group. When passed into `criteria.and(textMatch)`, the entire group must hold together with the tenant and status conditions.

The expression can be read structurally as:

~~~text
AND
├── tenant_id = tenantId
├── status = ACTIVE
└── OR
    ├── display_name LIKE pattern
    └── email_address LIKE pattern
~~~

Do not write three separate conditions and join them with OR at the top level, because that can drop the tenant or status constraint.

## 6. Multiple OR Choices and Multiple AND Groups

A real-world search can include several groups:

~~~text
tenant_id = current tenant
AND status = ACTIVE
AND (
    display_name contains keyword
    OR email_address contains keyword
    OR customer_code contains keyword
)
AND (
    city = cityFilter
    OR district = districtFilter
)
AND created_at >= fromDate
AND created_at < untilDate
~~~

Each group can be built separately:

~~~java
Criteria keywordGroup = Criteria.where("display_name").like(pattern)
        .or("email_address").like(pattern)
        .or("customer_code").like(pattern);

Criteria locationGroup = Criteria.where("city").is(city)
        .or("district").is(district);

Criteria criteria = Criteria.where("tenant_id").is(tenantId)
        .and("status").is("ACTIVE")
        .and(keywordGroup)
        .and(locationGroup)
        .and("created_at").greaterThanOrEquals(fromDate)
        .and("created_at").lessThan(untilDate);
~~~

Logical structure:

\[
tenant \land active \land (name \lor email \lor code)
\land (city \lor district) \land from \le createdAt < until
\]

In a real application, not every group is always present. If keyword is blank, omit the entire keywordGroup. If the user does not select a location, omit locationGroup. Never create comparisons against empty strings or unintended null values.

## 7. Building Dynamic Criteria from Optional Filters

Create a DTO describing the search request:

~~~java
import java.time.Instant;

public record CustomerSearchFilter(
        String status,
        String keyword,
        String city,
        String district,
        String postalCode,
        Instant createdFrom,
        Instant createdUntil,
        int limit
) {}
~~~

A custom repository can accept the filter, build Criteria, and use `JdbcAggregateTemplate`:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerSearchRepository {

    private final JdbcAggregateTemplate template;

    public CustomerSearchRepository(JdbcAggregateTemplate template) {
        this.template = template;
    }

    public List<Customer> search(
            UUID tenantId,
            CustomerSearchFilter filter
    ) {
        Criteria criteria = Criteria.where("tenant_id").is(tenantId);

        if (filter.status() != null && !filter.status().isBlank()) {
            criteria = criteria.and("status").is(filter.status());
        }

        if (filter.keyword() != null && !filter.keyword().isBlank()) {
            String pattern = "%" + filter.keyword().trim() + "%";

            Criteria keywordGroup =
                    Criteria.where("display_name").like(pattern)
                            .or("email_address").like(pattern)
                            .or("customer_code").like(pattern);

            criteria = criteria.and(keywordGroup);
        }

        if (filter.city() != null && !filter.city().isBlank()
                && filter.district() != null && !filter.district().isBlank()) {
            Criteria locationGroup =
                    Criteria.where("city").is(filter.city())
                            .or("district").is(filter.district());

            criteria = criteria.and(locationGroup);
        } else if (filter.city() != null && !filter.city().isBlank()) {
            criteria = criteria.and("city").is(filter.city());
        } else if (filter.district() != null && !filter.district().isBlank()) {
            criteria = criteria.and("district").is(filter.district());
        }

        if (filter.createdFrom() != null) {
            criteria = criteria.and("created_at")
                    .greaterThanOrEquals(filter.createdFrom());
        }

        if (filter.createdUntil() != null) {
            criteria = criteria.and("created_at")
                    .lessThan(filter.createdUntil());
        }

        int limit = Math.max(1, Math.min(filter.limit(), 200));
        Query query = Query.query(criteria).limit(limit);

        return template.findAll(query, Customer.class);
    }
}
~~~

The example starts with the mandatory tenant condition. Other conditions are added only when their filters contain valid values. This ensures every query remains scoped to the tenant even if the client sends no keyword.

`JdbcAggregateTemplate` executes the Query using the aggregate's metadata. Column names in Criteria must match the schema and the application's relational mapping; if the entity uses `@Column`, use the mapped column names accurately. Specific APIs may vary depending on the Spring Data JDBC version in use.

### 7.1. Why Start from Mandatory Conditions?

If you start from an optional filter and accidentally add no conditions, the application could query the entire table. In multi-tenant systems, the tenant condition should always be added before all client-provided filters.

Safe pattern:

~~~java
Criteria criteria = Criteria.where("tenant_id").is(authenticatedTenantId);

// Only add optional filters after the tenant condition.
if (status != null) {
    criteria = criteria.and("status").is(status);
}
~~~

`authenticatedTenantId` must come from the server-side security context or authenticated session. Never trust a tenant ID sent by the client without verifying access permissions.

### 7.2. Distinguishing an Omitted Filter from Matching NULL

These two cases have different meanings:

- `email == null` in a DTO may mean the user is not filtering by email.
- `email IS NULL` is a specific search condition.

If an API needs to support finding rows with NULL email, represent that intent explicitly (such as an `emailIsNull` flag) and add:

~~~java
criteria = criteria.and("email_address").isNull();
~~~

Do not interpret every null filter value as `IS NULL`; doing so would cause leaving a field blank to accidentally exclude most data.

## 8. Building an OR Group from a List of Conditions

Sometimes the number of OR choices is not fixed. For instance, a user selects multiple statuses, cities, or event types.

For a set of statuses, the simplest option is usually the `in` operator:

~~~java
Criteria criteria = Criteria.where("status").in(statuses);
~~~

This corresponds to `status IN (...)` and is usually clearer than chaining many OR conditions on the same column.

If OR conditions span multiple columns or each condition has a different value, you can collect a list of Criteria and combine them:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Criteria> alternatives = new ArrayList<>();

if (filter.city() != null && !filter.city().isBlank()) {
    alternatives.add(Criteria.where("city").is(filter.city()));
}

if (filter.district() != null && !filter.district().isBlank()) {
    alternatives.add(Criteria.where("district").is(filter.district()));
}

if (filter.postalCode() != null && !filter.postalCode().isBlank()) {
    alternatives.add(Criteria.where("postal_code").is(filter.postalCode()));
}

if (!alternatives.isEmpty()) {
    Criteria locationGroup = alternatives.get(0);

    for (int i = 1; i < alternatives.size(); i++) {
        locationGroup = locationGroup.or(alternatives.get(i));
    }

    criteria = criteria.and(locationGroup);
}
~~~

The locationGroup is added only when there is at least one choice. Never create an empty OR group. For a set of values on the same column, prefer `IN` because it is concise and expresses the intent directly.

## 9. Dynamic AND Condition Groups

Similarly, mandatory or optional conditions can be built by chaining `and(...)`:

~~~java
Criteria criteria = Criteria.where("tenant_id").is(tenantId);

if (filter.status() != null) {
    criteria = criteria.and("status").is(filter.status());
}

if (filter.createdFrom() != null) {
    criteria = criteria.and("created_at")
            .greaterThanOrEquals(filter.createdFrom());
}

if (filter.createdUntil() != null) {
    criteria = criteria.and("created_at")
            .lessThan(filter.createdUntil());
}
~~~

If all filters are supplied, the predicate is the intersection of all conditions. If a filter is omitted, its condition does not appear in the query.

Distinguish between omitting a filter and substituting a default value for it. For example, omitting status normally means no restriction on status; do not silently default to ACTIVE unless that is a product rule.

## 10. Executing with Query and JdbcAggregateTemplate

After building Criteria, wrap it in a Query:

~~~java
Query query = Query.query(criteria);
List<Customer> result = template.findAll(query, Customer.class);
~~~

You can add a result limit to avoid returning an overly large dataset:

~~~java
Query query = Query.query(criteria).limit(100);
~~~

For read-only queries, the service can mark the transaction read-only:

~~~java
@Service
public class CustomerSearchService {

    private final CustomerSearchRepository repository;

    public CustomerSearchService(CustomerSearchRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Customer> search(
            UUID tenantId,
            CustomerSearchFilter filter
    ) {
        return repository.search(tenantId, filter);
    }
}
~~~

If results need complex sorting, pagination, or projections, check the capabilities of Query in your version. When a query goes beyond what Criteria expresses comfortably, switch to custom SQL rather than building an unreadable Criteria tree.

## 11. When Custom SQL Is Needed: NamedParameterJdbcTemplate

Another option is building SQL predicates in code and binding all values via named parameters. This fits when you need dialect-specific SQL syntax, many parenthesized groups, or queries with complex joins.

Example:

~~~java
public List<Customer> search(UUID tenantId, CustomerSearchFilter filter) {
    StringBuilder sql = new StringBuilder("""
            SELECT id, tenant_id, customer_code, display_name,
                   email_address, status, city, district, created_at
            FROM customers
            WHERE tenant_id = :tenantId
            """);

    MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("tenantId", tenantId);

    if (filter.status() != null && !filter.status().isBlank()) {
        sql.append(" AND status = :status");
        params.addValue("status", filter.status());
    }

    if (filter.keyword() != null && !filter.keyword().isBlank()) {
        sql.append("""
                 AND (
                     display_name LIKE :pattern
                     OR email_address LIKE :pattern
                     OR customer_code LIKE :pattern
                 )
                """);

        params.addValue(
                "pattern",
                "%" + filter.keyword().trim() + "%"
        );
    }

    if (filter.createdFrom() != null) {
        sql.append(" AND created_at >= :createdFrom");
        params.addValue("createdFrom", filter.createdFrom());
    }

    if (filter.createdUntil() != null) {
        sql.append(" AND created_at < :createdUntil");
        params.addValue("createdUntil", filter.createdUntil());
    }

    sql.append(" ORDER BY created_at DESC, id DESC LIMIT :limit");
    params.addValue("limit", Math.max(1, Math.min(filter.limit(), 200)));

    return namedParameterJdbcTemplate.query(
            sql.toString(),
            params,
            customerRowMapper
    );
}
~~~

All appended SQL fragments are fixed strings controlled by code. User-supplied data is passed strictly through parameters such as `:status`, `:pattern`, and `:createdFrom`.

**Never concatenate user values directly into SQL.** Prepared/named parameters protect data values, but they cannot bind table names, column names, or SQL keywords. If dynamic sorting is needed, map the client's choice through an allowlist:

~~~java
String orderBy = switch (requestedSort) {
    case "name" -> "display_name";
    case "createdAt" -> "created_at";
    default -> "id";
};
~~~

Only fixed fragments from the allowlist are placed into the SQL statement. Never put requestedSort directly in ORDER BY.

### 11.1. When to Choose Criteria vs. SQL?

| Need | Suitable Choice |
|---|---|
| Dynamic filters on a single aggregate, standard column conditions | Criteria + Query |
| Moderately nested AND/OR groups | Criteria with nested Criteria |
| Queries needing joins, CTEs, or window functions | Custom SQL |
| Predicates needing database-specific expressions | Custom SQL |
| Leveraging aggregate mapping and template | JdbcAggregateTemplate |
| Controlling every SELECT column and RowMapper | NamedParameterJdbcTemplate |

With SQL templates, the application must maintain ResultSet mapping, data types, null handling, and tenant rules itself. `@Column` on an entity does not automatically configure a hand-written RowMapper.

## 12. Parenthesis Grouping Rules and Operator Precedence

SQL evaluates AND before OR. Even knowing this rule, write explicit parentheses around every OR group in business queries. That makes intent clear to readers and prevents bugs when new conditions are added.

Example requirement:

~~~text
(status = ACTIVE OR status = PENDING)
AND tenant_id = currentTenant
AND (city = Hue OR district = Hai Chau)
~~~

SQL:

~~~sql
WHERE (status = 'ACTIVE' OR status = 'PENDING')
  AND tenant_id = :tenantId
  AND (city = :city OR district = :district)
~~~

Criteria:

~~~java
Criteria statusGroup = Criteria.where("status").is("ACTIVE")
        .or("status").is("PENDING");

Criteria locationGroup = Criteria.where("city").is("Hue")
        .or("district").is("Hai Chau");

Criteria criteria = statusGroup
        .and("tenant_id").is(tenantId)
        .and(locationGroup);
~~~

The two OR groups are constructed separately and then joined with the AND conditions. This is much easier to read than a long chain alternating between OR and AND.

## 13. Edge Cases Requiring Explicit Decisions

### 13.1. Empty Keywords

If keyword is null or whitespace-only, normally omit the keyword search group. Do not generate a `%%` pattern unless you intend it to match every string and accept the query cost.

### 13.2. Empty Collections

For list-based filters, define the meaning of an empty list:

- Selecting no status may mean do not filter by status.
- Explicitly sending an empty list may mean no values are allowed.

These two semantics differ. Distinguish "field omitted" from "field sent with an empty list" in the DTO/API. Never construct `IN ()` when there are no elements.

### 13.3. NULL Values

Do not add an `isNull()` condition just because a filter parameter is null. Only use `isNull()` when the user explicitly chooses to filter for rows with NULL values.

### 13.4. Wildcard Characters

With `LIKE`, `%` and `_` act as SQL wildcards. If searching for literal strings, establish a consistent escaping policy. If users are meant to enter patterns, state clearly that `%` and `_` are treated as wildcards.

### 13.5. Tenant and Access Permissions

Tenant, owner, and access permissions must be added from the server-side security context. Never allow a client-controlled OR group to make the tenant condition optional.

### 13.6. Time Ranges

For time ranges, prefer half-open intervals:

~~~sql
created_at >= :from
AND created_at < :until
~~~

This keeps adjacent intervals from overlapping at boundaries. Standardize timezones and Java/SQL types when passing timestamps.

## 14. Performance of AND/OR Groups

Criteria structure ensures logically accurate predicates, but does not by itself guarantee fast queries. The database evaluates conditions based on indexes and statistics.

Some guidelines:

- Create indexes for frequently used filters after inspecting the workload.
- For tenant-scoped queries, indexes starting with the tenant key can be helpful.
- OR across multiple columns can make it harder for the query planner to pick an optimal index compared to a single-column predicate.
- `LIKE '%keyword%'` usually cannot use standard B-tree indexes effectively; consider full-text search, trigrams, or a search engine when search demands grow.
- Do not create indexes for every filter combination; indexes increase write overhead and storage usage.
- Inspect query plans on a real database with production-like data distributions.

Example index supporting queries by tenant and status:

~~~sql
CREATE INDEX idx_customers_tenant_status
ON customers (tenant_id, status);
~~~

If queries frequently filter by tenant and time:

~~~sql
CREATE INDEX idx_customers_tenant_created
ON customers (tenant_id, created_at);
~~~

These indexes are examples only. Choose indexes based on actual queries, selectivity, sort order, and write cost.

## 15. Common Errors

| Symptom | Cause | Fix |
|---|---|---|
| Results include other tenants | OR not parenthesized with the tenant condition | Build a separate OR group and AND it into the main predicate |
| Results broader than expected | Confusing AND/OR precedence | Write explicit parentheses and test with a truth table |
| Null filter drops results | Null converted into IS NULL when intent was to skip filter | Add predicate only when filter is explicitly supplied |
| Data not found by column name | Confusing Java property with physical column in Criteria/SQL | Check @Column and use the right column name |
| Dynamic Criteria has no conditions | No mandatory predicate initialized or empty group | Start with mandatory tenant/scope and only add non-empty OR groups |
| IN with empty list errors or has wrong semantics | Undefined meaning for empty collection | Handle separately before building Criteria |
| LIKE returns too many results | % and _ in input treated as wildcards | Escape or document pattern semantics clearly |
| Dynamic query vulnerable to SQL injection | Concatenating request values into SQL | Bind every value with parameters |
| Dynamic sort exploited | Passing column name directly from request into SQL | Whitelist column names and sort directions |
| Query slow with many ORs | Unsuitable index/query plan or contains search | Use EXPLAIN, consider full-text/trigram indexes |
| Tenant filter missing on one branch | Unstructured predicate assembly | Add tenant at the outermost level with AND |
| Criteria query hard to maintain | Single expression with too many nested groups | Extract each group into a named Criteria variable |

## 16. Practice Exercises

### Exercise 1 — Basic AND

Build a customer search by tenant and status. Use Criteria to add the status condition when the filter is sent. Verify that when status is null, only the tenant condition remains.

### Exercise 2 — OR Inside an AND Group

Create a search by tenant and keyword. The keyword can match display_name, email_address, or customer_code. Use an OR group and AND that group with the tenant condition.

### Exercise 3 — Two OR Groups

Extend the search to include both a keyword group and a location group. Write the logical expression and parenthesized SQL before translating it into Criteria.

### Exercise 4 — Dynamic OR Group

Allow selecting multiple contact types or multiple locations. Build a list of Criteria, combine them with OR, and add the group only when the list is non-empty.

### Exercise 5 — Criteria vs. Custom SQL

Implement the same filter using Criteria/JdbcAggregateTemplate and NamedParameterJdbcTemplate. Compare readability, SQL control, and mapping responsibilities.

### Exercise 6 — Logic Testing

Create test data across two tenants, multiple statuses, and various emails/names. Test combinations to verify no out-of-tenant rows appear when OR groups match.

### Exercise 7 — Performance

Enable SQL logging and inspect query plans for AND/OR groups. Test an index on tenant/status and evaluate the impact of contains-style LIKE searches.

## 17. Takeaways

- AND combines conditions that must all be true; OR combines alternative choices.
- Always group OR conditions logically with parentheses before combining them with outer AND conditions.
- Derived queries fit fixed combinations; dynamic filters should use Criteria/Query or custom SQL.
- Criteria can be nested with `and(Criteria)` and `or(Criteria)` to express logical groups.
- In Criteria examples, use column names aligned with the schema and `@Column` mappings; derived queries use Java properties.
- Start from mandatory tenant/security conditions before adding optional filters.
- Distinguish omitted filters, NULL-value filters, and empty collections.
- When using dynamic SQL, concatenate only fixed application-controlled fragments and bind all values with parameters.
- Criteria does not replace checking query plans; indexes, collations, and LIKE patterns strongly affect performance.
