# Combining Multiple Branches of a Type Hierarchy in Java Pattern Matching

## 1. Why combine multiple branches of a type hierarchy?

In a Java application, a parent type often has multiple sub-groups. For example, an activity logging system has two major branches:

- **AccountAction**: account operations, consisting of `Login` and `Logout`.
- **ServiceSignal**: service signals, consisting of `Ping` and `Fault`.

Both belong to the parent type `Activity`. If handled with multiple `instanceof` checks, type casts, and nested `if/else` branches, type dispatching logic easily becomes entangled with the handling logic for each variant.

**Pattern matching** lets you express type branches using `case`, while combining **type patterns**, **nested record patterns**, and `when` conditions directly at the point where handling is selected.

Lesson objectives:
1. Design and read a **multi-level, multi-branch sealed type hierarchy**.
2. Distinguish matching a **major branch** (`AccountAction`, `ServiceSignal`) from matching a **leaf type** (`Login`, `Logout`, `Ping`, `Fault`).
3. Combine record patterns, type patterns, and guards in the same `switch`.
4. Understand `case` ordering, dominance, exhaustiveness, `null`, and how to maintain code when the hierarchy changes.
5. Know when to use `default`, when to use a single pattern for an entire branch, and when to extract handling into a separate method.

**Java version:** Pattern matching for `switch` (JEP 441) and record patterns (JEP 440) are standard features in **Java 21**. The complete example below uses Java 21 without needing `--enable-preview`. `instanceof` with type patterns has been standard since Java 16.

## 2. Designing a hierarchy with two main branches

Consider the following type structure:

```text
Activity (sealed interface)
├── AccountAction (sealed interface)
│   ├── Login (record)
│   └── Logout (record)
└── ServiceSignal (sealed interface)
    ├── Ping (record)
    └── Fault (record)
```

Corresponding to the Java declarations:

```java
sealed interface Activity permits AccountAction, ServiceSignal {}

sealed interface AccountAction extends Activity
        permits Login, Logout {}

sealed interface ServiceSignal extends Activity
        permits Ping, Fault {}

record Place(String city, String country) {}

record Login(String user, Place place) implements AccountAction {}

record Logout(String user) implements AccountAction {}

record Ping(String service, int latencyMs) implements ServiceSignal {}

record Fault(String service, int status) implements ServiceSignal {}
```

The lines above are **illustrative declaration snippets**; in the complete program in section 4, they are placed inside a class.

`sealed` and `permits` declare the set of direct subtypes allowed to extend a type. Here `Activity` has exactly two direct branches; each branch in turn lists its leaf records. Records are inherently `final`, so there are no new subtypes of each record. Every direct subtype of a `sealed` type must conform to the `final`, `sealed`, or `non-sealed` rule; for the sub-interfaces in the example, we choose `sealed` to continue controlling the type tree.

Important point: **type checking order follows the parent–child relationship**, whereas **guard evaluation order is a condition within each type branch**. These two mechanisms work together, but they do not replace each other.

### Matching a major branch with a type pattern

When you only need to know which group an activity belongs to, you can check at the interface level:

```java
// Illustrative snippet inside a method with parameter Activity activity:
if (activity instanceof AccountAction) {
    System.out.println("ACCOUNT");
} else if (activity instanceof ServiceSignal) {
    System.out.println("SERVICE");
} else {
    System.out.println("NONE");
}
```

For a `Login` or `Logout` object, `instanceof AccountAction` evaluates to `true`. Similarly, `Ping` and `Fault` both belong to `ServiceSignal`. `null` does not match any `instanceof` check.

When you need to reuse the variable as the interface type, you can use a **type pattern**: `activity instanceof AccountAction action`. The variable `action` is bound and used in the matched branch.

### Matching leaf types with record patterns

When you need to read the data of each subtype instead of just checking its group, a `switch` can have cases such as:

```java
case Logout(String user) -> "LOGOUT " + user;
case Ping(String service, int latencyMs) -> "PING " + service;
```

These are **illustrative branches** of a `switch` expression, not a standalone program. The pattern both recognizes the `Logout`/`Ping` record and binds its components for processing.

## 3. Three levels of pattern composition in the same switch

With `Login(String user, Place place)`, you can combine:

```java
case Login(String user, Place(String city, String country))
        when "VN".equals(country) ->
    "LOGIN_VN " + user + "@" + city;
```

Read this branch in order:

1. **Hierarchy branch:** The selector must be the leaf type `Login` under the `AccountAction` branch.
2. **Outer record pattern:** `Login(...)` deconstructs the two components `user` and `place`.
3. **Inner record pattern:** `Place(String city, String country)` requires `place` to be a non-null `Place` and deconstructs the two components of `Place`.
4. **Type patterns:** `String user`, `String city`, and `String country` bind values according to the component types.
5. **Guard:** `when "VN".equals(country)` is true only when `country` equals `"VN"`, without throwing `NullPointerException` when `country` is `null` because `equals` is called on the string literal.

If the guard is false, Java can continue evaluating the next case. If `place` is `null`, the nested `Place(...)` does not match; you need a separate fallback for `Login` if you want to handle that case.

Writing each variant as a case is easier to follow than a chain of casts such as `((Login) activity).place().city()`. However, pattern matching is still a mechanism for reading and inspecting data; it does not make object structures deeply immutable, does not automatically create copies, and does not automatically validate business rules.

## 4. Complete runnable example on Java 21

Create the file **`HierarchyPatternDemo.java`**:

```java
public class HierarchyPatternDemo {
    sealed interface Activity permits AccountAction, ServiceSignal {}

    sealed interface AccountAction extends Activity
            permits Login, Logout {}

    sealed interface ServiceSignal extends Activity
            permits Ping, Fault {}

    record Place(String city, String country) {}

    record Login(String user, Place place) implements AccountAction {}

    record Logout(String user) implements AccountAction {}

    record Ping(String service, int latencyMs) implements ServiceSignal {}

    record Fault(String service, int status) implements ServiceSignal {}

    static String group(Activity activity) {
        if (activity instanceof AccountAction) {
            return "ACCOUNT";
        }
        if (activity instanceof ServiceSignal) {
            return "SERVICE";
        }
        return "NONE";
    }

    static String describe(Activity activity) {
        return switch (activity) {
            case Login(String user, Place(String city, String country))
                    when "VN".equals(country) ->
                "LOGIN_VN " + user + "@" + city;

            case Login(String user, Place(String city, String country)) ->
                "LOGIN " + user + "@" + city + "," + country;

            case Login(var user, var place) ->
                "LOGIN_UNKNOWN_PLACE " + user;

            case Logout(String user) ->
                "LOGOUT " + user;

            case Ping(String service, int latencyMs)
                    when latencyMs < 0 ->
                "PING_INVALID " + service;

            case Ping(String service, int latencyMs)
                    when latencyMs > 100 ->
                "PING_SLOW " + service + "=" + latencyMs + "ms";

            case Ping(String service, int latencyMs) ->
                "PING_OK " + service + "=" + latencyMs + "ms";

            case Fault(String service, int status)
                    when status >= 500 ->
                "FAULT_CRITICAL " + service + "=" + status;

            case Fault(String service, int status) ->
                "FAULT " + service + "=" + status;

            case null -> "NO_EVENT";
        };
    }

    public static void main(String[] args) {
        Activity[] values = {
            new Login("An", new Place("HaNoi", "VN")),
            new Login("Binh", new Place("Paris", "FR")),
            new Login("Chi", null),
            new Logout("Dung"),
            new Ping("search", 45),
            new Ping("api", 125),
            new Ping("queue", -1),
            new Fault("billing", 503),
            new Fault("auth", 401),
            null
        };

        for (Activity value : values) {
            System.out.println(group(value) + " | " + describe(value));
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 HierarchyPatternDemo.java
java HierarchyPatternDemo
```

Expected output:

```text
ACCOUNT | LOGIN_VN An@HaNoi
ACCOUNT | LOGIN Binh@Paris,FR
ACCOUNT | LOGIN_UNKNOWN_PLACE Chi
ACCOUNT | LOGOUT Dung
SERVICE | PING_OK search=45ms
SERVICE | PING_SLOW api=125ms
SERVICE | PING_INVALID queue
SERVICE | FAULT_CRITICAL billing=503
SERVICE | FAULT auth=401
NONE | NO_EVENT
```

Explanation of cases:

| Input | Handling branch | Reason |
| --- | --- | --- |
| `Login("An", Place("HaNoi","VN"))` | `LOGIN_VN` | Nested record pattern matches and country guard equals `VN` |
| `Login("Binh", Place("Paris","FR"))` | `LOGIN` | Nested pattern matches, but the `VN` guard is false |
| `Login("Chi", null)` | `LOGIN_UNKNOWN_PLACE` | Nested `Place(...)` does not match null; fallback `Login(var ...)` receives the record |
| `Logout("Dung")` | `LOGOUT` | Another leaf type in the `AccountAction` branch |
| `Ping("search",45)` | `PING_OK` | Neither guard is true; the unguarded `Ping` case handles it |
| `Ping("api",125)` | `PING_SLOW` | `latencyMs > 100` |
| `Ping("queue",-1)` | `PING_INVALID` | `latencyMs < 0` |
| `Fault("billing",503)` | `FAULT_CRITICAL` | `status >= 500` |
| `Fault("auth",401)` | `FAULT` | Unguarded `Fault` case |
| `null` | `NO_EVENT` | `case null` handles a null selector |

The `group` method distinguishes **the two parent groups** of the hierarchy. The `describe` method drills down into **the leaf types** and combines record patterns/guards. Separating these two responsibilities shows that you can handle things at the appropriate level of abstraction rather than always going down to every leaf type.

Note: in this example, the `switch` expression does not contain `default` because all leaf records in the sealed hierarchy are covered by unguarded cases, alongside `case null`. This differs from `switch` on `Object` or an open hierarchy.

## 5. Exhaustiveness when combining multiple branches

A `switch` expression must be **exhaustive**: at compile time, the compiler must prove that every non-null value of the selector type has a handling branch. A `sealed` hierarchy lets the compiler know the list of valid subtypes.

In this example:
- `Activity` directly permits only `AccountAction` and `ServiceSignal`.
- `AccountAction` permits only `Login` and `Logout`.
- `ServiceSignal` permits only `Ping` and `Fault`.
- The unguarded cases for `Login`, `Logout`, `Ping`, and `Fault` cover their respective leaf types.
- `case null` explicitly handles the null selector case.

Therefore, the example compiles **without needing default**. This is a major benefit of a sealed hierarchy: if you modify the source to add a new subtype without handling it, the compiler can detect that a `switch` expression is no longer exhaustive upon recompilation.

### Guards do not replace a covering case

A case with `when` only handles a subset of values for a subtype:

```java
// Snippet:
case Ping(String service, int latencyMs) when latencyMs > 100 ->
    "SLOW";
```

This case alone is **not enough** to cover every `Ping`. You must add a compatible unguarded case, for example:

```java
// Next snippet:
case Ping(String service, int latencyMs) ->
    "OTHER";
```

Similarly, `Login(String user, Place(...))` does not accept a `Login` with `place == null`. That is why the example includes `case Login(var user, var place)` as a fallback.

### Changes when the hierarchy has a non-sealed branch

If a branch is declared `non-sealed`, other classes can extend that branch, so a few known leaf records are **no longer the entire world**. You can use a type pattern covering the branch, such as `case ExtensionAction e -> ...`, or an appropriate `default`, instead of only listing existing subtypes.

When the selector is declared as `Object`, a regular non-sealed interface, or a parent class with unclosed subtypes, **do not assume** that the listed cases are sufficient. A `default` or an appropriate type pattern case ensures the switch expression handles all remaining types.

### Choosing the matching level

If you only need general information about a group, you can use `case AccountAction action` or `case ServiceSignal signal`. If you need specific data from `Login` and `Logout`, use the leaf-type cases. It is not necessary to list every leaf when the handling logic is genuinely the same.

A parent-branch type pattern placed before child patterns will make those subsequent child branches unreachable; therefore, you need to choose the **handling level** and **order** intentionally.

## 6. Dominance and case ordering

Java checks **dominance**: a general case must not appear before a specific case that it completely covers.

The following example is **intentionally wrong and will not compile** when placed in the same `switch`:

```java
case AccountAction action -> "ACCOUNT";
case Login(String user, Place(var city, var country)) -> "LOGIN";
```

Every `Login` is an `AccountAction`. Because the `AccountAction action` branch already accepts this subtype, the `Login(...)` branch after it can never be selected. The compiler reports a dominated case error.

Similarly:

```java
// Intentionally wrong if placed in this order:
case Ping(String service, int latencyMs) -> "PING";
case Ping(String service, int latencyMs) when latencyMs > 100 ->
    "SLOW_PING";
```

The unguarded `Ping` branch covers every `Ping`, rendering the `SLOW_PING` branch after it ineffective. Place guarded cases before the general case.

**Practical rule:** Order from specific conditions to general ones, then to fallbacks. Siblings in two branches with no inheritance relationship (such as `Login` and `Fault`) do not dominate each other; their relative order is usually a matter of presentation, not something that determines matching results.

## 7. Null and pattern variable scope

### Null in the input

A `switch` on a `null` reference needs explicit handling with `case null` if you want to return a result instead of encountering a `NullPointerException`. A regular `default` does not automatically catch a null selector. With `instanceof`, an expression on null evaluates to `false`.

### Null in nested records

The record `Login("Chi", null)` is a valid `Login` object under the current record definition, but its `place` component is null. It does not match `Place(String city, String country)` because a **record pattern** requires the child object to be non-null.

However, `Login(var user, var place)` still matches: `var place` is an unconditional pattern for a component of type `Place`, so it can bind a null value. Therefore, a `var`-style fallback needs a separate null check if data standards do not allow it.

A type pattern placed at a component with the exact matching type can also be unconditional inside a record pattern. Do not apply this rule mechanically to every type pattern in a broader-typed position; for example, `String text` at a component declared as `Object` does not match `null`.

### Scope

The variables `user`, `city`, and `country` bound by a record pattern can only be used in the `when` guard and the body of the corresponding case; they do not persist in other cases or after the `switch`. In `instanceof` combined with `&&`, they can only be used in places where Java confirms the branch has matched.

Use distinct variable names if multiple components have similar meanings, such as `sourceService` and `targetService`. Avoid declaring duplicate names within the same pattern or referencing variables from an unmatched case.

## 8. Common mistakes when combining hierarchy branches

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Parent case before leaf case | Leaf case is dominated | Move leaf cases needing special handling earlier |
| Using only `when`-guarded cases for a subtype | Fails to cover the entire subtype | Add an unguarded case or an appropriate fallback |
| Assuming a child record cannot be null | Some nested patterns skip the record even though the outer record is valid | Use a fallback case and clear data rules |
| Using `default` instead of `case null` | `switch` may throw `NullPointerException` when the selector is null | Handle null explicitly if the input can be null |
| Omitting `default` for an open hierarchy | Switch expression may not be exhaustive | Use a case covering the open branch or `default` |
| Packing all logic into one very long case | Pattern is hard to read, guard has too many conditions | Extract handling functions by group or subtype |
| Adding a subtype without re-checking switches | Branches need updating; recompilation can catch missing coverage | Recompile and run tests after hierarchy changes |
| Using a record pattern on a non-record class | Syntax/type error | Use a type pattern and regular class methods |

**Do not confuse pattern matching with regular polymorphism:** If behavior primarily belongs to each object and can be expressed well through a common interface method, dynamic dispatch via methods remains appropriate. Pattern matching is useful when the consumer needs to aggregate or transform multiple data shapes, such as rendering, DTO mapping, logging, or handling a protocol with closed variants.

**Do not assume pattern matching is faster than accessor/cast chains.** The primary goal is expressing structure and checking branch coverage. When performance is actually a requirement, measure on the application's processing path.

## 9. Implementation workflow and exercises

When adding multi-branch handling:
1. Draw the type tree, identifying which branches are `sealed` and which remain open.
2. Determine which logic applies to an entire major branch and which logic applies only to leaf subtypes.
3. Use a type pattern at the parent level for shared handling; use a record pattern at the subtype level when components are needed.
4. For nested record patterns, explicitly check the null component case.
5. Place `when` guards before unguarded cases of the same subtype.
6. Ensure the switch expression covers all subtypes and handles a null selector as needed.
7. Test inputs for each branch, guard boundary values, null, new subtypes, and fallback cases.

### Exercise 1: Add a leaf type

Add `record PasswordReset(String user) implements AccountAction {}` and add `PasswordReset` to `AccountAction`'s `permits` list. After declaring it, try recompiling `describe`: observe the error caused by the switch expression lacking coverage without the new case. Add `case PasswordReset(String user) -> "PASSWORD_RESET " + user;` before recompiling.

This exercise demonstrates how a sealed hierarchy helps detect a new unhandled branch.

### Exercise 2: Add a guard to a branch

Add a `Fault` case specifically for `status == 429`, returning the message `"FAULT_THROTTLED <service>"`. Place this case **before** the unguarded `Fault` case, while also considering its position relative to the `status >= 500` guard. Test `429`, `500`, and `400`: each value should route to the right case.

### Exercise 3: Choose the abstraction level

Suppose you want to count the occurrences of `AccountAction` and `ServiceSignal` without caring about subtypes. Compare two approaches: using two type patterns at the interface level, or listing four record patterns at the leaf level. Choose the less repetitive approach for the counting requirement; only use specific patterns when you actually need subtype-specific data.

**Remember:** Combining multiple branches of a type hierarchy is effective when you clearly separate **parent types for grouping**, **leaf types for data processing**, and **guards for value filtering**. With a closed `sealed` tree, Java 21 can check exhaustiveness at compile time. Write specific cases before general cases and always consider null, fallbacks, and hierarchy extensibility.

## References

- Java Language Specification, Java SE 21 — Pattern Matching: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11
- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
