# Do Not Export Internal Packages Just for Tests

## 1. Why Should You Not Export Internal Packages for Tests?

In the Java Platform Module System (JPMS), the module descriptor determines which packages are exposed to other modules. The **exports** directive is part of the API contract: it allows consuming modules to access public types in the exported package, according to standard Java access rules.

For example:

    module com.example.billing {
        exports com.example.billing.api;
    }

The **com.example.billing.api** package is the API surface that the module actively exposes. Packages such as **com.example.billing.internal**, **com.example.billing.persistence**, or **com.example.billing.impl** remain inside the module if they are not exported.

A class with the public modifier does not automatically become an API accessible from every module. If the package containing the class is not exported, other modules cannot use that class via standard access merely because the class is declared public.

When writing unit tests, we sometimes want to access internal classes or methods to test algorithms, state, or error branches. Adding:

    exports com.example.billing.internal;

just to make tests compile turns the internal package into part of the module's accessible surface in every environment where that artifact is used. Library users may start depending on implementation details. Later, renaming packages, moving classes, or changing the internal structure becomes harder because doing so could break external code.

The design principle is: **only export a package because it is a supported API for consumers, never export it merely to make it easier for tests to access.**

## 2. What Does exports Actually Do?

The **exports** directive exposes a package to other modules. For example:

    module com.example.billing {
        exports com.example.billing.api;
        exports com.example.billing.spi
            to com.example.integration;
    }

There are two forms:

- **Unqualified export:** the package is exported to any module that reads the current module.
- **Qualified export:** the package is exported only to the modules listed after the **to** keyword.

A qualified export can be useful for an SPI or API intentionally shared with a specific group of modules. However, putting a test module name in the production descriptor just to let tests access internals still creates an exception in the module contract and is usually not the right choice.

Exporting does not automatically export subpackages. If a module exports **com.example.billing.api**, the **com.example.billing.api.internal** package remains a separate package and is not exported unless declared separately.

Exporting also does not bypass Java modifiers. An exported package does not turn private members into public ones. It only removes the JPMS package-level encapsulation barrier so that other modules can access the types and members already permitted by language rules.

## 3. Encapsulation Is the Module's Contract

A well-designed module usually has a small API surface and a larger implementation part kept private.

For example:

    module com.example.billing {
        requires java.sql;

        exports com.example.billing.api;
        uses com.example.billing.spi.PaymentGateway;
    }

Package structure:

    com.example.billing.api
      InvoiceService.java
      Invoice.java

    com.example.billing.spi
      PaymentGateway.java

    com.example.billing.internal
      InvoiceServiceImpl.java
      InvoiceValidator.java

    com.example.billing.persistence
      JdbcInvoiceRepository.java

Consumers only need to use **InvoiceService** and **Invoice**. The implementation, validator, and repository can change without affecting consumers if they are not exposed.

If internal packages are exported just for tests, the module has exposed more details than consumers need. That can lead to:

- Consumers depending on implementation classes instead of the API.
- Package refactoring or internal structural changes causing compatibility errors.
- The module losing control over extension points.
- Internal types being used with the wrong lifecycle or call order.
- Replacing the implementation with another approach becoming difficult.
- A larger API surface making documentation, versioning, and compatibility testing more complex.

Tests should help protect the module's contract. They should not accidentally expand that contract.

## 4. Prefer Testing Through the Public API

The first way to test should be calling the module from a consumer's perspective:

    InvoiceService service = BillingModule.createService();

    Invoice invoice = service.createInvoice(request);

    assertEquals(InvoiceStatus.CREATED, invoice.status());

This test verifies behavior that consumers actually observe. It can still check many business rules, data validity, error handling, and interactions among internal components without directly accessing the implementation.

A good way to organize this is to create consumer tests in a separate module:

    module com.example.billing.tests {
        requires com.example.billing;
        requires org.junit.jupiter.api;
    }

The tests only import types exported from **com.example.billing**. If a test fails to compile because it uses an internal package, review whether the test is verifying a supported contract or depending on implementation details.

Testing through the public API offers these benefits:

- Verifies the behavior used by real applications.
- Preserves the freedom to change the implementation.
- Detects integration bugs between the API and internal components.
- Requires no test-only exports.
- Makes tests more stable during refactoring.

Not every test has to be black-box. White-box tests are still useful for complex algorithms, but separate access boundaries should be configured for the test environment.

## 5. When White-Box Testing Is Needed, Grant Access in Test Configuration

JPMS provides compiler and launcher options to adjust access permissions for a specific run. They are useful when tests need access to an internal package without turning that package into part of the production artifact's API.

### Using --add-exports for Tests

If a test needs to reference public types in an internal package of a named module, **--add-exports** can be used.

Example module:

    module com.example.billing {
        exports com.example.billing.api;
    }

The test runs in the unnamed module and needs to access a public class in an internal package. When compiling the test, you can add:

    javac --module-path mods \
          --add-exports com.example.billing/com.example.billing.internal=ALL-UNNAMED \
          -cp junit-platform-console-standalone.jar \
          -d target/test-classes \
          src/test/java/com/example/billing/InvoiceValidatorTest.java

When running the test, pass the corresponding permission to the JVM:

    java --module-path mods \
         --add-exports com.example.billing/com.example.billing.internal=ALL-UNNAMED \
         -jar junit-platform-console-standalone.jar \
         execute --class-path target/test-classes \
         --select-class com.example.billing.InvoiceValidatorTest

The illustrative example uses JUnit Console and common build paths; depending on the JUnit version or build tool, how the classpath is passed and tests are selected may differ.

The **ALL-UNNAMED** target means the package is exported to unnamed modules. If the test resides in a named module, specify the exact test module name instead of ALL-UNNAMED.

**--add-exports** allows accessing public types in the specified package. It does not grant deep reflection access to private or package-private members.

### Using --add-opens When a Framework Needs Deep Reflection

Some test frameworks, dependency injection frameworks, or mocking frameworks use reflection to access non-public fields, constructors, or methods. In that case, **--add-exports** may not be enough.

Use **--add-opens** at runtime:

    java --module-path mods \
         --add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED \
         -jar junit-platform-console-standalone.jar \
         execute --class-path target/test-classes

This option opens the package for deep reflection from the specified target module. It does not turn internal types into a compile-time API for tests. If a test needs to directly reference a public type in an unexported package, an appropriate export mechanism is still needed at compile time.

**--add-opens** is a runtime launcher option. Do not use it in place of --add-exports when the compiler needs package access.

### Using Both When Tests Have Both Needs

A test might both import internal public types and require a framework to perform deep reflection. In that case, both options can be passed:

    java --module-path mods \
         --add-exports com.example.billing/com.example.billing.internal=ALL-UNNAMED \
         --add-opens com.example.billing/com.example.billing.internal=ALL-UNNAMED \
         -jar junit-platform-console-standalone.jar \
         execute --class-path target/test-classes

Grant access only for the specific package and the specific test target needed. Avoid opening the entire module or all packages to all modules if unnecessary.

## 6. Putting Tests into the Module Itself with --patch-module

Another approach is compiling and running tests as part of the module under test. Build tools can use **--patch-module** to add test classes into the target module in the test environment.

Conceptual example:

    javac --module-path mods \
          --patch-module com.example.billing=target/test-classes \
          -d target/test-classes \
          src/test/java/com/example/billing/internal/InvoiceValidatorTest.java

When running, the build tool configures the JVM to patch the test classes into the module:

    java --module-path mods \
         --patch-module com.example.billing=target/test-classes \
         --module com.example.billing/com.example.billing.test.TestLauncher

When test classes are placed into the target module, they belong to the same module boundary as the implementation and can access package-private members under standard Java rules. Actual configuration depends on how the build tool compiles tests, output locations, and how the test framework is brought into the module graph.

If the test framework resides in another module, the patched module may need additional readability to the framework. The build tool can configure **--add-reads** for the test runtime. These test configurations should not be placed into the production descriptor if they are not actual application dependencies.

**--patch-module** is useful for white-box testing, but should be restricted to test tasks. It is not a way to ship test classes or internal implementations in a release artifact.

## 7. Distinguishing exports and opens

These two directives are often confused when configuring tests:

| Mechanism | Purpose | Test Scenario |
|---|---|---|
| **exports package** | Allows other modules to access public types in the package | Test imports public types in the API |
| **opens package** | Allows deep reflection into the package | Framework needs to access non-public fields/methods/constructors |
| **--add-exports** | Adds an export in a specific compile/runtime configuration | Test references public types in an internal package |
| **--add-opens** | Adds an open at runtime | Test framework uses deep reflection |
| **--patch-module** | Adds content to the target module | Places test classes into the same module for white-box testing |

Example in the descriptor:

    module com.example.billing {
        exports com.example.billing.api;
        opens com.example.billing.persistence;
    }

The opens directive does not make a package a compile-time API. It primarily serves deep reflection. Conversely, exports does not automatically allow frameworks to access all private members.

If only tests need reflection, do not add unrestricted opens to the production module descriptor. Configure --add-opens in the test JVM so the open permission exists only during that test run.

## 8. Are Qualified Exports a Solution for Tests?

JPMS supports qualified exports:

    module com.example.billing {
        exports com.example.billing.internal
            to com.example.billing.tests;
    }

This limits access to the package to a specifically named module. It can make sense if a package is genuinely an SPI or internal API intentionally shared with another module.

However, if **com.example.billing.tests** is only a test module, a qualified export still puts the test module name into the production descriptor. The release artifact will carry a test-specific access exception, and renaming or splitting the test module can affect the descriptor.

Therefore, qualified exports should only be used when the relationship between two modules is an intentional part of the architecture. For test-only access, prefer compiler/launcher configuration or patching the module in the test task.

## 9. Organizing Packages and Tests to Avoid Split Packages

Another error occurs when tests are placed in the same package name yet compiled into a separate named module. For example, the production module contains:

    com.example.billing.internal.InvoiceValidator

and the separate test module also contains:

    com.example.billing.internal.InvoiceValidatorTest

If both modules own the **com.example.billing.internal** package, the configuration can run into split package issues. Having the same package name does not merge two packages belonging to two different modules into one.

Common ways to organize this:

- Place test classes in a separate test package and test through the public API.
- If package-private access is needed, configure test classes to be patched into the production module during the test runtime.
- Use a build tool with JPMS support to create test modules and configure reads/opens/patch appropriately.
- Do not create a test module just to export all internal packages of the production module.

Having the same package name only matters when classes are actually loaded within the appropriate runtime boundary. Splitting tests into an independent module does not automatically allow tests to access package-private members of the production module.

## 10. Complete Design Example

Suppose the billing module has an API and an implementation:

    module com.example.billing {
        requires java.sql;
        exports com.example.billing.api;
    }

    package com.example.billing.api;

    public interface InvoiceService {
        Invoice create(InvoiceRequest request);
    }

The implementation is kept in an unexported package:

    package com.example.billing.internal;

    final class InvoiceValidator {
        boolean isValid(InvoiceRequest request) {
            return request != null;
        }
    }

The consumer module only uses the API:

    module com.example.application {
        requires com.example.billing;
    }

Black-box tests call InvoiceService and verify the results without needing to know InvoiceValidator exists.

If the algorithm in InvoiceValidator has many complex branches and needs white-box testing, the test task configuration can patch the test class into com.example.billing or use --add-exports for the test module if the class to reference is public. If a framework needs to access private members, add --add-opens only in the test JVM.

The production module-info.java keeps the proper contract:

    module com.example.billing {
        requires java.sql;
        exports com.example.billing.api;
    }

As a result, consumers only see the supported API, while tests can still use specialized mechanisms in the testing environment.

## 11. Key Takeaways

- **exports** is the module's API contract; only export packages that consumers actually need.
- Do not export internal packages just so tests can access the implementation.
- An unexported package can still contain public classes, but other modules cannot use them through normal access.
- Prefer testing through the public API to protect the behavior observed by consumers.
- Use **--add-exports** in tests when referencing public types in internal packages is needed.
- Use **--add-opens** in the test runtime when frameworks need deep reflection.
- **--add-opens** does not replace the compile-time access permission of --add-exports.
- Use **--patch-module** when you need to place test classes into the same module to test package-private members or implementation details.
- Qualified exports are only appropriate when the access relationship is an intentional part of the architecture, not a shortcut for tests.
- Do not open an entire module to ALL-UNNAMED in production just to make a test framework work.
- Keep test-only options in the test configuration of Maven, Gradle, or the test launcher.
- Check package and module boundaries to avoid split packages when separating tests into a distinct module.

**A module should expose exactly what consumers need to use.** Tests may require deeper access, but that access should be granted in the test configuration and only for the specific package, module, and time needed.

## References

- Java Platform Module System — JEP 261: https://openjdk.org/jeps/261
- Java SE 21 Tool Specifications — javac: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Java SE 21 API — Module: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
