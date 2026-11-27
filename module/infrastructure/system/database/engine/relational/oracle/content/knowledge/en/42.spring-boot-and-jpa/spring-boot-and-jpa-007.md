# Entity Mapping, Schemas, Object Names, and Quoted Identifiers in Spring Boot and JPA

When a Spring Boot application uses Spring Data JPA to access Oracle Database, Java class names do not necessarily match table names, field names do not necessarily match column names, and schema names do not automatically equal the login username. Hibernate must translate entity metadata into the table, column, sequence, join table, and SQL object names that Oracle actually recognizes.

This distinction becomes critical when connecting to an existing schema, especially legacy databases with:
- Uppercase table/column names following Oracle conventions.
- Lowercase or mixed-case object names created using double quotes.
- Names colliding with SQL keywords such as ORDER, USER, or LEVEL.
- A schema owner different from the database user the application logs in with.
- Legacy naming conventions that differ from Hibernate's default naming strategy.
- Sequences, synonyms, views, triggers, and foreign keys managed by separate scripts.

A single mapping error can cause ORA-00942, ORA-00904, ORA-02289, or SQL that executes against the wrong schema. The durable fix is understanding Oracle's object naming rules, declaring JPA mappings explicitly where needed, controlling Hibernate's naming strategy, and verifying the SQL Hibernate generates.

This lesson focuses on Spring Boot, Jakarta Persistence/JPA, and Oracle Database 19c. Some examples also apply to Spring Boot 2 applications using javax.persistence; Spring Boot 3 and later typically use jakarta.persistence. The annotations share the same meaning, while package imports and Hibernate versions differ.

## 1. Naming Layers in JPA and Oracle

### 1.1. Entity Name Is Not Table Name

An entity can be declared as:

~~~java
@Entity(name = "Customer")
@Table(name = "CUSTOMER", schema = "APP")
public class CustomerEntity {
    // fields
}
~~~

There are two different names here:
- The entity name `Customer` is used in JPQL/HQL.
- The table name `APP.CUSTOMER` is used in SQL sent to Oracle.

JPQL example using the entity name:

~~~java
SELECT c
FROM Customer c
WHERE c.id = :id
~~~

Hibernate translates JPQL into SQL referencing table APP.CUSTOMER. Do not use `@Entity(name = ...)` to rename the physical table.

If `name` is omitted from `@Entity`, the default entity name is typically the simple class name. That name remains independent of `@Table`.

### 1.2. Field/Property Name Is Not Column Name

Example:

~~~java
@Entity
@Table(name = "CUSTOMER", schema = "APP")
public class CustomerEntity {

    @Id
    @Column(name = "CUSTOMER_ID")
    private Long id;

    @Column(name = "DISPLAY_NAME")
    private String displayName;
}
~~~

The Java field `displayName` maps to column `DISPLAY_NAME`. Without `@Column(name=...)`, Hibernate derives a logical name from the field and passes it through the naming strategy.

For existing schemas, explicit column names avoid relying on automatic camelCase-to-snake_case conversion rules.

### 1.3. Schema Owner, Database User, and Current Schema

In Oracle:
- **Database user** is the account authenticated when opening a session.
- **Schema** is the collection of objects owned by a database user.
- **Current schema** is the schema Oracle uses to resolve unqualified object names in a session.
- One user can access objects in another schema if granted appropriate privileges.

For example, the application logs in as APP_RUNTIME while tables belong to APP_DATA. The mapping can point to APP_DATA.CUSTOMER:

~~~java
@Table(name = "CUSTOMER", schema = "APP_DATA")
~~~

APP_RUNTIME still needs appropriate SELECT/INSERT/UPDATE/DELETE privileges on that object. Specifying `schema` in an annotation does not grant access privileges.

### 1.4. Object Names Actually Stored by Oracle

Oracle normalizes unquoted identifiers to uppercase:

~~~sql
CREATE TABLE customer (
    customer_id NUMBER PRIMARY KEY
);
~~~

In the data dictionary, the names are typically stored as CUSTOMER and CUSTOMER_ID.

Names created with double quotes preserve exact casing:

~~~sql
CREATE TABLE "Customer" (
    "CustomerId" NUMBER PRIMARY KEY
);
~~~

This object's exact names are `Customer` and `CustomerId`. Queries must reference it using matching double quotes:

~~~sql
SELECT "CustomerId"
FROM "Customer";
~~~

An unquoted query referencing `CUSTOMER` looks for object `CUSTOMER`, and will not automatically match `"Customer"`.

## 2. Oracle Identifier Rules

### 2.1. Unquoted Identifiers

Unquoted identifiers:
- Are case-insensitive during name resolution.
- Are normalized to uppercase by Oracle.
- Cannot contain arbitrary special characters.
- Cannot be reserved words in disallowed contexts.
- Have length limits governed by database compatibility.

Thus, `CUSTOMER`, `Customer`, and `customer` without quotes all resolve to the same identifier `CUSTOMER`.

This is why most Oracle schemas store uppercase object names in the data dictionary even when DDL scripts are written in lowercase.

### 2.2. Quoted Identifiers

Quoted identifiers wrap the name in double quotes:

~~~sql
CREATE TABLE "SalesOrder" (
    "OrderId" NUMBER,
    "CreatedAt" TIMESTAMP
);
~~~

Oracle preserves exact casing and requires exact quoted references:

~~~sql
SELECT "OrderId", "CreatedAt"
FROM "SalesOrder";
~~~

The following forms do not match mixed-case quoted names:

~~~sql
SELECT ORDERID FROM SALESORDER;
SELECT "ORDERID" FROM "SALESORDER";
~~~

Both reference a different identifier from `"SalesOrder"."OrderId"`.

Quoted identifiers may be necessary for legacy databases or special names, but they reduce SQL readability and increase mapping risk. For new schemas, prefer unquoted identifiers, uppercase per Oracle convention, and avoid reserved words.

### 2.3. Reserved Words and Conflicting Names

Avoid naming objects or columns after SQL keywords such as ORDER, GROUP, USER, LEVEL, DATE, or similar keywords. Certain words may be keywords or reserved words depending on version and context.

If a legacy schema already has a name like `"Order"`, JPA must quote that identifier accurately. Do not change the annotation to `ORDER` and expect Oracle to resolve it automatically.

Better yet, if schema changes are possible, use unambiguous names like `SALES_ORDER` or `ORDER_HEADER`. For unchangeable schemas, mappings must match the existing names verbatim.

### 2.4. Identifier Length Limits

Oracle 19c supports identifiers up to 128 bytes when database `COMPATIBLE` is set to 12.2 or higher. With lower compatibility settings, the older 30-byte limit may still apply.

Check:

~~~sql
SHOW PARAMETER compatible;
~~~

The limit is measured in bytes, which is not necessarily the character count in multi-byte database character sets. Long names may be rejected or cause compatibility issues when migrating to databases with lower `COMPATIBLE` levels.

Names auto-generated by Hibernate for constraints, indexes, or sequences must also fit within the target database's limit.

### 2.5. Dictionary Names

For standard objects:

~~~sql
SELECT owner,
       table_name
FROM   all_tables
WHERE  owner IN ('APP', 'APP_DATA')
ORDER  BY owner, table_name;
~~~

For columns:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       nullable
FROM   all_tab_columns
WHERE  owner = 'APP_DATA'
AND    table_name = 'CUSTOMER'
ORDER  BY column_id;
~~~

Unquoted names appear in uppercase. Mixed-case quoted names appear in exact preserved case. Use data dictionary values to confirm exact identifiers rather than guessing from Java classes.

## 3. Mapping Entities with @Table and @Column

### 3.1. Explicit Schema and Table Mapping

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Column;

@Entity
@Table(name = "CUSTOMER", schema = "APP_DATA")
public class CustomerEntity {

    @Id
    @Column(name = "CUSTOMER_ID")
    private Long id;

    @Column(name = "DISPLAY_NAME", nullable = false, length = 120)
    private String displayName;
}
~~~

@Table:
- name: table or view name mapped by the entity.
- schema: schema owner.
- catalog: catalog if supported by database/provider; for Oracle, `schema` is normally the attribute to use.

@Column:
- name: column name.
- nullable: nullability metadata.
- length: declared length for string types.
- precision/scale: numeric metadata.
- insertable/updatable: controls whether the column participates in INSERT/UPDATE.
- unique: uniqueness metadata, typically useful during schema generation.

Metadata attributes do not alter schemas when `ddl-auto=validate` or `none`. They influence mapping and may be used when the provider generates DDL.

### 3.2. Entities Mapping Views

An entity can map a view if there is a stable unique key JPA can use to identify rows:

~~~java
@Entity
@Table(name = "CUSTOMER_SUMMARY_V", schema = "APP_REPORT")
public class CustomerSummary {
    @Id
    @Column(name = "CUSTOMER_ID")
    private Long customerId;

    @Column(name = "ORDER_COUNT")
    private Long orderCount;
}
~~~

JPA requires `@Id` to establish entity identity, even when the underlying object is a view. Never pick a non-unique column as `@Id`, or the persistence context may erroneously merge multiple rows into one entity.

If a view lacks a unique key, consider DTOs/projections and native queries instead of mapping it as a managed entity.

### 3.3. Mapping Fields with Different Names

~~~java
@Column(name = "CUST_NM")
private String customerName;
~~~

Java field names do not need to match column names. Keep Java naming clear and expressive while database names reflect the existing schema.

### 3.4. Insertable and Updatable

A column populated by a trigger or database expression can be mapped read-only:

~~~java
@Column(name = "CREATED_AT", insertable = false, updatable = false)
private LocalDateTime createdAt;
~~~

This prevents Hibernate from including the column in INSERT/UPDATE statements. It does not guarantee a value is generated; an appropriate trigger, default expression, or database mechanism is required. How generated values are retrieved after INSERT depends on Hibernate/dialect and mapping.

Do not set `insertable=false` on a NOT NULL column unless the database provides a default/trigger, or INSERTs will fail constraint checks.

### 3.5. A Field Mapping a Column Already Managed Elsewhere

In some mappings, the same column appears in multiple relationships. Only one mapping should write the column; the other can use `insertable=false, updatable=false`.

Example exposing a foreign key both as an association and as a scalar field:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "CUSTOMER_ID")
private CustomerEntity customer;

@Column(name = "CUSTOMER_ID", insertable = false, updatable = false)
private Long customerId;
~~~

Understand association ownership to avoid having two properties write the same column, which causes mapping exceptions or unpredictable updates.

## 4. Hibernate Naming Strategies in Spring Boot

### 4.1. Why Naming Strategies Matter

Hibernate does not simply pass raw Java field names into SQL. Mapping typically flows through:
1. Entity/property name.
2. Implicit naming strategy when no explicit name is declared.
3. Logical identifier.
4. Physical naming strategy.
5. SQL dialect and quoting rules.
6. Final SQL sent to Oracle.

For instance, field `customerAddress` can become `CUSTOMER_ADDRESS` or `customer_address` depending on naming strategy and quoting.

### 4.2. Implicit Naming Strategy

The implicit naming strategy determines logical names when annotations omit explicit object names.

Example:

~~~java
@Entity
public class CustomerProfile {
    @Id
    private Long id;

    private String displayName;
}
~~~

Without `@Table` and `@Column`, Hibernate derives table/column names from entity and property names. The outcome depends on the implicit strategy, physical strategy, and Hibernate version.

### 4.3. Physical Naming Strategy

The physical naming strategy translates logical names into final physical names. A strategy may:
- Convert camelCase to snake_case.
- Force lowercase or uppercase.
- Apply prefix/suffix rules.
- Leave names unchanged.

Important: explicit names in `@Table`/`@Column` also pass through the physical naming strategy. Writing `@Column(name="CUSTOMER_ID")` alone is not enough if a custom strategy alters it afterward.

### 4.4. Spring Boot Default Naming Changes Across Versions

Spring Boot has changed default naming strategy implementations and class names across Hibernate generations. Never copy class names from a Spring Boot 2 project into Boot 3/4 without checking actual dependencies.

When mapping legacy schemas:
- Check the Spring Boot version.
- Check the Hibernate ORM version.
- Inspect `spring.jpa.hibernate.naming.*` settings.
- Inspect the generated SQL.
- To preserve logical names verbatim, configure `PhysicalNamingStrategyStandardImpl` compatible with your Hibernate version.

Property example:

~~~properties
spring.jpa.hibernate.naming.physical-strategy=org.hibernate.boot.model.naming.PhysicalNamingStrategyStandardImpl
~~~

`PhysicalNamingStrategyStandardImpl` keeps physical names identical to the logical identifiers passed by Hibernate. It does not undo earlier implicit naming choices; for exact names, declare `@Table`/`@Column` explicitly.

### 4.5. Configuring Implicit Strategy When Needed

Example using the JPA-compliant implicit strategy:

~~~properties
spring.jpa.hibernate.naming.implicit-strategy=org.hibernate.boot.model.naming.ImplicitNamingStrategyJpaCompliantImpl
~~~

This is an optional setting, not a requirement for every application. Before changing it, verify the class exists in your Hibernate version and compare generated SQL names before and after.

### 4.6. Naming Strategies Do Not Rename Objects in Oracle

A naming strategy only changes how Hibernate emits identifiers. It does not:
- Rename real tables.
- Rename real columns.
- Create synonyms.
- Grant privileges.
- Change schema owners.
- Modify existing sequences.

If a strategy turns `CUSTOMER_ID` into unquoted `customer_id`, Oracle still resolves it to `CUSTOMER_ID`. However, if quoted as `"customer_id"`, that becomes a different identifier. This is a common reason applications break after enabling global quoting.

## 5. Schema Mapping in Spring Boot

### 5.1. Declaring Schema on Each Entity

~~~java
@Entity
@Table(name = "CUSTOMER", schema = "APP_DATA")
public class CustomerEntity {
    // ...
}
~~~

Advantages:
- Explicit schema owner per entity.
- Can map multiple schemas in one persistence unit with proper privileges.
- Less dependent on session current schema.
- Easy to read in entity definitions.

Disadvantages:
- Repeats the schema name across many entities.
- Changing schema names requires updating many mappings across environments.

### 5.2. Using Hibernate Default Schema

You can configure a default schema:

~~~properties
spring.jpa.properties.hibernate.default_schema=APP_DATA
~~~

Hibernate qualifies objects lacking an explicit schema with this default schema.

This is a Hibernate configuration, not a command changing the Oracle session's `CURRENT_SCHEMA`. Nor does it grant privileges to the database user.

If an entity declares `@Table(schema="OTHER_SCHEMA")`, the explicit mapping overrides the default schema per metadata/provider rules.

### 5.3. When Not to Set a Default Schema

Avoid setting a single global default schema when:
- Entities span multiple schemas.
- The application relies on synonyms resolved via current schema.
- Native SQL relies on session-level name resolution.
- Each tenant has its own schema selected per connection/session.
- Certain objects belong to different schema owners.

In multi-schema scenarios, declare schemas explicitly or design proper multi-tenancy.

### 5.4. Complete Illustrative Configuration

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//dbhost.example.com:1521/appsvc.example.com
spring.datasource.username=APP_RUNTIME
spring.datasource.password=ENV_DB_PASSWORD

spring.jpa.database-platform=org.hibernate.dialect.OracleDialect
spring.jpa.properties.hibernate.default_schema=APP_DATA
spring.jpa.hibernate.ddl-auto=validate

spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
~~~

Exact dialect/class names depend on the Hibernate version; modern Hibernate usually auto-detects the dialect from JDBC metadata unless an override is required. Avoid configuring old dialect classes incompatible with Hibernate 6.

Do not enable bind-parameter logging carelessly in production because bound values may contain PII or secrets. For debugging, use a test environment and time-bound logging.

### 5.5. Datasource Username and Default Schema Are Different Things

Example:
- Datasource username: APP_RUNTIME.
- Hibernate default schema: APP_DATA.
- Physical table: APP_DATA.CUSTOMER.

APP_RUNTIME must have appropriate privileges on APP_DATA.CUSTOMER. Setting default schema does not make Oracle treat APP_RUNTIME as the owner of APP_DATA.

## 6. CURRENT_SCHEMA and Synonyms in Oracle

### 6.1. ALTER SESSION SET CURRENT_SCHEMA

Oracle allows changing the default schema used to resolve unqualified names:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = APP_DATA;
~~~

After this statement, an unqualified query:

~~~sql
SELECT * FROM CUSTOMER;
~~~

can resolve to APP_DATA.CUSTOMER per Oracle name-resolution rules.

`CURRENT_SCHEMA` does not change `SESSION_USER` and does not grant extra privileges. The session remains authenticated as the original user, and required object privileges must still exist.

### 6.2. Checking Session Context

~~~sql
SELECT
    sys_context('USERENV', 'SESSION_USER') AS session_user,
    sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Use this query to confirm the application connected to the right service/PDB and whether `CURRENT_SCHEMA` matches expectations.

### 6.3. CURRENT_SCHEMA with Connection Pools

Connection pools reuse physical connections. If a request runs `ALTER SESSION SET CURRENT_SCHEMA`, that session state can persist when the connection returns to the pool, depending on pool/reset policy.

Risk:
- Tenant A's request returns the connection to the pool.
- Tenant B's request borrows the same connection.
- `CURRENT_SCHEMA` still points to tenant A.
- Unqualified SQL may access the wrong tenant's data.

If you must switch current schema per request:
- Set the schema before every borrow.
- Reset to the baseline state before returning the connection.
- Use the pool's connection initialization/reset hooks.
- Test across multiple requests and concurrency.
- Never assume the pool resets all session state automatically.

For multi-tenant systems, prefer Hibernate multi-tenancy mechanisms or managed routing over ad-hoc `ALTER SESSION` calls in business code.

### 6.4. Synonyms

A synonym is an alias pointing to another object:

~~~sql
CREATE SYNONYM CUSTOMER FOR APP_DATA.CUSTOMER;
~~~

Private synonyms belong to the creating schema; public synonyms have database-wide visibility per Oracle rules. A synonym is not a copy of data and does not grant privileges on the target object.

If Hibernate generates unqualified SQL, Oracle can resolve synonyms via name resolution. If Hibernate qualifies `APP_DATA.CUSTOMER`, the synonym `CUSTOMER` is bypassed in favor of the qualified reference.

### 6.5. Mapping via Synonyms

If an application is designed to access synonyms:

~~~java
@Entity
@Table(name = "CUSTOMER")
public class CustomerEntity {
    // ...
}
~~~

Avoid setting `hibernate.default_schema=APP_DATA` if that causes Hibernate to qualify tables and bypass the intended synonym. Verify generated SQL and privileges on the underlying target object.

Do not map a synonym as if it had independent metadata; JPA mappings still need the target object's real columns and keys.

## 7. Quoted Identifiers in JPA

### 7.1. Mapping Mixed-Case Tables

Suppose Oracle already has:

~~~sql
CREATE TABLE "SalesOrder" (
    "OrderId" NUMBER PRIMARY KEY,
    "OrderStatus" VARCHAR2(20)
);
~~~

JPA mapping:

~~~java
@Entity
@Table(name = "\"SalesOrder\"", schema = "APP_DATA")
public class SalesOrderEntity {

    @Id
    @Column(name = "\"OrderId\"")
    private Long orderId;

    @Column(name = "\"OrderStatus\"")
    private String orderStatus;
}
~~~

In Java strings, identifier double quotes are escaped with backslashes. Hibernate must receive exact quoted names to emit SQL referencing `"SalesOrder"."OrderId"`.

Writing only `@Table(name="SalesOrder")` may treat the name as unquoted, causing Oracle to search for `SALESORDER` instead of the quoted mixed-case `SalesOrder`.

### 7.2. Mapping Names Colliding with Reserved Words

Example table `"Order"` with column `"Date"`:

~~~java
@Entity
@Table(name = "\"Order\"", schema = "APP_DATA")
public class PurchaseOrderEntity {

    @Id
    @Column(name = "\"OrderId\"")
    private Long id;

    @Column(name = "\"Date\"")
    private LocalDate orderDate;
}
~~~

Avoid naming the Java entity `Order` if it causes confusion in JPQL or conflicts with query keywords. The entity name can be `PurchaseOrder` while the physical table is `"Order"`.

### 7.3. Quoting a Single Column

There is no need to quote the entire schema if only one object uses mixed case:

~~~java
@Column(name = "\"DisplayName\"")
private String displayName;
~~~

Other unquoted columns can retain standard uppercase mappings.

### 7.4. Global Quoted Identifiers

Hibernate supports quoting all identifiers globally:

~~~properties
spring.jpa.properties.hibernate.globally_quoted_identifiers=true
~~~

This makes Hibernate quote tables, columns, sequences, and many other identifiers per Hibernate rules. It can help with schemas using special names, but can also produce SQL incompatible with legacy schemas.

For example, if logical name `CUSTOMER_ADDRESS` gets quoted as `"customerAddress"` or `"customer_address"` depending on naming strategy, Oracle treats it as case-sensitive and distinct from unquoted `CUSTOMER_ADDRESS`.

Never enable global quoting to fix a single reserved-word error. Usually it is better to quote only the specific identifier or use a non-reserved physical name.

### 7.5. Skip Column Definitions

Hibernate provides properties related to global quoting and DDL column definitions. Configure them only when you understand their impact on `columnDefinition` and native SQL fragments. Never copy all quoting properties from another project without inspecting the generated DDL.

### 7.6. Backticks vs. Double Quotes

Hibernate supports backtick syntax in some annotations/versions as a cross-database request to quote identifiers, but that is a Hibernate-specific convention. For portable JPA mappings on Oracle, use escaped double quotes in annotation strings and verify the generated SQL.

## 8. Mapping Relationships and Supporting Objects

### 8.1. Many-to-One with JoinColumn

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(
    name = "CUSTOMER_ID",
    referencedColumnName = "CUSTOMER_ID",
    nullable = false
)
private CustomerEntity customer;
~~~

`name` is the foreign key column in the current table. `referencedColumnName` is the target table's column; if omitted, JPA typically defaults to the target entity's primary key column.

If the current table resides in a different schema, its schema is set by `@Table` on the owning entity. The target entity carries its own schema.

### 8.2. One-to-Many

~~~java
@OneToMany(mappedBy = "customer")
private List<SalesOrderEntity> orders = new ArrayList<>();
~~~

`mappedBy` must point to the association property on the child entity. It is not the column name `CUSTOMER_ID`. The foreign key column is configured via `@JoinColumn` on the ManyToOne side.

### 8.3. Many-to-Many with JoinTable

~~~java
@ManyToMany
@JoinTable(
    name = "USER_ROLE",
    schema = "APP_DATA",
    joinColumns = @JoinColumn(name = "USER_ID"),
    inverseJoinColumns = @JoinColumn(name = "ROLE_ID")
)
private Set<RoleEntity> roles = new HashSet<>();
~~~

`JoinTable` has its own schema. Do not assume it shares the other entity's schema; declare it explicitly if the object already exists.

### 8.4. ElementCollection and CollectionTable

~~~java
@ElementCollection
@CollectionTable(
    name = "CUSTOMER_TAG",
    schema = "APP_DATA",
    joinColumns = @JoinColumn(name = "CUSTOMER_ID")
)
@Column(name = "TAG_VALUE")
private Set<String> tags = new HashSet<>();
~~~

`CollectionTable` maps the table storing a collection of value types. Table name, schema, and join column must all match the database.

### 8.5. Embedded Objects and AttributeOverride

~~~java
@Embeddable
public class Address {
    private String city;
    private String postalCode;
}

@Entity
@Table(name = "CUSTOMER", schema = "APP_DATA")
public class CustomerEntity {
    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "city",
            column = @Column(name = "CITY_NAME")
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "POST_CODE")
        )
    })
    private Address address;
}
~~~

`name` in `AttributeOverride` refers to the embeddable's property; `name` in `@Column` refers to the physical column name. These two naming layers are distinct.

### 8.6. SecondaryTable

An entity can span multiple tables:

~~~java
@Entity
@Table(name = "EMPLOYEE", schema = "HR")
@SecondaryTable(
    name = "EMPLOYEE_DETAIL",
    schema = "HR",
    pkJoinColumns = @PrimaryKeyJoinColumn(name = "EMPLOYEE_ID")
)
public class EmployeeEntity {
    @Id
    @Column(name = "EMPLOYEE_ID")
    private Long id;

    @Column(name = "BIO", table = "EMPLOYEE_DETAIL")
    private String biography;
}
~~~

The `table` attribute in `@Column` points to the secondary table name in entity metadata. Verify join keys and actual schemas for both tables.

## 9. Mapping Oracle Sequences and Generated Identifiers

### 9.1. Sequence Generator

Oracle commonly uses sequences for primary keys:

~~~sql
CREATE SEQUENCE APP_DATA.CUSTOMER_SEQ
    START WITH 1
    INCREMENT BY 1
    NOCACHE;
~~~

JPA:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "customer_seq_generator"
)
@SequenceGenerator(
    name = "customer_seq_generator",
    sequenceName = "CUSTOMER_SEQ",
    schema = "APP_DATA",
    allocationSize = 1
)
@Column(name = "CUSTOMER_ID")
private Long id;
~~~

`name` in `@SequenceGenerator` is the generator name in persistence metadata. `sequenceName` is the physical sequence name. `schema` identifies the sequence owner.

### 9.2. Allocation Size and INCREMENT BY

`allocationSize` controls how Hibernate allocates IDs from a sequence. When Hibernate uses a pooled optimizer, `allocationSize` must align with the sequence's `INCREMENT BY` according to Hibernate's optimizer strategy.

For sequences incrementing by 1, `allocationSize=1` is simple and predictable. If setting a larger `allocationSize` to reduce round trips, create the sequence and configure the matching optimizer properly; otherwise sequence increment mismatches or unexpected IDs can occur.

Never change `allocationSize` in an entity without checking the existing database sequence.

### 9.3. Sequence in Another Schema

If the sequence belongs to `APP_ID` while the table belongs to `APP_DATA`:

~~~java
@SequenceGenerator(
    name = "customer_seq_generator",
    sequenceName = "CUSTOMER_SEQ",
    schema = "APP_ID",
    allocationSize = 1
)
~~~

The runtime user needs SELECT privilege on the sequence as well as access to the table. The sequence's schema does not have to match the table's schema.

### 9.4. Oracle Identity Columns

Oracle supports identity columns on modern releases:

~~~sql
CREATE TABLE APP_DATA.CUSTOMER (
    CUSTOMER_ID NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    DISPLAY_NAME VARCHAR2(120) NOT NULL
);
~~~

This can be mapped as:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
@Column(name = "CUSTOMER_ID")
private Long id;
~~~

Capabilities and generated SQL depend on Oracle version, dialect, and Hibernate version. If a schema already uses traditional sequences/triggers, do not switch to `IDENTITY` merely by editing annotations.

### 9.5. Checking Sequences in the Dictionary

~~~sql
SELECT sequence_owner,
       sequence_name,
       increment_by,
       cache_size,
       last_number
FROM   all_sequences
WHERE  sequence_owner = 'APP_DATA'
AND    sequence_name = 'CUSTOMER_SEQ';
~~~

For cached sequences, `LAST_NUMBER` is not necessarily the exact next value to be issued. Use the dictionary to inspect metadata, not `LAST_NUMBER` as an exact count of issued IDs.

## 10. Legacy Schemas and Special Cases

### 10.1. Schema Owner Different from Runtime User

Example:
- `APP_RUNTIME` logs in.
- `APP_DATA` owns `CUSTOMER` and `SALES_ORDER`.
- `APP_RUNTIME` is granted DML privileges on those tables.

Mapping:

~~~java
@Table(name = "CUSTOMER", schema = "APP_DATA")
~~~

The DBA can grant object-level privileges:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON APP_DATA.CUSTOMER
TO APP_RUNTIME;
~~~

Grant minimal privileges required by the workload. Never grant DBA, SELECT ANY TABLE, or broad privileges just to silence mapping errors.

### 10.2. Synonyms Are Not Privileges

If you create a synonym:

~~~sql
CREATE SYNONYM APP_RUNTIME.CUSTOMER
FOR APP_DATA.CUSTOMER;
~~~

`APP_RUNTIME` still needs privileges on `APP_DATA.CUSTOMER`. A synonym only provides an alternate name for object resolution.

### 10.3. Mapping Views and Read-Only Entities

Reporting views generally should not be updated via JPA. Use DTO projections/native queries or read-only entity mappings per application convention. Hibernate supports `@Immutable` as a Hibernate-specific annotation; it is not a standard JPA annotation.

If a view has no primary key, do not invent a fake `@Id` from a non-unique column.

### 10.4. Database Links

Objects accessed via a database link take the form `TABLE@DBLINK` in SQL. Standard JPA mappings do not natively model database links as schemas. You can use native queries or local views/synonyms, while carefully evaluating transactions, privileges, and distributed query limits.

### 10.5. Partitioned Tables

JPA typically maps the table owner/name without specifying partitions in `@Table`. The Oracle optimizer picks partitions via predicates and partition pruning. If querying a specific partition explicitly is required, use native SQL with appropriate syntax and manage the risk of coupling to physical storage layout.

## 11. Schema Generation and Migration

### 11.1. ddl-auto

Spring Boot can be configured with:

~~~properties
spring.jpa.hibernate.ddl-auto=none
~~~

Common values:
- none: Hibernate does not manage the schema.
- validate: verifies mappings against the existing schema.
- update: attempts to alter the schema to match mappings.
- create: creates a new schema from mappings.
- create-drop: creates on startup and drops on shutdown in certain environments.

For production schemas managed by DBAs/Flyway/Liquibase, typically use `validate` or `none`. Never rely on `update` for critical migrations: it does not replace reviewed migration scripts and cannot accurately express every schema change.

### 11.2. What Does Validate Catch?

`validate` checks certain mapping metadata such as table/column existence and types against the database. It does not prove:
- All constraints are correct.
- Indexes match design.
- Triggers/defaults/sequences work properly.
- Business queries return accurate results.
- All grants/synonyms are configured properly.
- Existing data is clean.

Combine `validate` with migration tools, integration tests, and dictionary checks.

### 11.3. Managing DDL with Flyway/Liquibase

Migration SQL example:

~~~sql
CREATE TABLE APP_DATA.CUSTOMER (
    CUSTOMER_ID NUMBER(19) NOT NULL,
    DISPLAY_NAME VARCHAR2(120) NOT NULL,
    CONSTRAINT PK_CUSTOMER PRIMARY KEY (CUSTOMER_ID)
);
~~~

JPA mappings must match actual names. Migrations provide versioned, reviewed schema changes with clear rollback/forward-fix paths.

### 11.4. Preventing Unintended Quoted Objects Generated by Hibernate

If global quoting or naming strategies differ between migrations and Hibernate, schema generation might create `"customer"` while migrations create `CUSTOMER`. Under Oracle rules, those are two separate objects.

Standardize one convention:
- Unquoted uppercase DDL.
- Uppercase in JPA annotations.
- Do not enable global quoting without reason.
- Quote only mandatory legacy objects individually.
- Integration test against the same Oracle version/`COMPATIBLE` level as production.

## 12. Diagnosing SQL Generated by Hibernate

### 12.1. Enabling SQL Logging in Test Environments

Example:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
spring.jpa.show-sql=false
~~~

Hibernate SQL logs reveal:
- Whether tables/schemas are qualified.
- Whether column names are accurate.
- Whether identifiers are quoted.
- Whether join columns match.
- Which sequence names are invoked.

Do not enable bind-value logging in production without evaluating sensitive data exposure. Even SQL text can reveal table/column names and business structure.

### 12.2. Inspecting Hibernate Metadata

You can inspect mapping metadata during `EntityManagerFactory` startup or via bootstrap logging appropriate to your Hibernate version. The goal is to confirm logical names, physical names, and quoting state before running queries.

Never modify the database to match suspected SQL names before verifying which naming strategy Hibernate applied.

### 12.3. Using the Oracle Dictionary

Tables:

~~~sql
SELECT owner, table_name
FROM   all_tables
WHERE  owner = 'APP_DATA'
AND    table_name LIKE '%CUSTOMER%';
~~~

Columns:

~~~sql
SELECT owner, table_name, column_name, data_type
FROM   all_tab_columns
WHERE  owner = 'APP_DATA'
AND    table_name = 'CUSTOMER'
ORDER  BY column_id;
~~~

Sequences:

~~~sql
SELECT sequence_owner, sequence_name
FROM   all_sequences
WHERE  sequence_owner = 'APP_DATA';
~~~

Constraints:

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status
FROM   all_constraints
WHERE  owner = 'APP_DATA'
AND    table_name = 'CUSTOMER';
~~~

### 12.4. Distinguishing Mapping Errors from Privilege Errors

ORA-00942 can happen when:
- The table/view does not exist.
- The name or schema is wrong.
- Quoted casing does not match.
- The user lacks privileges on the object.
- A synonym cannot resolve its target object.

Log in as the exact runtime database user and run the Hibernate-generated SQL. A DBA querying as SYS or the owner can see objects that the runtime user cannot access.

### 12.5. Native SQL and JPQL

JPQL uses entity names and property names:

~~~java
@Query("select c from CustomerEntity c where c.displayName = :name")
List<CustomerEntity> findByName(@Param("name") String name);
~~~

Native SQL uses physical object names:

~~~java
@Query(
    value = "select CUSTOMER_ID, DISPLAY_NAME " +
            "from APP_DATA.CUSTOMER where DISPLAY_NAME = :name",
    nativeQuery = true
)
List<Object[]> findNativeByName(@Param("name") String name);
~~~

Do not write `APP_DATA.CUSTOMER` in JPQL as though it were an entity name. Conversely, native queries must use exact Oracle schemas, tables, and columns.

## 13. Common Errors and Resolutions

| Error | Possible Cause | Investigation Path |
| --- | --- | --- |
| ORA-00942 | Wrong schema/table, quoted case, or missing privilege | Generated SQL, ALL_TABLES, grants, synonyms |
| ORA-00904 | Wrong column name or quoted case | ALL_TAB_COLUMNS, @Column, naming strategy |
| ORA-00903 | Invalid table name or bad mapping | @Table, schema, quoting, SQL logs |
| ORA-01747 | Invalid column specification, often bad name/alias/quote | Generated SQL, reserved words |
| ORA-02289 | Sequence missing or lacks privileges | @SequenceGenerator, ALL_SEQUENCES, GRANT |
| ORA-01031 | Insufficient privileges | Runtime user privileges on object/sequence |
| ORA-00972 | Identifier too long per COMPATIBLE | Object/constraint/sequence names |
| MappingException duplicate column | Two properties writing the same column | insertable/updatable and association ownership |
| Schema-validation error | Mapping and dictionary mismatch | Actual DDL, schema, naming strategy, types |

### 13.1. ORA-00942: table or view does not exist

Procedure:
1. Enable SQL logging to capture the exact SQL.
2. Check whether the table has a schema prefix.
3. Log in with the exact runtime user.
4. Check ALL_TABLES/ALL_VIEWS.
5. Check object owner and grants.
6. Check synonyms if used.
7. Check quoted identifiers.

Never grant SELECT ANY TABLE just to make the error disappear.

### 13.2. ORA-00904: invalid identifier

Common causes:
- Wrong `@Column`.
- Hibernate unexpectedly converting camelCase to snake_case.
- Database contains a quoted mixed-case column.
- Column belongs to a secondary table with wrong mapping.
- Native SQL uses a Java property name instead of column name.

Compare carefully against ALL_TAB_COLUMNS and SQL logs.

### 13.3. ORA-02289: sequence does not exist

Check sequence owner, `schema` in `@SequenceGenerator`, and SELECT privileges. If the sequence resides in another schema, declare the right schema or grant privileges/synonyms appropriately.

### 13.4. Schema Validation Failure

When Hibernate `validate` reports a missing table/column or type mismatch:
- Verify the datasource points to the right database/service/PDB.
- Verify default schema and entity schemas.
- Verify naming strategy.
- Check whether identifiers are quoted.
- Check column type/precision/scale.
- Verify migrations ran on the right environment.

Never switch `ddl-auto` to `update` just to bypass validation errors.

## 14. Practical Configuration Patterns

### 14.1. Standard Uppercase Oracle Schema

Oracle DDL:

~~~sql
CREATE TABLE APP_DATA.CUSTOMER (
    CUSTOMER_ID NUMBER(19) NOT NULL,
    DISPLAY_NAME VARCHAR2(120) NOT NULL,
    CONSTRAINT PK_CUSTOMER PRIMARY KEY (CUSTOMER_ID)
);
~~~

JPA:

~~~java
@Entity
@Table(name = "CUSTOMER", schema = "APP_DATA")
public class CustomerEntity {
    @Id
    @Column(name = "CUSTOMER_ID")
    private Long id;

    @Column(name = "DISPLAY_NAME", nullable = false, length = 120)
    private String displayName;
}
~~~

### 14.2. Legacy Schema with Quoted Mixed-Case

Oracle DDL:

~~~sql
CREATE TABLE APP_DATA."SalesOrder" (
    "OrderId" NUMBER PRIMARY KEY,
    "OrderStatus" VARCHAR2(20)
);
~~~

JPA:

~~~java
@Entity
@Table(name = "\"SalesOrder\"", schema = "APP_DATA")
public class SalesOrderEntity {
    @Id
    @Column(name = "\"OrderId\"")
    private Long id;

    @Column(name = "\"OrderStatus\"")
    private String status;
}
~~~

### 14.3. Runtime User Different from Owner

Datasource:

~~~properties
spring.datasource.username=APP_RUNTIME
spring.jpa.properties.hibernate.default_schema=APP_DATA
spring.jpa.hibernate.ddl-auto=validate
~~~

DBA grants:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON APP_DATA.CUSTOMER
TO APP_RUNTIME;
~~~

Sequence privilege if using a sequence in the owner schema:

~~~sql
GRANT SELECT ON APP_DATA.CUSTOMER_SEQ TO APP_RUNTIME;
~~~

### 14.4. Single Persistence Unit Spanning Multiple Schemas

Entity A:

~~~java
@Table(name = "CUSTOMER", schema = "APP_DATA")
~~~

Entity B:

~~~java
@Table(name = "COUNTRY", schema = "REF_DATA")
~~~

The runtime user needs appropriate privileges in both schemas. Avoid setting a single default schema if it causes missing qualifiers or qualifies objects under the wrong schema.

### 14.5. Cross-Schema Association Mapping

~~~java
@Entity
@Table(name = "SALES_ORDER", schema = "APP_DATA")
public class SalesOrderEntity {
    @Id
    @Column(name = "ORDER_ID")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "CUSTOMER_ID")
    private CustomerEntity customer;
}
~~~

~~~java
@Entity
@Table(name = "CUSTOMER", schema = "CRM_DATA")
public class CustomerEntity {
    @Id
    @Column(name = "CUSTOMER_ID")
    private Long id;
}
~~~

Hibernate must join to the target entity's schema. Verify generated SQL and cross-owner grants.

## 15. Workflow for Designing Mappings Against an Existing Oracle Schema

### Step 1 — Explore the Database

Collect:
- Service name/PDB.
- Runtime username.
- Schema owner.
- Actual tables/views/sequences.
- Column names and data types.
- Primary keys/foreign keys.
- Whether quoted identifiers exist.
- Grants and synonyms.

### Step 2 — Lock Down Naming Conventions

Decide:
- Java entity names following the domain.
- Entity names used in JPQL.
- Table/column names taken from the dictionary.
- Explicit schemas on entities or a default schema.
- Reserved words avoided or individually quoted.
- Global quoting disabled unless needed.

### Step 3 — Verify Versions

Record:
- Spring Boot version.
- Hibernate ORM version.
- Jakarta Persistence vs. javax.persistence.
- Oracle JDBC driver.
- Oracle Database version and `COMPATIBLE`.

Naming strategies, dialects, and identity/sequence support can vary across these versions.

### Step 4 — Write Explicit Mappings

Declare:
- `@Entity`.
- `@Table`.
- `@Id`.
- `@Column`.
- `@JoinColumn`/`@JoinTable`.
- `@SequenceGenerator` if needed.
- `@SecondaryTable`/`@CollectionTable` if used by physical objects.

### Step 5 — Control Naming Strategy

Inspect implicit/physical naming configuration. If a legacy schema uses exact names, consider `PhysicalNamingStrategyStandardImpl` and explicit annotations.

### Step 6 — Verify Privileges

Log in as the runtime user and test required SELECT/INSERT statements. Verify privileges on tables, sequences, views, and dependent objects.

### Step 7 — Validate and Integration Test

Use `ddl-auto=validate` or `none` per policy. Run tests against real Oracle or a compatible environment; H2 does not fully emulate quoted identifiers, Oracle sequences, data types, and SQL dialects.

### Step 8 — Inspect Actual SQL

Enable SQL logging in tests. Cross-check schemas/tables/columns/sequences against the dictionary. Confirm service and PDB after opening a connection.

### Step 9 — Put Migrations Under Version Control

Manage DDL with Flyway/Liquibase or an internal migration workflow. Review DDL and entity mappings together in pull requests.

### Step 10 — Enforce Production Controls

- Never auto-create/alter schemas from application instances.
- Use least-privilege runtime accounts.
- Never log sensitive bind values.
- Run smoke tests after deployment.
- Monitor ORA errors and schema validation failures.
- Keep naming conventions consistent across environments.

## 16. Lab Exercises

Use a test Oracle schema. Create objects via DDL in the assigned schema, then map them with Spring Boot/JPA. Never modify production schemas for experimentation.

### Exercise 1 — Entity Name and Table Name

Create `CustomerEntity` with `@Entity(name="Customer")` and `@Table(name="CUSTOMER")`. Write a JPQL query using `Customer` and verify the generated SQL references `CUSTOMER`.

### Exercise 2 — Explicit Column Mapping

Map Java `displayName` to `DISPLAY_NAME`. Inspect generated SQL and verify against the dictionary.

### Exercise 3 — Schema Owner Different from Runtime User

Log in as `APP_RUNTIME`, map `APP_DATA.CUSTOMER`, grant minimal object privileges, and verify queries.

### Exercise 4 — Default Schema

Remove `schema` from `@Table` and set `hibernate.default_schema=APP_DATA`. Inspect SQL. Then remove the property and observe the difference.

### Exercise 5 — Physical Naming Strategy

Compare the project's default strategy with `PhysicalNamingStrategyStandardImpl`. Record actual generated table/column names.

### Exercise 6 — Quoted Mixed-Case Table

Create `"SalesOrder"` and `"OrderId"`. Map them using escaped quoted strings in annotations. Verify SQL preserves exact casing and double quotes.

### Exercise 7 — Reserved Word

Create a test table with a quoted column `"Order"`. Map that column individually and compare against a non-reserved name.

### Exercise 8 — Global Quoted Identifiers

In a test environment, enable `globally_quoted_identifiers`. Inspect SQL and explain why a quoted lowercase identifier differs from an unquoted uppercase identifier. Restore configuration afterward.

### Exercise 9 — Synonym

Create a synonym for a table in another schema. Map an unqualified table name and observe the effect of adding `hibernate.default_schema`.

### Exercise 10 — Association and JoinColumn

Create `CUSTOMER` and `SALES_ORDER` with a foreign key. Map `@ManyToOne`, verifying the join column and both entities' schemas.

### Exercise 11 — Sequence Generator

Create `CUSTOMER_SEQ INCREMENT BY 1`. Use `@SequenceGenerator` with `allocationSize=1` and insert entities. Then inspect sequence metadata.

### Exercise 12 — CollectionTable

Map a `Set<String>` to table `CUSTOMER_TAG`. Verify schema, join column, and value column.

### Exercise 13 — Schema Validation

Run `ddl-auto=validate` with valid mappings, then intentionally alter one column name in a test to observe the error. Restore the mapping.

### Exercise 14 — Investigating ORA-00942/00904

Create a mapping with the wrong schema or wrong quoted casing. Use SQL logs and `ALL_TABLES`/`ALL_TAB_COLUMNS` to find the cause. Fix the annotation/naming strategy and re-run.

## 17. Common Misconceptions

**“@Entity(name) is the table name.”** No. It is the entity name used in JPQL; `@Table` specifies the physical table.

**“Java class names automatically equal table names.”** Not necessarily. Hibernate applies implicit/physical naming strategies, and `@Table` provides explicit mapping.

**“Database user and schema are always the same.”** No. A runtime user can access objects owned by another schema.

**“hibernate.default_schema grants privileges to the user.”** No. It only affects how Hibernate qualifies object names.

**“ALTER SESSION SET CURRENT_SCHEMA changes the logged-in user.”** No. `SESSION_USER` stays the same; `CURRENT_SCHEMA` only affects name resolution.

**“Oracle is completely case-insensitive.”** Unquoted identifiers are normalized to uppercase; quoted identifiers preserve exact casing and must be referenced accordingly.

**“Simply quoting a table name in Oracle makes JPA understand it automatically.”** No. Annotations must request quoting properly, and the naming strategy must not alter the identifier.

**“Enabling globally_quoted_identifiers is always safe.”** No. It can emit quoted identifiers that do not match existing unquoted objects.

**“Synonyms grant access privileges to objects.”** No. The user still needs privileges on the target object.

**“@Column(length=120) automatically alters production columns.”** No. It is mapping metadata; `ddl-auto`/migration policies govern whether the schema changes.

**“ddl-auto=update replaces Flyway/Liquibase.”** No. It cannot replace versioned, reviewed, rollback-capable production migrations.

**“Passing H2 tests proves Oracle mappings work.”** No. H2 does not fully emulate Oracle quoted identifiers, sequences, data types, synonyms, and SQL dialects.

## 18. References

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): rules for entities, tables, columns, identifiers, and relationship mappings.
- [Hibernate ORM User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): implicit/physical naming strategies, identifier quoting, schemas, and sequence mappings.
- [Spring Boot Reference — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html): datasource, JPA, and Hibernate configuration in Spring Boot.
- [Oracle Database 19c SQL Language Reference — Database Object Names and Qualifiers](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Database-Object-Names-and-Qualifiers.html): identifier rules, quoted names, and object name limits.
- [Oracle Database 19c SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): table names, columns, constraints, and DDL.
- [Oracle Database 19c SQL Language Reference — CREATE SEQUENCE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html): sequences and sequence properties.
- [Oracle Database 19c Database Reference — ALL_TAB_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TAB_COLUMNS.html): column metadata.
- [Oracle Database 19c Database Reference — ALL_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TABLES.html): table metadata.
- [Oracle Database 19c SQL Language Reference — CREATE SYNONYM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SYNONYM.html): synonyms and name resolution.

JPA mapping with Oracle requires distinguishing entity/property names from physical table/column names, schema owners from runtime users, and unquoted identifiers from quoted identifiers. Use `@Table`/`@Column`/`@JoinColumn`/`@SequenceGenerator` to describe existing objects; control implicit/physical naming strategies; use default schema or `CURRENT_SCHEMA` only when their scope is well understood; and verify generated SQL using the exact runtime account. **Keep physical names consistent with the Oracle dictionary, quote mandatory legacy identifiers accurately, and let migration tools manage versioned DDL.**
