# Checking Differences Across Spring Boot Versions

## Learning Objectives

After this lesson, you will be able to:

- Identify Spring Boot differences that affect documentation tests and snippet generation.
- Distinguish versions of Spring Boot, Spring Framework, Spring REST Docs, JUnit, Java, and the Asciidoctor plugin.
- Inspect dependency management via BOM, Gradle/Maven dependency reports, and verify the actual resolved libraries.
- Recognize key changes when upgrading from Spring Boot 2 to Spring Boot 3, especially the Java baseline and `javax`/`jakarta` namespaces.
- Choose the right test context such as `@WebMvcTest` or `@SpringBootTest`, configure `@AutoConfigureRestDocs`, and verify snippets on the new version.
- Build an upgrade checklist to catch compile, runtime, test, and Asciidoctor errors as well as documentation content changes.

## 1. Why Check Differences Across Spring Boot Versions?

Spring REST Docs is typically integrated into a Spring Boot project through test dependencies, test context configuration, and a documentation rendering plugin. When changing the Spring Boot version, the underlying foundation can also change: Spring Framework, Spring Test, Spring Security, Jakarta APIs, the Java baseline, dependency management, and build configuration.

A documentation test that runs on an older project may not run unmodified on a newer one. For example:

- A `javax.servlet.*` import may no longer be valid once the project moves to Jakarta.
- A newer Spring Framework version may require a different test configuration or compatible API.
- Legacy dependencies declared directly may conflict with versions managed by the Spring Boot BOM.
- Changes in Jackson or serialization settings can alter HTTP bodies and snippets.
- Test slices do not load the same beans/filters as a full application context, so observed behavior may shift depending on test configuration.
- The Asciidoctor plugin or Gradle/Maven setup may need updating independently of Spring Boot.

The goal of version verification is not merely a green build. You must confirm that tests still exercise the right application components, documentation is generated from accurate responses, and snippets still describe the API contract your team intends to publish.

## 2. Distinguishing Versions Within a Project

When reading `build.gradle`, `pom.xml`, or dependency reports, do not assume every library shares one version number.

| Component | Role | What to Check on Upgrade |
| --- | --- | --- |
| Spring Boot | Platform managing auto-configuration, dependency management, and build conventions | Plugin/BOM version, Java baseline, migration guide |
| Spring Framework | Spring MVC, WebFlux, Spring Test, and core container | Boot compatibility; API/configuration changes |
| Spring REST Docs | Captures HTTP exchanges and generates snippets | Integration module matching test client; compatibility with Spring/Test |
| JUnit | Test engine and lifecycle | JUnit 4 vs. Jupiter, extensions/rules, and engine dependencies |
| Spring Security | Filters, authentication, and authorization | Test security configuration, matchers, request post-processors |
| Jackson | JSON serialization/deserialization | Field names, null/default handling, date formats, modules, and `ObjectMapper` |
| Asciidoctor plugin/toolchain | Renders documentation from AsciiDoc | Plugin ID/version, tasks, attributes, and Java/Gradle environment |
| Java | Runtime and compiler for app/tests/build | Toolchain, source/target compatibility, API namespaces |

For example, `spring-restdocs-mockmvc` is the integration module for `MockMvc`; `spring-restdocs-webtestclient` is for `WebTestClient`; `spring-restdocs-restassured` is for REST Assured. A project should only declare the module it actually uses.

### 2.1. Do Not Confuse Spring Boot Versions with REST Docs Versions

The Spring Boot version and Spring REST Docs version follow separate release lifecycles. Your project's dependency management may manage certain versions via the Boot BOM, but never assume every plugin or external library outside the BOM is managed automatically.

Safe workflow:

1. Determine the target Spring Boot version.
2. Inspect the BOM/dependency management actually in effect.
3. Check the resolved versions of Spring Framework, Spring Test, and Spring REST Docs.
4. Cross-check compatibility requirements in the release documentation of the relevant libraries.
5. Avoid forcing an individual Spring or REST Docs module version without understanding the impact on remaining modules.

Do not copy a specific version number from another project just because both use Spring Boot. Projects may differ in Java version, build tool, Spring stack, and dependency graph.

## 3. Notable Changes When Upgrading from Spring Boot 2 to Spring Boot 3

Upgrading from Spring Boot 2 to 3 is an important example because the changes extend well beyond version numbers.

### 3.1. Java Baseline

Spring Boot 3 requires Java 17 or later. An older project building on Java 8 or 11 must upgrade its JDK/toolchain and re-verify the compiler, test runtime, CI images, and IDEs.

Areas to review:

- JDK installed on developer machines and CI runners.
- `java` toolchain, `sourceCompatibility`, `targetCompatibility`, or compiler release settings.
- Whether build plugins are compatible with the newer JDK.
- Whether the test runtime uses the exact JDK expected by the build.
- Whether older dependencies remain compatible with the new runtime.

Do not only change the Java version in the build file: verify `java -version`, the Gradle/Maven runtime, and the JDK actually used by CI.

### 3.2. `javax.*` Namespace Moving to `jakarta.*`

Spring Boot 3 pairs with Spring Framework 6 and the Jakarta EE 9+ ecosystem. Many Java EE APIs previously under `javax.*` moved to `jakarta.*`.

Common examples in web applications:

| Before Migration | After Migration |
| --- | --- |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |

Note: not every `javax.*` package moved to `jakarta.*`. Core Java APIs such as `javax.crypto` or `javax.net` remain part of the JDK. Never perform blind project-wide search-and-replace; check each package and the dependency supplying that API.

For REST Docs:

- Tests may import Servlet/Jakarta types through Spring Test libraries.
- Validation annotations on DTOs may need corresponding Jakarta imports.
- Older dependencies relying on superseded Java EE APIs may no longer be compatible.
- Compilation errors in tests may appear before REST Docs is even invoked.

Changing namespaces does not mean renaming every Spring REST Docs import. Let the compiler and dependency tree tell you which classes actually need migration.

### 3.3. Spring Framework and Test Infrastructure

Spring Boot 3 builds on Spring Framework 6. Changes in the framework, Servlet API, and transitive libraries can affect:

- MVC/WebFlux test configuration.
- Request binding and validation.
- Exception handling.
- Security filter chains and test support.
- Serialization and response content.

Accordingly, when a documentation test fails, identify whether it fails at compilation, context startup, request processing, assertions, or snippet generation. Each stage has distinct root causes.

### 3.4. JUnit and Test Dependencies

Many Spring Boot projects use JUnit Jupiter via the test starter, while older projects may still have JUnit 4 or mix both engines. Never infer the engine solely from the Boot major version; read the actual dependencies and test annotations in use.

JUnit 4 uses `@Rule`/`@ClassRule` for certain REST Docs integrations; JUnit Jupiter uses extensions such as `RestDocumentationExtension`. During migration, update lifecycle integration if tests switch frameworks, and ensure CI discovers the test engine properly.

## 4. Choosing the Right Test Context for a Boot Application

Spring Boot provides several ways to build a test context. Your choice affects which components are loaded and which HTTP behavior REST Docs records.

| Test Type | Purpose | Considerations for REST Docs |
| --- | --- | --- |
| `@WebMvcTest` | Tests a Spring MVC slice, typically focusing on controllers and web components | Lightweight; requires mocking service dependencies and checking which security/filters are loaded |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Builds a broader application context and uses `MockMvc` | Covers more real application configuration; takes longer |
| WebFlux test context | Tests reactive handlers/controllers | Use `WebTestClient` integration matching WebFlux configuration |
| Test connecting to a running server | Tests over a real HTTP endpoint | Can use `WebTestClient` or REST Assured depending on server setup |

If documentation describes a 401 status returned by a security filter, a slice test that does not load that filter will not verify that behavior. If documentation describes a date format configured by an application-wide Jackson module, ensure the test context uses the corresponding `ObjectMapper`/module.

## 5. Configuring Spring Boot to Generate Snippets

### 5.1. Dependencies

Gradle Groovy DSL example for a Spring MVC project using `MockMvc` and JUnit Jupiter:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Do not pin a version on each line if the project uses Spring Boot dependency management and the version is managed by the BOM. If the REST Docs version is not managed by your active dependency management, declare an explicit, consistent, and verified-compatible version.

For other test clients, the corresponding integration dependencies are:

```groovy
dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
    // Or the REST Assured module if the project uses REST Assured:
    testImplementation 'org.springframework.restdocs:spring-restdocs-restassured'
}
```

These are alternatives per test client; you do not need to add all three modules if you do not use them. REST Assured and server/test fixture dependencies should be declared separately according to project setup.

### 5.2. Using `@AutoConfigureRestDocs` in Spring Boot Tests

Spring Boot provides `@AutoConfigureRestDocs` to configure REST Docs in the test context. Example with JUnit Jupiter and `MockMvc`:

```java
@WebMvcTest(OrderController.class)
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderControllerDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void getOrder() throws Exception {
        given(orderService.findById(42L))
                .willReturn(new OrderResponse(42L, "PAID"));

        mockMvc.perform(get("/api/orders/{id}", 42)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andDo(document("orders-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Order ID")
                        ),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Order ID"),
                                fieldWithPath("status")
                                        .description("Order status")
                        )
                ));
    }
}
```

This is an illustrative pattern for a Boot test slice. Declare the corresponding static imports and test fixtures, such as `given`, `get`, `status`, `jsonPath`, `document`, `pathParameters`, `parameterWithName`, `responseFields`, and `fieldWithPath`. `@MockBean` was common in earlier Spring Boot generations; in newer Spring lines, check the recommended replacement API for your project version, such as current bean-override/test-mock support. Do not copy old mock annotations without checking deprecations for your version.

`@AutoConfigureRestDocs` configures integration with the test; `document(...)` still specifies which snippets and descriptors to generate. The annotation does not write field descriptions or verify business semantics automatically.

### 5.3. `@WebMvcTest` or `@SpringBootTest`?

Choose `@WebMvcTest` when you need fast MVC-layer tests and can supply dependencies via mocks/fakes. Choose `@SpringBootTest` combined with `@AutoConfigureMockMvc` when broader application configuration—such as converters, advice, security, or bean wiring—is required.

Full-context example:

```java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderApiDocumentationTest {
    @Autowired
    MockMvc mockMvc;

    // HTTP tests and document(...) calls go here.
}
```

Full context does not automatically guarantee the test mirrors production completely: profiles, databases, external services, gateways, and runtime environments can still differ. Document test scope clearly so readers know which layer produced the snippets.

## 6. Checking Resolved Dependencies

When upgrading Boot, do not just read the versions written in `build.gradle`; inspect the versions actually resolved after dependency management and conflict resolution.

### 6.1. Gradle

Useful commands:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

To see why a specific dependency version was selected:

```bash
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
```

On Windows, you can use `gradlew.bat` instead of `./gradlew`.

Focus checks on:

- Only one compatible version of each Spring Framework module is present.
- Spring Test matches the active Spring Framework/Boot version.
- The right REST Docs module is present and resolves to the expected version.
- The JUnit engine is included in the test runtime.
- No legacy dependency pulls in an incompatible Servlet/Validation API.

### 6.2. Maven

You can inspect the dependency tree:

```bash
mvn dependency:tree -Dscope=test
```

If needed, filter output for `org.springframework`, `spring-restdocs`, `junit`, or `jakarta`. Distinguish direct dependencies from transitive ones; an outdated library may be pulled in by another starter or plugin.

### 6.3. Reading Dependency Warnings

| Indicator | Possible Meaning |
| --- | --- |
| Dependency version changed unexpectedly | A BOM, plugin, or other dependency is overriding it |
| Two Spring Framework lines of different major/minor versions | Risk of an inconsistent classpath |
| Both `javax` and `jakarta` APIs for the same purpose | Legacy dependency remains or migration is incomplete |
| JUnit tests compile but do not run | Test engine/platform or discovery configuration is misconfigured |
| REST Docs class not found | Missing integration module or wrong version/classpath |

Do not resolve conflicts by immediately excluding dependencies. Identify which library requests it, which API is in use, and whether the resolved version is compatible.

## 7. Inspecting Snippets After an Upgrade

A green build is only the first step. Compare snippets before and after:

| Artifact | What to Verify |
| --- | --- |
| `http-request` | Are method, URI, query string, and request headers still accurate? |
| `request-fields` | Did field paths, field names, types, or payload structure change? |
| `http-response` | Do status, response headers, and JSON body still preserve the contract? |
| `response-fields` | Do strict descriptors accurately cover new or changed fields? |
| Error snippets | Do exception handlers, validation, and security still return expected statuses/bodies? |
| Asciidoctor output | Do includes, attributes, headings, and HTML rendering succeed? |

A newer Boot/Spring version may alter serialization or output ordering in examples. Not every diff is a breaking change, yet every difference should be explained before release.

### 7.1. Do Not Confuse Formatting Diffs with Contract Changes

For example, the two JSON payloads below share the same structure and values but differ in whitespace:

```json
{"id":42,"status":"PAID"}
```

```json
{
  "id": 42,
  "status": "PAID"
}
```

A formatting diff is not necessarily a contract change. Conversely, renaming `status` to `paymentStatus` is a structural change observable by clients. During review, distinguish:

- Changes in snippet display formatting.
- Changes in field or header ordering if any consumer invalidly depends on order.
- Changes in actual field names, types, values, status codes, or headers.
- Changes in error mapping and validation behavior.

## 8. Configuring Asciidoctor and Builds After Migration

Spring Boot manages application/test dependencies, while the Asciidoctor plugin is a separate build component. Check the plugin version and Gradle/Maven version independently; do not assume the plugin must share the same version number as Spring Boot.

Gradle Groovy DSL example with the Asciidoctor plugin already declared in `plugins`:

```groovy
configurations {
    asciidoctorExt
}

dependencies {
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

def snippetsDir = file("$buildDir/generated-snippets")

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    configurations 'asciidoctorExt'
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
}
```

This is a task-dependency configuration snippet, not a complete build file. Ensure:

1. The test output directory matches where Asciidoctor reads snippets.
2. The `snippets` attribute is assigned properly to the rendering task.
3. Tests run before Asciidoctor.
4. A clean build leaves no stale snippets from deleted or renamed tests.
5. The Asciidoctor plugin is compatible with the active Gradle/JDK version.
6. Missing includes or rendering errors are configured to fail CI if complete documentation is required.

Illustrative command:

```bash
./gradlew clean test asciidoctor
```

With Maven, inspect lifecycle/plugin executions to confirm snippet-generating tests run before the Asciidoctor goal. Do not assume Gradle and Maven setups share the same default paths or execution order.

## 9. Verification Workflow When Upgrading Spring Boot

Follow these steps in order:

**Step 1 — Record the baseline.** Record the current versions of Boot, Java, Spring REST Docs, JUnit, test client, Asciidoctor plugin, and active build commands. Capture sample snippet outputs for several key endpoints.

**Step 2 — Read migration guides.** Review the Spring Boot and Spring Framework release notes/migration guides across the target version range. Identify Java baselines, Jakarta changes, deprecated APIs, and test configuration changes.

**Step 3 — Upgrade dependency management.** Update the Boot plugin/BOM, toolchain, and direct dependencies; remove unnecessary version overrides. Inspect the dependency tree before resolving conflicts.

**Step 4 — Update source and tests.** Migrate imports, annotations, or test APIs per compiler errors and migration guides. Verify JUnit engine discovery and the corresponding REST Docs integration still work.

**Step 5 — Run tests by layer.** Execute unit tests, MVC/WebFlux documentation tests, and key integration tests. On failure, isolate whether it occurs at compile, context startup, request handling, assertions, or snippet generation.

**Step 6 — Regenerate and review snippets.** From a clean output, compare HTTP requests/responses, payloads, parameters, and headers. Confirm every diff is intentional and aligns with the contract.

**Step 7 — Render and inspect documentation.** Run the Asciidoctor/Markdown renderer, verify includes, and open the generated HTML to check content.

**Step 8 — Run CI on the target JDK/build image.** Release only when both the build and documentation are produced from the same commit/application version.

## 10. Common Upgrade Errors

| Error | Common Cause | How to Investigate |
| --- | --- | --- |
| `ClassNotFoundException`/`NoClassDefFoundError` for `javax.*` | Legacy Java EE dependency remains on classpath after migration | Find the dependency pulling the old API; replace with a compatible dependency instead of mass-renaming `javax` |
| Test compile fails on Servlet/Validation imports | Source still uses old namespace | Check the corresponding API and migration guide |
| `@AutoConfigureRestDocs` fails to resolve | Missing Boot test auto-configuration dependency or wrong classpath | Check test starter and dependency versions |
| Test context fails to initialize | Beans, profiles, security, or framework APIs changed | Read the root cause in stack traces; verify test slice/full context |
| Documentation tests run but produce no snippets | Test does not call `document`, filter/config not attached, or test did not execute | Check test discovery, integration configuration, and output directory |
| JSON snippets change after upgrade | Jackson/modules/configuration or DTO serialization changed | Compare actual HTTP responses and `ObjectMapper` configuration |
| `requestFields`/`responseFields` fail | Payload changed or strict descriptors not updated | Inspect actual body, check field paths, and decide the contract |
| Asciidoctor cannot find snippets | Tasks ran out of order or paths differ | Check task dependencies, `snippets` attribute, and output path |
| CI passes while local fails, or vice versa | Different JDK, profile, environment variables, or cache | Standardize the toolchain and run a clean build in an equivalent environment |

## 11. Version Difference Verification Checklist

- [ ] Spring Boot plugin/BOM and Java toolchain are updated intentionally.
- [ ] Spring Framework and Spring Test versions resolve consistently.
- [ ] Spring REST Docs integration module matches the active `MockMvc`, `WebTestClient`, or REST Assured setup.
- [ ] JUnit engine, extensions/rules, and test discovery still work.
- [ ] Jakarta migration is completed for APIs that actually changed namespaces.
- [ ] Spring Security, validation, serializers, and exception handlers are tested in the right test context.
- [ ] Documentation tests run and regenerate snippets into a clean output directory.
- [ ] Strict descriptors reflect current requests/responses.
- [ ] Asciidoctor plugin/tasks/attributes are compatible with the build tool and JDK.
- [ ] CI uses the same Java/build configuration as the release environment.
- [ ] All observed changes in the HTTP contract are reviewed and documented.

## 12. Practice Exercise

An older Spring Boot project currently uses Java 11, Spring MVC, `MockMvc`, JUnit 5, and Spring REST Docs. The team wants to upgrade to Spring Boot 3, but after bumping the version, tests fail to compile on some Servlet/Validation imports and response snippets show differences.

Create a plan to:

1. Record the pre-upgrade versions of Boot, Java, Spring REST Docs, Spring Test, JUnit, and the Asciidoctor plugin.
2. Verify actual resolved dependency versions via Gradle `dependencyInsight` or Maven `dependency:tree`.
3. Identify imports belonging to APIs that moved to Jakarta; migrate only the affected packages.
4. Run documentation tests in the appropriate test context and verify `@AutoConfigureRestDocs`/`MockMvc` configuration.
5. Compare before/after JSON responses to separate formatting diffs from contract changes.
6. Run a clean build, generate snippets, render Asciidoctor, and inspect the HTML.
7. Write migration notes for changes that clients must be aware of.

**Self-check question:** When upgrading Spring Boot, should you set the version of `spring-restdocs-mockmvc` to match Spring Boot's version number? Do not rely on matching version numbers that way. The two projects have independent release cycles; inspect the BOM, dependency resolution, and library compatibility requirements instead.

## Conclusion

Checking differences across Spring Boot versions requires examining the entire dependency chain from Java and the Boot BOM down to Spring Framework, Spring Test, Spring REST Docs, JUnit, and Asciidoctor. When upgrading from Boot 2 to Boot 3, the Java baseline and Jakarta namespaces stand out as primary areas to audit; changes in test contexts, security, and serialization can also affect HTTP snippets. Verify resolved dependencies, run documentation tests at the right scope, regenerate snippets from a clean output, and re-render the documentation. Only after distinguishing technical diffs from HTTP contract changes can a team reliably publish documentation matching the new API version.
