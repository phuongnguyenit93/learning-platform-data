# Access Flags, Superclass, Interfaces, Fields, and Methods in the `.class` File

## 1. Purpose and Location of Components

A `.class` file does not merely contain a list of bytecode instructions. It also describes **class identity**, **access/type characteristics**, **direct superclass**, **direct interfaces**, **declared fields**, and **declared methods**. The JVM relies on this information to load, link, verify, check access, execute, and perform reflection on the program.

This lesson focuses on six components of the `ClassFile` structure in **JVMS `4.1`**: `access_flags`, `this_class`, `super_class`, `interfaces[]`, `fields[]`, and `methods[]`. They heavily use indices pointing into the **constant pool** and contain sub-tables with their own structures.

After studying this, you will be able to read `javap -v -p` output to answer:

- Is this a `class`, `interface`, `enum`, annotation interface, or `module-info`? Which types are `public`, `final`, `abstract`?
- Who does this class directly `extends` and `implements`? Why is the `super_class` of an interface still `java/lang/Object`?
- Which fields and methods are **directly declared** in the file, and which members are only **inherited**?
- Does the `ACC_FINAL` flag differ for a class/field/method? Why can't the bit value `0x0040` be understood without knowing which table it belongs to?
- Where are the constructor `<init>`, class initializer `<clinit>`, field descriptor, method descriptor, and `Code` attribute represented?
- How should special cases such as `record`, `sealed class`, compiler-generated bridge methods, and `module-info.class` be read?

## 2. Map of the `ClassFile` Structure

A valid class file has a binary layout (schema according to JVMS; `u1`, `u2`, `u4` are 1-, 2-, and 4-byte unsigned integers respectively):

~~~text
ClassFile {
    u4             magic;
    u2             minor_version;
    u2             major_version;
    u2             constant_pool_count;
    cp_info        constant_pool[constant_pool_count - 1];

    u2             access_flags;
    u2             this_class;
    u2             super_class;

    u2             interfaces_count;
    u2             interfaces[interfaces_count];

    u2             fields_count;
    field_info     fields[fields_count];

    u2             methods_count;
    method_info    methods[methods_count];

    u2             attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

The order of appearance above is the **order of data in the file**, not the order in which the VM "executes the parts". `magic` is normally `0xCAFEBABE`; `major_version` helps identify the class-file format level (for example, Java 17 → major 61, Java 21 → 65, Java 25 → 69). `constant_pool` contains representations of names, strings, descriptors, class/field/method references, etc., which subsequent tables refer to by **index**.

| Item | Data Form | Meaning |
| --- | --- | --- |
| `access_flags` | `u2` bitmask | Attributes of the **class/interface/module being defined** |
| `this_class` | `u2` constant-pool index | Identity of this class/interface itself |
| `super_class` | `u2` constant-pool index or 0 in special cases | **Direct superclass** at the class-file format level |
| `interfaces_count`, `interfaces[]` | `u2` count and array of indices | List of **direct superinterfaces** |
| `fields_count`, `fields[]` | count and array of `field_info` | Fields **declared** in the class/interface |
| `methods_count`, `methods[]` | count and array of `method_info` | Methods/constructors/class initializer **declared** |
| `attributes[]` at end of file | array of `attribute_info` | Class-level metadata such as `SourceFile`, `Signature`, `Record`, `PermittedSubclasses`, etc. |

**Reading principle:** `this_class`, `super_class`, and each element of `interfaces[]` are **indices** to `CONSTANT_Class_info` in the constant pool, not names written directly into the `u2` fields. `fields[]` and `methods[]` in turn contain **sub-structures**, where each structure also points back to the constant pool to resolve its name and descriptor.

~~~text
ClassFile
  |
  +-- access_flags: ACC_PUBLIC | ACC_FINAL | ACC_SUPER
  +-- this_class -------> constant_pool[#X] = Class "demo/ClassLayout"
  +-- super_class ------> constant_pool[#Y] = Class "demo/Base"
  +-- interfaces[] -----> constant_pool[#A] = Class "demo/Labeled"
  |                    -> constant_pool[#B] = Class "java/io/Serializable"
  +-- fields[] ---------> field_info { flags, name_index, descriptor_index, attributes[] }
  +-- methods[] --------> method_info { flags, name_index, descriptor_index, attributes[] }
  +-- attributes[] -----> SourceFile, Signature, Record, ...
~~~

`#X`, `#Y`, `#A`, `#B` are only **illustrative notations**: actual index numbers are determined by the compiler and the class file content.

## 3. `access_flags` of a Class/Interface

`access_flags` is a 16-bit bitmask: each bit indicates an access permission or characteristic of the **class/interface/module**. Multiple flags can be enabled together, but JVMS has rules restricting combinations.

| Class-Level Flag | Hex Value | Accurate Interpretation |
| --- | --- | --- |
| `ACC_PUBLIC` | `0x0001` | Class/interface is declared `public` |
| `ACC_FINAL` | `0x0010` | Class cannot be subclassed |
| `ACC_SUPER` | `0x0020` | Historical compatibility flag for `invokespecial` semantics |
| `ACC_INTERFACE` | `0x0200` | This is an interface, not a regular class |
| `ACC_ABSTRACT` | `0x0400` | Abstract, cannot be instantiated directly |
| `ACC_SYNTHETIC` | `0x1000` | Compiler-generated type, does not correspond directly to a source declaration |
| `ACC_ANNOTATION` | `0x2000` | This is an annotation interface |
| `ACC_ENUM` | `0x4000` | Related to enum type according to JVMS rules |
| `ACC_MODULE` | `0x8000` | Special file describing a module, not a regular class/interface |

A class declared `public final class ClassLayout` typically has `ACC_PUBLIC`, `ACC_FINAL`, and `ACC_SUPER` in the file generated by modern `javac`. To illustrate the bitmask:

~~~text
ACC_PUBLIC = 0x0001
ACC_FINAL  = 0x0010
ACC_SUPER  = 0x0020
-------------------
Total      = 0x0031
~~~

When you see `flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER`, you are looking at the **permissions and characteristics of the class**, not the flags of a field or method.

Rules worth remembering:

- `ACC_INTERFACE` requires `ACC_ABSTRACT`; an interface cannot simultaneously set `ACC_FINAL` or `ACC_SUPER`. An annotation interface has both `ACC_ANNOTATION` and `ACC_INTERFACE`.
- A normal class must not have both `ACC_FINAL` and `ACC_ABSTRACT`.
- `ACC_SUPER` is a historical flag; from Java SE 8 onward, the JVM treats this flag as enabled for every class file regardless of the bit stored in the file. **Do not** use the presence/absence of this flag to conclude that the source contains the `super` keyword.
- `ACC_MODULE` is a special case for `module-info.class` with its own structural rules: this flag must not be combined with other class flags.

### Modern Features That Are Not Regular Class Flags

- **Record** (`record Point(int x, int y) {}`) uses the **`Record` attribute** and corresponding structural rules. Do not assume `ACC_RECORD` is an official `access_flags` bit in the JVMS `ClassFile` table: some bytecode libraries may use an internal `ACC_RECORD` constant or pseudo flag for metadata representation.
- **Sealed class/interface** uses the **`PermittedSubclasses` attribute** to store the list of permitted subclasses; there is no `ACC_SEALED` in the access flags table in `4.1`.
- **Nest-based access** uses metadata such as `NestHost`/`NestMembers`, related to `private` access checks; it is not inferred from `ACC_PRIVATE` of a "top-level class" (a top-level class does not have an `ACC_PRIVATE` flag here).
- `ACC_SYNTHETIC` of a **class** only refers to a compiler-generated class; `ACC_SYNTHETIC` can also appear on fields/methods according to their respective tables.

## 4. `this_class` and `super_class`: Distinguishing Self from Direct Parent

### `this_class`

`this_class` must point to a `CONSTANT_Class_info` representing **the class or interface being defined**. The internal name uses `/` instead of dots:

~~~text
Source: package demo; public class App { }
Binary name: demo.App
JVM internal name: demo/App
Field descriptor (referencing App): Ldemo/App;
~~~

`demo/App` in the constant pool is the type name in internal form; `Ldemo/App;` is a **field descriptor**. They must be distinguished because their syntax and usage locations differ.

### `super_class`

In a regular class, `super_class` points to the `CONSTANT_Class_info` of the **direct superclass**:

~~~java
class Animal { }
class Dog extends Animal { }
class Poodle extends Dog { }
~~~

For `Poodle.class`:

~~~text
this_class  -> Poodle
super_class -> Dog
~~~

`Animal` is an **indirect superclass**, not directly stored in `super_class` of `Poodle.class`. The JVM knows the inheritance chain by moving to `Dog.class` and then looking up `Dog`'s superclass.

Important special cases:

1. **`java/lang/Object`**: the only regular class without a direct superclass, so `super_class = 0`.
2. **Interface**: in the **class-file format**, an interface's `super_class` points to `java/lang/Object`. This **does not mean** the interface `extends Object` in Java source; direct superinterfaces are in `interfaces[]`.
3. **`module-info.class` with `ACC_MODULE`**: `super_class = 0` by its own rule and `interfaces_count = fields_count = methods_count = 0`. Do not apply the "only Object has super_class 0" rule to a module descriptor and overlook this exception.

For a class that does not write `extends` in source, the superclass is normally `java/lang/Object`. A `final` class can **inherit** from another class, but does not allow a third class to inherit from it.

## 5. `interfaces_count` and `interfaces[]`

`interfaces_count` is the number of **direct superinterfaces**. The `interfaces[]` array contains each corresponding **index** to `CONSTANT_Class_info`, preserving **left-to-right order in source** according to JVMS.

Example:

~~~java
interface Identified {
    long id();
}

interface Named {
    String name();
}

class Base implements Identified {
    @Override public long id() { return 1; }
}

class Item extends Base implements Named, java.io.Serializable {
    @Override public String name() { return "Item"; }
}
~~~

For `Item.class`:

~~~text
this_class    = Item
super_class   = Base
interfaces[]  = [Named, java/io/Serializable]
interfaces_count = 2
~~~

**`Identified` does not appear in `Item.class.interfaces[]`**, even though `Item` inherits the implementation of that interface through `Base`. You need to read `Base.class` to see the `Base implements Identified` relationship.

If an interface writes `interface B extends A, C`, `B`'s file has `super_class -> java/lang/Object` but `interfaces[] -> [A, C]`. This is a bytecode-level structure; do not infer backward that Java source allows a class to `extends` multiple superclasses: Java only allows **one direct superclass**, but can have multiple interfaces.

The elements of `interfaces[]` do not contain method implementations. This table specifies **direct type relationships**; individual methods belong to `methods[]` of each corresponding type.

## 6. `fields[]`: Directly Declared Fields

Each field has an independent `field_info` according to JVMS `4.5`:

~~~text
field_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

`name_index` points to the field name as `CONSTANT_Utf8_info`, while `descriptor_index` points to the descriptor representing the **JVM-level data type**. Attributes provide additional metadata such as `ConstantValue`, `Signature`, annotations, or deprecation information.

| Java Field | Descriptor | Typical Flags |
| --- | --- | --- |
| `private int count;` | `I` | `ACC_PRIVATE` |
| `public static final long MAX = 10L;` | `J` | `ACC_PUBLIC, ACC_STATIC, ACC_FINAL` |
| `volatile boolean running;` | `Z` | `ACC_VOLATILE` |
| `transient String secret;` | `Ljava/lang/String;` | `ACC_TRANSIENT` |
| `String[] names;` | `[Ljava/lang/String;` | per modifiers |
| `List<String> items;` | `Ljava/util/List;` | `Signature` may hold generic signature |

Main field flags:

| Flag Name | Hex | Semantics |
| --- | --- | --- |
| `ACC_PUBLIC` / `ACC_PRIVATE` / `ACC_PROTECTED` | `0x0001` / `0x0002` / `0x0004` | Field access permissions |
| `ACC_STATIC` | `0x0008` | Field belongs to the class rather than each instance |
| `ACC_FINAL` | `0x0010` | Field has final assignment constraints |
| `ACC_VOLATILE` | `0x0040` | Volatile field with Java memory semantics |
| `ACC_TRANSIENT` | `0x0080` | Transient field, meaningful for related serialization mechanisms |
| `ACC_SYNTHETIC` | `0x1000` | Compiler-generated field |
| `ACC_ENUM` | `0x4000` | Field representing an enum constant |

**Restrictions:** a field cannot be both `public` and `private`; nor can it be both `ACC_FINAL` and `ACC_VOLATILE`. Fields declared in an interface must have `ACC_PUBLIC`, `ACC_STATIC`, and `ACC_FINAL` (and may also have `ACC_SYNTHETIC` according to the rules).

### Declared Fields, Inherited Fields, and Initial Values

A class's `fields[]` only contains fields **declared in that class**, without copying inherited fields from the parent. `new Child()` may have state belonging to `Base` and `Child`, yet `Child.class.fields[]` still only lists the declarations in `Child`.

`ACC_STATIC | ACC_FINAL` **does not automatically prove** the presence of a `ConstantValue` attribute: only certain qualifying compile-time constants use this attribute. Other initializers may be placed by the compiler into `<clinit>` for static fields, or `<init>`/instance initializers for instance fields. `field_info` defines the field and its metadata; it does not contain all the execution logic for value assignment.

For example, `static int created;` has a default value of `0` at preparation and does not need `<clinit>` just to receive 0. Whereas `static int created = calculate();` usually generates class initialization code.

## 7. `methods[]`: Methods and Special Initializers

Each `method_info` element according to JVMS `4.6`:

~~~text
method_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

`name_index` indicates the name, and `descriptor_index` indicates **parameters and return type**. Method descriptor syntax:

~~~text
(ParameterDescriptors)ReturnDescriptor

()V                      -> void noArgs()
(I)I                     -> int f(int)
(JLjava/lang/String;)V   -> void g(long, String)
([Ljava/lang/String;)V   -> void main(String[])
()Ljava/lang/String;     -> String get()
~~~

| Method-Level Flag | Hex | Interpretation |
| --- | --- | --- |
| `ACC_PUBLIC` / `ACC_PRIVATE` / `ACC_PROTECTED` | `0x0001` / `0x0002` / `0x0004` | Method access permissions |
| `ACC_STATIC` | `0x0008` | Static method |
| `ACC_FINAL` | `0x0010` | Cannot override this method |
| `ACC_SYNCHRONIZED` | `0x0020` | Executes with monitor mechanism upon invocation |
| `ACC_BRIDGE` | `0x0040` | Compiler-generated bridge method |
| `ACC_VARARGS` | `0x0080` | Method declared with varargs |
| `ACC_NATIVE` | `0x0100` | Has a native implementation |
| `ACC_ABSTRACT` | `0x0400` | Has no method body |
| `ACC_SYNTHETIC` | `0x1000` | Compiler-generated method |
| `ACC_STRICT` | `0x0800` in major versions 46–60 | Historical flag for `strictfp`; no longer has that meaning outside this major version range |

Reading bits by **context** is critically important:

- `0x0020` in **class flags** is `ACC_SUPER`, while in **method flags** it is `ACC_SYNCHRONIZED`.
- `0x0040` in **field flags** is `ACC_VOLATILE`, while in **method flags** it is `ACC_BRIDGE`.
- `0x0080` in **field flags** is `ACC_TRANSIENT`, while in **method flags** it is `ACC_VARARGS`.
- `ACC_FINAL` appears in class/field/method, but carries the constraint corresponding to each kind; do not infer that they all represent the same runtime operation.

### `Code` Attribute, Abstract, and Native

For normal methods without `ACC_ABSTRACT` or `ACC_NATIVE`, the implementation is described by the **`Code` attribute** (bytecode, stack/locals, exception table, and some metadata). An `abstract` method has no body to store bytecode; a `native` method is implemented via native mechanisms rather than having `Code` like a normal Java method.

A `.class` file may declare:

- `<init>`: **instance initialization method**, corresponding to a constructor at the JVM level, with a descriptor having return type `V`; each overloaded constructor has its own descriptor.
- `<clinit>`: **class/interface initialization method**, generated by the compiler when static initialization needs to be executed; not a method you call from Java source like `obj.<clinit>()`.
- `main`: just the name of a method in `methods[]`. The launcher choosing `main` as the entry point is a separate startup rule, and does not make this method a special entry in the `ClassFile` format.

`methods[]` also only contains **methods declared** in that class/interface, without copying inherited methods. A `default method` defined by an interface belongs to `methods[]` **of the interface**, and a class that merely inherits that implementation does not necessarily have the same `method_info` in its own file.

### Generics, Overloading, and Bridge Methods

The JVM uses **descriptors** to identify field/method types. For `List<String>`, the normal JVM descriptor is `Ljava/util/List;` after type erasure; generic information can be preserved via the **`Signature` attribute**, rather than becoming a runtime descriptor like `List<String>`.

Overloads are distinguished by different descriptors. In a class file, there cannot be two `field_info` entries with the same **name + descriptor**, nor two `method_info` entries with the same **name + descriptor**. Because a method descriptor includes the **return type**, bytecode and the Java language do not share the exact same rules for evaluating a valid "signature"; do not blindly apply Java source overloading rules as the complete rules of the class-file verifier.

For generic overriding or covariant returns, the compiler may generate a **bridge method** to preserve proper dispatch after erasure. A bridge typically carries `ACC_BRIDGE | ACC_SYNTHETIC`, has its own method descriptor, and has `Code` forwarding to the actual implementation. This is why `javap -p -v` sometimes displays more methods than the number of explicit methods in source.

## 8. Java 17+ Example: Reading a Class from Source to `javap`

Create a file `ClassLayout.java` in an empty directory. The following code **compiles and runs standalone with Java 17+**:

~~~java
interface Labeled {
    String label();

    default String formatted() {
        return "[" + label() + "]";
    }
}

abstract class Base {
    protected final long id;

    Base(long id) {
        this.id = id;
    }

    public long id() {
        return id;
    }
}

public final class ClassLayout extends Base
        implements Labeled, java.io.Serializable {

    private static final long serialVersionUID = 1L;
    private static int created;
    private final String name;

    public ClassLayout(long id, String name) {
        super(id);
        this.name = name;
        created++;
    }

    @Override
    public String label() {
        return name;
    }

    public int score(int bonus) {
        return name.length() + bonus;
    }

    public static int created() {
        return created;
    }

    public static void main(String[] args) {
        ClassLayout item = new ClassLayout(7L, "JVM");
        System.out.println(item.formatted());
        System.out.println("id=" + item.id()
                + ",score=" + item.score(2)
                + ",created=" + created());
    }
}
~~~

Run:

~~~bash
javac ClassLayout.java
java ClassLayout
~~~

**Exact stdout:**

~~~text
[JVM]
id=7,score=5,created=1
~~~

Explanation: `ClassLayout` inherits `id()` and field `id` from `Base`, implements `label()`, inherits `Labeled`'s default `formatted()`, and has its own `name` field. The constructor increments `created` once. `"JVM".length() + 2 = 5`.

When `javac ClassLayout.java` runs, the directory will contain `Labeled.class`, `Base.class`, and `ClassLayout.class`; each class/interface has its **own ClassFile**. The `Base` class is not "embedded wholesale" into `ClassLayout.class`.

### Using `javap` to Read the Structure

~~~bash
javap -p ClassLayout
javap -v -p ClassLayout
javap -v -p Base
javap -v -p Labeled
javap -c -p ClassLayout
~~~

`-p` shows `private` members as well, `-v` shows metadata/constant pool/descriptors/flags/attributes, and `-c` disassembles `Code`. The full output includes many `#index` values, BCIs, and constant pool entries that may vary by compiler version; therefore, below are **the relationships to verify**, without claiming every line of output is byte-for-byte identical across all JDKs.

| Inspection Point | What to Observe in `ClassLayout.class` |
| --- | --- |
| Class header/flags | `public final class ClassLayout extends Base implements Labeled, java.io.Serializable`; corresponding flags `ACC_PUBLIC`, `ACC_FINAL`, and usually `ACC_SUPER` |
| `this_class` | Constant-pool `Class` pointing to `ClassLayout` |
| `super_class` | Constant-pool `Class` pointing to `Base`, **not `java/lang/Object`** |
| `interfaces[]` | Two direct interfaces: `Labeled` and `java/io/Serializable` in source order |
| `fields[]` | `serialVersionUID`, `created`, `name` are directly declared |
| `methods[]` | Constructor `<init>`, `label`, `score`, `created`, `main`; other compiler-generated members only if needed by the compiler |
| Constructor `Code` | Calls `Base.<init>(long)`, assigns `name`, and increments `created` |
| `main` `Code` | Creates `ClassLayout`, calls `formatted`, `id`, `score`, and prints the results |

What **should not be expected in `ClassLayout.class` as its own declared elements**:

- Field `id`: belongs to `Base.fields[]`.
- Method `id()`: belongs to `Base.methods[]`.
- Default `formatted()`: belongs to `Labeled.methods[]`; `ClassLayout` does not override that method.
- `java/lang/Object` as direct `super_class`: this class extends `Base`, and `Base` directly extends `Object`.

### Actual Descriptors of Methods/Fields

| Declaration | Descriptor in `ClassLayout.class` |
| --- | --- |
| `private static final long serialVersionUID` | `J` |
| `private static int created` | `I` |
| `private final String name` | `Ljava/lang/String;` |
| `ClassLayout(long, String)` | `(JLjava/lang/String;)V` |
| `String label()` | `()Ljava/lang/String;` |
| `int score(int bonus)` | `(I)I` |
| `static int created()` | `()I` |
| `static void main(String[])` | `([Ljava/lang/String;)V` |

`serialVersionUID` is a compile-time constant `long` and usually has `ConstantValue: long 1l`, while `created` defaults to 0 and is incremented in the constructor. Do not infer from two fields both being `static` that they must have the same attributes or the same initialization code.

### Reading a Field and a Method Schematically

The output below is **abbreviated for learning the structure**; it is not an actual dump:

~~~text
fields_count: 3
  field_info:
    access_flags: ACC_PRIVATE | ACC_FINAL
    name_index:        #... -> Utf8 "name"
    descriptor_index:  #... -> Utf8 "Ljava/lang/String;"
    attributes: ...

methods_count: ...
  method_info:
    access_flags: ACC_PUBLIC
    name_index:        #... -> Utf8 "score"
    descriptor_index:  #... -> Utf8 "(I)I"
    attributes:
      Code -> bytecode, max_stack, max_locals, exception_table, ...
~~~

Each `#...` is an index into the constant pool, which is different from the bytecode offsets printed by `javap -c`.

## 9. Cases That May Be Surprising in Real Files

### A. Interface Extending Interfaces

~~~java
interface Root { void root(); }
interface Left extends Root { }
interface Right extends Root { }
interface Combined extends Left, Right { }
~~~

`Combined.class` has `super_class -> java/lang/Object` and `interfaces[] -> [Left, Right]`. `Root` is an **indirect** interface ancestor and does not automatically appear in the list of direct superinterfaces. `Combined.methods[]` may **declare no new methods** because `root()` is inherited.

### B. `enum` and Annotation Interface

An enum has class-level `ACC_ENUM`; fields representing each enum constant also have `ACC_ENUM` **in field flags**. An annotation interface has `ACC_INTERFACE`, `ACC_ABSTRACT`, and `ACC_ANNOTATION`; its methods describe annotation elements, which differ from regular instance methods of a class. When encountering flags, read them according to the **file type** being analyzed.

### C. Record and Sealed Class

~~~java
record Coordinate(int x, int y) { }

sealed interface Shape permits Circle, Rectangle { }
record Circle(double radius) implements Shape { }
record Rectangle(double width, double height) implements Shape { }
~~~

This is a **Java 17+ source example**, though not a program with `main` to run directly. For a record, check the `Record` attribute, superclass `java/lang/Record`, component metadata, and compiler-generated fields/accessor methods. For a sealed interface, inspect the `PermittedSubclasses` attribute. **Do not** look for `ACC_RECORD` or `ACC_SEALED` in the class-level `access_flags` table of JVMS `4.1`.

### D. Compiler-Generated Methods

When viewing source with generics/bridges, lambdas, or nested classes, `methods_count` does not necessarily equal the number of method declarations in source. The compiler may generate helper methods with `ACC_SYNTHETIC`, `ACC_BRIDGE`, and other metadata attributes. When reading `javap`, separate **actual declarations in the class file** from **declarations you see in source**.

### E. Module Descriptor

`module-info.class` is a special structure. It uses `ACC_MODULE`, `this_class = module-info`, `super_class = 0`, and `interfaces_count = fields_count = methods_count = 0`, while also containing the `Module` attribute according to specification rules. If a parser tool assumes this is a normal class inheriting `Object` or always requires a constructor, the parser is misreading the `ACC_MODULE` case.

## 10. Common Mistakes When Analyzing or Writing a Parser

| Mistake | Corrected Understanding |
| --- | --- |
| Treating `this_class`/`super_class` numbers as encoded name strings | They are **indices** to `CONSTANT_Class_info` in the constant pool |
| Assuming `super_class` equal to 0 means a class has no parent in all cases | `Object` is the regular class with zero; `module-info.class` has a special rule |
| Thinking `interfaces[]` lists every interface inherited through the superclass | It only lists **direct superinterfaces** of the class/interface being read |
| Seeing `fields[]` missing parent fields and concluding the object lacks that state | Parent fields belong to the superclass's `fields[]`, not copied into the subclass |
| Treating `methods[]` as all methods an object can call | Only methods declared in the class; inherited/default methods reside where they are defined |
| Interpreting `0x0040` without checking the structure | It is `ACC_VOLATILE` for fields, `ACC_BRIDGE` for methods |
| Treating `ACC_SUPER` as source `super` or which class is being extended | It is a historical flag for `invokespecial`; read `super_class` to know the direct parent |
| Looking for `ACC_RECORD` or `ACC_SEALED` in JVMS ClassFile flags | Check the `Record` and `PermittedSubclasses` attributes |
| Assuming a `static final` field always has its value in `ConstantValue` | Only certain qualifying constants do; other static initialization may be in `<clinit>` |
| Thinking `main` is a special `ClassFile` field outside `methods[]` | `main` is a regular `method_info`, chosen by the launcher under entry rules |
| Equating a method descriptor with a generic signature | Descriptors use erased JVM types; `Signature` can supplement generic metadata |
| Using `javap -c` to infer the entire API and metadata | Combine with `javap -v -p` to see flags, descriptors, constant pool, and attributes |

## 11. Practical Workflow and Checklist for Reading a Class File

When given any `.class` file, this sequence helps analyze it systematically:

1. **Check source and file version:** `javap -verbose ClassName`, find `major version`, `minor version`, `this_class`, and `flags`.
2. **Read identity/type relationships:** confirm `this_class`, `super_class`, `interfaces_count`, and the order of `interfaces[]`; if there are inheritance questions, open the superclass/interface files as well.
3. **Read access flags from the right table:** class in JVMS `4.1`; field in `4.5`; method in `4.6`. Do not interpret bitmasks across tables.
4. **Separate members:** how many declared elements `fields_count`/`methods_count` actually have; compare with source and inherited members.
5. **Read descriptors:** translate notations like `I`, `J`, `Ljava/lang/String;`, `[I`, `(I)I` into their corresponding data types.
6. **Read attributes where they belong:** `ConstantValue` on fields; `Code` on executable methods; `Signature` for generics; `Record`, `PermittedSubclasses`, `Nest*` at the type level per specification.
7. **If there is a link/verify/access error:** cross-check class-file version, constant pool structure, flag combination rules, descriptors, and runtime access permissions. Do not infer from source while ignoring the actual class file.

Common commands (Java 17+):

~~~bash
javap -help
javap -p ClassLayout
javap -v -p ClassLayout
javap -c -p ClassLayout
javap -v -p Labeled
~~~

If the class is in a package or JAR, use the fully qualified name with classpath:

~~~bash
javap -v -p -classpath app.jar demo.ClassLayout
~~~

`javap` is a class-file inspection tool and does not need to run `main`. For files of unknown origin, prefer offline inspection and do not load/run classes just to "take a look". `javap` output is not a raw byte-for-byte dump, but it is well suited for learning the structural relationships above.

## 12. Self-Check Questions

**Question 1.** `ClassLayout` extends `Base`, `Base` extends `Object`. What is `ClassLayout.class.super_class`?  
**Answer:** `Base`. `Object` is an indirect ancestor of `ClassLayout`.

**Question 2.** `ClassLayout` directly implements only `Labeled` and `Serializable`. What is `interfaces_count`?  
**Answer:** 2, because it counts the **direct superinterfaces** in that class's own file.

**Question 3.** Why does `ClassLayout.methods[]` not necessarily contain `formatted()`?  
**Answer:** Because `formatted()` is a default method declared in `Labeled`; the class inherits the implementation through the interface and does not need a `method_info` for that method if it does not override it.

**Question 4.** If you see `0x0020` in the flags of a class and a method, do they mean the same thing?  
**Answer:** No. Class: `ACC_SUPER`; method: `ACC_SYNCHRONIZED`.

**Question 5.** What are the descriptor and main flags of `private final String name`?  
**Answer:** Descriptor `Ljava/lang/String;`, flags `ACC_PRIVATE` and `ACC_FINAL`.

**Question 6.** Why is `main([Ljava/lang/String;)V` still located in `methods[]`?  
**Answer:** Because `main` is a method of the class; the launcher selects it as the entry point, but the class format does not create a separate `main` table.

**Question 7.** When reading a `record` or `sealed class`, is it correct to look for `ACC_RECORD`/`ACC_SEALED` bits?  
**Answer:** Not in the standard `ClassFile.access_flags` table. Check the `Record`/`PermittedSubclasses` attributes and related metadata.

**Question 8.** Why does generics `List<String>` usually show the descriptor `Ljava/util/List;`?  
**Answer:** JVM descriptors use erased types; the `Signature` attribute may store additional generic type information.

## 13. Standard Reference Documentation

- [JVMS Java SE 25 — `4.1` The ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.1): entire class file layout, class `access_flags`, `this_class`, `super_class`, `interfaces`, `fields`, and `methods`.
- [JVMS Java SE 25 — `4.2` Names](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.2): internal names and binary names.
- [JVMS Java SE 25 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.3): field descriptors and method descriptors.
- [JVMS Java SE 25 — `4.5` Fields](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.5): `field_info`, flags, static/final/volatile constraints, and interface fields.
- [JVMS Java SE 25 — `4.6` Methods](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.6): `method_info`, flags, `<init>`/`<clinit>` methods.
- [JVMS Java SE 25 — `4.7` Attributes](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7): `Code`, `ConstantValue`, `Signature`, `Record`, `PermittedSubclasses`, and other metadata.
- [Java `javap` manual, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): `-v`, `-p`, `-c` options and how to inspect binaries.
- [Java SE Specifications](https://docs.oracle.com/javase/specs/): choose the right JVMS release if analyzing class files produced by a different JDK.

**Key takeaway:** `access_flags` describes **properties of the type being declared**; `this_class`/`super_class`/`interfaces[]` describe **identity and direct relationships** through the constant pool; `fields[]` and `methods[]` describe **members declared in that type itself**. Reading them alongside descriptors and attributes will help you understand the class file structure without equating it with Java source syntax.