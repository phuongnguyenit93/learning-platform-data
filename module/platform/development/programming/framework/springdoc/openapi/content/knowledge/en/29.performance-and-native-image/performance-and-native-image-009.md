# Runtime Hints for Custom Extensions When Necessary

springdoc-openapi can run in a Spring Boot application compiled into a GraalVM Native Image. However, when an application includes custom OpenAPI extensions—such as an OpenApiCustomizer, OperationCustomizer, or ModelConverter—some operations that occur only at runtime may not be fully inferred by Spring AOT.

Native Image must know ahead of time which elements will be accessed via reflection, which resources must be packaged, which types are used with Java serialization, and which JDK proxies must exist. This information is called runtime hints.

Not every application using springdoc needs to declare hints manually. Spring AOT already infers many common cases, including controller request/response types. Only add hints when an extension has behavior that AOT cannot infer and an error or check reveals missing metadata.

This lesson explains how to identify the need, use RuntimeHintsRegistrar and @ImportRuntimeHints, register reflection/resource/proxy hints, test hints, and verify OpenAPI endpoints in a native executable.

## 1. Why Does Native Image Need Runtime Hints?

An application running on a standard JVM can use reflection, read classpath resources, or create JDK proxies at runtime. The JVM has complete class metadata and the full classpath so those operations work.

Native Image is analyzed and compiled ahead of execution. The build process needs to know which elements must be retained and made accessible. A class or method looked up only by name at runtime may be stripped without a corresponding hint. Undeclared resources may not be packaged into the executable.

For example, an extension might call:

~~~java
Class.forName("com.example.openapi.CustomSchemaProvider");
~~~

Or read a file:

~~~java
new ClassPathResource("openapi/extensions/order-schema.yaml");
~~~

On the JVM, these operations can run normally. In a native executable, the class or resource may not exist in the way the extension expects if AOT cannot discover it.

Runtime hints supply additional information to the AOT/native-image build process. They do not alter business logic or create new classes/resources; they declare the dynamic accesses the application needs.

## 2. What Does Spring AOT Infer Automatically?

Spring AOT analyzes the ApplicationContext and bean definitions at build time. The framework can generate many hints based on how the application is declared.

Cases typically inferred automatically include:

- Request body and response body types declared in controller methods.
- DTOs discovered by Spring MVC/WebFlux from @RestController.
- Spring beans and annotations processed by the AOT processor.
- Certain proxies managed by Spring and generated at build time.
- Resources or reflection accesses for which libraries already provide hints.

Controller example:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
~~~

Spring AOT can recognize CreateOrderRequest and OrderResponse in the controller's contract and generate the necessary hints for binding/serialization.

Therefore, do not register reflection for every DTO simply because the application is compiled to a native image. Start by checking what AOT already recognizes and only add missing hints for extensions.

## 3. When Does a Custom Extension Need Hints?

A custom extension may need hints if it uses:

- Reflection to look up classes, fields, constructors, or methods by name.
- Resources selected by a name or pattern known only at runtime.
- Jackson or a binding mechanism to serialize/deserialize a type absent from controller signatures.
- JDK dynamic proxies created via Proxy or another library outside proxies managed by Spring AOT.
- Java Object Serialization via ObjectInputStream/ObjectOutputStream.
- Third-party libraries that do not yet provide required reachability metadata.

For example, a ModelConverter that scans fields via reflection may need reflection hints. An OpenApiCustomizer that loads schema fragments from the classpath by name may need resource hints. An extension calling WebClient to fetch metadata and deserialize the response into a DTO absent from controllers may need binding hints for that DTO.

A customizer that merely updates a title or adds an extension string to the OpenAPI model using standard APIs usually does not need separate runtime hints.

## 4. Distinguishing Reflection, JSON Binding, and Java Serialization

These three cases are easily confused:

| Case | Example | Typical Declaration |
|---|---|---|
| Reflection | Looking up a method or field by name | RuntimeHintsRegistrar or @RegisterReflection |
| JSON binding | Jackson serializing/deserializing a DTO | @RegisterReflectionForBinding when AOT cannot infer |
| Java serialization | ObjectOutputStream writing a Serializable object | Java serialization hint via RuntimeHints |

JSON binding is not Java serialization. Jackson typically uses reflection or bean/record metadata to read and write JSON. Do not register a Java serialization hint simply because an application returns JSON.

If a DTO appears in controller requests/responses, Spring usually infers the hint already. If a DTO is used only inside a WebClient or RestClient call within a service, AOT may not see that type through controller signatures; in that case, @RegisterReflectionForBinding is an appropriate choice.

## 5. RuntimeHints Categories

Spring provides RuntimeHints to aggregate runtime metadata requirements:

| Category | Purpose | Examples |
|---|---|---|
| Reflection hints | Permit accessing classes/members via reflection | Methods, constructors, fields |
| Resource hints | Package resources needed at runtime | YAML, JSON, templates, config files |
| Proxy hints | Register JDK dynamic proxies | Proxies for one or more interfaces |
| Serialization hints | Support Java serialization | Serializable types used with ObjectInputStream/ObjectOutputStream |

Hints are contributed during AOT processing and converted into metadata consumed by the native-image compiler.

Register the exact category matching the behavior. Adding a reflection hint will not make a missing resource appear in the image; a resource hint will not permit invoking a private method via reflection.

## 6. Registering a RuntimeHintsRegistrar

RuntimeHintsRegistrar is the extension point for registering hints using Java code.

A class implements this interface and writes its requirements to the RuntimeHints instance passed by Spring:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OpenApiExtensionHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
        RuntimeHints hints,
        ClassLoader classLoader
    ) {
        // Register only the runtime access required by the extension.
    }
}
~~~

Spring invokes registerHints during AOT processing. Therefore, this method should describe static metadata determinable at build time.

Do not use registerHints to call remote APIs, query a database, or depend on user requests. Runtime hints must be decided during the build, before the native executable runs.

## 7. Activating the Registrar with @ImportRuntimeHints

You can place @ImportRuntimeHints on a Spring bean or configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration
@ImportRuntimeHints(OpenApiExtensionHints.class)
class OpenApiNativeConfiguration {
}
~~~

Spring discovers the registrar and invokes it during AOT. Place the annotation near the component requiring the hints whenever possible, so metadata is only contributed when that component participates in the ApplicationContext.

For a custom OpenApiCustomizer, the annotation can be placed directly on the bean:

~~~java
@Component
@ImportRuntimeHints(OpenApiExtensionHints.class)
class SchemaCatalogCustomizer implements OpenApiCustomizer {
    // ...
}
~~~

This keeps the relationship between the customizer and its hints obvious to maintainers.

## 8. Example: Customizer Reading a Schema Fragment from the Classpath

Suppose an application has an extension loading schema guidance content from resources:

~~~text
src/main/resources/
  openapi/
    extensions/
      order-schema.yaml
      customer-schema.yaml
~~~

The customizer reads the resource during document generation:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import io.swagger.v3.oas.models.OpenAPI;

@Component
class SchemaCatalogCustomizer implements OpenApiCustomizer {

    @Override
    public void customise(OpenAPI openApi) {
        ClassPathResource resource =
            new ClassPathResource("openapi/extensions/order-schema.yaml");

        try (var input = resource.getInputStream()) {
            String text = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
            );
            openApi.addExtension("x-order-schema-notes", text);
        }
        catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot load order schema extension",
                ex
            );
        }
    }
}
~~~

On the JVM, the resource is normally found on the classpath. When running a native image, ensure the file is packaged into the executable.

Register the resource pattern:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class SchemaCatalogHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
        RuntimeHints hints,
        ClassLoader classLoader
    ) {
        hints.resources().registerPattern(
            "openapi/extensions/*.yaml"
        );
    }
}
~~~

Activate the hints:

~~~java
@Configuration
@ImportRuntimeHints(SchemaCatalogHints.class)
class SchemaCatalogNativeConfiguration {
}
~~~

The pattern must match the resource path relative to the classpath. Do not add a classpath: prefix to registerPattern's pattern. If the extension reads only one fixed file, register that exact file rather than a broad wildcard.

The example above adds the resource content to the x-order-schema-notes extension to illustrate resource reading. If YAML needs to become an actual Schema Object, parse the content using an appropriate parser and test that parser in the native image as well.

## 9. Registering Reflection for Dynamically Invoked Methods

Suppose a custom extension invokes a method via reflection:

~~~java
public class SchemaDescriptionProvider {

    public static String orderDescription() {
        return "Extended schema for orders";
    }
}
~~~

The extension looks up and invokes the method:

~~~java
import java.lang.reflect.Method;

import org.springframework.util.ReflectionUtils;

class SchemaDescriptionExtension {

    String description() {
        Method method = ReflectionUtils.findMethod(
            SchemaDescriptionProvider.class,
            "orderDescription"
        );

        if (method == null) {
            throw new IllegalStateException(
                "orderDescription method not found"
            );
        }

        return (String) ReflectionUtils.invokeMethod(method, null);
    }
}
~~~

Because the method is looked up and called via reflection, Native Image needs to know that this method must be retained and allowed for invocation.

You can register a method hint:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class SchemaDescriptionHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
        RuntimeHints hints,
        ClassLoader classLoader
    ) {
        Method method = ReflectionUtils.findMethod(
            SchemaDescriptionProvider.class,
            "orderDescription"
        );

        if (method == null) {
            throw new IllegalStateException(
                "Cannot find orderDescription"
            );
        }

        hints.reflection().registerMethod(
            method,
            ExecutableMode.INVOKE
        );
    }
}
~~~

Then import the registrar using @ImportRuntimeHints.

If the extension uses reflection to enumerate fields, constructors, or all methods instead of invoking one known method, register the corresponding member categories. Do not grant broader access than actually needed.

## 10. Registering Reflection for Data Types

When multiple members of a type must be registered, RuntimeHints allows declaring a type and member categories.

For example, an extension needs to invoke public constructors and public methods:

~~~java
hints.reflection().registerType(
    CustomSchemaPlugin.class,
    typeHint -> typeHint.withMembers(
        MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
        MemberCategory.INVOKE_PUBLIC_METHODS
    )
);
~~~

MemberCategory values specify which access kinds to retain. Depending on need, introspection, invocation, or field access may be required.

Do not select every category just to avoid errors. Overly broad hints enlarge the native image, diminish dead-code elimination benefits, and obscure the extension's actual dependencies.

If the type is known at build time, prefer a class literal over a String class name. If the class is chosen from configuration or plugin name, control the valid class set and register each class that may be used.

## 11. Using @RegisterReflectionForBinding for JSON DTOs

Spring Framework provides @RegisterReflectionForBinding to declare reflection metadata for types that are serialized/deserialized yet not inferred by AOT from controllers.

Example service calling WebClient:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
class SchemaRegistryClient {

    private final WebClient webClient;

    SchemaRegistryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(SchemaCatalogResponse.class)
    SchemaCatalogResponse loadCatalog() {
        return webClient.get()
            .uri("/internal/schema-catalog")
            .retrieve()
            .bodyToMono(SchemaCatalogResponse.class)
            .block();
    }
}
~~~

This example illustrates a response type deserialized inside a method body without appearing in a controller signature. The annotation registers metadata needed for constructors, fields, properties, and record components of that type; types referenced via properties are also handled per the annotation's rules.

If a service uses RestClient or Jackson directly, a similar approach applies. Identify the actual bound type and place the annotation on the appropriate bean or method.

## 12. DTOs Used by Controllers Usually Do Not Need Duplicate Registration

If a DTO appears in a controller method signature, Spring AOT can usually infer binding hints:

~~~java
@RestController
@RequestMapping("/api/schema")
class SchemaController {

    @PostMapping
    SchemaCatalogResponse create(
        @RequestBody SchemaCatalogRequest request
    ) {
        // ...
    }
}
~~~

There is no need to add @RegisterReflectionForBinding to every DTO in the project just because the application is built natively.

If a DTO both appears in a controller and is used in another reflective flow, verify whether the second flow needs additional hints. A hint inferred for Jackson binding does not automatically cover arbitrary custom reflection operations on the same class.

## 13. Resource Hints for Custom OpenAPI Files

Custom extensions may read:

- YAML/JSON schema fragments.
- API description templates.
- Operation name mapping files.
- Lists of tags or examples.
- Plugin-specific configuration files.
- Locale-selected resources.

Register an exact resource:

~~~java
hints.resources().registerPattern(
    "openapi/extensions/order-schema.yaml"
);
~~~

Or register a pattern for a group of files following a convention:

~~~java
hints.resources().registerPattern(
    "openapi/extensions/*.yaml"
);
~~~

If an extension reads files by locale:

~~~java
hints.resources().registerPattern(
    "openapi/messages/*.properties"
);
~~~

The pattern must cover resources actually used in the native executable. If a resource is generated after build time or read from an external filesystem, resource hints do not package it; instead configure paths and runtime file distribution.

## 14. JDK Proxy Hints

Some extensions use java.lang.reflect.Proxy or libraries creating JDK dynamic proxies from one or more interfaces.

Example:

~~~java
public interface SchemaProvider {
    String schemaName();
}
~~~

If a custom extension creates its own proxy:

~~~java
Object proxy = Proxy.newProxyInstance(
    SchemaProvider.class.getClassLoader(),
    new Class<?>[] { SchemaProvider.class },
    invocationHandler
);
~~~

Native Image needs to know that this proxy interface may be instantiated. Register it with:

~~~java
hints.proxies().registerJdkProxy(
    SchemaProvider.class
);
~~~

If a proxy implements multiple interfaces, register the exact interface set in the order and configuration used by the application.

Do not confuse JDK proxies with proxies generated by Spring AOP or Spring bean infrastructure. Spring AOT pre-generates many framework-managed proxies. Only add proxy hints when an extension creates its own dynamic proxies that AOT cannot detect.

## 15. Java Serialization Differs from Jackson JSON

RuntimeHints also supports Java serialization. This is the mechanism of ObjectInputStream and ObjectOutputStream, not the JSON format.

If an extension genuinely uses Java serialization:

~~~java
hints.reflection().registerJavaSerialization(
    LegacySchemaDescriptor.class
);
~~~

If an extension uses Jackson:

~~~java
objectMapper.readValue(
    json,
    SchemaCatalogResponse.class
);
~~~

it needs appropriate binding/reflection hints, typically @RegisterReflectionForBinding when AOT cannot infer the type.

Do not register Java serialization hints for every Jackson DTO. Doing so fails to resolve missing JSON binding metadata and makes native image configuration harder to understand.

## 16. Placing Hints Close to the Extensions That Need Them

A maintainable organization places the registrar alongside the customizer or converter:

~~~text
openapi/
  SchemaCatalogCustomizer.java
  SchemaCatalogHints.java
  SchemaDescriptionProvider.java
  SchemaCatalogResponse.java
~~~

The customizer describes OpenAPI. The registrar describes the dynamic accesses the customizer needs. DTOs are marked for binding only when Spring AOT does not recognize them automatically.

You can use a nested static class for the registrar:

~~~java
@Component
@ImportRuntimeHints(SchemaCatalogCustomizer.SchemaHints.class)
class SchemaCatalogCustomizer implements OpenApiCustomizer {

    public static class SchemaHints implements RuntimeHintsRegistrar {
        @Override
        public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader
        ) {
            hints.resources().registerPattern(
                "openapi/extensions/*.yaml"
            );
        }
    }
}
~~~

This keeps hints close to the component. If the customizer is no longer contributed to the ApplicationContext, hints attached to that bean are not contributed either.

## 17. Using META-INF/spring/aot.factories for Global Registration

Besides @ImportRuntimeHints, you can register a RuntimeHintsRegistrar globally via the META-INF/spring/aot.factories resource.

File contents:

~~~properties
org.springframework.aot.hint.RuntimeHintsRegistrar=\
com.example.openapi.OpenApiExtensionHints
~~~

This registration method suits libraries or modules wishing to contribute metadata without attaching annotations to a specific bean.

For ordinary applications, @ImportRuntimeHints is generally easier to read and trace. Avoid registering the same registrar through multiple mechanisms without reason, so you prevent duplicate configuration that is harder to audit.

## 18. Using Static GraalVM JSON Hint Files

When static metadata is needed, JSON files can be placed in the resource tree:

~~~text
src/main/resources/
  META-INF/
    native-image/
      com.example/
        orders-additional-hints/
          reflect-config.json
          resource-config.json
~~~

Spring Boot AOT also emits metadata under META-INF/native-image/{groupId}/{artifactId}. Therefore, place supplementary hints in a separate directory so they do not conflict with build-generated output paths.

Example resource-config.json:

~~~json
{
  "resources": {
    "includes": [
      {
        "pattern": "openapi/extensions/.*\\.yaml"
      }
    ]
  }
}
~~~

A reflect-config.json file can declare classes and methods requiring access in the GraalVM Native Image format matching your version.

Prefer RuntimeHintsRegistrar when you want metadata testable via Spring APIs and co-located with components. Use static JSON when sharing library-level metadata or when an external tool generated appropriate reachability configuration.

Never edit AOT-generated hint files directly inside target or build output. Those files are regenerated on every build.

## 19. Special Note for @OpenAPIDefinition and @SecurityScheme

The springdoc-openapi v2 FAQ notes regarding native images: if @OpenAPIDefinition or @SecurityScheme is placed on an annotation-only class not registered with Spring as configuration, that class may be stripped during native compilation.

Declare a configuration class:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0.0"
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

This tells Spring the class is a configuration bean included in the ApplicationContext. Do not use RuntimeHintsRegistrar to try to keep an improperly registered configuration class alive.

This note appears in springdoc's v2 FAQ. When using another major version, consult the FAQ and native image guide for that exact version.

## 20. Does a Custom ModelConverter Need Reflection Hints?

A ModelConverter can be used to customize how swagger-core derives a Schema Object from a Java type.

If the converter only calls public APIs on AnnotatedType, Schema, ModelResolver, and statically linked types, custom hints may not be needed.

If the converter:

- Scans private fields by name.
- Invokes getters via reflection.
- Loads classes from a plugin name.
- Creates proxies to read metadata.
- Loads resources containing type mappings.

then inspect each operation and add corresponding hints if AOT cannot infer them.

For example, a converter reading annotations on dynamically chosen fields may need introspection hints for fields or types. If a converter only uses reflection to invoke one specific method, register only the method needing invocation.

Do not register every member of an entire model package simply because a ModelConverter was added. Inspect the converter's exact code paths.

## 21. Customizers Adding Simple Metadata Usually Do Not Need Hints

Example customizer modifying only Info:

~~~java
@Component
class ApiInfoCustomizer implements OpenApiCustomizer {

    @Override
    public void customise(OpenAPI openApi) {
        openApi.getInfo()
            .description("API documentation generated from Spring Boot");
    }
}
~~~

This code calls ordinary Java APIs, loads no classes by name, reads no resources, and creates no dynamic proxies. Normally no separate RuntimeHintsRegistrar is needed.

Similarly, customizers adding tags, servers, or extension values using statically referenced model classes typically need no separate hints.

Focus on extensions performing dynamic access. Merely implementing OpenApiCustomizer does not mean the class needs reflection hints.

## 22. Springdoc Native Support and Third-Party Library Limits

springdoc-openapi v2 documents support for GraalVM Native Image in the Spring Boot 3 ecosystem. That does not mean every custom extension or third-party library pulled in by the application is automatically native-ready.

Spring Boot and Spring Framework provide many hints for the framework itself. springdoc can support native images for its standard paths. Yet external libraries using reflection or dynamic resource reads may still need their own reachability metadata.

When encountering an error in the native executable:

1. Determine whether the stack trace originates from Spring, springdoc, or a custom library.
2. Check whether that library already provides native hints or reachability metadata.
3. Check whether extension code performs dynamic reflection/resource/proxy accesses.
4. Use the tracing agent to collect missed accesses.
5. Add hints only for the parts the application is responsible for.

Do not use application RuntimeHints to paper over a library that does not support native image. If the bug lies in a library, check supported releases, the metadata repository, or upstream issues.

## 23. Testing RuntimeHintsRegistrar with RuntimeHintsPredicates

Spring provides RuntimeHintsPredicates to verify whether a registrar registers the expected metadata.

Example testing a resource pattern:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class SchemaCatalogHintsTests {

    @Test
    void registersSchemaResources() {
        RuntimeHints hints = new RuntimeHints();

        new SchemaCatalogCustomizer.SchemaHints()
            .registerHints(hints, getClass().getClassLoader());

        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("openapi/extensions/order-schema.yaml")
        ).accepts(hints);
    }
}
~~~

This test confirms the registrar contributes the required resource hint. It does not replace running the native executable because the file path could still be wrong or the extension could use additional reflection on another code path.

Matching predicates can be written for reflection, serialization, or proxy hints. Choose the predicate matching the access type your extension performs.

## 24. Testing Reflection Hints

If a registrar registers a specific method, write a test confirming that method can be invoked under the contributed metadata.

Across Spring Framework versions, predicate APIs can have different overloads for types, constructors, or methods. Use the exact API of the Spring Framework version managed by your Spring Boot BOM.

A reliable testing strategy:

1. Create an empty RuntimeHints instance.
2. Invoke the registrar with a test classloader.
3. Use RuntimeHintsPredicates to assert on the specific method/type.
4. Run the extension on the JVM with the tracing agent to record accesses.
5. Compare recorded accesses with registered hints.

Do not check only that the class exists. Native Image may retain the class while lacking permission to invoke the method or access the field the extension needs.

## 25. Using the GraalVM Tracing Agent to Discover Missing Hints

When you do not yet know which dynamic accesses an extension performs, the GraalVM tracing agent can observe the application running on the JVM and record reflection, resource, or proxy accesses.

Example running an executable JAR that already contains AOT assets:

~~~bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/orders-service.jar
~~~

After the application starts:

1. Call the OpenAPI endpoints.
2. Open Swagger UI if the application serves it.
3. Call endpoints with custom request/response schemas.
4. Trigger customizers and ModelConverters.
5. Fetch OpenAPI groups.
6. Exercise every extension branch using resources or reflection.
7. Stop the application so the agent writes metadata to the output directory.

The agent only records executed code paths. If an endpoint is never called or an extension is never triggered, the corresponding metadata may not appear.

Output from a test suite may contain accesses from the test framework itself. Review and apply an access filter if needed before committing generated files into the source tree.

## 26. Testing AOT on the JVM Before Building Native

You can run the application with AOT-generated assets on the JVM:

~~~bash
java -Dspring.aot.enabled=true \
  -jar target/orders-service.jar
~~~

The JAR must first be built with AOT processing. This mode catches certain errors caused by AOT-generated contexts or build-time conditions, though it still runs on the JVM and does not replace native executable testing.

Verify:

- Does the ApplicationContext start?
- Are customizer beans registered?
- Does the OpenAPI endpoint return the document?
- Are custom resources read?
- Do groups and security schemes appear?

After this step, proceed to build native and test the real executable.

## 27. Building Native Image with Maven

For a Maven project using spring-boot-starter-parent with Native Build Tools configured, the native profile can trigger AOT and native compilation.

Example:

~~~bash
./mvnw -Pnative native:compile
~~~

Or build a native container image with Buildpacks:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Executable names and plugin configurations depend on the project. The Spring Boot parent's native profile provides convenient defaults; if not using the parent, configure process-aot and Native Build Tools manually per Spring Boot documentation.

Native compilation requires a compatible GraalVM toolchain, the Native Image compiler, and a matching build environment. Use the same target OS/architecture where the application will deploy unless your pipeline supports cross-compilation.

## 28. Building Native Image with Gradle

With Gradle, add the GraalVM Native Build Tools plugin:

~~~kotlin
plugins {
    id("org.springframework.boot")
    id("org.graalvm.buildtools.native")
}
~~~

Then run:

~~~bash
./gradlew nativeCompile
~~~

Or build an image with Buildpacks:

~~~bash
./gradlew bootBuildImage
~~~

The Spring Boot Gradle plugin integrates AOT tasks when the native plugin is applied. Verify Gradle plugin and Native Build Tools versions match your Spring Boot version.

## 29. Testing the Native Executable Against OpenAPI Endpoints

After building, run the native executable and test the endpoints:

~~~bash
./target/orders-service
~~~

Verify OpenAPI JSON:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

If grouped documents exist:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/public -o openapi-public.json
curl -fsS http://localhost:8080/v3/api-docs/admin -o openapi-admin.json
~~~

Inspect extensions:

~~~bash
jq '.["x-order-schema-notes"]' openapi.json
~~~

Beyond documentation endpoints, invoke the real APIs to verify request/response DTOs, validation, serialization, and custom extensions exercised during request processing.

If testing only startup without calling /v3/api-docs, customizers may not have executed yet. Some resource/reflection errors only surface when the document is generated for the first time.

## 30. Testing Swagger UI in Native Image

If deploying Swagger UI with the application, verify both static resources and the OpenAPI document:

1. Open /swagger-ui/index.html or the configured path.
2. Verify the HTML page and JavaScript load successfully.
3. Verify Swagger UI fetches /v3/api-docs properly.
4. Verify custom schemas and security schemes appear.
5. Try an operation with a request body and response DTO.
6. Check the browser console and network responses.

Springdoc provides native support for standard paths, though custom transformers, bespoke resources, or static assets added by the application may need resource hints if loaded dynamically.

Do not add resource hints for the entire Swagger UI WebJar if the library already packages and supplies appropriate metadata. Only investigate custom assets managed by the application or reproducible failures.

## 31. Checking Groups and Customizers in AOT

If the application uses multiple GroupedOpenApi beans, test every group:

~~~text
/v3/api-docs
/v3/api-docs/public
/v3/api-docs/partner
/v3/api-docs/admin
~~~

Each group can use distinct customizers. An extension invoked only in the partner group might not be triggered when fetching only the default document.

When running the tracing agent or native smoke tests, invoke every group endpoint and verify:

- Is the group registered in the AOT ApplicationContext?
- Does the OpenAPI document contain the expected paths and schemas?
- Are customizers invoked?
- Are group-specific resources loaded?
- Are security schemes and extensions added?

If a group bean is created conditionally via @Profile or @Conditional, the condition may be evaluated at build time during AOT. Select the right profile/environment when running process-aot; do not expect a bean to appear at runtime if it was omitted from the AOT context.

## 32. AOT Requires Stable Bean Configuration at Build Time

AOT analyzes the ApplicationContext at build time. Certain conditions must be settled at that stage:

- The classpath is fixed.
- Bean definitions cannot change arbitrarily after the build.
- @Profile and @Conditional are evaluated against the AOT environment.
- Beans registered via singleton instances or dynamic suppliers may not be transformed like normal bean definitions.
- Bean types must be declared specifically enough for AOT to generate proxies/hints.

If a custom extension registers a ModelConverter or OpenApiCustomizer by adding a bean manually after the context starts, AOT may not see that bean.

Prefer registering extensions with @Bean, @Component, or AOT-supported Spring mechanisms. If dynamic bean definition registration is required, use AOT-aware mechanisms like ImportBeanDefinitionRegistrar where appropriate.

## 33. Common Pitfalls Running Native Image

| Symptom | Cause to Investigate |
|---|---|
| OpenAPI endpoint works on JVM but fails in native | Missing reflection/resource hint or library is not native-ready |
| Custom schema provider not found | Class loaded by name was not retained |
| Method invocation fails | Missing method invocation hint |
| YAML extension cannot be read | Resource not packaged or pattern is wrong |
| DTO from WebClient fails to deserialize | Binding type not inferred by AOT |
| JDK proxy cannot be created | Proxy interface not registered |
| @OpenAPIDefinition disappears | Annotation class not registered as @Configuration per springdoc v2 note |
| Only default group works | Corresponding customizer/group not activated or tested |
| Hints exist in source yet native still fails | Registrar not imported or access does not match hint |
| JVM AOT runs but native fails | Missing metadata required only by the native-image compiler |
| Unusually large image | Hints too broad or retaining unnecessary members/resources |
| Tracing agent fails to emit needed hint | Extension code path was not exercised during the agent run |

Read the first error and stack trace to identify the access type. Do not scatter reflection, resource, and proxy hints simultaneously by guesswork.

## 34. Workflow for Investigating Missing-Hint Errors

When the native executable hits an error in a custom extension:

1. Identify the failing class and method.
2. Determine whether the extension is doing reflection, binding, resource loading, or proxy creation.
3. Check whether AOT can infer that access from bean/controller signatures.
4. Use the tracing agent to record the code path.
5. Write the appropriate RuntimeHintsRegistrar or annotation.
6. Write a test with RuntimeHintsPredicates.
7. Rebuild AOT and the native image.
8. Re-run the exact failing endpoint/group/operation.
9. Verify the OpenAPI output matches the JVM output.
10. Review whether the hint is overly broad.

If the error originates in a third-party library, check the library's reachability metadata before maintaining a custom hint copy in the application.

## 35. Runtime Hints Checklist for Custom Extensions

- [ ] Confirmed the application genuinely runs native image/AOT.
- [ ] Checked springdoc and Spring Boot versions support native image.
- [ ] Identified which extensions use dynamic reflection or resources.
- [ ] Avoided blanket-adding hints for DTOs already inferred by AOT.
- [ ] Distinguished JSON binding from Java serialization.
- [ ] Non-controller DTOs use @RegisterReflectionForBinding when needed.
- [ ] Reflection hints grant access only to members actually invoked.
- [ ] Resource patterns match exact classpath paths.
- [ ] JDK proxy hints added only when extensions create their own proxies.
- [ ] RuntimeHintsRegistrar activated via @ImportRuntimeHints or appropriate registration.
- [ ] Hints placed close to custom extensions.
- [ ] @OpenAPIDefinition and @SecurityScheme reside on proper configuration beans.
- [ ] Wrote RuntimeHintsPredicates tests.
- [ ] Ran AOT on the JVM.
- [ ] Built and ran the native executable.
- [ ] Tested /v3/api-docs and all groups.
- [ ] Tested actual customizers, converters, resources, and DTOs in use.
- [ ] Did not edit build-generated hint files.
- [ ] Did not use broad hints merely to mask third-party library bugs.

## 36. References

- [Spring Boot – Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot – Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot – Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Boot – Testing Native Applications](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Framework – Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework API – RuntimeHintsRegistrar](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/RuntimeHintsRegistrar.html)
- [Spring Framework API – RegisterReflectionForBinding](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html)
- [springdoc-openapi v2 FAQ – GraalVM support](https://springdoc.org/v2/faq.html#is-graalvm-supported-)
- [GraalVM Native Image – Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)

Runtime hints supply metadata for dynamic accesses that Spring AOT cannot infer. With springdoc, most standard controller, DTO, and document flows are already supported; custom extensions only need hints when they perform reflection, resource loading, binding, or JDK proxying beyond what AOT detects. Identify the exact access, register minimal hints, verify with RuntimeHintsPredicates, and run the native executable against real OpenAPI endpoints/groups before releasing.
