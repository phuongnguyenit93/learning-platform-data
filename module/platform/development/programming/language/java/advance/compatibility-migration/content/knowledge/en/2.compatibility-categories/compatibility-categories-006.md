# Backward and Forward Compatibility from Provider and Consumer Perspectives

When a Java library, service, or protocol is upgraded, both sides are rarely deployed at the exact same moment. The provider may already run the new version while customer applications still run the old version; or an application updates first while a backend service cannot yet upgrade. Therefore, the crucial question is not merely whether the new version runs on its own, but whether **both sides at different versions continue communicating under a valid contract**.

Backward compatibility and forward compatibility describe how versions coordinate along one direction of time. Both terms must specify whether the viewpoint is the provider's or the consumer's. The exact same pair of versions can be backward compatible from one side's viewpoint and forward compatible from the other's.

## 1. Defining Provider, Consumer, and Versions

In this lesson, **the provider** is the component publishing an API, library, service, or data format. **The consumer** is the component calling the API, depending on the library, sending requests, or reading data produced by the provider.

Examples:

- A Java library exposes public classes and methods; a Spring Boot application depending on that library is the consumer.
- A REST service exposes endpoints; a mobile app or another service calling those endpoints is the consumer.
- A program writing data to a file is the data provider; a program reading that file in a later run is the data consumer.
- One module publishes an interface; another module implements that interface. In this case, clearly distinguish who defines the contract and who is responsible for implementing it.

Notation:

- **P1**: version 1 of the provider.
- **P2**: version 2 of the provider.
- **C1**: version 1 of the consumer.
- **C2**: version 2 of the consumer.

P1/C1 is the old pair. P2/C2 is the new pair. When upgraded independently, the system can exhibit two mixed combinations: P2 running with C1, or P1 running with C2. Those two combinations are the focus when evaluating compatibility.

The contract between both sides includes more than endpoint names or method signatures. It can also cover data types, validation rules, default values, processing order, error codes, exceptions, serialization formats, authentication requirements, size limits, and business semantics. A change is safe only when it preserves the commitments relied upon by the other side.

## 2. Compatibility from the Provider Perspective

Providers frequently release new versions without being able to force every consumer to upgrade immediately. Hence, the provider-side question is: can the new version continue serving consumers built against the old contract?

### 2.1. Provider Backward Compatibility

**P2 is backward compatible with C1** when the new provider still supports valid usage patterns performed by old consumers.

For example, library version 1 has the method:

~~~java
public class PriceCalculator {
    public BigDecimal total(BigDecimal price) {
        return price;
    }
}
~~~

An application compiled against `total(BigDecimal)`. If version 2 removes that method and keeps only `total(BigDecimal, Currency)`, the old application may throw `NoSuchMethodError` when running against the new JAR. Library version 2 compiling cleanly on its own does not prove that old application binaries remain compatible.

A less disruptive upgrade keeps the old method and delegates to the new implementation:

~~~java
public class PriceCalculator {
    public BigDecimal total(BigDecimal price) {
        return total(price, Currency.getInstance("VND"));
    }

    public BigDecimal total(BigDecimal price, Currency currency) {
        // Calculate the total using the specified currency.
        return price;
    }
}
~~~

This example is safe only if that default rule genuinely matches the API's prior semantics. Preserving the signature while altering the calculation, currency unit, or side effects still breaks the contract at the behavioral level.

In HTTP APIs, P2 may add an optional response field. Old consumers usually keep working if they ignore unknown fields and existing fields keep their original meaning. Conversely, if P2 renames an old field, changes its type, or requires consumers to send a new field, that change can break C1.

### 2.2. Provider Forward Compatibility

**P1 is forward compatible with C2** when the old provider can still serve the new consumer within the scope of features the old provider supports.

This usually requires an extensible protocol. For instance, P1 may ignore unknown optional request fields, or return metadata letting C2 detect an unsupported capability. If C2 sends an entirely new operation P1 lacks, neither side can conjure that capability out of thin air; the consumer must have a fallback or report the feature as unavailable.

Forward compatibility on the provider side therefore does not mean the old provider must execute every future version's features. It means the old provider handles understandable interactions safely while clearly signaling limits on newer features.

## 3. Compatibility from the Consumer Perspective

Consumers also have independent release lifecycles. A new application may need to connect to an older service because environments do not upgrade simultaneously; an old application may stay running long after the service has upgraded.

### 3.1. Consumer Backward Compatibility

**C2 is backward compatible with P1** when the new consumer can still use the old provider.

For example, application C2 releases with a newer library or client version, while some environments still run service P1. C2 must keep using endpoints and data fields already present in P1. If C2 unconditionally calls an endpoint introduced only in P2 during startup, it will fail against old environments.

A consumer can support this by:

- Requiring only baseline capabilities already provided by P1.
- Probing capabilities or API versions before invoking new features.
- Handling missing optional fields with meaningful default values.
- Having a fallback path when the provider does not yet support a new operation.

In Java applications, this also appears during dependency upgrades. If a new application calls a method added only in a newer library version, it cannot run against the old JAR. To support both versions, the consumer must restrict itself to the shared API or check capabilities before using extensions.

### 3.2. Consumer Forward Compatibility

**C1 is forward compatible with P2** when the old consumer can still handle the new provider.

A common example is P2 adding a `status` field to a JSON response. C1 can keep working if its parser tolerates unknown fields and its business logic does not rely on the new field. If C1 rejects every undeclared field or assumes responses always contain a fixed field set, the addition can break C1 even though P2 kept every old field intact.

Consumers must also prepare for new data values. For example, P2 introduces a new order status. If C1 maps every status into a closed Java enum and throws on unknown values, C1 loses forward compatibility. You can design an `UNKNOWN` branch or preserve the raw value for safe handling, depending on business rules.

Ignoring unknown data must be applied deliberately. Consumers should never ignore fields carrying security, authorization, monetary amounts, or transaction state semantics if ignoring them causes wrong decisions. Forward compatibility must go hand in hand with safety rules and explicit error handling.

## 4. Putting Both Perspectives Side by Side

Two mixed version combinations show why the perspective must be stated explicitly when using these terms:

| Running Combination | Provider Perspective | Consumer Perspective | Question to Answer |
|---|---|---|---|
| P2 + C1 | Provider is backward compatible | Consumer is forward compatible | Does the new provider still serve the old consumer? |
| P1 + C2 | Provider is forward compatible | Consumer is backward compatible | Can the new consumer still use the old provider? |

This can be remembered with a diagram:

~~~text
P2 (new provider)  <---->  C1 (old consumer)
  backward compatible        forward compatible

P1 (old provider)  <---->  C2 (new consumer)
  forward compatible         backward compatible
~~~

Terminology in engineering docs sometimes shifts based on whichever component is considered the one upgrading. Therefore, in migration docs, reviews, or integration contracts, state the concrete version pair—such as `P2 + C1`—instead of writing only "backward compatible." That removes most ambiguity.

## 5. Compatibility Layers to Verify in Java

A change may be compatible at one layer yet incompatible at another. Successful compilation is only one form of evidence; it does not prove old applications will link, run, and produce right results.

### 5.1. Source Compatibility

Can old source code recompile against the new library or JDK version without edits?

Changes that break source compilation include:

- Removing or renaming public classes, methods, constructors, or fields.
- Changing parameter types or return types so existing call sites become invalid.
- Adding an overload that makes previously unambiguous calls ambiguous.
- Changing checked exceptions in ways forcing callers to handle more exceptions.
- Adding abstract methods to interfaces not yet implemented by existing classes.

An overload change can break source compatibility even when previously compiled bytecode still links against the old method. Thus, verify both recompiling consumers and running old binaries.

### 5.2. Binary Compatibility

Can previously compiled bytecode link and run against the new library version without recompiling?

Bytecode stores references to classes, methods, and fields by name and descriptor. When the runtime cannot find what the bytecode expects, the program can fail during linking or when executing that code path. Typical examples include `NoSuchMethodError` when a method was removed or its descriptor changed; `NoSuchFieldError` when a referenced field no longer matches; and `IncompatibleClassChangeError` when type structure or usage changed incompatibly.

Another example involves interfaces: adding an abstract method leaves older implementations without a corresponding method body. Calling that method on an old instance can trigger `AbstractMethodError`. `default` methods reduce binary compatibility risks in some cases, yet interface conflicts and default behavior semantics still require review.

### 5.3. Behavioral Compatibility

The API keeps the same signatures and the application still runs, yet do observable results or side effects change?

Examples:

- A method previously accepted `null`, whereas the new version throws `NullPointerException`.
- A query previously returned a sorted list, whereas the new version returns unspecified order.
- An operation previously synchronous switched to asynchronous processing.
- A business failure previously returned error code A, whereas the new version returns error code B.
- A default setting, rounding rule, or tax calculation changed.

This is why compatibility cannot be concluded merely by comparing API signatures or compiling code. Actual behavior must be cross-checked against contracts and consumer expectations.

### 5.4. Data and Protocol Compatibility

Can consumers read data created by old or new versions? Does the provider understand requests from consumers at another version?

For JSON, critical cases include newly added fields, omitted legacy fields, changed field types, new enum values, and discontinued fields. For Java serialization or long-lived stored data, inspect class identifiers, data layouts, conversion rules, and readability of data written by prior versions.

Never assume adding fields is always harmless. A new field can break consumers using strict parsers; an old field might be treated as required by new consumers; or both sides may interpret units or semantics of the same value differently.

### 5.5. Build and Runtime Platform Compatibility

In Java migration, JDK versions, bytecode levels, Gradle/Maven, plugins, and dependencies are also part of compatibility. A library may be API-compatible while requiring a newer JDK than the consumer's runtime environment. Conversely, an application may compile on a newer JDK yet fail on an older runtime due to unsupported bytecode class versions or platform APIs.

Therefore, record minimum Java versions separately for compilation, runtime execution, and supported build tools. Never collapse these conditions into a vague claim like "supports Java 21" without stating which stage is meant.

## 6. Designing Providers to Support Multiple Consumer Generations

Providers reduce migration risk by treating their public contract as a versioned product lifecycle:

1. **Prefer optional extensions.** Adding new endpoints or methods is usually far easier to coordinate than renaming or deleting old ones. New fields should have clear defaults when old consumers omit or ignore them.
2. **Retain legacy APIs during transitions.** Mark old methods `@Deprecated`, offer replacements, and delegate old methods to the new implementation when semantics match.
3. **Never alter semantics silently.** Keeping a signature while altering units, validation rules, ordering, or side effects still breaks the contract.
4. **Publish capabilities and limits.** Consumers need to know which features, versions, or formats a provider supports—via capability endpoints, metadata, version headers, or system-appropriate negotiation.
5. **Define deprecation and removal policies.** State what will be removed, its replacement, the transition window, and end-of-support timelines.
6. **Test against representative consumers.** Run contract or integration tests against supported consumer versions, including precompiled binaries when required.

Not every change can stay compatible indefinitely. When breaking changes are necessary, providers should establish crisp version boundaries, publish roadmaps, and let both contracts coexist during the transition window.

## 7. Designing Consumers to Tolerate Controlled Change

Consumers cannot control when every provider upgrades. Hence, a consumer should explicitly define its lowest and highest supported versions and handle differences deliberately:

1. **Depend only on published contracts.** Avoid internal APIs or uncommitted implementation details.
2. **Handle extensible data.** Ignore irrelevant fields, retain unknown values, or map new enums to safe fallbacks. For money, permissions, security, or transaction states, define explicit business handling rules.
3. **Do not assume new features always exist.** Check capabilities or handle "unsupported" responses before invoking new capabilities.
4. **Use meaningful defaults.** When an old provider omits a new field, fill defaults only when business-valid.
5. **Avoid depending on unstable details.** Never depend on JSON key ordering, unguaranteed element ordering, free-form error text, or incidental sorting.
6. **Test against multiple provider versions.** New consumers must be tested against both the oldest supported provider and the newest provider in the matrix.

"Ignore unknown things" is not a universal rule for every field. If a new field indicates extra authentication rules, legal terms, or disallowed states, ignoring it causes severe bugs. Consumers must separate ignorable extensions from mandatory semantics.

## 8. Building a Migration Compatibility Matrix

Before deploying, list every pair of provider and consumer versions that can coexist. A small matrix turns vague assumptions into testable cases.

| Provider | Consumer | Verification Goal |
|---|---|---|
| P1 | C1 | Baseline: verify the current pair works before migration |
| P2 | C1 | New provider serves old consumer |
| P1 | C2 | New consumer uses old provider |
| P2 | C2 | New version pair works completely |

Not every system must support all four combinations. Your matrix should reflect real deployment topology, rollback windows, supported versions, and integration criticality. If deployments are always atomic and no old consumers remain, some pairs may be out of scope; document that decision explicitly.

A typical migration workflow has three phases:

**Expand:** The provider adds new APIs or fields while keeping the old contract intact. Consumers do not need to adopt extensions immediately.

**Migrate:** Consumers upgrade to use the new contract. During this phase, test P2/C1 and P1/C2 whenever either combination can arise during rollout or rollback.

**Contract:** Remove old APIs or stop emitting legacy data only after confirming no supported consumers rely on them. Removal must follow published deprecation policies and retirement schedules.

When testing, combine source compatibility checks, binary compatibility checks, contract tests, integration tests, and behavioral tests. For Java libraries, run applications precompiled against the prior version over the new dependency to catch linkage errors. For REST APIs, save real request/response fixtures from existing consumers and replay them against the new provider. For persisted data, verify reading records written by earlier versions and test planned rollback scenarios.

## 9. Common Misleading Assumptions

**"Adding a method is always compatible."** Adding methods to classes rarely affects existing callers, yet adding an abstract method to an interface can break implementations. Adding overloads can also make existing source calls ambiguous upon recompilation.

**"`@Deprecated` means it is safe to delete."** The annotation only signals API status. It does not prove consumers have migrated. A transition period and real usage evidence are required before removal.

**"If it compiles, it is compatible."** Compilation checks only part of source compatibility. Old binaries can fail to link; running programs can return wrong outputs due to behavioral changes.

**"Adding a JSON field cannot break clients."** Clients enforcing strict schemas, parsers rejecting unknown fields, or logic expecting fixed structures can fail. Know how real consumers parse data.

**"Semantic Versioning guarantees compatibility by itself."** Versioning conventions communicate change intent, yet remain helpful only when maintainers classify changes accurately and test contracts. Version numbers never replace engineering proof.

**"New providers and new consumers always deploy together."** In reality, multiple environments, independent release teams, un-updated mobile apps, or multi-year persisted records exist. Compatibility matrices must reflect real deployment lifecycles.

## 10. Checklist When Evaluating a Change

When reviewing an API change or planning an upgrade, answer in sequence:

- Who is the provider, who is the consumer, and what contract governs them?
- Which version pairs can coexist: P2/C1, P1/C2, or both?
- Does the change impact source, binary, behavior, data/protocol, or runtime platform?
- Does the old consumer keep working with the new provider?
- Does the new consumer handle working with the old provider?
- How are unsupported features detected and reported?
- Are tests covering real versions, historical data, and rollback scenarios?

The core point is always anchoring compatibility terminology to **the viewpoint under consideration and the specific version pair**. P2/C1 is backward compatible from the provider's perspective yet forward compatible from the consumer's perspective. P1/C2 is the reverse. Distinguishing these two perspectives and verifying the proper compatibility layers puts library, JDK, and Java service upgrades on solid ground while reducing the risk of disrupting components still relying on older contracts.
