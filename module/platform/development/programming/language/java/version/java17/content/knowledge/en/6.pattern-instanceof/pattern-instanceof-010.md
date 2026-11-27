# Distinguishing Standard `instanceof` from Preview Pattern `switch` in Java 17

Java 17 has two syntax groups that are easily confused when processing data by runtime type: **pattern matching for `instanceof`**, which is already a standard feature, and **pattern matching for `switch`**, which was in *preview* at the time. Both can check a type and bind a variable name to the matched value; the crucial differences lie in **stability level, how to compile and run, syntax scope, and how missing cases are handled**.

For projects that need long-term maintenance on **Java 17**, use stable `instanceof` patterns. If you encounter `switch` examples with `case String s -> ...` or `case null -> ...`, understand that this is not stable Java 17 `switch` syntax. The practice sections below present both so learners can tell them apart accurately; the preview parts are kept separate and used solely to illustrate the language's evolution.

## 1. Feature Status in Java 17

| Feature | Syntax example | Status in JDK 17 | Requires `--enable-preview`? |
| --- | --- | --- | --- |
| Regular `instanceof` type check | `value instanceof String` | Standard, long-standing | No |
| Pattern matching for `instanceof` | `value instanceof String text` | **Standard**, since Java 16 (JEP 394) | **No** |
| `switch` on `int`, `String`, `enum` constants | `case "OK" -> ...` | Standard; `switch` expressions and arrow labels stable since Java 14 | No |
| Pattern matching for `switch` | `case String text -> ...` | **First preview in Java 17** (JEP 406) | **Yes** |
| `case null` in pattern `switch` | `case null -> ...` | Part of the preview extension in Java 17 | **Yes** |
| Guarded pattern in `switch` | `case String s && s.length() > 3 -> ...` | Preview in Java 17 | **Yes** |

The two keywords `instanceof` and `switch` are long-standing parts of Java. What matters here is which release integrated **patterns** into each one and what its release status is.

Relevant milestones:

- **Java 16:** Pattern matching for `instanceof` was standardized by **JEP 394**.
- **Java 17:** Pattern matching for `switch` appeared in its **first preview**, under **JEP 406**.
- **Java 21:** Pattern matching for `switch` was officially standardized by **JEP 441**, after subsequent previews and syntax adjustments in intermediate Java releases.

Therefore, do not take a `switch` pattern example written for Java 21 and assume it runs unmodified on Java 17.

## 2. What Problem Does Standard `instanceof` Pattern Matching Solve?

Before pattern variables, the common approach was checking and casting manually:

~~~java
static String describe(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "Length: " + text.length();
    }
    return "Not a string";
}
~~~

With the same meaning in Java 17:

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "Length: " + text.length();
    }
    return "Not a string";
}
~~~

In the expression `value instanceof String text`:

1. `value` is the value to check.
2. `String` is the type to match.
3. `text` is the **pattern variable**, assigned the matched value with type `String`.
4. If the condition is `true`, the compiler knows `text` is safe to use wherever control flow guarantees the pattern matched.

There is no need to write the `(String) value` cast again. This reduces duplication and keeps the check close to where the data is used.

### 2.1. Java 17 example without preview

Create the file **`StableInstanceofDemo.java`**:

~~~java
public final class StableInstanceofDemo {

    private StableInstanceofDemo() {
    }

    static String describe(Object value) {
        if (value == null) {
            return "No data";
        }

        if (value instanceof String text && !text.isBlank()) {
            return "String: " + text.strip();
        }

        if (value instanceof Integer number) {
            return "Integer: " + number;
        }

        if (value instanceof String) {
            return "Blank string";
        }

        return "Other type: " + value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Object[] samples = {"  Java 17  ", 42, "   ", 3.14, null};
        for (Object sample : samples) {
            System.out.println(describe(sample));
        }
    }
}
~~~

Compile and run with **JDK 17**:

~~~bash
javac --release 17 -encoding UTF-8 StableInstanceofDemo.java
java StableInstanceofDemo
~~~

Expected output:

~~~text
String: Java 17
Integer: 42
Blank string
Other type: Double
No data
~~~

Neither command uses a preview flag. This is an appropriate example for practice code or stable Java 17 application code.

## 3. Scope of a Pattern Variable: Flow Scoping

Variable `text` in `value instanceof String text` is not valid everywhere after it appears. Java uses **flow scoping**: a pattern variable can be referenced where the compiler determines the pattern has definitely matched.

### 3.1. Inside the true `if` branch

~~~java
void print(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip()); // Valid: matched String.
    }

    // Cannot use text here by default:
    // the instanceof expression may have returned false.
}
~~~

### 3.2. In expressions combined with `&&`

~~~java
static boolean isLongText(Object value) {
    return value instanceof String text && text.length() >= 10;
}
~~~

If the left-hand part is `false`, `&&` does not evaluate the right-hand part. If the right-hand part runs, `text` is already a valid `String`.

Conversely, this is a compile error:

~~~java
// Wrong: the right-hand side of || can run when the pattern did not match.
// if (value instanceof String text || text.isBlank()) {
//     ...
// }
~~~

Because with `||`, the right-hand side is evaluated when the left-hand side is `false`; at that time `text` is not guaranteed to be assigned.

### 3.3. After an early-exit branch

~~~java
static int lengthOfText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Must pass a String");
    }

    return text.length(); // Valid: the non-matching branch threw an exception.
}
~~~

This is a useful **guard clause** pattern in validation: return or throw an exception immediately when the type does not match, then use the pattern variable in the success flow.

### 3.4. Checking `null` values

~~~java
Object value = null;

System.out.println(value instanceof String text); // false
~~~

When the input expression is `null`, `instanceof` returns `false`; it does not throw `NullPointerException` simply for a null input. If you want to distinguish "no data" from "another data type", handle `null` explicitly before or after the `instanceof` conditions.

### 3.5. Generic types and type erasure

Java does not allow checking a generic type argument that cannot be determined at runtime:

~~~java
Object value = java.util.List.of("A", "B");

// Invalid: List<String> cannot be fully checked at runtime.
// if (value instanceof java.util.List<String> list) {
//     ...
// }
~~~

The correct expression checks a form verifiable at runtime:

~~~java
if (value instanceof java.util.List<?> list) {
    System.out.println("Element count: " + list.size());
}
~~~

`List<?>` tells you the object is a list without proving the type of each element. If you need to guarantee all elements are `String`, check each element or validate at the data boundary.

## 4. Regular `switch` Is Still a Standard Feature in Java 17

A common misconception is seeing a `switch` with `->` arrows and concluding it is a preview feature. In fact, **switch expressions** and arrow case labels have been standard since **Java 14**.

Example of `switch` on an `enum`, completely stable in Java 17:

~~~java
public final class StableSwitchDemo {

    enum OrderStatus {
        NEW,
        PAID,
        CANCELLED
    }

    static String label(OrderStatus status) {
        return switch (status) {
            case NEW -> "New order";
            case PAID -> "Paid";
            case CANCELLED -> "Cancelled";
        };
    }

    public static void main(String[] args) {
        System.out.println(label(OrderStatus.PAID));
    }
}
~~~

Compile normally:

~~~bash
javac --release 17 -encoding UTF-8 StableSwitchDemo.java
java StableSwitchDemo
~~~

Output:

~~~text
Paid
~~~

This `switch` selects cases based on **enum constants** and returns an expression. It **does not** check the runtime type of an `Object` and does not declare a pattern variable `case String text`.

Constant labels can be used with `String` in Java 17:

~~~java
String output = switch (statusCode) {
    case "OK" -> "Success";
    case "RETRY" -> "Retry";
    default -> "Unknown";
};
~~~

The `case "OK" ->` syntax is also stable; it is **not the same** as `case String text ->`. The distinction is **constant label** vs. **type pattern label**, not the shape of the arrow.

## 5. Pattern Matching for `switch` in Java 17 Is Preview

JEP 406 extends `switch` to select branches by type and pattern constraints. In Java 17, the example below belongs to the **preview** feature:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Integer number -> "Integer: " + number;
        case String text -> "String: " + text;
        default -> "Other type";
    };
}
~~~

The two branches `case Integer number` and `case String text` declare pattern variables in each case, unlike constant-based `case` labels.

**Do not use the normal compile/run commands from section 2 to run this file**. With JDK 17, preview must be enabled in both phases.

### 5.1. Standalone preview example

Create the file **`PatternSwitchPreviewDemo.java`**:

~~~java
public final class PatternSwitchPreviewDemo {

    private PatternSwitchPreviewDemo() {
    }

    static String describe(Object value) {
        return switch (value) {
            case null -> "No data";
            case String text && text.isBlank() -> "Blank string";
            case String text -> "String: " + text.strip();
            case Integer number -> "Integer: " + number;
            default -> "Other type: " + value.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        Object[] samples = {"  Java 17  ", 42, "   ", 3.14, null};
        for (Object sample : samples) {
            System.out.println(describe(sample));
        }
    }
}
~~~

With **JDK 17**, compile:

~~~bash
javac --enable-preview --release 17 -encoding UTF-8 PatternSwitchPreviewDemo.java
~~~

And run:

~~~bash
java --enable-preview PatternSwitchPreviewDemo
~~~

Expected output:

~~~text
String: Java 17
Integer: 42
Blank string
Other type: Double
No data
~~~

The compiler may warn that the code uses preview features. This warning is intentional: the program is using syntax not yet standardized in Java 17 itself.

**The two flags have different roles:**

- `--release 17` selects the target language version and APIs.
- `--enable-preview` enables preview features of the JDK version currently compiling/running.

Setting only `--release 17` is not enough to use preview pattern `switch`. Enabling preview only at compile time while forgetting the flag at runtime also fails for class files using preview features.

### 5.2. Guards in the Java 17 preview

In the example above:

~~~java
case String text && text.isBlank() -> "Blank string";
~~~

`&& text.isBlank()` is a **guard** attached to the type pattern: the branch is selected only when the value is a `String` and the extra condition is true.

This guard syntax belongs to the **Java 17 preview**. In Java 21, pattern `switch` is standard and guards use `when`:

~~~java
// Java 21 or later; not Java 17 code:
case String text when text.isBlank() -> "Blank string";
~~~

Do not paste Java 21 `when` examples directly into Java 17 code. Conversely, do not treat the Java 17 preview `&&` guard syntax as standard for Java 21 code.

### 5.3. `case null` is also part of the preview extension

Traditional Java `switch` does not handle a `null` selector with normal constant labels: passing `null` into a traditional `switch` normally throws `NullPointerException`.

With preview pattern `switch`, JEP 406 allows:

~~~java
return switch (value) {
    case null -> "No value";
    case String text -> text;
    default -> "Value of another type";
};
~~~

This **does not mean every Java 17 `switch` supports `case null`**. The example above is still preview.

In Java 17 code without preview enabled, handle `null` before entering `switch` or use `if`:

~~~java
static String safeText(Object value) {
    if (value == null) {
        return "No value";
    }
    if (value instanceof String text) {
        return text;
    }
    return "Value of another type";
}
~~~

Note: `default` in a pattern `switch` is not a guaranteed substitute for `case null`. Without a label for null, a null value can still cause a `NullPointerException` according to `switch` rules.

## 6. Comparing the Same Requirement in Both Approaches

Suppose the requirement is to convert an `Object` value into a message:

- `null`: "No data".
- Empty or whitespace-only `String`: "Blank string".
- Other `String`: normalized with `strip()`.
- `Integer`: display the numeric value.
- Remaining types: display the data type.

**Approach A — Stable Java 17, without enabling preview:**

~~~java
static String describeStable(Object value) {
    if (value == null) {
        return "No data";
    }

    if (value instanceof String text) {
        if (text.isBlank()) {
            return "Blank string";
        }
        return "String: " + text.strip();
    }

    if (value instanceof Integer number) {
        return "Integer: " + number;
    }

    return "Other type: " + value.getClass().getSimpleName();
}
~~~

**Approach B — Java 17 preview:**

~~~java
static String describePreview(Object value) {
    return switch (value) {
        case null -> "No data";
        case String text && text.isBlank() -> "Blank string";
        case String text -> "String: " + text.strip();
        case Integer number -> "Integer: " + number;
        default -> "Other type: " + value.getClass().getSimpleName();
    };
}
~~~

In business terms, the two methods are equivalent for the specified input set. However, when choosing for a **real-world project running Java 17**, Approach A has the advantage of relying on standard Java 17 language features and working with default tooling. Approach B helps recognize the pattern `switch` concept, yet remains tied to the preview mechanism and historical syntax.

| Perspective | Standard `instanceof` pattern | Pattern `switch` in Java 17 |
| --- | --- | --- |
| Checks runtime type | Yes | Yes |
| Declares matched variable | Yes | Yes |
| Supports type-based branching | Via `if` / `else if` | Via `case Type variable` |
| Guard with extra condition | `&&` condition in `if` | Guarded pattern `&&` in `case` label |
| Null | `instanceof` yields `false`; add separate branch if desired | `case null` is in the preview extension |
| Exhaustiveness analysis | `if` chains do not automatically warn on missing variants | Some `switch` expressions can be checked for exhaustiveness on permitted types, but the pattern mechanism is still preview |
| Compiler/runtime flags | None | Required |
| Suitable for stable Java 17 code | Yes | Should not be chosen as the default foundation |
| Relationship to Java 21 | Continues working normally | Idea was standardized, with syntax changes during evolution |

## 7. Preview Pattern `switch` Has Branch-Ordering Rules

One advantage of pattern `switch` is that case labels can express specific and general type relationships. However, they also introduce **dominance** issues: an earlier case can cover all values of a subsequent case.

**Invalid** example in preview pattern `switch`:

~~~java
// Wrong: Number already matches every Integer,
// because Integer is a subtype of Number.
static String bad(Object value) {
    return switch (value) {
        case Number number -> "Number";
        case Integer integer -> "Integer"; // Dominated by the previous case.
        default -> "Other";
    };
}
~~~

The right ordering places specific patterns first:

~~~java
static String good(Object value) {
    return switch (value) {
        case Integer integer -> "Integer: " + integer;
        case Number number -> "Number: " + number;
        default -> "Other";
    };
}
~~~

Similarly, a `case Object anything` branch can dominate other type patterns for non-null values. In stable Java 17 code, when writing an `if` chain, the compiler does not automatically report a shadowed later branch under the same `switch` dominance mechanism; the author must pay attention to condition ordering.

With guards, the earlier example used:

~~~java
case String text && text.isBlank() -> "Blank string";
case String text -> "Non-blank string";
~~~

The guarded branch must precede the general `String` branch so the specialized branch gets a chance to run. If the general `String` branch were placed first, every string would match there and the later branch would no longer be useful.

## 8. `sealed` Types and Exhaustiveness of `switch`

Java 17 officially supports `sealed class` and `sealed interface`: a parent type can restrict its direct subtypes. This often goes hand in hand with the idea of **handling all valid variants**.

Business result model example:

~~~java
sealed interface LookupResult permits Found, Missing {
}

record Found(String name) implements LookupResult {
}

record Missing(int requestedId) implements LookupResult {
}
~~~

With **standard** `instanceof` patterns in Java 17:

~~~java
static String render(LookupResult result) {
    if (result instanceof Found found) {
        return "Found: " + found.name();
    }

    if (result instanceof Missing missing) {
        return "ID not found: " + missing.requestedId();
    }

    throw new IllegalStateException("Unsupported variant");
}
~~~

Even though the hierarchy currently has two variants, the `if` branches do not form an automatic proof to the compiler that the method handled everything. If `InvalidInput` is added to `permits` in the future, the method will still compile without warning about a missing branch; the fallback branch will only trigger at runtime when the new type arrives.

With **preview** pattern `switch` in Java 17, you could write:

~~~java
static String renderPreview(LookupResult result) {
    return switch (result) {
        case Found found -> "Found: " + found.name();
        case Missing missing -> "ID not found: " + missing.requestedId();
    };
}
~~~

Here, the compiler can rely on the sealed hierarchy to determine permitted subtypes and check the branches of the `switch` expression. Yet **pattern `switch` syntax in JDK 17 is still preview**; having standard `sealed` types does not automatically make pattern `switch` a standard language feature.

When adding a direct variant to the hierarchy, `switch` logic must be updated to match the new contract. This is why explicitly enumerating valid types is helpful when organizing APIs, even though stable Java 17 code usually handles them with `instanceof`.

### 8.1. `switch` expressions and the exhaustiveness requirement

A `switch` **expression** must produce a result for all valid execution paths. With a regular `enum`, all constants can be listed like in the `OrderStatus` example. With type patterns in Java 17 preview, the compiler also analyzes coverage over the input type set.

If a `switch` returns a value without covering all cases, a compile error occurs. A `default` branch is typically used with an open input type like `Object`. With a controlled sealed hierarchy, type patterns for the permitted branches can represent the entire set of outcomes.

Do not confuse the exhaustiveness of a **switch expression** with expecting every `if` chain to be checked by the compiler: those are two distinct mechanisms.

## 9. Does Pattern `instanceof` Replace Every Kind of Cast?

No. Pattern `instanceof` works well when you need to determine the **runtime type** of a reference and handle it according to that type. It does not automatically enforce every business rule or make every type conversion valid.

### 9.1. Runtime type vs. business meaning

~~~java
if (value instanceof String text) {
    // Already known to be a String.
    // Not yet known whether text is a valid email.
}
~~~

Type checking is not equivalent to content validation. You still must validate data according to business domain requirements.

### 9.2. Do not deconstruct records with Java 17 `instanceof`

A record can have components:

~~~java
record Point(int x, int y) {
}
~~~

In Java 17, the valid syntax is a **type pattern** followed by calling accessors:

~~~java
if (value instanceof Point point) {
    System.out.println(point.x() + point.y());
}
~~~

The **record pattern** syntax below is **not part of standard Java 17**:

~~~java
// Do not use in Java 17:
// if (value instanceof Point(int x, int y)) {
//     ...
// }
~~~

Record patterns appeared after Java 17 and were standardized in Java 21. Do not confuse Java 17's support for `record` with supporting record deconstruction in every pattern.

### 9.3. When the type is already known by contract

If an API already returns a concrete type, no cast or `instanceof` is needed:

~~~java
String text = service.loadText();
System.out.println(text.length());
~~~

Pattern matching has a clear role when an API receives diverse data types. Do not overuse type checks in place of interface design, polymorphism, or generics where those mechanisms express the requirement better.

## 10. Differences in Build, Runtime, and JDK Version

In Java 17, preview is a mechanism allowing experimentation with a language feature in a specific release before that feature is standardized or adjusted.

### 10.1. What do the compilation commands mean?

| Source code | Command | Expected outcome |
| --- | --- | --- |
| `if (obj instanceof String s)` | `javac --release 17 File.java` | Valid |
| `switch` on constant/enum using `->` | `javac --release 17 File.java` | Valid |
| `switch` with `case String s ->` | `javac --release 17 File.java` | Rejected because preview is not enabled |
| `switch` with `case String s ->` | `javac --enable-preview --release 17 File.java` | Compiles on JDK 17 with preview enabled |
| Class file using preview | `java --enable-preview MainClass` | Runs on the runtime matching the release compiled with preview |

Specifying `--release 17` should be used when compiling for Java 17; it enforces both language and API compatibility with the target release. For preview, ensure **the JDK actually running the compiler is also JDK 17**.

### 10.2. Why shouldn't Java 17 preview code be shipped carelessly?

Class files using preview features are specially marked by class-file version; the runtime must support that exact preview version. You cannot assume a class compiled with Java 17 preview will run on Java 18 or Java 21 merely because those versions are newer.

When an application uses preview features, you must control:

- The JDK version used to compile and run.
- The `--enable-preview` flag in builds, tests, and actual launch commands.
- IDE, CI, and deployment environment configurations.
- Plans to update source code when changing JDKs, since preview syntax and semantics can change across releases.

Therefore, in lessons or applications requiring **stable Java 17**, introducing preview `switch` syntax is meant for recognizing the difference, not recommending it as the default.

### 10.3. Be careful when copying examples from the Internet or an IDE

Three situations occur frequently:

1. **The IDE is using a newer JDK** and suggests official Java 21 `switch` pattern code; pasting it into a Java 17 project may fail to compile.
2. **Older articles use Java 17 preview** with `&&` guards; that code should not be treated as stable syntax usable across all versions.
3. **An application targets Java 17 without preview enabled in the build**; every `case Type variable` will fail even though `if (value instanceof Type variable)` works normally.

To determine the context, check `java -version`/`javac -version`, `--release` settings, or Maven/Gradle toolchains, and compare against the syntax being used.

## 11. When to Use `instanceof` Patterns vs. Polymorphism?

An `instanceof` pattern chain can suit **adapters**, **data conversion**, **parsing**, **formatters**, or situations needing classification across unrelated types:

~~~java
static String format(Object value) {
    if (value instanceof Integer n) {
        return "Number: " + n;
    }
    if (value instanceof String s) {
        return "Text: " + s;
    }
    return "Unsupported";
}
~~~

However, if classes belong to a hierarchy and each class knows how to perform the behavior itself, a regular interface may be more suitable:

~~~java
interface Message {
    String display();
}

record TextMessage(String text) implements Message {
    @Override
    public String display() {
        return text;
    }
}

record NumberMessage(int number) implements Message {
    @Override
    public String display() {
        return Integer.toString(number);
    }
}
~~~

Callers simply write:

~~~java
Message message = new TextMessage("Hello");
System.out.println(message.display());
~~~

This avoids forcing every consumer of `Message` to repeat an `instanceof` list. Choosing patterns or polymorphism depends on **who owns the behavior** and **who needs to know about the variants**: if formatting logic belongs to each type itself, polymorphism can be cleaner; if converting many types that share no interface into an external format, `instanceof` patterns are often natural.

With `sealed` hierarchies, both approaches have their place; what to avoid in Java 17 projects is accidentally introducing preview pattern `switch` syntax into code required to compile with the stable language.

## 12. Common Errors and Fixes Table

| Symptom | Cause | How to handle in Java 17 |
| --- | --- | --- |
| `case String s ->` reports "preview feature" | Using Java 17 pattern `switch` | Rewrite using `instanceof` or explicitly enable preview for experiments |
| `case "OK" ->` mistaken for preview | Confusing arrow `switch` expressions with pattern `switch` | Keep as is; this is stable syntax |
| `case String s when ...` fails to compile | That is guard syntax from a newer Java version | Use `if` with `instanceof` in stable Java 17 code |
| `if (x instanceof String s \|\| s.isEmpty())` fails | `s` is not guaranteed assigned on the right-hand side of `\|\|` | Use `&&` when logic fits or split into branches |
| Using `s` outside the `instanceof` branch scope | Pattern variables follow flow scoping | Use only on paths where the compiler knows the pattern matched |
| `instanceof List<String>` is invalid | Generic type erasure | Use `List<?>` and check elements if needed |
| Preview compiles successfully but fails at runtime | Preview not enabled at runtime or wrong JDK version | Use matching runtime and `java --enable-preview` |
| `switch` on null throws an exception | No null-handling branch | In stable Java 17, check null before switching |
| Assuming `record` automatically supports record patterns | Confusing records with record deconstruction | Use `instanceof Point p` then call `p.x()`, `p.y()` |
| Adding a sealed variant missed by `if` logic | `if` chains are not treated as exhaustive by the compiler | Update branches and handle defaults sensibly |

## 13. Practice Exercises

### Exercise 1 — Rewrite a cast as an `instanceof` pattern

Convert the following code to stable Java 17:

~~~java
if (value instanceof Number) {
    Number number = (Number) value;
    System.out.println(number.doubleValue());
}
~~~

Requirement: use a pattern variable, preserve the old behavior, do not enable preview. Then explain why the declared variable cannot be used in the branch if the type check returns `false`.

### Exercise 2 — Distinguish stable and preview `switch`

Identify which snippets compile normally with `javac --release 17` and which require preview:

~~~java
// A
String a = switch (status) {
    case "ACTIVE" -> "Active";
    default -> "Unknown";
};

// B
String b = switch (value) {
    case Integer i -> "Number " + i;
    default -> "Other";
};

// C
boolean c = value instanceof String s && s.length() > 3;
~~~

Hint: check whether the **case label** is a `String` constant or a **type pattern**. Do not look only at the arrow.

### Exercise 3 — Fix the flow scoping bug

What is wrong with the following snippet?

~~~java
// if (value instanceof String text || text.isBlank()) {
//     System.out.println("String");
// }
~~~

Rewrite the requirement "value must be a non-blank string" using `&&` and print the `strip()`ped content.

### Exercise 4 — Controlled preview experiment

Using `PatternSwitchPreviewDemo.java` from section 5:

1. Try compiling with `javac --release 17 PatternSwitchPreviewDemo.java` to observe the preview-related message.
2. Compile with `javac --enable-preview --release 17 -encoding UTF-8 PatternSwitchPreviewDemo.java`.
3. Run with `java --enable-preview PatternSwitchPreviewDemo`.
4. Rewrite the `describe` method using `instanceof` patterns, then run without preview.

The goal is to **distinguish language modes**, not to put preview features into applications.

### Exercise 5 — Evolve a `sealed` model

Create `sealed interface Result permits Success, Failure` with two records `Success(String value)` and `Failure(String message)`. Write `render(Result value)` using stable `instanceof` patterns. Then add a `Cancelled` variant to the hierarchy, update the method, and explain why this update must be reviewed everywhere `Result` is consumed.

## 14. Key Reminders for Working with Java 17

- `instanceof Type variable` is **standardized pattern matching** and is used directly in Java 17.
- `switch` expressions with constant labels and `->` are also **standard**; the arrow is not a sign of preview.
- `case Type variable ->`, `case null ->`, and guarded patterns in `switch` are parts of **preview pattern switch** in Java 17.
- When experimenting with preview on JDK 17, enable `--enable-preview` at both compile time and runtime; syntax can differ from Java 21's standard pattern `switch`.
- For code required to stay stable on Java 17, use `if`/`else if` with `instanceof` patterns, standard constant `switch`, or polymorphism according to design needs.

Accurately distinguishing **standardized features** from **preview features in each release** helps you write Java 17 code that actually runs in your target environment, while understanding why `switch` pattern examples across different Java versions can look similar yet be syntactically incompatible.
