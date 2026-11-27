# Initializing Schemas and Managing Migrations with Flyway or Liquibase

## Lesson Objectives

In the **JDBC Persistence** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson guides you through initializing and managing schemas for Spring Authorization Server using **Flyway** or **Liquibase** in a **Spring Boot** application.

When migrating an Authorization Server from in-memory storage to JDBC, creating tables is only the first step. Schemas must match the running Spring Authorization Server version; migrations must be ordered, tracked, and reproducibly deployable across development, testing, staging, and production.

Spring Authorization Server provides three commonly used JDBC components:

- **JdbcRegisteredClientRepository** stores configurations of registered OAuth2/OIDC clients.
- **JdbcOAuth2AuthorizationService** stores authorizations and the tokens/metadata attached to them.
- **JdbcOAuth2AuthorizationConsentService** stores user consent decisions for clients.

These three components depend on three SQL schema resources provided by Spring. Flyway or Liquibase should manage those DDLs as migrations inside the application's source control. Never let multiple mechanisms create and modify the same schema simultaneously.

After this lesson, you will be able to:

1. Explain the roles and relationships of the three JDBC tables in Spring Authorization Server.
2. Locate the exact three SQL schema resources in the active dependency.
3. Create versioned migrations with Flyway or changelogs/changesets with Liquibase.
4. Choose migration order and configure Spring Boot so migrations finish before repositories are used.
5. Adapt schemas for PostgreSQL, MySQL, or the target database management system.
6. Manage checksums, baselines, rollbacks, schema drift, and Spring Authorization Server upgrades.
7. Test migrations on clean databases and databases already containing data.
8. Deploy production migrations with least privilege, backups, expand/contract, and a recovery plan.

> **Running Scenario:** A team is deploying an Authorization Server for `auth.example.com`. Local environments use an empty database; staging holds test clients and consents; production already stores authorization codes, access tokens, and refresh tokens. The same migration set must create fresh schemas and upgrade legacy schemas without breaking active login sessions.

## 1. Why Manage Schemas with Migrations?

### 1.1. JDBC Repositories Require Properly Structured Tables

Spring Authorization Server's JDBC implementations do not automatically create tables on every startup. They query and write data according to the schema defined by the framework.

| Component | Interface | Main table | Contents |
|---|---|---|---|
| **JdbcRegisteredClientRepository** | `RegisteredClientRepository` | `oauth2_registered_client` | Client ID, secret, authentication methods, grant types, redirect URIs, scopes, client/token settings. |
| **JdbcOAuth2AuthorizationService** | `OAuth2AuthorizationService` | `oauth2_authorization` | Principal, grant type, authorized scopes, attributes, authorization code, access token, refresh token, ID Token, device/user code, and metadata. |
| **JdbcOAuth2AuthorizationConsentService** | `OAuth2AuthorizationConsentService` | `oauth2_authorization_consent` | Client, principal, and authorities/scopes consented by the user. |

If a repository queries a non-existent column, encounters incompatible data types, or hits a wrong table name, OAuth2/OIDC requests fail immediately during client authentication, authorization, token issuance, introspection, revocation, or consent flows.

**Note:** The three tables above constitute the persistence layer for Spring Authorization Server. They do not replace application tables for users, passwords, authorities, tenants, audits, or profiles. If form login uses a JDBC user store, Spring Security's user schema is a separate group and must be managed under the same system migration workflow.

### 1.2. More Than Just Creating Tables Once

Schemas evolve over a product's lifecycle:

- Upgrading Spring Authorization Server may change SQL resources or how repositories read/write.
- The application may need additional indexes, columns, constraints, or audit tables.
- Production databases contain data that must be preserved.
- Multiple environments must keep consistent schemas.
- A deployment may start multiple application instances concurrently.
- When a migration error occurs, you need to know the exact database state and how to recover.

Migration tools record the history of applied changes. That allows a fresh database to be built from scratch and a running database to be upgraded through reviewed steps.

### 1.3. Choose One Schema Management Mechanism

Spring Boot supports SQL script initialization, Flyway, and Liquibase. For production schemas, pick **one primary mechanism** as the source of truth.

| Mechanism | Best suited when | Key considerations |
|---|---|---|
| Flyway | The team wants sequential migrations in SQL or Java, where each versioned migration runs once. | Keep applied migrations immutable; verify checksums. |
| Liquibase | The team wants changelogs with changesets, preconditions, contexts/labels, and rollback metadata. | Changeset identity consists of author, id, and file path; keep changelog paths stable. |
| `schema.sql` / `data.sql` | Demos or small apps with simple initialization needs. | Lacks rich migration history; should not run alongside Flyway/Liquibase. |
| Hibernate `ddl-auto` | Schemas managed by JPA entities within an appropriate scope. | Not the tool for managing the three Authorization Server JDBC repository schemas. |

Do not run both Flyway and Liquibase to manage these three tables. Likewise, do not let `schema.sql`, Hibernate `create`/`update`, and a migration tool modify the same tables together. Having multiple schema owners makes execution order and actual database state hard to determine.

## 2. Three SQL Schema Resources of Spring Authorization Server

### 2.1. Paths Inside the Dependency

The SQL resources are packaged inside Spring Authorization Server. Their classpath resource names are:

| Resource | Consuming repository |
|---|---|
| `org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql` | `JdbcRegisteredClientRepository` |
| `org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql` | `JdbcOAuth2AuthorizationService` |
| `org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql` | `JdbcOAuth2AuthorizationConsentService` |

Extract resources from the **exact dependency version resolved in your build**. Never copy a schema from a blog post, the `main` branch, or another Spring Authorization Server version and assume compatibility.

You can open the dependency JAR with an IDE or archive tool to inspect files under `org/springframework/security/oauth2/server/authorization/`. For migrations, place the selected SQL contents into your application's source tree, review changes, and commit them alongside source code.

Resources inside the JAR do not automatically become Flyway migrations just by being on the classpath. Flyway looks for migrations in `classpath:db/migration` by default; Liquibase reads its configured changelog. Place DDLs into the location and format managed by your migration tool.

### 2.2. Registered Client Table

The `oauth2_registered_client` table stores OAuth2/OIDC client metadata. Typical columns include:

- `id`: unique internal key of the `RegisteredClient`.
- `client_id`: client identifier sent in protocol requests.
- `client_id_issued_at`: timestamp when the client ID was issued.
- `client_secret`, `client_secret_expires_at`: secret and secret expiration if the client uses a secret.
- `client_name`: display name.
- `client_authentication_methods`: allowed client authentication methods.
- `authorization_grant_types`: allowed grant types.
- `redirect_uris`, `post_logout_redirect_uris`: registered callback and logout URIs.
- `scopes`: permitted scopes.
- `client_settings`, `token_settings`: serialized client and token configurations.

This is security configuration data. Do not use `client_id` as the primary key instead of `id` when schemas/repositories expect two distinct values. Never store client secrets in plaintext; generate and store secrets using the `PasswordEncoder` matching your application configuration.

### 2.3. Authorization Table

The `oauth2_authorization` table stores the state of an authorization. Depending on grant type, it may contain multiple token types:

- Authorization code.
- Access token and metadata.
- Refresh token and metadata.
- OIDC ID Token and claims/metadata.
- User code and device code.
- Principal name, registered client ID, grant type, authorized scopes, and attributes.

This table holds large and sensitive payloads. Token/metadata/attribute columns can contain long or serialized data; do not arbitrarily replace LOBs with small `VARCHAR`s.

An authorization row may still hold a valid refresh token even after its authorization code has expired. Never delete a row just because one token inside it expired if other tokens still need validation or revocation.

### 2.4. Authorization Consent Table

The `oauth2_authorization_consent` table stores consent decisions keyed by the pair:

- `registered_client_id`: internal ID of the registered client.
- `principal_name`: End-User's principal name.
- `authorities`: set of granted authorities, typically including scopes.

The primary key is usually the `(registered_client_id, principal_name)` pair. If the application changes how principal names are canonicalized or mapped to subjects, evaluate the impact on legacy consents; never key consents by mutable emails or display names.

### 2.5. Table Creation Order

A clear creation order is:

1. `oauth2_registered_client`
2. `oauth2_authorization`
3. `oauth2_authorization_consent`

Both Authorization and Consent reference the client via `registered_client_id` at the data level. Standard SQL scripts may not declare foreign keys between these tables; the order above reflects domain dependencies and helps readers understand relationships. If adding foreign keys or `ON DELETE CASCADE` yourself, review client deletion policies, authorization retention, and repository behavior before deploying.

## 3. Preparing Migrations for the Project

### 3.1. Directory Structure

Example with Flyway:

~~~text
src/
  main/
    resources/
      db/
        migration/
          V001__create_oauth2_registered_client.sql
          V002__create_oauth2_authorization.sql
          V003__create_oauth2_authorization_consent.sql
~~~

Example with Liquibase:

~~~text
src/
  main/
    resources/
      db/
        changelog/
          db.changelog-master.yaml
          sql/
            oauth2-registered-client-schema.sql
            oauth2-authorization-schema.sql
            oauth2-authorization-consent-schema.sql
~~~

Choose only one of these two approaches for this schema. Paths and filenames follow project conventions; the migration tool executes them according to its configuration.

### 3.2. SQL Preparation Workflow

For each schema resource:

1. Check the active dependency version.
2. Open the exact SQL resource inside the JAR.
3. Compare it against the target database's current schema.
4. Select the proper dialect for the database.
5. Place the DDL into its own migration file.
6. Review table names, column names, data types, lengths, keys, and indexes.
7. Run against an empty database of the same engine as production.
8. Verify that repositories can read/write realistic data.
9. Commit the migration; once applied in long-lived environments, never edit old migration contents.

Never copy a schema and apply manual tweaks directly in production. Every change needs a new migration so all environments reproduce the exact same state.

### 3.3. Schemas by Database Vendor

The default SQL resources do not guarantee every data type works verbatim on every database. In particular, the authorization table contains LOB and timestamp columns.

In current Spring Security Authorization Server schemas, notes inside `oauth2-authorization-schema.sql` specify:

- For **PostgreSQL**, change columns declared as `blob` to `text` because PostgreSQL lacks the `blob` type used in that DDL.
- For **PostgreSQL**, change `timestamp` columns to `timestamptz` to store instants accurately with timezone awareness.
- For **MySQL Connector/J**, configure the connection URL with `preserveInstants=true`, `connectionTimeZone=UTC`, and `forceConnectionTimeZoneToSession=true` to preserve instants properly.

Inspect the resource comments in your **exact running version**; if that version includes different guidance, prioritize the notes bundled with the dependency. Never guess data type changes. Test how the JDBC driver binds and reads LOBs after migration.

Illustrative MySQL URL example:

~~~properties
spring.datasource.url=jdbc:mysql://db.example.com:3306/authdb?preserveInstants=true&connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
~~~

For PostgreSQL, migrations must use PostgreSQL-compatible data types for all corresponding columns. Create vendor-specific migration sets or use DBMS-conditional changelogs. Never run PostgreSQL SQL on MySQL just because column names match.

### 3.4. Do Not Arbitrarily Shorten Columns

Columns such as `client_settings`, `token_settings`, `attributes`, `metadata`, and token values can grow depending on configuration, claims, grant types, or application extensions.

Before changing lengths:
- Determine maximum serialized sizes produced by mappers.
- Check token formats, claims, and authorization attributes.
- Check database support for appropriate LOB/Text types.
- Test large payloads through the JDBC repository itself.
- Confirm token lookup queries still work.

Do not add generic indexes onto LOB/TEXT columns. Indexability and length limits depend on the vendor. Measure query plans before adding custom indexes.

## 4. Managing Schemas with Flyway

### 4.1. How Flyway Works

Flyway uses versioned migrations, typically named as:

~~~text
V001__create_oauth2_registered_client.sql
V002__create_oauth2_authorization.sql
V003__create_oauth2_authorization_consent.sql
~~~

Flyway records history in `flyway_schema_history`, including version, description, checksum, applied timestamp, and migration status.

Versioned migrations execute in version order and apply only once. Checksums detect if an already-applied migration's contents were altered.

**Important Rule:** Never modify a versioned migration that has already been applied in a long-lived environment. If a schema change is needed, create a new migration with a higher version.

### 4.2. Flyway Migration Example

Create three migration files under `src/main/resources/db/migration`. Each file contains the full DDL of the corresponding SQL resource selected and adapted for the target vendor.

~~~sql
-- V001__create_oauth2_registered_client.sql
-- Paste the full DDL from the schema resource of the exact SAS version.
-- Do not leave placeholders or partial CREATE TABLE statements in a real migration.
~~~

~~~sql
-- V002__create_oauth2_authorization.sql
-- Paste the full dialect-adjusted oauth2-authorization-schema.sql DDL.
~~~

~~~sql
-- V003__create_oauth2_authorization_consent.sql
CREATE TABLE oauth2_authorization_consent (
    registered_client_id varchar(100) NOT NULL,
    principal_name varchar(200) NOT NULL,
    authorities varchar(1000) NOT NULL,
    PRIMARY KEY (registered_client_id, principal_name)
);
~~~

The DDL above illustrates the small consent table from the current schema resource. For the Registered Client and Authorization tables, place the **full** DDL from the exact version's SQL resource into each respective file; comments in the first two blocks mark where the content goes, not runnable schema-creating migrations. Never run placeholder migrations and mark the schema as created.

If the project already has `V001`/`V002` migrations, choose the next unused version. Versions must be unique within the same migration location.

### 4.3. Spring Boot Configuration

Example configuration:

~~~yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration
    validate-on-migrate: true
  sql:
    init:
      mode: never
~~~

`spring.flyway.locations` specifies where to locate migrations. If your database requires a vendor-specific Flyway module, add that module per the Spring Boot/Flyway version guide and let dependency management handle versions.

Spring Boot can invoke `Flyway.migrate()` automatically at startup. Beans using JDBC operations are recognized by Spring Boot as depending on database initialization in standard configurations. If the application has custom initializers or multiple `DataSource`s, verify initialization ordering explicitly.

In production, migrations can run as a separate release/job step before rolling out the application. This separates DDL privileges from runtime data-access privileges and prevents multiple application instances from taking responsibility for schema changes at the same time.

### 4.4. Common Flyway Commands

~~~bash
flyway info
flyway validate
flyway migrate
~~~

- `info`: view applied migrations, pending migrations, and current version.
- `validate`: verify applied migrations match existing files, including checksums.
- `migrate`: apply pending migrations.

Do not run `repair` solely to silence checksum errors. First identify why the checksum differs: an edited file, a renamed/deleted migration, or an environment using the wrong location. `repair` only updates schema history metadata per a reviewed decision; it does not fix DDL or restore data.

### 4.5. Baselining an Existing Database

If production already contains the three tables before adopting Flyway, do not run initial table-creation migrations directly against that database. Instead:

1. Back up the database.
2. Compare the actual structure with the schema of the exact version.
3. Inspect data, indexes, constraints, data types, and history tables.
4. Choose a baseline version matching the verified schema.
5. Run a controlled `baseline` command on the existing database.
6. Ensure fresh databases still execute all schema-creating migrations from the beginning.
7. Run `validate` and verify repositories.

Do not enable `baseline-on-migrate` indiscriminately in production. Mistakenly baselining an incomplete schema as complete can cause Flyway to skip essential table-creation migrations.

### 4.6. Repeatable Migrations

Flyway also supports repeatable migrations, commonly used for views, procedures, or reference data that should be recreated when content changes.

Do not use repeatable migrations to recreate the three core OAuth2 tables. Foundational schema DDL should be versioned migrations so ordering and state are strictly controlled.

## 5. Managing Schemas with Liquibase

### 5.1. Changelogs and Changesets

Liquibase stores changes in changelogs. Each changeset is identified by **author**, **id**, and changelog path. Liquibase records history in `DATABASECHANGELOG` and uses `DATABASECHANGELOGLOCK` to coordinate updates.

By default, a changeset is not re-run once recorded. When changes are needed, add a new changeset. Never modify a changeset already applied in long-lived environments, as checksums and deployment history will become inconsistent.

Liquibase typically runs changesets inside transactions when supported by the database. DDL transaction behavior varies across vendors; do not assume a multi-statement changeset rolls back atomically on every DBMS.

### 5.2. YAML Changelog Using sqlFile

Example `src/main/resources/db/changelog/db.changelog-master.yaml`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-oauth2-registered-client
      author: platform
      comment: Create Spring Authorization Server registered client table
      changes:
        - sqlFile:
            path: sql/oauth2-registered-client-schema.sql
            relativeToChangelogFile: true
            splitStatements: true

  - changeSet:
      id: 002-create-oauth2-authorization
      author: platform
      comment: Create Spring Authorization Server authorization table
      changes:
        - sqlFile:
            path: sql/oauth2-authorization-schema.sql
            relativeToChangelogFile: true
            splitStatements: true

  - changeSet:
      id: 003-create-oauth2-authorization-consent
      author: platform
      comment: Create Spring Authorization Server consent table
      changes:
        - sqlFile:
            path: sql/oauth2-authorization-consent-schema.sql
            relativeToChangelogFile: true
            splitStatements: true
~~~

Place the three SQL files in `src/main/resources/db/changelog/sql/`. Each file contains the full DDL taken from the exact version's resource and adapted for the target database.

If you prefer Liquibase Change Types instead of SQL files, you can describe tables with `createTable`, `addColumn`, `addPrimaryKey`, and related change types. However, the Authorization table has many LOB columns and specific data types; using the SQL resources as a baseline makes comparing against the framework schema easier. Liquibase still manages ordering and changeset history.

### 5.3. Spring Boot Configuration

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  sql:
    init:
      mode: never
~~~

Spring Boot runs Liquibase automatically when the starter/module is on the classpath and enabled. You can customize the changelog path via `spring.liquibase.change-log`.

If the application needs a separate `DataSource` for migrations, Spring Boot supports `@LiquibaseDataSource` or dedicated Liquibase connection properties. Just like Flyway, migrations do not have to share the same database credentials as application runtime.

### 5.4. Preconditions, Contexts, and DBMS

Liquibase supports preconditions to check conditions before executing a changeset, such as database vendor, schema existence, or whether a table/column does not yet exist. Contexts/labels can control migrations intended for tests or specific environments.

Vendor-specific SQL variations should be expressed explicitly:
- PostgreSQL changelogs use DDL with `text`/`timestamptz` per schema resource guidance.
- MySQL changelogs use compatible data types and JDBC driver timezone settings.
- Never let a generic changeset silently execute DDL that is valid only on one vendor.

When using `sqlFile`, check `relativeToChangelogFile`, statement splitting, and delimiters. Run Liquibase against the target database engine before releasing.

### 5.5. Rollbacks with Liquibase

Liquibase supports rollbacks by tag, timestamp, or changeset count. Some Change Types provide automatic rollbacks; SQL changesets and operations without clear inverses require manually authored rollbacks.

However, **DDL rollback does not equate to data recovery**. If a changeset created a table and production subsequently wrote tokens/authorizations into it, rolling back with `DROP TABLE` destroys authentication data. For the three Authorization Server tables, planned backup/restore or creating a roll-forward migration to fix issues is usually much safer.

Do not put table-dropping rollbacks into production pipelines and treat them as the default recovery strategy.

## 6. Choosing Flyway or Liquibase?

Both can manage the three schema resources. Choose based on your team's workflow and existing migration standards in your system.

| Criterion | Flyway | Liquibase |
|---|---|---|
| Management unit | Versioned/repeatable migrations. | Changelogs and changesets. |
| Identity | Version, description, and checksum. | Author, id, changelog path, and checksum. |
| Authoring DDL | SQL or Java migrations. | Change Types, SQL, or `sqlFile`. |
| Ordering | By version; repeatable runs after versioned. | By changelog/include order. |
| Conditionals | Locations, vendor locations, and callbacks. | Preconditions, contexts, labels, `dbms`. |
| Rollback | Varies by edition/migration type; must be designed upfront. | Automatic rollback for certain Change Types; SQL requires manual rollback. |
| Best fit | Teams preferring simple, sequential SQL migrations. | Teams needing structured change descriptions, preconditions, and rollbacks in changelogs. |

Do not pick both to “increase safety.” A single source of history ensures every environment shares the same understanding of schema state.

## 7. Connecting JDBC Repositories to Migrated Schemas

Once migrations have created all three tables, configure Spring Authorization Server to use the JDBC implementations instead of in-memory services.

### 7.1. Declaring JDBC Beans

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration
class JdbcAuthorizationPersistenceConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            JdbcTemplate jdbcTemplate) {
        return new JdbcRegisteredClientRepository(jdbcTemplate);
    }

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationService(
                jdbcTemplate, registeredClientRepository);
    }

    @Bean
    OAuth2AuthorizationConsentService authorizationConsentService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationConsentService(
                jdbcTemplate, registeredClientRepository);
    }
}
~~~

`JdbcTemplate` implements `JdbcOperations`, so it can be passed directly into the JDBC component constructors. `RegisteredClientRepository` is shared by both the Authorization Service and the Consent Service to resolve `RegisteredClient` instances.

`RegisteredClientRepository` is a required component of the Authorization Server. `OAuth2AuthorizationService` and `OAuth2AuthorizationConsentService` can fall back to default in-memory implementations if unconfigured; therefore, verify that the two JDBC beans above are actually injected, otherwise authorization/consent data will be lost on process restart. API documentation also describes the JDBC implementations as simple and warns they may not meet high-throughput environments; benchmark realistic loads before choosing them for large deployments.

### 7.2. Wiring into the Authorization Server Configurer

Configuration structure example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        RegisteredClientRepository registeredClientRepository,
        OAuth2AuthorizationService authorizationService,
        OAuth2AuthorizationConsentService authorizationConsentService)
        throws Exception {

    OAuth2AuthorizationServerConfigurer configurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(configurer.getEndpointsMatcher())
        .with(configurer, authorizationServer -> authorizationServer
            .registeredClientRepository(registeredClientRepository)
            .authorizationService(authorizationService)
            .authorizationConsentService(authorizationConsentService)
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This wires the services into the Authorization Server. A complete application also needs `RegisteredClientRepository`, a JWK source, `JwtDecoder`, issuer settings, login chain, sessions, and OIDC/OAuth2 endpoints matching the product scope.

### 7.3. Initial Client Registration

Schemas only create tables; they do not automatically create application clients. Provision `RegisteredClient` records via controlled data migrations, an idempotent bootstrap job, or a dedicated client administration workflow.

Never insert production clients manually into the database with plaintext secrets. If seeding clients via SQL, generate secrets using the exact `PasswordEncoder` and store the encoded value. For clients with secret rotation, use governed admin processes and auditing instead of editing production rows directly.

## 8. Startup Order and Spring Boot Configuration

### 8.1. Migrations Must Run Before Repository Access

Target sequence:

~~~mermaid
flowchart TD
    A[Application or Release Job starts] --> B[Connect to target DataSource]
    B --> C[Flyway migrate or Liquibase update]
    C --> D[Verify migration history and schema]
    D --> E[Create JDBC repositories and services]
    E --> F[Start Authorization Server endpoints]
    F --> G[Accept OAuth2 and OIDC traffic]
~~~

Spring Boot recognizes Flyway/Liquibase as database initializers and includes dependency detection for many JDBC beans. If the application has custom initialization code, manually constructed beans, or multiple `DataSource`s, ensure repositories do not query before migrations finish.

### 8.2. Use Only One Schema Initializer

Example when choosing Flyway:

~~~yaml
spring:
  flyway:
    enabled: true
  liquibase:
    enabled: false
  sql:
    init:
      mode: never
~~~

Example when choosing Liquibase:

~~~yaml
spring:
  flyway:
    enabled: false
  liquibase:
    enabled: true
  sql:
    init:
      mode: never
~~~

If not using JPA, do not add Hibernate configuration. If the project uses JPA for another domain, never let `ddl-auto=create`, `create-drop`, or `update` alter schemas managed by the migration tool. Choose `validate` or `none` depending on JPA's role and project workflow.

### 8.3. Separating Migration and Runtime Privileges

A secure production setup:

| Account | Privileges |
|---|---|
| Migration user | DDL needed for migrations, read schema history/changelog, create indexes/alter tables per release. |
| Application user | Only required CRUD on runtime tables, without arbitrary privileges to drop/alter schemas. |
| Read-only/audit user | Read-only access to approved data for verification, reporting, or audits. |

Flyway/Liquibase can be configured to use a separate `DataSource` via `@FlywayDataSource`, `@LiquibaseDataSource`, or dedicated connection properties. Never store passwords in source control; use a secret manager or environment variables.

### 8.4. Protecting OAuth2 Data in the Database

The Authorization table can contain authorization codes, access tokens, refresh tokens, ID Tokens, and metadata. Treat this database as a credential store:

- Enable encryption at rest for databases, volumes, and backups per organizational standards.
- Restrict direct `SELECT` access on the authorization table; do not grant broad read access to analysts or unrelated apps.
- Never write tokens, authorization payloads, or client secrets into application logs, SQL logs, or traces.
- Encrypt JDBC transport with TLS when the database sits outside the process trust boundary.
- Protect snapshots/backups and verify restore workflows maintain the same protection level.
- Monitor access privileges and client registration changes with appropriate auditing.

Do not assume using a JDBC repository automatically encrypts all token values at the application layer. Review the implementation and deployment security requirements; if column-level encryption is required, design it in harmony with how the repository serializes, searches, and reads tokens.

## 9. Schema Upgrades and Production Rollouts

### 9.1. Schemas Must Stay Compatible with the Application Version

When upgrading Spring Authorization Server:
1. Identify the exact old and new dependency versions.
2. Diff the three SQL schema resources between the two versions.
3. Inspect repository/row mapper source code if column types or columns changed.
4. Determine migrations needed for existing data.
5. Test upgrading from the old schema populated with realistic data.
6. Deploy migrations according to the release plan.
7. After migration, run smoke tests before accepting traffic.

Do not assume the framework migrates the database automatically simply because a dependency version was bumped. Schema migrations are an application/deployment responsibility.

### 9.2. Expand/Contract for Multi-Instance Deployments

When changing schemas while multiple application versions run concurrently, use the expand/contract strategy:

1. **Expand:** add new columns or structures backward-compatibly with the old app; typically nullable or with safe defaults.
2. **Deploy compatibility code:** new application instances can read both old and new data and write according to transition rules.
3. **Backfill:** migrate legacy data in resumable batches with metrics.
4. **Switch:** shift reads/writes to the new structure once every instance is compatible.
5. **Contract:** drop old columns/constraints only in a later release when no instances or jobs still use them.

Never drop or rename columns in the same release while an older instance is still running old queries. With authorization data, migrate with extra care because token requests may be in flight during rollout.

### 9.3. Backups and Recovery

Before migrations with destructive changes or LOB conversions:
- Back up the database and verify restore capability.
- Record the current migration version.
- Measure expected runtime, locks, and disk space.
- Confirm retention for authorizations/refresh tokens.
- Assign an owner responsible for go, pause, or roll-forward decisions.
- Retain migration logs with sensitive data redacted.

If a migration partially fails, do not re-run blindly. Inspect the database's transaction behavior, history table state, applied DDL, and affected data before proceeding.

### 9.4. Never Wipe Token Data to “Clean Up the Schema”

The Authorization table holds credentials and security-relevant metadata. Truncating or dropping the entire table to work around a failed migration breaks valid authorizations and can disrupt logins/refreshes.

If cleanup is needed:
- Identify tokens that are expired, revoked, and no longer needed for protocol flows.
- Account for refresh tokens, device/user codes, and related authorization state.
- Execute bounded, resumable batches.
- Emit audit logs/metrics on deleted row counts.
- Verify revocation, introspection, and retention policies before purging.

## 10. Testing Migrations and JDBC Persistence

### 10.1. Testing on an Empty Database

Every migration must succeed on a fresh database matching the supported vendor/version.

Checklist:

- Migration finishes without errors.
- All three tables are created with exact names.
- Columns and primary keys match the schema.
- No table is created twice.
- Migration history records the proper version/changeset.
- Spring context boots cleanly with the JDBC repositories.

### 10.2. Testing on a Populated Database

Migration testing does not stop at `CREATE TABLE`. Create data via the repositories and verify it after migrations or upgrades:

| Operation | What to verify |
|---|---|
| `RegisteredClientRepository.save()` and `findByClientId()` | Client metadata, scopes, settings, and encoded secrets remain intact. |
| `OAuth2AuthorizationService.save()` and `findByToken()` | Authorizations, token values, timestamps, metadata, and attributes can be read back. |
| `OAuth2AuthorizationConsentService.save()` and `findById()` | Consents per registered client and principal remain accurate. |
| Application restart | Data survives process stop and restart. |
| Refresh/revoke/introspection | Flows reading/writing authorizations continue working. |
| Device authorization (if enabled) | User codes/device codes are persisted and queryable. |

### 10.3. Use Testcontainers or Equivalent Real Databases

H2 is convenient for fast tests, but cannot substitute for testing the production vendor. LOBs, timestamps, indexes, locking, transactional DDL, and collations can differ.

If production uses PostgreSQL, run migrations and repository integration tests on PostgreSQL. If MySQL is supported, add a dedicated MySQL job/test suite. Use the exact same migration files as production; never build test schemas from a separate DDL set.

### 10.4. Testing Migration Idempotency and Upgrades

- First run on a clean database: migrations apply cleanly.
- Second run: does not recreate tables or re-run versioned changesets.
- `validate`/history check: zero checksum drift.
- Upgrade from an older version: runs only pending new migrations.
- Mid-run failure test: know the exact database state and recovery procedure.

Never use `CREATE TABLE IF NOT EXISTS` to mask migration errors. It can silently skip an existing table with the wrong structure, leaving the application running against an incompatible schema.

## 11. Common Pitfalls and Resolutions

| Symptom | Possible cause | Resolution |
|---|---|---|
| `relation`/`table does not exist` | Migrations haven't run, wrong schema/catalog, or wrong `DataSource`. | Check migration history, database/schema, and the URL actually used by the migration tool. |
| `column not found` | SQL resource mismatches dependency version or missing migration. | Compare JAR resource against applied migrations; add a supplementary migration. |
| `BLOB` type unsupported | Used default schema on PostgreSQL without adapting types per guide. | Choose appropriate PostgreSQL DDL and verify LOB mapping. |
| Timestamp hour offset | Database/JDBC driver disagree on UTC/instant handling. | Apply timestamp types and JDBC URL options per vendor/resource guidance. |
| Duplicate table at startup | Running `schema.sql`, Hibernate DDL, and Flyway/Liquibase together. | Pick one schema owner; disable other initializers. |
| Flyway checksum mismatch | Versioned migration edited after being applied. | Restore original file or add a new migration; use `repair` only after reviewing history. |
| Liquibase checksum mismatch | Applied changeset modified or path/identity changed. | Restore changeset or add a new changeset; never delete history arbitrarily. |
| Repository returns `null` despite rows in table | Wrong `DataSource`/schema, mapper/version mismatch, or invalid manually inserted format. | Check constructors, SQL, registered client IDs, and data serialization. |
| Tokens lost after restart | Still using `InMemory` services/repositories. | Register JDBC beans and verify they are injected into the configurer. |
| Long migration locks | DDL/index/backfill causing locks or migration running on another node. | Inspect DB sessions/locks, migration plan, and execution window; never manually delete lock/history rows. |
| Slow authorization queries | Built-in JDBC implementation or indexes inadequate for load. | Inspect query plans, benchmark; evaluate vendor-specific indexes or custom repository. |
| Upgrade breaks token reads | Schema resource or serialization contract changed. | Diff versions, test upgrades against real data, and add compatibility migrations. |

## 12. Hands-On Exercise

**Scenario:** An Authorization Server has local, staging, and production environments. Local uses a PostgreSQL container. Production already holds client registrations, authorization codes, access/refresh tokens, and consents.

### Requirements

1. Identify the Spring Authorization Server version in dependencies.
2. Extract the three corresponding SQL resources from the exact JAR.
3. Create Flyway migrations with unique versions or a Liquibase changelog with three changesets.
4. Convert DDL to the PostgreSQL dialect per schema resource notes, including LOBs and timestamps.
5. Configure Spring Boot to use only the chosen migration tool.
6. Create JDBC beans for `RegisteredClient`, `Authorization`, and `Consent`.
7. Start the Authorization Server on an empty database.
8. Create a client, run an Authorization Code Flow, issue tokens, and save consent.
9. Restart the application and verify clients/authorizations/consents persist.
10. Add a backward-compatible migration and run it on staging with existing data.
11. Check Flyway `validate` or Liquibase changelog history.
12. Test upgrading Spring Authorization Server on a test branch, diff schema resources, and document required migrations.
13. Design a backup/roll-forward plan for production.
14. Separate migration credentials from runtime credentials.

**Completion Criteria:** fresh databases are created properly; existing databases upgrade without data loss; JDBC repositories read and write cleanly; migration history is consistent; application runtime holds no unnecessary DDL privileges.

## 13. Pre-Production Checklist

- [ ] Spring Authorization Server/Spring Security version pinned.
- [ ] Three SQL resources extracted from the exact dependency version.
- [ ] Migration files committed to source control.
- [ ] Only one tool manages the schema: Flyway or Liquibase.
- [ ] No other initializer modifies the OAuth2 tables.
- [ ] Creation order for Registered Client, Authorization, and Consent is explicit.
- [ ] DDL adapted and tested on the target database vendor.
- [ ] `BLOB`/`TEXT` and timestamps/timezones verified.
- [ ] Token/metadata columns are not shortened without benchmarking and bounds checks.
- [ ] Flyway versions/checksums or Liquibase changeset identities are stable.
- [ ] Applied migrations/changesets are never edited in long-lived environments.
- [ ] Existing databases are baselined only after comparing schemas, never blindly skipping migrations.
- [ ] Dedicated migrations exist for every new schema change.
- [ ] Tests cover both empty and populated databases.
- [ ] Integration tests cover all three JDBC repositories.
- [ ] Application restarts preserve clients, authorizations, and consents.
- [ ] Migrations complete before the Authorization Server receives traffic.
- [ ] Backups and restore rehearsals exist prior to risky migrations.
- [ ] Expand/contract plan exists for rolling deployments.
- [ ] Migration user and application user have separated privileges.
- [ ] Logs never print tokens, client secrets, or authorization payloads.
- [ ] Retention/cleanup policy exists for expired or revoked authorizations.
- [ ] Runbook exists for checksum mismatches, failed migrations, and database locks.

## Summary

Spring Authorization Server provides three JDBC schema resources for Registered Client, Authorization, and Authorization Consent. The JDBC components depend directly on these table structures; thus, schemas must match the running framework version and database vendor.

Flyway manages versioned migrations by order and checksum; Liquibase manages changelogs/changesets with history, preconditions, and rollbacks. Either can deploy the three SQL resources, though each schema should have only one migration owner. Spring Boot supports running migrations at startup; for production, migrations can be separated into a release job using dedicated DDL credentials.

The hardest challenges usually lie in database compatibility and upgrading existing data: LOBs, timestamps/timezones, schema drift, concurrent application instances, and active tokens. Test against the production database engine, keep migrations immutable once applied, take backups before risky changes, and prefer roll-forward when a rollback could destroy authorization data.

## References

1. [Spring Authorization Server 1.5.8 — JdbcRegisteredClientRepository API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/JdbcRegisteredClientRepository.html): classpath schema resource and JDBC repository for `RegisteredClient`.
2. [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html): schema resource, JDBC operations, `LobHandler`, and throughput limits.
3. [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationConsentService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationConsentService.html): schema resource and consent persistence.
4. [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClientRepository`, `OAuth2AuthorizationService`, and `OAuth2AuthorizationConsentService`.
5. [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): Flyway, Liquibase, SQL initialization, and database initialization ordering.
6. [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): versioning, ordering, checksums, and immutability of applied migrations.
7. [Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate): validating applied migrations against current migration files.
8. [Flyway — Schema History Table](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/flyway-schema-history-table): history, checksums, and migration status.
9. [Liquibase Community — What is a Changeset?](https://docs.liquibase.com/community/user-guide-5-0/what-is-a-changeset): changeset identity, checksums, and execution order.
10. [Liquibase Community — YAML Changelog Example](https://docs.liquibase.com/community/user-guide-5-0/yaml-changelog-example): YAML changelog structure.
11. [Liquibase Community — sqlFile](https://docs.liquibase.com/community/reference-guide-5-0/change-types/sqlfile): using SQL files in changesets.
12. [Liquibase Community — Preconditions](https://docs.liquibase.com/oss/user-guide-4-33/what-are-preconditions): controlling changeset execution with preconditions.
13. [Liquibase Community — Rollback](https://docs.liquibase.com/community/reference-guide-5-0/init-update-and-rollback-commands/rollback): tag-based rollbacks and manual rollback requirements for SQL changesets.
14. [Spring Security source — oauth2-authorization-schema.sql](https://github.com/spring-projects/spring-security/blob/main/oauth2/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql): authorization DDL example and PostgreSQL/MySQL notes; always cross-check the resource in your active dependency version.
15. [Spring Security source — oauth2-registered-client-schema.sql](https://github.com/spring-projects/spring-security/blob/main/oauth2/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql): Registered Client DDL example and vendor timestamp notes.
16. [Spring Security source — oauth2-authorization-consent-schema.sql](https://github.com/spring-projects/spring-security/blob/main/oauth2/oauth2-authorization-server/src/main/resources/org/springframework/security/oauth2/server/authorization/oauth2-authorization-consent-schema.sql): Authorization Consent DDL.
