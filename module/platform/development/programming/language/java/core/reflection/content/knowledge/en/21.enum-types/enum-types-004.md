# `Enum.valueOf()` with an enum's `Class`

`Enum.valueOf()` converts a **constant's declared name** into the constant belonging to **a specific enum type**. The `Class` parameter specifies which enum to look up in. This is a useful tool when writing configuration readers, data converters, or infrastructure code shared across multiple enums.

For example, the string `"FAST"` alone is not enough to identify an object: multiple enums may declare the same name. Only the pair `RunMode.class` and `"FAST"` specifies a request to find `RunMode.FAST`. When choosing the enum happens at runtime, `Class` is the piece of information connecting the string name to the Java type to process.

This lesson distinguishes two situations: already having `Class<E>` with a concrete enum type, and only having `Class<?>` obtained from type discovery mechanisms.

## 1. Signature and meaning of the type parameter

API signature:

```java
public static <T extends Enum<T>> T valueOf(
        Class<T> enumClass, String name)
```

This is a signature to read, not a method you need to implement yourself. The bound `<T extends Enum<T>>` ties the return type to the exact enum type that `enumClass` represents.

With `RunMode` already declared, the call can be written as follows:

```java
RunMode mode = Enum.valueOf(RunMode.class, "FAST");
```

`RunMode.class` has type `Class<RunMode>`, so the result is type-checked as `RunMode`. There is no need to cast from `Object` to the enum after the call.

The call looks up an **existing constant**; it does not create a new constant. In the experiment below, the comparison `mode == RunMode.FAST` evaluates to `true`.

According to [the `Enum.valueOf` contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)), the name must match the declared constant name exactly. If not found, it throws `IllegalArgumentException`; if the class or name argument is `null`, it throws `NullPointerException`.

### How does it differ from `RunMode.valueOf("FAST")`?

Each enum has an implicitly declared static `valueOf(String)` method. Therefore, when the enum is already known, `RunMode.valueOf("FAST")` is usually easier to read. The `Enum.valueOf(enumType, name)` form is useful for generic methods accepting `Class<E>`. The declaration rules for that method are described in [JLS on enum members](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9.3).

Both forms look up constant names; changing how you call it does not turn it into a parser for display labels or business codes.

## 2. Declared names, display labels, and business codes

Suppose the constant `FAST` has the label `Fast execution` and the code `fast-code`. These three strings serve different purposes:

| Value | Role in the experiment | `Enum.valueOf(RunMode.class, ...)` |
| --- | --- | --- |
| `"FAST"` | Declared name of the constant | Finds `RunMode.FAST` |
| `"Fast execution"` | Result of `toString()` used as a label | Not the name to look up |
| `"fast-code"` | Application-defined business code | Not automatically recognized |
| `"1"` | String representing a number | Not interpreted as `ordinal()` |

`valueOf` does not automatically trim whitespace, change case, read a `code` property, call `toString()` to compare, or infer an ordinal. The example below verifies each case with separate calls.

## 3. Complete Java 17+ example

The program has three methods serving three explicit contracts:

- `parseTyped`: exact lookup when `Class<E>` is already available.
- `parseNormalized`: a custom policy that intentionally strips leading/trailing whitespace and converts to uppercase.
- `parseRuntime`: accepts `Class<?>`, verifies it is an enum declaration, then looks up and returns `Enum<?>`.

Save the entire code into **`EnumValueOfDemo.java`**:

```java
import java.util.Locale;
import java.util.Objects;

public class EnumValueOfDemo {
    enum RunMode {
        SAFE("safe-code", "Safe execution"),
        FAST("fast-code", "Fast execution"),
        TURBO("turbo-code", "Turbo execution") {
            @Override
            public String toString() {
                return "Turbo custom label";
            }
        };

        private final String code;
        private final String label;

        RunMode(String code, String label) {
            this.code = code;
            this.label = label;
        }

        public String code() {
            return code;
        }

        @Override
        public String toString() {
            return label;
        }
    }

    public static <E extends Enum<E>> E parseTyped(
            Class<E> enumType, String name) {
        return Enum.valueOf(enumType, name);
    }

    public static <E extends Enum<E>> E parseNormalized(
            Class<E> enumType, String text) {
        Objects.requireNonNull(text, "text");
        String normalized = text.strip().toUpperCase(Locale.ROOT);
        return Enum.valueOf(enumType, normalized);
    }

    public static Enum<?> parseRuntime(Class<?> type, String name) {
        Objects.requireNonNull(type, "type");
        Objects.requireNonNull(name, "name");
        if (!type.isEnum()) {
            throw new IllegalArgumentException(
                    "Expected an enum declaration: " + type.getTypeName());
        }
        return parseCheckedClass(type, name);
    }

    @SuppressWarnings("unchecked")
    private static <E extends Enum<E>> E parseCheckedClass(
            Class<?> checkedType, String name) {
        Class<E> enumType = (Class<E>) checkedType;
        return Enum.valueOf(enumType, name);
    }

    private static void attempt(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " -> success");
        } catch (RuntimeException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        RunMode typed = parseTyped(RunMode.class, "FAST");
        System.out.println("Typed name = " + typed.name());
        System.out.println("Same constant = " + (typed == RunMode.FAST));
        System.out.println("Generated valueOf agrees = "
                + (RunMode.valueOf("FAST") == typed));
        System.out.println("Display label = " + typed);
        System.out.println("Business code = " + typed.code());
        System.out.println("Normalized name = "
                + parseNormalized(RunMode.class, " fast ").name());

        Class<?> discovered = Class.forName("EnumValueOfDemo$RunMode");
        Enum<?> dynamic = parseRuntime(discovered, "TURBO");
        System.out.println("Runtime enum type = "
                + dynamic.getDeclaringClass().getSimpleName());
        System.out.println("Runtime name = " + dynamic.name());
        System.out.println("Runtime display = " + dynamic);

        attempt("wrong case", () -> parseTyped(RunMode.class, "fast"));
        attempt("extra spaces", () -> parseTyped(RunMode.class, " FAST "));
        attempt("display label", () -> parseTyped(RunMode.class, "Fast execution"));
        attempt("business code", () -> parseTyped(RunMode.class, "fast-code"));
        attempt("ordinal text", () -> parseTyped(RunMode.class, "1"));
        attempt("missing name", () -> parseTyped(RunMode.class, "UNKNOWN"));
        attempt("null name", () -> parseTyped(RunMode.class, null));
        attempt("not an enum", () -> parseRuntime(String.class, "FAST"));
        attempt("null class", () -> parseRuntime(null, "FAST"));

        Enum<?> selected = RunMode.TURBO;
        attempt("constant runtime class",
                () -> parseRuntime(selected.getClass(), "SAFE"));
        System.out.println("From declaring class = "
                + parseRuntime(selected.getDeclaringClass(), "SAFE").name());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror EnumValueOfDemo.java
java EnumValueOfDemo
```

Output:

```text
Typed name = FAST
Same constant = true
Generated valueOf agrees = true
Display label = Fast execution
Business code = fast-code
Normalized name = FAST
Runtime enum type = RunMode
Runtime name = TURBO
Runtime display = Turbo custom label
wrong case -> IllegalArgumentException
extra spaces -> IllegalArgumentException
display label -> IllegalArgumentException
business code -> IllegalArgumentException
ordinal text -> IllegalArgumentException
missing name -> IllegalArgumentException
null name -> NullPointerException
not an enum -> IllegalArgumentException
null class -> NullPointerException
constant runtime class -> IllegalArgumentException
From declaring class = SAFE
```

The `attempt()` method serves only to observe failure cases in the experiment: printing the exception name and continuing to the next case. It is not a pattern for ignoring all `RuntimeException`s in application code.

## 4. Reading the strongly typed lookup flow

`parseTyped` has parameter `Class<E>` and returns `E`. When passing `RunMode.class`, the caller receives `RunMode` directly:

1. `Enum.valueOf` finds `FAST` in `RunMode`'s exact set of constants.
2. The `typed` variable receives that constant; comparing with `RunMode.FAST` yields `true`.
3. `RunMode.valueOf("FAST")` also yields the same constant.
4. Printing `typed.name()` produces `FAST`, whereas printing `typed` directly produces `Fast execution` because the enum overrode `toString()`.

This explains why using a display label as input to `valueOf` does not match the lookup policy. If external data uses `fast-code`, the application needs a separate lookup by code and a rule for handling nonexistent codes.

You should also not rename constants arbitrarily if those names are already used in configuration or interchange data. Old strings do not automatically turn into new names just because the enum was updated.

## 5. When only `Class<?>` is available at runtime

In the program, `Class.forName("EnumValueOfDemo$RunMode")` returns `Class<?>`. The name contains `$` because `RunMode` is a nested enum inside `EnumValueOfDemo`; this is the binary name used to locate the exact class in the example.

Even though the `Class` object actually represents `RunMode`, the `discovered` variable does not retain `Class<RunMode>` information at the static type level. Consequently, the following snippet **intentionally fails to compile**:

```java
Class<?> discovered = RunMode.class;
// Compile error: Class<?> does not satisfy the Class<T> bound where T extends Enum<T>.
Enum<?> value = Enum.valueOf(discovered, "FAST");
```

`if (discovered.isEnum())` checks the condition at runtime, but does not automatically change the variable's static type to `Class<RunMode>`. This is the difference between **verifying metadata values** and **proving type relationships to the compiler**.

### The dynamic boundary in the sample method

`parseRuntime` handles this difference behind a narrow boundary:

1. Rejects `null` for both the class and the name.
2. Uses `isEnum()` to ensure the class is an enum declaration, not a regular class or a constant's own class.
3. Calls the private method `parseCheckedClass` only after the check.
4. The private method isolates the cast that cannot be fully verified at compile time, then calls `Enum.valueOf`.
5. Outside callers only receive `Enum<?>`, because the caller does not know the concrete enum type.

`@SuppressWarnings("unchecked")` sits on the exact method containing the cast; it **does not perform verification** and does not make an invalid class valid. Only the `isEnum()` condition together with calling the private method solely from the checked branch forms the basis of the sample design.

Do not expose that private method publicly as a method allowing callers to arbitrarily pick `E`. If a caller were allowed to request an `E` different from the passed class, the return type would make a false promise. The public contract `Enum<?> parseRuntime(...)` avoids that promise.

If the enum class is still known throughout most of the application code, keep `Class<E>` and use a strongly typed helper. Only introduce the cast where `Class<?>` genuinely has to be accepted.

### Distinguishing class-lookup errors from constant-lookup errors

`Class.forName` can throw `ClassNotFoundException` before a `Class` object is found. `Enum.valueOf`, by contrast, handles looking up the constant within an already-identified type. In the example, `main` declares `throws ClassNotFoundException` because of the class discovery step, not because `Enum.valueOf` throws that exception.

There is no need to look up the `valueOf` method via `Method.invoke` just to perform this lookup. The `Enum.valueOf` API already accepts a `Class` object directly.

## 6. Must pass the declaring enum class

`RunMode.TURBO` has a constant-specific body overriding `toString()`. Therefore, the runtime class from `selected.getClass()` is an anonymous class for the constant, not the `RunMode` declaration itself.

In the experiment, `parseRuntime(selected.getClass(), "SAFE")` is rejected by `isEnum()`. However, `parseRuntime(selected.getDeclaringClass(), "SAFE")` succeeds. For an `Enum<?>` value, `getDeclaringClass()` returns the enum class owning the constant. The [`Class.isEnum()` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#isEnum()) clearly states this difference.

Do not replace the check by merely asking whether the class inherits `Enum`: a constant's own class still inherits from the enum, yet is not the enum declaration needed to look up the entire set of constants.

## 7. Input normalization is an application policy

`parseTyped(RunMode.class, " fast ")` is not made to succeed implicitly. The `parseNormalized` method in the program establishes a different contract:

```java
String normalized = text.strip().toUpperCase(Locale.ROOT);
return Enum.valueOf(enumType, normalized);
```

This is an excerpt from a method already in the program, not a standalone program. `Locale.ROOT` prevents case conversion from depending on the machine's default locale; that is the purpose of the [root locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html#ROOT).

In the experiment, the constant naming convention is uppercase, so `" fast "` is converted to `"FAST"` and the lookup succeeds. You must choose this policy based on the data format being processed.

Do not apply normalization universally: if a format requires exact names, extra spaces or wrong casing should be reported as errors. Java constant names are also not required to be uppercase; a case-folding rule can erase distinctions between names that the application wants to distinguish.

Name normalization still does not turn `fast-code` into `FAST`, nor does it turn multi-word labels into constant names. Those mappings require a separate contract.

## 8. Error handling and common mistakes

| Situation | Behavior or handling approach |
| --- | --- |
| Name does not exist, wrong case, or extra spaces | `IllegalArgumentException` from exact lookup |
| Name is `null` | `NullPointerException` |
| Class is `null` | `NullPointerException` |
| `parseRuntime` receives a non-enum-declaration class | Proactively throw `IllegalArgumentException` before casting |
| Only have `Class<?>` yet call `Enum.valueOf` directly | Compile error because the type bound is not satisfied |
| Passing `String.class` to a strongly typed call | The compiler rejects it as an enum class |
| Using display labels, business codes, or numeric strings | Not automatically interpreted as declared names |

When data comes from users, handle lookup errors at the conversion boundary and report clearly which unsupported value appeared in which field. Do not silently pick the first constant as a default just to avoid errors: doing so can alter the meaning of the request without the caller knowing.

If the application wants an optional result or a result carrying error information, define a wrapper method with that contract. `Enum.valueOf` itself does not return `null` or `Optional.empty()` to report a nonexistent name.

Only catch exceptions you actually know how to handle. An error from passing the wrong class to an internal converter usually needs to be fixed in configuration or calling code; it should not be lumped together with invalid constant-name input errors.

### Self-check

1. Why do you need to pass both `Class` and the constant name, instead of just the string `"FAST"`?
2. Why can `RunMode.class` be used directly while a `Class<?>` variable requires extra handling?
3. If `toString()` is changed to another label, does the call with `"FAST"` change its meaning?
4. Why does `isEnum()` returning `true` not automatically change the variable's static type?
5. With a constant that has a constant-specific body, which method should you use to get the `Class` for looking up constants of the same enum?
6. When is trimming spaces and uppercasing the right contract, and when should invalid input be reported?

Keep three facts in mind when applying this: **the right declaring enum class, the right declared constant name, and the right boundary between static type information and runtime metadata**.
