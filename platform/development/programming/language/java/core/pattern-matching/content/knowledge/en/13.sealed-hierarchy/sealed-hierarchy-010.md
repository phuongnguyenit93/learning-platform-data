# Risks When a Sealed Hierarchy Changes in Java Pattern Matching

A **sealed hierarchy** allows Java to restrict which classes or interfaces may directly extend or implement a type. Thanks to the `permits` list, the Java 21 compiler can verify that a pattern-matching `switch` is **exhaustive** (covering all possible subtypes) without requiring a `default` branch.

This is very useful when designing a domain with a well-defined set of cases. However, when the hierarchy is modified—adding a subtype, removing a subtype, opening a `non-sealed` branch, or changing a subtype—`switch` statements and expressions that depend on the old structure can be affected. In particular, **a previously compiled program can still link against the new library yet throw `MatchException` when encountering a new subtype that has no matching branch**.

> **Keep in mind:** "Exhaustive at compile time" does not mean "automatically handles every future version of the hierarchy." Changing a sealed hierarchy is a change to the type contract and requires checking **source recompilation**, **runtime compatibility**, and **the business meaning of each case**.

This article analyzes the risks, verification methods, and design strategies in **Java Core Pattern Matching**. The `sealed`, `permits`, and `non-sealed` syntax has been stable since **Java 17**; pattern matching for `switch` and `case null` have been stable since **Java 21**. Programs with type patterns in `switch` require JDK 21+.

## 1. Why Does `sealed` Help the Compiler Determine Exhaustiveness?

Suppose an API defines two event types:

```java
sealed interface Event permits Added, Removed {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}
```

Here, `Event` permits only two **direct permitted subtypes**: `Added` and `Removed`. Both are `record` types, so both are implicitly `final`: they cannot have any further subclasses.

Java 21 accepts:

```java
static String describe(Event event) {
    return switch (event) {
        case Added a -> "added:" + a.id();
        case Removed r -> "removed:" + r.id();
    };
}
```

Even without `default`, the `switch expression` is still exhaustive because every valid non-`null` object of type `Event` in the current hierarchy must be either `Added` or `Removed`.

This guarantee relies on **compile-time type information**. It is not an automatic check that updates itself when another JAR containing a new version of `Event` is swapped into the runtime environment.

### Scope of `permits`

A sealed class/interface lists **the types permitted to inherit from it directly**, not a list of every object that will ever exist. Each valid direct subtype must take one of the following forms:

- **`final`**: disallows further inheritance; a `record` is implicitly `final`.
- **`sealed`**: continues restricting permitted subtypes at the next level.
- **`non-sealed`**: allows this branch to be extended by other subclasses.

Direct permitted subtypes must follow Java's location/module rules: they must be in the same named module, or in the same package if using the unnamed module. When changing a hierarchy, you must compile the corresponding type declarations, not merely edit a name in `permits`.

## 2. Initial Java 21+ Program: Exhaustive, Without `default`

Save **`SealedExhaustiveDemo.java`**:

```java
sealed interface Event permits Added, Removed {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}

public class SealedExhaustiveDemo {
    static String describe(Event event) {
        return switch (event) {
            case Added a -> "added:" + a.id();
            case Removed r -> "removed:" + r.id();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Added("A7")));
        System.out.println(describe(new Removed("B2")));

        try {
            System.out.println(describe(null));
        } catch (NullPointerException ex) {
            System.out.println("null: NullPointerException");
        }
    }
}
```

Compile and run:

```bash
javac SealedExhaustiveDemo.java
java SealedExhaustiveDemo
```

Output:

```text
added:A7
removed:B2
null: NullPointerException
```

**Two distinct points:** All subtypes are covered, so the compiler does not require `default`. However, `null` **is not a subtype of `Event`**; when the `switch` selector is `null` and there is no `case null`, Java throws `NullPointerException`. Do not conflate the null-handling issue with the issue of adding a new subtype.

If the API allows `null`, you can add `case null`. If `null` is disallowed, validate at the boundary with `Objects.requireNonNull` or maintain a contract that rejects invalid values.

## 3. When the Library Adds a Subtype: Two Completely Different Scenarios

The next version of the model wants to support an update event as well:

```java
// Version V2 of the model:
sealed interface Event permits Added, Removed, Updated {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}
record Updated(String id) implements Event {}
```

Now `Event` has an additional permitted direct subtype. An old `switch` that only handles `Added`/`Removed` faces two risks depending on how it is deployed.

### 3.1. Recompiling the Old Client Against the New Library

```java
// DOES NOT COMPILE with Event V2:
static String describe(Event event) {
    return switch (event) {
        case Added a -> "added:" + a.id();
        case Removed r -> "removed:" + r.id();
    };
}
```

The compiler sees that `Updated` can also occur, so it reports that the `switch expression` **does not cover all possible input values**. This is a *non-exhaustive switch* error at **compile time**. It is a useful signal: the developer must decide how `Updated` should be handled.

A good fix is to **add an explicit case** for the new type, rather than adding `default -> "unknown"` just to silence the compiler error.

### 3.2. Keeping the Old Client Binary While Deploying the New Library

Another scenario can be more dangerous:

```text
Library V1: Event permits Added, Removed
    |
    +--> Client V1 is compiled:
         switch(Event) { case Added; case Removed; }
         Compiler concludes: exhaustive
    |
    v
Library V2: Event permits Added, Removed, Updated
    |
    +--> Replace library V1 with V2
         but DO NOT recompile client V1
    |
    v
Client V1 receives an Updated instance
    |
    +--> No case matches
         -> may throw java.lang.MatchException
```

According to the Oracle Java 21 documentation, when a `switch` was deemed exhaustive by the compiler, yet at runtime encounters a value that matches no pattern due to **separate compilation** and a modified hierarchy, it can throw **`MatchException`**.

This **does not contradict** the fact that adding a permitted subtype can remain *binary compatible*: the old class can still link against the new library, but its exhaustiveness assumption is stale when an instance of the new subtype flows through the old `switch`.

| Action | Situation | Consequence |
| --- | --- | --- |
| Recompile client with library V2 | Old cases are missing `Updated` | Compiler reports non-exhaustive |
| Run client binary V1 with library V2 | Receives `Updated`, no matching case | May throw `MatchException` |
| Recompile client after adding `case Updated` | All subtypes are handled | Compiles successfully |
| Client already had `default` | Receives `Updated` at runtime | May run fallback, depending on the written policy |
| Client only receives `Added`/`Removed` as before | Has not encountered the new subtype yet | May continue running normally, but the risk still exists |

**Do not assume every version upgrade throws `MatchException`.** The exception occurs when an execution path encounters a value not handled by the cases. A broad pattern or an existing `default` can match the new subtype.

## 4. Proper Update: Handle the New Subtype Explicitly

Save **`EvolvedHierarchyDemo.java`**:

```java
sealed interface EvolvedEvent permits NewAdded, NewRemoved, Updated {}

record NewAdded(String id) implements EvolvedEvent {}
record NewRemoved(String id) implements EvolvedEvent {}
record Updated(String id) implements EvolvedEvent {}

public class EvolvedHierarchyDemo {
    static String describe(EvolvedEvent event) {
        return switch (event) {
            case null -> "missing";
            case NewAdded a -> "added:" + a.id();
            case NewRemoved r -> "removed:" + r.id();
            case Updated u -> "updated:" + u.id();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new NewAdded("A7")));
        System.out.println(describe(new Updated("C3")));
        System.out.println(describe(null));
    }
}
```

```bash
javac EvolvedHierarchyDemo.java
java EvolvedHierarchyDemo
```

Output:

```text
added:A7
updated:C3
missing
```

Every direct subtype of `EvolvedEvent` has a case; `null` has its own branch. We still do not need `default`. If a fourth subtype is added and recompiled, the compiler can again detect any incomplete handling sites.

In a real application, it is not necessary to rename all types when adding a subtype. The names `EvolvedEvent`/`NewAdded`/`NewRemoved` in this example only keep the program self-contained and avoid name collisions with the V1 sample program.

## 5. How Does Binary Compatibility Differ from Migration Compatibility?

This is a point where many resources on sealed hierarchies are easily misread.

**Binary compatibility** means a previously compiled binary continues to link with a library change according to JVM/JLS rules. Under the Java 21 JLS, **adding a permitted direct subtype** to a sealed class/interface is a change that can be **binary compatible** with old binaries.

**Source recompilation compatibility** is a different question: when recompiling client source against the new types, are all compile-time requirements still satisfied? A `switch` missing the new subtype may no longer be exhaustive, so **recompilation fails** until the cases are updated.

**Migration compatibility** considers whether an old program behaves correctly when run with the new version of the library. A `switch` compiled against the old set of subtypes may encounter the new subtype and throw `MatchException`, or execute a fallback that is wrong for the business logic.

In short:

```text
Binary compatible:
    the old binary may still link

Source recompilation:
    an old switch may no longer be exhaustive and fail to compile

Migration compatible:
    you must check what the old binary will do when the new subtype appears
```

Therefore, **"does not break binary compatibility" is not a guarantee of "does not affect runtime behavior."** When maintaining an API with distributed consumers, both aspects must be checked.

### What If a Subtype Is Removed from `permits`?

The reverse change also carries risk. If a direct subtype is removed from the permitted set, yet **an old binary of that subtype is still loaded**, Java can throw **`IncompatibleClassChangeError`** because the old class is no longer permitted to directly inherit from the sealed parent. This is a linkage/inheritance error, not the same `MatchException` mechanism of an exhaustive switch.

Do not lump "adding a subtype" and "removing a subtype" into a single compatibility rule; the JLS has distinct rules for each kind of evolution of a sealed class/interface.

## 6. `default`: Convenient for Compatibility, but Can Hide Missing-Case Bugs

A common approach is to add a fallback:

```java
static String describe(Event event) {
    return switch (event) {
        case Added a -> "added:" + a.id();
        case Removed r -> "removed:" + r.id();
        default -> "unknown";
    };
}
```

In the V1 hierarchy, `default` might never process any valid object other than special cases. However, after `Updated` is added, the `switch` above still compiles cleanly and routes `Updated` into `default`.

**Benefits:**

- Provides a policy for subtypes not yet known to the consumer.
- Can prevent falling into an unmatched-case state at that specific `switch` site.
- Useful at boundaries receiving differently versioned data, if "unknown type" is a handleable state.

**Dangers:**

- The compiler **no longer forces you to update the cases** when an important subtype is added.
- `default -> "unknown"` can silently discard the meaning of the new type.
- For domains that must process every event accurately, a fallback that drops data can be worse than throwing an exception.
- `default` **does not accept a `null` selector**; if `null` is valid, you still need `case null` or `case null, default` according to policy.

For example, an `Updated` event might need to update an order's status. If `default` simply returns `"ignored"`, the program does not crash, yet the business state becomes wrong. Thus, **compile success alone is not proof of correct logic**.

## 7. Intentional Fail-Fast Fallback

When a system must run across multiple versions without silently mishandling a new subtype, `default` can be used to throw an informative error.

Save **`ExplicitFallbackDemo.java`**:

```java
sealed interface Event permits Added, Removed {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}

public class ExplicitFallbackDemo {
    static String describe(Event event) {
        return switch (event) {
            case null -> "missing";
            case Added a -> "added:" + a.id();
            case Removed r -> "removed:" + r.id();
            default -> throw new IllegalStateException(
                    "Unknown subtype: " + event.getClass().getSimpleName());
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Added("A7")));
        System.out.println(describe(new Removed("B2")));
        System.out.println(describe(null));
    }
}
```

```bash
javac ExplicitFallbackDemo.java
java ExplicitFallbackDemo
```

Output:

```text
added:A7
removed:B2
missing
```

If a new subtype becomes valid after the library is updated and enters a client binary containing this `default` branch, it will be rejected with an `IllegalStateException` carrying the subtype's name rather than silently receiving a bogus result like `"unknown"`.

**Important:** In the current sample program, `Event` does not yet include `Updated`, so do not pretend that output for the new subtype was executed in this version. This is the **intended policy when the hierarchy evolves**.

`event.getClass()` is safe inside the `default` branch of this example because `case null` is already declared. If the selector is `null` without `case null`, the `switch` itself throws an NPE before reaching `default`.

**Trade-off:** Using a fail-fast `default` makes runtime errors easier to diagnose, but it **does not replace the benefit of exhaustiveness checking upon recompilation**. Authors must proactively review contracts when adding subtypes.

## 8. The `non-sealed` Branch and Its True Extension Scope

Not every sealed hierarchy is completely closed at the leaf-class level. For example:

```java
sealed interface Notice permits Heartbeat, PluginNotice {}

record Heartbeat(int sequence) implements Notice {}
non-sealed class PluginNotice implements Notice {}
```

Because of `non-sealed`, developers can add subclasses of `PluginNotice` without modifying `permits` on `Notice`:

```java
final class ExtraNotice extends PluginNotice {}
```

A `switch` with a `case PluginNotice p` branch **covers subclasses** of `PluginNotice` as well, including ones added later:

```java
static String route(Notice notice) {
    return switch (notice) {
        case Heartbeat h -> "heartbeat:" + h.sequence();
        case PluginNotice p -> "plugin";
    };
}
```

If all plugin notices share one handling strategy, this is a reasonable way for a sealed hierarchy to still allow controlled extension along one branch.

### Complete Java 21+ Example

Save **`NonSealedBranchDemo.java`**:

```java
sealed interface Notice permits Heartbeat, PluginNotice {}

record Heartbeat(int sequence) implements Notice {}
non-sealed class PluginNotice implements Notice {}
final class ExtraNotice extends PluginNotice {}

public class NonSealedBranchDemo {
    static String route(Notice n) {
        return switch (n) {
            case null -> "missing";
            case Heartbeat h -> "heartbeat:" + h.sequence();
            case PluginNotice p -> "plugin";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(new Heartbeat(9)));
        System.out.println(route(new ExtraNotice()));
        System.out.println(route(null));
    }
}
```

```bash
javac NonSealedBranchDemo.java
java NonSealedBranchDemo
```

Output:

```text
heartbeat:9
plugin
missing
```

If `AnotherNotice extends PluginNotice` is introduced, `case PluginNotice` can still accept it. However, if a new plugin notice requires different handling, an overly broad case risks masking the new business requirement. **Type coverage does not equal semantically correct handling.**

When listing only a few concrete subclasses of `PluginNotice` without a case for the open branch itself, the compiler may consider the `switch` non-exhaustive. This reflects the fact that a `non-sealed` branch allows unknown subtypes to appear.

## 9. Types of Changes That Require Special Attention

| Hierarchy change | Risk to check |
| --- | --- |
| Add a direct subtype to `permits` | Old exhaustive `switch` is missing a case on recompile; old binaries may hit `MatchException` |
| Add a subtype within a deeper sealed branch | Does a `switch` handling only the old leaves miss the new type? |
| Add a subclass of `non-sealed` | Does the `non-sealed` branch case catch the new subclass and handle it properly? |
| Remove a direct subtype from `permits` | Will an old binary of the subtype fail when loaded (`IncompatibleClassChangeError`)? |
| Change `final`, `sealed`, or `non-sealed` | Does it widen or narrow the set of permitted runtime types? |
| Convert a closed hierarchy to open inheritance | Do `switch` statements/expressions relying on exhaustiveness still compile? |
| Change generic bounds or type arguments | Does type coverage on a generic sealed selector change? |
| Add a guarded `when` pattern | Can the guard be false, affecting exhaustiveness and subsequent cases? |
| Add a broad pattern or `default` | Could new subtypes be handled generically, or could a case suffer from dominance? |

A `switch` does not necessarily have to have **one case per direct subtype name**. Java checks **type coverage**; a broad pattern can cover multiple subtypes. For generic sealed types, the compiler also considers the selector's type argument to determine which subtypes actually apply. Therefore, risk analysis should be based on **the selector type, subtype relations, and the specific cases**, rather than just counting entries in `permits`.

## 10. Impact on `when` Guards and Dominance

Suppose we wrote:

```java
static String classify(Event event) {
    return switch (event) {
        case Added a when a.id().startsWith("A") -> "priority-add";
        case Added a -> "add";
        case Removed r -> "remove";
    };
}
```

*This is an illustrative method; it must be placed in an environment where `Event`/`Added`/`Removed` are defined.*

In the initial hierarchy, there is an unguarded `Added` case handling all remaining `Added` values, along with `Removed`. However, when `Updated` is added, a guard on `Added` **cannot cover `Updated`**. The compiler can report non-exhaustive upon recompilation.

A `when` guard only **restricts the condition under which an already-matched pattern applies**. It does not automatically accept all subtypes in a sealed hierarchy. If a guard can evaluate to `false`, the remaining branches must still cover the unmatched values to satisfy exhaustiveness.

In addition, when adding new cases:

- Place narrower patterns before broader unguarded patterns to avoid dominance errors.
- Placing a broad unguarded pattern earlier can cause the compiler to reject a subtype case that follows it.
- `when true` is treated similarly to an unguarded pattern for dominance checks; normal guards can evaluate to false.
- Check `null` selectors separately: `case null` is not replaced by a guarded type pattern.
- Do not add `default` just to silence compiler errors before knowing how the new subtype should be handled.

## 11. Distinguishing `MatchException`, NPE, and Linkage Errors

| Error name | Typical cause | What to do |
| --- | --- | --- |
| `MatchException` | A `switch` was considered exhaustive at compile time, but no pattern matches at runtime—for example, due to a modified sealed hierarchy | Compare client binary and model versions; inspect the actual runtime subtype value |
| `NullPointerException` | The `switch` selector is `null` without `case null` | Verify the null contract; add handling or reject null inputs explicitly |
| `IncompatibleClassChangeError` | An old class is no longer permitted to directly inherit from the new sealed parent, or another linkage compatibility rule is violated | Check `permits`, JARs, module path, and class loaders |
| `IllegalStateException` thrown by the program | A fail-fast `default` received an unsupported value | Read the message; check whether a new case or policy update is needed |
| Non-exhaustive compile error | The `switch` in source does not cover the new type domain | Add cases or a fallback according to business requirements |

**Not every `MatchException` is caused by adding a subtype.** Java 21 also has cases where exhaustive pattern matching fails due to nested record patterns or a `null` component not matching the declared patterns. Always inspect the stack trace, pattern types, actual data, and hierarchy versions before drawing a conclusion.

And **`default` is not `catch`**: if the selector expression or a guard throws an exception, Java does not jump to `default` to recover.

## 12. Three Design Choices When You Know the Hierarchy Will Evolve

### A. No `default`: Let the Compiler Enforce Handling Every Subtype

```java
return switch (event) {
    case Added a -> handleAdded(a);
    case Removed r -> handleRemoved(r);
};
```

*This snippet assumes `handleAdded` and `handleRemoved` return compatible types.*

Suitable when the domain is genuinely closed, each subtype has distinct logic, and all consumers can be recompiled. When a subtype is added, the non-exhaustive error forces an update. Trade-off: old client binaries may hit `MatchException` if deployed with the new library without being rebuilt.

### B. Fail-Fast `default`: Helps Detect Runtime Version Skew

```java
return switch (event) {
    case Added a -> handleAdded(a);
    case Removed r -> handleRemoved(r);
    default -> throw new IllegalStateException(
            "Unhandled Event subtype: " + event.getClass().getName());
};
```

Suitable for versioned API systems that may encounter unknown subtypes yet **must not silently ignore them**. Failure behavior is clearer and easier to monitor. Trade-off: the compiler will not flag missing cases when a subtype is added because `default` is present; review and testing processes must compensate for this.

### C. Pattern for an Extension Branch: Polymorphism/Strategy

```java
return switch (notice) {
    case Heartbeat h -> handleHeartbeat(h);
    case PluginNotice p -> handleAnyPlugin(p);
};
```

Suitable if all subtypes of `PluginNotice` share one policy, or a polymorphic handler is invoked from this branch. In return, you must verify that new subtypes are not mishandled by the generic branch.

You do not have to apply a single strategy across the entire system. Core domain logic can be exhaustive without `default`, integration boundaries can use an explicit fallback, and extension points can use a `non-sealed` branch.

## 13. Risks in Multi-Version Deployments

Many systems do not deploy libraries and clients simultaneously:

- The model/SDK is upgraded, while consumers still run classes compiled against the old model.
- A rolling deployment can have instances running different versions at the same time.
- A new producer starts emitting a new event subtype while some consumers do not support it yet.
- Caches, queues, or databases store data from another version, which is later deserialized into the new subtype.
- An adapter/plugin adds a subclass of a `non-sealed` branch outside the set of subtypes the consumer was tested with.

In each situation, **running unit tests on the new model alone is not enough**. Dependent consumers must be recompiled and tested, especially exhaustive `switch` statements in older builds.

Another pitfall is thinking "the new version didn't crash, so it's safe." If a new subtype falls into `default -> "ignored"`, the system may silently drop business data. Explicitly define the policy for unknown subtypes: return an unsupported-marked result, log and quarantine for later processing, or fail fast depending on the contract.

## 14. Checklist for Safely Upgrading a Sealed Hierarchy

When preparing to change `permits` or the subtype structure:

1. **Find all consumers of the sealed type**, including `switch` statements/expressions, `instanceof` chains, serializers, handler registries, and adapters.
2. **Classify the exact change:** adding a direct subtype, removing a subtype, opening a `non-sealed` branch, or modifying a multi-level hierarchy.
3. **Recompile consumers against the new dependency.** Do not compile only the module that defines the sealed type.
4. **Handle non-exhaustive errors intentionally.** Add new cases that reflect business logic, not just a `default` to bypass the error.
5. **Test every existing subtype and the new subtype.** Verify both return values and side effects, not merely that the code runs without throwing.
6. **Test version skew if rolling releases are used:** old client + new library, and new client + old library where applicable.
7. **Check `null` independently.** `null` is not a subtype; handle it via `case null` or a non-null contract.
8. **Verify `non-sealed` branches.** Test with a new subclass not present in the previous test suite to confirm the broad pattern truly applies the right policy.
9. **Check the classpath/module path and stale artifacts.** A subtype removed from `permits` whose binary still remains can cause linkage errors.
10. **Define unknown-type behavior at boundaries.** Do not silently ignore important data; provide logging/metrics and useful error messages.
11. **Monitor after deployment:** watch for `MatchException`, unknown subtypes, and unexpected fallback hits.
12. **Maintain regression tests.** Every time a subtype is added, add tests for proper consumer handling—even when `switch` has a `default`.

### Self-Check Table

```text
[ ] Build clients against the new sealed hierarchy
[ ] Every valid subtype has verified behavior
[ ] New subtypes are not mishandled by default or a generic handler
[ ] Test old binary + new library if two versions can coexist
[ ] null selector has an explicit policy
[ ] non-sealed branch intentionally supports or rejects new subclasses
[ ] No stale JAR/module remains that violates permits
[ ] Logging, alerts, or tests exist for MatchException/unknown subtypes
```

## 15. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "It's sealed, so the subtype list never changes." | The library owner can still release a new version with a different `permits` clause |
| "If it's exhaustive, it can never throw `MatchException`." | Runtime can encounter a new subtype after separate compilation; old exhaustiveness becomes stale |
| "Adding a subtype definitely breaks binary compatibility." | The JLS considers adding a permitted direct subtype binary compatible with old binaries under the right conditions, though migration risks exist |
| "An old client working with old subtypes means it supports the new subtype." | The problem only surfaces when execution actually receives the unhandled subtype |
| "Adding `default` is always better." | `default` can mask missing-case bugs and cause business logic defects |
| "Without `default`, it can never compile." | A sealed hierarchy lets a `switch expression` be exhaustive without `default` |
| "`non-sealed` completely breaks exhaustiveness." | A case on the `non-sealed` branch type itself can cover all its descendants |
| "`MatchException` means the same thing as `NullPointerException`." | They are different exceptions; a `null` selector without `case null` causes NPE |
| "Adding `case null` is enough for any hierarchy change." | `case null` only handles `null`, not new subtypes |
| "No crash means the logic is still right." | A generic fallback can silently mishandle the new subtype |

## Conclusion

A **sealed hierarchy** improves type safety by allowing the compiler to prove that a `switch` is exhaustive, but that guarantee depends on **the version of the hierarchy at compile time**. When the hierarchy changes:

- **Recompiling** with a new subtype can produce a **non-exhaustive** error and force you to update your cases.
- **Keeping an old client binary while deploying a new library** can lead to **`MatchException`** if runtime delivers a new subtype with no matching branch.
- **Adding `default`** can provide a fallback, but it can also hide missing cases; use it according to business policy, not merely to make code compile.
- **Use a `non-sealed` branch** when you genuinely need an extension point; cover the broad branch and test behavior with new subtypes.

Combine **rebuilding all consumers**, testing multiple version combinations, handling each subtype intentionally, and monitoring at runtime to avoid turning a "binary compatible" type change into an application failure.

## Official References

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): exhaustive switch with sealed types and `MatchException` scenarios when a hierarchy evolves.
- [Oracle Java 21 — MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): definition and separate-compilation failure cases.
- [JLS Java 21 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html): rules on changing `permits`, binary compatibility, and migration compatibility.
- [Oracle Java 21 — Sealed Classes](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html): `sealed`, `final`, `non-sealed`, and inheritance restrictions.
