# Splitting Configuration by Profile and Keeping Connection Secrets Out of Source Code

A **Spring Data Relational JDBC** application reads and writes data through a `DataSource`, a connection pool, and a JDBC driver. Whether running on a developer workstation, in CI, or in production, the application typically needs different databases, access privileges, and operational parameters. Hardcoding URLs, usernames, and passwords directly in Java code or a YAML file committed to Git risks leaking credentials and accidentally connecting to the wrong environment.

Spring Boot provides **profiles** to select environment-specific configuration and **externalized configuration** to inject values from outside the application. These two mechanisms complement each other: profiles choose the `dev`, `test`, or `prod` configuration set, while a secret manager, environment variables, or mounted secret files supply real passwords at runtime.

## 1. What Needs to Be Separated?

A typical `DataSource` receives a JDBC connection URL, username, password, and settings such as connection pool size:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/learning
    username: app_user
    password: ${DB_PASSWORD}
```

Here `${DB_PASSWORD}` is a **placeholder**, not a password. Spring Boot looks up the `DB_PASSWORD` property from its configuration sources at startup.

| Data Category | Examples | Where to Manage |
| --- | --- | --- |
| Shared, non-sensitive config | Application name, default connection timeout | `application.yml` in Git |
| Environment-specific config | Dev/staging/prod JDBC URLs, pool size | Profile-specific files or external configuration |
| Secrets | Database passwords, tokens, private keys | Secret manager, securely injected env vars, secret files outside repo |
| Identities and privileges | Service accounts, schema permissions | Database and access-control systems |

URLs and usernames are not always secrets, yet they can still reveal network topology or internal identifiers. For production, keep them externalized alongside secrets.

Key distinction to remember: **profiles do not protect passwords**, and **supplying passwords securely does not by itself prevent connecting to the wrong database**. Both must be designed intentionally.

## 2. How Spring Profiles Work

A Spring Profile is a logical name—such as `dev`, `test`, or `prod`—activated when the application starts. Spring Boot follows this convention:

```text
src/main/resources/
├── application.yml           # Shared across all environments
├── application-dev.yml       # Overrides applied only for dev
└── application-prod.yml      # Overrides applied only for prod

src/test/resources/
└── application-test.yml      # Configuration on the test classpath
```

With the `dev` profile active, values in `application-dev.yml` override matching property names from `application.yml`, unless a higher-precedence configuration source overrides them. The same applies to `prod`. Environment variables and external configuration sources can override file-based properties according to Spring Boot's precedence rules. Never assume `application-prod.yml` always holds the highest precedence.

Example:

```yaml
# application.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
```

```yaml
# application-dev.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 4
```

When running with the `dev` profile and no higher override, the pool limit is `4`; profiles that do not override it inherit `10`. There is no need to duplicate the entire shared configuration in every file.

### 2.1. Activating a Profile

The most common approach in deployment platforms is passing an environment variable:

```text
SPRING_PROFILES_ACTIVE=prod
```

Example startup in Bash:

```bash
SPRING_PROFILES_ACTIVE=dev ./gradlew bootRun
```

Example in Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\gradlew.bat bootRun
```

These commands only illustrate profile selection; to connect to a database, the application still needs the appropriate driver, database, and credentials. In your IDE, you can set `SPRING_PROFILES_ACTIVE` per run configuration. You can also pass `--spring.profiles.active=dev` on the command line; **never pass passwords as command-line arguments**, as they can leak in process lists, logs, or shell history.

If no profile is activated, Spring uses the default `default` profile. Production should explicitly specify its active profile rather than relying on a default that might point to the wrong database.

### 2.2. Multi-Document YAML Alternative

Instead of multiple files, you can use `spring.config.activate.on-profile` and separate YAML documents with `---`:

```yaml
spring:
  sql:
    init:
      mode: never

---
spring:
  config:
    activate:
      on-profile: dev
  datasource:
    url: jdbc:postgresql://localhost:5432/learning_dev

---
spring:
  config:
    activate:
      on-profile: prod
  datasource:
    url: ${DB_JDBC_URL}
```

Choose whichever layout stays clearest and avoid repeating the same property across multiple places. Do not put `spring.profiles.active` inside a document guarded by `spring.config.activate.on-profile` or a profile-specific file to try activating another profile; select profiles via profile-independent config, environment variables, or launch options.

## 3. Spring Data JDBC Configuration Example for Dev, Test, and Prod

Suppose the Spring Boot application uses Gradle with appropriate dependency version management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

The Data JDBC starter provides repository and Spring JDBC infrastructure; the application still needs the **JDBC driver** matching its database. In this example, dev/prod use PostgreSQL while test uses H2 in-memory. Without a BOM or dependency management, compatible dependency versions must be declared explicitly.

### 3.1. Shared File: `application.yml`

```yaml
spring:
  application:
    name: spring-data-jdbc-learning
  datasource:
    hikari:
      connection-timeout: 30000
  sql:
    init:
      mode: never
```

`connection-timeout` is the maximum wait time to borrow a connection from the pool, in milliseconds; it is not an SQL query timeout. `spring.sql.init.mode: never` disables automatic execution of `schema.sql`/`data.sql` by Spring Boot's SQL initializer. If using Flyway or Liquibase, configure the corresponding dependency and migration workflow. Spring Data JDBC **does not create table schemas by default merely because entities/repositories exist**.

### 3.2. Dev File: `application-dev.yml`

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL:jdbc:postgresql://localhost:5432/learning_dev}
    username: ${DB_USERNAME:learning_dev}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 5
```

The syntax `${DB_JDBC_URL:default_value}` allows a local URL fallback when no external property is supplied. Similarly, `DB_USERNAME` has a dev-only fallback. The password `${DB_PASSWORD}` **has no fallback**; if a required value is missing when Spring resolves it, configuration fails fast instead of trying a weak sample password. `learning_dev` is an illustrative local database account and must never have privileges in production.

Each developer can inject secrets from their own local environment without editing committed files.

### 3.3. Test File: `application-test.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:jdbc_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    hikari:
      maximum-pool-size: 3
```

In-memory H2 is convenient for simple tests. `sa` is a standard default username in in-memory H2 examples, not a real deployment credential. To enable this configuration in a test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class CustomerRepositoryTest {
    @Test
    void contextLoads() {
        // Add schema, fixtures, and assertions for actual tests.
    }
}
```

If the test queries repositories, set up the schema via migrations, `@Sql`, or an appropriate fixture mechanism; configuring a JDBC URL alone does not create tables. H2 does not fully emulate PostgreSQL's dialect, data types, locking, or transaction behavior. For integration tests depending on real database behavior, use an isolated PostgreSQL instance (for example via Testcontainers), never production.

### 3.4. Prod File: `application-prod.yml`

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX_SIZE:20}
      connection-timeout: 30000
  sql:
    init:
      mode: never
```

Production must supply `DB_JDBC_URL`, `DB_USERNAME`, and `DB_PASSWORD` from external sources. Never add fallbacks like `${DB_PASSWORD:123456}`; if a secret is missing, the application must refuse to start rather than falling back to a shared password. `DB_POOL_MAX_SIZE` can have a default since it is a performance tuning knob, not a secret. With multiple application instances, total connection counts can exceed database limits even if each instance's pool is relatively small.

## 4. Supplying Connection Details via Environment Variables

Spring Boot maps environment variable names to property names, for example:

| Environment Variable | Spring Property |
| --- | --- |
| `SPRING_PROFILES_ACTIVE` | `spring.profiles.active` |
| `SPRING_DATASOURCE_URL` | `spring.datasource.url` |
| `SPRING_DATASOURCE_USERNAME` | `spring.datasource.username` |
| `SPRING_DATASOURCE_PASSWORD` | `spring.datasource.password` |
| `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE` | `spring.datasource.hikari.maximum-pool-size` |

Two common patterns are used:

**Approach A — placeholders in YAML:** keep `url: ${DB_JDBC_URL}`, `username: ${DB_USERNAME}`, `password: ${DB_PASSWORD}`; the runtime environment supplies the corresponding `DB_*` variables.

**Approach B — direct binding:** omit URL/username/password from YAML; the runtime environment supplies `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, and `SPRING_DATASOURCE_PASSWORD` so Spring Boot binds them directly onto `DataSource`.

Both approaches are valid. If mixing multiple sources simultaneously, understand Spring Boot's property precedence order so the final resolved value does not surprise you.

### Why Do Environment Variables Still Need Protection?

Environment variables keep secrets out of Git, yet secrets still live inside the process context. Actors with sufficient access can read configuration dumps, process metadata, memory dumps, or debug logs if exposed by the system.

- Inject variables using the managed secret mechanism of your CI/CD platform, container orchestrator, or secret manager.
- Never print passwords with `echo`/`printenv`, and never dump the entire environment into logs.
- Never embed passwords in command lines, terminal history, Dockerfiles, commits, screenshots, or tickets.
- Restrict access to jobs, containers, logs, secrets, and management endpoints.
- Do not rely solely on password masking in one log viewer to assume every copy of your configuration is safe.

## 5. Secret Files and `configtree:` in Spring Boot

If your deployment platform mounts secrets as files, Spring Boot can load them via a **configuration tree**. For example, at container runtime you have:

```text
/run/secrets/
└── db_password       # File holding the real password; never in the repo
```

In `application-prod.yml`:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${db_password}
```

Spring Boot maps the filename `db_password` to a property named `db_password` with the file contents as its value; `${db_password}` injects that value into `spring.datasource.password`. URL and username in this example still come from environment variables.

`configtree:/run/secrets/` omits the `optional:` prefix, so the application fails to start if the required directory is absent. An unresolved placeholder should likewise fail loudly rather than silently continuing with a default password.

```text
application-prod.yml
      │
      │ password: placeholder
      ▼
Spring Environment ◀──── configtree:/run/secrets/ ◀──── Secret platform
      │                                             file db_password
      ▼
DataSource / HikariCP
      │
      ▼
PostgreSQL JDBC driver ──────────────────────────────── PostgreSQL
```

Secret files outside Git still require strict filesystem permissions, read-only mounts where appropriate, and secure backup handling. Never bake these files into Docker image layers or store them in publicly accessible locations.

In Kubernetes, a `Secret` can be mounted as files or environment variables. Base64-encoded values inside a Secret manifest **are not secure encryption**; you still need RBAC controls, restricted etcd access, encryption at rest, and tight workload permissions. Never commit manifests containing real passwords.

### Configuration Files Outside the Repository

Spring Boot also supports additional configuration locations, such as:

```text
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/relational-jdbc/
```

The trailing `/` indicates a directory. Matching config files inside it are loaded according to Spring Boot's config rules. A missing required location causes startup failure; only use `optional:file:/.../` if deployments are truly allowed to omit that directory. External files still contain secrets if they store passwords, so control read access, file permissions, mounts, and backups.

## 6. Managing Git and Local Configuration Files

A team-friendly repository layout:

```text
project/
├── build.gradle
├── .gitignore
├── .env.example              # Contains no real credentials
└── src/
    ├── main/resources/
    │   ├── application.yml
    │   ├── application-dev.yml
    │   └── application-prod.yml
    └── test/resources/
        └── application-test.yml
```

`.env.example` documents the configuration contract only:

```dotenv
SPRING_PROFILES_ACTIVE=dev
DB_JDBC_URL=jdbc:postgresql://localhost:5432/learning_dev
DB_USERNAME=learning_dev
DB_PASSWORD=REPLACE_WITH_PRIVATE_SECRET
```

`REPLACE_WITH_PRIVATE_SECRET` is merely an instructional placeholder, not a password to use. Real values can live in an untracked local file outside the repo or be injected directly by your IDE or secret manager.

Example `.gitignore`:

```gitignore
.env
.env.*
!.env.example
secrets/
config/private/
```

`.gitignore` only ignores **untracked files**. If a password has already been committed, removing it in a later commit does not purge it from Git history. You must **rotate/revoke the credentials**, assess exposure, inspect related logs/clones, and scrub repository history if necessary. Secret scanning in CI and code review helps catch mistakes early.

## 7. Protecting Separate Databases per Environment

`SPRING_PROFILES_ACTIVE=dev` does not stop an application from reaching production if `DB_JDBC_URL` is misconfigured and the account has production privileges. Profiles must be paired with isolated databases, accounts, and network rules:

| Profile | Database | Account | Recommended Privileges |
| --- | --- | --- | --- |
| `dev` | Independent dev DB | Dev user | No access to production |
| `test` | Recreated/disposable test DB | Test user | Privileges scoped to test migrations/fixtures |
| `staging` | Staging DB | Staging user | Isolated or scrubbed data per policy |
| `prod` | Production DB | Prod runtime user | Least privilege on required schemas/tables only |

Operational principles:

1. **Least privilege:** grant only the `SELECT`/`INSERT`/`UPDATE`/`DELETE` rights needed; when appropriate, use a separate migration account for DDL privileges.
2. **Network restrictions:** allow only authorized workloads to reach the database port; credentials should never be the sole line of defense.
3. **Transport encryption:** enable SSL/TLS and certificate verification according to security requirements; exact URL parameters vary across PostgreSQL, MySQL, and other drivers.
4. **Sensible connection pool sizing:** cap pool sizes based on total instance count and database capacity.
5. **Secret rotation:** maintain a process to issue, revoke, rotate passwords, and refresh workloads when needed.

### What Happens When Rotating a Password?

Connection pools keep already-authenticated connections open. After rotating a password, existing pooled connections may continue working while newly opened connections require the updated credentials. Updating a secret file or environment variable **does not automatically make a running `DataSource` reload the new value**. Rotation workflows must account for refreshing pools, rollout ordering, reconnection, and potential brief disruptions.

## 8. How Configuration Affects Spring Data JDBC

Suppose we have an entity and repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.repository.CrudRepository;

@Table("customers")
record Customer(@Id Long id, String email) {}

interface CustomerRepository extends CrudRepository<Customer, Long> {}
```

Application call:

```java
Customer saved = repository.save(new Customer(null, "an@example.test"));
Optional<Customer> found = repository.findById(saved.id());
```

The Java code is identical in dev and prod. What differs is the configuration loaded at runtime:

```text
1. Launcher/CI/container supplies SPRING_PROFILES_ACTIVE.
2. Spring Boot loads application.yml and profile-specific files/documents.
3. Environment variables or secret files supply missing values.
4. Spring resolves placeholders and configures DataSource.
5. HikariCP uses the JDBC driver to establish connections.
6. Spring Data JDBC repositories execute SQL over JDBC infrastructure.
7. Transaction manager/pool manages connections within execution boundaries.
```

For `@Transactional` services, let Spring manage transactions and connections through repositories, `JdbcTemplate`, or the configured `DataSource`. Calling `DriverManager.getConnection(...)` manually with hardcoded URLs/passwords inside business logic creates connections that do not automatically participate in Spring-managed transactions.

## 9. Common Deployment Issues

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Connected to the wrong environment | Wrong profile or JDBC URL overridden by pipeline | Verify active profile and non-sensitive DB identifier |
| `Could not resolve placeholder 'DB_PASSWORD'` | Missing env var or secret mount | Check that the secret is provided, **without printing its value** |
| `Failed to configure a DataSource` | Missing driver or invalid JDBC URL | Verify runtime dependencies, URL, and active profile |
| `password authentication failed` / `Access denied` | Wrong credentials/permissions or mismatched rotation | Check account, database privileges, and secret source |
| `Connection refused` / timeout | Host, DNS, port, network, or database unavailable | Verify service health, network policies, and TLS |
| `Table not found` / `relation does not exist` | Missing schema/migrations, wrong DB, or wrong schema | Check migrations and target database |
| Pool exhaustion | Connection leaks, long transactions, overload | Monitor active/idle/pending connections, query durations, and transactions |
| Auth fails after rotation | Pool/workload still holds stale credentials | Check secret lifecycle and pool restart/refresh |

You may log the active profile name and a sanitized database identifier. Never log passwords, tokens, URLs with embedded credentials, or the entire `Environment`. Actuator endpoints like `env` and `configprops` must still have restricted exposure and access controls, even though Spring masks sensitive values.

## 10. Practice Exercises

**Exercise 1 — Separate two environments.** Create `application-dev.yml` targeting local PostgreSQL and `application-test.yml` using H2. Switch profiles via environment variables and `@ActiveProfiles("test")`, verifying the repository connects to the expected database.

**Exercise 2 — Remove hardcoded passwords from source code.** Replace any hardcoded password in dev YAML with `${DB_PASSWORD}`. Supply the password via a run configuration or environment secret mechanism. Confirm the application fails fast when the required secret is absent.

**Exercise 3 — Test a mounted secret.** In an isolated environment, create `/run/secrets/db_password` outside the repo, load it with `configtree:`, and map `${db_password}` into `spring.datasource.password`. Verify file permissions and behavior when the mount is missing.

**Exercise 4 — Enforce real database privileges.** Create a dedicated test database/user with access limited to a specific schema, attempt an operation against another schema, and observe the database rejecting it. This clarifies the boundary between profile configuration and database security enforcement.

Keep this mental model throughout development: **select an explicit profile → load environment config → inject secrets from a protected source → initialize `DataSource` and driver → run repositories/transactions against the right database with least privilege**. That allows a single Spring Data JDBC codebase to run across dev, CI, and production without ever editing source code to swap credentials.
