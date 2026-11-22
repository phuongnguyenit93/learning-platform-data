# Operations That Do Not Trigger Class Initialization: Class Literals, Arrays, and Compile-Time Constants

## 1. What Problem Does This Lesson Solve?

In Java, **the JVM knowing about a class** does not necessarily mean **that class has been initialized**. Three cases that frequently cause confusion are:

1. Accessing a **class literal** such as `Example.class`.
2. Creating an **array whose element type is a class** such as `new Example[5]`.
3. Reading a **compile-time constant** such as `Example.MAX_SIZE` if it is a true *constant variable*.

**All three operations above, considered on their own, do not trigger initialization of `Example`.** However, the JVM may still have loaded/linked `Example`. And if a related expression performs an additional "active use" operation (such as `new Example()` or reading a non-constant `static` field), the class can still be initialized right then.

Goal after this lesson: accurately identify the three non-triggering cases, distinguish `static final` from a **constant variable**, predict the output of the Java 17+ example, and avoid confusing **loading** with **initialization**.

## 2. Background: How Loading, Linking, and Initialization Differ

When the JVM works with a type:

- **Loading:** finding/defining the runtime representation of the class from class data. A corresponding `Class<?>` object may be used by the JVM.
- **Linking:** `verification`, `preparation`, and symbolic reference `resolution`. Some resolution may occur later.
- **Initialization:** executing the initialization logic for `static` variables and the class's `static {}` blocks according to Java/JVM rules.

Illustrative code example:

~~~java
class Sample {
    static {
        System.out.println("Sample initialized");
    }
}
~~~

Seeing `Sample.class` or seeing that the JVM has loaded the bytecode is not enough to conclude that `Sample initialized` has been printed. Only when `Sample` is **initialized** is the `static` block above executed; in a normally initialized class definition, this block does not run again on every access.

According to [JLS 12.4.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1), a class is normally triggered for initialization upon the first occurrence of an operation such as:

- `new Sample()`: creating a `Sample` **instance**.
- `Sample.run()`: invoking a `static` method **actually declared by `Sample`**.
- Assigning a `static` field declared by `Sample`.
- Reading a `static` field declared by `Sample` **if it is not a constant variable**.
- Certain special/reflection mechanisms, for example the `Class.forName(String)` overload that requires initialization.

When a subclass is initialized, its superclass must also be initialized according to the rules. For an inherited static field, you must pay attention to the **class that declares the field**, not just the class name written to the left of the dot.

**Exact scope of this lesson:** "Does not trigger" only means **the operation under consideration does not by itself require initialization of the target class**. It does not prove that the class has not been loaded/linked, has not been initialized previously, or that no other class is initialized as a result of evaluating the expression.

## 3. Class Literals: `Sample.class` Does Not Initialize `Sample`

### 3.1. Retrieving Metadata Is Not Creating an Instance

~~~java
Class<Sample> info = Sample.class;
System.out.println(info.getName());
~~~

`Sample.class` is a **class literal**: it provides a `Class<Sample>` object describing the type. This operation **does not by itself trigger** `Sample`'s `static {}` block. Printing the name via metadata also does not force `Sample` to be initialized.

Compare:

~~~java
Sample object = new Sample(); // triggers initialization of Sample if it has not occurred yet
~~~

`new Sample()` creates an instance; this is one of the active use operations. The difference lies between **retrieving metadata** and **creating an object of the class**.

### 3.2. Table Distinguishing Similar-Looking Expressions

| Expression | Does it by itself require initializing class `Sample`? | Reason |
|---|---|---|
| `Sample.class` | **No** | A class literal only references metadata about the type |
| `Sample[].class` | **No** | A class literal for the array type; does not create a `Sample` instance |
| `Class.forName("Sample", false, loader)` | **Does not require** | `false` explicitly states initialization is not required |
| `Class.forName("Sample")` | **Yes** | The single-parameter overload requires initialization |
| `Class.forName("Sample", true, loader)` | **Yes** | The `true` flag requires initialization |
| `new Sample()` | **Yes** | Creates an instance |
| `Sample.action()` if `action` is a static method declared in `Sample` | **Yes** | Calls a static method of the class |

For a class in a package, `Class.forName` requires the appropriate **binary name**, for example `com.example.Sample`. For a static nested class, the binary name uses `$`. Meanwhile, `Sample.class` is understood directly by the compiler from the source code.

### 3.3. Where Reasoning Easily Goes Wrong

- **"`Sample.class` has not run `static`, so it has not been loaded."** Unfounded. Loading and initialization are two different things.
- **"Having a `Class<?>` object means there is already a `Sample` instance."** False. `Class<?>` represents metadata of the type, not the instance that `new Sample()` creates.
- **"`Class.forName` always only loads."** False: the overload and the `initialize` flag determine whether initialization is required. Do not use `Class.forName("Sample")` to illustrate a *not* initializing case.

## 4. Creating an Array Does Not Mean Initializing the Element Class

### 4.1. An Array Only Allocates Slots to Hold References

~~~java
Sample[] samples = new Sample[3];
System.out.println(samples.length); // 3
~~~

The expression `new Sample[3]` creates **an array object** consisting of three reference slots, all initially `null`:

~~~text
samples: Sample[]
+-----------+-----------+-----------+
| null      | null      | null      |
+-----------+-----------+-----------+
     [0]         [1]         [2]
~~~

It does **not** call `new Sample()` three times. Therefore, creating an array does not by itself trigger initialization of the component class `Sample`.

Similarly, the following two expressions do not by themselves initialize the `Sample` class:

~~~java
Sample[][] grid = new Sample[2][3];
Class<?> arrayType = Sample[].class;
~~~

The JVM may create or find the runtime class for the array type and element class information, but that is not initializing `Sample`. You should not use the time when the array class is created to infer when `Sample`'s `static {}` block runs.

### 4.2. When an Instance Appears Inside the Array Creation Expression

~~~java
Sample[] refs = new Sample[2];               // does not initialize Sample
Sample[] withObject = {new Sample(), null};  // initializes Sample
~~~

In the second line, **`new Sample()`** is the triggering operation, not the braces of the array initializer.

Similarly:

~~~java
Sample[] data = new Sample[Sample.size()];
~~~

If `size()` is a static method declared by `Sample`, calling `Sample.size()` can trigger initialization before the array is allocated. **Evaluating expressions inside the statement** must be separated from the initialization rule of `new Sample[...]` itself.

### 4.3. How to Observe It Yourself

Put `System.out.println("INIT Sample")` inside `Sample`'s `static {}`. Run a fresh JVM and execute **only** `Sample[] a = new Sample[2];`, printing `a.length`; expect not to see `INIT Sample`. Then add `a[0] = new Sample();`: when there has been no prior initialization activity, the line `INIT Sample` appears at the moment the instance is created.

## 5. Reading Compile-Time Constants Does Not Initialize the Declaring Class

### 5.1. The Proper Definition of a Constant Variable

Not every `static final` is a compile-time constant. According to [JLS 4.12.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4), a **constant variable** must simultaneously:

1. Be a `final` variable.
2. Have a **primitive** type such as `int`, `boolean`, `long`, `char`, or **`String`**.
3. Be initialized with a **constant expression** (see [JLS 15.29](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29)).

In practice, we commonly encounter a **`static final` constant variable** made public in a class or interface. The compiler can inline the value directly at the use site; reading this constant field does not by itself trigger the declaring class's initializer.

~~~java
class Limits {
    static {
        System.out.println("INIT Limits");
    }

    static final int MAX = 2 + 3;           // constant variable
    static final String PREFIX = "ja" + "va"; // constant variable
}
~~~

`System.out.println(Limits.MAX)` will print `5`; `System.out.println(Limits.PREFIX)` will print `java`. Reading those two constant variables alone does **not** cause `INIT Limits` to appear.

### 5.2. Comparing Each Type of Static Field

| Field declaration in `Limits` | Constant variable? | Does reading the field by itself trigger `Limits`? |
|---|---|---|
| `static final int MAX = 5;` | Yes | **No** |
| `static final long MASK = 1L << 3;` | Yes | **No** |
| `static final String CODE = "A" + "B";` | Yes | **No** |
| `static final boolean READY = true;` | Yes | **No** |
| `static final Integer BOXED = 5;` | **No** — `Integer` is a reference type | **Yes** |
| `static final int DYNAMIC = Integer.parseInt("5");` | **No** — a method call is not a constant expression | **Yes** |
| `static final String UUID = System.getProperty("id");` | **No** — method call | **Yes** |
| `static final String X = new String("x");` | **No** — `new` is not a constant expression | **Yes** |
| `static final int[] VALUES = {1, 2};` | **No** — array type | **Yes** |
| `static int mutable = 5;` | **No** — does not have `final` | **Yes** |

Do not confuse "assigned once", "fixed value in an example", or "has the `final` modifier" with the definition of a *constant variable*.

### 5.3. Interfaces and Fields Declared in a Superclass

A field declared in an interface is implicitly `public static final`, but it is only a *constant variable* if its value is a constant expression:

~~~java
interface Options {
    int PORT = 8080;                           // constant variable
    String MODE = System.getProperty("mode");   // not a constant variable
}
~~~

Reading `Options.PORT` does not by itself initialize `Options`; reading `Options.MODE` is an active use of a nonconstant static field and can trigger initialization of the interface.

With inheritance:

~~~java
class Parent {
    static int count = 1;
}
class Child extends Parent {}
~~~

Writing `Child.count` actually references the field **declared by `Parent`**. If not yet initialized, this read of a nonconstant field initializes `Parent`; writing `Child.count` does not automatically initialize `Child`.

### 5.4. Risk When Changing a Public Compile-Time Constant

If a library publishes:

~~~java
public static final int API_VERSION = 1;
~~~

a compiled client may store the literal `1` directly in its bytecode. Later, if the library changes the field to `2` while the client **has not been recompiled**, the client can still print `1` even when running against the new library JAR.

This is a consequence of **compile-time inlining** and binary compatibility ([JLS 13.4.9](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.9)), not the ClassLoader "mistakenly keeping the value". When changing a public constant that clients depend on, check and recompile clients when needed.

## 6. Standalone Java 17+ Practice

Create the exact file **`NoInitTriggersDemo.java`**. All required classes are in a single file:

~~~java
public class NoInitTriggersDemo {
    static class FromLiteral {
        static { System.out.println("INIT FromLiteral"); }
    }

    static class ArrayElement {
        static { System.out.println("INIT ArrayElement"); }
    }

    static class CompileTimeConstants {
        static { System.out.println("INIT CompileTimeConstants"); }
        static final int RETRIES = 2 + 3;
        static final String MODE = "safe";
        static final Integer BOXED = 10;
    }

    static class ComputedValue {
        static { System.out.println("INIT ComputedValue"); }
        static final int COUNT = Integer.parseInt("9");
    }

    public static void main(String[] args) {
        System.out.println("A");
        Class<?> type = FromLiteral.class;
        System.out.println(type.getSimpleName());

        System.out.println("B");
        ArrayElement[] array = new ArrayElement[3];
        System.out.println(array.length);

        System.out.println("C");
        System.out.println(CompileTimeConstants.RETRIES);
        System.out.println(CompileTimeConstants.MODE);

        System.out.println("D");
        System.out.println(ComputedValue.COUNT);

        System.out.println("E");
        System.out.println(CompileTimeConstants.BOXED);

        System.out.println("F");
        new FromLiteral();
        new ArrayElement();
    }
}
~~~

Compile/run from the directory containing the file:

~~~sh
javac NoInitTriggersDemo.java
java NoInitTriggersDemo
~~~

**Exact stdout** (verified with `javac --release 17`):

~~~text
A
FromLiteral
B
3
C
5
safe
D
INIT ComputedValue
9
E
INIT CompileTimeConstants
10
F
INIT FromLiteral
INIT ArrayElement
~~~

### Explaining the Exact Initialization Points

| Line group | Operation | Why not initialized / initialized |
|---|---|---|
| `A → FromLiteral` | `FromLiteral.class` and reading metadata name | No active use yet that triggers `FromLiteral` initialization |
| `B → 3` | `new ArrayElement[3]` | Creates an array of `null`; does not create `ArrayElement` |
| `C → 5 / safe` | Reading `RETRIES` and `MODE` | Both fields are constant variables, so they do not by themselves initialize `CompileTimeConstants` |
| `D → INIT ComputedValue → 9` | Reading `COUNT` | `Integer.parseInt` makes `COUNT` not a constant variable; `getstatic` triggers initialization |
| `E → INIT CompileTimeConstants → 10` | Reading `BOXED` | `Integer` is a reference type, so `BOXED` is not a constant variable |
| `F → INIT FromLiteral / INIT ArrayElement` | Two `new` expressions | Creates an instance of each class, triggering initialization if the class is not yet initialized |

The most important observation is that `INIT CompileTimeConstants` **does not appear when reading the two constants `RETRIES`/`MODE`**, and only appears when reading `BOXED`. `FromLiteral` also only initializes when creating an instance in group `F`, even though `FromLiteral.class` was already retrieved in group `A`.

### Bytecode-Level Verification

~~~sh
javap -c -p NoInitTriggersDemo
~~~

Look in the `main` method for:

- `ldc` for class literals and string literals.
- `anewarray` for the reference array allocation operation.
- The values of `RETRIES` and `MODE` used directly at the call site; no `getstatic` is needed for those two constant variables.
- `getstatic` for `ComputedValue.COUNT` and `CompileTimeConstants.BOXED`.

The opcodes observed with `javac` help explain why the code behaves this way; the **JLS specification** is the authoritative source of rules for when initialization occurs. Do not infer every JVM detail from a single opcode.

## 7. Small Experiments to Isolate Causes

**Experiment 1 — Array with an element initialized immediately:** change `new ArrayElement[3]` to `new ArrayElement[]{new ArrayElement(), null, null}`. The `INIT ArrayElement` line moves up to group `B`, because `new ArrayElement()` is now in the element expression.

**Experiment 2 — Changing a nonconstant to a constant:** change `static final int COUNT = Integer.parseInt("9");` to `static final int COUNT = 9;` and **recompile**. Reading `COUNT` no longer by itself triggers the initializer; `INIT ComputedValue` disappears from this program.

**Experiment 3 — Replacing only `class literal` with an instance:** keep `FromLiteral.class`, and add `new FromLiteral();` right below it. The `FromLiteral` class is initialized on that instance-creation line; the class literal is still not the trigger.

**Experiment 4 — Reflection:** compare `Class.forName("NoInitTriggersDemo$FromLiteral", false, loader)` with the `true` flag (where `loader` is the defining loader of `NoInitTriggersDemo`). The `false`-flag overload does not require initialization; the `true` flag does. Place the test before any `new FromLiteral()` to observe the difference.

**Observation note:** launch a **new JVM** for each case that requires an uninitialized class state. Repeating tests in the same JVM after initialization has occurred will not make `static {}` print again, easily leading to wrong conclusions.

## 8. Misconceptions to Avoid

1. **"Not initialized" means "not loaded."** False: class literals and array allocation can force the JVM to work with class information without initializing the target class.
2. **"`new Sample[3]` creates three `Sample` instances."** False: it only creates an array of three `null` slots.
3. **"The array contains `new Sample()`, so creating the array itself causes initialization."** False: it is the **instance** creation that causes initialization.
4. **"Any `final` or `static final` gets inlined."** False: primitive/`String` type and a constant expression are mandatory criteria.
5. **"`Integer` is a number, so `static final Integer` is a constant variable."** False: `Integer` is a reference type.
6. **"The name to the left of the dot determines the exact class to be initialized."** False for inherited fields; you must look at the class that actually **declares** the field.
7. **"Interface fields never trigger initialization."** False: an interface field that is not a constant variable can cause the interface to be initialized when read.
8. **"`Class.forName` is always the same as `Target.class`."** False: the single-parameter overload requires initialization.
9. **"Not seeing the initializer log means the class has never been initialized."** False if the class was initialized earlier; you must observe on a fresh JVM and attach the log to the right class.
10. **"Changing a constant's value in a JAR makes all clients automatically pick up the new value."** False if the client already inlined it and has not been recompiled.

## 9. Review Questions

1. State the difference between loading, linking, and initialization. Why does `Sample.class` not prove that the `static {}` block has run?
2. Why does `new Sample[4]` not create four `Sample` objects?
3. In `Sample[] data = {new Sample()};`, which operation causes initialization?
4. Classify `static final int A = 5;`, `static final int B = parse();`, and `static final Integer C = 5;` into constant/nonconstant variables.
5. When reading `Child.X` where `X` is a nonconstant static field declared in `Parent`, which class is the target of the trigger?
6. How do reading `Options.PORT` and `Options.MODE` on the interface in Section 5 differ?
7. Why does `INIT CompileTimeConstants` appear in group `E` but not in group `C` of the program?
8. In what scenario is `Class.forName(name, false, loader)` more appropriate than `Class.forName(name)` when you only want to observe class lookup?
9. A program has already printed `INIT Sample`, then runs `new Sample()` again without printing it again: is this normal?
10. Why might changing a public compile-time constant in a library require recompiling clients?

**Lesson completed when:** you can accurately predict stdout, explain the three operations that do not trigger initialization, and distinguish a *constant variable* from `static final` fields that are not compile-time constants.

## 10. Official References

- [JLS Java SE 21 12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1): initialization triggers, such as superclasses, static fields, and interfaces.
- [JLS Java SE 21 4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4): definition of a constant variable.
- [JLS Java SE 21 15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29): valid constant expressions.
- [JLS Java SE 21 13.4.9 — final Fields and Constants](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.9): compilation consequences when a constant value changes.
- [Java SE 21 Class.forName API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): the `initialize` parameter.

The examples use APIs and syntax compatible with Java 17 and later; the rules on initialization timing are presented according to the Java Language Specification.
