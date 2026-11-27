# Naming Strategies and Quoted Identifier Handling

## 1. Why Must Table and Column Names Be Managed Consistently?

When mapping Java entities to a relational database, an application must convert class and property names into table and column names. In Java, names commonly use camelCase such as `createdAt`, `customerId`; in the database, a development team might choose snake_case such as `created_at`, `customer_id`. Table names may also follow class names, business terms, or a custom convention.

Beyond naming conventions, SQL also has the concept of an **identifier**: the name of a database, schema, table, column, alias, or sequence. Some identifiers collide with SQL keywords or contain uppercase letters, spaces, or special characters. In those cases, the database may require the identifier to be enclosed in appropriate quotes.

In Spring Data Relational, including Spring Data R2DBC, these two concerns are handled through:

- **Naming strategy**: rules for deriving table names, column names, and linking columns from the Java model.
- **Quoted identifier**: metadata indicating that an identifier must be quoted when Spring Data generates SQL.

This lesson focuses on choosing naming conventions, overriding names with annotations, handling quoted identifiers, and coordinating mapping metadata with hand-written SQL.

## 2. Identifiers Differ from Data Values

You must distinguish SQL object names from values passed into a statement.

~~~sql
SELECT customer_id, status
FROM orders
WHERE customer_id = 42;
~~~

In the SQL statement above:

- `orders` is a table name.
- `customer_id` and `status` are column names.
- `42` is a data value used in the condition.

Table and column names are **identifiers**. Values such as IDs, emails, statuses, or dates are **data values**. The two categories follow different handling rules.

For data values, use bind parameters:

~~~java
databaseClient.sql("""
        SELECT customer_id, status
        FROM orders
        WHERE customer_id = :customerId
        """)
    .bind("customerId", customerId)
    .map((row, metadata) -> row.get("status", String.class))
    .one();
~~~

Bind parameters let the driver pass values with the right types and avoid concatenating user data directly into SQL strings. You cannot use a bind parameter to substitute a table or column name. For example, `FROM :tableName` does not mean the driver will replace the parameter with an SQL identifier.

If a table or column name truly has to vary by runtime selection, use an allowlist of predefined identifiers and build SQL according to safe rules. Never concatenate arbitrary identifier names directly from user requests.

## 3. Default NamingStrategy in Spring Data Relational

Spring Data Relational uses **NamingStrategy** to derive relational names from classes and properties. The default convention typically converts camelCase names to snake_case.

Examples:

| Java Model | Common Default Identifier |
|---|---|
| Class `CustomerOrder` | Table `customer_order` |
| Property `createdAt` | Column `created_at` |
| Property `customerId` | Column `customer_id` |
| Property `postalCode` | Column `postal_code` |

The purpose of a naming strategy is to let the Java model keep naming conventions natural to the programming language while the database uses a consistent relational convention. As a result, you do not need annotations on every property when names already follow the convention.

Actual names are also influenced by mapping annotations, schemas, dialects, and the Spring Data version. When integrating with an existing schema, check mapping metadata and actual SQL rather than merely guessing from class names.

### 3.1. Where Does the Naming Strategy Apply?

`NamingStrategy` participates in deriving identifiers such as:

- Table names from entity types.
- Column names from properties.
- Key column names used to link component objects back to the aggregate root.
- Reverse reference column names in related collection mappings.

Explicit mapping annotations such as `@Table` and `@Column` allow specifying concrete names per entity or property. This is suitable when a legacy table follows a different convention from the rest of the application.

### 3.2. Do Not Assume Automatic Pluralization

The default naming strategy should not be assumed to automatically pluralize class names into plural nouns. For instance, class `CustomerOrder` is normally converted by camelCase rules into `customer_order`; do not assume the framework will automatically turn it into `customer_orders`.

If the schema uses plural names, abbreviations, or custom prefixes, declare them with annotations or supply a suitable naming strategy. What matters is that rules are consistent and match the deployed schema.

## 4. Overriding Table and Column Names with Annotations

### 4.1. Using @Table to Specify the Table Name

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;
}
~~~

Here, Spring Data uses the `purchase_orders` table for the `PurchaseOrder` entity. Explicit table naming keeps the Java model from being forced to match database table naming conventions.

You can specify a schema if the application needs to partition objects by schema. Annotation syntax and how the dialect generates SQL must be verified for the version in use. When multiple schemas or databases exist, specify the schema explicitly in metadata or appropriate connection configuration instead of relying on an implicit search path.

### 4.2. Using @Column to Specify the Column Name

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_status")
    private String status;

    @Column("customer_id")
    private Long customerId;
}
~~~

Java properties can remain `status` and `customerId`, while the database uses `order_status` and `customer_id`. This is helpful when connecting to an existing schema or when column names must reflect specific database terminology.

Explicit annotations also let readers see the mapping immediately without inspecting the entire naming strategy. However, do not repeat annotations on every property when default names already follow the convention.

### 4.3. Column Names in Component Mappings

For collections mapped with `@MappedCollection`, the column linking to the aggregate root and the collection key column are also identifiers. Metadata example:

~~~java
@MappedCollection(idColumn = "order_id", keyColumn = "line_no")
private List<OrderLine> lines;
~~~

- `idColumn` specifies the column in the component table used to store the aggregate root's ID.
- `keyColumn` specifies the column used as the key or position of the collection element per mapping.

These names must match the schema. If the schema uses legacy names or names requiring quoting, specify them using the quoted identifier syntax supported by Spring Data Relational. Inspect generated SQL and the actual schema when using collection mappings.

## 5. What Is a Quoted Identifier?

### 5.1. Why Does SQL Have Identifier Quotes?

In SQL, an unquoted identifier is typically processed by the database using its own lexical and normalization rules. A quoted identifier is treated as an explicitly specified name, allowing names that match keywords, preserve uppercase/lowercase, or contain special characters forbidden by unquoted rules.

PostgreSQL example:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30)
);
~~~

The names `orders` and `status` need no quotes. PostgreSQL normalizes unquoted identifiers to lowercase.

If a table is created with quoted uppercase letters:

~~~sql
CREATE TABLE "PurchaseOrder" (
    "OrderId" BIGINT PRIMARY KEY,
    "orderStatus" VARCHAR(30)
);
~~~

Quoted identifiers preserve exact uppercase/lowercase casing. When querying, you must use the exact name as created:

~~~sql
SELECT "OrderId", "orderStatus"
FROM "PurchaseOrder";
~~~

The query `SELECT OrderId FROM PurchaseOrder` is not equivalent to the query above in PostgreSQL, because unquoted identifiers are folded to lowercase.

### 5.2. SQL Keywords and Names with Special Characters

Words such as `order`, `group`, `user`, or `select` can conflict with SQL syntax depending on the database and context. Identifiers containing spaces or special characters also commonly require quoting.

For instance, a table named `Order` or a column named `group` can make SQL hard to read or cause syntax errors if used improperly. You can resolve this in two ways:

1. Rename the table/column to a safe name, such as `purchase_orders`, `order_group`.
2. Keep the current name, mark the identifier as requiring quoting, and write it accurately in SQL.

If you have control over designing a new schema, prefer simple, consistent names and avoid SQL keywords. Quoted identifiers are useful when integrating legacy schemas or when preserving existing names is mandatory.

## 6. Marking Quoted Identifiers in Spring Data Relational

Spring Data Relational has a mechanism to represent quoted identifiers in mapping metadata. When declaring a name in an annotation, you can wrap the identifier in **backticks** to mark that it needs quoting.

Example:

~~~java
@Table("`Order`")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("`group`")
    private String group;
}
~~~

In Spring Data metadata, backticks mark a quoted identifier. When generating SQL, Spring Data applies the quoting rule appropriate for the database dialect. Do not assume that backticks are always sent verbatim to the database.

With PostgreSQL, the corresponding identifiers can be rendered with double quotes:

~~~sql
SELECT "id", "group"
FROM "Order";
~~~

Quoting syntax at the SQL layer depends on the database. For example, PostgreSQL uses double quotes for quoted identifiers; MySQL commonly uses backticks; SQL Server supports square brackets or double quotes when configured appropriately for quoted identifiers. Spring Data relies on the dialect to process identifiers marked as quoted in metadata.

### 6.1. Quoting Preserves Casing

Suppose a PostgreSQL schema has a table created as follows:

~~~sql
CREATE TABLE "PurchaseOrder" (
    "OrderId" BIGINT PRIMARY KEY,
    "orderStatus" VARCHAR(30)
);
~~~

Entity mapping must preserve the exact spelling of each identifier:

~~~java
@Table("`PurchaseOrder`")
public class PurchaseOrder {

    @Id
    @Column("`OrderId`")
    private Long id;

    @Column("`orderStatus`")
    private String status;
}
~~~

If you quote only the table name without quoting columns that need casing preserved, SQL may look up the wrong column. Conversely, if the schema uses unquoted lowercase names, quoting an uppercase name turns it into a different identifier in PostgreSQL.

The critical rule is that **names and quoted/unquoted status in mapping must match the created schema**. Do not add quotes arbitrarily hoping the database will ignore case differences.

### 6.2. Quoted Identifiers with @MappedCollection

Collection linking columns must also match the schema. Metadata example:

~~~java
@MappedCollection(
        idColumn = "`order_id`",
        keyColumn = "`line_no`"
)
private List<OrderLine> lines;
~~~

Quoted notation must be verified against the Spring Data Relational version in use and the corresponding dialect. If the schema uses lowercase snake_case names that are not keywords, these columns usually do not need quoting.

### 6.3. Using SqlIdentifier in the Mapping API

At the Spring Data Relational layer, identifiers are also represented by the **SqlIdentifier** type. This type stores the name and quoted/unquoted state separately, instead of concatenating quote characters into every SQL string.

Example of API semantics:

~~~java
SqlIdentifier.unquoted("customer_order");
SqlIdentifier.quoted("PurchaseOrder");
~~~

- `unquoted(...)` represents an identifier that does not require quoting.
- `quoted(...)` represents an identifier that must be quoted when rendering SQL.

When the identifier is rendered, the dialect is responsible for applying the appropriate quote character. Do not embed double quotes or backticks inside the content of `SqlIdentifier` and then mark it quoted, as that can produce double-quoting or names that fail to match the schema.

## 7. When Should You Quote Identifiers?

Consider quoting in the following cases:

| Case | Example | Handling |
|---|---|---|
| Collides with SQL keyword | `order`, `group` | Rename if possible; if it must be kept, quote |
| Must preserve casing | `PurchaseOrder` | Quote consistently in schema and mapping |
| Name contains spaces | `Order Details` | Quote, though renaming should be considered |
| Name has special characters | `customer-code` | Quote or change to a simple name |
| Legacy schema | Tables/columns already created with custom rules | Map explicitly and quote properly when needed |
| Standard snake_case name | `customer_order` | Usually no quoting needed |

Quoting is not a tool to fix every naming problem. Whenever you can alter the schema, simple names are easier to work with across hand-written SQL, migrations, reports, admin tools, and multiple database systems.

## 8. Custom NamingStrategy

### 8.1. When Is a Custom Naming Strategy Needed?

A project may have to follow specific conventions, for example:

- All tables have an `app_` prefix.
- Table and column names follow a custom snake_case rule.
- Tables are grouped by schema.
- Foreign key columns follow a consistent convention.
- A new system must remain compatible with a legacy database whose names do not follow default rules.

When there are many overrides, writing `@Table` and `@Column` on every class can produce repetitive metadata. A custom `NamingStrategy` centralizes the rules in one place.

### 8.2. Concept for Configuring NamingStrategy

You can provide a **NamingStrategy** bean in the application context for Spring Data Relational to use when deriving identifiers.

Illustrative example of a strategy that adds a `tbl_` prefix to table names and converts class names to snake_case:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.NamingStrategy;
import org.springframework.data.relational.core.sql.SqlIdentifier;

@Configuration
class RelationalNamingConfiguration {

    @Bean
    NamingStrategy namingStrategy() {
        return new NamingStrategy() {
            @Override
            public SqlIdentifier getTableName(Class<?> type) {
                String snakeCase = type.getSimpleName()
                        .replaceAll("([a-z0-9])([A-Z])", "$1_$2")
                        .toLowerCase(Locale.ROOT);

                return SqlIdentifier.unquoted("tbl_" + snakeCase);
            }
        };
    }
}
~~~

With the `CustomerOrder` class, the derived table name is `tbl_customer_order`. Methods that are not overridden continue using `NamingStrategy`'s default behavior if the Spring Data version provides corresponding default implementations.

This is an example of a simple rule. In real implementations, check the `NamingStrategy` API for your exact Spring Data Relational version, especially if customizing schema, column, key column, or reverse column names. Also confirm that Spring Boot auto-configuration picks up the custom bean.

### 8.3. Customizing Column Names

If a project wants custom rules for properties, you can override the method that derives column names. Conceptual example:

~~~java
@Override
public SqlIdentifier getColumnName(RelationalPersistentProperty property) {
    return SqlIdentifier.unquoted(
            property.getName().replaceAll("([a-z0-9])([A-Z])", "$1_$2")
                    .toLowerCase(Locale.ROOT));
}
~~~

This snippet assumes `RelationalPersistentProperty` is imported from Spring Data Relational. Keep it consistent with foreign key and collection column naming rules; if you override only regular column names while ignoring key/reverse columns, the schema may not match the SQL generated by mapping.

### 8.4. When Should You Use Annotations Instead of a Strategy?

Use annotations when a single entity or property is an isolated exception:

~~~java
@Table("legacy_customer")
class Customer {
    @Id
    private Long id;

    @Column("CUST_EMAIL")
    private String email;
}
~~~

Use `NamingStrategy` when a rule repeats across many entities and needs centralized management. Both can be combined: the strategy supplies defaults for most of the model, while annotations override special cases.

Avoid building overly complex naming strategies full of unpredictable exceptions. Clear rules backed by integration tests keep schemas more stable.

## 9. Quoted Identifiers in Hand-Written SQL

Mapping metadata and hand-written SQL are two separate contexts.

When using repositories or entity-mapping templates, Spring Data has metadata about tables, columns, and quoting status. When writing SQL directly via `@Query` or `DatabaseClient`, however, the developer is responsible for writing identifiers using the database's syntax.

PostgreSQL example with quoted table and column names:

~~~java
return databaseClient.sql("""
        SELECT "OrderId", "orderStatus"
        FROM "PurchaseOrder"
        WHERE "orderStatus" = :status
        """)
    .bind("status", status)
    .map((row, metadata) ->
            row.get("OrderId", Long.class))
    .all();
~~~

Here:

- `"PurchaseOrder"`, `"OrderId"`, and `"orderStatus"` are identifiers quoted in PostgreSQL syntax.
- `:status` is a bind parameter for a data value.
- `DatabaseClient` cannot substitute identifiers using bind parameters.

If porting this SQL statement to MySQL or SQL Server, check and adjust the quoting syntax to the target dialect. Do not copy PostgreSQL double quotes verbatim across every database.

### 9.1. Identifiers in @Query

With `@Query`, SQL is written explicitly. If the schema uses identifiers requiring quoting, apply the quoting style required by the target database. The `@Table` mapping annotation does not automatically rewrite identifiers inside custom SQL strings.

~~~java
@Query("""
    SELECT "OrderId", "orderStatus"
    FROM "PurchaseOrder"
    WHERE "orderStatus" = :status
    """)
Flux<OrderSummary> findByStatus(String status);
~~~

Bind parameter names must match how Spring Data binds method parameters in the version being used. For complex queries, `@Param` can be declared to make parameter names explicit.

### 9.2. Never Concatenate Identifiers from Untrusted Input

Do not write:

~~~java
String sql = "SELECT * FROM " + request.getParameter("table");
~~~

This approach lets input directly alter SQL structure. Bind parameters do not apply to table names, so you must use an allowlist if dynamic table selection is truly required:

~~~java
Map<String, String> allowedTables = Map.of(
        "orders", "orders",
        "customers", "customers"
);

String table = allowedTables.get(requestedResource);
if (table == null) {
    return Mono.error(new IllegalArgumentException("Unsupported resource"));
}

String sql = "SELECT id FROM " + table + " WHERE status = :status";

return databaseClient.sql(sql)
        .bind("status", status)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
~~~

The example only illustrates the allowlist principle. In real systems, avoid dynamic tables unless clearly necessary; if used, values taken from the allowlist must be application-controlled identifiers, never arbitrary strings from a request.

## 10. Quoting and Case-Sensitivity Differences Across Databases

Identifier quoting syntax and normalization rules are not identical across database management systems.

| Database | Common Identifier Quoting Style | Notable Rules |
|---|---|---|
| PostgreSQL | Double quotes: `"name"` | Unquoted identifiers are folded to lowercase; quoted identifiers preserve casing |
| MySQL | Backticks, e.g., `name` | Backticks are commonly used to quote; table-name case sensitivity also depends on the OS and configuration |
| SQL Server | Square brackets: `[name]` or double quotes in suitable mode | Check `QUOTED_IDENTIFIER` setting and collation |
| Oracle | Double quotes: `"name"` | Unquoted identifiers are typically folded to uppercase; quoted identifiers preserve casing |

Spring Data Relational uses the dialect to render identifiers that carry quoted status. Hand-written raw SQL, however, must still match the syntax of the connected database.

### 10.1. PostgreSQL Example

Unquoted names:

~~~sql
CREATE TABLE customer_order (
    customer_id BIGINT,
    created_at TIMESTAMP
);
~~~

They can be queried using unquoted lowercase or uppercase because PostgreSQL folds unquoted identifiers:

~~~sql
SELECT CUSTOMER_ID, CREATED_AT
FROM CUSTOMER_ORDER;
~~~

Quoted names with uppercase letters:

~~~sql
CREATE TABLE "CustomerOrder" (
    "CustomerId" BIGINT,
    "CreatedAt" TIMESTAMP
);
~~~

In that case, you must use the exact spelling:

~~~sql
SELECT "CustomerId", "CreatedAt"
FROM "CustomerOrder";
~~~

### 10.2. Avoid Mixing Two Conventions

A schema mixing `customer_order`, `CustomerOrder`, `CUSTOMER_ORDER`, and differently quoted identifiers is hard to maintain. Standardize rules when creating new schemas and document exceptions in legacy schemas.

If the database already exists, inspect actual database metadata before changing annotations. Changing quoting can cause the application to target a different identifier even when display names look nearly identical.

## 11. Common Errors When Naming and Quoting Identifiers

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Table or column does not exist | `NamingStrategy` derives a name different from the schema | Use `@Table`/`@Column` or adjust strategy to match |
| Syntax error near SQL keyword | Identifier collides with a reserved word without being quoted | Rename or mark as a quoted identifier |
| PostgreSQL reports relation/column does not exist despite matching-looking name | Case mismatch between quoted and unquoted identifiers | Inspect exact names in catalog and use matching spelling |
| Repository works while `@Query` fails | Mapping metadata does not rewrite identifiers in raw SQL | Quote according to dialect inside the query |
| SQL works on PostgreSQL but fails on MySQL | Uses quoting syntax or features specific to another database | Use the appropriate dialect and SQL |
| Collection mapping cannot find linking column | `idColumn`/`keyColumn` does not match schema | Check `@MappedCollection` and DDL |
| Table name has wrong prefix | Custom `NamingStrategy` is not applied or was overridden | Check bean, auto-configuration, and annotations |
| Table name is double-quoted or contains quote characters in the name | Mixed SQL quote characters into an identifier already marked quoted | Use `SqlIdentifier.quoted` or proper annotation syntax without manual quotes |

### 11.1. Missing Table or Column Errors

For example, Spring Data defaults to `purchase_order`, while the real schema is `purchase_orders`. The database reports that the relation/table does not exist. Verify the mapped name, naming strategy, and explicit annotations.

With PostgreSQL, also check the active schema and `search_path`. A table existing in another schema may still not be found if the connection uses a different default schema.

### 11.2. Reserved Word Errors

If a column is named `group`, hand-written SQL may parse it as a keyword. Rename it to `customer_group`, or quote properly for the database. When using mapping metadata, mark quoted identifiers in annotations rather than embedding SQL quote characters everywhere.

### 11.3. Case-Sensitivity Errors

In PostgreSQL, unquoted `OrderId` and quoted `"OrderId"` are not handled identically. Unquoted identifiers are folded to lowercase, whereas quoted identifiers preserve casing. Check the original DDL and system catalog to verify exact names.

### 11.4. Hand-Written SQL Not Matching Mapping Rules

Entity mapping may specify `@Table("`PurchaseOrder`")`, yet `@Query` still uses `FROM purchase_order`. The two statements reference two different identifiers. Use the exact name and quoting in hand-written SQL.

## 12. Workflow for Choosing a Naming Strategy for a Project

You can apply the following sequence when designing a schema or integrating an existing database:

1. **Identify database conventions:** snake_case, lowercase, table prefixes, schemas, and foreign key naming conventions.
2. **Inspect existing identifiers:** read DDL or database metadata to see exact names and quoting status.
3. **Select NamingStrategy:** use the default if suitable; use a custom strategy if broad shared rules differ.
4. **Override exceptions:** use `@Table`, `@Column`, and related mapping annotations for special names.
5. **Quote only when needed:** prefer renaming to avoid reserved words; if kept, quote consistently.
6. **Synchronize raw SQL:** review `@Query`, `DatabaseClient`, and migrations so they use proper dialect identifiers.
7. **Run integration tests:** verify insert, select, update, delete, collection mapping, and migrations against a real database.
8. **Observe SQL:** enable controlled SQL logging in development to verify names render properly.
9. **Keep schemas stable:** rename tables/columns through versioned migrations instead of editing databases manually per environment.

Simple decision diagram:

~~~text
Do Java names follow the default convention?
             |
        +----+----+
        |         |
       Yes        No
        |         |
        v         v
  Use default   Use @Table /
  naming        @Column or custom
  strategy      NamingStrategy
        |         |
        +----+----+
             |
             v
  Does identifier have reserved words,
  preserved casing, or special characters?
             |
        +----+----+
        |         |
        No       Yes
        |         |
        v         v
   No quoting   Mark quoted
   needed       in mapping metadata
        |         |
        +----+----+
             |
             v
  Test mapping and raw SQL
  against the target database
~~~

## 13. Testing Mapping and Quoted Identifiers

Unit tests can verify domain logic, yet they are insufficient to confirm the database interprets table/column names as expected. Integration tests with a compatible database type and version matching deployment are required.

Scenarios to verify include:

- Entities using default camelCase names map properly to snake_case.
- `@Table` and `@Column` override schema names properly.
- Reserved-word identifiers are quoted and queried successfully.
- Identifiers with uppercase letters are accessed according to database rules.
- `@MappedCollection` uses the proper `idColumn` and `keyColumn`.
- `@Query` and `DatabaseClient` use quoting syntax matching the dialect.
- Migrations create the exact identifier names mapping expects.
- Insert, update, select, and delete all work on the real schema.

You can use Testcontainers to run an isolated database per test run. This prevents situations where tests pass on H2 yet fail on PostgreSQL or MySQL due to differences in identifiers, data types, and SQL dialects.

Do not merely verify that Spring `ApplicationContext` starts. Execute real queries or save/read an entity to confirm mapping works end-to-end.

## 14. Conclusion

`NamingStrategy` enables Spring Data Relational to derive table names, column names, and linking identifiers from the Java model under a consistent convention. When matching legacy schemas or exceptions, you can override with `@Table`, `@Column`, `@MappedCollection`, or provide a custom `NamingStrategy`.

Quoted identifiers address names colliding with SQL keywords, needing preserved casing, or containing special characters. Spring Data Relational allows marking quoted identifiers in mapping metadata and uses the dialect to render appropriate quote characters. For hand-written SQL in `@Query` or `DatabaseClient`, developers remain responsible for using the target database's syntax.

Always distinguish identifiers from data values: table/column names cannot be substituted with bind parameters, while input values must be bound rather than concatenated. Simple naming conventions, explicit mapping metadata, and integration tests on a real database prevent missing-table/column errors and reduce discrepancies across environments.
