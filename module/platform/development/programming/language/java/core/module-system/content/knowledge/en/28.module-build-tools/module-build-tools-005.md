# Test module path and test module descriptor

## 1. Testing in the Java Platform Module System

In traditional Java applications, production classes and test classes are typically combined onto the same classpath. The test framework discovers test classes, loads them, and invokes methods without needing to know about module descriptors.

With the **Java Platform Module System (JPMS)**, once production code becomes a named module, access boundaries are governed by:

- Module names and **requires** dependencies.
- Module **readability** relationships.
- Which packages are **exports** for other modules to access public APIs.
- Which packages are **opens** for frameworks using deep reflection.
- The class loader and module layer where classes are defined.

Consequently, running tests is no longer just putting JAR files onto a single path list. You must determine the **test module path**, how test code is organized, and whether tests have their own **module-info.java** descriptor or are merged into the production module with **--patch-module**.

There are two key models:

1. **Test as a standalone named module**: has its own descriptor, accesses only the APIs exported by the production module, and suits public contract and integration testing.
2. **Test patched into the production module**: has no separate named test module at runtime; test code is treated as part of the production module, suiting tests for package-private code or cases where tests must reside in the same package as the implementation.

The two models address different needs. You should not use options that open every internal package when a test only needs public APIs.

## 2. How does the module path differ from the classpath?

**Classpath** holds classes/JARs loaded into the unnamed module of the corresponding class loader. Code in the unnamed module typically has no module-info.java file.

**Module path** holds named modules that can be resolved. An entry can be a modular JAR, an exploded module, or a JAR treated as an automatic module depending on artifact contents.

For example:

~~~bash
java --class-path "build/classes:lib/*" com.acme.app.Main
~~~

and:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

do not share the same access rules. With a named module, a class residing in a JAR present on the module path **does not guarantee** that a consumer is allowed to import it. The consumer also needs to read the module containing the class, and the package must be appropriately exported.

In testing, a test suite may have dependencies separate from production, such as an assertion library or test engine. Placing all test dependencies on the classpath and expecting them to automatically see every package of a named module often leads to readability, encapsulation, or reflection errors.

## 3. What is the test module path?

The **test module path** is the set of named modules supplied to the compiler or runtime when compiling/running tests. There is no Java option named --test-module-path; in practice, **--module-path** (or **-p**) is still used with the paths containing the modules needed for the test.

Typically, the following artifact groups are needed:

- **Production modules**: application modules and library modules under test.
- **Test modules**: if tests are compiled as a separate named module.
- **Test framework modules**: JUnit or runner modules if the tests use a framework.
- **Dependency modules**: modules that production and tests need at compile time/runtime.

There can be two output directories:

~~~text
project/
├── src/          # production module sources
├── test-src/     # test module sources
├── mods/         # production exploded modules
└── test-mods/    # test exploded modules
~~~

Example command to run a standalone test module:

~~~bash
java --module-path mods:test-mods \
     --module com.acme.math.tests/com.acme.math.tests.TestMain
~~~

On Linux/macOS, multiple path entries are separated by a colon. On Windows, use a semicolon and quote the path string when needed:

~~~powershell
java --module-path "mods;test-mods" --module com.acme.math.tests/com.acme.math.tests.TestMain
~~~

When building with Maven or Gradle, the test plugin can construct the module path and launcher options for you. However, you need to understand the actual module path to diagnose test failures.

## 4. Example production module as the test target

Create a project with a module com.acme.math:

~~~text
src/
└── com.acme.math/
    ├── module-info.java
    └── com/
        └── acme/
            └── math/
                ├── api/
                │   └── Calculator.java
                └── internal/
                    └── Accumulator.java
~~~

Module descriptor:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

Public class:

~~~java
package com.acme.math.api;

public final class Calculator {
    private Calculator() {
    }

    public static int sum(int left, int right) {
        return left + right;
    }
}
~~~

Internal class:

~~~java
package com.acme.math.internal;

final class Accumulator {
    private int total;

    void add(int value) {
        total += value;
    }

    int value() {
        return total;
    }
}
~~~

The module exports only com.acme.math.api. Package com.acme.math.internal is not exported; class Accumulator is also package-private.

Compile the production module:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.math
~~~

Output:

~~~text
mods/
└── com.acme.math/
    ├── module-info.class
    └── com/acme/math/
        ├── api/Calculator.class
        └── internal/Accumulator.class
~~~

This is an exploded named module that can be used directly on the test module path.

## 5. Model A: a test module with its own descriptor

To test the **public API** just like a real consumer, place test code in a standalone named module.

Source tree:

~~~text
test-src/
└── com.acme.math.tests/
    ├── module-info.java
    └── com/
        └── acme/
            └── math/
                └── tests/
                    └── TestMain.java
~~~

Test module descriptor:

~~~java
module com.acme.math.tests {
    requires com.acme.math;
}
~~~

Test class without external frameworks:

~~~java
package com.acme.math.tests;

import com.acme.math.api.Calculator;

public class TestMain {
    public static void main(String[] args) {
        assertEquals(5, Calculator.sum(2, 3));
        assertEquals(0, Calculator.sum(-2, 2));
        System.out.println("All tests passed");
    }

    private static void assertEquals(int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "Expected " + expected + ", got " + actual
            );
        }
    }
}
~~~

The test module imports only Calculator from the production module's exported package. This is an important test of the API contract: tests are not allowed to depend on implementation packages that library users cannot see either.

## 6. Compiling a standalone test module

After compiling production into mods, compile the test:

~~~bash
javac --module-source-path test-src \
      --module-path mods \
      -d test-mods \
      -m com.acme.math.tests
~~~

Explanation:

- --module-source-path test-src: where test module sources reside, including module-info.java.
- --module-path mods: where javac locates compiled production named modules.
- -d test-mods: output location for test modules.
- -m com.acme.math.tests: name of the test module being compiled.

Output:

~~~text
test-mods/
└── com.acme.math.tests/
    ├── module-info.class
    └── com/acme/math/tests/TestMain.class
~~~

Run:

~~~bash
java --module-path mods:test-mods \
     -m com.acme.math.tests/com.acme.math.tests.TestMain
~~~

Expected output:

~~~text
All tests passed
~~~

In this approach, the test module is never merged into the production module. Both modules have separate names, separate descriptors, and separate API boundaries.

## 7. A test module cannot bypass exports

Suppose in the standalone test module, we write:

~~~java
package com.acme.math.tests;

import com.acme.math.internal.Accumulator;
~~~

This code is invalid in the current example because:

1. com.acme.math.internal is not exported from com.acme.math.
2. Accumulator is a package-private class and cannot be accessed from another package even if the package were exported.

Adding requires com.acme.math to the test module descriptor only establishes readability; it does not force the production module to expose internal packages.

Depending on your goal, you can:

- Test only public behavior via Calculator, preserving encapsulation.
- Place tests into the same module/package with --patch-module when testing package-private logic is genuinely needed.
- Refactor the logic under test into a cleanly bounded API if multiple legitimate consumers need it.

Do not export every internal package solely because a standalone test module fails to compile.

## 8. Model B: patching test code into the production module

In many unit test suites, test classes need to be in the same package as production classes to access package-private members.

The **--patch-module** option allows adding test classes into an existing production module at compile time and runtime. This is common when test frameworks need to preserve the same package layout as production sources.

Example test source:

~~~text
patch-src/
└── com/
    └── acme/
        └── math/
            └── internal/
                └── AccumulatorTest.java
~~~

Test class:

~~~java
package com.acme.math.internal;

public class AccumulatorTest {
    public static void main(String[] args) {
        Accumulator acc = new Accumulator();
        acc.add(4);
        acc.add(6);

        if (acc.value() != 10) {
            throw new AssertionError(
                    "Expected 10, got " + acc.value()
            );
        }
        System.out.println("Internal test passed");
    }
}
~~~

AccumulatorTest is in the same package com.acme.math.internal as Accumulator. When patched as part of module com.acme.math, the test can access package-private types and members under standard Java access rules.

## 9. Compiling and running tests with --patch-module

Compile test sources in the context of the production module:

~~~bash
javac --module-path mods \
      --patch-module com.acme.math=patch-src \
      -d patch-classes \
      patch-src/com/acme/math/internal/AccumulatorTest.java
~~~

Explanation:

- --module-path mods: the compiled com.acme.math module.
- --patch-module com.acme.math=patch-src: test sources are processed as additions to module com.acme.math.
- -d patch-classes: emits test bytecode into a separate directory without overwriting production artifacts.

Run the compiled test:

~~~bash
java --module-path mods \
     --patch-module com.acme.math=patch-classes \
     -m com.acme.math/com.acme.math.internal.AccumulatorTest
~~~

Output:

~~~text
Internal test passed
~~~

At runtime, the test class belongs to module com.acme.math, in the same package as production classes. There is no need to export com.acme.math.internal to a standalone test module because in this model **no separate test module exists** containing AccumulatorTest.

If you forget --patch-module when running, the JVM sees only the original module contents and may fail to find the test's main class. Patch compilation does not automatically alter production artifacts.

## 10. Comparing test module descriptors vs. patch modules

| Criterion | Separate test named module | Test patched into production |
|---|---|---|
| Test module identity | Has its own name and module-info.java | Uses the production module's name |
| Relationship with production | Declares requires | Test is treated as code inside the production module |
| Access to exported public API | Yes, if the module reads the dependency | Yes |
| Access to package-private in same package | No, if in a different module | Possible, when tests reside in the same package of the patched module |
| Realism as an external consumer | High | Lower because tests have internal access |
| Suitable scenarios | API tests, integration tests, boundary tests | Unit tests for internal logic, fixtures |
| Key configuration | --module-path, module-info.java | --patch-module, usually alongside module path |
| Separating test artifacts from production | Yes | Test bytecode can be kept in a separate output directory |

Both strategies can coexist: test contracts with a standalone named test module, and test internal helpers with patched tests. Choose the tool according to encapsulation needs rather than granting extra access merely for test convenience.

## 11. Test descriptor when using JUnit

A testing framework like JUnit 5 provides an API to mark test methods and a platform/engine to discover and execute them. In a named test module, the descriptor must declare dependencies on the modules that test code actually imports.

Illustrative example of a test module using the JUnit Jupiter API:

~~~java
module com.acme.math.tests {
    requires com.acme.math;
    requires org.junit.jupiter.api;
}
~~~

Test code:

~~~java
package com.acme.math.tests;

import com.acme.math.api.Calculator;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void sumsNumbers() {
        assertEquals(5, Calculator.sum(2, 3));
    }
}
~~~

This is a **conceptual descriptor example**. Exact execution commands depend on JUnit version, runner, build tool, and whether JUnit JARs are placed on the module path or classpath. The test engine and launcher also have their own dependencies; merely adding requires org.junit.jupiter.api does not mean every runner will automatically discover and run tests.

Because many runners use reflection to discover or invoke test methods, it may be necessary to **opens the test package** to the corresponding runner module:

~~~java
module com.acme.math.tests {
    requires com.acme.math;
    requires org.junit.jupiter.api;

    opens com.acme.math.tests to org.junit.platform.commons;
}
~~~

The exact list of modules requiring opens depends on the actual runner and how the test framework is implemented. Do not automatically open the entire module if only one test package needs reflective access.

## 12. Test frameworks and --add-reads

When tests are patched into a production module, test code may reference JUnit or other framework APIs that the production module does **not** declare in requires. This creates a module readability issue.

Example production module:

~~~java
module com.acme.math {
    exports com.acme.math.api;
}
~~~

If test classes are patched into com.acme.math and use org.junit.jupiter.api.Test, module com.acme.math may need an additional readability edge to the module containing the JUnit API when compiling or running tests.

An experimental/test option can be used:

~~~text
--add-reads com.acme.math=org.junit.jupiter.api
~~~

or adjust the test module/framework layout using the build tool's supported mechanism. If the JUnit API is placed on the classpath, the target module of --add-reads may be ALL-UNNAMED in the appropriate situation.

However, --add-reads does not automatically pull JUnit into the module graph. For named modules not yet resolved, --add-modules or adding the appropriate root module may be needed. Check the actual runner configuration to see which modules are created.

Flags of this type belong to test configuration. You should not add requires for test libraries into **production** module-info.java if the test library is not a real dependency of the released software.

## 13. Test frameworks and --add-opens

JUnit, mocking frameworks, dependency injection containers, or serializers may need deep reflection into internal classes.

With named modules, a package being exports **does not mean** private members are automatically open for reflection. When a framework needs open access, the usual option is:

~~~text
--add-opens module.name/package.name=target.module
~~~

Example:

~~~bash
java --module-path mods:test-mods:lib-mods \
     --add-opens com.acme.math/com.acme.math.internal=org.junit.platform.commons \
     -m com.acme.math.tests/com.acme.math.tests.TestMain
~~~

This example illustrates syntax. Replace the target module with the module actually performing reflective access; not every test runner needs com.acme.math.internal opened.

Distinguish clearly:

- **exports**: allows normal Java access to public types/members of a package.
- **opens**: allows deep reflection under JPMS rules.
- **--add-exports**: adds a temporary export at compile time or runtime.
- **--add-opens**: adds package open permission at runtime.
- **--patch-module**: adds classes/resources into an existing module.

If an error comes from importing an unexported type, opens will not fix the compilation issue. If an error comes from reflecting into a private member, exports will not solve it on its own.

## 14. Test module path in Maven or Gradle

Build tools typically manage test dependencies in a separate scope. With JPMS, pay attention to several points:

1. Whether production sources have module-info.java.
2. Whether test sources have their own module-info.java or are patched into the production module by the build tool.
3. Whether test dependencies are on the module path, classpath, or a supported combination.
4. Which module layer/class loader the test runner uses to discover tests.
5. Whether --patch-module, --add-reads, --add-exports, and --add-opens options are generated automatically or must be configured manually.
6. Whether the test runtime JDK is compatible with the bytecode, test engine, and named modules.

For example, in Maven the compiler and test runner plugins have options related to the module path. In Gradle, the Java plugin and test task also have mechanisms to configure module inference/test runtime. Detailed behavior depends on the build tool/plugin version and project layout.

A common error is compiling tests with one set of module options while the test runner uses a different set. Inspect the actual Java command executed by the test task when diagnosing rather than relying solely on the dependency configuration declared in the build file.

## 15. Inspecting the test module descriptor

For a separate test module, you can inspect module-info.class:

~~~bash
javap -p -v test-mods/com.acme.math.tests/module-info.class
~~~

For a modular JAR, use:

~~~bash
jar --describe-module --file dist/com.acme.math.tests.jar
~~~

Note: a test module does not have to be packaged into a JAR. An exploded module under test-mods/com.acme.math.tests is sufficient to run.

When a test module requires production, the descriptor must reflect the exact module name. Do not use the Maven/JAR artifact name in place of the JPMS module name if the two names differ.

If using the patch strategy, do not create a second module-info.java just to patch into the production module. Trying to supply a differently named descriptor or a duplicate descriptor can cause unnecessary conflicts. Use the production descriptor and appropriate test options.

## 16. Observing module resolution during test execution

You can enable module resolution logging:

~~~bash
java --show-module-resolution \
     --module-path mods:test-mods \
     -m com.acme.math.tests/com.acme.math.tests.TestMain
~~~

This output helps identify root modules, dependency modules, and resolved relationships. It is especially useful when the test module cannot find the production module or a test framework module.

To check certain module path configuration issues, you can use:

~~~bash
java --validate-modules --module-path mods:test-mods
~~~

The --validate-modules option validates the module path within the launcher's capabilities. It is not a replacement for running tests; it helps catch certain configuration errors prior to execution.

When you need to confirm where classes are loaded from, you can enable class loading logging:

~~~bash
java -Xlog:class+load=info \
     --module-path mods:test-mods \
     -m com.acme.math.tests/com.acme.math.tests.TestMain
~~~

Viewing class sources helps distinguish whether test code is loaded from a standalone test module, from patch output, or from an unexpected JAR.

## 17. Common errors with test module descriptors

### Module not found

Example message:

~~~text
module not found: com.acme.math
~~~

The test module declares requires com.acme.math, yet javac or java cannot see that artifact.

How to fix: compile production first, put mods or the proper modular JAR onto --module-path, and verify the module name and output layout. Do not confuse the parent directory mods with the subdirectory mods/com.acme.math when choosing the appropriate module path form.

### Package is not visible

The test module imports an unexported internal package. Either test via the public API, or use the patch strategy if the test genuinely needs package-private code.

### InaccessibleObjectException

The test framework uses deep reflection on an unopened package. Check the error to identify which module is performing reflection, then consider opens in the test descriptor or a temporary --add-opens at runtime.

### Test class not found

Test classes may exist in the output directory, yet the runner looks in the wrong module layer, class loader, package, or module path. Inspect the test runner command and actual class sources.

### Split package between production and test named module

If a standalone test module places classes into the same package com.acme.math.internal as production, two named modules contain the same package. This can cause split package errors when the graph/layer involves both.

With a named test module, use a separate test package. If tests must share a production package, use --patch-module so test code belongs to the same named module instead of creating a second named test module splitting that package.

### Duplicate module name

The module path has multiple JARs/exploded modules with the same JPMS name. Remove duplicates or adjust dependencies before running tests; renaming JAR files does not change the module name inside the descriptor.

### NoClassDefFoundError or ServiceConfigurationError

Test dependencies may be missing at runtime, service providers may not be included in the layer, or the test engine cannot resolve required modules. Check the runtime module path and uses/provides when using ServiceLoader.

## 18. Do not widen production APIs just to run tests

Some approaches appear quick yet weaken encapsulation:

- Exporting all internal packages so tests can import them.
- Opening the entire module with open module without a real runtime need.
- Adding test frameworks to requires of the production module.
- Dumping all test JARs onto the module path without controlling named/automatic modules.
- Moving test sources into production sources to silence compiler errors.

These approaches alter the contract or runtime structure of released software purely for testing needs.

Better principles:

- Test public behavior with a standalone named test module.
- Test package-private details with the patch strategy when needed.
- Restrict opens or --add-opens to the exact package and target module.
- Keep test dependencies in test configurations rather than shipping them as production runtime dependencies when unneeded.
- Do not modify production module-info.java merely to mask build/test errors when dedicated test configuration exists.

Keeping these boundaries clear preserves strong encapsulation in the product while still letting tests access what they need within a controlled scope.

## 19. Practical workflow for a modular project

When setting up a test module path from scratch, you can follow this workflow:

1. **Define the production module name** and which packages are exports/opens in module-info.java.
2. **Compile production** with javac --module-source-path and -m, verifying module-info.class.
3. **Choose a test strategy**: a standalone named test module for API testing, or --patch-module for internal testing.
4. **If choosing a named test module**, create the test module-info.java requiring production and needed framework modules.
5. **Compile tests** with --module-source-path test-src, --module-path mods, and -d test-mods.
6. **If choosing patch tests**, compile with --patch-module production.module=patch-src and place outputs in a separate directory.
7. **Run tests** with java -p and -m or the test runner, ensuring the runtime module path contains all dependencies.
8. **Add only needed permissions**: --add-reads for readability, --add-exports for public access, --add-opens for deep reflection.
9. **Inspect resolution/class loading errors** if tests are not discovered or fail to run.
10. **Keep production artifacts clean**: never write test classes into production outputs or released modular JARs.

When using large frameworks, build tools are convenient for managing these steps. Still, understanding module-level javac/java syntax helps pinpoint whether an error arises during compilation, resolution, class loading, or test discovery.

## 20. Key takeaways

- **Test module path** is the module path used to compile/run tests; Java has no standard option named --test-module-path.
- **Test module descriptor** is the module-info.java of a named test module when tests are organized as an independent module.
- A named test module must requires the production module and any framework modules that test code imports.
- A named test module obeys the same readability, exports, and opens rules as any other module.
- **--patch-module** lets you place test classes into the production module to access package-private code in the same package.
- A standalone test module should not place classes into packages belonging to the production module, to avoid split packages.
- **--add-reads** and **--add-opens** solve different problems; do not use one in place of the other.
- Test frameworks using reflection may require opening test packages or production packages in a restricted scope.
- Compile-time module path and runtime module path must be consistent, yet they serve different phases.
- Inspect --show-module-resolution, module-info.class, and test runner commands when diagnosing.
- Do not broadly alter production exports/opens just to make tests pass.

**Conclusion:** With JPMS, test configuration must respect the module graph and encapsulation. Use a named test module with its own descriptor when you want to test like an external consumer; use --patch-module when you need internal tests within the same module. These two approaches provide clearly scoped testing without sacrificing the design boundaries of production modules.