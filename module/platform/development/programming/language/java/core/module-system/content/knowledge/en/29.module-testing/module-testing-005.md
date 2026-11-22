# Reflection Testing When Packages Are Closed in the Java Module System

When applying the Java Platform Module System (JPMS), a package may contain a public class yet still **not be exported** to other modules. Even if a package is exported, private fields or constructors in that package are not automatically opened for deep reflection. Therefore, a reflection test suite needs to verify both sides: **which accesses must be denied** and **which accesses are intentionally opened so a framework or module can operate**.

This is an important form of testing when migrating an application from the classpath to the module path. Tests that previously ran in the unnamed module or were merged into the module under test may have different access than an actual consumer running in an independent named module. If tests only check the happy path, or if the test runner passes --add-opens automatically to avoid errors, an overly broad configuration can exist undetected.

This lesson guides designing tests for closed packages, distinguishing exports from opens, using the Java reflection API, setting up two independent modules to verify boundaries, and handling test runner flags that could skew results.

## 1. Three Access Layers to Distinguish

In JPMS, there are at least three independent questions:

1. **Does one module read the other?** This relationship is typically established by requires in module-info.java.
2. **Is the package exported to the consumer?** Only with appropriate exports can ordinary Java code from the consumer access public types in that package.
3. **Is the package opened to the reflecting caller?** When deep reflection into private members is needed, the package must be opened to the caller's module under JPMS rules.

Example:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Package com.example.domain.api is the public API. Package com.example.domain.model, if it exists, is neither exported nor opened by the descriptor above.

This has the following consequences:

- Another module might observe a class name via certain reflection APIs, yet that does not mean it can invoke constructors, methods, or access fields on that class.
- Returning metadata from Class.getDeclaredField or Class.getDeclaredMethod does not imply permission to bypass access checks.
- An exported package does not mean private fields in the package are opened for deep reflection.
- Even when a package is opened, consumer source code importing a class from that package still requires appropriate exports.

Tests should separate these behaviors instead of lumping them into a single assertion that "reflection works".

## 2. Goals of Reflection Tests

A meaningful test suite should guard the following contracts:

| Scenario | Expectation |
| --- | --- |
| Consumer reads module yet package is not exported | Normal Java access is blocked |
| Consumer obtains metadata of private field in closed package | Must not bypass access checks |
| Caller in another module calls trySetAccessible on private field | Returns false if package is not open to caller |
| Caller in another module calls setAccessible(true) without permission | Throws InaccessibleObjectException |
| Package is opened via opens ... to for the right consumer | That consumer can perform appropriate deep reflection |
| Another consumer not listed in qualified opens | Still denied deep reflection |
| Package only has exports | Public API is accessible yet private members are not opened by default |
| Test runs only inside the package-owning module | Do not use that result to claim external modules are blocked |

Accurate tests must run under a module graph, module descriptors, and JVM arguments close to the real configuration.

## 3. Fixture: One Domain Module and One External Test Module

To reproduce JPMS boundaries, create two real named modules:

~~~text
reflection-demo/
└── src/
    ├── com.example.domain/
    │   ├── module-info.java
    │   └── com/example/domain/model/Customer.java
    └── com.example.probe/
        ├── module-info.java
        └── com/example/probe/ReflectionProbe.java
~~~

Domain module:

~~~java
// src/com.example.domain/module-info.java
module com.example.domain {
}
~~~

Model class:

~~~java
// src/com.example.domain/com/example/domain/model/Customer.java
package com.example.domain.model;

public final class Customer {
    private final String secret = "internal-only";

    public Customer() {
    }

    public String publicName() {
        return "customer";
    }
}
~~~

Probe module:

~~~java
// src/com.example.probe/module-info.java
module com.example.probe {
    requires com.example.domain;
}
~~~

With the descriptors above, the probe module **reads** domain, yet package com.example.domain.model remains **closed** to probe: it is neither exported nor opened.

This is an intentional fixture for testing permission denial. Do not use the default package and do not place the probe class inside the domain module itself, because the goal is to test a cross-module caller.

## 4. Negative Test with trySetAccessible

Create a test class running from the probe module:

~~~java
package com.example.probe;

import java.lang.reflect.Field;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field secret = type.getDeclaredField("secret");

        boolean accessible = secret.trySetAccessible();

        if (accessible) {
            throw new AssertionError(
                "Closed package unexpectedly allowed deep reflection"
            );
        }

        System.out.println("PASS: deep reflection denied");
    }
}
~~~

Key points:

- Class.forName looks up the class by binary name; the class name is written as a string to avoid importing a non-exported package.
- getDeclaredField retrieves metadata for the field named secret.
- trySetAccessible attempts to bypass Java language access checks with current reflection permissions.
- When probe is a different named module and domain.model is not open to probe, trySetAccessible returns false.
- If it returns true, the test fails and you must find out why the package was opened by a descriptor, JVM arguments, or another runtime adjustment.

This test neither instantiates Customer nor reads the field value. Thus it cleanly isolates the reflection permission check without depending on constructors or business data.

Compile both modules:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.domain,com.example.probe
~~~

Run on the module path:

~~~bash
java --module-path mods \
     -m com.example.probe/com.example.probe.ReflectionProbe
~~~

When no open permissions have been added, expect:

~~~text
PASS: deep reflection denied
~~~

This is a negative test: passing means permission was denied, not that the framework read the field.

## 5. Negative Test with setAccessible(true)

If you want to verify the exact exception type, replace the trySetAccessible call with:

~~~java
package com.example.probe;

import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field secret = type.getDeclaredField("secret");

        try {
            secret.setAccessible(true);
            throw new AssertionError(
                "Expected JPMS to reject private-field access"
            );
        } catch (InaccessibleObjectException expected) {
            System.out.println("PASS: inaccessible package rejected");
        }
    }
}
~~~

**setAccessible(true)** requests privilege escalation for reflection, whereas **trySetAccessible()** returns a boolean result when permission is not granted.

Do not catch every RuntimeException or Exception and let the test pass, because that can mask other errors such as class not found, a renamed field, or broken test code.

A good test separates looking up the class/field from requesting access so that on failure you know immediately whether the issue is the class name, bytecode, module graph, or encapsulation.

## 6. Why Can Class.forName Find a Class Even When the Package Is Closed?

JPMS distinguishes **the ability to locate and load a class** from **permission to access types and members**. In many modular configurations, Class.forName can load a class by name even if its package has not been exported or opened to the caller. That operation alone does not grant permission to invoke private members.

Therefore, the following sequence is not contradictory:

~~~text
Class.forName("...Customer")          -> may succeed
getDeclaredField("secret")           -> may succeed
trySetAccessible()                   -> false
setAccessible(true)                  -> InaccessibleObjectException
~~~

A common mistake is seeing a non-null Class<?> returned and concluding the package is open. The true conclusion can only be drawn by testing the access permission with the API the application actually uses.

Class availability still depends on the module being resolved, the class loader seeing the bytecode, and the exact class name. If Class.forName fails with ClassNotFoundException, fix the loading/resolution issue first rather than marking a negative reflection test as passed.

## 7. Positive Test with Qualified opens

Once you have confirmed the package is closed externally, try opening it restrictively to the probe module.

Edit the domain descriptor:

~~~java
module com.example.domain {
    opens com.example.domain.model
        to com.example.probe;
}
~~~

Rebuild both modules and re-run the ReflectionProbe class using trySetAccessible. With this configuration, probe's reflection elevation on the model package is allowed and **trySetAccessible()** can return true.

An explicit positive test:

~~~java
package com.example.probe;

import java.lang.reflect.Field;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field field = type.getDeclaredField("secret");

        if (!field.trySetAccessible()) {
            throw new AssertionError(
                "Qualified opens did not permit reflection"
            );
        }

        System.out.println("PASS: qualified opens allows probe");
    }
}
~~~

When using this example, replace the earlier negative test or run two variants with corresponding descriptors. You cannot expect both "permitted" and "denied" for the same caller, same package, and same module configuration simultaneously.

Qualified opens does not export the package. If you try to import com.example.domain.model.Customer in the probe module's source, javac will still report the package is not visible due to missing exports.

## 8. Verifying a Second Consumer Remains Blocked

To confirm **qualified** opens genuinely restricts access, create another module:

~~~text
src/
└── com.example.otherprobe/
    ├── module-info.java
    └── com/example/otherprobe/OtherProbe.java
~~~

Descriptor:

~~~java
module com.example.otherprobe {
    requires com.example.domain;
}
~~~

Use the same verification idea:

~~~java
package com.example.otherprobe;

import java.lang.reflect.Field;

public final class OtherProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field field = type.getDeclaredField("secret");

        if (field.trySetAccessible()) {
            throw new AssertionError(
                "Other module gained reflection access unexpectedly"
            );
        }

        System.out.println("PASS: other consumer remains blocked");
    }
}
~~~

When the domain descriptor states only **opens com.example.domain.model to com.example.probe**, module otherprobe has no deep reflection rights on that package.

Compile all three modules:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.example.domain,com.example.probe,com.example.otherprobe
~~~

Run each probe module independently:

~~~bash
java --module-path mods \
     -m com.example.probe/com.example.probe.ReflectionProbe
~~~

~~~bash
java --module-path mods \
     -m com.example.otherprobe/com.example.otherprobe.OtherProbe
~~~

Expected behavior when qualified opens is correct: probe is permitted, while otherprobe is denied. This tests both positive and negative cases for the same policy.

## 9. Verifying exports Does Not Substitute for opens

A package can be exported yet still closed to private reflection:

~~~java
module com.example.domain {
    exports com.example.domain.model;
}
~~~

The probe module declares requires as before. Now Java code in probe can import public types from the package:

~~~java
import com.example.domain.model.Customer;
~~~

Yet for the private field secret, the operation:

~~~java
Field field = Customer.class.getDeclaredField("secret");
boolean allowed = field.trySetAccessible();
~~~

remains blocked if the package has not been opened to probe.

Distinguish the two checks:

| Check | With exports but no opens |
| --- | --- |
| Import public class Customer | Allowed if probe reads domain |
| Invoke appropriate public constructor | May be allowed per Java access rules |
| Invoke public method publicName() | May be allowed per Java access rules |
| Bypass private access for field secret | Denied from probe |

This shows that tests covering only the public API are insufficient to guarantee a serialization framework can read private state.

Conversely, when a package only has opens, deep reflection may be permitted while consumer Java source still cannot access the package as an exported API.

## 10. Testing MethodHandles.privateLookupIn

Some frameworks use **MethodHandles** instead of java.lang.reflect.Field. JPMS still governs private access through module openness.

Example:

~~~java
package com.example.probe;

import java.lang.invoke.MethodHandles;

public final class LookupProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        try {
            MethodHandles.privateLookupIn(
                type,
                MethodHandles.lookup()
            );

            throw new AssertionError(
                "Expected privateLookupIn to be rejected"
            );
        } catch (IllegalAccessException expected) {
            System.out.println("PASS: privateLookupIn denied");
        }
    }
}
~~~

When package domain.model is closed to module probe, **privateLookupIn** cannot grant a private-access lookup. When the package is opened to probe and the caller has an appropriate lookup, the operation can succeed.

Note that MethodHandles has its own conditions regarding lookup modes, module readability, and lookup type. Therefore, when encountering IllegalAccessException, check both package openness and the actual lookup object; do not assume every MethodHandles failure is due to missing opens.

If a production framework uses MethodHandles, include at least one integration test through that framework itself rather than testing only Field.setAccessible.

## 11. Module API Helps Explain Test Results

In test code, you can inspect a class's module:

~~~java
Class<?> type =
    Class.forName("com.example.domain.model.Customer");

Module domain = type.getModule();
Module caller = ReflectionProbe.class.getModule();

System.out.println("Domain: " + domain.getName());
System.out.println("Caller: " + caller.getName());
System.out.println("Readable: " + caller.canRead(domain));
System.out.println(
    "Exported: " +
    domain.isExported("com.example.domain.model", caller)
);
System.out.println(
    "Opened: " +
    domain.isOpen("com.example.domain.model", caller)
);
~~~

When the package is neither exported nor opened, domain.isExported and domain.isOpen for module probe usually return false. After adding qualified opens, isOpen becomes true for module probe while remaining false for otherprobe.

These APIs diagnose **current runtime permissions**. They do not state whether permission came from module-info.java or from a launcher flag. If --add-opens is passed unintentionally, isOpen may return true even though the descriptor declares no opens.

To confirm the policy the artifact is intended to provide, cross-check the Module API against the packaged descriptor and test JVM arguments.

## 12. JVM Arguments Can Skew Negative Tests

A test meant to prove a package is closed loses validity if the launcher already added permission:

~~~bash
java --add-opens \
  com.example.domain/com.example.domain.model=com.example.probe \
  --module-path mods \
  -m com.example.probe/com.example.probe.ReflectionProbe
~~~

The flag above opens the package to probe at runtime. A negative test using trySetAccessible will return true and fail as designed.

The dangerous scenario is a loosely written test that only checks "no exception on startup" and therefore fails to catch unexpectedly opened permissions.

Inventory all places where flags might be injected:

- IDE Run/Debug configurations.
- Maven Surefire, Failsafe, and argLine settings.
- Gradle Test, JavaExec, or applicationDefaultJvmArgs.
- JDK_JAVA_OPTIONS, JAVA_TOOL_OPTIONS.
- CI scripts, container entrypoints, or launch scripts.
- Agents and launcher wrappers that may add module options.

A test verifying encapsulation should have a run mode **without relevant --add-opens/--add-exports flags** to verify the default boundary.

## 13. Risk When Tests Are Patched into the Module Under Test

Some build tools run modular tests by using **--patch-module** to inject test classes into the main module.

General example:

~~~bash
--patch-module com.example.domain=target/test-classes
~~~

When a test class is defined as part of the domain module itself, it is no longer a cross-module consumer of domain. A module has internal access to itself, so tests can access elements that an external library would be blocked from.

This is suitable for unit tests checking internal implementation, yet **unsuitable as sole evidence** that encapsulation blocks external consumers.

To test module boundary policy:

1. Use a separate named test module.
2. Have the test module declare requires on the production module if it needs to read it.
3. Do not patch test classes into the domain module in boundary tests.
4. Launch tests on the module path under a deterministic configuration.
5. Verify the test class's actual module with getModule().getName().

Verification snippet:

~~~java
System.out.println(ReflectionProbe.class.getModule().getName());
~~~

The output must be **com.example.probe** in the fixture above. If it prints **com.example.domain**, you are running the test inside the package-owning module, not as an external consumer.

## 14. Integration with JUnit and Maven

Real projects commonly use JUnit 5 and Maven. You can organize a separate integration test module, though you must check whether Maven Surefire or Failsafe puts test classes on the module path, uses --patch-module, or passes extra --add-opens.

Configuration goals:

- The domain module is built as a modular JAR with the proper descriptor.
- Integration tests run in a module distinct from domain when verifying boundaries.
- The test runtime does not automatically open the package being verified in negative cases.
- The JUnit engine and test launcher have the access needed to run tests, without accidentally opening domain.model to the test module.
- Assertions explicitly check false/true or the exact exception, rather than merely checking that the process didn't crash.

A simple JUnit test sample in a consumer module:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Field;
import org.junit.jupiter.api.Test;

final class DomainReflectionTest {
    @Test
    void privateFieldIsNotOpenToConsumer() throws Exception {
        Class<?> type =
            Class.forName("com.example.domain.model.Customer");

        Field field = type.getDeclaredField("secret");

        assertFalse(field.trySetAccessible());
    }
}
~~~

This is an assertion example. To run as a real test module, the test module descriptor must declare dependencies on the domain module and the JUnit modules matching your version; Maven/Gradle must configure the module path and test launcher appropriately.

Do not assume every JUnit artifact shares the same module name across all versions. Check the actual name with **jar --describe-module** or your toolchain documentation.

If Surefire automatically adds --add-opens to run tests, separate permissions needed by the JUnit engine from permissions the test is verifying. You can use a small Java main probe like the examples earlier in this article to isolate encapsulation checks from test runner complexity.

## 15. Integration with Gradle

In Gradle, how tests are placed on the module path depends on source sets, modularity inference, and plugins in use.

For example, there might be JVM args on a Test task:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'com.example.domain/com.example.domain.model=ALL-UNNAMED'
    )
}
~~~

This configuration may be needed by older test frameworks, yet it also alters the permissions tests observe. For tests verifying closed packages, separate boundary-checking configuration from tests that require opening packages to function.

You can create a JavaExec task running the module probe via **java --module-path ... -m ...**, or a dedicated integration-test task that does not pass flags opening the package under test.

What matters is not the task name, but the **actual module identity of the caller** and the **final JVM arguments**. Print caller.getModule().getName() when investigating.

## 16. Distinguishing InaccessibleObjectException and IllegalAccessException

Different APIs reflect different failure modes:

| Operation | Result When Blocked |
| --- | --- |
| Field.trySetAccessible() | Typically returns false |
| Field.setAccessible(true) | InaccessibleObjectException when accessible flag cannot be enabled due to JPMS |
| Field.get(instance) without permission | IllegalAccessException |
| Constructor.newInstance(...) without permission | IllegalAccessException or related access error |
| MethodHandles.privateLookupIn(...) | IllegalAccessException if lookup/module access conditions are not met |

Do not use a broad catch(Exception) to pass tests. If code hits ClassNotFoundException, NoSuchFieldException, or an unexpected initialization error, that is not evidence that encapsulation works correctly.

When a test must prove an access path is denied, assert the exact exception or return value of the operation production actually uses.

## 17. Controlled Reflection Testing Instead of Opening the Whole Module

If a framework only needs access to one model package, restrict the configuration by package and consumer:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model
        to com.example.json;
}
~~~

Avoid immediately replacing this with:

~~~java
open module com.example.domain {
    exports com.example.domain.api;
}
~~~

**open module** opens every package of the module to deep reflection. That can break negative tests protecting other packages and weaken boundaries the application wants to maintain.

An appropriate test suite can have two consumer modules:

- Module **com.example.json** is allowed to reflect into domain.model.
- Module **com.example.otherprobe** is denied reflection into domain.model.

For other internal packages of domain, both consumers must remain blocked unless the descriptor explicitly opens them.

Coexisting positive and negative tests verify the exact scope of qualified opens, rather than just verifying the framework can work.

## 18. Reflection Tests with Libraries on the Classpath

A legacy library on the classpath belongs to its class loader's unnamed module. If a classpath framework needs deep reflection into a named module's package, a temporary way to open access can be:

~~~bash
--add-opens com.example.domain/com.example.domain.model=ALL-UNNAMED
~~~

The value ALL-UNNAMED is not a module name you can write in module-info.java qualified opens. It is a special command-line option target representing unnamed modules.

Therefore, when evaluating migration:

- Tests with the framework on the classpath must reflect permissions granted to the unnamed module.
- Tests once the framework becomes a named module must reflect permissions for that specific module name.
- If moving the framework onto the module path changes its name or module identity, update qualified opens and corresponding tests.
- Do not infer from classpath tests that the exact same reflection path will work in a named-module runtime.

If an older library does not yet support JPMS and needs compatibility flags, document the flag along with source module, package, consumer, and removal condition. Never use a test with ALL-UNNAMED enabled as proof that a package is tightly closed.

## 19. Observation and Diagnostic Tools

You can inspect a modular JAR's descriptor:

~~~bash
jar --describe-module --file mods/com.example.domain.jar
~~~

If tests use exploded modules, check that module-info.class exists in the module output:

~~~text
mods/com.example.domain/module-info.class
mods/com.example.probe/module-info.class
~~~

You can observe module resolution:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.example.probe/com.example.probe.ReflectionProbe
~~~

When suspecting a class loaded from the wrong JAR or loader:

~~~bash
java -Xlog:class+load=info \
     --module-path mods \
     -m com.example.probe/com.example.probe.ReflectionProbe
~~~

In tests, print module identity:

~~~java
Module testModule =
    ReflectionProbe.class.getModule();

Module domainModule =
    Class.forName(
        "com.example.domain.model.Customer"
    ).getModule();

System.out.println("Test module: " + testModule.getName());
System.out.println("Domain module: " + domainModule.getName());
System.out.println(
    "Domain opened to test: " +
    domainModule.isOpen(
        "com.example.domain.model",
        testModule
    )
);
~~~

If a test fails, identify the module name, source artifact, JVM arguments, descriptor, and reflection API invoked. Those are the minimal pieces of evidence to separate permission errors from class loading errors.

## 20. Common Mistakes

**Using a test in the same module to prove a package is closed.** Code in the same module is allowed internal access to its own module; use a caller in another named module.

**Using only Class.forName and concluding the package is open.** Finding a Class does not prove deep reflection is permitted.

**Confusing exports with opens.** Exporting a public API does not permit reading private fields; opening serves reflection yet does not substitute for exports for ordinary source imports.

**Catching all exceptions and passing the test.** Classpath errors, field names, or test setup bugs can be masked.

**Keeping --add-opens in the test runtime.** Negative tests will run with the very permission they are designed to reject.

**Patching tests into the production module.** The caller module changes; tested permissions no longer reflect a real consumer.

**Testing only one module after qualified opens.** Fails to prove other modules remain blocked.

**Keeping an old JAR after editing the descriptor.** Source module-info.java changed while runtime still uses the stale module-info.class.

**Running only IDE classpath tests.** Behavior can differ when production uses named modules and the module path.

**Treating opens as a security sandbox.** JPMS provides strong encapsulation and API boundaries, not a mechanism to isolate untrusted code into a security sandbox.

## 21. Recommended Testing Workflow

1. Create a domain module fixture with a package containing a private field.
2. Create a separate probe module with requires on domain.
3. Verify the probe actually runs under the right module name via Class.getModule().
4. When the package is closed, confirm trySetAccessible returns false and setAccessible(true) is denied.
5. When only exports is present, verify public API works while private reflection stays blocked.
6. With qualified opens to probe, verify positive reflection passes.
7. Create otherprobe and confirm qualified opens does not grant permission to unlisted modules.
8. If production uses MethodHandles, test privateLookupIn accordingly.
9. If production uses serialization/injection frameworks, run integration tests that actually exercise that reflection path.
10. Review JVM args and the test runner to ensure packages are not accidentally opened in negative cases.
11. Inspect artifact module-info.class and use --show-module-resolution when needed.
12. Run tests with the JDK and module path matching the deployment environment.

**Reflection testing when packages are closed** does more than check whether one setAccessible call throws an exception. It verifies module policy: which consumers may use the public API, which consumers may perform deep reflection, and which consumers must be blocked. A test fixture of independent named modules, clear negative/positive assertions, and a launcher free of hidden overrides provides a reliable foundation to protect encapsulation as Java applications become modularized.