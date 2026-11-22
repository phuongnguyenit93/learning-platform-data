# Testing Reflection Permissions Within the Same Module and Across Modules (Java 17+)

## 1. Testing Goals

Java Reflection allows looking up metadata of classes, fields, methods, and constructors; **finding them does not equate to having permission to invoke them**. Since Java 9, the Java Platform Module System (JPMS) added module boundaries, especially important on Java 17+ with strong encapsulation.

An access-permission test suite must distinguish:

1. **Source-level type visibility:** Can a public class from that package be imported and compiled?
2. **Normal public member invocation permission:** Is standard Java access to the public API valid?
3. **Metadata lookup capability:** Can you obtain a `Method`, `Field`, or `Constructor<?>` object?
4. **Metadata usage capability:** Can you call `Method.invoke`, `Field.get/set`, or `Constructor.newInstance` directly?
5. **Deep reflection:** Is disabling normal access checks via `trySetAccessible`/`setAccessible` permitted?
6. **Method handles:** Can you create a suitable `Lookup` with `privateLookupIn` and access private members?
7. **Runtime environment differences:** Do classpath, named modules, `opens` in descriptors, and `--add-opens` at runtime produce results matching expectations?

The topic "same and different module" is **not** just testing public vs. private. Java adds boundaries for **packages, nests, class loaders, module readability, and package exports/opens**; do not collapse everything into a single `isPublic` flag.

## 2. Four Concepts to Distinguish: `public`, `requires`, `exports`, `opens`

Suppose module `com.demo.client` calls code in module `com.demo.domain`:

| Concept | Role |
| --- | --- |
| `public` on class/member | Java language visibility condition; alone it is not enough to cross module boundaries |
| `requires com.demo.domain;` | Establishes client readability of domain at compile time and runtime per the module graph |
| `exports com.demo.domain.api;` | Allows other modules to access public types and public members of the package under normal Java rules |
| `opens com.demo.domain.internal to com.demo.client;` | Allows **deep reflection** into the target package for the client module, including attempting `setAccessible` and `privateLookupIn` per API conditions |
| `open module com.demo.domain` | Opens every package in the module for deep reflection; does not automatically export them for source imports |
| `--add-opens A/p=B` | Additionally opens package `p` of module `A` to module `B` at runtime, without editing source/module-info |

**`exports` does not automatically grant private access. `opens` does not replace `exports` for importing public classes from another module.** You can both export and open the same package if you want both a public API and valid deep reflection.

Within the same **named module**, a caller may be allowed to use `setAccessible(true)` on non-public members of another class in the module under Reflection's conditions. That **does not mean ordinary Java source code is allowed to directly call private members**; private/package/protected rules still apply at compile time.

Across **different named modules**, even a private method of a public class in an `exports`-ed package is not automatically open to deep reflection; the package must be opened under appropriate conditions.

On the **classpath**, the application normally belongs to the unnamed module; packages of the unnamed module are open to deep reflection per JPMS rules. This is a separate test case, not proof that the same code will run when moved to a named module.

## 3. Expected Matrix When Testing

The following matrix assumes the caller reads the target module, has no extra privileged access mechanisms, and the target is a public class with a public or private method.

| Call site / target package config | Calling public member via normal Java | Deep reflection on private method from another module |
| --- | --- | --- |
| Same named module | Yes if Java visibility/package rules are satisfied | Suppression is typically permitted for members within the same module |
| Different module; package `exports`, not `opens` | Yes for public types and public members | **No** merely due to export |
| Different module; package `opens ... to client`, not `exports` | Cannot import that package as a normal public API | **Possible** if lookup/access conditions match |
| Different module; package `exports` and `opens` | Yes for public API | Deep reflection possible if conditions are met |
| Different module; neither `exports` nor `opens` | Cannot access directly from source | Deep reflection is typically denied |
| On classpath/unnamed module | Follows normal visibility/package rules | Differs from named modules; requires separate testing |

The table is a **permission model**, not a guarantee that every call will succeed. For example, a misplaced null receiver, wrong method signature, constructor throwing an exception, or restrictions on final fields still fail independently of JPMS.

### Which API Tests What?

- `getDeclaredMethod("secret")`: looks up a directly declared method, including private ones; it can usually return metadata even when calling it is forbidden.
- `method.canAccess(receiver)`: checks current access permission for the member with an appropriate receiver, **without modifying** the accessible flag itself. For static methods, pass `null` as receiver.
- `method.trySetAccessible()`: attempts to enable suppression, returning `true` or `false` if access is disallowed per contract; may throw other errors in certain situations.
- `method.setAccessible(true)`: may throw `InaccessibleObjectException` when suppression cannot be enabled, instead of returning a boolean.
- `method.invoke(receiver, args...)`: may throw `IllegalAccessException` when unauthorized, while exceptions from the target method are typically wrapped in `InvocationTargetException`.
- `MethodHandles.privateLookupIn(target, callerLookup)`: may throw `IllegalAccessException` if the caller lacks required privileges, lacks readability, or the package in another module is not suitably open; also enforces lookup modes.
- `lookup.findVirtual(...)` or `lookup.unreflect(method)`: enforces access checks using the respective `Lookup`; having obtained `Method` earlier grants no extra privilege.

A good test records the **target object, caller module, target module, package, mode, and API tested**. Do not just assert whether an exception was thrown while losing the cause.

## 4. Hands-On Practice: Two Named Modules, One Test Program

We create exactly two modules:

- `com.demo.domain` contains an exported public API and an internal class that is initially **neither exported nor opened**.
- `com.demo.client` has `requires com.demo.domain` and tests calls via the public API, external Reflection, plus a private Reflection check running **inside** domain.

Directory structure:

```text
src/
├── com.demo.domain/
│   ├── module-info.java
│   └── com/demo/domain/
│       ├── api/Entry.java
│       └── internal/
│           ├── Hidden.java
│           └── Probe.java
└── com.demo.client/
    ├── module-info.java
    └── com/demo/client/Main.java
```

This is a standalone Java 17+ example requiring no external libraries. The files below must preserve exact paths and packages.

### 4.1. Domain Module Without Opening the Internal Package

Create `src/com.demo.domain/module-info.java`:

```java
module com.demo.domain {
    exports com.demo.domain.api;
}
```

Package `api` is exported; package `internal` is neither exported nor opened to the client.

Create `src/com.demo.domain/com/demo/domain/internal/Hidden.java`:

```java
package com.demo.domain.internal;

public final class Hidden {
    public String publicMethod() {
        return "public-inside";
    }

    private String secret() {
        return "inside";
    }
}
```

`Hidden` is public **in an unexported package**. The client cannot import this class as a public API merely because it has the `public` modifier.

Create `src/com.demo.domain/com/demo/domain/internal/Probe.java`:

```java
package com.demo.domain.internal;

import java.lang.reflect.Method;

public final class Probe {
    private Probe() {}

    public static String sameModulePrivateCall()
            throws ReflectiveOperationException {
        Hidden target = new Hidden();
        Method method = Hidden.class.getDeclaredMethod("secret");

        if (!method.trySetAccessible()) {
            throw new AssertionError("Same-module access denied");
        }
        return (String) method.invoke(target);
    }
}
```

`Probe` invokes Reflection from the **same module** as `Hidden` (and in this example, the same package). The private method is not called directly in `Probe`'s source code, yet attempting Reflection suppression can be permitted. `opens` is not required solely for two classes in the same module to perform this Reflection path.

Create `src/com.demo.domain/com/demo/domain/api/Entry.java`:

```java
package com.demo.domain.api;

import com.demo.domain.internal.Hidden;
import com.demo.domain.internal.Probe;

public final class Entry {
    private Entry() {}

    public static String ping() {
        return "pong";
    }

    public static Object newHidden() {
        return new Hidden();
    }

    public static String probeInside()
            throws ReflectiveOperationException {
        return Probe.sameModulePrivateCall();
    }
}
```

`Entry` is the public gateway in the exported package. It can use `Hidden`/`Probe` from the internal package because they are in the same module. The client receives the object as type `Object` without importing the internal class.

### 4.2. Client Module and Test Program

Create `src/com.demo.client/module-info.java`:

```java
module com.demo.client {
    requires com.demo.domain;
}
```

Create `src/com.demo.client/com/demo/client/Main.java`:

```java
package com.demo.client;

import com.demo.domain.api.Entry;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args) throws Throwable {
        boolean expectOpen = args.length == 1
                && "open".equals(args[0]);

        System.out.println("same-module private="
                + Entry.probeInside());
        System.out.println("exported public=" + Entry.ping());

        Object target = Entry.newHidden();
        Class<?> targetClass = target.getClass();
        Method method = targetClass.getDeclaredMethod("secret");

        System.out.println("cross canAccess="
                + method.canAccess(target));

        boolean enabled = method.trySetAccessible();
        System.out.println("cross trySetAccessible=" + enabled);

        String reflectionResult;
        try {
            reflectionResult = (String) method.invoke(target);
        } catch (IllegalAccessException denied) {
            reflectionResult = "DENIED";
        }
        System.out.println("cross invoke=" + reflectionResult);

        String lookupResult;
        try {
            MethodHandles.Lookup privateLookup =
                    MethodHandles.privateLookupIn(
                            targetClass, MethodHandles.lookup());
            MethodHandle handle = privateLookup.findVirtual(
                    targetClass,
                    "secret",
                    MethodType.methodType(String.class));
            lookupResult = (String) handle.invoke(target);
        } catch (IllegalAccessException denied) {
            lookupResult = "DENIED";
        }
        System.out.println("privateLookupIn=" + lookupResult);

        boolean actualOpen = enabled
                && "inside".equals(reflectionResult)
                && "inside".equals(lookupResult);

        if (actualOpen != expectOpen) {
            throw new AssertionError(
                    "Expected open=" + expectOpen
                            + ", actual=" + actualOpen);
        }

        System.out.println("PASS " + (expectOpen ? "open" : "closed"));
    }
}
```

**Key points:**

1. `Entry.probeInside()` runs private Reflection **inside domain** and returns `"inside"`. This is the same-module check.
2. `Entry.ping()` calls the public API via `exports`, needing no `opens`.
3. `target.getClass().getDeclaredMethod("secret")` illustrates looking up non-public metadata from the client; do not infer invocation permission.
4. `canAccess(target)` is called **before** `trySetAccessible`. Since the client has no direct language access to the private method, the result is `false` in both scenarios.
5. `trySetAccessible` then depends on whether package `internal` is opened to the client module.
6. `privateLookupIn` is tested separately. It does not inherit permission from `method.trySetAccessible()` having been enabled; it checks the caller's `Lookup` and module configuration.
7. The `PASS` line appears only if the open/closed outcome matches the run argument. If permissions are unexpected, the program exits with `AssertionError` (non-zero exit code).

**Error distinction:** The `catch` blocks catch only `IllegalAccessException` to represent denial as `DENIED`. Do not use `catch (Throwable ignored)` because it could accidentally swallow program bugs unrelated to access. `main throws Throwable` is only to keep the MethodHandle example simple in this hands-on lesson.

## 5. Compile and Run Case 1: Closed Module

From the directory containing `src`, create the output directory:

```bash
mkdir out
```

Compile both modules (written as a single-line command for common shells, including PowerShell):

```bash
javac -d out --module-source-path src src/com.demo.domain/module-info.java src/com.demo.domain/com/demo/domain/api/Entry.java src/com.demo.domain/com/demo/domain/internal/Hidden.java src/com.demo.domain/com/demo/domain/internal/Probe.java src/com.demo.client/module-info.java src/com.demo.client/com/demo/client/Main.java
```

Run **without adding extra package-opening permissions**:

```bash
java --module-path out -m com.demo.client/com.demo.client.Main closed
```

Expected stdout:

```text
same-module private=inside
exported public=pong
cross canAccess=false
cross trySetAccessible=false
cross invoke=DENIED
privateLookupIn=DENIED
PASS closed
```

Explanation: the public API in package `api` is exported and callable; the private Reflection check running **inside domain** succeeds. From the client, however, package `internal` is not open, so `trySetAccessible` returns `false`; `Method.invoke` is forbidden from calling the private method; `privateLookupIn` is not granted a private lookup into the closed package.

If you replace `trySetAccessible()` with `setAccessible(true)` in the client, an unopened package can throw `InaccessibleObjectException`. That is a different failure signal from `IllegalAccessException` thrown by `Method.invoke`/`privateLookupIn`.

## 6. Run Case 2: Selectively Opening a Package via `--add-opens`

Without modifying source or rebuilding, re-run the **exact same class files** with an additional open grant:

```bash
java --module-path out --add-opens com.demo.domain/com.demo.domain.internal=com.demo.client -m com.demo.client/com.demo.client.Main open
```

Expected stdout:

```text
same-module private=inside
exported public=pong
cross canAccess=false
cross trySetAccessible=true
cross invoke=inside
privateLookupIn=inside
PASS open
```

Why does `canAccess` still print `false`? The call runs **before enabling the accessible override** and checks normal Java invocation permissions. `--add-opens` makes deep reflection **permissible when requested**, without turning private members into public source members.

Why does `privateLookupIn` succeed? Client reads domain via `requires`; domain opened `com.demo.domain.internal` **to the client module**, so lookup can be granted permission under the `privateLookupIn` contract.

### 6.1. Opening a Package via Descriptor Instead of the Command Line

You can also replace `src/com.demo.domain/module-info.java` with:

```java
module com.demo.domain {
    exports com.demo.domain.api;
    opens com.demo.domain.internal to com.demo.client;
}
```

This is an **alternative version** of the same file; do not create two `module-info.java` files for the domain module. Recompile using the command in section 5, then run without `--add-opens`:

```bash
java --module-path out -m com.demo.client/com.demo.client.Main open
```

The expected output matches the `open` scenario above. Qualified `opens` only grants deep reflection to the listed module; a third module does not automatically gain that permission. For production environments, declaring targeted `opens` is usually clearer than opening an entire module.

**Practical note:** After editing the descriptor to `opens`, to truly re-test the `closed` case you must revert to the original `module-info` and rebuild. Otherwise, running with argument `closed` will fail the assertion because you are testing an already-opened module.

## 7. Three Additional Checks to Avoid Wrong Conclusions

### 7.1. `--add-exports` Is Not Equivalent to `--add-opens`

With the **unopened** domain version from section 4, try:

```bash
java --module-path out --add-exports com.demo.domain/com.demo.domain.internal=com.demo.client -m com.demo.client/com.demo.client.Main closed
```

`--add-exports` grants the client access to that package's **public API** under export rules, but **does not open private members for deep reflection**. Since `secret()` is private, the expected outcome remains the `closed` scenario. Do not use `--add-exports` to "fix" a `privateLookupIn` failure.

### 7.2. Metadata Present Does Not Mean Member Invocable

In both scenarios, `getDeclaredMethod("secret")` returns a `Method`. It proves metadata can be retrieved, not that direct access is valid.

Conversely, if you request a wrong name/signature:

```java
Method missing = targetClass.getDeclaredMethod("unknown");
```

The snippet above illustrates an error in client context throwing `NoSuchMethodException`, **not** a JPMS error. A test suite should separate "not found" cases from "found but denied" cases.

### 7.3. `public` in an Unexported Package Is Still Restricted

`Hidden.publicMethod()` is a `public` method of a `public` class, yet its containing package is not exported. Those two `public` modifiers alone do not give the client compile-time permission to import `Hidden`. You can obtain the method's metadata via `target.getClass().getMethod("publicMethod")`, yet `invoke` from the client still obeys the declaring class/package permissions; checking `Modifier.isPublic(...)` alone cannot replace `exports`.

If a package is `opens` without `exports`, deep reflection after enabling the override can work, yet that still does not make the package a public API for the client to import in source.

## 8. Using `canAccess`, `trySetAccessible`, and `setAccessible` Properly

| API | Mutates state? | Key result / behavior |
| --- | --- | --- |
| `canAccess(receiver)` | No | `boolean` for access capability given current state |
| `trySetAccessible()` | Can enable accessible override if allowed | `true` if enabled; `false` when access cannot be suppressed |
| `setAccessible(true)` | Attempts to enable accessible override | Can throw `InaccessibleObjectException` if blocked by JPMS |
| `setAccessible(false)` | Disables override on that metadata object | Does not alter the module graph |
| `Method.invoke(...)` | Executes member when permitted | `IllegalAccessException` if blocked; target errors wrapped in `InvocationTargetException` |

**Valid receivers matter:**

- `Method.canAccess(instance)`: pass a suitable instance for an instance method.
- `Method.canAccess(null)`: pass `null` for a static method.
- `Field.canAccess(instance)`: instance fields need a receiver of the right type; static fields use `null`.
- `Constructor.canAccess(null)`: constructors take receiver `null`.

A wrong receiver can cause `canAccess` to throw `IllegalArgumentException`. Do not treat every exception during permission checks as proof of JPMS denial.

Mechanisms that mutate the accessible override should only be used when required by the framework contract; avoid toggling `setAccessible(true/false)` repeatedly on the same cached `AccessibleObject` shared across threads. That makes reasoning about permissions and access state difficult. Tests can use isolated metadata objects and explicitly track what enabled the override.

## 9. Testing `MethodHandles.Lookup` and `privateLookupIn`

`MethodHandles.lookup()` creates a lookup with the caller class's privileges. `publicLookup()` is more restricted. `privateLookupIn(targetClass, callerLookup)` does not work merely by having the target's `Class<?>`: it must satisfy **lookup modes**, module readability, and package-open permissions.

Two test questions should be separated:

1. **Can the method be found via Reflection?** `getDeclaredMethod` can return metadata.
2. **Is there permission to create a handle with private lookup?** `privateLookupIn` and `findVirtual` require separate permissions.

In the example, even though `method.trySetAccessible()` succeeds in the open scenario, `privateLookupIn` does **not** gain permission because that `Method` object flipped its flag; it evaluates the `Lookup`'s privileges and the module graph. Using a `Lookup` without all required privileges still will not succeed even on an open package.

Never cache a private-privileged `Lookup` and hand it out arbitrarily to plugins or untrusted callers. Module boundaries are part of code access policy; business authorization and user authentication are an additional layer of control.

Besides `findVirtual`, unreflecting such as `lookup.unreflect(method)` is also subject to lookup access checks. Do not assume method handles "bypass" encapsulation.

## 10. Testing Fields, Constructors, and Error Types

The same reasoning extends from methods to fields and constructors:

| Member | Metadata lookup | Permission check and execution |
| --- | --- | --- |
| Private instance field | `getDeclaredField("value")` | `canAccess(instance)`, `trySetAccessible()`, `get(instance)`/`set(instance, value)` |
| Private static field | `getDeclaredField("COUNT")` | `canAccess(null)`, `trySetAccessible()`, `get(null)` |
| Private constructor | `getDeclaredConstructor(types...)` | `canAccess(null)`, `trySetAccessible()`, `newInstance(args...)` |
| Private instance method | `getDeclaredMethod(name, types...)` | `canAccess(instance)`, `trySetAccessible()`, `invoke(instance, args...)` |

**Do not test writing to a `final` field just to prove access permission.** A final field has its own write restrictions, and succeeding at reading or suppressing access does not imply writing is valid. A `VarHandle` on a final field may only support read access modes. For constructors, instantiating an object can have side effects; use simple fixture classes that do not touch network/files/system state.

Exceptions to classify:

- `ClassNotFoundException`: type could not be found by name/loader.
- `NoSuchMethodException`, `NoSuchFieldException`: metadata has no member matching the search criteria.
- `IllegalAccessException`: the Reflection or Lookup operation lacks required permissions.
- `InaccessibleObjectException` (unchecked): unable to enable suppression via `setAccessible(true)` due to module/access policy.
- `InvocationTargetException`: the target method/constructor invoked via Reflection threw an exception; inspect `getCause()` for the actual error.
- `IllegalArgumentException`: arguments, receiver, or types passed to Reflection are incompatible.
- `WrongMethodTypeException`: call site types in `MethodHandle.invokeExact` do not match `MethodType`.
- `ExceptionInInitializerError` and class-loading/linking errors: independent of member access permissions; investigate separately.

A good test suite must not catch all errors and mark `"PASS blocked"`: doing so can turn programming bugs into false passes.

## 11. Ensuring Tests Run as Real Modules, Without Falling Back to the Classpath

Common test-configuration mistakes:

- Running `java -cp ...` instead of `--module-path ... -m ...`, placing classes in the unnamed module where deep reflection behaves differently than expected.
- Missing `requires` or failing to resolve the target module, leading to module-graph errors mistaken for private access failures.
- Adding `--add-opens` in IDE/JUnit settings while forgetting production lacks it, making tests pass falsely.
- Build tools placing test code into the **same module** as target code when the goal is to simulate a caller in a **different module**.
- Tests using a public class in an exported package and forgetting to test an actual private/closed package, never exercising strong encapsulation.
- Calling `setAccessible(true)` or `trySetAccessible` from code inside the target module and concluding external modules have the same permission.
- Using different JDK versions, launcher flags, and plugin/module paths between CI and production.

When diagnosing, you can print the actual modules of caller and target using the illustrative snippet below:

```java
System.out.println(Main.class.getModule().getName());
System.out.println(target.getClass().getModule().getName());
System.out.println(target.getClass().getModule().isOpen(
        target.getClass().getPackageName(),
        Main.class.getModule()));
```

Place this snippet in `Main.main` of the example. With the original configuration, the two module names are `com.demo.client` and `com.demo.domain`; the last line reflects whether the internal package is open to the client at runtime. With `--add-opens`, checking `Module.isOpen(package, clientModule)` helps confirm the module was opened to the right target.

For meaningful JUnit integration tests, use **two fixtures running across real module boundaries** or a forked-process harness with controlled launcher flags. You do not have to cram every scenario into one JUnit test running on the classpath.

## 12. PASS/FAIL Criteria and Negative Tests

A minimum test suite should cover both permitted and blocked cases:

| Test case | Expectation | Goal |
| --- | --- | --- |
| Same-module private reflection | Succeeds inside fixture `Probe` | Confirm internal suppression permission |
| Cross-module public exported API | Succeeds with `Entry.ping()` | Confirm `requires` + `exports` |
| Cross-module private in closed package | `trySetAccessible=false`; un-overridden call denied | Confirm strong encapsulation |
| Cross-module `privateLookupIn` when package closed | Denied | Confirm lookup does not bypass JPMS |
| Cross-module private with `--add-opens`/qualified `opens` | Deep reflection succeeds | Confirm opening to exact target module |
| Cross-module `--add-exports` only | Private deep reflection still denied | Distinguish `exports`/`opens` |
| Wrong method signature | `NoSuchMethodException` | Separate lookup errors from access errors |
| Wrong/null receiver for instance member | Appropriate exception | Confirm input errors are not confused with permissions |
| Private constructor/field | Corresponding allowed/denied cases | Extend rules to other member kinds |
| Real CI run via module path | PASS both positive and negative tests | Avoid classpath false positives |

Have tests print/log the **module configuration**, actual exception type, and `trySetAccessible` status. For negative tests, assert the **exact error type or boolean value**, not merely "any exception."

If a test modifies `module-info.java`, perform a clean rebuild and re-run from a known module-graph state. If a test runs with `--add-opens`, document the exact launcher flag so CI and other environments reproduce it accurately.

## 13. Checklist Before Using Cross-Module Reflection in Production

1. Identify the exact **caller module**, **target module**, target package, and member to access.
2. Ask whether a public API suffices. If so, use `exports` and public APIs instead of deep reflection.
3. If private reflection is needed, open only the necessary package to trusted modules; prefer qualified `opens` over opening globally.
4. Separate checking metadata existence from checking execution permission; do not use `isPublic` as the sole conclusion.
5. Test `canAccess`, `trySetAccessible`, `Method.invoke`, and `privateLookupIn` in the **exact** caller context.
6. Do not abuse `setAccessible` or `--add-opens` launcher flags to mask a flawed API design.
7. Do not arbitrarily invoke methods/constructors just to check permissions if they have side effects; use safe fixtures.
8. Include both allowed and denied cases in CI, verify module path/JDK/VM flags, and record actual status.
9. When using cached `Method`/`Field`/`Lookup`, also evaluate permissions and thread-safety conditions; module/reflection permissions do not automatically serve as user security policy.

### Self-Check

1. Why can `getDeclaredMethod("secret")` still succeed in the client module even when `invoke` is denied?
2. How do `exports` and `opens` differ? Does an exported package allow reading private fields from another module?
3. Why is `canAccess` called **before** `trySetAccessible` in the hands-on exercise?
4. Why does the open scenario still print `cross canAccess=false` yet `Method.invoke` subsequently succeeds?
5. When does `privateLookupIn` fail even though a `Method` was obtained via Reflection?
6. If you test on the classpath and then switch to the module path, why can deep reflection permissions change?
7. Why should negative tests check `IllegalAccessException` or `false` instead of catching all `Throwable`s?
8. How do you prove permission was opened to the client module without opening it to every other module?

**Takeaway:** Reflection permission tests must run within the **real module graph and call site**. `public` and `exports` address public APIs; `opens` and `privateLookupIn` concern deep reflection. **Looking up metadata**, **evaluating/granting access**, and **executing the member** are three distinct steps; reliable tests must verify both permitted and denied cases.