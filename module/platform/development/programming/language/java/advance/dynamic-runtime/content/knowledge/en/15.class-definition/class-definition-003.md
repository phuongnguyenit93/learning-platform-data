# 15.3 `defineHiddenClass` and Differences from Named Classes Findable via `Class.forName`

Java has two mechanisms that are easy to confuse when creating classes at runtime:

- **Named class (ordinary/named class)**: has a **binary name** so a class loader or the JVM can look it up by name, such as `java.lang.String`, `com.example.User`, or `com.example.Outer$Inner`. When the class is accessible through an appropriate class loader, `Class.forName("...")` can return its `Class<?>`. `MethodHandles.Lookup.defineClass(byte[])` is one way to define this kind of class.
- **Hidden class**: created using **`MethodHandles.Lookup.defineHiddenClass(byte[], boolean, ClassOption...)`**. The class still actually exists in the JVM and has a `Class<?>` object, bytecode, fields, methods, supertype, interfaces, and can be invoked via reflection/`MethodHandle`. However, its runtime name **is not a binary name**; `Class.forName` and `ClassLoader.loadClass` **cannot find a hidden class** by that name.

This is not simply a matter of `public` versus `private`. A hidden class can have `public` methods and still **not be discoverable by name**, while a named class can be difficult to access due to modules/class loaders and still have a binary name. The purpose of a hidden class is to provide runtime frameworks with an executable type that can be created on demand, without adding a discoverable name into the ordinary class namespace.

> **Environment:** JDK 17+. The `defineHiddenClass` API has existed since Java 15 (JEP 371). The four standalone examples below compile with `javac --release 17` and have verified stdout. `Class.getName()` of a hidden class contains a runtime-dependent suffix, so the examples only check stable characteristics (presence of `/`), **not hard-coding the generated name**.

## 1. What Do You Need to Know?

After this lesson, you can:

1. Distinguish **class definition**, **class discovery by name**, **static initialization**, and **class unloading**.
2. Explain why `defineHiddenClass(...)` returns a `Lookup` instead of a binary name, and how to obtain `Class<?>` via `lookup.lookupClass()`.
3. Understand why `Class.forName(hidden.getName())` throws `ClassNotFoundException`, even when `hidden` already exists and has the same class loader as the host class.
4. Compare `Lookup.defineClass(bytes)` with `Lookup.defineHiddenClass(bytes, initialize, options)` on **the exact same class file byte sequence**.
5. Use `MethodHandle`/reflection to access a hidden class through a real reference instead of relying on a name string.
6. Understand the meaning of the `initialize` parameter: `false` can defer `<clinit>`, `true` initializes immediately according to the JVM.
7. Understand `NESTMATE` in private access and `STRONG` in the lifecycle of a hidden class.
8. Recognize cases where multiple hidden classes are defined from the same bytecode, yet have **different identities and static states**, even with a shared class loader.
9. Avoid errors related to `Lookup` permissions, wrong packages, duplicate named definitions, class loaders, reflection, and using a hidden class name as a standard binary name.

## 2. Mental Model: Creating a `Class<?>` Does Not Mean Registering a Lookup-able Name

A JVM can contain multiple class objects related in different ways to the same source/bytecode. For a named class, the class loader manages identity by the **pair of binary name and defining loader** (along with related JVM rules). For a hidden class, the JVM allows a distinct class **without a normal binary name** and without being looked up by APIs that require that name.

```text
Valid bytecode of a class "Host$Template"
                 |
          +------+------+
          |             |
          v             v
Lookup.defineClass  Lookup.defineHiddenClass
          |             |
          v             v
Named Class A      Hidden Class H
          |             |
name: "Host$Template" name: "Host$Template/0x..." (illustrative form)
binary name: YES   binary name: NO
isHidden(): false  isHidden(): true
          |             |
          v             v
Class.forName       keep Class<?> H reference
("Host$Template")   or Lookup/MethodHandle to use
  -> possibly A     Class.forName(H.getName()) -> fails
```

The diagram above illustrates an example within the same loader and package, with an accessible named class. The `/0x...` suffix is commonly seen when printing a hidden class name on HotSpot, but do not rely on **the content or length of the suffix** when writing programs.

### 2.1. A Hidden Class Is Still a Full Class

A hidden class can:

- Have a representing `Class<?>` object; call `isHidden()` to identify it.
- Have methods, constructors, fields, a class initializer, and a superclass/interfaces according to class file constraints.
- Be verified, linked, and optionally initialized by the JVM.
- Be passed to APIs that accept `Class<?>`, for example to use `MethodHandles.Lookup`, `Class.getDeclaredMethods()`, or reflection with appropriate permissions.
- Participate in polymorphism through ordinary named interfaces/supertypes; an object with a hidden runtime class can still be used under a named interface type.
- Be defined multiple times from the same bytecode to create independent class identities.

However, a hidden class cannot **be named by a binary name in the constant pool of another class** like an ordinary class. Therefore, Java source code cannot write a normal import or field type pointing to the runtime name `Host$Template/0x...`; the Java lexer and JVM symbolic linkage do not treat it as a valid binary name.

### 2.2. "Not Findable by Name" Differs from "Unusable"

Do not think of a hidden class as *completely invisible*. It can be exposed through `obj.getClass()`, `Lookup.lookupClass()`, stack traces, diagnostics, reflection, or instrumentation permitted by the JVM. It is only intentionally **excluded from nominal lookup mechanisms using a class binary name**.

For example, a runtime can return an object implementing `Runnable` that has a hidden runtime class. The client does not know or find the runtime class name, yet can still call `((Runnable) object).run()` because `Runnable` is a valid named interface. A framework can also hold a `MethodHandle` to a method on the hidden class without using `Class.forName`.

## 3. Comparison Table: `defineClass`, `defineHiddenClass`, and `Class.forName`

| Question | `Lookup.defineClass(bytes)` | `Lookup.defineHiddenClass(bytes, init, opts)` | `Class.forName(name)` |
| --- | --- | --- | --- |
| What operation is this? | **Defines** a named class from bytecode | **Defines** a hidden class from bytecode | **Finds/loads and possibly initializes** a named class by name |
| Does it require class file `byte[]`? | Yes | Yes | No; takes a name string and uses a class loader |
| Return value | `Class<?>` | A new `MethodHandles.Lookup` on the hidden class | The found `Class<?>` |
| Binary name usable for lookup? | Yes, via an appropriate loader | **No** | Requires input to be a name the loader can resolve |
| `Class.isHidden()` | `false` | `true` | `false` for normal classes found |
| Registers name in the named classes namespace? | Yes, subject to uniqueness rules per loader | No, not under the named class mechanism | Does not define a hidden class itself |
| Defining the same bytecode again? | Same loader + same binary name can throw `LinkageError` | Can create multiple hidden class identities | Not a method for defining a duplicate |
| Static initialization | `defineClass` does not itself require immediate initialization | Boolean `initialize` decides whether to initialize immediately | `forName(name)` initializes by default; overload has `boolean` |
| Findable by `Class.forName` | Yes, if the right loader and lookup conditions are chosen | **No** | It is itself the lookup API |
| Has `ClassOption.NESTMATE` / `STRONG`? | No | Yes | No |
| Unloading mode | Tied to the defining loader by named class rules | Weak relationship by default; `STRONG` changes to strong loader relationship | Does not determine the unloading policy of the found class |

**Common point of confusion:** `Class.forName` does not redefine a hidden class just because the name in `getName()` looks similar to a Java class name. When a caller passes `hidden.getName()` (with `/`), the JVM does not convert it into a reference to the existing hidden class.

### 3.1. `Class.forName` Has Conditions for Named Classes

Saying "a named class can be found with `Class.forName`" is not a guarantee that **every named class can be found from every class loader**. Reasons a lookup can fail include:

- The caller uses a different loader that cannot see the corresponding class.
- The class is not actually on the class path/module path used by the loader.
- The binary name is wrong (for example, a nested class uses `$` rather than `.` between outer/inner in its binary name).
- Module/readability or class loading/linkage fails in context.

For a named class, you just need to **choose the right loader** to have a chance to resolve it:

```java
// Illustrative fragment with a named class having a binary name and appropriate loader.
Class<?> type = Class.forName(
        "com.example.Plugin", false, appropriateLoader);
```

The snippet above does not run standalone because `appropriateLoader` is not defined. The `false` parameter in the 3-argument overload only controls initialization, and does not turn a named class into a hidden class.

### 3.2. A Hidden Class Cannot Be Found Even with the Right Loader

For a hidden class:

```java
// Fragment: hidden is the Class<?> of the created hidden class.
Class.forName(hidden.getName());                   // ClassNotFoundException
hidden.getClassLoader().loadClass(hidden.getName());// ClassNotFoundException
```

Both calls above can throw a checked exception and will be tested in a complete program in section 6. `getClassLoader()` shows that the hidden class **is recorded as having a defining loader**, but the loader **does not use `loadClass` to return the hidden class by name**.

## 4. Core API: `MethodHandles.Lookup.defineHiddenClass`

Conceptual declaration from Java 17+:

```java
public MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException
```

This is the **API signature**, not a snippet you need to write in your program.

Common usage:

```java
// Fragment: bytes is a byte[] containing a valid class file.
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
Class<?> hiddenClass = hiddenLookup.lookupClass();
```

After the call, `hiddenLookup` is a Lookup whose **lookup class is the new hidden class**, convenient for finding methods/constructors/fields with corresponding access rights. `hiddenClass` is the `Class<?>` identifying the exact hidden type created.

Parameters:

1. **`bytes`:** a valid class file byte array (for example, bytecode generated by the compiler or ASM). Do not pass `.java` file contents, a name string, or uncompressed/raw JAR library bytes.
2. **`initialize`:** `true` requests the JVM to initialize the hidden class after linking; `false` defers initialization until Java/the JVM actually triggers it according to initialization rules.
3. **`options`:** a list of `ClassOption`, which in Java 17 includes `NESTMATE` and `STRONG`; it is valid to pass no options.

### 4.1. `Lookup` Must Have Appropriate Privileges

`defineHiddenClass` is an access-checked API, **not a class-loader escape hatch**:

- The Lookup needs **full privilege access** per the `java.lang.invoke` contract; a weak lookup (such as `MethodHandles.publicLookup()`) is insufficient.
- The class bytes must define a class with a package matching the **lookup class**.
- Defining a class in the same package/module and with access rights does not automatically bypass Java module security constraints.
- An invalid class file can cause `ClassFormatError`, `VerifyError`, or other errors during creation/linking.
- `NESTMATE` is not a command to grant arbitrary permissions to a class in another package/module; it attaches the hidden class to the nest of the **lookup class** according to API rules.

This API is useful when a framework already has a validly privileged `Lookup` and needs to define an executable runtime class without publishing a nominal binary name.

### 4.2. Package, Module, and Defining Loader

In defining a hidden class, the JVM uses the package of the class described by the bytes and places the hidden class in the runtime context of the lookup class (appropriate loader/module). When the bytes point to a different package than the lookup class, `defineHiddenClass` rejects it, typically with `IllegalArgumentException`. You should not change the bytecode's package simply by renaming the resource file string; the package is embedded inside the class file.

Specifically, the examples below place the host class and nested template in the same **unnamed package** so no module path configuration is needed. In real projects with a package like `com.example.runtime`, template classes must declare that exact package or the bytecode generator must produce the matching internal name.

### 4.3. Hidden Classes Can Be Initialized Separately and Multiple Times

Each successful `defineHiddenClass` call creates a new class. If the class file contains `static int count`, then two hidden classes defined from the same bytes have **two independent static fields**; initializing one class does not cause the other class's static initializer to be considered already run.

This differs from a named class in the same loader: a binary name cannot be defined twice as two independent named classes in the same loader namespace. If you want two named classes with the same binary name, they typically must be defined by **two different defining class loaders**.

## 5. Why `hidden.getName()` Cannot Be Used with `Class.forName`

To answer accurately, we must distinguish between **the name returned by Reflection** and **a binary name that can be recorded in a class file constant pool**.

### 5.1. A Hidden Class Name Has a Suffix Not Belonging to a Binary Name

On a hidden class, `Class.getName()` contains a `/` separating a classfile-style name `N` and a JVM-chosen suffix. The name observed on HotSpot typically looks like:

```text
HiddenClassNamesDemo$Template/0x0000000800...
```

The `...` in this example represents an abbreviated part; **there is no fixed suffix value** for applications to rely on. For the corresponding named nested class, `getName()` is simply:

```text
HiddenClassNamesDemo$Template
```

Only the second line is a valid **binary name** suitable for `Class.forName` when that class is defined in a loader that can see it.

`Class.getCanonicalName()` of a hidden class is `null`. `Class.descriptorString()` can contain a `.` in the suffix after the original name, making it **not a standard type descriptor usable as a symbolic field type** in the JVMS. Therefore, do not treat `hidden.getName()` or `hidden.descriptorString()` as formats that can be re-parsed by APIs that only accept nominal names like ordinary classes.

### 5.2. `Class.forName` Uses a Binary Name, Not Object Identity

`Class.forName("X")` is fundamentally a request to the JVM/class loader to find a class identified by a **string** in the access environment. It has no way to turn `"X/0x..."` into an existing `Class<?>` object of a hidden class. Even when:

- The hidden class and the host have the **same class loader**;
- The base name `X` matches another named class;
- Methods on the hidden class are `public`;
- The application has full reflection permissions;

… the ability to **retrieve from a string name** is still not added.

Conversely, `Class<?> hidden` and `MethodHandles.Lookup hiddenLookup` are **real references**; keeping these references allows direct interaction with the hidden class. This is a key design principle of the API.

### 5.3. What If the Original Name Also Exists?

Suppose the class bytes have the original name `HiddenClassNamesDemo$Template`. You can create a **hidden class** from those bytes, and also define an **ordinary class** with the same original binary name.

```text
Class.forName("HiddenClassNamesDemo$Template")
    -> finds the ORDINARY class (if present and loader is appropriate)

Class.forName(hidden.getName())
    -> cannot find the hidden class

hidden == named
    -> false
```

Do not infer that "`Class.forName` returned a class with the same code" means "`Class.forName` found the hidden class itself". Class identity governs type checking, static state, and method dispatch, not just byte-for-byte code.

## 6. Practice 1 — Same Bytes: Named Class Is Findable, Hidden Class Is Not

Create **`HiddenClassNamesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HiddenClassNamesDemo {
    static class Template {
        public static String greet(String name) {
            return "Hello, " + name;
        }
    }

    private static byte[] templateBytes() throws IOException {
        try (InputStream in = HiddenClassNamesDemo.class.getResourceAsStream(
                "HiddenClassNamesDemo$Template.class")) {
            if (in == null) {
                throw new IOException("Template bytecode resource not found");
            }
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = templateBytes();
        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup hiddenLookup = host.defineHiddenClass(bytes, true);
        Class<?> hidden = hiddenLookup.lookupClass();
        Class<?> named = host.defineClass(bytes);
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle hiddenMethod = hiddenLookup.findStatic(hidden, "greet", type);
        MethodHandle namedMethod = host.findStatic(named, "greet", type);

        System.out.println("hidden isHidden: " + hidden.isHidden());
        System.out.println("named isHidden: " + named.isHidden());
        System.out.println("different classes: " + (hidden != named));
        System.out.println("hidden has slash: " + hidden.getName().contains("/"));
        System.out.println("hidden canonical name null: "
                + (hidden.getCanonicalName() == null));
        System.out.println("hidden descriptor has dot suffix: "
                + hidden.descriptorString().contains("."));
        System.out.println("named forName works: "
                + (Class.forName(named.getName()) == named));
        try {
            Class.forName(hidden.getName());
            System.out.println("unexpected Class.forName result");
        } catch (ClassNotFoundException expected) {
            System.out.println("hidden forName: ClassNotFoundException");
        }
        try {
            hidden.getClassLoader().loadClass(hidden.getName());
            System.out.println("unexpected loadClass result");
        } catch (ClassNotFoundException expected) {
            System.out.println("hidden loadClass: ClassNotFoundException");
        }
        System.out.println("hidden invoke: "
                + (String) hiddenMethod.invokeExact("Ada"));
        System.out.println("named invoke: "
                + (String) namedMethod.invokeExact("Ada"));
    }
}
```

Compile and run in the same directory, so the compiler also generates the class file for the nested template:

```bash
javac --release 17 HiddenClassNamesDemo.java
java HiddenClassNamesDemo
```

**Verified exact stdout:**

```text
hidden isHidden: true
named isHidden: false
different classes: true
hidden has slash: true
hidden canonical name null: true
hidden descriptor has dot suffix: true
named forName works: true
hidden forName: ClassNotFoundException
hidden loadClass: ClassNotFoundException
hidden invoke: Hello, Ada
named invoke: Hello, Ada
```

### 6.1. Why Can the Program Define Both?

The `HiddenClassNamesDemo$Template.class` file was generated by `javac` as a resource. The program uses `getResourceAsStream(...)` to read the **bytes** of the nested class without referencing `Template.class` in code before `host.defineClass(bytes)`.

- `host.defineHiddenClass(bytes, true)` creates a separate hidden class with a runtime name suffixed by the VM.
- `host.defineClass(bytes)` defines a **named class** with the original binary name into the same lookup loader (previously this named class had not been defined by the JVM during this run).
- When `Class.forName(named.getName())` runs, the named class has already been defined so it can be found again.
- When `Class.forName(hidden.getName())` runs, the API has no name lookup path to find the hidden class.
- Because `hidden` and `named` are **two different class objects**, `hidden != named` even though the body of `greet` is identical.

### 6.2. Invoking a Hidden Method Without Looking Up by Name

`hiddenLookup.findStatic(hidden, "greet", type)` creates a `MethodHandle` using the hidden class's `Class<?>` directly. This is why the line `hidden invoke: Hello, Ada` still appears even though `Class.forName` fails.

`findStatic` checks method permissions/types against the appropriate `Lookup`; the fact that a hidden class can be used via a handle **does not** mean any other class has permission to call its private methods. Separate **ability to reference** from **access permissions**.

### 6.3. Why Avoid Printing the Full Hidden Class Name?

The suffix is dynamically chosen by the JVM, often related to identity and runtime context; if you print the full `hidden.getName()`, stdout is not reliable to assert as a fixed value across runs. The demo only prints **standard characteristics**: `isHidden`, the `/` character, `getCanonicalName()==null`, and `descriptorString` containing a suffix format differing from a standard binary descriptor.

In addition, `javac --release 17` only targets the Java 17 build API; the JVM running the application must support Java 17 class files and the APIs used.

## 7. How Does `initialize=false` Differ from `Class.forName(name,false,loader)`?

This is an important point when working with dynamic class loading.

### 7.1. `defineHiddenClass(bytes,false)` Already Created the Class; It Only Defers Initialization

Conceptual state:

```text
bytes
  |
  | defineHiddenClass(bytes, false)
  v
hidden Class<?> H has been derived + linked
  |
  | static initializer <clinit> is not yet required to run
  |
  | call Lookup.ensureInitialized(H)
  | or an operation that triggers initialization
  v
static initializer <clinit> of H runs
```

The `initialize` boolean does not mean "the class has not been created yet". The hidden class and `Class<?>` already exist; the JVM merely defers **initialization** of that class. `Lookup.ensureInitialized(...)` allows forcing class initialization with appropriate permissions.

### 7.2. With `Class.forName` for Named Classes

- `Class.forName("com.example.Foo")` has semantics requesting to **initialize** the named class if needed.
- `Class.forName("com.example.Foo", false, loader)` attempts to find/load the named class **without requiring immediate initialization**.
- Both approaches still rely on **the name of a named class**, not a hidden class.
- `ClassLoader.loadClass("...")` typically performs loading without immediate initialization; it does not turn into a lookup for a hidden class.

The four concepts **definition, loading, linking, initialization** can occur at different times. Use the exact phase name when reading class initializer logs.

### 7.3. Practice 2 — Two Hidden Classes and One Named Class Initialize Independently

Create **`HiddenInitializationDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public final class HiddenInitializationDemo {
    static class Payload {
        static {
            System.out.println("Payload <clinit>");
        }

        public static int value() {
            return 42;
        }
    }

    static byte[] code() throws IOException {
        try (InputStream in = HiddenInitializationDemo.class.getResourceAsStream(
                "HiddenInitializationDemo$Payload.class")) {
            if (in == null) throw new IOException("missing template class bytes");
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = code();
        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup lazy = host.defineHiddenClass(bytes, false);
        System.out.println("after define(false)");
        lazy.ensureInitialized(lazy.lookupClass());
        System.out.println("after ensureInitialized");

        MethodHandles.Lookup eager = host.defineHiddenClass(bytes, true);
        System.out.println("after define(true)");
        System.out.println("distinct hidden classes: "
                + (lazy.lookupClass() != eager.lookupClass()));

        Class<?> named = Class.forName(
                "HiddenInitializationDemo$Payload",
                false, HiddenInitializationDemo.class.getClassLoader());
        System.out.println("named is hidden: " + named.isHidden());
        Class.forName(named.getName());
        System.out.println("after named Class.forName");
    }
}
```

```bash
javac --release 17 HiddenInitializationDemo.java
java HiddenInitializationDemo
```

**Exact stdout:**

```text
after define(false)
Payload <clinit>
after ensureInitialized
Payload <clinit>
after define(true)
distinct hidden classes: true
named is hidden: false
Payload <clinit>
after named Class.forName
```

**Analysis:**

1. `defineHiddenClass(bytes,false)` creates the first hidden class without printing `Payload <clinit>`. The line `after define(false)` is printed before that class's class initializer runs.
2. `lazy.ensureInitialized(lazy.lookupClass())` causes the initializer to run once for the first hidden class.
3. `defineHiddenClass(bytes,true)` creates a **second hidden class** and initializes it immediately. Another `Payload <clinit>` line appears before `after define(true)`.
4. The two hidden classes have different identities despite identical bytes; therefore, each class's `<clinit>` runs separately.
5. `Class.forName(name,false,loader)` finds the named `Payload` without initializing it. `Class.forName(named.getName())` then initializes the named class and prints the **third** `Payload <clinit>` line.
6. All three classes in the example have the same initializer code, but they are not the same class. Hence printing three times is valid behavior, not a single initializer running repeatedly against the rules.

Note: if the named class had already been initialized earlier in the same JVM, `Class.forName` would not run the initializer again. The example keeps a self-contained sequence so stdout is deterministic.

## 8. `ClassOption.NESTMATE`: A Hidden Class Can Access the Host's Private Members

An ordinary nested class can be a **nestmate** of its enclosing class. Since Java 11, nestmates are the JVM mechanism that allows classes in the same nest to access each other's private members without needing synthetic accessors in many cases.

When defining a hidden class from bytes:

- **Default (without `NESTMATE`):** the hidden class is a nest of its own, and **does not automatically inherit the nest** of the template classfile or of the host Lookup. `NestHost`/`NestMembers` in the bytes do not automatically grant the hidden class the same rights as the original class.
- **With `NESTMATE`:** the hidden class is added as a nestmate of the **lookup class**. If the lookup class has an outer class as its nest host, the hidden class becomes a member of that nest.
- Nestmate grants private access **according to nest membership rules**, not the ability to access any private member of any class in the JVM.
- The hidden class still **has no binary name**; adding `NESTMATE` does not make `Class.forName` able to find it.

### 8.1. Why Is This an Important Feature?

Code-generating frameworks may need to directly call a private helper on the host safely, under the lookup class's permissions. If a hidden class is created without nestmate, bytecode accessing private members will be checked and can throw `IllegalAccessError` when resolving the operation. With `NESTMATE` and valid permissions, the access can succeed.

### 8.2. Practice 3 — Same Bytes, With/Without `NESTMATE`

Create **`HiddenNestmateDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HiddenNestmateDemo {
    private static String secret = "sealed";
    static class Reader {
        public static String read() {
            return secret;
        }
    }

    static byte[] code() throws IOException {
        try (InputStream in = HiddenNestmateDemo.class.getResourceAsStream(
                "HiddenNestmateDemo$Reader.class")) {
            if (in == null) throw new IOException("missing class bytes");
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = code();
        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup nested = host.defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> allowed = nested.lookupClass();
        MethodHandle reader = nested.findStatic(
                allowed, "read", MethodType.methodType(String.class));

        System.out.println("nestmate hidden: " + allowed.isHidden());
        System.out.println("nest host matches outer: "
                + (allowed.getNestHost() == HiddenNestmateDemo.class));
        System.out.println("nestmate reads: " + (String) reader.invokeExact());

        MethodHandles.Lookup isolated = host.defineHiddenClass(bytes, false);
        Class<?> denied = isolated.lookupClass();
        System.out.println("default nest host is self: "
                + (denied.getNestHost() == denied));
        try {
            MethodHandle deniedMethod = isolated.findStatic(
                    denied, "read", MethodType.methodType(String.class));
            String result = (String) deniedMethod.invokeExact();
            System.out.println("unexpected: " + result);
        } catch (IllegalAccessError expected) {
            System.out.println("without NESTMATE: IllegalAccessError");
        }
    }
}
```

```bash
javac --release 17 HiddenNestmateDemo.java
java HiddenNestmateDemo
```

**Exact stdout:**

```text
nestmate hidden: true
nest host matches outer: true
nestmate reads: sealed
default nest host is self: true
without NESTMATE: IllegalAccessError
```

Why?

1. `Reader.read()` is compiled by the compiler to read the private field `HiddenNestmateDemo.secret`, normally permitted by the nestmate relationship between the nested class and the outer class.
2. When `Reader.class` bytes are defined **hidden with `NESTMATE`**, the new hidden class becomes a nestmate of the lookup class `HiddenNestmateDemo`, so it can read the private field.
3. `allowed.getNestHost()` returns `HiddenNestmateDemo.class` as expected.
4. When using the same bytes to create a hidden class **without `NESTMATE`**, that class forms its own nest. Even though the original bytes came from nested `Reader`, the hidden copy **does not automatically inherit private access** from it.
5. When invoking the method that attempts to access the outer class's private field, the JVM rejects it with `IllegalAccessError`. This shows that nest permissions depend on **how the hidden class was defined**, not solely on the template's name or code.
6. `defineHiddenClass(bytes,false)` in the non-nestmate branch does not initialize immediately. The error appears when the method attempts to access the forbidden member; do not confuse it with `ClassNotFoundException` from `Class.forName`.

**Note:** `NESTMATE` does not change module policies, does not allow bypassing lookup permissions, and does not make the hidden class nominally discoverable.

## 9. `ClassOption.STRONG`: Class Lifecycle, Not Findability by Name

By default, a hidden class has a **weak** relationship with its defining loader: the JVM can unload the hidden class even while its loader remains reachable, as long as no references remain that keep the class alive. This is useful for runtimes that generate many temporary classes.

`MethodHandles.Lookup.ClassOption.STRONG` changes the **unloading relationship**:

- A `STRONG` hidden class has a strong relationship with its defining loader just like an ordinary class.
- In principle, a STRONG class can be unloaded if and only if its defining loader is no longer reachable and can be reclaimed under the corresponding rules.
- A **non-STRONG** hidden class can still live long if the application retains its `Class<?>`, `Lookup`, `MethodHandle`, or related instances that keep the class reachable.
- Not having `STRONG` **does not mean** the JVM must unload it immediately when you set `Class<?> = null`; GC and class unloading do not guarantee timing.
- Having `STRONG` **does not mean** the hidden class becomes a named class or is registered in the lookup table by binary name.

Choose `STRONG` when the lifecycle needs to be tightly bound to the loader; do not choose it just hoping `Class.forName` will work. To actually test unloading policies, you need GC/class-unloading tools and proper measurement procedures; **you cannot prove lifecycle solely with a single `System.gc()` call**.

### 9.1. Same Bytes, Multiple Hidden Classes with Independent Static State

If two hidden classes share the same bytecode `static int count; static int next(){return ++count;}`, each class has **its own copy of the static field**. They can have the same loader, same package, and same original nominal name, yet their identities and states remain distinct.

### 9.2. Practice 4 — One Normal Hidden Class and One `STRONG`

Create **`HiddenIsolationDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HiddenIsolationDemo {
    static class Counter {
        private static int count;
        public static int next() {
            return ++count;
        }
    }

    static byte[] code() throws IOException {
        try (InputStream in = HiddenIsolationDemo.class.getResourceAsStream(
                "HiddenIsolationDemo$Counter.class")) {
            if (in == null) throw new IOException("missing class bytes");
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup host = MethodHandles.lookup();
        byte[] bytes = code();
        MethodHandles.Lookup first = host.defineHiddenClass(bytes, true);
        MethodHandles.Lookup second = host.defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.STRONG);
        Class<?> a = first.lookupClass();
        Class<?> b = second.lookupClass();
        MethodType signature = MethodType.methodType(int.class);
        MethodHandle nextA = first.findStatic(a, "next", signature);
        MethodHandle nextB = second.findStatic(b, "next", signature);
        System.out.println("distinct: " + (a != b));
        System.out.println("first call A: " + (int) nextA.invokeExact());
        System.out.println("second call A: " + (int) nextA.invokeExact());
        System.out.println("first call B: " + (int) nextB.invokeExact());
        System.out.println("both hidden: " + (a.isHidden() && b.isHidden()));
        System.out.println("same loader: " + (a.getClassLoader() == b.getClassLoader()));
        try {
            Class.forName(b.getName());
            System.out.println("unexpected Class.forName result");
        } catch (ClassNotFoundException expected) {
            System.out.println("STRONG still undiscoverable: ClassNotFoundException");
        }
    }
}
```

```bash
javac --release 17 HiddenIsolationDemo.java
java HiddenIsolationDemo
```

**Exact stdout:**

```text
distinct: true
first call A: 1
second call A: 2
first call B: 1
both hidden: true
same loader: true
STRONG still undiscoverable: ClassNotFoundException
```

**Explanation:**

1. `first` and `second` are defined twice from **the same bytes**, yet `a != b`.
2. Calls to `nextA` increment `a`'s own counter: `1` then `2`.
3. The first call to `nextB` returns `1` because `b` has its own counter.
4. `a` and `b` both belong to the same defining loader, and `isHidden()` is true for both.
5. The `STRONG` option for `b` **does not** make `Class.forName(b.getName())` able to find it. The `ClassNotFoundException` line is concrete evidence.

**Do not over-infer from stdout:** This test does not prove that class `a` was unloaded or that class `b` definitely remains in memory forever. It only demonstrates **type identity, state, and lookup behavior**; unloading policy is explained by the API specification.

## 10. Reflection and `MethodHandle`: Hold the Class Reference Instead of Guessing the Name

### 10.1. Do Not Construct a Class Name and Call `Class.forName`

A wrong approach when building a dynamic runtime:

```java
// Anti-pattern: hiddenClass.getName() is not a binary name.
// Class<?> lookedUp = Class.forName(hiddenClass.getName());
```

The right approach: keep the `Class<?>` or `Lookup` object returned from the definition step.

```java
// Fragment: bytes is a valid class file in the same package.
MethodHandles.Lookup generatedLookup =
        privilegedLookup.defineHiddenClass(bytes, true);
Class<?> generatedType = generatedLookup.lookupClass();
// Look up the method using generatedLookup and generatedType, not Class.forName.
```

This is an illustrative fragment; `privilegedLookup` is not defined standalone. The programs above use `MethodHandles.lookup()` from a host with appropriate privileges to provide a self-contained example.

### 10.2. Reflection Can Be Used, Still Subject to Permissions

Example with a known `Class<?> hidden`:

```java
// Fragment: hidden is the Class<?> of a hidden class.
java.lang.reflect.Method[] methods = hidden.getDeclaredMethods();
for (java.lang.reflect.Method method : methods) {
    System.out.println(method.getName());
}
```

`getDeclaredMethods()` can list methods declared on the hidden class. **Invoking** private methods or sensitive members still requires appropriate reflection/module/nest permissions. `Class.isHidden()` is not a condition that forbids all reflection.

### 10.3. Interacting with `Class::getName` and Logging

In logging/metrics, you can print `hidden.getName()` to aid diagnostics. However, you should not:

- Save this name into configuration and expect `Class.forName` to resolve it again after a restart.
- Use the auto-generated name as a stable business key.
- Parse the suffix with regex and depend on internal JVM layout.
- Concatenate strings from the original name to find another hidden class with identical code.
- Call `ClassDesc.of(hidden.getName())` as if it were a valid binary name.
- Treat `descriptorString()` of a hidden class as a standard JVMS field descriptor to write into another class's class file.

When runtime identity is needed, keep `Class<?>` or an application-managed ID. An observation-oriented string cannot replace a real reference.

## 11. Hidden Classes, Class Loaders, and Unloading: Layers of Responsibility

### 11.1. Same Loader Does Not Mean Same Name Lookup

A named class and a hidden class can return the same `getClassLoader()`, yet only the named class has a binary name for the loader to resolve via `loadClass`. The same class loader is the **defining context**, not proof that every class of that loader is discoverable by string.

### 11.2. Two Different Loaders Can Hold Named Classes with the Same Name

Even with named classes, a name like `com.example.Plugin` is not enough to identify a unique class identity across the entire JVM. `Plugin` defined by loader A can be **different** from `Plugin` defined by loader B, even though the binary name is identical. `Class.forName(name, initialize, loader)` has a loader argument because identity is tied to the loader and lookup environment.

For hidden classes, identity is even more specific: defining again from the same bytes in the **same loader** also creates a different class object. Therefore:

```text
Named class identity ≈ (binary name, defining loader)
Hidden class identity = a distinct definition created by the JVM

Same code/loader does not guarantee same class identity.
```

The above is a learning model. Actual identity also obeys JVM module/nest/method resolution rules, but can be checked directly by comparing `Class<?>` references with `==`.

### 11.3. When Does Class Unloading Matter?

A runtime can generate thousands of hidden classes for expressions, call-site adapters, dynamic proxies, or helper methods. If every class were forced to stay alive with the loader for the entire lifetime of the loader, metadata memory could grow significantly. The default weak relationship allows the VM to reclaim hidden classes if they are no longer reachable under GC rules.

However, holding a `MethodHandle` or `Class<?>` in a global cache can keep a hidden class alive longer than intended. Therefore:

- Scope caches to appropriate lifetimes; avoid retaining every generated class indefinitely.
- Do not rely on `System.gc()` to verify correctness of class unloading.
- Only choose `STRONG` when a loader-bound lifetime model is needed.
- Do not use `Class.forName` as a tool to check whether a hidden class is still alive or unloaded; this API **never finds hidden classes**, even while the class is alive.

### 11.4. Design Purpose: No Name-Based Linkage Needed for Temporary Implementations

Many runtime generators only want **an invokable implementation**, without wanting the new class to be referenced nominally from other class code. Hidden classes serve that goal; recognizing this type helps explain why a lambda runtime implementation sometimes has a class name that cannot be called back via `Class.forName`.

However, **do not assert that every lambda on every JVM is necessarily a hidden class**. That is a JVM/runtime implementation choice; the Java language only specifies the functional interface contract and lambda behavior. Use `obj.getClass().isHidden()` if you actually need to observe what the runtime is using.

## 12. Common Errors and Exceptions

| Symptom / exception | Typical cause | How to handle |
| --- | --- | --- |
| `ClassNotFoundException` on `Class.forName(hidden.getName())` | Hidden class **has no lookup-able binary name** | Keep `Class<?>`/`Lookup`/`MethodHandle`; do not look up by string |
| `ClassNotFoundException` on `Class.forName(namedName)` | Class loader/class path/module context or binary name mismatch | Check defining loader, binary name (nested uses `$`), visibility |
| `LinkageError` when calling `defineClass(bytes)` twice | Named class with the same binary name already defined in the same defining loader | Avoid duplicates; use a separate loader or hidden classes if dynamic implementations are needed |
| `IllegalAccessException` at `defineHiddenClass` | `Lookup` lacks full privilege | Provide a properly privileged lookup from the caller; do not use `publicLookup` |
| `IllegalArgumentException` when bytes have a different package | Hidden class must belong to the lookup class's matching package | Fix internal name/package in the generator, or use a lookup in the right package |
| `ClassFormatError`/`VerifyError` | Bytes do not form a valid class file or bytecode fails verification rules | Validate compiler/generator, classfile version, constant pool/stack frames |
| `IllegalAccessError` when hidden code reads a private host field | Missing `NESTMATE` or invalid nest/private access | Use `NESTMATE` when permitted and intended, check `getNestHost()` |
| `NoSuchMethodException` on `Lookup.findStatic` | Wrong method name/type looked up | Check `MethodType`, return type, static vs instance |
| `WrongMethodTypeException` on `invokeExact` | Call-site type differs from handle type (including return type) | Inspect `handle.type()`, cast result accurately or use a valid adapter |
| `ExceptionInInitializerError` | `<clinit>` throws an exception when initializing hidden or named class | Inspect the cause, distinguish define/link time from initialization time |
| `NullPointerException` when reading bytecode resource | `getResourceAsStream(...)` returns `null` due to missing `.class` | Check path/resource; handle missing resource before defining |
| GC does not unload hidden class as expected | References still retain the class, `STRONG` was used, or GC has not decided to unload | Check cache/lifecycle/loader, use class unloading observation tools |
| Name in stack trace has `/0x...` | Runtime method belongs to a hidden class | Expected indicator; do not use the suffix to locate via Class.forName |
| Named `Class.forName` finds a different class from hidden | Same class bytes but **two definitions** | Compare `Class<?>` identity, loader, and `isHidden()` |

### 12.1. `ClassNotFoundException` Does Not Mean the Hidden Class Was Not Defined

If you already have `Class<?> hidden` and `hidden.isHidden()==true`, `Class.forName(hidden.getName())` failing is **intended design behavior**, not a missing class file loading error. Do not try adding classpath entries to "fix" that lookup. You need to pass the corresponding class reference/Lookup instead of the name.

### 12.2. Pay Attention to API Types When Debugging

- `Lookup.defineHiddenClass`: defines and links a hidden class from bytes.
- `Lookup.defineClass`: defines a named class from bytes.
- `Class.forName`: finds/loads a class by binary name (and initializes depending on overload).
- `ClassLoader.loadClass`: mechanism to find/load a named class by name.
- `Class.getName`: reports the runtime name; **does not guarantee** every returned name can be reloaded via `Class.forName`.
- `Class.isHidden`: checks hiddenness directly on `Class<?>`.
- `Lookup.ensureInitialized`: requests class initialization, with appropriate permissions.
- `MethodHandles.Lookup.ClassOption.NESTMATE`: alters nest membership when defining a hidden class.
- `MethodHandles.Lookup.ClassOption.STRONG`: alters the unloading relationship when defining a hidden class.

Do not lump all of these operations into a vague phrase "load class".

## 13. Designing Applications to Use Hidden Classes Properly

### 13.1. Return a Named Interface, Hide the Runtime Implementation

A public API can return an object implementing `Runnable`, `Callable<R>`, or a named domain interface. The implementation created at runtime via a hidden class can be called through the interface without the client needing the implementation name.

```text
Client code:
    Task task = factory.createTask();  // Task is a named interface
    task.run();                         // invoke interface contract

Runtime factory:
    bytes of hidden implementation
       |
    defineHiddenClass(..., options)
       |
    Lookup + Class<?> hidden
       |
    create appropriate instance / MethodHandle / constructor
       |
    return Task to client
```

This is a **diagram**, not a standalone Java program. The goal is to keep the API stable as a named interface, while the implementation code can be generated and reclaimed flexibly.

### 13.2. Accessing Host Private Members with Controlled Permissions

If a framework needs to implement a private helper on the host, `NESTMATE` is appropriate when the host itself provides a sufficiently privileged lookup. Do not treat `NESTMATE` as a way to arbitrarily escalate privileges for untrusted bytecode; the defined bytes will execute code with permissions according to the granted context.

This is especially important if input comes from untrusted users/plugins. Before calling `defineHiddenClass`, you must know the source of the bytes, classfile validation, and the application's sandbox/permission model. A hidden class **is not a sandbox**; "not findable by name" does not mean "safe to run arbitrary code".

### 13.3. Memory and Long-Running Operations

If a runtime creates a new hidden class for every expression:

- Consider caching keyed by expression semantics rather than creating unbounded duplicates.
- Do not retain class references in an unbounded static collection.
- Use weak/strong lifecycles intentionally and monitor memory.
- If you need to discover/persist a stable class by binary name across runs, hidden classes are **not suitable**; use a named class with the appropriate class loader/packaging.
- When designing serialization/protocols, do not rely on a hidden runtime class name to deserialize via `Class.forName`.

## 14. Self-Check Questions

1. What main parameters does `defineHiddenClass` take and what does it return?
2. Why does `Class.forName(hidden.getName())` fail even when `hidden.isHidden()==true` and the hidden class is alive?
3. Are a named class and a hidden class created from the same bytes necessarily the same `Class<?>`?
4. Does `Class.forName("Host$Template")` finding a named class mean it found the hidden copy of `Host$Template`?
5. What special character does `Class.getName()` of a hidden class contain that makes it not a binary name?
6. Can `MethodHandle` be used to call a method on a hidden class when `Class.forName` cannot find it?
7. Does `initialize=false` mean the class has not been created yet, or that it has been created without requiring `<clinit>` to run yet?
8. How are `defineHiddenClass(bytes,true)` and `Class.forName(name)` similar/different?
9. What does `NESTMATE` change? Why can the same bytes read a private field with the option, yet throw `IllegalAccessError` without it?
10. Does `STRONG` allow `ClassLoader.loadClass(hidden.getName())`?
11. If two hidden classes use the same bytes and the same loader, do their static fields share data?
12. Why can you not rely on `System.gc()` to verify that a hidden class has unloaded?
13. Can `MethodHandles.publicLookup()` arbitrarily `defineHiddenClass` into the package of any class?
14. Can a hidden class be seen by code via `obj.getClass()`?
15. When should you use a named class instead of a hidden class to support discovery?
16. If a named nested class has binary name `com.example.Outer$Inner`, is `Class.forName("com.example.Outer.Inner")` an appropriate name?

### Suggested Answers

1. `byte[] bytes`, `boolean initialize`, optional `ClassOption...`; returns a `Lookup` on the new hidden class.
2. A hidden class has no binary name; `Class.forName` is a nominal lookup and cannot find it.
3. No; each class definition creates a distinct identity.
4. No; that is the named class by binary name, not the hidden copy.
5. The `/` character and VM-generated suffix; not a valid binary name.
6. Yes; use `hiddenLookup.findStatic(...)`, `findVirtual(...)`, or reflection with the retained `Class<?>` and appropriate permissions.
7. The class is already created/linked, but initialization can be deferred.
8. Both can lead to initialization, but one **defines a hidden class from bytes**, while the other **finds/loads a named class by name**.
9. Adds the hidden class to the lookup class's nest, permitting valid private access; without NESTMATE, it defaults to a self-nest.
10. No; STRONG only affects the unloading relationship.
11. No; `Class<?>` identity and static state are separate.
12. The JVM/GC decides the timing; references can retain the class, and GC has no guaranteed schedule.
13. No; `defineHiddenClass` requires full privilege and a matching package/module.
14. Yes; hidden does not mean invisible to Reflection.
15. When nominal references, `Class.forName`, configured class names, or a stable ABI are needed.
16. No; nested binary names use `$`.

## 15. Original References for Lookup

- [Java SE 21 API — `MethodHandles.Lookup.defineHiddenClass` and `Lookup.defineClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): bytecode, package, full privilege access, initialize, hidden name, NESTMATE/STRONG, and common errors.
- [Java SE 21 API — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): the two values `NESTMATE` and `STRONG`, private access, and lifecycle.
- [Java SE 21 API — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `isHidden`, `getName`, `getCanonicalName`, `descriptorString`, and why `Class.forName` does not find hidden classes.
- [Java SE 21 API — `MethodHandles`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): how to create a Lookup and methods for finding method handles.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): design motivation, non-discoverability, lifecycle, lack of binary name, and replacement of the old anonymous-class mechanism.
- [JVMS Java SE 21 — `5.3.5 Deriving a Class from a class File Representation`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.5): ordinary classes, distinguishing how the VM derives classes.
- [Java SE 21 JLS — `12.4 Initialization of Classes and Interfaces`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4): timing of `<clinit>` execution.
- [Java SE 21 JLS — `12.7 Unloading of Classes and Interfaces`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.7): principles of class unloading.
- [Oracle JDK 15 Release Notes — JEP 371 impacts](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): `Class.getName` of a hidden class has `/` and `descriptorString` contains a special suffix.

**Conclusion:** `defineHiddenClass` creates **a real class without a binary name for nominal lookup**; therefore, `Class.forName(hidden.getName())` cannot recover that `Class<?>`. When you want to use a hidden implementation, keep a `Lookup`, `Class<?>`, or `MethodHandle` reference. If you need a named class to find via `Class.forName`, use the **named class** mechanism and the appropriate class loader. The `initialize` parameter, `NESTMATE`/`STRONG` options, and class unloading mechanism are separate design axes from whether the class can be found by name.