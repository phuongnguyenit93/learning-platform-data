# Checking Spring Boot, Jakarta, and Swagger Core Dependency Changes

When upgrading a Spring Boot application that uses springdoc-openapi, you need to inspect the Spring platform version, the Jakarta namespace, and the Swagger Core libraries in the dependency graph simultaneously. These three groups are directly coupled: Spring Boot determines the Spring Framework and Jakarta API generation; Springdoc provides integration tailored to that generation; and Swagger Core supplies the annotations, models, and OpenAPI processor used by Springdoc.

Springdoc inspects controllers, Spring configuration, data types, and annotations to produce OpenAPI JSON/YAML, which Swagger UI can then render. If you bump only the Spring Boot version while keeping an older generation of the Springdoc starter or Swagger Core, the application may fail to compile, fail to start, or produce inaccurate documentation.

## 1. Three compatibility axes to check

Before editing dependencies, identify all three axes:

| Axis | What to determine | Example |
| --- | --- | --- |
| Spring Boot and Java | Boot version, minimum Java version, managed Spring Framework | Boot 3 requires Java 17 and Spring Framework 6 |
| Jakarta API | Jakarta EE generation, Servlet API, and package namespace | Boot 3 uses Servlet 6 and jakarta.servlet |
| Springdoc and Swagger Core | Springdoc branch, starter, Swagger Core variant, and annotation version | Boot 3 uses Springdoc 2.x and Swagger Core Jakarta |

Do not upgrade individual libraries independently to their latest versions. Choose a combination tested compatible by Springdoc and Spring Boot, and let the BOM manage related dependencies wherever possible.

## 2. Spring Boot and Springdoc compatibility map

Per the Springdoc compatibility matrix at the time of writing:

| Spring Boot | Compatible Springdoc |
| --- | --- |
| 4.1.x | 3.1.x to 3.2.x |
| 4.0.x | 3.0.x |
| 3.5.x | 2.8.x to 2.10.x |
| 3.4.x | 2.7.x to 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x to 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x to 2.1.x |
| 2.7.x | Springdoc 1.6.0 or higher on the 1.x branch |

The version ranges indicate which Springdoc lines were built against the corresponding Spring Boot lines. When starting a new project or upgrading within the same branch, prefer the latest maintenance release within the compatible range rather than picking a version outside the matrix.

Springdoc 1.8.0 is the final open-source release supporting Spring Boot 2.x and 1.x. This is a legacy branch; do not use 1.x artifacts for Boot 3 or Boot 4 applications. Springdoc 2.x targets Boot 3, while Springdoc 3.x targets Boot 4.

## 3. Platform changes from Spring Boot 2 to 3

Spring Boot 3 is a major platform upgrade:

- Minimum Java increases to Java 17.
- Spring Framework moves from 5.x to 6.x.
- Spring Boot 3 targets the Jakarta EE 10 API level.
- Servlet API moves to 6.0; JPA moves to 3.1.
- Jakarta EE packages change from the javax namespace to jakarta.
- APIs, classes, and properties deprecated in Boot 2 may be removed.

Because Springdoc v1 was built for the Boot 2 generation, upgrading to Boot 3 means switching to Springdoc 2.x and the new starters. Do not merely bump the parent version while leaving all old dependencies unchanged.

Before upgrading, bring the Boot 2 application to the latest maintenance release of the 2.7.x line if the project roadmap allows. This step helps resolve deprecations and legacy dependencies ahead of the Spring Framework/Jakarta transition.

## 4. Platform changes from Spring Boot 3 to 4

Spring Boot 4 is based on Spring Framework 7 and Jakarta EE 11:

| Component | Spring Boot 3 | Spring Boot 4 |
| --- | --- | --- |
| Minimum Java | 17 | 17 |
| Spring Framework | 6.x | 7.x |
| Jakarta EE | 10 | 11 |
| Servlet API | 6.0 | 6.1 |
| JPA | 3.1 | 3.2 |
| Bean Validation | 3.0 | 3.1 |
| Springdoc | 2.x | 3.x |

Boot 4 continues using the Jakarta namespace. Consequently, there is no new javax-to-jakarta rename wave like the Boot 2-to-3 jump; the focus is on updating Jakarta API levels, Spring Framework, and compatible libraries.

Boot 4 also removes classes, methods, and configuration properties deprecated in Boot 3. Address warnings prior to upgrading to avoid compile or startup failures once those APIs are removed.

Another notable change is that Spring Boot 4 favors Jackson 3. Jackson 3 moves most groups/packages from com.fasterxml.jackson to tools.jackson; jackson-annotations alone keeps the com.fasterxml.jackson.core / com.fasterxml.jackson.annotation group and package. If the application or custom libraries directly use ObjectMapper, serializers, or Jackson modules, review compatibility separately.

## 5. Distinguish javax and jakarta

Jakarta EE changed its namespace from javax to jakarta. Examples:

| Legacy API | Jakarta API |
| --- | --- |
| javax.servlet.Filter | jakarta.servlet.Filter |
| javax.servlet.http.HttpServletRequest | jakarta.servlet.http.HttpServletRequest |
| javax.validation.Valid | jakarta.validation.Valid |
| javax.validation.constraints.NotNull | jakarta.validation.constraints.NotNull |
| javax.persistence.Entity | jakarta.persistence.Entity |
| javax.annotation.PostConstruct | jakarta.annotation.PostConstruct |
| javax.transaction.Transactional | jakarta.transaction.Transactional |
| javax.ws.rs.Path | jakarta.ws.rs.Path |

This is a package and binary type change, not merely an import rename. A filter compiled against javax.servlet.Filter cannot be invoked by a Jakarta container as a jakarta.servlet.Filter. Likewise, a validation provider on the old namespace will not automatically recognize Jakarta annotations on DTOs.

Do not blindly replace every occurrence of javax across source code. Several Java SE packages keep the javax namespace, such as javax.sql, javax.crypto, javax.net, and javax.xml. Convert only APIs belonging to Java EE/Jakarta EE that changed namespaces.

## 6. Audit direct and transitive Jakarta dependencies

When upgrading to Boot 3 or Boot 4, inspect both directly declared and transitive dependencies:

- Servlet API and embedded server.
- Bean Validation API and validation provider.
- JPA API, Hibernate, and persistence provider.
- Jakarta Annotations, Transactions, and REST APIs if used by the application.
- Legacy filters, security libraries, servlet initializers, or integrations.
- Build plugins, annotation processors, and test fixtures.

Example Servlet dependency for the Jakarta generation:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
~~~

In a standard Spring Boot application, the web starter and dependency management already provide the right version. Declare the Servlet API directly only if your source or module needs to compile against that API; do not pin an arbitrary version to override the Boot-managed dependency.

If the dependency tree still shows javax.servlet:javax.servlet-api on the runtime classpath of a Boot 3/4 application, identify which library pulls it in. You may need to upgrade that library to a Jakarta release or drop the legacy dependency. Never include both APIs simultaneously just to silence compiler errors.

## 7. Springdoc v1 to v2: replace starters and modules

Springdoc v2 renamed modules following the starter convention. Important mappings:

| Springdoc v1 | Springdoc v2 |
| --- | --- |
| springdoc-openapi-common | springdoc-openapi-starter-common |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api |
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui |

Support modules such as Javadoc, Kotlin, Data REST, Security, HATEOAS, and Groovy are consolidated into starter-common in the v2 model per the migration guide. Do not retain v1 modules solely because of similar names; check whether the capability now lives in starter-common or requires a separate extension module.

Example previously using Swagger UI on Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.8.0</version>
</dependency>
~~~

After moving to Boot 3, use the v2 starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

If the application uses WebFlux, pick springdoc-openapi-starter-webflux-ui. If only OpenAPI JSON/YAML is needed, use the webmvc-api or webflux-api variant to avoid bundling the UI at runtime.

## 8. Springdoc package and class changes

Beyond artifacts, several classes moved packages or changed names:

| Springdoc v1 | Springdoc v2 |
| --- | --- |
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

GroupedOpenApi import example:

~~~java
// Springdoc v1
import org.springdoc.core.GroupedOpenApi;

// Springdoc v2
import org.springdoc.core.models.GroupedOpenApi;
~~~

Customizer example:

~~~java
// Springdoc v1
import org.springdoc.core.customizers.OpenApiCustomiser;

// Springdoc v2
import org.springdoc.core.customizers.OpenApiCustomizer;
~~~

The interface name changed from OpenApiCustomiser to OpenApiCustomizer. If the application has customizer beans or methods accepting this type, update both imports and type declarations.

## 9. Springdoc v2 to v3 when moving to Boot 4

Springdoc v3 targets Spring Boot 4. Starters keep the webmvc/webflux and api/ui naming pattern:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

The example above fits the Boot 4.1.x branch per the current compatibility matrix. For Boot 4.0.x, use Springdoc 3.0.x. Do not pull Springdoc 3.2.x into Boot 3.5 just because it is newer; Boot 3.5.x belongs to the Springdoc 2.8.x to 2.10.x branch.

When moving from Springdoc 2 to 3, do not assume all transitive application dependencies stay unchanged. Check starters, Spring Framework 7, Jakarta EE 11, Swagger Core Jakarta, and Jackson under Boot 4's dependency management.

## 10. Swagger Core has two artifact lines: javax and Jakarta

Swagger Core 2.x provides OpenAPI annotations, models, and processors. Starting with 2.1.7, Swagger Core ships a parallel set of artifacts suffixed with -jakarta alongside the unsuffixed artifacts:

| Namespace | Example artifacts |
| --- | --- |
| javax | swagger-core, swagger-annotations, swagger-models, swagger-integration |
| Jakarta | swagger-core-jakarta, swagger-annotations-jakarta, swagger-models-jakarta, swagger-integration-jakarta |

Jakarta artifacts are built for the Jakarta EE ecosystem. Spring Boot 3/4 applications should use the Jakarta set whenever dependencies need Jakarta-integrated Swagger Core. The appropriate Springdoc starter already pulls in these dependencies; do not add swagger-core-jakarta manually without a direct need.

Do not mix swagger-core with swagger-core-jakarta or swagger-annotations with swagger-annotations-jakarta on the same runtime classpath. The two lines contain classes with identical names that depend on different namespaces. If the classloader picks the wrong variant, the application can hit linkage errors or broken Servlet/JAX-RS integration.

## 11. Do Swagger annotation imports change?

A common misconception: the -jakarta suffix applies to Maven artifacts, not to changing Swagger annotation packages from io.swagger to jakarta.swagger.

Imports remain:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
~~~

The OpenAPI v3 annotation package is still io.swagger.v3.oas.annotations. The Jakarta variant of Swagger Core provides annotation classes under the same package/API for compatibility with the Jakarta generation. Source code namespace updates apply to Servlet, Validation, Persistence, or other Jakarta APIs, not @Operation or @Schema imports.

Swagger Core 1.5.x belongs to Swagger 2.0/OpenAPI 2.0. Swagger Core 2.x produces OpenAPI 3.x; from 2.2.0 onward it supports OpenAPI 3.1. Do not confuse the Swagger Core library version with the OpenAPI version declared in the generated document.

## 12. Avoid pinning Swagger Core outside dependency management

Springdoc declares the compatible Swagger Core version inside its starter dependency graph. If a project adds swagger-core or swagger-annotations directly with a different version, it can override the version tested by Springdoc.

Start by declaring only the Springdoc starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.10.0</version>
</dependency>
~~~

Add Swagger Core directly only when application code explicitly calls Swagger Core APIs, such as ModelConverters or a custom integration. When doing so:

- Pick the Jakarta artifacts for Boot 3/4 applications.
- Use the Swagger Core version compatible with Springdoc.
- Keep swagger-core-jakarta, swagger-models-jakarta, swagger-annotations-jakarta, and swagger-integration-jakarta aligned.
- Avoid letting one Jakarta module pull in a javax module of a different version.
- Inspect the dependency tree after adding the dependency.

If you need to manage Swagger Core across multiple modules, consider Swagger Core's swagger-bom to keep modules on the same release. Do not use Swagger Core's BOM or versions to arbitrarily override what Springdoc selected.

## 13. Inspect the dependency graph with Maven

The dependency tree helps identify which module pulls in an older version:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

Check Servlet and Jakarta specifically:

~~~bash
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api,jakarta.servlet:jakarta.servlet-api
~~~

Also check Jackson when upgrading to Boot 4:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core,tools.jackson,com.fasterxml.jackson.module
~~~

Trace the dependency path from the application to the suspect artifact. For example, if unsuffixed swagger-core appears via an older library, identify that library before adding an exclusion. An exclusion only works when you know which replacement dependency supplies the required functionality.

## 14. Inspect the dependency graph with Gradle

View the runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Locate Swagger Core dependencies:

~~~bash
./gradlew dependencyInsight \
  --dependency swagger-core \
  --configuration runtimeClasspath
~~~

Locate Servlet API:

~~~bash
./gradlew dependencyInsight \
  --dependency servlet-api \
  --configuration runtimeClasspath
~~~

Check Jackson when moving to Boot 4:

~~~bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Gradle dependencyInsight reveals the selected version, which dependency requested it, and why another version was replaced. It is a fast way to spot conflicts caused by direct dependencies, constraints, or platforms.

## 15. Scan packages in source code

After updating dependencies, search for legacy Jakarta EE imports:

~~~bash
rg -n "javax\\.(servlet|validation|persistence|annotation|transaction|ws\\.rs)" src
~~~

Verify new Jakarta packages:

~~~bash
rg -n "jakarta\\.(servlet|validation|persistence|annotation|transaction|ws\\.rs)" src
~~~

Do not replace javax in bulk. Review each import against its actual API and check whether third-party libraries support Jakarta. In code using both Java SE and Jakarta EE, certain javax imports must remain unchanged.

After updating imports, verify:

- Filters, Servlets, Listeners, and HttpServletRequest.
- @Valid, @NotNull, @NotBlank, and the Validation provider.
- JPA entities, repositories, and the persistence provider.
- Lifecycle annotations such as @PostConstruct.
- Transaction managers and transaction annotations.
- JAX-RS APIs if the application uses Jersey or another REST integration.
- Test fixtures, mocks, and libraries using reflection on annotations.

## 16. Check Jackson changes when upgrading to Boot 4

Boot 4 favors Jackson 3. Most packages move from com.fasterxml.jackson to tools.jackson, though jackson-annotations keeps the com.fasterxml.jackson.annotation package.

Example when the application uses a mapper directly:

~~~java
// Jackson 2
import com.fasterxml.jackson.databind.ObjectMapper;

// Jackson 3
import tools.jackson.databind.ObjectMapper;
~~~

Do not apply this import change to every annotation. For instance, @JsonProperty, @JsonIgnore, and @JsonInclude belong to jackson-annotations and continue to use:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
~~~

When moving to Boot 4, inspect custom serializers/deserializers, ObjectMapper beans, Jackson modules, Kotlin module, Java Time module, and Springdoc schema resolution. If the application relies on a library supporting only Jackson 2, determine compatibility clearly; Spring Boot offers a spring-boot-jackson2 module as a transitional option, though it is deprecated and scheduled for future removal.

OpenAPI schemas can change when Jackson changes how it detects properties, naming strategies, modules, or serialization. Therefore, compare pre- and post-upgrade documents, especially for DTOs with custom serializers or @JsonView.

## 17. Special note when upgrading to Spring Boot 3.2

Spring Boot 3.2 changed parameter name discovery. If the application is not compiled with the option to retain parameter names, Springdoc may fail to infer query/path parameter names from bytecode.

With Maven Compiler Plugin, enable the parameters option:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

With the Gradle Java plugin:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

After enabling it, check the OpenAPI document to confirm parameter names are not lost or turned into unexpected names. If controllers already declare name explicitly in @RequestParam or @PathVariable, documentation relies less on bytecode name discovery.

## 18. Migrate configuration and address deprecations

Spring Boot can rename or remove configuration properties across major versions. When upgrading Boot 2 to 3 or Boot 3 to 4, check the configuration changelog and migration guide.

You can temporarily add spring-boot-properties-migrator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

This module reports renamed or removed properties on application startup and can temporarily assist migration. Once application.yml/properties is updated, remove the migrator module from the dependency graph.

Do not use the migrator as a permanent solution. The final configuration must use the exact property names of the target Boot version to avoid depending on temporary compatibility shims.

## 19. Step-by-step upgrade workflow

A repeatable workflow that isolates issues cleanly:

1. Record current versions of Java, Spring Boot, Spring Framework, Springdoc, Swagger Core, and Jakarta APIs.
2. Run existing tests and save OpenAPI JSON/YAML as a baseline.
3. If upgrading Boot 2 to 3, first bring the app to the final maintenance release of Boot 2.7.x.
4. If upgrading Boot 3 to 4, first bring the app to the latest maintenance release of Boot 3.5.x and resolve deprecations.
5. Select Java and Springdoc versions matching the target Boot's compatibility matrix.
6. Update the Boot parent/BOM or Gradle platform so dependency management is aligned.
7. Switch Springdoc v1 dependencies to v2 starters, or v2 to v3 starters.
8. Update Jakarta EE imports/dependencies if moving from Boot 2 to Boot 3; verify Jakarta EE 11 level if moving to Boot 4.
9. Verify Swagger Core Jakarta artifacts and remove old javax variants from runtime.
10. Update renamed Springdoc packages/classes and configuration properties.
11. Handle Jackson changes if upgrading to Boot 4.
12. Compile, run tests, start the application, and download the OpenAPI document.
13. Compare the new OpenAPI document against the baseline and confirm intentional schema changes.
14. Remove migration helpers and temporary dependencies once finished.

Do not upgrade Spring Boot, Springdoc, Swagger Core, Jackson, and multiple non-Spring libraries all at once without baseline tests. If an issue arises, upgrading in small batches makes it easier to identify the source of changes.

## 20. Verify results after upgrading

Once the application starts, check the endpoints:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -I http://localhost:8080/swagger-ui.html
~~~

If the project uses a custom path or API-only mode, adjust the URLs accordingly.

Verify the OpenAPI contents:

- The openapi field has the expected version.
- paths contain all operations.
- parameters preserve names, locations, required flags, and schemas.
- requestBody and responses have the right content types/schemas.
- components.schemas preserve properties, enums, formats, and nullability.
- Security schemes and requirements remain intact.
- Server URLs and context paths match the environment.
- No missing schema references or unintended duplicate component names exist.

For Swagger UI, confirm the page loads swagger-config and the OpenAPI document. If the document loads successfully while the UI fails to render, check content types, custom HttpMessageConverters, and the Swagger UI version before concluding Springdoc is incompatible.

## 21. Symptoms of incompatible dependencies

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| ClassNotFoundException: javax.servlet... | Legacy library still expects the javax Servlet namespace | Find the dependency pulling javax.servlet and upgrade it |
| ClassNotFoundException: jakarta.servlet... | Runtime lacks Jakarta Servlet API or wrong web stack starter | Check Boot starter and runtime classpath |
| NoClassDefFoundError reading annotations | Missing Swagger annotation artifact or wrong variant | Check swagger-annotations and swagger-core |
| NoSuchMethodError in io.swagger | Mismatched Swagger Core module versions | Align swagger-core, models, annotations, and integration |
| ClassCastException between javax and jakarta | Two namespaces mixed in the same integration path | Replace legacy dependency with Jakarta build |
| GroupedOpenApi not found | Leftover Springdoc v1 package import | Use org.springdoc.core.models.GroupedOpenApi in v2/v3 |
| OpenApiCustomiser not found | Interface was renamed | Use OpenApiCustomizer |
| OpenAPI loses parameter names | Compiler not retaining parameter names or missing explicit metadata | Enable -parameters and check binding annotations |
| Schema changed after moving to Boot 4 | Jackson 3 or serialization modules changed | Inspect mappers, annotations, custom serializers, and OpenAPI diff |
| Swagger UI fails to render document | JSON converter, content type, or Swagger UI dependency conflict | Check /v3/api-docs response and dependency tree |
| Application starts but docs endpoints missing | Wrong branch starter or API docs disabled | Check springdoc starter, auto-configuration, and properties |

Do not fix linkage errors by randomly pinning the latest swagger-core version. Locate the conflicting artifact, cross-check against the Springdoc version, and choose a consistent dependency set.

## 22. Pre-release dependency checklist

- [ ] Spring Boot version falls within a compatible Springdoc branch.
- [ ] Java runtime and compiler target satisfy Boot's requirements.
- [ ] Spring Framework version is managed by Boot without mismatched pins.
- [ ] Boot 3/4 runtime has no legacy Java EE javax dependencies left.
- [ ] javax packages audited per API; Java SE namespaces kept intact.
- [ ] Springdoc starter uses the right Web MVC/WebFlux artifact and branch 1/2/3.
- [ ] No old Springdoc v1 modules remain after moving to v2/v3.
- [ ] GroupedOpenApi, SpringDocUtils, and OpenApiCustomizer imports updated.
- [ ] Swagger Core Jakarta artifacts used consistently.
- [ ] No mixing of swagger-core and swagger-core-jakarta.
- [ ] swagger-core, models, annotations, and integration modules have compatible versions.
- [ ] Swagger Core not pinned independently when the starter manages compatible dependencies.
- [ ] Jackson modules and custom serializers are compatible with the target Boot.
- [ ] Inspected Maven dependency:tree or Gradle dependencyInsight.
- [ ] OpenAPI JSON/YAML fetched cleanly and schemas compared against baseline.
- [ ] Swagger UI renders the document and test requests work per configuration.
- [ ] Removed spring-boot-properties-migrator after updating configuration.

When upgrading Spring Boot, check Jakarta APIs and Swagger Core dependencies alongside Springdoc. Boot 2 to 3 is a major namespace and platform transition; Boot 3 to 4 continues advancing Jakarta EE, Spring Framework, and Jackson. Springdoc must stay on its compatible branch, and Swagger Core must use the right Jakarta variant with aligned module versions. The dependency tree, compile/tests, and pre/post-upgrade OpenAPI documents are the three key pieces of evidence proving a safe migration.

## References

- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Springdoc OpenAPI v2 — Migration from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [Springdoc OpenAPI — Current compatibility matrix and modules](https://springdoc.org/)
- [Swagger Core — Jakarta namespace artifacts](https://github.com/swagger-api/swagger-core)
- [Swagger Core — Jakarta annotations guidance](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
