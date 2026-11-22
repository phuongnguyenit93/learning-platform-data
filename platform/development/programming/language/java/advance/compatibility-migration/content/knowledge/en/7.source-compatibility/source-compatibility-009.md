# Enums, Sealed Types, and Switch Exhaustiveness When APIs Expand

In Java, enums and sealed types help model known sets of values or subtypes. Starting in Java 21, pattern matching for switch became a standard feature, letting the compiler check whether switch expressions over enums or sealed hierarchies cover all cases.

However, “exhaustive” at compile time does not mean the API's value set will never change. A library can add an enum constant or add a permitted subtype after consuming applications were compiled. When that happens, recompiled source code and old binaries can react differently. Without a clear policy for handling new values, a seemingly small API change can cause runtime failures or skipped business logic.

This lesson explains how enums, sealed hierarchies, and switch exhaustiveness interact; distinguishes source compatibility, binary compatibility, and behavioral compatibility; and presents ways to design fallbacks and tests when APIs expand during Java migrations.

## 1. Why Does Switch Exhaustiveness Matter During Migration?

A switch is exhaustive when the compiler determines every value that can enter the switch is handled by a branch. This is especially useful for switch expressions, because an expression must produce a result along every path.

For example, a payment system has three statuses:

```java
enum PaymentStatus {
    PENDING,
    AUTHORIZED,
    SETTLED
}

static String describe(PaymentStatus status) {
    return switch (status) {
        case PENDING -> "Waiting for payment";
        case AUTHORIZED -> "Payment authorized";
        case SETTLED -> "Payment completed";
    };
}
```

The compiler accepts this switch expression because at compile time, the enum has exactly three constants and all three are listed. If a later library version adds a REVERSED constant, the situation changes:

- When recompiling the application against the new library version, the switch expression lacks the REVERSED branch and the compiler reports incomplete coverage.
- When running an old binary compiled against the old enum while loading the new enum, if the new value enters the switch expression, the compiler-generated fallback branch can throw IncompatibleClassChangeError.
- If using a switch statement without default, the new value may match no branch and processing gets skipped.

This is an important difference between compile-time checking and real runtime data. APIs can upgrade independently of consuming applications; therefore, migration must consider both points in time.

## 2. Enums: Constant Sets That Can Expand Across Library Versions

### 2.1. An Enum Is Closed Within One Release, Yet the API Can Still Evolve

An enum represents a set of constants declared in the type:

```java
public enum DeliveryState {
    CREATED,
    PACKED,
    SHIPPED,
    DELIVERED
}
```

Within a specific library version, this constant set is finite and enumerable by the compiler. However, if the enum is public API, the provider can add constants in a later version:

```java
public enum DeliveryState {
    CREATED,
    PACKED,
    SHIPPED,
    DELIVERED,
    RETURNED
}
```

Previously compiled consumer code can still link against the new enum at the JVM level. Adding constants is generally considered binary-compatible under Java compatibility rules, yet that does not guarantee consumer business logic handles the new value.

Some APIs may return new constants from servers, databases, plugins, or dependencies unknown to older applications. Therefore, treat public enums as evolvable contracts unless the provider commits to keeping the constant set permanently fixed.

### 2.2. Switch Expressions and Switch Statements Behave Differently

**Switch expressions** must be exhaustive. Without default, the compiler verifies constants are covered:

```java
static int calculateFee(DeliveryState state) {
    return switch (state) {
        case CREATED -> 0;
        case PACKED -> 5;
        case SHIPPED -> 10;
        case DELIVERED -> 0;
    };
}
```

When recompiling against the enum with RETURNED added, the compiler requires handling the new constant. This is a helpful signal: the API change forces developers to review logic.

A compiled exhaustive switch expression can contain a synthetic fallback branch to guard the case where a binary was compiled separately against a different enum version. If at runtime it encounters a new constant absent from the set known at compile time, that fallback branch can throw IncompatibleClassChangeError. This is an intentional failure to avoid silently miscalculating.

**Switch statements** are not required to list every enum constant. Example:

```java
static void updateInventory(DeliveryState state) {
    switch (state) {
        case CREATED -> reserveStock();
        case PACKED -> prepareShipment();
        case SHIPPED -> markInTransit();
        case DELIVERED -> closeOrder();
    }
}
```

If runtime receives RETURNED, no branch executes. The code can still complete normally, yet return processing does not occur. This is a hard-to-spot bug because no exception is necessarily thrown.

If a switch statement represents mandatory processing, add a default branch with intentional behavior, such as logging and rejecting execution:

```java
static void processDeliveryState(DeliveryState state) {
    switch (state) {
        case CREATED -> reserveStock();
        case PACKED -> prepareShipment();
        case SHIPPED -> markInTransit();
        case DELIVERED -> closeOrder();
        default -> throw new IllegalArgumentException(
            "Unsupported delivery state: " + state
        );
    }
}
```

This helps old binaries fail clearly when encountering new states. If business logic permits ignoring or forwarding unknown values, the default branch can record telemetry and apply an appropriate fallback policy. Avoid leaving an empty default branch if skipping can corrupt data.

### 2.3. Choosing Between Exhaustive Switch and Default Fallback

There are two distinct design goals:

- **To force consumers to review every new constant:** use a switch expression listing each constant without adding default. When consumers recompile against the new API, the compiler will demand updates.
- **To allow old binaries to safely handle unknown constants:** use a default branch with a clear policy, or use an input conversion layer representing unknown values.

Neither choice fits every system. If a new state affects money, access permissions, data, or workflows, failing explicitly is usually safer than guessing. If the new value is only a minor display label, a fallback can keep user experience stable.

What to avoid is simultaneously using default to ignore unknown values while assuming the compiler will warn when the enum expands. Once default is present, the compiler stops requiring consumers to list new constants.

### 2.4. Null Is a Separate Case

Default does not equate to handling null. When switching on a reference type, a null selector usually causes NullPointerException unless a null branch is supported.

In pattern switch since Java 21, null can be handled explicitly:

```java
static String display(DeliveryState state) {
    return switch (state) {
        case null -> "No state supplied";
        case CREATED -> "Created";
        case PACKED -> "Packed";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        default -> "Other state: " + state.name();
    };
}
```

If the API disallows null, validate inputs before the switch and maintain a non-null invariant. What matters is an explicit null policy, not relying on the default branch.

### 2.5. Enum Constants and Stored Data

Expanding an enum can affect persisted or externally transmitted data:

- ordinal() is the constant's position in the declaration. Inserting a constant in the middle shifts the ordinal of subsequent constants.
- EnumType.ORDINAL in JPA stores the sequence number; when enum order changes, old data can be interpreted as a different state.
- EnumType.STRING stores the constant name, which is more stable than ordinal yet still impacted if a constant is renamed.
- Java serialization of enums uses constant names. Renaming can make old serialized data unreadable.
- JSON or message brokers typically serialize enums by name, yet exact behavior depends on library and configuration.

Do not use ordinal as a business code, database code, or wire protocol value. If enum values form part of a long-lived contract, attach an explicit stable code:

```java
public enum PaymentStatus {
    PENDING("P"),
    AUTHORIZED("A"),
    SETTLED("S");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

When reading data, map by code and have a policy for unknown codes. For example, an API receiving a status from a new service can keep the raw value for logging or forwarding instead of forcing every string into the current enum.

```java
import java.util.Optional;

static Optional<PaymentStatus> findByCode(String code) {
    for (PaymentStatus status : PaymentStatus.values()) {
        if (status.code().equals(code)) {
            return Optional.of(status);
        }
    }
    return Optional.empty();
}
```

Optional.empty() lets callers recognize unsupported values. If the system must round-trip unknown data, store the raw code separately instead of dropping it.

## 3. Sealed Types: Explicitly Declared Subtype Sets

### 3.1. How Sealed Hierarchies Constrain Subtypes

A sealed class or sealed interface declares which types are permitted to extend or implement it directly. Each direct subtype must have one of the modifiers final, sealed, or non-sealed.

Example:

```java
public sealed interface PaymentCommand
        permits CapturePayment, CancelPayment {
}

public record CapturePayment(String transactionId)
        implements PaymentCommand {
}

public record CancelPayment(String transactionId)
        implements PaymentCommand {
}
```

In this example, PaymentCommand has only two direct permitted subtypes. The compiler can use that list to verify whether a switch pattern covers all branches.

```java
static String route(PaymentCommand command) {
    return switch (command) {
        case CapturePayment capture ->
            "capture:" + capture.transactionId();
        case CancelPayment cancel ->
            "cancel:" + cancel.transactionId();
    };
}
```

This switch expression is exhaustive because every permitted subtype has a branch. When the API expands, both compiler and runtime behavior must be re-examined.

### 3.2. Adding a Permitted Subtype Is a Contract Change

Suppose the next version adds a refund command:

```java
public sealed interface PaymentCommand
        permits CapturePayment, CancelPayment, RefundPayment {
}

public record RefundPayment(String transactionId, long amount)
        implements PaymentCommand {
}
```

Consumers recompiling against the new API will see the old switch expression is no longer exhaustive and must add a branch for RefundPayment or an intentional fallback.

Consumer binaries compiled against the old subtype list can still load alongside the new library. However, if a RefundPayment instance enters the old switch expression, the compiler-generated fallback branch for exhaustive switches can throw IncompatibleClassChangeError. Therefore, adding a permitted subtype can cause substantial behavioral changes even without rebuilding consumer code.

With a switch statement lacking default, the new subtype may match no branch. This carries the same risk of skipped business logic as an enum switch statement.

### 3.3. sealed, final, and non-sealed Affect Exhaustiveness

The three subtype states determine which subtypes can appear:

- final: terminates the branch; no new subtypes can extend further.
- sealed: the subtype publishes its own set of permitted subtypes.
- non-sealed: reopens the branch, allowing other types to extend or implement it.

For example, an API wants to let external plugins extend one branch:

```java
public sealed interface PluginCommand
        permits BuiltInCommand, ExternalCommand {
}

public record BuiltInCommand(String name)
        implements PluginCommand {
}

public non-sealed interface ExternalCommand
        extends PluginCommand {
}
```

When switching on PluginCommand, a branch for ExternalCommand covers all external implementations:

```java
static String handle(PluginCommand command) {
    return switch (command) {
        case BuiltInCommand builtIn ->
            "Built-in: " + builtIn.name();
        case ExternalCommand external ->
            "External command";
    };
}
```

If a new plugin implements ExternalCommand, consumers can still process it through this branch without modifying the sealed parent. This is a deliberate extension-point design.

If all branches are sealed or final, the subtype set can be fully checked at compile time. If a non-sealed branch exists, handle that branch itself as an open group instead of trying to list every implementation that might appear in the future.

### 3.4. Pattern Guards Do Not Necessarily Cover an Entire Subtype

A guarded pattern only matches instances satisfying the condition. Example:

```java
static String classify(PaymentCommand command) {
    return switch (command) {
        case CapturePayment capture
                when capture.transactionId().startsWith("VIP-") ->
            "Priority capture";
        case CapturePayment capture ->
            "Regular capture";
        case CancelPayment cancel ->
            "Cancellation";
    };
}
```

The first branch handles only captures whose transaction ID starts with VIP-. The second branch handles remaining captures. If the second branch is omitted, the switch may no longer be exhaustive because the guard does not cover the entire CapturePayment type.

When reviewing pattern switches, check both guards and branch ordering. The compiler catches patterns dominated by a more general pattern. For example, placing a PaymentCommand command branch before a CapturePayment capture branch makes the latter unreachable. This is usually a helpful compile error, yet also a sign to redesign pattern ordering or specificity.

### 3.5. Null and Sealed Pattern Switches

Default handles values not matching other patterns, yet should not be assumed to handle null. If null is a valid input, add an explicit branch:

```java
static String routeNullable(PaymentCommand command) {
    return switch (command) {
        case null -> "No command";
        case CapturePayment capture -> "Capture";
        case CancelPayment cancel -> "Cancel";
        case RefundPayment refund -> "Refund";
    };
}
```

If the API promises non-null, enforce that at system boundaries via validation or constructors. Do not scatter null policies across individual switches.

## 4. Source Compatibility, Binary Compatibility, and Behavioral Compatibility

When an API changes, assess three concepts separately:

| Compatibility type | Question | Example with enums/sealed types |
|---|---|---|
| Source compatibility | Does consumer source code recompile against the new API? | Switch expression without default lacks the new enum constant or permitted subtype, so compilation fails |
| Binary compatibility | Can old consumer binaries link with the new API? | Adding an enum constant usually does not break linkage; hierarchy and referenced-type changes must be evaluated separately |
| Behavioral compatibility | At runtime, does the program handle new data accurately? | Old switch expression may throw ICCE; switch statement may skip the new branch |

An API can be binary-compatible yet behaviorally incompatible. Therefore, a “binary compatible” label in release notes is not enough to conclude consumers need no changes.

### 4.1. Adding Enum Constants

Adding a constant to an enum usually does not prevent old binaries from linking against the enum type. However:

- Previously compiled exhaustive switch expressions may throw ICCE upon encountering the new constant.
- Switch statements without default may skip the new constant.
- Logic relying on values().length, ordinal(), or declaration order may change.
- Parsers or serializers may reject unknown constant names.

Upon recompilation, switch expressions without default force consumers to inspect the new constant. This is a useful form of source-compatibility check.

### 4.2. Adding Permitted Subtypes

With a sealed API, adding a type to the permits list expands the set of instances that can appear at runtime. Recompiling consumers will need to update exhaustive switch expressions. Old binaries may hit the synthetic fallback branch and throw ICCE when an instance of the new subtype is passed in.

This is especially critical when the API is a public library or SPI implemented independently by many applications. A library vendor may ship a new subtype in a minor release, yet old consumers may not handle it. Clearly define versioning policies and communicate changes to API users.

### 4.3. Renaming or Removing Enum Constants

Renaming a constant is not equivalent to adding a constant. Source referencing the old name will fail to compile. Old binaries may fail when accessing a constant field that no longer exists. Java serialization or JSON stored by name can also become unreadable.

If a display name must change, separate the label from the constant name. If a wire/communication code must change, use explicit stable codes and support aliases or migration mappings for a transition period.

### 4.4. Modifying Sealed Hierarchies

Changes such as removing a permitted subtype, switching a subtype from final to non-sealed, or turning a branch sealed can affect both consumers and extension code. An external class implementing a non-sealed branch may become invalid if that branch is modified. Consumers using exhaustive switches also need to revisit assumptions about the type set.

When publishing a sealed hierarchy as part of a public API, treat the permits list and open/closed status of each branch as part of the contract. Do not change it without considering source consumers, binary consumers, and external plugins.

## 5. Designing APIs for Safe Expansion

### 5.1. When Should You Use Enums?

Enums fit when the value set is controlled by the same module or when a business domain has a relatively stable set of choices. Examples:

- Internal workflow states.
- Operation kinds managed by a single service.
- Configuration modes with a closed set of values.
- Classification outcomes produced by the application itself.

If an enum is public API and the provider may add constants, documentation must clearly explain how consumers should handle new values. For states with business impact, consider fail-fast or explicit unknown representations.

### 5.2. When Should You Use Sealed Types?

Sealed hierarchies fit when modeling a set of variants with differing structures, such as commands, events, expressions, or processing results. They allow the compiler to check switch branches against the published subtype set.

Choose subtype modifiers matching extension intent:

- Use final for variants that should not be extended.
- Use sealed for branches with a controlled set of child variants.
- Use non-sealed when intentionally permitting external extensions.

A hierarchy designed to be completely closed gives strong exhaustiveness, yet adding branches later must be treated as a contract change for consumers.

### 5.3. Creating Meaningful Fallbacks

Fallbacks should reflect business semantics, not merely silence compiler errors.

Several options:

| Policy | When appropriate | Example behavior |
|---|---|---|
| Fail fast | New value could corrupt money, permissions, states, or workflows | Throw exception containing unsupported constant/type info |
| Unknown bucket | New value can be displayed or logged without being understood yet | Display “Unsupported status” and log raw value |
| Preserve raw value | Gateways or proxies need to forward unknown data | Keep raw code or payload intact for round-trip |
| Ignore with telemetry | Secondary events without affecting correctness | Ignore while incrementing metrics and logging under control |
| Delegate extension | Plugin APIs must allow third-party extensions | Route via non-sealed interface or registry |

Do not pick ignore by default for critical operations. If the system receives a new payment status, ignoring it can leave orders stuck or corrupt reconciliation. Fallbacks need owners, logs/metrics, and reprocessing rules once the application upgrades.

### 5.4. Modeling Open Values with Wrappers

If data comes from external systems that can add new values, a plain enum may be too closed. You can preserve both the received value and the parse result:

```java
import java.util.Optional;

enum KnownStatus {
    PENDING,
    PAID,
    CANCELLED
}

record StatusValue(String raw, Optional<KnownStatus> known) {
    static StatusValue parse(String raw) {
        Optional<KnownStatus> known;
        try {
            known = Optional.of(KnownStatus.valueOf(raw));
        } catch (IllegalArgumentException ex) {
            known = Optional.empty();
        }
        return new StatusValue(raw, known);
    }
}
```

This example preserves the original string when unrecognized. In a real system, define null handling, code normalization, and how to distinguish invalid values from valid new values not yet supported by the application.

This wrapper can be used at API boundaries, message consumers, or database adapters. Core internal business logic can accept only validated states, while the integration layer retains and records raw values.

## 6. Auditing Switches When APIs Expand

### 6.1. Finding All Switches Involving Enums and Sealed Types

When upgrading a library version, search for switches over public API types that may change. You can start with keyword searches:

```shell
rg -n "switch\s*\(" src
rg -n "case\s+[A-Z][A-Z0-9_]*\s*->" src
rg -n "sealed\s+(interface|class)|permits\s+" src
```

The commands above are starting points; adjust paths and patterns to your project layout. Some switches live in generated sources or other modules, so check generated code as well if compiled into artifacts.

Build an inventory with columns:

| Location | Selector type | Switch form | Has default? | Risk when API expands |
|---|---|---|---|---|
| OrderService.java | OrderStatus | Expression | No | Recompile reports missing constant; old binary may throw ICCE |
| EventRouter.java | DomainEvent sealed | Pattern expression | No | New subtype may make old binary throw ICCE |
| AuditService.java | AuditLevel | Statement | No | New value may go unhandled |
| LabelFormatter.java | DisplayState | Expression | Yes | Fallback may handle new value, yet semantics must be checked |

The table above only illustrates how to record an inventory and does not represent actual project files.

### 6.2. Distinguishing Switch Expressions and Statements

Do not merely count switches. Classify them:

- Switch expressions return values and must be exhaustive.
- Switch statements perform side effects and may not list every value.
- Pattern switches use type patterns and guards; coverage depends on pattern types.
- Switches with default already have a fallback yet can mask API expansion.
- Switches with null branches need separate inspection.

For switch statements executing business actions, consider converting to switch expressions if results can be represented as values. The compiler will help surface unhandled cases when APIs change.

Example:

```java
static String actionFor(OrderStatus status) {
    return switch (status) {
        case CREATED -> "reserve";
        case PAID -> "fulfill";
        case SHIPPED -> "track";
        case CANCELLED -> "release";
    };
}
```

If a new status is added, the compile error forces developers to decide behavior. This is an advantage of switch expressions in tightly controlled domains.

### 6.3. Checking Guards and Pattern Dominance

For sealed hierarchies, confirm:

- Every permitted subtype is covered.
- Non-sealed branches are handled as open groups.
- Guards are not mistaken for full-subtype coverage.
- General patterns are not placed before specific patterns causing later branches to be dominated.
- Null has an explicit policy.
- Default has business meaning and observability.

If a switch grows complex with many guards and nested patterns, consider extracting logic into helper methods for testability. There is no need to turn every switch into a complex pattern structure just to use new features.

## 7. Testing Compatibility When APIs Bump Versions

Routine tests against a single dependency version are insufficient to catch all issues from API expansion. Test both old consumers and recompiled consumers.

### 7.1. Producer and Consumer Version Matrix

| Consumer | Runtime API | Purpose |
|---|---|---|
| Consumer built with old API | Old API | Current baseline |
| Consumer built with old API | New API with new enum constant/subtype | Detect runtime fallback, ICCE, or skipped branches |
| Consumer rebuilt with new API | New API | Detect compile errors from switch expressions missing branches |
| Consumer built with new API | Old API | Detect consumers referencing constants or subtypes present only in new API |

Not every combination is a supported configuration. Still, this matrix separates source, linkage, and behavioral errors.

### 7.2. Testing Expanded Enums

A useful test scenario:

1. Create API version 1 with an enum containing only current constants.
2. Compile a consumer with an exhaustive switch expression and a switch statement without default.
3. Create API version 2 adding a new enum constant.
4. Run the old consumer binary against API 2.
5. Pass the new constant into each switch and verify behavior.
6. Recompile the consumer against API 2 and record compile errors to handle.
7. Add or verify fallbacks if consumers require forward compatibility.

The goal is not making every old consumer automatically understand new values. The goal is ensuring behavior when encountering new values has been decided and tested.

### 7.3. Testing Expanded Sealed Hierarchies

Follow a similar scenario:

1. API 1 publishes a sealed interface with two permitted subtypes.
2. Consumer builds a switch expression covering both subtypes.
3. API 2 adds a third permitted subtype.
4. Run the old consumer binary with an instance of the new subtype.
5. Recompile the consumer against API 2 to check compiler demanding the new branch.
6. Verify fallbacks, non-sealed extension points, or appropriate versioning policies.

If the API has external plugins, add tests for implementations of non-sealed branches. Ensure consumer code does not assume only built-in implementations exist.

### 7.4. Testing Serialization and Protocols

Beyond switches, inspect data paths:

- JSON containing new enum constants.
- Message brokers sending codes unknown to consumers.
- Databases holding new status values.
- Java serialization reading data written by a newer version.
- REST clients and servers deployed at mismatched versions.
- Caches or event replays containing values from a later release.

If the protocol can expand, inspect how serialization libraries handle unknown enum values. Some libraries have options to map to a default constant; others throw errors. Do not rely on library defaults without tests confirming behavior.

## 8. Versioning Strategies for APIs With Enums and Sealed Types

### 8.1. Treat Adding Constants/Subtypes as Changes Requiring Notice

If an API is used by many independent consumers, adding enum constants or permitted subtypes may require consumers to update logic. Clearly document in release notes:

- What the new constant or subtype is.
- When the new value can appear.
- What behavior old consumers will experience upon receiving that value.
- Whether a fallback is recommended.
- Whether a major version bump is needed per product compatibility policy.

Do not merely say “added a new status” if it can make old switch expressions throw ICCE or switch statements skip business logic.

### 8.2. Use Major Versions When Contracts Truly Change

Not every enum addition requires a major version bump under all versioning policies. The decision depends on API commitments and unknown-value handling.

However, if consumers are expected to understand every constant/subtype and lack a safe fallback, expanding the value set can break source or behavioral compatibility. Consider a major version or an advance-announced transition period.

### 8.3. Provide Extension Points Instead of Repeatedly Editing Sealed Parents

If an API needs to let plugins or third parties extend it, design a clear non-sealed branch. Then consumers can handle built-in variants specifically and group all external implementations under one shared branch.

If the domain needs values from external systems that evolve independently, consider string codes or wrappers with raw values instead of closed enums. Sealed hierarchies suit API-controlled variant sets; open value models suit protocols where new values can appear.

### 8.4. Do Not Use default to Hide Business Discrepancies

A default branch can keep old binaries running, yet can also mask unhandled states. Clarify:

- Is continuing processing permitted?
- Must requests fail or events be rejected?
- Must raw values be stored for later replay?
- Are metrics needed to detect unknown-value frequency?
- Who will update consumers when new values appear?

A good fallback has safe behavior, logs/metrics, and a recovery path. An empty fallback merely turns an explicit failure into silent, hard-to-trace data corruption.

## 9. Safe API Upgrade Rollout Scenarios

### Case A: Internal Enum Within One Application

If the enum is used within one module and all consumers build together:

1. Add the new constant.
2. Compile all modules.
3. Fix switch expressions per compiler errors.
4. Inspect switch statements with side effects.
5. Run serialization and database mapping tests.
6. Release the application artifact atomically.

Because all consumers build together, the compiler helps locate many spots requiring updates.

### Case B: Enum in a Shared Library

If the library releases independently:

1. Check which versions consumers are using.
2. Decide whether the new constant can appear immediately after upgrading the provider.
3. If old consumers must coexist with the new provider, add fallbacks with clear policies or preserve contracts not emitting new values to old consumers.
4. Update release notes and the compatibility matrix.
5. Test old binaries with the new provider.

This is the scenario most prone to runtime errors because provider and consumers release independently.

### Case C: Sealed Hierarchy for a Plugin API

If the sealed hierarchy is part of an SPI:

1. Identify which branches are library-owned and which are for extensions.
2. Keep non-sealed branches if third parties must add implementations.
3. Avoid adding permitted subtypes that feed new instances into old consumers' exhaustive switches lacking fallbacks.
4. If adding a new subtype, update versioning and test old consumers.
5. Verify plugin loaders do not reject valid implementations.

### Case D: Expanding Protocols or Event Schemas

If an enum represents values from REST, Kafka, databases, or message schemas:

1. Define stable codes independent of enum names.
2. Allow parsers to recognize unknown values.
3. Retain raw values if forwarding or replay is needed.
4. Convert to known enums only after validation.
5. Test old consumers when producers emit new values.

Do not rely on ordinals or Java constant names as protocol contracts if systems must evolve independently.

## 10. Checklist for Reviewing Enums and Sealed Switches During Migration

### API and Domain Model

- [ ] Listed public enums that may expand.
- [ ] Listed sealed classes/interfaces and all permitted subtypes.
- [ ] Identified which branches are final, sealed, or non-sealed.
- [ ] Identified which APIs are committed closed vs expandable.
- [ ] Clearly documented policy when receiving unknown constants or subtypes.

### Switches and Business Logic

- [ ] Located switch expressions and switch statements over enums.
- [ ] Located pattern switches over sealed hierarchies.
- [ ] Classified switches with default vs without default.
- [ ] Checked guarded patterns and pattern dominance.
- [ ] Defined null policy.
- [ ] Replaced empty fallbacks with intentional behavior on critical branches.

### Data and Integration

- [ ] No enum ordinals used as storage or protocol codes.
- [ ] Checked JPA mappings, JSON, message brokers, and serialization.
- [ ] Defined stable codes if enum names can change.
- [ ] Defined how unknown raw values are retained or rejected.
- [ ] Tested version-mismatched producers/consumers.

### Testing and Release

- [ ] Compiled consumers against the new API version.
- [ ] Ran old consumer binaries against the new API in test environments.
- [ ] Tested switch expressions encountering new enum constants.
- [ ] Tested switch statements encountering new enum constants or subtypes.
- [ ] Tested expanded sealed hierarchies and non-sealed branches.
- [ ] Release notes clearly state impact on source, binary, and behavioral compatibility.
- [ ] Rollback plan and handling for data written with new values exist.

## Conclusion

Enums and sealed types let the compiler check switch exhaustiveness, yet exhaustiveness relies solely on the value set and subtypes known to the compiler at compile time. When an API expands, recompiling consumers can get helpful compile errors; old binaries can throw IncompatibleClassChangeError in switch expressions or skip new branches in switch statements.

During migration and API releases, distinguish source compatibility, binary compatibility, and behavioral compatibility. Choose enums for controlled value sets, sealed hierarchies for intentional variant sets, and design non-sealed branches or raw-value wrappers when extensibility is required. Finally, test both old and new consumers against the new provider while explicitly specifying fallbacks, logging, and versioning. Doing so prevents API expansion from silently corrupting workflows in running applications.
