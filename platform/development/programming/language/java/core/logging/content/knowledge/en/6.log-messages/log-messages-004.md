# Stable Messages in Java Logging

## 1. What Does "Stable Message" Mean?

An application can write millions of log lines and still be difficult to search if the same type of event is described with many different sentences. For example, when a payment is declined:

```text
Order ORD-101 could not be paid because the card expired
Payment ORD-102 failed: card has expired
Unable to process payment for order ORD-103 (expired card)
```

Human readers understand that these sentences mean roughly the same thing, but search tools, analytics, or alerting systems may treat them as different text patterns. Embedding the order ID, reason, and wording in an ad-hoc way makes it hard to answer: "How many times were payments declined for the same reason?".

A **stable message** is an approach to designing log messages with a **consistent message template and meaning** for the same type of event; the variable parts are placed into **parameters or separate data fields**. For example:

```text
Template: event=payment_result order_id={0} outcome={1} reason_code={2}

Run 1: event=payment_result order_id=ORD-101 outcome=DECLINED reason_code=CARD_EXPIRED
Run 2: event=payment_result order_id=ORD-102 outcome=DECLINED reason_code=CARD_EXPIRED
Run 3: event=payment_result order_id=ORD-103 outcome=APPROVED reason_code=NONE
```

The structure and field names remain unchanged; the order value, outcome, and reason change per execution. Operators can filter by `event=payment_result` and then group by `outcome` or `reason_code`.

**Stability does not mean every log record must contain the exact same character string.** If the order ID changes, the formatted record naturally changes. What needs to remain stable is the *event type, message template, field names, and semantics of each field*. Events with different business meanings should still have their own appropriate names or templates.

This is a **log content design** topic within Java logging architecture; it relates to loggers, formatters, handlers/appenders, and log search systems, but the focus is on making each message readable, filterable, and aggregatable over the long term.

## 2. Distinguishing Log Templates, Formatted Messages, and Context Data

A log record typically has three layers of information:

1. **Message template:** the fixed part that the source code uses to describe the event, for example `"event=order_created order_id={0}"` in `java.util.logging`.
2. **Event parameters:** values that change per execution, for example `"ORD-101"`, `"ORD-102"`.
3. **Log metadata:** level `INFO`/`WARNING`, timestamp, logger name, thread, service name, correlation ID, etc. Some fields are added by the framework or collection system.

The flow of how a log line is formed can be visualized as follows:

```text
Application code calls Logger
    |
    +-- fixed template: "event=order_created order_id={0}"
    +-- parameters:     ["ORD-101"]
    +-- log level:      INFO
    |
    v
LogRecord (template, parameters, level, and metadata)
    |
    v
Formatter / Encoder
    |
    v
"INFO event=order_created order_id=ORD-101"
    |
    v
Console / File / Collection system
```

In this example, the final string contains specific values and therefore differs between requests. Keeping the template stable gives the source code a clear convention; keeping **structured fields** makes it easy for analytics systems to query.

**Note:** `key=value` logs inside a single string are not automatically true "structured logging". If the output is just plain text, the collector may have to use a parser to extract each field. With backends that support JSON or dedicated log event attribute fields, use that capability when stable querying is needed; do not concatenate JSON manually.

## 3. Why Are Stable Messages Useful?

### Easy to Search and Group Events

With a fixed event name such as `payment_result`, a query can filter all payment results, then look specifically at `outcome=DECLINED` and group by `reason_code`. If every code branch writes an arbitrary sentence, filtering rules must depend on many Vietnamese/English variations, punctuation, and phrasing.

### More Accurate Alerting

An alert rule can track the count of `reason_code=GATEWAY_TIMEOUT` within a given time window. A stable reason code is less affected when a developer changes the sentence "Kết nối cổng thanh toán thất bại" to "Lỗi gọi payment gateway". Alert conditions based on **fields and codes** are more reliable than conditions that depend on exact display text.

### Comparable Across Versions

If yesterday's and today's deployments use the same event names and the same field meanings, we can compare counts and rates. If today `payment_declined` is changed to `pay_rejected` without updating queries, dashboards may display incorrect data even though the business logic still works.

### Supporting Investigation of a Specific Case

A stable template does not replace contextual information: each record still needs relevant identifiers such as `order_id`, `request_id`, or `correlation_id`. Those fields help locate a specific case; the event name helps compare that case with others of the same type.

### Defining the Scope of Change

When a message template becomes an input to queries, alerts, parsers, or reports, changing the template is changing the **system observability contract**. Naming, testing, and reviewing log changes seriously helps avoid breaking operational tools outside the Java code.

## 4. Which Parts Should Be Stable, and Which Can Change?

| Component | Design approach | Example |
| --- | --- | --- |
| Event name | Follows a convention, reflects a specific type of behavior | `payment_result`, `order_created` |
| Message template | Keeps its structure when the same event repeats | `"event=payment_result order_id={0} outcome={1}"` |
| Field names | Consistent punctuation, casing, and word joining | `order_id` instead of sometimes `orderId`, sometimes `order-number` |
| Field semantics | A field has the same unit/data type | `duration_ms` is always in milliseconds |
| Result/reason codes | Controlled set of values, avoiding ad-hoc wording | `APPROVED`, `DECLINED`, `CARD_EXPIRED` |
| Log level | Based on impact level and operational rules | `INFO` for expected declines, `SEVERE` for critical errors |
| Per-execution values | Allowed to change, passed via parameters or attributes | `order_id=ORD-101`, `correlation_id=req-7` |
| Timestamp and emission location | Each record has its own values | Timestamp, service, instance, trace id |
| Sensitive data | Do not put directly into the message | Do not log tokens, passwords, card numbers |

There is no need to force **every event type** to share a vague message like `"Action executed"`. For example, `order_created` and `order_cancelled` are two different events, even though both have `order_id`. Merging them into `"Order processed"` without an action or result code loses meaning.

On the other hand, the same type of payment result—whether approved or declined—can use a single `payment_result` template with different `outcome` values if the system wants to analyze them as outcomes of the same processing step. This is a domain modeling choice that should be kept consistent.

## 5. Java 17+ Example with a Fixed Message Template

`java.util.logging` (JUL), built into the JDK, supports parameterized messages. In JUL, templates use placeholders like `{0}`, `{1}`, `{2}`; `Formatter.formatMessage(LogRecord)` processes these parameters according to JUL's formatting mechanism.

The program below defines a template constant `PAYMENT_RESULT_TEMPLATE`. Three executions change the order ID, outcome, and reason code **without changing the template**. The handler is configured once so the output is easy to inspect.

Save the entire code to the file **`StableLogMessageDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class StableLogMessageDemo {
    private static final Logger LOG =
            Logger.getLogger(StableLogMessageDemo.class.getName());

    private static final String PAYMENT_RESULT_TEMPLATE =
            "event=payment_result order_id={0}"
            + " outcome={1} reason_code={2}";

    private StableLogMessageDemo() {
    }

    private static void recordPayment(
            String orderId, String outcome, String reasonCode) {
        LOG.log(Level.INFO, PAYMENT_RESULT_TEMPLATE,
                new Object[] {orderId, outcome, reasonCode});
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        try {
            recordPayment("ORD-101", "APPROVED", "NONE");
            recordPayment("ORD-102", "DECLINED", "CARD_EXPIRED");
            recordPayment("ORD-103", "DECLINED", "INSUFFICIENT_FUNDS");
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 StableLogMessageDemo.java
java StableLogMessageDemo
```

**stderr** receives three lines from `ConsoleHandler`:

```text
INFO event=payment_result order_id=ORD-101 outcome=APPROVED reason_code=NONE
INFO event=payment_result order_id=ORD-102 outcome=DECLINED reason_code=CARD_EXPIRED
INFO event=payment_result order_id=ORD-103 outcome=DECLINED reason_code=INSUFFICIENT_FUNDS
```

**stdout:** empty. If you run it in a terminal, you will still see the three lines because terminals usually display both stderr and stdout.

### Explaining the Example

- The constant `PAYMENT_RESULT_TEMPLATE` keeps the text fixed. Do not build a different sentence with an `if/else` chain for each payment reason.
- `recordPayment` only accepts the three variable values. The values are passed in an `Object[]` array to the `Logger.log` call, substituting for `{0}`, `{1}`, and `{2}` when the formatter processes the record.
- `LOG` is a class-level reusable logger. Message stability **does not depend** on creating a new logger per event; one logger can emit many event types using many different stable templates.
- `formatMessage(record)` returns the message with parameters substituted. Meanwhile, `record.getMessage()` on `LogRecord` retains the original template message passed to the logger, when no other special processing occurs.
- `setUseParentHandlers(false)` prevents this logger from forwarding events to parent logger handlers, avoiding duplicate output in the example.
- The example uses `INFO` even for `DECLINED` outcomes because a decline is an expected business outcome. Connection errors or program bugs need a separate log-level policy.

**Demonstration limitations:** the program does not perform real payments and does not connect to a centralized log store. The values `orderId`, `outcome`, and `reasonCode` are hardcoded in `main` for deterministic output. When values come from users or external services, they must be validated and properly encoded/escaped before logging. The `key=value` lines in the example are plain text; other backends may provide better support for structured data fields.

## 6. Unstable Patterns and How to Fix Them

### Mistake 1: Concatenating Dynamic Values into the Template

```java
// Illustrative example, not a standalone program:
LOG.info("Đơn " + orderId + " bị từ chối vì " + reasonText);
```

For each different `orderId` and `reasonText`, the full sentence differs. If you want to aggregate statistics by grouping the literal message, every order ID can become its own separate group.

A clearer template with JUL:

```java
LOG.log(Level.INFO,
        "event=payment_declined order_id={0} reason_code={1}",
        new Object[] {orderId, reasonCode});
```

Replace a free-form description with a `reasonCode` that has stable values. If operators need a human-readable explanation, the lookup tool can display friendly text based on the reason code; do not use free-form explanation sentences as the primary identifier.

**Subtle point:** string concatenation is not always wrong. Concatenating string literals to define **an immutable template constant** as in `PAYMENT_RESULT_TEMPLATE` is completely valid. The problem is putting variable values into the part used as a grouping key or for log analysis, making the template unpredictable.

### Mistake 2: One Event, Multiple Naming Styles

```text
event=payment_failed
event=payment_rejected
event=pay_denied
```

If they all represent the same **rule-based decline** and are emitted from the same processing step, choose one consistent name such as `payment_declined` and use `reason_code` to distinguish them. If one label represents a technical error and another is a bank's decline decision, **do not mistakenly merge them**: they have two different meanings and require different modeling.

### Mistake 3: Changing a Field's Meaning While Keeping Its Name

```text
duration=850        # here the unit is milliseconds
duration=0.85       # elsewhere the unit is seconds
```

Using the same `duration` field with different units causes dashboards to miscalculate. Use a name like `duration_ms` and standardize on milliseconds; when a unit change is needed, change the field name/schema version and update consumers.

### Mistake 4: Using the Log Message as an Error Code

```java
// Do not use the literal display sentence as a business contract:
String error = "Payment was declined";
if (error.equals(logMessage)) {
    // ...
}
```

Business code needs typed/standardized results and error codes; logs are observations of what happened. Changing log wording should not alter business decisions. Similarly, reporting queries should rely on `event`/`reason_code` rather than entirely on a prose sentence.

## 7. Different Parameter Syntax Between JUL and SLF4J

In the Java ecosystem, logging APIs do not use the same placeholder syntax.

| API | Example | Usage |
| --- | --- | --- |
| JUL: `java.util.logging.Logger` | `LOG.log(Level.INFO, "order_id={0}", orderId);` | Positional parameter `{0}` applied when the formatter runs |
| SLF4J: `org.slf4j.Logger` | `LOG.info("order_id={}", orderId);` | Parameter `{}` handled by the SLF4J API |
| Plain string concatenation | `LOG.info("order_id=" + orderId);` | Value is concatenated into the string before the log call; no separate template and parameters are passed through the API |

The SLF4J snippet below is an **example inside a class that has `LOG`**, requiring the SLF4J library and an implementation such as Logback; it will not run with the JDK alone:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);

void recordPayment(String orderId, String outcome, String reasonCode) {
    LOG.info("event=payment_result order_id={} outcome={} reason_code={}",
            orderId, outcome, reasonCode);
}
```

With SLF4J, a backend may provide structured logging or store parameters in the log event; how much template/argument information is preserved at the final destination depends on the implementation and encoder/appender configuration. A rendered text line alone does not let you assume all original data was preserved.

With JUL, `{0}` belongs to the `MessageFormat`-based formatting mechanism when the formatter runs. Note that single quotes `'` and curly braces in the template can affect `MessageFormat` syntax; if you need to include them in the template, follow the escaping rules of the API in use. Do not copy SLF4J's `"order_id={}"` template directly into JUL and expect JUL to substitute the parameter automatically.

**Performance note:** passing parameters to the logger usually avoids formatting the message before deciding whether to log or discard it. However, **the expressions that produce the arguments** are still evaluated before the call. If computing a value is expensive, look into level checks or the supplier/lazy logging mechanism of your API; do not put business side effects inside a method whose only purpose is logging.

## 8. Stable Messages with Structured Logging

In systems that require large-scale querying, logs should be treated as events with **named fields**, rather than just prose sentences. An illustrative record:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "payment-service",
  "event": "payment_result",
  "order_id": "ORD-102",
  "outcome": "DECLINED",
  "reason_code": "CARD_EXPIRED",
  "correlation_id": "req-abc"
}
```

This is **JSON illustrating a target format**, not the JSON output of the JUL program in section 5.

When collecting logs in structured form, stabilizing **`event`, field names, and value types** is usually more important than keeping a descriptive `message` sentence identical down to every space. A human-readable message is still valuable for operators, but dashboards should filter by dedicated fields.

Some design principles:

1. **Event names represent the actual action/outcome.** Do not log `payment_succeeded` when you have only sent the request to the payment gateway. A stable name with the wrong semantics still misleads.
2. **Use reason codes from a controlled set.** For example `CARD_EXPIRED`, `INSUFFICIENT_FUNDS`, `GATEWAY_TIMEOUT`; do not use full error sentences from external providers as primary codes.
3. **Keep types and units consistent.** For example, `duration_ms` is numeric; `outcome` is a string from a defined value set; correlation ID is a string.
4. **Separate high-cardinality values.** `order_id` and `request_id` are used to look up individual cases. Some platforms charge by the number of series/labels or indexed fields; do not turn every dynamic value into an indexed label without considering cost.
5. **Have a rule when a field does not apply.** For example, a successful payment can use `reason_code=NONE` if the contract specifies it, or omit the field according to the agreed schema. Avoid sometimes using `null`, sometimes `"N/A"`, and sometimes an empty string when they mean the same thing.
6. **Put common data in the right place.** Timestamp, service, environment, and trace id are usually added by the framework/collector. You do not necessarily need to repeat all of them inside every message sentence if they already exist as separate fields.

Plain-text templates only deliver stability when downstream tools process them consistently. Whenever possible, use a JSON encoder or the backend's structured attributes mechanism instead of fragile regular expressions to parse human-language sentences.

## 9. Stable Messages and Correlation IDs

Two events can share the same template while belonging to different transactions:

```text
event=order_updated order_id=ORD-101 correlation_id=req-a result=SUCCESS
event=order_updated order_id=ORD-101 correlation_id=req-b result=SUCCESS
```

Here, `event` and the field names are stable. `order_id` is the same because it is the same order, while `correlation_id` differs because they are two different execution flows. If the application handles retries, you can add `operation_id` or `attempt_id` to distinguish attempts and avoid interpreting two lines as two completed business transactions.

**A stable message alone is not enough for tracing:** without a correlation ID, thousands of lines with the same `event=order_updated` can still be hard to stitch into the exact execution flow.

In an environment using MDC (Mapped Diagnostic Context) of a suitable logging implementation, the correlation ID can be attached to the context per request and then included in logs via the encoder. Clean up the context when the request ends and propagate it intentionally across asynchronous processing. Do not store `currentRequestId` in a `static` variable that mutates per request just to reuse a shared logger.

## 10. Be Stable Without Conflating Different States

The same payment step has multiple possible outcomes:

```text
event=payment_result outcome=APPROVED
event=payment_result outcome=DECLINED reason_code=CARD_EXPIRED
event=payment_result outcome=FAILED reason_code=GATEWAY_TIMEOUT
```

The three records share a common prefix and structure, but **the business outcomes are different**. If operational tools need to alert on technical errors, they must filter specifically for `outcome=FAILED` and/or `reason_code`. Do not treat every `DECLINED` as an `ERROR`; a decline due to an expired card may be an expected workflow outcome.

Depending on the business domain, a system may also define separate event names such as `payment_authorized`, `payment_declined`, `payment_gateway_failed`. Both modeling approaches can be sound when each name has **one clear meaning**, is used consistently, and is not logged overlappingly in a way that skews counts.

For example, when both `payment_result outcome=APPROVED` and `payment_authorized` exist for the same step, you must clearly document whether they are two separate events or two representations of one outcome. Do not implicitly sum line counts from both templates to count approved payments.

## 11. Can Messages Be Changed After Deployment?

Yes, but you need to check whether they are being **consumed by another party**. Stability does not mean freezing every word forever.

**Relatively safe changes:** editing a human-readable explanation sentence without changing `event`, reason codes, field names, or data types in structured logs; you should still check whether any system matches the literal message text.

**Changes that can break queries:** renaming `order_id` to `orderId`, changing `duration_ms` to `duration_s` without a clear unit change, renaming `payment_result` to `payment_finished`, or flipping the meaning of `FAILED`/`DECLINED`. These changes require coordinating dashboards, alerts, parsers, and operational procedures.

**Adding new fields:** can be a backward-compatible change if consumers allow extra fields. For positional or regex-based parsers, adding a field to a string may break parsing even though structured JSON can still be read. Therefore, consider the **actual format and consumers** before concluding compatibility.

For long-lived schemas, it is good practice to have:

- An event catalog and brief documentation describing the meaning of each `event`, required/optional fields, and `outcome`/`reason_code` values.
- Checks in code review or tests to prevent accidental renames.
- A transitional rollout mechanism if a schema change is unavoidable: update consumers, possibly accept both old and new names for a period, and set a deprecation date.
- Schema versioning when there are breaking changes and a need to store multiple versions concurrently, for example a `schema_version` field; do not bump a version just for punctuation edits that do not affect the contract.

A small organization can manage conventions through documentation and code reviews; a large system can maintain a centralized schema/event catalog. What matters is knowing **what is committed to remain stable**.

## 12. Stable Messages Do Not Guarantee Complete Logs

Keeping a fixed template helps identify events, but it does not guarantee that **every execution is logged**. Logs can be filtered by level, sampled, dropped when a handler fails or collection is interrupted, duplicated by retries, or delayed in a centralized system.

When using logs to compute counts or rates:

- Identify the **canonical event** emitted at a confirmed step; avoid logging the same name before and after a state update.
- Recognize that a business operation may be retried multiple times. `payment_attempt_id`, `operation_id`, or an idempotency key helps distinguish attempts where needed.
- Account for sampling, retention, and retry settings in the logger/collector; the number of log lines does not automatically equal the number of completed transactions.
- Reconcile against the database, ledger, or audit system when official, consistent, or auditable figures are required.

For example, counting `event=payment_result outcome=APPROVED` in sampled logs cannot replace the transaction count confirmed by the transaction system. **Lexical stability is different from data reliability.**

## 13. Security and Safety When Formatting Messages

Stable messages encourage putting variable values into parameters. That gives you an opportunity to control **what kind of data is logged**, but logging parameterization itself is **not** a leak-prevention mechanism and does not automatically escape all data.

### Avoid Sensitive Information

Do not log passwords, authentication tokens, OTPs, API keys, full card numbers, or sensitive personal data in either templates or parameter values. For object IDs, use appropriate internal identifiers and strict log access controls; in some systems, IDs themselves may also need masking or hashing.

### Prevent Log Injection

If `reasonText` is received from an external source and concatenated into a log line, newline characters, control characters, or delimiters can cause one event to appear as multiple lines or spoof another field:

```text
reason_text=Invalid input
INFO event=payment_result outcome=APPROVED
```

This is a **risk example** when an input value contains a newline character; it is not output from the program in this article.

Mitigations: log only the fields actually needed, use an encoder/formatter with reliable escaping, limit value lengths, and map provider errors to controlled `reason_code` values in a catalog. Using `{0}` or `{}` placeholders does not automatically strip all disruptive characters from the rendered string.

### Do Not Use Input Data as the Template

Templates should be determined by application code and trusted configuration. Data received from users should be treated as **values**, not format strings for the logger to interpret. Treating arbitrary input as a template can break consistency, corrupt formatting structure, and create unnecessary error surfaces.

### Limit Data Size and Cost

A stable structure does not mean logging the entire request/response. Overly long messages increase cost, reduce readability, and may be truncated at some stage in the pipeline. Pick a few fields with diagnostic value and avoid attaching stack traces or large payloads to every routine event.

## 14. Display Language and Stable Messages

An application serving Vietnamese users may need friendly messages in Vietnamese, while operational tools may need language-independent event codes:

```text
event=payment_declined reason_code=CARD_EXPIRED
Displayed to user: Card has expired. Please use another payment method.
```

The first part is observability/technical data; the second part is a **product message** that can be localized. You should not use user-facing sentences as log identifiers if the product supports multiple languages: changing a translation or punctuation could break log queries.

Many systems still write human-readable `message` text in Vietnamese or English; there is no requirement to use one fixed language for all prose. What matters is that **event names, result codes, field names, and semantics remain stable**, while explanatory text can be managed separately as needed. JUL also supports localized resources via `ResourceBundle` in certain configurations; that does not replace the need for stable technical event codes.

## 15. Message Naming Conventions for a Project

Suppose an ordering application uses a group of business logs. A maintainable convention might look like this:

| Field / concept | Convention | Example |
| --- | --- | --- |
| `event` | Lowercase, words separated by `_`, describes the event | `order_created`, `payment_result` |
| `outcome` | Finite set, uppercase | `STARTED`, `SUCCESS`, `DECLINED`, `FAILED` |
| `reason_code` | Stable cause code | `CARD_EXPIRED`, `GATEWAY_TIMEOUT` |
| `order_id` | An order identifier; avoid sensitive info when possible | `ORD-101` |
| `correlation_id` | Identifies a request flow across steps | `req-7a` |
| `duration_ms` | Duration in milliseconds, numeric type if structured logging supports it | `125` |
| `service` | Stable service name per deployed system | `checkout-service` |

This is an **example convention**, not a mandatory Java standard. A project may use `camelCase` or another event naming style; what matters is having a consistent rule and understanding the data contract.

When reviewing a new message, you can ask:

1. **What does one event mean?** Are we merging two different outcomes or emitting the same name at multiple milestones?
2. **Which part is fixed, and which part changes?** Are IDs, usernames, or free-form reasons being embedded directly into the template?
3. **Are there codes and fields for querying?** Three months from now, can an on-call engineer filter by `event` and `reason_code` instead of searching prose?
4. **Do fields have clear units and types?** Is a convention like `duration_ms` applied uniformly?
5. **Could this accidentally break existing dashboards or alerts?** If the schema changed, have consumers been updated?
6. **Does it expose private data or allow log injection?** What is the minimum data necessary?
7. **Are the emission source and execution flow traceable?** Where are timestamp, service, and correlation ID attached in the event/pipeline?

## 16. One Way to Automatically Test Stability

If message generation logic is important for production monitoring, tests can verify the **template and parameters** when a log is created, rather than only matching the entire formatted line. In JUL, a custom `Handler` in a test can capture the `LogRecord` and inspect `record.getMessage()` and `record.getParameters()`.

Example idea inside a test (not a standalone runnable program):

```java
LogRecord record = capturedRecord;

assert "event=payment_result order_id={0} outcome={1} reason_code={2}"
        .equals(record.getMessage());
assert "ORD-101".equals(record.getParameters()[0]);
assert "APPROVED".equals(record.getParameters()[1]);
```

This way, if someone replaces the template with a dynamically concatenated sentence, the test can catch that the message contract changed. However, distinguish between **testing `LogRecord` creation** and **testing the final pipeline**: even if the template is right, the collector or encoder can still mis-map fields, truncate lines, or drop events. End-to-end tests for structured logs should focus on a few critical events rather than duplicating every detail of every message to avoid brittle tests.

A legitimate template adjustment should be made together with the related documentation, queries, and tests; not every test failure is a bug.

## 17. Common Mistakes

- **Changing wording in each `if` branch for the same event:** event names and reason codes become fragmented. Use a fixed template and pass data via parameters or fields.
- **Using the entire message as a grouping key:** varying `order_id` or free-form text creates too many groups. Group by `event`, `outcome`, and `reason_code`.
- **Creating an overly generic template:** `"Processing completed"` applied to hundreds of operations makes logs hard to understand. Choose event names with specific meaning.
- **Confusing JUL and SLF4J placeholders:** JUL `{0}` differs from SLF4J `{}`; messages may print literal placeholders if you use the wrong API.
- **Keeping the field name while changing the unit/meaning:** causes wrong statistics even while the parser keeps running. Add a new field or version the contract when needed.
- **Renaming `event` while forgetting filters/alerts:** operational tasks silently lose data. Treat the log schema as an interface with consumers.
- **Logging external error sentences verbatim as reason codes:** when the provider changes wording, dashboards split into separate groups. Map them to codes in an internal catalog.
- **Skipping escaping because parameters are used:** dynamic data can still contain newlines or secrets. Use a proper encoder and sanitize/filter data.
- **Using logs as the official source for transaction counts:** retries, sampling, dropped logs, or fan-out skew numbers. Reconcile against the transaction state source.
- **Overusing constants for every message:** not every log line needs its own constant; what matters is a stable, manageable template. For events emitted in many places or backed by an operational contract, shared constants/schemas are more helpful.

## 18. Self-Check Questions

1. **Are two different logs `"Đơn ORD-101 đã tạo"` and `"Đơn ORD-102 đã tạo"` wrong?** Specific values are allowed to differ. The issue is whether the source code uses a stable template or the log record has `event=order_created`/`order_id` fields so tools can recognize the same event type.
2. **When should you use `reason_code` instead of `reasonText`?** When you need stable filtering, grouping, and alerting; free-form text can accompany it if diagnostically valuable, provided it is protected and escaped.
3. **In JUL, where does `"order_id={0}"` get its value?** From the record's parameters when the formatter runs; the Java compiler does not substitute `{0}` itself.
4. **Can you replace `{0}` with `{}` when migrating a template from JUL to SLF4J?** Yes, but you must also switch to the right API and parameter-passing style; the two syntaxes are not automatically equivalent.
5. **Should `correlation_id` be fixed as a constant to make the message stable?** No. The correlation ID must change per execution flow; what stays stable is the **field name** and its role.
6. **An alert on `event=payment_result` disappears after renaming it to `payment_finished`. Why?** The event name is part of the contract with the filter; consumers must be updated or a migration process must be rolled out.
7. **Are `duration_ms=100` and `duration_ms=0.1` both valid for a step that took 100 ms?** No. With the field name `duration_ms`, the value `0.1` means 0.1 ms; if you want seconds, you must use a different field/unit.
8. **Should you rely on the count of lines with the same message to conclude the number of transactions?** Not by default. You need to understand retries, retention, sampling, and where the event is emitted.
9. **Can Vietnamese be used for the explanatory text of a message?** Yes. Event codes and fields used in analysis should follow a stable, translation-independent convention.
10. **If a user enters a newline in a field, do placeholders automatically prevent log injection?** No. You must use an appropriate encoder/escaping and data-limiting policy.

**Remember:** a stable message maintains **consistent event meaning, message template, and field structure**, while placing each execution's IDs, outcomes, reason codes, and context into **parameters or separate attributes**. In Java, choose the right syntax for your logging API (JUL `{0}`, SLF4J `{}`), define a searchable event contract, protect dynamic data, and control changes that affect observability systems.
