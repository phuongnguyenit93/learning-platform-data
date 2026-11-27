# Managing Connection Secrets and Least Privilege for Application Accounts

A Spring Data JPA application needs authentication credentials to connect to the database, yet database usernames and passwords are operational secrets. If they are stored directly in source code, committed to Git, or printed in logs, anyone without authorized database access could obtain them to read or modify data.

Beyond protecting secrets, the account used by the application must have only the privileges required for its business function. A normally running service typically only needs to read and write a specific set of tables; it does not need privileges to create databases, alter schemas, drop tables, or administer the server. This is the principle of least privilege.

## 1. Distinguishing Connection Configuration from Secrets

A datasource typically needs the following information:

- JDBC URL: server address, port, database, and connection parameters.
- Username: the database identity used by the application.
- Password or equivalent credential: authenticates that identity.
- TLS and network settings: protects the connection and restricts where connections are permitted from.

A JDBC URL is usually not a secret if it only contains the hostname, port, and database name. However, some URL formats allow embedding usernames/passwords or tokens. Never put credentials inside the URL because URLs frequently appear in logs, exceptions, metrics, or diagnostic output.

Application configuration can be managed in version control files as long as it contains no secret values. For example, environment variable names and configuration structure can be committed, while real values are supplied at runtime.

## 2. Never Hard-Code Credentials in Source Code

Do not write passwords directly in Java:

```java
// Don't: the secret gets packaged with the source code.
String password = "production-password";
```

Also never commit real passwords in `application.yml`:

```yaml
spring:
  datasource:
    username: shop_app
    password: production-password
```

These practices allow credentials to persist in Git history, build artifacts, container images, logs, or source copies. Removing a password from the current file does not erase it from Git history; if a secret has been exposed, revoke or rotate the credential.

Instead, use placeholders:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/shop
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
```

At startup, Spring Boot resolves `DB_USERNAME` and `DB_PASSWORD` from the environment or an external configuration source. The YAML file can be safely committed because it contains no real credential values.

Do not set a production password as the default value in a placeholder, such as `${DB_PASSWORD:secret123}`. If a secret is missing, the application should fail with a clear configuration error rather than silently falling back to a weak default password.

## 3. Providing Secrets from the Runtime Environment

Environment variables can be supplied at deployment time:

```bash
export DB_USERNAME=shop_app
export DB_PASSWORD='<injected-at-runtime>'
java -jar store-app.jar
```

In container or orchestrator environments, secrets can be passed to the process via environment variables or mounted as files. Choose the mechanism supported by your deployment platform and restrict who can read those values.

Common sources:

| Source | How It Is Used | Notes |
|---|---|---|
| Environment variable | Platform injects variables when starting the process | Avoid dumping the entire environment into logs or diagnostic dumps. |
| Secret manager | Application or deployment platform fetches secrets using an authorized identity | Requires IAM/access policy management and rotation. |
| Mounted secret file | Platform mounts files readable only by the appropriate user/process | Restrict filesystem permissions and never bake into images. |
| Spring Boot config tree | Maps files in a directory into properties | Useful for Docker/Kubernetes secrets mounted as files. |

With Spring Boot's Config Data API support, you can import a secret directory:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Example mounted directory with files:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

The content of each file is the corresponding value. Filenames map to property keys; credentials never need to be written into YAML. Remove the `optional:` prefix if the secret is mandatory for startup and you want fail-fast behavior when the directory is missing.

In Kubernetes, Secret objects should not be treated as secure merely because values appear in Base64. Base64 is encoding, not encryption. Enable appropriate encryption at rest for the cluster, restrict RBAC, scope secret read permissions by namespace/service account, and consider an external secret manager.

## 4. Configuring DataSource in Spring Boot

Minimal configuration example:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000

  jpa:
    hibernate:
      ddl-auto: validate
```

Datasource properties are bound by Spring Boot to the datasource and connection pool. HikariCP is the default pool in many Spring Boot JDBC/JPA applications when present on the classpath.

Key considerations:

- Configure JDBC URLs per environment, such as development, staging, and production.
- Each environment should have its own credentials; never share production passwords with developer machines.
- Allow connections only from the network/subnet the application requires.
- Enable TLS when supported by the database and deployment environment, and verify certificates according to system policy.
- Never place usernames/passwords in query parameters or log URLs.
- Never expose datasource configuration via public APIs or diagnostic pages.

Profiles like `application-prod.yml` are only a way to select environment-specific configuration. A profile is not a secret store: profile files can hold placeholders, hostnames, and pool settings, but never real passwords.

## 5. Separating the Application Account from the Migration Account

A common design mistake is using the same database account for both the running application and the migration tool. If the application is compromised, an attacker could exploit DDL privileges to alter schemas, create objects, or destroy data.

Separate at least two identities:

- **Runtime account:** used by the Spring Data JPA application while running; granted only the privileges needed for business operations.
- **Migration account:** used by Flyway, Liquibase, or the deployment process to create/alter schemas. DDL privileges are scoped to the managed database/schema.

For example, the runtime account may need `SELECT`, `INSERT`, `UPDATE`, and `DELETE` on specific tables. It typically does not need `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, database creation, superuser, or replication privileges.

The migration account may need to create tables, indexes, constraints, and modify schemas. These credentials are supplied only to the pipeline/deployment job that runs migrations, and kept out of the runtime container when unnecessary.

In production, do not rely on Hibernate `ddl-auto=create` or `update` to alter the schema using the application account. Use Flyway/Liquibase for versioned, auditable migrations, while Hibernate `ddl-auto=validate` catches mapping-schema mismatches without requiring DDL privileges for the application. Depending on deployment policy, `none` may also be chosen if schema validation runs in a separate step.

## 6. Least-Privilege Example on PostgreSQL

Privilege syntax depends on the database. The following example is specific to PostgreSQL and illustrates only a runtime account for an `app` schema.

Create the login role:

```sql
CREATE ROLE shop_app LOGIN;
```

Set the role's password or authentication method through a secure database administration process. Never store real passwords in migration scripts, repositories, or CI/CD logs.

Grant database connection and schema usage:

```sql
GRANT CONNECT ON DATABASE shop TO shop_app;
GRANT USAGE ON SCHEMA app TO shop_app;
```

Grant only the operations the application needs on specific tables:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE app.orders, app.order_items
TO shop_app;
```

If the application uses sequences for auto-generated keys, grant the needed privileges on those sequences:

```sql
GRANT USAGE, SELECT
ON SEQUENCE app.orders_id_seq
TO shop_app;
```

Sequence names must match the actual schema. If there are multiple sequences, grant privileges on each required sequence or configure appropriate default privileges.

So that tables created later by the schema owner automatically grant runtime access, PostgreSQL supports default privileges:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE shop_owner
IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO shop_app;

ALTER DEFAULT PRIVILEGES
FOR ROLE shop_owner
IN SCHEMA app
GRANT USAGE, SELECT ON SEQUENCES TO shop_app;
```

Default privileges apply to objects created in the future by the specified role, here `shop_owner`. They do not retroactively grant privileges on existing tables; run explicit `GRANT` statements for existing objects.

In production, scope privileges to each required table or table group. The example above uses two tables for illustration, not to suggest every application needs all four privileges on every table.

Avoid granting `ALL PRIVILEGES`, `CREATE` on schemas, or owner roles to the runtime account unless required by the business. For some use cases, column-level privileges, views, or stored procedures can further restrict accessible data.

## 7. Verifying That Application Privileges Are Truly Minimal

After granting privileges, test using the runtime account itself—not just a DBA account.

PostgreSQL example:

```sql
-- Allowed operations if appropriate for business logic:
SELECT id, status FROM app.orders LIMIT 1;

-- This operation must be rejected for the runtime account:
CREATE TABLE app.unexpected_table (id BIGINT);
```

A privilege test should verify:

- The application can read the tables it needs to read.
- The application can insert/update/delete only the data it needs to manipulate.
- The application cannot create, alter, or drop schemas/tables when not required.
- The application cannot read administrative tables or data belonging to other services.
- The runtime account has no superuser, owner, or unnecessary administrative privileges.
- The migration job can still perform schema changes using its separate identity.

Do not test destructive commands in production just to verify they are rejected. Use a test or staging database with the identical grant policy.

## 8. Secret Rotation and Connection Pools

Credentials must be rotated periodically or upon suspected exposure. However, changing a secret value in a secret manager does not automatically update passwords inside an active connection pool.

HikariCP holds open connections. When a new connection must be created after the database password changes, the pool may still use the credentials bound when the datasource initialized. Thus, rotation procedures must account for both the database and running datasources.

A safe rotation workflow typically involves:

1. Creating a new credential or preparing a mechanism allowing two credentials to coexist during transition if supported by the database.
2. Updating the secret where it is supplied to the application.
3. Recreating the datasource/connection pool or restarting instances via a tested deployment strategy.
4. Confirming new instances open connections and pass health checks.
5. Shifting all traffic to instances using the new credential.
6. Revoking the old credential once no instances or jobs still use it.

If the database allows only one password per account, plan the cutover window and potential disruption. You can use two login roles granted the same runtime privilege group to rotate sequentially: create the new role, grant equivalent privileges, deploy the new secret, and then revoke the old role. This approach depends on database policies and operational procedures.

Never assume refreshing an environment variable alone is sufficient. Test how the pool creates new connections after rotation.

## 9. Avoiding Secret Leaks via Logs and Diagnostic Endpoints

Credentials can accidentally leak outside config files through:

- Logging full datasource configuration objects.
- Printing exceptions containing URLs or authentication details.
- Writing environment variables into startup diagnostics.
- Exposing `/actuator/env`, `/actuator/configprops`, or admin endpoints to the Internet without access controls.
- Putting secrets into command lines, Dockerfiles, image layers, or CI build arguments.
- Pasting real config files into issues, chats, tickets, or reports.

Spring Boot sanitizes certain sensitive properties on Actuator endpoints, but do not rely on that as an excuse to expose endpoints publicly. Expose only needed endpoints, protect them with authentication/authorization, and restrict network access. Never log raw passwords or tokens.

If a credential has appeared in Git, logs, or tickets, treat it as compromised: revoke/rotate it immediately, investigate access scope, and handle historical copies according to organizational policy. Deleting the password line in a new commit does not revoke an exposed credential.

## 10. Separating Privileges by Environment and Service

Never share a single database account across all applications and environments.

For example:

| Identity | Environment/Scope | Privileges |
|---|---|---|
| `shop_dev_app` | Development | Runtime privileges on dev database |
| `shop_stage_app` | Staging | Runtime privileges on staging database |
| `shop_prod_app` | Production | Least-privilege runtime access on production database |
| `shop_migrator` | Migration pipeline | Required DDL privileges on application schema |
| `reporting_reader` | Reporting | Read-only access to required reporting views/tables |

Separating identities helps:

- Revoke one service's access without disrupting other services.
- Attribute logs/audits to a specific application.
- Limit blast radius if one credential is compromised.
- Rotate credentials on independent schedules.
- Prevent a dev application from accidentally accessing production.

If multiple services share one database, each service should have its own role granted access only to the data it owns or needs. If the database supports row-level security, it can add another layer of protection, provided you understand how session roles and connection pooling interact with policies.

## 11. Least Privilege in Relation to Spring Data JPA

Spring Data JPA does not require the runtime account to hold database administrative privileges. Actual privileges needed depend on application operations:

- Reading entities requires `SELECT`.
- Persisting new entities typically requires `INSERT` and appropriate sequence/identity privileges.
- Dirty checking updates require `UPDATE`.
- Deleting entities requires `DELETE`.
- Native queries or stored procedures require corresponding privileges, such as `EXECUTE`.
- Schema validation needs metadata/catalog read access as supported by the database; it does not require DDL privileges.
- Hibernate schema generation or migrations require DDL privileges and should run under a separate identity.

If the application uses auditing, triggers, stored procedures, or database views, required privileges may differ. Base grants on the actual SQL of each use case and grant the minimum required. Never grant broad permissions simply to silence a `permission denied` error; identify the exact table, sequence, schema, or procedure that was denied.

## 12. Testing Secure Configuration

Checks should exist across multiple layers:

**Configuration checks**

- Config files in Git contain only placeholders or non-sensitive values.
- Secrets are supplied at runtime from an approved source.
- Missing required secrets cause the application to fail fast.
- No real passwords appear in Docker images, artifacts, or CI logs.

**Connectivity checks**

- The application connects using the runtime account.
- Database endpoint and TLS settings match the environment.
- The connection pool can open new connections after a test rotation.
- When credentials are wrong or revoked, health checks and logs report authentication failure without printing secrets.

**Privilege checks**

- The runtime account can execute required business operations.
- The runtime account is denied unnecessary DDL/administrative operations.
- The migration account has properly scoped schema privileges.
- Each environment/service uses a distinct identity.

**Operational checks**

- A designated owner or process handles rotation.
- A revocation procedure exists if a secret leaks.
- Secret-read permissions and database privileges are audited regularly.
- Audit logs trace issuance, usage, and revocation of credentials.

## 13. Deployment Checklist

- Never hard-code or commit database passwords.
- Use placeholders and secret injection from environment variables, a secret manager, or config trees.
- Never embed credentials in JDBC URLs, logs, Dockerfiles, or images.
- Restrict which users and processes can read secrets.
- Use a dedicated runtime account, never a DBA or schema owner.
- Grant only the SQL privileges each use case actually requires.
- Use a separate migration identity for Flyway/Liquibase or DDL workflows.
- Configure TLS and network allowlists where appropriate.
- Have a rotation process that accounts for HikariCP and active connections.
- Test both permitted operations and operations that must be denied.
- Immediately revoke compromised credentials and investigate related logs.

Managing secrets and database privileges is part of Spring Data JPA deployment design. A secret manager protects how credentials are delivered and rotated; least privilege limits what the application can do if credentials leak. Combining both practices with separate identities for runtime and migrations reduces risk while keeping development and deployment workflows clear.