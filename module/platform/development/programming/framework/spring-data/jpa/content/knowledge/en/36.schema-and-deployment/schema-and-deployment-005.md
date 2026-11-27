# Order of schema.sql, data.sql, and Spring Boot Data Initialization

Spring Boot can initialize a database using SQL scripts, Hibernate/JPA, or migration tools such as Flyway and Liquibase. These mechanisms execute at different times. Without understanding their ordering, an application may encounter errors such as data.sql running before tables exist, Hibernate recreating the schema after scripts have loaded data, or multiple mechanisms attempting to create the same table.

With Spring Boot 3.x, three activities must be distinguished:

- **Schema initialization:** creating or altering table structures, keys, indexes, and constraints.
- **Data initialization:** inserting initial or sample data.
- **Versioned migration:** managing schema and data changes across deployment releases.

This lesson explains the default execution order of schema.sql, data.sql, and Hibernate, how to use spring.jpa.defer-datasource-initialization, environment-specific configuration, the difference between basic scripts and migrations, and how to test startup.

**Example prerequisites:** Java 17 or later, Spring Boot 3.x, Spring Data JPA, Hibernate, and JDBC. The application requires spring-boot-starter-data-jpa, the appropriate driver, and a DataSource. SQL syntax depends on the database; PostgreSQL examples are noted where applicable. Configurations are part of a Spring Boot application, not standalone Java programs run solely via javac.

## 1. Database Initialization Mechanisms in Spring Boot

A Spring Boot application may use one or more of the following mechanisms:

| Mechanism | Role | Usage Scope |
|---|---|---|
| schema.sql | Creates tables, indexes, constraints, or initial structures | Simple initialization, demos, tests, or small systems |
| data.sql | Inserts initialization data | Sample data, initial reference data |
| Hibernate ddl-auto | Creates, updates, validates, or drops schema from entity mappings | Development, mapping validation, or controlled environments |
| Flyway | Runs versioned migrations in order | Release-based schema management |
| Liquibase | Runs changelogs/changesets with history | Release-based schema management |

Do not let multiple tools jointly own changes to the same schema without explicit conventions. For example, if Flyway already creates the customers table, schema.sql and Hibernate must not also try to create that table.

In production, teams typically choose Flyway or Liquibase as the primary schema manager, and configure Hibernate validate to detect mapping mismatches.

## 2. What Are schema.sql and data.sql?

Spring Boot supports basic SQL scripts with two default filenames:

- **schema.sql:** runs statements that create or prepare database structures.
- **data.sql:** runs statements that insert data.

Example resource layout:

~~~text
src/
  main/
    resources/
      schema.sql
      data.sql
  main/
    java/
      com/example/
        Application.java
~~~

schema.sql:

~~~sql
CREATE TABLE departments (
    id BIGINT PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    CONSTRAINT fk_employees_department
        FOREIGN KEY (department_id)
        REFERENCES departments(id)
);
~~~

data.sql:

~~~sql
INSERT INTO departments (id, code, name)
VALUES (1, 'ENG', 'Engineering');

INSERT INTO departments (id, code, name)
VALUES (2, 'HR', 'Human Resources');

INSERT INTO employees (id, department_id, full_name)
VALUES (100, 1, 'An Nguyen');
~~~

With this layout, the schema script creates tables first, and then the data script inserts rows into existing tables. SQL statements must fit the target database and schema.

Basic scripts run at application startup according to SQL initialization settings. They are not a versioned migration system: Spring Boot does not track that an INSERT statement in data.sql should run only once across all startups.

## 3. Default Order: SQL Scripts Run Before Hibernate

By default, basic SQL initialization executes before JPA EntityManagerFactory initialization completes. In the normal flow:

~~~text
Spring Boot creates DataSource
          |
          v
SQL script initialization
          |
          +--> schema.sql
          |
          +--> data.sql
          |
          v
Initialize JPA EntityManagerFactory
          |
          v
Hibernate applies ddl-auto
          |
          v
Application finishes startup
~~~

Therefore, ordering among mechanisms is critical.

Suppose schema.sql created the products table and data.sql inserted data. If Hibernate subsequently runs with ddl-auto=create or create-drop, Hibernate may drop and recreate the schema from entity mappings. The data just inserted by data.sql can be lost.

This is a common reason why an application starts cleanly yet seeded data is missing after startup.

Ordering schema.sql before data.sql ensures data.sql has tables to insert into. However, this order does not mean data.sql always runs after Hibernate. By default, all basic SQL initialization occurs before JPA is fully initialized.

## 4. How Does spring.jpa.defer-datasource-initialization Change the Order?

If you want Hibernate to create the schema first and then have data.sql insert rows, enable:

~~~yaml
spring:
  jpa:
    defer-datasource-initialization: true
~~~

When this property is enabled, Spring Boot defers SQL script initialization until after the EntityManagerFactory beans have been created and initialized. With Hibernate creating the schema, the flow becomes:

~~~text
Spring Boot creates DataSource
          |
          v
Initialize JPA EntityManagerFactory
          |
          v
Hibernate applies ddl-auto
          |
          v
SQL script initialization
          |
          +--> schema.sql if configured/found
          |
          +--> data.sql
          |
          v
Application finishes startup
~~~

Key points to remember:

- This property defers SQL initialization as a whole, not just data.sql.
- If Hibernate already created a table and schema.sql also contains CREATE TABLE for the same table, the script can fail because the table already exists.
- The typical use case is Hibernate creating the schema in dev/test while data.sql only inserts rows after tables exist.
- Do not enable this property blindly if schema.sql is the primary table-creation source.

The default value of spring.jpa.defer-datasource-initialization is false.

## 5. Case A: schema.sql Creates Tables, data.sql Inserts Data

If you want SQL scripts to own schema creation, configure Hibernate to validate mappings instead of recreating tables:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:db/init/schema.sql
      data-locations: classpath:db/init/data.sql
      continue-on-error: false
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Flow:

1. DataSource is created.
2. schema.sql creates tables and constraints.
3. data.sql inserts initial data.
4. Hibernate initializes and validates entity mappings against the existing schema.
5. Application is ready.

Here, defer-datasource-initialization does not need to be enabled because SQL scripts must run before Hibernate. Hibernate validate neither creates nor drops tables.

This setup can be helpful for test environments or simple systems. For production applications with multiple schema versions, Flyway/Liquibase is usually more appropriate because they manage changes by version.

## 6. Case B: Hibernate Creates Schema, data.sql Inserts Data

In development or test environments, you can let Hibernate create the schema and then run data.sql:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create
    defer-datasource-initialization: true
  sql:
    init:
      mode: always
      data-locations: classpath:db/seed/data.sql
      continue-on-error: false
~~~

Flow:

1. Hibernate creates tables from entity mappings.
2. SQL initialization is deferred.
3. data.sql inserts data into the newly created tables.
4. Application finishes startup.

Do not include a schema.sql that recreates the same tables in this configuration. If an additional schema script is needed after Hibernate, it should only contain extra objects not managed by Hibernate and must be checked for compatibility.

**Note:** ddl-auto=create drops/recreates the schema according to provider behavior. Never use this configuration with a database containing data to preserve.

## 7. Hibernate ddl-auto and the Meaning of Each Value

The spring.jpa.hibernate.ddl-auto property controls how Hibernate handles the schema at startup:

| Value | General Behavior | Common Purpose |
|---|---|---|
| none | Does not create, update, or validate schema | Schema is managed by another tool |
| validate | Checks if mappings are compatible with current schema | Detects mapping/schema drift |
| update | Attempts to adjust schema to match mappings | Controlled experimentation/development |
| create | Creates schema from mappings on startup | Dev/test with disposable data |
| create-drop | Creates schema on startup, drops it when SessionFactory closes | Tests or demos |

Important points:

- update is not a complete migration tool. It does not replace controlling renames, data transformations, indexes, and constraints per release.
- create and create-drop can cause data loss.
- validate only checks certain mapping/schema aspects; it does not replace migration tests or checking every index/constraint.
- none does not mean the database needs no schema. It simply means Hibernate does not manage the schema during startup.

Spring Boot may pick different defaults depending on the environment. Typically, with an embedded database and no schema manager like Flyway/Liquibase, Boot defaults to create-drop; with other databases or when a schema manager is present, the default is usually none. Declare the value explicitly for important environments rather than relying on defaults.

## 8. Configuring SQL Initialization: mode, locations, and platform

The main properties live under spring.sql.init:

~~~yaml
spring:
  sql:
    init:
      mode: always
      platform: postgresql
      schema-locations: classpath:db/init/schema.sql
      data-locations: classpath:db/init/data.sql
      encoding: UTF-8
      continue-on-error: false
~~~

Meaning:

| Property | Effect |
|---|---|
| mode | Chooses whether scripts execute |
| platform | Selects database-specific script suffix |
| schema-locations | Locations of schema scripts |
| data-locations | Locations of data scripts |
| encoding | SQL file encoding |
| continue-on-error | Whether to continue if a script fails |

Values of mode:

- **embedded:** runs only for embedded databases; this is the common default.
- **always:** runs for both embedded and external databases such as PostgreSQL/MySQL.
- **never:** disables basic SQL initialization.

When using an external PostgreSQL or MySQL database, having schema.sql/data.sql on the classpath does not guarantee they will run. Check mode. With mode embedded, external databases are generally not initialized by these scripts.

## 9. Platform-Specific Scripts

When SQL needs to differ across databases, you can use platform-specific scripts:

~~~text
src/main/resources/
  schema.sql
  data.sql
  schema-postgresql.sql
  data-postgresql.sql
  schema-mysql.sql
  data-mysql.sql
~~~

Select the platform:

~~~yaml
spring:
  sql:
    init:
      platform: postgresql
      mode: always
~~~

Spring Boot supports platform-suffixed script names to pick matching content. For instance, PostgreSQL may use ON CONFLICT syntax, whereas MySQL may use its own syntax such as INSERT IGNORE or ON DUPLICATE KEY UPDATE.

Do not place a PostgreSQL-only SQL statement into a shared script if the application also runs on MySQL. You can use a shared script for portable SQL and platform scripts for specific differences. Verify which resources are actually loaded when customizing schema-locations/data-locations; configured paths must point to the right files.

## 10. Customizing Script Locations and Optional Resources

By default, Spring Boot looks for scripts using standard names on the classpath. You can organize a custom folder:

~~~text
src/main/resources/
  db/
    init/
      schema.sql
      data.sql
~~~

Configuration:

~~~yaml
spring:
  sql:
    init:
      schema-locations: classpath:db/init/schema.sql
      data-locations: classpath:db/init/data.sql
~~~

If a resource might not exist in certain profiles, use the appropriate optional prefix with the resource location, for example:

~~~yaml
spring:
  sql:
    init:
      data-locations: optional:classpath:db/init/data.sql
~~~

Do not use optional to hide missing required scripts. If schema initialization is a prerequisite for the application to function, a missing file should fail startup so the issue is caught early.

When setting custom schema-locations or data-locations, explicitly manage the list of files to run. Do not assume any file inside an arbitrary folder will be auto-discovered.

## 11. data.sql Re-Runs on Every Startup

A critical point: data.sql is an initialization script, not a run-once migration. If the application starts multiple times against the same database, INSERT statements can execute again.

For example:

~~~sql
INSERT INTO roles (id, code, name)
VALUES (1, 'ADMIN', 'Administrator');
~~~

If the id or code column has a UNIQUE constraint, the next startup can fail with a duplicate key error.

Ways to handle this:

1. Use data.sql only for databases created fresh every run, such as tests or demos.
2. Design database-appropriate idempotent seed inserts so re-runs do not create duplicates.
3. Use versioned migrations so initial data is applied once per migration history.
4. Use reference data managed separately by the deployment process.

PostgreSQL-specific example:

~~~sql
INSERT INTO roles (id, code, name)
VALUES (1, 'ADMIN', 'Administrator')
ON CONFLICT (code) DO NOTHING;
~~~

This is not portable SQL across all databases. MySQL, SQL Server, and Oracle have different syntax or mechanisms. If supporting multiple engines, use platform scripts or corresponding migrations.

Do not write an idempotent INSERT that silently ignores all errors if doing so could mask invalid seed data. Define natural keys, expected values, and how reference data is updated when it changes.

## 12. schema.sql Does Not Replace Flyway/Liquibase

schema.sql typically describes an initial schema state. It does not manage change history across releases.

Suppose version 1 has a customers table, a later version needs a status column, and the following version changes email structure. Simply editing schema.sql to the new state leaves a database created from the earlier version unaware of which ALTER statements to execute.

Flyway/Liquibase solves this using versioned migrations/changelogs:

~~~text
src/main/resources/
  db/
    migration/
      V1__create_customers.sql
      V2__add_customer_status.sql
      V3__add_customer_email_index.sql
~~~

Flyway records executed migrations in a history table. When a new version deploys, only unapplied migrations execute in order.

Liquibase manages changesets in a changelog and stores execution history accordingly.

For production:

- Use Flyway or Liquibase as the primary schema source.
- Never simultaneously let schema.sql and Hibernate ddl-auto=create/update modify tables managed by migrations.
- You can use Hibernate ddl-auto=validate to verify entity mappings after migrations.
- Manage schema changes via new migrations; do not edit versioned scripts that already ran in shared environments.

## 13. Ordering of Flyway/Liquibase and Hibernate

When Flyway or Liquibase is present, Spring Boot integrates these tools into initialization. The usual goal is for migrations to run before Hibernate initializes the EntityManagerFactory, so Hibernate sees the updated schema.

Typical flow:

~~~text
DataSource
    |
    v
Flyway or Liquibase migration
    |
    v
Database schema at new version
    |
    v
Hibernate EntityManagerFactory
    |
    v
ddl-auto=validate
    |
    v
Application ready
~~~

Configuration example:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  sql:
    init:
      mode: never
~~~

Migrations create tables and seed required data. Hibernate only checks mappings. Basic SQL initialization is disabled so schema.sql/data.sql cannot accidentally run again.

Do not enable defer-datasource-initialization just to make Flyway run before Hibernate. The defer property controls ordering between basic SQL script initialization and JPA EntityManagerFactory, specifically when you want scripts to run after Hibernate creates the schema.

If reference data must be loaded per release, place INSERTs inside versioned migrations so data is managed alongside the schema.

## 14. Spring Boot Profiles for Dev, Test, and Production

Do not use the same database initialization policy for every environment.

Example application-dev.yaml:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create
    defer-datasource-initialization: true
  sql:
    init:
      mode: always
      data-locations: classpath:db/seed/dev-data.sql
~~~

Example application-test.yaml:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
    defer-datasource-initialization: true
  sql:
    init:
      mode: always
      data-locations: classpath:db/seed/test-data.sql
~~~

Example application-prod.yaml when using Flyway:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  sql:
    init:
      mode: never
~~~

These dev/test configs assume Hibernate owns the schema and scripts only load data after schema creation. Production assumes Flyway or Liquibase manages the schema. Ensure the proper profile is active on deployment; never let create/create-drop slip into production.

## 15. Spring Data JPA Entity Mappings Must Match the Schema

Hibernate validate can catch errors such as missing tables/columns or incompatible mapped data types. Thus, when schema.sql or migrations create the schema, reconcile entity mappings carefully.

Entity example:

~~~java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    private Long id;

    @Column(nullable = false, length = 30, unique = true)
    private String code;

    @Column(nullable = false, length = 120)
    private String name;

    protected Department() {
    }
}
~~~

DDL must provide the departments table and matching columns. Differences in naming strategy, schema name, sequences, identity, enum mapping, precision/scale, and timezone can cause validate or runtime queries to fail.

Do not assume matching column names alone is sufficient. For example:

- Java Long can map to different numeric types depending on the database.
- Enum STRING needs a column storing enum names, not ordinals.
- BigDecimal needs appropriate precision/scale.
- IDENTITY and SEQUENCE use different DDL.
- Table/column names that are SQL keywords require quoting according to database rules.

When schemas are managed by migrations, migrations must accurately reflect the mappings used by the application.

## 16. Seed Data, Reference Data, and Business Data

Not all initial data belongs in data.sql.

Distinguish among:

- **Seed data:** fixed data for dev/test environments, such as a few sample customers.
- **Reference data:** lookup data required by the application, such as roles, currencies, or status codes.
- **Business data:** data generated by user activity, which must never be reloaded on each startup.

Seed data can fit well in data.sql for tests. Critical reference data for production should generally be managed via versioned migrations or a dedicated data sync workflow. Business data must never be reset or re-inserted when the application starts.

If reference data needs updates across releases, migrations can update rows using stable keys. Clearly define whether migrations are permitted to overwrite values modified by operators.

## 17. Script Errors and continue-on-error

Property:

~~~yaml
spring:
  sql:
    init:
      continue-on-error: false
~~~

With continue-on-error=false, script errors fail initialization. This is usually the safest choice because the application should not start with a partially applied schema or incomplete seed data.

If set to true, Spring Boot may continue past certain script errors. This can help in special scenarios but risks masking:

- Tables not created.
- Failed INSERTs.
- Missing constraints.
- Incomplete seed data.
- Part of a script running while subsequent statements did not.

Never set continue-on-error=true just to let the application start. Fix the script or explicitly classify which errors are truly safe to ignore.

DDL/DML failures and script atomicity depend on the database. Do not assume an entire SQL file always rolls back as a single transaction across all engines.

## 18. Testing with @DataJpaTest and Testcontainers

@DataJpaTest typically configures a test slice for JPA, repositories, and test databases. With embedded databases, SQL initialization may run with convenient defaults. However, test behavior can differ from production if engines differ.

Example checking a repository after seed data loads:

~~~java
@DataJpaTest
class DepartmentRepositoryTest {

    @Autowired
    private DepartmentRepository repository;

    @Test
    void loadsSeedDepartment() {
        Department department =
            repository.findById(1L).orElseThrow();

        assertThat(department.getCode()).isEqualTo("ENG");
        assertThat(department.getName()).isEqualTo("Engineering");
    }
}
~~~

This test assumes the schema and seed data initialized before the test method runs. If using data.sql while Hibernate creates the schema, configure defer-datasource-initialization appropriately.

With PostgreSQL/MySQL in production, use Testcontainers to verify the real dialect, DDL, and SQL behavior. Skeleton example:

~~~java
@Testcontainers
@DataJpaTest
class DepartmentPostgresTest {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16");

    // Configure the DataSource from the container with DynamicPropertySource
    // and let Spring run migrations/scripts in the test context.
}
~~~

This is an illustrative skeleton; configure spring.datasource.url, username, and password from the container. Testcontainers helps catch differences between H2 and the production database, especially SQL syntax, sequence/identity, constraints, and data types.

## 19. Multiple DataSources and Initialization Order

Applications with multiple DataSources may have multiple schemas and multiple initialization mechanisms. Default SQL initialization properties typically bind to the auto-configured DataSource. When declaring multiple DataSources manually, do not assume schema.sql/data.sql will automatically run on all of them.

Determine:

- Which DataSource is primary.
- Which repositories use which EntityManagerFactory.
- Which migration tool manages each schema.
- Which scripts run on which database.
- Whether migration order across databases has dependencies.

For custom DataSources, you may need separate initializers such as DataSourceScriptDatabaseInitializer or separate Flyway/Liquibase configurations per DataSource. Each initializer must bind to the right DataSource and be clearly ordered before its corresponding EntityManagerFactory.

Do not run the same data.sql against multiple databases if its contents do not fit all schemas.

## 20. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| data.sql reports table not found | Script runs before Hibernate when no schema exists | Run schema.sql first or defer when Hibernate creates tables |
| Seed data disappears after startup | Hibernate create/create-drop runs after script and recreates schema | Fix ordering or use a single schema creation source |
| data.sql does not run on PostgreSQL | mode is set to embedded | Set spring.sql.init.mode=always if genuinely needed |
| Duplicate key on restart | data.sql re-runs on every startup | Use idempotent seeding or versioned migrations |
| schema.sql creates duplicate tables with Hibernate | Both own the schema | Pick a single schema creation source |
| Hibernate validate fails | Entity mapping differs from DDL | Fix migration/schema or mapping |
| Platform-specific script not picked up | Incorrect platform or filename | Check spring.sql.init.platform and resource path |
| App starts despite missing seed data | continue-on-error=true masks errors | Set false and fix the root cause |
| Works in dev but fails in prod | Using H2 or non-portable SQL syntax | Test on production database via Testcontainers |
| Migration runs after Hibernate | Misconfigured dependencies/initializers | Use standard Flyway/Liquibase integration and check startup logs |
| With multiple DataSources only one DB has data | Initializer bound to only one DataSource | Configure separate initializers/migrations per source |
| ddl-auto=update makes schema hard to control | Using Hibernate instead of migration versioning | Use Flyway/Liquibase and validate |

## 21. Checklist for Choosing the Right Initialization Order

- [ ] Determine whether schema.sql, Hibernate, or Flyway/Liquibase manages the schema.
- [ ] If schema.sql creates tables, run SQL initialization before JPA and choose an appropriate ddl-auto such as validate.
- [ ] If Hibernate creates the schema and data.sql inserts afterward, enable defer-datasource-initialization=true.
- [ ] Never let both schema.sql and Hibernate create the same tables.
- [ ] Understand spring.sql.init.mode: embedded, always, and never.
- [ ] Verify platform-specific scripts and resource locations.
- [ ] Design data.sql to be safely re-runnable or use versioned migrations.
- [ ] Keep continue-on-error=false for required initialization.
- [ ] Use separate profiles for dev, test, and production.
- [ ] Use Flyway/Liquibase for production schemas with change history.
- [ ] Use ddl-auto=validate when Hibernate must verify migration-created schemas.
- [ ] Test startup from an empty database and from a previous schema version.
- [ ] Test on the exact database engine/driver using Testcontainers.
- [ ] For multiple DataSources, bind initializers/migrations explicitly to each source.

## 22. Conclusion

By default, Spring Boot's basic SQL initialization runs before JPA EntityManagerFactory initialization finishes; schema.sql runs before data.sql. Hibernate then applies ddl-auto. Consequently, if Hibernate recreates the schema after data.sql has inserted rows, seed data can be wiped out.

If schema.sql is the table-creation source, let scripts run before Hibernate and use an appropriate ddl-auto such as validate. If Hibernate creates the schema and data.sql inserts data afterward, enable spring.jpa.defer-datasource-initialization=true and avoid creating duplicate tables in schema.sql. For production, prefer Flyway or Liquibase for versioned schema management, Hibernate validate for mapping checks, and startup testing against the actual deployment database.