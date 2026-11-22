# Nestmates and private access between related classes in Java Reflection

## 1. What problem do nestmates solve?

Since **Java 11**, the JVM supports the concept of a **nest** (a group of classes belonging to the same nest): a *nest host* and member classes (*nest members*) whose relationship is recorded in class files. **Nestmate** classes can directly access each other's `private` members under JVM access-control rules, as long as they belong to the same valid nest.

The original problem: in Java, an outer class and classes nested inside it are allowed to use each other's `private` members right at the language level.

```java
class Library {
    private String code = "BOOK";

    static class Checker {
        String check(Library library) {
            return library.code; // Valid under Java language rules
        }
    }
}
```

Before Java 11, bytecode could not directly express all of these privacy permissions between classes under the older `private` access mechanism. Compilers typically had to generate `synthetic` bridge methods such as `access$...` so a nested class could read `private` members of its enclosing class. Java 11 introduced **nest-based access control** (JEP 181): the JVM understands nest relationships and can allow direct `private` access without those bridges.

> **Important distinction:** "Same nest" is a JVM-recognized relationship between `Class`es, not merely "same package", "same superclass", "similar class names", or "loaded together by a framework".

## 2. Which classes belong to a nest?

In normal Java code, *nested classes*—including `static nested class`, *inner class*, and compiled local/anonymous classes—can share the same nest as the outermost enclosing class. Deeply nested classes still share the same outermost nest host. **Independent top-level classes**, even in the same source file or same package, do not automatically become nestmates.

```java
public class House {
    private int secret = 7;

    static class Room {
        private String note = "private-room";

        static class Box {
            private long id = 1;
        }
    }

    class Window {
        private boolean open;
    }
}
```

In this structure, `House`, `House.Room`, `House.Room.Box`, and `House.Window` can belong to the same nest. There is no separate "sub-nest" just because `Box` is declared deeper.

The **nest host** is the class representing the nest. In the example above, when compiled normally with Java 11+, `House.class` is the host; `House.Room.class.getNestHost()` and `House.Room.Box.class.getNestHost()` return `House.class`. The host class itself is also a member of the nest.

**`private` access permission** is a mutual privilege among nestmates, in both directions:

- A nested class can read a `private` field or call a `private` method of the enclosing class.
- The enclosing class can access `private` members of a nested class.
- Two "sibling" nested classes sharing the same host can access each other's `private` members, given an appropriate reference/method.

Having a nest relationship **does not make members `public`**, nor does it grant access to all classes in the same package.

## 3. Three Reflection APIs for identifying nestmates

Methods on `java.lang.Class` available since Java 11:

| API | Returns | How to understand it |
| --- | --- | --- |
| `clazz.getNestHost()` | `Class<?>` | The host class of the nest containing `clazz`; for a class not participating in a multi-class nest, typically itself |
| `clazz.getNestMembers()` | `Class<?>[]` | Member classes of the nest, including the host; element order is unspecified |
| `a.isNestmateOf(b)` | `boolean` | `true` if the two `Class` objects are determined by the JVM to belong to the same nest |

Example using the classes from section 2:

```java
Class<?> host = House.Room.Box.class.getNestHost();
boolean related = House.Room.class.isNestmateOf(House.Window.class);
Class<?>[] members = House.class.getNestMembers();
```

These lines are an **illustrative snippet inside a Java method**, not a standalone program. `host` corresponds to `House.class` and `related` is `true` if the example is compiled/run on a JVM supporting nestmates.

Usage notes:

1. Do not rely on the element order from `getNestMembers()`. If stable display is needed, extract names and sort them.
2. `getNestMembers()` describes the nest and is **not synonymous** with `getDeclaredClasses()`: the latter retrieves directly declared member classes/interfaces, not intended to list all nestmates.
3. `isNestmateOf` checks a relationship between **classes**, not an all-encompassing test for every barrier when accessing a specific field/method.
4. Do not infer nest relationships by splitting strings on `$` in class names; binary names are not sufficient to establish access permission.

## 4. Java 17+ program: verifying private access via Reflection

Save the entire contents below into **`NestmateDemo.java`** (do not split the classes into separate files). `NestmateDemo` and the two nested classes `MemberReader`, `Peer` belong to the same nest; `Outside` is an independent top-level class placed in the same file to prove that **same package and same source file are still not enough**.

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

public class NestmateDemo {
    private String secret = "ALPHA";

    private String combine(String suffix) {
        return secret + suffix;
    }

    private static class MemberReader {
        static void inspect(NestmateDemo obj) throws Exception {
            // Private permission is granted because MemberReader and NestmateDemo are in the same nest.
            System.out.println("direct: " + obj.secret);

            // getDeclared* only finds metadata, it does not disable access checks automatically.
            Field field = NestmateDemo.class.getDeclaredField("secret");
            Method method = NestmateDemo.class.getDeclaredMethod(
                    "combine", String.class);

            // Not calling setAccessible(true).
            System.out.println("field canAccess: " + field.canAccess(obj));
            System.out.println("field value: " + field.get(obj));
            System.out.println("method canAccess: " + method.canAccess(obj));
            System.out.println("method result: " + method.invoke(obj, "!"));
        }
    }

    private static class Peer {}

    public static void main(String[] args) throws Exception {
        System.out.println("same nest: "
                + MemberReader.class.isNestmateOf(Peer.class));
        System.out.println("outside nest: "
                + MemberReader.class.isNestmateOf(Outside.class));
        System.out.println("peer listed: "
                + Arrays.asList(NestmateDemo.class.getNestMembers())
                        .contains(Peer.class));

        NestmateDemo obj = new NestmateDemo();
        MemberReader.inspect(obj);
        Outside.inspect(obj);
    }
}

// Independent top-level class: does not automatically belong to NestmateDemo's nest.
class Outside {
    static void inspect(NestmateDemo obj) throws Exception {
        Field field = NestmateDemo.class.getDeclaredField("secret");

        System.out.println("outside canAccess: "
                + field.canAccess(obj));
        try {
            field.get(obj);
        } catch (IllegalAccessException ex) {
            System.out.println("outside read: IllegalAccessException");
        }
    }
}
```

Compile and run with **JDK 17+**, using the default target of modern JDKs:

```bash
javac NestmateDemo.java
java NestmateDemo
```

Output:

```text
same nest: true
outside nest: false
peer listed: true
direct: ALPHA
field canAccess: true
field value: ALPHA
method canAccess: true
method result: ALPHA!
outside canAccess: false
outside read: IllegalAccessException
```

### Analyzing each group of results

1. `MemberReader.class.isNestmateOf(Peer.class)` is `true` even though the two nested classes have no inheritance relationship: both share the same nest host.
2. `Outside.class` does not belong to the nest just for being in the same package/source file; `isNestmateOf` returns `false`.
3. `NestmateDemo`'s `getNestMembers()` contains `Peer.class`. Do not rely on array index to assert membership.
4. The line `direct: ALPHA` is `private` access via normal Java syntax. The two `canAccess` lines and two Reflection results show that when **the caller is `MemberReader` in the same nest**, normal access checks also allow Reflection to read a `private` field and invoke a `private` method **without calling `setAccessible(true)`**.
5. `Outside` still obtains the `Field` object with `getDeclaredField`: the metadata query succeeds, but `canAccess(obj)` is `false`. When calling `Field.get`, the JVM/Reflection throws `IllegalAccessException` because the caller lacks permission.
6. `Method.invoke` in the example returns `ALPHA!`. This is when the method is *actually invoked*, distinct from merely looking up the `Method` with `getDeclaredMethod`.

The program intentionally uses `throws Exception` in a focused example for readability. In real applications, handle Reflection exceptions semantically: `NoSuchFieldException` and `NoSuchMethodException` for lookup; `IllegalAccessException` for access; `InvocationTargetException` when the target method throws an error; and type/argument mismatch cases.

## 5. How does private access via nestmates differ from setAccessible?

There are three independent operations that are easily confused:

**(1) Finding metadata.** `getDeclaredField("secret")` and `getDeclaredMethod("combine", String.class)` return member descriptor objects, including `private` ones. `getField`/`getMethod` are for the `public` member set under their respective lookup rules.

**(2) Checking normal access permission.** `field.canAccess(obj)` or `method.canAccess(obj)` reports whether the current caller has permission to perform the operation on a specific object given the current Reflection access state. The caller performing the check matters: in the example, running inside `MemberReader` returns `true`, while running inside `Outside` returns `false` for that `private` field. The argument must be valid: for instance fields/methods, pass a matching receiver; for static members, pass `null`. An invalid argument can cause `IllegalArgumentException`.

**(3) Requesting to bypass normal Java access checks.** `setAccessible(true)` or `trySetAccessible()` is a separate operation, subject to JPMS module constraints. Using them to suppress access checks is not a prerequisite when the caller already has access via a nest relationship.

| Caller and action | Find `private` metadata via `getDeclared...` | Actual access without accessible override enabled |
| --- | --- | --- |
| A valid nestmate class | Yes | Yes, if member kind/receiver/other conditions match |
| Top-level class in same package but outside nest | Can | No `private` access merely from sharing a package |
| A subclass outside the nest | Can | Inheritance does **not** grant `private` access |
| Library outside the module | Can look up metadata depending on API | `private` access is not automatically granted; `setAccessible` is also subject to `opens` rules |

**JPMS:** On Java 9+, a framework can be blocked when trying to call `setAccessible(true)` on a non-public member of a package in another module that has not `opens` that package. `trySetAccessible()` can return `false`; `setAccessible(true)` can throw `InaccessibleObjectException`. Do not add `--add-opens` or ignore errors by default. Design a public API or configure `opens` intentionally when a framework genuinely needs deep reflection.

A valid nest itself cannot be stretched arbitrarily across modules: members must satisfy class/runtime package/class loader conditions as specified by the JVM. Therefore, nestmates cannot be used to automatically cross another module's protection boundary.

## 6. Bytecode/JVM mechanism

### Java 8 and earlier: compilers typically generated accessors

Because older JVMs only allowed `private` member access inside **the owning class itself** (while Java source code supported access across nested classes), the compiler had to emit `synthetic` bridges, such as names like `access$000` or similar. Nested classes called the bridge instead of direct `private` access. Bridge naming/generation is a **compiler implementation detail**, not a stable API.

### Java 11+: nest information in class files

JEP 181 added class file attributes:

- **`NestHost`:** member class points to its host.
- **`NestMembers`:** host lists member classes in the same nest.

When performing `private` access checks, the JVM checks whether the two classes belong to the same **validly verified** nest. Merely writing another class name into a class file is not enough: the JVM also validates the relationship, including agreement from the host and runtime package/class loader constraints. Spoofed or inconsistent class file data can cause resolution/verification to fail; do not forge nest relationships by manually editing class names.

**Compilation target version matters greatly.** Running a program on a newer JDK does **not** automatically turn Java 8-targeted bytecode into nestmate bytecode: the compiler generates and records nest attributes when the target/class-file version supports them. If older JVMs must be supported, choose the appropriate `--release` and understand the compiler may use synthetic accessors. Java 8 does not recognize Java 11 class-file nest attributes.

You can inspect class files **after compilation**:

```bash
javap -v NestmateDemo
javap -v 'NestmateDemo$MemberReader'
```

The command above uses single-quote syntax suitable for Unix shells. In PowerShell you can also wrap class names containing `$` in single quotes. Look for the `NestMembers` attribute on the host and `NestHost` on the member. `javap -v` output is very long, varies by compiler/version, and should not be treated as fixed article output.

Do not confuse nest metadata with `InnerClasses` or `EnclosingMethod`: those attributes provide nested class/enclosing context structure information, but do not replace JVM nestmate checking rules.

## 7. Nestmates do not mean inheritance, package, or lexical access in every context

### 7.1. Nestmate vs subclass

```java
class Parent {
    private int hidden = 5;
}

class Child extends Parent {
    // Cannot write: int n = hidden;
}
```

`Child` does not gain `private` access to `Parent` merely because of `extends`. A subclass outside the nest also cannot call `getDeclaredField("hidden").get(instance)` and expect automatic permission. If a nested class happens to be both a subclass and a nestmate, `private` access stems from the **nest**, not inheritance.

### 7.2. Same package or same .java file

Two top-level classes in the same package can access valid package-private members, but cannot access each other's `private` members. The `Outside` class in the program above shows that **being in the same source file does not create a nest either**. Do not use `Class.getPackageName()` or binary names as a nestmate test; use `isNestmateOf`.

### 7.3. A nested class is not always an inner class

- A `static nested class` does not automatically hold a reference to an outer class instance. It can still be a nestmate and access `private` members of an outer object if it **already has a reference**.
- An `inner class` (non-static) usually has an enclosing instance context, yet having that reference and being granted `private` access by the JVM are two separate matters.
- Nest membership does not grant permission to read an instance field without an appropriate receiver; `private` access permission and object existence are not the same thing.

### 7.4. Reflection metadata and synthetic members

Reflection can observe compiler-generated `synthetic` members. When running code compiled for an older target, `access$...` methods may appear; when targeting Java 11+, they are usually no longer needed for access across nestmates. Do not rely on the count or names of synthetic members to assume applications behave identically across compilers.

Introspection tools can use `Method.isSynthetic()`, `Field.isSynthetic()`, and `Method.isBridge()` for detailed analysis. Only filter them out if business rules allow; for bytecode diagnostics, synthetic information can be very important.

## 8. Notes when using Reflection and handling errors

1. **Do not use `getFields()` to look for `private` fields.** You need `getDeclaredField()`; that method searches metadata declared directly on the class without walking superclasses.
2. **Do not equate "found" with "allowed to use".** `getDeclaredMethod()` finds metadata, `canAccess()` checks permission with the current caller and receiver, and `invoke()` performs the execution. Do not skip exception handling.
3. **Do not check permission from the wrong location.** `canAccess` results can differ between code inside a nestmate and a framework outside the nest; calling the check elsewhere can yield a different answer.
4. **Do not assume deep access solely from source-code relationships.** Only valid runtime nest relationships support the special access. Class loaders/modules, bytecode targets, and bytecode instrumentation tools can affect actual metadata.
5. **Do not use nest relationships to bypass JPMS.** `setAccessible` still follows module boundaries/`opens` and must be evaluated separately.
6. **Do not assume every field/method is an instance member.** `canAccess(null)` applies to static members, whereas instance members need a receiver of the right type.
7. **Do not compare element order from `getNestMembers()`.** If displaying in documentation, sort by name; if checking presence, use `contains` or compare `Class` objects.
8. **Do not use `getNestMembers()` as a substitute for analyzing all classes in an inheritance hierarchy.** A nest describes privacy among nestmates, not the full type hierarchy.

When designing a framework, the practical steps are usually: identify the owning `Class<?>`, read members via `getDeclared...`, decide whether only metadata or execution is needed, evaluate access at the execution point, and consider `trySetAccessible()` only when calling `private` from outside the nest is truly required and module configuration permits it.

## 9. Self-check and practice

**Question 1.** Why can `MemberReader` read `secret` directly while `Outside` cannot?
**Answer:** `MemberReader` belongs to the same nest as `NestmateDemo`; `Outside` is an independent top-level class outside the nest. Sharing a source file does not grant `private` access.

**Question 2.** Does `getDeclaredField("secret")` in `Outside` return a `Field`? Why does reading the field still fail?
**Answer:** Yes, because metadata lookup is a separate step from access checking; `Field.get` enforces access control from the caller outside the nest and throws `IllegalAccessException`.

**Question 3.** Is every subclass a nestmate of its superclass?
**Answer:** No. Inheritance and nest membership are two independent relationships.

**Question 4.** How do you check whether two classes belong to the same nest?
**Answer:** `A.class.isNestmateOf(B.class)`. Use `getNestHost()` to find the host; `getNestMembers()` to inspect members.

**Question 5.** Why aren't `NestHost`/`NestMembers` visible when compiling classes targeting Java 8?
**Answer:** The nestmate mechanism resides in Java 11+ class files, whereas targeting Java 8 uses the older compatibility mechanism when `private` access across nested classes is needed.

**Practice exercise:** Add a field `private int value = 42;` to `Peer` and a method `private static int read(Peer peer)` to `MemberReader` to access `peer.value`. Verify it can be called from `main` and compare it with calling via Reflection from `Outside`. Use only nestmate privileges without adding `setAccessible(true)`; explain the results based on caller, host, and `private` access.

**Core takeaway:** Nestmates are a JVM-level `private` access rule supported since Java 11. Reflection lets you **inspect the nest** (`getNestHost`, `getNestMembers`, `isNestmateOf`), **find metadata** (`getDeclared...`), and **perform operations** (`get`/`invoke`). These three things have distinct meanings, so verify the nest relationship and permissions accurately at the point where the member is used.