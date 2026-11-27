# Terminating when the route ends

## 1. The problem: what happens after the final step?

An order-processing system has the steps **validate → charge → audit**. Each order may pass through different steps: already-paid orders skip `charge`, while high-risk orders add `review`. Instead of building multiple fixed Routers, the system attaches a list of destinations to the message and lets endpoints process it in turn. That is **Routing Slip** in Enterprise Integration Patterns (EIP).

Sample path:

~~~text
OrderCommand
    → validate
    → charge
    → audit
    → [routing slip exhausted]
    → ?
~~~

That final question mark is crucial: **does exhausting the route list mean the message is dropped, the transaction is automatically completed, or the result is sent back to the caller?**

In **Spring Integration**, Routing Slip is represented by the `routingSlip` header. When an endpoint is capable of producing a reply and **does not configure its own output channel**, the framework can obtain the next destination from this header. **Once the path in the routing slip is exhausted, normal `replyChannel` handling resumes**. Therefore, *routing slip exhausted* does not mean *business workflow completed*, nor does it automatically emit a completion event. To confirm successful processing, you must observe the final endpoint's result and the flow's reply contract.

This lesson belongs to the **Routing slip** chapter in the **SPRING_INTEGRATION_PATTERN** module. The topic helps practice Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows while combining **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel, and correlation**, along with testing and observing processing branches.

**Expected outcomes:** understand the path-traversal algorithm, know when a routing slip is truly exhausted, distinguish a natural stop from errors or non-replying handlers, design intentional reply/terminal behavior, and write tests verifying each scenario.

## 2. Routing Slip is not a single-branch Router

A **Content-Based Router** typically decides *one next destination* from message content. **Routing Slip** carries an *itinerary* consisting of multiple steps and the current progress along that itinerary. Each processing step can pass the message to the next step without knowing the whole topology.

| Criterion | Content-Based Router | Routing Slip |
|---|---|---|
| Core question | Which channel should the message go to right now? | Which channels does the message still need to traverse? |
| Where decision lives | Router config or method/SpEL | Header storing the path and current position |
| Progression | Computes one branch per routing point | Traverses steps along the declared path |
| Termination point | Depends on target branch/consumer | When no routes remain and normal reply handling applies |
| Suitable scenarios | VN/US classification, event types | Request-varying workflows, multiple sequential steps |
| Main risks | Unknown keys, wrong mappings | Lost headers, route loops, missing replies, too many steps |

In Spring Integration's implementation, a routing slip is not a self-driving loop running the entire itinerary on its own. **Each handler must actually produce a reply** so the framework can resolve the next output channel. No reply means no message to forward.

## 3. Path and position counter

A routing slip can be understood via two components:

1. **Path:** list of routing steps/directives, e.g., `[orders.charge, orders.audit]`.
2. **Index:** position of the element currently being evaluated in the list.

In Spring Integration, `RoutingSlipHeaderValueMessageProcessor` creates a routing slip value with the resolved path and an initial index of `0`. When an entry is a channel name that resolves successfully, the routing slip forwards to that channel and increments the index in the reply message. **The path is not shortened; the index advances**.

~~~mermaid
flowchart LR
    IN["orders.validate<br/>reply: OrderState"] --> P0["Index 0: orders.charge"]
    P0 --> CH["Charge handler<br/>reply: OrderState"]
    CH --> P1["Index 1: orders.audit"]
    P1 --> AU["Audit handler<br/>reply: OrderState"]
    AU --> END{"Index ≥ path.size?"}
    END -->|"Yes"| RP["Fallback: normal replyChannel"]
~~~

**Note:** the example starts with `orders.validate` via the output channel configured where the routing slip is attached. Therefore, the path in the header only needs to list **the subsequent steps**, here `orders.charge` and `orders.audit`. Do not repeat `orders.validate` in the path unless you want to run validation twice.

An illustrative itinerary:

| Time | Endpoint just executed | Unchanged path | Next index | Action |
|---|---|---|---:|---|
| T0 | Header enricher → Validate | `charge, audit` | 0 | Enters validation |
| T1 | Validate returns reply | `charge, audit` | 0 → 1 | Routes to Charge |
| T2 | Charge returns reply | `charge, audit` | 1 → 2 | Routes to Audit |
| T3 | Audit returns reply | `charge, audit` | 2 (path exhausted) | Evaluates `replyChannel` |
| T4 | Reply sent to Gateway | No Routing Slip steps left | — | Caller receives result |

T3 only happens when Audit **returns a valid reply** and the flow preserves the reply context. If Audit is a `void` handler or returns `null`, the flow may stop right there **without ever performing the next routing-slip lookup**.

## 4. Exact termination rules in Spring Integration

Official documentation describes Routing Slip at the step of **selecting an output channel for an `AbstractMessageProducingHandler`**. The algorithm is consulted when the endpoint produces a reply **and specifies no `outputChannel`**.

Important rules:

1. Retrieve the entry at `routingSlipIndex` from the path.
2. If the entry is a `MessageChannel` bean name, use that channel as output and increment the index in the reply.
3. If the entry is a `RoutingSlipRouteStrategy`, invoke the strategy to decide the channel name.
4. When the strategy returns a valid channel, **the index stays on that strategy entry**; the strategy can be invoked again on the next turn.
5. When the strategy returns `null` or an empty string, the framework skips past the strategy entry by incrementing the index, then inspects the next entry.
6. **When the index moves past the last element, normal `replyChannel` behavior resumes.**

Therefore, **"route exhausted" means no destinations remain along the header itinerary**—it does not mean there must be a channel named `finish` or `done`. If you want a mandatory result-handling step before returning, add that step to the path or configure an explicit terminal handler.

One easily overlooked detail: **an endpoint's explicitly declared output channel takes precedence**. If `orders.charge` has a fixed output channel `orders.next`, the routing slip does not decide the next step at that point. The result may take an unintended detour or prevent the routing slip from advancing as designed. Avoid mixing fixed outputs and routing slips without documenting why.

## 5. A complete three-step request–reply example

The example below uses a Java record so state changes are easy to observe across each step:

~~~java
public record OrderState(
    String orderId,
    boolean validated,
    boolean charged,
    boolean audited
) {}
~~~

**Gateway** is where the caller submits a request and waits for a result; the reply is returned via Spring Integration messaging mechanics:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.entry")
public interface OrderProcessingGateway {
    OrderState process(OrderState order);
}
~~~

Attach the routing slip using a **HeaderEnricher**. This is Java configuration based on Spring Integration's `RoutingSlipHeaderValueMessageProcessor` component:

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderRoutingSlipConfiguration {

    @Bean
    @Transformer(
        inputChannel = "orders.entry",
        outputChannel = "orders.validate")
    public HeaderEnricher attachRoutingSlip() {
        return new HeaderEnricher(Collections.singletonMap(
            IntegrationMessageHeaderAccessor.ROUTING_SLIP,
            new RoutingSlipHeaderValueMessageProcessor(
                "orders.charge",
                "orders.audit")));
    }
}
~~~

Setting `outputChannel = "orders.validate"` on the HeaderEnricher is intentional: it sends the message **into the first step**. Afterwards, the Service Activators do not specify their own output channels, letting Routing Slip take control:

~~~java
@MessageEndpoint
public class OrderStepHandlers {

    @ServiceActivator(inputChannel = "orders.validate")
    public OrderState validate(OrderState input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new IllegalArgumentException("Missing orderId");
        }
        return new OrderState(
            input.orderId(), true, input.charged(), input.audited());
    }

    @ServiceActivator(inputChannel = "orders.charge")
    public OrderState charge(OrderState input) {
        if (!input.validated()) {
            throw new IllegalStateException("Order not validated");
        }
        return new OrderState(
            input.orderId(), true, true, input.audited());
    }

    @ServiceActivator(inputChannel = "orders.audit")
    public OrderState audit(OrderState input) {
        if (!input.charged()) {
            throw new IllegalStateException("Order not charged");
        }
        return new OrderState(
            input.orderId(), true, true, true);
    }
}
~~~

**Expected path:** `orders.entry → orders.validate → orders.charge → orders.audit → Gateway's replyChannel`. The final result has all three flags set to `true`. The example assumes handlers return normal objects, channels dispatch synchronously, and the reply context set by the Gateway is preserved throughout the message flow.

This is an academic illustration: real payment and audit operations are side effects requiring dedicated ports, transactions/idempotency, and error observability. The code intentionally transforms only immutable state to highlight the requirement that **handlers must return a reply**.

### Why does this flow actually exhaust the route?

The header enricher creates a path with **two** entries. When Validate produces a reply, the first entry sends the message to Charge. When Charge produces a reply, the second entry sends the message to Audit. When Audit produces a reply, there is no third entry; the framework falls back to inspecting the message's standard `replyChannel`. If the Gateway is still waiting and the reply is delivered successfully, the caller receives the final `OrderState`.

**Do not** append `orders.entry` to the end of the path to "send the result back to the start"; that can create a processing loop. The Gateway's return path is managed by `replyChannel`, not by routing back into the request channel.

## 6. How does exhausting the routing slip differ from completing the whole workflow?

Distinguish four milestones:

| Milestone | What happened | What is **not** yet guaranteed |
|---|---|---|
| **Routing slip exhausted** | No coordination entries remain in the header | Does not prove side effects have committed |
| **Final handler returns reply** | A result message exists for dispatch | Does not prove the caller received it |
| **Gateway receives reply** | Synchronous call has a result | Does not prove downstream notifications/brokers acknowledged |
| **Business workflow completed** | Defined business completion criteria are satisfied | Never inferred solely from an index or a boolean `send()` |

For example, Audit returns `OrderState(audited=true)`, yet an email-sending or ledger-posting task is still running asynchronously. The Gateway receiving a reply does not prove those other tasks finished. If the business requires all mandatory steps to succeed, model them explicitly in the flow using result/status, transaction boundaries, and intentional aggregation.

For fire-and-forget messages, there may be no caller waiting on `replyChannel`. In that case, terminating the Routing Slip should be represented by a meaningful **terminal consumer** or a completion event; do not assume exhausting the path automatically signals external systems.

## 7. Why do `void` or `null`-returning final handlers cause confusion?

Consider two handler styles:

~~~java
@ServiceActivator(inputChannel = "orders.audit")
public OrderState auditWithReply(OrderState order) {
    return auditService.markAudited(order);
}

@ServiceActivator(inputChannel = "orders.audit")
public void auditWithoutReply(OrderState order) {
    auditService.writeOnly(order);
}
~~~

**The two snippets above are alternatives**, not declared simultaneously on the same channel in the sample application.

`auditWithReply` creates a reply so the framework can continue resolving the destination. Once the path is exhausted, the reply can return to the Gateway. `auditWithoutReply` only performs a side effect and finishes the handler; there is no reply message for the routing slip mechanism to forward. If the Gateway expects a result, it may wait until timeout.

Therefore, define the **final endpoint's contract** explicitly:

- **Request–reply:** the final handler returns `OrderResult`/`OrderState` so the caller receives the result.
- **One-way:** the final handler intentionally does not reply, and the caller must not wait for a synchronous response; provide another ack/status mechanism if required.
- **Confirmed completion:** the final handler emits a completion event or persists durable status with retry/idempotency policies.
- **Error termination:** the handler throws an exception; this is the error path, not "normal route exhaustion" behavior.

**Check question:** after a message reaches the end of the path, who owns responsibility for confirming completion—the Gateway, a terminal handler, a state store, or an upstream broker? If you cannot point to one, the design may have "run out of road" without "finishing the job".

## 8. What happens when there is no `replyChannel`?

The framework rule is **to fall back to standard reply handling**, which does not promise that a valid reply channel exists. Actual behavior depends on the endpoint type, communication pattern, and message configuration:

1. **With Gateway/request–reply:** the Gateway typically creates or manages a reply channel; the final handler returns a reply and the caller receives the result when everything works properly.
2. **No caller waiting for a reply:** there may be no channel receiving the final result; design a suitable terminal sink or output channel.
3. **Invalid reply channel or no subscriber:** the message may encounter a delivery error, or the flow may not reach the desired state depending on configuration.
4. **Reply channel altered/lost at an adapter:** the Gateway may time out even though some steps already ran.

**Do not add a "default termination mode" by deleting the routing slip header mid-flow**. That changes semantics: while later steps have not run yet, the flow might send an early reply. If you need to short-circuit the process, decide via a route strategy or a coordinator with an explicit termination contract.

## 9. RoutingSlipRouteStrategy can decide when to advance steps

A path does not have to contain only static channel names. An entry can be a `RoutingSlipRouteStrategy`; the strategy inspects the **request message** and **current reply** to return the next channel name.

Key distinction:

- Strategy returns a **non-empty channel name**: sends the message to that channel, **without incrementing the index**. The strategy can be invoked again next time.
- Strategy returns **`null` or an empty string**: the strategy entry is considered finished; the framework increments the index to inspect the next entry.
- Once the path is exhausted: returns to normal `replyChannel` behavior.

~~~mermaid
flowchart TD
    Q["Endpoint produces reply, no outputChannel"] --> I["Read routingSlipIndex"]
    I --> D{"Current entry?"}
    D -->|"MessageChannel"| C["Send to channel, increment index"]
    D -->|"RoutingSlipRouteStrategy"| ST["Call getNextPath(request, reply)"]
    ST -->|"Channel name"| SAME["Send to channel, keep index"]
    ST -->|"null / empty"| NEXT["Increment index"]
    NEXT --> I
    D -->|"Path exhausted"| RP["Use standard replyChannel"]
~~~

For example, routing logic might require multi-pass state checks:

~~~text
Path = [reviewStrategy, auditChannel]

Pass 1: reviewStrategy returns "reviewChannel" → process review
Pass 2: reviewStrategy returns "reviewChannel" → re-check
Pass 3: reviewStrategy returns null            → skip strategy, go to auditChannel
Pass 4: Audit returns reply, path exhausted    → replyChannel
~~~

**Loop risk:** if the strategy always returns the same channel with no exit condition, the index never increments and the message can loop forever. Enforce hop limits, timeouts, progress state, and testable exit criteria.

**Reply type mismatch risk:** a POJO service's reply can be a plain domain object rather than a `Message<?>`. If a strategy's SpEL references `reply.headers` when the actual reply is just `OrderState`, the expression can fail. Control accepted types and only access properties that actually exist.

## 10. Exposing intentional termination states

In practice, stakeholders usually need to know **whether an order succeeded or failed**. Three ways exist to express a completion contract:

| Approach | When to use | Contract |
|---|---|---|
| **Gateway reply** | Short, synchronous tasks where caller waits | Returns result after final step emits reply and routing slip is exhausted |
| **Terminal handler + completion event** | Many asynchronous systems | Persists state and emits `OrderCompleted` when criteria are met |
| **Stateful process manager** | Long processes with multiple retries/branches | Persists progress, timeouts, compensation, checkpoints |

When using a completion event, have a single emission point where idempotency can be controlled. Do not let every handler seeing "no routes left" emit the same event on its own, as retries could emit duplicates.

A business result record:

~~~java
public record ProcessResult(
    String orderId,
    String outcome,       // COMPLETED / REJECTED / FAILED
    String lastStep,
    String correlationId
) {}
~~~

`lastStep` is metadata to aid tracing, not proof that side effects committed. When billing, inventory, or payment are involved, only use outcome `COMPLETED` when published business criteria are met.

## 11. When the route is empty from the start

A message might receive a routing slip with no valid entries, or a route strategy might return null/empty immediately. Distinguish clearly:

| Scenario | Design responsibility |
|---|---|
| **Valid empty itinerary** | Define whether an immediate reply should be returned |
| **No itinerary declared yet business requires mandatory steps** | Reject/validation error; never mark as completed |
| **Strategy intentionally returns null** | Advance to the next entry or reply per rules |
| **Channel name in path does not exist** | This is a config/resolution error, not successful completion |
| **Message loses routingSlip across a broker** | Missing coordination metadata; recover from state store or reject per contract |

If using request–reply for a no-op case, it is better to return a result from an explicit terminal endpoint rather than relying on implicit empty-path behavior in a topology lacking a reply producer.

**Never take routes directly from unvalidated user data.** Channel lists must only be chosen from an application-allowlisted set; invalid values must never become permission to route to an arbitrary bean.

## 12. Route exhaustion ≠ exception, Filter discard, or timeout

The following phenomena are easily confused in logs:

| Symptom | Possible cause | Classification |
|---|---|---|
| Index reached end of path and caller received reply | Normal routing slip exhaustion | **Path coordination completed** |
| A handler returned `null` | Produced no reply to continue | **Flow stopped early**, not path exhaustion |
| Filter dropped the message | Predicate failed; may have a discard channel | **Message filtered out** |
| Handler threw an exception | Business/technical failure | **Error path**, never treat as completion |
| Channel name failed to resolve | Route config/bean error | **Routing error** |
| Caller timed out | No reply received in time | **Insufficient information** to conclude handler did not run |
| Broker redelivered message | Missing ack or redelivery policy | **Delivery retry**, prior side effects may exist |

**Important practice:** dashboards should have separate metrics for *routing-slip-exhausted*, *terminal-success*, *terminal-error*, *timeout*, and *early-stop*. Do not lump everything together as "done"; otherwise lost messages and retry loops become untraceable.

## 13. Retry and idempotency after traversing several steps

Suppose the path is `validate → charge → audit`. Charge succeeded in collecting payment, then Audit suffers a network error. If you retry the **entire** Gateway call from the beginning:

~~~text
Attempt 1:
validate: OK
charge: PAYMENT COLLECTED
audit: TIMEOUT
caller: exception/timeout

Attempt 2:
validate: OK
charge: RISK OF DOUBLE CHARGING
audit: ...
~~~

Routing slip does not durably record "Charge committed" and does not guarantee exactly-once execution. Whenever side effects exist, each step needs:

1. **Stable idempotency key**: e.g., `orderId + actionType` or event ID; enforce uniqueness where the side effect executes.
2. **Checkpoint/progress store** if you need to resume from completed steps after a restart.
3. **Bounded retries** based on error type; validation errors should never retry endlessly.
4. **Transaction/outbox** when database updates and event emission must stay consistent.
5. **Compensation** for long-running business flows when distributed rollback is impossible.

Never use `routingSlipIndex` as proof of payment success; the index reflects route dispatch progress, not a transaction log. A message may have been forwarded while a downstream handler still failed.

## 14. Routing Slip in distributed environments: serializability

Spring Integration allows a path to contain channel names, `RoutingSlipRouteStrategy` names, or SpEL expressions. Within a single JVM, dynamic expressions can be convenient; **across brokers, persistent MessageStores, or JVM boundaries, you must consider serializability**.

Inline expressions can be converted by the framework into `ExpressionEvaluatingRoutingSlipRouteStrategy` objects, which depend on `BeanFactory` and are not serializable. Sending a message containing such an object through serialization can throw `NotSerializableException`.

**Practical recommendations:**

- Across distributed boundaries, avoid putting JVM-bound strategy/expression objects into wire headers.
- If a SpEL-based strategy is needed, register the strategy as a named bean per documentation and configure compatible entries.
- Represent itineraries as pure-data DTOs/step IDs when crossing brokers; at each boundary service, reconstruct the routing context according to that service's contract.
- Test serialize → deserialize → resume from checkpoint, not just in-JVM execution.
- Separate internal coordination routing metadata from public business events so external parties cannot tamper with paths.

In particular, **do not blindly serialize all Spring MessageHeaders to JSON**: some headers contain internal objects like reply channels, error channels, or route strategies; some objects are non-serializable or unsafe to exchange with external systems.

## 15. Routing Slip, Gateway, and timeouts

In a synchronous flow, the Gateway typically waits for the reply from the final handler after the path is exhausted. However, the wait time depends on **all steps**, not just the final one:

\[
T_{\text{gateway}} \approx T_{\text{validate}} + T_{\text{charge}} + T_{\text{audit}} + T_{\text{overhead}}
\]

If `charge` waits too long on a payment gateway, the Gateway may time out before the message reaches Audit; if `audit` returns `null`, the Gateway may also wait even though prior side effects already executed.

Adding `ExecutorChannel`, `QueueChannel`, or a broker introduces asynchronous execution boundaries and different reply/error mechanics. Design **replyChannel propagation, timeouts, correlation, error channels, and delivery acknowledgements** at every boundary; routing slip does not solve these automatically.

**Never mark a transaction as failed merely because the Gateway timed out.** Before retrying, verify status via an idempotency key/checkpoint or a business status query.

## 16. Combining with Filter, Router, Splitter, and Aggregator

Routing Slip does not replace other patterns:

- **Filter** drops messages violating the contract before starting the itinerary, or routes them to a reject channel. Dropped messages must be reported to any caller waiting for a reply.
- **Content-Based Router** can choose among multiple routes before attaching a path, such as international orders needing an extra review.
- **Transformer** normalizes payloads while preserving required metadata to proceed.
- **Gateway** provides the request–reply/timeout contract at application boundaries.
- **Splitter/Aggregator** handles splitting a message into parts and combining results by correlation; Routing Slip alone does not perform group aggregation.

~~~mermaid
flowchart LR
    G["Gateway"] --> F{"Contract filter"}
    F -->|"Valid"| T["Transformer + attach Routing Slip"]
    F -->|"Invalid"| ERR["Reject / error reply"]
    T --> V["Validate"]
    V --> C["Charge"]
    C --> A["Audit"]
    A --> E{"Routing slip exhausted"}
    E --> R["replyChannel → Gateway"]
~~~

When a step in an itinerary uses a Splitter to emit multiple child messages, decide **whether each child carries the same routing slip**, who is responsible for aggregating, and when a reply should be returned to the original itinerary. If one request expects **one** final result, you generally need an Aggregator or a coordinator emitting exactly one reply.

## 17. Unit tests and integration tests: proving genuine route completion

Before end-to-end testing, unit-test individual handlers to confirm they return replies and do not trigger unexpected side effects. For `OrderStepHandlers`, unit tests verify:

~~~java
@Test
void stepsReturnNewStates() {
    OrderStepHandlers handlers = new OrderStepHandlers();
    OrderState initial =
        new OrderState("O-101", false, false, false);

    OrderState valid = handlers.validate(initial);
    OrderState charged = handlers.charge(valid);
    OrderState audited = handlers.audit(charged);

    assertTrue(audited.validated());
    assertTrue(audited.charged());
    assertTrue(audited.audited());
    assertFalse(initial.validated());
}
~~~

This unit test **does not** prove the routing slip itself works; it only checks the contract that "each step returns a result object". You must have an integration test with a real Spring Integration context:

~~~java
@SpringJUnitConfig(classes = {
    OrderRoutingSlipConfiguration.class,
    OrderStepHandlers.class
})
class RoutingSlipCompletionTest {

    @Autowired
    OrderProcessingGateway gateway;

    @Test
    void returnsResultAfterFinalStep() {
        OrderState result = gateway.process(
            new OrderState("O-101", false, false, false));

        assertTrue(result.validated());
        assertTrue(result.charged());
        assertTrue(result.audited());
    }
}
~~~

This is a test-oriented example; in actual use, configure Gateway interface scanning and Spring test integration properly (you can use `@IntegrationComponentScan` as in the configuration). No HTTP server, broker, or database is needed when all handlers run in-JVM.

### Minimum test matrix

| Case | Setup | What to prove |
|---|---|---|
| Full path traversal | Validate → Charge → Audit, all three return replies | Gateway receives result with all three flags set |
| Valid empty path | Terminal endpoint returns final reply per contract | No mandatory steps skipped; reply handled explicitly |
| Intermediate handler returns `null` | Charge emits no reply | Audit is not called; Gateway has clear timeout/error path |
| Final handler is `void` | Audit only runs side effect | Do not assume Gateway receives a reply |
| Failure at Validate | Blank `orderId` | Exception/error path; no payment charged |
| Failure at Charge | Payment service times out | Audit is not reported as succeeded; bounded retry |
| Non-existent channel | Path contains wrong bean name | Routing error observed; not treated as path exhausted |
| Handler has own output | Charge overrides outputChannel | Verify routing slip is not used at that step |
| Strategy returns channel | Dynamic strategy still picking branch | Index does not increment for the strategy on this pass |
| Strategy returns null/empty | Advance to next entry | Index increments; if exhausted, falls back to replyChannel |
| Strategy always returns channel | No exit condition | Hop limit/timeout and alert triggered |
| Caller timeout | Audit runs slowly | Do not conclude side effect has not happened |
| Redelivery of same order | Retry after Charge commits | No duplicate payment collected |
| Cross-JVM | Serialize message with routing slip | Contains no non-serializable objects/inline strategies |
| Splitter/Aggregator | Multiple child messages with correlation | Does not emit multiple unintended replies |

Swap production handlers for test doubles when counting invocations. Avoid testing "route exhaustion" solely by checking that the final log appears; logs do not prove a reply was emitted properly and received by the caller.

## 18. Observability: measuring itinerary progress and termination

An event can cross multiple endpoints and transform payloads. You need telemetry to answer three questions:

1. **Which step is the message currently on?**
2. **Did it exhaust the routing slip normally, stop early, or fail?**
3. **Did the final result reach its intended destination?**

Suggested signals:

| Signal | Purpose |
|---|---|
| `route.path.size` and `route.step.index` | Track total steps and current step |
| `route.step.name` | Identify the channel/handler currently executing |
| `route.step.duration` | Detect slow handlers |
| `route.exhausted.count` | Count cases that exhausted the itinerary |
| `route.early_stop.count` | Handler returned `null` or Filter dropped before path end |
| `route.error.count` by reason code | Classify runtime/mapping errors |
| `gateway.reply.duration` and timeouts | Monitor reply contract |
| `workflow.completed.count` | Count by business criteria, **never use index as a substitute** |

Depending on your Spring Integration/Micrometer version and configuration, some metrics must be instrumented manually in interceptors/handlers. **Metric names in the table are suggested names**, not claims of default framework metric names.

For tracing, preserve event ID, business ID, and trace/correlation context per contract. Do not put `orderId` or `eventId` in metric tags if cardinality is high; use access-controlled logs/traces. Never log full payloads or sensitive headers.

## 19. Common mistakes

**"Exhausting the route automatically completes the business workflow."** False. The framework only selects the next channel and falls back to `replyChannel`; transactions, side effects, acks, and process status must be designed separately.

**"A `void` handler automatically proceeds to the next route."** False in standard request–reply flows: without a reply, there is no message to dispatch further.

**"Adding a channel named `finish` to the path is mandatory."** Not mandatory. Standard `replyChannel` can be used; if a terminal sink is needed, define its termination behavior explicitly.

**"Returning a channel name from a strategy increments the index."** False. When `RoutingSlipRouteStrategy` returns a channel, the index does not increment; the strategy can be called again. It is only skipped once it returns null/empty.

**"An explicit `outputChannel` and a routing slip control a step equally."** False. An output configured on the handler takes precedence and can prevent the routing slip from being consulted at that step.

**"A Gateway timeout means Charge hasn't run."** False. The caller may have missed the reply while side effects already committed. Retries require idempotency and status queries.

**"Using inline SpEL expressions in a routing slip across a broker is always safe."** False. Generated strategy objects may not be serializable; use appropriate contracts/strategy beans and test across JVM boundaries.

**"The `routingSlip` header can be accepted directly from clients."** Unsafe: values could steer the flow into unauthorized channels, create loops, or bypass validation. Itineraries must be constructed/validated at the application boundary.

**"A message entering a Splitter returns exactly one reply when the routing slip is exhausted."** Not automatic: the number of child messages and the Aggregator's release strategy govern how results are emitted.

## 20. Practice exercise: verifying that a path truly terminates

Build an **OrderRoutingSlip** feature with three steps and a Gateway:

1. **Define contracts:** `OrderState` and `OrderProcessingGateway.process()` returning a synchronous result.
2. **Attach Routing Slip:** HeaderEnricher adds path `orders.charge → orders.audit` before sending to `orders.validate`.
3. **Write Service Activators:** each step returns a new state; declare no `outputChannel` on handlers meant to be coordinated by the routing slip.
4. **Happy path:** verify the caller receives validated, charged, and audited state without routing back into input.
5. **Early-stop:** change Audit to `void` to observe the difference between "no reply" and "routing slip exhausted then replied".
6. **Failure path:** make Charge throw an error, attempt a retry, and protect the side effect with an idempotency key.
7. **Dynamic strategy:** add an entry for conditional review; test returning a channel, returning null, and a potential loop case.
8. **Observability:** measure `route.step.index`, handler duration, completions, and timeouts by correlation ID.
9. **Cross-JVM:** if using a broker/persistent store, test serialization and itinerary recovery after restart.

**Completion criteria:** include a sequence diagram, explain index position before/after each step, prove the result returns via `replyChannel` once the path is exhausted, have tests distinguishing path exhaustion from `null` handlers/errors/timeouts, and document durability/idempotency limits.

## 21. Takeaways

In Spring Integration, **terminating when the route ends** means **no next destination remains in the `routingSlip` header**. When a handler produces a reply and defines no dedicated `outputChannel`, Routing Slip is used to pick the next channel; **once the path is exhausted, reply delivery reverts to normal `replyChannel` rules**.

Never equate path exhaustion with business success, never assume `void` handlers will advance, and never let a strategy loop endlessly. Define terminal behavior, retries, idempotency, error paths, and correlation explicitly, and test outcomes at both the Gateway and individual processing steps.

### References

- Spring Integration Reference, **Routing Slip**: https://docs.spring.io/spring-integration/reference/router/routing-slip.html
- Enterprise Integration Patterns, **Routing Slip**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/RoutingTable.html
