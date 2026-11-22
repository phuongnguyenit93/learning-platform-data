# Designing Adapters and Intermediate Layers to Preserve Old Contracts

## 1. Context: Evolving APIs Without Disrupting Clients

During a **Java Advance Compatibility Migration**, the development team may need to change the JDK version, upgrade frameworks, replace libraries, or reorganize business implementation code. Those changes often affect APIs used by other modules, plugins, already-deployed applications, or partners.

Suppose the old library version publishes a method taking a traditional DTO and returning an amount as an integer. In the new architecture, the business logic uses a domain model, services with dependency injection, and a more accurate monetary type. If the old signature is changed directly, clients must update simultaneously. In practice, there may exist clients that are already compiled, packaged, or deployed separately and therefore cannot be upgraded at the same time.

An **adapter** is a component that converts between the old contract and the new model: it receives requests according to the old API, translates them into data/calls understood by the new implementation, and converts results or errors back into the form expected by old clients. An **intermediate layer** is the boundary organizing adapters, facades, mappers, and compatibility policies so that internal changes do not propagate directly to external clients.

The goals are:

- Maintain usability of the old API during the committed transition period.
- Allow the core to continue evolving on the new model, dependencies, and frameworks.
- Centralize mapping logic, error handling, and semantic differences into a clear boundary.
- Be able to test the commitments of the old API and the new API separately.
- Support gradual client migration, track usage, and remove the compatibility layer when conditions are met.

Not every API change needs an adapter. If an API is used only internally and all clients are upgraded and verified simultaneously, modifying it directly may be appropriate. An adapter is especially valuable when the old contract is already published, has multiple consumers, or has compatibility constraints during migration.

## 2. Defining the “Old Contract” Precisely

Keeping class names or method names is not enough to guarantee compatibility. A contract has multiple layers, from source code to behavior and data sent over the network.

| Contract Layer | Content to Preserve or Verify | Examples of Breaking Changes |
|---|---|---|
| Source API | Package name, public types, constructors, methods, generics, checked exceptions, and recompilability. | Removing a no-arg constructor; changing parameter types; changing a class to an interface. |
| Binary API | Binary names, method descriptors, field descriptors, static/instance, class/interface, ability for old client bytecode to link. | Old client uses invokestatic, but the new method is only an instance method. |
| Behavioral | Return values, null rules, validation, exceptions, processing order, transactions, retries, determinism, and thread-safety. | Instead of returning an old error code, the new API throws a different exception. |
| Wire/Communication API | Endpoints, HTTP methods/statuses, JSON field names, date-time formats, event names, schemas, and versions. | Renaming field totalCents to totalAmount in v1 response. |
| Operational | Timeouts, idempotency, permissions, logging, metrics, availability, and rollback capability. | Adapter automatically retries a write operation and creates an order twice. |

When building an adapter, start from a contract specification actually observed by consumers: published artifacts, API documentation, tests, and interaction logs. Current source code may already have changed compared to the version clients actually use.

### 2.1. Listing Consumers and Versions

To design the boundary properly, you need to know:

1. Which modules directly call the old Java classes or methods?
2. Which consumers are built in the same repository, and which hold old binaries?
3. Which HTTP clients, message consumers, batch jobs, or plugins are using the old contract?
4. Which consumers must stay compatible during the transition period?
5. Until which milestone is the old contract maintained, and who is responsible for migrating?

A facade may preserve the source API yet break the binary API if modifiers, class types, or constructors are changed. Similarly, an HTTP endpoint may keep its path yet break clients if status codes or payloads change. Therefore, the consumer list and commitments of each contract layer must be established before design decisions.

### 2.2. Distinguishing Commitments from Accidental Behavior

Not every detail of the old implementation is an intentional contract. However, if clients rely on an observed behavior, changing that behavior can still cause regressions.

For example, the old API returns an empty list when there is no data, whereas the new API returns null. If consumers iterate without a null check, this change can crash the application. The adapter should maintain returning an empty list for the old endpoint/method or establish a clear version change plan.

Conversely, if the old implementation had a dangerous bug that needs fixing, the team does not necessarily have to preserve that bug. Evaluate the risk, document the change, and add tests to ensure the decision is intentional.

## 3. Structure of Adapters and Intermediate Layers

A common structure:

~~~text
Old Client                 New Client
    │                          │
    ▼                          ▼
Old API / Facade         New API / Facade
    │                          │
    ▼                          │
Legacy Adapter                │
    │                          │
    ├── Legacy DTO mapper      │
    ├── Exception mapper       │
    └── Compatibility policy   │
                │              │
                ▼              ▼
          Application Service / Use Case
                       │
                       ▼
                 Domain / Core
                       │
                       ▼
           Infrastructure / External Adapter
~~~

In this model, old clients and new clients use two different entry points, yet both connect to a shared use case. The old adapter holds the necessary conversion. The core does not need to know outdated DTO names, error codes, or frameworks just to serve old clients.

### 3.1. Distinguishing Types of Intermediate Layers

| Component | Role | When Needed |
|---|---|---|
| Adapter | Converts data types, calls, or protocols from one interface to another. | Old API and new service have different signatures or representations. |
| Facade | Provides a simple, stable entry point in front of multiple internal components. | Need to keep a public API layer while changing internal structure. |
| Anti-corruption layer | Isolates terminology, data models, and assumptions of the legacy system from the new domain. | Two systems have different business models or vocabularies. |
| Mapper | Converts DTOs, enums, identifiers, money, time, or error responses. | Old and new data do not share the same structure/units. |
| Proxy / Gateway | Coordinates service access, transport, retries, or observability from a single boundary. | There are external services, remote connections, or access mechanisms to isolate. |

These concepts can work together. A facade preserves the public API, an adapter performs the call, a mapper converts DTOs, and a compatibility policy governs exception handling. There is no need to create one class for every pattern name if doing so obscures a simple flow; the responsibility boundary is what matters.

### 3.2. Dependency Direction

The compatibility layer is usually allowed to know both the old model and the new model. The new core should depend on internal abstractions, without importing legacy DTOs from old frameworks or legacy packages.

~~~text
legacy-api module
  └─ LegacyOrderFacade
       └─ LegacyOrderAdapter
            ├─ LegacyOrderMapper
            ├─ LegacyErrorMapper
            └─ OrderUseCase (abstraction)

application-core module
  ├─ OrderUseCase
  ├─ OrderCommand
  └─ OrderResult

infrastructure module
  └─ DefaultOrderUseCase / adapters
~~~

If the new core must return LegacyOrderDto or throw LegacyHttpException for all clients, the compatibility layer has been pushed backward into the domain. At that point, removing the old API later becomes much harder.

## 4. Example: Keeping the Old Java API and Moving to a New Service

Consider a library providing a pricing API. The old contract allows instantiating the object with a no-arg constructor and calling the quote method, returning a value in the smallest currency unit (e.g., cents) as an int.

Published version:

~~~java
package com.example.pricing.legacy;

public class LegacyPriceApi {
    public LegacyPriceApi() {
    }

    public int quote(String sku, int quantity)
            throws LegacyPricingException {
        return LegacyPricingEngine.quote(sku, quantity);
    }
}
~~~

During migration, the core moves to a modern use case with a long return type for a wider range of values:

~~~java
package com.example.pricing.application;

public record PriceQuery(String sku, int quantity) {
}

public record PriceQuote(long amountInMinorUnits) {
}

public interface PricingUseCase {
    PriceQuote quote(PriceQuery query)
            throws InvalidQuantityException, PricingUnavailableException;
}
~~~

The goal is to let new clients use PricingUseCase while pre-compiled old clients can still call LegacyPriceApi.quote(String, int).

### 4.1. Adapter Preserving the Public Signature

An intermediate layer can be implemented as follows:

~~~java
package com.example.pricing.legacy;

import com.example.pricing.application.PriceQuery;
import com.example.pricing.application.PriceQuote;
import com.example.pricing.application.PricingUseCase;
import com.example.pricing.application.InvalidQuantityException;
import com.example.pricing.application.PricingUnavailableException;
import java.util.Objects;

public class LegacyPriceApi {
    private final PricingUseCase delegate;

    // Keep the published public no-arg constructor.
    public LegacyPriceApi() {
        this(LegacyPricingComposition.createUseCase());
    }

    // Additional constructor to assist testing and explicit configuration.
    public LegacyPriceApi(PricingUseCase delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }

    /**
     * @deprecated New code should use PricingUseCase directly.
     */
    @Deprecated(since = "2.0")
    public int quote(String sku, int quantity)
            throws LegacyPricingException {
        try {
            PriceQuote result =
                    delegate.quote(new PriceQuery(sku, quantity));
            return Math.toIntExact(result.amountInMinorUnits());
        } catch (InvalidQuantityException e) {
            throw LegacyPricingException.invalidInput(e);
        } catch (PricingUnavailableException e) {
            throw LegacyPricingException.temporarilyUnavailable(e);
        } catch (ArithmeticException e) {
            throw LegacyPricingException.amountOutOfRange(e);
        }
    }
}
~~~

In this example, LegacyPricingComposition is the point creating the service appropriate for the application's configuration. LegacyPricingException assumes factory methods exist to convert errors according to the published contract. These are illustrative names; in a real project, use the constructors, error codes, and handling logic matching the old API.

Key decisions in the adapter:

1. Preserve the package, class name, and class kind.
2. Preserve the public no-arg constructor if old clients called it.
3. Preserve the instance method named quote, String/int parameter types, and int return type.
4. Do not change the method to static or change the class to an interface just to fit the new design.
5. Data is converted to PriceQuery at the adapter boundary.
6. The long result is converted to int using Math.toIntExact so it does not silently overflow.
7. Use case exceptions are mapped to legacy error forms that old clients can understand.
8. New clients depend directly on PricingUseCase so they do not bring LegacyPriceApi into the core.

In practice, if the old API had a different rule for handling out-of-range prices than in the example, the adapter must apply that exact rule. Math.toIntExact is a way to detect overflow; it does not by itself prove behavioral compatibility with the legacy system.

### 4.2. Why Not Keep the Same Method Name and Change It to static?

Clients compiled against an instance method typically contain an invokevirtual instruction. If the new version only provides a static method with the same name and descriptor, the JVM may throw IncompatibleClassChangeError when the call is resolved. The reverse direction can also cause errors.

You cannot simultaneously declare a static method and an instance method with the same name and parameter list in a single Java class just to satisfy both call styles. If moving from a static utility to an instance service, keep the old static facade and place the new instance API in a different type.

Similarly, when turning a public class into an interface, keep the old class and add the interface under a new binary name. Directly changing the same fully qualified name from a class to an interface can break old binary clients using new, extends, or invokevirtual.

### 4.3. Converting DTOs by Business Meaning

Mappers do not simply copy fields with similar names. Fields must be converted according to units and meaning.

| Legacy Data | New Data | What to Preserve |
|---|---|---|
| totalCents of type int | amountInMinorUnits of type long | Currency unit and rule for handling values exceeding int range. |
| createdAt as a local time string | Instant or OffsetDateTime | Timezone, offset, format, and behavior with historical data. |
| status as string OPEN/DONE | Enum with more states | Mapping for new states that old clients do not recognize. |
| null meaning not found | Optional.empty() or NotFoundException | Response form expected by old clients. |
| Integer ID | UUID or domain identifier | Stability, round-trip, and no data loss. |
| Old ordered list | Unordered collection | Ordering and stability if consumers depend on it. |

If the new model allows more states, there must be a mapping policy when old clients cannot express the new states. Avoid silently turning every unknown state into DONE or dropping important fields; decide and clearly document how to represent them or return an appropriate error.

## 5. Designing Adapters for HTTP APIs and Messages

The Java binary contract is not the only boundary. When migrating from Servlet to a new framework/web stack, changing JSON libraries, or altering the domain model, HTTP APIs and message schemas may also need compatibility layers.

### 5.1. Keeping HTTP Endpoint v1

Suppose an old client calls:

~~~http
GET /api/v1/orders/ORD-100
Accept: application/json
~~~

Published response:

~~~json
{
  "orderId": "ORD-100",
  "totalCents": 12500,
  "status": "OPEN"
}
~~~

The new application may store money as Money and richer domain states. Instead of changing the v1 response to match the new DTO, keep the v1 controller/route and use a mapper:

~~~text
GET /api/v1/orders/{id}
       │
       ▼
V1 HTTP Controller
       │
       ▼
OrderV1Adapter / DTO Mapper
       │
       ▼
OrderQueryUseCase
       │
       ▼
Domain Order
       │
       ▼
OrderV1Response preserving old schema
~~~

The v2 endpoint can use a different DTO, but v1 needs to maintain v1 field names, JSON types, HTTP codes, date formats, and error contracts per the compatibility policy.

For example, an adapter can convert domain NotFound into HTTP 404 with the v1 JSON error code; validation errors into HTTP 400 with the old body; infrastructure errors into HTTP 503 if consistent with the contract. Do not return stack traces or new Java exceptions to v1 clients.

### 5.2. Message and Event Schemas

For Kafka, AMQP, or other queues, an adapter can preserve old events while the internal domain changes:

~~~text
New Domain Event
     │
     ▼
Event Compatibility Mapper
     ├── Event v1 sent to old consumers
     └── Event v2 sent to new consumers
~~~

You must define versioning policies, topic/queue names, schema registries, partition keys, event ordering, retries, and idempotency. If the same business event is published under two versions, avoid letting a consumer subscribe to both and execute the business action twice.

A migration plan might prioritize upgrading consumers first so they can read the new schema, and only then changing producers. In another system, publishing v1/v2 in parallel is suitable. The decision depends on communication contracts and control over consumers; do not assume dual-publishing is always safe.

### 5.3. Java Serialization Needs Separate Consideration

If clients exchange objects via Java serialization, keeping class names and public methods is still not enough. Changing fields, class hierarchy, or serialVersionUID can make stored data or old payloads unreadable.

A JSON DTO adapter does not automatically fix Java serialization issues. When the system still has old binary data, you need a plan to read/migrate data, verify serialVersionUID and actual class versions, and run deserialization tests with data generated by the old version.

## 6. Translating Errors and Preserving Semantics

Errors are part of the contract. The adapter should translate new exceptions or results into the committed legacy form.

For example:

| Result from New Core | Old Contract May Require | Adapter Rule |
|---|---|---|
| Validation failure | LegacyValidationException or error code INVALID_INPUT | Convert to the exact error type and message/code format. |
| Not found | null, Optional, or a specific exception | Preserve published behavior rather than changing arbitrarily. |
| Service unavailable | LegacyServiceException with retryable status | Preserve transient/permanent classification. |
| Conflict | Error code ALREADY_EXISTS | Avoid turning into a generic error that makes clients retry wrongly. |
| Timeout | Timeout exception or HTTP 504 per API | Preserve retry meaning and avoid losing context. |
| Successful result | Old DTO or response | Preserve units, ordering, default values, and format. |

Do not catch all RuntimeExceptions and return a default success result. That approach can hide business errors, break monitoring, and make clients think a write operation succeeded.

On the other hand, letting new exceptions pass straight through the adapter is also unsafe when clients only handle legacy error types. Translate expected errors at the boundary while keeping the cause and appropriate diagnostic details in internal logs.

### 6.1. Checked Exceptions, null, and Empty

In Java, the list of checked exceptions is part of the source API experience, even though it is not in the method descriptor in the same way as parameters/return values. Keeping the method signature expected by clients helps older modules recompile more smoothly.

Clearly define:

- Is null valid as input?
- Does null, Optional.empty(), an empty list, or an exception represent “no data”?
- Which exceptions are retryable and which are permanent validation errors?
- Are error codes and HTTP statuses stable?
- Do consumers parse error messages by string matching?

If clients rely on message text, changing the text can also cause real failures, even though that is not a recommended client design. Where possible, define stable error codes and evolve so consumers do not depend on free-form messages.

### 6.2. Transactions and Atomicity

Suppose the old API created an order and deducted inventory in a single transaction. An adapter that merely calls two new use cases consecutively without maintaining the transaction boundary can cause one step to succeed and the other to fail, leaving corrupted data.

Therefore, before splitting services, determine:

- Which use case owns the transaction boundary?
- Is an atomic commit needed, or must saga/compensation be used?
- Which exceptions trigger rollback?
- Can a retry execute a write operation twice?
- Is the idempotency key preserved through the adapter?

The adapter should forward calls and compatibility policies; business correctness and transactions must have a clear owner in the application service or appropriate orchestration layer.

## 7. Avoiding Turning the Intermediate Layer into a “Second System”

An adapter easily bloats if the team places new business logic in it as quick fixes for individual scenarios.

Signs to watch for:

- The adapter contains many pricing, authorization, or business state rules in place of the domain.
- The same rule is implemented in both the v1 adapter and the v2 controller.
- The adapter knows too many persistence details or queries the database directly.
- New services import legacy classes to avoid writing mappers.
- There are multiple round-trips of legacy DTO → new DTO → legacy DTO for no reason.
- v1 API names exist inside the domain, making removing v1 difficult.

Keep the adapter thin in the sense of clear responsibilities: parse/validate according to the old contract, map data, call the use case, and map results and errors. “Thin” does not mean few lines of code at all costs; complex mapping is reasonable when preserving the old contract genuinely requires it.

### 7.1. Dependency Creation Points

If the old API previously provided a no-arg constructor, the adapter may have to keep it. However, do not use a freely mutable global variable to supply dependencies if doing so makes tests and runtime unpredictable.

One way to organize this is:

1. Keep the old constructor to preserve the binary/source API.
2. Have the old constructor delegate to a composition root with clear service-creation rules.
3. Add a constructor accepting dependencies for tests and new clients to configure explicitly.
4. Have a lifecycle and resource closing mechanism if the service creates threads, connections, or schedulers.

If the new service depends on a transaction manager or DI container, the composition root must be defined according to how the application operates. Do not create a new application context for every legacy call, because cost and lifecycle may differ completely from the old implementation.

## 8. Verifying the Compatibility Layer

Testing an adapter requires multiple perspectives because it is possible to preserve behavior for new sources while breaking old binary clients.

### 8.1. API Shape and Binary Compatibility

For a published Java library:

1. Keep the old library version artifact.
2. Compile a client fixture based on the old version.
3. Keep the client class files intact; do not recompile.
4. Run the old fixture with the new library containing the adapter.
5. Exercise constructors, methods, fields, and hierarchies used by the client.
6. Record linkage errors, results, and behavior.

Example running the binary fixture on Linux/macOS:

~~~bash
java -cp "client-old.jar:library-new.jar" com.example.compat.ClientFixture
~~~

On Windows:

~~~powershell
java -cp "client-old.jar;library-new.jar" com.example.compat.ClientFixture
~~~

If you need to compare APIs, you can use javap to view method descriptors, modifiers, and class/interface kinds:

~~~bash
javap -classpath library-old.jar -p -s com.example.pricing.legacy.LegacyPriceApi
javap -classpath library-new.jar -p -s com.example.pricing.legacy.LegacyPriceApi
~~~

Tools like japicmp or Revapi can automatically report API changes between two artifacts. However, metadata comparison results and old client tests should complement each other. Binary tests confirm actual execution call paths, while diff tools help detect a broader API surface.

### 8.2. Contract Tests for Old Behavior

The adapter should be tested with a concrete contract test suite:

| Test Group | Scenarios to Test |
|---|---|
| Happy path | Valid legacy data is mapped accurately and returns results of the right type/unit. |
| Boundary values | Zero, negative, maximum, overflow, empty strings, large quantities. |
| Null/empty | Distinguish null, empty collections, Optional, and objects missing fields. |
| Errors | Each new error type is converted to the right legacy exception/error code/status. |
| Date/time | Offset, timezone, daylight saving, historical data, and legacy formats. |
| Concurrency | Thread-safety, concurrent calls, and shared state. |
| Write semantics | Idempotency, retries, transactions, and rollback on partial failure. |
| Compatibility | Re-run fixtures compiled against the old version. |

When published v1 response data is available, golden fixtures can be used to compare JSON or serialized payloads. For JSON, test the semantic contract (fields, types, values, error shapes) and only compare field order if ordering is actually part of the contract.

### 8.3. Testing with Real Frameworks and Environments

If migration changes Spring Framework, Spring Boot, Jakarta namespace, serializers, or the HTTP stack, test the adapter through the exact deployed entry point.

For example, a unit test calling LegacyOrderAdapter directly does not yet prove the v1 endpoint works: controller mapping, validation, security filters, content negotiation, or exception handlers may have changed. You need integration tests sending real requests through the web stack and verifying responses against the old contract.

If the library is packaged in an executable JAR or container, verify the actual runtime artifact and dependency graph. A source-accurate adapter may still fail if deployment loads an older JAR different from the freshly built artifact.

## 9. Tracking Legacy API Usage

The adapter is a convenient place to know how many clients are still using the old contract. Each call can record metrics or structured logs with sensitive data restricted.

Useful indicators:

- Number of requests or invocations by API version and operation.
- Error rate, timeouts, and unsupported mapping outcomes.
- Latency of the adapter and of the underlying use case.
- Consumer group or client version if reliable identifiers exist.
- Remaining traffic ratio on v1 API versus v2.
- Number of open compatibility exceptions and resolution deadlines.

Do not log full request bodies or tokens just to count legacy clients. Prefer aggregate metrics, permitted IDs, and labels with appropriate cardinality. Do not generate business side effects from instrumentation.

### 9.1. Observing Without Changing Behavior

Adding metrics, tracing, or logging must not cause the old API to change timeouts, exceptions, or latency excessively. If the monitoring system is temporarily unavailable, do not let non-essential instrumentation cause business requests to fail, unless there is a specific operational requirement.

For adapters with mappings that cannot be represented in the old schema, have dedicated metrics/alerts so the team knows to upgrade clients or adjust policies before these cases become widespread in production.

## 10. Phased Migration Roadmap

A commonly used API evolution approach:

~~~text
Phase A: Baseline the old contract
      │
      ▼
Phase B: Place adapter/facade in front of the new core
      │
      ▼
Phase C: Run old clients and new clients in parallel
      │
      ▼
Phase D: Migrate consumers, measure usage, and reduce dependencies
      │
      ▼
Phase E: Confirm no remaining consumers need the old contract
      │
      ▼
Phase F: Remove the legacy API in an appropriate release version
~~~

### Phase A — Lock the Baseline

Save old artifacts/versions, public contracts, request/response fixtures, binary fixtures, and the consumer list. Capture a baseline of results, errors, latency, and critical behaviors. Without a baseline, it is very difficult to prove the adapter preserves the existing contract.

### Phase B — Add the Adapter

Add a facade or adapter at the right boundary so the new core has a clean API. Keep old classes/methods/endpoints per commitments. Create mappers, exception policies, and dedicated tests for the compatibility boundary. In this phase, old clients are not yet forced to change source code.

### Phase C — Deploy in Parallel

Let upgraded consumers use the new API. Unupgraded consumers continue through the old API. If the operation has side effects, do not call both implementations simultaneously for the same request just to compare results; use safe observation approaches or a separate test environment.

### Phase D — Migrate and Measure

Publish the replacement API and migration guide, assign owners for each consumer, and handle cases where mappings cannot represent full data. Use appropriate metrics/traces to verify v1 traffic decreases.

### Phase E — Finalize Conditions to Remove the Adapter

Do not rely only on “not seeing requests for a few hours”. Check consumers running on monthly/quarterly schedules, batch jobs, rarely used plugins, and clients outside observation scope. Record the observation window, end-of-support milestone, and process for handling unupgraded consumers.

### Phase F — Release Controlled Breaking Changes

Only remove the old API when aligned with versioning policies and support commitments. If breaking binary compatibility is required, clearly communicate the new major version/artifact, migration guide, and client recompilation requirements. SemVer helps communicate change magnitude but does not make old binaries automatically compatible.

## 11. Managing Versions, Deprecation, and Migration Documentation

The old API can be marked Deprecated to communicate migration direction:

~~~java
/**
 * @deprecated Migrate to PricingUseCase.
 */
@Deprecated(since = "2.0")
public int quote(String sku, int quantity)
        throws LegacyPricingException {
    // Delegate to new use case.
}
~~~

The forRemoval attribute should only be used when there is a clear removal plan. It is a signal to users and tooling that the API is intended to be removed in a later version; it is not a mechanism that automatically redirects calls to the new API.

A migration guide should specify:

- The old API, new API, and corresponding mappings.
- How to instantiate or inject dependencies instead of the old mechanism.
- Differences in DTOs, date/time types, currency units, error codes, and transactions.
- How to migrate synchronous consumers and background consumers.
- The version deprecation starts and the expected end-of-support version.
- Binary compatibility conditions and rebuild requirements if there are breaking changes.
- Minimal tests/examples for consumers to verify migration.

If the old package must be kept for binary contract reasons, do not automatically move it to a new package without providing corresponding bridge types. The fully qualified name is part of the identity used by client bytecode.

## 12. Rollback and Strategy When an Adapter Fails

Adding an intermediate layer can introduce new risks: wrong data mapping, altered exceptions, increased latency, or broken transactions. The rollout plan needs to anticipate how to roll back.

Questions to answer before deployment:

1. Can we roll back to the old artifact if the adapter fails?
2. Is data written by the new core still readable by the old version?
3. How might emitted v2 events affect v1 consumers?
4. By what mechanism should the v2 route be turned off or traffic shifted back to v1?
5. Are there irreversible database migrations or state changes?
6. Which metrics and alarms indicate the adapter is producing results deviating from the contract?

Code rollback is not synonymous with data rollback. If the new model writes data in a format the old implementation cannot read, design a schema transition phase or separate rollback strategy. API-level adapters only solve the interface; they do not automatically guarantee durable data compatibility.

## 13. Common Design Mistakes

| Mistake | Consequence | Appropriate Approach |
|---|---|---|
| Changing static to instance directly on an old public method. | Old binary clients may encounter IncompatibleClassChangeError. | Keep the old static facade; add an instance service under a new type. |
| Changing a public class to an interface with the same fully qualified name. | Clients using new, extends, or invokevirtual may fail to link. | Keep the old class; introduce a new interface and have the old class implement it. |
| Keeping the method name while changing return/parameter types. | Method descriptor changes; NoSuchMethodError may occur. | Keep the old method and add overloads/new APIs with a different name when needed. |
| Mapping long to int via direct cast. | Silent integer overflow and incorrect values returned. | Check bounds and decide on a compatible error-reporting mechanism. |
| Turning null into an exception or turning an exception into null. | Clients handle errors wrongly or hit NullPointerException. | Preserve legacy policies per method. |
| Passing legacy DTOs straight into the new domain. | The new core becomes coupled backward to the old API version. | Map at the adapter boundary. |
| Copying all business logic into the v1 adapter. | Two sources of logic easily diverge, hard to remove the adapter. | Share a common application service/use case. |
| Ignoring retries/idempotency when moving to HTTP or messaging. | May process duplicates, lose transactions, or drift data. | Design business-appropriate policies at the proper layer. |
| Testing only new sources without running pre-compiled old clients. | Fails to detect binary incompatibility. | Keep binary fixtures and test at runtime with the new library. |
| Deleting the adapter as soon as current traffic hits 0. | Batch jobs/infrequently running consumers may still use the old API. | Monitor usage cycles and verify the consumer list. |

## 14. Design Process for a Specific API Change

When receiving a request to replace an implementation during migration, follow this sequence:

1. **Identify the boundary:** Public Java API, HTTP endpoint, event, or all three? Who uses it?
2. **Record the baseline:** save signatures, binary artifacts, sample requests/responses, error behavior, and tests.
3. **List differences:** DTOs, fields, errors, lifecycle, transactions, static/instance, class/interface, serializers, and framework versions.
4. **Choose the intermediate form:** facade preserving old entry points, adapter/mapping to new use case, error mapping, and transport versioning if needed.
5. **Design dependency direction:** the new core does not need to know legacy DTOs or exceptions.
6. **Define policies for unrepresentable cases:** overflow, unknown enums, missing timezones, new operations with no v1 translation.
7. **Implement the adapter:** keep public contracts that must be preserved, centralize mapping and delegation.
8. **Run verification:** old binary clients, old source clients, contract tests, and integration tests through the real runtime.
9. **Measure and deploy:** observe usage, mapping errors, latency, and rollback conditions.
10. **Plan removal:** deprecation, migration guide, consumer owners, timelines, and end-of-support conditions.

The output of the design phase should include boundary diagrams, a list of preserved contracts, mapping tables, error-handling rules, versioning decisions, verification results, and rollback/removal conditions. This forms the basis for reviewers to understand precisely what the adapter protects and which differences have been accepted.

## 15. Conclusion

Adapters and intermediate layers help APIs evolve without forcing every consumer to change at the same time. They preserve the old contract at the published boundary, translate calls and data to the new core, and isolate legacy exceptions, DTOs, protocols, and assumptions.

The value of the solution depends on the accuracy of the preserved contract: binary names, constructors, static/instance, class/interface, method descriptors, response schemas, error behavior, transactions, and operational commitments. A good adapter has stable entry points, clearly owned mapping logic, tests with old binaries and data, usage observability, and a versioned removal plan. As a result, JDK/framework/dependency migrations can proceed incrementally while unupgraded clients continue operating under the published contract.
