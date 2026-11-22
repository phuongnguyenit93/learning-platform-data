# Version, Class Structure, and Access Constraints When Defining Classes Dynamically in Java

**Dynamic class definition** is the process by which the JVM receives a sequence of class-file bytecode at runtime and creates a `Class<?>` object representing a new type in the class loader's namespace. Related APIs include `ClassLoader.defineClass(...)`, `ClassLoader.findClass(...)`, and `MethodHandles.Lookup.defineClass(...)`. This step is completely different from `new SomeClass()`: **defining a class creates a runtime type, does not automatically create an instance of that class, and does not run the static initializer by default**.

A seemingly valid byte array is not enough for the JVM to accept the definition. The JVM checks the **class-file version**, structure/bytecode, binary name, package, relationships with superclass/interfaces, access permissions, and linking constraints. Some errors occur immediately at `defineClass`; others may only appear during `resolveClass`, reflective lookup, class initialization, or the first method invocation.

This lesson focuses on **“Version, Class Structure, and Access Constraints When Defining Classes Dynamically”** in the **Dynamic Class Definition** group of **Java core – classloader**, using JDK 17+ as the baseline and compilable/runnable examples.

## 1. Five layers of constraints to distinguish

| Layer | Key question | Example |
| --- | --- | --- |
| **Class-file version** | Does the current JVM understand this bytecode's format/features? | Major 65 from Java 21 on a JVM supporting only up to 61 from Java 17 |
| **Class-file format / verification** | Do the bytes have valid `ClassFile` structure, constant pool, methods, bytecode, stack-map, and invariants? | Wrong magic number, corrupted constant pool, verification type mismatch |
| **Identity / name / linkage** | Does the passed binary name match the class file? Does the loader define duplicates? Do references resolve validly? | `NoClassDefFoundError` due to wrong name, duplicate-definition `LinkageError` |
| **Runtime package / module / access** | Does the new class have permission to use target types/members or module packages? | Package-private member with the same package name but a different defining loader |
| **Protection domain / code source / package consistency** | Which security domain does the class belong to? Does the package have compatible certificates/sealing rules? | `SecurityException` when package signatures are inconsistent |

**Do not lump all errors into a single `catch (Exception)`.** Most verification/linking errors belong to the `Error` family (`LinkageError` and its subclasses). When debugging, you must distinguish between **bytes not found**, **invalid bytes**, **bytes that can be defined but have invalid access**, and **a class that can be loaded but fails during subsequent execution**.

## 2. Runtime type identity: binary name is not enough

In the JVM, two classes can share the same `Class.getName()` yet be different runtime types if defined by **two different defining loaders**:

```text
name = "plugins.Task"

(hostLoader defines plugins.Task)   → runtime Class A
(pluginLoader defines plugins.Task) → runtime Class B

A.getName().equals(B.getName()) → true
A == B                           → false
```

A practical interpretation: runtime class identity depends on **binary name + defining class loader**. This directly affects:

- `instanceof`, casting, and `Class.isAssignableFrom`;
- reflective lookup on parameter/return types;
- package-private access;
- interfaces shared between host and plugin;
- static state and class initialization of each runtime definition;
- loader constraints when method descriptors cross multiple loaders.

When implementing plugins, **host API/SPI/DTO classes** should be defined once by a shared loader, while implementations/private dependencies can be defined by separate loaders. If both sides independently define `api.Plugin` from the same source code, the plugin's object still may not be castable to the host API.

## 3. What does `ClassLoader.defineClass` take and return?

Common overloads:

```java
protected final Class<?> defineClass(
        String name, byte[] bytes, int offset, int length);

protected final Class<?> defineClass(
        String name, byte[] bytes, int offset, int length,
        java.security.ProtectionDomain domain);
```

These are **abbreviated API signatures for reading**, not methods you must declare yourself (they already exist in `ClassLoader`). `defineClass` is `protected final`: a non-subclass caller cannot invoke it directly on an arbitrary loader; subclasses typically expose it through `findClass`.

Parameters:

- `name` is the expected **binary name**, such as `"demo.generated.DynamicHello"`; do not pass `"demo/generated/DynamicHello.class"`.
- `bytes` is all or a slice of the **class-file bytes**, not UTF-8 Java source.
- `offset` and `length` determine the valid slice in the array; a negative offset or exceeding the bounds can cause `IndexOutOfBoundsException`.
- `domain` specifies the `ProtectionDomain` if using the explicit overload; `null` uses the default domain according to the Javadoc.
- The result is the newly defined `Class<?>` (if successful), **not yet an object instance**.

The Javadoc recommends passing a **non-null binary name** so it can be matched against the actual binary name inside the bytes and enforce the related constraints. The old `defineClass(byte[], int, int)` overload without a name parameter is deprecated and should not be used for new code.

### `findClass` differs from `defineClass`

`findClass(name)` is the hook to **locate bytes and then call `defineClass`** if needed. `loadClass(name)` normally checks if the class is already loaded and tries the parent first before reaching `findClass`.

```text
loadClass("demo.generated.DynamicHello")
      ├─ findLoadedClass(...)
      ├─ parent delegation
      └─ findClass(...)
            ├─ read /generated-out/demo/generated/DynamicHello.class
            └─ defineClass("demo.generated.DynamicHello", bytes, ...)
                       ↓
                    Class<?>
```

If you only want to add a bytecode source, you should typically **override `findClass` rather than overriding `loadClass` yourself** to preserve proper synchronization, parent delegation, and avoid duplicate definitions.

## 4. Practice A — defining a Java 17 class from a bytecode file

Create two source files with **separate output folders** so the host does not accidentally see the dynamic class on the application classpath.

```text
define-lab/
├── src/
│   ├── generated/demo/generated/DynamicHello.java
│   └── host/demo/DefineDemo.java
├── generated-out/      (generated by javac)
└── host-out/           (generated by javac)
```

**`src/generated/demo/generated/DynamicHello.java`:**

```java
package demo.generated;

public final class DynamicHello {
    static {
        System.out.println("DynamicHello initialized");
    }

    public DynamicHello() {
        System.out.println("DynamicHello constructed");
    }

    public String say() {
        return "Hello from dynamically defined class";
    }
}
```

**`src/host/demo/DefineDemo.java`:**

```java
package demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DefineDemo {
    static final class ByteFileLoader extends ClassLoader {
        ByteFileLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = Path.of("generated-out",
                    name.replace('.', '/') + ".class");
            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ByteFileLoader loader = new ByteFileLoader();

        Class<?> type =
                loader.loadClass("demo.generated.DynamicHello");

        System.out.println("defined by child=" +
                (type.getClassLoader() == loader));
        System.out.println("type=" + type.getName());
        System.out.println("before constructor");

        Object instance = type.getDeclaredConstructor().newInstance();
        String greeting =
                (String) type.getMethod("say").invoke(instance);

        System.out.println("result=" + greeting);
    }
}
```

From the `define-lab` directory, compile and run using JDK 17+:

```sh
javac --release 17 -d generated-out src/generated/demo/generated/DynamicHello.java
javac --release 17 -d host-out src/host/demo/DefineDemo.java
java -cp host-out demo.DefineDemo
```

**Stdout with the stated structure:**

```text
defined by child=true
type=demo.generated.DynamicHello
before constructor
DynamicHello initialized
DynamicHello constructed
result=Hello from dynamically defined class
```

**Key milestones:**

1. `ByteFileLoader` has the platform loader as its parent and does not automatically see classes in `generated-out`.
2. `loader.loadClass` calls the child's `findClass` because the parent cannot find the binary name.
3. `Files.readAllBytes` retrieves the bytecode generated by `javac`; `defineClass` creates the runtime class and returns `Class<?>`.
4. When `defined by child` and `type` are printed, the static initializer **has not run yet**.
5. `getDeclaredConstructor().newInstance()` creates an object and requires class initialization if not yet completed: the static block prints before the constructor.
6. `getMethod("say").invoke(instance)` calls the instance method, rather than defining the class again.

**Crucially:** the `java` command does **not** have `generated-out` on `-cp`. If you add that directory to the application classpath and use the system loader as the parent, parent-first delegation may define `DynamicHello` first; `type.getClassLoader() == loader` is then no longer guaranteed to be `true`. This is why the exercise deliberately separates the output directories.

`Path.of("generated-out", ...)` uses a path relative to the working directory; the commands must be run from `define-lab`. The example reads a file to learn about bytecode, not as a loader to be used directly for untrusted sources.

## 5. Class-file version limits: major/minor

The beginning of every class file has a basic structure:

```text
u4 magic            = 0xCAFEBABE
u2 minor_version
u2 major_version
u2 constant_pool_count
... constant_pool
... access_flags, this_class, super_class
... interfaces, fields, methods, attributes
```

**Major version** indicates which Java version era the class-file format belongs to. Common milestones:

| Java release | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

A JVM only supports class-file versions within the range it recognizes. For **Java 17**, a class with major version **65** (Java 21) or intentionally set to **100** cannot be defined normally: it typically throws **`UnsupportedClassVersionError`**.

**Do not infer from a `.class` file name, JAR name, or `sourceCompatibility` property** that the bytes already have the right version. Inspect them directly:

```sh
javac --release 17 -d generated-out src/generated/demo/generated/DynamicHello.java
javap -verbose -classpath generated-out demo.generated.DynamicHello
```

In the `javap -verbose` output, look for the line:

```text
major version: 61
```

`javac --release 17` both targets the Java 17 language/bytecode and restricts public APIs appropriate for the selected release. Enabling only `-source` while forgetting target/release is not always enough to avoid accidentally depending on newer-version APIs.

### Preview features also have conditions

It is not just the major version: there are specific rules for **preview class files** that use a special minor version. Bytes built with preview features may only run when the JVM supports that exact release with `--enable-preview`; merely having a major version within range is not sufficient for validity. When encountering `UnsupportedClassVersionError`, inspect both **major/minor**, compiler flags, and the JVM version.

## 6. Practice B — wrong binary name, invalid bytes, and too-new version

Reuse `generated-out/demo/generated/DynamicHello.class` from practice A; there is no need to run `DefineDemo`. Create the file **`src/host/demo/ClassBytesCheckDemo.java`**:

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public final class ClassBytesCheckDemo {
    static final class Definer extends ClassLoader {
        Definer() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> put(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] correct = Files.readAllBytes(Path.of(
                "generated-out/demo/generated/DynamicHello.class"));

        try {
            new Definer().put("demo.generated.WrongName", correct);
        } catch (NoClassDefFoundError error) {
            System.out.println("wrong name: " +
                    error.getClass().getSimpleName());
        }

        try {
            new Definer().put("demo.generated.Bad", 
                    "not a class".getBytes(StandardCharsets.UTF_8));
        } catch (ClassFormatError error) {
            System.out.println("bad bytes: " +
                    error.getClass().getSimpleName());
        }

        byte[] tooNew = correct.clone();
        tooNew[6] = 0;
        tooNew[7] = 100; // major = 100, not supported by Java 17

        try {
            new Definer().put("demo.generated.DynamicHello", tooNew);
        } catch (UnsupportedClassVersionError error) {
            System.out.println("too new: " +
                    error.getClass().getSimpleName());
        }
    }
}
```

Compile/run with **JDK 17**:

```sh
javac --release 17 -d host-out src/host/demo/ClassBytesCheckDemo.java
java -cp host-out demo.ClassBytesCheckDemo
```

**Expected stdout on Java 17/HotSpot with the bytes compiled above:**

```text
wrong name: NoClassDefFoundError
bad bytes: ClassFormatError
too new: UnsupportedClassVersionError
```

**Analysis of the three cases:**

- **Wrong name:** `defineClass("demo.generated.WrongName", correctBytes, ...)` is called, yet the file's actual `this_class` is `demo.generated.DynamicHello`. The `ClassLoader.defineClass` Javadoc clearly states that a mismatch leads to `NoClassDefFoundError`. That is not merely a `ClassNotFoundException`.
- **Bad bytes:** the string `"not a class"` is not a valid `ClassFile` (wrong magic/structure), so it throws `ClassFormatError`.
- **Too new:** bytes 6–7 represent the **major version** in the class file header (0-indexed). We change it from 61 to 100; Java 17 does not understand this version, resulting in `UnsupportedClassVersionError`.
- Each test uses a **new Definer instance** so that identity/duplicate-definition boundaries do not interfere with each other.
- `UnsupportedClassVersionError` extends `ClassFormatError`, so **catch the subclass before the superclass** if in the same try-block.

**Never patch class bytes arbitrarily in production.** Editing the version header does not “convert” bytecode instructions/attributes of a newer class file into code that can run on an older JVM. To run on Java 17, you must compile/transform with a supporting tool and remove incompatible features/APIs.

## 7. Class-file structure is more than just version

The `ClassFile` structure according to JVMS `4.1` consists of:

- **`magic`**: identifies the class file.
- **`minor_version` and `major_version`**: format version.
- **`constant_pool`**: symbolic references, UTF-8 strings, type/method/field descriptors, method handles, and related metadata.
- **`access_flags`**: modifiers such as public, final, interface, abstract, enum, annotation, module.
- **`this_class`/`super_class`**: the name of the class being defined and its superclass.
- **`interfaces`**: the interfaces declared by the class.
- **`fields`** and **`methods`**: signatures and metadata.
- **`attributes`**: `Code`, `StackMapTable`, annotations, `NestHost`/`NestMembers`, `Record`, `PermittedSubclasses`, etc.

The JVM must ensure **format checking** and **verification** according to the JVMS. A bytecode transformer/generator may produce:

- an out-of-bounds constant-pool index or wrong tag;
- a syntactically invalid descriptor;
- invalid instructions, inconsistent stack types;
- contradictory class declarations such as a final class being extended;
- a `StackMapTable` that does not match the bytecode;
- invalid names/inheritance cycles;
- an attribute inappropriate for the version or class kind.

Some issues cause **`ClassFormatError`**, others cause **`VerifyError`**, **`ClassCircularityError`**, or other `LinkageError` types depending on the phase. **Do not assume every bytecode error is thrown right at the `defineClass` call.** The JVM may perform some resolution lazily; errors can appear during `resolveClass` or when an instruction actually needs the reference.

### `javap` is an inspection tool, not a verifier replacing the JVM

```sh
javap -verbose -classpath generated-out demo.generated.DynamicHello
javap -c -p -classpath generated-out demo.generated.DynamicHello
```

`-verbose` displays the header/constant pool/attributes; `-c -p` displays bytecode including non-public members. The `javap` command reads the class file and **does not prove** that the runtime JVM loaded the class through the right loader, linked it successfully with all dependencies, or ran its initializer.

## 8. Binary name, package name, and path must be consistent

For the source:

```java
package demo.generated;

public class DynamicHello { }
```

The different names are:

| Concept | Value |
| --- | --- |
| Java source name | `demo.generated.DynamicHello` |
| Binary name | `demo.generated.DynamicHello` |
| Class-file relative path | `demo/generated/DynamicHello.class` |
| Internal JVM class name | `demo/generated/DynamicHello` |
| Descriptor used when referencing the type | `Ldemo/generated/DynamicHello;` |

When calling `loader.loadClass` or `defineClass(name, ...)`, pass the dot-separated **binary name**. When locating file bytes from a directory, you can convert `.` to `/`. Do not convert every `$` to `/`: the binary name of a nested class such as `demo.Outer$Inner` contains `$` as part of the binary name.

**Note on arrays:** `ClassLoader.defineClass` is not used to define an array class via a `ClassFile` carrying a name like `[L...;`. The JVM creates array classes via its own mechanism; `Class.getClassLoader()` of an array class reflects the element-type loader (or bootstrap for primitive arrays).

### What happens if the name does not match the bytes?

`defineClass("demo.generated.WrongName", correctBytes, ...)` reports `NoClassDefFoundError` (verified in example B), rather than automatically fixing the bytecode's name. You should not pass `name=null` just to bypass the issue: doing so drops certain checks and makes it harder for the code to guarantee accurate identity, source, and package.

## 9. A runtime package depends on the defining loader

In Java source, two classes declare the same:

```java
package shared;
```

However, package-private access at runtime does not depend solely on the `package` line. The JVM identifies a **runtime package** by the package name together with the **defining loader**. Therefore:

```text
AppLoader defines shared.Token           → runtime package P1
PluginLoader defines shared.DynamicAccess → runtime package P2

Text package name: shared == shared
Runtime package:    P1 != P2
```

As a result, `DynamicAccess` may not be permitted to access the parent's package-private `Token` or package-private method `Token.value()`, even though both declare `package shared;` in source.

This is an important point when dynamically generated classes use **ByteBuddy/ASM/JavaCompiler/custom ClassLoader** to “inject” a class into an existing package. **Having the same package name is not enough to obtain private/package access**.

In named modules, JPMS also has readability/exports/opens rules; do not treat defining-loader identity as a way to bypass module restrictions.

## 10. Practice C — same package name but denied package-private access

Project structure:

```text
access-lab/
├── src/
│   ├── host/shared/Token.java
│   ├── host/shared/AccessDemo.java
│   └── plugin/shared/DynamicAccess.java
├── host-out/
└── plugin-out/
```

**`src/host/shared/Token.java`:**

```java
package shared;

final class Token {
    static String value() {
        return "host-private-package";
    }
}
```

**`src/plugin/shared/DynamicAccess.java`:**

```java
package shared;

public final class DynamicAccess {
    public static String call() {
        return Token.value();
    }
}
```

The source above is valid when the compiler is given `host-out` as the compile classpath, because the Java compiler sees two source types in the same `shared` package. At runtime, however, they have **different defining loaders**.

**`src/host/shared/AccessDemo.java`:**

```java
package shared;

import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class AccessDemo {
    static final class PluginLoader extends ClassLoader {
        PluginLoader() {
            super(AccessDemo.class.getClassLoader());
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("shared.DynamicAccess")) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] bytes = Files.readAllBytes(Path.of(
                        "plugin-out/shared/DynamicAccess.class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("host call=" + Token.value());

        PluginLoader child = new PluginLoader();
        Class<?> dynamic = child.loadClass("shared.DynamicAccess");

        System.out.println("same textual package=" +
                dynamic.getPackageName().equals(
                        Token.class.getPackageName()));
        System.out.println("different defining loaders=" +
                (dynamic.getClassLoader()
                        != Token.class.getClassLoader()));

        try {
            dynamic.getMethod("call").invoke(null);
            System.out.println("unexpected success");
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println("cause=" +
                    cause.getClass().getSimpleName());
        }
    }
}
```

Compile from `access-lab`:

```sh
javac --release 17 -d host-out src/host/shared/Token.java src/host/shared/AccessDemo.java
javac --release 17 -cp host-out -d plugin-out src/plugin/shared/DynamicAccess.java
java -cp host-out shared.AccessDemo
```

**Stdout on OpenJDK/HotSpot 17 with this configuration:**

```text
host call=host-private-package
same textual package=true
different defining loaders=true
cause=IllegalAccessError
```

**Explanation:** `Token` is package-private and defined by the app loader. `DynamicAccess` is defined by the plugin loader itself despite sharing `package shared`. When `DynamicAccess.call()` bytecode attempts to call `Token.value()`, the JVM checks runtime accessibility; the two types do not belong to the same runtime package, causing `IllegalAccessError`. Reflection here only invokes a public static method `call`; the error actually originates **inside the method body**, so `Method.invoke` wraps it in `InvocationTargetException` and `getCause()` returns `IllegalAccessError`.

If the JVM performs eager resolution, the timing of reporting a linkage error may change; detailed messages/stacktraces also depend on the implementation. **The access principle does not change:** two separate defining loaders do not grant package-private access based solely on package name.

**Architectural fix:** move the required API to a **public shared contract**, or use a delegated mechanism such as `MethodHandles.Lookup.defineClass` with a valid lookup in the **same runtime package** when you genuinely need to create a class with package-private access. Do not arbitrarily add `setAccessible(true)` to bypass JVM linking/access rules.

## 11. `MethodHandles.Lookup.defineClass`: an option with specific constraints

Since Java 9, `MethodHandles.Lookup.defineClass(byte[])` can define a new class with the **same defining loader, same runtime package, and same protection domain** as the **lookup class**.

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> generated = lookup.defineClass(bytes);
```

This is a **snippet**: you need to import `java.lang.invoke.MethodHandles`, the variable `bytes` must contain valid class-file bytes, and the method must handle `IllegalAccessException`/linkage errors. When calling `MethodHandles.lookup()` from `demo.Host`, the class bytes must declare a class in the **same package** as `demo.Host`; that lookup cannot be used to arbitrarily define `another.package.Generated`.

Key conditions:

- The lookup must have **`PACKAGE` access mode**, showing that the caller has permission to operate in the corresponding runtime package.
- The bytes must carry a **class name belonging to the same package** as the lookup class; otherwise it will fail per the contract.
- The new runtime class is defined in the loader/module/package permitted by the lookup, rather than being arbitrarily attached to another loader object.
- Lookup.defineClass **does not run the class initializer** immediately; initialization may occur when the class is actively used later.
- The new class name must not duplicate a class already defined in the same defining loader.
- It does not automatically grant access to private members of unrelated classes; private access/nestmates must follow separate rules.

### Distinguishing `Lookup.defineClass` and `Lookup.defineHiddenClass`

`defineHiddenClass` (Java 15+) creates **hidden classes** for framework/runtime code generation. A hidden class is not a normal class that `Class.forName(binaryName)` can discover in the usual way; its name/identity and lifecycle differ. The API has options such as `NESTMATE` and a parameter requesting initialization.

Do not use a hidden class as a drop-in replacement for a plugin public API that needs to be discovered by binary name. Choose `Lookup.defineClass` when you need a **named class in the same package/loader as the lookup**, and `defineHiddenClass` when you truly need a runtime implementation class that does not rely on name-based discovery.

## 12. Practice D — `Lookup.defineClass` in the same runtime package

The following example creates a compiled class file in the `lookupdemo` package, then loads those bytes using the lookup of a host class **in the same package**.

Structure:

```text
lookup-lab/
├── src/
│   ├── generated/lookupdemo/GeneratedGreeter.java
│   └── host/lookupdemo/LookupDemo.java
├── generated-out/
└── host-out/
```

**`src/generated/lookupdemo/GeneratedGreeter.java`:**

```java
package lookupdemo;

public final class GeneratedGreeter {
    public String message() {
        return "defined with Lookup";
    }
}
```

**`src/host/lookupdemo/LookupDemo.java`:**

```java
package lookupdemo;

import java.lang.invoke.MethodHandles;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LookupDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of(
                "generated-out/lookupdemo/GeneratedGreeter.class"));

        Class<?> type = MethodHandles.lookup().defineClass(bytes);

        System.out.println("same defining loader=" +
                (type.getClassLoader()
                        == LookupDemo.class.getClassLoader()));
        System.out.println("same package=" +
                type.getPackageName()
                        .equals(LookupDemo.class.getPackageName()));

        Object object = type.getDeclaredConstructor().newInstance();
        System.out.println("message=" +
                type.getMethod("message").invoke(object));
    }
}
```

Compile/run on JDK 17:

```sh
javac --release 17 -d generated-out src/generated/lookupdemo/GeneratedGreeter.java
javac --release 17 -d host-out src/host/lookupdemo/LookupDemo.java
java -cp host-out lookupdemo.LookupDemo
```

**Stdout:**

```text
same defining loader=true
same package=true
message=defined with Lookup
```

The `java` command only exposes `host-out` to the application loader; `GeneratedGreeter.class` resides in a separate directory, so `Lookup.defineClass(bytes)` is what defines the class in the app loader. If you put `generated-out` on the application classpath and another code path has already loaded `lookupdemo.GeneratedGreeter`, `defineClass` will not be used to define a duplicate class.

**Access note:** this example uses only a public class/method. To practice package-private access, you can add a package-private class/member in the same package and verify when they are actually defined by the **same loader**; do not infer it from having the same package name in source.

## 13. Java access modifiers and JVM linking checks

There are at least three forms of access to distinguish:

1. **Java language access** when compiling source: `public`, `protected`, package-private, `private`; the compiler uses packages and module visibility.
2. **Runtime access checking** when linking or invoking references: the JVM evaluates **runtime package identity**, class/interface access, member accessibility, and applicable receiver rules.
3. **Reflection/MethodHandles access** when a caller looks up/invokes members: depends on the caller class, lookup modes, `AccessibleObject`, and JPMS `exports/opens`.

A dynamically defined class does not get “access to everything” just because its bytes were generated by the host. If the runtime class resides in a different loader, it does not have the host's package-private privileges. If it resides in a named module that cannot read another module, bytecode references may encounter access/linking errors.

### `public` is not always enough

A public class in a **non-exported** package of a named module does not automatically become accessible to arbitrary external modules. `public` is a condition of Java type access, whereas JPMS module readability/exports is a separate condition.

`opens` permits certain forms of deep reflection; it does not mean compile-time/public access across all modules is valid. Named modules are governed by the module graph and are not automatically “expanded” simply because a class loader defines an additional class.

**Do not equate** `IllegalAccessError` (a linking/runtime access error in bytecode) with `IllegalAccessException` (a checked exception from reflection/Lookup) or `InaccessibleObjectException` (deep reflection blocked by JPMS). They occur in different APIs/phases.

## 14. JPMS: module ownership of dynamically generated classes

When using `ClassLoader.defineClass` with a loader on the ordinary classpath, the defined class typically belongs to the **unnamed module** associated with the defining loader. Naming a JAR or embedding `module-info.class` at a URL does not automatically turn the class into a named module with validly resolved `requires`/`exports`.

To build a named-module plugin ecosystem, look at:

- `ModuleFinder` to locate modular artifacts;
- `Configuration.resolve(...)` to resolve the module graph;
- `ModuleLayer.defineModulesWithOneLoader(...)` or corresponding APIs to set up the layer/loader;
- `uses`, `provides`, `requires`, `exports`, `opens` of module descriptors;
- package uniqueness/visibility and loader ownership within the layer.

`MethodHandles.Lookup.defineClass` derives its loader/package/module scope from the lookup class; it is not an API to “arbitrarily inject classes into any named module”. Do not use reflective access to try bypassing module boundaries haphazardly; module openness and lookup privileges must be properly granted.

### Do not confuse `module-info.class` with a normal Java class

A class file carrying `ACC_MODULE` has the special structure of a module descriptor under JVMS `4`. It is not a Java class to be instantiated with `new` or `ClassLoader.defineClass("module-info", bytes,...)` like a typical plugin implementation. Module resolution is a separate mechanism.

## 15. Protecting the `java.*` package and sensitive namespace names

The `ClassLoader.defineClass` Javadoc specifies a restriction on names starting with `"java."`. An ordinary custom application loader is not allowed to call `defineClass("java.lang.MyString", ...)` to spoof the platform namespace: the system can throw **`SecurityException`**.

Similarly, once a class is already in a package with a given set of **signer certificates**, defining a new class with different certificates can cause a `SecurityException`. This rule prevents arbitrarily mixing bytes with different signing states in the same package of a defining loader.

**These constraints are not “suggestions” for a transformer**. When building a code generation library, make sure to:

- choose a legal namespace owned by the application;
- do not generate classes in the `java.*` package;
- maintain CodeSource/ProtectionDomain consistency when needed;
- check package sealing when using `URLClassLoader`/JAR manifests;
- avoid defining additional classes in a package managed by a signed/sealed dependency unless you truly understand the consequences.

## 16. ProtectionDomain and CodeSource: speaking accurately about permissions

The `defineClass(name, bytes, off, len, ProtectionDomain)` overload lets the caller explicitly specify a **protection domain**. A `ProtectionDomain` can be associated with a `CodeSource`, certificates, and legacy security policy components.

On JDK 17, the **Security Manager** is deprecated for removal, and choosing a domain should not be treated as a complete sandbox for untrusted code. Class loader/module visibility boundaries are distinct from **file/network/process access permissions**.

Example snippet explicitly specifying the bytecode source:

```java
CodeSource source = new CodeSource(
        new URL("file:/plugins/example.jar"),
        (java.security.cert.Certificate[]) null);

ProtectionDomain domain = new ProtectionDomain(source, null);
Class<?> type = defineClass(name, bytes, 0, bytes.length, domain);
```

This is a **snippet inside a `ClassLoader` subclass**; it requires imports for `java.net.URL`, `java.security.CodeSource`, and `java.security.ProtectionDomain`, plus the variables `name` and `bytes`; it is not a standalone Java program. In practice, protection domains/permissions/certificates must be configured properly for the runtime. Do not copy this snippet assuming all permissions are disabled or that it is already safe against malicious bytecode.

**If the input is untrusted**, consider isolation at the **process/container** level along with controls over bytecode provenance, signatures/allowlists, API/IO permissions, and resource quotas; `defineClass` only defines a JVM type and does not provide complete isolation.

## 17. Package signing and sealing: two distinct mechanisms

**Signer certificate consistency:**

- When a defining loader defines a class in a package, its signer certificates can impose a consistency constraint on other classes in that package.
- If subsequent bytes/class definitions use a different certificate set, `defineClass` may throw `SecurityException`.
- `ProtectionDomain.getCodeSource()` can provide the code source/certificates under appropriate conditions.

**Package sealing:**

- A JAR manifest can declare a package `Sealed: true`; a sealed package is bound to a code source according to the loader's rules.
- `URLClassLoader` and package metadata support sealing checks when defining a package.
- Calling `ClassLoader.defineClass` directly in a custom loader does not mean the system automatically applies the exact sealing policy of `URLClassLoader` if the loader does not manage `definePackage`, code source, and JAR origins the way URLClassLoader does.
- Do not assume “having the same package name means arbitrary JARs can be combined,” especially for signed/sealed packages.

These signing/sealing constraints are **consistency and integrity mechanisms**, not proof that a class file can run or has business-level authorization.

## 18. Superclass/interface relationships and loading constraints

A class that is successfully defined may still be unusable if its **superclass/interfaces** or symbolic references violate JVM rules.

Example scenario:

```text
Host loader defines api.Message → runtime type M1
Plugin loader defines api.Message → runtime type M2

HostInterface.accept(api.Message) expects M1
Plugin implementation uses M2

JVM method descriptors can lead to
loader constraint violation / LinkageError
```

You cannot “force” type M2 into M1 merely by changing package/class names in source or via reflection. You must ensure shared API types are delegated to **a single common defining loader**, or use serialization/protocol DTOs across the boundary.

Some other constraints:

- A class must not extend a `final class`.
- A class cannot directly implement a non-interface type.
- Superclass/interface references must be accessible and conform to JVM inheritance constraints.
- Sealed types restrict permitted direct subclasses/implementations; checks can lead to `IncompatibleClassChangeError` if the dynamic class violates the hierarchy.
- Bytecode referencing a method/field with a descriptor that differs from the runtime API can lead to `NoSuchMethodError` / `NoSuchFieldError`.

**Do not claim all errors occur immediately at `defineClass`:** some checks happen during loading/linking, while others are deferred by the JVM until references are first resolved/invoked.

## 19. Sealed classes, records, and nestmates in Java 17+

### Sealed classes

Java 17 supports `sealed` and `permits`. The class-file bytecode stores the list of permitted subclasses in the `PermittedSubclasses` attribute. A dynamic class **cannot arbitrarily `extends` a sealed superclass** simply by using the matching name in source. The JVM must verify matching permitted direct subclasses, module/package constraints, and type identity.

A `sealed` superclass defined by a parent loader does not necessarily allow a child loader to define a direct subclass from what looks like the same package. Check both the sealed hierarchy constraints and defining loaders; do not rely on type names or manually copied attributes.

### Records

`record` generates its own methods/fields/construction contract along with the `Record` attribute. If transforming a record's bytecode, you must preserve the `java.lang.Record` superclass, component metadata, canonical constructor semantics, and verifier rules. A class file with an arbitrary attribute does not automatically become a valid record.

### Nests and private access

`NestHost` / `NestMembers` attributes denote **nestmates**, enabling certain private accesses among classes in the same nest. The JVM validates these constraints; you cannot inject forged attributes to grant private access from an arbitrary loader. `Lookup.defineHiddenClass(..., NESTMATE)` is an access-controlled API; it is not equivalent to attaching an arbitrary binary name to a nest.

## 20. Successful class definition does not guarantee constructor/method execution succeeds

Reviewing the phases:

```text
read/generate bytes
        │
        ▼
defineClass(name, bytes, ...)
        │
        ├─ class-file format + identity checks
        ▼
Class<?> type
        │
        ├─ resolveClass(type) / JVM linking
        │     └─ may detect verifier/loader errors
        │
        ├─ getDeclaredConstructor(), getMethod()
        │     └─ reflection metadata/access checks
        │
        ├─ newInstance / static method active use
        │     └─ JVM class initialization; <clinit> may fail
        │
        └─ invoke/field access
              └─ method/field resolution and access checks
```

**Some steps may be performed earlier by the JVM** than shown in the diagram, but observable errors conform to the program points requiring the reference per the specification.

Do not assume `getDeclaredConstructor()` has executed the constructor. It is `Constructor.newInstance()` that creates the object and runs the constructor body. When the constructor body throws an exception, the reflective call usually wraps it in `InvocationTargetException`; whereas `ClassFormatError` or `IllegalAccessError` are different errors, not necessarily thrown by the constructor body.

### Static initialization errors

If `<clinit>` throws an exception, the first active use may receive `ExceptionInInitializerError`, and subsequent attempts using **the same runtime class** may receive `NoClassDefFoundError` because the class is erroneous. Calling `loadClass` again does not automatically reset initialization state. If you genuinely need to define a different class version, you typically need a new loader instance and an appropriate lifecycle.

## 21. Duplicate definitions and concurrency safety when generating classes

A custom loader cannot define the same binary name twice in the same defining loader. If two threads concurrently execute:

```java
byte[] bytes = /* class-file bytes of generated.Task */;
defineClass("generated.Task", bytes, 0, bytes.length);
```

This is an **illustrative snippet** inside a subclass, not standalone Java code. Without proper coordination, one of the define calls can fail with a duplicate-definition `LinkageError`.

Using the default `ClassLoader.loadClass` provides protection through `getClassLoadingLock(name)` and `findLoadedClass(name)`. If you override `loadClass` for child-first loading, you must handle the loaded cache and synchronization accurately.

### Need to create multiple versions with the same name?

You cannot “overwrite the old Class<?>” using `defineClass` in **the same loader instance**. Instead:

- Create a **new defining loader** for the new generation of the plugin.
- Keep the shared API in the parent stable so casts/contracts hold.
- Shut down the old activity, unregister callbacks, clean up threads/`ThreadLocal` entries, and close resources.
- Drop strong references to old provider instances/`Class<?>`/loader when you want the JVM to have a chance to unload them.
- Do not expect `URLClassLoader.close()` or GC to happen instantaneously or to rewrite an already defined class.

If you need to replace code within the same JVM without changing the loader, there are instrumentation/redefinition mechanisms with strict limitations; do **not** assume they can arbitrarily modify hierarchies, fields, and method signatures.

## 22. Error table — categorized by timing and cause

| Error | Typical scenario | Diagnostic hint |
| --- | --- | --- |
| `ClassNotFoundException` | Loader cannot find bytes for the binary name | Check lookup path, parent, JAR/classpath |
| `NoClassDefFoundError` | Passed `name` does not match `this_class`, or dependency/class init failed | Distinguish wrong name from erroneous class/missing dependency |
| `ClassFormatError` | Bytes do not conform to `ClassFile` format | Check magic, pool, attributes, generator |
| `UnsupportedClassVersionError` | Major/minor version is not supported by the JVM | `javap -verbose`, `java -version`, `javac --release` |
| `VerifyError` | Bytecode violates verification/type-flow constraints | Check stack, locals, `StackMapTable`, generator |
| `ClassCircularityError` | Hierarchy has an invalid cycle | Check superclass/interface references |
| `LinkageError` duplicate class | Defining the same name/loader a second time | `findLoadedClass`, synchronization, loader identity |
| `SecurityException` | Defining `java.*` with wrong loader, inconsistent package signing/certificates | Binary name, `ProtectionDomain`, signer set |
| `IllegalAccessError` | Incompatible runtime class/member access or package/module restrictions | Defining loaders, runtime package, JPMS |
| `IncompatibleClassChangeError` | Mismatch in class/interface/final/sealed/inheritance/linkage contract | Compare binaries, hierarchy, class file version |
| `NoSuchMethodError` / `NoSuchFieldError` | Caller bytecode references do not match the runtime library | Method descriptors, classpath order, version skew |
| `ClassCastException` | Two runtime types share the same name but have different defining loaders | `getClassLoader()`, `isAssignableFrom` |
| `ExceptionInInitializerError` | Static initializer threw an exception | Cause/stacktrace from the first active use |
| `IllegalAccessException` | Reflection or Lookup lacks access permission | Caller, lookup modes, JPMS exports/opens |
| `InaccessibleObjectException` | Deep reflection denied by module encapsulation | `opens`, target module and caller module |

Some errors can appear across multiple phases and take JVM-dependent forms; the table describes **common causes**, without promising that “each error occurs only on a fixed line”.

## 23. Diagnosing the right bytecode, loader, and runtime

### Class-file inspection tools

```sh
javap -verbose -classpath generated-out demo.generated.DynamicHello
javap -c -p -classpath generated-out demo.generated.DynamicHello
java -version
```

Inspect `major version`, `this_class`, superclass/interfaces, method descriptors, and attributes. If you have a Java 21 class while the deployment target is Java 17, the build must use `--release 17` or run on a newer runtime compatible with that artifact — **do not just edit the header bytes**.

### Observing the runtime defining loader

Valid snippet when placed in a class and called:

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
    System.out.println("package=" + type.getPackageName());
}
```

`getClassLoader() == null` typically represents the bootstrap loader. `type.getModule().getName() == null` typically indicates an unnamed module, not that the class does not belong to any module object.

### HotSpot Unified Logging

```sh
java -Xlog:class+load=info -cp host-out demo.DefineDemo
java -Xlog:help
```

Class loading logs help reveal the bytecode source at runtime, though many lines depend on the implementation; there is no fixed standard stdout for JVM logs. `-Xlog` does not prove that a class has been initialized or that its constructor has run. To inspect `<clinit>`, observe program behavior or log class initialization if the JDK/runtime supports it.

### When errors occur after defineClass

Print the **exception type**, **cause chain**, **target binary name**, **defining loader identity**, **module/package**, and **class-file version**. Do not log the full bytes or paths containing secrets to public logs. With multiple plugins, include a plugin ID/generation to distinguish two loaders that share the same class name.

## 24. A safer workflow for releasing dynamic classes

1. **Choose the namespace and contract:** which public API and package does the new class need? Which types must be shared between the host and plugin?
2. **Decide between defining loader or Lookup:** choose `ClassLoader.defineClass` for a separate namespace or `Lookup.defineClass` when exact same-package/same-loader privileges are needed.
3. **Lock down the Java target runtime:** use `javac --release 17` if production runs Java 17; check the major/minor version at build time.
4. **Generate/read valid bytes:** use a compiler/bytecode generator that supports the relevant class-file version, stack maps, and attributes; do not edit bytes arbitrarily.
5. **Match the binary name:** `defineClass(name, bytes,...)` must use a name matching `this_class`.
6. **Check structural constraints:** superclass, interfaces, final/sealed/record attributes, nest metadata.
7. **Check runtime access:** runtime package + defining loader, module readability/exports/opens, package-private/nestmate rules.
8. **Check security metadata:** package signer consistency, code source/protection domain, sealing if the loader applies it.
9. **Synchronize:** avoid duplicate definitions and use loader locking if multiple threads create a class with the same name.
10. **Validate in the application:** resolve, instantiate/invoke in tests, check for missing dependencies, binary signatures, and static initializer errors.
11. **Close out the lifecycle:** use a new loader for a different generation, and manage references and callbacks on hot-reload.
12. **Protect the environment:** if bytes come from an untrusted third party, use independent isolation/security controls; a class loader is not a sandbox.

### What should be tested automatically

- A version higher than the runtime target is rejected with the proper error type.
- Corrupt class-file bytes are rejected.
- A name passed to `defineClass` that does not match `this_class` reports a wrong-name error.
- Duplicate classes in the same loader cannot be redefined.
- Same Java package text with different defining loaders does not automatically grant package-private access.
- Shared API type identity holds when a provider/plugin is loaded.
- The new class in its module/package has permission to access the APIs it needs.
- No static constructor side effects occur before active use if the design does not require them.
- Two generations of a plugin have proper lifecycle/reference cleanup without unnecessarily retaining the old classloader.

## 25. Common misconceptions

- **“`defineClass` is `new`.”** False: it creates a runtime `Class<?>`, not an instance.
- **“All you need is a byte array starting with CAFEBABE.”** False: format, pool, descriptors, attributes, and verification must all be valid.
- **“You can run a Java 21 class on a Java 17 JVM by changing major 65 to 61.”** False: instructions/APIs/attributes may be incompatible.
- **“The `name` of `defineClass` is only for logging.”** False: the API matches the binary name against the bytes and enforces namespace constraints.
- **“Two classes with the same `package shared` always access each other's package-private members.”** False: the runtime package also includes the defining loader.
- **“`Lookup.defineClass` can inject a class into any loader/module.”** False: permissions are constrained by the lookup class and PACKAGE mode.
- **“`setAccessible(true)` fixes any `IllegalAccessError`.”** False: runtime bytecode linking checks and module restrictions are a different matter.
- **“`ClassFormatError` and `VerifyError` are both `ClassNotFoundException`.”** False: they are distinct JVM errors.
- **“Successful class definition means all method references are resolved.”** Not necessarily; some resolution can be lazy.
- **“Once the class is loaded, the constructor definitely runs.”** False: class initialization and object creation are later steps.
- **“You can redefine the same class name in the same loader when updating a JAR.”** No; you need a new loader or a specialized redefinition mechanism with limitations.
- **“ProtectionDomain makes a plugin sandbox absolute.”** False; it does not replace process isolation and a security model.
- **“A JAR containing `module-info.class` automatically becomes a named module when read by URLClassLoader.”** No; JPMS resolution/layers are a different mechanism.
- **“`IllegalAccessError` always appears immediately at `defineClass`.”** The timing is not guaranteed if symbolic references are resolved later.

## 26. Self-check questions

**1. What does `defineClass` return and what has it not done yet?** It returns the `Class<?>` of the new runtime type; it does not automatically return an instance and does not necessarily run the class initializer.

**2. With `--release 17`, what is the class-file major version?** 61.

**3. Can a class with major 65 run on Java 17?** No; the version exceeds what is supported, typically reporting `UnsupportedClassVersionError`.

**4. Why does `defineClass("a.Other", bytes of a.Widget)` fail?** Because the binary name does not match `this_class`; it may throw `NoClassDefFoundError`.

**5. Is the magic CAFEBABE enough to confirm a valid class?** No. Valid structure/constant-pool/method/attribute/bytecode verification is required.

**6. Which family does `UnsupportedClassVersionError` belong to?** It extends `ClassFormatError`, which belongs to `LinkageError`.

**7. Does the same `package shared` in source allow package-private access between two different defining loaders?** No; the runtime package depends on the defining loader.

**8. Why does `Lookup.defineClass` only use bytes in the same package as the lookup class?** Because the API verifies PACKAGE lookup privileges and places the class in the same runtime package/loader.

**9. Does `defineClass` automatically run `<clinit>`?** Not by default; class initialization is required upon appropriate active use.

**10. How does parent-first help when a plugin uses a host API?** It ensures the provider/host use the same `Class<?>` for interfaces/DTOs defined by the parent.

**11. Can two versions with the same class name exist in one JVM?** Yes, if they have different defining loaders; the same binary name cannot be defined twice in the same defining loader.

**12. How does `IllegalAccessError` differ from `IllegalAccessException`?** `IllegalAccessError` is typically a linking/runtime access error, whereas `IllegalAccessException` is a checked exception from the reflection/Lookup API.

**13. Can `ClassLoader.defineClass` inject a class into any named module?** No; loader/module/Lookup access and JPMS restrictions still apply.

**14. Why does `NoClassDefFoundError` not necessarily mean the `.class` file is missing?** It can be caused by a wrong binary name, a resolution error, or a class that previously failed initialization.

**15. What is a safe way to update an implementation class already defined in a plugin loader?** Create a new plugin class loader/generation, use shared API identity, and manage the old lifecycle; do not call define redundantly.

## 27. Official references

- [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `defineClass` overloads, `findClass`, parent delegation, name/package/certificate checks, ProtectionDomain, and linking errors.
- [Java SE 17 `MethodHandles.Lookup` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineClass`/`defineHiddenClass`, lookup modes, same-package/loader restrictions.
- [JVMS Java SE 17 — Chapter 4, The class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): version numbers, `ClassFile` layout, verification, `Record`, and `PermittedSubclasses` attributes.
- [JVMS Java SE 17 — Chapter 5, Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): runtime identity, class loader constraints, access/linking/initialization.
- [JLS Java SE 17 — Chapter 6, Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html): binary names, packages, and access rules.
- [Java SE 17 `ProtectionDomain` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html): protection domains and code source.
- [JDK 17 `javap` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspecting major version, pool, and bytecode.

**Conclusion:** When creating classes dynamically, the JVM does not simply “run bytecode as soon as it can read it.” The class file must have a **valid version and structure**, binary name/loader identity must be consistent, superclass/interfaces/attributes must satisfy linking rules, and all accesses remain subject to **runtime package, JPMS, and ProtectionDomain**. Use `ClassLoader.defineClass` or `Lookup.defineClass` properly, and verify class-file bytes and runtime access at each step rather than treating every failure as a generic classpath error.
