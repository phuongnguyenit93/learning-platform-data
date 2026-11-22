# Finding the Binary Representation and Creating `Class` in the JVM

## 1. Objectives

In the Java class lifecycle, **class loading** answers two practical questions:

1. Where does the JVM obtain the **binary representation** of a class or interface?
2. From that representation, how does the JVM create the **runtime type definition** and the **java.lang.Class** object representing the type?

This is the central step before analyzing the **linking** and **initialization** steps in depth. Already having a **Class** object **does not mean** that **static** initialization code has been executed.

After this lesson, you will be able to:
- Explain the relationship between binary names, class files, bytecode sources, and class loaders.
- Describe how the JVM requests a loader to find or define a class, as well as how it creates a Class mirror.
- Distinguish an **initiating loader** from a **defining loader** and explain a class's identity.
- Understand why classes with the same name but different loaders may not be castable to one another.
- Verify using Java 17+, the **javap** and **jar** commands, and JVM logging.

## 2. From Source Code to Binary Representation

For a typical Java class, the program follows this path:

~~~text
src/demo/Widget.java
         │ javac -d out ...
         ▼
out/demo/Widget.class              ┐
or a file inside a JAR             ├─ source containing class-file bytes
or bytecode from another source    ┘
         │
         │ JVM asks class loader to find/define the class
         ▼
JVM reads the provided binary representation
         │
         ├─ checks required name and definition
         ├─ creates the JVM's internal type representation
         └─ associates it with a java.lang.Class object
         │
         ▼
Class<?> representing demo.Widget
         │
         ├─ can be linked according to JVM rules
         └─ initialized when initialization conditions occur
~~~

A **binary representation** is the data describing the structure and executable code of a class/interface. In the familiar case, it is the **JVM class file format**. The Java compiler **javac** typically generates **.class** files from **.java** files, but the JVM does not require every class to originate from a separate **.class** file on disk: bytecode can also be obtained from a JAR, dynamically generated in memory, or from a loader's own source.

A typical **.jar** file is a **ZIP archive containing multiple entries**, in which entries such as **demo/Widget.class** contain the bytecode of each class. A JAR **is not** a single binary representation of all the classes inside it.

### 2.1 Components Inside a Class File

A class file is structured according to the Java Virtual Machine Specification, for example:

| Part | Role |
| --- | --- |
| Magic number **0xCAFEBABE** | Class file format signature. |
| Major/minor version | Indicates the class file format version that must be supported. |
| **constant_pool** | Contains constants, names, types, and required **symbolic references**. |
| Access flags, this_class, super_class, interfaces | Describes the class, superclass, interfaces, and access properties. |
| Fields and methods | Describes members, descriptors, and attributes; code for applicable methods is stored in the **Code** attribute. |
| Attributes | Metadata such as Code, SourceFile, LineNumberTable, annotations, bootstrap methods..., depending on the class. |

For example, **demo.Widget** can be referenced in the constant pool by the internal type name **demo/Widget**. At runtime, these symbolic references are processed according to linking rules; having a constant pool **does not mean** every reference has already been resolved immediately when the class is loaded.

The JVM defines the class file format and constraints for loaders to provide valid bytes. Corrupted bytecode, bytecode with a mismatched name, or bytecode not supported by the running JVM can lead to errors such as **ClassFormatError**, **NoClassDefFoundError**, or **UnsupportedClassVersionError**, depending on the specific cause. Those errors are different from simply not finding a resource on the classpath.

### 2.2 Three Easily Confused Name Forms

Consider a class declared as **package demo; public class Widget**:

| Context | Corresponding Name | Usage |
| --- | --- | --- |
| **Binary name** | **demo.Widget** | Class name passed to **ClassLoader.loadClass** or **Class.forName** for a normal class. |
| **Internal name** in a class file | **demo/Widget** | The **/**-delimited form in many class file structures. |
| Common **resource path** | **demo/Widget.class** | Entry path searched in the classpath/JAR in typical loader implementations. |
| **Descriptor** of a type reference | **Ldemo/Widget;** | Field/method descriptor syntax. |

A nested class that is not top-level can have a binary name such as **demo.Outer$Inner**. **demo.Outer.Inner** is how the name is written in many source code contexts, but it is not the binary name of that normal kind of nested class.

**Note:** replacing dots with **/** and appending **.class** is a commonly used resource lookup convention, not a mandatory algorithm for every loader. A custom loader can read bytes from memory, a database, the network, or encrypted data.

## 3. Who Finds the Class? Class Loaders and Delegation

The JVM uses class loaders to bring class definitions into the runtime. In typical Java applications, there are:

- **Bootstrap loader:** provided by the JVM to define many platform classes; **Class.getClassLoader()** usually returns **null** for classes defined by the bootstrap loader.
- **Platform loader:** serves the appropriate platform modules.
- **Application/System loader:** usually loads application code from the classpath/module path within its scope of responsibility.
- **Custom loader:** built by an application/library, for example a plugin system, engine, or container.

This is a general model; this order should not be treated as a fixed sequence of directories on disk or a guarantee that every JVM/custom loader searches for classes from the same locations.

### 3.1 Common Delegation Mechanism

With the default implementation of **ClassLoader.loadClass(name, resolve)**, a loader typically:

1. Checks whether a class with that name has already been found/loaded by this loader.
2. If not, asks the parent loader (or the bootstrap loader if applicable).
3. If the parent cannot find it, calls its own **findClass(name)**.
4. If the **resolve** parameter requests it, performs the appropriate resolveClass step before returning.

The idea is to let related loaders share platform classes and avoid unnecessary duplicate definitions. However, Java allows a **custom class loader** to have its own delegation policy. You cannot apply the **parent-first** rule to every loader without checking the implementation code.

### 3.2 Initiating Loader and Defining Loader Are Different

Suppose application loader **A** is asked to find **java.lang.String**, and delegates to bootstrap loader **B** to define String:

~~~text
load request to A
       │
       └─ A forwards to B
                  │
                  └─ B defines java.lang.String
                         │
                         └─ A receives the corresponding Class<?>
~~~

In JVM terminology:
- **Initiating loader:** a loader that the JVM records as having initiated the loading of that class (which may include a delegating loader).
- **Defining loader:** the loader that **actually defines** the class/interface from the binary representation or according to the appropriate class creation rules.

In the example, **A** can be an initiating loader, while **B** is the defining loader. Calling **A.loadClass(...)** **does not prove** that A is the defining loader of the result.

For a normal class, **clazz.getClassLoader()** indicates the loader that defined that class (or **null** if the class was defined by the bootstrap loader). It is not an API that lists all initiating loaders that have ever requested the class.

## 4. When Does the JVM Create the Class Object and What Is It Used For?

When the JVM creates a runtime class/interface from a binary representation, it also has a corresponding **java.lang.Class** object so that Java code can describe and manipulate the type. This is commonly referred to as a **Class mirror**.

A Class object can be obtained via:

~~~java
Class<?> a = String.class;
Class<?> b = someObject.getClass();
Class<?> c = Class.forName("demo.Widget", false, loader);
Class<?> d = loader.loadClass("demo.Widget");
~~~

The operations above are not completely equivalent:

- **T.class** obtains the Class mirror for type T without itself requesting T's static initializer to run.
- **object.getClass()** obtains the actual runtime class of an already existing object.
- **Class.forName(name, false, loader)** requests loading (and linking per the API contract) of the found class, but **does not initialize the class on this call**.
- **ClassLoader.loadClass(name)** finds/loads the class and returns the Class object; this call **does not proactively initialize** the class. Reference resolution depends on JVM timing/rules and the overload called.
- **Class.forName(name)** in its single-argument form requests initialization by default for the found class, so it can cause the static initializer to run immediately.

**A Class mirror is not an instance of the class it describes.** For example, **Widget.class** has the static type **Class<Widget>**; that object is used for metadata/reflection, whereas **new Widget()** is how to create an instance of Widget. **getDeclaredConstructor().newInstance()** also creates an instance and can trigger initialization before calling the constructor.

The information a Class mirror allows inspecting includes the class name, superclass, interfaces, declared members, annotations, module, and class loader. The JVM has internal runtime data structures for execution, though the specification **does not mandate** a fixed memory layout for every JVM; a **java.lang.Class** object is not a direct byte-for-byte copy of the **.class** file.

## 5. Java 17+ Example: Finding Bytecode and Observing the Class Mirror

Create the following two files in the proper directories:

~~~text
project/
└── src/
    └── demo/
        ├── Widget.java
        └── LoadingDemo.java
~~~

**src/demo/Widget.java**:

~~~java
package demo;

public class Widget {
    static {
        System.out.println("Widget initialized");
    }

    public String message() {
        return "Hello";
    }
}
~~~

**src/demo/LoadingDemo.java**:

~~~java
package demo;

public class LoadingDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = LoadingDemo.class.getClassLoader();

        String resource = "demo/Widget.class";
        System.out.println("resource found = "
                + (loader.getResource(resource) != null));

        Class<?> type = loader.loadClass("demo.Widget");
        System.out.println("binary name = " + type.getName());

        Class<?> again = Class.forName("demo.Widget", false, loader);
        System.out.println("same Class = " + (type == again));

        System.out.println("before instance creation");
        Object instance = type.getDeclaredConstructor().newInstance();
        System.out.println("instance type = "
                + instance.getClass().getSimpleName());
    }
}
~~~

From the **project** directory, run:

~~~bash
javac -d out src/demo/Widget.java src/demo/LoadingDemo.java
java -cp out demo.LoadingDemo
~~~

**Expected stdout** when using the application classpath exactly as in the command above:

~~~text
resource found = true
binary name = demo.Widget
same Class = true
before instance creation
Widget initialized
instance type = Widget
~~~

Analysis:

1. **javac -d out** creates the files **out/demo/Widget.class** and **out/demo/LoadingDemo.class**. These are the binary representations for the application loader to find.
2. **getResource("demo/Widget.class")** shows that the bytecode as a resource can be found in this example. Simply seeing the resource **does not yet mean** the class has been defined by the JVM.
3. **loadClass("demo.Widget")** returns the Class object describing Widget. There is no **Widget initialized** line yet: the program has not triggered the initialization of Widget.
4. **Class.forName(..., false, ...)** returns the same Class because it requests the same binary name through the same loader setup in the example; the **==** operator is true because it is the same runtime definition.
5. **getDeclaredConstructor().newInstance()** triggers initialization before creating the instance; the static block prints exactly once before reaching the final line.

In specialized loaders, **getResource** may be blocked, mapped differently, or able to find a resource while **loadClass** cannot define the corresponding class. Therefore, probing for a resource is useful when debugging a normal classpath, but **does not replace** the actual result of **loadClass**.

### 5.1 Inspecting the Binary Representation with javap

After compiling:

~~~bash
javap -classpath out -v demo.Widget
~~~

Some information to look for in the output (version values and indices vary by JDK/compiler):

- **Classfile .../out/demo/Widget.class**, class name, superclass;
- **major version** along with the constant pool;
- type names or method/field descriptors;
- the **<clinit>** method containing code for the static initializer;
- the **Code** attribute in methods that have bytecode.

To view only the bytecode instructions, use:

~~~bash
javap -classpath out -c -p demo.Widget
~~~

Depending on the shell language, the output content can be long. **javap** helps inspect the compiled class file; it **does not prove** that the runtime JVM loaded the class from that exact file if the application runs with a different classpath, module path, or loader.

If packaging a JAR:

~~~bash
jar --create --file example.jar -C out .
jar --list --file example.jar
~~~

You will see entries such as **demo/Widget.class** and **demo/LoadingDemo.class**. The **jar --list** command only lists data inside the archive; it does not load or initialize classes into a running JVM.

## 6. Defining a Class from Bytecode: What Creates a New Definition?

In a custom loader, the **defineClass(...)** method supported by ClassLoader allows converting a valid byte array into a class defined by that loader. A common flow is:

~~~text
ClassLoader.loadClass(name)
       │
       ├─ returns known class / delegates to parent
       │
       └─ finds bytecode (for example in findClass)
               │
               ▼
     defineClass(binaryName, bytes, ...)
               │
               ▼
       new Class<?> defined by the loader
~~~

If you call **defineClass** for the same binary name that the same loader has already defined once, it cannot silently replace the existing Class with different content: the JVM enforces constraints against duplicate definitions and may throw a **LinkageError**. The **redefine/retransform** mechanism provided by instrumentation is a separate matter, not a new defineClass call to create a second Class within the same loader.

The loader must provide a matching binary name, valid bytes, and comply with package/protection domain restrictions and loading constraints. **defineClass** is an operation that creates a runtime definition, not an API that guarantees the class has executed its static initializers.

### 6.1 Class Identity = (binary name, defining loader)

In the JVM, the identity of a class/interface is determined by its **binary name combined with its defining class loader**. Direct consequences:

- Same name and **same class definition**: identical Class references.
- Same name but **defined by two different loaders**: two **different** runtime types.
- Printing the same **Class.getName()** is not enough to confirm that two objects can be cast to one another.

Model:

~~~text
                  bytecode for isolated.Payload
                             │
                     ┌───────┴────────┐
                     ▼                ▼
              defining loader L1   defining loader L2
                     │                │
                     ▼                ▼
               Class #1           Class #2
                name =             name =
          isolated.Payload    isolated.Payload
                     │                │
                     └───────┬────────┘
                             ▼
                 Class #1 != Class #2
~~~

In applications with plugins, modular runtimes, and containers, this is a common cause of a **ClassCastException** that looks nonsensical on the surface: two classes with the same name belonging to two runtime definitions.

### 6.2 Runnable Example: Two Loaders Independently Defining the Same Binary Name

Create the structure:

~~~text
project/
└── src/
    └── isolated/
        ├── Payload.java
        └── TwinLoadersDemo.java
~~~

**src/isolated/Payload.java**:

~~~java
package isolated;

public class Payload {
    public String value() {
        return "payload";
    }
}
~~~

**src/isolated/TwinLoadersDemo.java**:

~~~java
package isolated;

import java.nio.file.Files;
import java.nio.file.Path;

public class TwinLoadersDemo {
    static final class ByteArrayLoader extends ClassLoader {
        Class<?> defineOwn(byte[] classBytes) {
            return defineClass(
                    "isolated.Payload",
                    classBytes,
                    0,
                    classBytes.length
            );
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("out/isolated/Payload.class")
        );

        ByteArrayLoader left = new ByteArrayLoader();
        ByteArrayLoader right = new ByteArrayLoader();

        Class<?> a = left.defineOwn(bytes);
        Class<?> b = right.defineOwn(bytes);

        System.out.println("same name = "
                + a.getName().equals(b.getName()));
        System.out.println("same Class = " + (a == b));
        System.out.println("different defining loader = "
                + (a.getClassLoader() != b.getClassLoader()));

        Object first = a.getDeclaredConstructor().newInstance();
        Object second = b.getDeclaredConstructor().newInstance();
        System.out.println("same runtime type = "
                + (first.getClass() == second.getClass()));

        try {
            a.cast(second);
        } catch (ClassCastException ex) {
            System.out.println("cross-loader cast = ClassCastException");
        }
    }
}
~~~

From the **project** directory:

~~~bash
javac -d out src/isolated/Payload.java src/isolated/TwinLoadersDemo.java
java -cp out isolated.TwinLoadersDemo
~~~

Stdout:

~~~text
same name = true
same Class = false
different defining loader = true
same runtime type = false
cross-loader cast = ClassCastException
~~~

Both ByteArrayLoaders receive **the exact same byte array** yet call **defineClass** separately. This is an example of intentionally defining classes separately to demonstrate class identity; the **defineOwn** method directly illustrates the defineClass API, **bypassing the default parent delegation mechanism of loadClass**. In real applications, you typically implement **findClass** in a controlled manner and let **loadClass** execute the appropriate delegation process.

If you modify the example so that both loaders delegate to the same parent to define Payload, the result can be the **same** Class object; simply instantiating two loader objects does not automatically create two definitions of Payload.

## 7. Special Cases: Arrays, Primitives, Hidden Classes, and Modules

You should not apply the model of **finding a .class file on disk** to every type supported by the JVM.

### 7.1 Array Classes

For an expression such as:

~~~java
String[] names = new String[2];
Class<?> arrayType = names.getClass();
~~~

The JVM creates an array class according to its own rules rather than searching for a **[Ljava/lang/String;.class** file. The component type affects the defining loader of the array class; an array whose component type is a primitive has the bootstrap loader. Creating a **Foo[]** array does not require initializing Foo merely because the array is allocated.

The runtime name of an array class is represented in descriptor form, for example **[Ljava.lang.String;** in **Class.getName()**, so it cannot be treated as a regular filename.

### 7.2 Primitives and void

**int.class**, **boolean.class**, and **void.class** have Class mirrors, yet they do not correspond to a class file like **int.class** on the classpath. The JVM creates and manages these Class objects according to special rules.

### 7.3 Hidden Classes

APIs such as **MethodHandles.Lookup.defineHiddenClass** support classes intended for special runtime purposes; you should not assume that every class can be looked up again by binary name via **ClassLoader.loadClass**. Hidden classes must be distinguished from regular classes/interfaces defined by a loader by name.

### 7.4 Modules and Lookup Scope

When using the Java Module System, the **module path**, module graph, readability, exports, and loader/module policies affect which classes can be found and who can access them. Having a path containing **.class** or **.jar** files **is not sufficient** to conclude that a class will be accessed successfully at runtime. **Class.getModule()** is one data source for runtime inspection, while a module name and a binary class name remain two different concepts.

## 8. Distinguishing Finding Bytes, Loading, Linking, and Initialization

| Observation | What Can Be Concluded | What Cannot Yet Be Concluded |
| --- | --- | --- |
| **jar --list** shows **demo/Widget.class** | The JAR contains an entry with that name. | The JVM has loaded Widget. |
| **getResource** returns a URL/stream | The loader or resource mechanism located the resource. | Those bytes have definitely been defined as a Class. |
| **loadClass("demo.Widget")** returns a Class | The call returned the corresponding runtime Class. | Widget's static initializer has run. |
| **Class.forName(name, false, loader)** returns a Class | The class is found/loaded and linked per the API contract, without requesting initialization in this call. | Every symbolic reference has already been resolved at that point. |
| **Class.forName(name)** returns a Class | For a regular class, the call requests initialization. | An instance constructor has run or a Widget object has been created. |
| **new Widget()** succeeds | Widget was initialized according to the rules before creating the instance. | The class will be initialized again for subsequent objects. |

Because **linking** comprises verification/preparation/resolution with specific timing defined by the specification, combining **javap**, logging, and a program with a static block provides more perspectives than relying on a single log alone.

## 9. Diagnosing Errors When Finding Class Definitions

### 9.1 Class Exists in File/JAR, Yet ClassNotFoundException Occurs

Check:

1. Is the name passed to **Class.forName** or **loadClass** the exact **binary name**? For nested classes, check the **$** character.
2. Do the runtime **-cp**, **--module-path**, and other library configurations contain the required definition? The classpath used during **javac** does not automatically guarantee the same classpath during **java**.
3. Which loader is receiving the request? Does it have custom delegation/filtering? For instance, code inside a plugin may use a different loader from application code.
4. Does the class actually exist under the exact package and name after building or packaging the JAR?

**ClassNotFoundException** is a checked exception commonly thrown by APIs that look up a class by name. **NoClassDefFoundError** is a LinkageError that can appear when the JVM needs a class definition that is unavailable or when the class previously failed to initialize. The two errors can be related, but they are **not synonymous**.

### 9.2 ClassFormatError or UnsupportedClassVersionError

**ClassFormatError** indicates that the class file data has an invalid format; **UnsupportedClassVersionError** occurs when the VM does not support the provided class file version. Check the compiler with **javac -version**, the runtime with **java -version**, or **javap -verbose** to compare versions. This error cannot be resolved merely by changing the class name.

### 9.3 NoSuchMethodError, IllegalAccessError, LoaderConstraintViolation

These may be errors during resolution/linking or binary incompatibility, such as having two versions of a library on the actual loading path. With different loaders, the JVM also enforces type-consistency constraints at certain usage points; a **LinkageError** related to a loading constraint requires checking the defining loaders of the classes sharing the same name.

### 9.4 ClassCastException Despite Identical Class Names

Inspect the object and check:

~~~java
Class<?> actual = object.getClass();

System.out.println(actual.getName());
System.out.println(actual.getClassLoader());
System.out.println(actual.getModule());
~~~

Compare it against the target type's Class using **==**, **getClassLoader()**, **getModule()**, and where the bytecode actually originated. Recent casting error messages often indicate the loader/module of the involved classes. **Do not work around this by force-casting**; instead, align the shared API contract, loader visibility, or how types are shared between the host and plugins.

## 10. Tools for Observing Classes in Practice

In Java 17+ environments, a fairly useful option when you need to see which classes the JVM has loaded is:

~~~bash
java -Xlog:class+load=info -cp out demo.LoadingDemo
~~~

The log usually shows the class name and source according to the capabilities of the VM in use, though the format and number of lines depend on the JDK/VM. To check the tags and log levels supported by the VM:

~~~bash
java -Xlog:help
~~~

**Limitation:** class loading logs tell you that a class has been loaded, **not when <clinit> is executed**. For class identity issues, inspect **Class.getClassLoader()** or observe the actual Class instance. For class files on disk, use **javap -v** to read their structure. For packaged artifacts, use **jar --list** to confirm that the entry exists.

In large systems, enabling full logging for every class can be noisy. Create a small reproducible example first, use the exact classpath/module path, and then broaden your observation if needed.

## 11. Common Misconceptions

- **“A class name is enough to identify a type.”** Not enough: the defining loader is part of the runtime identity.
- **“I found the .class in the JAR, so the JVM has definitely loaded it.”** False: having an entry in a JAR does not mean the running loader used that entry.
- **“loadClass always re-reads the file on every call.”** False: loaders typically use a cache or mechanism to look up already-loaded classes; duplicate definitions within the same loader are restricted.
- **“The loader receiving the request is the defining loader.”** False when delegation is involved.
- **“Class<?> is a raw copy of the bytecode sitting in the heap.”** False: Class is an object reflecting the runtime type; its internal layout is a VM detail.
- **“Once a Class exists, the static initializer has already run.”** False: loading and initialization are distinct.
- **“Every type has a .class file.”** False: primitives, void, arrays, and certain special runtime forms are handled separately.
- **“Every custom loader is parent-first.”** Not necessarily; you need to read the loader's delegation policy.
- **“Using getResource is enough to prove a class is defined.”** False: resource lookup and class definition are two separate steps.

## 12. Self-Check

**Question 1.** For the **demo** package, why are **demo.Widget**, **demo/Widget**, and **demo/Widget.class** three different strings?

**Answer:** They are respectively the binary name, the internal name form, and the common resource path. The **loadClass** API for a normal class accepts a binary name, while files/JARs typically contain the resource path.

**Question 2.** Why can **loader.loadClass("demo.Widget")** return a Class without printing the line inside the static block?

**Answer:** It loads/returns the Class without proactively initializing the class; the static initializer runs when an initialization condition is met.

**Question 3.** Two ByteArrayLoaders receive the same bytes and both call defineClass for the same name. Why are the Class objects different?

**Answer:** The binary name is the same, but the defining loaders differ; the JVM treats them as two separate class definitions.

**Question 4.** A custom loader A delegates to parent B and receives back a Class defined by B. Does the Class's **getClassLoader()** return A or B?

**Answer:** It returns the defining loader B (if not bootstrap). A can be an initiating loader.

**Question 5.** Should you infer that the VM has initialized a class if you only see a **class+load** log?

**Answer:** No. Class loading logs reflect loading; initialization must be verified separately.

**Question 6.** Why does the primitive **int** still have **int.class** even though there is no class file on disk?

**Answer:** The JVM provides Class mirrors for primitives according to its own rules; it does not require a normal class file lookup.

## 13. Key Takeaways

Break the path down into independent questions:

~~~text
Binary name
    ↓
Who receives the load request?
    ↓
From what source does the loader find the bytes?
    ↓
Which loader actually defines the class?
    ↓
JVM creates runtime definition + Class mirror
    ↓
Linking/initialization occur under their own conditions
~~~

The **binary representation** is the data describing the class; the **defining loader** together with the binary name determines the runtime class's identity; the **Class mirror** is the Java object representing that definition. These three concepts explain most classpath issues, plugin isolation, and the confusion between “seeing the bytecode” and “the JVM having defined the class”.

**Further reading from the Java SE 21 specification:**
- JLS §12.2 (*Loading of Classes and Interfaces*): https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2
- JVMS §4 (*The class File Format*): https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- JVMS §5.3 (*Creation and Loading*): https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3
- ClassLoader API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
