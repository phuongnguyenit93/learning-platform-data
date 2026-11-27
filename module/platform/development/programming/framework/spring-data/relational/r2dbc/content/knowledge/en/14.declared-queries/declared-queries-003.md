# Binding Parameters with @Param

## 1. Why is parameter binding needed in declared queries?

Spring Data R2DBC allows declaring queries directly on a repository interface using the @Query annotation. Inside a SQL statement, you often need to pass values from Java method parameters into filter conditions, update values, or other expressions.

For example, a repository needs to find a customer by email:

~~~java
@Query("SELECT id, full_name, email FROM customers WHERE email = :email")
Mono<Customer> findCustomerByEmail(@Param("email") String email);
~~~

In this example, there are two names in two contexts:

- email in @Param("email") is the logical parameter name declared on the Java method.
- :email in the SQL statement is the named placeholder that Spring Data uses to bind the value into the query.

When the method is called with an email address, Spring Data takes the Java parameter's value and binds it to the corresponding placeholder. The value is passed as a statement parameter rather than concatenated directly into the SQL string.

The @Param annotation belongs to the org.springframework.data.repository.query package. It is especially useful for repository methods annotated with @Query that use named parameters.

## 2. How does @Param work?

### 2.1. Naming method parameters

Example:

~~~java
import org.springframework.data.repository.query.Param;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, full_name, email
        FROM customers
        WHERE email = :email
        """)
    Mono<Customer> findByEmailAddress(
        @Param("email") String emailAddress
    );
}
~~~

The Java parameter name is emailAddress. The SQL placeholder, however, is :email. The @Param("email") annotation tells Spring Data that the value of emailAddress must be bound to the placeholder named email.

The name inside @Param does not have to match the Java variable name. What must be ensured is that the string in @Param matches the placeholder name in the SQL statement.

The binding flow can be visualized as follows:

~~~text
Repository call
findByEmailAddress("a@example.com")
              |
              v
Java parameter: emailAddress
              |
              v
@Param("email")
              |
              v
SQL placeholder: :email
              |
              v
Bind value into statement
              |
              v
Database executes query
~~~

### 2.2. Names must match exactly

Suppose the SQL has the placeholder :customerId:

~~~java
@Query("""
    SELECT id, customer_id, status
    FROM orders
    WHERE customer_id = :customerId
    """)
Flux<Order> findByCustomer(
    @Param("customerId") Long id
);
~~~

This declaration binds properly even though the Java variable name is id. If you write @Param("customer_id") while the SQL uses :customerId, Spring Data cannot find the corresponding logical parameter. Depending on when detection occurs and the version, an error may appear during query creation or at execution time.

Choose a readable naming convention and apply it consistently. Typically, placeholder names should describe the value's meaning, such as :customerId, :status, or :createdAfter.

### 2.3. Multiple parameters in a single query

A method can accept multiple parameters. Each named placeholder is bound to a parameter via a corresponding @Param:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE first_name = :firstName
      AND last_name = :lastName
      AND active = :active
    """)
Flux<Customer> searchCustomers(
    @Param("firstName") String firstName,
    @Param("lastName") String lastName,
    @Param("active") Boolean active
);
~~~

Binding table:

| Java parameter | @Param | SQL placeholder |
|---|---|---|
| firstName | firstName | :firstName |
| lastName | lastName | :lastName |
| active | active | :active |

Every placeholder must have a matching value. Do not rely on method parameter order to guess placeholder names when the SQL uses named parameters.

## 3. When is @Param needed?

### 3.1. Used with @Query having named parameters

Typical case:

~~~java
@Query("""
    SELECT id, status, created_at
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
    """)
Flux<Order> findOrders(
    @Param("customerId") Long customerId,
    @Param("status") OrderStatus status
);
~~~

@Param makes the relationship between placeholder names and Java parameters clear. It is explicit, readable, and less dependent on compilation metadata.

### 3.2. Relying on Java parameter names in some configurations

Spring Data can discover parameter names from class file metadata if compilation retains parameter names, for example by using the javac -parameters option. In supported cases, Java parameter names can then match named placeholders without writing @Param on every parameter.

However, this depends on compiler configuration, Spring version, and how parameter name discovery works. If parameter names are absent from bytecode, Spring may fail to infer the required names.

Therefore, for repository queries using named parameters, explicit @Param declarations are generally easier to maintain, especially when:

- Java variable names differ from SQL placeholder names.
- A project has multiple modules with varying build configurations.
- Code must behave consistently across build environments.
- A method has many parameters or parameter names that could easily be confused.

### 3.3. @Param is not needed for derived query methods

For derived query methods, Spring Data derives conditions from the method name and binds arguments according to the order/properties described in the method.

Example:

~~~java
Flux<Customer> findByFirstNameAndLastName(
    String firstName,
    String lastName
);
~~~

Here, @Param is unnecessary because there is no hand-written SQL string with named placeholders. Spring Data parses the method name and parameters to construct the query.

Similarly:

~~~java
Mono<Customer> findByEmail(String email);

Flux<Order> findByCustomerIdAndStatus(
    Long customerId,
    OrderStatus status
);
~~~

Do not add @Param simply because a method has parameters. Use it when you need to bind parameters to placeholder names in declared queries or in repository APIs that support parameter name annotations.

### 3.4. @Param is not an annotation for every query style

@Param does not replace DatabaseClient's binding mechanism. When writing SQL directly with DatabaseClient, you call bind() on the statement spec:

~~~java
return databaseClient.sql("""
        SELECT id, full_name, email
        FROM customers
        WHERE email = :email
        """)
    .bind("email", emailAddress)
    .map((row, metadata) -> mapCustomer(row))
    .one();
~~~

Here the name email is bound via .bind("email", emailAddress), not via @Param. @Param attaches to repository method parameters; DatabaseClient uses its own bind API.

## 4. Named parameters and SQL placeholders

### 4.1. The :name syntax

In Spring Data R2DBC declared queries, named parameters are typically written with a leading colon before the name:

~~~sql
SELECT id, full_name
FROM customers
WHERE email = :email
~~~

The :email placeholder is a slot that receives a value. It is not a column name and does not alter the SQL statement's structure.

Another example:

~~~sql
SELECT id, status
FROM orders
WHERE customer_id = :customerId
  AND status = :status
  AND created_at >= :createdAfter
~~~

Correspondingly, the repository method can be declared as:

~~~java
@Query("""
    SELECT id, status
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
      AND created_at >= :createdAfter
    """)
Flux<Order> searchOrders(
    @Param("customerId") Long customerId,
    @Param("status") String status,
    @Param("createdAfter") Instant createdAfter
);
~~~

### 4.2. Named parameters are translated into driver bind markers

The R2DBC SPI and individual drivers each have their own bind marker rules. For instance, one driver may use positional markers, while another uses a different marker syntax.

Spring Data R2DBC operates with named parameters at the query layer and translates them into the bind markers used by the dialect/driver. Therefore, when writing `@Query` under Spring Data R2DBC's abstraction, you typically use :name instead of hardcoding a driver's native marker syntax.

This keeps queries readable and reduces coupling to how a driver numbers parameters. Nevertheless, the SQL itself must still be valid for the database dialect. Named parameters do not turn PostgreSQL-, MySQL-, or SQL Server-specific SQL syntax into universal SQL.

### 4.3. Reusing the same parameter in multiple places

A single value can be used across multiple conditions in the same query:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE email = :email
       OR backup_email = :email
    """)
Mono<Customer> findByPrimaryOrBackupEmail(
    @Param("email") String email
);
~~~

Both placeholders named email receive the same value from the same parameter. If you need two independent values, give them two distinct names and declare two @Param annotations.

### 4.4. Do not confuse parameter names with column names

Example:

~~~java
@Query("""
    SELECT id, full_name
    FROM customers
    WHERE customer_code = :code
    """)
Mono<Customer> findByCode(
    @Param("code") String customerCode
);
~~~

customer_code is the column name in the database. code is the placeholder name. customerCode is the Java variable name. All three names can differ, as long as the mapping and parameter binding are declared properly.

## 5. Practical examples with various parameter types

### 5.1. Finding by ID and status

~~~java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
    ORDER BY created_at DESC
    """)
Flux<Order> findByCustomerAndStatus(
    @Param("customerId") Long customerId,
    @Param("status") String status
);
~~~

A service can call:

~~~java
public Flux<Order> getPaidOrders(Long customerId) {
    return orderRepository.findByCustomerAndStatus(
        customerId,
        "PAID"
    );
}
~~~

If status is an enum, you can declare the parameter as OrderStatus and rely on configured conversions, provided the column type and converter are compatible. For manual queries, verify how enum binding works in your Spring Data/driver version.

### 5.2. Finding by time range

~~~java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM orders
    WHERE created_at >= :fromTime
      AND created_at < :toTime
    ORDER BY created_at
    """)
Flux<Order> findCreatedBetween(
    @Param("fromTime") Instant fromTime,
    @Param("toTime") Instant toTime
);
~~~

Using a half-open interval [fromTime, toTime) makes it easy to chain consecutive intervals without handling boundary overlaps. The Instant type must convert cleanly to the database and driver's timestamp type.

### 5.3. Searching with LIKE

You can bind the search pattern itself:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE full_name LIKE :pattern
    """)
Flux<Customer> searchByName(
    @Param("pattern") String pattern
);
~~~

The service builds the pattern:

~~~java
public Flux<Customer> search(String keyword) {
    String pattern = "%" + keyword + "%";
    return customerRepository.searchByName(pattern);
}
~~~

The keyword value is still bound as data. The percent signs are part of the pattern value, not a concatenation of keyword into the SQL statement.

If case-insensitive search is needed, syntax depends on the database—for example, ILIKE in PostgreSQL or LOWER(...) in engines that support the corresponding expression. Use the syntax appropriate for your actual dialect.

## 6. Binding collections with IN conditions

A query may need to filter by a set of IDs or a set of statuses. Example:

~~~java
@Query("""
    SELECT id, customer_id, status
    FROM orders
    WHERE status IN (:statuses)
    """)
Flux<Order> findByStatuses(
    @Param("statuses") Collection<String> statuses
);
~~~

When using a named parameter with a collection in an IN context, Spring Data R2DBC's parameter expansion mechanism can generate the corresponding bind markers for the collection elements. This avoids manually concatenating lists of values into the SQL string.

Call example:

~~~java
List<String> statuses = List.of("PAID", "SHIPPED");

Flux<Order> orders = orderRepository.findByStatuses(statuses);
~~~

### 6.1. Empty collections

An empty collection is a case that must be handled explicitly. IN syntax with an empty list does not share the same meaning or consistent support across all dialects/drivers.

If an empty collection means returning no results, handle it before calling the repository:

~~~java
public Flux<Order> findByStatuses(Collection<String> statuses) {
    if (statuses == null || statuses.isEmpty()) {
        return Flux.empty();
    }

    return orderRepository.findByStatuses(statuses);
}
~~~

If an empty collection means applying no filter, design a separate method/query or build the query in explicit branches. Never rely on how a database interprets IN ().

### 6.2. A collection does not mean a single SQL parameter

When expanding a collection, each element is bound as a separate value. Do not concatenate elements into a SQL string like:

~~~java
String sql = "SELECT * FROM orders WHERE id IN (" + ids + ")";
~~~

String concatenation is both error-prone syntactically and vulnerable to SQL injection if data comes from external input. Use named collection binding or a supported query builder API.

## 7. Null values and SQL conditions

A Java parameter can accept null if its type permits. However, SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. The expression:

~~~sql
email = :email
~~~

does not become an IS NULL check when email is bound to null. Comparing with NULL yields UNKNOWN, so the row is not selected by that WHERE condition.

If you need to find rows where email is NULL, use a separate SQL condition:

~~~sql
WHERE email IS NULL
~~~

Repository example:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE email IS NULL
    """)
Flux<Customer> findWithoutEmail();
~~~

If business logic has two cases—filtering by email when provided and returning all when null—design the logic intentionally. An expression like:

~~~sql
WHERE (:email IS NULL OR email = :email)
~~~

requires attention to the null parameter's type and how the database infers bind types. Depending on the driver, you may need explicit type declarations or separate queries. Do not use this expression blindly without testing against a real database.

Also distinguish null from an empty string. An email parameter of "" searches for empty strings when using equality comparison; it does not find rows with NULL email.

## 8. @Param and parameter data types

Parameter names only solve binding. The value must still have a type that Spring Data conversions, the R2DBC driver, and the database can handle.

Example:

| Java type | Common column | Notes |
|---|---|---|
| Long | BIGINT | ID or large integer |
| Integer | INTEGER | Integer |
| BigDecimal | DECIMAL / NUMERIC | Decimal requiring precision |
| String | VARCHAR / TEXT | String |
| Boolean | BOOLEAN | Depends on database engine |
| LocalDate | DATE | Date |
| LocalDateTime | TIMESTAMP | Date and time without time zone |
| Instant | Driver-compatible timestamp | Maintain consistent UTC convention |
| Enum | String or configured type | Requires corresponding conversion |

If a method accepts Long while the database column is UUID, setting @Param properly cannot fix the type mismatch. Align the Java type, column type, and converters.

Enum parameter example:

~~~java
@Query("""
    SELECT id, status
    FROM orders
    WHERE status = :status
    """)
Flux<Order> findByStatus(
    @Param("status") OrderStatus status
);
~~~

If OrderStatus is stored by its default name, Spring Data can convert the enum via its default conversion mechanism. If the enum uses custom business codes, you need registered read/write converters and must verify that converters apply to query parameters in your version.

## 9. @Param cannot substitute table names, column names, or dynamic SQL syntax

Bind parameters are for values only. You cannot use placeholders to substitute table names or column names in the normal way.

Semantically invalid example:

~~~sql
SELECT * FROM :tableName
~~~

Or:

~~~sql
SELECT id, full_name
FROM customers
ORDER BY :columnName
~~~

Placeholders are bound as literal values. The database does not interpret a bound value as an identifier or SQL keyword. In the case of ORDER BY :columnName, the database may treat it as a constant value expression for every row rather than a column name to sort by.

If you need dynamic sort column selection, use Sort supported by Spring Data or map the input to an allowlisted set of identifiers. Example:

~~~java
Sort sort = switch (requestedSort) {
    case "name" -> Sort.by("fullName");
    case "created" -> Sort.by("createdAt");
    default -> Sort.by("id");
};
~~~

Never concatenate client-supplied column names directly into SQL. Whitelist valid options before constructing the query.

Similarly, do not use @Param to replace keywords like ASC/DESC, operators, or SQL fragments. Structural elements of the query must be determined from trusted code.

## 10. Parameter binding helps reduce SQL injection risk

Unsafe:

~~~java
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";
return databaseClient.sql(sql);
~~~

If email contains quotes or content crafted to manipulate SQL, the query can be altered unintentionally.

Safer:

~~~java
@Query("""
    SELECT id, full_name, email
    FROM customers
    WHERE email = :email
    """)
Mono<Customer> findByEmail(@Param("email") String email);
~~~

Spring Data binds the value as a statement parameter. The database handles the value separately from the SQL structure, reducing the risk of input data being interpreted as SQL syntax.

Parameter binding does not replace all security measures. You still need access control checks, business validation, result limits, and whitelisting of dynamic identifiers. Do not include sensitive data in SQL logs or error messages sent to clients.

## 11. Combining @Param with @Modifying

Beyond SELECT, repository queries can use @Query for update or delete statements depending on the API and version. For modifying queries, Spring Data R2DBC supports the @Modifying annotation in corresponding cases.

Example:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = :status
    WHERE id = :orderId
    """)
Mono<Integer> updateStatus(
    @Param("orderId") Long orderId,
    @Param("status") String status
);
~~~

In the example, two parameters are bound by name. The return type is typically used to receive the affected row count according to the Spring Data R2DBC version's API.

A multi-record update can also use named parameters:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = :newStatus
    WHERE customer_id = :customerId
      AND status = :oldStatus
    """)
Mono<Integer> moveOrdersToNewStatus(
    @Param("customerId") Long customerId,
    @Param("oldStatus") String oldStatus,
    @Param("newStatus") String newStatus
);
~~~

Verify method signatures and annotation requirements in the Spring Data version you are using. If a business operation involves multiple statements that must succeed or fail together, wrap them in a reactive transaction.

## 12. @Param in queries with JOIN or subqueries

Named parameters work the same way when the SQL involves multiple tables. Example:

~~~java
@Query("""
    SELECT o.id, o.customer_id, o.status, o.created_at
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE c.email = :email
      AND o.created_at >= :createdAfter
    """)
Flux<Order> findOrdersForCustomer(
    @Param("email") String email,
    @Param("createdAfter") Instant createdAfter
);
~~~

Placeholder names do not need to match aliases or table names. email is the logical parameter, while c.email is the column being compared.

Subqueries can also use named parameters:

~~~java
@Query("""
    SELECT id, customer_id, status
    FROM orders
    WHERE customer_id IN (
        SELECT id
        FROM customers
        WHERE active = :active
    )
    """)
Flux<Order> findOrdersForActiveCustomers(
    @Param("active") Boolean active
);
~~~

A placeholder can appear anywhere appropriate in the query. Keep names clear and avoid reusing the same name for different business values just because they share the same Java type.

## 13. Common errors when using @Param

| Error | Cause | Resolution |
|---|---|---|
| Named parameter not found | @Param name does not match placeholder | Compare the exact names in the annotation and SQL |
| Placeholder has no value | SQL has :name but method lacks a matching parameter | Add the parameter or fix the query |
| Java parameter has a different name and @Param is omitted | Spring lacks required parameter name metadata | Use explicit @Param or ensure the build retains parameter names |
| Unnecessary @Param on derived queries | Confusing query derivation with @Query | Let Spring derive from the method name and parameter order |
| Using @Param with DatabaseClient.bind() | Confusing repository annotations with direct bind API | Use DatabaseClient's .bind("name", value) |
| Binding null and comparing with = | SQL does not treat NULL as an ordinary equal value | Use IS NULL or design query branches |
| Binding column or table names | Placeholders only accept values | Use a whitelist or Sort for dynamic identifiers |
| IN with an empty collection | No elements to expand bind markers | Handle empty collections before calling the repository |
| Parameter type incompatible with column | Binding name is right but type is mismatched | Align Java type, converter, driver, and schema |
| Concatenating input strings into SQL | Data mixes into the query structure | Use parameter binding |

## 14. Workflow for declaring a query method with @Param

When writing a repository method using @Query, follow this sequence:

1. Write the SQL statement using table and column names matching the schema.
2. Choose meaningful named placeholders for each value to pass.
3. Declare Java parameters with types compatible with the columns and conversions.
4. Annotate each parameter with @Param to link the exact placeholder name.
5. Choose a Mono or Flux return type according to result cardinality.
6. For UPDATE/DELETE, check @Modifying and return type requirements for your Spring Data version.
7. Never concatenate input data into SQL strings.
8. Explicitly handle null, empty collections, and boundary data cases.
9. Verify the SQL against your actual dialect and driver.
10. Write integration tests for valid parameters, empty results, null if permitted, empty collections, and values with special characters.

Combined example:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT id, customer_id, status, created_at
        FROM orders
        WHERE customer_id = :customerId
          AND status = :status
          AND created_at >= :createdAfter
        ORDER BY created_at DESC
        """)
    Flux<Order> searchOrders(
        @Param("customerId") Long customerId,
        @Param("status") String status,
        @Param("createdAfter") Instant createdAfter
    );
}
~~~

This method has three parameters, each explicitly bound to a named placeholder. The result is Flux<Order> because a customer can have multiple matching orders.

## 15. Self-check exercises

### Exercise 1: Binding different names

The SQL uses :emailAddress while the Java parameter is named email. Declare the method with @Param.

Hint:

~~~java
@Query("SELECT id, email FROM customers WHERE email = :emailAddress")
Mono<Customer> findByEmail(
    @Param("emailAddress") String email
);
~~~

### Exercise 2: Multiple conditions

Write a repository method to find orders by customerId, status, and createdAfter.

Hint:

~~~java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM orders
    WHERE customer_id = :customerId
      AND status = :status
      AND created_at >= :createdAfter
    """)
Flux<Order> search(
    @Param("customerId") Long customerId,
    @Param("status") String status,
    @Param("createdAfter") Instant createdAfter
);
~~~

### Exercise 3: Do derived queries need @Param?

Does the method findByFirstNameAndLastName(String firstName, String lastName) need @Param?

Hint: Not needed for query methods derived from the method name. Spring Data parses the method name and binds arguments according to that structure.

### Exercise 4: Null conditions

You want to find customers whose email is NULL. Can you bind null into email = :email to do this?

Hint: No. Use email IS NULL because comparing with NULL does not return TRUE.

### Exercise 5: Collections in IN

Write a method to find orders matching a set of statuses.

Hint:

~~~java
@Query("""
    SELECT id, status
    FROM orders
    WHERE status IN (:statuses)
    """)
Flux<Order> findByStatuses(
    @Param("statuses") Collection<String> statuses
);
~~~

Handle empty collections in the service layer before invoking the query.

### Exercise 6: SQL injection

Why shouldn't you concatenate search keywords directly into SQL statements?

Hint: Data can be interpreted as SQL syntax. Use placeholders and bind values as parameters.

## 16. Key takeaways

- @Param belongs to org.springframework.data.repository.query and links Java parameters to named placeholders in repository queries.
- With @Query, placeholders typically have the form :name and values are bound by name.
- The name in @Param must match the placeholder name; the Java variable name may differ.
- You can use multiple @Param annotations in one method and reuse one named parameter in multiple places.
- Derived query methods usually do not need @Param because Spring derives conditions from the method name.
- DatabaseClient uses the .bind() API, not @Param.
- Bind parameters are for values, not for substituting table names, column names, or SQL keywords.
- Do not compare NULL with an equals sign; use IS NULL when looking for null values.
- Handle empty collections before using IN and verify parameter types against the schema/driver.
- Use parameter binding instead of string concatenation to reduce SQL injection risks.
- For modifying queries, verify @Modifying and return signatures for your Spring Data R2DBC version.
- Test queries against a real database and driver, especially with specialized types and nulls.

When writing declared queries, pick clear placeholder names and bind each parameter with @Param. This approach keeps SQL separate from input data, makes repositories easier to read, and reduces errors when renaming variables or expanding query conditions.
