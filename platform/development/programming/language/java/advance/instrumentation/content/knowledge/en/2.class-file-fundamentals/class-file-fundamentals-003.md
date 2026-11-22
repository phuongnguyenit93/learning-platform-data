# Internal Class Names, Field, Method, and Array Descriptors in JVM Class Files

When reading a `.class` file with `javap` or writing instrumentation tools with ASM, we do not work directly with Java source type syntax. The JVM uses an **internal name** to identify classes/interfaces and a **descriptor** to describe field types, parameter lists, and method return types. Correctly distinguishing these three forms is essential for reading the constant pool, looking up members, and generating valid bytecode.

After this lesson, you should be able to convert Java types to descriptors and vice versa, read method descriptors from left to right, understand how arrays and nested classes are encoded, and use `owner/name/descriptor` correctly when instrumenting bytecode.

## 1. Three Easily Confused Representations

| Context | Example | Meaning |
| --- | --- | --- |
| Name in Java code | `java.lang.String` | Familiar syntax in source code |
| *Binary name* | `java.util.Map$Entry` | Binary name of the nested class `Map.Entry` |
| *Internal name* | `java/lang/String`, `java/util/Map$Entry` | Binary name with package-separating `.` replaced by `/` |
| *Field descriptor* | `Ljava/lang/String;`, `[I` | Encodes **a single type** |
| *Method descriptor* | `(Ljava/lang/String;[I)V` | Encodes **parameters and return type** |

For example, `java.lang.String` is a regular class name; `java/lang/String` is an internal name; and `Ljava/lang/String;` is the descriptor of the `String` reference type. The leading `L` and trailing `;` are **part of the descriptor**, not part of the internal name.

For nested classes:

- In source code: `java.util.Map.Entry`.
- Binary name: `java.util.Map$Entry`.
- Internal name: `java/util/Map$Entry`.
- Field descriptor: `Ljava/util/Map$Entry;`.

The `$` character can appear in a binary name because the compiler encodes member classes, local classes, or anonymous classes. **Do not replace `$` with `/` or `.`** when constructing an internal name. A class in the default package such as `Example` has internal name `Example` and object descriptor `LExample;`.

**Where is each name used?** In a class file, a `CONSTANT_Class_info` entry representing a class/interface normally uses an internal name, such as `java/lang/String`; if it represents an **array type**, the name stored there has the form of an array descriptor, such as `[[I` or `[Ljava/lang/String;`. The fields `field_info.descriptor_index` and `method_info.descriptor_index` point to a UTF-8 string in the constant pool describing the field/method. Reference entries `CONSTANT_Fieldref_info`, `CONSTANT_Methodref_info`, and `CONSTANT_InterfaceMethodref_info` also pair the member name with its descriptor through `CONSTANT_NameAndType_info`.

## 2. Descriptor Grammar and Primitive Type Code Table

The core JVM syntax can be read in a condensed form:

~~~text
FieldDescriptor   ::= FieldType
FieldType         ::= BaseType | ObjectType | ArrayType
BaseType          ::= B | C | D | F | I | J | S | Z
ObjectType        ::= L InternalClassName ;
ArrayType         ::= [ FieldType

MethodDescriptor  ::= ( FieldType* ) ReturnType
ReturnType        ::= FieldType | V
~~~

In the grammar above, the text between `L` and `;` must be the internal name of the class/interface. The `[` character can repeat to represent multiple array dimensions. The parentheses in a method descriptor are required characters; there are no commas, spaces, or parameter names.

| Code | Java Type | Code | Java Type |
| --- | --- | --- | --- |
| `B` | `byte` | `C` | `char` |
| `D` | `double` | `F` | `float` |
| `I` | `int` | `J` | `long` |
| `S` | `short` | `Z` | `boolean` |

Remember two points: `J` represents `long` (not `L`), while `L` begins an object type. `V` means `void`, but is **only allowed in the return type position of a method descriptor**. A field, parameter, or array element cannot have descriptor `V`.

Examples of **field descriptors**:

| Type Declaration | Descriptor | How to Read |
| --- | --- | --- |
| `int` | `I` | An integer value |
| `long` | `J` | A long value |
| `boolean` | `Z` | A boolean value |
| `String` | `Ljava/lang/String;` | Reference to `java.lang.String` |
| `Object` | `Ljava/lang/Object;` | Reference to `java.lang.Object` |
| `Runnable` | `Ljava/lang/Runnable;` | Reference to an interface, same syntax as a class |
| `Map.Entry` | `Ljava/util/Map$Entry;` | Reference to a nested class |

Field names such as `count` or `values` **are not part of the descriptor**. For example, `private int count;` has name `count` and descriptor `I`, stored in their respective fields in the `field_info` structure.

## 3. Descriptors for Array Types

Each `[` character at the **beginning** of a descriptor adds **one array dimension**, followed by the descriptor of the final element type:

| Java | Array descriptor |
| --- | --- |
| `int[]` | `[I` |
| `long[][]` | `[[J` |
| `double[][][]` | `[[[D` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |
| `Map.Entry[]` | `[Ljava/util/Map$Entry;` |
| `int[][][]` | `[[[I` |

For example, `[[Ljava/lang/String;` is read in three steps: the first `[` is dimension 1, the second `[` is dimension 2, and `Ljava/lang/String;` is the `String` element type; the result is `String[][]`. With `[[I`, the final element type is `int`, so this is `int[][]`.

Several important rules:

1. **Arrays are still reference types**, even when the elements are primitives. The descriptor of `int[]` is `[I`, not `L[I;`.
2. Do not put `[]` at the end: `Ljava/lang/String;[]` is invalid. Array dimensions must come **at the beginning**: `[Ljava/lang/String;`.
3. Object arrays use `[L...;`, and primitive arrays use `[` followed by the primitive code. `[V` is invalid because there is no `void` array.
4. According to the JVM Specification, a valid array type descriptor has **at most 255 dimensions**. This is a limit of the JVM format, not a recommendation for designing multi-dimensional arrays.

Note the difference between the reflection API and descriptors: `String[][].class.getName()` returns `[[Ljava.lang.String;` (with dots in the class name inside the array's binary name string), whereas `String[][].class.descriptorString()` returns `[[Ljava/lang/String;` matching class file descriptor syntax. Therefore, do not take the string from an array's `Class.getName()` and assume it is always a JVM descriptor.

## 4. Method Descriptors: Parameters and Return Types

General form:

~~~text
(<parameter-descriptor-1><parameter-descriptor-2>...)<return-descriptor>
~~~

Between `(` and `)` are **the parameter types in their exact declaration order**; after `)` is **a single return type** or `V`. When there are no parameters, the parentheses are `()`. Do not include the method name, parameter names, `throws`, `public/static` modifiers, or generic type arguments in the descriptor.

| Java Method | Descriptor |
| --- | --- |
| `void run()` | `()V` |
| `int doubleIt(int value)` | `(I)I` |
| `String trim(String input)` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `long sum(int[] values, long seed)` | `([IJ)J` |
| `String[][] merge(String[] a, int[][] b)` | `([Ljava/lang/String;[[I)[[Ljava/lang/String;` |
| `public static void main(String[] args)` | `([Ljava/lang/String;)V` |

Reading `(IDLjava/lang/Thread;)Ljava/lang/Object;`:

1. Encounter `(`: start of parameters.
2. `I`: first parameter is `int`.
3. `D`: second parameter is `double`.
4. `Ljava/lang/Thread;`: third parameter is `java.lang.Thread`.
5. Encounter `)`: end of parameter list.
6. `Ljava/lang/Object;`: return value is `java.lang.Object`.

This corresponds to `Object m(int i, double d, Thread t)`. Because `L...;` has variable length, you must read up to `;` instead of treating each character as a type. When encountering `[`, continue reading through the end of the element descriptor to determine **a single array parameter**.

**The `this` receiver is not written into the method descriptor.** An instance method `String name()` still has descriptor `()Ljava/lang/String;`, even though when invoked with `invokevirtual` the JVM also consumes a receiver reference from the operand stack. A `static` method with the same parameter list and return type has the exact same descriptor; the `static` modifier is represented via access flags, not via the descriptor.

**Constructors** in a class file have the special name `<init>` and return descriptor `V`. The constructor `Example(int x)` corresponds to `<init>(I)V`. The class initializer `<clinit>`, if present, uses descriptor `()V`. These two names belong to the **name** part, while `(I)V` or `()V` is the **descriptor** part.

### The 255-Unit Parameter Limit

The JVM limits the total *parameter length* of a method descriptor to at most **255 units**. `long` and `double` each contribute **2 units**; all other types, including arrays and references, contribute **1 unit**. For instance/interface methods, **1 additional unit is counted for `this`**, even though `this` does not appear in the descriptor string. Therefore, an instance method can have at most 254 `int` parameters, or fewer if `long`/`double` are used. This limit also explains why adding parameters when instrumenting a method with a very large signature can produce an invalid class file.

## 5. Descriptors and Generic Signatures Are Two Separate Layers of Information

JVM descriptors express types after **type erasure**, so they do not retain generic type arguments such as `String` in `List<String>`. For example:

~~~java
private java.util.List<String> names;

public java.util.List<String> copy(java.util.List<String> input) {
    return input;
}
~~~

- Field descriptor of `names`: `Ljava/util/List;`.
- Method descriptor of `copy`: `(Ljava/util/List;)Ljava/util/List;`.
- The `<String>` information can be preserved in the `Signature` attribute of the class file, with its **own signature grammar**.

Do not pass `Ljava/util/List<Ljava/lang/String;>;` where a **field descriptor** is expected: that is generic signature syntax, not a valid descriptor. Similarly, `T...;` has meaning in a generic signature but is not a primitive/object/array type code of a field descriptor. When looking up methods via bytecode APIs, you must use the appropriate erased descriptor.

If a generic type variable has no explicit bound, its erasure is normally `Object`; if it has a class/interface bound, it is erased to the appropriate first bound. Thus, to derive the descriptor of a generic method correctly, you need the erased signature rather than copying `<T>` syntax verbatim from source.

## 6. Inspecting Descriptors with JDK Tools

Create a file named `DescriptorWalkthrough.java` with the following code. This example uses only JDK 17+ APIs and requires no external libraries:

~~~java
import java.lang.invoke.MethodType;
import java.util.Map;

public class DescriptorWalkthrough {
    public static void main(String[] args) {
        System.out.println(Map.Entry.class.getName());
        System.out.println(Map.Entry.class.getName().replace('.', '/'));
        System.out.println(String.class.descriptorString());
        System.out.println(int[][].class.descriptorString());
        System.out.println(String[][].class.getName());
        System.out.println(String[][].class.descriptorString());

        MethodType type =
                MethodType.methodType(long.class, int[].class, long.class);
        System.out.println(type.descriptorString());

        MethodType parsed = MethodType.fromMethodDescriptorString(
                "([IJ)J", DescriptorWalkthrough.class.getClassLoader());
        System.out.println(parsed.parameterCount());
    }
}
~~~

Compile and run:

~~~bash
javac DescriptorWalkthrough.java
java DescriptorWalkthrough
~~~

Exact stdout:

~~~text
java.util.Map$Entry
java/util/Map$Entry
Ljava/lang/String;
[[I
[[Ljava.lang.String;
[[Ljava/lang/String;
([IJ)J
2
~~~

Meaning: `Class.descriptorString()` returns the exact descriptor for primitives, objects, and arrays; `MethodType.descriptorString()` gives the descriptor of a **method type**; `MethodType.fromMethodDescriptorString(...)` parses a method descriptor and resolves reference types using the provided class loader. For classes that cannot be found during descriptor parsing, type resolution may fail.

To see the information compiled directly into a class file, create `BytecodeFixture.java`:

~~~java
public class BytecodeFixture {
    private String[] labels;
    private int[][] points;

    public static long sum(int[] values, long initial) {
        long result = initial;
        for (int value : values) {
            result += value;
        }
        return result;
    }

    public String[][] wrap(String[] values) {
        return new String[][] { values };
    }
}
~~~

Run:

~~~bash
javac BytecodeFixture.java
javap -p -s BytecodeFixture
javap -v BytecodeFixture
~~~

In the `javap -p -s` output, look for the following descriptor lines (next to the corresponding field/method names):

~~~text
labels  -> [Ljava/lang/String;
points  -> [[I
BytecodeFixture() -> ()V
sum(int[], long) -> ([IJ)J
wrap(String[]) -> ([Ljava/lang/String;)[[Ljava/lang/String;
~~~

The lines above are a **condensed reference table**, not a verbatim copy of `javap`'s output format. Running `javap -v` additionally displays the constant pool, access flags, `descriptor:`, and bytecode instructions to verify the relationship between names, descriptors, and call instructions.

## 7. Direct Application When Instrumenting with ASM

ASM uses the exact JVM name forms. In calls such as `visitFieldInsn` and `visitMethodInsn`, you must keep these separate:

- `owner`: internal name of the class owning the member, e.g., `java/lang/System`.
- `name`: member name, e.g., `out` or `println`.
- `descriptor`: field descriptor if it is a field, or method descriptor if it is a method.
- `opcode`/`isInterface`: how the field is accessed or method is invoked; these two values are **not encoded into the descriptor**.

The following ASM code snippet illustrates bytecode equivalent to `System.out.println("Hello");`. This is an **illustrative API snippet** requiring a project with the ASM library and a valid `MethodVisitor mv`; it is not a standalone Java program:

~~~java
mv.visitFieldInsn(
        Opcodes.GETSTATIC,
        "java/lang/System",
        "out",
        "Ljava/io/PrintStream;");

mv.visitLdcInsn("Hello");

mv.visitMethodInsn(
        Opcodes.INVOKEVIRTUAL,
        "java/io/PrintStream",
        "println",
        "(Ljava/lang/String;)V",
        false);
~~~

Operand stack trace: `GETSTATIC` pushes the `PrintStream` reference onto the stack; `LDC` pushes the `String`; `INVOKEVIRTUAL` consumes the receiver + one `String` and returns `void`. The descriptor of field `out` is `Ljava/io/PrintStream;`, while the descriptor of `println(String)` is `(Ljava/lang/String;)V`. Mistaking `owner` for `Ljava/io/PrintStream;`, mistaking a field type for a method descriptor, or using `java.io.PrintStream` where an internal name is expected can cause the tool to emit malformed or unresolvable references.

To avoid error-prone string concatenation, ASM provides `org.objectweb.asm.Type` with methods such as `Type.getInternalName(SomeClass.class)`, `Type.getDescriptor(SomeClass.class)`, and `Type.getMethodDescriptor(...)`. These are **ASM library** APIs, not part of the JDK. Verification is still necessary because a syntactically valid descriptor does not guarantee that the call uses the right opcode, receiver, operand stack types, or StackMap frames. When instrumenting an existing call, read the original descriptor, determine the parameter order and return type, and then maintain the appropriate stack state.

### Analyzing Common Errors

| Symptom | What to Check |
| --- | --- |
| `NoSuchMethodError` | Are owner + name + **full method descriptor** (including return type) all exact? |
| `NoSuchFieldError` | Are owner + field name + field descriptor all exact? |
| `ClassNotFoundException` when using reflection | `Class.forName("java.lang.String")` requires a binary name with `.`, not `java/lang/String` |
| `ClassFormatError` or `VerifyError` | Is the descriptor valid; are the call instructions, operand stack, local variables, and frames compatible? |
| Instrumentation misses an overloaded method | Does the filter match on **name + descriptor** instead of just the name? |

An overloaded method named `process` may have `(I)V` and `(Ljava/lang/String;)V`; matching only `process` is not enough. In Java source code you cannot overload solely by return type, but **method descriptors at the JVM level still include the return type**, so it must be preserved when looking up or calling at the bytecode level.

## 8. Quick Conversion Checklist and Syntax Errors

**From Java type to field descriptor:** (1) primitive → single-letter code; (2) class/interface → `L` + internal name + `;`; (3) array → prepend `[` for each dimension. For methods, concatenate the parameter descriptors inside `(...)` and then append the return type descriptor (or `V`).

**From descriptor to Java:** (1) if it starts with `[`, count the dimensions; (2) read the primitive code or `L...;` pair; (3) convert `/` in the internal name back to `.` when displaying the full name; (4) if it is a method, split the parts before and after `)`. Do not split `L...;` at `/`, because everything from `L` to `;` is **a single type**.

| String | Assessment |
| --- | --- |
| `Ljava/lang/String;` | Valid: object field descriptor |
| `[Ljava/lang/String;` | Valid: array field descriptor |
| `([I)V` | Valid: method taking `int[]` and returning `void` |
| `java.lang.String` | Neither an internal name nor a field descriptor |
| `Ljava.lang.String;` | Invalid: class names in descriptors must use `/` between packages |
| `V` as field/parameter | Invalid: `void` is only valid as a return type |
| `[V` | Invalid: there is no `void[]` |
| `(I, J)V` | Invalid: descriptors have no commas or spaces |
| `()Ljava/lang/String` | Invalid: missing `;` terminating the object type |
| `Ljava/util/List<Ljava/lang/String;>;` | Not a field descriptor; this is generic signature syntax |

A valid descriptor must **consume the entire string** with no trailing characters. For example, `I;` is invalid because `I` is already a complete field descriptor; `;` is only used to terminate `L...;`. There is no rule for appending `;` after a primitive code or after a primitive array such as `[[I`.

## 9. Self-Check Exercises

1. Decode `(IJ[Ljava/lang/String;)V` into its parameter list and return type.
2. Write the descriptor for `static String[][] combine(int[] a, boolean enabled, Map.Entry<String, Integer> e)`.
3. Determine the field descriptors for `double[][]`, `Thread[]`, and `long[][][]`.
4. Given the call `visitMethodInsn(INVOKESTATIC, "java/lang/System", "nanoTime", "()J", false)`, how many parameters does the method take and what type does it return?
5. Explain why `String[].class.getName()` and `String[].class.descriptorString()` differ.

**Reference Answers:**

1. `int`, `long`, `String[]` → `void`. The `[Ljava/lang/String;` part is a single parameter.
2. `([IZLjava/util/Map$Entry;)[[Ljava/lang/String;`. The type arguments `<String, Integer>` are erased in the descriptor.
3. `[[D`, `[Ljava/lang/Thread;`, `[[[J`, respectively.
4. No parameters; returns `long` (`J`). Because it is `INVOKESTATIC`, there is no `this` receiver.
5. `getName()` returns the binary name of the array class (e.g., `[Ljava.lang.String;`); `descriptorString()` returns the class file descriptor syntax (`[Ljava/lang/String;`).

To study further from the official specification, consult *Java Virtual Machine Specification (Java SE 21)*, [§4.2.1 — Binary Class and Interface Names](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.2.1), [§4.3.2 — Field Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.2), and [§4.3.3 — Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3).