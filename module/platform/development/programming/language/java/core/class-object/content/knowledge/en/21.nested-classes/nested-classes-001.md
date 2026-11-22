# Classification of Nested Classes: Static, Inner, Local, and Anonymous in Java

In Java, a **nested class** is a class declared within the scope of another class or a context that allows class declarations. Instead of writing only standalone *top-level classes*, Java lets you organize helper classes close to where they are used. Choosing a **static nested class**, **non-static member inner class**, **local class**, or **anonymous class** directly affects access to the enclosing object, how instances are created, name scope, the ability to use local variables, the level of encapsulation, and object lifecycle.

Example of the two kinds of member nested classes:

```java
class Outer {
    private static int shared = 10;
    private int value = 20;

    static class Nested {
        int readShared() {
            return shared;
        }
    }

    class Inner {
        int readBoth() {
            return shared + value;
        }
    }
}
```

How to create objects:

```java
Outer.Nested nested = new Outer.Nested();

Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
```

`Nested` is a **static member nested class**: it does not need an `Outer` instance to be created. `Inner` is a **non-static member inner class**: each instance of it is associated with an **enclosing instance** of `Outer` when instantiated normally.

In a method, you can declare a named class used only within the method scope (**local class**), or create a subclass/implementation without naming the class in the source (**anonymous class**):

```java
void run() {
    int limit = 3;

    class LocalTask implements Runnable {
        @Override
        public void run() {
            System.out.println(limit);
        }
    }

    Runnable first = new LocalTask();

    Runnable second = new Runnable() {
        @Override
        public void run() {
            System.out.println(limit + 1);
        }
    };

    first.run();
    second.run();
}
```

The snippet above is an illustrative method body, not a standalone program. Both classes can use the variable `limit` because it is **final or effectively final**.

This lesson targets **Java 17+**, thoroughly presenting all four types, naming and instantiation, the `this`/`Outer.this` mechanism, access modifiers, captured variables, differences between anonymous classes and lambdas, design choices, common compile/runtime errors, multiple runnable Java files with `javac`/`java` and outputs, exercises, and a checklist.

## 1. The Big Picture: Where Can a Class Reside?

At a conceptual level, there are three locations to distinguish:

1. **Member class:** declared directly in the body of another class, similar to where fields/methods are declared. A member class can be `static` or non-`static`.
2. **Local class:** declared in a block of an execution context, such as a method/constructor body or an appropriate block. It has a name within a local scope and is not a member of the enclosing class.
3. **Anonymous class:** an expression that creates an instance of a class with no declared name in the source code, while simultaneously declaring the implementation/subclass right at the expression.

**Nested class** is the broad term. In Java's classification, **inner class** has a technical meaning: a nested class **not declared static according to the appropriate context**, consisting of non-static member inner classes, non-static local classes, and anonymous classes. In many introductory materials, "inner" is sometimes used loosely for any nested class; when reading advanced documentation, you should use the proper classification.

### Quick Identification Table

| Criterion | Static nested member | Non-static member inner | Local class | Anonymous class |
| --- | --- | --- | --- | --- |
| Has a name in source code? | Yes | Yes | Yes, but only within scope | No self-declared class name |
| Where is it declared? | Member of enclosing type | Member of enclosing class | Inside a local block/context | Right at the `new` expression |
| Requires enclosing `Outer` instance to create? | No | Yes (under normal instantiation) | Depends on static vs. instance context | Depends on context and superclass/target |
| Accesses `static` members of Outer? | Yes, per access | Yes | Yes, per access/scope | Yes, per access/scope |
| Directly uses instance field `Outer.this.field`? | No enclosing Outer instance merely from nesting | Yes, if there is a valid enclosing relationship | Yes, if declared in the corresponding instance context | Yes, if there is a suitable enclosing instance |
| Captures local variables? | No, because it is a member declaration | No, because it is a member declaration | Yes; must be final/effectively final | Yes; must be final/effectively final |
| Typical instantiation | `new Outer.Nested()` | `outer.new Inner()` | `new Local()` in scope | `new Interface() { ... }` |
| Can the class name be reused multiple times in source? | Yes | Yes | Yes, within scope | Cannot invoke constructor by anonymous class name |
| Best used when | Helper does not need outer state | Behavior is tied to an owner instance | Temporary implementation within a scope | Concise, one-off override/implementation |

**Note:** Local/anonymous classes can access enclosing instances when created in an appropriate instance context, but not every local/anonymous class has an enclosing instance of an `Outer`. Determine the **actual context**, rather than just checking whether the code resides in the Outer.java file.

## 2. The Most Important Difference: With or Without an Enclosing Instance

A **non-static member inner class** is associated with an instance of the enclosing class:

```text
Outer object (value = 20)
       ▲
       │ enclosing instance
Inner object
```

The `Inner` object can use `Outer.this.value` when within a valid scope.

For a static nested class:

```text
Outer.Nested object
       │
       └─ does not require an accompanying Outer object
```

It can still access **private static members** of the enclosing class per access rules, or access instance members if **provided with an explicit Outer reference**.

### "Located in Outer.java" Is Not Enough to Prove an Outer Instance Exists

A static nested class is still declared inside the Outer body, but its runtime object **does not need** to be tied to an Outer object. That is why `new Outer.Nested()` is valid without `new Outer()`.

Conversely, `new Outer.Inner()` in a place without an appropriate enclosing instance is invalid syntax/instantiation. The clear way is:

```java
Outer owner = new Outer();
Outer.Inner part = owner.new Inner();
```

## 3. Static Nested Member Class: Concept and Mechanics

A **static nested member class** is a *member type* organized inside another class with the `static` modifier; it does not need an enclosing **object** of the outer class:

~~~java
class Library {
    private static final String PREFIX = "LIB";
    static class Code {
        String label(int id) { return PREFIX + "-" + id; }
    }
}
~~~

`new Library.Code().label(7)` returns `"LIB-7"`. A Code object still has its own instance members; the `static` modifier of the **type** does not make all of its fields static. If Code needs to read instance state of Library, it must receive a `Library` reference **explicitly**. The lesson **Static nested class does not need an enclosing object** is where Builder, access, type parameters, reflection, and class initialization are taught in full.

## 4. Runnable Example: Static Nested Class

Save as **`StaticNestedDemo.java`**:

```java
public class StaticNestedDemo {
    private static final String PREFIX = "ITEM";
    private final String ownerName;

    public StaticNestedDemo(String ownerName) {
        this.ownerName = ownerName;
    }

    public static class Code {
        private final int number;

        public Code(int number) {
            this.number = number;
        }

        public String label() {
            return PREFIX + "-" + number;
        }
    }

    public static void main(String[] args) {
        Code code = new Code(7);
        StaticNestedDemo.Code other =
                new StaticNestedDemo.Code(8);

        System.out.println(code.label());
        System.out.println(other.label());

        StaticNestedDemo owner =
                new StaticNestedDemo("Warehouse");
        System.out.println(owner.ownerName);
    }
}
```

Run on Java 17+:

```bash
javac -encoding UTF-8 StaticNestedDemo.java
java StaticNestedDemo
```

**Exact stdout:**

```text
ITEM-7
ITEM-8
Warehouse
```

Two `Code` instances are created **without needing an Outer instance**. The `PREFIX` field is static; the `ownerName` field is an instance field and cannot be accessed unqualified from `Code.label()`.

### What If Outer Instance State Is Needed?

You can pass a reference **explicitly**:

```java
static class Inspector {
    String inspect(StaticNestedDemo owner) {
        return owner.ownerName;
    }
}
```

The fact that `Inspector` is a static nested class does not prevent it from using a passed-in Outer object; it only means **there is no implicit Outer instance**. It still obeys type checking and access control.

## 5. Why Is a Static Nested Class Often a Good Default Choice?

If a helper only needs the **namespace/encapsulation** of Outer without needing the state of **a specific Outer instance**, `private static class Helper` usually expresses that independence accurately: it is easier to create/test and has no mandatory enclosing-instance association. Classic cases are a `static nested Builder` creating an outer value object (next runnable example), or a `static nested Node` in a collection.

Do not treat this as an absolute rule: an inner member class makes sense when a callback/cursor needs to operate on that specific owner instance. **Choose based on dependency and lifecycle**, not the notion that "static is always faster". The lesson **Choosing between a nested class and a top-level class** presents the design matrix, public API trade-offs, and refactoring.

## 6. Runnable Builder with a Static Nested Class

Save as **`BuilderNestedDemo.java`**:

```java
public final class BuilderNestedDemo {
    private final String host;
    private final int port;

    private BuilderNestedDemo(Builder builder) {
        host = builder.host;
        port = builder.port;
    }

    @Override
    public String toString() {
        return host + ":" + port;
    }

    public static final class Builder {
        private String host = "localhost";
        private int port = 8080;

        public Builder host(String value) {
            host = value;
            return this;
        }

        public Builder port(int value) {
            port = value;
            return this;
        }

        public BuilderNestedDemo build() {
            return new BuilderNestedDemo(this);
        }
    }

    public static void main(String[] args) {
        BuilderNestedDemo first =
                new Builder().build();

        BuilderNestedDemo second =
                new Builder().host("example.test").port(9000).build();

        System.out.println(first);
        System.out.println(second);
    }
}
```

```bash
javac -encoding UTF-8 BuilderNestedDemo.java
java BuilderNestedDemo
```

Stdout:

```text
localhost:8080
example.test:9000
```

A new `Builder` is created **without needing a `BuilderNestedDemo` instance** beforehand. Builder can access the private constructor/fields through the nesting access relationship.

## 7. Non-Static Member Inner Class: Associated with an Outer Instance

A **non-static member inner class** associates each inner object with an appropriate **enclosing instance**:

~~~java
class Account {
    private int balance;
    class Reader {
        int currentBalance() { return balance; }
    }
}
~~~

~~~java
Account account = new Account();
Account.Reader reader = account.new Reader();
~~~

`Reader` is a real class that can have constructors, fields, methods, and implement interfaces; it **does not automatically extend Account**. From an instance method of Account, `new Reader()` can be used; from a static context, an owner must be provided explicitly. The lesson **Inner member class associated with an enclosing object** covers identity across multiple owners, generic membership, and lifetime principles in depth.

## 8. Runnable Example: Inner Class Reading/Modifying Outer State

Save as **`InnerClassDemo.java`**:

```java
public class InnerClassDemo {
    private final String accountId;
    private int balance;

    public InnerClassDemo(String accountId, int balance) {
        this.accountId = accountId;
        this.balance = balance;
    }

    public class Teller {
        public void deposit(int amount) {
            balance += amount;
        }

        public String receipt() {
            return accountId + ":" + balance;
        }
    }

    public Teller createTeller() {
        return new Teller();
    }

    public static void main(String[] args) {
        InnerClassDemo a = new InnerClassDemo("A", 100);
        InnerClassDemo b = new InnerClassDemo("B", 200);

        InnerClassDemo.Teller tellerA = a.new Teller();
        InnerClassDemo.Teller tellerB = b.createTeller();

        tellerA.deposit(20);
        tellerB.deposit(5);

        System.out.println(tellerA.receipt());
        System.out.println(tellerB.receipt());
    }
}
```

```bash
javac -encoding UTF-8 InnerClassDemo.java
java InnerClassDemo
```

Stdout:

```text
A:120
B:205
```

The two `Teller` objects are both of type `InnerClassDemo.Teller`, yet they are bound to **two different enclosing instances**. Modifying `balance` through Teller A does not touch B's balance.

### Distinguishing Type and Enclosing Instance

`InnerClassDemo.Teller` is **the same member class** regardless of whether it was created from instance `a` or `b`. Java does not generate a type `a.Teller` distinct from type `b.Teller`. It is the **reference bound to the instance at runtime** that determines which owner `Teller` reads/modifies.

## 9. `Outer.this` and `Outer.super`

In an inner instance method, `this` is the **inner object**, and `Outer.this` is the **enclosing Outer object** selected by lexical nesting. For example:

~~~java
class Outer {
    String name = "OUTER";
    class Inner {
        String name = "INNER";
        String describe() {
            return this.name + "/" + Outer.this.name;
        }
    }
}
~~~

`describe()` returns `"INNER/OUTER"`. With multiple levels of nesting, qualified `TypeName.this` is only valid when a corresponding enclosing instance exists; it does not cross a static boundary to create a nonexistent Outer object. The lesson **Name shadowing and qualification with Outer.this** explains local/field shadowing, lambdas/anonymous classes, `Outer.super`, and multiple nested scopes.

## 10. Runnable: `this` Differs from `Outer.this`

Save as **`OuterThisDemo.java`**:

```java
public class OuterThisDemo {
    private final String name = "OUTER";

    public class Inner {
        private final String name = "INNER";

        public String show() {
            return this.name + " / " + OuterThisDemo.this.name;
        }

        public boolean sameOwner(OuterThisDemo other) {
            return OuterThisDemo.this == other;
        }
    }

    public static void main(String[] args) {
        OuterThisDemo outer = new OuterThisDemo();
        OuterThisDemo.Inner inner = outer.new Inner();

        System.out.println(inner.show());
        System.out.println(inner.sameOwner(outer));
        System.out.println(inner.sameOwner(new OuterThisDemo()));
    }
}
```

```bash
javac -encoding UTF-8 OuterThisDemo.java
java OuterThisDemo
```

Stdout:

```text
INNER / OUTER
true
false
```

`OuterThisDemo.this` returns the enclosing instance bound to the inner object; it does not automatically create a new object.

## 11. Does an Inner Class Automatically Use the Outer Instance as Its Superclass?

**No.** An enclosing instance is **different from** an `extends` inheritance relationship.

```java
class Outer {
    class Inner {
    }
}
```

`Inner` **does not** automatically extend Outer. If no other superclass is declared, Inner extends Object like a normal class.

- **Nesting** provides access/scope and can provide an enclosing instance.
- **Inheritance** provides a subtype relationship, overridden methods, and method/field inheritance.

The statement `Inner is-a Outer` is false unless the Inner class is actually declared to extend Outer and satisfies the constraints. A member inner class normally does not have a subtype relationship with its enclosing class.

### So Can You Use an Interface?

Yes:

```java
interface Task {
    void execute();
}

class Owner {
    class Worker implements Task {
        @Override
        public void execute() {
            System.out.println("done");
        }
    }
}
```

The inner class is an implementation of Task while simultaneously being bound to an Owner instance.

## 12. Private Access Scope Between the Enclosing Class and Nested Classes

Nested classes and the enclosing type can access each other's `private` members according to the nesting context, but **access permission** is different from **how the receiver is obtained**. For example:

~~~java
class Vault {
    private int secret = 42;
    static class Inspector {
        int read(Vault source) { return source.secret; }
    }
    class Reader {
        int read() { return secret; }
    }
}
~~~

Static nested `Inspector` must receive a Vault instance; member inner `Reader` has an enclosing Vault instance. Nesting does not expose private APIs to the outside. Since Java 11, the JVM has had **nestmate access control**; do not depend on specific synthetic accessor names. The lesson **Accessing private members and enclosing members** covers all private and multi-level cases as well as how the compiler/JVM implements them.

## 13. Runnable: Both Static and Inner Classes Read Private State

Save as **`PrivateAccessDemo.java`**:

```java
public class PrivateAccessDemo {
    private final int number;

    public PrivateAccessDemo(int number) {
        this.number = number;
    }

    private static class StaticReader {
        int read(PrivateAccessDemo target) {
            return target.number;
        }
    }

    private class InnerReader {
        int read() {
            return number;
        }
    }

    public static void main(String[] args) {
        PrivateAccessDemo outer = new PrivateAccessDemo(42);

        StaticReader first = new StaticReader();
        InnerReader second = outer.new InnerReader();

        System.out.println(first.read(outer));
        System.out.println(second.read());
    }
}
```

```bash
javac -encoding UTF-8 PrivateAccessDemo.java
java PrivateAccessDemo
```

Stdout:

```text
42
42
```

Both nested classes are private to external code, but `main` of the enclosing class is allowed to instantiate/access them per access rules.

## 14. Member Access Modifiers: A Nested Type Can Be public/private/protected

A member nested class can be declared like other class members:
- `public static class Builder`;
- `private static class Node`;
- `protected class InnerHelper`;
- Package-private `class Helper`.

When part of a published API, a nested type can appear in signatures:

```java
public final class Result {
    public static record Error(String code) {}
}
```

However, not every kind of nested class is suitable as a public API. A private implementation helper should not be unintentionally exposed through an inaccessible public return type.

### Top-Level Classes and Nested Member Classes Differ

A regular top-level class has top-level access of `public` or package-private; **it cannot be declared top-level private/protected**.

A member class placed inside an enclosing type **can be private/protected** according to applicable language rules.

A local/anonymous class **is not a member class** and does not carry the same set of access modifiers as member types. A local class name only lives within its declaration scope.

## 15. Static Context and Access to Instance Members

A classic mistake:

```java
class Outer {
    private int count;

    static class Nested {
        int read() {
            // return count; // Error: no Outer instance.
            return 0;
        }
    }
}
```

Fix it by passing an instance:

```java
static class Nested {
    int read(Outer owner) {
        return owner.count;
    }
}
```

Or if by nature the class must be tied to an Outer instance, replace it with a non-static member inner class:

```java
class Inner {
    int read() {
        return count;
    }
}
```

**Design rule:** choose static nested for a **naming/encapsulation** relationship; choose inner when the **owner instance** relationship is part of the contract.

## 16. Member Inner Classes and Retaining References to Outer: Watch the Lifecycle

A non-static member inner object is tied to an enclosing instance. If a long-lived registry holds onto an inner listener, it **can extend the owner's lifetime** longer than expected:

~~~text
Event bus → inner listener → enclosing controller
~~~

This is a **reachability and lifecycle** issue, not "every inner class leaks". When a listener may continue to exist for a long time, you should unregister it according to its lifecycle or choose a static nested class/explicit dependency if appropriate. Converting to a static nested class **does not fix** retention if the helper itself still holds a strong reference to the owner.

The lesson **Implicit references to the enclosing object and memory retention risks** is where GC roots, callbacks, lambdas, method references, subscription cleanup, weak refs, and heap inspection are analyzed. This is only an early warning for choosing the class kind.

## 17. Local Class: A Named Class Confined to Local Scope

A **local class** is declared inside an appropriate block of a method/constructor, or an equivalent context under Java rules:

```java
void process() {
    class Formatter {
        String format(int n) {
            return "n=" + n;
        }
    }

    Formatter formatter = new Formatter();
}
```

`Formatter` has a **type name in scope** from its point of declaration according to scoping rules, but code outside the method cannot directly write `new Formatter()` because that name is not visible.

A local class is useful when:
- The logic is substantial enough to warrant a class name, constructor, and multiple methods.
- The type is only used within a single method/block.
- It needs to read some final/effectively final local variables.
- It is not worth creating a member nested class or top-level class.

### A Local Class Is a Full-Fledged Class

It can:
- Implement an interface or extend a superclass.
- Have a constructor and instance members.
- Override methods.
- Be instantiated multiple times within the scope.
- Be returned as an interface/superclass type if appropriate.

**However,** the local class name cannot be used directly outside its declaration scope; the caller typically sees only the public type/interface that the local class implements.

## 18. Runnable: Local Class with a Constructor and Two Instances

Save as **`LocalClassDemo.java`**:

```java
public class LocalClassDemo {
    interface Greeter {
        String greet();
    }

    static Greeter create(String prefix) {
        int punctuationCount = 2;

        class LocalGreeter implements Greeter {
            private final String name;

            LocalGreeter(String name) {
                this.name = name;
            }

            @Override
            public String greet() {
                return prefix + " " + name
                        + "!".repeat(punctuationCount);
            }
        }

        return new LocalGreeter("An");
    }

    public static void main(String[] args) {
        Greeter first = create("Xin chào");
        Greeter second = create("Hello");

        System.out.println(first.greet());
        System.out.println(second.greet());
    }
}
```

```bash
javac -encoding UTF-8 LocalClassDemo.java
java LocalClassDemo
```

Stdout:

```text
Xin chào An!!
Hello An!!
```

`LocalGreeter` is a **named local class**, yet the method returns the `Greeter` interface. The code in `main` does not need (and outside the scope cannot) use the name `LocalGreeter`.

### What Is Captured?

- `prefix`: parameter of `create`, effectively final.
- `punctuationCount`: local variable, effectively final.
- `name`: an instance field belonging to each LocalGreeter object, not a captured local variable.

Two calls to `create` produce two local class instances with different captured values.

## 19. Captured Local Variables: `final` or `effectively final`

Local and anonymous classes can reference:
- Local variables;
- Method parameters;
- Exception parameters and variables within permissible scopes;

if those variables are subject to capture and satisfy the **final or effectively final** condition along with definite assignment/scope constraints.

Valid example:

```java
void run() {
    int threshold = 10;

    class Checker {
        boolean test(int value) {
            return value > threshold;
        }
    }

    System.out.println(new Checker().test(12));
}
```

`threshold` is not written with `final`, yet it is never reassigned after initialization; it is **effectively final**.

Invalid example:

```java
void run() {
    int threshold = 10;

    class Checker {
        boolean test(int value) {
            return value > threshold;
        }
    }

    threshold = 20; // Makes threshold not effectively final.
}
```

If the local class references `threshold` in a way that requires capture, reassigning the variable causes the compiler to reject it.

### Why Does Java Impose This Constraint?

A local class instance can outlive the stack frame of a method that has already finished. It must store/maintain captured values according to the semantics and cannot assume the local variable remains a permanently live stack slot for the class to read/write.

The final/effectively final constraint avoids the illusion that the same local variable can be directly "jointly modified" by long-lived callbacks.

**Capturing a reference variable does not mean the referenced object is immutable.**

## 20. Runnable: Capturing a Final Reference While Mutating the Object

Save as **`CapturedReferenceDemo.java`**:

```java
public class CapturedReferenceDemo {
    interface CounterView {
        int read();
    }

    static CounterView make(int[] shared) {
        class Reader implements CounterView {
            @Override
            public int read() {
                return shared[0];
            }
        }

        return new Reader();
    }

    public static void main(String[] args) {
        int[] data = {1};
        CounterView reader = make(data);

        System.out.println(reader.read());

        data[0] = 7;
        System.out.println(reader.read());
    }
}
```

```bash
javac -encoding UTF-8 CapturedReferenceDemo.java
java CapturedReferenceDemo
```

Stdout:

```text
1
7
```

The parameter `shared` is not reassigned in `make`, so it is effectively final; the local class captures **the reference to the same array**. The array remains mutable, and changing an element affects subsequent reads.

**Warning:** this is a single-threaded example. If the array is mutated across multiple threads, proper synchronization/visibility is needed; effectively final does not automatically make a mutable object thread-safe.

## 21. A Local Class from a Static Context Has No Enclosing Outer Instance

Example:

```java
class Outer {
    private int value = 1;

    static void run() {
        class Local {
            int get() {
                // return value; // No Outer instance.
                return 0;
            }
        }
    }
}
```

Because `run` is a static method, the local class does not have `Outer.this` merely because the code appears inside Outer.

Fix:
- Pass a specific `Outer` object to the Local constructor.
- Or move the logic to an instance method if it is truly tied to an enclosing instance.
- Or use only valid static state.

Conversely, when a local class is declared in an **instance method of Outer**, it can access `Outer.this`/appropriate instance members while also capturing local variables.

### Do Not Equate a Local Class with an "Inner Class Member"

A local class is not a member in the class body, so it cannot be referred to from the outside using the `Outer.Local` syntax like `Outer.Nested` or `Outer.Inner`.

## 22. Runnable: Local Class in an Instance Method Using `Outer.this`

Save as **`LocalEnclosingDemo.java`**:

```java
public class LocalEnclosingDemo {
    private final String owner;

    LocalEnclosingDemo(String owner) {
        this.owner = owner;
    }

    interface Task {
        String describe();
    }

    Task createTask(int id) {
        class LocalTask implements Task {
            @Override
            public String describe() {
                return LocalEnclosingDemo.this.owner
                        + "#" + id;
            }
        }

        return new LocalTask();
    }

    public static void main(String[] args) {
        LocalEnclosingDemo a =
                new LocalEnclosingDemo("A");
        LocalEnclosingDemo b =
                new LocalEnclosingDemo("B");

        Task taskA = a.createTask(10);
        Task taskB = b.createTask(20);

        System.out.println(taskA.describe());
        System.out.println(taskB.describe());
    }
}
```

```bash
javac -encoding UTF-8 LocalEnclosingDemo.java
java LocalEnclosingDemo
```

Stdout:

```text
A#10
B#20
```

`id` is captured under the effectively final constraint; `owner` comes from the enclosing instance. These two data sources have **different mechanisms**, even though both are accessible inside the local class's method.

## 23. A Local Class Can Be Returned via an Interface After the Method Ends

A local class has a name visible only inside the method, yet its object can live on:

```java
Runnable makeTask() {
    int number = 7;

    class LocalTask implements Runnable {
        @Override
        public void run() {
            System.out.println(number);
        }
    }

    return new LocalTask();
}
```

The caller then invokes `task.run()` after the `makeTask` method has returned. This is valid; the captured value of `number` is still used by the instance.

**Do not confuse type-name scope with object lifetime:**
- The name `LocalTask` can only be written within the local scope.
- A runtime instance of LocalTask can be stored in a collection, returned, registered as a callback, or run in a thread later.

That is precisely why you need to check whether capturing the outer object/dependencies causes resources to be retained longer than intended.

## 24. Anonymous Class: An Unnamed Class at a `new` Expression

An anonymous class is typically written:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
```

The code creates **an instance of a class with no declared name in source**; that class implements `Runnable` and overrides `run()`.

There is no separate declaration:

```java
class MyRunnable implements Runnable { ... }
```

and there is no constructor `new MyRunnable()` either, because an anonymous class has no source name to invoke again in that way.

### Two Common Forms

**Implementing an interface:**

```java
SomeInterface ref = new SomeInterface() {
    @Override
    public void execute() {
        // ...
    }
};
```

**Subclassing a named class:**

```java
Base ref = new Base(constructorArgs) {
    @Override
    public void work() {
        // ...
    }
};
```

In the class-extending form, `Base` must allow subclassing and valid constructor invocation. An anonymous class cannot extend a final class to override it.

**You cannot "implement multiple interfaces" using the syntax `new A(), B() { }`**. An anonymous class declaration is based on one specified class or interface; additional interfaces can be inherited indirectly through the superclass.

## 25. Runnable: Anonymous Implementation of an Interface

Save as **`AnonymousInterfaceDemo.java`**:

```java
public class AnonymousInterfaceDemo {
    interface Formatter {
        String format(String value);
    }

    public static void main(String[] args) {
        Formatter upper = new Formatter() {
            @Override
            public String format(String value) {
                return value.toUpperCase(
                        java.util.Locale.ROOT);
            }
        };

        Formatter wrapped = new Formatter() {
            @Override
            public String format(String value) {
                return "[" + value + "]";
            }
        };

        System.out.println(upper.format("java"));
        System.out.println(wrapped.format("java"));
    }
}
```

```bash
javac -encoding UTF-8 AnonymousInterfaceDemo.java
java AnonymousInterfaceDemo
```

Stdout:

```text
JAVA
[java]
```

Each `new Formatter() { ... }` is an independent anonymous class expression; both objects have the static type `Formatter` when viewed through the variables, yet they execute different overridden logic.

## 26. Anonymous Subclass of a Concrete Class

Example superclass:

```java
class Message {
    private final String text;

    Message(String text) {
        this.text = text;
    }

    String render() {
        return text;
    }
}
```

Anonymous subclass:

```java
Message message = new Message("hello") {
    @Override
    String render() {
        return "[" + super.render() + "]";
    }
};
```

Characteristics:
- Has a **constructor call to the superclass** with the argument `"hello"`.
- Does not declare its own constructor named after the anonymous class.
- Can use an **instance initializer block** if additional initialization logic is needed, but avoid hard-to-understand side effects.
- Can use `super.render()` to call the superclass implementation.
- Cannot override a `final` method.

### When Is It Worth Using?

If you only need to alter one method in a single place and do not need reuse or a type name, an anonymous subclass can be concise. If the logic is complex, involves multiple differently configured instances, or needs independent testing, a named class is usually easier to maintain.

## 27. Runnable: Anonymous Subclass Calling `super`

Save as **`AnonymousSubclassDemo.java`**:

```java
class Message {
    private final String text;

    Message(String text) {
        this.text = text;
    }

    String render() {
        return text;
    }
}

public class AnonymousSubclassDemo {
    public static void main(String[] args) {
        Message basic = new Message("hello");

        Message decorated = new Message("hello") {
            @Override
            String render() {
                return "[" + super.render() + "]";
            }
        };

        System.out.println(basic.render());
        System.out.println(decorated.render());
        System.out.println(basic == decorated);
    }
}
```

```bash
javac -encoding UTF-8 AnonymousSubclassDemo.java
java AnonymousSubclassDemo
```

Stdout:

```text
hello
[hello]
false
```

The variable `decorated` is declared with type `Message`, yet the runtime instance belongs to an anonymous subclass of Message; the call to `render()` dispatches to the override.

## 28. Anonymous Classes Also Capture Local Variables

```java
int offset = 5;

java.util.function.IntUnaryOperator add =
        new java.util.function.IntUnaryOperator() {
            @Override
            public int applyAsInt(int value) {
                return value + offset;
            }
        };
```

`offset` must be final/effectively final.

### Having No Name Does Not Mean Having No State

An anonymous class can have:
- Instance fields;
- Initializer blocks;
- Methods;
- References to the enclosing instance if the context is valid;
- Captured local variables;
- Overrides of superclass methods.

However, the caller holds the object via a **static type** such as an interface/superclass and cannot simply call a method that appears only in the anonymous class and is not declared by the static type.

### Example of a New Method Not Visible Through the Interface

```java
Runnable task = new Runnable() {
    public void helper() {
        System.out.println("help");
    }

    @Override
    public void run() {
        helper();
    }
};

task.run();
// task.helper(); // Does not compile because Runnable does not have helper().
```

Code inside the anonymous class can call `helper()`, but the API of the `task` variable exposes only the methods of `Runnable` (along with valid Object methods).

## 29. Runnable: Anonymous Class Using a Captured Value and Internal State

Save as **`AnonymousCaptureDemo.java`**:

```java
import java.util.function.IntSupplier;

public class AnonymousCaptureDemo {
    static IntSupplier create(int start) {
        int increment = 2;

        return new IntSupplier() {
            private int value = start;

            @Override
            public int getAsInt() {
                value += increment;
                return value;
            }
        };
    }

    public static void main(String[] args) {
        IntSupplier first = create(10);
        IntSupplier second = create(100);

        System.out.println(first.getAsInt());
        System.out.println(first.getAsInt());
        System.out.println(second.getAsInt());
    }
}
```

```bash
javac -encoding UTF-8 AnonymousCaptureDemo.java
java AnonymousCaptureDemo
```

Stdout:

```text
12
14
102
```

Distinctions:
- `start` and `increment` are captured parameters/local values.
- `value` is a **mutable instance field** belonging to each individual anonymous object.
- The effectively-final restriction applies to **captured local variables**; it does not forbid an anonymous object from having mutable instance fields.

**Not automatically thread-safe:** calling `getAsInt` concurrently on the same anonymous instance has a data race on `value` without synchronization.

## 30. `this` Differs Between an Anonymous Class and a Lambda

An anonymous class creates a new **class instance**. Inside an anonymous class instance method, `this` is the **anonymous instance**.

A lambda expression has a different **lexical scope**: `this` inside a lambda (when valid) means `this` of the enclosing context, **not a "lambda object this"** created separately by the lambda in source.

This is a major difference even though both can be assigned to the functional interface `Runnable`:

```java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(this.getClass().getSimpleName());
    }
};

Runnable lambda = () -> {
    // this here points to the enclosing instance, if any.
};
```

Generated class names for anonymous classes/lambdas **should not be placed into fixed expected stdout** if the code checks runtime type names; instead, compare identity with the owner.

### One More Thing: Overloading and Shadowing

An anonymous class is its own class scope; it can declare fields/methods that shadow names from the enclosing context. A lambda does not create a Java-source-style class scope like that and has its own name resolution rules.

Therefore, replacing an anonymous class with a lambda **is not always a refactoring that preserves all behavior**, even when the implementation has only a single abstract method.

## 31. Runnable: Comparing `this` of an Anonymous Class and a Lambda

Save as **`ThisLambdaComparisonDemo.java`**:

```java
public class ThisLambdaComparisonDemo {
    private final String ownerName = "OWNER";

    void demonstrate() {
        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        "anonymous this is owner = "
                        + ((Object) this == ThisLambdaComparisonDemo.this));
            }
        };

        Runnable lambda = () -> {
            System.out.println(
                    "lambda this is owner = "
                    + (this == ThisLambdaComparisonDemo.this));
        };

        anonymous.run();
        lambda.run();
        System.out.println(ownerName);
    }

    public static void main(String[] args) {
        new ThisLambdaComparisonDemo().demonstrate();
    }
}
```

```bash
javac -encoding UTF-8 ThisLambdaComparisonDemo.java
java ThisLambdaComparisonDemo
```

Stdout:

```text
anonymous this is owner = false
lambda this is owner = true
OWNER
```

Inside the anonymous `run`, `this` is the instance of the anonymous Runnable implementation, so it differs from Outer.this. Inside the lambda, `this` is the enclosing `ThisLambdaComparisonDemo` instance.

### Does a Static Method Containing a Lambda Have `this`?

No. `this` does not become valid in a static context merely by being written inside a lambda. A lambda does not automatically create an enclosing instance for a static method.

## 32. Lambda and Anonymous Class: Which Should You Choose?

For a **functional interface** (only one abstract method according to the applicable definition), a lambda is usually concise:

```java
Runnable task = () -> System.out.println("done");
```

Anonymous class:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("done");
    }
};
```

**Usually prefer a lambda when**:
- The goal is simply to provide a short behavior for a functional interface.
- You do not need a separate class with internal mutable fields/methods.
- You do not need an anonymous `this` or a subclass-specific initializer.
- You do not need to override multiple methods of a concrete superclass.

**Use an anonymous class when**:
- You need to subclass a concrete class right at a single point.
- An interface/class has multiple methods that need to be overridden in an inline implementation.
- You need the `super` behavior of an anonymous subclass.
- You need explicit instance state/methods inside the callback object.
- The `this`/scope semantics of an anonymous class are intentional.

**Use a named local/member class when** the implementation is long, has multiple behaviors, needs debugging/testing/reuse, or a type name has explanatory value.

### Are Lambdas Anonymous Classes?

You should not equate them. A lambda is a **lambda expression** with its own semantics in Java; the runtime may use an implementation strategy such as invokedynamic. You should not rely on class file names or the identity of a lambda object as if it were an anonymous class declared with `new Interface() { ... }`.

## 33. Anonymous Classes and Abstract Classes

An anonymous class can create a subclass of an abstract class by providing the missing implementations:

```java
abstract class Operation {
    abstract int compute(int a, int b);
}

Operation sum = new Operation() {
    @Override
    int compute(int a, int b) {
        return a + b;
    }
};
```

If the abstract class has a constructor that requires arguments, use the `new AbstractBase(args) { ... }` syntax with the appropriate constructor invocation.

**You cannot create an anonymous subclass of a final class.** With a Java 17 sealed hierarchy, you must also abide by the list of permitted direct subclasses and corresponding constraints; you cannot arbitrarily use an anonymous subclass to bypass sealed restrictions.

## 34. Runnable: Anonymous Subclass of an Abstract Class

Save as **`AnonymousAbstractDemo.java`**:

```java
abstract class Operation {
    private final String label;

    Operation(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }

    abstract int apply(int a, int b);
}

public class AnonymousAbstractDemo {
    public static void main(String[] args) {
        Operation multiply = new Operation("multiply") {
            @Override
            int apply(int a, int b) {
                return a * b;
            }
        };

        Operation maximum = new Operation("max") {
            @Override
            int apply(int a, int b) {
                return Math.max(a, b);
            }
        };

        System.out.println(multiply.label()
                + "=" + multiply.apply(3, 4));
        System.out.println(maximum.label()
                + "=" + maximum.apply(3, 4));
    }
}
```

```bash
javac -encoding UTF-8 AnonymousAbstractDemo.java
java AnonymousAbstractDemo
```

Stdout:

```text
multiply=12
max=4
```

Both anonymous objects have the static type `Operation` when stored in the variables, while the runtime subclasses have different `apply` implementations.

## 35. Combining Nested Class Kinds in a System

A class is not limited to using only one form of nesting. They can serve different purposes:

- **Static nested `Builder`**: constructs an object without needing an already-completed enclosing instance.
- **Member inner `View`**: represents a view bound to a specific instance.
- **Local `Validator`**: named logic needed only inside one method.
- **Anonymous `Runnable`**: a one-off callback with concise behavior.
- **Lambda**: another option for functional behavior, not a kind of anonymous class.

There is no principle that "the deeper the nested class, the better". Nesting across too many levels can cause poor readability, coupling, and confusion over `this`/scope.

## 36. Comprehensive Program Combining All Four Kinds

Save as **`NestedKindsDemo.java`**:

```java
public class NestedKindsDemo {
    private final String owner;

    NestedKindsDemo(String owner) {
        this.owner = owner;
    }

    static class StaticHelper {
        String describe() {
            return "static";
        }
    }

    class InnerHelper {
        String describe() {
            return "inner:" + owner;
        }
    }

    interface Action {
        String run();
    }

    Action localAction(int n) {
        class LocalAction implements Action {
            @Override
            public String run() {
                return "local:" + n;
            }
        }

        return new LocalAction();
    }

    Action anonymousAction(int n) {
        return new Action() {
            @Override
            public String run() {
                return "anonymous:" + n;
            }
        };
    }

    public static void main(String[] args) {
        NestedKindsDemo outer = new NestedKindsDemo("A");

        StaticHelper one = new StaticHelper();
        NestedKindsDemo.InnerHelper two =
                outer.new InnerHelper();
        Action three = outer.localAction(7);
        Action four = outer.anonymousAction(8);

        System.out.println(one.describe());
        System.out.println(two.describe());
        System.out.println(three.run());
        System.out.println(four.run());
    }
}
```

```bash
javac -encoding UTF-8 NestedKindsDemo.java
java NestedKindsDemo
```

**Stdout:**

```text
static
inner:A
local:7
anonymous:8
```

Summary:
- `StaticHelper` is created without an Outer instance, using only the namespace name.
- `InnerHelper` is bound to the outer instance `outer`.
- `LocalAction` is a named type visible only inside `localAction` and captures `n`.
- The anonymous implementation is declared inline inside `anonymousAction` and also captures `n`.

### Lessons from the Comprehensive Example

All four kinds produce objects whose methods can be called like any Java class instance. The differences lie in **declaration location, enclosing context, capture, and construction**, not in each kind having some "special kind of memory" separate from ordinary objects.

## 37. Do Local and Anonymous Classes "Store Local Variables on the Stack"?

You should not think of a runtime instance as merely holding a "pointer to a stack slot" of a method that has already finished. The needed values/references are captured according to language semantics; implementation details are chosen by the compiler/JVM.

Example:

```java
Runnable createTask() {
    String message = "done";
    return () -> System.out.println(message);
}
```

After `createTask()` returns, the Runnable can still use `message` when executed. It is valid for a lambda/local/anonymous class to outlive the method, as long as the object remains reachable.

### Capturing a Reference Can Keep an Object Alive Longer

If a captured local variable points to a large object, a long-lived callback can retain a reference to that object. Likewise, a local/anonymous class in an enclosing instance context can retain the enclosing object when needed. Therefore:
- Do not capture an entire service/controller if only an ID/String is needed.
- Check the lifecycle when registering a long-lived callback.
- Unregister listeners/subscriptions at the right time.
- Avoid unnecessary references through an enclosing instance.

## 38. Is an Explicit `final` Keyword Required?

It is not mandatory for **effectively final** variables:

```java
int factor = 3;

Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(factor);
    }
};
```

`factor` is effectively final as long as it is not reassigned according to the rules.

However, the code:

```java
int factor = 3;
factor++;
Runnable task = () -> System.out.println(factor);
```

is invalid because `factor` has been modified and is not effectively final.

A **mutable object** referenced by a final variable can change its contents:

```java
final java.util.List<String> items =
        new java.util.ArrayList<>();

Runnable task = () -> System.out.println(items.size());

items.add("A");
task.run(); // 1
```

However, concurrent code requires synchronization when one thread mutates the list and another thread reads it; you cannot rely on `final` alone.

### Is the Array-Counter Workaround Advisable?

Some people write `final int[] count = {0};` and then modify `count[0]++` inside a lambda/anonymous class. The syntax may compile, but:
- It makes state implicitly mutable.
- It is not thread-safe.
- It obscures intent.
- It may be better to use an explicitly designed holder object, `AtomicInteger` if appropriate for the problem, or change the API to return a result.

**Do not treat a single-element array as the default way to "bypass effectively final".**

## 39. Is a `private static` Member Nested Class Independent of the Enclosing Type?

It is independent with respect to the **enclosing instance requirement**, but not completely independent:
- The type name is still a member of the enclosing type.
- It can access private static state/enclosing private instance state via a reference.
- It is compiled and carries nest membership under JVM semantics.
- Its visibility is governed by its modifier (`private`, package-private...).
- It may depend on constants/static initialization of the enclosing type.

Therefore, when saying "a static nested class is independent", it should be understood as **having no implicit Outer instance**, not "having no relationship whatsoever with Outer".

## 40. Nested Interfaces, Records, and Enums: Extending the Classification

Alongside nested **classes**, Java also allows **nested interfaces**, **nested enums**, and **nested records** in appropriate contexts. Some of these nested types are **implicitly static** under language rules.

Example:

```java
class Api {
    interface Handler {
        String handle(String input);
    }

    record Result(int code, String message) {
    }

    enum State {
        READY, DONE
    }
}
```

You can use:

```java
Api.Handler handler = input -> input;
Api.Result result = new Api.Result(200, "OK");
Api.State state = Api.State.READY;
```

No Api instance is needed to create Result or access the enum state.

### Note on Java 17

Nested record declarations have static semantics; a record is a final class. A record does not automatically have an implicit enclosing instance merely because it is placed inside another class.

**Do not call a nested interface a "non-static inner interface"** in the sense of a member inner class. A nested interface type follows the appropriate static semantics.

## 41. Runnable: Nested Interface/Record/Enum

Save as **`NestedTypesDemo.java`**:

```java
public class NestedTypesDemo {
    interface Handler {
        Result handle(String input);
    }

    record Result(int code, String data) {
    }

    enum State {
        OK, ERROR
    }

    public static void main(String[] args) {
        Handler handler =
                input -> new Result(200, input.toUpperCase(
                        java.util.Locale.ROOT));

        Result result = handler.handle("java");

        System.out.println(result);
        System.out.println(State.OK);
    }
}
```

```bash
javac -encoding UTF-8 NestedTypesDemo.java
java NestedTypesDemo
```

Stdout:

```text
Result[code=200, data=JAVA]
OK
```

These are **nested types**, though not all four kinds of **nested class** share the same instantiation approach. Enum constants and interfaces have their own rules.

## 42. Static Declarations Inside Inner/Local Classes in Java 17

Some older resources or interview questions state: **"An inner class cannot have static members except for constant variables."** This rule was **relaxed in newer Java versions**. In **Java 17**, inner classes are allowed to declare appropriate static members, including static methods/static nested types, under the current language rules.

That **does not** turn a non-static member inner class into a static nested class:
- An inner instance is still tied to an enclosing Outer instance.
- `Outer.this` is still valid in an inner instance context.
- A static method of an inner class still **has no `this`**.
- A static nested member class still does not require an Outer instance.

**Do not mechanically memorize rules from Java 8 documentation and apply them unchanged to Java 17.** When you need to conclude whether a construct compiles, verify it specifically with `--release 17`.

### Java 17 Example

Save as **`InnerStaticMemberDemo.java`**:

```java
public class InnerStaticMemberDemo {
    private final String name = "OUTER";

    class Inner {
        static String type() {
            return "INNER-TYPE";
        }

        String owner() {
            return InnerStaticMemberDemo.this.name;
        }
    }

    public static void main(String[] args) {
        InnerStaticMemberDemo outer =
                new InnerStaticMemberDemo();
        Inner inner = outer.new Inner();

        System.out.println(Inner.type());
        System.out.println(inner.owner());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InnerStaticMemberDemo.java
java InnerStaticMemberDemo
```

Stdout:

```text
INNER-TYPE
OUTER
```

The purpose of this example is to illustrate **the difference between "a class being inner" and "that class having a static member"** in Java 17, not to encourage nesting too many static members inside an inner class if it hurts readability.

## 43. Nested Classes and Generic Type Parameters

A member inner class inside a generic Outer can use the type parameter of the enclosing instance context:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    class Reader {
        T read() {
            return value;
        }
    }
}
```

A static nested class **cannot directly reference Outer's type parameter `T`** as an instance type parameter that it automatically inherits:

```java
class Box<T> {
    static class StaticReader {
        // T read() { ... } // Invalid: Outer's T is not in scope that way.
    }
}
```

It can declare its own type parameters:

```java
static class StaticReader<U> {
    U identity(U value) {
        return value;
    }
}
```

### Example of an Inner Class Type Name

With `Box<String> box = new Box<>("Java");`, the non-static member inner type can be referred to as `Box<String>.Reader`.

For a static nested class, the type is normally `Box.StaticReader<U>`, not `Box<String>.StaticReader<U>`, because a static member type is not tied to each parameterization of Outer in that syntax.

## 44. Runnable: Generics and Inner/Static Nested Classes

Save as **`GenericNestedDemo.java`**:

```java
public class GenericNestedDemo<T> {
    private final T value;

    GenericNestedDemo(T value) {
        this.value = value;
    }

    class Reader {
        T read() {
            return value;
        }
    }

    static class Holder<U> {
        private final U value;

        Holder(U value) {
            this.value = value;
        }

        U read() {
            return value;
        }
    }

    public static void main(String[] args) {
        GenericNestedDemo<String> box =
                new GenericNestedDemo<>("Java");

        GenericNestedDemo<String>.Reader reader =
                box.new Reader();

        GenericNestedDemo.Holder<Integer> holder =
                new GenericNestedDemo.Holder<>(17);

        System.out.println(reader.read());
        System.out.println(holder.read());
    }
}
```

```bash
javac -encoding UTF-8 GenericNestedDemo.java
java GenericNestedDemo
```

Stdout:

```text
Java
17
```

`Reader` is bound to a `GenericNestedDemo<String>` instance; static `Holder<U>` has its own generic parameter `U` and does not require an enclosing instance.

## 45. Shadowing: Same Variable Name Across Multiple Scopes

When a parameter, an inner field, and an outer field share the same name, Java uses scope/shadowing to resolve them:

~~~java
class Outer {
    int value = 1;
    class Inner {
        int value = 2;
        void show(int value) {
            System.out.println(value);            // 3
            System.out.println(this.value);       // 2
            System.out.println(Outer.this.value); // 1
        }
    }
}
~~~

Calling `show(3)` prints 3, 2, and 1 in order. Whether `private` access is permitted is a separate question from name resolution. The lesson **Name shadowing and qualification with Outer.this** analyzes in detail cases with multiple tiers, inherited members, method resolution, and lambdas/anonymous classes.

## 46. Runnable: Local, Inner, and Outer Sharing the Same Name

Save as **`NestedShadowingDemo.java`**:

```java
public class NestedShadowingDemo {
    private int value = 1;

    class Inner {
        private int value = 2;

        void show(int value) {
            System.out.println(value);
            System.out.println(this.value);
            System.out.println(NestedShadowingDemo.this.value);
        }
    }

    public static void main(String[] args) {
        NestedShadowingDemo outer =
                new NestedShadowingDemo();
        Inner inner = outer.new Inner();

        inner.show(3);
    }
}
```

```bash
javac -encoding UTF-8 NestedShadowingDemo.java
java NestedShadowingDemo
```

Stdout:

```text
3
2
1
```

The resolution does not rely on the runtime class name; it relies on lexical name resolution and explicit qualifiers.

## 47. Reflection: Determining Whether a Class Is Member, Local, or Anonymous

Java Reflection provides operations such as:
- `Class.isMemberClass()`;
- `Class.isLocalClass()`;
- `Class.isAnonymousClass()`;
- `Class.getDeclaringClass()`;
- `Class.getEnclosingClass()`;
- `Class.getSimpleName()`.

Both a static nested class and a non-static member inner class are **member classes** according to `isMemberClass()`. Distinguish static/non-static via modifiers, such as `Modifier.isStatic(clazz.getModifiers())` for a member class.

A local class returns `isLocalClass() == true`, and an anonymous class returns `isAnonymousClass() == true`. A named top-level class does not belong to any of those three groups.

### Do Not Rely on Compiler-Generated Binary Names as an API

You may see files/names such as:
- `Outer$Nested.class`;
- `Outer$Inner.class`;
- `Outer$1Local.class`;
- `Outer$1.class`.

These examples are only for **common recognition**, not a guaranteed list of names across every compiler/source/anonymous expression. The numbering order and details of generated names should not serve as a business contract.

## 48. Runnable: Reflection Classifying the Four Kinds

Save as **`NestedReflectionDemo.java`**:

```java
import java.lang.reflect.Modifier;

public class NestedReflectionDemo {
    static class Nested {
    }

    class Inner {
    }

    static void inspect() {
        class Local {
        }

        Object anonymous = new Object() {
        };

        print("static", Nested.class);
        print("inner", Inner.class);
        print("local", Local.class);
        print("anonymous", anonymous.getClass());
    }

    static void print(String label, Class<?> type) {
        System.out.println(label + ": "
                + type.isMemberClass() + ","
                + type.isLocalClass() + ","
                + type.isAnonymousClass() + ","
                + Modifier.isStatic(type.getModifiers()));
    }

    public static void main(String[] args) {
        inspect();
    }
}
```

```bash
javac -encoding UTF-8 NestedReflectionDemo.java
java NestedReflectionDemo
```

Stdout according to the reflection APIs on Java 17:

```text
static: true,false,false,true
inner: true,false,false,false
local: false,true,false,false
anonymous: false,false,true,false
```

`getName()` and `getSimpleName()` are not printed here to avoid depending on compiler-generated names of anonymous/local classes. The `Modifier.isStatic` output on the last line indicates that the anonymous class is not declared as a static member type; it is not a substitute answer for asking whether an enclosing instance exists.

## 49. Source File Organization and Bytecode

A source file can contain:
- One public top-level class matching the file name.
- Multiple nested member classes.
- Local classes declared inside methods.
- Anonymous class expressions.
- Other package-private top-level classes if needed.

For example, when compiling:

```bash
javac -encoding UTF-8 NestedKindsDemo.java
```

The compiler typically generates multiple `.class` files for the related runtime classes. This is normal: **being nested in source does not mean all bytecode resides in a single file**.

You can examine:

```bash
javap -p NestedKindsDemo
```

However, the detailed output depends on the compiler and class file structure; do not assume the file count or internal field names as an API contract.

## 50. Nesting and Encapsulation: The Benefit Is Not Hiding Everything

A nested class is useful when a type **is genuinely an implementation detail** of the enclosing type:

```java
public final class LinkedBag {
    private static final class Node {
        Object value;
        Node next;
    }
}
```

`Node` is a private static helper that does not need an outer `LinkedBag` instance.

However, if a nested class grows larger and is used by multiple modules/packages as an independent type, you can extract it into a top-level class with an appropriate package-private/public API.

### Design Questions

- Does the type make sense on its own?
- Does it need to access private members very frequently?
- Is it too tightly coupled to Outer?
- Is it merely an implementation helper?
- Does it need to be unit tested directly via a public contract?
- If the class is reused in many places, does the nested name make the code cumbersome?
- Does it need the owner object's lifetime to perform its behavior?

**Choose nesting for ownership/encapsulation**, not merely to reduce the number of source files.

## 51. Avoid Overly Long Anonymous Classes

An anonymous class hundreds of lines long is often difficult to:
- Read and debug when stack traces only show generated type names.
- Directly test the logic if it is deeply embedded inside a method.
- Reuse behavior across call sites.
- Give a meaningful name to the design abstraction.
- Review state/capture/enclosing-instance dependencies.

When an anonymous class starts having many fields, many helper methods, and branches, consider:
- A named local class if its scope is only within a single method.
- A private static nested class if it does not need enclosing state.
- A private member inner class if it truly needs enclosing state.
- A separate top-level class if the logic is a reusable domain service.
- A lambda if only a single short functional operation remains.

An anonymous class is not bad; **choosing the right size and contract** is what matters.

## 52. Anonymous Classes Have No Explicit Constructor of Their Own

You cannot define:

```java
new Runnable() {
    // Runnable() { }  // No separate constructor name for the anonymous type.
};
```

An anonymous class object can declare an **instance initializer block**:

```java
Runnable task = new Runnable() {
    private final int seed;

    {
        seed = 7;
    }

    @Override
    public void run() {
        System.out.println(seed);
    }
};
```

For a subclass of a named class, the `new Base(args) { ... }` part uses the matching superclass constructor invocation according to the rules.

### Be Careful with Initializers Calling Overridable Methods

Just like regular classes, the constructor/init sequence can create hazards when calling overridable methods before state is ready. Do not use anonymous initializers for complex side effects that callers cannot easily see.

## 53. Runnable: Initializer of an Anonymous Class

Save as **`AnonymousInitializerDemo.java`**:

```java
public class AnonymousInitializerDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private final int seed;

            {
                seed = 7;
            }

            @Override
            public void run() {
                System.out.println("seed = " + seed);
            }
        };

        task.run();
    }
}
```

```bash
javac -encoding UTF-8 AnonymousInitializerDemo.java
java AnonymousInitializerDemo
```

Stdout:

```text
seed = 7
```

In an anonymous class, the initializer block runs during instance creation. `seed` is a final instance field assigned inside the initializer block.

## 54. Why Should Static Nested Classes Be Used with Data Structures?

A node of a stack/list/tree typically does not need the state of the **container instance**. Therefore:

~~~java
final class IntStack {
    private Node head;
    private static final class Node {
        final int value;
        final Node next;
        Node(int value, Node next) {
            this.value = value;
            this.next = next;
        }
    }
}
~~~

`Node` is a private nested type for code organization; it has no mandatory enclosing `IntStack` instance and is not a singleton. If owner state is needed, supply a reference or choose an inner class matching the contract. The lesson **Choosing between a nested class and a top-level class** examines cohesion, access, testability, and memory footprint overall; the next section still keeps a runnable program using a static Node.

## 55. Runnable: Stack with a Private Static Node

Save as **`StaticNodeStackDemo.java`**:

```java
public final class StaticNodeStackDemo {
    private Node top;

    private static final class Node {
        final int value;
        final Node next;

        Node(int value, Node next) {
            this.value = value;
            this.next = next;
        }
    }

    public void push(int value) {
        top = new Node(value, top);
    }

    public int pop() {
        if (top == null) {
            throw new IllegalStateException("empty");
        }

        int value = top.value;
        top = top.next;
        return value;
    }

    public static void main(String[] args) {
        StaticNodeStackDemo stack =
                new StaticNodeStackDemo();

        stack.push(3);
        stack.push(5);

        System.out.println(stack.pop());
        System.out.println(stack.pop());
    }
}
```

```bash
javac -encoding UTF-8 StaticNodeStackDemo.java
java StaticNodeStackDemo
```

Stdout:

```text
5
3
```

`Node` is private in the source and static nested to avoid an unnecessary enclosing-instance dependency. This is a typical practical application rather than just syntax to memorize.

## 56. Inner Classes Are Appropriate When Behavior Is Always Bound to an Owner

An **inner member class** is suitable when the behavior genuinely belongs to a specific owner object, such as a cursor/iterator or a command that modifies the state of a document/counter instance:

~~~java
class Counter {
    private int value;
    class IncrementCommand {
        void execute() { value++; }
    }
}
~~~

Creating a command via `counter.new IncrementCommand()` links it to that exact Counter; two counters can have their own separate commands even though they share the same Inner type. However, a long-lived callback can keep the owner alive longer than intended, so you must define its lifecycle. Need a helper that uses only a data snapshot? Consider a static nested class with explicit dependencies. Detailed choice analysis belongs to the lesson **Choosing between a nested class and a top-level class**.

## 57. Runnable: Command Bound to an Owner Instance

Save as **`InnerCommandDemo.java`**:

```java
public class InnerCommandDemo {
    private final String name;
    private int count;

    InnerCommandDemo(String name) {
        this.name = name;
    }

    class IncrementCommand implements Runnable {
        @Override
        public void run() {
            count++;
        }
    }

    int count() {
        return count;
    }

    public static void main(String[] args) {
        InnerCommandDemo a = new InnerCommandDemo("A");
        InnerCommandDemo b = new InnerCommandDemo("B");

        Runnable commandA = a.new IncrementCommand();
        Runnable commandB = b.new IncrementCommand();

        commandA.run();
        commandA.run();
        commandB.run();

        System.out.println(a.name + ":" + a.count());
        System.out.println(b.name + ":" + b.count());
    }
}
```

```bash
javac -encoding UTF-8 InnerCommandDemo.java
java InnerCommandDemo
```

Stdout:

```text
A:2
B:1
```

The example runs sequentially; if commands are invoked concurrently on the same Counter, `count` must be protected with appropriate synchronization/atomic semantics.

## 58. The `static` Modifier and Anonymous Classes Are Not a Pair of Choices

You can write an anonymous class inside a **static method**:

```java
static Runnable make() {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println("task");
        }
    };
}
```

This is valid and does not turn the anonymous class into a **static member nested class**. It is still an anonymous class, simply declared/instantiated inside a static context without an enclosing `this` instance of Outer.

Therefore, two classification dimensions must be separated:
- **Declaration form**: named member, local, anonymous.
- **Instance/static context**: whether an appropriate enclosing instance exists.

An anonymous class in an instance method can access Outer state; an anonymous class in a static method does not automatically have Outer.this.

## 59. Defining Scope When an Anonymous/Local Class Resides Inside a Nested Static Helper

Suppose:

```java
class Outer {
    static class Nested {
        Runnable create() {
            int id = 7;

            return new Runnable() {
                @Override
                public void run() {
                    System.out.println(id);
                }
            };
        }
    }
}
```

The anonymous class captures `id` in `Nested.create`. It does not have an Outer instance merely because Nested is nested inside Outer. It can be bound to a `Nested` enclosing instance in an appropriate context.

If you want to access an Outer object, there must be an explicit reference to that object.

### Very Deep Nesting Levels

Multiple layers of local/anonymous/member types complicate determining the enclosing instance. If readers have to continually ask "What is `this` right now?", consider refactoring into named types with explicit dependencies.

## 60. Common Compiler Errors When Learning the Four Kinds of Nested Classes

| Code / Symptom | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| `new Outer.Inner()` in external code | A member inner class needs an enclosing Outer instance | `outer.new Inner()` |
| `new Outer.Nested()` when class Nested is private | Access is not permitted for external callers | A factory on Outer or adjust the API appropriately |
| Static nested class reads `Outer.this.x` | No implicit enclosing Outer instance | Pass an Outer reference or use an inner class |
| Instance field `x` is read directly in a static nested method | No Outer receiver instance | `owner.x` |
| `new Inner()` from a static method of Outer | No implicit Outer `this` | `outer.new Inner()` |
| Local class name used outside the method | Type name exists only in local scope | Return an interface/superclass or extract to a member class |
| Captured variable is reassigned | Not final/effectively final | Do not reassign the variable / change the design |
| Using `this` inside an anonymous class thinking it is Outer | `this` is the anonymous object | `Outer.this` if valid |
| Using `this` inside a lambda in a static method | A static context has no instance `this` | Pass a specific receiver |
| Anonymous class implements an interface without overriding an abstract method | Incomplete implementation | Override all required abstract methods |
| Anonymous class extends a final class | Final forbids subclassing | Choose a different strategy/interface |
| `Runnable r = new Runnable(){ void helper(){} }; r.helper();` | Static type Runnable does not have helper | Put the method in the interface or use a named type |
| Using `new Interface() { }` when Interface has an unimplemented abstract method | Incomplete concrete anonymous class | Implement the method or use a lambda if functional |
| Assuming a local class is a member `Outer.Local` | Local type is not a member | Use a member class if a public type is needed |
| Assuming a static nested class cannot access private Outer members | Nesting grants valid access | Pass an outer object to read instance state |
| Anonymous class/lambda holds unsynchronized mutable state | An effectively-final reference does not lock the referent | Synchronization/atomics per the contract |
| Inner listener keeps owner alive long | Enclosing-instance relation/lifecycle | Static helper, explicit capture, unregister |
| Assuming `Outer$1` is a fixed binary name | Compiler-generated detail | Do not put generated names into business logic |
| Applying the Java 8 rule "inner forbids static methods" to Java 17 | Rules change across versions | Verify with `--release 17` |
| Using too many anonymous blocks for large business logic | Logic is hard to name/test | Local/member/top-level named class |

## 61. Technique for Solving Output-Prediction Exercises with Nested Classes

When examining a code snippet, proceed in order:

1. **Identify the declaration location**: member, local block, or anonymous expression?
2. **If it is a member class**, does it have the `static` modifier?
3. **If it is a non-static member inner class**, where is the Outer instance specified at `new`?
4. **If it is local/anonymous**, is the code created in a static or instance context?
5. **Identify the receiver `this`** inside each body.
6. **If an Outer instance is needed**, is `Outer.this` valid at that point?
7. **Is the field name shadowed** by local/parameter/inner fields?
8. **Is the captured local variable** final/effectively final?
9. **Does the static type of the reference** have the method being called?
10. **Does the runtime implementation** override according to the superclass/interface?
11. **What is the order of object creation and field initialization**?
12. Is there a risk of retaining a reference to the outer/captured mutable object for too long?
13. When printing stdout, avoid predicting compiler-generated class names, identity hashes, or scheduling if not guaranteed.

### Quick Recognition Table

| Expression | Meaning |
| --- | --- |
| `new Outer.Nested()` | Creates a static nested member instance |
| `outer.new Inner()` | Creates a member inner instance bound to `outer` |
| `new Inner()` in an Outer instance method | Uses the implicit enclosing `this` |
| `new Local()` in a method | Creates a local named class instance in scope |
| `new Runnable() { ... }` | Creates an anonymous implementation |
| `new Base(args) { ... }` | Creates an anonymous subclass of Base |
| `Outer.this` | Enclosing instance of Outer when it validly exists |
| `this` in a member inner method | Inner instance |
| `this` in an anonymous method | Anonymous instance |
| `this` in a lambda in an instance context | Enclosing instance by lexical scope |

## 62. Exercise 1 — Does a Static Nested Class Need an Outer Object?

```java
class Outer {
    static class Nested {
        int value() {
            return 10;
        }
    }
}
```

**Question:** Does `new Outer.Nested().value()` require `new Outer()` beforehand?

**Answer:** No. A static nested member class does not need an implicit enclosing Outer instance. The result is `10`.

## 63. Exercise 2 — Instantiating an Inner Class

```java
class Outer {
    class Inner {
    }
}
```

**Question:** How do you create an Inner instance from outside Outer?

**Answer:**

```java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
```

`new Outer.Inner()` without a corresponding enclosing instance is invalid.

## 64. Exercise 3 — Two Different Owners

```java
class Counter {
    int count;

    class Reader {
        int get() {
            return count;
        }
    }
}
```

Two Counter objects `a` and `b` have different `count` values, and `a.new Reader()` and `b.new Reader()` are created. Do the two Readers read the same `count` variable?

**Answer:** No. Each Reader is bound to its own enclosing Counter instance, so although the field name is the same, the state belongs to two different objects.

## 65. Exercise 4 — `this` and `Outer.this`

```java
class Outer {
    int value = 1;

    class Inner {
        int value = 2;

        int sum() {
            return this.value + Outer.this.value;
        }
    }
}
```

**Answer:** `sum()` returns `3` because `this.value = 2` and `Outer.this.value = 1`.

## 66. Exercise 5 — Static Nested Class Reading a Private Outer Field

```java
class Outer {
    private int value = 7;

    static class Nested {
        int read(Outer owner) {
            return owner.value;
        }
    }
}
```

**Question:** Does this compile?

**Answer:** Yes. A static nested class can access a private instance field via an explicit `owner` reference thanks to nesting access. Without `owner`, it cannot read an instance field as if it were static.

## 67. Exercise 6 — Local Captured Variable

```java
void run() {
    int factor = 2;

    class Local {
        int calculate() {
            return factor * 5;
        }
    }

    System.out.println(new Local().calculate());
}
```

**Answer:** Prints `10`. `factor` is effectively final because it is not reassigned.

## 68. Exercise 7 — Modified Local Variable

```java
void run() {
    int factor = 2;

    class Local {
        int calculate() {
            return factor * 5;
        }
    }

    factor = 3;
}
```

**Answer:** Does not compile because factor is captured yet not effectively final. Fix by keeping the value constant, passing state into an object with an explicit contract, or redesigning the flow.

## 69. Exercise 8 — Capturing a Reference to an Array

```java
int[] number = {1};

Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(number[0]);
    }
};

number[0] = 9;
task.run();
```

**Answer:** Prints `9`. The reference `number` remains effectively final, while the contents of the array are mutable. This does not capture a deep snapshot.

## 70. Exercise 9 — Can a Local Class Be Used Outside the Method?

A method creates a local class `Helper` and returns the `Runnable` interface. Can the caller write `new Helper()` outside the method?

**Answer:** No. The name `Helper` exists only within the local scope. The runtime instance can live on through the `Runnable` interface reference.

## 71. Exercise 10 — Anonymous Subclass Calling a Superclass Method

```java
class Base {
    String text() {
        return "A";
    }
}

Base value = new Base() {
    @Override
    String text() {
        return super.text() + "B";
    }
};

System.out.println(value.text());
```

**Answer:** `AB`. The anonymous class overrides the method and uses `super.text()` to call the Base implementation.

## 72. Exercise 11 — Anonymous Class Implementing Multiple Abstract Methods?

```java
interface Actions {
    void open();
    void close();
}
```

**Question:** Can you create `new Actions() { ... }` overriding only `open()`?

**Answer:** No, if a valid implementation of `close()` is missing. The created anonymous class must be concrete and fulfill all abstract method requirements. A lambda cannot be used either because this interface is not a functional interface due to having two abstract methods.

## 73. Exercise 12 — `this` Inside an Anonymous Class

An anonymous `Runnable` inside an instance method of Outer compares `this == Outer.this`.

**Answer:** `false` because `this` inside an anonymous instance method is the anonymous object, whereas `Outer.this` is the enclosing Outer instance.

## 74. Exercise 13 — `this` Inside a Lambda

A `Runnable` lambda inside an instance method of Outer compares `this == Outer.this`.

**Answer:** `true` because a lambda uses the lexical `this` of the enclosing instance context.

## 75. Exercise 14 — Does an Anonymous Class Have Its Own Named Constructor?

**Answer:** You cannot declare an explicit constructor named after the anonymous class because it has no source name. You can pass arguments to a superclass constructor and include an instance initializer block.

## 76. Exercise 15 — Accessing a Helper Method Not Declared on the Interface

```java
Runnable r = new Runnable() {
    void helper() {
        System.out.println("help");
    }

    @Override
    public void run() {
        helper();
    }
};
```

**Question:** Can `r.helper()` be called from the outside?

**Answer:** No. The static type `Runnable` does not declare `helper`. Inside the anonymous class body, `run` can still call helper.

## 77. Exercise 16 — Static Nested Class or Inner Class for Node?

A `Tree` has thousands of nodes, each containing only `int value` and child references, and never needs the state of the Tree object.

**Answer:** Usually choose **private static nested Node**. It preserves namespace/encapsulation without attaching an unnecessary implicit enclosing Tree instance.

## 78. Exercise 17 — Inner Callback Retaining the Owner Object

A UI screen registers a member inner listener with a singleton event bus and forgets to unregister it. What is the risk?

**Answer:** The listener holds a relationship with the enclosing screen instance, and if retained long-term, can prevent the screen from being garbage-collected when expected. Mitigate this with lifecycle unregistration, minimal capture, or a static helper/explicit dependencies as appropriate.

## 79. Exercise 18 — Generic Outer and Static Nested Class

```java
class Box<T> {
    static class Helper {
        // T read() { ... }
    }
}
```

**Answer:** Static nested Helper cannot directly use Outer's type parameter `T` like an instance member inner class. Helper can declare its own type parameter, for example `Helper<U>`, or accept a parameterized `Box<T>` in an appropriately declared context.

## 80. Exercise 19 — Reflection Distinguishing Local/Anonymous

**Question:** Which two reflection methods are commonly used to check whether a `Class<?>` is local or anonymous?

**Answer:** `clazz.isLocalClass()` and `clazz.isAnonymousClass()`. For a member nested class, use `isMemberClass()`; to check the static modifier of a member class, inspect `Modifier.isStatic(clazz.getModifiers())`.

## 81. Exercise 20 — The Old Java 8 Rule

An old resource claims that no inner class may declare a static method. Does that apply unchanged to `javac --release 17`?

**Answer:** No. Java 17 allows static declarations inside inner classes under current rules. You must still distinguish a class having a static member from a class declared as a static nested member; those are two different properties.

## 82. Exercise 21 — Local Class Inside a Static Method

```java
class Outer {
    int count;

    static void work() {
        class Local {
            int read() {
                // return count;
                return 0;
            }
        }
    }
}
```

**Answer:** You cannot read `count` unqualified as an enclosing Outer field because a local class declared inside a static method has no implicit Outer instance. Pass an explicit Outer reference into Local or move the context to an instance method.

## 83. Exercise 22 — Should an Anonymous Class Be Used for a Long Business Rule?

An anonymous `PaymentStrategy` has 200 lines, many instance fields, several helper methods, and needs to be used in three places.

**Answer:** It should usually be extracted into a named class, a static nested helper, or a top-level implementation depending on ownership and testability/reusability. An anonymous class is only concise when the scope and behavior are sufficiently small.

## 84. Exercise 23 — Can a Class Be Placed Inside an Anonymous Class?

**Answer:** Java permits appropriate declarations/nesting inside an anonymous class body according to language rules. However, nesting too many layers can complicate name scope/receivers; an anonymous class should not be viewed as mandatorily "having exactly one method".

## 85. Exercise 24 — Type Visibility and Runtime Object Lifetime

A local class `LocalTask` resides inside a method that returns `Runnable`. After the method returns, does the returned object die along with the stack frame?

**Answer:** No. The object can remain alive if reachable via the `Runnable` reference. The class name is scope-restricted, which does not restrict instance lifetime in that way.

## 86. Exercise 25 — Choosing a Solution

Scenarios:
1. A `Builder` creating an immutable `Request`.
2. A `Cursor` reading/modifying the specific `Document` enclosing instance.
3. A named validator used only within one method.
4. A short, one-off `Runnable`.

**Suggestions:**
1. `static nested Builder`.
2. `inner Cursor` if coupling to the owner instance is intentional; or static with an explicit owner for a clear lifecycle.
3. `local class`.
4. `anonymous class`, or a lambda if only functional behavior is needed and anonymous class semantics are not.

## 87. Nested Class Selection Checklist

1. Is the type **member**, **local**, or **anonymous**?
2. Does it need **an enclosing instance**?
3. Does it need to read/modify Outer instance fields without receiving a parameter?
4. If an outer instance is not needed, have you considered **static nested**?
5. Does the class need a name to be reused/tested directly?
6. If the logic is only within one block yet fairly long, is a local named class reasonable?
7. If an implementation is small and used only once, is an anonymous class clear enough?
8. If the interface is functional, would a lambda be simpler?
9. Do you need to override multiple methods or subclass a concrete class, making a lambda unsuitable?
10. Which object does `this` point to in each nested scope?
11. Is `Outer.this` or an explicit owner field needed?
12. Is there field/parameter shadowing that could easily cause confusion?
13. Are captured local variables **final/effectively final**?
14. Do captured references point to mutable objects?
15. If the callback runs across multiple threads, is the captured state thread-safe?
16. Does it risk retaining the outer instance/resources longer than the intended lifecycle?
17. Is `public/private/protected` visibility appropriate for the API?
18. Is a private nested type being exposed through a public signature?
19. Is instantiation using `new Outer.Nested()` or `outer.new Inner()` done correctly?
20. Are **Java 17 rules** being applied instead of following Java 8 restrictions?
21. Is any anonymous class getting too long and hard to test?
22. Does any code depend on compiler-generated `$1` class names?
23. With a generic Outer, is a type parameter being misused inside a static nested class?
24. Is any nested interface/record/enum implicitly static rather than inner?
25. Does a domain need make a top-level type clearer than nesting?
26. Do build examples use the right public class/file name and language level?
27. Does the output avoid identity hashes, generated class names, and unguaranteed thread scheduling?

## Key Takeaways

- A **static nested member class** has a name, resides inside the enclosing type, yet **does not require an enclosing instance**; use `new Outer.Nested()`.
- A **non-static member inner class** has a name and is bound to **an Outer instance** when created; from the outside, use `outer.new Inner()`.
- A **local class** has a name within a **local block/scope**, can capture final/effectively final variables, and can have objects that outlive the method.
- An **anonymous class** has no declared name in source; use a `new Interface() { ... }` or `new Base(args) { ... }` expression to create an implementation/subclass in place.
- `this` inside a member inner/anonymous class is **that class's instance**, while `Outer.this` is the corresponding enclosing instance; `this` inside a lambda carries the **lexical enclosing context**.
- **A static nested class cannot automatically read Outer instance fields**, yet it can still access private Outer state through an **explicitly supplied reference**.
- **Local/anonymous capture** does not turn mutable objects into immutable ones. Final/effectively final restricts **reassigning the local variable**, not mutating the referent.
- **A lambda is not an anonymous class** and cannot replace every anonymous implementation, especially when needing to subclass a concrete class or use class-scoped state/`super`.
- In Java 17, the rules for static members of inner classes differ from older Java guides; always check against the exact release.
- Choose the kind of nested class based on **enclosing instance requirement, name scope, API visibility, reusability, and lifecycle**, not merely syntactic brevity.

When reading a nested class, the fastest way to understand it is to determine **where the class is declared**, **which instances are bound/captured**, and **which names/members are visible at compile time**. Those three questions explain most of the differences among static nested, member inner, local, and anonymous classes.
