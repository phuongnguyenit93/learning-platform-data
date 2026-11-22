# `MethodHandles.Lookup`: Permissions Are Checked at Handle Creation

In Java, a `MethodHandle` is a typed reference to a method or constructor; a `VarHandle` is an object that provides type-checked access operations on variables, fields, or array elements. To obtain a handle to a **named member** (method, constructor, field), we typically use `java.lang.invoke.MethodHandles.Lookup`. The key point: **access permissions are checked when creating the handle; once you hold a valid handle, invoking it does not repeat Java access checks on the target member**. Invocation is still subject to type checks, operation constraints, and exceptions thrown when the target code runs.

This is why `Lookup` is both a member-lookup tool and a **delegated capability**: it carries the context and access level of the code that created it. Understanding this boundary helps you write libraries, frameworks, Reflection/MethodHandle code, and code interacting with the Java Platform Module System (JPMS) correctly and safely.

## 1. What Access Context Does `Lookup` Hold?

`MethodHandles.Lookup` is the object used as a "factory" to create handles. It records:

- **Lookup class**: the class whose access rights are evaluated; retrieved via `lookup.lookupClass()`.
- **Lookup modes**: the active access levels, such as `PUBLIC`, `PACKAGE`, `PROTECTED`, `PRIVATE`, `MODULE`; the bitmask can be inspected via `lookup.lookupModes()`. Having these bits does not mean access is granted to every class/member in any module.
- **Module context**: module readability relationships, `exports`/`opens` packages, and—for a lookup transferred to another module—the previous lookup context can also affect access scope.

Permissions are determined by the **calling class that created the `Lookup`**, the lookup modes, the accessibility of the target class, and the target member. Naming a `Lookup` variable `admin` or passing a different `Class<?>` into a search method does not elevate privileges.

### Three Common Ways to Obtain a Lookup

| Method | Scope and Effect | Limitations to Remember |
| --- | --- | --- |
| `MethodHandles.lookup()` | Lookup bound to **the class executing this call**; normally has full rights corresponding to that class, including private members of the class/nestmates and access permitted by Java | Cannot automatically read `private` members of another top-level class just because it is in the same package; cannot bypass encapsulation of another module |
| `MethodHandles.publicLookup()` | Lookup restricted to eligible `public` classes/members; useful when a library only needs public APIs | Cannot access `private`/`package-private` members; under JPMS, it only sees public APIs in unconditionally exported packages |
| `MethodHandles.privateLookupIn(Target.class, callerLookup)` | Creates a lookup with private access capabilities to `Target` **if** `callerLookup` is allowed to perform deep reflection on that class | The source lookup must have `PRIVATE` and `MODULE`; across modules, module readability must also hold and the target package must be `opens` to the caller's module |

`lookup.in(Target.class)` only **switches the lookup context with potentially narrowed privileges**—it is not a command that grants private access. Switching to another nest, package, or module can drop the corresponding modes. `dropLookupMode(...)` can also intentionally reduce privileges. To access private members of another class, use `privateLookupIn` when eligible rather than treating `in` as a shortcut.

## 2. When Are Permissions Evaluated?

Consider the flow of looking up a method via `findVirtual`:

1. Caller code creates or receives a `Lookup`; the lookup retains the class identity and access modes.
2. The code requests `lookup.findVirtual(Target.class, "work", MethodType.methodType(ReturnType.class, ...))`.
3. Java resolves the class/member and **checks access**: whether `Target` is visible, whether the member is allowed under the lookup's modes, and whether other module/protected constraints hold.
4. If valid, the API returns a `MethodHandle` with a defined type. If not, **handle creation** fails, usually with `IllegalAccessException` for insufficient permissions or `NoSuchMethodException` for an unmatched method search.
5. Any code that receives the handle can invoke it according to the handle's type and invocation rules, even if that code could not have created an equivalent handle itself. **There is no new private access check on each invocation.**

APIs that typically check access at creation time include `findStatic`, `findVirtual`, `findSpecial`, `findConstructor`, `findGetter`, `findSetter`, `findVarHandle`, `findStaticVarHandle`, and several forms of `unreflect`. When calling `unreflect` from a Reflection object whose accessible flag was modified, behavior also depends on the API's rules; you should not infer that every `Lookup` bypasses access checks.

For `VarHandle`, passing the access check when obtaining the handle does not mean **every access mode** is available: for instance, calling `set` through a VarHandle on a `final` field is generally unsupported and may throw `UnsupportedOperationException`. Support for get/set/atomic operations and type correctness of each operation remain call-time constraints.

### Separating Handle Creation Errors from Handle Invocation Errors

| Phase | Example | Meaning |
| --- | --- | --- |
| **Creation** | `findVirtual` requests a private member that the lookup is not permitted to see | `IllegalAccessException` |
| **Creation** | Name, method kind, or `MethodType` signature not found | `NoSuchMethodException` (for methods); wrong field lookup may throw `NoSuchFieldException` |
| **Invocation** | `invokeExact` is called with parameter/return types that do not exactly match the handle's type | `WrongMethodTypeException` |
| **Invocation** | Argument value requires a reference cast but is incompatible | `ClassCastException` may occur |
| **Invocation** | The target method itself throws an exception | The target method's exception is propagated according to handle invocation rules |

`invokeExact` requires the descriptor at the call site to match the handle's type exactly; `invoke` permits certain valid type adaptations. That difference is **invocation-time type checking**, not re-granting private read permissions. In addition, `MethodHandle.asType(...)` creates a type-adapted handle without looking up the private member again, so no new `Lookup` is required for that adaptation.

## 3. Java 17+ Example: Allowed to Create Handle, Not Allowed to Look Up Private Directly

Save the following example **as-is** to `LookupAccessDemo.java`. The file contains two top-level classes; `SecretBox` is **not** a nested class/nestmate of `LookupAccessDemo`. This matters because nestmates in modern Java can share private access under their own rules.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;

public class LookupAccessDemo {
    public static String greeting() {
        return "hello";
    }

    private static void consume(MethodHandle handle, SecretBox box)
            throws Throwable {
        // consume does not have permission to look up SecretBox.message() itself.
        // However, it is allowed to use the handle that was handed to it.
        String value = (String) handle.invokeExact(box);
        System.out.println("delegated: " + value);
    }

    public static void main(String[] args) throws Throwable {
        MethodType noArgsString = MethodType.methodType(String.class);

        MethodHandles.Lookup publicView = MethodHandles.publicLookup();
        MethodHandle greetingHandle = publicView.findStatic(
                LookupAccessDemo.class, "greeting", noArgsString);
        System.out.println("public: " + (String) greetingHandle.invokeExact());

        MethodHandles.Lookup caller = MethodHandles.lookup();
        try {
            caller.findVirtual(SecretBox.class, "message", noArgsString);
            System.out.println("unexpected success");
        } catch (IllegalAccessException expected) {
            System.out.println("normal lookup: denied");
        }

        MethodHandles.Lookup privateView =
                MethodHandles.privateLookupIn(SecretBox.class, caller);

        MethodHandle secretHandle = privateView.findVirtual(
                SecretBox.class, "message", noArgsString);

        SecretBox box = new SecretBox();
        System.out.println(
                "private lookup: " + (String) secretHandle.invokeExact(box));

        consume(secretHandle, box);

        VarHandle countHandle = privateView.findVarHandle(
                SecretBox.class, "count", int.class);
        System.out.println("private VarHandle: " + (int) countHandle.get(box));

        try {
            publicView.findVirtual(SecretBox.class, "message", noArgsString);
            System.out.println("unexpected success");
        } catch (IllegalAccessException expected) {
            System.out.println("public lookup: denied");
        }

        System.out.println(
                "receiver count: " + secretHandle.type().parameterCount());
    }
}

class SecretBox {
    private int count = 7;

    private String message() {
        return "secret=42";
    }
}
~~~

Run in a terminal with JDK 17 or newer:

~~~bash
javac LookupAccessDemo.java
java LookupAccessDemo
~~~

Standard output:

~~~text
public: hello
normal lookup: denied
private lookup: secret=42
delegated: secret=42
private VarHandle: 7
public lookup: denied
receiver count: 1
~~~

Point-by-point explanation:

- `publicLookup().findStatic(...)` succeeds because `LookupAccessDemo` is a public class and `greeting()` is a public static method. The resulting handle has type `()String`.
- `caller` is the lookup of `LookupAccessDemo`; it can access members matching that class's permissions, **and cannot access `private` members of `SecretBox`** even though both classes are in the same package.
- `privateLookupIn(SecretBox.class, caller)` succeeds in this example within the same unnamed module with a sufficiently privileged source lookup. Afterward, `findVirtual` creates a handle for `SecretBox.message()` and `findVarHandle` creates a handle for the `count` field.
- The `consume` method only **receives** the handle. It does not need to perform the lookup itself or undergo another private access check during `invokeExact(box)`. That is **delegating a capability** to other code.
- `publicView` lacks permission to find `SecretBox.message()`; moreover, `SecretBox` is a package-private type, so the class itself does not meet the visibility requirement of a public lookup.
- `MethodType.methodType(String.class)` describes the **declared parameters** of `message()` (no parameters). However, the handle created by `findVirtual` needs the `SecretBox` receiver in the first position, so the handle has type `(SecretBox)String` and `parameterCount()` equals `1`.

Note: the `catch (IllegalAccessException ...)` blocks here intentionally test **unauthorized access at handle creation time**. Do not use exceptions as a general application authorization mechanism; if a member does not exist or has the wrong signature, you must handle the corresponding lookup error types.

## 4. Comparison with Reflection and Other Privilege Options

With core Reflection, `Method.invoke` generally performs access checks at invocation time according to Reflection's mechanism (the `AccessibleObject` state can affect it); with a handle successfully created through `Lookup`, subsequent invocations do not repeat the Java access check for the original member. Therefore:

- `getDeclaredMethod("hidden")` can retrieve the metadata of a private method, but **finding a method** is different from **having permission to call it** or **having permission to create a MethodHandle** for it.
- `setAccessible(true)` is not a skeleton key to bypass JPMS at will: deep access is still restricted by modules, and `InaccessibleObjectException` may occur.
- `lookup.findVirtual(...)` checks permissions when obtaining the handle; `handle.invokeExact(...)` checks the descriptor and runs the target code. Do not conflate the two moments.
- Handing a `MethodHandle` to a private method or a `VarHandle` to a private field to a plugin/callback is equivalent to **granting the ability to use that member**. Hiding the method/field name after passing the handle does not revoke the capability.
- Handing over an entire privileged `Lookup` object is even broader: the recipient can request **other handles** within the lookup's permission scope. If you only want to expose a chosen behavior, provide a narrow handle or a wrapper API instead of a privileged lookup.
- If you need to run with fewer privileges, deliberately use `publicLookup()`, `dropLookupMode(...)`, or a public API designed for consumers; module `exports`/`opens` must be considered carefully.

When using `MethodHandle` in frameworks, identify who creates the lookup, which class is the lookup class, whether the target class's package is read/opened/exported appropriately, and who receives the handle. The ability to create a handle and the ability to use a handle are two distinct permission boundaries.

## 5. Common Misconceptions

| Misconception | Fact |
| --- | --- |
| “`MethodHandles.lookup()` lets you access private members of any class in the same package.” | A lookup has permissions bound to the **calling class**; private members of another top-level class require a valid mechanism such as `privateLookupIn`. |
| “`publicLookup()` can read any `public` member regardless of class/module.” | The enclosing class must be accessible and the module/package must satisfy public visibility rules. |
| “`lookup.in(Target.class)` elevates privileges to `Target`'s private members.” | `in` can **drop** modes; it does not increase privileges. |
| “`exports` is enough to access private members across modules.” | `exports` serves public APIs; cross-module deep reflection requires `opens` and other lookup conditions. |
| “Every `invokeExact` re-checks whether the caller has private permissions.” | Access checks for the member happen when **creating** the handle; invocation checks types and runs the code. |
| “Once a VarHandle is created, you can always call `set`.” | Access modes also depend on variable kind, `final`, and supported features. |
| “Passing a private handle to a third party is harmless.” | The recipient can use the granted handle; delegation scope must be controlled. |

### Self-Check Questions

1. If `A` and `B` are two top-level classes in the same package, why can't `MethodHandles.lookup()` from `A` directly use `findVirtual` to open a private method of `B`?
2. Why does `privateLookupIn` succeed within the same module, yet can fail between two named modules even when the target class is `public`?
3. When `findVirtual` succeeds and the handle is passed to code unaware of the target class, when are member permissions checked? And when are argument types checked?
4. Why does `findVirtual(SomeClass.class, "f", MethodType.methodType(String.class))` create a handle with one extra receiver parameter compared to `findStatic` for a zero-argument method?

**Conclusion:** `Lookup` determines **who may create a handle to which member**; a successfully created handle is a capability that can be used or delegated. Access checks occur when creating the handle, while type checks, operation support, and target exceptions still apply when using the handle. Grasping this boundary is key to using `MethodHandle`/`VarHandle` properly with Java 17+ and JPMS.

*Reference documentation: [Java SE 21 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) and [Java SE 21 — MethodHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html).*