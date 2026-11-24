# Distinguishing Classpath Conditions from Native Image Reachability Declarations

## Learning Objectives

When developing auto-configuration for a Spring Boot library, two questions are commonly confused:

1. **Is the optional library or class present on the classpath for this configuration to activate?**
2. **If the application runs under GraalVM Native Image, which classes, methods, resources, or proxies must be retained and allowed for dynamic access?**

The first question belongs to **auto-configuration conditions**, such as `@ConditionalOnClass`. The second belongs to **reachability metadata/runtime hints**, such as `RuntimeHintsRegistrar`. Both mechanisms can appear together in an integration, yet they address two different phases and two different problems.

This lesson uses Spring Boot 3.3, Spring Framework 6.1, and Java 17+ to explain:

- How `@ConditionalOnClass` checks whether a dependency is on the classpath.
- Why Spring AOT evaluates conditions at build time and produces a fixed bean graph for native image.
- How GraalVM Native Image analyzes reachability under the closed-world assumption.
- When reflection, resource, serialization, JDK proxy, and JNI hints must be declared.
- How to register hints using `RuntimeHintsRegistrar`, `@ImportRuntimeHints`, and JSON metadata.
- How to test conditions and runtime hints, then verify with a native executable.

## 1. Two Different Questions in the Build Lifecycle

Suppose the Acme library has an integration for an optional vendor codec SDK:

- Application adds only Acme core: no codec SDK present.
- Application adds codec SDK: Acme can create the codec adapter.
- The adapter uses reflection to invoke a method on an SDK-generated DTO.
- The adapter reads templates from resources whose names are dynamically assembled by locale.

There are two decisions:

**Decision A — Should the adapter be registered?**

If the codec SDK is not on the classpath, the codec auto-configuration must not be applied. That is the job of `@ConditionalOnClass`.

**Decision B — If the adapter is included in the native image, which dynamic accesses must still work?**

Native Image static analysis may fail to infer methods invoked via reflection or resources looked up by runtime-constructed names. That is the job of runtime hints/reachability metadata.

| Criterion | Classpath Condition | Native-Image Reachability Declaration |
| --- | --- | --- |
| Question | Is the dependency/class present to enable configuration? | Which dynamic elements must be retained and accessible in the executable? |
| Common Spring mechanism | `@ConditionalOnClass`, `@ConditionalOnMissingClass` | `RuntimeHints`, `RuntimeHintsRegistrar`, `@ImportRuntimeHints` |
| Input | Classpath and configuration metadata | Dynamic operations performed by the application/library |
| Timing in standard JVM | When Spring processes configurations | When Spring AOT generates hints and during Native Image build |
| Role in native build | Shapes configuration/bean graph at AOT build time | Guides Native Image to retain elements needed for dynamic access |
| What it cannot do | Does not grant reflection permission or put methods into metadata | Does not add missing JARs/classes and does not enable auto-configuration |

A class can exist in a JAR without needing reflection. Conversely, a class declared in reflection hints must still exist in the dependency graph if the application needs to use that class. Thus the two concepts cannot substitute for each other.

## 2. Classpath Conditions with @ConditionalOnClass

`@ConditionalOnClass` is a Spring Boot conditional annotation. It matches only when the specified class exists on the classpath being used by Spring.

Example:

~~~java
package com.acme.codec.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
public class AcmeCodecAutoConfiguration {

    @Bean
    CodecAdapter codecAdapter() {
        return new CodecAdapter();
    }
}
~~~

In this example:

- If the JAR containing `com.vendor.codec.Codec` is on the classpath, the condition can match.
- If the dependency is absent, the configuration class is not applied.
- `@ConditionalOnClass` does not create the codec bean and does not register reflection metadata.
- The condition only decides whether the configuration is eligible to participate in bean registration; other conditions can still exclude the configuration.

### 2.1. Using Class Names When Dependencies Are Optional

You can declare the class using a string name:

~~~java
@ConditionalOnClass(name = "com.vendor.codec.Codec")
~~~

This approach is useful when the autoconfigure module does not want to reference the optional dependency's type directly. It also avoids having to resolve that type just to read annotations.

Spring Boot can read annotation metadata on configuration classes using ASM before the class is loaded. However, be careful with `@Bean` methods whose return types or parameter types come from an optional SDK: the JVM may have to resolve method signatures before the method-level condition is evaluated. If a group of beans requires the SDK, place `@ConditionalOnClass` at the configuration-class level and isolate the integration in a separate class.

### 2.2. Classpath Conditions Do Not Check Reachability

Suppose class Codec is in the JAR, the condition matches, and Spring registers CodecAdapter. That still does not prove every method the adapter invokes via reflection will exist in the native executable.

A classpath condition does not ask:

- Is the method called directly from an entry point?
- Can GraalVM see a call path to the method?
- Is the resource looked up by a constant string or a name assembled at runtime?
- Is a JDK proxy created with a dynamic interface list?

Those are questions for Native Image static analysis and reachability metadata.

## 3. Spring AOT Evaluates Conditions at Build Time

A Spring Boot application on the JVM typically constructs its bean graph at startup. Spring Boot can react to the classpath, profiles, properties, and bean definitions at that time.

When Spring AOT is enabled for a native image, Spring must pre-generate the assets needed for GraalVM analysis. The AOT process initializes the ApplicationContext up to the stage where bean definitions are ready, evaluates conditions, and generates corresponding code/metadata.

**Conditions are evaluated against the Environment at build time.** The native executable's classpath is also fixed at build time. Therefore:

- Dependency present on classpath during AOT: the `@ConditionalOnClass` branch can enter the bean graph.
- Dependency absent during AOT: that branch is not included in the generated bean graph.
- `@ConditionalOnProperty` and profiles affecting bean creation are also evaluated in the build environment.
- Changing properties/profiles when running the native executable cannot enable a bean excluded from the AOT bean graph or disable a bean already generated in the graph.

This **does not mean every property is frozen**. Properties read by business logic after beans are created can still affect runtime behavior. The limitation lies in properties/conditions that decide which beans are registered in the ApplicationContext.

Example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.codec",
        name = "enabled",
        havingValue = "true")
class AcmeCodecAutoConfiguration {
    // Beans for the codec integration.
}
~~~

If `acme.codec.enabled=true` in the environment running AOT, the configuration branch is processed at build time. If the property is only set to true after the native executable has been built, the application cannot rely on that property to create a new bean branch.

### 3.1. Why Must AOT Fix the Bean Graph?

Native Image uses the closed-world assumption: it analyzes the program from entry points and includes only elements that static analysis determines are needed in the executable, along with elements described by metadata.

If Spring were allowed to arbitrarily construct new bean graphs from properties or classpath at runtime, GraalVM could not know which classes/methods must be retained. AOT shifts most configuration decisions to build time to create an analyzable graph.

### 3.2. Design Options When Runtime Variation Is Needed

If an application needs to select a strategy via a runtime property, consider pre-registering the required strategies in the bean graph and letting a service select the implementation based on runtime configuration.

For example, both strategies are packaged and have required hints:

~~~java
@Service
class CodecSelector {

    private final Map<String, CodecAdapter> adapters;

    CodecSelector(Map<String, CodecAdapter> adapters) {
        this.adapters = adapters;
    }

    CodecAdapter select(String mode) {
        CodecAdapter adapter = adapters.get(mode);
        if (adapter == null) {
            throw new IllegalArgumentException("Unsupported codec mode: " + mode);
        }
        return adapter;
    }
}
~~~

This selects among existing beans. It does not ask Spring to create extra beans after AOT. If a strategy depends on an SDK not packaged in the native executable, the selector cannot make that dependency appear.

## 4. Native Image Reachability and the Closed-World Assumption

GraalVM Native Image performs static analysis from the application's entry points. Direct calls typically form reachability paths that the compiler can trace.

Example:

~~~java
public class Application {

    public static void main(String[] args) {
        new Greeter().sayHello();
    }
}

class Greeter {

    void sayHello() {
        System.out.println("Hello native image");
    }
}
~~~

The call path from `main` to `Greeter.sayHello()` can be statically analyzed. If no path requires a class/method, Native Image can omit it from the executable.

Difficulty arises with behavior determined only at runtime:

~~~java
String className = configuration.getImplementationClass();
Class<?> type = Class.forName(className);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

The class name comes from configuration. Static analysis cannot always infer which class and constructor will be used. If the application requires this kind of access, appropriate metadata must be supplied or the design changed so the compiler sees a static call path.

### 4.1. Dynamic Access Kinds Commonly Requiring Declaration

| Kind | Example | Corresponding Hints |
| --- | --- | --- |
| Reflection | `Class.forName`, `Method.invoke`, invoking constructor via reflection | Reflection hints |
| Dynamic resources | `ClassLoader.getResource(name)` with name assembled from property | Resource hints |
| Serialization | Reading/writing objects via Java serialization | Serialization hints |
| JDK dynamic proxy | `Proxy.newProxyInstance` with interface list | Proxy hints |
| JNI | Native code looking up Java classes, fields, or methods | JNI hints |

Not every reflection/resource access needs manual declaration. Native Image can recognize some operations with constant arguments; Spring AOT also infers hints for many familiar contracts. Supplement metadata only for accesses the toolchain cannot infer.

### 4.2. Having a Class on the Classpath Does Not Mean It Is Automatically Kept

A library may sit on the classpath while most of its code is unreferenced from entry points. Static analysis can remove unreachable portions. If code needs that class only through reflection, the required elements must be declared.

Conversely, a hint does not replace a dependency. If a JAR is not packaged, declaring reflection for that class does not download the JAR or add the class to the application.

## 5. Spring RuntimeHints: API for Declaring Accessibility

Spring Framework provides the `RuntimeHints` API to describe dynamic accesses required in a native image. This API groups:

- `hints.reflection()`: classes, constructors, methods, and fields needing reflection.
- `hints.resources()`: resource patterns and resource bundles.
- `hints.serialization()`: types needing Java serialization.
- `hints.proxies()`: JDK dynamic proxies.
- `hints.jni()`: Java access from native code via JNI.

Spring AOT converts these hints into metadata usable by GraalVM.

Example registering a resource:

~~~java
hints.resources().registerPattern("acme/templates/*.txt");
~~~

Example registering method reflection:

~~~java
Method method = ReflectionUtils.findMethod(
        AcmePayload.class, "encode", String.class);

hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
~~~

Register only the exact permission required. If code only needs to introspect a method, do not declare broader invoke permission. Broader hints can enlarge the executable and make reflection scope harder to control.

## 6. Writing a RuntimeHintsRegistrar for a Library

A library can package required hints in a class implementing `RuntimeHintsRegistrar`.

**File:** `src/main/java/com/acme/codec/AcmeCodecRuntimeHints.java`

~~~java
package com.acme.codec;

import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public final class AcmeCodecRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method encode = ReflectionUtils.findMethod(
                AcmePayload.class, "encode", String.class);

        if (encode == null) {
            throw new IllegalStateException(
                    "Expected AcmePayload.encode(String) to exist");
        }

        hints.reflection().registerMethod(encode, ExecutableMode.INVOKE);
        hints.resources().registerPattern("acme/templates/*.txt");
        hints.proxies().registerJdkProxy(AcmeCodecPlugin.class);
        hints.serialization().registerType(AcmeSnapshot.class);
    }
}
~~~

The types AcmePayload, AcmeCodecPlugin, and AcmeSnapshot are the library's APIs in the example:

- AcmePayload has method encode(String) invoked via reflection.
- AcmeCodecPlugin is an interface used to create a JDK dynamic proxy.
- AcmeSnapshot is a type written/read via Java serialization.
- Template files are looked up by names that may vary at runtime.

The example above intentionally registers four hint categories to illustrate the API. In a real library, keep only the lines matching how the code operates. If AcmeSnapshot does not use Java serialization, remove serialization registration; if no JDK proxy is created, remove the proxy hint.

### 6.1. Attaching the Registrar with @ImportRuntimeHints

Place the registrar close to the configuration or bean using the dynamic accesses:

~~~java
package com.acme.codec.autoconfigure;

import com.acme.codec.AcmeCodecRuntimeHints;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.ImportRuntimeHints;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ImportRuntimeHints(AcmeCodecRuntimeHints.class)
public class AcmeCodecAutoConfiguration {
}
~~~

`@ImportRuntimeHints` lets Spring process the registrar when the component or bean method is registered. When a configuration has a condition and is not added to the BeanFactory, hints attached to that configuration are not contributed either. This is why hints should live close to the code needing them.

If a registrar must be registered statically for the whole deployment unit, Spring Framework supports the file:

~~~text
META-INF/spring/aot.factories
~~~

With properties contents:

~~~properties
org.springframework.aot.hint.RuntimeHintsRegistrar=com.acme.codec.AcmeCodecRuntimeHints
~~~

The registrar needs a no-arg constructor to be instantiated by this mechanism. When possible, prefer `@ImportRuntimeHints` because it ties hint lifecycle to the component/bean actually contributed.

### 6.2. Hints for Optional Dependencies

If a registrar can be used across different classpaths, do not assume optional classes are always present. Use APIs that check classes by name and class loader, such as `registerTypeIfPresent`, or place the registrar in an integration artifact loaded only when the corresponding SDK is present.

Class-name-based example:

~~~java
hints.reflection().registerTypeIfPresent(
        classLoader,
        "com.vendor.codec.OptionalPayload",
        typeHint -> typeHint.withMethod(
                "decode",
                java.util.List.of(
                        org.springframework.aot.hint.TypeReference.of(String.class)),
                ExecutableMode.INVOKE));
~~~

This enables conditional hint registration based on the class loader without forcing code to directly reference the optional type. However, if the integration is not on the classpath, that integration's adapter should not enter the bean graph.

## 7. Automatic Hints and Cases Needing Supplements

Spring AOT already infers many common needs. For example, when Spring recognizes a controller return type needing JSON serialization, the framework can add required reflection hints. Certain annotations such as `@EventListener` are designed to tell Spring a method must be invoked via reflection.

Before manually registering hints, check whether the framework already supports that case.

### 7.1. @RegisterReflectionForBinding

When a DTO needs reflection for binding or serialization/deserialization that Spring cannot infer automatically, you can use the utility annotation:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;

@RegisterReflectionForBinding(AcmePayload.class)
@Configuration
class AcmeJsonConfiguration {
}
~~~

This annotation suits reflection needed when binding objects, including constructors, fields, properties, and nested types per the binding registrar's rules. It does not replace resource hints, proxy hints, or JNI hints.

### 7.2. Do Not Arbitrarily Register All Reflection

For example, enabling every field/method/constructor of a class can bloat metadata and expand the access surface. Prefer:

- Registering only methods/constructors actually invoked.
- Registering fields only if code genuinely reads/writes them via reflection.
- Using binding hints for DTO binding instead of manually opening the entire class.
- Registering narrow resource patterns rather than pulling all classpath resources into the executable.
- Registering proxies only with the exact interface list and exact order needed.

## 8. Direct JSON Metadata for GraalVM

In addition to Spring RuntimeHints, static JSON metadata can be supplied. Spring Boot 3.3 describes hint files generated or consumed in the directory:

~~~text
META-INF/native-image/{groupId}/{artifactId}/
~~~

Common configuration file types in Boot 3.3's toolchain include:

- `reflect-config.json`
- `resource-config.json`
- `serialization-config.json`
- `proxy-config.json`
- `jni-config.json`

Example of a resource needing to be packaged:

**File:** `src/main/resources/META-INF/native-image/com.acme/acme-codec-additional/resource-config.json`

~~~json
{
  "resources": {
    "includes": [
      {
        "pattern": "\\\\Qacme/templates/default.txt\\\\E"
      }
    ]
  }
}
~~~

This is the traditional Native Image JSON configuration format used in the corresponding toolchain. JSON metadata structure can vary across GraalVM versions; check the schema supported by the native-image version in use. Spring Boot recommends placing static hint files in a separate subdirectory under META-INF/native-image to avoid colliding with the directory generated by Spring AOT.

For Spring Boot libraries, RuntimeHints is generally easier to integrate and test because hints are expressed via a Java API. Static JSON remains useful when:
- Metadata comes from a third-party library lacking a registrar.
- Specific Native Image configurations must be declared.
- The project already has verified metadata to package alongside the artifact.

### 8.1. Reachability Metadata Repository and Tracing Agent

GraalVM provides the Reachability Metadata Repository containing community-contributed metadata for many libraries. Native Build Tools can fetch metadata matching dependencies/versions during the build.

The tracing agent can run alongside a JVM application or test suite to record reflection, resources, proxies, and dynamic accesses actually performed. The agent helps surface missing entries, yet only records code paths executed during that collection run.

When using the agent:
1. Run key business scenarios.
2. Run tests covering branches with dynamic reflection/resources.
3. Use access filters if output contains many test-framework accesses.
4. Review generated metadata and remove unnecessary entries.
5. Re-run native build and native tests.

The agent is a discovery tool, not proof that every code path is covered. Unexecuted scenarios may still lack metadata.

## 9. Testing Classpath Conditions and Runtime Hints Separately

The two mechanisms must have separate tests because they protect two different contracts.

### 9.1. Testing @ConditionalOnClass with FilteredClassLoader

**File:** `src/test/java/com/acme/codec/OptionalCodecConditionTests.java`

~~~java
package com.acme.codec;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalCodecConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(OptionalCodecAutoConfiguration.class));

    @Test
    void createsAdapterWhenOptionalCodecClassIsPresent() {
        runner.run(context ->
                assertThat(context).hasSingleBean(CodecAdapter.class));
    }

    @Test
    void skipsAdapterWhenOptionalCodecClassIsAbsent() {
        runner.withClassLoader(new FilteredClassLoader(OptionalCodecApi.class))
                .run(context ->
                        assertThat(context).doesNotHaveBean(CodecAdapter.class));
    }

    @AutoConfiguration
    @ConditionalOnClass(name = "com.acme.codec.OptionalCodecApi")
    static class OptionalCodecAutoConfiguration {

        @Bean
        CodecAdapter codecAdapter() {
            return new CodecAdapter();
        }
    }
}

interface OptionalCodecApi {
}

class CodecAdapter {
}
~~~

The first test confirms the class is on the test classpath so the condition matches. The second uses FilteredClassLoader to simulate a classpath missing the optional API; the adapter bean is not registered.

This test verifies only the classpath condition. It does **not** prove reflection/resource metadata is sufficient for a native executable.

### 9.2. Testing RuntimeHintsRegistrar with RuntimeHintsPredicates

**File:** `src/test/java/com/acme/codec/AcmeCodecRuntimeHintsTests.java`

~~~java
package com.acme.codec;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeCodecRuntimeHintsTests {

    @Test
    void registersReflectionAndResourceHints() {
        RuntimeHints hints = new RuntimeHints();

        new AcmeCodecRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
                .onMethod(AcmePayload.class, "encode")
                .invoke())
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("acme/templates/default.txt"))
                .accepts(hints);
    }
}
~~~

Assume AcmeCodecRuntimeHints registers the encode method and resource pattern as in the earlier example. The test uses `RuntimeHintsPredicates` to verify whether the registrar declared the right hints.

Testing can be extended to serialization and proxies using corresponding predicates. Do not merely assert that the registrar ran; assert the exact methods/resources/types the application needs.

### 9.3. Unit Testing Hints Is Not Enough

RuntimeHintsPredicates checks the metadata Spring generates. It does not run GraalVM Native Image itself and does not prove the actual executable can start.

A native pipeline should include:
- JVM tests for business logic and auto-configuration.
- Classpath condition tests for optional dependencies.
- Unit tests for RuntimeHintsRegistrar.
- AOT processing at build time.
- Native compilation.
- Smoke/integration tests running the native executable itself and exercising key reflection/resource/proxy paths.

## 10. Verification Workflow from Dependencies to Native Executable

A practical workflow:

1. **Inspect the dependency graph:** is the optional SDK actually added to the needed module/starter?
2. **Test classpath conditions:** use FilteredClassLoader or test contexts to verify branches with/without the SDK.
3. **Run AOT processing:** use the right profile/task of the Spring Boot plugin so conditions are evaluated with the intended build-time Environment.
4. **Inspect generated assets:** view generated sources/bytecode and hints under the build tool's AOT output.
5. **Test custom hints:** run RuntimeHintsPredicates tests.
6. **Build the native image:** use GraalVM Native Image or a native build plugin matching the JDK/Boot version.
7. **Run the native executable:** exercise code paths using reflection, resources, proxies, serialization, or JNI.
8. **Investigate missing registration errors:** read Native Image messages, add exact hints, and repeat tests.

With Spring Boot 3.3, documentation notes AOT output typically resides in:
- Maven: `target/spring-aot/main/resources`.
- Gradle: `build/generated/aotResources`.

Paths can vary by plugin/build layout. Check your project's actual output rather than assuming a fixed directory.

## 11. Scenario Combining Both Mechanisms

Suppose Acme provides a Vendor Codec integration:

**Classpath condition**

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ImportRuntimeHints(AcmeCodecRuntimeHints.class)
class AcmeVendorCodecAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CodecAdapter.class)
    CodecAdapter codecAdapter() {
        return new CodecAdapter();
    }
}
~~~

**When a standard JVM application runs:**

- SDK on classpath: classpath condition matches and the adapter bean can be created.
- SDK absent: the configuration class is skipped.

**When the application undergoes AOT/native build:**

- SDK on classpath at AOT time: the configuration branch can enter the bean graph.
- SDK absent at AOT time: the branch is not created in the AOT bean graph.
- The registrar is processed when the configuration is contributed; hints are transferred into native metadata.
- GraalVM uses static analysis together with metadata to retain dynamic accesses needed by the adapter.

**When the native executable runs:**

- The classpath cannot be changed to add another SDK.
- The bean graph is already fixed per the AOT build.
- Declared reflection/resources/proxies can function per the packaged hints.
- Runtime properties cannot enable an auto-configuration excluded during AOT.

This example shows how conditions and hints cooperate sequentially: conditions decide whether the integration participates in AOT; hints describe dynamic accesses the integration needs once included in the executable.

## 12. Common Mistakes When Confusing Both Mechanisms

1. **Assuming @ConditionalOnClass automatically registers reflection.** The condition only checks the classpath; add RuntimeHints when dynamic access is needed.
2. **Assuming a reflection hint adds a missing dependency.** Hints do not replace dependency management; the SDK must still be on the classpath at build time.
3. **Testing only classpath conditions and concluding native image compatibility.** Condition tests do not check reflection/resource/proxy metadata.
4. **Testing only RuntimeHintsRegistrar and concluding the bean is activated.** Hint tests do not verify auto-configuration conditions or the dependency graph.
5. **Changing a property to enable a bean after a native build.** AOT already evaluated conditions and fixed the bean graph; select appropriate profiles/properties at build time.
6. **Using a property condition as a dynamic bean on/off switch in a native executable.** Pre-register strategies and select runtime behavior inside a bean when the requirement is merely switching handling logic.
7. **Placing @ConditionalOnClass on a method whose return type belongs to an optional SDK.** The JVM may resolve method signatures before the condition; guard at the class level and isolate the integration.
8. **Declaring reflection for an entire class when only one method is called.** Overly broad metadata enlarges the access surface and may increase image size; register precisely.
9. **Forgetting dynamically assembled resource names.** Native Image cannot always infer resource names; register a sufficiently narrow pattern.
10. **Assuming Spring AOT always finds every dynamic access automatically.** The framework infers many contracts yet cannot know every reflection/resource lookup performed by a library.
11. **Registering hints on an unrelated configuration.** Hints may get packaged even when the feature is unused; place @ImportRuntimeHints near the component needing them.
12. **Using the tracing agent without exercising enough scenarios.** The agent records only executed code paths; add tests for rare branches.
13. **Keeping the entire tracing agent output of a test suite verbatim.** Test frameworks can generate lots of metadata unnecessary at runtime; review and filter output.
14. **Using JSON metadata matching a schema from a different GraalVM version.** Verify the format and schema supported by your project's toolchain.
15. **Running only JVM tests after adding hints.** Most JVMs do not need those hints; run AOT/native builds and the native executable to verify effect.

## 13. Review Checklist for Native-Image-Ready Spring Boot Libraries

### Classpath and Auto-Configuration

- [ ] Each optional integration has clear dependencies and classpath conditions.
- [ ] Optional classes are guarded at the class level if method signatures reference them.
- [ ] Property/profile conditions affecting the bean graph are supplied during build-time AOT.
- [ ] Auto-configurations have tests when dependencies are present and when excluded from the classpath.
- [ ] No reliance on altering classpath or bean graph after native build.

### Runtime Hints

- [ ] Identified reflection, resource, serialization, JDK proxy, and JNI operations.
- [ ] Checked which parts Spring AOT infers automatically.
- [ ] Registrars register only needed elements.
- [ ] Hints are attached near components via @ImportRuntimeHints when appropriate.
- [ ] Resource patterns are sufficiently specific.
- [ ] Optional classes are handled via class loader checks or split into appropriate artifacts.
- [ ] RuntimeHintsPredicates tests verify required metadata.

### Native Verification

- [ ] AOT processing runs with accurate build profiles/properties.
- [ ] Generated AOT assets are inspected when diagnosing issues.
- [ ] Native image build succeeds.
- [ ] Native executable runs in CI or a verification environment.
- [ ] Tests exercise key reflection/resource/proxy paths.
- [ ] Tracing agent metadata is reviewed rather than copied blindly.

## 14. Self-Check Questions

**Question 1.** What question does `@ConditionalOnClass(name = "com.vendor.codec.Codec")` answer?

**Answer:** It checks whether class Codec is on the classpath so the auto-configuration is eligible to apply. It does not register reflection or resource hints.

**Question 2.** The SDK is on the classpath during AOT build, yet a method called via reflection does not appear in the native image. Which mechanism should you inspect?

**Answer:** Reachability metadata/runtime hints. The condition confirmed the dependency is present; the issue lies in dynamic access that static analysis cannot infer.

**Question 3.** If `acme.codec.enabled=false` during AOT build and then changed to true when running the native executable, is the codec bean created?

**Answer:** No. Conditions affecting the bean graph were evaluated at build time; runtime properties cannot add back an excluded bean.

**Question 4.** A resource is read using a name assembled from locale. What should be declared?

**Answer:** A resource hint with a sufficiently narrow pattern, such as `acme/templates/*`, or an equivalent resource registration via RuntimeHints.

**Question 5.** Does a passing RuntimeHintsPredicates test prove the native executable works?

**Answer:** No. It verifies the Spring registrar declared hints. AOT processing, native compilation, and tests running the executable on critical code paths are still required.

**Question 6.** When an optional SDK is not on the classpath, should hints still be registered for every class of that SDK?

**Answer:** That integration should not enter the build graph when the dependency is absent. Split registrars by integration or use classloader-aware registration; classpath conditions and hints should together reflect the actual dependency structure.

## 15. Takeaways

Distinguish two decision layers:

- **Classpath conditions** decide whether an auto-configuration participates. In a native build, Spring AOT evaluates conditions against the build-time classpath and Environment, then produces a fixed bean graph.
- **Reachability metadata/runtime hints** describe dynamic accesses that GraalVM cannot fully infer via static analysis, such as reflection, resource lookups, serialization, JDK proxies, or JNI.

A present dependency is not automatically permitted to be accessed via reflection. A hint does not add a dependency or create a bean. When designing a native-friendly starter, test both contracts separately: test conditions under varying classpaths and test hints with RuntimeHintsPredicates; then verify with a native build and native executable.

### Official Spring Boot, Spring Framework, and GraalVM Documentation

- [Spring Boot 3.3 — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot 3.3 — Advanced Native Image Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot 3.3 — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/3.3/how-to/aot.html)
- [Spring Framework 6.1 — Ahead-of-Time Optimizations and Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework 6.1 — RuntimeHintsRegistrar Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/aot/hint/RuntimeHintsRegistrar.html)
- [Spring Framework 6.1 — ImportRuntimeHints Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ImportRuntimeHints.html)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM — Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/guides/configure-with-tracing-agent/)
