# Choosing Between Nested and Top-Level Classes in Java

When designing a Java application, whether a class is placed **inside another class** or as a **top-level class** determines more than just the number of `.java` files. This choice reflects **conceptual independence**, **scope of use**, **encapsulation**, **access rights**, **the relationship with an enclosing object**, **reusability**, **testability**, and **object lifecycle**.

Suppose you are writing `Order` and have the following types:

- `OrderLine`: represents a line item of the order.
- `Node`: an internal linked node to store a data structure of Order.
- `Builder`: assists in creating an Order.
- `TaxPolicy`: tax rules used across multiple modules.
- `Cursor`: operates on exactly one Order instance.

Should all of them be written as nested classes of `Order`? Not necessarily. Each type has a different **ownership scope and reusability**.

A pragmatic principle:

> **If a class is an implementation detail of exactly one enclosing class, consider a nested class. If the class is an independent concept, used by multiple parts of the system, and has its own lifecycle/API, consider a top-level class.**

Once you have chosen nested, the next question is:

> **Does that class actually need an enclosing instance? If not, generally choose a static nested member class instead of a non-static member inner class.**

This lesson is presented on **Java 17+**, covering top-level versus nested, private/package-private/public API, static nested and member inner, local and anonymous classes, choices for builders/value objects/callbacks, refactoring changes, bytecode/JVM, module boundaries, testability, memory retention, design smells, and many examples that can be saved to files and run with `javac`/`java`.

## 1. Two Ways to Declare a Class and Their Initial Meaning

A **top-level class** is declared directly within a compilation unit, not inside the body of another class:

```java
class Product {
    private final String sku;

    Product(String sku) {
        this.sku = sku;
    }
}
```

A **nested member class** resides inside an enclosing type:

```java
class Order {
    private static class Node {
        String sku;
        Node next;
    }
}
```

Here, `Node` primarily serves as an **implementation detail of Order**. External users do not need to see the name `Order.Node` when merely creating or working with an Order via the public API.

However, placing a class inside another class **does not automatically guarantee good design**. If `Node` gradually becomes a domain type needed by multiple parts of the system, forcing it into Order can make the API awkward to use.

### Two Dimensions to Consider Separately

1. **Conceptual role:** is this an independent domain concept or a helper that only makes sense alongside its owner?
2. **Instance relationship:** when the class is instantiated, does it need an implicit reference to a specific enclosing object?

A helper that belongs only to Order but **does not need an Order instance** → typically `private static class Helper`.

An object that needs to maintain a relationship with **exactly one Order instance** → can be `class InnerHelper`.

A `Money` domain type used across Order, Invoice, Refund, and Accounting → usually deserves to be a **top-level value type**, even if it was initially created only from Order.

## 2. Classification Diagram

```text
Java type declaration
│
├── Top-level class
│   └── public or package-private
│
└── Nested class
    │
    ├── Member class in enclosing type body
    │   ├── static nested member
    │   └── non-static member inner
    │
    ├── Local class (named within block scope)
    │
    └── Anonymous class (no source name)
```

The main design choices are distinguished by **declaration site**, **accessibility**, and **enclosing instance requirement**.

In Java semantics, the term **inner class** has a broader technical scope than non-static member inner: applicable local and anonymous classes are also inner classes. However, when contrasted with “static nested”, practical documentation commonly uses “member inner” to refer to a **non-static member class**.

**A lambda is not an anonymous class declaration.** A lambda provides behavior for a functional interface with its own semantics regarding `this`, capture, and implementation.

## 3. Quick Comparison Table

| Criterion | Top-level | Static member nested | Non-static member inner | Local | Anonymous |
| --- | --- | --- | --- | --- | --- |
| Independent source name? | Yes | `Outer.Nested` name | `Outer.Inner` name | Name only within block | No source class name |
| Where declared? | At compilation unit level | Enclosing type body | Enclosing class body | Inside a block/context | Directly at the instance creation expression |
| Needs enclosing instance? | No | No | Yes in normal object creation | Depends on enclosing context | Depends on enclosing context |
| Can be a private member type? | No | Yes | Yes | Not the same kind of access modifiers | Not the same kind of access modifiers |
| Widely reusable? | Easiest | Yes, if accessible; subject to a qualified name | Yes, but depends on owner instance | Limited by name scope | Usually in one place |
| Ideal for | Independent domain/service/value type | Helper, Node, Builder, subordinate API type | Owner-bound view/cursor/command | Helper used only within one method | Short inline implementation |
| Risk of owner coupling? | None inherently | By name/access, no implicit instance | Has enclosing instance relation | Depends on context/capture | Depends on context/capture |

You should not reduce every choice to a single score. **Reusability** is not always more important than **encapsulation**; **fewer files** is not always more important than **domain independence**.

## 4. Top-Level Class: When Is It Appropriate?

A top-level class is usually appropriate if a type:

- Has **independent domain meaning**: `Money`, `Address`, `CustomerId`.
- May be used by multiple classes or multiple packages.
- Has its own public contract/versioning.
- Has multiple behaviors that need to be tested separately.
- Has a lifecycle independent of an owner object.
- Needs to be easily referenced by name by a DI framework, serialization library, or API consumer.
- Has the potential to become an extension point for other development teams.
- Is not genuinely an implementation detail of an enclosing class.

Design example:

```text
com.example.billing
├── Money.java
├── Invoice.java
├── TaxPolicy.java
└── InvoiceService.java
```

`Money` and `TaxPolicy` can be used in both `Invoice` and `Refund`. Forcing `Money` to become `Invoice.Money` would create misleading naming if Money does not belong exclusively to Invoice.

### Top-Level Does Not Have to Be Public

A top-level class can be **package-private** (without declaring `public`):

```java
package demo;

final class LocalRateTable {
    // Only code with appropriate package access can use it directly.
}
```

Therefore, it is incorrect to say “to hide a type, it must be nested”. Package-private top-level classes are also a valid form of encapsulation, except their scope is the **package**, rather than **just a single enclosing class**.

## 5. Access Modifier Rules for Top-Level and Member Classes

A top-level ordinary class in Java source typically has:
- `public`;
- Or no access modifier (package-private).

**You cannot declare a top-level class with `private`, `protected`, or `static`** as a standalone class at the compilation unit level.

Invalid examples:

```java
// private class Secret { }   // Invalid at top-level.
// protected class Helper { } // Invalid at top-level.
// static class Utility { }   // Invalid at top-level.
```

Conversely, a member nested class can be exposed or hidden according to member rules:

```java
public class Container {
    public static class PublicResult {
    }

    protected static class ProtectedHelper {
    }

    private static class InternalNode {
    }
}
```

`private static class InternalNode` is intended only for the implementation accessible to the enclosing class/nest, not a type for external system clients to use arbitrarily.

### How Many Public Top-Level Classes Can a Compilation Unit Have?

According to the standard rule when compiling source from files with `javac`, each Java file exposes one **public top-level class/interface** matching the file name. For example, public `Invoice` in `Invoice.java`.

You can declare additional **package-private top-level classes** in the same compilation unit, but when they start growing large and taking on their own responsibilities, splitting them into separate files is usually easier to read/search.

You should not use “cramming multiple package-private classes into the same file” to avoid designing type boundaries.

## 6. Runnable: Package-Private Top-Level Helper

Save the file **`TopLevelChoiceDemo.java`**:

```java
final class PriceFormatter {
    String format(int cents) {
        int units = cents / 100;
        int fractional = cents % 100;

        return units + "." + (fractional < 10 ? "0" : "")
                + fractional;
    }
}

public class TopLevelChoiceDemo {
    public static void main(String[] args) {
        PriceFormatter formatter = new PriceFormatter();

        System.out.println(formatter.format(1250));
        System.out.println(formatter.format(205));
    }
}
```

```bash
javac -encoding UTF-8 TopLevelChoiceDemo.java
java TopLevelChoiceDemo
```

Stdout:

```text
12.50
2.05
```

`PriceFormatter` is a **top-level package-private class**, with no enclosing instance relationship with `TopLevelChoiceDemo`.

This formatter example only illustrates type organization; real monetary applications need to handle negative signs, overflow, currency/scale, and domain-specific rounding, rather than using this simple logic as a financial library.

## 7. Static Nested Class: When Is It the Best Choice?

Choose a **static nested member class** if:

1. The type is essentially an **implementation detail or companion type** of an enclosing class.
2. It does not need access to an implicit `Outer.this`.
3. You want to name it and restrict its visibility according to the owner.
4. It may need to read private members via an explicitly passed reference, without needing to be permanently bound to an owner instance.
5. It does not warrant being an independent public top-level concept.

Example:

```java
public final class IntStack {
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
```

`Node` is a separate type at the JVM level, but in the source API, it is a **detail of IntStack**. There is no mandatory `IntStack` reference stored inside every Node simply because Node is declared nested.

### Do Not Confuse a “Static Nested Class” with a Static Singleton

`static` on a member class **does not** create a singleton or limit it to a single instance. Each statement:

```java
new IntStack.Node(...);
```

if written from a place with valid access and arguments, can still create another Node instance.

Here Node is private, so the example illustrates that instantiation rights remain within the scope of IntStack rather than external clients.

## 8. Runnable: Private Static Node for a Stack

Save **`NestedNodeStackDemo.java`**:

```java
public final class NestedNodeStackDemo {
    private Node top;

    private static final class Node {
        private final int value;
        private final Node next;

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

        int result = top.value;
        top = top.next;
        return result;
    }

    public static void main(String[] args) {
        NestedNodeStackDemo stack = new NestedNodeStackDemo();

        stack.push(4);
        stack.push(9);

        System.out.println(stack.pop());
        System.out.println(stack.pop());
    }
}
```

```bash
javac -encoding UTF-8 NestedNodeStackDemo.java
java NestedNodeStackDemo
```

Stdout:

```text
9
4
```

If you turn Node into a public top-level class without an independent need, you can bloat the public API and force clients to understand a type unrelated to using the stack.

## 9. A Static Nested Class Still Accesses Private Members of the Enclosing Class

A static nested class can access private static members directly, and private instance members **through an instance reference**.

```java
class Outer {
    private int value = 7;

    private static class Reader {
        int read(Outer owner) {
            return owner.value;
        }
    }
}
```

This is valid because **nesting permits appropriate private access**. However, the static nested Reader **has no `Outer.this`**.

Invalid examples inside Reader:

```java
// return value; // Invalid without an Outer instance.
// return Outer.this.value; // No implicit enclosing Outer.
```

Therefore, choosing static nested **does not forbid using Outer's state**, but rather forces the dependency on **a specific object** to be explicit.

### Why Does Explicit Dependency Matter?

When reading the method `read(Outer owner)`, callers and reviewers see that:
- It reads state from a passed-in reference.
- A single Reader can be used to read multiple Outer instances.
- There is no default lifetime coupling to a specific Outer instance.

A member inner class expresses a different relationship: it is bound to an enclosing Outer instance from creation.

## 10. Runnable: Static Helper with an Owner Parameter

Save **`StaticHelperAccessDemo.java`**:

```java
public final class StaticHelperAccessDemo {
    private final String code;

    StaticHelperAccessDemo(String code) {
        this.code = code;
    }

    private static final class Inspector {
        String inspect(StaticHelperAccessDemo target) {
            return "[" + target.code + "]";
        }
    }

    public static void main(String[] args) {
        StaticHelperAccessDemo a =
                new StaticHelperAccessDemo("A");
        StaticHelperAccessDemo b =
                new StaticHelperAccessDemo("B");

        Inspector inspector = new Inspector();

        System.out.println(inspector.inspect(a));
        System.out.println(inspector.inspect(b));
    }
}
```

```bash
javac -encoding UTF-8 StaticHelperAccessDemo.java
java StaticHelperAccessDemo
```

Stdout:

```text
[A]
[B]
```

`Inspector` can use the private `code` without needing an implicit enclosing instance. The state-reading relationship **is indicated by the method parameter**.

## 11. Non-Static Member Inner Class: When Should You Choose It?

A **non-static member inner class** usually makes sense if its instance **makes sense when bound to exactly one enclosing object**:

- A Cursor bound to a Document.
- A Command operating on an Editor instance.
- A View tied to the state of a Session instance.
- A handler that is part of an owner with a managed lifecycle.

Example:

```java
class Counter {
    private int count;

    class Increment {
        void apply() {
            count++;
        }
    }
}
```

`Increment` is bound to the `Counter` instance used to create it.

Creating from outside:

```java
Counter counter = new Counter();
Counter.Increment command = counter.new Increment();
```

`Counter.Increment` does not automatically extend Counter. The enclosing relation **differs from** inheritance.

### Do Not Use an Inner Class Just Because It Is “Written Inside a Class”

If a helper does not need Outer's state, using an inner class typically makes the relationship between objects stronger than necessary. Choosing `static nested` expresses the intent more clearly.

## 12. Runnable: Owner-Bound Member Inner Command

Save **`OwnerBoundCommandDemo.java`**:

```java
public final class OwnerBoundCommandDemo {
    private final String name;
    private int count;

    OwnerBoundCommandDemo(String name) {
        this.name = name;
    }

    public final class Increment implements Runnable {
        @Override
        public void run() {
            count++;
        }
    }

    public static void main(String[] args) {
        OwnerBoundCommandDemo first =
                new OwnerBoundCommandDemo("first");
        OwnerBoundCommandDemo second =
                new OwnerBoundCommandDemo("second");

        Runnable firstCommand = first.new Increment();
        Runnable secondCommand = second.new Increment();

        firstCommand.run();
        firstCommand.run();
        secondCommand.run();

        System.out.println(first.name + "=" + first.count);
        System.out.println(second.name + "=" + second.count);
    }
}
```

```bash
javac -encoding UTF-8 OwnerBoundCommandDemo.java
java OwnerBoundCommandDemo
```

Stdout:

```text
first=2
second=1
```

Both commands share the same declared implementation type, yet **are bound to two different enclosing instances**. Because the behavior needs to update the specific owner, an inner class expresses this coupling directly.

**Do not infer thread-safety:** if multiple commands on the same owner are invoked from multiple threads, the `count++` operation requires appropriate synchronization.

## 13. Member Inner Classes Have Coupling and Lifecycle Costs

A member inner object is tied to its enclosing instance. If it is stored somewhere that outlives the owner, the owner may remain unintentionally reachable.

Example scenario:

```text
Long-lived event bus
  └── registered listener
        └── enclosing Screen object
              └── large UI model
```

If the listener is a member inner class of `Screen`, this instance relationship can cause **memory retention**. Not every inner class always causes a memory leak; leaks/retention occur when reference lifetimes are not properly managed.

Solutions:
- Use a **static nested listener** when no Outer instance is needed.
- Pass minimal state/dependencies if needed, instead of capturing the entire owner.
- Unregister the listener according to the lifecycle (`unregister`/`close`).
- Do not store an inner object in a global registry if the owner is supposed to be short-lived without cleanup.
- Re-examine ownership: if the listener is genuinely a component whose lifetime matches the owner, holding the reference may be appropriate.

### Do Not Use Inner Classes to Avoid Constructor Parameters

“Not having to pass the object” is not necessarily better. Hidden dependencies can:
- Make isolated testing harder.
- Make GC/lifecycle harder to reason about.
- Cause code to access private mutable state too broadly.
- Increase coupling between the helper and the enclosing class.

If a helper needs a few immutable scalar values, a static nested class with a constructor accepting those values can be clearer.

## 14. Runnable: Inner vs. Static Nested Regarding Dependencies

Save **`DependencyChoiceDemo.java`**:

```java
public final class DependencyChoiceDemo {
    private final String prefix;

    DependencyChoiceDemo(String prefix) {
        this.prefix = prefix;
    }

    final class InnerFormatter {
        String format(String message) {
            return prefix + ":" + message;
        }
    }

    static final class StaticFormatter {
        private final String prefix;

        StaticFormatter(String prefix) {
            this.prefix = prefix;
        }

        String format(String message) {
            return prefix + ":" + message;
        }
    }

    public static void main(String[] args) {
        DependencyChoiceDemo owner =
                new DependencyChoiceDemo("app");

        InnerFormatter inner = owner.new InnerFormatter();

        StaticFormatter helper =
                new StaticFormatter("app");

        System.out.println(inner.format("ready"));
        System.out.println(helper.format("ready"));
    }
}
```

```bash
javac -encoding UTF-8 DependencyChoiceDemo.java
java DependencyChoiceDemo
```

Stdout:

```text
app:ready
app:ready
```

Both implementations produce the same result, but their **relationship** differs:
- `InnerFormatter` carries an enclosing owner relationship.
- `StaticFormatter` holds exactly the `String prefix` it needs.

If the formatter actually depends only on the prefix, a static nested class is usually easier to reuse/test.

## 15. Public Static Nested Type: Sometimes a Good API

Not every nested class should be private. A **public static nested class** can describe a type that **conceptually depends** on an API owner:

- `Map.Entry<K,V>` is a familiar example of a **nested interface** in the Java API.
- `Outer.Builder` for a fluent builder of Outer.
- `Response.Status` if Status has no independent meaning outside Response in the domain.
- `Parser.Token` if Token is part of the public parser API.

Example:

```java
public final class HttpRequest {
    public static final class Builder {
        // ...
    }
}
```

Clients see `HttpRequest.Builder` and understand its role as the builder accompanying HttpRequest.

### However, Public Nested Types Also Create Coupling

If a public nested type begins to be used by multiple modules **without needing the enclosing API**, the long qualified name `Outer.Nested` can misrepresent the ownership relationship.

A public `Invoice.Money` only makes sense if “Money is a type that has meaning solely within Invoice”. If Money is shared across refund/pricing, a top-level `Money` is usually clearer.

**Rule:** public nested is appropriate when the **qualified name adds useful information**, not merely to reduce the number of source files.

## 16. Runnable: Public Static Nested Builder

Save **`RequestBuilderChoiceDemo.java`**:

```java
public final class RequestBuilderChoiceDemo {
    private final String path;
    private final int retries;

    private RequestBuilderChoiceDemo(Builder builder) {
        path = builder.path;
        retries = builder.retries;
    }

    @Override
    public String toString() {
        return "Request[path=" + path
                + ", retries=" + retries + "]";
    }

    public static final class Builder {
        private String path = "/";
        private int retries = 0;

        public Builder path(String value) {
            path = value;
            return this;
        }

        public Builder retries(int value) {
            retries = value;
            return this;
        }

        public RequestBuilderChoiceDemo build() {
            return new RequestBuilderChoiceDemo(this);
        }
    }

    public static void main(String[] args) {
        RequestBuilderChoiceDemo request =
                new RequestBuilderChoiceDemo.Builder()
                        .path("/health")
                        .retries(3)
                        .build();

        System.out.println(request);
    }
}
```

```bash
javac -encoding UTF-8 RequestBuilderChoiceDemo.java
java RequestBuilderChoiceDemo
```

Stdout:

```text
Request[path=/health, retries=3]
```

A Builder exists **before the Request is created**, so making it a non-static member inner class of Request would create a very strange reverse dependency: needing a Request instance to build a new Request.

## 17. Local Class: Used Only Within One Block, Yet Named

A **local class** is suitable when the logic:
- Is used only within a single method/block.
- Is large enough to warrant a type name, instance fields, or multiple methods.
- Needs to capture a few `final`/`effectively final` local variables.
- Does not warrant becoming a member nested or top-level type.

Example:

```java
void execute() {
    int limit = 3;

    class LocalChecker {
        boolean valid(int value) {
            return value < limit;
        }
    }

    LocalChecker checker = new LocalChecker();
}
```

This is only a snippet illustrating a method body. The name `LocalChecker` is not visible to code outside the method.

### Do Not Confuse Name Scope with Object Lifetime

A local class instance can be returned via an interface and outlive the method that created it. It is still an ordinary Java object; only the **class name in source** has limited scope.

If a local class gradually comes to be used in two or three different methods, it should usually be promoted to a member nested class or a top-level class.

## 18. Runnable: Local Class as a Temporary Strategy

Save **`LocalStrategyChoiceDemo.java`**:

```java
public class LocalStrategyChoiceDemo {
    interface Labeler {
        String label(int value);
    }

    static Labeler makeLabeler(String prefix) {
        int factor = 2;

        class LocalLabeler implements Labeler {
            @Override
            public String label(int value) {
                return prefix + "-" + (value * factor);
            }
        }

        return new LocalLabeler();
    }

    public static void main(String[] args) {
        Labeler first = makeLabeler("A");
        Labeler second = makeLabeler("B");

        System.out.println(first.label(3));
        System.out.println(second.label(5));
    }
}
```

```bash
javac -encoding UTF-8 LocalStrategyChoiceDemo.java
java LocalStrategyChoiceDemo
```

Stdout:

```text
A-6
B-10
```

- `LocalLabeler` has a name, but is visible only inside `makeLabeler`.
- `prefix` and `factor` are captured under the effectively final requirement.
- The caller only needs the `Labeler` API and does not need to know the local implementation type.

If the behavior is just a single expression and the interface has a single abstract method, a lambda can also be a more concise choice.

## 19. Anonymous Class: Where Is an Inline Implementation Needed?

An **anonymous class** is written directly inside an object creation expression:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("hello");
    }
};
```

Usually suitable when:
- The implementation is very short.
- It is used in only one place.
- No source type name is needed.
- You want to override a superclass method or implement an interface inline.
- No dedicated constructor with an anonymous class name is needed.

If an anonymous block grows to 100 lines with multiple fields and branches, consider a named class.

**Note:** if the target is just a functional interface, a lambda is usually easier to read than an anonymous class. However, lambdas and anonymous classes do not share the same semantics regarding `this`, scope, and construction; do not replace one with the other mechanically when behavior depends on those details.

## 20. Runnable: Anonymous Class for a One-Off Callback

Save **`AnonymousChoiceDemo.java`**:

```java
public class AnonymousChoiceDemo {
    interface Formatter {
        String format(int value);
    }

    public static void main(String[] args) {
        Formatter formatter = new Formatter() {
            @Override
            public String format(int value) {
                return "[" + value + "]";
            }
        };

        System.out.println(formatter.format(7));
    }
}
```

```bash
javac -encoding UTF-8 AnonymousChoiceDemo.java
java AnonymousChoiceDemo
```

Stdout:

```text
[7]
```

In this particular example, `Formatter formatter = value -> "[" + value + "]";` is also a good way to write it because Formatter is a functional interface. Anonymous classes remain useful when instance state, multiple methods, or subclass semantics are needed.

## 21. Anonymous Classes and Lambdas Are Not Interchangeable in All Cases

Some differences:

| Aspect | Anonymous class | Lambda |
| --- | --- | --- |
| Has an anonymous class declaration? | Yes | No |
| Allowed target is | An applicable interface or a superclass not prohibited from being subclassed | A functional interface |
| `this` inside an instance body | The anonymous object itself | `this` from the enclosing lexical context |
| Can declare instance fields | Yes | Does not declare separate class body fields like an anonymous class |
| Can override multiple methods | Yes, if needed | Only provides the functional method implementation |
| Can call `super` of an anonymous subclass | Yes, when valid | Has no such anonymous subclass super |
| Accesses local variables | Final/effectively final | Final/effectively final |
| Suitable for | Subclass/callback with state/class semantics | Short functional interface behavior |

### Be Careful When Converting an Anonymous Class to a Lambda

An anonymous class inside an instance method has `this` referring to the anonymous object. A lambda inside the same method has `this` referring to the enclosing instance. If the body calls `this.someMethod()`, refactoring may change the target method or even fail to compile.

Therefore, “just wanting fewer lines” is not sufficient reason to refactor: check `this`, overload resolution, shadowing, and captured state.

## 22. Top-Level Package-Private or Private Static Nested?

This is an important design question.

Suppose `Order` uses `OrderValidator` internally.

**Option A — package-private top-level:**

```java
final class OrderValidator {
    boolean valid(int quantity) {
        return quantity > 0;
    }
}
```

Other classes in the **same package** can reference this name according to access rules.

**Option B — private static nested:**

```java
final class Order {
    private static final class Validator {
        boolean valid(int quantity) {
            return quantity > 0;
        }
    }
}
```

`Validator` is tightly hidden behind the enclosing/nest access boundary. Naming it `Order.Validator` expresses that it is a detail belonging to Order.

### How to Decide?

- A helper serving **multiple classes in the same package**, without wanting it to be public → top-level package-private.
- A helper serving **only one class** with no independent meaning → private static nested.
- A helper with public meaning across multiple packages → top-level public, or public nested if it conceptually belongs to an owner.
- A helper needing an owner instance for each operation → member inner or static helper taking the owner, depending on lifecycle/coupling.

**Do not overuse private nested classes** to mix multiple responsibilities into the same class. The enclosing class should still have a clear purpose.

## 23. Runnable: Private Static Nested Helper for a Validator

Save **`ScopedValidatorDemo.java`**:

```java
public final class ScopedValidatorDemo {
    private final int quantity;

    ScopedValidatorDemo(int quantity) {
        if (!Validator.isValid(quantity)) {
            throw new IllegalArgumentException("quantity");
        }
        this.quantity = quantity;
    }

    private static final class Validator {
        static boolean isValid(int quantity) {
            return quantity > 0;
        }
    }

    public static void main(String[] args) {
        ScopedValidatorDemo valid =
                new ScopedValidatorDemo(3);

        System.out.println(valid.quantity);

        try {
            new ScopedValidatorDemo(0);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 ScopedValidatorDemo.java
java ScopedValidatorDemo
```

Stdout:

```text
3
quantity
```

`Validator` is a detail of `ScopedValidatorDemo`, requiring no owner instance. If the validation rules are later used across multiple domain types, they can be extracted into a top-level package-private/public type with a clear contract.

## 24. Design Criteria to Prioritize in Order

A simple process:

**Question 1 — Does the type have its own meaning?** If yes, top-level is usually a strong candidate.

**Question 2 — Does the type serve a single owner?** If yes, nested can provide good encapsulation.

**Question 3 — Is an enclosing instance truly needed?** If not, prefer a static nested member.

**Question 4 — Is it used only within one method?** If yes and the logic needs a name, a local class may suffice.

**Question 5 — Is there only a small implementation at one call site?** If yes, use an anonymous class or a lambda when appropriate.

**Question 6 — If public, does the qualified name clarify the API or introduce coupling?** Check this before publishing the type.

**Question 7 — How long will the class exist?** Check reference retention, callback lifecycle, shared state, and memory boundaries.

**Question 8 — When the design changes, how many callers must be modified?** Moving a public nested type to top-level is an API change that can ripple widely.

Do not start with “wanting the fewest Java files”; start with **the responsibility of the type**.

## 25. Decision Tree for Practical Selection

```text
Does the new type have an independent role, reused in multiple places?
  ├── Yes → consider top-level class/record/interface
  └── No
       │
       ├── Is it only a helper of an enclosing type?
       │     ├── Yes → needs a specific enclosing object?
       │     │          ├── Yes → member inner or static + explicit owner
       │     │          └── No → private/public static nested per API
       │     └── No → consider package-private top-level
       │
       └── Appears only inside a single block/call site?
             ├── Needs a name/relatively long type state → local class
             └── Short implementation → appropriate anonymous/lambda
```

The diagram is a **decision guide**, not a grammar with a single right answer. A helper appearing in only one place may still be worth extracting to top-level if it has complex behavior, needs independent testing, or is likely to evolve into its own concept.

## 26. Cohesion: The Closer the Responsibilities, the More Sense Nesting Makes

**Cohesion** refers to the degree to which components within a module/type serve the same responsibility.

A `LinkedList` having a private `Node`:
- Node describes the storage unit that allows LinkedList to function.
- Node does not represent a public domain concept.
- Node changes when LinkedList changes its implementation.
- Private static nested Node is a sensible way to organize it.

Conversely, `Order` and `Customer` may interact, but that does not mean Customer is an implementation detail of Order:
- Customer has its own identity/lifecycle.
- Multiple Orders point to the same Customer.
- Customer is used by multiple services.
- Top-level `Customer` is usually clearer than `Order.Customer`.

### “Sharing the Same File” Does Not Imply Cohesion

If two classes merely happen to be written in the same file because one person is maintaining them, nesting can obscure domain boundaries that ought to be separated.

**Consider the reason for change**:
- Do two types often need to change together because they share an invariant? Nesting may make sense.
- Does one type change for an independent reason? Top-level usually avoids unnecessary coupling.

## 27. Encapsulation: Private Nested Classes Help Hide Representation

A public class can keep its internal data structure hidden from the outside:

```java
public class UserIndex {
    private Node first;

    private static final class Node {
        final String username;
        Node next;

        Node(String username) {
            this.username = username;
        }
    }
}
```

Benefits:
- Consumers only see the public methods of UserIndex.
- Changing the Node representation does not force consumers to recompile against that source type.
- Private access across the nest can be used, reducing boilerplate getters added just so the two classes can communicate.
- The helper type cannot be misused by unrelated package code.

**However, encapsulation does not mean hiding all logic inside private classes.** If Node/Index both bloat, an interface or a dedicated top-level abstraction may clarify responsibilities.

## 28. Testability: When Is a Nested Class Hard to Test?

A private static nested helper cannot be tested from external code by its own name. However, this is **not necessarily a problem** if it is strictly an implementation detail:
- Test the owner's public operations.
- Verify observable behavior and invariants.
- Avoid tests tightly coupled to private implementation structure.

If the helper has complex and business-critical logic:
- You can extract it into a **package-private top-level class** to test within the same package.
- You can extract it into a public service/domain type if it has a real contract.
- You can pass dependencies/inject a strategy to test it separately.
- Or keep it private nested while writing thorough tests through the owner when coverage and maintainability are sufficient.

### Do Not Expose Implementation Just to Test a Field

A mistake is changing a private nested class to public nested just so a unit test can access a method. Widening visibility can expose an unintended API. First, reconsider behavioral tests and responsibility boundaries.

### Static Nested Is Easier to Test Than Inner When No Owner Is Needed

With an inner class, tests often have to construct an enclosing instance. If the helper is logically independent, a static nested or top-level class makes setup simpler.

## 29. Risk of Exposing Private Implementation Through a Public API

Example:

```java
public class Catalog {
    private static class InternalEntry {
        String code;
    }

    // Do not design a public API around InternalEntry.
}
```

A public method can at the source level declare a private nested return type, yet external callers have no way to use that type normally and completely. Such an API is hard to learn, hard to maintain, and coupled to the implementation.

Instead, expose:
- `public record EntryView(String code)` if this is a public data carrier belonging to Catalog;
- Or a top-level `CatalogEntry` if it is an independent domain concept;
- Or an appropriate public interface.

### Returning Values Through a Public Abstraction

The implementing class itself can be private nested, while the return type is public:

```java
public java.util.Iterator<String> iterator() {
    return new PrivateIterator();
}
```

This snippet illustrates the signature; `PrivateIterator` requires an appropriate implementation inside the owner.

API users do not need to know the implementation class. This is a sound encapsulation strategy.

## 30. Nested Types and the Java Module System (JPMS)

In a named module, a class being public **does not automatically mean** every other module can use it. Cross-module access also depends on:
- Whether the module containing the package `exports` that package to the consumer.
- Member/class accessibility.
- Compile/readability relationships between modules.
- Reflection may require `opens` or other mechanisms when accessing deep internals.

Example module descriptor:

```java
module com.example.billing {
    exports com.example.billing.api;
}
```

A public top-level type in package `com.example.billing.internal` does not automatically become an exported API just by being public. Conversely, a public static nested type in an exported API package can be part of the module's public surface.

**Nestmate private access and JPMS exports are two separate layers**:
- Nesting can grant private access between related classes.
- Export/module rules control whether other modules can access packages/types.
- You should not use a private nested class to bypass modular encapsulation.

Choose between top-level and nested in conjunction with the **package boundary** and **module API surface**, rather than looking only at a single source file.

## 31. Package Organization and Business Domain Responsibilities

In large projects, package structure is often just as important as nesting.

Example:

```text
com.acme.orders
    Order.java
    OrderLine.java
    OrderService.java

com.acme.pricing
    Money.java
    PricingPolicy.java

com.acme.orders.internal
    OrderIndex.java
```

If `OrderLine` has a public domain name and behavior, a top-level `OrderLine` is an easy choice to justify. If `Order` internally uses a `Node` to implement an internal linked buffer, a private static nested Node is appropriate.

### Package-Private Top-Level as a Middle Ground

Not every independent class has to be public:
- A top-level package-private helper allows **multiple classes in the same package** to collaborate.
- It does not force the helper to belong to a single owner.
- It does not turn the helper into a shared API for code in other packages.
- As the helper grows, it can be moved to a dedicated file without changing the qualified type name as exposed within the same package.

### However, Package Names Do Not Guarantee Dependency Architecture

Even when top-level types are neatly organized, if two modules have circular references or expose internals arbitrarily, the design still has issues. Nesting is only one part of the architecture.

## 32. Type Naming: Does `Outer.Part` Make Semantic Sense?

A public nested type creates the naming form `Outer.Part`.

Choose nested if a name such as:
- `Request.Builder`;
- `Parser.Token`;
- `StateMachine.Transition`;

helps users understand the context immediately.

Avoid nested if:
- `Order.Money` when Money is needed across multiple aggregates.
- `User.DateRange` when DateRange is a general time concept.
- `Screen.Logger` when Logger is a system-wide service.

Sometimes public types share names across multiple domains, and a qualified nested name reduces ambiguity. However, if nesting is used solely to avoid name collisions, revisit domain naming and packages first.

## 33. Nested Interface, Enum, and Record

Ordinary classes are not the only types that can be nested. In Java 17:
- Nested interfaces have **static semantics** according to the language rules.
- Member records are **implicitly static**.
- Member enums have corresponding static semantics.
- Interface nested types do not have an implicit enclosing instance like member inner classes.

Example:

```java
public final class Job {
    public enum Status {
        NEW, DONE
    }

    public record Result(Status status, String message) {
    }
}
```

You can use `Job.Status.DONE` and `new Job.Result(...)` without needing a Job instance.

### When Should an Enum/Record Be Nested?

- If `Status` genuinely describes the lifecycle of Job and carries no meaning outside Job, `Job.Status` clarifies the API.
- If `Status` is used across multiple aggregates with unified semantics, a top-level enum may be more appropriate.
- If `Result` is the sole result of the Job API, a nested record can be concise; if multiple APIs share that type, consider top-level.

### Are Records Automatically “Safe”?

A record is generally final, with final components, but if a component holds a mutable array/List, it is not automatically deeply immutable. The nested/top-level decision **does not replace** designing mutable ownership.

## 34. Runnable: Nested Record and Enum Accompanying an Owner

Save **`NestedResultChoiceDemo.java`**:

```java
public final class NestedResultChoiceDemo {
    public enum Status {
        OK, REJECTED
    }

    public record Result(Status status, String message) {
    }

    public static Result evaluate(int quantity) {
        if (quantity > 0) {
            return new Result(Status.OK, "accepted");
        }
        return new Result(Status.REJECTED, "invalid");
    }

    public static void main(String[] args) {
        System.out.println(evaluate(3));
        System.out.println(evaluate(0));
    }
}
```

```bash
javac -encoding UTF-8 NestedResultChoiceDemo.java
java NestedResultChoiceDemo
```

Stdout:

```text
Result[status=OK, message=accepted]
Result[status=REJECTED, message=invalid]
```

The nested enum/record express two types whose semantics are closely tied to the owner API; they do not need an enclosing instance.

## 35. Nested Generic Types and Independence

A generic enclosing class:

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

    static class Holder<U> {
        final U value;

        Holder(U value) {
            this.value = value;
        }
    }
}
```

- Member inner `Reader` can use `T` from the enclosing generic instance.
- Static nested `Holder<U>` has its own type parameter `U`.
- A static nested class cannot directly use Box's `T` as a type parameter of an Outer instance.

During design, if a nested helper starts needing independent type parameters and is used in multiple contexts, it may be a sign that a top-level generic helper is more appropriate.

Conversely, `Box<T>.Reader` expresses that **Reader is bound to a Box<T> instance**, which is right if the semantics require an owner.

## 36. Runnable: Generic Outer with Inner and Static Nested Classes

Save **`GenericClassChoiceDemo.java`**:

```java
public final class GenericClassChoiceDemo<T> {
    private final T value;

    GenericClassChoiceDemo(T value) {
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
        GenericClassChoiceDemo<String> box =
                new GenericClassChoiceDemo<>("Java");

        GenericClassChoiceDemo<String>.Reader reader =
                box.new Reader();

        GenericClassChoiceDemo.Holder<Integer> holder =
                new GenericClassChoiceDemo.Holder<>(17);

        System.out.println(reader.read());
        System.out.println(holder.read());
    }
}
```

```bash
javac -encoding UTF-8 GenericClassChoiceDemo.java
java GenericClassChoiceDemo
```

Stdout:

```text
Java
17
```

The type of Reader is bound to a parameterization of the generic enclosing type; Holder is independent and has its own type parameter.

## 37. Is “Static Nested Classes Run Faster Than Inner Classes” True?

You should not draw an absolute performance conclusion solely from the `static` keyword.

Design differences:
- An inner class has an enclosing-instance relationship, which can entail a reference/coupling and related costs.
- A static nested class does not require an implicit enclosing object.
- The JVM/JIT performs many optimizations, and layout/escape analysis and representation details should not be turned into rigid assumptions.
- The logic/allocations/locks inside the class usually affect performance more than the keyword on the declaration.

**Choose static nested for the right dependency semantics first**, then profile if performance truly matters.

Do not use object-size/bytecode predictions as the sole reason to change a public API.

## 38. Lifetime and Garbage Collection: What to Watch For

Any object still reachable from GC roots through reference paths can continue to be retained.

For nested/member inner classes:
- An inner instance can maintain a relationship to its enclosing instance.
- An anonymous/local callback can capture references, depending on the context.
- A long-lived registry/thread/executor can extend the lifetime of a callback.
- When the callback holds an owner reference, the owner can remain reachable.

For static nested classes:
- There is no implicit Outer instance from nesting.
- However, if the constructor accepts `Outer owner` and stores it in a field, it **still retains the owner**.
- Therefore, merely turning `class Inner` into `static class Helper` while still keeping `owner` does not automatically eliminate retention.

**Solve this by managing ownership and lifecycle**, not merely by changing a keyword.

### Example of an Anti-Pattern to Recognize

```java
class Screen {
    class Listener {
        void onEvent() {
            // Uses Screen's state.
        }
    }
}
```

If Listener is registered globally and never unregistered, Screen can live longer than expected. A static nested listener that accepts only an immutable ID and unregisters at the right time can be better if requirements permit.

## 39. Nested Classes and `synchronized`/Thread Safety

Choosing a nested or top-level class **does not automatically provide synchronization**.

```java
class Outer {
    private int count;

    class Inner {
        void increment() {
            count++;
        }
    }
}
```

Some people mistakenly think that because Inner sits inside Outer and accesses a private field, Java automatically locks the owner. **This is incorrect.**

- `count++` is not an atomic increment across multiple threads.
- Nesting does not create a lock.
- Static nested classes are not automatically thread-safe either.
- Local/anonymous classes capture mutable references, yet they do not automatically establish happens-before guarantees either.

If an object is shared between threads, appropriately use:
- Immutable state/snapshots;
- `synchronized`/locks with clear invariants;
- Atomic classes/collections;
- Or other higher-level concurrency mechanisms.

## 40. Source File Organization and Generated Class Files

A single source file `Outer.java` containing nested classes can produce multiple `.class` files when compiled.

Example:

```java
class Outer {
    static class Helper {
    }

    class Inner {
    }
}
```

The compiler may generate class files named similarly to:
- `Outer.class`;
- `Outer$Helper.class`;
- `Outer$Inner.class`.

**Do not treat generated `$...` names as a public business contract.** Compiler-generated details for local/anonymous classes can change and are not something source API users should rely on.

### Does a Nested Class “Run Inside” Outer?

Not in the sense that runtime objects share the same memory body. A nested class is still a separate runtime type with its own class metadata and corresponding instances. Nesting is a declaration/access/enclosing-context concept, not “one object physically residing inside another object”.

## 41. Using Reflection to Inspect Types

Java Reflection provides:
- `Class.isMemberClass()`;
- `Class.isLocalClass()`;
- `Class.isAnonymousClass()`;
- `Class.getEnclosingClass()`;
- `Class.getDeclaringClass()`;
- `Modifier.isStatic(clazz.getModifiers())`.

When choosing class organization:
- Reflection classification can assist framework/debug tooling.
- However, **do not use reflection as a substitute for API design**.
- Frameworks have their own constructor/visibility rules, so you need to evaluate the specific framework's contract.

### Note That “Nested” Differs from the Static Modifier at Runtime

Both a static nested member class and a member inner class can have `isMemberClass() == true`; the static modifier distinguishes them.

An ordinary top-level class is neither a member, local, nor anonymous class.

## 42. Runnable: Distinguishing Top-Level and Static Nested via Reflection

Save **`ReflectionChoiceDemo.java`**:

```java
import java.lang.reflect.Modifier;

final class PackageHelper {
}

public class ReflectionChoiceDemo {
    static class Nested {
    }

    class Inner {
    }

    public static void main(String[] args) {
        Class<?> top = PackageHelper.class;
        Class<?> nested = Nested.class;
        Class<?> inner = Inner.class;

        System.out.println(top.isMemberClass());
        System.out.println(nested.isMemberClass());
        System.out.println(inner.isMemberClass());

        System.out.println(Modifier.isStatic(
                nested.getModifiers()));
        System.out.println(Modifier.isStatic(
                inner.getModifiers()));
    }
}
```

```bash
javac -encoding UTF-8 ReflectionChoiceDemo.java
java ReflectionChoiceDemo
```

Stdout:

```text
false
true
true
true
false
```

The code does not rely on compiler-generated class file names. It only uses classification APIs with clear contracts.

## 43. Inheritance and Nesting Are Two Independent Concerns

A class can:
- Extend a superclass;
- Implement interfaces;
- Be top-level or nested;
- Have independent visibility appropriate to its declaration;
- Have or not have an enclosing instance.

Example:

```java
class Worker implements Runnable {
    @Override
    public void run() {
    }
}
```

and:

```java
class Outer {
    private static class Worker implements Runnable {
        @Override
        public void run() {
        }
    }
}
```

both implement Runnable. The main difference is **placement/access/naming**, not that implementing the interface has a different meaning.

An inner class `Outer.Inner` **does not automatically extend Outer**.

**Do not choose nested just because it “must inherit from Outer”**; if an is-a relationship is needed, declare inheritance properly and evaluate domain semantics.

## 44. Changing Top-Level to Nested: What Must Be Reviewed

Refactoring from:

```java
public class Token {
}
```

to:

```java
public class Parser {
    public static class Token {
    }
}
```

can change:
- Source type name: `Token` → `Parser.Token` at call sites/imports.
- Binary name of the class.
- Public API signatures where the type is used.
- Reflection/class-loading of the type name.
- Serialization/configuration/deserialization where the class name is persisted.
- Module packaging/export expectations.
- Framework annotations and class discovery.
- Constructor calls/visibility.

If this is an internal private helper not yet used by anything outside the owner, refactoring can be straightforward. If it is a **published public type**, this is usually a **breaking API change**.

### Do Not Assume Changing Nesting Only Edits One File

The scope of callers can be much broader: tests, generated code, reflection config, persisted data, and binary dependencies. You need to understand the compatibility contract first.

## 45. Changing Member Inner to Static Nested: Risks

Converting:

```java
class Outer {
    class Inner {
        String describe() {
            return Outer.this.toString();
        }
    }
}
```

into:

```java
class Outer {
    static class Inner {
        // No more Outer.this.
    }
}
```

is not just adding `static`. If the class uses the enclosing instance:
- You must pass a specific `Outer` reference when creating the helper.
- Constructors/call sites `outer.new Inner()` must change to `new Outer.Inner(owner)` or an equivalent factory.
- You must review lifetime, equality, and captured state.
- If public, source/binary compatibility may change.
- You must test behavior when multiple Outer instances exist.

If the helper **does not need** an enclosing instance, moving to static nested is usually a clearer improvement.

## 46. Changing Static Nested to Top-Level: When Does It Make Sense?

Signs that a helper is growing into an independent type:
- Imported/reused by multiple owners.
- Has multiple collaborators and state unrelated to Outer.
- Has direct unit tests as an API.
- Has its own business rules and multiple reasons to change.
- Needs its own public contract or package-level ownership.
- The qualified name `Outer.Helper` misleads about ownership.

Approach:
1. Precisely define the responsibility and public contract.
2. Create the top-level type with an appropriate name/package.
3. Move behavior; replace private access with clear APIs/dependencies instead of exposing all fields.
4. Update callers/imports.
5. Run compilation/tests of consumer modules.
6. If it is a public API, consider a compatibility/migration strategy.

**Do not extract a class solely because it is 200 lines long** if it remains a highly cohesive implementation detail of Outer. Length is a signal to review, not a hard rule.

## 47. When a Top-Level Class Wants to Access an Owner's Private State

A top-level class does **not** automatically have permission to access private fields of another class, even within the same package.

Example:

```java
class Outer {
    private int secret = 7;
}

class Helper {
    int read(Outer outer) {
        // return outer.secret; // Invalid: private.
        return 0;
    }
}
```

If `Helper` is a private static nested class of Outer, it can access `outer.secret` via nesting access.

Do not rush to add public getters for every private field just so the helper can use them; doing so can expose state more broadly than desired. Consider:
- Keeping the helper nested if it genuinely belongs to the implementation detail.
- Passing Helper a **value snapshot**/interface defined by the owner.
- Providing a well-bounded package-private operation if within the package.
- Extracting an abstraction/domain responsibility if the need spans beyond one owner.

## 48. Simpler Code Organization Is Sometimes a Method, Not a New Class

Before choosing between nested or top-level, ask:

> Do we actually need a new **class**?

If there is only a stateless transformation:

```java
private static boolean validQuantity(int quantity) {
    return quantity > 0;
}
```

a private static method inside the owner can be clearer than creating a `private static class Validator` that has just a single static method.

If the logic carries substantial state/invariants and needs a constructor, a class makes more sense. If the logic is a simple value carrier, a record may fit. If the logic is an encapsulated behavior to be passed around, a functional interface + lambda is also worth considering.

**Do not create too many nested classes just to group a few lines of code** when a method/record/enum already expresses it clearly.

## 49. Do Not Overuse “Utility Classes”

A giant `private static class Utils` containing:
- Date parsing;
- Currency conversion;
- HTTP calls;
- Validation;
- Logging;
- Formatting;

has very low cohesion. Making it nested does not fix the design problem.

Separate responsibilities along real boundaries:
- Domain value concepts can be top-level.
- Implementation helpers belonging solely to the owner can be private static nested.
- Cross-cutting services/utilities can be top-level classes with clear APIs.
- Small operations should remain methods.

**Naming something “Utils” or “Helper” is often a sign that you need a more meaningful name**, though not every Helper is wrong.

## 50. Too Many Local/Anonymous Classes Can Make Code Hard to Navigate

If a method contains many anonymous implementations, business logic can get buried inside callback blocks:

```java
register(new Callback() { /* lots of logic */ });
schedule(new Runnable() { /* lots of logic */ });
transform(new Function<>() { /* lots of logic */ });
```

These are illustrative snippets, not standalone runnable examples.

Ways to improve:
- Short callbacks → lambda.
- A long behavior used only within the method → local named class.
- Owner-specific reusable helper → private static nested.
- Independent business strategy → top-level implementation/service.

Consider **debuggability** and **testability** alongside reducing lines of source code.

## 51. Design Scenario: Parser, Token, and Lexer

A Parser needs tokens when analyzing data.

**Nested option:**

```java
public final class Parser {
    public record Token(String text, int position) {
    }
}
```

Makes sense if:
- Token has meaning only within the Parser API.
- Clients always work through Parser.
- Qualified `Parser.Token` reduces confusion with other tokens.
- No independent tokenizer is needed.

**Top-level option:**

```java
public record Token(String text, int position) {
}
```

Makes sense if:
- Token is used by Lexer, Parser, SyntaxHighlighter, IDE, and Analytics.
- It has its own contract and independent versioning.
- Multiple modules need to import Token without depending on Parser naming.

**There is no single absolute right answer**, but Token's responsibility needs to be decided first.

## 52. Design Scenario: Builder of an Immutable Value Object

An immutable `Config` has a multi-parameter constructor. `Config.Builder`:
- Expresses the purpose of creating Config.
- Is not an independent domain entity.
- Can be mutable during the build phase.
- Does not need an existing Config instance.

**Choose a public static nested Builder** when a public builder is the way to construct Config:

```java
Config config = new Config.Builder()
        .host("localhost")
        .port(8080)
        .build();
```

The example shows conceptual usage; the Config class and its methods must be defined according to the actual API.

Do not choose a member inner Builder because it requires an enclosing Config instance, which contradicts the goal of building a new Config.

## 53. Design Scenario: Iterator of a Collection

A collection can provide an Iterator.

A **member inner iterator** makes sense if:
- It needs to read/modify the owner instance itself.
- Binding to the owner/lifecycle is part of the design.
- Frequent access to enclosing state is needed.

A **static nested iterator** makes sense if:
- It only needs an explicit collection reference/array snapshot.
- You want to make the dependency explicit.
- You do not want an implicit enclosing relation.

A **top-level iterator** makes sense when the iterator is an independent/reusable abstraction across multiple collection types with its own contract.

There is no rule saying “an iterator must always be inner”; many Java implementations use different structures.

## 54. Design Scenario: DTO, Request, Response

A nested record `PaymentResponse.Result` can make sense if it belongs solely to PaymentResponse.

However, `Money` and `CurrencyAmount` should be considered **top-level domain value objects** when used across multiple requests/responses.

### Do Not Confuse Nested Types with JSON Hierarchy

JSON:

```text
{
  "order": {
    "id": "O1",
    "amount": 100
  }
}
```

does not force Java classes to be nested according to the JSON structure. A top-level `OrderDto` can still be serialized into a nested JSON object; that is the responsibility of DTO mapping/serialization.

**Java nesting is a source/API decision**, not a payload structure requirement.

## 55. Design Scenario: Event Listeners

A one-off listener just to print a simple log → lambda.

A long listener used only inside a setup method → local class or named helper.

A listener that is an implementation detail of one screen/controller → private static nested if no enclosing instance is needed, or inner if an owner relation is desired.

An event handler/service used across multiple parts of the system → a top-level class is more appropriate.

**Lifecycle must be considered**: a listener registered with an event bus can live a long time. Hiding a listener as an inner class does not exempt you from the responsibility to unregister it.

## 56. Design Scenario: Strategy Pattern

A `PricingPolicy` interface and multiple implementations:

```java
interface PricingPolicy {
    int price(int base);
}
```

If the policies are reusable business rules, top-level classes like `SeasonalPricingPolicy` and `MemberPricingPolicy` are usually appropriate.

If only one specialized policy applies inside an owner and is not reused, a private static nested class or local class is clear enough.

If the policy is just a single expression and the interface is functional, a lambda:

```java
PricingPolicy tenPercentOff = base -> base * 9 / 10;
```

is simpler than a named class.

**Do not use class placement to hide domain decisions**: a policy with significant business semantics needs its own name and tests even if it currently has only one caller.

## 57. Design Scenario: Value Object Shared by Multiple Aggregates

`Address`, `EmailAddress`, `Money`, `DateRange` are typically candidates for top-level records/classes because they:
- Do not depend on a parent instance.
- Have their own invariants and validation.
- Are reused across multiple aggregates.
- Have intrinsic value equality/hashing.
- Are easy to locate via IDE/search.

Example:

```java
public record Money(long cents, String currency) {
}
```

If Money only stays within the Invoice package, it can be package-private top-level instead of public; consider the public surface based on consumers.

**Being a record is not a mandatory reason to be top-level**: a nested record is still valid and useful if its domain role is genuinely subordinate.

## 58. Public API Stability and Source Compatibility

When a public type exists in a library:
- The package name + type name are part of the source API.
- For a nested class, the qualified name `Outer.Inner` matters for imports and references.
- Moving nested → top-level can force callers to update imports and method signatures.
- Binary name, reflection, serialized forms, and framework discovery can be affected.

If it is only a private static Node, the implementation can change without making commitments to clients. That is a major benefit of encapsulation.

### Principle

**Keep closed what is not yet a contract; expose what has stable meaning for consumers.**

Do not make `Outer.InternalNode` public just for convenient access to internal data, unless it is genuinely a meaningful API supported long-term.

## 59. Unit Testing After Refactoring Placement

A verification strategy:
1. Compile all sources under the target JDK/`--release`.
2. Run unit tests against public behavior.
3. If a helper was extracted to top-level, write tests directly for its own contract.
4. If an inner class was made static, test multiple enclosing instances to avoid pointing to the wrong owner.
5. Check memory retention/lifecycle callbacks if applicable.
6. Check serialization/reflection/framework registration if the type name is public.
7. Check access from actual packages/modules.
8. Check generics/type parameters and constructor call sites.
9. Do not mechanically assert compiler-generated names such as `Outer$1`.
10. If a library API is used by binary clients, check binary/source compatibility according to the versioning policy.

Only unit testing a single method without compiling callers is usually insufficient after moving a public type.

## 60. Exercise 1 — Choosing Node

A `LinkedStack` has a Node containing only `int value` and `Node next`. Node never needs `LinkedStack.this`, and no other code uses Node.

**Answer:** `private static class Node` inside LinkedStack is a good choice. A top-level Node would unnecessarily widen the name scope, and a member inner class would attach a meaningless implicit enclosing instance.

## 61. Exercise 2 — Choosing Money

`Money` is used across Order, Invoice, Refund, and Ledger; it has its own equality/invariants.

**Answer:** Usually a **top-level immutable value object** (record or final class), public/package-private depending on the module API. `Order.Money` makes Money look like it belongs exclusively to Order.

## 62. Exercise 3 — Choosing Builder

An immutable `UserProfile` needs a builder to create the object before a UserProfile instance exists.

**Answer:** A public/private **static nested Builder** (depending on the public API). Do not use a member inner Builder, which requires an existing UserProfile enclosing instance.

## 63. Exercise 4 — Choosing Cursor

`Document.Cursor` reads and replaces content of exactly one Document instance; the cursor makes no sense when separated from its owner.

**Answer:** A member inner class is a good candidate. If you want explicit dependency/lifecycle, a static nested Cursor accepting `Document owner` in its constructor can also be appropriate.

## 64. Exercise 5 — Choosing a Validator Used in Two Classes in the Same Package

`OrderValidator` is used by Order and ReturnRequest, without needing to be a public API.

**Answer:** A package-private top-level `OrderValidator` is usually appropriate. Making it private nested inside Order forces ReturnRequest to either depend on it or duplicate logic, which is not necessarily good.

## 65. Exercise 6 — Is Top-Level Private Valid?

```java
private class Helper {
}
```

outside any enclosing class.

**Answer:** No. A top-level ordinary class cannot be private. Choose package-private top-level or private member nested depending on the desired scope.

## 66. Exercise 7 — Can a Static Nested Class Read a Private Field?

```java
class Outer {
    private int x = 7;

    static class Helper {
        int get(Outer owner) {
            return owner.x;
        }
    }
}
```

**Answer:** Yes. Nested access allows reading the private field via an explicit `owner` reference. However, Helper has no `Outer.this`.

## 67. Exercise 8 — Is a Static Nested Class Automatically a Singleton?

```java
class Outer {
    static class Helper {
    }
}
```

**Answer:** No. Calling `new Outer.Helper()` multiple times creates multiple instances. `static` in a class declaration only pertains to the enclosing-instance relation and membership.

## 68. Exercise 9 — Does a Member Inner Class Automatically Extend Outer?

```java
class Outer {
    class Inner {
    }
}
```

**Answer:** No. Nesting is distinct from inheritance. Inner is not automatically a subtype of Outer.

## 69. Exercise 10 — Local Class Reused Across Three Methods?

A named local class is used in one method, and then a requirement arises to reuse the logic in three other methods.

**Answer:** Consider a private static nested member class if the logic belongs to one owner and does not need an instance; or top-level package-private if multiple classes in the package use it. Do not copy-paste three local declarations.

## 70. Exercise 11 — Small One-Off Callback

A handler only needs to call `System.out.println("done")` on callback.

**Answer:** If the API uses a functional interface, a lambda is usually the first choice. An anonymous class is also valid, though longer. Only prefer an anonymous class if anonymous `this`/subclass semantics are needed.

## 71. Exercise 12 — Anonymous Class Containing 200 Lines

An anonymous implementation has 200 lines, mutable fields, and helper methods, and needs independent testing.

**Answer:** Consider a named class; private static nested when it belongs solely to the owner, or top-level when it is independent logic. Do not keep it anonymous simply because it originally appeared at one call site.

## 72. Exercise 13 — Moving a Public Nested Type to Top-Level

A library exposes `Parser.Token`; a new version changes it to top-level `Token`.

**Answer:** This is usually an API change; update imports, signatures, reflection/serialization assumptions, and evaluate compatibility before releasing. It must not be treated as a harmless internal refactoring.

## 73. Exercise 14 — Retaining the Owner via a Listener

A non-static inner listener is retained by a singleton event bus after the UI screen closes.

**Answer:** There is a risk of memory retention of the enclosing screen; use lifecycle unregistration and consider a static helper/minimal capture if no owner instance is needed.

## 74. Exercise 15 — Package-Private vs. Private Nested

A helper is used only by `Order`. Should it be package-private top-level or private static nested?

**Answer:** If it is genuinely an implementation detail specific to Order and needs no owner instance, private static nested expresses ownership more clearly and hides it more tightly. Package-private top-level is not wrong, but its scope is broader.

## 75. Exercise 16 — Top-Level Type Holding a Resource

A `PaymentGateway` holds its own connection/lifecycle and is injected into multiple services.

**Answer:** Usually a top-level service type/interface, not nested under Order just because Order calls it. The resource/dependency should manage its lifecycle independently.

## 76. Exercise 17 — Nested Enum

`Job.Status` pertains strictly to the Job lifecycle.

**Answer:** A public nested enum `Job.Status` is a design that can make sense. If multiple aggregates share states under the same contract, a top-level enum may be clearer.

## 77. Exercise 18 — Inner Class and Generic Outer

`Box<T>.Reader` wants to read private `T value` from a specific Box instance.

**Answer:** A member inner class is suitable. A static nested class would not have the implicit enclosing instance/type parameter T from Box and would have to accept the appropriate owner/type parameter explicitly.

## 78. Exercise 19 — Package Export

A `public class Internal` resides in a package not exported by the module.

**Answer:** Another module cannot automatically access that class just because it is public. Module exports/readability must be considered. Being nested or top-level does not change the JPMS mechanism.

## 79. Exercise 20 — “Not Wanting Many Files”

A developer places `User`, `Order`, `Payment`, and `Invoice` as nested types of `Application` to reduce the file count.

**Answer:** This is usually a weak reason. Types with independent responsibilities should use an appropriate top-level/package/module design, even if it produces more files. Fewer files do not guarantee cohesion.

## 80. Exercise 21 — Inner Class That Does Not Use Its Owner

A `class Helper` inside Outer does not access Outer's fields/methods and has no owner lifecycle requirement.

**Answer:** You should usually consider adding `static` to the nested member class to remove the implicit enclosing instance coupling. If the helper is an independent concept, consider top-level.

## 81. Exercise 22 — Can a Static Nested Class Still Retain Its Owner?

A static nested Helper constructor takes `Outer owner` and stores it in a field `private final Outer owner`.

**Answer:** It can still keep Outer alive long-term through the explicit reference. `static` does not automatically eliminate memory retention caused by fields you intentionally store.

## 82. Exercise 23 — A Method with Three-Line Helper Logic

To validate `quantity > 0`, do we need to create a private static nested `QuantityValidator`?

**Answer:** Not necessarily. A private static method can be simpler, unless the logic needs its own state, extensibility, or a type with a responsibility worth naming.

## 83. Exercise 24 — Nested Class and Performance

A member inner class and a static nested class both perform a simple addition. Can we state that static nested is always faster?

**Answer:** No. The primary difference is dependency/enclosing instance semantics. Runtime performance also depends on the compiler/JIT, data layout, allocations, and actual behavior; measure when required.

## 84. Exercise 25 — Testability of a Private Node

A `LinkedStack` has a private static nested Node. External unit tests cannot access Node directly.

**Answer:** That is not necessarily bad. Test `push/pop` and invariants through the public API; only consider separating the type/visibility if Node becomes a reusable domain concept with its own contract.

## 85. Common Design Mistakes Table

| Mistake | Consequence | Better Choice |
| --- | --- | --- |
| Putting every class into one Outer for fewer files | God class, low cohesion | Top-level by responsibilities |
| Defaulting to inner for every helper | Unnecessary owner coupling/lifetime | Static nested if `Outer.this` is not needed |
| Making every nested implementation public | Bloated API, hard to change | Private nested or package-private |
| Placing Money under Order even though many modules use it | Semantically misleading qualified name | Top-level Money |
| Using public top-level just to test an internal helper | Unintended API expansion | Test behavior or package-private |
| Choosing static nested thinking it is a singleton | Misunderstanding the modifier | Design a separate singleton if needed |
| Assuming an inner class is a subtype of Outer | Wrong type relationship | Distinguish nesting from inheritance |
| Trying to use a local class from another method | Name out of scope | Member/top-level named class |
| Refactoring anonymous → lambda without checking `this` | Behavior may change | Check lexical scope |
| Using a long anonymous class with multiple responsibilities | Hard to debug/test | Named class |
| Using nested helpers to access private members everywhere | Excessive coupling | Narrow the interface/invariants |
| Global inner listener without unregistering | Retains owner long-term | Lifecycle cleanup, static helper |
| Storing owner in static nested and assuming no leak | Owner remains reachable | Manage explicit references |
| Moving public nested to top-level without checking clients | Breaking source/binary APIs | Compatibility/migration |
| Assuming top-level private is valid | Compile error | Package-private or private nested |
| Assuming public automatically bypasses JPMS exports | Module access error | Design exports/opens properly |
| Assuming nested is definitely faster/slower | Decision lacking evidence | Benchmark/profile when needed |
| Treating generated class names as a contract | Unstable compiler detail | Public type names/contracts |
| Mistaking a nested record for an inner instance | Wrong static semantics | Recognize nested records are implicitly static |
| Assuming nesting provides thread safety | Data races still occur | Independent concurrency contract |

## 86. Checklist for Choosing Class Organization

1. Does the new type represent an **independent business concept**?
2. Is it reused by multiple classes/packages?
3. Does it have its own lifecycle?
4. Does it need to be exposed in the public API?
5. If public, does the name `Outer.Type` help clarify ownership?
6. If it serves only one owner, is it genuinely an implementation detail?
7. Does the helper **need an enclosing instance `Outer.this`**?
8. If not needed, have you considered `private static nested`?
9. If an owner is needed, should it keep an implicit relation or an explicit reference?
10. Is there a risk of an event listener/callback keeping the owner alive too long?
11. Can a single private method be used instead of a new class?
12. Is the logic only inside one method? Is a local named class appropriate?
13. Is it short inline logic? Is an anonymous class/lambda appropriate?
14. If anonymous, does it use anonymous `this`, super, or fields?
15. If refactoring anonymous → lambda, have you checked lexical scope?
16. If local/anonymous captures variables, are they final/effectively final?
17. Are captured mutable objects thread-safe if used concurrently?
18. Should the top-level type be public or package-private?
19. Should the member nested type be public, protected, private, or package-private?
20. Are you widening visibility just to test an implementation?
21. As the type grows, does it have multiple reasons to change?
22. Does the type have static generics/enclosing generic parameter dependencies?
23. Does the API distinguish nested interfaces/enums/records from member inner classes?
24. Does changing nesting alter an exposed source/binary name?
25. Do Java modules/packages export the exact intended public types?
26. Do reflection/serialization/frameworks rely on a specific class name?
27. Does the file organization make IDE/search/find-usages easy to understand?
28. Does a separate implementation need independent unit tests, or is testing through the owner sufficient?
29. Are dependencies overly hidden when using private access between nested classes?
30. Are you speculating about performance from `static` without measuring?
31. For concurrent behavior, have you separated thread safety from the nesting choice?
32. Are you prioritizing **responsibility and ownership** over the number of files/source lines?

## Conclusion

**Choose a top-level class** when the type is an independent concept, has its own lifecycle/API, is used by multiple components, or needs to be extended outside a single owner. A top-level class can be `public` or **package-private**, and does not necessarily have to be exposed across the entire system.

**Choose a static nested member class** when the type is an implementation detail or companion type closely tied to an enclosing class, yet **does not need an implicit enclosing instance**. This is usually a good choice for `Node`, `Builder`, `Helper`, formatters, or internal implementations.

**Choose a non-static member inner class** when an instance genuinely **belongs to and works with a specific enclosing object**. At the same time, evaluate coupling, lifecycle, and the risk of retaining the owner reference longer than intended.

**Choose a local class** when you need a named implementation that only makes sense within one block; **choose an anonymous class** for a short inline implementation when class semantics are needed; consider a **lambda** for a short behavior of a functional interface.

The best decision is not a design with more or fewer class files, but a design where **type name, scope, owner relationship, access level, and API boundary** accurately convey the meaning of the system. Each class should be placed where it accurately reflects **who owns its responsibility** and **who actually needs to use it**.
