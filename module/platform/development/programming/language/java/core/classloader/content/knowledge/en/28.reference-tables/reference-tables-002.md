# Table of Operations Triggering Class or Interface Initialization in Java

## 1. Distinguishing Between “Class Loaded” and “Class Initialized”

When analyzing Java ClassLoaders, the question **“has this class been loaded yet?”** is not synonymous with **“has the class's static initializer run yet?”**. The JVM has several distinct phases:

1. **Loading:** finding the binary representation, creating the runtime class/interface and the corresponding `Class<?>` object, with the defining ClassLoader determined.
2. **Linking:** verification, preparation, and resolution (the timing of resolution may vary depending on the JVM strategy).
3. **Initialization:** executing class/interface initialization code, specifically static field initializers and static initialization blocks (if any).

Example:

```java
class Sample {
    static {
        System.out.println("Sample initialized");
    }

    static int number = 123;
}
```

This is an **illustrative source snippet** without `main`. Obtaining `Sample.class` or the result of a `loadClass("Sample")` call does not mean the line `Sample initialized` has been printed yet. Conversely, when code actually reads `Sample.number` for the first time while the class is not yet initialized, the JVM must initialize `Sample` before returning the value.

In Java, “class initialization” has a very specific meaning. **Static initialization** of a class is neither “running the constructor” for each instance nor the process of the JVM loading bytecode from a file. This article focuses on **the table of which operations trigger initialization, which ones do not, and important exceptions regarding interfaces, superclasses, compile-time constants, and reflection**.

## 2. Core Rules per JLS 17 §12.4.1

JLS 17 states that a class or interface `T` needs to be initialized before the first occurrence of one of the applicable active initialization operations. The foundational categories are:

- **Creating an instance of class `T`**, for example `new T()`.
- **Invoking a static method declared by `T`**.
- **Assigning a static field declared by `T`**.
- **Reading a static field declared by `T` where that field is not a *constant variable*.**
- **Certain reflective operations** via `java.lang.Class` or `java.lang.reflect` according to the API contract.

When the JVM initializes a **class**, it also initializes its uninitialized **superclasses** and relevant **superinterfaces that declare default methods** according to JLS/JVMS rules. Conversely, when initializing an **interface**, that **does not automatically initialize all superinterfaces** of that interface.

The execution order of static field initializers and `static { ... }` in a class/interface follows their **order of appearance in source** and the language rules; each runtime class/interface has its initialization state managed separately by the JVM. A class that has been successfully initialized does not re-run `<clinit>` just because there is another `getstatic` or `new` call.

**Key takeaway:** the same operation may trigger initialization of **another class** without initializing the class that appears in the source expression. For example, `Sub.inheritedField` might actually be a field declared by `Parent`; in that case, **Parent** is the one initialized by the field access, while **Sub** is not automatically initialized by it.

## 3. Quick Reference Table: Operations and Initialization

The table below assumes the corresponding class/interface **has not been initialized beforehand**, there are no class file errors, and the class member being referenced is actually declared on the stated type. “Yes” means **that operation directly requires initialization** under Java semantics. “No” means **not solely because of that operation alone**, although loading/linking or initializing a related class may arise from another context.

| Operation | Which type is initialized? | Conclusion | Precise notes |
| --- | --- | --- | --- |
| `new T()` where `T` is a class | `T` along with required superclasses/default-method superinterfaces | **Yes** | Before an instance is successfully created, class `T` must be initialized |
| Calling `T.staticMethod()` declared by `T` | Class or interface `T` | **Yes** | Static method invocation is an active use |
| Assigning `T.staticField = ...` | Type **declaring the field** | **Yes** | For an assignable field; `putstatic` requires initialization |
| Reading `T.staticField` that is not a constant variable | Type **declaring the field** | **Yes** | `getstatic` for a non-constant field is an active use |
| Reading `T.CONST` which is a *constant variable* | Usually does not require initialization just to obtain the constant | **No** | The value may be placed into the caller's constant pool |
| Referencing `T.class` | `T` | **No** | A class literal may lead to loading/linking, not initialization |
| Creating an array `new T[n]` | Element class `T` | **No** | The array class can be created without initializing the component class yet |
| `x instanceof T` | `T` | **No** | A type check is not an active-use trigger for `T` |
| Casting `(T) x` | `T` | **No** | `checkcast` does not automatically run the static initializer of the target type |
| Declaring `T variable;` or assigning `T ref = null` | `T` | **No** | Merely using the type name in source does not cause `T` to initialize |
| Default `ClassLoader.loadClass("pkg.T")` | `T` | **No** | Loading a class does not mean initializing it; custom code may do otherwise |
| `Class.forName(name, false, loader)` | `T` | **No** | Finds/loads/links per the API, but does not require initialization |
| `Class.forName(name)` | `T` | **Yes** for ordinary classes/interfaces | The 1-parameter overload requires initialization |
| `Class.forName(name, true, loader)` | `T` | **Yes** | The boolean parameter selects initialization |
| `Class.forName(name, false, loader)` with an array class name | Component class | **No** | An array type does not require component initialization |
| `T.class.getName()` / `getClassLoader()` | `T` | **No** | Reading class metadata is not sufficient to trigger `<clinit>` |
| `T.class.getDeclaredMethod("run")` | `T` | **No** for the lookup operation | May load/resolve other metadata; does not invoke the method |
| `method.invoke(null)` for a static method belonging to `T` | `T` | **Yes** | Reflection invocation triggers initialization when needed |
| `field.get(null)` reading a static field belonging to `T` | `T` | **Yes** per the reflection API | Even when the field has a compile-time constant value in the experiment |
| `constructor.newInstance(...)` | Declaring class | **Yes** | Reflective instance creation |
| `MethodHandle.invokeExact(...)` for static method/field of `T` | `T` | **Yes** when actually performing the operation | Obtaining a handle does not mean invoking the handle |
| Only `lookup.findStatic(T.class, ...)` | `T` | **No** in the example | Not yet invoked; examine the specific API, do not conflate finding a handle with invoking it |
| `MethodHandles.Lookup.ensureInitialized(T.class)` | `T` | **Yes** | The API requires ensuring the class is initialized when permissions allow |
| `new ImplementsPlain()` with an interface without default methods | Interface `Plain` | **No** solely from initializing the implementing class | The implementing class is still initialized |
| `new ImplementsDefault()` with an interface declaring a default method | Superinterface `HasDefault` | **Yes** before the corresponding class per the rules | Important for static field initializers of the interface |
| Reading a non-constant static field in interface `I` | `I` | **Yes** | Accesses the owner interface; does not automatically initialize superinterfaces |
| Initializing `Sub` extends `Parent` | `Parent` | **Yes** if not yet initialized | Parent is initialized before Sub |
| Reading only `Sub.field` where the actual field is declared by Parent | `Parent`, not necessarily Sub | **Owner only** | The name `Sub` in the expression does not determine initialization |
| Creating lambda `() -> T.staticMethod()`, without invoking the lambda yet | `T` | **No because the body has not run yet** | Lambda linkage has its own specifics; if the body actually runs, active use occurs |
| `T` appearing only in a generic type/type token | `T` | **No** solely from type syntax | Depends on whether the runtime expression calls another triggering API |

The table is a **trigger** lookup tool, not an assertion that the class always remains in an uninitialized state up to that point: the JVM may have already initialized it due to other code, a dependent class, or a prior operation. Furthermore, in a custom loader environment, the `loadClass` method overridden by a framework itself might proactively call `Class.forName(..., true, ...)` or execute code with side effects; the table describes **the standard API contract**, and does not guarantee that a custom method performs no extra work.

## 4. Dedicated Table for Static Fields and Compile-Time Constants

A very common source of confusion is inferring from `static final` that a field “does not cause the class to initialize”. This is **not always true**. The concept in the JLS is a **constant variable**: a `final` variable of primitive type or `String`, initialized with a **constant expression**.

| Declaration | Constant variable? | Does reading via normal Java source cause the owner to initialize? |
| --- | --- | --- |
| `static final int A = 10;` | Yes | **No** solely from reading `A` |
| `static final String S = "Java";` | Yes | **No** solely from reading `S` |
| `static final long L = 1L + 2L;` | Yes | **No** when the expression is a compile-time constant |
| `static final int X = Integer.parseInt("7");` | No | **Yes** if the owner is not yet initialized |
| `static final String T = new String("Java");` | No | **Yes** |
| `static final Integer I = 7;` | No: wrapper reference is not a primitive/String | **Yes** |
| `static int count = 5;` | No | **Yes** |
| `static final Object O = new Object();` | No | **Yes** |
| `static final int[] NUMBERS = {1, 2};` | No: array reference | **Yes** |

Example:

```java
final class Settings {
    static {
        System.out.println("init=Settings");
    }

    static final int PORT = 8080;
    static final String HOST = "localhost";
    static final int DYNAMIC_PORT = Integer.parseInt("8080");
}
```

This is an **illustrative class** without main. `System.out.println(Settings.PORT)` and `Settings.HOST` can be replaced by the compiler with literals/constant pool entries, so they do **not** require `Settings` initialization. However, `Settings.DYNAMIC_PORT` is not a constant variable: reading it will require initializing Settings first.

**Watch out for JAR versioning:** if a client was compiled and inlined `Settings.PORT`, changing the PORT value in the JAR at runtime will not necessarily make the client show the new value. This is a binary compatibility characteristic of constant variables, not proof that the ClassLoader picked the wrong class.

**Watch out for reflection:** `Field.get(null)` reading a static field via reflection can trigger initialization even when the source declaration is a constant variable. Therefore, the rule “compile-time constants do not initialize” cannot be applied to every **access mechanism**; one must distinguish normal bytecode/expressions from reflection.

## 5. Complete Java 17 Example: Observing 21 Operations and Initialization State

The example below combines the cases into a single program, but each case uses **a separate untouched class/interface** whenever it is necessary to measure the initialization timing. This avoids a testing pitfall: if a class was already initialized on a previous line, a subsequent line cannot print `init=...` again even though that operation is itself an active use.

Save the code to the file **`InitActionsDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class InitActionsDemo {
    private static String trace(String message) {
        System.out.println(message);
        return message;
    }

    static final class Passive {
        static { trace("init=Passive"); }
        static final int CONST = 42;
        static int number = 7;
        static String echo() { return "ok"; }
    }
    static final class WriteTarget {
        static { trace("init=WriteTarget"); }
        static int number;
    }
    static final class Constructed {
        static { trace("init=Constructed"); }
        String value() { return "object"; }
    }
    static class Parent {
        static { trace("init=Parent"); }
    }
    static final class Child extends Parent {
        static { trace("init=Child"); }
        static String value = "child";
    }
    static class FieldOwner {
        static { trace("init=FieldOwner"); }
        static int inherited = 11;
    }
    static final class Derived extends FieldOwner {
        static { trace("init=Derived"); }
    }
    interface Plain {
        String MARK = trace("init=Plain");
    }
    static final class ImplementsPlain implements Plain {
        static { trace("init=ImplementsPlain"); }
    }
    interface HasDefault {
        String MARK = trace("init=HasDefault");
        default String value() { return "default"; }
    }
    static final class ImplementsDefault implements HasDefault {
        static { trace("init=ImplementsDefault"); }
    }
    interface Base {
        String MARK = trace("init=Base");
    }
    interface Extended extends Base {
        String MARK = trace("init=Extended");
    }
    static final class ForNameTarget {
        static { trace("init=ForNameTarget"); }
    }
    static final class MethodTarget {
        static { trace("init=MethodTarget"); }
        public static String run() { return "method"; }
    }
    static final class FieldTarget {
        static { trace("init=FieldTarget"); }
        public static final int VALUE = 99;
    }
    static final class HandleTarget {
        static { trace("init=HandleTarget"); }
        public static String run() { return "handle"; }
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("01 literal=" + Passive.class.getSimpleName());
        System.out.println("02 constant=" + Passive.CONST);
        System.out.println("03 array=" + (new Passive[2]).length);
        System.out.println("04 forNameFalse=" +
                (Class.forName(Passive.class.getName(), false,
                        InitActionsDemo.class.getClassLoader()) == Passive.class));
        System.out.println("05 getstatic=" + Passive.number);
        System.out.println("06 invokestatic=" + Passive.echo());
        WriteTarget.number = 9;
        System.out.println("07 putstatic=" + WriteTarget.number);
        System.out.println("08 new=" + new Constructed().value());
        System.out.println("09 subclass=" + Child.value);
        System.out.println("10 inherited=" + Derived.inherited);
        System.out.println("11 plainImplement=" + new ImplementsPlain().getClass().getSimpleName());
        System.out.println("12 plainField=" + Plain.MARK);
        System.out.println("13 defaultImplement=" + new ImplementsDefault().value());
        System.out.println("14 extendedField=" + Extended.MARK);
        Class<?> named = Class.forName(ForNameTarget.class.getName(), true,
                InitActionsDemo.class.getClassLoader());
        System.out.println("15 forNameTrue=" + named.getSimpleName());
        Method method = MethodTarget.class.getDeclaredMethod("run");
        System.out.println("16 reflectedMethodFound=" + (method != null));
        System.out.println("17 methodInvoke=" + method.invoke(null));
        Field field = FieldTarget.class.getDeclaredField("VALUE");
        System.out.println("18 fieldFound=" + (field != null));
        System.out.println("19 fieldGet=" + field.get(null));
        MethodHandle handle = MethodHandles.lookup().findStatic(
                HandleTarget.class, "run", MethodType.methodType(String.class));
        System.out.println("20 handleFound=" + (handle != null));
        System.out.println("21 handleInvoke=" + (String) handle.invokeExact());
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac --release 17 InitActionsDemo.java
java InitActionsDemo
```

No Maven, Gradle, external JAR files, or custom ClassLoader are needed. The code was compiled with `javac 21 --release 17` and tested on Java 21; the operations use Java 17-compatible APIs/syntax. **Actual stdout of the program:**

```text
01 literal=Passive
02 constant=42
03 array=2
04 forNameFalse=true
init=Passive
05 getstatic=7
06 invokestatic=ok
init=WriteTarget
07 putstatic=9
init=Constructed
08 new=object
init=Parent
init=Child
09 subclass=child
init=FieldOwner
10 inherited=11
init=ImplementsPlain
11 plainImplement=ImplementsPlain
init=Plain
12 plainField=init=Plain
init=HasDefault
init=ImplementsDefault
13 defaultImplement=default
init=Extended
14 extendedField=init=Extended
init=ForNameTarget
15 forNameTrue=ForNameTarget
16 reflectedMethodFound=true
init=MethodTarget
17 methodInvoke=method
18 fieldFound=true
init=FieldTarget
19 fieldGet=99
20 handleFound=true
init=HandleTarget
21 handleInvoke=handle
```

**Note on the line `12 plainField=init=Plain`:** the `trace("init=Plain")` method both prints the message and **returns that same string** as the value of the `MARK` field. Therefore, the output lines contain `init=Plain` twice with two different meanings: a standalone line reporting when the interface initialized and a string value printed after `plainField=`. The same applies to `Extended.MARK`. This is intentional output, not an accidental duplicate print or double interface initialization.

### 5.1. Analyzing the Group of Operations That Do Not Initialize Immediately

The first four lines relate to class `Passive`:

```text
01 literal=Passive
02 constant=42
03 array=2
04 forNameFalse=true
```

There is **no** `init=Passive` yet in these four lines, because:

- `Passive.class` obtains the `Class<?>` mirror without requiring `<clinit>` to run.
- `Passive.CONST` is the compile-time constant `42`, used without needing to read the runtime field via `getstatic`.
- `new Passive[2]` creates **an array holding Passive references**, without calling `new Passive()` for each element. The array slots are initially `null`.
- `Class.forName(name, false, loader)` requests loading/linking the appropriate class, but **does not actively perform initialization**.

Only at line 05 does this appear:

```text
init=Passive
05 getstatic=7
```

Reading `Passive.number` is an active use of a non-constant static field, so initialization occurs before the value `7` is printed. Line 06 invokes the static method `Passive.echo()`, but does not print `init=Passive` again because this class is already initialized.

### 5.2. Assigning a Static Field and Creating an Object

The lines:

```text
init=WriteTarget
07 putstatic=9
init=Constructed
08 new=object
```

show that:

- **Assigning** `WriteTarget.number = 9` requires initializing the class before the assignment completes, even though the field has not been read.
- `new Constructed()` requires initializing the class before instance creation. The `value()` method is called on the existing instance.

Do not confuse `new Constructed[5]` with `new Constructed()`: the first operation only creates an **array**, not five Constructed objects.

### 5.3. Superclass Before Subclass, Yet Which Owner Does a Static Field Belong To?

When accessing `Child.value`, class Child must be initialized, and the JVM ensures that superclass `Parent` is initialized first:

```text
init=Parent
init=Child
09 subclass=child
```

Conversely, when accessing `Derived.inherited`, the field is actually declared in `FieldOwner`. The result:

```text
init=FieldOwner
10 inherited=11
```

**There is no `init=Derived`.** This is proof that a subclass name appearing in a source expression does not automatically initialize the subclass if the member is a static field declared by a superclass. JLS §12.4.1 has an example of this exact case.

### 5.4. Interfaces Without Default Methods and Interfaces With Default Methods

Line 11:

```text
init=ImplementsPlain
11 plainImplement=ImplementsPlain
```

When initializing `ImplementsPlain`, interface `Plain` does not automatically initialize merely because the class implementing it initializes, because Plain **declares no default methods**. Only when code actually reads `Plain.MARK`, since MARK is a non-constant field, does `Plain` initialize:

```text
init=Plain
12 plainField=init=Plain
```

As for interface `HasDefault`, it declares `default String value()`. When class `ImplementsDefault` needs initialization, the JVM handles initializing the required superinterface with default methods **before** the class:

```text
init=HasDefault
init=ImplementsDefault
13 defaultImplement=default
```

One must not generalize that “all interfaces are initialized when a class implements them”. Only those superinterfaces falling into the category required by JLS/JVMS rules are initialized along with the class. A compiler may also occasionally generate **synthetic default methods** relevant to determining which interfaces need initialization; therefore, when analyzing transformed bytecode, examine the actual class/interface definitions.

### 5.5. An Interface Extending an Interface Does Not Automatically Initialize the Parent Interface

In the demo:

```java
interface Base {
    String MARK = trace("init=Base");
}
interface Extended extends Base {
    String MARK = trace("init=Extended");
}
```

When reading `Extended.MARK`, only interface **Extended** requires initialization for the field it declares:

```text
init=Extended
14 extendedField=init=Extended
```

**There is no `init=Base`.** Initializing an interface **does not automatically trigger initialization of its superinterfaces**. If `Base.MARK` is subsequently actually read, Base may be initialized at that point.

### 5.6. Reflection: Retrieving Metadata Is Not the Same as Invoking/Getting a Field

`Class.forName(..., true, ...)` actively initializes:

```text
init=ForNameTarget
15 forNameTrue=ForNameTarget
```

However, `MethodTarget.class.getDeclaredMethod("run")` only looks up metadata, so the line:

```text
16 reflectedMethodFound=true
```

appears without `init=MethodTarget` yet. When calling:

```java
method.invoke(null);
```

to execute the **static method** declared in MethodTarget, reflection triggers initialization first:

```text
init=MethodTarget
17 methodInvoke=method
```

Similarly, `getDeclaredField("VALUE")` does not automatically initialize, but `Field.get(null)` on a static field leads to:

```text
18 fieldFound=true
init=FieldTarget
19 fieldGet=99
```

Even though `VALUE` is `public static final int VALUE = 99` (a compile-time constant), a **reflective read** still has a different initialization contract from a Java source expression inlined by the compiler. This is a scenario frequently overlooked in brief reference tables.

### 5.7. MethodHandle: Distinguishing Finding a Handle from Invoking a Handle

`MethodHandles.lookup().findStatic(HandleTarget.class, "run", ...)` **retrieves the method handle**. The experiment has not printed `init=HandleTarget` at this step yet:

```text
20 handleFound=true
```

When calling `handle.invokeExact()`, the JVM actually performs the static invocation, requiring initialization:

```text
init=HandleTarget
21 handleInvoke=handle
```

**Do not equate all MethodHandles operations**: there are APIs for querying handles, APIs for ensuring initialization, and APIs for executing handles. These operations have different semantics. When explaining a specific call site, one should examine the invocation kind (static field getter/setter, static method, constructor), the target, and the execution timing, rather than concluding “seeing MethodHandle means immediate initialization”.

## 6. ClassLoader.loadClass, Class.forName, and Class Initialization

A core point regarding the ClassLoader topic:

```java
Class<?> loaded = loader.loadClass("pkg.Widget");
```

Under standard behavior, the `loadClass` API **loads/finds** the runtime class and may perform linking according to the relevant rules, but **does not automatically request initialization**. Whereas:

```java
Class<?> type = Class.forName("pkg.Widget", true, loader);
```

actively requests initialization of class `pkg.Widget`. If that class has not yet been initialized, the associated static code will be executed before the call completes normally.

Three usage patterns:

| API | Intent | Notes |
| --- | --- | --- |
| `loader.loadClass("pkg.Widget")` | Find/load via loader | Does not automatically initialize per standard contract; custom overrides may have side effects |
| `Class.forName("pkg.Widget", false, loader)` | Look up class via loader without initializing | Useful for scanners, inspecting metadata first |
| `Class.forName("pkg.Widget", true, loader)` | Look up and ensure initialization | May cause side effects from the static initializer |

With the overload:

```java
Class.forName("pkg.Widget");
```

Java uses the caller context to select the appropriate loader and **initializes the class** according to the contract. Do not assume this call always uses `Thread.currentThread().getContextClassLoader()`. To control the loader/initialization in a plugin system, use the three-parameter overload with an explicit loader.

### Why Does false Not Guarantee That “No Other Class Is Initialized”?

`initialize=false` only states that **the API does not request initialization of the requested class itself**. During loading/linking, the VM may load dependent classes or custom ClassLoader code may execute side effects. If the custom loader **itself calls** a static method on another class, that other class may be initialized. Therefore:

- Do not infer from `Class.forName(... false ...)` that “no initialization occurred anywhere in the JVM”.
- Do not take the constructor log of another object as proof that the target class initialized.
- When clean testing is needed, use a separate untouched class and log its own static initializer.
- Inspect the stack trace/cause when the API fails during linking or initialization; the two error categories are different.

### Parent Delegation Does Not Change Initialization Rules

A child loader may return a class defined by the parent. Having the child return that class **does not run `<clinit>` a second time**. Initialization is tied to the **actual runtime class** managed by the JVM, that is, the same binary name + defining loader. If two loaders **each define two different runtime classes** with the same binary name, they have separate initialization states and can be initialized at two different times.

## 7. Related Bytecode: new, getstatic, putstatic, invokestatic

When comparing source with bytecode, the instructions commonly associated with active use are:

| Instruction | Purpose | Can it require initialization? |
| --- | --- | --- |
| `new` | Create an instance of a class | **Yes** for the class being instantiated |
| `getstatic` | Read a static field | **Yes** for a non-constant variable field / when bytecode actually reads the field |
| `putstatic` | Assign a static field | **Yes** |
| `invokestatic` | Invoke a static method | **Yes** |
| `ldc` with a String/int literal | Load a constant from the constant pool | **No** automatically initializing the owner of the constant variable that appeared in source |
| `ldc` class literal | Obtain a Class mirror | **No** automatically initializing the represented class |
| `anewarray` / `multianewarray` | Create an array | **No** automatically initializing the component class solely due to array creation |
| `checkcast` / `instanceof` | Type check/cast | **No** automatically initializing the target class |
| `invokevirtual` for an instance method | Invoke an instance method | **No** automatic initialization in the same sense as static active use |
| `invokeinterface` for an instance method | Invoke an instance method via an interface | **No** solely from the instance call; the object already exists and the class is usually already initialized |

**Note on `getstatic` and constant variables:** the Java source expression `Settings.PORT` for a compile-time constant is typically **inlined** by the compiler, so the caller's bytecode may not contain `getstatic Settings.PORT`. When analyzing manually generated bytecode, one must not overlook the triggering semantics of an actually executed `getstatic` instruction simply because the field in the class file carries `final`. The JLS table describes normal access from Java source, while the JVMS describes triggering at the instruction level — distinguish these two levels to avoid false contradictions.

**How to inspect the example's bytecode yourself:**

```bash
javap -c -p InitActionsDemo
javap -c -p 'InitActionsDemo$Passive'
```

Both commands use single-quote syntax suitable for Linux/macOS/Git Bash. On Windows PowerShell, you can also quote the nested class name so that the `$` sign is not treated as a variable by the shell; `javap` should be run in the directory containing the `.class` files.

In the `javap -c` output, look for `ldc`/constants, `getstatic`, `putstatic`, and `invokestatic` in the corresponding sections. Do not infer initialization solely from the fact that **the constant pool references the class**: examine which instructions are actually executed and the JVM rules.

## 8. Initialization Order and Impact from Superclasses / Default Interfaces

When class `Child` is initialized, the JVM follows this procedure:

```text
Request to initialize Child
    |
    +-- Parent not yet initialized? -> initialize Parent
    |
    +-- superinterfaces declaring default methods
    |   not yet initialized? -> initialize in specified order
    |
    +-- Child runs static field initializers and static blocks
```

A class may inherit many interfaces indirectly. The exact order and set of interfaces needing initialization are specified in detail by JLS 12.4.2; one should not simply depict “all interfaces before all superclasses”. What matters in practice is:

- **A superclass must be initialized before its subclass**.
- When a class initializes, those **superinterfaces declaring default methods** within the specified scope must be initialized in sequence.
- A class implementing an interface **with only static fields/abstract methods** and no default methods is not required to initialize that interface merely because the implementing class initializes.
- Initializing an interface **does not automatically** initialize its superinterfaces.
- **Whichever type declares a static field is the exact type** initialized when reading a non-constant field, not the type used to write the expression.

These scenarios frequently appear in frameworks: an interface declares a static variable that creates a singleton/registry with side effects; code may trigger it when initializing an implementation **if the interface declares a default method**, even before the default method is called.

### Declaration Order of Static Fields and Static Blocks

```java
class Ordering {
    static int a = print("a", 1);
    static {
        System.out.println("static block");
    }
    static int b = print("b", 2);

    static int print(String name, int value) {
        System.out.println(name);
        return value;
    }
}
```

This is **illustrative** source. An active use of Ordering leads to the sequence:

```text
a
static block
b
```

Static fields **that are not constant variables** are initialized by executing expressions in source order. Do not confuse this with **preparation**, the runtime phase that assigns static fields their default values before initialization.

## 9. Concurrency Across Multiple Threads: Only One Successful Initialization

When two threads first touch the same runtime class:

```text
Thread T1                               Thread T2
   |                                       |
   +-- requests to initialize X            +-- requests to initialize X
   |                                       |
   +-- JVM marks X as initializing         +-- JVM waits for initialization of X
   |
   +-- runs static fields / <clinit>
   |
   +-- completes successfully
                                           +-- continues after X is initialized
```

JLS 12.4.2 specifies **synchronizing initialization per runtime class/interface**, with the states “uninitialized”, “being initialized”, “initialized”, and “erroneous”. If initialization of the same class is requested recursively by **the very thread currently performing initialization**, the JVM has rules for handling reentrant requests; it does not simply run `<clinit>` an infinite number of times.

Consequences:

- Successful static initialization of a class **occurs only once for that runtime definition**, not once per thread.
- Two different defining ClassLoaders defining the same binary name can lead to **two separate initializations**, because they are two distinct runtime classes.
- If a static initializer blocks forever or waits on a cyclic lock between threads, the program can hang; ClassLoader is not by itself a barrier that handles deadlocks.
- Do not rely on `System.out.println` in a static block always reflecting the entire ordering when multiple threads and multiple independent classes initialize in parallel; each class has its own ordering rules.

### When a Static Initializer Fails

A class whose static initializer throws an exception:

```java
class Broken {
    static final int X = fail();

    static int fail() {
        throw new IllegalStateException("boom");
    }
}
```

This is **illustrative** code. The first time an operation requiring initialization of Broken is performed (for example, accessing `Broken.X`), it can typically result in an `ExceptionInInitializerError` wrapping the non-Error exception. The class is marked **erroneous** per the JLS procedure, and subsequent initialization requests may receive a `NoClassDefFoundError` associated with the erroneous state.

Inspect the **cause and the first failure**, rather than trying to fix it by repeatedly calling `Class.forName` on the same defining loader and expecting the static block to re-run. With a named class that is already erroneous, one typically must fix the bug and manage a new loader/class lifecycle to obtain an independent runtime definition if the architecture permits.

## 10. Reading Logs: A “Loaded” Class Does Not Mean “Initialized”

If unified logging is enabled on a suitable JDK:

```bash
java -Xlog:class+load=info -cp . InitActionsDemo
```

The JVM logs class loading events. This log is useful for seeing **which classes were loaded and from what source**, but it does not replace static initialization logging. A class can be loaded/linked by reflection or the verifier without having initialized yet. To observe initialization via logging, one must identify the supported tag/level on the JVM in use; do not automatically treat every `class+load` line as a `<clinit>` event.

In the example, the `init=...` lines printed by the static initializer or initializer expression themselves are clear proof that **the initialization code of that class/interface actually ran**.

### An Analysis Workflow When Output Is Unexpected

1. Identify the **runtime Class<?> and defining loader**, because the same class name in two loaders has two different initialization states.
2. Check whether the target class actually has a static initializer or a static field initializer with side effects. A class producing no output does not mean it has not been initialized.
3. Identify the **first active-use operation**: `new`, static method, non-constant static field, reflection, or Class.forName true.
4. Check **which** class/interface actually **declares** the field. Access through a subclass may initialize the superclass rather than the subclass.
5. Check whether the field is a constant variable; inspect the caller's bytecode to identify inlining.
6. If interfaces are involved, check default methods, synthetic defaults, and the initialization rules for superinterfaces.
7. Distinguish the behavior of `getDeclaredMethod` from `Method.invoke`, `findStatic` from `invokeExact`, and `forName false` from `forName true`.
8. If the class was already initialized before the experiment, create **another class** or start a fresh JVM; do not expect `<clinit>` to re-run automatically in the same runtime class.
9. If an error occurs, read `ExceptionInInitializerError`/`NoClassDefFoundError` and the original cause.
10. In a multi-classloader plugin setup, ensure you are not testing a Class object from the parent and attributing it as a definition of the child.

## 11. Common Misconceptions

| Misconception | Correction |
| --- | --- |
| “ClassLoader.loadClass means the static block has run.” | Loading is distinct from initialization. Check active use and `Class.forName` options. |
| “`T.class` definitely triggers `static {}`.” | A class literal does not require initialization. |
| “`static final` never initializes when read.” | Only a **constant variable** via source access normally does not initialize; reference values/runtime expressions differ. |
| “`new T[10]` creates ten instances of T.” | It creates an array of ten reference slots, typically null initially. |
| “If `getstatic` is in the bytecode, the field owner must be the type printed in source.” | The field's declaring type is what matters; source may use a subclass name to refer to a different field owner. |
| “Initializing a class always initializes every interface it implements.” | Only those superinterfaces with default methods according to the rules. |
| “Initializing an interface always initializes its parent interface.” | Not automatically. |
| “Reading `Sub.parentField` necessarily initializes Sub.” | It may only initialize Parent if the field is declared in Parent. |
| “`Class.forName(name, false, loader)` does nothing.” | It can load/link the class without actively initializing the target. |
| “`Class.forName(name)` is identical to `loader.loadClass(name)`.” | The `forName` overload has different initialization behavior. |
| “Obtaining a Field/Method via reflection means executing the owner's code.” | Metadata lookup is distinct from runtime invoke/get/set. |
| “Reading a constant via Field.get cannot initialize.” | Reflection has its own initialization contract; the demo shows `Field.get` initializes the owner. |
| “Obtaining a static MethodHandle immediately runs the class initializer.” | Finding a handle and invoking a handle are two different actions; inspect the API/call site. |
| “The static initializer runs every time a new object is created.” | Only once upon successful initialization for a runtime class, not per instance. |
| “The same class name in two loaders will share static state.” | Two defining loaders create two separate runtime classes/statics. |
| “Once the JVM finishes compiling/linking, all static blocks of dependencies have run.” | Linking and initialization have different rules/timing. |
| “ExceptionInInitializerError can be fixed by calling loadClass again.” | A class in the erroneous state has subsequent error rules; find the initialization cause. |

## 12. Self-Check Questions

**Question 1.** `Sample.class` is obtained, yet no static class action has occurred. Has `<clinit>` definitely run?

**Answer:** No. A class literal is not an initialization trigger.

**Question 2.** `static final int X = 123;` and `static final Integer Y = 123;`. Does reading them via normal Java source have the same effect?

**Answer:** No. X is a constant variable if the expression is compile-time, and is typically inlined; Y is a wrapper reference that does not belong to the primitive/String types of a constant variable, so reading Y is an active use of the owner.

**Question 3.** How do `new Widget[3]` and `new Widget()` differ with respect to initialization?

**Answer:** Creating an array does not require Widget initialization; creating a Widget instance does.

**Question 4.** `Child inheritedField` is accessed via the name Child, though the field is declared by Parent. Which class is initialized by that operation?

**Answer:** Parent, if not yet initialized; Child does not automatically initialize solely from that field expression.

**Question 5.** Interface I declares no default methods. When initializing a class that implements I, is I required to initialize?

**Answer:** Not solely because the class implements it. However, reading I.nonConstantField or another active-use operation can initialize I.

**Question 6.** Interface J extends I, and a non-constant static field declared by J is read. Does I automatically initialize along with it?

**Answer:** No, initializing J does not automatically trigger initialization of I.

**Question 7.** How do `Class.forName(name, false, loader)` and `Class.forName(name, true, loader)` differ?

**Answer:** False does not require initializing the target; true requires initializing the target before completing normally.

**Question 8.** Why can reflective `Field.get(null)` on a `public static final int` initialize the owner even though normal source access does not?

**Answer:** Reflection invocation has semantics requiring class initialization before retrieving a static field via the API; whereas a source constant variable can be inlined by the compiler.

**Question 9.** If `getDeclaredMethod` returns a Method object without printing `init=Target`, yet `invoke(null)` prints it, is there a contradiction?

**Answer:** No. Looking up method metadata and executing the method are different.

**Question 10.** Why does `HasDefault` initialize before `ImplementsDefault` in the example?

**Answer:** Because the JVM initializes superinterfaces declaring default methods per the JLS before completing the initialization of the class.

**Question 11.** Two independent ClassLoaders define the same binary name T. Do the static initializers of T share state?

**Answer:** No. They are two runtime classes with two different defining loaders, each having its own initialization state.

**Question 12.** When Broken.<clinit> fails the first time, is the JVM guaranteed to try running it completely again next time?

**Answer:** No. The class may be in the erroneous state, and subsequent requests usually receive NoClassDefFoundError. One must analyze the first failure's cause.

## 13. Checklist When Building an Initialization Table for a Real Application

- [ ] Identify the **declaring** class/interface for the operation, not just the name used in source.
- [ ] Separate loading, linking, and initialization into three steps.
- [ ] Classify the trigger: new, invokestatic, putstatic, non-constant getstatic, reflection, MethodHandle invocation.
- [ ] Verify whether `static final` is truly a constant variable.
- [ ] Verify that class literal, array creation, cast, instanceof, and `forName(false)` are operations that do not automatically initialize the target.
- [ ] Check the parent class before the child class.
- [ ] For interfaces, check for default methods and superinterface relationships.
- [ ] Do not assume that interface initialization always triggers initialization of parent interfaces.
- [ ] Understand that reflection lookup is distinct from method/field invocation.
- [ ] Do not confuse static variable initialization with instance field/constructor initialization.
- [ ] If testing is needed, use a fresh JVM and uninitialized target classes.
- [ ] Compare static output with bytecode via `javap -c` when suspecting a constant was inlined.
- [ ] When using a custom ClassLoader, record both the binary name and the defining loader.
- [ ] Track initialization errors and the erroneous state rather than only catching `ClassNotFoundException`.
- [ ] Do not design large/hard-to-recover side effects in static initializers.
- [ ] Treat JLS 12.4.1 and 12.4.2 as the authoritative source when there is any dispute over initialization timing.

## 14. Conclusion and References

**Not every operation that “touches a class name” triggers initialization.** Java only initializes a class/interface when specific triggers occur or when there is a dependent initialization relationship under JVM rules. The clearest cases are `new T()`, static methods, assigning a static field, reading a non-constant static field, and certain reflection operations. Conversely, `T.class`, `new T[n]`, `Class.forName(..., false, ...)`, reading a compile-time constant, casting, and `instanceof` **do not automatically cause the target to be initialized**.

When inheritance is involved, dependency conditions become subtler: superclass before subclass; superinterfaces with default methods are considered when initializing a class; an interface initializing itself does not mean every superinterface also initializes. Finally, the initialization state belongs to **the runtime class defined by a defining loader**, not merely the class name on paper.

Official sources for reference:

- **JLS Java SE 17 §12.4.1 — When Initialization Occurs:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1
- **JLS Java SE 17 §12.4.2 — Detailed Initialization Procedure:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
- **JVMS Java SE 17 §5.5 — Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JLS Java SE 17 §4.12.4 — final Variables and Constant Variables:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4
- **Java SE 17 `Class` API, `forName`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 `Field` API, `get`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html
- **Java SE 17 `MethodHandles.Lookup` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
