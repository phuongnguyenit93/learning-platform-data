# Conditional Registration by Classpath and Keeping Metadata Properly Scoped

## 1. The Problem: Optional Dependencies Are Not Always Present

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring AOT prepares code and metadata at build time so GraalVM Native Image can analyze and build the executable. A Spring Boot application often integrates many optional libraries: storage SDKs, PDF generators, drivers, observability modules, or adapters for external services. Some environments include a given dependency, while others do not.

If runtime hints are registered for every library regardless of the classpath, the application can:

- reference nonexistent classes and fail immediately during AOT processing;
- package unnecessary reflection metadata, proxies, or resources;
- enlarge the native image and increase analysis time;
- obscure a feature's true dependencies, making configuration harder to maintain.

Conversely, if the dependency is present yet metadata required for reflection/resources is not registered, the JVM application may run normally while the native executable fails on a rarely exercised business branch.

The goal is to **enable an integration only when the dependency is genuinely present, register metadata only for operations that integration actually uses, and test both classpath states**.

## 2. Distinguishing Three Concepts

The three questions below are related but do not replace one another:

| Concept | Question answered | Common mechanism |
| --- | --- | --- |
| Classpath condition | Is the optional library present in the application build? | `@ConditionalOnClass`, `ClassUtils.isPresent` |
| Runtime hints / reachability metadata | Which dynamic accesses must Native Image preserve? | `RuntimeHintsRegistrar`, `RuntimeHints`, GraalVM metadata |
| Runtime feature condition | Is the feature enabled for this execution? | Properties, profiles, business conditions, and runtime config |

For example: the PDF SDK may be on the classpath while PDF export is disabled by a property. In that case:

- the classpath condition determines whether the PDF integration configuration can be loaded;
- runtime hints describe the constructors/resources/proxies that native image must retain for that integration;
- the runtime property determines whether the PDF endpoint or business logic is enabled in the current environment, provided the bean structure was prepared accordingly.

**A classpath condition is not a runtime feature flag.** With native images, the bean graph and classpath conditions are processed during AOT; adding a new JAR after the executable has been compiled will not make the binary load that class on its own.

## 3. Why Check the Classpath Before Registering Hints?

GraalVM Native Image uses a closed-world model. The tool analyzes the types and call paths visible at build time. A snippet of code that directly references an optional library class can trigger linkage or class-loading errors even when that feature is unused.

Unsafe example in a module with an optional dependency:

~~~java
import com.vendor.pdf.PdfEngine;

class PdfHints {
    void register(RuntimeHints hints) {
        hints.reflection().registerType(
            PdfEngine.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
        );
    }
}
~~~

If `com.vendor.pdf.PdfEngine` is absent from the classpath, the class containing that reference may fail to load. Merely wrapping the call in a Java `if` condition inside a method is not always enough: the JVM may need to resolve types when loading or verifying the class.

The solution is to place the integration inside a configuration guarded by a classpath condition while avoiding direct references to optional types in classes that are always loaded.

## 4. Using @ConditionalOnClass to Enable Integration Configuration

Spring Boot provides `@ConditionalOnClass` to apply configuration only when the specified class can be found on the classpath.

Example auto-configuration for a PDF SDK:

~~~java
package com.example.pdf;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.ImportRuntimeHints;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.pdf.PdfEngine")
@ImportRuntimeHints(PdfRuntimeHints.class)
public class PdfAutoConfiguration {
    // Declare PDF integration beans here.
}
~~~

Use the `name` attribute to check the class name as a string when the dependency is optional. That way, the configuration class does not need to import the SDK just to express the condition.

If this configuration is published as a library auto-configuration, register the class name in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The file contents are the fully qualified names of auto-configuration classes, one per line:

~~~text
com.example.pdf.PdfAutoConfiguration
~~~

Spring Boot evaluates the condition before applying the corresponding configuration. If the SDK is absent, the PDF configuration is skipped; beans and hints imported from that configuration should not be applied.

### 4.1. When to use a class literal instead of `name`?

If the dependency is mandatory and the class is always on the compile classpath, you can use:

~~~java
@ConditionalOnClass(PdfEngine.class)
~~~

For optional libraries, however, `name = "..."` prevents the configuration class from linking directly to external classes. In particular, do not place method signatures, fields, or superclasses referencing optional types inside an unconditionally loaded configuration. If a bean needs SDK types, keep that bean inside a conditional configuration or use a separate adapter.

### 4.2. Placing conditions on a separate configuration class

A dedicated conditional configuration class is easier to control when classpath dependencies are absent:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.pdf.PdfEngine")
class PdfIntegrationConfiguration {

    @Bean
    PdfRenderer pdfRenderer() {
        return new VendorPdfRenderer();
    }
}
~~~

Avoid putting a method that directly returns an optional SDK type in an unconditional configuration, because Spring or the JVM may have to introspect that type even when the bean is not instantiated.

## 5. Registering RuntimeHints Conditionally

`@ImportRuntimeHints` lets a Spring configuration import a `RuntimeHintsRegistrar`. Once the integration configuration passes its classpath condition, the registrar contributes metadata for the operations the SDK needs.

Example:

~~~java
package com.example.pdf;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ClassUtils;

final class PdfRuntimeHints implements RuntimeHintsRegistrar {

    private static final String OPTIONS_TYPE =
        "com.vendor.pdf.PdfOptions";

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        if (!ClassUtils.isPresent(OPTIONS_TYPE, classLoader)) {
            return;
        }

        Class<?> optionsType =
            ClassUtils.resolveClassName(OPTIONS_TYPE, classLoader);

        try {
            hints.reflection().registerConstructor(
                optionsType.getConstructor(),
                ExecutableMode.INVOKE
            );
        }
        catch (NoSuchMethodException ex) {
            throw new IllegalStateException(
                "The PDF SDK no longer exposes the expected public constructor",
                ex
            );
        }

        hints.resources().registerPattern("vendor/pdf/default-profile.json");
    }
}
~~~

In this example:

- The type name is kept as a string, so the registrar has no static import of the optional SDK.
- `ClassUtils.isPresent` checks for the class using the classloader supplied by AOT.
- Only when the class exists does the registrar resolve the type and register reflection hints.
- Only the no-argument public constructor is registered because the example assumes the SDK instantiates `PdfOptions` via that constructor.
- Only one specific resource is registered because the example assumes the SDK reads that exact profile file.

In real configuration, the auto-configuration condition already prevents the registrar from being imported when the SDK is absent. Checking `ClassUtils.isPresent` inside the registrar is an extra safeguard, useful when the registrar is reused or invoked directly in tests.

**Do not use a single broad classpath condition for an entire module if different integrations have different dependencies.** Split configurations/hints by capability so each part loads only when its corresponding dependency is present.

## 6. Scoping Reflection Metadata Properly

Reflection hints describe which members must be kept for dynamic access. Choose categories matching how the code invokes the SDK.

| Actual operation | Metadata to consider |
| --- | --- |
| Invoke public constructor via reflection | `MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS` |
| Invoke declared constructor (including non-public) | `MemberCategory.INVOKE_DECLARED_CONSTRUCTORS` |
| Invoke public method via reflection | `MemberCategory.INVOKE_PUBLIC_METHODS` |
| Invoke declared method via reflection | `MemberCategory.INVOKE_DECLARED_METHODS` |
| Introspect methods only, without invoking | `MemberCategory.INTROSPECT_PUBLIC_METHODS` or corresponding declared category |
| Access fields via reflection | `MemberCategory.PUBLIC_FIELDS` or `MemberCategory.DECLARED_FIELDS` |
| Type allocated via special mechanism | `MemberCategory.UNSAFE_ALLOCATED` when genuinely needed |

If the SDK only instantiates an object using a no-argument public constructor, you can register that constructor alone:

~~~java
void registerOptions(RuntimeHints hints, Class<?> optionsType)
        throws NoSuchMethodException {
    hints.reflection().registerConstructor(
        optionsType.getConstructor(),
        ExecutableMode.INVOKE
    );
}
~~~

If a specific method must be invoked via reflection, register that method alone with `registerMethod(...)` and `ExecutableMode.INVOKE`; if only introspection is needed, use `INTROSPECT` mode. Registering individual constructors/methods has a narrower scope than enabling a `MemberCategory` for all members of that kind. There is no need to register all declared methods, fields, and constructors if the application does not use them.

If the application only introspects annotations or method signatures, do not register invoke permissions unnecessarily. If a framework needs to invoke a private method, document that exact requirement and verify compatibility with native image.

### 6.1. Do not register a type merely because it is on the classpath

A dependency may contain hundreds of classes while the application calls only a small API. There is no reason to retain an entire package for reflection simply because the dependency is present. Trace the call path:

1. Which classes are actually instantiated via reflection?
2. Which constructors are invoked?
3. Which methods are invoked dynamically?
4. Which fields are accessed?
5. Are there types that only need introspection without invocation?

Register each required type/member. If a library already supplies compatible reachability metadata, prefer the library's metadata instead of creating a duplicate hint set in the application.

## 7. Resource Hints Also Need Conditions and Narrow Scope

An SDK may read schemas, templates, or profiles from the classpath. Native Image does not necessarily package every resource just because it exists in a JAR. Register only resources that are actually read.

Registering a single file:

~~~java
hints.resources().registerPattern("vendor/pdf/default-profile.json");
~~~

Registering a file group with a clear convention:

~~~java
hints.resources().registerPattern("vendor/pdf/templates/*.json");
~~~

Use broad patterns only when the application truly needs the entire file set. Avoid patterns like `**/*` or registering all dependency resources when only one specific schema is needed.

If a resource is only required when an optional SDK is present, register it inside a registrar imported by the `@ConditionalOnClass`-guarded auto-configuration. If the resource is used by the application independently of the SDK, register it in a separate configuration matching that feature.

A resource hint does not create a missing file. The file must exist on the input classpath before Native Image packages it. Therefore verify all of the following:

- whether the file exists in the dependency/application JAR;
- whether the resource path matches the classpath path;
- whether the hint is visible to the AOT/native build;
- whether the native executable can read the file at runtime.

## 8. Proxies and Serialization: Declare Only When Execution Paths Need Them

Reflection is not the only metadata type. Runtime hints can also describe JDK dynamic proxies and serialization.

### 8.1. JDK dynamic proxies

If the SDK creates a proxy for a specific set of interfaces, register those exact interfaces:

~~~java
hints.proxies().registerJdkProxy(
    PdfCallback.class,
    ProgressListener.class
);
~~~

This example assumes both interfaces are types present in the application or a mandatory dependency. If an interface belongs to an optional library, do not reference it directly from an unconditionally loaded class; place the registration inside a conditional configuration or resolve via classloader as shown for reflection.

The interface list and their order are part of the proxy definition. Do not register proxies for every interface in a package if only one combination is used.

### 8.2. Serialization

If a type is serialized/deserialized by a mechanism requiring native metadata, register that exact type:

~~~java
hints.serialization().registerType(PdfJobState.class);
~~~

Do not assume every JSON library requires identical serialization hints. Jackson binding, Java serialization, and custom serializers use different mechanisms. Rely on actual errors, library documentation, and native tests to decide which metadata is necessary.

## 9. When Are Classpath Conditions Evaluated in Spring AOT?

Spring AOT processes the `ApplicationContext` at build time. Therefore, `@ConditionalOnClass` is evaluated against the **build/AOT process** classpath. If the SDK is among build dependencies, the integration configuration can be processed and contribute hints. If the SDK is absent, the configuration is excluded.

This leads to the following rules:

- Optional dependencies must be on the build classpath when you want the integration included in the native executable.
- You cannot add a new dependency after the executable has been built and expect the binary to load its classes automatically.
- Runtime configuration can toggle a bean or feature if the required bean graph and logic were already prepared.
- If AOT ran without the dependency present, toggling a property at runtime cannot recreate code/hints for that integration.

Diagram:

~~~mermaid
flowchart TB
    A["Classpath during Spring AOT"] --> C{"Optional SDK present?"}
    C -->|No| X["Skip SDK auto-configuration and hints"]
    C -->|Yes| R["Load conditional auto-configuration"]
    R --> H["Registrar adds minimal metadata"]
    H --> N["Native Image analyzes classpath + hints"]
    N --> E["Executable with SDK integration"]
    X --> E2["Executable without SDK integration"]
    E --> T["Runtime: property determines how feature is used"]
~~~

Two executables can have different bean graph structures if built from different classpaths. This is a property of closed-world native compilation, not a Binder or runtime property bug.

## 10. When to Use RuntimeHintsRegistrar vs. JSON Metadata?

Spring provides the `RuntimeHintsRegistrar` Java API to register metadata during AOT processing. This is the natural choice when hints are tied to a Spring configuration or a specific integration.

JSON reachability metadata is appropriate when:

- a library wants to distribute metadata independently of any specific Spring application;
- metadata is already provided by the library or an official repository;
- metadata must be declared in GraalVM's schema without writing a Java registrar.

With JSON metadata supporting conditions, application can be limited by type reachability rather than applied unconditionally. Follow the exact schema and version for your GraalVM/Native Build Tools; do not copy metadata from another version without verifying.

The two mechanisms should not duplicate registrations for the same member set without reason. Duplication rarely makes an application more correct; it makes auditing metadata scope harder.

## 11. Testing Both With and Without the Dependency

An optional integration must have tests for **both classpath states**.

### 11.1. Testing configuration when the SDK is present

When the SDK is on the test classpath, verify that the auto-configuration creates the expected bean:

~~~java
class PdfAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(PdfAutoConfiguration.class)
            );

    @Test
    void createsPdfIntegrationWhenSdkIsPresent() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(PdfRenderer.class);
        });
    }
}
~~~

This test assumes the test runtime includes the SDK and required bean implementation. Adjust the runner to match actual dependencies.

### 11.2. Testing when the SDK is absent

Spring Boot test provides `FilteredClassLoader` to simulate an absent dependency:

~~~java
@Test
void skipsPdfIntegrationWhenSdkIsAbsent() {
    contextRunner
        .withClassLoader(new FilteredClassLoader("com.vendor.pdf"))
        .run(context -> {
            assertThat(context).doesNotHaveBean(PdfRenderer.class);
        });
}
~~~

In addition to not creating the bean, the test must verify that the `ApplicationContext` still starts without `NoClassDefFoundError` or `ClassNotFoundException`. If an unconditionally loaded class still references the optional SDK, this test catches it early.

### 11.3. Testing RuntimeHints contents

You can test the registrar directly with `RuntimeHintsPredicates`:

~~~java
RuntimeHints hints = new RuntimeHints();
new PdfRuntimeHints().registerHints(hints, getClass().getClassLoader());

assertThat(
    RuntimeHintsPredicates.reflection()
        .onType(PdfOptions.class)
        .withMemberCategory(MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS)
        .test(hints)
).isTrue();
~~~

This test snippet requires the SDK on the test classpath. You can also add a test with a classloader filtering out the dependency to confirm the registrar skips resolving the type when the class is absent, if the registrar is designed to support that case.

### 11.4. Native integration tests

Finally, build and run the native executable for the variant with the SDK. Exercise the exact flow using reflection/resources/proxies/serialization, because JVM `ApplicationContext` tests cannot prove Native Image retained sufficient metadata.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Importing optional class in an always-loaded config | Failure when dependency is absent | Use class name in condition and isolate config |
| Registrar always registers hints for every SDK | Redundant metadata, or nonexistent class errors | Guard registrar behind condition and check classloader |
| Using `allDeclaredMethods`/all constructors for every type | Retains far too many members | Choose the exact `MemberCategory` per operation |
| Registering all resources of a dependency | Large binary and hard to audit | Register specific files or narrow patterns |
| Assuming `@ConditionalOnClass` creates reflection hints automatically | Native build may miss dynamically invoked constructors/methods | Add separate hints for actual reflection behavior |
| Treating RuntimeHints as a feature flag | Confuses build metadata with runtime configuration | Separate classpath conditions, metadata, and feature properties |
| Testing only when the dependency is present | Class-loading errors when SDK is missing go undetected | Test both present and absent states |
| Testing only on JVM | Native reachability bugs are missed | Run native integration tests on dynamic-access flows |
| Adding dependency after binary is built | Binary lacks the new classes | Rebuild native with the dependency on the build classpath |

## 13. Hands-on Workflow

Suppose an application has an optional integration with a PDF SDK. The SDK is only used in certain deployments and needs only the public constructor of `PdfOptions` plus the resource `vendor/pdf/default-profile.json`.

**Step 1 — identify dependencies and integration points**

- Identify the Maven/Gradle artifact containing the SDK.
- Identify which classes exist only when the dependency is present.
- Find the exact constructors/methods/resources/proxies the code actually uses.
- Do not register metadata based on the library's entire API.

**Step 2 — isolate auto-configuration**

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.pdf.PdfEngine")
@ImportRuntimeHints(PdfRuntimeHints.class)
class PdfAutoConfiguration {
}
~~~

Ensure the class is published via auto-configuration imports or imported via the appropriate Spring Boot mechanism.

**Step 3 — register narrowly scoped hints**

~~~java
final class PdfRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        String typeName = "com.vendor.pdf.PdfOptions";
        if (!ClassUtils.isPresent(typeName, classLoader)) {
            return;
        }
        Class<?> type = ClassUtils.resolveClassName(typeName, classLoader);
        hints.reflection().registerType(
            type,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
        );
        hints.resources().registerPattern("vendor/pdf/default-profile.json");
    }
}
~~~

This example assumes the SDK only needs the public constructor and one exact resource. If the SDK actually invokes public methods via reflection or creates proxies, add the exact metadata for those operations.

**Step 4 — test both classpaths**

- Test with SDK present: integration bean appears and hints are registered.
- Test with SDK absent: `ApplicationContext` starts normally; SDK beans and hints are not applied.

**Step 5 — build natively and exercise business flow**

Build using Maven or Gradle per module configuration. Run the native executable with the SDK and invoke the PDF generation flow. Verify the resource is read, constructor reflection works, and unrelated endpoints still run.

**Step 6 — audit metadata**

Review the registrar and reachability metadata, removing unused members/resources. Compare build logs, native compilation time, and executable size when evaluating impact.

## 14. Checklist Before Completing Integration

- [ ] Optional dependency is checked via a classpath condition.
- [ ] Auto-configuration containing SDK references is isolated.
- [ ] Registrar does not directly import optional types in always-loaded code.
- [ ] Hints retain only constructors/methods/fields/proxies/resources genuinely needed.
- [ ] Resource hints point to files present on the input classpath.
- [ ] No duplication of metadata already provided by the library.
- [ ] Tested both when the dependency is present and when absent.
- [ ] Native tests exercise critical reflection/resource/proxy flows.
- [ ] Binary is rebuilt whenever classpath dependencies or metadata change.

**Remember:** conditions answer *whether the library is present to enable the integration*; runtime hints answer *which dynamic accesses Native Image must retain*; runtime configuration answers *how the feature is used in the running environment*. Conditional and minimal metadata registration keeps the native executable compatible while keeping the classpath and footprint properly scoped.
