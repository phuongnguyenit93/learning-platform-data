# Other Languages on the JVM and the Common Class File Contract

## 1. The JVM runs bytecode, not only Java source code

The Java Virtual Machine (JVM) is a virtual machine with a specification for **class files**, bytecode, class loading, linking, data types, method invocation, and execution. The JVM does not require the original program to be written in Java: any tool that generates `.class` files conforming to the specification, along with the necessary runtime libraries, can run on a compatible JVM.

~~~text
Java (.java) ──────── javac ──────────────┐
Kotlin/JVM (.kt) ──── kotlinc ────────────┤
Scala (.scala) ────── scalac ─────────────┼─→ .class (may be packaged in .jar)
Groovy (.groovy) ──── compiler/runtime ───┤                    │
Clojure (.clj) ────── compiler/runtime ───┘                    ▼
                                           class loader → verify/link → JVM
~~~

Languages share an **execution target**, not necessarily syntax, type system, or program organization. Kotlin has compiler-level nullability; Scala has different ways of representing types/functions than Java; Clojure has namespaces, immutable data, and a dynamic model; Groovy supports metaprogramming. Each language's compiler/runtime maps those features into JVM structures: classes, methods, fields, instructions, metadata, and supporting libraries.

**Scope:** here “Kotlin” means **Kotlin/JVM**, not Kotlin/JS or Kotlin/Native. Other implementations of the same language may use different platforms. Names such as JRuby, Jython, etc. refer to specific implementations running on the JVM, not proof that every Ruby/Python implementation automatically runs Java bytecode.

## 2. Representative JVM languages and interoperability boundaries

| Language | Common execution model | When interacting with Java |
| --- | --- | --- |
| Java | `javac` compiles to class files | Java API and ABI are the familiar linking standard |
| Kotlin/JVM | `kotlinc` generates classes, uses the Kotlin standard library | Getters, top-level functions, default parameters, and nullability have their own mappings |
| Scala | `scalac` generates classes, uses scala-library | Traits, companion objects, functions, and member names may generate bytecode different from source expressions |
| Groovy | Compiler/runtime on the JVM, with dynamic invocation mechanisms | Some operations depend on the Groovy runtime and call sites |
| Clojure | Compiler/runtime creates or loads JVM classes | Clojure functions/namespaces and data do not automatically become ordinary JavaBeans |
| JRuby and other languages | Interpreter, bytecode generation, or JIT depending on the implementation | Interop depends on that implementation's bridge API and runtime |

A JAR is a ZIP archive typically containing `.class` files, resources, and metadata, **not a second kind of bytecode**. A JAR may be missing runtime dependencies; running successfully requires the appropriate classpath/module path and library versions. A valid class also does not mean every method in the source language has an easily callable public Java method.

## 3. Common binary contract: class-file format

At the structural level, the `ClassFile` format consists of:

~~~text
magic (0xCAFEBABE)
minor_version, major_version
constant_pool_count, constant_pool
access_flags
this_class, super_class
interfaces_count, interfaces
fields_count, fields
methods_count, methods
attributes_count, attributes
~~~

- **Magic** identifies the class file; **major/minor version** indicates the format level that the JVM must support.
- **Constant pool** contains constant information, names, descriptors, type/member references, and related data for bytecode to reference.
- **Access flags** describe class/interface characteristics; **this_class**, **super_class**, **interfaces** describe JVM-level type relationships.
- **Fields/methods** contain names, access permissions, types via **descriptors**, and related attributes. For methods with bytecode, the `Code` attribute contains instructions and execution-related information.
- **Attributes** allow recording `Code`, `StackMapTable`, `Signature`, exceptions, annotations, debug information, and compiler/language-specific metadata.

JVM internal type names use `/` such as `java/lang/String`; Java displays binary names in the form `java.lang.String`. Descriptors are an important part of the ABI:

| JVM Descriptor | Type/meaning |
| --- | --- |
| `I`, `J`, `Z` | `int`, `long`, `boolean` |
| `V` | `void`, used for return type |
| `Ljava/lang/String;` | reference to `java.lang.String` |
| `[I` | `int[]` array |
| `(I)Ljava/lang/String;` | method taking `int`, returning `String` |
| `(Ljava/lang/String;)V` | method taking `String`, returning `void` |

JVM calls link based on the class/interface owning the member, name, descriptor, invocation kind, and access rules. A method described in Java as `String greet(String)` has the descriptor `(Ljava/lang/String;)Ljava/lang/String;`. Generic types in source code may undergo **type erasure** and be additionally represented in `Signature`. Bytecode descriptors do not inherently contain all source-level constraints such as Kotlin nullable/non-nullable or all Scala generic details.

### Class file versions

For example, Java 17 emits class file major version **61**; Java 21 uses major version **65**. A JVM can only read class-file versions specified for that runtime release. If you bring a class built with a newer target to an older JVM that does not support it, you may encounter `UnsupportedClassVersionError`.

For Java code, `javac --release 17` on a JDK supporting that option sets the bytecode level and restricts standard Java APIs to Java 17. For Kotlin/Scala or other compilers, the JVM target option must be checked separately: setting a bytecode target **does not by itself prove** that every dependency and called API can run on an older JVM. Preview features also have their own class-file rules; avoid inferring solely from the major number if the program uses preview features.

## 4. How does the JVM load, verify, link, and execute classes?

1. **Loading:** a class loader finds or receives bytes and defines the type. The runtime identity of a class depends on **its binary name and defining class loader**; two different defining loaders can create two separate types even if their names match.
2. **Linking:** the JVM **verifies** class/bytecode constraints, **prepares** static data, and **resolves** symbolic references according to the rules; resolution may happen lazily as needed.
3. **Initialization:** at specified trigger points, the JVM initializes the class/interface and executes the corresponding static initializers.
4. **Execution:** instructions operate on local variables, the operand stack, objects/heap, and other runtime mechanisms. A specific JVM may interpret and then JIT-compile hot code; this does not require the original source to be Java.

Invocation instructions such as `invokevirtual`, `invokestatic`, `invokeinterface`, `invokespecial`, `invokedynamic` perform different invocation mechanisms. A compiler may generate lambdas, bridge methods, synthetic classes, state machines, or bootstrap methods to translate language features into JVM operations. Seeing `invokedynamic` also does not mean the source is necessarily a dynamic language: Java also has cases that use that instruction.

The **Verifier** checks the validity of bytecode according to the specification; it does not prove business logic correctness, does not enforce all nullability rules of the Kotlin compiler, and is not a comprehensive security sandbox mechanism.

## 5. Java 17+ example: creating and inspecting class files yourself

Create the file `src/demo/ContractDemo.java` with the **complete** content:

~~~java
package demo;

interface Message {
    String text();
}

final class Greeting implements Message {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    @Override
    public String text() {
        return "Xin chào, " + name;
    }
}

public class ContractDemo {
    public static void main(String[] args) {
        Class<?> type = Greeting.class;
        System.out.println(type.getName());
        System.out.println(type.getSuperclass().getName());
        System.out.println(type.getInterfaces()[0].getName());
        System.out.println(new Greeting("JVM").text());
    }
}
~~~

From the directory containing `src`, using JDK 17+:

~~~bash
javac --release 17 -d out src/demo/ContractDemo.java
java -cp out demo.ContractDemo
~~~

Exact stdout:

~~~text
demo.Greeting
java.lang.Object
demo.Message
Xin chào, JVM
~~~

Even though declared together in one source file, the compiler generates separate class files for `ContractDemo`, `Greeting`, and `Message`. The JDK's `javap` tool lets you read the actual binary contract:

~~~bash
javap -classpath out -p -s demo.Greeting
javap -classpath out -c -p demo.Greeting
javap -classpath out -v -p demo.Greeting
~~~

`-s` shows descriptors, for example `text()` returning `java.lang.String` has descriptor `()Ljava/lang/String;`; `-c` shows instructions, `-v` shows the constant pool, version, and attributes; `-p` shows non-public members as well. Because the compile command uses `--release 17`, the class file has major version **61**. String concatenation instruction details may differ across compilers, so do not force the entire `javap` output to be identical across all JDK versions.

The observation above helps distinguish three levels: **Java source** (the syntax you write), **class-file API/bytecode** (generated by the compiler), and **runtime behavior** (executed by the JVM). Other JVM languages must still cross the class file boundary, though they may choose different code generation strategies.

## 6. Kotlin/JVM example generating a class for Java to call

This example requires **JDK 17+ and the Kotlin command-line compiler/runtime**. Create `src/demo/Greeter.kt`:

~~~kotlin
package demo

class Greeter(private val who: String) {
    fun greet(): String = "Hello, $who"
}
~~~

Create `src/demo/JavaCaller.java`:

~~~java
package demo;

public class JavaCaller {
    public static void main(String[] args) {
        Greeter greeter = new Greeter("JVM");
        System.out.println(greeter.greet());
    }
}
~~~

The commands below assume `kotlinc`, `javac`, and `kotlin` are in PATH:

~~~bash
kotlinc -jvm-target 17 src/demo/Greeter.kt -d out
javac --release 17 -cp out -d out src/demo/JavaCaller.java
kotlin -cp out demo.JavaCaller
~~~

Stdout:

~~~text
Hello, JVM
~~~

Because `kotlinc` created `demo/Greeter.class`, `javac` can compile `JavaCaller` thanks to the `out` classpath. Java calls the constructor and public method `greet()` based on the JVM ABI, without needing to understand Kotlin syntax. The `kotlin` command provides the Kotlin standard library at runtime. If replaced with `java -cp out demo.JavaCaller` without adding the Kotlin runtime, the program may fail with missing runtime classes; real projects use Gradle/Maven to declare and package dependencies.

Inspect the ABI directly with:

~~~bash
javap -classpath out -p -s demo.Greeter
~~~

The result will show the JVM constructor, private field, and method generated by the compiler; there is no need to infer JVM members solely from the shape of Kotlin syntax.

## 7. Why is multi-language interop not completely transparent?

### 7.1. Source-level API differs from JVM-level API

In Kotlin/JVM, a property `val name: String` typically has a getter `getName()` for Java to call rather than defaulting to a public field. Top-level functions are generated in a class named after the file or a customized name. Default parameters **do not automatically** generate all Java overloads; `@JvmOverloads` supports certain cases. `@JvmName`, `@JvmStatic`, `@JvmField` adjust how the JVM API is exposed when appropriate.

A `suspend` function may use a continuation and a state machine; the JVM method in `javap` may differ from the Kotlin signature read in the source. Scala has companion objects, traits, and its own compiled structures; Groovy/Clojure have functionality invoked through a dynamic runtime. For Java callers to use it reliably, design and verify the **public JVM API**, rather than guessing based on similarity of source function names.

### 7.2. Nullability, generics, and advanced types

The JVM distinguishes primitives/references and descriptors, but does not have a single shared type system mode for all source languages. For example, Kotlin's `String` and `String?` may both use the reference descriptor `Ljava/lang/String;`; the compiler, annotations, metadata, and additional runtime checks express the difference. Java code can still pass `null`, so the Java/Kotlin boundary needs a clear nullability contract.

With ordinary Java generics, `List<String>` and `List<Integer>` use the same JVM type after erasure; source generic information may appear in `Signature` and is not equivalent to two separate runtime classes. Bridge methods, casts, or runtime type tokens may be necessary when mapping different abstractions.

### 7.3. Exceptions and runtime libraries

Checked exceptions are a checking rule in the Java compiler, **not a verifier rule forcing every JVM caller to catch them**. Kotlin does not enforce checked exception checking like Java; exposing `throws` information to Java requires the corresponding compiler/annotation mechanism when needed.

Compiled code does not mean it is independent of the language runtime. Kotlin has the Kotlin standard library; Scala has scala-library; Groovy/Clojure have their respective runtimes. You must check both the **compile classpath** (to compile the caller), the **runtime classpath/module path** (to load and run), dependency versions, and how the JAR is packaged. “Having a .jar file” does not prove it is a self-contained executable fat JAR.

### 7.4. Class loaders and runtime type boundaries

If two defining class loaders load two copies with the same name `example.Greeter`, the JVM treats them as two types; a cast can throw `ClassCastException` even though the display names are identical. This situation commonly occurs in plugins, application containers, and hot reload. The class file contract does not automatically eliminate type identity issues caused by loaders.

## 8. Source compatibility, binary compatibility, and behavior

There are three compatibility layers to consider independently:

1. **Source compatibility:** can a caller keeping its source unchanged still compile against the new API?
2. **Binary compatibility (ABI):** can an already-compiled caller still link/run with the new library without recompiling?
3. **Behavioral compatibility:** the API still runs, but are the results, side effects, and conventions still correct?

Removing a method/constructor, renaming a JVM member, changing a descriptor, changing static to instance, or changing inheritance relationships can cause linkage errors for old callers. Conversely, preserving the ABI does not guarantee preserving behavior. Kotlin/Scala compiler and runtime versions also have their own binary compatibility guarantees: being JVM bytecode does not prove all versions of them are interchangeable.

| Error/symptom | Investigation direction |
| --- | --- |
| `UnsupportedClassVersionError` | Class-file version is higher than what the currently running JVM supports |
| `ClassNotFoundException` | The class lookup mechanism by name could not find the matching class |
| `NoClassDefFoundError` | A class needed at execution time could not be loaded/defined, possibly due to a missing dependency or an earlier initialization failure |
| `NoSuchMethodError` | The caller requests a method name/descriptor that does not exist in the runtime library |
| `AbstractMethodError`, `IncompatibleClassChangeError` | Class/method relationships at runtime diverge from how the caller was linked |
| `VerifyError` | Bytecode/class file failed verification |
| `ClassCastException` when type names look identical | Check inheritance relationships and defining class loaders |

Do not conclude the cause solely from the exception name; you need the stack trace, dependency tree, classpath/module path, class loader, and the actual loaded class file.

## 9. Workflow for exploring an unfamiliar JVM library

When you want to call a compiled library from Java or another JVM language, follow these practical steps:

1. **Inspect classes and resources:** `jar tf library.jar`.
2. **Verify the public API:** `javap -classpath library.jar -public -s ten.package.TenClass`, paying attention to member names and descriptors.
3. **Inspect metadata and version when needed:** `javap -classpath library.jar -p -v ten.package.TenClass`; check class-file major version, `Signature`, annotations, and synthetic/bridge methods.
4. **Cross-check the runtime environment:** JDK version, compiler target, Kotlin/Scala/Groovy/Clojure runtime, dependency versions, module path or classpath.
5. **Compile a minimal Java caller:** run it with the proper runtime/dependencies to verify linkage rather than only looking at source.
6. **When upgrading versions:** compare the generated ABI and the library/compiler compatibility policy, especially when callers are not recompiled.

Running on the same JVM **does not guarantee identical performance**. Allocation, boxing, dynamic calls, reflection, coroutine scheduling, JIT warm-up, and library implementations all have an impact. For a fair comparison, measure with an appropriate workload/benchmark.

## 10. Common misconceptions

- “The JVM only runs Java”: false, it runs code following the JVM class-file/runtime contract.
- “All class files run on every JVM”: false, you must consider bytecode version, runtime, dependencies, and environment.
- “Same JVM means same nullability/generic/exception rules”: false, many constraints are handled by the source compiler or its own runtime.
- “Valid Kotlin/Scala code means Java can call every function by the same name”: false, you need to check the actual JVM ABI.
- “A JAR already has all dependencies”: false, that is only true for packaging types that include them.
- “The verifier proves bytecode is correct and safe”: false, it verifies JVM constraints and does not replace logic testing and security review.

## 11. Self-check questions

1. Why can `javap` read `Greeter.class` generated by the Kotlin compiler? Because `.class` conforms to the JVM class-file format structure.
2. Distinguish `(Ljava/lang/String;)V` from `()Ljava/lang/String;`? The former takes a `String` and returns no result; the latter takes no parameters and returns a `String`.
3. Are two classes with the same name but defined by two different defining loaders the same runtime type? No.
4. When Java calls a Kotlin library and an error about missing `kotlin.*` occurs, what should be checked first? The runtime classpath/dependencies and the Kotlin standard library.
5. When updating a JAR causes `NoSuchMethodError`, what is the first tool to help check? `javap -s` on the class in the runtime JAR to compare method names and descriptors with the ABI expected by the caller.

**Core takeaway:** The JVM class file is the common contract for loading, verifying, linking, and executing multiple languages. Practical interoperability also depends on the **compiler-generated ABI**, versions and runtime dependencies, class loaders, and the additional semantics of each language.
