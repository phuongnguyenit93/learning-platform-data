# Visitor Pattern and Pattern Switch in Domain Model Design (Java 21)

When building a **domain model** that has multiple object variants representing the same business concept, we often need to perform many operations on each variant: computation, validation, formatting, converting to DTOs, exporting reports, or generating code. Two familiar ways to organize this are the **Visitor pattern** and **pattern matching for switch**.

- The **Visitor pattern** uses a visitor object that defines operations for each specific type; model elements provide an `accept` method to delegate handling to the visitor.
- **Pattern switch** uses `switch` with *type patterns* or *record patterns* to branch by data type or structure directly inside a method. With a `sealed` model, the compiler can check whether all variants have been handled.

Both help replace long `instanceof` + cast chains with intentional structure. However, **they are not architecturally identical**: Visitor embeds the processing contract into the domain types, whereas pattern switch typically keeps algorithms outside the model and relies on the variant types. This article uses **Java 21 or later**: `sealed` has been available since Java 17, `record` has been stable since Java 16, and pattern matching for `switch` along with record patterns have been stable since Java 21 (JEP 441 and JEP 440).

## 1. The Problem: A Domain Model with Three Expression Forms

Suppose an application manages an arithmetic expression tree. We have three forms:

- `Num(value)`: an integer.
- `Add(left, right)`: the sum of two expressions.
- `Mul(left, right)`: the product of two expressions.

Example expression tree for `(2 + 3) * 4`:

```text
         Mul
        /   \
      Add   Num(4)
     /   \
  Num(2) Num(3)
```

Operations that can evolve independently:

1. **Evaluate**: compute the numeric value (result `20`).
2. **Print**: display the expression with parentheses (`((2 + 3) * 4)`).
3. In the future, we may add condition checking, statistical analysis, or conversion to another representation.

A model compatible with both approaches:

```java
sealed interface Expr permits Num, Add, Mul {
    <R> R accept(Visitor<R> visitor);
}

interface Visitor<R> {
    R visit(Num expr);
    R visit(Add expr);
    R visit(Mul expr);
}

record Num(int value) implements Expr {
    public <R> R accept(Visitor<R> visitor) {
        return visitor.visit(this);
    }
}

record Add(Expr left, Expr right) implements Expr {
    Add {
        java.util.Objects.requireNonNull(left, "left");
        java.util.Objects.requireNonNull(right, "right");
    }

    public <R> R accept(Visitor<R> visitor) {
        return visitor.visit(this);
    }
}

record Mul(Expr left, Expr right) implements Expr {
    Mul {
        java.util.Objects.requireNonNull(left, "left");
        java.util.Objects.requireNonNull(right, "right");
    }

    public <R> R accept(Visitor<R> visitor) {
        return visitor.visit(this);
    }
}
```

The declarations above are **component snippets**; to run directly, use the complete class in section 9.

Explanation of the design choices:

- `sealed interface Expr permits Num, Add, Mul` restricts the direct classes permitted to implement `Expr`. In this illustrative model, all three records are `final` by default, so the set of variants is closed.
- `record` represents data concisely with components and accessors such as `value()`, `left()`, `right()`.
- `Add` and `Mul` validate `left/right` in their compact constructors so the tree has no `null` child branches. This rule is **explicitly enforced by the domain**, not automatic just from using records.
- `accept` serves the Visitor pattern. If choosing a **pattern-switch-only** design, the interface and records can omit `accept` and `Visitor` while keeping the data components and `sealed` constraint.

A `sealed` model makes sense when the set of expression types is controlled within the same library and the author wants the compiler to report missing cases when adding a new form. If the type set needs to be freely extensible by external plugins, a closed model like this may not be suitable.

## 2. Visitor Pattern: Separating Operations from Data Structures

### The Visitor Contract

`Visitor<R>` is an interface with one handler method for **each variant** of `Expr`:

```java
interface Visitor<R> {
    R visit(Num expr);
    R visit(Add expr);
    R visit(Mul expr);
}
```

`R` is the return type of the operation: `Integer` if computing a value, `String` if printing an expression, or another DTO type.

A visitor for evaluating the value:

```java
static final class EvalVisitor implements Visitor<Integer> {
    public Integer visit(Num expr) {
        return expr.value();
    }

    public Integer visit(Add expr) {
        return Math.addExact(expr.left().accept(this),
                             expr.right().accept(this));
    }

    public Integer visit(Mul expr) {
        return Math.multiplyExact(expr.left().accept(this),
                                  expr.right().accept(this));
    }
}
```

`visit(Add)` calls `accept(this)` on both child branches and adds the results. `visit(Mul)` does the same for multiplication. `Math.addExact` and `Math.multiplyExact` throw `ArithmeticException` if `int` overflows; this ensures both implementations in this article follow the same overflow rule.

### How Does Double Dispatch Work?

The key distinction of Visitor is **double dispatch**. Given:

```java
Expr tree = new Add(new Num(2), new Num(3));
int answer = tree.accept(new EvalVisitor());
```

Call flow:

1. `tree.accept(...)` is selected based on the **runtime type** of the element, which here is `Add`.
2. Inside `Add.accept`, the code calls `visitor.visit(this)`. The argument `this` here has type `Add`, so the compiler selects the `visit(Add)` overload.
3. The call to `EvalVisitor`'s implementation performs the addition; the two child branches in turn call `accept` on themselves.

Therefore, the caller does not need to write an `if (expr instanceof Add) ...` chain and does not need to cast the object to `Add`. Specifically: **selecting the `visit(Add)` overload** is based on the static type `Add` of `this` inside `Add.accept`, while invoking the visitor's implementation uses standard virtual dispatch. This is the practical meaning of “double dispatch” in this pattern.

### Adding a New Visitor

If we need to print the formula instead of evaluating it, we only need a new class implementing `Visitor<String>`:

```java
static final class PrintVisitor implements Visitor<String> {
    public String visit(Num expr) {
        return Integer.toString(expr.value());
    }

    public String visit(Add expr) {
        return "(" + expr.left().accept(this) + " + "
                   + expr.right().accept(this) + ")";
    }

    public String visit(Mul expr) {
        return "(" + expr.left().accept(this) + " * "
                   + expr.right().accept(this) + ")";
    }
}
```

On the same tree:

```java
Expr tree = new Mul(
        new Add(new Num(2), new Num(3)),
        new Num(4));
System.out.println(tree.accept(new EvalVisitor()));  // 20
System.out.println(tree.accept(new PrintVisitor())); // ((2 + 3) * 4)
```

This is the main advantage of Visitor: **adding an operation** by creating a new visitor without having to add corresponding business methods to every record type. In return, each model type must have `accept` and the system maintains the `Visitor` contract.

## 3. Pattern Switch: Expressing Operations with a Switch Expression

Starting in Java 21, we can evaluate the tree using `switch` combined with **record patterns**:

```java
static int evalBySwitch(Expr expr) {
    return switch (expr) {
        case Num(int value) -> value;
        case Add(var left, var right) ->
                Math.addExact(evalBySwitch(left), evalBySwitch(right));
        case Mul(var left, var right) ->
                Math.multiplyExact(evalBySwitch(left), evalBySwitch(right));
    };
}
```

Key benefits:

- `case Num(int value)` checks for a `Num` record and extracts `value` directly, without needing `Num n = (Num) expr`.
- `case Add(var left, var right)` deconstructs the two `Expr` components; `var` **infers the static type** from the record declaration.
- For each branch, `evalBySwitch` recurses on the sub-expressions. The algorithm is equivalent in result to `EvalVisitor`.
- No `visit` or `accept` is needed if the architecture does not use Visitor.
- No `default`: because `Expr` is `sealed` and all three variants `Num`, `Add`, `Mul` are handled, the compiler can prove the **switch expression is exhaustive** for non-`null` `Expr` values.

This is not merely a rewritten chain of casts. The compiler understands **pattern variables** scoped validly within the corresponding `case` branch, so `left`, `right`, and `value` are already bound before use.

### Type Pattern or Record Pattern in Switch?

If you need the record object itself, use a **type pattern**:

```java
static int readNum(Object value) {
    return switch (value) {
        case Num num -> num.value();
        default -> -1;
    };
}
```

If you need the components directly, use a **record pattern**:

```java
static int readNumParts(Object value) {
    return switch (value) {
        case Num(int number) -> number;
        default -> -1;
    };
}
```

The two methods above are **illustrative examples** that need to be placed in a class containing the `Num` record. Both accept a `Num` and return its integer value. However, with `switch (value)` when `value == null`, the examples above have no `case null` so they will throw `NullPointerException`; `default` does not match a `null` selector by default. This differs from `instanceof`, which returns `false` for `null`.

## 4. Exhaustiveness When the Domain Model Is Sealed

Suppose `Expr` has only the three types listed in `permits`, and the subclasses are all `final`. When switching on `Expr`, the compiler knows the set of cases that must be handled.

```java
return switch (expr) {
    case Num(int value) -> value;
    case Add(var left, var right) -> evalBySwitch(left) + evalBySwitch(right);
    case Mul(var left, var right) -> evalBySwitch(left) * evalBySwitch(right);
};
```

*This is a structural illustration; the full program uses `Math.addExact`/`Math.multiplyExact` to detect overflow.*

If a new variant is added later, such as `Negate(Expr child)`, and `permits` is updated accordingly, a `switch` without `default` will typically trigger a compiler error for **not being exhaustive** until a `Negate(...)` case is added. This helps locate algorithms that need updating as the domain evolves.

With Visitor, if `Visitor<R>` is extended with `visit(Negate expr)`, concrete implementations such as `EvalVisitor` and `PrintVisitor` must also be updated to fulfill the new contract. The new variant's `accept` will call the matching overload. **Both approaches have mechanisms to detect missing handlers, though the compile errors appear in different places.**

**Do not add `default` just to silence the compiler** when the variant set is genuinely controlled by `sealed`: a `default` branch can mask an unsupported new type. Only add a fallback when the domain truly requires valid behavior for unlisted types, or when the model allows open extension.

### `when` Guards and Case Ordering

Pattern switch also allows additional conditions:

```java
static String describeNumber(Expr expr) {
    return switch (expr) {
        case Num(int value) when value < 0 -> "negative";
        case Num(int value) -> "number=" + value;
        case Add(var l, var r) -> "addition";
        case Mul(var l, var r) -> "multiplication";
    };
}
```

This is an **illustrative method** for the same model. The `Num` branch with `when` precedes the general `Num` branch; if reversed, the broader branch would shadow the specific one and Java would report a *dominance* error.

A branch with a `when value < 0` guard **does not cover all `Num` instances on its own**. Therefore, the unguarded `Num(int value)` branch (or another sufficiently broad handler) is still required to ensure the switch is exhaustive.

## 5. Null and Domain Invariants

There are two kinds of `null` to handle separately.

### Null in the Switch Selector

With `evalBySwitch(Expr expr)` above, calling:

```java
evalBySwitch(null);
```

will throw `NullPointerException` because the pattern-matching `switch` has no `case null`. If `null` is allowed and has business meaning, specify it explicitly:

```java
static String kindOrMissing(Expr expr) {
    return switch (expr) {
        case null -> "none";
        case Num(var value) -> "number";
        case Add(var left, var right) -> "addition";
        case Mul(var left, var right) -> "multiplication";
    };
}
```

With Visitor, calling `expr.accept(visitor)` when `expr == null` also throws `NullPointerException` at the method invocation. If both algorithms must share the same `null` policy, design a shared contract and handle it explicitly at the caller level.

### Null in Child Records

`record Add(Expr left, Expr right)` does not forbid `null` references by default. In this article's model, the **compact constructor** checks `Objects.requireNonNull(left, "left")` and similarly for `right`, so `new Add(null, new Num(1))` is rejected at construction time.

This is a **domain invariant**. Thanks to it, both the Visitor and recursive pattern switch algorithms can assume the branches of `Add`/`Mul` are valid. If the constructor check were removed, the record pattern `Add(var left, var right)` could still match an `Add` with `left == null`: `var left` is a *component pattern* that can bind `null`. Then the recursive call `evalBySwitch(left)` would encounter a `null` selector and throw an exception. Therefore, **matching a record pattern does not mean all record components are non-null**.

## 6. Visitor vs. Pattern Switch: Strengths and Limitations

| Criterion | Visitor pattern | Pattern switch on sealed/record |
| --- | --- | --- |
| Where behavior is defined | Separate `Visitor` classes; `Expr` requires `accept` | Inside the method containing `switch`, usually outside domain types |
| Branch selection | `accept` + `visit` (double dispatch) | Runtime pattern matching via `case` |
| Adding a new operation | Create a new `Visitor<R>` implementation | Create a new method or service with a `switch` |
| Adding a domain variant | Update visitor interface, visitor implementations, and `accept` on the new variant | Add subtype, update exhaustive switches that do not yet handle it |
| Boilerplate | Many `accept`/`visit` methods | Minimal boilerplate with `record` and `sealed` |
| Result per operation | Type `R` of `Visitor<R>` | Return type of the method/`switch expression` |
| Null selector | Calling `null.accept(...)` throws NPE | `switch(null)` throws NPE if there is no `case null` |
| Completeness guarantee | Compiler checks required methods against the visitor contract | Compiler checks exhaustiveness/dominance of the switch |
| Language version | Visitor pattern works in older Java versions | Examples with record patterns and pattern switch require Java 21+ |

This is a comparison of **code organization**, not a claim that one is always faster than the other. Actual performance depends on tree structure, allocation rate, JIT, visitor implementation, and algorithm workload; run representative benchmarks if performance is a real concern.

### When to Choose Visitor

Visitor makes sense when:

- There are many independent operations over a relatively stable set of types.
- You want to represent operations as objects that can be configured, dependency-injected, hold state, or shared across APIs.
- An existing model already exposes an `accept`/`Visitor` contract and many parts of the system depend on it.
- The project must still support a Java version prior to Java 21, so modern pattern switch cannot be used.

**Trade-off:** each variant must implement `accept`; when adding a variant to the visitor interface, all corresponding visitors must be updated.

### When to Choose Pattern Switch

Pattern switch usually makes sense when:

- The domain is a **closed set of variants** modeled with `sealed interface`/`sealed class`.
- The variants are mostly data (`record`) and need pure algorithms without adding dispatch methods to them.
- You want to read the logic in one place, see each branch directly, and let the compiler check for missing cases.
- The project uses Java 21+ and algorithms can be implemented as small, easy-to-test functions/services.

**Trade-off:** each operation still needs its own set of cases. If the tree structure is very deep or the logic is complex, extract helper functions rather than letting one `switch` turn into a huge block of code.

### Can Both Be Used Together?

Yes. The example in this article intentionally uses **the same model** with `accept` for Visitor and also uses `evalBySwitch` externally. This is useful when **gradually migrating from legacy Visitor code to pattern switch** or when comparing results.

However, do not force every domain type to implement Visitor only to never use `accept`. Choose one approach as the default for the module; maintain both in parallel only when there is a specific goal and behavioral comparison tests.

## 7. Avoiding Refactors That Change Semantics

When converting Visitor to pattern switch (or vice versa), do not just compare results on a single simple tree. Consider:

1. **Tree traversal order.** Addition and multiplication in the demo evaluate the left branch then the right branch. If operations have side effects, reversing the order changes behavior.
2. **Null constraints.** The invariant `left/right != null` lives in the constructor; if one approach handles `null` silently while the other throws an exception, the two algorithms are not equivalent.
3. **Overflow and business errors.** Both Visitor and switch in this article use `Math.addExact`/`Math.multiplyExact`; replacing them with `+` and `*` can change results on `int` overflow.
4. **Permitted subtypes.** `sealed` closes the variant set; if the domain is extended via plugins, design an extension mechanism instead of a closed set of cases.
5. **Visitor state.** A visitor may hold state, caches, or service dependencies. Converting it to a pure `switch` function may require passing that state as parameters or moving it to a service.
6. **Exceptions and logging.** Preserve ordering, messages, and error policies when they are part of the contract.
7. **Exhaustiveness.** Do not use a broad `default` to hide newly added subtypes.

For large applications, test with the same suite of trees (single-node tree, deeply nested tree, negative numbers, zero, boundary values, error cases) before removing the legacy Visitor.

## 8. Complete Java 21 Program: Both Approaches on the Same Domain

Save the file **`VisitorVsPatternSwitch.java`**:

```java
public class VisitorVsPatternSwitch {
    sealed interface Expr permits Num, Add, Mul {
        <R> R accept(Visitor<R> visitor);
    }

    interface Visitor<R> {
        R visit(Num expr);
        R visit(Add expr);
        R visit(Mul expr);
    }

    record Num(int value) implements Expr {
        public <R> R accept(Visitor<R> visitor) {
            return visitor.visit(this);
        }
    }

    record Add(Expr left, Expr right) implements Expr {
        Add {
            java.util.Objects.requireNonNull(left, "left");
            java.util.Objects.requireNonNull(right, "right");
        }

        public <R> R accept(Visitor<R> visitor) {
            return visitor.visit(this);
        }
    }

    record Mul(Expr left, Expr right) implements Expr {
        Mul {
            java.util.Objects.requireNonNull(left, "left");
            java.util.Objects.requireNonNull(right, "right");
        }

        public <R> R accept(Visitor<R> visitor) {
            return visitor.visit(this);
        }
    }

    static final class EvalVisitor implements Visitor<Integer> {
        public Integer visit(Num expr) {
            return expr.value();
        }

        public Integer visit(Add expr) {
            return Math.addExact(expr.left().accept(this),
                                 expr.right().accept(this));
        }

        public Integer visit(Mul expr) {
            return Math.multiplyExact(expr.left().accept(this),
                                      expr.right().accept(this));
        }
    }

    static final class PrintVisitor implements Visitor<String> {
        public String visit(Num expr) {
            return Integer.toString(expr.value());
        }

        public String visit(Add expr) {
            return "(" + expr.left().accept(this) + " + "
                       + expr.right().accept(this) + ")";
        }

        public String visit(Mul expr) {
            return "(" + expr.left().accept(this) + " * "
                       + expr.right().accept(this) + ")";
        }
    }

    static int evalBySwitch(Expr expr) {
        return switch (expr) {
            case Num(int value) -> value;
            case Add(var left, var right) ->
                    Math.addExact(evalBySwitch(left), evalBySwitch(right));
            case Mul(var left, var right) ->
                    Math.multiplyExact(evalBySwitch(left), evalBySwitch(right));
        };
    }

    static String kindOrMissing(Expr expr) {
        return switch (expr) {
            case null -> "none";
            case Num(var value) -> "number";
            case Add(var left, var right) -> "addition";
            case Mul(var left, var right) -> "multiplication";
        };
    }

    public static void main(String[] args) {
        Expr tree = new Mul(
                new Add(new Num(2), new Num(3)),
                new Num(4));
        int visitorValue = tree.accept(new EvalVisitor());
        int switchValue = evalBySwitch(tree);

        System.out.println("visitor eval=" + visitorValue);
        System.out.println("switch eval=" + switchValue);
        System.out.println("visitor format=" + tree.accept(new PrintVisitor()));
        System.out.println("same=" + (visitorValue == switchValue));
        System.out.println("zero=" + evalBySwitch(new Add(new Num(-5), new Num(5))));
        System.out.println("kind=" + kindOrMissing(tree));
        System.out.println("null kind=" + kindOrMissing(null));

        try {
            evalBySwitch(null);
        } catch (NullPointerException ex) {
            System.out.println("null eval rejected");
        }

        try {
            new Add(null, new Num(1));
        } catch (NullPointerException ex) {
            System.out.println("null child rejected=" + ex.getMessage());
        }
    }
}
```

Compile and run with **JDK 21 or newer**:

```bash
javac --release 21 -encoding UTF-8 VisitorVsPatternSwitch.java
java VisitorVsPatternSwitch
```

**Exact stdout:**

```text
visitor eval=20
switch eval=20
visitor format=((2 + 3) * 4)
same=true
zero=0
kind=multiplication
null kind=none
null eval rejected
null child rejected=left
```

Explanation:

- The tree `Mul(Add(Num(2), Num(3)), Num(4))` represents `(2 + 3) * 4`. Both `EvalVisitor` and `evalBySwitch` return `20`.
- `PrintVisitor` formats the tree recursively as `((2 + 3) * 4)`.
- `same=true` compares the two algorithms on the same input; `zero=0` demonstrates adding a negative and a positive number.
- `kindOrMissing(tree)` recognizes the `Mul` type; `kindOrMissing(null)` hits the `case null` branch.
- `evalBySwitch(null)` has no `case null` branch, so it throws `NullPointerException`, which is caught and prints `null eval rejected`.
- The `Add` constructor uses `Objects.requireNonNull(left,"left")`, so attempting to create `Add(null,...)` is rejected with the message `left`.

The program was verified with `javac --release 21` and actually run with the output shown above.

## 9. Common Mistakes

1. **Confusing Visitor and pattern switch as the same syntax.** Visitor is an interface-based design pattern using `accept`/`visit` methods; pattern switch is a Java 21 language feature.
2. **Keeping an open model while expecting switch to always be exhaustive without a fallback.** `sealed` clarifies the subtype set; if a subtype branch remains open (`non-sealed`), classification logic must account for values belonging to that open branch.
3. **Adding `default` to dodge errors when the model gains a subtype.** That defeats the compiler's ability to enforce handling the new variant. Add a specific case if that is the design intent.
4. **Placing a broad case before a specific case.** `case Expr e` can shadow subsequent `Num(...)` and `Add(...)` cases; a shadowed branch will cause the compiler to report a dominance error.
5. **Assuming `case null` in a switch handles null in all components.** `case null` only catches the **selector** of that `switch` itself. Record components need their own policy.
6. **Assuming a record pattern can never extract `null`.** A `var left` component pattern can bind a `null` component reference. Enforce input constraints in the constructor or check before recursing.
7. **Omitting `public` on `accept` when implementing the interface.** Interface methods are `public`; the record's implementation must also provide a method with compatible access visibility.
8. **Forgetting to add `visit` when adding a subtype.** The Visitor interface and all implementations must be maintained to support the new type.
9. **Confusing `var` with dynamic typing.** In `Add(var left,var right)`, the compiler infers `left` and `right` to have type `Expr` from the record definition; runtime values are checked during matching.
10. **Comparing Visitor and switch on only a single happy path.** Check `null`, nested cases, overflow, exceptions, and formatted output.
11. **Running code with record patterns on Java 17 and expecting default support.** `switch` pattern matching and record patterns in this article require Java 21+.

## 10. Practice Exercises

**Exercise 1.** Why does `evalBySwitch` not need `default` in the example?

*Answer:* `Expr` is `sealed`, permitting only the three records `Num`, `Add`, and `Mul` at the direct level, and they are all final variants; every non-`null` form of `Expr` is handled by the corresponding cases.

**Exercise 2.** If `record Negate(Expr child) implements Expr` is added to the model and included in `permits`, what needs attention?

*Answer:* Add `case Negate(...)` to exhaustive switches; for Visitor, extend the contract with `visit(Negate)`, update all visitor implementations, and implement `accept` on the new record. Also enforce `child != null` if required by the domain.

**Exercise 3.** Why does `record Add(Expr left, Expr right)` have `Objects.requireNonNull` in its constructor, while the record pattern `Add(var left,var right)` itself can still match a null component?

*Answer:* The constructor proactively enforces the invariant **when creating the object**. `Add(var left,var right)` only deconstructs components; a `var` component pattern does not exclude `null` if the data allows it. In the given program, the constructor blocks creating `Add` with a null child through normal instantiation.

**Exercise 4.** Can the same model use both `PrintVisitor` and `evalBySwitch`?

*Answer:* Yes. One operation is performed via `accept/visit`, and the other via `switch`; the subclasses do not need to change. However, avoid maintaining two duplicate processing systems long-term unless there is a specific need.

**Exercise 5.** Write `sizeBySwitch(Expr expr)` yourself to return the number of nodes in the tree. For `Mul(Add(Num(2), Num(3)), Num(4))`, the result must be **5**.

*Hint:*

```java
static int sizeBySwitch(Expr expr) {
    return switch (expr) {
        case Num(var value) -> 1;
        case Add(var left, var right) ->
                1 + sizeBySwitch(left) + sizeBySwitch(right);
        case Mul(var left, var right) ->
                1 + sizeBySwitch(left) + sizeBySwitch(right);
    };
}
```

This snippet is a method added to the class with the declared records, not a standalone Java file.

**Official documentation:** [JEP 409 – Sealed Classes](https://openjdk.org/jeps/409), [JEP 395 – Records](https://openjdk.org/jeps/395), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).