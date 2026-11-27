# Replacing Cast Chains in Data Processing with `instanceof` Patterns (Java 17)

> **Topic:** Java 17  
> **Chapter:** Pattern `instanceof`  
> **Goal:** Convert manual type-check-then-cast code to **pattern matching for `instanceof`**, use pattern variables within valid scopes in data-processing branches, and avoid syntax that is not yet stable in Java 17.

## 1. Scenario: Why Do Cast Chains Become Hard to Read?

In Java, a method accepting `Object`, an interface, or a supertype can receive many different actual objects. For example, a message-processing system might receive an order-created event, a processing error, or a text note. Before accessing properties specific to each kind, traditional Java code usually had to do two things:

1. Check whether the object is of the desired kind using `instanceof`.
2. Explicitly cast with `(Type) object` before reading the data.

Example before applying patterns:

```java
static String describe(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "Text: " + text.strip();
    } else if (value instanceof Integer) {
        Integer number = (Integer) value;
        return "Integer: " + number.intValue();
    } else {
        return "Unsupported";
    }
}
```

The lines `String text = (String) value` and `Integer number = (Integer) value` repeat type information immediately after checking it. With multiple types, multiple `if` levels, and many cast sites, the code grows longer, becomes harder to follow, and risks misreading variables or casting to the wrong type if the condition is edited without updating the body.

**Pattern matching for `instanceof`** directly addresses this case with the syntax:

```java
if (expression instanceof Type variableName) {
    // variableName already has type Type here.
}
```

Since Java 16 (JEP 394), this has been a standard feature and is **stable in Java 17**. You do not need to enable `--enable-preview` to use type patterns with `instanceof`.

## 2. Basic Conversion: Checking Type and Obtaining a Variable in One Expression

### 2.1. Before and after

**Before — separate check and cast:**

```java
Object input = "  Java 17  ";

if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.strip());
}
```

**After — type pattern:**

```java
Object input = "  Java 17  ";

if (input instanceof String text) {
    System.out.println(text.strip());
}
```

The expression `input instanceof String text` serves two purposes:

- Checks whether the runtime value of `input` is compatible with `String`.
- When matched, creates and assigns the **pattern variable** `text` of type `String`, usable wherever the compiler guarantees the check succeeded.

In this example, `text` is used directly to call `strip()`. You do not need—and should not write—`(String) input` inside the `if` body.

### 2.2. `instanceof` before and after still performs type checking

| Characteristic | Traditional `instanceof String` | Pattern `instanceof String text` |
|---|---|---|
| Checks runtime type | Yes | Yes |
| Returns boolean result | Yes | Yes |
| Automatically creates a narrowed reference variable | No | Yes, when the pattern matches |
| Requires manual cast to call subtype APIs | Usually yes | Not within `text`'s scope |
| Does `null` match? | No | No |
| Usable in Java 17 without preview enabled? | Yes | Yes |

**Note:** This is a **type pattern**. Syntax for checking and extracting record components, such as `instanceof Point(int x, int y)`, is **not part of stable Java 17**; record patterns were finalized in Java 21.

### 2.3. Benefit when the source expression is complex

With `instanceof` patterns, you do not need to repeat the source expression in a cast:

```java
static void process(Object[] items, int index) {
    if (items[index] instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
```

This is particularly helpful when the value comes from a method call, array element, or intermediate data layer. Still, when reading from a source with side effects, it is good practice to extract the value into a variable first so the program stays easy to trace:

```java
Object item = queue.poll();
if (item instanceof String text) {
    System.out.println(text);
}
```

## 3. Converting an Entire `if / else if` Chain That Uses Casts

Suppose a processor receives `OrderCreated` and `ProcessingError` objects:

```java
record OrderCreated(String orderId, int quantity) { }
record ProcessingError(String code, String message) { }
```

**Old code:**

```java
static String describe(Object event) {
    if (event instanceof OrderCreated) {
        OrderCreated created = (OrderCreated) event;
        return "Order " + created.orderId()
                + " has " + created.quantity() + " items";
    } else if (event instanceof ProcessingError) {
        ProcessingError error = (ProcessingError) event;
        return "Error " + error.code() + ": " + error.message();
    } else if (event instanceof String) {
        String note = (String) event;
        return "Note: " + note.strip();
    }
    return "Unrecognized data";
}
```

**Code after replacing with patterns:**

```java
static String describe(Object event) {
    if (event instanceof OrderCreated created) {
        return "Order " + created.orderId()
                + " has " + created.quantity() + " items";
    } else if (event instanceof ProcessingError error) {
        return "Error " + error.code() + ": " + error.message();
    } else if (event instanceof String note) {
        return "Note: " + note.strip();
    }
    return "Unrecognized data";
}
```

Each branch merges **type check + typed variable declaration** onto one line. As a result, the data-processing code focuses more on business rules than on cast statements.

There is no need to alter the `if / else if` structure during refactoring. What matters is that each pattern variable has a descriptive name and is used only where the type check succeeded.

## 4. Complete Example Runnable with Java 17

Create a file named `DataProcessingDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class DataProcessingDemo {

    record OrderCreated(String orderId, int quantity) {
        OrderCreated {
            Objects.requireNonNull(orderId, "orderId");
            if (orderId.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order data");
            }
        }
    }

    record ProcessingError(String code, String message) {
        ProcessingError {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
        }
    }

    static String describe(Object value) {
        if (value == null) {
            return "Null data";
        }

        if (value instanceof OrderCreated created) {
            return "Created order " + created.orderId()
                    + " x " + created.quantity();
        }

        if (value instanceof ProcessingError error) {
            return "Error " + error.code() + ": " + error.message();
        }

        // Combine type pattern with business checks.
        if (value instanceof String note && !note.isBlank()) {
            return "Note: " + note.strip();
        }

        // Recognize list type without manual casting.
        if (value instanceof List<?> items) {
            return "List: " + items.size() + " elements";
        }

        return "Unsupported: " + value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Object[] inputs = {
                new OrderCreated("ORD-100", 3),
                new ProcessingError("OUT_OF_STOCK", "Out of stock"),
                "  priority  ",
                List.of("A", "B"),
                42,
                null
        };

        for (Object input : inputs) {
            System.out.println(describe(input));
        }
    }
}
```

Compile and run:

```bash
javac --release 17 DataProcessingDemo.java
java DataProcessingDemo
```

Expected output:

```text
Created order ORD-100 x 3
Error OUT_OF_STOCK: Out of stock
Note: priority
List: 2 elements
Unsupported: Integer
Null data
```

Key takeaways from the example:

1. `value` has declared type `Object` yet can hold different runtime values.
2. Each matched pattern branch gets a properly typed variable: `created`, `error`, `note`, or `items`.
3. `created.orderId()` and `error.message()` are `record` accessors, not a new record-pattern syntax.
4. `value instanceof String note && !note.isBlank()` only calls `note.isBlank()` when the data is actually a `String`.
5. `value instanceof List<?> items` keeps generic type checking safe without an unchecked `(List<String>)` cast.
6. Checking `value == null` distinguishes missing data from other data types. `instanceof` itself returns `false` when the value is `null`.

## 5. The Most Important Rule: Variable Scope Depends on Control Flow

Java 17 determines the scope of a **pattern variable** by the locations where the compiler is certain the pattern matched. This is commonly called **flow scoping**.

### 5.1. The variable exists inside the matching `if` branch

```java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // Valid
    } else {
        System.out.println("Not a string");
        // System.out.println(text); // WRONG: text is not in scope here.
    }

    // System.out.println(text); // WRONG: the if branch may not have matched.
}
```

If `instanceof` returns `false`, there is no guarantee `text` was assigned, so it cannot be used in the `else` branch or arbitrarily after the `if`.

### 5.2. Use `&&` to check additional conditions on narrowed data

```java
static boolean isValidCode(Object input) {
    return input instanceof String code
            && !code.isBlank()
            && code.startsWith("ORD-");
}
```

The `&&` operator evaluates from left to right and stops on `false`. Thus, Java guarantees `code` is assigned when checking `!code.isBlank()` and `code.startsWith(...)`.

This is one way to **reduce deep `if` nesting** while keeping conditions clear.

**Before:**

```java
if (input instanceof String) {
    String code = (String) input;
    if (!code.isBlank()) {
        if (code.startsWith("ORD-")) {
            System.out.println("Valid order code");
        }
    }
}
```

**After:**

```java
if (input instanceof String code
        && !code.isBlank()
        && code.startsWith("ORD-")) {
    System.out.println("Valid order code");
}
```

### 5.3. Do not arbitrarily use a pattern variable on the right-hand side of `||`

**Invalid** example:

```java
// WRONG: if the left-hand side is false, text has no value yet.
// if (input instanceof String text || text.isBlank()) {
//     System.out.println("...");
// }
```

With `||`, the right-hand side is evaluated when the left-hand side is **false**. At that moment, `input instanceof String text` did not match, so `text` is unavailable.

When you need an exclusion condition, write clear branches:

```java
static String readNonBlankString(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("Need a string");
    }
    if (text.isBlank()) {
        throw new IllegalArgumentException("String must not be blank");
    }
    return text.strip();
}
```

Or write a combined condition using negation and `||`:

```java
static String readName(Object input) {
    if (!(input instanceof String name) || name.isBlank()) {
        throw new IllegalArgumentException("Name must be a non-blank string");
    }
    return name.strip();
}
```

In the second example, `name.isBlank()` is only evaluated when `!(input instanceof String name)` is `false`, meaning the pattern **has** matched. This is a rule about **control flow**, not a simplistic rule saying "never use `||` with patterns."

### 5.4. Guard clauses and variable scope after early-exit branches

A very useful way to refactor input handling is **check the type and exit early**:

```java
static int parseLength(Object input) {
    if (!(input instanceof String text)) {
        throw new IllegalArgumentException("String required");
    }

    // By this point, Java knows for sure text is a String.
    return text.strip().length();
}
```

Because the wrong-type branch always terminates with `throw`, if execution continues after `if`, the check must have succeeded. Java allows using `text` in the code that follows.

Similarly, `return` or `continue` can be used when appropriate:

```java
static void printUppercaseStrings(List<?> values) {
    for (Object value : values) {
        if (!(value instanceof String text)) {
            continue;
        }
        System.out.println(text.toUpperCase());
    }
}
```

This often produces more readable code than wrapping the entire processing body in multiple nested `if` blocks.

### 5.5. Pattern variables can appear in conditional expressions

```java
static String summary(Object input) {
    return input instanceof String text
            ? "Length: " + text.length()
            : "Not a string";
}
```

Variable `text` is in scope in the result branch when `instanceof` is `true`. You cannot arbitrarily use `text` in the `false` branch.

## 6. Using Patterns to Clean Up `Object` and `Map<?, ?>` Data

A common source of repeated casts is flexible data: configuration read from libraries, internal events, maps holding heterogeneous values, or data at integration boundaries. In those cases, patterns can check **each value** before use.

### 6.1. Example before replacing casts

```java
static int readQuantity(Object raw) {
    if (!(raw instanceof java.util.Map)) {
        throw new IllegalArgumentException("Must be a Map");
    }
    java.util.Map<?, ?> fields = (java.util.Map<?, ?>) raw;

    Object quantity = fields.get("quantity");
    if (!(quantity instanceof Integer)) {
        throw new IllegalArgumentException("quantity must be an Integer");
    }

    Integer number = (Integer) quantity;
    return number.intValue();
}
```

The code requires two cast sites, even though each site is already guarded by an `instanceof` check.

### 6.2. Refactoring with patterns and guard clauses

```java
import java.util.Map;

public class MapDataDemo {

    static int readQuantity(Object raw) {
        if (!(raw instanceof Map<?, ?> fields)) {
            throw new IllegalArgumentException("Must be a Map");
        }

        Object rawQuantity = fields.get("quantity");
        if (!(rawQuantity instanceof Integer quantity)) {
            throw new IllegalArgumentException("quantity must be an Integer");
        }

        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must not be negative");
        }

        return quantity;
    }

    public static void main(String[] args) {
        Object valid = Map.of("quantity", 5, "unit", "items");
        System.out.println(readQuantity(valid)); // 5
    }
}
```

Compile:

```bash
javac --release 17 MapDataDemo.java
java MapDataDemo
```

**Things to understand:**

- `Map<?, ?> fields` checks that the data is a `Map`, without asserting the types of each key or value inside. Using the `?` wildcard is key to avoiding an unchecked generic cast.
- `fields.get("quantity")` returns `Object`. The second pattern ensures it is genuinely an `Integer` before use.
- When a value does not match, the method fails intentionally instead of casting blindly and producing a confusing `ClassCastException`.
- This example explicitly requires `Integer`. A JSON data source might deserialize numbers as `Long`, `Double`, or `BigDecimal` depending on the library and configuration; determine the input schema before choosing a pattern. Do not assume every numeric value is an `Integer`.

Pattern matching **is not an automatic validator for an entire `Map`**, nor does it replace business validation. For data with a stable structure, convert it early to a strongly typed DTO/record and process that type instead.

## 7. Generics: Why Use `List<?>` Instead of `List<String>` in Patterns?

Java uses **type erasure** for much of its generic type information at runtime. Therefore, you cannot directly check a non-reifiable parameterized type as below:

```java
Object raw = List.of("A", "B");

// WRONG: cannot check List<String> using instanceof.
// if (raw instanceof List<String> names) {
//     ...
// }
```

The valid approach in Java 17 is checking the collection type with a wildcard, then checking each element:

```java
import java.util.ArrayList;
import java.util.List;

public class NameListDemo {
    static List<String> extractNonBlankNames(Object raw) {
        List<String> result = new ArrayList<>();

        if (!(raw instanceof List<?> items)) {
            return result;
        }

        for (Object item : items) {
            if (item instanceof String name && !name.isBlank()) {
                result.add(name.strip());
            }
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        Object values = List.of("An", 17, "  Bình  ", "");
        System.out.println(extractNonBlankNames(values)); // [An, Bình]
    }
}
```

In this example, the source list may contain multiple kinds of data. There is no `(List<String>) raw` cast; each element only enters the result list when it is genuinely a `String`.

If the business requirement is that **every** element must be a string, do not silently skip wrong-typed elements. Instead, fail with a clear error:

```java
static List<String> requireStrings(Object raw) {
    if (!(raw instanceof List<?> values)) {
        throw new IllegalArgumentException("Need a List");
    }

    List<String> names = new java.util.ArrayList<>();
    for (Object value : values) {
        if (!(value instanceof String name)) {
            throw new IllegalArgumentException("List contains a non-String element");
        }
        names.add(name);
    }
    return List.copyOf(names);
}
```

The choice between **filtering** and **rejecting** wrong-typed data is a business decision; patterns simply make the check clearer and safer.

## 8. Combining `instanceof` Patterns with Records and Sealed Interfaces

Java 17 has stable `record` and `sealed interface` support. You can use records as data variants of a sealed interface and handle them with `instanceof` patterns.

```java
public class ResultDemo {
    sealed interface Result permits Success, Failure { }

    record Success(String value) implements Result { }
    record Failure(String code, String message) implements Result { }

    static String toMessage(Result result) {
        if (result instanceof Success success) {
            return "Success: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Error " + failure.code() + ": " + failure.message();
        }
        throw new IllegalStateException("Unhandled Result type");
    }

    public static void main(String[] args) {
        System.out.println(toMessage(new Success("OK")));
        System.out.println(toMessage(new Failure("E-1", "Rejected")));
    }
}
```

In this example:

- `sealed interface Result` restricts direct implementations to `Success` and `Failure`.
- `record Success` and `record Failure` describe the data for each variant.
- `instanceof Success success` checks the type and allows calling `success.value()`.
- There is no direct "record deconstruction" in the pattern. Java 17 requires accessing components via accessors like `value()`, `code()`, and `message()`.

**Important:** With `if` chains in Java 17, the compiler **does not automatically verify exhaustiveness across all variants** of a sealed interface. If `Pending` is added to `permits` later and you forget to update `toMessage`, the method could reach the exception-throwing fallback at runtime. When changing the type set, review every branching point and add appropriate tests. If the behavior is each variant's responsibility, you can put a shared method on the interface and use polymorphism to require every record to provide an implementation.

### 8.1. Do not confuse with pattern matching for `switch`

The following syntax looks very concise:

```java
// Not stable syntax usable with --release 17:
//
// return switch (result) {
//     case Success success -> success.value();
//     case Failure failure -> failure.message();
// };
```

In **Java 17**, pattern matching for `switch` is a **preview** feature (JEP 406). It was only finalized as a standard feature in Java 21 (JEP 441). For Java 17 lessons, use `instanceof` patterns in `if`, `else if`, and guard clauses; do not put preview syntax into examples meant for normal compilation.

### 8.2. Do not confuse with record patterns

```java
record Point(int x, int y) { }

static int sum(Object value) {
    if (value instanceof Point point) {
        return point.x() + point.y(); // Valid on Java 17
    }
    return 0;
}
```

Syntax like `value instanceof Point(int x, int y)` is **not** an alternative available in Java 17. Record patterns were finalized in Java 21 (JEP 440).

## 9. Pitfalls When Refactoring Type-Check Chains

### 9.1. `null` does not match a type pattern

```java
Object value = null;

System.out.println(value instanceof String);       // false
System.out.println(value instanceof String text);  // false
```

There is no need to write `value != null && value instanceof String text` just to prevent `NullPointerException` in the `instanceof` check itself. However, if `null` carries a distinct meaning (missing data, absent field), handle it explicitly when needed.

### 9.2. Check specific subtypes before broader supertypes

```java
static String classify(Object input) {
    if (input instanceof Integer number) {
        return "Integer: " + number;
    }
    if (input instanceof Number number) {
        return "Number: " + number;
    }
    return "Other";
}
```

An `Integer` is also a `Number`. If the `Number` branch comes first, the `Integer` branch below will not handle `Integer` objects. This is the same **rule-ordering** concern that existed in traditional `if / else if` chains; patterns do not automatically prioritize types.

### 9.3. Do not use a pattern when the type is already known at compile time

Example:

```java
String name = "Lan";

// WRONG in Java 17: checking String against a String pattern is pointless.
// if (name instanceof String text) {
//     System.out.println(text.length());
// }

System.out.println(name.length()); // Correct and simpler
```

When the input expression's type is already a subtype of the pattern type, checking provides no new information and the Java 17 compiler rejects such patterns. Pattern matching is useful when **the static type is broader** than the needed type, such as `Object`, `Number`, or a parent interface.

### 9.4. Cannot check non-reifiable generic type arguments

```java
Object input = List.of(1, 2, 3);

// WRONG: instanceof List<Integer> numbers
if (input instanceof List<?> numbers) {
    System.out.println("Has " + numbers.size() + " elements");
}
```

Check each element next if you need to guarantee the exact element type. A manual cast `(List<Integer>) input` can produce an unchecked warning and does not prove the elements are actually `Integer`.

### 9.5. Do not assume a pattern variable is usable outside all branches

```java
static int textLength(Object input) {
    if (input instanceof String text) {
        return text.length();
    }

    // Cannot use text here: the pattern might fail.
    return 0;
}
```

Conversely, if the negated branch **terminates execution** via `return` or `throw`, the variable can be used after `if`, as shown in section 5.4.

### 9.6. Pattern variables are not automatically `final`

In Java 17, a pattern variable is not implicitly `final`:

```java
static void printTrimmed(Object input) {
    if (input instanceof String text) {
        text = text.strip(); // Valid in Java 17
        System.out.println(text);
    }
}
```

In many cases, it is still better to **keep the pattern variable to represent the matched object** and create another local variable when a transformation has its own meaning:

```java
if (input instanceof String text) {
    String normalized = text.strip();
    System.out.println(normalized);
}
```

That approach keeps raw data separate from normalized data, especially in multi-step data-processing code.

### 9.7. Avoid variable names conflicting with variables already in scope

Pattern variables still follow local variable scoping and naming collision rules:

```java
static void show(Object value) {
    String text = "fallback";

    // WRONG: cannot declare a pattern variable with the same name as local text
    // when the two scopes overlap.
    // if (value instanceof String text) {
    //     System.out.println(text);
    // }

    if (value instanceof String actualText) {
        System.out.println(actualText);
    } else {
        System.out.println(text);
    }
}
```

### 9.8. Pattern matching does not replace business value validation

```java
if (raw instanceof String email) {
    // Only know raw is a String; do not know whether it is a valid email yet.
}
```

Similarly, `raw instanceof Integer count` does not guarantee `count >= 0`. Distinguish between:

- **Type checking:** is the value of the right data type?
- **Value validation:** is the string valid, is the number within range, and does the data satisfy business rules?

For input from users or external systems, both layers of checking are required.

## 10. Step-by-Step Process for Refactoring a Multi-Type Data-Processing Method

When encountering a long method full of `instanceof` checks, casts, and nested `if` blocks, refactor step by step:

1. **Identify the input's static type:** usually `Object`, an interface, or a superclass. Note the runtime types the method can encounter.
2. **Find repeated pairs:** `value instanceof X` right before `X x = (X) value`. Replace with `value instanceof X x`.
3. **Preserve branch semantics:** change one branch's syntax at a time; do not reorder types or change fallbacks yet.
4. **Move safe secondary conditions into `&&`:** for example, `value instanceof String text && !text.isBlank()`.
5. **Use guard clauses if they reduce nesting:** `if (!(value instanceof X x)) return/throw;` and then continue processing with `x`.
6. **Remove redundant casts and clarify pattern variable names:** use `order`, `error`, `name`; avoid chains of unreadable `x`/`a` names.
7. **Evaluate design limits:** if the same branching logic is duplicated in many places or the type set changes constantly, consider polymorphism/visitor models or a clearer data structure.

### Example replacing three levels of `if` with a guard clause

**Before:**

```java
static String parseTitle(Object raw) {
    if (raw instanceof String) {
        String title = (String) raw;
        if (!title.isBlank()) {
            String normalized = title.strip();
            if (normalized.length() <= 40) {
                return normalized;
            }
        }
    }
    throw new IllegalArgumentException("Invalid title");
}
```

**After:**

```java
static String parseTitle(Object raw) {
    if (!(raw instanceof String title)) {
        throw new IllegalArgumentException("Title must be a string");
    }

    String normalized = title.strip();
    if (normalized.isEmpty() || normalized.length() > 40) {
        throw new IllegalArgumentException("Invalid title");
    }
    return normalized;
}
```

The new version keeps the type check explicit, eliminates the cast, and separates normalization from validation. When applying this in a real project, check whether changing exception messages or whitespace-handling behavior affects existing APIs or callers.

## 11. When to Use Patterns, and When to Use Polymorphism?

Pattern matching fits **data boundaries** or situations requiring behavior selection based on runtime value types:

- Reading heterogeneous data from `Map<?, ?>` or `List<?>`.
- Handling multiple message/event types through a shared input API.
- Mapping variants of a sealed hierarchy to display formats, DTOs, or reports.
- Checking an object at a boundary between two layers with known types.

However, if code must repeatedly ask "what type is this?" to perform the same behavior, polymorphism is usually worth considering:

**Repeated branching on the caller side:**

```java
interface Shape { }
record Rectangle(double width, double height) implements Shape { }
record Circle(double radius) implements Shape { }

static double area(Shape shape) {
    if (shape instanceof Rectangle rect) {
        return rect.width() * rect.height();
    }
    if (shape instanceof Circle circle) {
        return Math.PI * circle.radius() * circle.radius();
    }
    throw new IllegalArgumentException("Unsupported Shape");
}
```

**Or placing shared behavior on the parent type:**

```java
interface Shape {
    double area();
}

record Rectangle(double width, double height) implements Shape {
    public double area() {
        return width * height;
    }
}

record Circle(double radius) implements Shape {
    public double area() {
        return Math.PI * radius * radius;
    }
}

static double area(Shape shape) {
    return shape.area();
}
```

The two snippets above are **two independent design approaches**; do not put definitions with the same names into a single file. The second approach is usually better when calculating area is a core behavior of each shape and you want each class to define it. Meanwhile, an external converter serving multiple output formats may make more sense using patterns in one centralized place.

## 12. Practice Exercises

### Exercise 1 — Remove repeated casts

Refactor the following Java 17 snippet using `instanceof` patterns:

```java
static String inspect(Object value) {
    if (value instanceof Long) {
        Long number = (Long) value;
        return "Long=" + number;
    } else if (value instanceof String) {
        String text = (String) value;
        return "String=" + text.strip();
    }
    return "Unsupported";
}
```

**Reference solution:**

```java
static String inspect(Object value) {
    if (value instanceof Long number) {
        return "Long=" + number;
    }
    if (value instanceof String text) {
        return "String=" + text.strip();
    }
    return "Unsupported";
}
```

### Exercise 2 — Filter data by type and condition

Write the method `static List<String> normalizeCodes(List<?> rawCodes)`:

- Keep only elements of type `String`.
- Discard empty or whitespace-only strings.
- Trim leading/trailing whitespace and convert to uppercase using `Locale.ROOT`.
- Do not use any manual casts.

**Reference solution:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

static List<String> normalizeCodes(List<?> rawCodes) {
    List<String> result = new ArrayList<>();
    for (Object value : rawCodes) {
        if (value instanceof String code && !code.isBlank()) {
            result.add(code.strip().toUpperCase(Locale.ROOT));
        }
    }
    return List.copyOf(result);
}
```

For example, `normalizeCodes(List.of(" abc ", 123, "", " xYz "))` returns the list `[ABC, XYZ]`.

### Exercise 3 — Guard clauses and dynamic `Map` data

Given input `Object raw`, require:

1. Must be a `Map<?, ?>`.
2. Key `"name"` must hold a non-blank `String`.
3. Return the name after `strip()`.
4. If any condition fails, throw `IllegalArgumentException`.

**Solution:**

```java
import java.util.Map;

static String readName(Object raw) {
    if (!(raw instanceof Map<?, ?> values)) {
        throw new IllegalArgumentException("Data must be a Map");
    }

    Object nameValue = values.get("name");
    if (!(nameValue instanceof String name) || name.isBlank()) {
        throw new IllegalArgumentException("name must be a non-blank string");
    }

    return name.strip();
}
```

### Exercise 4 — Spot the variable-scope bug

Examine the two snippets below:

```java
// A
// if (value instanceof String text || text.isBlank()) { ... }

// B
// if (!(value instanceof String text)) return;
// System.out.println(text.length());
```

**Question:** Which snippet is valid regarding pattern variable scope in Java 17, and why?

**Answer:** A is invalid because `||` can evaluate the right-hand side after the type check fails, leaving `text` unassigned. B is valid if inside a method with a return type compatible with `return;` (such as a `void` method): once past the `if`, the negated condition must be false, so `text` definitely matched `String`.

### Exercise 5 — Extend variant handling

Suppose `sealed interface Result permits Success, Failure` already has two records. Add `Pending(String ticketId)` and update `toMessage`.

**Question:** Does Java 17 automatically report a compile error on the old `if` chain for missing the `Pending` branch?

**Answer:** No. After adding `Pending` to `permits`, the old `if/else if` code still compiles, but will hit the fallback when receiving `Pending`. You must proactively update the handler method and related tests.

## 13. Key Takeaways

| Scenario | Java 17 usage |
|---|---|
| Check type then immediately cast | `if (raw instanceof String text)` |
| Add a condition based on the subtype | `if (raw instanceof String text && !text.isBlank())` |
| Continue processing after rejecting wrong type | `if (!(raw instanceof String text)) throw ...;` |
| Generic data with unknown component type | `raw instanceof List<?> list`, check elements separately |
| Record data | `raw instanceof RecordType record`, use `record.component()` |
| `null` data | `instanceof` returns `false`; handle `null` separately if needed |
| Need multi-type branching | `if/else if` chain with patterns, specific branches before broad ones |
| Want to use `case Type variable ->` | That is preview pattern switch in Java 17; do not use in stable Java 17 code |
| Want to deconstruct `RecordType(var a, var b)` | Record patterns belong to Java 21; Java 17 uses accessors |
| Business logic requires value validation | Patterns only check types; validation is still required |

## 14. Official Documentation

- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): proposal finalized in Java 16, stable for use in Java 17.
- [Oracle Java 17 — Pattern Matching](https://docs.oracle.com/en/java/javase/17/language/pattern-matching.html): official guide with examples applying type patterns when working with objects.
- [Java Language Specification 17 — `15.20.2 The `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): rules for type checking and pattern testing.
- [Java Language Specification 17 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): flow-based scope of pattern variables.
- [Java Language Specification 17 — `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): definition of type patterns in Java 17.
- [JEP 406 — Pattern Matching for `switch` (Preview in Java 17)](https://openjdk.org/jeps/406) and [JEP 441 — Pattern Matching for `switch` (Java 21)](https://openjdk.org/jeps/441): distinguishing Java 17 preview syntax from stable syntax in later Java releases.
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440): reference to avoid confusing accessing record components in Java 17 with deconstruction in newer releases.

**Conclusion:** When processing data with multiple runtime types, replacing `instanceof` + `(Type) value` chains with **`instanceof Type variable`** reduces cast boilerplate and states type constraints right at the condition. Combine flow scoping, `&&`, guard clauses, and schema/value checks to process data more clearly and safely on Java 17 without relying on preview features.
