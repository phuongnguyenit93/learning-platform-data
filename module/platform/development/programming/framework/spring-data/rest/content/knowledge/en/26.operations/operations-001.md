# Separating Development, Testing, and Production Configurations in Spring Data REST

## 1. Goals and Principles

A Spring Data REST application typically runs in at least three environments:

- **Development (dev)**: developers run the application on their local machines, using databases and integrated services intended for development, with verbose logging enabled to investigate issues.
- **Testing (test)**: runs unit tests and integration tests with isolated data and deterministic configuration, without accidentally connecting to a real database.
- **Production (prod)**: serves real users, retrieves connection details and secrets from the deployment environment, restricts diagnostic information, and uses safe database configuration.

Spring Boot supports separating these configurations using **Spring Profiles** and **Externalized Configuration**. The same source code and the same JAR file can run in different environments; the environment determines which configuration is loaded at startup.

Principles to apply:

1. Put shared values in application.yml.
2. Put environment-specific differences in application-dev.yml, application-test.yml, and application-prod.yml.
3. Select the profile at startup via an environment variable, JVM system property, or command-line argument.
4. Keep passwords, tokens, private keys, and sensitive information out of source code and build artifacts.
5. Only allow test configurations to use test data; never let dev or test silently become the production configuration.
6. Use the same built artifact across environments and change only runtime configuration per environment.

## 2. How Do Spring Profiles Work?

A profile is the name of a group of configurations or beans enabled in the Environment. When the dev profile is activated, Spring Boot loads the shared configuration along with the dev-specific configuration. Beans annotated with @Profile("dev") can also be registered in the application context.

Example file structure:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-prod.yml
~~~

application.yml is always the shared configuration. An application-{profile}.yml file is only applied when the corresponding profile is active. For example, when prod is active, Spring Boot loads application.yml and then applies the values in application-prod.yml; profile-specific values override shared values when the same property appears in both places.

Multiple profiles can be enabled at the same time, such as dev,metrics. When multiple profiles define the same property, the profile processed later can override earlier values. Only enable multiple profiles deliberately, and avoid combining dev with prod, which makes configuration unpredictable.

If no active profile is set, Spring uses a default profile named default. You can rename the default profile with spring.profiles.default. For applications that need to force the deployment environment to declare a profile explicitly, you can set spring.profiles.default: none in the shared file. Then, if someone forgets to set a profile, application-dev.yml, application-test.yml, and application-prod.yml will not be selected as profiles.

**Do not set spring.profiles.active or spring.profiles.default inside a profile-specific file** such as application-prod.yml or in a document activated by spring.config.activate.on-profile. These properties must live in a non-profile-specific document or be passed from outside the application. The clearest approach for deployment is setting SPRING_PROFILES_ACTIVE in the runtime environment.

## 3. Creating Shared Configuration

Example src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: spring-data-rest-api
  profiles:
    default: none
  data:
    rest:
      base-path: /api
      default-page-size: 20
      max-page-size: 100
      detection-strategy: annotated

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

Explanation:

- spring.application.name sets the application name.
- spring.profiles.default: none prevents silently using the default profile when the deployment has not declared a profile.
- spring.data.rest.base-path: /api sets a shared prefix for repository endpoints, for example /api/orders.
- default-page-size and max-page-size limit the default and maximum page sizes of collection endpoints.
- detection-strategy: annotated only exports repositories annotated with @RepositoryRestResource (except cases configured for export individually). This is a deliberate way to control which repositories appear in the REST API.
- management.endpoints.web.exposure.include only exposes the Actuator endpoints that are needed. Do not open all endpoints just for debugging convenience.
- management.endpoint.health.show-details: never avoids returning health details to arbitrary callers of the endpoint.

If the application does not use YAML, the same properties can be written in application.properties. You should standardize on one format across the entire project; when .properties and YAML coexist in the same location, .properties takes higher precedence.

With detection-strategy: annotated, a repository must be exported explicitly, for example:

~~~java
@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders"
)
public interface OrderRepository extends JpaRepository<Order, UUID> {
}
~~~

This example assumes the application uses Spring Data JPA. With Spring Data MongoDB, Cassandra, or another store module, the repository extends the corresponding interface of that module. Restricting exported repositories helps control the API surface, but **does not replace authentication and authorization**. Endpoints with sensitive data still need Spring Security and appropriate authorization rules.

## 4. Development Configuration

Create src/main/resources/application-dev.yml:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/spring_data_rest_dev
    username: spring_dev
  jpa:
    hibernate:
      ddl-auto: update

logging:
  level:
    org.springframework.data.rest: DEBUG
    org.hibernate.SQL: DEBUG

server:
  error:
    include-message: always
~~~

In this example:

- The database is PostgreSQL installed on the development machine.
- ddl-auto: update is convenient for the local development loop, but should not be used in production.
- DEBUG logging helps observe Spring Data REST and SQL behavior. If logs contain sensitive data, sanitize or adjust them before sharing logs.
- server.error.include-message: always is only appropriate in a controlled local environment; do not enable it broadly in production because error messages can disclose internal details.

The database password is passed separately via the SPRING_DATASOURCE_PASSWORD environment variable; do not write passwords into committed configuration files. If using a local database that does not require a password, configure it according to your team's database setup while still preserving the rule of never putting real credentials into Git.

Run on macOS/Linux:

~~~bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
~~~

Run on Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\mvnw.cmd spring-boot:run
~~~

Or run the built JAR:

~~~bash
java -jar target/spring-data-rest-api.jar --spring.profiles.active=dev
~~~

After startup, check the startup logs to confirm the dev profile is active and call an endpoint under the configured base path, for example GET http://localhost:8080/api/orders.

If the project does not use JPA, omit the spring.datasource and spring.jpa sections and replace them with properties for the actual persistence module. Spring Data REST does not require every application to use the same kind of database.

## 5. Testing Configuration

Create src/main/resources/application-test.yml:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:spring_data_rest_test;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop

logging:
  level:
    org.springframework.data.rest: WARN
    root: WARN
~~~

This configuration is for a Spring Data REST application using JPA with H2 in test dependencies. An in-memory database is created specifically for tests; the schema is created when the context starts and dropped when the context closes. Never put production data into the test database.

If integration tests depend on specific behavior of PostgreSQL, MySQL, or the real database in use, run tests against the exact engine using Testcontainers or a dedicated test database. H2 can differ from the production database in data types, SQL dialect, constraints, and transaction behavior.

Activate the test profile in Spring TestContext using @ActiveProfiles:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class OrderRestIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesOrderCollection() throws Exception {
        mockMvc.perform(get("/api/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Commonly used static and standard imports:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
~~~

The test assumes the repository has been exported at /api/orders and the application has Spring MVC MockMvc test support. Adjust the path and media type if the application customizes REST mappings.

Run tests:

~~~bash
./mvnw test
~~~

Or on Windows:

~~~powershell
.\mvnw.cmd test
~~~

@ActiveProfiles("test") instructs Spring TestContext to activate the test profile when creating the application context. As a result, integration tests do not depend on whatever profile happens to be set in the developer's terminal. If a test uses @SpringBootTest(properties = ...), @DynamicPropertySource, or @TestPropertySource, keep in mind that test-specific configuration sources have high precedence and can override values in profile files.

## 6. Production Configuration

Create src/main/resources/application-prod.yml:

~~~yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate

logging:
  level:
    root: INFO

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
~~~

This example still assumes the application uses Spring Data JPA:

- ddl-auto: validate requires Hibernate to verify the existing schema instead of modifying the schema at application startup. Use Flyway, Liquibase, or your organization's migration process to apply schema changes before deployment.
- open-in-view: false avoids keeping the persistence context open for the entire duration of web request processing; review and handle fetch strategies appropriately before enabling this.
- Default logging is at INFO level; only raise log levels temporarily with a clear plan, scope, and expiration time.
- Health details are only shown to callers granted appropriate authorization.
- Liveness and readiness probes are useful when deploying on Kubernetes or platforms that support health probes.

Do not put real database URLs, usernames, passwords, tokens, or private keys in application-prod.yml. Pass them via a secret manager, environment variables, or a config tree mounted into the container by the deployment platform.

Example environment variables for production:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL=jdbc:postgresql://db.internal:5432/spring_data_rest
SPRING_DATASOURCE_USERNAME=spring_app
SPRING_DATASOURCE_PASSWORD=<secret supplied by deployment platform>
~~~

Spring Boot relaxed binding converts property names into environment variable names: dots become underscores, hyphens are removed, and characters are uppercased. Thus spring.datasource.password corresponds to SPRING_DATASOURCE_PASSWORD.

You can use a config tree if the platform mounts secrets as files. Example files:

~~~text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
~~~

Add to application-prod.yml:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Spring Boot reads filenames in the config tree as property names. With this approach, the secret mount configuration must exist when the production application starts; do not set default values for required secrets to avoid running the application with unintended credentials.

Activate the production profile when running:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar target/spring-data-rest-api.jar
~~~

Or pass the profile directly:

~~~bash
java -jar target/spring-data-rest-api.jar --spring.profiles.active=prod
~~~

On container/orchestrator platforms, set profiles and secrets in the workload's deployment configuration. Do not package secrets into the JAR or Docker image. Promote the same tested artifact across environments; change only runtime configuration.

## 7. Configuration Precedence Order

Spring Boot aggregates properties from many sources. A higher-precedence source can override values from a lower-precedence source. For commonly used sources, you can remember the ascending order as follows:

1. Default values set by the application.
2. Configuration files on the classpath, including application.yml and profile-specific files.
3. Configuration files outside the JAR.
4. OS environment variables.
5. Java system properties.
6. SPRING_APPLICATION_JSON.
7. Command-line arguments.
8. Certain test-specific sources such as @SpringBootTest(properties=...), @DynamicPropertySource, and @TestPropertySource can take higher precedence than typical runtime sources.

The full order includes additional sources such as @PropertySource, JNDI, and servlet context parameters. Consult the Externalized Configuration documentation when you need to determine the exact winning source in a specific scenario.

For example, if application-prod.yml sets server.port: 8080 but the deployment supplies SERVER_PORT=9090, the value from the environment variable is used. A command-line argument --server.port=9091 can further override that value.

Points to remember:

- Profile-specific files override shared files when the same property is defined.
- Configuration files outside the JAR can override files packaged inside the JAR.
- With multiple active profiles, profile order affects the final value.
- Do not embed spring.profiles.active inside application-prod.yml; select the profile from runtime.
- If using spring.config.location, that list of locations replaces the default configuration locations. If you want to add locations, consider spring.config.additional-location.
- Spring Boot loads application.properties and YAML variants from standard configuration locations. Avoid defining the same property in both formats.

## 8. Distinguishing Spring Profiles and @Profile

application-{profile}.yml files determine which configuration values are loaded. The @Profile annotation determines which beans or configuration classes are registered.

Example of registering a bean only to support development:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
class DevelopmentConfiguration {

    // Declare beans intended only for the development environment.
}
~~~

@Profile can be used on @Component, @Configuration, @ConfigurationProperties, or bean methods according to Spring rules. Do not use profiles as a substitute for authorization: an endpoint or repository containing sensitive data must still be protected with Spring Security and authorization policies.

For custom application configuration with many fields, prefer grouping them into a strongly typed @ConfigurationProperties class with validation. This catches missing or mistyped configuration at startup rather than scattering @Value strings across services.

## 9. Actuator and Health Checks on Deployment

When using Spring Boot Actuator, the health endpoint is exposed over HTTP at /actuator/health by default. When health probes are enabled, you can check:

- /actuator/health/liveness: whether the application is alive and should keep running or needs a restart.
- /actuator/health/readiness: whether the application is ready to receive traffic.

When deploying on Kubernetes, point livenessProbe and readinessProbe to the corresponding endpoints. Do not blindly include database or external service checks in liveness: if a shared database has a temporary outage, Kubernetes could restart all instances at once and worsen the incident. Readiness can factor in external dependencies if that matches how the system handles failures.

Only expose necessary Actuator endpoints. Avoid exposing env, configprops, beans, heapdump, or * publicly because these endpoints can reveal internal details or sensitive data. If needed for diagnostics, protect them with Spring Security, network policies, or platform access controls.

## 10. Pre-Deployment Checklist

### Development

- [ ] The dev profile is explicitly enabled when running locally.
- [ ] The local database is separated from test and production databases.
- [ ] Local credentials are not committed to Git.
- [ ] Verbose logs and error messages are only enabled in a controlled local environment.
- [ ] No mock services or fake data are included in the production profile.

### Testing

- [ ] Tests use @ActiveProfiles("test") or an equivalent configuration.
- [ ] The test database is created/isolated and cleaned up per the test lifecycle.
- [ ] Integration tests verify repository endpoints, base path, HAL responses, and critical behavior.
- [ ] Tests never read from or write to the production database.
- [ ] If relying on engine-specific SQL/dialect features, tests run against the same database type as production.

### Production

- [ ] Deployment sets SPRING_PROFILES_ACTIVE=prod.
- [ ] Database URL and credentials come from a secret manager, environment variables, or config tree.
- [ ] No passwords, tokens, or private keys exist in source code, JARs, or images.
- [ ] Schema is migrated before deployment; Hibernate does not auto-update the production schema.
- [ ] Repositories are intentionally exported and endpoints have authentication/authorization.
- [ ] Only necessary Actuator endpoints are exposed; health details are protected.
- [ ] Health probes match the deployment platform.
- [ ] The same tested artifact is promoted to production.

## 11. Troubleshooting

| Symptom | Common Cause | How to Check and Resolve |
|---|---|---|
| Application always uses default configuration | Profile not enabled or incorrect filename | Check SPRING_PROFILES_ACTIVE, application-{profile}.yml naming, and startup logs. |
| application-prod.yml is not loaded | prod profile not active or file placed in wrong location | Set SPRING_PROFILES_ACTIVE=prod; verify the file is on the classpath or in a declared external config location. |
| spring.profiles.active causes an error in a profile file | Active property placed inside application-prod.yml or a profile-specific document | Move profile selection to an environment variable, system property, or command line. |
| YAML value is not used | Environment variable, system property, or command line has higher precedence | Check which property source is overriding; verify environment variable naming follows relaxed binding. |
| Database password is not bound | Wrong environment variable name or secret not mounted | For spring.datasource.password, use SPRING_DATASOURCE_PASSWORD; verify deployment supplies the variable or config tree. |
| Tests accidentally connect to local database | Tests do not activate the test profile | Use @ActiveProfiles("test"), verify the test datasource, and do not rely on developer machine environment variables. |
| H2 tests pass but production fails with SQL errors | H2 differs from production engine or dialect | Run integration tests against the matching database using Testcontainers or a dedicated test database. |
| /api/orders returns 404 | Wrong base path, repository not exported, or different mapping | Check spring.data.rest.base-path, detection-strategy, and @RepositoryRestResource on the repository. |
| /actuator/health/liveness returns 404 | Health probes not enabled or Actuator missing from classpath | Check the Actuator dependency and management.endpoint.health.probes.enabled. |
| Cannot read health details | show-details is never or caller is not authorized | Keep safe defaults in production; configure roles and security if operators need to view details. |
| Production fails to start due to ddl-auto: validate | Schema not migrated or incompatible with entities | Run the proper versioned migration before deployment, and verify schema and connection settings. |

To determine which source a final property came from, Spring Boot can assist diagnostics via the env and configprops Actuator endpoints. Only expose them temporarily in a protected environment; sensitive values are sanitized by default, but the endpoints still reveal internal configuration structure.

## 12. Official References

- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): activating profiles, default profile, includes, profile groups, and profile-specific configuration files.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property source precedence order, profile-specific files, environment variables, config import, and configuration trees.
- [Spring Data REST — Getting Started / Basic Settings](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): repository detection strategy, base path, and Spring Data REST configuration properties.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): list of properties supported by Spring Boot, including spring.data.rest.*, spring.datasource.*, and management.*.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, endpoint security, health details, liveness, and readiness probes.
- [Spring Framework — Context Configuration with Environment Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html): using @ActiveProfiles in Spring TestContext.
- [Spring Framework — Integration Testing](https://docs.spring.io/spring-framework/reference/testing/integration.html): testing wiring, persistence, and Spring applications without deploying to an application server.
