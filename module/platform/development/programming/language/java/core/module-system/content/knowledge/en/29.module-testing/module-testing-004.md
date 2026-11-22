# JUnit on the Module Path

When a Java application uses the Java Platform Module System (JPMS), running unit tests with JUnit requires attention to more factors than the traditional classpath approach: **named modules**, `requires`, `exports`, `opens`, class loaders, and how the JUnit Platform discovers test engines. A test that runs fine on the classpath may fail to compile or fail to be discovered when the same bytecode is moved onto the module path.

The core point: **JUnit is a reflection-based framework**, whereas JPMS enforces access boundaries between modules. To test effectively while preserving production code encapsulation, you need to clearly choose one of two strategies: **tests in an independent named module** or **tests patched into the module under test**.

This lesson covers source layout, relevant JUnit modules, a JUnit Jupiter test example, Maven/Gradle configuration, running the JUnit Platform Console, and handling common errors.

## 1. Why Is JUnit on the Module Path Different from the Classpath?

On a standard classpath, test sources can import the JUnit API and another class without a module descriptor:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class BasicTest {
    @Test
    void addition() {
        assertEquals(5, 2 + 3);
    }
}
```

Classes on the classpath belong to the corresponding class loader's unnamed module. The build tool prepares JUnit dependencies, discovers the tests, and executes them via the JUnit Platform.

With named modules, Java also has to answer these questions:

1. Does the module containing the tests **read** the `org.junit.jupiter.api` module?
2. Does the module containing the tests read the **production module** under test?
3. Is the production API package `exports`ed to the test module?
4. Is the package containing test classes/methods `opens`ed to the module performing reflection?
5. Has the JUnit Jupiter **TestEngine** been resolved into the module graph?
6. Does the JUnit Platform launcher locate and select the right test classes?
7. Do test classes placed in the same package as production classes cause a split package when placed in a separate test module?

These issues stem from module boundaries, not from any change in JUnit assertions.

## 2. JUnit Components to Distinguish

JUnit 5 organizes its runtime into **JUnit Platform**, **JUnit Jupiter**, and **JUnit Vintage**. In a JPMS environment, the corresponding artifacts may be identified by different module names:

| Component | Common Module Name | Role |
|---|---|---|
| JUnit Jupiter API | `org.junit.jupiter.api` | `@Test`, lifecycle annotations, assertions |
| JUnit Jupiter Engine | `org.junit.jupiter.engine` | Discovers and executes Jupiter tests |
| JUnit Platform Commons | `org.junit.platform.commons` | Internal utilities for engines and reflection |
| JUnit Platform Engine | `org.junit.platform.engine` | TestEngine interface and discovery |
| JUnit Platform Launcher | `org.junit.platform.launcher` | Orchestrates test engines |
| JUnit Platform Console | `org.junit.platform.console` | Runs tests from the command line |
| JUnit Vintage Engine | `org.junit.vintage.engine` | Runs JUnit 3/4 tests via the Platform |

These are examples from the common JUnit module layout; your actual JUnit setup must have compatible artifacts. Verify a module name directly from the JAR in use:

```shell
jar --describe-module --file lib/junit-jupiter-api.jar
```

The file path here is illustrative. For a JAR with a version in its name, pass the actual file path.

**Jupiter API is not Jupiter Engine.** Code can compile because the API is present, yet the launcher cannot run tests if the engine is absent or unresolved. Conversely, having the engine in the `lib` directory does not guarantee the engine enters the configuration if the launch setup does not make it a root or a selected dependency/service provider.

## 3. Two Module Testing Models

### 3.1. Tests as a Separate Named Module

Example:

```text
com.example.math
      ↑
      │ requires
com.example.math.tests
      │
      └── requires org.junit.jupiter.api
```

The test module directly declares dependencies on the production module and the JUnit API. Tests use exported API packages, just like a normal client application.

Strengths:

- Verifies the public API contract from an external module's perspective.
- Test module has its own descriptor, making dependencies explicit.
- No need to alter or patch production module contents.
- Well suited for API tests and many integration tests.

Limitations:

- Cannot import non-exported internal packages.
- Cannot access package-private members of another module.
- Test packages still need to be opened for JUnit reflection when required.
- Module path and discovery configuration must be complete.

### 3.2. Tests Patched into the Production Module

With `--patch-module`, the compiler and runtime treat certain test classes as additions to the production module. This is useful when unit tests need access to package-private code in the same package.

Strengths:

- Preserves an internal unit-testing model similar to traditional classpath tests.
- Can access package-private members in the same module/package.
- Avoids exporting implementation packages just for testing.

Limitations:

- Needs extra readability to JUnit granted for the test step via `--add-reads`.
- Reflection may require `--add-opens`.
- Must ensure test patches are used only in test configurations and never packaged into production JARs.

The two strategies are not mutually exclusive: a project can patch unit tests and run API/integration tests in a separate test module.

## 4. Production Module Example

Suppose there is a `com.example.math` module with an exported API package:

```text
src/main/java/
├── module-info.java
└── com/example/math/api/
    └── Calculator.java
```

Descriptor:

```java
module com.example.math {
    exports com.example.math.api;
}
```

Class:

```java
package com.example.math.api;

public final class Calculator {
    public int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public int divide(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("Divisor must not be zero");
        }
        return a / b;
    }
}
```

Because the API package is exported, other modules can use the public class `Calculator` if they have readability to `com.example.math`.

To test behavior strictly through the public contract, use a separate test module. If you need to test a non-exported class `com.example.math.internal.MathHelper`, consider patching tests into the same module instead of exposing the entire implementation externally.

## 5. Approach A: Independent Named Test Module

An illustrative source layout:

```text
project/
├── src/main/java/
│   ├── module-info.java
│   └── com/example/math/api/Calculator.java
└── src/test-modules/
    └── com.example.math.tests/
        ├── module-info.java
        └── com/example/math/tests/CalculatorTest.java
```

Test module descriptor:

```java
module com.example.math.tests {
    requires com.example.math;
    requires org.junit.jupiter.api;

    opens com.example.math.tests to org.junit.platform.commons;
}
```

Explanation:

- `requires com.example.math` lets tests read the production module.
- `requires org.junit.jupiter.api` provides annotations and Assertions.
- `opens com.example.math.tests to org.junit.platform.commons` allows reflection in JUnit Platform to access non-public test classes/methods as needed.

If extensions or other frameworks need reflection, you may need to open the package to those modules as well. Identify the reflecting module from the stack trace instead of unnecessarily opening the entire module.

Test:

```java
package com.example.math.tests;

import com.example.math.api.Calculator;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {
    private final Calculator calculator = new Calculator();

    @Test
    void addReturnsSum() {
        assertEquals(9, calculator.add(4, 5));
    }

    @Test
    void divisionRejectsZero() {
        assertThrows(
            IllegalArgumentException.class,
            () -> calculator.divide(10, 0)
        );
    }
}
```

JUnit Jupiter normally allows non-public test classes and test methods. However, reflective access across a named module boundary must still satisfy `opens` or runtime flags.

## 6. Compiling the Production Module and Test Module

An illustrative command sequence on Linux/macOS (adjust paths and shell syntax on Windows):

Compile the production module:

```shell
javac -d out/main     src/main/java/module-info.java     src/main/java/com/example/math/api/Calculator.java
```

Package into a modular JAR:

```shell
mkdir -p mods
jar --create --file mods/com.example.math.jar -C out/main .
```

Assume `lib` contains the JUnit JARs and compatible dependencies. Compile the test module:

```shell
javac --module-path "mods:lib"     -d out/test/com.example.math.tests     src/test-modules/com.example.math.tests/module-info.java     src/test-modules/com.example.math.tests/com/example/math/tests/CalculatorTest.java
```

After compilation, `out/test/com.example.math.tests` is an exploded named module containing `module-info.class` and the test classes. It can be used as a module path entry.

Notes:

- `--module-path` differs from `--class-path`. For module paths, use directories containing modular JARs or explicit JAR paths; do not assume `lib/*` acts like a classpath wildcard.
- On Windows, entries in a path list are separated by `;`, not `:`.
- Do not include the test module in a production image just because tests need it.
- If the test module depends on other modules, they must be found in the runtime image or on the appropriate module path.

## 7. Running a Named Test Module with JUnit Platform Console

One way to run directly with the JUnit Platform Console (on versions supporting the `execute` subcommand) is:

```shell
java --module-path "mods:lib:out/test/com.example.math.tests"     --add-modules com.example.math.tests,org.junit.jupiter.engine     --module org.junit.platform.console/org.junit.platform.console.ConsoleLauncher     execute --select-module com.example.math.tests
```

Explanation:

1. `mods` contains the production module.
2. `lib` contains JUnit Platform, Jupiter Engine, and compatible dependencies.
3. `out/test/com.example.math.tests` is the exploded test module.
4. `--add-modules` ensures the test module and Jupiter Engine are included in the graph.
5. `--module` launches ConsoleLauncher.
6. `--select-module` instructs JUnit Platform to select the target test module.

ConsoleLauncher syntax varies across versions. Check help for your installed version:

```shell
java --module-path "lib"     -m org.junit.platform.console/org.junit.platform.console.ConsoleLauncher     --help
```

On versions with the `execute` subcommand, you can inspect help for that subcommand specifically. Do not assume one command-line fragment works for every JUnit release.

JUnit Platform discovers `TestEngine` implementations via the service provider mechanism. If the Engine JAR is present somewhere yet the module is not resolved, the launcher may fail to find Jupiter Engine. Therefore, when running manually on the module path, check both the root module set and service binding.

## 8. Approach B: Tests in the Same Module via --patch-module

Suppose the production module also has an implementation package:

```text
src/main/java/
└── com/example/math/internal/MathHelper.java

src/test/java/
└── com/example/math/internal/MathHelperTest.java
```

Internal class:

```java
package com.example.math.internal;

final class MathHelper {
    static int square(int value) {
        return value * value;
    }
}
```

Unit test in the same package:

```java
package com.example.math.internal;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MathHelperTest {
    @Test
    void computesSquare() {
        assertEquals(36, MathHelper.square(6));
    }
}
```

If tests are compiled into another module, package `com.example.math.internal` is not exported and class `MathHelper` is not public, so the test cannot access it directly.

Under the `--patch-module` model, the test class is placed into the same named module `com.example.math`. Tests in the same package can then use package-private classes/methods just like in a normal compilation unit.

## 9. Compiling Tests with --patch-module and --add-reads

Assuming the production module is compiled and `mods` holds its modular JAR:

```shell
javac --module-path "mods:lib"     --add-modules org.junit.jupiter.api     --patch-module com.example.math=src/test/java     --add-reads com.example.math=org.junit.jupiter.api     -d out/test-patch     src/test/java/com/example/math/internal/MathHelperTest.java
```

Flags:

- `--patch-module`: tells the compiler to treat test sources as additions to the production module.
- `--add-modules`: ensures the JUnit API module participates in the compilation graph.
- `--add-reads`: allows `com.example.math` to read `org.junit.jupiter.api` solely for this test compilation configuration.
- `-d`: directory storing the compiled test class files.

Why is `--add-reads` required? Because the production module descriptor does not contain:

```java
requires org.junit.jupiter.api;
```

And that is normal. JUnit is a test dependency, not part of the production module's contract. Editing the production descriptor to add JUnit just to compile tests is usually not the right solution.

Some build tools generate equivalent flags automatically when they detect a modular test project. If invoking javac manually, keep compiler and runtime flags consistent.

## 10. Running Patch Tests with JUnit Platform

At runtime, compiled test classes need to be patched into the production module. At the same time, the production module must read the JUnit API and the package containing tests must allow reflection.

Illustrative command:

```shell
java --module-path "mods:lib"     --patch-module com.example.math=out/test-patch     --add-modules com.example.math,org.junit.jupiter.api,org.junit.jupiter.engine     --add-reads com.example.math=org.junit.jupiter.api     --add-opens com.example.math/com.example.math.internal=org.junit.platform.commons     --module org.junit.platform.console/org.junit.platform.console.ConsoleLauncher     execute --select-package com.example.math.internal
```

Explanation:

- Test classes are patched into `com.example.math`.
- `--add-reads` grants test-only readability to the JUnit API.
- `--add-opens` opens the test package to the reflection component.
- `--add-modules` adds the test runtime modules that must be resolved.
- JUnit Platform Console selects the test package to run.

With some ConsoleLauncher versions or test discovery strategies, a different way of selecting the test module or test classes may be required. Actual flags and documentation must match your JUnit version.

**Do not place test-only `--patch-module`, `--add-reads`, and `--add-opens` flags into production startup commands**. Those options belong strictly to the test runtime.

## 11. When Do You Need requires, add-reads, and add-modules?

These three mechanisms solve different problems.

### requires in module-info.java

```java
module com.example.math.tests {
    requires com.example.math;
    requires org.junit.jupiter.api;
}
```

This is a static dependency of a separate named test module. It is used by the compiler and resolver to establish readability.

### --add-reads

```text
--add-reads com.example.math=org.junit.jupiter.api
```

Adds a readability edge for a single compile/run invocation without modifying the module descriptor. Common in patch tests.

### --add-modules

```text
--add-modules org.junit.jupiter.engine
```

Adds a root module to be selected during resolution. It does not arbitrarily create readability between modules and does not export packages.

If the JUnit API module is already on the module path yet the test module does not read it, adding `--add-modules` will not necessarily fix import errors. If the test module has the right `requires` yet the API module is not found, fix the module path or dependency artifact first.

## 12. When Do You Need opens and add-opens?

JUnit Jupiter typically executes tests via reflection. The package containing test classes must permit reflection to the module where JUnit Platform makes the reflective call.

For a separate test module:

```java
module com.example.math.tests {
    requires com.example.math;
    requires org.junit.jupiter.api;
    opens com.example.math.tests to org.junit.platform.commons;
}
```

For patch tests:

```text
--add-opens com.example.math/com.example.math.internal=org.junit.platform.commons
```

Key distinction:

- `exports`: opens standard Java API access to public types.
- `opens`: allows deep reflection within a package.
- `--add-exports`: grants public type access to a specific module.
- `--add-opens`: grants deep reflection access at runtime.

An exported package does not automatically allow JUnit to access private/package-private test methods via reflection. Conversely, opening a package for reflection does not mean external code can import all internal types as a public API.

If a reflection error comes from another library — such as Mockito, an ORM, a JSON serializer, or a Jupiter extension — the target module of `opens` may differ from `org.junit.platform.commons`. Inspect the stack trace and actual module name to choose the right scope.

## 13. Maven Surefire with Named Modules

The Maven Surefire Plugin supports running tests in JPMS projects. Example POM configuring JUnit Jupiter in test scope:

```xml
<dependencies>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
  </dependency>
</dependencies>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.2</version>
      <configuration>
        <useModulePath>true</useModulePath>
      </configuration>
    </plugin>
  </plugins>
</build>
```

The versions above are real examples, not mandatory requirements. Choose JUnit/JDK/Surefire versions compatible with your project toolchain and align JUnit artifacts within the same release train.

Run:

```shell
mvn test
```

To inspect the full command line, classpath/module path, and Surefire flags:

```shell
mvn -X test
```

When tests are not discovered or hit module access errors, check:

1. Does Maven recognize the production `module-info.java`?
2. Are test classes patched into the production module or run on the classpath?
3. Are the JUnit API and Engine in the right positions on the test runtime?
4. Does Maven generate any `--patch-module`, `--add-reads`, or `--add-opens` flags?
5. Do Maven's JDK version and the test-execution JDK match?

Do not move the JUnit dependency to compile scope just to work around errors. JUnit should normally remain a test dependency.

## 14. Gradle and useJUnitPlatform()

In Gradle Groovy DSL, an illustrative configuration:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

java {
    modularity.inferModulePath = true
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Components:

- `testImplementation` holds the API and dependencies for compiling tests.
- `testRuntimeOnly` adds runtime components needed by the build.
- `modularity.inferModulePath` lets Gradle infer the module path when a module descriptor is detected.
- `useJUnitPlatform()` executes tests via the JUnit Platform.

Run:

```shell
./gradlew test
```

On Windows, use `gradlew.bat test` if using the Gradle Wrapper.

Not every Gradle version or plugin automatically configures the same module-patching strategy. If your test source set is organized as a separate named test module, you may need dedicated module source path, compilation task, and test runtime configuration. Inspect the actual command generated by Gradle when troubleshooting.

## 15. JUnit 4, Vintage, and Migration

An older codebase may contain both:

```java
import org.junit.Test;                  // JUnit 4
```

and:

```java
import org.junit.jupiter.api.Test;      // JUnit Jupiter
```

These two annotations belong to two different test frameworks. The JUnit Platform can run JUnit 4 tests via the **Vintage Engine** when the corresponding dependency is supplied, yet merely adding the Jupiter API does not turn JUnit 4 tests into Jupiter tests.

When inventorying tests before migration, record:

- Counts of JUnit 4 and Jupiter tests.
- Whether the JUnit Vintage Engine or custom runners are used.
- Whether extensions, rules, or integrated test frameworks like Spring Test are present.
- Which dependencies belong to test compile-time vs. test runtime.
- Which modules need opens for reflection.
- Whether any test suite needs the classpath instead of the module path during transition.

A practical roadmap can keep a group of legacy tests on the classpath while new tests are written as named modules, provided CI is clearly configured to avoid "disappearing tests" from test reports.

## 16. Checking Module Names of JUnit Dependencies

Do not guess module names solely from filenames or Maven artifact IDs. Inspect each artifact with:

```shell
jar --describe-module --file lib/junit-jupiter-api.jar
jar --describe-module --file lib/junit-jupiter-engine.jar
```

Replace paths with actual filenames. You can list modules observable by the launcher:

```shell
java --module-path "mods:lib" --list-modules
```

However, `--list-modules` does not prove every module will be resolved during a test run. To inspect resolution, use:

```shell
java --show-module-resolution     --module-path "mods:lib:out/test/com.example.math.tests"     --add-modules com.example.math.tests,org.junit.jupiter.engine     -m org.junit.platform.console/org.junit.platform.console.ConsoleLauncher     execute --select-module com.example.math.tests
```

When an engine is not discovered, check both service provider declarations and module resolution. Test discovery is a separate phase after the launcher starts successfully.

## 17. Error: Module Does Not Read JUnit API

A typical error:

```text
module com.example.math does not read org.junit.jupiter.api
```

The usual cause is that test classes are patched into the production module, yet the production module lacks readability to the JUnit API.

How to handle:

- Identify which module the test is actually running in.
- If the test is a separate named module, add `requires org.junit.jupiter.api;` to the test module descriptor.
- If the test is patched into the production module, use `--add-reads com.example.math=org.junit.jupiter.api` in test compile and runtime configuration as needed.
- Ensure the JUnit API artifact is on the module path and resolved.
- Do not add JUnit to the production descriptor if it is not a genuine runtime/contract dependency of the product.

If the compiler reports `package org.junit.jupiter.api is not visible`, check both the module path and readability. `--add-opens` cannot fix a missing requires.

## 18. InaccessibleObjectException During JUnit Reflection

A runtime error might look like:

```text
java.lang.reflect.InaccessibleObjectException:
module com.example.math does not "opens com.example.math.internal"
to module org.junit.platform.commons
```

This situation is not directly about a missing JUnit API. The test class may have been found, yet JUnit cannot use reflection to invoke the test method.

How to fix:

1. For a separate test module, `opens` the test package to the module performing reflection.
2. For patch tests, add `--add-opens` with the exact module/package/target at runtime.
3. Check whether the exception comes from JUnit Platform, Mockito, a DI framework, or another extension.
4. Restrict opens to necessary packages; avoid making the whole production module an `open module` just for one test.

If tests must access private fields of a JDK module, consider redesigning the test to rely on public APIs. Do not broadly open JDK internals in default pipelines.

## 19. Error: No Tests Found

When the launcher runs yet discovers no tests, you may see:

```text
No tests found
```

Possible causes:

- Test classes were not compiled, or were compiled into a directory outside the patch/module path.
- The test module was not resolved.
- Jupiter Engine is missing at runtime or not discovered by JUnit Platform.
- The selector points to the wrong package/module/class.
- Tests use JUnit 4 annotations while only Jupiter Engine is present.
- Build tool include/exclude patterns filter out the tests from discovery.
- The test suite uses a launcher version incompatible with the passed flags.

Steps to try:

1. Check that `.class` files were generated.
2. Check module names and the module path.
3. Select a specific test class instead of scanning the entire runtime.
4. Check the JUnit Engine provider.
5. Enable build tool/launcher logs to inspect discovery.
6. Check module `opens` if discovery sees the class yet cannot invoke methods.

Do not simply dump every JAR onto the classpath to "make it run" and conclude the module path is configured properly. That changes the runtime model under test.

## 20. Split Packages Between Tests and Production

A JPMS-specific error occurs when a separate test module contains the same package as the production module:

```text
com.example.math
└── com.example.math.internal

com.example.math.tests
└── com.example.math.internal
```

From the module perspective, the same package name exists in two named modules. Depending on readability, exports, and class loader strategy, this configuration may be rejected or cause issues.

If you want an independent test module, place tests in a dedicated package such as:

```text
com.example.math.tests
```

and test only the API exported by the production module. If you want tests in the same package to access package-private members, use `--patch-module` instead of creating a second named test module owning the same package.

Changing the module name does not resolve a split package; you must change the package layout or how the test module is defined.

## 21. Resources and Test Fixtures on the Module Path

Beyond Java classes, tests may need:

- JSON/YAML/XML fixtures.
- SQL seed files.
- Properties and logging configuration.
- Service provider metadata.
- Test extensions discovered via ServiceLoader.
- Resources loaded via `Class.getResourceAsStream`.
- Files looked up via the thread context class loader.

With JPMS, resource lookup can be affected by module encapsulation and class loaders. A resource existing on disk does not mean it is inside the module artifact or module patch used at runtime.

For patch tests, ensure `src/test/resources` or the resource output is included in the patch path per build configuration. For a separate test module, resources must reside inside the test module or be accessed via the appropriate path/classloader.

When a fixture is not found, do not immediately modify `opens`. Check:

1. Was the resource copied to the build output?
2. Which module is the resource placed in?
3. Does code use `Class.getResourceAsStream`, `Module.getResourceAsStream`, or a class loader?
4. Is the absolute/relative resource path correct?
5. Is the resource affected by encapsulation or package opening permissions?

## 22. JUnit and ServiceLoader on the Module Path

JUnit Platform uses the service provider mechanism to discover `TestEngine`s. This mirrors JPMS service binding in applications.

Example of a separate application using services:

```java
module com.example.app {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

Provider:

```java
module com.example.codec.json {
    requires com.example.codec.api;
    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

For tests to use a provider, the provider module must actually be present in the appropriate configuration/layer. Simply putting a JAR in a module path directory does not guarantee it becomes a resolved module.

For JUnit, also distinguish:

- Annotation/assertion API: JUnit Jupiter API.
- Engine module: supplies the TestEngine implementation.
- Launcher: requests engine discovery via the service mechanism.
- Module resolution: determines which modules are actually selected.
- Test discovery: determines which test classes are discovered in the runtime graph.

A successful build only confirms compilation. You cannot infer that JUnit Platform discovered the test engine and executed the entire test suite.

## 23. API Tests and Internal Unit Tests

These two test tiers generally have different goals:

### API/Integration Tests

Tests import only public types in exported packages. They act like a real consumer module:

```java
module com.example.math.tests {
    requires com.example.math;
    requires org.junit.jupiter.api;
    opens com.example.math.tests to org.junit.platform.commons;
}
```

This style catches issues that same-module tests can miss, such as forgetting `exports` on an API package or missing `requires` in a consumer module.

### Implementation Unit Tests

Tests need to verify package-private behaviors in the same package. They can be patched into the production module:

```text
--patch-module com.example.math=out/test-patch
```

This style is convenient for internal logic but does not completely replace API tests. Because tests run in the same module, they can access types that consumer modules cannot access.

When designing a test suite, keep both perspectives according to system complexity.

## 24. Migration Process from Classpath Tests

A migration plan can proceed step by step:

1. Inventory JUnit versions, runners, engines, and extensions currently in use.
2. Confirm the target JDK version and module names of JUnit artifacts.
3. Review descriptors and exported packages of production modules.
4. Classify tests: public API/integration vs. internal/package-private unit tests.
5. Create a named test module for tests verifying module boundaries.
6. Use patch-module for tests needing internal implementation access.
7. Keep JUnit dependencies in test scope.
8. Configure the minimal required readability and opens.
9. Configure the test engine and launcher on the right module path.
10. Run a small test, observe test discovery, then expand to the full suite.
11. Compare discovered test counts against the old classpath baseline.
12. Test identically on local machines, CI, and release environments.

During transition, some tests may still need to run on the classpath. What matters is making clear **which runtime model each test is verifying**; never equate classpath results with module path results.

## 25. Quick Diagnostic Table

| Symptom | Cause Category to Check |
|---|---|
| `module ... does not read org.junit.jupiter.api` | Missing `requires` or `--add-reads` |
| `package org.junit.jupiter.api is not visible` | JUnit API module path/readability |
| `module ... does not open package ...` | Missing `opens` or `--add-opens` |
| `InaccessibleObjectException` | Reflection across module boundary blocked |
| `Module ... not found` | Missing JAR, wrong module name, or module path |
| `No tests found` | Test output, selector, runtime test module, or engine |
| `TestEngine not found` | Engine dependency/module resolution/service discovery |
| `package ... is not visible` | Test module lacks read edge or production package not exported |
| `reads package ... from both ...` | Split package or two modules exporting the same package |
| Runs in IDE yet fails in CI | Different JDK, build tool, test runtime flags, or test selector |

Effective debugging classifies the error first: **compilation**, **module resolution**, **access/reflection**, or **test discovery**. Each error category has a different fix.

## 26. Modular JUnit Project Checklist

- [ ] Production `module-info.java` does not contain unnecessary JUnit dependencies.
- [ ] Test classes are built under a clear strategy.
- [ ] Named test module has `requires` on the production module and JUnit API.
- [ ] Patch tests have `--add-reads` for the right module/target.
- [ ] Packages containing tests are opened with minimal scope for reflection when needed.
- [ ] Compatible JUnit Jupiter Engine and JUnit Platform Launcher are present at runtime.
- [ ] Required modules are actually resolved.
- [ ] Test module does not accidentally create a split package with production.
- [ ] Test resources are copied and found under module configuration.
- [ ] Maven Surefire or Gradle `useJUnitPlatform()` is properly configured.
- [ ] Discovered test count matches expectations.
- [ ] CI uses matching JDK, JUnit, module path, and test flags as local runs.
- [ ] Broadened access flags are not carried into production launchers.

## Conclusion

JUnit on the module path requires coordinating three mechanisms: **dependency readability**, **package access for reflection**, and **test discovery via the JUnit Platform**. A separate named test module suits verifying public APIs; patching tests via `--patch-module` suits verifying package-private implementation within the same module.

`requires` and `--add-reads` let the test module read the JUnit API or production module; `opens` and `--add-opens` let the engine/framework access test classes via reflection; `--add-modules` and launcher configuration ensure required runtime modules are resolved. These options do not substitute for one another.

Keep JUnit in test scope, open only the packages actually needed, verify Jupiter Engine discovery, and test on the exact module path used by your build/CI. By choosing a deliberate test strategy, an application can benefit from JPMS encapsulation while maintaining a reliable JUnit test suite.