
# Method descriptors and differences from source-level signatures

When Java compiles a method, the compiler converts the source-level declaration into a binary representation that the JVM uses to link and invoke the method. This representation is called a **method descriptor**. It has its own structure and rules, differing from the method signature that developers see in Java source.

This difference is very important when evaluating binary compatibility. Two methods may look nearly identical at the source level yet have different descriptors; conversely, two different generic declarations may be turned into the same descriptor by type erasure. The compiler can also generate bridge methods to preserve override relationships after erasing generics or when using covariant return types.

If a migration team only compares method names and parameter lists in source code, it may miss changes that prevent old bytecode from linking with a new library. This lesson explains the structure of a descriptor, compares it with a source-level signature, shows how to inspect it with tools, and explains how to use that information to check binary compatibility.

## 1. What is a method signature at the source code level?

In Java, a method signature is determined by the method name, the method's type parameters (if any), and the formal parameter types, following the adaptation rules of the Java Language Specification. The key point to remember is that **the return type is not a component used to distinguish overloads at the source level**.

For example:

~~~java
public class Converter {
    public String convert(int value) {
        return Integer.toString(value);
    }

    public String convert(long value) {
        return Long.toString(value);
    }
}
~~~

The two methods have the same name but different parameter types, so they have different signatures. The compiler can choose the appropriate method based on argument types and overload resolution rules.

Conversely, the following declaration is invalid in Java:

~~~java
public class Converter {
    public String convert(int value) {
        return Integer.toString(value);
    }

    public long convert(int value) {
        return value;
    }
}
~~~

The two methods have the same name and the same parameter types. Changing only the return type does not create a valid overload at the source level.

A source-level signature also does not include the following information:

| Information | Used to distinguish method signatures at the source level? |
|---|---|
| Method name | Yes |
| Type parameters and parameter types | Yes, according to Java signature rules |
| Return type | No |
| Parameter names | No |
| throws clause | No |
| Annotations | No |
| Access modifiers such as public/private | No |
| static vs. instance | Does not create a separate overload if name and parameters match |

Some information outside the signature can still affect invocation, access permissions, type checking, behavior, or how the compiler emits bytecode. They are simply not components that distinguish overloads under source-level rules.

## 2. What is a method descriptor at the JVM level?

The JVM does not describe methods the same way Java source does. In a class file, a method has a name and a **descriptor**. The descriptor precisely describes the parameter types and return type after conversion to JVM form.

General structure:

~~~text
(parameter-descriptor...)return-descriptor
~~~

Parentheses enclose the parameter list; the part after the closing parenthesis is the return type.

Examples:

| Java declaration | Method descriptor |
|---|---|
| void run() | ()V |
| int add(int a, int b) | (II)I |
| String find(int id) | (I)Ljava/lang/String; |
| void send(String value) | (Ljava/lang/String;)V |
| long sum(int[] values) | ([I)J |
| Object lookup(String key, int index) | (Ljava/lang/String;I)Ljava/lang/Object; |

A descriptor does not contain the method name. In a class file, the method name and descriptor are two separate items. When the JVM links a call, the symbolic reference identifies the owning class/interface, method name, and descriptor. Therefore, two methods with different names can have the same descriptor and still be two distinct methods.

### 2.1. Data type notation

Primitive types and void have fixed notations:

| Java type | Descriptor |
|---|---|
| byte | B |
| char | C |
| double | D |
| float | F |
| int | I |
| long | J |
| short | S |
| boolean | Z |
| void (return type only) | V |

Reference types use the form:

~~~text
Lbinary/name/of/Class;
~~~

Examples:

| Java type | Descriptor |
|---|---|
| String | Ljava/lang/String; |
| java.util.List | Ljava/util/List; |
| com.example.User | Lcom/example/User; |

Package names use forward slashes in descriptors. For inner classes, the binary name typically contains a dollar sign:

~~~text
Lcom/example/Outer$Inner;
~~~

Arrays use square brackets at the beginning of the element type's descriptor:

| Java type | Descriptor |
|---|---|
| int[] | [I |
| long[][] | [[J |
| String[] | [Ljava/lang/String; |
| User[][] | [[Lcom/example/User; |

### 2.2. Constructing a descriptor step by step

Consider the method:

~~~java
public String find(int id, boolean active) {
    return "user";
}
~~~

Convert each parameter:

- int becomes I.
- boolean becomes Z.
- Return type String becomes Ljava/lang/String;.

Combine according to the method descriptor structure:

~~~text
(IZ)Ljava/lang/String;
~~~

Consider another method:

~~~java
public void save(String name, long version, byte[] data) {
}
~~~

The parameters are String, long, and byte[], respectively; the return type is void. Descriptor:

~~~text
(Ljava/lang/String;J[B)V
~~~

This conversion does not depend on parameter names. Renaming name to username does not change the descriptor.

## 3. Descriptors include the return type

This is the most important difference between a method signature in Java source and a JVM method descriptor.

For example, two hypothetical declarations:

~~~java
String getValue(int id)
Object getValue(int id)
~~~

At the source level, the two methods have the same name and parameter types, so they cannot be declared as two overloads in the same regular Java class.

At the JVM level, the descriptors are respectively:

~~~text
(I)Ljava/lang/String;
(I)Ljava/lang/Object;
~~~

The descriptors differ because the return type is included. A JVM class file can represent methods with the same name and parameters but different return descriptors, even though Java source does not allow developers to declare two such methods directly.

This can occur when:

- The compiler generates a bridge method.
- Another language running on the JVM has different source rules than Java.
- Bytecode is generated or transformed using ASM, Byte Buddy, or similar tools.

### 3.1. Changing the return type can break binary compatibility

Suppose library version 1 has:

~~~java
public class UserRepository {
    public User find(long id) {
        return null;
    }
}
~~~

Method descriptor:

~~~text
(J)Lcom/example/User;
~~~

Library version 2 changes the return type to a different type:

~~~java
public class UserRepository {
    public Optional<User> find(long id) {
        return Optional.empty();
    }
}
~~~

New descriptor:

~~~text
(J)Ljava/util/Optional;
~~~

A consumer compiled against version 1 contains a reference to the method with the old descriptor. When running with version 2 where that method no longer exists, the JVM can throw:

~~~text
java.lang.NoSuchMethodError
~~~

In source, the method name and parameter types remain the same. However, the binary reference has changed because the return type is part of the descriptor.

This is why binary compatibility checks cannot just compare method names and parameters.

## 4. Generics and type erasure

Java generics are checked primarily at compile time. During compilation, the compiler applies **type erasure** to convert parameterized types into their corresponding JVM types.

For example:

~~~java
public interface Store<T> {
    T get();
    void put(T value);
}
~~~

If T has no explicit bound, the erasure of T is Object. The corresponding descriptors:

~~~text
get: ()Ljava/lang/Object;
put: (Ljava/lang/Object;)V
~~~

While source code has T, the JVM descriptor does not contain the type variable name T. Generic information can be kept separately in a class file attribute named Signature for use by the compiler, reflection, and metadata-reading tools.

Example of a generic method:

~~~java
public <T> T identity(T value) {
    return value;
}
~~~

Descriptor after erasure:

~~~text
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

The generic Signature attribute can retain the information that the parameter and result use the same type variable T. The two forms of metadata serve two different purposes:

| Component | Purpose |
|---|---|
| Descriptor | Linking and invoking methods at the JVM level |
| Signature attribute | Retaining generic information for tools and reflection to read |
| Source declaration | Expressing generic types for developers and the compiler |

### 4.1. Bounds change erasure

If a type variable has a bound:

~~~java
public <T extends Number> T normalize(T value) {
    return value;
}
~~~

The erasure of T is Number, not Object. Descriptor:

~~~text
(Ljava/lang/Number;)Ljava/lang/Number;
~~~

If the bound is changed from Number to Serializable, the descriptor can change to:

~~~text
(Ljava/io/Serializable;)Ljava/io/Serializable;
~~~

Even if the method name and generic structure look similar, changing a bound can change the descriptor and break linking of old bytecode.

### 4.2. Generic changes may not change the descriptor

Suppose version 1:

~~~java
public List<String> names() {
    return List.of();
}
~~~

Version 2:

~~~java
public List<CharSequence> names() {
    return List.of();
}
~~~

Both have the descriptor:

~~~text
()Ljava/util/List;
~~~

Because the generic type argument is erased from the descriptor. Consequently, this change may not cause the JVM to lose the method at the linkage step, but it can still cause source incompatibility, alter generic metadata, cause errors in consumers upon recompilation, or change behavior.

You should not conclude that an unchanged descriptor means a change is completely safe. Binary linkage is one part of compatibility and does not cover all source and behavioral contracts.

## 5. Bridge methods and synthetic methods

The Java compiler can generate methods that developers do not declare directly. Two common class file flags:

- ACC_BRIDGE: a bridge method generated by the compiler to preserve override relationships after type erasure or for covariant return types.
- ACC_SYNTHETIC: a method or member generated automatically by the compiler, not a regular source declaration.

Bridge methods allow methods with generic types or covariant return types to continue working properly across bytecode boundaries.

### 5.1. Bridge methods from generic erasure

Consider the example:

~~~java
public class Node<T> {
    public void set(T value) {
        System.out.println(value);
    }
}

public class IntegerNode extends Node<Integer> {
    @Override
    public void set(Integer value) {
        System.out.println(value.intValue());
    }
}
~~~

At the source level, IntegerNode overrides the method set(T) with T replaced by Integer.

However, Node's method after erasure is set(Object): void. The method written in IntegerNode is set(Integer): void.

The compiler generates a bridge method whose descriptor corresponds to the erased method:

~~~java
// Illustrative pseudocode, auto-generated by the compiler
public void set(Object value) {
    set((Integer) value);
}
~~~

Descriptors of the two methods:

~~~text
set(Integer): (Ljava/lang/Integer;)V
set(Object):  (Ljava/lang/Object;)V
~~~

The bridge method may have the ACC_BRIDGE and ACC_SYNTHETIC flags. It forwards calls from the erased descriptor to the specific method.

### 5.2. Bridge methods from covariant return types

Java allows a subclass to override a method with a return type that is a subtype of the superclass's return type.

~~~java
public class Parent {
    public Object value() {
        return "parent";
    }
}

public class Child extends Parent {
    @Override
    public String value() {
        return "child";
    }
}
~~~

In source, Child.value() is valid because String is a subtype of Object. However, Parent's descriptor is ()Ljava/lang/Object;, while Child's descriptor is ()Ljava/lang/String;.

To maintain dispatch for bytecode referencing Parent.value() with return descriptor Object, the compiler can generate a bridge in Child:

~~~java
// Illustrative pseudocode
public Object value() {
    return value(); // Forwards to the method returning String
}
~~~

In the class file, the bridge method has the superclass's descriptor and the actual method has the descriptor returning String. When inspecting with javap, you can see two methods with the same name but different descriptors.

### 5.3. Why are bridge methods important during analysis?

When using reflection or bytecode reading tools, you may see multiple methods with the same name that look nearly identical. Do not assume these are duplicate methods caused by an error.

You need to check:

- Does the method have the bridge flag?
- Does the method have the synthetic flag?
- Where do the descriptors of the original method and the bridge differ?
- Is the bridge preserving a generic override or a covariant return?
- Which descriptor is the consumer bytecode calling?

In Java Reflection, you can check:

~~~java
for (var method : IntegerNode.class.getDeclaredMethods()) {
    System.out.println(method);
    System.out.println("bridge=" + method.isBridge());
    System.out.println("synthetic=" + method.isSynthetic());
}
~~~

Reflection can return bridge methods alongside methods written by developers. Method-scanning frameworks should check the bridge/synthetic flags to avoid processing the same logic twice.

## 6. Information not included in a method descriptor

A descriptor only describes parameter types and the return type. Several other attributes are stored elsewhere in the class file or are not used by the JVM to distinguish methods.

| Information | Included in descriptor? | Location or impact |
|---|---|---|
| Method name | No | Separate name_index in method_info |
| Parameter types | Yes | Parameter descriptor section |
| Return type | Yes | Return descriptor section |
| Parameter names | No | May be in the MethodParameters attribute |
| throws clause | No | Exceptions attribute |
| Generic type | Not completely | Signature attribute |
| Annotations | No | RuntimeVisibleAnnotations and corresponding attributes |
| public/private/protected | No | Access flags |
| static | No | Access flags and invocation opcode kind |
| synchronized | No | Access flags |
| bridge/synthetic | No | Access flags |
| varargs | No | ACC_VARARGS; parameter is represented by an array descriptor |

### 6.1. The throws clause is not part of the descriptor

The following two declarations have the same descriptor:

~~~java
public void load(String path) throws IOException {
}

public void load(String path) throws SQLException {
}
~~~

Both have the descriptor:

~~~text
(Ljava/lang/String;)V
~~~

Java source may handle them differently due to checked exceptions, but JVM method linkage does not distinguish them by their throws clause. Changing a throws clause can affect source compatibility for consumers when recompiling, but does not change the descriptor.

### 6.2. Parameter names are not part of the descriptor

Example:

~~~java
public void setName(String name)
public void setName(String username)
~~~

Parameter names can be stored in the class file if the compiler emits a MethodParameters attribute or appropriate debug information. However, they do not affect the descriptor:

~~~text
(Ljava/lang/String;)V
~~~

Renaming parameters does not break old bytecode's link to the method.

### 6.3. Varargs and arrays

In Java source:

~~~java
public void log(String... messages)
~~~

Varargs are represented as an array at the descriptor level:

~~~text
([Ljava/lang/String;)V
~~~

The method has the ACC_VARARGS flag, but its descriptor is identical to a method accepting String[]:

~~~java
public void log(String[] messages)
~~~

Therefore, changing from varargs to an array can preserve the descriptor while changing how consumers call it when compiling source. This is a typical example of the difference between binary compatibility and source-level API usability.

### 6.4. static and instance methods

The static modifier is not in the descriptor. For example:

~~~java
public static int calculate(long value)
~~~

An instance method with the same name, parameters, and return type will have the same descriptor:

~~~text
(J)I
~~~

However, static/instance is a class file property and affects how bytecode invokes the method:

- invokestatic invokes a static method.
- invokevirtual invokes an instance method on a class.
- invokeinterface invokes a method through an interface.
- invokespecial is used for constructors, private methods, or certain special calls according to JVM rules.

Changing static to instance or vice versa can cause old bytecode to fail with IncompatibleClassChangeError, even though the descriptor does not change, because the invocation opcode and expectation of the method kind no longer match.

## 7. Constructor and field descriptors

### 7.1. Constructor

A constructor has the special name <init> and its descriptor always has return type void, denoted V.

Example:

~~~java
public User(String name, long id) {
}
~~~

Descriptor:

~~~text
(Ljava/lang/String;J)V
~~~

A constructor has no return type in Java source, yet the class file still represents the return descriptor as V.

A class initializer uses the special name <clinit> and descriptor ()V.

### 7.2. Field descriptors

A field does not have a method descriptor; instead it has a field descriptor, which describes the field's type.

Example:

~~~java
private long id;
private String name;
private List<String> roles;
~~~

| Field | Descriptor |
|---|---|
| id | J |
| name | Ljava/lang/String; |
| roles | Ljava/util/List; |

The generic type argument of List does not appear in the field descriptor; generic information may reside in the Signature attribute.

If a field's type changes from long to String, the descriptor changes from J to Ljava/lang/String;. Old bytecode references the field by owner, name, and descriptor; if no matching field remains, NoSuchFieldError may occur.

## 8. How to inspect descriptors using JDK tools

### 8.1. Using javap -s

Compile a class:

~~~java
package com.example;

public class Api {
    public String find(int id, boolean active) {
        return "user";
    }

    public void send(String name, long version, byte[] data) {
    }
}
~~~

Run:

~~~bash
javac -d out src/com/example/Api.java
javap -classpath out -p -s com.example.Api
~~~

The output looks like:

~~~text
public java.lang.String find(int, boolean);
  descriptor: (IZ)Ljava/lang/String;

public void send(java.lang.String, long, byte[]);
  descriptor: (Ljava/lang/String;J[B)V
~~~

Options:

- -p: displays private members as well.
- -s: displays descriptors.
- -v: displays class file details, access flags, and attributes.

### 8.2. Using javap -v to view bridges and generic Signatures

Run:

~~~bash
javap -classpath out -p -s -v com.example.IntegerNode
~~~

In the output, look for these sections:

- descriptor: binary descriptor.
- Signature: generic metadata if present.
- ACC_BRIDGE: bridge method.
- ACC_SYNTHETIC: member automatically generated by the compiler.
- Code: bytecode executing the method.

When comparing two builds, keep the full output to distinguish which methods were declared in source and which were generated by the compiler.

### 8.3. Viewing bytecode instructions that invoke methods

Use:

~~~bash
javap -classpath app.jar -c -v com.example.Consumer
~~~

An invoke instruction in bytecode references the owner, name, and descriptor. A conceptual example:

~~~text
invokevirtual com/example/Api.find:(IZ)Ljava/lang/String;
~~~

If the new library no longer has a method matching that symbolic reference, the JVM can throw a linkage error when executing the call.

### 8.4. Class file analysis tools

Besides javap, you can use:

- ASM: reads and writes class files, and constructs method descriptors via Type.
- Byte Buddy: creates or transforms classes/methods at runtime.
- BCEL: reads and analyzes bytecode structures.
- Binary compatibility tools such as japicmp or Revapi: compare APIs between library versions.

These tools complement javap. Before drawing conclusions, still verify the actual released artifacts and test a consumer compiled against the old version.

## 9. Descriptors and binary compatibility when upgrading libraries

When a library changes, compare the descriptors of public/protected methods and fields that consumers can use.

| Change | Does descriptor change? | Main risk |
|---|---|---|
| Rename parameter | No | Usually does not affect linkage |
| Change return type | Yes | Old bytecode may encounter NoSuchMethodError |
| Change parameter type | Yes | Old bytecode references a descriptor that no longer exists |
| Change parameter order | Yes | Descriptor changes |
| Add new overload | Old descriptor remains intact | May cause source ambiguity when consumer recompiles |
| Change throws clause | No | May cause source compatibility issues |
| Change generic type argument after erasure | Possibly no | May affect source/generic metadata/behavior |
| Change static to instance | Descriptor unchanged | May encounter IncompatibleClassChangeError |
| Change field type | Yes | Old bytecode may encounter NoSuchFieldError |
| Add bridge method | Adds a descriptor | Usually for override compatibility; inspect bridge flag |

### 9.1. Changing parameter types

Version 1:

~~~java
public void send(String message)
~~~

Descriptor:

~~~text
(Ljava/lang/String;)V
~~~

Version 2:

~~~java
public void send(CharSequence message)
~~~

Descriptor:

~~~text
(Ljava/lang/CharSequence;)V
~~~

Even though String implements CharSequence, the descriptors are not the same. Old bytecode calls the method accepting String and does not automatically redirect the reference to the method accepting CharSequence during linking. If the old method is removed, NoSuchMethodError may occur.

A safer migration approach is to keep the old method and add the new overload in a compatible release:

~~~java
public void send(String message) {
    send((CharSequence) message);
}

public void send(CharSequence message) {
    // New implementation
}
~~~

This approach preserves the old descriptor during the transition period, though overload resolution and behavior still need to be reviewed.

### 9.2. Adding an overload can affect source compatibility

Suppose initially:

~~~java
public void process(String value) {
}
~~~

The consumer has the call:

~~~java
process(null);
~~~

Then the library adds:

~~~java
public void process(Integer value) {
}
~~~

When the consumer recompiles, the call process(null) becomes ambiguous because null can be converted to both String and Integer. Old bytecode compiled previously still references the String method's descriptor if that method still exists.

Therefore, adding an overload usually preserves binary compatibility but can still cause source incompatibility. This is why both compiled consumers and recompiled consumers need to be tested.

## 10. Verification using old and new consumers

A practical verification method is to create a consumer using the library's API and then test two scenarios.

### Scenario A: consumer compiled against the old library version

1. Compile the consumer using the old library version.
2. Keep the consumer class files unchanged.
3. Replace the runtime dependency with the new library version.
4. Run the consumer without recompiling.

If the old method descriptor is missing or changed, the JVM can throw a linkage error. This is a direct test for binary compatibility.

### Scenario B: consumer recompiled against the new version

1. Use the old consumer source.
2. Replace the compile dependency with the new library.
3. Recompile.
4. Run tests and check warnings/errors.

This scenario detects source incompatibility, such as overload ambiguity, new checked exceptions, or incompatible generic types.

The two scenarios answer two different questions. A library can preserve binary compatibility yet fail to allow consumers to recompile; conversely, new source code may compile successfully while old bytecode fails to run.

### 10.1. Keeping the right artifacts in the test

To make results reproducible:

- Save checksums of the old and new libraries.
- Record the compiler and runtime JDKs.
- Keep the old consumer class files intact.
- Control the classpath so another JAR version is not loaded accidentally.
- Capture full logs when running.
- Verify that classes are loaded from the expected JAR file.

Class loading logs can be used on modern JDKs:

~~~bash
java -Xlog:class+load=info -cp "consumer.jar:library-new.jar" com.example.Consumer
~~~

On Windows, the classpath separator is a semicolon instead of a colon. Depending on the JDK, the log format may differ.

## 11. Process for comparing descriptors between two releases

A suitable process for a library:

1. Obtain the exact JARs of the old and new releases.
2. List the public/protected classes and APIs that consumers are allowed to use.
3. Run javap -p -s on the classes to compare.
4. Record method names, descriptors, field descriptors, and access flags.
5. Distinguish source-declared methods from bridge/synthetic methods.
6. Compare the generic Signature attribute if the generic API changed.
7. Review changes to static/instance, visibility, and throws separately.
8. Run a binary compatibility tool to extend the check across the entire API.
9. Run the consumer compiled with the old release against the new release.
10. Recompile the consumer against the new release and run regression tests.

Do not simply compare javap output files as plain text by method name. Descriptors and flags need to be parsed, because display order or formatting can vary across JDKs.

## 12. Common misconceptions

- **Confusing signature with descriptor:** source signature does not include the return type, whereas method descriptor does.
- **Thinking generics appear completely in the descriptor:** type arguments undergo erasure; generic metadata is stored separately.
- **Thinking the throws clause changes the descriptor:** the throws clause is not part of the descriptor.
- **Thinking parameter names affect linkage:** parameter names are not components of the descriptor.
- **Thinking varargs differ from arrays in descriptors:** varargs are represented as an array; the ACC_VARARGS flag is stored separately.
- **Thinking static is inside the descriptor:** static is an access flag and affects the invocation opcode.
- **Thinking two methods with the same name are always valid overloads in Java:** return type alone does not create an overload in source, even though the JVM descriptor contains the return type.
- **Thinking bridge methods are buggy duplicate code:** bridges are usually a mechanism the compiler needs to preserve overrides after erasure or covariant returns.
- **Thinking an unchanged descriptor means no breaking change:** source, generic metadata, checked exceptions, and behavioral contracts can still change.
- **Thinking a successful build is enough:** old consumer bytecode must be run against the new artifact to test actual linkage.

## 13. Verification checklist

### Source signature and descriptor

- [ ] Distinguished source-level method signature from JVM method descriptor.
- [ ] Identified descriptors of key public/protected methods.
- [ ] Identified descriptors of relevant constructors and fields.
- [ ] Checked return types because the return type is included in the descriptor.
- [ ] Distinguished descriptors from the generic Signature attribute.
- [ ] Recorded bridge and synthetic methods.

### Binary compatibility

- [ ] Compared descriptors between the old and new releases.
- [ ] Checked changes to parameters, return types, and field types.
- [ ] Checked static/instance and access flags.
- [ ] Evaluated the source-level impact of throws clauses and generic metadata.
- [ ] Checked whether new overloads cause ambiguous calls when recompiling.
- [ ] Ran the old consumer against the new library.
- [ ] Recompiled the consumer against the new library.

### Evidence

- [ ] Used javap -p -s or a class file inspection tool.
- [ ] Saved descriptors and artifact checksums.
- [ ] Controlled the classpath and confirmed the intended JAR is loaded.
- [ ] Saved linkage error logs or test results.
- [ ] Identified a migration plan for each changed descriptor.

## Conclusion

A method signature at the Java source level and a method descriptor at the JVM level serve two different layers. A source signature does not use the return type to distinguish overloads, whereas a descriptor describes both parameters and the return type. Generic types undergo erasure before descriptors are generated; bridge methods can be generated by the compiler to preserve overrides; attributes such as throws, parameter names, annotations, and static are stored or handled elsewhere.

When evaluating binary compatibility, read descriptors from actual artifacts, compare access flags and related metadata as well, and run a consumer compiled against the old library version on top of the new version. Combining that test with recompiling the consumer will clearly reveal both binary compatibility and source compatibility.
