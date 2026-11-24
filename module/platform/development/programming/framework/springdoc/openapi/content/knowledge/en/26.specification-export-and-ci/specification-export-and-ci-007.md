# A Dedicated Profile for Exporting Documentation While Still Loading All Required Mappings

springdoc-openapi builds the OpenAPI document by inspecting a running Spring Boot application: controllers, functional routes, Spring MVC/WebFlux configuration, DTOs, validation, and annotations. Therefore, when exporting documentation in CI, the application must start with the beans that register the endpoints clients will call in the deployment environment.

A dedicated documentation-export profile is very useful: it can disable Swagger UI, use mock adapters for external services, and avoid connecting to production systems. However, if this profile accidentally excludes controllers, RouterFunctions, or handler-registration configuration from the ApplicationContext, the application may still start successfully while the OpenAPI document misses operations or has only empty paths.

This lesson guides you through designing a documentation-export profile, preserving required mappings, configuring springdoc, and using the Maven/Gradle plugin to save JSON or YAML as a build artifact.

## 1. Why do you need a dedicated profile for exporting OpenAPI?

In a real project, production runtime configuration often includes components unnecessary for the documentation-export step:

- Connections to a production database or message broker.
- Calls to payment, email, inventory, or third-party services.
- Enabling Swagger UI for end users.
- Logging, tracing, or caching configured for the deployment environment.
- Credentials and endpoints that exist only in the live environment.

An export profile lets the application start under a controlled configuration. For example:

| Component | Production profile | Openapi profile |
| --- | --- | --- |
| REST controllers | Yes | Yes |
| RouterFunction/WebFlux routes | Yes | Yes |
| RequestMappingHandlerMapping | Yes | Yes |
| Springdoc API docs endpoint | Yes if enabled | Enabled so the plugin fetches documentation |
| Swagger UI | Per deployment policy | Can be disabled |
| Database adapter | Connects to production database | Test adapter or empty data |
| External service adapter | Real client | Safe stub/no-op or mock |
| Production secrets | Yes via secret store | Not needed |

The key point is that the export profile changes configuration and adapters needed for startup; it must still register the exact set of endpoints belonging to the API contract.

## 2. Springdoc reads registered mappings

Springdoc does not synthesize controllers from class names or from source code on disk. It reads the handlers registered by Spring in the ApplicationContext.

With Spring MVC, mapping annotations such as @RequestMapping, @GetMapping, and @PostMapping are registered through RequestMappingHandlerMapping. With WebFlux, the application also has mapping annotations and can register functional routes via RouterFunction beans.

If a controller is excluded by @Profile, @ConditionalOnProperty, a component scan filter, or import configuration, that controller's mappings do not appear in the handler registry. springdoc cannot include that operation in the document.

The documentation-generation flow can be visualized as follows:

~~~mermaid
flowchart TD
    A[Start Spring Boot with openapi profile] --> B[Load configuration and profile groups]
    B --> C[Register controller and RouterFunction beans]
    C --> D[Create HandlerMapping and route registry]
    D --> E[springdoc reads mappings, DTOs, and annotations]
    E --> F[Build OpenAPI model]
    F --> G[GET /v3/api-docs or /v3/api-docs.yaml]
    G --> H[Maven/Gradle plugin saves artifact]
~~~

A successful application startup only proves that the ApplicationContext can be created. It does not prove that all expected operations were registered.

## 3. Common mistake: controllers active only in dev/prod profiles

Suppose a controller is annotated with a profile:

~~~java
@RestController
@RequestMapping("/api/orders")
@Profile({"dev", "production"})
class OrderController {

    @GetMapping
    List<OrderResponse> listOrders() {
        return List.of();
    }
}
~~~

When running with the dev or production profile, the controller is created. But when running:

~~~bash
java -jar app.jar --spring.profiles.active=openapi
~~~

the controller is not registered because the openapi profile does not match dev or production. Spring Boot may still start if no other bean depends on the controller. As a result, the /api/orders endpoint disappears from the OpenAPI document.

Do not place environment profiles on controllers merely to swap adapters or deployment settings. Unless there is a real requirement to hide the entire API in that environment, let controllers stay active in every profile that must serve the contract.

## 4. Separating API mapping profiles from infrastructure profiles

An easy-to-control way to organize this is to split profiles by responsibility:

- api-mappings: enables API controllers and routes.
- production-adapters: enables adapters connecting to real databases/services.
- export-adapters: enables safe adapters dedicated to the documentation-export step.
- openapi: composite profile used when exporting the document.

Declare profile groups in the profile-independent application.yml:

~~~yaml
spring:
  profiles:
    group:
      production:
        - api-mappings
        - production-adapters
      openapi:
        - api-mappings
        - export-adapters
~~~

When production is activated, Spring Boot activates both api-mappings and production-adapters. When openapi is activated, the application still registers API mappings while using export-adapters.

Profile groups are supported in modern Spring Boot versions, from the 2.4 line onward. In older versions, you can use spring.profiles.include in the base application.yml to include the required profiles. Do not put spring.profiles.active, spring.profiles.include, or spring.profiles.group inside application-openapi.yml or any configuration document activated only by a profile; these profile-control properties must reside in profile-independent configuration.

If controllers do not need a dedicated profile, omit @Profile on controllers altogether. Then the openapi group only needs to activate the right adapter profile.

## 5. Registering controllers under a mapping profile when truly needed

If the project actively manages mapping groups via profiles, controllers can use the api-mappings profile:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/orders")
@Profile("api-mappings")
class OrderController {

    private final OrderQuery orderQuery;

    OrderController(OrderQuery orderQuery) {
        this.orderQuery = orderQuery;
    }

    @GetMapping
    List<OrderResponse> listOrders() {
        return orderQuery.findAll();
    }
}
~~~

The openapi profile group already includes api-mappings, so the controller still appears in the ApplicationContext when the plugin starts the application.

If the project does not need to toggle entire groups of controllers on or off, do not add @Profile solely for export. Shared controllers reduce the risk of forgetting to activate a profile and ensure the contract is generated from the same mapping set across environments.

## 6. Satisfying controller dependencies with dedicated adapters

A common reason teams put @Profile on controllers is that the controller depends on a database or external service. When running the export profile, production infrastructure beans do not exist, causing constructor injection to fail.

Separate infrastructure-dependent logic behind an interface/port:

~~~java
import java.util.List;

interface OrderQuery {
    List<OrderResponse> findAll();
}
~~~

Production adapter:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("production-adapters")
class JpaOrderQueryAdapter implements OrderQuery {

    private final OrderRepository repository;

    JpaOrderQueryAdapter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public List<OrderResponse> findAll() {
        return repository.findAll().stream()
            .map(OrderResponse::from)
            .toList();
    }
}
~~~

Adapter used during documentation export:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
@Profile("export-adapters")
class ExportOrderQueryAdapter implements OrderQuery {

    @Override
    public List<OrderResponse> findAll() {
        return List.of();
    }
}
~~~

The controller is still created and its mappings are still registered. While springdoc reads metadata, it does not need to invoke business logic to list orders. The export adapter exists so the ApplicationContext has all required dependencies if controllers or configuration need them at startup.

If the endpoint is called in a smoke test, the adapter returns empty data or synthetic fixtures. Never connect to a production database and never return real user data in OpenAPI artifacts.

## 7. Preventing both adapters from being registered at the same time

With the profile group configuration above, production-adapters and export-adapters are two mutually exclusive profiles. This avoids having two beans implementing OrderQuery and triggering a NoUniqueBeanDefinitionException.

If the application has multiple active profiles simultaneously, check the conditions on each adapter. You can use @Primary when intentionally selecting a default implementation, but do not use @Primary to mask two poorly designed profiles.

Errors to check:

| Error | Cause |
| --- | --- |
| NoSuchBeanDefinitionException | The export profile excluded an adapter needed for constructor injection |
| NoUniqueBeanDefinitionException | Both production and export adapters are active |
| Controller missing | The controller's profile was not activated |
| Mapping exists but calling endpoint fails | The export adapter does not support smoke-test requests or dependent beans are incomplete |
| ApplicationContext starts slowly | The export profile is still calling a real database, broker, or remote service |

## 8. Dedicated springdoc configuration for the export profile

Create application-openapi.yml:

~~~yaml
spring:
  main:
    banner-mode: off

server:
  port: 9090

springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: false
~~~

In this profile:

- The API docs endpoint stays enabled so the build plugin can download JSON.
- Swagger UI is disabled because CI only needs the OpenAPI document.
- A dedicated port reduces the risk of conflicting with a locally running application.
- You can add export-adapter, timeout, or mock-endpoint settings.

The two springdoc properties serve distinct purposes:

| Property | Effect |
| --- | --- |
| springdoc.api-docs.enabled | Enables/disables the OpenAPI JSON/YAML endpoint |
| springdoc.swagger-ui.enabled | Enables/disables the Swagger UI interface |

If you set springdoc.api-docs.enabled=false in the export profile, the plugin will get a 404 when calling /v3/api-docs. Disabling Swagger UI does not remove the API docs endpoint.

If only API docs are needed, you can use the API starter matching your web stack such as springdoc-openapi-starter-webmvc-api or springdoc-openapi-starter-webflux-api. If the project already uses the UI starter, simply disable Swagger UI in the export profile.

## 9. Activating the profile from the launch command

You do not need to set openapi as the application's default profile. Activate it specifically in the export step:

~~~bash
java -jar target/application.jar --spring.profiles.active=openapi
~~~

Or via an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=openapi java -jar target/application.jar
~~~

In CI, this profile applies only to the process launched by the plugin. When the production application runs normally, it continues to use the profile specified by the deployment environment.

Do not put spring.profiles.active=openapi inside application-openapi.yml. Spring Boot only allows active/default/include/group properties in profile-independent configuration documents; application-openapi.yml is already activated by a profile, so it is not the place to activate that same profile itself.

## 10. Verifying mappings before exporting the file

Before configuring the plugin, verify that the openapi profile produces the right mappings. For Spring MVC, you can use MockMvc:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("openapi")
class OpenApiExportProfileTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exportsExpectedOrderOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/orders'].get").exists());
    }
}
~~~

This example assumes the API has a GET /api/orders operation and the OpenAPI endpoint uses the default path. If the project changes springdoc.api-docs.path, update the URL in the test. If the project uses Spring WebFlux, use WebTestClient to call the documentation endpoint and check the path similarly.

This test confirms the documentation is generated and the expected operation appears. Add assertions for key operations, security schemes, and response schemas that clients depend on.

## 11. Checking functional routes and springdoc filters

With WebFlux functional endpoints, RouterFunction beans must also be registered in the export profile. If a RouterFunction is created inside a @Configuration class annotated with @Profile("production"), the openapi profile will lack that route.

Beyond profiles, springdoc's filtering properties can also cause missing operations in the document:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /internal/**
~~~

Check package and path filters in application.yml, application-openapi.yml, and group configs. If a filter matches only a subset of routes, the document may be valid JSON yet omit part of the API that needs to be exported.

Distinguish two causes:

1. Mapping does not exist in Spring: check profiles, component scan, bean conditions, and RouterFunctions.
2. Mapping exists but is not included in OpenAPI: check packages-to-scan, paths-to-match, paths-to-exclude, @Hidden, and group configs.

## 12. Exporting JSON and YAML via HTTP endpoints

Once the application is running with the openapi profile, springdoc serves by default:

~~~text
JSON: http://localhost:9090/v3/api-docs
YAML: http://localhost:9090/v3/api-docs.yaml
~~~

You can download manually:

~~~bash
curl --fail --silent --show-error http://localhost:9090/v3/api-docs --output openapi.json

curl --fail --silent --show-error http://localhost:9090/v3/api-docs.yaml --output openapi.yaml
~~~

If springdoc.api-docs.path was changed, use the corresponding new URL. Only save the file after the response succeeds; curl with --fail returns an error code when the server responds with HTTP 4xx/5xx.

## 13. Exporting automatically with the springdoc Gradle plugin

The Gradle plugin starts the Spring Boot application, calls the OpenAPI endpoint, and saves the result to a file. The plugin requires the Spring Boot plugin along with the springdoc runtime dependency; since it only calls an HTTP endpoint, it does not depend directly on the springdoc library version. Pick a plugin version compatible with your Gradle and build setup.

Kotlin DSL example for Spring Boot 3:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("org.springdoc.openapi-gradle-plugin") version "2.0.0"
}

openApi {
    apiDocsUrl.set("http://localhost:9090/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("openapi.json")
    waitTimeInSeconds.set(60)

    customBootRun {
        args.set(
            listOf(
                "--spring.profiles.active=openapi",
                "--server.port=9090"
            )
        )
    }
}
~~~

Run:

~~~bash
./gradlew generateOpenApiDocs
~~~

Default output under the example configuration:

~~~text
build/openapi/openapi.json
~~~

customBootRun lets you start the application with a profile different from regular bootRun. Settings not overridden continue to inherit from bootRun, so check the JVM arguments, environment variables, and main class used by the build.

To export YAML, change the URL to end with .yaml and update the filename:

~~~kotlin
openApi {
    apiDocsUrl.set("http://localhost:9090/v3/api-docs.yaml")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("openapi.yaml")
    customBootRun {
        args.set(
            listOf(
                "--spring.profiles.active=openapi",
                "--server.port=9090"
            )
        )
    }
}
~~~

The plugin also supports requestHeaders for sending headers when the documentation endpoint requires authentication, and groupedApiMappings for downloading multiple groups into separate files. Do not put access tokens or secrets directly into build.gradle.kts; retrieve credentials from a CI secret store.

## 14. Exporting automatically with the springdoc Maven plugin

The Maven plugin works together with spring-boot-maven-plugin. The Spring Boot plugin starts the application before integration tests and stops it afterward; the springdoc plugin calls the API docs endpoint and writes the file.

Configuration example in pom.xml:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-maven-plugin</artifactId>
      <configuration>
        <jvmArguments>-Dspring.application.admin.enabled=true</jvmArguments>
        <arguments>
          <argument>--spring.profiles.active=openapi</argument>
          <argument>--server.port=9090</argument>
        </arguments>
      </configuration>
      <executions>
        <execution>
          <id>pre-integration-test</id>
          <goals>
            <goal>start</goal>
          </goals>
        </execution>
        <execution>
          <id>post-integration-test</id>
          <goals>
            <goal>stop</goal>
          </goals>
        </execution>
      </executions>
    </plugin>

    <plugin>
      <groupId>org.springdoc</groupId>
      <artifactId>springdoc-openapi-maven-plugin</artifactId>
      <version>1.6</version>
      <executions>
        <execution>
          <id>generate-openapi</id>
          <goals>
            <goal>generate</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <apiDocsUrl>http://localhost:9090/v3/api-docs</apiDocsUrl>
        <outputFileName>openapi.json</outputFileName>
        <outputDir>${project.build.directory}/openapi</outputDir>
        <failOnError>true</failOnError>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Run:

~~~bash
./mvnw verify
~~~

The file is written to target/openapi/openapi.json. failOnError should be enabled in CI; otherwise, some download or file-write failures are only logged and the build may continue even though no artifact was created.

To export YAML, change apiDocsUrl to /v3/api-docs.yaml and outputFileName to openapi.yaml:

~~~xml
<apiDocsUrl>http://localhost:9090/v3/api-docs.yaml</apiDocsUrl>
<outputFileName>openapi.yaml</outputFileName>
~~~

The Maven plugin also supports headers for calling authenticated endpoints and attachArtifact for attaching the file as a Maven artifact. Credentials must come from environment variables or a secret store, never committed to the POM.

If the build fails mid-phase, check whether the Spring Boot process was stopped. The plugin documentation notes that when a build fails, the stop goal may not execute; a lingering old application process could serve stale documentation to the next build.

## 15. The export profile must not accidentally use production configuration

The openapi profile should create an environment that can start up and accurately reflect the contract, without pulling in production secrets or side effects.

Safe options include:

- Repository adapters returning empty collections or synthetic fixtures.
- A mock server for remote APIs if the ApplicationContext requires those endpoints at startup.
- An in-memory database if startup strictly requires database schemas or metadata.
- Disabling schedulers, consumers, and background jobs unnecessary during export.
- Never sending emails, processing payments, or writing real data during startup.
- Configuring fixed timeouts and ports so the plugin can wait for the endpoint to become ready.

Do not disable Spring Security completely just so the plugin can call /v3/api-docs. If the docs endpoint is protected, configure appropriate permissions for the export profile or pass headers from a CI secret store. Do not let the export profile accidentally become a public configuration in production.

## 16. Validating the documentation endpoint in CI

After the plugin generates the file, the pipeline should check the artifact:

~~~bash
test -s build/openapi/openapi.json
jq -e '.openapi and .paths and (.paths | length > 0)' build/openapi/openapi.json
~~~

With Maven:

~~~bash
test -s target/openapi/openapi.json
jq -e '.openapi and .paths and (.paths | length > 0)' target/openapi/openapi.json
~~~

These assertions are only a baseline check: the file is non-empty, JSON parses, the OpenAPI version field exists, and there is at least one path. Add checks for critical operations to detect when a profile drops mappings.

Example:

~~~bash
jq -e '.paths["/api/orders"].get' build/openapi/openapi.json
jq -e '.components.schemas.OrderResponse' build/openapi/openapi.json
~~~

If the API has multiple groups, inspect each file generated from groupedApiMappings or each group URL of the Maven plugin.

## 17. Distinguishing startup failures from missing-mapping errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Application fails to start | Missing bean dependency in openapi profile | Create an export adapter or activate the required bean profile |
| Application runs but paths is empty | Controllers/RouterFunctions not registered | Check @Profile, @ConditionalOnProperty, and component scan |
| Only some controllers are missing | Controllers belong to another profile or lie outside scan packages | Check profile groups and packages-to-scan |
| Functional endpoints do not appear | RouterFunction bean not created | Check the @Profile on @Configuration and bean methods |
| Endpoints exist at runtime but not in docs | paths-to-match, paths-to-exclude, or @Hidden | Check springdoc filters and group configs |
| Plugin receives 404 | API docs endpoint disabled or wrong path/port | Check springdoc.api-docs.enabled, api-docs.path, and plugin URL |
| Plugin receives 401/403 | Security blocks the API docs endpoint | Grant CI permissions or pass valid headers |
| Stale file still appears | Plugin did not overwrite due to up-to-date task or old app running | Check task inputs, clean output, and stop old processes |
| Plugin times out | Slow application startup or waiting on external service | Increase wait/timeout prudently and use export adapters |
| Document differs from production | Export profile alters package/path filters or adapter metadata | Compare profile groups, springdoc filters, and OpenAPI customizers |

Do not check only HTTP 200 on /v3/api-docs. A valid document missing operations can still turn CI green if the pipeline lacks assertions on required paths.

## 18. Checking mappings in Spring MVC and WebFlux

With Spring MVC, inspect registered mappings via RequestMappingHandlerMapping or check the generated OpenAPI JSON. With WebFlux functional endpoints, verify that RouterFunction beans are created in the export profile.

A direct way to check the document is comparing against a list of required paths:

~~~json
{
  "requiredPaths": [
    "/api/orders",
    "/api/customers",
    "/api/payments"
  ]
}
~~~

This is an expected-paths list for the pipeline, not part of the OpenAPI document. CI can use a script or contract test to verify every path exists in the OpenAPI file.

If a controller has multiple HTTP methods, check specific methods. A path appearing only with GET does not mean POST/PUT/DELETE were also registered.

## 19. Keeping the contract consistent between export profile and runtime

The export profile may use different adapters, but components affecting the contract must remain consistent:

- Controllers and RouterFunctions.
- DTOs and Jackson serialization configuration.
- Validation constraints.
- Security schemes, scopes, and response metadata.
- Controller advice and error responses.
- springdoc packages/paths/group configuration.
- OpenAPI customizers and operation customizers.

If the export profile drops a ControllerAdvice or Jackson module, schemas/responses may differ from runtime. If the export profile uses a different OpenAPI customizer, the exported file may not reflect the documentation served in production.

Separate customizers that describe the contract from beans used solely for the UI. When profile-specific settings are needed, change only environment values such as public server URLs, never unintended schema or operation structures.

## 20. Recommended CI workflow

1. Choose compatible versions of Spring Boot, springdoc, and build plugins.
2. Define the openapi profile group in base configuration if extra mapping profiles need activation.
3. Keep controllers and RouterFunctions registered in the export profile.
4. Use safe adapters for databases, brokers, and external services.
5. Enable springdoc.api-docs.enabled and optionally disable springdoc.swagger-ui.enabled.
6. Launch the application with --spring.profiles.active=openapi.
7. Wait for the application to be ready, then call the JSON or YAML endpoint.
8. Save the file into target/build directory as a build artifact.
9. Verify the file is non-empty, parseable, and contains key paths/operations.
10. Run contract diffs and review changes before publishing or generating clients.
11. Stop the application process after export, even when the pipeline errors.

A good export profile makes documentation generation reproducible in CI while preserving accurate API mappings and schemas. When controllers/routes remain in the ApplicationContext and only infrastructure adapters are swapped, the OpenAPI document reflects the real contract without connecting to production or enabling Swagger UI during the build.

## References

- [Spring Boot 4.2 – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot 3.5 – Profiles](https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html)
- [springdoc-openapi v2 – Maven and Gradle plugins](https://springdoc.org/v2/)
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi Maven plugin – README and CI options](https://github.com/springdoc/springdoc-openapi-maven-plugin)
- [springdoc-openapi Gradle plugin – README and customBootRun](https://github.com/springdoc/springdoc-openapi-gradle-plugin)
- [Spring Framework – @Profile](https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles)
