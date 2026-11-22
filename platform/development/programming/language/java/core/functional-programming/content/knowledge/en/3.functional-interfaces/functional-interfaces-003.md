# `default`, `static`, and `private` Methods Do Not Increase the Abstract Method Count

## 1. The Core Idea to Understand

A **functional interface** in Java is an interface that has **exactly one abstract method** according to the rules for determining the *single abstract method* (SAM). It can serve as the target type for lambda expressions and method references. When reading an interface with many method declarations, do not mechanically count lines of declarations: you must distinguish **abstract methods** from methods that already have a body.

Three groups often cause confusion:

- **`default`:** instance methods that already have a body, providing default behavior for objects implementing the interface.
- **`static`:** methods attached to the interface itself, with a body; called via the interface name, often used as factories or utilities.
- **`private` / `private static`:** internal helper methods with a body, only callable within the same interface; they support reusing logic without exposing public API.

**None of the three groups above create an additional abstract method.** An interface with one SAM plus multiple `default`, `static`, and `private` methods can still be marked `@FunctionalInterface`. Important point to remember: *not increasing the SAM count* does not mean these methods do not exist, have no behavior, or can be called the same way.

`default` and `static` methods in interfaces were introduced in Java 8; `private` instance and `private static` methods were introduced in Java 9. Examples in this lesson use **Java 17 or later**.

## 2. Which Methods Are Counted as Abstract?

An instance declaration without a body, such as `boolean test(String value);`, is an abstract method that must be provided by an implementing class (unless that class remains abstract). In a regular interface, an instance method without a conflicting modifier is implicitly `public abstract`.

~~~java
@FunctionalInterface
interface Check {
    boolean test(String value); // Single SAM
}
~~~

`Check` can be implemented using a lambda because there is only one abstract contract:

~~~java
Check hasContent = value -> value != null && !value.isBlank();
boolean ok = hasContent.test("Java"); // true
~~~

The two blocks above are **illustrative snippets placed in the same scope where `Check` is accessible**; the complete standalone Java program is in section 5.

### Counting More Accurately

Not every declaration ending with `;` is a separate SAM:

1. Ignore methods that have a body: `default`, `static`, and `private` are not abstract methods.
2. Declarations whose signatures match `public` methods of `java.lang.Object` (such as `equals(Object)`, `hashCode()`, `toString()`) **are not counted** when determining the SAM of a functional interface.
3. For inherited interfaces, you must examine the abstract methods *that actually remain* and their override-equivalent signature relationships, rather than merely adding up declarations from each parent interface.
4. `@FunctionalInterface` does not turn an interface into a functional one by itself; it asks the compiler to check the rules and report an error when they are not satisfied. You can omit the annotation and the interface is still functional if it meets the conditions.

An example with an additional `equals` declaration remains valid because `equals(Object)` is a public method of `Object`:

~~~java
@FunctionalInterface
interface Describer {
    String describe(String value);
    boolean equals(Object other); // Does not create a second SAM
}
~~~

Do not generalize this rule to any method that “looks like” an Object API: the signature and override semantics must match. On the other hand, you cannot declare `default String toString()` or `default boolean equals(Object)` to override a method of `Object` in an interface; Java forbids default methods from overriding non-`final` methods of `Object` under language rules.

## 3. Comparing Four Method Kinds in an Interface

| Kind | Has body? | Counted toward SAM? | How called / who uses it | Primary purpose |
| --- | --- | --- | --- | --- |
| `abstract` | No | **Yes**, subject to language SAM exceptions | Called on implementing object; lambda supplies implementation | Define the required contract |
| `default` | Yes | **No** | Called on implementing object; can be overridden | Add default behavior, coordinate instance methods |
| `static` | Yes | **No** | `InterfaceName.method(...)` | Factories, utilities tied to the contract |
| `private` | Yes | **No** | Only methods inside the same interface | Share instance logic, can call SAM on `this` |
| `private static` | Yes | **No** | Only methods inside the same interface | Internal utility logic needing no instance state |

Note: the `abstract` keyword does not have to be written explicitly in a `public` instance declaration of an interface. You cannot combine `abstract` with `default`, `static`, or `private` to create a “method that is both bodied and abstract”.

### 3.1. `default`: Built-In Behavior for Instances

~~~java
@FunctionalInterface
interface Validator {
    boolean valid(String text);

    default boolean validTrimmed(String text) {
        return valid(text == null ? "" : text.trim());
    }
}
~~~

`valid(String)` is the SAM. `validTrimmed(String)` **already has a body**, so it adds no abstract contract; it calls back into the SAM via `valid(...)`. A single lambda `Validator validator = s -> !s.isEmpty();` suffices to provide both behaviors. An implementing class can also override `validTrimmed` if desired.

Real-world use case: adding a convenience operation built on top of the core check without forcing every implementation to rewrite the same logic.

### 3.2. `static`: Factories or Shared Algorithms

~~~java
@FunctionalInterface
interface IntRule {
    boolean test(int number);

    static IntRule greaterThan(int boundary) {
        return value -> value > boundary;
    }
}
~~~

`IntRule.greaterThan(10)` creates an `IntRule`. The `greaterThan` method has a body and returns a lambda, not an additional SAM. **Interface `static` methods are not inherited as static methods of implementing classes or subinterfaces.** Therefore, call `IntRule.greaterThan(10)` instead of `SomeImplementation.greaterThan(10)`.

A `static` method does not use `this`; it is not an instance method that can be overridden. To create a check that depends on an object's instance data, use the SAM or an appropriate instance/default method.

### 3.3. `private`: Sharing Internal Implementation

~~~java
@FunctionalInterface
interface NormalizedRule {
    boolean test(String value);

    default boolean check(String value) {
        return test(normalize(value));
    }

    default String display(String value) {
        return check(value) ? "OK" : "NO";
    }

    private static String normalize(String value) {
        return value == null ? "" : value.trim();
    }
}
~~~

`normalize` is purely a helper inside `NormalizedRule`; it cannot be called from outside or overridden by implementing classes. If a helper needs to call the SAM or other instance methods directly, you can use a `private` instance method:

~~~java
private boolean evaluate(String normalizedValue) {
    return test(normalizedValue);
}
~~~

The `evaluate` snippet above is a **code fragment placed inside an interface that has a `test(String)` method**, not a standalone program. A private instance method can use instance behavior; a private static method should only use passed-in data or static members. Do not try to declare `private abstract`: that is an invalid modifier combination.

Private methods help avoid duplicating logic across multiple default methods while keeping the API surface small. This is an important difference from creating extra default methods just to share a helper function that should not be public.

## 4. Why Can Lambdas Still Be Used When There Are Many Methods?

A lambda does not implement all the methods visible in an interface: it provides an implementation for **a single abstract contract**. `default` behaviors already have bodies, `static` methods belong to the interface, and `private` methods only serve internal implementation.

For example, if an interface has the structure:

~~~text
TextRule
├─ test(String)                 // public abstract → 1 SAM
├─ testNormalized(String)       // default → 0 SAM
├─ explain(String)              // default → 0 SAM
├─ minLength(int)               // static → 0 SAM
├─ evaluate(String)             // private instance → 0 SAM
└─ normalize(String)            // private static → 0 SAM
Total abstract methods to implement: 1
~~~

An expression `value -> value != null && value.length() >= 3` is enough to implement `test`. Afterward, you can call `testNormalized` or `explain` on the created function object.

This exact mechanism enables a functional interface to offer a richer convenience API while maintaining compatibility with lambdas.

## 5. Complete Java 17 Example: SAM with `default`, `static`, and `private`

Create the file **`FunctionalInterfaceMethodsDemo.java`** with the following content:

~~~java
public class FunctionalInterfaceMethodsDemo {

    @FunctionalInterface
    interface TextRule {
        // Single abstract method (SAM).
        boolean test(String value);

        // Default #1: provides behavior on the instance.
        default boolean testNormalized(String value) {
            return evaluate(normalize(value));
        }

        // Default #2: reuses another default method.
        default String explain(String value) {
            return testNormalized(value) ? "PASS" : "FAIL";
        }

        // Private instance: calls the instance contract test(...).
        private boolean evaluate(String value) {
            return test(value);
        }

        // Private static: pure helper based on passed parameters.
        private static String normalize(String value) {
            return value == null ? "" : value.trim();
        }

        // Static factory: creates a SAM implementation.
        static TextRule minLength(int minimum) {
            if (minimum < 0) {
                throw new IllegalArgumentException("minimum < 0");
            }
            return value -> value != null && value.length() >= minimum;
        }
    }

    public static void main(String[] args) {
        TextRule atLeast3 = TextRule.minLength(3);
        TextRule onlyLetters = value ->
                value != null
                && !value.isEmpty()
                && value.codePoints().allMatch(Character::isLetter);

        System.out.println(atLeast3.explain("  Java  "));
        System.out.println(atLeast3.explain("  Go  "));
        System.out.println(onlyLetters.testNormalized("  Java "));
        System.out.println(TextRule.minLength(3).test("Go"));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 FunctionalInterfaceMethodsDemo.java
java FunctionalInterfaceMethodsDemo
~~~

**Exact output:**

~~~text
PASS
FAIL
true
false
~~~

Line-by-line explanation:

1. `"  Java  "` is normalized by `normalize` to `"Java"` (4 characters), meeting the minimum length of 3 → `PASS`.
2. `"  Go  "` is normalized to `"Go"` (2 characters), below the minimum length of 3 → `FAIL`.
3. The `onlyLetters` lambda checks Unicode code points using `codePoints()`, so `"Java"` consists only of letters → `true`. Using `codePoints` instead of `chars` is useful when handling Unicode characters outside the BMP.
4. Calling `test("Go")` directly does not normalize, and the length is still only 2 → `false`.

The compiler accepts `@FunctionalInterface` because the single abstract method is `test(String)`. The program both uses lambdas to implement the SAM and invokes the `static` factory and `default` methods, while `private` helpers are called internally within the interface. Methods with bodies do not cause the interface to lose its functional nature.

## 6. Inheritance Cases and Conflicts to Know

### 6.1. Inheriting a `default` Method Does Not Add a SAM

~~~java
interface HasLabel {
    default String label() {
        return "ready";
    }
}

@FunctionalInterface
interface LabeledTask extends HasLabel {
    void runTask();
}
~~~

`LabeledTask` still has only one abstract method, `runTask()`. An implementing class can use the inherited `label()` or override it. By contrast, `static` methods of `HasLabel` (if any) are not inherited as member methods of `LabeledTask`.

### 6.2. Two `default` Methods with the Same Signature Can Conflict

~~~java
interface First {
    default String name() { return "first"; }
}

interface Second {
    default String name() { return "second"; }
}

class Combined implements First, Second {
    @Override
    public String name() {
        return First.super.name() + "+" + Second.super.name();
    }
}
~~~

Because two independent interfaces provide two default versions of `name()`, `Combined` must resolve the conflict by overriding. In the example, calling `First.super.name()` and `Second.super.name()` explicitly selects the desired default implementations. **Default method conflicts are an inheritance behavior-resolution issue**, not something that automatically increases the abstract method count in each source interface.

In addition, a concrete instance method inherited from a class takes precedence over a default method with the same signature from an interface under Java's resolution rules.

### 6.3. A Subinterface Can Turn a `default` Method Back into `abstract`

An important distinction: **having a `default` method does not increase the SAM count**, yet a subinterface *can redeclare that method as abstract*; when it does, that method in the subinterface must be counted again as a contract requiring implementation.

~~~java
interface Parent {
    default void reset() {}
}

interface Child extends Parent {
    void reset();   // Re-abstracts the inherited behavior
    void process(); // Another abstract method
}
~~~

`Child` here has two abstract contracts (`reset` and `process`), so it is **not a functional interface**. If you add `@FunctionalInterface` to `Child`, the compiler reports an error. Do not conclude “once a default method, never counted”.

### 6.4. Equivalent Signatures and Object

If two parent interfaces declare the same abstract method with override-equivalent signatures, the effective SAM count can still be **one** after combining. Conversely, two independent abstract methods with different signatures make the interface no longer functional. Equivalent signatures require checking valid return types and Java's override rules, not guessing solely from the method name.

`public` methods of `Object` such as `equals(Object)` still follow the exception described in section 2; they are not treated as an additional SAM just because they are redeclared in an interface.

## 7. Common Compile Errors and Misunderstandings

| Misunderstanding | Result or cause | How to fix |
| --- | --- | --- |
| Counting every method declaration line as a SAM | Interfaces with default/static/private methods are misjudged as non-functional | Count only effective abstract contracts |
| Assuming `static` requires an implementing class | Static methods with bodies belong to the interface | Call via `InterfaceName.method()` |
| Calling `Impl.minLength(...)` instead of `TextRule.minLength(...)` | Interface static methods are not inherited by implementing classes | Use the interface name that declares the method |
| Calling a `private` method from outside the interface | Inaccessible due to visibility | Use an appropriate public/default API |
| Writing `private abstract void help();` | Private abstract methods are invalid | Choose a public abstract SAM or a private method with a body |
| Writing `default void f();` | Default methods must have a body | Provide a body or declare it abstract |
| Declaring two independent abstract methods and adding `@FunctionalInterface` | Compiler reports the interface is invalid with the annotation | Redesign the contract into one SAM, splitting interfaces if needed |
| Two parent interfaces have default methods with the same signature | Implementing class hits an inherited method conflict | Override and choose the concrete behavior |
| Thinking `@FunctionalInterface` is required to use lambdas | The annotation is only a compile-time check | Lambdas can be used whenever the interface satisfies the SAM rules |
| Trying to declare a default method overriding `Object`'s `equals`/`toString` | Java forbids default methods from overriding them in this way | Let implementations handle it or use a different API name |

### Intentional Error Example for Self-Diagnosis

The block below **does not compile** because it has two independent abstract methods; it is only for error analysis:

~~~java
@FunctionalInterface
interface InvalidRule {
    boolean test(String value);
    int score(String value); // Second SAM: invalid

    default String label() {
        return "invalid";
    }

    static InvalidRule example() {
        throw new UnsupportedOperationException();
    }
}
~~~

`label` and `example` do not increase the SAM count. The two methods `test` and `score` are the cause. To fix it, identify the primary responsibility of the interface: for example, keep only `test` abstract and compute `score` based on `test` via a default method *if that makes semantic sense*, or split the responsibilities into two interfaces. Do not arbitrarily merge functionality just to get the annotation past the compiler.

## 8. Process for Checking Whether an Interface Is Functional

When encountering a new interface or modifying an existing API, follow these steps:

1. **Read abstract methods:** instance methods without bodies in the interface and inherited abstract methods that remain in effect.
2. **Exclude non-abstract methods:** `default`, `static`, `private`/`private static`; also account for inherited default methods.
3. **Apply Object exceptions and override-equivalent signatures:** do not double-count contracts merged by Java, and do not count declarations matching `public` methods of `Object`.
4. **Check inheritance:** is a default method re-abstracted, are there two different abstract methods, or is there an unresolved default conflict?
5. **Add `@FunctionalInterface` if the intent is a SAM API:** so the compiler protects the constraint as the code evolves.
6. **Try assigning a lambda or method reference:** the lambda must match the SAM's parameter count, parameter types, and return type; checked exceptions must also be compatible with the SAM contract.

If the result is exactly one valid abstract method, the interface can serve as a lambda target type. A lambda essentially only describes how to implement the SAM; default methods provide reusable behavior, and static/private methods organize the API and implementation.

## 9. Self-Check Exercises

**Exercise 1 — Count SAMs.** Consider:

~~~java
@FunctionalInterface
interface Formatter {
    String format(String input);

    default String formatOrEmpty(String input) {
        return input == null ? "" : format(input);
    }

    static Formatter identity() {
        return value -> value;
    }

    private static boolean missing(String input) {
        return input == null;
    }
}
~~~

How many abstract methods are there? **One: `format`.** The remaining methods have bodies. Note that `missing`, even though uncalled, is still a valid private static method (the compiler or tools may warn about unused methods, but it does not change the SAM count).

**Exercise 2 — Write a lambda.** Create `Formatter formatter = s -> s.trim().toUpperCase();`, and test `formatter.formatOrEmpty(" java ")` and the `null` case. The results are `"JAVA"` and `""`, respectively; the default operation avoids passing `null` into the lambda.

**Exercise 3 — Add a default method.** Add `default int lengthOf(String input) { return formatOrEmpty(input).length(); }` to `Formatter`. Explain why the original lambda remains valid: the new method has a body, so it does not introduce a second abstract contract.

**Exercise 4 — Find the error.** Change `private static boolean missing(...)` to `private abstract boolean missing(...);`. Predict the compile error and state the relevant modifier rule. Then try adding `int size(String value);` to see the effect of `@FunctionalInterface` when a second SAM actually appears.

**Exercise 5 — Inheritance.** Create two interfaces with the same default method and a class that implements both. Write an override to resolve the conflict; distinguish the default inheritance issue from SAM counting.

## 10. Takeaways

- A functional interface has **a single abstract contract** under the SAM rules, even though it can expose many other methods.
- `default` (Java 8+) has a body and can be overridden by implementing classes; `static` (Java 8+) has a body, is called via the interface name, and is not inherited as an instance API.
- `private`/`private static` (Java 9+) have bodies and only support implementation inside the interface itself.
- Do not add the methods above to the SAM count. You must also consider the `Object` exception, equivalent signatures, inheritance, and whether a default method is redeclared as abstract in a subinterface.
- `@FunctionalInterface` is a tool that enforces the rule at compile time. When maintaining a lambda-friendly API, prefer adding sensible behavior via `default`/`static`/`private` instead of accidentally adding a second abstract method.

**Official reference documentation:** Javadoc for `java.lang.FunctionalInterface`, Java Language Specification sections *Functional Interfaces* (JLS `9.8) and *Interface Method Declarations* (JLS `9.4), and Javadoc for `java.util.function`.