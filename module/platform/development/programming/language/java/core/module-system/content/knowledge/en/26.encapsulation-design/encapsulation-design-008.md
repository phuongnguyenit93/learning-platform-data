# Testing That a Module Does Not Expose Unintended APIs

In the Java Platform Module System (JPMS), **strong encapsulation** is not merely splitting source code into named modules. A good module design must clearly specify which packages are public API, which packages are reserved for implementation, and which frameworks (if any) are allowed to use deep reflection. Testing these boundaries prevents a change in **module-info.java**, a JAR packaging configuration, or a launch option from accidentally exposing classes that should remain hidden.

The goal of this lesson is to build repeatable tests that answer three questions:

1. **Compile-time:** Can an independent module import and use the public API while being rejected when importing an internal package?
2. **Runtime reflection:** Is code in another module blocked when attempting deep access to private fields, methods, or constructors of the target module?
3. **Module contract:** Do the descriptor and launch configuration match the approved list of **exports**, **opens**, and access exceptions?

Merely inspecting the directory structure or naming a package **internal** is not enough. Actual access boundaries are determined by the descriptor, module graph, Java access rules, and any additional runtime permissions granted.

## 1. What Does Exposing Unintended APIs Mean?

A named module can contain many packages, yet not every package should become an API for other modules. For example:

~~~text
com.acme.order
├── com.acme.order.api
├── com.acme.order.internal
├── com.acme.order.persistence
└── com.acme.order.spi
~~~

Suppose the design contract specifies:

- **com.acme.order.api**: public API for consuming applications.
- **com.acme.order.internal**: implementation details, neither exported nor opened.
- **com.acme.order.persistence**: internal entities, opened only to a specific ORM when reflection is genuinely required.
- **com.acme.order.spi**: extension contract, which can be qualified-exported if only a plugin module is allowed to use it.

Changes that can cause API exposure:

~~~java
module com.acme.order {
    exports com.acme.order.api;
    exports com.acme.order.internal; // Exposes implementation package
}
~~~

Or:

~~~java
open module com.acme.order {
    exports com.acme.order.api;
}
~~~

In the second example, all packages of the module are opened for deep reflection at runtime; this is far broader permission than exporting only the public API.

A modular JAR accidentally packaged as an **automatic module** can also lose its intended boundaries. Automatic modules have broad compatibility rules, exporting and opening all of their packages. Therefore, testing must not merely read package names: it must verify the module type and actual permissions.

## 2. Understanding requires, exports, and opens Precisely

Three groups of rules must be distinguished:

| Mechanism | What Is Permitted? | Can Be Tested With |
|---|---|---|
| **requires** and module readability | Calling module reads the target module. | Module graph and **Module.canRead(...)**. |
| **exports** | Other modules access public types/members in the package under Java rules. | Compile-time consumer test and **ModuleDescriptor.exports()**. |
| **opens** | Other modules perform deep reflection into the package at runtime. | **trySetAccessible()**, **Module.isOpen(...)**, **ModuleDescriptor.opens()**. |

Example of a descriptor with tight boundaries:

~~~java
module com.acme.order {
    exports com.acme.order.api;
}
~~~

Another module declares:

~~~java
module com.acme.client {
    requires com.acme.order;
}
~~~

Then the client can use the public API in **com.acme.order.api**. However, the client cannot import public types from **com.acme.order.internal** because that package is not exported.

Declaring a class **public** does not automatically turn it into a system-wide API. Public only addresses part of the Java rules; JPMS also checks module boundaries.

Conversely, if the module has:

~~~java
module com.acme.order {
    exports com.acme.order.api;
    opens com.acme.order.persistence to com.acme.orm;
}
~~~

The **persistence** package remains unexported for direct source-code imports, while **com.acme.orm** can perform deep reflection according to the granted permission. That can be an intentional design exception, not an unintended API leak.

## 3. Building Sample Modules to Test Encapsulation

The following example uses a business module and an independent test module. The key point is that tests must run **outside the module under test**.

Directory structure:

~~~text
src/
  com.acme.order/
    module-info.java
    com/acme/order/api/OrderApi.java
    com/acme/order/internal/OrderState.java
tests/
  com.acme.contract.test/
    module-info.java
    com/acme/contract/test/EncapsulationTest.java
negative-src/
  com.acme.contract.negative/
    module-info.java
    com/acme/contract/negative/IllegalImport.java
~~~

Business module descriptor:

~~~java
// src/com.acme.order/module-info.java
module com.acme.order {
    exports com.acme.order.api;
}
~~~

Implementation class:

~~~java
// src/com.acme.order/com/acme/order/internal/OrderState.java
package com.acme.order.internal;

public final class OrderState {
    private final String secret;

    public OrderState(String secret) {
        this.secret = secret;
    }
}
~~~

API class:

~~~java
// src/com.acme.order/com/acme/order/api/OrderApi.java
package com.acme.order.api;

import com.acme.order.internal.OrderState;

public final class OrderApi {
    private OrderApi() {
    }

    public static Object sampleState() {
        return new OrderState("INTERNAL-ONLY");
    }
}
~~~

Having **OrderApi** instantiate and use **OrderState** is valid: both packages belong to the same module. The **sampleState()** method intentionally returns **Object** so the test module gets a real instance without importing the internal type.

In real application design, the API should return a stable contract type rather than Object. Here Object only serves to illustrate reflection limits when the implementation package is not exported.

## 4. Testing Success with the Intentionally Exposed API

External test module:

~~~java
// tests/com.acme.contract.test/module-info.java
module com.acme.contract.test {
    requires com.acme.order;
}
~~~

A simple test:

~~~java
package com.acme.contract.test;

import com.acme.order.api.OrderApi;

public final class EncapsulationTest {
    public static void main(String[] args) throws Exception {
        Object state = OrderApi.sampleState();

        if (state == null) {
            throw new AssertionError("Public API is not working");
        }

        System.out.println("Public API accessible");
    }
}
~~~

Compile the business module:

~~~bash
javac -d mods --module-source-path src -m com.acme.order
~~~

Compile the test module:

~~~bash
javac -d testmods \
      --module-path mods \
      --module-source-path tests \
      -m com.acme.contract.test
~~~

Run on Linux/macOS:

~~~bash
java --module-path "mods:testmods" \
     -m com.acme.contract.test/com.acme.contract.test.EncapsulationTest
~~~

On Windows, multi-directory module paths use semicolons:

~~~powershell
java --module-path "mods;testmods" -m com.acme.contract.test/com.acme.contract.test.EncapsulationTest
~~~

This is a **positive test**: the intentionally exported API must compile and run successfully from an external module. A suite running only negative tests without positive tests will struggle to distinguish proper encapsulation from a configuration that breaks the entire API.

## 5. Negative Compile Test: Internal Package Must Not Be Importable

The strongest test for source-code access is actually using **javac** to compile a consuming module that attempts to import an internal package.

Descriptor of the negative test module:

~~~java
// negative-src/com.acme.contract.negative/module-info.java
module com.acme.contract.negative {
    requires com.acme.order;
}
~~~

Class attempting to use the implementation:

~~~java
// negative-src/com.acme.contract.negative/com/acme/contract/negative/IllegalImport.java
package com.acme.contract.negative;

import com.acme.order.internal.OrderState;

public final class IllegalImport {
    OrderState state = new OrderState("should-not-compile");
}
~~~

Compile this fixture separately:

~~~bash
javac -d negative-out \
      --module-path mods \
      --module-source-path negative-src \
      -m com.acme.contract.negative
~~~

When **com.acme.order** only exports the **api** package, the compiler is expected to reject the import of **com.acme.order.internal**. The message typically states that the package is not visible or is not exported to the caller module.

This is an **expected compilation failure**, not a bug in the lesson. In CI, check both conditions:

1. **javac** exits with a non-zero code.
2. The diagnostic accurately reflects **the internal package is not exported**; not a syntax error, missing JDK, missing module path, or nonexistent source file.

A negative test should not be marked passing simply because some compilation error occurred. If the fixture has broken syntax, the test no longer proves module encapsulation.

Bash example:

~~~bash
if javac -d negative-out --module-path mods \
         --module-source-path negative-src \
         -m com.acme.contract.negative; then
    echo "FAIL: internal package became importable"
    exit 1
else
    echo "Expected: javac rejected internal package"
fi
~~~

In a real pipeline, capture stderr and verify the appropriate diagnostic before accepting the negative test.

## 6. Negative Runtime Test: Do Not Open Private Fields to Callers

**javac** checks API importability, yet is not enough to prove the module disallows deep reflection. A runtime test placed in another module is needed.

Add to the test class:

~~~java
package com.acme.contract.test;

import com.acme.order.api.OrderApi;
import java.lang.reflect.Field;

public final class EncapsulationTest {
    public static void main(String[] args) throws Exception {
        Object state = OrderApi.sampleState();

        Class<?> internalClass = state.getClass();
        Module owner = internalClass.getModule();
        Module caller = EncapsulationTest.class.getModule();
        String pkg = internalClass.getPackageName();

        if (owner.isExported(pkg, caller)) {
            throw new AssertionError("Internal package was exported");
        }

        if (owner.isOpen(pkg, caller)) {
            throw new AssertionError("Internal package was opened");
        }

        Field secret = internalClass.getDeclaredField("secret");

        if (secret.trySetAccessible()) {
            throw new AssertionError(
                "Caller was able to deep-reflect into private field"
            );
        }

        System.out.println("Encapsulation preserved");
    }
}
~~~

This test checks three layers of signals:

- **isExported(pkg, caller)**: whether the package is accessible as a runtime API to the caller.
- **isOpen(pkg, caller)**: whether the package is open to the caller for deep reflection.
- **trySetAccessible()**: whether the caller can actually suppress access checks on the private field.

Obtaining a **Class<?>** or **Field** does not equate to permission to read or write the value. The goal of a negative runtime test is to verify that cross-boundary access **is disallowed**.

**Note:** A test placed inside **com.acme.order** will produce different results, because code in the same module has broader internal access than code in an external module. Make sure the test is compiled and run under the named module **com.acme.contract.test**.

## 7. Checking the Descriptor with an Allowlist

Compile tests verify specific cases. To avoid missing packages accidentally exported or opened, you can inspect the **ModuleDescriptor** of the artifact directly.

Example using **ModuleFinder**:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

public final class DescriptorContractTest {
    public static void main(String[] args) {
        ModuleDescriptor d = ModuleFinder
            .of(Path.of("mods"))
            .find("com.acme.order")
            .orElseThrow()
            .descriptor();

        if (d.isAutomatic() || d.isOpen()) {
            throw new AssertionError(
                "Module must be a non-open explicit module"
            );
        }

        Set<String> expectedExports = Set.of("com.acme.order.api");

        Set<String> actualExports = d.exports().stream()
            .filter(e -> !e.isQualified())
            .map(ModuleDescriptor.Exports::source)
            .collect(Collectors.toSet());

        if (!expectedExports.equals(actualExports)) {
            throw new AssertionError(
                "Exports do not match contract: " + actualExports
            );
        }

        if (d.exports().stream().anyMatch(
                ModuleDescriptor.Exports::isQualified)) {
            throw new AssertionError(
                "Unapproved qualified exports present"
            );
        }

        if (!d.opens().isEmpty()) {
            throw new AssertionError(
                "Module is opening packages for reflection"
            );
        }

        System.out.println("Module descriptor contract passed");
    }
}
~~~

This is an example for a policy where **only one package is exported and no packages are opened**. For modules with valid qualified exports/opens, replace absolute bans with an allowlist of package names and target module lists.

Because **ModuleDescriptor** is immutable and reflects the module's metadata, reading it does not require loading business classes. You can inspect the JAR directly after building, instead of inspecting only the source descriptor.

### Why Must Both Automatic and Open Modules Be Checked?

If a library is packaged incorrectly and loses **module-info.class**, a JAR placed on the module path can become an automatic module. An automatic module has broad export/open semantics, even if synthesized directive sets differ from the exports you wrote in source.

Similarly, an **open module** opens every package at runtime. Therefore, just checking the number of **opens** entries is not always enough; both **isOpen()** and **isAutomatic()** must be checked.

## 8. Qualified Exports and Qualified Opens Need Dedicated Tests

Sometimes a system needs to grant a specific module access to a package not meant for the general public:

~~~java
module com.acme.order {
    exports com.acme.order.api;
    exports com.acme.order.spi to com.acme.plugin.host;
    opens com.acme.order.persistence to com.acme.orm;
}
~~~

In this case:

- **api** is exported to every module reading the order module.
- **spi** is exported only to **com.acme.plugin.host**.
- **persistence** is opened only to **com.acme.orm**.

The descriptor test must compare both the package and the targets:

~~~java
for (ModuleDescriptor.Exports e : d.exports()) {
    System.out.println(
        e.source() + " -> " + e.targets()
    );
}

for (ModuleDescriptor.Opens o : d.opens()) {
    System.out.println(
        o.source() + " -> " + o.targets()
    );
}
~~~

For an unqualified directive, the **targets()** set is empty; for a qualified directive, this set contains target module names. Distinguish the two cases using **isQualified()**, rather than inferring that an empty set means "no permission".

A useful testing policy is to explicitly declare the list:

~~~text
unqualified exports:
  com.acme.order.api

qualified exports:
  com.acme.order.spi -> com.acme.plugin.host

qualified opens:
  com.acme.order.persistence -> com.acme.orm

other exports/opens:
  forbidden
~~~

Then compare the actual descriptor against this contract. That way, an accidental change from a qualified export to an unqualified export is caught, even though the package name stays the same.

## 9. Runtime Testing in the Right Caller Module

Export or open permissions can depend on the caller. A test that only calls:

~~~java
targetModule.isOpen("com.acme.order.persistence")
~~~

does not express the same full semantics as checking whether the package is open to a specific module:

~~~java
targetModule.isOpen(
    "com.acme.order.persistence",
    ormModule
)
~~~

Similarly, for qualified exports:

~~~java
targetModule.isExported(
    "com.acme.order.spi",
    pluginModule
)
~~~

Create test modules corresponding to each important consumer role: a regular application, a permitted plugin, a permitted ORM framework, and a non-permitted module.

A test for **com.acme.orm** proves the ORM has the required permission, yet does not prove **com.acme.untrusted** is blocked. For sensitive packages, both positive and negative tests matching the policy are needed.

One more detail: runtime checks can reflect access changes applied after startup, whereas **ModuleDescriptor** reflects the original metadata. Therefore, descriptor checks and runtime behavior checks complement rather than replace each other.

## 10. Avoiding Letting JVM Options Mask Test Results

The following options can alter module boundaries at runtime:

~~~text
--add-exports source.module/package=target.module
--add-opens source.module/package=target.module
--add-reads source.module=target.module
~~~

For example:

~~~bash
java --add-opens com.acme.order/com.acme.order.internal=ALL-UNNAMED \
     -p "mods:testmods" \
     -m com.acme.contract.test/com.acme.contract.test.EncapsulationTest
~~~

The command above opens the package to unnamed modules, not necessarily to the named test module. If the goal is to test boundaries between named modules, verify the exact target of each flag.

A configuration like the following will directly cause a negative reflection test to fail:

~~~bash
java --add-opens com.acme.order/com.acme.order.internal=com.acme.contract.test \
     -p "mods:testmods" \
     -m com.acme.contract.test/com.acme.contract.test.EncapsulationTest
~~~

Because the flag granted permission to the test module, **trySetAccessible()** can succeed. This is not a random JVM bug, but the exact result of the requested configuration.

When running contract tests:

1. Use clear, reproducible Java commands.
2. Check **VM options** passed by the IDE, Maven, Gradle, or CI.
3. Avoid permission-widening flags if they are not part of the test contract.
4. Check **--patch-module** or other module-related options that may alter how tests run.
5. Record the JDK version and module kind (named/unnamed/automatic) to interpret results.

In particular, many test frameworks use reflection. If the test runner already grants **--add-opens** to the module under test, a negative reflection test may no longer reflect the production configuration you want to protect. You can run a standalone test JVM with a dedicated test module for cleaner evidence.

## 11. Do Not Confuse Encapsulation with Inability to Inspect Metadata

Even when a package is not exported, certain reflection APIs can still return class names or member metadata. For example:

~~~java
Class<?> type = state.getClass();

System.out.println(type.getName());
System.out.println(type.getDeclaredFields().length);
~~~

Seeing the type name or knowing the class has fields does not prove the caller can read, write, or invoke those members. Blocking access operations is different from completely hiding every trace of metadata.

A misguided test often checks only that:

~~~java
state.getClass().getDeclaredFields().length == 0
~~~

and concludes "the module is encapsulated". This inference is incorrect; **getDeclaredFields()** can discover declarations without granting deep access.

Instead, check:

- Can an internal import compile?
- Is the package exported/opened to the caller?
- Can **trySetAccessible()** or **setAccessible(true)** perform deep reflection?
- Can the approved public API be called?

These results map directly to the JPMS contract that needs protection.

## 12. Service Providers Do Not Need to Export the Implementation Package

JPMS supports service binding:

~~~java
module com.acme.order {
    exports com.acme.order.api;

    provides com.acme.order.api.OrderPlugin
        with com.acme.order.internal.DefaultOrderPlugin;
}
~~~

In this case, the **internal** package can remain neither exported nor opened. **ServiceLoader** is allowed to locate the provider via the **provides ... with ...** declaration, yet that does not mean every module can import or deep-reflect into the implementation.

Do not treat ServiceLoader discovering a provider as evidence that the implementation package leaked API. The service contract is published through the service type and module descriptor, while the concrete implementation can stay hidden.

Conversely, if a consumer uses the provider class directly instead of the service interface, you may have accidentally created a dependency on the implementation. Contract tests should prefer using the public service type and checking that the implementation package remains unexported.

## 13. Analyzing the Final JAR, Not Just module-info.java in Source

In a build pipeline, the final artifact can differ from what developers see in the source tree. A packaging plugin, build profile, or shading step can drop the descriptor or change the JAR structure.

After creating the JAR:

~~~bash
jar --create \
    --file dist/com.acme.order.jar \
    -C mods/com.acme.order .
~~~

Inspect the actual descriptor:

~~~bash
jar --describe-module \
    --file dist/com.acme.order.jar
~~~

Inspect the archive contents:

~~~bash
jar --list --file dist/com.acme.order.jar
~~~

Confirm:

- **module-info.class** is present in the expected modular JAR.
- The module name is exact and stable.
- No exports or opens appear outside the allowlist.
- Implementation packages do not become exported packages merely due to artifact changes.
- The JAR does not accidentally turn into an automatic module.

You can use **jdeps** to find static dependencies of the JAR:

~~~bash
jdeps --summary dist/com.acme.order.jar
~~~

However, **jdeps** does not replace descriptor checks and negative tests. A valid static dependency does not prove packages are properly protected; conversely, Java reflection can create runtime relationships that static analysis does not fully see.

## 14. Public API Is Not Always Stable API

JPMS protects boundaries at the package level. An exported package can contain multiple public types, yet not every public type should become a long-term contract.

Example package:

~~~text
com.acme.order.api
  OrderService.java
  OrderRequest.java
  ExperimentalOrderDebug.java
~~~

If **com.acme.order.api** is exported, the public type **ExperimentalOrderDebug** is also accessible to other modules. JPMS has no directive to export individual classes separately.

Therefore, if there are public implementations that should not become API:

- Move the class to an unexported package if reasonable.
- Reduce the access modifier when the design allows.
- Separate the stable API from implementation or experimental packages.
- Use API surface checking tools to detect changes to public types/methods in exported packages.

JPMS tests help enforce package boundaries, while compatibility testing of the public API may require additional public signature analysis tools. Do not assume that "exporting only one package" is enough for every class inside that package to be well-designed.

## 15. Integrating Module Boundary Tests into CI

A pipeline can consist of the following steps:

~~~text
1. Compile source module
2. Package modular JAR
3. Inspect ModuleDescriptor of the final JAR
4. Compile positive consumer test: must succeed
5. Compile negative consumer test: must fail for the right reason
6. Run negative reflection test: must be blocked
7. Run positive service/framework test if qualified opens exist
8. Save logs and results along with JDK version
~~~

Expected results:

| Test | Correct Result |
|---|---|
| Import exported public API | Compilation succeeds. |
| Import unexported internal package | Compilation fails because the module does not export the package. |
| Deep reflection from non-permitted module | **trySetAccessible()** returns false or **setAccessible(true)** is blocked. |
| Deep reflection from permitted framework | Can work if policy permits and caller is the right module. |
| Descriptor exports/opens allowlist | Matches exactly. |
| Final artifact is not an open/automatic module | Condition confirmed. |
| Run without extra-contract VM flags | No unexpected permissions granted. |

If one of the negative tests starts passing after upgrading a dependency or editing a descriptor, that is a signal to review: an internal package may have just been unintentionally exported/opened.

If a positive test fails, the API contract may have been narrowed too aggressively. Both directions are important for a stable module encapsulation contract.

## 16. Common Testing Mistakes

| Symptom | Possible Cause | Fix |
|---|---|---|
| Negative compile test fails because module is not found | Fixture module path is wrong. | Fix the path before concluding encapsulation passed. |
| Reflection negative test passes unexpectedly | Test runs in the same module, package is opened, or --add-opens is present. | Move test into a separate named module; inspect descriptor and VM options. |
| Descriptor test allows automatic module | Only counting exports/opens without checking module kind. | Check **isAutomatic()** and **isOpen()**. |
| Test checks only package names, not targets | Qualified exports/opens are treated as public. | Compare both **isQualified()** and **targets()**. |
| Test runs on classpath instead of module path | Many expected named-module boundaries are lost. | Run the fixture as a named module. |
| Internal package contains public types in an exported package | Every public type of the package is accessible. | Move implementations to an unexported package. |
| VM options differ between CI and production | Test produces unrepresentative results. | Synchronize configuration; isolate tests without exception flags. |
| No positive API test exists | Valid API could be closed off without detection. | Add a positive consumer test. |

## 17. Encapsulation Protection Checklist

- The module is packaged as an **explicit named module**.
- The module has not unintentionally become an **automatic module** or **open module**.
- Only approved API packages have unqualified exports.
- Qualified exports/opens are granted only to valid target modules.
- Internal/implementation packages are not unintentionally exported or opened.
- Consumer tests belong to a different named module, not inside the source module.
- Positive compile tests can use the valid API.
- Negative compile tests are rejected due to the proper export rule.
- Negative runtime tests confirm deep reflection is disallowed for callers outside the allowlist.
- The descriptor in the final JAR matches the policy; do not inspect source alone.
- VM options such as **--add-exports** and **--add-opens** are controlled and do not invalidate tests.
- CI reruns contract tests after changing descriptors, JDK, or build configuration.

**Testing that a module does not expose unintended APIs means testing an access contract**, not merely checking package names or counting public classes. Combine three layers of evidence: **negative compile tests**, **runtime reflection tests**, and a **ModuleDescriptor allowlist** on the packaged artifact. This approach catches both cases where the public API is accidentally expanded and cases where frameworks or JVM options relax reflection permissions beyond design intent.
