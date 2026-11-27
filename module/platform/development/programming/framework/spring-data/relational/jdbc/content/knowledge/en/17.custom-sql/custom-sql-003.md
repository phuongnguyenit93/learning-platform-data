# Named Queries and the META-INF/jdbc-named-queries.properties File

In **Spring Data Relational JDBC (Spring Data JDBC)**, a repository method can fetch data using a query derived from its method name, using SQL declared directly with `@Query`, or using a **named query** placed in a resource file on the classpath. Named queries let you separate SQL from the repository interface and keep statements in a central place with clear identifier keys.

In Spring Data JDBC, the default named queries file has the exact name:

`META-INF/jdbc-named-queries.properties`

Each query is declared with a key combining the **domain type name** and the **repository method name**. When the repository invokes the corresponding method, Spring Data looks up the named query by that key and executes the SQL with bound parameters.

## 1. When should you use a named query?

Suppose an application has a `Customer` entity and needs to find customers by last name. A simple query can be derived from the method:

~~~java
List<Customer> findByLastName(String lastName);
~~~

When the SQL becomes more complex—for example, needing joins, CTEs, database-specific functions, or reporting logic—you may want to write explicit SQL. There are three common options:

| Declaration style | Where does the SQL live? | Suitable when |
|---|---|---|
| Derived query | Repository method name | Simple property-based queries |
| `@Query` | Directly on the repository method | Short SQL tightly coupled to the method |
| Named query | `META-INF/jdbc-named-queries.properties` | Wanting to separate SQL from the interface or manage named statements centrally |

Named queries are helpful when SQL is long, needs to be read independently from Java code, or when many queries should be managed centrally. It is still concrete SQL targeting a schema/database, not an abstract query language.

## 2. File structure and location

In a standard Gradle or Maven application, place the resource at:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/customer/
    │       ├── Customer.java
    │       └── CustomerRepository.java
    └── resources/
        └── META-INF/
            └── jdbc-named-queries.properties
~~~

The source path is `src/main/resources/META-INF/jdbc-named-queries.properties`. During the build, the file is copied to the application classpath; Spring Data JDBC looks up the resource by its default name `META-INF/jdbc-named-queries.properties`.

Do not place the file inside a Java package such as `src/main/java/com/example/...`, and do not rename it arbitrarily to `named-queries.properties` unless you have configured another lookup mechanism. The resource name and location are part of the convention.

In multi-module applications, the file must reside in the resources of a module packaged into the runtime classpath where the repository runs. A file located in another module that is not included on the runtime classpath will not be found.

## 3. Query naming rules

A named query key is formed from the **domain class name** and the **repository method name**, joined by a dot:

~~~text
<DomainType>.<repositoryMethodName>
~~~

Examples:

| Domain type | Repository method | Key in properties |
|---|---|---|
| `Customer` | `findByLastName` | `Customer.findByLastName` |
| `Order` | `findRecentOrders` | `Order.findRecentOrders` |
| `Product` | `countAvailableProducts` | `Product.countAvailableProducts` |

The method name must match the method declared on the repository exactly, including case sensitivity. The domain type name is the name of the domain class managed by the repository; do not substitute the SQL table name for the class name.

For example, if the domain class is `CustomerProfile` and the method is `findActiveProfiles`, the key will be `CustomerProfile.findActiveProfiles`, even if the table is named `customer_profiles`.

## 4. Complete example: finding Customer by last name

### Domain entity

~~~java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("first_name")
    private String firstName;

    @Column("last_name")
    private String lastName;

    protected Customer() {
        // For Spring Data JDBC.
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }
}
~~~

### Repository method

~~~java
package com.example.customer;

import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByLastName(
        @Param("lastName") String lastName
    );
}
~~~

The method does not have `@Query`. Spring Data JDBC can look up the named query by the key `Customer.findByLastName`.

### The jdbc-named-queries.properties file

~~~properties
Customer.findByLastName=SELECT id, first_name, last_name FROM customers WHERE last_name = :lastName ORDER BY id
~~~

When calling:

~~~java
List<Customer> customers =
    customerRepository.findByLastName("Nguyen");
~~~

Spring Data JDBC looks up the SQL in the resource, binds the `lastName` value to the `:lastName` parameter, executes it, and maps the result rows into a list of `Customer` instances.

## 5. Named parameters and parameter safety

Named queries use named parameters with the `:parameterName` syntax:

~~~properties
Customer.findByName=SELECT id, first_name, last_name FROM customers WHERE first_name = :firstName AND last_name = :lastName
~~~

Repository:

~~~java
List<Customer> findByName(
    @Param("firstName") String firstName,
    @Param("lastName") String lastName
);
~~~

The name after the colon must match the parameter name recognized by Spring Data. Using explicit `@Param` avoids relying on whether the compiler preserves Java parameter names.

**Do not concatenate input values into SQL.** Write `WHERE last_name = :lastName` and let Spring Data/JDBC bind the parameter. This separates data from SQL syntax, handles escaping properly, and prevents SQL injection from user values.

Do not do this:

~~~java
String sql = "SELECT * FROM customers WHERE last_name = '" + lastName + "'";
~~~

Named queries do not automatically turn column names or table names into parameters. Identifiers such as table names, column names, and sort directions must be fixed in SQL. If dynamic sorting selection is needed, use an appropriate sorting/query API or build SQL in a controlled way from an allowlist; never bind identifiers as values.

## 6. Properties format and multi-line SQL

`jdbc-named-queries.properties` is a Java properties file, not YAML or a SQL script. Each entry has the form:

~~~properties
query.key=SQL statement
~~~

Lines starting with `#` or `!` can be used as comments:

~~~properties
# Queries for CustomerRepository
Customer.findByLastName=SELECT id, first_name, last_name FROM customers WHERE last_name = :lastName
~~~

For long SQL statements, you can use a trailing backslash `\` for line continuation according to Java properties rules:

~~~properties
Customer.searchDirectory=SELECT id, first_name, last_name \
    FROM customers \
    WHERE last_name = :lastName \
    ORDER BY last_name, first_name, id
~~~

The trailing `\` indicates that the property value continues on the next line. Leading whitespace on continuation lines is stripped according to properties rules; check the joined SQL if formatting relies on meaningful whitespace.

If the SQL contains special properties characters such as trailing backslashes or escape sequences, follow Java properties escaping rules. A simple approach is to keep SQL on a single line or use clear line continuations.

## 7. Named queries can be used for complex queries

Suppose you need to find Customers who have at least one confirmed Order. SQL can use `EXISTS`:

~~~properties
Customer.findCustomersWithConfirmedOrders=SELECT c.id, c.first_name, c.last_name FROM customers c WHERE EXISTS (SELECT 1 FROM sales_orders o WHERE o.customer_id = c.id AND o.status = :status) ORDER BY c.id
~~~

Repository:

~~~java
List<Customer> findCustomersWithConfirmedOrders(
    @Param("status") String status
);
~~~

Call:

~~~java
List<Customer> customers =
    customerRepository.findCustomersWithConfirmedOrders("CONFIRMED");
~~~

This named query returns `Customer` roots, not a list of `Order`s. It only uses the `sales_orders` table in the filter condition. `Customer` remains a separate aggregate and `Order` remains a separate aggregate.

Another example is a statistical query with a scalar result:

~~~properties
Customer.countCustomersWithOrders=SELECT COUNT(DISTINCT c.id) FROM customers c JOIN sales_orders o ON o.customer_id = c.id
~~~

The repository can declare:

~~~java
long countCustomersWithOrders();
~~~

The return type must be compatible with the value returned by the query. For a scalar query, do not declare the method to return `Customer` because the result does not contain columns to map into an entity.

## 8. Named query vs. @Query: choose one place to declare

If SQL is placed directly on the repository:

~~~java
@Query("""
    SELECT id, first_name, last_name
    FROM customers
    WHERE last_name = :lastName
    ORDER BY id
    """)
List<Customer> findByLastName(
    @Param("lastName") String lastName
);
~~~

This uses `@Query` instead of a named query. When a method has a query declared directly via annotation, that query is used for the method; a named query with the same key is not the source to edit for that method.

Guidelines for choosing:

- **Derived query** when the method name can express simple conditions.
- **`@Query`** when SQL is short and reviewers benefit from seeing it right next to the method.
- **Named query** when SQL is long, needs to be separated from the Java interface, or you want to manage SQL in a separate resource.

Do not maintain the same SQL in both `@Query` and properties expecting the two copies to stay in sync automatically. Choose a single source of declaration per method to avoid editing the wrong place.

## 9. Named queries, derived queries, and the query lookup process

When a repository method has no `@Query`, Spring Data can look up a named query by naming convention. If no matching named query exists, the framework can generate a query from the method name according to the default query lookup strategy.

Example:

~~~java
List<Customer> findByLastName(String lastName);
~~~

This can work as a derived query if no named query entry exists. Once you add the entry:

~~~properties
Customer.findByLastName=SELECT id, first_name, last_name FROM customers WHERE last_name = :lastName
~~~

that method will use the declared SQL. This allows switching from a derived query to explicit SQL without changing the method name called by services.

If you want explicit SQL without relying on conventions, `@Query` is the clearer choice. When debugging, verify the method name, domain type name, properties key, and classpath resource before concluding the repository failed to find the SQL.

## 10. SQL results must match the return type

Named queries do not automatically convert every result set into any arbitrary Java type. The SQL must return columns and data types matching the method's result type:

| Return type | SQL result shape |
|---|---|
| `Customer` | One row with columns mapped to Customer |
| `Optional<Customer>` | Zero or one Customer row |
| `List<Customer>` | Multiple Customer rows |
| `long` | A numeric value, typically COUNT |
| `boolean` | A boolean value compatible with driver/mapping |
| Projection/DTO | Columns/aliases corresponding to projection properties |

For entities, the query should return the primary key and all required mapped columns. If the entity has `@Column("first_name")`, the SQL column name must be recognized accurately by the mapping. Use aliases when querying expressions or when column names differ from properties.

### Join queries do not automatically turn other aggregates into child objects

SQL can join multiple tables to filter or build a projection, but joining in SQL does not automatically change aggregate boundaries. If the repository method returns `Customer`, ensure the result set matches the Customer mapping. If you need a DTO combining Customer and Order data, declare a separate projection/DTO and alias columns clearly.

For aggregates with child collections, do not assume a custom query joining child tables will automatically build the full object graph like `findById`. Design the result according to the query contract and verify mapping for the Spring Data JDBC version in use; when you need to load the aggregate via standard mapping, use the appropriate repository operation.

## 11. Named queries across database dialects

A properties file can contain many statements, but the SQL must still be compatible with the running database. If the same application supports PostgreSQL and MySQL, avoid assuming a complex query runs identically on both.

Differences can arise in:

- String, date/time, and JSON functions.
- Pagination syntax, CTEs, or vendor-specific expressions.
- Data type casting syntax.
- Function names and generated column syntax.
- Return types of aggregate functions.

If the SQL uses standard syntax common to both, a single named query can serve both. If dialect-specific SQL is needed, organize resources/configuration using an explicit application strategy, or use a custom repository/implementation to select the right statement. Do not put two entries with the same key in one properties file expecting the framework to pick by database.

## 12. Organizing multiple named queries

One file can manage queries for multiple domain types:

~~~properties
# Customer
Customer.findByLastName=SELECT id, first_name, last_name FROM customers WHERE last_name = :lastName
Customer.findByName=SELECT id, first_name, last_name FROM customers WHERE first_name = :firstName AND last_name = :lastName

# Order
Order.findRecentOrders=SELECT id, customer_id, status, created_at FROM sales_orders WHERE created_at >= :since ORDER BY created_at DESC
Order.countByCustomer=SELECT COUNT(*) FROM sales_orders WHERE customer_id = :customerId

# Product
Product.findBySku=SELECT id, sku, unit_price, stock_quantity FROM products WHERE sku = :sku
~~~

Helpful conventions:

- Group entries by domain type and add comments so readers can locate them easily.
- Each key appears only once in the final resource.
- Match method names exactly with the repository.
- Use clear named parameter names that match `@Param`.
- Keep column/alias order consistent with entities or projections.
- Never store passwords, tokens, or secrets inside SQL properties.

When the number of queries grows large, you can split by module or custom query infrastructure if the application supports it; however, the default resource Spring Data JDBC looks for is `META-INF/jdbc-named-queries.properties`.

## 13. Verifying that a named query is loaded

When a method does not run the expected SQL, check layer by layer:

1. **Resource path:** Is the file in `src/main/resources/META-INF/`?
2. **Classpath:** Is the file packaged in the build resources/JAR output of the runtime module?
3. **Key:** Does the key follow `DomainType.methodName`?
4. **Method:** Does the repository declare the method with the exact name and parameters?
5. **Parameter:** Does `:parameterName` match `@Param("parameterName")`?
6. **SQL:** Are table/column names, parameter types, and syntax valid for the dialect?
7. **Result mapping:** Does the query return sufficient columns and types compatible with the method return type?

You can check whether the resource was copied after building by inspecting the module's resources output or listing JAR contents. Example with Gradle:

~~~powershell
Get-Content .\build\resources\main\META-INF\jdbc-named-queries.properties
~~~

This example path assumes you are inside the module containing the application and have run the appropriate build/resources task. If the project uses a different source set or module layout, check the corresponding classpath output.

To observe SQL and bind parameters during development, enable appropriate logging for Spring JDBC and Spring Data Relational for your version. Do not enable logging of sensitive values in production.

## 14. Common mistakes

| Symptom | Possible cause | How to fix |
|---|---|---|
| Named query not found | Wrong filename or wrong directory | Use `META-INF/jdbc-named-queries.properties` on the classpath |
| Query is ignored even though file exists | Key does not match domain type or method name | Verify exact `<DomainType>.<methodName>` |
| Method runs derived query instead of file SQL | Missing key entry or resource not packaged | Check key and resources/JAR output |
| Missing parameter error | `:name` does not match parameter name | Use explicit `@Param("name")` |
| SQL injection or quote errors | Concatenating input strings into SQL | Use named parameters and bind values |
| Column not found error | SQL uses table/column names different from schema | Compare against DDL and `@Column` mappings |
| Result mapping error | Query missing ID/required columns or wrong aliases | Return columns compatible with entity/projection |
| Query works on PostgreSQL but fails on MySQL | Uses dialect-specific syntax/functions | Write compatible SQL or separate strategies by dialect |
| Properties split incorrectly across lines | Improper line continuation or escaping | Check Java properties rules and resulting SQL string |
| Edited SQL but app still uses old version | Resource in build output/JAR was not updated | Rebuild/restart the running artifact |

## 15. Practice exercises

1. Create a `Customer` entity mapped to the `customers` table and a repository with a `findByLastName` method.
2. Create `src/main/resources/META-INF/jdbc-named-queries.properties` with the key `Customer.findByLastName`.
3. Write SQL with the named parameter `:lastName` and declare the method parameter with `@Param("lastName")`.
4. Call the method with a last name containing accented characters; verify the correct result is returned.
5. Add the named query `Customer.findCustomersWithConfirmedOrders` using `EXISTS` to filter customers with CONFIRMED orders.
6. Add a query counting Customers with Orders and declare the method returning `long`.
7. Temporarily change the key to `Customer.findByLastNames` (wrong name) to observe that the framework does not use that entry; restore the correct key afterward.
8. Put the same SQL into `@Query` on the method and observe that the directly declared annotation is used; then remove the annotation so the method uses the named query again.
9. Pass an input containing a single quote and verify that parameter binding still treats it as data rather than SQL syntax.
10. Verify that the properties file is packaged into the output/JAR and that the application still finds it when run from the built artifact.

## 16. Key takeaways

Spring Data JDBC named queries are declared in the `META-INF/jdbc-named-queries.properties` resource. Each entry uses a `DomainType.methodName` key with a SQL value; the corresponding repository method supplies parameters for the framework to bind to placeholders such as `:lastName`.

Named queries keep SQL separate from Java interfaces, but still require careful management of key names, classpath resources, dialects, return types, and column mappings. Use derived queries for simple conditions, `@Query` for short method-adjacent SQL, and named queries when you want to manage SQL in a separate resource. Always bind values rather than concatenating input strings, and ensure result sets match the entity or projection declared by the repository method.
