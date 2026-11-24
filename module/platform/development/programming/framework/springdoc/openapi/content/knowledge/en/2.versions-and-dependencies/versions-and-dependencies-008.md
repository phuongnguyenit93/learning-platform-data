# javax and jakarta Namespaces Across Spring Boot Generations

When upgrading an application from Spring Boot 2 to Spring Boot 3, many imports starting with `javax.*` must change to `jakarta.*`. This is a namespace change for Java EE APIs moved to Jakarta EE, not a rule to rename every package starting with `javax`.

Spring Boot 3 uses Spring Framework 6 and Jakarta EE 10. APIs such as Servlet, Persistence, and Bean Validation moved to `jakarta.*` packages; corresponding dependencies must also be upgraded. Spring Boot 4 continues using the `jakarta` namespace, built on Jakarta EE 11 and Spring Framework 7. Therefore, when moving from Boot 3 to Boot 4, the main work is upgrading API/specification versions and compatible libraries, not performing another `javax` to `jakarta` rename.

For springdoc-openapi, you must check two independent axes:

1. The namespace of platform APIs used by the application, such as `jakarta.servlet` and `jakarta.validation`.
2. The springdoc major version compatible with Spring Boot: 1.x branch for Boot 2, 2.x for Boot 3, and 3.x for Boot 4.

## 1. Why Are There Two Namespaces?

Java EE moved to Jakarta EE after platform stewardship transferred to the Eclipse Foundation. Jakarta EE 9 changed the package namespace from `javax.*` to `jakarta.*` for Jakarta EE APIs. The goal was to establish a new namespace governed by Jakarta EE.

Class names may look identical, but the package is part of a Java type's identity. For example:

`javax.servlet.http.HttpServletRequest`

and

`jakarta.servlet.http.HttpServletRequest`

are two distinct types to the JVM. They are not interchangeable just because they share the same class name. A library compiled against `javax.servlet.Filter` is not automatically compatible with a container expecting `jakarta.servlet.Filter`.

This affects:

- Imports in Java, Kotlin, and Groovy code.
- Direct and transitive dependencies.
- Annotations and interfaces searched by the framework at runtime.
- Method signatures in compiled libraries.
- XML descriptors, service providers, and reflection configs.
- Generated sources, annotation processors, and test fixtures.

## 2. Namespace Boundaries by Spring Generation

| Generation | Spring Framework | Enterprise API Platform | Primary Namespace |
|---|---|---|---|
| Spring Boot 2.x | Spring Framework 5.x (Boot 2.7.x uses 5.3.x) | Java EE 7/8; latest baseline of this line includes Servlet 4.0, JPA 2.2, Bean Validation 2.0 | `javax.*` for Java EE APIs |
| Spring Boot 3.x | Spring Framework 6.x | Jakarta EE 9/10; Boot 3.0 uses Servlet 6.0 and JPA 3.1 | `jakarta.*` for Jakarta EE APIs |
| Spring Boot 4.x | Spring Framework 7.x | Jakarta EE 11 baseline; Servlet 6.1, JPA 3.2, Bean Validation 3.1 | Continues `jakarta.*` |

The specification versions in the table are platform baselines for each generation. Check the compatibility matrix and dependency management of your exact patch release before upgrading an application.

### 2.1. Moving from Boot 2 to Boot 3

This is the largest namespace transition step:

- Spring Boot 3 requires Java 17 or higher.
- Spring Framework 6 moved to the Jakarta EE namespace.
- Jakarta EE APIs used by the application must have compatible dependencies.
- Third-party libraries must provide Jakarta-compatible releases.
- Imports, XML descriptors, and related configurations must be updated.

The Spring Boot migration guide recommends upgrading the application to the latest release in the 2.7.x line before moving to Boot 3. This helps address deprecations and dependencies on the old generation before changing platforms.

### 2.2. Moving from Boot 3 to Boot 4

Boot 4 does not revert to `javax`. Applications continue using the Jakarta namespace, while checking new API levels and dependencies:

- Spring Framework 7.x.
- Jakarta EE 11 baseline.
- Servlet 6.1.
- JPA 3.2.
- Bean Validation 3.1.
- Integration libraries must support Spring Framework 7 and Jakarta EE 11.

Boot 4 also introduces module/starter changes and removes several APIs deprecated in Boot 3. Do not treat compiling after changing the Boot version as proof that all dependencies are compatible.

## 3. Packages That Commonly Must Change

The table below lists common package pairs in Spring applications:

| Previous API | Post-Migration API | Commonly Appears In |
|---|---|---|
| `javax.servlet.*` | `jakarta.servlet.*` | Servlets, Filters, Listeners, request/response |
| `javax.persistence.*` | `jakarta.persistence.*` | JPA entities, repository mappings, persistence annotations |
| `javax.validation.*` | `jakarta.validation.*` | Bean Validation, `@Valid`, constraint annotations |
| `javax.transaction.Transactional`, `javax.transaction.UserTransaction` | `jakarta.transaction.Transactional`, `jakarta.transaction.UserTransaction` | JTA annotations and transaction API |
| `javax.annotation.PostConstruct`, `javax.annotation.PreDestroy`, `javax.annotation.Resource` | `jakarta.annotation.*` | Lifecycle and resource injection |
| `javax.inject.*` | `jakarta.inject.*` | JSR-330 `@Inject`, `@Named`, `@Qualifier` |
| `javax.websocket.*` | `jakarta.websocket.*` | WebSocket endpoints and sessions |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` | JAX-RS API and implementations |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` | JAXB marshalling/unmarshalling |
| `javax.mail.*` | `jakarta.mail.*` | Mail API |

Only replace packages belonging to the corresponding specification. Some libraries may use APIs with similar names from another namespace; check the library's documentation and dependencies before editing.

For Dependency Injection, identify the exact artifact in use. Jakarta Dependency Injection 2.x provides the `jakarta.inject` package; older libraries compiled against `javax.inject` may still need their own compatible release. Update imports and dependencies together according to the specification version chosen by the application.

### 3.1. `javax` Packages That Remain Unchanged

Not every `javax` package belongs to Java EE/Jakarta EE. Many packages are part of Java SE and do not change namespaces:

| Package Keeping `javax` | Examples |
|---|---|
| `javax.sql` | `DataSource`, `ConnectionPoolDataSource` |
| `javax.transaction.xa` | `XAResource`, `XAException`, `Xid` |
| `javax.crypto` | `Cipher`, `SecretKey`, `Mac` |
| `javax.net` and `javax.net.ssl` | `SocketFactory`, `SSLContext`, `SSLSocket` |
| `javax.xml.parsers` | `DocumentBuilder`, `SAXParser` |
| `javax.xml.stream` | `XMLInputFactory`, `XMLStreamReader` |
| `javax.naming` | `Context`, `InitialContext` |
| `javax.management` | JMX API |
| `javax.annotation.processing` | Java annotation processing API |

For example, `javax.sql.DataSource` remains the right type when an application uses JDBC. Changing it to `jakarta.sql.DataSource` is wrong because no such Jakarta SQL API exists.

**Practical rule:** determine whether a package belongs to Java SE or a Jakarta EE specification before replacing imports. Never run a global find-and-replace from `javax` to `jakarta`.

## 4. Migrating Imports in Spring Boot Code

### 4.1. Servlet API

Before migration:

~~~java
import java.io.IOException;
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;

public class RequestAuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain
    ) throws IOException, ServletException {
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        chain.doFilter(httpRequest, response);
    }
}
~~~

After migration:

~~~java
import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;

public class RequestAuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain
    ) throws IOException, ServletException {
        HttpServletRequest httpRequest = (HttpServletRequest) request;
        chain.doFilter(httpRequest, response);
    }
}
~~~

Filter logic can stay the same, but all Servlet types in method signatures must share the container's namespace. A `javax.servlet.Filter` cannot be registered as a `jakarta.servlet.Filter`.

### 4.2. Bean Validation

Before migration:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.Positive;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive long price
) {}

public ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
) {
    // handle request
}
~~~

After migration:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive long price
) {}

public ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
) {
    // handle request
}
~~~

If constraint annotations from `javax.validation` are still used, Boot 3's Jakarta Validation provider may not recognize them as Jakarta API constraints. As a result, validation may not run or integration with annotation types may fail.

### 4.3. JPA

Before migration:

~~~java
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "products")
class ProductEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
~~~

After migration:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
class ProductEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
~~~

Annotation names and mapping logic in the example do not change. However, the JPA provider and specification version change with the Spring generation; verify queries, mappings, dialects, and schema generation with integration tests.

### 4.4. Spring Annotations Do Not Automatically Change Namespaces

Annotations belonging to Spring Framework retain the `org.springframework.*` package, for example:

- `org.springframework.web.bind.annotation.RestController`
- `org.springframework.web.bind.annotation.RequestMapping`
- `org.springframework.beans.factory.annotation.Autowired`
- `org.springframework.transaction.annotation.Transactional`
- `org.springframework.stereotype.Service`

Distinguish `org.springframework.transaction.annotation.Transactional` from `javax.transaction.Transactional`. If the application uses the JTA annotation, the corresponding package changes to `jakarta.transaction.Transactional`. Do not change a Spring annotation to a `jakarta` package just because the annotation name looks the same.

## 5. Dependencies Must Also Change with the Namespace

Updating imports while keeping old API JARs will cause compile or runtime failures. For applications using Spring Boot starters, prefer dependencies managed by Spring Boot instead of manually pinning Jakarta API versions.

| Old Dependency | Replacement Direction |
|---|---|
| `javax.servlet:javax.servlet-api` | `jakarta.servlet:jakarta.servlet-api` |
| `javax.validation:validation-api` | `jakarta.validation:jakarta.validation-api` |
| `javax.persistence:javax.persistence-api` | `jakarta.persistence:jakarta.persistence-api` |
| Legacy Java EE API bundles | Corresponding Jakarta API artifacts managed by platform/dependency management |

In Spring Boot, it is usually best to use the appropriate starter, such as `spring-boot-starter-validation` or `spring-boot-starter-data-jpa`, rather than adding separate API and implementation dependencies manually. The Servlet API is typically supplied via the web starter and container; declare it directly only for specific build requirements like compile-only/provided.

### 5.1. Do Not Mix Both APIs of the Same Specification

An older dependency can pull in `javax.servlet-api` while the application runs on a Jakarta container. Even if application source code migrated to `jakarta.servlet`, the old library may still reference `javax.servlet` types.

Inspect the dependency tree:

~~~bash
# Maven
mvn dependency:tree

# Find legacy Java EE artifacts in the dependency tree
mvn dependency:tree -Dincludes=javax.servlet:*,javax.validation:*,javax.persistence:*

# Gradle
./gradlew dependencies --configuration runtimeClasspath
~~~

When an old dependency is found:

1. Upgrade the library to a Jakarta-supporting release.
2. If the old dependency is no longer used, remove it from the build.
3. If a transitive dependency pulls in the old API, check for a newer release or apply controlled exclusions.
4. Do not blindly exclude the old API if the library still requires it; in that case replace the library or isolate a compatibility boundary.

Do not keep both APIs of the same specification simultaneously just to make compilation pass. The two namespaces are two independent type sets and can cause errors when frameworks exchange objects across interfaces.

## 6. Third-Party Libraries Must Support Jakarta

An application may have updated its imports and still fail because an older library was compiled against `javax.*`. Library groups to audit:

- Servlet filters, listeners, security adapters, and embedded container extensions.
- JPA providers, Hibernate extensions, custom types, and auditing libraries.
- Validation providers and custom constraints.
- SOAP/JAX-WS, JAXB, JAX-RS, mail, and WebSocket implementations.
- Report engines, document processors, and server integration libraries.
- Test utilities, mock servers, test containers, and annotation processors.

A library compatible with Boot 2 is not automatically compatible with Boot 3. Check the library's release notes or compatibility matrix. If the vendor provides a Jakarta branch, upgrade to it; if not, consider replacing it or keeping the legacy component in a separate service with a clear communication boundary.

### 6.1. Why Can't You Simply Cast?

Suppose an older library accepts:

~~~java
public void register(javax.servlet.Filter filter) {
    // ...
}
~~~

The Boot 3 application provides:

~~~java
jakarta.servlet.Filter filter = new RequestAuditFilter();
~~~

These two types have no inheritance relationship. You cannot cast `jakarta.servlet.Filter` to `javax.servlet.Filter`. You need a library version compiled with the Jakarta API or an adapter replacement.

## 7. springdoc-openapi and Swagger Annotations During Migration

The application's Jakarta namespace and the springdoc version are two separate decisions.

| Spring Boot | Spring Framework | Appropriate springdoc Branch | Notes |
|---|---|---|---|
| 2.x | 5.3.x | 1.x; 1.8.0 is the last open-source release for Boot 2/1 | Uses legacy modules. |
| 3.x | 6.x | 2.x | Uses springdoc v2 starter modules. |
| 4.x | 7.x | 3.x | Uses springdoc branch compatible with Boot 4. |

Dependency examples for Spring MVC:

~~~xml
<!-- Spring Boot 2 / springdoc v1 -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.8.0</version>
</dependency>
~~~

~~~xml
<!-- Spring Boot 3 / springdoc v2 -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

~~~xml
<!-- Spring Boot 4 / springdoc v3 -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Set the version according to the current compatibility matrix. Do not use springdoc 3.x with Boot 3 or springdoc 2.x with Boot 4 just because the artifact names look the same.

### 7.1. Swagger Annotations Do Not Move to `jakarta`

OpenAPI annotations remain under the package:

`io.swagger.v3.oas.annotations.*`

For example, `@Operation`, `@Parameter`, `@Schema`, `@ApiResponse`, and `@SecurityScheme` do not change to `jakarta.swagger.*`. They are not Jakarta EE APIs.

### 7.2. springdoc Packages May Change Separately

From springdoc v1 to v2, several packages/classes changed:

| springdoc v1 | springdoc v2 |
|---|---|
| `org.springdoc.core.GroupedOpenApi` | `org.springdoc.core.models.GroupedOpenApi` |
| `org.springdoc.core.SpringDocUtils` | `org.springdoc.core.utils.SpringDocUtils` |
| `org.springdoc.api.annotations.ParameterObject` | `org.springdoc.core.annotations.ParameterObject` |
| `org.springdoc.core.customizers.OpenApiCustomiser` | `org.springdoc.core.customizers.OpenApiCustomizer` |

These are springdoc API changes, not Java EE namespace changes. Handle them alongside each other while classifying causes accurately to avoid wrong import replacements.

## 8. XML Descriptors, Service Loaders, and Generated Sources

Migration is not limited to `.java` files. Also search:

- `web.xml`, `web-fragment.xml`.
- `persistence.xml`, `orm.xml`.
- `beans.xml` and Jakarta EE module descriptors.
- `META-INF/services/*`.
- `module-info.java`.
- Generated sources under `target/generated-sources` or `build/generated`.
- Reflection/native-image configurations.
- Kotlin, Groovy, and test sources.

For example, an older Servlet descriptor might use the Java EE XML namespace:

~~~xml
<web-app xmlns="http://xmlns.jcp.org/xml/ns/javaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://xmlns.jcp.org/xml/ns/javaee
           http://xmlns.jcp.org/xml/ns/javaee/web-app_4_0.xsd"
         version="4.0">
</web-app>
~~~

With Servlet 6.0, the descriptor uses the Jakarta EE namespace and corresponding schema:

~~~xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           https://jakarta.ee/xml/ns/jakartaee
           https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">
</web-app>
~~~

When upgrading to Boot 4/Servlet 6.1, update descriptors to the matching schema version. If the application does not package a descriptor because it uses Java-based Spring configuration, do not create one just to complete migration.

### 8.1. Service Provider Files

A library may register implementations via `META-INF/services`. If the interface belongs to a Jakarta API, the interface name in the service file must also be the new Jakarta name. Check service files packaged in JARs as well as files generated by annotation processors.

## 9. How to Find Imports That Need Changing

Start with scoped searches instead of replacing every `javax` string:

~~~bash
# Example: search common Jakarta EE namespaces in sources
rg -n "javax\.(servlet|persistence|validation|transaction|annotation|inject|ws\.rs|websocket|xml\.bind|mail)" \
  src pom.xml build.gradle build.gradle.kts

# Find remaining imports after migration
rg -n "^import javax\.(servlet|persistence|validation|transaction)" \
  src
~~~

After updating, check in reverse for old Java EE dependencies:

~~~bash
mvn dependency:tree | rg "javax\.(servlet|persistence|validation)|javax.servlet-api|validation-api"
~~~

Search commands only generate a list to review. A match on `javax.annotation.processing` or `javax.sql` is not a migration bug. Inspect the exact package and API before editing.

## 10. Common Errors When Namespaces Are Inconsistent

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `package javax.servlet does not exist` | Old Servlet dependency removed or source not yet migrated | Update imports to `jakarta.servlet` and use compatible dependency/container. |
| `package jakarta.validation does not exist` | Appropriate Jakarta Validation API/starter missing | Add validation starter or Boot-managed dependency. |
| `NoClassDefFoundError: javax/servlet/...` | An older library still references the old Servlet namespace | Upgrade/replace library, check dependency tree and runtime classpath. |
| `ClassNotFoundException: javax.persistence...` | Old JPA extension or persistence library | Upgrade to a release supporting Jakarta Persistence. |
| `ClassCastException` between `javax` and `jakarta` types | Two APIs with the same name but different type identities | Align all dependencies to one namespace for that specification. |
| Filter not recognized by container | Filter implements `javax.servlet.Filter` on a Jakarta container | Switch to `jakarta.servlet.Filter` or upgrade the library providing the filter. |
| Bean Validation does not run | Constraint annotations still come from `javax.validation` | Switch annotations and provider to Jakarta Validation. |
| JPA entities not discovered | Entity uses `javax.persistence.Entity` in a Jakarta runtime | Update imports, check package scan and provider. |
| Springdoc does not display endpoints or schemas | Incompatible Springdoc version or old dependency breaking startup/scan | Choose the right springdoc branch and check generated OpenAPI. |
| `NoSuchMethodError` in an integration library | Library compiled against a different generation of APIs/framework | Align library and Spring/Jakarta API versions; inspect classpath. |

Not every `NoSuchMethodError` is caused by namespaces. It is a general linkage error; identify the loaded class and method descriptor before drawing conclusions.

## 11. Inspecting Dependencies and Classpath

### 11.1. Maven

Inspect the dependency tree and search for old APIs:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api
mvn dependency:tree -Dincludes=javax.validation:validation-api
mvn dependency:tree -Dincludes=javax.persistence:javax.persistence-api
~~~

Check which dependency brings the old API onto the runtime classpath. If the library already has a Jakarta version, upgrade it before adding exclusions. Use the Spring Boot parent/BOM to manage versions uniformly.

### 11.2. Gradle

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency javax.servlet --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet --configuration runtimeClasspath
~~~

`compileClasspath` helps catch old types still present at compile time; `runtimeClasspath` helps catch old libraries packaged or loaded at runtime.

### 11.3. Checking Bytecode When Source No Longer Has Old Imports

Compiled libraries may still reference `javax.*` even when application source no longer does. `jdeps` can help inspect class-level dependencies:

~~~bash
jdeps --ignore-missing-deps -verbose:class target/application.jar
~~~

For Spring Boot executable JARs, inspect libraries inside `BOOT-INF/lib` if the tool does not automatically read nested JARs. You can unpack the artifact into a temporary build directory and run `jdeps` on individual JARs under investigation.

## 12. Migration Tools and Controlled Usage

Several tools can reduce repetitive work:

| Tool | Support |
|---|---|
| OpenRewrite | Recipes to upgrade Spring Boot and migrate some packages/imports, dependencies, and configs. |
| Spring Boot Migrator | Analyzes certain changes and suggests migration steps. |
| IntelliJ IDEA migration/refactoring | Finds usages, updates imports, and assists scoped refactoring. |
| `jdeps` | Analyzes class and package dependencies in bytecode. |

Automated tools should only produce diffs for review. Never run a recipe and ignore transitive dependencies, XML descriptors, generated code, or libraries lacking Jakarta releases.

Safe workflow:

1. Commit or create a migration branch for a rollback point.
2. Run the tool on a selected module scope.
3. Review every changed package.
4. Inspect the dependency tree and generated sources.
5. Run compile, unit tests, and integration tests.
6. Compare generated OpenAPI documents before and after.

## 13. Upgrade Procedure for Applications with springdoc

### 13.1. From Boot 2 to Boot 3

1. Upgrade the application to the latest release of the Boot 2.7.x line.
2. Record Java, Spring Boot, Spring Framework, springdoc, and related dependency versions.
3. Check which libraries still depend on `javax.servlet`, `javax.persistence`, or `javax.validation`.
4. Upgrade third-party libraries to Jakarta-supporting versions.
5. Switch Jakarta EE imports to `jakarta.*`; keep Java SE `javax.*`.
6. Update dependency coordinates or use Spring Boot-managed starters.
7. Upgrade springdoc from v1 to v2 and update springdoc-specific starters/imports.
8. Update XML descriptors, service loaders, and generated sources if present.
9. Run compile, tests, and runtime checks.
10. Compare OpenAPI JSON/YAML and Swagger UI against the baseline.

### 13.2. From Boot 3 to Boot 4

1. Upgrade the application to the latest release of the Boot 3.5.x line.
2. Audit deprecations already present in Boot 3.
3. Upgrade Spring Framework and Jakarta APIs to Boot 4/Jakarta EE 11.
4. Check Servlet 6.1, JPA 3.2, and Bean Validation 3.1 compatibility.
5. Review new modules/starters and removed or replaced integrations.
6. Choose springdoc v3 compatible with Boot 4.
7. Do not run a global `javax` → `jakarta`; most applications already use Jakarta from Boot 3.
8. Run all integration tests and check OpenAPI output.

## 14. Verifying Springdoc After Migration

Springdoc reads controllers, annotations, Spring configuration, validation constraints, and models to generate OpenAPI JSON/YAML. If namespaces are inconsistent, some annotations or data types may not be recognized by the framework as expected.

After upgrading, verify:

- `/v3/api-docs` returns HTTP 200 and valid JSON.
- `/v3/api-docs.yaml` returns YAML if the application enables that endpoint.
- Controller paths and HTTP methods still appear.
- `@Valid` and Jakarta constraints are applied.
- JPA DTO/entity mappings do not alter responses unexpectedly.
- `@Operation`, `@Parameter`, `@Schema`, and `@ApiResponse` are still read.
- Security schemes and operation requirements are not lost.
- Swagger UI loads the right OpenAPI document.

### 14.1. MockMvc Regression Test

Example checking that the document still contains an operation after migration:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiNamespaceMigrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiStillContainsProductOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/products'].get").exists());
    }
}
~~~

This is a regression test for the document. Additional HTTP integration tests are needed to verify request validation, serialization, and runtime responses actually work after changing namespaces.

## 15. Common Migration Mistakes

- **Replacing every `javax` string with `jakarta`**: breaks Java SE packages such as `javax.sql` or `javax.crypto`.
- **Changing imports only while keeping old dependencies**: compile/runtime may still load `javax` APIs.
- **Upgrading Spring Boot only without upgrading third-party libraries**: old filters, JPA extensions, or validation libraries become incompatible.
- **Mixing `javax.servlet.Filter` and `jakarta.servlet.Filter`**: Jakarta containers do not recognize old Servlet types.
- **Keeping `javax.validation` annotations**: Jakarta Validation providers do not treat them as matching constraints.
- **Forgetting XML descriptors**: `web.xml`, `persistence.xml`, or `orm.xml` may still have old schema namespaces.
- **Forgetting generated sources and service loaders**: a clean build may regenerate old imports or provider names.
- **Confusing Spring's `@Transactional` with JTA**: the two annotations have different packages and distinct semantics.
- **Confusing Swagger annotations with Jakarta annotations**: `io.swagger.v3.oas.annotations` does not change namespaces.
- **Using the wrong springdoc major line**: Boot 2 uses 1.x, Boot 3 uses 2.x, Boot 4 uses 3.x.
- **Checking compile only**: linkage errors may surface only when Spring initializes filters, entity managers, or validation providers.
- **Skipping OpenAPI semantic diff**: required flags, formats, enums, or responses may change even when the app still starts.
- **Using exclusions to hide old dependencies**: libraries may still call excluded classes and fail at runtime.

## 16. Review Checklist

- [ ] Confirmed whether upgrading Boot 2 → 3 or Boot 3 → 4.
- [ ] Spring Framework and Jakarta EE baselines belong to the right generation.
- [ ] Only Jakarta EE packages moved to `jakarta.*`.
- [ ] Java SE packages like `javax.sql`, `javax.crypto`, and `javax.net.ssl` kept intact.
- [ ] Servlet, JPA, Validation, and JTA imports audited.
- [ ] Spring annotations `org.springframework.*` not mistakenly changed.
- [ ] Swagger annotations `io.swagger.v3.*` not mistakenly changed.
- [ ] Dependency tree has no unnecessary legacy Java EE APIs.
- [ ] Third-party libraries have Jakarta-supporting releases.
- [ ] XML descriptors, service loaders, and generated sources inspected.
- [ ] Springdoc major version compatible with Spring Boot.
- [ ] Compile, unit tests, and integration tests all pass.
- [ ] OpenAPI JSON/YAML verified and diffed against baseline.
- [ ] Swagger UI, validation, security, and JPA mappings work properly.

## 17. References

- [Spring Boot 3.0 Migration Guide – Jakarta EE](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide#jakarta-ee)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Framework Versions – Java/Jakarta EE versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions#javajakarta-ee-versions)
- [Jakarta EE – Unaffected non-EE javax packages](https://github.com/jakartaee/platform/blob/main/namespace/unaffected-packages.adoc)
- [Jakarta Dependency Injection 2.0](https://jakarta.ee/specifications/dependency-injection/2.0/)
- [Java SE – javax.transaction.xa package](https://docs.oracle.com/en/java/javase/17/docs/api/java.transaction.xa/javax/transaction/xa/package-summary.html)
- [springdoc-openapi v2 – Migration from v1](https://springdoc.org/v2/#migrating-from-springdoc-openapi-v1)
- [springdoc-openapi – Current compatibility matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot)
- [OpenRewrite – Spring Boot migration recipes](https://docs.openrewrite.org/recipes/java/spring/boot3)

Namespace migration is a change in Java types and dependencies, not just editing import syntax. Boot 2 to Boot 3 moves Java EE APIs to Jakarta; Boot 3 to Boot 4 continues Jakarta and raises the baseline to EE 11. Audit source code, the dependency tree, third-party libraries, XML, and generated code; keep Java SE `javax` packages untouched; and then verify springdoc with OpenAPI regression tests and HTTP runtime tests.
