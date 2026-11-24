# Missing /v3/api-docs Endpoint Due to Wrong Starter or Disabled Configuration

In a Spring Boot application with springdoc-openapi, a request to /v3/api-docs may return 404, 401, 403, or be redirected to a login page. These outcomes have different causes. A 404 usually suggests that the documentation endpoint has not been registered, the requested URL is incorrect, or a proxy is not forwarding the request. 401 and 403 are usually related to Spring Security. If Swagger UI does not open but /v3/api-docs still returns JSON, the issue lies in the UI or static resources rather than the OpenAPI endpoint.

The diagnostic process should start with the web stack and dependency starter, then check enable/disable properties, custom paths, context path, and security. Do not conclude that springdoc is not working just because the Swagger UI button is missing: an API-only starter can still provide OpenAPI JSON/YAML without a UI.

## 1. Distinguishing Endpoint Errors from Swagger UI Errors

Springdoc provides two parts that can be used independently:

- The OpenAPI endpoint generates the JSON/YAML document, defaulting to /v3/api-docs and /v3/api-docs.yaml.
- Swagger UI provides a browser interface to view and try out operations. The interface is usually opened via /swagger-ui.html.

| Observed result | Meaning to check |
| --- | --- |
| /v3/api-docs returns 200 and valid JSON | The endpoint works. If the UI fails, check the UI starter, static resources, swagger-config, and security. |
| /v3/api-docs returns 404 | Check the starter, auto-configuration, enable/disable properties, custom path, context path, and proxy. |
| /v3/api-docs returns 401 | The endpoint may already be registered, but the request is unauthenticated. |
| /v3/api-docs returns 403 | The request reached the security layer, but the principal lacks authority or is blocked by policy. |
| Request receives 302 or 303 to the login page | Security is using form login or a redirect mechanism; check the Location header and authentication configuration. |
| /v3/api-docs returns 200 but paths is empty | The endpoint exists; check controller scanning, group filters, mappings, and @Hidden. |
| /swagger-ui.html fails but /v3/api-docs works | Check whether the *-api or *-ui starter is used, whether the UI is disabled, and the UI resource requests. |

A document with `paths: {}` is a different situation from a missing endpoint. In the first case, springdoc generated the document but found no operations matching the scan configuration or filters. In the second case, the documentation route may not be registered or may not be accessible at the URL being called.

## 2. Choosing the Starter by Web Stack

With Spring Boot 3 and springdoc 2.x, choose the starter that matches your application:

| Application architecture | With Swagger UI | OpenAPI JSON/YAML only |
| --- | --- | --- |
| Spring MVC / Servlet | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webmvc-api |
| Spring WebFlux / Reactive | springdoc-openapi-starter-webflux-ui | springdoc-openapi-starter-webflux-api |

Spring Boot 4 uses the springdoc 3.x line and its corresponding starters. Spring Boot 2 applications belong to the legacy springdoc 1.x line, using artifacts according to the v1 documentation instead of copying v2/v3 starter names. Always check the compatibility matrix for your exact Spring Boot line before choosing a version.

Maven example for a Spring MVC application on Spring Boot 3:

~~~xml
<properties>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

The example above uses webmvc-ui to provide both the OpenAPI endpoint and Swagger UI. If the application only needs the documentation endpoint, change the artifact to springdoc-openapi-starter-webmvc-api. There is no need to add a UI starter just to generate JSON.

With Spring WebFlux, use spring-boot-starter-webflux and the corresponding springdoc-openapi-starter-webflux-ui or springdoc-openapi-starter-webflux-api starter. Do not choose the MVC starter for a purely reactive application.

### 2.1. Common Mistakes When Declaring Dependencies

| Misconfiguration or suspect setup | Why it causes issues | How to fix |
| --- | --- | --- |
| WebFlux application with only the webmvc starter added | Auto-configuration does not match the running web stack | Use the appropriate webflux starter. |
| MVC application with the webflux starter added | May lack the expected MVC integration | Use the webmvc starter. |
| Using springdoc-openapi-starter-webmvc-ui for Boot 2 | Modern starters belong to the springdoc 2.x line, not Boot 2 | Use the legacy springdoc 1.x module compatible with Boot 2 or upgrade the platform as planned. |
| Using springdoc 1.x in Boot 3/4 | Wrong platform line and namespace | Boot 3 uses springdoc 2.x; Boot 4 uses springdoc 3.x. |
| Adding only Swagger annotations | Annotations describe the API but do not register springdoc endpoints | Add the appropriate springdoc starter. |
| Using a *-api starter while expecting Swagger UI | API-only starters do not provide the UI | Choose the *-ui starter if an interface is needed. |
| Adding both MVC UI and WebFlux UI | Pulls two integration stacks into the same application, causing redundant configuration or conflicts | Keep only the starter matching the actual web stack. |

Do not use the presence of @Operation or @Schema annotation classes as proof that the endpoint has been registered. These annotations are only processed by springdoc when the corresponding integration is present on the runtime classpath.

## 3. Verifying the Actual Web Application Type

Spring Boot can run as Servlet MVC or Reactive WebFlux. Check the underlying starter dependency:

~~~xml
<!-- Spring MVC application -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

~~~xml
<!-- Spring WebFlux application -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

If both spring-boot-starter-web and spring-boot-starter-webflux are on the classpath, Spring Boot usually selects MVC when both stacks are present. This can lead developers to think the application is running WebFlux just because the code uses Mono or Flux. Check the actual application context type and select the springdoc starter according to the stack activated by Boot.

The appearance of Mono or Flux in a controller does not by itself prove the application is running WebFlux. An MVC application can use reactive types in some layers while still running on the Servlet stack.

## 4. Verifying the Dependency Is on the Runtime Classpath

A dependency appearing in the build file is not guaranteed to be present at runtime. Check the dependency tree rather than only reading pom.xml or build.gradle.

With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc
./mvnw dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.springframework
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Confirm:

- The correct webmvc or webflux starter is present.
- The springdoc version belongs to a line compatible with the running Spring Boot version.
- The starter is in implementation or the appropriate runtime scope, not only in test scope.
- Both legacy artifacts and modern starters are not present simultaneously unless intentional.
- Required springdoc modules are not excluded by another dependency.
- Swagger Core or Spring modules are not overridden to an incompatible version.

If the dependency is only in testImplementation, tests may see springdoc while the production executable artifact does not. Move the starter into the application's runtime dependencies.

## 5. Checking Whether a Property Disables the OpenAPI Endpoint

The property controlling whether the OpenAPI endpoint is enabled is `springdoc.api-docs.enabled`. The default value is `true`. If configured as `false`, springdoc does not expose the API docs endpoint:

~~~yaml
springdoc:
  api-docs:
    enabled: false
~~~

To re-enable it:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

Check every configuration source that could override this value:

- application.yml or application.properties.
- Profile files such as application-prod.yml, application-staging.yml.
- Environment variables, for example SPRINGDOC_API_DOCS_ENABLED.
- JVM system properties, for example -Dspringdoc.api-docs.enabled=false.
- Command-line arguments, for example --springdoc.api-docs.enabled=false.
- Config server, Kubernetes ConfigMap/Secret, or external deployment configuration.

The final value is determined by Spring Boot's property source precedence. Do not just look in application.yml and conclude the property is not disabled; a production profile or environment may set a different value.

In environments where documentation is needed, the configuration can be set to:

~~~yaml
springdoc:
  api-docs:
    enabled: true
~~~

If production policy requires disabling OpenAPI, keeping `false` is an intentional decision. In that case, do not use opening Swagger UI as a way to verify the docs endpoint; verify in a profile where documentation is allowed to run.

## 6. Distinguishing api-docs.enabled from swagger-ui.enabled

These two properties control two different components:

| Property | Controls | Effect when false |
| --- | --- | --- |
| springdoc.api-docs.enabled | OpenAPI JSON/YAML endpoint | /v3/api-docs is not served. |
| springdoc.swagger-ui.enabled | Swagger UI | The UI is not served, though the OpenAPI endpoint may still work. |

Example disabling only the UI:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

In this configuration, /v3/api-docs can still return JSON. Do not enable Swagger UI just to fix an API docs error if the real cause is springdoc.api-docs.enabled=false or the wrong starter.

Conversely, if an API-only starter is used, having no UI is expected behavior. The JSON/YAML endpoint is still the part to inspect.

## 7. Checking for a Customized Path

The default endpoint is /v3/api-docs, but the following property can change the path: `springdoc.api-docs.path`.

For example:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
~~~

With this configuration, call /openapi instead of /v3/api-docs. The corresponding YAML is usually at /openapi.yaml. If the application has groups, documents are served under the new base path, for example /openapi/partner-v1.

Search for the `springdoc.api-docs.path` property across all profiles and configuration sources. If it has a custom value, calling /v3/api-docs can return 404 even when springdoc is working normally.

Do not confuse the document download path with the Swagger UI path:

- springdoc.api-docs.path changes the JSON/YAML URL.
- springdoc.swagger-ui.path changes the UI entry point URL.

Changing the UI path does not change the docs path. Changing the docs path also does not automatically change the controller business API mappings.

## 8. Checking Context Path and Reverse Proxy

A Servlet application may be placed under a context path:

~~~yaml
server:
  servlet:
    context-path: /store
~~~

In that case, the external access URL may be /store/v3/api-docs.

For a WebFlux application, the base path is usually configured via:

~~~yaml
spring:
  webflux:
    base-path: /store
~~~

If the application runs behind a reverse proxy or API gateway, the proxy may preserve, strip, or rewrite prefixes. Determine the actual strategy:

1. The proxy preserves the prefix when forwarding requests.
2. The proxy strips the prefix and forwards the shortened path.
3. The proxy rewrites both requests and response redirects.

Test the URL from a client through the public ingress, not just by calling backend localhost. If the proxy publishes under /store, the public request may be /store/v3/api-docs while the backend receives /v3/api-docs.

If springdoc needs to generate absolute URLs based on the public scheme/host/prefix, configure forwarded headers on the proxy and in Spring. Only trust forwarded headers set by a trusted proxy; do not allow arbitrary Internet requests to dictate the host or prefix reflected in the document.

## 9. Distinguishing 404 from 401, 403, and Spring Security Redirects

Spring Security can block documentation endpoints even when springdoc routes are registered:

| Status | Common cause | How to verify |
| --- | --- | --- |
| 401 Unauthorized | Not logged in or token missing/invalid | Send valid credentials and inspect the authentication entry point. |
| 403 Forbidden | Authenticated but lacking authority/scope or blocked by policy | Check authorization rules and the principal's authorities. |
| 302 Found or 303 See Other | Form login redirecting to the login page | Inspect the Location header and login configuration. |
| 404 Not Found | Route does not exist at the requested path, rewritten wrongly by proxy, or excluded by config | Check mappings, properties, context path, and gateway. |
| 200 OK but body is HTML | May have received a login/fallback page instead of OpenAPI JSON | Check Content-Type and the actual response body. |

Example rule for an environment where reading documentation is permitted:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasAuthority("docs.read")
    .anyRequest().authenticated()
);
~~~

This is only an illustrative rule snippet to merge into an existing SecurityFilterChain. If the documentation endpoint needs to be public in a dev environment, access can be configured according to that environment's policy. For internal documentation, keep authentication and grant the authority to the API registry or developers. Do not open up the entire application just to make /v3/api-docs return 200.

When changing `springdoc.api-docs.path`, update the security matchers accordingly. In particular, the YAML URL such as /v3/api-docs.yaml is a sibling of the base path; the pattern `/v3/api-docs/**` may not cover it. Check JSON, YAML, groups, and swagger-config.

## 10. Layered Verification with curl

Call the default endpoint directly:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Check YAML:

~~~bash
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

If the path has been customized:

~~~bash
curl -i http://localhost:8080/openapi
~~~

If the application has a context path:

~~~bash
curl -i http://localhost:8080/store/v3/api-docs
~~~

If the endpoint requires authentication:

~~~bash
curl -i \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  http://localhost:8080/v3/api-docs
~~~

Replace `ACCESS_TOKEN` with a valid test token for your environment. Do not record real tokens in scripts, shared logs, or documentation. Read the status, Content-Type, Location, and response body; a 200 status with content type text/html is not an OpenAPI JSON document.

## 11. Checking Runtime Configuration and Startup Logs

When dependencies and properties appear correct but the endpoint still does not appear:

1. Restart the application after changing dependencies or configuration. Editing the build file does not automatically update a running process.
2. Check startup logs to confirm the application context started successfully without bean creation or auto-configuration errors.
3. Enable targeted verbose logging for the springdoc package in a development environment:

~~~yaml
logging:
  level:
    org.springdoc: DEBUG
~~~

4. Run the application with `--debug` to view Spring Boot's condition evaluation report when you need to determine why auto-configuration was not activated.
5. If Actuator mappings are already exposed and securely protected in an internal environment, check /actuator/mappings to find the API docs handler. Do not expose mappings publicly just for diagnostics.

Not every springdoc release writes a single log line stating the endpoint has been registered. Use logs alongside the dependency tree, runtime properties, and actual requests to isolate the issue.

## 12. Checking Excluded or Conflicting Dependencies

If the starter is in the build file but the endpoint does not appear, the dependency may be excluded or overridden by an incompatible version.

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
./mvnw help:effective-pom
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
~~~

Look for these situations:

- Both springdoc 1.x and 2.x/3.x are present.
- Both MVC and WebFlux starters are used even though the application only runs one stack.
- The springdoc dependency is declared in test scope instead of runtime.
- An exclusion removes the auto-configuration or core module.
- Another dependency forces Swagger Core/Jackson/Spring Framework to an incompatible version.
- The old `springdoc-openapi-ui` artifact is still used in an application that migrated to modern starters.

Do not manually add every Swagger module to compensate for missing dependencies. First identify which artifacts the starter pulls in, which versions are resolved, and which dependency path causes the conflict.

## 13. Distinguishing a Missing Endpoint from an Empty Document

If /v3/api-docs returns 200 with empty `paths`, springdoc is already serving the endpoint. In that case, check:

- Whether the controller is registered as a Spring bean.
- Whether the mapping is actually a request mapping recognized by Spring MVC/WebFlux.
- Whether `springdoc.packages-to-scan` or `springdoc.paths-to-match` filters out the controller.
- Whether the group being called has appropriate `packagesToScan`, `pathsToMatch`, or `pathsToExclude`.
- Whether the operation/controller is annotated with `@Hidden`.
- Whether the endpoint is in the management context or another group.

Example of a package filter that is too narrow:

~~~yaml
springdoc:
  packages-to-scan: com.example.publicapi
~~~

If the actual controller resides in `com.example.api.orders`, it may not be included in the document. Broaden or fix the package filter to match the application's actual structure. Controller filtering should not be used to fix a 404 docs endpoint; it only controls which operations appear in the document.

## 14. Minimal Configuration Example to Restore the OpenAPI Endpoint

For a Spring MVC application on Spring Boot 3 and springdoc 2.x, a minimal configuration can be:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: false
~~~

An API-only starter is sufficient for OpenAPI JSON/YAML. `swagger-ui.enabled=false` in this example only disables the UI, not the documentation endpoint. Version 2.10.0 is an example for the Boot 3.5.x line; choose a version matching your actual application's compatibility matrix.

If Swagger UI is needed, switch the dependency to `springdoc-openapi-starter-webmvc-ui` and set `springdoc.swagger-ui.enabled: true` or omit the property to use the default. For WebFlux, switch to the corresponding WebFlux starter.

## 15. Testing the Endpoint After Fixing

A simple integration test can verify that the endpoint returns JSON and contains the OpenAPI fields:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiEndpointAvailabilityTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void servesOpenApiDocument() throws Exception {
        String body = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode document = objectMapper.readTree(body);
        assertThat(document.path("openapi").asText()).startsWith("3.");
        assertThat(document.path("info").isObject()).isTrue();
        assertThat(document.path("paths").isObject()).isTrue();
    }
}
~~~

This example assumes the docs endpoint is not blocked by security in tests. If the application protects the document, add appropriate authentication and authorities. If `springdoc.api-docs.path` was changed, update the URL in the test to match the configuration. For WebFlux applications, use `WebTestClient` instead of `MockMvc`.

This test confirms that the document exists and has the basic structure. To verify that actual APIs are published, add assertions for a specific path and operationId. To verify Swagger UI, test the UI endpoint and the resources/config loaded separately by the browser.

## 16. Common Errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| /v3/api-docs returns 404 right after adding dependency | Starter does not match web stack or is missing at runtime | Choose the right webmvc/webflux starter and check the runtime dependency tree. |
| /v3/api-docs returns 404 only in production | Profile, environment, or ConfigMap disables docs; context path/proxy differs from local | Check runtime properties and the public URL through ingress. |
| /v3/api-docs is disabled even though local YAML sets true | A higher-precedence property source overrides it to false | Check command line, JVM, env, profiles, and config server. |
| /v3/api-docs returns 401/403 | Spring Security blocks the request | Check authentication, authorities, and docs matchers. |
| /v3/api-docs redirects to login | Security uses form login | Check Location and authenticate according to policy. |
| /v3/api-docs works but UI is missing | Using *-api starter or UI is disabled | Use *-ui starter and check swagger-ui.enabled. |
| UI opens but reports failed to load definition | swagger-config points to old URL, CORS, security, or proxy rewrite | Check the Network tab and requests to JSON/YAML. |
| Calling /v3/api-docs returns 404 but /openapi works | springdoc.api-docs.path was changed | Use the custom endpoint and update consumers. |
| Only group endpoint works | Calling a group URL, or the default document is not configured as expected | Check group id and docs base path. |
| Endpoint returns 200 but paths is empty | Package/path filter or controller scanning does not match | Check packages, path filters, mappings, and @Hidden. |
| Works locally but proxy returns 404 | Prefix stripped/preserved wrongly or proxy does not route docs path | Check rewrites, forwarded prefix, and public URL. |
| API docs work in tests but not in production | Dependency is only in test scope or profiles differ | Check the runtime artifact and effective configuration. |

## 17. Diagnostic Checklist

Follow these steps in order:

1. Call /v3/api-docs directly and record status, Content-Type, Location, and body.
2. Determine whether the application runs MVC or WebFlux.
3. Confirm the springdoc starter matches the web stack and is on the runtime classpath.
4. Confirm the springdoc version is compatible with Spring Boot.
5. Check `springdoc.api-docs.enabled` in runtime configuration, not only in local files.
6. Check whether `springdoc.api-docs.path` has been customized.
7. Check Servlet context path or WebFlux base path.
8. Check whether a proxy/gateway rewrites prefixes and routes the docs endpoint.
9. Distinguish 404 from 401, 403, and Spring Security redirects.
10. If JSON returns 200 with empty paths, check package/path filters and `@Hidden`.
11. If only the UI fails, check the `*-ui` starter, `swagger-ui.enabled`, `swagger-config`, and static resources.
12. Check the dependency tree and startup logs when the cause is still unclear.
13. Run an integration test for JSON and YAML after fixing.

## 18. Guiding Principles

- Choose the starter matching the actual web stack: MVC or WebFlux.
- Distinguish API-only starters from starters with Swagger UI.
- Use the right springdoc line for the running Spring Boot generation.
- Check `springdoc.api-docs.enabled` and overriding property sources.
- Check `springdoc.api-docs.path` before concluding the default URL is lost.
- Separate endpoint errors from Swagger UI errors and security errors.
- Read status, content type, redirects, and response body instead of only looking at the browser page.
- Check context path, reverse proxy, and runtime dependency tree.
- Only investigate package/path filters when the endpoint returns a document but is missing operations.
- Add integration tests so JSON/YAML endpoints keep working after upgrades.

When /v3/api-docs does not appear, determine which URL the request is hitting, which web stack the application runs, and which springdoc starter is present at runtime. Then check enable/disable properties, custom paths, context path, proxy, and Spring Security. If the endpoint already returns a document without operations, move on to checking controller scanning and filters. Separating these layers helps fix the root cause without loosening access permissions or adding unnecessary dependencies.

## References

- [Springdoc OpenAPI – Getting Started](https://springdoc.org/)
- [Springdoc OpenAPI – FAQ](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [Springdoc OpenAPI v2 – Getting Started](https://springdoc.org/v2/getting-started.html)
- [Spring Boot – Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
