# 6.5 lookup, publicLookup, and Lookup Access Modes

## 1. Lesson Objectives

After this lesson, you will be able to:

- Distinguish between `MethodHandles.lookup()` and `MethodHandles.publicLookup()` by **caller class**, access scope, and module boundaries.
- Read `Lookup.lookupClass()`, `lookupModes()`, and `hasFullPrivilegeAccess()`; understand the flags `PUBLIC`, `PRIVATE`, `PROTECTED`, `PACKAGE`, `MODULE`, `UNCONDITIONAL`, and `ORIGINAL`.
- Understand why `Lookup.in(...)` and `dropLookupMode(...)` only **reduce** privileges, while `privateLookupIn(...)` can create a lookup into another class but must satisfy strict conditions.
- Create method handles for public/private methods using Java 17+, explain `IllegalAccessException` errors, and separate access errors from signature errors.
- Properly apply `exports`, `opens`, and `requires` of the Java Platform Module System (JPMS) when cross-module access is needed; avoid exposing a library's private access.

## 2. What is `Lookup`, and why does it have privileges?

`java.lang.invoke.MethodHandles.Lookup` is a **lookup context and access-checking** object used to create `MethodHandle` (or `VarHandle`) instances for methods, constructors, fields, and certain JVM-level operations. For example:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle handle = lookup.findStatic(
        SomePublicClass.class,
        "someStaticMethod",
        MethodType.methodType(String.class));
```

The snippet above is **illustrative code**, assuming `SomePublicClass.someStaticMethod()` is static and returns `String`; it requires importing `java.lang.invoke.*` and handling `NoSuchMethodException` and `IllegalAccessException`. `Lookup` does not perform the invocation itself: it **creates** the handle, and the handle is then invoked using `invokeExact`, `invoke`, or another adapter.

A lookup essentially holds context:

- **Lookup class:** the class that the lookup represents, which can be viewed via `lookup.lookupClass()`.
- **Access modes:** the types of access still permitted, viewed via `lookup.lookupModes()` (a bit mask).
- **Module context:** the module of the lookup class and, when the lookup has crossed modules, possibly a **previous lookup class** for checking module readability.

From a security standpoint, a lookup is a **capability** (a transferable right). Methods such as `findStatic`, `findVirtual`, `findConstructor`, or `findGetter` check access **when creating** the handle. Once created successfully, the handle can be invoked by whoever receives it without re-checking member access against the caller on each invocation. Therefore, handing a `Lookup` with private access or a handle to a sensitive method to untrusted code is a real grant of privilege.

**Distinguishing three objects:** `MethodType` describes parameter/return types; `Lookup` decides **whether linking** to the member is allowed; `MethodHandle` is the linked invocation. Having the right `MethodType` does not mean having sufficient privileges to create the handle.

## 3. `MethodHandles.lookup()`: obtaining the privileges of the class actually calling the API

`MethodHandles.lookup()` is a **caller-sensitive** method: the JVM determines the class that is **executing the call** to `lookup()`. It creates a lookup with full privilege access for that class, including private access to the calling class itself and its valid nestmates.

For example, inside `OrderService`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
boolean belongsToOrderService =
        lookup.lookupClass() == OrderService.class;
```

This is **illustrative code inside `OrderService`**, not a standalone file. With the call placed directly in this class, the variable `belongsToOrderService` is `true`. If you move the `MethodHandles.lookup()` call into a helper and return the lookup from the helper, the lookup class at that point is the **helper**, not `OrderService`.

Consequences:

- `lookup()` can find private members of the calling class itself or its nestmates according to Java rules, but **does not automatically grant private access on every class**.
- When a library wraps a helper `getLookup()` and calls `MethodHandles.lookup()` inside the helper, it returns a lookup with the privileges of the **helper**. This helper cannot be used as a workaround to obtain private privileges of an arbitrary caller.
- `lookup()` creates an object that has the `ORIGINAL` bit (caller provenance) and has `PRIVATE` + `MODULE`, so `hasFullPrivilegeAccess()` returns `true`. The remaining modes follow specific JVM semantics.

For generated code or bootstrap methods, a lookup provided by the JVM to the call context has security significance; you should not fabricate or mistakenly pass a lookup with higher privileges than required.

## 4. `MethodHandles.publicLookup()`: minimal public access

`MethodHandles.publicLookup()` returns a lookup used for **public** members of **public** classes located in packages that are **unconditionally exported** (unqualified export) to all modules. This object has no private, protected, or package-private access, and does not provide full privilege access.

The most common point of confusion: on Java 17, `publicLookup()` has the **`UNCONDITIONAL`** mode, not the privilege set of `lookup()` with `PRIVATE` simply subtracted. `UNCONDITIONAL` allows public access checks in unconditionally exported packages, under a context that assumes the module is readable. A public lookup **does not have access** to look inside closed packages or packages only conditionally exported to specific modules.

Practical examples:

- `publicLookup().findVirtual(String.class, "toUpperCase", MethodType.methodType(String.class))` can create a handle to a public method of `String` in an exported public package.
- `publicLookup()` **cannot** invoke a `private static` method of any class.
- A class declared `public` but located in a package that is **not unconditionally exported** of a named module is still not automatically accessible via public lookup.
- You cannot pass a public lookup into `privateLookupIn(...)` to “elevate” to private access; a public lookup lacks both `PRIVATE` and `MODULE`.

`publicLookup().lookupClass()` is conventionally `Object.class`, but this lookup class **does not grant special privileges** to access internals of `java.lang.Object`. Privileges are still determined by the lookup's modes.

### 4.1. Quick Comparison

| Property | `MethodHandles.lookup()` | `MethodHandles.publicLookup()` |
| --- | --- | --- |
| Bound to | The class **calling** `lookup()` | Minimal public context, lookup class conventionally `Object` |
| Private access to calling class / nestmates | Yes, when Java access is valid | No |
| Public method of public class in unconditionally exported package | Yes, if the corresponding class and module are accessible in the caller context | Yes |
| Public method in conditionally exported package | Yes, **if** the caller module is exported to and module readability conditions are valid | No via unqualified export, because the package is not exported to all modules |
| Package-private / protected access | Yes, when Java access conditions are met | No |
| `ORIGINAL` / `UNCONDITIONAL` | Has `ORIGINAL` when created directly via `lookup()` | Has `UNCONDITIONAL` |
| `hasFullPrivilegeAccess()` | `true` for the original lookup | `false` |
| Sharing with untrusted plugins | High risk, as it grants the caller's access context | Fewer privileges, but capability and callable data still need consideration |

**Note:** “public” in Java does not mean bypassing JPMS. A public member of a public class can still be inaccessible from another module if the package is not properly exported.

## 5. `Lookup` Access Modes

The constants are declared in `MethodHandles.Lookup`. `lookupModes()` returns a **bit mask**, not an ordinal or linear privilege level. A lookup can have multiple bits; reading individual bits must use bitwise AND:

```java
boolean mayAccessPrivate =
        (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
```

This is an illustrative snippet inside code that already has a `lookup` variable. Having the `PRIVATE` bit is a condition on the **kind of access**, not a guarantee that a private member of an arbitrary class is accessible; it also depends on the lookup class, nestmates, module, package, and related checks.

| Mode | Practical meaning in Java 17 | What must **not** be inferred |
| --- | --- | --- |
| `PUBLIC` | Ability to access public members/types within the lookup's module context and access checks. | Does not bypass `exports` / module readability. |
| `PRIVATE` | Private access appropriate for the lookup class and nestmates; a component of full privilege. | Does not grant private access to arbitrary classes. |
| `PROTECTED` | Protected access within the scope permitted by Java, including certain subclass cases. | Cannot invoke protected members of arbitrary classes; instance methods also have receiver type constraints. |
| `PACKAGE` | Package-private access within the appropriate **runtime package**. | Having the same package name string across different class loaders/modules does not automatically make them the same runtime package. |
| `MODULE` | Retains verification context within the lookup class's module, allowing access to public types in the same module even if the package is not exported externally; combined with `PRIVATE` for full privilege. | Does not mean private access to all classes in the module. |
| `UNCONDITIONAL` | Public access under unconditional export rules, assuming readability; this is the mode of `publicLookup()`. | Does not include `PRIVATE` / `MODULE` and cannot read private members. |
| `ORIGINAL` | Marker of provenance for a lookup created for an actual caller (or special VM context), relevant to APIs requiring provenance. | Not a “super privilege” to bypass all access checks. |

### 5.1. Checking Privileges Properly

- `lookupModes()` is appropriate when you need to explain or restrict capabilities. Always compare using a **bit mask**, never compare a hardcoded number as a “privilege level”.
- `hasFullPrivilegeAccess()` checks whether a lookup has **both `PRIVATE` and `MODULE`**. Do not equate it with `ORIGINAL`: `privateLookupIn` can return a lookup with full privilege in the same module but **without** `ORIGINAL`.
- Determine actual access by attempting to look up the **exact member** and handling `IllegalAccessException` in the right place; checking the `PRIVATE` bit alone is not enough for an arbitrary class.
- `lookupClass()` and `previousLookupClass()` help explain the lookup context, especially when a lookup has transitioned across different modules.

Do not write code assuming `lookupModes()` on every JVM is always a specific integer value and branching on that number. The constants `Lookup.PUBLIC`, etc. are the proper way to interact directly with the API.

## 6. Full Example 1 — public/private lookup, `in`, `privateLookupIn`, and dropping privileges

The following example intentionally places `Vault` and `LookupAccessDemo` as **two different top-level classes** in the same source file. Both belong to the unnamed module when run on the classpath, but they are **not nestmates** of each other; this clearly shows that `Lookup.in(Vault.class)` does not grant private access to `Vault`.

Create the file **`LookupAccessDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

class Vault {
    private static String pin() {
        return "8246";
    }
}

public class LookupAccessDemo {
    private static String secret() {
        return "PRIVATE";
    }

    public static String greeting() {
        return "PUBLIC";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup local = MethodHandles.lookup();
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
        MethodType noArgsString = MethodType.methodType(String.class);

        System.out.println("caller is demo: "
                + (local.lookupClass() == LookupAccessDemo.class));
        System.out.println("caller has private: "
                + ((local.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
        System.out.println("public has unconditional: "
                + ((publicOnly.lookupModes()
                        & MethodHandles.Lookup.UNCONDITIONAL) != 0));
        System.out.println("public has private: "
                + ((publicOnly.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));

        MethodHandle secretHandle = local.findStatic(
                LookupAccessDemo.class, "secret", noArgsString);
        System.out.println("own private: " + (String) secretHandle.invokeExact());

        try {
            publicOnly.findStatic(LookupAccessDemo.class, "secret", noArgsString);
            System.out.println("unreachable");
        } catch (IllegalAccessException expected) {
            System.out.println("public lookup private: denied");
        }

        MethodHandle publicHandle = publicOnly.findStatic(
                LookupAccessDemo.class, "greeting", noArgsString);
        System.out.println("public method: " + (String) publicHandle.invokeExact());

        MethodHandles.Lookup moved = local.in(Vault.class);
        System.out.println("in(Vault) has private: "
                + ((moved.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
        try {
            moved.findStatic(Vault.class, "pin", noArgsString);
            System.out.println("unreachable");
        } catch (IllegalAccessException expected) {
            System.out.println("in(Vault) private: denied");
        }

        MethodHandles.Lookup deep =
                MethodHandles.privateLookupIn(Vault.class, local);
        MethodHandle pin = deep.findStatic(Vault.class, "pin", noArgsString);
        System.out.println("privateLookupIn: " + (String) pin.invokeExact());

        MethodHandles.Lookup reduced =
                local.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        System.out.println("reduced has private: "
                + ((reduced.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
        System.out.println("original retains private: "
                + ((local.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
    }
}
```

Compile with Java 17+ API and run:

```bash
javac -encoding UTF-8 --release 17 LookupAccessDemo.java
java LookupAccessDemo
```

Stdout output:

```text
caller is demo: true
caller has private: true
public has unconditional: true
public has private: false
own private: PRIVATE
public lookup private: denied
public method: PUBLIC
in(Vault) has private: false
in(Vault) private: denied
privateLookupIn: 8246
reduced has private: false
original retains private: true
```

**Reading the output step by step:**

1. `local` is created directly inside `LookupAccessDemo.main`, so its lookup class is `LookupAccessDemo` and it has private access to create a handle for `secret()`.
2. `publicOnly` can only find valid public members. Looking up `secret()` throws `IllegalAccessException` **when creating the handle**, before any invocation; looking up `greeting()` succeeds.
3. `local.in(Vault.class)` switches the lookup class to `Vault` but **loses `PRIVATE`** because `Vault` is a different top-level class. It cannot create a handle to `Vault.pin()`.
4. `privateLookupIn(Vault.class, local)` checks the privileges of `local` and module conditions, then creates a lookup carrying private access on `Vault`. In this same-unnamed-module example, reading `pin()` is valid.
5. `dropLookupMode(PRIVATE)` returns a **new lookup** with fewer privileges. The original `local` retains its privileges, illustrating the immutability of lookup capabilities.

In real code, `throws Throwable` on `main` keeps the demo concise; when integrating into a library, separate `NoSuchMethodException`, `IllegalAccessException`, `WrongMethodTypeException`, and exceptions thrown by the target method. `invokeExact` requires the signature at the call site to **match the handle's type exactly**: here the method returns `String` and takes no arguments, so casting `(String)` before `invokeExact()` helps the compiler determine the right return type.

## 7. `Lookup.in(target)`: changing context without escalating privileges

`Lookup.in(Class<?> newLookupClass)` returns a new lookup with the specified lookup class. It can only **preserve or reduce** the access capabilities from the original lookup. Key rules from the Java 17 Javadoc:

- Switching to a different class => loses `ORIGINAL`.
- Moving to a different module => loses `MODULE`.
- Moving to a different package => loses `PACKAGE` and `PROTECTED` per package rules.
- Moving to a class not in the appropriate **package member/nest** scope => loses `PRIVATE` (cannot “borrow private” of the new class).
- If the new class is completely inaccessible to the old lookup => may lose all modes.
- When crossing multiple modules, `previousLookupClass()` helps check readability; “hopping” to a third module can cause all privileges to be lost.

**Key takeaway:** `in(target)` is not a way to open private members on another class. It changes the **point of view** while reducing privileges to prevent capability amplification. When there is a genuine need to access private members of another class, see `privateLookupIn` and the JPMS conditions in section 9.

### 7.1. Common mistakes when using `in`

- Taking `MethodHandles.lookup().in(Target.class)` and assuming it has all private privileges of `Target`.
- Comparing classes by package name alone, ignoring class loaders and modules.
- Assuming that `in` into an exported package will restore `PACKAGE`/`PRIVATE` that were previously lost. **Lost privileges are not automatically restored** by another `in` call.
- Treating `Lookup.in` as “just changing the class name” without re-checking `lookupModes()`; changing context can alter the access level and `find...` results.

## 8. `dropLookupMode(mode)`: intentionally reducing privileges

`dropLookupMode(int modeToDrop)` creates a lookup with fewer privileges, convenient when a framework needs to pass a subset of capabilities to less trusted code. There is no need to manually assemble a `Lookup` by reflecting internal constructors (the JDK provides no public API for doing so).

The difference between “clearing one bit” and “reducing according to rules”:

- `dropLookupMode(PRIVATE)` also drops `ORIGINAL` and `PROTECTED`; typically `PUBLIC`, `MODULE`, and `PACKAGE` remain.
- `dropLookupMode(PACKAGE)` drops both `PACKAGE` and `PRIVATE` (along with `ORIGINAL`/`PROTECTED`), because private access cannot remain valid when package access is dropped under API rules.
- `dropLookupMode(MODULE)` additionally removes `MODULE`, `PACKAGE`, and `PRIVATE`; a normal lookup is left with only module-checked public access.
- `dropLookupMode(PUBLIC)` from a normal lookup drops all access modes.
- `publicLookup().dropLookupMode(UNCONDITIONAL)` also produces a lookup with no remaining access privileges.

For a non-public lookup, `dropLookupMode` always drops `ORIGINAL` and `PROTECTED`, even when the requested mode to drop is a different mode. Therefore **do not predict the result with `oldModes & ~mode`**; the Javadoc defines the dependency rules among modes.

Only **one valid mode constant** may be passed (`PUBLIC`, `MODULE`, `PACKAGE`, `PROTECTED`, `PRIVATE`, `ORIGINAL`, or `UNCONDITIONAL`). Using an invalid value or attempting to pass a bitwise OR of multiple modes can throw `IllegalArgumentException`. You can chain multiple calls if you want to drop multiple kinds of privileges, while accepting these dependency rules.

**Note on least privilege:** even a reduced lookup is still a capability. If a framework only needs to let an extension invoke one permitted method, it is usually clearer to **keep the Lookup in trusted code and hand out only a controlled `MethodHandle`** or a narrow interface. Do not pass a broad lookup just to save a few lines of glue code.

## 9. `privateLookupIn(target, caller)` and JPMS

`MethodHandles.privateLookupIn(Target.class, callerLookup)` creates a new lookup targeting `Target`, **with potential private access** to the target after verifying conditions. This is an API for libraries/frameworks that legitimately need deep access, not an unconditional “bypass”.

### 9.1. Required Conditions

For `callerLookup`:

1. The caller lookup must have **both `PRIVATE` and `MODULE`** — meaning `hasFullPrivilegeAccess()` is `true`.
2. `Target.class` must be a suitable class/interface, not a primitive type, `void`, or an array.
3. If target and caller are in the **same module**, the API can return a lookup with full privilege on the target (but **without** `ORIGINAL`).
4. If target is in a **different module**, the caller's module must **read** the target module and the target module must **open** the package containing the target to the caller module.
5. After crossing to another module, the resulting lookup has `PRIVATE` but **no `MODULE`**; therefore it cannot be reused to perform another cross-module deep lookup in the same way.

If privileges are insufficient, `privateLookupIn` throws `IllegalAccessException`. You should not “fix” this by automatically adding `--add-opens` on every package in production; instead, design public interfaces, exported/opened packages by contract, or clear module integration.

### 9.2. Differences between `exports` and `opens`

| Declaration in `module-info.java` | Primary meaning | Effect |
| --- | --- | --- |
| `exports api;` | Exposes the package's public API to **all modules** for normal access. | Suitable for `publicLookup` if the class and member are public and other conditions are satisfied. |
| `exports api to consumer;` | Exports the public API only to the named modules. | A public lookup under `UNCONDITIONAL` does **not** treat this as an unqualified export. |
| `opens internal to tool;` | Allows **deep reflection** on the package for module `tool`. | Can allow cross-module `privateLookupIn` if readability and caller privileges exist. |
| `opens internal;` | Deep reflection on the package for other modules, not restricted to a specific list. | Broader than necessary if only one tool/framework needs to read private members. |
| `requires core;` | The caller module declares readability of module `core`. | Required for cross-module `privateLookupIn` alongside the target's `opens`. |

Example of an **illustrative module configuration**, consisting of **two separate `module-info.java` files**, not a single compilable file:

```java
// Module core.inventory:
module core.inventory {
    exports inventory.api;
    opens inventory.internal to tools.reader;
}

// Module tools.reader:
module tools.reader {
    requires core.inventory;
}
```

The logic in `tools.reader` once it has a `Class<?> targetType` object representing a class in package `inventory.internal`:

```java
// Illustrative snippet inside a class belonging to module tools.reader:
MethodHandles.Lookup own = MethodHandles.lookup();
MethodHandles.Lookup target =
        MethodHandles.privateLookupIn(targetType, own);
```

In the snippet above, `MethodHandles` requires importing `java.lang.invoke.MethodHandles`. With a public target class in an unexported package, the reader module can obtain `Class<?>` through an appropriate discovery mechanism without needing code to directly import a class from the internal package. The **reads + opens** condition determines whether deep lookup is possible; having only `requires` or only `exports` does not substitute for `opens`.

When an application runs on the **classpath/unnamed module**, many same-module operations can succeed that would be blocked in a named-module deployment. Therefore, you must test with the actual packaging, module path, and opens/exports configuration. Depending on the case, `--add-opens target.module/pkg=caller.module` can help with diagnostics or compatibility, but should not be treated as the default privilege design.

### 9.3. When NOT to use `privateLookupIn`?

- If the member is already **public** and the package is exported, you can create the handle from an appropriate existing lookup without needing private privileges.
- If the library provides an official API or factory, use that API instead of forcing the package to be `opens`.
- If the caller lookup has already had `dropLookupMode(MODULE)` or `dropLookupMode(PRIVATE)` called on it, `privateLookupIn` will fail; it is not a way to restore dropped privileges.

## 10. Full Example 2 — `lookup()` context belongs to the helper, not the helper's caller

A common design mistake is writing a utility method that returns a lookup and assuming the lookup automatically has the privileges of the class **calling the utility method**. The following example proves the difference with a real check.

Create the file **`CallerContextDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

class LookupFactory {
    static MethodHandles.Lookup provide() {
        return MethodHandles.lookup();
    }
}

public class CallerContextDemo {
    private static String hidden() {
        return "hidden";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup own = MethodHandles.lookup();
        MethodHandles.Lookup fromFactory = LookupFactory.provide();

        System.out.println("own context: "
                + (own.lookupClass() == CallerContextDemo.class));
        System.out.println("factory context: "
                + (fromFactory.lookupClass() == LookupFactory.class));

        MethodType type = MethodType.methodType(String.class);
        System.out.println("own hidden: " + (String) own
                .findStatic(CallerContextDemo.class, "hidden", type)
                .invokeExact());

        try {
            fromFactory.findStatic(CallerContextDemo.class, "hidden", type);
            System.out.println("unreachable");
        } catch (IllegalAccessException expected) {
            System.out.println("factory hidden: denied");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CallerContextDemo.java
java CallerContextDemo
```

Stdout:

```text
own context: true
factory context: true
own hidden: hidden
factory hidden: denied
```

**Explanation:** `LookupFactory.provide()` calls `MethodHandles.lookup()` itself, so the result has `LookupFactory` as its lookup class, not `CallerContextDemo`. The two classes are in the same package in the example, but they are different top-level classes and **not nestmates**; the helper does not automatically gain access to private methods of `CallerContextDemo`.

For a framework to access private members of a user class, the framework must receive a **validly handed-over lookup context** or use `privateLookupIn` under the right conditions, rather than assuming a helper can acquire all privileges on its own.

## 11. How do access checks, type errors, and privilege errors differ?

Consider the call:

```java
MethodHandle mh = lookup.findVirtual(
        String.class,
        "substring",
        MethodType.methodType(String.class, int.class));
String result = (String) mh.invokeExact("hello", 2);
```

This is **illustrative code inside a method that declares `lookup`**, assuming `MethodHandle` and `MethodType` are imported and exceptions are handled. `findVirtual` creates a handle with `String` as the **first receiver**; the full type of the handle is `(String, int)String`. The result is `"llo"`.

Note three independent layers:

1. **Does the member exist and is the search signature right?** `findVirtual`/`findStatic` can throw `NoSuchMethodException` if no method with a matching type is found. `findGetter`/`findSetter` can throw `NoSuchFieldException`.
2. **Does the lookup have permission to create the handle?** If the class/member is not accessible in the lookup context, `find...` throws `IllegalAccessException`; this is a **handle-creation** error, not an invocation error.
3. **Does the call site match the handle's type?** `invokeExact` requires an exact type match; a mismatch can throw `WrongMethodTypeException`. `invoke` can apply supported conversions, but does not remove basic type checking. Exceptions thrown by the target method itself are propagated through the handle as execution errors.

**Do not use `catch (Exception) { ... }` and treat every case as a permission error.** Separate configuration/member-name errors, access policy errors, and execution type errors for easier diagnosis.

## 12. Using `Lookup` in Frameworks and Plugins

### 12.1. Framework needing to call a provider's public API

A plugin interface has public methods in an exported module. The framework can look up a `MethodHandle` using a lookup with sufficient public privileges without opening private APIs. Avoid starting with `privateLookupIn` when the public API already meets the requirement.

### 12.2. Serializer/ORM needing to read private fields

If accessing private fields is mandatory, the framework can receive permission from the application module (qualified `opens`) and create a lookup with `privateLookupIn`. Even better, if public accessors or contract-based code generation are available, the need for deep reflection can be reduced. Cache `VarHandle`/`MethodHandle` after access checking; do not attempt to open privileges repeatedly on every request.

### 12.3. DSL/dynamic language runtime

The runtime can link an operation name at runtime into a method handle. `MethodType` represents the signature, `Lookup` verifies the context, and `CallSite`/`invokedynamic` can hold the dynamic linkage. Privilege conditions still apply; a dynamic runtime does not automatically gain permission to call private members.

### 12.4. Sharing capabilities with extensions

Do not pass the core's full-privilege lookup directly into an untrusted plugin API. Use a lookup with fewer privileges when appropriate, or a narrow interface/handle that only permits approved operations. Remember that **once a private handle has been created, whoever receives the handle can usually use it**, even if the core later uses a different lookup with fewer privileges.

## 13. Common Mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| “`publicLookup` has the `PUBLIC` bit and all public members are callable” | Java 17 `publicLookup` uses the `UNCONDITIONAL` mode, restricted to unconditionally exported packages. | Check public class, public member, and JPMS exports. |
| “`lookup()` is JVM-wide admin privilege” | Privileges are tied to the class actually calling the API and Java access rules. | Check `lookupClass()`, target member, and module. |
| “`lookup.in(Target.class)` gets private access to Target” | `in` only preserves/reduces privileges; a different class can lose PRIVATE. | Use `privateLookupIn` when conditions are met, or a public API. |
| “Dropping a mode is just `mask & ~bit`” | `dropLookupMode` cascades, dropping ORIGINAL/PROTECTED and dependent modes. | Call the official API and inspect the resulting modes. |
| “`hasFullPrivilegeAccess()` allows reading privates in any module” | Full privilege is tied to the caller context; cross-module also requires `reads` + `opens`. | Define valid modules and handle `IllegalAccessException`. |
| “`exports` and `opens` are the same” | `exports` serves ordinary public API access; `opens` is for deep reflection. | Choose the module declaration according to the access type needed. |
| “Changing `Lookup` privileges after issuing a handle revokes old handles” | Access is checked when the handle is created; an issued handle is an independent capability. | Protect/revoke at the application layer; do not issue sensitive handles arbitrarily. |
| “A wrong `invokeExact` type is a permission error” | A signature mismatch throws `WrongMethodTypeException`, distinct from `IllegalAccessException` at lookup time. | Check `handle.type()` and the caller descriptor. |
| “A factory returning a lookup has the privileges of the code calling the factory” | `lookup()` is caller-sensitive to where **`lookup()` is actually called**. | Pass a valid lookup from the caller if a trusted API requires it. |

Beyond member privileges, class loading/class visibility, module readability, and nestmate structure can all affect the outcome. If classpath tests pass while module-path tests fail, compare the module descriptors before adding privilege-widening workarounds.

## 14. Self-Check Questions

**Q1.** When writing `MethodHandles.lookup()` in `ServiceA`, can the lookup invoke a private method of `ServiceB`?

**A:** Not by default. The initial lookup belongs to `ServiceA`; private access only follows valid relationships such as the same class or nestmates. If `ServiceB` is outside that scope, another mechanism like `privateLookupIn` must be used and its conditions must be met.

**Q2.** Why can `publicLookup()` invoke a public method of `String`, yet cannot invoke a public method of a public class in an unexported package?

**A:** A public lookup is restricted to public classes and members in **unconditionally** exported packages. Being a public class/member is not enough if JPMS blocks the package.

**Q3.** How does `lookup.in(Target.class)` differ from `privateLookupIn(Target.class, lookup)`?

**A:** `in` switches context and only preserves or reduces privileges. `privateLookupIn` grants a new lookup with private access on the target after checking full privilege and module/opens conditions; it does not succeed automatically.

**Q4.** When calling `dropLookupMode(PRIVATE)`, why are `ORIGINAL` and `PROTECTED` also lost?

**A:** `dropLookupMode` has dependent privilege rules, rather than simply clearing the requested bit. The Java 17 Javadoc specifies the additional loss of those modes.

**Q5.** In named modules, what does `privateLookupIn` across modules require?

**A:** The caller lookup must have `PRIVATE` and `MODULE`; the caller module must **read** the target module; the target module must **open** the package containing the target to the caller. After crossing modules, the lookup no longer has `MODULE` or `ORIGINAL`.

**Q6.** If a private handle has already been created and passed to other code, does invoking it re-check the private access of the new caller?

**A:** Member access was already checked when the handle was created. The recipient of the handle can invoke it within its type and behavioral limits; therefore, do not hand private handles or high-privilege lookups to untrusted code.

## 15. Key Takeaways

- **`lookup()`:** caller-sensitive, bound to the class actually calling the API; the original lookup has `ORIGINAL` and full privilege within its valid scope.
- **`publicLookup()`:** minimal capability, `UNCONDITIONAL` mode, only for public APIs of public classes in unconditionally exported packages.
- **Access modes are not a numeric hierarchy:** `lookupModes()` is a bit mask; `PRIVATE`, `PACKAGE`, `PROTECTED`, `MODULE`, `PUBLIC`, `UNCONDITIONAL`, and `ORIGINAL` each have distinct meanings.
- **`in` / `dropLookupMode` only reduce privileges.** `privateLookupIn` grants a lookup to a target if and only if the privilege and module conditions are satisfied.
- **Access is checked at handle creation**, so protect both the lookup and the created handle. With modules, distinguish `exports` and `opens`, and prefer the least-privileged API needed.

### Official Java SE 17 Documentation

- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, `publicLookup`, `privateLookupIn`, and full-privilege rules.
- [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access modes, `in`, `dropLookupMode`, `lookupClass`/`previousLookupClass`, and module access.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): access checking at creation, invocation types, `invokeExact`, and `invoke`.
- [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): representation of method handle signatures.
- [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): module structure, readability, and `exports`/`opens` relationships.
