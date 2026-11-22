# Calling Another Method on the Same Object in Java with `this.method()`

In Java, an **instance method** can call another instance method on **the very object receiving the call**. The explicit syntax is `this.method(arguments)`. In a normal instance context, writing `method(arguments)` also usually calls it on the implicit receiver `this`. This is how a class splits large behavior into smaller methods while still operating on the state of **the same instance**.

The key point is: **`this` is a reference to the current object, not a class name**, and `this.method()` does not automatically force Java to call the implementation declared in the class containing that line of code. If the method can be overridden, Java applies **dynamic dispatch** based on the runtime type of the object.

This Java 17+ lesson focuses on what calling another method on the same object means: the receiver, instance fields, helper methods, implicit calls, inheritance, constructors, method chaining, nested classes, lambdas, recursion, concurrent access, and common mistakes.

## 1. Receiver: Which Object Is the Method Running On?

Consider the class:

~~~java
class Counter {
    private int count;

    void increment() {
        this.setCount(this.getCount() + 1);
    }

    int getCount() {
        return this.count;
    }

    private void setCount(int count) {
        this.count = count;
    }
}
~~~

This is a declaration snippet without a `main` method to run standalone. When calling:

~~~java
Counter first = new Counter();
Counter second = new Counter();

first.increment();
first.increment();
second.increment();
~~~

These lines are a fragment inside a method. When `first.increment()` is running, `this` inside `increment()` points to `first`'s object. Both `this.getCount()` and `this.setCount(...)` operate on that object. When `second.increment()` runs, `this` points to `second`'s object instead.

As a result, `first.getCount()` is `2` and `second.getCount()` is `1`. The two objects use the same class source code but keep **separate instance state**.

~~~text
first ------> Counter object A { count = 2 }
                this in first.increment()

second -----> Counter object B { count = 1 }
                this in second.increment()
~~~

The diagram is a reference model and does not assert physical memory addresses. **There is no `new Counter()` call inside `increment()`**: calling another method via `this` simply continues working on the current object.

## 2. Structure of a `this.method(...)` Call

The expression:

~~~java
this.validateAmount(amount);
~~~

consists of:

- `this`: the receiver, meaning the current object.
- `.`: selects a member of the receiver.
- `validateAmount`: the name of the method to call.
- `(amount)`: the arguments passed to the corresponding method.

Java resolves methods according to rules for names, access scope, argument types, overloading, and inheritance. When selecting the implementation of an overridable instance method, Java also uses runtime dispatch.

Another method can be called even if it is `private` within the same class:

~~~java
class TicketOffice {
    private int sold;

    void sell(int quantity) {
        this.validateQuantity(quantity);
        this.recordSale(quantity);
    }

    private void validateQuantity(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Số vé phải dương");
        }
    }

    private void recordSale(int quantity) {
        sold = Math.addExact(sold, quantity);
    }
}
~~~

This declaration snippet has no `main`. The public method `sell` handles coordination, while the two private methods perform validation and updating. All of them operate on the same `TicketOffice` object receiving the `sell` call.

**Benefit:** the caller only needs to know `sell`; it neither needs nor is allowed to directly access the two private helpers. The class retains control over state, reduces duplicated logic, and expresses the order of validating before updating.

## 3. Are `this.method()` and `method()` Always the Same?

In a normal instance method, when there are no name-resolution issues, the two forms are usually equivalent:

~~~java
class Greeter {
    private String name = "Lan";

    String getName() {
        return name;
    }

    String greetingA() {
        return "Chào " + this.getName();
    }

    String greetingB() {
        return "Chào " + getName();
    }
}
~~~

On the same `Greeter` object, `greetingA()` and `greetingB()` both call `getName()` with the current object as the receiver, returning `"Chào Lan"`.

However, you must not assume that every call omitting `this.` is equivalent everywhere:

- In a **static method**, there is no current instance, so you cannot call an instance method without a receiver.
- In an **inner class** or anonymous class, `this` can point to the inner/anonymous object, not the outer object.
- When overloading is present, the selected method still depends on the number/types of arguments; adding `this.` does not by itself change the method signature.
- If the name collides with a field or local variable, `name` without parentheses reads the variable or field; only `name()` with parentheses is a method call.
- A call with a different receiver such as `other.getName()` can execute on a completely different object.

Example distinguishing field access from a method call:

~~~java
class Student {
    private String name;

    Student(String name) {
        this.name = name; // field = constructor parameter
    }

    String name() {
        return this.name; // field
    }

    String display() {
        return this.name().toUpperCase(); // method call, then String method
    }
}
~~~

`this.name` and `this.name()` are **not the same**. The parentheses distinguish field access from a method call. In the constructor, `this.name = name` handles the parameter shadowing the field; in `display`, `this.name()` executes another method of the same `Student`.

## 4. Splitting Behavior: High-Level Methods Coordinate, Small Methods Handle Processing

A common design approach:

~~~java
class Invoice {
    private long subtotal;
    private long tax;

    void update(long subtotal, long tax) {
        this.requireNonNegative(subtotal);
        this.requireNonNegative(tax);

        long checkedTotal = Math.addExact(subtotal, tax);
        this.subtotal = subtotal;
        this.tax = checkedTotal - subtotal;
    }

    long total() {
        return Math.addExact(this.subtotal, this.tax);
    }

    private void requireNonNegative(long value) {
        if (value < 0) {
            throw new IllegalArgumentException("Số tiền âm");
        }
    }
}
~~~

This is an illustrative snippet. `update` uses a helper to validate inputs; both calls to `this.requireNonNegative(...)` share the current invoice as their receiver. The `total()` method reads two fields of the same object.

When a helper **does not depend on instance state at all**, like `requireNonNegative`, making it `private static` can also be reasonable and makes clear that it depends only on its parameters. `this` helps emphasize the receiver, but it is not always the best design choice for a purely computational helper.

**Important:** splitting methods does not automatically provide atomicity. If one method has already modified state and the next method throws an exception, Java does not roll back automatically. Identify invariants and precompute values that could fail before committing important state.

## 5. Complete Java 17+ Example: Methods Calling Each Other on the Same Object

Create the file **`SameObjectCallsDemo.java`**:

~~~java
public class SameObjectCallsDemo {
    static final class ScoreBoard {
        private final String player;
        private int score;
        private int updates;

        ScoreBoard(String player) {
            if (player == null || player.isBlank()) {
                throw new IllegalArgumentException("Tên không hợp lệ");
            }
            this.player = player;
        }

        ScoreBoard addPoints(int points) {
            this.requirePositive(points);
            int nextScore = Math.addExact(this.score, points);
            int nextUpdates = Math.incrementExact(this.updates);
            this.score = nextScore;
            this.updates = nextUpdates;
            return this;
        }

        ScoreBoard addBonus() {
            return this.addPoints(2);
        }

        String summary() {
            return this.player + ": score=" + this.score
                    + ", updates=" + this.updates;
        }

        boolean sameInstance(ScoreBoard other) {
            return this == other;
        }

        private void requirePositive(int points) {
            if (points <= 0) {
                throw new IllegalArgumentException(
                        "Điểm cộng phải dương");
            }
        }
    }

    public static void main(String[] args) {
        ScoreBoard lan = new ScoreBoard("Lan");
        ScoreBoard mai = new ScoreBoard("Mai");

        lan.addPoints(3).addBonus();
        mai.addPoints(4);

        System.out.println(lan.summary());
        System.out.println(mai.summary());
        System.out.println("Same Lan = " + lan.sameInstance(lan));
        System.out.println("Same Mai = " + lan.sameInstance(mai));

        try {
            lan.addPoints(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Lan after rejection = " + lan.summary());
    }
}
~~~

Commands to run from the directory containing the source file, using JDK 17+:

~~~bash
javac -encoding UTF-8 SameObjectCallsDemo.java
java SameObjectCallsDemo
~~~

**Exact stdout:**

~~~text
Lan: score=5, updates=2
Mai: score=4, updates=1
Same Lan = true
Same Mai = false
Rejected = Điểm cộng phải dương
Lan after rejection = Lan: score=5, updates=2
~~~

**Step-by-step analysis:**

1. `lan.addPoints(3)` is called on the `lan` object, so `this` inside `addPoints` is that exact object.
2. `this.requirePositive(3)` checks the parameter using a `private` helper. If the input is invalid, the method stops with an exception before modifying the score.
3. `Math.addExact` and `Math.incrementExact` precompute the new values. When there is no numeric overflow, both fields of **the same ScoreBoard object** are updated.
4. `return this;` returns **a reference to `lan`** without creating a new object. Therefore, the following `.addBonus()` call is still invoked on `lan`.
5. Inside `addBonus()`, `this.addPoints(2)` again calls a method on the same object. Lan receives a total score of `3 + 2 = 5` and has two updates.
6. `mai.addPoints(4)` runs with a different receiver; it does not modify Lan's object. Mai has a score of 4 and one update.
7. `sameInstance` uses `this == other` to check the identity of the two references. `lan.sameInstance(lan)` is true, while `lan.sameInstance(mai)` is false.
8. `addPoints(0)` throws `IllegalArgumentException` when validation fails; it does not change score/updates, so the final line still shows `score=5, updates=2`.

The example simultaneously demonstrates **calling a helper on the current instance**, **calling back into a public method of the current instance**, and **returning `this` for chaining**. It is designed for single-threaded access; if a mutable `ScoreBoard` is shared across multiple threads, appropriate synchronization is required.

## 6. Returning `this` for Consecutive Calls (Method Chaining)

A method can return the current object if the return type is compatible:

~~~java
class MessageBuilder {
    private final StringBuilder buffer = new StringBuilder();

    MessageBuilder append(String text) {
        if (text == null) {
            throw new IllegalArgumentException("text null");
        }
        this.buffer.append(text);
        return this;
    }

    String build() {
        return this.buffer.toString();
    }
}
~~~

With `new MessageBuilder().append("Java").append(" 17").build()`, the result is `"Java 17"`. Each `append` call continues on **the same builder**.

You should distinguish between:

- `return this;`: returns the same current object.
- `return new MessageBuilder();`: creates a different object if the constructor succeeds.
- `return this.append(text);`: calls the method on the same object and then returns **the result that method returns**. In the ScoreBoard example, that is `this` itself.
- A chain of mutable methods can produce **multiple side effects**. If a later step throws an exception, earlier steps do not roll back automatically.

Chaining is convenient for builders and fluent APIs, but it should only be used when each method has a clear contract: whether it mutates the current object or creates a new value object.

## 7. `this.method()` and Dynamic Dispatch When a Subclass Overrides

A very important point: a method in a superclass can be called on an object belonging to a subclass. When it writes `this.otherMethod()`, the receiver is still **the entire runtime object**, so Java may select the subclass's override.

Create the file **`ThisDispatchDemo.java`**:

~~~java
public class ThisDispatchDemo {
    static class Parent {
        String message() {
            return "Parent";
        }

        String fromParent() {
            return "fromParent -> " + this.message();
        }
    }

    static final class Child extends Parent {
        @Override
        String message() {
            return "Child";
        }

        String fromChild() {
            return this.message() + "/" + super.message();
        }
    }

    public static void main(String[] args) {
        Parent parent = new Parent();
        Parent polymorphic = new Child();
        Child child = new Child();

        System.out.println(parent.fromParent());
        System.out.println(polymorphic.fromParent());
        System.out.println(child.fromChild());
    }
}
~~~

Run:

~~~bash
javac ThisDispatchDemo.java
java ThisDispatchDemo
~~~

Stdout:

~~~text
fromParent -> Parent
fromParent -> Child
Child/Parent
~~~

Explanation:

- `parent.fromParent()` calls `this.message()` on an actual `Parent` object, so `Parent.message()` is selected.
- `polymorphic` is declared with type `Parent` but references a `Child` object. `Parent.fromParent()` runs on the `Child` receiver; the `this.message()` call undergoes **dynamic dispatch** to `Child.message()`.
- `child.fromChild()` calls `this.message()` (Child) and then `super.message()` (Parent) to produce `Child/Parent`.

| Syntax | Meaning |
| --- | --- |
| `this.message()` | Calls on the current object; an override may be selected based on the runtime type |
| `message()` | In a normal instance context, the implicit receiver is the current object |
| `super.message()` | Selects the appropriate superclass implementation in a subclass context |
| `other.message()` | Calls on the object referenced by the `other` variable, which may differ from the current object |
| `Parent.message()` | Cannot replace an instance method's receiver with a class name using static-call syntax |

**Do not confuse overloading and overriding.** The compiler resolves overloads based on the name, argument types/count, and applicability rules. For an overridden instance method, runtime dispatch continues to select the implementation for the actual object type. Writing `this.` does not disable either mechanism.

## 8. `this.method()` and `this(...)` Are Not the Same

Both syntaxes contain the `this` keyword, but one calls a method while the other is **constructor chaining**:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle() {
        this(1, 1);   // calls the two-parameter constructor
    }

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Cạnh không hợp lệ");
        }
        this.width = width;
        this.height = height;
    }

    int area() {
        return this.width * this.height;
    }

    String describe() {
        return "area=" + this.area();
    }
}
~~~

`this(1, 1)` is not a call to a method named `this`; it delegates to a constructor in the same class. In **Java 17**, `this(...)` is an explicit constructor invocation and must be **the first statement** in the constructor body when used. `this.area()` is a normal instance method call with no similar position constraint.

A constructor does not return a value using `return value` syntax, so you cannot write `this(...)` inside an instance method to "re-initialize the object". If you need to restore state, create a named method with appropriate validation.

## 9. Do Not Use `this` from a Static Method

A static method has no **current instance receiver**, so you cannot call an instance method via `this`:

~~~java
class Configuration {
    private String mode = "normal";

    String mode() {
        return this.mode;       // valid: instance method
    }

    static void printMode() {
        // this.mode();         // invalid: this in static context
        // mode();              // invalid: instance method missing receiver
    }
}
~~~

In a static method, an actual object is needed to make the call:

~~~java
class Greeter {
    private final String name;

    Greeter(String name) {
        this.name = name;
    }

    String greeting() {
        return "Chào " + name;
    }

    static String greet(Greeter person) {
        return person.greeting();  // call on a specific receiver
    }
}
~~~

`greet(Greeter person)` is static, yet it can call the instance method `greeting()` through the `person` parameter. If `person == null`, the call throws `NullPointerException`. Replacing `person` with `this` in a static context is a compile error.

Another static method is called via its class name or an appropriate unqualified name, for example `Math.abs(-3)`. There is no need for `this`, and no `this` exists to call it.

## 10. Calling a Method on `this` Differs from Calling on Another Object

~~~java
class Note {
    private String text;

    Note(String text) {
        this.text = text;
    }

    void appendBang() {
        this.append("!");
    }

    void append(String suffix) {
        this.text += suffix;
    }

    String text() {
        return text;
    }
}
~~~

If `Note first = new Note("A")` and `Note second = new Note("B")`, then `first.appendBang()` modifies only the first object: `first.text()` is `"A!"`, and `second.text()` is still `"B"`.

However, if `Note alias = first`, `alias.appendBang()` modifies **the same Note object** as `first`. Different variable names do not imply different objects; this is the concept of **aliasing** for reference values.

In a method that has another object parameter:

~~~java
class Box {
    private int amount;

    void add(int n) {
        amount = Math.addExact(amount, n);
    }

    void passTo(Box target, int n) {
        this.amount -= n;   // modifies the current object
        target.add(n);      // modifies the object that target references
    }
}
~~~

This is a receiver illustration, **not a sufficiently safe money/value transfer API**: it does not yet validate negative numbers, sufficient amount, overflow, null, self-transfer, or race conditions. In real code, all of those constraints must be handled. In the example, `this.amount` and `target.add(n)` can affect two different objects, or the same object if `target == this`.

## 11. Recursion: `this.method()` Can Call Itself

A method calling itself through `this` is a recursive call. Without a stopping condition, it can fill up the call stack:

~~~java
class BadCounter {
    private int count;

    int count() {
        return this.count(); // logic error: calls the method infinitely
    }
}
~~~

This code compiles, but when `count()` is called, it keeps calling `count()` forever and typically causes a `StackOverflowError`. If the intent is to read the field, you must write `return this.count;` **without parentheses**.

Recursion between two methods can also be infinite:

~~~java
class Loop {
    int left() {
        return this.right();
    }

    int right() {
        return this.left();
    }
}
~~~

Valid recursion requires a base case:

~~~java
class Countdown {
    String describe(int n) {
        if (n <= 0) {
            return "done";
        }
        return this.describe(n - 1);
    }
}
~~~

`this.describe(n - 1)` still calls on the same object, but the argument decreases until it stops. Even with a stopping condition, an excessively large `n` value can still exceed the stack limit; for simple linear counting, a loop is usually more appropriate.

## 12. Be Careful When Calling Overridable Methods in a Constructor

A superclass constructor can run while subclass initialization is still incomplete. If the superclass constructor calls `this.method()` and that method is overridden, subclass code may observe fields that have not yet been assigned.

Create the file **`ConstructorDispatchDemo.java`**:

~~~java
public class ConstructorDispatchDemo {
    static class Parent {
        Parent() {
            this.show();
        }

        void show() {
            System.out.println("Parent");
        }
    }

    static class Child extends Parent {
        private String label = "ready";

        @Override
        void show() {
            System.out.println("Child label = " + label);
        }
    }

    public static void main(String[] args) {
        new Child();
    }
}
~~~

Run:

~~~bash
javac ConstructorDispatchDemo.java
java ConstructorDispatchDemo
~~~

Stdout:

~~~text
Child label = null
~~~

When `Parent()` calls `this.show()`, the runtime receiver is already a `Child` object, so the `Child.show()` override is selected. However, the subclass's field initializer `label = "ready"` has not run yet; `label` still holds its default value `null`.

**How to handle it:** do not call overridable methods from a constructor if the logic requires complete state. Prefer appropriate `private`/`static`/`final` helpers, or perform operations that need the full object via a factory or a post-construction startup step. Similarly, do not register callbacks or pass `this` out of the constructor prematurely (*this escape*).

## 13. Inner Classes: `this.method()` and `Outer.this.method()` Have Different Receivers

In a **non-static inner class**, `this` is the inner instance, while `Outer.this` represents the appropriate enclosing outer instance.

Create the file **`NestedMethodCallsDemo.java`**:

~~~java
public class NestedMethodCallsDemo {
    private final String label = "outer";

    private String describe() {
        return "Outer:" + label;
    }

    class Inner {
        private final String label = "inner";

        private String describe() {
            return "Inner:" + label;
        }

        String both() {
            return this.describe()
                    + " | "
                    + NestedMethodCallsDemo.this.describe();
        }
    }

    public static void main(String[] args) {
        NestedMethodCallsDemo outer = new NestedMethodCallsDemo();
        NestedMethodCallsDemo.Inner inner = outer.new Inner();
        System.out.println(inner.both());
    }
}
~~~

Run:

~~~bash
javac NestedMethodCallsDemo.java
java NestedMethodCallsDemo
~~~

Stdout:

~~~text
Inner:inner | Outer:outer
~~~

In `Inner.both()`, `this.describe()` calls on the **inner object**, whereas `NestedMethodCallsDemo.this.describe()` calls on the **outer object**. Having the same method name `describe` does not merge these two receivers into one.

`Outer.this` only makes sense when there is an appropriate enclosing instance; a **static nested class** does not automatically have an enclosing outer instance. Inside a static nested object, `this` is still valid in instance methods of **the static nested class itself**, not of the outer class.

## 14. `this` in Lambdas, Anonymous Classes, and Bound Method References

A lambda declared inside an instance method keeps the interpretation of `this` from its **lexical enclosing context**. An anonymous class, on the other hand, has its own object; `this` inside a method of the anonymous class points to that anonymous object.

~~~java
class JobOwner {
    String label() {
        return "outer";
    }

    Runnable lambdaJob() {
        return () -> System.out.println(this.label());
    }

    Runnable anonymousJob() {
        return new Runnable() {
            private String label() {
                return "anonymous";
            }

            @Override
            public void run() {
                System.out.println(this.label());
                System.out.println(JobOwner.this.label());
            }
        };
    }
}
~~~

**Validity note:** In the anonymous class, the `label()` method in the example is `private`, so it does not override the package-private method of `JobOwner` because it is not the superclass of the anonymous `Runnable`; it is the anonymous object's own method. If you call `new JobOwner().lambdaJob().run()`, stdout is `outer`. If you call `new JobOwner().anonymousJob().run()`, it prints `anonymous` and `outer` in order.

### 14.1. Bound Method Reference `this::method`

Besides calling immediately with `this.method()`, you can write `this::method` to create a **method reference** bound to the current receiver for a functional interface:

~~~java
class Alarm {
    private int rings;

    void ring() {
        this.rings++;
    }

    Runnable callback() {
        return this::ring;
    }

    int ringCount() {
        return rings;
    }
}
~~~

If:

~~~java
Alarm alarm = new Alarm();
Runnable callback = alarm.callback();

callback.run();
callback.run();
System.out.println(alarm.ringCount()); // 2
~~~

then the callback has bound the exact `alarm` object, so `rings` is incremented twice on that object.

**Important difference:** `this.ring()` calls immediately; `this::ring` by itself **does not execute `ring()` yet**, instead creating a method reference to be called later. Registering a callback that carries a reference to `this` also requires paying attention to object lifecycle, especially when the callback is stored or triggered before the constructor finishes.

## 15. Calling a Helper Does Not Make an Operation Thread-Safe

~~~java
class ConcurrentCounter {
    private int value;

    void increment() {
        this.recordIncrement();
    }

    private void recordIncrement() {
        this.value++; // not an atomic read-modify-write
    }
}
~~~

Two threads concurrently calling `increment()` on **the same object** can still suffer from a **lost update**. `this` is not a lock, memory barrier, or atomic variable. Splitting a method into helpers does not make each modification atomic either.

Example using a monitor for the increment operation:

~~~java
class SafeCounter {
    private int value;

    synchronized void increment() {
        this.recordIncrement();
    }

    synchronized int current() {
        return this.value;
    }

    private void recordIncrement() {
        this.value++;
    }
}
~~~

When every access to `value` follows the same synchronization strategy, each `increment()` call holds the receiver's monitor while calling the helper. If other code bypasses the monitor and modifies the field, the design can still be broken.

You should also consider **two variables pointing to the same object**: `Counter a = new Counter(); Counter b = a;` does not create two independent states; calling methods concurrently through `a` and `b` still accesses the same shared object.

## 16. Cases Where Methods Have Results and Side Effects

A method calling another method of the object itself may:

- Only **read data**: `this.currentBalance()`, `this.isEmpty()`.
- **Modify data**: `this.deposit(amount)`, `this.clear()`.
- **Return the receiver itself**: `return this;` for chaining.
- **Return another object**: `return this.createSnapshot();` when a helper creates a snapshot.
- **Throw an exception**: `this.validate(amount)` can block subsequent steps.
- **Call another collaborator**: `this.notifyObservers()` can trigger I/O/callbacks.

`this.method()` by itself **does not tell you** whether the method has side effects; you must understand the called method's contract. For example, a harmless-looking getter that performs lazy initialization changes implementation state. When splitting logic, keep each method's intent clear, especially with command/query APIs.

If multiple methods are called sequentially in one business operation, determine **which operations can fail** and **which state must be preserved on failure**. Java does not automatically undo already-executed calls when a later method throws an exception.

## 17. Common Mistakes

| Mistake or misconception | What is true |
| --- | --- |
| "`this.method()` always calls the method written in this class." | An overridable method can dispatch to a subclass implementation |
| "`method()` has no receiver." | In a normal instance context, the implicit receiver is `this` |
| "Writing `this.` creates a new object." | No, `this` holds a reference to the current object |
| "Calling the same method on two different variables always modifies two objects." | Two variables can alias the same object |
| "`this.field` and `this.field()` are the same." | One accesses a field, while the other calls a method |
| "You can call `this.instanceMethod()` inside a static method." | A static context has no current instance |
| "`this(...)` is a normal method call." | It is a constructor invocation |
| "`super.method()` creates a different superclass object." | No, it selects superclass behavior on the same object |
| "`this.method()` cannot cause recursion." | It can call the same method again, so a base case is needed |
| "Calling a method in a constructor is always safe." | If the method is overridable, it may run on uninitialized subclass state |
| "`this.method()` automatically protects data across threads." | No; a separate concurrency protocol is required |
| "`this::method` calls the method immediately." | It creates a method reference to be executed via a functional interface |

## 18. Self-Check Exercises

**Question 1.** In `Counter.increment()`, do the two calls `this.getCount()` and `this.setCount(n)` create two objects?

**Answer:** No. Both execute on the current `Counter` object; only the receiver's state is read/written.

**Question 2.** Does omitting `this.` in `this.getCount()` change the receiver?

**Answer:** In an appropriate instance context and when `getCount()` resolves to the same method, no. The `getCount()` call uses `this` as its implicit receiver.

**Question 3.** If `Parent.run()` calls `this.show()` while the runtime receiver is `Child` and `Child` overrides `show()`, which implementation runs?

**Answer:** Instance dispatch selects `Child`'s override based on the receiver's runtime type.

**Question 4.** Is `this(10)` at the start of a constructor equivalent to `this.setValue(10)`?

**Answer:** No. `this(10)` calls another constructor in the same class; `this.setValue(10)` calls an instance method.

**Question 5.** Why can the method `int count() { return this.count(); }` cause an error?

**Answer:** It repeatedly calls `count()` itself instead of reading the `count` field at all. Without a base case, this leads to infinite recursion.

**Question 6.** How does `return this;` enable calling `a.add(1).add(2)`?

**Answer:** `add(1)` returns the receiver `a` itself, so the `add(2)` call continues on that same object.

**Question 7.** In a non-static inner class, what is the difference between `this.describe()` and `Outer.this.describe()`?

**Answer:** The first call uses the inner receiver, while the second call uses the appropriate enclosing outer receiver.

**Question 8.** Two threads call `this.increment()` on the same object, and the method uses `value++`. Does writing `this.` make the increment atomic?

**Answer:** No. `this` specifies the receiver and does not create synchronization. A lock, atomic variable, or another design is needed depending on requirements.

**Question 9.** Why can a superclass constructor calling `this.show()` observe null from a subclass field?

**Answer:** Dynamic dispatch can select the subclass implementation while the subclass's initializers/constructor body have not run yet.

**Question 10.** Does `this::ring` increment the `rings` variable immediately when the method reference expression is created?

**Answer:** No. It binds the receiver and behavior; the `rings` variable is incremented when the corresponding functional method is executed.

## 19. Practical Checklist

When you see a method calling another method, ask:

1. **Who is the receiver?** `this`, the implicit current object, `other`, or `Outer.this`?
2. **Does the context have an instance?** Static methods do not have `this`.
3. **How is the method resolved?** Parameter types/count determine overloads; the runtime type can determine overrides.
4. **Are fields of the current object modified?** The other called method may be a query, a command, or both.
5. **Is there a recursive call path?** Is the base case guaranteed to be reached?
6. **Is this running inside a constructor?** Avoid calling overridable methods and exposing an incomplete object.
7. **If returning `this`, does the caller know it receives the same instance?**
8. **If the first method changes state and a subsequent method fails, do invariants still hold?**
9. **If methods run concurrently, is the data properly protected?**
10. **If there is an inner/lambda/anonymous class, which instance does `this` point to?**

**Conclusion:** `this.method()` is an explicit way to **call another method on the current object**. This style supports breaking down behavior and reusing logic within a class, but correctness still depends on the receiver, dynamic dispatch, invariants, initialization order, and concurrency. Accurately distinguishing `this.method()`, `other.method()`, `super.method()`, `Outer.this.method()`, and `this(...)` helps make Java code clearer, easier to test, and less error-prone.
