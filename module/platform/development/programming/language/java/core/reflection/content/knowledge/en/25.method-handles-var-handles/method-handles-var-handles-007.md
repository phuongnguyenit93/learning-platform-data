# `MethodHandles.privateLookupIn` and Module Access Opening Conditions (Java 17+)

## 1. Why Is `privateLookupIn` Needed?

`MethodHandle` and `VarHandle` provide access to methods, constructors, and variables through an **access capability object** (`MethodHandles.Lookup`). When calling `findVirtual`, `findStatic`, `findVarHandle`, etc., Java checks the `Lookup`'s permissions right at handle creation time. Holding a `Class<?>` or knowing a private member's name **does not automatically grant permission** to access that member.

The method:

~~~java
MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(Target.class, callerLookup);
~~~

creates a `Lookup` whose **lookup class context is `Target`** and which can access `Target`'s `private` members, **only when `callerLookup` already holds sufficient privileges and module boundaries permit deep access** (*deep reflection*). Introduced in Java 9, this API fits the JPMS module system. It does not open packages, does not disable the module system, and does not yet create a `MethodHandle` or `VarHandle`; to use a member, you must look up the member using `targetLookup` in the next step.

Lesson objectives:

- Understand the differences among `MethodHandles.lookup()`, `publicLookup()`, `Lookup.in(...)`, and `privateLookupIn(...)`.
- Know the exact requirements for `PRIVATE`, `MODULE`, `reads` relationships, and `opens` directives.
- Distinguish `exports` from `opens` and know how to use `--add-opens` for testing/diagnostics.
- Invoke private methods and manipulate private fields with MethodHandle/VarHandle, handling access errors in the right place.
- Recognize that moving a `Lookup` from one module to another drops the `MODULE` mode and prevents arbitrarily "forwarding" private permissions.

## 2. `Lookup` Is a Transferable Access Capability

`MethodHandles.lookup()` is **caller-sensitive**: whichever class contains the call normally returns a `Lookup` whose `lookupClass()` is that class, with full privileges of the calling class (in an ordinary call, including the `PRIVATE` and `MODULE` modes).

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();
System.out.println(caller.lookupClass().getName());
~~~

`MethodHandles.publicLookup()` only grants public access according to its rules, **lacking `PRIVATE`/`MODULE` to call `privateLookupIn`**. `caller.in(Other.class)` changes the lookup context class, but privileges may be reduced—especially when changing classes, packages, or modules; it is not a way to self-elevate to private access.

Key methods:

| API | Meaning |
| --- | --- |
| `MethodHandles.lookup()` | Creates a lookup bound to **its actual calling class** |
| `MethodHandles.publicLookup()` | Public lookup, lacking privileges to request a private lookup |
| `lookup.lookupClass()` | The class the lookup currently represents |
| `lookup.lookupModes()` | Privilege bitmask, including `PUBLIC`, `PRIVATE`, `PROTECTED`, `PACKAGE`, `MODULE`, etc. |
| `lookup.in(SomeClass.class)` | Switches context without increasing privileges |
| `MethodHandles.privateLookupIn(Target.class, lookup)` | Requests a new lookup with private access on `Target`, after checking conditions |
| `lookup.findVirtual`, `findStatic`, `findVarHandle` | Creates handles on members according to the lookup's current permissions |

`Lookup` is a **capability**: if code receives a sufficiently privileged lookup or a handle to a private method, that code can exercise the granted capability. Limit sharing these objects with untrusted plugins or components; do not treat hiding a method name as a security boundary.

## 3. Conditions for `privateLookupIn` in Java 17

Let `M1` be the module containing `callerLookup.lookupClass()` and `M2` be the module containing `Target.class`.

### 3.1. General Conditions

1. `callerLookup` must have **both `Lookup.PRIVATE` and `Lookup.MODULE`**. A `Lookup` restricted by `publicLookup()` or `dropLookupMode(...)` may lack sufficient modes. `privateLookupIn` does not restore lost modes.
2. `Target` must be a **real class/interface**, not a primitive, `void`, or array class; passing `int.class`, `void.class`, or `String[].class` as target throws `IllegalArgumentException`.
3. `targetClass` and `callerLookup` must not be `null`; otherwise `NullPointerException` is thrown.
4. When permission checks fail, the call can throw **`IllegalAccessException`**. In Java 17 environments where a Security Manager is enabled, corresponding policies can also throw `SecurityException`.

### 3.2. When `M1 == M2`

When the lookup has `PRIVATE`/`MODULE` and the target is in the **same module**, `privateLookupIn` grants the lookup full-privilege access to the target, even across different packages within that module. No extra `opens` is needed just for an **intra-module** private lookup.

This does not mean ordinary Java syntax in one class can call a private method of another class. This extended access is granted through an API that checks `Lookup` and must be decided by the lookup owner.

### 3.3. When `M1 != M2`

Both of the following must hold **simultaneously**:

- **`M1 reads M2`:** the calling module has a readability relationship to the target module, e.g., `requires vault.core;` in `module-info.java`, or equivalent runtime configuration.
- **`M2 opens Target's package to M1`:** e.g., `opens demo.vault to demo.client;` in M2's descriptor, or adding permission for the exact package via `--add-opens vault.core/demo.vault=demo.client`.

In addition, the caller lookup must still hold `PRIVATE` and `MODULE` per the general condition. Having only module readability or only `exports` is **not enough** to access private members.

| Scenario | `privateLookupIn(Target, caller)` |
| --- | --- |
| Same module, caller lookup has required modes | Can create private lookup |
| Different modules, has `reads` and package is `opens` to caller | Can create private lookup |
| Different modules, package is only `exports` | Private lookup is not permitted |
| Different modules, package is `opens` but caller module does not read target module | Conditions not met |
| `publicLookup()` even if package is `opens` | Lacks `PRIVATE`/`MODULE` |
| Target is `int.class` or `String[].class` | `IllegalArgumentException` |

> **Rule:** module checks are performed against the **module of the lookup class**, not a module name the application wishes to assume or merely the file location of the API call. Passing a `Lookup` through an API does not give it extra permissions.

## 4. How Does `exports` Differ from `opens`?

`module-info.java` has two complementary concepts:

~~~java
module vault.core {
    exports demo.vault;
    opens demo.internal to demo.client;
}
~~~

- `exports demo.vault;`: allows modules that read `vault.core` to use **public types and public members** in that package via normal access rules. It does not permit opening private members.
- `opens demo.internal to demo.client;`: permits **deep reflection** into package `demo.internal` from module `demo.client` (still subject to appropriate lookup/module conditions). It is not a declaration that all types in that package can be imported directly at compile time.
- `opens demo.internal;`: opens to every module; broader scope than necessary.
- `open module vault.core { ... }`: opens all packages in the module; choose only when genuinely appropriate.
- A package can be both `exports` and `opens` simultaneously if both public API usage and private reflection are needed.

If you do not own the target module's source code, the JVM supports a runtime option:

~~~bash
--add-opens vault.core/demo.vault=demo.client
~~~

Before `=` is `module/package` to open; after `=` is the **module granted access**, not a package name. For code running from the **classpath**, the target module can open to `ALL-UNNAMED`:

~~~bash
--add-opens vault.core/demo.vault=ALL-UNNAMED
~~~

`--add-exports` and `--add-opens` are two distinct mechanisms: adding `--add-exports` does not permit private access. Nor does `--add-opens` automatically grant `PRIVATE`/`MODULE` modes to a weak caller lookup, or create a missing `reads` relationship. For named modules, `--add-reads source.module=target.module` can add a readability relationship when genuinely needed.

## 5. Example 1 — Calling a Private Method and Manipulating a Private Field in the Same Module

The following Java 17+ program contains two **top-level classes** in the same file, placed on the classpath (unnamed module). They are **not nestmates**; therefore, `PrivateLookupDemo`'s direct lookup cannot access private members of `TokenBox`.

Create `PrivateLookupDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;

class TokenBox {
    private int count = 1;

    private String reveal(String prefix) {
        return prefix + "ok";
    }
}

public class PrivateLookupDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup caller = MethodHandles.lookup();

        try {
            caller.findVirtual(
                    TokenBox.class, "reveal",
                    MethodType.methodType(String.class, String.class));
        } catch (IllegalAccessException ex) {
            System.out.println("Direct lookup denied");
        }

        MethodHandles.Lookup privileged =
                MethodHandles.privateLookupIn(TokenBox.class, caller);

        MethodHandle reveal = privileged.findVirtual(
                TokenBox.class, "reveal",
                MethodType.methodType(String.class, String.class));

        TokenBox box = new TokenBox();
        System.out.println((String) reveal.invokeExact(box, "ID:"));

        VarHandle count = privileged.findVarHandle(
                TokenBox.class, "count", int.class);
        int before = (int) count.get(box);
        count.set(box, 5);
        int after = (int) count.get(box);
        System.out.println("count: " + before + " -> " + after);
    }
}
~~~

Run:

~~~bash
javac PrivateLookupDemo.java
java PrivateLookupDemo
~~~

Expected output:

~~~text
Direct lookup denied
ID:ok
count: 1 -> 5
~~~

**Analysis:** `caller` is created in `PrivateLookupDemo`, so direct `findVirtual` cannot read the private `TokenBox.reveal`. `privateLookupIn` switches the privileged context to `TokenBox`. `findVirtual` creates a handle with a logical signature consisting of receiver `TokenBox` followed by parameter `String`; `invokeExact(box, "ID:")` requires the Java types at the call site to match exactly. `findVarHandle` creates access to the `int count` field; `get` and `set` on the instance likewise follow the declared type.

If `TokenBox` were placed as a **nested class** in the same nest as the calling class, Java could allow private access via nestmate access even without `privateLookupIn`. Hence, the example deliberately uses two top-level classes to demonstrate the difference.

## 6. Example 2 — Two Named Modules: Denied First, Then Opening the Package

We will create module `vault.core` containing `demo.vault.Vault` and module `demo.client` containing the test program. `vault.core` **exports the public API** so `demo.client` compiles, but initially **does not open** the package for deep reflection.

Directory structure:

~~~text
src/
├── vault.core/
│   ├── module-info.java
│   └── demo/vault/Vault.java
└── demo.client/
    ├── module-info.java
    └── demo/client/Main.java
~~~

File `src/vault.core/module-info.java`:

~~~java
module vault.core {
    exports demo.vault;
}
~~~

File `src/vault.core/demo/vault/Vault.java`:

~~~java
package demo.vault;

public final class Vault {
    public Vault() {}

    private String secret() {
        return "ACCESS_GRANTED";
    }
}
~~~

File `src/demo.client/module-info.java`:

~~~java
module demo.client {
    requires vault.core;
}
~~~

File `src/demo.client/demo/client/Main.java`:

~~~java
package demo.client;

import demo.vault.Vault;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class Main {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup caller = MethodHandles.lookup();

        System.out.println("reads: "
                + Main.class.getModule().canRead(Vault.class.getModule()));
        System.out.println("open: "
                + Vault.class.getModule().isOpen(
                        "demo.vault", Main.class.getModule()));

        try {
            MethodHandles.Lookup target =
                    MethodHandles.privateLookupIn(Vault.class, caller);

            MethodHandle secret = target.findVirtual(
                    Vault.class, "secret",
                    MethodType.methodType(String.class));

            Vault vault = new Vault();
            System.out.println((String) secret.invokeExact(vault));
        } catch (IllegalAccessException ex) {
            System.out.println("Private lookup denied");
        }
    }
}
~~~

In the directory containing `src`, compile and run (Java 17+):

~~~bash
javac --module-source-path src -d out -m vault.core,demo.client
java --module-path out -m demo.client/demo.client.Main
~~~

Output when `vault.core` only has `exports`:

~~~text
reads: true
open: false
Private lookup denied
~~~

The readability relationship exists due to `requires vault.core;`. However, `exports demo.vault;` **does not imply** `opens demo.vault;`; `privateLookupIn` throws `IllegalAccessException` before looking up the method.

Run again while opening the package only to `demo.client`:

~~~bash
java --module-path out \
  --add-opens vault.core/demo.vault=demo.client \
  -m demo.client/demo.client.Main
~~~

The trailing `\` is line-continuation syntax commonly used in Unix shells. On Windows PowerShell, you can write the same command **on one line**:

~~~powershell
java --module-path out --add-opens vault.core/demo.vault=demo.client -m demo.client/demo.client.Main
~~~

Output:

~~~text
reads: true
open: true
ACCESS_GRANTED
~~~

To configure this in module source instead of a runtime flag, update `src/vault.core/module-info.java` to:

~~~java
module vault.core {
    exports demo.vault;
    opens demo.vault to demo.client;
}
~~~

Then **recompile both modules** and run the normal command without `--add-opens`. The target of opening is the **client module**, not the `demo.client` package; the matching names are just an example choice.

> This two-module example requires directory organization and compilation with JPMS. Placing all classes on the classpath and running them moves them into the unnamed module, where package-opening rules differ from an encapsulated named module. Therefore, do not use a classpath demo to "prove" whether a named module is open.

## 7. What Happens to a Lookup When "Teleporting" Across Modules?

`privateLookupIn(Target.class, caller)` is described as **teleporting a lookup** to the target:

- If both classes belong to the **same module**, the result has full-privilege access on the target and `previousLookupClass()` is `null`.
- If transitioning from module `M1` to a different module `M2`, the result has `PRIVATE` but **loses `MODULE`**; `previousLookupClass()` records the original lookup class in `M1`. Java 17 also specifies that the resulting lookup lacks `ORIGINAL`.
- Because `MODULE` is gone, that result cannot be used as `caller` for a second `privateLookupIn` to yet another class/module. Deep-access privileges cannot be chained across modules this way.

To inspect this in `Main` of Example 2, after successfully creating `target` you can add:

~~~java
System.out.println("target lookup class: "
        + target.lookupClass().getName());
System.out.println("previous lookup class: "
        + target.previousLookupClass().getName());
System.out.println("has MODULE: "
        + ((target.lookupModes() & MethodHandles.Lookup.MODULE) != 0));
~~~

The snippet above is a **fragment**, runnable only when `target` is created across two different modules; `previousLookupClass()` is non-`null` in that case:

~~~text
target lookup class: demo.vault.Vault
previous lookup class: demo.client.Main
has MODULE: false
~~~

Do not apply this snippet mechanically to the same-module case, because `previousLookupClass()` can be `null` then. Once a valid `MethodHandle` is obtained, Java primarily checks the call types and invocation feasibility of the handle; it does not re-run the `privateLookupIn` privilege check on every `invoke`. Thus, a handle to a private member is an object that must be managed carefully.

## 8. Comparison with Reflection `setAccessible(true)`

Traditional Java Reflection can use `getDeclaredMethod`, `getDeclaredField`, and `setAccessible(true)`; Method Handles create a handle directly from a `Lookup`. Both are bound by the module system's **strong encapsulation**, though the timing and checking APIs differ.

| Aspect | Traditional Reflection | Method Handles |
| --- | --- | --- |
| Finding members | `Class.getDeclaredMethod` / `getDeclaredField` | `Lookup.findVirtual` / `findVarHandle` |
| Requesting deep access | `setAccessible(true)` or `trySetAccessible()` | `MethodHandles.privateLookupIn(...)` |
| Module keeps package closed | May throw `InaccessibleObjectException` / fail to set accessible | `privateLookupIn` may throw `IllegalAccessException` |
| Execution | `Method.invoke`, `Field.get/set` | `MethodHandle.invokeExact/invoke`, `VarHandle.get/set` |
| Error style on call | `InvocationTargetException` may wrap method errors | MethodHandle generally propagates method throwables directly; type mismatches also need handling |

Do not interpret `privateLookupIn` as a "bypass" equivalent to `setAccessible(true)`. Both operate only within the bounds Java permits. A library needing cross-version compatibility should ask the data-owning module to **selectively open** only the needed package, rather than recommending `open module` or `--add-opens` for all packages by default.

## 9. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| `IllegalAccessException` in `privateLookupIn` | Caller lacks `PRIVATE`/`MODULE`, lacks `reads`, or target package is not `opens` | Print `lookupModes()`, `canRead`, `isOpen`; check descriptor/flags |
| `IllegalArgumentException` in `privateLookupIn` | Target is primitive, void, or array | Pass the `Class` of a real class/interface |
| `IllegalAccessException` in `findVirtual` after obtaining lookup | Member not accessible by lookup or wrong permissions/context chosen | Check which lookup is actually used and the declaring class |
| `NoSuchMethodException` in `findVirtual` | Wrong name/`MethodType` or wrong overload | Verify **both return type and parameter list** of `MethodType` |
| `NoSuchFieldException` in `findVarHandle` | Field name or field type mismatch | Verify the exact field type |
| `WrongMethodTypeException` on handle call | Type mismatch at `invokeExact` call site or unsuitable adapter type | Compare `handle.type()` with receiver/argument/return types |
| `ClassCastException` on handle call | Runtime object incompatible during conversion | Check receiver and argument types |
| `InaccessibleObjectException` from `setAccessible` | Package not opened for deep reflection | Open the package to the exact target or choose a public API |
| Works on classpath but fails on module path | Difference between unnamed module and named modules | Run a true JPMS sample; check `module-info.java` |

Short diagnostic checklist (the following lines are a **fragment** inside a class that has imported `MethodHandles` and knows `Target`):

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();
Module from = caller.lookupClass().getModule();
Module to = Target.class.getModule();
String pkg = Target.class.getPackageName();

System.out.println("PRIVATE: "
        + ((caller.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
System.out.println("MODULE: "
        + ((caller.lookupModes() & MethodHandles.Lookup.MODULE) != 0));
System.out.println("reads: " + from.canRead(to));
System.out.println("opens: " + to.isOpen(pkg, from));
~~~

Here `Target` is an existing target class in the program, not a hypothetical API name. Checking these properties helps identify which privilege is missing **before** attempting a private access operation.

## 10. Safe Design with Modules and Method Handles

1. **Own the package-opening grant at the target module.** Prefer `opens package to trusted.module;` if a library truly needs deep reflection. For ordinary interaction, provide public APIs via `exports` or service interfaces.
2. **Create lookups in trusted locations.** `MethodHandles.lookup()` must be called in caller-module code with the proper privileges; a lookup obtained from `publicLookup` or an untrusted plugin cannot elevate itself.
3. **Request only the needed members.** Once you have a private lookup, create the exact `MethodHandle`/`VarHandle`s required; do not store and distribute the full lookup when only narrow operations are needed.
4. **Separate permission checks from business errors.** `IllegalAccessException` when creating a lookup differs from `WrongMethodTypeException` when invoking a handle and errors thrown by the target method itself.
5. **Do not infer permissions from package names.** Module identity, `reads`, and `opens` are runtime conditions. Packages sharing the same name in two modules do not automatically share access rights.
6. **Do not indiscriminately open JDK packages.** When diagnosing `java.base` errors, consider supported APIs instead of using `--add-opens java.base/...=ALL-UNNAMED` in production.

A privileged `Lookup` is a delegatable capability. When one module opens a package to another module, the receiving module can create handles to private members in the opened package; this decision affects your application's encapsulation boundaries.

## 11. Self-Check Questions

1. Does `publicLookup()` have enough privilege to call `privateLookupIn`? **No**, because it lacks `PRIVATE` and `MODULE`.
2. Do two classes in different packages within the same named module require `opens`? **Not merely for being in different packages**; `privateLookupIn` with a full-privilege caller can create a private lookup within the same module.
3. The client module already has `requires vault.core;` and the target package is `exports`ed—can private members be invoked now? **Not yet**; the package must also be `opens` to the client if across modules.
4. Who receives access from `--add-opens vault.core/demo.vault=demo.client`? **Module `demo.client`**, not every module; a caller lookup with the required modes is still needed.
5. What is lost when `privateLookupIn` transitions between two named modules? **The `MODULE` mode** on the resulting lookup; `previousLookupClass()` records the prior lookup class.
6. Why does the same source code sometimes behave differently on the classpath vs. the module path? **The unnamed module opens packages**, whereas named modules have `exports`/`opens` descriptors and checked readability relationships.
7. Does a `MethodHandle` that was already created successfully need `privateLookupIn` called again before each `invokeExact`? **No**; you must invoke the handle with the exact signature and keep the granted capability safe.

## 12. Official Documentation

- [Java SE 17 — MethodHandles and privateLookupIn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [Oracle Java 17 Migration Guide — --add-opens](https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html)

**Remember:** `privateLookupIn` succeeds only when the caller lookup holds **`PRIVATE` + `MODULE`**; if the target is in another module, **`reads`** and **`opens`** for the exact package/module are also required. `exports` only enables using public APIs, not opening private members. Once access is granted, `MethodHandle`/`VarHandle` is an executable capability that must be managed carefully.