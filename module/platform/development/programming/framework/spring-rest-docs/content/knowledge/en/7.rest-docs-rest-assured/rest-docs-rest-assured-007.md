# REST Assured 5 and Spring REST Docs Compatibility Requirements

## 1. Why Care About Version Compatibility?

**Spring REST Docs** generates REST API documentation from executed HTTP tests. You can use Spring MVC Test/MockMvc, WebTestClient, or **REST Assured 5** as the client that calls and verifies the API. When choosing REST Assured, the project must align versions across Java, Spring Framework/Spring Boot, Spring REST Docs, and the REST Assured artifacts.

Successful dependency resolution alone does not prove libraries are compatible at runtime. Some failures only surface when tests initialize filters, serialize JSON, process responses, or generate snippets. Therefore, select supported major versions, manage versions consistently, and run a minimal documentation test before scaling out to the full API.

With Spring REST Docs **3.0.6**, the documentation requires a minimum of **Java 17**, **Spring Framework 6**, and specifically for the `spring-restdocs-restassured` module, **REST Assured 5.2**. That means REST Assured 5.2 is the minimum baseline for this integration, not a requirement to pin exactly 5.2. The official documentation specifies that the current integration targets REST Assured 5. <https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/>.

## 2. Compatibility Matrix to Check

| Component | Requirement When Using Spring REST Docs 3.0.6 | Notes |
| --- | --- | --- |
| JDK | Java 17 or higher | Check both the JDK running Gradle/Maven and the compile/test toolchain. |
| Spring Framework | 6.x | Spring Boot 3.x typically manages Spring Framework 6; still choose the right Boot version and project dependency set. |
| Spring REST Docs | 3.0.x (e.g., 3.0.6) | All `spring-restdocs-*` modules should use the same version. |
| REST Assured | 5.2 or higher within the 5.x line | The `spring-restdocs-restassured` 3.0.x module is documented for REST Assured 5. |
| JUnit | JUnit Jupiter or JUnit 4 per the corresponding integration | Examples in this article use JUnit 5 with `RestDocumentationExtension`. |
| Build | Gradle or Maven with clear dependency management | Tests must run before the snippet compilation step. |

This matrix is a guide for the REST Docs 3.0.x and REST Assured 5 combination, not a guarantee that arbitrary patch versions of Spring Boot, Jackson, Groovy, or HTTP clients can be mixed freely. Use your project's BOM/parent and inspect the dependency tree if conflicts arise.

### Distinguishing REST Assured 5, 6, and 7

- **REST Assured 5.x:** the release line required by Spring REST Docs 3.0.x's `spring-restdocs-restassured` integration; a minimum of 5.2 is required per the Spring REST Docs documentation.
- **REST Assured 6.x:** a separate major version. REST Assured 6 documentation specifies a Java 17 baseline and upgrades the underlying Groovy version to 5.x; major changes can affect dependencies and integrations. Do not swap 5.x artifacts for 6.x and assume Spring REST Docs 3.0.x remains supported simply because it compiles.
- **REST Assured 7.x:** also a separate major version, introducing module/path engine changes that require checking its corresponding documentation. Do not take REST Assured 7 configuration examples and apply them verbatim to a project expected to use REST Assured 5.

When upgrading REST Assured across major versions, re-check compatibility docs for both projects and run real documentation tests. The REST Assured 6.0 release notes mention Java 17+, Groovy 5.x, and Spring 7 support changes—a clear sign that a major upgrade is a platform shift, not just a version bump. <https://rest-assured.io/release-notes/6-0/>.

## 3. Required Artifacts and Their Roles

For a Spring Boot project using REST Assured to send HTTP requests to a running server, you typically need these test artifacts:

| Artifact | Group ID | Role |
| --- | --- | --- |
| `rest-assured` | `io.rest-assured` | `given()`, `when()`, `then()` DSL, HTTP requests, and assertions. |
| `spring-restdocs-restassured` | `org.springframework.restdocs` | Filter integrating REST Assured with Spring REST Docs to generate snippets. |
| `spring-boot-starter-test` | `org.springframework.boot` | Spring Boot testing infrastructure, JUnit Jupiter, and common test utilities. |
| `rest-assured-bom` (when needed) | `io.rest-assured` | Aligns versions consistently across REST Assured modules. |

Only add modules you actually need. For instance, tests querying JSON via GPath may need the JSON path module matching your REST Assured release line; modules specific to MockMvc or WebTestClient are unnecessary if tests only use REST Assured against an HTTP server. REST Assured 5 provides artifacts under `io.rest-assured`; all REST Assured modules must stay on the same version. REST Assured documents this rule at <https://rest-assured.io/docs/modules/>.

## 4. Managing Dependencies with Gradle

### 4.1. Declaring Dependencies

The example below uses **REST Assured 5.5.7** as an illustrative version in the 5.x line. When applying it, verify the approved patch version in your organization's repository and align all other REST Assured artifacts to that same version. Spring REST Docs in this example uses 3.0.6:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    testImplementation 'io.rest-assured:rest-assured:5.5.7'
    testImplementation 'org.springframework.restdocs:spring-restdocs-restassured:3.0.6'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`testImplementation` keeps libraries on the test classpath; do not add them to the application runtime classpath merely to generate documentation. If the project manages dependencies via the Spring Boot plugin/BOM, prefer centralized management over scattering version numbers across individual dependencies.

### 4.2. Managing with the REST Assured BOM

If you use multiple REST Assured modules, import `rest-assured-bom` to enforce the same version across all modules:

```groovy
dependencies {
    testImplementation platform('io.rest-assured:rest-assured-bom:5.5.7')

    testImplementation 'io.rest-assured:rest-assured'
    testImplementation 'org.springframework.restdocs:spring-restdocs-restassured:3.0.6'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

In this example, the BOM manages only `io.rest-assured:*` artifacts; it does not manage the Spring REST Docs version. Therefore, `spring-restdocs-restassured` still specifies the matching Spring REST Docs version.

Do not declare conflicting versions simultaneously for `rest-assured`, `json-path`, `xml-path`, or other REST Assured modules. If one module explicitly declares 5.5.7 while another pulls in a different patch/major version, inspect the dependency report and exclude the conflicting transitive source intentionally.

## 5. Managing Dependencies with Maven

### 5.1. Direct Declaration

In a project already managing Spring Boot dependencies via parent/BOM, place the test dependencies in `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>io.rest-assured</groupId>
        <artifactId>rest-assured</artifactId>
        <version>5.5.7</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-restassured</artifactId>
        <version>3.0.6</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

This assumes the parent/BOM already manages `spring-boot-starter-test`. Without dependency management, declare versions for all artifacts. Avoid mixing standalone Spring Framework versions alongside the Spring Boot BOM, as that can produce an inconsistent Spring dependency combination.

### 5.2. Importing the REST Assured BOM

If you use multiple REST Assured artifacts, declare the BOM in `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.rest-assured</groupId>
            <artifactId>rest-assured-bom</artifactId>
            <version>5.5.7</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.rest-assured</groupId>
        <artifactId>rest-assured</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-restassured</artifactId>
        <version>3.0.6</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

A BOM typically manages only artifacts from its own library ecosystem. The REST Assured BOM does not replace the Spring Boot BOM or Spring REST Docs dependency management. If a project imports multiple BOMs, check Maven's import order and precedence rules to verify which final versions get selected.

## 6. Example Test with REST Assured 5 and Spring REST Docs

Suppose the application exposes `GET /api/orders/{id}` and test fixtures ensure order `1001` exists. The API returns:

```json
{
  "id": 1001,
  "status": "CONFIRMED"
}
```

The JUnit 5 test class below uses Spring Boot 3.x, Spring REST Docs 3.0.x, and REST Assured 5.x:

```java
import io.restassured.builder.RequestSpecBuilder;
import io.restassured.http.ContentType;
import io.restassured.specification.RequestSpecification;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;

import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.documentationConfiguration;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    @LocalServerPort
    private int port;

    private RequestSpecification specification;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.specification = new RequestSpecBuilder()
                .setBaseUri("http://localhost")
                .setPort(this.port)
                .setBasePath("/api")
                .addFilter(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetOrder() {
        given(this.specification)
                .accept(ContentType.JSON)
                .pathParam("id", 1001)
                .filter(document("orders-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Order ID")),
                        responseFields(
                                fieldWithPath("id").description("Order ID"),
                                fieldWithPath("status").description("Order status"))))
        .when()
                .get("/orders/{id}")
        .then()
                .statusCode(200)
                .contentType(ContentType.JSON)
                .body("id", equalTo(1001))
                .body("status", equalTo("CONFIRMED"));
    }
}
```

`RANDOM_PORT` starts the embedded HTTP server; `@LocalServerPort` supplies the actual test port. `documentationConfiguration(...)` is attached to `RequestSpecification`, while `document("orders-get", ...)` is attached to the request to be documented. The `/api/orders/{id}` endpoint and fixture must exist in the application under test; JSON field names must match the actual response. This example serves as an integration pattern for an existing API and does not create the controller or order data itself.

## 7. Key Differences When Using REST Assured 5

When choosing REST Assured 5 with Spring REST Docs, pay special attention to:

### 7.1. Use the Right Group ID and Artifacts

Modern REST Assured releases use the `io.rest-assured` group ID. Do not mix legacy `com.jayway.restassured` artifacts with modern artifacts on the same test classpath. Examples based on REST Assured 5 should use `io.restassured.*` and `io.restassured.module.*` packages.

### 7.2. Keep REST Assured Modules Version-Aligned

If tests need JSON path, XML path, or an HTTP client extension, verify all modules match the same REST Assured 5 version. Using the BOM prevents version skew between `rest-assured` and auxiliary modules. Do not add `rest-assured-all` or path modules just assuming every project needs them; add only what your tests actually use.

### 7.3. Keep Spring REST Docs and Spring Framework on the Right Line

Spring REST Docs 3.0.x is built for Spring Framework 6 and requires Java 17. A Spring Boot 3.x project is usually the right foundation, though you still want the Boot BOM to manage Spring libraries consistently. Do not pull a Spring Framework 7 module onto a Spring Boot 3 classpath just to test compatibility with another REST Assured release.

### 7.4. Do Not Infer Compatibility Just Because It Compiles

Some differences surface at runtime or inside filters when Spring REST Docs processes the HTTP exchange. Run the documentation test to verify all of these layers work together:

- The JUnit extension provides `RestDocumentationContextProvider`.
- `RequestSpecification` accepts the `documentationConfiguration(...)` filter.
- `document(...)` observes the request and response.
- Descriptors for path/query parameters, headers, and payloads validate data properly.
- The build generates snippets and the Asciidoctor task reads from the right output directory.

## 8. Inspecting Dependencies and Diagnosing Compatibility Issues

The following commands help verify resolved dependencies. Run them in the project directory:

```bash
# Gradle: inspect relevant test dependencies
./gradlew dependencies --configuration testRuntimeClasspath

# Gradle: inspect REST Assured and Spring REST Docs specifically
./gradlew dependencyInsight --dependency rest-assured --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-restdocs-restassured --configuration testRuntimeClasspath

# Maven: inspect the relevant dependency tree
mvn dependency:tree -Dincludes=io.rest-assured,org.springframework.restdocs,org.springframework
```

On Windows, you can use `gradlew.bat`. Inspect the output to confirm:

1. Only one consistent REST Assured 5 version resolves across all `io.rest-assured` modules in use.
2. `spring-restdocs-restassured` belongs to the same Spring REST Docs release line as other REST Docs modules in the project.
3. Spring Framework resolves to the 6.x line when using REST Docs 3.0.x.
4. JUnit Jupiter and the test engine are present if tests use `@ExtendWith(RestDocumentationExtension.class)`.
5. No legacy `com.jayway.restassured` dependency is mixed onto the classpath unintentionally.

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cannot find `RestAssuredRestDocumentation` | Missing `spring-restdocs-restassured` or wrong version/package. | Check `org.springframework.restdocs:spring-restdocs-restassured` on the test runtime classpath. |
| `NoSuchMethodError` or `ClassNotFoundException` | Skewed transitive dependency or mixed major versions. | Inspect the dependency tree, align REST Assured modules with the BOM, and avoid mixing legacy libraries. |
| REST Docs reports incompatible REST Assured | Using REST Assured below 5.2 or jumping to major 6/7 outside the documented combination for the module. | Use REST Assured 5.2+ in the 5.x line for REST Docs 3.0.x integration. |
| Class version / unsupported class file error | JDK used to run tests is below Spring REST Docs' baseline. | Switch Gradle/Maven toolchain and test JVM to Java 17 or higher. |
| Spring `NoSuchMethodError` | Mixing Spring Framework 5/7 into a project using REST Docs 3.0.x. | Let the Spring Boot BOM manage Spring Framework 6 versions consistently. |
| Tests run but no snippets appear | REST Docs filter not attached or request does not call `document(...)`. | Check `documentationConfiguration(...)`, `.filter(document(...))`, and the output directory. |
| Tests run but descriptors fail | Actual JSON/headers/path parameters do not match documentation. | Inspect responses and align the API or descriptors to the agreed contract. |

Dependency resolution errors and API test failures are separate issues. First verify the classpath and versions; once dependencies are consistent, run a minimal endpoint test before expanding to richer payload and header descriptions.

## 9. Build and CI: Test Before Compiling Documentation

Spring REST Docs generates snippets while tests run. Therefore, the build order must ensure tests pass before Asciidoctor compiles the documentation. Condensed Gradle configuration example:

```groovy
plugins {
    id 'org.asciidoctor.jvm.convert' version '3.3.2'
}

configurations {
    asciidoctorExt
}

ext {
    snippetsDir = file('build/generated-snippets')
}

dependencies {
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor:3.0.6'
}

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    configurations 'asciidoctorExt'
    dependsOn tasks.named('test')
}
```

This adds configuration for the Asciidoctor plugin and dependency; it does not replace the REST Assured/Spring REST Docs dependencies in Section 4. An `.adoc` file can include snippets with:

```asciidoc
= Orders API

== Get Order

=== Request
include::{snippets}/orders-get/http-request.adoc[]

=== Path parameters
include::{snippets}/orders-get/path-parameters.adoc[]

=== Response fields
include::{snippets}/orders-get/response-fields.adoc[]
```

In CI, the pipeline should stop if documentation tests fail. Never publish leftover snippets from an older build as if they came from the current run. If using Markdown, configure an appropriate snippet-processing workflow since default snippets are typically generated in AsciiDoc format.

## 10. Checklist for Choosing and Verifying a Compatible Combination

- [ ] Build and test JDK is Java 17 or higher for Spring REST Docs 3.0.x.
- [ ] Spring Framework is on the 6.x line when using Spring REST Docs 3.0.x.
- [ ] `spring-restdocs-restassured` is added in test scope with a consistent Spring REST Docs version.
- [ ] REST Assured is on the 5.x line and at least 5.2 as required by the integration module.
- [ ] All `io.rest-assured` artifacts in use share the same version or are managed by `rest-assured-bom`.
- [ ] Legacy group ID `com.jayway.restassured` is not mixed with `io.rest-assured`.
- [ ] Executed a real JUnit documentation test and confirmed snippets are generated.
- [ ] Both assertions and request/response descriptors pass before compiling documentation.
- [ ] Build/CI runs tests before Asciidoctor and publishes documentation only from passing builds.

REST Assured 5 is the integration line documented as supported by Spring REST Docs 3.0.x. Keeping Java 17+, Spring Framework 6, and REST Assured 5.2+ in a consistently managed dependency set gives your project a solid foundation for generating snippets from HTTP tests and compiling verifiable API documentation.

## References

- [Spring REST Docs – Requirements and Build configuration](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [REST Assured – Which module do I need, Keep the versions in line, and Spring Boot](https://rest-assured.io/docs/modules/)
- [REST Assured – Release notes 5.2.0](https://rest-assured.io/release-notes/5-2/)
- [REST Assured – Release notes 6.0.0](https://rest-assured.io/release-notes/6-0/)
