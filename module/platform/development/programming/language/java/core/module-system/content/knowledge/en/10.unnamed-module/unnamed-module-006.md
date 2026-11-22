# Migration when test code is still in the unnamed module

When migrating a Java application from the classpath to the Java Platform Module System (JPMS), it is not necessary to convert all test code into a named module immediately. A common migration approach is to keep test sources and the test framework on the classpath, while production modules already have `module-info.java` and run on the module path.

In this configuration, test classes belong to the **unnamed module** of the class loader. An unnamed module can read resolved named modules, but access is still governed by JPMS boundaries: tests can use public APIs in exported packages; unexported internal packages remain closed to normal source access.

To ensure a controlled migration, you need to understand how to combine `--module-path`, `--add-modules`, `--add-exports`, and `--add-opens`, as well as distinguish public API testing from internal testing that requires special access permissions.

## 1. Unnamed modules in the test context

When a class is loaded from the classpath, it belongs to the unnamed module associated with the corresponding class loader. Unlike a named module, an unnamed module does not have a `module-info.java` to declare `requires`, `exports`, or `opens`.

Project example:

```text
application/
├── src/main/java/
│   └── com.example.application/
│       ├── module-info.java
│       └── com/example/application/
│           ├── api/
│           │   └── OrderService.java
│           └── internal/
│               └── OrderRepository.java
└── src/test/java/
    └── com/example/application/
        └── OrderServiceTest.java
```

Production code belongs to the named module `com.example.application`. If tests are compiled and run from the classpath, `OrderServiceTest` belongs to an unnamed module, even though it uses the same package name in the source code.

This is an important boundary: writing the same `package com.example.application;` does not make tests on the classpath part of the production named module. Tests and production still reside in two different modules.

## 2. An unnamed module can read named modules

An unnamed module can read resolved named modules in the runtime configuration. Therefore, tests on the classpath can reference public types in packages exported by a named module.

Production descriptor:

```java
module com.example.application {
    exports com.example.application.api;
}
```

Test source:

```java
package com.example.application;

import com.example.application.api.OrderService;

class OrderServiceTest {
    void createsOrder() {
        OrderService service = new OrderService();
        // Verify the public behavior of the service.
    }
}
```

Tests can import and use `OrderService` if the API package is exported, the production module is present on the module path, and it has been resolved.

In this case, the tests do not need a separate `module-info.java`. Being in the unnamed module does not prevent tests from calling exported public APIs.

## 3. Why are --module-path and --add-modules needed?

When compiling or running tests from the classpath, production named modules must be placed on the module path. In addition, the module under test must be added to the set of resolved modules.

Example compiling tests with `javac`:

```shell
javac ^
  --module-path build/mods ^
  --add-modules com.example.application ^
  --class-path lib/junit-platform-console-standalone.jar ^
  -d build/test-classes ^
  @build/test-sources.txt
```

On Windows PowerShell or CMD, the `^` character in the example is CMD's line continuation character; if running in PowerShell, you can write the command on one line or use a backtick for line continuation. On Linux/macOS, you can write:

```shell
javac \
  --module-path build/mods \
  --add-modules com.example.application \
  --class-path lib/junit-platform-console-standalone.jar \
  -d build/test-classes \
  @build/test-sources.txt
```

Meaning of the options:

- `--module-path build/mods` provides the compiled named modules.
- `--add-modules com.example.application` requests adding the production module to the resolved module set.
- `--class-path` provides test libraries such as JUnit Platform Console Standalone.
- `-d build/test-classes` specifies the output directory for compiled test classes.

When running tests with JUnit Console Launcher:

```shell
java \
  --module-path build/mods \
  --add-modules com.example.application \
  --class-path "build/test-classes:lib/junit-platform-console-standalone.jar" \
  org.junit.platform.console.ConsoleLauncher execute \
  --scan-class-path
```

On Windows, the separator for classpath elements is a semicolon (`;`); on Linux and macOS, it is a colon (`:`). Adjust directory paths and module names to match your actual build structure.

`--add-modules` is especially useful because the tests are in the unnamed module. Tests can read resolved named modules, yet the production module still needs to be present in the runtime configuration for its classes to be found.

## 4. Testing public APIs: the preferred case

If tests only verify the module's public contract, the simplest migration path is to export the proper API packages and keep the tests on the classpath.

Production example:

```java
module com.example.application {
    exports com.example.application.api;
}
```

Test:

```java
import com.example.application.api.OrderService;

import static org.junit.jupiter.api.Assertions.*;

class OrderServiceTest {
    @Test
    void calculatesOrderTotal() {
        OrderService service = new OrderService();

        assertEquals(120, service.totalFor("ORDER-01"));
    }
}
```

The test calls public methods like a regular client. This is also a design benefit: tests verify behavior that module users can rely on, without needing to know how the module stores data or organizes internal classes.

You should not export internal packages merely to make test access easier. Exports are part of the module contract; once a package is exported, other modules can depend on public types in that package.

## 5. When tests need to access public types in an unexported package

During certain migration stages, tests might need to access a public class in an internal package. Export permission can be granted temporarily using the `--add-exports` option.

Example production module:

```java
module com.example.application {
    exports com.example.application.api;
}
```

The test wants to reference a public class in the package:

```text
com.example.application.internal
```

You can add:

```shell
--add-exports com.example.application/com.example.application.internal=ALL-UNNAMED
```

This option must be applied at both test compile time and runtime if tests reference that package:

```shell
javac --module-path build/mods ^
      --add-modules com.example.application ^
      --add-exports com.example.application/com.example.application.internal=ALL-UNNAMED ^
      --class-path lib/junit-platform-console-standalone.jar ^
      -d build/test-classes @build/test-sources.txt
```

When running:

```shell
java --module-path build/mods ^
     --add-modules com.example.application ^
     --add-exports com.example.application/com.example.application.internal=ALL-UNNAMED ^
     --class-path "build/test-classes;lib/junit-platform-console-standalone.jar" ^
     org.junit.platform.console.ConsoleLauncher execute --scan-class-path
```

The syntax has the form:

```text
--add-exports <module>/<package>=<target-module>
```

Here:

- `com.example.application` is the module owning the package.
- `com.example.application.internal` is the additionally exported package.
- `ALL-UNNAMED` represents unnamed modules.

This option is a command-line exception and does not modify `module-info.java` inside the JAR. It should be scoped to test tasks and used only for packages that genuinely need testing. If an internal package must be used frequently, revisit the API boundaries rather than keeping extra exports indefinitely.

## 6. --add-exports does not grant deep reflection

`--add-exports` allows normal Java API access to the specified package. It does not automatically grant frameworks permission to use deep reflection to read or modify private fields, private methods, or non-public constructors.

If tests or frameworks need deep reflection, `--add-opens` can be used:

```shell
--add-opens com.example.application/com.example.application.internal=ALL-UNNAMED
```

Example test using reflection:

```java
Field field = OrderRepository.class.getDeclaredField("connection");
boolean accessible = field.trySetAccessible();

assertTrue(accessible);
```

For operations on private members to be allowed, the module containing the package must open that package to the module performing reflection.

Remember:

- `--add-exports` serves normal access to public types from an unexported package.
- `--add-opens` serves deep reflection at runtime.
- `--add-opens` does not replace `--add-exports` when test code needs to import a public type from an unexported package.
- `--add-opens` is a runtime option, not a solution for compiling source code that references an unexported package.

If a test framework performs reflection, the open target must be the module actually containing the reflection code. When JUnit or supporting libraries run on the classpath, the target is usually `ALL-UNNAMED`. If the framework runs as a named module, use the framework's module name instead of defaulting to ALL-UNNAMED.

## 7. Tests with the same package name still cannot access package-private members

A common misconception is placing a test in the same package as production code and expecting to access package-private members.

Production example:

```java
package com.example.application.internal;

class OrderRepository {
    void clearCache() {
    }
}
```

The test also declares:

```java
package com.example.application.internal;

class OrderRepositoryTest {
    void testClearCache() {
        OrderRepository repository = new OrderRepository();
        repository.clearCache();
    }
}
```

If production belongs to a named module while the test belongs to an unnamed module, sharing the same package name does not make the test a member of the production module. Package-private access remains restricted by runtime package/module boundaries; tests cannot rely on matching package names to access package-private classes or members.

Adding `--add-exports` also does not turn package-private into public. It only opens package access at the module level for types and members that are already accessible under Java access modifiers.

There are three ways to handle this:

1. Test behavior through the public API if that is the contract to protect.
2. Move white-box tests into the module under test, for example by configuring `--patch-module` or using a test module path mechanism supported by the build tool.
3. Refactor the code so the part under test has a suitable abstraction or seam, rather than forcing tests to depend on internal details.

When using `--patch-module`, tests are injected into the target module during compilation or execution. This approach can place tests within the same module boundary as production code, but compile and runtime configurations must be aligned; test dependencies such as JUnit must also be readable by the test module. Do not add `--patch-module` arbitrarily if only public API testing is needed.

## 8. Distinguishing --add-reads during migration

`--add-reads` adjusts readability relationships between modules. It is typically needed when a named module must read another module that its descriptor does not declare, for example in certain test configurations or legacy integrations.

For example:

```shell
--add-reads com.example.application=ALL-UNNAMED
```

This option states that the named module `com.example.application` is allowed to read unnamed modules.

In typical test scenarios, the access direction is tests in the unnamed module calling exported APIs of the production named module. An unnamed module can already read resolved named modules, so `--add-reads` is usually unnecessary for this direction.

Do not confuse them:

- `--add-reads` adds a readability relationship.
- `--add-exports` opens a package for normal Java code access.
- `--add-opens` opens a package for deep reflection.

These three options address three distinct aspects. Add only the exact option required by the actual error or need.

## 9. Configuring tests in Gradle or Maven

When using Gradle or Maven, the principles remain the same as direct JDK commands:

- Production modules must be compiled and placed properly on the module path.
- The test framework and test classes can remain on the classpath.
- Production modules must be resolved in the runtime configuration.
- Permission-expanding options should only be attached to test tasks or the test JVM.

In Gradle, JVM arguments can be configured for the test task:

```groovy
tasks.test {
    jvmArgs(
        '--add-modules', 'com.example.application',
        '--add-opens',
        'com.example.application/com.example.application.internal=ALL-UNNAMED'
    )
}
```

This example only illustrates where to place runtime arguments. For production modules to actually be placed on the module path, the build must configure modularity appropriately, such as enabling module path inference when the project meets Gradle's conditions:

```groovy
java {
    modularity.inferModulePath = true
}
```

If test sources remain in the unnamed module, verify how Gradle organizes the test compile classpath, test runtime classpath, and module path before adding flags. Not every project shares the same layout, especially when using multiple source sets or custom test plugins.

With Maven, JVM options are typically passed to the forked test JVM via Surefire/Failsafe configuration. Check the plugin version and how the plugin constructs the module path in the specific project. Do not copy a generic module-path configuration without verifying the actual command line of the test process.

## 10. Practical migration roadmap

A cautious roadmap can be divided into steps:

1. **Modularize production first:** add `module-info.java` and declare dependencies and API packages.
2. **Keep tests on the classpath:** tests continue belonging to the unnamed module in the initial phase.
3. **Resolve production modules:** configure the module path and add modules under test to the runtime configuration.
4. **Test public APIs:** prioritize testing through exported packages.
5. **Open packages only with justification:** use `--add-exports` for public types in unexported packages and `--add-opens` for deep reflection.
6. **Separate white-box tests:** if package-private access is required, consider patching tests into the module or redesigning test seams.
7. **Scope flags to tests:** do not let permission-expanding options accidentally become production configuration.
8. **Re-evaluate after migration:** once tests stabilize, decide whether tests need to become a named module or remain in the unnamed module.

The goal is to maintain migration velocity while keeping visibility into where tests depend on internal implementation. Every addition of `--add-exports` or `--add-opens` should have a specific reason and be removable when no longer needed.

## Conclusion

Test code can remain in the unnamed module while production has already migrated to JPMS. An unnamed module can read resolved named modules and use public APIs belonging to exported packages. With proper configuration, tests can continue running from the classpath during migration.

When deeper access is needed, distinguish the permissions properly: `--add-exports` for public types in unexported packages, `--add-opens` for deep reflection, and `--add-reads` for adjusting readability direction. These flags do not make classpath tests members of a named module and do not grant package-private access.

Start with public API testing, restrict exceptions to the test runtime, and only use `--patch-module` or move tests to the module path when white-box testing is required. That way, production can maintain clear module boundaries while the test suite is migrated step by step.