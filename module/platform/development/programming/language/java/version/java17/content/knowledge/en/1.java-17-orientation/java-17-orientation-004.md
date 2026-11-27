# The Relationship Between `sealed`, `record`, and Pattern Matching in Java 17

In Java 17, `sealed`, `record`, and pattern matching can be combined to model a set of results or states with a controlled number of variants, where each variant carries its own data and is handled according to its specific type. The three features solve **three different problems**:

- **`sealed`** answers: *Which types are allowed to inherit from or implement this root type?*
- **`record`** answers: *How is a data-carrying variant declared concisely, clearly, and consistently?*
- **Pattern matching with `instanceof`** answers: *When given a value of the root type, how do you identify the concrete variant and use it without manual casting?*

They are **not dependent on one another**: a `record` does not have to belong to a `sealed` hierarchy; a `sealed` hierarchy can contain regular classes; and `instanceof` pattern matching works with many reference types, not just `record`. Their combination is especially useful when representing a **sum type** (*a value belonging to one of several variants*) together with **product types** (*each variant bundling multiple data components*).

## 1. Status of These Features in Java 17

| Feature | Stably Usable in Java 17? | Meaning |
| --- | --- | --- |
| `record` | Yes; finalized in Java 16 | Declares data-carrier classes with automatically generated constructor, accessors, `equals`, `hashCode`, and `toString`. |
| `sealed class` / `sealed interface` | Yes; finalized in Java 17 | Restricts which direct subtypes may inherit or implement. |
| Pattern matching for `instanceof` | Yes; finalized in Java 16 | Combines type testing and binding a safely cast pattern variable. |
| Pattern matching for `switch` | **Not yet a finalized feature in Java 17** | Only in *preview* in Java 17; finalized in Java 21. |
| Record patterns, e.g. `case Point(int x, int y)` | **No finalized support in Java 17** | Deconstructs record components via patterns; finalized in Java 21. |

All runnable Java 17 examples below use only **finalized** features, without needing `--enable-preview`. When reading documentation written for Java 21 or later, distinguish a **type pattern** (`instanceof Success s`) from a **record pattern** (`Success(var value)`): record patterns cannot be used in standard Java 17 code.

## 2. Problem: One Result with Multiple Data Shapes

Suppose a login operation returns exactly one of three outcomes:

1. **Success**: includes a user ID and display name.
2. **Wrong password**: includes the number of remaining attempts.
3. **Account locked**: includes the lock reason.

If you use a single object with optional fields `success`, `userId`, `remainingAttempts`, and `lockReason`, the program can construct nonsensical combinations: succeeding while also having a lock reason, or failing with a wrong password while still carrying a `userId`. A clearer approach is to declare **one root type and variants with distinct structures**:

```text
LoginResult (sealed interface)
├── LoggedIn       (record: userId, displayName)
├── WrongPassword  (record: remainingAttempts)
└── Locked         (record: reason)
```

`LoginResult` defines the valid direct variants; each `record` defines the data for its variant; and `instanceof` handles values when the concrete variant is not known at compile time.

### Complete, runnable Java 17 example

Save the following code as `LoginDemo.java`:

```java
import java.util.Objects;

public class LoginDemo {

    public sealed interface LoginResult
            permits LoggedIn, WrongPassword, Locked {
    }

    public record LoggedIn(long userId, String displayName)
            implements LoginResult {

        public LoggedIn {
            if (userId <= 0) {
                throw new IllegalArgumentException("userId must be positive");
            }

            displayName = Objects.requireNonNull(displayName, "displayName").strip();
            if (displayName.isEmpty()) {
                throw new IllegalArgumentException("displayName must not be blank");
            }
        }
    }

    public record WrongPassword(int remainingAttempts)
            implements LoginResult {

        public WrongPassword {
            if (remainingAttempts < 0) {
                throw new IllegalArgumentException("remainingAttempts must be non-negative");
            }
        }
    }

    public record Locked(String reason)
            implements LoginResult {

        public Locked {
            reason = Objects.requireNonNull(reason, "reason").strip();
            if (reason.isEmpty()) {
                throw new IllegalArgumentException("reason must not be blank");
            }
        }
    }

    public static String render(LoginResult result) {
        Objects.requireNonNull(result, "result");

        if (result instanceof LoggedIn success) {
            return "Login succeeded: "
                    + success.displayName() + " (#" + success.userId() + ")";
        }

        if (result instanceof WrongPassword failure) {
            return "Wrong password; " + failure.remainingAttempts() + " attempts remaining";
        }

        if (result instanceof Locked locked) {
            return "Account locked: " + locked.reason();
        }

        // if/instanceof is not checked for variant exhaustiveness in Java 17.
        throw new IllegalStateException(
                "Unhandled result type: " + result.getClass().getName());
    }

    public static void main(String[] args) {
        System.out.println(render(new LoggedIn(7, " Lan ")));
        System.out.println(render(new WrongPassword(2)));
        System.out.println(render(new Locked("Login limit exceeded")));
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 LoginDemo.java
java LoginDemo
```

Output:

```text
Login succeeded: Lan (#7)
Wrong password; 2 attempts remaining
Account locked: Login limit exceeded
```

This example also illustrates a record's **compact constructor**: constructor parameters can be validated or normalized (`strip()`), after which Java automatically assigns the final values to the record's component fields. `displayName()` and `remainingAttempts()` are generated accessors, not `getDisplayName()` and `getRemainingAttempts()`.

## 3. `sealed`: Controlling the Branches of the Model

With the declaration:

```java
sealed interface LoginResult permits LoggedIn, WrongPassword, Locked {}
```

the compiler only allows **the types listed in `permits`** to directly implement `LoginResult`. For instance, `class Guest implements LoginResult {}` will fail to compile if `Guest` is not on the permitted list. This tells the API author what direct result forms can exist and prevents external code from arbitrarily adding a new variant to a closed interface.

A direct subtype of a `sealed` type must declare how it continues the inheritance policy:

| Subtype Declaration | Effect |
| --- | --- |
| `final class` or `record` | Cannot have further subtypes; `record` is **implicitly `final`**. |
| `sealed class` / `sealed interface` | Continues restricting direct subtypes at the next level. |
| `non-sealed class` / `non-sealed interface` | Reopens inheritance or implementation along that branch. |

Short example:

```java
sealed interface Message permits TextMessage, ExtensibleMessage {}

record TextMessage(String text) implements Message {}

non-sealed interface ExtensibleMessage extends Message {}

class CustomMessage implements ExtensibleMessage {}
```

Here `Message` has only two **direct** subtypes, yet the hierarchy can still be extended through `ExtensibleMessage`. Thus, `sealed` does not automatically mean every grandchild/descendant class of the root type is finitely enumerated. When you want a truly closed set of variants, leaf branches usually use `record` or `final class`, avoiding `non-sealed`.

Important constraints in Java 17:

- Types listed in `permits` must **directly** extend or implement the `sealed` type, not merely indirectly.
- In a **named module** (with `module-info.java`), the root type and its permitted subtypes must be in the same module; in the **unnamed module**, they must be in the same package.
- If the subtypes are declared in the same compilation unit, the `permits` clause can be inferred, though writing it explicitly makes the structure easier to read.
- `sealed` restricts **the right to create subtypes**, not who can instantiate objects of subtypes with accessible constructors; nor is it an authentication or authorization mechanism.

**Why did the main example use `sealed interface`?** A record always extends `java.lang.Record`, so it cannot extend an arbitrary class. However, a record **can `implements` an interface**. Consequently, `sealed interface` is usually the natural choice when all variants are records. If you need to share implementation or state across a hierarchy of regular classes, a `sealed abstract class` remains valid, though record branches cannot `extends` that class.

## 4. `record`: Packaging Different Data for Each Variant

Consider:

```java
record WrongPassword(int remainingAttempts) implements LoginResult {}
```

Java generates a `private final` backing field, the corresponding canonical constructor, the `remainingAttempts()` accessor, plus `equals`, `hashCode`, and `toString` based on the record components. For example, two `new WrongPassword(2)` instances have `equals()` return `true`, whereas `new WrongPassword(1)` differs.

Because a record is `final`, another type cannot alter `WrongPassword`'s structure by subclassing it. This is why records fit **leaf variants** of a `sealed` hierarchy: each branch has an explicit type and clear data.

### Records do not guarantee deep immutability

A record stores component references in `final` fields; if a component points to a mutable object, that object's contents can still change. For instance, `record Tags(List<String> values) {}` does not stop callers from mutating an `ArrayList` passed in. When you want data protected against unintended mutation, perform **defensive copying**:

```java
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    public Tags {
        values = List.copyOf(Objects.requireNonNull(values, "values"));
    }
}
```

`List.copyOf` creates a list that cannot be modified via the `List` API (and also rejects `null` elements), but it **does not deep-copy** mutable objects inside the list. With arrays or mutable nested structures, consider copying in both the constructor and accessor if you want to avoid exposing internal state. Record-generated `equals()` also does **not** compare arrays element-by-element: array components still follow standard array equality, which is identity-based unless you override it.

### When should you not choose a record?

Records fit return values, messages, commands, configuration values, or read-only data with a fixed structure. An object with a **mutable-state lifecycle**, one that needs class inheritance, or one that must conform to a framework's proxy/no-arg constructor mechanism may be better served by a regular class. `sealed` does not have to pair with records: a `final class` branch is completely valid when its behavior and state are better implemented that way.

## 5. Pattern Matching: Working with the Concrete Variant

Before pattern matching for `instanceof`, checking a type and casting had to be written as two operations:

```java
if (result instanceof LoggedIn) {
    LoggedIn success = (LoggedIn) result;
    System.out.println(success.displayName());
}
```

In Java 17, you can write:

```java
if (result instanceof LoggedIn success) {
    System.out.println(success.displayName());
}
```

`success` is a **pattern variable** of static type `LoggedIn`, in scope only where the compiler's flow analysis determines the match succeeded. Reading data via `success.displayName()` therefore requires no manual cast.

A pattern variable can also appear in compound conditions using `&&`:

```java
if (result instanceof LoggedIn success && success.userId() > 0) {
    System.out.println(success.displayName());
}
```

The right-hand operand is evaluated only when the left-hand `instanceof` holds. You cannot assume `success` is in scope in arbitrary other branches or across an `||` expression where the right-hand side might run when the match failed. Variable scope is governed by **flow scoping**, not simply by curly braces.

**Important distinction:** `instanceof LoggedIn success` in Java 17 only matches the **type** and provides a type-checked reference. It does **not deconstruct** `userId` and `displayName` into separate variables; to extract each component, you still call `success.userId()` and `success.displayName()`. Component deconstruction via *record patterns* was standardized in Java 21.

### Can the compiler automatically check that all branches are handled?

**No, not with an `if (x instanceof ...)` chain in Java 17.** Even though `LoginResult` allows only three variants, the compiler does not force `render` to check all three branches. If `Expired` is later added to `permits`, the existing `render` method will still compile and only throw `IllegalStateException` when encountering the new value. Therefore, audit all variant-handling sites whenever you modify the type hierarchy; an explicit fallback exception helps catch omissions at runtime.

An `instanceof` condition also **never matches `null`**. In the example, `Objects.requireNonNull(result, "result")` states the input contract explicitly, preventing `null` from reaching an unintended branch.

## 6. Relationship to `switch` Across Java Versions

In Java 17, the stable way to branch on **variant types** is `instanceof` pattern matching. Traditional `switch` remains suitable for `enum` values, strings, or other types supported by Java 17 `switch` expressions, but **there is no finalized type-pattern `switch` syntax (`case LoggedIn s -> ...`)**.

In newer versions:

- **Java 21** finalized pattern matching for `switch`, enabling `case LoggedIn success -> ...` and other type-based cases.
- **Java 21** finalized record patterns, allowing matching and deconstructing record components inside patterns.
- With pattern-matching `switch`, the compiler can use information from a `sealed` hierarchy to check **exhaustiveness** across valid branches. Handling of `null` must still be considered explicitly when an API permits `null`.

In Java 17, pattern matching for `switch` was still in *preview*; preview syntax and behavior evolved across subsequent Java releases. When building Java 17 applications that must be stable and maintainable, use finalized features as in the example above rather than pasting Java 21 `switch` examples into Java 17 code or relying on outdated preview syntax.

## 7. How Does `sealed` + `record` Differ from `enum`?

Both `enum` and `sealed` are useful for expressing a controlled set of cases, yet they model data differently:

| Requirement | `enum` | `sealed interface` + `record`s |
| --- | --- | --- |
| Fixed constants like `NEW`, `RUNNING`, `DONE` | Very natural | Often unnecessary |
| Each case carries **different associated data types** | Requires designing extra fields/behavior and validity rules manually | Natural: each record declares its own exact components |
| Creating multiple instances with different data for the same variant | Enum constants are fixed singleton instances | You can instantiate `new LoggedIn(...)` or `new WrongPassword(...)` repeatedly |
| Using `switch` for exhaustiveness checking in Java 17 | Supported, especially with `switch` expressions | Type-based `switch` over sealed types is not finalized in Java 17 |
| Controlling direct inheritance branches | Enums cannot serve as arbitrary open type hierarchies | Supports `permits`, `final`, `sealed`, `non-sealed` |

If you only need three statuses **without different payloads**, such as `PENDING`, `APPROVED`, and `REJECTED`, an `enum` is usually simpler. If success must carry a `userId` while failure must carry a `reason`, three records implementing a `sealed interface` model each case's structure much more accurately.

## 8. Extended Example: A Recursive Expression Tree

The login result model is a business-domain example; these three features are equally useful for modeling syntax, rules, or hierarchical structures. An addition expression tree can consist of an **integer literal** or the **sum of two expressions**:

```java
public class ExpressionDemo {
    sealed interface Expr permits NumberExpr, AddExpr {}

    record NumberExpr(int value) implements Expr {}

    record AddExpr(Expr left, Expr right) implements Expr {}

    static int evaluate(Expr expression) {
        if (expression instanceof NumberExpr number) {
            return number.value();
        }
        if (expression instanceof AddExpr add) {
            return evaluate(add.left()) + evaluate(add.right());
        }
        throw new IllegalArgumentException("Unsupported expression");
    }

    public static void main(String[] args) {
        Expr expression = new AddExpr(new NumberExpr(10), new NumberExpr(32));
        System.out.println(evaluate(expression)); // 42
    }
}
```

Here:

- `Expr` clearly states the valid direct node types in this tiny expression language.
- `NumberExpr` and `AddExpr` carry different data components yet are treated uniformly as `Expr`.
- `evaluate` selects behavior based on the runtime type; the `AddExpr` branch recurses on its two child expressions.

Because `AddExpr` holds `Expr` children, a tree can nest arbitrarily deeply without introducing arbitrary types outside the permitted list. If the structure is built from external input, you still need to validate inputs (for example, disallowing `null` for `left` or `right`) and watch recursion depth; `sealed` by itself does not enforce those invariants.

## 9. Common Design Mistakes and Misconceptions

1. **Assuming `sealed` makes `if/else` exhaustive automatically.** Java 17 does not enforce exhaustiveness across `instanceof` chains; adding a new variant requires updating handling code.
2. **Assuming `record` is deeply immutable.** Mutable objects such as lists, maps, and arrays still require appropriate copying and publication strategies.
3. **Assuming a `record` must `extends` a `sealed class`.** Records cannot extend another class; combine them using a `sealed interface` instead.
4. **Using `non-sealed` in a hierarchy intended to be completely closed.** `non-sealed` allows additional subtypes to appear under that branch.
5. **Calling `getX()` or accessing record fields directly like traditional DTO classes.** A record's standard accessor is `x()`, and its backing fields are `private`.
6. **Using Java 21 record pattern or type-pattern `switch` syntax in Java 17 sources.** Those features were not finalized in Java 17; the project's target language version must be kept clear.
7. **Using `sealed` for an API intentionally meant for third-party subtyping.** That is an open extension contract; `permits` restrictions can break the intended extension point.
8. **Stuffing unrelated status fields into one record to merge every outcome.** If fields are only valid for specific outcomes, define distinct variants with their own payloads.

## 10. How to Choose and Combine Them in Practice

When designing a Java 17 API, ask in order:

1. **Is there a finite set of cases controlled by the development team?** If yes, consider a `sealed interface` for the root type. If API consumers need to define their own subtypes, a regular interface may fit better.
2. **Does each case primarily carry clear, rarely changing data?** If yes, use a `record` for leaf variants. If it has mutable state and a complex lifecycle, consider a `final class` or an appropriate class hierarchy.
3. **Do the variants have different payloads, or are they just named states?** For simple labels, an `enum` may suffice. For per-variant payloads, `sealed` plus records is usually clearer.
4. **How should each variant be handled in Java 17?** Use `instanceof` type patterns, call record accessors, and throw a clear exception on unhandled cases; update those sites whenever `permits` expands.

**Remember the relationship:** `sealed` **closes the set of direct subtypes**, `record` **describes each case's data**, and pattern matching **identifies the concrete type when processing**. In Java 17, this trio provides a clear, type-safe way to model multi-variant data, while record pattern deconstruction and exhaustive type-pattern `switch` belong to newer Java releases.
