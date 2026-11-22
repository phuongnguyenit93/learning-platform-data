# Designing Easy-to-Use Overloaded Method Sets in Java

**Method overloading** allows multiple methods to share the same name while having different parameter lists. When designing an API, the goal is not to create as many overloads as possible, but to help users **predict how to call them, understand their meaning accurately, avoid mistakenly passing wrong arguments, and get consistent behavior**. A good overload set provides a few convenient ways to invoke **the same operation**; a poor overload set forces callers to guess which method the compiler will pick or leaves them unsure how `null`, integers, arrays, and default parameters are handled.

This article focuses on **the mindset for designing overloaded method sets** in Core Java, combining API principles, runnable Java 17+ examples, design pitfalls, and a verification process before publishing an API.

## 1. Distinguishing “Valid Overloads” from “Easy-to-Use Overloads”

At a basic level, the following declarations have **different signatures**:

~~~java
void send(String message) { }
void send(String message, int retries) { }
void send(String message, int retries, long delayMillis) { }
~~~

They differ in the number and types of parameters, so they can coexist in the same class. However, looking at the signatures alone does not tell you whether `retries` can be negative, whether `delayMillis` is in milliseconds or seconds, or how many retries `send(message)` performs by default.

That is the gap between **syntactic validity** and **API usability**:

| Criterion | Merely Needs to Compile | Easy-to-Use Design Also Requires |
| --- | --- | --- |
| Signature | Name and parameter type list differ | Signatures express meaning clearly |
| Parameters | The compiler accepts the passed types | Order, units, and bounds are predictable |
| Defaults | Overloads with fewer parameters can be called | Default values are defined consistently |
| Result | Valid return type | Same result concept for the same operation |
| Errors | Can throw exceptions | Validation rules and errors are unsurprising |
| Extensibility | Adding a new signature compiles | Does not make existing calls ambiguous upon recompilation |

**Foundational principle:** only share the same name when the methods can be naturally explained as **different ways of calling the same action**.

## 2. Identify the “Core Operation” Before Creating Overloads

Suppose you need an API that generates a greeting. Reasonable variants:

- `greet(name)`: greets using the default phrase and repeats once;
- `greet(name, salutation)`: the caller chooses the salutation, still repeating once;
- `greet(name, salutation, repetitions)`: the caller chooses both the salutation and the number of repetitions.

All three calls return **a greeting string**. They share the same meaning and differ in **their level of configuration**. This is a natural case for overloading.

Conversely, if `greet(name, int)` sends a greeting via email while `greet(name, String)` deletes the greeting history, sharing the name `greet` fails to reflect the major difference in behavior. You should name them `sendGreeting`, `deleteGreetingHistory`, or equivalent domain names.

A helpful question to ask is: **“If you hide the parameter lists, are all methods with the same name answering one question or performing one kind of action?”** If not, overloading is usually not the right tool.

## 3. Use a Single Shared Implementation Method and Have Shorter Overloads Delegate

A reliable design approach is to choose **one core method** containing input validation and the main logic; the convenience overloads call it with default values. As a result:

1. Validation rules and result formatting live in **one place**.
2. Fixing a bug in the algorithm does not require updating three copies.
3. Default values are stated explicitly and are easy to verify.
4. Unit tests can be written for the delegation paths and important boundaries.
5. Users do not have to pass default values repeatedly themselves.

Call diagram:

~~~text
greet(name)
    |
    +--> greet(name, "Xin chào")
               |
               +--> greet(name, salutation, 1)
                               |
                               +--> validate
                               +--> create and return string

greet(name, salutation, repetitions)
    |
    +--> validate
    +--> create and return string
~~~

The arrows represent **delegation calls** in code, not class inheritance relationships. This is a simple way to organize APIs with few options; when the number of options grows too large, consider a configuration object or a builder.

## 4. Complete Example: Designing GreetingApi

Create the file **`GreetingApi.java`** in your working directory. All `greet` overloads are `public static`, return `String`, and do not write to stdout; only `main` prints the demo output.

~~~java
import java.util.StringJoiner;

public final class GreetingApi {
    private GreetingApi() {
        // Utility class: no need to create an instance.
    }

    public static String greet(String name) {
        return greet(name, "Xin chào");
    }

    public static String greet(String name, String salutation) {
        return greet(name, salutation, 1);
    }

    public static String greet(
            String name, String salutation, int repetitions) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (salutation == null || salutation.isBlank()) {
            throw new IllegalArgumentException("Lời chào không hợp lệ");
        }
        if (repetitions < 1 || repetitions > 5) {
            throw new IllegalArgumentException(
                    "Số lần phải từ 1 đến 5");
        }

        String sentence = salutation + ", " + name + "!";
        StringJoiner joiner = new StringJoiner(" | ");
        for (int i = 0; i < repetitions; i++) {
            joiner.add(sentence);
        }
        return joiner.toString();
    }

    public static void main(String[] args) {
        System.out.println(greet("An"));
        System.out.println(greet("Bình", "Chào"));
        System.out.println(greet("Mai", "Hello", 3));

        try {
            System.out.println(greet("An", "Hello", 0));
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 GreetingApi.java
java GreetingApi
~~~

**Exact stdout:**

~~~text
Xin chào, An!
Chào, Bình!
Hello, Mai! | Hello, Mai! | Hello, Mai!
Lỗi: Số lần phải từ 1 đến 5
~~~

### Why Is This Example Easy to Use?

| Call | Caller Intent | Execution Path |
| --- | --- | --- |
| `greet("An")` | Simplest greeting | Automatically uses `"Xin chào"` and `1` repetition |
| `greet("Bình", "Chào")` | Choose salutation | Automatically uses `1` repetition |
| `greet("Mai", "Hello", 3)` | Full configuration | Goes directly to the core method |
| `greet("An", "Hello", 0)` | Invalid repetition count | Same validation rules, throws an exception |

The overloads do not print content themselves or modify external data, so the caller decides whether to display it on the console, in a UI, or save the result. The same validation rules apply whether you call the short or long version.

**Contract scope:** the name and salutation must be non-`null` and must not consist solely of whitespace; `repetitions` is in the range `1..5`. The example **preserves leading/trailing whitespace** on non-empty strings; it does not automatically call `trim()`. This is a decision that can be changed depending on requirements, but it must remain consistent across overloads.

## 5. Choosing “Short” Overloads Based on Clear Default Values

An overload with fewer parameters is only useful if the omitted values have **sensible, stable, and explainable defaults**.

Example:

~~~java
static String greet(String name) {
    return greet(name, "Xin chào");
}
~~~

The caller chooses `greet("An")` to apply the default greeting, rather than arbitrarily omitting a required parameter. Meanwhile, the two-parameter overload defines the default repetition count as one:

~~~java
static String greet(String name, String salutation) {
    return greet(name, salutation, 1);
}
~~~

The two snippets above extract the idea from the complete program. You should not scatter different default values across multiple overloads, causing `greet(name)` and `greet(name, greeting)` to have inconsistent repetition rules.

### When Should You Avoid Guessing a Default?

If an API requires a **currency**, **time zone**, **time unit**, or **access permission**, a wrong default can cause serious bugs. For example, `schedule(10)` does not make it clear whether `10` means seconds or minutes. Prefer a type that carries meaning:

~~~java
void schedule(java.time.Duration delay) {
    // ...
}
~~~

This is a **signature illustration** without a business-logic body; the `Duration` type clarifies the meaning of a time duration better than an `int` without units. You do not always have to add a `schedule(int seconds)` overload, because it could cause users to misunderstand the unit.

## 6. Consistency Rules for Results, Errors, and Side Effects

Overloads sharing the same name should maintain a **predictable contract**:

- **Inputs:** the same parameter concept should be validated against the same standard. In `greet`, every call path rejects an empty name.
- **Outputs:** the same result meaning. All `greet` overloads return **the greeting text**; none unexpectedly returns a character count.
- **Side effects:** avoid cases where the one-argument version only performs a calculation while the two-argument version automatically writes to a file or sends an email without the method name indicating it.
- **Exceptions:** equivalent invalid cases should be reported consistently; do not silently ignore them in one place while throwing an error in another without deliberate intent.
- **Empty values and `null`:** clearly specify whether they are accepted, interpreted as defaults, or rejected.

This does not mean every overload **must** have the same return type: Java allows different return types as long as the parameter lists already differ in signature. However, **from an API design standpoint**, changing the result type and meaning across overloads with similar purposes usually makes the API harder to use.

Questionable example:

~~~java
int find(String key) { return 0; }
String find(String key, boolean verbose) { return ""; }
~~~

The two signatures differ, yet adding `verbose` completely changes both the return type and the meaning of the result. This situation suggests the API is merging two distinct purposes and should have clearer names or a consistent result type. This is an **illustrative snippet**, not a complete search feature.

## 7. Overloads Cannot Be Distinguished by Return Type Alone

The following two declarations **cannot coexist in the same class**:

~~~java
int size() {
    return 1;
}

long size() {
    return 1L;
}
~~~

Both share the same `size()` signature. Java does not allow overload selection based on the receiving variable's type, such as `long result = size();`.

Changes that **do not create a new signature**:

| Change | Example | Creates a New Overload? |
| --- | --- | --- |
| Changing only the return type | `int f(int)` to `long f(int)` | No |
| Changing only parameter names | `f(int amount)` to `f(int value)` | No |
| Changing only `throws` | `throws IOException` to `throws SQLException` | No |
| Changing only the access modifier | `private f(int)` to `public f(int)` | No |
| Only adding/removing `static` | `static f(int)` and `f(int)` | No |
| Changing the number of parameters | `f(int)` to `f(int,int)` | Yes |
| Changing parameter types | `f(int)` to `f(long)` | Yes |
| Changing parameter type order | `f(int,long)` to `f(long,int)` | Yes, but calls can be ambiguous |

For generic methods, Java also has rules regarding generic parameter types, *subsignature*, and *erasure*, so the table is a quick reference for basic cases; it does not replace the full Java Language Specification.

## 8. Avoid Overloads That Make `null` Ambiguous

An easy-to-spot design mistake is providing multiple overloads that accept **unrelated reference types** in the same position:

~~~java
static void deliver(String text, java.time.Duration delay) { }
static void deliver(String text, java.util.Locale locale) { }
~~~

The two declarations **have different signatures and can coexist**. However:

~~~java
deliver("Xin chào", null); // ERROR: ambiguous call
~~~

`null` is compatible with both `Duration` and `Locale`; neither type is a subtype of the other. The compiler cannot choose a single method.

You can cast it:

~~~java
deliver("Xin chào", (java.time.Duration) null);
~~~

However, casting only helps the compiler make a choice; **it does not guarantee that `null` is a valid argument under the contract**. A public API that forces callers to cast in order to call it with `null` is usually a sign that the design needs revisiting.

### Preferred Solution: Distinct Names for Distinct Meanings

Instead of using `deliver(text, Duration)` and `deliver(text, Locale)` to perform two different kinds of behavior, consider:

~~~java
void deliverAfter(String text, java.time.Duration delay) { }
void deliverLocalized(String text, java.util.Locale locale) { }
~~~

These are only **illustrative declarations**; the names better clarify the role of the second parameter and eliminate the overload conflict here.

If you have `show(Object)` and `show(String)` overloads, calling `show(null)` can select `show(String)` because `String` is more specific than `Object`. However, being able to pick an overload **does not mean** that choice matches the user's intent. When an API is expected to handle `null`, you should define explicit rules or avoid misleading overload groups.

## 9. Choose Parameter Types to Limit Unexpected Conversions

Java has a multi-phase overload selection mechanism. In common cases, **primitive widening** is considered in the strict phase before boxing/unboxing is needed and before variable-arity varargs calls.

Create the file **`OverloadChoiceDemo.java`**:

~~~java
public class OverloadChoiceDemo {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    static String choose(int... values) {
        return "varargs: " + values.length;
    }

    public static void main(String[] args) {
        System.out.println(choose(5));
        System.out.println(choose(Integer.valueOf(5)));
        System.out.println(choose());
        System.out.println(choose(5, 6));
    }
}
~~~

Compile and run:

~~~bash
javac OverloadChoiceDemo.java
java OverloadChoiceDemo
~~~

Stdout:

~~~text
long
Integer
varargs: 0
varargs: 2
~~~

`choose(5)` selects `long` because `5` has type `int`, which can be widened to `long` in the strict phase before boxing to `Integer` is needed. `choose(Integer.valueOf(5))` selects `Integer` because the argument type matches directly. `choose()` and `choose(5, 6)` require varargs.

**Design lesson:** avoid creating `int`, `long`, `Integer`, and `Object...` overloads just to “accept everything” if the behavior does not actually need to distinguish those types. Users may mispredict which overload gets selected, and adding an overload in a library update can change resolution outcomes when client code is recompiled.

If an API requires a clear unit or value domain, choose **one primary parameter type** and add conversion overloads only when the usability benefit is large enough.

## 10. Varargs Are Convenient but Increase Ambiguity Risk

Varargs allow calls with zero, one, or multiple elements, such as `log("A", "B")` for `log(String... messages)`. However, when combined with regular overloads, consider the following cases:

~~~java
static void log(String message) { }
static void log(String... messages) { }
~~~

These two declarations are valid: their signatures are `log(String)` and `log(String[])`, respectively. For `log("A")`, the `log(String)` version is selected in the fixed-arity phase, before the compiler needs to pack a single element into an array for varargs.

However, `log(null)` can be **ambiguous**: a `null` argument matches both `String` and `String[]`, and neither type is a subtype of the other. You must clarify intent with `log((String) null)` or `log((String[]) null)`, though a better approach is to design an API that does not force callers into unpredictable situations.

Two varargs methods with different element types can also cause an error when called with no arguments:

~~~java
static void collect(String... values) { }
static void collect(Integer... values) { }

// collect(); // ERROR: cannot select a unique overload
~~~

**Varargs and arrays share the same parameter type in the signature:** `print(String... xs)` cannot coexist with `print(String[] xs)` in the same class; both have the equivalent signature `print(String[])`. Therefore, you cannot create a “separate overload for array calls” simply by changing `...` to `[]`.

**Recommendation:** include varargs in an API when the benefit of passing multiple discrete values is clear, test empty calls, `null` calls, and array calls, and avoid unrelated varargs overload groups.

## 11. Parameter Names and Order Must Prevent Confusion

Consider two valid signatures:

~~~java
void schedule(String task, int priority) { }
void schedule(int priority, String task) { }
~~~

Although the two overloads have different parameter type orders, offering both calling conventions rarely brings a clear benefit. It forces users to remember two conventions at the same time.

A more dangerous case:

~~~java
void copy(String source, String destination) { }
~~~

A call like `copy(destination, source)` still **compiles** because both arguments are `String`. You cannot solve this by adding an overload that only swaps **parameter variable names**, because the signature remains `copy(String,String)`.

To make the API easy to use:

- Order parameters predictably—for example, “source, destination”—and apply that order consistently across all related APIs.
- When two values share the same type but play distinct critical roles, consider dedicated domain types such as `SourcePath` and `DestinationPath`, or a request object.
- Use descriptive parameter names in declarations and Javadoc; even though they are not part of the signature, they improve code readability and IDE assistance.
- Avoid overloads that merely reorder parameters without adding genuinely useful capability.

Another bad smell is low-context `boolean` parameters: `send(message, true, false)` leaves readers guessing what `true` stands for. Methods named `sendQuietly`, `sendWithReceipt`, or a configuration object may be a better fit depending on the domain.

## 12. Generics: Avoid Overloads That Clash After Type Erasure

Java does not allow overloading based solely on **generic type arguments** when erasure causes the two signatures to collide:

~~~java
void save(java.util.List<String> names) { }
void save(java.util.List<Integer> numbers) { }
~~~

This is an **intentionally non-compiling example** when both declarations reside in the same class; they cause a *name clash* because both parameter types erase to `List`.

One solution, when the behavior is identical, is a generic method:

~~~java
static <T> int count(java.util.List<T> items) {
    return items.size();
}
~~~

This is an **in-class illustrative snippet** without `main`. The same `count` works with a list containing `String`, `Integer`, or any other type without needing element-specific overloads. You can use `List<?>` if you only need to inspect elements without depending on type `T`.

If the behavior of `saveNames` and `saveScores` is genuinely different, choosing two descriptive names is better than forcing an inappropriate overload. You can also use dedicated domain wrapper types to distinguish **input objects**, though avoid inventing new types solely to work around the compiler when two operations fundamentally deserve different names.

## 13. Constructor Overloading: Same Principles, but Avoid Boolean Traps

Constructors can also be overloaded, and they can delegate using `this(...)`. Example:

~~~java
class RetryPolicy {
    private final int attempts;
    private final long delayMillis;

    RetryPolicy() {
        this(3, 1000L);
    }

    RetryPolicy(int attempts) {
        this(attempts, 1000L);
    }

    RetryPolicy(int attempts, long delayMillis) {
        if (attempts < 1 || delayMillis < 0) {
            throw new IllegalArgumentException("Cấu hình không hợp lệ");
        }
        this.attempts = attempts;
        this.delayMillis = delayMillis;
    }
}
~~~

This is an **illustrative class definition** without `main`. In Java 17, a `this(...)` call in a constructor must be **the first statement**. Every path that creates an instance passes through the two-parameter constructor and applies the same validation.

This design is easy to use because the defaults are clear: three attempts and a 1000 ms delay. However, callers may not know what unit `1000L` represents when looking solely at `new RetryPolicy(3, 1000L)`. For new APIs, the `Duration` type and the parameter name `delay` usually convey the meaning better:

~~~java
RetryPolicy(int attempts, java.time.Duration delay) {
    // Illustrative declaration; validate that delay is non-null and non-negative.
}
~~~

**This illustrative constructor cannot be placed as-is in the `RetryPolicy` class above without writing a valid body**; it only suggests an alternative API design.

A constructor with too many overloads is often a sign that the object has many independent configuration options; consider a factory method or a builder.

## 14. When Should You Replace Overloads with a Factory Method or Builder?

If there are many independent optional parameters such as format, locale, path, timeout, retries, and log level, adding overloads for every combination can cause a “signature explosion”:

~~~text
send(message)
send(message, retryCount)
send(message, timeout)
send(message, locale)
send(message, retryCount, timeout)
send(message, retryCount, locale)
send(message, timeout, locale)
send(message, retryCount, timeout, locale)
...
~~~

This is a diagram of possible configurations, **not a verified set of Java signatures**. Some combinations may collide in types or be ambiguous; the number of combinations grows rapidly with the number of options.

**Selection guidelines:**

| Situation | Usually Appropriate Design |
| --- | --- |
| 2–3 ways to provide inputs for the same operation, with obvious defaults | Overload |
| Fundamentally different behavior | Different method names |
| Many independent options | Configuration object, builder |
| Constructor with unclear parameter semantics | Clearly named static factory method |
| Multiple parameters of the same primitive/`String` type easily swapped | Domain value type or request object |
| Overloads causing ambiguous `null`/lambda calls | Differently named APIs or clearer argument types |

A conceptual example of using a builder:

~~~java
// Call illustration, not a complete program.
Request request = Request.builder()
        .message("Xin chào")
        .retryCount(3)
        .timeout(java.time.Duration.ofSeconds(5))
        .build();
sender.send(request);
~~~

A builder comes with the cost of extra types and code, so you should not force a builder onto every API that only has one simple option. The goal is to match complexity **to the number of configuration dimensions**, rather than following a rigid template.

## 15. Overload Resolution Depends on Static Types, Not the Runtime Class of Arguments

A common misconception is that Java always selects the overload matching the **actual runtime type of the object**. With overloading, the compiler chooses the signature based on the type information available at the call site.

Create the standalone file **`StaticTypeOverloadDemo.java`**:

~~~java
public class StaticTypeOverloadDemo {
    static String describe(Object value) {
        return "Object";
    }

    static String describe(String value) {
        return "String";
    }

    public static void main(String[] args) {
        Object first = "An";
        String second = "An";

        System.out.println(describe(first));
        System.out.println(describe(second));
        System.out.println(describe((String) first));
    }
}
~~~

Compile/run:

~~~bash
javac StaticTypeOverloadDemo.java
java StaticTypeOverloadDemo
~~~

Stdout:

~~~text
Object
String
String
~~~

Although `first` actually refers to a `String`, its **declared type** is `Object`. Thus, `describe(first)` selects the overload taking `Object`. Explicitly casting to `String` in `describe((String) first)` changes the expression type at the call site and causes the `String` overload to be selected.

Do not confuse this with **overriding**: after the compiler selects the **signature** of an instance method, the overridden implementation on the receiver's runtime class can still be dynamically dispatched. Overloading and overriding are two distinct mechanisms; API design should avoid relying on confusion between them.

## 16. Adding Overloads Can Break Compatibility on Recompilation

Suppose the initial version of an API only has:

~~~java
static String show(Object value) {
    return "Object";
}
~~~

A user writes `show("hello")` and the compiler selects `show(Object)`. Later, the library adds:

~~~java
static String show(String value) {
    return "String";
}
~~~

When client code is **recompiled**, the `show("hello")` call can select the more specific `show(String)`, changing behavior even though the caller **did not modify its source code**. This is a **source/recompilation-level** compatibility issue.

Another risk:

~~~java
static void send(String value) { }
static void send(Integer value) { }
~~~

If previously only `send(String)` existed, `send(null)` could compile and select `String`. After adding `send(Integer)`, the existing call becomes **ambiguous upon recompilation**.

These examples are illustrative declarations, not complete programs. Therefore, before extending a public API, check at least:

- Existing calls using integer literals and boxing/widening;
- `null` calls and zero-argument varargs calls;
- Types with inheritance relationships such as `Object` and `String`;
- Generic methods, lambdas, or method references if the API uses them;
- Critical client programs after **recompilation**.

**Note:** binary compatibility of existing bytecode and resolution outcomes upon recompilation **are not the same issue**. Adding an overload may leave previously compiled calls unchanged, yet change the selection when compiling new source code.

## 17. Evaluate “Ease of Use” with Call-Site Examples, Not Just Declarations

Before finalizing a design, try writing code from the **API user's side**:

~~~java
GreetingApi.greet("An");
GreetingApi.greet("Mai", "Hello");
GreetingApi.greet("Mai", "Hello", 3);
~~~

These three lines show clear intent, but you should examine further:

- Can callers infer the **default salutation** and **repetition bounds** from the names/Javadoc or autocomplete?
- Do the overloads always return the same kind of information?
- If a parameter is `null`, does the caller get a clear error or does the compiler report an ambiguity?
- Could any new overload make `greet("An")` select a different target after a library update?
- Can you read the name and parameters **without needing to guess the actual type** of a variable?
- If a short overload uses default values, does it **delegate to the same logic**?
- Has every default value and measurement unit been documented?

Do not test only “clean” calls. Try creating misleading calls such as `f(null)`, `f()`, `f(0)`, `f(1,2)`, empty arrays, wrapper types, and reference variables with a broader static type.

## 18. Testing an Overload Set with a Small Matrix

A good test suite needs to verify **the right version is selected** and **the result/contract is correct**. For `GreetingApi`, the core test cases are:

| Call | Expected Result or Error |
| --- | --- |
| `greet("An")` | `"Xin chào, An!"` |
| `greet("An", "Hi")` | `"Hi, An!"` |
| `greet("An", "Hi", 2)` | `"Hi, An! | Hi, An!"` |
| `greet("An", "Hi", 1)` | Same result as the two-parameter overload |
| `greet("An", "Hi", 5)` | Exactly 5 greetings |
| `greet("An", "Hi", 0)` | `IllegalArgumentException` |
| `greet("An", "Hi", 6)` | `IllegalArgumentException` |
| `greet(null)` | `IllegalArgumentException` |
| `greet("   ")` | `IllegalArgumentException` |
| `greet("An", null)` | `IllegalArgumentException` |
| `greet("An", "")` | `IllegalArgumentException` |

You do not need to run every case with `System.out.println` in the main example; in a real project, you can use JUnit and assertions that compare values or expect exceptions. When an overload only forwards, verify that the result of the short call **equals the long call with the published defaults**.

For compiler-affected overloads, add **compilation pass/fail** tests or small files run with `javac`—for example, whether an ambiguous `collect()` call is actually rejected. You cannot completely replace this kind of compile-time verification with runtime unit tests.

## 19. Designs to Avoid and How to Improve Them

| Problematic Design | Why It Is Hard to Use | Improvement Direction |
| --- | --- | --- |
| `send(String)` and `send(String,boolean,boolean)` | Meaning of the two flags is unclear | Mode-revealing names, enum, or options |
| `parse(String)` returns an object, `parse(String,int)` both parses and writes to DB | Same name but unexpected differing side effects | Separate parsing and persistence |
| `read(String path)`, `read(Path path)` with completely different error handling | Hard for users to predict | Use the same contract; overloads only change input representation |
| `set(int,long)` and `set(long,int)` | `set(1,2)` can be ambiguous | Consistent parameter structure, clear domain types |
| `log(String)`, `log(String...)` without considering `null` | `log(null)` can be ambiguous | Redesign overloads or remove redundant forms |
| `process(List<String>)`, `process(List<Integer>)` | Type erasure causes a name clash | Generic method, different names, or different input types |
| 8–16 constructors differing only in option sets | Callers struggle to remember order and defaults | Builder/options/factory |
| Multiple overloads copying the full algorithm | Bug fixes miss a branch, behavior diverges | One core implementation and delegating overloads |
| Adding overloads without testing old code | Changes selected overload on recompile | Check source compatibility |
| Unclear unit for `int delay` | Misuse of seconds vs. milliseconds | `Duration` or unit-explicit parameter name/type |

The best improvement is not necessarily **adding more overloads**. Sometimes the solution is **removing a redundant overload**, choosing a new name, or creating a well-designed request object.

## 20. Practice Exercises

**Exercise 1 — Overload design.** An API that computes product labels needs `label(code)`, `label(code,locale)`, and `label(code,locale,style)`. Indicate which overload should be the core method, how the other overloads should forward, and what default values should be published.

**Exercise 2 — Identifying duplicate signatures.** Can `int count(String text)` and `long count(String value)` be declared at the same time? Why do changing variable names or the return type not create a new signature?

**Exercise 3 — Null ambiguity.** Given `send(String,Duration)` and `send(String,Locale)`, is `send("Hi",null)` valid? Propose a design that eliminates confusion for the caller.

**Exercise 4 — Type conversions.** In `OverloadChoiceDemo`, why does `choose(5)` select `long` instead of `Integer` or varargs? What happens with `choose(Integer.valueOf(5))`?

**Exercise 5 — Varargs.** If you have `log(String)` and `log(String...)`, which version does `log("A")` select? What risk does `log(null)` carry?

**Exercise 6 — Optional parameters.** A method has six independent configuration options. Should you create overloads for every combination? When is a request object or builder easier to use?

**Exercise 7 — Static types.** Given `describe(Object)`, `describe(String)`, and a variable `Object x = "hello";`, why does `describe(x)` not automatically select `describe(String)`?

**Exercise 8 — API compatibility.** Why can adding `show(String)` to an API that already has `show(Object)` change the behavior of `show("x")` when a client application is recompiled?

**Reference answers:**

1. Use the three-parameter version as the core method, with the two shorter versions forwarding with default `locale` and `style` chosen according to business requirements; avoid assuming a default locale when the application needs deterministic results.
2. No; both are `count(String)`, and return types and parameter names do not create signature differences.
3. No; both `Duration` and `Locale` accept `null`, and neither is a more specific choice. Use names like `sendAfter`/`sendLocalized` or an appropriate request object.
4. Primitive widening from `int` to `long` is considered before boxing and varargs calls; an `Integer` argument selects the matching `Integer` overload.
5. `log("A")` selects `log(String)`; `log(null)` is ambiguous between `String` and `String[]`.
6. Usually no: too many combinations create a confusing API. A builder/options object enables named configuration and centralized validation.
7. The compiler uses the variable's static type `Object` to resolve the overload; it does not rely on the current object being a `String`.
8. Upon recompilation, `String` is a more specific candidate than `Object`, so the compiler can select the new method.

## 21. References

- [Java Language Specification 17, §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): signature components, subsignatures, and erasure.
- [Java Language Specification 17, §8.4.9 — Overloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.9): rules for declaring overloaded methods.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): candidate search phases, most-specific method, varargs, and invocation semantics.
- [Java SE 17 API — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): unit-explicit duration type.
- [Java SE 17 API — StringJoiner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html): joining string elements in the complete example.

**Key takeaway:** a good overload is not just about having different signatures. It is **a group of calls sharing the same meaning**, with **clear defaults**, **a consistent validation/implementation flow**, avoiding **ambiguity** and **unexpected type conversions**, while remaining **easy to extend** without making client code harder to use. Design from the caller's perspective first, and then choose how many overloads are enough.
