# The Problem of Restricting Subtypes in a Data Domain

## 1. The problem: a data domain with only a fixed set of valid cases

Suppose a payment system needs to represent **the outcome of processing a transaction**. According to the current business rules, a single processing attempt can produce only one of three outcomes:

1. **Approved:** the transaction succeeded, carrying a transaction ID and an amount.
2. **Declined:** the transaction could not be completed, carrying a specific reason.
3. **PendingVerification:** the customer must complete a verification step, carrying a request ID for tracking.

The three outcomes carry **different associated data**, yet all of them can be passed through the same abstract type `PaymentResult`. This is a common pattern in domains with a strictly defined set of cases: login results, approval statuses, command types in a processor, parsing results, or responses from an ordering workflow.

What matters most is the following rule:

> Every object accepted as a `PaymentResult` must belong to one of the cases permitted by the business domain.

If you only write a regular `interface`, Java allows other classes to implement that interface, even when the designer did not intentionally list them. The "only three cases" rule then exists in documentation and agreements between developers, but it is **not enforced by the compiler**.

Java 17 can express this rule using a **sealed class** or **sealed interface**. The sealed feature was standardized in Java 17 (JEP 409). This lesson moves from the need to restrict subtypes in a data domain to how to use `sealed` properly and recognize its limitations.

## 2. Open model: why a regular interface is not enough

Consider the declaration:

```java
public interface PaymentResult {
}
```

The three agreed-upon types:

```java
public record Approved(String transactionId) implements PaymentResult {
}

public record Declined(String reason) implements PaymentResult {
}

public record PendingVerification(String requestId) implements PaymentResult {
}
```

Syntactically, someone else can still write:

```java
public record UnknownResult(String payload) implements PaymentResult {
}
```

The snippets above illustrate declarations in **separate files** (or they could be placed as appropriate nested types). If `PaymentResult` is a public interface, `UnknownResult` can perfectly well implement it even though it is not among the three defined business cases. When another part of the system receives a `PaymentResult`, it might encounter an unfamiliar type and have to guess how to handle it.

For example:

```java
static String describe(PaymentResult result) {
    if (result instanceof Approved approved) {
        return "Success: " + approved.transactionId();
    }
    if (result instanceof Declined declined) {
        return "Declined: " + declined.reason();
    }
    if (result instanceof PendingVerification pending) {
        return "Verification required: " + pending.requestId();
    }
    return "Unknown result";
}
```

The final branch forces the application to confront the possibility of additional implementation types. In a domain that truly allows only three cases, this is a gap between the **business rule** and the **type contract**.

Workarounds such as checking class names as strings, starting from `Object`, or making all fields in a single object nullable usually make the code harder to maintain. We need to declare the set of valid types directly.

## 3. Sealed interface: turning a business rule into a Java constraint

In Java 17, the syntax:

```java
public sealed interface PaymentResult
        permits Approved, Declined, PendingVerification {
}
```

means that `PaymentResult` **only allows the three types named in `permits` to inherit/implement it directly**.

The permitted types:

```java
public record Approved(String transactionId) implements PaymentResult {
}

public record Declined(String reason) implements PaymentResult {
}

public record PendingVerification(String requestId) implements PaymentResult {
}
```

With declarations placed according to Java's package/module rules, this is a valid model. A `record` is implicitly `final`, so it satisfies the requirement for a direct implementation type of a sealed interface.

If someone tries to implement another case:

```java
// Intentionally INVALID example:
public record UnknownResult(String payload) implements PaymentResult {
}
```

the compiler will reject it because `UnknownResult` is **not listed in `permits`**. The error appears immediately at compile time, before the system ever has to handle an unexpected object at runtime.

Model diagram:

```text
PaymentResult  («sealed interface»)
│
├── Approved               («record», final)
│   └── transactionId
│
├── Declined               («record», final)
│   └── reason
│
└── PendingVerification    («record», final)
    └── requestId
```

The domain rule is directly visible in the diagram: a `PaymentResult` can belong to the three permitted branches. Choosing records in this example is an appropriate decision for **immutable data outcomes (shallowly immutable at the component reference level)**, while the authority to restrict branches comes from `sealed`.

### 3.1. What does `sealed` actually guarantee?

When declared properly, `sealed` provides:

- **Control over direct inheritance:** only types in the permitted list can `extends`/`implements` the sealed type.
- **Expression of a known set of cases:** the branch names become part of the type contract.
- **Compile-time prevention of ad-hoc implementations:** instead of discovering them when a transaction hits an unknown handling branch at runtime.
- **Better readability:** developers know where to look to understand the scope of the domain.
- **A foundation for tooling and future language features:** newer Java versions can use pattern matching in `switch` to leverage closed-set information. Be sure to distinguish those capabilities from Java 17.

`sealed` **does not automatically** check every business rule. It does not prove that `transactionId` is valid, that `reason` is non-blank, that the transaction was persisted to a database, or that a sequence of state transitions is valid. Those rules still require validation, service logic, data transactions, and testing.

### 3.2. `sealed` restricts **direct subtypes**

This is the most important point when reading the syntax. `permits A, B` does not mean the entire inheritance tree has only two concrete types at every level. Each permitted type `A` or `B` can decide whether its own branch can be extended further, using `final`, `sealed`, or `non-sealed`.

Therefore, to keep the model's set of outcomes finite, consider **closing leaf branches** with `final` or using records. Do not add `non-sealed` just to silence a compiler error.

## 4. Complete example running on Java 17

To illustrate with a single file you can copy and run directly, we place the types as nested members inside a public class. The example includes three result branches, basic validation, and code that dispatches on the result type.

Create the file **PaymentResultDemo.java**:

```java
import java.util.Objects;

public class PaymentResultDemo {

    public sealed interface PaymentResult
            permits Approved, Declined, PendingVerification {
    }

    public record Approved(String transactionId, long amountInCents)
            implements PaymentResult {

        public Approved {
            Objects.requireNonNull(transactionId, "transactionId");
            if (transactionId.isBlank()) {
                throw new IllegalArgumentException("Transaction ID must not be blank");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException("Amount must be positive");
            }
        }
    }

    public record Declined(String reason) implements PaymentResult {

        public Declined {
            Objects.requireNonNull(reason, "reason");
            if (reason.isBlank()) {
                throw new IllegalArgumentException("Reason must not be blank");
            }
        }
    }

    public record PendingVerification(String requestId)
            implements PaymentResult {

        public PendingVerification {
            Objects.requireNonNull(requestId, "requestId");
            if (requestId.isBlank()) {
                throw new IllegalArgumentException("Request ID must not be blank");
            }
        }
    }

    static PaymentResult pay(long amountInCents, boolean needsVerification) {
        if (amountInCents <= 0) {
            return new Declined("Invalid amount");
        }
        if (needsVerification) {
            return new PendingVerification("VERIFY-001");
        }
        return new Approved("TX-001", amountInCents);
    }

    static String explain(PaymentResult result) {
        if (result instanceof Approved approved) {
            return "Charged " + approved.amountInCents()
                    + " cents, ID " + approved.transactionId();
        }
        if (result instanceof Declined declined) {
            return "Declined: " + declined.reason();
        }
        if (result instanceof PendingVerification pending) {
            return "Pending verification: " + pending.requestId();
        }
        throw new IllegalStateException(
                "Unhandled result type: " + result
        );
    }

    public static void main(String[] args) {
        System.out.println(explain(pay(125_000, false)));
        System.out.println(explain(pay(125_000, true)));
        System.out.println(explain(pay(-100, false)));
    }
}
```

Run with JDK 17:

```shell
java -version
javac --release 17 PaymentResultDemo.java
java PaymentResultDemo
```

Sample output:

```text
Charged 125000 cents, ID TX-001
Pending verification: VERIFY-001
Declined: Invalid amount
```

Several design decisions in this example:

- `PaymentResult` is a **sealed interface** because the branches share the concept of a processing result without needing to share object state or an implementation superclass.
- `Approved`, `Declined`, and `PendingVerification` are **records**, since each result carries a simple set of data. Records automatically generate the constructor, accessors, `equals`, `hashCode`, and `toString` per the record contract.
- Each record has a **compact constructor** that validates data within its own scope. `sealed` does not replace validation at this layer.
- The `pay` method returns the common `PaymentResult` type, keeping callers decoupled from branch-selection details.
- The `explain` method uses **pattern matching for `instanceof`**, which has been standard since Java 16 and works normally in Java 17 without enabling preview features.
- IDs `TX-001` and `VERIFY-001` are simulated values only. Real systems must generate IDs according to business workflows and enforce uniqueness.

**Important caveat:** Even though the type hierarchy currently has only three branches, Java 17 **does not automatically verify that an `if`/`instanceof` chain handles every branch**. If a new branch is permitted later, you must locate and update all corresponding dispatch sites. Throwing `IllegalStateException` at the end is a defensive runtime choice, not a substitute for compile-time exhaustiveness checking.

## 5. Why not solve this problem with an enum alone?

An `enum` is a great fit when the domain only needs **a fixed set of status constants**:

```java
enum PaymentStatus {
    APPROVED,
    DECLINED,
    PENDING_VERIFICATION
}
```

However, many business domains need to return different data for each case:

| Case | Specific data required |
|---|---|
| `Approved` | Transaction ID, approved amount |
| `Declined` | Decline reason |
| `PendingVerification` | Verification request ID |

If you only use an enum, you might have to create a class containing every possible field:

```java
// Suboptimal modeling example:
record PaymentResponse(
        PaymentStatus status,
        String transactionId,
        Long amountInCents,
        String reason,
        String verificationRequestId
) {}
```

With this design, an object could carry `status = APPROVED` with `transactionId = null`, or carry both `reason` and `transactionId` even though only one makes sense. You have to manually guard against invalid combinations.

A sealed type combined with records allows **each case to have its own structure**; for example, `Approved` has no `reason` field because that field does not belong to the nature of a success branch.

Still, not every set of states calls for `sealed`:

| Need | Usually appropriate choice |
|---|---|
| Only a fixed set of status codes, little or no per-case data | `enum` |
| Finite cases carrying different payloads/traits that need polymorphism | `sealed interface`/`sealed class` and concrete branches |
| Allowing external parties to create additional valid implementations, e.g., plugin systems | Regular `interface` |
| Wanting a shared base implementation and controlled inheritance tree | `sealed class`, if inheritance fits the design |

Enums can also hold fields, methods, and per-constant behavior. Therefore, this is a **domain modeling choice**, not a rule that `sealed` is always better than `enum`.

## 6. Language rules to understand about `sealed` in Java 17

### 6.1. `sealed`, `permits`, and inheritance relationships

A sealed class or interface specifies the types permitted to inherit or implement it directly:

```java
sealed interface DocumentResult permits Saved, SaveFailed {
}

record Saved(long documentId) implements DocumentResult {
}

record SaveFailed(String reason) implements DocumentResult {
}
```

The records above are types in the same illustrative compilation unit. In a multi-file project, they must be placed in a valid package/module.

**The `permits` list describes direct subtype relationships**, not a list of objects allowed to be instantiated. In addition to appearing in `permits`, a permitted type must actually declare `extends` or `implements` on the sealed type.

If the subtypes are in the same *compilation unit* as the sealed type, Java can infer the permitted subclasses so you can omit `permits`. However, writing `permits` explicitly is often helpful in lessons and business models because readers can immediately see the set of cases.

### 6.2. Direct subtypes must explicitly state how extension continues

A class or interface that directly inherits a sealed type must have an appropriate inheritance modifier:

- **`final`:** stops the inheritance branch here. Records are implicitly `final`.
- **`sealed`:** continues restricting direct subtypes of this branch.
- **`non-sealed`:** reopens inheritance/implementation below this branch.

For example:

```java
sealed interface Command permits ExitCommand, DataCommand {
}

final class ExitCommand implements Command {
}

non-sealed interface DataCommand extends Command {
}

final class ImportCommand implements DataCommand {
}
```

`Command` still has only **two direct branches**: `ExitCommand` and `DataCommand`. But because `DataCommand` is declared `non-sealed`, other types can implement it and thereby also become `Command` **indirectly**.

Diagram:

```text
Command (sealed)
├── ExitCommand (final)         <- terminal branch
└── DataCommand (non-sealed)   <- open branch
    ├── ImportCommand (final)
    └── ...more subtypes can be added
```

If the business domain requires the number of cases across the entire tree to be finite, design the branches to preserve that constraint. `non-sealed` is an intentional tool for extension points, not something to reach for by default.

### 6.3. Package/module constraints

Java 17 restricts where permitted subtypes can reside:

- If the sealed type is in a **named module**, its direct permitted subclasses must belong to the **same named module**; they do not have to be in the same package.
- If the sealed type is in an **unnamed module** (e.g., a standard classpath application), its direct permitted subclasses must belong to the **same package**.

This affects how you organize code across multiple files. You cannot use `permits` to arbitrarily allow a library class in another module to inherit from your sealed type.

Example same-package structure suitable for a classpath application:

```text
src/main/java/com/example/payment/
├── PaymentResult.java
├── Approved.java
├── Declined.java
└── PendingVerification.java
```

Each file declares the same `package com.example.payment;` line. `PaymentResult.java` lists the other three classes in `permits`. When using a build tool with Java 17, the compiler enforces this permission relationship.

### 6.4. How to choose between `sealed class` and `sealed interface`

A **sealed interface** describes a shared contract. It feels natural when branches have independent data or behavior, especially when each branch is a record.

A **sealed class** is suitable when subtypes need to share a constructor, fields, or common behavior owned by the superclass:

```java
abstract sealed class Operation
        permits TransferOperation, RefundOperation {

    private final String operationId;

    protected Operation(String operationId) {
        this.operationId = java.util.Objects.requireNonNull(operationId);
    }

    public String operationId() {
        return operationId;
    }
}

final class TransferOperation extends Operation {
    TransferOperation(String id) {
        super(id);
    }
}

final class RefundOperation extends Operation {
    RefundOperation(String id) {
        super(id);
    }
}
```

`sealed` does not mean `abstract`. The two keywords serve different roles: `abstract` prevents direct instantiation of an abstract class and allows incomplete behavior; `sealed` restricts which types may directly inherit it. When the domain root class should not have standalone instances, combining `abstract sealed class` is a common choice.

### 6.5. `sealed` does not bypass normal encapsulation rules

Being able to declare `permits` **does not alter** `public`, package-private, or `private` access visibility. A permitted subtype must still satisfy access checks and may need to access the superclass constructor via `protected` or package-private visibility.

Nor does a sealed class mean that data in every subtype is immutable. A `final` class can still contain mutable fields. If the problem requires data immutability, you must additionally design for it using `final` fields, records, defensive copies, or other suitable techniques.

## 7. Dispatching on results in Java 17: staying version-accurate

When receiving a `PaymentResult` variable, consuming code usually needs to know which case occurred. Java 17 supports **pattern matching for `instanceof`** as a standard feature:

```java
static String toMessage(PaymentResultDemo.PaymentResult result) {
    if (result instanceof PaymentResultDemo.Approved a) {
        return "OK: " + a.transactionId();
    }
    if (result instanceof PaymentResultDemo.Declined d) {
        return "ERROR: " + d.reason();
    }
    if (result instanceof PaymentResultDemo.PendingVerification p) {
        return "ACTION_REQUIRED: " + p.requestId();
    }
    throw new IllegalStateException("Unhandled payment result");
}
```

Declaring the type in the `instanceof` condition simultaneously creates a cast variable if the condition succeeds. This reduces manual casting:

```java
if (result instanceof PaymentResultDemo.Approved) {
    PaymentResultDemo.Approved a =
            (PaymentResultDemo.Approved) result;
    // ...
}
```

The second snippet is still valid, but longer and repeats the type name.

**Important version limitation:** In Java 17, **pattern matching for switch is only in preview**, not standard syntax. Do not present `switch (result) { case Approved a -> ... }` as a standard Java 17 solution without clearly explaining preview status and special flags. Pattern matching for switch was finalized in Java 21. Likewise, record patterns belong to versions after Java 17.

This has a practical consequence: Java 17 does not yet have a standard pattern-based `switch` for the compiler to use `sealed` for exhaustiveness checking across all branches as newer versions do. When adding a new permitted subtype in Java 17, you must audit related `if`/`instanceof` chains, visitors, or routers via code search and testing.

Do not promise that `sealed` automatically makes all dispatch logic **exhaustive** in Java 17; what the compiler actually enforces here is **direct inheritance permission**.

## 8. When does restricting subtypes add value?

### 8.1. Business outcomes with different payloads

Pattern:

```text
LoginResult
├── LoggedIn(sessionToken)
├── InvalidCredentials(reason)
└── MfaRequired(challengeId)
```

The cases are defined in the login contract. Each branch holds appropriate data, while callers only receive `LoginResult`. This is a strong candidate if the development team fully controls the set of cases and the API change lifecycle.

### 8.2. Cases of an expression or syntax tree

```text
Expression
├── NumberLiteral(value)
├── Add(left, right)
└── Multiply(left, right)
```

For a parser or interpreter of a mini-language with a known set of nodes, `sealed` helps describe which node types can appear. `Add` can hold two `Expression` values and form a tree structure. If a division operator is added later, the list and related processors must be explicitly updated.

### 8.3. Scoped internal commands or events

```text
OrderDecision
├── Accepted(orderId)
├── Rejected(reason)
└── ManualReview(caseId)
```

This model fits when the application **owns the set of decisions**. Conversely, a public event bus where external plugins define new events may need an open interface and a dynamic handler registration mechanism.

### 8.4. Distinguishing valid cases from invalid data combinations

A generic record with many nullable fields can allow invalid combinations:

```text
status=DECLINED, transactionId="TX-001", reason=null
```

Separate branches help **narrow the representable states**, because `Declined` only carries data meant for a decline and can validate `reason` itself. This is a data-modeling benefit: less guesswork over field combinations in processing code.

`sealed` plus records **does not guarantee every object is valid** if constructors still accept bad data or fields hold mutable objects; remaining invariants must still be enforced explicitly.

## 9. When should you not lock a hierarchy with `sealed`?

`sealed` is a decision about **API extensibility**. If a domain is intentionally designed for independent components to contribute implementations, locking the hierarchy can get in the way.

For example, an interface:

```java
public interface NotificationChannel {
    void send(String message);
}
```

may allow plugins to supply `EmailChannel`, `SmsChannel`, `WebhookChannel`, or new channels. If a library cannot know every implementation up front, a `sealed interface` with a fixed list will restrict legitimate use cases.

Situations to weigh carefully:

- **API extension point:** a library published for third parties to implement an interface themselves.
- **Service Provider Interface (SPI):** supporting implementations loaded from other modules/plugins.
- **Truly open business domains:** new result types emerge continuously due to external system integrations.
- **Simple status codes only:** `enum` is easier to understand.
- **Objects with complex lifecycles and mutable state:** choose classes/entities according to domain and framework needs rather than forcing records.
- **Package/module constraints incompatible with current architecture:** consider centralizing definitions and hierarchy extension instead of trying to force types from other modules to be direct permitted subclasses.

Do not use `sealed` just to "write modern Java 17." Determine upfront **who owns the list of valid cases**, **whether external extension is needed**, and **when a new branch may be added**.

## 10. Adding a new case: what changes?

Suppose the payment system adds a `RefundRequired` state when a transaction requires a refund. This is a **domain contract change**, not just adding a class.

Before the change:

```java
sealed interface PaymentResult
        permits Approved, Declined, PendingVerification {
}
```

After agreeing on the business requirement, add the type:

```java
sealed interface PaymentResult
        permits Approved, Declined, PendingVerification, RefundRequired {
}

record RefundRequired(String transactionId, String reason)
        implements PaymentResult {
}
```

These two snippets **illustrate before/after declarations**; do not place both in the same file as that would duplicate the definition of `PaymentResult`.

Because `RefundRequired` is listed, the compiler allows it as a direct subtype. However, places that only handle the original three cases can still hit runtime error branches, return incorrect default messages, or skip business logic. A proper upgrade must include:

1. Determining whether the new case truly belongs to the same domain or needs its own model.
2. Adding the new branch to `permits` and declaring its specific data/invariants.
3. Identifying flows that must react to this case: services, controllers, HTTP/API response mapping, logging, persistence, telemetry.
4. Checking whether serializers/deserializers and mapping libraries in use support the new data representation.
5. Adding tests for the new branch and existing branches, especially unhandled paths.

In Java 17, using `sealed` **helps protect hierarchy extension boundaries**, while distributing handling logic for the new case remains the responsibility of design and testing.

## 11. Applying `sealed` to a Java 8/11 codebase being upgraded

When migrating a system to Java 17, there is no need to turn every interface into a sealed one. Start from places showing signs of a **closed domain**:

- Business documentation lists a finite set of result types.
- Implementations are owned by the same module or an appropriate package.
- Callers must distinguish among a few specific cases; there is no public plugin contract.
- Uncontrolled creation of new subtypes could break processing logic.

Recommended rollout steps:

**Step 1 — Define the domain contract.** List the name, meaning, required data, and creation conditions of each branch. Distinguish *business outcomes* from *workflow states* that mutate over time.

**Step 2 — Inventory existing subtypes.** Before changing an interface to `sealed`, find all `implements`/`extends` usages, including in tests and dependent modules. If subtypes exist in external modules or plugins, revisit the decision to lock the hierarchy.

**Step 3 — Decide the level of closure.** Use a sealed interface or sealed class; prefer `final`/records at leaf branches. Only use `non-sealed` when you truly want a branch to remain open.

**Step 4 — Review handling sites.** Audit `if`/`instanceof` checks, behavior dispatchers, mappers, and API boundary conversions. The system must still handle invalid states or external input explicitly.

**Step 5 — Check compatibility.** Upgrade compile and runtime configuration to Java 17 and verify dependencies/frameworks. For public libraries, changing an open interface to `sealed` is a contract change that can break compilation for client code that previously implemented the interface.

**Step 6 — Test behavior.** Test creating each valid branch, validation on bad input, response mapping, and adding a new subtype. The compiler offers partial protection, not a replacement for business tests.

### Compiler version configuration

Example from a terminal with JDK 17:

```shell
javac --release 17 PaymentResultDemo.java
java PaymentResultDemo
```

`sealed` is a standardized language feature in Java 17. If a project must **run on Java 11**, you cannot write sealed types and compile with `--release 11`; you must either update the runtime requirement or keep a Java 11-compatible model. A binary compiled for Java 17 cannot run directly on a Java 11 JVM.

## 12. Common misconceptions

| Misconception | Accurate understanding in Java 17 |
|---|---|
| "`sealed` means a class has no subclasses." | That is closer to `final`. `sealed` allows **a listed set of direct subtypes**. |
| "`permits` lists all subtypes at every level." | It lists **direct** subtypes; a `non-sealed` branch can open up further. |
| "With `sealed`, all `if` branches are checked for completeness by the compiler." | Java 17 does not automatically check exhaustiveness of `if`/`instanceof` chains. |
| "`sealed` makes data immutable." | `sealed` controls inheritance, not field mutability. |
| "Records must be used with `sealed`." | Records can be used independently; sealed classes/interfaces can also be used with regular classes. |
| "`non-sealed` can be used to declare any class." | This keyword only applies when declaring a direct subtype of a sealed type to reopen inheritance for that branch. |
| "You can directly permit a subtype from any module." | Direct permitted subtypes must be in the same named module, or the same package if in an unnamed module. |
| "`sealed` eliminates all validation and error handling." | It only guards subtype boundaries; per-branch data still needs valid contracts. |
| "Handling `sealed` in Java 17 requires switch patterns." | Java 17 has standard `instanceof` pattern matching. Switch patterns in Java 17 are still preview. |
| "Changing a library interface to `sealed` has no impact on users." | This can be a breaking change for client code that previously created its own implementations. |

## 13. Practice exercises

### Exercise 1 — Application approval domain

Design an approval outcome with three cases:

- `Accepted`: has `applicationId` and `approvedAt`.
- `Rejected`: has `reason`.
- `NeedMoreDocuments`: has a list of document names to supply.

Requirements:

1. Use `sealed interface ApplicationDecision` and three corresponding `record` types.
2. Write validation to prevent blank application IDs, blank reasons, and invalid document lists.
3. Use `List.copyOf` when storing the list of required documents so callers cannot mutate the list after creating the record.
4. Write a `toMessage(ApplicationDecision decision)` method using pattern matching for `instanceof`, running on JDK 17 without preview.
5. Try writing a fourth record not named in `permits`; observe the compiler error and explain why it occurs.

**Thought question:** If the product team allows partners to define their own custom approval outcome type, does the current sealed contract still fit? Re-analyze domain ownership before choosing a fix.

### Exercise 2 — Controlling extension per branch

Design:

```text
Message (sealed)
├── InternalMessage (final)
└── ExternalMessage (non-sealed)
    └── PartnerMessage
```

Write the necessary classes/interfaces and explain:

- Why does `PartnerMessage` not need to appear in `Message`'s `permits` list?
- If `ExternalMessage` is changed to `sealed`, what needs to change?
- If the requirement is "there must be strictly two message types in the entire system," how should it be redesigned?

### Exercise 3 — Choosing enum, sealed, or regular interface

For each problem, identify the initial choice and rationale:

| Problem | Considerations |
|---|---|
| Days of the week | Fixed constant set, virtually no per-case payload |
| Loan application processing outcome | Outcomes have distinct payloads and the system owns the set of cases |
| File export plugin | Do third parties need to add their own formats? |
| AST syntax nodes in a small compiler | Who designs the node types and is extension anticipated? |

The focus of the exercise is to clarify **domain data rules** before choosing Java keywords.

## 14. Key takeaways on purposeful use of `sealed`

A sealed hierarchy fits when the set of subtypes is **part of a controlled business contract**. It turns a limit from a promise in documentation into a rule checked by Java 17 at compile time.

Before adding `sealed`, always ask yourself:

1. Does the domain truly allow only a predefined set of cases?
2. Who owns the right to add new subtypes? Do library consumers or plugins need to extend it themselves?
3. Should leaf branches be `final`/records, or is there a clear reason to keep them `sealed` or `non-sealed`?
4. What specific data and invariants does each case carry?
5. How must type-dispatching sites be updated and tested when the domain changes?

Restricting subtypes is a **domain design decision**, and `sealed` is Java 17's tool for enforcing the inheritance constraint part of that decision.

## 15. References

- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): specification of the goals and mechanism for sealed classes/interfaces finalized in JDK 17.
- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html): official rules on class/interface declarations, inheritance, `permits`, and `non-sealed`.
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/index.html): API reference compatible with Java 17.
- [dev.java — Learn Java](https://dev.java/learn/): learning resources on object modeling, records, inheritance, and Java language features.
