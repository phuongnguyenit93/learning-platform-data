# Separating Development, Testing, and Production Configurations

Spring Data R2DBC applications typically run across multiple environments: a developer's local machine, automated testing environments, staging, and production. Each environment may use different database hosts, credentials, pool sizes, timeouts, logging levels, and migration policies. Mixing these values into code or using a single configuration file with hardcoded values makes deployments error-prone—risking environment mismatches, secret leaks, or inappropriate load on the database.

Spring Boot supports externalized configuration and profiles to separate configuration by environment. The goal is to keep the application logic identical while environment-dependent values are supplied from configuration files, environment variables, command-line arguments, a secret manager, or the deployment platform. You need to clearly define which configuration source has higher precedence, which profile is active, and what the application should do when required configuration is missing.

## 1. What should differ between environments?

Some values commonly vary:

| Configuration group | Development | Test | Production |
| --- | --- | --- | --- |
| Database endpoint | Local container or dev machine | Isolated test database | Managed database/cluster |
| Credentials | Dedicated dev account | Temporary test account | Securely managed secret |
| Database/schema | Sample/experimental data | Resettable database | Real data, requires protection |
| Pool size | Small, convenient for debugging | Sized for concurrent tests | Sized for capacity and connection budget |
| Timeout | May be longer when debugging | Has a deadline so tests do not hang | Aligned with SLOs and request deadlines |
| Logging | DEBUG when needed | INFO or test logs | INFO/WARN, avoid exposing data |
| Migration | May run automatically at startup | Create schema from migrations | Controlled job/stage |
| Observability | Console/local metrics | Test reports | Metrics, tracing, alerting |

Do not create a separate codebase for each environment. Profiles should only change configuration and a few beans that genuinely need to differ; business rules and entity mappings should remain consistent.

## 2. Externalized configuration in Spring Boot

Spring Boot can read configuration from multiple sources:

- `application.yml` or `application.properties` files in the application.
- Profile-specific files such as `application-dev.yml`, `application-test.yml`.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config trees or secrets mounted as files.
- External configuration sources integrated through appropriate Spring Boot mechanisms.

These sources follow a precedence order. Higher-precedence sources override values in configuration files. Therefore, a value in `application.yml` is not necessarily the final runtime value if the deployment environment passes a different environment variable or command-line argument.

Example:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: shop_dev
    password: dev_only_password
~~~

When running in production, environment variables can override these:

~~~text
SPRING_R2DBC_URL=r2dbc:postgresql://db.internal:5432/shop
SPRING_R2DBC_USERNAME=shop_app
SPRING_R2DBC_PASSWORD=<injected-secret>
~~~

Never store real passwords in source control. Example values in documentation are for local use only; real environments must retrieve credentials from a secret manager or the platform's security mechanism.

## 3. Using Spring Profiles

Profiles let you declare configuration or beans that are only active in a selected environment.

A typical file structure:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
└── application-prod.yml
~~~

`application.yml` holds common configuration; profile-specific files contain only the differences.

Activate a profile via an environment variable:

~~~text
SPRING_PROFILES_ACTIVE=dev
~~~

Or via the command line:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Do not activate the production profile by default in the artifact or code. The deployment environment is responsible for selecting the appropriate profile. For production, explicitly configure the profile and verify the effective values when the application starts.

## 4. Common configuration in application.yml

Example common configuration for an R2DBC application:

~~~yaml
spring:
  application:
    name: order-service

  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 10m
      max-life-time: 30m
      max-acquire-time: 2s

  sql:
    init:
      mode: never

server:
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

This is a skeleton example; supported properties and binding behavior depend on the versions of Spring Boot, Spring Data Relational, and R2DBC Pool. If you configure the pool via URL or a custom `ConnectionFactory` bean, ensure these properties are actually applied to the factory in use.

Do not put production endpoints, credentials, or pool sizes into the common configuration if environments need different values. Common configuration should contain safe defaults and environment-independent settings.

## 5. The development profile

The `application-dev.yml` file can use a local database:

~~~yaml
spring:
  config:
    activate:
      on-profile: dev

  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop_dev
    username: shop_dev
    password: dev_only_password
    pool:
      initial-size: 1
      max-size: 5
      max-acquire-time: 5s

  flyway:
    enabled: true
    url: jdbc:postgresql://localhost:5432/shop_dev
    user: shop_dev
    password: dev_only_password
    locations: classpath:db/migration

logging:
  level:
    root: INFO
    org.springframework.data.r2dbc: DEBUG
    io.r2dbc.postgresql.QUERY: DEBUG
~~~

Development can prioritize ease of startup and observability:

- Use a local database or dedicated container.
- Use an account without production privileges.
- Keep the pool small so limits are easy to notice and connections are not overconsumed.
- Enable SQL logging when investigating issues.
- Optionally run migrations automatically so developers always have the latest schema.

Do not enable bind parameter logging that may contain passwords, tokens, emails, or personal data. If you need to inspect SQL, configure safe logging and use only dummy data.

## 6. The test profile

Tests need an environment that can be created, cleaned, and reproduced. A simple profile configuration:

~~~yaml
spring:
  config:
    activate:
      on-profile: test

  r2dbc:
    url: r2dbc:postgresql://localhost:5433/shop_test
    username: shop_test
    password: test_only_password
    pool:
      initial-size: 1
      max-size: 4
      max-acquire-time: 3s

  flyway:
    enabled: true
    url: jdbc:postgresql://localhost:5433/shop_test
    user: shop_test
    password: test_only_password

logging:
  level:
    root: WARN
~~~

The test profile should:

- Use a dedicated database and never point to production.
- Run migrations to build the schema just like a real environment.
- Use reproducible fixture data.
- Set timeouts so hanging tests fail fast.
- Size the pool for test concurrency without making it overly large.
- Not depend on leftover data from a previous run.

For integration tests, Testcontainers is usually better suited than an embedded database on a different engine because it runs the exact database engine used in production.

## 7. The production profile

The `application-prod.yml` file should only contain defaults and non-secret configuration. Endpoints and secrets are typically injected by the platform:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod

  r2dbc:
    pool:
      enabled: true
      initial-size: 10
      max-size: 30
      max-acquire-time: 1s
      max-idle-time: 10m
      max-life-time: 30m

  flyway:
    enabled: false

server:
  shutdown: graceful

logging:
  level:
    root: INFO
    org.springframework.data.r2dbc: INFO

management:
  endpoint:
    health:
      show-details: never
~~~

These pool and timeout numbers are only examples, not production defaults. You must calculate them based on the number of application instances, database connection limits, query concurrency, transaction duration, and SLOs.

Production migrations can run in a separate deployment job before rolling out the application. If an organization chooses to run migrations on application startup, proper locking/coordination and an appropriate migration account must be in place; do not let every instance freely use a broad DDL account.

## 8. Distinguishing R2DBC URLs and JDBC URLs

Spring Data R2DBC uses an R2DBC driver to execute business queries. Flyway/Liquibase in common setups use JDBC to execute schema migrations.

Example:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/shop
    username: shop_app
    password: ${DB_APP_PASSWORD}

  flyway:
    url: jdbc:postgresql://db.internal:5432/shop
    user: shop_migrator
    password: ${DB_MIGRATION_PASSWORD}
~~~

The two URLs use different protocols and can use two different accounts:

- `r2dbc:` for repositories, `R2dbcEntityTemplate`, and `DatabaseClient`.
- `jdbc:` for JDBC migration tools.

At runtime, the corresponding driver dependency is required for each protocol if both are used in the same artifact. Using JDBC in the migration stage does not turn business queries into blocking JDBC.

## 9. Separating runtime accounts and migration accounts

Do not use the same database user with broad DDL privileges for both the application and migrations.

A permission model:

| Account | Typical privileges needed |
| --- | --- |
| Application user | SELECT/INSERT/UPDATE/DELETE on required tables |
| Migration user | CREATE/ALTER and updating migration history |
| Test user | Appropriate privileges on a resettable test database |
| Read-only user | SELECT on permitted tables/schemas if using replicas |

Separating privileges reduces the blast radius if the runtime application has a bug or is compromised. The application user should not be a database owner/superuser merely for migration convenience.

Production credentials should be managed by a secret manager, Kubernetes Secret, or equivalent mechanism; restrict who can read them and rotate them as needed. Never commit files containing real secrets.

## 10. Environment variables and placeholders

Spring Boot supports placeholders to resolve values from property sources:

~~~yaml
spring:
  r2dbc:
    url: ${DB_R2DBC_URL}
    username: ${DB_R2DBC_USERNAME}
    password: ${DB_R2DBC_PASSWORD}
~~~

You can declare defaults for local use:

~~~yaml
spring:
  r2dbc:
    url: ${DB_R2DBC_URL:r2dbc:postgresql://localhost:5432/shop_dev}
    username: ${DB_R2DBC_USERNAME:shop_dev}
    password: ${DB_R2DBC_PASSWORD:}
~~~

An empty default for a password can allow the application to start and fail to connect later. For production, require mandatory variables and fail fast if they are missing. Do not use a real password or a high-privilege account as a default value.

Environment variables typically use uppercase names with underscores, such as `SPRING_R2DBC_URL` or `DB_R2DBC_URL`. Standardize on one convention to avoid having two properties represent the same setting with confusing override sources.

## 11. Fail fast when required configuration is missing

If the production database URL or credentials are missing, the application should report a configuration error immediately at startup rather than falling back to an incorrect default endpoint.

You can use constructor binding with `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.database")
@Validated
public record DatabaseSettings(
        @NotBlank String role,
        @NotBlank String environment
) {}
~~~

Declare property enabling:

~~~java
@Configuration
@EnableConfigurationProperties(DatabaseSettings.class)
public class AppConfiguration {
}
~~~

For R2DBC connection settings, Spring Boot has its own built-in configuration. Do not create a custom class reusing the `spring.r2dbc` prefix unnecessarily. Use custom properties for values owned by your application, such as routing policy or consistency mode.

Validation detects missing or invalid properties immediately during binding. For secrets, avoid including secret values in exception messages or configuration logs.

## 12. Avoiding accidental profile dependencies

Multiple profiles can be activated at the same time:

~~~text
SPRING_PROFILES_ACTIVE=prod,metrics
~~~

Spring Boot applies configuration from activated profiles according to their order and property precedence. Feature/group profiles such as `metrics` can enable observability; environment profiles such as `prod` provide endpoints and timeouts.

Do not create too many overlapping profiles like `prod-eu`, `prod-us`, `prod-large-pool`, `prod-debug` when most only differ by a few properties. Use environment variables for deployment values and profiles for meaningful configuration groups.

Do not activate `dev` and `prod` simultaneously unless exact override rules are defined. If profiles conflict, one value can unexpectedly override another.

## 13. Profile-specific beans with @Profile

In addition to YAML, `@Profile` can restrict beans:

~~~java
@Configuration
public class DatabaseDiagnosticsConfiguration {

    @Bean
    @Profile({"dev", "test"})
    DatabaseDiagnostics databaseDiagnostics() {
        return new VerboseDatabaseDiagnostics();
    }

    @Bean
    @Profile("prod")
    DatabaseDiagnostics productionDiagnostics() {
        return new SafeDatabaseDiagnostics();
    }
}
~~~

Only use profile-specific beans when behavior or implementations truly differ. Do not create two repository implementations just because the database URL differs; let the connection factory configuration handle the endpoint.

If no profile is selected, the application needs safe default behavior. You can use the `default` profile or validation requiring a specific profile depending on your deployment approach. Avoid letting production accidentally run dev beans.

## 14. Checking active profiles

You can inspect active profiles via the Actuator `env` endpoint if it is exposed and secured, or log non-sensitive information at startup:

~~~java
@Component
public class ActiveProfileLogger implements ApplicationRunner {

    private final Environment environment;

    public ActiveProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info(
                "Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles())
        );
    }
}
~~~

Do not log the entire `Environment` or all property values; they may contain passwords, tokens, and sensitive connection strings. Only log profile names and necessary non-secret details.

## 15. Different connection pools per environment

Pool size should be chosen based on database capacity and instance count, not a single universal number:

- Development: small pool to avoid consuming connections and to simplify debugging.
- Test: pool sized for test concurrency; each test suite may need its own database/container.
- Production: pool based on throughput, connection hold time, instance count, replica topology, and database connection limits.

Example profile-based configuration:

~~~yaml
# application-dev.yml
spring:
  r2dbc:
    pool:
      initial-size: 1
      max-size: 5
      max-acquire-time: 5s
~~~

~~~yaml
# application-prod.yml
spring:
  r2dbc:
    pool:
      initial-size: 10
      max-size: 30
      max-acquire-time: 1s
~~~

Do not copy these illustrative values without measuring. Total possible connections can be estimated as:

~~~text
possible connections =
    application instances * pool max size
    + worker pools
    + migration/admin/monitoring clients
    + other services
~~~

If you have writer and reader pools, sum both. Calculate using the maximum replica count during autoscaling or rolling deployments, which can temporarily increase instance count.

## 16. Environment-specific timeouts and latency budgets

Timeouts must align with request deadlines:

- Pool acquire timeout: limits time spent waiting for a connection.
- Query/statement timeout: limits database execution time.
- HTTP client timeout: limits time spent waiting on external dependencies.
- Request timeout: overall use-case/HTTP deadline.

For example, local environments may use longer timeouts for debugging queries, while production must enforce finite deadlines to avoid holding requests and resources for too long.

Do not set a query timeout pointlessly higher than the request deadline; when a request times out and is cancelled, the SQL statement may still continue running depending on the driver/database. Coordinate timeouts across Reactor, the driver, and the database.

Tests should have timeouts short enough to detect deadlocks or non-terminating publishers, yet not so short that they cause flaky tests on slow CI runners.

## 17. Migrations in development, test, and production

Schemas should be managed with migrations such as Flyway or Liquibase. Policies can vary by environment:

| Environment | Common policy |
| --- | --- |
| Development | Auto-migrate on app startup to update the local schema |
| Test | Run migrations before integration tests or when the test context creates the database |
| Staging | Run migrations as a deployment job and verify before rollout |
| Production | Controlled job/stage with backups and process approvals |

If the application uses R2DBC while Flyway/Liquibase run over JDBC, configure a separate JDBC URL and driver. Do not confuse `spring.r2dbc.url` with `spring.flyway.url` or `spring.liquibase.url`.

Do not let every production pod freely run migrations using an application user with DDL privileges. If running migrations during startup, you must understand lock behavior, startup ordering, and account permissions.

## 18. Testcontainers instead of a production database

Integration tests should use an isolated database:

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16")
                    .withDatabaseName("shop_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://" + postgres.getHost()
                        + ":" + postgres.getMappedPort(5432)
                        + "/" + postgres.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }
}
~~~

This example illustrates configuring R2DBC properties from Testcontainers. If using Flyway, you also need to configure the corresponding JDBC URL/credentials for the same container. Image name, version, and Testcontainers dependencies should be pinned to match the production database.

Testcontainers helps verify SQL dialects, mappings, constraints, and transactions on a real engine. It does not replace unit tests and must never accidentally connect to a real database.

## 19. Configuring migrations for Testcontainers

If Flyway runs in the test context, add the JDBC driver and configure the JDBC URL:

~~~java
@DynamicPropertySource
static void configureProperties(DynamicPropertyRegistry registry) {
    String host = postgres.getHost();
    int port = postgres.getMappedPort(5432);
    String database = postgres.getDatabaseName();

    registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://" + host + ":" + port + "/" + database
    );
    registry.add("spring.r2dbc.username", postgres::getUsername);
    registry.add("spring.r2dbc.password", postgres::getPassword);

    registry.add("spring.flyway.url", () ->
            "jdbc:postgresql://" + host + ":" + port + "/" + database
    );
    registry.add("spring.flyway.user", postgres::getUsername);
    registry.add("spring.flyway.password", postgres::getPassword);
}
~~~

This is an example for Flyway. For Liquibase, use the corresponding properties. Test configuration should never reuse credentials or hosts from the production profile.

If migrations run in a separate test setup step, you can disable auto-migration in the Spring context to avoid running twice, while ensuring migrations have run before repository tests execute.

## 20. Test profiles and fixture data

Do not rely on data manually entered by developers into a local database. Tests need reproducible data:

- Create fixtures using SQL or builders in tests.
- Use deterministic IDs if tests need references.
- Clean up data or create a fresh database/container per suite.
- Never use real production data unless it has been anonymized and approved.
- Verify that test execution order does not affect other tests.

If tests run in parallel, avoid sharing a single database/schema with mutable data without isolation. You can create separate schemas/databases or namespace data per test.

## 21. Docker Compose for development

A local environment can use Docker Compose:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: shop_dev
      POSTGRES_USER: shop_dev
      POSTGRES_PASSWORD: dev_only_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U shop_dev -d shop_dev"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  postgres_data:
~~~

The password in this Compose file is for local illustration only. Never reuse it for staging or production. If local data needs resetting, you can intentionally delete the volume; that operation will wipe the local database.

Applications running on the host use `localhost`. If the application also runs inside the Compose network, the hostname is typically the service name `postgres`, not `localhost`.

## 22. Docker/Kubernetes and production configuration

In containers, configuration is commonly injected via environment variables or mounted secrets:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
  - name: SPRING_R2DBC_URL
    valueFrom:
      configMapKeyRef:
        name: order-service-config
        key: r2dbc-url
  - name: SPRING_R2DBC_USERNAME
    valueFrom:
      secretKeyRef:
        name: order-service-db
        key: username
  - name: SPRING_R2DBC_PASSWORD
    valueFrom:
      secretKeyRef:
        name: order-service-db
        key: password
~~~

This Kubernetes manifest example only illustrates referencing a ConfigMap/Secret; never put secret values directly into committed YAML. In a real system, apply RBAC, encryption at rest, secret rotation, and least-privilege read permissions.

ConfigMaps are suited for non-secret values such as internal endpoints or feature settings. Secrets are suited for passwords/tokens, but cluster security must be configured; naming an object `Secret` does not automatically make it secure if access control and encryption are not configured.

## 23. Graceful shutdown and pool lifecycle

Production requires stopping the application in a controlled manner:

- Stop accepting new requests.
- Allow in-flight requests to finish within the grace period.
- Close background publishers/consumers according to lifecycle.
- Close the connection pool after no operations remain in flight.
- Avoid interrupting database transactions mid-flight whenever possible.

Spring Boot supports graceful shutdown on the web server; configure a wait duration aligned with the orchestrator platform. Background workers and custom connection pools need explicit lifecycle beans so they are closed properly.

Never create a new pool per request or per service call. A pool is a long-lived application resource, typically managed by Spring as a bean.

## 24. Environment-specific logging

Development may need SQL logging to understand mappings and queries. Production needs enough logging for operations while avoiding sensitive data exposure.

Example:

~~~yaml
# application-dev.yml
logging:
  level:
    root: INFO
    org.springframework.data.r2dbc: DEBUG
~~~

~~~yaml
# application-prod.yml
logging:
  level:
    root: INFO
    org.springframework.data.r2dbc: INFO
~~~

Do not enable sensitive parameter logging in production. When investigating slow queries, prefer tracing, query metrics, and controlled slow query logs. Overly verbose log levels can increase I/O, log volume, and data exposure risk.

## 25. Environment-specific observability

Development:

- Health checks and console logs.
- Local metrics when investigating.
- Debug endpoints may be enabled, but only in trusted environments.

Test:

- Collect test reports, error logs, and query durations.
- Metrics may be enabled to detect pool leaks or hanging tests.
- Do not expose management endpoints to external networks.

Production:

- Properly configured health/readiness/liveness probes.
- Metrics for HTTP, JVM, R2DBC pool, and database.
- Distributed tracing with a sampling policy.
- Alerts for pool pending counts, acquire timeouts, query latency, and database errors.
- Management endpoints secured, exposing only what is necessary.

Never publicly expose `env`, `configprops`, heap dumps, or thread dumps. These endpoints can disclose configuration, secrets, or runtime data.

## 26. Readiness when the database is not yet ready

An application may start before the database is ready or lose connectivity afterward. Distinguish between:

- Liveness: is the process still alive?
- Readiness: can the instance accept traffic?
- Startup probe: has the application finished starting?

If readiness checks the database, a database outage can stop the instance from receiving traffic; this may or may not be appropriate depending on your architecture. Do not casually make liveness directly depend on the database, because a database failure could cause the orchestrator to continuously restart every instance and worsen the outage.

The R2DBC health indicator and response details should be secured. Checking connections on the health endpoint also generates database load, so set an appropriate frequency and timeout.

## 27. Profiles do not replace feature flags

Profiles are suited for environment configuration differences or startup bean selection. Feature flags are better suited when enabling/disabling features per tenant, user, or gradual rollout within the same environment.

Do not create a new profile for every feature rollout. For instance, `prod-new-checkout` and `prod-old-checkout` complicate configuration; a feature flag manages feature state much more cleanly.

If a feature flag affects the schema, you must still ensure the schema is compatible with both the enabled and disabled code paths during the rollout window.

## 28. Do not use profiles to hide dangerous configuration

Avoid having:

~~~yaml
spring:
  r2dbc:
    url: ${SPRING_R2DBC_URL:r2dbc:postgresql://production-db:5432/shop}
    username: ${SPRING_R2DBC_USERNAME:admin}
    password: ${SPRING_R2DBC_PASSWORD:admin}
~~~

If environment variables are missing, the application could silently connect to production using default credentials. This is a dangerous configuration.

Instead, production should require mandatory variables with no sensitive defaults; local environments can provide defaults in a separate dev profile. Always verify the active profile and connection endpoint are not production before running tests or destructive scripts.

## 29. Testing profile configuration

You should have tests verifying that configuration binds correctly:

- The `dev` profile uses a local/test database endpoint.
- The `test` profile never uses a production host.
- The `prod` profile requires mandatory secrets/URLs.
- Pool max size and acquire timeout match the property source.
- Migrations are enabled/disabled according to policy.
- Logging and Actuator exposure do not exceed requirements.

You can use `ApplicationContextRunner` or `@SpringBootTest` with profile/property overrides to test beans and configuration binding. Do not rely solely on visually inspecting YAML files; property precedence can cause runtime to receive different values.

For custom `@ConfigurationProperties`, test validation and missing property cases. For R2DBC, integration tests should verify actual connectivity to the intended database.

## 30. Safely verifying effective configuration

When multiple configuration sources exist, you need to know where the final value came from. You can:

- Log active profiles.
- Use Actuator `env`/`configprops` in secured dev environments.
- Use startup validation to verify endpoints and pool bounds.
- Inspect environment variables in deployment manifests.
- Never print passwords, tokens, or full secrets.

A startup validator can check that the hostname or database name is in an allowlist for the environment:

~~~java
@Component
public class DatabaseTargetValidator implements ApplicationRunner {

    private final Environment environment;

    public DatabaseTargetValidator(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] profiles = environment.getActiveProfiles();
        String url = environment.getProperty("spring.r2dbc.url", "");

        if (Arrays.asList(profiles).contains("test")
                && url.contains("production-db")) {
            throw new IllegalStateException(
                    "Test profile must not connect to production database"
            );
        }
    }
}
~~~

This is an illustrative example; a real allowlist should parse the host/database from the URL rather than checking a substring. Do not log the URL if it contains credentials or sensitive query parameters.

## 31. Environment configuration and multiple databases

An application may have primary/replica setups or databases for multiple bounded contexts. In such cases, changing a single `spring.r2dbc.url` property is insufficient if multiple connection factories are needed.

You can define custom properties:

~~~yaml
app:
  database:
    writer:
      url: ${DB_WRITER_URL}
      username: ${DB_WRITER_USERNAME}
      password: ${DB_WRITER_PASSWORD}
    reader:
      url: ${DB_READER_URL}
      username: ${DB_READER_USERNAME}
      password: ${DB_READER_PASSWORD}
~~~

Each environment supplies the corresponding values. `ConnectionFactory` beans must be explicitly configured with qualifiers and separate pools. If you only have a single database, do not introduce this complexity unnecessarily.

## 32. Secrets management and rotation

Secrets can be provided via:

- Kubernetes Secrets or integrated secret stores.
- Cloud secret managers.
- Vault or a secrets management platform.
- Mounted files with restricted filesystem permissions.
- Runtime-injected environment variables, if compliant with policy.

Principles:

- Never commit secrets to Git.
- Never bake secrets into image/container layers.
- Restrict which users and services can read them.
- Never log property sources or exceptions containing credentials.
- Rotate credentials according to procedure.
- Plan for updating pools/connections when passwords change.

If rotation makes new connections use the new password while old connections remain open, you need to understand how the pool recreates connections and when a restart/reload is needed. Do not assume every driver/pool automatically picks up new secrets after a file or environment change.

## 33. Configuration changes and rolling deployments

When changing a database endpoint, password, or pool size, consider old and new instances running simultaneously:

1. New secret/endpoint is provisioned.
2. New instances start and create new pools.
3. Readiness confirms connections work.
4. Traffic gradually shifts to new instances.
5. Old instances shut down gracefully and close their pools.
6. Old credentials are revoked only after no active connections need them.

If old passwords are revoked before old instances shut down, in-flight requests may fail if the pool needs to open a new connection. Rotation plans must account for rollout duration and connection lifetime.

## 34. Test configuration must never modify production

Test, cleanup, or migration commands can destroy data. Ensure:

- The `test` profile only uses a dedicated database.
- Testcontainers creates isolated databases.
- Local tests do not pick up a production URL from shared shell environment variables.
- Reset/clean scripts require confirmation or are allowed only on test hostnames/schemas.
- CI uses credentials with restricted privileges.
- Real production data is never used unless anonymized and approved.

A common mistake is a developer having a production `DB_URL` in their shell profile and running integration tests with the default profile. Tests could accidentally write to or delete real data if configuration is not controlled.

## 35. Common pitfalls

1. **Putting production endpoints and passwords in application.yml.** Easily leaks secrets and connects to the wrong environment.
2. **Not declaring an active profile on deployment.** The application may fall back to default configuration.
3. **Activating dev and prod simultaneously unintentionally.** Property overrides become unpredictable.
4. **Using the same database user for runtime and migrations.** Grants the application unnecessary DDL privileges.
5. **Confusing R2DBC URLs with JDBC URLs.** JDBC migration tools do not use the R2DBC protocol.
6. **Configuring overly large pools on every instance.** Total connections can exceed database limits during scale-out.
7. **Using production-sized pools in parallel tests.** Tests may contend for connections or connect to the wrong endpoint.
8. **Editing YAML without checking effective properties.** Environment variables or command-line arguments can override them.
9. **Using default credentials when secrets are missing.** The application can start with an insecure configuration.
10. **Enabling SQL DEBUG in production.** Logs can expose sensitive data and increase I/O.
11. **Leaving Actuator env/configprops publicly open.** Can expose internal configuration.
12. **Letting every pod run migrations with the runtime account.** Makes privileges and ordering hard to control.
13. **Ignoring rolling deployments in connection budgets.** Temporary instance count can double.
14. **Not verifying the test profile points to the right database.** Risks writing to production data.
15. **Creating a ConnectionPool per request.** Pools are not reused and exhaust resources.
16. **Assuming secret rotation automatically updates open connections.** Pools may continue using existing connections.

## Quick selection checklist

- Put common configuration in `application.yml`; place only differences in profile files.
- Activate profiles from the deployment environment, never hardcode production.
- Use environment variables or a secret manager for endpoints and credentials.
- Use separate databases for development and testing; prefer Testcontainers for integration tests.
- Separate the runtime user from the migration user and read-only user when needed.
- Configure pools/timeouts according to workload and total connection budget, without copying a single set of values across all environments.
- Use Flyway/Liquibase with a separate JDBC URL if migrations run via JDBC in an R2DBC application.
- Run production migrations in a controlled stage/job and roll out schema-compatible code.
- Secure Actuator, never log secrets, and avoid sensitive SQL parameter logging in production.
- Verify effective configuration and active profiles at startup.
- Design graceful shutdown, readiness, and secret rotation for rolling deployments.
- Write tests confirming the `test` profile cannot connect to production.

Separating development, testing, and production configurations allows the same Spring Data R2DBC application to run consistently across environments while using the right database, credentials, pool sizing, and operational policies. Use Spring Profiles for meaningful configuration groups, externalized properties for deployment values, and a secret manager for sensitive data. Calculate connection budgets across all instances, separate runtime accounts from migration accounts, test against isolated databases, and verify runtime configuration instead of just reading YAML. When migrations, readiness, graceful shutdown, and secret rotation are integrated into the deployment workflow, the risk of connecting to the wrong environment and operational failures drops significantly.
