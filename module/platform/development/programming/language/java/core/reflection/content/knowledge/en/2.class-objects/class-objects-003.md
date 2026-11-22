# Class.forName with Binary Names in Java Reflection

## 1. Objectives and context

In Java Reflection, **`Class.forName(String name)`** looks up a class or interface by name at runtime and returns the `Class<?>` object representing that type. The crucial point is that the string passed in must follow the **binary name** of an ordinary class/interface; the name you write in Java code sometimes differs from this name. Arrays in particular have a special representation syntax, while primitives cannot be looked up with `Class.forName("int")`.

After this lesson, you can distinguish simple names, canonical names, and binary names; accurately look up top-level classes, member classes, and arrays; explain the loading/initialization process; choose the appropriate overload/class loader; and handle typical lookup errors.

## 2. How does a binary name differ from a canonical name?

A **binary name** is the name used to identify a class/interface in Java's binary representation, as specified in JLS §13.1. For a top-level class, the name is typically the package name plus the class name, such as `java.lang.String`. For a **member class or interface** nested inside another type, the binary name uses **`$`** between nesting levels, such as `java.util.Map$Entry`, whereas Java source writes `java.util.Map.Entry`.

| Type | Name in Java source / canonical name | Name suitable for `Class.forName` |
| --- | --- | --- |
| Top-level class | `java.lang.String` | `java.lang.String` |
| Top-level interface | `java.util.List` | `java.util.List` |
| Member interface | `java.util.Map.Entry` | `java.util.Map$Entry` |
| Nested member class | `com.example.Outer.Inner` | `com.example.Outer$Inner` |
| Multi-level nesting | `com.example.Outer.Middle.Inner` | `com.example.Outer$Middle$Inner` |
| Array `String[]` | `java.lang.String[]` | `[Ljava.lang.String;` |
| Array `String[][]` | `java.lang.String[][]` | `[[Ljava.lang.String;` |
| Array `int[]` | `int[]` | `[I` |
| Primitive `int` | `int` | Use `int.class`, do not use `Class.forName("int")` |

Three APIs for getting names from a `Class` object:

- `getSimpleName()`: the short name, such as `Inner`; does not carry enough package/outer class information.
- `getCanonicalName()`: the name in source syntax, such as `com.example.Outer.Inner`. Local classes and anonymous classes usually have no canonical name, so this can return `null`.
- `getName()`: for ordinary classes/interfaces, returns the binary name, such as `com.example.Outer$Inner`; for arrays, returns the special form like `[Ljava.lang.String;`; for primitives, returns `int`, `boolean`, etc.

**Practical rule:** When you already have `SomeType.class`, take `SomeType.class.getName()` to produce the string for class/interface and array types instead of manually converting dots to `$`. The exceptions are primitives or `void`, because their `getName()` strings cannot be used to load them back via `Class.forName`.

## 3. Exact syntax by type kind

### 3.1. Top-level classes and interfaces

```java
Class<?> stringType = Class.forName("java.lang.String");
Class<?> listType = Class.forName("java.util.List");
```

The string is the fully qualified name including the package. Unlike how the compiler resolves `String` in source code, `Class.forName("String")` does not automatically prepend the `java.lang` package. It attempts to find a class with the exact name passed.

### 3.2. Member classes and member interfaces

```java
Class<?> entry = Class.forName("java.util.Map$Entry");
Class<?> nested = Class.forName("com.example.Outer$Inner");
```

The second line only succeeds when the class `com.example.Outer$Inner` actually exists and is visible to the loader. This example illustrates the syntax and does not assume the project contains that class. In `com.example.Outer$Inner`, dots separate the package and the top-level type; `$` separates the outer and inner types. Do not replace all dots with `$`.

The naming rule above also applies to **non-static inner classes**. However, looking up the `Class` does not mean you can create an instance of an inner class using a no-argument constructor: an inner class constructor typically requires an implicit reference to the outer object.

### 3.3. Array types using descriptor-style names

For arrays, the string accepted by `Class.forName` consists of one `[` character per dimension and the code for the component type:

- For a class/interface component: `L` + binary name + `;`, for example `[Ljava.lang.String;`.
- For primitives: use codes `Z` = boolean, `B` = byte, `C` = char, `D` = double, `F` = float, `I` = int, `J` = long, `S` = short.
- For two-dimensional arrays, add another `[`: `[[I` for `int[][]`, `[[Ljava.lang.String;` for `String[][]`.

```java
Class<?> strings = Class.forName("[Ljava.lang.String;");
Class<?> ints = Class.forName("[I");
Class<?> matrix = Class.forName("[[I");
Class<?> entries = Class.forName("[Ljava.util.Map$Entry;");
```

Do not use `"java.lang.String[]"` or `"int[]"` with the name-taking overload. These are **array type names**, not binary names of top-level classes; the most reliable way to get the name is `String[].class.getName()` or `int[].class.getName()`. Loading an array class does not automatically initialize the array's element class.

### 3.4. Primitives, generics, local, and anonymous classes

`Class.forName("int")` and `Class.forName("void")` are not ways to get the `Class` object of primitives/void; use `int.class`, `void.class`, `Integer.TYPE`. Also do not pass generic syntax `"java.util.List<java.lang.String>"`: generic type arguments are not part of the binary name of the raw class `java.util.List`.

Names of local or anonymous classes can include compiler-generated sequence numbers, such as `Outer$1Local` and `Outer$1`. These names can change when code is edited or recompiled. Do not hardcode them into configuration; if reflection is needed on such classes, prefer `instance.getClass()` and use the existing `Class`.

## 4. Java 17+ program demonstrating binary names

Create the file **`BinaryNameDemo.java`** with the complete contents:

```java
public class BinaryNameDemo {
    static class Nested {}

    private static void show(String label, Class<?> type) {
        System.out.println(label + ": " + type.getName());
    }

    public static void main(String[] args) throws ClassNotFoundException {
        show("Top-level", Class.forName("java.lang.String"));
        show("Member", Class.forName("java.util.Map$Entry"));
        show("Nested", Class.forName("BinaryNameDemo$Nested"));
        show("Object array", Class.forName("[Ljava.lang.String;"));
        show("Primitive array", Class.forName("[I"));

        System.out.println("Canonical: " + Nested.class.getCanonicalName());

        try {
            Class.forName("BinaryNameDemo.Nested");
        } catch (ClassNotFoundException exception) {
            System.out.println("Canonical lookup: ClassNotFoundException");
        }

        try {
            Class.forName("int");
        } catch (ClassNotFoundException exception) {
            System.out.println("Primitive lookup: ClassNotFoundException");
        }
    }
}
```

In the directory containing the file, run:

```bash
javac BinaryNameDemo.java
java BinaryNameDemo
```

**Output:**

```text
Top-level: java.lang.String
Member: java.util.Map$Entry
Nested: BinaryNameDemo$Nested
Object array: [Ljava.lang.String;
Primitive array: [I
Canonical: BinaryNameDemo.Nested
Canonical lookup: ClassNotFoundException
Primitive lookup: ClassNotFoundException
```

Here `BinaryNameDemo.Nested` is the canonical name useful in Java source, whereas `BinaryNameDemo$Nested` is the binary name for looking up the class. Because the program declares no package, the leading part of the binary name is just `BinaryNameDemo`. If the file were in `package demo;`, the lookup string would be `demo.BinaryNameDemo$Nested`.

The example also illustrates that `Class.forName` **does not automatically convert** the source array name `String[]` into JVM form and **does not automatically convert** the string `int` into a primitive `Class`.

## 5. Loading types by name and initialization timing

`Class.forName(String)` looks up by name and **requests initialization** of the target class when needed. `Class.forName(name, false, loader)` still loads/links the class but **does not actively initialize** it; a regular `ClassLoader.loadClass(name)` also does not request initialization yet. These operations are distinct from calling a constructor to create an instance.

| Call | Notable result |
| --- | --- |
| `Class.forName("demo.Widget")` | Looks up by name and requests running static initialization of `Widget` if it has not happened yet. |
| `Class.forName("demo.Widget", false, loader)` | Retrieves metadata to inspect the type before actively using it. |
| `Class.forName("[Ldemo.Widget;")` | Looks up the array type; does not thereby initialize the element class `Widget`. |

A valid name can still fail to be found if the loader cannot see the definition. A found class can also fail during linking or initialization. The lesson on the three-argument overload goes deeper into choosing the loader and the `initialize` flag; the lesson on class lifecycle analyzes separately the moments when the JVM runs `static` initialization.

## 6. Finding `Class` does not mean you have an object

`Class.forName` only returns type metadata; it does not create an instance automatically. When you want to instantiate an object via reflection, you must locate the appropriate constructor:

```java
Class<?> type = Class.forName("java.util.ArrayList");
Object instance = type.getDeclaredConstructor().newInstance();
System.out.println(instance.getClass().getName());
```

This is a **fragment** placed inside a method that handles/declares `ReflectiveOperationException`; the output is `java.util.ArrayList`. `ArrayList` has a no-argument constructor; not every class does. A constructor might not be public or might have access restricted by the module system; `getDeclaredConstructor().newInstance()` is not guaranteed to succeed for every newly loaded type.

For types known at compile time, `SomeType.class` is usually shorter and more type-safe; `Class.forName` fits when the type name comes from configuration or a plugin, framework, or dynamic programming mechanism.

## 7. Error diagnosis

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `ClassNotFoundException` with `java.util.Map.Entry` | Confusing canonical name with binary name | Use `java.util.Map$Entry`. |
| `ClassNotFoundException` with `String` | Missing package name | Use `java.lang.String`. |
| `ClassNotFoundException` with `java.lang.String[]` | Confusing source array syntax | Use `[Ljava.lang.String;` or `String[].class`. |
| `ClassNotFoundException` with `int` | Primitives are not looked up as classes by a loader | Use `int.class`. |
| Correct name still not found | Wrong classpath, module path, or class loader | Check runtime dependencies and loader. |
| `ExceptionInInitializerError` | Static initialization failed | Inspect the root cause in the static initializer. |
| `NoClassDefFoundError` | Class/dependency needed during linking or usage is missing, or the class previously failed initialization | Check the first error in logs and the cause chain. |
| Other `LinkageError` | Verification/linking error or incompatible bytecode | Check dependencies and library versions. |

`ClassNotFoundException` is a **checked exception**, usually related to looking up a class by name. `ExceptionInInitializerError` and `NoClassDefFoundError` are **Errors**, which are not handled merely by `catch (ClassNotFoundException)`. Avoid catching `Error` broadly to hide deployment/environment failures.

## 8. Safe application with dynamic class names

When reading class names from configuration, store the exact binary name if possible—for example, using `Plugin.class.getName()` where the data is produced. Do not blindly replace every `.` with `$`, because dots in package names must be preserved. If a dedicated class loader is needed (plugins or application servers), use the three-argument overload and retain the plugin's proper loader.

Loading and initializing a class can execute code in static initializers. If the name comes from external data, restrict allowed classes, verify the expected superclass/interface, and only instantiate according to an explicit contract. For example, once `binaryName` has been verified as permitted:

```java
Class<?> loaded = Class.forName(binaryName, false, pluginClassLoader);
if (!Runnable.class.isAssignableFrom(loaded)) {
    throw new IllegalArgumentException("Expected Runnable");
}
Class<? extends Runnable> taskType = loaded.asSubclass(Runnable.class);
```

This is a **fragment** using two existing variables `String binaryName` and `ClassLoader pluginClassLoader`; it only checks the subtype and has not yet created an instance. Even though `initialize=false` was used, subsequent operations on the class can cause the JVM to initialize it. Checking only the subtype does not replace an allowlist of permitted classes and evaluating the trustworthiness of the source.

## 9. Self-check questions

1. Source has `package demo;` and `Outer` contains `static class Inner`. What string looks up the inner type? **`"demo.Outer$Inner"`**, not `"demo.Outer.Inner"`.
2. To look up `String[][]`, which name is used? **`"[[Ljava.lang.String;"`**: two `[` characters for two dimensions, `Ljava.lang.String;` for the reference component type.
3. Why doesn't `Class.forName("int")` replace `int.class`? **Primitives are not classes defined by a loader under a binary name**.
4. To get `Class` without requesting the static initializer to run yet, what do you use? **`Class.forName(binaryName, false, loader)`**, while understanding that later operations can initialize the class.
5. Why can a valid name still fail lookup? **The runtime class loader or classpath/module path does not contain or cannot see the matching class**.

**Remember:** For ordinary classes/interfaces, use the **binary name**; for member types use `$`. For arrays, use names like `[L...;` or `[I`. For primitives, use class literals. Always distinguish lookup, initialization, and instantiation to properly understand how `Class.forName` behaves.