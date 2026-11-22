# Designing a Utility Class with a `private` Constructor in Java

## 1. What Is a Utility Class?

A **utility class** is a class used to **group functionally related operations**, typically provided as **`static methods`** and the necessary constants, and **does not represent an entity with its own instance state**.

Familiar Java APIs demonstrate this style:

- `Math.max(3, 7)`: computes the greater of two numbers.
- `Arrays.toString(values)`, `Arrays.sort(values)`: helper operations for arrays.
- `Objects.requireNonNull(value)`: checks a reference value.
- `Collections.unmodifiableList(list)`: provides a view that disallows modification through that view per its contract.
- `Integer.parseInt("42")`: converts a string to an `int`. This is a **static method on a class that also serves other purposes**, not an example suggesting that every class with a static method is a utility-only class.

When building a utility class yourself, such as `TextUtils` or `NumberUtils`, the typical goals are:

1. Calling functionality through the **class name**: `TextUtils.normalize(input)`.
2. Not needing to create objects of type `TextUtils`.
3. Having no instance fields that need to be retained across calls.
4. Not misleadingly suggesting that each utility object has its own identity or lifecycle.
5. Exposing only a **shared API** that is genuinely meaningful.

Because no object of a utility class is needed, an important design decision is to **close off unnecessary instantiation paths with a `private` constructor**.

> **Common pattern:** `public final class XUtils { private XUtils() { ... } public static ... }`. However, `public`, `final`, and `private` solve **three different problems**; you need to understand each modifier clearly rather than mechanically copying the template.

## 2. Why Is Writing Only Static Methods Still Not Enough?

If you write:

```java
public class NumberUtils {
    public static int square(int value) {
        return value * value;
    }
}
```

This is a class with a static method. **However**, because the class declares no constructors, Java automatically provides an appropriate **default constructor**. For a `public class` like the one above, the default constructor is `public`; a caller can write:

```java
NumberUtils utils = new NumberUtils();
System.out.println(utils.square(4)); // Compiles, but conveys the wrong intent.
```

This call is an **illustrative code snippet inside a method**. It creates a `NumberUtils` object that carries no useful state, then calls a static method through an instance variable. The calculation still returns 16, but this way of writing misleadingly suggests that the method depends on the `utils` object.

There is no business reason for multiple instances to exist like:

```java
NumberUtils a = new NumberUtils();
NumberUtils b = new NumberUtils();
```

Two `NumberUtils` objects differ in identity, yet provide no distinct information needed by `square`. Creating them incurs overhead and introduces API noise, however small the cost may be.

**Fix:** declare a constructor that is inaccessible from code outside the class:

```java
public final class NumberUtils {
    private NumberUtils() {
    }

    public static int square(int value) {
        return value * value;
    }
}
```

Then clients use:

```java
int result = NumberUtils.square(4);
```

There is no need to create a `NumberUtils` instance, and `new NumberUtils()` cannot be written from an unrelated class under Java source access rules.

## 3. The Three Modifiers in the Utility Class Pattern

| Modifier | Where Is It Placed? | Purpose | Does Not Mean |
| --- | --- | --- | --- |
| `public` | Top-level utility class when used outside the package | Allows clients to reference the class by name | Does not automatically make all fields/methods public |
| `final` | Utility class | Prevents the class from being subclassed | Does not automatically make the constructor private |
| `private` | Constructor | Prevents callers outside the permitted scope from directly calling the constructor | Does not stop static methods from working |
| `static` | Utility methods and appropriate shared members | Called via the class name, without needing a receiver | Does not mean it only runs once |
| `private static` | Internal helper methods/fields | Keeps implementation details out of the API | Does not automatically guarantee thread safety |
| `public static final` | Public constants with a stable contract | Places constants at the class level; the field cannot be reassigned | Does not automatically freeze a mutable object referenced by the field |

**Key point:** A `private` constructor and the `final` modifier **do not substitute for each other**:

- Only a `private` constructor: blocks ordinary `new Utility()` calls from unrelated classes; access rules from enclosing/nest members must still be considered.
- Only a `final` class: blocks inheritance, but **does not block instance creation** if a constructor is accessible.
- Using both usually expresses the intent “no instantiation, no subclassing” clearly.

Making a utility class `final` is usually a reasonable choice, but **is not required for static methods to work**. If a class is intentionally designed for subclassing/extension, it probably should not be classified as a utility-only class.

## 4. First Complete Example: A Utility Class That Cannot Be Instantiated by Clients

Create the file **`UtilityClassDemo.java`**:

```java
final class TextUtils {
    private TextUtils() {
        throw new AssertionError("No TextUtils instances");
    }

    static String normalize(String text) {
        if (text == null) {
            throw new IllegalArgumentException("text is required");
        }
        return text.trim().toLowerCase();
    }

    static boolean sameNormalized(String left, String right) {
        return normalize(left).equals(normalize(right));
    }
}

public class UtilityClassDemo {
    public static void main(String[] args) {
        System.out.println(TextUtils.normalize("  JAVA  "));
        System.out.println(TextUtils.sameNormalized(" Java ", "java"));

        // TextUtils helper = new TextUtils();
        // If uncommented: error because the constructor is private.
    }
}
```

Compile and run with **Java 17+**:

```bash
javac UtilityClassDemo.java
java UtilityClassDemo
```

**Standard output:**

```text
java
true
```

Explanation:

- `TextUtils` is a top-level package-private `final` class. In the demo program, `UtilityClassDemo` is in the same package, so it is allowed to call the package-private static methods of `TextUtils`.
- `TextUtils.normalize(...)` works **without a `TextUtils` object**.
- The constructor is `private`; clients in other classes cannot call it directly.
- The constructor intentionally throws `AssertionError` to emphasize that the utility is not expected to have instances; this is an option, not a mandatory requirement.
- Both static methods operate on parameters and do not maintain mutable instance state.

**Compilation note:** the example above has exactly **one public top-level class**, `UtilityClassDemo`. Because `TextUtils` is not public, it can reside in the same file. If you want `TextUtils` to be a public API for other packages, you should place it in `TextUtils.java`, declare `public final class TextUtils`, and make the methods intended for external callers public.

## 5. What Does a `private` Constructor Actually Block?

A private constructor specifies **where normal Java code is allowed to call the constructor**. For example:

```java
final class ParserUtils {
    private ParserUtils() {
    }

    static int parsePositive(String raw) {
        int value = Integer.parseInt(raw);
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        return value;
    }
}
```

Callers can still use the static API when access permissions allow:

```java
int number = ParserUtils.parsePositive("12");
```

However, an unrelated class cannot:

```java
// ParserUtils parser = new ParserUtils(); // Compile-time error.
```

**Important point:** a private constructor **does not prevent the class from being loaded or statically initialized**, does not prevent calling static methods, does not create a singleton instance, and does not mean “the class does not exist at runtime”.

Java also has cases where **private access is permitted** within the enclosing/nestmate relationship of nested classes. Therefore, the accurate statement is “a private constructor blocks ordinary instance creation from code without access”, **not** “no program can create this object under any circumstances”.

### Should You Write an Empty Constructor or Throw `AssertionError`?

Both of the following versions are common:

```java
private ParserUtils() {
}
```

```java
private ParserUtils() {
    throw new AssertionError("Utility class");
}
```

- **Empty constructor**: sufficient to block code outside the valid access scope from calling the constructor.
- **Constructor throwing `AssertionError`**: clearly shows that even code with private access that accidentally calls the constructor will fail at runtime.
- **There is no requirement** for a utility constructor to throw an exception; using `throw` in the code is a design/team choice.
- `AssertionError` is not a security mechanism against reflection or all non-standard ways of creating objects.
- Do not confuse the `AssertionError` type with the `assert` keyword: they are different; throwing `new AssertionError(...)` **does not depend** on enabling JVM assertions with `-ea`.

**Recommendation:** choose a simple, consistent convention. Having an explicit private constructor matters more than debating between an empty body and one that throws an error.

## 6. Constructors Have No Return Type, Not Even `void`

A constructor is a distinct Java syntax construct: its name **matches the class name**, and it declares no return type.

Correct:

```java
final class Constants {
    private Constants() {
    }
}
```

Wrong in intent:

```java
class Constants {
    private void Constants() {
        // This is a method named Constants, NOT a constructor.
    }
}
```

In the second example, `private void Constants()` is **a valid method** as long as it does not conflict with other rules. Because the class **declares no actual constructor**, the compiler can still provide a default constructor. Accidentally adding `void` **does not block instance creation**.

This is a very dangerous mistake when learners try to “create a private constructor” but write a private method instead. How to check: a constructor has no `void`, `int`, `String`, or any return type.

## 7. When No Constructor Is Declared, Java Automatically Generates a Default Constructor

The difference between:

```java
public class Utility {
    public static int doubleOf(int x) {
        return x * 2;
    }
}
```

and:

```java
public class Utility {
    private Utility() {
    }

    public static int doubleOf(int x) {
        return x * 2;
    }
}
```

These are **two alternative versions** and are not compiled together with the same name `Utility`.

In the first version, because the class has no declared constructor, the compiler adds a **default constructor** with the corresponding access modifier according to Java rules. For an ordinary public top-level class, the default constructor is public, so clients can write `new Utility()`.

In the second version, the constructor is declared explicitly and is private; the compiler **no longer automatically adds a public no-arg constructor**. That is why a utility class must write a private constructor **rather than merely omitting constructors from the source code**.

### A Parameterized Constructor Also Prevents the Default No-Arg Constructor

If a class declares `Utility(int code)`, Java does not add the default `Utility()`. However, callers can still create an object via `new Utility(1)` when this constructor is accessible. To declare “no instance needed”, you should keep **only intentional private constructors**; any public constructor still permits instantiation.

## 8. Why Does `final` Often Accompany a Private Constructor?

A `final class` cannot be subclassed. For a utility-only class, inheritance usually makes no sense because:

1. Static methods are not overridden through ordinary instance polymorphism; a static method with a matching signature in a subclass can be **hiding**, not dynamic dispatch.
2. There is no instance state or instance behavior to extend.
3. Inheriting from a utility class primarily to call static members by the subclass name is misleading about API ownership.
4. `final` makes the intent “this is a utility group, not a base class” clear.

Example:

```java
public final class DateTextUtils {
    private DateTextUtils() {
    }

    public static String yearMonth(int year, int month) {
        return year + "-" + String.format("%02d", month);
    }
}
```

The code above is a utility class; there is no need to create an object or inherit from it to use `DateTextUtils.yearMonth(2026, 10)`.

**Design note:** If the real goal is to allow subclasses to override formatting logic, consider an **instance interface/strategy** instead of trying to override a static method. `final` and a private constructor are not a mandatory “performance optimization”; they communicate a contract.

## 9. Practical Example: A Utility for Validating and Normalizing Codes

Create **`CodeUtilsDemo.java`**:

```java
final class CodeUtils {
    private CodeUtils() {
        throw new AssertionError("No instances");
    }

    static String canonical(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("code required");
        }

        String value = raw.trim().toUpperCase();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank code");
        }

        return value;
    }

    static boolean same(String first, String second) {
        return canonical(first).equals(canonical(second));
    }

    static String withPrefix(String prefix, String raw) {
        return canonical(prefix) + "-" + canonical(raw);
    }
}

public class CodeUtilsDemo {
    public static void main(String[] args) {
        System.out.println(CodeUtils.canonical("  ab-12  "));
        System.out.println(CodeUtils.same(" a1 ", "A1"));
        System.out.println(CodeUtils.withPrefix(" item ", " b2 "));
    }
}
```

```bash
javac CodeUtilsDemo.java
java CodeUtilsDemo
```

```text
AB-12
true
ITEM-B2
```

Lessons:

- `canonical` is a pure static method with respect to utility object state; its return value is based on its arguments.
- `same` and `withPrefix` reuse `canonical` to avoid duplicating validation.
- There are no instance fields and no `CodeUtils` objects.
- Methods can throw exceptions when input is invalid; static does not mean “cannot fail”.
- Default `toUpperCase()` and `toLowerCase()` can be locale-dependent when used without specifying a locale. For **protocol identifiers** that require cross-machine consistency, consider `toUpperCase(Locale.ROOT)`. The example above uses ASCII input so stdout is deterministic; production design needs to clarify locale rules.

### A Locale-Independent, Identifier-Friendly Version

```java
import java.util.Locale;

final class CanonicalIds {
    private CanonicalIds() {
    }

    static String of(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        return input.trim().toUpperCase(Locale.ROOT);
    }
}
```

This is an **illustrative class declaration**; the import goes at the top of the file when used. `Locale.ROOT` keeps case conversion locale-neutral for many identifier-handling cases; it does not by itself turn this normalization into a complete Unicode or security identifier policy.

## 10. Distinguishing a Utility Class from a Stateful Object

A utility class is suitable for operations like:

```java
int max = Math.max(a, b);
String key = CodeUtils.canonical(raw);
```

However, if the problem requires distinct state per user, session, configuration, or lifecycle, an **instance class** is usually more appropriate.

For example, you should not cram everything into a mutable static field:

```java
class BadCartUtils {
    static int total;

    static void add(int amount) {
        total += amount;
    }
}
```

Users/callers in the same process could accidentally share a single `total` variable. The `add` method is static, yet the data **belongs to each individual shopping cart**, not the application level.

A semantically sound design:

```java
class ShoppingCart {
    private int total;

    void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        total += amount;
    }

    int total() {
        return total;
    }
}
```

Each `new ShoppingCart()` creates an object with its own `total`. `cart.add(...)` is an instance method with a specific receiver. There may be a static helper to assist with fee calculation, but **the cart state itself** should belong to the cart object.

**Principle:** do not use a utility class to avoid learning classes and objects, or to turn per-instance state into global state.

## 11. Example Comparing a Stateless Utility and a Stateful Object

Create the file **`UtilityVsObjectDemo.java`**:

```java
final class PriceUtils {
    private PriceUtils() {
    }

    static int withFee(int price, int fee) {
        if (price < 0 || fee < 0) {
            throw new IllegalArgumentException("negative value");
        }
        return Math.addExact(price, fee);
    }
}

class Cart {
    private int total;

    void addItem(int price, int fee) {
        total = Math.addExact(total, PriceUtils.withFee(price, fee));
    }

    int total() {
        return total;
    }
}

public class UtilityVsObjectDemo {
    public static void main(String[] args) {
        Cart first = new Cart();
        Cart second = new Cart();

        first.addItem(100, 10);
        first.addItem(50, 5);
        second.addItem(20, 2);

        System.out.println("first=" + first.total());
        System.out.println("second=" + second.total());
    }
}
```

```bash
javac UtilityVsObjectDemo.java
java UtilityVsObjectDemo
```

```text
first=165
second=22
```

Here:

- `PriceUtils.withFee` is a static utility: it relies only on `price` and `fee` and needs no instance state.
- `Cart.addItem` is an instance method: it modifies the `total` belonging to each cart.
- The additions use `Math.addExact` so that any integer overflow error occurs **before the assignment to total completes**, avoiding corrupting the field in an overflow scenario.
- A utility class cannot replace the state-holding role of `Cart`.

Decide how to separate utility and instance classes based on **responsibility boundaries**, not because “static is more convenient to call”.

## 12. A Utility Class Is Not a Singleton

A **singleton** is a design pattern that aims to provide **a single shared instance**, whereas a utility class with a private constructor and only static methods usually **needs no instance at all**.

Comparison:

| Criterion | Utility class | Singleton/single-instance service |
| --- | --- | --- |
| Primary API | `TypeName.staticMethod()` | `getInstance().instanceMethod()` or injected service |
| Instance required | No | Yes |
| State per instance | Usually none | May have state |
| Private constructor | Prevents normal instance creation | Can control instance count |
| Polymorphism via instance | Not for static methods | Possible if the API is instance-based and the design supports it |
| Test dependency substitution | Often requires refactoring/configuring a wrapper | Can replace implementation using an interface/DI |
| Lifecycle and cleanup | No utility object to close | Can manage lifecycle/service |

**A private constructor does not create a singleton by itself.** It only restricts access to calling the constructor. A singleton requires a mechanism to create, retain, and publish the instance with an appropriate contract.

Singleton example (for comparison only):

```java
final class ConfigService {
    private static final ConfigService INSTANCE = new ConfigService();

    private ConfigService() {
    }

    static ConfigService getInstance() {
        return INSTANCE;
    }

    String mode() {
        return "demo";
    }
}
```

Here `getInstance()` is static, while `mode()` is an **instance method** on the singleton object. In contrast, a pure utility class does not create an `INSTANCE` and has no `mode()` bound to object state.

**Note:** if the goal is a robust singleton that avoids many serialization and reflection pitfalls, an `enum` singleton is often worth considering. This is a different problem from a utility class, and you do not need to use an enum merely to hold static helpers.

## 13. Do Not Add Mutable Static Fields Arbitrarily

A static utility that depends only on its inputs is usually easy to reuse and easy to test. However, if you put a mutable static field into a utility, it becomes **shared application state**:

```java
final class RequestUtils {
    private static int counter;

    private RequestUtils() {
    }

    static int next() {
        return ++counter;
    }
}
```

Wherever `RequestUtils.next()` is called, it modifies the same `counter` field of the class for its corresponding class loader/class identity. Across multiple threads, `++counter` risks lost updates; `static` **does not guarantee atomicity or thread safety**.

Version when you truly want a shared counter:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class RequestUtils {
    private static final AtomicInteger COUNTER = new AtomicInteger();

    private RequestUtils() {
    }

    static int next() {
        return COUNTER.incrementAndGet();
    }
}
```

The two `RequestUtils` snippets are **two alternative versions**. `AtomicInteger.incrementAndGet` supports atomic incrementing per this type's contract. However, if unique IDs are needed across multiple JVMs or after restarts, a static counter within a single process is still not enough.

**Design question:** does that data belong to the entire application or to a specific object? If it has its own session/tenant/test scope, prefer keeping state in an instance/service with an explicit lifecycle rather than hiding it inside a utility class.

## 14. Static Methods Should Stay Simple and Clear About Side Effects

A utility method named `normalize` or `calculate` usually sets an expectation of **minimal side effects**. No Java rule forces a static method to be pure, but keeping utility behavior clear helps clients trust it more.

Compare two approaches:

```java
static int sortedMaximum(int[] values) {
    java.util.Arrays.sort(values);
    return values[values.length - 1];
}
```

This method **modifies the input array** and also fails on an empty array. If the API only means “find the maximum”, the mutation is unnecessary.

An option that does not mutate the input:

```java
static int maximum(int[] values) {
    if (values == null || values.length == 0) {
        throw new IllegalArgumentException("values required");
    }

    int max = values[0];
    for (int value : values) {
        if (value > max) {
            max = value;
        }
    }
    return max;
}
```

These are **two illustrative static method snippets**; place one inside an appropriate utility class. The second version reads the array without sorting or changing its slots, states preconditions clearly, and guards against empty/null inputs.

**Good design:** document if a method **mutates arguments**, has I/O side effects, accesses shared mutable state, caches, or uses the current time. `static` does not guarantee purity; the implementation and contract themselves decide that.

## 15. Public API and Private Helper Methods

A utility class can have **public static methods** serving clients and **private static helpers** serving only the implementation.

The file **`ApiHelperDemo.java`**:

```java
final class KeyUtils {
    private KeyUtils() {
    }

    static String key(String prefix, String raw) {
        return requirePart(prefix) + ":" + requirePart(raw);
    }

    private static String requirePart(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("blank part");
        }
        return input.trim().toUpperCase(java.util.Locale.ROOT);
    }
}

public class ApiHelperDemo {
    public static void main(String[] args) {
        System.out.println(KeyUtils.key(" user ", " a42 "));

        // KeyUtils.requirePart("x"); // Error: private.
    }
}
```

```bash
javac ApiHelperDemo.java
java ApiHelperDemo
```

```text
USER:A42
```

In this demo, `KeyUtils.key` is package-private because the client is in the same package. When providing a public library, you can declare `public final class KeyUtils` and `public static String key(...)`, while keeping `requirePart` private.

**Encapsulation principle:** a public utility class does not need to make every helper method/field public. Expose only calls with a stable contract; private helpers can change their names and implementations without clients directly depending on them.

### A Top-Level Utility Class Can Be Package-Private

A helper does not necessarily have to be public. If a utility is used only by classes in the `app.internal` package, use:

```java
final class InternalMath {
    private InternalMath() {
    }

    static int clamp(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("invalid bounds");
        }
        return Math.max(min, Math.min(value, max));
    }
}
```

`InternalMath` is a top-level package-private class. Any class in the same package can call `InternalMath.clamp(...)` under the access rules; code in other packages cannot directly use it. The constructor remains private because no instance needs to be created.

## 16. Static Imports: Concise Syntax Without Changing the Utility's Nature

Suppose there is a public utility:

```java
package demo.util;

public final class CheckUtils {
    private CheckUtils() {
    }

    public static boolean positive(int value) {
        return value > 0;
    }
}
```

The file should be saved as **`CheckUtils.java`** in the `demo.util` package. A caller in another package can call:

```java
boolean valid = demo.util.CheckUtils.positive(5);
```

Or use a static import:

```java
import static demo.util.CheckUtils.positive;
```

and then:

```java
boolean valid = positive(5);
```

These are **illustrative source snippets, not a single verbatim combined file**; `import` must be placed in its proper position at the top of a compilation unit.

`import static` does not create an instance, does not invoke the method, and does not change access modifiers. It only allows resolving the method name without qualification at the call site; access rules still apply.

You should not indiscriminately static-import every method with generic names like `parse`, `get`, or `check` if doing so makes it hard to tell where an implementation belongs. For clear utility APIs, `CheckUtils.positive(...)` is often easier to follow.

## 17. Is Exposing Constants in a Utility Class Necessary?

A utility class can store constants:

```java
public final class Limits {
    public static final int MAX_BATCH_SIZE = 100;

    private Limits() {
    }
}
```

Read it via `Limits.MAX_BATCH_SIZE`. However, only use `public` when it is part of the **API contract** needed by clients. Internal constants should be `private static final` or package-private as required.

### Distinguishing `static final` from Deep Immutability

`public static final int MAX_BATCH_SIZE` is a primitive constant that cannot be reassigned from other code.

By contrast:

```java
public static final java.util.List<String> NAMES =
        new java.util.ArrayList<>();
```

Although the field reference is `final`, **the list object is still mutable**; callers can write `SomeUtils.NAMES.add("X")` if the field is accessible. For publicly shared data, consider `List.of(...)` or returning a defensive copy/unmodifiable view per the contract.

**A common misconception:** that because a utility class has no instances, “all data inside it is safe”. Static mutable objects can be an even subtler source of side effects than instance state.

## 18. Organizing Java Files and Public Class Names

A public top-level utility class should be placed in a file matching the class name:

```text
src/
  demo/
    util/
      TextUtils.java
    app/
      Main.java
```

**File `src/demo/util/TextUtils.java`:**

```java
package demo.util;

public final class TextUtils {
    private TextUtils() {
    }

    public static String headline(String text) {
        if (text == null) {
            throw new IllegalArgumentException("text required");
        }
        return text.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
```

**File `src/demo/app/Main.java`:**

```java
package demo.app;

import demo.util.TextUtils;

public class Main {
    public static void main(String[] args) {
        System.out.println(TextUtils.headline(" java core "));
    }
}
```

From the directory containing `src`:

```bash
javac -encoding UTF-8 -d out src/demo/util/TextUtils.java src/demo/app/Main.java
java -cp out demo.app.Main
```

**Output:**

```text
JAVA CORE
```

Here:

- `TextUtils` is top-level public so code in `demo.app` can reference it by name.
- The private constructor preserves the intent of not creating objects.
- The static method is public so callers in other packages can use it.
- `Main` depends only on the static API and does not need `new TextUtils()`.

If the project uses **JPMS named modules**, the package containing the public class must also be appropriately exported to other modules. `public` does not automatically cross `module-info.java` boundaries.

## 19. Do Not Store Mutable Configuration in a Static Utility

A utility class such as:

```java
final class FormatUtils {
    static String language = "vi";

    private FormatUtils() {
    }

    static String greeting() {
        return language.equals("vi") ? "Xin chào" : "Hello";
    }
}
```

creates a single shared point of mutable state at the class level. If two users or two tests need different locales, modifying `FormatUtils.language` can cause them to interfere with each other. In addition, there is a concurrency risk.

Stateful object design:

```java
final class Greeter {
    private final String language;

    Greeter(String language) {
        this.language = language;
    }

    String greeting() {
        return "vi".equals(language) ? "Xin chào" : "Hello";
    }
}
```

Each `Greeter` holds its own configuration. A utility class can still provide **an operation that accepts language as a parameter**, without having to own global configuration:

```java
static String greeting(String language) {
    return "vi".equals(language) ? "Xin chào" : "Hello";
}
```

This method snippet goes inside a utility class. **Selection rule:** if a value varies by user/request/tenant/lifecycle, passing configuration explicitly or using an instance service/strategy is usually safer and clearer than a mutable static field.

## 20. Utility Classes and Dependency Injection/Testability

A pure static helper with no environmental dependencies is usually easy to test:

```java
int result = PriceUtils.withFee(100, 10);
```

However, a static method that directly reads real time, environment variables, or makes network calls can be hard to control in tests:

```java
// Example snippet of a design prone to environment dependencies:
static java.time.Instant now() {
    return java.time.Instant.now();
}
```

If business code needs a mockable “clock”, pass an appropriate dependency:

```java
class ReportService {
    private final java.time.Clock clock;

    ReportService(java.time.Clock clock) {
        this.clock = clock;
    }

    java.time.Instant generatedAt() {
        return java.time.Instant.now(clock);
    }
}
```

Here `ReportService` is an instance service with an explicit dependency; in tests you can pass `Clock.fixed(...)`, and in production you pass the system clock. `Instant.now(clock)` is a static factory, yet it reads the provided clock, making it easier to test than an API that forces use of the system clock.

**Static methods are not always hard to test:** pure static utility methods with consistent inputs/outputs are usually very easy to test. Difficulty arises when a static method **hides mutable or non-deterministic dependencies** or when the implementation needs to be swapped at runtime.

## 21. Runnable Example: Designing a Utility for Range Checking

The file **`RangeUtilsDemo.java`**:

```java
final class RangeUtils {
    private RangeUtils() {
        throw new AssertionError("No RangeUtils instances");
    }

    static boolean contains(int value, int min, int max) {
        checkBounds(min, max);
        return value >= min && value <= max;
    }

    static int clamp(int value, int min, int max) {
        checkBounds(min, max);
        return Math.max(min, Math.min(value, max));
    }

    private static void checkBounds(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
    }
}

public class RangeUtilsDemo {
    public static void main(String[] args) {
        System.out.println(RangeUtils.contains(7, 1, 10));
        System.out.println(RangeUtils.contains(12, 1, 10));
        System.out.println(RangeUtils.clamp(-3, 0, 100));
        System.out.println(RangeUtils.clamp(150, 0, 100));
    }
}
```

```bash
javac RangeUtilsDemo.java
java RangeUtilsDemo
```

```text
true
false
0
100
```

Notable points:

- `contains` and `clamp` form a clear **static API**.
- `checkBounds` is a private static helper that avoids duplicating validation without exposing internal details.
- The private constructor protects the no-instance design.
- The `final` class prevents inheritance.
- Each call performs its checks independently; there is no object state to store between calls.

**Scope limitation:** the `RangeUtils` utility handles integers with both bounds inclusive; if you want a different API such as a half-open interval, define a different method name/contract rather than silently changing the meaning of `contains`.

## 22. Avoid Duplicate Helper Classes and Overly Generic Names

A utility class can become a “catch-all container” if unrelated methods are grouped together merely because they are all static:

```java
class Utils {
    static String normalizeName(String name) { /* ... */ return name; }
    static int calculateTax(int value) { /* ... */ return value; }
    static void sendEmail(String email) { /* ... */ }
}
```

This is a **structural illustration snippet**, with simplified method bodies. The name `Utils` does not clearly state a responsibility; testability and ownership can suffer.

It is better to group by specific domain:

- `NameNormalizer` or `NameUtils` for name processing.
- `TaxCalculator` for tax calculation (which can be an instance class if it has policies/configuration).
- `EmailService` for sending email (usually a service with dependencies; it should not casually be placed in a static helper if it needs connections, retries, logging, and configuration).

The goal is not to have as many classes as possible. A good utility class **has functional cohesion**: related methods, an easy-to-understand contract, minimal shared state, and no hidden dependencies.

## 23. Cases Where a `private constructor` Is an Inappropriate Design

Do not apply the “private constructor + static methods” pattern if:

1. **Objects have their own state**: `BankAccount`, `Order`, and `ShoppingCart` should have appropriate instance lifecycles.
2. **Polymorphism/strategy is needed**: when implementations are interchangeable, interfaces and instance methods are usually more appropriate.
3. **Dependency injection is needed**: a service depending on a `Clock`, repository, HTTP client, and so on usually needs a constructor/factory that receives dependencies, rather than hiding everything in static globals.
4. **Resources need to be held and closed**: database connections/sessions/file handles require a clear lifecycle and cleanup, and should not be simulated with uncontrolled mutable static fields.
5. **The class is a base class intended for inheritance**: a private constructor can prevent subclasses from calling the superclass constructor from the appropriate context; `final` directly forbids inheritance.
6. **Returning objects via a static factory is the primary purpose, while the class is also a data type**: for example, `UserId.of(...)` with a private constructor is an *immutable value object with a factory*, **not necessarily a utility class**; `UserId` still has instances with their own values.
7. **A framework needs to instantiate the class in its own way**: read the framework contract (ORM, serializer, dependency injection) before locking down the constructor. Do not assume the utility pattern applies to entity/component classes.

**Evaluation criterion:** If creating multiple instances of the class is **meaningful in the business domain**, it is usually not a utility-only class.

## 24. Pitfalls Related to Inheritance and Static Method Hiding

Writing a `final` utility class prevents others from creating subclasses. Even if `final` is omitted, static methods do **not** participate in polymorphic overriding like instance methods.

Example:

```java
class BaseUtils {
    static String name() {
        return "Base";
    }
}

class ChildUtils extends BaseUtils {
    static String name() {
        return "Child";
    }
}
```

If you have `BaseUtils ref = new ChildUtils();`, calling `ref.name()` still selects `BaseUtils.name()` via static method resolution, not Child based on the runtime object. In utility design, `extends BaseUtils` usually does not deliver the polymorphism people expect.

**Note:** the example above allows instance creation to illustrate method hiding and is **not** the standard utility class pattern because the constructors are not private. A true utility-only class should use `final` and a private constructor if inheritance is not intended.

## 25. Nested Utility Helpers Can Be a `private static class`

If a helper serves only a single public class, a new top-level utility class is not strictly necessary:

```java
public class ReportService {
    private static final class Text {
        private Text() {
        }

        static String tidy(String value) {
            return value == null ? "" : value.trim();
        }
    }

    public String report(String title) {
        return "Report:" + Text.tidy(title);
    }
}
```

In this example:

- `Text` is a **private static nested class**, serving only the implementation of `ReportService`.
- `static` on the nested class means it **does not need an enclosing `ReportService` instance** to exist.
- `private` on the nested class governs the accessibility scope of the type name.
- The private constructor inside `Text` blocks creating unnecessary utility objects.
- The static method `Text.tidy` can be called by `ReportService` under the access rules between enclosing and nested classes.

There is no need to turn `Text` into a public top-level utility just so one method can call it. However, if there is only a very small helper method, it may be simpler to place `private static String tidy(...)` directly inside `ReportService` without creating an extra nested type.

## 26. A Private Constructor Can Still Be Called by Code with Access

A rule that needs to be understood accurately: code inside **the class itself** can always call a private constructor; nestmate/enclosing cases can also access it under the language rules.

The file **`PrivateConstructorScopeDemo.java`**:

```java
public class PrivateConstructorScopeDemo {
    private PrivateConstructorScopeDemo() {
        System.out.println("constructor called internally");
    }

    public static void main(String[] args) {
        // Same class, so the private constructor is still accessible.
        PrivateConstructorScopeDemo instance =
                new PrivateConstructorScopeDemo();

        System.out.println(instance != null);
    }
}
```

```bash
javac PrivateConstructorScopeDemo.java
java PrivateConstructorScopeDemo
```

```text
constructor called internally
true
```

The example above **intentionally** calls the private constructor from the class itself to illustrate access boundaries. It is **not a practical utility class pattern** (because a utility class should not create meaningless instances). If you want a class to guard against even this accidental call at runtime, you can throw `AssertionError` in the constructor, though it still should not be treated as an “impossible-to-instantiate” mechanism against all reflection/VM techniques.

**Conclusion on `private`:** it determines **source code** access permissions based on context. It does not turn the constructor into invalid syntax everywhere.

## 27. Should You Use `abstract` Instead of a `private` Constructor?

A learner might suggest:

```java
abstract class Utility {
    static int square(int x) {
        return x * x;
    }
}
```

That is because an abstract class cannot be instantiated directly with `new Utility()`, yet:

- The class can be **subclassed** unless prevented by other restrictions.
- If no constructor is declared, it still has an appropriate default constructor for subclasses.
- The `abstract` keyword conveys the meaning “can serve as a base class for implementations”, which is misleading.
- `abstract final class Utility` is an invalid modifier combination for a class in Java.

Therefore, for a utility-only class that **needs neither instances nor inheritance**, **`final class + private constructor`** is usually chosen instead of using `abstract` to block `new` indirectly.

## 28. Unit Testing a Utility Class

Pure static methods that take inputs and return outputs are relatively easy to test. In particular, check:

- Normal and boundary inputs (0, negative values, large values, and null when the API may receive null).
- Arithmetic boundaries (`Integer.MAX_VALUE`, overflow, division by zero if applicable).
- Locale, Unicode, and encoding when processing strings.
- Invalid inputs must throw exceptions according to the contract.
- If a method mutates an array/list supplied by the caller, test the side effects or verify that it does not mutate.
- If there is shared state/static caching, test isolation and concurrency appropriately.

An example of manual testing without a framework:

The file **`UtilitySelfTestDemo.java`**:

```java
final class NumberUtils {
    private NumberUtils() {
    }

    static int positiveSquare(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
        return Math.multiplyExact(value, value);
    }
}

public class UtilitySelfTestDemo {
    public static void main(String[] args) {
        if (NumberUtils.positiveSquare(3) != 9) {
            throw new AssertionError("3^2 should be 9");
        }

        boolean invalidRejected = false;
        try {
            NumberUtils.positiveSquare(-1);
        } catch (IllegalArgumentException ex) {
            invalidRejected = true;
        }

        if (!invalidRejected) {
            throw new AssertionError("negative input accepted");
        }

        System.out.println("tests passed");
    }
}
```

```bash
javac UtilitySelfTestDemo.java
java UtilitySelfTestDemo
```

```text
tests passed
```

`NumberUtils.positiveSquare` checks for negative input and uses `Math.multiplyExact` to throw an error when squaring overflows `int`, before there is any mutable state that would need restoration. No `assert` statement appears, so the checks do not depend on `-ea`.

**It is not mandatory to test a private constructor using reflection** merely to achieve code coverage. The design value here is that the constructor **is not part of the accessible API** for ordinary clients. Tests should prioritize the contract of the static methods and useful failure cases.

## 29. Practical Question: Properly Designing a Utility for a Collection of Values

Create the file **`CollectionUtilsDemo.java`**:

```java
import java.util.List;

final class NumberListUtils {
    private NumberListUtils() {
        throw new AssertionError("No instances");
    }

    static int sum(List<Integer> numbers) {
        if (numbers == null) {
            throw new IllegalArgumentException("numbers required");
        }

        int total = 0;
        for (Integer number : numbers) {
            if (number == null) {
                throw new IllegalArgumentException("null element");
            }
            total = Math.addExact(total, number);
        }
        return total;
    }

    static int countPositive(List<Integer> numbers) {
        if (numbers == null) {
            throw new IllegalArgumentException("numbers required");
        }

        int count = 0;
        for (Integer number : numbers) {
            if (number == null) {
                throw new IllegalArgumentException("null element");
            }
            if (number > 0) {
                count++;
            }
        }
        return count;
    }
}

public class CollectionUtilsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(-2, 4, 7);

        System.out.println(NumberListUtils.sum(numbers));
        System.out.println(NumberListUtils.countPositive(numbers));
        System.out.println(numbers);
    }
}
```

```bash
javac CollectionUtilsDemo.java
java CollectionUtilsDemo
```

```text
9
2
[-2, 4, 7]
```

- `NumberListUtils` contains related operations in the same domain: lists of integers.
- Private constructor, final class: no utility instance is needed.
- Methods are static and do not store mutable state between calls.
- Validates the list and null elements according to the chosen contract.
- Uses `Math.addExact` to avoid silent overflow when summing.
- Does not call `remove`/`set`/`sort`, so the example does not modify the structure or element references of the input list.

In general Java code, `List<Integer>` can be a mutable or unmodifiable list and may contain null depending on the implementation. The utility contract must specify the null policy rather than assuming every list behaves like `List.of(...)`.

## 30. Diagnosing Common Errors

| Situation | Cause | Fix |
| --- | --- | --- |
| Static methods are written, yet `new Utils()` still works | The compiler adds a default constructor | Declare an actual private constructor |
| Writing `private void Utils()` | This is a method, not a constructor | Remove the `void` return type |
| A private constructor exists, yet another public constructor still exists | Callers use the remaining public constructor | Review all constructors |
| Assuming `final` prevents object creation | `final` only prevents subclassing | Add a private constructor |
| Assuming a private constructor blocks every way to create an instance on the JVM | `private` is normal access control, not a guarantee of absolute impossibility | State the contract accurately; do not rely on it as a security boundary |
| Putting `new Utils()` inside a static utility method | No utility instance is needed | Call the static helper directly |
| Calling `utils.method()` when the method is static | Syntax creates a misleading impression of a receiver | Write `Utils.method()` |
| Using `this.field` in a static method | A static context has no `this` | Use a parameter/specific object or an instance method |
| Moving a mutable field to static for easier calling | Creates unintended shared state | Keep state in an instance/service |
| Using `abstract` for a utility class | Easily suggests unintended inheritance | `final` + private constructor |
| Marking a helper private when clients need to use it | Access is narrower than what the public API needs | Expose only the API genuinely needed; keep details private |
| Exposing a mutable `static final List` | final does not make the list immutable | Use immutable/unmodifiable data or a defensive copy |
| A utility contains every unrelated helper | Low cohesion | Split by clear responsibilities |
| Making every method static even when polymorphism is needed | Static methods are not overridden | Use an instance interface/strategy |
| Using a global static clock/config | Tests and multi-tenant setups depend on environment state | Pass dependencies via parameters/constructors |
| Assuming a static method is automatically thread-safe | Static does not provide synchronization | Use atomics/locks or eliminate shared mutation |
| Private constructor prevents a framework from instantiating an entity | The framework requires its own construction contract | Choose a pattern suited to the entity/framework instead of a utility |
| Using static imports indiscriminately | Hard to tell from the source which class a method belongs to | Only import explicitly when it improves readability |

## 31. Self-Check Questions and Answers

**Question 1.** Does `public class Utils { public static int add(...); }` block `new Utils()`?

**Answer:** No. If no constructor is declared, the compiler provides a default constructor with corresponding access, so for an ordinary public class an instance can be created.

**Question 2.** Why does a private constructor not stop `Utils.add(...)` from working?

**Answer:** A static method is called through the type; it does not need an object created by a constructor.

**Question 3.** Is `private void Utils() { }` a private constructor?

**Answer:** No. Because it has `void`, it is a method, and a default constructor can still exist.

**Question 4.** Does `final class Utils` with a public constructor allow `new Utils()`?

**Answer:** Yes. `final` forbids subclassing, not creating instances.

**Question 5.** If a private constructor has an empty body, can code outside in an unrelated class create an object?

**Answer:** No, under normal Java access rules. Code within the class/nest that has access can still call it; an empty body does not throw an error by itself.

**Question 6.** Is a private constructor required to `throw new AssertionError(...)`?

**Answer:** No. This is optional for catching unexpected calls from code that has access to the constructor.

**Question 7.** Should a utility class hold multiple per-user mutable static fields?

**Answer:** Usually no. Values that vary by user/session/tenant should reside in an object/service or parameters with a clear lifecycle.

**Question 8.** Is `public static final List<String> DATA = new ArrayList<>();` immutable?

**Answer:** No. The field reference is final, but the list object itself is still mutable and can be modified through an alias.

**Question 9.** Does the `normalize(String)` method have to be static?

**Answer:** If it does not depend on instance state and has a clear input-processing contract, a static utility is a natural choice; it is not an absolute requirement of the language.

**Question 10.** Why is a utility class different from a singleton?

**Answer:** A utility needs no instance; a singleton actively manages and provides one instance.

**Question 11.** Can you use a private constructor to create `UserId.of("A")` while UserId is still a value object?

**Answer:** Yes. `of` is a static factory, while UserId instances carry their own values; it is not necessarily a utility class.

**Question 12.** Can a static utility accept a mutable object and modify it?

**Answer:** Yes, if the implementation performs a valid mutation. `static` does not guarantee purity or freedom from side effects.

**Question 13.** Does `package-private final class InternalUtils` need to be public?

**Answer:** No, if only classes in the same package need access. Its constructor can still be private.

**Question 14.** Why is `Math.max` a good example of a static API?

**Answer:** The result is computed from the arguments; no specific `Math` receiver object is needed.

**Question 15.** If a unit test wants to swap the implementation per call while a static utility accesses the network directly, what should you consider?

**Answer:** Extract the dependency into an interface/service, inject the client/config, or pass appropriate parameters. Do not hastily use mutable static globals as test configuration.

**Question 16.** Can a private nested utility class be used by its outer class?

**Answer:** Yes. Enclosing classes/nestmates have the appropriate private access permissions according to Java.

**Question 17.** Can a static utility use a generic method?

**Answer:** Yes. It can declare its own `static <T> ...` type parameter on the method without needing an instance.

**Question 18.** Does having a private constructor guarantee that the class will never be initialized at runtime?

**Answer:** No. Class initialization and static method invocation can still occur. A private constructor restricts instance creation via access control; it does not prevent the class from being loaded or statically initialized.

## 32. Checklist When Reviewing a Utility Class

- [ ] Does the class name clearly indicate the functional group and avoid overly generic `Utils`?
- [ ] Do the methods genuinely need neither receiver state nor identity?
- [ ] Are there no unnecessary instance fields?
- [ ] Is the constructor declared `private` **with no return type**?
- [ ] Have you checked whether any public/protected/package-private constructor was accidentally left exposed?
- [ ] Can the class be marked `final` if there is no subclassing contract?
- [ ] Are static methods called in the form `ClassName.method(...)`?
- [ ] Are internal helper methods kept `private static` when appropriate?
- [ ] Are public classes/methods exposed only when clients outside the package actually need them?
- [ ] Does the static API describe its null policy, exceptions, range/overflow, and side effects?
- [ ] Are mutable input arrays/lists being modified unintentionally?
- [ ] Are `static final` constants genuinely immutable in meaning, especially with referenced objects?
- [ ] Are there any static mutable fields causing test contamination or concurrency issues?
- [ ] Is a static utility class being confused with a singleton, factory, or stateful service?
- [ ] If calling a library/framework, is dependency injection, a lifecycle, or overriding needed instead of a static API?
- [ ] Is there a `javac`/`java` example confirming the static API works without `new Utils()`?
- [ ] If processing strings/identifiers, have locale, Unicode, and normalization contracts been checked?
- [ ] If generics/static imports/method references are used, are the syntax and access scopes correct?
- [ ] When refactoring, is the public API kept stable and are implementation helpers kept from being exposed?

---

**Remember:** A utility class is used to group **class-level operations that do not require a separate receiver object**. Merely declaring static methods **is not enough to block object creation**, because Java can generate a default constructor. A clear pattern is usually **`final class` + `private` constructor + static API**: the private constructor restricts external `new` calls, `final` forbids subclassing, and static methods are called via the class name. Do not confuse this pattern with a singleton, do not abuse mutable static fields, and choose an instance service/interface when the problem requires state, a lifecycle, or polymorphism.
