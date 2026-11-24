# Migrating Artifacts and Packages from Springdoc v1 to v2

Springdoc-openapi v2 is the release line for Spring Boot 3 and the Spring Framework 6/Jakarta EE ecosystem. When upgrading from Springdoc v1, the primary tasks are replacing old artifacts with v2 starters, updating several Java packages, handling Spring Boot 3's javax-to-jakarta changes, and re-verifying the OpenAPI document after building.

Do not treat the migration as simply bumping a dependency version number. v1 is typically used in Spring Boot 1/2 applications; v2 is built for Spring Boot 3 and newer. If a project still runs Spring Boot 2, keep the compatible Springdoc v1 line instead of placing v2 starters on the classpath. If upgrading both Spring Boot and Springdoc, handle the platform changes under a single controlled plan.

## 1. Understand compatibility boundaries between v1 and v2

| Component | Springdoc v1 | Springdoc v2 |
|---|---|---|
| Spring Boot platform | Spring Boot 1/2 line, depending on Springdoc version | Spring Boot 3 and newer |
| Spring Framework | Spring Framework 5 in common Boot 2 setups | Spring Framework 6 |
| Java | Depends on the Spring Boot v1 version in use | Spring Boot 3 requires Java 17 or newer |
| Jakarta namespace | Primarily javax APIs on Boot 2 platforms | Jakarta APIs use the jakarta namespace |
| MVC/UI integration artifact | Typically springdoc-openapi-ui | Uses springdoc-openapi-starter-webmvc-ui |
| WebFlux/UI integration artifact | Typically springdoc-openapi-webflux-ui | Uses springdoc-openapi-starter-webflux-ui |
| API without Swagger UI | Uses matching v1 core/API module | Uses starter-webmvc-api or starter-webflux-api |
| GroupedOpenApi | org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |

Springdoc v2 is not a drop-in replacement for every Spring Boot 2 application. Before swapping dependencies, determine the project's Spring Boot version, Java version, and web stack. If the project cannot upgrade to Boot 3 yet, select a v1 version compatible with the current Boot line and plan the platform upgrade separately.

## 2. Audit the platform before upgrading

Record the following details before making changes:

- Spring Boot version in the parent, plugin, or version catalog.
- Java version used for compiling, testing, and running production.
- Whether the project uses Spring MVC or Spring WebFlux.
- Whether the project needs Swagger UI or only OpenAPI JSON/YAML.
- Springdoc modules currently in use, including support modules such as security, data-rest, or Kotlin.
- org.springdoc packages imported in source code.
- Swagger 2 or OpenAPI 3 annotations in use.
- Third-party libraries depending on Springfox, Swagger Core, or javax.

For Maven, check the parent and version-management properties in pom.xml. For Gradle projects, inspect the Spring Boot plugin, version catalog, convention plugins, and dependency constraints. Do not infer the actual version from a single file if versions are managed elsewhere.

## 3. Map UI artifacts from v1 to v2

For a Spring MVC application needing Swagger UI, replace the v1 dependency:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.x.y</version>
</dependency>
~~~

with the v2 starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

For a WebFlux application needing Swagger UI, use the starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

The values 1.x.y and 2.x.y are illustrative placeholders. Replace them with versions verified compatible with your project's Spring Boot and Java versions.

The artifact name indicates the web stack. Do not use the WebMVC starter for a pure WebFlux application or vice versa. If both spring-boot-starter-web and spring-boot-starter-webflux appear on the classpath, Spring Boot chooses the web application type based on classpath conditions; verify the application's actual web stack before picking the Springdoc starter.

## 4. Choose the API starter when Swagger UI is not needed

If you only need OpenAPI JSON/YAML endpoints for pipelines or external tools to fetch, there is no need to pull in Swagger UI assets.

Spring MVC API-only:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Spring WebFlux API-only:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-api</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Pick one starter matching your stack and purpose. The UI starter already includes the required API components for its stack; do not add both the UI starter and the API starter for the same stack just to be safe.

## 5. Update dependencies in Maven

You can declare the Springdoc version in pom.xml:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.x.y</version>
    </dependency>
</dependencies>
~~~

Replace 2.x.y with the v2 version verified compatible with your Spring Boot version. If your organization manages versions via Spring Boot dependency management or an internal Maven BOM, follow project conventions. Do not declare conflicting versions in multiple places that cause dependency mediation to pick an unexpected version.

After editing, run:

~~~bash
mvn -U clean test
~~~

If the project uses the Maven Wrapper, prefer mvnw or mvnw.cmd depending on the OS to keep the same Maven version in CI and on developer machines.

## 6. Update dependencies in Gradle

With Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.y")
}
~~~

With Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation "org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.y"
}
~~~

Manage versions in the version catalog, convention plugin, or gradle.properties per project structure. For WebFlux applications, swap the artifact to springdoc-openapi-starter-webflux-ui; if UI is not needed, use the matching API starter.

After updating:

~~~bash
./gradlew clean test
~~~

If the project uses the wrapper on Windows, run gradlew.bat clean test.

## 7. Remove v1 artifacts to prevent duplicate classpaths

Once switched to v2 starters, audit and remove unnecessary v1 artifacts, such as:

- springdoc-openapi-ui
- springdoc-openapi-webmvc-core
- springdoc-openapi-webflux-ui
- springdoc-openapi-webflux-core
- Springdoc v1 modules declared directly or pulled in transitively.

The list above covers common artifacts, not an exhaustive list for every project. Rely on the dependency tree to identify actual artifacts.

Do not keep both v2 starters and v1 core modules on the same classpath. Mixing two major versions can cause class loading errors, incompatible method signatures, duplicate auto-configuration, or inconsistent generated documents.

Do not delete an add-on module based solely on its name. Identify the functionality it provides and locate the matching module/starter in the v2 line using the documentation for the target version.

## 8. Move the GroupedOpenApi package

A common source-level change is the GroupedOpenApi package.

V1:

~~~java
import org.springdoc.core.GroupedOpenApi;
~~~

V2:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
~~~

Example group configuration after migration:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .pathsToExclude("/api/internal/**")
                .build();
    }
}
~~~

Familiar builder methods such as group, pathsToMatch, and pathsToExclude remain the standard way to configure groups. After updating imports, re-check filters to confirm the operation set in each document has not changed unexpectedly.

## 9. Migrate OpenApiCustomiser to OpenApiCustomizer

In v1, the interface used British spelling as OpenApiCustomiser. In v2, the interface name uses OpenApiCustomizer.

V1:

~~~java
import org.springdoc.core.customizers.OpenApiCustomiser;

@Bean
OpenApiCustomiser addDescription() {
    return openApi ->
            openApi.getInfo().setDescription("API Documentation");
}
~~~

V2:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;

@Bean
OpenApiCustomizer addDescription() {
    return openApi ->
            openApi.getInfo().setDescription("API Documentation");
}
~~~

This is a type name and import change. Customizer logic should still be re-tested because a customizer can apply to the default document or groups depending on the bean type and configuration. If the application has multiple groups, verify all documents receive the expected customizations.

## 10. Review OperationCustomizer and other customizers

Projects may also use:

- OperationCustomizer to customize individual operations.
- GlobalOpenApiCustomizer to apply shared changes across OpenAPI documents.
- OpenApiCustomizer to customize a document according to configuration scope.
- Custom application-specific filter or customizer beans.

Do not guess renames or packages for every customizer. Locate each org.springdoc import, inspect compiler errors after upgrading dependencies, and cross-check the API of your chosen v2 version. Some types kept their names, while some types or packages changed.

Example illustrating an operation customizer:

~~~java
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OperationCustomizationConfiguration {

    @Bean
    OperationCustomizer addOperationDescription() {
        return (operation, handlerMethod) -> {
            if (operation.getDescription() == null) {
                operation.setDescription("Operation exposed by the application.");
            }
            return operation;
        };
    }
}
~~~

When migrating existing customizers, preserve applicability conditions, execution order, and group scope. Do not replace a global customizer with one scoped to a single group if the contract relies on shared metadata.

## 11. Keep OpenAPI 3 annotation packages unchanged

Common Swagger Core OpenAPI 3 annotations still reside in the io.swagger.v3.oas.annotations package, for example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
~~~

Annotations such as Operation, Parameter, Schema, ApiResponse, Tag, Hidden, and OpenAPIDefinition do not move to org.springdoc simply because Springdoc is upgraded from v1 to v2.

Distinguish these OpenAPI 3 annotations from old Swagger 2 annotations in io.swagger.annotations, such as Api, ApiOperation, ApiModel, and ApiModelProperty. If the project still has Swagger 2 annotations, perform a separate migration to OpenAPI 3 annotations; swapping starters does not convert them automatically.

## 12. Handle javax to jakarta when upgrading to Spring Boot 3

Spring Boot 3 and Spring Framework 6 moved Jakarta EE APIs to the jakarta namespace. This is a platform change, not a Springdoc-specific change.

Packages commonly needing conversion:

| Before (Boot 2) | After (Boot 3) |
|---|---|
| javax.validation.* | jakarta.validation.* |
| javax.servlet.* | jakarta.servlet.* |
| javax.persistence.* | jakarta.persistence.* |

Validation example:

~~~java
// Before
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;

// After
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
~~~

Do not replace every occurrence of javax mechanically. Some packages belong to Java SE and remain javax, such as javax.sql and javax.crypto. Only convert APIs whose namespace moved in Jakarta EE; check dependencies and documentation for each library.

Third-party libraries that still release only javax builds may be incompatible with Spring Boot 3. Upgrade or replace those libraries with Jakarta-compatible releases before concluding an error belongs to Springdoc.

## 13. Check application properties configuration

Common Springdoc properties from v1 continue under matching names in v2, for example:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
~~~

Do not change every property just because the major version increased. However, confirm each property is supported in the documentation for your exact v2 release, especially if the project uses less common properties, custom paths, groups, caching, OAuth, or advanced Swagger UI settings.

After migration, check default URLs:

- /v3/api-docs for OpenAPI JSON.
- /v3/api-docs.yaml for OpenAPI YAML.
- /swagger-ui.html or the configured Swagger UI path.

If there is a context path or reverse proxy, check public URLs and forwarded headers per the application's deployment configuration.

## 14. Migrate group configuration and documentation endpoints

If the project uses GroupedOpenApi, confirm group endpoints still work after updating packages. For example, a group named public is typically accessed at:

~~~text
/v3/api-docs/public
/v3/api-docs.yaml/public
~~~

Verify:

- Group names remain unchanged.
- pathsToMatch and pathsToExclude are accurate.
- Package filters still select the expected controllers.
- Operations are neither missing nor unexpectedly duplicated across multiple groups.
- Customizers apply to the intended groups.
- Security rules for group endpoints remain appropriate.

An import error can prevent group beans from being created or stop the application context from starting. A filter mistake can let the application start cleanly while producing an empty group document or missing operations.

## 15. Handle additional modules

Beyond the MVC/WebFlux starters, a project may use Springdoc integrations such as Spring Data REST, HATEOAS, security, Kotlin, or specialized components. When moving to v2:

1. List each v1 artifact currently declared.
2. Identify the capability that module provides.
3. Locate the corresponding module/starter in the v2 line.
4. Check the compatibility matrix against Spring Boot and Java.
5. Keep only the single Swagger Core version aligned with the starter.
6. Run tests for add-on features, not just the default docs endpoint.

Do not guess v2 artifact names simply by prepending starter to old names. Module layout was reorganized; verify the module list in the corresponding release documentation.

## 16. Inspect the dependency tree and version conflicts

After swapping starters, check the dependency tree to catch legacy artifacts still pulled in.

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
~~~

Verify:

- Only one Springdoc major line exists on the runtime classpath.
- No unintended Springfox or Springdoc v1 starters remain.
- Swagger Core and Swagger annotations use a compatible version set.
- No legacy library pulls in javax APIs conflicting with Jakarta.
- No transitive dependency is overridden with an arbitrary version without verifying compatibility.

Do not manually add swagger-core, swagger-annotations, or swagger-annotations-jakarta just to silence compile errors when the starter already manages them. First identify which dependency is missing or conflicting.

## 17. Search and update imports across source code

You can search for old packages in source code:

~~~bash
rg -n "org\.springdoc\.core\.GroupedOpenApi|OpenApiCustomiser|io\.swagger\.annotations|javax\.validation|javax\.servlet|javax\.persistence" .
~~~

Then categorize the findings:

| Search match | Action required |
|---|---|
| org.springdoc.core.GroupedOpenApi | Change to org.springdoc.core.models.GroupedOpenApi |
| OpenApiCustomiser | Inspect and change to OpenApiCustomizer in the matching v2 package |
| io.swagger.annotations.* | Migrate Swagger 2 annotations to OpenAPI 3 if still used |
| javax.validation.* | Migrate to jakarta.validation.* when upgrading to Boot 3 |
| javax.servlet.* | Migrate to jakarta.servlet.* when upgrading to Boot 3 |
| javax.persistence.* | Migrate to jakarta.persistence.* when upgrading to Boot 3 |

Do not run blind bulk replacements across all files without inspecting context. For example, javax.sql.DataSource does not change to jakarta.sql.DataSource; the javax.sql package belongs to Java SE.

## 18. Example OpenAPI configuration after migration

A simple v2 configuration can use GroupedOpenApi and OpenApiCustomizer:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/api/**")
                .build();
    }

    @Bean
    OpenApiCustomizer customizeOpenApiInfo() {
        return openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info());
            }
            openApi.getInfo()
                    .description("Public API documentation for the application.");
        };
    }
}
~~~

This snippet illustrates the primary v2 package imports. If a customizer must apply across all groups, pick the global interface/bean appropriate for your version and check the output of each group.

## 19. Verify after building

Once the source compiles:

~~~bash
mvn clean verify
~~~

Or:

~~~bash
./gradlew clean check
~~~

Start the application and check the JSON endpoint:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi-v2.json
~~~

Check YAML:

~~~bash
curl -fS http://localhost:8080/v3/api-docs.yaml -o openapi-v2.yaml
~~~

Verify the document parses cleanly:

~~~bash
jq -e '.openapi and .info and .paths' openapi-v2.json
~~~

Then open Swagger UI if the UI starter is used. If using only the API starter, do not expect /swagger-ui.html to work.

## 20. Compare contracts before and after migration

Upgrading a major version can alter how springdoc detects controllers, infers schemas, or applies customizers. Save the v1 OpenAPI JSON as a baseline before migrating and compare it against the v2 document.

Check:

- Path list and HTTP methods.
- operationId, summary, and description.
- Path, query, header, and cookie parameters.
- Request body, required flags, and media types.
- Response statuses, headers, and content types.
- Component schemas, $ref, enums, and nullability.
- Security schemes and security requirements.
- Group membership and document groups.
- servers, tags, and external documentation.

Use an OpenAPI-aware diff tool rather than byte-by-byte text comparison. Differences in key ordering or formatting do not alter the contract; conversely, losing a response or changing a required field can be a breaking change even if the file differs by only a few lines.

## 21. Check security and Swagger UI

After swapping starters, re-check the security chain for documentation endpoints:

- /v3/api-docs and /v3/api-docs/**
- /v3/api-docs.yaml and group YAML endpoints if enabled.
- /swagger-ui.html.
- /swagger-ui/** static assets.

v2 starters do not decide who is allowed to read documentation. If the project previously used Spring Security to permit or protect docs, verify matchers still match the actual paths.

If Swagger UI loads the page without showing operations, inspect requests to /v3/api-docs/swagger-config and the spec URL in the browser Network tab. If API docs work while UI returns 404, verify the project has the UI starter rather than the API-only starter.

## 22. Common errors when migrating v1 to v2

| Symptom | Possible cause | Resolution |
|---|---|---|
| Maven/Gradle fails to resolve artifact | Still using v1 artifact name or wrong repository/version | Switch to the v2 starter matching your web stack and check repositories |
| Spring Boot 2 fails to start with v2 starter | Springdoc v2 targets Spring Boot 3+ | Stay on compatible Springdoc v1 or upgrade the platform |
| GroupedOpenApi not found | Importing v1 package | Use org.springdoc.core.models.GroupedOpenApi |
| OpenApiCustomiser not found | Interface spelling/name changed | Use OpenApiCustomizer per the v2 API |
| javax/jakarta errors | Dependencies or source still use old namespace | Migrate Jakarta APIs and upgrade third-party libraries |
| NoSuchMethodError or ClassNotFoundException | Mixing v1/v2 modules or incompatible Swagger Core | Check dependency tree and eliminate version conflicts |
| Swagger UI 404 while JSON works | Using API-only starter or proxy not routing UI assets | Use the UI starter if needed or update proxy rules |
| API docs 404 | API docs disabled, wrong path, or wrong stack starter | Check properties, context path, and starter |
| Group document empty | Filters or package scanning changed | Check GroupedOpenApi and match criteria |
| Customizer has no effect on groups | Bean scope differs from expectations | Pick the right global customizer and test each group |
| Schema differs after migration | Differences in introspection, Jakarta validation, or Jackson | Compare OpenAPI JSON and test runtime payloads |
| UI opens but spec request returns 401/403 | Security matchers or auth config no longer match | Check filter chain and docs access rules |

## 23. Step-by-step migration workflow

1. Lock down the current Spring Boot, Java, and web stack versions.
2. Save the v1 OpenAPI JSON/YAML as a baseline.
3. List all Springdoc artifacts and org.springdoc imports.
4. Identify any add-on dependencies in use.
5. Upgrade Spring Boot to a compatible 3.x release and set Java to at least 17 if not already on that baseline.
6. Migrate Jakarta EE APIs from javax to jakarta only for packages that genuinely belong to Jakarta.
7. Replace v1 artifacts with the v2 starter matching MVC/WebFlux and UI/API.
8. Remove duplicate v1 modules from the dependency graph.
9. Update GroupedOpenApi, OpenApiCustomiser, and changed imports.
10. Keep OpenAPI 3 annotations in their packages and handle any remaining Swagger 2 annotations separately.
11. Build and resolve compile/runtime errors from dependencies or namespaces.
12. Verify JSON/YAML endpoints, Swagger UI, and each group.
13. Compare the v2 document against the v1 baseline and run contract/integration tests.
14. Deploy only after critical schemas, security, and operations are confirmed.

If your organization splits the Spring Boot and Springdoc upgrades across multiple pull requests, keep every step buildable and testable. However, do not run Springdoc v2 on Spring Boot 2 as an intermediate state.

## 24. Rollback plan

Before deploying, save:

- Source commit or tag prior to migration.
- Dependency lockfile or dependency tree of the old release.
- OpenAPI JSON/YAML baseline.
- Spring Security and proxy configuration related to docs.
- Pre-migration build/test results.

If the v2 release causes production issues, roll back the corresponding platform/dependency/source changes together to a verified working commit. Do not simply downgrade Springdoc to v1 while keeping Spring Boot 3 and Jakarta-only dependencies if that combination is incompatible.

## 25. Completion checklist

- [ ] Spring Boot and Java are within the compatibility range of the selected Springdoc v2.
- [ ] Application uses the correct MVC or WebFlux starter.
- [ ] UI or API starter selected according to requirements.
- [ ] No Springdoc v1 artifacts remain on the runtime classpath.
- [ ] No incompatible Swagger Core major versions mixed.
- [ ] GroupedOpenApi uses the v2 package.
- [ ] OpenApiCustomiser updated to OpenApiCustomizer if used by the project.
- [ ] Other customizers compile and have verified applicability scope.
- [ ] OpenAPI 3 annotations continue using io.swagger.v3.oas.annotations.
- [ ] Leftover Swagger 2 annotations reviewed.
- [ ] Jakarta EE APIs moved to jakarta; Java SE javax preserved.
- [ ] Build and tests pass.
- [ ] /v3/api-docs and /v3/api-docs.yaml work.
- [ ] Swagger UI works if the UI starter was chosen.
- [ ] Groups, security, and customizers produce the expected results.
- [ ] v2 OpenAPI document compared against the v1 baseline.

## 26. Design principles

- Pair Springdoc v2 with Spring Boot 3+, never attach v2 to a Boot 2 application.
- Pick starters according to web stack and UI/API requirements.
- Remove leftover v1 dependencies to avoid mixing major versions.
- Update GroupedOpenApi to org.springdoc.core.models.
- Switch OpenApiCustomiser to OpenApiCustomizer and verify customizer scope.
- Keep OpenAPI 3 annotations in io.swagger.v3.oas.annotations.
- Handle javax per Jakarta EE API rather than blind string replacement.
- Check add-on modules in v2 documentation instead of guessing artifact names.
- Inspect the dependency tree for conflicts before adding overrides.
- Compare both the document and runtime behavior after migration instead of relying only on a passing build.

## Conclusion

Migrating Springdoc v1 to v2 is part of moving to Spring Boot 3 and Jakarta. Replace old artifacts with v2 starters matching MVC/WebFlux and UI/API needs, update the GroupedOpenApi package, change OpenApiCustomiser to OpenApiCustomizer where used, and audit dependencies and Jakarta namespaces. OpenAPI 3 annotations in io.swagger.v3.oas.annotations remain in place; Swagger 2 annotations and javax APIs must be handled individually by purpose. Complete the migration by inspecting the dependency tree, running build/tests, verifying docs endpoints, groups, Swagger UI, security, and comparing the v2 OpenAPI document against the v1 baseline.

## References

- [springdoc-openapi documentation](https://springdoc.org/)
- [springdoc-openapi migration guide](https://springdoc.org/#migrating-from-springdoc-openapi-v1)
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Framework 6.0 Overview](https://docs.spring.io/spring-framework/reference/overview.html)
