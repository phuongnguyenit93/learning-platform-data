# Type, Method, and Array Class Descriptors in the JVM

## 1. What Problem Do Descriptors Solve?

In Java source code, we write `int`, `java.lang.String`, `String[][]`, or `String join(int, String[])`. In bytecode and the `.class` structure, the JVM needs a way to represent **data types** using short strings with a well-defined syntax so each type can be read unambiguously, independent of source-code formatting. That string is called a **descriptor**.

There are two main forms:

- **Field descriptor**: describes **a single type** of a field, variable, parameter, or value. For example: `I` is `int`, `Ljava/lang/String;` is `java.lang.String`, `[[I` is `int[][]`.
- **Method descriptor**: describes **the ordered list of parameter types and the return type**. For example: `(I[Ljava/lang/String;)V` is a method taking `int` and `String[]`, and returning `void`.

A descriptor **does not contain** variable names, method names, parameter names, generic type arguments, access modifiers, `throws` clauses, or method body contents. The method name and the descriptor are two separate pieces of information in a class file. This is the foundation for reading `javap -s` output, distinguishing overloaded methods, using reflection/method handles, and understanding how the JVM links references to classes.

> Make the distinction clear from the start: `java.lang.String` is the *binary name* widely used in Java APIs; `java/lang/String` is the *internal name* form in class files; `Ljava/lang/String;` is the descriptor for that reference type.

## 2. Field Descriptor Syntax

According to JVMS §4.3.2, a field descriptor represents a single type:

```text
FieldType = BaseType | ObjectType | ArrayType
BaseType  = B | C | D | F | I | J | S | Z
ObjectType = L InternalClassName ;
ArrayType  = [ FieldType
```

Primitive type mapping table:

| Java Type | Descriptor | Mnemonic |
|---|---|---|
| `byte` | `B` | byte |
| `char` | `C` | char |
| `double` | `D` | double |
| `float` | `F` | float |
| `int` | `I` | int |
| `long` | `J` | long, uses the symbol `J` |
| `short` | `S` | short |
| `boolean` | `Z` | boolean |

`V` represents `void` and is **only valid as the return type of a method descriptor**; `V` is not a valid descriptor for a field, parameter, or array element.

### Class or Interface Types

The syntax is `L` + internal name + `;`:

| Source Type | Field Descriptor |
|---|---|
| `String` | `Ljava/lang/String;` |
| `java.lang.Object` | `Ljava/lang/Object;` |
| `java.util.List` | `Ljava/util/List;` |
| `java.util.Map.Entry` | `Ljava/util/Map$Entry;` |

In an internal name, `/` separates packages; the `$` symbol typically appears in the binary name of a nested class. Both `L` and `;` are mandatory parts of a reference descriptor; writing only `java/lang/String` is an internal name, not yet a field descriptor.

Descriptors do not represent generic type details. For example, after type *erasure*, `List<String>` and `List<Integer>` share the same descriptor `Ljava/util/List;`. Generic information may be preserved in the `Signature` attribute, which has a different grammar from descriptors.

## 3. Array Class Descriptors

Each `[` represents **one array dimension**; following the `[` characters is the descriptor of the ultimate element type.

| Java Type | Descriptor |
|---|---|
| `int[]` | `[I` |
| `long[][]` | `[[J` |
| `boolean[][][]` | `[[[Z` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |
| `java.util.Map.Entry[][]` | `[[Ljava/util/Map$Entry;` |

How to read `[[Ljava/lang/String;`: the two `[` characters indicate a two-dimensional array; `Ljava/lang/String;` indicates the ultimate element is `String`. Stripping one `[` yields the direct component type: `String[][]` has a component type of `String[]`; only after stripping the second `[` do we reach `String`.

Common points of confusion:

- `String[]` and `String[][]` are **two different runtime array classes**, corresponding to two distinct `Class<?>` objects. The JVM creates array classes on demand; there is no separate source file named `[Ljava/lang/String;`.
- For reference arrays, the array class has a defining loader corresponding to the defining loader of the reference element type; arrays of primitive types are associated with the bootstrap loader (`getClassLoader()` may return `null`). Having the same descriptor is not enough to uniquely identify a runtime class if the same reference name is defined by different class loaders.
- Java arrays are objects; an array class has `java.lang.Object` as its direct superclass and implements `java.lang.Cloneable` and `java.io.Serializable`. These traits do not appear in the descriptor string.
- Multidimensional arrays in Java are actually **arrays of arrays**; for example, `new int[2][]` and `new int[2][3]` both have the runtime type `int[][]`, i.e., descriptor `[[I`. A descriptor describes the **type**, not the size or element count.
- The JVMS limits array type field descriptors to at most **255 dimensions**; this is a class file structural limit, not a normal declaration syntax meant for application code.

## 4. Method Descriptor Syntax

According to JVMS §4.3.3:

```text
MethodDescriptor = ( ParameterType* ) ReturnType
ParameterType    = FieldType
ReturnType       = FieldType | V
```

Each parameter type is written **contiguously**, with no commas and no spaces, all enclosed in parentheses. Immediately after `)`, there must be **exactly one** return type, even when the method returns `void`.

| Java Declaration | Method Descriptor |
|---|---|
| `void ping()` | `()V` |
| `int square(int n)` | `(I)I` |
| `boolean contains(String s)` | `(Ljava/lang/String;)Z` |
| `String format(int n, String[] tags)` | `(I[Ljava/lang/String;)Ljava/lang/String;` |
| `long[][] convert(byte[] input, double factor)` | `([BD)[[J` |
| `void accept(String... values)` | `([Ljava/lang/String;)V` |

Example of splitting `(I[Ljava/lang/String;)Ljava/lang/String;`:

1. `(`: starts the parameter list.
2. `I`: the first parameter is `int`.
3. `[Ljava/lang/String;`: the second parameter is `String[]`; the `;` character terminates the reference element's descriptor.
4. `)`: ends the parameter list.
5. `Ljava/lang/String;`: the return type is `String`.

**There is no method name in a descriptor.** Both declarations `int sum(int a, int b)` and `int add(int x, int y)` have `(II)I`. In a class file, the name combined with the descriptor identifies a method; having two methods with the same parameters but different return types does not form a valid overload in Java source code.

**`this` is not recorded in a descriptor.** The instance method `String label(int id)` still has `(I)Ljava/lang/String;`, even though the JVM needs a receiver object at call time. Similarly, the constructor `Person(String name)` has the special name `<init>` in bytecode and the descriptor `(Ljava/lang/String;)V`; `V` here does not mean the constructor is declared to return `void` in source code. The static initializer `<clinit>` uses `()V`.

**Varargs are arrays** in descriptors: `void log(String... lines)` and `void log(String[] lines)` have the same descriptor `([Ljava/lang/String;)V` (which is why both cannot be declared as overloads). `throws IOException` does not change the descriptor; exceptions are separate method metadata.

For method descriptors, the JVMS also specifies that the total parameter length cannot exceed 255 *units*: `long`/`double` contribute two units, other types one unit; for instance methods, one extra unit is counted for the receiver. This is a bytecode format/verification constraint, not syntax visible in source code.

## 5. Why Are Descriptors Important When Reading Bytecode?

In a class file, `field_info` and `method_info` reference descriptor strings in the constant pool. Symbolic references to fields or methods are also paired with a name and descriptor through the corresponding constant pool structures. This allows the JVM to know the exact data types and signatures to link.

Consider the following example code:

```java
class Example {
    String[][] names;

    int count(String[] values) {
        return values.length;
    }
}
```

In the class file, the field `names` has descriptor `[[Ljava/lang/String;` and the method `count` has descriptor `([Ljava/lang/String;)I`. We can inspect this after compilation using `javap -s -p Example`. The corresponding lines will look like:

```text
java.lang.String[][] names;
  descriptor: [[Ljava/lang/String;

int count(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)I
```

`javap` displays declarations in a human-readable form while also printing the actual descriptor from the class file. Add `-c` as in `javap -c -p Example` if you need to inspect bytecode instructions; `-s` is the option focused on descriptors.

Descriptors follow Java generics *erasure*. For example:

```java
java.util.List<String> normalize(java.util.List<Integer> input)
```

The descriptor of the method above is:

```text
(Ljava/util/List;)Ljava/util/List;
```

`String` and `Integer` are generic type arguments, so they are absent from this descriptor. Type variables with an upper bound are also erased to the appropriate bound type (or `Object` if there is no explicit bound). If you need type arguments at runtime, you must inspect generic metadata when available, such as `Signature` and reflection's `getGenericParameterTypes()`; do not infer them from the descriptor.

When the compiler generates a **bridge method** to preserve compatibility after erasure, the bridge is a real method in the class file with its own descriptor; this is why `javap -v` output sometimes shows more methods than appear directly in the source code.

## 6. How Do Reflection Array Class Names Differ from Descriptors?

Java has several APIs that return **different naming formats**; do not blindly convert between them by replacing `.` with `/`.

| Java 17 Expression | Result |
|---|---|
| `String.class.getName()` | `java.lang.String` |
| `String.class.descriptorString()` | `Ljava/lang/String;` |
| `int.class.getName()` | `int` |
| `int.class.descriptorString()` | `I` |
| `String[][].class.getName()` | `[[Ljava.lang.String;` |
| `String[][].class.getTypeName()` | `java.lang.String[][]` |
| `String[][].class.descriptorString()` | `[[Ljava/lang/String;` |
| `String[][].class.getComponentType().descriptorString()` | `[Ljava/lang/String;` |

A subtle detail: `Class.getName()` for **reference arrays** produces an array name form with `[` and `L...;`, but uses **dots** in the element name (`[[Ljava.lang.String;`); class-file descriptors use **slashes** (`[[Ljava/lang/String;`).

When obtaining a `Class<?>` via `Class.forName`:

- `Class.forName("java.lang.String")`: regular class, uses the binary name.
- `Class.forName("[[Ljava.lang.String;")`: `String[][]` array class, uses the name format returned by `Class.getName()` for arrays.
- `Class.forName("[[I")`: primitive `int[][]` array class.
- `Class.forName("Ljava/lang/String;")` and `Class.forName("[Ljava/lang/String;")` **are not valid ways to pass names** for those classes.

In Java 17, `Class.descriptorString()` is the direct way to get a type descriptor, while `java.lang.invoke.MethodType.descriptorString()` provides a method descriptor. `MethodType.fromMethodDescriptorString(descriptor, loader)` parses a method descriptor back into a `MethodType` and resolves reference class names using the provided loader.

## 7. Standalone Runnable Java 17 Example

Create `DescriptorDemo.java`:

```java
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class DescriptorDemo {
    static String format(int id, String[] tags) {
        return id + ":" + tags.length;
    }

    public static void main(String[] args) throws Exception {
        System.out.println(int.class.descriptorString());
        System.out.println(String.class.descriptorString());
        System.out.println(String[][].class.descriptorString());
        System.out.println(String[][].class.getName());
        System.out.println(
                String[][].class.getComponentType().descriptorString());

        Method method = DescriptorDemo.class.getDeclaredMethod(
                "format", int.class, String[].class);
        MethodType type = MethodType.methodType(
                method.getReturnType(), method.getParameterTypes());
        System.out.println(type.descriptorString());

        Class<?> arrayClass = Class.forName("[[Ljava.lang.String;");
        System.out.println(arrayClass == String[][].class);

        MethodType parsed = MethodType.fromMethodDescriptorString(
                type.descriptorString(),
                DescriptorDemo.class.getClassLoader());
        System.out.println(parsed.parameterCount());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac DescriptorDemo.java
java DescriptorDemo
```

Exact stdout:

```text
I
Ljava/lang/String;
[[Ljava/lang/String;
[[Ljava/lang/String;
[Ljava/lang/String;
(I[Ljava/lang/String;)Ljava/lang/String;
true
2
```

Meaning:

- The first five lines contrast a primitive, a class, a two-dimensional array, the `getName()` format, and the component type.
- The method descriptor line is generated from the `String` return type and the two parameters `int` and `String[]`. Because `format` is static, there is no receiver to confuse with a parameter.
- The `true` value shows that the array name string from `getName()` can be passed to `Class.forName` to obtain the exact same `Class` object.
- `2` is the **method parameter count**, distinct from the number of array dimensions and the number of characters in the descriptor.

Inspect the compiled metadata directly:

```bash
javap -s -p DescriptorDemo
```

In the output, the `format` method will include the line:

```text
descriptor: (I[Ljava/lang/String;)Ljava/lang/String;
```

Note: `MethodType` represents a parameter list and return type; when using a method handle for an instance method, the specific method handle kind may include the receiver in the *handle's method type*. That does not change the descriptor rules for the method declared in the class file.

## 8. Descriptors, Names, and Class Loaders During Type Linking

A descriptor tells the JVM **what kind of type is needed**, but a reference such as `Lcom/example/Plugin;` still has to be resolved within a **class loader context**. The JVM does not treat two classes with the same binary name created by two different defining class loaders as the same runtime type. Therefore, two `Class<?>` objects can have identical `descriptorString()` values yet evaluate to `false` with `==`.

For an array `[Lcom/example/Plugin;`, the reference element type `com.example.Plugin` is also subject to this rule. Two different loaders can lead to two different array classes even though the descriptor string is identical. Conversely, the array descriptor `[[I` contains only the primitive `int`, so there is no user class name to resolve.

Key points when working with bytecode or dynamic APIs:

1. Use **descriptors** to understand signatures at the JVM level; use proper **binary names** when calling APIs that expect class names, such as `Class.forName`.
2. When parsing a method descriptor, step through one type at a time according to the grammar. You cannot split parameters by commas (descriptors have no commas) or take one character at a time (an object type spans multiple characters up to `;`).
3. When turning a descriptor into a runtime `Class`/`MethodType`, account for the loader that can resolve the referenced class; having the descriptor string alone does not guarantee the class exists or is accessible to the current loader.
4. Do not treat descriptors as storage for generic information, parameter names, nullability, or annotations.

## 9. How to Read Descriptors Quickly and Common Mistakes

A practical reading procedure:

1. If the string starts with `(`, read it as a **method descriptor**: parse parameters sequentially up to `)`, then parse exactly one return type.
2. For each type: `B/C/D/F/I/J/S/Z` is a primitive; `L` requires reading up to `;`; each `[` adds one array dimension, followed by parsing **one** element type.
3. Convert `/` in internal names to dots for package names when explaining in Java terms; keep `$` when you need the exact binary name of a nested class.
4. Verify that `V` appears only as a method return type, and ensure there are no trailing characters after the final type.

| Common Mistake | Why It Is Wrong | Correct Form |
|---|---|---|
| Writing `Lint;` | `int` is a primitive, not a class | `I` |
| Writing `Ljava.lang.String;` in a class-file descriptor | Internal names use `/` | `Ljava/lang/String;` |
| Forgetting `;` after an object type | No delimiter marks where the reference type ends | `Ljava/lang/String;` |
| Writing `[V` | No `void[]` array exists | Arrays require a valid element type such as `[I` |
| Writing `(I, J) V` | Descriptors have no commas or spaces | `(IJ)V` |
| Writing `(String[])String` | That is source-like notation, not a descriptor | `([Ljava/lang/String;)Ljava/lang/String;` |
| Including the receiver in an instance descriptor | The `this` receiver is handled implicitly by the JVM | `int size()` → `()I` |
| Thinking `List<String>` keeps `String` in the descriptor | Generic arguments undergo erasure | `Ljava/util/List;` |

### Self-Check

Try decoding these before checking the answers:

1. `[[D` describes which type?
2. `(Ljava/lang/String;[[I)Z` describes which signature?
3. What is the descriptor of `void print(long id, String... labels)`?
4. What is the descriptor of a field of type `java.util.Map<String, Integer>[]`?
5. What is the descriptor of `Object[][] build(byte[] bytes, double factor)`?

**Answers:**

1. `double[][]`.
2. A method taking `String` and `int[][]`, returning `boolean`.
3. `(J[Ljava/lang/String;)V`, because varargs are represented as an array.
4. `[Ljava/util/Map;`, because the `String` and `Integer` arguments undergo erasure.
5. `([BD)[[Ljava/lang/Object;`: `[B` is `byte[]`, `D` is `double`, and `[[Ljava/lang/Object;` is `Object[][]`.

## 10. Summary and Official References

- **Primitive types:** `B C D F I J S Z`; `V` is only for the `void` return type.
- **Class/interface:** `L` + internal name + `;`.
- **Array:** one `[` per dimension, followed by the element type descriptor.
- **Method:** `(` + concatenated parameter descriptors + `)` + return descriptor.
- **Class loader:** a descriptor is a syntactic description; runtime identity also depends on where and how the class name is resolved.

Official references:

- [Java Virtual Machine Specification, §4.2–4.3: Names and Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3).
- [Java SE 17 `Class.descriptorString()`, `getName()`, and `getComponentType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 `MethodType` and `fromMethodDescriptorString`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html).