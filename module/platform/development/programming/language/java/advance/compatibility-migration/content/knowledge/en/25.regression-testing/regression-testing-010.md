# Comparing Results and Detecting Allowed Differences

During a Java upgrade, a project can compile successfully, pass all existing unit tests, and still alter behavior observable by users or integrated systems. Two deployments may both return HTTP 200 yet differ in monetary amounts, data ordering, error codes, timestamps, JSON format, number of published events, or TLS connectivity. Conversely, two JSON responses may differ in property order or trace IDs yet still be equivalent according to the contract.

What matters is not making every result before and after migration character-for-character identical. What matters is **fully detecting meaningful differences, distinguishing regressions from valid changes, and preventing ignore rules from masking real bugs**.

This lesson belongs to **Java Advance Compatibility Migration**, chapter **Regression Testing**, on the topic **Comparing Results and Detecting Allowed Differences**. The content focuses on comparing behavior across JDK versions, building test oracles, handling non-deterministic data, designing semantic comparisons, managing approved exceptions, and verifying results in real Java environments.

## 1. Difference Does Not Equal Regression

Suppose the old version returns:

~~~json
{
  "orderId": "O-42",
  "total": "240000.00",
  "currency": "VND",
  "items": [
    {"sku": "BOOK", "quantity": 2}
  ],
  "traceId": "a1",
  "processedAt": "2026-11-12T03:00:00Z"
}
~~~

The new version returns:

~~~json
{
  "processedAt": "2026-11-12T03:00:01Z",
  "items": [
    {"quantity": 2, "sku": "BOOK"}
  ],
  "currency": "VND",
  "traceId": "b2",
  "total": "240000.00",
  "orderId": "O-42"
}
~~~

The two JSON strings are not identical. However:

- Property order in a JSON object generally carries no ordering semantics.
- traceId may be operational metadata whose specific value is not guaranteed.
- processedAt may vary because the two runs do not use the same clock.
- total, currency, orderId, and quantity are business data that must be strictly verified.
- Element order in a JSON array is usually meaningful and must not be arbitrarily ignored.

If a comparator only compares strings, it can produce false positives. If the comparator strips every field whose name contains id or time, it can create dangerous false negatives.

**Principle:** classify differences by contract and impact level, not by whether plus/minus signs appear in a diff.

## 2. Four Categories of Comparison Results

| Category | Meaning | Handling |
|---|---|---|
| Exact match | Results are identical under the required representation | Pass |
| Semantic equivalent | Representation differs, but semantics and contract remain unchanged | Pass with specific rule |
| Approved behavior change | Semantics changed intentionally, reviewed and approved | Conditional pass/versioning |
| Unexpected difference | Difference is not allowed or violates an invariant | Fail and investigate |
| Inconclusive | Insufficient data or test harness failure | Do not treat as pass |

Adding an inconclusive status is necessary. If events or database snapshots cannot be collected, there is no basis to conclude that the two application versions are equivalent.

### 2.1. “Allowed Difference” Must Have a Scope

A valid rule might be:

~~~text
Only allow the /traceId value to differ.
Both values must be non-empty strings in the valid format.
Other locations in the payload must still be equivalent.
The traceId linkage within each execution must still be consistent.
~~~

An overly broad rule like “ignore all identifiers” can skip orderId, customerId, or tenantId, leading to lost evidence of data errors.

### 2.2. Intentional Changes Are Not Automatically Backward-Compatible

For example, a new JDK rejects weak TLS under security policy. This may be the right security change yet still prevent an old consumer from connecting. It requires a migration decision, communication, and a compatibility handling plan—not merely adding a “ignore handshake errors” rule.

## 3. Test Oracle: Where Does the Reference Come From?

A **test oracle** is the basis for concluding whether an output is correct.

The main approaches:

1. **Expected values:** results computed from business requirements or an independent specification.
2. **Differential testing:** running the same input on the old and new versions and comparing outputs.
3. **Invariant/property testing:** checking rules that must always hold even when concrete values vary.
4. **Consumer contract testing:** checking what callers depend on.
5. **Historical replay:** ensuring old data and old flows can still be processed.

Do not treat the old version as absolute truth. It may have a bug that the new version accidentally fixes. When V1 and V2 differ, analyze which behavior aligns with the business domain and published contract.

### 3.1. Example Independent of the Old Baseline

~~~text
Input:
  quantity = 3
  unitPrice = 120.00
  discount = 10.00

Business invariant:
  subtotal = 360.00
  total = 350.00
  total >= 0
  currency unchanged
~~~

If both V1 and V2 return total=349.00, the differential test may pass while the independent invariant still fails. Combining both oracle types helps avoid legitimizing historical bugs.

## 4. Inventorying All Observable Outputs

A request can leave many effects beyond the HTTP response:

| Boundary | Data to compare |
|---|---|
| REST/gRPC | Status, headers, body, errors |
| Serialization | JSON, XML, Avro, Protobuf schema/value |
| Database | Rows, constraints, transaction outcome |
| Messaging | Topic, key, payload, event order |
| Batch | Input/output files, record count, report |
| Computation | Decimal precision, rounding, overflow |
| Security | Authentication, authorization, signature, TLS |
| Time | Timestamps, expiration, scheduling |
| Concurrency | Duplicates, races, consistency |
| Operations | Startup, shutdown, GC, resource usage |
| Performance | Latency distribution, throughput, error rate |

For example, two versions both return:

~~~json
{"status":"COMPLETED"}
~~~

yet V1 publishes one OrderCompleted event while V2 publishes two events. This can be a serious regression even though the body is identical.

**Result comparison must include contract-required side effects.**

## 5. Preparing an Equivalent Comparison Environment

Two executions are only meaningful when key factors are controlled or explicitly recorded:

- Commit/build of the old and new versions.
- JDK vendor, version, and update.
- Container image digest, OS, CPU architecture.
- Java locale, default charset, timezone.
- Database snapshot, schema, and seed.
- Feature flags and application configuration.
- Network stubs or external services.
- Clock, randomness, and ID generator.
- Heap, GC, CPU/memory limits.
- Thread pool and concurrency level.
- Cache warm-up, connection pools.
- Observability agents.
- Dependency versions.

### 5.1. Baseline Template

~~~text
OLD:
  appVersion:
  sourceCommit:
  javaVersion:
  javaVendor:
  imageDigest:

NEW:
  appVersion:
  sourceCommit:
  javaVersion:
  javaVendor:
  imageDigest:

SHARED:
  fixtureVersion:
  databaseSeed:
  timezone:
  locale:
  featureFlags:
  upstreamStubs:
  requestSequence:
  testConcurrency:
  measurementWindow:
~~~

If upgrading Java while also upgrading the database driver, framework, or serializer, record all changes. A difference cannot automatically be attributed to the JDK.

### 5.2. Differential Testing Model

~~~text
Controlled fixture/input
           |
       +---+---+
       |       |
       v       v
    Old JDK  New JDK
       |       |
       v       v
    Output A Output B
       |       |
       +---+---+
           |
           v
   Contract validation
           |
           v
    Semantic comparison
           |
           v
   Allowed-difference policy
           |
           v
   Classification and report
~~~

If using recorded production traffic, protect PII/secrets and isolate side effects to avoid writing data, sending emails, or charging payments twice.

## 6. Three Levels of Comparison

### 6.1. Byte-for-byte equality

Directly comparing bytes.

Suitable for:

- Artifacts requiring reproducible binary output.
- Signatures/hashes when a canonical representation is committed.
- Fixed-width records and exact binary protocols.
- File checksum contracts.
- Data that must remain identical byte for byte.

Not suitable if two JSON objects only differ in property order and the contract does not specify ordering.

### 6.2. Structural equality

Parse data into structures and then compare:

~~~text
JSON string -> JSON tree -> compare fields and values
XML document -> XML model -> namespace-aware compare
Database -> keyed rows -> compare columns
~~~

This comparison ignores some meaningless representational differences, yet must not ignore required fields, type changes, or array order if the contract requires them.

### 6.3. Semantic equality

Extract business facts:

~~~text
Result -> parse -> validate schema
       -> map domain facts
       -> compare business invariants
~~~

For example, two CSVs with the same records in different orders can be equivalent if the contract is an unordered set of records. Conversely, a transaction list ordered chronologically or by sequence number must preserve order.

### 6.4. Comparing by Data Domain

| Data | Typical comparison |
|---|---|
| Monetary amounts | Exact decimal and rounding rule |
| Dynamic UUID | Format, uniqueness, correlation |
| Ordered list | Exact sequence |
| Value set | Set equality |
| List with duplicate elements | Multiset equality |
| Instant | Same point in time or bounded tolerance per contract |
| Security decision | Exact allow/deny semantics |
| Performance | Statistics and SLO |
| Digital signature | Verification and protocol-specific invariants |

Do not use one generic comparator for all output types.

## 7. JSON: Differences to Distinguish

Two JSON objects:

~~~json
{"id":"A1","status":"PAID"}
~~~

~~~json
{"status":"PAID","id":"A1"}
~~~

are usually equivalent regarding object members. However:

~~~json
{"items":["A","B"]}
~~~

~~~json
{"items":["B","A"]}
~~~

can differ semantically if items is an ordered sequence.

### 7.1. Missing Differs from Null Differs from Zero

~~~json
{}
~~~

~~~json
{"discount":null}
~~~

~~~json
{"discount":0}
~~~

must not be treated as equivalent by default. For PATCH, missing may mean keep unchanged; null may mean delete; zero may be a concrete numeric value.

### 7.2. Number Differs from String

~~~json
{"total":125000}
~~~

~~~json
{"total":"125000"}
~~~

differ in wire type, even though a lenient parser may convert them. If the API contract requires a number, replacing a number with a string is a breaking change for many consumers.

### 7.3. Field Rename

~~~json
{"customerId":"C-1"}
~~~

is not the same as:

~~~json
{"clientId":"C-1"}
~~~

A semantic comparator might recognize that the two names share the same meaning, yet that **does not prove backward compatibility**. If an old consumer only understands customerId, changing the wire name can still break the system.

### 7.4. Property Order and Canonical Serialization

Some systems sign canonical JSON or hash payloads. When a contract requires exact canonical bytes, property ordering/escaping may be governed by canonicalization rules. Do not rely on the rule “JSON object order does not matter” to ignore a signature mismatch.

## 8. Example: Comparing JSON with Jackson and JUnit

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JsonCompatibilityTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void objectMemberOrderDoesNotMatter() throws Exception {
        String oldJson =
            "{\"id\":\"A1\",\"amount\":2,\"status\":\"PAID\"}";
        String newJson =
            "{\"status\":\"PAID\",\"id\":\"A1\",\"amount\":2}";

        JsonNode before = mapper.readTree(oldJson);
        JsonNode after = mapper.readTree(newJson);

        assertEquals(before, after);
    }
}
~~~

In the example, Jackson JsonNode equality for JSON objects does not require the same property order as the original strings. JSON arrays are still compared in order.

### 8.1. Ignoring Exactly One Metadata Field

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class NarrowNormalizationTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void ignoresOnlyRootTraceId() throws Exception {
        JsonNode a = mapper.readTree(
            "{\"orderId\":\"O1\",\"total\":\"10.00\",\"traceId\":\"x\"}"
        ).deepCopy();

        JsonNode b = mapper.readTree(
            "{\"traceId\":\"y\",\"total\":\"10.00\",\"orderId\":\"O1\"}"
        ).deepCopy();

        ((ObjectNode) a).remove("traceId");
        ((ObjectNode) b).remove("traceId");

        assertEquals(a, b);
    }
}
~~~

This snippet assumes the root is an object and the contract allows /traceId to differ in value. For untrusted data, validate the node type and schema before casting or normalizing.

**Warning:** if the contract requires traceId to be present and in a valid format, merely removing the field and comparing is not enough. Check the presence/type/format of that field first, then ignore the dynamic value part.

### 8.2. Do Not Normalize Before Schema Validation

A safe order:

~~~text
Raw JSON
  |
  v
Schema/type checks
  |
  v
Validate allowed dynamic fields
  |
  v
Normalize only approved paths
  |
  v
Compare business facts
  |
  v
Report raw and normalized diff
~~~

This avoids accidentally masking a missing required field or a changed JSON type.

## 9. Ordering of Lists, Sets, Multisets, and Pagination

A comparator needs to know the collection semantics.

| Contract | Example | Comparison rule |
|---|---|---|
| Sequence | Transaction history, event order | Compare in the same order |
| Set | Normalized permissions | Compare element set |
| Multiset | Cart lines that may repeat | Compare both values and occurrence counts |
| Map | Key/value data | Compare by key |
| Ordered page | Sorted search results | Compare order and boundaries |

If you simply convert a list to a HashSet and compare, duplicates are lost. If a paginated API has unstable sorting, define a tie-breaker, such as ORDER BY created_at, id.

### 9.1. Occurrence Counting Example

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class Multisets {
    public static <T> Map<T, Long> count(List<T> values) {
        Map<T, Long> result = new HashMap<>();

        for (T value : values) {
            result.merge(value, 1L, Long::sum);
        }

        return result;
    }
}
~~~

Multiset comparison:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

assertEquals(
    Multisets.count(beforeItems),
    Multisets.count(afterItems)
);
~~~

Use only when the contract does not guarantee order yet still requires preserving repetition counts.

### 9.2. HashMap Iteration Order After a JDK Upgrade

HashMap does not guarantee iteration order like a sorted List. JDK or dependency changes can alter outputs that accidentally rely on HashMap iteration. However, even though the old behavior was not guaranteed by the Java specification, real consumers may have come to depend on that output. Investigate the de facto contract before declaring it safe.

## 10. Time, Timezone, and Clocks

A test running V1 at 10:00:00 and V2 at 10:00:01 can observe different timestamps even with identical logic.

### 10.1. Best Practice Is Injecting Clock

~~~java
import java.time.Clock;
import java.time.Instant;

public final class PaymentService {
    private final Clock clock;

    public PaymentService(Clock clock) {
        this.clock = clock;
    }

    public Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

Test:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PaymentServiceTest {
    @Test
    void fixedClockMakesOutputDeterministic() {
        Instant instant =
            Instant.parse("2026-11-12T03:00:00Z");

        Clock fixed = Clock.fixed(
            instant,
            ZoneOffset.UTC
        );

        PaymentService service = new PaymentService(fixed);

        assertEquals(instant, service.createdAt());
    }
}
~~~

If Clock is controlled in the application layer, both versions can produce identical timestamp values. This is generally better than stripping all timestamps from comparison.

### 10.2. When the Clock Cannot Be Fixed

A policy can allow a bounded difference on a specific field, such as a processing timestamp created between request start and end. However, define:

- Field name/JSON path.
- Time range.
- Unit and precision.
- Offset/timezone.
- Out-of-bounds cases must fail.
- Whether the timestamp type must be exact or not.

Do not use a wide time tolerance for expiration, security tokens, or ledger timestamps if the contract requires exactness.

### 10.3. JDK Timezone Data May Differ

A JDK update may bring new timezone/locale data; container base images also have different default timezones. Test with an explicit ZoneId, especially around DST and regions with time-policy changes. If the new version reflects a new official timezone rule, that may be an intentional change; record the scope and consumer impact.

## 11. Randomness, UUIDs, and Correlation

Values that typically differ across two runs:

- UUID.
- Session ID.
- Trace ID.
- Security token.
- Generated database ID.
- Random sample ID.
- Retry/backoff jitter.

### 11.1. Do Not Fix SecureRandom in Production

For deterministic tests, inject an IdGenerator or TokenGenerator. Test builds use a seeded/fixture generator; production builds use a generator meeting security requirements.

Do not modify production code by replacing SecureRandom with java.util.Random just to make snapshot tests pass.

### 11.2. Compare Relationships Instead of Raw IDs

~~~text
POST /orders -> returns orderId
GET /orders/{orderId} -> returns same order
OrderCreated event -> references same orderId
Database order -> same business entity
~~~

IDs between V1 and V2 may differ, but within each run, components must link accurately. Comparators should map by business key and verify referential consistency rather than stripping all identifiers.

### 11.3. ID Formats Also Have Contracts

If the public API promises a UUID string, V2 returning null or an invalid string must not be treated as an allowed difference. Rules should only ignore raw values after validating format, uniqueness, and relationships.

## 12. Floating Point, BigDecimal, and Precision

Do not use the same tolerance for all numeric values.

| Domain | Appropriate comparison |
|---|---|
| Money, balances | Exact decimal and rounding policy |
| Quantities | Exact integer |
| Sensor measurements | Absolute/relative tolerance per accuracy |
| Scientific results | Error bounds + special cases |
| Percentage reports | Specified scale, precision, rounding |
| Signatures/hashes | Exact/protocol verification |

### 12.1. BigDecimal Scale and Value

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

If the business contract only requires the same decimal value, compareTo can be used. If the API requires two digits after the decimal point when serialized to a string, scale remains part of the contract.

### 12.2. Numeric Tolerance in JUnit

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SensorTest {
    @Test
    void boundedMeasurementNoise() {
        double expected = 12.345678;
        double actual = 12.345680;

        assertEquals(expected, actual, 0.00001);
    }
}
~~~

The 0.00001 threshold is illustrative only. In real projects it must be chosen according to device/algorithm accuracy, not incrementally relaxed until the test turns green.

### 12.3. Absolute and Relative Tolerance

A rule can express:

~~~text
abs(actual - expected) <= absoluteTolerance
OR
abs(actual - expected)
    <= relativeTolerance * max(abs(expected), abs(actual))
~~~

Consider numbers near zero, extremely large numbers, NaN, infinity, and signed zero. Tolerance depends on the value domain and correctness requirements.

### 12.4. Rounding Mode Is a Business Policy

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("12.345");
BigDecimal rounded = amount.setScale(
    2,
    RoundingMode.HALF_EVEN
);
~~~

If V1 and V2 differ due to HALF_EVEN/HALF_UP, this is a policy change requiring approval, not natural floating-point noise.

### 12.5. JDK/Hardware Upgrades Do Not Explain All Discrepancies

Some numeric differences can come from algorithms, vectorization, dependencies, or CPU architecture. Still, consult the numeric contract before legitimizing any discrepancy.

## 13. Serialization and Schema Compatibility

Upgrading the JDK often goes together with upgrading Jackson, JAXB, Hibernate, Spring, Avro/Protobuf libraries, or configuration.

Differences can appear in:

- Wire field names.
- Null/missing/default.
- String vs number.
- Enum representations.
- Date/time format.
- JSON property order.
- XML namespace/whitespace.
- Array/list order.
- Object serialization.
- Binary schema resolution.
- Unknown-field handling.

### 13.1. A Semantic Match Does Not Replace Wire Compatibility

V1:

~~~json
{"amount":125000}
~~~

V2:

~~~json
{"amountText":"125000"}
~~~

A comparator that knows how to map amountText to amount can compute the same business value, yet clients reading amount can break.

Therefore **two separate conclusions** are needed:

1. Are the business facts equivalent?
2. Is the wire/API contract compatible with old consumers?

### 13.2. XML

Whitespace and attribute order may be insignificant under an XML data model, yet element order, namespace URIs, and text content can matter. For XML signatures, use the signature protocol's canonicalization standard rather than arbitrarily stripping or sorting XML.

### 13.3. Avro/Protobuf

A schema registry can check compatibility rules, yet it does not know whether default values are business-accurate. Consumer–writer matrix testing and historical event replay remain necessary.

### 13.4. Java Object Serialization

ObjectOutputStream has serialVersionUID, class descriptors, and its own schema evolution rules. During migration, test deserializing historical data and round-trip semantics; do not just compare raw serialized bytes if a byte-level format is not promised.

## 14. Database: Also Compare Post-Transaction State

Identical responses with different database state can still be a regression.

~~~text
Input: completeOrder("O-42")

V1:
  orders.status = COMPLETED
  payments.captured = 1
  outbox OrderCompleted = 1 event

V2:
  orders.status = COMPLETED
  payments.captured = 1
  outbox OrderCompleted = 2 events
~~~

The response may look identical, yet V2 violates the duplicate event invariant.

### 14.1. Snapshotting by Business Keys

Use a database seeded with identical data and snapshot the relevant tables/records. For auto-generated primary keys, map by business key and verify foreign-key relationships.

Do not remove all IDs from comparison if they serve an integrity role.

### 14.2. Data Without ORDER BY

SQL does not guarantee row order when a query has no ORDER BY. If the API contract requires ordering, define ORDER BY with a tie-breaker; if the output is a set, a multiset comparison is more appropriate.

### 14.3. Transaction Semantics

Check:

- Commit and rollback.
- Atomicity.
- Isolation.
- Optimistic locking/version.
- Constraint enforcement.
- Retries and idempotency.
- Number of records affected.
- Outbox consistency.
- Duplicate prevention.

### 14.4. Database Schema Migration Is a Separate Change

If upgrading the JDK at the same time as changing schemas, separate root causes of errors. Old data may have defaults/missing fields and new drivers may deserialize differently, so fixtures for historical rows are needed.

## 15. Events, Queues, and Eventual Consistency

For Kafka/RabbitMQ or event systems, comparison needs to check:

- Topic/queue.
- Partition/key.
- Event type/schema version.
- Headers and payload.
- Event count.
- Ordering within the committed scope.
- Retries, duplicates, and dead-letter behavior.
- Consumer-visible final state.

### 15.1. Do Not Impose Global Order Outside the Contract

A broker may only guarantee ordering within a partition or aggregate. Do not compare all events by global sequence when the contract does not commit to it; however, preserve order within the scope where it is meaningful.

### 15.2. Eventual Consistency Needs Wait-Until

~~~text
Start operation
       |
       v
Poll expected invariant
       |
       +--> reached before deadline: pass
       +--> deadline exceeded: fail
~~~

Do not merely hard-sleep for a fixed duration and compare outputs if the system has variable asynchronous latency.

### 15.3. Shadow Traffic Must Isolate Side Effects

A payment request sent concurrently to V1/V2 can charge twice if not isolated. Shadow runs should use separate environments or stub providers while controlling idempotency and data usage permissions.

## 16. Exceptions and Error Responses Are Also Contracts

V1:

~~~json
{"code":"INVALID_AMOUNT","message":"Amount must be positive"}
~~~

V2:

~~~json
{"status":400,"error":"Bad Request"}
~~~

Both may return HTTP 400 yet differ in machine-readable error code. If clients rely on INVALID_AMOUNT, this is a breaking change.

### 16.1. Classifying Stability Levels

| Component | Usually needs to be preserved? |
|---|---|
| HTTP status | Per API contract |
| Machine-readable error code | Per API contract |
| Error body schema | Per API contract |
| User-facing message | May be localized per policy |
| Internal stack trace/line number | Usually not part of the contract |
| Java exception type in public library | Can be a source/binary API contract |
| Audit event | Usually must preserve semantics |

Do not ignore the entire error response merely because wording changed.

### 16.2. Security Errors

A change making error messages less revealing can be an improvement. Still, check error codes, authorization outcomes, and avoid leaking data. In particular, a request previously denied that is now permitted must be treated as a security regression until proven otherwise.

## 17. Locale, Charset, Timezone, and Unicode

JDKs, locale providers, and container images can alter outputs in:

- Dates/months and calendars.
- Decimal separator.
- Currency format.
- Collation and sorting.
- Default charset.
- Line endings.
- Unicode normalization/case mapping.
- Timezone data.

Starting in Java 18, the default charset is standardized to UTF-8 per JEP 400 within its defined scope. If legacy code relies on the OS default charset, migration can produce file/network output differences.

### 17.1. Use Explicit Locale

~~~java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat format = NumberFormat.getNumberInstance(
    Locale.forLanguageTag("vi-VN")
);

String result = format.format(12345.67);
~~~

If a fixed formatting contract is needed, tests should specify Locale/timezone/charset explicitly rather than relying on undocumented defaults.

### 17.2. Line Endings

LF and CRLF may be equivalent for a text file if the contract only specifies line content. However, for signed files, hashes, or fixed-width protocols, every byte can matter. Do not normalize line endings globally.

### 17.3. Unicode Normalization

Two visually identical strings can contain different code-point sequences. Unicode normalization may be a valid requirement for search/input, yet may alter IDs, signatures, or payloads needing verbatim round-trips. Choose based on domain.

### 17.4. Sorting with Locale

If the API requires stable pagination, there must be a comparator/collation policy and a tie-breaker. An ordering change when upgrading locale data needs to be tested with accented Vietnamese data, not just ASCII.

## 18. Security: A Category of Differences That Must Be Evaluated Separately

Upgrading the JDK can change TLS policies, certificate validation, cryptographic defaults, module access, or reflection behavior.

### 18.1. Legacy TLS Rejected

V1 connects to an endpoint that only supports weak algorithms, while V2 rejects it. This may be the right change under security policy, yet requires a migration plan:

1. Confirm the protocol/cipher/certificate causing the error.
2. Assess the required security level.
3. Upgrade the server or use a controlled gateway when needed.
4. Approve a time-bound exception if any.
5. Test downgrade resistance and certificate validation.
6. Do not disable hostname verification or enable trust-all to make tests pass.

### 18.2. Authorization Invariants

Example:

~~~text
Tenant A must not view Tenant B's data.
Expired tokens must be rejected.
Unauthorized users must not update roles.
Invalid input must not cause side effects.
~~~

These invariants matter more than the overall pass rate. An authorization regression cannot be hidden by a normalization rule even if it affects only a single test case.

### 18.3. Cryptographic Output

Some signatures involve randomness, so raw signature bytes differ across two signing runs even when both are valid. In that case, tests can check verification success, key identity, algorithm policy, and integrity. However, for digest/canonical hashing contracts, byte equality must still be preserved.

Do not use the ability to sign “successfully” to overlook an algorithm downgrade.

## 19. Performance Regression Differs from Functional Regression

Java processing time is affected by JIT, GC, CPU, heap, warm-up, container quotas, native libraries, and network. A 4 ms call on V1 and 5 ms on V2 is not enough to conclude a regression.

### 19.1. Functional Comparison

~~~text
Input -> expected business output/side effects
~~~

### 19.2. Non-Functional Comparison

~~~text
Comparable workload
      |
      v
Distributions of latency, throughput, CPU, memory, errors
      |
      v
SLO/guardrails with sufficient evidence
~~~

Both types must use separate criteria. Do not apply a 10% latency tolerance to monetary amounts or transaction counts.

### 19.3. Factors to Control When Measuring

- JDK vendor/update.
- CPU architecture.
- JVM heap/GC.
- Thread counts.
- Request mix.
- Database/cache state.
- Network conditions.
- Warm-up duration.
- Sample size and number of runs.
- Monitoring/agent overhead.

### 19.4. Useful Metrics

- p50/p95/p99 latency.
- Throughput.
- Error rate.
- CPU utilization.
- GC pause distribution.
- Allocation rate.
- RSS/native memory.
- Queue lag.
- Startup time.

A version with higher throughput because it returns more errors is not an improvement.

### 19.5. Microbenchmarks and End-to-End

When measuring very small Java methods, JMH or a suitable benchmarking tool is more useful than a single-call System.nanoTime. However, evaluating a production migration still requires integration/load tests on the real deployment topology.

## 20. JDK Changes That May Be Valid Yet Still Require Evidence

| Difference | Potentially acceptable when | Needs additional checks |
|---|---|---|
| JSON property order | Object structure equivalent | Signed/canonical payload? |
| HashMap iteration order | Order is not part of the contract | Do real consumers depend on it? |
| UUID/traceId | Dynamic value, valid format | Correlation/uniqueness |
| Processing timestamp | Time-bounded policy exists | Expiration/audit semantics |
| Error wording | Machine-readable contract stable | Consumer/client parsing |
| Charset output | Intentional UTF-8 contract | Historical data |
| Locale format | Policy updated | Internationalization tests |
| TLS handshake rejected | Required by new security policy | Support plan for old endpoints |
| GC log format | Switched to Unified Logging | Parsers/metrics still work |
| Small latency delta | Within SLOs/guardrails | Statistical reliability |

No row in the table passes automatically. They are **candidates** for a decision grounded in contracts, policy, and evidence.

## 21. Flaky Tests and Non-Determinism

Common sources of nondeterminism:

- Realtime clock.
- Random IDs.
- Thread scheduling.
- Concurrent races.
- HashMap/HashSet iteration.
- File listing order.
- External API changes.
- Retries/backoff.
- Cache warm-up.
- Background jobs.
- Tests sharing a database/queue.

### 21.1. A Successful Re-Run Does Not Prove the Test Was Wrong

If a test fails 10% of the time, that may be a real concurrency regression. Do not auto-retry and ignore the first failure without investigating.

### 21.2. Making Tests Deterministic

Prioritize:

- Clock injection.
- Deterministic ID generator in tests.
- Isolated database seeds.
- Upstream stubs.
- Bounded wait-until.
- Explicit sort order.
- Unique test namespaces.
- Controlled concurrency.
- Fixed fixture versions.
- Recording execution metadata on failure.

### 21.3. Do Not Use Indefinitely Long Sleeps

For asynchronous operations, condition-based waiting and an appropriate deadline work better than Thread.sleep for a fixed duration. If the timeout exceeds the business threshold, the test must fail.

## 22. Property-Based and Metamorphic Testing

When exact output is non-deterministic, relationships can be tested.

Examples:

- Serialize then deserialize preserves business data.
- Given non-negative unit prices, increasing quantity does not decrease subtotal.
- Two requests with the same idempotency key do not create two payment charges.
- Concatenated pages neither lose nor duplicate records under a fixed snapshot.
- Sum of line totals must equal order total under the rounding policy.
- An unauthorized user cannot read another tenant's data.

### 22.1. Metamorphic Relation

~~~text
Input A -> Output A

Transform Input A -> Input B -> Output B

Required relation:
  Relation(Output A, Output B) == true
~~~

This approach does not require knowing the exact output for every input. It complements differential testing, especially if V1 and V2 share the same bug.

### 22.2. Boundary Inputs

Must include:

- Min/max integers and overflow.
- BigDecimal scale/rounding.
- NaN/infinity/signed zero.
- Unicode, combining marks, and surrogate pairs.
- Null/missing/empty.
- DST/leap day/timezone.
- Duplicate records.
- Deep JSON/XML nesting.
- Malformed certificates.
- Concurrent retries.
- Historical schema versions.

Boundary cases detect parser/serializer/JDK changes much more easily than a happy-path-only dataset.

## 23. Normalization Rules Must Be Narrow and Verifiable

Normalization is a tool, not a license to ignore unexpected results.

A good rule might look like:

~~~yaml
ruleId: DIFF-TRACE-001
scope:
  endpoint: GET /orders/{id}
  jsonPath: /traceId
operation: compare-format-only
constraints:
  required: true
  type: string
  nonEmpty: true
reason: Diagnostic identifier is generated independently
owner: api-platform
reviewDate: 2027-03-01
~~~

This is an illustrative schema, not the format of any specific library.

### 23.1. What Should Be Included in a Rule

- Stable ID.
- API/event/module scope.
- Exact JSON path or database column.
- Pre-/post-normalization conditions.
- Maximum deviation when it is a tolerance.
- Business/technical justification.
- Owner and reviewer.
- Expiration/review date.
- Negative tests proving it does not mask other bugs.

### 23.2. What Not to Do

~~~yaml
ignoreFieldsMatching: "*Id"
ignoreAllTimestamps: true
ignoreAllUnknownProperties: true
~~~

These rules can lose evidence of wrong tenantId/orderId, expired tokens, audit timestamps, or schema drift.

### 23.3. Keep Both Raw and Normalized Diffs

Example report:

~~~text
Raw:
  /traceId: abc -> def

Rule:
  DIFF-TRACE-001

Checks:
  field exists: yes
  type is string: yes
  format valid: yes
  correlation within run: yes

Normalized:
  no remaining differences

Decision:
  approved non-semantic difference
~~~

Do not store only normalized data, because reviewers need to know what was ignored.

## 24. Catalog of Approved Differences Differs from Known Defects

Must distinguish:

**Approved difference:** a difference that does not violate the contract or is an approved contract change.

**Known defect:** an identified regression that has not yet been fixed.

Example:

~~~text
DIFF-090
Status: KNOWN_DEFECT
Impact: Export loses one optional customer attribute
Owner: reporting-team
Mitigation: Disable affected export variant
Fix milestone: next release
~~~

A known defect can be handled by a release manager under a separate risk decision, yet must not be relabeled as semantic equivalent to make the report look clean.

### 24.1. Intentional Changes

An intentional behavior change requires:

1. Specific business/technical requirement.
2. Consumer impact assessment.
3. Versioning/deprecation if breaking.
4. Positive tests for the new behavior.
5. Negative tests for disallowed behavior.
6. Appropriate approval and release notes.
7. Rollback/contingency if needed.

**Allowed does not mean “zero risk remaining”.**

## 25. Do Not Use Total Diff Count as the Sole Guardrail

Example:

~~~text
Total: 10,000 cases
Exact match: 8,000
Semantic equivalent: 1,700
Approved changes: 250
Unexpected: 50
Inconclusive: 0
~~~

These are illustrative numbers. A 99.5% pass rate is insufficient if the remaining 50 cases are payment/authorization errors.

### 25.1. Classification by Severity

- Critical: security, money, irreversible data loss.
- High: breaking API, duplicate side effects, transaction violations.
- Medium: consumer-visible output/behavior difference with mitigation.
- Low: cosmetic/diagnostic non-contract change.

Actual severity must be based on the organization's risk policy. One critical case can block a release even if thousands of other cases pass.

### 25.2. Tie Diffs to Specific Locations

Reports should group by:

- Endpoint/operation.
- Business domain.
- JSON path/database field.
- Exception/error code.
- Dependency/JDK version.
- Platform.
- Approved rule ID.
- Owner.
- Test fixture.

Do not merely count 18 diffs; if 18 old diffs disappear yet 18 new diffs appear, the unchanged total is still a problem.

## 26. Designing the Comparison Engine

A model:

~~~text
Input fixtures or sanitized replay
             |
             v
 Old execution / New execution
             |
             v
 Collect responses, database, events,
 files, metrics and diagnostics
             |
             v
 Validate schema and required fields
             |
             v
 Domain-specific comparison
   - exact
   - structural
   - multiset/sequence
   - numeric/time bounds
   - relational invariants
             |
             v
 Approved-difference rules
             |
             v
 Classify:
   equal
   semantic match
   approved change
   regression
   inconclusive
             |
             v
 Evidence report and review
~~~

### 26.1. The Comparator Must Not Alter Production Output

Normalization is only applied to a copy inside the test harness/compare layer. Do not alter real databases or API responses to make comparisons pass.

### 26.2. Schema Must Be Checked First

If total becomes totalAmount, semantic mapping may see the same value while old client schemas can still break. Reports must present wire contract status and semantic business status separately.

### 26.3. Collecting Side Effects

A comparison result can be divided into:

~~~text
response:
  status
  headers
  body

sideEffects:
  databaseChanges
  events
  outboundCalls
  generatedFiles

nonFunctional:
  latency
  cpu
  memory
  logs
~~~

Not every test needs to capture every component, yet you must know what has not been verified.

### 26.4. Inconclusive Is Not Success

If an external dependency times out, a database snapshot cannot be collected, or the test harness parser crashes, it must be recorded as inconclusive/infra failure. Concluding compatibility requires sufficient evidence across the defined scope.

## 27. Actionable Diff Reports

Example:

~~~text
Case:
  ORDER-QUOTE-017

Baseline:
  Java 11, app 4.2.0

Candidate:
  Java 21, app 5.0.0

Request:
  quote-two-items.json

Difference:
  JSON path: /total
  Before: "240000.00"
  After:  "240000.01"

Classification:
  UNEXPECTED_SEMANTIC_DIFFERENCE

Severity:
  HIGH

Environment:
  Locale: vi-VN
  Timezone: UTC
  Database seed: fixture-2026-11

Rule:
  none

Next action:
  Investigate rounding/dependency behavior
~~~

Example allowed difference:

~~~text
Case:
  ORDER-QUOTE-017

Difference:
  JSON path: /traceId
  Before: "e4..."
  After:  "a1..."

Classification:
  APPROVED_NON_SEMANTIC_DIFFERENCE

Rule:
  DIFF-TRACE-001

Validation:
  Both are valid identifiers
  Correlation within each run verified

Owner:
  api-platform

Review:
  2027-03-01
~~~

Do not allow reports to automatically attach secrets/PII; sanitized fixtures, redacted values, and secure internal links can be stored instead.

## 28. Differences That Can Usually Be Allowed

### 28.1. Diagnostic Metadata

Trace ID or diagnostic timestamp if outside the contract and backed by rules checking presence/format/correlation.

### 28.2. JSON Object Member Order

Normally carries no meaning in semantic JSON. Signed canonical JSON cases must follow signature rules.

### 28.3. Non-Semantic Whitespace

For example, JSON pretty-printing or line endings of text files allowed by contract. Does not hold for XML text content, fixed-width protocols, or signed payloads.

### 28.4. Log Format

A new JDK may use Unified Logging for GC instead of PrintGCDetails. Different raw log text is normal, yet parsers, metrics, and investigation capabilities still need verification.

### 28.5. Internal Error Messages

Stack trace line numbers and wording can change. However, public error codes/HTTP status and security behavior still need to be preserved or versioned.

### 28.6. Bounded Numeric Differences

Only for floating-point or measurement domains with designed tolerances; do not apply by default to currency ledgers.

### 28.7. Approved Security Changes

A legacy TLS endpoint may be rejected under new policy. This is a migration exception/intentional change requiring consumer impact assessment and mitigation, not a bug to be silently ignored.

## 29. Differences That Must Be Treated as Issues Until Proven Otherwise

- Incorrect monetary amount, currency, or tax policy.
- Missing required API field.
- JSON type change not supported by consumers.
- Data loss or writing to the wrong tenant.
- Authorization change outside policy.
- Missing audit event.
- Transaction loss of atomicity.
- Duplicate event publication causing side effects.
- Critical ordering altered.
- Broken uniqueness or foreign key.
- Historical data serialization fails.
- Incorrect cryptographic verification.
- Incorrect expiration/security timestamp.
- Native crash/JVM crash.
- Error rate increasing past guardrail.
- p99 latency exceeding SLO under comparable workload.

If the product intentionally changes one of these behaviors, a dedicated breaking-change process with an owner and consumer migration is required; it cannot be resolved with an unconditional ignore rule.

## 30. Layered Regression Test Suite

### 30.1. Unit Tests

Verify domain calculations, parsers, formatters, validation. Use a fixed Clock and deterministic inputs.

### 30.2. Contract Tests

Verify API/event schemas, error codes, consumer compatibility, fields, and enum behavior.

### 30.3. Integration Tests

Run databases, brokers, serializers, and frameworks on the target JDK. Verify transactions and side effects.

### 30.4. Differential Replay

Run the same fixtures on V1/V2, capture outputs, compare semantics, and classify against rules.

### 30.5. Shadow/Canary

Capture representative traffic with isolated or controlled side effects; monitor operational errors and SLOs. Do not send real duplicate payment operations merely to compare.

### 30.6. Production Rollout

After CI passes, measure behavior on the new runtime/image and have a rollback plan. Regression testing does not end at the compiler boundary.

## 31. Workflow for Classifying and Approving Differences

### Step 1 — Lock Down the Contract

Define strict invariants, wire APIs, dynamic fields, error codes, data side effects, and performance guardrails.

### Step 2 — Create the Baseline

Save outputs from the old JDK, input fixtures, database seed, Java/dependency versions, and environment metadata.

### Step 3 — Control Non-Determinism

Inject Clock/ID generators, stub external systems, reset the database, choose explicit ordering, and pin feature flags.

### Step 4 — Run the Candidate

Use the target JDK, framework, container, and OS/architecture. Collect responses, databases, events, and metrics.

### Step 5 — Validate Schema

Catch field name/type changes, missing/null values, enums, and required/optional fields before normalization.

### Step 6 — Compare by Domain

Apply appropriate exact, structural, sequence/multiset, numerical/time tolerance, or relational invariants.

### Step 7 — Apply Approved Rules

Apply only active rules within scope and constraints. Record raw diff, rule ID, and validation results.

### Step 8 — Triage Anomalies

Classify as regression, intentional change, known defect, flaky test, infrastructure failure, or unresolved. Do not automatically merge unresolved into allowed.

### Step 9 — Review and Update Golden Fixtures

Update the baseline only after reviewers understand the diff and decide. Add negative tests proving the comparator has not become too loose.

### Step 10 — Canary and Rollback Readiness

Monitor error rates, SLOs, data integrity, security, and native/runtime failures. If serious discrepancies appear, roll back according to the designed procedure.

## 32. Synthesis Example: Upgrading Java 11 to Java 21

An order service exhibits the following differences:

| Output | V1 | V2 | Assessment |
|---|---|---|---|
| JSON field order | id before status | status before id | Potentially semantic-equivalent |
| traceId | UUID A | UUID B | Potentially allowed if format/correlation valid |
| total | 100.00 | 100.01 | Fail, check rounding |
| processedAt | T0 | T0+1s | Use Clock or bounded policy |
| items array | A, B | B, A | Fail if ordered contract |
| Error code | INVALID_AMOUNT | BAD_REQUEST | Review client contract |
| TLS legacy | Success | Rejected | Security policy review |
| GC log | Legacy syntax | Unified Logging | Parser/observability validation |
| p99 latency | 180 ms | 185 ms | Evaluate distribution/SLO |
| Outbox events | 1 | 2 | Regression if duplicate side effects |

A good report does not just say “there are 10 diffs”. It must classify each diff by semantics, contract, risk, and decision.

### 32.1. Decision Example

~~~text
Approved:
  JSON object property order
  Diagnostic traceId values

Requires investigation:
  Monetary rounding
  Array ordering
  Duplicate event

Requires product/security decision:
  Legacy TLS endpoint rejection

Requires performance analysis:
  p99 latency trend under comparable workload

Requires tooling migration:
  GC log parser for Unified Logging
~~~

## 33. Comparator Design Checklist

- [ ] Independent contract defined, not just snapshots of the old version.
- [ ] Raw bytes, structure, and semantic facts distinguished.
- [ ] Both responses and side effects checked.
- [ ] Schema validated before normalization.
- [ ] JSON object and array ordering distinguished.
- [ ] Sequence, set, and multiset distinguished.
- [ ] Missing/null/empty/zero distinguished.
- [ ] Rounding/precision defined for each numeric domain.
- [ ] Clock/timezone controlled.
- [ ] Random IDs and correlation controlled.
- [ ] Historical data fixtures included.
- [ ] Locale/charset/Unicode checked.
- [ ] Idempotency and concurrency checked.
- [ ] Security invariants kept strict.
- [ ] Allowed differences distinguished from known defects.
- [ ] Rule ID, scope, owner, and expiry attached.
- [ ] Negative tests for normalization included.
- [ ] Production data/PII protected in fixtures.
- [ ] Both raw diff and normalized diff saved.
- [ ] Inconclusive status included.
- [ ] Tested on target runtime/container.
- [ ] Canary and rollback guardrails designed.

## 34. Allowed Difference Record Template

~~~text
RULE
  Rule ID:
  Status: PROPOSED / APPROVED / EXPIRED
  Owner:
  Reviewer:
  Created:
  Review date:

SCOPE
  Service:
  Endpoint/event:
  Schema/contract version:
  Input fixtures:
  JSON path / DB column:
  Old JDK:
  New JDK:
  Framework/library versions:

DIFFERENCE
  Previous behavior:
  New behavior:
  Kind: structural / semantic / performance
  Allowed transformation:
  Allowed bound:
  Preconditions:
  Cases that must fail:

JUSTIFICATION
  Business requirement:
  Technical cause:
  Consumer impact:
  Security impact:
  Evidence/ticket:

VALIDATION
  Raw output:
  Normalized output:
  Positive tests:
  Negative tests:
  Old/new integration tests:
  Replay tests:
  Performance evidence:

DECISION
  Approved:
  Release impact:
  Rollback condition:
  Expiration/removal milestone:
~~~

This template prevents a rule from turning into a permanent exception whose reason nobody knows.

## 35. Summary

Comparing results during a Java upgrade is not just performing a text diff. It is the process of establishing **behavioral contracts**, building **test oracles**, controlling inputs and environments, comparing by **business semantics**, and managing intentional differences with evidence and approval.

Key principles:

1. **Compare by contract, not just by text.** Harmless representational differences can be normalized, yet field names, types, and business facts must still be accurate.
2. **Avoid overly broad normalization.** Every rule must have scope, constraints, owner, review date, and negative tests.
3. **Eliminate spurious diffs from Clock, randomness, and environment** before widening tolerances.
4. **Stay strict on money, data, and security.** Do not ignore errors because the overall pass rate is high.
5. **Check side effects as well.** Databases, events, transactions, and idempotency can break even when HTTP bodies look identical.
6. **Combine differential tests with independent invariants.** The old version may contain bugs; do not treat it as the sole truth.
7. **Distinguish intentional changes from known defects.** A known bug does not magically become valid output.
8. **Evaluate performance by distributions and comparable workloads.** A single measurement is insufficient.
9. **Keep raw diffs, normalized diffs, and decisions.** It must be possible to audit what the comparator ignored.
10. **Verify through production runtime.** CI, integration, canary, metrics, and rollback are parts of a single migration.

A well-tested migration does not require every output byte before and after upgrading the JDK to match. It requires every **meaningful difference** to be visible, explained with contracts and evidence, explicitly conditionally approved, or blocked for fixing before corrupting system data and behavior.
