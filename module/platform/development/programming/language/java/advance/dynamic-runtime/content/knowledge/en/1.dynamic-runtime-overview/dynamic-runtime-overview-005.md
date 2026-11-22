# 1.5. Distinguishing Using Compiled Code from Generating, Compiling, and Defining New Code

## Learning Objectives

After this lesson, you can:

- Distinguish **using an already-compiled class** from **generating source code**, **compiling source code into bytecode**, and **defining a class from bytecode in a running JVM**.
- Explain the distinct roles of the compiler, class loader, class linking/initialization, Reflection, and JIT.
- Identify cases that actually generate bytecode or a new class definition at runtime, even without Java source code.
- Choose the appropriate approach for applications, plugins, proxies, and code generation tools; recognize limitations regarding class loaders, deployment, and safety.

## 1. Four Easily Confused Actions

In Java, the phrase “using dynamic classes” can refer to several different actions. You need to ask precisely: **is new source code being generated, is new bytecode being compiled/generated, and is the JVM defining a new class from bytecode or merely using an existing definition?**

| Action | Input | Direct Result | Does it necessarily generate new bytecode at runtime? |
| --- | --- | --- | --- |
| **Using compiled code** | Classes already on the classpath/module path, or an existing library | Calling constructors, methods, fields; can select a class by name or via an interface | No |
| **Generating new source code** | Strings, templates, AST, or configuration | Source text such as a Java file | Not yet; having source alone is not enough for the JVM to run |
| **Compiling source code** | Java source and required dependencies | Bytecode in a .class file or in memory; accompanied by diagnostics if it fails | Yes, if compilation succeeds and actually produces bytecode |
| **Class definition** | Valid class bytecode and a class-loading context | A Class object representing the class definition in the JVM | Not necessarily: the bytecode may have been compiled beforehand |

**“Class definition” in the JVM context is not synonymous with writing a class declaration statement in source code.** When a class loader defines a class from .class data, the JVM creates the runtime identity for that class. This also happens when a previously compiled class is loaded for the first time; therefore, “defining a new class in the JVM” **does not by itself prove** that source code or bytecode was just generated at runtime.

A clearer way to observe this is along two independent axes:

1. **When does the bytecode appear?** Before running (build/deploy) or while the program is running.
2. **Which class loader defines the bytecode, and when?** A class can be defined by the JVM on demand, even if the bytecode has existed on disk for a long time.

For example, a plugin .jar compiled yesterday that is loaded into the JVM by the application today is still **using compiled bytecode**, and at the same time may be **defining that class for the first time in a class loader**. Conversely, a program can compile new source into .class without ever loading/defining that class.

## 2. Processing Chain from Source to Execution

~~~text
At development time / at runtime:
.java --(javac or JavaCompiler)--> .class (bytecode)
                                        |
                                        v
                class loader finds/reads bytecode to load
                                        |
                                        v
                        define the class in the JVM
                                        |
                                        v
                     linking: verify, prepare, resolve (*)
                                        |
                                        v
                 initialize the class when conditions require
                                        |
                                        v
                new / method call / Reflection / MethodHandle
                                        |
                                        v
             JVM interprets or JIT optimizes executable code
~~~

(*) **Resolution** may be performed lazily on demand; the diagram should not be understood as requiring all references to be resolved immediately on a fixed schedule. **Loading**, **linking**, and **initialization** are distinct concepts:

- **Loading/defining:** finding bytes and forming a class in the JVM, associated with the defining class loader.
- **Verification:** checking bytecode validity rules; **preparation:** allocating and setting default values for static variables; **resolution:** translating symbolic references into concrete references (can be deferred).
- **Initialization:** executing static variable initializers and static blocks according to Java semantics, when the class is actively used or when required by an API.
- **Execution/JIT:** executing methods and possibly compiling bytecode into machine code for optimization; **JIT is not** the step of compiling Java source into .class files.

**Class.forName("ClassName")** is commonly used to select a class by name at runtime. With its single-parameter overload, it also requests initialization of the class. **ClassLoader.loadClass("ClassName")** loads the class, but this operation itself does not necessarily initialize it immediately. Neither is responsible for generating or compiling Java source.

## 3. Case A: Using Compiled Classes, Even When Selecting Classes with Reflection

Create two Java files in the same directory.

**ExistingGreeting.java**

~~~java
public class ExistingGreeting {
    public String message() {
        return "Hello from existing bytecode!";
    }
}
~~~

**UseExisting.java**

~~~java
public class UseExisting {
    public static void main(String[] args) throws ReflectiveOperationException {
        // The class name is only decided when the program runs.
        Class<?> type = Class.forName("ExistingGreeting");

        Object instance = type.getDeclaredConstructor().newInstance();
        String text = (String) type.getMethod("message").invoke(instance);

        System.out.println(text);
    }
}
~~~

Compile first, then run:

~~~bash
javac -encoding UTF-8 ExistingGreeting.java UseExisting.java
java UseExisting
~~~

Output on stdout:

~~~text
Hello from existing bytecode!
~~~

**What actually happens:**

1. The **javac** command creates **ExistingGreeting.class** and **UseExisting.class** before the **java** command runs.
2. While **UseExisting** is running, **Class.forName** looks up the class by name and can cause the JVM to load, define, and initialize **ExistingGreeting** if that has not been done yet.
3. Reflection obtains the constructor/method from that class definition and invokes the method.
4. **No** new Java source is generated; **no** new compilation is invoked from **UseExisting**.

If you remove **ExistingGreeting.class** from the classpath (and the class cannot be found elsewhere), the **Class.forName** call will fail with **ClassNotFoundException**. Reflection does not automatically infer or compile the **ExistingGreeting.java** file still sitting on disk.

**Note:** The **new ExistingGreeting()** syntax also uses a compiled class, but the class name is referenced directly in code. **Class.forName** adds the ability to **select** the class by name at runtime; that is dynamic selection of which class to use, not generating a new class.

## 4. Case B: Generating Source, Compiling, and Loading a New Class at Runtime

Java provides the standard **javax.tools.JavaCompiler** API (JSR 199) so a program can ask the Java compiler to compile source at runtime. This is a multi-step chain: **generate source → compile → obtain bytecode → load/define class → use**.

The example below is self-contained and runs on **JDK 17+ with the jdk.compiler compiler module**. It creates a source file in a temporary directory, invokes the compiler, opens a URLClassLoader to load the newly generated .class file, and invokes a method.

**CompileAtRuntime.java**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileAtRuntime {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "This runtime does not provide JavaCompiler (jdk.compiler).");
        }

        Path dir = Files.createTempDirectory("runtime-java-");
        Path sourceFile = dir.resolve("RuntimeOnlyGreeting.java");

        String source = """
                public class RuntimeOnlyGreeting {
                    public String message() {
                        return "Hello from newly compiled code!";
                    }
                }
                """;

        try {
            // Step 1: the program generates source itself while running.
            Files.writeString(sourceFile, source, StandardCharsets.UTF_8);

            // Step 2: compile the generated source into a .class file.
            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();

            try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(
                            diagnostics, null, StandardCharsets.UTF_8)) {

                Iterable<? extends JavaFileObject> units =
                        manager.getJavaFileObjects(sourceFile.toFile());

                Boolean success = compiler.getTask(
                        null,
                        manager,
                        diagnostics,
                        List.of("-encoding", "UTF-8", "-d", dir.toString()),
                        null,
                        units
                ).call();

                if (!Boolean.TRUE.equals(success)) {
                    throw new IllegalStateException(
                            "Compilation failed: " + diagnostics.getDiagnostics());
                }
            }

            // Step 3: load/define the class from the newly generated .class.
            URL[] urls = { dir.toUri().toURL() };
            try (URLClassLoader loader = new URLClassLoader(
                    urls, CompileAtRuntime.class.getClassLoader())) {

                Class<?> type =
                        Class.forName("RuntimeOnlyGreeting", true, loader);

                // Step 4: use the new class via Reflection.
                Object instance = type.getDeclaredConstructor().newInstance();
                System.out.println(type.getMethod("message").invoke(instance));
            }
        } finally {
            // This example generates only one .java file and one .class file.
            Files.deleteIfExists(dir.resolve("RuntimeOnlyGreeting.class"));
            Files.deleteIfExists(sourceFile);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Run in the directory containing the example file:

~~~bash
javac -encoding UTF-8 CompileAtRuntime.java
java CompileAtRuntime
~~~

Output on stdout:

~~~text
Hello from newly compiled code!
~~~

Corresponding responsibility table:

| Code snippet | Role | What it does not do on its own |
| --- | --- | --- |
| **Files.writeString** | Generates new Java source | Does not compile or load the class |
| **JavaCompiler.getTask(...).call()** | Parses, checks, and compiles source; outputs .class file | Does not invoke methods on the new class |
| **new URLClassLoader(...)** | Prepares the search path for the loader | Creating a loader does not mean any class is loaded |
| **Class.forName(..., true, loader)** | Requests finding/loading, defining if needed, and initializing the class | Does not generate or compile source |
| **getMethod(...).invoke(...)** | Invokes behavior on an instance of the defined class | Does not create additional classes just by using Reflection |

**Key point:** This example generates a new class name (**RuntimeOnlyGreeting**) that the parent loader does not have; **URLClassLoader** can read the .class from the temporary directory. The loader ultimately uses the JVM's class-definition mechanism. The code does not directly call **ClassLoader.defineClass**, yet the **definition** step still occurred.

Some practical conditions: **ToolProvider.getSystemJavaCompiler()** can return **null** if the runtime does not provide a compiler; the source code must be valid; the public class file name must match; dependencies and compiler options must be configured correctly. JavaCompiler can compile source in memory using custom **JavaFileObject/FileManager**, without necessarily writing .java/.class to disk like the educational example.

## 5. Defining a Class Directly from Bytecode: Java Source Is Not Required

If you already have a byte array representing a valid .class file, code can define a class **without calling JavaCompiler**. That bytecode may be generated at runtime by a bytecode generator, compiled beforehand by another program, or read from an external source.

Common APIs/mechanisms:

- **ClassLoader.defineClass(...)**: a protected API used by class loader subclasses when defining a class from bytecode. You cannot arbitrarily call this protected method from any class in any context.
- **MethodHandles.Lookup.defineClass(byte[])**: defines an ordinary class from bytecode in **the same runtime package and class loader** as the lookup class, with the required access permissions; it does not automatically perform static initialization.
- **MethodHandles.Lookup.defineHiddenClass(...)**: serves hidden classes for specialized runtime mechanisms; identity and lookup rules differ from ordinary classes.
- **java.lang.reflect.Proxy**: can create proxy classes at runtime to implement known interfaces. This creates a new runtime class even though the application does not write and compile a Java source string itself.
- Libraries such as **Byte Buddy** or **ASM** can construct bytecode directly, but they are additional libraries rather than default Reflection behavior.

The following snippet **only illustrates a single API step, not a standalone runnable program**; the **bytes** variable must contain a valid prepared class file, the class's package name must be compatible with the lookup, and the lookup must have **PACKAGE** access:

~~~java
// bytes: valid bytecode of a class not yet defined
// in the corresponding class loader/package.
byte[] bytes = obtainValidClassBytes();
Class<?> defined = java.lang.invoke.MethodHandles
        .lookup()
        .defineClass(bytes);
~~~

The **obtainValidClassBytes()** function here is an illustrative placeholder, not part of Java SE. This snippet demonstrates the separation: **defining a class from bytes** is a separate step; there is no source generation or javac invocation.

If the bytes are invalid, have the wrong package/access permissions, have an incompatible bytecode version, or duplicate a class name already defined in the same loader, the API may throw the corresponding error (**ClassFormatError**, **IllegalArgumentException**, **IllegalAccessException**, **UnsupportedClassVersionError**, **LinkageError**, ...).

## 6. Classification Table of Practical Scenarios

| Scenario | Generates new source at runtime? | Generates/compiles new bytecode at runtime? | Can define a new runtime class? | Correct interpretation |
| --- | --- | --- | --- | --- |
| **new MyService()** with an existing class | No | No | Yes, if the class is loaded/defined by the loader for the first time | Using compiled code |
| **Class.forName("plugin.Impl")** with an existing .jar | No | No | Yes, if the class has not yet been defined by the loader | Loading and using compiled code by name |
| **ServiceLoader.load(MyService.class)** finding a packaged provider | No | No | Possibly | Discovering/instantiating an existing provider, not compiling a provider itself |
| **JavaCompiler** compiling source generated from a template | Yes | Yes, when compilation succeeds | Only when the bytecode is subsequently loaded/defined | Dynamic source generation + compilation |
| Program **reads an existing .class and calls defineClass** in a new loader | No | No | Yes | Defining from existing bytecode |
| **Proxy.newProxyInstance(...)** | Not Java source supplied by the application | May generate proxy bytecode when needed | Yes | Runtime creates a proxy class, different from merely calling Reflection |
| **ASM/Byte Buddy** generator produces bytes and defines a class | Not required | Yes | Yes | Creating a class directly from bytecode |
| **JIT** optimizes a running method | No | Does not produce new .class files | Not because of the JIT step itself | Compiling bytecode to machine code, a different meaning of “compile” |

Three rules can be drawn from this table:

1. **Reflection is not code generation by default**: Reflection can inspect and invoke members on existing classes.
2. **Generating bytecode does not equal loading a class**: the compiler can produce a .class file without the program ever using or defining that class.
3. **Loading/defining a class does not equal dynamic compilation**: a loader usually just reads pre-built bytecode.

## 7. Class Loader Identity and Why a New Class Is Not Simply “Overwriting the Old Class”

In the JVM, the identity of an ordinary class is determined by its **binary name** (for example **com.example.Plugin**) **and its defining class loader**. Two .class files with the same name defined by two different loaders are two different types at runtime; you cannot automatically cast an object of one class to the other.

Conceptual example:

~~~text
Loader A defines com.example.Plugin -> Class A
Loader B defines com.example.Plugin -> Class B

Same binary name, but Class A != Class B.
An instance of Class A is not automatically an instance of Class B.
~~~

Within a single loader, **you cannot redefine the same binary name as another ordinary class** by calling defineClass again; attempting a duplicate definition will encounter a linkage error. Replacing the .class file on disk also **does not change** the live definition in the loader.

To deploy a new version while the application is still running, one design approach is to use a **new loader** to load the new version, switch business references over to the new instances, and then let old objects/loaders lose all remaining references if you want the JVM to have a chance to reclaim them. This should not be interpreted as replacing the old class “in place”; old instances still belong to the old loader's class. **Instrumentation/redefinition** mechanisms have their own contracts and limitations, and are not an automatic consequence of JavaCompiler or defineClass.

Ordinary class loaders following the **parent delegation** model ask the parent first. Therefore, placing new bytecode with the same name as a class already visible to the parent does not guarantee the child loader will pick the new version. For plugins, you must clearly design the classpath policy, parent, shared packages, common interfaces/APIs, and loader lifecycle. Closing a **URLClassLoader** helps release the I/O resources it holds, but **does not guarantee** the class will be unloaded immediately; unloading depends on the ability to garbage-collect the class loader and related references.

## 8. Distinguishing Common Types of “Dynamic” Behavior in Java

**Dynamic dispatch:** When calling an overridden method through an interface/base class, the runtime selects the implementation based on the actual type of the object. What is “dynamic” here is **method selection**, not necessarily creating/compiling a new class.

**Reflection:** The runtime inspects metadata, finds constructors/methods/fields, and accesses them according to visibility/module rules. It makes using classes more flexible, but the invoked members are usually already in existing bytecode.

**MethodHandle and invokedynamic:** Support flexible call-site linkage models in the JVM. The word “dynamic” does not mean that using them compiles new Java source. Some internal mechanisms or frameworks may generate auxiliary/hidden classes, but each mechanism must be analyzed specifically.

**Dynamic proxy/code generation:** The runtime generates class/bytecode structures to create interceptors, adapters, or interface implementations, usually without needing to emit readable .java source.

**Runtime Java compilation:** The application actively generates/receives source, runs the compiler, and then processes the new .class. This is the clearest option when the requirement genuinely calls for “compiling Java while the application is running,” at the cost of needing a compiler, dependency sources, diagnostics handling, and loader management.

**JIT compilation:** The JVM optimizes loaded bytecode into machine code for execution. Do not equate it with the **JavaCompiler** API or the **javac** compiler that produces .class files.

## 9. Choosing the Right Mechanism

| Practical requirement | Usually suitable approach | Considerations |
| --- | --- | --- |
| Calling application code known at build time | Static references, interfaces, dependency injection | Simple; easy type checking and deployment |
| Selecting an implementation by config/class name, already built | Interface + **ServiceLoader** or **Class.forName** | Managing classpath/module path, API contract, constructors |
| Loading a plugin .jar without restarting | Dedicated class loader, shared plugin API | Separating class identity, lifecycle, and loader reclamation |
| Creating a wrapper object around an interface to intercept methods | **java.lang.reflect.Proxy** or proxy framework | Must understand interface/proxy limits and invocation behavior |
| Generating classes from a schema or high-speed configuration | Bytecode generator like Byte Buddy/ASM | More complex; requires verifying bytecode and JVM version |
| Executing new Java source generated by the system | **JavaCompiler** + class loader, or a separate build pipeline | Requires JDK/compiler, error handling, and execution security |

Not every “dynamic configuration” need requires creating new classes. If the variations are just data (rules, parameters, known strategies), prefer configuration and existing interfaces before introducing runtime class compilation/definition.

## 10. Technical Constraints and Common Errors

### 10.1. The Compiler Is Different from the Java Runtime

**java** runs compiled applications, whereas **javac** is the compiler; **ToolProvider.getSystemJavaCompiler()** provides a compiler only when the runtime environment has a suitable implementation (typically a full JDK with **jdk.compiler**). An application packaged with a custom runtime image may lack this module. You must verify on the actual deployment environment, not just on the development machine.

### 10.2. Source and Bytecode Must Be Consistent

A public top-level class in source must match the file name when using ordinary Java files. You must account for imports, classpath/module path, target version, encoding, and API version. Bytecode generated by a newer JDK may not run on an older JVM, causing **UnsupportedClassVersionError**.

### 10.3. Successful Compilation Does Not Guarantee Successful Loading

A class can compile successfully yet fail at runtime due to missing dependencies, different API versions, or incorrect module accessibility. Typical errors include:

- **ClassNotFoundException:** an operation looking up a class by name cannot find the class.
- **NoClassDefFoundError:** the JVM cannot obtain a required definition during linking/use (for example, a missing dependency or a prior initialization failure).
- **ClassFormatError/VerifyError:** the class file is malformed or violates bytecode requirements.
- **LinkageError** and its subclasses: linking issues such as duplicate definitions or incompatible class versions.
- **ExceptionInInitializerError:** static initialization of the class threw an error.

Errors during compilation via **JavaCompiler** should be collected and presented using **DiagnosticCollector**, rather than merely logging “compile failed”.

### 10.4. A Class Loader Is Not a Security Sandbox

Compiling and running arbitrary source is equivalent to giving that code the opportunity to perform actions that the JVM process is permitted to do. Merely moving code into a new class loader **does not** make the code safe. If there is untrusted source/bytecode, you must design a separate execution boundary (such as an isolated process, restricted OS permissions, resource policies, time/memory limits, input controls, and auditing) suited to the threat model. Do not rely on Reflection, class loaders, or package names to control execution permissions.

### 10.5. Resource and Lifecycle Management

Compilation is often expensive in CPU, memory, and I/O; creating too many classes/loaders can increase metadata in metaspace, warm-up time, and the risk of retaining references long-term. You should cache by an appropriate key/version, close file managers/loaders when no longer needed, monitor diagnostics, and clearly define a plugin upgrade policy. Deleting a .class file after it has been loaded is not equivalent to unloading the class.

## 11. Self-Check

**Question 1.** An application reads an implementation name from config, calls **Class.forName**, and then calls a method. Does it compile a new class itself?

**Answer:** No. It selects and uses a class with existing bytecode. If the class has not yet been defined by the loader, loading/defining may occur at runtime, but there is no new Java compilation step.

**Question 2.** A program uses **JavaCompiler** to create **Plugin.class** in a temporary directory and then exits without calling a loader. Has the JVM used Plugin's runtime definition yet?

**Answer:** No, at least not solely because of that compilation step. The existence of a .class file is not enough to say the class has been loaded/defined and used in the application's JVM.

**Question 3.** A framework generates bytecode with ASM and then calls a class-definition API; it does not create .java source. Is a new runtime class created?

**Answer:** Yes. Generating bytecode and defining a class does not require corresponding Java source.

**Question 4.** Two different loaders both define the name **example.Plugin**. Can they be treated as the same type just because the names are identical?

**Answer:** No. Class identity includes the defining loader; you must account for type compatibility and shared interfaces.

**Question 5.** After a program runs, the JVM JIT-compiles a method. Does that mean the application just generated Java source and invoked javac?

**Answer:** No. JIT optimizes bytecode into machine code for execution, which is different from the path from Java source to a .class file.

## Key Takeaways

- **Using compiled code** answers the question “from which bytecode does the program execute behavior?”.
- **Generating source** answers the question “where is new source generated/obtained?”.
- **Compiling** answers the question “has the source been turned into bytecode?”.
- **Defining a class** answers the question “which loader turned the bytecode into a runtime type in the JVM?”.
- The four activities can occur in combination, but **you should not use one term to stand for all of them**. In particular, **Class.forName/Reflection is not itself JavaCompiler**, and **JavaCompiler is not itself the step of defining/using a class**.

## References

- Java SE 17, **JavaCompiler / ToolProvider**: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- Java SE 17, **MethodHandles.Lookup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, **ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Language Specification, **Chapter 12 — Execution**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
