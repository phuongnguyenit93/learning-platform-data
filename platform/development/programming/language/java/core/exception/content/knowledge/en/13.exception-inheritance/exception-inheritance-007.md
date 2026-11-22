# Checked Exceptions of Superclass Constructors in Java

## 1. The Situation to Understand

In Java, when creating an instance of a subclass, the **superclass constructor must be executed** as part of the initialization process. If the superclass constructor declares a **checked exception** such as `IOException`, the subclass constructor calling it must comply with the exception checking rules. This is a situation easily confused with the `throws` rules for `@Override` methods.

Example:

```java
class Parent {
    Parent() throws java.io.IOException {
        throw new java.io.IOException("parent initialization failed");
    }
}

class Child extends Parent {
    Child() throws java.io.IOException {
        super();
    }
}
```

These are **two valid illustrative classes**, without a `main` method yet. The `super()` call can propagate `IOException` outward, so `Child()` declares `throws IOException`. When a caller writes `new Child()`, the caller itself must catch or declare the checked exception.

Objectives of this lesson:

- Accurately understand the constructor invocation order from superclass to subclass.
- Know how to check for checked exceptions in explicit `super(...)` and implicit `super()` calls.
- Recognize why a subclass's default constructor may **fail to compile** if the superclass constructor declares a checked exception.
- Explain why `super(...)` cannot be placed inside a `try/catch` block directly within the subclass constructor in **Java 17**.
- Use `throws`, choose a superclass constructor overload, or redesign the API when needed.
- Distinguish between **non-overridable constructors** and **overridden methods with restricted checked exceptions**.
- Understand `this(...)` and constructor chaining across multiple classes.
- Determine how callers handle errors, what has already executed before initialization fails, and resource management considerations.
- Avoid confusing compilation errors caused by `throws` with errors caused by a missing matching superclass constructor or lack of access permissions.

Complete programs in this lesson are compatible with Java 17+, with `javac`/`java` commands and `stdout` described separately. Snippets that **intentionally fail to compile** are explicitly marked.

## 2. Constructors Are Not Overridable Methods

First, distinguish between two concepts:

- **Method overriding:** a subclass provides an alternative implementation for an inherited method, with a `throws` contract relationship between the parent method and the child method.
- **Constructor chaining:** a subclass constructor calls a superclass constructor to initialize the superclass portion of the object; this is a **constructor call**, not an override.

Example:

```java
class Parent {
    Parent() throws java.io.IOException {
    }

    void read() throws java.io.IOException {
    }
}

class Child extends Parent {
    Child() throws Exception { // VALID FOR CONSTRUCTOR THROWS.
        super();
    }

    @Override
    void read() throws Exception { // INVALID FOR METHOD OVERRIDE.
    }
}
```

This is **code illustrating an intentional compilation error**, because `Child.read()` declares `Exception`, which is broader than `IOException`. Meanwhile, `Child() throws Exception` is valid regarding the constructor relationship: `IOException` from `super()` is a subtype of `Exception`, so the checked exception is handled by declaration.

Why are the two results different?

- Constructors are not inherited and cannot be overridden; the subclass constructor has an **independent contract** with the `new Child(...)` caller.
- The `read()` method in the subclass overrides a contract that can be invoked through the static type `Parent`. Java does not allow adding new or broader checked exceptions to an overridden method.
- Even though a subclass constructor can declare `throws Exception`, in a good API you should declare a **narrow, meaningful type**, so callers are not forced to catch overly broad `Exception`.

**Core rule:** a subclass constructor may declare a checked exception equal to or broader than the type required by `super(...)`; however, it must not **omit** the checked exception obligation from the superclass constructor call unless there is a valid handling mechanism.

## 3. Object Initialization Order: Superclass Before Subclass

When `new Child(...)` executes successfully, Java must initialize the superclass state before completing the subclass part. A simplified diagram:

```text
caller invokes new Child(...)
        |
        v
Child(...) starts constructor chain
        |
        v
super(...) / this(...) per constructor semantics
        |
        v
Parent(...) and required ancestor classes
        |
        v
initialize Child's instance fields / instance initializers
        |
        v
Child constructor body
        |
        v
new Child(...) returns reference
```

The diagram does not attempt to show details about memory allocation or default values before running constructors. The key point is that if a superclass constructor terminates abruptly with an exception, **subsequent initialization of the subclass does not run**.

### Runnable program: error in superclass constructor blocks subclass constructor

Create file **`ParentConstructorFlowDemo.java`**:

```java
import java.io.IOException;

class Parent {
    Parent(boolean fail) throws IOException {
        System.out.println("parent start");
        if (fail) {
            throw new IOException("parent failed");
        }
        System.out.println("parent end");
    }
}

class Child extends Parent {
    private final int number = initializeNumber();

    private int initializeNumber() {
        System.out.println("child field initializer");
        return 7;
    }

    Child(boolean fail) throws IOException {
        super(fail);
        System.out.println("child constructor body");
    }

    int number() {
        return number;
    }
}

public class ParentConstructorFlowDemo {
    public static void main(String[] args) {
        try {
            new Child(true);
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }

        System.out.println("---");

        try {
            Child child = new Child(false);
            System.out.println("result=" + child.number());
        } catch (IOException failure) {
            System.out.println("unexpected=" + failure.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac ParentConstructorFlowDemo.java
java ParentConstructorFlowDemo
```

Exact `stdout`:

```text
parent start
caught=parent failed
---
parent start
parent end
child field initializer
child constructor body
result=7
```

Explanation of the failure path:

1. Caller invokes `new Child(true)`.
2. `Child(boolean)` calls `super(true)`.
3. `Parent(boolean)` prints `parent start` and throws `IOException("parent failed")`.
4. The superclass constructor does not complete normally, so **the initializer for field `number` and the subclass constructor body do not run**.
5. No `Child` object is returned to the caller; the `catch (IOException)` in the caller handles the error.

Success path: the superclass constructor completes, then the subclass's field initializer and constructor body execute in order, and finally the caller receives the `Child` object and reads `number() == 7`.

**Note:** a constructor failure **does not automatically roll back** side effects that occurred before throwing, such as logging, creating files, or external operations. If a constructor opens a resource and then fails, cleanup must be designed within the scope that owns the resource.

## 4. `super(...)` Throws a Checked Exception: What Does the Subclass Constructor Do?

A subclass constructor must invoke a superclass constructor, directly or indirectly via `this(...)`. When the superclass constructor call can throw a checked exception, the subclass constructor needs to declare a compatible type in `throws`, unless the design path is changed to avoid calling a superclass constructor with that contract.

Basic example:

```java
import java.io.IOException;

class ConfigBase {
    ConfigBase() throws IOException {
        // May read configuration.
    }
}

class ConfigChild extends ConfigBase {
    ConfigChild() throws IOException {
        super();
    }
}
```

This is a **valid class declaration snippet**, without a `main` method yet.

When writing `new ConfigChild()`, the caller must use `try/catch` or declare `throws IOException`. A checked error can occur even if the body of `ConfigChild()` performs no I/O operations after `super()`: **the superclass constructor call alone is enough to create the obligation**.

### 4.1. What about a broader declaration?

From a language standpoint, this subclass constructor is also valid:

```java
class ConfigChild extends ConfigBase {
    ConfigChild() throws Exception {
        super();
    }
}
```

This is an alternative snippet—**do not place it simultaneously with the class of the same name above** when compiling. Because `IOException` extends `Exception`, declaring `throws Exception` covers the error from `super()`. However, callers must deal with the broader `Exception` contract and may be forced to catch more than necessary.

If the subclass constructor has its own steps that also throw checked exceptions, it can list multiple types:

```java
class ConfigChild extends ConfigBase {
    ConfigChild() throws IOException, java.text.ParseException {
        super();
        parseOwnState();
    }

    private void parseOwnState() throws java.text.ParseException {
        throw new java.text.ParseException("invalid child config", 0);
    }
}
```

This is an illustrative class snippet, requiring `import java.io.IOException` or using the fully qualified name; `IOException` is understood as `java.io.IOException`. `ParseException` originates **from the subclass's own logic**, not necessarily from the superclass constructor. The subclass constructor can add its own checked exceptions because **it is not a method override**.

### 4.2. A subclass cannot declare an unrelated checked exception and omit the parent's error

The following **intentionally fails to compile**:

```java
class Parent {
    Parent() throws java.io.IOException {
    }
}

class Child extends Parent {
    Child() throws java.sql.SQLException {
        super(); // IOException is not covered by SQLException.
    }
}
```

The compiler rejects this because `SQLException` and `IOException` are two checked exceptions on different branches. Simply declaring another checked type does not fulfill the obligation for `super()`.

Fix it with `throws IOException`, or `throws IOException, SQLException` if the subclass constructor body also has a valid path that throws `SQLException`. You cannot treat "already having a `throws` clause" as sufficient.

## 5. Implicit `super()`: The Most Easily Overlooked Error

In Java 17, if a subclass constructor does not begin with a valid explicit constructor invocation such as `this(...)` or `super(...)`, the compiler implicitly inserts a call to `super()`.

Example:

```java
class Parent {
    Parent() throws java.io.IOException {
    }
}

class Child extends Parent {
    Child() {
        System.out.println("child");
    }
}
```

This is **code that intentionally fails to compile**. Even though the `super` keyword is not visible, the meaning of the subclass constructor is equivalent to:

```java
Child() {
    super(); // Implicit and may throw IOException.
    System.out.println("child");
}
```

Because `Child()` does not declare `throws IOException`, `javac` reports an unhandled/undeclared checked exception at the constructor. It is not caused by `System.out.println`.

**Fix:**

```java
class Child extends Parent {
    Child() throws java.io.IOException {
        super(); // This line can be omitted; super() is still called implicitly.
        System.out.println("child");
    }
}
```

Here, the `Child` class snippets are **alternatives**; do not place multiple declarations with the same name in the same scope.

### Implicit `super()` differs from having no no-arg constructor

There are at least **two different compilation errors**:

1. The no-arg superclass constructor **exists** but declares a checked exception → the subclass constructor needs a compatible `throws`.
2. The superclass **has no accessible no-arg constructor** → the implicit `super()` **does not match any constructor**, and even adding `throws Exception` will not fix it. You must call `super(arguments)` to select a valid superclass constructor.

Example of case 2:

```java
class Parent {
    Parent(String name) {
    }
}

class Child extends Parent {
    Child() {
        // There is no Parent(), so implicit super() is invalid.
    }
}
```

This is **code that intentionally fails to compile**. Fix it as:

```java
class Child extends Parent {
    Child() {
        super("default");
    }
}
```

**Important:** do not confuse "no default constructor" with "default constructor throws a checked exception." The two errors require different solutions.

## 6. The Subclass's **Default** Constructor Can Also Fail to Compile

If a subclass **does not declare any constructor**, Java generates a default constructor. For a regular class, this default constructor calls `super()` and **does not automatically infer checked exceptions to add to `throws`**.

Example that **intentionally fails to compile**:

```java
class Parent {
    Parent() throws java.io.IOException {
    }
}

class Child extends Parent {
    // No constructor declared.
    // Default Child() must call Parent(), but IOException is not declared.
}
```

This is sometimes surprising: "I didn't declare `Child()` at all, why does the compiler report an error in the subclass?" Because the default constructor cannot make a `super()` call that has a checked exception it does not declare.

The fix is to **declare the subclass constructor explicitly**:

```java
class Child extends Parent {
    Child() throws java.io.IOException {
        super();
    }
}
```

If a no-arg superclass constructor does not exist or is not accessible, the fix must also select the right superclass constructor, not just add `throws`.

### Easy-to-follow test pattern

- Write a superclass with `Parent() throws IOException`.
- Write an empty subclass.
- Compile → error related to default constructor/checked exception.
- Write `Child() throws IOException { super(); }`.
- Recompile → valid if there are no other errors.

These snippets are **alternative class fragments** to learn one rule; do not paste all `Child` versions with the same name into one file.

## 7. Why Can't `super(...)` Be Wrapped in `try/catch` Inside a Subclass Constructor in Java 17?

A natural instinct is to try:

```java
class Child extends Parent {
    Child() {
        try {
            super();
        } catch (java.io.IOException failure) {
            System.out.println("fallback");
        }
    }
}
```

This is **code that intentionally fails to compile in Java 17**. The superclass constructor call `super(...)` cannot be placed arbitrarily inside a `try` block in the subclass constructor body. In Java 17, an explicit constructor invocation must appear as the first statement of the constructor; a `try/catch` cannot wrap the `super(...)` call to "catch it directly in the subclass constructor."

Even if you place a `try/catch` **after** `super()`, it only catches exceptions from operations executed inside that `try` block afterward, not from the superclass constructor call that already happened:

```java
class Child extends Parent {
    Child() throws java.io.IOException {
        super();

        try {
            doChildWork();
        } catch (java.io.IOException failure) {
            System.out.println("child work failed");
        }
    }

    private void doChildWork() throws java.io.IOException {
        throw new java.io.IOException("child operation");
    }
}
```

This is a valid illustrative class when `Parent()` declares `throws IOException`. The subclass constructor **still** must declare `throws IOException` for `super()`.

### If you truly need to recover from a superclass constructor failure

You need to **change the handling boundary** rather than directly wrapping `super()` in the subclass constructor:

- **Caller** catches the checked exception when calling `new Child(...)`.
- **Superclass** handles the error internally or provides another constructor with a suitable contract.
- **Redesign initialization:** if possible, move operations that can fail to a factory or initialization method with its own error policy, instead of forcing the superclass constructor to throw a checked exception.
- **Choose a different superclass constructor overload** if semantics and contracts allow.

Do not create a falsely successful object if required superclass initialization fails. If the superclass constructor throws, creating the subclass object does not complete normally.

**Version scope:** the `super(...)` syntax explanation here applies to Java 17. Later JDKs may expand constructor body structure through new language features; when working with Java 17, follow that version's rules.

## 8. Choosing a Superclass Constructor Overload That Does Not Throw a Checked Exception

A superclass can have multiple constructors with different contracts. The subclass may choose a valid overload using `super(arguments)`:

```java
class Parent {
    Parent() throws java.io.IOException {
        throw new java.io.IOException("default failed");
    }

    Parent(String preset) {
        System.out.println("parent preset=" + preset);
    }
}
```

If the subclass calls `super()`, it must handle/declare `IOException`. If it calls `super("cached")`, the selected overload **does not declare a checked exception**, so the subclass does not need to declare `IOException` just because **another overload** of the superclass has `throws`.

### Runnable program: choosing a safe superclass constructor

Create file **`OverloadedSuperConstructorDemo.java`**:

```java
import java.io.IOException;

class Base {
    Base() throws IOException {
        throw new IOException("default path unavailable");
    }

    Base(String mode) {
        System.out.println("base mode=" + mode);
    }
}

class Derived extends Base {
    Derived() {
        super("cached");
        System.out.println("derived ready");
    }
}

public class OverloadedSuperConstructorDemo {
    public static void main(String[] args) {
        new Derived();
        System.out.println("done");
    }
}
```

```bash
javac OverloadedSuperConstructorDemo.java
java OverloadedSuperConstructorDemo
```

`stdout`:

```text
base mode=cached
derived ready
done
```

Explanation: `Derived()` calls the `Base(String)` overload. The `Base() throws IOException` overload is not executed on this path. Therefore, `Derived()` does not need `throws IOException`.

**Do not abuse:** only choose another overload if it genuinely establishes the invariants the object needs. Switching from required initialization to "cached" just to avoid a checked exception can produce an object in an invalid state.

## 9. `this(...)`: Exceptions Propagating Through the Subclass's Own Constructor Chain

`this(arguments)` is used to call another constructor in the **same class**. One constructor in the chain must eventually lead to an appropriate superclass constructor. Checked exceptions from a constructor invoked via `this(...)` must also be handled according to compile-time rules.

Example:

```java
class Child extends Parent {
    Child() throws java.io.IOException {
        this("sample");
    }

    Child(String name) throws java.io.IOException {
        super();
        System.out.println(name);
    }
}
```

This is an illustrative class snippet when `Parent() throws IOException`. The no-arg constructor **does not directly call `super()`**, but it calls `this("sample")`; the delegated constructor calls `super()` and can throw `IOException`. Therefore, the entire chain must ensure checked exceptions are declared at each uncaught call.

### Runnable example: propagating errors through `this(...)`

Create file **`ThisConstructorChainDemo.java`**:

```java
import java.io.IOException;

class Parent {
    Parent(boolean fail) throws IOException {
        System.out.println("parent");
        if (fail) {
            throw new IOException("parent failed");
        }
    }
}

class Child extends Parent {
    Child(boolean fail) throws IOException {
        this("delegated", fail);
        System.out.println("outer child");
    }

    Child(String name, boolean fail) throws IOException {
        super(fail);
        System.out.println("inner child: " + name);
    }
}

public class ThisConstructorChainDemo {
    public static void main(String[] args) {
        try {
            new Child(false);
        } catch (IOException failure) {
            System.out.println("unexpected");
        }

        System.out.println("---");

        try {
            new Child(true);
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }
    }
}
```

```bash
javac ThisConstructorChainDemo.java
java ThisConstructorChainDemo
```

`stdout`:

```text
parent
inner child: delegated
outer child
---
parent
caught=parent failed
```

On the success path, the order is superclass constructor → remainder of the `(String, boolean)` constructor → remainder of the `(boolean)` constructor. On the failure path, the superclass constructor throws first, so the `inner child` and `outer child` lines from the second run do not appear.

If a subclass constructor calls `this(...)` **without** declaring a checked exception that the target constructor can throw, the compiler reports an error at the calling constructor, even though the subclass constructor does not directly write `super()`.

### Cycles with `this(...)` are not allowed

`Child() { this(1); }` and `Child(int n) { this(); }` calling only each other is an invalid **recursive constructor invocation**. Adding `throws` does not solve this because there must be a path that actually initializes the superclass and completes the constructor chain.

## 10. Multi-Level Inheritance Chains: root → middle → leaf

For multiple levels:

```text
Root() throws IOException
     |
     v
Middle() throws IOException
     |
     v
Leaf() throws IOException
     |
     v
new Leaf() at caller
```

Each constructor calling upward may have to declare a compatible checked exception. If a layer cannot change the root constructor, the caller must still be prepared for the final exception published by the selected constructor at the lowest level.

### Runnable program: three constructor levels

Create file **`ThreeLevelConstructorDemo.java`**:

```java
import java.io.IOException;

class Root {
    Root(boolean fail) throws IOException {
        System.out.println("root");
        if (fail) {
            throw new IOException("root failed");
        }
    }
}

class Middle extends Root {
    Middle(boolean fail) throws IOException {
        super(fail);
        System.out.println("middle");
    }
}

class Leaf extends Middle {
    Leaf(boolean fail) throws IOException {
        super(fail);
        System.out.println("leaf");
    }
}

public class ThreeLevelConstructorDemo {
    public static void main(String[] args) {
        try {
            new Leaf(false);
        } catch (IOException failure) {
            System.out.println("unexpected");
        }

        System.out.println("---");

        try {
            new Leaf(true);
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }
    }
}
```

```bash
javac ThreeLevelConstructorDemo.java
java ThreeLevelConstructorDemo
```

`stdout`:

```text
root
middle
leaf
---
root
caught=root failed
```

When `Root` fails, **there are no `middle`/`leaf` lines** in the failed initialization attempt. The `Leaf` object never finishes being created and is not returned to the caller.

This also applies if `Root` is an abstract class with a constructor: an abstract class cannot be instantiated directly with `new Root()`, but its constructor **still executes** when instantiating a concrete subclass. An abstract constructor with `throws IOException` also creates checked exception obligations for subclass constructors.

## 11. Checked Exceptions from **Argument Expressions** of `super(...)`

Checked errors do not come only from the **superclass constructor body**. When evaluating an expression used as an argument to `super(arguments)` or `this(arguments)`, a helper method can throw a checked exception, and the calling constructor must also handle/declare it.

Example:

```java
class Parent {
    Parent(String value) {
        System.out.println("parent=" + value);
    }
}

class Child extends Parent {
    private static String loadValue() throws java.io.IOException {
        throw new java.io.IOException("cannot prepare argument");
    }

    Child() throws java.io.IOException {
        super(loadValue());
    }
}
```

This is a **valid class snippet**. `Parent(String)` does not declare any checked exception, but `loadValue()` is called **to produce the argument** for the superclass constructor and has `throws IOException`. Thus `Child()` still needs to declare the checked `IOException`.

### Runnable example: argument fails before superclass constructor is invoked

Create file **`SuperArgumentFailureDemo.java`**:

```java
import java.io.IOException;

class Base {
    Base(String value) {
        System.out.println("base=" + value);
    }
}

class Derived extends Base {
    private static String prepare(boolean fail) throws IOException {
        System.out.println("prepare argument");
        if (fail) {
            throw new IOException("argument failed");
        }
        return "ready";
    }

    Derived(boolean fail) throws IOException {
        super(prepare(fail));
        System.out.println("derived body");
    }
}

public class SuperArgumentFailureDemo {
    public static void main(String[] args) {
        try {
            new Derived(true);
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }
        System.out.println("---");
        try {
            new Derived(false);
        } catch (IOException failure) {
            System.out.println("unexpected");
        }
    }
}
```

```bash
javac SuperArgumentFailureDemo.java
java SuperArgumentFailureDemo
```

`stdout`:

```text
prepare argument
caught=argument failed
---
prepare argument
base=ready
derived body
```

On the failure path, `prepare(true)` throws before the `Base(String)` call actually executes the superclass constructor body, so **`base=...` is not printed**. This is an important distinction: during checked exception analysis, you must inspect both the invoked constructor and **all argument evaluation expressions**.

In Java 17, avoid directly using `this` or uninitialized instance members inside an explicit constructor invocation. The `prepare` method in the example is `static` so it does not depend on uninitialized instance state.

## 12. Can a Subclass Constructor Add Its Own Checked Exceptions?

**Yes.** A constructor is not an override, so there is no rule saying "the subclass may only keep or narrow the superclass's `throws`" as there is for overridden methods.

If `Parent()` throws no checked exceptions, `Child()` can declare `throws IOException` and throw it from its own body:

```java
class Parent {
    Parent() {
    }
}

class Child extends Parent {
    Child(boolean fail) throws java.io.IOException {
        super();
        if (fail) {
            throw new java.io.IOException("child setup failed");
        }
    }
}
```

This is a valid illustrative class. The caller `new Child(true)` must handle/declare `IOException` according to the signature of `Child(boolean)`, even though `Parent()` throws no checked exceptions at all.

Compare with method overriding:

```java
class Parent {
    void load() {
    }
}

class Child extends Parent {
    @Override
    void load() throws java.io.IOException {
    }
}
```

This is **code that intentionally fails to compile**, because `Parent.load()` does not allow checked `IOException`. Thus, "subclass constructors can broaden checked exceptions, while overridden methods cannot" is a distinction worth remembering accurately.

### Designing constructor contracts

A caller can only create an object successfully if the entire required initialization chain completes. Therefore, a subclass constructor should declare checked exceptions that are **truly meaningful** for the initialization process. Arbitrarily declaring a broad `throws Exception` makes it harder for callers to classify errors and can lead to overly generic error-handling code.

## 13. Callers Must Catch or Declare Checked Exceptions When Using `new`

If `Child(...)` has `throws IOException`, the expression `new Child(...)` is checked just like any other call that throws a checked exception.

Two valid approaches:

**Approach A — caller catches:**

```java
try {
    Child child = new Child(true);
    System.out.println("created");
} catch (java.io.IOException failure) {
    System.out.println("construction failed: " + failure.getMessage());
}
```

**Approach B — caller declares:**

```java
public static void main(String[] args)
        throws java.io.IOException {
    Child child = new Child(false);
    System.out.println("created");
}
```

Both are **illustrative code snippets**: a suitable `Child` class and method/`main` are required.

**Case C — neither caught nor declared** in a normal method will be rejected by the compiler:

```java
static void start() {
    Child child = new Child(true); // Does not handle IOException.
}
```

This snippet **intentionally fails to compile**, assuming `Child(boolean) throws IOException`.

### What if the caller uses a superclass-typed variable?

With:

```java
Parent value = new Child(true);
```

The checked exception rule for the expression `new Child(true)` depends on the **selected `Child` constructor**, not just the `Parent` variable type receiving the reference. The static type of the receiving variable does not eliminate the obligation to handle initialization errors from the subclass constructor.

Once the object **has been created successfully**, method calls through `Parent` use the checked exception contract of the method selected via the **static type** `Parent`. These are two different operations: `new` to construct an object, and method invocation on an existing object.

## 14. Constructor Failures and Resource Management

An exception from `super(...)` prevents construction from completing. However, **resources already opened before throwing** may remain open if not managed.

### 14.1. Superclass constructors must preserve their own cleanup

If a superclass constructor opens resource A and then a subsequent initialization step fails, the caller has no reference to a constructed object on which to call `close()`. The constructor or factory responsible for resource A must clean it up on the failure path.

Example **logic snippet**:

```java
Resource opened = openFirst();
try {
    initializeFurther(opened); // May fail.
} catch (Exception failure) {
    try {
        opened.close();
    } catch (Exception cleanup) {
        failure.addSuppressed(cleanup);
    }
    throw failure;
}
```

This is an **illustrative snippet** requiring declarations for `Resource`, the methods, and full checked exception handling. The goal is to show that the root cause should not be masked by a close failure. When a resource implements `AutoCloseable` and ownership fits, `try-with-resources` is usually less error-prone than manual cleanup.

### 14.2. Resource created in a TWR header before a subclass constructor fails

Create file **`ConstructorWithResourcesDemo.java`**:

```java
import java.io.IOException;

class TraceResource implements AutoCloseable {
    TraceResource() {
        System.out.println("open first");
    }

    @Override
    public void close() {
        System.out.println("close first");
    }
}

class Parent {
    Parent(boolean fail) throws IOException {
        System.out.println("parent constructor");
        if (fail) {
            throw new IOException("constructor failed");
        }
    }
}

class Child extends Parent implements AutoCloseable {
    Child(boolean fail) throws IOException {
        super(fail);
        System.out.println("child constructor");
    }

    @Override
    public void close() {
        System.out.println("close child");
    }
}

public class ConstructorWithResourcesDemo {
    public static void main(String[] args) {
        try (TraceResource first = new TraceResource();
             Child child = new Child(true)) {
            System.out.println("body");
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }
    }
}
```

```bash
javac ConstructorWithResourcesDemo.java
java ConstructorWithResourcesDemo
```

`stdout`:

```text
open first
parent constructor
close first
caught=constructor failed
```

Here:

1. `TraceResource first` is successfully initialized in the TWR header.
2. While initializing `Child child`, the `Parent` constructor throws `IOException`.
3. Because `Child` was not constructed successfully, **no `Child` object is bound to the resource slot to have `close()` called**; `close child` does not appear.
4. Resource `first` is already managed in the header, so it is closed, and `close first` appears.
5. The caller receives the checked exception from the failed `Child` construction.

If `first.close()` also throws, the close error can become a **suppressed exception** attached to the primary exception thrown by the constructor. `try-with-resources` cannot automatically close resources that the superclass constructor created internally and lost references to; the constructor/factory must design its own cleanup.

### 14.3. Do not call methods on an object that failed to construct

If `new Child(...)` throws, a normal assignment `Child child = new Child(...)` does not complete and the program has no `Child` object returned to the caller. There is no valid `child.close()` call on that failed construction result. Place cleanup responsibility where the resource is owned and already accessible.

## 15. Cases Easily Confused with Superclass Constructor Exceptions

### 15.1. Missing matching `super()` constructor error

If the superclass only has `Parent(int)`, the subclass must call `super(intValue)`. Adding `throws IOException` does not create a no-arg constructor.

### 15.2. Superclass constructor access error

If the superclass constructor is `private` and a subclass in another class lacks permission to call it, the error is **accessibility**, not a checked exception. You need to pick an accessible constructor or change the superclass design.

### 15.3. Constructors in abstract classes

Abstract classes still have constructors. When instantiating a concrete subclass, the abstract parent constructor is still called and any checked exceptions must still be handled/declared.

### 15.4. Interfaces have no constructors

A class implementing an interface does not call an interface constructor: interfaces have no instance constructors. It still calls the constructor of its **actual superclass** (usually `Object` if there is no explicit `extends` class).

### 15.5. Constructors cannot be `@Override`n

Putting `@Override` on a constructor is wrong. A constructor's name matches the class name and it has no return type. The checked `throws` restriction for method overriding does not apply to constructors.

### 15.6. Exceptions from subclass instance initializers

If the superclass constructor completes, the subclass's instance field initializers and instance initializers run **before the subclass constructor body**. They can cause construction to fail, but that is not an error thrown by the superclass constructor. Checked exception rules for initializers have their own constraints in the JLS; do not assume any checked exception in an initializer can be thrown arbitrarily without considering all constructors of the class.

### 15.7. Undeclared runtime errors

A superclass constructor can throw `RuntimeException` or `Error` without declaring `throws`. These types are unchecked, so the compiler does not require subclass constructors to declare them. However, they can still cause object creation to fail at runtime.

### 15.8. Compiler error messages

Messages like "unreported exception ...; must be caught or declared to be thrown" indicate an unhandled checked exception. Messages like "constructor ... cannot be applied to given types" or "... has private access" relate to overloads/access. Read the actual error type rather than mechanically adding `throws Exception`.

## 16. Decision Flowchart When a Subclass Fails to Compile

```text
Child constructor has an error at super()/implicit super()
                     |
                     v
Does Parent have a matching, accessible constructor?
         |                                 |
         NO                               YES
         |                                 |
         v                                 v
Choose right super(args) or      Do parent constructor / argument
fix Parent API/access            expressions have checked exceptions?
                                           |
                               +-----------+-----------+
                               |                       |
                              YES                      NO
                               |                       |
                               v                       v
                         Child must declare       Check syntax or
                         compatible checked       other logic errors
                         in throws or choose
                         another valid init path
                               |
                               v
                         Caller new Child(...)
                         catches/declares checked
```

When a subclass constructor also calls `this(...)`, trace the delegation chain to find the constructor that ultimately calls `super(...)`; check checked exceptions at every call.

### Safe troubleshooting workflow

1. Confirm whether the error comes from implicit `super()`, explicit `super(arguments)`, `this(arguments)`, or an argument expression.
2. Look up the **actual selected constructor signature** (do not guess by class name).
3. Check whether the superclass constructor is accessible and the parameter types match.
4. List checked exceptions from the invoked constructor and from argument expressions.
5. Declare a suitable checked type on the calling constructor, or use another overload/initialization design with the right semantics.
6. Trace callers of `new Child(...)` to catch or declare the checked exception.
7. Inspect the failure path: what initialization already ran, which resources were created, and who must clean them up.
8. Recompile and verify behavior on both the success and failure paths.

## 17. Summary Table of `throws` Contracts

| Scenario | Valid in Java 17? | Why |
| --- | --- | --- |
| `Parent() throws IOException`; `Child() throws IOException { super(); }` | **Yes** | `Child` declares the exact checked exception from `super` |
| `Parent() throws IOException`; `Child() throws Exception { super(); }` | **Yes** | `Exception` covers `IOException`, though the contract is broad |
| `Parent() throws IOException`; `Child() { super(); }` | **No** | Omits the checked exception obligation |
| `Parent() throws IOException`; `Child() throws SQLException { super(); }` | **No** | `SQLException` is on another branch and does not cover `IOException` |
| `Parent() throws IOException`; `class Child extends Parent { }` | **No** in the stated case | Default `Child()` does not automatically declare `throws` |
| Parent only has `Parent(String)`; Child writes `Child() { }` | **No** | Implicit `super()` has no matching overload |
| Parent has `Parent(String)` without `throws`; Child uses `super("A")` | **Yes** | The invoked overload declares no checked exceptions |
| Parent throws no checked exceptions; Child constructor itself `throws IOException` | **Yes** | Subclass constructor does not override superclass constructor |
| Parent method throws no checked exceptions; overridden method adds `throws IOException` | **No** | Checked exception rule for method overriding |
| Subclass constructor calls `this(...)` that `throws IOException` without declaring it | **No** | Delegated constructor call has a checked exception |
| Superclass constructor throws no checked exceptions, but `super(loadValue())` with `loadValue() throws IOException` | Needs matching `throws` | Exception comes from evaluating the argument |
| `try { super(); } catch (IOException e) { ... }` in `Child()` | **No** in Java 17 | Cannot wrap an explicit constructor invocation this way |
| `new Child()` when `Child() throws IOException` in a caller without `catch`/`throws` | **No** | Caller must handle the checked exception |
| Parent constructor throws `IllegalStateException`, Child does not declare `throws` | **Yes** for unchecked checking | `RuntimeException` does not require declaration |

The table evaluates **only the stated rules**; abbreviated examples assume appropriate classes, access permissions, and other declarations. A complete snippet must also compile regarding parameters, fields, packages, and class names.

## 18. Common Misconceptions

**"A subclass constructor overrides the superclass constructor."** False. Constructors are not inherited/overridden; a `super(...)` call is constructor chaining, not method dynamic dispatch.

**"Because overriding cannot broaden checked exceptions, a `Child` constructor also cannot add `SQLException` if the `Parent` constructor only throws `IOException`."** False for constructor rules. `Child` can declare additional checked exceptions of its own because constructors do not override. However, it **still must cover `IOException`** if it calls a superclass constructor that has `throws IOException`.

**"Not writing `super()` means there are no superclass checked exceptions."** False. Java 17 inserts `super()` implicitly when a constructor does not explicitly delegate or call the superclass.

**"If a subclass declares no constructor, the compiler generates a default constructor with all required `throws`."** False. The default constructor does not automatically infer `throws IOException` to satisfy the superclass constructor.

**"You can wrap `super()` in a `try/catch` inside `Child` to handle the error immediately."** Invalid in Java 17. You must handle it in the caller, change the superclass API/constructor, or select a suitable overload.

**"`throws SQLException` on `Child` is enough because it is also a checked exception."** False if the `super()` call has `throws IOException` which `SQLException` does not cover.

**"If `Parent()` has `throws IOException` but an empty body, `Child` does not need to declare it."** False. Checking is based on the contract of the invoked method/constructor, not just on a single runtime execution.

**"The subclass constructor finishes its body first and then calls the superclass constructor."** False. The superclass constructor executes before the subclass's initializers and constructor body in normal cases.

**"The `Parent` constructor fails, yet `Child` is still created with default fields."** False. If an exception escapes construction, the `new Child(...)` expression does not complete normally.

**"An error in `super(load())` definitely comes from the superclass constructor."** Not necessarily. `load()` in the argument expression can throw before the superclass constructor body runs.

**"Abstract class constructors are never called."** False. An abstract parent's constructor is still a link in the chain when instantiating a concrete subclass.

**"When writing `Parent variable = new Child()`, the compiler only checks `Parent`'s constructor."** False. Checked exception obligations of the `new Child()` expression are based on the selected `Child` constructor.

**"Adding `throws Exception` solves every `super()`-related error."** False. It does not fix missing overloads, `private` constructors, mismatched parameter types, or recursive `this(...)` chains.

**"Because `Child` construction failed, any resources `Parent` opened are automatically rolled back."** False. Java does not automatically roll back side effects or close unmanaged internal resources. Cleanup must be designed.

**"`try-with-resources` will call `close()` on `Child` even if `new Child()` throws before initialization finishes."** False. The `Child` resource slot did not finish initializing, so it is not closed as a successfully created resource; only previously managed resources are closed according to the rules.

**"Unchecked exceptions cannot cause a constructor to fail without declaring `throws`."** False. `RuntimeException` and `Error` can still occur at runtime.

## 19. Self-Check Questions

1. **`Parent() throws IOException`, `Child()` calls `super()` without `throws`: is it valid?** No.
2. **Is `Child() throws IOException { super(); }` valid?** Yes, if the selected superclass constructor is `Parent() throws IOException` and other conditions are valid.
3. **Is `Child() throws Exception` instead of `IOException` valid for a constructor?** Yes, though broader than necessary.
4. **Does `Child()` with only `throws SQLException` cover `IOException` from `super`?** No.
5. **Class `Child` has no constructor while `Parent() throws IOException`: what is the problem?** The implicit default constructor does not declare the checked exception, so it fails to compile.
6. **If `Parent` has no no-arg constructor, does merely adding `throws` fix the error?** No; you must call the right overload `super(arguments)`.
7. **Why can't you write `try { super(); } catch ...` inside `Child` in Java 17?** Explicit constructor invocations have positioning constraints and cannot be placed inside a `try` block like that.
8. **If there is a `Parent(String)` without `throws`, and `Child` calls `super("preset")`, what happens?** No checked handler is needed for `IOException` from the other `Parent()` overload.
9. **`Child()` throws `IOException` itself while `Parent()` has no `throws`: is it allowed?** Yes, because constructors do not override.
10. **Parent method has no `throws`, `Child` overrides the method and adds `throws IOException`: is it allowed?** No, because an overridden method cannot add checked exceptions.
11. **Constructor `Child(boolean)` calls `this(String, boolean) throws IOException`: does `Child(boolean)` need `throws`?** Yes, unless there is another valid handling mechanism; in Java 17 you cannot wrap `this(...)` in `try`.
12. **Superclass constructor runs and throws before initializing `Child`'s fields: does `Child`'s field initializer run?** No.
13. **Where can an error from `super(load())` come from?** From `load()` during argument evaluation or from the invoked superclass constructor.
14. **What must the caller of `new Child()` do when `Child() throws IOException`?** Catch or declare a compatible `IOException`.
15. **Does assigning the result of `new Child()` to a `Parent` variable remove the `IOException` obligation?** No.
16. **If `Parent` is an abstract class, does its constructor run when creating `Child`?** Yes.
17. **`Parent()` throws an undeclared `RuntimeException`; must `Child` add `throws RuntimeException`?** Not required because it is unchecked.
18. **If the superclass constructor fails, does the caller have a complete `Child` object to close?** No.
19. **If the first resource in TWR is created, and the second resource's constructor throws: is the first resource closed?** Yes, according to TWR rules.
20. **Should you add `throws Exception` to every subclass constructor to avoid checking?** No; choosing a specific contract helps callers handle errors properly and exposes design issues.

## 20. Official Java 17 Documentation

- [Java Language Specification 17 — `8.8 Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor structure, `throws`, explicit constructor invocations, and default constructors.
- [Java Language Specification 17 — `8.8.7.1 Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): rules for `this(...)`, `super(...)`, and invocation placement restrictions in Java 17.
- [Java Language Specification 17 — `8.8.9 Default Constructor](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.9): implicit constructor when a class declares no constructors.
- [Java Language Specification 17 — `11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): obligations to declare/catch checked exceptions when invoking constructors.
- [Java Language Specification 17 — `12.5 Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): instance creation process across inheritance levels.
- [Java Language Specification 17 — `8.4.8.3 Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): comparing `throws` restrictions on overridden methods with constructors.
- [Java Language Specification 17 — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cleanup of resources already initialized in the header if a subsequent resource fails to initialize.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): common checked exception in constructors performing I/O.

**Key takeaway:** A subclass constructor does not override a superclass constructor: it **calls the superclass constructor** via `super(...)` directly or through a `this(...)` chain. If the superclass constructor or argument expressions have checked exceptions, the subclass constructor must **declare a compatible type**, or select another initialization path with the right contract. `super()` may be inserted implicitly; a subclass's default constructor does not automatically inherit the superclass's `throws`. Callers creating the object must catch/declare checked exceptions from the selected constructor, and if construction fails, any opened resources still require cleanup in the proper ownership scope.
