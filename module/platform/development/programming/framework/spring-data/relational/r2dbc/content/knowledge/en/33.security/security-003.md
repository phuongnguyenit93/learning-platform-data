# Managing Credentials with Configuration and Secret Stores

Spring Data R2DBC applications need credentials to connect to a database, typically including a URL, username, password, and sometimes TLS certificates or driver-specific authentication options. These are deployment configuration details and should not be hardcoded in source code, committed configuration files, or container images.

The safe organization is to **externalize credentials**: the application receives configuration from the deployment environment or a secret manager, and Spring Boot uses those values to create the `ConnectionFactory`. Each environment can use its own database and account without changing source code.

Secret management is more than hiding passwords. You must control who can read secrets, the privileges of the database account, how secrets are passed into the process, how credentials are rotated, the lifecycle of the connection pool, and how to prevent secrets from appearing in logs, traces, exceptions, or build artifacts.

## 1. What Information Needs to Be Protected?

An R2DBC application typically requires:

| Configuration | Example | Sensitivity level |
|---|---|---|
| spring.r2dbc.url | r2dbc:postgresql://db.internal:5432/orders | Can be sensitive if the URL contains user info or a token |
| spring.r2dbc.username | orders_app | Account identification information |
| spring.r2dbc.password | Secret value | Secret |
| TLS client private key | Private key contents | Highly sensitive secret |
| TLS client certificate | Client certificate | Needs integrity protection |
| Trust store password | Trust store password | Secret |
| Driver-specific token | Authentication token | Secret |

Many drivers allow embedding username/password directly in the URL. That is convenient, but increases the risk of secrets appearing in logs, exceptions, metric labels, or management screens. With Spring Boot, separate URL, username, and password into distinct properties whenever the driver and configuration allow.

Example URL without credentials:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/orders
~~~

Username/password values can be supplied directly via the environment variables `SPRING_R2DBC_USERNAME` and `SPRING_R2DBC_PASSWORD`. Never write real values into committed files.

## 2. Externalized Configuration in Spring Boot

Spring Boot has an externalized configuration mechanism: the same application can read properties from YAML/properties files, environment variables, system properties, command-line arguments, config trees, and integrated property sources.

This allows configuration to be bound in one place:

~~~java
@ConfigurationProperties(prefix = "spring.r2dbc")
public record R2dbcConnectionSettings(
    String url,
    String username,
    String password
) {}
~~~

Or let Spring Boot auto-configure `ConnectionFactory` from the `spring.r2dbc.*` namespace.

There is no need to read secret files manually in individual repositories. Let Spring bind the configuration and let `ConnectionFactory`/the driver receive the appropriate values.

### 2.1. Using environment variables

Spring Boot maps lowercase dot-separated properties to uppercase environment variables using underscores as separators:

| Property | Environment variable |
|---|---|
| spring.r2dbc.url | SPRING_R2DBC_URL |
| spring.r2dbc.username | SPRING_R2DBC_USERNAME |
| spring.r2dbc.password | SPRING_R2DBC_PASSWORD |
| spring.r2dbc.pool.max-size | SPRING_R2DBC_POOL_MAXSIZE |

The platform can supply these environment variables directly. Spring Boot binds them to the corresponding properties without storing credentials in `application.yml`.

Environment variables are convenient for containers and CI, though they are not a dedicated secret manager. On some operating systems, process inspection, diagnostic dumps, or privileged operational tools can read a process's environment. For higher security requirements, consider mounting secrets as files or using a secret manager integration.

### 2.2. Using placeholders and required values

You can reference environment variables in `application.yml` with Spring placeholders, but ensure you never provide a weak default password. If an environment variable is missing, the application should fail fast instead of silently connecting with a default credential.

Production datasource username/password are typically required configuration. Use optional placeholders only when an explicitly designed fallback source exists.

Never put secret values in example configurations inside the repository. When documenting, list only variable names such as `SPRING_R2DBC_PASSWORD`.

## 3. Reading Secrets from Files with Config Trees

Some platforms mount secrets as individual files. Spring Boot supports config trees to read each filename as a property key and the file contents as its value.

Example secrets directory:

~~~text
/run/secrets/
    spring.r2dbc.url
    spring.r2dbc.username
    spring.r2dbc.password
~~~

In `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

If the files exist, Spring can read their contents into the corresponding properties. The file `spring.r2dbc.password` becomes the property `spring.r2dbc.password`.

When secrets are required, consider omitting `optional` so the application fails if the directory or file does not exist. Use `optional` only when an explicitly designed fallback configuration source is present.

Config trees work well with Docker secrets, Kubernetes Secret volumes, or secret agents that write files. File permissions must be restricted to the user running the application.

### 3.1. Secret files

Each file holds one value, usually without a YAML wrapper. Pay attention to trailing newlines, encoding, and file permissions.

Never write secrets to temporary files with broad read permissions. Never copy secrets into build directories, static directories, or published artifacts.

### 3.2. Choosing environment variables or files?

| Delivery method | Best suited when | Key considerations |
|---|---|---|
| Environment variable | CI, container runtimes, platforms with secret injection | Can be exposed via process diagnostics or dumps |
| Config tree / mounted file | Docker/Kubernetes secret volumes, file-writing secret agents | Requires controlling file permissions and file updates |
| Secret manager integration | Auditing, versioning, policies, and rotation are needed | Requires managing identity and access permissions |
| Committed YAML file | Non-sensitive configuration | Never use to store real passwords |

These approaches can be combined. For example, `application.yml` holds the non-sensitive URL, a config tree provides username/password, and TLS certificates are mounted in a dedicated directory.

## 4. Separating Configuration by Environment

Local development, integration tests, staging, and production usually use different databases, usernames, and passwords.

A sensible layout:

~~~text
src/main/resources/
    application.yml

src/test/resources/
    application-test.yml
~~~

`application.yml` contains non-secret defaults or property names to bind. `application-test.yml` can contain test-specific pool sizes or logging. Test credentials are supplied by Testcontainers or isolated test secrets.

The production platform supplies its own secrets via environment variables, mounted files, or a secret manager. Never create a production profile with passwords committed in `application-prod.yml`.

### 4.1. Profiles are not secret stores

Profiles select configuration groups by environment. Profiles do not encrypt or protect file contents. An `application-prod.yml` containing a plaintext password is still a secret stored in source control even if it is only activated in production.

Use profiles to select behavior and non-sensitive configuration; fetch credentials from secure external sources.

### 4.2. Do not reuse the same credentials across environments

Using the same database account across local, test, staging, and production increases the blast radius if one environment is compromised.

Separate accounts for local developers, integration tests, staging, production runtime, and migration/schema administration. Runtime accounts normally do not need privileges to create databases, create roles, or alter schemas.

## 5. Using a Secret Manager

A secret manager stores and distributes credentials with features such as access policies, auditing, versioning, rotation, and leases. Common options include:

- HashiCorp Vault.
- AWS Secrets Manager or AWS Systems Manager Parameter Store.
- Azure Key Vault.
- Google Cloud Secret Manager.
- Platform-provided internal secret stores.

Applications should authenticate to the secret manager using workload identity, a service account, or the platform's short-lived identity mechanism. Avoid embedding master tokens or long-lived cloud access keys inside images.

### 5.1. Spring Cloud Vault

Spring Cloud Vault can integrate Vault with the Spring Environment so secrets are exposed as property sources. A common import configuration in Spring Boot/Spring Cloud versions supporting Config Data is:

~~~yaml
spring:
  config:
    import: vault://
~~~

Vault connection settings, authentication methods, secret backends, and paths depend on the Spring Cloud Vault version and how Vault is organized in your system. Consult the documentation for the exact dependency version in use.

If a KV backend provides properties named `spring.r2dbc.username` and `spring.r2dbc.password`, Spring Boot can bind them like any other property source. However, do not assume every Vault path automatically maps to this namespace; configure the appropriate mapping/paths.

### 5.2. Static secrets and dynamic database credentials

A secret manager can store static username/password pairs or issue dynamic database credentials with leases/expirations.

**Static secrets:**

- A long-lived database account exists.
- The secret manager stores the current version.
- On rotation, the password is changed according to a deployment process.

**Dynamic credentials:**

- The secret backend creates a new username/password with defined privileges and lifetime.
- Credentials carry a lease and can expire or be revoked.
- The application must manage renew/reissue and the lifecycle of active connections.

Dynamic credentials shorten the lifetime of an exposed secret, but require careful lifecycle integration. Fetching credentials once at startup and letting a connection pool live indefinitely can leave the application using expired credentials when opening new connections.

### 5.3. Identity instead of master secrets

On cloud platforms or Kubernetes, prefer workload identity/service accounts so the application retrieves secrets with scoped permissions. This avoids distributing long-lived access keys just to read a database password.

Secret manager policies should restrict which paths/secrets can be read, which environments and services have access, allowed actions, authentication lifetimes, and auditing. Do not grant read access to the entire secret store to an application that only needs one database password.

## 6. Kubernetes Secrets and Spring R2DBC

A Kubernetes Secret can be exposed to a Pod as environment variables or as a mounted volume.

Example Deployment/Pod using a secret volume:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-service
spec:
  containers:
    - name: app
      image: example/orders-service:1.0
      volumeMounts:
        - name: db-credentials
          mountPath: /run/secrets
          readOnly: true
  volumes:
    - name: db-credentials
      secret:
        secretName: orders-db-credentials
~~~

If the Secret contains the keys `spring.r2dbc.username` and `spring.r2dbc.password`, the volume creates corresponding files under `/run/secrets`. Spring Boot imports the config tree:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Illustrative Secret manifest:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-db-credentials
type: Opaque
stringData:
  spring.r2dbc.username: orders_app
  spring.r2dbc.password: REPLACE_AT_DEPLOYMENT
~~~

`REPLACE_AT_DEPLOYMENT` is only an illustrative placeholder, not a password to use. Never commit real production secrets into Git manifests. You can use External Secrets Operator, Secrets Store CSI Driver, or your platform's secret manager integration to sync secrets into Pods.

### 6.1. Kubernetes Secrets are not automatically a full secret manager

A Kubernetes Secret is an object for storing sensitive data inside the cluster. Protection depends on etcd encryption at rest, RBAC, node permissions, Pod permissions, auditing, and how secrets are mounted.

Base64 in a manifest is not encryption. Never treat a Base64-encoded string as a protected password.

Restrict service accounts to reading only required resources; avoid granting list/watch across all Secrets in a namespace when a workload only mounts one specific secret.

### 6.2. Updating a mounted Secret does not mean the application updated its credentials

Kubernetes can update mounted secret volume contents via projection, but the application must re-read the files and reconfigure resources using those values. Spring Boot does not automatically recreate `ConnectionFactory` simply because a config tree file changed.

If secrets are injected as environment variables, values inside a running process do not update automatically when the Kubernetes Secret changes. A Pod restart/rollout or an explicitly supported reload mechanism is typically required.

## 7. CI/CD and Secret Injection

Build/test/deploy pipelines often need credentials to access registries, test databases, or secret managers. Distinguish pipeline secrets from application runtime secrets.

Guidelines:

- Pull secrets from the CI secret store or via workload identity.
- Provide secrets only to jobs that need them.
- Never print secrets to stdout/stderr.
- Disable shell tracing when commands might echo secret values.
- Avoid passing secrets via command-line arguments where possible, since process lists or logs may expose them.
- Never store secrets in build artifacts, build caches, or test reports.
- Never use production credentials for integration tests.
- Use least privilege and short lifetimes.

### 7.1. Build time vs. runtime

Database credentials are normally runtime configuration. Do not bake them into Docker build `ARG` or `ENV` instructions in a `Dockerfile`. An image should be deployable across environments without rebuilding and without containing passwords.

Example `Dockerfile` without credentials:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/orders-service.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

When running the container, the platform supplies properties via secret environment variables or mounted files. The same image can run in staging and production with different secrets.

### 7.2. Secrets in pipeline logs

Never run debug commands that dump the entire environment when pipelines hold secrets. Some CI platforms mask registered values, but masking is not an absolute guarantee, especially if a secret is encoded, sliced, or transformed.

Never include URLs with embedded passwords in error messages or test output. When diagnostics are needed, log the host, port, database name, and connection state with credentials stripped.

## 8. Least Privilege for Database Accounts

Storing a password safely is not enough if the account has overly broad privileges.

A service's runtime account should have only the permissions it needs: `CONNECT` on the database, `SELECT`/`INSERT`/`UPDATE`/`DELETE` on tables the service owns, required sequence/identity privileges, and `EXECUTE` on stored procedures the application actually calls.

Typically, a runtime account should not have `CREATE DATABASE`, `CREATE ROLE`, `SUPERUSER`, access to other services' tables, or privileges to alter production schemas when migrations use a separate account.

### 8.1. Separating runtime and migration accounts

Migrations may need `CREATE`/`ALTER`/`DROP`, while runtime application code only needs DML. Use separate accounts:

| Account | Purpose | Typical privileges |
|---|---|---|
| orders_app | R2DBC runtime | Required SELECT/INSERT/UPDATE/DELETE |
| orders_migrator | Flyway/Liquibase | DDL and migration privileges |
| orders_readonly | Reporting if needed | Restricted SELECT |

Do not run migrations with the runtime account just for convenience. If the application is compromised, broad DDL rights enlarge the impact.

### 8.2. Separating by service and database

If multiple services share a database server, do not share one database user with read/write access across all schemas unless required. Separate users/schemas/roles per service to limit the blast radius.

Separate credentials also help auditing identify which service performed an action and allow revoking one workload's access without disrupting the entire application.

## 9. TLS and Protecting Data in Transit

Credentials must be protected while traveling over the network. When R2DBC connects to a database across an untrusted network, configure TLS according to the driver and database.

- Require TLS when the database supports it and the environment requires transport protection.
- Verify the certificate chain and hostname; never disable verification just to clear connection errors.
- Protect private keys and trust store passwords as secrets.
- Use certificates with defined validity periods and renewal processes.
- Avoid trust-all or insecure modes in production.
- Check TLS options for the exact R2DBC driver and version.

SSL mode syntax is not uniform across PostgreSQL, MySQL, SQL Server, and various R2DBC drivers. Do not copy SSL query parameters from one driver to another. Configure driver-specific properties or `ConnectionFactoryOptions` per the documentation of the driver in use.

## 10. Credential Rotation

Credential rotation replaces passwords, usernames, or tokens on a schedule or when compromise is suspected. Rotation limits how long a leaked secret remains usable, while needing to avoid dropping active application connections.

A rotation lifecycle may include:

1. Creating a new credential or updating the password per database policy.
2. Publishing the new secret to the secret manager.
3. Updating runtime workload configuration.
4. Opening new connections with the new credential.
5. Verifying the application works with the new credential.
6. Draining/closing old connections on a planned schedule.
7. Revoking the old credential once no workload uses it.

### 10.1. Why updating the secret alone is not enough

`R2dbcTransactionManager` and `ConnectionFactory` use configuration established when beans are initialized. With a connection pool, existing connections already authenticated with the old credential. Changing a property source does not automatically:

- Rebind all already-created beans.
- Recreate the `ConnectionFactory`.
- Close open connections.
- Update passwords for already-authenticated connections.
- Guarantee new connections use the new secret.

Therefore, rotation must include a pool reload/recreation mechanism or an application instance rollout. Implementation details depend on how `ConnectionFactory`, the pool, and the secret provider are configured.

### 10.2. Zero-downtime rotation

A common pattern with databases supporting multiple users/credentials is creating a new account first:

1. Create `orders_app_v2` with the same least-privilege grants.
2. Store the new username/password in the secret store.
3. Start new instances or refresh the pool to use the new credential.
4. Verify connectivity and real requests.
5. Shift traffic completely to the new instances.
6. Revoke `orders_app_v1` once old connections have drained.

This avoids changing the password of a single user actively shared across all running instances simultaneously. If the database or policy does not allow two parallel users, plan a rotation maintenance window with clear rollback steps.

### 10.3. Dynamic credentials with leases

When a secret manager issues short-lived database credentials, the application must manage lease duration, renewal timing, failure handling on renewal, timing for opening new connections, validity of existing connections after revocation, and how pools are closed/recreated when credentials change.

Do not wait until a lease expires to fetch a new credential. Renew/reissue ahead of expiry with an adequate buffer. If the old credential is revoked while the pool still holds connections, in-flight queries may fail depending on the database.

## 11. Connection Pools and Secret Lifecycle

Connection pools reduce connection setup cost by reusing connections. That also means credentials used when a connection was opened can outlive the initial secret read.

When a secret changes:

- Open connections may keep working until closed or until the server revokes the session.
- New connections must use the current credential.
- The pool may continue holding old connections.
- The `ApplicationContext` may still hold the old `ConnectionFactory`.
- A new property source alone does not guarantee the pool has updated.

A rotation strategy should coordinate the secret provider with pool lifecycle. You can roll out new Pods to create fresh `ConnectionFactory`/pools and drain old Pods, or use a pool abstraction with controlled refresh if implemented in the project.

Never create a new `ConnectionFactory` per request. Pool recreation must be coordinated, bounded, and ensure old connections close after in-flight work finishes.

### 11.1. Graceful shutdown

When rolling out new instances:

1. Stop accepting new requests on the old instance.
2. Wait for in-flight requests/transactions to finish within a bounded timeout.
3. Close the old pool/`ConnectionFactory`.
4. Confirm the new instance uses the new credentials.
5. Revoke the old secret only after no connections depend on it.

Graceful shutdown avoids cutting off transactions mid-flight or failing active requests unnecessarily.

## 12. Multiple R2DBC Datasources and Separate Secrets

An application may use multiple `ConnectionFactory` beans. Each datasource needs its own credentials and secret paths. For example, custom configuration for Orders can bind `app.datasource.orders.url`, `app.datasource.orders.username`, and `app.datasource.orders.password`, while Billing uses the corresponding `app.datasource.billing.*` namespace.

| Property | Environment variable |
|---|---|
| app.datasource.orders.url | APP_DATASOURCE_ORDERS_URL |
| app.datasource.orders.username | APP_DATASOURCE_ORDERS_USERNAME |
| app.datasource.orders.password | APP_DATASOURCE_ORDERS_PASSWORD |
| app.datasource.billing.url | APP_DATASOURCE_BILLING_URL |
| app.datasource.billing.username | APP_DATASOURCE_BILLING_USERNAME |
| app.datasource.billing.password | APP_DATASOURCE_BILLING_PASSWORD |

Spring Boot can bind these environment variables to the corresponding properties via relaxed binding. The names in the table are variable names, not literal values to assign in YAML.

Example typed configuration:

~~~java
@ConfigurationProperties(prefix = "app.datasource.orders")
public record OrdersDatabaseProperties(
    String url,
    String username,
    String password
) {}
~~~

~~~java
@ConfigurationProperties(prefix = "app.datasource.billing")
public record BillingDatabaseProperties(
    String url,
    String username,
    String password
) {}
~~~

These properties are custom application configuration; Spring Boot does not automatically use `app.datasource.*` to create R2DBC factories without custom configuration. When creating beans, attach the right credentials, `ConnectionFactory`, template/repositories, and transaction manager.

Separating secrets ensures rotating or revoking one datasource does not directly impact another datasource's account.

## 13. Avoiding Credential Leaks in Logs and Diagnostics

Secrets can leak outside source code via:

- Logging connection URLs with embedded username/password.
- Printing the entire `Environment` or `System.getenv()`.
- Logging exceptions containing connection strings.
- Logging requests/responses containing tokens.
- Putting secrets into metric labels or tracing baggage.
- Leaving test failure dumps containing config objects.
- Committing `.env`, `application-local.yml`, or IDE run configurations.
- Putting secrets into Docker build `ARG`s, image layers, or build caches.
- Sharing heap dumps or support bundles containing runtime configuration.

### 13.1. Safe logging

If connection info must be logged, log only controlled non-sensitive fields such as database host, port, database name, and datasource alias. Never log passwords, tokens, private keys, or URLs containing credentials.

Never log an entire object holding username/password via `toString()` if a record or generated `toString` can expose the secret.

### 13.2. Exceptions and Actuator

Some diagnostic endpoints can expose configuration properties or environment values. Restrict Actuator access, never expose `env`/`configprops` endpoints publicly, and enable sanitization for sensitive properties.

Do not enable debug logging on drivers or connection factories in production without understanding what data will be written. If temporary debugging is required, limit duration, scope, and log access.

### 13.3. Files and repositories

Adding patterns to `.gitignore` only helps prevent accidental addition of local files; it does not remove previously committed secrets and does not protect files generated inside build artifacts.

If a secret was committed, treat it as compromised: rotate/revoke the credential first, then clean Git history and copies according to organizational policy. Deleting the line in a new commit does not make the old credential safe.

## 14. Local Development and Integration Tests

Developers need to run the application locally without using production secrets. Options include a local PostgreSQL container with throwaway user/password, a local config file outside Git, environment variables supplied by the IDE or shell, a developer-scoped secret store, or Testcontainers spinning up an isolated database for integration tests.

Never commit real values into `application-local.yml`. If a local file holds secrets, keep it out of version control and restrict filesystem permissions on the machine.

With Testcontainers, you can use `@DynamicPropertySource` to register the container's URL/credentials in the test context. These are temporary test credentials unrelated to production secrets.

### 14.1. Use least-privilege test accounts

Integration tests may run migrations, truncates, or schema resets. Use an isolated test database with privileges restricted to that database/schema. Never reuse production usernames/passwords just to make tests pass.

## 15. When Secrets Are Inaccessible

The application needs a clear policy when the secret manager or secret file is unavailable.

For credentials required to connect to the database, failing fast on startup is usually best if secrets cannot be retrieved. Starting an application in a half-working state causes continuous request errors and makes misconfiguration harder to detect.

During runtime secret rotation, you may keep the current credential briefly while its lease remains valid and retry fetching the new secret with backoff. Never continue indefinitely with an expired or revoked credential.

Never log secret values when reporting failures. Log only a sanitized secret name/path, datasource alias, failure timestamp, and a safe provider error code.

## 16. Testing and Operating Rotation

Secret management should be tested as part of the application lifecycle.

Test and operational scenarios may include:

- Missing required username/password causes a clear startup failure.
- Test environments use isolated credentials and never pick up production secrets accidentally.
- `ConnectionFactory` is constructed from the intended property source.
- Secrets containing special characters are not truncated or misparsed.
- TLS verifies certificates/hostnames properly.
- The runtime user lacks unnecessary DDL/administrative privileges.
- A new secret version is provisioned and new instances connect successfully.
- Old pools drain/close after rollout.
- The old secret is revoked once no workload uses it.
- Secret manager unavailability triggers defined behavior.
- Logs, traces, and exceptions contain no passwords or tokens.
- Multiple datasources use their own distinct secrets.

Never print secrets in test assertions or reports. To prove configuration is correct, assert successful connectivity and the datasource alias rather than comparing and printing passwords.

## 17. Workflow for Designing Credentials for an R2DBC Application

1. Identify every database and `ConnectionFactory` the application uses.
2. Create a separate database user per service/datasource.
3. Grant minimal privileges for runtime operations.
4. Separate runtime accounts from migration accounts.
5. Keep URLs and non-sensitive settings in application config.
6. Supply username/password via environment, config tree, or secret manager.
7. Use workload identity to authenticate to the secret manager whenever possible.
8. Protect connections with TLS and certificate verification.
9. Define TTL/leases and a rotation schedule.
10. Design how `ConnectionFactory`/pools refresh or recreate when secrets change.
11. Drain old connections before revoking old credentials.
12. Restrict secret read permissions and enable auditing.
13. Prevent secrets from appearing in logs, traces, images, and repositories.
14. Test missing secrets, rotation, pool lifecycle, and outages.
15. Monitor authentication failures and secret lease status without logging secret values.

## 18. Common Mistakes

**Writing passwords directly in `application.yml`.** Files can be committed or packaged into images. Use externalized configuration.

**Treating Base64 as encryption.** Base64 is only encoding. Use a secret manager or properly protected secret storage.

**Using the same credentials across every environment.** One leaked secret can compromise production. Separate accounts and secrets per environment.

**Using an administrative database account for the application.** A compromised runtime service could alter schemas or data far beyond its needs. Apply least privilege.

**Embedding credentials in URLs and logging the URL.** Passwords can appear in logs and diagnostics. Separate username/password into distinct properties.

**Updating the secret store without refreshing the pool.** `ConnectionFactory` and the pool may retain old settings. Perform a rollout or controlled lifecycle refresh.

**Revoking the old password too early.** Old instances may still hold connections or not yet have the new secret. Verify rollout and drain before revoking.

**Treating environment variables as unexposed.** Process diagnostics and dumps can expose environments. Use mounted secrets/config trees or secret integrations where appropriate.

**Using production secrets in CI/tests.** Tests can wipe data or run migrations. Use isolated test databases and credentials.

**Not separating the migration user.** The runtime account gains unnecessary DDL privileges. Use a dedicated migration identity.

**Swallowing secret provider errors and using old passwords indefinitely.** You may keep trying expired or revoked credentials. Define clear lease and fallback behavior.

## 19. Design Principles

- Never hardcode credentials in source code, committed files, or Docker images.
- Use Spring Boot externalized configuration to bind R2DBC URL, username, and password.
- Prefer a secret manager or mounted config tree for sensitive credentials.
- Use environment variables when suited to the platform, while understanding process-diagnostic risks.
- Use workload identity instead of long-lived master keys whenever possible.
- Separate secrets by environment, service, and datasource.
- Separate runtime database users from migration/admin users.
- Apply least privilege and audit secret access.
- Protect database connections with TLS and certificate verification.
- Never log URLs containing credentials, passwords, tokens, or private keys.
- Never assume secret rotation automatically updates `ConnectionFactory` or connection pools.
- Coordinate rotation with pool refresh/recreation, rollouts, and graceful shutdown.
- For dynamic credentials, track leases and renew before expiry.
- Use throwaway credentials and isolated databases for tests.
- Test startup, authentication, rotation, revocation, and secret-provider outages.

## 20. Takeaways

R2DBC credentials should be supplied externally and bound through Spring Boot configuration. Environment variables, config trees, Kubernetes Secrets, and secret managers are different delivery mechanisms; the choice depends on the platform, audit requirements, rotation needs, and required protection level. Never store passwords in source, images, or logs, and never share one high-privilege account across all services.

Rotation must account for `ConnectionFactory` and connection pools: updating a secret source does not automatically switch already-created connections to new credentials. Provision the new credential, refresh/roll out the pool, verify connections, drain old connections, and only then revoke the old credential. Combining least privilege, TLS, short-lived identities, auditing, and isolated testing reduces secret exposure risk and limits the impact if a credential is compromised.
