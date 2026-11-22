# Controlled --add-reads or --add-opens for Testing

When testing an application that uses the Java Platform Module System (JPMS), the test suite may need more access than production code: the framework has to discover test methods via reflection, tests need to read a test library's API, or an internal test needs to reach non-exported classes. JPMS does not automatically relax the module graph just because code runs from a test directory.

Two common options are **--add-reads** and **--add-opens**. They solve two different problems:

- **--add-reads** adds a readability relationship: a named module is allowed to read a target module, including the unnamed module when using ALL-UNNAMED.
- **--add-opens** opens a package of a source module for deep reflection from a target module at runtime.

The goal during testing is not to break encapsulation across the entire application. Apply extra permissions only when tests genuinely need them, narrow them by module and package, restrict them to test tasks, and never carry them into production configuration.

## 1. Why Do JPMS Tests Have Special Access Needs?

A modular application might be deployed with this descriptor:

~~~java
module com.example.billing {
    exports com.example.billing.api;
}
~~~

In production, consumers should only use the api package. At test time, however, three distinct needs can arise:

1. Black-box tests using the public API of com.example.billing from another test module.
2. White-box tests compiled into the module under test to verify internal behavior.
3. A test runner or framework reflecting on classes/methods/fields of the module under test.

If tests live in an independent named module and only call exported APIs, you typically do not need --add-reads or --add-opens: simply declare requires and use the public API normally.

If tests are patched into the production module or the framework requires deep reflection, targeted permission relaxation is sometimes necessary.

## 2. Understanding requires, exports, opens, and Readability

Each mechanism serves a specific purpose:

| Mechanism | Meaning |
| --- | --- |
| requires m | Declares a static dependency, making the current module read m. |
| exports p | Allows access to public types in package p under JPMS rules. |
| opens p | Allows deep reflection into package p at runtime. |
| --add-reads a=b | Adds a readability edge where a reads b in tool or runtime configuration. |
| --add-exports a/p=b | Exports package p of a to b. |
| --add-opens a/p=b | Opens package p of a for deep reflection from b at runtime. |

One option cannot substitute for all others:

- Having readability does not let you access public types in a non-exported package.
- An exported package does not necessarily permit accessing private fields via reflection.
- An opened package does not automatically add readability or turn the package into a public API for compile-time imports.
- --add-reads does not open a package for a framework to call setAccessible(true).

Different errors require different mechanisms.

## 3. --add-reads Syntax

General syntax:

~~~text
--add-reads SOURCE_MODULE=TARGET_MODULE
~~~

Multiple target modules can be specified as a comma-separated list, depending on tool support. The relationship is directional: SOURCE_MODULE is permitted to read TARGET_MODULE.

Example:

~~~bash
java --module-path mods \
    --add-reads com.example.billing=com.example.testing.tools \
    -m com.example.billing/com.example.billing.Main
~~~

In this example, com.example.billing is granted readability to com.example.testing.tools. That does **not** mean com.example.testing.tools reads com.example.billing; the reverse direction requires its own readability relationship.

Readability allows cross-module references under JPMS rules, but the target's package must still be appropriately exported for external code to access public types.

## 4. Using ALL-UNNAMED When Dependencies Are on the Classpath

A JAR on the classpath belongs to the unnamed module of its class loader. It has no module name to write in a named module's requires directive.

When test classes are patched into a named module yet need to use test libraries on the classpath, you can add a readability edge:

~~~bash
--add-reads com.example.billing=ALL-UNNAMED
~~~

Meaning: module com.example.billing can read unnamed modules in the current configuration. This is common when JUnit or a mocking library is supplied on the test classpath instead of the module path.

This option does not change where the library is located and does not turn classpath JARs into named modules. If a named test module needs a library that already has a module name on the module path, prefer requires in the test descriptor whenever possible.

ALL-UNNAMED has a broader scope than a specific named module. Therefore, apply it only to test tasks that genuinely need to read classpath libraries.

## 5. --add-opens Syntax

General syntax:

~~~text
--add-opens SOURCE_MODULE/PACKAGE=TARGET_MODULE
~~~

For example, a test framework packaged as a named module com.example.test.engine needs deep reflection into package com.example.billing.internal:

~~~bash
java --module-path mods \
    --add-opens com.example.billing/com.example.billing.internal=com.example.test.engine \
    -m com.example.test.launcher/com.example.test.launcher.Main
~~~

The module names in the command above are illustrative; replace them with the actual module names of your test engine, launcher, and application module.

The --add-opens option makes the package accessible for deep reflection from the target module at runtime. It does not grant open access to every other package in the source module.

If the test engine sits on the classpath, replace the target module with ALL-UNNAMED:

~~~bash
--add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED
~~~

Open only the exact packages the test runner truly needs. Do not open all of java.base or dozens of internal application packages without a concrete error and reason.

## 6. Why Do JUnit or Test Frameworks Need opens?

Test frameworks typically discover annotated methods and invoke them via reflection. A test method may be package-private or have a non-public constructor; invoking it from another module is governed by JPMS access rules.

Example:

~~~java
package com.example.billing.test;

import org.junit.jupiter.api.Test;

class InvoiceCalculatorTest {
    @Test
    void addsTax() {
        // Test assertions.
    }
}
~~~

If the test class is patched into the named module com.example.billing, the framework module may need reflective access to package com.example.billing.test to instantiate the class and invoke methods.

When the test engine is a named module, open the package to the exact module needing reflective access. When the framework is on the classpath, ALL-UNNAMED can be used. Which module needs access depends on the version, packaging, and launcher in use; obtain it from the actual error or test framework documentation rather than guessing from the JAR filename.

Not every test needs opens. For example, a test that only calls exported public methods may run without requiring deep reflection into private members, depending on how the test runner operates.

## 7. Black-Box Tests with a Separate Module

A good way to test public contracts is to place tests in a separate named module:

~~~text
src/
├── com.example.billing/
│   ├── module-info.java
│   └── com/example/billing/api/InvoiceService.java
└── com.example.billing.tests/
    ├── module-info.java
    └── com/example/billing/tests/ApiContractTest.java
~~~

Production module:

~~~java
module com.example.billing {
    exports com.example.billing.api;
}
~~~

Test module:

~~~java
module com.example.billing.tests {
    requires com.example.billing;
}
~~~

Tests can use public types in the api package. The test module cannot automatically read the internal package because the production module does not export it.

The benefit is that tests reflect how an external consumer actually uses the library. If the API needs a package or type that is not exported, a compile error exposes the inconsistent contract.

For this type of test, do not add --add-exports or --add-opens just to make tests pass. If a test cannot use the public API, review the API design or how the test is structured.

## 8. White-Box Tests with --patch-module

Some tests need to live in the same module as production code to test package-private classes or internal behavior. JPMS supports --patch-module to add classes/resources to a named module at compile time or runtime.

Example:

~~~text
src/main/java/com/example/billing/internal/TaxTable.java
src/test/java/com/example/billing/internal/TaxTableTest.java
~~~

When tests are patched into com.example.billing, from the module system's perspective those test classes belong to com.example.billing rather than forming an independent test module.

Illustrative compile configuration:

~~~bash
javac --module-path mods \
    --patch-module com.example.billing=src/test/java \
    --add-reads com.example.billing=ALL-UNNAMED \
    --class-path libs/test-api.jar \
    -d out/test \
    src/test/java/com/example/billing/internal/TaxTableTest.java
~~~

Here:

- --patch-module indicates that the test sources are compiled as additions to module com.example.billing.
- --add-reads adds readability to test libraries on the classpath.
- --class-path supplies the test libraries to the compiler.
- out/test holds the compiled test classes.

The example assumes actual compiled artifacts in mods and corresponding libraries in libs. Compilation details are adapted to the project's layout and build plugins.

--patch-module is **not** a way to open packages to external frameworks. The test runner may still need --add-opens when invoking test methods via reflection.

## 9. Runtime Tests May Need All Three Settings

For white-box tests patched into the production module with a framework running on the classpath, the test run may need:

~~~text
--patch-module com.example.billing=out/test
--add-reads com.example.billing=ALL-UNNAMED
--add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED
~~~

Their roles differ:

- patch-module injects compiled test classes into the target named module.
- add-reads lets tests inside the target module read test libraries in the unnamed module.
- add-opens allows the classpath runner to reflect into the needed test or implementation package.

If test classes live in com.example.billing.tests instead of internal, open the package actually containing the test classes to the framework. You do not necessarily need to open internal just because the tests exercise it by calling package-private methods.

These options should only exist in the test process. When running the production application, never patch test classes into modules and do not pass broadened permissions that production does not need.

## 10. Minimal Example: Reproducing the Need for --add-opens

Suppose there is a named module com.example.counter:

~~~java
module com.example.counter {
    exports com.example.counter.api;
}
~~~

A class in a non-exported package:

~~~java
package com.example.counter.internal;

public final class CounterState {
    private int count = 7;

    private CounterState() {
    }
}
~~~

A ReflectionProbe program on the classpath wants to instantiate it and read the private field:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
                Class.forName("com.example.counter.internal.CounterState");

        Constructor<?> constructor = type.getDeclaredConstructor();
        constructor.setAccessible(true);
        Object target = constructor.newInstance();

        Field field = type.getDeclaredField("count");
        field.setAccessible(true);

        System.out.println(field.getInt(target));
    }
}
~~~

Suppose the modular JAR or compiled output of com.example.counter is in mods and the compiled ReflectionProbe is in out/probe. When running:

~~~bash
java --module-path mods \
    --add-modules com.example.counter \
    -cp out/probe \
    ReflectionProbe
~~~

Calling setAccessible(true) can throw InaccessibleObjectException because the internal package is not open to the unnamed module.

If this is a controlled test, you can run:

~~~bash
java --module-path mods \
    --add-modules com.example.counter \
    --add-opens com.example.counter/com.example.counter.internal=ALL-UNNAMED \
    -cp out/probe \
    ReflectionProbe
~~~

Now the internal package is opened for deep reflection from the program on the classpath. This is a clearly scoped runtime permission, not a permanent change to module-info.java.

In real systems, consider whether testing through the public API is sufficient before relying on private fields.

## 11. --add-reads Cannot Fix InaccessibleObjectException

Suppose module com.example.counter is already readable by the test module, yet the test attempts to call:

~~~java
field.setAccessible(true);
~~~

on a private field of a non-open package.

Adding:

~~~text
--add-reads com.example.tests=com.example.counter
~~~

only adds a readability edge from tests to counter. It does not grant permission to access private fields via reflection.

When an error states that a package is not open to the caller module, check opens or --add-opens appropriately. If the test does not genuinely need private members, switching to the public API is better.

Conversely, --add-opens does not help the compiler import a public type in a non-exported package under standard access rules. When compile-time API access is needed, look at exports/--add-exports and readability.

## 12. When Is --add-exports Needed?

This lesson focuses on --add-reads and --add-opens, but sometimes a test failure is due to a package not being visible rather than deep reflection.

For example, a test tries to import a public implementation class from a non-exported package:

~~~java
import com.example.billing.internal.BillingCalculator;
~~~

If the test is in another named module, the compiler may report that the package is not exported. Adding --add-opens at runtime will not solve that compilation error.

When compatibility genuinely requires it, tooling can pass:

~~~text
--add-exports com.example.billing/com.example.billing.internal=com.example.billing.tests
~~~

to the exact target module at compile time and runtime as needed. However, if such tests can be written using the public API, do not create dependencies on internal classes simply to make writing tests easier.

If you own the production code, it is usually better to turn the logic under test into an intentional contract or use patched tests in the same module rather than broadly exposing internal APIs.

## 13. Gradle Configuration Only for Tests

In Gradle, place JVM options on the Test task, not on production run configurations.

Example with Groovy DSL:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-reads',
        'com.example.billing=ALL-UNNAMED',
        '--add-opens',
        'com.example.billing/com.example.billing.internal=ALL-UNNAMED'
    )
}
~~~

This snippet illustrates where to place the configuration. It is appropriate only if tests run with module com.example.billing resolved and the framework truly needs both permissions.

If Gradle or a test plugin already configures the module path, patch-module, or equivalent permissions, avoid duplication or conflicts. Compiler options on JavaCompile tasks and JVM options on Test tasks have different scopes.

When compiling test classes patched into a named module, you may also need to configure compiler arguments or the module path. Do not assume jvmArgs on the Test task alters how javac compiled the tests.

If only an integrationTest task needs reflection, configure that specific task rather than applying tasks.withType(Test) to all tests.

## 14. Maven Configuration for Test Runtime

With the Maven Surefire Plugin, test runtime JVM flags are typically configured via argLine when the plugin forks a JVM and uses the appropriate execution mode.

Illustrative example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>
            --add-reads com.example.billing=ALL-UNNAMED
            --add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
~~~

In real configurations, preserve other JVM arguments your project uses, such as coverage agent flags. How the test module path and patch-module are configured depends on the plugin, Java version, and project layout.

For integration tests, the Maven Failsafe Plugin can be configured separately to keep relaxed permissions scoped to the exact tests that need them.

Do not copy these test flags into java -jar commands, production container images, or service launch scripts. Test-only flags exist to enable testing for specific reasons, not to change the packaging policy of the production program.

## 15. When to Choose the Descriptor Instead of Flags?

There are two ways to grant permissions:

1. **Declare permissions in module-info.java:** suited for long-term designed behavior, such as a production framework needing deep reflection into a model package.
2. **Add flags at test runtime/compile time:** suited for cases where only tests need the permission and it should not become part of the production contract.

Example where production needs an ORM:

~~~java
module com.example.billing {
    exports com.example.billing.api;
    opens com.example.billing.entity to com.example.persistence;
}
~~~

This is part of the application's runtime design, not a temporary test permission.

Conversely, if only the test suite wants to read private state, consider a test-only configuration:

~~~text
--add-opens com.example.billing/com.example.billing.internal=com.example.tests
~~~

The name com.example.tests must be the actual module name when tests run as a named module. If the reflecting framework is in a different module from the test classes, the target of opens must be the module actually performing the reflection.

Avoid modifying production module-info.java to open packages to test frameworks used only during builds, unless the system has a clear architectural reason.

## 16. How to Identify the Module Actually Performing Reflection

Error messages usually report both the source module and the target module:

~~~text
module com.example.billing does not "opens
com.example.billing.internal" to module com.example.test.engine
~~~

This means:

- The package belongs to module com.example.billing.
- The rejected package is com.example.billing.internal.
- The module performing reflection is com.example.test.engine.

A corresponding test-only remedy might be:

~~~text
--add-opens com.example.billing/com.example.billing.internal=com.example.test.engine
~~~

Do not automatically target the test class module if the stack trace shows the framework engine belongs to a different module.

If the message says "to unnamed module", the caller was in the unnamed module at the time of the error. In that case ALL-UNNAMED can be used for the test runtime, though you should still verify classpath artifacts and the exact scope to open.

To confirm a JAR's module name:

~~~bash
jar --describe-module --file path/to/test-engine.jar
~~~

This is especially helpful for automatic modules, whose names are derived from the manifest or JAR filename.

## 17. Handling "module not found" or "unknown module"

If --add-reads or --add-opens references a module that does not exist or has not been resolved, the launcher/compiler may warn or error depending on the situation.

Common causes:

- Wrong module name for the framework or application.
- Dependency has not been placed on the module path.
- Module is on the module path but was not resolved into the configuration.
- Test configuration uses the classpath while the flag points to an assumed module name.
- The build command uses a different JDK or configuration than the manual run command.

First verify the actual module name:

~~~bash
jar --describe-module --file libs/framework.jar
~~~

Then inspect runtime module resolution:

~~~bash
java --show-module-resolution \
    --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Add --add-modules when there is a reason to bring a root module into the graph. Do not use --add-reads as a substitute for locating or resolving a missing module.

## 18. Quick Error Distinction Table

| Symptom | Possible Mechanism Involved | How to Address |
| --- | --- | --- |
| package ... is not visible | Missing export or readability | Check requires, module path, exports, and --add-exports. |
| module ... does not read ... | Missing readability | Check requires or --add-reads in the right direction. |
| InaccessibleObjectException | Deep reflection into a closed package | Check opens or --add-opens for the exact caller. |
| IllegalAccessException when invoking method | Insufficient reflection/Java visibility permission | Check caller, member, exports/opens, and invocation path. |
| ClassNotFoundException | Class cannot be found | Check classpath/module path and class loader. |
| NoClassDefFoundError | Required dependency or class failed to load | Check runtime dependencies and root cause. |
| Tests pass in IDE yet fail on CLI | IDE and CLI pass different module flags | Compare compiler args, JVM args, and module path config. |
| Tests only pass when opening all packages | Tests depend heavily on implementation | Consider switching to public API or isolating white-box tests in the right module. |

Do not fix these errors by adding every flag at once. Choose the minimal permission based on the error message and testing need.

## 19. Observing Module State Without Opening Permissions

If you need to verify readability and opens inside a program, you can use the Module API:

~~~java
Module owner = com.example.billing.api.Invoice.class.getModule();
Module caller = TestDiagnostics.class.getModule();

System.out.println("Caller reads owner: " + caller.canRead(owner));

System.out.println("API exported to caller: " +
        owner.isExported("com.example.billing.api", caller));

System.out.println("Internal open to caller: " +
        owner.isOpen("com.example.billing.internal", caller));
~~~

These APIs report the current runtime relationship between two modules without calling setAccessible(true). When analyzing a framework, caller must be the module actually invoking reflection; checking with TestDiagnostics.class.getModule() does not necessarily match a framework in another module.

To check open permissions for a test engine, obtain the engine's own Module object if possible, or rely on exception messages and the module graph.

## 20. Keeping Test Permissions Narrowly Scoped

A controlled strategy should clearly specify:

- **Source module:** the module owning the package to access.
- **Package:** the package containing the denied class or method.
- **Target module:** the framework/test runner that actually needs permission.
- **Phase:** test compilation only, unit tests, or integration tests.
- **Reason:** missing readability, deep reflection needed, or public type in a non-exported package.
- **Removal point:** when upgrading the framework, refactoring tests, or switching to public APIs.

Example configuration tracking table:

| Permission | Phase | Reason |
| --- | --- | --- |
| --add-reads com.example.billing=ALL-UNNAMED | Patched test compile and test runtime when needed | Test classes in the named module must reference test libraries on the classpath. |
| --add-opens com.example.billing/com.example.billing.tests=ALL-UNNAMED | Test runtime | Classpath test engine needs to invoke test methods via reflection. |
| --add-opens com.example.billing/com.example.billing.internal=com.example.test.engine | Specific test runtime | Named-module engine needs to inspect private members in a white-box test. |

Do not add these lines unless your project has the corresponding need. The table only illustrates how to document decisions; module and package names must come from your real project.

## 21. Steps to Eliminate Temporary Flags

A test-only flag can become technical debt if left unmanaged. To remove it:

1. List all JPMS flags configured specifically for tests.
2. Group them by source module, package, and target module.
3. Identify which tests actually require each permission.
4. For black-box tests, switch assertions to the public API instead of private fields.
5. For white-box tests, consider patch-module or extracting an intentional internal API where appropriate.
6. Upgrade frameworks if newer versions offer better JPMS support.
7. Remove flags one by one once the underlying need is eliminated.
8. Re-run unit tests, integration tests, and production launch commands to confirm no hidden dependency remains.

Do not copy test flags into production just to make environments identical. The two environments have different roles and should maintain appropriate minimal privileges.

## 22. Self-Check

**Scenario 1:** A test class is patched into com.example.billing and imports a test library on the classpath. When the compiler reports that the module does not read the unnamed module, what should you check?

Answer: --add-reads com.example.billing=ALL-UNNAMED during test compilation, along with the classpath containing the library. If runtime also needs to link against that library, configure the appropriate readability relationship at runtime.

**Scenario 2:** A test framework on the classpath cannot invoke a package-private method in module com.example.billing. The error states package com.example.billing.tests is not open. Which flag might apply?

Answer: --add-opens com.example.billing/com.example.billing.tests=ALL-UNNAMED at runtime, provided the framework genuinely needs deep reflection into this test package.

**Scenario 3:** Does adding --add-reads make setAccessible(true) succeed on a private field of another module?

Answer: no. --add-reads only adds readability. Deep reflection typically requires the package to be opened to the right target.

**Scenario 4:** Why does an independent test using only exported public APIs usually not need --add-opens?

Answer: the test can rely on requires and standard Java access rules; there is no need to bypass private member checks.

**Scenario 5:** The test engine is a named module, yet the project uses ALL-UNNAMED out of habit. What should be checked?

Answer: verify which module actually performs reflection. If it is a named module, specify that module name instead of ALL-UNNAMED whenever possible.

**Scenario 6:** Should test add-opens flags be added to the production launch command?

Answer: normally no. Grant relaxed permissions only in the test task that needs them, document the reason, and remove the flag when no longer needed.

**Scenario 7:** The compiler reports a public class in an internal package is not visible. Should --add-opens be used to fix it?

Answer: no. This is likely a compile-time exports/readability issue. Check whether the test can use the public API or should be reorganized as a white-box test; use targeted --add-exports only if truly necessary.