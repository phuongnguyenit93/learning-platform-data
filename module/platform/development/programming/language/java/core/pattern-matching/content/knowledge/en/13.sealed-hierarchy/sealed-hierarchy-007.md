# Extending a sealed hierarchy without breaking callers in Java

## 1. The problem: a closed hierarchy while business requirements still change

**Sealed classes** and **sealed interfaces** restrict which types are allowed to directly extend or implement them via a **permits** list. This feature was standardized in **Java 17** and is very useful when a data model has only a known set of states.

Initial example:

~~~java
sealed interface Event permits Created, Deleted {}

record Created(String id) implements Event {}
record Deleted(String id) implements Event {}
~~~

A caller using **pattern matching for switch** in **Java 21** can write:

~~~java
static String render(Event event) {
    return switch (event) {
        case Created c -> "created:" + c.id();
        case Deleted d -> "deleted:" + d.id();
    };
}
~~~

The snippets above are illustrative declarations that need to be placed in a valid file/class; they are not standalone programs. Because the two records are all the permitted direct subtypes of **Event**, the compiler can prove that the **switch** expression covers all non-**null** Event objects without needing **default**.

Now the system needs to add an **Archived** state. If you modify the model to:

~~~java
// New version, REPLACES the Event declaration and subtypes above.
sealed interface Event permits Created, Deleted, Archived {}

record Created(String id) implements Event {}
record Deleted(String id) implements Event {}
record Archived(String id) implements Event {}
~~~

then the old **render** method, if **recompiled** against the new Event definition, is no longer exhaustive: **case Archived** is missing. For callers compiled before the subtype was added, the situation also carries its own risk when receiving an Archived instance at runtime.

Therefore, "extending without breaking callers" needs to be defined by an **API evolution contract**: will callers be required to handle every new subtype, or are they allowed to use fallback handling? Is it necessary to preserve source compatibility, class file compatibility, or business behavior across a multi-version upgrade?

## 2. Three levels of compatibility to distinguish

| Compatibility level | Question to answer | Risk when adding a permitted subtype |
| --- | --- | --- |
| **Source compatibility** | Does the old caller recompile against the new library? | An exhaustive switch without default may be missing a case and be rejected by the compiler |
| **Binary compatibility** | Does a previously compiled caller class file still link against the new library? | **Adding a permitted direct subtype** is a binary-compatible change according to the JLS; it does not by itself cause a linkage error |
| **Behavioral / migration compatibility** | Can the old caller handle the new object at runtime? | A switch with no applicable label may throw **MatchException** on Java 21, or fall into a fallback that is incorrect for business logic |

According to the **Java Language Specification 21**, adding a permitted direct subclass/subinterface to a sealed hierarchy is generally **binary compatible**, because previously compiled binaries can still link. However, if a **switch** compiled against the old subtype list encounters an instance of the new subtype and no label applies, it may throw **java.lang.MatchException**. The specification calls this a **migration compatibility** issue, not evidence that changing the sealed type broke binary compatibility.

That leads to two principles:

1. **A green build against the new library does not guarantee runtime safety** if some consumers still run old binaries or receive the new subtype over a data channel.
2. **Not breaking binary compatibility** does not mean **not breaking source compatibility**: recompiling a Java 21 caller with a switch without default may report an exhaustiveness error, and that is a useful signal to update the business logic.

**Note:** not every change to a sealed hierarchy is safe. *Removing* a subtype from the permitted list, changing modifiers, or altering method contracts have different compatibility rules; this article focuses on **extension** and strategies to limit impact.

## 3. Strategy A — reserve a stable extension branch

If you know the system will add new variants in the future, you can design the sealed root with a branch dedicated to extension:

~~~java
sealed interface Message permits Created, Deleted, Extension {}

record Created(String id) implements Message {}
record Deleted(String id) implements Message {}

non-sealed interface Extension extends Message {}
~~~

Here:

- **Message** remains sealed: users cannot arbitrarily create a new *direct subtype* of Message outside the permitted list.
- **Extension** is a permitted direct subinterface, but declared **non-sealed**; suitable classes can implement Extension **without modifying Message's permits list**.
- Callers can handle **case Extension extension** as a fallback branch with a clear static type.
- Later, you can add **record Paused(...) implements Extension** or **record Resumed(...) implements Extension** without adding them directly to Message's permits.

This is a way to create an **extension zone** inside a mostly closed model. It trades off part of the exhaustiveness checking in the Extension branch: the compiler knows all Extension instances match **case Extension**, but **does not force callers to enumerate every future implementation of Extension**. The contract for handling Extension must therefore proactively define behavior for unknown types as well.

**Condition for maintaining stability:** keep the direct branches of Message unchanged and do not add a new *direct* subtype outside **Created**, **Deleted**, **Extension**. If you still add a new direct subtype to permits, old exhaustive switches that lack a case for that subtype may encounter the same problem as before.

### Complete, runnable Java 21 example

Create the file **SealedCompatibilityDemo.java**:

~~~java
public class SealedCompatibilityDemo {
    sealed interface Message permits Created, Deleted, Extension {}

    record Created(String id) implements Message {}
    record Deleted(String id) implements Message {}

    non-sealed interface Extension extends Message {}

    record Paused(String id, int seconds) implements Extension {}
    record Resumed(String id) implements Extension {}

    static String handle(Message message) {
        return switch (message) {
            case null -> "missing";
            case Created c -> "created:" + c.id();
            case Deleted d -> "deleted:" + d.id();
            case Extension extension -> handleExtension(extension);
        };
    }

    static String handleExtension(Extension extension) {
        if (extension instanceof Paused paused) {
            return "paused:" + paused.id() + ":" + paused.seconds();
        }
        return "extension:" + extension.getClass().getSimpleName();
    }

    static String handleWithFallback(Message message) {
        return switch (message) {
            case null -> "missing";
            case Created c -> "created";
            case Deleted d -> "deleted";
            default -> "unknown-message";
        };
    }

    public static void main(String[] args) {
        Message[] examples = {
                new Created("A"),
                new Deleted("B"),
                new Paused("C", 5),
                new Resumed("D"),
                null
        };

        for (Message message : examples) {
            System.out.println(
                    handle(message) + " | " + handleWithFallback(message)
            );
        }
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac -encoding UTF-8 SealedCompatibilityDemo.java
java SealedCompatibilityDemo
~~~

Expected output:

~~~text
created:A | created
deleted:B | deleted
paused:C:5 | unknown-message
extension:Resumed | unknown-message
missing | missing
~~~

**How to read the output:**

1. **Created** and **Deleted** are handled by their own branches, preserving the caller's familiar contract.
2. **Paused** and **Resumed** both belong to **Extension**, so **handle** does not need a direct case added for each of these classes. This is how the switch structure on Message is preserved.
3. In **handleExtension**, the **Paused** type is handled specifically via **instanceof Paused paused**. **Resumed** does not yet have specific handling, so it receives the fallback **extension:Resumed**. When a new Extension implementation is added, the caller still has an intentional handling path.
4. **handleWithFallback** has **default**, so existing and future Extension classes all go to the **unknown-message** branch without causing a missing-case error.
5. **null** has its own **case null** branch, allowing both methods to return **missing**. You should not assume that the default of a pattern switch will automatically catch null.

This example intentionally uses **non-sealed** for Extension to illustrate the extension approach. In a real project, you should only use this open style when allowing new implementations is an intentional part of the API. If only an internal organization is allowed to create subtypes, module/package design and access rules still need to be considered separately.

## 4. Strategy B — add an intentional fallback for the caller

Sometimes you do not want to introduce an Extension branch into the model, yet you still need to allow the owner to expand the **permits** list. A Java 21 caller can choose a switch with **default**:

~~~java
static String render(Event event) {
    return switch (event) {
        case null -> "missing";
        case Created c -> "created:" + c.id();
        case Deleted d -> "deleted:" + d.id();
        default -> "unsupported-event";
    };
}
~~~

Here **Event**, **Created**, and **Deleted** are the illustrative types declared in the opening example. With the new Event version that has the **Archived** subtype, the program can recompile because default catches the unclassified part. Old binaries also have a fallback branch to handle an Archived instance according to the design contract, instead of falling into a situation where no case applies.

However, a fallback comes with a **trade-off**: the compiler no longer reminds the author "Archived is not handled specifically yet" when a subtype is added. If Archived was supposed to trigger an important workflow, silently returning **unsupported-event** can mask a business bug.

Therefore, a fallback needs a clear policy: **return a typed error**, log/metric, a safe display value for "unknown", or delegate to a handler for another version. In APIs that return business results, it is usually better to represent **unknown/unsupported** with an explicit result type rather than returning a false success.

### Use a catch-all pattern or default?

You can use a root-type pattern at the end to catch the remaining objects:

~~~java
// Java 21+ illustrative snippet placed inside a method receiving Event event:
return switch (event) {
    case Created c -> "created:" + c.id();
    case Deleted d -> "deleted:" + d.id();
    case Event unknown -> "unsupported-event";
};
~~~

**case Event unknown** covers every non-null Event object, including new subtypes. It has a typed variable **unknown** so it can be used in fallback handling. Do not add subtype cases after it: they will be shadowed by the general branch and the compiler may report a **dominated case**.

**Difference:** **default** handles remaining values according to fallback rules; **case Event unknown** is a type pattern that matches every non-null Event. If the contract allows null, you should still write an explicit null-handling branch. For sealed hierarchies where callers want the compiler to remind them when a subtype is added, **do not use either form of catch-all**.

## 5. Strategy C — keep an intermediate sealed branch

You do not always have to use non-sealed. Another approach is to keep the root stable and place types that may evolve under a **sealed** subinterface:

~~~java
sealed interface Message permits Created, Deleted, Lifecycle {}

record Created(String id) implements Message {}
record Deleted(String id) implements Message {}

sealed interface Lifecycle extends Message
        permits Paused, Resumed {}

record Paused(String id) implements Lifecycle {}
record Resumed(String id) implements Lifecycle {}
~~~

The caller handles the root with:

~~~java
static String summarize(Message message) {
    return switch (message) {
        case Created c -> "created";
        case Deleted d -> "deleted";
        case Lifecycle state -> "lifecycle";
    };
}
~~~

The snippets above are **Java 21+ illustrative code**, not a standalone program. If the owner adds a new permitted subtype **Retrying implements Lifecycle** and updates Lifecycle's permits, the **summarize** switch still has **case Lifecycle state** and continues to cover that subtype. The compiler for **summarize** does not force the caller to distinguish each Lifecycle subtype.

Conversely, a consumer switching directly on **Lifecycle** with **Paused** and **Resumed** cases and no default may have to add **case Retrying** when recompiling. The benefit of an intermediate branch is **limiting the blast radius**: general callers only know Lifecycle, while deeper business callers accept the responsibility of classifying Lifecycle's subtypes.

The difference compared to **non-sealed Extension**: the **sealed Lifecycle** branch still maintains a closed subset and exhaustiveness checking for code that wants to analyze the exact set of sub-states. That can be a better choice when the owner needs full control over new subtypes.

## 6. You cannot both force every caller to handle new subtypes and promise callers will not have to change

A sealed hierarchy that enumerates subtypes exhaustively is a **closed-world contract**. If a third party is writing:

~~~java
return switch (event) {
    case Created c -> processCreated(c);
    case Deleted d -> processDeleted(d);
};
~~~

and you add **Archived** directly to Event, the compiler has a valid reason to report a missing branch when the consumer recompiles.

That is not necessarily a "Java bug". It is a **contract change notification**. An API that wants both to expose all detailed states to callers and to freely add any new state without causing callers to change must either define fallback behavior upfront or separate a stable interface from an extensible detail layer.

Three consistent choices:

| API priority | Usually suitable design | Trade-off |
| --- | --- | --- |
| Every new subtype must be handled specifically | Sealed root + exhaustive switch, no default | Extending will require updating callers on rebuild |
| Support future subtypes with common behavior | **default** case or root-type pattern as fallback | Callers may miss new business cases |
| Stabilize high-level callers while still managing a detailed branch | Sealed root + **non-sealed** or intermediate sealed branch | Deeper callers may still need upgrades |
| Reduce type classification in callers | Appropriate polymorphism/handler/visitor | Must design interface responsibilities and versioning |

**There is no single solution that guarantees every kind of compatibility for every change.** The right approach is to determine who owns the subtypes, who owns the switch, and where fallback is permitted.

## 7. Organizing the API for controlled evolution

### 7.1. Keep public APIs less dependent on subtype names

If a service only needs to display a general message, give callers a stable method or adapter instead of requiring them to know every new record. For example:

~~~java
// Example adapter signature, not a complete program.
interface MessagePresenter {
    String present(Message message);
}
~~~

An implementation managed by the library can update the subtype handling logic when the library releases a new version. Callers only call **present(message)**, so they rarely need to edit switches directly. This does not solve every versioning problem on its own, but it **centralizes the responsibility** of updating subtypes in one place.

If you want to put behavior on the interface, consider polymorphism: implementations handle abstract methods themselves or use well-designed default methods. However, adding a required method to a public interface can cause issues for old implementations; method compatibility rules must be evaluated separately, not just by looking at sealed permits.

### 7.2. Separate "known" and "unknown" behavior

A stable classifier can return typed values such as **KnownResult** and **UnknownResult**, or use explicit error status codes. Instead of turning a new subtype into a silent success, callers can follow a rule:

- If the subtype is familiar: execute the supported workflow.
- If the subtype is new: store the information, report incomplete support, or display a safe fallback.
- If the subtype violates the contract: reject in a controlled way.

This is especially necessary for data passing through JSON, event buses, databases, or inter-service interfaces. A switch with default may not be enough: **the deserializer may reject the new data type before the switch logic is even called**. You need to check the format, discriminator, schema, and ability to read the new version as well.

### 7.3. Versioning and rolling upgrades

In multi-module systems, owners often deploy the model/producer before or after the consumer. Pay attention to:

1. Can old consumers receive new subtype data during the transition period?
2. Can the decoding layer preserve an unknown type or return a controlled error?
3. Do consumers already have a predefined default or fallback branch?
4. Is there a mechanism to monitor or disable the feature that produces the new subtype until consumers are ready?
5. Does rebuilding consumers against the new API version enable exhaustiveness checking?

A safe release strategy is to **upgrade consumers first**, adding the ability to accept or reject the new subtype according to the contract, and only then enable the producer to emit data of that subtype.

## 8. Common mistakes to avoid

**Mistake 1 — confusing binary compatible with "never fails at runtime".** Adding a permitted direct subtype does not necessarily break class file linkage, but an old exhaustive switch may throw **MatchException** when encountering a new subtype that has no case.

**Mistake 2 — adding default just to silence compiler errors.** Default makes a switch exhaustive, but does not guarantee the fallback meets business requirements. If the new state is important, it needs dedicated handling.

**Mistake 3 — forgetting null.** Type patterns like **case Created c** and **case Extension e** do not match null. **default** does not replace **case null** in the reference switches illustrated above; lacking a null-handling case can throw **NullPointerException**.

**Mistake 4 — non-sealed extension without a general handling branch.** If Root allows Extension to have countless future implementations, callers that want stability must have **case Extension** or a fallback covering them, rather than only listing currently known classes.

**Mistake 5 — keeping root permits unchanged and assuming direct subtypes can be added freely.** A sealed root still restricts direct subtypes. To add a variant without changing the root, it must implement an appropriate permitted subinterface, such as Extension.

**Mistake 6 — assuming every caller is safe because one switch has a default.** Other callers may cast, serialize/deserialize, check class names, or switch without default. You need to inventory all points that depend on the hierarchy.

**Mistake 7 — guards when only guarded branches exist.** **case Extension e when supported(e)** does not cover Extensions that do not satisfy the guard; an unguarded Extension case or appropriate fallback is needed.

**Mistake 8 — changing from sealed to non-sealed to "get rid of errors" without reviewing API impact.** Opening up implementation rights can break domain invariants, introduce uncontrolled implementations, and change caller expectations.

**Mistake 9 — assuming exhaustiveness also checks business logic.** The compiler only guarantees a type-appropriate case; it does not prove that a branch returns the right result, avoids bad side effects, or handles serializers properly.

**Mistake 10 — not testing old binaries.** A clean build of the entire project only checks source compatibility of the new code. If the actual system updates one service at a time, you must also test the path where an old-version consumer receives the new subtype.

## 9. Pre-release verification checklist

1. **Determine the scope of extension:** adding a direct subtype of the root, adding a subtype under a sealed branch, or adding an implementation of a non-sealed branch?
2. **Inventory caller contracts:** do callers have exhaustive switches without default, general patterns, default, visitors, or adapters?
3. **Distinguish the three compatibility levels:** source on rebuild, binary on linking, behavior when encountering new data.
4. **Choose an unknown-subtype policy:** require a dedicated case, safe fallback, controlled error, or forbid sending to old consumers?
5. **Recompile consumers** against the new model version to detect non-exhaustive switches, dominance, and other API changes.
6. **Test all old and new subtypes**, including null, true/false guards, invalid data, and fallback results.
7. **Test version-skew scenarios**, especially callers built before the new subtype existed; check paths that could trigger MatchException.
8. **Check serializers and transport schemas**: a correct switch is useless if the new data cannot be parsed yet.
9. **Monitor fallbacks** with logs/metrics/tests rather than silently treating unknown subtypes as fully handled.
10. **Write upgrade instructions**: which version introduces the subtype, which consumers need changes, and when producers may emit the new data format.

### Self-check questions

**Question 1.** A sealed root initially has **Created** and **Deleted**; a Java 21 switch lists both with no default. The owner adds the direct subtype **Archived**. When rebuilding the old caller, what happens? **The compiler may report that the switch is not exhaustive.** That is an intentional check.

**Question 2.** Without rebuilding the caller, you only replace the library with a version that permits Archived. Will the old binary definitely fail to link? **No.** Adding a permitted subtype is binary compatible, but if Archived enters an old switch with no applicable label, Java 21 may throw **MatchException**.

**Question 3.** There is **sealed Message permits Created, Deleted, Extension** and **non-sealed Extension**. Does adding **Paused implements Extension** require modifying Message's permits list? **No.** Callers with **case Extension** will cover Paused.

**Question 4.** A caller only writes **case Extension e when e instanceof Paused** with no branch for other Extensions. Is it guaranteed to be exhaustive? **No.** A new implementation might not satisfy the guard.

**Question 5.** The root has a default returning **unknown**; when a new subtype is added, is everything guaranteed to be right? **Not yet**. You must check whether the unknown handling satisfies business requirements, error contracts, and the upgrade process.

**Question 6.** A sealed root has a sub-branch **sealed Lifecycle**; a high-level caller uses **case Lifecycle l**, while a low-level caller switches separately on Lifecycle. If a subtype is added to Lifecycle, who risks having to change? **The low-level caller** that enumerates each subtype without default; the high-level caller with case Lifecycle already covers that branch.

## 10. Official documentation

- [JLS Java SE 21, §13.4.2.1 — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.2.1): binary and migration compatibility when adding a permitted subclass.
- [JLS Java SE 21, §13.5.2 — Sealed and Non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.5.2): changing the set of permitted subinterfaces and behavior of old binaries.
- [JLS Java SE 21, §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): how the compiler analyzes exhaustiveness.
- [JLS Java SE 21, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): how switch expressions produce results and handle non-matching labels.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): purpose and mechanism for restricting subtypes.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type patterns, exhaustive switches, dominance, and null.

**Conclusion:** safely extending a sealed hierarchy requires deciding upfront *whether callers need to know each subtype*. If callers must handle every type specifically, an exhaustive switch without default is a good mechanism and adding a subtype can intentionally fail the build. If evolutionary compatibility is the priority, reserve an extension branch with a general case, use an explicit fallback, or centralize handling in a stable API. Whichever approach you choose, verify **source, binary, and runtime behavior** separately; "adding a permitted subtype is binary compatible" does not mean old consumers already understand the new data.