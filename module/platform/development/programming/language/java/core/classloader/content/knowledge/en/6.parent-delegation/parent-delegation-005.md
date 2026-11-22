# Defining loader and initiating loader in the JVM

## 1. Why are there two “loader” concepts?

When reading Java code, you often encounter the expression:

~~~java
Class<?> type = loader.loadClass("demo.Widget");
~~~

It is easy to conclude that the **loader** object itself is the loader that **defined** the class **demo.Widget**. That conclusion can be wrong: **loader** may receive the request and then **delegate** to another loader. The JVM distinguishes two roles:

- **Defining loader**: the loader that actually creates/defines the runtime class or interface from the type's representation; for an ordinary class, this is the loader that directly defines the class.
- **Initiating loader**: a loader that participates in **initiating loading** of a class or interface, even though it may return a definition created by another loader.

A runtime type has **one defining loader**, but it can be **initiated** by many different loaders. That is why “the loader asked to find the class” and “the loader that owns the class's runtime definition” are two separate questions.

This article focuses on the **delegation mechanism** and the distinction between these two roles according to the JVM Specification (JVMS §5.3, §5.3.4), then connects them to `Class` objects, type identity, APIs, and real-world error scenarios.

## 2. Conceptual example: A requests, B defines

Suppose an application has loader **ChildLoader A** and parent **AppLoader B**. B has found and defined the class **demo.Shared**.

~~~text
                 JVM / Java code
                       |
                       | asks A to find demo.Shared
                       v
              ChildLoader A
              (initiating)
                       |
                       | delegates via parent-first
                       v
              AppLoader B
              (defining)
                       |
                       | finds/defines demo.Shared
                       v
           Class<?> of demo.Shared
                       |
                       | returns the same Class object
                       v
                  ChildLoader A
                       |
                       v
                requesting code
~~~

In this delegation scenario:

1. **A** receives the load request. A may be recorded as an initiating loader of the returned type.
2. **B** provides the actual runtime definition; **B** is the defining loader.
3. The result returned from **A.loadClass("demo.Shared")** still has **getClassLoader() == B**.
4. If multiple child loaders delegate to B, they can receive **the same `Class` object**.
5. No new class “defined by A” is created merely because A received the request.

**Terminology note:** The steps below describe a loader receiving and delegating a request. The JVMS is the exact basis for determining an *initiating loader* in the context of JVM loading records; do not simply count every ClassLoader object that appears in a Java call chain and claim that all of them are recorded by the JVM as initiating loaders. In particular, the definition of an initiating loader is tied to JVM loading events, not a set arbitrarily named by the application.

## 3. Exact definitions according to the JVM Specification

JVMS §5.3 describes loading as the process of finding a binary representation of a class/interface and creating the runtime type. For a **non-array class/interface**:

- Loader **L** can obtain the bytecode itself and ask the JVM to create the class from that representation: **L directly defines the class**.
- Loader **L** can also **delegate** the work to another loader, and then return the class that the other loader defined: **L loads indirectly**.
- If the JVM asks **L** to initiate loading and L returns a class created by another loader, **the initiating loader and the defining loader can differ**.
- A defining loader also serves as an initiating loader of the class it defines. A class can be recorded with additional initiating loaders through delegation.
- The runtime identity of a non-array class/interface is the pair **(binary name, defining loader)**, and does not include the names of all initiating loaders.

| Question | Defining loader | Initiating loader |
| --- | --- | --- |
| Who actually defines the runtime type? | This loader itself. | Can be itself or another loader. |
| How many can one runtime type have? | One defining loader. | Possibly multiple initiating loaders. |
| Component of class identity? | **Yes**: combined with the binary name. | **No**: initiating alone does not create a new identity. |
| What does `Class.getClassLoader()` return? | The defining loader (or null for bootstrap). | Not an API for listing initiating loaders. |
| Can delegation make the two roles differ? | Yes. | Yes. |
| If two loaders only initiate the same class, are there two copies of the class? | No. | No. |
| If two loaders separately define the same binary name directly? | Creates two distinct runtime classes. | Each loader also initiates the class it defines. |

### 3.1 What does “defining a class” mean?

A class loader directly defines a class when the JVM creates a runtime representation from a binary representation associated with that loader. For custom Java loaders, this operation typically uses overloads of **ClassLoader.defineClass**.

~~~text
bytes for demo.Widget
         |
         v
ClassLoader L -- defineClass(...) --> JVM
                                      |
                                      v
                            runtime class demo.Widget
                            defining loader = L
                                      |
                                      v
                            java.lang.Class mirror
~~~

A class defined once by L cannot be silently replaced with a second class having the **same binary name and the same defining loader L** by calling defineClass again. Redefinition via instrumentation is a different mechanism and should not be equated with defining an additional separate class.

The defining loader not only affects type identity, but also participates in determining the **runtime package** (package name and defining loader), loading constraints, and rules that guarantee type safety.

### 3.2 “Initiating loading” does not mean “having executed the static block”

The term **initiating loader** refers to **loading**, not **class initialization**. A call to **loadClass** typically does not run the static initializer yet.

Three distinct steps:

~~~text
LOADING
  find/define type; determine initiating and defining loaders
       |
       v
LINKING
  verification, preparation, resolution according to JVM rules
       |
       v
INITIALIZATION
  execute static logic upon active use and corresponding triggers
~~~

The word “initiating” in the name initiating loader **does not mean** “the loader that initializes static fields”. This is a common confusion because the two words *initiate* and *initialize* look similar in meaning.

## 4. How does a Java ClassLoader typically delegate?

With the default implementation of **ClassLoader.loadClass(name, resolve)**, the process typically consists of:

1. **findLoadedClass(name)** checks whether the JVM has already recorded the corresponding class for the current loader.
2. If not, try **parent.loadClass(name)**, or bootstrap depending on the loader's condition.
3. If the parent cannot find it, call **findClass(name)** implemented by the current loader.
4. If needed, perform **resolveClass** and then return the `Class` object.

Pseudocode illustrating the idea:

~~~java
// Illustrative pseudocode, not verbatim JDK source code
Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
    Class<?> clazz = findLoadedClass(name);

    if (clazz == null) {
        try {
            clazz = delegateToParentOrBootstrap(name);
        } catch (ClassNotFoundException ignored) {
            clazz = findClass(name);
        }
    }

    if (resolve) {
        resolveClass(clazz);
    }

    return clazz;
}
~~~

This is the **common parent-first mechanism**, not a rule that every custom ClassLoader must follow. Plugin containers, application servers, or hand-written loaders may alter the class lookup policy (while still needing to satisfy JVM constraints).

### 4.1 Why does a class have multiple initiating loaders?

Suppose **Loader A** and **Loader C** are two different child loaders that both delegate to **Loader B**:

~~~text
      Loader A                 Loader C
    (requester)              (requester)
        |                        |
        +-----------+------------+
                    |
                    v
                Loader B
           defines demo.Shared
                    |
                    v
        ONE single java.lang.Class
              for demo.Shared
~~~

If JVM loading records A and C as appropriate initiating loaders, there is still **only one class** because the defining loader is B.

What needs to be checked is **which loader owns the final definition of the class**. Creating multiple ClassLoader objects does not automatically duplicate classes defined by the parent.

## 5. Java 17+ example #1: child loader initiates, parent defines

Create the file **DelegationRolesDemo.java** with a nested class and a child loader:

~~~java
public class DelegationRolesDemo {
    static class Shared {
        static {
            System.out.println("Shared initialized");
        }
    }

    static class ChildLoader extends ClassLoader {
        int ownFindClassCalls;

        ChildLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            ownFindClassCalls++;
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader = DelegationRolesDemo.class.getClassLoader();
        ChildLoader child = new ChildLoader(appLoader);

        Class<?> first = child.loadClass(Shared.class.getName());
        System.out.println("same Class = " + (first == Shared.class));
        System.out.println("child defines = "
                + (first.getClassLoader() == child));
        System.out.println("app defines = "
                + (first.getClassLoader() == appLoader));
        System.out.println("child findClass calls = "
                + child.ownFindClassCalls);

        Class<?> again = child.loadClass(Shared.class.getName());
        System.out.println("same repeated result = " + (first == again));

        System.out.println("before active use");
        new Shared();
    }
}
~~~

Compile and run:

~~~bash
javac DelegationRolesDemo.java
java DelegationRolesDemo
~~~

Stdout:

~~~text
same Class = true
child defines = false
app defines = true
child findClass calls = 0
same repeated result = true
before active use
Shared initialized
~~~

### Result analysis

**child.loadClass(...)** receives the first request but uses parent-first; the application loader can already find the nested class `DelegationRolesDemo$Shared`, so **ChildLoader.findClass** is not called.

**first == Shared.class** is true because both are **the same runtime class**, defined by the application loader.

**first.getClassLoader() == child** is false; **first.getClassLoader() == appLoader** is true. This is direct evidence confirming the defining loader, regardless of which child loader was asked to load it.

Calling **child.loadClass(...)** again returns the same `Class`; the program does not define a separate copy of Shared.

The line **Shared initialized** only appears when **new Shared()** creates active use. The earlier **loadClass** calls do not initialize Shared on their own.

**Practical check:** if a class is defined by the bootstrap loader such as **java.lang.String**, **String.class.getClassLoader()** returns **null** in Java. Null represents the bootstrap loader; it does not mean the type “has no defining loader”.

## 6. Java 17+ example #2: two defining loaders create two different types

The previous example showed that multiple delegating loaders still receive **one** class. Now consider the case where two loaders actually define the same binary name themselves from the same bytecode file.

Create the structure:

~~~text
project/
├── IsolationDemo.java
└── src/
    └── sample/
        └── Payload.java
~~~

**src/sample/Payload.java**:

~~~java
package sample;

public class Payload {
    public Payload() {
    }

    public String message() {
        return "hello";
    }
}
~~~

**IsolationDemo.java**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IsolationDemo {
    public static void main(String[] args) throws Exception {
        URL classes = Path.of("out").toUri().toURL();

        try (URLClassLoader left = new URLClassLoader(
                     new URL[]{classes},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader right = new URLClassLoader(
                     new URL[]{classes},
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> a = left.loadClass("sample.Payload");
            Class<?> b = right.loadClass("sample.Payload");

            System.out.println("same name = "
                    + a.getName().equals(b.getName()));
            System.out.println("same Class = " + (a == b));
            System.out.println("left defines a = "
                    + (a.getClassLoader() == left));
            System.out.println("right defines b = "
                    + (b.getClassLoader() == right));

            Object fromRight = b.getDeclaredConstructor().newInstance();
            try {
                a.cast(fromRight);
                System.out.println("cast succeeded");
            } catch (ClassCastException expected) {
                System.out.println("cross-loader cast = ClassCastException");
            }
        }
    }
}
~~~

From inside the **project** directory, run:

~~~bash
javac -d out src/sample/Payload.java IsolationDemo.java
java -cp out IsolationDemo
~~~

Stdout:

~~~text
same name = true
same Class = false
left defines a = true
right defines b = true
cross-loader cast = ClassCastException
~~~

### Why do both loaders define Payload?

Here both **URLClassLoader** instances have the **platform class loader** as their parent. The platform loader in this example's run command does not look up the application class `sample.Payload` in the `out` directory, so each URLClassLoader finds the file at its own URL and defines the class itself.

Both **a** and **b** have the binary name `sample.Payload`, and the bytecode also comes from the same file, yet their **defining loaders are different**. Therefore:

~~~text
(sample.Payload, left)  !=  (sample.Payload, right)
~~~

Two objects of these classes are not automatically type-compatible. The operation **a.cast(fromRight)** throws ClassCastException, even though the class names look identical.

**Important condition to reproduce:** the parent of both URLClassLoader instances must **not be able to load sample.Payload**. If you replace the parent with the application loader (where `out` is on the classpath) and parent-first delegation succeeds, both may return the same Class defined by the application loader, yielding a different result.

You should not arbitrarily change the parent in the example and still expect two defining loaders.

## 7. Type identity: binary name + defining loader

For a regular runtime class/interface, the JVMS defines identity by the pair:

~~~text
(binary name, defining class loader)
~~~

Example:

~~~text
("com.example.Plugin", LoaderA) → Class A
("com.example.Plugin", LoaderB) → Class B
("com.example.Plugin", LoaderA) → still Class A if already defined
~~~

Two classes with the same binary name but different defining loaders are **two distinct types**. Conversely, two different initiating loaders that delegate to the same defining loader can use **the exact same Class**.

This affects:

- **Type casting** and the `instanceof` operator.
- **Method/field signatures** containing dependency class names.
- **Reflection** and `Class` comparisons.
- **Runtime package** and package-private access checks.
- **Plugin loading** when the host and plugin have separate copies of libraries.
- **Serialization, proxies, service loading**, and frameworks that use reflection when the classpath/classloader is split.

### 7.1 Comparing Class rather than just String names

~~~java
boolean sameName = first.getName().equals(second.getName());
boolean sameRuntimeType = first == second;
ClassLoader firstDefiner = first.getClassLoader();
ClassLoader secondDefiner = second.getClassLoader();
~~~

`sameName` being true **does not imply** `sameRuntimeType` is true.

If **getClassLoader()** returns null, the class is typically defined by the bootstrap loader; primitive Class mirrors also have a special representation. Do not infer that a class is broken merely because getClassLoader returns null.

### 7.2 Class loading and runtime packages

The JVM determines a class's runtime package by **package name + defining loader**. Therefore, two classes that both declare `package demo;` but are created by two different defining loaders can belong to **two different runtime packages** with respect to access checks.

Do not assume that having the same `package demo;` line in source code automatically grants package-private access between classes defined by independent loaders. In modular applications, modules and their corresponding access rules must also be considered.

## 8. One class name, multiple loaders, yet one Class: why delegation is useful

Delegation is commonly used to share common types and avoid incompatible duplicate class versions.

Imagine a host application with a shared interface:

~~~java
package api;

public interface Task {
    void execute();
}
~~~

Both the host and the plugin need **api.Task** to have **the same runtime definition** so that plugin objects can be used as the host's Task.

If each plugin loader defines its own copy of `api.Task`, having the same name and bytecode is not enough for a cast to the host's `api.Task` to succeed. That is why many plugin systems choose to have the shared API defined by a parent/shared loader, while child loaders define the plugin implementations.

~~~text
Shared API loader
   └─ defines api.Task
           ▲
           │ delegated
     +-----+-----+
     |           |
PluginLoader1  PluginLoader2
defines Impl1  defines Impl2

Impl1 / Impl2 both share the same Class api.Task
~~~

Real-world configuration also depends on dependency versions, package ownership, and child-first/parent-first policies. A useful architectural rule is to clearly determine **which APIs must share a single defining loader**, and which implementations are allowed to be isolated.

## 9. When is the initiating loader more than an “internal detail”?

The defining loader determines class identity; the initiating loader helps the JVM track class name resolution consistently across loaders that may delegate.

### 9.1 Consistency when reloading the same binary name

JLS §12.2.2 describes the property that well-behaved class loaders should guarantee: given the same name, a loader should return the same `Class` object. If a loader has previously initiated a class and is asked for the same name again, the JVM has a tracking mechanism to prevent arbitrary replacement with an inconsistent class.

That is why a loader cannot arbitrarily “return Class A today and Class B tomorrow” for the same request and context; the JVM enforces the necessary constraints to protect the type system.

### 9.2 Loading constraints

The JVM imposes **loading constraints** so that loaders have a compatible view of types appearing in method/field relationships and corresponding linkage points. For example, if two classes with different defining loaders participate in linking a method with a parameter of type `api.Message`, constraints can force both sides to agree on the identity of `api.Message`.

When loaders return different Class objects for a type that must agree, linking can fail with **LinkageError** (for example, a **loader constraint violation** message on a particular JVM).

Do not infer that every case where two loaders define the same binary name is immediately an error. The IsolationDemo example still manages to create two different classes. The error occurs when the JVM encounters **specific constraints** requiring them to be consistent.

### 9.3 Calling loadClass is not a complete introspection of initiating state

Java exposes **Class.getClassLoader()** to inspect the defining loader, but does not provide a general API on Class to list all initiating loaders ever involved.

**ClassLoader.findLoadedClass(name)** is a protected method that checks whether a class has been recorded by the JVM as initiated by that loader per the API contract; it should not be interpreted as a way to list every class that the loader directly defines.

Because loading paths and how the JVM records initiating loaders have specific specification details, use **loadClass results, the defining loader, and class identity** to verify examples; do not speculate about the entire internal state from a single API call alone.

## 10. Related APIs and what they tell us

| API | Appropriate usage | Should not be inferred |
| --- | --- | --- |
| `loader.loadClass(binaryName)` | Ask the loader to return the Class by name. | That the called loader is the defining loader. |
| `clazz.getClassLoader()` | Inspect the class's defining loader; null may mean bootstrap. | The list of initiating loaders. |
| `ClassLoader.getParent()` | Inspect the parent according to the API hierarchy. | That parent-first delegation always applies or that all classes are defined by the parent. |
| `findClass(name)` | Hook typically implemented by a custom loader to find/define a class when delegation fails. | That the JVM must by default call this hook for every loadClass. |
| `defineClass(...)` | Create a class from a binary representation with the defining loader. | That redefining the same class name in the same loader is allowed arbitrarily. |
| `findLoadedClass(name)` | Check whether a class is recorded as initiated by the loader when called inside a subclass. | That it only reflects classes directly defined by the loader. |
| `Class.forName(name, false, loader)` | Obtain a Class using the specified loader without triggering initialization. | That the loader argument is necessarily the defining loader. |
| `Class.forName(name)` | Find a class using the appropriate caller's loader and request initialization. | That it only performs loading without running the static initializer. |

In the examples, **Class.getName()** returns the binary name of a regular class, but is not sufficient to determine class identity. The most direct operation to compare two Class objects is **a == b**.

**Distinguishing a class's loader from the thread's context class loader:** `Thread.currentThread().getContextClassLoader()` is a context used by some frameworks/APIs to look up classes/services. It can be set to a different loader and does **not** define the claiming loader of any Class. Relying solely on the thread context loader can lead to wrong conclusions.

## 11. Observing loaders and classes at runtime

### 11.1 Observing with Java

At the point where you need to inspect a Class:

~~~java
Class<?> c = object.getClass();
System.out.println("name = " + c.getName());
System.out.println("defining loader = " + c.getClassLoader());
System.out.println("module = " + c.getModule());
System.out.println("same expected Class = " + (c == Expected.class));
~~~

The code above is an illustrative snippet to place inside a method where `object` and `Expected` are already available; it is not a standalone class. The `getModule()` information is useful when modules and classloaders interact.

Some classes defined by the bootstrap loader return null from getClassLoader; do not call methods on that value without a null check.

### 11.2 Observing class loading on JVMs that support Unified Logging

On modern HotSpot / JDK, you can enable logging:

~~~bash
java -Xlog:class+load=info DelegationRolesDemo
~~~

The number of lines and log format depend on the JDK/JVM. To view supported tags:

~~~bash
java -Xlog:help
~~~

The loading log can indicate the class source; it is not an absolute mechanism to infer the initiating loader list, nor does it prove that the static initializer has run. When you need to prove static initialization, create an example with a static block that prints a controlled message as in section 5.

### 11.3 Reading class files to check the binary name

If you suspect a class in a JAR has the wrong package/name, use:

~~~bash
javap -verbose -classpath out sample.Payload
jar --list --file example.jar
~~~

`javap` inspects the class file/constant pool; `jar --list` checks archive entries. These two commands **do not tell you which runtime loader defined the class** in the running application. Finding `sample/Payload.class` does not guarantee that the JVM used those exact bytes, because another loader could have found a different definition.

## 12. Error scenarios: when should you inspect the defining loader?

### 12.1 ClassCastException even though both names are identical

For example, the exception shows two classes both named `com.example.Dto`. Before assuming the JVM performed the cast incorrectly, check **a.getClassLoader()** and **b.getClassLoader()**. If the defining loaders are different, these are two runtime types; you need to clarify where the shared API is defined and the delegation policy of the plugins.

Usually, you should ensure that DTOs/interfaces used for communication are defined by a shared loader, while plugin-specific code can be isolated in child loaders.

### 12.2 NoClassDefFoundError or ClassNotFoundException

If a custom loader asks its parent to find a class, the parent does not find it, and the child cannot find it either, **ClassNotFoundException** can be thrown by the loadClass API. When the JVM requires a type for resolution, the corresponding loading failure can manifest as **NoClassDefFoundError**.

Check the binary name, artifact source, classpath/module path, parent loader, findClass logic, and root cause in the stack trace. Do not immediately assume that the loader in the exception is the defining loader, because defining the class may not have succeeded.

### 12.3 LinkageError: loader constraint violation

If an interface/class needs to be shared across a loader boundary, yet both sides return incompatible versions of the type in method signatures, the JVM can report a constraint error. You need to compare the module configuration, library versions, API types passed across the boundary, and which loader defines each type.

“Classes having the same name” is only a clue; **different loaders are not necessarily always wrong**. In plugin isolation, that may be intentional by design. The error occurs when a boundary requires sharing a type without agreeing on class identity.

### 12.4 Created a child loader, yet the class still uses the old implementation

If a child loader is parent-first and the parent has already defined the class, child.loadClass may return the parent's Class without calling child.findClass. Therefore, placing a new version of the class in the child's URL **does not guarantee** it will be used.

It may be necessary to explicitly adjust **parent visibility/delegation rules** for packages allowed to be isolated. Avoid switching to child-first indiscriminately, especially for JDK classes, shared APIs, or packages where the VM requires a unified definition.

## 13. Special cases to know

### 13.1 Array classes

The JVM creates an array class directly, not by looking up a `[Lsample/Payload;.class` file from the classpath. For an array whose component is a reference type, the defining loader of the array class is tied to the defining loader of the component type according to JVMS rules. For a primitive-array class, the JVM applies the bootstrap rule.

Therefore, when comparing `Payload[].class` from two Payload definitions with different loaders, the array runtime types also differ. These are not two array class files read by two loaders.

### 13.2 Primitive types and void

`Class` mirrors such as `int.class` and `void.class` do not correspond to an ordinary class file on the classpath. Do not interpret a primitive's getClassLoader as a custom loader reading bytes for `int.class`.

### 13.3 Modules and custom loaders

The Java Platform Module System affects where a class is located, accessibility, and module membership. `clazz.getModule()` provides useful context alongside the defining loader. However, **the module name does not replace the defining loader in the class identity pair**; a module is an additional dimension for organization/accessibility.

### 13.4 Class unloading

A class definition is tied to its defining loader. Whether a class can be unloaded depends on live references holding the class, the loader, and other JVM conditions. Do not infer that a class is unloaded merely because an initiating loader object is no longer used. This relates to GC/class lifecycle and should be analyzed using real measurement tools when needed.

## 14. Misconceptions to avoid

- **“Any loader that calls loadClass is the defining loader.”** False: a loader can delegate.
- **“Multiple initiating loaders mean multiple copies of Class.”** False: multiple loaders can receive the same Class from a single defining loader.
- **“getClassLoader() tells you the initiating loader.”** False: it returns the defining loader or null for bootstrap.
- **“The parent loader is always used first.”** True for many default implementations, though custom loaders can change delegation.
- **“If class names are the same, they can be cast.”** False when the defining loaders are different.
- **“Same bytes means the same runtime type.”** False; the defining loader and binary name must also match.
- **“Calling loadClass initializes all static fields.”** False; loading and initialization are different.
- **“All intermediate loaders in a Java call stack are always recorded by the JVM as initiating.”** Cannot be inferred; refer to the JVMS on JVM-initiated loading and delegation.
- **“An API field/method shared by two plugins is automatically compatible because they are in the same package.”** False if shared types are defined separately and violate class identity/loading constraints.

## 15. Self-check questions

**Question 1.** Loader A receives a request and delegates to B, which defines `pkg.Service`. Is `Service.class.getClassLoader()` A or B?

**Answer:** B, the defining loader. A may act as an initiating loader when the JVM requests loading through delegation.

**Question 2.** Loaders A and C both delegate to B for `pkg.Service`. Must there be two different Class objects?

**Answer:** No. They can both receive the same Class object defined by B.

**Question 3.** Loaders A and C each directly define `pkg.Service` using the same bytes. Are the two Class objects equal?

**Answer:** No, because their defining loaders differ. Class identity consists of the binary name and the defining loader.

**Question 4.** Why might calling `child.loadClass(...)` never execute `child.findClass(...)`?

**Answer:** The default implementation uses parent-first delegation. If the parent finds the Class, the child returns that result immediately.

**Question 5.** Does `findLoadedClass` only find classes directly defined by that loader?

**Answer:** No; the API contract is based on classes for which the JVM has recorded the loader as an initiating loader, which can include classes returned through delegation.

**Question 6.** Once loadClass has been called successfully, is the class's static initializer guaranteed to have run?

**Answer:** Not yet. Initialization normally waits for a separate active use; the single-argument `Class.forName(name)` has a different initialization rule.

**Question 7.** Why do two plugins need to share the same Class object for a communication interface?

**Answer:** If each plugin defines the interface separately, the runtime type identities differ, leading to cast or linkage errors when the API boundary requires consistent types.

**Question 8.** Does `String.class.getClassLoader()` returning null mean String has no defining loader?

**Answer:** No. Null represents the bootstrap loader according to the Class API contract in this case.

## 16. Knowledge summary

To debug classloader issues, separate three steps:

~~~text
(1) Which loader does the JVM / program ask to find the class?
           |
           v
     initiating loader
           |
           | may delegate
           v
(2) Which loader actually defines the class?
           |
           v
      defining loader
           |
           v
(3) The runtime type is determined by:
    (binary name, defining loader)
~~~

The **defining loader** determines the identity of the runtime class; the **initiating loader** represents the role of initiating loading, possibly via delegation. If you remember only one practical rule: **`loader.loadClass(name)` does not prove that loader defined the class; inspect `Class.getClassLoader()` and compare the `Class` objects themselves.**

### References

- **JVMS Java SE 17 §5.3 – Creation and Loading:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS Java SE 17 §5.3.4 – Loading Constraints:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- **JLS Java SE 17 §12.2.2 – Class Loader Consistency:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2.2
- **ClassLoader API, Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Class API, Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
