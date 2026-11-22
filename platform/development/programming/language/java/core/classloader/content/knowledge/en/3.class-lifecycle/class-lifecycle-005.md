# Preparation: Allocating and Setting Default Values for Static Fields

## 1. Where Does Preparation Fit in the Class Lifecycle?

When the JVM needs to use a class or interface, part of its work consists of **Loading → Linking → Initialization**. **Preparation** is a stage within **Linking**, occurring after the JVM verifies the validity of the class and before the class is initialized.

~~~text
           Loading
     (creates the class representation from bytecode)
                │
                ▼
           Linking
       ┌─────────────────┐
       │ Verification    │  Checks bytecode validity
       │ Preparation     │  Creates static fields, sets default values
       │ Resolution      │  Resolves symbolic references when needed
       └─────────────────┘
                │
                ▼
         Initialization
       (assigns ConstantValue constants per JVM rules;
        runs <clinit> if present)
                │
                ▼
         Class usage
~~~

The diagram depicts **conceptual tasks**: the JVM may perform *resolution* eagerly or defer it per reference; not every reference is resolved before the program starts running. What is mandatory is that a class/interface must be **verified and prepared before being initialized**.

**What does Preparation do?** The JVM creates storage for the `static` fields declared by the class/interface and assigns **their type's default values** to them. This stage does not run Java code written by the developer, does not call constructors, and does not execute expressions after the `=` sign in field declarations.

Examples of declarations:

~~~java
static int count = 100;
static boolean ready = true;
static Object cache = new Object();
~~~

After Preparation, according to the default-value model, the fields respectively hold **`0`, `false`, `null`**. Only when **Initialization** takes place do the declaration expressions assign `100`, `true`, and a reference to the new object, respectively.

That is the core distinction: **Preparation sets the initial state by type; Initialization executes the code that produces the state desired by the application.**

## 2. How Does the JVM Allocate Static Fields and Assign Default Values?

A field declared `static` is associated with **the class/interface defined in the JVM**, not with individual instances of the class. During the Preparation phase, the JVM creates the corresponding storage slots and sets defaults according to type:

| `static` Field Type | Default Value After Preparation | Example |
|---|---|---|
| `byte`, `short`, `int`, `long` | Integer `0` matching the type | `static long timeout = 99L;` → `0L` before the initializer |
| `float`, `double` | Floating-point `+0.0` matching the type | `static double rate = 1.5;` → `0.0` before the initializer |
| `char` | Null character `'\u0000'` (Unicode U+0000) | `static char marker = 'A';` |
| `boolean` | `false` | `static boolean ready = true;` |
| Reference types (e.g., `String`, `Integer`, arrays, objects) | `null` | `static String title = "Hello";` |
| `static` field without a declared initializer | Remains at its default value even after Initialization, unless assigned elsewhere | `static int attempts;` keeps `0` |

Notes:

- These values are **defaults mandated by Java/JVM semantics**, not garbage or random data.
- `static String text = "abc";` holds `null` at Preparation; assigning the string reference happens during Initialization. Similarly, `static Object value = new Object();` does not invoke `new Object()` during Preparation.
- `static int[] numbers = new int[3];`: **the array reference field** defaults to `null` at Preparation. The three-element array is created only when the `new int[3]` expression is executed during Initialization; the array elements themselves are what default to `0`.
- Fields **without `static`** belong to each individual object. They receive default values during instance allocation as part of the object creation process, **not** when the JVM performs Preparation on a class.
- Descriptions such as “statics reside strictly in Metaspace” or “statics definitely reside in the physical Method Area” are misleading. The specification defines **storage and value semantics**, whereas memory layout details are a JVM implementation decision. Metaspace in HotSpot primarily holds class metadata; do not equate all static fields with the Metaspace region.

Preparation may also set up certain internal structures (such as tables supporting method invocation). That is internal JVM work, not the execution of the program's `static { ... }` blocks.

## 3. Distinguishing Preparation, Initialization, and Assignment Order

Consider the following class across three points in time:

~~~java
class Settings {
    static int attempts;               // No initializer
    static long timeout = 5000L;       // Has initializer
    static boolean enabled = true;     // Has initializer
    static String region = "ap-south"; // Has initializer

    static {
        System.out.println("Settings initialized");
    }
}
~~~

**At Preparation:**

~~~text
attempts = 0
timeout  = 0L
enabled  = false
region   = null
~~~

**During Initialization:**

1. The default values still exist when initialization begins.
2. The JVM executes static field initializers and static blocks in the order they appear in source code, after handling special initialization steps (if any).
3. `timeout` becomes `5000L`, `enabled` becomes `true`, and `region` becomes `"ap-south"`.
4. The static block prints `Settings initialized`; `attempts` remains `0` because no code assigns a different value to it.

**After successful Initialization:** the fields hold the state constructed by the initializers and static blocks. You should neither misconstrue Preparation as running `static { ... }` nor assume Java skips default values just because a field is declared with `= ...`.

An important detail: code running **during the class's own initialization** can sometimes observe fields whose initializers have not run yet and that still hold their default values. This mechanism is demonstrated in the example below; it does **not** mean application code can freely read static fields before the class is initialized.

## 4. Java 17+ Example: Observing Default Values While Initialization Is Underway

The example consists of a standalone source file **`PreparationDemo.java`**. The nested class `Data` declares its fields in an intentional order.

~~~java
public class PreparationDemo {
    static class Data {
        // No initializer: 0 after Preparation and remains 0.
        static int neverAssigned;

        // This method runs when Initialization starts; the fields below
        // have not run their initializers yet, so they still hold default values.
        static int amount = calculate();

        static long timeout = 99L;
        static boolean enabled = true;
        static String label = "ready";

        // Primitive constant compiled into a ConstantValue.
        static final int LIMIT = 42;

        // Integer is not a Java "constant variable".
        static final Integer WRAPPED = Integer.valueOf(42);

        static {
            System.out.println("Static block: initialization complete");
        }

        private static int calculate() {
            System.out.println(
                "While initializing: timeout=" + timeout
                + ", enabled=" + enabled
                + ", label=" + label
            );
            return 7;
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
            "PreparationDemo$Data",
            false,
            PreparationDemo.class.getClassLoader()
        );

        System.out.println("Loaded type: " + type.getName());

        // Compile-time constant inlined by javac at the use site:
        // this access does not trigger initialization of Data.
        System.out.println("Constant only: " + Data.LIMIT);

        // getstatic on a non-constant-variable field:
        // this point forces Data to be initialized.
        System.out.println("Amount: " + Data.amount);

        System.out.println(
            "After initialization: timeout=" + Data.timeout
            + ", enabled=" + Data.enabled
            + ", label=" + Data.label
        );

        System.out.println("Unassigned: " + Data.neverAssigned);
        System.out.println("Wrapped: " + Data.WRAPPED);
    }
}
~~~

From the directory containing `PreparationDemo.java`, run on JDK 17+:

~~~bash
javac -encoding UTF-8 PreparationDemo.java
java PreparationDemo
~~~

**Stdout:**

~~~text
Loaded type: PreparationDemo$Data
Constant only: 42
While initializing: timeout=0, enabled=false, label=null
Static block: initialization complete
Amount: 7
After initialization: timeout=99, enabled=true, label=ready
Unassigned: 0
Wrapped: 42
~~~

### Why Does the Output Appear in This Exact Order?

**Step 1 — Loading/linking without initialization.** `Class.forName("PreparationDemo$Data", false, loader)` requests finding, loading, and linking the class without actively initializing it. Merely printing the class name **is not** an action that initializes `Data`. Therefore, there is no output from `calculate()` or the static block before the `Loaded type` line.

**Step 2 — Reading a compile-time constant.** `Data.LIMIT` is a *constant variable* (`static final int` initialized with a constant expression). For this source code, `javac` replaces the use expression with the value `42` in the caller's bytecode; the statement printing the constant does not cause `Data` to initialize. Do not infer that *every* `static final` field behaves this way: `WRAPPED` is an `Integer`, so it is not a constant variable.

**Step 3 — Accessing `Data.amount`.** This is an ordinary `static` field, so reading it constitutes an **active use** and the JVM must initialize `Data` before providing its value. In Preparation earlier, `amount` and the other fields already received their type defaults.

**Step 4 — Running `calculate()`.** The first initializer is `amount = calculate()`. When the method runs, the initializers declared further down for `timeout`, `enabled`, and `label` **have not run yet**, so the method observes `0`, `false`, `null`. Calling this method is legal: the compiler restricts certain direct forward references to static fields declared later in an initializer, whereas reading via a method invoked at runtime can observe the defaults.

**Step 5 — Completing Initialization.** The JVM assigns `amount = 7`, proceeds to assign `timeout = 99L`, `enabled = true`, `label = "ready"`, creates the value for `WRAPPED`, and then runs the static block. Afterward, `Data.amount` returns `7` to the waiting statement in `main`.

**Step 6 — Field without an initializer.** `neverAssigned` remains `0`, demonstrating that the program **does not need** an explicit `= 0` to have a default value. Once the class has finished initializing, all subsequent accesses in the example read the post-initialization state.

> **Experiment limitation:** The `While initializing...` line is printed **during Initialization**, while several initializers have not yet run; it is not a Java statement running *during Preparation*. Under normal Java usage, reading a non-constant `static` field triggers class initialization before returning a result, making it difficult to directly and independently read Preparation state from application code.

## 5. Notes on `static final` and `ConstantValue`

This is a point frequently misexplained when learning about Preparation. Compare the following:

~~~java
static final int MAX_USERS = 100;
static final String NAME = "demo";
static final int COMPUTED = Integer.parseInt("100");
static final Integer BOXED = 100;
static final int[] VALUES = {1, 2, 3};
~~~

| Declaration | Is It a Java *constant variable*? | How the Value Is Produced |
|---|---|---|
| `MAX_USERS` | Yes: `final`, primitive type, constant expression | `javac` typically generates a `ConstantValue` attribute |
| `NAME` | Yes: `final String`, constant expression | `javac` typically generates `ConstantValue` |
| `COMPUTED` | No: method-invocation expression | Assigned when executing class initialization code |
| `BOXED` | No: `Integer` is not among the constant-variable types | Autoboxing / calling `Integer.valueOf` when executing initialization |
| `VALUES` | No: array type | Array is created when executing initialization |

**Exact distinction according to JVMS Java 17:**

- **Preparation (5.4.2):** The JVM creates the `static` fields and sets **default values**; it does not execute explicit Java initializers.
- **Initialization (5.5, step 6):** `static final` fields that have a `ConstantValue` attribute are assigned their constant values **immediately before `<clinit>` is executed** (and before certain subsequent initialization steps). This is not execution of code inside `<clinit>`.
- **Initialization (5.5, step 9):** The JVM executes `<clinit>`, which corresponds to static assignments that require running code and static blocks. For ordinary Java source code, `<clinit>` follows declaration order.

Therefore, the statement “all `static final` fields are assigned right during Preparation” is **overbroad and does not accurately reflect the ordering in JVMS Java 17**. Introductory materials sometimes fold `ConstantValue` constants into the Preparation diagram for simplicity; when specification precision is needed, separate **Preparation's default values** from **`ConstantValue` assignment at the start of Initialization**.

In particular, a caller printing `MAX_USERS` without triggering class initialization **does not prove that the access directly read a field still in its Preparation state**. The compiler may already have inlined `100` into the caller's bytecode.

## 6. Inspecting Bytecode Yourself with `javap`

The example above produces at least two class files:

~~~text
PreparationDemo.class
PreparationDemo$Data.class
~~~

Run the commands below in **Bash** or **PowerShell** (use single quotes to preserve the `$` character):

~~~bash
javap -v 'PreparationDemo$Data'
javap -c -p 'PreparationDemo$Data'
javap -c PreparationDemo
~~~

What to look for in the output (independent of the constant pool index numbers chosen by `javac`):

1. The `LIMIT` field has an entry equivalent to `ConstantValue: int 42`.
2. The `static {};` method in the `javap -c -p` output is `<clinit>` displayed as a static initializer; it contains the call to `calculate()` and `putstatic` instructions to assign fields that require runtime initialization.
3. In `PreparationDemo.main`, printing `Data.LIMIT` does not require a `getstatic` on the `LIMIT` field; the constant may already be embedded into the print statement's string or pushed using a constant-pushing opcode, depending on how `javac` compiles the string concatenation expression.
4. Accessing `Data.amount` uses `getstatic`, causing the JVM to check and ensure `Data` has been initialized before its value is returned.

**How to read it:** `javap` displays the bytecode/metadata of `.class` files; it **does not display a “preparation method”**. Preparation is an operation performed by the JVM during linking; `<clinit>` is the class initialization code compiled from the static initializers.

## 7. Quick Q&A on the Boundaries of Preparation

**Does Preparation create an instance of the class?** No. Setting default values for `static` fields does not call the class's constructor. An expression like `new Object()` placed in a static initializer is executed only when Initialization runs.

**Does Preparation run static blocks?** No. `static { ... }` contributes to `<clinit>` and runs during Initialization.

**Is `static final` always a “pre-assigned” value?** No. Only `static final` constants of primitive types or `String` whose initializer is a **constant expression** are constant variables in Java semantics. `static final List<?>`, `static final Integer`, `static final int[]`, or a `static final int` computed from a method require runtime initialization.

**If no initializer is specified, does the JVM skip the field?** No. The `static` field still exists and has a default value. For example, `static String message;` has `null`, and `static boolean active;` has `false`.

**Does `Class.forName("X", false, loader)` mean class X is only at Loading and has not undergone Preparation?** No. This overload requests finding, loading, and linking, while **not actively initializing** the specified class. Loading and Preparation are two different tasks; “not yet Initialized” does not mean “not yet Linked”.

**Does each ClassLoader have its own set of static fields?** More precisely: each class **separately defined** by a loader has that class's own static state. Two loaders defining two classes with the same binary name can produce two independent runtime types and sets of static fields. Two loaders that merely both point to **a single class defined by a parent** do not inherently produce two sets of static fields.

**When can Preparation fail?** Linking steps may throw `LinkageError` when invalid type constraints are detected; allocating runtime structures may encounter `OutOfMemoryError`. Errors caused by running initializer expressions (for example, a failing calculation or method call) belong to **Initialization** and must not be misattributed to Preparation.

**Do static fields always exist until the JVM terminates?** They belong to the lifecycle of the defined class. A class may become eligible for reclamation under class unloading rules when its corresponding classloader is no longer reachable and other conditions are satisfied; the timing and possibility of reclamation depend on the JVM. `static` does not mean a “permanent” memory region independent of the class lifecycle.

## 8. Three Self-Check Questions

**Question 1.** Given `static int x = 9; static boolean ok;`, what are the model values of the two fields immediately after Preparation? And what are they after Initialization when no other code assigns to `ok`?

**Answer:** After Preparation: `x = 0` and `ok = false`. After Initialization: `x = 9` and `ok = false`.

**Question 2.** Why does `calculate()` in the `Data` example observe `timeout = 0` even though the source code has `timeout = 99L`?

**Answer:** Preparation set `timeout = 0L`. When Initialization calls `calculate()` for the `amount` field, the initializer for `timeout`, which appears later, has not been executed yet. Only after the method returns does the JVM proceed to assign `99L`.

**Question 3.** Why does the statement printing `Data.LIMIT` not trigger Initialization, whereas reading `Data.amount` can trigger it?

**Answer:** `LIMIT` is a compile-time constant and can be inlined into the caller's bytecode, so that statement does not need to access the field via `getstatic`. `amount` is an ordinary static field; reading it requires the class to be initialized. This is the **active use** rule, not a sign that the caller directly read memory left after Preparation.

## 9. Specification References

- [Java Virtual Machine Specification 17 — 5.4.2 Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2): creating static fields and setting default values without running explicit initializers.
- [Java Virtual Machine Specification 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): order of `ConstantValue` assignment and `<clinit>` execution.
- [Java Language Specification 17 — 12.3.2 Preparation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3.2): relation of Preparation to classes/interfaces.
- [Java Language Specification 17 — 12.4 Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): active use behavior and static initializer ordering.

**Key takeaway:** Preparation creates and sets **default values for static fields**, whereas setting the values described in Java source code takes place during Initialization; `ConstantValue` constants have a separate assignment step at the start of Initialization according to the JVMS.
