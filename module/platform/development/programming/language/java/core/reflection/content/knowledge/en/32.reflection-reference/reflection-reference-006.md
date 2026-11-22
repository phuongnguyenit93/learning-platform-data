# Access Control Table by Modifier, Package, Nest, and Module in Java Reflection

## 1. Four Layers to Evaluate When Accessing a Member via Reflection

When using `java.lang.reflect.Method`, `Field`, or `Constructor`, the question "Can it be accessed?" does not depend only on `public`/`protected`/`private`. Distinguish **four layers**:

1. **Finding metadata**: do `getMethod`/`getDeclaredMethod` or `getField`/`getDeclaredField` return a reflective object?
2. **Java language access**: the member's modifiers; visibility of the declaring class; package, subclass, and **nestmate** relationship of the caller.
3. **JPMS module boundaries** (Java 9+): is the package `exports`ed to the calling module; when deep reflection is needed, is it `opens`ed?
4. **Invocation state**: is the receiver of the right type, are arguments valid, and does the reflective object have the suppress-access-check flag set?

**Having metadata ≠ having permission to use it**. For instance, `getDeclaredMethod("secret")` can return a private method, yet `Method.invoke` can throw `IllegalAccessException` when the calling code lacks permission and has not been allowed to suppress access checks.

This article is an **access control reference table** for Java 17+, prioritizing distinguishing the public API contract from contextual factors that alter the outcome.

## 2. Summary Modifier Table Without Bypassing Access Checks

Assume the member resides in a **class the caller can access** and package/module gates are already satisfied. This table describes permissions under Java language access control, **before considering `setAccessible(true)`**.

| Member Modifier | Declaring class itself | Another class in the same nest | Another class in the same runtime package, different nest | Subclass in a different package | Unrelated class in a different package |
| --- | --- | --- | --- | --- | --- |
| `public` | Yes | Yes | Yes | Yes | Yes |
| `protected` | Yes | Yes | Yes | Yes, **with receiver/qualified access conditions** | No |
| No modifier (*package-private*) | Yes | Yes | Yes | No | No |
| `private` | Yes | Yes, because *nestmate* | No | No, unless also a nestmate | No |

**Conditions for reading the table:**

- "Same package" at runtime does not mean merely matching package name strings. Classes must belong to **the same runtime package**, typically considering both package name and *defining classloader*. Two plugins with identically named packages defined by separate classloaders are not automatically considered the same runtime package.
- `protected` in a subclass **in a different package** does not simply allow calling on any superclass instance. Access to instance members has receiver conditions: in a subclass `S` context, the qualified receiver must generally be of type `S` or a subtype of `S`. Permission to invoke a protected instance method on a plain superclass instance is not automatically granted just because the caller is a subclass.
- `private` since Java 11 has **nest-based access control** semantics: classes in the same nest can access each other's private members (when runtime constraints are met), without needing `setAccessible` solely because they are different classes.
- Access to the **declaring type** must still be valid. A public method inside a non-public class does not automatically become callable from a class in another package just because the method has the `public` modifier.
- For code in **different named modules**, the table above also requires the JPMS gate (Section 5). Module `exports` does not turn `private` or package-private members into public ones.

### Note on Package-Private

There is no `package-private` keyword in Java. A member declared without `public`, `protected`, or `private` normally has package access. Example:

```java
class Example {
    String packageName() { return "default access"; }
}
```

This is a fragment, not a complete program. This access **does not depend** on subpackage names: `com.app` and `com.app.tools` are **two different packages**. Being in the same module but different packages also does not automatically grant package-private access.

## 3. Nestmate: Private Members Can Be Accessed Between Classes in the Same Nest

A **nest** is a group of classes regarded by the JVM as having the same nest host. For nested classes (`Outer`, `Outer.Inner`, `Outer.StaticNested`), they are typically in the same nest and permitted to access each other's private members. Nest support has been in the JVM since Java 11 (JEP 181).

Lookup APIs:

- `Class#getNestHost()`: returns the class serving as the nest host.
- `Class#getNestMembers()`: returns the nest members of the class according to runtime info.
- `Class#isNestmateOf(Class<?>)`: checks whether two classes belong to the same nest.

Do not use `getEnclosingClass()` comparisons or class names containing `$` as a substitute for nestmate checks. Dynamically loaded classes, bytecode variants, or classes not nested in Java source must rely on actual runtime metadata.

**Same nest differs from same package.** Another top-level class in the same package as `Outer` does not automatically gain permission to call `Outer.Inner` private members. Conversely, nestmates do not need to call `setAccessible(true)` to perform private access already permitted by Java.

In reflection, checks are evaluated against **the actual caller class** of caller-sensitive APIs. If `Method.invoke` is executed inside a nestmate, it can succeed; if the exact same `Method` object is handed to another top-level helper outside the nest and invoked from there, it can throw `IllegalAccessException`. Do not confuse the permissions of where **metadata is obtained** with the permissions of where **the call is executed**.

## 4. Runnable Java 17+ Example: Same Package Differs from Same Nest

The program has two top-level classes in **the same file**, in the *unnamed package* for illustration. `AccessMatrixDemo.Vault` and `AccessMatrixDemo.NestPeer` are in the same nest; `PackagePeer` is another top-level class, in the same runtime package but **a different nest**.

Save the entire code below into **`AccessMatrixDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;

public class AccessMatrixDemo {
    public static class Vault {
        public String everyone() { return "public"; }
        protected String family() { return "protected"; }
        String samePackage() { return "package"; }
        private String secret() { return "secret"; }
    }

    public static class NestPeer {
        public static String readSecret(Vault target) throws Exception {
            Method secret = Vault.class.getDeclaredMethod("secret");
            return (String) secret.invoke(target); // Same nest, without calling setAccessible.
        }
    }

    public static void main(String[] args) throws Exception {
        Vault target = new Vault();
        System.out.println("nestmates: "
                + Vault.class.isNestmateOf(NestPeer.class));
        System.out.println("nest private: "
                + NestPeer.readSecret(target));
        System.out.println("package-private: "
                + PackagePeer.readPackage(target));
        System.out.println("protected same package: "
                + PackagePeer.readProtected(target));
        System.out.println("private from non-nest: "
                + PackagePeer.readPrivate(target));
        System.out.println("public call: "
                + Vault.class.getMethod("everyone").invoke(target));
        System.out.println("declared finds private: "
                + (Vault.class.getDeclaredMethod("secret") != null));
        System.out.println("getMethods finds private: "
                + Arrays.stream(Vault.class.getMethods())
                        .anyMatch(m -> m.getName().equals("secret")));
        System.out.println("unnamed module: "
                + !Vault.class.getModule().isNamed());
    }
}

// Another top-level class: same package, but NOT in the same nest as Vault.
class PackagePeer {
    static String readPackage(AccessMatrixDemo.Vault target)
            throws Exception {
        Method m = AccessMatrixDemo.Vault.class
                .getDeclaredMethod("samePackage");
        return (String) m.invoke(target);
    }

    static String readProtected(AccessMatrixDemo.Vault target)
            throws Exception {
        Method m = AccessMatrixDemo.Vault.class
                .getDeclaredMethod("family");
        return (String) m.invoke(target);
    }

    static String readPrivate(AccessMatrixDemo.Vault target)
            throws Exception {
        Method m = AccessMatrixDemo.Vault.class
                .getDeclaredMethod("secret");
        try {
            return (String) m.invoke(target);
        } catch (IllegalAccessException ex) {
            return ex.getClass().getSimpleName();
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac --release 17 AccessMatrixDemo.java
java AccessMatrixDemo
```

Output:

```text
nestmates: true
nest private: secret
package-private: package
protected same package: protected
private from non-nest: IllegalAccessException
public call: public
declared finds private: true
getMethods finds private: false
unnamed module: true
```

**Explanation:** `NestPeer` can call `Vault.secret` because the two classes are in the same nest. `PackagePeer` is in the same package, so it can invoke package-private and protected methods, but calling private is disallowed. `getDeclaredMethod` still **finds** the private method; `getMethods` only lists public methods and does not retrieve private members. The example runs on the **classpath** (unnamed module), so the last line is `true`. For named modules, see the `module-info.java` configuration in Section 5.

Running on JDK 17 or newer suffices; the program does not use `--add-opens` and does not call `setAccessible`.

## 5. JPMS: `exports` and `opens` Are Not Synonymous

The **Java Platform Module System (JPMS)** adds module-level control since Java 9. For named modules, a package is the boundary for two important directives:

- `exports pkg;`: exposes the **public types and public/protected members accessible under Java rules** of the package to permitted modules. `exports pkg to some.module;` restricts to specified modules. It supports normal access and reflection for the eligible public surface; it does not automatically grant deep reflection to private members.
- `opens pkg;`: allows **deep reflection at runtime** into the package under the conditions of `AccessibleObject.setAccessible/trySetAccessible`. `opens pkg to tool.module;` opens only to the specified module. It **does not automatically grant permission to reference types in source code** like `exports`.
- `open module my.module { ... }`: opens every package of the module for deep reflection; opening the entire module is a broad scope, so consider a narrower `opens pkg to tool.module`.
- An `opens` **does not force** a tool to use private fields; tools should still maintain their own allowlist/authorization policies.

### Matrix Between Two Named Modules

Assume the calling module is `client.module`, the declaring class resides in `library.module`, and both modules are properly resolved. This table describes **cross-module boundary permissions** for public classes/members or enabling deep reflection, while Java language modifiers still apply.

| Package State in `library.module` Relative to Caller | Use Normal Public API | Can `getDeclared...` Discover? | `trySetAccessible` for Private Member from Another Module | Remarks |
| --- | --- | --- | --- | --- |
| `exports api;` or `exports api to client.module;` | Yes when member/type is public and language conditions are met | Can find metadata when `Class<?>` is available | **No** if the package is not simultaneously open | Public export differs from deep access |
| `opens internal;` or `opens internal to client.module;`, not exported | Does not turn internal types into static-use API | Can find metadata when `Class<?>` is obtained | **Possible**, if `setAccessible` conditions are met | Targeted at framework reflection |
| Both `exports` and `opens` | Yes under public contract | Possible | Possible | Broader permissions |
| Neither `exports` nor `opens` | Does not allow ordinary clients to use public types in this package | Having `Class<?>` does not auto-grant permission | **No** | Not bypassed by `getDeclared...` |
| Caller and declaring class **in the same module** | Still obeys Java modifiers | Possible | `setAccessible(true)` can generally suppress modifier checks | Same module does not mean direct private access between non-nest classes |

**Subtle note:** Access checks performed by `AccessibleObject` differ in one point from ordinary language rules: **reflection assumes the caller's module has readability to the declaring class's module** (see Javadoc). When **compiling/referencing statically** from another named module, `requires` dependencies and package `exports` remain relevant conditions. Do not equate the ability to reflect via an already-obtained class name with the ability to `import` the type in source code.

### Two Illustrative `module-info.java` Snippets

Suppose a library provides package `com.example.api` to apps and opens an internal package to a framework:

```java
// library's module-info.java; configuration example, does not run standalone.
module example.library {
    exports com.example.api to example.client;
    opens com.example.internal to example.serializer;
}
```

An application referencing the library's public API:

```java
// client's module-info.java; configuration example.
module example.client {
    requires example.library;
}
```

`example.client` can access the public API in `com.example.api`; `example.serializer` can use deep reflection on `com.example.internal` when calling `setAccessible` within the opened package scope, while still requiring corresponding access, class loading, and API conditions. This code is a **configuration fragment**; building requires creating full modules/packages and concrete sources. Do not treat `opens` as a safe delegation mechanism for untrusted code.

### Named, Unnamed, Automatic, and Open Modules

On the **classpath**, classes typically belong to the **unnamed module**; packages of the unnamed module are treated as exported and open to other modules per the `AccessibleObject` Javadoc. Named modules follow `module-info.java` (aside from extra runtime flags). **Automatic modules** form when placing a plain JAR on the module path, carrying automatic-module export/open characteristics, yet should not be relied upon as a long-term security boundary design; when migrating to an explicit named module, deep reflection outcomes can change.

Launcher options such as `--add-exports`/`--add-opens` can bridge compatibility in managed environments, but these are configuration exceptions, not a reason to use them indiscriminately. Prefer libraries providing public APIs or opening the exact package to the exact framework.

## 6. Table of `setAccessible`, `trySetAccessible`, and `canAccess`

Normally, when `Method.invoke`/`Field.get`/`Constructor.newInstance` is called, access checks are enforced. `AccessibleObject` provides APIs to inspect or enable suppressing checks within JDK limits:

| API | Purpose | Notable Result / Exception |
| --- | --- | --- |
| `member.canAccess(receiver)` | Asks whether **the current caller** can access the member on that receiver | Returns boolean; can throw `IllegalArgumentException` if wrong receiver kind is used (constructor/static need `null`) |
| `member.trySetAccessible()` | Requests enabling the suppress Java access checks flag if permitted | `true` if enabled, `false` if disallowed by access rules; can still throw `SecurityException` depending on configuration |
| `member.setAccessible(true)` | Enables suppressing checks if permitted | Can throw `InaccessibleObjectException` when the module disallows it, or other security errors per environment |
| `member.setAccessible(false)` | Reverts to default access checks | Does not "close" the package or revoke already-issued handle references |
| `member.isAccessible()` | Legacy API querying only the flag state | **Deprecated**; cannot replace `canAccess` |

**The exact contract of `setAccessible(true)` in Java 17** allows caller class `C` to enable access check suppression for a member declared in class `D` if at least one condition holds:

1. `C` and `D` are in **the same module**; or
2. The member is `public`, class `D` is `public`, and `D`'s package is **exported** to `C`'s module; or
3. The member is `protected static`, class `D` is `public`, `D`'s package is exported to the caller module, and `C` is a subclass of `D`; or
4. `D`'s package **opens** to `C`'s module.

If `C` is in another module and `D`'s package is not open to `C`, then `setAccessible(true)` **cannot** be used to enable access to private, package-private, protected instance members, or protected constructors merely from knowing the member name. For non-modifiable `final` fields such as `static final`, record `final` fields, or hidden class `final` fields, setting the flag also **does not grant write permission**.

For instance fields/methods, `canAccess(instance)` requires a matching instance; for constructors/static members, `canAccess(null)` is the appropriate syntax. **`canAccess` is not an auto-fix permission function** and is not a check for whether a method name exists.

Safe example to avoid forcing deep access:

```java
Method m = type.getDeclaredMethod("operation"); // fragment
if (m.canAccess(instance) || m.trySetAccessible()) {
    Object result = m.invoke(instance);
    // Process result
} else {
    // Insufficient permission: fall back to public API or report a clear configuration error.
}
```

This fragment assumes `type`, `instance`, and a zero-argument method are valid, and that the caller handles checked exceptions. In general-purpose libraries, classify error causes, check the receiver first, and avoid blindly calling `trySetAccessible` when handling untrusted code/plugins; technical capability does not imply authorization to read contents.

## 7. `protected` Across Packages: Why Does the Receiver Matter?

Place the superclass and subclass in two packages:

```java
// file base/Parent.java
package base;
public class Parent {
    protected String token() { return "token"; }
}
```

```java
// file child/Child.java
package child;
public class Child extends base.Parent {
    public String onChild() {
        return token(); // Valid: called on the Child instance itself.
    }

    public String onReceiver(Child other) {
        return other.token(); // Valid: allowed receiver.
    }

    // public String wrong(base.Parent parent) {
    //     return parent.token(); // Invalid here: Parent qualifier.
    // }
}
```

These two snippets are **independent fragments by source path**, not part of the single-file runnable example in Section 4. The point is that a subclass outside the package has permission to use protected members within the defined scope, but is not allowed to access protected instance members through arbitrary superclass-typed receivers. Reflection should likewise not be assumed to unconditionally bypass that restriction.

For `protected static` members, checks have specific conditions under `AccessibleObject.setAccessible` rules when crossing modules; they are not constrained by an instance receiver like protected instance methods. When analyzing inheritance across modules, first check whether the declaring type/package is appropriately exported.

## 8. `MethodHandles.Lookup` Has Its Own Permission System and Does Not Automatically Bypass JPMS

`java.lang.invoke.MethodHandles.Lookup` is an object representing lookup/invocation capabilities with context-dependent **access modes**. `MethodHandles.lookup()` creates a lookup according to the class where it is called; `MethodHandles.publicLookup()` is restricted to usable public members.

`Lookup.findVirtual`, `findStatic`, `findGetter`, `findVarHandle`, etc. check permissions when finding a handle. Do not assume `MethodHandle` or `VarHandle` bypasses modifiers or modules simply because the code does not call `Method.invoke` directly.

`MethodHandles.privateLookupIn(Target.class, callerLookup)` can allow looking up private members when the caller has sufficient permissions and appropriate module conditions (including `opens` when crossing modules). It is **not a backdoor** that automatically reads private members in any named module. Do not hand out lookups with broad private permissions to untrusted code.

In some frameworks, a cleaner strategy is to use a public contract/annotation for allowed members, create the needed handles in a privileged context, and provide those handles. Separate metadata discovery from delegated operation capability.

## 9. Reflection Lookup: Declared, Public, Inherited, and Access

| Call | Discovery Scope | Common Pitfall |
| --- | --- | --- |
| `type.getMethod(name, parameterTypes)` | `public` methods of the type, including matching inherited public methods | Does not find protected/package-private/private methods |
| `type.getDeclaredMethod(name, parameterTypes)` | Methods declared **directly** in the type, any modifier | Does not search inherited; returning metadata does not grant call rights |
| `type.getMethods()` | Exposed public methods (including inherited) | Order is not a sorting contract |
| `type.getDeclaredMethods()` | Directly declared methods, including private/protected/package-private | Does not automatically suppress access checks |
| `type.getField(name)` / `getFields()` | Matching public fields (including inherited) | Field hiding requires checking declaring class |
| `type.getDeclaredField(name)` / `getDeclaredFields()` | Directly declared fields, any modifier | Does not pull inherited; no default read permission |
| `type.getConstructor(parameterTypes)` | Public constructor of the type | Constructors are not inherited |
| `type.getDeclaredConstructor(parameterTypes)` | Constructor declared in the type, including private | Still requires access checks when instantiating |

`Modifier.toString(member.getModifiers())` shows the modifier representation. `member.getDeclaringClass()` shows the declaring class. When building tools, remember to filter bridge/synthetic members per context; sometimes they appear in metadata without being part of the public business contract. Obtaining a `Class<?>` via `Class.forName` also does not imply every member inside the class will be accessible.

## 10. Diagnosing by Error Type

| Outcome / Error | Common Cause | How to Handle |
| --- | --- | --- |
| `NoSuchMethodException` | Name or parameter types mismatch; used `getMethod` for a private method | Compare metadata with exact overload, switch to `getDeclaredMethod` when discovering declared members |
| `IllegalAccessException` in `Method.invoke`/`Field.get` | Caller lacks current Java reflection permission | Check modifiers, declaring class, package/nest/module; prefer public API |
| `InaccessibleObjectException` from `setAccessible(true)` | Not allowed to suppress checks across module boundaries | Consider narrowly scoped `opens` or public API design; do not force opening the whole JVM |
| `trySetAccessible() == false` | Could not enable access flag | Handle gracefully, log configuration reason, do not retry endlessly |
| `IllegalArgumentException` from `Method.invoke` | Wrong receiver class, wrong argument count/types, invalid primitive conversion | Check `getDeclaringClass`, `getParameterTypes`, and receiver |
| `NullPointerException` from instance invocation with `null` receiver | Missing receiver for instance member | Check `receiver != null` before calling |
| `InvocationTargetException` | The target method/constructor itself threw an exception | Inspect `getCause()`, do not confuse with access errors |
| `ExceptionInInitializerError` | Static initialization of declaring class failed | Analyze initializer and root cause |

**Do not use `setAccessible(true)` as a universal cure** for every error: wrong receiver, wrong parameter signature, missing member, or exceptions thrown by the target method cannot be fixed by an access flag.

### Investigation Checklist

1. What is `member.getDeclaringClass()`? Is the declaring class actually accessible?
2. What are the modifiers of the member and of the declaring class?
3. In which class/nest/package does the code **calling `invoke/get/set`** reside? Does it have its own permissions?
4. If in a different package: is the caller a subclass? Does the receiver have the right subtype per protected rules?
5. If in a different named module: is the target package `exports`ed or `opens`ed to which module? Is public access or deep access needed?
6. Were `setAccessible`/`trySetAccessible` called, and what was the actual result?
7. Is the receiver a valid instance, do static members use an appropriate receiver, and do arguments match the signature?
8. If running on a JVM with multiple classloaders: do two classes with "the same package name" actually belong to the same runtime package?
9. Are you inadvertently giving untrusted plugins or data permission to inspect/invoke arbitrary private members?
10. Can deep reflection be replaced with an owner-defined interface/public factory/API?

## 11. Common Reasoning Errors

- **"`private` is only accessible inside the exact declaring class":** missing Java 11+ context; nestmates can access each other's private members.
- **"Having the same package name is enough":** runtime package also involves the defining classloader, especially with plugins.
- **"Same module means same package":** false; two different packages in the same module are still subject to package access.
- **"`protected` lets a subclass invoke on any Parent instance":** false across packages for protected instance members.
- **"If `getDeclaredMethod` finds it, `invoke` will definitely succeed":** false; metadata discovery is separate from access, receiver, and argument contracts.
- **"`exports` also enables private reflection":** false; deep reflection from another module typically requires `opens`/a qualifying condition in `AccessibleObject`.
- **"`opens` is like `exports`, apps can `import` any type":** false; `opens` is for reflective access, not compile-time API exports.
- **"`trySetAccessible()` always returns true if the caller has `Class<?>`":** false; strong encapsulation can block it.
- **"`setAccessible(true)` lets you modify any final field":** false; there are non-modifiable final fields (static final, record final, hidden class final) for which the flag grants no write access.
- **"`MethodHandle` bypasses Java security and JPMS":** false; `Lookup` carries and enforces access modes.

## 12. Quick Self-Check

1. `Outer.A` and `Outer.B` are two nestmates, and `A` declares a private method. Can `B` reflectively invoke that method without enabling the accessible flag? **Yes**, if they are in the same nest and other call conditions are valid.
2. Two top-level classes in the same package, different nests, one class has a private field. Can the other read it via `Field.get` without enabling the flag? **No**.
3. `Library` is a named module that exports `api` but does not open `api`; a client module can read the public API, so can it access a private field from the client via `trySetAccessible`? **Not by default**.
4. Does adding `opens internal to framework.module;` let another app automatically `import internal.Hidden` at compile time? **No**.
5. Does a subclass in a different package have access to a protected instance member when the receiver is an arbitrary instance of the superclass? **No, there are receiver/qualifier conditions**.
6. If `getDeclaredMethods()` returns a private member, is it callable by default? **No**.
7. Is `canAccess(null)` suitable for an instance method or a constructor/static member? **Constructor/static**; an instance member requires a receiver belonging to the declaring class.
8. Same class name, same package name, but loaded by two different defining classloaders: do they automatically share package-private access? **No**.
9. A tool needs to read a private field in another named module: is `exports` sufficient? **No**; check `opens` and `AccessibleObject` rules.
10. A reflection call throws `InvocationTargetException`: what should you check first? **`getCause()` to see the error thrown by the target code itself**.

Standard Java 17 Documentation:

- [JLS `6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6)
- [JLS `6.6.2.1 — Access to a protected Member](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6.2.1)
- [JLS `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Javadoc `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Javadoc `Class.getNestHost` / `isNestmateOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Javadoc `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181)
