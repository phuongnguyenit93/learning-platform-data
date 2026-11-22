# instanceof with Interface Types in Java (Java 17+)

## 1. Meaning: Checking Whether an Object Implements an Interface Contract

In Java, an `interface` describes a **behavioral contract**. Many different classes can `implements` the same interface even without sharing a direct superclass. The `instanceof` operator lets you ask at **runtime**: does the referenced object belong to a type that implements that interface?

```java
interface Printable {
    String render();
}

record Invoice(String id) implements Printable {
    @Override
    public String render() {
        return "Invoice " + id;
    }
}
```

If `Object value = new Invoice("A1");`, then `value instanceof Printable` returns `true`. A variable with a **declared type** of `Object` can still reference an actual `Invoice` object. `instanceof` checks the runtime type of the object, so the result does not depend on whether the variable was originally declared as `Object`, `Serializable`, another interface, or a suitable superclass.

This is a **type-relationship check**, not a string-based method-name check. A class that declares a method named `render()` on its own, **without** `implements Printable`, does not automatically become a `Printable`.

## 2. Two Ways to Write It: Boolean `instanceof` and Type Pattern

### Traditional Way: Check Then Cast

```java
static void printOld(Object value) {
    if (value instanceof Printable) {
        Printable printable = (Printable) value;
        System.out.println(printable.render());
    }
}
```

The expression `value instanceof Printable` returns a `boolean`. If true, casting `(Printable) value` inside the `if` branch is valid for the same object that was checked. This style still works.

### Pattern Matching: Check and Declare the Variable Together

Since Java 16 (JEP 394, finalized), you can write a **type pattern**:

```java
static void printNew(Object value) {
    if (value instanceof Printable printable) {
        System.out.println(printable.render());
    }
}
```

The form `expression instanceof InterfaceName variable` has three effects:

1. Checks whether the evaluated object matches the interface `InterfaceName`.
2. If it matches, creates the pattern variable `variable` with the **static type** of that interface.
3. Allows using the variable in scopes where the compiler knows the check succeeded.

Here `printable` has type `Printable`, so you can call `render()` and any other methods declared on `Printable`. Manual casting is no longer needed.

**Note:** `Printable printable` here is a *type pattern*, not a method parameter declaration syntax. `instanceof` only checks and assigns the variable when the object matches; it does not create a new object or copy data.

## 3. Runnable Program: One Interface, Multiple Implementations

Save all of the following code into **InterfaceInstanceofDemo.java**. The example uses syntax that is finalized in Java 17:

```java
public class InterfaceInstanceofDemo {

    interface Printable {
        String render();
    }

    interface Tagged {
        String tag();
    }

    record Invoice(String id, int total)
            implements Printable, Tagged {
        @Override
        public String render() {
            return "Invoice " + id + ": " + total;
        }

        @Override
        public String tag() {
            return "BILL";
        }
    }

    static final class Note implements Printable {
        private final String text;

        Note(String text) {
            this.text = text;
        }

        @Override
        public String render() {
            return "Note " + text;
        }
    }

    static void inspect(Object value) {
        if (value instanceof Printable printable) {
            System.out.println("Printable: " + printable.render());

            if (printable instanceof Tagged tagged) {
                System.out.println("Tag: " + tagged.tag());
            }
        } else {
            System.out.println("Not printable");
        }
    }

    public static void main(String[] args) {
        inspect(new Invoice("A1", 250));
        inspect(new Note("Hello"));
        inspect("plain text");
        inspect(null);
    }
}
```

Compile and run from the directory containing the file:

```bash
javac InterfaceInstanceofDemo.java
java InterfaceInstanceofDemo
```

**Exact output:**

```text
Printable: Invoice A1: 250
Tag: BILL
Printable: Note Hello
Not printable
Not printable
```

Explanation for each object:

- `Invoice` both `implements Printable` and `implements Tagged`, so it matches **both** patterns. Both the `render()` and `tag()` lines are printed.
- `Note` only `implements Printable`, so it matches the first pattern, while `printable instanceof Tagged tagged` does not match.
- `String` can be printed via `toString()`, but that does not mean it `implements Printable`; the `else` branch runs.
- `null` does not match any `instanceof` type pattern, so it also enters the `else` branch.

Notably, the variable `printable` inside the `if` has a declared type of `Printable`, yet you can still check `instanceof Tagged` on it: the runtime object can implement **multiple independent interfaces**. You do not need to know the concrete class is `Invoice`.

## 4. How Interface Matching Works in the Type System

Suppose:

```java
interface HasId {
    String id();
}

interface Auditable extends HasId {
    void audit();
}

class AuditEntry implements Auditable {
    @Override
    public String id() {
        return "E-1";
    }

    @Override
    public void audit() {
        System.out.println("audited");
    }
}
```

This is a standalone illustrative example separate from the program in section 3. With `Object obj = new AuditEntry();`:

- `obj instanceof Auditable` is `true` because the class `AuditEntry` directly implements `Auditable`.
- `obj instanceof HasId` is also `true` because `Auditable extends HasId`: the object implements inherited interfaces as well.
- `obj instanceof Runnable` is `false` because `AuditEntry` does not implement `Runnable`.

Similarly, if a superclass already `implements HasId`, an instance of a subclass inheriting that type behavior also matches `HasId`. When checking an interface, Java evaluates the **actual runtime type and `extends`/`implements` relationships**, not just the class name written next to the variable.

An object can match multiple interfaces at the same time; the checks are not mutually exclusive. Therefore `if (x instanceof A) { ... }` and `if (x instanceof B) { ... }` can both execute, whereas `if ... else if ...` only executes the first matching branch.

## 5. Pattern Variable Scope (Flow Scoping)

The compiler only allows using a pattern variable at points where the true condition is guaranteed to hold.

### Inside an `if` Branch and the `&&` Operator

```java
static void printIfNonEmpty(Object input) {
    if (input instanceof Printable p
            && !p.render().isEmpty()) {
        System.out.println(p.render());
    }
}
```

The `&&` operator evaluates the right-hand side only when the left-hand side is true, so `p` is available on the right-hand side and inside the `if` body. This example assumes `render()` returns a non-`null` string; if the interface allows returning `null`, check for it separately before calling `isEmpty()`.

Conversely, you cannot use `p` as if it were always assigned on the right-hand side of `||`:

```java
// Invalid: p is not guaranteed to exist when the right-hand side needs to be evaluated.
// if (input instanceof Printable p || p.render().isEmpty()) { }
```

### Negated Condition and Early Return

```java
static String renderOrFallback(Object input) {
    if (!(input instanceof Printable p)) {
        return "unsupported";
    }
    return p.render();
}
```

After the `if` statement, execution only continues when the pattern has matched, because the negated branch has already executed `return`. Therefore `p` can be used on the `return p.render()` line. With `new Invoice("A1", 250)`, the returned result is `"Invoice A1: 250"`; with `null`, it returns `"unsupported"`.

A variable declared in a type pattern does not have free scope across the entire method. Avoid reusing the same name within the same scope in a way that causes duplicate declaration conflicts, and read compiler errors to determine the exact places where the variable is in scope.

## 6. Which Methods Does an Interface Type Allow Calling?

When using `input instanceof Printable p`, the variable `p` has **static type `Printable`**. The compiler only allows calling methods declared by the `Printable` interface (along with applicable `Object` methods), even if the runtime class has additional methods of its own.

For example, `Invoice` in the main program has the record accessors `id()` and `total()`, but `Printable` does not declare them:

```java
if (value instanceof Printable p) {
    p.render();      // Valid: Printable declares render().
    // p.total();    // Compile error: Printable does not declare total().
}
```

If you actually need functionality from another interface, match that interface as well:

```java
if (value instanceof Printable p
        && value instanceof Tagged t) {
    System.out.println(p.render() + " / " + t.tag());
}
```

This example clearly expresses that the object must satisfy **both contracts**. If you need a specific class, you can match `Invoice invoice`, but doing so couples the code directly to one implementation. Prefer matching an interface when the business logic cares about the **capability to perform a behavior**, rather than the class identity.

`instanceof` does not call `render()` just to test whether it matches. The method only runs when your code actually invokes it after the check.

## 7. `null` Values and Known Static Types

### When the Value Is `null`

```java
Object candidate = null;
System.out.println(candidate instanceof Printable); // false
```

Neither the boolean expression nor the type pattern matches `null`. There is no `NullPointerException` merely from performing an `instanceof` check; an error can only occur if you access the object or call a method unsafely elsewhere.

### When the Variable Already Has the Interface Type

```java
Printable p = new Invoice("A2", 100);
boolean present = p instanceof Printable; // true if p != null
```

If the goal is only to check whether an object is present, `p != null` is usually clearer. When a variable is already declared as `Printable`, checking the same interface again adds no new information about whether `render()` can be called.

There is a **Java version difference**: Java 17 does not allow an unconditional type pattern `p instanceof Printable matched` if the static type of `p` is already a subtype of `Printable`; Java 21+ allows certain unconditional patterns in `instanceof`. To keep examples compatible with Java 17, use `p != null` in this case. However, `p instanceof Tagged t` is still useful because `Printable` and `Tagged` are two independent interfaces, and the runtime object may implement both.

### Checks That Can Be Rejected at Compile Time

Not every pair of types can be used with `instanceof`. If the compiler can prove that a value cannot belong to the target type according to Java's type rules (for example, a variable whose static type is a `final` class that does not implement the interface being matched), the expression can fail at compile time with an incompatible types error. If the input object may have multiple possible types, use an appropriate supertype/interface reference, such as `Object`, to perform the runtime check when needed.

## 8. Generic Interfaces: You Can Check `List<?>`, Not `List<String>`

Because of **type erasure**, the Java runtime does not retain the full type arguments of most generic instances. Therefore, you cannot use `instanceof` to distinguish `List<String>` from `List<Integer>` with syntax like this:

```java
// Invalid: the String type argument cannot be verified at runtime.
// if (value instanceof java.util.List<String> names) { }
```

Instead, use the reifiable wildcard form:

```java
import java.util.List;

static void inspectList(Object value) {
    if (value instanceof List<?> items) {
        System.out.println("size=" + items.size());

        if (!items.isEmpty()
                && items.get(0) instanceof String first) {
            System.out.println("first=" + first);
        }
    }
}
```

With `inspectList(List.of("A", "B"))`, the output is:

```text
size=2
first=A
```

`List<?>` confirms that the object implements the `List` interface, but **does not assert** that the elements have type `String`. Thus `items.get(0)` returns a value of static type `Object`; check further with `instanceof String first` if your logic requires the element to be a string. Checking one element does not prove that all elements are `String`; to verify the entire list, you must check each element.

For generic interfaces you define yourself, the same rule applies: non-reifiable type arguments cannot be arbitrarily checked with `instanceof`.

## 9. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| `instanceof Printable` only matches a class named `Printable`. | `Printable` is an interface; **any class implementing the contract** (including through inheritance) can match. |
| Simply having a `render()` method on a class is enough to match. | Java uses explicit `implements`/`extends` type relationships; matching a method name is not enough. |
| Because the declared type is `Object`, it cannot match an interface. | `instanceof` inspects the runtime type; `Object` can hold a reference to an instance implementing the interface. |
| `instanceof` throws an error when the variable is `null`. | `null instanceof Interface` evaluates to `false`. |
| Matching `Printable p` lets you call every method of the runtime class. | `p` has static type `Printable`; methods outside the interface require a different type or an additional check. |
| Only one interface can match at a time. | An object can implement multiple independent interfaces; patterns for each can match. |
| Matching `List<?>` proves all elements are strings. | It checks the `List` interface, not the generic type argument or the type of every element. |
| A pattern variable can be used anywhere after the `if`. | Scope depends on control flow and whether the match is guaranteed. |

Another design mistake is writing a chain of `if (x instanceof ConcreteA) ... else if (x instanceof ConcreteB) ...` when those classes all implement a common interface that already provides the method you need to call. In that case, you can simply work with the interface and polymorphism:

```java
static void print(Printable printable) {
    if (printable != null) {
        System.out.println(printable.render());
    }
}
```

Use `instanceof` when **the object comes from a broader type** or when a behavior depends on whether the object supports **an additional interface**. If the caller already guarantees `Printable`, calling the method directly through the interface is usually simpler.

## 10. Exercises and Solutions

### Exercise 1 — Two Classes Implementing a Shared Contract

Given:

```java
interface Payable {
    int amount();
}

record Order(int amount) implements Payable {}
record Salary(int amount) implements Payable {}
```

Write a method that takes an `Object`, returns `amount()` if the object implements `Payable`, and otherwise returns `0`.

Solution (placed alongside the declarations above):

```java
static int amountOrZero(Object value) {
    if (value instanceof Payable payment) {
        return payment.amount();
    }
    return 0;
}
```

Results: `amountOrZero(new Order(120)) == 120`, `amountOrZero(new Salary(500)) == 500`, and `amountOrZero(null) == 0`. There is no need to distinguish `Order` from `Salary` because both already provide `amount()`.

### Exercise 2 — An Object Implementing Multiple Interfaces

Given `Object value = new Invoice("Z9", 80);` from the complete program in section 3, are the following expressions true or false?

- `value instanceof Printable`: **true**, because `Invoice implements Printable`.
- `value instanceof Tagged`: **true**, because `Invoice implements Tagged`.
- `value instanceof Runnable`: **false**, because `Invoice` does not implement `Runnable`.
- After `if (value instanceof Printable p)`, is calling `p.tag()` directly valid? **No**, because `tag()` belongs to `Tagged`, not `Printable`; you need to check for `Tagged` or use a reference of type `Tagged`.

### Exercise 3 — Checking Generic Elements Individually

Given `Object value = java.util.List.of("Java", 21);`, write a check `value instanceof java.util.List<?> items` and then classify the first element. Sample solution:

```java
if (value instanceof java.util.List<?> items
        && !items.isEmpty()) {
    Object first = items.get(0);
    if (first instanceof String text) {
        System.out.println(text.toUpperCase());
    } else {
        System.out.println("first item is not a String");
    }
}
```

Here it prints `JAVA`, because the first element is the string `"Java"`. Even though the list contains an `Integer` element at another position, using `List<?>` is valid; there is no false assumption that all elements have the same type.

## 11. Key Takeaways

- **`x instanceof MyInterface`**: returns `true` when `x != null` and the object's runtime type directly or indirectly implements `MyInterface`.
- **`x instanceof MyInterface m`**: both checks and introduces a variable of type `MyInterface` in places where the match is guaranteed; this is a finalized type pattern since Java 16 and works well in Java 17+.
- An object can match **multiple interfaces**; a type pattern does not grant access to methods outside the interface it declares.
- `instanceof List<?>` only proves the object is a `List`, not its generic type argument. `null` never matches.
- When a method already receives the right interface type, prefer invoking behavior through the interface; use `instanceof` when narrowing from `Object` or checking for optional capabilities.

Official references:
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java Language Specification — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
