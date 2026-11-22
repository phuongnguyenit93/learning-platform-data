# Binary Names, Internal Names, and Descriptors of Fields, Methods, and Arrays

## 1. Why must these name representations be distinguished?

In Java, a class can be referred to in multiple forms:

~~~text
Java source code:           java.lang.String
Binary name:                java.lang.String
JVM internal name:          java/lang/String
Reference type descriptor:  Ljava/lang/String;
String[] array descriptor:  [Ljava/lang/String;
~~~

These strings **are not arbitrarily interchangeable**. They serve different roles in Java source, the Java Virtual Machine Specification (JVMS), **.class** files, bytecode reading tools, and the Reflection API. Confusion usually only surfaces when writing code that processes bytecode, looking up classes via reflection, generating proxies, using instrumentation, querying methods by descriptor, or interpreting constant pool information.

After this lesson, you can:

- Identify binary names, internal names, and canonical/source names of regular classes and nested classes.
- Read and construct **field descriptors** for primitives, references, and one- or multi-dimensional arrays.
- Read and construct **method descriptors**, including parameter lists, return types, and **void**.
- Explain why **java.lang.String**, **java/lang/String**, **Ljava/lang/String;**, and **[Ljava.lang.String;** appear in different APIs/contexts.
- Understand how names/descriptors appear in **CONSTANT_Class**, **CONSTANT_NameAndType**, **CONSTANT_Fieldref**, and **CONSTANT_Methodref**.
- Verify results using **javap -s -p -v**, **Class.getName()**, **Class.getCanonicalName()**, **Class.forName()**, and **MethodType**.

The focus is on the exact meaning of the class file format; this lesson uses Java 17+ for illustration.

## 2. Names in Java: source, canonical, and binary name

### 2.1. What is a binary name?

A **binary name** is the name defined by the Java Language Specification (JLS, §13.1) to identify a class/interface type according to the rules used in binary form. For common top-level classes, the binary name is the same as the fully qualified name commonly seen in source code:

~~~text
java.lang.String
java.util.Map
com.example.app.Customer
~~~

The dot **.** separates package components. For a **member class** declared inside another class, the binary name uses **$** to join the binary name of the enclosing class and the simple name of the member class:

~~~java
// Example illustrating declaration structure:
package com.example.app;

class Outer {
    static class Inner {}
}
~~~

~~~text
Source/canonical name of member class: com.example.app.Outer.Inner
Binary name of member class:           com.example.app.Outer$Inner
Binary name of top-level class:        com.example.app.Outer
~~~

Not every **$** character proves there is a nested class: Java allows **$** in identifiers, and local/anonymous classes have their own compiler-generated binary name rules. Also, do not use a rule like "replace every dot with $" to turn a source name into a binary name: package dots remain dots.

The binary name is also tied to class identity at runtime together with the **defining class loader**; two different class loaders can define classes with the same binary name that the JVM still treats as distinct runtime classes.

### 2.2. Canonical name is not synonymous with binary name

A **canonical name** is the way of writing a name according to Java language rules for types that have a canonical name. For a member class, this notation uses a dot between **Outer** and **Inner**; the binary name uses **$**.

Reflection often shows:

| Class | **Class.getName()** | **Class.getCanonicalName()** |
| --- | --- | --- |
| **java.lang.String** | **java.lang.String** | **java.lang.String** |
| **Outer.Inner** | **Outer$Inner** (if in no package) | **Outer.Inner** |
| **int** | **int** | **int** |
| **String[]** | **[Ljava.lang.String;** | **java.lang.String[]** |
| **int[][]** | **[[I** | **int[][]** |

**getCanonicalName()** can return **null** for local or anonymous classes that have no canonical name. **getName()** of an array uses a descriptor-like representation, but **the reference component name is written with dots**, unlike an object descriptor in a class file which uses slashes. A later section will explain this clearly.

### 2.3. Internal name: the JVM's internal name

When representing the binary name of a class/interface in class file structures that require **internal form**, the JVMS replaces package dots **.** with forward slashes **/**.

~~~text
Binary name:   java.lang.String
Internal name: java/lang/String

Binary name:   com.example.app.Outer$Inner
Internal name: com/example/app/Outer$Inner
~~~

**The $ of a member class is preserved**, not changed to a slash. **/** in an internal name is a package/class component separator according to JVM grammar, **not a guarantee of an actual file path on disk**.

For example, in a JAR, the entry **com/example/app/Outer$Inner.class** typically corresponds to that class; however, execution may use modules, custom class loaders, byte arrays, or other class sources. The internal name is an identification concept in the class file and should not be equated with filesystem APIs.

## 3. Three strings commonly misused

Consider the type **java.lang.String**:

| String | Correct role | Where is it used? |
| --- | --- | --- |
| **java.lang.String** | Binary name | **Class.forName("java.lang.String")**, metadata/class names according to Java rules |
| **java/lang/String** | Internal name of the class | **CONSTANT_Class** for a non-array class; the class name part inside an object descriptor |
| **Ljava/lang/String;** | Field descriptor of a reference to String | **field_info.descriptor_index**; parameter/return type of a method descriptor |

**The L prefix and ;** are grammatical components of a descriptor for an **object/reference type**. Therefore, **java/lang/String** alone **is not a field descriptor** and **Ljava/lang/String;** **is not a class internal name**.

Some bytecode tools take name arguments as internal names, whereas the reflection API takes binary names. Before passing a name string to a library, read the contract carefully: one API requires an **owner internal name**, another requires a **type descriptor**, and another needs a **binary name**. Conversion between them must only be performed according to the exact data kind.

## 4. What is a descriptor in a class file?

A **descriptor** is a compact syntax string representing the **type of a field** or the **parameter set and return type of a method**. Descriptor strings are stored in the constant pool as modified UTF-8 strings according to the class file format; **field_info**, **method_info**, or **NameAndType** structures reference it by index.

The JVMS specification distinguishes:

- **Field descriptor**: represents a value type, including primitive, object/reference, or array.
- **Method descriptor**: represents the parameter types in sequence inside **(...)** followed by the return type.
- **Generic signature**: additional information about generic type arguments/type variables; uses a **Signature** grammar distinct from regular descriptors.

Descriptors are data with execution/linking meaning; **a generic signature does not replace a descriptor**.

## 5. Field descriptor code table for primitives

Each primitive type uses exactly one ASCII character:

| Java type | Descriptor | Field example |
| --- | --- | --- |
| **byte** | **B** | **byte count** → **B** |
| **char** | **C** | **char initial** → **C** |
| **double** | **D** | **double score** → **D** |
| **float** | **F** | **float ratio** → **F** |
| **int** | **I** | **int age** → **I** |
| **long** | **J** | **long total** → **J** |
| **short** | **S** | **short level** → **S** |
| **boolean** | **Z** | **boolean active** → **Z** |

Two things to remember:

1. **J** is the code for **long**, not **L**. The character **L** is reserved for object reference types.
2. **V** represents **void** when it stands in the **method return type position**; **void is not a field type**, nor can it be an element of an array descriptor.

For example, **int** is **I**, not **int**; **boolean** is **Z**, not **B** or **boolean**.

Descriptor characters identify the **declared type**. The fact that the JVM uses computational **int** for many instructions operating on byte/short/char/boolean does not turn the descriptors **B/S/C/Z** into **I**.

## 6. Descriptor of object reference types

Object type grammar:

~~~text
L<internal-name>;
~~~

Where **L** is the leading character, **internal-name** uses **/**, and **;** terminates the type.

Examples:

| Java type | Internal name | Field descriptor |
| --- | --- | --- |
| **String** | **java/lang/String** | **Ljava/lang/String;** |
| **Object** | **java/lang/Object** | **Ljava/lang/Object;** |
| **java.util.List** | **java/util/List** | **Ljava/util/List;** |
| **com.example.Customer** | **com/example/Customer** | **Lcom/example/Customer;** |
| **com.example.Outer.Inner** | **com/example/Outer$Inner** | **Lcom/example/Outer$Inner;** |

For **Lcom/example/Outer$Inner;**:

~~~text
L        com/example/Outer$Inner       ;
^        ^                              ^
start    internal binary name           end of object descriptor
~~~

Do not write **Lcom.example.Outer.Inner;** in a class-file descriptor. The dot between **Outer.Inner** in a canonical/source name also cannot replace the **$** of a member-class binary name.

### 6.1. Unqualified names

A field name or method name is stored as an **unqualified name**, for example **count**, **parse**, **equals**. They do not contain **.**, **;**, **[**, **/**; most method names are also restricted from containing **<** and **>**, except for the special names **<init>** and **<clinit>**.

A field name or method name **is not combined with its descriptor into a single string in the class file**. They appear in separate entries: name **count** + descriptor **I**, or name **accept** + descriptor **(I)Z**. Notations like **accept(I)Z** often seen in documentation/logs are a combined representation for readability, not field descriptor syntax.

## 7. Array descriptor: add one [ for each dimension

An **array descriptor** is formed by one or more **[** characters preceding the descriptor of the final element type. Each **[** corresponds to one dimension.

~~~text
T[]     -> [ + descriptor(T)
T[][]   -> [[ + descriptor(T)
T[][][] -> [[[ + descriptor(T)
~~~

Examples:

| Java type | Array descriptor | How to read |
| --- | --- | --- |
| **int[]** | **[I** | One-dimensional array, component is int |
| **int[][]** | **[[I** | Two-dimensional array, final component is int |
| **boolean[]** | **[Z** | One-dimensional boolean array |
| **byte[][]** | **[[B** | Two-dimensional byte array |
| **String[]** | **[Ljava/lang/String;** | One-dimensional String array |
| **String[][]** | **[[Ljava/lang/String;** | Two-dimensional String array |
| **Outer.Inner[]** | **[Lcom/example/Outer$Inner;** | One-dimensional member class array |
| **double[][][]** | **[[[D** | Three-dimensional double array |

**The position of [ matters:** the descriptor **[I** (int[]) differs from **I** (int); **[[I** (int[][]) also differs from **[I** (int[]). In Java, a multi-dimensional array is actually an array whose elements are arrays; the descriptor represents the nesting level and does not require all rows to have the same length.

**Class file limit:** a valid array type descriptor has at most **255 dimensions**; this does not mean an application should or has enough RAM to create a 255-dimensional array. It is not possible to create a **void[]** array type or a **[V** descriptor.

### 7.1. Reference arrays: dots or slashes?

Distinguish these three notations very carefully:

~~~text
Source type:
    java.lang.String[]

Field descriptor in class file:
    [Ljava/lang/String;

Class.getName() of String[].class:
    [Ljava.lang.String;
~~~

**Class.getName()** is special: for reference arrays, it uses **dots in the binary name part of the component type**, whereas the array descriptor in the class file uses the **internal name with /**. The two representations look similar but are different character strings.

For primitive arrays, there is no package name to convert, so **int[]** produces the string **[I** in both array descriptor form and **getName()**.

### 7.2. Arrays also have Class objects

An array class object can be obtained via **String[].class** or **int[][].class**, and has a display name according to runtime rules. This does not generate Java source declaring a class **[I**. Array types are distinct runtime types, and the class file constant pool can contain a **CONSTANT_Class** holding an array name in descriptor form, such as **[Ljava/lang/String;**.

For **CONSTANT_Class**:
- If referencing a regular class/interface, the name string is usually in **internal form**, for example **java/lang/String**.
- If referencing an array class, the string represents an **array descriptor**, for example **[Ljava/lang/String;**.

Therefore, the statement "every **CONSTANT_Class** contains an internal name without [" is false. This is a very worthwhile distinction to check when reading the constant pool.

## 8. Method descriptor: (parameters)return type

Core grammar:

~~~text
MethodDescriptor:
    ( ParameterDescriptor* ) ReturnDescriptor

ParameterDescriptor:
    FieldType

ReturnDescriptor:
    FieldType | V
~~~

That means: **(**, directly concatenating the field descriptors of all parameters **in exact order**, **)**, and then a descriptor for the return type or **V** for **void**.

There are no commas or spaces separating parameters in a standard descriptor.

| Java declaration | Method descriptor |
| --- | --- |
| **void run()** | **()V** |
| **int sum(int a, int b)** | **(II)I** |
| **boolean valid(String text)** | **(Ljava/lang/String;)Z** |
| **String join(String a, String b)** | **(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;** |
| **long convert(int n, double d)** | **(ID)J** |
| **String[] lookup(int[] ids, String[][] names)** | **([I[[Ljava/lang/String;)[Ljava/lang/String;** |
| **void accept(boolean[] flags, long n)** | **([ZJ)V** |
| **Object identity(Object x)** | **(Ljava/lang/Object;)Ljava/lang/Object;** |

Breaking down an example:

~~~text
([I[[Ljava/lang/String;)[Ljava/lang/String;
 | |                | |  
 | +-- int[]       | +-- String[] (return)
 +-- parameter 1   +-- parameter 2 is String[][]
~~~

More precisely, the content between **(** and **)** consists of two concatenated parameters: **[I** and **[[Ljava/lang/String;**. After **)** is **[Ljava/lang/String;**. With the **;** character, you must know it terminates the object descriptor; subsequent characters may be the descriptor of the next parameter.

### 8.1. The return type is part of the method descriptor

The two method descriptors **(I)I** and **(I)J** are different because their return types differ. The JVM can distinguish symbolic reference information at the name and descriptor level; whereas **Java source does not allow overloading a method solely by changing the return type**.

~~~java
// These two declarations in the same class are an error in Java source:
// int find(int id)  { return id; }
// long find(int id) { return id; }
~~~

Do not infer that Java language overloading rules are identical to every structural rule of the class file. The method name and descriptor together participate in bytecode identification/linking; Java's compile-time rules also depend on signature/overload resolution.

### 8.2. Is the this parameter included in the descriptor?

No. For instance methods, **this** is passed implicitly by the method invocation instruction; **there is no this parameter descriptor at the beginning**.

~~~java
class Account {
    int deposit(int amount) {
        return amount;
    }
}
~~~

The method descriptor of **deposit** is **(I)I**, **not** **(LAccount;I)I**.

When viewing the bytecode of an instance method, local slot 0 usually holds **this**, but the local variables layout does not turn **this** into an explicit parameter of the method descriptor.

### 8.3. Parameter slot count limit

The JVMS limits the total **parameter length** of a method descriptor to **255 units**. A **long** or **double** parameter each counts as **2**; all other types, including array/reference, count as **1**. For instance/interface method invocations, the limit also counts the implicit **this** as **1** unit, even though **this** does not appear in the descriptor string.

This is a limit of the JVM model, **not** a limit on the number of text characters in the descriptor.

## 9. Where do they live in the class file and constant pool?

A class file has a **constant_pool** structure, followed by the field and method declaration tables. At a minimal level:

~~~text
ClassFile
  constant_pool
    CONSTANT_Utf8        "demo/names/NameDemo"
    CONSTANT_Class       -> Utf8 internal name
    CONSTANT_Utf8        "count"
    CONSTANT_Utf8        "I"
    CONSTANT_Utf8        "check"
    CONSTANT_Utf8        "(I[Ljava/lang/String;)Z"
    CONSTANT_NameAndType -> name + descriptor
    CONSTANT_Fieldref    -> class + name_and_type
    CONSTANT_Methodref   -> class + name_and_type
  fields[]
    field_info
      name_index        -> "count"
      descriptor_index  -> "I"
  methods[]
    method_info
      name_index        -> "check"
      descriptor_index  -> "(I[Ljava/lang/String;)Z"
~~~

The diagram illustrates the **roles** of the elements, not the actual offsets of a specific class file. The constant pool uses multiple entry types related by indices; a field declaration does not necessarily have a **Fieldref** pointing back to itself. **Fieldref/Methodref** appear when there is a corresponding symbolic reference (for example, a bytecode instruction that needs to reference a field/method).

In a class file:
- **field_info** stores the **simple name** and **field descriptor**.
- **method_info** stores the **simple name** and **method descriptor**.
- **CONSTANT_NameAndType** pairs a member name with a descriptor for use in symbolic references and other structures.
- **CONSTANT_Fieldref**, **CONSTANT_Methodref**, or **CONSTANT_InterfaceMethodref** combines an owner class/interface and a **NameAndType**.
- **CONSTANT_Class** usually points to a class internal name or an array descriptor, depending on the referenced target.

### 9.1. Example of decoding a call

Suppose the Java code is:

~~~java
// Illustrative code; requires java.lang.String and code inside a method:
int length = "Java".length();
~~~

The symbolic reference of the method **String.length()** describes:

~~~text
Owner class internal name: java/lang/String
Method name:               length
Method descriptor:         ()I
~~~

Familiar notation:

~~~text
java/lang/String.length:()I
~~~

This is a **notation for presenting a symbolic reference**, not a single method descriptor string. The descriptor is only **()I**; the owner and method name are separate components.

### 9.2. Initialization methods

Constructors typically appear in the class file with method name **<init>** and a descriptor ending in **V**, for example:

~~~text
<init>(Ljava/lang/String;I)V
~~~

The special name **<clinit>** represents the class/interface initialization method in the class file, having the descriptor **()V** according to JVM rules. These are not methods written directly with the names **<init>** or **<clinit>** in Java source.

## 10. Standalone Java 17+ example to observe names and descriptors

Create the file structure:

~~~text
demo/
  names/
    NameDemo.java
~~~

Contents of **demo/names/NameDemo.java**:

~~~java
package demo.names;

import java.lang.invoke.MethodType;

public class NameDemo {
    private int count;
    private String[] titles;
    private int[][] grid;
    private Item item;

    public static class Item {
    }

    public static boolean check(int limit, String[] names) {
        return limit > 0 && names != null;
    }

    public static String[] convert(int[] ids, Item item) {
        return new String[] {String.valueOf(ids.length), item.getClass().getSimpleName()};
    }

    public static void main(String[] args) {
        Class<?> nested = Item.class;
        Class<?> nestedArray = Item[][].class;

        System.out.println("outer=" + NameDemo.class.getName());
        System.out.println("nestedBinary=" + nested.getName());
        System.out.println("nestedCanonical=" + nested.getCanonicalName());

        System.out.println("arrayGetName=" + nestedArray.getName());
        System.out.println("arrayCanonical=" + nestedArray.getCanonicalName());
        System.out.println("intArrayGetName=" + int[][].class.getName());
        System.out.println("stringArrayGetName=" + String[].class.getName());

        MethodType method = MethodType.methodType(
                boolean.class, int.class, String[].class);
        System.out.println("methodDescriptor=" + method.toMethodDescriptorString());
    }
}
~~~

From the directory **containing the demo folder**, using JDK 17+:

~~~bash
mkdir out
javac -encoding UTF-8 -d out demo/names/NameDemo.java
java -cp out demo.names.NameDemo
~~~

If **out** already exists, skip the **mkdir out** command. **stdout output of the program**:

~~~text
outer=demo.names.NameDemo
nestedBinary=demo.names.NameDemo$Item
nestedCanonical=demo.names.NameDemo.Item
arrayGetName=[[Ldemo.names.NameDemo$Item;
arrayCanonical=demo.names.NameDemo.Item[][]
intArrayGetName=[[I
stringArrayGetName=[Ljava.lang.String;
methodDescriptor=(I[Ljava/lang/String;)Z
~~~

Explanation of results:

1. **getName()** of a regular/member class returns the **binary name** with package dots and **$** between nested member classes.
2. **getCanonicalName()** of a member class uses **.** between the outer/inner class.
3. **Item[][].class.getName()** has the **[[** prefix and the reference component part uses the binary name with **dots**: **[[Ldemo.names.NameDemo$Item;**.
4. **Item[][].class.getCanonicalName()** displays the source form **demo.names.NameDemo.Item[][]**.
5. The primitive array **int[][]** uses **[[I**.
6. **MethodType.toMethodDescriptorString()** provides the descriptor in exact class file syntax: **(I[Ljava/lang/String;)Z**. The **check** method has those exact parameters and return type.

The fields are declared to be observed in bytecode; no runtime values need to be assigned for **javap** to display their descriptors.

### 10.1. Viewing field and method descriptors with javap

Run:

~~~bash
javap -classpath out -p -s demo.names.NameDemo
javap -classpath out -p -s 'demo.names.NameDemo$Item'
~~~

In some shells (such as PowerShell), single quotes around a class name containing **$** help prevent variable interpolation. Quote syntax needs to be adjusted to the shell in use; in Bash, single quotes can also be used as above.

In the output for class **NameDemo**, look for these name/descriptor pairs:

~~~text
private int count;
  descriptor: I

private java.lang.String[] titles;
  descriptor: [Ljava/lang/String;

private int[][] grid;
  descriptor: [[I

private demo.names.NameDemo$Item item;
  descriptor: Ldemo/names/NameDemo$Item;

public static boolean check(int, java.lang.String[]);
  descriptor: (I[Ljava/lang/String;)Z

public static java.lang.String[] convert(int[], demo.names.NameDemo$Item);
  descriptor: ([ILdemo/names/NameDemo$Item;)[Ljava/lang/String;
~~~

These are **the key lines to compare**, with no guarantee that every part of **javap** output is identical across versions/compilation setups. Types are presented in the declaration line in a human-readable way; the string after **descriptor:** follows JVM syntax.

### 10.2. Viewing the constant pool and symbolic references

Run:

~~~bash
javap -classpath out -v -p demo.names.NameDemo
~~~

Look for strings similar to:

~~~text
demo/names/NameDemo
demo/names/NameDemo$Item
java/lang/String
(I[Ljava/lang/String;)Z
([ILdemo/names/NameDemo$Item;)[Ljava/lang/String;
~~~

With **-v**, the output includes class file info, constant pool, attributes, and code; **#n** index numbers, constant pool positions, and other minor details may vary. Observe the relationships between **Class**, **Utf8**, **NameAndType**, and method/field references rather than memorizing indices.

### 10.3. Reading bytecode without confusing names

A disassembly line might show:

~~~text
Method java/lang/String.valueOf:(I)Ljava/lang/String;
~~~

This line contains the **owner internal name** (java/lang/String), **method name** (valueOf), and **method descriptor** ((I)Ljava/lang/String;). Even when displayed together, they remain three semantically independent components.

## 11. Reflection API and loading classes by name

Java Reflection provides several ways to view names, but **these operations are not uniform in string format**.

| API | Used for | Example |
| --- | --- | --- |
| **Class.getName()** | Binary name of a regular class; special encoding for array classes | **String.class.getName()** → **java.lang.String** |
| **Class.getCanonicalName()** | Canonical name when available | **String[].class.getCanonicalName()** → **java.lang.String[]** |
| **Class.getSimpleName()** | Shorter, friendlier name | **NameDemo.Item.class.getSimpleName()** → **Item** |
| **Class.getTypeName()** | Type name for display, arrays have **[]** | **String[][].class.getTypeName()** → **java.lang.String[][]** |
| **Class.forName(String)** | Look up a class by binary name (or supported array-name encoding) | **Class.forName("java.lang.String")** |
| **MethodType.toMethodDescriptorString()** | Descriptor of a method type | **MethodType.methodType(void.class, int.class)** → **(I)V** |

For member classes, **Class.forName** uses the binary name containing **$**:

~~~java
// Illustrative snippet placed in a method that throws ClassNotFoundException:
Class<?> c = Class.forName("demo.names.NameDemo$Item");
~~~

The string **demo.names.NameDemo.Item** is a canonical/source name and **does not** substitute for the binary name of a member class in **Class.forName**.

### 11.1. Class.forName and array names

For array classes, **Class.forName** accepts an array-name encoded string matching the **Class.getName()** format:

~~~java
// Illustrative snippet, may throw ClassNotFoundException:
Class<?> strings = Class.forName("[Ljava.lang.String;");
Class<?> ints2d = Class.forName("[[I");
Class<?> nested2d = Class.forName("[[Ldemo.names.NameDemo$Item;");
~~~

Note that **[Ljava.lang.String;** uses **dots** in the binary component name. Passing the class-file descriptor string **[Ljava/lang/String;** directly to **Class.forName** is an invalid name format in this API.

Do not use **Class.forName("int[]")** or **Class.forName("[Ljava/lang/String;")** out of habit without checking the contract: array classes have a special name form, whereas **int[].class** is the direct and safe expression in source code.

### 11.2. When do you need to convert names?

- From a **regular class binary name** to internal name: replace **package dots** with **/** and keep **$** of member classes.
- From a reference class internal name to field descriptor: concatenate **L** + internal name + **;**.
- From a type descriptor to an array: prepend **[** for each dimension.
- From a descriptor back to a Java type: requires a grammar-compliant parser; simple dot replacement is not enough.
- With reflection, prefer operating on **Class<?>**, **Method**, **MethodType**, and standard APIs when possible; only construct descriptor strings manually when truly needed to integrate with JVM formats/bytecode tooling.

## 12. Generic signature is not the same as a descriptor

Suppose there is a field:

~~~java
// Code illustrating a class field:
java.util.List<String> names;
~~~

The **field descriptor** is still:

~~~text
Ljava/util/List;
~~~

The **String** type argument information does not appear in the basic descriptor, because Java generics rely primarily on **type erasure**. If the class file retains the appropriate generic metadata, the **Signature** attribute will carry the generic representation (for example **Ljava/util/List<Ljava/lang/String;>;**).

Similarly, two methods with **List<String>** and **List<Integer>** as parameters do not become two valid Java overloads merely by differing in generic type arguments, because erasure results in the same parameter type/signature at the corresponding checking layer.

Distinguish the terms:

| Term | What does it contain? |
| --- | --- |
| **Descriptor** | Field type or parameter/return types used by the JVM for linking/execution |
| **Signature attribute** | Generic parameterized types, type variables, and bounds in declarations that have generic data |
| **Method name** | Simple name, e.g. **find** |
| **Binary/internal name** | Class/interface name, not the entire method type |
| **Source declaration** | Java syntax including modifiers, generic arguments, parameter names... which descriptors do not store in full |

Do not pass a generic signature string into a place that expects a field descriptor; **<...>** belongs to a different grammar and can cause bytecode libraries to reject the input.

## 13. How to read and construct descriptors manually without tools

Follow this order:

**For a field:**

1. Determine the Java type after ignoring the variable name, modifiers, and generic arguments for a regular descriptor.
2. If primitive, convert to the single character **B/C/D/F/I/J/S/Z**.
3. If class/interface, find the exact **binary name** (especially for nested classes), convert to internal name, then wrap with **L...;**.
4. If array, count the **[]** pairs and prepend the corresponding number of **[** before the component type's descriptor.

Example:

~~~text
java.util.Map.Entry<String, Integer>[] entries
    -> raw member class: java.util.Map$Entry
    -> internal name:    java/util/Map$Entry
    -> field descriptor: [Ljava/util/Map$Entry;
~~~

**For a method:**

1. Read each parameter in order and build a field descriptor for each.
2. Concatenate all of them **without commas** inside **(...)**.
3. After **)**, append the return type's field descriptor or **V** if **void**.
4. Do not add a **this** parameter just because the method is an instance method.
5. Do not include the method name, parameter names, **throws**, or generic type arguments in the basic descriptor.

Example:

~~~java
// Code illustrating declaration:
static long evaluate(byte flag, String[][] names, int[] offsets)
~~~

~~~text
byte         -> B
String[][]   -> [[Ljava/lang/String;
int[]        -> [I
long         -> J

Method descriptor:
(B[[Ljava/lang/String;[I)J
~~~

**Left-to-right parser reading:** After **(** comes **B** (parameter 1), **[[Ljava/lang/String;** (parameter 2), **[I** (parameter 3); **)** closes the list; **J** is the return type.

## 14. Common mistakes

### 14.1. Using dots in an object descriptor

**Wrong:** **Ljava.lang.String;**.

**Correct:** **Ljava/lang/String;**.

An object descriptor in a class file uses the internal name, not the dot-separated binary name.

### 14.2. Using the canonical name of a nested class when the API needs a binary name

**Wrong in a binary name context:** **com.example.Outer.Inner**.

**Correct:** **com.example.Outer$Inner** when **Inner** is a member class of **Outer**.

However, remember that **$** is also a Java identifier character that can appear elsewhere; do not infer nested class structure solely by string manipulation without metadata.

### 14.3. Missing the L or ; in an object descriptor

**Wrong:** **java/lang/String**, when the required position is a *field descriptor*.

**Correct:** **Ljava/lang/String;**.

**java/lang/String** itself can be completely valid when the API is requesting an *internal class name*; it is only wrong because of **mismatched input data kind**.

### 14.4. Writing method descriptors with commas or readable types

**Wrong:** **(int,String[])boolean** or **(I,[Ljava/lang/String;)Z**.

**Correct:** **(I[Ljava/lang/String;)Z**.

Method descriptors do not contain commas separating parameters.

### 14.5. Confusing long and object reference

**Wrong:** using **L** for the **long** type.

**Correct:** **J** for **long**; **L<internal-name>;** for class/interface references.

### 14.6. Using V for a field or array element

**Wrong:** **V** as a field descriptor or **[V** for a void array.

**Correct:** **V** is only used as the return descriptor of a method returning **void**, e.g. **()V**.

### 14.7. Forgetting array dimensions

**int[]** is **[I**; **int[][]** is **[[I**. Missing one **[** changes the type completely. A method returning **String[][]** must end with **[[Ljava/lang/String;**, not **[Ljava/lang/String;**.

### 14.8. Reading array getName() as a class file descriptor

**String[].class.getName()** → **[Ljava.lang.String;**, whereas the field descriptor → **[Ljava/lang/String;**. The two strings are not character-for-character equal. For primitive arrays, the string similarity does not prove the same rule applies to reference arrays.

### 14.9. Confusing descriptor with generic signature

**List<String>** has field descriptor **Ljava/util/List;**; the generic **String** representation is not in the main descriptor. Reflection generic metadata or **Signature** is not a place to take a replacement descriptor for code generation.

### 14.10. Confusing a method descriptor with the full symbolic reference

**java/lang/String.length:()I** contains the owner, method name, and descriptor. The actual method descriptor part is only **()I**.

## 15. Self-check exercises

**Question 1.** What are the binary name, internal name, and field descriptor of **java.util.Map.Entry**?

**Answer:**

~~~text
Binary name:    java.util.Map$Entry
Internal name:  java/util/Map$Entry
Descriptor:     Ljava/util/Map$Entry;
~~~

**Question 2.** What are the descriptors of **boolean[][][]** and **long[]**?

**Answer:** **[[[Z** and **[J**. **boolean** uses **Z**, **long** uses **J**.

**Question 3.** Parse **([Ljava/lang/String;I)V**.

**Answer:** A method taking two parameters **String[]** then **int**, returning **void**. The **;** terminates the String component descriptor; the following **I** is the second parameter.

**Question 4.** What does **(ILjava/lang/Object;)[[D** mean?

**Answer:** A method taking **int** and **Object**, returning **double[][]**. The output is a two-dimensional array of type double.

**Question 5.** What descriptor does the field **java.util.List<String> list** have?

**Answer:** **Ljava/util/List;**. Generic String information only resides in generic metadata when present, not in the field descriptor.

**Question 6.** Why is **Class.forName("[Ljava.lang.String;")** valid in a Reflection context while **[Ljava/lang/String;** is the class-file array descriptor form?

**Answer:** Reflection **Class.forName** uses array-name encoding with a **dot-separated binary name** for the reference component, whereas the class file descriptor uses an **internal name with /**.

**Question 7.** Does an instance method **String read(int n)** have the descriptor **(Lmy/pkg/Reader;I)Ljava/lang/String;** to include **this**?

**Answer:** No. The method's descriptor is **(I)Ljava/lang/String;**. **this** is passed implicitly at runtime and is not in the descriptor.

**Question 8.** You see in **javap -v** a **CONSTANT_Class** entry referencing the string **[I**. Is it wrong because it does not contain a package path?

**Answer:** No. **CONSTANT_Class** can describe an array class using an **array descriptor**; **[I** is the array type int[].

**Question 9.** Why cannot **(I)V** be interpreted as a field descriptor?

**Answer:** Parentheses and return **V** belong to **method descriptor** grammar. A field descriptor only describes a single type and does not contain a parameter list or void return.

## 16. Checklist when working with class files, Reflection, and bytecode tooling

1. Identify whether the API requires a **binary name**, **internal name**, **field descriptor**, **method descriptor**, or **generic signature**.
2. For nested member classes, get the exact **binary name** with **$** before converting package dots to **/**.
3. For primitives, use the single-character code; for objects, use **L...;**; for arrays, prepend the exact number of **[**.
4. For methods, assemble **(parameter descriptors) + return descriptor**, including **V** if returning void; do not include the name or **this**.
5. For array reflection, distinguish **Class.getName()** (reference component has **.**) from the class-file descriptor (**/**).
6. Do not treat a generic Signature as a regular descriptor, or assume class names in the constant pool are always without **[**.
7. Read **javap -s -p -v** output and compare with source declarations, method descriptors, and the constant pool; when possible, use **MethodType** and typed APIs to generate accurate strings.

### Official references

- **JVMS Java SE 17, §4.2 — Names**, especially §4.2.1 Binary Class and Interface Names: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.2
- **JVMS Java SE 17, §4.3.2 — Field Descriptors**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.2
- **JVMS Java SE 17, §4.3.3 — Method Descriptors**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3
- **JVMS Java SE 17, §4.4 — Constant Pool**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4
- **JLS Java SE 17, §13.1 — The Form of a Binary**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1
- **Java 17 API, Class**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java 17 API, MethodType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html

**Remember:** **Binary names** use dots for packages and **$** for member classes; **internal names** use **/** instead of package dots; **field descriptors** encode a single type with **B/C/D/F/I/J/S/Z**, **L...;**, or **[...]**; **method descriptors** combine **(parameters)return type**. For **array classes**, how **Class.getName()** represents reference names uses dots and is not identical to the descriptor in the class file. Reading these boundaries correctly helps you avoid most errors when analyzing class files and working with Reflection/bytecode.