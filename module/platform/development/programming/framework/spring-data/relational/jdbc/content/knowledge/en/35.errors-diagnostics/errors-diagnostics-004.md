# Wrong Table/Column Names, Quoting, and Schema Search Path

When Spring Data JDBC reads or writes an aggregate, the framework generates SQL based on mapping metadata, naming strategy, dialect, and database configuration. If the table name, column name, or schema in the mapping does not match the actual database, SQL queries can fail even though the Java entity compiles cleanly.

Common issues include nonexistent tables, nonexistent columns, identifiers colliding with SQL keywords, case mismatches, or the connection looking for a table in a different schema. These errors sometimes share the same symptom, such as "table not found", yet stem from different root causes.

This lesson explains how Spring Data JDBC derives relational names, how to override them with annotations, how databases handle unquoted versus quoted identifiers, the role of schemas and search paths, and a workflow for comparing generated SQL against database metadata.

## 1. Where does Spring Data JDBC get table and column names?

Spring Data Relational uses mapping metadata to determine table, column, and join column names in an aggregate. When names are not specified explicitly, the framework applies the default naming strategy.

Example entity:

~~~java
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private LocalDateTime createdAt;
}
~~~

With the default naming strategy commonly used in Spring Data Relational, camelCase Java names are converted to snake_case. For example:

| Java property/type | Typical derived relational name |
|---|---|
| PurchaseOrder | purchase_order |
| orderNumber | order_number |
| createdAt | created_at |

The effective name is also influenced by any custom NamingStrategy, mapping annotations, and the Spring Data Relational version. When a database already has a schema created by another system, do not guess table or column names from class names; inspect the actual schema.

## 2. Overriding table names with @Table

If a table has a different name from the default, use @Table:

~~~java
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    // ...
}
~~~

If the table resides in a specific schema, you can declare the schema:

~~~java
@Table(value = "purchase_orders", schema = "sales")
public class PurchaseOrder {
    // ...
}
~~~

Verify annotation attributes and schema support against your project's Spring Data JDBC version. For databases or dialects with specific schema rules, verify the generated SQL.

When a schema is specified explicitly, the application does not have to rely entirely on the connection's default schema or search path to locate that table.

## 3. Overriding column names with @Column

Use @Column when a Java property name does not match the column name:

~~~java
import org.springframework.data.relational.core.mapping.Column;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_no")
    private String orderNumber;

    @Column("created_on")
    private LocalDateTime createdAt;
}
~~~

In this example, the Java properties remain orderNumber and createdAt, while Spring Data JDBC maps them to order_no and created_on.

### 3.1. Column mapping does not modify the schema

Annotations only alter the application's mapping metadata. They do not automatically create, rename, or migrate columns in the database.

If an entity uses:

~~~java
@Column("order_no")
private String orderNumber;
~~~

then the table must actually contain a column named order_no. If the database only has order_number, SQL statements will still fail with "column not found".

Keep entity mappings synchronized with migrations and schemas. Do not change annotations to mask an unapplied migration or schema drift across environments.

## 4. Collection column names and aggregate relationships

Spring Data JDBC persists aggregates using a relational structure. For child collections, pay attention to the child table, foreign key, and key column when the collection is ordered or uses a Map.

Example:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_number"
    )
    private List<OrderLine> lines;
}
~~~

Names to verify:

- Aggregate root table: purchase_orders.
- Table storing OrderLine according to the child type's mapping.
- Linking column idColumn in the child table: order_id.
- keyColumn if the collection needs to store position or map key: line_number.

If the child table uses a different foreign key column name, configure the mapping accordingly. A wrong idColumn typically causes loading or saving the collection to fail even when the root table works.

Do not confuse @Column with @MappedCollection: @Column maps a scalar property to a column; @MappedCollection describes how a child collection is stored within an aggregate.

## 5. NamingStrategy and Global Naming Rules

When many entities share a convention different from the default, you can supply a custom NamingStrategy instead of repeating annotations on every property.

NamingStrategy can determine names for:

- Tables from entity types.
- Columns from properties.
- Foreign key columns for collections.
- Key columns for collections.

Example illustrating table name customization for one entity:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.NamingStrategy;
import org.springframework.data.relational.core.sql.SqlIdentifier;

@Configuration
public class RelationalNamingConfiguration {

    @Bean
    NamingStrategy namingStrategy() {
        return new NamingStrategy() {

            @Override
            public SqlIdentifier getTableName(Class<?> type) {
                if (type == PurchaseOrder.class) {
                    return SqlIdentifier.unquoted("purchase_orders");
                }

                return NamingStrategy.INSTANCE.getTableName(type);
            }
        };
    }
}
~~~

This snippet illustrates the modern SqlIdentifier-based NamingStrategy API. Check the exact signature and registration mechanism for your project's Spring Data Relational version; older versions may have a different API.

A custom NamingStrategy is a broad mapping rule. Changing it can affect many entities, including child tables and linking columns. If only one or two names differ, @Table and @Column usually express intent more clearly.

## 6. What is an identifier and why does quoting matter?

Databases distinguish identifiers from data values. Table and column names are identifiers; strings bound in a WHERE clause are values.

Example:

~~~sql
SELECT order_number
FROM purchase_orders
WHERE status = ?;
~~~

Here purchase_orders, order_number, and status are identifiers. The value bound to ? is a parameter.

Prepared statements protect values from SQL injection, but table or column names cannot be bound as value parameters. Identifiers must be determined from mapping metadata or a whitelist and quoted according to the database's syntax when required.

### 6.1. SQL Keywords

Certain names easily collide with SQL keywords or syntax:

- order
- user
- group
- key
- rank
- value

For instance, a table named order can cause syntax errors because ORDER is a keyword in ORDER BY. The simplest fix is usually to choose a non-conflicting name like purchase_orders.

If you must remain compatible with an existing schema that uses special names, verify how identifiers are quoted for your database and mapping infrastructure.

## 7. Unquoted vs. Quoted Identifiers

Databases apply distinct rules to unquoted versus quoted identifiers. These rules affect case sensitivity and whether a name is interpreted as a keyword.

### 7.1. PostgreSQL

In PostgreSQL:

- Unquoted identifiers are folded to lowercase.
- Double-quoted identifiers preserve their exact casing and are case-sensitive.

Example:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY
);
~~~

The unquoted name purchase_orders is resolved as lowercase.

If a table is created as:

~~~sql
CREATE TABLE "PurchaseOrders" (
    id BIGINT PRIMARY KEY
);
~~~

then queries must use the exact quoted identifier:

~~~sql
SELECT * FROM "PurchaseOrders";
~~~

An unquoted query for PurchaseOrders is folded to lowercase by PostgreSQL and will not match the quoted mixed-case table name.

### 7.2. Oracle

Oracle typically folds unquoted identifiers to uppercase. Quoted identifiers preserve their casing and must be referenced consistently.

Consequently, schemas created with quoted mixed-case identifiers can cause friction when using auto-generated SQL or when multiple tools follow different conventions.

### 7.3. MySQL

MySQL uses backticks to quote identifiers. Case sensitivity for table names also depends on the operating system and the lower_case_table_names setting. Do not assume that because mixed-case table names work on a Windows machine, a Linux production environment will behave the same way.

### 7.4. Do not use one database's quote style for another

Common quoting styles:

| Database | Common identifier quoting |
|---|---|
| PostgreSQL | Double quotes: "name" |
| Oracle | Double quotes: "name" |
| MySQL | Backticks: name |
| SQL Server | Square brackets: [name], or double quotes when configured |

Spring Data JDBC's dialect and identifier processing generate database-appropriate SQL. Do not manually embed quote characters into every annotation or table name without verifying how the framework processes them.

## 8. Quoting in Spring Data Relational

Spring Data Relational represents relational names using SqlIdentifier. An identifier can carry quoted or unquoted semantics, and the dialect supplies identifier processing rules appropriate for the database.

If a generated mapping name needs quoting, a custom NamingStrategy can return a quoted SqlIdentifier:

~~~java
SqlIdentifier quotedName = SqlIdentifier.quoted("Order");
~~~

This example illustrates creating a quoted identifier. Feeding identifiers into mapping must go through the proper extension point for your Spring Data Relational version, such as NamingStrategy. Do not assume that adding quote characters inside a @Table or @Column string always yields a quoted identifier; depending on mapping behavior, the annotation may treat the entire string as a literal name.

Before choosing quoting for an existing schema, verify:

1. Which quoting rules the database used when creating object names.
2. Whether mapping produces a quoted or unquoted SqlIdentifier.
3. Which quote character the dialect uses.
4. Whether the actual SQL uses the expected name and casing.

Whenever possible, prefer lowercase/snake_case names that are not keywords and require no quoting. Simple conventions reduce errors across environments and migration tools.

## 9. Schemas and Search Path

A schema is a namespace containing tables and other database objects. A single database can contain multiple schemas with identically named tables:

~~~text
database
├── public
│   └── purchase_orders
├── sales
│   └── purchase_orders
└── archive
    └── purchase_orders
~~~

If a SQL statement only states:

~~~sql
SELECT * FROM purchase_orders;
~~~

the database must determine which schema to search first. That rule depends on the database engine and session configuration.

### 9.1. PostgreSQL search_path

PostgreSQL uses search_path to locate objects without a schema prefix. You can inspect it:

~~~sql
SHOW search_path;
SELECT current_schema();
~~~

If search_path does not include the sales schema, or another schema takes precedence, an unqualified query may target the wrong table or report relation does not exist.

You can specify the schema explicitly in the mapping:

~~~java
@Table(value = "purchase_orders", schema = "sales")
public class PurchaseOrder {
    // ...
}
~~~

Alternatively, configure search_path on the connection/session according to your application strategy. With connection pools, session state can persist on a connection and be reused by subsequent requests. If you alter search_path per request, make sure to reset state before returning the connection to the pool.

### 9.2. MySQL and database/catalog

In MySQL, a schema typically corresponds to a database. A connection can select a default database in the JDBC URL or qualify table names with the database/schema.

Check the current database:

~~~sql
SELECT DATABASE();
~~~

If the application connects to the wrong default database, the table may exist elsewhere while queries still report it missing.

### 9.3. SQL Server and default schema

SQL Server associates a default schema with a database user. Unqualified table names are resolved against the connecting user's default schema.

Verify the current schema or metadata using the application's actual user. Do not test solely with a DBA account if the application connects using an account with a different default schema.

## 10. Distinguishing Table Name Errors from Search Path Errors

Error messages can guide the investigation:

| Symptom | Possible cause |
|---|---|
| Table/relation does not exist | Wrong table name, wrong case, or wrong schema/search path |
| Invalid identifier | Wrong column name, case, or quoting |
| Column not found | @Column mismatches schema or migration has not run |
| Syntax error near table name | Identifier is a keyword or quoting is invalid |
| Permission denied | Table exists, but the user lacks permissions |
| Ambiguous column | JOIN query across multiple tables has duplicate column names without qualification |
| Works locally, fails in production | Different database, OS, search_path, schema, or naming configuration |

Do not rename the table immediately when you see "not found". First confirm whether the object exists in the exact database and schema the application connects to.

## 11. Inspecting Database Metadata

JDBC provides DatabaseMetaData to inspect tables and columns visible to the current connection:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    try (ResultSet tables = metadata.getTables(
            connection.getCatalog(),
            "sales",
            "purchase_orders",
            new String[] {"TABLE"})) {

        while (tables.next()) {
            System.out.println(tables.getString("TABLE_SCHEM"));
            System.out.println(tables.getString("TABLE_NAME"));
        }
    }
}
~~~

Catalog, schema pattern, and table pattern parameters have driver-specific semantics. If no results appear, check the current catalog/schema and how the driver handles case sensitivity.

You can also query the database's information schema or catalog views:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name = 'purchase_orders';
~~~

Inspect columns:

~~~sql
SELECT table_schema, table_name, column_name
FROM information_schema.columns
WHERE table_name = 'purchase_orders'
ORDER BY ordinal_position;
~~~

Run these queries using the exact same database user and connection settings as the application. Just because a DBA sees the table does not mean the application user has access permissions or the matching search path.

## 12. Comparing SQL Generated by Spring Data JDBC

When mappings look right yet queries still fail, inspect the actual SQL.

Steps:

1. Identify the repository method or aggregate operation that fails.
2. Enable JDBC logging appropriate for your Spring version, or use a SQL observation tool.
3. Capture the SQL after the framework generates the query.
4. Inspect table names, column names, schemas, and identifier casing.
5. Compare each identifier against database metadata.
6. Inspect parameter values separately from identifier names.

Tools like datasource-proxy or P6Spy can help observe SQL statements and execution times. Be careful with sensitive data in parameter logs; do not enable logging that exposes personal data or secrets in production without proper safeguards.

### 12.1. SQL inside @Query is developer-authored SQL

With custom queries:

~~~java
@Query("""
    SELECT id, order_no
    FROM sales.purchase_orders
    WHERE status = :status
    """)
List<OrderSummary> findSummaries(@Param("status") String status);
~~~

Table and column names inside the SQL string must match the database. Do not assume @Table or @Column will rewrite identifiers inside literal SQL strings.

If a migration renames a table, update all related custom queries, views, stored procedures, and SQL scripts.

## 13. Migrations and Schema Drift

A mapping may succeed in development yet fail in production because migrations are out of sync.

Examples:

- The entity changed @Column from order_number to order_no.
- The column-renaming migration has not run in production.
- One environment has sales.purchase_orders while another only has public.purchase_orders.
- A database was created manually with quoted mixed-case names.
- The migration tool ran under a different schema user than the application.

Verification steps:

1. Check which migration versions have been applied in each environment.
2. Inspect the live DDL, not just migration files in the repository.
3. Check the schema and user the application connects with.
4. Compare table names, column names, data types, and constraints.
5. Run migrations against the right database and schema.
6. Run integration tests with the target dialect and driver.

Do not alter entity mappings as a temporary workaround for an environment missing a migration without first identifying the authoritative schema source.

## 14. Naming Rules to Minimize Errors

An operationally friendly convention typically has these characteristics:

- Use lowercase snake_case for tables and columns.
- Avoid SQL keywords as table or column names.
- Avoid quoted mixed-case names unless required for compatibility.
- Use @Table and @Column when database names differ from Java names.
- Specify the schema explicitly if the application should not depend on search path.
- Apply the same naming convention across migrations, custom queries, and entity mappings.
- Do not change the global naming strategy just to fix a single table.

Example:

~~~sql
CREATE TABLE sales.purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

~~~java
@Table(value = "purchase_orders", schema = "sales")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @Column("created_at")
    private LocalDateTime createdAt;
}
~~~

camelCase Java names, lowercase snake_case relational names, and explicit schemas keep mappings readable and less dependent on session settings.

## 15. Testing Mappings Against the Target Database

H2 is useful for fast tests, but it does not prove all identifier rules for PostgreSQL, MySQL, Oracle, or SQL Server.

Differences that can affect behavior:

- Case folding rules.
- Identifier quote characters.
- Reserved keywords.
- Schema/catalog/search path behavior.
- Table name case sensitivity.
- How drivers return metadata.
- DDL syntax and generated SQL.

If production uses PostgreSQL, critical integration tests covering table and column names should run against PostgreSQL with a compatible driver, such as via Testcontainers. Do the same for other target databases.

Tests should cover:

1. Inserting an aggregate.
2. Reading an aggregate.
3. Updating an aggregate.
4. Saving and loading child collections.
5. Executing custom @Query methods.
6. Verifying the specified schema and application user permissions.

## 16. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| Spring looks for purchase_order but DB has purchase_orders | Default derived name differs from actual table name | Use @Table with the exact table name |
| Query reports order_number not found | Property mapping derives a different name or DB column is order_no | Use @Column and align migrations |
| Table exists, yet relation does not exist | Wrong search path or default schema | Qualify the schema or configure session settings properly |
| Works on Windows, fails on Linux | Table name case-sensitivity rules differ | Use lowercase conventions and test on target OS/database |
| Table named Order causes syntax error | Identifier conflicts with SQL keyword | Rename or quote according to dialect |
| Quoted table still cannot be found | Quoted identifiers are case-sensitive | Use exact spelling and quote conventions when creating and querying |
| Child collection fails to load | Wrong child table or idColumn/keyColumn | Verify @MappedCollection and foreign key |
| Repository works, but @Query fails | Literal SQL uses old table/column names | Update custom SQL to match schema |
| DBA sees table, application does not | Application user lacks permissions or uses a different schema | Verify with exact credentials and metadata |
| One environment fails after deploy | Unapplied migration or schema drift | Check migration history and live DDL |
| Custom NamingStrategy renames many entities | Global rule applies broadly | Narrow the change and test all mappings |
| Adding quotes inside @Table still produces invalid SQL | Annotation is not interpreted as a quoted identifier as expected | Inspect SqlIdentifier and actual dialect behavior |

## 17. Diagnostic Workflow for Table/Column Name Errors

When encountering a mapping error, proceed in order:

1. **Identify the database:** check JDBC URL, catalog, and database user.
2. **Identify the schema:** check the current schema and search path.
3. **Verify database objects:** query metadata to confirm tables and columns exist.
4. **Verify mapping:** inspect @Table, @Column, @MappedCollection, and NamingStrategy.
5. **Check identifiers:** determine whether names are quoted, reserved words, or mixed-case.
6. **Inspect actual SQL:** confirm which identifiers Spring Data JDBC emits.
7. **Check migrations:** compare the live schema against applied migrations.
8. **Check permissions:** confirm the application user has access to the right schema.
9. **Run integration tests:** use the same database/driver and connection settings.
10. **Fix the root cause:** update mappings, migrations, or schema/search path using consistent conventions.

## 18. Practice Exercises

### Exercise 1 — Default vs. Explicit Names

1. Create PurchaseOrder with property orderNumber.
2. Observe the derived table and column names.
3. Create a schema using purchase_orders and order_no.
4. Map them using @Table and @Column.
5. Verify insert and read operations.

### Exercise 2 — Schema Search Path

1. Create two schemas containing a table with the same name.
2. Run a query without qualifying the schema.
3. Change search_path or default schema.
4. Observe which table gets selected.
5. Specify the schema explicitly in the mapping and compare.

### Exercise 3 — Quoted Identifiers

1. Create a table with a quoted mixed-case name.
2. Try querying it without quotes.
3. Try querying it with exact quotes and casing.
4. Inspect metadata via JDBC.
5. Note why lowercase unquoted naming is easier to operate.

### Exercise 4 — NamingStrategy

1. Configure a custom NamingStrategy for one entity.
2. Check the generated table name.
3. Confirm other entities still use the default rule.
4. Verify collection mappings as well.
5. Run an integration test against the target database.

### Exercise 5 — Diagnosing a Migration Error

1. Rename a column in an entity.
2. Skip applying the migration in the test database.
3. Observe the column not found error.
4. Apply the migration.
5. Re-run the test and verify the mapping.

## 19. Conclusion

Table and column name errors in Spring Data JDBC usually stem from mismatches between mapping metadata, the live schema, and database identifier rules. Identify the names derived by the naming strategy, use @Table and @Column for differing names, and also verify collection linking columns via @MappedCollection.

Quoting and case sensitivity depend on the database. Unquoted identifiers may be case-folded or collide with keywords; quoted identifiers generally preserve spelling and must be referenced accurately. The schema search path determines where the database looks for unqualified tables, so a table can exist while the application connection still fails to find it.

When diagnosing issues, verify using the exact application user, schema, and JDBC driver; compare generated SQL with database metadata and applied migrations. Adopting lowercase snake_case conventions, avoiding reserved words, and specifying schemas explicitly when needed will significantly reduce mapping errors across environments.
