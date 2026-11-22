# How Does IllegalAccessException Differ from InaccessibleObjectException in Java Reflection?

When using Reflection to read fields, invoke methods, or instantiate objects, developers often run into two similarly named errors:

- `java.lang.IllegalAccessException`: the Reflection operation **is not permitted to access a member** under the applicable access rules.
- `java.lang.reflect.InaccessibleObjectException`: the program **attempted to request bypassing access checks via Reflection, but the JVM did not allow enabling that permission**, usually due to strong encapsulation in the Java Platform Module System (JPMS).

The two exceptions answer **two different questions**. `IllegalAccessException` usually occurs when **performing the operation on the member**; `InaccessibleObjectException` usually occurs when **trying to open Reflection access before the operation**, such as with `setAccessible(true)`. They can involve the same member, yet they are not synonymous and cannot be fixed by the same measure in every case.

## 1. Understand the Access Model Before Looking at the Errors

In Java, there are two important layers of rules:

1. **Java language access permissions**: `public`, `protected`, package-private (no modifier), `private`, and class/package/subclass/nestmate relationships.
2. **JPMS module boundaries (Java 9+)**: a package belonging to a named module can be **exported** to support public API access, or **opened** to allow Reflection deeper access into non-public members.

Reflection can still find metadata about a member using `getDeclaredMethod(...)`, `getDeclaredField(...)`, or `getDeclaredConstructor(...)` even when **invoking/reading/writing** that member is denied. “Seeing metadata” does not mean “having permission to use the member.”

Example:

```java
Method method = type.getDeclaredMethod("secret"); // Retrieve metadata.
method.invoke(target);                            // Perform the call; may fail.
```

This is an **illustrative snippet**, assuming `type` and `target` already exist. At `invoke`, the JVM checks the caller's access permissions if access checks have not been validly suppressed.

### The Role of AccessibleObject

`Method`, `Field`, and `Constructor` extend `AccessibleObject`. Their APIs have distinct meanings:

- `canAccess(receiver)`: checks whether the current caller has permission to access the member with the given receiver. For static members/constructors, the receiver must follow the API's specific contract, usually `null`.
- `trySetAccessible()`: attempts to enable access-check suppression for the Reflection object; returns `true` if successful, `false` if it cannot be enabled due to access constraints. Certain specific security checks can still throw an exception.
- `setAccessible(true)`: requests suppression of access checks; if it cannot be enabled due to module rules, it may throw `InaccessibleObjectException`.
- `setAccessible(false)`: disables access-check suppression previously enabled on that Reflection object; it does **not** modify the class/member's modifiers.

The name `setAccessible(true)` is misleading: it is **not** a command that turns a `private` method into `public` or opens a package globally. It only affects that `AccessibleObject` instance within what the JVM permits.

## 2. IllegalAccessException: Blocked When Reading, Writing, Invoking, or Instantiating

`IllegalAccessException` is a **checked exception** extending `ReflectiveOperationException`. Operations like the following can throw this exception when the caller is not allowed access:

- `Method.invoke(target, args)` when the method or its declaring class is not accessible to the caller.
- `Field.get(target)` or `Field.set(target, value)` when read/write access via Reflection is not granted. `final` fields also have specific write restrictions.
- `Constructor.newInstance(args)` when the constructor is not accessible to the caller.

For example, `getDeclaredMethod("secret")` may return a `Method` describing a private method. If the method resides in a class not in the same nest and the caller lacks access permission, `invoke` will throw `IllegalAccessException`, unless the caller has validly enabled access-check suppression.

Key distinctions:

- `IllegalAccessException` stems from **permission to use the member during Reflection execution**.
- `IllegalAccessError` is a **`LinkageError`**, typically thrown when bytecode references a class/member that cannot be accessed under runtime linkage constraints; this is **not** the checked exception from `Method.invoke`.
- A Java compile error like “has private access” is also **not** Reflection's `IllegalAccessException`: the compiler may reject direct access code before runtime.

### How to Diagnose

First inspect the member's declaring class, modifiers, and caller context:

```java
Method method = target.getClass().getDeclaredMethod("secret");
System.out.println(method.getDeclaringClass().getName());
System.out.println(Modifier.toString(method.getModifiers()));
```

This is an **illustrative snippet**, requiring `import java.lang.reflect.Method;` and `import java.lang.reflect.Modifier;`, assuming `target` exists and the method name is exact. `getDeclaredMethod` does **not** automatically search methods inherited from superclasses; use `getMethod` when looking up a public member per the API contract.

Whenever possible, use a `public` API designed for callers. If you must call a non-public member in controlled code, you may consider `trySetAccessible()`, while taking module boundaries and access permissions into account.

## 3. InaccessibleObjectException: Failing When Requesting Deep Access

`InaccessibleObjectException` is an **unchecked exception** extending `RuntimeException`, in the `java.lang.reflect` package. A common case:

```java
Method method = someClass.getDeclaredMethod("hidden");
method.setAccessible(true); // May throw InaccessibleObjectException.
```

This is an **illustrative snippet**. On Java 17+, many internal JDK packages belong to named modules and are not open to every caller. That `getDeclaredMethod` finds metadata does **not** mean the JVM permits `setAccessible(true)`.

Concrete example: package `java.lang` of module `java.base` is exported for using public APIs, yet **is not opened by default** to applications in the unnamed module for deep reflection into protected/private JDK members. Consequently, attempting to open `ClassLoader#defineClass(...)` via Reflection is usually rejected when running Java 17 with default module configuration.

Unlike `IllegalAccessException`, which happens when `invoke/get/set/newInstance` lacks permission, `InaccessibleObjectException` indicates that **the very act of requesting to bypass access checks is not accepted**. The error can occur before ever invoking the actual member.

**Important:** `setAccessible(true)` can succeed on private members within the **same module** or in an appropriately opened package, depending on API rules. Therefore, do not conclude “Java 17 always forbids Reflection on private members.” Java 17 still allows deep reflection in many cases; the difference lies in access scope and modules.

## 4. Runnable Java 17+ Example: Two Exceptions, Two Moments

The following example requires no external libraries. It places `SecretBox` as a **separate top-level class** in the same file, rather than a nested class in the same nest, to demonstrate `IllegalAccessException` clearly. Then it attempts to access a protected JDK method to observe `InaccessibleObjectException`.

Save the **entire** code into `AccessErrorsDemo.java`:

```java
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;

public class AccessErrorsDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Method local = SecretBox.class.getDeclaredMethod("reveal");
        System.out.println("lookup: " + local.getName());

        try {
            local.invoke(new SecretBox());
        } catch (IllegalAccessException ex) {
            System.out.println("invoke before suppression: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("local trySetAccessible: "
                + local.trySetAccessible());
        System.out.println("invoke after suppression: "
                + local.invoke(new SecretBox()));

        Method defineClass = ClassLoader.class.getDeclaredMethod(
                "defineClass", String.class, byte[].class, int.class, int.class);
        System.out.println("JDK trySetAccessible: "
                + defineClass.trySetAccessible());

        try {
            defineClass.setAccessible(true);
            System.out.println("setAccessible JDK: granted");
        } catch (InaccessibleObjectException ex) {
            System.out.println("setAccessible JDK: "
                    + ex.getClass().getSimpleName());
        }
    }
}

class SecretBox {
    private String reveal() {
        return "secret value";
    }
}
```

Compile/run using **JDK 17+**, with **default** launch options (without adding extra `--add-opens`):

```bash
javac --release 17 -encoding UTF-8 AccessErrorsDemo.java
java AccessErrorsDemo
```

Stdout on OpenJDK with default module configuration:

```text
lookup: reveal
invoke before suppression: IllegalAccessException
local trySetAccessible: true
invoke after suppression: secret value
JDK trySetAccessible: false
setAccessible JDK: InaccessibleObjectException
```

**Reading the output in order:**

1. `getDeclaredMethod("reveal")` retrieves metadata for the private method without invoking it or changing access.
2. `local.invoke(new SecretBox())` fails with `IllegalAccessException` because `AccessErrorsDemo` and `SecretBox` are two top-level classes **in different nests**, and `reveal()` is `private`.
3. `local.trySetAccessible()` succeeds because both classes belong to the same unnamed module, where the JVM permits bypassing access checks for this case.
4. The second `invoke` returns `secret value`: access to the private member is now valid for that opened `Method` object.
5. `ClassLoader#defineClass(String, byte[], int, int)` is a protected method in package `java.lang` of named module `java.base`. A program in the unnamed module is not granted deep reflection into this package under default configuration, so `trySetAccessible()` returns `false`.
6. On that same JDK member, `setAccessible(true)` throws `InaccessibleObjectException`. No `defineClass(...)` call is ever executed.

**Why can the output change?** If the JVM is launched with a module-opening argument, for example:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED AccessErrorsDemo
```

Then opening `ClassLoader#defineClass` can succeed: `JDK trySetAccessible` becomes `true` and the message prints `setAccessible JDK: granted`. That illustrates the role of module openness. Depending on the environment/runtime, pre-existing package-opening flags also affect the result; do not treat the example's stdout as a guarantee for every JVM configuration.

**Do not use `--add-opens` indiscriminately in production** just to make an exception disappear. Doing so alters encapsulation boundaries and can depend heavily on JDK internals.

## 5. JPMS: How Does exports Differ from opens?

Consider a named module `billing.core` with package `billing.api` containing public classes and methods, and package `billing.internal` containing private fields requiring Reflection.

An *illustrative* `module-info.java` file:

```java
module billing.core {
    exports billing.api;
    opens billing.internal to billing.tool;
}
```

Meaning:

- `exports billing.api;` lets other modules use the **public API** of `billing.api` per module and Java access rules. It does **not** automatically grant deep reflection to private fields.
- `opens billing.internal to billing.tool;` allows module `billing.tool` to perform deep reflection into package `billing.internal` per API conditions. It does **not** mean that module can import every package-private class as a public API.
- `open module billing.core { ... }` opens all packages of the module for Reflection; it has broader scope and requires design consideration.
- A package can be both exported and opened; the effects of the two declarations differ.

This is an **illustrative configuration snippet**, not a standalone runnable module project; module `billing.tool` and the packages would need to exist to compile the example.

### Command-Line Variants

When `module-info.java` cannot be changed, the JVM provides options:

```bash
java --add-opens billing.core/billing.internal=billing.tool \
     --module-path mods \
     --module billing.tool/billing.tool.Main
```

The command above illustrates a shell supporting `\` line continuation, assuming `mods` contains compiled modules and the main class is exact. Use the same idea with `ALL-UNNAMED` if the caller belongs to the unnamed module.

**Distinction:**

- `--add-exports module/package=target`: grants export permission, serving public API access per access rules.
- `--add-opens module/package=target`: grants package open permission for deep reflection, better fitting cases where `setAccessible(true)` is blocked by JPMS.

`--add-exports` alone is **not** enough to open private members of a package in a named module. `--add-opens` likewise does **not** turn `private` into public for normal Java calls.

### Unnamed Module and Same-Module Access

Applications running on the classpath typically belong to the unnamed module. Under the JPMS model, packages of the unnamed module are considered broadly exported and opened; thus the demo can enable access for `SecretBox.reveal()`. Within a named module, Reflection on non-public members **inside the same module** also has cases where enabling access is permitted. However, when crossing into another named module whose package is not opened, `setAccessible(true)` is normally rejected.

You must check the **caller's module**, the **declaring class's module**, and the **package's** export/open status; knowing only the `private` modifier is insufficient to predict `InaccessibleObjectException`.

## 6. Quick Comparison Table

| Criterion | `IllegalAccessException` | `InaccessibleObjectException` |
|---|---|---|
| Package | `java.lang` | `java.lang.reflect` |
| Type | **Checked**, extends `ReflectiveOperationException` | **Unchecked**, extends `RuntimeException` |
| Typical phase | `Method.invoke`, `Field.get/set`, `Constructor.newInstance` | `AccessibleObject.setAccessible(true)` |
| Question the JVM is answering | “Is the caller permitted to perform this operation on this member?” | “Is it permitted to bypass access checks for this member?” |
| Common cause | Private/protected/package-private or inaccessible class; valid suppression not enabled | Package belongs to a named module not opened to the caller; deep reflection rules deny it |
| `trySetAccessible()` | Can succeed and permit subsequent operations | Usually returns `false` in module-restricted scenarios |
| Preferred fix | Use an appropriate public member/contract, fix invocation, or apply valid suppression | Open the package intentionally or stop deep reflection into internals |
| What not to do | Catch and ignore the exception assuming the method ran | Catch and proceed assuming `setAccessible(true)` succeeded |

**One member can lead to either exception depending on the execution path:** if you skip `setAccessible` and try `invoke`, the program may hit `IllegalAccessException`; if you first try `setAccessible(true)` in a JPMS-locked package, the program may hit `InaccessibleObjectException`. Both do not necessarily get thrown together.

## 7. Practical Diagnostic Workflow

### Step 1: Identify the API Throwing the Exception

Read the **full stack trace** and locate the first call site from your code:

- `invoke/get/set/newInstance` → focus on member access rights, modifiers, and the receiver.
- `setAccessible(true)` → inspect bypass permissions and package/module status.
- `getDeclaredMethod/getDeclaredField` failing with `NoSuchMethodException/NoSuchFieldException` → that is a separate lookup error; do not lump it into either access exception.

Do not just grep the word “access” in the message and guess the error.

### Step 2: Inspect Member and Module Metadata

Some useful APIs:

```java
Class<?> owner = method.getDeclaringClass();
Module module = owner.getModule();
String packageName = owner.getPackageName();

System.out.println("owner = " + owner.getName());
System.out.println("module = " + module.getName());
System.out.println("modifiers = "
        + java.lang.reflect.Modifier.toString(method.getModifiers()));
System.out.println("package = " + packageName);
```

This is an **illustrative snippet**, assuming variable `method` of type `Method` already exists. `module.getName()` may be `null` for an unnamed module. To inspect the caller's exact permissions, also check `Class::getModule` on the caller and `Module::isExported`, `Module::isOpen` with the appropriate package name/target module.

### Step 3: Evaluate Valid Ways to Open Access

If you genuinely intend to use Reflection on a non-public member:

```java
if (!method.trySetAccessible()) {
    throw new IllegalStateException(
            "Member is not open for deep reflection: " + method);
}
Object result = method.invoke(target);
```

This is an **illustrative snippet**, assuming a non-static method and suitable `target`; add handling for the checked exceptions of `invoke` in calling code. `trySetAccessible()` lets you handle the un-opened branch without relying on `InaccessibleObjectException` from `setAccessible(true)`. It does **not** guarantee the subsequent method call succeeds: the method may throw an exception, have a wrong receiver, wrong arguments, or hit other runtime errors.

### Step 4: Fix According to the Root-Cause Layer

- If the API offers a suitable public method/getter, prefer that API.
- If the class is in code you control, consider adjusting visibility/contracts or reorganizing code; do not widen permissions just for one Reflection utility.
- If the package belongs to a **named module you own**, open it selectively with `opens package to module;` when deep reflection is truly needed (e.g., serializers/frameworks).
- If the module belongs to a **library/JDK**, check API documentation and alternative public APIs; `--add-opens` should only be a deliberate solution in a controlled environment.
- If the exception appeared after upgrading from Java 8 to Java 17+, closely inspect module encapsulation and libraries trying to access JDK internals; upgrading libraries is usually more sustainable than tweaking JVM flags.

## 8. Common Diagnostic Mistakes

**Mistake 1: “Having `getDeclaredMethod` means it can be called.”** False. Lookup and access checks are two separate steps.

**Mistake 2: “Calling `setAccessible(true)` always fixes `IllegalAccessException`.”** False. If the module does not open the corresponding package, that call itself can throw `InaccessibleObjectException`.

**Mistake 3: “Java 17 forbids accessing private members via Reflection.”** False. Private members in the same module or in an opened package still have cases where suppression is permitted.

**Mistake 4: “Adding `exports` is enough to read private fields.”** False. `exports` and `opens` serve different purposes.

**Mistake 5: “`InaccessibleObjectException` is checked and requires declaring `throws`.”** False. It is an unchecked exception, whereas `IllegalAccessException` is checked.

**Mistake 6: “Catching both exceptions and ignoring them handles the issue.”** False. Access permission **was not granted** and the operation may not have run; catching and ignoring can mask logic or security bugs.

**Mistake 7: “Every exception from `Method.invoke` is `IllegalAccessException`.”** False. If the real method throws an exception, Reflection normally wraps it in `InvocationTargetException`; wrong arguments can produce `IllegalArgumentException`; class initialization or linkage failures have other mechanisms.

**Mistake 8: “A private method in a nested class always causes `IllegalAccessException`.”** Not necessarily. Java has **nest-based access control**: nestmates can access each other's private members per language/JVM rules. That is why the runnable example used two separate **top-level classes**.

## 9. Self-Check Questions

**Question 1.** `getDeclaredField("password")` returns a `Field` successfully; immediately afterward `field.get(target)` throws `IllegalAccessException`. Why?

**Answer:** Metadata lookup succeeded, but the caller lacks permission to perform the read operation on the member. Check the declaring class/member and access checks.

**Question 2.** `field.setAccessible(true)` throws `InaccessibleObjectException` on Java 17. Is simply changing the field to `public` guaranteed to fix it?

**Answer:** No. You must consider the named module and the package's export/open status; changing the modifier alone may not suffice. Prefer a public API or intentional openness configuration.

**Question 3.** `trySetAccessible()` returns `false`: should you proceed to call `field.get(...)` as if access were opened?

**Answer:** No. The call to open access failed; you need to handle that branch, or verify whether the caller actually already has permission under normal Java access checks using `canAccess(...)`.

**Question 4.** Why is `--add-exports java.base/java.lang=ALL-UNNAMED` not equivalent to `--add-opens java.base/java.lang=ALL-UNNAMED`?

**Answer:** Export serves usability of public elements; open permits deep reflection under JPMS rules. They are not synonymous.

**Question 5.** If Java 8 code used Reflection to access JDK internal fields and breaks on Java 17, what should you check first?

**Answer:** The stack trace, which library/framework is doing internal reflection, whether alternative public APIs exist, module boundaries, and whether the library can be upgraded; use JVM opening flags only after understanding their purpose.

## Standard References

- Java SE API: [`IllegalAccessException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessException.html).
- Java SE API: [`InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html).
- Java SE API: [`AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html) — `setAccessible`, `trySetAccessible`, `canAccess`.
- Java SE API: `Method.invoke`, `Field.get/set`, `Constructor.newInstance`, `Module.isOpen/isExported`.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403), effective since JDK 17.

**Takeaway:** `IllegalAccessException` indicates that **the Reflection operation on the member is not permitted**; `InaccessibleObjectException` indicates that **the attempt to open deep reflection permission was denied**. To resolve properly, identify **the API throwing the error**, **the modifiers/member**, and **the module/package of both caller and declaring class**, then choose a public API or open access deliberately.
