# Inspecting bytecode with javap: abstract flag, interface flag, and bridge method

When reading Java source code, we see abstract classes, interfaces, and generic methods at the language level. After compilation, the JVM works with class files, descriptors, and access flags. The **javap** tool helps inspect what the compiler actually generates, especially the three flags **ACC_ABSTRACT**, **ACC_INTERFACE**, and **ACC_BRIDGE**.

This article uses a small example that can be compiled with Java 17+, and then reads the relevant bytecode instead of inferring solely from the source code.

## 1. What is javap used for?

**javap** is a tool included with the JDK for analyzing class files. Some useful options:

| Option | Purpose |
|---|---|
| **-p** | Displays private members as well, in addition to regular members |
| **-v** | Displays detailed information: class file version, flags, constant pool, and attributes |
| **-s** | Displays internal descriptors of classes and methods |
| **-c** | Displays bytecode instructions in the Code section |
| **-classpath** or **-cp** | Specifies where to find class files |

For example, **javap -v -p StringMapper** shows the flags of the class and methods, while **javap -c -p StringMapper** lets you see the instructions of the compiler-generated bridge method. You can combine options, such as **javap -v -p -c StringMapper**.

Run javap on the compiled **.class** file. If you have just edited the source code without recompiling, the javap output will still reflect the old class version.

## 2. Flags to distinguish

Flags are bits in the class file structure. javap typically presents them as a hex value and a list of human-readable names.

| Flag | Value | Context | Meaning |
|---|---:|---|---|
| **ACC_ABSTRACT** | **0x0400** | Class or method | The class cannot be instantiated directly; for a method, the body is left empty and a concrete class must provide an implementation when needed |
| **ACC_INTERFACE** | **0x0200** | Class file representing an interface | Marks the type as an interface |
| **ACC_BRIDGE** | **0x0040** | Method | Marks a compiler-generated bridge method to preserve dispatch, commonly seen with generics and type erasure |
| **ACC_SYNTHETIC** | **0x1000** | Member | Marks a compiler-generated member that does not correspond directly to an explicit declaration in the source code |
| **ACC_PUBLIC** | **0x0001** | Class or member | The member is publicly accessible; for a top-level class, only appears if the class is declared public |
| **ACC_SUPER** | **0x0020** | Regular class | A class file flag commonly found on Java classes; it does not mean the class is abstract or has a superclass we declared ourselves |

An important point: flag interpretation depends on context. You should not read a bit value in isolation from whether it belongs to the flags of a class, method, or field.

**ACC_ABSTRACT** and **ACC_INTERFACE** are not synonymous. An interface has the **ACC_INTERFACE** class flag and also has **ACC_ABSTRACT** at the class file level. An abstract method has **ACC_ABSTRACT** in the flags of the method itself. An abstract class has **ACC_ABSTRACT** in the class flags, but does not have **ACC_INTERFACE**.

An interface still carries the abstract class flag even when it has **default**, **static**, or **private** methods with a body. Interface methods that have a body do not necessarily carry **ACC_ABSTRACT**.

## 3. Runnable Java 17+ example

Create a file named **BytecodeFlagsDemo.java** with the following content. The interface and abstract class in the example are placed in the same file to keep experimentation simpler.

~~~java
interface Mapper<T> {
    T map(T value);
}

abstract class Base {
    public abstract Number value();
}

final class StringMapper implements Mapper<String> {
    @Override
    public String map(String value) {
        return value.trim();
    }
}

public class BytecodeFlagsDemo {
    public static void main(String[] args) {
        Mapper<String> mapper = new StringMapper();
        System.out.println(mapper.map("  Java  "));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac --release 17 BytecodeFlagsDemo.java
java BytecodeFlagsDemo
~~~

Stdout:

~~~text
Java
~~~

The **--release 17** option instructs the compiler to generate Java 17-compatible bytecode and restrict APIs to that version. When using a Java 17 compiler, the class file has major version **61**.

The compile command generates the class files, including **Mapper.class**, **Base.class**, **StringMapper.class**, and **BytecodeFlagsDemo.class**. Each class file describes a separate type; therefore, you need to inspect the right class name when running javap.

## 4. Inspecting the abstract flag of classes and methods

Run:

~~~bash
javap -v -p Base
~~~

In the top part of the output, look for the class flags. The relevant part will look like:

~~~text
abstract class Base
  ...
  flags: (0x0420) ACC_SUPER, ACC_ABSTRACT
~~~

The **Base** class has **ACC_ABSTRACT** because it is declared abstract. The **ACC_SUPER** flag is a standard Java class flag and does not mean that Base is abstract.

Next, find the **value()** method:

~~~text
public abstract java.lang.Number value();
  descriptor: ()Ljava/lang/Number;
  flags: (0x0401) ACC_PUBLIC, ACC_ABSTRACT
~~~

The method has no Java body, so the class file does not contain a normal Code section for this method. The descriptor **()Ljava/lang/Number;** means there are no parameters and the return type is **java.lang.Number**.

A concrete class extending Base must implement the missing abstract method; otherwise, that class must also be declared abstract. Looking at the class-level flag and the method-level flag helps identify these two separate concepts.

## 5. Inspecting the interface flag

Run:

~~~bash
javap -v -p Mapper
~~~

The top part of the output will show that the type is an interface along with the class-level flags:

~~~text
interface Mapper<T>
  ...
  flags: (0x0600) ACC_INTERFACE, ACC_ABSTRACT
~~~

This is the primary indicator that the class file represents an interface. The value **0x0600** is the sum of **ACC_INTERFACE (0x0200)** and **ACC_ABSTRACT (0x0400)**.

The generic method in the interface looks like:

~~~text
public abstract T map(T);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (0x0401) ACC_PUBLIC, ACC_ABSTRACT
  Signature: #... // (TT;)TT;
~~~

The **descriptor** line and the **Signature** line answer two different questions:

- **Descriptor** is the type used for linking and invocation at the JVM level. After type erasure, both the parameter T and result T of this method become **java.lang.Object**.
- **Signature** retains generic information so tools and the compiler can represent the source type **T**. The constant pool index in actual output depends on the compilation; the **#...** here is an illustrative omission, not literal javap text.

Do not conclude that an interface has no executable methods just because its class file has **ACC_ABSTRACT**. This flag describes the interface type at the class level; individual methods still have their own flags. Abstract methods have no body, whereas default or static methods have a body and do not carry **ACC_ABSTRACT** at the method level.

## 6. Why does the compiler generate a bridge method?

Java generics are primarily implemented using **type erasure**. In the example, the source declaration is **Mapper&lt;T&gt;** with the method **T map(T value)**. After erasure, the descriptor of the method in the interface is:

~~~text
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

However, the **StringMapper** class implements the specialized method:

~~~java
public String map(String value)
~~~

The descriptor of this method is:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

The two descriptors are different. At the JVM level, a method taking Object is not the same as a method taking String. So that a call made against the erased contract is still dispatched to the specialized implementation, the compiler generates a **bridge method** with the erased descriptor. The bridge method checks and forwards the argument, then calls the actual method in StringMapper.

A bridge method does not need to be written in the source code. It is an extra member in bytecode to preserve polymorphic behavior when generics undergo type erasure. The same idea can also appear in some cases of overriding with a covariant return type.

## 7. Using javap to find a bridge method

Run:

~~~bash
javap -v -p StringMapper
~~~

In the output, you will see the source method:

~~~text
public java.lang.String map(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  flags: (0x0001) ACC_PUBLIC
~~~

And an additional method that looks like:

~~~text
public java.lang.Object map(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

The three flags above can be read as follows:

- **ACC_PUBLIC**: the bridge can be called with public access.
- **ACC_BRIDGE**: this is a bridge method.
- **ACC_SYNTHETIC**: the compiler marks this method as a generated member.

The value **0x1041** corresponds to **0x0001 + 0x0040 + 0x1000**. Look at the list of flag names as well instead of only memorizing the numbers.

Because the verbose output can be long, focus on the method name, descriptor, flags, and the Code section of the method that takes Object. Constant pool index numbers may differ across builds; what needs to be compared is the descriptor and behavior.

## 8. Reading the bridge's Code section

You can ask javap to display the bytecode:

~~~bash
javap -c -p StringMapper
~~~

The bridge method will have instructions equivalent to the following; the constant pool indices and comments may differ:

~~~text
public java.lang.Object map(java.lang.Object);
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #... // class java/lang/String
     5: invokevirtual #... // Method map:(Ljava/lang/String;)Ljava/lang/String;
     8: areturn
~~~

Reading in order:

1. **aload_0** pushes the current object onto the operand stack.
2. **aload_1** pushes the Object parameter onto the stack.
3. **checkcast java/lang/String** checks and casts the parameter to String. If the caller passes an incompatible type, this instruction can throw **ClassCastException**.
4. **invokevirtual map(String)** calls the actual implementation in StringMapper.
5. **areturn** returns the resulting reference. String is a reference type, so the reference return instruction is used.

A bridge method is not a duplicate containing independent business logic. It forwards the call made with the erased descriptor to the specialized method. That is why a bridge method is usually short and has cast instructions along with calling another method.

## 9. Diagnostic workflow with javap

When you need to verify that the compiler generated the expected structure:

1. **Recompile** the source code with the desired JDK and version options.
2. **Inspect the right class** with javap. If the class is in a package or a separate build directory, pass the full name or classpath.
3. **Use -v** to view flags and attributes.
4. **Use -s** to compare descriptors, especially when generics undergo type erasure.
5. **Use -c** to inspect which cast and method call the bridge performs.
6. **Compare the source method and the bridge**: the names may be the same, while the parameters or return type in the descriptor differ.
7. **Verify flags at the right level**: class flags do not replace method flags, and a bridge's flags are not the flags of the entire class.

A useful command for quickly checking descriptors and bytecode is:

~~~bash
javap -p -s -c StringMapper
~~~

If you need to view detailed flags, add **-v**. To view non-public members, keep **-p**; without this option, some information might not appear as expected.

## 10. Common misconceptions

- **Confusing ACC_ABSTRACT with ACC_INTERFACE:** an interface carries both flags at the class level, whereas an abstract class has ACC_ABSTRACT without ACC_INTERFACE.
- **Looking only at method names:** two methods with the same name can have different descriptors. Check the parameters, return type, and internal descriptor.
- **Assuming bridge methods are written in source code:** bridges are typically generated by the compiler. Use javap or the Reflection API to identify them.
- **Assuming ACC_SYNTHETIC is synonymous with ACC_BRIDGE:** synthetic is a general label for compiler-generated members; a bridge is a kind of method with a specific purpose.
- **Reading Signature as descriptor:** Signature can preserve generic types, whereas the descriptor reflects the post-erasure types used in JVM linking.
- **Not recompiling after editing source code:** javap reads class files on disk, so it can show stale results.
- **Comparing constant pool numbers across builds:** indices like **#7** are not stable identifiers. Compare method names, descriptors, flags, and bytecode instructions.
- **Assuming every interface method is abstract:** default, static, and private methods have bodies; inspect the flags of each method.
- **Ignoring ClassCastException in a bridge:** a bridge can cast from Object to the specialized type. Raw type calls or unsafe generic code can pass an argument of the wrong type.

## 11. Output reading checklist

- An abstract class has **ACC_ABSTRACT** in its class-level flags.
- An interface has **ACC_INTERFACE** and **ACC_ABSTRACT** in its class-level flags.
- An abstract method has **ACC_ABSTRACT** in the method's flags.
- The source method and bridge are compared by descriptor, not only by name.
- A compiler-generated bridge typically has **ACC_BRIDGE** and **ACC_SYNTHETIC**.
- The Code section of the bridge shows how it forwards the argument and calls the specialized method.
- Recompiled and inspected the right class file.

When analyzing bytecode, always determine **whether a flag belongs to a class or a method**, and then cross-reference it with the **descriptor** and **Code**. Combined together, these three pieces of information clearly explain why an abstract class, an interface, or a bridge method appears in the compiled output.
