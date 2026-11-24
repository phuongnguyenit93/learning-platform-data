# Supplying Test Configuration Instead of Depending on Production Services at Build Time

When exporting OpenAPI in CI, springdoc-openapi needs a running Spring Boot application to generate documentation from controllers, models, annotations, and existing configuration. Consequently, the export process can accidentally initialize a production database, call an identity provider, connect to Kafka, send requests to partner services, or read live environment secrets if the build uses default configuration.

A safe and reliable approach is creating a profile dedicated to documentation export, such as an openapi profile. This profile supplies test configuration, mock data, or replacement services for dependencies unnecessary for specification generation. The application still initializes the controllers and springdoc components to scan; only external integrations are swapped for CI-appropriate configuration.

This lesson explains how to organize the profile, replace production dependencies, run the application temporarily to fetch OpenAPI JSON, save artifacts, and verify results before release.

## 1. Why shouldn't builds depend on production services?

springdoc-openapi typically generates documentation at runtime from the Spring application context. When CI needs to export an OpenAPI file, the application must start up enough for springdoc to discover endpoints, schemas, security schemes, and metadata.

If the application uses production configuration during this step, the build can run into problems:

- Fails to start when the production database is unreachable.
- The build depends on live environment secrets, credentials, or certificates.
- A bean calls a partner API immediately at initialization or during doc generation.
- Kafka, RabbitMQ, or schedulers open connections and run unintended tasks.
- CI lacks network access to the internal production environment.
- Export results vary with the data, state, or configuration of external services.
- The build could accidentally send emails, emit messages, or trigger side effects.

Generating OpenAPI primarily needs application metadata. It generally does not need production business data or permission to call live services. Therefore, provide a dedicated startup environment with deterministic test data and integrations.

## 2. Separating export configuration from production configuration

Spring Boot supports profile-specific configuration. You can create an application-openapi.yml file containing settings dedicated to documentation export:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
  application-openapi.yml
~~~

The openapi profile is activated when running the application in CI. Properties in application-openapi.yml override the corresponding values from application.yml.

Example:

~~~yaml
# application-openapi.yml
server:
  port: 18080

spring:
  application:
    name: catalog-service

springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false

app:
  jobs:
    enabled: false
  messaging:
    consumers-enabled: false
  integrations:
    inventory:
      mode: stub
    payment:
      mode: stub
~~~

The app.jobs, app.messaging, and app.integrations properties are examples of application-specific settings. They only take effect if application code actually reads and applies them, such as with @ConfigurationProperties or @ConditionalOnProperty. There is no default rule in Spring Boot that disables schedulers or consumers merely because these keys appear.

Do not put production passwords, API keys, client secrets, or private keys into the export profile. If a component needs credentials to start, supply dedicated test credentials or replace that component with a mock adapter.

## 3. An export profile is not a stripped-down production profile

The export profile must preserve the components needed for springdoc to see the API contract:

- Controllers or functional routes.
- DTOs, records, enums, and models used in requests/responses.
- OpenAPI and validation annotations.
- Security schemes and operation metadata.
- Document group configuration if the project uses GroupedOpenApi.
- Beans required to build the application context.

Components that can usually be replaced or disabled in a controlled manner:

- HTTP clients calling partner services.
- Background message listeners and consumers.
- Schedulers, batch jobs, or notification senders.
- External identity provider connections if the application can use test auth configuration.
- Real databases, if replaceable with a temporary database or suitable test double.

Do not disable component scanning or strip out all controllers just to make the application start faster. Doing so can leave the exported documentation missing endpoints. The goal is replacing unnecessary dependencies while keeping the API definitions to be published intact.

## 4. Replacing adapters that call external services

Place external integrations behind an interface so implementations can be swapped per profile. For example, an application needing inventory lookup:

~~~java
interface InventoryGateway {
    InventoryItem findBySku(String sku);
}

record InventoryItem(
    String sku,
    int availableQuantity
) {
}
~~~

Production implementation calling the real service:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

@Component
@Profile("!openapi")
class HttpInventoryGateway implements InventoryGateway {

    private final RestTemplate restTemplate;

    HttpInventoryGateway(
            RestTemplateBuilder builder,
            @Value("${app.integrations.inventory.base-url}") String baseUrl) {
        this.restTemplate = builder
            .rootUri(baseUrl)
            .build();
    }

    @Override
    public InventoryItem findBySku(String sku) {
        return restTemplate.getForObject(
            "/items/{sku}",
            InventoryItem.class,
            sku
        );
    }
}
~~~

Implementation used in the export profile:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("openapi")
class OpenApiStubConfiguration {

    @Bean
    InventoryGateway inventoryGateway() {
        return sku -> new InventoryItem(sku, 25);
    }
}
~~~

When the openapi profile is active, Spring creates the mock bean. In other profiles, Spring creates the production HTTP adapter. Controllers and services still depend on the InventoryGateway interface, so endpoint signatures do not need to change.

Ensure only one implementation is registered in each profile. If the production implementation lacks an appropriate profile or condition, the application may fail with multiple beans of the same type.

The stub here only helps the application context start and gives flows needing inventory a deterministic result. It does not replace HTTP integration testing against the real inventory service. Communication tests require a dedicated environment such as WireMock or Testcontainers.

## 5. Using ConditionalOnProperty for optional integrations

If the application already uses properties to toggle integrations on/off, control them via the export profile:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ProductionMessagingConfiguration {

    @Bean
    @ConditionalOnProperty(
        name = "app.messaging.consumers-enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    MessageConsumer messageConsumer() {
        return new MessageConsumer();
    }
}
~~~

In application-openapi.yml:

~~~yaml
app:
  messaging:
    consumers-enabled: false
~~~

The example above is only meaningful if the application controls consumer creation with that exact property. With Spring Kafka, RabbitMQ, or other libraries, check the corresponding listener/container configuration; preventing a single consumer bean from being created does not necessarily disable all auto-configuration or connection factories.

If the application needs to keep messaging beans to build schemas or metadata, disable message consumption instead of removing required beans. Do not rely on an assumed framework property without verifying it exists in the version in use.

## 6. Test database for startup

Some applications connect to a database immediately at startup because of JPA, Flyway, Liquibase, or repositories. If CI only needs to generate documentation, it should not point to a production database.

There are three common options:

| Option | When suitable | What to check |
|---|---|---|
| H2 or in-memory database | Simple schema compatible with H2 | Dialect, data type, and SQL migration differences |
| Testcontainers | Need a temporary database with the same engine as production | CI must have a container runtime |
| Repository/service test doubles | No database access needed during doc generation | Must replace the exact dependencies and keep controllers in context |

If using H2, you can configure:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:openapi;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

This configuration is only suitable when entity mappings can initialize with H2 and do not rely on production-database-specific SQL. If the application uses migrations incompatible with H2, use Testcontainers with the same database engine or replace repositories in a dedicated test context.

If running the packaged application with the Spring Boot Maven Plugin, test-scope dependencies are not automatically on the runtime classpath of the application process. You can add the test database at runtime scope in a separate export Maven profile so it does not enter the production artifact. If using @SpringBootTest inside the test process, test-scope dependencies can be used directly.

Do not blindly disable Flyway or Liquibase. If the application needs the schema to initialize repositories, run migrations against a compatible temporary database. Only disable migrations once confirmed the application context does not require that schema.

## 7. Keeping security schemes in documentation without depending on a production identity provider

springdoc can describe Bearer, OAuth2, or OpenID Connect without calling a production identity provider to generate documentation. Security schemes are OpenAPI metadata; runtime token verification is a separate activity.

In the export profile:
- Allow the CI process to read the OpenAPI documentation endpoint.
- Keep the API's security schemes and security requirements.
- Do not include production client secrets in configuration.
- If a JWT decoder needs keys or an issuer to initialize, use test public keys/JWKs or a mock JwtDecoder in the test context.
- Do not disable authentication for the entire API just so the plugin can download documentation.

With Spring MVC/Spring Security, you can permit only the documentation endpoints in a filter chain dedicated to the export profile:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@Profile("openapi")
class OpenApiSecurityConfiguration {

    @Bean
    SecurityFilterChain openApiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/v3/api-docs/**",
                    "/v3/api-docs.yaml"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .build();
    }
}
~~~

If the application already has another SecurityFilterChain, configure profiles so two chains do not unexpectedly compete. You can integrate the documentation-endpoint rules into the existing chain. With WebFlux, use SecurityWebFilterChain and the corresponding matchers instead of the Servlet configuration above.

The paths in the example are defaults. If springdoc.api-docs.path was changed or group endpoints are used, update the matchers accordingly. Using permitAll in the openapi profile does not mean opening documentation in production; this profile is only activated in the CI process used for export.

## 8. Exporting OpenAPI with the springdoc-openapi Maven Plugin

springdoc-openapi-maven-plugin calls the running application's OpenAPI endpoint and writes the response to a file. The plugin does not replace the Spring Boot runtime and does not initialize all application dependencies by itself. Therefore, the application must be started with the export profile before running the generate goal.

A typical Maven workflow:

1. Build the application.
2. Start Spring Boot in the pre-integration-test phase.
3. Activate the openapi profile in the application JVM.
4. Call the /v3/api-docs endpoint in the integration-test phase.
5. Write JSON to the build directory.
6. Stop the application in the post-integration-test phase.

Example plugin configuration inside a Maven profile:

~~~xml
<profiles>
    <profile>
        <id>openapi-export</id>

        <dependencies>
            <dependency>
                <groupId>com.h2database</groupId>
                <artifactId>h2</artifactId>
                <scope>runtime</scope>
            </dependency>
        </dependencies>

        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>start-openapi-app</id>
                            <phase>pre-integration-test</phase>
                            <goals>
                                <goal>start</goal>
                            </goals>
                        </execution>
                        <execution>
                            <id>stop-openapi-app</id>
                            <phase>post-integration-test</phase>
                            <goals>
                                <goal>stop</goal>
                            </goals>
                        </execution>
                    </executions>
                    <configuration>
                        <jvmArguments>
                            -Dspring.profiles.active=openapi
                        </jvmArguments>
                    </configuration>
                </plugin>

                <plugin>
                    <groupId>org.springdoc</groupId>
                    <artifactId>springdoc-openapi-maven-plugin</artifactId>
                    <version>1.4</version>
                    <executions>
                        <execution>
                            <id>export-openapi</id>
                            <phase>integration-test</phase>
                            <goals>
                                <goal>generate</goal>
                            </goals>
                        </execution>
                    </executions>
                    <configuration>
                        <apiDocsUrl>http://localhost:18080/v3/api-docs</apiDocsUrl>
                        <outputFileName>openapi.json</outputFileName>
                        <outputDir>${project.build.directory}/openapi</outputDir>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

The example uses H2 at runtime scope, but only inside the openapi-export Maven profile. When production builds run without activating this profile, the H2 dependency is not added to the production artifact.

Replace the plugin version with the version approved by your project and check compatibility with the current Maven/Spring Boot setup. If using separate dependency management, add the appropriate H2 version or BOM.

Run the workflow:

~~~bash
mvn -B -Popenapi-export clean verify
~~~

When Maven runs this profile, the Spring Boot Maven Plugin starts the application on port 18080 with the openapi profile. The springdoc plugin calls the configured URL and writes the file to target/openapi/openapi.json.

Phases are critical: if export runs before the application is ready, the plugin fails to fetch documentation. If the app does not stop after export, the CI process may hang or occupy the port for the next job. When a phase fails and stops the lifecycle before reaching post-integration-test, the pipeline should have a process cleanup step in an always-run section of CI.

If the api-docs path was customized, update the URL in apiDocsUrl. If separate groups need exporting, use the corresponding group endpoints, such as /v3/api-docs/public, and create a separate execution/output file for each group.

## 9. Ensuring export configuration is not activated in production

The openapi profile should only be enabled explicitly in the documentation-export job. Do not set spring.profiles.active=openapi in application.yml or production environment variables.

Several principles:
- Use the openapi-export Maven profile only in the export job.
- Enable spring.profiles.active=openapi only on the JVM running the export application.
- Production deployments continue to use the dedicated production profile.
- Do not let the openapi profile override shared configuration if that profile could be accidentally activated outside CI.
- Do not package fixed test secrets that could be misused in production.
- You can inspect active profiles in startup logs to confirm the process is using openapi.

Maven profiles and Spring profiles serve different roles. The openapi-export Maven profile decides which dependencies/plugins are added to the build. The openapi Spring profile decides which configuration and beans are loaded when the application runs. Sharing a similar name helps memory, but the two profiles do not activate each other automatically; JVM or environment settings are needed to pass the Spring profile into the application process.

## 10. Using a test context instead of a packaged application process

Another option is creating an integration test with @SpringBootTest. The test context can use @TestConfiguration, Mockito, or test beans to replace dependencies without putting mock implementations into the application artifact.

Directional example:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.profiles.active=openapi",
        "springdoc.api-docs.enabled=true"
    }
)
@Import(OpenApiTestOverrides.class)
class OpenApiExportTest {
    // Fetch the OpenAPI document over HTTP and write it to a build file.
}
~~~

In the test context, you can swap repositories/clients for test beans and use a random port to avoid conflicts. The test can call the /v3/api-docs endpoint and save the response to the build directory.

The advantage is that test dependencies are available and no separate application JVM needs to be launched. However, the test must genuinely fetch the HTTP response from the application context to verify web and springdoc configuration accurately. Instantiating an OpenAPI bean directly can miss issues related to endpoints, security filters, context paths, or serialization.

If using this approach, ensure the test runs in the right CI phase, the file is written to the build directory, and the test fails if the docs endpoint does not return a valid document.

## 11. Gradle and other CI systems

springdoc-openapi-maven-plugin is a Maven plugin. Gradle projects can use an integration test or a CI task that starts the application with the openapi profile and downloads the documentation endpoint.

Equivalent Gradle workflow:
1. Build the executable application or test runtime.
2. Run the application with the openapi Spring profile.
3. Wait for the health/readiness endpoint or poll until the docs endpoint is ready.
4. Download /v3/api-docs or group endpoints.
5. Save the response to build/openapi/openapi.json.
6. Stop the application even if the documentation download step fails.
7. Validate the file before uploading the artifact.

Do not use a fixed sleep as the sole condition for checking application readiness. Use health checks or bounded retries until the docs endpoint responds, then report a clear error on timeout.

Whether using GitHub Actions, GitLab CI, Jenkins, or another system, keep the export profile and artifact path consistent. The CI runner needs permissions to download dependencies, start databases/containers if applicable, and write artifacts to the job workspace.

## 12. Inspecting the OpenAPI file after export

An existing file does not mean a valid document. After export, check at least:

- The file exists and is non-empty.
- JSON parses cleanly.
- The openapi field is present and the version falls within the project's supported range.
- info.title and info.version are present.
- Important paths are published.
- Request/response schemas are not missing due to the profile accidentally excluding beans.
- Security schemes and security requirements still appear.
- Server URLs do not mistakenly point to localhost, container hostnames, or internal URLs.
- No credentials, tokens, or secrets appear in descriptions/examples.
- Schema compositions and constraints conform to the OpenAPI version.

You can add an OpenAPI validator in CI to check document structure. If the project has a baseline, use a contract diff tool to detect breaking changes before merging or publishing.

Do not compare file sizes alone. Key ordering, metadata, or formatting can change without changing the contract; conversely, a file of identical size can still contain incompatible changes.

## 13. Checking whether the export profile produces documentation equivalent to production

The export profile replaces external dependencies, but it must preserve API metadata. Verify the following components between the export profile and the normal application environment:

| Component | What to keep consistent |
|---|---|
| Controllers/functional routes | Paths, methods, operationIds, tags |
| DTOs and schemas | Properties, types, required flags, validation constraints |
| OpenAPI annotations | Summaries, descriptions, responses, examples |
| Security | Schemes, scopes, and security requirements |
| GroupedOpenApi | Group names, paths/include/exclude |
| Customizers | Added schemas and operations |
| Jackson | Naming strategies, modules, and serialization metadata |

A stub service can return mock data, but it must not replace a controller with a stripped-down controller having a different contract. If the export profile skips a bean that builds operation metadata, the generated documentation will not reflect the real contract.

Have automated checks confirming that key paths and schemas exist in the exported file. When changing profile configuration, review those assertions to avoid silently dropping endpoints while the build stays green.

## 14. Common errors

**Build uses application-prod.yml.** The application attempts to connect to a live database, identity provider, or service. Activate the dedicated openapi profile when running the export process.

**Added application-openapi.yml without enabling the profile.** Spring Boot does not pick that file automatically. Pass spring.profiles.active=openapi to the JVM or process environment.

**Created a stub bean while the production implementation is still registered.** Spring may report multiple beans of the same type or pick the wrong adapter. Use @Profile or @ConditionalOnProperty on both implementations.

**Put H2 in test scope and ran the packaged app.** The dependency is missing from the process's runtime classpath. Use an export Maven profile with runtime scope or run inside a test context.

**Disabled databases/messaging globally.** The application context may fail to initialize or lose required beans. Only replace/disable side-effecting components per profile.

**Opened the entire API without authentication.** Permit only the documentation endpoint in the export profile; keep operation security schemes and authorization intact.

**Used a production identity provider to build OpenAPI.** Export does not need production tokens. Use test keys/JWKs or a mock decoder if the application needs JWT components initialized.

**Called the docs endpoint before the application was ready.** The plugin gets connection errors. Ensure startup lifecycle completes and the endpoint responds before the generate goal.

**Did not stop the application after export.** The CI runner keeps a lingering process and occupied port. Bind the stop goal to the right phase and add cleanup when the pipeline fails.

**Export profile dropped controllers or customizers.** JSON is valid yet missing operations. Keep the application context intact and check required paths/schemas.

**Internal data or URLs leaked into documentation.** Inspect servers, examples, and descriptions to remove internal hostnames, tokens, or secrets before uploading artifacts.

## 15. Checklist for the OpenAPI export pipeline

- [ ] A dedicated Spring profile exists for export, such as openapi.
- [ ] application-openapi.yml exists with test ports and configuration.
- [ ] Export profile contains no production secrets.
- [ ] External HTTP integrations are replaced with stubs, WireMock, or test services.
- [ ] Database uses an appropriate in-memory/test container or repository test double.
- [ ] Consumers, schedulers, and batch side effects are intentionally disabled.
- [ ] Controllers, DTOs, security metadata, and OpenAPI customizers remain loaded.
- [ ] Documentation endpoint is permitted within the CI process scope.
- [ ] Maven/Gradle activates the right Spring profile.
- [ ] Application is started before calling the docs endpoint.
- [ ] OpenAPI JSON/YAML is written to a defined artifact path.
- [ ] Application is stopped even when export fails.
- [ ] File is parsed and validated.
- [ ] Paths, schemas, server URLs, and security schemes are verified.
- [ ] Contract diff or baseline check runs before publishing.

## References

- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): profile configuration and activation per environment.
- [Spring Boot Maven Plugin – Start and Stop](https://docs.spring.io/spring-boot/maven-plugin/run.html): running the application in the Maven lifecycle.
- [springdoc-openapi Maven Plugin](https://github.com/springdoc/springdoc-openapi-maven-plugin): calling OpenAPI endpoints and writing documentation to files during builds.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): precedence order and configuration loading.
- [Spring Framework – Environment Profiles](https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles): conditional bean creation per profile.
- [Testcontainers](https://testcontainers.com/): creating ephemeral test dependencies such as databases and infrastructure services.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): structure and rules of an OpenAPI document.
