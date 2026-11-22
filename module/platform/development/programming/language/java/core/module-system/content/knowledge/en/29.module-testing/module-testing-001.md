# Testing Code in a Named Test Module

When testing a Java application that uses JPMS, test code does not necessarily have to run on the classpath or be merged directly into the production module. You can create a separate **named test module** with its own name and **module-info.java**. The test module declares **requires** on the module under test while accessing only the packages exported by the production module. As a result, tests run under readability and strong encapsulation rules that are closer to a real modular application.

This organization is suitable when you want to verify public APIs, test integration across multiple modules, or prove that a library is genuinely usable from an independent consumer named module. It differs from the **--patch-module** technique, which injects test classes into the module under test so internal implementation can be tested in certain situations.

This article explains named test modules, how to compile and run them with the JDK, how to use the JUnit Platform, limitations when accessing internal packages, and how to choose a testing strategy based on your goal.

## 1. What Is a Named Test Module?

A named test module is an explicitly named module created specifically for test code. It typically has its own **module-info.java** file along with a set of test classes, but it is not packaged as part of the production artifact released to end users.

Example production module:

~~~java
module com.acme.calculator {
    exports com.acme.calculator.api;
}
~~~

Separate test module:

~~~java
module com.acme.calculator.tests {
    requires com.acme.calculator;
}
~~~

The name **com.acme.calculator.tests** is the name of the test module; it is distinct from **com.acme.calculator**. The **requires** directive allows the test module to read the production module. Because the production module only exports the **com.acme.calculator.api** package, the test module can use APIs in that package but cannot directly import classes belonging to non-exported packages.

This is a key difference from simply running tests on the classpath: test code behaves like a real modular consumer and must obey the module graph and module boundaries.

Key benefits:

- Detects missing dependencies in a consumer's module descriptor.
- Verifies that public API packages are exported properly.
- Tests module behavior when code is called from another module.
- Separates test frameworks and dependencies from the production module.
- Allows building integration test suites as independent named modules.
- Prevents accidentally relying on package-private members or non-exported implementation packages.

However, a named test module does not automatically replace internal unit tests, does not guarantee that the test framework is already resolved, and does not grant access to package-private members of another module.

## 2. Two Common Modular Testing Strategies

Before writing tests, choose the boundary that the test is meant to verify.

| Strategy | Module identity of tests | Strengths | Limitations |
|---|---|---|---|
| **Separate named test module** | A module distinct from the production module | Tests APIs, readability, exports, and integration like a real consumer | Cannot access non-exported packages or package-private members via requires alone |
| **Patch test classes into the production module** | Test classes are treated as part of the production module at runtime | Useful when testing implementation, package-private members, or keeping tests close to production structure | No longer an independent consumer module; requires --patch-module configuration and proper framework access |
| **Tests on the classpath** | Unnamed module of the class loader | Simple for legacy code and some test runners | May not fully verify the module boundaries of a named consumer |
| **Custom ModuleLayer for tests** | One or more named modules in a dedicated layer | Tests plugins, providers, and multi-layer behavior | More complex with respect to module finders, loaders, and service identity |

Not every project needs every strategy. For a library exposing APIs to many other modules, a separate named test module is very useful. For package-private logic that the project decides to test directly, patch-module may be more appropriate, though you should first evaluate whether testing through the public API is sufficient.

## 3. Source Structure for Production and Test Modules

A minimal example uses two source roots: **src** for the production module and **tests** for the test module.

~~~text
project/
├── src/
│   └── com.acme.calculator/
│       ├── module-info.java
│       └── com/acme/calculator/api/
│           └── Calculator.java
├── tests/
│   └── com.acme.calculator.tests/
│       ├── module-info.java
│       └── com/acme/calculator/tests/
│           └── CalculatorTestMain.java
├── mods/
└── test-mods/
~~~

Each root module directory has its own descriptor. The test package is named **com.acme.calculator.tests**, avoiding sharing the implementation package name of the production module.

Using two source roots separates dependencies:

- The production module does not need to depend on JUnit or test helpers.
- The test module can depend on the production module and test libraries.
- The production artifact only takes output from **mods/com.acme.calculator**.
- The test artifact and test runner use output from **test-mods/com.acme.calculator.tests**.
- Module APIs can be verified by actually running tests from another named module.

Although the module name often has a **.tests** suffix, the specific name is up to the project; it must be valid and must not collide with any module name used in the same configuration.

## 4. Complete Production Module Example

Production descriptor:

~~~java
// src/com.acme.calculator/module-info.java
module com.acme.calculator {
    exports com.acme.calculator.api;
}
~~~

API class:

~~~java
// src/com.acme.calculator/com/acme/calculator/api/Calculator.java
package com.acme.calculator.api;

public final class Calculator {
    public int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public int subtract(int left, int right) {
        return Math.subtractExact(left, right);
    }
}
~~~

In this example, **Calculator** is a public type in an exported package. Another test module can import the class and call its public methods after declaring **requires com.acme.calculator**.

Suppose the production module also has a **com.acme.calculator.internal** package for implementation algorithms; that package is not exported and is not part of the API contract. An independent consumer test should verify the results provided by the public API rather than importing internal implementation classes.

Using **Math.addExact** gives the example a clear error behavior to test: when addition overflows the int range, the method throws **ArithmeticException**. A good public API should define both normal behavior and observable error conditions for consumers.

## 5. Writing a Named Test Module Without a Framework

To see the JPMS mechanics clearly before adding JUnit, create a test module with a main method using manual assertions.

Test module descriptor:

~~~java
// tests/com.acme.calculator.tests/module-info.java
module com.acme.calculator.tests {
    requires com.acme.calculator;
}
~~~

Test class:

~~~java
// tests/com.acme.calculator.tests/com/acme/calculator/tests/CalculatorTestMain.java
package com.acme.calculator.tests;

import com.acme.calculator.api.Calculator;

public final class CalculatorTestMain {
    public static void main(String[] args) {
        Calculator calculator = new Calculator();

        if (calculator.add(2, 3) != 5) {
            throw new AssertionError("2 + 3 should equal 5");
        }

        if (calculator.subtract(8, 3) != 5) {
            throw new AssertionError("8 - 3 should equal 5");
        }

        boolean overflowDetected = false;
        try {
            calculator.add(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException expected) {
            overflowDetected = true;
        }

        if (!overflowDetected) {
            throw new AssertionError("Overflow should throw");
        }

        System.out.println("All modular tests passed");
    }
}
~~~

If a test fails, **AssertionError** causes the process to fail with an error. This example does not use the Java keyword **assert**, because **assert** can be disabled if the runtime does not enable **-ea**. In real testing, a test framework usually handles assertions, test discovery, and reporting instead of manual code.

The key point is that the test class is defined in the named module **com.acme.calculator.tests** and accesses the production API via **requires** plus **exports**.

## 6. Compiling and Running the Test Module with javac/java

Assuming you are in the project root directory with the structure from the example above, compile the production module first:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.calculator
~~~

Then compile the test module. The test needs to find the compiled production module on the module path:

~~~bash
javac --module-path mods \
      --module-source-path tests \
      -d test-mods \
      -m com.acme.calculator.tests
~~~

With this layout, the compiled output looks like:

~~~text
mods/
└── com.acme.calculator/
    ├── module-info.class
    └── com/acme/calculator/api/Calculator.class

test-mods/
└── com.acme.calculator.tests/
    ├── module-info.class
    └── com/acme/calculator/tests/CalculatorTestMain.class
~~~

Run the test as a modular program:

~~~bash
java --module-path "mods:test-mods" \
     -m com.acme.calculator.tests/com.acme.calculator.tests.CalculatorTestMain
~~~

On Linux/macOS, module path entries are separated by colons as in the example. On Windows, use a semicolon: **"mods;test-mods"**. These commands use Java 9+ and assume the source/output paths match the illustrated structure.

At runtime, the launcher must resolve **com.acme.calculator.tests** as the root. The **requires com.acme.calculator** directive brings the production module into the graph. If the production module is missing from the module path, the runtime may report **FindException**; that proves the test is governed by JPMS dependency checks.

## 7. Why Can't a Test Module Arbitrarily Use Internal Packages?

Suppose the production module has a class:

~~~java
package com.acme.calculator.internal;

public final class CalculationEngine {
    public int compute(int x, int y) {
        return x + y;
    }
}
~~~

The class is **public**, but the package **com.acme.calculator.internal** is not exported in the descriptor:

~~~java
module com.acme.calculator {
    exports com.acme.calculator.api;
}
~~~

If the test module imports the internal class:

~~~java
import com.acme.calculator.internal.CalculationEngine;
~~~

the compiler will reject access to the non-exported package, even though the test module has **requires com.acme.calculator**.

The two directives have different roles:

- **requires** establishes a readability relationship to a module.
- **exports** exposes a package so other modules can access public types in that package.

You should not add **exports com.acme.calculator.internal;** just to make tests compile, because doing so turns an implementation package into a public API for every module that reads the production module.

If a test truly needs to access an internal public class, you can consider **qualified exports** targeted to the test module in a controlled module configuration, or temporarily use **--add-exports** when compiling/running. However, both approaches create a test dependency on the implementation. If you need to test package-private members, qualified exports are not enough because Java access modifiers still apply.

## 8. When to Use --patch-module Instead of a Separate Named Test Module?

If the test's goal is to verify **package-private** classes, methods, or constructors of the production module, a separate test module does not have access via requires alone. A traditional modular Java testing approach is to **patch test classes into the production module**.

Conceptual example:

~~~bash
java --module-path mods \
     --patch-module com.acme.calculator=build/patch-tests \
     -m com.acme.calculator/com.acme.calculator.tests.InternalTestRunner
~~~

The example above only illustrates the syntax. For the test runner to execute successfully, it must also be compiled with the proper patch configuration, reside in the patched output, and have appropriate dependencies. You cannot simply pass an already compiled test module to **--patch-module** and assume its descriptor will be used as a new module.

When patching:

- Test classes are considered part of the patched module.
- Tests in the same package can access package-private members under the corresponding Java rules.
- Tests no longer simulate an independent named consumer module.
- The production module descriptor remains the descriptor governing module boundaries.
- The test framework may require additional readability and opens at runtime.

Therefore, a **separate named test module** and **patch-module** serve different purposes. Prefer testing the public API with a separate consumer module, and use patch tests only when there is a valid reason to test internal implementation.

## 9. Combining JUnit Jupiter with a Named Test Module

In real projects, JUnit 5/JUnit Jupiter is commonly used to structure tests. When running under JPMS, you need to distinguish the **test module**, the **JUnit API module**, the **module used to discover/execute tests**, and the **module performing reflection**.

Example descriptor for a test module using JUnit Jupiter:

~~~java
module com.acme.calculator.tests {
    requires com.acme.calculator;
    requires org.junit.jupiter.api;

    opens com.acme.calculator.tests to org.junit.platform.commons;
}
~~~

Explanation:

- **requires com.acme.calculator** allows tests to access the production module's public API.
- **requires org.junit.jupiter.api** allows the compiler to recognize the **@Test** annotation and JUnit Jupiter API assertions.
- **opens com.acme.calculator.tests to org.junit.platform.commons** allows the corresponding JUnit Platform reflection component to access test classes/methods when needed.

JUnit module names and reflection details may depend on the actual JUnit artifacts/versions in use; verify them with **jar --describe-module** on the resolved JARs. For some runners or extensions, you may need to open the package to the corresponding module performing reflection. Do not open the entire production module just because the test framework needs access to test methods.

Test class:

~~~java
package com.acme.calculator.tests;

import com.acme.calculator.api.Calculator;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {
    private final Calculator calculator = new Calculator();

    @Test
    void addsTwoNumbers() {
        assertEquals(5, calculator.add(2, 3));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(
            ArithmeticException.class,
            () -> calculator.add(Integer.MAX_VALUE, 1)
        );
    }
}
~~~

In JUnit Jupiter, test classes and test methods do not have to be public. However, in a named module, the test runner's use of reflection into the test package must satisfy the appropriate **opens** directive. The **@Test** annotation can compile successfully while test discovery/execution fails because the package is not open.

The JUnit Platform requires a suitable test engine (such as the Jupiter engine), launcher, or build tool runner integration. Simply adding the JUnit API to the module path is not enough to run tests automatically; the test engine and runtime configuration must work properly.

## 10. Why Can Test Discovery Fail Even When javac Succeeds?

Compiling and running tests are two distinct phases.

At compile time, a named test module needs:

- To find the production module on the module path.
- To find the module providing JUnit annotations/assertions.
- To have **requires** with the exact module names.
- To import only types exported to the test module.

When the JUnit Platform runs, it additionally needs:

- The test module resolved in the appropriate layer.
- A matching test engine discovered and present at runtime.
- The test package opened to the module that needs reflection.
- Test classes/methods properly discovered by the test framework.
- Modules supporting extensions/providers present in the runtime configuration.

For example, an **InaccessibleObjectException** usually relates to **opens** rather than a missing **requires**. A **FindException** for the production module usually relates to the module path or module name. Cases where JUnit finds zero tests may happen because the test module was not resolved, selectors are wrong, the engine is missing, or the test runner configuration does not see that module.

Do not fix every test discovery failure with **--add-opens ALL-UNNAMED**. Identify which named module the test runner/framework runs in and which package genuinely needs to be opened.

## 11. Maven/Gradle Configuration Notes

Build tools may compile production sources and test sources using different strategies. Merely enabling a test plugin or adding a **module-info.java** file in the test directory does not prove that tests are running as an independent named test module.

### Maven

In Maven, **maven-surefire-plugin** and **maven-failsafe-plugin** provide test execution mechanisms. Certain configurations may place tests on the module path or patch tests into the production module depending on the plugin version and project setup.

Example configuration snippet for a test runner using the module path:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <useModulePath>true</useModulePath>
  </configuration>
</plugin>
~~~

The example only illustrates the option; a project should pin plugin versions according to its policy and check the actual output. **useModulePath=true** does not by itself guarantee that test code is a separate named test module; you must verify the test descriptor, compilation output, and how Surefire executes tests in your specific configuration.

### Gradle

In Gradle, the **Test** task can use the JUnit Platform:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Another configuration can let Gradle infer the module path when a descriptor is present:

~~~groovy
java {
    modularity.inferModulePath = true
}
~~~

However, these snippets are not enough to define a separate named test module if source sets and module output paths are not organized accordingly. You need to inspect plugins, source roots, the test's module-info.java, and the JVM arguments actually generated by the task.

In both Maven and Gradle, check:

1. Are test sources compiled into a separate named module or patched into the production module?
2. Does the test runtime contain the full JUnit API, engine, and launcher?
3. Does the runner select the right test module and test classes?
4. Is the test package opened for framework reflection?
5. Do CI scripts use the same configuration as developer machines?

Do not infer behavior from the **test** task name alone. Use build logs and runtime module/class loader inspection to confirm how tests actually run.

## 12. Should a Test Module Export Its Test Packages?

Normally, a named test module **does not need to export** packages containing test classes. The test runner should not need to import test implementations like an ordinary Java API; it may need reflection, in which case restricted **opens** is the appropriate configuration.

Minimal descriptor example:

~~~java
module com.acme.calculator.tests {
    requires com.acme.calculator;
    requires org.junit.jupiter.api;
    opens com.acme.calculator.tests to org.junit.platform.commons;
}
~~~

Here, the **com.acme.calculator.tests** package is not exported as a public API. **opens** only allows deep reflection at runtime from the specified module.

If another test utility module needs to use a public helper class, you can extract that helper into a separate **test fixtures module** with explicit exports instead of exporting the entire test package. This keeps shared testing contracts stable and avoids cyclic dependencies between test modules.

In many systems, test code only needs to execute, not have other modules import its test classes. Therefore, start with empty exports and grant access only when there is a legitimate consumer.

## 13. Test Fixtures and Shared Dependencies

When multiple named test modules need fake data, builders, or mock implementations, consider creating a dedicated test support module, for example:

~~~java
module com.acme.test.fixtures {
    requires com.acme.calculator;
    exports com.acme.test.fixtures.api;
}
~~~

Test modules can read the fixtures:

~~~java
module com.acme.calculator.tests {
    requires com.acme.calculator;
    requires com.acme.test.fixtures;
}
~~~

Organizational principles:

- Test fixtures are dependencies for testing, not production runtime dependencies.
- Export only helper APIs that multiple test modules genuinely need.
- Do not pull mock/test framework libraries into the production module unless required by business functionality.
- If test fixtures need to read an API module, declare **requires** explicitly.
- Avoid helpers that mutate global state in ways that make tests order-dependent.
- Ensure fixtures do not repackage a duplicate copy of a service API, which would cause different class identities when testing multiple layers.

A named test module may need more dependencies than a production module, but the test module graph should remain readable and clearly scoped.

## 14. Testing a Service Provider with a Named Test Module

A common JPMS use case is **ServiceLoader**. A named test module can verify that a service provider module is actually resolved and discovered according to the service contract.

Suppose an API module contains the interface:

~~~java
module com.acme.codec.spi {
    exports com.acme.codec.spi;
}
~~~

Provider module:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.spi;

    provides com.acme.codec.spi.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Test module:

~~~java
module com.acme.codec.tests {
    requires com.acme.codec.spi;
    uses com.acme.codec.spi.Codec;
}
~~~

Test code:

~~~java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

boolean found = loader.stream().findAny().isPresent();
if (!found) {
    throw new AssertionError("No codec provider found");
}
~~~

Ensure the provider module is resolved into the appropriate layer. Merely having a provider JAR on the module path does not guarantee it is included in the resolved graph. In a test launcher, you can use **--add-modules com.acme.codec.json** to add the provider as a root or use an appropriate service binding mechanism.

With a custom ModuleLayer, you can use **ServiceLoader.load(layer, Codec.class)** to locate providers in the selected layer. The test module must share the same service API identity with the provider; do not package multiple copies of the API into plugin layers.

This test suite verifies the actual module configuration rather than just calling an implementation class constructor directly.

## 15. Testing Exports and Encapsulation

Named test modules are especially useful for verifying that module boundaries match the design.

### Positive Test

Write a consumer test module that imports a public type from an exported package:

~~~java
import com.acme.calculator.api.Calculator;
~~~

If the test compiles and runs successfully, this confirms at least that the access path used aligns with the module descriptor and runtime graph.

### Negative Test

Attempt to compile a separate source that tries to import a type from a non-exported package:

~~~java
import com.acme.calculator.internal.CalculationEngine;
~~~

The compiler should reject access when there is no qualified export or escape hatch. This kind of negative test usually must be structured as a controlled compilation test step that expects failure, rather than placed directly in the regular test source set where it would fail the whole build.

Distinguish between:

- Tests checking **exports**: importing and accessing public types across named modules.
- Tests checking **opens**: framework reflection from an appropriate module.
- Tests checking **readability**: needing **requires** to read a dependency module.
- Tests checking **package-private**: only code in the same package under appropriate module/class loader conditions can access it.

These tests can coexist, but you should not lump every failure together as "the module doesn't work".

## 16. Testing Reflection from Frameworks

With ORM or JSON serialization frameworks, a test might only pass when the production module opens the model package to the framework.

Example production descriptor:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
    opens com.acme.customer.model to com.acme.json;
}
~~~

A consumer named test module can call the public API and verify that the framework processes the model as expected. However, **com.acme.json** is the module that needs deep reflection; it is not necessary to open the model package to the test module just because the test invokes the functionality.

If a test attempts to use reflection directly from **com.acme.customer.tests**, opening the package for the test module must be considered separately, and that may differ from the production configuration. Avoid concluding that production supports the framework just because the test runner passes **--add-opens ...=ALL-UNNAMED** and tests pass.

When reflection errors occur:

1. Read the exception to identify the source module/package and target module.
2. Check whether the package-owning module has an appropriate **opens** directive.
3. Check what module name the framework/test runner has.
4. Use **--add-opens** only as a clearly scoped escape hatch when the descriptor cannot be modified.
5. Re-run the tests under the module configuration intended for production.

Named test modules expose discrepancies between declared permissions and permissions granted by VM options.

## 17. Avoiding Split Packages Between Production and Test Modules

A common mistake in source organization is placing a test class in the same package as a production class and then putting them into **two different named modules**.

Example:

~~~text
production module:
  com.acme.calculator.internal.Engine

test module:
  com.acme.calculator.internal.EngineTest
~~~

Both modules contain the **com.acme.calculator.internal** package. This is a **split package**, which can cause conflicts during resolution or layer definition, depending on exports/readability and how class loaders map modules.

Do not keep that layout and try to swap class loaders via trial-and-error. There are two clear choices:

- For a **separate named test module**, place test classes in a distinct package such as **com.acme.calculator.tests** and test only the API the module permits.
- For **tests needing the same package** to access package-private members, use the strategy of patching tests into the production module in a separate test build, instead of defining a second named test module with the same package.

Although multiple loaders can be used in some configurations, that is not a reason to design split packages as a default. Clear package ownership makes test modules easier to build, easier to debug, and less dependent on launcher details.

## 18. Checking Runtime Module Identity in Tests

When you suspect tests are running on the classpath instead of the module path, check with **Class.getModule()**:

~~~java
Module testModule = CalculatorTestMain.class.getModule();
Module productionModule = Calculator.class.getModule();

System.out.println("Test named: " + testModule.isNamed());
System.out.println("Test module: " + testModule.getName());
System.out.println("Production module: " + productionModule.getName());
System.out.println("Same module: " + (testModule == productionModule));
~~~

In the separate test module example, expect:

~~~text
Test named: true
Test module: com.acme.calculator.tests
Production module: com.acme.calculator
Same module: false
~~~

If testModule.isNamed() returns false, the test class is in an unnamed module in the observed runtime context. If the two module objects are identical, the test class may have been patched into the production module or defined under a different configuration than expected.

To investigate further, print:

~~~java
System.out.println(testModule.getLayer());
System.out.println(testModule.getClassLoader());
System.out.println(productionModule.getLayer());
System.out.println(productionModule.getClassLoader());
~~~

Module name is essential information, but class loader and layer also matter in architectures with multiple layers. Do not conclude that two classes belong to the same runtime module just because they share a similar package prefix.

## 19. Common Errors and Troubleshooting

| Symptom | Possible Cause | What to Check |
|---|---|---|
| **Module com.acme.calculator not found** | Test module path is missing the production module | Verify output/module path during compile and run |
| Compiler reports package is not visible | Production package is not exported to the test module | Check descriptor; test via public API or consider controlled qualified export |
| Test importing package-private fails | Test is in another module and lacks Java-level access | Switch to testing public API or organize patch-module |
| JUnit discovers 0 tests | Runner does not scan test module, engine missing, or wrong selector | Check JUnit Platform runtime, module roots, and test discovery |
| **InaccessibleObjectException** when running JUnit | Test package or production package is not opened to the corresponding reflection module | Verify opens to the right module performing reflection |
| Named test module treated as unnamed | Test classes were placed on the classpath | Check how the build tool places output onto the module path |
| **ResolutionException** due to package conflict | Split package or exports conflict in the graph | Separate test package or adjust module structure |
| ServiceLoader does not find provider | Provider module not resolved or incorrect uses/provides | Check descriptor, layer, and service binding |
| Tests pass in IDE but fail on CI | IDE and CI use different module paths, VM options, or engines | Compare the actual Java command and runtime image |
| Test code appears in release JAR | Build artifact mixes test output into production | Separate outputs and inspect release JAR contents |

These errors can occur at different stages: javac compilation, startup module resolution, layer definition, test discovery, or runtime invocation. Read the exact exception type and the named module/package before choosing a fix.

## 20. Implementation Workflow in a Project

A practical roadmap for a project transitioning to JPMS:

1. **Define the test goal:** public API, integration, module boundaries, or implementation internals.
2. **Create a production module with a clear descriptor:** expose API packages using exports.
3. **Create a separate test source root:** place module-info.java with a module name suffixed with tests.
4. **Declare test dependencies:** requires for the production module and necessary test API modules.
5. **Compile in order:** production output first, then the test module with production on the module path.
6. **Choose a runner:** a simple main test runner or JUnit Platform engine/launcher.
7. **Open the test package if needed:** qualified opens for reflection performed by the framework.
8. **Run as a named module:** verify Class.getModule().isNamed() and the actual module name.
9. **Test module boundaries:** import exported APIs and organize negative compile tests if needed.
10. **Separate integration tests:** you can create dedicated modules for end-to-end, service, or plugin layer tests.
11. **Control artifacts:** do not include test modules/classes/framework dependencies in production JARs unless explicitly intended.
12. **Synchronize CI:** run the same JDK/module-path/VM options on developer machines and pipelines.
13. **Document patch-module cases:** explain why tests need internal access and the conditions to remove this configuration.

If the project has not yet set up builds for a separate named test module, start with the framework-free example in sections 4–6. Once module names, requires, and runtime paths work, integrate JUnit to separate JPMS issues from framework discovery/reflection issues.

## 21. Practice Exercises

1. Create **com.acme.calculator** with one exported API package and one non-exported internal package.
2. Create **com.acme.calculator.tests** with **requires com.acme.calculator**.
3. Write a **CalculatorTestMain** that verifies results and overflow errors using AssertionError.
4. Compile the production module and then the test module using **--module-source-path** and **--module-path**.
5. Run the test module with **java -m**, verifying main method execution and proper exit status.
6. Remove the production module from the module path at runtime and observe the missing module message.
7. Try importing a public class from the non-exported package and observe the compiler error.
8. Try placing a test class in the same internal package as production inside a separate named module, and investigate the split-package issue.
9. Switch tests to JUnit Jupiter, declare **requires org.junit.jupiter.api**, and open the test package to the appropriate framework module.
10. Verify that the test engine/launcher resolves the test module properly and that test discovery finds the methods.
11. Create another test module that tests only the public API to compare with patch-module tests.
12. Add a provider module and write an integration test using ServiceLoader, confirming the provider is resolved.
13. Print the Module object, name, layer, and loader of both test and production classes.
14. Verify that the production JAR does not contain test classes or JUnit dependencies.
15. Run tests in CI with the exact launcher flags and target JDK.

## 22. Key Takeaways

- A **named test module** is a module with its own descriptor and name, usually declaring **requires** on the production module.
- It tests the production API under module boundaries similar to a real modular consumer.
- **requires** does not grant access to non-exported packages; package-private members remain governed by Java access rules.
- **--patch-module** is for test code that needs to be treated as part of the production module; it differs from a separate test module.
- Test packages should be namespaced separately from production packages to avoid split packages.
- A JUnit Jupiter test module may need **requires org.junit.jupiter.api** and qualified **opens** to the JUnit Platform reflection module.
- The test engine/launcher must be present and configured; merely compiling test annotations is not enough to run tests.
- Build tools may run tests on the classpath, module path, or via patch-module; verify the actual runtime setup.
- Service integration tests require proper provider resolution and shared service API identity.
- Module APIs should be tested through exported packages first; test internal implementation only with clear justification.
- Production artifacts should not contain test classes or test framework dependencies.
- When debugging, distinguish compiler errors, module resolution errors, layer instantiation errors, reflection errors, and test discovery errors.

**A named test module makes tests a real JPMS consumer.** Use it when you want to verify that the module descriptor and API boundaries work properly with external applications; combine it deliberately with patch-module when testing internal implementation is necessary.