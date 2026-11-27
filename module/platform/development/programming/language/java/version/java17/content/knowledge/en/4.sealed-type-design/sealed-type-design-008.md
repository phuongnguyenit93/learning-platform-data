# Changing the Subtype List of a `sealed` Type and Its Impact on Client Code in Java 17

**Topic:** Java 17 → Designing with sealed  
**Focus:** Understanding what happens when adding, removing, or modifying subtypes in a `sealed` hierarchy—from compile errors to behavioral changes in running programs.

In Java 17, `sealed class` and `sealed interface` are **standard** language features. They let a parent type specify which types are allowed to **directly** `extends` or `implements` it. That list typically represents the cases the application knows how to handle. Consequently, when the list changes, you are not merely editing one declaration line: you are changing the data model's contract with every caller that uses it.

This lesson uses only stable features of **Java 17**, such as `sealed`, `record`, and pattern matching for `instanceof`. It does not use pattern matching for `switch`, because that feature is still in *preview* in Java 17 itself.

## 1. The `permits` List Is Part of the Type Contract

Consider a processing result model:

~~~java
public sealed interface OperationResult
        permits OperationResult.Success, OperationResult.Failure {

    record Success(String value) implements OperationResult {}

    record Failure(String reason) implements OperationResult {}
}
~~~

This declaration means:

- `OperationResult` permits only `Success` and `Failure` to **directly** implement it.
- Both subtypes are `record` types, so they are implicitly `final`: no class can inherit from a record.
- Calling code knows the model is currently designed around two direct cases.
- `permits` **does not** automatically guarantee every `if` branch in client code handles everything properly; that remains the program's responsibility.

We can depict the initial structure:

~~~text
OperationResult (sealed interface)
├── Success (record, final)
└── Failure (record, final)
~~~

When adding a `Pending` case:

~~~java
public sealed interface OperationResult
        permits OperationResult.Success,
                OperationResult.Failure,
                OperationResult.Pending {

    record Success(String value) implements OperationResult {}

    record Failure(String reason) implements OperationResult {}

    record Pending(String requestId) implements OperationResult {}
}
~~~

the permitted case set expands:

~~~text
OperationResult (sealed interface)
├── Success (record, final)
├── Failure (record, final)
└── Pending (record, final)   ← new case
~~~

A valid change on the library side can still cause older client code to misbehave or throw an exception when receiving `Pending`.

> **Important distinction:** `permits` restricts **direct** subtypes. If a subtype is `non-sealed`, **indirect** subtypes can continue appearing without adding their names to the root-level `permits` list.

## 2. Kinds of Changes to Distinguish

| Change | Resulting hierarchy | Notable impact on calling code |
| --- | --- | --- |
| **Add a direct subtype** to `permits` | A new valid case appears. | Older code may not yet know how to display, store, or process this case. |
| **Remove a subtype** from `permits` | That type is no longer permitted to directly extend/implement. | If the subtype source keeps the old relationship, it fails to compile; older binaries also risk linkage errors on load. |
| **Rename or move a subtype to another package/module** | Binary name, accessibility, or position in the hierarchy can change. | Imports, instantiations, type matching, and compiled dependencies can break. |
| Change a subtype from **`final` to `non-sealed`** (when it is a valid subclass of a sealed type) | That branch can now be extended further. | Code that previously assumed a "closed" branch must account for new indirect subtypes. |
| Change a subtype from **`non-sealed` to `sealed`** | An open branch becomes one restricting direct subtypes. | Subclasses not in the permitted list may become invalid. |
| Change the data shape or behavior of a subtype | The `permits` list may stay unchanged. | Constructors, accessors, validation rules, and business outcomes for callers can change. |

There is no single "compatible" verdict covering all changes. Evaluate at least **three layers**: whether source code recompiles, whether compiled binaries load/run, and whether business behavior stays correct.

## 3. Step-by-Step Example: Adding a New Subtype

Let's build a small API compilable with Java 17, then observe the impact of adding `Pending`.

### 3.1. Version 1 — Only `Success` and `Failure`

**File `OperationResult.java`:**

~~~java
public sealed interface OperationResult
        permits OperationResult.Success, OperationResult.Failure {

    record Success(String value) implements OperationResult {}

    record Failure(String reason) implements OperationResult {}
}
~~~

**File `ResultPrinter.java`:**

~~~java
public class ResultPrinter {
    static String format(OperationResult result) {
        if (result instanceof OperationResult.Success success) {
            return "Success: " + success.value();
        }
        if (result instanceof OperationResult.Failure failure) {
            return "Failure: " + failure.reason();
        }

        throw new IllegalArgumentException(
            "Unsupported result type: " + result.getClass().getName()
        );
    }

    public static void main(String[] args) {
        OperationResult result = new OperationResult.Success("Saved");
        System.out.println(format(result));
    }
}
~~~

Compile and run commands:

~~~shell
javac --release 17 OperationResult.java ResultPrinter.java
java ResultPrinter
~~~

Output:

~~~text
Success: Saved
~~~

In version 1, `format` has two `instanceof` branches corresponding to the two permitted subtypes. The branch throwing an exception expresses a **fail-fast** policy if a type the method does not support appears.

### 3.2. Version 2 — Adding `Pending`

Replace the contents of `OperationResult.java` with:

~~~java
public sealed interface OperationResult
        permits OperationResult.Success,
                OperationResult.Failure,
                OperationResult.Pending {

    record Success(String value) implements OperationResult {}

    record Failure(String reason) implements OperationResult {}

    record Pending(String requestId) implements OperationResult {}
}
~~~

If another component constructs `new OperationResult.Pending("REQ-42")` and passes it to version 1's `ResultPrinter.format`, both existing `instanceof` conditions evaluate to false. Execution enters the branch throwing `IllegalArgumentException`.

Note the distinction:

- **Version 2's API compiles cleanly:** `Pending` is declared in `permits` and is an implicitly `final` record.
- **Version 1 client code still recompiles:** `if`/`instanceof` chains in Java 17 do not check exhaustiveness across all branches of a sealed type.
- **Behavior may no longer be appropriate:** the system now receives a valid new outcome that the old handler does not support.

This is a classic example of a change that is **source-compatible at compile time** yet requires **behavioral updates**.

### 3.3. Updating Client Code to Support the New Type

Update `format`:

~~~java
static String format(OperationResult result) {
    if (result instanceof OperationResult.Success success) {
        return "Success: " + success.value();
    }
    if (result instanceof OperationResult.Failure failure) {
        return "Failure: " + failure.reason();
    }
    if (result instanceof OperationResult.Pending pending) {
        return "Pending, request ID: " + pending.requestId();
    }

    throw new IllegalArgumentException(
        "Unsupported result type: " + result.getClass().getName()
    );
}
~~~

With `new OperationResult.Pending("REQ-42")`, the output becomes:

~~~text
Pending, request ID: REQ-42
~~~

This snippet uses **pattern matching for `instanceof`**, a standard feature built into Java 17. There is no need for `case Pending p -> ...` inside `switch`, because pattern matching in `switch` is still preview in Java 17.

### 3.4. What Should the Fallback Branch Do?

No single fallback strategy fits every application. Some options:

| Use case | Policy on encountering a new subtype | Reason |
| --- | --- | --- |
| Display-only user information | May show a neutral label while logging an event to update the UI. | Avoid crashing the display flow over a newly introduced, not-yet-formatted type. |
| Transaction processing, financial decisions, or authorization | Fail safely or halt explicitly; never treat an unknown type as success. | Misclassification can corrupt critical business state. |
| Data sync across multiple service versions | Agree on a compatibility policy beforehand for new values; consider protocol versioning. | Older receivers must know whether to skip, buffer, reject, or error. |
| APIs requiring that only defined cases be accepted | Throw an exception with the concrete type information. | Surfaces handlers that have fallen behind the contract. |

Example of a default pattern to avoid:

~~~java
// Avoid: treating any unrecognized type as success.
return "Success";
~~~

What must be decided is **the semantics of the new type**, not merely how to stop the application from throwing an exception.

## 4. Adding a Subtype: How Source, Binary, and Behavioral Compatibility Differ

When replacing version 1 of a library containing a sealed hierarchy with version 2, distinguish:

**Source compatibility** means client code can recompile against the new API. With `if`/`instanceof` branches like those above, **merely adding** a subtype usually does not cause existing branches to fail compilation. However, other rules such as constructors, methods, visibility, and simultaneous API changes must still be checked.

**Binary compatibility** means previously compiled class files can link and run against the new library version under JVM rules. **Adding** a permitted subtype generally does not force existing binary consumers to recompile, provided the classes, methods, binary names, and API structures they already use remain intact. This does not promise identical runtime outcomes.

**Behavioral compatibility** means the program still handles new inputs and outcomes properly. An older binary may load cleanly and then throw an exception in an "unsupported type" branch, misrecord data, drop events, or return inaccurate content.

Visual illustration:

~~~text
Library v1
    OperationResult -> Success | Failure
           │
           ▼
Client code v1: handles Success, Failure

Library v2
    OperationResult -> Success | Failure | Pending
           │
           ▼
Client code v1: can run, but does not know how to handle Pending
           │
           ▼
Client code v2: handles Pending under new business rules
~~~

**Adding to `permits` does not automatically update clients.** For public libraries, publishing a new release with release notes is part of maintaining the API contract.

## 5. Removing a Subtype: Impact Can Be Far More Severe

Suppose originally:

~~~java
sealed interface JobState permits Running, Paused, Stopped {
}

record Running() implements JobState {}

record Paused() implements JobState {}

record Stopped() implements JobState {}
~~~

Later, the application removes the `Paused` state and changes the sealed interface to:

~~~java
sealed interface JobState permits Running, Stopped {
}
~~~

There are two distinct scenarios.

### 5.1. Keeping the Source of `Paused`

If `Paused` still declares `implements JobState` in source code, the Java 17 compiler rejects it because `Paused` is no longer in the permitted direct subtype list.

To rebuild from source, the team must actually migrate/delete/remodel `Paused` and update every site that constructs or consumes it.

### 5.2. Keeping an Old Compiled `Paused` Class File

When a previously compiled `Paused` binary still implements `JobState`, yet the new `JobState` no longer permits it, the JVM can throw **`IncompatibleClassChangeError` when loading/linking the subtype**. This is the **binary compatibility** hazard of narrowing the permitted subtype list. If `Paused` was deleted from the dependency while an older client still references it, class-resolution errors such as `NoClassDefFoundError` can also occur.

Do not assume that "already compiled code is unaffected by `permits`." Sealed hierarchies are encoded in class-file metadata and verified by the JVM.

### 5.3. A Less Disruptive Deprecation/Removal Workflow

A practical workflow might include:

1. **Locate every dependent site:** constructors, `instanceof` checks, return APIs, stored data, and messages/events involving `Paused`.
2. **Stop producing the old state** deliberately while continuing to handle older values if they still exist.
3. **Migrate stored data and communication contracts** to a replacement state. Do not map the old state onto another state without verified semantic equivalence.
4. **Update all consuming components** before releasing the hierarchy removal change.
5. **Build and deploy consistently** across libraries and client code, avoiding mixing binaries from incompatible versions.

For APIs shared across teams, removing a subtype often requires a major (breaking) release rather than a minor release.

## 6. Changing `final`, `sealed`, and `non-sealed` on Branches

The direct `permits` list is not the entire inheritance tree. Branch shapes matter as well.

### 6.1. A `final` Branch Is Closed

~~~java
sealed interface Notification
        permits Email, Internal {
}

record Email(String address) implements Notification {}

final class Internal implements Notification {}
~~~

`Email` is a record and `Internal` is a final class, so neither can have subtypes. When an API consists purely of closed branches like these, the concrete type set can be understood fairly clearly from the hierarchy.

### 6.2. A `non-sealed` Branch Permits Indirect Extension

~~~java
sealed interface Notification
        permits Email, External {
}

record Email(String address) implements Notification {}

non-sealed interface External extends Notification {
    String target();
}

final class Webhook implements External {
    @Override
    public String target() {
        return "https://example.com/hook";
    }
}
~~~

Here `Notification` still permits only two **direct** subtypes: `Email` and `External`. Yet `Webhook` is a valid indirect implementation through `External`, and future types can also `implements External`.

This affects calling code:

~~~java
static String describe(Notification notification) {
    if (notification instanceof Email email) {
        return "Email: " + email.address();
    }
    if (notification instanceof External external) {
        return "External system: " + external.target();
    }
    throw new IllegalArgumentException("Unsupported type");
}
~~~

The `External` branch handles both `Webhook` and other implementations of `External`. However, if individual implementations need different behavior, checking only the parent interface will not suffice. Decide whether to rely on a shared contract, add polymorphic methods, or promote key cases into the type model.

**Design warning:** never infer that a sealed type has only two concrete object types just because `permits` lists two names. Always check whether any branch is `non-sealed`.

### 6.3. Restricting an Existing Branch with `sealed`

Suppose `External` was initially `non-sealed` and external libraries implemented it. Changing `External` to `sealed interface External permits Webhook` stops other existing implementations from directly extending `External`. This can break source or binary compatibility for existing extensions.

Before narrowing a branch, identify everyone who owns and implements subtypes, including subtypes in other modules. With named modules, permitted direct subtypes must live in the same named module as the sealed type; with unnamed modules, they must live in the same package.

## 7. Renaming, Moving, and Modifying Subtype Structure

Not every risky change shows up as adding or deleting a name in `permits`.

**Renaming `Failure` to `Rejected`:** clients using `new Failure(...)`, `instanceof Failure`, `import Failure`, or `Failure`'s accessors must be updated. If the old class file is removed, binaries referencing the old name will hit linkage/class-resolution errors. Changing docs alone without a migration policy is not enough.

**Moving a subtype to another package/module:** review `permits`, imports, visibility, binary names, and Java 17's same-package/same-module rules. Moving a subtype outside the permitted scope cannot be fixed merely by writing the new name in `permits`.

**Changing a `record` to a regular `class`:** even if the new type remains valid in `permits`, callers may depend on the record's canonical constructor, record accessors, `equals`, `hashCode`, `toString`, or record-style construction. This is a data-contract change requiring separate evaluation.

**Changing constructors, fields, methods, or generic structure:** even when the subtype list is unchanged, source, binary, or behavioral compatibility can still break. `sealed` does not replace standard API versioning discipline.

## 8. Writing Client Code Suitable for Java 17

### 8.1. Use `instanceof` Pattern Matching Explicitly

Java 17 code can handle each branch via:

~~~java
if (result instanceof OperationResult.Success success) {
    // Use success.value()
} else if (result instanceof OperationResult.Failure failure) {
    // Use failure.reason()
} else {
    // Define policy when the API introduces a new subtype.
}
~~~

This is stable Java 17 syntax. It requires no preview flag and **emits no compiler warning** when a sealed interface gains a new subtype.

### 8.2. Prefer Polymorphic Behavior When Appropriate

In some cases, instead of placing `instanceof` chains across many clients, you can declare shared behavior:

~~~java
sealed interface DisplayResult permits DisplayResult.Ok, DisplayResult.Error {
    String displayText();

    record Ok(String value) implements DisplayResult {
        @Override
        public String displayText() {
            return "Success: " + value;
        }
    }

    record Error(String reason) implements DisplayResult {
        @Override
        public String displayText() {
            return "Error: " + reason;
        }
    }
}
~~~

Clients simply do:

~~~java
String text = result.displayText();
~~~

If the library later adds a new direct subtype, that subtype must also implement `displayText()` (unless it inherits a valid implementation). This co-locates display logic near the data and can reduce the number of client sites requiring edits.

However, **not every decision belongs in subtypes**: storage, authorization, UI presentation, and client-specific business rules can vary per consumer. Use polymorphism when the behavior is genuinely shared and belongs to the model's responsibility.

### 8.3. Avoid Relying on Java 17 Preview Pattern `switch`

In Java 17, examples such as:

~~~java
// Do not use as stable Java 17 syntax:
// return switch (result) {
//     case OperationResult.Success s -> s.value();
//     case OperationResult.Failure f -> f.reason();
// };
~~~

belong to pattern matching in `switch`, which was experimental in Java 17. Exhaustiveness analyses for pattern `switch` in newer Java versions must not be assumed as a standard Java 17 language guarantee.

When a course targets Java 17, use `instanceof`, polymorphic methods, or contract-driven API design as shown above.

## 9. Inspecting the Permitted Subtype List via Reflection

Java 17 provides the standard reflection APIs `Class.isSealed()` and `Class.getPermittedSubclasses()`. You can use them for diagnostics or verifying the hierarchy structure actually loaded.

With version 2 of `OperationResult.java` above, create **`InspectPermits.java`**:

~~~java
public class InspectPermits {
    public static void main(String[] args) {
        Class<OperationResult> type = OperationResult.class;

        System.out.println("Sealed: " + type.isSealed());

        Class<?>[] permitted = type.getPermittedSubclasses();
        if (permitted != null) {
            for (Class<?> subtype : permitted) {
                System.out.println(subtype.getName());
            }
        }
    }
}
~~~

Compile with:

~~~shell
javac --release 17 OperationResult.java InspectPermits.java
java InspectPermits
~~~

With version 2, the expected output is `Sealed: true` followed by the nested class names corresponding to `Success`, `Failure`, and `Pending` (such as `OperationResult$Success`). Do not depend on the printed order in business logic.

`getPermittedSubclasses()` returns **direct** permitted subtypes, not an automatic traversal of all multi-level descendants. For non-`sealed` types, this API returns `null`. Reflection is useful for runtime inspection, yet **does not replace** versioning policies or updating code to handle new subtypes.

## 10. Impact on Persisted Data and Inter-Service Communication

`sealed` is a Java type-system rule; it does not automatically manage JSON formats, database records, message-broker events, or cross-version compatibility between services.

For example, an application serializes a result as:

~~~json
{
  "type": "success",
  "value": "Saved"
}
~~~

If after expanding the hierarchy, a new service instance sends:

~~~json
{
  "type": "pending",
  "requestId": "REQ-42"
}
~~~

an older service that knows only `success` and `failure` may fail to decode the new message. Adding `Pending` to the sealed interface **does not make older decoders understand `type=pending`**.

When managing data across versions, clarify:

1. **Formats and type discriminators:** such as `success`, `failure`, `pending`, defined in the data contract rather than tied arbitrarily to Java class names.
2. **Reading older data:** after removing or renaming `Failure`, how will the new application handle legacy records?
3. **Older receivers encountering new data:** will they reject, quarantine, ignore with logging, or negotiate a protocol version?
4. **Deployment order:** in what sequence are readers and writers upgraded so unsupported cases are not produced prematurely?
5. **Security and data validation boundaries:** accept only permitted subtypes and values per your parser and business rules; never trust external payloads just because Java classes are sealed.

In distributed systems, "just adding a subtype" can still be a **protocol breaking change** if receivers require recognizing every variant.

## 11. Strategy for Evolving `sealed` Hierarchies in Real Projects

### 11.1. Before Adding a Subtype

Determine whether the new case truly differs in **semantics** and **data**. If it is only a presentation difference, a field or shared behavior may suffice; if it has its own lifecycle or business rules, a new subtype may be clearer.

Find all places using the parent type as a parameter, return type, or field; pay special attention to `instanceof` chains, factories, serializers, type-keyed maps/registries, handlers, workflows, and fallback exception paths.

### 11.2. When Modifying Subtypes

Keep existing subtypes intact if you are only extending the API. Ensure the new subtype has a valid modifier (`final`, `sealed`, or `non-sealed` per Java 17 rules), is listed properly in `permits`, resides in the right package/module, and carries the required data.

If removing or replacing a subtype, establish a clear migration plan for old clients and stored data. Changing `permits` before updating dependent components can cause build or deployment failures.

### 11.3. During Release

A typical rollout sequence when **adding** a subtype across services:

1. Update the contract and announce the new data type.
2. Upgrade **readers/consumers** to understand or safely handle the new type.
3. Then enable **writers/producers** to emit the new type.
4. Monitor unsupported-type errors and business behavior during rollout.

When **removing** a subtype, generally work in reverse at the data level: stop producing legacy values, drain or migrate remaining legacy values, and only then drop the type from the API and consumers. Exact sequencing depends on your system and team contracts.

### 11.4. When Upgrading Libraries

Ensure the application does not accidentally mix class files from two incompatible versions. If a new version removes a subtype while another library was compiled against the old subtype, errors may surface only when the JVM actually loads that class.

Dependency version management, migration guides, and testing critical business flows help catch impacts that compilation alone cannot reveal.

## 12. When Should You Avoid `sealed`?

`sealed` fits when a hierarchy has **intentionally controlled direct cases**. It is a poor fit when the design expects plugins or external applications to directly add implementations from their own packages or modules.

For APIs requiring public extensibility, consider:

- A regular interface allowing diverse implementations.
- A sealed hierarchy restricting only top-level categories, with a `non-sealed` branch serving as the extension point.
- Keeping internal result types sealed while using a separate interface for the external plugin contract.

The trade-off is between **model control** and **extensibility**. Choosing `sealed` makes direct cases easy to read and govern, while also turning changes to that type set into API evolution events requiring careful version management.

## 13. Frequently Asked Questions

**Does adding a new name to `permits` break compilation in all old clients?**  
No. With Java 17 `if`/`instanceof` chains like the examples, old code usually still compiles. However, when receiving the new subtype, that code may fail to handle it properly.

**Can I omit `default` or the fallback branch because a sealed interface has only a few subtypes?**  
That depends on structure and handling style. In stable Java 17, `if`/`instanceof` chains are not guaranteed by the compiler to cover every case. A fallback branch makes the policy explicit when an unexpected case arrives, especially across API upgrades.

**Can a subtype omitted from `permits` still exist if compiled against an older version?**  
It cannot be treated as valid: the JVM enforces sealed constraints during type linking/loading. An older subtype binary can cause `IncompatibleClassChangeError` if the new supertype no longer permits it.

**Does adding an indirect subtype require editing the root type's `permits`?**  
Not necessarily. If that subtype inherits through a `non-sealed` branch, only the direct branch type appears in the root's `permits` list.

**Can I use `switch` pattern matching so the compiler reports missing cases in Java 17?**  
That feature is still in preview in Java 17, so it falls outside the stable API/syntax covered by this lesson. You can use `instanceof` or polymorphism as demonstrated.

**When does a subtype change require a major version?**  
Java prescribes no fixed versioning rule. Removing/renaming a subtype, altering data contracts, or causing clients to mishandle a case are signals to evaluate it as a breaking change under your library or system release policy.

## 14. Official References

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): sealed classes and interfaces becoming a standard feature in Java 17.
- [Java Language Specification 17, Chapter 8 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): direct subtype restrictions, `permits`, `final`, `sealed`, `non-sealed`.
- [Java Language Specification 17, Chapter 9 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): sealed interfaces and permitted direct subinterfaces/implementations.
- [Java Language Specification 17, Chapter 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): evaluating API changes against compiled binaries.
- [Java SE 17 API, `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isSealed()`, `getPermittedSubclasses()`.
- [JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): why `switch` pattern matching is not used as standard Java 17 syntax.

**Design principle:** Treat edits to `permits` as changes to both the type contract and data-processing flows. Alongside ensuring Java 17 compilation succeeds, review legacy consumers, deployed binaries, persisted data, and the domain semantics of each subtype.
