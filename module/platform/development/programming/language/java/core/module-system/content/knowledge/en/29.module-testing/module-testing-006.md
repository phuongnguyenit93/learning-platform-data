# Testing ServiceLoader with Provider Modules

## 1. Test Objectives

In the Java Platform Module System (JPMS), **ServiceLoader** is the standard mechanism for consumers to discover implementations of a service type without directly depending on provider classes. A consumer needs only the service interface, while provider modules declare their implementations in their module descriptors.

When testing ServiceLoader in a modular application, you must verify more than object instantiation:

- The service interface resides in an API module with its package properly exported.
- The consumer or test module declares **uses** for the service type.
- Provider modules declare a valid **provides ... with ...** directive.
- Provider modules are resolved into the module graph or module layer under test.
- ServiceLoader uses the right layer/class loader to locate providers.
- Providers deliver behavior conforming to the contract.
- Tests do not assume provider ordering.
- Cases with no providers or misconfigured providers are handled intentionally.

The example in this article uses **Java 17 or later**, a TextFormatter service contract, two provider modules, and a named test module with a main method that verifies results itself. This avoids external test libraries so JPMS mechanics are clear before moving to JUnit.

## 2. Distinguishing Three Roles in Service Loading

The model has three module roles:

**API module** defines the service type referenced by both consumers and providers.

**Provider module** implements the service type and registers the provider in module-info.java.

**Consumer/test module** declares service consumption with uses and queries ServiceLoader.

Diagram:

~~~text
com.acme.format.tests
    | requires
    v
com.acme.format.api
    ^               ^
    | requires      | requires
    |               |
com.acme.format.upper    com.acme.format.reverse
    | provides                | provides
    +------ TextFormatter ----+
                ^
                |
       ServiceLoader discovery
~~~

The test module does not need to directly require com.acme.format.upper or com.acme.format.reverse. That independence is precisely what to verify: the consumer relies solely on the service contract, while providers can change independently.

Multiple implementations can provide the same service. Therefore, unit/integration tests should verify by identity or behavior rather than assuming the first provider is always a specific implementation.

## 3. Project Structure

Organize sources as follows:

~~~text
service-test/
├── src/
│   ├── com.acme.format.api/
│   │   ├── module-info.java
│   │   └── com/acme/format/api/TextFormatter.java
│   ├── com.acme.format.upper/
│   │   ├── module-info.java
│   │   └── com/acme/format/upper/UpperFormatter.java
│   └── com.acme.format.reverse/
│       ├── module-info.java
│       └── com/acme/format/reverse/ReverseFormatter.java
├── test-src/
│   └── com.acme.format.tests/
│       ├── module-info.java
│       └── com/acme/format/tests/
│           ├── ServiceDiscoveryTest.java
│           └── NoProviderTest.java
├── mods/
└── test-mods/
~~~

Each module directory contains module-info.java at its root. Classes belong to distinct packages, avoiding split packages across named modules.

Keep production code in src and test code in test-src to separate artifacts easily. The tests module compiles into test-mods, keeping test classes out of production JARs.

## 4. Defining the Service API

Create src/com.acme.format.api/module-info.java:

~~~java
module com.acme.format.api {
    exports com.acme.format.api;
}
~~~

Create the service type:

~~~java
package com.acme.format.api;

public interface TextFormatter {
    String name();

    String format(String text);
}
~~~

The contract has two methods:

- name() returns a stable identifier for the provider.
- format(text) transforms a string according to the provider's rules.

This identifier supports selecting and verifying providers. In real systems, the API may declare additional metadata, configuration, and error-handling rules, while keeping the contract small and independent of implementations.

Package com.acme.format.api is exported because both providers and consumers need to reference TextFormatter. If the API package were not exported, providers in other modules could not implement the type in ordinary Java code.

## 5. Writing the First Provider Module

Create src/com.acme.format.upper/module-info.java:

~~~java
module com.acme.format.upper {
    requires com.acme.format.api;

    provides com.acme.format.api.TextFormatter
        with com.acme.format.upper.UpperFormatter;
}
~~~

Implementation:

~~~java
package com.acme.format.upper;

import com.acme.format.api.TextFormatter;
import java.util.Locale;

public final class UpperFormatter implements TextFormatter {

    public UpperFormatter() {
    }

    @Override
    public String name() {
        return "upper";
    }

    @Override
    public String format(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

The provider module needs requires on the API module because the implementation uses TextFormatter. The provides directive registers the implementation for the service.

Package com.acme.format.upper **does not have to be exported** to the test module. The test only needs the interface; ServiceLoader and the module system handle provider instantiation via service metadata.

The provider class in this example is public, has a public no-arg constructor, and implements TextFormatter directly. That is the standard way to register a provider class. Named modules can also use a provider method in factory scenarios, though it is not needed for this example.

## 6. Writing the Second Provider Module

Descriptor for src/com.acme.format.reverse/module-info.java:

~~~java
module com.acme.format.reverse {
    requires com.acme.format.api;

    provides com.acme.format.api.TextFormatter
        with com.acme.format.reverse.ReverseFormatter;
}
~~~

Implementation:

~~~java
package com.acme.format.reverse;

import com.acme.format.api.TextFormatter;

public final class ReverseFormatter implements TextFormatter {

    public ReverseFormatter() {
    }

    @Override
    public String name() {
        return "reverse";
    }

    @Override
    public String format(String text) {
        return new StringBuilder(text).reverse().toString();
    }
}
~~~

Now two named modules both provide TextFormatter without sharing any package. Each provider only requires the API module and has no knowledge of or dependency on the other provider.

A single service type can have many providers. Adding a third provider only requires a new module registering provides properly, provided that module is included in the active layer.

## 7. Creating a Named Test Module with uses

Descriptor for the test module at test-src/com.acme.format.tests/module-info.java:

~~~java
module com.acme.format.tests {
    requires com.acme.format.api;
    uses com.acme.format.api.TextFormatter;
}
~~~

The two directives perform separate jobs:

- requires com.acme.format.api lets the test module read the service contract.
- uses com.acme.format.api.TextFormatter declares the test module as a service consumer.

Having requires does not replace uses. In a named module, when code calls ServiceLoader for a service type, the caller module must declare uses for that service per API rules.

Notably, the descriptor does not contain:

~~~text
requires com.acme.format.upper;
requires com.acme.format.reverse;
~~~

The test verifies discovery through service metadata, not direct linkage to implementations. Adding requires for each provider just to test would undermine the flexibility of the SPI.

## 8. Testing Provider Discovery and Behavior

Create ServiceDiscoveryTest.java in package com.acme.format.tests:

~~~java
package com.acme.format.tests;

import com.acme.format.api.TextFormatter;
import java.util.HashMap;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.Set;

public final class ServiceDiscoveryTest {

    public static void main(String[] args) {
        ServiceLoader<TextFormatter> loader =
                ServiceLoader.load(
                        ModuleLayer.boot(),
                        TextFormatter.class
                );

        Map<String, TextFormatter> providers = new HashMap<>();

        for (TextFormatter service : loader) {
            TextFormatter old =
                    providers.putIfAbsent(service.name(), service);

            if (old != null) {
                throw new AssertionError(
                        "Duplicate provider name: " + service.name()
                );
            }

            System.out.println(
                    service.name() + " from module "
                    + service.getClass().getModule().getName()
            );
        }

        Set<String> expected = Set.of("upper", "reverse");

        if (!providers.keySet().equals(expected)) {
            throw new AssertionError(
                    "Expected providers " + expected
                    + ", actual " + providers.keySet()
            );
        }

        assertEquals(
                "HELLO",
                providers.get("upper").format("hello")
        );

        assertEquals(
                "cba",
                providers.get("reverse").format("abc")
        );

        System.out.println("ServiceLoader integration test passed");
    }

    private static void assertEquals(
            String expected, String actual
    ) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected " + expected + ", actual " + actual
            );
        }
    }
}
~~~

The test performs three checks:

1. **Discovery**: exactly two providers matching the expected names.
2. **Uniqueness**: no two providers share the same logical name.
3. **Contract behavior**: upper and reverse perform the expected transformations.

Do not call iterator().next() assuming the first provider is upper, because provider order is not a business priority contract. Using Set and Map keeps the test independent of iteration order.

In this example, ServiceLoader.load(ModuleLayer.boot(), service) searches providers only in the boot layer and relevant ancestor layers per API rules. For custom plugin layers, pass the plugin layer instead of defaulting to the boot layer.

## 9. Compiling Production Modules

From the service-test directory, compile the three production modules:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.format.api,com.acme.format.upper,com.acme.format.reverse
~~~

Output:

~~~text
mods/
├── com.acme.format.api/
│   ├── module-info.class
│   └── com/acme/format/api/TextFormatter.class
├── com.acme.format.upper/
│   ├── module-info.class
│   └── com/acme/format/upper/UpperFormatter.class
└── com.acme.format.reverse/
    ├── module-info.class
    └── com/acme/format/reverse/ReverseFormatter.class
~~~

These are three exploded modules. Each has its own descriptor and package. Placing mods on the module path allows the Java launcher to locate them by module name.

If using modular JARs instead of exploded modules, verify each JAR has module-info.class at its root. Inspect provides declarations with jar --describe-module.

## 10. Compiling the Named Test Module

Compile the test module against the API module already in mods:

~~~bash
javac --module-source-path test-src \
      --module-path mods \
      -d test-mods \
      -m com.acme.format.tests
~~~

Here:

- --module-source-path test-src locates module-info.java and test sources.
- --module-path mods provides the service API and compiled production modules.
- -d test-mods keeps test output separate.
- -m com.acme.format.tests selects the exact named test module.

Because the test module imports only TextFormatter, it does not need to import UpperFormatter or ReverseFormatter; providers are discovered at runtime.

The test module also gets module-info.class at the root of test-mods/com.acme.format.tests.

## 11. Running Tests with Provider Modules Resolved

A module merely sitting on the module path is not guaranteed to be resolved as a root/module in the boot layer in every configuration. To make test conditions explicit, add provider modules to the root set explicitly:

~~~bash
java --module-path mods:test-mods \
     --add-modules com.acme.format.upper,com.acme.format.reverse \
     --module com.acme.format.tests/com.acme.format.tests.ServiceDiscoveryTest
~~~

On Windows:

~~~powershell
java --module-path "mods;test-mods" --add-modules com.acme.format.upper,com.acme.format.reverse --module com.acme.format.tests/com.acme.format.tests.ServiceDiscoveryTest
~~~

Thanks to --add-modules, both upper and reverse are resolved into the boot layer. Because the test calls ServiceLoader.load(ModuleLayer.boot(), TextFormatter.class), it discovers the providers from those modules.

Sample output:

~~~text
upper from module com.acme.format.upper
reverse from module com.acme.format.reverse
ServiceLoader integration test passed
~~~

The order of the two provider lines may vary. What matters is that the Set of provider names and their behavior are verified.

Clearly distinguish **module path** from **resolved modules**: a JAR appearing on the module path does not guarantee every module in the directory joins the module graph. In integration tests, pin module roots/layer configuration so results are reproducible.

## 12. Testing When No Providers Are Present

You should verify that the consumer handles the case with zero implementations.

Create NoProviderTest.java:

~~~java
package com.acme.format.tests;

import com.acme.format.api.TextFormatter;
import java.util.ServiceLoader;

public final class NoProviderTest {

    public static void main(String[] args) {
        ServiceLoader<TextFormatter> loader =
                ServiceLoader.load(
                        ModuleLayer.boot(),
                        TextFormatter.class
                );

        if (loader.iterator().hasNext()) {
            throw new AssertionError(
                    "Expected no provider in isolated test layer"
            );
        }

        System.out.println("No-provider test passed");
    }
}
~~~

This test is only valid when the layer under test **contains no provider modules**. Therefore, prepare a module path fixture without upper/reverse. For example on Linux/macOS, after compiling:

~~~bash
mkdir -p only-api-mods
cp -R mods/com.acme.format.api only-api-mods/
~~~

Run with only-api-mods and test-mods, omitting the full mods directory from the module path:

~~~bash
java --module-path only-api-mods:test-mods \
     --module com.acme.format.tests/com.acme.format.tests.NoProviderTest
~~~

Expected result:

~~~text
No-provider test passed
~~~

On Windows, create the corresponding directory and copy the exploded com.acme.format.api module via File Explorer or PowerShell, then separate module path entries with semicolons.

Do not run the no-provider test on a module path containing provider modules and treat an empty result as guaranteed. Module resolution and service binding may pull providers into the boot layer. A negative fixture must **genuinely isolate** provider artifacts.

## 13. Testing a Single Provider

In addition to two-provider and zero-provider tests, you can verify a single-implementation configuration.

Prepare a module path fixture containing only the API module and upper module, then run a test tailored for the single-provider scenario. For this test, the expected Set is:

~~~java
Set<String> expected = Set.of("upper");
~~~

Goals:

- Confirm the consumer does not need to know about the reverse provider.
- Confirm upper's module descriptor registers the service properly.
- Confirm upper's behavior is stable.
- Catch dependencies that accidentally pull in unwanted providers.

In multi-profile build environments such as test, staging, and production, testing the same service contract across different provider sets catches distribution configuration errors before deployment.

## 14. Provider Methods and How to Test Them

In a named module, a provider can be created from a **provider class** or from a static method named provider on the class named in the provides clause.

Example module descriptor:

~~~java
module com.acme.format.special {
    requires com.acme.format.api;

    provides com.acme.format.api.TextFormatter
        with com.acme.format.special.FormatterFactory;
}
~~~

Provider method:

~~~java
package com.acme.format.special;

import com.acme.format.api.TextFormatter;

public final class FormatterFactory {

    private FormatterFactory() {
    }

    public static TextFormatter provider() {
        return new ConfiguredFormatter();
    }
}
~~~

Here ConfiguredFormatter is a suitable TextFormatter implementation inside the provider module. When testing, ensure:

- The module is resolved into the layer under test.
- The provides clause names the exact service type.
- The provider method has a valid signature and returns an appropriate instance.
- Instantiating the provider does not throw an exception.
- Instance behavior satisfies the contract.

ServiceLoader.Provider.type() may represent the type per the provider mechanism, so if you need to check the real implementation, inspect the instance returned by Provider.get() rather than assuming the class after with is always the object's runtime class.

## 15. Inspecting Descriptors and provides Metadata

If ServiceLoader returns an empty result, a quick diagnostic step is inspecting the module descriptor:

~~~bash
javap -v -p mods/com.acme.format.upper/module-info.class
~~~

For modular JARs:

~~~bash
jar --describe-module --file dist/com.acme.format.upper.jar
~~~

Details to verify:

- Is the module name exact (com.acme.format.upper)?
- Does it have requires com.acme.format.api?
- Does it have provides com.acme.format.api.TextFormatter with ...?
- Does the provider class exist with the exact package name?

Inspect the test module descriptor:

~~~bash
javap -v -p test-mods/com.acme.format.tests/module-info.class
~~~

It must contain uses com.acme.format.api.TextFormatter. If the test module omits uses, calling ServiceLoader from a named module can raise ServiceConfigurationError.

Do not confuse **being able to import the service contract** with **a service being registered by a provider**: requires/exports grants type access; uses/provides describes the service relationship.

## 16. ServiceLoader and Service Binding

There are two separate steps:

1. **Module resolution/service binding** decides which provider modules enter the module configuration.
2. **ServiceLoader** queries the layer/class loader and instantiates providers when code iterates the service.

When creating custom module layers, Configuration.resolve(...) resolves roots and requires, whereas Configuration.resolveAndBind(...) can additionally bind modules providing services per uses/provides.

In integration tests using dynamic module layers, construct fixtures explicitly and inspect configuration modules before calling ServiceLoader.load(layer, ServiceType.class).

Example querying providers in a supplied layer:

~~~java
public static void verifyLayer(ModuleLayer layer) {
    ServiceLoader<TextFormatter> services =
            ServiceLoader.load(layer, TextFormatter.class);

    for (TextFormatter service : services) {
        System.out.println(
                service.name() + " -> "
                + service.getClass().getModule().getName()
        );
    }
}
~~~

The method above sits inside a class importing TextFormatter, ServiceLoader, and ModuleLayer. If the caller is a named module, the caller's descriptor must declare uses for the service type.

**Service binding does not mean providers are instantiated.** Resolution prepares the module graph; provider instances are created only when ServiceLoader actually requests them.

## 17. Testing Provider Load Failures

A misconfigured provider can throw **ServiceConfigurationError** when ServiceLoader discovers or instantiates it.

Negative cases to test:

- Provider module specifies a non-existent class after with.
- Implementation does not implement the service contract.
- Constructor or provider method throws an exception.
- Provider method returns null or an incompatible type.
- Runtime dependency of the provider is missing.
- Service type is loaded as two distinct Class objects across class loaders.

In named modules, many invalid provider declarations are caught at compile time when compiling the descriptor/provider. To create runtime failure fixtures, control packaging or runtime conditions rather than placing uncompilable sources into normal tests.

Consumers can handle errors according to policy:

~~~java
try {
    for (TextFormatter formatter :
            ServiceLoader.load(TextFormatter.class)) {
        System.out.println(formatter.name());
    }
} catch (java.util.ServiceConfigurationError error) {
    throw new IllegalStateException(
            "Service provider configuration failed", error
    );
}
~~~

Provider errors should not be silently swallowed if a feature requires a mandatory service. Logging the module, provider name, and cause aids diagnosis.

## 18. Do Not Test Providers by Order

A common mistake:

~~~java
TextFormatter first = ServiceLoader
        .load(TextFormatter.class)
        .iterator()
        .next();

assert "upper".equals(first.name());
~~~

This snippet depends on provider ordering and assumes at least one provider exists. Ordering can change when the module path, packaging, or layers change.

A better approach:

- Collect providers by a stable key.
- Verify the discovered set of keys.
- Detect duplicate keys when the contract requires uniqueness.
- Verify each behavior through the interface.
- If business logic requires priority ordering, define an explicit policy rather than relying on ServiceLoader iteration order.

For example, use Map<String, TextFormatter> or Set<String>. For mandatory providers, raise a clear error when the Set is empty instead of calling next() blindly.

## 19. Testing with JUnit and Framework Runners

When moving to JUnit 5, assertions from the examples above can be written using @Test and Assertions.

Example:

~~~java
@Test
void discoversExpectedProviders() {
    Set<String> names = new HashSet<>();

    ServiceLoader.load(
            ModuleLayer.boot(),
            TextFormatter.class
    ).forEach(provider -> names.add(provider.name()));

    assertEquals(Set.of("upper", "reverse"), names);
}
~~~

This is the test method body; you need to import Test, HashSet, Set, ServiceLoader, TextFormatter, and assertEquals. The JUnit API module name is typically org.junit.jupiter.api, while engine/launcher and module path configuration depend on the JUnit version and build tool.

For a named test module, the descriptor needs requires for the test framework modules imported by code, and may need qualified opens if the runner performs deep reflection. If tests are patched into the production module, --add-reads/--add-opens may be needed in dedicated test settings.

Do not add JUnit dependencies to production module-info.java just to run tests if they are not real runtime dependencies of the application.

## 20. TCCL and ServiceLoader.load(service)

Distinguish two invocation forms:

~~~java
ServiceLoader<TextFormatter> viaContextLoader =
        ServiceLoader.load(TextFormatter.class);

ServiceLoader<TextFormatter> viaLayer =
        ServiceLoader.load(
                ModuleLayer.boot(),
                TextFormatter.class
        );
~~~

The load(service) overload uses the thread context class loader (TCCL) and its corresponding provider discovery rules. In container or plugin applications, TCCL can differ across threads.

The overload taking ModuleLayer gives tests explicit control over the queried layer. Still, results depend on which provider modules were resolved into that layer.

When testing ServiceLoader in thread pools:

- Do not assume a worker thread's TCCL matches the test-creating thread unless the framework guarantees it.
- If changing TCCL, restore the previous value in a finally block.
- Do not share a single ServiceLoader instance across threads without proper synchronization.
- Use an explicit layer when the test aims to verify the service registry of a specific module layer.

## 21. Common Errors

**Provider not found even though JAR is on the module path**

The provider module may not have been resolved into the queried layer. Use --add-modules for deterministic fixtures, or inspect service binding/module layer creation in your application.

**Consumer fails to declare uses**

A named module calls ServiceLoader without declaring uses for the service type. Add uses to the consumer/test module's module-info.java.

**Provider fails to declare provides**

Having an implementation class is not enough. A named provider module must declare a valid provides ... with ....

**Implementation package is not exported**

This is usually **not an error**. ServiceLoader does not require exporting the provider's implementation package just to instantiate the service. Export only the API package containing the service contract when consumers/providers need to import it.

**Provider sees a different copy of the service interface**

If two class loaders separately define a service interface with the same name, the provider may not be recognized as a valid subtype. Share the same API module/class loader to preserve type identity.

**Test checks only that at least one provider exists**

Such a test can pass even when a critical provider is missing. Check the expected set of providers when the test fixture specifies the exact module set.

**No-provider test still sees implementations**

Provider modules might be entering the boot layer via root configuration or service binding. Build a module path fixture containing only the API and tests, excluding provider artifacts.

**ServiceConfigurationError**

Check the descriptor, provider factory/constructor, runtime dependencies, and cause. One broken provider can abort iteration before the test collects all implementations.

**Tests behave differently on classpath vs. module path**

Classpath META-INF/services and named-module provides are two different registration mechanisms. Verify how each dependency is packaged and which loader/layer ServiceLoader actually uses.

## 22. Practical Workflow

1. Create the service API in a dedicated named module and export the package containing the service type.
2. Create at least one provider module with requires on the API and provides ... with ....
3. Create a named test module with requires on the API and uses for the service type.
4. Compile production modules with javac --module-source-path.
5. Compile the test module with --module-path pointing to production artifacts.
6. Run tests with a module path containing the exact fixture; use --add-modules to place desired provider modules into the boot layer for determinism.
7. Query ServiceLoader.load(ModuleLayer.boot(), ServiceType.class) or load(layer, ...) for custom layers.
8. Verify provider identity, module name, and behavior without relying on iteration order.
9. Prepare a negative fixture with no providers and verify an empty result.
10. When tests fail, inspect module-info.class, module resolution, and the module path before modifying implementation code.

## 23. Takeaways

- ServiceLoader discovers only registered providers present within the queried layer/class loader scope.
- Consumer named modules declare uses; provider named modules declare provides ... with ....
- Providers do not need to export implementation packages just for ServiceLoader instantiation.
- A test named module can require only the service API without requiring provider modules.
- An artifact existing on the module path does not mean that module is necessarily in the resolved module graph.
- --add-modules is useful for pinning provider sets in integration tests.
- Tests should verify the provider set and behavior rather than assuming ServiceLoader ordering.
- Zero-provider tests need a module path/layer environment genuinely free of providers.
- ServiceConfigurationError indicates a discovery/initialization failure, not necessarily a business method bug.
- For custom plugin layers, use ServiceLoader.load(layer, service) to inspect the right layer.
- TCCL affects load(service); control TCCL when tests run across multiple threads.
- Keep test dependencies and broad reflective permissions out of production descriptors unless necessary.

**Conclusion:** Testing ServiceLoader in JPMS must verify **uses/provides** metadata, module resolution, provider discovery scope, and implementation behavior. An independent test module using the service API, deterministic provider fixtures, and order-independent assertions catches packaging and configuration errors before the application reaches production.