# Business Rules in Processor — Controlling Data Quality with Spring Batch

## 1. Why Should Business Rules Be Explicitly Designed in the Processor?

An order import batch typically has three stages:

```text
CSV / JDBC / API source
        |
        v
  ItemReader<I>
  reads and builds input items
        |
        v
  ItemProcessor<I, O>
  normalizes + evaluates business rules
        |
        +-- valid -----------------------> output item O
        |
        +-- out of scope ----------------> null (intentional filter)
        |
        +-- violation needing handling --> exception or REJECTED result
        |
        v
  ItemWriter<O>
  writes a chunk's results
```

For example, an order is written to the system only if:

- It has a valid external order ID.
- The order status is an actionable type.
- The amount is greater than 0, with valid format and currency.
- The business date matches the import period.
- The total amount does not exceed the auto-approval threshold.
- Orders requiring manual approval go into a separate flow rather than vanishing silently.

These requirements are **business rules**. They express business policy, not merely whether data matches a Java type.

In Spring Batch, **`ItemProcessor<I, O>`** is a natural place to implement per-item rules because it sits between reader and writer, can transform input to output, filter items, or raise errors according to step policy.

However, placing business rules in the processor **does not mean every problem should be solved by one giant `if/else`**. Decisions to filter, reject, quarantine, abort the entire job, look up reference data, or enforce cross-record consistency all need an explicit contract.

This lesson belongs to **Data quality** in **Spring Batch Core Processing**, using **Java 17+, Spring Batch 5.x, Spring Boot 3.x, and JUnit 5** as the context. API details should be cross-checked if your application uses another Spring Batch version, especially Spring Batch 6.x.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish schema validation, business rules, transformations, filters, rejects, and quarantine.
2. Use `ItemProcessor<I,O>` to evaluate per-item rules in a testable way.
3. Choose the right outcome: `return item`, `return null`, `throw exception`, or return a decision object.
4. Compose multiple processors or validators while preserving ordering and data contracts.
5. Connect rule violations with `skip`, `skipLimit`, `SkipListener`, and error persistence.
6. Design rules that stay stable across retries/restarts, avoid duplicate side effects, and support versioning and auditing.
7. Measure, test, and improve data quality with appropriate metrics.

---

## 2. How Do Business Rules Differ from Schema or Technical Checks?

An input can parse into a Java object successfully and still not be allowed to be written.

| Check Type | Example | Typically Suitable Layer |
| --- | --- | --- |
| Format / parsing | Date `2026-13-55` cannot parse into `LocalDate` | Reader/tokenizer/field mapper |
| Attribute validation | Blank `externalOrderId`, code length exceeds 50 | Bean Validation or processor |
| Per-item business rule | Order has `amount <= 0`, disallowed currency | Processor / domain rule service |
| Eligibility | `CANCELLED` order is outside report scope | Processor filter or upstream query |
| Cross-item rule | At most one order ID per period; total cost within budget | Unique constraint, staging/aggregation, writer, or reconciliation step |
| Target data constraint | Unique key, foreign key, check constraint | Database/writer as final safeguard |
| Whole-batch integrity | Complete sequence numbers; source total matches output | Post-processing aggregation/reconciliation step |
| Infrastructure | Lost DB connection, HTTP timeout | Retry/recovery; do not label as business error |

**A per-item processor is not the sole source of truth for dataset-wide correctness.** For instance, two items with the same external order ID may be handled by different threads. Using only a `HashSet` inside the processor for duplicate detection breaks easily under partitioning, retries, restarts, or multi-instance runs. Unique constraints or a controlled staging/dedup step are needed to protect global uniqueness.

### 2.1. Data Quality Has Multiple Dimensions

In batch applications, a rule usually protects one or more quality dimensions:

- **Completeness:** missing required fields.
- **Validity:** values failing business conditions.
- **Consistency:** contradictory states/values.
- **Uniqueness:** a business key appears only the permitted number of times.
- **Timeliness:** data belongs to an eligible processing period.
- **Accuracy:** values match the source or approved formulas.

Do not simply equate all unwanted values with "dirty data": a `CANCELLED` order can be completely valid data that is **outside the batch's scope**.

### 2.2. Rules Can Express Policy, Not Just Validation

Example:

```text
Order A: status = CANCELLED
  -> data-valid
  -> must not enter the completed orders table
  -> FILTERED

Order B: amount = -500
  -> violates amount > 0
  -> REJECTED or FAIL per policy

Order C: amount = 900_000_000
  -> valid data
  -> needs MANUAL_REVIEW per approval threshold

Order D: amount = 200_000
  -> valid and eligible
  -> ACCEPTED
```

If you return `null` for A, B, and C alike, `filterCount` goes up while losing any way to distinguish validly excluded items from rejected or review-required ones. That design destroys auditability.

---

## 3. The Core Contract of `ItemProcessor<I, O>`

In Spring Batch 5.x:

```java
@FunctionalInterface
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Three primary outcomes:

| `process` Return/Action | How Spring Batch Interprets It | Meaning to Define in Application |
| --- | --- | --- |
| Returns an object `O` | Item proceeds to chunk's writer | ACCEPTED or result to persist |
| Returns `null` | Item is **filtered**; excluded from chunk output | Use only when dropping the item is desired behavior |
| Throws exception | Step handles exception per fault-tolerant policy or fails | Validation/recoverable failure needing classification |

Key points:

- Returning `null` is **not an exception**, does not consume `skipLimit`, and does not increment `processSkipCount`; it is **filtering**.
- Processor exceptions can make the step `FAILED`, or be **skipped** if `.faultTolerant().skip(...)` is configured accordingly.
- Choosing skip drops the item within the execution per policy; it does not automatically persist the item into a durable error table.
- Processing an item may be **re-invoked** upon transaction rollback/retry. Processors should be deterministic and free of non-transactional side effects.

### 3.1. Filter vs. Skip

```text
ItemProcessor returns null
    |
    v
filtered item
    |
    +-- increments execution's filterCount
    +-- does not go to writer
    +-- does not count as process skip

ItemProcessor throws BusinessRuleViolationException
    |
    +-- configured non-skippable:
    |       step FAILS
    |
    +-- configured skippable within limit:
            item is SKIPPED
            processSkipCount increments
            SkipListener may be called
```

Filtering fits "no output needed"; skipping fits "bad record that can be controllably bypassed." If the business mandates a **rejection record** per failed item, use a durable quarantine/reject strategy instead of relying only on those two counters.

### 3.2. Define Policy Before Writing Code

A decision table aligns Product Owner, Data Steward, and operations:

| Rule Code | Condition | Decision | Reason |
| --- | --- | --- | --- |
| `ORDER_ID_REQUIRED` | Blank ID | REJECT | Cannot identify order |
| `STATUS_NOT_IN_SCOPE` | Status is CANCELLED | FILTER | Not part of output set |
| `AMOUNT_NON_POSITIVE` | Amount null or ≤ 0 | REJECT | Invalid monetary value |
| `CURRENCY_UNSUPPORTED` | Currency not in allowlist | REJECT | No processing support |
| `AMOUNT_SCALE` | Amount has more than 2 significant decimal places | REJECT | No silent rounding |
| `DATE_OUT_OF_SCOPE` | Order date differs from job business date | FILTER or REJECT per contract | Must be explicitly defined |
| `AMOUNT_REVIEW_REQUIRED` | Amount exceeds auto-approval threshold | MANUAL_REVIEW | Must not turn into silent data loss |
| `CUSTOMER_BLOCKED` | Customer is restricted | REJECT or MANUAL_REVIEW | Depends on compliance policy |

This table is **an example policy**, not Spring Batch defaults. Real applications must agree on thresholds and consequences for each rule.

---

## 4. Designing the Domain Model and Rule Context

Start with strongly typed models rather than passing `Map<String,Object>` through every layer.

### 4.1. Immutable Input and Output Models

Java 17 supports `record`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record OrderRow(
    String externalOrderId,
    BigDecimal amount,
    String currency,
    String status,
    LocalDate businessDate
) {}

public record ApprovedOrder(
    String externalOrderId,
    BigDecimal amount,
    String currency,
    LocalDate businessDate
) {}
```

Input may be unnormalized; output represents data conforming to the writer's contract. Never mutate the input object in place inside the processor if that same object is used by retries, logs, skip listeners, or other delegates. Returning a fresh object makes data flow easier to test.

### 4.2. Rule Snapshot for a Single Run

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Set;

public record OrderRuleContext(
    LocalDate businessDate,
    BigDecimal maxAutoApprovedAmount,
    Set<String> allowedCurrencies,
    String ruleVersion
) {
    public OrderRuleContext {
        allowedCurrencies = Set.copyOf(allowedCurrencies);
    }
}
```

The context holds **the rule values chosen for this run**, not a live database connection or repository. Snapshotting configuration ensures items within an execution are evaluated under consistent policy.

If a system must restart after a deployment that changed rules, `ruleVersion` is an essential part of the contract. Decide upfront **whether restarts use the old rule snapshot or apply new rules**, because changing evaluation outcomes between runs can leave inconsistent data.

---

## 5. Example Processor Evaluating Business Rules

### 5.1. Exception with a Stable Rule Code

Instead of throwing `IllegalArgumentException("bad data")` for everything, throw an exception carrying a **stable rule code**:

```java
public final class BusinessRuleViolationException
        extends RuntimeException {

    private final String ruleCode;
    private final String externalOrderId;

    public BusinessRuleViolationException(
            String ruleCode,
            String externalOrderId,
            String message) {

        super(message);
        this.ruleCode = ruleCode;
        this.externalOrderId = externalOrderId;
    }

    public String getRuleCode() {
        return ruleCode;
    }

    public String getExternalOrderId() {
        return externalOrderId;
    }
}
```

`ruleCode` is the contract with dashboards, logs, rejection tables, and tests. Never put sensitive data or full raw payloads into exception messages.

### 5.2. Complete Processor

This example filters `CANCELLED` orders out of the import set, rejects rule-violating orders, and normalizes currency before writing.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

import org.springframework.batch.item.ItemProcessor;

public final class OrderBusinessRuleProcessor
        implements ItemProcessor<OrderRow, ApprovedOrder> {

    private final OrderRuleContext rules;

    public OrderBusinessRuleProcessor(OrderRuleContext rules) {
        this.rules = rules;
    }

    @Override
    public ApprovedOrder process(OrderRow item) {

        if (item == null) {
            throw violation(
                "INPUT_NULL", null, "Input order is null");
        }

        String id = item.externalOrderId();
        if (id == null || id.isBlank()) {
            throw violation(
                "ORDER_ID_REQUIRED", id, "Order ID is required");
        }
        id = id.trim();

        String status = item.status() == null
            ? ""
            : item.status().trim().toUpperCase(Locale.ROOT);

        // Only filter statuses defined by the business contract.
        if ("CANCELLED".equals(status)) {
            return null;
        }

        if (!"READY".equals(status)) {
            throw violation(
                "STATUS_UNSUPPORTED", id,
                "Status is not eligible for import");
        }

        if (item.amount() == null ||
                item.amount().signum() <= 0) {
            throw violation(
                "AMOUNT_NON_POSITIVE", id,
                "Order amount must be positive");
        }

        String currency = item.currency() == null
            ? ""
            : item.currency().trim().toUpperCase(Locale.ROOT);

        if (!rules.allowedCurrencies().contains(currency)) {
            throw violation(
                "CURRENCY_UNSUPPORTED", id,
                "Currency is not supported");
        }

        if (item.businessDate() == null ||
            !rules.businessDate().equals(item.businessDate())) {
            throw violation(
                "DATE_OUT_OF_SCOPE", id,
                "Business date does not match this job");
        }

        // Never silently round a monetary value with invalid precision.
        BigDecimal amount;
        try {
            amount = item.amount().setScale(
                2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw violation(
                "AMOUNT_SCALE", id,
                "Amount has unsupported decimal precision");
        }

        if (amount.compareTo(
                rules.maxAutoApprovedAmount()) > 0) {
            throw violation(
                "AMOUNT_REVIEW_REQUIRED", id,
                "Order must be reviewed before import");
        }

        return new ApprovedOrder(
            id, amount, currency, item.businessDate());
    }

    private static BusinessRuleViolationException violation(
            String code,
            String id,
            String message) {
        return new BusinessRuleViolationException(
            code, id, message);
    }
}
```

This illustrates an "**accepted / filtered / exception**" processor. Orders needing manual review currently throw an exception; if the business requires durable manual-review records, merely skipping does not create a record. Section 9 introduces the more suitable **decision object + routing writer** variant.

### 5.3. Why Evaluate Rules in That Order?

Ordering is part of the contract:

1. Extract ID so subsequent errors attach to the record.
2. Recognize valid out-of-scope statuses and filter intentionally.
3. Reject unsupported statuses.
4. Check amount, currency, and date.
5. Normalize money without silent rounding.
6. Apply approval threshold.
7. Build the new output.

An item can violate multiple rules simultaneously. The **fail-fast** approach above reports the first violation. If you need to report every error on a record, return a validation result holding a list of violations instead of throwing on the first check. This choice directly affects source-data remediation UX and violation metrics.

### 5.4. Adjusting Filter and Validation Order

Here `CANCELLED` is filtered **before** checking amount. Thus a canceled order with a negative amount never appears in `AMOUNT_NON_POSITIVE` stats. That is fine if canceled orders are outside amount auditing, yet wrong for a program measuring data quality across the **entire feed**.

If all input errors must be reported, validate before filtering or record an independent audit stream. Explicitly define which population data quality KPIs cover: the whole source or only business-eligible records.

---

## 6. Unit Testing the Processor

Pure-Java business rules should be tested before booting a full Spring context. This cuts run time and pinpoints causes when rules change.

### 6.1. Fixture

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Set;

final class OrderFixtures {

    static OrderRuleContext rules() {
        return new OrderRuleContext(
            LocalDate.of(2026, 11, 16),
            new BigDecimal("1000000.00"),
            Set.of("VND", "USD"),
            "rules-2026-11"
        );
    }

    static OrderRow valid() {
        return new OrderRow(
            "  ORDER-001  ",
            new BigDecimal("125.50"),
            " usd ",
            "READY",
            LocalDate.of(2026, 11, 16)
        );
    }
}
```

### 6.2. JUnit 5 Covering Decision Branches

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderBusinessRuleProcessorTest {

    private final OrderBusinessRuleProcessor processor =
        new OrderBusinessRuleProcessor(OrderFixtures.rules());

    @Test
    void normalizesAndApprovesValidOrder() {
        ApprovedOrder actual =
            processor.process(OrderFixtures.valid());

        assertNotNull(actual);
        assertEquals("ORDER-001", actual.externalOrderId());
        assertEquals("USD", actual.currency());
        assertEquals(
            new BigDecimal("125.50"),
            actual.amount());
    }

    @Test
    void filtersCancelledOrder() {
        OrderRow cancelled = new OrderRow(
            "ORDER-C",
            new BigDecimal("50.00"),
            "USD",
            "CANCELLED",
            LocalDate.of(2026, 11, 16));

        assertNull(processor.process(cancelled));
    }

    @Test
    void rejectsZeroAmountWithStableCode() {
        OrderRow invalid = new OrderRow(
            "ORDER-Z",
            BigDecimal.ZERO,
            "USD",
            "READY",
            LocalDate.of(2026, 11, 16));

        BusinessRuleViolationException exception =
            assertThrows(
                BusinessRuleViolationException.class,
                () -> processor.process(invalid));

        assertEquals(
            "AMOUNT_NON_POSITIVE",
            exception.getRuleCode());
    }

    @Test
    void requiresReviewAboveThreshold() {
        OrderRow large = new OrderRow(
            "ORDER-L",
            new BigDecimal("1000000.01"),
            "USD",
            "READY",
            LocalDate.of(2026, 11, 16));

        BusinessRuleViolationException exception =
            assertThrows(
                BusinessRuleViolationException.class,
                () -> processor.process(large));

        assertEquals(
            "AMOUNT_REVIEW_REQUIRED",
            exception.getRuleCode());
    }

    @Test
    void neverSilentlyRoundsAmount() {
        OrderRow extraPrecision = new OrderRow(
            "ORDER-P",
            new BigDecimal("10.005"),
            "USD",
            "READY",
            LocalDate.of(2026, 11, 16));

        BusinessRuleViolationException exception =
            assertThrows(
                BusinessRuleViolationException.class,
                () -> processor.process(extraPrecision));

        assertEquals(
            "AMOUNT_SCALE",
            exception.getRuleCode());
    }
}
```

These tests verify the item-level business rule contract: transformations, filtering, error codes, and thresholds. They do not prove skip policies, transactions, quarantine persistence, or rollbacks across the whole step; those require integration tests.

### 6.3. Boundary Testing Matters More Than Mid-Range Values

For `amount > 0` and `amount <= max`, test cases should include:

- Null.
- `0` and negative numbers.
- Very small positive values.
- Exact maximum threshold.
- Threshold plus one smallest permitted unit.
- Scale exceeding permitted precision.
- Abnormally large values or precision exceeding database column limits.

For business dates, test before, on, and after the period. For currency/status, test lowercase, whitespace, null, and codes outside the allowlist. When inputs involve Unicode/encoding, do not assume `trim()` handles every whitespace character or business normalization.

---

## 7. Composing Multiple Rules in a Structured Pipeline

A processor hundreds of lines long with mixed responsibilities is hard to follow. A common pattern splits logic into stages:

```text
RawOrder
   |
   v
BasicValidationProcessor
   |
   v
CanonicalizationProcessor
   |
   v
BusinessEligibilityProcessor
   |
   v
RiskClassificationProcessor
   |
   v
ApprovedOrder / Decision
```

Spring Batch provides `CompositeItemProcessor` to chain multiple `ItemProcessor`s in order. Each delegate's output type must match the next delegate's input type.

### 7.1. Composite Processor Example

```java
import java.util.List;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.support.CompositeItemProcessor;

ItemProcessor<OrderRow, OrderRow> normalize = item ->
    new OrderRow(
        item.externalOrderId() == null
            ? null : item.externalOrderId().trim(),
        item.amount(),
        item.currency() == null
            ? null : item.currency().trim(),
        item.status() == null
            ? null : item.status().trim(),
        item.businessDate());

ItemProcessor<OrderRow, ApprovedOrder> business =
    new OrderBusinessRuleProcessor(rules);

CompositeItemProcessor<OrderRow, ApprovedOrder> pipeline =
    new CompositeItemProcessor<>();

pipeline.setDelegates(List.of(normalize, business));
```

`rules` in the example is the `OrderRuleContext` built for the job. Delegates run in list order. If an earlier delegate returns `null` to filter an item, the composite stops and does not pass that item to subsequent delegates.

**State note:** if a delegate implements `ItemStream`, ensure `open/update/close` lifecycle callbacks are invoked properly under your version and wrapper/composite wiring. Some composites/delegates may not automatically register streams under every wiring pattern; missing checkpoints often surface only during restarts.

### 7.2. When Do You Need Dedicated Rule Classes?

When rules have many variants requiring metadata and versioning, you can use a contract:

```java
public interface BusinessRule<T> {
    String code();
    RuleOutcome evaluate(T item, RuleContext context);
}
```

`RuleOutcome` and `RuleContext` are project-defined domain types. A `RuleEngine` runs a list of rules in order, returning an outcome or a set of violations. This approach helps:

- Add/remove rules cleanly.
- Unit-test each rule independently.
- Toggle rules by policy version or tenant.
- Attach codes/severities and observe outcomes.
- Keep validation, persistence, and retry decisions out of one monolithic class.

Still, do not build an over-engineered rule engine just to replace a few simple conditions. Architecture should match rule count, churn rate, and audit requirements.

---

## 8. Bean Validation and `ValidatingItemProcessor`

Spring Batch includes validation tools usable before or within the business processor.

### 8.1. `ValidatingItemProcessor`

A Spring Batch `Validator<T>` inspects an item and throws `ValidationException` when invalid:

```java
import org.springframework.batch.item.validator.ValidationException;
import org.springframework.batch.item.validator.Validator;

Validator<OrderRow> basicValidator = row -> {
    if (row == null ||
        row.externalOrderId() == null ||
        row.externalOrderId().isBlank()) {

        throw new ValidationException(
            "externalOrderId is required");
    }
};
```

Used with `ValidatingItemProcessor`:

```java
import org.springframework.batch.item.validator.ValidatingItemProcessor;

ValidatingItemProcessor<OrderRow> basicValidation =
    new ValidatingItemProcessor<>(basicValidator);

// Do not filter by default; ValidationException propagates.
basicValidation.setFilter(false);
```

You can then insert `basicValidation` into `CompositeItemProcessor` ahead of the business stage.

If `setFilter(true)` is set, failing items return `null` and count as **filtered**, not skipped. Enable this only when silent dropping matches business intent; if auditing invalid records is required, retain violations and route to quarantine.

### 8.2. Bean Validation (Jakarta Validation)

With Spring Boot 3.x, you can use:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Model:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;

public record ImportDto(
    @NotBlank String externalOrderId,
    @NotNull @Positive BigDecimal amount,
    @NotBlank String currency
) {}
```

Spring Batch provides `BeanValidatingItemProcessor<T>` to enforce Jakarta Bean Validation constraints on items when matching validation infrastructure is configured. Annotations like `@NotBlank` or `@Positive` work well for common field checks, while cross-field, tenant-specific, business-date, or policy-version rules usually need a dedicated processor/domain service.

**Do not equate annotations with a complete data quality contract.** `@Positive` cannot tell whether an amount exceeds a tenant's approval limit.

### 8.3. Ordering Validators and Business Rules

A sensible pipeline is:

```text
Parse input
   -> validate required fields and basic types
   -> normalize values
   -> business rules / eligibility
   -> classify accepted / rejected / review
   -> writer
```

If a rule expects normalized values (such as uppercase currency), normalization must run before that rule. When original data must be preserved for audits, keep both raw and canonical values in the decision or audit record; never overwrite raw payloads losing traceability.

---

## 9. When Not to Return `null`: Decision Objects and Quarantine

Suppose the batch must persist every item with an explicit decision:

- Valid: write to `approved_orders`.
- Rule violation: write to `rejected_orders` with the rule code.
- Over limit: write to `manual_review_queue`.

If the processor merely returns `null` for invalid items, the writer never sees them. `SkipListener` can log, yet does not automatically guarantee a transactionally consistent durable audit record.

### 9.1. Decision Model

Java 17 uses `sealed interface` and `record`:

```java
public sealed interface OrderDecision
        permits AcceptedDecision,
                RejectedDecision,
                ReviewDecision {
}

public record AcceptedDecision(
    ApprovedOrder order) implements OrderDecision {
}

public record RejectedDecision(
    String externalOrderId,
    String ruleCode,
    String ruleVersion) implements OrderDecision {
}

public record ReviewDecision(
    String externalOrderId,
    String reasonCode,
    String ruleVersion) implements OrderDecision {
}
```

Instead of throwing exceptions for violations meant for quarantine, the processor can return a decision:

```java
public final class ClassifyingOrderProcessor
        implements ItemProcessor<OrderRow, OrderDecision> {

    private final OrderRuleContext rules;

    public ClassifyingOrderProcessor(OrderRuleContext rules) {
        this.rules = rules;
    }

    @Override
    public OrderDecision process(OrderRow row) {

        if (row == null ||
            row.externalOrderId() == null ||
            row.externalOrderId().isBlank()) {
            return new RejectedDecision(
                null, "ORDER_ID_REQUIRED", rules.ruleVersion());
        }

        if (row.amount() == null ||
            row.amount().signum() <= 0) {
            return new RejectedDecision(
                row.externalOrderId(),
                "AMOUNT_NON_POSITIVE",
                rules.ruleVersion());
        }

        if (row.amount().compareTo(
                rules.maxAutoApprovedAmount()) > 0) {
            return new ReviewDecision(
                row.externalOrderId(),
                "AMOUNT_REVIEW_REQUIRED",
                rules.ruleVersion());
        }

        if (!rules.businessDate().equals(
                row.businessDate())) {
            return new RejectedDecision(
                row.externalOrderId(),
                "DATE_OUT_OF_SCOPE", rules.ruleVersion());
        }

        return new AcceptedDecision(new ApprovedOrder(
            row.externalOrderId(),
            row.amount(),
            row.currency(),
            row.businessDate()));
    }
}
```

This example demonstrates **classification** and does not share the full rule set of `OrderBusinessRuleProcessor` in section 5. In real systems, reuse shared rule/domain validation and handle `CANCELLED`/unsupported currencies explicitly; avoid accidentally running two divergent policies.

### 9.2. Routing Writer for Multiple Outcomes

An `ItemWriter<OrderDecision>` can split items by type and delegate to specialized writers:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

public final class OrderDecisionWriter
        implements ItemWriter<OrderDecision> {

    private final ItemWriter<ApprovedOrder> approvedWriter;
    private final ItemWriter<RejectedDecision> rejectedWriter;
    private final ItemWriter<ReviewDecision> reviewWriter;

    public OrderDecisionWriter(
            ItemWriter<ApprovedOrder> approvedWriter,
            ItemWriter<RejectedDecision> rejectedWriter,
            ItemWriter<ReviewDecision> reviewWriter) {
        this.approvedWriter = approvedWriter;
        this.rejectedWriter = rejectedWriter;
        this.reviewWriter = reviewWriter;
    }

    @Override
    public void write(Chunk<? extends OrderDecision> chunk)
            throws Exception {

        List<ApprovedOrder> approved = new ArrayList<>();
        List<RejectedDecision> rejected = new ArrayList<>();
        List<ReviewDecision> review = new ArrayList<>();

        for (OrderDecision decision : chunk.getItems()) {

            if (decision instanceof AcceptedDecision accepted) {
                approved.add(accepted.order());

            } else if (
                decision instanceof RejectedDecision invalid) {
                rejected.add(invalid);

            } else if (
                decision instanceof ReviewDecision pendingReview) {
                review.add(pendingReview);
            }
        }

        if (!approved.isEmpty()) {
            approvedWriter.write(new Chunk<>(approved));
        }

        if (!rejected.isEmpty()) {
            rejectedWriter.write(new Chunk<>(rejected));
        }

        if (!review.isEmpty()) {
            reviewWriter.write(new Chunk<>(review));
        }
    }
}
```

If all three delegate writers are JDBC writers sharing the **same transaction manager and datasource** as the chunk step, they participate in one transaction so accepted/rejected/review rows stay consistent on rollback. If they write to three separate databases or call HTTP, **there is no automatic atomicity**; design idempotency, outboxes, or reconciliation separately.

**Metadata counts:** Spring Batch's `writeCount` for a step writing `OrderDecision` counts **decision items passed through the writer**, not strictly approved orders. To know accepted/rejected/review counts, query dedicated tables/metrics. Never treat `writeCount` as approved orders in this routing design.

### 9.3. What Should Quarantine Store?

A rejected record may require:

| Field | Role |
| --- | --- |
| Source system / file / batch ID | Trace origin |
| Business key or source line ID | Identify record |
| Rule code | Stable error classification |
| Rule version | Identify applied policy |
| Original value / sanitized payload | Support controlled fixing and reprocessing |
| JobInstance / Execution ID | Correlate execution and audit |
| First seen / last seen | Track history |
| Resolution status | `NEW`, `FIXED`, `WAIVED`, `REPROCESSED`, etc. |

Store only necessary data with explicit security and retention rules; keep PII/secrets out of uncontrolled logs, metric tags, or exception strings.

---

## 10. Configuring a Fault-Tolerant Step: Bounded Skip

When policy permits skipping some invalid records instead of writing them via a routing writer, use Spring Batch fault tolerance.

### 10.1. Spring Batch 5.x Example

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, ApprovedOrder> processor,
        ItemWriter<ApprovedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, ApprovedOrder>chunk(
            100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(BusinessRuleViolationException.class)
        .skipLimit(50)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
```

Key semantics to remember:

- `.skip(BusinessRuleViolationException.class)` lets the step skip that exception type within the limit.
- `.skipLimit(50)` caps total skips for the step under Spring Batch policy, not 50 per error type.
- When a processor exception is skipped, `processSkipCount` increments per the framework.
- If errors exceed the limit, the step fails.
- `.retry(TransientDataAccessException.class)` targets transient resource failures; tune the classifier for your JDBC driver and domain.
- Never include `BusinessRuleViolationException` in default retries: the same input and rule snapshot will usually keep failing.

**Careful consideration:** in the section 5 example, `AMOUNT_REVIEW_REQUIRED` is also a `BusinessRuleViolationException`. With a broad skip setting, orders needing review would **be skipped** without entering a manual review queue. If that is unacceptable, use separate exception subclasses and a classifying skip policy, or switch to decision routing as in section 9.

### 10.2. Is `skipLimit` a Data Quality KPI?

No. `skipLimit` is a **step circuit-breaker**, preventing a badly broken feed from skipping indefinitely. A system often needs a percentage threshold, such as at most 0.1% invalid records, rather than a static integer.

To enforce ratios, compute errors against a clearly defined denominator (raw records, parsed records, or eligible records), then evaluate the rule in a summary step or dedicated quality gate. An in-processor counter is unreliable under rollbacks, retries, or parallel execution.

### 10.3. `SkipListener` and Error Recording

Spring Batch provides `SkipListener<I,O>` with callbacks such as:

```java
import org.springframework.batch.core.SkipListener;

public final class OrderSkipObserver
        implements SkipListener<OrderRow, ApprovedOrder> {

    @Override
    public void onSkipInProcess(
            OrderRow item, Throwable throwable) {

        if (throwable
                instanceof BusinessRuleViolationException violation) {
            // Observe the rule code for audit/metrics.
            // Never blindly call external APIs.
            String code = violation.getRuleCode();
        }
    }
}
```

Register with the builder via `.listener(new OrderSkipObserver())` on the fault-tolerant step. `SkipListener` is useful for knowing an item was skipped, yet **is not an automatic exactly-once mechanism for arbitrary side effects**. If the callback writes to an external database/queue outside the active transaction and the step rolls back or restarts, audit data can duplicate or drift.

If every invalid record requires durable evidence consistent with chunk outcomes, use a routing writer in the same transaction or an outbox with an explicit idempotency key.

### 10.4. Errors That Must Never Be Skipped

- Database connection loss.
- Output mapping errors causing the entire writer to fail.
- Metadata repository persistence failures.
- Rule version configuration errors.
- Code bugs such as `NullPointerException`.
- Critical data quality gate breaches requiring halting the batch to fix the source.

Configuring `.skip(Exception.class)` can let a job report `COMPLETED` even while dropping massive amounts of data and hiding infra outages. Skip only exception types permitted by business contract, with proper thresholds and auditing.

---

## 11. Write Rules as Pure, Deterministic Functions

### 11.1. Retries and Restarts Can Invoke the Processor Multiple Times

In chunk processing, an item can be reprocessed upon transaction rollbacks, fault-tolerant retries, or job restarts:

```text
Chunk:
  read item 101
  process item 101 -> approved
  write(chunk)     -> database error
  transaction      -> ROLLBACK

Restart/retry:
  read item 101 (or reprocess cached item)
  process item 101 -> must produce compatible result
  write(chunk)     -> retry / commit
```

If the processor causes side effects—sending emails, calling payment APIs, writing non-transactional audit logs, or incrementing business-impacting counters—retries can duplicate those actions.

**Preferred design:**

```text
Business processor:
  result = f(input item, immutable rule context)
  no external writes
  no notifications sent
  no identifying UUIDs generated per process call
  no dependence on global mutable state
```

Necessary I/O should happen in a transaction-managed step or a service with controlled retry/idempotency semantics.

### 11.2. Avoid Calling `LocalDate.now()` Directly in Rules

Suppose an import job runs on the 16th and restarts on the 17th. If a business rule compares input dates against `LocalDate.now()`, the same item may pass on the 16th and fail on the 17th.

Instead of:

```java
if (!item.businessDate().equals(LocalDate.now())) {
    return null;
}
```

Pass the **`JobInstance`'s business date** as a stable parameter:

```java
new OrderRuleContext(
    LocalDate.parse(jobBusinessDate),
    maxAmount,
    allowedCurrencies,
    ruleVersion
);
```

If a rule genuinely depends on wall-clock time, define a contract `Clock` or cutoff instant snapshot, recording it in metadata/`JobParameters` so restarts never silently flip decisions.

### 11.3. External Reference Data Needs Snapshots or Versions

For example, a rule "customer has an active account" queries another service. If customer status changes between the initial run and a restart, outcomes can differ for the same input.

Strategies:

- Prefetch/snapshot reference tables at job start per data period.
- Query using a version or effective-at timestamp.
- Cache with appropriate keys, TTLs, and explicit invalidation.
- For rules that truly must evaluate against the latest state, specify re-evaluation semantics on restart clearly.
- Add tests for consistency when rule configs or reference data change between executions.

A processor reading reference data once into a mutable singleton field can also leak state across jobs or tenants. Design bean scopes and context isolation properly.

---

## 12. JobParameters, Rule Version, and `@StepScope`

### 12.1. Passing Business Date into the Processor

With Spring Boot 3 and Spring Batch 5, create a step-scoped processor:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Set;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderProcessorConfiguration {

    @Bean
    @StepScope
    ItemProcessor<OrderRow, ApprovedOrder> orderProcessor(
            @Value("#{jobParameters['businessDate']}")
            String businessDate,
            @Value("#{jobParameters['ruleVersion']}")
            String ruleVersion) {

        OrderRuleContext context = new OrderRuleContext(
            LocalDate.parse(businessDate),
            new BigDecimal("1000000.00"),
            Set.of("USD", "VND"),
            ruleVersion
        );

        return new OrderBusinessRuleProcessor(context);
    }
}
```

`@StepScope` creates a proxy bean resolving `jobParameters` when the step execution actually runs, not at application startup. This example assumes both parameters are present and properly formatted; production code should validate `JobParameters` before the job launches.

### 12.2. Identifying vs. Non-Identifying Parameters

Spring Batch uses job name and **identifying JobParameters** to identify a `JobInstance`. Choices:

- `businessDate` is usually identifying because each date starts a new logical processing run.
- `tenantId` can be identifying if jobs run per tenant.
- Whether `ruleVersion` is identifying depends on the contract: if changing version means a new run, document it; if restarts must preserve old rules, never silently swap versions or read "latest" config.
- `traceId` is usually non-identifying; changing a trace ID should not create a separate `JobInstance`.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("tenantId", "TENANT-A", true)
    .addString("ruleVersion", "rules-2026-11", false)
    .addString("traceId", "trace-63829", false)
    .toJobParameters();
```

**Important note:** `non-identifying` does not mean free to change arbitrarily when restarting via `JobOperator`; Spring Batch restarts rely on the parameters and metadata of the original instance/execution. Stability of rule configuration must be enforced via deployment/version policies and snapshots, not merely `identifying=false`.

### 12.3. When Rules Change Between Runs

A job fails while rule version A is active; the next day production deploys version B. The system needs a policy:

| Policy | Approach | Trade-off |
| --- | --- | --- |
| Freeze rule snapshot | Store version and run matching logic on restart | Must keep/maintain older rule versions |
| Re-evaluate under new policy | Allow processor to run version B | Requires reconciliation; risks differing from prior chunks |
| Forbid restart across breaking rule changes | Reject restart; require migration/reprocess | Safer when contracts change drastically |

Never assume swapping a JAR lets you safely restart every failed job without verifying rule-code, input/output schema, and `ExecutionContext` compatibility.

---

## 13. Cross-Item Rules: Why Not Store State in One Processor?

Some rules go beyond single items:

- No two orders share a business key in the same file.
- Batch-wide amount total must match header/trailer.
- One customer cannot exceed N transactions per day.
- Every file must have complete sequence numbers.
- Two records from different sources must match before publishing a report.

A processor holding a mutable `Map`/`Set` to count or track seen IDs runs into trouble:

1. On rollback/retry, the same item is reprocessed and falsely flagged as duplicate.
2. On JVM restart, in-memory state is lost.
3. In multi-threaded steps, mutable maps suffer race conditions.
4. With partitioning, each partition cannot see other partitions' data.
5. Large datasets can exhaust heap memory.

### 13.1. Alternative Approaches

| Rule | Typically Suitable Approach |
| --- | --- |
| Business key unique across all target data | Unique constraint + idempotent upsert / reject policy |
| Duplicates within one input file | Staging table with unique key per source file; SQL query/aggregation |
| Total amount must match trailer | Aggregation step or post-load reconciliation step |
| Daily per-customer transaction cap | Transactional query/aggregation over snapshotted data |
| Cross-entity relationships | Validate in staging or dedicated join/match step |
| Risk scores needing history | Domain rule service reading snapshotted/versioned reference data |

A per-item processor can still call a domain service for eligibility checks, provided cross-item accuracy accounts for consistency, concurrency, and transaction semantics where the service reads state.

### 13.2. Why Database Constraints Must Still Exist

Even if the processor checks that an external order ID is absent from the database, two parallel Batch executions can both check "absent" and then both insert. Only a database unique constraint can arbitrate concurrency at the end. Processor validation improves error messages; it **never replaces** constraints.

---

## 14. Data Quality Gates: Per-Record Errors vs. Batch-Wide Failures

Some workflows tolerate up to 0.5% bad items; others must **halt the whole job if even one record violates a rule**.

### 14.1. Three Overall Policies

1. **Strict:** any critical violation marks the step `FAILED`; use when output cannot tolerate missing items.
2. **Tolerant with threshold:** allow skips/rejects within limits and finish with a usable result set.
3. **Quarantine + gate:** store rejected/review decisions, then evaluate total counts/ratios/critical rules in a later step to decide whether results may be published.

### 14.2. Ratio-Based Gates

Example:

```text
Raw rows parsed:             100,000
Eligible rows:                95,000
Rejected eligible rows:          250
Allowed invalid ratio:          0.2%

Observed ratio:
  250 / 95,000 = 0.2632%
  -> FAIL DATA QUALITY GATE
```

Define the denominator explicitly. If 5,000 canceled orders were validly filtered, the reject ratio over 100,000 raw records differs from the ratio over 95,000 eligible records. Never pick a denominator just to make KPIs look better.

### 14.3. Gate Timing Affects Business Outcomes

If Batch already wrote accepted records to production tables and a quality gate later fails, **a `FAILED` job does not automatically roll back previously committed chunks**. For batch-wide all-or-nothing workflows:

```text
Reader -> Processor -> staging tables
                  |
                  v
          Quality reconciliation
                  |
          +-------+--------+
          |                |
        PASS             FAIL
          |                |
          v                v
     Publish/merge     Keep quarantine,
     from staging      do not publish
```

Staging/merging separates **loading and validating data** from **publishing valid data**. Depending on requirements, publishing can use an appropriately scoped transaction or a version/pointer swap, rather than hoping one giant transaction spans all chunks.

---

## 15. Business Rules and Transactions/Restarts

### 15.1. What Happens When the Writer Fails?

A chunk has 100 input items; the processor accepted 96 and filtered 4. The writer hits a database error and the transaction rolls back. On retry/restart, the processor may re-run on some items depending on reader/step policies.

If the processor is a pure function with a stable rule context, the outcome stays 96 accepted and 4 filtered. If the processor increments a mutable counter as the source of truth, the counter increments twice and diverges from committed output.

### 15.2. In-Memory Counters Are Not Official Results

Code like:

```java
private long rejectedCount = 0;

public ApprovedOrder process(OrderRow row) {
    if (isInvalid(row)) {
        rejectedCount++; // May increment again on rollback/retry.
        return null;
    }
    return map(row);
}
```

is not a reliable measure of unique rejected records in batches with retries/restarts. Moreover, if a singleton processor bean is shared across executions, state can bleed across jobs.

Prefer:

- `StepExecution` counters for baseline visibility.
- Rejected/decision tables with **unique business keys** for durable audit counts.
- Post-execution SQL aggregations/queries for official KPIs.
- Micrometer counters for real-time observability while recognizing they count **invocations/attempts**, not necessarily unique records.
- If stateful processing is truly required, design `ItemStream`, checkpoints, thread safety, and rollback semantics explicitly.

### 15.3. Rule Processors Must Be Contractually Idempotent

Idempotency in a processor means the same input and immutable rule context always produce the same output without new side effects. **Writer idempotency** is a separate concern: writing the same approved item again must not create unintended duplicate outputs.

Systems need both whenever metadata checkpoints and business transactions do not commit atomically—especially when metadata and business databases are separate.

---

## 16. Audit Trails and Observability for Business Rules

### 16.1. Use Rule Codes, Not Just Free-Form Messages

An exception message may change when wording is tweaked, whereas `ruleCode` should maintain stable semantics:

```text
ruleCode=AMOUNT_NON_POSITIVE
ruleVersion=rules-2026-11
jobName=importOrdersJob
stepName=importOrdersStep
jobExecutionId=9221
sourceRecordId=ORDER-148
decision=REJECTED
```

This example log avoids sensitive information; real IDs must still follow your organization's data policies.

When a rule splits into two distinct rules or changes meaning, introduce a **new version/code**, rather than letting historical dashboards interpret the same code under two meanings.

### 16.2. Bounded-Cardinality Metrics

Suggested metrics (illustrative names, not built-in):

| Metric | Unit | Meaning |
| --- | --- | --- |
| `batch.rule.evaluations` | attempts | Number of rule evaluations |
| `batch.rule.violations` | attempts | Number of rule violations |
| `batch.rule.duration` | seconds | Rule/service latency |
| `batch.dataquality.rejected` | decisions | Count of rejected decisions |
| `batch.dataquality.review` | decisions | Count of review-required decisions |
| `batch.dataquality.gate_failed` | gates | Count of failed quality gates |
| `batch.dataquality.quarantine_backlog` | records | Count of unresolved records |

Restrict tags to `job.name`, `step.name`, `rule.code`, `rule.version`, and `decision` where value sets are small and bounded. **Never put `externalOrderId`, raw amounts, customer emails, or `jobExecutionId` into metric tags** due to high cardinality and data exposure risks.

### 16.3. Rule Evaluation Latency

A business rule comparing `BigDecimal`s is very fast. A rule making per-item HTTP/DB calls can become a severe bottleneck:

```text
100,000 items
  * 1 remote check per item
  * 20 ms average/check
  = ~2,000 seconds sequential wait
```

This is a linear estimate for sequential processing before accounting for network variance, caching, concurrency, and retries. To optimize:

- Preload small reference tables per rule version.
- Batch lookups instead of N+1 queries.
- Cache with proper keys, TTLs, and invalidation.
- Use business-date reference snapshots.
- Enforce timeouts and retries on remote rule services.
- Under parallelism, verify the service handles the request rate and rules hold no mutable state.

Never sacrifice rule correctness purely for throughput; stale caches may be acceptable for display rules yet unacceptable for compliance rules.

---

## 17. Bad Data, Security, and Rule Change Governance

### 17.1. Controlled Storage of Rejected Data

Quarantine tables may hold raw payloads to aid fixing errors. Yet raw payloads can include customer IDs, financial details, addresses, or tokens that must not sit around indefinitely.

Enforce:

- Data classification and retention policies.
- Access controls so operators only view data within their scope.
- Audit logs of edits, waivers, and reprocessing actions.
- Masking/encryption for sensitive data.
- Exclusion of full payloads from exception messages and metric labels.
- Field minimization—storing only fields genuinely required for remediation.

### 17.2. Managing Rule Changes

Externally configured rules need a lifecycle:

```text
DRAFT
  -> REVIEWED
  -> APPROVED
  -> EFFECTIVE(version, timestamp)
  -> RETIRED
```

When a batch runs, log `ruleVersion`/effective instant. Never let users edit threshold configs mid-run so half a file uses rule A and the other half uses rule B, unless explicitly designed as a requirement.

### 17.3. Reprocessing Rejected Records

Once source data is fixed, you typically need to:

1. Identify rejected records/slots and the old rule version.
2. Select new inputs or corrected data with edit auditing.
3. Decide whether to rerun a `JobInstance`, run a dedicated remediation job, or start a new ingestion.
4. Use business keys/unique constraints to prevent rewriting already-accepted records.
5. Reconcile output and update quarantine statuses.

**Do not assume restarting a `COMPLETED` `JobInstance` will reprocess filtered/skipped items.** Completed jobs cannot restart under normal mechanics. Remediation may require a new job or a separate workflow branch.

---

## 18. Integration Testing Business Rules in a Chunk Step

Unit tests prove processor logic, yet step-level tests must verify filter/skip/writer semantics.

### 18.1. Expected Fixture

Suppose a test file has 6 items:

| ID | Status | Amount | Outcome |
| --- | --- | ---: | --- |
| A | READY | 100 | Accepted |
| B | CANCELLED | 50 | Filtered |
| C | READY | 0 | Rejected/Skipped per policy |
| D | READY | 200 | Accepted |
| E | READY | 10.005 | Rejected/Skipped |
| F | READY | 300 | Accepted |

With a step configured with `skip(BusinessRuleViolationException.class)`, `skipLimit(2)`, and a writer receiving only `ApprovedOrder`:

- `readCount` expected: 6 if the input fixture has no read failures.
- `filterCount` expected: 1 for B.
- `processSkipCount` expected: 2 for C and E.
- `writeCount` expected: 3 for A, D, and F if the writer succeeds.
- `JobExecution` `COMPLETED` if no other errors occur.

These values apply to this fixture in a synchronous step with no special retries/rollbacks. Tests should read the persisted `StepExecution` from the repository rather than inspecting in-memory processor counters alone.

### 18.2. Assertion Skeleton

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;

import static org.junit.jupiter.api.Assertions.*;

JobExecution execution =
    jobLauncherTestUtils.launchJob(uniqueParameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution step = execution.getStepExecutions().stream()
    .filter(s -> "importOrdersStep".equals(s.getStepName()))
    .findFirst()
    .orElseThrow();

assertEquals(6L, step.getReadCount());
assertEquals(1L, step.getFilterCount());
assertEquals(2L, step.getProcessSkipCount());
assertEquals(3L, step.getWriteCount());
```

This is an **assertion skeleton** inside an integration test configured with `@SpringBatchTest`, `@SpringBootTest`, `JobRepository`, `JobLauncher`, and reader/processor/writer beans. `uniqueParameters` is a test-fixture `JobParameters` variable, not built-in to Spring Batch.

If using a decision-routing writer instead of skip/filter, expected counters **differ** because rejected/review decisions still reach the writer. Base tests on the chosen contract rather than copying assertions from a different strategy.

### 18.3. Testing Exceeding the Skip Limit

Add a third business-violating item G when `skipLimit(2)` is already reached. Processing must reflect the threshold policy: the step fails instead of skipping infinitely.

Inspect final status, exception/cause, and chunks committed prior to failure. Because chunk processing has transaction boundaries, job `FAILED` does not roll back earlier committed chunks. If partial output must never be published, use staging + quality gate + publish steps.

### 18.4. Testing Retry/Restart

Fail the writer after committing some chunks, then restart the job with the same identifying parameters. Assert:

- The processor creates no duplicate external side effects.
- Rule decisions on reprocessed items stay consistent under the same rule snapshot.
- The reader restores checkpoints properly.
- Accepted output has no duplicates and quarantine data holds unique keys.
- Final data quality totals count **unique records**, not attempts.

### 18.5. Multi-Threaded Steps

If a processor uses an `AtomicInteger` to count violations or a mutable `HashSet` to deduplicate, single-threaded unit tests will miss race conditions. For multi-threaded/partitioned steps:

- Rule contexts must be immutable and thread-safe.
- Metrics registries must be thread-safe.
- Never keep per-item ordering state unless synchronization and checkpointing are explicitly designed.
- Enforce uniqueness in the database or staging layer.
- Test concurrency and partition boundaries with representative datasets.

---

## 19. Design Patterns and Common Pitfalls

| Pattern / Pitfall | Consequence | Fix |
| --- | --- | --- |
| Returning `null` for all invalid data | Loses rejection trail; only `filterCount` grows | Filter only truly out-of-scope items; use skip/quarantine for errors |
| Throwing generic `RuntimeException` | Hard to classify; risks wrong retry/skip | Use contractual exceptions/rule codes |
| `skip(Exception.class)` | Hides infra errors; missing output | Skip only allowed error types with thresholds |
| Sending emails / calling payment APIs in processor | Retries duplicate side effects | Move to writer/outbox/idempotent service |
| Using `LocalDate.now()` for business date | Restart on another day flips decisions | Use `JobParameters`/`Clock` snapshot |
| Fetching "latest" thresholds per item | One job runs mixed policies | Freeze rule version/context |
| Counting errors via mutable singleton field | Breaks on retries, parallelism, multiple jobs | Use step counters, unique decision ledger, SQL aggregation |
| Local `HashSet` deduplication | Breaks on restarts/partitions | Use unique keys / staging |
| Silent rounding of monetary amounts | Wrong amounts and broken audits | Explicit scale/rounding contract |
| Changing rule-code meaning without versioning | Historical dashboards become ambiguous | Version rules and audits |
| Filtering first then auditing full source | Artificially depressed data quality KPIs | Define eligible population / denominator explicitly |
| Writing quarantine via HTTP inside `SkipListener` | Audits can duplicate or drift | Routing writer in same transaction / outbox |
| Testing processor units only | Misses skip/rollback/wiring bugs | Chunk + `JobRepository` integration tests |
| Asserting only `JobExecution COMPLETED` | Items can vanish if skips are too permissive | Assert accepted/rejected counts and business output |
| Omitting unique constraints in writer | Two workers insert the same business key | Constraints + idempotent writes |
| Querying database per item in rules | N+1 queries, low throughput | Batch lookups / preload / cached snapshot |

### 19.1. A Decision Flow for Authoring a New Rule

```text
Input item
    |
    v
Valid parse/shape?
    | no
    +------> Reader mapping error / validation violation
    |
    v
Within business scope?
    | no
    +------> FILTER (if allowed by contract)
    |
    v
Can rule decide per item independently?
    | no
    +------> Staging / aggregate / cross-record validation
    |
    v
Does violation require an audit record?
    | yes
    +------> Decision REJECTED / REVIEW -> routing writer
    |
    v
Is violation skippable within threshold?
    | yes
    +------> BusinessRuleViolationException -> fault-tolerant skip
    |
    v
Critical violation?
    | yes
    +------> Fail step / quality gate
    |
    v
Accepted -> ItemWriter
```

This diagram shows business options, not a fixed order enforced by Spring Batch. A rule can also require both auditing **and** blocking publish; combine staging/decision routing with a quality gate.

---

## 20. Practice Exercises

### Exercise 1 — Order Rule Set Processor

Write `ItemProcessor<OrderRow, ApprovedOrder>` enforcing:

- Non-blank ID.
- `CANCELLED` status filtered.
- Any status other than `READY` is a violation.
- `Amount > 0`.
- Currency in configured allowlist.
- Business date equals import period.
- Amounts above threshold produce a review-required rule code.

Write unit tests for every branch and amount boundary.

### Exercise 2 — Composite Processor

Split the pipeline into normalize, validate, and business eligibility. Use `CompositeItemProcessor` to chain stages.

Requirement: prove downstream stages are skipped when an upstream stage filters an item, and output transformations match the next delegate's input type.

### Exercise 3 — Skip vs. Filter Differences

Use the 6-item fixture from section 18 with skip limit 2. Run an integration test and assert `readCount`, `filterCount`, `processSkipCount`, and `writeCount`.

Add a third violating item. Inspect step status and committed data, and explain why `filterCount` does not count toward `skipLimit`.

### Exercise 4 — Durable Quarantine

Change the processor to return `AcceptedDecision`, `RejectedDecision`, or `ReviewDecision`. Write a routing writer persisting to three tables with unique keys.

Requirement: when the writer throws and the chunk rolls back, no partial accepted/rejected/review records persist if all three tables share one transaction. Restart and prove zero duplicate decisions.

### Exercise 5 — Changing Rule Version Between Restarts

A job on the 16th runs with rule version A and fails at the second chunk. Then threshold config changes to version B.

Design a snapshot-freeze or migration policy; write tests proving the same input is handled consistently with the chosen restart contract.

### Exercise 6 — Data Quality Gate

A feed has 100,000 rows, 5,000 out-of-scope items, and 250 rejected eligible items. Maximum allowed invalid ratio is 0.2% of the eligible population.

Compute the actual ratio, design a gate step, and propose how to block sub-par output from reaching production tables.

### Exercise 7 — Cross-Record Rules

Two orders share the same external ID across two partitions. Prove a local `HashSet` in the processor fails to guarantee duplicate detection. Propose a staging unique constraint and concurrency integration test.

### Exercise 8 — Observability and Reporting

Design a dashboard showing total source records, eligible, accepted, filtered, skipped, rejected, manual-review, and KPIs by `ruleCode` and rule version. Specify denominators, unique-record counting rules, and how to avoid high-cardinality metric tags.

---

## 21. Checklist for Designing Processor Business Rules

Before deploying a processor to a real data pipeline, answer:

- Which document/decision table defines the rules, and who approves changes?
- Are input shape, reference data, and business date stable per run?
- Is an item's outcome accepted, filtered, rejected, sent to review, or a job failure?
- Does filtering strictly mean "out-of-scope item"?
- Which violations are skippable, what is the limit, and who handles skipped records?
- Is durable quarantine required within the same transaction?
- Do rules depend on other records, uniqueness, or batch totals?
- Does the processor avoid non-transactional side effects and stay deterministic across retries/restarts?
- Are rule versions/configs frozen and audited?
- Do metrics reflect unique decisions or only attempts?
- Have unit, integration, restart, and reconciliation tests verified the exact contract?

A reliable processor does more than emit "clean" data—it makes clear **why each item was accepted, excluded, or routed to manual handling**, and keeps those decisions consistent across the lifecycle of a Spring Batch job.

## 22. References

- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): `ItemProcessor`, filtering, and transformation.
- [Spring Batch Reference — Validating Input](https://docs.spring.io/spring-batch/reference/processor.html): validation in processing pipelines.
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunks and transaction boundaries.
- [Spring Batch Reference — Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): fault-tolerant skip configuration.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retries and backoff.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): saving/restoring state.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` and job/step testing utilities.
- [Spring Batch API — CompositeItemProcessor](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/support/CompositeItemProcessor.html): chaining processors sequentially.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraint validation.
