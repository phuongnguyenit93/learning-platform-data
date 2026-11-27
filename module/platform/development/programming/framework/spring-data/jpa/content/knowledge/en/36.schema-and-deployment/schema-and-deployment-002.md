# Meaning of ddl-auto Modes Across Environments

**Module:** Spring Data JPA  
**Topic Group:** Schema and Deployment

## 1. Objectives

After this lesson, you will be able to:

- Explain the role of spring.jpa.hibernate.ddl-auto in a Spring Boot application using Hibernate.
- Distinguish between none, validate, update, create, and create-drop.
- Choose the appropriate configuration for local development, test, staging, and production.
- Understand the risk of data loss when Hibernate automatically creates or modifies schemas.
- Distinguish Hibernate schema generation from migrations using Flyway or Liquibase.
- Design a controlled, repeatable, and safe schema deployment process for application upgrades.
- Verify JPA mappings, actual schemas, and migrations before releasing.

## 2. What Is ddl-auto?

In a Spring Boot application using Spring Data JPA with Hibernate, the property:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

controls Hibernate's behavior toward the database schema when initializing the SessionFactory or EntityManagerFactory. The name ddl-auto is Spring Boot's way of passing Hibernate's schema action configuration.

A schema is the storage structure in the database, consisting of tables, columns, data types, primary keys, foreign keys, unique constraints, indexes, and related objects. JPA mappings describe how Java entities and properties correspond to that structure.

For example:

~~~java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;
}
~~~

The mapping tells Hibernate it needs a customer table with primary key id and a non-null name column with a maximum length of 120 according to JPA metadata. However, this mapping does not guarantee that the running database already has that exact table and constraint. That depends on schema actions, migrations, and the actual database structure.

ddl-auto determines whether Hibernate validates, creates, or attempts to update the schema at application startup. It is not a schema change history tool and does not replace a versioned migration workflow.

## 3. Five Common Modes

| Value | Main Behavior | Common Purpose |
|---|---|---|
| none | Performs no schema actions | Application uses an externally managed schema |
| validate | Checks whether mappings are compatible with the current schema; does not create/alter tables | Startup verification, commonly used in staging/production |
| update | Hibernate attempts to adjust the schema to match mappings | Convenient for local experimentation, not a safe migration tool |
| create | Creates the schema from mappings; may drop existing structures before recreating | Dedicated databases that can be wiped and recreated |
| create-drop | Creates the schema on startup and drops it when the SessionFactory closes | Tests or temporary environments |

Exact behavior may depend on the Hibernate version and dialect. Check the specific library version in use when relying on a particular behavior.

## 4. none: Hibernate Does Not Manage the Schema

~~~properties
spring.jpa.hibernate.ddl-auto=none
~~~

With none, Hibernate neither creates/alters tables automatically nor validates that the schema matches mappings. The application expects the database to be prepared by another process.

Suitable when:

- Flyway or Liquibase manages the entire schema.
- A DBA or deployment pipeline is responsible for applying DDL.
- The application lacks privileges to alter database structures.
- The release process separates DDL privileges from the runtime application account.

The advantage is that startup behavior never silently alters database structures. The disadvantage is that if migrations have not been applied, the application may still start and only fail later when querying or writing data.

If using none, include a schema verification step in the pipeline or integration tests. Do not treat a successful application startup as proof that the schema is correct.

## 5. validate: Check Compatibility Only

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

validate instructs Hibernate to check whether the current schema is compatible with the mappings Hibernate knows about. If unacceptable differences are detected, initialization can fail so the application does not run against an invalid schema.

Suitable when:

- The database has already been created via migrations.
- You want the application to detect missing required tables or columns early.
- You want staging and production not to modify the schema on startup.
- The pipeline needs to ensure migrations were applied before the new application version runs.

For example, an entity has a property mapped to column customer.name, but the customer table does not yet have that column. validate can fail application startup, catching the missing migration.

**Limitations of validate:** this is not a comprehensive database test suite. Do not assume it verifies every business rule, existing data, index definitions, query performance, every constraint type, or all DBMS-specific DDL details. Verify schemas and migrations with appropriate tools outside Hibernate.

validate also does not fix the schema. If a column is missing, you must create a migration or fix the schema through a managed process, then restart the application.

## 6. update: Convenient, but Not a Migration Tool

~~~properties
spring.jpa.hibernate.ddl-auto=update
~~~

update tells Hibernate to attempt to alter the current schema to match mappings. For example, adding a new property may create the corresponding column. Exact behavior depends on Hibernate, the dialect, and the type of change.

update can be useful during local experimentation with a disposable database. However, do not rely on it as a migration tool for shared environments or production because:

- It does not produce versioned migration history showing which changes were applied.
- It cannot express the intent of transforming data from an old structure to a new one.
- It does not guarantee safe handling of all renames, column splits/merges, data type changes, or constraint modifications.
- It does not know how to backfill existing data according to business rules.
- It can cause drift between databases if environments started with different schemas.
- It is difficult to review, test, roll back, and coordinate with multi-version application deployments.

For example, renaming a Java property from fullName to displayName does not necessarily tell Hibernate to rename the column. Depending on the mapping and version, schema update may create a new column or leave the old one behind. Existing data may not be moved to the new column as intended.

An explicit migration can rename the column, backfill data, and verify the result. That is why update does not replace Flyway or Liquibase.

## 7. create: Recreate the Schema

~~~properties
spring.jpa.hibernate.ddl-auto=create
~~~

create instructs Hibernate to create the schema from mappings. In Hibernate's schema generation strategy, creation may include dropping existing schema objects before recreating them. Therefore, existing data can be lost.

Only use this when the database is an isolated environment that can be completely recreated, such as a temporary local database. Do not enable create on a database containing data that must be kept.

create does not mean migrating from an old schema version to a new one. It rebuilds the structure from current mappings without preserving business data through a transition plan.

## 8. create-drop: Create on Startup, Drop on Close

~~~properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

create-drop creates the schema during initialization and drops it when the SessionFactory closes cleanly. This is a common choice for tests with a dedicated database whose data does not need to survive after testing.

Test configuration example:

~~~properties
# application-test.properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

When using create-drop:

- The database must be dedicated to tests.
- Never accidentally connect to a shared or production database.
- Do not depend on data persisted from a previous run.
- Tests should set up their own fixtures and assert results.
- Understand the test context lifecycle; context reuse may cause schema creation/dropping timing to differ from individual test methods.

create-drop is particularly useful with Testcontainers databases created for a test suite or test group. When the container and context shut down, test data is discarded along with the temporary environment.

## 9. Choosing Configuration by Environment

There is no single value suited to every environment. Choose based on purpose and how schemas are managed.

| Environment | Common Choice | Reason |
|---|---|---|
| Local with disposable database | create or create-drop | Fast schema rebuilds while experimenting |
| Local preserving data | validate or migrations; update only for controlled experiments | Avoids accidental data loss and verifies schema |
| Unit/integration tests with dedicated DB | create-drop or migrations from scratch | Each test run has a deterministic state |
| CI | Migrations + validate or none | Tests migrations and mappings on a clean database |
| Staging | validate or none after pipeline runs migrations | Mirrors production, catches drift before release |
| Production | validate or none after migrations | Application does not create/alter schema during startup |

### 9.1. Local development

If the local database only contains disposable test data, create-drop provides a clean schema whenever a new persistence context is created. If you want to preserve data across restarts, use migrations and validate.

update can occasionally be convenient while learning or prototyping new mappings, but it should not become the project's sole workflow. Run migrations locally so schema changes are captured in reviewable history.

### 9.2. Test

For integration tests, you can choose create-drop if Hibernate mappings are the test schema source. If the project uses Flyway/Liquibase in practice, include tests that run real migrations on a compatible database to catch SQL errors or ordering issues.

Do not test solely against H2 if production runs PostgreSQL or MySQL and the project relies on database-specific behavior. Testcontainers lets you run the same database type in CI or locally.

### 9.3. Staging

Staging should mirror the production workflow: migrations are applied first, then the application verifies the schema. validate catches mapping-schema mismatches during startup. If the pipeline includes an independent schema check and the application does not need to self-validate, none can also be appropriate.

### 9.4. Production

In production, avoid create, create-drop, and update. These modes can cause unplanned structural changes, data loss, or schema divergence across instances.

Typically, use Flyway/Liquibase to apply migrations, then choose validate if you want Hibernate to check compatibility on startup. Use none if the deployment process already validates the schema in a separate step and you do not want Hibernate performing that check.

The database account used by the application in production should generally have only the privileges required at runtime. Separating the migration account with DDL privileges from the application account reduces the risk of an application startup accidentally altering the schema.

## 10. Default Values in Spring Boot

Do not rely on leaving ddl-auto blank and assuming it is always none or always update. Spring Boot may choose a default based on the database type and whether a schema manager is present.

In common configurations, if an embedded database is used without a schema manager, Boot may choose create-drop. With non-embedded databases or when a schema management tool is present, the default is usually none.

Behavior also depends on Spring Boot version, Hibernate, datasource, and SQL initialization settings. To avoid surprises across local, CI, and production, declare the value explicitly in the corresponding profile:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Verify the actual effective configuration at startup, especially when multiple application.properties files, profiles, environment variables, or deployment overrides exist.

## 11. How Does Hibernate ddl-auto Differ from Flyway and Liquibase?

Hibernate schema generation primarily relies on current entity mappings to create, validate, or attempt to update a schema.

Flyway and Liquibase manage schema changes using versioned migrations or changelogs. Each change is explicitly described, stored in the repository, and applied in order.

| Criterion | Hibernate ddl-auto | Flyway/Liquibase |
|---|---|---|
| Source of truth | Entity mappings | SQL migrations or changelogs |
| Change history | Not a versioned migration system | History/versions/checksums |
| Data backfills | Cannot adequately express business workflows | Can write explicit SQL or changesets |
| Renaming/splitting/merging columns | Should not rely on update to infer | Migrations describe changes explicitly |
| Review and deployment | Behavior depends on mappings/provider | Changes are reviewed beforehand |
| Rollback | No reliable business rollback plan | Can design compensating migrations or rollbacks depending on tool |

A common workflow is:

1. Developer updates entities and writes the corresponding migration.
2. Tests run migrations on a clean database and from a previous version's database.
3. Staging pipeline applies the migration.
4. Application starts with ddl-auto=validate or none.
5. Production applies migrations in the tested deployment order.
6. New application runs on the compatible schema.

Do not let both Hibernate update and Flyway/Liquibase modify the schema in production. Two mechanisms can produce unpredictable results and compromise the clarity of migration history.

## 12. Versioned Migration Example

Suppose you need to create the customer table:

~~~sql
-- V1__create_customer.sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
~~~

Later, you need to add a status:

~~~sql
-- V2__add_customer_status.sql
ALTER TABLE customer
ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
~~~

This example uses PostgreSQL syntax. For MySQL or other databases, identity types and some syntax may differ.

Migrations are stored in Flyway's default directory, typically db/migration on the classpath. Filenames follow the versioned migration convention, such as V1__create_customer.sql. Flyway records executed migrations in its schema history table.

For larger changes, consider the expand-contract strategy:

1. Add new columns or tables in a way compatible with the old application version.
2. Deploy application code able to read/write the transitional structure.
3. Backfill legacy data in controlled batches.
4. Verify that data has been fully migrated.
5. Switch the application to the new structure.
6. Only drop the old column in a later release, once no instances still depend on it.

This approach is useful during rolling deployments where multiple instances run two application versions concurrently for a period of time.

## 13. Coordinating Schema Migrations and JPA Mappings

When editing entities, check the following:

- Do @Table and @Column match table/column names in the migration?
- Are Java types and SQL types compatible?
- Are nullable, length, precision, and scale reflected in the schema?
- Do @Id, @GeneratedValue, and the identity/sequence strategy match the database?
- Does @JoinColumn point to the correct foreign key?
- Is the enum stored as STRING or ORDINAL, and does the migration use the right column type?
- Do converters, embedded objects, and inheritance produce matching structures?
- Have required indexes and constraints been created in the migration?

Enum example:

~~~java
@Enumerated(EnumType.STRING)
@Column(nullable = false, length = 20)
private OrderStatus status;
~~~

With EnumType.STRING, the database stores the enum name. Renaming an enum constant can affect existing data. With EnumType.ORDINAL, the database stores numeric positions; inserting or reordering constants can change the meaning of old data. Consider data migrations when modifying enums.

Annotations like @Column(nullable = false) describe mappings and may affect generated DDL. They do not automatically modify the database when ddl-auto=none or validate. Create a migration to add the NOT NULL constraint and handle legacy null data before applying it.

## 14. Pre-Deployment Verification Process

A checklist that can be applied to every release:

1. Identify the current schema version and running application version.
2. Review new migrations, SQL, and data impact.
3. Run migrations on a clean database.
4. Run upgrade migrations from the previous version's schema.
5. Verify backfilled data and constraints.
6. Run integration tests against the right database type or Testcontainers.
7. Start the application with ddl-auto=validate to detect incompatible mappings.
8. Verify pipeline ordering: database migrations complete before new instances receive traffic.
9. Define a recovery plan if the migration or deployment fails.
10. Monitor startup logs and SQL errors after release.

For large tables, adding columns, creating indexes, or altering constraints can lock tables or take substantial time. Consider online/concurrent index creation if supported by the database, lock duration, data volume, and backfill strategy. Do not assume every ALTER TABLE statement is fast and non-disruptive.

## 15. Common Mistakes

### 15.1. Using update in production for convenience

update does not provide migration history and does not clearly express how data is migrated. Use versioned migrations for reviewable, controlled deployments.

### 15.2. Using create or create-drop with a database containing data to keep

These modes can wipe schemas and data. Only use them with temporary databases dedicated to a developer or tests.

### 15.3. Thinking validate will fix the schema

validate only checks certain compatibility aspects. When discrepancies exist, apply a migration or fix the schema externally.

### 15.4. Assuming validate checks every constraint and all data

Hibernate validation does not replace verifying constraints, indexes, data, and execution plans with database tools. Test those requirements separately.

### 15.5. Letting every instance alter the schema at startup

Multiple instances starting simultaneously with schema actions can cause DDL contention or inconsistent states. Let a controlled migration step manage schema changes before the application runs.

### 15.6. Forgetting which profile is active

Local might use create-drop while production accidentally inherits the same setting due to an incorrect profile or environment variable. Check the effective configuration in each environment and keep sensitive information out of committed config files.

### 15.7. Changing mappings and forgetting the migration

The application may work locally because update automatically adds the column, yet fail in staging/production using validate or none. Every schema change needs a corresponding migration and upgrade test.

## 16. Checklist for Choosing ddl-auto

- [ ] Is the database a temporary environment where data can be wiped?
- [ ] Is the schema managed by Hibernate or a migration tool?
- [ ] Do local, test, staging, and production have separate configurations?
- [ ] Do tests run on a production-compatible database type?
- [ ] Does production avoid create, create-drop, and update?
- [ ] Are migrations versioned, reviewed, and run in order?
- [ ] Are migrations tested from both an old schema and a clean database?
- [ ] Is validate used to verify mappings where appropriate?
- [ ] Does the runtime account have minimal database privileges?
- [ ] Does the pipeline apply migrations before deploying new instances?
- [ ] Is there a plan for backfills, rollback/compensation, and handling interrupted deployments?

## 17. Conclusion

ddl-auto determines how Hibernate handles the schema at application startup. none does not intervene, validate checks compatibility, update attempts to adjust the schema, create recreates the schema, and create-drop also drops the schema when the SessionFactory closes. Local and test setups can use schema creation modes on temporary databases; staging and production should let versioned migrations manage changes, then use validate or none depending on the pipeline. Understanding the risks of each mode, testing migrations, and separating DDL privileges from the runtime account enable safe and repeatable Spring Data JPA deployments.