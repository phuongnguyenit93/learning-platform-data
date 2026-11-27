# RuntimeHintsPredicates for Verifying Registered Access Types

When a Spring library needs reflection, resource loading, Java serialization, or JDK proxy creation in a Native Image, it must declare those requirements using **runtime hints**. Writing a `RuntimeHintsRegistrar` is only half the work: tests are needed to verify that the registrar actually declares the exact access types that the code will use.

Spring Framework provides **`RuntimeHintsPredicates`** to inspect `RuntimeHints` using meaningful conditions. Tests can verify that a constructor is allowed to be invoked via reflection, a method has an invocation hint, a resource is included in the image, a type is registered for Java serialization, or a set of interfaces has a JDK proxy hint. These tests run quickly on the JVM without compiling a native executable.

This lesson covers how to write a registrar, test each hint category, test whether Spring discovers the registrar during AOT, and extend testing with the RuntimeHints Agent. Finally, the lesson distinguishes evidence from predicates from the evidence required when running a real native image.

## 1. Why test runtime hints?

A wrong or missing hint may only surface when the native executable runs a rarely used business branch. For example:

- A constructor is declared for introspection, but the code actually needs to invoke the constructor.
- A method has the right name but the wrong parameter signature.
- A resource is registered with a pattern that does not match the actual path.
- A JDK proxy has the right interfaces, but their order differs from the order used when creating the proxy.
- A DTO is registered for reflection binding, but the code uses Java serialization instead.
- A registrar has its own unit tests, but is not imported or not discovered during Spring AOT.

Merely verifying that `registerHints()` was called does not prove that the required access has been declared. `RuntimeHintsPredicates` turns those requirements into concrete assertions.

~~~mermaid
flowchart TD
    A["RuntimeHintsRegistrar"] --> B["Build RuntimeHints"]
    B --> C["RuntimeHintsPredicates"]
    C --> D{"All predicates pass?"}
    D -->|No| E["Fix registrar or test"]
    E --> A
    D -->|Yes| F["Verify Spring AOT discovers registrar"]
    F --> G["Run native build and runtime test"]
    G --> H{"Real code paths work?"}
    H -->|No| I["Investigate metadata, resources, or code path"]
    I --> A
    H -->|Yes| J["Evidence established for tested flows"]
~~~

**Passing predicates confirm the hint structure in the `RuntimeHints` object under test.** They do not compile a native image, do not exercise every runtime branch, and do not verify that a resource file actually exists in the artifact unless the test checks that separately.

## 2. Where do RuntimeHints and RuntimeHintsPredicates live?

`RuntimeHints` belongs to Spring Framework, in the `org.springframework.aot.hint` package. It collects the dynamic access requirements needed by an application:

| Category | Registration API | Meaning |
|---|---|---|
| Reflection | `hints.reflection()` | Classes, constructors, methods, and fields accessed via reflection |
| Resource | `hints.resources()` | Classpath files and resource bundles needed at runtime |
| Java serialization | `hints.serialization()` | Types serialized via Java Object Serialization |
| JDK proxy | `hints.proxies()` | Interface sets used with `java.lang.reflect.Proxy` |
| JNI | `hints.jni()` | Reflection access needed for JNI |

`RuntimeHintsPredicates` is in the `org.springframework.aot.hint.predicate` package. This API provides four predicate groups:

~~~java
RuntimeHintsPredicates.reflection()
RuntimeHintsPredicates.resource()
RuntimeHintsPredicates.serialization()
RuntimeHintsPredicates.proxies()
~~~

These predicates inspect reflection, resource, Java serialization, and JDK proxy hints respectively. The `RuntimeHintsPredicates` API has been available since Spring Framework 6.0, so it can be used in Spring Boot 3.x+ applications using Spring Framework 6.x. Let Spring Boot dependency management manage the Spring Framework version and avoid mixing modules from different minor versions.

Note: `RuntimeHints` has a `jni()` API, but `RuntimeHintsPredicates` does not provide a dedicated JNI factory in this standard predicate set. For JNI, verify the appropriate configuration and run native tests for the actual call path.

## 3. Separating the registrar from tests

You should write the registrar as a class that can be instantiated directly in unit tests. For example, an application with an invoice SDK needs to:

- Invoke the `InvoicePayload(String)` constructor via reflection.
- Invoke the `normalize()` method via reflection.
- Read the `invoice/templates/invoice-v1.json` resource.
- Create a JDK proxy for `InvoiceGateway` and `Serializable`.
- Use Java serialization for `AuditEvent`.

Example data types:

~~~java
import java.io.Serializable;
import java.util.Locale;

public final class InvoicePayload {

    private final String invoiceId;

    public InvoicePayload(String invoiceId) {
        this.invoiceId = invoiceId;
    }

    public String normalize() {
        return this.invoiceId.trim().toUpperCase(Locale.ROOT);
    }

    public String debugDump() {
        return this.invoiceId;
    }
}

public interface InvoiceGateway {
    String submit(String invoiceId);
}

public final class AuditEvent implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String invoiceId;

    public AuditEvent(String invoiceId) {
        this.invoiceId = invoiceId;
    }
}
~~~

The resource is located at:

~~~text
src/main/resources/
└── invoice/
    └── templates/
        └── invoice-v1.json
~~~

Paths in `registerPattern` and `forResource` are relative to the classpath root and use `/`. Do not include the `src/main/resources` prefix in the resource name.

## 4. Registering the required hint types

Example registrar:

~~~java
import java.io.Serializable;
import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class InvoiceRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(InvoicePayload.class, typeHint -> {
            typeHint.withMembers(MemberCategory.INVOKE_DECLARED_CONSTRUCTORS);
            typeHint.withMethod(
                "normalize",
                List.of(),
                ExecutableMode.INVOKE
            );
        });

        hints.resources().registerPattern(
            "invoice/templates/invoice-v1.json"
        );

        hints.proxies().registerJdkProxy(
            InvoiceGateway.class,
            Serializable.class
        );

        hints.serialization().registerType(AuditEvent.class);
    }
}
~~~

Each API describes one specific requirement:

- `ExecutableMode.INVOKE` requests the ability to invoke a constructor or method via reflection.
- `registerPattern` declares a classpath resource that must be included in the image.
- `registerJdkProxy` declares a JDK proxy implementing the exact interface set.
- `serialization().registerType` is for Java Object Serialization.

Do not broadly register all methods, fields, or constructors just to make tests pass. Declare only the exact access types that the code actually performs.

## 5. Creating RuntimeHints in unit tests

Unit tests can invoke the registrar directly to obtain a `RuntimeHints` instance:

~~~java
RuntimeHints hints = new RuntimeHints();

new InvoiceRuntimeHints().registerHints(
    hints,
    getClass().getClassLoader()
);
~~~

Then use predicates to verify it. A common assertion pattern with AssertJ is:

~~~java
assertThat(predicate).accepts(hints);
~~~

Here, `predicate` is a `Predicate<RuntimeHints>` created by Spring. `accepts` fails the test if the `hints` object does not satisfy the condition.

This approach separates two concerns: what metadata the registrar produces, and what access types the test requires. When a test fails, the assertion tells you which hint kind is missing instead of waiting for the native executable to throw an error at runtime.

## 6. Testing constructor and method reflection

`RuntimeHintsPredicates.reflection()` creates predicates for reflection. You can check types, constructors, methods, or fields.

Example checking constructor and method invocation permissions:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

@Test
void registersReflectionInvocationHints() throws Exception {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    Constructor<?> constructor =
        InvoicePayload.class.getDeclaredConstructor(String.class);

    Method normalize =
        InvoicePayload.class.getDeclaredMethod("normalize");

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onConstructor(constructor)
            .invoke()
    ).accepts(hints);

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onMethod(normalize)
            .invoke()
    ).accepts(hints);
}
~~~

Using the resolved `Constructor` or `Method` helps the test pinpoint the exact signature. For overloaded methods, avoid passing only the class and method name if multiple methods share that name; the simple name-based API can throw an error when a unique method cannot be identified.

You can check that a type is registered with a specific member category:

~~~java
assertThat(
    RuntimeHintsPredicates.reflection()
        .onType(InvoicePayload.class)
        .withMemberCategory(MemberCategory.INVOKE_DECLARED_CONSTRUCTORS)
).accepts(hints);
~~~

In the registrar from section 4, the type hint registered `INVOKE_DECLARED_CONSTRUCTORS`, so this assertion matches. `withMemberCategories(...)` can be used when verifying that multiple categories are present simultaneously; `withAnyMemberCategory(...)` only requires at least one category from the list.

## 7. Distinguishing introspection from invocation

Reflection has two distinct needs:

- **Introspection:** finding or reading metadata about a member.
- **Invocation:** calling a constructor or method.

`ReflectionHintsPredicates` lets you explicitly choose the verification mode using `introspect()` and `invoke()`.

For example, a method that only needs to be discovered:

~~~java
import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;

hints.reflection().registerType(
    InvoicePayload.class,
    typeHint -> typeHint.withMethod(
        "normalize",
        List.of(),
        ExecutableMode.INTROSPECT
    )
);
~~~

Corresponding assertion:

~~~java
Method method = InvoicePayload.class.getDeclaredMethod("normalize");

assertThat(
    RuntimeHintsPredicates.reflection()
        .onMethod(method)
        .introspect()
).accepts(hints);
~~~

If the code calls `Method.invoke()`, require `invoke()`. A test that only checks introspection can pass even though the hint does not grant the invocation mode the application needs.

When a constructor or method is registered with both modes, the predicate for each mode confirms that respective mode. Test the mode that closely matches the runtime operation to avoid overly lenient tests.

## 8. Testing classpath resources

Resource hints often fail because the source tree path is confused with the classpath path. If the file is at `src/main/resources/invoice/templates/invoice-v1.json`, the runtime path is `invoice/templates/invoice-v1.json`.

Assertion:

~~~java
@Test
void registersInvoiceTemplate() {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    assertThat(
        RuntimeHintsPredicates.resource()
            .forResource("invoice/templates/invoice-v1.json")
    ).accepts(hints);
}
~~~

`forResource` also accepts paths starting with `/`; the leading slash is stripped during checking. If the resource resides in the same package as a type, there is an overload taking a type reference and a relative name:

~~~java
import org.springframework.aot.hint.TypeReference;

RuntimeHintsPredicates.resource()
    .forResource(TypeReference.of(InvoicePayload.class), "invoice-v1.json");
~~~

The predicate checks that a hint can cover the resource name. It does not confirm that the file was packaged into the JAR or that the file actually exists. You can also check for the resource on the test classpath:

~~~java
assertThat(
    getClass().getClassLoader()
        .getResource("invoice/templates/invoice-v1.json")
).isNotNull();
~~~

The two assertions verify two different things: that the metadata is declared and that the file is present on the test classpath. Both are needed if your goal is to ensure the resource is packaged and permitted into the native image.

## 9. Testing Java serialization

For Java Object Serialization, use `RuntimeHintsPredicates.serialization().onType(...)`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void registersJavaSerializationType() {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    assertThat(
        RuntimeHintsPredicates.serialization()
            .onType(AuditEvent.class)
    ).accepts(hints);
}
~~~

The registered type must implement `Serializable` when using the `Class` overload. This predicate verifies the Java serialization hint.

**Do not confuse Java serialization with JSON data binding.** `RuntimeHintsPredicates.serialization()` does not check Jackson, JSON-B, or DTO reflection binding. For DTOs used with Jackson, you typically need to check reflection hints for constructors, properties, fields, or record components depending on how the serializer actually accesses them. You can use `@RegisterReflectionForBinding` where Spring supports it or register reflection hints explicitly.

## 10. Testing JDK dynamic proxies

The proxy predicate verifies that the exact set of interfaces is registered:

~~~java
@Test
void registersJdkProxyInterfaces() {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    assertThat(
        RuntimeHintsPredicates.proxies()
            .forInterfaces(
                InvoiceGateway.class,
                Serializable.class
            )
    ).accepts(hints);
}
~~~

**Interface order matters.** If the application creates a proxy via `Proxy.newProxyInstance` with the interface list ordered as `InvoiceGateway`, `Serializable`, the test must check that exact same order. Swapping the order in the predicate can cause the test to fail even though the interface names are the same.

This predicate checks JDK interface proxies. It does not prove that a CGLIB subclass or a dynamically generated Byte Buddy class has been generated.

## 11. Writing a complete test class for the registrar

You can group the checks above into a single test class:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.io.Serializable;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class InvoiceRuntimeHintsTests {

    private RuntimeHints hints;

    @BeforeEach
    void setUp() {
        this.hints = new RuntimeHints();
        new InvoiceRuntimeHints().registerHints(
            this.hints,
            getClass().getClassLoader()
        );
    }

    @Test
    void registersConstructorInvocation() throws Exception {
        Constructor<?> constructor =
            InvoicePayload.class.getDeclaredConstructor(String.class);

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onConstructor(constructor)
                .invoke()
        ).accepts(this.hints);
    }

    @Test
    void registersMethodInvocation() throws Exception {
        Method method =
            InvoicePayload.class.getDeclaredMethod("normalize");

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onMethod(method)
                .invoke()
        ).accepts(this.hints);
    }

    @Test
    void registersResource() {
        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("invoice/templates/invoice-v1.json")
        ).accepts(this.hints);
    }

    @Test
    void registersSerialization() {
        assertThat(
            RuntimeHintsPredicates.serialization()
                .onType(AuditEvent.class)
        ).accepts(this.hints);
    }

    @Test
    void registersProxy() {
        assertThat(
            RuntimeHintsPredicates.proxies()
                .forInterfaces(
                    InvoiceGateway.class,
                    Serializable.class
                )
        ).accepts(this.hints);
    }
}
~~~

Each test has a single objective. When an assertion fails, you can isolate the registrar or hint type that needs fixing. Avoid cramming all assertions into a single test because the first failure can mask the remaining gaps.

## 12. Verifying that Spring AOT discovers the registrar

Unit tests that call `registerHints` directly do not prove that Spring will discover the registrar in the application. If you use `@ImportRuntimeHints`, you should test the AOT integration path.

Example configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceRuntimeHints.class)
class InvoiceNativeConfiguration {
}
~~~

You can use `refreshForAotProcessing` to verify that Spring processes the configuration and collects hints:

~~~java
@Test
void importedRegistrarContributesHintsDuringAot() {
    RuntimeHints generatedHints = new RuntimeHints();

    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext()) {

        context.register(InvoiceNativeConfiguration.class);
        context.refreshForAotProcessing(generatedHints);
    }

    assertThat(
        RuntimeHintsPredicates.resource()
            .forResource("invoice/templates/invoice-v1.json")
    ).accepts(generatedHints);
}
~~~

`refreshForAotProcessing` processes the configuration for AOT and collects the registrar's contributions. It does not instantiate all application beans like a normal runtime refresh. This test confirms that the `@ImportRuntimeHints` registration path is discovered during AOT processing.

If the registrar is registered statically via `META-INF/spring/aot.factories`, verify that the resource file is present in the artifact and run an appropriate AOT test. Tests that invoke the registrar directly do not test discovery via factories files.

## 13. Verifying how the registrar is attached to a component

Spring recommends placing `@ImportRuntimeHints` close to the component that needs the hints. This ensures hints are only contributed when the corresponding component participates in the `BeanFactory`.

Example:

~~~java
@Component
@ImportRuntimeHints(InvoiceRuntimeHints.class)
class InvoiceClient {
    // Perform operations that require hints.
}
~~~

If the registrar is attached to a configuration that is always imported, hints may be contributed even when the corresponding feature is not actually used. For optional modules, consider attaching the registrar to that module's auto-configuration or component.

Tests should cover two scenarios:

- Component/feature enabled: the required hints must appear.
- Component/feature not registered: hints tied exclusively to that component should not appear if the design requires conditional scoping.

Organizing things this way avoids pulling metadata from every integration into every application variant.

## 14. Using predicates to check whether the registrar over-registers

Predicates can confirm the presence of a hint, but they do not automatically decide whether a hint is too broad. The test author needs to write assertions matching the intended scope.

For example, if only one specific method is needed, test that method:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void onlyRegistersExpectedMethod() throws Exception {
    RuntimeHints hints = new RuntimeHints();
    new InvoiceRuntimeHints().registerHints(
        hints,
        getClass().getClassLoader()
    );

    Method normalize =
        InvoicePayload.class.getDeclaredMethod("normalize");

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onMethod(normalize)
            .invoke()
    ).accepts(hints);

    boolean hasUnexpectedHint =
        RuntimeHintsPredicates.reflection()
            .onMethod(InvoicePayload.class, "debugDump")
            .invoke()
            .test(hints);

    assertThat(hasUnexpectedHint).isFalse();
}
~~~

Do not replace this with a generic assertion like “the type has some reflection hint” if the actual requirement is a specific method. Conversely, if a library genuinely uses all public methods per a contract, checking the corresponding member category may be more appropriate.

Use negative assertions when metadata scoping is an intentional requirement. Avoid asserting that every other member is absent if Spring or dependencies can legitimately contribute additional hints.

## 15. How to read failures when a predicate does not match

A predicate returning `false` usually means the `RuntimeHints` object does not contain a hint matching the check condition. Analyze by category:

| Failing assertion | Check first |
|---|---|
| `onType(...).withMemberCategory(...)` | Did the registrar register the exact type and category? |
| `onConstructor(...).invoke()` | Is the constructor signature exact and is the mode `INVOKE`? |
| `onMethod(...).invoke()` | Does the method have the right declaring class, name, parameters, and invocation mode? |
| `forResource(...)` | Does the pattern match the classpath path? Was the filename confused with the source path? |
| `serialization().onType(...)` | Is the type registered for Java serialization or only with a reflection binding hint? |
| `proxies().forInterfaces(...)` | Is an interface missing or is the interface order wrong? |
| AOT integration test misses hint | Was the registrar imported/discovered? Was the configuration processed in the AOT context? |

For overloaded methods, resolve the exact `Method` using `getDeclaredMethod(name, parameterTypes)` and pass it to `onMethod(Method)`. This avoids picking the wrong method sharing the same name.

For resource patterns, check the actual resource name on the classpath as well. The predicate only confirms that metadata can cover the path, not that the file is copied into the artifact.

## 16. How RuntimeHintsPredicates and RuntimeHints Agent differ

The two tools serve two levels of testing:

| Tool | Input | What it proves |
|---|---|---|
| `RuntimeHintsPredicates` | A `RuntimeHints` object and a specific condition | Whether the declared hints match the requirement |
| Spring `RuntimeHintsAgent` | Actual calls executed in the test JVM | Whether the provided hints cover the recorded dynamic accesses |
| GraalVM Tracing Agent | Application/tests running on the JVM | Collects dynamic access configurations observed in the executed flows |
| Native executable test | Actual native binary | Whether the tested paths work on the native runtime |

`RuntimeHintsPredicates` is the right choice for registrar unit tests because it requires neither an agent nor native compilation. When you need to uncover dynamic accesses that the test author has not thought of yet, you can supplement with RuntimeHints Agent or GraalVM Tracing Agent.

No tool automatically guarantees that every application branch has been covered. Test quality still depends on inputs, profiles, configuration, and the business flows exercised.

## 17. Using Spring RuntimeHints Agent to catch missed calls

Spring Framework provides `RuntimeHintsAgent` in the `org.springframework:spring-core-test` test module. The agent records method invocations related to runtime hints while tests execute. Afterwards, the test can compare the recorded invocations against a `RuntimeHints` object.

Gradle dependency example:

~~~kotlin
dependencies {
    testImplementation("org.springframework:spring-core-test")
}
~~~

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-core-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

To use it, the Java agent must be loaded into the test JVM via the appropriate build tool configuration. `@EnabledIfRuntimeHintsAgent` allows marking tests to run only when the agent is present.

Test pattern following Spring Framework:

~~~java
import java.lang.reflect.Constructor;

final class InvoiceDecoder {

    InvoicePayload decode(String invoiceId) {
        try {
            Constructor<?> constructor =
                InvoicePayload.class.getDeclaredConstructor(String.class);
            return (InvoicePayload) constructor.newInstance(invoiceId);
        }
        catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.test.agent.EnabledIfRuntimeHintsAgent;
import org.springframework.aot.test.agent.RuntimeHintsInvocations;
import org.springframework.aot.test.agent.RuntimeHintsRecorder;

import static org.assertj.core.api.Assertions.assertThat;

@EnabledIfRuntimeHintsAgent
class InvoiceRuntimeHintsAgentTests {

    @Test
    void recordedInvocationsAreCoveredByHints() {
        RuntimeHints hints = new RuntimeHints();

        new InvoiceRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        RuntimeHintsInvocations invocations =
            RuntimeHintsRecorder.record(() -> {
                InvoiceDecoder decoder = new InvoiceDecoder();
                decoder.decode("sample-payload");
            });

        assertThat(invocations).match(hints);
    }
}
~~~

This example assumes `InvoiceDecoder.decode` actually performs the dynamic access operations under test and that the package containing that code is instrumented by the agent. When configuring the agent, choose the appropriate packages; if application code falls outside the instrumented scope, invocations may not be recorded.

The agent only observes paths that the tests execute. Be sure to exercise all important serializer, resource, proxy, and reflection paths to minimize blind spots.

## 18. GraalVM Tracing Agent as a complementary tool

The GraalVM Tracing Agent runs alongside the application on the JVM to record dynamic accesses such as reflection, resources, JNI, proxies, and serialization. It can emit JSON configuration files for native builds.

Example:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=build/native-agent-config \
  -jar build/libs/invoice-service.jar
~~~

Run the necessary test scenarios, then inspect the metadata generated by the agent. Compare it with the hints provided by Spring AOT and libraries.

Tracing Agent and RuntimeHints Agent do not replace each other:

- Spring's RuntimeHints Agent helps compare recorded invocations against `RuntimeHints`.
- GraalVM Tracing Agent generates configuration metadata in Native Image format.
- `RuntimeHintsPredicates` verifies specific requirements explicitly stated by tests.

Do not blindly copy all agent output into production. The agent may record test infrastructure, branches unused in production, or environment-dependent configuration.

## 19. Testing the native image after predicates pass

Passing predicates are a necessary condition for the registrar, but they are not final proof. After hint tests pass, run the AOT/native build and execute the actual business flows:

1. Run registrar unit tests using `RuntimeHintsPredicates`.
2. Run AOT tests to verify that Spring discovers the registrar.
3. Build the native executable using the project's Gradle/Maven configuration.
4. Launch the executable on the exact target OS/architecture.
5. Exercise the actual reflection paths, resource reads, proxy creations, or serialization.
6. Re-run with supported production profiles and configurations.
7. Check logs for missing registrations and runtime errors.

Gradle example with common GraalVM Native Build Tools configuration:

~~~bash
./gradlew processAot
./gradlew nativeCompile
~~~

With Maven:

~~~bash
./mvnw spring-boot:process-aot
./mvnw -Pnative package
~~~

Exact tasks/goals depend on plugin configuration and Spring Boot version. Not every Maven project has a `native` profile preconfigured; check the project's build configuration before using it.

## 20. Spring Framework version notes

`RuntimeHintsPredicates`, `RuntimeHints`, and `RuntimeHintsRegistrar` have been available since Spring Framework 6.0. Spring Boot 3.x applications typically use these APIs via the Spring Framework version managed by Boot.

Some supplementary testing APIs may change across versions. In particular, the RuntimeHints Agent/Recorder has different status and configuration across Spring Framework branches; Spring Framework 7.x API documentation marks some agent/recorder APIs as deprecated in favor of GraalVM's missing-registration reporting mechanism.

When upgrading Spring Framework or GraalVM in a project:

- Check the `RuntimeHintsPredicates` API and sub-predicates in the Javadoc for your exact version.
- Check whether the Java agent is still supported as configured.
- Check whether GraalVM missing-registration flags exist in your target toolchain.
- Re-run unit, AOT, and native integration tests.
- Do not upgrade `spring-core` or `spring-core-test` independently out of sync with Spring Boot dependency management.

## 21. Hint testing workflow in a library

A Spring integration library should maintain the following workflow:

1. List the dynamic accesses the code performs: reflection, resources, Java serialization, proxies, or JNI.
2. Write a `RuntimeHintsRegistrar` or corresponding annotations to declare the requirements.
3. Write unit tests invoking the registrar and checking each requirement with `RuntimeHintsPredicates`.
4. Verify the specific reflection mode: introspection or invocation.
5. Verify resource paths on the classpath and proxy interfaces in the exact order.
6. Write AOT integration tests to verify that Spring discovers the registrar.
7. Use RuntimeHints Agent or Tracing Agent when you need to discover hard-to-spot paths.
8. Run native executable tests for flows involving dynamic access.
9. Repeat testing when upgrading dependencies or changing DTOs, resources, proxies, or configuration.

A small test matrix helps track coverage:

| Category | Predicate to use | Additional testing |
|---|---|---|
| Constructor | `reflection().onConstructor(...).invoke()` | Instantiate via reflection in native |
| Method | `reflection().onMethod(...).invoke()` | Invoke method via reflection in native |
| Resource | `resource().forResource(...)` | Read classpath file in native |
| Java serialization | `serialization().onType(...)` | Serialize/deserialize real payload |
| JDK proxy | `proxies().forInterfaces(...)` | Create proxy and invoke method in native |
| JNI | No dedicated JNI factory in `RuntimeHintsPredicates` | Run actual native methods and JNI callbacks |

## 22. Key takeaways

`RuntimeHintsPredicates` is a unit testing tool for verifying that a `RuntimeHints` object declares the right reflection, resource, Java serialization, and JDK proxy requirements. Be sure to check the exact constructor/method signatures, introspection/invocation modes, resource paths, and proxy interface order.

Tests should invoke the registrar directly to inspect hint contents, followed by AOT integration tests to verify that Spring actually discovers the registrar. RuntimeHints Agent and GraalVM Tracing Agent can help find unanticipated dynamic accesses, but they only observe executed flows.

Finally, **passing predicates do not replace native executable tests**. Only when the native binary actually runs the required reflection, resource, proxy, and serialization flows on the target environment does the team have operational evidence for the tested flows.

### References

- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework 6.2 — RuntimeHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html
- Spring Framework 6.2 — ReflectionHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/ReflectionHintsPredicates.html
- Spring Framework 6.2 — ResourceHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/ResourceHintsPredicates.html
- Spring Framework 6.2 — SerializationHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/SerializationHintsPredicates.html
- Spring Framework 6.2 — ProxyHintsPredicates: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/ProxyHintsPredicates.html

Testing APIs and agent mechanisms depend on Spring Framework/GraalVM versions. Pin your toolchain, consult the Javadoc for your project's exact version, and re-run native tests when upgrading.
