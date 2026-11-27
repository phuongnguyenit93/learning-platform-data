# `MethodHandles.Lookup` and Lookup Object Permissions in Java 17

`MethodHandles.Lookup` is the object representing the **access context** when Java creates `MethodHandle` or `VarHandle` instances. A lookup object carries the class serving as the starting point for access checks and the set of permissions it is allowed to use.

This matters because Method Handles do not automatically bypass `private`, `protected`, package access, or module boundaries. When calling a method such as `findVirtual` or `findGetter`, Java uses the lookup object's permissions to decide whether to permit creating a handle to that member.

You can picture it as:

```text
MethodHandles.Lookup
       |
       +-- lookupClass()      class serving as access context
       |
       +-- lookupModes()      current lookup permissions
       |
       +-- find... / unreflect...
                 |
                 v
            MethodHandle
                 |
                 v
        invoke permission-checked member
```

Three points to remember:

- **A lookup object is not a global permission.** It represents the permissions of a specific context.
- **Permissions are checked when creating the handle.** A valid `MethodHandle` can be passed elsewhere and can still invoke the member the handle represents.
- **A lookup object can carry powerful privileges.** Do not casually share a lookup with private access to untrusted code or plugins.

`MethodHandles.Lookup` belongs to package `java.lang.invoke` and has existed since Java 7. Module-aware APIs such as `privateLookupIn` were added in Java 9; all of them work in Java 17 without requiring preview flags.

## 1. MethodHandle and Lookup solve two different problems

`MethodHandle` is a typed reference to a method, constructor, field, or callable operation. `Lookup` is the object used to **find and create** those handles under Java access rules.

For example, a class with a public method:

```java
public class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

We can look up a method handle using lookup:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle greetHandle = lookup.findVirtual(
        Greeter.class,
        "greet",
        MethodType.methodType(String.class, String.class)
);
```

Once the handle is created, it can be invoked:

```java
Greeter greeter = new Greeter();

String message = (String) greetHandle.invokeExact(greeter, "An");
System.out.println(message);
```

Output:

```text
Hello, An
```

In this example:

- `lookup` is the object that performs the access check.
- `findVirtual` looks up the instance method `greet`.
- `MethodType` describes the return type and parameter types of the method.
- `greetHandle` is a handle that can be invoked with a `Greeter` receiver and a `String` argument.

With `findVirtual`, `MethodType` describes the method's declared parameters and return type; the receiver is prepended to the handle's invocation type. Thus the actual handle type has the form `(Greeter, String)String`.

**Lookup is not a handle.** Lookup is the tool that creates handles; the handle is the resulting artifact used to perform the operation.

## 2. What information does a Lookup object contain?

`MethodHandles.Lookup` is a static nested class inside `MethodHandles`. A lookup object is bound to:

1. **Lookup class:** the class serving as the access context.
2. **Lookup modes:** the access permissions owned by the lookup object.
3. **Previous lookup class (if any):** information about a prior lookup in certain cases, especially when using `privateLookupIn`.

Important inspection methods:

| Method | Meaning |
|---|---|
| `lookupClass()` | Returns the class serving as the lookup's access context |
| `lookupModes()` | Returns a bit mask representing the available lookup modes |
| `hasFullPrivilegeAccess()` | Checks whether the lookup has full privilege access |
| `hasPrivateAccess()` | Checks whether the lookup has private access; this API is deprecated |
| `previousLookupClass()` | Returns the previous lookup class if present, otherwise `null` |

Example:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

System.out.println(lookup.lookupClass());
System.out.println(lookup.lookupModes());
System.out.println(lookup.hasFullPrivilegeAccess());
System.out.println(lookup.previousLookupClass());
```

When calling `MethodHandles.lookup()` inside class `LookupInfo`, the lookup class is `LookupInfo.class`. It is not the class of an external caller invoking a helper method.

### 2.1. The lookup class determines the access context

Suppose:

```java
package com.example;

import java.lang.invoke.MethodHandles;

public class LookupOwner {
    public static MethodHandles.Lookup createLookup() {
        return MethodHandles.lookup();
    }
}
```

Another class calling `LookupOwner.createLookup()` receives a lookup object whose lookup class is `LookupOwner`, because the `lookup()` call occurs inside `LookupOwner`.

This is crucial: if you want a lookup with private access to a class, the `MethodHandles.lookup()` call must happen in that class's context (or use an appropriate mechanism such as `privateLookupIn` when the module permits). Calling a helper from another class does not turn the lookup into the external caller's lookup.

## 3. Lookup modes and access permission meanings

A lookup object can carry one or more modes. The modes reflect the types of access it is allowed to perform.

| Mode | General meaning |
|---|---|
| `PUBLIC` | Access public members according to module and type rules |
| `PRIVATE` | Access private members in permitted contexts |
| `PROTECTED` | Access protected members according to Java rules |
| `PACKAGE` | Access package-private members within the appropriate package |
| `MODULE` | Permission tied to the lookup class's module, required for certain module-aware operations |
| `UNCONDITIONAL` | Special public permission of a public lookup, applying to unconditionally exported packages |

Modes are represented by constants and bit masks. Do not hard-code mode integers in application logic; use inspection methods such as `hasFullPrivilegeAccess()` or appropriate member-lookup APIs.

### 3.1. Full privilege access

A lookup created directly via `MethodHandles.lookup()` normally has **full privilege access** in the calling class's context. According to the Java 17 API, full privilege access includes the necessary permissions such as private, protected, package, and module access.

`hasFullPrivilegeAccess()` is the clear way to check whether a lookup has full privilege access:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

if (lookup.hasFullPrivilegeAccess()) {
    System.out.println("Lookup has full privilege access");
}
```

Do not confuse full privilege access with being able to access every member of every module. Module boundaries, package accessibility, and each API's conditions still apply. Full privilege is evaluated relative to the lookup class and its module.

### 3.2. Private access does not equal full privilege

A lookup with the `PRIVATE` mode can access private members in its granted context, but that does not necessarily mean it holds all other permissions such as `MODULE`.

In Java 17, `hasPrivateAccess()` is deprecated. If the goal is to check whether a lookup has full privilege access, use `hasFullPrivilegeAccess()`.

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

boolean fullPrivilege = lookup.hasFullPrivilegeAccess();
// Avoid relying on hasPrivateAccess() in new code.
```

## 4. Three common ways to obtain a lookup

The most important factory methods:

| API | General permissions | When to use |
|---|---|---|
| `MethodHandles.lookup()` | Lookup bound to the calling class, normally with full privilege access in that context | Code needing to create handles for members the class itself can access |
| `MethodHandles.publicLookup()` | Public-only lookup | Only needing access to unconditionally exported public APIs |
| `MethodHandles.privateLookupIn(target, caller)` | Creates a lookup with private access to target when module/access conditions are met | Frameworks or libraries needing controlled deep access to another class |

### 4.1. `MethodHandles.lookup()` — lookup of the current class

This is the standard way to obtain a lookup object:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

The lookup class is the class where the call is executed. It has access permissions matching that class's context, including private access to the class and appropriate package/module permissions.

Private method example:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class SecretBox {
    private String reveal() {
        return "classified";
    }

    public static MethodHandle revealHandle()
            throws NoSuchMethodException, IllegalAccessException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        return lookup.findVirtual(
                SecretBox.class,
                "reveal",
                MethodType.methodType(String.class)
        );
    }
}
```

Because the `lookup()` call resides inside `SecretBox`, the lookup has the private permission required to find `reveal`.

Another class can receive the created handle:

```java
SecretBox box = new SecretBox();
MethodHandle reveal = SecretBox.revealHandle();

String value = (String) reveal.invokeExact(box);
System.out.println(value);
```

Output:

```text
classified
```

Key point: code invoking the handle does not need its own private access to `SecretBox`. Access was checked when `revealHandle` created the handle and handed it to the caller. Therefore, sharing a handle also shares the capability to invoke that operation.

### 4.2. `MethodHandles.publicLookup()` — public access only

`publicLookup()` returns a lookup with restricted public permissions. It is appropriate when a library only needs to access public members of public classes in unconditionally exported packages.

```java
MethodHandles.Lookup publicLookup = MethodHandles.publicLookup();

MethodHandle handle = publicLookup.findVirtual(
        String.class,
        "length",
        MethodType.methodType(int.class)
);
```

Invoking the handle:

```java
int length = (int) handle.invokeExact("Java 17");
System.out.println(length); // 8
```

A public lookup has no private access and is not a way to bypass module encapsulation. It cannot access private methods or internal packages that have not been appropriately exported.

### 4.3. Why is publicLookup limited to unconditional exports?

A module can export a package to all modules or only to specific modules:

```java
module com.example.library {
    exports com.example.api;
    exports com.example.spi to com.example.framework;
}
```

`com.example.api` is exported unconditionally. `com.example.spi` is exported only to `com.example.framework`.

`publicLookup()` is a universal public lookup; it does not represent a specific client module to satisfy a qualified export. Consequently, do not assume it can access packages exported only to a designated module.

## 5. Permissions are checked when creating a MethodHandle

Methods such as `findVirtual`, `findStatic`, `findConstructor`, `findGetter`, and `findSetter` perform access checks based on the lookup object.

Example:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle handle = lookup.findStatic(
        Integer.class,
        "parseInt",
        MethodType.methodType(int.class, String.class)
);
```

If the lookup has adequate permission, the handle is created. If not, the lookup method may throw `IllegalAccessException`; if the member is not found or the descriptor type does not match, it may throw `NoSuchMethodException`, `NoSuchFieldException`, or a corresponding error.

Once the handle has been created, invoking the handle does not re-run the full Java access checks performed during member lookup. A handle is a capability object capable of performing the granted operation. At invocation time, the JVM still checks type constraints, receiver, arguments, and other runtime conditions.

### 5.1. A handle's authority is not the call site's authority

The `SecretBox` example in the previous section shows that a caller can invoke a handle to a private method that the caller could not look up using its own lookup.

This establishes a security principle:

> Only pass a MethodHandle when you intend to grant the recipient the capability to perform the operation that handle represents.

Do not expose a handle to a sensitive operation merely because it is convenient for integration. In particular, never hand a full-privilege lookup to a plugin or external code without deliberate intent.

## 6. Finding different kinds of members

`Lookup` provides several `find...` methods. Each method corresponds to a kind of member.

| Method | Member looked up | Example |
|---|---|---|
| `findVirtual` | Instance method called via virtual dispatch | `toString()` |
| `findStatic` | Static method | `Integer.parseInt(String)` |
| `findSpecial` | Method invoked specially per JVM semantics, such as super invocation | Calling a superclass/default method implementation |
| `findConstructor` | Constructor | `new Widget(String)` |
| `findGetter` | Getter handle for an instance field | Reading `object.name` |
| `findSetter` | Setter handle for an instance field | Writing `object.name` |
| `findStaticGetter` | Reading a static field | Reading `Config.VERSION` |
| `findStaticSetter` | Writing a static field | Writing a static field if allowed |
| `findVarHandle` | VarHandle for an instance field | Accessing a field with memory access modes |
| `findStaticVarHandle` | VarHandle for a static field | Accessing a static field |

These methods do not bypass modifiers automatically. The lookup's permissions must be sufficient for the requested member.

### 6.1. findStatic

```java
class MathOps {
    static int doubleIt(int value) {
        return value * 2;
    }
}

MethodHandle doubleIt = MethodHandles.lookup().findStatic(
        MathOps.class,
        "doubleIt",
        MethodType.methodType(int.class, int.class)
);

int result = (int) doubleIt.invokeExact(21);
```

Because `doubleIt` is static, the handle does not take a receiver object.

### 6.2. findConstructor

```java
class Widget {
    private final String name;

    Widget(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

MethodHandle constructor = MethodHandles.lookup().findConstructor(
        Widget.class,
        MethodType.methodType(void.class, String.class)
);

Widget widget = (Widget) constructor.invokeExact("panel");
```

For `findConstructor`, the passed `MethodType` has return type `void.class` and the constructor's parameter types. The resulting handle returns the newly constructed instance.

In this example, the constructor is package-private and the lookup code is in the same package. If the constructor were private, the lookup would require appropriate private access.

### 6.3. findGetter and findSetter

```java
class Profile {
    private String nickname;

    Profile(String nickname) {
        this.nickname = nickname;
    }
}

MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter = lookup.findGetter(
        Profile.class,
        "nickname",
        String.class
);

MethodHandle setter = lookup.findSetter(
        Profile.class,
        "nickname",
        String.class
);
```

If this code is outside `Profile` and in a different package, a regular lookup does not have permission to access the private field `nickname`. The lookup must be performed from a privileged context or using `privateLookupIn` when the module permits.

### 6.4. VarHandle

`VarHandle` is a typed API for reading/writing fields, array elements, or memory regions under various memory access modes. Lookup is also the standard way to obtain a VarHandle:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

class Counter {
    int value;
}

MethodHandles.Lookup lookup = MethodHandles.lookup();

VarHandle valueHandle = lookup.findVarHandle(
        Counter.class,
        "value",
        int.class
);

Counter counter = new Counter();
valueHandle.set(counter, 10);

int current = (int) valueHandle.get(counter);
```

The example above uses a package-private field in the same package. For private fields, appropriate lookup access is still required. VarHandle is not a way to bypass encapsulation; it enforces access rules upon creation.

## 7. `unreflect`: creating a handle from Reflection objects

In addition to `find...`, `Lookup` can create MethodHandles from reflection objects:

- `unreflect(Method)`
- `unreflectConstructor(Constructor<?>)`
- `unreflectGetter(Field)`
- `unreflectSetter(Field)`
- Variants related to VarHandle.

Example:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;

Method method = String.class.getMethod("substring", int.class);

MethodHandle handle = MethodHandles.lookup().unreflect(method);
```

`getMethod` here retrieves the public method `substring(int)`. `unreflect` converts the existing `Method` into a `MethodHandle`, while still enforcing access rules related to the lookup and the reflection object's accessibility state.

Do not assume that merely holding a `Method` object lets you create a handle to any private member. Reflection and lookup access rules must still be satisfied.

### 7.1. When to use find and when to use unreflect?

| Situation | Typically suitable choice |
|---|---|
| Class, member name, and MethodType are known upfront | `findVirtual`, `findStatic`, `findGetter`... |
| Already have a `Method` or `Constructor` from reflection | `unreflect` or `unreflectConstructor` |
| Already have a `Field` and want to read/write via handle | `unreflectGetter` / `unreflectSetter` |
| Need access modes for a field or synchronized variable | `findVarHandle` / `unreflectVarHandle` |

`find...` describes the desired member directly. `unreflect...` is useful when another part of the program has already performed discovery via reflection.

## 8. `Lookup.in` — changing the lookup class and narrowing permissions

`Lookup.in(Class<?>)` creates a new lookup object with the requested lookup class. The new lookup's permissions are adjusted according to the relationship between the old lookup and the new class.

Example:

```java
MethodHandles.Lookup original = MethodHandles.lookup();

MethodHandles.Lookup narrowed = original.in(String.class);

System.out.println(original.lookupClass());
System.out.println(narrowed.lookupClass());
System.out.println(narrowed.lookupModes());
```

Key points:

- `in` is not a way to request more permissions.
- When switching to a different lookup class, modes that no longer apply may be dropped.
- The new lookup does not automatically acquire private access to the target class just because you passed `String.class` or another class.
- Permissions can only be retained or narrowed according to API rules.

Therefore, `in` is useful when you want a lookup with a different context and narrower permissions. It does not replace `privateLookupIn`.

### 8.1. Example showing why in cannot be used to obtain arbitrary private access

Suppose:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandles.Lookup another = lookup.in(SomeOtherClass.class);
```

You cannot conclude that `another` has private access to `SomeOtherClass`. `in` does not turn the caller into the target class itself and does not grant permissions across module boundaries.

If you need private access to another class, you must meet the requirements of `privateLookupIn`.

## 9. `dropLookupMode` — proactively dropping permissions

`dropLookupMode(int)` creates a new lookup object by removing a mode from the current permission set. This is a way to **reduce privileges** under the principle of least privilege.

Example:

```java
MethodHandles.Lookup full = MethodHandles.lookup();

MethodHandles.Lookup publicOnly =
        full.dropLookupMode(MethodHandles.Lookup.PRIVATE);

System.out.println(full.lookupModes());
System.out.println(publicOnly.lookupModes());
```

Dropping one mode may cause dependent modes to be dropped according to API rules. Do not assume the bit mask after dropping differs by only a single bit; if you need to inspect remaining permissions, check via `lookupModes()` or appropriate predicate methods.

Some notes:

- You cannot use `dropLookupMode` to add permissions back.
- The method accepts a valid mode defined by `Lookup`.
- If the mode is not present in the lookup, the result may keep the current lookup unchanged.
- The returned lookup is a separate object with a restricted permission set.

### 9.1. Creating a lower-privilege lookup before sharing

For example, a component that only needs public access:

```java
MethodHandles.Lookup internal = MethodHandles.lookup();

MethodHandles.Lookup apiOnly =
        internal.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

This illustrates the idea of reducing privileges. In real designs, understand the related modes and verify the result; if you only need universal public access, `MethodHandles.publicLookup()` may express the intent more clearly.

## 10. `privateLookupIn` — requesting a lookup with private access to another class

`MethodHandles.privateLookupIn` is a key API when building frameworks, mappers, or libraries that need access to private members of another class.

Syntax:

```java
MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(targetClass, callerLookup);
```

Where:

- `targetClass` is the class that the new lookup will use as its lookup class.
- `callerLookup` is an existing lookup representing the requesting code's permissions.
- The new lookup has private access to target if permission and module conditions are met.

### 10.1. Access conditions

In Java 17, the caller lookup must have appropriate permissions, specifically `PRIVATE` and `MODULE`. If the target class belongs to another module, the package containing the target class must be **open to the caller's module**.

If conditions are not met, the call can throw `IllegalAccessException`.

Points to remember:

1. `privateLookupIn` is not an unconditional private-access API.
2. The target's module must open the package to the caller's module when the two classes are in different modules.
3. `opens` is the module descriptor mechanism used for deep reflection/access.
4. The resulting lookup has the target class as its lookup class and retains the previous lookup class information.
5. When crossing a module boundary, the `MODULE` permission is stripped from the resulting lookup; do not treat it as equivalent to a full-privilege lookup created directly inside the target module.

If target and caller are in the same module, cross-module package opening is not needed, though the caller lookup must still hold the modes required by the API.

### 10.2. Module descriptor example with qualified opens

Module containing the class to access:

```java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.internal
            to com.example.framework;
}
```

Framework module:

```java
module com.example.framework {
    requires com.example.domain;
}
```

`opens com.example.domain.internal to com.example.framework` allows the framework module to perform deep reflection/private lookup into this internal package under module system rules.

With `exports` alone, the framework can access public APIs in the exported package, but does not have deep reflection permission on private members merely from the export.

### 10.3. Creating a private lookup and finding a private method

Suppose the framework has received `Class<?> targetClass` from model registration or reflection:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandles.Lookup caller = MethodHandles.lookup();

MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(targetClass, caller);

MethodHandle handle = targetLookup.findVirtual(
        targetClass,
        "internalValue",
        MethodType.methodType(String.class)
);
```

If the target's package is opened to the framework module and the caller lookup has sufficient permissions, the framework can create a handle to the private method `internalValue`.

Obtaining `Class<?>` and being permitted to access private members are two different things. Having a class object does not automatically mean having permission to access all members of that class.

### 10.4. Why not open the entire module?

You can use `opens` without a module list to open all packages of a module for deep reflection, but doing so weakens encapsulation.

Prefer qualified opens when you know exactly which framework needs access:

```java
opens com.example.domain.internal to com.example.framework;
```

Open only the required package and the required module. Do not use a broad open declaration just to make access errors disappear without understanding the root cause.

## 11. How do `exports` and `opens` affect Lookup?

These two directives have distinct meanings:

- `exports` exposes a package for ordinary access to public types.
- `opens` permits deep reflection into a package, including private access via APIs such as `privateLookupIn` when the remaining conditions are met.

| Module directive | Public API access | Deep reflection/private lookup |
|---|---|---|
| Neither exported nor opened | Other modules cannot access the package as a normal API | Not open for deep reflection from other modules |
| `exports package` | Allows accessing public types in the package per module rules | Does not automatically allow private lookup |
| `opens package` | Does not automatically expose the package for normal import/compile-time API | Allows controlled deep reflection |
| `exports package to M` | Only module M can access the package's public API | Does not automatically allow private lookup |
| `opens package to M` | Does not automatically export the public API | Module M can perform deep reflection |

`privateLookupIn` requires an open package when the target is in another module. Adding `requires` alone in the caller module is not enough to access private members.

### 11.1. Using --add-opens at runtime

In certain operational or diagnostic situations, the JVM supports the `--add-opens` option to open a package at runtime:

```bash
java --add-opens com.example.domain/com.example.domain.internal=com.example.framework \
     --module-path mods \
     -m com.example.framework/com.example.framework.Main
```

This option adjusts package opening in the runtime module graph. It is not the default replacement for module descriptor design. For applications you control, declaring qualified `opens` in the module descriptor expresses the contract more clearly.

## 12. Lookup and reflection: similarities and differences

Reflection and Method Handles can both look up and operate on class members, but their usage models differ.

| Reflection | Method Handles |
|---|---|
| Uses `Class`, `Method`, `Field`, `Constructor` | Uses `Lookup`, `MethodHandle`, `VarHandle` |
| Can enable access override via `setAccessible`/`trySetAccessible` if module permits | Creates handles via lookup with appropriate access permissions |
| Invokes methods via `Method.invoke` | Invokes handles via `invoke`/`invokeExact` |
| Reflective API describing members and metadata | Handle is a typed operation object |
| Access checks can be tied to the accessible state of the reflection object | Permissions are checked when the lookup creates the handle |

### 12.1. Lookup is not a way to bypass strong encapsulation

Example:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle handle = lookup.findVirtual(
        SomeLibraryClass.class,
        "privateOperation",
        MethodType.methodType(void.class)
);
```

If the current class lacks private access and the module does not open the appropriate package, looking up the handle will fail. Method Handles still enforce module access control.

### 12.2. trySetAccessible and privateLookupIn

With reflection, `trySetAccessible()` requires matching module conditions to enable deep access. With Method Handles, `privateLookupIn` creates a lookup object with private access under corresponding conditions.

Both are governed by module encapsulation. Do not treat either API as a shortcut to reach internal implementation details of the JDK or third-party libraries.

## 13. Lookup objects as a security capability

In security design, a **capability** is an object representing the right to perform a specific action. A lookup object and handles created from it exhibit capability-like properties:

- A full-privilege lookup can create handles to many members within its permission scope.
- A handle to a private method allows the recipient to call that method even if the recipient could not look up the method itself.
- A narrowed lookup can only create handles within its remaining permission scope.
- Passing out a lookup or handle means sharing the corresponding authority.

For example, a framework needs to read a private field to map data. Instead of handing the application module's full-privilege lookup to the framework, the application can create a handle for just the needed field and hand over that handle:

```java
MethodHandle nameReader = targetLookup.findGetter(
        Customer.class,
        "name",
        String.class
);

// Only pass nameReader to the component that needs to read the name.
```

The recipient can read the exact field represented by the handle; it does not obtain a lookup to discover arbitrary private members of `Customer`.

### 13.1. Do not share powerful lookups unnecessarily

Avoid:

```java
// Risky design if recipient is untrusted.
plugin.initialize(MethodHandles.lookup());
```

This lookup is created from the calling class and may carry full privilege access. If the plugin retains the lookup, it can create handles within the lookup's permission scope.

Consider:

- Passing only the specific MethodHandles needed.
- Using `publicLookup()` if only public APIs are needed.
- Creating narrowed lookups by dropping unnecessary modes.
- Not opening module packages more broadly than required.
- Drawing clear boundaries between trusted code and plugins.

Not every plugin is untrusted; this is the principle of granting privileges based on minimum need.

## 14. Lookup permissions and common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| `IllegalAccessException` when calling `findVirtual` | Lookup lacks the required mode or package access | Check lookup class, modes, package export/open, and module |
| `NoSuchMethodException` | Wrong method name or `MethodType` | Verify name, parameter types, and return type |
| `NoSuchFieldException` | Wrong field name or field type | Verify exact field declaration and type |
| `privateLookupIn` throws `IllegalAccessException` | Caller lacks PRIVATE/MODULE or target package is not open | Check caller lookup and qualified opens |
| Using `publicLookup` fails to access a qualified-export package | Public lookup does not represent a specific client module | Use an appropriate caller/exported module lookup or design a clear public API |
| `in(targetClass)` cannot access private members | `in` does not grant extra private access | Use `privateLookupIn` when module permits |
| Handle found but invocation throws type error | Receiver/argument types do not match handle type | Check `MethodType` and call-site signature |
| Plugin can invoke a private method after receiving a handle | The handle already carries the access checked at creation | Only share handles when you genuinely intend to grant that capability |

### 14.1. Distinguishing lookup errors from invocation errors

Errors can occur at two points:

**During member lookup:**

```java
MethodHandle handle = lookup.findVirtual(
        Greeter.class,
        "missing",
        MethodType.methodType(String.class)
);
```

If no matching method exists, handle lookup fails, usually with `NoSuchMethodException`.

**During handle invocation:**

```java
String result = (String) handle.invokeExact("wrong receiver");
```

If the call site does not exactly match the handle's type, `invokeExact` may throw `WrongMethodTypeException`. If the receiver is invalid, a corresponding runtime type error may occur.

Do not attribute every Method Handle failure to an access permission error. Identify whether the error occurred during lookup or during invocation.

### 14.2. Inspecting lookup modes when debugging

You can print lookup information:

```java
static void describe(MethodHandles.Lookup lookup) {
    System.out.println("Lookup class: " + lookup.lookupClass().getName());
    System.out.println("Modes: " + lookup.lookupModes());
    System.out.println(
            "Full privilege: " + lookup.hasFullPrivilegeAccess()
    );
    System.out.println(
            "Previous lookup class: " + lookup.previousLookupClass()
    );
}
```

This information helps identify which class a lookup represents and what permissions remain. Do not log or expose powerful lookup objects in production systems merely for debugging; access-related artifacts should also be managed appropriately.

## 15. Complete example: creating narrowed lookups and invoking handles

The following example demonstrates public lookup, the current class's lookup, and a pre-created handle.

Create `LookupDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupDemo {
    public static class Calculator {
        public int add(int left, int right) {
            return left + right;
        }

        private int secretMultiply(int value) {
            return value * 10;
        }

        public static MethodHandle secretHandle()
                throws NoSuchMethodException, IllegalAccessException {
            MethodHandles.Lookup ownLookup = MethodHandles.lookup();

            return ownLookup.findVirtual(
                    Calculator.class,
                    "secretMultiply",
                    MethodType.methodType(int.class, int.class)
            );
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle addHandle = lookup.findVirtual(
                Calculator.class,
                "add",
                MethodType.methodType(int.class, int.class, int.class)
        );

        Calculator calculator = new Calculator();

        int sum = (int) addHandle.invokeExact(calculator, 10, 20);
        System.out.println("Sum: " + sum);

        MethodHandle secretHandle = Calculator.secretHandle();

        int secretResult =
                (int) secretHandle.invokeExact(calculator, 7);

        System.out.println("Private result: " + secretResult);

        MethodHandles.Lookup publicLookup = MethodHandles.publicLookup();

        MethodHandle lengthHandle = publicLookup.findVirtual(
                String.class,
                "length",
                MethodType.methodType(int.class)
        );

        int length = (int) lengthHandle.invokeExact("Java 17");
        System.out.println("Length: " + length);

        System.out.println("Lookup class: " + lookup.lookupClass().getName());
        System.out.println(
                "Full privilege: " + lookup.hasFullPrivilegeAccess()
        );
    }
}
```

Compile and run on JDK 17:

```bash
javac --release 17 LookupDemo.java
java LookupDemo
```

Output:

```text
Sum: 30
Private result: 70
Length: 8
Lookup class: LookupDemo
Full privilege: true
```

Analysis:

1. `lookup` is created in `LookupDemo.main`, so its lookup class is `LookupDemo`.
2. `add` is a public method; the current lookup can create a handle to it.
3. `secretMultiply` is a private method. `Calculator.secretHandle` calls `lookup()` inside `Calculator`, so it has the required private access.
4. The private handle is returned to `main`; the caller can invoke the created handle.
5. `publicLookup` finds `String.length` because it is a public method of a public class in an unconditionally exported package.
6. There is no need to hand `Calculator`'s full-privilege lookup to `main`; only the needed handle is shared.

## 16. Practice exercises

### Exercise 1 — Which class is the lookup class?

```java
class Service {
    static MethodHandles.Lookup lookup() {
        return MethodHandles.lookup();
    }
}

class Client {
    void run() {
        MethodHandles.Lookup lookup = Service.lookup();
    }
}
```

**Question:** Does `lookup.lookupClass()` return `Service.class` or `Client.class`?

**Answer:** `Service.class`. The `MethodHandles.lookup()` call occurs inside the `Service.lookup` method.

### Exercise 2 — Can publicLookup find a private method?

```java
MethodHandles.Lookup lookup = MethodHandles.publicLookup();
```

**Answer:** No. `publicLookup` only has public access within the scope defined by the API; it has no private access.

### Exercise 3 — Is requires enough for privateLookupIn?

A framework module declares `requires com.example.domain`. The domain module does not open the package containing the target class to the framework.

**Question:** Can the framework call `privateLookupIn` to access private members?

**Answer:** Not with `requires` alone. When the target is in another module, the target's package must be opened to the framework module; the caller lookup must also have the required permissions.

### Exercise 4 — in or privateLookupIn?

You have a lookup for class A and want to create a lookup with private access to class B in another module, where B's package is opened to module A.

**Answer:** Use `MethodHandles.privateLookupIn(B.class, lookupA)` if `lookupA` meets the requirements. `lookupA.in(B.class)` is not a way to request additional private access.

### Exercise 5 — Does a handle carry access authority?

Class A creates a handle to a private method of A and passes that handle to class B.

**Answer:** Yes. B can invoke the received handle even though B does not have permission to look up that private method itself. Therefore, passing a handle grants the capability to perform the operation.

### Exercise 6 — Does `requires transitive` open private members?

**Answer:** No. `requires transitive` propagates readability between modules. For deep reflection/private lookup across module boundaries, the target package must be appropriately opened using `opens` or a corresponding runtime option.

### Exercise 7 — Finding a handle type mismatch

A handle has type `(Greeter, String)String`. The call site uses `invokeExact` with arguments `(Object, String)String`.

**Answer:** The call site type does not exactly match the handle type; `WrongMethodTypeException` may occur. With `invokeExact`, the static types at the call site matter.

## 17. Key takeaways

- `MethodHandles.Lookup` represents the **access context and permissions** used to find MethodHandles/VarHandles.
- `lookupClass()` identifies the context class; it depends on where `MethodHandles.lookup()` is called.
- `lookupModes()` reports the mode set; `hasFullPrivilegeAccess()` checks for full privilege access.
- `MethodHandles.lookup()` creates a lookup bound to the calling class.
- `MethodHandles.publicLookup()` provides only public access within unconditionally exported packages.
- `Lookup.in` changes the lookup class and may narrow permissions; it never grants extra private access.
- `dropLookupMode` proactively reduces permissions.
- `privateLookupIn` creates a lookup with private access to a target when the caller has sufficient permissions and the target package is opened if crossing a module boundary.
- `requires` establishes readability; `exports` exposes public APIs; `opens` allows deep reflection.
- Permissions are checked when creating the handle; the handle can subsequently be passed to other code and still perform the granted operation.
- Powerful lookups and handles should be managed like capabilities; share only the exact permissions the recipient needs.

## Official references for Java 17

- [Java SE 17 API — `java.lang.invoke.MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Java SE 17 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Java SE 17 API — `java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Java SE 17 API — `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html).
- [Java SE 17 API — `java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html).
- [Java SE 17 API — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).
- [Java Language Specification 17 — `7.7`: Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7).
- [JEP 261 — Module System](https://openjdk.org/jeps/261).
