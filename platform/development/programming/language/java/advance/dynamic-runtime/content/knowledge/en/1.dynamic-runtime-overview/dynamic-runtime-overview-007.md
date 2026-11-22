# 1.7. Background Knowledge and Practice Environment with Standard Java 21 APIs

> **Context:** This is the introductory lesson of the **Overview** group in Java Advance – dynamic-runtime. The lesson uses **standard JDK 21** APIs and tools to build a foundation on runtime types, class loading, metadata discovery, dynamic method invocation, and setting up an experimental environment. No frameworks, bytecode generators, or external libraries are needed.

## 1. Learning Objectives and Prerequisites

After this lesson, you will be able to:

1. Explain how **compile time** differs from **runtime**, and distinguish normal polymorphism from looking up/invoking members by name at runtime.
2. Distinguish the **loading – linking – initialization** phases, and the meaning of `Class<?>`, class loaders, and modules.
3. Correctly identify the API groups `Class`, `java.lang.reflect`, `java.lang.invoke`, `Proxy`, `ServiceLoader` and choose the corresponding tool.
4. Install/verify JDK 21 yourself, compile and run pure Java examples, and use `jshell`, `javap`, `jdeps`, and class loading logs.
5. Diagnose errors caused by missing classes, incorrect signatures, access control, module path, and incompatible bytecode.

You should know classes/interfaces, overriding, exceptions, `static`, basic Java generics, and how to use the terminal. The two labs have standalone source code and do not depend on Spring, Maven, or Gradle.

## 2. In What Sense Is Java “Dynamic” at Runtime?

Consider the familiar call:

```java
Greeter greeter = new Greeter();
String message = greeter.greet("An");
```

The compiler checks the `Greeter` type and the `greet` call. If an instance method is overridden, the JVM can select the implementation based on the **actual type of the object** at runtime (*dynamic dispatch*). This is still a statically type-checked Java program.

In mechanisms such as plugins, serializers, dependency injection, test runners, or RPC adapters, the class name or method name is sometimes known only from configuration or metadata. The program needs the additional ability to **find classes**, **read structure**, **invoke members indirectly**, or **create interface implementations at runtime**. Those are the needs commonly referred to as *dynamic runtime*.

```text
Source .java --javac--> bytecode .class
                              |
                              v
                    JVM loads and links class
                              |
                              v
                    Class<?> / metadata / Module
                         /         \
                        v           v
                  Reflection    MethodHandle
                         \         /
                          v       v
                      Invoke member
                              |
                       Proxy / SPI when needed
```

The diagram only illustrates the learning path. The JVM is not required to load, resolve, and initialize every class at the same time.

### 2.1. Loading, linking, and initialization

- **Loading:** The JVM finds the binary definition of a class and creates an object representing the corresponding type. The *binary name* of the class and its defining class loader are key components of **runtime identity**.
- **Linking:** consists of *verification* (checking structure/validity), *preparation* (allocating memory and default values for `static` variables), and *resolution* (resolving symbolic references; can be performed on demand). Linking does not mean running every static initializer of the application.
- **Initialization:** The JVM executes type initialization according to language/JVM rules, including `static` blocks. For example, `Class.forName("java.lang.String")` requests class initialization; the `Class.forName(name, false, loader)` overload does not request immediate initialization.

Do not assume that `Class<?>` allows arbitrarily modifying any running class. It primarily represents **type and metadata**, and remains subject to the constraints of the type system, access control, and the Java Platform Module System (JPMS).

### 2.2. Class names in code and binary names

- `java.util.ArrayList` is the binary name of the `ArrayList` class.
- A nested class `Outer.Inner` typically has a binary name of the form `Outer$Inner`.
- A type's display name, simple name, canonical name, and binary name are not always interchangeable. When calling `Class.forName`, you must use the name required by the API.

## 3. Map of JDK 21 APIs and Tools

| Task | Standard API | Key points to remember |
| --- | --- | --- |
| Represent and look up types | `java.lang.Class`, `ClassLoader` | `Class.forName` looks up by name; the loader can affect type identity. |
| Inspect methods, fields, constructors, annotations | `java.lang.reflect.Method`, `Field`, `Constructor`, `Annotation` | Distinguish `getMethod` from `getDeclaredMethod`; access permissions still apply. |
| Invoke methods or constructors flexibly | `Method.invoke`, `Constructor.newInstance` | The result is usually `Object`; errors inside the target method are wrapped in `InvocationTargetException`. |
| Reference/invoke methods with typed signatures | `java.lang.invoke.MethodHandle`, `MethodHandles.Lookup`, `MethodType` | `invokeExact` requires the types at the call site to match the handle type exactly. |
| Access variables through a handle | `java.lang.invoke.VarHandle` | Allows access modes defined for the variable kind, including memory/concurrency-related operations; not needed for the basic labs. |
| Create runtime implementations of interfaces | `java.lang.reflect.Proxy`, `InvocationHandler` | Standard JDK proxy is **interface-based**; calls are dispatched through the handler. |
| Discover plugins by service contract | `java.util.ServiceLoader` | Only finds providers **registered** via SPI configuration or JPMS; does not automatically scan all classes. |
| Module information and accessibility | `java.lang.Module`, `ModuleLayer` | Distinguish `exports`, `opens`, classpath, and module path. |
| JVM-level dynamic linking | `java.lang.invoke.CallSite`, `invokedynamic` | Foundational topic for advanced mechanisms; no need to generate bytecode yourself in this lesson. |
| Bytecode/runtime diagnostics | Tools `java`, `javac`, `jshell`, `javap`, `jdeps`, `jcmd` | These are JDK executables, not Java packages to import. |

Some lessons on dynamic runtime will go deeper into `java.lang.instrument` or agent loading mechanisms. An agent is a separate deployment environment; you do **not** need an agent for the two labs and should not confuse reflection with bytecode modification. Prefer public Java SE APIs and avoid relying on `sun.*`/`jdk.internal.*`.

## 4. Setting Up the Java 21 Practice Environment

### 4.1. JDK, JAVA_HOME, and PATH

Install a **JDK 21** distribution suitable for your operating system. `JAVA_HOME` should point to the JDK directory; the `PATH` variable needs to include that JDK's `bin` directory. Open a new terminal and run:

```sh
java -version
javac -version
jshell --version
```

Both `java` and `javac` must show major version **21**; patch numbers and vendor names may vary. If you have multiple JDKs, check which executable is actually selected:

| Operating System | Command |
| --- | --- |
| Windows PowerShell/CMD | `where.exe java` and `where.exe javac` |
| macOS/Linux | `command -v java` and `command -v javac` |

`java` is used to run, `javac` is used to compile, and `jshell` is the REPL. Do not confuse “JDK 21 is installed” with “the terminal is running Java 21”.

### 4.2. Organizing the lab directory

Create a `dynamic-runtime-lab` directory in your practice location. Save two standalone files `RuntimeBasicsLab.java` and `ProxyLab.java` there, in UTF-8 format. Each lab has one `public class` matching the file name. Run the commands below **from this directory**.

We are using the **default classpath** (unnamed module) and have not written `module-info.java` yet, because the goal is to understand the APIs before adding module constraints. Use `javac --release 21` so the compiler restricts syntax/APIs to Java 21; to run reliably, you still need a matching Java runtime.

### 4.3. Try it right away with JShell

Run `jshell`, then enter each expression:

```java
Class.forName("java.lang.String").getName()
String.class.getModule().getName()
String.class.getClassLoader()
```

You will see the name `java.lang.String`, module `java.base`, and the value `null` for `String`'s class loader. Here, `null` denotes the **bootstrap class loader**, not an error. The prompt line, temporary variable numbers, and how JShell displays results may vary. Type `/exit` to quit.

## 5. Lab 1: Reflection and MethodHandle Invoking the Same Method

Save the following full content to **`RuntimeBasicsLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class RuntimeBasicsLab {
    public static class Welcome {
        public String greet(String name) {
            return "Xin chào, " + name + "!";
        }
    }

    public static void main(String[] args) throws Throwable {
        Class<?> type = Class.forName("RuntimeBasicsLab$Welcome");
        Object instance = type.getDeclaredConstructor().newInstance();

        Method reflected = type.getMethod("greet", String.class);
        String viaReflection = (String) reflected.invoke(instance, "An");

        MethodHandle handle = MethodHandles.lookup().findVirtual(
            Welcome.class,
            "greet",
            MethodType.methodType(String.class, String.class)
        );
        String viaHandle =
            (String) handle.invokeExact((Welcome) instance, "Bình");

        System.out.println("Class: " + type.getName());
        System.out.println("Reflection: " + viaReflection);
        System.out.println("MethodHandle: " + viaHandle);
    }
}
```

Compile/run:

```sh
javac --release 21 RuntimeBasicsLab.java
java RuntimeBasicsLab
```

**Exact stdout:**

```text
Class: RuntimeBasicsLab$Welcome
Reflection: Xin chào, An!
MethodHandle: Xin chào, Bình!
```

### 5.1. Line-by-line explanation of dynamic meaning

1. `Class.forName("RuntimeBasicsLab$Welcome")` uses the **binary name** of the nested class to obtain `Class<?>` at runtime. The `$` here is part of the class name, not a shell variable.
2. `getDeclaredConstructor().newInstance()` obtains the no-argument constructor and creates an object. Here, the nested class `Welcome` is `public static`, so it does not need a receiver of the outer class.
3. `getMethod("greet", String.class)` specifies the method name and parameter type list; the target method is `public`. `reflected.invoke(instance, "An")` returns `Object`, so we cast it to `String`.
4. `MethodHandles.lookup()` creates a `Lookup` object carrying the permissions of the calling class; `findVirtual` takes the class, method name, and `MethodType` consisting of the return type + declared parameter types. Because it is an instance method, the **handle** takes the `Welcome` receiver as its first argument, forming the effective signature `(Welcome, String)String`.
5. `invokeExact` is a *signature-polymorphic* call: the compiler records the types at the call site. Casting `(Welcome) instance` and casting `(String)` for the result ensure the receiver/return types match the handle exactly. Changing to an incompatible type may throw `WrongMethodTypeException`.
6. Both approaches invoke `Welcome.greet`. The differences lie in the lookup mechanism, signature model, invocation rules, and error handling.

In the lab, `main throws Throwable` keeps the focus on the APIs. Production code should handle exceptions within a clear scope; avoid using `throws Throwable` indiscriminately.

### 5.2. When to use which?

- **Direct call** when the interface/class and method are already known at compile time; the code is clear, refactorable, and best checked by the compiler.
- **Reflection** when you need to inspect metadata, annotations, method names from configuration, or dynamic mapping.
- **MethodHandle** when you need to store a typed invocation, adapt signatures, compose operations in `java.lang.invoke`, or handle low-level dynamic invocation logic.

Do not assume `MethodHandle` is always faster than Reflection; JIT optimizations, caching, warm-up, and benchmark design determine the outcome. Do not compare performance using a few manual loops and draw general conclusions.

## 6. Lab 2: Standard JDK Dynamic Proxy

Save the following content to **`ProxyLab.java`**:

```java
import java.lang.reflect.Proxy;

public class ProxyLab {
    public interface Greeting {
        String say(String name);
    }

    public static void main(String[] args) {
        Greeting proxy = (Greeting) Proxy.newProxyInstance(
            Greeting.class.getClassLoader(),
            new Class<?>[] { Greeting.class },
            (instance, method, arguments) -> {
                if (method.getName().equals("say")) {
                    return "Chào, " + arguments[0] + "!";
                }
                if (method.getName().equals("toString")) {
                    return "GreetingProxy";
                }
                throw new UnsupportedOperationException(method.toString());
            }
        );

        System.out.println(proxy.say("Mai"));
    }
}
```

Run:

```sh
javac --release 21 ProxyLab.java
java ProxyLab
```

**Stdout:**

```text
Chào, Mai!
```

`Proxy.newProxyInstance` returns an object implementing the `Greeting` interface even though you did not declare `GreetingImpl`. The call `proxy.say("Mai")` is routed to the `InvocationHandler` along with the `Method` metadata and argument array; the handler returns a `String` according to the interface contract. This is how to build a runtime implementation of an **interface**, not to automatically create an arbitrary subclass.

In real applications, the handler must properly handle `equals`, `hashCode`, `toString`, and interface default methods when relevant; it must ensure the result has the right type and that exceptions are not hidden. The lab only implements the branches needed for illustration.

## 7. ClassLoader and JPMS: Two Factors That Change Runtime Behavior

### 7.1. Identity of a class

In Java, two classes with the **same binary name** defined by different *defining class loaders* can be **two different runtime types**. This is why plugins or embedded applications can encounter `ClassCastException` even when logs show the “same class name”.

APIs to distinguish:

| Command/API | Correct understanding |
| --- | --- |
| `obj.getClass()` | Gets the runtime class of an existing object. |
| `SomeType.class` | Gets the `Class` object when the type is known directly at compile time. |
| `Class.forName(name)` | Looks up by name and requests class initialization. |
| `Class.forName(name, false, loader)` | Looks up with a specific loader, without requesting initialization at this call. |
| `ClassLoader.loadClass(name)` | Loads/finds a class according to the loader's contract; does not mean the class is always initialized. |
| `Thread.currentThread().getContextClassLoader()` | Context loader provided by the environment/caller, often useful for SPI/frameworks; does not default to the loader of the currently running class. |

Most Java loaders use parent delegation when searching for classes, but you should not assume every custom loader system behaves the same way. For `Class.getClassLoader()`, `null` is a valid value for classes defined by the bootstrap loader.

### 7.2. Classpath vs. module path

The two labs run on the **classpath** and belong to the *unnamed module*. In a JPMS application with `module-info.java`, additional semantics are needed:

- `requires`: declares a module dependency.
- `exports`: allows other modules to access public types according to module rules; not a license for deep reflection into private members.
- `opens`: opens a package for controlled deep reflection; can be scoped with `opens ... to ...`.
- `Module.isExported` and `Module.isOpen`: help check module access permissions at runtime.

`setAccessible(true)` does not allow breaking every boundary; you may encounter `InaccessibleObjectException` when a package belongs to a non-open module. Fix this by designing a public SPI, adjusting the module descriptor, or using appropriate `Lookup` permissions. The JVM flag `--add-opens` should only be used intentionally for compatibility/diagnostics, not as a default solution.

### 7.3. ServiceLoader and plugin architecture

`ServiceLoader.load(Service.class)` only discovers providers that **have declared the service contract**: typically via a `META-INF/services/<fully-qualified-service-name>` file on the classpath, or `uses`/`provides ... with ...` when using named modules. It does not automatically scan all classes.

Remember three distinct questions:

- **Reflection:** “What metadata and methods does this class have; is there permission to access/invoke them?”
- **Proxy:** “Can we build an implementation of an interface and forward calls to a handler?”
- **ServiceLoader:** “Which providers are registered to implement this interface/service?”

Many frameworks combine these mechanisms, but their goals do not overlap.

## 8. Observing Classes and Runtime with JDK 21 Tools

After compiling Lab 1, run the following commands:

```sh
javap -p RuntimeBasicsLab
javap -c RuntimeBasicsLab
jdeps RuntimeBasicsLab.class
java -Xlog:class+load=info RuntimeBasicsLab
```

| Tool | Meaning | Interpretation caveat |
| --- | --- | --- |
| `javap -p` | View class file signatures and members, including non-public ones. | Does not tell you which methods actually ran. |
| `javap -c` | View compiled bytecode; cross-check API calls in `main`. | Bytecode does not reveal all runtime JIT optimizations. |
| `jdeps` | Analyze statically visible bytecode/class/module dependencies. | Cannot guarantee seeing every class loaded only by string name at runtime. |
| `-Xlog:class+load=info` | Enable JVM unified logging for class loading. | Logs can be very long and vary across JVM builds; do not treat them as fixed lab stdout. |
| `jcmd -l` | List JVM processes that the tool can detect. | Output depends on permissions and running JVMs. |
| `java --list-modules` | List observable modules of the runtime image. | Applications on the classpath can still belong to the unnamed module. |

Do not mix **program stdout**, **stderr**, **JVM log lines**, and **tool output** when recording experiment results. Re-run without log flags to confirm the standard stdout of Lab 1.

## 9. Common Error Diagnostic Table

| Error/symptom | Possible cause | How to check |
| --- | --- | --- |
| `ClassNotFoundException` | Wrong binary name or the loader/classpath cannot find the definition. | Check the name, `$` for nested classes, `.class` location, classpath/module path, and loader. |
| `NoClassDefFoundError` | A dependent class is missing at runtime or a previous initialization failed. | Inspect the message and *root cause*, check runtime dependencies and the first error that occurred. |
| `NoSuchMethodException` | Wrong name, overload, parameter types, or using the wrong public/declared lookup. | Compare `getMethod` vs. `getDeclaredMethod`, print parameter types, and check `javap`. |
| `IllegalAccessException` / `InaccessibleObjectException` | Java access rules or JPMS disallow access. | Check member visibility, `Lookup`, `exports`, and `opens`. |
| `InvocationTargetException` | The target method invoked via reflection threw an exception. | Check `getCause()` to find the actual error in the target. |
| `WrongMethodTypeException` | Argument/return types at the handle call site do not match, especially with `invokeExact`. | Print `handle.type()`; check the receiver, parameter count, and return type. |
| `UnsupportedClassVersionError` | The runtime does not understand the compiled class file version. | Check actual `java -version`; Java 21 class files have major version **65**. |
| Proxy returns wrong result | Handler misses a method or returns the wrong type. | Check `method.getName()`, signature, and interface contract. |

Effective debugging workflow: identify the exception and *cause* → reproduce with a fixed command → check versions and classpath/module path → verify names/signatures via metadata/`javap` → change only one assumption → re-run.

## 10. Practice Exercises

**Exercise A — metadata:** Use `Class.forName("java.util.ArrayList")`, print `getName()`, `getSuperclass()`, `getInterfaces()`. Explain why the direct interface list does not necessarily include all inherited interfaces.

**Exercise B — verify initialization:** Create a new class with `static { System.out.println("initialized"); }`. Compare `Class.forName(name, false, loader)` and `Class.forName(name)` in **two separate new JVMs**. A class having been initialized earlier in the same JVM will skew the conclusion if overlooked.

**Exercise C — handle type:** Print `handle.type()` from Lab 1, cross-check receiver + parameter + return types. Try changing one type to an incorrect one and record the exception; finally revert and verify the exact stdout.

**Exercise D — proxy:** Add method `String farewell(String name)` to `Greeting`, extend the handler to respond properly to both `say` and `farewell`. State the expected stdout yourself before running.

**Exercise E — diagnostics:** Inspect `javap -c RuntimeBasicsLab`, locate the Reflection and MethodHandle calls; re-run with the JVM class-load log. Distinguish program output from class-loading logs.

### Self-assessment

- [ ] Both `java` and `javac` are actually Java 21.
- [ ] Both programs compile with `javac --release 21` and produce the described stdout.
- [ ] Can state the differences between loading, linking, and initialization.
- [ ] Can explain why one class name can represent two runtime types when defining loaders differ.
- [ ] Clearly distinguish Reflection, MethodHandle, Proxy, and ServiceLoader.
- [ ] Can name at least three typical errors and how to check their root causes properly.
- [ ] Understand JPMS boundaries during reflective access and do not break access permissions by default.

## 11. Safe Practice Principles

1. When class/method names come from users or external configuration, use an allowlist and check interfaces/contracts; do not instantiate or invoke anything solely from an untrusted string.
2. Reflection and handles must respect Java access control and module boundaries. Design an appropriate public extension point before considering deep reflection.
3. Dynamic runtime increases flexibility but also increases the risk of wrong names, wrong types, and harder debugging. Choose direct calls when possible, and use dynamic mechanisms when requirements truly demand them.
4. For real plugins/class loaders, pay attention to references/caches, thread context loaders, resource lifecycles, and unloadability. `System.gc()` does not guarantee a class is unloaded.
5. Logging and diagnostic flags can produce a lot of output, sometimes containing sensitive environment information; remove them after testing.

## 12. Standard References for Further Lookup

- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Java SE 21 — Reflection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/package-summary.html)
- [Java SE 21 — MethodHandles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 21 — Dynamic Proxy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [JDK 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) and [JDK 21 — java](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)

**Connection to later lessons:** These labs serve as a baseline for in-depth analysis of class loading, reflection, method handles, proxies, SPI, or dynamic linking. When moving to real modules/plugins, compare each new behavior against the working pure Java 21 version.
