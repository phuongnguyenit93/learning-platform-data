# Operations That Actively Trigger Class and Interface Initialization in Java

## 1. What Phase Is Initialization?

When we say the JVM performs **class initialization**, we are referring to the phase that executes the initialization code for `static` variables and `static { … }` blocks of a class or interface. Standard compilers gather these initialization steps into a special class initialization method `<clinit>` in bytecode; not every class needs a `<clinit>`. This phase differs from:

- **Loading:** finding/reading the class representation and creating the corresponding `Class` object.
- **Linking:** consists of verification, preparation, and resolution (which may be performed at an appropriate time). Preparation allocates memory for `static` variables and sets default values. Values from the `ConstantValue` attribute are assigned during **initialization, before `<clinit>`**, according to JVMS §5.5.
- **Initialization:** executing `static` initializers that have runtime effect in declaration order, and ensuring the required initialization relationships with supertypes.

A class that has been *loaded* or *linked* **has not necessarily been initialized**. The JVM can load type information beforehand and defer running `static` code until the program actually uses the type in one of the ways considered **active use** by the specification.

Within a single JVM, for a specific class identified by its **binary name together with its defining class loader**, successful initialization is performed once. Multiple threads that simultaneously trigger that class are synchronized by the JVM; subsequent uses do not re-run `static` blocks.

## 2. The Four Primary Bytecode Operations That Force JVM Initialization

At the JVM level, the four most important instructions are `new`, `getstatic`, `putstatic`, and `invokestatic`. When the instruction is executed and the target class/interface has not yet been initialized, the JVM must perform initialization before the operation can proceed (after the necessary loading/linking steps).

| JVM Instruction | Common Java Usage | Type Actually Initialized | Notes |
| --- | --- | --- | --- |
| `new` | `new Customer()` | The instantiated `Customer` class, along with required supertypes | Merely declaring a reference variable is not equivalent to instantiating an object. |
| `getstatic` | `Customer.total` | The class/interface that **declares** the resolved `static` field | Reading a field that is not a *constant variable* triggers initialization; compile-time constants are typically inlined and thus do not emit `getstatic`. |
| `putstatic` | `Customer.total = 10` | The class/interface that **declares** the resolved `static` field | The JVM initializes the type before the external `static` write executes. |
| `invokestatic` | `Customer.refresh()` | The class/interface that **declares** the resolved `static` method | Initialization occurs before the `static` method body is invoked. |

For example, with:

~~~java
class Counter {
    static int count = initialize();
    static int initialize() {
        System.out.println("Counter initialized");
        return 1;
    }
    static void reset() { count = 0; }
}
~~~

The first execution of `Counter.count`, `Counter.count = 9`, or `Counter.reset()` will initialize `Counter` first, if that type has not yet been initialized. If all three operations are run sequentially, the initialization message appears only once. The snippet above is an illustrative class to drop into a program; a complete example with `main` and deterministic output is in Section 6.

**Note on the actual target:** in `Child.inheritedField`, the field may be declared in `Parent`; in that case, `Parent` itself is initialized by the field access, while `Child` is not necessarily initialized. The same rule applies to inherited `static` methods: consider the type **that declares the resolved member**, not just what is written to the left of the dot.

### 2.1. `new`: Creating a Class Instance

`new Account()` is an active use of the `Account` class. Before the object is created in the normal way, the JVM must ensure that `Account` has been initialized; if the class has an uninitialized superclass, the superclass is initialized first. Only after that do the instance initializer and constructor logic run.

Distinguish clearly:

- `Account account;` only declares a variable.
- `Account account = null;` only assigns a `null` reference.
- `Account[] accounts = new Account[3];` creates an **array object**, and does not itself trigger initialization of the element class `Account`.
- `new Account()` is what directly triggers initialization of `Account`.

Do not infer that the JVM is forced to initialize every class mentioned by name in a source file.

### 2.2. `getstatic`: Reading a `static` Field That Is Not a Compile-Time Constant

For example:

~~~java
static final int MAX_SIZE = 64;                   // constant variable
static final String PREFIX = "ID-";             // constant variable
static final int PORT = Integer.parseInt("8080"); // value computed at runtime
static final Integer BOXED = 64;                  // not a constant variable
static int counter = 1;
~~~

In Java, a *constant variable* is a `final` variable of primitive type or `String` that is initialized with a **constant expression**. Expressions reading `MAX_SIZE` or `PREFIX` from elsewhere are typically compiled directly to the constant value itself; that read **does not trigger initialization** of the class declaring the constant.

Conversely, `PORT`, `BOXED`, and `counter` are not constant variables. Even though `PORT` and `BOXED` also have `final`, reading these fields can emit `getstatic` and initialize the declaring class. The statement "accessing any `static final` never triggers initialization" is **false**.

Because the compiler can inline constant values into the caller's class file, changing a constant in a library without recompiling the caller can also cause the caller to use the stale value. This is a consequence of constant inlining, not a class loader bug.

### 2.3. `putstatic`: Writing a `static` Field

For example, `Settings.enabled = true` requires the class declaring `enabled` to have been initialized before the write. If `Settings` contains `static boolean enabled = false;`, the initializer runs during the initialization phase, and then the external assignment sets it to `true`. Do not confuse default/internal initialization steps with a caller's `static` write operation.

### 2.4. `invokestatic`: Calling a `static` Method

For example, `Registry.open()` triggers initialization of the type declaring the `open` method before the method body executes. This holds true even if the method does not access any `static` fields.

A normal *instance* method call through an existing object is not a new active cause for initializing the type: creating an instance of a class in the standard way already required that class to be initialized.

## 3. Operations via Reflection and MethodHandle

Beyond standard Java syntax, several dynamic invocation APIs also actively trigger initialization:

| Operation | Triggers Initialization? | Conditions / Explanation |
| --- | --- | --- |
| `Class.forName("com.example.Plugin")` | **Yes** | The single-argument overload requires initializing the found class. |
| `Class.forName(name, true, loader)` | **Yes** | `initialize=true` requests initialization if the class is not yet initialized. |
| `Class.forName(name, false, loader)` | **Not by this call alone** | Finds/loads the class without requesting execution of its initializers. |
| `SomeType.class` | **No** | Obtaining a `Class` object does not itself trigger initialization of the corresponding type. |
| `SomeType.class.getDeclaredMethods()` | **Normally no** | Only inspects the type's metadata; unlike invoking a discovered `static` method. |
| `SomeType.class.getDeclaredConstructor().newInstance()` | **Yes** | Reflection actually instantiates the class. |
| `Method.invoke(null, …)` for a `static` method | **Yes** | Invokes the `static` method of the declaring type. |
| `Field.get(null)` / `Field.set(null, value)` for a `static` field | **Yes** | Reads or writes a `static` field via reflection; unlike retrieving `Field` metadata. |
| `ClassLoader.loadClass(name)` under standard implementation | **Does not itself require initialization** | Primarily loads/returns `Class`; a custom loader may still run additional logic on its own. |

For example, if you want to discover plugins without running static initializers yet, you typically start with `Class.forName(name, false, loader)`, and then decide when to actually initialize them. Conversely, `Class.forName(name)` can execute code inside `static { … }` immediately, making it unsuitable if the goal is merely to read metadata without triggering the class.

At the JVM level, the **first invocation** of a `MethodHandle` created from resolving a reference with reference kind `REF_getStatic`, `REF_putStatic`, `REF_invokeStatic`, or `REF_newInvokeSpecial` can also trigger initialization of the target type. Distinguish between merely *looking up/creating a handle* and actually *invoking the handle*; the exact timing and conditions are defined in JVMS §5.5. When invoking the bootstrap method of `invokedynamic`, executing that bootstrap method must also adhere to the corresponding initialization rules.

In addition, the JVM initializes the class chosen as the program entry point before invoking `main`, and certain JNI/reflective calls from native code may also require initialization. Therefore, the list of Java statements inside a single file does not represent all possible entry points into this process.

## 4. Transitive Initialization Through Inheritance Relationships

When **a class** is initialized, the JVM guarantees:

1. Any uninitialized superclass is initialized **before** the subclass.
2. Any superinterfaces in the proper inheritance hierarchy **that declare a default method** are also initialized according to the JVM algorithm; this may include compiler-generated default methods.
3. Only after these prerequisite steps do the `static` initializers of the class being initialized execute.

Do not infer that **every interface a class `implements` is initialized immediately**. An interface without default methods normally does not have to be initialized merely because an implementing class is initialized. On the other hand, initializing **an interface** does not automatically initialize all of its superinterfaces.

Consider a meaningful example with the declarations:

~~~java
class Parent {
    static int total = 4;
}
class Child extends Parent {
    static { System.out.println("Child initialized"); }
}
~~~

If the first use is `Child.total`, `Parent` is the one declaring the `total` field, so `Parent` is initialized, while `Child` **is not initialized solely because of the `Child.total` syntax**. If `new Child()` is executed afterward, `Child` is then initialized; `Parent` is not initialized a second time.

The *only the declaring type* principle also applies to reading a `static` field of an interface via the name of a subinterface or implementing class. When solving exercises, identify where the member is **actually declared** before concluding which type runs `<clinit>`.

## 5. Cases That Seem Like Active Use but Are Not

| Action | Initializes `Target` From That Action Alone? | Why? |
| --- | --- | --- |
| `Target t = null;` | No | Only declares/assigns a reference. |
| `Target.class` | No | Having a `Class` object does not mean running static initializers. |
| `new Target[5]` | No | Creates an array of references, not `Target` instances. |
| `obj instanceof Target` or `(Target) obj` | No | Type testing/casting is not one of the four primary active initialization instructions. |
| `ClassLoader.loadClass("Target")` | No, under the standard loadClass contract | Loading is distinct from initialization. |
| Reading `Target.CONST` when `CONST` is a constant variable | No | The value is typically inlined directly into the caller's bytecode. |
| Retrieving `Field`/`Method` metadata via reflection | Not merely from retrieving metadata | Subsequent reading/writing of the field or invoking the static method is what triggers initialization. |
| Reading `Child.parentField` inherited from `Parent` | No for `Child` | Only the type that actually declares the field is the initialization target of `getstatic`. |

The "no" conclusions in this table apply **to the specific operation under consideration itself**. Surrounding code, additional APIs, or custom class loader mechanisms can still produce side effects and initialize the class themselves during processing. A class could also have already been initialized earlier by another operation.

## 6. Java 17+ Experiment to Verify the Cases

Save the following **`ActiveInitDemo.java`** file in a separate directory and run it with JDK 17 or later. The example places all helper types inside an outer class so it can be compiled and executed standalone.

~~~java
public class ActiveInitDemo {
    static class Constants {
        static { System.out.println("init Constants"); }
        static final int COMPILE_TIME = 7;
        static final int RUNTIME = Integer.parseInt("9");
    }

    static class OnWrite {
        static { System.out.println("init OnWrite"); }
        static int count = 1;
    }

    static class OnCall {
        static { System.out.println("init OnCall"); }
        static void ping() { System.out.println("ping"); }
    }

    static class Parent {
        static { System.out.println("init Parent"); }
        static int inherited = 4;
    }

    static class Child extends Parent {
        static { System.out.println("init Child"); }
    }

    interface WithDefault {
        int MARKER = announce();
        static int announce() {
            System.out.println("init WithDefault");
            return 1;
        }
        default void action() {}
    }

    static class ImplementsDefault implements WithDefault {
        static { System.out.println("init ImplementsDefault"); }
    }

    static class Reflective {
        static { System.out.println("init Reflective"); }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. passive");
        Class<?> type = Constants.class;
        System.out.println("constant=" + Constants.COMPILE_TIME);
        Class.forName(type.getName(), false, type.getClassLoader());

        System.out.println("2. getstatic");
        System.out.println("runtime=" + Constants.RUNTIME);

        System.out.println("3. putstatic");
        OnWrite.count = 5;
        System.out.println("count=" + OnWrite.count);

        System.out.println("4. invokestatic");
        OnCall.ping();

        System.out.println("5. inherited static");
        System.out.println("inherited=" + Child.inherited);

        System.out.println("6. new Child");
        new Child();

        System.out.println("7. new ImplementsDefault");
        new ImplementsDefault();

        System.out.println("8. reflection");
        Class.forName(Reflective.class.getName());
        System.out.println("done");
    }
}
~~~

Run in the directory containing the source:

~~~bash
javac ActiveInitDemo.java
java ActiveInitDemo
~~~

Stdout output (executed and verified):

~~~text
1. passive
constant=7
2. getstatic
init Constants
runtime=9
3. putstatic
init OnWrite
count=5
4. invokestatic
init OnCall
ping
5. inherited static
init Parent
inherited=4
6. new Child
init Child
7. new ImplementsDefault
init WithDefault
init ImplementsDefault
8. reflection
init Reflective
done
~~~

**Reading the results in sequence:**

1. The `passive` section retrieves `Constants.class`, reads the `COMPILE_TIME` constant, and calls `Class.forName(..., false, ...)`. None of those lines print `init Constants`.
2. Reading `Constants.RUNTIME` (a `static final int` that is *not* a constant variable) forces initialization of `Constants`; the initializer prints `init Constants` before `main` prints the value `9`.
3. Writing `OnWrite.count = 5` forces initialization of `OnWrite` first; the value of `count` afterward is `5`. The subsequent read does not re-run the initializer.
4. Calling `OnCall.ping()` forces initialization of `OnCall` before printing `ping`.
5. Accessing `Child.inherited` initializes `Parent`, because that field is declared in `Parent`. It does **not yet** print `init Child`.
6. `new Child()` then initializes `Child`; `Parent` is already initialized, so it does not print a second time.
7. `ImplementsDefault` has a superinterface `WithDefault` declaring the default method `action()`. The JVM initializes `WithDefault` before `ImplementsDefault`, demonstrating this dependent initialization rule when initializing a class.
8. `Class.forName(Reflective.class.getName())` requires initializing `Reflective`, so the message appears before `done`.

In the example above, the helper classes are each used for the first time in order so that observation is independent and easy to verify. If you change the order of the operations, a class already initialized in an earlier step will not re-run its initializer, resulting in different output.

## 7. Initialization Flow and Common Pitfalls

When an operation requires initializing a type `T`, the JVM uses that type's own initialization state to ensure correct behavior across multiple threads:

~~~text
Active use operation on T
          |
          v
T already successfully initialized? ---- Yes ----> Proceed with operation
          |
          No
          |
          v
T being initialized by another thread?
          |                              \
         Yes                              No
          |                                |
          v                                v
Wait for result per JVM rules      Initialize relevant supertypes
                                           |
                                           v
                                  Run T's initializers
                                           |
                               +-----------+-----------+
                               |                       |
                            Success                 Failure
                               |                       |
                               v                       v
                          Mark as done      T is in erroneous state
~~~

Details of the synchronization algorithm and recursive initialization handling are specified in JLS §12.4.2 and JVMS §5.5; the diagram only outlines the stages needed for conceptual understanding.

- **`static` block throws an exception:** when an initializer fails, the JVM marks the type as erroneous. The failing initialization attempt can throw `ExceptionInInitializerError` (if the cause is an exception that is not an `Error`); subsequent uses can receive `NoClassDefFoundError` because the class could not be initialized. That is an *initialization* error, distinct from a class file not being found.
- **Using `static` variables in an initialization cycle:** an initializer can call into another type and then circle back to the original type. The initializing thread can observe fields that have not yet been assigned their final values, such as `0` or `null`; avoid designing circularly dependent initializers.
- **I/O, networking, or heavy logic in `static`:** merely calling `Class.forName(name)` or a simple `static` method can incur unexpected work or failure at runtime; keep side effects controlled.
- **Measuring timing via loading logs:** `-verbose:class` or `-Xlog:class+load=info` indicates class loading, and does not prove when `<clinit>` runs. Use messages inside initializers or dedicated tools to observe initialization.
- **Misunderstanding constants:** only a *constant variable* per the JLS has the non-initializing read rule described above. Having `static final` does not mean it is a compile-time constant.
- **Misidentifying the initialization target through inheritance:** determine where the member is declared or which class is actually being instantiated, rather than guessing from the name before the dot.

## 8. Checklist for Reasoning Whether an Expression Triggers Initialization

When encountering a Java expression or bytecode snippet, check the following in order:

1. Is the JVM executing `new`, `getstatic`, `putstatic`, or `invokestatic`? If it is an access to a `static final` constant, check whether the compiler inlined a literal instead of emitting `getstatic`.
2. If it is a `static` member access, **which class/interface declares the field or method after resolution**?
3. If it is reflection, is it only reading metadata, or is it actually requesting initialization, creating an instance, invoking a method, or reading/writing a `static` field? For `Class.forName` overloads, what is the `initialize` argument?
4. If it is a `MethodHandle`, is it merely obtaining the handle or invoking a handle of a trigger-capable reference kind?
5. Has the target type already been initialized? If it is done, initializers do not run again. If not, its superclass and relevant superinterfaces with default methods may need to be initialized first.
6. Do not guess solely from the fact that a class has been loaded, has a `Class` object, is mentioned in a signature, or has an array of that type.

**Self-check:** Do the two statements `Plugin.class.getDeclaredMethods()` and `Class.forName("com.example.Plugin")` have the same effect on the static initializer of `Plugin`? **No.** The first only queries metadata; the second (with the single-parameter overload and a valid class name) requires initialization if `Plugin` has not yet been initialized.

## Authoritative References

- [JLS Java SE 21, §12.4.1 – When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1): lists language-level active uses, compile-time constants, classes/interfaces, default methods, and reflection.
- [JLS Java SE 21, §12.4.2 – Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.2): synchronization, recursive initialization, and failure handling.
- [JVMS Java SE 21, §5.5 – Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5): `new`, `getstatic`, `putstatic`, `invokestatic`, `MethodHandle`, and JVM behavior.
- [JDK 21, Class.forName](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): distinguishes between `initialize=true` and `false`.
