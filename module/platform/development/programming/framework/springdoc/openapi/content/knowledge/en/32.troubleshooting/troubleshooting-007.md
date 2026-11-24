# Missing Parameter Names and `-parameters` Compiler Configuration

Springdoc-openapi reads Spring MVC/WebFlux mappings and controller method metadata to generate the OpenAPI Parameter Object. If Java parameter names are not retained in bytecode, documentation may lack names, use placeholder names, or mismatch the names clients expect. This problem commonly appears after upgrading the JDK, Spring Framework, or migrating to Spring Boot 3.

The foundational fix is compiling Java source with the `-parameters` option so `javac` records parameter names in the `MethodParameters` attribute of class files. In addition, names can be declared explicitly in Spring annotations such as `PathVariable`, `RequestParam`, or `RequestHeader`. For public APIs, explicit names keep contracts stable even when Java variable names are refactored.

## 1. Common Symptoms

A controller may be written as follows:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestParam String status,
        @RequestParam Integer page) {
    // ...
}
~~~

Developers expect the OpenAPI document to contain two query parameters named `status` and `page`. However, if parameter names are not stored in bytecode or the framework cannot discover them, the document may:

- Omit parameter names or fail to generate parameters properly.
- Display fallback names such as `arg0` or `arg1`.
- Produce unstable names across builds.
- Mismatch the query parameter names that Spring actually binds at runtime.
- Cause Spring to fail during request binding when an annotation relies on parameter name resolution but name metadata is missing.

Exact symptoms depend on the Spring version, annotation declarations, compiler, and springdoc version. Do not assume every project shows `arg0`; inspect your application's OpenAPI JSON and bytecode directly.

## 2. Why Can Parameter Names Disappear?

In Java source code, the compiler knows variable names such as `status` or `page`. However, `.class` files are not required by default to store method parameter names in a reflection-accessible way.

The `javac -parameters` option instructs the compiler to write parameter names into `MethodParameters` metadata. At runtime, Java Reflection can read names via `java.lang.reflect.Parameter.getName()` and check presence via `isNamePresent()`.

Without this metadata, `getName()` may return synthetic names like `arg0` and `isNamePresent()` returns `false`. Spring Framework and springdoc may be unable to infer the needed names from the method signature.

Spring Framework 6.1 removed the fallback mechanism for discovering parameter names from bytecode `LocalVariableTable`. Consequently, applications using Spring Framework 6.1 or newer must compile with `-parameters` if relying on the framework to infer method parameter names. Pay close attention to this when upgrading to Spring Boot versions managing Spring Framework 6.1.

## 3. Distinguishing Method Parameter Names from DTO Property Names

Not every name appearing in OpenAPI comes from `MethodParameters`.

| Name kind | Example | Primary metadata source |
|---|---|---|
| Path parameter | orderId in /orders/{orderId} | Mapping and PathVariable |
| Query parameter | page in ?page=2 | RequestParam or method parameter name |
| Header parameter | X-Tenant | RequestHeader |
| Cookie parameter | sessionId | CookieValue |
| Field in request body | customerCode in JSON | DTO, Jackson, record component, Schema |
| Field in response body | createdAt in JSON | DTO, Jackson, record component, Schema |

The `-parameters` option primarily affects method parameter names. It does not rename DTO properties and does not replace Jackson annotations such as `JsonProperty`.

For example:

~~~java
public record SearchRequest(
        String customerCode,
        Integer page
) {}

@PostMapping("/orders/search")
Mono<List<OrderResponse>> search(@RequestBody SearchRequest request) {
    // ...
}
~~~

The names `customerCode` and `page` in the request body schema are inferred from the DTO/record structure and serialization settings. If only DTO properties have wrong names, check Jackson, `JsonProperty`, getter/field access, and `Schema` instead of only enabling `-parameters`.

## 4. Checking Whether Annotations Rely on Name Inference

Spring annotations can accept an explicit name or let the framework infer it from the method parameter name.

Example relying on inference:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestParam String status,
        @RequestHeader String tenant) {
    // ...
}
~~~

Example with explicit declarations:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestParam(name = "status") String state,
        @RequestHeader(name = "X-Tenant") String tenant) {
    // ...
}
~~~

In the second example, the Java variable name `state` does not dictate the query parameter name. Spring uses the `name` declared in `RequestParam`, which is `status`. The header is published as `X-Tenant` even though the Java variable is `tenant`.

Annotations commonly offer a `name` or `value` attribute for explicit declaration:

| Annotation | Declaration example |
|---|---|
| PathVariable | PathVariable("orderId") |
| RequestParam | RequestParam(name = "page") |
| RequestHeader | RequestHeader(name = "X-Tenant") |
| CookieValue | CookieValue(name = "sessionId") |

Explicit names reduce reliance on compiler metadata and keep HTTP contracts stable when Java variable names are changed.

## 5. Enabling `-parameters` in Maven

With the Maven Compiler Plugin, configure `parameters` as `true`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

If the project already manages the compiler plugin in a parent POM or `pluginManagement`, place the configuration in the appropriate inherited location. Do not declare an arbitrary plugin version if the Spring Boot parent already manages a compatible version.

You can check the effective configuration with:

~~~bash
mvn help:effective-pom
~~~

Locate the `maven-compiler-plugin` section and verify `parameters` is enabled. Then run a clean compile so old class files are regenerated:

~~~bash
mvn clean test
~~~

Editing `pom.xml` without recompiling the module containing the controller can leave old class files missing `MethodParameters`.

## 6. Enabling `-parameters` in Gradle Kotlin DSL

With `build.gradle.kts`:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

This configuration applies to `JavaCompile` tasks in the current project, including `compileJava` and other Java source sets. If controllers live in a separate module, place the configuration in the module that actually compiles the controllers or in a shared configuration applied to those modules.

After making changes:

~~~bash
./gradlew clean test
~~~

## 7. Enabling `-parameters` in Gradle Groovy DSL

With `build.gradle`:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

If the project uses convention plugins, put the configuration into the convention plugin so every relevant Java module shares the same rule. Avoid configuring only the application module while controllers are compiled inside a separate library module.

After updating:

~~~bash
./gradlew clean test
~~~

## 8. Ensuring Configuration Applies to the Right Module

In multi-module projects, a module containing controllers may be built independently and packaged as a JAR. In that case, enabling `-parameters` only in the boot application module does not change the compiled bytecode of the controller module.

Check:

1. Identify which module or JAR the controller class is loaded from.
2. Enable `-parameters` in that module's compile configuration.
3. Clean and rebuild the module containing the controller.
4. If the module is published as an internal artifact, republish the artifact built with the new metadata.
5. Update the application's dependency to use the new artifact.
6. Inspect bytecode from the exact JAR used by the application.

Do not confuse class files in workspace `target/classes` with classes actually loaded from an old JAR on the runtime classpath.

## 9. Declaring Explicit Names for Path Parameters

For path parameters, OpenAPI requires the parameter name to match the placeholder in the path. Declare both the mapping and annotation clearly:

~~~java
@GetMapping("/orders/{orderId}")
OrderResponse getOrder(
        @PathVariable("orderId") UUID id) {
    // ...
}
~~~

The Java variable name is `id`, while the HTTP path parameter name is `orderId`. The annotation clarifies this boundary. The OpenAPI document should contain path `/orders/{orderId}` and parameter:

~~~yaml
name: orderId
in: path
required: true
schema:
  type: string
  format: uuid
~~~

If you only rename the Java variable while keeping the explicit annotation, the public URL stays unchanged. This keeps contracts stable during code refactoring.

## 10. Declaring Explicit Names for Query Parameters

Example pagination API:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int pageSize) {
    // ...
}
~~~

OpenAPI should document query parameters `page` and `size`. The variable name `pageSize` is not used as the HTTP parameter name because the annotation specifies `size`.

If omitting the `name` attribute:

~~~java
@RequestParam int page
~~~

Spring must discover the method parameter name to infer `page`. With bytecode lacking metadata, request binding may fail or documentation may lack the intended name.

## 11. Declaring Explicit Names for Headers and Cookies

Header:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @RequestHeader(name = "X-Tenant") String tenantId) {
    // ...
}
~~~

Cookie:

~~~java
@GetMapping("/profile")
ProfileResponse getProfile(
        @CookieValue(name = "sessionId") String session) {
    // ...
}
~~~

Variable names `tenantId` and `session` are internal Java details. The HTTP wire names remain `X-Tenant` and `sessionId`.

For standard or custom headers, keep the exact casing agreed upon in the API contract. Header names are case-insensitive in HTTP, yet documentation should use consistent casing.

## 12. Distinguishing `@Parameter` from Spring Annotations

Springdoc can use OpenAPI annotations like `Parameter` to add documentation descriptions:

~~~java
@GetMapping("/orders")
List<OrderResponse> findOrders(
        @Parameter(description = "Filter by order status")
        @RequestParam(name = "status") String state) {
    // ...
}
~~~

`RequestParam` controls how Spring binds the query parameter at runtime. `Parameter` adds OpenAPI metadata such as `description`, `example`, `schema`, or presentation options.

Do not use `Parameter` to replace `RequestParam`, `PathVariable`, or `RequestHeader`. Writing only `Parameter(name = "status")` without declaring the corresponding query parameter name in Spring mappings can leave documentation looking correct while runtime binding fails.

When using both annotations, keep names consistent. For example, `RequestParam(name = "status")` and `Parameter(name = "state")` risk documenting one name while the server expects another. If overriding a name in OpenAPI is necessary, verify that the change matches the actual HTTP protocol.

## 13. Inspecting Bytecode with `javap`

After a clean build, use `javap` to inspect the controller class:

~~~bash
javap -v -p target/classes/com/example/api/OrderController.class
~~~

Replace the class path with your actual package and controller name. Locate the `MethodParameters` section of the method under inspection.

When compiled with `-parameters`, the output typically contains a section similar to:

~~~text
MethodParameters:
  Name
  status
  page
~~~

If `MethodParameters` is missing or names are absent, check:

- Whether Maven/Gradle actually passes `-parameters` to `javac`.
- Whether the inspected class file is the output of the latest build.
- Whether the controller is compiled in another module.
- Whether runtime is loading an old JAR from a dependency cache or internal repository.

Do not conclude solely from `LocalVariableTable`. Local variable metadata and `MethodParameters` are two distinct bytecode attributes. Modern Spring Framework requires parameter names to be preserved via the standard reflection mechanism.

## 14. Inspecting with Java Reflection

You can write a small check to verify parameter names in compiled classes:

~~~java
import java.lang.reflect.Method;

class ParameterMetadataCheck {

    static void inspect() throws NoSuchMethodException {
        Method method = OrderController.class.getDeclaredMethod(
                "findOrders", String.class, Integer.class);

        for (java.lang.reflect.Parameter parameter : method.getParameters()) {
            System.out.println(
                    parameter.getName() + " / " + parameter.isNamePresent());
        }
    }
}
~~~

If metadata is preserved, `isNamePresent()` returns `true` and `getName()` returns source names like `status` or `page`. Otherwise, `getName()` may return `arg0`, `arg1` and `isNamePresent()` returns `false`.

Adjust the parameter type list in `getDeclaredMethod` to match your project's method signature. If the method is overloaded, pick the exact overload using parameter types.

You can add a JUnit assertion to prevent regressions:

~~~java
@Test
void controllerParameterNamesArePresent() throws Exception {
    Method method = OrderController.class.getDeclaredMethod(
            "findOrders", String.class, Integer.class);

    assertThat(method.getParameters())
            .allMatch(java.lang.reflect.Parameter::isNamePresent);
}
~~~

This test verifies class metadata in the test runtime. It does not replace testing the OpenAPI document or actual request binding.

## 15. Inspecting Parameter Names in OpenAPI JSON

After the application starts, download the OpenAPI document:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect the operation's parameters:

~~~bash
jq '.paths["/orders"].get.parameters' openapi.json
~~~

If the actual path has a prefix or different name, replace `/orders` with the path in the document. The output should reflect the proper public names, parameter locations, and schemas.

Example expected structure:

~~~json
[
  {
    "name": "status",
    "in": "query",
    "required": false,
    "schema": {
      "type": "string"
    }
  },
  {
    "name": "page",
    "in": "query",
    "required": false,
    "schema": {
      "type": "integer",
      "format": "int32"
    }
  }
]
~~~

If the document has no parameters, check method mappings, Spring annotations, operation filters, package scanning, and springdoc configuration. If parameters appear with wrong names, check `MethodParameters` and annotation `name`/`value` attributes.

## 16. Testing Runtime Requests as Well

The OpenAPI document is only a description. Send real requests to confirm Spring binds the expected names:

~~~bash
curl -i "http://localhost:8080/orders?status=PAID&page=2"
~~~

With path parameters:

~~~bash
curl -i "http://localhost:8080/orders/7f7d3c4a-1e5a-4d6e-9b4f-1e4d1f6a2b30"
~~~

With headers:

~~~bash
curl -i -H "X-Tenant: tenant-a" http://localhost:8080/orders
~~~

If OpenAPI states `status` while runtime only accepts `state`, or the document says `X-Tenant` while the controller binds `tenantId` by a different inferred name, contract and implementation are out of sync. Use explicit Spring annotations to lock down wire-format names.

## 17. Distinguishing Name Inference Errors from Filter or Customizer Bugs

Not every missing parameter is caused by missing `-parameters`.

| Sign | Area to inspect |
|---|---|
| Multiple method parameters become arg0/arg1 | Compiler metadata and -parameters |
| Only one parameter lacks a name | Spring annotation, method signature, or custom resolver |
| Parameter disappears completely | Mapping, hidden/filter, operation customizer, or package scan |
| DTO property has wrong name | Jackson, record component, getter/setter, or JsonProperty |
| Name in documentation is right but request binds wrongly | OpenAPI annotation and Spring annotation mismatch |
| Local works but CI fails | Different compiler plugin configuration, module build, or artifact cache |

If a parameter was removed by `OperationCustomizer` or `OpenApiCustomizer`, enabling `-parameters` will not restore it. Check customizers and filters that modify operations.

## 18. Checking When Using Spring Framework 6.1 or Newer

With Spring Framework 6.1, the fallback mechanism reading parameter names from `LocalVariableTable` was removed. Therefore, projects must preserve parameter names in bytecode using the `-parameters` compiler option if relying on name inference.

When upgrading Spring Boot, check the Spring Framework version managed by the Spring Boot BOM. Do not check only the springdoc version; changing Spring Boot can change how Spring discovers parameter names even when controller source code is unchanged.

If a project needs to run across multiple Spring Boot branches, enable `-parameters` in the build for consistent behavior. Simultaneously use explicit names in annotations for parameters belonging to important public contracts.

## 19. Refreshing Build Output and Dependency Caches

After enabling the compiler flag, clean build the module containing controllers:

~~~bash
mvn clean verify
~~~

Or:

~~~bash
./gradlew clean test
~~~

If the application uses internal JARs, rebuild and republish those modules, then update dependency versions in the application. When verification is needed, open the exact JAR used at runtime and inspect the classes inside.

Do not wipe the entire Maven or Gradle cache as a first step. First verify dependency resolution and output paths. Only purge caches selectively if evidence shows the build is consuming an old artifact.

## 20. Keeping Compiler Flags Consistent in CI

Bugs often appear when developer machines have custom compiler settings while CI pipelines do not use the same configuration. Store the `-parameters` flag in `pom.xml`, `build.gradle`, or convention plugins committed to the repository.

Check:

- Local builds and CI invoke the same Maven/Gradle wrapper.
- Modules containing controllers receive the compiler flag.
- CI performs a clean build when compiler options change.
- Artifacts are published from fresh builds rather than reusing old JARs.
- Tests checking `isNamePresent` or OpenAPI parameter names run in the pipeline.

Do not merely pass a compiler flag in a one-off local command and forget the official build configuration.

## 21. Common Errors and Fixes

| Symptom | Possible cause | How to fix |
|---|---|---|
| OpenAPI shows arg0 instead of expected name | Bytecode lacks MethodParameters | Enable -parameters and clean build controller module |
| Spring reports unable to infer argument name | Annotation lacks name/value and reflection has no name | Enable -parameters or declare explicit names |
| Local works but CI fails | Compiler configuration or artifacts differ | Inspect effective POM, Gradle tasks, and published JARs |
| Only controllers in one module fail | That module does not receive compiler flag | Configure JavaCompile/Maven compiler for that exact module |
| Parameter name in OpenAPI differs from query string | Parameter annotation and RequestParam mismatch | Align wire-format names in Spring and OpenAPI annotations |
| @Parameter has right name but request does not bind | Only OpenAPI metadata was declared | Specify the name in RequestParam/PathVariable/RequestHeader |
| DTO field has wrong name | Not a MethodParameters issue | Check Jackson, JsonProperty, record component, and Schema |
| Enabled -parameters yet documentation stays stale | Missing clean build or app loads old JAR | Identify runtime classes and rebuild/republish artifacts |
| Parameter does not appear | Operation filter, hidden annotation, or customizer removes it | Check mappings, group filters, and customizers |
| MethodParameters has names yet Spring still fails | Annotation or method overload mismatch | Check method signatures and names declared in annotations |

## 22. Ordered Diagnostic Procedure

1. Download OpenAPI JSON and identify the affected operation.
2. Inspect parameter `name`, `in`, and `schema` under `paths`.
3. Compare path/method against controller mappings.
4. Check whether Spring annotations specify explicit `name`/`value` or rely on inference.
5. Use `javap` to inspect `MethodParameters` in the controller class.
6. If metadata is missing, enable `-parameters` in the compiler for the module containing the controller.
7. Clean build and re-verify bytecode.
8. Start the new artifact and reload OpenAPI JSON.
9. Send runtime requests with the published parameter names.
10. If documentation is still wrong, check `OpenApiCustomizer`, `OperationCustomizer`, group filters, and package scanning.

Do not change annotations, compiler configuration, and customizers simultaneously in a single attempt when the root cause is unknown. Changing one factor at a time identifies exactly what fixed the issue.

## 23. Testing with Integration Tests

You can test the OpenAPI document using `WebTestClient` or `MockMvc` depending on your web stack. Example reading the JSON document and asserting query parameter names:

~~~java
@Test
void orderSearchDocumentsStableQueryNames() {
    webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(JsonNode.class)
            .value(document -> {
                JsonNode parameters = document.at(
                        "/paths/~1orders/get/parameters");

                assertThat(parameters.toString()).contains("\"status\"");
                assertThat(parameters.toString()).contains("\"page\"");
            });
}
~~~

This is an illustrative assertion for parameter names. In project tests, iterate over elements and assert `name`, `in`, `required`, and `schema` to avoid passing merely because a string appeared elsewhere in the JSON.

Combine with a runtime test:

~~~java
@Test
void orderSearchAcceptsDocumentedQueryNames() {
    webTestClient.get()
            .uri(uriBuilder -> uriBuilder
                    .path("/orders")
                    .queryParam("status", "PAID")
                    .queryParam("page", 2)
                    .build())
            .exchange()
            .expectStatus().isOk();
}
~~~

Adjust response assertions to match your actual API. The objective is locking both the published name and the name bound by Spring.

## 24. Checklist Before Closing the Issue

- [ ] Determined whether the parameter is a method parameter or a DTO property.
- [ ] Checked whether Spring annotations infer names or specify explicit `name`/`value`.
- [ ] Module containing the controller compiles with `-parameters`.
- [ ] Bytecode contains `MethodParameters` and `isNamePresent()` returns `true`.
- [ ] Clean build performed after changing compiler options.
- [ ] Runtime uses the new JAR/classes.
- [ ] OpenAPI JSON displays proper `name` and `in`.
- [ ] Runtime requests use the matching query/path/header/cookie names.
- [ ] `@Parameter` is not used in place of Spring binding annotations.
- [ ] Customizers/filters/groups do not unintentionally drop or rename parameters.
- [ ] CI applies the same compiler configuration as local builds.
- [ ] Tests protect parameter names of the public contract.

## 25. Design Principles

- Enable `-parameters` in the compiler for Java modules with controllers relying on method parameter names.
- Prefer explicit `name`/`value` declarations for path, query, header, and cookie parameters on public APIs.
- Distinguish OpenAPI metadata from `@Parameter` vs runtime binding from `RequestParam`, `PathVariable`, `RequestHeader`, and `CookieValue`.
- Do not confuse method parameter names with DTO property names.
- Use `javap` and Java Reflection to verify bytecode rather than guessing from source code.
- Clean build and verify the exact runtime artifact after changing compiler options.
- Verify both OpenAPI JSON and real requests.
- Check customizers and group filters if metadata exists yet the document still lacks parameters.
- Put compiler flags and regression tests into the official build so local and CI stay consistent.

## Conclusion

Missing parameter names usually stem from bytecode lacking `MethodParameters` metadata or Spring annotations leaving name inference to the framework. Enable the `-parameters` compiler option in Maven or Gradle to preserve method parameter names; for public APIs, explicitly declare `name`/`value` in `PathVariable`, `RequestParam`, `RequestHeader`, and `CookieValue`. Distinguish this from DTO property naming issues, which are governed by Jackson and schema metadata. Diagnose sequentially from OpenAPI JSON, Spring annotations, `javap` bytecode, Java Reflection, to runtime requests. Finally, keep compiler settings in the repository and add tests so parameter names do not disappear during CI builds.

## References

- [Java Compiler: javac options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java Reflection: Parameter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html)
- [Spring Framework 6.1 Reference](https://docs.spring.io/spring-framework/reference/overview.html)
- [springdoc-openapi documentation](https://springdoc.org/)
