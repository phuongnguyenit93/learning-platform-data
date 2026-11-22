# Do Not Open the Entire Production Module Just to Make Testing Easier

When writing tests for an application using the Java Platform Module System (JPMS), a common temptation is changing `module com.example.orders` to `open module com.example.orders` so JUnit, Mockito, or test frameworks can reflect into any class, constructor, or field. That can get some tests running faster, yet it **weakens the encapsulation boundary of the entire production module**.

Core principle: **permissions needed only for testing should be granted in test configuration**, not automatically turned into the production program's access contract. Check the test's goal first, then choose the right approach: test via the public API, patch tests into the module, open a scoped package to the framework, or extract an intentional test-support API.

## 1. Why Does JPMS Change Testing?

In traditional Java, most classes sit on the classpath and belong to their class loader's unnamed module. Test frameworks frequently use reflection to:

- Locate `@Test` classes and instantiate them.
- Invoke non-public test methods.
- Read/write fields in test fixtures.
- Call private constructors or methods via `setAccessible(true)`.
- Create mocks, proxies, or inject dependencies.

When production code becomes a **named module**, packages have access rules governed by the module descriptor. Alongside `public`, `protected`, package-private, and `private` modifiers, JPMS adds:

- **Readability:** which modules may read another module, usually declared with `requires`.
- **Exports:** which packages allow other modules to use public types in standard Java code.
- **Opens:** which packages allow other modules to perform deep reflection.

Therefore, tests may see a class on the module path yet still be unable to access the package or member needed. This is intentional JPMS encapsulation behavior, not a reason to open the entire production module.

## 2. Differences Between exports, opens, and open module

Suppose the initial production module is:

    module com.example.orders {
        exports com.example.orders.api;
    }

Packages:

    com.example.orders.api
    com.example.orders.internal
    com.example.orders.persistence

External modules can import public types in `com.example.orders.api`, yet are not automatically permitted to import types in `internal` or `persistence`.

Three mechanisms are frequently confused:

| Mechanism | Meaning | Effect |
|---|---|---|
| `exports p;` | Allows other modules to access public types in package p | Standard Java access |
| `opens p;` | Opens package p for deep reflection from other modules | Runtime reflection access |
| `opens p to m;` | Opens package p exclusively to module m | Target-scoped reflection |
| `open module X { ... }` | Opens all packages of module X for deep reflection | Very broad reflection permission |

`open module` **does not automatically export all packages for direct imports**. However, it allows other modules to perform deep reflection into every package in the module, including packages intended as implementation details.

An example not to apply just for test convenience:

    open module com.example.orders {
        exports com.example.orders.api;
    }

This configuration exposes `api`, `internal`, and `persistence` to deep reflection, even when tests may only need access to one field on one class.

## 3. Risks of Opening the Entire Production Module

Switching to `open module` affects every run of the packaged module, not just tests.

Consequences:

1. **Expanded reflection surface:** code in other modules can request deep access to more internal packages than intended.
2. **Blurred architectural contracts:** which packages are implementation details vs. reflection contracts is no longer clear.
3. **Fragile dependencies:** frameworks or tests may start relying on private fields/constructors that change easily.
4. **Masked configuration issues:** a test that should require test-scoped `--add-opens` no longer exposes the real access boundary.
5. **Undermines JPMS migration goals:** module descriptors exist to express dependency boundaries, not merely to pass compilation.

This does not mean every `open module` is wrong. A module deliberately designed for broad reflection, such as certain data-model modules backing frameworks, may need it. However, **convenience for an isolated test is not proof that production needs every package opened**.

## 4. Prefer Testing Behavior Through the Public API

If the goal is to verify a module's behavior, start with the exported API.

Example production module:

    module com.example.orders {
        exports com.example.orders.api;
    }

API:

    package com.example.orders.api;

    public final class OrderService {
        public int total(int price, int quantity) {
            if (price < 0 || quantity < 0) {
                throw new IllegalArgumentException();
            }
            return price * quantity;
        }
    }

A JUnit test may simply be:

    package com.example.orders.tests;

    import com.example.orders.api.OrderService;
    import org.junit.jupiter.api.Test;

    import static org.junit.jupiter.api.Assertions.assertEquals;
    import static org.junit.jupiter.api.Assertions.assertThrows;

    class OrderServiceTest {
        @Test
        void calculatesTotal() {
            assertEquals(150, new OrderService().total(50, 3));
        }

        @Test
        void rejectsNegativeQuantity() {
            assertThrows(IllegalArgumentException.class,
                () -> new OrderService().total(50, -1));
        }
    }

The test targets the externally observable contract. It does not need to know which internal class performs multiplication or which private field holds a cache.

If tests live in a separate named module, the test module needs readability to the production module, and the test framework may need reflection access to the package containing the test class. These requirements can be met via **test configuration**, not by opening every production package.

## 5. Separate Test Module to Verify API Boundaries

A clean JPMS-aligned testing approach places API tests in a separate named module.

Production descriptor:

    module com.example.orders {
        exports com.example.orders.api;
    }

Illustrative descriptor for a test module:

    module com.example.orders.contract.tests {
        requires com.example.orders;
        requires org.junit.jupiter.api;
        opens com.example.orders.contract.tests
            to org.junit.platform.commons;
    }

Tests import only exported API packages. This lets the test suite act like an **independent client** and verify module boundaries.

Module names and package opening needs for JUnit depend on the JUnit/test launcher version in use; `org.junit.platform.commons` is an example of a component that may perform reflection. Use the `InaccessibleObjectException` message or actual launcher configuration to identify the target.

A separate test module generally suits contract tests or integration tests. It does not need to become part of the production artifact.

## 6. When Tests Need Package-Private Access: Use Proper Test Patching

Some unit tests are designed to exercise a package-private algorithm inside a module rather than going solely through the public API.

For example, production has a class:

    package com.example.orders.internal;

    final class OrderRules {
        static boolean validQuantity(int quantity) {
            return quantity > 0;
        }
    }

Test in the same package:

    package com.example.orders.internal;

    import org.junit.jupiter.api.Test;

    import static org.junit.jupiter.api.Assertions.assertFalse;
    import static org.junit.jupiter.api.Assertions.assertTrue;

    class OrderRulesTest {
        @Test
        void validatesQuantity() {
            assertTrue(OrderRules.validQuantity(3));
            assertFalse(OrderRules.validQuantity(0));
        }
    }

Merely placing the test class in the same package name in a different JAR **does not guarantee** package-private access. In JPMS, two classes with the same package name in different runtime modules or class loaders do not necessarily belong to the same runtime package.

The `--patch-module` mechanism injects compiled test classes into a named module in the test environment:

    --patch-module com.example.orders=build/test-classes

When patched properly, the test class is treated as part of module `com.example.orders`. However, if test code uses a JUnit API in another module or on the classpath, the patched production module may still need corresponding readability edges.

Key point: `--patch-module` is an option for **test JVM/compile tasks**, not a reason to package test classes into the production JAR.

## 7. --patch-module Does Not Automatically Solve Every Access Permission

Distinguish the problem each option solves:

    --patch-module
    --add-reads
    --add-exports
    --add-opens

| Option | Role |
|---|---|
| `--patch-module X=path` | Adds or replaces class/resource content in module X in the configured environment |
| `--add-reads X=Y` | Adds an edge where module X reads Y |
| `--add-exports X/p=Y` | Grants Y access to public types in package p of X |
| `--add-opens X/p=Y` | Opens package p of X to Y for deep reflection |

For example, test classes are patched into `com.example.orders` while the JUnit API resides on the classpath. For test code to read JUnit types in the unnamed module, compile/test configuration may need:

    --add-reads=com.example.orders=ALL-UNNAMED

If the test framework on the classpath also needs reflection on non-public test methods in `com.example.orders.internal`, the test JVM may need:

    --add-opens=com.example.orders/com.example.orders.internal=ALL-UNNAMED

These flags make sense only if JUnit is actually in the unnamed module. If the framework is in a named module, the target must be the framework's actual module name.

Do not copy all flags into the production launcher. Compiling tests and running tests may also need different configurations, so place flags in the right phase.

## 8. When Deep Reflection Is Needed, Open Just One Package in the Test JVM

Suppose a framework uses reflection to read a private field on an internal class:

    package com.example.orders.internal;

    public final class OrderState {
        private String status = "NEW";
    }

A test/framework runs:

    Field field = OrderState.class.getDeclaredField("status");
    field.setAccessible(true);

With a named module, if the package is not opened to the caller, `setAccessible(true)` can throw:

    java.lang.reflect.InaccessibleObjectException

If the framework runs on the classpath in the test JVM, you can configure:

    --add-opens=com.example.orders/com.example.orders.internal=ALL-UNNAMED

If the framework runs in named module `com.example.test.framework`, use:

    --add-opens=com.example.orders/com.example.orders.internal=com.example.test.framework

This opens only **one package** of **one source module** to **the exact target**. It does not affect other packages in the production module.

You can use `trySetAccessible()` to test whether access can be enabled without relying on exceptions when blocked by module access:

    if (field.trySetAccessible()) {
        Object value = field.get(state);
        System.out.println(value);
    } else {
        System.out.println("Reflection not permitted");
    }

If you only need to call a public method, check `requires` and `exports` rather than using `--add-opens` as a blanket fix for every access error.

## 9. Place Flags in the Right Place: Test JVM, Not Production JVM

A project can involve multiple JVMs:

- Production application JVM.
- JVM running unit tests.
- JVM running integration tests.
- IDE test runner JVM.
- JVMs spawned by Maven Surefire/Failsafe or Gradle Test.
- JVMs executing other build tools.

When a test needs `--add-opens`, the flag must go to **the JVM actually running the test framework**. Putting it in the production launch command does not pass it to the test JVM.

With Maven Surefire, an illustrative configuration:

    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <argLine>
          --add-opens=com.example.orders/com.example.orders.internal=ALL-UNNAMED
        </argLine>
      </configuration>
    </plugin>

If using JaCoCo or another tool that already sets `argLine`, merge arguments instead of overwriting prior settings. `ALL-UNNAMED` is valid only when the test framework's reflecting code runs in the unnamed module.

With the Gradle Java plugin:

    tasks.withType(Test).configureEach {
        jvmArgs(
            '--add-opens=com.example.orders/com.example.orders.internal=ALL-UNNAMED'
        )
    }

Depending on source sets and Gradle/JUnit configuration, a different target module may be required. Configuration should reflect whether JUnit is actually loaded from the classpath or module path.

## 10. Use Production module-info to Describe Production Needs

If a framework genuinely needs reflection **when the application runs in production**, opening the package in the descriptor can be the right design.

Example:

    module com.example.orders {
        exports com.example.orders.api;

        opens com.example.orders.persistence
            to com.example.orm;
    }

A module holding entities requiring ORM mapping can deliberately open the persistence package to the ORM module. That is an intentional production contract.

Conversely, a `com.example.orders.internal` package that only needs opening for JUnit during tests should not be added to the production descriptor:

    opens com.example.orders.internal;

just to make tests shorter.

A clear rule of thumb: **If all tests were deleted from the project, would production still need that reflection permission?** If not, consider placing the permission in test configuration instead of the production module descriptor.

Qualified opens in the descriptor remains an active permission in the production artifact; it does not become test-only merely because the receiving module's name contains `test`.

## 11. Do Not Export Internals Just to Make Test Imports Easy

Another way to bypass test boundaries is adding:

    exports com.example.orders.internal;

This publishes the internal package as an API accessible from other modules, provided readability and Java access modifiers are met.

Over-exporting creates long-term coupling: other modules may start using internal classes. Refactoring data structures, renaming packages, or removing classes will then break code depending on what was never designed as a public API.

Better options include:

- Testing behavior through exported API packages.
- Testing package-private implementation via `--patch-module` in the test environment.
- Opening selectively for test framework reflection via test VM options.
- Extracting genuinely reusable algorithms into a deliberately designed public API/package.
- Extracting a separate test-support package if the project has a clear architectural reason.

Do not create a production `export` just because the test runner has not been configured properly.

## 12. JUnit and Test Discovery: Finding Tests Differs from Permission to Invoke Tests

JUnit Platform is responsible for discovering and running tests. Discovery may see a test class, yet reflecting to call a non-public constructor or test method must still obey JPMS.

For example, an error may state:

    module com.example.orders does not "opens
    com.example.orders.internal" to module org.junit.platform.commons

In this situation, the target needing permission is the module actually performing reflection, such as `org.junit.platform.commons`, not necessarily the main application module.

Targeted configuration:

    --add-opens=com.example.orders/com.example.orders.internal=org.junit.platform.commons

Treat this strictly as an example: the project's target module name must come from stack traces, error messages, and how JUnit is loaded. Another setup might use the unnamed module or a different JUnit component.

When a test runner discovers no tests, the cause may also be source sets, the test engine, or the module path rather than missing `opens`. Do not add reflection flags before identifying the exact failing stage.

## 13. Checking Package Openness with the Module API

You can query whether a package is currently open to another module at runtime:

    Module source = OrderService.class.getModule();
    Module target = MyTestFramework.class.getModule();

    boolean openForTarget = source.isOpen(
        "com.example.orders.internal",
        target
    );

    System.out.println(openForTarget);

When running with the right VM options, the result can be `true`. If the package is not yet open to the actual target, the result can be `false`.

Note the distinction:

    source.isExported("com.example.orders.api", target);
    source.isOpen("com.example.orders.internal", target);

The first check concerns public API access; the second concerns deep reflection.

This API is useful for diagnosing test/module layer environments, though `isOpen` results should not be used as an excuse to automatically open more production packages. Permission configuration still needs clear scope and intent.

## 14. Maven and Gradle: Separating Test-Scoped Workarounds

In Maven, compiler plugin, Surefire/Failsafe, and runtime launcher configurations can differ. Paths to inspect separately:

- Compiling production module: compiler module path and descriptor.
- Compiling tests: test classpath/module path, patching mechanism if used.
- Running unit tests: Surefire/JUnit VM options.
- Running integration tests: Failsafe or dedicated runner.
- Running production: launcher free of test-only overrides.

In Gradle, `JavaCompile` and `Test` are separate tasks. Configurations for `test` and `integrationTest` (if custom-defined) may differ. A flag added to `test.jvmArgs` does not automatically apply to every JVM or custom task.

A maintainable configuration practice is using a shared helper or convention plugin for **test tasks that genuinely require reflection**, rather than putting every flag into system-wide `JAVA_TOOL_OPTIONS`.

If a project maintains both classpath and module path builds during migration, ensure tests reflect the target production configuration. Tests passing on the classpath do not prove production JPMS boundaries are right.

## 15. Testing Module Boundaries as a Contract

Beyond unit tests, maintain a test suite that verifies module boundaries hold.

Examples of conditions to verify:

1. Module `com.example.orders` exports the exact `com.example.orders.api` package.
2. Packages `internal` and `persistence` are not broadly exported unnecessarily.
3. Packages not needing production reflection are not opened in the descriptor.
4. Client modules using only the public API run cleanly on the module path.
5. Test-specific flags do not appear in production launch commands.
6. Provider modules and service discovery (if any) resolve properly without opening the entire module.

You can inspect a modular JAR's descriptor:

    jar --describe-module --file orders.jar

In Java code, read the descriptor:

    ModuleDescriptor descriptor =
        OrderService.class.getModule().getDescriptor();

    System.out.println(descriptor.exports());
    System.out.println(descriptor.opens());

This is an example of late-stage architectural testing. Authoring a module with a small, clear descriptor makes boundary checks meaningful in themselves.

## 16. Decision Workflow When a Test Hits an Access Error

When encountering `IllegalAccessException`, `InaccessibleObjectException`, or package visibility errors, proceed in order:

**Step 1 — Identify the error.**

- If `package ... is not visible` at compile time: check `requires`, readability, `exports`.
- If `InaccessibleObjectException` on `setAccessible(true)`: check `opens` for the caller module.
- If `IllegalAccessException` when invoking/accessing fields via reflection: check access modifiers, reflection type, and module access.
- If `module not found`: fix the module path first instead of arbitrarily opening packages.

**Step 2 — Determine the test scope.**

Is the test checking public API, package-private implementation, or framework reflection behavior?

**Step 3 — Choose the narrowest solution.**

- Public API test: use designed exports.
- Same module/package test: consider `--patch-module`.
- Framework needing private reflection in tests: `--add-opens` for the exact package and target.
- Production framework genuinely needing reflection: design scoped `opens` for production needs.

**Step 4 — Put permissions in the right place.**

Use test compile/runtime flags when only tests need them; avoid writing broad changes into production descriptors.

**Step 5 — Re-run in the target environment.**

Confirm the test runtime actually receives the flags; read any subsequent message if another error appears. Do not assume all errors share the same root cause.

## 17. Comparing Approaches

| Option | Production Encapsulation | Test Support | When Appropriate |
|---|---|---|---|
| Test via public API | Preserved | Good for public behavior | Default preference |
| Separate test module | Preserves API boundaries | Good for contract/integration | Want to test as external client |
| `--patch-module` in tests | Production descriptor unchanged | Can test package-private | Unit tests needing same module/package |
| Test-scoped `--add-opens` | Production artifact unchanged | Permits package/target deep reflection | JUnit, mock/serialization frameworks needing reflection |
| `opens p to m` in descriptor | Opens one package at production runtime | Can assist tests | Genuine production reflection need exists |
| `open module` | Opens all packages | Can make tests easy to run | Only when whole module is intentionally designed for broad reflection |

Choose a solution based on the module's public contract and actual reflection risk, not solely on whichever option silences the error fastest.

## 18. Common Misconceptions

- **Assuming `open module` only opens packages to JUnit.** It opens every package in the module for deep reflection at runtime.
- **Assuming an `exports`ed package allows reading private fields.** Deep reflection requires appropriate package openness.
- **Assuming placing a test in the same package name suffices to call package-private code.** Runtime module and class loader matter; `--patch-module` may be needed.
- **Assuming `--patch-module` automatically adds readability to the test framework.** `--add-reads` may still be needed when a module is patched and the framework sits outside that module.
- **Assuming `ALL-UNNAMED` means all named modules.** It applies only to unnamed modules.
- **Assuming `--add-opens` fixes missing dependencies.** It does not supply missing classes, JARs, or modules.
- **Assuming modifying the production module descriptor is the only way to make tests run.** Test runners and VM options can grant test-scoped permissions.
- **Assuming tests passing on the classpath prove the production module path is right.** These are two different organization and access-control mechanisms.
- **Assuming all test permissions should become production permissions.** Tests have special privileges for internal observation; production does not necessarily need them.

## Key Takeaways

- Never turn a production module into an `open module` just for testing convenience.
- Default to testing behavior through **exported APIs**.
- If package-private implementation must be tested, consider **test-only `--patch-module`**.
- If a test framework needs deep reflection, use **`--add-opens` scoped to the exact package and target** on the test JVM.
- If a production framework genuinely needs reflection, express that permission with `opens` aligned to the module design.
- Distinguish `exports` (public API), `opens` (reflection), `--add-reads` (readability), and `--patch-module` (test classes in module).
- Keep production artifacts and production launch commands free of test-only permissions.

A good test suite makes a module reliable **without weakening production boundaries**. Controlling permissions by test scope and exact package/module preserves both testability and JPMS encapsulation benefits.