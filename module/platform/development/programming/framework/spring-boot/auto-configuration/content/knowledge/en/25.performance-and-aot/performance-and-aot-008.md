# RuntimeHints and @ImportRuntimeHints for Reflection, Resources, and Proxies in Spring Boot Native Image

## 1. Why Does Native Image Need Runtime Hints?

On a standard JVM, many dynamic operations still work because the runtime can look up classes and members while the program is running. For example:
- Invoking a method via reflection when only the method name is known as a string.
- Reading a resource file using a dynamically constructed classpath path.
- Creating a JDK dynamic proxy from a list of interfaces.
- Using Java serialization or JNI.

GraalVM Native Image analyzes the application at build time under a closed-world model. Classes, methods, resources, or proxies not identified as needed may be stripped from the image. When code performs dynamic operations at runtime, the application can fail even though it runs fine on the JVM.

Spring Framework provides the `RuntimeHints` API to describe dynamic capabilities that the native runtime must retain. In Spring Boot 3.3, libraries can implement `RuntimeHintsRegistrar` and attach the registrar to configurations using `@ImportRuntimeHints`.

**Runtime hints are metadata for the AOT/native build.** They do not create beans themselves, do not alter business logic, do not turn a reflection call into a direct call, and do not make an inherently native-incompatible library fully compatible.

## 2. Hint Categories in RuntimeHints

A `RuntimeHints` object groups requirements for runtime accessibility:

| API | Purpose | Example |
| --- | --- | --- |
| `hints.reflection()` | Allows accessing types, constructors, fields, or methods via reflection | A legacy library invokes a method by name |
| `hints.resources()` | Retains resources or resource patterns in the native image | Rules files in `src/main/resources` |
| `hints.proxies()` | Declares JDK interface proxies that need to be created | `Proxy.newProxyInstance(...)` |
| `hints.serialization()` | Supports Java serialization | Reading/writing objects via `ObjectInputStream` |
| `hints.jni()` | Declares access via Java Native Interface | Integrating a native library via JNI |

This lesson focuses on reflection, resources, and proxies. Serialization and JNI are separate categories; do not confuse Java serialization with Jackson JSON serialization.

A hint should only be registered when code genuinely requires that behavior. Overly broad registration forces the native image to retain more components, increases image size, and can mask a design that relies unnecessarily on reflection.

## 3. What Can Spring Infer Automatically?

Not every occurrence of reflection or JSON requires writing a custom registrar. Spring AOT automatically generates many hints for cases the framework understands, such as:
- Request/response data types on `@RestController` methods are typically analyzed to generate reflection hints needed for serialization.
- `@ConfigurationProperties` are processed by Spring AOT to generate reflection hints for binding.
- Spring-managed configurations and proxies can be handled by the AOT engine based on metadata the framework observes.

Certain cases still require supplements:
- Libraries invoking reflection using class/method names loaded from configuration files.
- Resource paths constructed dynamically and not inferable from source.
- Applications creating JDK proxies manually with dynamic interface lists.
- DTOs bound or serialized via `WebClient`, `RestClient`, or `RestTemplate` in ways Spring cannot infer types from controller signatures.
- Third-party libraries performing dynamic behavior for which Spring lacks corresponding integration.

For DTOs requiring binding, check `@RegisterReflectionForBinding` before manually registering individual fields/methods. For custom reflection, resources, or proxies that the framework cannot infer, use `RuntimeHintsRegistrar`.

## 4. What Is RuntimeHintsRegistrar?

`RuntimeHintsRegistrar` is a callback invoked by Spring AOT so libraries can contribute hints into the `RuntimeHints` object managed by the AOT engine.

Interface contract:

~~~java
public interface RuntimeHintsRegistrar {
    void registerHints(RuntimeHints hints, ClassLoader classLoader);
}
~~~

Two parameters:
- `hints` is where reflection, resource, proxy, serialization, or JNI hints are registered.
- `classLoader` is the deployment unit's class loader. It may be unavailable in some environments, so when handling optional dependencies, do not assume this parameter is always non-`null`.

Implementations should have a no-arg constructor so Spring can instantiate them during AOT processing. The `registerHints` method is invoked at build time, not as a callback repeated every time a user makes a request.

## 5. Connecting a Registrar with @ImportRuntimeHints

For an auto-configuration library, the clearest declaration is placing `@ImportRuntimeHints` on the `@AutoConfiguration` class:

~~~java
package com.acme.catalog.autoconfigure;

import com.acme.catalog.aot.CatalogRuntimeHints;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.ImportRuntimeHints;

@AutoConfiguration
@ImportRuntimeHints(CatalogRuntimeHints.class)
public class CatalogAutoConfiguration {
}
~~~

Spring AOT detects this annotation and invokes the registrar while processing configurations. In a real library, `CatalogAutoConfiguration` must still be published via Spring Boot's auto-configuration mechanism, such as through `AutoConfiguration.imports`.

`@ImportRuntimeHints` can also be placed on Spring beans or `@Bean` factory methods. For a group of hints belonging to a library, attaching it to the auto-configuration or configuration class owning that feature generally clarifies ownership and scope.

Processing flow:

~~~mermaid
flowchart TD
    A["Spring Boot AOT processing"] --> B["Analyze CatalogAutoConfiguration"]
    B --> C["Read @ImportRuntimeHints"]
    C --> D["Instantiate CatalogRuntimeHints"]
    D --> E["Invoke registerHints(...)"]
    E --> F["Collect reflection/resource/proxy hints"]
    F --> G["Generate metadata for native-image build"]
    G --> H["GraalVM analyzes and builds native executable"]
~~~

If the application simply runs on a standard JVM without AOT processing, this annotation does not alter how reflection/resource/proxy code behaves on the JVM.

## 6. Registering Reflection for a Specific Method

Suppose a legacy library only knows a method name at runtime:

~~~java
package com.acme.catalog.legacy;

public final class LegacyDecoder {

    public String decode(String value) {
        return value.trim();
    }
}
~~~

The application invokes the method via reflection:

~~~java
Method method = LegacyDecoder.class.getDeclaredMethod(
        "decode", String.class);

String decoded = (String) method.invoke(
        new LegacyDecoder(), "  item-42  ");
~~~

On the JVM, the method can be found via reflection. In a native image, corresponding reflection access must be declared before building.

Registrar:

~~~java
package com.acme.catalog.aot;

import java.lang.reflect.Method;
import java.util.Objects;

import com.acme.catalog.legacy.LegacyDecoder;
import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public final class CatalogRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method decode = Objects.requireNonNull(
                ReflectionUtils.findMethod(
                        LegacyDecoder.class, "decode", String.class));

        hints.reflection().registerMethod(
                decode, ExecutableMode.INVOKE);
    }
}
~~~

`ExecutableMode.INVOKE` declares that the method needs to be invoked via reflection. Spring also distinguishes introspection needs from invocation; register only the permission needed for the actual operation.

If constructor or field access is needed, use the corresponding `ReflectionHints` APIs. If multiple members across a whole type are needed, you can register by `MemberCategory`, though you should restrict categories instead of enabling every access kind by default.

### When to Use RegisterReflectionForBinding?

If the goal is for Spring to bind or serialize/deserialize a DTO, the dedicated annotation is usually more suitable than registering individual methods manually:

~~~java
@Component
@RegisterReflectionForBinding(CatalogPayload.class)
class CatalogHttpAdapter {
}
~~~

`@RegisterReflectionForBinding` generates the reflection hints needed for binding, including constructors, fields, properties, and referenced types according to the processor's rules. It does not replace hints for an arbitrary method invoked via reflection.

## 7. Retaining Classpath Resources with ResourceHints

Native Image does not automatically keep every resource inside a JAR. If a library reads files by name or pattern that AOT cannot infer, register the resource:

~~~java
hints.resources().registerPattern(
        "catalog/catalog-rules.properties");
~~~

Assume the resource resides at:

~~~text
src/main/resources/
└── catalog/
    └── catalog-rules.properties
~~~

Contents:

~~~properties
mode=strict
max-items=100
~~~

The application can read the file through the class loader:

~~~java
try (InputStream input = getClass().getClassLoader()
        .getResourceAsStream("catalog/catalog-rules.properties")) {

    if (input == null) {
        throw new IllegalStateException("Catalog rules not found");
    }

    Properties properties = new Properties();
    properties.load(input);
}
~~~

`registerPattern` accepts a resource path relative to the classpath and supports patterns. If a library needs a group of files, you can register an appropriate pattern instead of each individual file.

Distinguish two cases:
- Resources packaged in the classpath/JAR need to be retained in the native image.
- Files placed externally by operators on the filesystem are deployment data; do not register them as classpath resources. Read from the filesystem path and configure mounts/volumes appropriately.

## 8. Registering JDK Dynamic Proxies

A JDK proxy creates a proxy class implementing one or more interfaces. Example:

~~~java
public interface CatalogClient {
    String findById(String id);
}
~~~

The application creates a dynamic proxy:

~~~java
CatalogClient client = (CatalogClient) Proxy.newProxyInstance(
        CatalogClient.class.getClassLoader(),
        new Class<?>[] { CatalogClient.class },
        (proxy, method, args) -> "catalog:" + args[0]);
~~~

Native Image needs to know this proxy interface is used. Register with:

~~~java
hints.proxies().registerJdkProxy(CatalogClient.class);
~~~

If the actual proxy implements multiple interfaces, pass all interfaces in the same registration call and preserve the exact order matching the created proxy. The interface list is part of the proxy descriptor.

**API limitation:** `registerJdkProxy` declares JDK interface-based proxies. Do not use it to describe CGLIB/class-based proxies. Proxies created by Spring AOP or other frameworks may already be supported by Spring AOT; if creating proxies via a custom mechanism, verify the exact proxy type and corresponding native guidance.

## 9. Combining Reflection, Resources, and Proxies in One Registrar

A library often needs several kinds of hints at once. You can group them in a single implementation:

~~~java
package com.acme.catalog.aot;

import java.lang.reflect.Method;
import java.util.Objects;

import com.acme.catalog.api.CatalogClient;
import com.acme.catalog.legacy.LegacyDecoder;
import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public final class CatalogRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method decode = Objects.requireNonNull(
                ReflectionUtils.findMethod(
                        LegacyDecoder.class, "decode", String.class));

        // Method invoked via reflection.
        hints.reflection().registerMethod(
                decode, ExecutableMode.INVOKE);

        // File read from classpath in native runtime.
        hints.resources().registerPattern(
                "catalog/catalog-rules.properties");

        // Application creates a JDK proxy for this interface.
        hints.proxies().registerJdkProxy(CatalogClient.class);
    }
}
~~~

Attach the registrar to the auto-configuration:

~~~java
@AutoConfiguration
@ImportRuntimeHints(CatalogRuntimeHints.class)
public class CatalogAutoConfiguration {
}
~~~

The module structure can look like:

~~~text
acme-catalog-autoconfigure/
├── src/main/java/com/acme/catalog/
│   ├── api/CatalogClient.java
│   ├── legacy/LegacyDecoder.java
│   ├── aot/CatalogRuntimeHints.java
│   └── autoconfigure/CatalogAutoConfiguration.java
└── src/main/resources/
    └── catalog/catalog-rules.properties
~~~

A registrar should describe the exact behaviors owned by the module. If multiple independent integrations need distinct hints, you can split into small registrars and attach each to its corresponding auto-configuration for easier review and maintenance.

## 10. Testing Registrars with RuntimeHintsPredicates

You do not need to build a native image for every small change in a registrar. Spring provides `RuntimeHintsPredicates` to test whether hints have been registered into a `RuntimeHints` object.

JUnit 5 and AssertJ example:

~~~java
package com.acme.catalog.aot;

import java.lang.reflect.Method;

import com.acme.catalog.api.CatalogClient;
import com.acme.catalog.legacy.LegacyDecoder;
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogRuntimeHintsTests {

    @Test
    void registersReflectionResourceAndProxyHints() throws Exception {
        RuntimeHints hints = new RuntimeHints();

        new CatalogRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        Method decode = LegacyDecoder.class.getDeclaredMethod(
                "decode", String.class);

        assertThat(RuntimeHintsPredicates.reflection()
                .onMethod(decode).invoke())
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("catalog/catalog-rules.properties"))
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.proxies()
                .forInterfaces(CatalogClient.class))
                .accepts(hints);
    }
}
~~~

Run tests on the JVM:

~~~bash
./gradlew test --tests "*CatalogRuntimeHintsTests"
~~~

Or Maven:

~~~bash
./mvnw -Dtest=CatalogRuntimeHintsTests test
~~~

This test verifies three contracts of the registrar:
- Method `LegacyDecoder.decode(String)` is registered with invocation mode.
- Resource `catalog/catalog-rules.properties` has a hint.
- JDK proxy for `CatalogClient` has a hint.

`RuntimeHintsPredicates` confirms metadata has been declared. It does not prove the entire native executable will run successfully; AOT processing, native-image build, and tests on the executable for critical flows are still required.

## 11. Other Ways to Register Hints

`@ImportRuntimeHints` is usually the clearest choice when hints belong to a specific configuration. Spring Framework also supports two other approaches.

### 11.1. Registering via META-INF/spring/aot.factories

You can register a registrar statically in the resource:

`src/main/resources/META-INF/spring/aot.factories`

Contents:

~~~properties
org.springframework.aot.hint.RuntimeHintsRegistrar=com.acme.catalog.aot.CatalogRuntimeHints
~~~

This approach fits when a library wants to contribute hints without tying the registrar to a specific configuration class. The implementation needs a no-arg constructor and must be on the classpath during AOT processing.

Do not register the same registrar through multiple mechanisms without reason; avoid duplicating metadata and obscuring its source.

### 11.2. Native Image JSON Metadata

GraalVM also supports static metadata in JSON files under `META-INF/native-image`. Spring Boot 3.3 notes that automatically generated hints reside in a directory named by `groupId/artifactId`; supplemental metadata should be placed in a separate directory to avoid colliding with generated output.

The JSON approach is useful when:
- A library does not integrate with Spring AOT.
- Metadata needs to be shared across multiple native applications.
- Metadata is provided by a third-party library.
- Certain hints are inconvenient to express via a registrar.

If you already use `RuntimeHintsRegistrar` for a Spring library, keeping hints in code typically ensures type references are compile-checked and makes unit testing easier.

## 12. Using the Tracing Agent to Find Missing Hints

When an application runs fine on the JVM yet fails in a native image, the GraalVM tracing agent can record reflection, resource, or proxy operations that actually occur on the JVM.

Example running the AOT application on the JVM with the agent:

~~~bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/my-application.jar
~~~

Next:
1. Exercise the application flows that use reflection/resources/proxies.
2. Stop the application so the agent writes configuration files.
3. Inspect the generated hints and identify entries genuinely belonging to the application.
4. Remove metadata that only serves test infrastructure if not needed at runtime.
5. Place the required files into `src/main/resources/META-INF/native-image/` or translate required entries into a `RuntimeHintsRegistrar`.
6. Rebuild the native image and run regression tests.

The tracing agent only records code paths that were executed. If a business branch is not exercised, the agent cannot discover that branch's hints. Therefore, the agent assists investigation and does not replace understanding the code and designing test coverage.

## 13. Nested Configuration Properties and Boot's Built-In Hints

Spring Boot automatically generates reflection hints for `@ConfigurationProperties` during AOT processing. However, nested properties using a separate non-inner class must be annotated with `@NestedConfigurationProperty` so Spring recognizes the binding structure in native images.

Example:

~~~java
@ConfigurationProperties(prefix = "catalog")
public class CatalogProperties {

    private String region;

    @NestedConfigurationProperty
    private final RetrySettings retry = new RetrySettings();

    // getters...
}
~~~

If `RetrySettings` is an independent class, the annotation tells Spring AOT this is a nested configuration property. For constructor binding or records, place the annotation on the corresponding field/parameter per Boot's guidelines.

This is hint/binding metadata already supported by Spring Boot's rules. Do not add a blanket reflection registrar for all properties just to compensate for a nested type that was not annotated properly.

## 14. Common Mistakes and Troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Method works via reflection on JVM yet fails in native | Missing method invocation hint | Register the exact method via `registerMethod(..., ExecutableMode.INVOKE)` |
| Resource is in JAR yet unreadable in native | Resource not retained by reachability metadata | Register `resources().registerPattern(...)` and verify the path |
| `Proxy.newProxyInstance` fails in native | Missing JDK proxy hint or mismatched interface list | Register `registerJdkProxy` with the exact interfaces and order |
| Proxy hint present yet CGLIB still fails | Wrong hint used for class-based proxy | Analyze the specific proxy mechanism; `registerJdkProxy` is only for JDK interface proxies |
| JSON DTO fails reflection | AOT did not recognize the DTO's binding path | Check `@RegisterReflectionForBinding` or corresponding binding hints |
| Registrar is never called | Missing `@ImportRuntimeHints` or `aot.factories` registration | Check configurations discovered by AOT and build logs |
| Hints only work in IDE | Resource or registrar not packaged properly into module/JAR | Check source sets, dependencies, and resources in the artifact |
| Native image still missing hints after edit | Running stale binary or did not perform AOT/native rebuild | Re-run AOT processing, native compile, and test the new executable |
| Native image bloats in size | Overly broad registration keeping unnecessary members/types | Narrow reflection scope and resource patterns |
| Tracing agent produces strange entries | Agent recorded test framework or unrelated code paths | Use access filters, review files, and retain only needed hints |
| Nested properties fail to bind in native | Independent nested class unrecognized | Use `@NestedConfigurationProperty` in the right place |
| Registrar depending on optional class causes compile/runtime error | Directly referencing optional type when dependency is absent | Use classloader-aware registration such as `registerTypeIfPresent` when appropriate |

## 15. Workflow for Implementing and Reviewing Runtime Hints

1. **Reproduce the error:** identify which operation works on the JVM yet fails in native.
2. **Check automatic support:** see whether Spring AOT already infers hints for controllers, configuration properties, binding, or proxies.
3. **Choose the right hint type:** reflection, resource, JDK proxy, serialization, or JNI.
4. **Restrict access scope:** register only the methods/members/resources/interfaces genuinely needed.
5. **Contribute hints:** implement `RuntimeHintsRegistrar` and wire via `@ImportRuntimeHints`.
6. **Write unit tests:** use `RuntimeHintsPredicates` to verify each hint.
7. **Run AOT/native build:** confirm the registrar is processed and metadata is present in the artifact.
8. **Run native regression tests:** exercise the exact code path that previously failed.
9. **Review size and scope:** remove redundant hints, overly broad resource patterns, or unnecessary reflection access.
10. **Document the rationale:** explain why each hint exists so maintainers know when it can be removed.

Review flow:

~~~mermaid
flowchart TD
    A["Identify dynamic operation"] --> B{"Did Spring AOT infer the hint?"}
    B -->|"Yes"| C["Use automatic hint"]
    B -->|"No"| D{"Required access type"}
    D --> E["Reflection"]
    D --> F["Resource"]
    D --> G["JDK Proxy"]
    E --> H["RuntimeHintsRegistrar"]
    F --> H
    G --> H
    H --> I["@ImportRuntimeHints"]
    I --> J["RuntimeHintsPredicates test"]
    J --> K["AOT and native build"]
    K --> L["Native regression test"]
~~~

## 16. Knowledge Self-Check

1. What is `RuntimeHints` used for? **Describing dynamic capabilities that must be retained in a native image.**
2. At which phase is `RuntimeHintsRegistrar` invoked? **During AOT processing at build time.**
3. Which annotation connects a registrar to a configuration? **`@ImportRuntimeHints`.**
4. Which API registers a method invoked via reflection? **`hints.reflection().registerMethod(method, ExecutableMode.INVOKE)`.**
5. Which API retains a classpath resource? **`hints.resources().registerPattern(...)`.**
6. Which API declares a JDK dynamic proxy? **`hints.proxies().registerJdkProxy(...)`.**
7. Does `registerJdkProxy` register CGLIB class proxies? **No; this API is for JDK interface proxies.**
8. Which annotation provides reflection hints for DTO binding? **`@RegisterReflectionForBinding`.**
9. Which API is used to verify hints in unit tests? **`RuntimeHintsPredicates`.**
10. Does a passing RuntimeHintsPredicates unit test prove the native executable works? **No; AOT/native builds and regression tests on the image are still needed.**
11. Does a file external to the application on the filesystem need a classpath resource hint? **No; configure an appropriate filesystem path/mount instead.**
12. Why should you not register all reflection members by default? **It enlarges the image and grants broader access permissions than actually needed.**

## Official References

- [Spring Boot 3.3.13 — Advanced Native Images Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html): custom hints, `RuntimeHintsRegistrar`, `@ImportRuntimeHints`, testing hints, tracing agent, and static metadata.
- [Spring Framework 6.1 — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): AOT model and Runtime Hints.
- [Spring Framework 6.1 — `RuntimeHintsRegistrar` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/aot/hint/RuntimeHintsRegistrar.html): contract and how to register registrars.
- [Spring Framework 6.1 — `ProxyHints` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/aot/hint/ProxyHints.html): JDK proxy hints and interface lists.
- [Spring Framework 6.1 — `RuntimeHintsPredicates` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.22/javadoc-api/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html): testing reflection, resource, and proxy hints.
- [Spring Framework 6.1 — `@RegisterReflectionForBinding` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html): reflection hints for data binding and serialization.
