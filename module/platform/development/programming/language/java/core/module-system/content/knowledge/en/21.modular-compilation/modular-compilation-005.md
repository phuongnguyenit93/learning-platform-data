# javac --patch-module in Build or Test

## Objectives

After this lesson, you will be able to:

- Explain what `--patch-module` is used for when compiling a named module.
- Distinguish between `--patch-module`, `--module-path`, and `--class-path`.
- Compile test sources as part of the module under test.
- Allow tests to access package-private code in the same package without exporting internal packages into the public API.
- Configure the required compiler arguments in a `javac` command or Gradle.
- Understand why patching the module is also required at test runtime.

## 1. The Problem When Testing a Named Module

Suppose a module only exports its API package:

~~~java
module com.example.calc {
    exports com.example.calc.api;
}
~~~

Inside the module there is an internal package:

~~~java
package com.example.calc.internal;

final class Calculator {

    int add(int left, int right) {
        return left + right;
    }
}
~~~

`Calculator` has default (package-private) access, so only code in the same package can access it. The `com.example.calc.internal` package is also not exported to other modules.

This is a sound encapsulation choice: external applications use the public API, while the internal implementation stays hidden.

However, tests need to test `Calculator` directly, including package-private behavior. If tests are compiled as code in a separate module or placed in the unnamed module on the classpath, they do not automatically get access as a class in the same package and same module.

`javac --patch-module` solves this by inserting additional sources or classes into an existing named module during compilation.

## 2. Syntax and Meaning of --patch-module

General syntax:

~~~text
javac --patch-module <module>=<path>[<path-separator><path>...]
~~~

Example:

~~~bash
javac --patch-module com.example.calc=src/test/java ...
~~~

Meaning:

- `com.example.calc` is the name of the module to be patched.
- `src/test/java` is the directory containing test sources compiled as part of that module.
- Multiple paths can be passed, separated by the operating system's path separator.
- On Windows, the path separator is a semicolon (`;`); on Linux/macOS, the path separator is a colon (`:`).

When using `--patch-module`, the compiler treats the patched sources as members of the target module. Therefore, test classes can reside in an internal package of the module and access package-private members in the same package.

`--patch-module` does not create a new module. The target module must already be resolved in the compilation's module graph. This option augments or overrides the module's contents using the specified paths.

### 2.1. Distinguishing the Three Path Types

| Option | Purpose |
|---|---|
| `--module-path` | Locate named modules and their dependencies |
| `--class-path` / `-cp` | Locate classes belonging to the unnamed module |
| `--patch-module` | Add sources/classes into a specific named module |

For example, `--module-path build/mods` helps the compiler find the `com.example.calc` module; `--patch-module com.example.calc=src/test/java` places test sources into that module; `-cp libs/junit-platform-console-standalone.jar` provides the JUnit library on the classpath.

The three options have distinct roles and may need to appear in the same command.

## 3. Example Project Structure

Suppose the project has the following structure:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/
│   │       ├── module-info.java
│   │       └── com/example/calc/
│   │           ├── api/CalculatorService.java
│   │           └── internal/Calculator.java
│   └── test/
│       └── java/
│           └── com/example/calc/
│               └── internal/CalculatorTest.java
├── libs/
│   └── junit-platform-console-standalone.jar
└── build/
~~~

Module descriptor:

~~~java
module com.example.calc {
    exports com.example.calc.api;
}
~~~

The test resides in the exact package of the class under test:

~~~java
package com.example.calc.internal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    void addsTwoNumbers() {
        Calculator calculator = new Calculator();

        assertEquals(5, calculator.add(2, 3));
    }
}
~~~

`CalculatorTest` does not need to be exported. When patched into `com.example.calc`, the test class and `Calculator` belong to the same module and the same package `com.example.calc.internal`.

## 4. Compiling the Main Module First

First, compile the main sources into an exploded module:

~~~bash
javac -d build/mods/com.example.calc \
    src/main/java/module-info.java \
    src/main/java/com/example/calc/api/CalculatorService.java \
    src/main/java/com/example/calc/internal/Calculator.java
~~~

After this command, the output directory looks like:

~~~text
build/mods/
└── com.example.calc/
    ├── module-info.class
    └── com/example/calc/
        ├── api/CalculatorService.class
        └── internal/Calculator.class
~~~

The path `build/mods` is the module path root. Inside it lies the exploded module `com.example.calc`.

## 5. Compiling Tests with javac --patch-module

If JUnit is placed on the classpath, tests can be compiled as follows:

~~~bash
javac \
    --module-path build/mods \
    --patch-module com.example.calc=src/test/java \
    --add-reads com.example.calc=ALL-UNNAMED \
    -cp libs/junit-platform-console-standalone.jar \
    -d build/test-classes \
    src/test/java/com/example/calc/internal/CalculatorTest.java
~~~

Explanation of each option:

1. `--module-path build/mods` helps the compiler find the named module `com.example.calc`.
2. `--patch-module com.example.calc=src/test/java` places test sources into the `com.example.calc` module for this compilation pass.
3. `--add-reads com.example.calc=ALL-UNNAMED` allows the target module to read types on the classpath, including JUnit.
4. `-cp` provides the JUnit APIs imported by the test sources.
5. `-d build/test-classes` places the compiled test classes into a separate output directory.
6. The final path is the source file being compiled.

`ALL-UNNAMED` is the readability target for classes belonging to the unnamed module. If the test framework is placed on the module path and has a module name, use that module name instead of `ALL-UNNAMED`.

Important point: the test class is compiled as part of `com.example.calc`, even though the `.class` file is written to `build/test-classes`. As a result, it can access the package-private `Calculator` in the same package.

## 6. Patching the Module When Running Tests

`--patch-module` in the `javac` command only takes effect for that compilation pass. It does not automatically make test classes members of the module when the JVM runs.

When running tests, you need to patch the directory containing compiled test classes into the same module:

~~~bash
java \
    --module-path build/mods \
    --patch-module com.example.calc=build/test-classes \
    --add-reads com.example.calc=ALL-UNNAMED \
    --add-opens com.example.calc/com.example.calc.internal=ALL-UNNAMED \
    -cp libs/junit-platform-console-standalone.jar \
    org.junit.platform.console.ConsoleLauncher execute \
    --select-class com.example.calc.internal.CalculatorTest
~~~

In the runtime command:

- `--patch-module` places the compiled test classes into the target module.
- `--add-reads` lets the target module read JUnit on the classpath.
- `--add-opens` opens the internal package to code on the classpath so the test framework can access it via reflection when needed.
- `--select-class` tells JUnit to run the specific test class.

`--add-opens` serves reflective access at runtime. It does not replace `--add-reads` when the compiler needs to read JUnit types. If the test framework is in a named module, replace `ALL-UNNAMED` with the appropriate module name and configure the required permissions for that module.

## 7. Configuration in Gradle

With the Gradle Java Plugin, you can pass compiler arguments to `compileTestJava`. The following example assumes the main module is `com.example.calc`, tests use JUnit on the classpath, and Gradle has detected the main output as a named module:

~~~groovy
plugins {
    id 'java'
}

java {
    modularity.inferModulePath = true
}

tasks.named('compileTestJava', JavaCompile) {
    options.compilerArgs.addAll([
        '--patch-module',
        'com.example.calc=' + sourceSets.test.java.srcDirs.asPath,
        '--add-reads',
        'com.example.calc=ALL-UNNAMED'
    ])
}
~~~

Here:

- `sourceSets.test.java.srcDirs.asPath` gathers all test source roots and joins them with the OS-appropriate path separator.
- `compileTestJava` still uses Gradle's dependency configurations to locate JUnit.
- `--patch-module` adjusts the module membership of test sources when the compiler processes them.

You also need to configure the test task's runtime so test classes are patched into the module when the JVM starts:

~~~groovy
tasks.named('test', Test) {
    jvmArgs(
        '--patch-module',
        'com.example.calc=' + sourceSets.test.output.classesDirs.asPath,
        '--add-reads',
        'com.example.calc=ALL-UNNAMED',
        '--add-opens',
        'com.example.calc/com.example.calc.internal=ALL-UNNAMED'
    )
}
~~~

The output paths in the example are illustrative for a simple project. If the build has multiple source sets, multiple output directories, custom test tasks, or JUnit running on the module path, adjust the module name and paths to match the actual configuration. Also check that test outputs are not loaded simultaneously in two ways that cause conflicts between the module path and classpath.

## 8. When Should --patch-module Be Used?

Common scenarios:

- Tests need to access package-private classes or methods inside a module.
- Tests need to be placed in the same package as the implementation, while that package is not exported.
- The build has separate test sources that need to be compiled as an extension of the main module.
- You need to add classes/resources to experiment with a module in a specific run.

Do not use `--patch-module` as a substitute for API design. If a package needs to be used regularly by external applications, consider designing a proper public API. When only internal tests need access to the implementation, module patching is a focused testing mechanism.

Also distinguish `--patch-module` from `--add-exports`. `--add-exports` alters package accessibility across module boundaries; `--patch-module` places content directly inside the target module. For tests in the same package and same module, patching the module is generally more appropriate than exporting internal packages solely so tests can access them.

## 9. Common Errors and How to Handle Them

| Symptom | Common Cause | Where to Check |
|---|---|---|
| `module not found` | Target module not found on the module path | Check `--module-path` and the module name |
| `package ... is not visible` when importing JUnit | Target module does not yet read the unnamed module or JUnit module | Add `--add-reads` with the proper target |
| Test cannot access package-private member | Test has not been patched into the right module or package | Check the module name and package declaration |
| Test compiles but class is not found at runtime | Patched only at `javac`, not patched when running the JVM | Add runtime `--patch-module` pointing to test output |
| Framework cannot access test via reflection | Package has not been opened to the module containing the framework | Use appropriate `--add-opens` at runtime |
| Unexpected provider or class is found | Patch path or module path contains multiple versions of a class | Check paths and module loading order |

When diagnosing, inspect the actual command line that the build tool passes to the compiler and JVM. Gradle/Maven configurations may add module paths or classpaths automatically, so looking only at a snippet of `build.gradle` does not necessarily reflect the full execution command.

## 10. Summary

`javac --patch-module` allows compiling additional sources as part of an existing named module. In modular Java testing, this technique keeps tests in the same module and package as the implementation, enabling testing of package-private code without exporting internal packages.

A modular test setup typically needs three things: placing the main module on `--module-path`, patching test sources into the module with `--patch-module`, and configuring readability to the test library with `--add-reads` if the library is on the classpath. When running tests, patch the test output directory into the module again and open packages to the framework if it requires reflection.

References:

- [javac — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [java launcher — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
