# 5.4. Differences in Module Readability Checks Between Reflection and `MethodHandles.Lookup`

In the Java Platform Module System (JPMS), **readability** is a relationship between two modules: module `M1` *reads* module `M2` when `M1` is allowed to depend on types of `M2` according to module rules. However, not all runtime method invocation mechanisms handle readability the same way.

Key takeaways from this lesson:

- **Core Reflection** (`java.lang.reflect.Method`, `Field`, `Constructor`, which extend `AccessibleObject`) **assumes that the readability relationship already exists when performing reflective access checks**. It still checks `public`, `exports`, `opens`, and other conditions; this assumption **does not add a read edge** to the module graph.
- **`MethodHandles.lookup()`** creates a `Lookup` bound to the actual caller. When using methods such as `findStatic`, `findVirtual`, `findGetter`, a regular `Lookup` **checks readability** during handle creation, along with accessibility and lookup modes.
- **`MethodHandles.publicLookup()` is an exception worth remembering**: the `UNCONDITIONAL` mode also assumes readability, but only allows access to public members of public types in **unconditionally exported** packages.
- **`MethodHandles.privateLookupIn(target, callerLookup)`** is not exempt from readability: if the target belongs to another module, the caller module **must read** the target module, **and** the target package must `opens` to the caller module; the caller lookup must also have sufficient `PRIVATE` and `MODULE` privileges.

This lesson uses Java 17+ and an experiment with **two named modules** so you can see a Reflection call succeed while a regular `Lookup` fails, even though they both target the same `public static` method.

## 1. Separating Four Layers of Conditions: resolution, readability, exports, and opens

Before analyzing a call, identify exactly which condition is being questioned.

| Concept | Question it answers | Example |
| --- | --- | --- |
| **Resolution** | Is the module included in the module graph for this run? | `--add-modules m.lib` forces the resolver to select `m.lib` |
| **Readability** | Does the user's module *read* the target module? | `module m.client { requires m.lib; }` or at runtime `--add-reads m.client=m.lib` |
| **Exports** | Does the target package expose **public types/members** to the calling module? | `exports demo.lib;` or `exports demo.lib to m.client;` |
| **Opens** | Does the target package allow **deep reflection** for the calling module? | `opens demo.lib to m.client;` |

These are four **different** conditions. `exports` does not automatically create a `reads` relationship. `opens` does not automatically create a `reads` relationship. A resolved module also does not mean an arbitrary module automatically reads it.

Suppose `m.client` and `m.lib` are two **named modules**. `m.client` wants to use the class `demo.lib.Service` of `m.lib`:

1. The runtime needs a way to load that class, so the target module must be resolved and the appropriate class loader must be able to find the class.
2. A regular Java access or a regular `Lookup` will require the relevant readability and accessibility conditions.
3. If using Reflection, access checks via `AccessibleObject` **assume** the readability step, but still require a `public` class/member in an appropriately `exports`-ed package for regular access.
4. If you want to invoke a private method via deep reflection, the package must be appropriately `opens`-ed and access must be enabled when permitted; `exports` alone is not enough.
5. If you want `privateLookupIn` across module boundaries, **both readability and opens** are required, even if Reflection can already access the private method using `trySetAccessible()`.

The read relationship can be checked at runtime:

```java
boolean readable = callerClass.getModule().canRead(targetClass.getModule());
```

This is an **illustrative code snippet** using existing `callerClass` and `targetClass`; it does not compile into a standalone program. `Module.canRead` indicates the read relationship in the graph at the time of checking; it does not imply that the package is `exports`-ed or `opens`-ed.

> You should not try this experiment with only the classpath: classpath code resides in the unnamed module, which has special readability rules toward resolved modules. Two named modules without `requires` create a clearer scenario.

## 2. Why Can Core Reflection Bypass Missing Readability?

`Method`, `Field`, and `Constructor` are all reflected objects extending `AccessibleObject`. According to the Java SE 17 contract, when a reflected object checks Java language access, it has **one difference** from normal checks: **the module of the code using the reflected object is treated as if it can read the module containing the reflected member**.

For example, if both the target class and method are `public`, the target package is `exports`-ed to the caller, and the caller already has a valid `Class<?>` or `Method`, then `method.invoke(...)` can succeed **even if** `callerModule.canRead(targetModule)` returns `false`.

Limitations:

- The readability assumption applies within the **access checks of reflected objects**; it does not automatically perform `callerModule.addReads(targetModule)`, does not modify `module-info.class`, and does not make unresolved modules available.
- **Visibility** still matters: a private method does not become public just because of the readability assumption.
- **`exports`/`opens`** still matter: a `public` method in a package that is not appropriately exported can be blocked; to use deep reflection to bypass visibility across different modules, the package must be opened to the caller according to the corresponding policy.
- Obtaining metadata (`getMethod`, `getDeclaredMethod`) and actually invoking (`invoke`), reading/writing (`Field.get`/`set`), or creating an instance (`Constructor.newInstance`) are different steps. Finding metadata is not enough to prove the member is accessible.
- `setAccessible(true)` or `trySetAccessible()` is not an all-powerful privilege. If the package is not appropriately `opens`-ed, requesting to suppress access checks for a non-public member across modules can fail.

This property makes Core Reflection useful for tools, frameworks, and code that needs to access dynamically discovered types. It **should not** be understood as all runtime APIs implicitly ignoring module readability.

## 3. `MethodHandles.Lookup`: Privileges Bound to the Lookup Class

`MethodHandles.lookup()` is a caller-sensitive API: the returned `Lookup` stores the **lookup class** as the class calling the API. Methods such as:

```java
lookup.findStatic(targetClass, "run", methodType(void.class));
lookup.findVirtual(targetClass, "name", methodType(String.class));
lookup.findGetter(targetClass, "count", int.class);
```

are **illustrative snippets** using existing `lookup` and `targetClass` variables. These statements create a `MethodHandle` after checking the privileges of the lookup class, `Lookup.lookupModes()`, class/member accessibility, and applicable module relationships. These examples should not be understood as three statements that always succeed.

For a regular `Lookup` with `PUBLIC` mode and no previous lookup class, when accessing a `public` class in another module, the module of the lookup class must **read** the target module; the target package must also be `exports`-ed at least to the module of the lookup class.

`Lookup` has important characteristics:

- **Privileges are checked at method handle creation time.** Once validly created, a method handle does not re-run the same access check on every `invoke`/`invokeExact`. Core Reflection checks privileges when each caller uses the reflected object according to the API's rules.
- `MethodHandles.lookup()` creates a capability representing the caller's privileges. Passing it to other code means granting the right to create handles within the scope that the lookup allows; a full-privilege lookup should not be exposed indiscriminately.
- `lookup.in(Other.class)` does not automatically grant more privileges: when changing the lookup class, modes can be **reduced**; across module boundaries, the previous lookup class can make checks more restrictive.
- `Lookup.lookupModes()` shows the privilege bits, but merely having the `PUBLIC` bit **does not guarantee** that the target module can be read or that the package is exported.

A regular `Lookup` behaves closer to Java/bytecode access semantics than Core Reflection's convenience-first rules.

## 4. Exception: `publicLookup()` with `UNCONDITIONAL`

Do not generalize that **every** `MethodHandles.Lookup` rejects when readability is missing.

`MethodHandles.publicLookup()` returns a minimal-privilege lookup with `UNCONDITIONAL` mode. According to the Java SE 17 API, this mode **assumes readability**, so it can create handles to:

- public members
- belonging to public types
- located in packages that are **unconditionally exported** (`exports some.package;`) from the target module.

Example:

```java
MethodHandles.Lookup openPublic = MethodHandles.publicLookup();
```

This is only an illustrative declaration; the standalone runnable class in section 6 will demonstrate it in full.

`publicLookup()` is not a way to bypass privileges. If a package only has `exports p to m.client` (a qualified export), then `UNCONDITIONAL` **does not** enjoy that export privilege like a normal lookup bound to `m.client`. It also cannot suddenly access `private` members, and does not have the privileges required to use `privateLookupIn` with `publicLookup()` alone.

More precisely:

| Option | Readability check against target module | Other conditions to note |
| --- | --- | --- |
| Core Reflection via `AccessibleObject` | **Assumed present** in the reflected object's access check | Visibility and `exports`/`opens` still apply |
| `MethodHandles.lookup()` + `find*` | **Checked**, based on the lookup class's module (and previous lookup class if any) | Lookup modes and accessibility |
| `MethodHandles.publicLookup()` + `find*` | `UNCONDITIONAL` **assumes present** | Only public types/members in unconditionally exported packages |
| Cross-module `MethodHandles.privateLookupIn(target, caller)` | **Requires** caller module reads target module | Target package **opens** to caller; caller has `PRIVATE` and `MODULE` modes |

This table describes common APIs. Some `Lookup.unreflect*` variants also have their own rules when receiving a reflected object with the accessible flag enabled; see section 9 to avoid mechanical extrapolation.

## 5. Deep Reflection and `privateLookupIn`: Why Is `opens` Not Enough?

Suppose `m.lib` declares:

```java
module m.lib {
    opens demo.lib to m.client;
}
```

This snippet **does not** indicate that `m.client` can read `m.lib`, nor is it an `exports demo.lib` directive for regular Java access. However, if `m.client` has already loaded the appropriate class and is granted deep reflection by `opens`, then `trySetAccessible()` on a private member can succeed.

On the other hand, to run:

```java
MethodHandles.Lookup privateAccess =
        MethodHandles.privateLookupIn(targetClass, MethodHandles.lookup());
```

when `targetClass` is in another module, Java SE 17 requires:

1. The passed-in lookup has appropriate **`PRIVATE` and `MODULE` modes** (full-privilege lookup).
2. The target is a valid class (not primitive/array/`void`).
3. The caller module **reads** the target module.
4. The target module **opens** the package containing the target class at least to the caller module.
5. Other security checks (if present in the environment) do not deny it.

Missing readability will cause `privateLookupIn` to throw `IllegalAccessException` **even when** `Method.trySetAccessible()` for a private method in the same class has returned `true`. When cross-module access succeeds, the new `Lookup` has private privileges on the target but loses `MODULE` mode; one must not assume this lookup can be carried over to hop through multiple subsequent modules.

The core point: **`opens` resolves deep access privileges; `reads` resolves the ability of a module to reference another module under the Lookup mechanism.** One condition does not replace the other.

## 6. Java 17+ Practice: Same Method, Two Different Check Behaviors

Create directories/files with the exact structure:

```text
src/
├── m.lib/
│   ├── module-info.java
│   └── demo/lib/Service.java
└── m.client/
    ├── module-info.java
    └── demo/client/Main.java
```

This is **a multi-module program**. All the files below must be created at the exact paths before running the `javac` command in the parent directory of `src`.

**File `src/m.lib/module-info.java`:**

```java
module m.lib {
    exports demo.lib;
    opens demo.lib to m.client;
}
```

- `exports demo.lib;` allows public, unconditional access to the package's public types.
- `opens demo.lib to m.client;` allows code in `m.client` to request deep reflection on the package, within API limits.
- These two lines **do not** make `m.client` read `m.lib`.

**File `src/m.lib/demo/lib/Service.java`:**

```java
package demo.lib;

public class Service {
    public static String hello() {
        return "hello-from-library";
    }

    private static String hidden() {
        return "hidden";
    }
}
```

**File `src/m.client/module-info.java`:**

```java
module m.client {
}
```

Intentionally **do not** declare `requires m.lib;`, so the client module does not yet have a read edge to the library module. `Main` will look up the class by runtime string name, avoiding direct references to the `Service` type in the client source code.

**File `src/m.client/demo/client/Main.java`:**

```java
package demo.client;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class Main {
    public static void main(String[] args) throws Throwable {
        Class<?> target = Class.forName("demo.lib.Service");

        System.out.println("readable="
                + Main.class.getModule().canRead(target.getModule()));

        // Core Reflection: access check assumes readability.
        System.out.println("reflection="
                + target.getMethod("hello").invoke(null));

        // Deep Reflection: depends on opens, does not require a read edge.
        var privateMethod = target.getDeclaredMethod("hidden");
        System.out.println("open=" + privateMethod.trySetAccessible());
        System.out.println("deepReflection=" + privateMethod.invoke(null));

        var lookup = MethodHandles.lookup();
        try {
            var handle = lookup.findStatic(
                    target, "hello", MethodType.methodType(String.class));
            System.out.println("lookup=" + (String) handle.invokeExact());
        } catch (IllegalAccessException expected) {
            System.out.println("lookup=denied");
        }

        // UNCONDITIONAL: public API + unqualified export.
        var publicHandle = MethodHandles.publicLookup().findStatic(
                target, "hello", MethodType.methodType(String.class));
        System.out.println("publicLookup="
                + (String) publicHandle.invokeExact());

        // privateLookupIn: requires both reads and opens.
        try {
            var privileged = MethodHandles.privateLookupIn(target, lookup);
            var handle = privileged.findStatic(
                    target, "hidden", MethodType.methodType(String.class));
            System.out.println("privateLookup=" + (String) handle.invokeExact());
        } catch (IllegalAccessException expected) {
            System.out.println("privateLookup=denied");
        }
    }
}
```

The `Main` program intentionally catches **only** `IllegalAccessException` for lookup operations that might be denied, and prints `denied`. Other exceptions are propagated via `throws Throwable` to avoid hiding lab setup errors.

### 6.1. Compiling Both Modules

In the directory containing `src`, run:

```bash
javac --release 17 -d mods --module-source-path src src/m.lib/module-info.java src/m.lib/demo/lib/Service.java src/m.client/module-info.java src/m.client/demo/client/Main.java
```

The command above creates compiled modules in `mods/m.lib` and `mods/m.client`; it only requires JDK 17 or higher. The files have no shell-dependent characters, so explicit arguments work in both Bash and PowerShell.

### 6.2. Running WITHOUT a Read Edge

```bash
java --module-path mods --add-modules m.lib -m m.client/demo.client.Main
```

Output:

```text
readable=false
reflection=hello-from-library
open=true
deepReflection=hidden
lookup=denied
publicLookup=hello-from-library
privateLookup=denied
```

`--add-modules m.lib` **resolves** the library module so the class can be loaded; it **does not** add `requires`/`reads` from `m.client` to `m.lib`. `Class.forName` can load the class in the experiment's class loader configuration. This does not mean an unresolved module or any arbitrary class loader can always find that class.

Exact line-by-line analysis:

- `readable=false`: `m.client` does not read `m.lib` according to the module graph.
- `reflection=hello-from-library`: public method in a public class of an unconditionally exported package; **Core Reflection assumes readability in the access check**.
- `open=true`: package `demo.lib` is opened to `m.client`, so `trySetAccessible()` for the private method succeeds. Opening a package still does not create a read edge.
- `deepReflection=hidden`: after validly enabling access, the private method can be invoked reflectively.
- `lookup=denied`: `MethodHandles.lookup()` is bound to the `Main` class in `m.client`; `findStatic` cannot create the handle because the lookup class's module does not read `m.lib`.
- `publicLookup=hello-from-library`: the `UNCONDITIONAL` lookup is allowed to access public members in an unconditionally `exports`-ed package, despite having no read edge.
- `privateLookup=denied`: `privateLookupIn` does not accept missing readability, even though `opens` is already present.

### 6.3. Running WITH a Read Edge

No source changes needed; just add a runtime read edge to isolate the exact variable being tested:

```bash
java --module-path mods --add-modules m.lib --add-reads m.client=m.lib -m m.client/demo.client.Main
```

Output:

```text
readable=true
reflection=hello-from-library
open=true
deepReflection=hidden
lookup=hello-from-library
publicLookup=hello-from-library
privateLookup=hidden
```

Compared to the previous run, only three key lines changed: `readable` from `false` to `true`, `lookup` from `denied` to the public method's result, and `privateLookup` from `denied` to the private method's result. Both Reflection calls and `publicLookup` still succeed as before.

Both runs above were built and tested with `javac --release 17` in a JDK environment supporting Java 17+. The printed values do not depend on hash codes, random module lists, or memory addresses.

In an application with a real module dependency, the standard source expression is:

```java
module m.client {
    requires m.lib;
}
```

This is **the approach to modify the example to create a read edge via the module descriptor**. It is no longer the "missing readability" test case from the first run; when changing `module-info.java`, it must be recompiled.

## 7. Decision Table When Debugging Cross-Module Errors

Keep the exact `m.lib` configuration used in the example: package `demo.lib` is both unconditionally `exports`-ed and `opens`-ed to `m.client`, with public target class and method in the `hello` branch.

| API | `m.client` **does not read** `m.lib` | Has `reads` |
| --- | --- | --- |
| `Module.canRead` | `false` | `true` |
| `target.getMethod("hello").invoke(null)` | Succeeds | Succeeds |
| `target.getDeclaredMethod("hidden").trySetAccessible()` | `true` | `true` |
| `lookup.findStatic(target, "hello", ...)` with `MethodHandles.lookup()` | `IllegalAccessException` | Succeeds |
| `MethodHandles.publicLookup().findStatic(...)` | Succeeds | Succeeds |
| `MethodHandles.privateLookupIn(target, lookup)` | `IllegalAccessException` | Succeeds |

**Do not extrapolate this table to other configurations.** If `exports` is removed, public lookup and Reflection public access may change; if `opens` is removed, deep Reflection and private lookup are restricted. If the library module is not resolved, `Class.forName` may fail from the start. The table's results depend strictly on the stated conditions.

How to diagnose at runtime when you have a `Class<?>` reference:

```java
Module from = Main.class.getModule();
Module to = target.getModule();
String packageName = target.getPackageName();

System.out.println("reads=" + from.canRead(to));
System.out.println("exportedToClient=" + to.isExported(packageName, from));
System.out.println("openedToClient=" + to.isOpen(packageName, from));
```

This is an **illustrative snippet in the context of `Main`**, using `target` from the existing program, not a standalone runnable program. `isExported(..., from)` and `isOpen(..., from)` can return `true` due to unconditional export/open or due to a qualified directive applying to the caller. They do not automatically create readability.

## 8. Differences Easily Overlooked

### 8.1. `exports` Does Not Replace `requires`, `opens` Does Not Replace `--add-reads`

- `requires m.lib` in `module m.client` provides a read edge via the module descriptor.
- `--add-reads m.client=m.lib` provides an additional read edge at runtime, useful for diagnostics or integrations needing adjustment.
- `exports demo.lib` opens the package's public API to all modules, but does not force any module to read `m.lib`.
- `opens demo.lib to m.client` grants controlled deep reflection, without creating a read edge.
- `--add-opens m.lib/demo.lib=m.client` adjusts openness at runtime; it **does not** automatically satisfy the `reads` condition of `privateLookupIn`.
- `--add-exports m.lib/demo.lib=m.client` adjusts export at runtime; it **does not** automatically create a read edge.

For `privateLookupIn` to succeed from another named module, check **readability + opens + lookup privileges** in the exact order, rather than just adding one of the flags.

### 8.2. `publicLookup()` Is Not a "Root Lookup"

`publicLookup()` has few privileges, even though it bypasses the readability check at the `UNCONDITIONAL` level. It only accepts public types/members belonging to **unconditionally exported** packages. `MethodHandles.lookup()` can have more privileges within the caller's own module, but across different modules the read relationship must be considered.

A qualified export such as `exports demo.lib to m.client;` can allow `m.client` to use the public API through an appropriate lookup **when there is a read edge**; however, `publicLookup()` does not represent `m.client` to enjoy an export privilege intended only for `m.client`.

### 8.3. `Lookup.in(...)` Is Not a Way to "Teleport to Gain Privileges"

Example:

```java
MethodHandles.Lookup relocated = MethodHandles.lookup().in(targetClass);
```

This snippet is only an illustration using an existing `targetClass`. It cannot elevate privileges beyond the original capability; changing the lookup class can strip lookup modes. When a lookup is moved across modules, `previousLookupClass()` can participate in checking the allowed scope. A lookup that has crossed into another module cannot automatically be used as a "pass-through ticket" to gain private access to a third module.

### 8.4. `unreflect` Has Its Own Rules for Accessible Reflected Objects

`Lookup.unreflect(Method)` and the `unreflect*` APIs accept a `Method`, `Field`, or `Constructor` already created by Core Reflection. According to the Java SE 17 specification, **if the accessible flag of the reflected object has not been enabled**, the `unreflect` API performs the access check immediately based on the lookup class. When the flag has been validly enabled, some `unreflect*` APIs can rely on the privileges already granted to the reflected object.

That means one must not conclude all `unreflect*` methods behave identically to `findStatic` or `privateLookupIn`. The example in section 6 intentionally uses `findStatic` to test the difference in readability without mixing it with the accessible flag. Specifically, `unreflectVarHandle` always performs the access check based on the lookup class regardless of the `Field`'s accessible flag.

### 8.5. Lookup Fails at Creation Time, Not on Every Handle Invocation

`MethodHandles.Lookup.findStatic` can throw `IllegalAccessException` **right at handle lookup/creation time**. If handle creation succeeds, calling `handle.invokeExact()` does not repeat the same access check for each caller. Conversely, `Method.invoke` performs access checks when the method is invoked, unless privileges have been validly suppressed.

This difference in check timing matters when designing frameworks that cache method handles. A `MethodHandle` with access privileges is a capability that needs to be held and shared in a controlled manner; do not pass a full-privilege `Lookup` to untrusted components.

## 9. Common Mistakes and How to Handle Them

| Misconception / Error | Why it is wrong | How to check |
| --- | --- | --- |
| "Without `requires`, Reflection will definitely fail" | Core Reflection's access checks assume readability | Print `Module.canRead`, then distinguish `exports`/`opens` errors |
| "Since Reflection can call it, `lookup.findStatic` can too" | Regular Lookup still enforces module readability | Check the read edge and lookup modes |
| "`opens` is enough for `privateLookupIn`" | Cross-module `privateLookupIn` also requires **reads** | `from.canRead(to)` and `to.isOpen(pkg, from)` |
| "`publicLookup` checks reads identically to `lookup()`" | `UNCONDITIONAL` assumes readability | Check if the package has an **unqualified export** and public API |
| "`publicLookup` can call a private method in an opened package" | `UNCONDITIONAL` does not have `PRIVATE`/`MODULE` modes | Use `privateLookupIn` with a lookup that has appropriate privileges |
| "If `Class.forName` succeeds, the module is already readable" | Class loading/discovery and module access checks are different | Compare `Class.forName` with `Module.canRead` |
| "If `getDeclaredMethod` finds it, it can definitely be invoked" | Metadata discovery does not equate to invoke privileges | Try appropriate `canAccess`, `trySetAccessible` and handle errors |
| "`--add-opens` fixes every `IllegalAccessException`" | It does not automatically add a read edge or lookup mode privileges | Diagnose `reads`, `exports`, `opens`, and lookup modes separately |
| "A `Lookup` moved across modules can elevate privileges" | Lookup modes can be reduced, and the previous lookup class is checked | `lookupClass()`, `previousLookupClass()`, `lookupModes()` |

When encountering an exception, pay attention to where the error originates:

- `ClassNotFoundException`: the class/module may not be resolved or the class loader cannot find the class.
- `NoSuchMethodException`/`NoSuchFieldException`: the member does not exist with the searched name/signature.
- `IllegalAccessException` from `Lookup.find*` or `privateLookupIn`: may be missing reads, missing exports/opens, wrong Java visibility, or insufficient lookup privileges.
- `InaccessibleObjectException` from `setAccessible(true)`: the package/module does not allow suppressing access checks.
- `InvocationTargetException` from `Method.invoke`: the invoked method itself threw an exception; this is a different error from lookup permission.
- `WrongMethodTypeException` or type mismatch on `invokeExact`: the invocation signature does not match the handle's `MethodType`; not evidence of missing readability.

Do not assume every `IllegalAccessException` has a single cause. In practice, you must examine the module graph, module declarations, and the specific lookup type.

## 10. Diagnostic Workflow for an Access Error on Java 17+

1. **Identify the two modules**: the caller module and the target module. Identify the class declaring the member, the package, `public`/`private`, and the actual API being used.
2. **Check module resolution and class loader**: has the target `Class<?>` actually been loaded? If not, resolve this step first.
3. **Print `canRead`** to see whether the caller has a read edge. Do not infer this relationship from Reflection succeeding.
4. **Check `exports` and `opens`**: public access usually requires appropriate export; deep reflection/private lookup requires openness when crossing modules.
5. **Classify the call**:
   - Core Reflection: readability is assumed in the reflected object's access check; still checks visibility, exports/opens.
   - `lookup().find*`: checks readability based on the lookup context.
   - `publicLookup().find*`: `UNCONDITIONAL`, only unconditionally exported public API.
   - `privateLookupIn`: across modules, must have `reads` + `opens` + `PRIVATE`/`MODULE` modes.
6. **Check when the error is thrown**: when finding the member, when creating the method handle, when enabling `accessible`, or during the actual invoke. Distinguish access errors from method body errors.
7. **Fix according to the proper contract**: add `requires` in the module descriptor when there is a real dependency; provide appropriate `exports`/`opens` when needed; only use runtime flags `--add-reads`/`--add-opens`/`--add-exports` when deployment goals require it and in a controlled manner.

### Self-Check Questions

1. `m.client` does not read `m.lib`, but `m.lib` exports a public package. Can Core Reflection on a public method succeed? **Yes**, if class/member access and other conditions are met.
2. If `m.client` does not read `m.lib`, and the package is opened to `m.client`, will cross-module `privateLookupIn` always succeed? **No**, reads and lookup privileges are still required.
3. Does `publicLookup()` really bypass readability? **Yes, via `UNCONDITIONAL`**, but only for unconditionally exported public APIs.
4. Is `--add-opens` the same as `--add-reads`? **No**. One opens deep reflection privileges, the other creates a read relationship.
5. When calling `lookup.findStatic(...)`, when does the privilege check happen? **At handle creation time**; a validly created handle can be invoked again without per-caller access checks each time.
6. Does `getDeclaredMethod(...)` finding a private method prove that `setAccessible(true)` will succeed? **No**; JPMS can block it.
7. Why does the experiment use two named modules? **To clearly illustrate a missing read edge**; the unnamed module on the classpath has special readability rules.
8. Can `publicLookup()` help call a public member in a package that only has `exports p to m.client`? **Not based on that qualified export alone**, because the `UNCONDITIONAL` lookup requires an unqualified export.

## 11. Official Reference Documentation

- [Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): the **assume readability** rule and `setAccessible`/`trySetAccessible`.
- [Java SE 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()`, and conditions for `privateLookupIn`.
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): module access checks, `UNCONDITIONAL`, `Lookup.in`, and factory/unreflect methods.
- [Java SE 17 — `Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `addReads`, and the module graph.

**Concluding principle:** when comparing access privileges on Java modules, simultaneously ask **"is the module resolved?", "does the caller read it?", "is the package exported/opened?", "does the invocation mechanism use Reflection, regular Lookup, public Lookup, or private lookup?"**. Only by answering all four questions can you accurately explain why the same method can be called via Core Reflection yet denied by `MethodHandles.lookup()`.