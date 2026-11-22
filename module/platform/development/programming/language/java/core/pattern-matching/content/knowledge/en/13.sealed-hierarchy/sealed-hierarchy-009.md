# Combining Sealed Types with Records in Java

**Topic:** Java Core Pattern Matching → *Sealed hierarchy*. This lesson presents how to combine **`sealed class` / `sealed interface`** and **`record`** to model a finite set of states, enabling readable, compile-time-checked exhaustive `switch` expressions and record patterns with minimal casting. The examples use **Java 21** (record patterns and pattern matching for switch are finalized) and require no preview features.

## 1. The problem: one parent type, multiple valid data forms

Imagine a calculator that must handle three kinds of expressions:

- Numeric value: an integer, for example `3`.
- Addition: two sub-expressions, for example `3 + 5`.
- Negation: one sub-expression, for example `-(5)`.

If you use a single class with a `kind` field alongside multiple nullable fields, the author must manually maintain invariants: when `kind == SUM`, both operands must be present; when `kind == NUMBER`, the addition fields should not be used. The Java compiler does not automatically verify the consistency of these flags and fields.

If you use a regular interface:

```java
interface Expr { }

record Num(int value) implements Expr { }

record Sum(Expr left, Expr right) implements Expr { }
```

you gain polymorphism, but **any class permitted by access rules can implement `Expr`**. When a `switch` needs to handle every `Expr` type, the compiler does not know that the subtype list is closed.

Adding `sealed` clarifies the set of allowed direct subtypes:

```java
sealed interface Expr permits Num, Sum, Neg { }

record Num(int value) implements Expr { }
record Sum(Expr left, Expr right) implements Expr { }
record Neg(Expr inner) implements Expr { }
```

This is a fitting combination: **`sealed` restricts *the possible variants*, and `record` describes *the data of each variant*.** As a result, a `switch` over `Expr` can be checked for exhaustiveness across all defined variants.

## 2. Respective roles of `sealed` and `record`

### 2.1. `sealed` controls the inheritance structure

A `sealed interface` or `sealed class` specifies the list of types **permitted to directly extend/implement it** via `permits` (or inferred according to JLS rules in certain cases within the same compilation unit).

```java
sealed interface Payment permits Cash, Card { }

record Cash(int amount) implements Payment { }
record Card(String token) implements Payment { }
```

Here, only `Cash` and `Card` are declared as permitted direct implementors of `Payment`. If another type attempts to implement `Payment` directly without permission, the compiler reports an error.

Key points to note:

- `permits` lists **direct subtypes**, not arbitrary descendants at any level.
- A direct subtype of a sealed class/interface must have an appropriate closed/open modifier: `final`, `sealed`, or `non-sealed` (explicitly or implicitly by declaration kind).
- If a branch is declared `non-sealed`, descendants beneath that branch can extend it further; `sealed` on the parent does not mean every level in the hierarchy stays closed forever.
- When using named modules, `permits` subtypes must belong to the same module; with an unnamed module, they must belong to the same package. This is a Java language constraint, not merely a code-organization convention.
- `permits` can be omitted when the eligible direct subtypes are inferred per JLS within the same compilation unit. For lessons and public libraries, writing `permits` explicitly often makes the design clearer.

### 2.2. `record` stores the data of a variant

A record such as:

```java
record Cash(int amount) implements Payment { }
```

has a component `amount`; Java generates the corresponding field, accessor `amount()`, canonical constructor (if not explicitly defined), and `equals`, `hashCode`, and `toString` methods according to record rules.

`Cash` is **implicitly `final`**. Therefore, a record can directly implement a sealed interface **without adding `final`**. Each record expresses a clear data structure.

However, a record **does not automatically validate** business rules: `amount < 0` can still be constructed unless the constructor rejects it. Records also provide only **shallow immutability**: if a component references a mutable object, that object can still be mutated.

### 2.3. Why `sealed interface` is usually preferred over `sealed class` with records

Records have a fixed superclass defined by Java, `java.lang.Record`, and **cannot declare `extends SomeClass`**. Records can `implements` interfaces.

Valid:

```java
sealed interface Event permits Started, Stopped { }
record Started(long epochMillis) implements Event { }
record Stopped(String reason) implements Event { }
```

Invalid (illustrating **does not compile**):

```java
// DOES NOT COMPILE:
// sealed abstract class Event permits Started { }
// record Started(long time) extends Event { }
```

A record cannot extend an arbitrary superclass. If you want all variants to be records, **a `sealed interface` is usually the natural parent type**. If you must use a `sealed class` because of shared state or implementation, direct subtypes must be regular classes; you cannot make a record `extends` that class.

## 3. A data model shaped like an algebraic data type

The structure:

```java
sealed interface Expr permits Num, Sum, Neg { }

record Num(int value) implements Expr { }
record Sum(Expr left, Expr right) implements Expr { }
record Neg(Expr inner) implements Expr { }
```

can be read as a “sum of possibilities”:

```text
Expr =
    Num(value: int)
  | Sum(left: Expr, right: Expr)
  | Neg(inner: Expr)
```

This modeling style is close to an **algebraic data type (ADT)** in functional programming, using Java features: a closed hierarchy for the “branches” and records for the “fields”.

**Strengths:**

- No need to store a `kind` tag and manually remember which tag corresponds to which fields.
- No new kind of `Expr` can be created outside the permitted set while the hierarchy remains closed.
- The data of `Sum` and `Neg` has type `Expr`, enabling recursive tree representations.
- `switch` dispatches on each record and can deconstruct components directly in the case label.
- When a new permitted subtype is added and recompiled, the compiler can point out `switch` statements/expressions that are no longer exhaustive.

**Limitation:** A sealed hierarchy only closes the **set of types**; it does not prove that all **component values** are valid. A `Sum(null, null)` is still valid at the type level if the constructor does not validate it.

## 4. Using type patterns to handle each record

A simple version using type patterns:

```java
static int eval(Expr expr) {
    return switch (expr) {
        case Num n -> n.value();
        case Sum s -> Math.addExact(eval(s.left()), eval(s.right()));
        case Neg n -> Math.negateExact(eval(n.inner()));
    };
}
```

This example is **within the same context where `Expr`, `Num`, `Sum`, and `Neg` were declared** above. When the selector has static type `Expr`, the JLS checks the permitted subtypes and recognizes that the three labels exhaustively cover the current hierarchy.

No `default` branch is needed. If a new variant is added to the sealed hierarchy and the code is recompiled, the compiler will require this expression to be revisited.

A minor downside of type patterns is having to call accessors to retrieve data: `n.value()`, `s.left()`, `s.right()`.

## 5. Record patterns: type checking *and* data deconstruction

Java 21 supports **record patterns**:

```java
static int eval(Expr expr) {
    return switch (expr) {
        case Num(int n) -> n;
        case Sum(Expr left, Expr right) ->
                Math.addExact(eval(left), eval(right));
        case Neg(Expr inner) -> Math.negateExact(eval(inner));
    };
}
```

`Num(int n)` means: the value must be an instance of `Num`, and its `int value` component is bound to the pattern variable `n`. `Sum(Expr left, Expr right)` extracts two components; `Neg(Expr inner)` extracts one component.

Breaking down a label:

```java
case Sum(Expr left, Expr right) ->
        Math.addExact(eval(left), eval(right));
```

1. Java checks whether the selector matches the record class `Sum`.
2. If it matches, the record pattern tests each component in turn using the component patterns.
3. The variables `left` and `right` are brought into scope for the branch when matching succeeds.
4. The branch body recursively calls `eval` and adds the results using `Math.addExact`.

`Math.addExact` throws `ArithmeticException` if addition overflows `int`. This does not detract from the example; it is an explicit choice rather than letting `int` addition overflow silently.

### Record patterns and type patterns as two levels of detail

| Type pattern | Record pattern | When to choose |
| --- | --- | --- |
| `case Num n -> n.value()` | `case Num(int n) -> n` | Want to use only the `value` component |
| `case Sum s -> eval(s.left()) + eval(s.right())` | `case Sum(Expr a, Expr b) -> eval(a) + eval(b)` | Want to read the two-operand structure directly |
| `case Neg n -> ...` | `case Neg(Expr inner) -> ...` | Want to express the structure right in the label |
| Variable refers to the whole record | Variables bound from matched components | Need to call multiple methods on the record or only need components? |

There is no requirement that every case must use a record pattern. For large records or logic that needs the whole object, a type pattern can be clearer. For small structures where you work directly with components, record patterns are usually more concise and readable.

## 6. Combining nested record patterns

Tree-like expressions pair particularly well with **nested record patterns**. For example, to match specifically a `Sum` whose two arguments are `Num`:

```java
static String inspect(Expr expr) {
    return switch (expr) {
        case Sum(Num(int a), Num(int b)) -> "sum-two-literals:" + a + "," + b;
        case Sum(Expr left, Expr right) -> "other-sum";
        case Num(int n) -> "number:" + n;
        case Neg(Expr inner) -> "negative-expression";
    };
}
```

For `new Sum(new Num(1), new Num(2))`, the first branch returns `sum-two-literals:1,2`. For `new Sum(new Num(1), new Neg(new Num(2)))`, the first branch does not match because the right-hand side is `Neg`; the subsequent `Sum(Expr left, Expr right)` branch handles it and returns `other-sum`.

Two important notes:

- Place **specific** branches like `Sum(Num(...), Num(...))` before the **general** `Sum(Expr, Expr)` branch. If the order is reversed, the specific branch will be *dominated*, causing a compile-time error.
- Nested record patterns describe **data structure**, not value conditions such as “`a > 0`”. Use `when` if you need to filter by value.

The `Expr` tree is a recursive model, but **matching in a single label does not automatically recurse indefinitely**. It deconstructs only the components named in the pattern expression; to traverse the whole tree, use recursion with a base case such as `eval` or `describe`.

## 7. `when` guards on sealed record patterns

A `Num` type may have multiple business categories:

```java
static String describe(Expr expr) {
    return switch (expr) {
        case Num(int n) when n < 0 -> "negative literal:" + n;
        case Num(int n) -> "literal:" + n;
        case Sum(Expr left, Expr right) ->
                "sum(" + describe(left) + "," + describe(right) + ")";
        case Neg(Expr inner) -> "neg(" + describe(inner) + ")";
    };
}
```

The guard `when n < 0` is evaluated **only after the record pattern `Num(int n)` has matched**, so `n` is available to use. If the guard evaluates to `false`, Java continues testing subsequent labels; the unguarded `case Num(int n)` handles the remaining numbers.

**Do not write only guarded branches and assume the compiler will consider them exhaustive.** Java does not prove that arbitrary boolean expressions cover all possible values. When a variant needs branching with guards, include an **unguarded** label to cover the rest.

### Guards vs. `if` inside the case body

If you only want to classify `Num` internally, you can write:

```java
case Num(int n) -> {
    if (n < 0) {
        yield "negative literal:" + n;
    }
    yield "literal:" + n;
}
```

This is a **single branch** in the `switch` expression; once `Num` is selected, an `if` condition does not cause Java to fall through to other cases. With `when`, a false guard means the current label does not apply. Choose the approach that matches your intended control flow.

## 8. Exhaustiveness: why sealed + record beats classifying `Object`

When the selector has static type `Expr`:

```java
static int eval(Expr expr) {
    return switch (expr) {
        case Num(int n) -> n;
        case Sum(Expr left, Expr right) -> eval(left) + eval(right);
        case Neg(Expr inner) -> -eval(inner);
    };
}
```

the compiler can infer the set of subtypes from the sealed hierarchy and verify that the switch is exhaustive.

However, if you change the parameter to `Object`:

```java
// DOES NOT COMPILE (switch expression is not exhaustive).
static String incomplete(Object input) {
    return switch (input) {
        case Num(int n) -> "number";
        case Sum(Expr a, Expr b) -> "sum";
        case Neg(Expr inner) -> "neg";
    };
}
```

`Object` can hold `String`, `Integer`, or other classes. The three record patterns only cover `Expr`, **not every `Object`**.

How to fix it if the API accepts `Object`:

```java
static String inspect(Object input) {
    return switch (input) {
        case null -> "missing";
        case Expr expr -> "expr:" + describe(expr);
        default -> "not-expr";
    };
}
```

Here, `Expr expr` is a general type pattern covering the subtypes of `Expr`, while `default` is still required for non-`Expr` types because the selector is `Object`.

**API lesson:** declare the parameter as `Expr` if the method **only accepts valid expressions**. Only widen to `Object` at boundaries that genuinely need to classify heterogeneous inputs. A wider API is not always a better API.

### Do not mechanically add `default` to a closed hierarchy

```java
// DO NOT USE default just to avoid revisiting new subtypes.
static String maybeHidesFutureCase(Expr expr) {
    return switch (expr) {
        case Num(int n) -> "num";
        case Sum(Expr a, Expr b) -> "sum";
        default -> "other";
    };
}
```

This code compiles, but when a new subtype is added, `default` can mask the missing specific handling. For a closed model, prefer listing all three branches `Num`, `Sum`, `Neg` and omitting `default` if each variant truly has distinct behavior.

## 9. Handling `null` at two different levels

**Level 1: the selector `Expr` itself is `null`.** Top-level record patterns on the selector do not match `null`. An exhaustive `switch` expression over `Expr` without `case null` can still throw **`NullPointerException`** when invoked with `null`.

```java
static String label(Expr expr) {
    return switch (expr) {
        case Num(int n) -> "num";
        case Sum(Expr a, Expr b) -> "sum";
        case Neg(Expr inner) -> "neg";
    };
}
```

Calling `label(null)` results in an NPE rather than matching any record branch. If `null` is a valid input to handle, add:

```java
case null -> "missing";
```

to the `switch` above.

**Level 2: the selector is a non-null record whose component is `null`.** For example, `new Sum(null, new Num(1))` can exist if the constructor does not check for it. This is **not a null selector**, because `Sum` itself is an object.

This is a **model invariant** issue, not simply a `case null` issue. For the expression tree in this lesson, choose the policy of **disallowing null components**:

```java
record Sum(Expr left, Expr right) implements Expr {
    Sum {
        java.util.Objects.requireNonNull(left, "left");
        java.util.Objects.requireNonNull(right, "right");
    }
}
```

This is a **compact canonical constructor**. When creating `new Sum(null, new Num(1))`, `requireNonNull` throws an NPE with the message `left`. Any `Sum` instance created through this constructor is guaranteed to have two non-null components.

A similar validation constructor can be written for `Neg(Expr inner)`.

**Deeper note:** in Java 21, whether a nested pattern can match a `null` component depends on the pattern kind and type relationships; do not blindly apply the rule “null matches no pattern” from the outer selector to every nested component. A simpler and safer approach in this model is to **enforce non-null invariants in the constructor**, rather than delegating structural protection to every `switch` branch.

## 10. Are records truly immutable?

Records guarantee that **component fields** are `private final`, have no default setters, and cannot have extra arbitrary instance fields added. However, this is **shallow immutability**. For example:

```java
record Tags(java.util.List<String> names) { }

java.util.List<String> source = new java.util.ArrayList<>();
source.add("first");
Tags tags = new Tags(source);
source.add("second");

// tags.names() can now observe the "second" element.
```

Reason: `names` is a `final` reference to a mutable list, not an immutable copy.

To mitigate this in a record model:

```java
record Tags(java.util.List<String> names) {
    Tags {
        names = java.util.List.copyOf(names);
    }
}
```

`List.copyOf` creates or reuses an unmodifiable list that rejects null elements. When a record holds collections, arrays, or mutable objects, consider **defensive copying**, return types, and the deep immutability of elements.

A record implementing a sealed interface does not alter these immutability rules. **`sealed` controls who may be a subtype; `record` controls state structure and generated API**, not arbitrary data-safety guarantees.

## 11. Generic sealed interface + generic record

Combining `sealed` and `record` is not limited to non-parameterized types. A generic result model:

```java
sealed interface Result<T> permits Ok, Failure { }

record Ok<T>(T value) implements Result<T> { }

record Failure<T>(String reason) implements Result<T> { }
```

This defines a closed set of variants `Ok` or `Failure`, while keeping the success value type generic over `T`.

For `Result<String>`, Java 21 can infer type arguments in record patterns:

```java
static String display(Result<String> result) {
    return switch (result) {
        case Ok(var value) -> "ok:" + value.toUpperCase();
        case Failure(var reason) -> "error:" + reason;
    };
}
```

`Ok(var value)` is inferred from the `Result<String>` type context; `value` has static type `String`, so `toUpperCase()` is valid. No `default` is needed because the two variants exhaustively cover the generic hierarchy.

**Limitations to understand accurately:**

- The generic parameter `T` is not fully retained at runtime due to **type erasure**.
- The static type of the selector matters greatly. If the selector is only `Object` from untrusted data, you cannot rely on a generic record pattern to assert `T == String`.
- `record Ok<T>` does not automatically enforce `value != null`. For instance, `new Ok<String>(null)` can still be created; `display` above would throw an NPE at `value.toUpperCase()`. If `null` is invalid, validate it in the record constructor.
- Not every hierarchy needs to be generic; add `T` only when it expresses a type relationship useful to callers.

### Minimal standalone generic example

Create `GenericResultDemo.java`:

```java
public class GenericResultDemo {
    sealed interface Result<T> permits Ok, Failure {}
    record Ok<T>(T value) implements Result<T> {}
    record Failure<T>(String reason) implements Result<T> {}

    static String display(Result<String> result) {
        return switch (result) {
            case Ok(var value) -> "ok:" + value.toUpperCase();
            case Failure(var reason) -> "error:" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(display(new Ok<>("ok")));
        System.out.println(display(new Failure<String>("unavailable")));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 GenericResultDemo.java
java GenericResultDemo
```

Output:

```text
ok:OK
error:unavailable
```

This demonstrates combining a **closed set of variants** with a **generic result type**, where pattern matching uses compile-time type information effectively.

## 12. Complete program: sealed + record expression tree

Create **`SealedRecordPatternsDemo.java`**. The program includes invariant-validating constructors, exhaustive switches, record patterns, guards, and `null` handling at the `Object` boundary:

```java
public class SealedRecordPatternsDemo {
    sealed interface Expr permits Num, Sum, Neg {}

    record Num(int value) implements Expr {}

    record Sum(Expr left, Expr right) implements Expr {
        Sum {
            java.util.Objects.requireNonNull(left, "left");
            java.util.Objects.requireNonNull(right, "right");
        }
    }

    record Neg(Expr inner) implements Expr {
        Neg {
            java.util.Objects.requireNonNull(inner, "inner");
        }
    }

    static int eval(Expr expr) {
        return switch (expr) {
            case Num(int n) -> n;
            case Sum(Expr left, Expr right) ->
                    Math.addExact(eval(left), eval(right));
            case Neg(Expr inner) ->
                    Math.negateExact(eval(inner));
        };
    }

    static String describe(Expr expr) {
        return switch (expr) {
            case Num(int n) when n < 0 -> "negative literal:" + n;
            case Num(int n) -> "literal:" + n;
            case Sum(Expr left, Expr right) ->
                    "sum(" + describe(left) + "," + describe(right) + ")";
            case Neg(Expr inner) ->
                    "neg(" + describe(inner) + ")";
        };
    }

    static String inspect(Object candidate) {
        return switch (candidate) {
            case null -> "missing";
            case Expr expr -> "expr:" + describe(expr);
            default -> "not-expr";
        };
    }

    public static void main(String[] args) {
        Expr tree = new Sum(new Num(3), new Neg(new Num(5)));

        System.out.println(describe(tree));
        System.out.println("eval=" + eval(tree));
        System.out.println(describe(new Num(-2)));

        System.out.println(inspect(null));
        System.out.println(inspect(new Num(7)));
        System.out.println(inspect("other"));

        try {
            new Sum(null, new Num(1));
        } catch (NullPointerException e) {
            System.out.println("invalid:" + e.getMessage());
        }

        try {
            eval(null);
        } catch (NullPointerException e) {
            System.out.println("eval-null:NPE");
        }
    }
}
```

Compile and run commands:

```bash
javac --release 21 -encoding UTF-8 SealedRecordPatternsDemo.java
java SealedRecordPatternsDemo
```

Output:

```text
sum(literal:3,neg(literal:5))
eval=-2
negative literal:-2
missing
expr:literal:7
not-expr
invalid:left
eval-null:NPE
```

### Reading the output and how the features work together

1. `tree` is `Sum(Num(3), Neg(Num(5)))`. Each node is a record in the `Expr` sealed hierarchy.
2. `describe` deconstructs each record by label: `Sum` has two operands, `Neg` has one sub-expression, and `Num` has an integer.
3. `eval` computes `3 + (-5)`, returning **`-2`**. The compiler accepts the expression without a `default` because all variants `Num`, `Sum`, and `Neg` are covered.
4. For `Num(-2)`, the guard `when n < 0` selects the specialized label; if the guard is false, the following `Num(int n)` label handles it.
5. `inspect(null)` returns `missing` because of `case null`. `inspect(new Num(7))` matches the type pattern `Expr expr`; `inspect("other")` enters `default` because the `Object` selector receives values that are not `Expr`.
6. `new Sum(null, new Num(1))` is rejected by the constructor before becoming a valid node. The code catches the NPE and prints the component name `left`.
7. `eval(null)` has no `case null`, so even though it is exhaustive over subtypes, it still throws an NPE. This reflects a policy that `eval` expects a valid non-null `Expr`; for public APIs, `Objects.requireNonNull` can be added to provide a proactive message.

**Program limitations:** the code uses recursion; a very deep tree can cause a stack overflow. `Math.addExact` and `Math.negateExact` can also throw `ArithmeticException` on numeric overflow. These are algorithmic limits independent of `switch` exhaustiveness.

## 13. Evolving the model: the compiler helps detect missing cases

Suppose the model is extended with multiplication:

```java
record Mul(Expr left, Expr right) implements Expr { }
```

With the sealed interface declaring `permits Num, Sum, Neg`, you cannot simply add the record above: **`Mul` is not yet in the permitted list**. You must update the hierarchy:

```java
sealed interface Expr permits Num, Sum, Neg, Mul { }
```

This illustrates **a change on the full model**, not standalone compilable code; you also need to declare `Mul` and keep all related subtypes.

When recompiling `eval` and `describe` against the updated sealed hierarchy, exhaustive `switch` expressions lacking `case Mul(...)` will be flagged by the compiler for update. That is a major benefit of **not writing `default` indiscriminately** for closed hierarchies.

An option that loses this signal:

```java
// Inside a switch that already has Num/Sum/Neg cases:
default -> throw new IllegalArgumentException("unexpected expression");
```

If a `default` is always present, the compiler considers the switch exhaustive and will not force you to add a `Mul` branch. The `Mul` case would only be discovered at runtime. For an application-owned set of variants, if you want full support for new subtypes, **prefer omitting `default`** and letting the compiler point out every place that needs updating.

### Binary compatibility and `MatchException`

If a module containing a `switch` was compiled against an older hierarchy, and at runtime receives a subtype added in another module **without recompiling the switch**, a switch that was exhaustive at compile time may fail to find a matching label. Java 21 can throw **`MatchException`**.

Practical takeaway: when releasing changes to an enum or sealed hierarchy, **recompile dependent modules and run compatibility tests**. This runtime error is not a reason to always add a silent `default`; it is a sign that deployment versioning must be managed.

## 14. Which model fits? Comparing alternatives

### Sealed interface + record

Use when there is a **finite number of variants with different data representing the same domain concept**: event types, commands, results, AST expressions, payment methods, or return states.

Pros: the API self-documents the valid states, minimal boilerplate, and pattern matching/exhaustiveness are effective. Cost: adding a new variant may require updating multiple `switch` sites, which is **intentional** when every operation must be updated.

### Enum + data fields

`enum` works well when the state set consists primarily of **values without per-variant payloads**, such as `NEW`, `DONE`, `FAILED`. If `FAILED` needs an error string while `DONE` needs a timestamp of a different type, sealed records usually provide a cleaner representation than an enum combined with multiple `nullable` fields.

### Regular extensible interfaces/classes

Use when external callers need to create new implementations under a plugin/SPI contract. `sealed` may overly restrict extensibility requirements. If external extension is needed, consider a regular interface or an **intentional** `non-sealed` branch for extension.

### Polymorphism via methods instead of multiple `switch` blocks

If a behavior belongs naturally to each variant and new operations are rarely added, you can declare a method on the interface and implement it in each record, such as `int eval()`. This avoids scattered `switch` blocks.

Conversely, for an AST that needs many independent operations (`eval`, `format`, `optimize`, `serialize`), a sealed record model paired with exhaustive dispatchers is a clear choice. There is no rule that “sealed records are always better than polymorphism”; it is a trade-off between **extending the set of subtypes** and **extending the set of operations**.

## 15. Common compile-time and modeling mistakes

### 15.1. A record cannot extend a class

```java
// DOES NOT COMPILE:
// sealed abstract class Root permits Child {}
// record Child(int x) extends Root {}
```

Records extend `java.lang.Record` and do not allow `extends` in their syntax. Use a `sealed interface` if you want records to implement it directly.

### 15.2. A record cannot be declared `non-sealed` or `sealed`

```java
// DOES NOT COMPILE:
// non-sealed record Num(int value) implements Expr {}
```

Records are implicitly `final`. Users cannot subclass a record, even when the record is a subtype in a sealed hierarchy.

### 15.3. Forgetting `permits` or defining a subtype outside the list

```java
// Given sealed interface Expr permits Num, Sum, Neg;
// DOES NOT COMPILE when added directly:
// record Mul(Expr left, Expr right) implements Expr {}
```

Update the permitted subtype list where the sealed type is defined and verify module/package rules per the JLS.

### 15.4. Missing a branch for a new subtype

If `permits` is updated to add a new subtype but a `switch` expression lacks a corresponding branch and has no catch-all case, the compiler reports it as non-exhaustive. This is a signal to **update the behavior**, not an error to hide immediately with `default -> null`.

### 15.5. Placing a general branch before a specialized branch

```java
// DOES NOT COMPILE:
static String invalid(Expr expr) {
    return switch (expr) {
        case Expr e -> "any expression";
        case Num(int n) -> "number"; // Dominated by the preceding Expr label.
    };
}
```

An unguarded `Expr e` label already covers every non-null `Expr`. Place specific patterns first if needed, or keep only the general branch when subtype dispatch is unnecessary.

### 15.6. Using a record pattern without covering all components

The label `Sum(Num(int a), Num(int b))` only matches a `Sum` containing two `Num`s; it **does not handle all `Sum` instances**. If only a very specific nested branch is present without a general `Sum(Expr left, Expr right)`, the compiler may consider the switch non-exhaustive.

### 15.7. Assuming records automatically reject `null` or invalid values

The default constructor of `record Sum(Expr left, Expr right)` does not reject `null`. If `null` violates an invariant, add a compact canonical constructor and test the failure case.

### 15.8. Confusing exhaustiveness with `null` handling

Even when a `switch` over `Expr` covers `Num`, `Sum`, and `Neg`, a `null` selector still throws an NPE unless `case null` is present. Define clearly whether `null` input is valid and enforce it consistently.

### 15.9. Using records for state with complex mutable resources without care

A record holding a `List`, `Map`, or mutable buffer does not deep-copy it automatically. If immutability matters, use defensive copies or a more appropriate object type.

### 15.10. Confusing direct closure with whole-tree closure

A sealed type can permit a `non-sealed` subtype, opening the hierarchy beneath that branch. If you want all variants to be concrete, finite records, keep direct variants as implicitly `final` records or appropriate `final` classes.

## 16. Exercises with answers

**Exercise 1 — converting a tag-based design to sealed records**

You have a transaction class with a string `kind` (`"CASH"`/`"CARD"`) and frequently null `amount` and `token` fields. Model the two variants without using a string tag.

**Reference answer:**

```java
sealed interface Payment permits Cash, Card {}
record Cash(int amount) implements Payment {}
record Card(String token) implements Payment {}
```

Then write an exhaustive `switch` using type or record patterns. Validation for `amount`/`token` can be added per business requirements.

**Exercise 2 — exhaustiveness**

Given `Expr` consisting of `Num`, `Sum`, and `Neg`, why does a `switch` on an `Expr` parameter with only the three corresponding record pattern branches not need `default`, whereas a `switch` on an `Object` parameter needs an additional branch covering other types?

**Answer:** The static type `Expr` is a sealed hierarchy with a known set of permitted subtypes, so the compiler can verify coverage from `permits`. `Object` is an open type and includes many values that are not `Expr`.

**Exercise 3 — nested records**

For `new Sum(new Num(1), new Neg(new Num(2)))`, which branch matches?

```java
case Sum(Num(int a), Num(int b)) -> "two-nums";
case Sum(Expr left, Expr right) -> "other-sum";
```

**Answer:** The `other-sum` branch, because the right-hand side is `Neg`, not `Num`.

**Exercise 4 — null**

Can `new Sum(null, new Num(1))` be created if the `Sum` record does not declare a validating constructor? Will `case null` in a `switch` on `Expr` catch that `Sum` object?

**Answer:** The default constructor allows `null` components; `case null` only catches a **null selector**, not a non-null record with a `null` component. Validate non-null on record creation if that is an invariant.

**Exercise 5 — generics**

Given `Result<String>` with two generic records `Ok<T>` and `Failure<T>`, why can `case Ok(var value)` give `value` the type `String` without needing a runtime `Class<String>` token?

**Answer:** The static type `Result<String>` and Java 21's generic record pattern type inference give the compiler enough information to infer the type. This is not runtime proof that arbitrary untrusted data from `Object` can be safely treated as `Result<String>`.

**Exercise 6 — adding a subtype**

If you add `Mul` to the `permits` list and recompile, what helps you find missing handlers? Why can adding `default -> "unknown"` to every `switch` be a poor choice?

**Answer:** The compiler can report `switch` expressions that are no longer exhaustive. A catch-all `default` can hide the need to handle the new subtype, leading to incorrect business results.

**Exercise 7 — choosing polymorphism vs. `switch`**

A model only evaluates each node's value, but new node types are added frequently. Should you place an `eval()` method on the interface and implement it in each record?

**Answer:** Yes, if each variant owns its behavior and changes mostly involve adding subtypes. If the requirement is many independent operations over a closed set of subtypes, sealed records + exhaustive `switch` are usually more convenient. Base the decision on the application's axis of extension.

## 17. Pre-production checklist

1. **Is the set of variants known and controlled by the same team?** If not, `sealed` may be too restrictive.
2. **Do the variants carry small payloads describable by components?** Records are a strong fit.
3. **Does any record need to extend a class other than `Record`?** If so, records do not fit; consider regular classes.
4. **Does the `permits` list name the exact direct subtypes and satisfy module/package rules?**
5. **Has each permitted subtype chosen an appropriate `final`/`sealed`/`non-sealed` modifier?** Records are implicitly `final`.
6. **Do any components need non-null checks, numeric bounds, or defensive copies?** Write a constructor.
7. **Does the `switch` accept the sealed parent type or `Object`?** This determines how far the compiler can check exhaustiveness.
8. **Are `case null` and null-component handling clearly separated?**
9. **Does any guarded branch need an unguarded label to cover the remaining values?**
10. **Is a `default` hiding future subtype additions?** If every variant must be handled explicitly, consider removing it.
11. **Are record patterns too deep or hard to read?** If so, use type patterns/accessors or helpers.
12. **Have all variants, constructor failures, nulls, and hierarchy changes been tested?** Manage recompilation of dependent modules to avoid runtime mismatches.

**Conclusion:** combining `sealed interface` + `record` creates a strong Java model for a finite set of variants with distinct data. `sealed` encodes **subtype constraints** into the type system; `record` encodes **data structure** into the declaration; Java 21 record patterns and exhaustive `switch` expressions allow every variant to be handled with minimal boilerplate while prompting the team whenever the model evolves.

## Official references

- [JLS Java SE 21 `9.1 — Interface Declarations`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1): sealed interfaces, permitted direct implementations, and declaration rules.
- [JLS Java SE 21 `8.1.1.2 — sealed, non-sealed, final Classes`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): closed/open states of classes in a hierarchy.
- [JLS Java SE 21 `8.1.6 — Permitted Direct Subclasses`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.6): `permits`, same module/package, and direct subtypes.
- [JLS Java SE 21 `8.10 — Record Classes`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): components, implicit `final`, canonical constructors, and generated members.
- [JLS Java SE 21 `14.30 — Patterns`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns, record patterns, matching, and pattern properties.
- [JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): exhaustiveness checking on sealed hierarchies.
- [JLS Java SE 21 `18.5.5 — Record Pattern Type Inference`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5): generic record pattern inference.
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): sealed coverage examples, record patterns, and hierarchy changes between compile time and runtime.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): record deconstruction and null-handling notes.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
