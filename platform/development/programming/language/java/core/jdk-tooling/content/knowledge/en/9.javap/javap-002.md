# Viewing Class Declarations with javap

javap is a command-line tool included with the JDK, used to inspect the structure of compiled Java classes. When you need to know which modifiers a class has, which class it extends, which interfaces it implements, and what constructors, fields, and methods it declares, javap lets you view this information directly from a .class file or a JAR library.

This tool is useful when reading the API of third-party libraries, checking artifacts after a build, investigating linkage errors between classes, verifying method signatures, and comparing two versions of a library. javap displays declarations in a form close to Java source code, and can also display descriptors and metadata at the bytecode level.

## 1. What does javap read?

Java source code is compiled into bytecode in .class files. A class file stores information about:

- Class name, package, and modifiers such as public, abstract, or final.
- Superclass and interfaces implemented by the class.
- Constructors, fields, and methods.
- Data types, parameters, return types, and member access levels.
- Additional attributes such as generic Signature, annotations, constant values, debug information, and method bytecode.

javap reads this information and presents it at multiple levels of detail. When you only need to inspect the public API, use member filtering mode. When you need to investigate JVM signatures, use -s. When you need to view deeper metadata, use -v.

javap works with compiled bytecode. It does not need the original .java file, nor does it fully reconstruct the original source code: comments, local variable names when debug metadata is absent, original expression structures, and many source formatting details are not stored in the class file.

## 2. Installing and checking javap

javap is a JDK tool. If a JDK is installed on your machine and the JDK's bin directory is in PATH, you can invoke it directly:

~~~bash
javap --version
javap --help
~~~

Check the Java and compiler versions to know which environment is being used:

~~~bash
java -version
javac -version
javap --version
~~~

On Windows, you can identify which executable is being invoked with:

~~~powershell
where.exe javap
~~~

On Linux or macOS:

~~~bash
type -a javap
~~~

If javap is not recognized, check whether PATH contains the JDK's bin directory. Do not confuse javap with java: java launches applications, javac compiles source code, and javap inspects class file structure.

## 3. Basic syntax

Common syntax:

~~~bash
javap [options] class
~~~

The class argument is usually the fully qualified binary name of the class, including the package. For example:

~~~bash
javap java.lang.String
javap java.util.ArrayList
~~~

For project classes, javap needs to know where to find the .class file. Use classpath:

~~~bash
javap -classpath out com.acme.model.Customer
~~~

In this example:

- out is the root directory containing the compiled package tree.
- com.acme.model.Customer is the fully qualified binary name of the class.
- Do not separate package names with slashes when passing the class as a class name.
- Do not add the .class extension when passing a fully qualified binary name.

You can pass the path to a class file directly in some situations, for example:

~~~bash
javap -private out/com/acme/model/Customer.class
~~~

Using the class name together with -classpath is usually more convenient when the class is in a package structure or when inspecting a JAR.

## 4. Practical example: viewing a class declaration

Create the directory structure:

~~~text
javap-demo/
└── src/
    └── com/
        └── acme/
            └── model/
                └── Customer.java
~~~

File src/com/acme/model/Customer.java:

~~~java
package com.acme.model;

public final class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public static Customer guest() {
        return new Customer("Guest");
    }
}
~~~

Compile from the javap-demo directory:

~~~bash
javac -d out src/com/acme/model/Customer.java
~~~

After compilation, the class file is created at:

~~~text
out/com/acme/model/Customer.class
~~~

View the class declaration:

~~~bash
javap -classpath out com.acme.model.Customer
~~~

Typical output:

~~~text
Compiled from "Customer.java"
public final class com.acme.model.Customer {
  public com.acme.model.Customer(java.lang.String);
  public java.lang.String name();
  public static com.acme.model.Customer guest();
}
~~~

From this output you can read:

- The class has the fully qualified name com.acme.model.Customer.
- The class has the modifiers public and final.
- The constructor takes one String parameter.
- The method name() returns String.
- The method guest() is static and returns Customer.

By default, javap does not display private fields in this output. To view private fields and members as well, you need to use the -private option.

## 5. Filtering members by access level

One of the most common tasks is checking the API that a class exposes to external code. javap provides options to filter by visibility:

| Option | Displayed members |
|---|---|
| -public | Only public classes and public members. |
| -protected | public and protected. |
| -package | public, protected, and package-private. This is the default level. |
| -private | All access levels, including private. |
| -p | Shorthand for -private. |

For example, viewing only the public API:

~~~bash
javap -public -classpath out com.acme.model.Customer
~~~

Viewing both public and protected:

~~~bash
javap -protected -classpath out com.acme.model.Customer
~~~

Viewing package-private members and above:

~~~bash
javap -package -classpath out com.acme.model.Customer
~~~

Viewing all members:

~~~bash
javap -private -classpath out com.acme.model.Customer
~~~

For the Customer class above, the output of -private may look like:

~~~text
Compiled from "Customer.java"
public final class com.acme.model.Customer {
  private final java.lang.String name;
  public com.acme.model.Customer(java.lang.String);
  public java.lang.String name();
  public static com.acme.model.Customer guest();
}
~~~

The field name has private access, so it only appears when using -private or -p. This is a quick way to check what internal fields/methods a library has, or confirm whether a member is actually public as described in the documentation.

Note: javap only displays class file information. The private modifier restricts access according to Java rules, but it is not an encryption mechanism or protection against inspecting the contents of a class file.

## 6. Reading the class header, superclass, and interfaces

The header of the javap output describes the class declaration. For example:

~~~text
public abstract class com.acme.service.BaseService
    extends com.acme.service.AbstractComponent
    implements com.acme.service.Reloadable, java.io.Closeable
~~~

You can read:

- public: the class can be accessed from other packages if the module/package permits.
- abstract: cannot be instantiated directly with a normal constructor.
- extends: the direct superclass.
- implements: the implemented interfaces.

For an interface, the output may look like:

~~~text
public interface com.acme.service.Reloadable
~~~

For an enum or record, javap shows the corresponding class file structure; a record class typically has java.lang.Record as its superclass and generated accessors for its components. Some compiler-generated members may appear when viewing all members.

Do not draw conclusions based solely on a single header line. Use -private or -v if you need to check constructors, fields, compiler-generated methods, bridge methods, or class metadata.

## 7. Viewing JVM signatures with -s

The -s option tells javap to display the internal type signature, commonly called the JVM descriptor, beneath each field or method.

~~~bash
javap -s -classpath out com.acme.model.Customer
~~~

Example output:

~~~text
Compiled from "Customer.java"
public final class com.acme.model.Customer {
  public com.acme.model.Customer(java.lang.String);
    descriptor: (Ljava/lang/String;)V
  public java.lang.String name();
    descriptor: ()Ljava/lang/String;
  public static com.acme.model.Customer guest();
    descriptor: ()Lcom/acme/model/Customer;
}
~~~

Descriptors describe parameter types and return types in JVM format. Basic symbols:

| Symbol | Java type |
|---|---|
| B | byte |
| C | char |
| D | double |
| F | float |
| I | int |
| J | long |
| S | short |
| Z | boolean |
| V | void |
| Lpackage/Type; | Reference type |
| [ | Array |

For methods, a descriptor has the form:

~~~text
(parameter-descriptors)return-descriptor
~~~

Examples:

- ()V: no parameters, returns void.
- (I)I: takes int, returns int.
- (Ljava/lang/String;)V: takes String, returns void.
- ([Ljava/lang/String;)V: takes a String array, returns void.

Descriptors are useful when investigating linkage errors such as NoSuchMethodError. The JVM identifies methods by name and descriptor; changing only a parameter type or return type can change the descriptor, even if the method name stays the same.

## 8. Distinguishing generic Signature and descriptor

Generics in Java are implemented primarily through type erasure. Therefore, the descriptor of a generic method usually contains the types after type parameters are erased, whereas the generic Signature attribute stores additional generic type information for the compiler and reflection to use where appropriate.

For example, file src/com/acme/model/Registry.java:

~~~java
package com.acme.model;

import java.util.List;

public class Registry<T> {
    private final List<T> entries;

    public Registry(List<T> entries) {
        this.entries = entries;
    }

    public T first() {
        return entries.get(0);
    }
}
~~~

Compile:

~~~bash
javac -d out src/com/acme/model/Registry.java
~~~

View the descriptor:

~~~bash
javap -s -classpath out com.acme.model.Registry
~~~

The first() method has a descriptor after type erasure equivalent to:

~~~text
descriptor: ()Ljava/lang/Object;
~~~

Because T is erased to Object according to erasure rules in this example.

To view the generic Signature attribute and detailed metadata:

~~~bash
javap -v -classpath out com.acme.model.Registry
~~~

In the verbose output, look for lines labeled Signature. They show the generic information stored in the class file. Do not confuse a descriptor with a generic Signature: the descriptor serves JVM-level linkage, while Signature retains additional generic type information.

## 9. Viewing constants and static final fields

The -constants option displays the values of static final fields that have a constant value in the class file:

~~~bash
javap -constants -classpath out com.acme.config.AppConfig
~~~

Source example:

~~~java
package com.acme.config;

public class AppConfig {
    public static final int RETRY_LIMIT = 3;
    public static final String MODE = "SAFE";
}
~~~

After compilation, javap -constants can display the values:

~~~text
public class com.acme.config.AppConfig {
  public static final int RETRY_LIMIT = 3;
  public static final java.lang.String MODE = "SAFE";
}
~~~

This option is useful when checking constants packaged into a library, verifying default values, or investigating constant changes between two artifact versions.

Not every static final field has a ConstantValue attribute. Values initialized by a runtime expression may not be displayed this way. Also inspect the bytecode of the static initializer if you need to understand how initialization happens.

## 10. Viewing detailed information with -v

The -v (verbose) option tells javap to display much more class file information, including:

- Minor/major version of the class file.
- Access flags of the class and its members.
- Constant pool.
- Field and method descriptors.
- Attributes such as Signature, Exceptions, RuntimeVisibleAnnotations.
- StackMapTable and metadata used for bytecode verification.
- Information related to bootstrap methods or inner classes.

Example:

~~~bash
javap -v -classpath out com.acme.model.Customer
~~~

Verbose output can be very long. When investigating a specific detail, look for labels such as Classfile, major version, flags, descriptor, Signature, RuntimeVisibleAnnotations, or ConstantValue.

The class file version helps determine which Java level the compiler targeted when generating bytecode. For example, Java 17 uses major version 61. If an older runtime tries to load a class file with a major version higher than it supports, an UnsupportedClassVersionError may occur.

Do not use -v as the default choice when you only need to inspect the API. Detailed output easily adds noise and makes comparisons harder; start with -public or -private, then add -s or -v when you have a specific question.

## 11. Viewing bytecode and debug metadata

The main goal of this article is viewing class declarations, but javap also supports several modes to inspect how methods were compiled:

| Option | Purpose |
|---|---|
| -c | Displays bytecode instructions for each method. |
| -l | Displays the line number table and local variable table if present. |
| -s | Displays field and method descriptors. |
| -v | Displays detailed class file information. |

Example:

~~~bash
javap -c -classpath out com.acme.model.Customer
javap -l -classpath out com.acme.model.Customer
~~~

-c is useful when checking which APIs a method calls, which invoke instructions the compiler generated, or how an expression was compiled. -l is useful when you need to view source line numbers and local variables stored in debug metadata.

Local variable information may not appear if the compiler did not generate the corresponding metadata. When needed, compile with javac -g to request writing debug information:

~~~bash
javac -g -d out src/com/acme/model/Customer.java
~~~

The -g option affects debug metadata in the class file; it does not change the public API declaration of the class. To inspect this information again, use javap -l or javap -v.

## 12. Viewing classes in JARs and external libraries

javap can read classes inside a JAR by placing the JAR on the classpath.

Example:

~~~bash
javap -classpath lib/customer-api.jar -public com.acme.api.Customer
~~~

If you need to combine an output directory with multiple JARs:

~~~bash
javap -classpath "out:lib/api.jar:lib/common.jar" -private com.acme.api.Customer
~~~

On Windows, the classpath separator is a semicolon:

~~~powershell
javap -classpath "out;lib/api.jar;lib/common.jar" -private com.acme.api.Customer
~~~

On Linux and macOS, the classpath separator is a colon. Enclose the entire classpath value in quotes so the shell passes it as a single argument, especially when paths contain spaces.

You can inspect classes in the standard library:

~~~bash
javap -public java.util.ArrayList
~~~

When inspecting classes in named modules, javap supports module path and module options. You can view the exact syntax with:

~~~bash
javap --help
~~~

Distinguish between classpath and module path: classpath locates classes using the traditional class loader mechanism; module path locates packaged modules or module directories according to JPMS. Choose the lookup mechanism that matches how the library is distributed.

## 13. Overloads, constructors, and nested classes

A class can have multiple methods with the same name but different parameter lists. javap displays each overload separately:

~~~java
package com.acme.math;

public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }

    public long add(long a, long b) {
        return a + b;
    }
}
~~~

After compilation, view the descriptors:

~~~bash
javap -s -classpath out com.acme.math.Calculator
~~~

The two add methods have different descriptors:

~~~text
add(int, int)   -> (II)I
add(long, long) -> (JJ)J
~~~

Constructors also appear in the member list. A constructor has no return type in Java syntax, but its JVM descriptor always ends with V because a constructor has the special name <init> and returns no value.

Nested classes are usually compiled into separate class files with binary names containing the $ character. For example, if class com.acme.Outer has a nested class Inner, it can be inspected with:

~~~bash
javap -private -classpath out 'com.acme.Outer$Inner'
~~~

Quotes prevent the shell from interpreting the $ character as a variable. In PowerShell, single-quoted strings also preserve this character literally.

## 14. Using javap to compare APIs between two versions

When upgrading a library, you can inspect the declaration of the same class in two different JARs:

~~~bash
javap -public -s -classpath old-api.jar com.acme.api.Client
javap -public -s -classpath new-api.jar com.acme.api.Client
~~~

Compare the results to detect:

- Removed or renamed public methods.
- Changed parameter types or return types.
- Changed constructors.
- Changed public/static fields.
- Changed class superclass or interfaces.
- Descriptors that are no longer compatible with old client bytecode.

If you need automated comparison, you can redirect the output to files and use an OS diff tool:

~~~bash
javap -public -s -classpath old-api.jar com.acme.api.Client > old.txt
javap -public -s -classpath new-api.jar com.acme.api.Client > new.txt
diff -u old.txt new.txt
~~~

On PowerShell, you can save output using redirection operators and compare with Compare-Object. When comparing, use the same javap version and the same options to minimize unrelated differences.

javap is a useful inspection tool, but it is not a complete binary compatibility checker. For libraries with strict compatibility requirements, combine it with dedicated API analysis tools, real client testing, and versioning practices.

## 15. Common errors when using javap

| Symptom | Common cause | Resolution |
|---|---|---|
| Error: class not found | Incorrect class name or classpath does not point to the package root/JAR containing the class. | Verify the fully qualified binary name and classpath path. |
| javap cannot find the newly compiled class file | javac output is in a different directory or the wrong package path is used. | Check the -d option of javac and use the correct classpath root. |
| Only public methods are visible, private fields are missing | javap is using the default visibility level or -public. | Add -private or -p. |
| Expected generic type is missing from descriptor | JVM descriptors use type erasure. | Use -v and look for the Signature attribute. |
| static final value is not shown | The field has no constant value attribute or -constants was not used. | Use -constants and check how the field is initialized. |
| No local variable names or source line numbers | The class file does not contain the corresponding debug metadata. | Compile with -g, then inspect with -l or -v. |
| Output is too long and hard to read | Using -v or -c when only declarations are needed. | Start with -public, -protected, or -private; add options as needed. |
| Confusion with nested classes | Using the source-level name instead of the binary name. | Use the binary name with $ and enclose it in quotes. |
| Cannot read classes in a module | Using classpath for an artifact distributed as a module or missing module path. | Check how it is packaged and use appropriate module options. |

## 16. Workflow for inspecting class declarations

When given a class or library to investigate, you can follow this sequence:

1. Locate the .class file, JAR, or module containing the class.
2. Identify the package name and the fully qualified binary name of the class.
3. Use the appropriate -classpath or module path so javap finds the right artifact.
4. Start with -public to view the external API.
5. Use -protected or -package when you need to see additional access levels.
6. Use -private to inspect all fields, constructors, and methods.
7. Use -s to verify method/field descriptors.
8. Use -constants to inspect constants stored in the class file.
9. Use -v when you need generic Signature, annotations, class file version, or access flags.
10. Use -c and -l when you need to inspect bytecode and debug metadata.
11. When upgrading a library, compare declarations of both artifacts using the same options and the same javap version.

## 17. Key takeaways

javap lets you see the actual structure of a class file after compilation. For viewing class declarations, the most important options are -public, -protected, -package, and -private to filter members; -s to read descriptors; -constants to view constants; and -v to inspect deeper metadata.

By knowing how to choose the right classpath, use fully qualified binary names, and distinguish descriptors from generic Signatures, developers can inspect the API of their own projects or external libraries, verify changes between versions, and pinpoint the causes of linkage errors without needing the original source code.
