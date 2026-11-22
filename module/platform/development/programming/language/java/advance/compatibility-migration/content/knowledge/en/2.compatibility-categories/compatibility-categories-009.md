# Defining the boundary between supported contracts and implementation details

During a Java upgrade, not every existing class, method, package, or configuration carries the same compatibility commitment. Some elements form contracts that consumers are entitled to rely upon; others are merely how the module implements those contracts in the current release. Defining the boundary between these two groups shows the team what must be protected during migration, what may change internally, and how to communicate when a published commitment must change.

Without defining this boundary, two failures easily occur. On one hand, developers may inadvertently break APIs relied upon by other applications. On the other hand, teams may bind themselves to every helper class, variable name, data structure, and algorithmic detail simply because they once appeared in source code. Both outcomes make migration unpredictable and costly.

## 1. What is a supported contract?

A supported contract is the set of interaction points, rules, and behaviors that a module provider publishes or confirms consumers may rely on within the stated support scope. Contracts can appear across Java APIs, configurations, protocols, data formats, plugins, build tasks, extension points, or runtime behaviors.

A contract generally answers:

- What may consumers call, implement, extend, configure, or customize?
- Which inputs are accepted and which results are guaranteed?
- How are error conditions, exceptions, lifecycles, and usage limits specified?
- Which Java, framework, Gradle, or dependency versions fall within the support window?
- When a contract changes, how are consumers notified and how long do they have to migrate?

A contract is not just a list of `public` methods. A property in `application.yml`, a Kafka topic name, a JSON schema, a documented Gradle task, or a callback ordering rule can all be contracts if consumers are guided or permitted to rely on them.

Conversely, a `public` class can still be an internal detail if the provider explicitly documents that it is outside the supported API, avoids exporting it across module boundaries, and follows a clear change policy. However, merely thinking of a class as "internal" in the developers' minds is not enough to eliminate risk when consumers already depend on it in practice.

## 2. What is an implementation detail?

An implementation detail is how a module realizes a contract without promising a stable interaction point to consumers. Developers may change these details to improve performance, reliability, maintainability, or internal structure as long as the associated contracts hold.

Common examples of implementation details:

- Local variable names, how private methods are split, and internal helper structure.
- Internal data structures such as `HashMap`, `ArrayList`, caches, or queues used behind an API.
- Sorting algorithms, retry strategies, or query optimizations while observable results continue honoring the contract.
- Concrete implementation classes standing behind a public interface.
- Internal packages, package-private classes, and resources unpublished to consumers.
- Source-set layouts, submodule structure, or internal build configuration files.

A detail truly falls outside the contract only when consumers have not been promised reliance on it and changing it breaks no promised behavior. For instance, collection iteration order can be an implementation detail if the API promises no ordering. If documentation promises ascending sorted output, that ordering has become a behavioral contract even though the specific sorting algorithm remains an implementation detail.

## 3. Distinguishing Java access visibility from support commitments

Java defines access levels `public`, `protected`, package-private, and `private`. They control language-level access, yet do not by themselves express the full support policy of a library or platform.

| Java indicator | Access meaning | Additional support check needed |
|---|---|---|
| `public` | Accessible wherever classpath/module boundaries permit | Is this a supported public API, or simply a type needing `public` for framework/internal wiring? |
| `protected` | Accessible from subclasses and same-package classes per Java rules | Are consumers permitted to subclass or override? Is the method a stable extension point? |
| Package-private | Accessible only within the same package per language rules | Are internal packages managed as private implementation? |
| `private` | Directly accessible only within the declaring class | Usually an implementation detail, though reflection, serialization, or frameworks can create unexpected coupling. |

For example, a library may declare a `public` class so a framework can instantiate it while intending consumers never to instantiate it or rely on its constructors directly. To retain freedom to change constructors, publish a supported factory or interface while explicitly documenting that the implementation class is not consumer-facing API.

The Java Platform Module System (JPMS) adds module boundaries. In `module-info.java`, `exports` exposes a package to other modules under module rules; `opens` permits reflective access as declared. These technical mechanisms usefully narrow access surfaces, yet `exports` alone does not replace documentation and compatibility policies. Exported packages still require explicit classification as supported, experimental, or internal.

Example:

```java
module com.example.customer {
    exports com.example.customer.api;

    // Implementation package is not exported to ordinary consumers.
}
```

In this example, `com.example.customer.api` is the intended access boundary. The team still needs to state which types and behaviors in that package constitute supported contracts, the minimum Java version, and how API changes are handled.

## 4. Where supported contracts can live

### 4.1. Public Java APIs

Java APIs include classes, interfaces, enums, records, annotations, constructors, methods, and fields consumers are allowed to use. Account for both calling the API and extending it.

For example, a library publishes this interface:

```java
package com.example.customer.api;

public interface CustomerLookup {
    Customer findById(String customerId);
}
```

Consumers can invoke `findById`. If the library also permits consumers to implement `CustomerLookup` themselves, this interface is also an extension point. Adding a new abstract method can then prevent consumer source from compiling or break legacy implementations against the contract.

API contract attributes to capture include:

- Parameter types, return types, generic bounds, and supported overloads.
- Handling of `null`, default values, and valid input constraints.
- Throw conditions and exception types.
- Ownership and lifecycle rules for returned objects, streams, or resources.
- Thread-safety, concurrency guarantees, and callback rules when promised.
- Interfaces consumers may implement, classes they may subclass, and methods they may override.
- Annotations, reflection metadata, or component names frameworks/consumers are instructed to use.

Not every `public` change carries equal impact. Renaming a method breaks source compatibility and can break binary compatibility. Changing `null` behavior may keep the signature intact while breaking behavioral compatibility. Evaluate each compatibility dimension separately rather than comparing method signatures alone.

### 4.2. SPIs and extension points

A Service Provider Interface (SPI) allows consumers to supply implementations for a module to use. Interfaces, abstract classes, callbacks, plugin hooks, and `ServiceLoader` integrations frequently form extension contracts.

Example:

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
```

If consumers implement `PaymentGateway`, developers must assess the impact of adding methods, altering parameter types, changing callback ordering, or changing invocation conditions. If an interface exists solely for internal implementations, avoid turning it accidentally into a public SPI via documentation, package exports, or user-facing examples.

With `ServiceLoader`, service names, provider registration locations, and initialization rules can also be contracts. When migrating Java or module systems, confirm providers remain discovered and initialized properly.

### 4.3. Configuration and environment variables

Property names, data types, defaults, units, and precedence rules across config sources can all form contracts. Example:

```yaml
customer:
  client:
    connect-timeout: 2s
    retry-count: 3
```

Consumers may already depend on `customer.client.connect-timeout` and `customer.client.retry-count`. Renaming properties, changing units from seconds to milliseconds, or altering defaults can make systems behave differently even when every Java API stays identical.

When defining configuration boundaries, state clearly:

- Name and type of each supported property.
- Required vs. optional status, defaults, and valid bounds.
- Units, formatting, and parsing rules.
- Supported configuration sources and precedence order.
- Handling of legacy properties, invalid values, and retired properties.

### 4.4. Protocols, schemas, and data

HTTP endpoints, status codes, headers, message broker topics, event names, JSON/XML schemas, file formats, serialization, and database schemas can all serve as cross-system contracts.

For example, a service returns JSON with a string `customerId` field. Renaming it to `id` can stop consumers from reading data. Likewise, changing enum values, timezones, rounding rules, or missing-value representations can create incompatibilities invisible to the Java compiler.

For persisted data, contracts also cover reading data written by earlier versions and compatibility while old and new versions coexist. Schema migrations must account for both running applications and other data-reading/writing tools.

### 4.5. Build-time contracts and developer tools

A module may publish Gradle plugins, convention plugins, tasks, DSL extensions, annotation processors, or code generators. Consumers invoke these components inside build scripts or CI pipelines.

Example:

```kotlin
plugins {
    id("com.example.java-conventions")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
```

If a plugin documents a plugin ID, `java` extension, tasks, or configuration properties, those documented names and behaviors form a build-time contract. Changing task names, extension types, task ordering, or plugin application semantics can break consumer builds before the application ever runs.

Contract scope must be defined per consumer category: plugin users, direct task callers, readers of task-generated outputs, or solely the provider's internal pipeline. Not every internal task must preserve a stable name or output.

### 4.6. Runtime behavior and operational bounds

Contracts can specify observable behavior such as processing order, idempotency, timeouts, retries, transaction boundaries, thread-safety, lifecycles, or resource cleanup. Performance and resource limits can also become commitments when published in SLAs or operational documentation.

For example, if an API guarantees FIFO processing order, swapping queue implementations while preserving FIFO is an implementation change; switching to unordered execution is a contract change. Conversely, if an API promises no ordering, consumers must not depend on the incidental order of one particular implementation.

## 5. Classifying support levels

A clear policy should distinguish at least the groups below. Label names may differ across projects, yet meaning and handling should stay consistent.

| Category | Meaning | Change rules |
|---|---|---|
| Supported | Formal contract consumers are permitted to rely on | Changes must follow compatibility policy, deprecation notices, and migration timelines. |
| Experimental / Preview | Provided for trial use without stability guarantees | Can evolve faster; must document limitations and scope explicitly. |
| Deprecated | Legacy contract still present while a replacement path exists | Announce version deprecated, replacement guidance, and planned removal timeline once set. |
| Internal / Unsupported | Internal details or surfaces unsupported for consumers | Can change per implementation needs; no compatibility promised. |

Do not rely solely on package-name conventions or comments. Reflect the policy in API documentation, usage guides, release notes, and artifact packaging. If internal annotations such as `@Internal` exist, define their exact meaning and enforce consistent application across build tools, docs, and teams.

Example annotation documenting when an API was introduced or deprecated:

```java
/** Supported API for looking up a customer. */
public interface CustomerLookup {
    Customer findById(String customerId);
}

/** @deprecated Use CustomerLookup.findById instead. */
@Deprecated(since = "4.2", forRemoval = true)
public Customer findCustomer(String customerId) {
    return customerLookup.findById(customerId);
}
```

`@Deprecated` triggers compiler and IDE warnings for consumers, yet does not establish a full deprecation policy on its own. Documentation must still name the replacement API, how long the old API remains supported, and which version may remove it.

## 6. Designing boundaries so implementations can evolve

One effective approach is having consumers depend on supported abstractions while concrete implementations stay behind them. Example:

```java
package com.example.customer.api;

public interface CustomerLookup {
    Customer findById(String customerId);
}
```

```java
package com.example.customer.internal;

final class DefaultCustomerLookup implements CustomerLookup {
    @Override
    public Customer findById(String customerId) {
        // Implementation may change across versions.
        return loadCustomerFromCacheOrDatabase(customerId);
    }

    private Customer loadCustomerFromCacheOrDatabase(String customerId) {
        // Cache/database access details remain internal.
        return null;
    }
}
```

In this design, consumers only need `CustomerLookup`. Providers can swap caching, database access, class structure, retry policies, or internal algorithms without forcing consumer edits as long as promised behavior holds.

Design principles that sharpen boundaries:

1. **Publish abstractions intentionally.** Export or publish only the types consumers need; keep concrete implementations in internal packages where appropriate.
2. **Avoid leaking internal types into public signatures.** If return or parameter types are internal classes, consumers become coupled to the implementation.
3. **Define extension points intentionally.** Permit subclassing or implementation only for types the team commits to maintaining as contracts.
4. **Specify observable behavior.** Clarify what is guaranteed, what is not guaranteed, and edge conditions.
5. **Keep internal dependencies behind abstractions.** Swapping helper libraries or implementations should not force consumers to declare unnecessary dependencies.
6. **Separate public APIs from internal config.** Never force consumers to tweak internal flags or class names just to steer an unsupported implementation detail.

With Gradle Java Library, `api` and `implementation` configurations control which dependencies appear on consumer compile classpaths. This manages dependency exposure rather than serving as sole proof that a class or package is a supported API. Combine dependency exposure with documentation and API policies.

## 7. Identifying boundaries in an existing module

In modules already in use, boundaries are not always clearly designed from the start. Combine published contracts with how consumers actually use the module.

### Step 1: Collect consumer-accessible surfaces

List exported packages, `public`/`protected` classes and members, interfaces, abstract classes, annotations, service providers, resources, configurations, build tasks/plugins, and external protocols. This forms the candidate inventory, not proof that every item is supported.

### Step 2: Review documentation and support signals

Examine API references, READMEs, integration examples, migration guides, release notes, deprecation notices, and supported version ranges. Items appearing in official usage guides are far more likely to be contracts than items mentioned only in internal debugging notes.

### Step 3: Find consumers and inspect their dependencies

Audit source code, dependency graphs, build scripts, configurations, reflection, serialization, resource lookups, and workflows. Determine whether consumers call only published APIs or also touch implementation classes, internal packages, hidden tasks, or incidental defaults.

### Step 4: Classify each interaction point

Assign Supported, Experimental, Deprecated, or Internal/Unsupported labels. For each item, record evidence, active consumers, version scopes, and decision owners. When information is incomplete, mark it undetermined rather than labeling it internal by default.

### Step 5: Map compatibility dimensions

For every contract, evaluate source, binary, behavioral, runtime, configuration/data, and build-time compatibility as relevant. One interaction point can be compatible along one dimension yet incompatible along another.

### Step 6: Validate with representative consumers

Run compile tests, binary compatibility checks, integration tests, or build tests using real consumers. Testing must reflect supported usage patterns and key consumers discovered during auditing.

## 8. Assessing changes during migration

When a change is proposed, first determine whether it touches a contract or an implementation detail. Then analyze affected compatibility dimensions and consumers.

| Change | If within implementation | If within a supported contract |
|---|---|---|
| Changing internal collection structure | Safe if observable results stay unchanged | Must preserve promised ordering, uniqueness, or collection characteristics. |
| Renaming a class | Safe for internal classes unused by consumers | Can break imports, API signatures, reflection, or serialization; needs a migration plan. |
| Changing retry algorithm | Safe if promised behaviors hold | Must evaluate retry counts, backoff, timeouts, and side effects relied upon by consumers. |
| Changing config property | Safe if property is strictly internal | Must provide aliases/deprecation or a migration step. |
| Changing a dependency | Safe if dependency is unexposed and behavior remains compatible | Must check API types, version alignment, and consumer runtimes. |
| Changing schema or event | Safe for internal-only formats with no external consumers | Requires data compatibility, versioning, and producer/consumer transition strategy. |

An implementation change can still break a contract indirectly. For example, replacing `HashMap` with another structure is an internal change; yet if that inadvertently alters return ordering promised by the API, the overall change remains a breaking change.

### 8.1. When consumers rely on internal details

In long-lived systems, consumers sometimes depend on classes or behaviors that were never promised. Do not assume all such coupling automatically becomes a permanent contract; nor should you ignore it during a migration.

Record:

- Which consumers use the detail and for what purpose.
- How widespread and critical those consumers are.
- Whether a supported replacement API exists.
- Cost of updating consumers vs. risk of changing immediately.
- Whether a transitional phase is needed.

After assessment, teams may temporarily retain behavior, introduce replacement APIs, emit warnings, publish migration guides, or agree on removal timing. If a widely used detail must be promoted to supported status, record that decision explicitly instead of letting contracts grow implicitly.

## 9. Example: changing an implementation class without breaking the API

Suppose an early library release uses a direct-query implementation:

```java
public interface CustomerLookup {
    Customer findById(String customerId);
}

final class JdbcCustomerLookup implements CustomerLookup {
    @Override
    public Customer findById(String customerId) {
        // Direct JDBC query.
        return queryDatabase(customerId);
    }
}
```

In a later release, the team wants to add caching to reduce database load:

```java
final class CachedCustomerLookup implements CustomerLookup {
    private final CustomerRepository repository;
    private final CustomerCache cache;

    @Override
    public Customer findById(String customerId) {
        Customer cached = cache.get(customerId);
        if (cached != null) {
            return cached;
        }

        Customer loaded = repository.findById(customerId);
        if (loaded != null) {
            cache.put(customerId, loaded);
        }
        return loaded;
    }
}
```

If consumers depend only on `CustomerLookup`, the team can swap `JdbcCustomerLookup` for `CachedCustomerLookup` without forcing consumer code edits. However, the team must still verify the behavioral contract: does staleness stay within acceptable bounds, does missing-customer behavior stay identical, do repository exceptions propagate as before, and do writes keep cache state consistent?

This example shows abstractions enable swapping implementations, yet do not guarantee compatibility automatically. Behavioral contracts still require verification after the change.

## 10. Testing and documenting contract boundaries

Boundaries are useful only when verifiable. Depending on the module, use evidence such as:

| Evidence | Purpose |
|---|---|
| API documentation and API diffs | Expose public/protected surface and signature changes. |
| Binary compatibility checker | Detect changes breaking linkage of pre-compiled consumer bytecode. |
| Consumer compile tests | Confirm representative consumer source still compiles against the new version. |
| Contract tests | Verify behaviors promised by the provider to consumers. |
| Integration tests | Verify configuration, protocols, data, and component interactions. |
| Build plugin tests | Verify plugin IDs, extensions, tasks, and configs used by consumer builds. |
| Schema compatibility tests | Confirm old/new producers and consumers exchange data during transitions. |
| Migration guides and release notes | Help consumers learn about changes, upgrade paths, and end-of-support timelines. |

A contract registry record can use this structure:

| Field | Content to record |
|---|---|
| Contract ID | Stable code or name for reference. |
| Surface | Java API, SPI, config, protocol, data, build plugin, or runtime behavior. |
| Support level | Supported, Experimental, Deprecated, or Internal/Unsupported. |
| Consumer | Consuming project groups or systems. |
| Compatibility scope | Supported JDKs, frameworks, dependencies, and versions. |
| Behavior | Inputs, outputs, exceptions, limits, and boundary conditions. |
| Change policy | Versioning, deprecation, transition period, and removal rules. |
| Verification | Tests or evidence validating the contract. |

Example recorded entry:

```yaml
contract:
  id: customer-lookup-api
  surface: java-api
  supportLevel: supported
  package: com.example.customer.api
  compatibility:
    java: "17+"
  behavior:
    input: customerId must be non-blank
    missingCustomer: returns null
  verification:
    - customer-lookup-contract-test
    - consumer-compile-test
```

This illustrates one way to document contracts. In real projects, follow team-agreed formats and rules, explicitly capturing `null` semantics, exceptions, and Java version behavior per the actual module.

## 11. Checklist before making migration changes

- [ ] Identified interaction points accessible to consumers.
- [ ] Distinguished Java access visibility from formal support levels.
- [ ] Audited relevant APIs, SPIs, configurations, protocols, data, and build-time surfaces.
- [ ] Classified Supported, Experimental, Deprecated, and Internal/Unsupported items using evidence.
- [ ] Identified actual consumers, including those relying on internal details.
- [ ] Determined affected source, binary, behavioral, runtime, and other compatibility dimensions.
- [ ] Selected tests matching contracts and representative consumers.
- [ ] Prepared deprecation notices or migration guides where contracts must change.
- [ ] Updated documentation and release notes to reflect current support policies.

## Conclusion

The supported contract boundary defines what consumers can rely upon and what providers must uphold under compatibility policy. Implementation details describe how a module fulfills contracts and may evolve while promised behaviors stay intact. This boundary must be established from APIs, SPIs, configs, protocols, data, build-time surfaces, documentation, and actual consumer usage. During migration, classifying each interaction point clearly and verifying via consumer tests keeps internal changes controlled while reducing the risk of breaking commitments other systems depend on.