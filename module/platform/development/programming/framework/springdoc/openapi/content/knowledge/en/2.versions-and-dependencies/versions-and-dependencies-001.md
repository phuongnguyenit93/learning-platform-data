# Distinguishing Spring Boot, Springdoc, and OpenAPI Specification Versions

When adding springdoc-openapi to a Spring Boot application, there are at least three version types to distinguish: the Spring Boot version, the springdoc-openapi library version, and the OpenAPI Specification version that the application outputs. These three numbers do not need to match and are not interchangeable. An application can run Spring Boot 4.1, use springdoc 3.2.0, and still output a document conforming to OpenAPI 3.0 if configuration and consumers require it.

Choosing the wrong springdoc line can prevent the application from starting, cause missing auto-configuration, or lead to compatibility errors with Spring Framework, Jakarta API, Swagger Core, and Jackson. Choosing the wrong OpenAPI version can prevent SDK generators, API gateways, or tool registries from reading the schema as expected. Therefore, identify the Spring platform first, choose springdoc according to the compatibility matrix, and then select the OpenAPI version based on consumer capabilities.

## 1. The Three Version Axes and Public API Version

| Axis | Example | What does it decide? |
| --- | --- | --- |
| Spring Boot | `4.1.2`, `3.5.16` | Application platform, Spring Framework, auto-configuration, dependency management, and Java requirements. |
| springdoc-openapi | `3.2.0`, `2.10.0` | Spring integration library version that scans controllers/models and generates documentation. |
| OpenAPI Specification | `3.1.0`, `3.0.1` | Syntax and semantics of the generated JSON/YAML document. |
| API version (`info.version`) | `1.4.0`, `2026-11` | API contract version published by the development team for consumers. |

The first three axes have compatibility relationships but independent lifecycles. `info.version` is metadata describing the API, not the version of Spring Boot, springdoc, or the OpenAPI Specification. For example, changing springdoc from `2.9.x` to `2.10.x` does not require changing `info.version` if the API contract has not changed.

In an OpenAPI document, the top fields of the document:

~~~yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.4.0
~~~

`openapi: 3.1.0` indicates that the document complies with OpenAPI Specification version 3.1.0. `info.version: 1.4.0` is the API version published by the development team. These two fields have different meanings.

## 2. Compatibility Matrix Between Spring Boot and springdoc

Springdoc maintains different major lines for each Spring Boot generation. According to the official compatibility matrix checked on 20-11-2026:

| Spring Boot | Compatible springdoc line built for it |
| --- | --- |
| `4.1.x` | `3.1.x` – `3.2.x` |
| `4.0.x` | `3.0.x` |
| `3.5.x` | `2.8.x` – `2.10.x` |
| `3.4.x` | `2.7.x` – `2.8.x` |
| `3.3.x` | `2.6.x` |
| `3.2.x` | `2.3.x` – `2.5.x` |
| `3.1.x` | `2.2.x` |
| `3.0.x` | `2.0.x` – `2.1.x` |
| Spring Boot `2.x` and `1.x` | Legacy `springdoc 1.x` line; `1.8.0` is the last Open Source release published for these lines. |

The matrix is a guide for choosing the library line; it does not mean every patch release in a range has been tested against every patch release of Spring Boot. When choosing a specific version, read the release notes and compatibility matrix for that exact line. Do not assume that a newer springdoc version is always backward-compatible with every older Spring Boot version.

At the time of verification, the official documentation lists `springdoc 3.2.0` for the Spring Boot `4.1.x` line and `springdoc 2.10.0` for the Spring Boot `3.5.x` line. This is a reference point as of the date noted above; before each upgrade, re-check the releases page and matrix because the project may have published newer versions.

### 2.1. Why Do Boot 2, Boot 3, and Boot 4 Use Different Lines?

- **Spring Boot 1.x/2.x:** belongs to the springdoc 1.x line. This is the legacy line using the older Spring ecosystem and Java EE `javax.*` namespace. Version `1.8.0` is the last Open Source release published for these lines.
- **Spring Boot 3.x:** uses springdoc 2.x. Boot 3 requires Java 17 or higher and migrated to Jakarta EE 9 with the `jakarta.*` namespace. Springdoc 2 was built for this platform generation.
- **Spring Boot 4.x:** uses springdoc 3.x. Do not choose springdoc 2 just because the application previously used Boot 3; Boot 4 belongs to the new integration line.

When upgrading Boot 2 to Boot 3, besides switching springdoc 1.x to 2.x, you must also handle the `javax.*` to `jakarta.*` namespace change and major Spring Framework changes. When upgrading Boot 3 to Boot 4, choose springdoc 3.x and check Spring Boot 4 compatibility changes. Do not treat this as a simple operation of swapping a few dependencies.

## 3. Choosing a Starter by Web Stack and UI Needs

Springdoc provides separate starters for Spring MVC, WebFlux, and whether or not Swagger UI is included:

| Web stack | With Swagger UI | OpenAPI endpoint only |
| --- | --- | --- |
| Spring MVC / Servlet | `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webmvc-api` |
| Spring WebFlux / Reactive | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |

Choose the exact single starter matching the actual stack. With Spring Boot 3, Spring MVC applications typically use `spring-boot-starter-web`; WebFlux applications use `spring-boot-starter-webflux`. Starting from Spring Boot 4, the MVC starter was renamed to `spring-boot-starter-webmvc`; `spring-boot-starter-web` still remains but is deprecated in favor of the new name. WebFlux applications continue using the corresponding WebFlux starter. Do not add both springdoc UI starters just to experiment, as this can pull in unnecessary configuration and dependencies.

If you only export OpenAPI JSON/YAML for an API catalog, CI, or SDK generator, the `*-api` starter is sufficient. If developers need an interactive interface, choose the `*-ui` starter. There is no need to add a separate Swagger UI dependency when springdoc's UI starter already provides that integration.

The starter artifacts above are for modern springdoc lines. Legacy springdoc 1.x projects use old module naming conventions; do not copy v2/v3 Maven coordinates into a Boot 2 application without consulting v1 documentation.

## 4. Maven Example for Spring Boot 4.1 and springdoc 3.2

For a Spring MVC application running Spring Boot 4.1.x, you can use the WebMVC UI starter. The example below illustrates the compatibility baseline published in springdoc documentation at the time of verification:

~~~xml
<properties>
    <java.version>17</java.version>
    <springdoc.version>3.2.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

The example assumes the project already uses `spring-boot-starter-parent` or imports the Spring Boot dependency BOM to manage Spring dependencies. The springdoc version is declared explicitly because the Spring Boot BOM does not automatically select a compatible springdoc line for every application.

## 5. Maven Example for Spring Boot 3.5 and springdoc 2.10

For a Spring MVC application running Spring Boot 3.5.x, select springdoc 2.10.x per the matrix:

~~~xml
<properties>
    <java.version>17</java.version>
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

If the application uses WebFlux, use `spring-boot-starter-webflux` and the springdoc artifact `springdoc-openapi-starter-webflux-ui`. If only JSON/YAML is needed, replace the `-ui` suffix with `-api`.

Do not add arbitrary versions of `swagger-core`, `swagger-annotations`, or `swagger-ui` to fix an error before inspecting the dependency tree. The springdoc starter manages the related dependencies; overriding an individual component can cause Swagger libraries to use incompatible versions.

## 6. Gradle Kotlin DSL Example

With Gradle, declare the springdoc version as a variable for easier upgrades and reviews:

~~~kotlin
val springdocVersion = "2.10.0"

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion"
    )
}
~~~

The snippet above is for Spring Boot 3.5.x. If the project uses Boot 4.1.x, select the springdoc 3.1.x–3.2.x line per the current matrix, for example `3.2.0` at the time of verification. Gradle does not change compatibility principles simply because its dependency syntax differs from Maven.

If the project uses a version catalog (`libs.versions.toml`), put the version in the catalog and reference the alias in `build.gradle.kts`. Avoid declaring the same version across multiple files because it easily causes drift during upgrades.

## 7. Generated OpenAPI Specification Version

The springdoc version determines integration capabilities and the bundled Swagger Core version; the OpenAPI document version can be selected separately within the range supported by springdoc.

Current configuration documentation provides the property:

`springdoc.api-docs.version`

This property selects OpenAPI 3.0 or OpenAPI 3.1. For example:

In the current configuration documentation for springdoc v2/v3, the default value is OpenAPI 3.1. The springdoc v1 line defaults to OpenAPI 3.0; if upgrading from v1 to v2, inspect the document's `openapi` field because the default dialect can change even when controllers do not change.

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

If an API catalog or SDK generator only supports OpenAPI 3.0, you can configure:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Verify that the property value is supported by the exact springdoc line in use. After changing it, call `/v3/api-docs` and check the `openapi` field at the top of the document; do not rely solely on YAML configuration without verifying the output.

### 7.1. Key Differences Between OpenAPI 3.0 and 3.1

OpenAPI 3.1 updates the Schema Object model to align more closely with JSON Schema Draft 2020-12. This expands how nullable types, union types, and complex schemas are expressed. OpenAPI 3.0 uses its own schema model with some different rules, such as the `nullable` property.

Illustrative example:

~~~yaml
# OpenAPI 3.0
type: string
nullable: true
~~~

~~~yaml
# OpenAPI 3.1
type:
  - string
  - "null"
~~~

This is an example of schema representation; not every schema can be converted simply by changing the `openapi` field. Check validators, SDK generators, API gateways, mock servers, and contract testing tools before changing dialects.

If consumers still depend on OpenAPI 3.0, keeping 3.0 during a transition period may be better than switching immediately to 3.1. If consumers already fully support 3.1 and need the new schema capabilities, upgrade with proper testing.

## 8. Do Not Confuse OpenAPI Version with info.version

Document configuration example:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

And API metadata:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI storeApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Store API")
                .version("1.4.0"));
    }
}
~~~

In the resulting document, `openapi` describes the specification version, while `info.version` describes the API version. Changing `info.version` from `1.4.0` to `1.5.0` does not convert the document from OpenAPI 3.0 to 3.1. Changing `springdoc.api-docs.version` also does not publish a new business API version.

## 9. What Does the Spring Boot BOM Manage and Not Manage?

Spring Boot dependency management helps select compatible versions of Spring Framework, Jackson, logging, validation, and many other integrated libraries. When using the Spring Boot parent or BOM, you normally should not manually pin versions for individual `spring-core`, `spring-web`, `spring-context`, or Jackson modules without a specific reason.

Springdoc is an additional integration library. Choose the springdoc version according to the compatibility matrix and declare it explicitly in Maven/Gradle. Do not assume the Spring Boot BOM will automatically upgrade springdoc to a compatible line.

Principles:

- Keep Spring Boot dependencies managed by the project's BOM.
- Declare one explicit springdoc version, optionally via a property or version catalog.
- Let the springdoc starter manage bundled Swagger Core, annotations, and UI versions.
- Do not override a single Swagger module before identifying the root cause of a conflict.
- When a transitive dependency override is needed, check release notes and run contract tests on the generated document.

## 10. Inspecting the Dependency Tree on Conflicts

With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.springframework
~~~

You can inspect the effective POM:

~~~bash
./mvnw help:effective-pom
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
~~~

Look for these cases:

- Both springdoc 1.x and 2.x/3.x present at the same time.
- Multiple unnecessary MVC/WebFlux starters present.
- Swagger Core or `swagger-annotations` forced to a different version than the starter's.
- Jackson/Spring Framework overridden away from the version managed by Spring Boot.
- Old `springdoc-openapi-ui` dependency alongside a new starter.

When you see multiple versions, do not exclude dependencies randomly. Check which dependency pulls that version in, why it is present, and which starter needs it. After adjusting, run a build and fetch the document to confirm auto-configuration still works.

## 11. Migrating from springdoc 1.x to 2.x

This is usually part of upgrading Spring Boot 2 to Boot 3. Main steps:

1. Upgrade the application to Java 17 or higher.
2. Upgrade Spring Boot to the 3.x line compatible with the project's dependencies.
3. Migrate Java EE `javax.*` namespaces to Jakarta `jakarta.*` in the corresponding APIs.
4. Replace springdoc 1.x dependencies with the springdoc 2.x starter appropriate for MVC or WebFlux.
5. Inspect Swagger annotations, Spring Security, validation, and customizers.
6. Rebuild the application and verify `/v3/api-docs`, Swagger UI, and groups.
7. Compare the OpenAPI document before and after the upgrade to detect schema, operation, or metadata changes.

Do not mechanically find-and-replace every namespace. Some standard Java packages still belong to `javax.*`; only APIs moved to Jakarta need changing. Check compile errors and the Spring Boot migration guide.

## 12. Migrating from springdoc 2.x to 3.x

Spring Boot 4 corresponds to the springdoc 3.x line. When upgrading:

1. Verify the application already meets Spring Boot 4's platform and Java requirements.
2. Choose springdoc 3.x according to the corresponding Boot 4.0/4.1 matrix.
3. Verify MVC vs. WebFlux starter and UI vs. API-only module.
4. Read the release notes for springdoc 3.x and Spring Boot 4.
5. Check the APIs, auto-configuration, customizers, and model converters used by the application.
6. Run context startup tests, contract tests, and verify JSON/YAML output.
7. Compare the document against the baseline before releasing.

Do not keep springdoc 2.x in a Boot 4 application just because the code compiles in the IDE. The compatibility matrix is the basis for line selection; startup tests and document verification confirm actual integration.

## 13. Safe Upgrade Procedure

When upgrading Spring Boot, springdoc, or the OpenAPI dialect, split the work into reviewable steps:

1. Record the current Java, Spring Boot, springdoc, and `openapi` versions.
2. Save the current OpenAPI JSON/YAML as a baseline.
3. Document the groups, operationIds, component schemas, and docs endpoints used by consumers.
4. Choose the springdoc version per the target Spring Boot's compatibility matrix.
5. Update the springdoc dependency and perform any necessary source migrations.
6. Keep the OpenAPI dialect unchanged in the initial upgrade if consumers do not yet need a change.
7. Run tests and regenerate the document under the same profile/configuration.
8. Diff the new document against the baseline, classifying dependency-driven changes versus intentional API changes.
9. Change OpenAPI 3.0 to 3.1 only in a separate change with consumer testing.
10. Release and monitor for errors from SDK generators, gateways, registries, or clients.

Separating dependency upgrades from contract changes makes it easier to pinpoint causes when the document changes. Changing Boot, springdoc, schemas, operationIds, and the OpenAPI dialect all at once makes it very hard to identify which change broke things.

## 14. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Boot 3 app fails to start with springdoc 1.x | Wrong springdoc line chosen for Boot 3/Jakarta | Switch to springdoc 2.x matching the matrix. |
| Boot 4 app has auto-configuration errors | Using springdoc 2.x instead of 3.x | Choose springdoc 3.x for the exact Boot 4 minor. |
| `ClassNotFoundException` or `NoSuchMethodError` | Swagger Core/Spring/Jackson version mismatch | Inspect the dependency tree and let the starter/BOM manage related dependencies. |
| `/v3/api-docs` is missing | Wrong starter used or endpoint configuration disabled | Check MVC/WebFlux, API/UI artifact, and `springdoc.api-docs.enabled`. |
| Swagger UI missing while JSON works | Using `*-api` starter or UI disabled | Choose the `*-ui` starter if an interface is needed. |
| Both MVC and WebFlux starters present | Dependencies copied from multiple examples | Keep only the starter matching the actual web stack. |
| SDK generator fails after switching to OpenAPI 3.1 | Consumer does not yet fully support the new dialect/schemas | Keep OpenAPI 3.0 or upgrade consumers with testing. |
| `info.version` changed but OpenAPI version did not | Confusing API version with specification version | Check `info.version` and the `openapi` field separately. |
| OpenAPI document changed after springdoc upgrade | Swagger Core or introspection changed | Diff against baseline and review affected schemas/operations. |
| Maven/Gradle pulls multiple Swagger versions | Dependency override or legacy starter used alongside new starter | Trace the dependency path and remove intentional/unintended conflicts. |
| Boot 2 project cannot use v2/v3 starters | Confusing new starter artifacts with legacy modules | Use the springdoc 1.x line and v1 docs for legacy projects. |

## 15. Checklist Before Adding or Upgrading springdoc

Before merging dependency changes, confirm:

1. Exact Spring Boot minor version and Java version of the application are known.
2. Chosen springdoc line falls within Boot's compatibility matrix.
3. MVC vs. WebFlux is correctly identified.
4. UI starter vs. API-only starter is chosen based on needs.
5. Legacy springdoc and new starters do not appear together.
6. Swagger Core/Jackson/Spring modules are not unintentionally overridden.
7. OpenAPI Specification version is chosen according to consumer capabilities.
8. `info.version` is not confused with the `openapi` field.
9. `/v3/api-docs`, YAML, Swagger UI, and required groups work.
10. Contract diff has no unplanned breaking changes.
11. Release notes for Spring Boot and springdoc have been read.
12. Dependency tree is inspected when signs of conflict appear.

## 16. Guiding Principles

- Identify Spring Boot first, then select springdoc per the compatibility matrix.
- Boot 4 uses springdoc 3.x; Boot 3 uses springdoc 2.x; Boot 1/2 belong to the legacy springdoc 1.x line.
- Choose the MVC/WebFlux and UI/API-only starter matching the application architecture.
- Let the Spring Boot BOM manage platform dependencies; declare the springdoc version separately.
- Avoid overriding Swagger Core, annotations, or Swagger UI without inspecting the dependency tree.
- Distinguish Spring Boot, springdoc, OpenAPI Specification, and `info.version` versions.
- Choose OpenAPI 3.0/3.1 based on validator, SDK generator, and consumer support.
- Keep the OpenAPI dialect stable during dependency upgrades unless a dialect change is requested.
- Save a baseline and diff the document after every upgrade.
- Read release notes and test JSON/YAML endpoints before releasing.

Spring Boot determines the application platform; springdoc determines whether the integration library is compatible with that platform; OpenAPI Specification determines the emitted contract format; and `info.version` is the API version published by the development team. By selecting each axis accurately, using the appropriate starter, and checking the document after upgrades, an application can change platforms or libraries without accidentally breaking tools and clients consuming OpenAPI.

## References

- [Springdoc OpenAPI – Compatibility Matrix and Getting Started](https://springdoc.org/)
- [Springdoc OpenAPI v2 – Spring Boot 3 Documentation](https://springdoc.org/v2/)
- [Springdoc OpenAPI v1 – Legacy Spring Boot Documentation](https://springdoc.org/v1/index.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [Springdoc OpenAPI – Releases](https://github.com/springdoc/springdoc-openapi/releases)
- [Spring Boot 4.0 Migration Guide – renamed/deprecated starters](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [OpenAPI Specification 3.0.4](https://spec.openapis.org/oas/v3.0.4.html)
- [Spring Boot – Upgrading](https://docs.spring.io/spring-boot/reference/upgrading/index.html)
