# Textual Order of `static` Fields and `static` Blocks in Java

In Java, a class can declare multiple **static fields** interleaved with **static initializer blocks (`static { ... }`)**. When the class is initialized, Java executes the field initializers and static blocks in the **order they appear in the source text**, but there are several foundational rules to understand first: default values, constant variables, forward-reference restrictions, class initialization triggers, and superclass–subclass order.

Example:

~~~java
class Settings {
    static int first = 2;

    static {
        System.out.println("block 1: " + first);
    }

    static int second = first + 3;

    static {
        System.out.println("block 2: " + second);
    }
}
~~~

When `Settings` is **actually initialized**, the `first` field is assigned 2; the first block sees 2; the `second` field receives 5; the second block sees 5. However, merely **declaring** the class does not mean static blocks will run immediately; code must trigger the class initialization process.

Lesson goal: accurately analyze **“which field initializer runs first, which block runs later, and whether a field has already received its new value at the moment it is read?”** instead of mechanically memorizing “static runs first”.

This content belongs to Java Core — **Class & Object / Initialization Order**, using Java 17+. Complete programs include the file name, `javac`, `java`, and stdout. Snippets that intentionally fail to compile are marked separately.

## 1. Learning Outcomes

After this lesson, you should be able to:

1. Distinguish between **class loading, linking/preparation, and initialization** at a sufficient level to read static code.
2. Understand that a normal static field has a **default value** before an initializer explicitly assigns a value.
3. Describe the **top-to-bottom order** of static field initializers and `static { ... }` within the same class.
4. Know that each runtime class is initialized according to Java rules and does not re-run static initializers each time an additional instance is created.
5. Predict the stdout of programs that print logs across multiple static fields/blocks.
6. Explain when the compiler reports an **illegal forward reference**.
7. Distinguish between fields accessed via a **simple name**, via a **qualified name**, and via a **method**.
8. Understand why a method can read a field declared after it and see the **default value**.
9. Distinguish a **constant variable** (`static final` primitive/String with a constant expression) from other static final fields.
10. Understand why reading a compile-time constant does not necessarily trigger class initialization.
11. Trace the order between **superclass and subclass**, as well as between static and instance initializers.
12. Read static initialization errors, and avoid circular initialization and unintended side effects.
13. Know when static blocks/fields are appropriate, and when to extract to a factory or lazy initialization.
14. Test initialization scenarios based on semantics rather than relying on the IDE environment.

## 2. Distinguishing Four Easily Conflated Concepts

| Concept | Main Meaning | Does It Run Static Initializers? |
| --- | --- | --- |
| **Loading** | The JVM finds and creates a representation of the class/interface | Does not by default mean they have run |
| **Linking / preparation** | Verifies and prepares class variables; sets prepared values according to VM rules | Not the phase that runs static blocks sequentially |
| **Initialization** | Executes the class initialization procedure; field initializers/static blocks according to Java semantics | **Yes**, this is the central phase |
| **Instance initialization** | Prepares and initializes each specific object when creating an instance | Not static initializers running again |

Saying “as soon as the JVM encounters a class name, its static block runs immediately” is **inaccurate**. The JVM can load/link a class first without initializing it yet. Conversely, there are active uses of a class that require initialization to occur before proceeding.

### Important Rule

> Within a class, after special handling for **constant variables**, Java executes static field initializers and static initializer blocks in the **textual order** of their declarations in the source code.

The difference between the field preparation phase and the time initializers run explains why a static field read too early can still hold its **default value**. However, one must not assert that every static final compile-time constant also holds only 0/null up until its exact declaration line: **constant variables have their own initialization rules**.

## 3. Syntax of Static Field Initializers and Static Initializer Blocks

A static field can be initialized directly in its declaration:

~~~java
class AppConfig {
    static int maxUsers = 100;
    static String mode = "development";
}
~~~

A static initializer block:

~~~java
class AppConfig {
    static int maxUsers;

    static {
        maxUsers = 100;
        System.out.println("AppConfig initialized");
    }
}
~~~

These are **two illustrative classes in two independent approaches**; do not merge the two snippets into a single `AppConfig` declaration.

A `static { ... }` block is code executed during the **class initialization process**, not a named method. It takes no parameters, has no return value, and cannot use an instance's `this`.

A class can have **multiple static blocks**, interleaved among multiple static field declarations. Within the same class, **source position** determines the execution order of the initializers belonging to normal initialization.

## 4. The Most Important Rule: Interleaved in Textual Order

Consider the illustrative class:

~~~java
class Demo {
    static int a = 1;

    static {
        System.out.println("A=" + a);
    }

    static int b = a + 2;

    static {
        System.out.println("B=" + b);
        b += 5;
    }

    static int c = b * 2;
}
~~~

Order:

1. Initializer `a = 1`.
2. The first static block reads `a` and prints `A=1`.
3. Initializer `b = a + 2`, giving `b = 3`.
4. The second static block prints `B=3`, then updates `b = 8`.
5. Initializer `c = b * 2`, giving `c = 16`.

The JVM does not run **all field initializers first** and then run **all static blocks**. If it did, the result would be different; Java uses source order when executing those normal static declarations.

**Ask the right questions:** “Does this line appear before or after any static block in the source?” and “At what point was the class actually initialized?”

## 5. Complete Runnable Example: Logging Each Static Initializer

Create the file **`StaticTextualOrderDemo.java`**:

~~~java
public class StaticTextualOrderDemo {
    static class Sample {
        static int alpha = mark("field alpha", 3);

        static {
            System.out.println("block 1: alpha=" + alpha);
            alpha += 2;
        }

        static int beta = mark("field beta", alpha * 2);

        static {
            System.out.println("block 2: beta=" + beta);
            beta++;
        }

        static int gamma = mark("field gamma", beta + alpha);

        static int mark(String label, int value) {
            System.out.println(label + "=" + value);
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("main begins");
        System.out.println("gamma=" + Sample.gamma);
        System.out.println("alpha=" + Sample.alpha);
        System.out.println("beta=" + Sample.beta);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StaticTextualOrderDemo.java
java StaticTextualOrderDemo
~~~

Stdout:

~~~text
main begins
field alpha=3
block 1: alpha=3
field beta=10
block 2: beta=10
field gamma=16
gamma=16
alpha=5
beta=11
~~~

### State Table After Each Step

| Step in `Sample` | `alpha` | `beta` | `gamma` | Action |
| --- | ---: | ---: | ---: | --- |
| Defaults of static ints | 0 | 0 | 0 | Initial values before normal initializers |
| `alpha = mark(...,3)` | 3 | 0 | 0 | Prints `field alpha=3` |
| Block 1 | 5 | 0 | 0 | Prints alpha=3, adds 2 |
| `beta = mark(...,alpha*2)` | 5 | 10 | 0 | Prints `field beta=10` |
| Block 2 | 5 | 11 | 0 | Prints beta=10, then ++ |
| `gamma = mark(...,beta+alpha)` | 5 | 11 | 16 | Prints `field gamma=16` |
| After initialization | 5 | 11 | 16 | Main prints the three values |

At the beginning of `main`, the nested class `Sample` does not yet need to be initialized; the print statement for `main begins` runs first. When the expression `Sample.gamma` is used, Java initializes `Sample` and runs the entire log sequence in order. Reading `Sample.alpha`/`beta` **afterward** does not cause the static code to run again.

The `mark` method **can be declared at the end of the class** and still be called in an initializer at the top; the difference between a forward reference of a **field** and calling a **method** will be explained in detail below.

## 6. Default Values Before Explicit Value Assignment

Class variables are fields, so they have **default values** according to their data types when prepared under Java/JVM rules:

| Field Type | Normal Default Value |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` of the corresponding type |
| `float`, `double` | positive zero of the corresponding type |
| `char` | NUL character `'\\u0000'` |
| `boolean` | `false` |
| Reference types such as `String`, `List`, arrays | `null` |

Example:

~~~java
class Settings {
    static int count;
    static boolean enabled;
    static String title;
}
~~~

If there is no initializer or other assignment, after normal class initialization: `count == 0`, `enabled == false`, `title == null`.

**Distinction:** A local variable in a method **does not** automatically read a similar default value if it has not been definitely assigned. For example, local `int n; System.out.println(n);` is a compile-time error.

### Special Exception for Constant Variables

A `static final int LIMIT = 10;` initialized with a constant expression belongs to the **constant variables** group. Java handles this group before normal static initializers; reading them should not be interpreted as “guaranteed to see 0 up until the LIMIT line in the source”. Therefore, the default values table is most useful when analyzing **non-constant static fields**.

## 7. Class Initialization Runs Once Under Normal Conditions

Consider:

~~~java
class Gateway {
    static int requests = 0;

    static {
        System.out.println("Gateway initialized");
    }

    Gateway() {
        requests++;
    }
}
~~~

After:

~~~java
Gateway a = new Gateway();
Gateway b = new Gateway();
~~~

Two `new` calls invoke the constructor for two instances, so the static field `requests` increments twice. However, the static block **does not** run again for each object. In a runtime class that has already been successfully initialized, the initialization procedure is not executed again by subsequent object creations.

### Do Not Infer That “static Has a Permanent Lifetime”

A runtime class can have a lifecycle related to the class loader and the application environment; two classes with the same name defined by different class loaders can have separate static states. For a small single-JVM program using a normal class loader, the model “the static initializer runs once for this class” is sufficient.

## 8. Runnable Example: Static Blocks and Constructors Differ

Save the file **`StaticVersusInstanceDemo.java`**:

~~~java
public class StaticVersusInstanceDemo {
    static class Gadget {
        static int nextId = 1;

        static {
            System.out.println("Gadget static block");
        }

        final int id;

        {
            System.out.println("Gadget instance block");
        }

        Gadget() {
            id = nextId++;
            System.out.println("constructor id=" + id);
        }
    }

    public static void main(String[] args) {
        System.out.println("start");
        new Gadget();
        new Gadget();
        System.out.println("nextId=" + Gadget.nextId);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticVersusInstanceDemo.java
java StaticVersusInstanceDemo
~~~

Stdout:

~~~text
start
Gadget static block
Gadget instance block
constructor id=1
Gadget instance block
constructor id=2
nextId=3
~~~

- The `nextId` static field initializer runs when Gadget is initialized for the first time.
- The static block prints exactly **once**.
- The instance initializer block runs **each time a Gadget is created**.
- The constructor body also runs for **each Gadget instance**.
- Reading static `Gadget.nextId` at the end does not re-run the static block.

Both static fields and static blocks belong to the **class initialization** process; instance fields and non-static initializer blocks belong to the **instance initialization** process. These two concepts are not interchangeable.

## 9. Illegal Forward Reference: Why Can't a Later Field Be Read by Simple Name?

Try declaring:

~~~java
class Invalid {
    // static int earlier = later; // Error: illegal forward reference.
    static int later = 10;
}
~~~

If uncommented, the compiler rejects it because within a **static field initializer of the same class**, a **simple name** `later` refers to a field declared **after** the read location and does not fall under an allowed exception.

Similarly:

~~~java
class Invalid {
    static {
        // System.out.println(later); // Error: illegal forward reference.
    }

    static int later = 10;
}
~~~

The intentionally invalid line is commented out so that the remaining snippets are valid.

### Why Does Java Restrict This?

If direct reading of any field declared later were allowed, a developer might easily assume that field's initializer had already run. In reality, the read could see the default value. The rule restricting **simple-name forward references in certain static initialization contexts** aims to prevent accidental bugs, even though it does not block every indirect way of reading.

**Do not memorize the rule of thumb “Java forbids mentioning any member declared below”.** Java allows calling a method declared below, and certain ways of referencing a field using a qualified name remain valid.

## 10. Distinguishing Between Simple Names and Qualified Names

An advanced but very useful point:

~~~java
class QualifiedExample {
    static int observed = QualifiedExample.later;
    static int later = 10;
}
~~~

In the initializer of `observed`, the expression `QualifiedExample.later` is a **qualified name**. It differs from `later`, which is a simple name under the illegal forward reference rule being examined.

This example can compile. When `observed` is initialized, `later` **has not yet executed its `= 10` initializer**, so reading the non-constant `later` here yields `0`. Afterward, the initializer `later = 10` runs.

### Runnable Example

Create the file **`QualifiedForwardReadDemo.java`**:

~~~java
public class QualifiedForwardReadDemo {
    static class Example {
        static int observed = Example.later;
        static int later = 10;

        static {
            System.out.println("observed=" + observed);
            System.out.println("later=" + later);
        }
    }

    public static void main(String[] args) {
        System.out.println("main=" + Example.later);
    }
}
~~~

~~~bash
javac -encoding UTF-8 QualifiedForwardReadDemo.java
java QualifiedForwardReadDemo
~~~

Stdout:

~~~text
observed=0
later=10
main=10
~~~

**Important:** Just because this code compiles does not mean you should write it this way in a real application. It creates a dependency sensitive to declaration order and can surprise readers. You should **place the dependency's initializer above where it is used**, or design explicit initialization when the logic is complex.

## 11. A Method Called from an Initializer Can Read a Field Declared Later

The simple-name forward reference rule examines the location of the **field access expression** inside the initializer. If an initializer **calls a method**, and that method reads the field, it can be syntactically valid because the read occurs inside the **method body**, not directly inside the initializer under the prohibited condition.

Example:

~~~java
class Indirect {
    static int observed = readLater();
    static int later = 10;

    static int readLater() {
        return later;
    }
}
~~~

The method `readLater()` has already been declared and can be called when `observed` is initialized. However, at that moment, `later` has not yet been assigned 10 in textual order, so the method receives the **default value 0**.

This creates a “valid yet dangerous trap”: the code **has no compile error**, but the value may differ from expectations.

### Runnable Example

Save the file **`MethodForwardReadDemo.java`**:

~~~java
public class MethodForwardReadDemo {
    static class Example {
        static int observed = readLater();

        static int later = 10;

        static int readLater() {
            System.out.println("inside method later=" + later);
            return later;
        }

        static {
            System.out.println("observed=" + observed);
            System.out.println("later=" + later);
        }
    }

    public static void main(String[] args) {
        System.out.println("final observed=" + Example.observed);
    }
}
~~~

~~~bash
javac -encoding UTF-8 MethodForwardReadDemo.java
java MethodForwardReadDemo
~~~

Stdout:

~~~text
inside method later=0
observed=0
later=10
final observed=0
~~~

Analysis:

1. Class `Example` begins initialization; normal static ints have a default value of 0.
2. `observed = readLater()` calls the method.
3. The method reads `later` before the `later = 10` initializer has run, so it prints 0 and returns 0.
4. Afterward, `later = 10`.
5. The static block prints `observed=0` and `later=10`.
6. Reading `Example.observed` after initialization is still 0; it **does not recalculate automatically**.

You should not use this approach to “bypass” the compiler's illegal forward reference check in production code. If the code means that observed must equal later=10, arrange the dependencies in the proper order or write direct, clear initialization.

## 12. Default Values When a Static Field Has Not Yet Reached Its Initialization Turn

In a program with multiple fields, tabulate according to three states:

1. **Default:** the field already has its prepared value under VM rules, but its normal initializer has not yet run.
2. **Initialized:** the field's initializer has run and completed.
3. **Mutated:** another static block/method may modify the field afterward.

Example:

~~~java
class State {
    static int first = 3;
    static int second = first * 2;

    static {
        first = 10;
    }

    static int third = first + second;
}
~~~

Result:

| Step | first | second | third |
| --- | ---: | ---: | ---: |
| Before normal initializers | 0 | 0 | 0 |
| `first = 3` | 3 | 0 | 0 |
| `second = first * 2` | 3 | 6 | 0 |
| Static block | 10 | 6 | 0 |
| `third = first + second` | 10 | 6 | 16 |

What is easy to overlook is that `second` **does not recalculate automatically** when `first` changes to 10. A field initializer is **an assignment action at a single point in time**, not a spreadsheet formula continuously depending on `first`.

## 13. A Static Block Can Reassign a Static Field Declared Above

A non-final static field can be modified multiple times across static blocks:

~~~java
class Flags {
    static String mode = "default";

    static {
        mode = "ready";
    }

    static {
        mode = mode.toUpperCase();
    }
}
~~~

After successful class initialization, `Flags.mode` is `"READY"`. There is no “separate copy” per block: both blocks and the initializer operate on the **same static field**.

However, a `final` field has strict assignment rules. You cannot initialize a final field and then arbitrarily reassign it in a subsequent block:

~~~java
class InvalidFinal {
    static final int LIMIT = 10;

    static {
        // LIMIT = 20; // Invalid: the final field has already been assigned.
    }
}
~~~

## 14. A Blank `static final` Can Be Assigned in a Static Block

A **blank static final field** is a static final field without a direct initializer at its declaration:

~~~java
class Tokens {
    static final String PREFIX;

    static {
        PREFIX = "ID-";
    }
}
~~~

In this context, a constructor makes no sense for a static final field, because the field belongs to the class rather than to an instance. Set up a blank static final according to **definite assignment rules** during static initialization, typically directly inside a static block.

### Runnable Example with Multiple Static Blocks

Create the file **`BlankStaticFinalDemo.java`**:

~~~java
public class BlankStaticFinalDemo {
    static class TokenConfig {
        static final String PREFIX;

        static {
            PREFIX = "ID-";
            System.out.println("prefix assigned");
        }

        static int number = 5;

        static {
            System.out.println("second block: " + PREFIX + number);
        }
    }

    public static void main(String[] args) {
        System.out.println("result=" + TokenConfig.PREFIX + "42");
    }
}
~~~

~~~bash
javac -encoding UTF-8 BlankStaticFinalDemo.java
java BlankStaticFinalDemo
~~~

Stdout:

~~~text
prefix assigned
second block: ID-5
result=ID-42
~~~

`PREFIX` is assigned once in the first static block. `number = 5` runs after that block and before the second static block. `PREFIX` is not a compile-time constant variable in this example because it does not have a constant-expression initializer directly at the field declaration; therefore, accessing it from main triggers initialization.

**Key takeaway:** A blank static final field can be assigned in a valid initializer block, but you cannot allow an initialization path to read it before definite assignment or assign it a second time. Do not use a blank final as mutable state.

## 15. `static final` Constant Variables Have Their Own Rules

Example:

~~~java
class Limits {
    static final int MAX = 10;
    static final String PREFIX = "X-";
}
~~~

These two fields are candidates for **constant variables**: a final field of primitive or String type, initialized with **constant expressions**.

They have several differences:

- Constant variables are initialized before normal static initializers during class initialization according to Java rules.
- Reading a constant variable from another class **does not necessarily trigger** initialization of the declaring class.
- The compiler can **inline** the value when compiling the client.
- A risk of a stale version of the constant appearing in client bytecode that has not been recompiled may arise.

Conversely:

~~~java
static final Integer BOXED = Integer.valueOf(10);
static final int COMPUTED = compute();
static final java.time.Duration TIMEOUT =
        java.time.Duration.ofSeconds(5);
~~~

are not constant variables under the same rules merely because they have `static final`: Integer/Duration are reference objects (not a String constant variable), and the method call `compute()` is not a constant expression.

## 16. Runnable Example: A Constant May Not Trigger a Static Block

Create the file **`ConstantInitializationDemo.java`**:

~~~java
public class ConstantInitializationDemo {
    static class Config {
        static final int LIMIT = 10;
        static final String LABEL = "Java";
        static final Integer BOXED = Integer.valueOf(20);

        static {
            System.out.println("Config static block");
        }
    }

    public static void main(String[] args) {
        System.out.println("limit=" + Config.LIMIT);
        System.out.println("label=" + Config.LABEL);
        System.out.println("boxed=" + Config.BOXED);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstantInitializationDemo.java
java ConstantInitializationDemo
~~~

Stdout:

~~~text
limit=10
label=Java
Config static block
boxed=20
~~~

The first two lines use the compile-time constant variables `LIMIT` and `LABEL`. In this program, merely reading them does not cause `Config` to run its static block. When reading `BOXED` — which is not a constant variable — class `Config` is initialized and prints `Config static block` before the `boxed=20` line.

**Common mistake:** “Whenever encountering `ClassName.FIELD`, Java runs the static block”. That is not true for cases where a constant variable is used as shown above.

## 17. A Constant Variable Can Be Read Early and Still Hold Its Constant Value

In the section on forward reads, a non-constant static int normally yields the default value when an initializer further down has not yet run. However, **constant variables are a different case**.

Example:

~~~java
class Example {
    static int observed = readConstant();
    static final int LIMIT = 7;

    static int readConstant() {
        return LIMIT;
    }
}
~~~

`LIMIT` is a compile-time constant variable. Reading `LIMIT` in the method can be compiled as using the value 7; it is unlike reading a normal static field whose initializer has not yet run.

At the time of class initialization, Java handles constant variables before normal static field initializers, so the mechanical inference “a field located below must still be 0” must not be applied to `LIMIT`.

### Runnable Example

Save **`ConstantForwardReadDemo.java`**:

~~~java
public class ConstantForwardReadDemo {
    static class Example {
        static int observed = readConstant();
        static final int LIMIT = 7;

        static int readConstant() {
            return LIMIT;
        }

        static {
            System.out.println("observed=" + observed);
            System.out.println("LIMIT=" + LIMIT);
        }
    }

    public static void main(String[] args) {
        System.out.println("main=" + Example.observed);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstantForwardReadDemo.java
java ConstantForwardReadDemo
~~~

Stdout:

~~~text
observed=7
LIMIT=7
main=7
~~~

In this snippet, `readConstant()` is called before the LIMIT declaration line in normal initializer order, yet the constant variable has the value 7. The result differs from the `readLater()` example that read a **non-constant static field** whose initializer turn had not yet arrived and saw 0.

**Distinguish carefully:** Reading this constant value does not mean that the `readConstant()` method can never involve class initialization in every context; in this example, initialization was triggered by `Example.observed` in main.

## 18. What If a Static Field Is Only Declared Without an Initializer?

If you write:

~~~java
class Counters {
    static int hits;
    static String latest;
}
~~~

then there is no explicit field initializer to run separately for `hits` or `latest`. The fields are set to their default values under VM rules and remain so until code performs an assignment later.

`Counters.hits` can be read as 0 and `Counters.latest` as null when the class is used normally.

Adding a static block:

~~~java
class Counters {
    static int hits;

    static {
        hits = 1;
    }
}
~~~

then after successful initialization, `hits == 1`. If other code updates `hits` afterward, the value changes — textual initialization order only explains the **initialization phase**, and does not freeze a static field for life.

## 19. Declaration Order and Method Order: Do Not Equate Them

Compare:

~~~java
class Example {
    static int x = calculate();

    static int calculate() {
        return 5;
    }
}
~~~

Valid. Calling the method `calculate()` before the position of the method declaration in the source **does not cause** an illegal forward reference like reading a simple-name field too early.

In Java, method declarations do not operate like “a script where functions must be defined before being called” by line order; the compiler knows the class's method signatures. However, **when the method is called** still matters greatly: if the method reads a static field that has not yet been assigned an explicit initializer, it may see the default value.

### When Does the Method Body Run?

~~~java
static int a = method();

static int method() {
    System.out.println("method executed");
    return 3;
}
~~~

The `method` method runs **right at the time the initializer `a = method()` is executed**, not when the compiler reads the method declaration. The **execution** order comes from the call in the initializer.

## 20. When a Static Initializer Affects a Later Field

Not only can it read early; a static block can also **write** to a field declared below, depending on the applicable forward-reference/assignment rules.

Example:

~~~java
class Example {
    static {
        future = 4;
    }

    static int future = 9;
}
~~~

Assigning to the simple name `future` on the left-hand side of an assignment has an exception in the forward-reference rule; this illustrative snippet can compile. However, after the block, the initializer `future = 9` runs and **overwrites** the value 4. Therefore, the final value is 9, not 4.

### Runnable Program

Create the file **`ForwardWriteDemo.java`**:

~~~java
public class ForwardWriteDemo {
    static class Example {
        static {
            future = 4;
            System.out.println("assigned future in block");
        }

        static int future = 9;

        static {
            System.out.println("later future=" + future);
        }
    }

    public static void main(String[] args) {
        System.out.println("final=" + Example.future);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForwardWriteDemo.java
java ForwardWriteDemo
~~~

Stdout:

~~~text
assigned future in block
later future=9
final=9
~~~

**Note:** You should not use “write first, initializer below overwrites” as an intentional design. This is an example of the forward-assignment mechanism. If the logic requires a clear order, write initializers in an easy-to-understand, one-way dependency order.

## 21. When Is a Class Initialized?

A class or interface is not always initialized just because the JVM has loaded it. Active uses of a class can normally trigger initialization, for example:

- Creating an instance with `new ClassName()`.
- Calling a static method declared by the class.
- Reading/writing a static field declared by the class, except for the special case of a constant variable.
- Situations involving reflective invocation or using the class according to VM-specified mechanisms.

To measure the order in examples, you should place the class with static blocks as a **nested static class** or a separate class, and then trigger it on a controlled line from `main`.

### Which Example Easily Causes Misunderstanding?

If the file has:

~~~java
public class Main {
    static {
        System.out.println("Main initialized");
    }

    public static void main(String[] args) {
        System.out.println("main called");
    }
}
~~~

The static block of **Main itself** runs before the `main` body, because the Main class must be initialized to call main under normal execution conditions. However, that **does not mean every class mentioned in Main's source has already run its static blocks**.

## 22. Runnable Example: Do Not Confuse Main Class Initialization with a Nested Class

Save **`MainAndNestedInitDemo.java`**:

~~~java
public class MainAndNestedInitDemo {
    static {
        System.out.println("outer init");
    }

    static class Nested {
        static {
            System.out.println("nested init");
        }

        static int value = 42;
    }

    public static void main(String[] args) {
        System.out.println("main body");
        System.out.println("nested value=" + Nested.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 MainAndNestedInitDemo.java
java MainAndNestedInitDemo
~~~

Stdout:

~~~text
outer init
main body
nested init
nested value=42
~~~

Explanation:

1. The main class must be initialized to execute `main`, so it prints `outer init`.
2. The `main` body starts and prints `main body`.
3. Reading `Nested.value` (a non-constant static int) requires initializing `Nested`, causing `nested init` to be printed.
4. Afterward, the expression reads the value 42 and prints `nested value=42`.

There is no relationship where “every static nested class automatically initializes at the same time as outer”. Each nested class is a runtime class with its own initialization lifecycle.

## 23. Inheritance: Superclass Initializes Before Subclass

When a class `Child extends Parent` must be initialized, Java ensures that the appropriate superclass is initialized before the subclass according to class initialization rules.

Example:

~~~java
class Parent {
    static int p = 1;

    static {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    static int c = 2;

    static {
        System.out.println("Child");
    }
}
~~~

If the program accesses `Child.c` in a way that triggers Child initialization, Parent's static initialization must complete appropriately before running Child's static initialization.

### Order Table

| Scope | Basic Order |
| --- | --- |
| Parent | Parent's static field initializers and static blocks in source order |
| Child | Child's static field initializers and static blocks in source order |
| Creating a Child instance | After the necessary class initializations, instance initialization follows constructor/superclass rules |

Do not merge all static fields of both classes into a single list sorted by file name, when the file was written, or alphabetical order. You must consider **the superclass → subclass dependency order**, and then **the textual order within each class**.

## 24. Runnable Example: Parent and Child Order

Create **`InheritanceStaticInitDemo.java`**:

~~~java
public class InheritanceStaticInitDemo {
    static int mark(String text, int number) {
        System.out.println(text + "=" + number);
        return number;
    }

    static class Parent {
        static int parentValue = mark("Parent.field", 1);

        static {
            System.out.println("Parent.block");
        }
    }

    static class Child extends Parent {
        static int childValue = mark("Child.field", 2);

        static {
            System.out.println("Child.block");
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        System.out.println("child=" + Child.childValue);
        System.out.println("parent=" + Parent.parentValue);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InheritanceStaticInitDemo.java
java InheritanceStaticInitDemo
~~~

Stdout:

~~~text
before
Parent.field=1
Parent.block
Child.field=2
Child.block
child=2
parent=1
~~~

`Child.childValue` triggers initialization of Child. The JVM ensures Parent is initialized first; then Child executes its own static declarations in textual order. When main reads `Parent.parentValue` at the end, Parent has already been initialized, so its static block does not print again.

### A Notable Exception

Reading an **inherited static field** through a subclass name may only initialize the **class that declares the field**, not necessarily the subclass. For example, if `Child` does not declare `shared` and inherits `Parent.shared`, then `Child.shared` actually refers to the field declared in Parent. When you need to deduce which class initializes, identify the **class that actually declares the static member**, not just the class qualifier written in the source.

## 25. Static Initialization Differs from Instance Initialization in Inheritance

With `new Child()`, there are two layers of order to analyze:

1. Class initialization: the necessary superclasses, then the subclass.
2. Instance construction: the instance portion of the superclass and its constructor, then the instance portion of the subclass and its constructor, according to Java rules.

For each class during instance creation, **instance field initializers and instance initializer blocks** are processed in their textual order at the appropriate stage, rather than arbitrarily interleaving with class initialization.

### Runnable Example Illustrating Both Types

Create the file **`ClassAndObjectInitDemo.java`**:

~~~java
public class ClassAndObjectInitDemo {
    static class Parent {
        static {
            System.out.println("Parent static");
        }

        {
            System.out.println("Parent instance");
        }

        Parent() {
            System.out.println("Parent constructor");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child static");
        }

        {
            System.out.println("Child instance");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        new Child();
        System.out.println("again");
        new Child();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassAndObjectInitDemo.java
java ClassAndObjectInitDemo
~~~

Stdout:

~~~text
begin
Parent static
Child static
Parent instance
Parent constructor
Child instance
Child constructor
again
Parent instance
Parent constructor
Child instance
Child constructor
~~~

The first creation of Child triggers initialization of class Parent and then Child; afterward, the object is created following the constructor chain. The second time, class initialization has already completed, so only the instance blocks and constructors run again. This is completely different from two static blocks interleaved within **the same class**, which was the initial focus of textual order.

## 26. When a Static Initializer Calls a Method of Another Class

A field initializer can call a method of class B:

~~~java
class A {
    static int data = B.load();
}

class B {
    static int load() {
        return 5;
    }
}
~~~

In the example, initializing A upon reaching `data = B.load()` can trigger initialization of B if B has not yet been initialized. Once B is ready, the `load` method runs and returns 5; A continues to completion.

**Key point:** Textual order is a rule **within each class**, but the process can **branch off to initialize another class** right at a method-call or field-read step. Therefore, logs from multiple classes can interleave along the dependency path, rather than appearing only as large separate blocks.

### What to Avoid

Creating static initializers with cross-dependencies across multiple classes makes code hard to predict. Class A reading B, B reading C, and C reading A can lead to a **partially initialized state** or liveness errors if multiple threads and locks are involved. Reorganize dependencies so that initialization is simple, one-way, and easy to test.

## 27. Circular Initialization: Static Fields Can Observe Incomplete State

If A needs B while initializing and B in turn reads A, VM rules can reveal the static fields of a class that is currently initializing but **has not finished running** its initializers.

Example:

~~~java
class A {
    static int value = B.value + 1;
}

class B {
    static int value = A.value + 1;
}
~~~

When **the same thread** begins initialization from A, the following can occur:

1. A.value is at default 0; A's initializer needs `B.value`.
2. B begins initializing; B's initializer needs `A.value`.
3. Because A is already being initialized by **the same thread**, the recursive request does not re-run A's entire initializer and can observe the current `A.value` as 0.
4. B.value becomes 1.
5. A resumes and assigns `A.value = 2`.

### Runnable Example

Create the file **`CircularStaticInitDemo.java`**:

~~~java
public class CircularStaticInitDemo {
    static class A {
        static int value = B.value + 1;
    }

    static class B {
        static int value = A.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("A=" + A.value);
        System.out.println("B=" + B.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 CircularStaticInitDemo.java
java CircularStaticInitDemo
~~~

Stdout:

~~~text
A=2
B=1
~~~

**Do not treat this example as a design pattern.** The result depends on the initialization starting point: if B is actively initialized first in another program, the order and values may differ. Textual order still holds within each class, but a circular dependency requires considering the entire class-init graph to predict the outcome.

In a multithreaded environment, circular class initialization can also create mutual-waiting risks. Prioritize decoupling dependencies and reducing side effects in static initialization.

## 28. Static Initialization and Exceptions

A static field initializer or static block can **fail**:

~~~java
class Broken {
    static int value = fail();

    static int fail() {
        throw new IllegalStateException("configuration unavailable");
    }
}
~~~

When initializing Broken, the exception can cause the JVM to report `ExceptionInInitializerError` with `IllegalStateException` as the root cause. The class may be marked in an **erroneous** state in the class runtime. Subsequent uses may report `NoClassDefFoundError` instead of attempting to initialize again.

This is important when reading logs: `NoClassDefFoundError` after a failed init can be a **secondary consequence**, not “the class file mysteriously disappearing”.

### Do Not Use Static Blocks for Heavy Operations

Error-prone tasks such as making network calls, opening database connections, reading multiple files, or initializing resources with complex lifecycles should usually have **explicit setup and error handling** instead of executing arbitrarily in a static initializer.

A static init error can affect the entire runtime class, making retries and test isolation difficult.

## 29. Runnable Example: Failure During Class Initialization

Save the file **`StaticInitializationFailureDemo.java`**:

~~~java
public class StaticInitializationFailureDemo {
    static class Broken {
        static int value = load();

        static int load() {
            throw new IllegalStateException("invalid config");
        }
    }

    static void attempt(String label) {
        try {
            System.out.println(Broken.value);
        } catch (Throwable ex) {
            System.out.println(label + "=" +
                    ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        attempt("first");
        attempt("second");
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInitializationFailureDemo.java
java StaticInitializationFailureDemo
~~~

Typical stdout on Java 17:

~~~text
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

When `Broken.value` is accessed for the first time, the JVM initializes Broken and `load()` throws `IllegalStateException`. The initialization error is represented by `ExceptionInInitializerError`. The next time, the runtime class is already in a failed initialization state, so the JVM reports `NoClassDefFoundError`.

**Only in this learning example** do we catch `Throwable` to see both error types; **you should not broadly catch Throwable in applications** to hide serious errors. In a real system, you need to trace the original cause, fix the configuration, and design retry/lifecycle handling at the appropriate layer.

## 30. A Static Block Is Not the Right Place for All Logic

A short static block can be reasonable for building complex immutable lookup data:

~~~java
class ColorCodes {
    static final java.util.Map<String, Integer> CODES;

    static {
        java.util.Map<String, Integer> data =
                new java.util.HashMap<>();
        data.put("RED", 1);
        data.put("GREEN", 2);
        CODES = java.util.Map.copyOf(data);
    }
}
~~~

This is an illustrative class. `CODES` is a final reference to an unmodifiable map snapshot with immutable String keys and Integer values in the example.

However, if a block reads data from the network or registers callbacks in multiple places, initialization order can easily turn into a **hidden** lifecycle system that is hard to test. Better alternatives may be a simple static factory method, an explicit constructor, service setup, or the lazy holder pattern.

### One Thing That Is Incorrect

`static final Map<String, String> map = new HashMap<>();` **is not automatically immutable**, even though the reference is final. If there is a public getter returning the mutable Map or methods that mutate it, the state can change after initialization and affect all callers.

## 31. Lazy Holder: Initializing Resources Only When Actually Needed

One way to defer data initialization is to hold the resource in a separate **static nested class**:

~~~java
class Repository {
    private static class Holder {
        static final java.util.List<String> NAMES =
                java.util.List.of("Mai", "An");
    }

    static java.util.List<String> names() {
        return Holder.NAMES;
    }
}
~~~

Calling `Repository.names()` can initialize Repository and then initialize Holder when the static field Holder.NAMES is used; Holder does not necessarily get initialized as soon as the program first knows the name Repository.

### Runnable Example

Create the file **`LazyHolderDemo.java`**:

~~~java
public class LazyHolderDemo {
    static class Repository {
        static {
            System.out.println("Repository initialized");
        }

        static class Holder {
            static {
                System.out.println("Holder initialized");
            }

            static final java.util.List<String> NAMES =
                    java.util.List.of("Mai", "An");
        }

        static void ping() {
            System.out.println("ping");
        }

        static java.util.List<String> names() {
            return Holder.NAMES;
        }
    }

    public static void main(String[] args) {
        Repository.ping();
        System.out.println("names=" + Repository.names());
        System.out.println("names again=" + Repository.names());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LazyHolderDemo.java
java LazyHolderDemo
~~~

Stdout:

~~~text
Repository initialized
ping
Holder initialized
names=[Mai, An]
names again=[Mai, An]
~~~

`Repository.ping()` triggers Repository initialization, without using Holder. When the first `names()` call accesses `Holder.NAMES`, Holder is initialized separately. The second `names()` call does not re-run the blocks.

**Do not overuse lazy holder:** It is useful when there is a resource worth deferring, but it can cause initialization errors at the time of first use. Define a failure strategy/lifecycle if the initializer is complex.

## 32. Interaction with `static final` and Constant Inlining

An example:

~~~java
public class PublicLimits {
    public static final int MAX_USERS = 100;
}
~~~

A compiled client referencing `PublicLimits.MAX_USERS` may have it replaced by the compiler with the value 100 in the client's bytecode. If the library is changed to 200 and only the library is rebuilt, the old client may still use 100. This is a consequence of **compile-time constants**, not a static initializer that has not yet had a chance to run.

If you want the config to vary by deployment, consider an accessor method:

~~~java
public static int maxUsers() {
    return 100;
}
~~~

The method can be called at runtime and does not undergo the same constant inlining mechanism as a `public static final int` field with a constant expression.

**Do not infer** that every `static final` is inlined. A `static final Integer`, `Duration`, or `String` computed via a method call is not a constant variable under the rules stated above.

## 33. Static Blocks and Hidden Inherited Fields

Suppose:

~~~java
class Parent {
    static int value = 1;
}

class Child extends Parent {
    static int value = 2;
}
~~~

These are **two distinct static fields** because Child declares its own field with the same name (field hiding). Child does not override Parent's field.

If inside Child there is:

~~~java
static {
    System.out.println(value);
    System.out.println(Parent.value);
}
~~~

then the name `value` in Child normally refers to **Child.value** declared in Child, while `Parent.value` is the superclass's field. When determining initialization order, you must distinguish the **field owner** rather than looking only at the matching field name.

Do not use field hiding as a way to organize readable config; it causes confusion about the order and which field is actually read. For static data, accessing through the **declaring class** makes things clearer.

## 34. A Static Initializer Cannot Have `this`

In a static block:

~~~java
class Example {
    int instanceValue = 1;
    static int sharedValue = 2;

    static {
        System.out.println(sharedValue); // Valid.
        // System.out.println(this.instanceValue); // Error.
        // System.out.println(instanceValue);      // Error.
    }
}
~~~

A static context has no instance receiver `this`. To read an instance field, a concrete object is needed:

~~~java
Example example = new Example();
System.out.println(example.instanceValue);
~~~

However, creating an object right inside a static initializer often complicates the initialization graph. Do not create an object just to bypass the absence of `this` if you can use a more appropriate value/config.

### Cannot Return a Value from a Static Block

~~~java
static {
    // return; // Invalid in a static initializer.
}
~~~

A static initializer is not a method. It has no parameter list, return type, or invocation by name from a caller.

## 35. Static Initialization and Checked Exceptions

You cannot arbitrarily let a static initializer block throw an unhandled checked exception:

~~~java
class Config {
    static {
        // throw new java.io.IOException("missing"); // Invalid:
        // a checked exception cannot escape like this from an initializer.
    }
}
~~~

If I/O is needed during initialization, checked exceptions must be handled properly. However, **catching and rethrowing an unchecked exception in a static block** is not necessarily good design, because failure can render the entire runtime class unusable afterward.

Consider an explicit load method:

~~~java
static ConfigData load(java.nio.file.Path path)
        throws java.io.IOException {
    // Read the file and return the result; the caller handles errors.
    return null; // Illustrates the signature, not an actual implementation.
}
~~~

The code above is an **illustrative signature for error handling**, not yet a runnable program; in a real application, there must be a `ConfigData` type and a concrete implementation, without returning null arbitrarily.

## 36. Avoiding Side Effects in Static Initializers

Static initialization runs at the time a class is **actively used**. If a static block:

- Writes files.
- Opens network ports.
- Modifies system properties.
- Registers listeners.
- Starts threads.
- Touches multiple external services.

then a caller that only wants to read a field of the class could accidentally trigger a side effect. This makes tests and runtime startup depend on **who uses the class first**.

### Example of a Design Smell

~~~java
class AppGlobals {
    static {
        System.setProperty("app.mode", "production");
    }
}
~~~

This is a **counterexample snippet**. It alters a process-wide property when AppGlobals is initialized; other tests or modules can be affected without knowing the cause.

Instead of hidden side effects, use **explicit bootstrap/configuration**, with clear ownership and cleanup. In particular, do not let a static initializer inadvertently create a “whoever runs first decides the entire config” situation.

## 37. Test Results Can Depend on Whether the Class Has Already Been Initialized

A test that prints logs and expects a static block to appear every time a test method runs will be unreliable if the test runner keeps the runtime class across tests. Another test might initialize the class first, meaning the static block has already run when the test needs to observe it.

You should not write tests that rely solely on “this class has definitely never been initialized before” in a shared test process unless you genuinely control class loading/lifecycle.

### Reasonable Ways to Test

- Test the final state or public behavior after initialization.
- For initialization order, use a small standalone example class and run it in a controlled process/class-loader when needed.
- Do not rely on arbitrary test method ordering.
- Avoid mutable static global state across tests.
- If initializing external resources, test through an explicit initialization API with fake dependencies.
- When you need to test initialization failures, consider a separate JVM process because the class may be marked erroneous after the first failure.

This is a practical risk of using static blocks for heavy setup: test isolation is more complex than with explicit instance/setup.

## 38. Synthesis Problem: Line-by-Line Trace Within the Same Class

Given:

~~~java
class Calculation {
    static int x = 2;

    static {
        x += 3;
    }

    static int y = x * 2;

    static {
        y = y - x;
        x++;
    }

    static int z = x + y;
}
~~~

Calculate:

- After `x = 2`: x = 2.
- After the first block: x = 5.
- After `y = x * 2`: y = 10.
- The next block: y = 10 - 5 = 5; x = 6.
- After `z = x + y`: z = 11.

Final values: `x=6`, `y=5`, `z=11`.

A common mistake is treating `y = x * 2` as an automatically updating formula when x increases in a later block. In Java, the initializer only runs at the **initialization step**. `y` keeps 10 until it is reassigned to 5 by the subsequent code block.

## 39. Runnable Synthesis Example with Three Static Fields and Two Blocks

Create the file **`StaticTraceExerciseDemo.java`**:

~~~java
public class StaticTraceExerciseDemo {
    static class Calculation {
        static int x = 2;

        static {
            x += 3;
        }

        static int y = x * 2;

        static {
            y = y - x;
            x++;
        }

        static int z = x + y;
    }

    public static void main(String[] args) {
        System.out.println("x=" + Calculation.x);
        System.out.println("y=" + Calculation.y);
        System.out.println("z=" + Calculation.z);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticTraceExerciseDemo.java
java StaticTraceExerciseDemo
~~~

Stdout:

~~~text
x=6
y=5
z=11
~~~

To solve this type of exercise, do not just count fields or blocks. Write **one table row for each initializer/block in exact source order**; each row updates the fields actually affected.

## 40. Comparing a Static Field Initializer with an Instance Field Initializer

Example:

~~~java
class Sample {
    static int a = logStatic();

    int b = logInstance();

    static int logStatic() {
        System.out.println("static");
        return 1;
    }

    int logInstance() {
        System.out.println("instance");
        return 2;
    }
}
~~~

This is an illustrative class. `logStatic` is called during class initialization if the class is initialized; `logInstance` is called **each time a Sample instance is created** after appropriate class initialization. The fact that the two initializers appear together in the source does not mean they run interleaved line by line for each object.

If a static block appears after an instance field declaration, the static block still belongs to **class initialization**, and does not wait for each instance to reach that position. Therefore, “in textual order” must be understood **within the same initialization phase type and class**, not simply reading the class line by line and running everything in a single top-to-bottom flow for each `new`.

## 41. Do Not Treat File Order as Class Initialization Order

Two files:

~~~text
src/
├── A.java
└── B.java
~~~

The fact that `A.java` appears before `B.java` in the file explorer, alphabetical name order, or which file the compiler reads first **does not by itself determine runtime initialization order**.

If A uses a static method of B, B may be initialized while A is initializing. If B is used first, the reverse occurs. The class hierarchy, class initialization triggers, and dependency graph are the proper basis for prediction.

A static initializer with side effects requires distinguishing “source order **within one class**” from “the order in which independent classes are initialized **across the whole program**”. There is no global file-sorting table that substitutes for execution order.

## 42. Issues to Watch Out For with Multiple Threads

Java class initialization is coordinated by the JVM so that two independent threads do not arbitrarily run the same static initializer as two separate normal initializations.

However:

- Static fields **can be modified after initialization**, and those updates must follow Java Memory Model rules.
- `static int count; count++` is not automatically atomic.
- `static final List` can hold a mutable object; that object is not automatically thread-safe.
- If thread A and thread B need to initialize mutually dependent classes along complex paths, unintended waiting during class initialization can occur.
- Do not use static blocks as a place to implement a complex network of thread startup/coordination.

**Do not confuse “the JVM protects class initialization” with “every static field is thread-safe”.** You must design visibility, synchronization, atomicity, and ownership for subsequent state-updating operations.

## 43. Exercise 1 — Determine Textual Order

Given:

~~~java
class Steps {
    static int a = 1;

    static {
        a *= 3;
    }

    static int b = a + 2;

    static {
        b += a;
    }
}
~~~

After successful class initialization, what are `a` and `b`?

**Answer:** `a=3`. Initializer `b = a + 2` gives `b=5`. The final block makes `b=5+3=8`. Result: `a=3`, `b=8`.

## 44. Exercise 2 — Direct Forward Reference

Given:

~~~java
class Sample {
    // static int first = second; // Why is this an error?
    static int second = 9;
}
~~~

**Answer:** `second` is used by its simple name in a static field initializer **before the field declaration** in the same class, violating the forward-reference restriction. This is not because Java does not know the `second` field exists — the compiler knows the declaration — but because of the rule restricting early field usage in a static initialization context.

Try replacing it with a qualified name and predicting the value of `first` before the second initializer runs.

## 45. Exercise 3 — Indirect Read Through a Method

~~~java
class Example {
    static int early = read();

    static int late = 12;

    static int read() {
        return late;
    }
}
~~~

**Answer:** After initialization, `early=0`, `late=12`. The `read()` method is called while `late` is still at its default 0; the `late = 12` initializer runs afterward.

## 46. Exercise 4 — Constant Variable

~~~java
class Config {
    static int observed = readLimit();
    static final int LIMIT = 15;

    static int readLimit() {
        return LIMIT;
    }
}
~~~

**Answer:** `observed=15`. `LIMIT` is a static final int with a constant-expression initializer, unlike the non-constant static field `late` in the previous exercise. Reading LIMIT in the method returns 15.

## 47. Exercise 5 — Superclass and Subclass

~~~java
class Base {
    static int a = 2;
    static {
        a++;
    }
}

class Derived extends Base {
    static int b = a * 2;
    static {
        b++;
    }
}
~~~

If `Derived.b` triggers initialization of Derived, Base is initialized first: `Base.a` goes from 2 to 3; Derived uses `a=3` to compute `b=6` and then increments it to 7.

**Answer:** `Base.a=3` and `Derived.b=7`.

## 48. Exercise 6 — Initialization Error and Improvement Approach

A class has:

~~~java
class ServiceConfig {
    static final String ENDPOINT = readRemoteConfig();

    static String readRemoteConfig() {
        throw new IllegalStateException("service offline");
    }
}
~~~

If class initialization fails, why does calling a method involving this class again not simply “retry initialization from the start”?

**Answer:** The JVM can mark the runtime class erroneous after an init failure; subsequent uses may receive `NoClassDefFoundError`. If config loading can fail transiently and needs retries, use an explicit config loader/service with a clear lifecycle and retry policy, rather than tying all retry semantics to a static final field initializer.

## 49. Self-Assessment Checklist

- [ ] I can distinguish class loading/preparation from class initialization.
- [ ] I know non-constant static fields have default values before normal initializers.
- [ ] I do not mechanically apply default 0/null to compile-time constant variables.
- [ ] I know field initializers and static blocks interleave in **source order** within the same class.
- [ ] I know static blocks do not run again for each new instance.
- [ ] I know static methods can be declared later and called earlier in an initializer.
- [ ] I know when a simple-name forward read causes an `illegal forward reference`.
- [ ] I know a qualified forward read can compile and observe the default value.
- [ ] I know a method-mediated forward read can observe the default value.
- [ ] I distinguish forward assignment that is valid in certain cases from prohibited forward reads.
- [ ] I know a `static final int` with a constant expression differs from a `static final Integer`.
- [ ] I know reading a compile-time constant may not trigger class initialization.
- [ ] I know a blank static final field can be assigned in a static block.
- [ ] I know a static field initializer does not automatically re-run when another field changes.
- [ ] I can determine the order of Parent static before Child static when initializing Child.
- [ ] I know accessing an inherited static field may initialize only the class declaring the member.
- [ ] I distinguish a static initializer from an instance initializer and a constructor.
- [ ] I do not treat source file order as system-wide class initialization order.
- [ ] I recognize circular static initialization and partially initialized state.
- [ ] I understand class initialization failure can produce `ExceptionInInitializerError`/`NoClassDefFoundError`.
- [ ] I avoid side effects and complex cross-dependencies in static blocks.
- [ ] I understand a lazy nested holder is initialized separately on demand.
- [ ] I know JVM-safe class initialization does not make every static mutation thread-safe.
- [ ] I know how to design tests that avoid depending on a class already initialized in another test.
- [ ] I can compile and run the Java 17+ examples with results matching the lesson.

**Conclusion:** For a Java class, trace **the static field initializers and static initializer blocks in exact top-to-bottom order in the source text**, while placing them in the context of **when class initialization is actually triggered, what default values static fields hold, and how constant variables are specially handled**. When encountering a field declared later, distinguish **prohibited simple-name forward reads**, **qualified/indirect reads that can see the default value**, and **compile-time constants that hold their constant value**. With multiple classes, add superclass–subclass order and class-init dependencies. A step-by-step initialization table will help you predict a program accurately instead of relying on the intuition that “static always runs first”.
