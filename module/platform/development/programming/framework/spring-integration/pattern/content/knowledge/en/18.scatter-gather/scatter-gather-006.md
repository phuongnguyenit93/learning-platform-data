# Accepting a Partial Result vs. Failing Completely

> **Chapter:** Scatter gather  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and monitoring each branch. This lesson focuses on **deciding whether to accept a partial result or fail the entire operation** when some recipients have not replied or return errors.

## 1. Learning objectives

After this lesson, you can:

1. Describe the two phases **scatter** (distributing the same request to multiple processors) and **gather** (collecting replies by correlation) of the Scatter-Gather EIP.
2. Distinguish **all replies received**, **business success**, **quorum met**, **missing replies**, **timeout**, **technical error**, **business error**, and **late replies**.
3. Design an explicit policy: **all-or-nothing**, **conditional partial acceptance**, **quorum**, or **manual review**, with mandatory recipients and quality thresholds.
4. Configure an implementation approach in Spring Integration, including Scatter-Gather, Recipient List/Publish-Subscribe, Aggregator, correlation, release, timeouts, and partial expiry.
5. Explain why `groupTimeout` **is not automatically an absolute deadline from request arrival**, and why **zero replies** needs a request-level deadline mechanism.
6. Write unit-testable Java policies and design integration tests for 0/1/N replies, duplicates, late replies, partials, full failures, and races near the deadline.
7. Control retry/idempotency, side effects, compensating actions, observability, and data security across multiple recipients.

## 2. Business example: fetching quotes from three suppliers

An e-commerce platform needs shipping quotes from three partners: `FAST`, `ECONOMY`, and `GLOBAL`. One `QuoteRequest` sends the same delivery conditions to all three suppliers; results may arrive with different latencies.

~~~text
QuoteRequest(requestId=REQ-901, destination=VN)
                  |
                  v
             Scatter
                  |
          +-------+--------+
          |       |        |
        FAST   ECONOMY   GLOBAL
          |       |        |
       80.000   65.000   ...timeout...
          |       |        |
          +-------+--------+
                  |
                  v
              Gather
             2 / 3 replies
                  |
                  v
    Return best price from the 2 providers,
    or fail everything because GLOBAL is missing?
~~~

The answer depends on the **business contract** and cannot be decided solely by what the Aggregator is technically capable of.

- For **suggesting shipping prices to a shopper**, two valid quotes may be enough to display; the result must flag "not all quotes received".
- For **a financial reconciliation flow requiring all three sources**, one missing reply may **prevent the request from completing**, even when two sources succeeded.
- For **a critical mandatory destination** like `FAST` due to hazardous-goods handling requirements, if it has not replied, the remaining two results **cannot be treated as sufficient**.
- For **quorum** (e.g., at least two independent sources), two-source results may be acceptable if both are valid and no mandatory-source policy is violated.

~~~mermaid
flowchart TD
    IN["QuoteRequest"] --> S["Scatter to FAST, ECONOMY, GLOBAL"]
    S --> A["Gather replies by executionId"]
    A --> C{"Completion criteria met?"}
    C -->|"All present, valid"| OK["COMPLETE: accepted"]
    C -->|"Quorum met, partial allowed"| PART["PARTIAL_ACCEPTED + missing list"]
    C -->|"Missing / before deadline"| WAIT["WAITING"]
    C -->|"Expired, criteria unmet"| FAIL["FAILED / RECONCILIATION"]
    WAIT --> A
~~~

**Important academic rule:** "Having two out of three replies" **does not automatically equal** "2/3 success". A reply may report a business rejection, malformed schema, or invalid price. Validate **validity and meaning** of each result before applying a partial policy.

## 3. Scatter-Gather: two phases, two distinct responsibilities

**Scatter:** sends one request to multiple recipients capable of independent processing; can use Recipient List Router or Publish-Subscribe depending on configured topology.

**Gather:** receives replies, correlates them to **the same execution**, applies a release condition, and builds a combined result for the caller or downstream.

~~~mermaid
flowchart LR
    Q["Request"] --> SC["Scatterer"]
    SC --> P1["Provider FAST"]
    SC --> P2["Provider ECONOMY"]
    SC --> P3["Provider GLOBAL"]
    P1 --> RP["Reply / correlation"]
    P2 --> RP
    P3 --> RP
    RP --> AG["Gatherer / Aggregator"]
    AG --> OUT["Combined response"]
~~~

Scatter-Gather differs from "calling three HTTP APIs sequentially" in that branches can **proceed independently**, and the caller needs a strategy for **when enough replies have arrived**. However, a Scatter-Gather flow **does not guarantee parallel execution on its own**: that depends on channels, executors, Gateway, and infrastructure.

### 3.1. Comparison with closely related EIPs

| Pattern | Focus | Example |
| --- | --- | --- |
| **Scatter-Gather** | Send a request to multiple recipients and **collect replies** per policy | Query three partners, aggregate quotes |
| **Recipient List** | Select recipients to receive a message; **does not necessarily wait for replies** | Emit event to audit and analytics |
| **Publish-Subscribe Channel** | Distribute a message to subscribers | One event for multiple consumers |
| **Splitter** | Split **one multi-part payload** into child messages | Three order lines → three stock check requests |
| **Aggregator** | Combine replies/messages in the same group | Combine three results into one |
| **Content-Based Router** | Pick a branch conditionally | Frozen goods → cold storage |

A system can use **Splitter → process each item → Aggregator** without being Scatter-Gather in the sense of "asking multiple providers the same question"; the distinction is **one question sent to multiple recipients** vs. **multiple distinct data parts needing processing**.

### 3.2. Two questions that must not be merged

1. **Did Scatter succeed?** Were messages dispatched to every required channel/adapter?
2. **Does Gather have a trustworthy result?** Did enough replies arrive that genuinely satisfy business policy?

`MessageChannel.send(...) == true` or a broker ACK may only confirm **technical receipt at the boundary**, not that providers finished calculating quotes or committing actions.

## 4. Separating completeness from business outcome

Model a combined result along **two independent dimensions**:

- **Completeness:** how many valid replies arrived relative to the expected recipients?
- **Business outcome:** do the received replies satisfy policy?

| Completeness | Business outcome | Meaning |
| --- | --- | --- |
| `ALL_RESPONDED` | `ALL_ACCEPTED` | All recipients replied and passed conditions |
| `ALL_RESPONDED` | `SOME_REJECTED` | All replied, yet at least one provider rejected |
| `PARTIAL_TIMED_OUT` | `PARTIAL_ACCEPTED` | Not all replied, yet a subset satisfies criteria |
| `PARTIAL_TIMED_OUT` | `FAILED` | Not all replied and minimum/mandatory threshold unmet |
| `NO_REPLIES` | `FAILED` | Zero replies before deadline |

**Warning:** `ALL_RESPONDED` does not mean `ALL_ACCEPTED`. A provider may reply very quickly that it does not support the delivery address. That is **a received reply**, not **a usable quote**.

### 4.1. Technical replies vs. business replies

An HTTP 200 carrying a valid quote differs from an HTTP 200 carrying `status=REJECTED`. HTTP 503, timeouts, and disconnects are technical situations where **you may not know whether the provider processed the request**.

With Scatter-Gather:

- **ACCEPTED reply:** data eligible for selection per contract.
- **REJECTED reply:** recipient returned a terminal business decision; not counted as a successful quote.
- **No reply / timeout:** **UNKNOWN/NOT_RECEIVED** state; never assume it is REJECTED.
- **Malformed reply:** schema error; send to error/quarantine, do not count toward valid replies.
- **Duplicate reply:** must deduplicate by recipient/operation identity.

## 5. Four common policies: strict, partial, quorum, and fail-fast

### 5.1. Strict all-or-nothing

**Succeeds only when every mandatory recipient returns a successful reply.** If any reply ends in terminal rejection, or the deadline expires with missing replies, the whole request is marked incomplete per contract.

~~~text
Expected: [FAST, ECONOMY, GLOBAL]
Accepted: [FAST, ECONOMY]
Missing:  [GLOBAL]
Deadline: reached

Result: FAILED / INCOMPLETE
~~~

Suitable when **decisions are forbidden with missing data**, such as an approval requiring sign-off from three independent departments.

**A strict failure does not equal a transaction rollback.** If recipients already executed side effects (reserved inventory, transferred funds, booked slots), marking the overall result failed **does not undo** committed actions.

### 5.2. Conditionally accepted partial result

A result may be returned when:

1. Some providers are still missing or rejected.
2. There are **at least N valid quotes**.
3. **Mandatory** providers returned valid replies.
4. A deadline or controlled release rule determined when to stop waiting.
5. Caller/downstream **knows the result is partial** and has corresponding handling rules.

Example `minAccepted=2`, `mandatory={FAST}`:

~~~text
FAST:    ACCEPTED 80.000
ECONOMY: ACCEPTED 65.000
GLOBAL:  NO_REPLY

At deadline: PARTIAL_ACCEPTED
Best known quote: ECONOMY 65.000
Missing providers: [GLOBAL]
~~~

**"Best known quote" does not guarantee the lowest possible price**, because GLOBAL has no data yet. If the UI displays it, clearly phrase it as the best price **among quotes received so far**.

### 5.3. Threshold quorum

A quorum might be `2/3`, `3/5`, or a condition based on **source weights and independence**. Counting raw replies is insufficient:

- Two replies from **the same logical provider** do not form a two-party quorum.
- One provider behind multiple aliases/channels must not be counted twice.
- Some parties may be **mandatory**; they must be present regardless of count.
- For legally/financially impactful outcomes, "majority returned" may not equal "sufficient evidence".

**Quorum does not always wait until timeout.** If policy permits releasing as soon as two answers arrive without caring about the third, the Aggregator can release early; however, that may sacrifice a better result. Choose deliberately between **optimal latency** and **result quality**.

### 5.4. Fail-fast when conditions are unrecoverable

If a **mandatory** provider returns a terminal business error, such as `NOT_ELIGIBLE`, a strict policy can **fail early** without waiting for remaining providers. However, if it is only a retriable network glitch, failing fast immediately may be premature.

Define clearly:

- **Terminal rejection:** final conclusion per contract; can fail-fast.
- **Transient failure:** recoverable technical error; wait/retry within deadline.
- **Uncertain outcome:** unclear whether side effects occurred; reconcile before deciding on compensation.
- **Deadline reached:** SLA cutoff to close the result set, without turning UNKNOWN into terminal rejection.

## 6. Decision table: when is partial truly valid?

Assume expected `{FAST, ECONOMY, GLOBAL}`, mandatory `{FAST}`, minimum accepted = 2.

| FAST | ECONOMY | GLOBAL | Deadline reached? | Partial policy decision |
| --- | --- | --- | --- | --- |
| ACCEPTED | ACCEPTED | ACCEPTED | No need to wait | `ACCEPTED_COMPLETE` |
| ACCEPTED | ACCEPTED | Missing | No | `WAITING` |
| ACCEPTED | ACCEPTED | Missing | Yes | `ACCEPTED_PARTIAL` |
| ACCEPTED | Missing | ACCEPTED | Yes | `ACCEPTED_PARTIAL` |
| Missing | ACCEPTED | ACCEPTED | Yes | `FAILED` (mandatory missing) |
| Terminal REJECTED | ACCEPTED | ACCEPTED | Any | `FAILED` (mandatory rejected) |
| ACCEPTED | Terminal REJECTED | ACCEPTED | No need to wait | `ACCEPTED_PARTIAL` (2 met, all 3 replied) |
| ACCEPTED | Missing | Missing | Yes | `FAILED` (only 1 accepted) |
| Missing | Missing | Missing | Yes | `FAILED` (zero replies) |
| ACCEPTED | ACCEPTED | ACCEPTED | Yes | `ACCEPTED_COMPLETE` |

If switched to **strict all-or-nothing**, any row with missing or REJECTED cannot become `ACCEPTED_COMPLETE`. Policies should be **versioned**, especially if thresholds or mandatory providers change while a request is in flight.

### 6.1. Do not "reduce expectedCount" to fake quorum

Suppose GLOBAL times out; never silently change `expectedCount=3` to `expectedCount=2` and record `COMPLETE`. Doing so erases evidence that GLOBAL failed to reply.

Preserve the **original expected set** and record explicitly:

~~~json
{
  "executionId": "RUN-901",
  "expectedProviders": ["FAST", "ECONOMY", "GLOBAL"],
  "respondedProviders": ["FAST", "ECONOMY"],
  "missingProviders": ["GLOBAL"],
  "decision": "ACCEPTED_PARTIAL",
  "policyVersion": "quote-policy-v2"
}
~~~

## 7. Contract must include expected recipients and execution identity

In Scatter-Gather, a request can be retried, and the same provider may send a reply twice. Therefore, **received message count differs from unique responding provider count**.

~~~text
Request REQ-901
   execution RUN-901-A
     expected FAST, ECONOMY, GLOBAL
     FAST reply accepted
     FAST reply accepted (duplicate)
     ECONOMY reply accepted
     GLOBAL missing

Raw reply count = 3
Unique respondent count = 2
Completeness = PARTIAL
~~~

A sound policy must count by **trusted provider ID**, not just `group.size()` or `sequenceSize`.

### 7.1. Distinguishing identifiers

| Field | Meaning | Example |
| --- | --- | --- |
| `requestId` | Caller's business request | `REQ-901` |
| `executionId` | One specific scatter run; group key | `RUN-901-A` |
| `providerId` | Authorized logical recipient | `FAST` |
| `operationId` | Idempotency key for side-effectful work | `quote-op-901` |
| `correlationId` | Links replies to scatter execution | `RUN-901-A` or corresponding group key |
| `messageId` | Framework-managed envelope ID | May change across replay/adapters |
| `policyVersion` | Result acceptance rules | `quote-policy-v2` |

**Correlation does not replace idempotency.** Correlation is a reply-grouping mechanism. Slow responses still require checking whether the execution is already closed; replayed requests can still cause side effects if downstream lacks a stable idempotency key.

### 7.2. Expected recipients are authoritative data

If a user supplies `expectedProviders=["FAST"]` to bypass mandatory providers, the partial policy is defeated. The expected set must be computed by **a trusted routing policy** based on authenticated data and the chosen version.

If the recipient list is dynamically selected, `sequenceSize` must reflect **the number of recipients actually chosen** when sequencing is used; meanwhile, business policy must know **contractually mandatory recipients**, not just current channel count.

## 8. Java 17: framework-independent data model and policy

To separate business semantics from Spring Integration configuration, let's define a pure Java policy that evaluates replies at a given instant.

### 8.1. Records and states

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Set;

enum ProviderStatus {
    ACCEPTED,
    REJECTED
}

record ProviderReply(
    String providerId,
    ProviderStatus status,
    BigDecimal price
) {
    ProviderReply {
        if (providerId == null || providerId.isBlank()) {
            throw new IllegalArgumentException("providerId required");
        }
        Objects.requireNonNull(status, "status");

        if (status == ProviderStatus.ACCEPTED
                && (price == null || price.signum() < 0)) {
            throw new IllegalArgumentException(
                "Accepted quote needs non-negative price");
        }
    }
}

record ScatterPlan(
    String executionId,
    String requestId,
    String policyVersion,
    Set<String> expectedProviders,
    Set<String> mandatoryProviders,
    int minimumAccepted,
    boolean allowPartial,
    Instant deadline
) {
    ScatterPlan {
        if (executionId == null || executionId.isBlank()
            || requestId == null || requestId.isBlank()
            || policyVersion == null || policyVersion.isBlank()) {
            throw new IllegalArgumentException("Identity/version required");
        }
        expectedProviders = Set.copyOf(
            Objects.requireNonNull(expectedProviders));
        mandatoryProviders = Set.copyOf(
            Objects.requireNonNull(mandatoryProviders));
        Objects.requireNonNull(deadline);

        if (expectedProviders.isEmpty()
            || !expectedProviders.containsAll(mandatoryProviders)
            || minimumAccepted < 1
            || minimumAccepted > expectedProviders.size()) {
            throw new IllegalArgumentException("Invalid scatter plan");
        }
    }
}

enum DecisionStatus {
    WAITING,
    ACCEPTED_COMPLETE,
    ACCEPTED_PARTIAL,
    FAILED
}

record ScatterDecision(
    DecisionStatus status,
    int expectedCount,
    int respondedCount,
    List<String> acceptedProviders,
    List<String> missingProviders,
    String reasonCode
) {
    ScatterDecision {
        acceptedProviders = List.copyOf(acceptedProviders);
        missingProviders = List.copyOf(missingProviders);
    }
}
~~~

`ProviderStatus.REJECTED` here represents **a terminal business decision** only; HTTP 503 errors, timeouts, or indeterminate responses **must not automatically become REJECTED**. Technical failures pass through retry/error/reconciliation, and the provider is still considered **lacking a valid terminal reply** until an outcome is determined.

### 8.2. Policy accepting N replies, deduplicating, and applying rules

~~~java
import java.time.Instant;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

final class ScatterDecisionPolicy {
    private ScatterDecisionPolicy() {}

    static ScatterDecision evaluate(
            ScatterPlan plan,
            Collection<ProviderReply> replies,
            Instant now) {

        Objects.requireNonNull(plan);
        Objects.requireNonNull(replies);
        Objects.requireNonNull(now);

        Map<String, ProviderReply> unique = new HashMap<>();

        for (ProviderReply reply : replies) {
            if (reply == null
                    || !plan.expectedProviders().contains(reply.providerId())) {
                throw new IllegalArgumentException(
                    "Unknown/null provider reply");
            }
            ProviderReply previous =
                unique.putIfAbsent(reply.providerId(), reply);
            if (previous != null && !previous.equals(reply)) {
                throw new IllegalArgumentException(
                    "Conflicting duplicate provider reply");
            }
        }

        Set<String> accepted = unique.values().stream()
            .filter(r -> r.status() == ProviderStatus.ACCEPTED)
            .map(ProviderReply::providerId)
            .collect(Collectors.toSet());

        List<String> missing = plan.expectedProviders().stream()
            .filter(id -> !unique.containsKey(id))
            .sorted()
            .toList();

        List<String> acceptedIds = accepted.stream().sorted().toList();
        int responded = unique.size();
        boolean allResponded = missing.isEmpty();
        boolean allAccepted = accepted.size() == plan.expectedProviders().size();
        boolean mandatoryAccepted =
            accepted.containsAll(plan.mandatoryProviders());
        boolean mandatoryRejected = plan.mandatoryProviders().stream()
            .anyMatch(id -> unique.containsKey(id)
                && unique.get(id).status() == ProviderStatus.REJECTED);
        boolean quorumSatisfied =
            accepted.size() >= plan.minimumAccepted() && mandatoryAccepted;
        boolean deadlineReached = !now.isBefore(plan.deadline());

        DecisionStatus status;
        String reason;

        if (mandatoryRejected) {
            // Terminal business failure on a mandatory recipient.
            status = DecisionStatus.FAILED;
            reason = "MANDATORY_PROVIDER_REJECTED";
        } else if (allResponded && allAccepted) {
            status = DecisionStatus.ACCEPTED_COMPLETE;
            reason = "ALL_PROVIDERS_ACCEPTED";
        } else if (allResponded || deadlineReached) {
            if (plan.allowPartial() && quorumSatisfied) {
                status = DecisionStatus.ACCEPTED_PARTIAL;
                reason = "PARTIAL_POLICY_SATISFIED";
            } else {
                status = DecisionStatus.FAILED;
                reason = deadlineReached
                    ? "DEADLINE_WITHOUT_REQUIRED_RESULTS"
                    : "INSUFFICIENT_VALID_REPLIES";
            }
        } else {
            status = DecisionStatus.WAITING;
            reason = "AWAITING_REPLIES";
        }

        return new ScatterDecision(
            status,
            plan.expectedProviders().size(),
            responded,
            acceptedIds,
            missing,
            reason);
    }
}
~~~

**Exact meaning of the function:**

- **Counts unique providers**, not duplicate messages.
- A **mandatory provider returning REJECTED** fails the request fast per the illustrative policy.
- When **all replies arrive and all providers ACCEPTED**, returns `ACCEPTED_COMPLETE`.
- When **all have replied**, or **deadline is reached**, can return `ACCEPTED_PARTIAL` **only if allowPartial=true, minimum is met, and no mandatory accepted is missing**.
- If incomplete and time remains, returns `WAITING`.
- If criteria are unmet upon closing the group, returns `FAILED`.
- Validation does not silently ignore invalid replies, unknown providers, or conflicting duplicates.

**Important limitation:** `evaluate` is a **pure policy**; it does not dispatch, schedule timeouts, or persist closed state. It is designed to be called when a new reply arrives or when a deadline watcher fires. Production also needs **atomic state transitions** on the execution so the final result is never emitted twice.

### 8.3. How is all-or-nothing expressed?

Strict example:

~~~java
ScatterPlan strict = new ScatterPlan(
    "RUN-901-STRICT",
    "REQ-901",
    "quote-policy-strict-v1",
    Set.of("FAST", "ECONOMY", "GLOBAL"),
    Set.of("FAST", "ECONOMY", "GLOBAL"),
    3,
    false,
    Instant.parse("2026-11-21T10:00:05Z"));
~~~

Thresholded partial example:

~~~java
ScatterPlan partial = new ScatterPlan(
    "RUN-901-PARTIAL",
    "REQ-901",
    "quote-policy-v2",
    Set.of("FAST", "ECONOMY", "GLOBAL"),
    Set.of("FAST"),
    2,
    true,
    Instant.parse("2026-11-21T10:00:05Z"));
~~~

Both policies share one scatter/gather mechanism yet make **different business decisions**. Never change `allowPartial` while an execution is pending without saving a policy version/snapshot; otherwise, the same set of replies can yield two different outcomes upon retry.

## 9. Release timing: all replies vs. quorum met

There are two common approaches when `2/3` replies arrive:

1. **Release immediately upon quorum:** cuts latency, yet may miss a better price or an unknown mandatory factor. Requires a contract focused purely on "any two sources" rather than "best choice across all".
2. **Wait until deadline or all replies:** improves chances of receiving the remaining reply, then accepts partial if policy allows. This is the strategy in `ScatterDecisionPolicy` above.

### 9.1. Configuring the Aggregator's release strategy

If choosing wait-for-all, the Gatherer can:

- Correlate by `executionId`.
- Release completely when **every expected provider has one valid reply**.
- If the group expires while incomplete, configure **partial expiry**.
- Pass received replies to the output processor/policy to decide `ACCEPTED_PARTIAL` vs. `FAILED`.

If releasing **immediately on quorum**, the Gatherer must inspect **unique accepted providers** plus mandatory conditions; do not use `group.size() >= 2` because duplicates or a REJECTED reply can satisfy count erroneously.

### 9.2. Do not take `Aggregator released` as proof of policy acceptance

Aggregator **releasing** a group is a **technical timing decision for emitting output**. It may release due to all replies, quorum, or timeout. After release, the **business decision processor** must still evaluate conditions and emit a clearly statused outcome.

For example, a group with all three replies where GLOBAL is REJECTED may still be released normally by the Aggregator; under strict policy, **the business decision is still FAILED**.

## 10. Spring Integration: Scatter-Gather and partial expiry policies

Spring Integration supports the Scatter-Gather EIP with a **scatterer** and **gatherer**, configurable via Java DSL and related endpoints. In the scatter phase, a Recipient List or Publish-Subscribe distributes the request to recipient channels/flows; in the gather phase, an Aggregator mechanism collects correlated replies and applies a release strategy.

### 10.1. Recommended topology diagram

~~~text
quotes.in
  |
  v
Validate / authenticate / create ScatterPlan snapshot
  |
  v
Scatter-Gather
  +-- scatter: FAST request handler ------> reply FAST
  +-- scatter: ECONOMY request handler ---> reply ECONOMY
  +-- scatter: GLOBAL request handler ----> reply GLOBAL
  |
  +-- gather: correlate executionId
      |
      +-- all replies → combined group
      +-- expiry → partial group (if configured)
      |
      v
Business decision processor (strict / partial / quorum)
  |
  +--> quotes.accepted.complete
  +--> quotes.accepted.partial
  +--> quotes.failed / quotes.reconciliation
~~~

**Design assumptions:** recipient handlers **actually return replies** through the Scatter-Gather mechanism, rather than calling a one-way adapter and stopping. Over async brokers/HTTP, design reply routes, correlation, and state stores rather than expecting an HTTP request thread to block indefinitely.

### 10.2. Java DSL illustrating configuration mechanics

The example below is a **DSL configuration sketch** showing responsibilities, not a standalone program ready to compile without declaring `fastHandler`, `economyHandler`, `globalHandler`, and reply topology:

~~~java
// Spring Integration Java DSL sketch:
// Verify overload signatures and endpoint config for your version.
IntegrationFlow quoteScatterGather() {
    return IntegrationFlow.from("quotes.in")
        .scatterGather(
            scatterer -> scatterer
                .recipientFlow(f -> f.handle(fastHandler))
                .recipientFlow(f -> f.handle(economyHandler))
                .recipientFlow(f -> f.handle(globalHandler)),
            gatherer -> gatherer
                .groupTimeout(5_000L)
                .sendPartialResultOnExpiry(true))
        .channel("quotes.gathered")
        .get();
}
~~~

Handlers may require dedicated Gateways/adapters and reply messages built per contract. `groupTimeout` is a group-level timeout inside Gatherer; `sendPartialResultOnExpiry(true)` **does not turn a partial into success**. Place a **policy processor** after Gatherer to decide `ACCEPTED_PARTIAL` or `FAILED`, plus a request-level **deadline watcher** if the SLA must run from scatter start.

**Note:** exact methods on DSL specs and Scatter-Gather lifecycle can differ across Spring Integration versions. This lesson is about **architecture and partial-vs-fail decisions**, not a claim that a snippet runs unmodified across every version without checking APIs. `ScatterDecisionPolicy` is pure Java code for testing business logic independently.

### 10.3. Do not mix control flow into a single callback

If the Scatterer callback chooses recipients, calls three external APIs itself, catches exceptions, computes results, and writes to a database, distinguishing errors/timeouts becomes very hard. Separate:

- **Scatter policy:** picks valid expected recipients.
- **Recipient handler:** executes or forwards the request per provider.
- **Reply mapper:** creates a valid `ProviderReply` with `executionId/providerId`.
- **Gatherer:** groups by correlation, releases/expires per technical policy.
- **Business policy processor:** accepts partial or fails.
- **Finalization/registry:** emits **exactly one final decision** per execution.

## 11. Why is group timeout not enough to guarantee an SLA?

A request starts at T0. Provider FAST replies at T0+1s; ECONOMY at T0+3s; GLOBAL does not reply. If the overall SLA is 5 seconds, the system must decide at T0+5s regardless of when the Aggregator received its first message.

~~~text
T0       Scatter request created; deadline=T0+5s
T0+1     FAST reply -> Aggregator creates group
T0+3     ECONOMY reply -> Aggregator updates group
T0+5     Business deadline must settle outcome
T0+9     GLOBAL late reply
~~~

A `groupTimeout(5000)` may be calculated/rescheduled based on group state and message arrival timestamps. Therefore, **never interpret it as an absolute deadline at exactly T0+5** without verifying your version's behavior and actual configuration.

### 11.1. Request-level deadline watcher

A resilient architecture persists at scatter time:

~~~text
ScatterExecution:
    executionId    = RUN-901
    requestId      = REQ-901
    expected       = [FAST, ECONOMY, GLOBAL]
    mandatory      = [FAST]
    createdAt      = T0
    deadlineAt     = T0 + 5 seconds
    policyVersion  = quote-policy-v2
    state          = OPEN
~~~

The watcher can run via a scheduler, delay queue, or persistent workflow engine. At deadline:

1. Read execution state.
2. Read valid recorded replies.
3. Invoke the business decision policy.
4. Use **CAS/transaction** to transition `OPEN → CLOSED` exactly once.
5. Emit the corresponding final output, or write to an outbox for crash reliability.
6. Subsequent replies go to the late/reconciliation path.

### 11.2. What if zero replies arrive?

If none of the three providers reply, the Gatherer may **never have created a message group**. Without a group, **per-group timeout has nothing to expire**. The deadline watcher must emit `FAILED(NO_REPLIES)` or `BatchTimedOut` per contract.

Never design an API promising "always responds within 5 seconds" using only `groupTimeout` on the Aggregator. Test the zero-reply case **from the scatter request registry**, not just by sending one reply and waiting.

## 12. Late replies, duplicates, and races near the deadline

Suppose `ACCEPTED_PARTIAL` was emitted at T0+5 with FAST and ECONOMY. At T0+7, GLOBAL returns a better price than both. There are three options:

| Policy | Behavior | Trade-off |
| --- | --- | --- |
| **Ignore + audit** | Do not alter emitted decision; record late reply | Easy to uphold single-final-result contract; misses better price |
| **Versioned update** | Emit `QuoteResultUpdated(v2)` with new price if still allowed | Caller must support updates and versions |
| **Reconcile/manual review** | Handle via separate workflow without overwriting first result | More states, easier control |

**Never emit a second unversioned `QuoteResult(FINAL)` with the same execution ID.** That can cause consumers to charge payment or book shipping twice.

### 12.1. Tombstone or closed execution registry

After Aggregator release/expiry, the group may be deleted from the store. A late reply with the same correlation can create a new group unless blocked. Use a registry:

~~~text
Reply arrives:
  execution OPEN      -> validate/dedup -> gather
  execution COMPLETE  -> duplicate / late handling
  execution EXPIRED   -> reconciliation / audit
  execution UNKNOWN   -> reject / investigation
~~~

Tombstone retention must match **the window in which messages can arrive late or be replayed**. Keeping tombstones for 10 seconds is insufficient if the broker can replay after days.

### 12.2. Race: final reply and timeout simultaneously

~~~text
Thread A: receives GLOBAL, 3/3 complete
Thread B: deadline watcher sees 2/3
~~~

An execution must **commit only one final outcome**. Use compare-and-set/transactions on a single source of truth, then publish the final event via outbox/idempotent publisher if needed. The outcome may be COMPLETE **or** PARTIAL depending on which atomic transition wins, never **both**.

### 12.3. Duplicate replies are not extra quorum

Receiving FAST twice and ECONOMY once is not three providers. Validate and deduplicate by `(executionId, providerId, responseId/operationId)` as appropriate. If two replies from the same provider carry different prices, enforce an explicit **version/attempt** policy or quarantine; never arbitrarily pick "last write wins".

## 13. All-or-nothing with side effects: failing the request does not mean rollback

Quoting examples are typically read-only. However, if scatter dispatches three **booking commands** instead of quote lookups, all three recipients can produce side effects. One failing branch does not automatically undo the two branches that already succeeded.

~~~mermaid
flowchart TD
    X["Scatter: reserve 3 resources"] --> A["A committed"]
    X --> B["B committed"]
    X --> C["C failed / unknown"]
    A --> F["Global all-or-nothing outcome = FAILED"]
    B --> F
    C --> F
    F --> COMP["Compensation / reconciliation"]
    COMP --> R["Release A, B if needed"]
~~~

**This is not an automatic distributed transaction.** You need compensating rules (Saga/compensating actions), idempotency, verification of whether commits happened, and monitoring of the compensations themselves.

### 13.1. Do not use Scatter-Gather for a single-owner command

If `ChargePayment` should execute on **one** responsible payment system, sending the same command to three providers via a Recipient List could cause three charges. For single-owner actions, use a Router to choose **one owner**, then emit events to dependents after completion. Scatter-Gather fits when multiple parties are **permitted to process the same independent request concurrently**.

### 13.2. Per-recipient retries

If ECONOMY and FAST replied and only GLOBAL timed out, retrying the entire scatter re-sends requests to all three. For reads this adds load; for side effects it creates major risk.

Prefer:

- Retrying **only the failing branch** within the deadline, with bounded backoff/limits.
- Stable idempotency keys on external consumers for side-effectful commands.
- Status lookups when timeouts leave indeterminate outcomes.
- Never resetting the overall deadline indefinitely on each retry.
- Reconciliation once retries exhaust with unknown outcomes.

## 14. Error channel vs. partial results

A handler error can happen **before or after** a request is accepted by a channel:

| Scenario | What to do | Counts as a valid reply? |
| --- | --- | --- |
| Provider returns valid ACCEPTED | Normalize `ProviderReply` | Yes |
| Provider returns business REJECTED | Normalize terminal reply | Yes, though not accepted |
| HTTP 503 / timeout | Retry/error path per policy | No, unless contract defines a dedicated terminal outcome |
| Malformed JSON | Reject/quarantine, alert contract breach | No |
| Unauthenticated source | Block before Gatherer | No |
| ReplyChannel lost across broker | Fix header mapping/reply routing | No |
| Adapter received response but lost before state write | May retry/redeliver | Needs dedup and recovery |

With a synchronous `DirectChannel`, exceptions may propagate back to the caller; with executors/pollers/brokers, errors typically go through an error channel or transport error mechanism. An `ErrorMessage` **does not automatically become** a `ProviderReply(REJECTED)` for Gatherer.

### 14.1. When turning errors into replies to close a group early

You can create a **typed failure result** like `ProviderOutcome(providerId, TECHNICAL_ERROR)` after exhausting retries and verifying state, letting Gatherer track the expected set. Yet keep these distinct:

- **Terminal business rejection:** confirmed refusal by the recipient.
- **Technical failure:** unable to process request; side effects may be unknown.
- **Timeout/unknown:** no trustworthy result.

Do not force all three into `REJECTED` and claim all business replies arrived.

## 15. JUnit 5: unit tests for partial-vs-fail decisions

Examples use the records and `ScatterDecisionPolicy` from section 8. Time is passed via `Instant now` so tests **do not depend on wall-clock time or `Thread.sleep`**.

### 15.1. Testing partial acceptance when quorum and mandatory are met

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ScatterDecisionPolicyTest {
    private static final Instant DEADLINE =
        Instant.parse("2026-11-21T10:00:05Z");

    private static ScatterPlan plan(boolean allowPartial) {
        return new ScatterPlan(
            "RUN-901", "REQ-901", "quote-policy-v2",
            Set.of("FAST", "ECONOMY", "GLOBAL"),
            Set.of("FAST"), 2, allowPartial, DEADLINE);
    }

    private static ProviderReply accepted(String id, String price) {
        return new ProviderReply(id, ProviderStatus.ACCEPTED,
            new BigDecimal(price));
    }

    @Test
    void acceptsPartialOnlyAfterDeadlineWhenQuorumIsSatisfied() {
        List<ProviderReply> replies = List.of(
            accepted("FAST", "80000"),
            accepted("ECONOMY", "65000"));

        ScatterDecision before = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE.minusSeconds(1));
        assertEquals(DecisionStatus.WAITING, before.status());

        ScatterDecision after = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE);
        assertEquals(DecisionStatus.ACCEPTED_PARTIAL, after.status());
        assertEquals(2, after.respondedCount());
        assertEquals(List.of("GLOBAL"), after.missingProviders());
    }

    @Test
    void strictPolicyFailsWithSameTwoRepliesAtDeadline() {
        List<ProviderReply> replies = List.of(
            accepted("FAST", "80000"),
            accepted("ECONOMY", "65000"));

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(false), replies, DEADLINE);

        assertEquals(DecisionStatus.FAILED, result.status());
        assertEquals(List.of("GLOBAL"), result.missingProviders());
    }

    @Test
    void requiredProviderMissingCannotBeOverriddenByQuorum() {
        List<ProviderReply> replies = List.of(
            accepted("ECONOMY", "65000"),
            accepted("GLOBAL", "60000"));

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE);

        assertEquals(DecisionStatus.FAILED, result.status());
        assertEquals(List.of("FAST"), result.missingProviders());
    }

    @Test
    void completeAndSuccessfulRepliesAreAcceptedComplete() {
        List<ProviderReply> replies = List.of(
            accepted("FAST", "80000"),
            accepted("ECONOMY", "65000"),
            accepted("GLOBAL", "60000"));

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE.minusSeconds(2));

        assertEquals(DecisionStatus.ACCEPTED_COMPLETE, result.status());
        assertEquals(3, result.respondedCount());
        assertTrue(result.missingProviders().isEmpty());
    }

    @Test
    void terminalRejectionFromMandatoryProviderFailsEarly() {
        List<ProviderReply> replies = List.of(
            new ProviderReply("FAST", ProviderStatus.REJECTED, null));

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), replies, DEADLINE.minusSeconds(4));

        assertEquals(DecisionStatus.FAILED, result.status());
        assertEquals("MANDATORY_PROVIDER_REJECTED", result.reasonCode());
    }

    @Test
    void duplicateReplyDoesNotCountAsAnotherProvider() {
        ProviderReply fast = accepted("FAST", "80000");

        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), List.of(fast, fast), DEADLINE);

        assertEquals(1, result.respondedCount());
        assertEquals(DecisionStatus.FAILED, result.status());
    }

    @Test
    void conflictingDuplicateMustNotChooseRandomWinner() {
        assertThrows(IllegalArgumentException.class, () ->
            ScatterDecisionPolicy.evaluate(
                plan(true), List.of(
                    accepted("FAST", "80000"),
                    accepted("FAST", "70000")), DEADLINE));
    }

    @Test
    void noReplyFailsAtDeadlineRatherThanInventingSuccess() {
        ScatterDecision result = ScatterDecisionPolicy.evaluate(
            plan(true), List.of(), DEADLINE);

        assertEquals(DecisionStatus.FAILED, result.status());
        assertEquals(0, result.respondedCount());
        assertEquals(3, result.missingProviders().size());
    }
}
~~~

**These are business unit tests**; they do not prove Gatherer, Scheduler, MessageGroupStore, or external providers work properly. They let you verify policy rules without waiting 5 seconds per test.

### 15.2. Additional test needed: all replied, one rejected

An important case not covered in the JUnit example above:

~~~text
FAST: ACCEPTED
ECONOMY: REJECTED
GLOBAL: ACCEPTED

Expected group size = 3
Received group size = 3
Accepted count = 2

Strict policy  -> FAILED
Partial policy -> ACCEPTED_PARTIAL
Completeness   -> ALL_RESPONDED
~~~

Therefore, **"partial" in business policy does not necessarily mean "missing replies"**. You can have **all replies** yet only **partial** acceptance. Retain both dimensions `completeness` and `business decision` in responses/metrics when explaining outcomes.

## 16. Integration tests for Spring Integration Scatter-Gather

To test the full flow, replace external providers with **test handlers** or **Gateway stubs** whose responses you control. Use `QueueChannel` to collect the final result, and test each scenario with bounded timeouts.

### 16.1. Happy path 3/3 test

~~~text
Given:
  ScatterPlan expected = [FAST, ECONOMY, GLOBAL]
  All three fake handlers return a valid ProviderReply
  Reply messages preserve executionId/correlation

When:
  Send QuoteRequest into quotes.in

Then:
  Gatherer emits one combined group
  Policy result = ACCEPTED_COMPLETE
  Unique respondent count = 3
  No duplicate final output
  Each provider received exactly one request
~~~

Assert **the exact set of recipients scattered to**, not just that Gatherer emitted an output. If all three test handlers fired due to a duplicate misconfiguration, the group might look "full" while actually missing another provider.

### 16.2. Partial timeout 2/3 test

~~~text
Given:
  FAST replies at once
  ECONOMY replies at once
  GLOBAL deliberately does not reply
  ScatterPlan allows partial after deadline

When:
  Start scatter-gather execution
  Trigger the configured group expiry / deadline
  Wait for final output with a bounded timeout

Then:
  One final decision = ACCEPTED_PARTIAL
  Missing provider = GLOBAL
  Caller does not see an unqualified "complete" result
  No second final decision after deadline
~~~

**Do not use arbitrary `Thread.sleep` to guess timeout timing.** Tests should use a controllable `TaskScheduler`/clock or short deadlines with conditional awaits with enough margin to avoid CI flakiness. Remember group timeout differs from request deadline.

### 16.3. Strict failure test with the same data

With **the exact same two replies FAST + ECONOMY**, but `allowPartial=false`, assert:

- Final outcome is `FAILED`, reason `DEADLINE_WITHOUT_REQUIRED_RESULTS`.
- Missing list contains `GLOBAL`.
- Side-effectful downstream handlers of the **accepted flow** are not invoked.
- Error/rejection is emitted per explicit contract, not silently dropped.
- The entire scatter is not retried infinitely.

### 16.4. Zero-replies test

Prevent any fake provider from replying. Verify:

1. The deadline watcher (started from `ScatterExecution`) sees an open execution.
2. No `MessageGroup` exists in Gatherer if no reply arrived.
3. The finalizer emits `FAILED(NO_REPLIES)` or `QuoteTimedOut` exactly once.
4. Gateway/caller receives a timeout response per SLA.
5. No late reply can spawn a new execution on its own.

### 16.5. Testing duplicates, out-of-order, late replies, and races

| Scenario | What to assert |
| --- | --- |
| Replies arrive `GLOBAL → FAST → ECONOMY` | Grouped properly regardless of arrival order |
| FAST sends twice | Unique reply count remains 1 |
| FAST sends two different prices | Quarantine/conflict; no random price selected |
| Reply from unexpected provider | Rejected before Gatherer |
| Reply missing executionId | Not misgrouped; clear error path |
| GLOBAL arrives after PARTIAL | Late/reconcile; no second final emitted |
| All three finish right at deadline | One final outcome via atomic finalization |
| Scheduler not running | Alert fires; group does not wait forever |
| Restart when only 2/3 arrived | Matches MessageGroupStore/recovery contract |
| Two JVMs process same group | Locks/CAS/shared-state prevent double-release |

Integration tests must **isolate state**; do not reuse the same execution ID across tests if `MessageGroupStore` or the context is cached without cleanup.

## 17. Release and completion with request–reply Gateway

If the caller uses `@MessagingGateway` or a Gateway waiting on Scatter-Gather, understand:

- **Gateway reply timeout** is the wait limit at the caller boundary.
- **Recipient timeout** is the timeout of an individual call to a provider.
- **Group timeout** is the Gatherer's wait/expiry policy.
- **Business deadline** is the absolute SLA defined by the workflow.

Values must align. For example, a 5-second business deadline with a 3-second Gateway timeout causes the caller to give up before the system evaluates partial, even though the Gatherer could respond at second 5.

Similarly, a 60-second Gateway timeout with a 5-second business deadline makes the caller wait needlessly if the finalizer fails to emit output. **Timeouts across layers do not replace each other.**

### 17.1. What should be returned to the client on partial?

A response may carry:

~~~json
{
  "requestId": "REQ-901",
  "executionId": "RUN-901",
  "status": "ACCEPTED_PARTIAL",
  "completeness": "MISSING_REPLIES",
  "acceptedQuotes": [
    {"providerId": "FAST", "price": 80000},
    {"providerId": "ECONOMY", "price": 65000}
  ],
  "missingProviders": ["GLOBAL"],
  "selectedProvider": "ECONOMY",
  "policyVersion": "quote-policy-v2"
}
~~~

Depending on the contract, the system may return an appropriate HTTP status code and body state. **Do not assume partial always maps to one specific HTTP code.** In financial/insurance APIs, a partial may be a **pending** state rather than letting the user proceed with a transaction.

### 17.2. Business responses must not leak internal provider lists

If provider names, internal routes, or sensitive prices must stay hidden externally, the response DTO needs a proper **projection**. Internal `ScatterDecision` can retain broader details; the outbound Transformer exports only fields the client is authorized to see.

## 18. Measuring effectiveness: latency vs. result quality

Partial-vs-fail decisions always involve **trade-offs** among latency, availability, completeness, and correctness.

| Metric | Question answered | Caveat |
| --- | --- | --- |
| `scatter_request_count` | How many scatter runs started? | Not equal to total requests sent to providers |
| `recipient_request_count` | How many requests did each provider receive? | Retries increase this count |
| `reply_valid_count` | How many valid replies arrived? | A valid reply can still be REJECTED |
| `unique_accepted_count` | How many accepted providers? | Deduplicated by logical provider |
| `partial_accepted_count` | How many partial results were usable? | Distinguish quality from full success |
| `strict_failed_count` | How many requests failed completely? | Due to deadline, mandatory miss, or rejection |
| `no_reply_count` | How many requests received zero replies? | Requires request-level watcher |
| `late_reply_count` | How many replies arrived after close? | May signal SLA/network issues |
| `group_open_age` | Are groups lingering too long? | Alerts on leaks/reaper failures |
| `provider_latency_p95/p99` | Which provider causes deadline breaches? | Measuring only successful replies causes survivor bias |
| `business_conversion/outcome` | Was partial actually useful? | Do not look only at dispatch success rate |

### 18.1. Do not optimize solely for partial-accepted rate

A policy accepting partial immediately after the first reply cuts latency sharply yet **increases the risk of high prices**, incomplete data, or compliance breaches.

Track **decision quality**, such as the gap between the price selected at partial time and the optimal price across all quotes once late ones arrive, if policy and data ethics allow measuring it. Never use late data to silently alter an already-confirmed transaction.

### 18.2. Logging and metric cardinality

`executionId`, `requestId`, `customerId`, and `correlationId` have high cardinality: put them in access-controlled logs/traces, never as aggregated metric tags. Tags like `providerType`, `decisionStatus`, `timeoutReason`, and `policyVersion` are more controllable, though their value sets must still be bounded and payload PII/secrets kept out of logs.

## 19. Anti-patterns to avoid

| Anti-pattern | Consequence | Better approach |
| --- | --- | --- |
| 2/3 replies automatically treated as success | Replies could be REJECTED or duplicates | Count unique accepted providers and evaluate policy |
| Changing expected from 3 to 2 after timeout | Hides the missing provider | Keep original expected set, mark partial |
| Using `group.size()` as quorum | Duplicates create fake quorum | Deduplicate by provider/business ID |
| Treating `sendPartialResultOnExpiry(true)` as business success | Caller misuses incomplete data | Business decision processor after Gatherer |
| Using only group timeout for zero replies | No group exists to expire | Request-level deadline watcher |
| Setting `groupTimeout=5000` and claiming T0+5 SLA | Deadline may reset on group activity | Persist `deadlineAt` independently |
| Treating every HTTP error as REJECTED | Network error differs from business refusal | Separate terminal business/technical/unknown |
| Disabling partial with no error/reply path | Gateway hangs until obscure timeout | Explicit failed/timeout response |
| Failing all without compensating side effects | Committed resources/money remain dangling | Saga/compensation/reconciliation |
| Retrying whole scatter when one provider drops | Re-sends to already-succeeded providers | Per-recipient retry with idempotency |
| Deleting group and forgetting late replies | Creates new group or second final | Tombstone/closed-state |
| Letting caller pick mandatory providers | Bypasses mandatory rules | Trusted routing policy and authorization |
| Using `MessageHeaders.id` as business key | Replay generates a different ID | Stable operation ID, provider ID |
| Testing only policy without reply routing | Wiring bugs still time out | Integration test real scatter/gather |
| Testing timeouts with fixed `Thread.sleep` | Flaky under CI load | Controllable clock/scheduler or bounded await |
| Logging every raw reply to debug | Leaks PII/partner data | Log reasons and minimal metadata |

## 20. Pre-deployment checklist

- [ ] Defined **expected recipient set** and **mandatory recipient set** from a trusted policy.
- [ ] Distinguished **valid reply**, **accepted business result**, **rejected terminal result**, **technical error**, and **unknown/missing**.
- [ ] Documented decision table for strict, partial, quorum, mandatory, and fail-fast.
- [ ] Prevented duplicates from inflating successful provider counts.
- [ ] Froze `ScatterPlan` and `policyVersion` per execution; never change semantics on replay.
- [ ] Distinct `executionId`/correlation per run, plus stable idempotency keys for side effects.
- [ ] Configured Scatterer/Gatherer/reply channels with proper topology, preserving headers across adapters.
- [ ] Defined release strategy and timeout/partial expiry tested on your Spring Integration version.
- [ ] Request-level deadline watcher handles **zero replies** and absolute deadlines.
- [ ] Closed-state/tombstone prevents late replies from creating a second final outcome.
- [ ] Fail-all has compensation/reconciliation rules when recipients cause side effects.
- [ ] Gateway timeout, recipient timeout, group timeout, and business deadline align.
- [ ] Policy unit tests and integration tests cover happy/partial/strict/no-reply/duplicate/late/race cases.
- [ ] Suitable `MessageGroupStore`/recovery exists if workflows must survive restarts.
- [ ] Monitored open groups, timeouts, missing recipients, partial quality, late replies, and idempotent finalization.
- [ ] No raw payloads or sensitive data leak via logs/metric tags/outbound responses.

## 21. Practice exercise

A corporate credit-limit approval service sends a request to three departments: `COMPLIANCE`, `RISK`, and `CREDIT`. All three respond `APPROVED`, `REJECTED`, or fail to respond before an 8-second deadline. By rule:

- `COMPLIANCE` is mandatory.
- `RISK` and `CREDIT` are two supplemental evaluators.
- Approval is granted only if `COMPLIANCE=APPROVED` **and** at least one of `RISK`, `CREDIT` is also `APPROVED`.
- `REJECTED` from `COMPLIANCE` fails the request immediately.
- If a source has not replied yet, returning **`PENDING_PARTIAL`** to display progress is allowed, **but executing the disbursement command is forbidden** on that result.

**Tasks:**

1. Diagram Scatter-Gather with three recipients, Aggregator, business decision processor, and output channels `approved`, `pending`, `failed`.
2. Build a decision table for 0/1/2/3 reply combinations, missing mandatory, terminal rejection, and timeout.
3. Define `ScatterPlan` with `executionId`, `deadlineAt`, `expectedSet`, `mandatorySet`, `policyVersion`.
4. Distinguish "eligible to recommend approval" from "authorized to disburse"; explain why a partial view does not equal a final legal decision.
5. Design correlation, release strategy, and timeouts, preventing a duplicate `RISK` from creating a false quorum.
6. Write unit tests with a fake clock and no `Thread.sleep` for one strict condition and one partial condition.
7. Design a request-level watcher for 0 replies and a late-reply path after request closure.
8. When an external service times out yet may have recorded a result, propose reconciliation/idempotency instead of assuming rejection.
9. Propose observability: open groups, missing/rejected, policy version, retries, late replies, and final decisions, without exposing personal data.

**Hint:** this exercise's policy **differs** from the quoting example: partial here is permitted only as **an incomplete observational status**, never as authority to trigger disbursement side effects. Separate two enums or statuses: `decisionCompleteness` and `authorizationToDisburse`.

## 22. Summary

**Accepting a partial result vs. failing completely** is a **business decision** layered atop Scatter-Gather mechanics. The Scatterer distributes the request; Gatherer/MessageGroupStore/correlation collects replies and decides when to release or expire. However, **enough messages does not mean enough useful results**, and **releasing a group does not grant authority to execute the next business step**.

A solid design preserves the original expected set, validates **unique provider replies**, defines **mandatory recipients**, minimum result thresholds, deadlines, how partials are returned, and fail-all behavior. With Spring Integration, configure Scatter-Gather, Aggregator, `groupTimeout`, `sendPartialResultOnExpiry`, reply routing, and error channels properly; add a **deadline watcher for 0 replies**, closed-state/tombstones for late replies, idempotency, and compensation for side effects. Test **completeness, business decisions, near-deadline races, and single final outcome emission** so the system stays fast, contract-compliant, and traceable.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Scatter-Gather, Recipient List, Aggregator, Correlation Identifier); Spring Integration documentation on Scatter-Gather, Aggregators, Message Groups, Java DSL, Error Handling, and Testing; Java SE documentation on `Set`, `Map`, `Instant`, `BigDecimal`, and concurrency primitives.
