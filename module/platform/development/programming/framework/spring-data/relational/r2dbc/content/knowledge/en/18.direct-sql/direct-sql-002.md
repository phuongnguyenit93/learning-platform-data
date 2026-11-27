# Binding Valued Parameters and bindNull

When using Spring Data Relational R2DBC, applications frequently send SQL through **DatabaseClient**. Input values are passed into SQL statements using bind parameters. For parameters with a value, use **bind()**. For parameters that need to carry SQL **NULL**, use **bindNull()** and specify the corresponding Java type.

These two operations serve different purposes:

- **bind(name, value)** binds a non-null value to a placeholder.
- **bindNull(name, javaType)** binds a typed SQL NULL value to a placeholder.

The R2DBC SPI does not treat Java null as a regular value that can be passed to bind(). Therefore, do not call bind("nickname", null). Call bindNull("nickname", String.class) instead.

An even more common point of confusion: **bindNull only binds SQL NULL to a parameter; it does not turn column = :parameter into column IS NULL, nor does it omit the condition from WHERE.** To find columns whose value is NULL, write an IS NULL predicate. To skip an omitted filter, remove that predicate from the SQL statement or design an intentional optional expression.

## 1. What Is a Bind Parameter?

A bind parameter is a placeholder in a SQL statement. The application supplies the value separately for the placeholder instead of concatenating input data directly into the SQL string.

Example:

~~~sql
SELECT id, name
FROM customer
WHERE email = :email;
~~~

In Spring DatabaseClient, you can bind the value as follows:

~~~java
Mono<CustomerSummary> customer =
    databaseClient.sql(
            "SELECT id, name FROM customer WHERE email = :email"
        )
        .bind("email", "an@example.com")
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class)
        ))
        .one();
~~~

Here:

- :email is a named parameter in the application's SQL statement.
- bind("email", ...) binds the value to the parameter named email.
- DatabaseClient handles translating the named parameter into the bind marker used by the R2DBC driver.
- The driver binds the value using the corresponding database's mechanism and codecs.

The placeholder name is not part of the data. The email value is bound separately, so special characters in email cannot alter the SQL structure the way direct string concatenation can.

## 2. How Do bind() and bindNull() Differ?

| API | When to Use | Example |
|---|---|---|
| bind(String, Object) | An actual, non-null value | bind("name", "An") |
| bindNull(String, Class<?>) | When binding SQL NULL | bindNull("nickname", String.class) |

Consider a table with a nullable nickname column:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    nickname VARCHAR(100) NULL
);
~~~

When inserting a customer without a nickname:

~~~java
Mono<Void> insert =
    databaseClient.sql(
        "INSERT INTO customer (id, name, nickname) " +
        "VALUES (:id, :name, :nickname)"
    )
    .bind("id", 42L)
    .bind("name", "An")
    .bindNull("nickname", String.class)
    .then();
~~~

The nickname parameter is sent as SQL NULL. The database column must allow NULL; if the column has a NOT NULL constraint, the database will reject the statement.

For non-null values, use bind:

~~~java
DatabaseClient.GenericExecuteSpec spec =
    databaseClient.sql(
        "INSERT INTO customer (id, name, nickname) " +
        "VALUES (:id, :name, :nickname)"
    );

spec = spec.bind("id", 42L);
spec = spec.bind("name", "An");
spec = spec.bind("nickname", "Annie");
~~~

Bind methods return a GenericExecuteSpec used to continue configuring the statement. Retain the returned value when chaining or reassign spec.

## 3. Why Is bind(null) Incorrect?

Do not write:

~~~java
databaseClient.sql(
        "INSERT INTO customer (name, nickname) " +
        "VALUES (:name, :nickname)"
    )
    .bind("name", "An")
    .bind("nickname", null);
~~~

The regular bind API requires a non-null value. R2DBC needs to know the data type to encode a NULL value for the database/driver, so it provides the dedicated bindNull API.

Correct version:

~~~java
databaseClient.sql(
        "INSERT INTO customer (name, nickname) " +
        "VALUES (:name, :nickname)"
    )
    .bind("name", "An")
    .bindNull("nickname", String.class);
~~~

Marking a Java variable with @Nullable does not change R2DBC's rules. Nullable annotations document the contract in code and assist analysis tools; at execution time, you must still choose bind() or bindNull() appropriately.

## 4. What Does the Java Type in bindNull Mean?

The R2DBC SPI signature for binding null requires a Java type, for example:

~~~java
statement.bindNull(0, String.class);
~~~

Spring DatabaseClient provides the named-parameter form:

~~~java
spec.bindNull("nickname", String.class);
~~~

This type tells the driver which data type to encode the SQL NULL as. Some common types:

| Column or Data | Common Java Type |
|---|---|
| VARCHAR, CHAR, TEXT | String.class |
| BIGINT | Long.class |
| INTEGER | Integer.class |
| BOOLEAN | Boolean.class |
| DECIMAL, NUMERIC | BigDecimal.class |
| DATE | LocalDate.class |
| TIMESTAMP | LocalDateTime.class |
| TIMESTAMP WITH TIME ZONE | Usually OffsetDateTime.class or a driver-supported type |
| UUID | UUID.class |

The Java type must be compatible with the mapping and codecs of the R2DBC driver in use. For specialized database types, custom converters or driver-provided codecs may be required.

Do not pass Object.class for every null parameter when the column type is known. An overly generic type can prevent the driver from selecting a codec or prevent the database from inferring the required SQL type.

Example:

~~~java
spec = spec.bindNull("ownerId", Long.class);
spec = spec.bindNull("createdAt", LocalDateTime.class);
spec = spec.bindNull("price", BigDecimal.class);
~~~

Note: bindNull accepts a Java Class, not a SQL type name string. Pass Long.class, not "BIGINT".

## 5. Binding Values and bindNull Directly in the R2DBC SPI

When using the low-level R2DBC SPI, Statement typically uses bind indexes:

~~~java
Publisher<? extends Result> result =
    connection.createStatement(
            "INSERT INTO customer (name, nickname) VALUES ($1, $2)"
        )
        .bind(0, "An")
        .bindNull(1, String.class)
        .execute();
~~~

In the example, bind indexes start at 0. The $1, $2 syntax is the marker format of some drivers such as PostgreSQL; other drivers may use another format. With direct SPI usage, follow the marker syntax and binding rules of the specific driver.

When using DatabaseClient, applications typically write named parameters like :name. Spring translates them into the marker format required by the driver. Do not confuse Spring's named-parameter syntax with the native SQL marker syntax of every R2DBC driver.

## 6. bindNull Does Not Mean IS NULL

This is the most important point when writing WHERE conditions.

Suppose you want to find customers whose nickname is SQL NULL. The following statement is incorrect:

~~~sql
SELECT id, name
FROM customer
WHERE nickname = :nickname;
~~~

If nickname is bound as SQL NULL, the expression nickname = NULL does not become TRUE. Under SQL's three-valued logic, comparing against NULL evaluates to UNKNOWN. Therefore, rows with a NULL nickname are not selected by WHERE.

To find rows with NULL values, you must write:

~~~sql
SELECT id, name
FROM customer
WHERE nickname IS NULL;
~~~

Similarly:

- Use IS NOT NULL to find non-null values.
- Do not use = NULL or <> NULL to check for null.
- Binding a null parameter cannot replace the IS NULL operator.

### When Is bindNull Still Needed in a WHERE Expression?

Sometimes SQL uses a null parameter to represent "do not apply filter":

~~~sql
SELECT id, name
FROM customer
WHERE (:status IS NULL OR status = :status);
~~~

If status is bound as SQL NULL, the :status IS NULL branch is TRUE and the condition does not filter by status. If a string such as ACTIVE is bound, the first branch is FALSE and the query only returns rows where status equals ACTIVE.

In this case, bindNull("status", String.class) is valid because the goal is to use null as a signal to skip the filter. This is different semantics from requesting "find rows whose status is NULL."

Some databases or drivers may need additional type/cast information to infer a null parameter, especially when the placeholder appears only inside an IS NULL expression. If type inference fails, inspect the generated SQL, bind type, and database rules; a CAST appropriate for the target database may be required.

## 7. Distinguishing Three Meanings: Omitting a Filter, Finding NULL, and Comparing with a Value

A search API may need three states:

1. No filter sent: do not apply a status condition.
2. Requesting NULL status: only return rows where the status column is SQL NULL.
3. Sending status = ACTIVE: only return rows where status equals ACTIVE.

These three states should not be collapsed into a single nullable Java variable if the API needs to distinguish all three.

| Intent | SQL to Generate | Is bindNull Needed? |
|---|---|---|
| Do not filter status | Do not add status predicate | No |
| Find NULL status | status IS NULL | No |
| Find non-NULL status | status IS NOT NULL | No |
| Find status equal to ACTIVE | status = :status | No, use value bind |
| Null parameter means skip filter in fixed SQL | (:status IS NULL OR status = :status) | Yes |

Example building explicit predicates:

~~~java
List<String> predicates = new ArrayList<>();
Map<String, Object> parameters = new LinkedHashMap<>();

if (filter.statusMode() == StatusMode.IS_NULL) {
    predicates.add("c.status IS NULL");
} else if (filter.statusMode() == StatusMode.EQUALS) {
    predicates.add("c.status = :status");
    parameters.put("status", filter.status());
}
// StatusMode.ANY: do not add status predicate.
~~~

Then bind parameters only for the placeholders actually present in the SQL. This cleanly separates absent, explicit null, and a concrete value.

## 8. Example of Binding Nullable Parameters in DatabaseClient

A small helper can choose bind() or bindNull() based on the value:

~~~java
private DatabaseClient.GenericExecuteSpec bindNullable(
        DatabaseClient.GenericExecuteSpec spec,
        String name,
        Object value,
        Class<?> javaType) {

    if (value == null) {
        return spec.bindNull(name, javaType);
    }

    return spec.bind(name, value);
}
~~~

Usage when the SQL statement already includes the matching placeholders:

~~~java
DatabaseClient.GenericExecuteSpec spec =
    databaseClient.sql(
        "INSERT INTO customer (name, nickname, owner_id) " +
        "VALUES (:name, :nickname, :ownerId)"
    );

spec = spec.bind("name", "An");
spec = bindNullable(spec, "nickname", nickname, String.class);
spec = bindNullable(spec, "ownerId", ownerId, Long.class);

return spec.fetch().rowsUpdated();
~~~

If nickname is null, the helper calls bindNull("nickname", String.class). If ownerId has a value, the helper calls the regular bind. Both placeholders remain in the SQL; the helper only decides what value gets bound.

Do not use this helper to decide whether a filter belongs in the SQL. That decision belongs in the predicate-building step. If a placeholder does not appear in the SQL statement, it should not be bound.

## 9. bindNull in INSERT and UPDATE

### Inserting a Nullable Column

When you want to store SQL NULL in a column:

~~~java
databaseClient.sql(
        "INSERT INTO customer (id, name, nickname) " +
        "VALUES (:id, :name, :nickname)"
    )
    .bind("id", 42L)
    .bind("name", "An")
    .bindNull("nickname", String.class)
    .fetch()
    .rowsUpdated();
~~~

### Updating a Column to NULL

When a user clears their nickname and business logic requires storing SQL NULL:

~~~java
databaseClient.sql(
        "UPDATE customer SET nickname = :nickname WHERE id = :id"
    )
    .bindNull("nickname", String.class)
    .bind("id", 42L)
    .fetch()
    .rowsUpdated();
~~~

This is an intentional partial update: the nickname column is set to NULL, and columns absent from SET are untouched by this statement.

If an update API treats null as "do not change the nickname field," then do not call bindNull. Omit the nickname column from SET. If null means "clear the current value," use bindNull. The semantics must be defined in the API contract.

## 10. bindNull with Optional Filters

Suppose a filter has a status field. There are two common implementation approaches.

### Approach A: Build Dynamic SQL and Omit the Predicate When Absent

~~~java
String sql =
    "SELECT id, name FROM customer WHERE tenant_id = :tenantId";

if (status != null) {
    sql += " AND status = :status";
}

DatabaseClient.GenericExecuteSpec spec =
    databaseClient.sql(sql)
        .bind("tenantId", tenantId);

if (status != null) {
    spec = spec.bind("status", status);
}
~~~

When absent, neither the predicate nor the parameter binding is added. Build the full SQL string before calling databaseClient.sql(sql) so placeholders and bindings match.

### Approach B: Fixed SQL Where Null Means Skip Filter

~~~java
DatabaseClient.GenericExecuteSpec spec =
    databaseClient.sql(
        "SELECT id, name FROM customer " +
        "WHERE tenant_id = :tenantId " +
        "AND (:status IS NULL OR status = :status)"
    )
    .bind("tenantId", tenantId);

if (status == null) {
    spec = spec.bindNull("status", String.class);
} else {
    spec = spec.bind("status", status);
}
~~~

Approach B uses bindNull as a signal to skip the condition. Verify that the driver/database properly infers the null parameter's type. With many filters, SQL like (:p IS NULL OR column = :p) can be harder to optimize than dynamic predicates; inspect the execution plan.

If null means finding rows with a NULL column, use the status IS NULL predicate instead of Approach B.

## 11. bindNull in IN, LIKE, and Comparisons

### IN

~~~sql
WHERE owner_id IN (:ownerId)
~~~

Binding ownerId as NULL does not turn an IN condition into a search for NULL owner_id. To also match rows where owner_id is NULL, write it explicitly:

~~~sql
WHERE owner_id IN (:ownerIds)
   OR owner_id IS NULL
~~~

A list containing a null element does not replace IS NULL either; comparisons inside IN follow SQL three-valued logic. Handle null elements in a list separately if required by business logic.

### LIKE

~~~sql
WHERE name LIKE :pattern
~~~

Binding null to pattern does not match all names or empty strings. The result of LIKE with NULL is UNKNOWN. If you do not want to apply a name filter, omit the predicate or use an intentional optional-filter expression. If you want to find NULL names, use name IS NULL.

### Date Ranges and Comparisons

~~~sql
WHERE created_at >= :createdFrom
~~~

If createdFrom is NULL, the condition does not automatically become "unbounded in time." It will not select rows via comparison. Omit the predicate or write explicit nullable logic.

## 12. Named Parameters and Positional Parameters

Spring DatabaseClient typically lets you write named parameters:

~~~java
databaseClient.sql(
        "SELECT id FROM customer WHERE email = :email"
    )
    .bind("email", email);
~~~

Named parameters improve readability by associating values with placeholder names. Spring translates these placeholders into the marker format used by the driver.

In the direct R2DBC SPI, statements usually bind positionally:

~~~java
statement
    .bind(0, email)
    .bindNull(1, String.class);
~~~

Indexes normally start at 0 in the R2DBC API. SQL marker syntax and numbering within the statement depend on the driver.

When using the SPI directly, ensure:

- The number of markers matches the number of bindings.
- Bind indexes are valid and none are missing.
- Null values use bindNull(index, javaType).
- Marker syntax matches the driver.

## 13. Safe Parameter Binding and SQL Injection

Never concatenate user data into a SQL statement:

~~~java
String sql =
    "SELECT id FROM customer WHERE email = '" + email + "'";
~~~

Bind the value instead:

~~~java
databaseClient.sql(
        "SELECT id FROM customer WHERE email = :email"
    )
    .bind("email", email);
~~~

Parameter binding protects SQL structure from input being interpreted as syntax. However, binding applies only to values, not table names, column names, operators, or sort directions. Those dynamic SQL parts must be selected from an application-controlled whitelist.

bindNull also preserves SQL structure: it merely supplies a typed NULL value. It is not string concatenation, not a mechanism for omitting predicates, and not an access-control check.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Calling bind(name, null) | API/driver rejects null values | Use bindNull(name, JavaType.class) |
| Using bindNull without a type | No type to select codec or infer SQL type | Specify the appropriate Java type |
| Passing a SQL type name as a String | Wrong API parameter type | Pass String.class, Long.class, etc. |
| Using column = :value with null to find NULL | Returns no NULL rows | Use column IS NULL |
| Assuming bindNull omits the filter | Predicate is still executed | Omit the predicate or write an explicit optional expression |
| Assuming null in LIKE acts as a wildcard | Condition does not match as expected | Use a valid pattern or omit the filter |
| Using null in IN to match NULL columns | Does not yield the expected semantics | Add OR column IS NULL |
| Using primitives for nullable fields | Cannot represent null | Use wrappers such as Long, Boolean |
| Ignoring driver-unsupported data types | Codec or conversion error | Check driver, converters, and database types |
| Binding a placeholder absent from SQL | Statement configuration error | Keep predicate and parameter lists synchronized |
| Having a placeholder but forgetting to bind | Statement fails to execute | Check every SQL-building branch |
| Using bind for column names | Database treats it as a value | Use an identifier whitelist |

## 15. Testing Value Binding and bindNull

You should test both non-null values and SQL NULL against a real database and R2DBC driver.

Example test matrix for the nickname column:

| Input | How to Bind | Expected Outcome |
|---|---|---|
| Annie | bind("nickname", "Annie") | Stores string Annie |
| null, want to store NULL | bindNull("nickname", String.class) | nickname column is SQL NULL |
| null, want to keep unchanged on update | Do not include nickname in SET | Existing value remains unchanged |
| null, want to find NULL rows | SQL nickname IS NULL | Only returns rows with NULL nickname |
| null, want to skip filter | Omit predicate or bindNull in optional expression | Does not filter by nickname |

In addition to data results, verify:

- Whether the column allows NULL.
- Whether the driver has a codec for the Java type passed to bindNull.
- Whether the database can infer the null parameter type in expressions or requires a CAST.
- Every SQL branch binds all placeholders.
- No input is concatenated directly into SQL.
- Absent and explicit null behavior match the API contract.

Integration tests help uncover differences in data types, placeholders, and null handling across R2DBC drivers. A test using only mocks cannot prove that the real driver encodes SQL NULL properly.

## 16. Workflow for Choosing bind() vs. bindNull()

Before binding a value, answer in order:

1. Does the placeholder actually exist in the SQL statement?
2. Is the Java value null?
3. If null, does the business logic intend to write SQL NULL, compare against NULL, or skip a filter?
4. If writing or passing SQL NULL, what is the corresponding Java type?
5. If comparing against NULL, does the SQL use IS NULL or IS NOT NULL?
6. If skipping a filter, is the predicate omitted from SQL or using an optional expression with the right semantics?
7. Do the driver and database support that bind type?

API selection rule:

~~~text
Input value
      |
      v
  Is it null?
   /       \
 No        Yes
  |         |
  v         v
bind()   What does business logic want?
            |
     +------+------+
     |      |      |
 Store NULL Find NULL Skip filter
     |      |      |
     v      v      v
 bindNull IS NULL Omit predicate
           (no
         bindNull needed)
~~~

## 17. Key Takeaways

- bind(name, value) is for non-null values.
- bindNull(name, javaType) is for SQL NULL parameters and must specify the matching Java type.
- The R2DBC SPI has Statement.bind(index, value) and Statement.bindNull(index, javaType); bind indexes typically start at 0.
- bindNull does not replace = with IS NULL, does not omit predicates, and does not act as a wildcard.
- In SQL, = NULL or <> NULL comparisons cannot check for null; use IS NULL or IS NOT NULL.
- Distinguish omitting a filter, sending null to find SQL NULL, and sending a concrete value.
- On update, null may mean setting the column to NULL or leaving it untouched; the API contract must state this clearly.
- Use the right Java type so the driver picks the codec and the database handles the type properly.
- Do not concatenate input into SQL; bind parameters are for values only, while dynamic identifiers must go through a whitelist.
- Test null handling with the exact target R2DBC driver and database.
