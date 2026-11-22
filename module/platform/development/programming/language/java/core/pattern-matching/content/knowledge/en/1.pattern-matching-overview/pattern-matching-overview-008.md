# Limitations of Pattern Matching in Java 21

Pattern matching helps Java check whether a value matches a **pattern** while simultaneously extracting type-checked data. In Java 21, the two primary cases are **type patterns** (commonly used with `instanceof` or `switch`) and **record patterns** (deconstructing the components of a `record`, including nested patterns). The syntax is more concise than manual casting, but pattern matching is **not** a tool for checking every kind of condition, replacing the type system, or automatically validating business data.

## 1. Only Matches Pattern Forms Supported by the Language

- A **type pattern** checks an object's type at runtime and declares a variable, such as `value instanceof String text`. The variable `text` can only be used in places where the compiler proves that the match succeeded.
- A **record pattern** extracts data according to the declared *components* of a `record`, for example `case Point(var x, var y)`. It does not automatically deconstruct fields of arbitrary regular classes, cannot arbitrarily access private fields, and does not provide custom deconstruction mechanisms for classes.
- In Java 21, there is no built-in pattern syntax for deconstructing individual elements of an array/`List`, matching regexes, or expressing numeric constraints. You can use `when` in `switch` or `&&` conditions with `instanceof` to perform additional checks, but those are **additional conditions**, not new pattern kinds.
- Type patterns in Java 21's stable features are primarily for **reference types**. You cannot write `case int n` as a primitive type pattern in Java 21; a `switch` on `int` still uses constant labels such as `case 1`, `case 2`, etc.

For example, `Point` must be a `record` for the following component deconstruction syntax to work directly:

```java
record Point(int x, int y) {}

static String show(Object value) {
    return switch (value) {
        case Point(var x, var y) -> "(" + x + ", " + y + ")";
        default -> "not a point";
    };
}
```

This is an illustrative snippet that needs to be placed inside a class or a valid Java context; on its own, it is not a standalone runnable file.

## 2. Structural Matching Does Not Mean Valid Data

`record User(String name, int age) {}` still allows creating `new User(null, -2)` if the constructor does not validate inputs. The pattern `User(var name, var age)` only extracts the two components; it **does not prove** that `name` has content or that `age` is valid.

In `switch`, use `when` to check additional required business conditions:

```java
record User(String name, int age) {}

static String describe(User user) {
    return switch (user) {
        case null -> "missing user";
        case User(var name, var age)
                when name != null && !name.isBlank() && age >= 0
                -> name + " (" + age + ")";
        case User(var name, var age) -> "invalid user";
    };
}
```

This snippet is an illustration that needs to be placed inside a class. The final `User(var name, var age)` branch handles records that match the type but fail the `when` condition. For critical data, validation in the constructor, domain service, or validation layer is still necessary; pattern matching only helps *read and branch* on data.

## 3. Cannot Bypass Generics Type Erasure

Java erases most generic type argument information at runtime (*type erasure*). Therefore, if an input variable has type `Object`, you cannot assert that every element is a `String` by matching `List<String>`:

```java
// DOES NOT COMPILE when value has type Object:
if (value instanceof java.util.List<String> strings) {
    // ...
}
```

Match a type that can be checked at runtime, then check each element if your business logic requires it:

```java
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text);
        }
    }
}
```

The two snippets above are illustrations inside a method with a `value` variable. `List<?>` only proves that it is a `List`; it **does not** guarantee that all elements are `String`. An unchecked cast like `(List<String>) value` also cannot restore type evidence that has been erased.

## 4. `null` Needs to Be Handled Explicitly

- `null instanceof String` evaluates to `false`; `instanceof` type patterns do not match `null`.
- A `switch` using patterns on a reference value normally throws `NullPointerException` when the selector is `null`, unless there is an appropriate `null`-handling branch such as `case null`. **A standalone `default` does not catch `null`.**
- A record can hold a `null` reference component. Extracting a component with `var` does not automatically validate that the component is non-`null`; you must check it before calling methods on it.

For example, `case null -> "missing"` explicitly specifies how to handle a null selector. When using `when text != null && ...`, the `null` check applies to the **component** extracted from the record rather than just the selector itself.

## 5. Pattern Variable Scope Depends on Control Flow

The compiler uses *flow scoping*: a pattern variable is only in scope where the compiler can prove that the pattern matched.

```java
static void printIfText(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        System.out.println(text.trim()); // valid: text is definitely assigned
    }

    // System.out.println(text); // ERROR: text is out of scope
}
```

With `&&`, the right-hand side is only evaluated if the left-hand side is true, so `text` can be used on the right-hand side. Conversely, do not rely on `text` after `||`, because another branch can be true while `instanceof` is false:

```java
// DOES NOT COMPILE: text is not definitely assigned when the other || branch is true.
if (value instanceof String text || value == null) {
    System.out.println(text);
}
```

These examples are snippets inside an appropriate class/method, not standalone programs. When conditional expressions become complex, splitting conditions or using `if`/early return is easier to read and verify.

## 6. `switch` Has Rules for Ordering, Exhaustiveness, and `when`

**Dominance (one branch covering another).** A broader type branch placed earlier can prevent a narrower type branch after it from ever being selected. Java reports a compile-time error instead of silently leaving that branch unreachable:

```java
// DOES NOT COMPILE in a pattern switch with an Object selector:
case CharSequence chars -> "character sequence";
case String text -> "string"; // dominated by the preceding CharSequence case
```

Place more specific branches before more general ones. Branches with `when` must also be evaluated for dominance; a guard condition can cause a type to be handled in the first branch while still requiring a fallback branch of the same type afterward.

**Exhaustiveness (covering all possible cases).** A `switch` expression must be exhaustive; a `switch` statement using patterns is also an enhanced switch and must be exhaustive. When the selector has an open type like `Object`, `default` is usually required. With a `sealed` interface, the compiler can verify that all permitted subtypes are covered; if the sealed hierarchy changes, the corresponding `switch` statements/expressions must be reviewed.

**A `when` guard does not replace a fallback branch.** If you only have `case Circle(var r) when r > 0`, the case of a `Circle` with a non-positive radius remains unhandled. Add an unguarded `case Circle(var r)` or an appropriate general branch.

**Do not conflate syntax.** `when` is used with pattern labels in a Java 21 `switch`; with `instanceof`, use `&&` to chain additional checks. The `switch` rules protect branching integrity, but they cannot decide for you which business conditions are correct.

## 7. Pattern Matching Does Not Replace Data Design or Guarantee Performance

- Pattern matching reduces repetitive `instanceof` and casting, but it does not guarantee faster execution than well-written `if`/cast code. Performance still depends on the data, compiler/JIT, branching, and inner logic.
- A long chain of `case` branches checking subtypes may signal that the object model lacks shared behavior. When objects genuinely own behavior, polymorphism or an interface method is sometimes clearer.
- Record patterns fit immutable structural data at the component level well; they do not turn records into a schema-validation mechanism or deep object copying. A reference component can still point to a mutable object.
- With a non-`sealed` hierarchy, you must not assume all subtypes are enumerated. With a `sealed` hierarchy, you still need to update logic if the set of subtypes changes.

## 8. Complete Example Running on Java 21

Create the file **`PatternMatchingLimitsDemo.java`**:

```java
public class PatternMatchingLimitsDemo {
    sealed interface Payload permits Text, Count {}

    record Text(String value) implements Payload {}
    record Count(int value) implements Payload {}

    static String explain(Payload payload) {
        return switch (payload) {
            case null -> "missing";
            case Text(var value) when value != null && !value.isBlank()
                    -> "text=" + value;
            case Text(var ignored) -> "text unavailable";
            case Count(var value) when value > 0 -> "positive=" + value;
            case Count(var value) -> "non-positive=" + value;
        };
    }

    public static void main(String[] args) {
        Object source = " Java ";
        if (source instanceof String text && !text.isBlank()) {
            System.out.println(text.trim());
        }

        System.out.println(explain(new Text("hello")));
        System.out.println(explain(new Text(null)));
        System.out.println(explain(new Count(0)));
        System.out.println(explain(null));
    }
}
```

Compile and run with **JDK 21** (no `--enable-preview` needed):

```bash
javac --release 21 PatternMatchingLimitsDemo.java
java PatternMatchingLimitsDemo
```

Stdout:

```text
Java
text=hello
text unavailable
non-positive=0
missing
```

Points to observe: `instanceof` confirms `source` is a string before calling `trim()`; the record pattern branch with `when` only accepts non-`null` and non-blank text; the next `Text` branch catches invalid data cases; `Count(0)` is handled by the fallback branch; `case null` handles a null selector. `Payload` is a sealed interface, so the two subtypes `Text` and `Count` are sufficient for exhaustiveness over non-`null` values in this example.

## 9. How to Choose When Applying Pattern Matching

1. Need to check whether a value belongs to a specific type or record? Use a type/record pattern; data from a record still needs validation if there are constraints.
2. Need to check generic element types, regexes, value ranges, or business rules? Use the corresponding additional checks; patterns do not prove these on their own.
3. Need to branch across multiple types using `switch`? Order narrower branches before broader ones; handle `null`, failed guards, and exhaustiveness explicitly.
4. Need to use a pattern variable outside a condition? Check flow scoping, especially with `&&`, `||`, negation, or early returns.
5. If logic grows long or changes frequently, consider extracting methods, validation, or polymorphism to keep the code easy to test and maintain.

Pattern matching is a tool for **expressing type-safe checks and data extraction** in the forms supported by Java 21. Its most important limitation is that a successful match only guarantees what the pattern actually checks; all remaining properties must be modeled and validated separately.
