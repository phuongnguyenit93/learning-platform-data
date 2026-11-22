# Prerequisites for Java Instrumentation: Class Lifecycle, Bytecode, Class Loaders, Modules, and Concurrency

Java Instrumentation operates on a program at the **class and bytecode** level. Before writing an agent or attaching observability tools, you need to understand where the JVM obtains class definitions, when it verifies and initializes a class, how a class's identity is determined, how modules restrict access, and what happens when multiple threads load classes concurrently. This lesson builds the foundation for those operations; the examples use Java 17 or later.

## 1. Big Picture and Learning Objectives

General flow when running a Java application:

~~~text
.java source code
    │ javac
    ▼
Class file (.class, containing bytecode and metadata)
    │ ClassLoader finds/reads bytes
    ▼
[ClassFileTransformer may receive and transform bytes during class definition]
    │
    ▼
JVM defines the class, links (verification + preparation; resolution on demand)
    │
    ▼
Class initialization upon active use requirement (<clinit>, if present)
    │
    ▼
Method execution, which may be JIT-compiled to machine code
~~~

The diagram illustrates a new class loading case; it does not assert that all linking steps happen at one fixed point in time. **Retransformation/redefinition** is a different flow that affects an already-defined class; it is not simply re-running the entire initialization cycle.

After this lesson, you should be able to:

1. Distinguish **loading**, **linking**, and **initialization**, and identify the exact point where bytes can be transformed.
2. Read the basic structure of a class file and bytecode, and understand why the JVM rejects invalid bytecode.
3. Explain why two classes with the same fully qualified name may still not be the same type if they have different defining class loaders.
4. Distinguish **module readability**, **exports**, and **opens**, especially when an agent uses reflection.
5. Identify contention, reentrancy, deadlock, and consistency issues when class loading/transformation happens concurrently.

## 2. Class Lifecycle: Load, Link, Initialize, Use

### 2.1. Loading — Finding and Defining a Class

When a type with a binary name such as **com.example.Service** is needed, the JVM asks the appropriate class loader to find its definition. In typical implementations, the loader obtains the bytes from the classpath, module path, a JAR, or a custom source and then defines the class (for example via **ClassLoader.defineClass**). The binary name uses dot notation; in the internal name used by class files and transformers, the package separator is typically a slash, such as **com/example/Service**.

You must distinguish:

- **Initiating loader**: the loader involved in requesting the class load; it may delegate to another loader.
- **Defining loader**: the loader that actually defines the class. The defining loader together with the binary name determines the runtime identity of the type.
- **Class object**: the representation of the loaded type; you can query **Class.getClassLoader()**. For many platform classes defined by the bootstrap loader, the result is **null**.

If you use an agent and register a **ClassFileTransformer** early enough, the transformer can be invoked while the JVM is defining the class. The fact that the transformer is invoked **does not mean** the class has already executed its static initializer or constructor.

### 2.2. Linking — Verification, Preparation, Resolution

**Linking** consists of three related activities that do not necessarily complete at the same time:

| Activity | What does the JVM do? | What to remember during instrumentation |
| --- | --- | --- |
| Verification | Checks that the class file and bytecode have valid structure, types, and control flow | Invalid stack, local variables, jump targets, or StackMapTable can cause a **VerifyError** |
| Preparation | Prepares static fields with default values; constant variables have an exception under the **ConstantValue** rule | Do not equate preparation with executing **static {}** blocks |
| Resolution | Converts symbolic references in the constant pool into runtime references, which may expose the need to load additional classes | Can occur early or lazily at the point of use; linkage errors sometimes appear only when a specific branch is executed |

The JVM guarantees that a class is verified and prepared before initialization, but **resolution** is permitted to be performed lazily. Do not rely on a rigid assumption that every type mentioned by a method is already loaded and resolved as soon as the enclosing class is loaded.

### 2.3. Initialization — Running Static Initialization Code

Class initialization executes **<clinit>**, which the compiler synthesizes from non-constant-expression static field assignments and **static {}** blocks in source order. Each class is initialized once per class-definition lifecycle; the JVM synchronizes this when multiple threads request it concurrently.

Actions that can trigger initialization include **new**, reading/writing a non-constant-variable static field, invoking a static method, and certain reflection operations. Conversely, obtaining a class literal such as **Target.class** or reading a compile-time constant does not by itself force initialization.

Standalone example:

~~~java
// File: LifecycleDemo.java
public class LifecycleDemo {
    static class Target {
        static final int CONSTANT = 7;  // compile-time constant
        static int value = initialize();

        static int initialize() {
            System.out.println("Target.<clinit> runs");
            return 42;
        }

        static void ping() {
            System.out.println("ping(): " + value);
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
                "LifecycleDemo$Target",
                false,  // load the class without requesting initialization
                LifecycleDemo.class.getClassLoader()
        );
        System.out.println("Class obtained: " + type.getSimpleName());
        System.out.println("Constant: " + Target.CONSTANT);
        Target.ping();
        Target.ping();
    }
}
~~~

~~~bash
javac --release 17 LifecycleDemo.java
java LifecycleDemo
~~~

Expected output:

~~~text
Class obtained: Target
Constant: 7
Target.<clinit> runs
ping(): 42
ping(): 42
~~~

Explanation: **Class.forName(name, false, loader)** obtains the **Class** object without requesting initialization; the **CONSTANT** value is embedded by the compiler into the bytecode at the call site; the first call to **ping()** is what triggers class initialization. Two calls do not re-run **<clinit>**. If **initialize()** fails, the first attempt may encounter **ExceptionInInitializerError**; subsequent uses may encounter **NoClassDefFoundError** because the class is in a failed initialization state.

### 2.4. Where Instrumentation Sits in the Lifecycle

- **On initial load**: the transformer receives the bytes before the JVM finishes defining/verifying the class. It can return a different valid byte array or **null** to leave it unchanged.
- **When a class is already loaded**: registering a new transformer does not automatically modify existing classes. To affect already-loaded classes, you need a mechanism such as **Instrumentation.retransformClasses** or **redefineClasses**, depending on JVM capabilities and agent permissions.
- **Retransform/redefine does not automatically re-run static initializers** and does not recreate existing objects. Static state remains intact unless program logic actively changes it.
- **Active stack frames** may continue executing the old method definition; new invocations will follow the updated definition. Therefore, redefinition should not be interpreted as an atomic switch for all currently running calls.
- With standard class redefinition/retransformation, the JVM enforces schema-change restrictions: you cannot arbitrarily add/remove fields or methods, change the inheritance hierarchy, or alter many other structural attributes. Transforming **on initial definition** has different latitude than modifying a live class.

## 3. Bytecode: What Does the JVM Actually Read and Verify?

### 3.1. From Java Source to Class File

**javac** turns Java source into a class file (or multiple class files for nested types, anonymous classes, etc.). A class file typically contains:

- **Magic and version**: the class file format signature and the class file version that the runtime must support.
- **Constant pool**: strings, literals, type names, field/method names, descriptors, references to method handles, and entities requiring resolution.
- **Access flags, this/super, interfaces**: type metadata and inheritance relationships.
- **Fields, methods, attributes**: member definitions, annotations, generic signatures, and module/nest/record metadata where applicable.
- **Code attribute** of methods with bytecode: **max_stack**, **max_locals**, the instruction sequence, the exception table, and sub-attributes; **StackMapTable** assists the verifier in modern class file versions.

JVM instructions operate on the **operand stack**, **local-variable slots**, and **constant pool**. For example, an **int** addition may push two operands onto the stack using instructions such as **iload**, perform **iadd**, and return the result with **ireturn**. Variable names and source-level generics are generally not full runtime type information; many generic forms are erased.

### 3.2. Reading Bytecode Instead of Guessing from Source

Create the following file:

~~~java
// File: BytecodeDemo.java
public class BytecodeDemo {
    static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(add(3, 4));
    }
}
~~~

~~~bash
javac --release 17 BytecodeDemo.java
java BytecodeDemo
javap -c -p BytecodeDemo
javap -v -p BytecodeDemo
~~~

**java** prints **7**. In the **add** method, the standard disassembly has the sequence **iload_0**, **iload_1**, **iadd**, **ireturn**; **javap -v** shows the version, constant pool, descriptors, attributes, and additional metadata. When comparing output, observe the **stack effect** of each instruction and the data types along each branch, rather than just reading the mnemonics.

With Java 17, **javac --release 17** produces class file major version **61**. Classes compiled for a version higher than the runtime can cause **UnsupportedClassVersionError**.

### 3.3. Why Can Adding a Few Bytes Break an Entire Class?

Suppose you insert logging instructions at the beginning of a method. If you only add bytes without updating the related structures, errors can occur:

1. **Control flow**: offsets for jumps, exception handlers, and try/catch blocks shift.
2. **Operand stack**: pushing a value of the wrong type, missing a pop/return, or computing an insufficient **max_stack**.
3. **Local slots**: adding a variable while forgetting **max_locals** or using the wrong type.
4. **Stack map frames**: frames no longer match control flow after adding branches.
5. **Descriptors and symbolic refs**: calling a method with an incompatible signature, missing a dependency, or resolving in the wrong loader.
6. **Metadata**: annotations, line numbers, and module/nest/record attributes may need to remain consistent.

Libraries such as **ASM** or **Byte Buddy** handle much of the mechanical work; they do not replace understanding class file structure and program semantics. For instance, ASM's automatic frame computation mode may need to resolve a common superclass; if the resolver uses the wrong class loader, the result can still be wrong. Avoid trying to load application classes inside the transformer solely to infer types, as that can trigger nested class loading.

Minimum rules when transforming: process once per **internal class name**, preserve intended semantics, recompute offsets/frames when needed, check bytecode version compatibility, and test on branches that are actually executed.

## 4. Class Loaders: Type Identity, Delegation, and Isolation

### 4.1. Common Hierarchy

In a modern Java runtime, you typically encounter:

| Loader | Typical role |
| --- | --- |
| Bootstrap | Defines many Java platform classes, supported by the JVM; **getClassLoader()** may return **null** |
| Platform | Part of the platform modules; does not mean all platform classes have special privileges |
| Application/system | Typically loads application code from the appropriate classpath/module path |
| Custom loader | Loads plugins, isolated applications, dynamically generated classes, or implements hot deployment |

Standard loaders typically apply **parent-first delegation**, though custom loaders can use different strategies. The **thread context class loader** is a pointer on a thread for libraries or SPIs to locate implementations; it does not automatically become the defining loader of every class the thread uses.

### 4.2. The Runtime Identity Formula

A runtime type is fundamentally distinguished by **(binary name, defining class loader)**. Two definitions of **example.Item** in two different loaders are two different types, even if the bytecode is identical. Consequently, a cast can fail and **isAssignableFrom** can return **false** even when the class names look identical.

A runnable Java 17 example that defines a separate copy of the nested class **Item** in a different loader:

~~~java
// File: LoaderIdentityDemo.java
import java.io.IOException;
import java.io.InputStream;

public class LoaderIdentityDemo {
    public static class Item { }

    static final class IsolatedLoader extends ClassLoader {
        private final String targetName = Item.class.getName();

        IsolatedLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(targetName)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    String resource = name.replace('.', '/') + ".class";
                    try (InputStream in = getParent().getResourceAsStream(resource)) {
                        if (in == null) {
                            throw new ClassNotFoundException(name);
                        }
                        byte[] bytes = in.readAllBytes();
                        result = defineClass(name, bytes, 0, bytes.length);
                    } catch (IOException e) {
                        throw new ClassNotFoundException(name, e);
                    }
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> fromApp = Item.class;
        Class<?> isolated = new IsolatedLoader(
                LoaderIdentityDemo.class.getClassLoader()
        ).loadClass(Item.class.getName());

        System.out.println(fromApp.getName().equals(isolated.getName()));
        System.out.println(fromApp == isolated);
        System.out.println(fromApp.isAssignableFrom(isolated));
    }
}
~~~

~~~bash
javac --release 17 LoaderIdentityDemo.java
java LoaderIdentityDemo
~~~

~~~text
true
false
false
~~~

**Explanation**: the fully qualified names match, but **IsolatedLoader** calls **defineClass** itself for **Item**; the class loaded from the application loader and the class loaded from the isolated loader have different identities. This pattern intentionally breaks parent-first for a single name for illustration; you should not copy it as-is into a production class loader because there are many other concerns such as packages, resources, sealing, signatures, protection domains, and lifecycle.

### 4.3. Implications for Agents and Transformers

- **ClassFileTransformer** receives both **loader** and **className**. You need to consider **loader + name** when filtering classes, caching bytecode, attaching markers, or recording metrics. Filtering by name alone can collide with multiple definitions in plugin systems or app servers.
- A **null loader** must be handled deliberately; do not call **loader.loadClass(...)** without checking.
- Do not assume the agent's classpath sees all application types. The agent may be loaded by the system loader while the code to observe is defined by a different loader.
- Avoid holding strong references to **Class**, **ClassLoader**, or loader-keyed cache entries indefinitely; that can prevent **class unloading** and cause memory leaks when an application reloads.
- Do not use a transformer to arbitrarily call back into application code: loading new classes while transforming can cause recursion, deadlock, or class circularity.

## 5. Java Platform Module System (JPMS): reads, exports, and opens

Since Java 9, **modules** add an access boundary alongside packages and class loaders. Every class belongs to a module; a module can be **named** (declared via **module-info.java**) or **unnamed** (for example, many classes on the classpath). Each class loader has its own unnamed module; you should not treat all classpath code across all loaders as belonging to the same module.

### 5.1. Three Concepts to Distinguish

| Concept | Meaning | Scenario |
| --- | --- | --- |
| **Readability** | Module A has a reads relationship to module B to reference eligible public types | Declaring **requires** or adjusting the graph when needed |
| **exports** | Allows authorized modules to access **public** types/members of a package under JPMS rules | Using a public API from another module |
| **opens** | Allows **deep reflection** on a package, including accessing non-public members if other reflection rules permit | Agent/framework using **setAccessible(true)** or deep reflection |

Example application module declaration:

~~~java
// File: module-info.java
module com.example.app {
    exports com.example.app.api;
}
~~~

The **com.example.app.api** package is public to other modules with readability; the **com.example.app.internal** package is not exported or opened. **exports** does not by itself allow accessing private fields via reflection. To open the internal package to a named diagnostic module:

~~~java
module com.example.app {
    exports com.example.app.api;
    opens com.example.app.internal to com.example.inspector;
}
~~~

When the application cannot modify **module-info.java**, the runtime environment can choose to open the package to code on the classpath using the flag:

~~~bash
java --add-opens com.example.app/com.example.app.internal=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

This command illustrates the syntax: it only runs when the appropriately named modules/classes have been compiled and are on the **module path**. **--add-exports** and **--add-opens** are not synonymous; use only the minimum privilege required. When an agent has **Instrumentation**, the **redefineModule** API also allows adjusting certain reads/exports/opens relationships at runtime; this does not remove constraints on class loaders and valid bytecode.

### 5.2. Placing Class Loaders Alongside Modules for Diagnostics

When an agent reports that it cannot call an API or read a field, ask in order:

1. **Which loader actually defined the type?** Does the same FQCN guarantee the same **Class**?
2. **Which module is the type in?** Is it a named module?
3. **Can the caller's module read the target module?**
4. **Is the package exported to the caller?** If deep reflection is needed, is it **opened** to the caller?
5. **Do the method/field and access modifiers** permit the intended operation?

For example, **InaccessibleObjectException** typically points to a module deep-reflection restriction; switching to another loader is not a general fix. Conversely, a **ClassCastException** when two names are identical can come from two different loaders, even when the module is already opened.

## 6. Concurrency: Class Loading and Instrumentation Do Not Happen on a Single Thread

### 6.1. The JVM Synchronizes Class Initialization, Not All Agent Data

A class is initialized under JVM synchronization. If multiple threads concurrently use an uninitialized class, one thread performs the required initialization; the other threads are coordinated according to JVM rules. That **does not** make all static mutable fields thread-safe. After initialization completes, mutations are still governed by the Java Memory Model.

Class loaders have class-loading locks associated with **getClassLoadingLock(name)**. Some loaders support parallel-capable class loading; you must not assume all callbacks from different class loads are always serialized. Nested call relationships between transformers, reflection, and custom loaders can lead to circular lock waits or reentrancy.

### 6.2. Happens-before, Visibility, and Atomicity

- **Happens-before** explains when one thread is guaranteed to observe writes from another thread.
- **volatile** establishes visibility/ordering for accesses to that variable, but an operation like **counter++** does not become atomic just because the variable is volatile.
- **AtomicInteger/LongAdder** are suitable for multithreaded counters, depending on whether you need exact instantaneous reads or high throughput.
- **ConcurrentHashMap** is useful for shared caches; multi-step operations on the map still require careful consistency design.
- **ThreadLocal** is only appropriate for thread-bound state and must be cleaned up when using thread pools to avoid stale data lingering.

Example of thread-safe state, applying the same principle to metrics updated by multiple transform callbacks:

~~~java
// File: ConcurrentStateDemo.java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentStateDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger hits = new AtomicInteger();
        ExecutorService executor = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (int i = 0; i < 1_000; i++) {
                tasks.add(executor.submit(() -> {
                    hits.incrementAndGet();
                }));
            }
            for (Future<?> task : tasks) {
                task.get(); // wait for completion and propagate any task error
            }
            System.out.println("Hits: " + hits.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac --release 17 ConcurrentStateDemo.java
java ConcurrentStateDemo
~~~

~~~text
Hits: 1000
~~~

If you replace **AtomicInteger** with a plain **int** and increment it directly from four threads, updates can be lost. **Future.get()** only waits for completion and propagates task results/errors; it does not fix race conditions in the update itself.

### 6.3. Discipline Inside a Transformer

A transformer can run on the thread that is defining the class. Therefore:

1. **Keep callbacks short, bounded, and with minimal side effects**. Avoid long synchronous I/O, global locks, network connections, or calling back into application subsystems.
2. **Do not mutate the input classfileBuffer array in place**; when modification is needed, produce a new valid byte array; return **null** if unchanged. Filter targets accurately by name/loader/module and avoid transforming the agent's own sensitive dependencies.
3. **Expect reentrancy and concurrent invocations**. Guard against repeated transformation if a transformer can run across multiple transform/retransform passes; protect caches with appropriate mechanisms and avoid complex lock ordering.
4. **Do not depend on a fixed load order** across threads, loaders, and libraries. State that must be consistent must be safely published under the Java Memory Model.
5. **Handle errors explicitly**. If a class is transformed into invalid bytecode, the error may surface during define/link, breaking startup or the functionality that class serves. When not sufficiently certain, do not transform that class.

## 7. Minimal Example: Observing the Class Loading Interception Point with a Java Agent

This example **observes** the transformer callback without modifying bytecode. It ties together class loading and internal names without requiring any libraries outside the JDK.

~~~java
// File: TraceAgent.java
import java.lang.instrument.Instrumentation;

public final class TraceAgent {
    public static void premain(String args, Instrumentation instrumentation) {
        instrumentation.addTransformer(
                (loader, className, classBeingRedefined, protectionDomain, classfileBuffer) -> {
                    if ("ProbeApp$Target".equals(className)) {
                        System.out.println("Agent saw: " + className);
                    }
                    return null; // do not modify class bytes
                }
        );
    }
}
~~~

~~~java
// File: ProbeApp.java
public final class ProbeApp {
    static final class Target {
        static void ping() {
            System.out.println("App running");
        }
    }

    public static void main(String[] args) {
        Target.ping();
    }
}
~~~

Create a text file **agent.mf** with the following content (with a trailing newline at the end of the file):

~~~text
Premain-Class: TraceAgent
~~~

Compile, package, and run in a directory containing the three files just created:

~~~bash
javac --release 17 TraceAgent.java ProbeApp.java
jar cfm trace-agent.jar agent.mf TraceAgent.class
java -javaagent:trace-agent.jar ProbeApp
~~~

Output:

~~~text
Agent saw: ProbeApp$Target
App running
~~~

**Interpretation**: the JVM invokes **premain** before **main**, the agent registers the transformer, and then the JVM defines **ProbeApp$Target** when it is used. The **className** value uses the internal class name (with **$** for nested types), while **return null** signals no byte modification. Merely registering a transformer does not guarantee observing classes loaded earlier. In a real agent, you need to add class/module/loader filtering, avoid the agent's own dependencies, check transformation permissions, and design for thread safety. If you want to retransform already-loaded classes, you must check **isRetransformClassesSupported()**, verify **isModifiableClass(...)**, configure **Can-Retransform-Classes** for the agent when needed, and register a transformer that supports retransformation.

## 8. Common Errors and Diagnostic Methods

| Symptom / Error | Cause to check first | Diagnostic step |
| --- | --- | --- |
| **ClassNotFoundException** | Loader could not find the requested name | Correct binary name, classpath/module path, loader, and delegation? |
| **NoClassDefFoundError** | Dependent type missing at runtime or class previously failed initialization | Read the **cause** and the first error log, not just the final message |
| **ClassFormatError** / **UnsupportedClassVersionError** | Malformed class file or major version exceeds runtime | **javap -v**, runtime JDK, and bytes after transformation |
| **VerifyError** | Invalid stack, frames, control flow, descriptors, or types | Disassemble bytecode; compare StackMapTable and jump targets |
| **LinkageError** / loader constraint violation | Inconsistent type definitions/relationships across loaders | Print FQCN, **Class.getClassLoader()**, source JAR, and dependency graph |
| **ClassCastException** with identical class names | Two different defining loaders or incompatible type relationships | Compare the two **Class** objects, loaders, and modules |
| **InaccessibleObjectException** | Package is not **opens** to the module invoking reflection | Check caller's module, **opens**, and JVM flags |
| **UnmodifiableClassException** / unsupported API error | JVM/class does not permit the requested retransform/redefine | Check capabilities and schema restrictions |
| Hang during startup or plugin load | Deadlock/reentrancy between class loader, transformer, and static initializer | Take a thread dump; locate lock owners and load/transform call stacks |
| Wrong metrics or leak after reload | Race condition, non-thread-safe cache, or strong reference held to loader | Evaluate happens-before, atomicity, and lifecycle/cache cleanup |

Foundational tools worth knowing:

~~~bash
javac --release 17 SomeClass.java
javap -c -p SomeClass
javap -v -p SomeClass
java -Xlog:class+load=info SomeClass
java --describe-module java.instrument
~~~

The commands above are illustrative; **SomeClass.java** must exist. **-Xlog:class+load=info** can produce a great many lines; filter the logs for target classes rather than assuming every loaded class came from your transformer. A **thread dump** taken with an appropriate tool (for example **jcmd** on supported JVMs) is often more useful than adding logging right in the middle of code at risk of deadlock.

## 9. Checklist Before Learning or Writing Advanced Instrumentation

- I distinguish **newly loaded classes** from **already-defined classes**, and know why registering a transformer late may not affect older classes.
- I distinguish **load/link/initialize**; I do not expect retransformation to re-run constructors or **<clinit>**.
- I can read **class file version, constant pool, Code, instructions, and stack frames**, and understand when the JVM throws **VerifyError**.
- I associate each class with its exact **defining loader**, handle **null** loaders, and avoid retaining loaders in caches indefinitely.
- I know whether the target module has appropriate **reads/exports/opens**; I do not use deep reflection without permission.
- I know callbacks can be invoked concurrently/reentrantly, protect shared state, and avoid I/O or circular locks on the class-loading path.
- I have ways to observe errors using **javap**, class-load logs, stack traces/thread dumps, and testing on the exact target JDK.

### Self-Check Questions

1. **Why does reading Target.CONSTANT not necessarily run Target.<clinit>?** Because it is a compile-time constant; the caller's bytecode can use the inlined value.
2. **Can two classes with the same FQCN always be cast to each other?** No; the defining class loader is part of the type's identity.
3. **Is exports sufficient to read a private field via setAccessible(true)?** No; deep reflection requires access conditions and the package to be appropriately **opens**.
4. **Why can volatile counter++ still be wrong?** Because read–increment–write is not atomic; multiple threads can lose updates.
5. **Why does a transformer installed after startup not automatically modify all already-loaded classes?** A transformer sees subsequent class definitions; already-loaded classes require a JVM-supported retransform/redefine mechanism.
6. **If a VerifyError occurs after adding logging, what should you check?** Control flow, types on the operand stack, max_stack/max_locals, descriptors, exception table, and stack map frames.

## 10. Authoritative References

- [JVM Specification Java SE 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [JVM Specification Java SE 17 — The class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
- [JLS 17 — Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
- [Java 17 Instrumentation API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 ClassFileTransformer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JLS 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)

The examples use Java 17 public APIs and do not require enabling preview features. When moving to a different runtime/JDK, re-check Instrumentation capabilities, module permissions, and the corresponding agent loading policies.
