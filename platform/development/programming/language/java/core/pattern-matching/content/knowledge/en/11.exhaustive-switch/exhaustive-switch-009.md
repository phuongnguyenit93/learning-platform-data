# MatchException and Runtime Hierarchy Changes

In **Java 21**, a `switch` can be recognized by the compiler as **exhaustive** (covering all cases) thanks to information about a `sealed` hierarchy or `enum` constants. However, if **the code containing the `switch` is not recompiled**, while the library defining the hierarchy has changed and been deployed at runtime, the program may encounter a value that **does not match any case**. When that happens, Java can throw **`java.lang.MatchException`**.

This is not a contradiction: the compiler checked exhaustiveness based on **the set of types visible at compile time**. The JVM, on the other hand, executes based on **the classes actually loaded at runtime**. When these two sets of information diverge due to *separate compilation* and out-of-sync library upgrades, the exhaustiveness that was once proven may no longer hold for runtime data.

Key topics in this lesson:

- Distinguish **compile-time exhaustiveness** from **runtime branch selection**.
- Know when Java 21 throws `MatchException`, and when it throws `NullPointerException` or other class linkage errors.
- Reproduce the error by **compiling an old `switch`**, then extending the `sealed` hierarchy **without recompiling the `switch`**.
- Handle this properly in systems with multiple modules, JARs, or independently deployed versions.

## 1. What is `MatchException`?

`java.lang.MatchException` appeared as an official API starting in **Java 21**. It is an **unchecked exception**, specifically a `final` class extending `RuntimeException`.

It indicates that **pattern matching failed in an unexpected way**. A typical case: a `switch` construct was considered exhaustive at compile time, but no case applies to a value that appears at runtime.

Conceptual example:

```java
// Point A: the compiler only sees First and Second.
switch (event) {
    case First first -> handleFirst(first);
    case Second second -> handleSecond(second);
}

// Point B: at runtime Third is added, but the old switch is still used.
// If event is actually Third, no case matches => MatchException.
```

This is **illustrative code**, not a standalone program. The condition to understand is that `First`, `Second`, and `Third` are all compatible subtypes of a hierarchy that allows adding the `Third` subtype in a new version; the `switch` was only compiled against the old version.

**Not all `MatchException`s are caused by hierarchy changes.** Java 21 also has cases involving **nested record patterns** and `null` in a component, or errors when invoking a record accessor during deconstruction. However, runtime hierarchy changes are a very important scenario when upgrading libraries and deploying multiple modules.

## 2. The core idea: two points in time have two different views

Imagine an application with two parts:

- **Library** containing `sealed interface Event` and its permitted implementation classes.
- **Client** containing a `switch` branching on each subtype of `Event`.

At **the first compilation**, library v1 defines:

```text
Event (sealed)
├── Start (final)
└── Stop  (final)
```

Client v1 uses:

```java
return switch (event) {
    case Start s -> "start";
    case Stop s -> "stop";
};
```

Because `Event` only permits `Start` and `Stop`, the Java 21 compiler can prove that the `switch` expression on `Event` is **exhaustive for all non-null Event objects**. No `default` is needed.

Later, library v2 adds a subtype:

```text
Event (sealed)
├── Start (final)
├── Stop  (final)
└── Pause (final)   <-- new
```

If the client **still runs the bytecode compiled from v1**:

- When receiving `Start` or `Stop`, the old cases can still handle them normally.
- When receiving `Pause`, there is no case in the client bytecode for the new subtype.
- If class loading and other linkages are valid, the "no case matches" path can end with a **`MatchException`**.

Thus, `MatchException` can appear **even though the original program compiled successfully and passed exhaustiveness checking**. It is a sign that an assumption the compiler once accepted no longer reflects runtime reality.

## 3. Full demo: compiling the library and client separately

Here is how to reproduce it using **JDK 21**, without needing `--enable-preview`. Perform this in **a separate test directory**, not on a library serving production.

### Step 1 — Create v1 of the hierarchy

File **`Event.java`**:

```java
public sealed interface Event permits Start, Stop {
    static Event sample() {
        return new Start();
    }
}
```

File **`Start.java`**:

```java
public final class Start implements Event {}
```

File **`Stop.java`**:

```java
public final class Stop implements Event {}
```

`sealed` restricts the direct subtypes that `Event` permits. The direct implementors `Start` and `Stop` are declared `final`, so no further subtypes can be derived through them.

### Step 2 — Create a client that only knows v1

File **`Client.java`**:

```java
public class Client {
    static String describe(Event event) {
        return switch (event) {
            case Start ignored -> "start";
            case Stop ignored -> "stop";
        };
    }

    public static void main(String[] args) {
        try {
            System.out.println(describe(Event.sample()));
        } catch (MatchException unexpected) {
            System.out.println("MatchException");
        }
    }
}
```

Here `Client.describe` is an **exhaustive switch expression**, because the compiler sees that `Event` only permits `Start` and `Stop`.

The `catch` block is intentionally **only for keeping stdout stable in the demo**. In real applications, you should not use `catch (MatchException)` as a normal business branch to replace updating the hierarchy and handlers.

Compile both library v1 and the client into the `out` directory:

```bash
javac --release 21 -d out Event.java Start.java Stop.java Client.java
java -cp out Client
```

Output of running v1:

```text
start
```

At this point, `out/Client.class` is bytecode generated **according to Event v1 information**.

### Step 3 — Change the hierarchy to v2

**Replace the entire content** of `Event.java` with version v2:

```java
public sealed interface Event permits Start, Stop, Pause {
    static Event sample() {
        return new Pause();
    }
}
```

**Add a new file** `Pause.java`:

```java
public final class Pause implements Event {}
```

Keep `Start.java` and `Stop.java` unchanged, **and keep `Client.java` unchanged**.

The crucial point: **only recompile the library**, do not include `Client.java` in the next `javac` command, and do not delete `out/Client.class`:

```bash
javac --release 21 -cp out -d out Event.java Start.java Stop.java Pause.java
java -cp out Client
```

Output of running **old client + library v2**:

```text
MatchException
```

Because `Event.sample()` v2 returns `Pause`, `Client.describe` compiled at v1 encounters a subtype for which it has no handling branch. `MatchException` is caught in `main` and prints a single line, so there is no stack trace in this demo's stdout. If you remove `catch`, the program will terminate with an unhandled exception and stack trace information printed by the JVM to the error stream.

This demonstrates **separate compilation**: multiple files/classes are compiled at different times and then assembled into a running application. **Do not delete and recompile the entire `out` directory at this step** if the goal is to reproduce the error; otherwise the compiler will detect the missing `Pause` case before running.

### Step 4 — Fix the client and recompile

In `Client.describe`, update the `switch`:

```java
static String describe(Event event) {
    return switch (event) {
        case Start ignored -> "start";
        case Stop ignored -> "stop";
        case Pause ignored -> "pause";
    };
}
```

This is a replacement method inside `Client.java`, not a standalone file. Then:

```bash
javac --release 21 -cp out -d out Client.java
java -cp out Client
```

Output:

```text
pause
```

If at v2 you **recompile the client without adding the `Pause` case**, the compiler will report that the `switch` expression is not exhaustive. That is **desirable** feedback: a design oversight is caught at build time instead of waiting until runtime.

## 4. Why can changing `permits` cause an error even when old classes still exist?

For a `sealed` interface/class, the `permits` list defines which types are allowed to directly implement/extend it. The compiler uses this information during exhaustiveness checking.

Adding `Pause` does not necessarily make `Start` or `Stop` disappear or cause loading `Event` v2 to fail. The application can start up and work normally in many situations. **Only when a `Pause` instance reaches the old `switch`** does the problem surface as a missing branch.

This differs from changes that make classes no longer link validly, such as deleting a class or changing the hierarchy so that an old class is no longer permitted to implement the sealed type. In those cases, the JVM may throw **`NoClassDefFoundError`, `IncompatibleClassChangeError`, or another appropriate linkage error** before reaching the `switch`. You should not lump all library upgrade errors into `MatchException`.

The key distinction is that **`MatchException` reflects a pattern selection failure of a construct that was supposed to be exhaustive**, not a general message saying "every binary change causes this exception".

## 5. The same thing can happen with enums

A `switch` expression on an enum can be exhaustive when it lists every constant the compiler knows about:

```java
enum Mode { READ, WRITE }

static String modeName(Mode mode) {
    return switch (mode) {
        case READ -> "read";
        case WRITE -> "write";
    };
}
```

This is an illustrative snippet placed inside a class. If a new version of the enum adds `ARCHIVE`, but the class containing `modeName` **is not recompiled** and runtime passes `Mode.ARCHIVE`, the old `switch` expression can throw `MatchException`.

Why? The compiler of the old version confirmed that `READ` and `WRITE` were sufficient. The new version adds a value that the old code does not know about.

Note two scenarios:

- **Exhaustive switch expression on enum v1**: has a safeguard mechanism when runtime encounters a new unrecognized constant.
- **Traditional switch statement is not required to be exhaustive**: a statement that only handles a few constants can complete normally when encountering a constant without a matching label. Not every `switch` syntax on an enum produces the same outcome.

Therefore, when upgrading an enum, you need to check **the form of the switch** and **whether the code was actually recompiled**, rather than just looking at the enum name.

## 6. `switch` statements with patterns are also affected

Java 21 requires **enhanced switch statements** to be exhaustive, including statements that use pattern labels:

```java
static void consume(Event event) {
    switch (event) {
        case Start start -> System.out.println("start");
        case Stop stop -> System.out.println("stop");
    }
}
```

This is a method **compiled with Event v1** in the demo section; it is not a complete file. If you run the exact old bytecode with `Event` v2 and encounter `Pause`, an enhanced switch statement without a matching case can throw `MatchException`, similar to a switch expression.

Conversely, the following traditional switch statement remains valid even though it is not exhaustive:

```java
static void oldStyle(int code) {
    switch (code) {
        case 1 -> System.out.println("one");
    }
}
```

Calling `oldStyle(2)` simply executes no branch; this case **does not automatically generate a `MatchException`**. This is why you need to distinguish the exhaustiveness requirement of enhanced switch statements from traditional switch statements.

## 7. `null`: NPE on the selector vs. MatchException from hierarchy changes

For a reference selector, when **the selector value itself is `null`** and there is no applicable `case null` label, Java 21 throws **`NullPointerException`**, even if the branches are considered exhaustive for non-null subtypes.

For example, with `Event`:

```java
static String nullable(Event event) {
    return switch (event) {
        case null -> "missing";
        case Start ignored -> "start";
        case Stop ignored -> "stop";
    };
}
```

This is an example based on **Event v1**, handling `null` explicitly. If you remove `case null` and pass `null`, a `NullPointerException` will occur; that situation should not be called a `MatchException` caused by a new subtype.

Another misconception: **`default` does not automatically catch `null`** in a pattern switch. If you want to handle both `null` and fallback values together, you can use the special `case null, default -> ...` construct when appropriate.

Further distinction: with a **nested record pattern**, sometimes **the outer selector is non-null** while **an inner component is null**. In some switches considered exhaustive by the compiler due to nested patterns, a `null` component can lead to `MatchException`. That is completely different from `switch(null)` without a null branch, which throws `NullPointerException`.

## 8. When MatchException occurs without changing the hierarchy

According to the Java 21 API, `MatchException` is not tied solely to separate compilation. Two notable groups:

### Null inside a nested record pattern

Suppose `Part` is a sealed type with only `One` and `Two`, and a record `Box` has a `Part` component. The two record patterns `Box(One ...)` and `Box(Two ...)` can be evaluated by the compiler as sufficient for the `Box` type, yet **`new Box(null)` matches neither sub-pattern**.

Full program demonstrating this on JDK 21 — create file **`NestedNullMatchDemo.java`**:

```java
public class NestedNullMatchDemo {
    sealed interface Part permits One, Two {}

    record One() implements Part {}
    record Two() implements Part {}
    record Box(Part part) {}

    static String describe(Box box) {
        return switch (box) {
            case Box(One one) -> "one";
            case Box(Two two) -> "two";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Box(new One())));

        try {
            System.out.println(describe(new Box(null)));
        } catch (MatchException ex) {
            System.out.println("nested-MatchException");
        }
    }
}
```

Compile and run:

```bash
javac --release 21 NestedNullMatchDemo.java
java NestedNullMatchDemo
```

Stdout:

```text
one
nested-MatchException
```

This case requires no JAR or hierarchy changes. **`Box` is a non-null selector**, but the `part` inside is null and does not satisfy either `One` or `Two` pattern.

If business requirements allow a null component, check/normalize it before passing the record into the switch, or design an appropriate handling branch. Do not confuse an outer-level `case null` with catching null for **an inner nested component**.

### A record accessor throws an exception during deconstruction

A record pattern must invoke accessors to retrieve component values. If an accessor invoked implicitly during matching **throws an exception**, pattern matching can throw `MatchException` and store the original exception in `getCause()`. This is an error **during pattern execution**, not a missing branch from adding a subtype.

Therefore, when diagnosing, in addition to the exception name, you need to inspect the **stack trace**, **cause**, and when it occurred. Do not automatically conclude that every `MatchException` is caused by `sealed permits` changes.

## 9. Does `default` prevent errors when adding a subtype?

Suppose the actual behavior allows a fallback branch:

```java
static String describeWithFallback(Event event) {
    return switch (event) {
        case Start ignored -> "start";
        case Stop ignored -> "stop";
        default -> "unknown event";
    };
}
```

If compiled against Event v1 and then receiving `Pause` at v2 runtime, `default` will typically catch `Pause` and produce `"unknown event"`. **That is an advantage when an API needs open-ended compatibility**.

However, this approach has a cost:

- **The compiler does not force adding a new case** when v2 adds `Pause`, because `default` already covers the rest.
- If every subtype must have dedicated handling (for example, mandatory financial events/state flows), `default` can **hide missing branches**, turning a source-update oversight into unintended fallback behavior.
- If a default branch silently ignores data, the system may drop events without reporting an error.

Consider the two strategies:

| Context | Appropriate Policy |
| --- | --- |
| Closed sealed hierarchy where every subtype must be handled explicitly | Do not add `default` just to silence exhaustiveness errors; recompile when the hierarchy changes |
| API intentionally accepts new types with generic behavior | A clearly designed `default` can be used, along with logging/metrics if needed |
| Runtime selector can be null | Handle `case null` or check beforehand; `default` alone is not enough |
| Nested record component can be null | Add a branch or validation at the component level; do not infer from outer-level `case null` |
| Scenario requiring detection of deployment mismatches | Ensure version synchronization and test subtype changes instead of swallowing `MatchException` |

There is no one-size-fits-all answer like "every switch must have default" or "never use default". The choice depends on the API contract and what maintainers expect when a subtype is added.

## 10. How to diagnose MatchException in practice

When encountering a stack trace with `java.lang.MatchException`, prioritize following the evidence:

1. **Locate where the error was thrown:** which class/method containing a `switch` or record pattern does the stack trace point to? Also check `getCause()` if present.
2. **Inspect the offending value:** what is its actual runtime type? If it is `Pause` in the example, check whether the client binary has a corresponding case. Only log data when compliant with security policies.
3. **Check the classes and JARs actually loaded:** are the library and client at the expected matching versions? Are there two JARs containing the same class on the classpath/module path?
4. **Compare the hierarchy at build time and runtime:** have `permits` or the enum constant list changed? Was a module deployed with a new library while keeping an old client?
5. **Distinguish other errors:** `NullPointerException` for a null selector; `MatchException` for no-match; linkage errors for deleted classes or invalid hierarchies; errors from record accessors.
6. **Recompile dependents:** if the hierarchy changed, rebuild the client containing the switch so the compiler identifies the cases that need to be added.
7. **Retest on a clean build:** verify the deployed set of classes/JARs, and run tests with new subtypes and nested null data.
8. **Do not fix with a blanket catch:** only catch `MatchException` at an appropriate boundary to log or translate it into an upper-layer error; you must still fix the handler or synchronize dependencies.

Example of a syntactically valid monitoring block:

```java
try {
    processEvent(event);
} catch (MatchException ex) {
    System.err.println("Unmatched pattern: " + ex);
    throw ex;
}
```

This is an illustrative snippet inside a method where `processEvent` and `event` are declared. Rethrowing the exception after logging helps prevent the application from **continuing as if the event had been processed successfully**.

In production systems, logs should include deployment/module version identifiers and the appropriate event type, without automatically printing entire sensitive payloads.

## 11. Prevention when releasing libraries and applications

Several useful techniques:

- **Rebuild dependent modules** when changing a sealed hierarchy, adding enum constants, or changing record shapes. Do not assume that a module whose own source did not change definitely does not need recompilation.
- **Synchronize release artifacts:** lock dependency versions consistently across build, test, and deploy; avoid mixing an old client with a new library on the classpath.
- **Test exhaustive branch coverage:** add tests for every current subtype/enum constant. With a sealed hierarchy, a switch without `default` helps the compiler enforce updates upon recompilation.
- **Test rolling upgrades:** if servers and clients may run different versions for a period, agree on backward/forward compatibility contracts and how new types are handled.
- **Monitor runtime errors:** alert on `MatchException` and linkage errors after deployment, while retaining enough version information to cross-reference.
- **Do not swap binaries arbitrarily:** identical class names or JAR paths do not guarantee the hierarchy stayed the same; all related classes must be compiled and packaged consistently.

In particular, **`javac --release 21` only constrains the Java 21 language and APIs** at compile time. It does **not** lock the set of subtypes or enum constants of a dependency that will be loaded at runtime. Dependency policies and rebuilding dependents still need to be managed separately.

## 12. Comparison table of commonly confused errors

| Scenario | Typical Outcome in Java 21 | Explanation |
| --- | --- | --- |
| Enhanced `switch` is not exhaustive in the current source | **Compile-time error** | Compiler detects uncovered types/cases |
| Old switch compiled exhaustively against sealed v1, runtime encounters new subtype from sealed v2 | **`MatchException`** when no case matches | Hierarchy changed between compile time and runtime |
| Enum switch expression from v1, runtime receives new enum constant | **`MatchException`** if no matching branch exists | Enum constant list differs across versions |
| Selector is `null`, no applicable `case null` label | **`NullPointerException`** | Not the same as a missing subtype in the hierarchy |
| Outer selector is a non-null record, nested component is null so no sub-pattern matches | Can be **`MatchException`** | Exhaustiveness is inferred from type patterns, leaving a gap for null components |
| Record accessor throws an exception during matching | Can be **`MatchException`**, with original exception as cause | Error during deconstruction |
| Library changes/deletes classes causing invalid linkage | **Linkage error**, depending on situation | May fail before execution reaches the switch |
| Non-exhaustive traditional switch statement encounters a value with no case | May **do nothing** | Not an enhanced statement requiring exhaustiveness |

Do not rely on `MatchException` being an unchecked exception to treat it as a normal "wrong data type branch". It usually reflects a broken design or deployment assumption and warrants investigation.

## 13. Self-check exercises

1. With Event v1 having only `Start` and `Stop`, explain why a `switch` without `default` in `Client.describe` still compiles.
2. Add `Pause` and compile **all** sources: at what stage does the error appear? Compare this with compiling only the new library and using the old `Client.class`.
3. If `default -> "unknown"` is added to `Client.describe` in v1, what will runtime produce when receiving `Pause` in v2? Does that always meet business requirements?
4. If `Event.sample()` returns `null`, which exception occurs when the `switch` has no `case null`?
5. Why can `new Box(null)` in the nested record example throw `MatchException` even without any library changes?
6. Why does a **clean rebuild** catch an error that swapping a JAR in the deployment directory does not immediately reveal?

### Short answers

1. The v1 compiler sees all subtypes permitted by `Event`.
2. Rebuilding everything with the new hierarchy causes the compiler to report the missing `Pause` case; running the v1 client with library v2 can throw `MatchException`.
3. `default` can catch `Pause` and return `"unknown"`; however, it can easily hide a case that actually needs dedicated handling.
4. `NullPointerException`, because `null` on the **selector** is not handled.
5. Because `null` in the **nested component** causes the record patterns not to match even though the outer record type matched.
6. The compiler re-checks the new hierarchy and all `case` branches instead of relying on assumptions frozen in old bytecode.

## Conclusion

In Java 21, an exhaustive pattern switch **does not mean every future binary combination is safe**. The compiler proves exhaustiveness based on the hierarchy present at build time; when runtime receives a new subtype or enum constant and the switch bytecode has not been updated, **`MatchException` can occur**. It is the responsibility of the build/deploy pipeline to update dependent modules, re-verify handling branches, and release compatible artifacts.

At the same time, distinguish errors caused by hierarchy changes from `null` on the selector, `null` inside a record component, and exceptions from record accessors. Analyzing the exact root cause leads to the right fix: **adding cases, rebuilding, synchronizing dependencies, or fixing data/patterns**, rather than just adding a `catch` and ignoring it.

### Official references

- [Java SE 21 — `MatchException` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
- [Java Language Specification 21 — §14.11.3, Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3)
- [Java Language Specification 21 — §14.11.1.1, Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
