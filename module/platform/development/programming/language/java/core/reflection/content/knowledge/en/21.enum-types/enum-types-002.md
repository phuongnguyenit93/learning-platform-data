# Enum constant order and when `getEnumConstants()` returns `null`

When a tool only receives a `Class<?>` at runtime, it may need to know whether that type is an enum and, if so, which constants it contains. For example, a form builder needs to list options, while a configuration validator needs to know the valid values.

`Class.getEnumConstants()` solves this enumeration without needing to know the enum name when writing the tool. There are two rules to grasp: **constants are returned in declaration order**; **`null` differs from an empty enum array**. In addition, the runtime class of an enum constant with its own body may differ from the declaring enum class.

## 1. Understanding the return value properly

The API signature on `Class<T>` is:

```java
public T[] getEnumConstants()
```

This is a signature for API reference, not a method you need to implement yourself. If a variable has type `Class<Stage>`, the call returns type `Stage[]`. If you only have `Class<?>`, you can receive the result into `Object[]` and check it before using it.

According to [the contract of `Class.getEnumConstants()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getEnumConstants()), the result is the constants in declaration order, or `null` when the `Class` object does not represent an enum declaration.

| Queried type | Result | Meaning |
| --- | --- | --- |
| Enum with constants | Array containing the constants | Has a set of options to iterate |
| Enum without constants | Array of length `0` | Is an enum, but the constant set is empty |
| Regular class, interface, primitive type, or array type | `null` | The type under inspection is not an enum declaration |

Do not access `.length`, use a `for` loop, or create a stream from the result before distinguishing these cases. If you receive `null`, you do not yet have an array to iterate over.

## 2. Declaration order is not alphabetical name order

Suppose the enum is declared as follows:

```java
enum Stage {
    REVIEW, DRAFT, PUBLISHED
}
```

The iteration result is `REVIEW`, `DRAFT`, `PUBLISHED`, not alphabetical order. `Stage.values()` also returns the constants in declaration order; this method is implicitly declared for each enum according to [JLS on enum members](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9.3).

Each constant has an `ordinal()` starting from `0`, corresponding to its declaration position. `name()` gives the declared name; `toString()` may be overridden to produce a display label. Those are distinct roles in the [`Enum` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html).

In the example above, `REVIEW.ordinal()` is `0` even though `DRAFT` comes before it when sorting by name. Therefore, you must decide whether you want to preserve declaration order or create a separate display order.

## 3. Standalone runnable Java 17+ experiment

The following program tests ordering, an empty enum, non-enum types, a constant's own class, and rejecting unsuitable inputs.

Save the entire code into **`EnumConstantsDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;

public class EnumConstantsDemo {
    enum Stage {
        REVIEW, DRAFT, PUBLISHED
    }

    enum Empty {
    }

    enum Flavor {
        BASIC,
        CUSTOM {
            @Override
            public String toString() {
                return "Custom label";
            }
        }
    }

    private static String names(Class<?> type) {
        Object[] constants = type.getEnumConstants();
        if (constants == null) {
            return "null";
        }
        return Arrays.stream(constants)
                .map(value -> ((Enum<?>) value).name())
                .toList()
                .toString();
    }

    private static Object[] requireEnumConstants(Class<?> type) {
        Objects.requireNonNull(type, "type");
        Object[] constants = type.getEnumConstants();
        if (constants == null) {
            throw new IllegalArgumentException(
                    type.getTypeName() + " is not an enum declaration");
        }
        return constants;
    }

    public static void main(String[] args) {
        System.out.println("Stage constants = " + names(Stage.class));
        System.out.println("Stage values = " + Arrays.toString(Stage.values()));
        for (Stage stage : Stage.class.getEnumConstants()) {
            System.out.println(stage.name() + " ordinal = " + stage.ordinal());
        }

        Stage[] sorted = Stage.class.getEnumConstants();
        Arrays.sort(sorted, Comparator.comparing(Stage::name));
        System.out.println("Sorted by name = " + Arrays.toString(sorted));
        System.out.println("Declaration order = " + names(Stage.class));

        System.out.println("Empty is enum = " + Empty.class.isEnum());
        System.out.println("Empty constants = " + names(Empty.class));
        System.out.println("Empty count = " + Empty.class.getEnumConstants().length);

        System.out.println("String constants = " + names(String.class));
        System.out.println("Enum constants = " + names(Enum.class));
        System.out.println("Array constants = " + names(Stage[].class));
        System.out.println("int constants = " + names(int.class));

        Enum<?> selected = Flavor.CUSTOM;
        System.out.println("CUSTOM instanceof Enum = " + (selected instanceof Enum<?>));
        System.out.println("BASIC runtime is enum = " + Flavor.BASIC.getClass().isEnum());
        System.out.println("CUSTOM runtime is enum = " + selected.getClass().isEnum());
        System.out.println("CUSTOM runtime constants = " + names(selected.getClass()));
        System.out.println("CUSTOM declaring is Flavor = "
                + (selected.getDeclaringClass() == Flavor.class));
        System.out.println("CUSTOM declaring constants = "
                + names(selected.getDeclaringClass()));
        System.out.println("CUSTOM name = " + selected.name());
        System.out.println("CUSTOM display = " + selected);

        System.out.println("Required Stage count = "
                + requireEnumConstants(Stage.class).length);
        System.out.println("Required Empty count = "
                + requireEnumConstants(Empty.class).length);
        try {
            requireEnumConstants(String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("Required String = " + ex.getClass().getSimpleName());
        }
        try {
            Enum.valueOf(Stage.class, "MISSING");
        } catch (IllegalArgumentException ex) {
            System.out.println("Missing name = " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 EnumConstantsDemo.java
java EnumConstantsDemo
```

Output:

```text
Stage constants = [REVIEW, DRAFT, PUBLISHED]
Stage values = [REVIEW, DRAFT, PUBLISHED]
REVIEW ordinal = 0
DRAFT ordinal = 1
PUBLISHED ordinal = 2
Sorted by name = [DRAFT, PUBLISHED, REVIEW]
Declaration order = [REVIEW, DRAFT, PUBLISHED]
Empty is enum = true
Empty constants = []
Empty count = 0
String constants = null
Enum constants = null
Array constants = null
int constants = null
CUSTOM instanceof Enum = true
BASIC runtime is enum = true
CUSTOM runtime is enum = false
CUSTOM runtime constants = null
CUSTOM declaring is Flavor = true
CUSTOM declaring constants = [BASIC, CUSTOM]
CUSTOM name = CUSTOM
CUSTOM display = Custom label
Required Stage count = 3
Required Empty count = 0
Required String = IllegalArgumentException
Missing name = IllegalArgumentException
```

`names()` uses `name()` to print constant names, avoiding confusion with an overridden `toString()` label. The cast to `Enum<?>` is performed only after `getEnumConstants()` has produced a non-`null` array; the elements at that point are enum constants.

## 4. Reading the results and applying them properly

### Preserving or changing order intentionally

`Stage constants` and `Stage values` both print `[REVIEW, DRAFT, PUBLISHED]`. The program then fetches the array into `sorted` and sorts it by `Stage::name`, producing `[DRAFT, PUBLISHED, REVIEW]`.

A subsequent read via `getEnumConstants()` still yields the original declaration order. Sorting the local array does not alter the enum declaration, does not turn the `REVIEW` constant into another constant, and does not change its `ordinal()`.

If declaration order is already the desired order for a form, iterate over the result directly. If the UI needs a different order, express that rule explicitly using a comparator or a separate ordering property.

Do not use the order of `getDeclaredFields()` as a substitute for the enum's ordering contract. The fields array is meant for describing members, whereas this problem needs a list of **enum constant values**.

### An empty enum is valid input

`Empty.class.isEnum()` yields `true`, while `Empty.class.getEnumConstants()` yields `[]` with length `0`. An enum is not required to have at least one constant; the enum body syntax allows omitting a constant list.

For a value-picking tool, this result can mean there are no options to display. It does not mean the input type is invalid. That is why you should not merge `null` with an empty array up front.

### Why do `Enum.class`, array types, and primitive types return `null`?

In the experiment, `String.class`, `Enum.class`, `Stage[].class`, and `int.class` all return `null`.

- `String` is a regular class.
- `Enum` is the common base class, not an `enum` declaration containing its own set of constants.
- `Stage[]` is an array type, even though its element type is an enum.
- `int` is a primitive type.

If you are handling an array type and actually want to find the constants of its element type, determine the component type and inspect it. Do not treat every type containing an enum as the enum itself.

## 5. A constant's own class is not an enum declaration

In the experiment, `Flavor.CUSTOM` has a constant-specific class body overriding `toString()`, so `selected.getClass()` is an anonymous subclass. Consequently, `selected.getClass().isEnum()` is `false`, and `getEnumConstants()` on that subclass returns `null`. Conversely, `selected.getDeclaringClass() == Flavor.class`, and calling `getEnumConstants()` on `Flavor.class` returns both `BASIC` and `CUSTOM`.

When holding an `Enum<?>` constant, use `getDeclaringClass()` to find the set of constants of the same type. This case reinforces that **`null` depends on the Class being queried**, and does not mean a constant with its own body has disappeared from the enum. The lesson on `getClass` and `getDeclaringClass` analyzes the anonymous subclass mechanism and type-key normalization in detail.

## 6. Handling `null` according to your tool's contract

The following two approaches serve two different needs.

**A tool inspecting many kinds of types:** `names()` accepts any `Class<?>`. It checks `constants == null` and reports that the type is not an enum declaration; an empty array is still rendered as `[]`.

**A tool accepting only enums:** `requireEnumConstants()` in the example rejects other types with `IllegalArgumentException`. The method name and exception clearly state the precondition. `Empty.class` is still accepted and returns a constant count of `0`.

Do not automatically convert every `null` result into an empty array if the program needs to distinguish invalid input from a valid enum with no constants. If you intentionally normalize them, document that decision in the tool's own contract.

You must also distinguish **the method returning `null`** from **the receiver variable being `null`**. If the variable `Class<?> type` is `null`, the expression `type.getEnumConstants()` throws `NullPointerException` upon invocation; it does not return a result for you to inspect. That is why the sample method uses `Objects.requireNonNull(type, "type")` for the input.

### Do not confuse with looking up a single constant name

`getEnumConstants()` lists the set of constants; `Enum.valueOf(Stage.class, "MISSING")` looks up a specific name. The second call in the experiment throws `IllegalArgumentException` because no such name exists, rather than returning `null`.

The name being looked up must match exactly, including case and with no extra whitespace. That is the separate contract of the [`Enum.valueOf` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)), and should not be inferred from how `getEnumConstants()` handles non-enum types.

## 7. Notes on names, ordinals, and maintainability

`ordinal()` describes the declaration position in the current version. If a constant is added at the beginning or positions are swapped, the ordinals of subsequent constants change. Therefore, using it as a long-term stored code can cause the same number to be interpreted as a different value after a program update.

For example, with `[REVIEW, DRAFT, PUBLISHED]`, `0` points to `REVIEW`. If `DRAFT` is later moved to the front, `0` points to `DRAFT` instead. When stable business codes are needed, design dedicated codes and corresponding lookup rules.

`name()` preserves the declared name, whereas `toString()` in the experiment turns `CUSTOM` into `Custom label`. This label change does not alter the constant's name, declaration position, or owning enum class. Tools should choose clearly whether they need the technical name or display content.

## 8. Common mistakes and self-check

| Mistake | How to avoid |
| --- | --- |
| Using `.length` immediately without checking for `null` | Classify the result before iterating |
| Treating an empty enum as a non-enum type | Distinguish `[]` from `null` |
| Assuming the order is alphabetical | Rely on declaration order or sort explicitly |
| Checking for an enum solely by whether the object inherits `Enum` | When the constant set is needed, identify the exact declaring enum class |
| Using `constant.getClass()` for every constant | For an enum constant, use `getDeclaringClass()` to find its owning enum |
| Treating `toString()` as an always-fixed constant name | Use `name()` when the exact declared name is needed |
| Storing `ordinal()` as a stable business code | Use a dedicated code when stability across changes is required |
| Thinking a name absent from `valueOf` returns `null` | Handle `IllegalArgumentException` per the lookup contract |

Try the following changes and predict the output before running:

1. Move `PUBLISHED` to the beginning of `Stage`: how do the enumerated result and `ordinal()` change?
2. Add a constant to `Empty`: by what else is the difference between an empty array and `null` determined?
3. Remove the custom body from `CUSTOM`: why can the result from `getClass()` change?
4. Change the `Custom label` string: do `name()`, `getDeclaringClass()`, and constant order change?

After this lesson, you should be able to determine for yourself: whether you are receiving a type or an enum value, whether that type is the enum declaration itself, and whether your tool wants to preserve declaration order or create a different order.
