# Primitive Types, void, and the Limits of loadClass

## 1. The Problem: Why Does int.class Exist When loadClass("int") Does Not Work?

In Java, **types** and **classes that can be loaded from bytecode** are not the same set. The Java language has eight primitive types: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, and `double`. The JVM also represents `void` for methods that do not return a value. Meanwhile, `java.lang.ClassLoader.loadClass(String)` is designed to find a class or interface by its **binary name**, such as `java.lang.String` or `com.example.Account`.

Therefore:

- `int.class`, `boolean.class`, and `void.class` are valid Java expressions that return special `Class<?>` objects supported by the VM.
- `ClassLoader.loadClass("int")` or `Class.forName("int")` is not the API for obtaining the representation of the primitive `int`.
- `ClassLoader.loadClass("void")` or `Class.forName("void")` is not the API for obtaining `void.class`.
- `Integer.class` is a **wrapper class**, which differs from `int.class`; `Void.class` is a wrapper/reference class, which differs from `void.class`.
- `int[]` is an **array reference type**: even though its elements are primitive, the array itself is an object and has an array class created by the JVM when needed.

This lesson clarifies those semantics, the difference between `ClassLoader.loadClass` and `Class.forName`, and how reflection and JVM descriptors represent primitives, `void`, and arrays.

## 2. The Eight Primitive Types and Their Class<?> Representations

The primitive types have the following names and descriptors:

| Java Type | JVM Descriptor | Example Value |
|---|---|---|
| `boolean` | `Z` | `true` |
| `byte` | `B` | `(byte) 1` |
| `short` | `S` | `(short) 2` |
| `char` | `C` | `'A'` |
| `int` | `I` | `42` |
| `long` | `J` | `42L` |
| `float` | `F` | `3.5f` |
| `double` | `D` | `3.5d` |

A primitive value is not an object with identity in the way a reference type is. When boxing, Java can represent a value using a wrapper object such as `Integer`, but `Integer` and `int` are two different types.

In reflection, `Class<?>` still represents primitive types. The standard Java API provides:

```java
Class<?> intType = int.class;
Class<?> longType = long.class;
Class<?> boolType = boolean.class;

boolean same = int.class == Integer.TYPE;  // true
boolean wrapper = int.class == Integer.class; // false
```

Is `Integer.TYPE` a `public static final Class<Integer> TYPE` field? **You should not infer the exact generic type of that field**; what matters is the `Class<?>` value representing `int`. The Java API defines the `TYPE` field on wrapper classes to return the `Class` object of the corresponding primitive.

### Why Can Class Represent Primitives?

`Class` is the JVM's reflection API; it does not only represent classes and interfaces loaded from `.class` files. The JVM has built-in `Class` objects for the eight primitives and `void`. These objects **are not created from files named `int.class`, `boolean.class`, or `void.class` on the class path**.

This explains both of the following facts at the same time:

```java
System.out.println(int.class.isPrimitive()); // true
System.out.println(int.class.getClassLoader()); // null
```

In the `Class.getClassLoader()` API, primitives and `void` return `null`. That **is not evidence that the bootstrap loader read an `int.class` file**. The `null` value can also represent the bootstrap loader for classes actually defined by bootstrap, such as `java.lang.String` on a standard JDK. The same API result can correspond to different type-creation mechanisms.

## 3. How Special Is void?

`void` is a special type indicating that there is no return value. It can appear in a method declaration:

```java
public static void log(String message) {
    System.out.println(message);
}
```

However, you cannot write `void value;`, `new void[3]`, or use `void` as a method parameter in Java source code.

The JDK still provides:

```java
Class<?> voidType = void.class;
Class<?> viaWrapper = Void.TYPE;
System.out.println(voidType == viaWrapper); // true
System.out.println(void.class.isPrimitive()); // true
```

According to Java's `Class.isPrimitive()`, there are **nine built-in `Class` objects** for the eight primitives and `void`; all nine return `true` for `isPrimitive()`. That **does not mean** a variable can hold a `void` value the way it holds an `int`.

Distinguish between:

| Expression | Represents |
|---|---|
| `void.class` | The special return type `void` |
| `Void.TYPE` | The same `Class` object as `void.class` |
| `Void.class` | The reference class `java.lang.Void` |
| `int.class` | The primitive `int` |
| `Integer.class` | The reference class `java.lang.Integer` |

The wrapper `Void` exists in the standard library. `ClassLoader.loadClass("java.lang.Void")` can find that class, but this is **not** the way to obtain `void.class`.

## 4. The Actual Limits of ClassLoader.loadClass(String)

According to the Java SE 17 API, `ClassLoader.loadClass(String)` takes the **binary name of a class or interface**, not a JVM descriptor code and not an arbitrary Java source expression.

Valid examples:

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();

Class<?> s = loader.loadClass("java.lang.String");
Class<?> list = loader.loadClass("java.util.ArrayList");
```

The following table is easy to remember:

| Input String | Valid Class/Interface Name? | Notes |
|---|---|---|
| `java.lang.String` | Yes | Binary name of a class |
| `java.util.Map$Entry` | Yes | Binary name of a nested interface |
| `com.example.Service` | Yes, if the class exists and is visible to the loader | Looked up through the chosen loader |
| `int` | No | Primitive type; no ordinary class file with this name |
| `void` | No | Special return type |
| `I` | No | JVM descriptor for `int` |
| `Ljava/lang/String;` | No | JVM field descriptor of a class |
| `java/lang/String` | No | Internal name, not a binary name |
| `[I` | Not part of the binary-name contract of `loadClass` | Use `Class.forName("[I")` or `int[].class` for arrays |

`loadClass(name)` is equivalent to `loadClass(name, false)`. With the default implementation, the class loader checks whether the class is already loaded, delegates to the parent (or bootstrap if the parent is `null`), and then calls `findClass`. A custom loader can override lookup, but it does not turn a primitive into an ordinary class file.

### When loadClass Fails

If the class is not in the search sources visible to the loader, the usual result is `ClassNotFoundException`:

```java
try {
    loader.loadClass("int");
} catch (ClassNotFoundException ex) {
    System.out.println("Không có class int để load");
}
```

This is an **illustrative snippet** that requires a `loader` variable in scope. If you want a complete program, use the example in Section 7.

The error above does not mean the JVM lacks the `int` type. To get the `Class<?>` for a primitive, use `int.class` or `Integer.TYPE`.

## 5. Class.forName and Array Names: Exceptions to Know

`Class.forName("java.lang.String")` is the common way to obtain a `Class<?>` from a class's binary name. However, `Class.forName("int")` and `Class.forName("void")` do not turn Java keywords into type tokens; those calls throw `ClassNotFoundException` on a standard JDK.

`Class.forName` also supports **array names** using special syntax:

```java
Class<?> primitiveArray = Class.forName("[I");
Class<?> referenceArray =
        Class.forName("[Ljava.lang.String;");
```

Result:

- `primitiveArray == int[].class` is `true`.
- `referenceArray == String[].class` is `true`.
- `Class.forName("[[I")` retrieves `int[][].class`.
- `Class.forName("[Ljava.lang.String;")` uses **dots** in the element class name.
- `Class.forName("[Ljava/lang/String;")` is not the standard syntax for looking up this reference array via `Class.forName`.

The reason is that array classes have their own **runtime naming convention**, which `Class.getName()` also uses. For ordinary classes and interfaces, `Class.forName` still uses the binary name.

### Comparing Class.forName and loadClass

| API | Ordinary Class Case | Primitive/void | Array |
|---|---|---|---|
| `SomeType.class` | Used when the type is known at compile time | `int.class`, `void.class` are valid | `int[].class`, `String[].class` are valid |
| `Class.forName(name)` | Takes a binary name | Does not interpret `"int"`, `"void"` | Takes array names like `"[I"`, `"[Ljava.lang.String;"` |
| `ClassLoader.loadClass(name)` | Takes a class/interface binary name | No ordinary primitive/void class file exists | Does not use array descriptors as a standard API contract |
| `Array.newInstance(component, n)` | Not for loading ordinary classes | Can take primitive components like `int.class` | Creates an array object; the array class is provided by the runtime |

`Class.forName(name, initialize, loader)` also lets you specify the initialization flag and the loader used for lookup. `initialize=false` **does not** make primitive-name lookup valid; `loader=null` typically indicates bootstrap lookup for classes.

## 6. Primitive Arrays Are Objects, Not Primitives

One of the most important points:

```java
int count = 3;        // primitive value
int[] values = new int[3]; // reference to array object
```

The array `int[]` is a **reference type** and is a JVM object. You can verify this:

```java
System.out.println(int.class.isPrimitive());     // true
System.out.println(int[].class.isPrimitive());   // false
System.out.println(int[].class.isArray());       // true
System.out.println(values instanceof Object);   // true
System.out.println(int[].class.getComponentType() == int.class); // true
```

The snippet above requires the `values` variable to be declared as in the example. If you need to create an array via reflection:

```java
Object array = java.lang.reflect.Array.newInstance(int.class, 3);
System.out.println(array.getClass() == int[].class); // true
```

There is no `void[]` array. `Array.newInstance(void.class, 3)` is not allowed and throws `IllegalArgumentException`.

### Who Creates Array Classes?

The Java `ClassLoader` API specifies that **array classes are created by the runtime as needed**, rather than created by a loader from the bytecode of an ordinary class file. `Class.getClassLoader()` of an array class corresponds to the loader of its **element type** if it is a reference type; if the element type is primitive, the result is `null`.

For example:

- `String[].class.getClassLoader()` typically returns `null` on JDK 17 because `String` is defined by bootstrap.
- `int[].class.getClassLoader()` returns `null`, but that does not mean bootstrap read `[I.class`.
- If `plugin.Message` is defined by loader P, the corresponding array class `plugin.Message[]` has the same loader as that element class. Two plugin loaders defining two separate `plugin.Message` classes can lead to two different array types.
- `int[][]` is still a reference type, with a name of the form `[[I` and direct component type `int[]`.

## 7. Complete Java 17 Example: Distinguishing Primitive, void, Array, and Loader

Create the file **`PrimitiveAndLoaderDemo.java`**:

```java
public class PrimitiveAndLoaderDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader app = PrimitiveAndLoaderDemo.class.getClassLoader();

        System.out.println("int primitive: " + int.class.isPrimitive());
        System.out.println("void primitive: " + void.class.isPrimitive());
        System.out.println("Integer primitive: "
                + Integer.class.isPrimitive());
        System.out.println("int equals TYPE: "
                + (int.class == Integer.TYPE));
        System.out.println("void equals TYPE: "
                + (void.class == Void.TYPE));

        System.out.println("int loader null: "
                + (int.class.getClassLoader() == null));
        System.out.println("void loader null: "
                + (void.class.getClassLoader() == null));

        System.out.println("int descriptor: "
                + int.class.descriptorString());
        System.out.println("void descriptor: "
                + void.class.descriptorString());

        System.out.println("int[] array: " + int[].class.isArray());
        System.out.println("int[] primitive: "
                + int[].class.isPrimitive());
        System.out.println("int[] loader null: "
                + (int[].class.getClassLoader() == null));
        System.out.println("int[] component is int: "
                + (int[].class.getComponentType() == int.class));

        System.out.println("Find [I: "
                + (Class.forName("[I") == int[].class));
        System.out.println("Find String[]: "
                + (Class.forName("[Ljava.lang.String;")
                        == String[].class));

        try {
            Class.forName("int");
            System.out.println("Unexpected forName success");
        } catch (ClassNotFoundException expected) {
            System.out.println("forName(int): not found");
        }

        try {
            app.loadClass("void");
            System.out.println("Unexpected loadClass success");
        } catch (ClassNotFoundException expected) {
            System.out.println("loadClass(void): not found");
        }

        System.out.println("String class by loader: "
                + (app.loadClass("java.lang.String") == String.class));
    }
}
```

Compile and run with JDK 17 or later on the standard class path:

```bash
javac PrimitiveAndLoaderDemo.java
java PrimitiveAndLoaderDemo
```

Stdout on standard JDK 17:

```text
int primitive: true
void primitive: true
Integer primitive: false
int equals TYPE: true
void equals TYPE: true
int loader null: true
void loader null: true
int descriptor: I
void descriptor: V
int[] array: true
int[] primitive: false
int[] loader null: true
int[] component is int: true
Find [I: true
Find String[]: true
forName(int): not found
loadClass(void): not found
String class by loader: true
```

**How to read the output:**

1. `int.class` and `void.class` are supported by the VM, whereas `Integer.class` is a reference class.
2. `int.class == Integer.TYPE` and `void.class == Void.TYPE` are both true.
3. `getClassLoader() == null` for primitives and `void` does not mean a corresponding class file was found and read by bootstrap.
4. `int[]` is an array reference type and has its own `Class<?>`.
5. `Class.forName("[I")` and `Class.forName("[Ljava.lang.String;")` are valid because of the API's array naming convention.
6. Looking up `"int"` and `"void"` with binary-name class lookup APIs does not yield primitive/void tokens.

If a custom system class loader with non-standard policies is used, some lookups may behave differently. This sample intentionally uses the default execution on JDK 17.

## 8. How Do JVM Descriptors Differ from Class.getName?

Bytecode uses **field descriptors** and **method descriptors** to represent types. In Java SE 17, `Class.descriptorString()` is the way to get a type's descriptor from a `Class<?>` object.

| Type | `Class.getName()` | `Class.descriptorString()` |
|---|---|---|
| `int` | `int` | `I` |
| `long` | `long` | `J` |
| `boolean` | `boolean` | `Z` |
| `void` | `void` | `V` |
| `String` | `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` | `[I` |
| `int[][]` | `[[I` | `[[I` |
| `String[]` | `[Ljava.lang.String;` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava.lang.String;` | `[[Ljava/lang/String;` |

In a field descriptor, `I` represents `int`. `V` is only valid as a **method return type**, not as a field type or method parameter type. A method:

```java
public static void print(int count, String[] labels) {
}
```

has the descriptor:

```text
(I[Ljava/lang/String;)V
```

The part inside `(...)` has one `int` parameter and one `String[]` parameter; `V` after `)` represents no return value.

### Distinguishing Three Ways to Write the Name of String

- `java.lang.String`: binary name, commonly used with `loadClass`.
- `java/lang/String`: internal name in JVM metadata.
- `Ljava/lang/String;`: field descriptor of the reference type `String`.

Do not pass `Ljava/lang/String;` to `loadClass` expecting Java to automatically interpret it as `java.lang.String`.

## 9. Java 17 Example: Reflecting a void Method Without loadClass("void")

Create the file **`VoidMethodDemo.java`**:

```java
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class VoidMethodDemo {
    public static void ping(int count) {
    }

    public static void main(String[] args) throws Exception {
        Method method = VoidMethodDemo.class.getDeclaredMethod(
                "ping", int.class);

        System.out.println("Return type is void: "
                + (method.getReturnType() == void.class));

        MethodType type = MethodType.methodType(
                method.getReturnType(), method.getParameterTypes());

        System.out.println("Method descriptor: "
                + type.descriptorString());
    }
}
```

Run:

```bash
javac VoidMethodDemo.java
java VoidMethodDemo
```

Stdout:

```text
Return type is void: true
Method descriptor: (I)V
```

The example shows that reflection obtains the `void` return type via `void.class`; `MethodType` can represent `void` in the **return** position. There is no ordinary class `void` loaded by `ClassLoader.loadClass`.

## 10. Other Limits of loadClass to Remember

### Does Not Create an Instance

`loader.loadClass("com.example.Service")` returns `Class<?>`; it does not run a constructor to create a `Service` instance. You must use an appropriate object creation mechanism to get an instance.

### Does Not Initialize the Class by Default

`ClassLoader.loadClass(String)` is equivalent to `loadClass(name, false)`, meaning it does not request resolution with `resolve=true` and **does not trigger class initialization like an active use**. Loading, linking, and initialization are distinct stages. The single-argument `Class.forName(name)` overload typically triggers initialization for the located class.

### Does Not Bypass Visibility or Module Boundaries

A loader that cannot see the required class or module may fail with `ClassNotFoundException`. Obtaining `Class<?>` does not prove that the class's methods, constructors, or fields are accessible from everywhere; access checks and JPMS still apply.

### Does Not Turn a Wrapper into a Primitive

`loadClass("java.lang.Integer")` returns the wrapper `Integer.class`, not `int.class`. Boxing and unboxing are language and runtime rules, not "name translation" inside a class loader.

### Does Not Determine All Linking Stages

A class may be found, yet later fail during resolution, preparation, or initialization when used—for example due to a missing dependency, `NoClassDefFoundError`, `ExceptionInInitializerError`, or `LinkageError`. A successful `loadClass` call does not guarantee that the entire application behavior will succeed.

### Does Not Create Array Classes from .class Files

Array classes are created by the runtime. Use `int[].class`, `Class.forName("[I")`, or `Array.newInstance(int.class, length)`; do not assume that a `[I.class` file exists or that `loadClass("[I")` is the contract for accessing arrays.

## 11. Common Mistakes

| Misconception | Correct Understanding |
|---|---|
| "Because `int.class` exists, there is an `int.class` file." | Primitive Class objects are pre-created by the VM; no ordinary bytecode class file is needed. |
| "`Class.forName("void")` must equal `Void.class`." | `Void.class` is the wrapper reference class; `void.class` and `Void.TYPE` are what represent void. |
| "`int.class` and `Integer.class` are the same type." | One is primitive, one is a reference wrapper; `==` is false. |
| "`void.class.isPrimitive()` must be false." | The API includes void among the nine primitive-related Class objects; the result is true. |
| "`int[]` is primitive because its elements are int." | An array is a reference type; `int[].class.isPrimitive()` is false. |
| "Every `getClassLoader() == null` proves bootstrap read a class file." | Primitives/void and primitive arrays also return null by API rule, without a corresponding ordinary class file. |
| "`loadClass("[I")` is the standard API to load an array." | `loadClass` takes a class/interface binary name; use `Class.forName("[I")` to access an array class with supported syntax. |
| "A successful `loadClass` has already run the static initializer." | Loading and initialization are two separate steps. |
| "The JVM descriptor `Ljava/lang/String;` is a binary name." | The binary name of that class is `java.lang.String`. |
| "You can declare `void[]` or a `void` parameter." | Void is only valid in method return contexts and as an API type token, not as an array component or parameter type. |

## 12. Self-Check Exercises

**Question 1.** `int.class` exists, so why is `ClassLoader.loadClass("int")` not a valid way to access it?

**Answer:** The primitive `int` is not a class or interface with `.class` bytecode for a loader to look up by binary name. `int.class` is a special VM Class object; `Integer.TYPE` can also be used.

**Question 2.** What does `void.class.isPrimitive()` print? Can you create `new void[3]`?

**Answer:** It prints `true` according to `Class.isPrimitive()`. No, `void[]` is not a valid array type.

**Question 3.** Is `Integer.TYPE == Integer.class` true?

**Answer:** No. `Integer.TYPE == int.class` is true; `Integer.class` is the wrapper reference class.

**Question 4.** What type does `Class.forName("[I")` return? Does `Class.forName("int")` return the same type?

**Answer:** `Class.forName("[I")` returns `int[].class`. `Class.forName("int")` cannot find a primitive via binary-name lookup.

**Question 5.** How do `String[].class.getName()` and `String[].class.descriptorString()` differ?

**Answer:** The first is `[Ljava.lang.String;` with dots; the second is `[Ljava/lang/String;` with slashes in the internal name.

**Question 6.** When `int[].class.getClassLoader() == null`, can we conclude that a `[I.class` file is on the bootstrap class path?

**Answer:** No. Array classes are created by the runtime; primitive arrays have a null loader by JVM/API rules.

**Question 7.** What is the descriptor of the method `void notify(int count, String[] names)`?

**Answer:** `(I[Ljava/lang/String;)V`. `I` for `int`, `[Ljava/lang/String;` for `String[]`, and `V` for the `void` return type.

**Question 8.** Why cannot `ClassLoader.loadClass("java.lang.Integer")` replace `int.class`?

**Answer:** It retrieves the definition of the wrapper class `Integer`, which is a reference type different from the primitive `int`.

## 13. Key Takeaways and References

- **The eight primitives + void** have special VM-created `Class<?>` objects; there are no corresponding binary-name class files to load via `loadClass("int")` or `loadClass("void")`.
- **Arrays** are reference types even when their elements are primitive. Array classes are created by the runtime; `int[]` differs from `int`.
- **ClassLoader.loadClass(String)** looks up classes and interfaces by binary name and is subject to loader visibility; it does not create instances or trigger initialization.
- **Class.forName** supports ordinary class binary names and array names like `[I`, `[Ljava.lang.String;`, but does not interpret primitive tokens like `"int"`.
- **The descriptor** of primitive `int` is `I`, and of `void` in a method return is `V`; these differ from Java source spelling and binary names.

Official sources:

1. [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isPrimitive`, `getName`, `getClassLoader`, `forName`, `descriptorString`.
2. [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation, how the JVM creates array classes.
3. [Java SE 17 — Void](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Void.html): `Void.TYPE` and the wrapper class.
4. [JVMS 17 — Types and Values](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html): primitive, reference, and array types.
5. [JVMS 17 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): field/method descriptors, primitive/void syntax.