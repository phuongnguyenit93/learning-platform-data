# Initialization Order of Fields, Initializer Blocks, and Constructors in Java

## 1. Rules to Remember

When creating a Java object with `new`, initialization components **do not run in an arbitrary order**. For a concrete class that can be initialized, the core sequence is:

1. **Class initialization (if it has not occurred yet):** the required `static` initializers are executed, with the superclass initialized before the subclass.
2. **Object allocation and default value assignment:** instance fields receive initial values such as `0`, `false`, `null`; these are not yet the values written in field initializer expressions.
3. **Run the constructor chain from subclass up to superclass to find the starting point:** the subclass constructor calls `super(...)` or `this(...)`; the execution of ancestor constructors takes place before the subclass's instance initialization.
4. **Within each class, after the superclass constructor finishes:** execute the instance field initializer expressions and instance initializer blocks of the current class **in the order they appear in the source code**, and then execute the body of the current constructor.
5. **Complete the final subclass:** when the constructor of the class instantiated with `new` finishes, the new object completes the normal initialization process.

For a `Parent` → `Child` relationship without complex constructor delegation, the easy-to-remember order is:

```text
Required static initialization (Parent before Child, once per class)
    ↓
Allocation + default values for all instance fields
    ↓
Object constructor
    ↓
Parent: field initializer / instance initializer block (order in code)
    ↓
Parent: constructor body
    ↓
Child: field initializer / instance initializer block (order in code)
    ↓
Child: constructor body
    ↓
new Child() returns the object reference
```

This diagram illustrates the typical case. If a constructor calls `this(...)`, it delegates to another constructor in **the same class** first; that class's field initializers and instance initializers still run only **once** per object. Additionally, static initializers may have already run from an earlier use of the class; they **do not necessarily run during the specific `new` invocation being observed**.

## 2. Three Easily Confused Types of Components

| Component | Example | When does it execute? |
| --- | --- | --- |
| Instance field initializer | `int count = 10;` | Every time an object of the class or a subclass is created, during the instance initialization phase of the class declaring the field |
| Instance initializer block | `{ count++; }` | Every time an object is initialized, interleaved with field initializers in the order they appear in the source code |
| Constructor | `Example() { ... }` | Runs when the corresponding constructor is called in the object initialization chain, after the instance initialization phase of the class containing that constructor |
| Static field initializer | `static int limit = 100;` | When the class is initialized; not repeated per object |
| Static initializer block | `static { ... }` | During the class initialization phase, interleaved with static field initializers in the order they appear in the source code |

Two particularly important principles:

- **Instance members within the same class are interleaved in textual order.** There is no rule to “initialize all fields first, and then run all instance blocks.” If an instance block appears between two field initializers in the code, it runs between those two initializers.
- **Static and instance are two separate sequences.** A `static` block placed at the end of a file does not run after constructors because of its position; during class initialization, the class's `static` components run in their respective order before the creation of the first object that triggers initialization of that class.

Fields declared without an initializer, such as `int count;`, also receive default values as soon as the object's memory is prepared. They do not have an assignment step in the source-code order of field initializers, unless assigned in a block/constructor.

## 3. Experiment 1: Order of Field Initializers, Instance Blocks, and Constructor in the Same Class

The complete program below runs on Java 17 or later.

**File `Main.java`:**

```java
public class Main {
    private int first = mark("1. initialize first", 10);

    {
        System.out.println("2. instance block A; first = " + first);
    }

    private int second = mark("3. initialize second", 20);

    {
        System.out.println("4. instance block B; second = " + second);
    }

    Main() {
        System.out.println("5. constructor; first = "
                + first + ", second = " + second);
    }

    private int mark(String message, int value) {
        System.out.println(message);
        return value;
    }

    public static void main(String[] args) {
        new Main();
    }
}
```

Run:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Exact stdout:**

```text
1. initialize first
2. instance block A; first = 10
3. initialize second
4. instance block B; second = 20
5. constructor; first = 10, second = 20
```

Explanation:

1. The memory for `Main` has been prepared; both `first` and `second` initially have the default value `0`.
2. The field initializer of `first` calls `mark(...)`, prints line 1, and returns `10`.
3. Instance block A runs at the exact position where it is declared, sees `first == 10`, and prints line 2.
4. The field initializer of `second` runs next, prints line 3, and assigns `20`.
5. Instance block B prints line 4; finally, the body of `Main()` prints line 5.

The `mark` method only helps make the order visible; this method itself is not called automatically by Java. Java evaluates the **initializer expression** containing `mark`.

**Try changing it:** move block B before the declaration of `second` and replace reading `second` inside the block with a method call that reads the value of `second`. In that case, it can observe the default value `0`. In Java, directly referencing an instance field by its simple name in an initializer placed before that field's declaration can also trigger the **illegal forward reference** rule; that is a source-code check, distinct from the phenomenon of a field not yet having been assigned its intended value.

## 4. Default Values Exist Before Initializers Run

This is the key point for understanding surprising outputs: all instance fields of an object already have default values before the constructor chain processes initializers.

| Field Type | Default Value |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` matching the type |
| `float`, `double` | `0.0` matching the type |
| `char` | `'\u0000'` (NUL character) |
| `boolean` | `false` |
| Reference types such as `String`, arrays, objects | `null` |

**Standalone example, file `Main.java`:**

```java
public class Main {
    private int observed = readLater();
    private int later = 42;

    private int readLater() {
        return later;
    }

    Main() {
        System.out.println("observed = " + observed);
        System.out.println("later = " + later);
    }

    public static void main(String[] args) {
        new Main();
    }
}
```

Run `javac -encoding UTF-8 Main.java` and then `java Main`:

```text
observed = 0
later = 42
```

When the expression `observed = readLater()` is executed, the `later` field already exists, but it is **not yet the turn** of the expression `later = 42`. The `readLater()` method reads the default value `0`; only afterward is `later` assigned `42`. This is valid and consistent behavior.

Note: the example calls through a method to demonstrate default values. Writing `private int observed = later;` directly before the declaration of `later` can cause an `illegal forward reference` error; do not confuse that error with the default value rule.

## 5. Experiment 2: With Inheritance, the Superclass Performs Instance Initialization Before the Subclass

Consider two classes `Parent` and `Child`. Each class has a field initializer, an instance block, and a constructor.

**File `Main.java`:**

```java
class Parent {
    int parentValue = trace("1. Parent field", 10);

    {
        System.out.println("2. Parent instance block");
    }

    Parent() {
        System.out.println("3. Parent constructor");
    }

    static int trace(String message, int value) {
        System.out.println(message);
        return value;
    }
}

class Child extends Parent {
    int childValue = trace("4. Child field", 20);

    {
        System.out.println("5. Child instance block");
    }

    Child() {
        // super(); is implicitly inserted by the compiler here in Java 17.
        System.out.println("6. Child constructor");
    }
}

public class Main {
    public static void main(String[] args) {
        Child child = new Child();
        System.out.println("7. values = "
                + child.parentValue + ", " + child.childValue);
    }
}
```

Run:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Exact stdout:**

```text
1. Parent field
2. Parent instance block
3. Parent constructor
4. Child field
5. Child instance block
6. Child constructor
7. values = 10, 20
```

The key point is that the `Child()` constructor calls the `Parent()` constructor first. When `Parent()` actually executes, Java runs `Parent`'s instance initializers in the order they appear and only then runs the body of `Parent()`. Only after the superclass's part completes does Java run `Child`'s initializers and then the body of `Child()`.

If `Parent` also inherits from another class, the instance initialization sequence continues downward from higher ancestors to the subclass. Normally, the `Object` constructor is the start of this chain; the example does not print the step for `Object`.

### When the Superclass Constructor Takes Parameters

If `Parent` only declares `Parent(String name)`, the `Child` constructor must call an appropriate superclass constructor, for example `super("Mimi");`. Java **does not automatically generate** a no-arg constructor in `Parent` when that class already has a developer-declared constructor. Omitting an appropriate `super(...)` call causes a constructor compilation error; it does not change the initialization order rules.

In Java 17, an explicit `super(...)` or `this(...)` call must be the first statement of a constructor; both statements cannot appear together as direct calls in the same constructor.

## 6. Experiment 3: `this(...)` Does Not Run Initializers Twice

A class can have multiple constructors. When one constructor calls `this(...)`, it **delegates** to another constructor of the same class. The field initializers and instance blocks still only need to run **once** for the object being created.

**File `Main.java`:**

```java
class Sample {
    private int value = report("1. field initializer");

    {
        System.out.println("2. instance block");
    }

    Sample() {
        this(5);
        System.out.println("4. no-arg constructor body");
    }

    Sample(int number) {
        System.out.println("3. int constructor body: " + number);
    }

    private static int report(String message) {
        System.out.println(message);
        return 100;
    }
}

public class Main {
    public static void main(String[] args) {
        new Sample();
    }
}
```

Run `javac -encoding UTF-8 Main.java` and `java Main`:

```text
1. field initializer
2. instance block
3. int constructor body: 5
4. no-arg constructor body
```

Actual sequence:

1. `new Sample()` selects the no-arg constructor.
2. The first statement of that constructor is `this(5)`, transferring control to `Sample(int)`.
3. Because `Sample(int)` does not call another constructor in the same class, it executes an implicit `super()` call, then `Sample`'s instance initializers run in declaration order, followed by the body of `Sample(int)`.
4. Control returns to `Sample()` and executes the rest of that constructor.

There is no second printing of `field initializer` or `instance block`. A `this(...)` chain must terminate at a constructor that calls `super(...)` (explicitly or implicitly) and must not form an infinite constructor-call cycle.

## 7. Experiment 4: How Do Static Initializers and Instance Initializers Differ?

`static` belongs to the **class**, not to an individual object. `static` field initializer expressions and `static` blocks are executed in the order they appear in each class **when the class is initialized**. When a subclass is initialized, Java ensures that the appropriate superclasses have already been initialized first.

Meanwhile, instance initializers run again for **each new object**.

**File `Main.java`:**

```java
class Parent {
    static int sharedParent = log("Parent static field");

    static {
        log("Parent static block");
    }

    int instanceParent = log("Parent instance field");

    {
        log("Parent instance block");
    }

    Parent() {
        log("Parent constructor");
    }

    static int log(String message) {
        System.out.println(message);
        return 1;
    }
}

class Child extends Parent {
    static int sharedChild = log("Child static field");

    static {
        log("Child static block");
    }

    int instanceChild = log("Child instance field");

    {
        log("Child instance block");
    }

    Child() {
        log("Child constructor");
    }
}

public class Main {
    public static void main(String[] args) {
        System.out.println("-- first --");
        new Child();
        System.out.println("-- second --");
        new Child();
    }
}
```

Run:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Exact stdout when running this program in a fresh JVM:**

```text
-- first --
Parent static field
Parent static block
Child static field
Child static block
Parent instance field
Parent instance block
Parent constructor
Child instance field
Child instance block
Child constructor
-- second --
Parent instance field
Parent instance block
Parent constructor
Child instance field
Child instance block
Child constructor
```

On the first `new Child()`, `Parent` and `Child` have not yet been initialized, so the static sequence of the superclass and then the subclass runs before the instance sequence. On the second invocation, the classes are already initialized and **do not re-execute** the static initializers; each new object still re-runs the instance sequence and constructors.

There is one caveat to understand regarding **observation timing**: a class may have already been initialized earlier due to another active use (for example, accessing a static field that is not a compile-time constant, calling a static method, or using `Class.forName` in a way that initializes the class). Therefore, the static lines will not necessarily appear at the first `new` statement in a larger program. Accessing a `static final` constant that is a compile-time constant expression also has its own triggering rules.

You should not infer the execution order of `static` and instance members from which declaration line appears earlier in the file as a whole. Identify the **class initialization phase** and the **object initialization phase** first, and then examine the order within each phase.

## 8. Assignment Order When the Same Field Is Assigned Multiple Times

The final value of a field is the value after the last assignment **in the initialization flow that actually executed**.

**Standalone example, file `Main.java`:**

```java
public class Main {
    private int level = 1;

    {
        level = 2;
    }

    Main() {
        level = 3;
    }

    public static void main(String[] args) {
        System.out.println(new Main().level);
    }
}
```

Output when running `javac -encoding UTF-8 Main.java` and `java Main`:

```text
3
```

The object receives the default `level = 0`, followed sequentially by `1` in the field initializer, `2` in the instance block, and `3` in the constructor. Setting values in a constructor is typically used when the value depends on parameters passed at object creation time; field initializers suit fixed default values; instance blocks suit logic shared across constructors, though they should be used cautiously because they can make the initialization flow harder to read.

For a **blank final instance field** (a `final` field not assigned immediately at declaration), Java requires the field to be assigned in accordance with definite assignment rules before the constructor completes. It can be assigned in an instance initializer or an appropriate constructor, but it cannot be freely overwritten multiple times like the non-`final` `level` example. A `final` field that already has an initializer at its declaration cannot be reassigned in a constructor.

## 9. Overridden Methods Can Run While Subclass Fields Still Hold Default Values

Note a case that is easy to get wrong when predicting stdout order: if the `Parent` constructor calls an overridable instance method, Java still dispatches to the implementation in `Child`, even though `Child`'s initializers have not yet run. Suppose `Child` declares `String label = "READY"` and overrides `describe()` to read `label`, while `Parent()` calls `describe()`.

| Point in Time | Value of `Child.label` when `describe()` reads it |
| --- | --- |
| Inside the `Parent()` body | `null` (default value, Child's initializers have not run yet) |
| After `new Child()` completes | `"READY"` |

**The initialization order remains unchanged**; it is the dynamic dispatch mechanism that causes the subclass logic to run early. When analyzing examples that call methods from a constructor, add an override-checking step to the order diagram. The article “Risks of Calling Overridable Methods in a Constructor” provides a reproducible program, failure patterns, and safe design approaches.

## 10. Checklist for Predicting Output Before Running

For exercises asking you to determine the order of printed lines during object initialization, you can solve them using the following process:

1. **Identify the object creation statement and the actual runtime type after `new`.** For example, `Parent p = new Child();` still creates a **Child object**, so `Child`'s initialization chain is used.
2. **Determine which classes have not yet undergone static initialization.** If not yet initialized, execute static initializers in superclass-before-subclass order; within each class, static field initializers and static blocks are interleaved in source-code order.
3. **Provisionally note the default value for every instance field.** Having `int x = 7` does not mean `x` is already `7` from the very beginning.
4. **Trace the `this(...)` / `super(...)` chain.** Find the final constructor in each delegation chain and determine which bodies will run as the calls return.
5. **In each class from superclass to subclass:** run instance field initializers and instance blocks in the exact order they appear, followed by the relevant constructor body.
6. **If an overridable method is called**, consider the implementation class selected by dynamic dispatch and the state of the fields **at the exact moment of the call**.
7. **Keep separate objects distinct.** A new `new` invocation re-runs the instance initialization, but does not re-run static initializers of classes that have already been initialized.

### Common Misconceptions

- “Every field initializer runs before every instance block.” **False:** within the same class, they are interleaved in declaration order.
- “The subclass constructor runs first because of `new Child()`.” **False:** the superclass constructor finishes its initialization before the subclass's instance initialization phase and constructor body.
- “`this(...)` calls two constructors, so the instance block runs twice.” **False:** there is only one object; the class's initializers run once, even though multiple constructor bodies may execute as calls return.
- “Static initializers run whenever each object is created.” **False:** they run once during class initialization, at the time determined by the class initialization triggering rules.
- “An assignment expression in a field declaration takes effect before the superclass constructor.” **False:** subclass fields still hold their default values while the superclass constructor is running.
- “Calling an overridden method from the superclass constructor will see the subclass already ready.” **False:** the `label = null` example proves that subclass state may not yet be complete.

## 11. Summary of Execution Order

Always distinguish three separate steps: **static class initialization**, **preparing default values for the object**, and **instance initialization along the constructor chain**. Within a class, field initializers and instance blocks run in the order they appear in the source code; constructor bodies run after them. With inheritance, the instance initialization process proceeds from superclass to subclass. With `this(...)`, the class's initializers run only once. Mastering these rules helps you accurately predict stdout, avoid using uninitialized state, and write more maintainable constructors.
