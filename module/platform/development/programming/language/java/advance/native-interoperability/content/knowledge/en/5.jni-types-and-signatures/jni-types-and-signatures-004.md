# Reading Type Descriptors for Classes, Arrays, and Methods in JNI

## 1. Why do we need to read type descriptors?

A **type descriptor** is a character string following the Java Virtual Machine (JVM) syntax, recorded in `.class` files to represent field types and method types. JNI (Java Native Interface) uses the same convention, often called a **type signature**, when looking up Java fields or methods from C/C++ code.

For example:

- `int` → `I`.
- `java.lang.String` → `Ljava/lang/String;`.
- `int[][]` → `[[I`.
- `long calculate(int count, String name, int[] values)` → `(ILjava/lang/String;[I)J`.

A descriptor is a very short string, but it must **match exactly**: a missing `;`, a wrong type character, or a wrong array dimension count can cause `GetFieldID` or `GetMethodID` to fail to find the member. This content belongs to **JNI Types and Signatures**: understanding how to read, construct, verify, and use descriptors in JNI calls.

Distinguish the different representations of the same type:

| Representation | Example with `String` | Purpose |
| --- | --- | --- |
| Java source name | `java.lang.String` | Writing Java code |
| Internal name | `java/lang/String` | Calling `FindClass` for regular classes and representing class names in bytecode |
| Type/field descriptor | `Ljava/lang/String;` | Describing object types in fields, parameters, and return values |
| Method descriptor | `(I)Ljava/lang/String;` | A method that takes `int` and returns `String` |

A descriptor does not contain parameter names, Java code, or native library addresses. In JNI, the field/method name and the `sig` string are **two separate arguments**.

## 2. Primitive types table

For a primitive type, the descriptor is a single character:

| Java type | Descriptor | C type in JNI |
| --- | --- | --- |
| `boolean` | `Z` | `jboolean` |
| `byte` | `B` | `jbyte` |
| `char` | `C` | `jchar` |
| `short` | `S` | `jshort` |
| `int` | `I` | `jint` |
| `long` | `J` | `jlong` |
| `float` | `F` | `jfloat` |
| `double` | `D` | `jdouble` |
| `void` | `V` | `void` |

Things to remember:

- `J` is the descriptor for `long`; `L` starts a **class/interface type**.
- `B` is `byte`, whereas `Z` is `boolean`.
- `V` is allowed as a **method return type** but not as a field type or method parameter. `void[]` or `(V)I` is invalid.
- `jint`, `jstring` are **types in JNI C code**, not JVM descriptor syntax. Write `I` for `int`, `Ljava/lang/String;` for `String`.
- Java `char` is encoded in 16-bit UTF-16 code units; the character `C` in a descriptor only represents the **type**, not how a string is encoded.

For example: the field `private int age;` uses `I`, the field `long id;` uses `J`; the method `void reset()` uses `()V`.

## 3. Reading descriptors for classes and interfaces: `L...;`

An object type has the form:

```text
L<class-name-as-internal-name>;
```

How to decode:

1. `L` begins the reference type.
2. Read the class/interface name up to the `;` character.
3. Convert `/` in the class name to `.` as package separators to return to the Java representation.
4. The `;` character is a **mandatory terminator**.

| Java | Descriptor |
| --- | --- |
| `String` | `Ljava/lang/String;` |
| `Object` | `Ljava/lang/Object;` |
| `java.util.List` | `Ljava/util/List;` |
| `java.util.Map` | `Ljava/util/Map;` |
| `java.io.IOException` | `Ljava/io/IOException;` |
| `com.example.model.Order` | `Lcom/example/model/Order;` |

For instance, `Ljava/util/Map;` is **one** object descriptor, not three types `L`, `java/util/Map`, and `;`. Therefore, in a method descriptor, the string `(Ljava/lang/String;I)V` has two parameters: `String` and `int`.

### 3.1. Nested classes and the `$` character

Code:

```java
package demo;

public class Outer {
    public static class Inner {
    }
}
```

The descriptor for `Outer.Inner` is:

```text
Ldemo/Outer$Inner;
```

`/` separates packages, while `$` appears in the **binary name** of nested classes. Do not replace `$` with `/` or `.`. Some local/anonymous classes have compiler-generated names (`$1`, `$1Local`, ...); it is best to check `javap` or `Class.descriptorString()` to know for sure.

### 3.2. `FindClass` differs from descriptor syntax

JNI `FindClass`, when given a **regular class name**, uses the **internal name** without `L` and `;`:

```c
// Inside a JNI function with a valid JNIEnv *env:
jclass stringClass = (*env)->FindClass(env, "java/lang/String");
```

If looking up an **array type**, `FindClass` accepts an **array type signature**, such as `"[I"` or `"[Ljava/lang/String;"`. Meanwhile, `GetFieldID` / `GetMethodID` still require standard descriptors like `"Ljava/lang/String;"` when referring to a `String` type.

JNI calls also depend on the active class loader. A correct descriptor does not guarantee finding a class if the loader lacks permission or cannot see that class.

## 4. Reading array descriptors

Each array dimension is represented by **one `[` character preceding the element type descriptor**:

```text
[FieldType
[[FieldType
[[[FieldType
```

| Java type | Descriptor |
| --- | --- |
| `int[]` | `[I` |
| `int[][]` | `[[I` |
| `long[][][]` | `[[[J` |
| `boolean[]` | `[Z` |
| `double[][]` | `[[D` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |
| `Object[][][]` | `[[[Ljava/lang/Object;` |
| `java.util.List[]` | `[Ljava/util/List;` |

Example of reading `[[Ljava/lang/String;`: two `[` characters indicate **two dimensions**; the remainder `Ljava/lang/String;` is the element type `String`, yielding `String[][]`. For `[[D`, the element type `D` is `double`, yielding `double[][]`.

Do not add `L` before a primitive array: `[I` is correct for `int[]`, whereas `L[I;` is wrong. An array is a **reference type** in Java even when its elements are primitives. The JVMS allows array descriptors with at most **255 dimensions**, though real-world projects rarely need more than a few dimensions.

### 4.1. `Class.getName()` and `descriptorString()` can differ

For `String[][].class`:

```java
System.out.println(String[][].class.getTypeName());
System.out.println(String[][].class.getName());
System.out.println(String[][].class.descriptorString());
```

Output:

```text
java.lang.String[][]
[[Ljava.lang.String;
[[Ljava/lang/String;
```

- `getTypeName()` is the human-readable name.
- `getName()` for array classes has a form close to the descriptor, but the component class name uses `.`.
- `descriptorString()` returns the exact JVM descriptor with `/`.

When a JNI signature is needed, `Class.descriptorString()` avoids mistakes compared to copying `Class.getName()` and manipulating the string manually.

## 5. Reading method descriptors: `(parameters)return-type`

Standard grammar:

```text
(<concatenated-parameter-descriptors>)<return-descriptor>
```

`(` opens and `)` closes the parameters. **There are no commas or spaces** between descriptors. The return part is **one** field type or `V`.

| Java declaration | Method descriptor |
| --- | --- |
| `void reset()` | `()V` |
| `int sum(int x, int y)` | `(II)I` |
| `boolean check(String s)` | `(Ljava/lang/String;)Z` |
| `long f(int n, String s, int[] arr)` | `(ILjava/lang/String;[I)J` |
| `String join(String[] parts, int limit)` | `([Ljava/lang/String;I)Ljava/lang/String;` |
| `void scan(int[][] matrix, boolean enabled)` | `([[IZ)V` |
| `double[] transform(double[][] values)` | `([[D)[D` |
| `List<String> findAll()` | `()Ljava/util/List;` |

Reading `(ILjava/lang/String;[I)J` step by step:

1. `(`: start of parameters.
2. `I`: parameter 1 is `int`.
3. `Ljava/lang/String;`: parameter 2 is `String`.
4. `[I`: parameter 3 is `int[]`.
5. `)`: end of parameter list.
6. `J`: return type is `long`.

This corresponds to the signature `long f(int, String, int[])`.

### 5.1. What a method descriptor does not represent

A descriptor string **does not contain**:

- The method name (`f`, `reset`, ...), variable/parameter names, or exception names in `throws`.
- Modifiers such as `public`, `private`, `static`, `final`, `synchronized`.
- The implicit `this` reference of an instance method.
- The hidden C/JNI parameters `JNIEnv *` and `jobject`/`jclass`.
- Full generic types (`List<String>`, `T`, wildcards) after erasure.

**The return type is part of the descriptor.** You must pass the exact `(I)I` or `(I)J` matching the actual method, even though Java source does not allow overloading differing only by return type. The descriptor identifies parameter types **in exact order**.

### 5.2. Constructors, static methods, and overloading

Java constructors:

```java
class Person {
    public Person(String name, int age) {}
    public static int parse(String s) {
        return Integer.parseInt(s);
    }
}
```

In the JVM:

- A constructor has the special name `<init>` and descriptor `(Ljava/lang/String;I)V`. A constructor does not return `LPerson;`.
- The static method `parse` has descriptor `(Ljava/lang/String;)I`. No `Class` parameter is added.
- The two overloads `sum(int,int)` and `sum(int)` differ in the `(II)...` and `(I)...` parts.

In JNI, you look up constructors or instance methods with `GetMethodID`; you look up static methods with `GetStaticMethodID`. These functions require both **name** and **descriptor**, and cannot be substituted for one another merely by changing the signature string.

A class also has a special initialization method `<clinit>` at the bytecode level (`()V`) when needed, but that is not a constructor for use with `GetMethodID`.

### 5.3. Varargs and generic erasure

Java varargs is an array at the descriptor level:

```java
void print(String... words);
```

Descriptor: `([Ljava/lang/String;)V`, with no `...` notation.

For:

```java
java.util.List<String> names;
java.util.List<Integer> list();
```

The field descriptor of `names` is `Ljava/util/List;` and the method descriptor of `list()` is `()Ljava/util/List;`. Generic type arguments are not in this descriptor. Generic information may be stored in the **`Signature`** attribute of the class file, which is a different format. Therefore, do not pass `Ljava/util/List<Ljava/lang/String;>;` to `GetFieldID`.

For `<T extends Number> T echo(T value)`, the erasure of `T` is `Number`, so the descriptor is `(Ljava/lang/Number;)Ljava/lang/Number;`. Some compiler-generated bridge/synthetic methods have their own descriptors: inspect the actual bytecode instead of guessing.

## 6. Decoding a complex descriptor

Consider the string:

```text
([[ILjava/lang/String;J)[[Ljava/lang/Object;
```

Reading order:

1. `(` opens the parameter list.
2. `[[I` → first parameter `int[][]`.
3. `Ljava/lang/String;` → second parameter `String`; must read up to `;`.
4. `J` → third parameter `long`.
5. `)` closes the list.
6. `[[Ljava/lang/Object;` → returns `Object[][]`.

Corresponding Java signature (method name is illustrative only):

```java
Object[][] process(int[][] matrix, String label, long version);
```

Compare:

- `([[I)V`: **one** parameter of type `int[][]`, returns `void`.
- `([I[I)V`: **two** parameters both of type `int[]`, returns `void`.
- `(II)I`: two `int`s back-to-back with no comma.
- `(Ljava/lang/String;I)V`: `String` and `int`, returns `void`.

**Tip:** when you see `L`, read continuously until `;`; when you see `[`, count dimensions then decode the next type; when you see `(`, decode each parameter until `)` then read exactly one return type. `V` is only valid in the return type position.

## 7. Runnable Java 17+ example: printing descriptors and verifying with reflection

We can inspect descriptors **without loading a C library**. JDK 17 provides `Class.descriptorString()` for classes/primitives/arrays and `MethodType.toMethodDescriptorString()` for methods. Use reflection to cross-check against an actual Java method.

Create the file **`DescriptorLab.java`** in an empty directory, without a `package` declaration:

```java
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public final class DescriptorLab {
    private int[] counts = {1, 2};
    private String title = "demo";

    public DescriptorLab() {
    }

    public long compute(int n, String text, int[][] matrix) {
        return n + text.length() + matrix.length;
    }

    public void tags(String... labels) {
        this.title = String.join(",", labels);
    }

    public static final class Item {
    }

    public static Item[] build(String[][] words, long version) {
        return new Item[words.length];
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        System.out.println("int: " + int.class.descriptorString());
        System.out.println("long: " + long.class.descriptorString());
        System.out.println("void: " + void.class.descriptorString());
        System.out.println("String: " + String.class.descriptorString());
        System.out.println("int[][]: " + int[][].class.descriptorString());
        System.out.println("String[][]: " + String[][].class.descriptorString());
        System.out.println("Item[]: " + Item[].class.descriptorString());

        MethodType compute = MethodType.methodType(
                long.class, int.class, String.class, int[][].class
        );
        System.out.println("compute: " + compute.toMethodDescriptorString());

        MethodType build = MethodType.methodType(
                Item[].class, String[][].class, long.class
        );
        System.out.println("build: " + build.toMethodDescriptorString());

        MethodType tags = MethodType.methodType(void.class, String[].class);
        System.out.println("tags: " + tags.toMethodDescriptorString());

        Method actual = DescriptorLab.class.getDeclaredMethod(
                "compute", int.class, String.class, int[][].class
        );
        MethodType reflected = MethodType.methodType(
                actual.getReturnType(), actual.getParameterTypes()
        );
        System.out.println("reflection: " + reflected.toMethodDescriptorString());

        MethodType parsed = MethodType.fromMethodDescriptorString(
                "(ILjava/lang/String;[[I)J",
                DescriptorLab.class.getClassLoader()
        );
        System.out.println(
                "parsed third parameter: " + parsed.parameterType(2).getTypeName()
        );
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 DescriptorLab.java
java DescriptorLab
```

**Exact stdout:**

```text
int: I
long: J
void: V
String: Ljava/lang/String;
int[][]: [[I
String[][]: [[Ljava/lang/String;
Item[]: [LDescriptorLab$Item;
compute: (ILjava/lang/String;[[I)J
build: ([[Ljava/lang/String;J)[LDescriptorLab$Item;
tags: ([Ljava/lang/String;)V
reflection: (ILjava/lang/String;[[I)J
parsed third parameter: int[][]
```

Notable points explained:

- `int.class.descriptorString()` returns `I`; `String.class.descriptorString()` returns `Ljava/lang/String;`; arrays prepend `[` for each dimension.
- The nested class `Item` has internal name `DescriptorLab$Item`, so `Item[]` has descriptor `[LDescriptorLab$Item;`.
- `MethodType.methodType(returnType, argTypes...)` describes the parameters and return type accurately; `toMethodDescriptorString()` produces the method descriptor string.
- `getDeclaredMethod(...)` retrieves the actual `compute` method. The reflection result matches the manually constructed one because they share the same signature.
- `MethodType.fromMethodDescriptorString(...)` parses the string back into a `MethodType` with the given class loader; `parameterType(2)` is the third parameter (`int[][]`).

### 7.1. Reading `.class` files directly with `javap -s`

After `javac` succeeds, run:

```bash
javap -s -p DescriptorLab
```

`-s` prints internal descriptors, `-p` also shows private members. Excerpt of relevant lines (order/other details may also appear):

```text
private int[] counts;
  descriptor: [I

private java.lang.String title;
  descriptor: Ljava/lang/String;

public DescriptorLab();
  descriptor: ()V

public long compute(int, java.lang.String, int[][]);
  descriptor: (ILjava/lang/String;[[I)J

public void tags(java.lang.String...);
  descriptor: ([Ljava/lang/String;)V

public static DescriptorLab$Item[] build(java.lang.String[][], long);
  descriptor: ([[Ljava/lang/String;J)[LDescriptorLab$Item;
```

Match each Java declaration with its `descriptor:` line. In real JNI projects, run `javap -s -p` on the **actual packaged class file** to avoid mismatches due to versions, overloads, generics, or compiler-generated methods. `javap -v -p` additionally shows the constant pool, generic `Signature`, and bridge/synthetic flags.

## 8. When applied in JNI functions

The JNI API signatures (in C form to understand their meaning) include:

```c
jclass FindClass(JNIEnv *env, const char *name);

jfieldID GetFieldID(JNIEnv *env, jclass clazz,
                    const char *name, const char *sig);

jmethodID GetMethodID(JNIEnv *env, jclass clazz,
                      const char *name, const char *sig);

jfieldID GetStaticFieldID(JNIEnv *env, jclass clazz,
                          const char *name, const char *sig);

jmethodID GetStaticMethodID(JNIEnv *env, jclass clazz,
                            const char *name, const char *sig);
```

These are **illustrative API declarations**, not a standalone compilable C file. In JNI C code, actual calls go through `JNIEnv`, for example `(*env)->GetMethodID(env, ...)`. Field IDs look up a **field descriptor**; method IDs look up a **full method descriptor**.

Based on `DescriptorLab` in section 7, this is an **illustrative code snippet inside a JNI function returning `void` with a valid `JNIEnv *env`**, not a standalone native program:

```c
jclass cls = (*env)->FindClass(env, "DescriptorLab");
if (cls == NULL) {
    return;
}

jfieldID field = (*env)->GetFieldID(env, cls, "counts", "[I");
if (field == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jmethodID method = (*env)->GetMethodID(
        env, cls, "compute", "(ILjava/lang/String;[[I)J");
if (method == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jmethodID ctor = (*env)->GetMethodID(
        env, cls, "<init>", "()V");
if (ctor == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jmethodID factory = (*env)->GetStaticMethodID(
        env, cls, "build",
        "([[Ljava/lang/String;J)[LDescriptorLab$Item;");
if (factory == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

(*env)->DeleteLocalRef(env, cls);
```

This snippet only illustrates **ID lookup**. To invoke a method, you must have the object/arguments and use the appropriate `CallLongMethod`, `CallStaticObjectMethod`, etc.; JNI resource, reference, and exception rules still apply.

Compare similar-looking strings used in different positions:

```c
(*env)->FindClass(env, "java/lang/String");         // Class name
(*env)->FindClass(env, "[Ljava/lang/String;");      // Array type
(*env)->GetFieldID(env, cls, "title",
                   "Ljava/lang/String;");          // Field descriptor
```

- `FindClass` takes an **internal** class name or an array signature.
- `GetFieldID` takes a **field name** and **a field descriptor**.
- `GetMethodID` takes a **method name** and **a method descriptor** including the return type.
- `GetStaticFieldID` / `GetStaticMethodID` are used for static members, while the functions without `Static` are used for instance members.
- `NULL` return values must be checked; some failures leave a pending Java exception. Do not use a null ID, do not make further API calls that violate exception-handling rules, and do not clear exceptions arbitrarily.

### 8.1. Why aren't descriptors written using C types?

For example, the C-side JNI function has `JNIEnv *env`, `jobject receiver`, and `jint n`. Yet the descriptor for the Java method `int inc(int n)` is still just `(I)I`. The first two hidden arguments in the C function signature are not arguments passed by the Java caller, so they do not appear in the Java descriptor.

A descriptor is also **not the exported JNI symbol name** from the native library. C symbol names following JNI conventions (or `RegisterNatives`) belong to a separate linking mechanism. `javac -h` helps generate the correct header when implementing native methods.

## 9. Common mistakes when reading type descriptors

| Incorrect | Cause | Correct |
| --- | --- | --- |
| `Ljava.lang.String;` | Using `.` in internal name | `Ljava/lang/String;` |
| `java/lang/String` in `GetFieldID` | Missing `L` and `;` | `Ljava/lang/String;` |
| `L` for `long` | Confusing object prefix with primitive | `J` |
| `[I` for `int[][]` | Missing one array dimension | `[[I` |
| `L[java/lang/String;` | Wrong position of `[` | `[Ljava/lang/String;` |
| `(V)I` | `void` is invalid as a parameter | `()I` if there are no parameters |
| `(I)` | Missing return type | `(I)V`, `(I)I`, ... depending on declaration |
| Passing `sum(II)I` directly as `sig` | Method name must be passed separately | `name="sum"` and `sig="(II)I"` |
| `(jint)jint` | Using JNI C types instead of Java descriptors | `(I)I` |
| `Ljava/util/List<Ljava/lang/String;>;` for a JNI field | Confusing generic `Signature` with field descriptor | `Ljava/util/List;` |
| `(Ljava/lang/String;...)V` | Varargs is an array at JVM level | `([Ljava/lang/String;)V` |
| `FindClass(env,"Ljava/lang/String;")` | Confusing descriptor with `FindClass` class name | `FindClass(env,"java/lang/String")` |

Other errors that are not descriptor syntax mistakes:

- **Wrong static/instance**: you must use `GetMethodID` or `GetStaticMethodID` appropriately.
- **Wrong return type or overload**: descriptors differ even when names are identical.
- **Different class loaders**: two classes with the same name loaded by different loaders are different runtime types. The descriptor string alone does not identify the loader.
- **Mismatched class file version**: Java source changed recently while native code still holds the descriptor from an older version.
- **Not handling exceptions** when a JNI lookup returns `NULL`.
- **Confusing `NoSuchMethodError` with `UnsatisfiedLinkError`**: `GetMethodID` looking up a Java method can throw `NoSuchMethodError` when the signature is wrong, whereas `UnsatisfiedLinkError` relates to loading/linking a native library or native method.

## 10. Self-check exercises

Decode the following strings before looking at the answer column:

| Descriptor | Equivalent Java type/signature |
| --- | --- |
| `[Z` | `boolean[]` |
| `[[[J` | `long[][][]` |
| `Ljava/util/Map$Entry;` | `java.util.Map.Entry` |
| `([[D)V` | `void f(double[][])` |
| `([Ljava/lang/String;I)Z` | `boolean f(String[], int)` |
| `()Ljava/lang/String;` | `String f()` |
| `(Ljava/lang/Object;[I)[Ljava/lang/String;` | `String[] f(Object, int[])` |
| `([[ILjava/util/List;)V` | `void f(int[][], List)` |

The `f` in the answers is a **hypothetical** method name for illustration, because descriptor strings do not store method names. How to construct a descriptor yourself: take each primitive type or `L...;`, prepend `[` for each array dimension, concatenate parameters inside `(...)`, and then append the return type.

## 11. Checklist for JNI work

1. Inspect the **running class file**, using `javap -s -p` to confirm signatures.
2. Primitives are single characters `B C D F I J S Z`; `V` is only for return types.
3. Classes/interfaces use `Linternal/name;`, nested classes use `$` in the binary name.
4. Arrays prepend `[` for each dimension, followed by the element descriptor.
5. Methods use `(parameters-in-order)return-type`, with no names or commas.
6. Use arrays for varargs, erased types for generics, and `<init>` returning `V` for constructors.
7. Distinguish `FindClass` (internal name or array signature) from `GetFieldID`/`GetMethodID` (descriptors).
8. Check instance/static, class loader, JNI messages, and `NULL`/exceptions before using IDs.

## Official references

- [Java Virtual Machine Specification 17 — Field Descriptors (`4.3.2)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.2).
- [Java Virtual Machine Specification 17 — Method Descriptors (`4.3.3)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3).
- [JNI Specification 17 — Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html).
- [JNI Specification 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html).
- [Oracle JDK 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [Oracle JDK 17 — Class.descriptorString()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#descriptorString()) and [MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html).