# Fields and Methods in a Java Class File

After compilation, `javac` stores information about a Java class in a `.class` file. Alongside method bytecode, a class file also describes **fields**, **methods**, data types, access permissions, generic signatures, and many other attributes.

Understanding how fields and methods are represented helps you read `javap -verbose` output, investigate class linking errors, inspect library APIs, and understand why Java source code sometimes does not appear identically in the class file.

## 1. What are fields and methods?

In Java source code:

- A **field** is a variable declared directly inside a class or interface. A field can be an instance variable or a static variable.
- A **method** is a unit of behavior declared in a class or interface. A method can take parameters, return a value, or return no value.
- A **constructor** is the component that initializes an object. In a class file, a constructor is represented as a special method named `<init>`.
- A **class initializer** is the static initialization part. If code is needed to execute static initializers, the compiler generates a special method named `<clinit>`.

Example:

```java
public class Account {
    private String owner;        // instance field
    private static int total;    // static field

    public Account(String owner) { // constructor
        this.owner = owner;
        total++;
    }

    public String getOwner() {   // method
        return owner;
    }
}
```

Fields store the state of a class or object. Methods describe operations that can be performed on that state.

## 2. Where does a class file store fields and methods?

According to the JVM class file format, after the header and constant pool, a class file has the following main sections:

1. Access flags, the current class name, and the superclass name.
2. The list of interfaces implemented by the class.
3. The list of fields.
4. The list of methods.
5. The list of class-level attributes.

The two structures describing fields and methods have a similar form:

```text
field_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}

method_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
```

The `name_index` and `descriptor_index` fields are indices referencing entries in the constant pool, not name or type strings stored directly at that position.

- `access_flags`: flags describing the access permissions and properties of the field/method.
- `name_index`: the field name or method name.
- `descriptor_index`: the field type description or method type signature in JVM format.
- `attributes_count`: the number of additional attributes.
- `attributes`: additional information such as constant values, generic signatures, bytecode, exceptions, or annotations.

A class file has `fields_count` and `methods_count` to indicate the number of elements in each list.

## 3. What is a descriptor?

A **descriptor** is a standard notation string used by the JVM to describe the type of a field and the parameters/return value of a method. A descriptor differs from the Java type name displayed in source code.

### Field descriptors

Some basic type notations:

| Notation | Java Type |
| --- | --- |
| `B` | `byte` |
| `C` | `char` |
| `D` | `double` |
| `F` | `float` |
| `I` | `int` |
| `J` | `long` |
| `S` | `short` |
| `Z` | `boolean` |
| `L...;` | Reference type |
| `[...` | Array type |

Examples:

| Java Declaration | Field Descriptor |
| --- | --- |
| `int count;` | `I` |
| `boolean active;` | `Z` |
| `long id;` | `J` |
| `String name;` | `Ljava/lang/String;` |
| `int[] values;` | `[I` |
| `String[][] names;` | `[[Ljava/lang/String;` |

Class names in a descriptor use forward slashes `/` to separate packages and end with a semicolon. For example, `java.lang.String` is represented as `Ljava/lang/String;`.

### Method descriptors

A method descriptor has the structure:

```text
(parameter_type_1 parameter_type_2 ...)return_type
```

The parameters are enclosed in parentheses. The return type follows the closing parenthesis. If the method returns `void`, the notation is `V`.

Examples:

| Java Declaration | Method Descriptor |
| --- | --- |
| `void run()` | `()V` |
| `int add(int a, int b)` | `(II)I` |
| `String find(int id)` | `(I)Ljava/lang/String;` |
| `boolean matches(String text, int mode)` | `(Ljava/lang/String;I)Z` |
| `void setNames(String[] names)` | `([Ljava/lang/String;)V` |

Descriptors do not include parameter names. Therefore, two overloaded methods with the same name but different parameter types will have different descriptors.

Example:

```java
void print(int value);
void print(String value);
```

The two descriptors are `(I)V` and `(Ljava/lang/String;)V`, respectively.

## 4. Field access flags

Fields have flags describing their access permissions and properties. Some common flags:

| Flag | Meaning |
| --- | --- |
| `ACC_PUBLIC` | The field has public access |
| `ACC_PRIVATE` | The field is accessible only within the declaring class according to Java rules |
| `ACC_PROTECTED` | The field has protected access |
| `ACC_STATIC` | The field belongs to the class rather than individual objects |
| `ACC_FINAL` | The field can be assigned only once according to final rules |
| `ACC_VOLATILE` | The field has volatile semantics in the Java memory model |
| `ACC_TRANSIENT` | The field is marked transient for the default serialization mechanism |
| `ACC_SYNTHETIC` | A member generated by the compiler, not declared directly in source code |
| `ACC_ENUM` | The field represents an enum constant |

Example:

```java
public static final int MAX_RETRIES = 3;
private volatile boolean running;
private transient String cachedToken;
```

The fields above can carry corresponding flag combinations such as `ACC_PUBLIC`, `ACC_STATIC`, `ACC_FINAL`, `ACC_PRIVATE`, `ACC_VOLATILE`, or `ACC_TRANSIENT`.

Access flags in a class file are JVM-level representations. Actual access rules also involve packages, classes, subclasses, modules, and Java language rules.

## 5. Method access flags

Methods also have access flags and flags describing how they are executed.

| Flag | Meaning |
| --- | --- |
| `ACC_PUBLIC` | Public method |
| `ACC_PRIVATE` | Private method |
| `ACC_PROTECTED` | Protected method |
| `ACC_STATIC` | Static method |
| `ACC_FINAL` | The method cannot be overridden according to Java rules |
| `ACC_SYNCHRONIZED` | The method has synchronization when invoked |
| `ACC_BRIDGE` | A bridge method generated by the compiler to support generics/covariant return types |
| `ACC_VARARGS` | The method declares a varargs parameter |
| `ACC_NATIVE` | The method is implemented in native code |
| `ACC_ABSTRACT` | An abstract method with no bytecode body |
| `ACC_SYNTHETIC` | A method generated by the compiler |

Example:

```java
public static void main(String[] args) {
    // ...
}

public synchronized void update() {
    // ...
}

public abstract void execute();
```

An `abstract` or `native` method does not have a regular bytecode body, so it does not have a `Code` attribute like a Java method with a body.

Do not confuse `ACC_BRIDGE` with a method written directly by a programmer. The compiler may generate bridge methods to preserve dispatch rules and type compatibility when using generics or covariant return types.

## 6. Important field attributes

After the name and descriptor indices, a field can carry multiple attributes.

### ConstantValue

`ConstantValue` stores the constant value for certain static final fields that have a compile-time constant value, such as primitive or String constant variables.

Example:

```java
public static final int LIMIT = 100;
public static final String LABEL = "JAVA";
```

When inspected with `javap -verbose`, you may see information similar to:

```text
public static final int LIMIT;
  descriptor: I
  flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: int 100
```

Not every `static final` field has a `ConstantValue`. If the value needs to be computed at runtime or is initialized with a non-constant expression, the compiler may generate code in the class initializer instead of using this attribute.

An important note: public primitive/String constant values may be inlined by the compiler of calling code into dependent classes. When changing a constant in a library, it is sometimes necessary to recompile clients so they pick up the new value.

### Signature

The `Signature` attribute stores generic signature information that a regular descriptor cannot fully represent.

Example:

```java
private List<String> names;
```

The field descriptor is:

```text
Ljava/util/List;
```

The generic information can be stored in the Signature attribute:

```text
Ljava/util/List<Ljava/lang/String;>;
```

The JVM links fields by their type-erased descriptors. Generic Signatures retain information for the compiler, reflection, and analysis tools.

### RuntimeVisibleAnnotations and RuntimeInvisibleAnnotations

Annotations on a field can be stored in annotation attributes:

- `RuntimeVisibleAnnotations`: annotations that can be accessed at runtime via reflection if retention allows.
- `RuntimeInvisibleAnnotations`: annotations stored in the class file but not exposed as runtime-visible annotations through standard reflection.

Example:

```java
@Deprecated
private String oldName;
```

Depending on the annotation and its retention policy, the corresponding annotation metadata is stored in the class file.

## 7. Important method attributes

Methods can have attributes describing their body, exceptions, generics, parameters, and annotations.

### Code

For a method with a bytecode body, the `Code` attribute contains:

- `max_stack`: maximum depth of the operand stack required.
- `max_locals`: number of local variable slots required.
- `code_length` and `code[]`: length and sequence of bytecode instructions.
- `exception_table`: exception handling information in the method.
- Nested attributes, such as `LineNumberTable`, `LocalVariableTable`, and `StackMapTable`.

Abstract and native methods do not have a regular `Code` attribute because they do not have a bytecode body in the class file.

### Exceptions

The `Exceptions` attribute lists the checked exceptions declared in the method's `throws` clause.

Example:

```java
public void load() throws java.io.IOException {
    // ...
}
```

The `throws IOException` information can be displayed by `javap` and is stored in the Exceptions attribute. This attribute serves declarative information; runtime exception handling is represented separately in bytecode and the Code attribute's exception table.

### Signature and MethodParameters

- `Signature` stores the method's generic signature when needed.
- `MethodParameters` can store parameter names and related flags when compiled with `-parameters`.

Example:

```java
public <T> T first(List<T> values) {
    return values.get(0);
}
```

The runtime descriptor of the method after type erasure is:

```text
(Ljava/util/List;)Ljava/lang/Object;
```

The generic Signature retains information closer to the source declaration:

```text
<T:Ljava/lang/Object;>(Ljava/util/List<TT;>;)TT;
```

The descriptor is used for JVM-level linking; the Signature preserves generic metadata for tools and reflection.

### Annotations and AnnotationDefault

Annotations can appear on methods or parameters. For annotation methods of an annotation type, the `AnnotationDefault` attribute can store the default value of the annotation element.

Example:

```java
public @interface Role {
    String value() default "USER";
}
```

The default value `USER` is represented in the annotation type's class file using the appropriate attribute.

## 8. Constructors and class initializers in a class file

Constructors and static initializers have special names in a class file:

- `<init>`: instance constructor. Its descriptor ends with `V` because constructors do not return a value.
- `<clinit>`: static class initialization method, with descriptor `()V`.

Example:

```java
public class Config {
    private static final int DEFAULT_PORT = 8080;
    private static int currentPort;

    static {
        currentPort = DEFAULT_PORT + 1;
    }

    public Config() {
    }
}
```

The compiler generates the `<init>` constructor. Because there is a static initialization block, the compiler also generates `<clinit>` to execute the static initialization code.

Not every class needs `<clinit>`. If there are no static initialization operations to execute, this method may not be present. A compile-time constant such as `static final int DEFAULT_PORT = 8080` is typically represented using ConstantValue and by itself does not necessarily require generating `<clinit>`.

## 9. Complete example: inspecting fields and methods with javap

Create the file **`MemberDemo.java`**:

```java
import java.util.List;

public class MemberDemo<T> {
    public static final int MAX = 10;
    private static final String LABEL = "demo";

    private int count;
    private T value;

    public MemberDemo(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }

    public void setCount(int count) {
        this.count = count;
    }

    public boolean isPositive(int number) {
        return number > 0;
    }

    public static String format(String prefix, int number) {
        return prefix + number;
    }

    public List<String> names() {
        return List.of(LABEL);
    }

    public static void main(String[] args) {
        MemberDemo<String> demo = new MemberDemo<>("Java");
        System.out.println(demo.getValue());
        System.out.println(demo.isPositive(5));
    }
}
```

Compile with debug information and parameter names:

```bash
javac -g -parameters -d out MemberDemo.java
```

View members including private ones:

```bash
javap -classpath out -p MemberDemo
```

View field and method descriptors:

```bash
javap -classpath out -p -s MemberDemo
```

View full metadata and attributes:

```bash
javap -classpath out -p -s -v MemberDemo
```

In the output, you can identify:

- `MAX`: static final int field, descriptor `I`, with ConstantValue.
- `LABEL`: static final String field, descriptor `Ljava/lang/String;`.
- `count`: instance int field, descriptor `I`.
- `value`: generic `T` field, type-erased descriptor `Ljava/lang/Object;`, with Signature if retained.
- `<init>`: constructor taking an Object after type erasure.
- `getValue()`: descriptor returning Object, Signature showing generic type T.
- `format(String, int)`: descriptor `(Ljava/lang/String;I)Ljava/lang/String;`.
- `main(String[])`: descriptor `([Ljava/lang/String;)V`.

Run the program:

```bash
java -cp out MemberDemo
```

Output:

```text
Java
true
```

Note: detailed `javap` output may differ in constant pool index ordering, bytecode offsets, and formatting across JDK versions. Focus on descriptors, access flags, and attribute meanings rather than relying on specific index numbers.

## 10. In what order should you read javap output?

When inspecting a class file, you can read in the following order:

1. **Class name and superclass:** confirm the exact class being analyzed.
2. **Fields:** check names, descriptors, access flags, and ConstantValue.
3. **Methods:** check names, descriptors, access permissions, and declared attributes.
4. **Code:** for methods with a body, inspect bytecode, max stack, local slots, and the exception table.
5. **Signature:** check whether generic types are retained in metadata or erased in descriptors.
6. **Exceptions and annotations:** check throws declarations and annotation metadata.
7. **Debug attributes:** check LineNumberTable, LocalVariableTable, and MethodParameters if needed for investigation.

Useful commands:

| Purpose | Command |
| --- | --- |
| View public declarations | `javap -classpath out MemberDemo` |
| View private fields/methods too | `javap -classpath out -p MemberDemo` |
| View descriptors | `javap -classpath out -p -s MemberDemo` |
| View method bytecode | `javap -classpath out -c MemberDemo` |
| View detailed metadata | `javap -classpath out -v MemberDemo` |
| View constant fields | `javap -classpath out -constants MemberDemo` |
| View debug information | `javap -classpath out -l MemberDemo` |

If the class is in a package, use its fully qualified name, such as `com.example.MemberDemo`, and the classpath must point to the root directory containing the `com` package.

## 11. How can fields and methods differ from source code?

A class file is the result of compilation, so not every member in it corresponds one-to-one with a declaration line in source code.

Some common situations:

- The compiler generates bridge methods to support generics and covariant return types.
- The compiler generates synthetic fields or methods to support certain language constructs.
- A default constructor may be generated by the compiler if the class declares no constructor.
- Static initializers are combined into `<clinit>`.
- Generic types undergo type erasure in descriptors, while Signature can store generic information.
- Parameter names and local variable names may be absent from the class file if not compiled with the corresponding metadata.

Therefore, when inspecting libraries or investigating runtime behavior, treat the class file as a JVM-level representation, not a verbatim copy of Java source code.

## 12. Common issues when analyzing fields and methods

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| Private fields not visible | `javap` defaults to showing only public/protected members depending on view mode | Use `javap -p` |
| Cannot understand descriptor | Confusing JVM notation with Java types | Break the descriptor into parameters, return type, and reference types |
| Generic T shown as Object | Descriptor reflects type erasure | Check the Signature attribute with `javap -v` |
| Method bytecode not visible | Method is abstract/native or `-c` was not used | Check method flags and run `javap -c` |
| ConstantValue not visible | Field is not an eligible constant variable or is initialized at runtime | Check `<clinit>` and initialization bytecode |
| Parameter names not visible | Class was not compiled with `-parameters` | Recompile with `javac -parameters` |
| Local variable names/line numbers missing | Debug attributes are missing | Compile with `javac -g` |
| Method appears that is not in source code | Compiler generated bridge/synthetic method or specially represented/inherited member | Check access flags, `ACC_BRIDGE`, and `ACC_SYNTHETIC` |

## 13. Key Takeaways

- A class file has separate lists for fields and methods; each member is described by access flags, name, descriptor, and attributes.
- A field descriptor describes the data type; a method descriptor describes parameter types and the return type.
- Generic types typically undergo type erasure in descriptors; Signature can retain generic information.
- `ConstantValue` stores certain static final constant values; not every final field has this attribute.
- `Code` contains the bytecode of methods with a body; abstract and native methods do not have a regular Code attribute.
- `<init>` is the constructor, while `<clinit>` is the class initializer.
- Use `javap -p -s -v` to inspect private members, descriptors, and detailed metadata.

When you understand the structure of fields and methods in a class file, you can accurately read JVM-level APIs, recognize generic erasure, analyze bytecode, and diagnose issues related to class linking or library compatibility.