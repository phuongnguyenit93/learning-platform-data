# `null` Objects and Calls Through Interface References in Java

An interface-typed variable can hold a reference to an object of an implementing class **or the value `null`**. When the variable holds an object, Java uses **polymorphism** to select the appropriate instance method implementation at runtime. When the variable holds `null`, there is no object to execute the method: an instance method call through that reference causes a `NullPointerException` (`NPE`).

This lesson clarifies what is checked **at compile time**, what happens **at runtime**, why `default` methods also cannot be called through a `null` reference, and how to handle null according to the API contract.

## 1. `null` is not an object implementing an interface

Example:

```java
interface Notifier {
    void send(String message);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("Console: " + message);
    }
}
```

The following declarations are all valid when placed inside an appropriate method or code section:

```java
Notifier active = new ConsoleNotifier();
Notifier absent = null;
Notifier another = active;
```

`active` and `another` hold references to **the same object**, a `ConsoleNotifier`. `absent` does not point to any object. The declared type of all three variables is `Notifier`, but their actual values may differ.

Important distinctions:

- An **interface** is a reference type that defines a contract. An object cannot be created directly using `new Notifier()`.
- An **object** is created by a concrete class, for example `new ConsoleNotifier()`, and can then be held in an interface-typed variable.
- **`null`** is a value representing the absence of a reference to an object; it is not an instance of `Notifier`, `ConsoleNotifier`, or `Object`.
- Assigning `null` to an interface-typed variable is allowed: `Notifier absent = null;`. That declaration **does not create** an object with empty methods and does not call a constructor either.
- Declaring, assigning, passing, or returning `null` through a reference type does not usually cause `NullPointerException` by itself. The error occurs when code performs an operation that requires a real object.

A variable declared as an interface **does not guarantee it is always non-null**. Java 17's ordinary reference type system allows the value `null` unless the application applies additional contracts or checking tools.

## 2. Two phases: compile-time type checking and runtime dispatch

Consider the call:

```java
Notifier notifier = new ConsoleNotifier();
notifier.send("hello");
```

**At compile time**, the compiler knows the declared type of `notifier` is `Notifier`. It verifies that `Notifier` has an instance method `send(String)` that the current code is allowed to call.

**At runtime**, Java checks the actual object that the variable references. Because the object here is a `ConsoleNotifier`, the JVM executes `ConsoleNotifier.send(String)` and prints:

```text
Console: hello
```

Replace the object value with `null`:

```java
Notifier notifier = null;
notifier.send("hello");
```

The code still **compiles cleanly**: `Notifier` declares `send(String)`. However, at runtime a **`NullPointerException`** will occur, because there is no target object to execute the method.

Important rule:

> The interface type determines which methods can be **called syntactically and by type**; the actual object determines which implementation **is executed**. If the reference is `null`, there is no object to dispatch to.

Do not confuse `null` with “a class that does not override the method”. When there is no object, Java cannot run an instance method of any class. The exception is thrown at the call operation, before the body of the target method begins.

## 3. Runnable Java 17+ example: `null`, `default`, `static`, and polymorphism

Create the file **`NullInterfaceDemo.java`**:

```java
interface Notifier {
    String CHANNEL = "message";

    void send(String text);

    default void ping() {
        System.out.println("Notifier ping");
    }

    static String category() {
        return "notification";
    }
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String text) {
        System.out.println("Console: " + text);
    }
}

public class NullInterfaceDemo {
    public static void main(String[] args) {
        Notifier missing = null;

        System.out.println("is null: " + (missing == null));
        System.out.println("instanceof Notifier: "
                + (missing instanceof Notifier));

        // Access static members using the interface name.
        System.out.println("channel: " + Notifier.CHANNEL);
        System.out.println("category: " + Notifier.category());

        try {
            missing.send("hello");
        } catch (NullPointerException e) {
            System.out.println("send: NullPointerException");
        }

        try {
            missing.ping();
        } catch (NullPointerException e) {
            System.out.println("ping: NullPointerException");
        }

        Notifier active = new ConsoleNotifier();
        active.send("hello");
        active.ping();
    }
}
```

Compile and run:

```bash
javac NullInterfaceDemo.java
java NullInterfaceDemo
```

Output:

```text
is null: true
instanceof Notifier: false
channel: message
category: notification
send: NullPointerException
ping: NullPointerException
Console: hello
Notifier ping
```

Explanation of each group of results:

1. `missing == null` is `true` because the variable does not reference any object.
2. `missing instanceof Notifier` is `false`. The `instanceof` operator does not consider `null` an instance of any type.
3. `Notifier.CHANNEL` is a `public static final` field of the interface; `Notifier.category()` is a `static` method of the interface. Both are accessed via the **type name**, without needing a `Notifier` object.
4. `missing.send(...)` causes a `NullPointerException` even though `send` is validly declared in the interface. The compiler checks the signature successfully but does not create an object for `missing`.
5. `missing.ping()` also causes a `NullPointerException`, even though the `default` method has a body right inside the interface. **`default` is still an instance method**, requiring a target object.
6. After `active` holds `new ConsoleNotifier()`, `active.send(...)` runs the concrete class's overridden method; `active.ping()` uses the `default` implementation inherited from the interface.

In regular application code, you should not use `try/catch (NullPointerException)` to check whether a reference is null. Here, `try/catch` only demonstrates that **both calls throw an error** so the program continues running and displays the full output.

## 4. Which calls require an object? How do static fields and methods differ?

Distinguish among the following member forms:

| Expression | Does it require an object? | When the reference variable is `null` |
| --- | --- | --- |
| `ref.send("x")` (instance method) | Yes | `NullPointerException` |
| `ref.ping()` (`default` method) | Yes | `NullPointerException` |
| `ref.toString()` (`Object` instance method) | Yes | `NullPointerException` |
| `ref == null` | No | Returns `true` |
| `ref instanceof Notifier` | No dereference needed | Returns `false` |
| `Notifier.CHANNEL` (static field) | No | Accessible via the interface name |
| `Notifier.category()` (static method) | No | Callable via the interface name |

`toString()` in the table is an instance method of `Object` and also requires an object. A non-`null` interface reference can call appropriate public methods from `Object` according to Java rules; however, a `null` variable cannot execute `toString()`.

For a **static method declared in an interface**, the correct way to call it is `Notifier.category()`. Do not confuse it with a `default` method; interface static methods are not inherited as instance methods to be called through a `Notifier` variable. Therefore, the example focuses on syntax with the interface type name and avoids writing `missing.category()`.

Even though the expressions `Notifier.CHANNEL` and `Notifier.category()` are called when `missing == null`, they **do not use** the value of `missing`. Being able to access static members does not make `missing` a valid object.

## 5. `null` when passing parameters, returning values, and reassigning references

An interface is often used as a parameter type or return type to decouple calling code from implementing classes:

```java
static void dispatch(Notifier notifier) {
    notifier.send("start");
}
```

The snippet above is **an illustrative method**, placed in the same context as the `Notifier` declaration in Section 3. `dispatch(new ConsoleNotifier())` works normally, whereas `dispatch(null)` still passes the type check at the call site but will cause a `NullPointerException` when `dispatch` attempts to call `notifier.send(...)`.

This applies similarly to methods returning an interface:

```java
static Notifier findNotifier(boolean enabled) {
    return enabled ? new ConsoleNotifier() : null;
}
```

The compiler allows both a `ConsoleNotifier` object and `null` to be a return value of type `Notifier`. **The caller** must understand the contract: can this method return `null`, or is it guaranteed to always return a valid implementation?

A variable can change its value over time:

```java
Notifier first = new ConsoleNotifier();
Notifier second = first;
first = null;

second.send("still works");
```

Here, `first = null` **does not destroy the object** referenced by `second`. `second.send(...)` still runs normally and prints `Console: still works`. `null` is a value of the **reference variable**; reassigning one variable does not delete or make `null` other references pointing to the same object.

## 6. Safe ways to check and handle `null`

The appropriate approach depends on the **business contract**. There are two very different situations:

### Case A — having no object is valid

If the requirement allows having no notifier, only call it when one exists:

```java
static void notifyIfPresent(Notifier notifier) {
    if (notifier != null) {
        notifier.send("ready");
    }
}
```

If the input can validly be `null`, the method above implements the “skip if there is no notifier” policy. Do not use this policy by default for every API; silent skipping can hide configuration or data errors.

It can also be written using an early-exit branch:

```java
static void notifyIfPresent(Notifier notifier) {
    if (notifier == null) {
        return;
    }
    notifier.send("ready");
}
```

Behaviorally, the two snippets above are identical for this example method. There is no need to catch an exception to perform a simple `null` check.

### Case B — an object is required

Use `Objects.requireNonNull` to validate input at the API boundary and detect errors early:

```java
import java.util.Objects;

static void notifyRequired(Notifier notifier) {
    Objects.requireNonNull(notifier, "notifier");
    notifier.send("ready");
}
```

These are illustrative lines inside a class that has access to the declared `Notifier`; this is not a standalone Java file. When `notifier` is `null`, `Objects.requireNonNull` throws `NullPointerException` with the message `"notifier"`. When it is non-`null`, it returns the reference itself and the method continues.

If a different exception contract is needed, you can proactively throw `IllegalArgumentException` or an appropriate custom exception. Choose a consistent convention and document it clearly in the API.

### Case C — providing explicit fallback behavior

If the policy is “when there is no recipient, use the default recipient”, you can select an alternative implementation:

```java
static void notifyWithFallback(Notifier preferred, Notifier fallback) {
    Notifier chosen = preferred != null ? preferred
                                        : java.util.Objects.requireNonNull(fallback);
    chosen.send("ready");
}
```

This approach still uses polymorphism normally: `chosen` has the interface type and holds an actual implementing object. There is no need to put special logic into a call through `null`.

In APIs where “do nothing” has a clear meaning, you can consider a **Null Object** implementation (a real object that performs an empty operation). A Null Object is a **valid instance** of the interface; it is completely different from the `null` value. Replacing `null` with a Null Object is only appropriate if skipping the operation is a sound policy.

## 7. `instanceof` and pattern matching do not match `null`

The `instanceof` operator is useful when you need to determine the actual type before a specialized operation:

```java
Notifier value = null;

if (value instanceof ConsoleNotifier console) {
    console.send("ok");
} else {
    System.out.println("Not a ConsoleNotifier instance");
}
```

This illustrative snippet uses **pattern matching for `instanceof`**, which is stable in Java 17. When `value` is `null`, the condition is `false`, the pattern variable `console` is not assigned for use in the `if` branch, and the program prints:

```text
Not a ConsoleNotifier instance
```

With `value = new ConsoleNotifier()`, the condition becomes `true`; `console` references that same object and calls `send("ok")`.

Several expressions to distinguish:

```java
Notifier value = null;

boolean noReference = (value == null);          // true
boolean hasNotifier = (value instanceof Notifier); // false
Notifier castValue = (Notifier) value;           // still null
```

Casting a `null` reference to an interface is valid and **does not create an object**. Therefore, `castValue.send("x")` still causes a `NullPointerException`. Casting only requests or checks how a reference value is viewed by type; it does not provide an instance when the value is `null`.

## 8. Common misconceptions with `equals`, `toString`, and method references

### Checking for null by calling a method on the variable itself

The following approach is unsafe:

```java
Notifier notifier = null;
// notifier.equals(null);  // Causes NullPointerException at runtime
// notifier.toString();    // Causes NullPointerException at runtime
```

To check for null, use `notifier == null` or `notifier != null`. If the goal is to compare two potentially null values, `java.util.Objects.equals(a, b)` can be useful, because this static method handles `null` according to its contract.

Example:

```java
String a = null;
System.out.println(java.util.Objects.equals(a, null)); // true
System.out.println("ok".equals(a));                    // false
```

On the second line, the receiver is the string literal `"ok"`, which is non-null, so the call is safe. Reversing it to `a.equals("ok")` will cause a `NullPointerException`.

### Object-bound method references and lambdas can differ in when they fail

Consider the interface with the `send(String)` method as in Section 3:

```java
Notifier missing = null;

// Method reference expression bound to a null receiver:
// java.util.function.Consumer<String> direct = missing::send;

// Lambda only attempts to call the receiver when executed:
// java.util.function.Consumer<String> delayed = text -> missing.send(text);
```

The `missing::send` line here is commented out to avoid halting the program: with a **bound instance method reference**, the method reference expression requires a receiver and will cause a `NullPointerException` **as soon as the expression is evaluated** if the receiver is `null`. With the lambda `text -> missing.send(text)`, creating the lambda does not call the method by itself; the error occurs **when the lambda is executed** (if `missing` is still `null` at that time).

The two forms look similar, yet they have different timing for using the receiver. When analyzing an NPE, identify **which expression** attempted to use the receiver, rather than looking only at the declared interface type.

## 9. Expression evaluation order: arguments can run before the NPE appears

A notable Java detail: in an instance method call, the receiver expression is evaluated, and then the argument expressions are evaluated in left-to-right order. If the receiver evaluates to `null`, the exception is usually detected **after the arguments have been evaluated**, right before executing the call.

Save the standalone example to **`ArgumentOrderDemo.java`**:

```java
interface Task {
    void execute(int number);
}

public class ArgumentOrderDemo {
    static int argument() {
        System.out.println("Evaluating argument");
        return 5;
    }

    public static void main(String[] args) {
        Task task = null;

        try {
            task.execute(argument());
        } catch (NullPointerException e) {
            System.out.println("NullPointerException");
        }
    }
}
```

Compile and run:

```bash
javac ArgumentOrderDemo.java
java ArgumentOrderDemo
```

Output:

```text
Evaluating argument
NullPointerException
```

`argument()` was called and printed its message, but **`Task.execute` was not executed**, because the target object did not exist. This matters if an argument expression has side effects, such as logging or mutating state.

Do not rely on exceptions as a control-flow mechanism to “protect” side effects. If null can occur, check or validate the receiver **before** preparing arguments that have significant cost or side effects.

## 10. When does `NullPointerException` occur and when does it not?

| Scenario | Compile time | Runtime |
| --- | --- | --- |
| `Notifier n = null;` | Valid | Value assignment only, no NPE |
| `Notifier n = new ConsoleNotifier();` | Valid | Creates a real object |
| `n.send("x")` when `n` holds an object | Valid | Dispatches to the appropriate implementation |
| `n.send("x")` when `n == null` | Valid | Throws `NullPointerException` |
| `n.ping()` when `n == null` | Valid if `default ping()` exists | Still throws `NullPointerException` |
| `n == null` | Valid | Returns `true` or `false` |
| `n instanceof Notifier` when `n == null` | Valid | Returns `false` |
| `(Notifier) null` | Valid | Result is `null`, no NPE yet |
| `new Notifier()` | Invalid | Does not run |
| `Notifier.category()` with `category()` static | Valid | Runs the static method via the interface name |
| `n.category()` with `category()` static in the interface | Invalid | Does not run |

If the program throws `NullPointerException` at `n.send("x")`, what you need to look for is **why `n` is null at the call site**. The compiler does not guarantee a valid object merely because the method is in the interface.

## 11. Designing APIs that accept or return interfaces to avoid null errors

An interface helps code reduce coupling to implementing classes, but by itself it does not guarantee that a value is always present. You should establish concrete contracts:

1. **Required inputs:** validate early using `Objects.requireNonNull`, guide callers to pass a valid object, and test the null case so the API fails clearly.
2. **Optional inputs:** document the meaning of null, check before calling, or provide a fallback value. Avoid silent skipping if a missing dependency is a configuration error.
3. **Potentially absent results:** you can return `null` if the contract clearly specifies it, or consider `Optional<Notifier>` for **return values** when it helps express an absent state. Avoid creating `Optional` just to hide an unclear design.
4. **Do not use `instanceof` as a mandatory null check:** `instanceof` returns false for null, yet it also carries the meaning of checking the actual type; if you are only asking whether an object is present, `!= null` is clearer.
5. **Do not catch NPE instead of validating data:** an NPE can originate from **any null dereference operation** inside a complex call, so catching too broadly can hide other bugs.
6. **Use static methods via the interface name:** `Notifier.category()` has a different mechanism from `notifier.send(...)`. One does not require an instance, while the other does.
7. **Specify valid states clearly in tests:** include at least a case passing a valid implementing class, a case passing null if allowed, and a case where null is rejected if the API requires a mandatory reference.

A maintainable design approach is to require mandatory dependencies right in the constructor of the object that uses them, rather than leaving an interface-typed field as null and waiting until a call occurs to discover the error. Example:

```java
import java.util.Objects;

final class NotificationService {
    private final Notifier notifier;

    NotificationService(Notifier notifier) {
        this.notifier = Objects.requireNonNull(notifier, "notifier");
    }

    void notifyUser() {
        notifier.send("welcome");
    }
}
```

The code above needs to be placed in the same environment where `Notifier` from Section 3 is declared. It ensures that `NotificationService`'s constructor **rejects null right at creation time**. After successful creation, and if the field is not altered by any unusual external mechanism, the service's methods can use `notifier` without repeated null checks.

## 12. Common mistakes when working with interface references

| Mistake or misconception | Why it is wrong | How to fix |
| --- | --- | --- |
| “An interface-typed variable has the `send` method, so it can be called even when null” | Compile-time type validity does not guarantee a target object exists | Check the contract and validate the reference before calling |
| “The interface has `default`, so Java will run it automatically for null” | `default` is still an instance method that needs a receiver | Only call through a valid object |
| “`null` is an object of the interface” | `null` is not an instance of any type | Use `== null`; do not attribute behavior or a runtime class to it |
| “Casting `(Notifier) null` will create a `Notifier`” | A cast does not create an instance | Use `new LớpTriểnKhai()` when an object is needed |
| “`instanceof Notifier` will be true if the variable is declared `Notifier`” | `instanceof` inspects the object at runtime; null gives false | Check based on the actual value and intent |
| “Catching NPE is the standard way to detect a missing notifier” | It can hide errors originating from another location | Validate `null` before dispatching or according to the API contract |
| “Accessing `static` of an interface requires a non-null variable” | Static members belong to the interface | Use the syntax `TênInterface.thànhViên` |
| “After `first = null`, every variable that used to point to the object also becomes null” | Variable assignment only changes one reference | Track each reference variable independently |
| “An NPE always occurs before evaluating arguments” | Instance calls have a defined evaluation order | Check the receiver before preparing arguments with side effects |

## 13. Self-check exercises

**Exercise 1 — predict the output.** With `Notifier` from Section 3:

```java
Notifier notifier = null;
System.out.println(notifier == null);
System.out.println(notifier instanceof Notifier);
System.out.println(Notifier.category());
```

What is the output? Why is there no NPE? **Answer:** Prints `true`, `false`, `notification` in order. No line calls an instance method through `notifier`.

**Exercise 2 — explain the error.**

```java
Notifier notifier = null;
notifier.ping();
```

Is this a compile-time error or a runtime error? Does anything change if `ping()` is a `default` method? **Answer:** The code compiles cleanly; at runtime it throws `NullPointerException`. `default` provides a default body for an **instance method**; it does not make null a valid receiver.

**Exercise 3 — preserve the right behavior.** Write a method `sendIfAvailable(Notifier notifier, String text)` according to the contract: if `notifier == null`, skip; if non-null, call `send(text)` exactly once. Then write `sendRequired(...)` to reject null using `Objects.requireNonNull`.

One solution:

```java
static void sendIfAvailable(Notifier notifier, String text) {
    if (notifier != null) {
        notifier.send(text);
    }
}

static void sendRequired(Notifier notifier, String text) {
    java.util.Objects.requireNonNull(notifier, "notifier").send(text);
}
```

These two methods are snippets to place **inside a class** that can use `Notifier`. Which version to choose depends on the contract; you cannot infer from the `Notifier` signature alone whether null is valid.

**Exercise 4 — polymorphism and reference changes.** Predict the output:

```java
Notifier one = new ConsoleNotifier();
Notifier two = one;
one = null;
two.send("A");
```

**Answer:** Prints `Console: A`. The two variables used to point to the same object, and only `one` was reassigned to `null`. `two` still holds a reference to `ConsoleNotifier`.

### Key takeaways

- An interface-typed variable can hold **an implementing object or `null`**.
- The interface type lets the compiler check methods; **polymorphism** selects the implementation from the actual object. With `null`, **there is no object to dispatch to**, so an instance call causes `NullPointerException`.
- `default` methods still require an instance; interface `static` fields and methods are used via the **interface name**.
- `null instanceof Interface` always evaluates to `false`; casting `null` does not create an object.
- Handle null according to the **API contract**: skip intentionally, use a fallback object, or reject early. Do not use `catch (NullPointerException)` as the default way to check for null.
