# Class object, array classes, and how the JVM creates runtime type representations

When a Java program runs, the JVM does not only manage **instances**. It also manages **types at runtime**: classes, interfaces, array types, primitive types, and the `void` type used in the reflection model. A `java.lang.Class<?>` object is **the Java-level entry point to the representation of a type recognized by the JVM**; meanwhile, an **array class** is a kind of class created by the JVM according to its own rules, without needing a `String[].class` file output by `javac`.

Three main points of this article:

1. **A `Class` object is different from an instance:** multiple instances of the same runtime class usually obtain the same `Class` object via `getClass()`; the `Class` object describes the **type**, not an instance of that type.
2. **Type identity is tied to the class loader:** two class definitions with the **same binary name** but defined by two different defining class loaders are **two different runtime types**. This explains loader and cast errors in plugin/container applications.
3. **The JVM creates array classes on demand:** for example, `int[].class`, `String[].class`, and `String[][].class` are valid `Class` objects even though no `class String[]` source code exists. An array object also retains its runtime component type so the JVM can check element stores.

The scope of this article is **class loading/identity and runtime type representation**, not the structure of the entire heap or GC algorithms. Examples run on **Java 17+**.

## 1. What does “Class object” mean?

In Java, `java.lang.Class<T>` is the library class representing the runtime information of a type. An object of this class is often called a **class object**, **Class mirror**, or simply a `Class` object.

```java
String first = new String("A");
String second = new String("B");

Class<?> mirror1 = first.getClass();
Class<?> mirror2 = second.getClass();
Class<String> literal = String.class;

System.out.println(mirror1 == mirror2); // true
System.out.println(mirror1 == literal); // true
System.out.println(first == second);    // false
```

This is a **Java snippet placed inside a method**, not a standalone source file. Two `String` instances are created separately, but both have the same runtime class, so the two `getClass()` calls return the same `Class` object. `String.class` provides the corresponding class literal.

**Do not confuse the objects:**

```text
             String instance A                 String instance B
           ┌─────────────────┐               ┌─────────────────┐
first ───► │ content "A"     │   second ───► │ content "B"     │
           └─────────────────┘               └─────────────────┘
                    │                                  │
                    └───────── runtime class ──────────┘
                                     │
                                     ▼
                              Class<String>
                            mirror of String
```

The diagram shows **logical relationships**, not actual RAM layout. From a `Class` object, reflection can look up the name, superclass, interfaces, fields, methods, constructors, annotations, array component type, etc., but the `Class` object does not itself store all instance field values of each object.

### What are the ways to obtain a Class object?

| Way | Example | Meaning |
| --- | --- | --- |
| Class literal | `String.class` | Refers to a type at compile time |
| Primitive class literal | `int.class` | Obtains the Class mirror for a primitive type |
| Array class literal | `String[][].class` | Obtains the Class mirror for an array type |
| Runtime instance | `obj.getClass()` | The actual type of the **object**, not just the static type of the variable |
| Lookup by name | `Class.forName("java.lang.String")` | Finds/loads a type by binary name via the appropriate loader, with the overload's initialization rules |
| Reflection array creation | `Array.newInstance(component, 3).getClass()` | The JVM creates an array object/array Class according to the runtime component type |

`obj.getClass()` requires `obj != null`; calling it on `null` causes a `NullPointerException`. Conversely, `String.class` does not require creating a `String` instance.

**`Class<?>` is not `Class<Object>`:** the `?` is a wildcard, appropriate when the program only wants to describe a runtime type without knowing the specific `T` parameter. `Class<String>` describes the `String` type, but it does not mean a `Class<String>` is a **String instance**.

## 2. Runtime class differs from the static declared type of a variable

```java
Object value = "hello";
System.out.println(value.getClass() == String.class); // true
```

The variable `value` has a **declared/static type** of `Object`, but the referenced object belongs to the **runtime class** `String`. `value.getClass()` reflects the actual existing object, not the `Object` keyword in the declaration.

This is directly related to:

- **Dynamic dispatch** of overridable instance methods.
- **`instanceof` and reference casts** being decided from the runtime type along with appropriate subtype relationships.
- **Reflection**: `getDeclaredMethods()` returns methods declared on the described class; `getMethods()` includes public methods according to API rules.
- **Serialization/framework mapping**: may need to know the runtime class to read metadata and create/transform data.

A Class object and **internal class metadata** are not completely the same API concept. The JVM can store class structures in its own implementation-specific way and provide `java.lang.Class` as an observable mirror from Java. Do not infer from `Class<?> c` that all class-file bytes or metadata must reside inside object `c` in a fixed layout.

## 3. Runtime type identity: binary name + defining class loader

A class or interface is not identified solely by its name string.

According to the JVM model, **the identity of a class/interface is determined by the pair (binary name, defining class loader)**. Definitions with the same name but defined by different loaders produce **non-identical** runtime classes. Therefore:

```text
(name = "example.Plugin", loader = Loader-A)  ──► Class A
(name = "example.Plugin", loader = Loader-B)  ──► Class B

A.getName().equals(B.getName())   → true
A == B                            → false
A.isAssignableFrom(B)             → false (if there is no subtype relationship)
```

The diagram assumes the two loaders actually **define** the class with the same name independently. If loader B **delegates to loader A/parent** and returns the same already-loaded definition, the class object will be the same. The **initiating loader** (the loader requested to start loading) and the **defining loader** (the loader that actually defines the class) are not necessarily the same; the two roles must be distinguished.

### 3.1. Parent delegation and class loader namespaces

The common way of loading classes uses parent delegation: a loader tries delegating to its parent before looking for a definition itself. This mechanism helps multiple pieces of code share foundational classes. However, custom class loaders can use their own strategies permitted by the JVM, so one should not say “every class with the same name in a JVM is automatically the same class”.

When two libraries/plugins are loaded by different loaders:

- You may see a confusing message like `X cannot be cast to X`: the displayed name is the same, but the **runtime identity is different**.
- One class may use the static fields of definition A, while the other uses the static fields of definition B.
- A reference whose runtime class belongs to loader A is not automatically compatible with the class of the same name belonging to loader B.
- The corresponding array types `X[]` are also different when component `X` has a different runtime type.

**Important:** class loaders determine namespaces and load definitions; they do not make every cast fail. If two parts of code use the **same `Class` object** via delegation, identity and casts according to type relationships still work normally.

### 3.2. `getClassLoader()` and bootstrap classes

`SomeClass.class.getClassLoader()` returns the defining loader from the Java reflection perspective. For types defined by the **bootstrap loader**, the API usually returns **`null`**; there are also cases like primitives/void and primitive arrays that do not have a normal `ClassLoader` object as a defining loader. Therefore `null` **does not mean the class has not been loaded**.

An example that does not depend on addresses or implementation names:

```java
System.out.println(int.class.getClassLoader() == null);    // true
System.out.println(int[].class.getClassLoader() == null);  // true
```

Classes defined by the application loader usually have `getClassLoader() != null`, but do not hard-code the loader's implementation class name because different JDKs/runtimes may organize them differently.

## 4. Primitives, `void`, and reference types all have a Class mirror

The `Class` API includes types that cannot have their own object instances like `String`:

| Expression | What it represents | Notes |
| --- | --- | --- |
| `int.class` | Primitive type `int` | `int.class == Integer.TYPE` |
| `boolean.class` | Primitive type `boolean` | Not equivalent to `Boolean.class` |
| `void.class` | The `void` type in reflection | `void.class == Void.TYPE`; cannot do `new void` |
| `String.class` | Runtime class `String` | Reference type |
| `java.util.List.class` | Runtime interface `List` | Not a specific `List` object |
| `int[].class` | Array class of `int[]` | Reference type even though the element type is primitive |
| `String[][].class` | Two-dimensional array class | Component type is `String[]` |

`Class.isPrimitive()` is used to query primitive-like Class objects according to the Java API (including the `void.class` case), but **`void` is not a normal variable type holding a value** in Java source. For wrapper types, `Integer.class.isPrimitive()` is `false`.

For generic code, distinguish:

```java
Class<?> primitive = int.class;
Class<?> wrapper = Integer.class;
System.out.println(primitive == wrapper); // false
```

Autoboxing/unboxing between `int` and `Integer` is a language conversion; it does **not** make the two types share a Class mirror.

## 5. How does the JVM create array classes differently from regular classes?

### 5.1. An array class is a real runtime type

Each array type has its own runtime class:

```text
int[]           → Class mirror: int[].class
int[][]         → Class mirror: int[][].class
String[]        → Class mirror: String[].class
String[][]      → Class mirror: String[][].class
Plugin[]        → Class mirror corresponding to Plugin[] of the right defining loader
```

The JVM **does not require a ClassFile named `int[].class` or `java.lang.String[].class`**. The format and semantics of array classes are handled specially by the JVM. Array classes **are created by the JVM on demand**, rather than being loaded directly from a ClassFile declaring the array like a regular class.

For an **array of a reference type**, the defining loader of the array class is determined from the defining loader of the component/reference type. For primitive arrays, there is no user-supplied defining class loader. That is why two `Plugin` classes with the same binary name but different loaders entail two different `Plugin[]` types.

### 5.2. `getComponentType()` and `isArray()`

```java
Class<?> t = String[][].class;
System.out.println(t.isArray());                                  // true
System.out.println(t.getComponentType() == String[].class);        // true
System.out.println(t.getComponentType().getComponentType()
        == String.class);                                         // true
```

This is an illustrative snippet inside a method; `getComponentType()` **removes exactly one dimension**. For `String[][]`, the direct component is **`String[]`**, not `String`. For `int[].class`, the component is `int.class`.

For a Class object that does not describe an array, `getComponentType()` returns **`null`**. `isArray()` returns `false` for primitives, `void`, regular classes, and interfaces.

### 5.3. Array superclass and implemented interfaces

Every array object in Java is a reference object. The JVM establishes the type relationships:

- The direct superclass of an array class is **`java.lang.Object`**.
- Array classes implement **`java.lang.Cloneable`** and **`java.io.Serializable`**.
- An array object has a fixed **`length`** and can be **cloned** to create a new array object.
- There is no `class MyArray extends String[]` source; Java programs cannot define subclasses of an array class.

These also apply to `int[]`: `int[]` is an object, even though the elements inside are `int`.

```java
System.out.println(int[].class.getSuperclass() == Object.class); // true
System.out.println(Cloneable.class.isAssignableFrom(int[].class)); // true
System.out.println(java.io.Serializable.class.isAssignableFrom(int[].class)); // true
```

Do not confuse `getSuperclass()` with `getInterfaces()`: an array class has superclass `Object` and two standard interfaces, rather than inheriting from `Object[]` in all cases. **`int[]` is not a subtype of `Object[]`**, though it is a subtype of `Object`.

### 5.4. Covariance and runtime checking

For reference element types, Java arrays are **covariant**:

```java
String[] texts = new String[1];
Object[] values = texts;        // valid
values[0] = "hello";           // valid
values[0] = new Object();      // ArrayStoreException at runtime
```

This is an illustrative snippet; the last line intentionally causes an exception. The **static** type of `values` is `Object[]`, but its runtime class is still **`String[].class`**. The `aastore` instruction checks whether the assigned value is compatible with the runtime component type. The array is still the same object; the assignment `values = texts` **does not convert the array into a new `Object[]`**.

Conversely, primitive arrays **are not covariant in that way**:

```java
Object object = new int[2]; // valid: int[] is an Object
// Object[] wrong = new int[2]; // compile error
```

Even when the array type is a valid subtype, **`aastore` checks at runtime** because the compiler may only know the variable is declared with a broader type.

## 6. Binary names and array class name notation in reflection

`Class.getName()` for a regular class usually returns the binary name, whereas for an array class it uses a notation similar to a **field descriptor**:

| Runtime type | `Class.getName()` | `Class.getTypeName()` |
| --- | --- | --- |
| `int` | `int` | `int` |
| `String` | `java.lang.String` | `java.lang.String` |
| `int[]` | `[I` | `int[]` |
| `long[][]` | `[[J` | `long[][]` |
| `String[]` | `[Ljava.lang.String;` | `java.lang.String[]` |
| `String[][]` | `[[Ljava.lang.String;` | `java.lang.String[][]` |

Decoding:

- Each **`[`** character represents one array dimension.
- `I` represents `int`, `J` represents `long`, `Z` represents `boolean`, `D` represents `double`.
- `L...;` represents a reference component type. In `Class.getName()`, the class name inside uses **`.`** (`java.lang.String`), not the `/` slash you might see in a ClassFile descriptor (`java/lang/String`).
- For a nested class, the component's binary name may contain **`$`**, for example `Outer$Inner`.

Note the two contexts: names from **`Class.getName()`** and **field descriptors stored in a ClassFile** are very similar for arrays, but **do not write reference class names identically**. Do not take the string `Ljava/lang/String;` and pass it straight to `Class.forName` without considering the naming rules.

### `Class.forName` with array names

```java
Class<?> ints = Class.forName("[I");
Class<?> texts = Class.forName("[Ljava.lang.String;");

System.out.println(ints == int[].class);        // true
System.out.println(texts == String[].class);    // true
```

This is a snippet inside a method that **`throws ClassNotFoundException`** or handles the exception. The name `java.lang.String[]` **is not** a valid binary notation for array lookup with the overload above; for the primitive source name `"int"`, `Class.forName("int")` also does not provide a primitive Class object. Use `int.class` or `Integer.TYPE` for primitives.

When using `Class.forName(String)`, the simple overload defaults to requiring initialization of a normal class when appropriate. There is an overload **`Class.forName(String name, boolean initialize, ClassLoader loader)`** to explicitly choose initialization. When the name specifies an **array class**, it does not force the component class to initialize just to create/look up the array Class object.

## 7. Instructions related to array creation

The compiler/JVM has dedicated instructions for array objects; it does not use `new` with a class file name `"int[]"` declared in Java.

| Instruction | Purpose | Java source example |
| --- | --- | --- |
| `newarray` | Creates a one-dimensional **primitive** array | `new int[3]`, `new byte[2]` |
| `anewarray` | Creates a one-dimensional **reference component** array | `new String[3]`, `new int[2][]` |
| `multianewarray` | Allocates the specified dimensions of a multidimensional array | `new int[2][3]` |
| `arraylength` | Gets the length of an array object from an array reference | `numbers.length` |
| `iaload`, `aaload` and load group | Reads an element according to array kind | `numbers[i]`, `names[i]` |
| `iastore`, `aastore` and store group | Writes an element; `aastore` checks runtime type when storing a reference | `numbers[i]=1`, `names[i]="x"` |

These are **typical bytecode patterns**, with no guarantee that every source expression always has a single corresponding instruction. The compiler may change the instruction structure while preserving semantics.

### 7.1. Multidimensional arrays are arrays of arrays

```java
int[][] a = new int[2][3];
int[][] b = new int[2][];

System.out.println(a.length);           // 2
System.out.println(a[0].length);        // 3
System.out.println(b.length);           // 2
System.out.println(b[0] == null);       // true
```

For `a`, the JVM creates the outer array and enough inner arrays for the two specified dimensions; for `b`, only the outer array is created and the component reference slots are initially `null`. Thus they **have the same runtime type `int[][]`**, but the graph of allocated array instances is different.

**Length is a property of the array instance**, not a fixed property of the array Class: `new int[2]` and `new int[7]` have the same `Class` object `int[].class`, but have lengths 2 and 7 respectively. Do not infer that the `Class` describing `int[2]` is a different runtime type from `int[7]`.

### 7.2. Data and errors at creation/access time

- `new int[-1]` causes **`NegativeArraySizeException`**.
- Array allocation can cause **`OutOfMemoryError`** if resources are insufficient.
- Reading `length` or reading/writing an element through a null array reference can cause **`NullPointerException`**.
- A negative index or `>= length` causes **`ArrayIndexOutOfBoundsException`** on access.
- Writing an object incompatible with the actual component type into a reference array can cause **`ArrayStoreException`**.
- Not every operation on `Object[]` is valid for `int[]`; the element type must match.

The errors above relate to **array instances** and runtime values. The bytecode verifier also checks constraints on instruction types, the operand stack, and class file validity; that is a different verification layer.

## 8. Runnable Java 17+ example: Class objects for classes, primitives, and arrays

Create **`ClassMirrorDemo.java`** in an empty directory:

```java
import java.io.Serializable;
import java.lang.reflect.Array;

public class ClassMirrorDemo {
    interface Marker {}

    static class Item implements Marker {}

    static class Other {}

    public static void main(String[] args) throws ClassNotFoundException {
        Item first = new Item();
        Item second = new Item();

        Class<?> mirror = first.getClass();
        System.out.println("same literal: " + (mirror == Item.class));
        System.out.println("same runtime type: "
                + (mirror == second.getClass()));
        System.out.println("different instances: " + (first != second));

        System.out.println("class name: " + mirror.getName());
        System.out.println("simple name: " + mirror.getSimpleName());
        System.out.println("superclass: "
                + mirror.getSuperclass().getName());
        System.out.println("interface: "
                + mirror.getInterfaces()[0].getSimpleName());

        System.out.println("int primitive: " + int.class.isPrimitive());
        System.out.println("wrapper primitive: "
                + Integer.class.isPrimitive());
        System.out.println("void mirror: " + (void.class == Void.TYPE));

        System.out.println("int array name: " + int[].class.getName());
        System.out.println("String 2D name: "
                + String[][].class.getName());
        System.out.println("component 2D: "
                + (String[][].class.getComponentType()
                        == String[].class));
        System.out.println("component primitive: "
                + int[].class.getComponentType().isPrimitive());

        System.out.println("array superclass: "
                + (int[].class.getSuperclass() == Object.class));
        System.out.println("array Cloneable: "
                + Cloneable.class.isAssignableFrom(int[].class));
        System.out.println("array Serializable: "
                + Serializable.class.isAssignableFrom(int[].class));
        System.out.println("array loader: "
                + (Item[].class.getClassLoader()
                        == Item.class.getClassLoader()));

        int[] numbers = {1, 2, 3};
        System.out.println("same array class: "
                + (numbers.getClass() == int[].class));
        System.out.println("array length: " + Array.getLength(numbers));

        System.out.println("lookup [I: "
                + (Class.forName("[I") == int[].class));
        System.out.println("lookup String[]: "
                + (Class.forName("[Ljava.lang.String;")
                        == String[].class));

        Object[] items = new Item[1];
        items[0] = new Item();
        System.out.println("runtime component: "
                + items.getClass().getComponentType().getSimpleName());
        try {
            items[0] = new Other();
        } catch (ArrayStoreException e) {
            System.out.println("bad store: ArrayStoreException");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ClassMirrorDemo.java
java ClassMirrorDemo
```

**Standard output:**

```text
same literal: true
same runtime type: true
different instances: true
class name: ClassMirrorDemo$Item
simple name: Item
superclass: java.lang.Object
interface: Marker
int primitive: true
wrapper primitive: false
void mirror: true
int array name: [I
String 2D name: [[Ljava.lang.String;
component 2D: true
component primitive: true
array superclass: true
array Cloneable: true
array Serializable: true
array loader: true
same array class: true
array length: 3
lookup [I: true
lookup String[]: true
runtime component: Item
bad store: ArrayStoreException
```

### Observed explanation

1. Two `new Item()` calls create **two instances**, but `getClass()` and `Item.class` lead to the same Class mirror of type `Item` defined by the same loader.
2. `ClassMirrorDemo$Item` is the **binary name of the nested class**; `getSimpleName()` returns the `Item` part.
3. `int.class` is primitive; `Integer.class` is a wrapper reference class. `void.class` represents the `void` type in reflection.
4. `[I` represents `int[]`; `[[Ljava.lang.String;` represents `String[][]`.
5. The `int[]` array has superclass `Object`, and is `Cloneable` and `Serializable`. An array class of `Item[]` has a defining loader corresponding to `Item`.
6. `Array.getLength` reads the length of the **array instance**, not a fixed element-count property of `int[].class`.
7. `Class.forName("[I")` and the binary array name `[Ljava.lang.String;` return the corresponding array Class mirror.
8. `Object[] items = new Item[1]` does not make the runtime component `Object`. Assigning `Other` through `Object[]` must be rejected by `aastore` because the actual array object can only hold `Item` or an appropriate subtype.

The program catches `ArrayStoreException` and prints a fixed string itself, avoiding dependence on detailed messages across JVM versions.

## 9. Class literals and array creation **do not** mean initializing the component class

Class loading, linking, **class initialization**, and **array class creation** are events that must be distinguished. Obtaining `Target.class` or creating `Target[]` does not always trigger the `Target` static initializer.

Create the file **`ArrayInitializationDemo.java`**:

```java
public class ArrayInitializationDemo {
    static class Target {
        static {
            System.out.println("Target static initializer");
        }

        Target() {
            System.out.println("Target constructor");
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        System.out.println("begin");

        Class<?> type = Target.class;
        System.out.println("literal: " + type.getSimpleName());

        Target[] array = new Target[2];
        System.out.println("array length: " + array.length);
        System.out.println("component: "
                + array.getClass().getComponentType().getSimpleName());

        Class.forName(Target.class.getName(),
                false, Target.class.getClassLoader());
        System.out.println("after lookup without initialization");

        Class.forName(Target.class.getName(),
                true, Target.class.getClassLoader());
        System.out.println("after lookup with initialization");

        new Target();
        System.out.println("end");
    }
}
```

Run on Java 17+:

```bash
javac -encoding UTF-8 ArrayInitializationDemo.java
java ArrayInitializationDemo
```

**Exact standard output:**

```text
begin
literal: Target
array length: 2
component: Target
after lookup without initialization
Target static initializer
after lookup with initialization
Target constructor
end
```

### Analysis

- `Target.class` provides the Class mirror of nested class `Target`; this operation **does not by itself require executing the static initializer**.
- `new Target[2]` creates an **array object with two reference slots**; the two elements are initially `null`. It **does not create two `Target` objects**, so the constructor is not printed; merely creating the array also does not trigger static initialization of the component class.
- `array.getClass().getComponentType()` returns the Class mirror of `Target`, without forcing `Target.<clinit>` to run.
- `Class.forName(name, false, loader)` loads/looks up and links the class if needed, but requests **not to initialize the class** through this call.
- `Class.forName(name, true, loader)` requests initialization of the uninitialized class, so it prints **one** `Target static initializer` line.
- After static initialization succeeds, `new Target()` creates an instance and calls the constructor; the static initializer does not run again.

**Remember:** an array class can be created or resolved by the JVM without initializing its component class. Only if **later** the code executes `new Target()`, calls a static method of `Target`, or performs a corresponding active use must initialization occur according to JVM/JLS rules.

For a reference array, creating the outer array and **populating elements with default `null` references** is completely different from creating instances of the component type. For a primitive array, elements have the default value of the primitive type such as `0`, `false`, or `0.0`.

## 10. Experimenting with class identity using two defining loaders

This example directly illustrates that **the same binary name does not mean the same class object**. Without replacing the system-wide classloader of the running JVM, the example uses two custom class loaders solely to independently define a small class from the **same bytecode**.

Create **`LoaderTarget.java`**:

```java
public class LoaderTarget {
}
```

Create **`LoaderIdentityDemo.java`**:

```java
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    static final class ByteLoader extends ClassLoader {
        Class<?> define(String binaryName, byte[] bytes) {
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("LoaderTarget.class"));

        ByteLoader loaderA = new ByteLoader();
        ByteLoader loaderB = new ByteLoader();

        Class<?> a = loaderA.define("LoaderTarget", bytes);
        Class<?> b = loaderB.define("LoaderTarget", bytes);

        System.out.println("same binary name: "
                + a.getName().equals(b.getName()));
        System.out.println("same Class object: " + (a == b));
        System.out.println("same defining loader: "
                + (a.getClassLoader() == b.getClassLoader()));

        Class<?> arrayA = Array.newInstance(a, 0).getClass();
        Class<?> arrayB = Array.newInstance(b, 0).getClass();
        System.out.println("same array class: " + (arrayA == arrayB));
        System.out.println("array A component: "
                + (arrayA.getComponentType() == a));
        System.out.println("array B component: "
                + (arrayB.getComponentType() == b));
    }
}
```

Compile both files in the same directory and run there:

```bash
javac -encoding UTF-8 LoaderTarget.java LoaderIdentityDemo.java
java LoaderIdentityDemo
```

**Exact standard output:**

```text
same binary name: true
same Class object: false
same defining loader: false
same array class: false
array A component: true
array B component: true
```

### Why is this example valid?

- `LoaderTarget.class` has already been created by `javac`; the program only **reads the bytes of that file itself**.
- `ByteLoader.define` calls **`ClassLoader.defineClass`**. Each `ByteLoader` object separately defines a class with the same binary name `LoaderTarget`.
- `a.getName()` and `b.getName()` are the same; however `a != b` and the defining class loaders are different.
- `Array.newInstance(a, 0)` and `Array.newInstance(b, 0)` create **two empty array objects**, while also allowing the JVM to recognize the corresponding `LoaderTarget[]` array classes according to the two independent component types.
- Because `a` and `b` are different runtime types, `arrayA` and `arrayB` are also different runtime types, even though printing their names alone may look the same.
- The code intentionally uses `defineClass` directly to illustrate the **defining loader**; a complete production custom loader also needs appropriate loading policies, synchronization, delegation, and security/byte-source checks.

**Simulation limitation:** the example does not require instantiating `LoaderTarget` from loader A or B. It only needs to define the class and create array classes; therefore it does not depend on calling the constructor or class initialization of `LoaderTarget`. Having a `Class` object does not imply that the static initializer has run.

## 11. Reflection: operating on runtime types instead of instances

Several `Class` and `java.lang.reflect.Array` APIs help inspect/manipulate type information:

| API | Meaning | Notes |
| --- | --- | --- |
| `obj.getClass()` | Runtime class of an instance | NPE if `obj == null` |
| `Class.getName()` | Runtime/binary name or array name form | Nested classes may have `$`, arrays have `[` |
| `Class.getTypeName()` | More readable type name for arrays | Not a guarantee to always return a source literal |
| `Class.isArray()` | Does the Class mirror describe an array type? | `int[].class.isArray()` is `true` |
| `Class.getComponentType()` | Component type of one dimension | Returns `null` if not an array |
| `Class.isPrimitive()` | Primitive/void marker per the API | `Integer.class` is a wrapper, not primitive |
| `Class.isInterface()` | Runtime interface type? | Arrays are not interfaces |
| `Class.getSuperclass()` | Superclass of the applicable class | `Object`, primitives, interfaces have different rules; array is `Object` |
| `Class.getClassLoader()` | Loader that defined the class per reflection | `null` can indicate bootstrap/primitive |
| `Class.isInstance(value)` | Checks if an object is an instance of the runtime type? | Always returns `false` for `null` |
| `Class.isAssignableFrom(other)` | Checks type-assignment relationship from `other` to receiver | **The direction of the check matters** |
| `Array.newInstance(component, n)` | Creates a runtime array instance from a component `Class` | Negative size causes `NegativeArraySizeException` |
| `Array.getLength(array)` | Gets the length of an array object | Argument must be a valid array object |

Distinguish `isInstance` and `isAssignableFrom`:

```java
System.out.println(Number.class.isInstance(Integer.valueOf(3))); // true
System.out.println(Number.class.isAssignableFrom(Integer.class)); // true
System.out.println(Integer.class.isAssignableFrom(Number.class)); // false
```

`isInstance` examines an **existing object**, while `isAssignableFrom` examines the **relationship between runtime types**. Both are affected by the identity of the defining loader; they do not just compare name strings.

### Reflection and generics

`Class<List>` does not separately encode a runtime class for `List<String>` and `List<Integer>` by generic type arguments. Regular Java generics use **type erasure**; generic metadata may be kept in `Signature` and read via APIs such as `Field.getGenericType()`, but **it does not create a new `Class` object for each type parameter**.

```java
java.util.List<String> words = java.util.List.of("a");
java.util.List<Integer> numbers = java.util.List.of(1);
System.out.println(words.getClass() == numbers.getClass());
```

In the example using `List.of`, the specific runtime factory implementation can vary by JDK; therefore **one should not use two instances returned from a factory to claim that all `List<T>` have the same implementation class**. The rule to remember is that regular generic type arguments **do not split into separate runtime classes per parameter `T`**.

When you need to create a generic array using reflection, accept an explicit `Class<T>` component and consider a checked cast; do not try to call `new T[10]` in a generic method if the Java type system does not allow it.

## 12. Observing bytecode and the connection to ClassFile

After compiling `ClassMirrorDemo.java`, use:

```bash
javap -c -p ClassMirrorDemo
javap -verbose ClassMirrorDemo
```

Useful patterns to look for:

| Java source | Commonly seen bytecode | Meaning |
| --- | --- | --- |
| `Item.class` | `ldc` referencing a type entry in the constant pool | Obtains the runtime `Class` mirror of the type |
| `first.getClass()` | `invokevirtual java/lang/Object.getClass:()Ljava/lang/Class;` | Obtains the runtime class of the object |
| `new Item()` | `new`, `dup`, `invokespecial <init>` | Creates the object and executes the constructor |
| `new int[3]` | `newarray int` | Creates a primitive array object |
| `new Item[1]` | `anewarray` | Creates a reference array object |
| `numbers.length` | `arraylength` | Pushes the `int` length onto the operand stack |
| `values[index]` / `values[index] = ...` | appropriate `*aload` / `*astore` | Reads/writes an element and performs related runtime checks |
| `String[][].class` | `ldc` referencing the array class | Obtains the mirror of the runtime array type |

`ldc` with a class literal uses a symbolic reference in the constant pool, but **it does not mean calling the `java.lang.Class()` constructor from Java code**. The JVM manages obtaining/maintaining the Class mirror for a runtime type according to the VM's foundational rules.

Bytecode `newarray`, `anewarray`, and `multianewarray` perform array instance allocation and interact with array classes; they **do not need a bytecode `<init>` constructor of an array class** like a programmer-declared class. Arrays have special VM rules.

**`javap -c` prints bytecode stored in the class file**, not CPU JIT machine code. Instructions, offsets, and constant pool ordering can differ across compilers/versions while still adhering to the same semantics.

## 13. Errors and how to identify the right layer

| Symptom | Cause to check |
| --- | --- |
| `ClassNotFoundException` on `Class.forName(...)` | Wrong name/binary name, or classpath/module path/loader cannot find the definition |
| `NoClassDefFoundError` | Runtime cannot load the required definition, or the class previously failed initialization; do not automatically lump every cause into a missing file |
| `LinkageError` or loader constraint violation | Inconsistent identity/relationships between classes and loaders, or incompatible class metadata |
| `ClassCastException` even though both printed class names look the same | Check the **defining class loader**, not just `getName()` |
| `ArrayStoreException` when writing through `Object[]` | The runtime component type of the array may be narrower than the static type `Object` |
| `NegativeArraySizeException` | The created array size is negative |
| `ArrayIndexOutOfBoundsException` | The accessed index is outside `0 .. length-1` |
| `NullPointerException` when using `getClass()` or `array.length` | The reference is `null` |
| Able to obtain `Class` but no static initializer log appears | Class loading/obtaining a mirror **does not** always cause class initialization |
| `Class.forName("java.lang.String[]")` does not find the array type | Use the array name in the form `[Ljava.lang.String;` or the class literal `String[].class` |

Do not use `==` between **two instances** in place of `==` between **two Class mirrors**; they answer two different questions. Similarly, both object identity and class identity differ from comparing two name strings.

## 14. Exercises and self-check questions

**Exercise 1 — One runtime type, multiple instances.**  
Given `String a = new String("x"); String b = new String("y");`. What do `a == b` and `a.getClass() == b.getClass()` return?  
**Answer:** `false` and `true`. Two different instances, but the same runtime class.

**Exercise 2 — Array of arrays.**  
Is `String[][].class.getComponentType()` equal to `String.class`?  
**Answer:** **No**; it equals `String[].class`. Each `getComponentType()` removes **one dimension**.

**Exercise 3 — Arrays with different lengths.**  
Is `new int[2].getClass() == new int[9].getClass()` true?  
**Answer:** **True** (if written in a valid Java expression with appropriate parentheses); both have the same `int[]` type; length belongs to each instance, not the runtime class.

**Exercise 4 — Class loader identity.**  
Why can `Class<?> a` and `Class<?> b` have the same `getName()` while `a == b` is `false`?  
**Answer:** They can be **two definitions with the same binary name from different defining loaders**. Compare `getClassLoader()`, and inspect the loading path and delegation relationships.

**Exercise 5 — Array initialization.**  
Does `new Target[5]` call the `Target()` constructor 5 times?  
**Answer:** **Not even once**; it creates an array containing 5 default `null` references. Creating `Target` objects requires separate operations like `new Target()`.

**Exercise 6 — Active use.**  
Do `Target.class` and `Class.forName("Target", true, loader)` have the same initialization effect?  
**Answer:** **No**; a class literal does not by itself force the static initializer to run; `Class.forName` with `initialize=true` requests initialization according to the corresponding rules.

**Exercise 7 — Primitive Class mirror.**  
Is `int.class == Integer.class` true?  
**Answer:** **False**. Primitive `int` and wrapper class `Integer` are two different types.

**Exercise 8 — Array inheritance.**  
What are `Object.class.isAssignableFrom(int[].class)` and `Object[].class.isAssignableFrom(int[].class)` respectively?  
**Answer:** `true` and `false`. Every array is an Object, but a primitive array is not an Object[].

**Exercise 9 — Runtime store check.**  
Why does `Object[] a = new String[1]; a[0] = new Object();` compile yet fail?  
**Answer:** The static type `Object[]` allows assigning Object; the runtime array object has component type `String`, so `aastore` throws `ArrayStoreException`.

**Exercise 10 — ClassFile.**  
Is it mandatory to find an `int[].class` file on disk for `int[].class` to work?  
**Answer:** **No**. The JVM creates/recognizes array classes according to its own rules. A regular ClassFile describes a defined class/interface, not a JVM-created array class.

**Exercise 11 — `Class.forName` array name.**  
Is the appropriate runtime name when looking up `String[]` `java.lang.String[]` or `[Ljava.lang.String;`?  
**Answer:** According to the array name syntax of `Class.getName()`, use **`[Ljava.lang.String;`**.

**Exercise 12 — Two classes with the same name in plugins.**  
If loader A and loader B actually define two independent `com.example.Plugin` classes, is the corresponding `com.example.Plugin[]` guaranteed to be a single array class?  
**Answer:** **No**. Array classes are identified via their corresponding component type; different component runtime types produce different array types.

### Conclusion

When debugging Java class loading, always distinguish **object instance**, **Class mirror**, **runtime type identity**, **defining loader**, and **array class**. `Class<?>` is the observation port for a runtime type, not a copy of an object. A class/interface type carries an identity tied to its name and defining loader. Array classes are created by the JVM according to their component type; array objects have their own length and data, whereas an array Class object describes the **type**, not the length of a specific instance. Class literals and array creation also do not force the component class to run its static initializer.

To read the detailed rules, consult *The Java Virtual Machine Specification*, section **§5.3 (Creation of Classes and Interfaces, in which §5.3.3 is Creation of Array Classes)**, and *The Java Language Specification*, sections **§10 (Arrays)** and **§12.4 (Initialization)**. The `java.lang.Class` and `java.lang.reflect.Array` APIs provide direct ways to test the concepts in this article.