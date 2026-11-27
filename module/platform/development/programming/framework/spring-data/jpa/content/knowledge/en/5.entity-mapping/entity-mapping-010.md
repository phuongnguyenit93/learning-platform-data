# Physical Naming, Logical Naming, and SQL Keyword Conflict Rules

## 1. Why naming conventions matter

Java entities typically use `PascalCase` for classes and `camelCase` for attributes, whereas database schemas typically use `snake_case`. Beyond casing differences, table and column names must also avoid SQL keywords such as `ORDER`, `GROUP`, or `USER`. If mapping names, Hibernate-generated names, and actual database names diverge, applications can hit missing table/column errors or SQL syntax errors at query runtime.

The goal of naming conventions is to clarify the three naming layers, keep mappings stable across environments, and avoid relying on how a particular database engine handles keywords or case sensitivity.

## 2. Distinguishing Entity name, logical name, and physical name

| Concept | Meaning | Example |
| --- | --- | --- |
| Entity name | Name used by JPQL; defaults to class name and can be set via `@Entity(name = "...")` | `PurchaseOrder` |
| Logical name | Name Hibernate derives from explicit mappings or implicit naming rules | `purchaseOrder`, `orderNumber` |
| Physical name | Final identifier name Hibernate sends to the database after applying the physical naming strategy | `purchase_order`, `order_number` |

The entity name belongs to the object model and JPQL queries. Table/column names belong to the physical schema. `@Entity(name = "PurchaseOrder")` does not automatically set the table name; `@Table(name = "purchase_order")` declares the table name in the mapping. Similarly, JPQL uses the Java property `orderNumber`, while SQL may use the column `order_number`.

## 3. How Hibernate generates names

Naming follows two main steps:

1. **Implicit naming strategy** produces a logical name when the mapping does not declare an explicit name. For instance, entity `PurchaseOrder` and attribute `orderNumber` can derive logical names from class/field names or relationship context.
2. **Physical naming strategy** takes the logical name and transforms it into the physical name used in SQL. This is where camelCase-to-snake_case, lowercasing, or project-specific conventions are applied.

In Spring Boot 3, the default configuration typically uses `SpringImplicitNamingStrategy` and `CamelCaseToUnderscoresNamingStrategy`. Consequently, `purchaseOrder` usually converts to `purchase_order`, and `createdAt` to `created_at`. Your application's exact configuration may be overridden; check `spring.jpa.hibernate.naming` before assuming physical names.

You can explicitly configure the physical strategy in `application.yml` when a project needs uniform behavior:

```yaml
spring:
  jpa:
    hibernate:
      naming:
        physical-strategy: org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
```

Do not change naming strategies across environments. A change here can cause Hibernate to look for different table/column names than the ones created by migrations.

## 4. Declaring explicit names in Entities

Example mapping with readable Java names and snake_case physical names:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity(name = "PurchaseOrder")
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @Column(name = "order_status", nullable = false, length = 30)
    private String status;
}
```

This is an illustrative mapping snippet; real entities must include constructors, accessors, and other mappings as required by the application. `@Table` declares the table, `@Column` declares the column, and `@Id` identifies the primary key. `@JoinColumn` can also specify the physical name for a foreign key column.

When using Spring Boot's naming strategy, explicitly declared names also pass through the physical naming strategy. Therefore, write names directly in the desired physical convention, e.g., `order_number`, rather than mixing `orderNumber` and expecting every strategy to transform it identically.

## 5. Rules for avoiding SQL keywords

SQL keywords are defined per dialect and database version. A name valid in one database system can be a reserved keyword or special identifier in another. Common examples to avoid include `order`, `group`, `user`, `key`, `value`, `rank`, `limit`, `select`, and `table`; this list is neither exhaustive nor uniform across all databases.

Prefer renaming to a clear domain noun:

| Conflict-prone name | Recommended name |
| --- | --- |
| `order` | `purchase_order` |
| `user` | `user_account` or `app_user` |
| `group` | `customer_group` or `group_name` |
| `key` | `config_key` or `key_code` |
| `value` | `config_value` or `attribute_value` |
| `rank` | `sort_rank` or `priority_rank` |
| `limit` | `page_limit` or `credit_limit` |

Do not rely merely on the current database accepting a name. When switching dialects, upgrading database versions, or running migrations in another environment, that name can become an issue. The safe rule is to use descriptive domain names, keep singular/plural consistent, prefer snake_case, and avoid common keywords.

## 6. When mapping a legacy schema with keyword-colliding names

For legacy schemas that cannot be renamed immediately, you can quote identifiers in Hibernate mappings. Hibernate supports backticks in mapping names and converts them into the dialect-appropriate quote character:

```java
@Entity
@Table(name = "`order`")
public class LegacyOrder {

    @Id
    private Long id;

    @Column(name = "`group`")
    private String groupName;
}
```

This is Hibernate quoting syntax, not a Java convention or portable SQL syntax usable directly in every database. Hibernate emits dialect-specific quoting, such as double quotes or square brackets depending on the database engine. If portability across JPA providers is needed, renaming tables/columns in the schema is generally the more durable choice.

You can enable `hibernate.globally_quoted_identifiers` to quote all identifiers:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        globally_quoted_identifiers: true
```

Only enable this global setting after evaluating your schema and migrations. Quoting can alter how databases handle case sensitivity; for example, PostgreSQL treats unquoted and quoted identifiers differently. Migration scripts, indexes, constraints, and native SQL queries must match quoted names verbatim. Avoid turning it on globally just to work around one keyword-colliding column.

## 7. JPQL, SQL, and column names are three different contexts

JPQL references entity names and Java properties:

```java
select p from PurchaseOrder p where p.orderNumber = :number
```

SQL executed against the database references physical tables and columns:

```sql
SELECT id, order_number, order_status
FROM purchase_order
WHERE order_number = ?;
```

Therefore, do not write JPQL using physical table/column names unless intentionally using native SQL. Conversely, when writing native SQL, use the exact physical names in the schema and the database's quoting rules. If JPQL reports an unknown property, check Java field/property names; if SQL reports an unknown column/table, check physical names and migrations.

## 8. Synchronizing mappings with schemas and migrations

`@Table` and `@Column` only describe mappings for the ORM; they do not rename existing tables/columns when running with migrations. With Flyway or Liquibase, DDL must create the exact physical names Hibernate uses. Example schema matching the entity above:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    order_status VARCHAR(30) NOT NULL
);
```

When changing naming strategies or renaming mappings, create migrations to rename tables/columns and update dependent foreign keys, indexes, views, native queries, or reports. Do not use `ddl-auto=update` as a production migration tool; manage schema changes with controlled migrations and use an appropriate validation mode, such as `validate`, when the project architecture calls for it.

## 9. Common errors and how to investigate

**Syntax error near a keyword such as `order` or `group`.** Inspect the actual SQL Hibernate generates, identify the conflicting identifier, and prefer renaming the physical identifier. If a legacy schema forces keeping the name, quote the exact identifier in the mapping and verify dialect-generated SQL.

**Table or column not found after adding `@Table`/`@Column`.** Compare the name in the mapping, the name after the physical naming strategy, and the DDL migration. Check whether explicit names were transformed from camelCase to snake_case.

**Works on dev machine but fails in another environment.** Check whether dialect, database version, case-sensitivity rules, default schema, and naming strategy match. Avoid names dependent on database-specific keywords.

**JPQL reports entity or property not found.** Use the entity name in `FROM` and Java property names in JPQL expressions. `@Entity(name = "...")` controls the entity name; `@Table` does not control JPQL names.

**Native SQL fails after renaming mappings.** Native SQL must be updated to match the physical schema. Naming strategies do not automatically rewrite native SQL strings written by the application.

**Still getting identifier not found even after quoting.** Check exact casing and how the database stores quoted identifiers; also verify that the quoting syntax is Hibernate mapping syntax rather than hard-coded dialect quotes.

## 10. Checklist when designing new names

- Set explicit entity names when stable names in JPQL are needed.
- Use explicit `@Table` and `@Column` for important tables/columns or schemas with fixed conventions.
- Use snake_case for physical names and camelCase for Java properties.
- Avoid SQL keywords and common function/data-type names; prefer meaningful domain names.
- Verify the Spring Boot/Hibernate implicit and physical naming strategies.
- Ensure DDL migrations, foreign keys, indexes, views, and native SQL use the exact same physical names.
- Quote identifiers only when maintaining compatibility with legacy schemas; weigh case-sensitivity and portability impacts.
- Inspect generated SQL on the target dialect and run schema checks in an integration environment.

Good naming conventions make entity mappings readable, generated SQL predictable, and schemas less coupled to quirks of specific database engines. Whenever you have permission to evolve the schema, safe and meaningful physical names are usually the simplest, most stable solution.
