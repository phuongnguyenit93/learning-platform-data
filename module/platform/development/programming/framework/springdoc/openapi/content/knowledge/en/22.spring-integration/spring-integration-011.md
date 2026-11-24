# Verifying Integration Features for Your Exact Springdoc Generation

`springdoc-openapi` integrates deeply with Spring Boot, Spring MVC, Spring WebFlux, Spring Security, Spring Data, and Swagger libraries. Consequently, a configuration that works in one generation may no longer work in another. Dependency artifacts, Java packages, auto-configuration mechanisms, and certain extension APIs have changed across major versions.

When verifying an integration feature, first identify which Spring Boot generation the application uses and which springdoc dependencies are actually loaded at runtime. Only then select the matching documentation, starters, imports, and configuration style. Reading only the version declared directly in the build file is insufficient because dependency management or transitive libraries may pull in another version.

This lesson presents a verification workflow from dependencies to runtime: choosing the right generation, checking Web MVC/WebFlux, aligning packages and APIs, verifying auto-configuration, testing OpenAPI/Swagger UI endpoints, and resolving common integration errors. The goal is confirming the feature operates on the application's exact Spring Boot and springdoc combination.

## 1. Why Must You Identify the Springdoc Generation?

`springdoc-openapi` evolves alongside major changes in Spring Boot and Spring Framework. Several changes directly affect source code:

- Spring Boot 3 migrated the Jakarta EE ecosystem from the `javax.*` namespace to `jakarta.*`.
- springdoc 2.x moved to starter artifacts and renamed several packages, classes, and interfaces.
- springdoc 3.x supports the Spring Boot 4 generation.
- Auto-configuration and managed dependencies can differ between version lines.

Using the wrong generation can prevent the application from compiling, starting, or generating documentation, or keep Swagger UI from loading the OpenAPI document. Some errors appear only at runtime due to incompatible versions on the classpath.

The right workflow starts from the actual Spring Boot version, then selects a compatible springdoc version. Do not pick springdoc solely from an Internet example because that example may target a different Boot line.

## 2. Compatibility Matrix by Spring Boot Version

According to the compatibility table in the official springdoc documentation at the time of writing:

| Spring Boot | springdoc generation | Notes |
|---|---|---|
| 4.1.x | 3.1.x to 3.2.x | springdoc 3.x is built for Spring Boot 4 |
| 4.0.x | 3.0.x | Use the matching 3.0.x line |
| 3.5.x | 2.8.x to 2.10.x | springdoc 2.x line |
| 3.4.x | 2.7.x to 2.8.x | springdoc 2.x line |
| 3.3.x | 2.6.x | springdoc 2.x line |
| 3.2.x | 2.3.x to 2.5.x | springdoc 2.x line |
| 3.1.x | 2.2.x | springdoc 2.x line |
| 3.0.x | 2.0.x to 2.1.x | springdoc 2.x line |
| 2.x and 1.x | 1.x | Final open-source release of 1.x is 1.8.0; check detailed matrix for older Boot versions |

This table reflects versions published as compatible by the project, not advice to upgrade Spring Boot solely to adopt newer springdoc releases. For stable running projects, choose the supported springdoc version for your current Boot line and review release changelogs before upgrading.

The matrix may change as Spring Boot or springdoc releases new versions. Always consult the matching documentation:

- Current documentation: https://springdoc.org/
- springdoc 2.x documentation: https://springdoc.org/v2/
- springdoc 1.x documentation: https://springdoc.org/v1/
- Repository and release notes: https://github.com/springdoc/springdoc-openapi

## 3. Determining the Actual Spring Boot Version

Inspect build files and dependency management before picking a starter.

With Maven, look up the version in the parent or dependency management:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
~~~

If the project imports the Spring Boot BOM instead of using the starter parent, check the version in `dependencyManagement`. If the version is supplied via a property, inspect the final resolved value after Maven resolution.

You can view the dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

With Gradle, check plugins and dependency management:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.5.16"
}
~~~

Then inspect resolved dependencies:

~~~bash
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
~~~

Do not check only the version written in the build file. Parent POMs, BOMs, version catalogs, plugins, or convention plugins may determine the actual version.

## 4. Identifying Web MVC vs. WebFlux

springdoc provides different starters depending on the web stack. Choosing the wrong starter can prevent auto-configuration from working as intended or pull both stacks onto the classpath.

| Application web stack | Starter with Swagger UI | OpenAPI-only starter |
|---|---|---|
| Spring MVC | `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webmvc-api` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |

For springdoc 2.x and 3.x, artifacts carry the `springdoc-openapi-starter-` prefix. For springdoc 1.x, legacy artifact names lacked the new starter structure, such as `springdoc-openapi-ui` for MVC and `springdoc-openapi-webflux-ui` for WebFlux.

MVC application example:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

WebFlux application example:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Versions in these examples only illustrate the springdoc 2.x line matching Spring Boot 3.5.x. If the application runs Spring Boot 4, use the springdoc 3.x line and verify the exact version against the current matrix.

Do not add both MVC and WebFlux starters just to experiment. First confirm whether the application actually uses `spring-boot-starter-web` or `spring-boot-starter-webflux`, then pick the matching starter.

## 5. Choosing the Right Artifact for Your Needs

Not every project needs the Swagger UI interface. If you only need JSON/YAML endpoints for pipelines to fetch the specification, use the API-only starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

If an interactive UI is needed, use the `-ui`-suffixed starter. The UI starter provides both the OpenAPI endpoints and Swagger UI.

Several integration modules such as Spring HATEOAS, Kotlin, Javadoc, Data REST, and Security have been consolidated or changed declaration styles across generations. Particularly in the 2.x line, migration docs state that several v1 modules were merged into `springdoc-openapi-starter-common`. Do not keep copying extra dependencies from v1 examples without checking v2/v3 documentation.

## 6. Package and Class Differences Between v1 and v2

When upgrading from springdoc 1.x to 2.x, several classes moved packages or changed names:

| springdoc 1.x | springdoc 2.x |
|---|---|
| `org.springdoc.core.SpringDocUtils` | `org.springdoc.core.utils.SpringDocUtils` |
| `org.springdoc.api.annotations.ParameterObject` | `org.springdoc.core.annotations.ParameterObject` |
| `org.springdoc.core.GroupedOpenApi` | `org.springdoc.core.models.GroupedOpenApi` |
| `org.springdoc.core.customizers.OpenApiCustomiser` | `org.springdoc.core.customizers.OpenApiCustomizer` |
| `org.springdoc.core.Constants` | `org.springdoc.core.utils.Constants` |
| `org.springdoc.core.SwaggerUiConfigParameters` | `org.springdoc.core.properties.SwaggerUiConfigParameters` |

An easily missed difference is that `OpenApiCustomiser` used British spelling in v1, whereas the interface in v2 is `OpenApiCustomizer`. When the compiler reports a missing symbol, check imports for the right generation instead of adding an old dependency to make the class appear.

Standard Swagger/OpenAPI annotations remain in this namespace:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
~~~

Do not confuse springdoc class package changes with the `io.swagger.v3.oas.annotations` package.

## 7. Namespace Differences Between javax and jakarta

Spring Boot 2 generally uses legacy Java EE APIs under the `javax.*` namespace. Spring Boot 3 and newer generations use Jakarta EE with the `jakarta.*` namespace.

Examples:

| API | Common in Spring Boot 2 | Spring Boot 3/4 |
|---|---|---|
| Validation | `javax.validation.Valid` | `jakarta.validation.Valid` |
| Constraint | `javax.validation.constraints.NotNull` | `jakarta.validation.constraints.NotNull` |
| Servlet | `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` |
| Persistence | `javax.persistence.Entity` | `jakarta.persistence.Entity` |

If upgrading from Boot 2 to Boot 3 while still using validation or servlet annotations from `javax.*`, newer libraries may fail to recognize metadata as expected. This is a namespace compatibility issue of the application and dependencies, not a springdoc-specific bug.

When verifying schema validation, confirm constraint imports come from the namespace matching your current Spring Boot version. If a DTO uses `jakarta.validation.constraints.NotNull` while the classpath only has the old API, the application may fail to compile or skip validation.

## 8. Inspecting the Dependency Tree and Version Conflicts

A project may declare springdoc 2.x while a transitive dependency pulls a v1 artifact into runtime. The result can be `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException`, or inconsistent behavior.

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
~~~

Check the following:

- Only a single springdoc generation exists on the runtime classpath.
- `org.springdoc` artifacts belong to the same compatible line.
- `swagger-core` and Swagger UI are not forced to incompatible versions.
- Both MVC and WebFlux starters are not pulled in unintentionally.
- Library versions already managed by the Spring Boot BOM are not explicitly overridden without a specific reason.
- No v1 artifacts remain after switching to v2/v3 starters.

When version conflicts occur, identify which dependency pulls in the older version and exclude it or upgrade the root dependency. Do not fix it by adding multiple JAR versions or declaring duplicate classes.

## 9. Verifying Auto-Configuration

springdoc uses Spring Boot auto-configuration to register beans, endpoints, and integrations. When dependencies are correct yet endpoints do not appear, check whether auto-configuration is loaded or excluded.

Start the application with the debug condition report:

~~~bash
java -jar app.jar --debug
~~~

Or add the corresponding flag when running the application in your IDE. Search for Springdoc-related condition reports and check:

- Was auto-configuration detected?
- Are classpath conditions satisfied?
- Is the application running MVC or WebFlux?
- Is any exclude configuration removing auto-configuration?
- Is a custom bean or configuration overriding default behavior?
- Are packages containing `@Configuration`, `@OpenAPIDefinition`, `@SecurityScheme`, and `GroupedOpenApi` covered by component scanning?

In newer Spring Boot generations, auto-configuration is declared through Spring Boot's dedicated import mechanism. Do not copy springdoc's internal configuration classes into your application. If integrating Spring Framework without Spring Boot, configuration differs and must follow the guide dedicated to non-Boot applications.

## 10. Checking Package Structure and Component Scanning

Springdoc needs to detect controllers, DTOs, annotations, and configuration beans. A common mistake is placing the application class in too deep a package, leaving controllers or configuration outside the component-scan scope.

Example of a scannable structure:

~~~text
com.example.store
├── StoreApplication.java
├── api
│   └── ProductController.java
├── dto
│   └── ProductResponse.java
└── config
    └── OpenApiConfiguration.java
~~~

`StoreApplication` should sit at an appropriate root package so subpackages are scanned. If you explicitly restrict `scanBasePackages`, ensure packages containing controllers and OpenAPI configuration are included.

If using `@Controller` instead of `@RestController`, methods need `@ResponseBody` or corresponding configuration to be treated as REST endpoints. A controller returning views may not be documented by springdoc as expected.

If using `GroupedOpenApi`, verify group beans are component-scanned and `pathsToMatch`/`packagesToScan` filters do not accidentally exclude endpoints.

## 11. Verifying Endpoints After Application Startup

With default configuration, common endpoints are:

| Endpoint | Purpose |
|---|---|
| `/v3/api-docs` | OpenAPI JSON |
| `/v3/api-docs.yaml` | OpenAPI YAML |
| `/v3/api-docs/{group}` | Group OpenAPI document |
| `/swagger-ui.html` | Swagger UI entry point |

Call them directly with curl:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/swagger-ui.html
~~~

Inspect status code, `Content-Type`, and body. A `200` response alone is not enough: `/v3/api-docs` must be valid OpenAPI JSON, not an HTML login page or a proxy error page.

If you changed `springdoc.api-docs.path`, `springdoc.swagger-ui.path`, context path, or management port, use the actual configured URLs. Do not conclude endpoints are missing merely because default paths failed.

## 12. Inspecting the OpenAPI Document Instead of Looking Only at Swagger UI

Swagger UI is a viewer and tester for the specification. When the UI fails to display, inspect the OpenAPI document directly to tell whether the bug is in document generation or the UI layer.

A minimal document should contain sections such as:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Store API",
    "version": "1.0.0"
  },
  "paths": {
    "/api/products": {
      "get": {
        "responses": {
          "200": {
            "description": "List of products."
          }
        }
      }
    }
  }
}
~~~

The actual OpenAPI version can be `3.0.x` or `3.1.x` depending on configuration and library version. Do not hardcode an assumption that every springdoc version emits the same `openapi` version.

Verify:

- `info.title` and `info.version` are accurate.
- `paths` contains the expected endpoints.
- HTTP methods and path parameters are accurate.
- Request bodies and responses have matching media types.
- Schemas are referenced properly.
- Security schemes and security requirements are present when needed.
- Group documents contain only endpoints belonging to that group.
- JSON and YAML reflect the exact same contract.

If JSON is valid while Swagger UI fails to render, focus on checking Swagger UI paths, spec URL, CORS, proxies, security, and UI configuration properties.

## 13. Checking Swagger UI and the OpenAPI URL

Swagger UI can use default endpoints or a custom specification URL. Commonly used properties include:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    url: /v3/api-docs
~~~

If the application uses multiple groups, configuring `springdoc.swagger-ui.urls` can provide a list of documents. Verify each group URL is reachable and returns valid JSON.

If the UI shows a failure to load the definition:

1. Open the OpenAPI JSON URL directly in the browser.
2. Confirm status code and `Content-Type`.
3. Verify the response is valid OpenAPI JSON.
4. Open Developer Tools and inspect Network/Console for failed requests.
5. Confirm the UI points to the right URL, context path, and group.
6. Check CORS if the UI and document have different origins.
7. Check whether Spring Security blocks or redirects document requests.

Do not modify OpenAPI contents just to mask a document-loading failure. First pinpoint which request failed and at which layer.

## 14. Checking Context Path and Reverse Proxy Configuration

In production, the application may run under a context path or behind a reverse proxy. Swagger UI needs to generate URLs matching the address seen by browsers.

For example, the application is published at:

~~~text
https://api.example.com/store
~~~

while the backend only receives internal requests at:

~~~text
http://store-service:8080
~~~

If forwarded headers are not processed properly, server URLs or spec fetch URLs can be generated with internal hosts. Check proxy configuration, context path, forwarded headers, and Spring Boot's `server.forward-headers-strategy` matching your infrastructure.

Trust forwarded headers only from trusted proxies. Do not enable trusting all headers from external clients if the application can be reached directly.

When changing context path or management port, check both Swagger UI and OpenAPI endpoints. One endpoint might work in the main application while failing exposure on the management port, or vice versa.

## 15. Checking Spring Security Integration

When Spring Security is enabled, `/v3/api-docs` or `/swagger-ui/**` resources may be protected. If the UI returns 401, 403, or redirects to login, that may be the security filter chain policy rather than a springdoc bug.

Check each separately:

- `/swagger-ui.html`
- `/swagger-ui/**`
- `/v3/api-docs`
- `/v3/api-docs.yaml`
- `/v3/api-docs/{group}`

If documentation requires login, configure rules for both document endpoints and UI resources. If allowing public access, intentionally apply `permitAll()` to the exact paths. Do not disable Spring Security globally just to make Swagger UI appear.

Ensure schemes in OpenAPI accurately describe the runtime mechanism. `@SecurityScheme` and `@SecurityRequirement` only describe the contract; they do not replace actual authentication and authorization configuration.

## 16. Checking Parameter Name Discovery

Some applications upgrading to Spring Boot 3.2 or later may see parameter names no longer inferred as before if bytecode does not retain parameter names. This can cause OpenAPI to display missing or unexpected parameter names.

With Maven Compiler Plugin, enable preserving parameter names:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

With Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

After changing configuration, clean and recompile so bytecode is regenerated. For public APIs, still declare `@PathVariable("id")`, `@RequestParam("page")`, or `@Parameter(name = "...")` explicitly when parameter names are an important part of the contract.

## 17. Checking HttpMessageConverter When Using Spring MVC

In Spring MVC, springdoc requires suitable message converters to return documentation. If the application overrides the `HttpMessageConverter` list, Swagger UI may fail to load or render the OpenAPI definition.

Springdoc documentation notes that when overriding Spring Boot's default converters, `ByteArrayHttpMessageConverter` must be preserved and registration order matters. For example:

~~~java
converters.add(new ByteArrayHttpMessageConverter());
converters.add(new MappingJackson2HttpMessageConverter(jacksonBuilder.build()));
~~~

This caveat applies to MVC applications customizing converters. Do not mechanically apply this snippet to WebFlux, because WebFlux uses different codecs. When encountering serialization or response-body errors, identify the active stack first and inspect the corresponding converters/codecs.

## 18. Checking API Changes When Upgrading Major Versions

When upgrading springdoc from 1.x to 2.x or 2.x to 3.x, do not merely bump the dependency version and wait for the build to pass. Review:

1. Were artifacts switched to the right starters?
2. Were package imports updated?
3. Was the Jakarta namespace updated if upgrading Spring Boot 2 to 3/4?
4. Do customizer beans, `GroupedOpenApi`, and `SpringDocUtils` use APIs of the target generation?
5. Are configuration properties still valid in the new version's docs?
6. Is auto-configuration discovered and not excluded?
7. Were integration modules replaced by the new starters/modules?
8. Did JSON/YAML change schemas or OpenAPI version?
9. Does Swagger UI work with current authentication and proxies?
10. Do contract tests catch unintended differences?

For major changes, create an upgrade branch and update dependencies and imports step by step. Save a pre-upgrade OpenAPI snapshot to compare against the post-upgrade output.

## 19. Verifying with Dependency and Integration Tests

A verification workflow should cover both build steps and running the application:

~~~text
Build file / BOM
      |
      v
Resolve dependency tree
      |
      v
Verify Boot + springdoc + web stack
      |
      v
Compile and start application
      |
      v
Check auto-configuration
      |
      v
Request JSON / YAML / Swagger UI
      |
      v
Validate paths, schemas, groups and security
      |
      v
Compare OpenAPI contract with previous release
~~~

Automate a smoke test verifying:

- The application starts cleanly.
- `/v3/api-docs` returns 200 and parses as JSON.
- `/v3/api-docs.yaml` returns valid YAML if enabled.
- Swagger UI returns HTML and loads the spec.
- Important groups are present.
- Key operations have paths, methods, and request/response schemas.
- Security schemes and requirements are not lost.
- No internal endpoints are unexpectedly exposed.

For MVC, use `MockMvc` or test against a real HTTP port. For WebFlux, use `WebTestClient`. If an issue occurs only behind a reverse proxy, add an integration test going through the public URL because in-process tests do not simulate the entire infrastructure.

## 20. Diagnosing Errors by Symptom

| Symptom | Cause to inspect | Resolution |
|---|---|---|
| Starter or artifact not found | Wrong artifact name for major version | Check v1, v2, or v3 starter names |
| `ClassNotFoundException` for springdoc classes | Import or dependency from another generation | Update packages and remove old dependencies |
| `NoSuchMethodError` | Version conflict between springdoc, swagger-core, or Spring | Inspect runtime dependency tree |
| `GroupedOpenApi` not found | Using v1 import in v2/v3 | Check package `org.springdoc.core.models` |
| `OpenApiCustomiser` not found | Using old interface name | For v2/v3 use `OpenApiCustomizer` |
| Validation annotations not reflected | Using `javax.validation` on Boot 3/4 or missing validation dependency | Check `jakarta.validation` and runtime |
| Missing `/v3/api-docs` endpoint | Wrong starter, excluded auto-configuration, or wrong web stack | Check classpath and condition report |
| Only some controllers missing | Wrong component scan, package filter, or group filter | Check packages and `GroupedOpenApi` |
| Swagger UI fails to load definition | Broken JSON endpoint, security, CORS, proxy, or wrong spec URL | Open JSON directly and check Network tab |
| Swagger UI fails to render after overriding converters | Missing or misordered ByteArray converter | Check MVC `HttpMessageConverter` setup |
| Missing parameter names | Compiler not retaining parameter names | Enable `-parameters`, declare names explicitly |
| Spec URL points to internal host | Wrong forwarded headers or context path | Configure proxy and forwarded-header strategy |
| Group does not appear | Group bean not scanned or filter mismatch | Check bean and group filter conditions |
| JSON is valid but Try it out fails | Security, CORS, server URL, or runtime API issue | Inspect actual requests from browser |

Do not resolve errors by blindly upgrading every dependency to the latest release. First find the exact root cause, consult the compatibility matrix, and upgrade to a supported combination.

## 21. Verification Workflow When Starting a Project

Follow in order:

1. Read the Spring Boot version from parent, BOM, or plugin.
2. Determine the Java version and MVC/WebFlux web stack.
3. Choose the springdoc major/minor version from the official compatibility matrix.
4. Pick the right UI or API-only starter.
5. Verify resolved artifacts in the runtime dependency tree.
6. Check package imports and `javax`/`jakarta` namespaces.
7. Start the application and inspect auto-configuration.
8. Call JSON/YAML endpoints directly.
9. Open Swagger UI and inspect Network/Console.
10. Verify groups, security, context path, and reverse proxy behavior.
11. Run integration tests to verify the contract.
12. Record the Boot version, springdoc version, starter, and test results in project documentation.

When upgrading, repeat this workflow and compare pre/post OpenAPI documents. This catches contract changes caused by dependencies or schema generation changes.

## 22. Key Takeaways

- Choose springdoc according to the Spring Boot generation, not merely the newest release.
- Boot 2.x uses the springdoc 1.x line; Boot 3.x uses the 2.x line; Boot 4.x uses the 3.x line.
- Boot 3/4 uses the Jakarta namespace; Boot 2 generally uses the Javax namespace.
- Choose the WebMVC or WebFlux starter matching your actual web stack.
- v2/v3 use starter artifacts and introduce package changes compared to v1.
- `GroupedOpenApi`, `SpringDocUtils`, and `OpenApiCustomizer` have different packages/APIs across generations.
- Check the runtime dependency tree to catch version conflicts.
- Check auto-configuration, component scanning, and group filters if endpoints or controllers are missing.
- Verify JSON/YAML independently before troubleshooting Swagger UI.
- When customizing `HttpMessageConverter`, keep required converters in the right order; WebFlux uses separate codecs.
- Verify parameter name discovery, context path, reverse proxy, and Spring Security.
- Automate smoke tests to ensure integration features keep working after every upgrade.

To verify integration features for the exact Springdoc generation in use, start from the application's Spring Boot, Java, and web stack combination. Pick the right springdoc major version, starter, and package APIs, then verify runtime dependencies, auto-configuration, JSON/YAML endpoints, and Swagger UI. Finally, use integration tests to prove the generated documentation matches the actual API.
