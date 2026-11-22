# Exhaustiveness When Adding a New Subtype to a Java Sealed Hierarchy

## 1. Why can adding a subtype make a switch no longer exhaustive?

When a **sealed class** or **sealed interface** permits only a fixed set of subtypes, the Java compiler can use this list to prove that a **switch expression** handles all permitted object types. The biggest benefit appears when the data model **evolves over time**: adding a new subtype can leave existing switches missing a case and cause a **compile-time error upon recompilation**.

Consider the initial version of an event model:

~~~java
sealed interface Event permits Started, Stopped {}

record Started(String id) implements Event {}
record Stopped(String id) implements Event {}

static String describe(Event event) {
    return switch (event) {
        case Started started -> "started:" + started.id();
        case Stopped stopped -> "stopped:" + stopped.id();
    };
}
~~~

This is an **illustrative Java 21 declaration and method snippet**, not a standalone program. Because **Started** and **Stopped** are all the permitted direct subtypes of **Event**, the two unguarded cases cover every non-**null** **Event** object. Therefore, no **default** is needed.

Suppose the next version adds a new state:

~~~java
// New version of the model, replacing the old declaration.
sealed interface Event permits Started, Stopped, Paused {}

record Started(String id) implements Event {}
record Stopped(String id) implements Event {}
record Paused(String id) implements Event {}
~~~

If **describe** is kept unchanged and **recompiled on Java 21 against the new model**, the compiler will see that **Paused** objects are not handled. The result is an error: **switch expression does not cover all possible input values** (the exact diagnostic wording may vary across compilers). This is the protective effect of exhaustiveness: changing the model forces consumers to consider the behavior for the new subtype.

**Key point:** the statement that "adding a subtype breaks old switches" requires distinguishing between **source compatibility upon recompilation**, **binary compatibility of already-compiled class files**, and **runtime behavior with data of the new subtype**. These three things are not entirely the same.

## 2. The right upgrade workflow: update the model, get the error, add the case

A sound evolution workflow:

1. Add **Paused** to the **permits** list of **Event**, then create a valid implementation.
2. Recompile all modules containing switch expressions that handle **Event**.
3. The compiler points out the switches that do not yet have a branch for **Paused**.
4. Add **case Paused paused** and decide the business outcome.
5. Run tests for all three subtypes, including cases where the new data comes from an API, database, or asynchronous message.

The updated switch version:

~~~java
static String describe(Event event) {
    return switch (event) {
        case Started started -> "started:" + started.id();
        case Stopped stopped -> "stopped:" + stopped.id();
        case Paused paused -> "paused:" + paused.id();
    };
}
~~~

This method has **no default** yet is exhaustive for the new version of Event. When a fourth subtype is added, maintainers will again receive a signal from the compiler.

**Adding the case is the technical part; choosing the behavior is the business part.** For a **Paused** event, the application must decide whether to log, change state, emit a notification, or reject the event. Simply adding a branch that returns a string does not mean the entire related processing flow is ready.

## 3. Full Java 21 example: the new subtype is handled

Save the program **SealedEvolutionDemo.java**:

~~~java
public class SealedEvolutionDemo {
    sealed interface Notification
            permits Sent, Failed, Queued {}

    record Sent(String id) implements Notification {}
    record Failed(String reason) implements Notification {}
    record Queued(int position) implements Notification {}

    static String describe(Notification notification) {
        return switch (notification) {
            case Sent sent -> "sent:" + sent.id();
            case Failed failed -> "failed:" + failed.reason();
            case Queued queued -> "queued:" + queued.position();
        };
    }

    static String describeWithDefault(Notification notification) {
        return switch (notification) {
            case Sent sent -> "sent";
            case Failed failed -> "failed";
            default -> "fallback";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Sent("A1")));
        System.out.println(describe(new Failed("timeout")));
        System.out.println(describe(new Queued(3)));
        System.out.println(
                describeWithDefault(new Queued(3)));
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac -encoding UTF-8 SealedEvolutionDemo.java
java SealedEvolutionDemo
~~~

Output:

~~~text
sent:A1
failed:timeout
queued:3
fallback
~~~

**Explanation of each result:**

- **Sent("A1")** matches the **Sent** branch, producing **sent:A1**.
- **Failed("timeout")** matches **Failed**, producing **failed:timeout**.
- **Queued(3)** is the new subtype in the current **permits** set; the **describe** method has a corresponding case, so it produces **queued:3**.
- **describeWithDefault** only lists **Sent** and **Failed**, followed by **default**, so the compiler still accepts it. **Queued(3)** falls into **fallback** without forcing the developer to write a dedicated handling branch.

This program shows that **default still makes a switch syntactically exhaustive, but it can suppress the signal when expanding the subtype set**. If **Queued** has mandatory dedicated business logic, a method with an overly broad default can hide a design bug even though it compiles cleanly.

**Versions:** sealed types were standardized in Java 17; pattern matching for **switch** and the **case Type variable ->** syntax became standard in Java 21. The program requires no preview features.

## 4. Should default appear in a switch over a sealed type?

There is no rule that "forbids default." The decision depends on the business contract:

| Style | When adding a new subtype and recompiling | When to use |
| --- | --- | --- |
| List every subtype, **no default** | Compiler can report missing case, forcing an update | Each type must be handled individually |
| A few subtypes + **default** | Usually still compiles, new subtype falls into default | All unlisted types genuinely share the same behavior |
| Broad parent-type case, such as **case Event e** at the end | Can still be exhaustive, new subtype matches the broad branch | You truly want uniform handling for everything remaining |
| Subtypes with **when** guards | Arbitrary guards do not by themselves guarantee exhaustiveness | Add an unguarded case covering the remainder or a fallback policy |

For example, **default** is reasonable when the task only needs to return a generic **"not supported"** description for any unhandled state, and accepting a new subtype with that behavior is the explicit intent.

Conversely, in a **state machine** with exact rules for every state, a broad default can defer bugs until users encounter the new state. In that situation, **omitting default** to leverage the compiler is usually better for maintainability.

Even when omitting default, you still need tests for each subtype: the compiler only proves that a branch **exists**, not that the branch's logic is **correct**.

## 5. How does adding a direct subtype differ from adding a subclass under an existing subtype?

The **permits** clause of a sealed type controls its **direct subtypes**. Each permitted subtype must follow Java's rules and be declared in one of the appropriate forms: **final**, **sealed**, or **non-sealed**; a **record** is implicitly final by language specification.

### 5.1. Adding a new permitted direct subtype

~~~java
sealed interface Shape permits Circle, Rectangle, Triangle {}
~~~

If a switch previously had only **case Circle** and **case Rectangle**, the Java 21 compiler no longer considers it exhaustive once **Triangle** is permitted and not yet covered.

### 5.2. Adding an implementation of an existing non-sealed branch

~~~java
sealed interface Task permits KnownTask, ExternalTask {}

record KnownTask(int id) implements Task {}

non-sealed interface ExternalTask extends Task {}

final class ThirdPartyTask implements ExternalTask {}
~~~

This is an **illustrative snippet of type declarations**, not a program with main. If a switch over **Task** has **case KnownTask known** and **case ExternalTask external**, the compiler can consider it exhaustive with respect to the permitted subtypes, and **ThirdPartyTask** is already within the matching scope of **ExternalTask**.

When adding another class that implements **ExternalTask**, a new compile-time case is not necessarily required: the **ExternalTask** case already covers every implementation of that interface. This is very important: exhaustiveness is a property of **type relationships**, not a rigid list of every class name across the entire program.

### 5.3. Multi-level sealed hierarchies

If a permitted subtype is itself **sealed**, the compiler can trace its child branches to prove exhaustiveness. When a subtype is added at a deeper level, a switch that individually lists the subtypes at that level can become non-exhaustive upon recompilation.

If the switch has a broad case directly matching the permitted parent type, the new subtype at the deeper level remains covered. Therefore, how much the compiler forces code changes depends on **how the cases partition the hierarchy**.

## 6. Source compatibility: errors appear upon recompilation

A change can cause **existing consumer source code** to stop compiling against the new model version:

~~~java
// Old version:
sealed interface State permits Open, Closed {}
record Open() implements State {}
record Closed() implements State {}

// Old switch was exhaustive.
static String label(State value) {
    return switch (value) {
        case Open opened -> "open";
        case Closed closed -> "closed";
    };
}
~~~

After updating the model to **permits Open, Closed, Suspended** and adding **record Suspended() implements State {}**, the compiler can no longer guarantee that every State matches the old switch. **The missing branch does not need to be executed at runtime to be detected**; simply recompiling against the new hierarchy is enough.

The proper fix is to **update the consumer source code**:

~~~java
// Replacement for the label method after adding the Suspended subtype:
static String label(State value) {
    return switch (value) {
        case Open opened -> "open";
        case Closed closed -> "closed";
        case Suspended suspended -> "suspended";
    };
}
~~~

The snippets in this section are **mutually exclusive versions**—do not copy both same-named declarations or methods into the same file. The complete runnable example in section 3 shows the updated state.

A useful rule during code review: **a compiler error reporting a missing case after upgrading a dependency is a signal that requires business analysis**, not just a nuisance to silence with default.

## 7. Binary compatibility: old class files may still link

The Java 21 specification draws a clear distinction between adding a permitted direct subtype of a sealed class/interface and running a switch compiled before that subtype existed:

- **Adding a permitted subtype** is generally a **binary-compatible** change for existing binaries: already-compiled class files can still link against the new model.
- However, an **exhaustive switch compiled against the old hierarchy** can encounter an **instance of the new subtype** for which the switch has no applicable label.
- When no applicable label is found at runtime, **Java 21 can throw java.lang.MatchException**. This is a **migration/runtime behavior** issue, even though the model change is binary-compatible at the linking level.
- If you **recompile** the consumer against the new model while still missing the case and lacking a suitable covering branch, the error surfaces at **compile time** instead of waiting until runtime.

This does not mean every new subtype will always cause a **MatchException**. The error can only occur when an old binary receives a value of the new type and **no case applies**. If the switch already has a **default** or a broad pattern covering that object, the corresponding branch can handle it.

**Do not confuse this with IncompatibleClassChangeError when removing a subtype:** **removing** a class from the permitted list of a sealed hierarchy has different compatibility rules and can prevent that class's binary from loading properly. This article focuses primarily on **adding a subtype**.

### Checklist table for three deployment scenarios

| Situation | Possible outcome | Recommended action |
| --- | --- | --- |
| Recompile new model + old consumer switch without default | Compile-time error because it is no longer exhaustive | Add the appropriate case |
| Replace only the new model binary, keep running consumer built with old model | May throw **MatchException** when encountering an unmatched new subtype instance | Rebuild/retest all consumers and update cases |
| Consumer has default or a general branch | May execute the fallback branch instead of a coverage error | Check whether the fallback is business-valid or hiding an omission |

Because a multi-module system may ship the **library containing the sealed model** and the **consumer containing the switch** on different schedules, both **build-time compatibility checks** and **testing with data from the new model version** are necessary.

## 8. Adding an enum constant poses a similar problem

With an enum:

~~~java
enum Phase { NEW, RUNNING, DONE }

static String label(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
    };
}
~~~

If **CANCELLED** is added to **Phase**, the original default-less switch expression will be missing a case and will typically fail to compile when recompiled. Even if the old binary still links, runtime behavior with a new enum constant that has no applicable case can fail.

As of Java 21, switch expressions and pattern switches require exhaustiveness, though **you should not assume a single fixed exception name across all Java versions**: earlier versions of switch expressions used a different runtime error type when a new enum constant appeared that an old binary did not know about. When diagnosing in practice, verify against the exact JDK being run.

Just like with sealed hierarchies, adding **default** can fall back to default behavior, but it can also mask the fact that a new business state has not been explicitly designed for.

## 9. Null, when, and case ordering when extending subtypes

### Null is not automatically handled by exhaustiveness

A switch over **Notification** that covers **Sent**, **Failed**, and **Queued** can still throw **NullPointerException** when the input is **null**. If null is a valid state, add **case null**:

~~~java
// Illustrative Java 21+ switch expression snippet:
return switch (notification) {
    case null -> "missing";
    case Sent sent -> "sent:" + sent.id();
    case Failed failed -> "failed:" + failed.reason();
    case Queued queued -> "queued:" + queued.position();
};
~~~

**case null** handles nullability, while type pattern cases handle non-null objects; the two checks must be considered separately.

### A case with when does not necessarily cover the subtype

~~~java
// Not exhaustive if this is the only case for Queued.
case Queued queued when queued.position() > 0 ->
        "queued-positive";
~~~

A **Queued(0)** will not match the guard. When adding a new subtype with multiple internal states, you need an unguarded case to catch the remainder or another valid covering structure:

~~~java
case Queued queued when queued.position() > 0 ->
        "queued-positive";
case Queued queued -> "queued-other";
~~~

These are illustrative labels inside a **Java 21 switch**, not a complete standalone program. The unguarded **Queued** case must come after the specific **when** case; otherwise, it will cause a **dominated case** error.

### A broad parent type can shadow a new subtype

If a parent-type case (for example, **case Notification n**) is placed before subtype branches, the specific branches after it can be flagged by the compiler for dominance. When a new subtype is added, place specific cases before broad cases and evaluate whether a broad case is unintentionally shadowing a dedicated handling requirement.

## 10. A safe workflow for changing a sealed model

When proposing to add a subtype, you can follow this ordered checklist:

1. **Identify the public contract of the sealed type.** Inspect the permitted direct subtypes, **final**, **sealed**, and **non-sealed** branches, and related module dependencies.
2. **Clearly define the new subtype's behavior.** For example, how should the new status be logged, transitioned, displayed in the UI, or mapped in APIs?
3. **Update the model declaration and implementation** following Java's sealed syntax.
4. **Do a clean build and recompile consumers** that use switch expressions or enhanced switches; record all non-exhaustive errors.
5. **Add dedicated handling cases**, rather than adding a blanket default just to silence errors.
6. **Audit existing switches that have default or broad patterns:** they will not necessarily trigger a compile error, but they may be accepting the new subtype with inappropriate behavior.
7. **Test every old and new subtype**, including null inputs, true/false guards, boundary cases of each state, and exception behavior.
8. **Check compatibility across multi-version deployments:** avoid running old consumer binaries with the new model without testing the new subtype; also test rolling-upgrade scenarios when the system has multiple services/modules.
9. **Review serializers/deserializers and API contracts**, because the new subtype can affect parsing, persistence, and data exchange outside switches.
10. **Document the change** and update examples/test fixtures for the new subtype; pay attention to all state machine branches and data mappings.

An easily overlooked scenario: an existing switch has a default returning **"unknown"**, so the build stays green after adding a subtype. That does not prove the business logic supports the new subtype; add tests based on realistic values of that subtype.

## 11. Self-check questions

**Q1.** A sealed interface **Result** initially has only **Ok** and **Error**; a switch expression has two cases and no default. **Pending** is added and the consumer is recompiled without modifying the switch. What happens? **A compile-time non-exhaustive switch error**, because the target type now has a new uncovered subtype.

**Q2.** Does adding **default -> "other"** fix the compile error? **Usually yes**, but it is not necessarily business-correct. If Pending requires dedicated rules, **case Pending** must be added.

**Q3.** If the consumer is not recompiled and only the new model library is deployed, is everything guaranteed to be safe? **No.** Even though the change may be binary-compatible, a Pending instance entering an old switch with no applicable branch can cause a **MatchException** on Java 21.

**Q4.** A sealed interface has a permitted subtype **External**, declared **non-sealed**, and a switch already has **case External x**. A new class is added that implements External. Will the switch always be missing a case? **No**. The External type pattern already covers those implementations as well.

**Q5.** A new subtype **Queued** is only handled by **case Queued q when q.position() > 0**. Is that sufficient for all Queued instances? **No**. Values with position 0 or negative will bypass the guard; a branch covering the remainder is needed.

**Q6.** A switch has cases for every subtype, and null is passed into a switch without case null. Does exhaustiveness prevent an NPE? **No**. Type coverage and null handling are two independent concerns.

## 12. Official references

- [JLS Java 21 §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): how the compiler computes coverage for sealed types, enums, patterns, and default.
- [JLS Java 21 §13.4.2.1 — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.2.1): adding permitted subclasses, binary compatibility, and impact on exhaustive switches.
- [JLS Java 21 §13.5.2 — Sealed and Non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.5.2): updating permitted interfaces, binary compatibility, and MatchException.
- [JLS Java 21 §15.28.2 — Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2): what happens if no label matches at runtime.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): syntax and semantics of switch patterns in Java 21.

**Conclusion:** adding a new subtype is the real-world test of exhaustive switch benefits. With a sealed hierarchy and a switch without default, the Java 21 compiler helps catch missing cases **at recompilation time**. However, **binary compatibility does not guarantee business safety at runtime with the new subtype**: old consumers can encounter **MatchException** if no branch applies. Therefore, update switches intentionally, audit existing defaults, and re-run full builds and tests when evolving type models.