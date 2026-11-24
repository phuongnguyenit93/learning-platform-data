# AOT, Reflection, and Metadata-Only Types

Springdoc-openapi builds documentation by reading controllers, DTOs, Spring configuration, and OpenAPI annotations. On a standard JVM, the library can use reflection to inspect classes, fields, methods, and annotations at runtime. When compiling a GraalVM Native Image, the program is analyzed ahead of runtime; dynamic accesses that the analyzer cannot infer require reachability metadata.

An easily overlooked case is a Java type referenced only in annotations such as `@Schema(implementation = ApiError.class)`, in `@ApiResponse`, in an indirectly referenced schema, or in client calls like `bodyToMono(ApiError.class)`. That type may not appear in any controller parameter or return type. Spring AOT usually infers reflection hints automatically from explicit request/response types on `@RestController`, but you should not assume every type mentioned in metadata is sufficiently registered for schema introspection and JSON binding.

This lesson explains how to distinguish class reachability from member reflection access, how to add hints for metadata-only DTOs, how to test hints, and how to verify OpenAPI endpoints on a native executable.

## Objectives

After this lesson, you will be able to:

- Explain why a native image needs reachability metadata for reflection and resources.
- Distinguish types appearing in controller signatures from types appearing only in OpenAPI annotations or generics.
- Recognize when Spring AOT can infer binding hints automatically.
- Use `@RegisterReflectionForBinding` for DTOs needing serialization/deserialization that AOT cannot infer.
- Use `RuntimeHintsRegistrar` and `@ImportRuntimeHints` when custom hints are required.
- Distinguish reflection hints for JSON binding from Java Object Serialization.
- Retain configuration classes that only hold `@OpenAPIDefinition` or `@SecurityScheme`.
- Test hints using `RuntimeHintsPredicates` and the tracing agent.
- Verify `/v3/api-docs`, Swagger UI, and JSON responses on a native executable.
- Design a CI pipeline to catch errors that only surface in a native image.

## 1. Why Does AOT Need Metadata?

On the HotSpot JVM, applications can load classes and use reflection to locate methods, fields, or constructors at runtime. GraalVM Native Image enforces a closed-world model: the builder analyzes paths reachable from entry points and includes only components determined to be necessary in the executable.

Code that directly invokes `new ProductResponse(...)` and accesses explicit methods is usually easy to analyze statically. However, if a library uses `Class.forName`, `Class.getDeclaredFields`, `Method.invoke`, Jackson introspection, or class names resolved from configuration, the builder may not know ahead of time which elements will be accessed.

Reachability metadata for Native Image declares which dynamic accesses must be preserved. Common categories include:

| Metadata Category | Used When |
|---|---|
| Reflection | Inspecting classes, constructors, methods, fields, or record components |
| Resources | Reading classpath files by name or pattern |
| Java serialization | Using `ObjectInputStream`/`ObjectOutputStream` |
| JDK proxies | Creating dynamic proxies from an interface list |
| JNI | Native code accessing Java classes/members |

Spring AOT generates source code, bytecode for certain proxies, and `RuntimeHints`. Native Image combines those hints with static analysis to build the executable.

### A Present Class Does Not Mean Reflection Members Are Ready

Distinguish two things:

1. The class is retained in the native image and can be referenced.
2. The class's constructors, fields, properties, methods, or record components are registered for the right dynamic access mode.

A class can still exist while calls to `getDeclaredFields()` or `Method.invoke()` fail if metadata omits the corresponding access permissions. Therefore, seeing a class in the binary or seeing an annotation containing `SomeDto.class` does not prove JSON binding will work.

## 2. Which Types Does Spring AOT Infer Automatically?

Spring Framework performs AOT processing on the `ApplicationContext` at build time. During this process, Spring analyzes bean definitions, controller mappings, and structures determinable from the classpath.

Cases where Spring automatically registers reflection hints include:

- Parameter types of `@RequestBody` methods.
- Return types of `@RestController` or `@Controller` methods when Spring recognizes they will be serialized, typically as JSON.
- `@ConfigurationProperties` types and properly declared nested types.
- Spring components and libraries that already supply their own runtime hints.

Example of types appearing directly in a controller signature:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    ProductResponse create(
            @RequestBody CreateProductRequest request) {
        // ...
    }
}
~~~

Spring can see `CreateProductRequest` as the request type and `ProductResponse` as the response type during AOT. The reflection hints needed for data binding are usually inferred automatically.

This does not mean every DTO in the application is registered automatically. Types selected by class name at runtime, types typed as `Object`, types constructed only via clients, or types mentioned only in annotations can fall outside what Spring infers from handler signatures.

## 3. Types Appearing Only in OpenAPI Metadata

Springdoc reads OpenAPI annotations to construct schemas. Example:

~~~java
@Operation(
    operationId = "createOrder",
    responses = {
        @ApiResponse(
            responseCode = "201",
            description = "Order created"
        ),
        @ApiResponse(
            responseCode = "422",
            description = "Invalid order data",
            content = @Content(
                schema = @Schema(implementation = ApiError.class)
            )
        )
    }
)
@PostMapping("/orders")
OrderResponse createOrder(
        @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

`ApiError` only appears inside the annotation; it is absent from the method's parameter and return types. Springdoc needs to inspect this class to build the error response schema. If the application also serializes `ApiError` at runtime via a handler returning `Object`, `ResponseEntity<?>`, or a generic type, AOT may not infer complete hints for JSON binding.

Places that commonly produce metadata-only types:

- `@Schema(implementation = SomeDto.class)`.
- `@ApiResponse` and `@Content(schema = ...)`.
- `@Parameter` or annotations declaring supplementary types.
- Schemas used via `@OpenAPIDefinition`, customizers, or Java configuration.
- Error response classes built in `@ControllerAdvice` where handlers declare overly generic return types.
- Types passed to `WebClient`/`RestClient` inside method bodies instead of appearing in bean signatures.
- Types loaded by class name or selected by configuration/plugins.

Not every type in OpenAPI metadata requires JSON binding hints. Determine whether the type only serves schema generation or is also serialized/deserialized at runtime:

| Role of Type | Primary Need |
|---|---|
| Only for Springdoc to read annotations/properties to build schemas | Reflection introspection for the exact members Springdoc reads |
| JSON body serialized/deserialized by Jackson | Reflection/binding hints for constructors, properties, fields, or record components |
| Instantiated or invoked via custom runtime reflection | Hints for the exact constructors/methods/fields accessed |
| OpenAPI configuration class | Must be a bean/configuration discovered by AOT |

A class literal in an annotation may create a reference to the class, but should not be treated as a substitute for binding hints. Inspect AOT output and test the native runtime to confirm.

## 4. Registering DTOs with @RegisterReflectionForBinding

When a DTO requires JSON serialization or deserialization but cannot be inferred by Spring from controller signatures, you can use `@RegisterReflectionForBinding`.

Example error DTO and nested type:

~~~java
import java.util.List;

public record ApiError(
    String code,
    String message,
    List<FieldViolation> violations
) {
}

public record FieldViolation(
    String field,
    String reason
) {
}
~~~

Registering the types needing binding on a Spring configuration:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
    ApiError.class
})
class ApiNativeBindingConfiguration {
}
~~~

The binding hint for `ApiError` also covers types referenced through properties and record components, such as `FieldViolation`. You can explicitly declare nested types as well to clarify scope or if that type is used independently elsewhere.

The annotation can be placed on a class-level bean or directly on a method, field, or constructor close to where the hint is needed. Placing it near the component using the type helps maintainers understand why the hint exists.

### When Should It Be Used?

Use `@RegisterReflectionForBinding` when:

- A DTO is passed to `WebClient`/`RestClient` and is absent from controller method signatures.
- A DTO is deserialized from an external response via generic types or `Object`.
- A DTO is serialized in an exception handler with a generic return type.
- A DTO is selected only via metadata yet is also used by Jackson to produce JSON.

If a class only serves Springdoc metadata reading and is never serialized/deserialized, do not blanket-register full binding for every model. Identify the exact members needing introspection; use narrow hints matching the operations Springdoc performs.

## 5. @OpenAPIDefinition Classes Must Be Retained by AOT

Springdoc specifically notes for native images: if `@OpenAPIDefinition` or `@SecurityScheme` is placed on a class with no implementation or bean configuration, that class may vanish during native compilation. Place the annotations on a `@Configuration` class:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0",
        description = "Order management API"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiConfiguration {
}
~~~

Do not create an annotation-only class and leave it outside component scanning. For native images, the configuration must participate in the `ApplicationContext` so Spring AOT can process it.

## 6. RuntimeHintsRegistrar for Custom Cases

When convenience annotations cannot express the access pattern, you can create a `RuntimeHintsRegistrar`. This is Spring's API for declaring reflection, resource, Java serialization, and JDK proxy hints.

Example registering a method invoked via reflection and a resource:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class ApiRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        Method method = ReflectionUtils.findMethod(
            ApiSchemaIntrospector.class,
            "describe",
            Class.class
        );

        if (method != null) {
            hints.reflection().registerMethod(
                method,
                ExecutableMode.INVOKE
            );
        }

        hints.resources().registerPattern(
            "openapi/examples/*.json"
        );
    }
}
~~~

Activate the registrar with `@ImportRuntimeHints`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ApiRuntimeHints.class)
class ApiNativeHintsConfiguration {
}
~~~

This example illustrates a custom introspection method and a sample resource. In a real application, replace class/method names and patterns with the resources actually used. Do not register resources or methods merely because they might be useful; only add verified accesses.

### Hints for Classes/Members Read via Reflection

If a library reads fields, constructors, or methods of a DTO in ways `@RegisterReflectionForBinding` does not cover, use `hints.reflection().registerType(...)` with appropriate `MemberCategory` values. Choose categories based on actual errors:

- Hints for class/member introspection when discovering members and metadata. In Spring Framework 7, introspection is included by default when registering a reflection hint for a type; the `INTROSPECT_*` categories are deprecated.
- `INVOKE_*` when invoking constructors or methods is required.
- `ACCESS_DECLARED_FIELDS`/`ACCESS_PUBLIC_FIELDS` when accessing field values on Spring Framework 7. The older `DECLARED_FIELDS`/`PUBLIC_FIELDS` names are deprecated.

`MemberCategory` names and capabilities depend on the Spring Framework version bundled with Spring Boot. Check your project BOM's API and test hints rather than copying categories from another version.

## 7. Distinguishing JSON Binding from Java Serialization

The term "serialization" can refer to two distinct mechanisms:

- JSON binding by Jackson or HTTP message converters: requires reflection hints for DTOs, properties, record components, and constructors. Use `@RegisterReflectionForBinding` when Spring cannot infer them.
- Java Object Serialization via `ObjectOutputStream`/`ObjectInputStream`: requires separate Java serialization metadata.

Do not register `registerJavaSerialization` simply because an endpoint returns JSON. Likewise, do not assume `@RegisterReflectionForBinding` automatically supports a `Serializable` class passed over an object stream.

## 8. Static Reachability Metadata JSON When Needed

Native Image can read `reachability-metadata.json` on the classpath under `META-INF/native-image/...`. Abbreviated example:

~~~json
{
  "reflection": [
    {
      "type": "com.example.api.ApiError",
      "allDeclaredFields": true,
      "allPublicMethods": true,
      "allPublicConstructors": true
    }
  ]
}
~~~

Example path:

~~~text
src/main/resources/
  META-INF/
    native-image/
      com.example/
        order-api-additional-hints/
          reachability-metadata.json
~~~

Spring Boot also generates metadata in its own directory keyed by `groupId` and `artifactId`. Place supplementary files in a non-overlapping directory to avoid overwriting AOT output.

JSON metadata is useful when shipping hints with a library or when static configuration is required. For hints belonging to a Spring application, prefer the `RuntimeHints` API to declare them near the consuming component. Avoid enabling all fields/methods when only a few members are needed, as doing so forces the native image to retain more elements than necessary.

## 9. Resources and Proxies Related to Swagger UI

Reflection is not the only hint category to check:

- OpenAPI YAML/JSON files loaded dynamically by name from the classpath require resource hints.
- Customized Swagger UIs with custom CSS, JavaScript, or template files must be packaged and recognized.
- JDK dynamic proxies used in integrations may require proxy hints.
- Third-party libraries need their own reachability metadata if they do not already provide hints.

Springdoc supports GraalVM native images, though you must still verify on your exact Spring Boot/Springdoc version. When using standard starters, many hints for the library itself are already supplied; avoid adding speculative duplicate registrations.

## 10. Testing Hints with RuntimeHintsPredicates

You can unit-test a registrar in isolation before building a native image:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class ApiRuntimeHintsTests {

    @Test
    void registersApiErrorReflectionHint() {
        RuntimeHints hints = new RuntimeHints();
        new ApiErrorRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onType(ApiError.class)
        ).accepts(hints);
    }
}

class ApiErrorRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        hints.reflection().registerType(
            ApiError.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
        );
    }
}
~~~

The example above only verifies that a reflection hint exists for the type. It does not prove every member Jackson needs is registered. For DTOs used in JSON binding, inspect the hints generated by `@RegisterReflectionForBinding` and follow up with native integration tests.

For configurations using `@RegisterReflectionForBinding`, inspect the hints produced during AOT or write AOT tests matching your Spring Boot version. `RuntimeHintsPredicates` can verify type, method, field, resource, and proxy hints; it does not prove OpenAPI endpoints actually work inside the native executable.

## 11. Using the Tracing Agent to Find Missing Hints

The GraalVM tracing agent observes reflection, resource, and proxy accesses while running on the JVM, then writes metadata to assist native builds.

Example running an AOT-processed application with the agent:

~~~bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/order-api.jar
~~~

Once the application starts:

1. Call `/v3/api-docs`.
2. Open Swagger UI if the application serves the UI.
3. Call operations with request DTOs and response DTOs.
4. Trigger error responses whose schemas are declared in annotations.
5. Exercise `WebClient`/`RestClient` flows deserializing types absent from controller signatures.
6. Stop the application so the agent flushes the metadata files.

The agent only records executed paths. If an error response or polymorphic branch is never triggered, metadata for that branch may not appear.

When running the agent across a test suite, output may include hints solely for test frameworks. Use access filters and review generated files before committing to source. Never dump the entire agent output into a project without triage.

## 12. Enabling Strict Reachability Checks

Modern GraalVM releases offer an exact reachability metadata mode to surface missing registrations earlier. You can enable `--exact-reachability-metadata` during native builds; some releases allow scoping by package.

When running the executable, the reporting mode can be set to:

~~~text
-XX:MissingRegistrationReportingMode=Warn
~~~

`Warn` logs missing registrations for investigation. In controlled test runs, you can use:

~~~text
-XX:MissingRegistrationReportingMode=Exit
~~~

`Exit` causes tests to fail even if code has a `catch (Throwable)` block that accidentally swallows missing-registration errors. These flags depend on the GraalVM version; check documentation for your exact distribution before adding them to builds.

## 13. Verifying OpenAPI and Runtime on the Native Executable

Passing JVM tests are not sufficient to conclude the native image has all required hints. Run smoke tests against the native executable or container:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Check at minimum:

| Flow | What to Verify |
|---|---|
| Fetch OpenAPI JSON/YAML | Springdoc generates the document without reflection errors |
| Swagger UI | HTML, JavaScript, CSS, and OpenAPI URL load cleanly |
| Controller request DTO | JSON deserializes accurately |
| Controller response DTO | JSON serializes accurately |
| Error response in annotation | Schema is present and runtime response has matching structure |
| DTO used only via WebClient/RestClient | Client deserializes the body |
| Records and nested DTOs | Constructors/properties/record components are accessed properly |
| Polymorphic DTOs | Subtypes are retained and deserialized by discriminator |
| Security metadata | Security schemes and requirements still appear in the document |

Cross-check both sides: the OpenAPI schema must describe the real body accurately, and the runtime body must serialize cleanly. A schema appearing in `/v3/api-docs` does not prove Jackson has sufficient hints to handle the corresponding type.

## 14. AOT Limitations to Keep in Mind

Spring AOT requires a bean model determinable at build time. Several dynamic runtime behaviors conflict with the closed-world assumption:

- The classpath and dependency set are fixed at build time.
- Bean definitions cannot change arbitrarily once the native image is built.
- Profiles and bean creation conditions like `@ConditionalOnProperty` are evaluated during the AOT build.
- Singletons registered directly via `registerSingleton` may not be processed by AOT like ordinary bean definitions.
- Classpath scanning cannot rely on dynamic classpath scanning in native runtime.

If API groups, controllers, or OpenAPI configuration depend on profiles, select the profile during the AOT build and test that exact configuration. Do not expect toggling a runtime property to create additional controllers or beans not packaged into the native image.

## 15. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `/v3/api-docs` throws reflection error in native image | DTO appearing only in OpenAPI annotation lacks appropriate hint | Identify missing class/member, add binding or reflection hint |
| Swagger UI loses API title or security scheme | Class carrying only `@OpenAPIDefinition`/`@SecurityScheme` stripped by AOT | Place annotations on a scanned `@Configuration` |
| Serializes on JVM but fails in native image | Jackson needs unregistered field/constructor/record hints | Use `@RegisterReflectionForBinding` for uninferred DTOs |
| Fails only on error responses | Error DTO appears in `@ApiResponse` but not in controller signature | Check actual handler type and register hint |
| HTTP client cannot deserialize DTO | Type only passed to `bodyToMono` or `body(...)` | Register binding hint for client DTO |
| Some properties disappear | Only class hint exists; required field/property access is missing | Check member-level hints and Jackson access strategy |
| Custom Swagger UI resource returns 404 | File omitted from native image | Register resource pattern and verify packaging |
| Native image lacks proxy | Dynamic JDK proxy created without proxy hint | Register required proxy interfaces |
| Tracing agent fails to catch the bug | Tests never hit the failing branch | Expand scenarios to cover every response/media type |
| Overly broad hints bloat binary | Registering all fields/methods across many DTOs | Narrow member categories and retain only needed types |

## 16. Integrating AOT/Native Image into CI

A practical pipeline should include these steps:

1. Pin Spring Boot, Spring Framework, Springdoc, and GraalVM versions via the BOM.
2. Run JVM tests and `/v3/api-docs` contract tests.
3. Run AOT processing with the intended production profile.
4. Check metadata-only DTOs and custom hints.
5. Run `RuntimeHintsPredicates` tests for application-owned hints.
6. Build the native executable or native container.
7. Launch the native executable in CI.
8. Fetch `/v3/api-docs` and `/v3/api-docs.yaml`.
9. Call operations with request/response DTOs and error responses.
10. Verify WebClient/RestClient flows, polymorphic DTOs, and custom resources.
11. Run exact reachability metadata or missing-registration reporting if supported by GraalVM.
12. Archive native build logs and smoke test results as release evidence.

With Maven, a Spring Boot project with the native profile configured can typically build an image via:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

With Gradle, a project configured for Buildpacks native images can use:

~~~bash
./gradlew bootBuildImage
~~~

These commands depend on the project's build, plugin, and Docker/Buildpacks configuration. If producing only an AOT-processed JAR, verify the JAR contains generated code and native-image hint files before proceeding to the image build step.

## 17. Comprehensive Practice Exercise

Build an order API with standard DTOs and an error DTO declared only in OpenAPI metadata:

~~~java
public record CreateOrderRequest(
    String productCode,
    int quantity
) {
}

public record OrderResponse(
    String orderId,
    String status
) {
}

public record ApiError(
    String code,
    String message,
    List<FieldViolation> violations
) {
}

public record FieldViolation(
    String field,
    String reason
) {
}
~~~

Tasks:

1. Create a controller accepting `CreateOrderRequest` and returning `OrderResponse`.
2. Use `@ApiResponse` with `@Schema(implementation = ApiError.class)` to document error responses.
3. Ensure the runtime error handler returns a body with matching structure.
4. Create a `@Configuration` for `@OpenAPIDefinition` and `@SecurityScheme`.
5. Register `ApiError` via `@RegisterReflectionForBinding` if it is not inferred from handler signatures.
6. Verify hints for record components and nested types.
7. If any DTO is used via `WebClient`, add a binding hint for that DTO.
8. Build the AOT/native image according to your project's Spring Boot version.
9. Fetch `/v3/api-docs` and verify the `ApiError` schema.
10. Send valid and invalid requests to verify JSON serialization/deserialization.
11. Run the tracing agent across response branches and review generated metadata.
12. Run native smoke tests in CI and archive logs.

### Completion Criteria

- [ ] Can distinguish AOT processing from Native Image compilation.
- [ ] Can explain why a reachable class does not imply member reflection is registered.
- [ ] Can identify DTOs present in controller signatures vs. DTOs appearing only in annotations.
- [ ] Knows when Spring infers binding hints automatically.
- [ ] Uses `@RegisterReflectionForBinding` for JSON-bound types not inferred by AOT.
- [ ] Uses `RuntimeHintsRegistrar` when custom hints are required.
- [ ] `@OpenAPIDefinition`/`@SecurityScheme` classes are configuration beans processed by AOT.
- [ ] Distinguishes JSON binding from Java Object Serialization.
- [ ] Has tests covering hints and native runtime.
- [ ] `/v3/api-docs` and Swagger UI work on the native executable.
- [ ] Error responses and nested DTOs serialize accurately.
- [ ] CI checks missing registrations and retains native smoke test evidence.

## Further Study

After this lesson, combine AOT/native image practices with contract testing, schema generation, serialization, and performance testing. Whenever adding a new type to OpenAPI annotations or customizers, determine whether it is used at runtime or only for documentation generation, then register the right hint type and verify on the native executable.

## References

- [Springdoc FAQ – GraalVM support](https://springdoc.org/#is-graalvm-supported)
- [Spring Boot – Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot – Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Framework – Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [GraalVM – Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM – Dynamic Features of Java](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/)
