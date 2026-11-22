# Compile-Time Constants, Class Literals, and Accessing Fields Declared in a Superclass

## 1. Core issue: mentioning a type does not necessarily initialize that type

When Java source writes **T.CONSTANT**, **T.class**, **Child.someField**, or **T.staticMethod()**, the type name appearing in the expression may look the same, but the **class initialization rules** are not the same. The JVM distinguishes **the class containing the referencing source code**, **the class that actually declares the member**, **whether the field is a constant variable or not**, and **whether the operation requires active use**.

Three phenomena to master:

1. **Compile-time constants:** A constant variable of primitive type or String, declared final and initialized with a constant expression, is usually compiled into a **constant value at the call site**. Reading this field **does not force the declaring class to undergo initialization**.
2. **Class literal:** The expression **SomeType.class** obtains the corresponding **Class<?>** without **automatically forcing the static initializer** of SomeType to run. Obtaining a Class object is different from calling **Class.forName(name)**, which requires initialization.
3. **Inherited static field:** If **Child.VALUE** actually references the field **VALUE declared in Parent**, then the initialization rule checks **Parent**, not automatically Child. The **Child** identifier in the source does not turn the field into a field declared by Child.

The goal of this lesson is to accurately predict **when a class is initialized, which static code runs, and which values are printed**, and then verify using **javap** and Java 17+. At the same time, you need to understand the impact on binary compatibility, JVM class loading, and reflection.

## 2. Positioning the problem in the JVM lifecycle

A typical class/interface has three related groups of work:

~~~text
Class bytes
    |
    v
LOADING
  - Find/read definition
  - Create runtime class and Class object
  - Attach defining class loader
    |
    v
LINKING
  - Verification: check structure and bytecode
  - Preparation: create static fields and default values
  - Resolution: resolve symbolic references when needed
    |
    v
INITIALIZATION when required
  - Ensure superclass and superinterfaces
    requiring initialization are processed
  - Execute ConstantValue rules and <clinit> code
  - Run static field initializers / static blocks
    |
    v
Class ready for active use
~~~

**Loading does not mean Initialization.** The fact that a representation of a class exists at runtime, that the class has been verified/prepared, or that a symbolic reference has been resolved **does not by itself prove that the class's static block has run**.

**Initialization** occurs under specific conditions in JLS §12.4.1 and JVMS §5.5. Merely having a line of Java mention a class name is not enough to decide.

### 2.1. Quick reference table

| Java Operation | Does it require initialization of T? |
| --- | --- |
| **new T()** | **Yes**, if T is a class and has not been initialized |
| **T.someStaticMethod()** when the method is actually declared in T | **Yes** |
| Writing **T.someStaticField = value** when the field is declared by T | **Yes** according to field usage rules |
| Reading **T.mutableOrRuntimeStaticField** declared by T | **Yes** if the field is not a constant variable |
| Reading **T.COMPILE_TIME_CONSTANT** | **No**, does not trigger initialization solely from reading a constant variable |
| **T.class** | **No**, does not trigger initialization of T solely from a class literal |
| **Class.forName("pkg.T")** | **Yes**, requires initialization via the single-parameter overload |
| **Class.forName("pkg.T", false, loader)** | **No**, does not require initialization, though it may still load/link |
| Typical **ClassLoader.loadClass("pkg.T")** | Does not automatically require initialization |
| **new T[10]** | Does not initialize component class T just from creating an array |
| **Child.inheritedStaticField** | Checks the class/interface that **actually declares the field**, not inferred from the word Child |

The table refers to the **target class**. An expression may cause **another class** to initialize, such as code in the receiver expression or an auxiliary static method being called. It is necessary to identify the complete operation if there are side effects.

## 3. What is a constant variable, precisely according to the JLS?

JLS §4.12.4 defines a **constant variable**: a **final** variable, of **primitive** or **String** type, **initialized with a constant expression** (JLS §15.29).

All three conditions are required:

1. **final:** the variable's value cannot be reassigned after valid initialization.
2. **Primitive or String type:** for example int, long, boolean, char, double, String; **does not** include Integer, Long, Object, List.
3. **The initializer is a constant expression:** an expression that the compiler can evaluate under compile-time semantics, for example **10 + 20**, **"Hello" + "!"**, **5 > 3**.

**static is not part of the general definition** of a constant variable. However, this lesson focuses on **static final fields** because class initialization rules directly relate to static field access. A local variable or instance final field can also satisfy the JLS definition of a constant variable in its context.

### 3.1. Examples of compile-time constants

~~~java
// Illustrative code declared in a Java class:
static final int MAX_USERS = 10 * 4;
static final long TIMEOUT = 2_000L + 500L;
static final String VERSION = "v" + "1";
static final boolean ENABLED = 3 < 5;
static final char LETTER = 'A';
static final double RATIO = 0.5;
~~~

Each field above has a primitive or String type, is final, and its initializer is a valid constant expression.

In particular, **VERSION** is a String constant expression despite having the **+** operator; the compiler can fold it into **"v1"** when compiling the client.

### 3.2. static final fields that are **not** constant variables

~~~java
// Illustrative code in a class:
static final Integer BOXED = 10;
static final int PARSED = Integer.parseInt("10");
static final String CREATED = new String("hello");
static final String SYSTEM_VALUE = System.getProperty("app.mode");
static final java.util.List<String> NAMES = java.util.List.of("a");
static final int COMPUTED = compute();

static int compute() {
    return 42;
}
~~~

Reasons:

| Field | Why is it not a constant variable? |
| --- | --- |
| **BOXED** | Type **Integer** is a reference wrapper, not a primitive or String |
| **PARSED** | Contains a method call **Integer.parseInt**, not a constant expression |
| **CREATED** | Contains **new String(...)**, not a constant expression |
| **SYSTEM_VALUE** | Value comes from a runtime system property |
| **NAMES** | Type List is not in the group of types allowed by the JLS for a constant variable |
| **COMPUTED** | Contains a method call **compute()**, even though the method always returns 42 |

Therefore, **final** does not mean "the compiler already knows the value"; **static final** also does not mean "reading it does not initialize the class." This distinction is central when observing the output of static blocks.

### 3.3. What can a constant expression contain?

Common forms according to JLS §15.29:

- Primitive literals, string literals, and text blocks where applicable.
- Unary operators **+**, **-**, **~**, **!**; excluding **++/--**.
- Arithmetic **+**, **-**, **\***, **/**, **%**; bit-shift operations and certain comparison operations.
- Logical/bitwise operators, **&&**, **||**, and the conditional operator **?:**.
- Valid casts and parenthesized expressions.
- Simple/qualified names referencing other **constant variables**.

Does not include method invocations, **new**, reading fields that are not constant variables, reading files, clocks, runtime properties, or computations depending on application state.

Example:

~~~java
// Illustrative code:
static final int BASE = 40;
static final int ANSWER = BASE + 2;     // constant variable
static final int DELAY = loadDelay();   // not a constant variable

static int loadDelay() {
    return 100;
}
~~~

**ANSWER** is computed from the constant variable **BASE** and literal 2, so it is a compile-time constant; **DELAY** depends on a method call.

## 4. Why does reading a compile-time constant not trigger <clinit>?

When a client compiles:

~~~java
int max = Config.MAX_USERS;
~~~

with **MAX_USERS** being a **static final int** constant variable, the Java compiler must use the constant value of the field at compile time according to binary form rules. The client's bytecode can use an instruction that pushes a constant such as **bipush/sipush/ldc** instead of **getstatic Config.MAX_USERS**.

If **getstatic** is not executed to read the field at runtime, that operation does not need to initialize Config just to obtain MAX_USERS.

Illustrative example:

~~~text
Java source:
    System.out.println(Settings.PORT);

With Settings.PORT as constant variable int = 8080:

Client bytecode conceptually:
    getstatic java/lang/System.out:Ljava/io/PrintStream;
    sipush 8080
    invokevirtual java/io/PrintStream.println:(I)V

Not needed:
    getstatic Settings.PORT:I
~~~

**This instruction sequence is illustrative**; the exact bytecode depends on the compiler. For the number 8080, **sipush** is an appropriate representation because 8080 is within the signed short range. The key point is that the client uses the **constant value** rather than being forced to read the static field at runtime.

**Note:** Do not infer that **Settings has not been loaded** just because the static block did not print a log. The JVM may have loaded/linked the class for another reason, without having performed initialization yet. "Not initialized" and "not loaded" are two different conclusions.

### 4.1. ConstantValue in the class file

Static final constant fields can carry a **ConstantValue attribute**. The JVMS specifies how ConstantValue values are assigned as part of class initialization, in a specified order. This is metadata so the runtime knows the value of the constant field **if/when the class is initialized**.

Distinguish two perspectives:

- **Client compile-time:** reading a constant variable in Java source can use the inlined value, without needing active use to initialize the declaring class.
- **Class runtime:** the class file has the field declaration and its ConstantValue information; when class initialization actually occurs, the VM ensures static constant fields have the correct values according to the specification.

Therefore, there is no contradiction when a client prints the value 8080 even though the static block in Settings has not run.

### 4.2. Constant values can be embedded into old clients

If library version 1 has:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 5;
}
~~~

A client compiled against version 1 can carry the constant **5** directly in its bytecode.

If the library is replaced with:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 7;
}
~~~

without **recompiling the client**, the old client may continue using **5**. When recompiling the client against the new version, it can use **7**. This is a **binary compatibility** risk when publishing public compile-time constants as configuration that changes across releases.

**Do not misdiagnose this as a classloader cache:** the new runtime class may be loaded properly while the client bytecode still contains the old number from compile time. If the value needs to change independently of the client artifact, use an appropriate runtime access API (for example a static method, external configuration, or a non-constant-variable field) and design compatibility clearly.

## 5. Runnable Java 17+ example: constant, class literal, and active use

Create the file **ConstantVsInitialization.java**:

~~~java
public class ConstantVsInitialization {
    static class Target {
        static final int PORT = 8080;
        static final String LABEL = "api" + "-v1";
        static final Integer BOXED = 12;
        static final int DYNAMIC = Integer.parseInt("21");

        static {
            System.out.println("Target:<clinit>");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("main:start");

        Class<?> type = Target.class;
        System.out.println("className=" + type.getSimpleName());

        Class.forName("ConstantVsInitialization$Target", false,
                ConstantVsInitialization.class.getClassLoader());

        System.out.println("port=" + Target.PORT);
        System.out.println("label=" + Target.LABEL);
        System.out.println("main:before-boxed");

        System.out.println("boxed=" + Target.BOXED);
        System.out.println("dynamic=" + Target.DYNAMIC);
        System.out.println("main:end");
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ConstantVsInitialization.java
java ConstantVsInitialization
~~~

**Exact stdout for a fresh run:**

~~~text
main:start
className=Target
port=8080
label=api-v1
main:before-boxed
Target:<clinit>
boxed=12
dynamic=21
main:end
~~~

Milestone-by-milestone analysis:

1. **Target.class** obtains Target's Class object and **getSimpleName()** retrieves the name; these two operations do not by themselves require initializing Target.
2. **Class.forName(...,false,loader)** does not require initialization, even though it may perform loading/linking.
3. **Target.PORT** and **Target.LABEL** are both constant variables. The client already knows their values, so they are not active uses that initialize Target.
4. Reading **Target.BOXED** is reading a static field that is **not a constant variable**. The JVM must initialize Target before returning the field; static initializers run in textual order and print **Target:<clinit>**.
5. Target.BOXED returns Integer 12; when concatenated into a string, the value is displayed as **12**.
6. DYNAMIC is computed during initialization, so it already has the value 21. Subsequent reads do not run the static block again.

The example intentionally places **Class.forName(false)** and the constant reads before the nonconstant read. If replaced with **Class.forName("ConstantVsInitialization$Target")** (the single-parameter overload), Target may initialize right at that forName call and the stdout order will differ.

## 6. Not all static final fields behave the same when read

Consider these cases:

| Declaration | Constant variable? | Does the first read require class initialization? |
| --- | --- | --- |
| **static final int A = 1;** | Yes | No, not just from reading A |
| **static final String B = "ab" + "c";** | Yes | No, not just from reading B |
| **static final boolean C = true;** | Yes | No, not just from reading C |
| **static final Integer D = 1;** | No | Yes |
| **static final int E = Math.abs(-1);** | No | Yes |
| **static final String F = new String("abc");** | No | Yes |
| **static int G = 1;** | No | Yes |
| **static final int H = Other.CONST;** where Other.CONST is a constant variable | Yes if the initializer is a valid constant expression | No, not just from reading H |
| **static final int I = Other.runtimeValue;** | No | Yes |

Use the JLS definition to reason, rather than guessing by the keyword **final** or solely based on whether the value "looks already known".

### 6.1. Compile-time constants are not a runtime configuration mechanism

If a program must read a value from the environment, system property, configuration file, or database, that is a runtime value. You should not write a public constant variable and expect swapping a JAR to make all clients immediately see the new value.

Design choices:

- Fixed value defined by an API/protocol and not expected to change: **public static final primitive/String constant** may be appropriate.
- Value that can change by environment: provide a method to read configuration or dependency injection, and define caching/reloading.
- Runtime value immutable after bootstrap: use **static final** computed at initialization (not a compile-time constant) or an immutable config instance, considering load/init timing and errors.
- Sensitive information: avoid hardcoding as a public compile-time constant because it can appear in client bytecode and analysis tools.

## 7. Class literal: T.class provides Class without calling <clinit>

In Java, a **class literal** is an expression such as:

~~~java
String.class
int.class
int[].class
java.util.List.class
SomeType.class
~~~

It returns the **Class<?>** representing the corresponding type; it is not an operation that creates an instance of that type.

Example:

~~~java
// Illustrative code inside a method:
Class<?> c = Heavy.class;
System.out.println(c.getName());
~~~

If Heavy has a static block that prints **"Heavy initialized"**, merely writing **Heavy.class** and calling **getName()** **does not force** that message to be printed.

Facts to distinguish:

- Having a **Class object** does not mean **the class has undergone initialization**.
- Creating/obtaining a Class object may involve loading/linking the type, but **does not trigger initialization solely due to a class literal**.
- **Class.getName()**, **getSimpleName()** to obtain the name are not equivalent to calling a static method of Heavy itself.
- **Class.forName(name)** has different behavior: the single-parameter overload requires initialization.
- **Class.forName(name,false,loader)** allows lookup without requiring initialization; use the exact binary name, for example nested member classes with **$**.

### 7.1. Class literals do not run constructors

Compare:

~~~java
Class<?> type = Widget.class;  // get type descriptor
Widget instance = new Widget(); // create instance, active use
~~~

**Widget.class** does not create a Widget object and does not call a constructor. **new Widget()** requires the Widget class to be initialized first, and then the JVM allocates the object and runs the constructor chain according to the rules.

Also distinguish:

~~~java
Widget[] array = new Widget[3];
~~~

The line above creates an array containing three references initially all null. It does not create three Widget instances and does not require initialization of Widget solely because the component type is Widget.

### 7.2. Primitive and array class literals

**int.class**, **boolean.class**, and **String[].class** all have corresponding Class objects; primitive/array types have their own class loading rules. For example, **int.class.getName()** returns **int**, **int[].class.getName()** returns **[I**, and **String[].class.getName()** returns **[Ljava.lang.String;**.

Do not assume there is a binary file **int.class** or **[I.class** on the classpath. Primitive and array runtime types are handled by the JVM through a special mechanism.

## 8. Three ways to obtain Class and initialization differences

| Approach | Requires initialization? | Notes |
| --- | --- | --- |
| **T.class** | Does not automatically require | Type is known at compile time |
| **Class.forName("pkg.T")** | Yes | Uses the overload called by name, requires initialization |
| **Class.forName("pkg.T", true, loader)** | Yes | Selects loader and requires init |
| **Class.forName("pkg.T", false, loader)** | No | Selects loader, does not require init |
| **loader.loadClass("pkg.T")** | Normally no | Default contract of loadClass(name) does not initialize |
| **obj.getClass()** | Does not automatically init a new type just from the Class object | The object already exists; the class was already initialized if creating the object required it |
| **T.class.getDeclaredFields()** | Does not necessarily init T | Reflection metadata inspection is not the same as Field.get/Field.set |

If using the Reflection API **Field.get(null)** to read a **static field**, Reflection's contract may **initialize the class declaring the field before retrieving the value**, even when the corresponding field in Java source is a compile-time constant. Therefore, do not mechanically apply the **source read of constant variable** rule to all reflective access.

### 8.1. API choices when writing frameworks

For a library that wants to **inspect metadata without executing static code yet**:

~~~java
// Illustrative code:
Class<?> cls = Class.forName(binaryName, false, loader);
var fields = cls.getDeclaredFields();
~~~

This is a common approach, but it can still have loading/linking effects and exceptions. Do not use it to promise "absolutely no code in the system is executed" — other related components may have already been initialized earlier or have their own activity.

When a framework needs to create an instance or trigger static initialization, it must clearly document the timing of active use so users understand side effects and dependency requirements.

## 9. Static fields declared in a superclass: the Child qualifier does not decide initialization

JLS §12.4.1 states clearly: a reference to a **static field** causes initialization only of **the class/interface that actually declares the field** according to the field's conditions, even though the syntax may use the name of a subclass, subinterface, or class implementing an interface.

Consider:

~~~java
class Parent {
    static int count = 10;
}

class Child extends Parent {
    static {
        System.out.println("Child initialized");
    }
}
~~~

When writing:

~~~java
System.out.println(Child.count);
~~~

**count** is declared in **Parent**, not Child. If not already initialized, the JVM must initialize Parent before reading the nonconstant static field. However, just because the source writes **Child.count**, it is **not required** to run Child's static initializer.

Compare the two rules:

- **Child.count**: resolves the actual field declaration as Parent.count → nonconstant static read → initialize Parent.
- **Child.ownCount** if the field is actually declared in Child: nonconstant static read → initialize Child, which entails initializing Parent beforehand if not already initialized.

**This is a rule based on the declaring type**, not a rule of "taking the class name closest to the dot."

### 9.1. When Parent's field is a compile-time constant

~~~java
class Parent {
    static final int LIMIT = 10;
}

class Child extends Parent {}
~~~

**Child.LIMIT** references **Parent.LIMIT**, a constant variable. Reading it **does not require initialization** of either Parent or Child from that operation alone. The compiler can embed literal 10 at the call site.

Thus there are two independent dimensions:

1. **Which is the declaring class?** — Parent.
2. **Is the field a constant variable?** — Yes or no.

Both must be answered, rather than applying a blanket rule like "a static field always initializes the class first."

### 9.2. What about field hiding?

~~~java
class Parent {
    static int value = 1;
}

class Child extends Parent {
    static int value = 2;
}
~~~

Here **Child.value** is a field actually **declared in Child**, not an inherited field. Therefore, reading **Child.value** is an active use of Child; the JVM must initialize superclass Parent before initializing Child.

Conversely, reading **Parent.value** only needs to initialize Parent. The same identifier **value** represents **two different fields**, which can have separate storage and lifecycles.

**Do not confuse field hiding with overriding:** static fields are not overridden via polymorphic dispatch like instance methods. The compiler resolves a field reference according to the appropriate type and declaration.

## 10. Runnable Java 17+ example: Parent field, Child field, compile-time constant

Create the file **InheritedStaticDemo.java**:

~~~java
public class InheritedStaticDemo {
    static class Parent {
        static final int LIMIT = 3;

        static int count = startCount();

        static int startCount() {
            System.out.println("Parent:<clinit>");
            return 10;
        }
    }

    static class Child extends Parent {
        static int own = initializeOwn();

        static int initializeOwn() {
            System.out.println("Child:<clinit>");
            return 20;
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("constant=" + Child.LIMIT);
        System.out.println("inherited=" + Child.count);
        System.out.println("after-parent");
        System.out.println("own=" + Child.own);
        System.out.println("end");
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 InheritedStaticDemo.java
java InheritedStaticDemo
~~~

**Exact stdout:**

~~~text
begin
constant=3
Parent:<clinit>
inherited=10
after-parent
Child:<clinit>
own=20
end
~~~

Line-by-line analysis:

1. **Child.LIMIT** is a constant field declared in Parent. The client uses the constant value 3; it does not require initializing Parent or Child.
2. **Child.count** is resolved by the compiler as **Parent.count**. This is a nonconstant static field; the JVM initializes Parent, calls startCount(), and prints **Parent:<clinit>**.
3. **Child** still does not need to be initialized after reading **Child.count**.
4. **Child.own** is a nonconstant static field declared in Child. The JVM initializes Child; Parent is already initialized, so it does not run again.
5. Parent and Child are two runtime classes with separate initialization states; the order of source qualifiers does not merge them into one.

Note that the program **only uses static field reads** for demonstration; there is no need to create a Child instance with **new Child()**.

## 11. A static field accessed through a subinterface

The rule "initialize the class/interface that declares the field" also applies to interfaces, but **interface initialization** is not like class inheritance: initialization of a subinterface **does not automatically** cause all superinterfaces to initialize.

Consider the standalone Java 17+ program **InterfaceFieldDemo.java**:

~~~java
public class InterfaceFieldDemo {
    interface Root {
        int CONST = 11;
        int RUNTIME = initRoot();

        static int initRoot() {
            System.out.println("Root:init");
            return 21;
        }
    }

    interface Branch extends Root {
        int OWN = initBranch();

        static int initBranch() {
            System.out.println("Branch:init");
            return 31;
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("constant=" + Branch.CONST);
        System.out.println("own=" + Branch.OWN);
        System.out.println("inherited=" + Branch.RUNTIME);
        System.out.println("end");
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 InterfaceFieldDemo.java
java InterfaceFieldDemo
~~~

**Stdout:**

~~~text
begin
constant=11
Branch:init
own=31
Root:init
inherited=21
end
~~~

Why was **Root:init** not printed before **Branch:init**?

- **Root.CONST** is a constant variable (interface fields are implicitly declared public static final). Reading **Branch.CONST** does not initialize Root.
- **Branch.OWN** is a field declared in Branch and computed by the static method **initBranch()**, not a constant variable. Reading it initializes Branch.
- **Initializing an interface does not automatically initialize its superinterfaces**; therefore, Root did not need to initialize at the time Branch.OWN was read.
- **Branch.RUNTIME** references a field actually declared in Root; the field is nonconstant → initialize Root at that point.
- There is no rule that "a subinterface always initializes its superinterface first" like superclass initialization of a class.

This is a clear example of the **declaring interface** rule and the difference between **class** inheritance and **interface** inheritance.

## 12. Static methods also check where they are actually declared

Active use rules also apply to static methods. For example:

~~~java
class Base {
    static void ping() {
        System.out.println("ping");
    }
}

class Derived extends Base {
    static {
        System.out.println("Derived:init");
    }
}
~~~

If a client method writes **Derived.ping()**, Java resolves the invocation according to the actual declaration of the method (here **Base.ping**). The static invocation operation requires initializing **Base**, not causing **Derived** to initialize just because the name Derived was used.

**However, static methods are not polymorphically overridden:** They can be hidden by a static method with the same signature in a subclass; in that case **Derived.ping()** may actually reference the method declared in Derived and trigger initialization of Derived.

Distinguish the cases:

| Expression | Actually selected member | Initialization involved |
| --- | --- | --- |
| **Derived.inherited** | Static field declared in Base | Base if nonconstant |
| **Derived.CONSTANT** | Constant variable declared in Base | No active use solely from reading the constant |
| **Derived.own** | Static field declared in Derived | Derived, then superclass if needed |
| **Derived.ping()** if ping is only in Base | Static method declared in Base | Base |
| **Derived.ping()** if Derived declares a method hiding Base.ping | Method declared in Derived | Derived |

When a method or field is hidden, you need to check which declaration the compiler bound the name to. You cannot conclude by looking at an isolated identifier.

## 13. Using javap to prove instead of just guessing from source

After creating the two examples above, run:

~~~bash
javap -c -p ConstantVsInitialization
javap -c -p InheritedStaticDemo
javap -v -p 'InheritedStaticDemo$Parent'
javap -v -p 'InheritedStaticDemo$Child'
~~~

**javap -c** prints bytecode, **javap -v** shows the constant pool, method descriptors, and attributes. Nested class names contain the **$** character; quote appropriately in shells with variable expansion.

### 13.1. How is a constant loaded?

When printing **Child.LIMIT**, the compiler may use an integer literal directly, such as:

~~~text
iconst_3
~~~

or fold the constant into an appropriate string concatenation. For a program calling **println("constant=" + Child.LIMIT)**, the Java 17 compiler may fold the entire concatenation into a single literal **"constant=3"**. What is worth observing is that **getstatic Parent.LIMIT is not needed** to fetch the value at runtime in a client compiled according to the JLS.

**Do not force the compiler to emit a specific opcode**, because with the same semantics there may be constant optimizations, **invokedynamic** for string concatenation, and other approaches depending on the version.

### 13.2. Which owner will a field declared in Parent have?

In the bytecode of **InheritedStaticDemo**, reading **Child.count** typically contains a symbolic reference to:

~~~text
getstatic InheritedStaticDemo$Parent.count:I
~~~

not **InheritedStaticDemo$Child.count:I**. The compiler identifies the actual field declaration as Parent. You can use **javap -c -p** to inspect the owner and **getstatic**.

When reading **Child.own**, the reference will point to **InheritedStaticDemo$Child.own:I**; active use of this field causes Child to initialize.

### 13.3. Class literals typically use ldc Class

For **Target.class**, the bytecode typically has an instruction like:

~~~text
ldc   #n      // class ConstantVsInitialization$Target
~~~

This is how to obtain the **Class object**, not **invokestatic Target.method** or **new Target**. The compiler may optimize local variable layout, but class literal semantics do not require static initialization of Target.

### 13.4. Why can't we rely entirely on stdout?

A class can be **loaded, verified, and prepared** before stdout shows a static initializer. Bytecode references can also be resolved by the JVM using an eager or lazy strategy. From **not seeing the log "Target:<clinit>"**, one should only conclude that **that logging code has not run yet**, not that all loading/linking states have not occurred.

## 14. Class literal of a superclass or subclass: a comparative example

Create **ClassLiteralDemo.java**:

~~~java
public class ClassLiteralDemo {
    static class Parent {
        static {
            System.out.println("Parent initialized");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("begin");

        System.out.println("name=" + Child.class.getSimpleName());
        System.out.println("parent=" + Child.class.getSuperclass().getSimpleName());
        System.out.println("after-literals");

        Class.forName("ClassLiteralDemo$Child", true,
                ClassLiteralDemo.class.getClassLoader());
        System.out.println("after-forName");
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 ClassLiteralDemo.java
java ClassLiteralDemo
~~~

**Stdout:**

~~~text
begin
name=Child
parent=Parent
after-literals
Parent initialized
Child initialized
after-forName
~~~

**getSuperclass()** retrieves metadata about Parent but does not need to run Parent's static initializer just from querying the superclass. **Class.forName(...,true,loader)** afterward is an active request to initialize Child, which entails initializing Parent before Child according to class hierarchy rules.

Notable point: **Child.class** does not initialize Child; **Child.class.getSuperclass()** does not cause Parent to initialize; but **forName(true)** on Child requires both classes in the order Parent → Child if not yet initialized.

### 14.1. Does a static nested class depend on initializing the outer class?

~~~java
class Outer {
    static { System.out.println("Outer initialized"); }

    static class Nested {
        static { System.out.println("Nested initialized"); }
    }
}
~~~

**Outer.Nested.class** does not initialize Nested; an active use **new Outer.Nested()** initializes Nested according to the rules of that runtime class itself. A static nested class **does not automatically initialize Outer** just because it is declared inside Outer in the source. A nested naming relationship is different from a superclass relationship.

## 15. Compile-time inlining and binary compatibility

Consider the application build process:

~~~text
Build 1:
  LibraryConfig.LIMIT = 5
  javac LibraryConfig.java Client.java
  Client.class may contain literal 5

Deploy 2:
  Only replace LibraryConfig.class (LIMIT = 7)
  Do not recompile Client.class

Runtime:
  Old Client.class may still print 5
~~~

These steps describe a build/deploy scenario, not a self-contained runnable terminal script. When the client's class file has already stored the constant value substituted at compile time, the runtime **does not need to query LibraryConfig.LIMIT**.

### 15.1. Example with two versions of a library class

Version 1, file **LibraryConfig.java**:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 5;
}
~~~

Client file:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println("limit=" + LibraryConfig.LIMIT);
    }
}
~~~

Compile both with Java 17:

~~~bash
javac --release 17 -encoding UTF-8 LibraryConfig.java Client.java
java Client
~~~

**Stdout of the first version:**

~~~text
limit=5
~~~

Then replace **LibraryConfig.java** with:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 7;
}
~~~

**Recompile only the library**, without compiling Client:

~~~bash
javac --release 17 -encoding UTF-8 LibraryConfig.java
java Client
~~~

**Stdout may still be:**

~~~text
limit=5
~~~

Finally, recompile Client with the new version:

~~~bash
javac --release 17 -encoding UTF-8 Client.java
java Client
~~~

**Stdout after recompiling the client:**

~~~text
limit=7
~~~

These execution steps assume running in the same directory containing the exact files and without another **LibraryConfig.class** earlier on the classpath. This is a classic example of why changing public compile-time constants can cause surprises even when the library JAR has been replaced.

### 15.2. Does replacing a constant with a method solve everything?

A method such as **LibraryConfig.limit()** called at runtime can avoid having the client embed the constant value, but you must consider:

- Replacing a field with a method is a **binary API change**: old clients accessing the field may become incompatible and need to be rebuilt.
- A runtime method still has its own versioning, class loader identity, and config caching concerns.
- If the value is read from config, you need to define when reloading, validation, and error handling occur.
- For a constant representing a fixed protocol meaning, inlining may be a desirable property.

The reasonable solution depends on the **value-change contract**, not simply a rule of "always use a method."

## 16. Constants in interfaces and inheritance

Interface fields are **public static final** by default, but the initializer can be a runtime expression; therefore, not every field in an interface is a constant variable.

~~~java
interface Options {
    int PORT = 8080;                    // constant variable
    int REAL_PORT = readPort();          // not a constant variable

    static int readPort() {
        return 9090;
    }
}
~~~

Reading **Options.PORT** does not initialize Options from that operation alone. Reading **Options.REAL_PORT** requires initializing Options if not already initialized.

When a subinterface inherits fields:

~~~java
interface ParentInterface {
    int LIMIT = 10;
    int DYNAMIC = calculate();

    static int calculate() { return 20; }
}

interface ChildInterface extends ParentInterface {
    int OWN = 30;
}
~~~

**ChildInterface.LIMIT** and **ChildInterface.DYNAMIC** both refer to actual declarations in ParentInterface. LIMIT is a constant variable; DYNAMIC is not constant, so reading it initializes ParentInterface, **without being required to initialize ChildInterface** solely because the syntax uses ChildInterface.

Conversely, reading a nonconstant field declared by ChildInterface itself initializes ChildInterface; interface initialization does not automatically trigger all superinterfaces like class superclass initialization does.

## 17. Some advanced, easily confused scenarios

### 17.1. Field hiding changes the declaring type

~~~java
class Parent {
    static final int CODE = 1;
}

class Child extends Parent {
    static final int CODE = 2;
}
~~~

**Child.CODE** references **Child.CODE**, not Parent.CODE. Both are still constant variables, so source reads do not automatically initialize the respective classes.

If **Child.CODE** is changed to **static int CODE = 2;**, reading **Child.CODE** is an active use of Child, triggering superclass initialization if needed. **Having the same field name** is not what decides; **declaration and constant-variable status** are what decide.

### 17.2. Static field access through an expression with side effects

In Java, a static field can be accessed using an expression that is a reference name:

~~~java
// Illustrative code, assuming Base.number is static int:
Base ref = null;
int value = ref.number;
~~~

Even though ref is null, reading a **static field** does not dereference ref like an instance field, so it does not throw NullPointerException solely because ref is null. Static field access still checks the declaring class, not the object reference value.

When the qualifier is an **expression with side effects**, Java may have to evaluate the expression according to language rules and then discard its value before performing the field operation. Therefore, to analyze **all stdout and exceptions**, you must consider the qualifier expression as well, not just the initialization of the declaring class.

**Recommendation:** Always write **Base.number** instead of **ref.number** for static fields to avoid confusion.

### 17.3. Class literals and reflection are not completely equivalent

**T.class** does not initialize T. However, reflection operations such as **Field.get(null)** and **Field.set(null, value)** for a static field may require initializing the declaring class according to the API. Thus:

~~~java
// Illustration in a method with throws Exception:
Class<?> type = T.class;                  // does not require initializing T
var field = type.getDeclaredField("X");   // inspect metadata
Object value = field.get(null);           // may initialize the declaring class
~~~

The code above is not standalone because **T** must be declared and **X** must exist and be accessible. Calling getDeclaredField/getDeclaredFields may involve loading/linking metadata; it must not be turned into a blanket promise that "reflection does not initialize."

### 17.4. Reading a constant variable in the declaring class itself

If a class has:

~~~java
static final int CONSTANT = 8;
static int VALUE = CONSTANT * 2;
~~~

**VALUE** is initialized during initialization, while the compiler can use the constant expression **16** for the initializer. This does not mean the class never initializes: reading **VALUE** from outside is still a nonconstant static field access and requires class initialization.

If a class only declares compile-time constants, the compiler may not generate a **<clinit>** containing instructions. Even so, Java still defines the class lifecycle; the absence of <clinit> output does not allow concluding that "this type has no initialization step at all in the JVM model."

### 17.5. Class loaders and two runtime copies

Two different class loaders can define two classes with the same binary name. Each runtime class has its own initialization state and its own static fields. A client that has embedded a compile-time constant does not even need to load the class where the field was originally declared when reading the constant.

Conversely, when using a class literal or forName through a different loader, you can obtain a **different Class object**, even with the same name. This is why you must identify **(binary name, defining loader)** when investigating class initialization issues in plugins/application servers.

## 18. Common mistakes and how to fix them

| Misconception | Why it is wrong | How to verify |
| --- | --- | --- |
| "All static final fields do not initialize the class." | Wrappers, new String, method calls, etc. are not constant variables | Check JLS 4.12.4 and the initializer |
| "Just writing Child.X in source initializes Child." | X may be declared by Parent | Find the declaring field; inspect the owner of getstatic in javap |
| "Getting Child.class will print the static block." | A class literal is not an active use | Test the static block and class literal |
| "Class.forName always only loads." | forName(name) requires init; the false overload does not | Choose the right overload |
| "A String constant with + is not a constant." | Concatenating compile-time string constants can still be a constant expression | Check the constant-expression grammar |
| "Client automatically reads the new constant value when swapping the JAR." | The value may have been embedded in Client.class | Rebuild/recompile the client; check javap -c |
| "Having a Class object proves <clinit> has run." | Loading/linking is different from initialization | Observe initializer side effects and active use |
| "Static final Integer is the same as static final int." | Integer is a reference wrapper, not a constant variable | Identify the declared type |
| "Accessing Child.parentField causes both Parent and Child to init." | Only the declaring field undergoes active use, if nonconstant | Observe the two static initializers independently |
| "All reflection access does not initialize." | Field.get and certain operations require init | Read the corresponding API contract |
| "Creating new T[10] initializes T." | Array creation is different from creating a T instance | Distinguish anewarray from new |
| "Source has only one class so there is only one lifecycle." | Nested/static member classes have their own runtime classes | Run javap on each class, observe separate init |

## 19. Procedure for predicting stdout of a program

When encountering a question with **static blocks, constants, class literals, Parent/Child**, do not guess by intuition. Follow these steps:

1. **List the runtime classes** and inheritance/interface structure; distinguish nested classes and superclasses.
2. **Note the true declaration site** of each field/method used, rather than inferring from the qualifier name before the dot.
3. **Classify static fields:** constant variable if final + primitive/String + constant expression, or runtime field otherwise.
4. **Mark active use operations**: new instance, static method invocation, nonconstant static field read/write, reflective initialization; skip class literals or constant reads if those are all that occur.
5. **When class T initializes for the first time**, include superclass initialization and the appropriate superinterfaces per the rules, then run T's static initializers in textual order; a class that has already initialized successfully does not run again.
6. **For interfaces**, remember that initializing an interface does not automatically initialize all superinterfaces.
7. **Trace side effects** of the initializers that are actually invoked, recording stdout in order.
8. **Treat class literals/forName(false)** as operations that may load/link but do not yet require init.
9. **Cross-check with javap**: constants appear as literals, runtime static fields use getstatic with the declaring owner; string concatenation may be folded by the compiler.
10. **If there are multiple class loaders**, separate the state of each runtime class by its defining loader before building the timeline.

Self-practice table:

| Step | Source expression | Declaring type | Constant variable? | Which class must init? | Output/side effect |
| --- | --- | --- | --- | --- | --- |
| 1 | **Child.CONST** | Parent | Yes | None from this operation | Prints constant |
| 2 | **Child.runtimeValue** | Parent | No | Parent | Parent static initializer |
| 3 | **Child.class** | Not a field | Not applicable | None from class literal | Obtains Class object |
| 4 | **Child.ownRuntime** | Child | No | Child (and uninitialized superclass if needed) | Child static initializer |

## 20. Self-check exercises

**Exercise 1.** Which fields are constant variables?

~~~java
static final int A = 3 * 7;
static final Integer B = 21;
static final String C = "ja" + "va";
static final int D = Math.max(20, 21);
~~~

**Answer:** **A** and **C**. B has type Integer; D has a method call.

**Exercise 2.** Does the following snippet print **"init"** when only the client line is executed?

~~~java
class Settings {
    static final int PORT = 8080;
    static { System.out.println("init"); }
}
int p = Settings.PORT;
~~~

**Answer:** No, not from reading the constant variable; the compiler can use literal 8080 directly. The client line must be placed inside a valid method to run the program.

**Exercise 3.** Does the class literal of a class with a static block initialize it immediately?

~~~java
Class<?> c = Settings.class;
~~~

**Answer:** No. A class literal creates/obtains the Class object, which is not an active use that initializes Settings.

**Exercise 4.** Do the two forName methods have the same initialization effect?

~~~java
Class.forName("pkg.Settings");
Class.forName("pkg.Settings", false, loader);
~~~

**Answer:** No. The single-parameter overload requires initialization; the **false** overload does not. This example is illustrative only and requires a valid class and loader.

**Exercise 5.** If **Parent.value** is a nonconstant static field, and **Child extends Parent** does not declare value, which class does reading **Child.value** initialize?

**Answer:** Parent; Child does not initialize just because it is used as the qualifier.

**Exercise 6.** If Child **declares** a new field value with the same name as Parent.value, what happens when reading **Child.value**?

**Answer:** The selected field is Child.value; if nonconstant, Child must initialize (and superclass Parent is initialized beforehand if needed).

**Exercise 7.** Interface Root declares **int C = 1** and **int R = compute()**, and Branch extends Root. What is the difference between reading **Branch.C** and **Branch.R**?

**Answer:** C is a constant variable so reading it does not initialize Root; R is a runtime field so reading it causes Root to initialize. Branch does not automatically initialize just because of the qualifier.

**Exercise 8.** A library changes **public static final String VERSION = "v1"** to **"v2"**, but an old client still prints v1. Why?

**Answer:** VERSION is a constant variable, so the client may contain the constant embedded at compile time. Recompile the client against the new library; if a runtime-configurable value is needed, design a different API.

**Exercise 9.** Is **static final String NAME = new String("A")** a compile-time constant?

**Answer:** No. It uses **new**, which is not a constant expression; reading static field NAME requires initializing the class.

**Exercise 10.** A program only executes **new Widget[3]** and has never used Widget. Must the static block in Widget run?

**Answer:** No. Creating an array does not create a Widget instance and is not an active use that initializes Widget.

**Exercise 11.** Can **Field.get(null)** on a static final int constant cause the declaring class to initialize, even though reading it directly in Java source does not?

**Answer:** Yes. Reflection Field.get on a static field has its own contract regarding initialization; compiler inlining rules do not apply to reflection calls.

**Exercise 12.** Why might **javap** not have **getstatic Parent.LIMIT** for the source line **Child.LIMIT**?

**Answer:** LIMIT is a constant variable whose value is resolved at compile time and used directly in the client bytecode. Child is a source qualifier, not the declaring type, and does not need to initialize to read the constant.

**Exercise 13.** Place **Class.forName("ClassLiteralDemo$Child", true, loader)** after a **Child.class.getName()** in a fresh JVM: which class initializes first if neither is initialized and Child extends Parent?

**Answer:** Parent is initialized before Child when the JVM initializes Child; class literal/getName does not force either to initialize before the forName(true) call.

## 21. Checklist when writing code and in JVM interviews

- First determine whether it is a **compile-time constant** or a **runtime static field**.
- Use the exact definition: **final + primitive/String + constant expression**; do not assume every **static final** is a compile-time constant.
- For **T.class**, do not infer that static code has run; for **Class.forName**, check the **exact overload** and the initialize parameter.
- When source writes **Child.X**, find **the class/interface that actually declares X**; do not assume Child initializes.
- For hidden fields, identify the declaration chosen by the compiler based on the expression's type.
- For **subinterfaces**, remember that initializing an interface does not automatically initialize superinterfaces.
- For long-lived client builds, suspect **inlined public constants** if old values are observed at runtime.
- When using Reflection, do not mechanically apply the Java source constant read rule; read the API contract.
- If an exact explanation is needed, compile and inspect **javap -c/-v**, observing constants, **getstatic owner**, and Class literals.
- Use static initializers with side effects cautiously: they only run when there is an initialization request and can throw errors that put the class in an erroneous state.
- When debugging with plugins, always consider the **defining class loader**, because the same class name can be two runtime classes.
- Avoid depending on detailed loading/linking timing that the JVM is allowed to decide flexibly.

### Reference Documentation

- **JLS Java SE 17, §4.12.4 — final Variables / Constant Variables:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4
- **JLS Java SE 17, §15.29 — Constant Expressions:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29
- **JLS Java SE 17, §12.4.1 — When Initialization Occurs:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1
- **JLS Java SE 17, §12.4.2 — Detailed Initialization Procedure:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
- **JLS Java SE 17, §13.4.9 — final Fields and Constants / Binary Compatibility:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.4.9
- **JVMS Java SE 17, §5.5 — Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JVMS Java SE 17, §4.7.2 — ConstantValue Attribute:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2
- **Java SE 17 API — Class.forName:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 API — java.lang.reflect.Field:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html

**Remember:** A **constant variable** allows clients to use a compile-time constant without forcing the declaring class to initialize; a **class literal** returns a Class object without automatically running **<clinit>**; **Child.field** must be resolved to the **actual declaring class/interface** before applying active use rules. When analyzing initializers, the exact question is not "which class name does the source mention?", but **"what runtime operation occurs, where is the field/method declared, and is it a constant variable?"**.
