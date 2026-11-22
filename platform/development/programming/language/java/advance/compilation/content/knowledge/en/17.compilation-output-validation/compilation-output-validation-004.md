# Comparing Generics in Signature with Post-Erasure Descriptors Using javap

When compiling Java with **generics**, the `.class` file usually contains **two ways of describing types** for the same field, method, or class:

- **JVM descriptor**: type description at the JVM level actually used to link fields, methods, and execute bytecode. Descriptors use types after **type erasure**, not retaining type arguments such as `String` in `List<String>`.
- **`Signature` attribute**: additional metadata in the class file recording the generic type info of the **declaration**: type variables, bounds, parameterized types, wildcards, generic methods, or generic superclasses. Java reflection, compilers, and bytecode analysis tools can rely on this metadata to present detailed type information.

From this, two conclusions must be held simultaneously: **generic type arguments are largely erased from descriptors and execution mechanisms**, yet **declarative generic information can be retained in the `Signature` attribute**. Saying “generics vanish completely after compiling” is inaccurate; saying “the JVM uses `Signature` to check each element of `List<String>` at runtime” is also wrong.

The lesson's goal is **validating compilation outputs** using `javac`, `javap -s`, `javap -v`, the Java Reflection API, and comparing bridge methods. Examples are compatible with **Java 17+**; key outputs were verified with **OpenJDK 21**.

## 1. Distinguishing Three Concepts Named “Signature”

In the Java context, the word “signature” can refer to different things:

| Term | Nature | Contains Generic Type Arguments? |
| --- | --- | --- |
| **Java source method signature** | Java language concept distinguishing methods by name and parameter types (with conditions defined in JLS) | Uses Java type rules in source; not a JVM descriptor string |
| **JVM method descriptor** | String encoding parameter type list + return type in `method_info` | **No**; uses JVM types after erasure |
| **Class-file `Signature` attribute** | Metadata attribute with its own generic signature syntax per JVMS `4.7.9.1 | **Yes**, when declarations use generic constructs and the compiler must emit the attribute |

Example of a source method:

~~~java
List<String> names(List<String> input)
~~~

At the JVM level, the descriptor has the form:

~~~text
(Ljava/util/List;)Ljava/util/List;
~~~

Meanwhile, the method's `Signature` attribute has the form:

~~~text
(Ljava/util/List<Ljava/lang/String;>;)Ljava/util/List<Ljava/lang/String;>;
~~~

Both strings are valid and **describe two different layers of information**. Do not confuse the `Signature` attribute with the Java source method signature used in overloading: Java does **not** allow two methods differing only in return type to form two ordinary overloads, whereas JVM method descriptors **do include the return type**.

## 2. How Does Type Erasure Affect Types?

According to Java Language Specification `4.6, erasure converts language generic types into types usable by the JVM:

- `List<String>` and `List<Integer>` both erase to the raw class/interface `List`.
- A type variable without an explicit bound, such as `T` in `class Box<T>`, has erasure `Object`.
- With `T extends Number`, the erasure of `T` is `Number`.
- With multiple bounds, erasure is based on the **leftmost bound**. For example, `T extends Number & Comparable<T>` has erasure `Number`.
- With `U extends CharSequence`, the erasure of `U` is `CharSequence`.
- Arrays containing reference element types remain arrays after erasure; descriptors use `[`.
- Primitive types have no generic parameterization; descriptors still use the corresponding primitive symbols.

**Erasure does not merely strip `<...>` brackets from source while leaving everything else untouched.** The compiler must replace type variables with appropriate bounds; in certain situations it also inserts casts and generates bridge methods to preserve Java semantics.

Example:

~~~java
class Box<T extends Number> {
    T value;
    T get() { return value; }
}
~~~

The JVM does not have a separate runtime class `Box<Integer>` and a class `Box<Double>` created specifically for those type arguments. Field `value` and the return type of `get()` in descriptors are represented as `java.lang.Number` because the bound of `T` is Number.

## 3. JVM Descriptor Syntax: Reading Symbols Correctly

Descriptors do not use ordinary Java name syntax. They are symbol strings defined by JVM Specification `4.3.2 and `4.3.3.

### 3.1. Field Descriptor Notation

| Java type | Descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `java.lang.String` | `Ljava/lang/String;` |
| `java.util.List` | `Ljava/util/List;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| `int[][]` | `[[I` |

Class names in descriptors use **`/`** to separate internal packages, not **`.`** as type names in Java source. For reference types, **`L`** opens the class name and **`;`** closes the reference type.

`V` represents **void return** in a **method descriptor**, not the type of a valid field.

### 3.2. Method Descriptor Notation

General form:

~~~text
(Parameter1DescriptorParameter2Descriptor...)ReturnDescriptor
~~~

Example:

~~~java
static int sum(int a, int b) { return a + b; }
~~~

Descriptor:

~~~text
(II)I
~~~

Method:

~~~java
static void log(String value, int times) { }
~~~

Descriptor:

~~~text
(Ljava/lang/String;I)V
~~~

Method:

~~~java
static String[] convert(int[] values) {
    return new String[values.length];
}
~~~

Descriptor:

~~~text
([I)[Ljava/lang/String;
~~~

**There are no commas or parameter names** between descriptor components. A generic method such as `<T> T identity(T t)` with an implicit Object bound will have descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`, while the generic signature carries info about `T`.

### 3.3. What Is the JVM Descriptor Used For?

Descriptors participate in identifying fields/methods in class files and symbolic references for linking/invocation. The JVM uses descriptors to know parameter counts, parameter JVM types, and return types; generic type arguments like `String` in `List<String>` do not enter this structure.

**Do not confuse with source type checking:** javac still checks generic type arguments when compiling Java. Part of generic information is also stored so other compilers can understand declarations when using class files as dependencies.

## 4. Main Example: A Generic Class with Field, Constructor, and Method

Create file **GenericSample.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericSample<T extends Number> {
    private T value;
    public List<String> labels;

    public GenericSample(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public List<T> copy(List<T> input) {
        return new ArrayList<>(input);
    }

    public <U extends CharSequence> U echo(U input) {
        return input;
    }

    public static void main(String[] args) {
        GenericSample<Integer> sample =
                new GenericSample<>(7);

        System.out.println(sample.get());
        System.out.println(sample.copy(List.of(3, 5)));
        System.out.println(sample.echo("ok"));
    }
}
~~~

Compile with JDK 17+:

~~~bash
javac --release 17 -d out GenericSample.java
java -cp out GenericSample
~~~

**Verified standard output:**

~~~text
7
[3, 5]
ok
~~~

This is complete source, needing no libraries outside the JDK. `--release 17` selects the Java 17 compilation level; with javac 21, the generated class file has major version 61 instead of 65 of JDK 21's default target. **The generic syntax of descriptors and `Signature` in the example does not change because of this target choice.**

### 4.1. Using javap -s to View Descriptors

Run:

~~~bash
javap -classpath out -p -s GenericSample
~~~

Where:

- **`-classpath out`** points to the directory containing `GenericSample.class`.
- **`-p`** requests showing private members too (otherwise field `value` may be hidden).
- **`-s`** requests printing **internal type signatures** in the `javap` utility's terminology, meaning the **JVM descriptors** appearing below declaration lines.
- **`-s` is not the flag to directly print the class-file `Signature` attribute** containing generic syntax; to view that attribute, use `-v`.

Key output excerpts, verified against OpenJDK 21:

~~~text
private T value;
  descriptor: Ljava/lang/Number;

public java.util.List<java.lang.String> labels;
  descriptor: Ljava/util/List;

public GenericSample(T);
  descriptor: (Ljava/lang/Number;)V

public T get();
  descriptor: ()Ljava/lang/Number;

public java.util.List<T> copy(java.util.List<T>);
  descriptor: (Ljava/util/List;)Ljava/util/List;

public <U extends java.lang.CharSequence> U echo(U);
  descriptor: (Ljava/lang/CharSequence;)Ljava/lang/CharSequence;

public static void main(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)V
~~~

**Note:** the declaration line reconstructed by `javap` may print `T` or `List<String>` thanks to class-file info. **The `descriptor:` line right underneath** is the JVM descriptor value this lesson compares against. Do not take headers printing generics as proof that descriptors contain generics.

### 4.2. Comparison Table per Declaration

| Java Declaration | JVM descriptor | Why |
| --- | --- | --- |
| `T value` | `Ljava/lang/Number;` | `T extends Number` erases to Number |
| `List<String> labels` | `Ljava/util/List;` | Type argument String is absent from descriptor |
| `GenericSample(T value)` | `(Ljava/lang/Number;)V` | Constructor returns void in descriptor |
| `T get()` | `()Ljava/lang/Number;` | Return type T erases to Number |
| `List<T> copy(List<T>)` | `(Ljava/util/List;)Ljava/util/List;` | Generic arguments of List are not in JVM descriptor |
| `<U extends CharSequence> U echo(U)` | `(Ljava/lang/CharSequence;)Ljava/lang/CharSequence;` | U has erasure CharSequence |
| `main(String[])` | `([Ljava/lang/String;)V` | String array and void return |

Reading descriptors accurately helps catch a common reasoning error: **`T extends Number` does not erase to Object**. Only type variables with no explicit bound or an appropriate bound have Object as erasure.

## 5. Using javap -v to View the Signature Attribute

Run:

~~~bash
javap -classpath out -p -v GenericSample
~~~

The **`-v`** flag prints constant pool, attributes, code details, and metadata; **`-p`** remains useful to ensure private members appear.

The output is long, so locate each declaration and the **`descriptor:`** and **`Signature:`** lines underneath it. A verified excerpt looks like:

~~~text
private T value;
  descriptor: Ljava/lang/Number;
  Signature: #...                    // TT;

public java.util.List<java.lang.String> labels;
  descriptor: Ljava/util/List;
  Signature: #...                    // Ljava/util/List<Ljava/lang/String;>;

public GenericSample(T);
  descriptor: (Ljava/lang/Number;)V
  Signature: #...                    // (TT;)V

public T get();
  descriptor: ()Ljava/lang/Number;
  Signature: #...                    // ()TT;

public java.util.List<T> copy(java.util.List<T>);
  descriptor: (Ljava/util/List;)Ljava/util/List;
  Signature: #...                    // (Ljava/util/List<TT;>;)Ljava/util/List<TT;>;

public <U extends java.lang.CharSequence> U echo(U);
  descriptor: (Ljava/lang/CharSequence;)Ljava/lang/CharSequence;
  Signature: #...                    // <U::Ljava/lang/CharSequence;>(TU;)TU;
~~~

**Notation `#...` is an illustrative constant-pool index placeholder.** In real output, there are numbers `#19`, `#22`, etc. Index numbers can change by JDK, build type, and constant pool layout; **the string after the `//` comment is the meaningful generic signature part**.

At the bottom of class output there is also a class-level line:

~~~text
Signature: #...                    // <T:Ljava/lang/Number;>Ljava/lang/Object;
~~~

Note the class-level Signature appears **outside the member body section**, because it belongs to `ClassFile`. Signatures directly under fields/methods/constructors belong to `field_info` or `method_info` respectively.

### 5.1. Decoding Field Signature Strings

Field `T value`:

~~~text
TT;
~~~

In generic signature grammar, the initial **`T`** opens a **type variable signature**, variable name **T**, terminated by **`;`**. This string differs from JVM descriptor `Ljava/lang/Number;` which states only erasure.

Field `List<String> labels`:

~~~text
Ljava/util/List<Ljava/lang/String;>;
~~~

Here:

- `Ljava/util/List` represents the List class/interface reference.
- `<...>` contains type arguments in generic signature form.
- `Ljava/lang/String;` is the String argument.
- The final `;` closes List's class-type signature.

In the descriptor, all argument info between `<` and `>` is absent:

~~~text
Ljava/util/List;
~~~

### 5.2. Decoding Method Signatures

Method `T get()`:

~~~text
descriptor: ()Ljava/lang/Number;
Signature:  ()TT;
~~~

The descriptor describes the actual JVM return type as Number. Generic Signature states that in source the return type is **type variable T**, declared at class level. A caller with `GenericSample<Integer>` is checked by the compiler as retrieving Integer; this does not cause the JVM to have a separate method for Integer.

Method `copy`:

~~~text
descriptor: (Ljava/util/List;)Ljava/util/List;
Signature:  (Ljava/util/List<TT;>;)Ljava/util/List<TT;>;
~~~

Inside the generic signature, `TT;` is type argument T for both parameter and result. The JVM descriptor leaves only raw `List`.

Method `echo`:

~~~text
descriptor: (Ljava/lang/CharSequence;)Ljava/lang/CharSequence;
Signature:  <U::Ljava/lang/CharSequence;>(TU;)TU;
~~~

This is a case with a **generic method type parameter U**. The `<U::Ljava/lang/CharSequence;>` part declares U has interface bound CharSequence. **The double colon** here is not a typo: the grammar denotes an empty class bound followed by interface bound `CharSequence`. The `(TU;)TU;` part encodes U as parameter and return type.

### 5.3. Decoding Class-Level Signature

~~~text
<T:Ljava/lang/Number;>Ljava/lang/Object;
~~~

Meaning:

- `<T:Ljava/lang/Number;>` declares type parameter T with bound Number.
- `Ljava/lang/Object;` is the generic superclass of GenericSample in the example.
- A class signature string can also include generic interfaces when the class implements corresponding interfaces.

This is how bytecode preserves the **`T extends Number` declaration** even though member descriptors have only Number.

## 6. Signature Is Not Just Another Name for Descriptor

Every field and method in a class file has a **descriptor** carrying a mandatory structure for the JVM to understand the member kind. Generic `Signature` is an **auxiliary attribute**, appearing when declarations need to express generic constructs per JVMS rules.

Comparison:

| Criterion | descriptor | Signature attribute |
| --- | --- | --- |
| Where stored | `field_info.descriptor_index` / `method_info.descriptor_index` | `Signature` attribute in attributes list |
| Mandatory for class-file field/method | Yes | Only when declaration uses specified generic constructs |
| Contains `<Ljava/lang/String;>` of `List<String>` | No | Yes |
| Contains type variable name `T` | No; replaced by erasure | Can contain `TT;` |
| Used directly in JVM linking / invocation | Yes | No, not for distinguishing generic instantiations at runtime |
| Serves generic reflection and other compilers | Base runtime type info | Yes, stores generic declaration info |
| Has `(args)return` form for methods | Yes | May also have leading parameters and bounds |
| Conveniently displayed by javap | `javap -s` or `-v` | `javap -v` |

**Absence of a Signature attribute** does not by itself prove the compiler made a mistake. A class/method/field not using type variables or parameterized types may have only a descriptor. Conversely, for a generic declaration falling under specified rules, JVMS requires the compiler to emit the corresponding Signature.

Per JVMS `4.7.9, a class file has at most **one Signature attribute** at a `ClassFile`, `field_info`, `method_info` location (and record components per spec version). Tools reading class files must determine which member an attribute belongs to; do not merely scan the whole constant pool for the word “Signature” and guess.

### 6.1. How Is Signature Stored via the Constant Pool?

Inside a class file, the `Signature` attribute stores an index to a `CONSTANT_Utf8_info` containing the signature string. `javap -v` typically prints:

~~~text
Signature: #68  // Ljava/util/List<Ljava/lang/String;>;
~~~

`#68` itself is a constant-pool reference in a specific class file, **not a standardized Signature code** for looking up across all class files. The string on the right describes the type per signature grammar.

If writing a bytecode validation tool, parse the class file structurally or use a proper class-file reading API instead of only regex-searching `javap` stdout.

## 7. Why Does Erasure Still Preserve Type Safety at Source?

Suppose:

~~~java
GenericSample<Integer> x = new GenericSample<>(7);
Integer number = x.get();
~~~

At source level, javac checks bound `Integer extends Number`, and knows `get()` has return type T corresponding to Integer in the `GenericSample<Integer>` context. Yet in bytecode, the `get()` method still has descriptor:

~~~text
()Ljava/lang/Number;
~~~

The compiler can insert **`checkcast java/lang/Integer`** at points using values needing Integer. That is an execution mechanism to preserve type expectations after erasure. Depending on context, casts may be optimized or inserted at the caller; do not assume a given println statement always contains exactly one checkcast without checking bytecode.

To inspect bytecode of the compiled program:

~~~bash
javap -classpath out -p -c GenericSample
~~~

`-c` disassembles method code; look for the `checkcast` instruction if emitted by the compiler in the specific situation. `javap -v` also includes the Code attribute yet contains much more metadata.

**Important:** runtime does not guarantee a List collection holds Strings just because field `labels` has Signature `List<String>`. Legacy/raw code or unchecked casts can break type safety and cause `ClassCastException` later. The Signature attribute is **declaration metadata**, not a validator scanning every collection element on every operation.

## 8. Separate Example: Erasure of the First Bound

Try the declarations:

~~~java
class Bounds<T extends Number & Comparable<T>> {
    T data;
    T get() { return data; }
}
~~~

Here `T` has two bounds. The first bound is `Number`, so the descriptor of `data` and return of `get()` use `Number`. The generic signature can still encode both bounds, where `Comparable<T>` still carries type argument T.

Another case:

~~~java
class Unbounded<T> {
    T data;
}
~~~

Because T declares no explicit bound, the erasure of T is Object:

~~~text
descriptor: Ljava/lang/Object;
Signature:  TT;
~~~

With an interface bound:

~~~java
class RunnableBox<T extends Runnable> {
    T task;
}
~~~

`Runnable` is the first bound so the descriptor is `Ljava/lang/Runnable;`. In the generic signature, interface bounds have their own syntax; rely on `javap -v` to see the exact output.

**Read descriptors based on type variable erasure per JLS `4.6**, not based on an object's runtime value or a type argument used at one specific call site.

## 9. Wildcards: Symbols +, -, * in Generic Signature

The `Signature` attribute also has syntax encoding **wildcards**:

| Source generic type | Typical generic signature part | Explanation |
| --- | --- | --- |
| `List<? extends Number>` | `Ljava/util/List<+Ljava/lang/Number;>;` | `+`: upper-bounded wildcard |
| `List<? super Integer>` | `Ljava/util/List<-Ljava/lang/Integer;>;` | `-`: lower-bounded wildcard |
| `List<?>` | `Ljava/util/List<*>;` | `*`: unbounded wildcard |
| `List<String>` | `Ljava/util/List<Ljava/lang/String;>;` | Concrete type argument |
| `List<T>` | `Ljava/util/List<TT;>;` | Type variable T |

**All of the `List<...>` fields above share the JVM field descriptor `Ljava/util/List;`**, even though their generic signature contents differ.

Do not confuse `+` or `-` in generic signatures with arithmetic operators in bytecode. They are symbols of **signature grammar** per JVMS `4.7.9.1, used to preserve variance meanings expressed through wildcards in Java source.

This is also evidence of why reading only descriptors is **insufficient** when building IDEs or API documentation wanting to reconstruct declaration wildcards.

## 10. Bridge Methods: A Key Consequence of Erasure

Generics and overriding must maintain polymorphism after erasure. In certain cases, the compiler generates a **bridge method**; verifying both descriptors and flags of the bridge is a very useful exercise.

Create file **Child.java**:

~~~java
class Parent<T> {
    public T get() {
        return null;
    }
}

public class Child extends Parent<String> {
    @Override
    public String get() {
        return "child";
    }

    public static void main(String[] args) {
        Parent<String> p = new Child();
        System.out.println(p.get());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -d out Child.java
java -cp out Child
~~~

**Verified stdout on OpenJDK 21:**

~~~text
child
~~~

### 10.1. Same Name get, Two Descriptors in Child

In Parent<T>, the source method `T get()` erases to Object, so in `Parent.class`:

~~~text
descriptor: ()Ljava/lang/Object;
~~~

In Child, the overriding method declares return `String`. When using `javap -s`:

~~~bash
javap -classpath out -p -s Parent Child
~~~

In `Child.class`, you will see **two methods named get** with different descriptors:

~~~text
public java.lang.String get();
  descriptor: ()Ljava/lang/String;

public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
~~~

From Java source's perspective, the two methods seen are one valid public override and one compiler-generated bridge, not two source overloads manually declared by the programmer based on return type. The `get():Object` entry in the class file ensures calls through `Parent` still dispatch to the implementation in Child.

### 10.2. Flags ACC_BRIDGE and ACC_SYNTHETIC

Run:

~~~bash
javap -classpath out -p -v Child
~~~

The bridge section looks like:

~~~text
public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
  Code:
     0: aload_0
     1: invokevirtual #...  // Method get:()Ljava/lang/String;
     4: areturn
~~~

The `#...` number is a mutable constant-pool index. Meaning:

- **ACC_BRIDGE**: bridge method generated by the compiler to support overriding relationships after generic erasure/covariant returns.
- **ACC_SYNTHETIC**: method not appearing verbatim in user source code.
- The bridge returns Object and calls the actual `String get()` implementation in Child.
- The bridge has its **own descriptor**, because the JVM needs the exact method descriptor at call/linking sites.

**A bridge is not a sign of a compiler bug or a new generic instantiation.** It is a compiler technique maintaining polymorphism per Java rules. When using Reflection API `getDeclaredMethods()`, bridges can be visible; `Method.isBridge()` and `isSynthetic()` help classify them.

### 10.3. Why Comparing Signature and Descriptor Alone Is Not Enough in Overrides

If looking only at one method in Child, learners may ask why `get()` has both String and Object returns. You need to understand **class hierarchies, erased parent method descriptors, and bridge methods**. Therefore, verifying generic output sometimes requires inspecting multiple class files rather than just one class file.

Do not mechanically call a bridge method a “generic method whose Signature contains String”. The bridge in the example has descriptor `()Ljava/lang/Object;` and the bridge flag; it does not need a generic Signature attribute like the source declaration `Parent<T>.get()`.

## 11. Reflection: Erased Types and Generic Declarations Differ

The Java Reflection API supports both reading types per JVM/erasure and reading generic declaration types.

With `GenericSample.java` from section 4, create **ReflectProbe.java**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;

public class ReflectProbe {
    public static void main(String[] args) throws Exception {
        Field field =
                GenericSample.class.getField("labels");

        System.out.println(
                "field type=" + field.getType().getTypeName()
        );
        System.out.println(
                "field generic=" +
                field.getGenericType().getTypeName()
        );

        Method getter =
                GenericSample.class.getMethod("get");

        System.out.println(
                "return type=" +
                getter.getReturnType().getTypeName()
        );
        System.out.println(
                "return generic=" +
                getter.getGenericReturnType().getTypeName()
        );

        TypeVariable<?> variable =
                GenericSample.class.getTypeParameters()[0];

        System.out.println(
                "type variable=" + variable.getName()
        );
        System.out.println(
                "bound=" +
                variable.getBounds()[0].getTypeName()
        );
    }
}
~~~

Compile and run (must include `GenericSample.java`):

~~~bash
javac --release 17 -d out GenericSample.java ReflectProbe.java
java -cp out ReflectProbe
~~~

**Verified standard output on OpenJDK 21:**

~~~text
field type=java.util.List
field generic=java.util.List<java.lang.String>
return type=java.lang.Number
return generic=T
type variable=T
bound=java.lang.Number
~~~

Especially important pairs:

- `Field.getType()` returns **raw Class object** `List.class` corresponding to descriptor `Ljava/util/List;`.
- `Field.getGenericType()` returns type info `List<String>`, the declaration stored in generic metadata.
- `Method.getReturnType()` returns `Number.class` for `T get()` because the erasure of T is Number.
- `Method.getGenericReturnType()` can return a `TypeVariable` object named T.
- `Class.getTypeParameters()` lets you read type parameter declarations and bounds.

**Do not misunderstand Reflection:** the result of `getGenericType()` tells you **the field was declared as List<String>**; it does not prove every object pointed to by the field actually contains Strings. `ArrayList<String>` and `ArrayList<Integer>` are not two distinct runtime classes solely because of generic arguments.

### 11.1. Generic Superclasses and Object Instances

If source has:

~~~java
class IntegerBox extends GenericSample<Integer> {
    IntegerBox() {
        super(1);
    }
}
~~~

This is an **illustrative class snippet**, placed in the same project and compiled with `GenericSample.java`. `IntegerBox.class.getGenericSuperclass()` can show type argument Integer because the **`extends GenericSample<Integer>`** declaration is recorded in IntegerBox's class-level Signature.

Conversely, if merely instantiating:

~~~java
GenericSample<Integer> instance =
        new GenericSample<>(1);
~~~

then `instance.getClass()` is `GenericSample.class`, and **does not carry a separate runtime class for Integer**. Information about the type argument in a **usage variable** is not necessarily retained as an attribute on the object at runtime.

## 12. Descriptors Serve Linkage; Signatures Support Generic Reflection

A conceptual view:

~~~text
GenericSample<T extends Number>  (Java source)
                  |
                  v
              javac
                  |
                  +-- JVM descriptors
                  |     field value: Ljava/lang/Number;
                  |     get(): ()Ljava/lang/Number;
                  |     labels: Ljava/util/List;
                  |
                  +-- Signature attributes
                        field value: TT;
                        get(): ()TT;
                        labels: Ljava/util/List<Ljava/lang/String;>;
                        class: <T:Ljava/lang/Number;>Ljava/lang/Object;
                  |
                  v
              .class file
                  |
                  +-- JVM uses descriptors for type/linking/invocation
                  +-- compiler/reflection/tooling reads generic metadata
~~~

According to JVMS, the Signature attribute's role is **supporting reflection, debugging, and compiling when only class files remain**. The JVM does not need to use Signature's type arguments to generate specialized class versions for String/Integer.

For class files created or modified by external tools, **generic Signature may be malformed** even when descriptors still exist. JVMS documentation notes that validation of Signature validity may occur when Java SE library methods access generic metadata; therefore, when building bytecode-reading tools, do not assume every Signature from untrusted files is always valid.

## 13. Reading Local Variables: Different from Field/Method-Level Signature Attributes

`Signature` attached to a class, field, method, or record component is not the only metadata mechanism related to generics. Local variables in methods can have debug info:

- **LocalVariableTable**: name, slot, and descriptor of local variables within bytecode scope.
- **LocalVariableTypeTable**: generic type signatures of certain local variables when the compiler emits sufficient metadata.

Example:

~~~java
// Illustrates code inside a method.
List<String> words = List.of("a", "b");
System.out.println(words.size());
~~~

If appropriate debug metadata is enabled:

~~~bash
javac -g -d out GenericSample.java
javap -classpath out -v -p GenericSample
~~~

You can inspect debug attributes **if source actually contains the local variable you want to view**. The command above on the original `GenericSample.java` source has some other locals yet does not contain the `words` variable from the illustrative fragment. To see `words`, you must **add the fragment into a real method** before compiling. Do not assume every generic local variable will always have `LocalVariableTypeTable` if the compiler wasn't asked to emit metadata or if optimizations/code structures differ.

**Do not confuse `LocalVariableTypeTable` with member-level `Signature`.** A tool inspecting only field/method Signatures will not automatically recover all generic types of local variables.

## 14. Cross-Checking Output with javap via a Repeatable Workflow

A validation workflow for class files after compilation:

1. **Save source version:** know which declarations are being tested; never use stale class files.
2. **Compile to dedicated output:** e.g., `javac --release 17 -d out ...`.
3. **Read class-level summary:** `javap -classpath out -p GenericSample` to see public and private members.
4. **Read descriptors:** `javap -classpath out -p -s GenericSample`.
5. **Read Signature attributes:** `javap -classpath out -p -v GenericSample`.
6. **Match per member:** field `labels` with field `labels`, method `copy` with method `copy`.
7. **Apply erasure rules:** explain why JVM types are raw List/Number/Object.
8. **Verify generic metadata:** confirm type parameters, bounds, and type arguments preserved in Signature.
9. **If generic overrides exist:** also check superclasses/subclasses and bridge methods.
10. **When needing runtime proof:** call `Field.getGenericType()` and `Method.getGenericReturnType()`.
11. **QA sign-off:** class file compiled successfully; output was read from the right directory, right class, and right JDK.

### 14.1. How to Recognize Expected Results

With the given `GenericSample.java`, a satisfactory verification must simultaneously confirm:

- Field `value`: descriptor `Ljava/lang/Number;`, Signature `TT;`.
- Field `labels`: descriptor `Ljava/util/List;`, Signature `Ljava/util/List<Ljava/lang/String;>;`.
- Constructor: descriptor `(Ljava/lang/Number;)V`, generic Signature `(TT;)V`.
- Method `get`: descriptor `()Ljava/lang/Number;`, Signature `()TT;`.
- Method `copy`: descriptor `(Ljava/util/List;)Ljava/util/List;`, Signature has `List<T>` on parameter and result.
- Method `echo`: descriptor takes `CharSequence`, Signature declares generic U.
- Class-level Signature has `<T:Ljava/lang/Number;>Ljava/lang/Object;`.
- Program stdout `7`, `[3, 5]`, `ok` as in section 4.

Running only `javap -s` is **insufficient** to confirm generic Signature attributes. Running only `javap -v` without matching each descriptor/member line is also easy to misinterpret.

## 15. Common Reasoning Mistakes

**Mistake 1 — “In bytecode, generics are completely gone.”**

False, because the `Signature` attribute can store the full generic declaration. More accurately: **JVM descriptors and most runtime operations use erased types**, while compilers/tooling/reflection can read back generic metadata.

**Mistake 2 — “javap -s is the only command to view generic Signature.”**

False. `javap -s` prints internal JVM descriptors; when wanting to see the attribute named `Signature`, use `javap -v` and inspect the exact member.

**Mistake 3 — “T with bound Number still turns into Object.”**

False. Erasure takes the **leftmost bound**, so `T extends Number` becomes Number. Only with T having no explicit bound is erasure normally Object.

**Mistake 4 — “Two Lists with different type arguments create two JVM descriptor types.”**

False. `List<String>` and `List<Integer>` share the same erased field descriptor `Ljava/util/List;`; generic Signatures differ when declarations differ.

**Mistake 5 — “Signature is a runtime rulebook checking every element.”**

False. `Signature` is metadata; generic collections do not become containers specialized by the JVM for String. Raw/unchecked code can still cause heap pollution.

**Mistake 6 — “Two get methods in Child are two Java source overloads I wrote.”**

False. In the example `Child` wrote only one `String get()`; the compiler generated bridge `Object get()` to ensure polymorphism after erasure.

**Mistake 7 — “Every class file must have Signature.”**

False. Members not using generic constructs do not necessarily have Signature. JVM descriptors are the more fundamental structural part.

**Mistake 8 — “Number #68 in javap has a fixed generic meaning.”**

False. It is **an index into the constant pool of a specific class file**. The encoded signature string is the semantic info needing decoding.

**Mistake 9 — “If Reflection reads List<String>, the object definitely contains only Strings.”**

False. `Field.getGenericType()` speaks about the declaration; it does not verify all runtime values or aliases holding raw types.

**Mistake 10 — “Having generic Signature allows method overloading differing only in return type.”**

False. Java source does not allow overloading solely by return type. JVM descriptors include the return type for class-file and method-linking mechanisms; that is a different rule layer from Java source overloading.

## 16. Self-Practice Exercises

### Exercise 1 — Identify Descriptors

From the following Java types, write JVM field descriptors and then verify with javap:

- `int`.
- `long`.
- `String[]`.
- `List<String>`.
- `List<? extends Number>`.
- `T` in `class Holder<T extends Number>`.

Explain why the two List fields use the same descriptor yet their Signatures can differ.

### Exercise 2 — Change the Bound

Replace `class GenericSample<T extends Number>` with another class `GenericSample<T>` and adjust code appropriately. Predict what type the descriptors of field `value` and method `get` change to from Number; verify with `javap -s` and `-v`.

### Exercise 3 — Wildcards

Create a class with three fields `List<? extends Number>`, `List<? super Integer>`, and `List<?>`. Compile and find symbols `+`, `-`, `*` respectively in `Signature`. Verify that the descriptors of all three remain `Ljava/util/List;`.

### Exercise 4 — Bridge Methods

Compile `Child.java` from section 10. Use `javap -v -p` to identify the name, descriptor, and flags of the bridge method. Predict output when calling `Parent<String> p = new Child(); p.get()`.

### Exercise 5 — Reflection

Run `ReflectProbe.java` and explain why `field.getType()` returns raw List whereas `field.getGenericType()` returns List<String>. Check similarly with `getReturnType()` and `getGenericReturnType()` of `get()`.

### Exercise 6 — Describe an Output Precisely

Given two lines:

~~~text
descriptor: (Ljava/util/List;)Ljava/util/List;
Signature:  (Ljava/util/List<TT;>;)Ljava/util/List<TT;>;
~~~

Write a short explanation for learners: the JVM sees a method accepting/returning List, while generic metadata expresses List<T> on both input/output. Do not write that the JVM automatically checks every element is T at runtime.

### Exercise 7 — Audit a Class File Without Source

You receive only a `.class` file from a library. Use `javap -v` to identify its generic superclass, fields, and method signatures. State what **can be verified** from the class file and what **cannot be inferred**, e.g., the type argument of an object instance that the program creates later.

## 17. Self-Check Questions

1. How does a JVM descriptor differ from the `Signature` attribute in purpose and storage location?
2. Why does `List<String>` have descriptor `Ljava/util/List;`?
3. With `T extends Number`, is the erasure of T Object or Number?
4. What does `TT;` encode in a generic signature?
5. Why does `<U::Ljava/lang/CharSequence;>` have two colons?
6. How do `javap -s` and `javap -v` need to be used differently?
7. Why does `GenericSample<Integer>` not make the JVM create a separate class GenericSampleInteger?
8. Does Reflection reading generic Signature reveal declarations or guarantee runtime values?
9. When does the compiler need a bridge method? Which flags help identify it?
10. Why are there two descriptors `get():Object` and `get():String` in `Child.class`?
11. How does `LocalVariableTypeTable` differ from field or method `Signature`?
12. If `Signature` is absent, is the class file necessarily broken?
13. How do you ensure `javap` is reading the freshly compiled class file?
14. Why should constant-pool index numbers not be used as comparison criteria between builds?

## 18. Official References

- **JLS 21 `4.6 — Type Erasure:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6
- **JVMS 21 `4.3.2 — Field Descriptors:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.2
- **JVMS 21 `4.3.3 — Method Descriptors:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3
- **JVMS 21 `4.7.9 — Signature Attribute:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9
- **JVMS 21 `4.7.9.1 — Generic Signatures:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9.1
- **Oracle JDK 21 — javap Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html
- **Java SE 21 — Field.getGenericType:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html
- **Java SE 21 — Method.getGenericReturnType:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html

**Remember:** To verify compiled generics, **place `descriptor` and `Signature` side by side on the exact field/method/class**. Descriptor shows **erased JVM types**; Signature preserves **generic declaration metadata** so compilers, reflection, and tooling understand type variables/arguments/bounds. Use `javap -s` to see descriptors, `javap -v -p` to see both Signature and bridge flags, and use Reflection to check generic info at the declaration level.
