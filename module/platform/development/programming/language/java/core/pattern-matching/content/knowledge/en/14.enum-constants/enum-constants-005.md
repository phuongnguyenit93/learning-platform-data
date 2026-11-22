# Enum Evolution and Compatibility in Java

## 1. Enum Changes Across Versions: Why Can a Small Change Cause a Big Failure?

An `enum` describes a set of named constants, such as order statuses, job statuses, or event types:

```java
enum JobStatus {
    NEW,
    RUNNING,
    DONE
}
```

Initially, the system only has three statuses. After some time, the product needs to add `PAUSED` or rename `RUNNING` to `IN_PROGRESS`. If modules, data files, databases, APIs, and messages are deployed at **different times**, this change can affect previously compiled code and existing data.

**Enum evolution** is the process of changing an enum's set of constants or behavior across versions. **Compatibility** does not have just one meaning:

1. **Binary compatibility:** whether a `.class` file compiled against the old enum can still link and run with the new enum, according to Java's linking rules.
2. **Source compatibility:** whether old client source code still compiles when the enum is changed and the client is recompiled.
3. **Behavioral compatibility:** whether the program still returns business-correct results for both old and new values.
4. **Data/wire compatibility:** whether strings or numbers already written to a database, JSON, message queue, cache, log, configuration file, or sent by another service are still interpreted correctly.

A change can be **binary-compatible yet behaviorally breaking**. This is the most important scenario when adding an enum constant to an exhaustive `switch`.

The [JLS Java 21 §13.4.26](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.26) specification states: **adding or reordering enum constants does not break binary compatibility with preexisting binaries**, but adding a constant can cause a previously compiled exhaustive `switch` to fail when it encounters the new value. Therefore, the word "compatible" must always be accompanied by **which type of compatibility** is being discussed.

## 2. Which Parts of an Enum Are Easily Affected by Changes?

Given the enum:

```java
enum JobStatus {
    NEW,
    RUNNING,
    DONE
}
```

Java provides several ways to work with it:

| Member | Meaning | Impact When the Enum Evolves |
| --- | --- | --- |
| `JobStatus.NEW` | `public static final` field representing the `NEW` constant | Removing/renaming `NEW` causes code referencing the old constant to lose the field |
| `JobStatus.values()` | Array of constants in **current declaration order** | Adding/removing/reordering changes the array length and order |
| `status.name()` | Exact identifier name, such as `"NEW"` | Unchanged when only reordering; changes when renaming the constant |
| `status.ordinal()` | Position in the declaration, starting from `0` | Changes when inserting, removing, or reordering |
| `JobStatus.valueOf("DONE")` | Looks up a constant by **exact name match** | Non-existent name throws `IllegalArgumentException` |
| `status.toString()` | Defaults to `name()`, but can be overridden | Not a durable identifier if used for display |
| `switch(status)` | Selects a branch based on the constant | Adding a constant can create an unhandled branch |

`ordinal()` is an internal index based on declaration order, **not a stable business code**. The `Enum.ordinal()` API advises that most applications have no need to call it directly; structures like `EnumSet` and `EnumMap` are the typical users.

`name()` is stable across **reordering**, but **not** stable if the constant name itself is changed. If a name has already been published externally, renaming it must be treated as a protocol or schema change, not merely a Java code refactoring.

## 3. Impact Table of Common Enum Changes

| Change | Binary Compatibility | Source Compatibility | Behavioral/Data Risk |
| --- | --- | --- | --- |
| **Add** `PAUSED` at the end | Yes, per JLS | Old exhaustive `switch expression` may **fail to compile** on rebuild | Old consumers may not know `PAUSED`; new persisted strings cannot be read by old versions |
| **Insert** a constant in the middle | Yes | Conditional, same as adding a constant | `ordinal` of subsequent constants shifts |
| **Reorder** constants | Yes | Usually does not break name-based references | `ordinal`, `values()` order, and natural order change |
| **Remove** `RUNNING` | Not guaranteed; usually breaks binaries referencing it | Code using `RUNNING` fails to compile | `NoSuchFieldError`, old name-based data cannot be decoded |
| **Rename** `RUNNING` to `IN_PROGRESS` | Effectively removes the old field and adds a new field | References to the old name fail on rebuild | Values stored by `name` and old Java serialization lose the corresponding constant |
| **Change `toString()`** or constant logic | Depends on the specific API change; may still link | May still compile | Display/APIs using `toString()` produce different output |
| **Add a stable `code` field** while keeping the old name | Depends on the change structure; usually feasible | Old clients usually need no changes | Must ensure codes are unique and mapping is backward compatible |

A "Yes" in the binary column **is not a promise that all runtime functionality is safe**. For example, even though adding `PAUSED` is binary-compatible, an old binary containing an exhaustive `switch` without a `PAUSED` branch can still fail when receiving `PAUSED`.

Practical rule: **analyze three things simultaneously**: the enum code version, the consumer code version, and the data crossing the boundary between those two versions.

## 4. Adding an Enum Constant and `switch expression` Exhaustiveness

### 4.1. Version 1: Complete Code, No `default` Needed

```java
enum Status {
    NEW, DONE
}

static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case DONE -> "done";
    };
}
```

This is an illustrative snippet placed in a valid Java context. With selector type `Status` having exactly two constants, the `switch expression` covers every constant known to the compiler, so **`default` is not required**.

Omitting `default` has a maintainability benefit: it expresses the expectation that **every constant must be handled explicitly**.

### 4.2. Version 2: Adding `PAUSED`

```java
enum Status {
    NEW, PAUSED, DONE
}
```

If you recompile the `label` method above against the new enum, Java reports an error like:

```text
the switch expression does not cover all possible input values
```

Because `PAUSED` has no handling branch yet. This is a **source compatibility error** in a specific consumer (not every source file using the enum will fail).

Direct fix:

```java
static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case PAUSED -> "paused";
        case DONE -> "done";
    };
}
```

**Do not mechanically patch it with `default`** if `PAUSED` has its own business behavior. `default` makes it compile, but it can also hide future new constants.

### 4.3. What If the Old Consumer Is Not Recompiled?

Consider a **consumer binary already compiled** when the enum only had `NEW` and `DONE`, then run against the enum version that adds `PAUSED`.

According to JLS Java 21:

- Adding a constant is still a **binary-compatible** change.
- If the consumer receives `PAUSED` and the `switch expression` has no applicable case, the Java 21 runtime can throw **`java.lang.MatchException`**.
- Omitting `default` is how you make the compiler enforce handling each value upon recompilation, but **it does not guarantee an old binary runs correctly with every new value when deployed independently**.

**Version note:** the runtime failure behavior of an exhaustive `switch` has evolved across Java versions; older Java releases had cases that threw `IncompatibleClassChangeError`. For this lesson and Java 21 lab, use the `MatchException` rule from JLS Java 21 §15.28.2. Do not assume the exact same exception type for all older JDKs.

A real system can "load classes successfully" and only fail when it receives `PAUSED`. Therefore, you must test **old consumer + new producer**, not just whether the application starts up.

## 5. Separate Compilation Lab: Seeing Binary-Compatible Yet Runtime-Incompatible Behavior

The following experiment uses **Java 21+**, with two Java files in the same directory and a `classes` output directory. This lab uses **two consecutive versions of the same file**; do not combine both `Status` definitions into one program.

**Step A — Create `Status.java` version 1:**

```java
public enum Status {
    NEW, DONE
}
```

**Step B — Create `Consumer.java` (unchanged across both runs):**

```java
public class Consumer {
    static String label(Status status) {
        return switch (status) {
            case NEW -> "new";
            case DONE -> "done";
        };
    }

    public static void main(String[] args) {
        Status value = Status.valueOf(args[0]);
        System.out.println(label(value));
    }
}
```

Compile both files and run:

```bash
javac --release 21 -d classes Status.java Consumer.java
java -cp classes Consumer NEW
```

Output:

```text
new
```

**Step C — Replace the contents of `Status.java` with version 2** (keep `Consumer.java` untouched):

```java
public enum Status {
    NEW, PAUSED, DONE
}
```

Compile **only `Status.java`**, keeping the old `Consumer.class` file:

```bash
javac --release 21 -d classes Status.java
java -cp classes Consumer PAUSED
```

This tests **mixing an old binary with a new enum**. Java 21 can throw `MatchException` when the old consumer encounters `PAUSED` in an exhaustive `switch` without a matching branch. In a terminal, the stack trace includes file names and line numbers; do not treat the full stack trace as a fixed output of the exercise.

**Step D — Try recompiling the consumer** against the new enum:

```bash
javac --release 21 -cp classes -d classes Consumer.java
```

Now the compiler knows about `PAUSED` and detects that the `switch expression` is not exhaustive, forcing you to update the code. This is the advantage of **omitting `default`** when each enum constant requires its own behavior.

**What the lab verifies:**

| Scenario | Effect |
| --- | --- |
| Consumer v1 compiled with Status v1 | Succeeds |
| Consumer v1 (already compiled) run with Status v2, only using `NEW`/`DONE` | Can still work normally |
| Consumer v1 run with Status v2 and receives `PAUSED` | Can fail at runtime due to missing case |
| Recompile Consumer v1 with Status v2 | Reports missing coverage in `switch expression` |

This lab is about `switch expression`; do not automatically apply the exact same runtime conclusion to a **legacy `switch statement`**—the next section explains the difference.

## 6. Legacy `switch statement` Can Silently Ignore New Constants

With a traditional `switch statement` on an enum, the compiler does not require `default`:

```java
enum Status {
    NEW, DONE, PAUSED
}

static void print(Status status) {
    switch (status) {
        case NEW -> System.out.println("new");
        case DONE -> System.out.println("done");
    }
}
```

This method **compiles** even though `PAUSED` is missing. If you call `print(Status.PAUSED)`, no label matches, the statement completes normally, and **nothing is printed**.

That is an important distinction to remember:

- **`switch expression`:** must be exhaustive; missing a constant of the current enum is a compile-time error.
- **Legacy `switch statement`:** not required to be exhaustive; new values can be silently ignored.
- **Enhanced `switch statement`** in Java 21 (for example, using pattern labels or `case null`) has its own exhaustiveness requirements and must not be equated with a legacy statement.

If you want to use a switch statement without ignoring unexpected values, add an explicit `default`:

```java
static void printStrict(Status status) {
    switch (status) {
        case NEW -> System.out.println("new");
        case DONE -> System.out.println("done");
        default -> throw new IllegalArgumentException(
            "Unhandled status: " + status
        );
    }
}
```

When you choose `default`, you are choosing a **fallback policy**. It can be a good policy at boundaries with untrusted data, but it also stops the compiler from forcing you to update every case when the enum expands.

## 7. `default`: Operational Safety Net or Hiding Missing Updates?

There is no single rule that every enum `switch` must or must not use `default`.

**Omitting `default`** is appropriate when:
- The enum set is a **closed domain** controlled by the application.
- Every constant must have its own behavior.
- When a constant is added, you **want compilation to fail** until the handling code is updated.
- Modules are compiled and deployed in reasonably close sync.

**Using `default`** is appropriate when:
- The consumer must keep operating on unexpected data and has a well-defined fallback.
- It is not possible to update all consumers at the same time.
- New values can temporarily be handled uniformly under a shared policy.
- `default` logs, returns an "unsupported" code, or throws a designed exception rather than doing the wrong thing silently.

Fail-fast example:

```java
static String labelStrict(Status value) {
    return switch (value) {
        case NEW -> "new";
        case DONE -> "done";
        default -> throw new IllegalStateException(
            "Unhandled status: " + value
        );
    };
}
```

This `default` branch must still be tested, because the compiler will not ask you to add a new case when `PAUSED` is introduced.

Intentional fallback example:

```java
static String labelForUi(Status value) {
    return switch (value) {
        case NEW -> "New";
        case DONE -> "Done";
        default -> "Unsupported status";
    };
}
```

If the UI can display `Unsupported status` without corrupting transaction state, this is a reasonable choice. However, in payment processing or sensitive business logic, lumping all unknown states into a single default branch can be logically dangerous; define a dedicated policy for that kind of behavior.

## 8. Reordering Constants: Binary-Compatible, Yet `ordinal` Changes Meaning

Suppose v1 is:

```java
enum Stage {
    NEW, RUNNING, DONE
}
```

Then:

```text
NEW.ordinal()     = 0
RUNNING.ordinal() = 1
DONE.ordinal()    = 2
```

After reordering:

```java
enum Stage {
    DONE, NEW, RUNNING
}
```

Then:

```text
DONE.ordinal()    = 0
NEW.ordinal()     = 1
RUNNING.ordinal() = 2
```

According to the JLS, reordering is **binary-compatible** because the named constants still exist. However, a database that stored `0` meaning `NEW` and new code that reads it via `Stage.values()[0]` will get **`DONE`**: the data is misinterpreted without necessarily raising an error.

Consequences of reordering or inserting constants:
- `ordinal()` and `values()[i]` indices change.
- `values()` returns constants in the new declaration order.
- `Enum.compareTo()` and the enum's natural order are based on declaration position, so sorting results can change.
- `EnumSet` and `EnumMap` represent/iterate constants in the enum's natural order, so iteration order can change.
- Code relying on "first constant", "last constant", or enum order as priority can change behavior.

**Do not use `ordinal` as a storage key, API code, or historical data value.** It is suitable for the enum's internal mechanics and certain specialized collections, not as a durable data contract across versions.

Simulating a comparison between two versions using two **separate** enums:

```java
enum Before { NEW, RUNNING, DONE }
enum Reordered { DONE, NEW, RUNNING }

System.out.println(Before.NEW.ordinal());    // 0
System.out.println(Reordered.NEW.ordinal()); // 1
```

The two enums above are different types in the same program; they only **simulate the order difference between two versions**, not actually running two binaries of the same enum.

## 9. Renaming or Removing Constants: Source, Binary, and Data Risks

Changing from:

```java
enum Status {
    NEW, RUNNING, DONE
}
```

to:

```java
enum Status {
    NEW, IN_PROGRESS, DONE
}
```

looks like a simple rename, but to Java, each enum constant corresponds to a `public static final` field. The new version has **removed the `RUNNING` field** and added the `IN_PROGRESS` field.

Consequences:

- **Recompiling old source:** references to `Status.RUNNING` or `case RUNNING` labels will fail because the name no longer exists.
- **Old binaries:** a compiled binary that still directly references the `RUNNING` field can throw **`NoSuchFieldError`** when linking/executing the relevant code.
- **Stored strings:** `Status.valueOf("RUNNING")` will throw `IllegalArgumentException` because the new enum no longer has a constant with that name.
- **Data over APIs:** old consumers do not know `IN_PROGRESS`, while new consumers do not know `RUNNING` unless there is a transition mechanism.
- **Java object serialization:** enums are serialized by constant name; renaming/removing a name can break deserialization of historical data.

**Renaming is not a binary-compatible change** just because an IDE has a "Rename Symbol" feature. The IDE only updates call sites within the source scope it controls; it does not rename values in databases, message queues, archived data, other services' API contracts, or already-released binaries.

### A Safer Transition: Keep the Old Constant Temporarily

```java
enum Status {
    NEW,
    RUNNING,      // old name, kept during the transition period
    IN_PROGRESS,  // new name
    DONE
}
```

If both constants exist, you must define the mapping rules and when to stop emitting `RUNNING`. For example, emit only `IN_PROGRESS` for new data while still accepting `RUNNING` from old consumers. However, **these two constants are two distinct enum objects**: `RUNNING != IN_PROGRESS`, so you cannot just add the new constant and assume they are automatically equivalent. Explicit mapping is required at handling sites and in relevant `switch` statements.

Another strategy is to keep the Java constant `RUNNING` for code compatibility and only change the **display label** or **wire code** via a separate field. This is often less risky if the rename is only for UI or business terminology.

## 10. `name()`, `valueOf()`, `toString()`, and Serialization

### 10.1. `name()` Is the Identifier Name, Not a User Label

```java
enum Status { NEW, RUNNING, DONE }

System.out.println(Status.RUNNING.name()); // RUNNING
```

`name()` is final and returns the exact declared name. It is unaffected by reordering, but directly affected if the constant is renamed.

`toString()` returns the name by default, but an enum can override `toString()` for friendly display:

```java
enum Status {
    NEW, RUNNING, DONE;

    @Override
    public String toString() {
        return switch (this) {
            case NEW -> "New job";
            case RUNNING -> "In progress";
            case DONE -> "Completed";
        };
    }
}
```

With this enum, `RUNNING.toString()` returns `"In progress"` while `RUNNING.name()` still returns `"RUNNING"`. Do not use `toString()` as a storage identifier if it can freely change with language, translations, or UI requirements.

### 10.2. `valueOf()` Requires an Exact Name

```java
Status.valueOf("DONE");  // DONE

// Throws IllegalArgumentException if the enum has no matching constant:
// Status.valueOf("PAUSED");
```

`valueOf()` is case-sensitive; it does not trim whitespace and does not automatically map old names to new names. If data comes from users, APIs, or multi-version databases, you must have a **parse/normalize/migration** layer instead of calling `valueOf` without error handling.

### 10.3. Standard Java Serialization of Enums Uses **Name**, Not Ordinal

The Java Object Serialization Specification, §1.12, states that an enum constant serialized with `ObjectOutputStream` is represented by its **constant name**. Upon deserialization, the system uses the name to look up the corresponding enum constant.

This means:
- Simply reordering constants usually does not invalidate serialized names.
- Renaming or removing a constant can prevent old Java serialization data from being decoded normally.
- You cannot customize enum serialization using normal `writeObject/readObject` hooks as you can with arbitrary classes.

**Do not generalize** this conclusion to every JSON library, protobuf, ORM, or other binary serialization system. Each framework and configuration may serialize enums by **name, number, custom code, or its own format**. Always check the actual serializer in use.

## 11. Designing Stable Wire Codes Decoupled from Constant Names

When an enum is persisted or exchanged across versions, using a **stable business code** is often better than using `ordinal`, and can be better than `name()` if Java names are likely to be refactored.

```java
enum Status {
    NEW("new"),
    RUNNING("running"),
    DONE("done");

    private final String code;

    Status(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Here:
- `Status.RUNNING.name()` is `"RUNNING"`.
- `Status.RUNNING.code()` is `"running"`.
- The `"running"` code is treated as a **contract with external data**, so it should remain stable or have alias migration if it must change.
- Declaration order and `ordinal` can change without changing the wire code.

**A stable code does not mean automatic compatibility.** If an old version does not know the `"paused"` code, it still needs a policy for handling unknown values. A dedicated code only avoids coupling to renames and ordinals.

### A Parser That Can Accept Old Version Aliases

```java
static java.util.Optional<Status> parseCode(String raw) {
    if (raw == null) {
        return java.util.Optional.empty();
    }

    String code = raw.strip().toLowerCase(java.util.Locale.ROOT);

    return switch (code) {
        case "new" -> java.util.Optional.of(Status.NEW);
        case "running", "in-progress" ->
            java.util.Optional.of(Status.RUNNING);
        case "done", "finished" ->
            java.util.Optional.of(Status.DONE);
        default -> java.util.Optional.empty();
    };
}
```

This illustrative parser belongs in a class containing the `Status` enum above, or use the complete file in the next section. It:

1. Handles `null` without throwing `NullPointerException`.
2. Normalizes whitespace and letter casing using `Locale.ROOT`.
3. Accepts legacy aliases like `"in-progress"` or `"finished"`.
4. Returns `Optional.empty()` for unknown codes so the caller can decide whether to log, reject, or fall back.
5. Does not map an unknown code to an arbitrary status, avoiding accidental business logic errors.

**Important:** an alias like `"in-progress"` must be documented as having the same meaning as `RUNNING` at the boundary; do not assume similar names are equivalent if the business logic has changed.

## 12. Runnable Java 17 Program: `name`, `ordinal`, Alias, Exhaustive `switch`

Save the file **`EnumEvolutionDemo.java`**:

```java
public class EnumEvolutionDemo {
    enum Status {
        NEW("new"),
        RUNNING("running"),
        DONE("done");

        private final String code;

        Status(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    // Two enums only simulate the ordering of two different versions.
    enum Before { NEW, RUNNING, DONE }
    enum Reordered { DONE, NEW, RUNNING }

    static String label(Status s) {
        return switch (s) {
            case NEW -> "New";
            case RUNNING -> "In progress";
            case DONE -> "Done";
        };
    }

    static java.util.Optional<Status> parseCode(String raw) {
        if (raw == null) {
            return java.util.Optional.empty();
        }

        String code = raw.strip().toLowerCase(java.util.Locale.ROOT);

        return switch (code) {
            case "new" -> java.util.Optional.of(Status.NEW);
            case "running", "in-progress" ->
                java.util.Optional.of(Status.RUNNING);
            case "done", "finished" ->
                java.util.Optional.of(Status.DONE);
            default -> java.util.Optional.empty();
        };
    }

    public static void main(String[] args) {
        for (Status s : Status.values()) {
            System.out.println(
                s.name() + ":ordinal=" + s.ordinal()
                + ",code=" + s.code()
            );
        }

        System.out.println("label=" + label(Status.RUNNING));
        System.out.println("legacy=" + parseCode("in-progress"));
        System.out.println("unknown=" + parseCode("paused"));
        System.out.println("valueOf=" + Status.valueOf("DONE"));

        System.out.println(
            "Before.NEW.ordinal=" + Before.NEW.ordinal()
        );
        System.out.println(
            "Reordered.NEW.ordinal=" + Reordered.NEW.ordinal()
        );
        System.out.println(
            "Before.DONE.ordinal=" + Before.DONE.ordinal()
        );
        System.out.println(
            "Reordered.DONE.ordinal=" + Reordered.DONE.ordinal()
        );
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 EnumEvolutionDemo.java
java EnumEvolutionDemo
```

Output:

```text
NEW:ordinal=0,code=new
RUNNING:ordinal=1,code=running
DONE:ordinal=2,code=done
label=In progress
legacy=Optional[RUNNING]
unknown=Optional.empty
valueOf=DONE
Before.NEW.ordinal=0
Reordered.NEW.ordinal=1
Before.DONE.ordinal=2
Reordered.DONE.ordinal=0
```

Analysis:

- The first three lines demonstrate that `name()`, `ordinal()`, and `code()` are distinct.
- `label` uses an exhaustive `switch expression` without `default`, because all three constants are handled.
- `legacy=Optional[RUNNING]` demonstrates that an old alias string can map to the current status under an explicit policy.
- `unknown=Optional.empty` shows that the parser does not assume every external code is valid.
- The `Before`/`Reordered` lines illustrate that `ordinal` changes even when the **names** `NEW` and `DONE` stay the same.

This example does not require Java 21, because `switch expression` was officially supported before Java 17. It is suitable for studying **enums and constants** on their own even before using pattern `switch`.

## 13. Enums in Pattern `switch` over Interfaces/Sealed Types (Java 21+)

Java 21 allows `switch` with a selector of a **reference type**, not necessarily a specific enum. In some cases, an enum constant label can be written with its qualified enum name, such as `case Status.NEW`, to distinguish constants of an enum implementing an interface.

```java
sealed interface Event permits Status, Fault {}

enum Status implements Event {
    NEW, DONE
}

record Fault(String message) implements Event {}
```

With static selector type `Event`, a pattern `switch` can use these labels:

```java
static String describe(Event event) {
    return switch (event) {
        case Status.NEW -> "new";
        case Status.DONE -> "done";
        case Fault f -> "fault:" + f.message();
    };
}
```

Because `Event` is sealed and the `Status` enum currently has only two constants, this set of labels is considered exhaustive by the compiler. If you add a new constant to `Status` and recompile this code, you must re-evaluate coverage, following the same enum evolution rules above.

**Standalone Java 21 program**, file `EnumPatternIntegrationDemo.java`:

```java
public class EnumPatternIntegrationDemo {
    sealed interface Event permits Status, Fault {}

    enum Status implements Event {
        NEW, DONE
    }

    record Fault(String message) implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case Status.NEW -> "new";
            case Status.DONE -> "done";
            case Fault f -> "fault:" + f.message();
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Status.NEW));
        System.out.println(describe(Status.DONE));
        System.out.println(describe(new Fault("offline")));

        try {
            System.out.println(describe(null));
        } catch (NullPointerException ex) {
            System.out.println("null => NPE");
        }
    }
}
```

Run:

```bash
javac --release 21 EnumPatternIntegrationDemo.java
java EnumPatternIntegrationDemo
```

Output:

```text
new
done
fault:offline
null => NPE
```

Key takeaways:

- `case Status.NEW` and `case Status.DONE` are **enum constant labels**; `case Fault f` is a type pattern.
- `Fault` is handled via the pattern variable `f`.
- `null` is not matched by any label above, so `NullPointerException` is caught in `main`.
- Java 21 pattern `switch` adds multi-type dispatch across interface/sealed hierarchies; the rule that **enum evolution changes coverage** still applies.

Do not confuse version requirements: the example in section 12 uses Java 17, whereas this example uses Java 21+ pattern `switch` syntax.

## 14. Multi-Service Deployment: Old Consumer and New Producer

Suppose service A (producer) can emit order statuses and service B (consumer) reads them. Initially both know `NEW` and `DONE`. Later, A starts sending `PAUSED`.

If B is still running the old version:
- A parser calling `Status.valueOf("PAUSED")` can throw `IllegalArgumentException`.
- An `Optional`-returning parser returns unknown, allowing service B to act according to a predefined policy: log it, return an error code, route the message to a dead-letter queue, or store it for later processing.
- If the new data has already been converted into a Java enum object of the new version while the `switch` logic belongs to an old binary, the unknown-branch risk from section 4 still exists.
- If B only has a legacy `switch statement` without `default`, the new status can be silently ignored without anyone noticing.

Therefore, rollout order must be based on **consumer readiness**, not just the producer's ability to emit the new enum.

### A Safer Rollout Process

1. **Prepare the consumer:** release a parser or logic capable of accepting/logging unknown values; verify that handling paths do not corrupt state.
2. **Agree on wire codes:** add a durable mapping, such as `"paused"`, and document its meaning in the schema/API contract.
3. **Update all relevant switches:** decide between specific branches or fallback, and test both switch expressions and switch statements.
4. **Deploy consumer logic before emitting new data**, whenever possible.
5. **Enable emitting the new value in a controlled manner**, monitoring metrics/logs for unknown codes.
6. **Maintain aliases for old names during the transition period** and remove them only when certain no party still needs them.
7. **Recompile and retest related modules**, avoiding running binaries out of sync with the current enum set.

"Adding an enum constant is binary-compatible" does **not** mean a producer can send new data to any old consumer version without preparation.

## 15. Migrating Stored Data

### 15.1. If `ordinal` Was Stored

For example, the database contains:

```text
status_ordinal
0
1
2
```

When v1 was `NEW, RUNNING, DONE`, the numbers corresponded to `NEW, RUNNING, DONE` respectively. After reordering to `DONE, NEW, RUNNING`, reading via `values()[ordinal]` scrambles the meaning.

**How to migrate:**
1. Clearly identify the **historical version** corresponding to each row/batch of data.
2. Use a mapping table **fixed to the old version's meaning**, e.g., `0 -> "new"`, `1 -> "running"`, `2 -> "done"`.
3. Convert the data to a **stable code** with its own schema instead of the current enum index.
4. Verify total row counts, compare status distribution statistics before/after, and run application read-back tests.
5. Remove legacy reading logic only when certain no ordinal-based data remains.

Do not write the migration using `Status.values()[oldOrdinal]` from the **new version**: that reproduces the exact bug you are trying to fix.

### 15.2. If `name()` or Constant Strings Were Stored

If the database stores `"RUNNING"` but the new enum only has `IN_PROGRESS`, you need to:
- Keep an alias in the read layer: `"RUNNING" -> IN_PROGRESS`.
- Or migrate the stored data according to an approved mapping.
- Account for events in queues, backup files, configurations, cache data, replay logs, and downstream APIs if they will be parsed again.
- Decide when to remove the old alias after all producers/consumers have transitioned.

Do not just fix the new application and ignore historical data: an old record read back months later can still carry the old constant name.

### 15.3. If Standard Java Serialization Was Used

Default Java serialization for enums is based on the **constant name** rather than ordinal. This avoids one class of breakage from reordering, but **does not** protect you from renames or removals.

For long-term storage or inter-service communication, consider an independent schema and explicit migration mechanism instead of relying on Java object serialization as a durable data format.

## 16. Compatibility Analysis Checklist Before Modifying an Enum

When a pull request adds, removes, renames, or reorders an enum, check each item in order:

1. **Which constants changed?** Added, removed, renamed, reordered, or metadata-only?
2. **Who are the consumers?** Code in the same repository, published libraries, third-party plugins, REST/JSON, queues, batch jobs, persistence?
3. **Which enum version were consumers compiled against?** Could multiple `.class` versions run across different environments?
4. **Are `switch expression`s exhaustive?** If adding a constant, recompile consumers to detect missing branches.
5. **Are there `switch statement`s without `default`?** They might ignore the new constant at runtime.
6. **Is any `default` too broad?** Is it hiding a requirement for specific handling or dangerous behavior?
7. **Are `ordinal()`, `values()[i]`, or natural order used as data?** Reordering can produce wrong results.
8. **Are values serialized by name or number?** Check the exact serializer/framework in use.
9. **Are there direct field references to a constant being removed?** Old binaries may hit `NoSuchFieldError`.
10. **Is `valueOf` called on external strings?** Unknown/legacy handling is required.
11. **Are there formal migrations and aliases?** Retest historical data, caches/queues, and backups.
12. **Have version pairs been tested?** Old consumer with new producer; new consumer with old data; source rebuild; binary runtime; persisted data.

### Practical Testing Matrix

| Version Pair | What to Observe |
| --- | --- |
| Consumer v1 + enum v1 | Baseline: handles initial constants |
| Consumer v1 + enum v2 (no rebuild) | Binary link/load, `switch` encountering new constant, parser for new data |
| Consumer v1 source + enum v2 (rebuild) | Exhaustiveness errors or old name references |
| Consumer v2 + data v1 | Do aliases, deserialization, and migration work? |
| Consumer v2 + enum v2 | Full handling of both new and old constants |
| Consumer v2 + unknown data | Is the unknown-value policy safe, clear, and observable? |

Testing **old binary with new enum** and **old source recompiled with new enum** are two different scenarios; do not rely solely on unit tests run after rebuilding all source code.

## 17. Common Mistakes

**Mistake 1: "Adding an enum constant is non-breaking in every sense."**  
False. The JLS guarantees binary compatibility in a specific sense; an exhaustive `switch` or a consumer unaware of the new code can still fail.

**Mistake 2: "Reordering an enum has no impact."**  
False if the system uses `ordinal`, `values()[i]`, natural order, or `EnumSet`/`EnumMap` iteration order as business semantics.

**Mistake 3: "Renaming a constant is just a name refactor."**  
False for released binaries and external data; at the API level it is equivalent to removing the old field and adding a new field.

**Mistake 4: "`default` in a switch is always best practice."**  
Not necessarily. It can hide missing handling for new constants; base the choice on the contract.

**Mistake 5: "Without `default`, runtime will never see an unexpected state."**  
False when binaries and enums are updated independently. Java 21 can throw `MatchException` when encountering a new value.

**Mistake 6: "A legacy `switch statement` automatically knows the enum was extended."**  
No. It can do nothing when encountering a new constant with no matching branch.

**Mistake 7: "`name()` is a wire code that never changes."**  
It only stays the same as long as the **constant name stays the same**; renaming changes the string data.

**Mistake 8: "`toString()` is a stable identifier."**  
It can be overridden and changed for display requirements. Avoid using it as a business key without an explicit contract.

**Mistake 9: "Java object serialization of enums uses ordinal."**  
No. Standard Java serialization uses the enum constant name. However, other libraries may choose numeric representations.

**Mistake 10: "`Enum.valueOf` returns `null` when a constant does not exist."**  
False. It throws `IllegalArgumentException` if the name is not found; catch/map it properly or use an `Optional`-returning parser.

**Mistake 11: "Old data can be mapped using the new enum's ordinal."**  
False if the order has changed. Migration requires mapping based on the **historical schema**, not the current enum.

**Mistake 12: "Deploying the new producer first is enough because enums are binary-compatible."**  
False at inter-service boundaries. Old consumers may be unable to parse or handle the new constant.

## 18. Exercises and Answers

**Question 1.** V1 has `enum State { NEW, DONE }`. V2 adds `PAUSED`. A v1 consumer contains a `switch expression` listing the two old constants with no `default`. What can happen?

*Answer:* When rebuilding the consumer against v2, the compiler reports a missing branch. If the old binary is kept and run with enum v2, receiving `PAUSED` on Java 21 can throw `MatchException`. Adding a constant does not break binary compatibility per the JLS, but it does not guarantee behavioral compatibility.

**Question 2.** Does reordering `{NEW, DONE}` to `{DONE, NEW}` affect `name()`? What about `ordinal()`?

*Answer:* `NEW.name()` is still `"NEW"`; `NEW.ordinal()` changes from `0` to `1`. Data stored by ordinal can be misinterpreted.

**Question 3.** Why can renaming `RUNNING` to `IN_PROGRESS` cause `NoSuchFieldError`?

*Answer:* An enum constant is a `public static final` field on the enum class. An old binary still references the `RUNNING` field, which no longer exists on the new enum.

**Question 4.** Does `Status.valueOf("paused")` automatically map to `PAUSED` or return `null`?

*Answer:* No. `valueOf` requires an exact name match, such as `"PAUSED"` when the enum has that constant; otherwise it throws `IllegalArgumentException`. A parser with normalization, alias, and unknown-value policies is needed for external input.

**Question 5.** A legacy `switch statement` on an enum omits `default` yet still compiles. What happens when it receives a new constant with no case?

*Answer:* The statement can complete normally without executing any branch. This is a silent-skip risk, unlike an exhaustive `switch expression`.

**Question 6.** Does standard Java serialization of an enum write `ordinal` or `name`?

*Answer:* It writes the enum constant name; therefore reordering does not change the name, but renaming or removing can affect deserialization.

**Question 7.** Should `default -> "UNKNOWN"` be added to every `switch`?

*Answer:* Not as an absolute rule. Use it when a fallback matches the contract; omit `default` when you need the compiler to enforce explicit handling of every new enum constant. Both approaches require testing runtime behavior and multi-version data.

**Question 8.** A system uses the code `"running"` in the database and the Java enum changes from `RUNNING` to `IN_PROGRESS`. How can you reduce risk?

*Answer:* Keep the stable wire code `"running"` if the meaning has not changed, support legacy aliases if the code must change, deploy supporting consumers before producers emit new codes, migrate historical data with tests, and handle any old binaries still referencing the Java name `RUNNING`.

## 19. Key Takeaways

- **Adding/reordering constants:** JLS considers these binary-compatible, yet they can still break source exhaustiveness, data ordering, or runtime `switch` behavior.
- **Removing/renaming constants:** can break field references in binaries, source code, `valueOf`, and name-serialized data.
- **`ordinal` is not a durable storage code**; `name` is more stable across reordering but still depends on the declared name.
- **Exhaustive `switch expression`** helps catch missing cases at rebuild time; old binaries still need testing when run against a new enum.
- **Legacy `switch statement`** can silently ignore new values if no case or `default` matches.
- **Safe evolution policy:** design stable wire codes, provide aliases/migrations for old data, handle unknown values, test version pairs, and deploy consumers before producers whenever possible.

**Core principle:** *Binary compatibility only answers whether old machine code can link against the new type; the correctness of `switch`, parsers, and data must be verified separately across the entire lifecycle of the enum.*

### Official References

- [Java SE 21 JLS §13.4.26 — Evolution of Enum Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.26)
- [Java SE 21 JLS §14.11 — Switch Statement and Exhaustiveness](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §15.28.2 — Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2)
- [Java SE 17 API — java.lang.Enum: name, ordinal, valueOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html)
- [Java Object Serialization Specification §1.12 — Serialization of Enum Constants](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/serial-arch.html#serialization-of-enum-constants)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
