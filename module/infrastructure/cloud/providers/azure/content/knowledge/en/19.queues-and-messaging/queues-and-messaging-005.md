# Peek-Lock, Settlement, and Message Lock Renewal

An order system on Azure typically sends tasks from an API into an **Azure Service Bus Queue**, and workers handle payment capture, invoicing, or notifications. When multiple workers run concurrently, the system must prevent two workers from normally processing the same message at once. Yet if a worker receives a message and loses connectivity before finishing, that work must not be lost either.

**Peek-Lock** in Azure Service Bus solves a critical piece of this problem: the broker delivers a message to one consumer and temporarily **locks** it for a finite duration. The consumer processes it and explicitly reports the outcome via **settlement** operations: **Complete**, **Abandon**, **Dead-letter**, or **Defer**. If work runs long, the consumer can **renew the lock** before it expires.

However, Peek-Lock **does not create a business-level exactly-once guarantee**. A message can still be redelivered after lock expiration, network interruptions, or settlement failures. A reliable design always pairs message locking with **idempotency**, durable state persistence, bounded retries, and operational observability.

This lesson belongs to the **Queues and Messaging** chapter of the **CLOUD_PROVIDERS_AZURE** learning path: covering the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data—deploying, monitoring, securing, and controlling costs for an Azure application.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Peek**, **Peek-Lock receive**, and **Receive-and-Delete**.
2. Explain the message lifecycle from **Active → Locked → Completed/Abandoned/Deferred/Dead-lettered**.
3. Choose the right settlement for success, transient errors, permanent data errors, and deferred work.
4. Understand **LockDuration**, **LockedUntil**, **DeliveryCount**, **MaxDeliveryCount**, and **LockToken**.
5. Use **manual lock renewal** or **AutoLockRenewer** in the Python SDK within appropriate limits.
6. Design consumers resilient to **MessageLockLost**, connection drops, duplicate processing, and failures after side effects occur.
7. Distinguish **message locks** from **session locks** and identify prefetch/concurrency hazards.
8. Inspect queues, message counts, RBAC, private networking, metrics, and costs safely.

## 1. Why Is Message Locking Needed?

Suppose a **payment-jobs** queue holds message **PAY-001** to record a payment. Two workers, A and B, are listening for messages.

If the broker deleted the message immediately upon handing it to A, and A crashed before saving the transaction, the job would be lost. Conversely, if the broker let both A and B normally process the same message simultaneously, the system would risk double-charging the payment.

Peek-Lock offers a practical compromise:

~~~text
Service Bus Queue: payment-jobs
         |
         | receive with Peek-Lock
         v
Worker A receives PAY-001
         |
         +--> Broker temporarily locks PAY-001
         |    Worker B does not receive the locked copy in normal flow
         |
         +--> A processes and persists state
                 |
                 +-- Success --------> Complete
                 +-- Transient error -> Abandon / let lock expire
                 +-- Corrupt data ---> Dead-letter
                 +-- Process later --> Defer
~~~

The lock is **time-bounded**, because the broker cannot wait forever on a crashed worker. If A fails to finish or renew in time, the broker can redeliver the message to another consumer. Therefore, an application must never treat holding a lock as permanent proof that only it can execute business side effects.

## 2. Distinguishing Peek, Peek-Lock, and Receive-and-Delete

These three similar-sounding terms mean completely different things.

| Operation / Mode | What Does It Do? | Is Message Locked? | Main Risk |
|---|---|---|---|
| **Peek** | Browses/views messages without claiming them for processing | No | Not a work-claim mechanism; another receiver can still process the message |
| **Peek-Lock receive** | Receives message and acquires a lock before settlement | Yes, for a finite window | If lock is lost or settlement fails, the message can be redelivered |
| **Receive-and-Delete** | Broker removes message from the queue upon delivery | No Peek-Lock settlement | Worker crashing after receive can permanently lose work |

**Peek** is used for inspection and diagnostics, never to claim processing ownership. With **Receive-and-Delete**, speed or simplicity does not justify the risk for critical workloads.

### When to Use Receive-and-Delete?

Consider it only for data where loss causes negligible harm—such as non-critical telemetry backed by another collection path, when the architect explicitly accepts data loss. For transactions, invoices, batch jobs, and database updates, **Peek-Lock is usually the right choice**.

### Easily Confused Names

**Peek** is not equivalent to **Peek-Lock**. Calling peek merely inspects messages; a **lock** is created when a consumer receives in **PEEK_LOCK** mode. Similarly, **Complete** is not an arbitrary delete: it is only valid for a message on which the receiver currently holds a valid lock, executed through the proper protocol/SDK.

## 3. Lifecycle of a Message Under Peek-Lock

~~~text
                  Producer sends message
                           |
                           v
                         ACTIVE
                           |
                   Receive Peek-Lock
                           |
                           v
                         LOCKED
                     /   /  |  \
                    /   /   |   \
                   v   v    v    v
              COMPLETE ABANDON DEFER DEAD-LETTER
                 |        |     |        |
                 v        v     v        v
             Removed    ACTIVE Deferred  DLQ
                            ^
                            |
                 Lock expired / redelivered
~~~

**This diagram is logical** and does not represent every corner of the broker state machine. A message can also hit TTL expiration, be auto-dead-lettered by policy, or be affected by sessions/transactions.

### Key States to Understand

- **Active:** eligible to be picked up by normal receivers.
- **Locked:** held by a receiver for a bounded duration.
- **Completed:** broker accepts successful settlement and removes the message from the work queue.
- **Abandoned:** receiver explicitly releases the lock; the message becomes eligible for redelivery.
- **Deferred:** message stays in the queue yet **does not appear in normal receives**; must be fetched by **sequence number**.
- **Dead-lettered:** message moves to the **dead-letter subqueue (DLQ)** for separate handling.

**Defer is neither dead-lettering nor an automatic scheduled retry.** If the application fails to persist the sequence number and run a retrieval process, deferred jobs can sit unnoticed indefinitely.

## 4. LockDuration, LockedUntil, and LockToken

When Service Bus delivers a message under Peek-Lock, it issues a time-bounded lock. Key attributes:

| Concept | Meaning | Scope |
|---|---|---|
| **LockDuration** | Default lock duration when receiving in Peek-Lock mode | Queue/subscription configuration |
| **LockedUntil** | Timestamp when the current lock expires per SDK/broker metadata | Received message |
| **LockToken** | Lock identifier authorizing settlement/renewal operations | Locked message delivery |
| **DeliveryCount** | Number of times the message has gone through broker deliveries | Message |
| **MaxDeliveryCount** | Threshold of deliveries before broker auto-dead-letters on limit breach | Queue/subscription configuration |

### LockDuration Is Not Unlimited Processing Time

In Azure Service Bus, **LockDuration** is typically configurable from a few seconds up to a **maximum of 5 minutes** per entity/API limits; the common default is **1 minute**. Always verify current limits and actual queue/subscription settings before deployment.

A 20-minute job is **not** guaranteed safe just by setting `LockDuration = 5 minutes`. For longer runs, consumers must renew locks properly or change architecture to finish early and hand long-running execution to a dedicated orchestrator.

### Locks Belong to the Current Delivery

If worker A receives a message and loses its lock, that delivery is no longer valid for calling `Complete`. Worker B can receive the same message with a fresh lock. **Never store `LockToken` as a business identifier**, and never use it instead of `messageId`/`jobId` for deduplication.

### Never Rely on Local Machine Clocks Alone

**LockedUntil** indicates expected expiration, yet network latency, clock skew, service state, and settlement calls all take time. Never wait until the final second to renew or `Complete`.

## 5. Settlement: Complete

**Complete** tells the broker the consumer finished processing the message and it can be removed from the workflow. Choose Complete only after:

1. The payload has been validated.
2. Business outcomes are durably persisted (database, blob, ledger).
3. Required external side effects are handled or safely tracked by architecture.
4. The consumer still holds a valid lock.

~~~text
Receive PAY-001
      |
      v
Check jobId in ledger
      |
      v
Write idempotent transaction to DB
      |
      v
Commit DB transaction successfully
      |
      v
Complete message
      |
      v
Broker removes message from queue
~~~

### Why Not Complete First?

Anti-pattern:

~~~text
Receive -> Complete -> call database -> crash
~~~

If the message is already removed from the queue before the database write finishes, the job can be lost. The safer sequence is **persist state/results first, then Complete**.

### An Unavoidable Failure Window with Peek-Lock

~~~text
Receive
  |
  v
DB write succeeds
  |
  v
Worker crashes before Complete
  |
  v
Message is redelivered
~~~

On the second delivery, the worker must see that the **job already succeeded** and simply call `Complete` **without creating a second transaction**. That is why **idempotency** is mandatory even when using Peek-Lock properly.

## 6. Settlement: Abandon

**Abandon** explicitly releases the message lock so it becomes eligible for redelivery. Use it when the consumer fails on the current attempt yet has reason to expect a subsequent attempt can succeed.

Examples:

- An OCR API returns a transient error.
- The database is failing over and returns a connection error.
- The worker hits transient memory pressure while the environment recovers.

~~~text
Worker receives JOB-042
        |
        v
Calls OCR service
        |
        v
OCR returns transient 503
        |
        v
Abandon message
        |
        v
Message returns to receivable state
        |
        v
Another worker (or same worker) receives again
~~~

### Abandon Does Not Create a Long Backoff

Abandon usually makes the message available again right away; if all workers hit the same outage, they will repeatedly receive and abandon, causing a **retry storm**, spiking `DeliveryCount`, and pushing messages rapidly into the DLQ.

If you need minutes or hours of delay, consider:

- Bounded exponential backoff in orchestration.
- Scheduled messages or a dedicated retry queue.
- Error-type routing and concurrency caps.
- Circuit breakers when downstream dependencies are down.

Never hold a lock and sleep for hours to "retry": the lock would require constant renewal, waste worker resources, and still risk expiring.

## 7. Settlement: Dead-Letter

**Dead-letter** explicitly moves a message to the **dead-letter subqueue** when it cannot be processed through normal flow—for example:

- Payload violates schema.
- Required fields are missing and cannot be fixed by retrying.
- Job type was rejected by business policy.
- Message format is incompatible with active consumers.

~~~text
Receive PAY-002
     |
     v
Validate payload
     |
     v
Missing required orderId
     |
     v
Dead-letter:
  reason = InvalidPayload
  description = Missing orderId
     |
     v
DLQ for investigation or replay after fix
~~~

### A DLQ Is Not an Auto-Emptied Trash Bin

Messages in a DLQ require an operational process:

1. Monitor dead-letter counts and message age.
2. Categorize root causes by schema, version, and source.
3. Fix the producer or consumer.
4. Decide whether to **replay**.
5. On replay, dispatch in a controlled flow preserving the **jobId/idempotency key**.
6. Record who executed the replay and the outcome.

Never blindly replay thousands of malformed messages just because a service came back up; that repeats failures and wastes money.

### Reason and Description Must Be Safe

Record short, consistent, metrics-friendly reasons such as **InvalidSchema** or **UnsupportedVersion**. Never place passwords, tokens, card numbers, or raw sensitive payloads into dead-letter descriptions.

## 8. Settlement: Defer

**Defer** fits when a message is valid, yet the consumer wants to process it later according to application-specific sequencing—for example:

- Job B must wait until Job A completes.
- A document requires approval before processing.
- A component is awaiting auxiliary data tracked by the application.

When deferred, a message no longer appears in normal receives. The application must save the message's **sequence number** so it can later retrieve it via the **receive deferred messages** API.

~~~text
Receive JOB-B (sequence number 12345)
        |
        v
Dependency JOB-A not yet complete
        |
        v
Record in ledger:
  JOB-B -> DEFERRED, sequenceNumber=12345
        |
        v
Defer message
        |
        v
JOB-A finishes
        |
        v
Receive deferred message by sequence number
        |
        v
Process JOB-B -> Complete
~~~

### Defer vs. Scheduled Message

| Scenario | Appropriate Mechanism |
|---|---|
| Message already received but must wait on a business dependency | Defer + store sequence number + wake-up process |
| Want to send a new message that becomes active at a future time | Schedule message via Service Bus capability |
| Permanently broken message | Dead-letter |
| Transient failure wanting early retry | Abandon or controlled retry strategy |

**Never use Defer unless your app persists the sequence number and has a reliable wake-up flow.** Store that number in a durable database or orchestrator, never solely in worker RAM.

## 9. Settlement Decision Table by Scenario

| Processing State | Suggested Settlement | Note |
|---|---|---|
| Data and state persisted successfully | **Complete** | Complete only after durable side effects |
| Job already SUCCEEDED earlier; message redelivered | **Complete** | Do not re-run business side effects |
| SQL/API returns 503; needs retry | **Abandon** or backoff retry | Avoid tight infinite retry loops |
| Corrupt JSON / missing required field | **Dead-letter** | Clear reason, no leaked secrets |
| Waiting on dependency with coordinator ledger | **Defer** | Must persist sequence number |
| Lock already expired | Old delivery can no longer be settled | Wait/handle redelivery properly; check idempotency |
| Worker shuts down mid-processing | Finish/Complete if lock and time remain, or allow safe retry | Support graceful shutdown |

These options serve as design guidance; specific business rules, sessions, TTLs, and transaction requirements may alter the implementation.

## 10. DeliveryCount and MaxDeliveryCount

Service Bus tracks **DeliveryCount** to help identify messages that have been redelivered repeatedly; entities enforce a **MaxDeliveryCount** setting. The typical default is **10** for queues/subscriptions—verify actual configuration.

When consumers repeatedly abandon or let locks expire and messages get redelivered, delivery count increments. Once it exceeds the broker's maximum delivery threshold, Service Bus can **automatically dead-letter** the message with a max-delivery reason.

~~~text
PAY-003:
  attempt 1: worker A crashes
  attempt 2: worker B Abandons
  attempt 3: worker C fails
  ...
  exceeds MaxDeliveryCount
       |
       v
  Broker moves message to DLQ
~~~

### Why Not Set MaxDeliveryCount Very High?

If a payload has a permanent defect, 1,000 extra attempts only:

- Add wasted processing cycles and cost.
- Pollute logs and alerts.
- Waste worker time on doomed messages.
- Put needless pressure on downstream systems.

Choose `MaxDeliveryCount` based on job type, recoverability, and SLAs. Separate **transient** from **permanent** errors before deciding to retry.

### Never Use DeliveryCount as a Business Run ID

`DeliveryCount` helps operations, yet it never replaces `messageId` or `jobId`. A producer might send a new message with the same business command, or a single message might be redelivered. Deduplicate using explicit business identifiers.

## 11. When Must You Renew a Lock?

Suppose a queue has `LockDuration = 60 seconds`, while an OCR task can take 3 minutes. Without renewal:

~~~text
00:00  Worker A receives JOB-100, locked until 01:00
00:10  A starts OCR
01:00  Lock expires
01:05  Worker B can receive JOB-100 again
02:50  A finishes OCR and tries Complete
02:50  Complete can fail with MessageLockLost
~~~

Meanwhile, B may be running the same job. Solve this at **two layers**:

1. **Hold the lock long enough while valid work runs**, via renewal.
2. **Prevent duplicate side effects if the lock is still lost**, via idempotency and business leases.

Renewal reduces expiration-driven duplicates under normal conditions, yet **never turns Peek-Lock into a cross-system distributed transaction**.

### Two Ways to Renew

- **Manual renewal:** consumer calls the SDK to request a fresh lock expiration for the message.
- **Automatic renewal:** SDK periodically renews the lock in the background up to an application-configured max duration.

Renewal duration is bounded; applications must pick sensible limits aligned with processing times, max allowed execution time, and budget.

## 12. Manual Lock Renewal

In the Azure Service Bus Python SDK, receivers provide **`renew_message_lock(message)`** for messages still holding a valid lock.

Pseudocode:

~~~text
message = receive_peek_lock()
deadline = now + processing_timeout

while not job_finished and now < deadline:
    process_small_step()

    if nearing_message_lock_expiration:
        receiver.renew_message_lock(message)

if job_finished_and_result_durable:
    receiver.complete_message(message)
else:
    handle_retry_or_failure()
~~~

Notes:

- Renewal must happen **before** the lock expires.
- Once a lock is lost, no renewal call can "revive" the old delivery.
- Network errors, service maintenance, or worker termination can cause renewal to fail.
- Lock renewal does not extend message TTL or guarantee job completion.
- Never write an unbounded renewal loop when business rules require timeouts.

### Decoupling Processing Time from Lock Hold Time

A task might take 20 minutes waiting on OCR. Holding a message lock and keeping a worker replica pinned the entire time raises costs and exposes renewal to interruptions.

For very long workflows, consider **Durable Functions, Container Apps Jobs, Sagas, schedulers, or state machines**: the consumer receives the message, durably creates a job record, `Complete`s the message **only after the job is durably persisted**, and another runner tracks and executes the long work. This requires explicit result orchestration—never simply call `Complete` before persisting durable state.

## 13. AutoLockRenewer in the Python SDK

The Azure Service Bus Python SDK provides **`AutoLockRenewer`** to automatically renew message locks up to a maximum duration. This helps when processing times vary without being excessively long.

Conceptual example:

~~~python
from azure.servicebus import AutoLockRenewer

renewer = AutoLockRenewer(max_lock_renewal_duration=300)

try:
    # receiver has already received message in PEEK_LOCK mode.
    renewer.register(
        receiver,
        message,
        max_lock_renewal_duration=300
    )

    process_message(message)
    # Complete only after all required side effects are durable.
    receiver.complete_message(message)
finally:
    renewer.close()
~~~

**This snippet illustrates logic and cannot run standalone**, as `receiver`, `message`, and `process_message` must be initialized. The **300-second** value is the maximum renewal cap requested by the app, not the queue's `LockDuration`, and does not guarantee the lock survives 300 seconds under every failure condition.

### Limits of Auto-Renewal

1. Renewal only works while the process and SDK background mechanism remain healthy, networked, and authorized.
2. The SDK can encounter renewal errors even while processing continues.
3. Once `max_lock_renewal_duration` is reached, the lock can expire if work has not finished.
4. A message that lost its lock cannot be `Complete`d with the old lock.
5. In CPU-bound workloads, verify heavy processing does not starve the thread or event loop performing renewals.
6. Avoid registering thousands of locked messages simultaneously if SDK or worker resources cannot keep up.

Track **p95/p99 processing times** to size renewal limits rather than relying solely on averages.

## 14. Python Example: Receiving and Settling with Peek-Lock

This hands-on example uses **`azure-servicebus`** and **`azure-identity`**. The worker connects to an existing queue, receives messages via Peek-Lock, validates JSON payloads, simulates brief work, and calls `Complete`. Malformed messages are dead-lettered; transient processing errors are abandoned if the lock remains valid.

### Prerequisites Before Running

- An Azure Service Bus namespace and queue provisioned in a lab environment.
- Caller identity holds **Azure Service Bus Data Receiver** at the appropriate scope.
- Uses Microsoft Entra ID / managed identity or authorized developer credentials—never embed connection strings in code.
- TLS connectivity, DNS, and network access to the namespace are working.
- Queue holds no production transactions: this program **actively receives and settles** messages.
- Python runtime and packages:

~~~bash
python -m pip install azure-servicebus azure-identity
~~~

Example environment variables:

~~~bash
export SERVICEBUS_FQDN="sb-demo.servicebus.windows.net"
export SERVICEBUS_QUEUE="invoice-jobs"
~~~

On Azure, **`DefaultAzureCredential`** can use a managed identity; locally it can use configured developer identities. Always verify tenant, subscription, permissions, and environment before running.

### Sample Worker

~~~python
import json
import logging
import os
import time

from azure.identity import DefaultAzureCredential
from azure.servicebus import (
    AutoLockRenewer,
    ServiceBusClient,
    ServiceBusReceiveMode,
)
from azure.servicebus.exceptions import MessageLockLostError


FQDN = os.environ["SERVICEBUS_FQDN"]
QUEUE = os.environ["SERVICEBUS_QUEUE"]


def parse_job(message):
    # This sample expects the sender to use UTF-8 JSON bytes (DATA body).
    raw = b"".join(message.body)
    data = json.loads(raw.decode("utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Message body must be a JSON object")
    if not isinstance(data.get("jobId"), str) or not data["jobId"]:
        raise ValueError("Missing jobId")
    return data


def do_short_demo_work(job):
    # Simulates computation only; creates no real side effects.
    # Production code must persist outputs and an idempotent job ledger.
    logging.info("Processing jobId=%s", job["jobId"])
    time.sleep(2)


def main():
    credential = DefaultAzureCredential()
    renewer = AutoLockRenewer(max_lock_renewal_duration=300)

    try:
        with ServiceBusClient(
            fully_qualified_namespace=FQDN,
            credential=credential,
        ) as client:
            with client.get_queue_receiver(
                queue_name=QUEUE,
                receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                prefetch_count=0,
                max_wait_time=5,
            ) as receiver:
                # Lab: pull at most one message per run.
                messages = receiver.receive_messages(
                    max_message_count=1,
                    max_wait_time=5,
                )

                for message in messages:
                    try:
                        renewer.register(
                            receiver,
                            message,
                            max_lock_renewal_duration=300,
                        )

                        try:
                            job = parse_job(message)
                        except (ValueError, UnicodeDecodeError,
                                json.JSONDecodeError) as invalid:
                            receiver.dead_letter_message(
                                message,
                                reason="InvalidPayload",
                                error_description="Missing or invalid JSON job",
                            )
                            logging.warning(
                                "Dead-lettered invalid message: %s",
                                type(invalid).__name__,
                            )
                            continue

                        do_short_demo_work(job)
                        receiver.complete_message(message)
                        logging.info("Completed jobId=%s", job["jobId"])

                    except MessageLockLostError:
                        # Old lock is invalid: do not attempt Complete again.
                        logging.exception("Message lock was lost")

                    except Exception:
                        logging.exception("Unexpected worker error")
                        try:
                            receiver.abandon_message(message)
                        except Exception:
                            # Lock may already be lost; broker handles redelivery.
                            logging.exception(
                                "Unable to abandon the received message"
                            )
    finally:
        renewer.close()
        credential.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
~~~

**Limitations of this sample:**

- This is a **lab consumer**, not a production solution; it receives at most one message and intentionally simulates brief work.
- It omits a real idempotency database/ledger, retry scheduler, circuit breaker, and full structured telemetry.
- Payload assumes a **DATA message body** containing UTF-8 JSON; other AMQP body types require appropriate decoders.
- It neither sends sample messages nor creates queues; learners must use an authorized test queue.
- The generic error branch attempts `Abandon` only if the lock still holds; if permissions or connectivity failed, that call can also fail.
- `AutoLockRenewer` is included for illustration even though the task takes ~2 seconds. For tasks reliably shorter than `LockDuration`, auto-renewal may be unnecessary.
- If `MessageLockLost` occurs after business work actually succeeded, the subsequent redelivery still needs the ledger to avoid duplicate side effects.

## 15. Production Pattern: Idempotent Ledger and Safe Complete

A serious consumer requires a business-bound **idempotency key**, not just a lock token. For example:

~~~text
MessageId = producer-assigned identifier
JobId = ORD-00421
Ledger key = namespace + business operation + JobId
~~~

The ledger can live in Azure SQL, Cosmos DB, PostgreSQL, or any store supporting **unique keys / conditional writes**. Pseudocode:

~~~text
receive message Peek-Lock
validate and normalize JobId

atomically insert JobId as PROCESSING with lease/owner
    if already SUCCEEDED:
        Complete current delivery
        stop
    if another worker owns active processing lease:
        defer or retry safely based on policy
        stop

try:
    perform business operation with idempotent side effects
    durably record SUCCEEDED + result reference
    Complete current message while lock remains valid
except permanent invalid input:
    record rejected status
    Dead-letter message if lock valid
except transient error:
    record failed attempt
    Abandon or schedule controlled retry if lock valid
except lock lost:
    do not settle stale delivery
    preserve ledger for safe redelivery/reconciliation
~~~

### Why Is "Check Then Insert" Insufficient?

Two workers can read the ledger concurrently and both see that `JobId` does not exist yet. If both proceed to execute side effects, duplicates still occur. Use **unique constraints, transactions, compare-and-swap, or atomic claims**.

### Business Lease vs. Message Lock

A message lock protects settlement authority in Service Bus. A **business lease/ledger** protects correctness across databases, Blob Storage, and external APIs. The two can expire independently; design explicit job claim timeouts and recovery rules.

### When External Side Effects Exist

If a worker sends emails or triggers partner payments, neither `Complete` nor a DB rollback can unsend an email. Use **partner API idempotency keys**, the outbox pattern, durable delivery state, and reconciliation.

## 16. MessageLockLost and Common Errors

**MessageLockLost** (or the corresponding Service Bus error) means the requested operation used a lock that is no longer valid. Possible causes include:

- Worker ran longer than `LockDuration`.
- Lock renewal did not occur in time or failed.
- Network interruption broke the receive session.
- Infrastructure/service events invalidated the lock in edge cases, even before nominal expiration.
- Settlement was attempted using a stale or closed receiver/lock reference.

### Never Assume a Failed Complete Means Business Logic Did Not Run

Example:

~~~text
10:00:00 Receive PAY-120
10:00:15 DB transaction commits successfully
10:01:05 Attempt Complete -> MessageLockLost

Correct conclusion:
  - The DB transaction may already exist.
  - The message may be redelivered.
  - The next consumer must check JobId and Complete safely.

WRONG conclusion:
  - Complete failed, so the DB definitely wasn't updated.
~~~

### What to Do When a Lock Is Lost?

1. Never retry `Complete` or `Abandon` using the expired lock token.
2. Log safely: `messageId`, `jobId`, `deliveryCount`, processing duration, and error type.
3. Let the broker redeliver the message—do not manually re-publish an unconditional copy.
4. On redelivery, execute your idempotency flow.
5. Tune `LockDuration`, renewal, concurrency, and task design if lock losses recur.

## 17. Prefetch Can Expire Locks Before Processing Begins

**Prefetch** lets a client pre-download multiple messages to cut network round-trips. While it can boost throughput for fast tasks, under Peek-Lock **prefetched messages start ticking down their lock timers while sitting in client memory** before application code even starts processing them.

Example:

~~~text
LockDuration = 60 seconds
Prefetch = 100 messages
One worker processing sequentially: 5 seconds/message

The 20th message waits in buffer ~95 seconds.
By the time processing starts, its lock may already be expired.
~~~

### Tuning Guidance

- For slow tasks: set **`prefetch_count=0`** or a very small number.
- For fast tasks: raise prefetch only after measuring throughput and lock-loss rates.
- Never prefetch more messages than can be processed within lock/renewal limits.
- Measure **buffer wait time**, not just active processing time.
- Use concurrent consumers where appropriate, without overwhelming databases or downstream APIs.

**Auto-renewal does not make unbounded prefetch safe.** Registering renewals for hundreds of buffered messages adds overhead without fixing sequential processing bottlenecks.

## 18. Concurrency and Lock Ownership

If a queue holds 500 messages and 20 workers run, Service Bus distributes eligible messages across receivers per broker mechanics. Each worker may hold multiple locked messages depending on SDK/config.

~~~text
Queue: 500 active messages
        |
        +--> Worker A: message 1, 2, 3 ...
        +--> Worker B: message 4, 5, 6 ...
        +--> Worker C: message 7, 8, 9 ...
        ...
~~~

As concurrency rises:

- Throughput may improve.
- Lock timeouts become likelier if work exceeds real capacity.
- Database connection pools and API rate limits saturate faster.
- Retries can overlap with work from earlier deliveries.

A sound rule is **concurrency ≤ sustainable processing capacity**, and total time from receive to settlement must fit comfortably inside your `LockDuration`/renewal budget.

### Session-Enabled Queues: A Special Case

If a queue/subscription uses **sessions**, consumers receive by **`SessionId`**. **Session locks** differ from ordinary message locks:

- A receiver acquires a session lock to process messages grouped by session.
- Intra-session ordering can be coordinated per Service Bus capabilities.
- Dedicated **renew session lock** APIs and session auto-renewal exist in the SDK.
- Losing a session lock causes the receiver to lose processing rights for that session.

Do not default to **`renew_message_lock`** for messages inside a session receiver; check the exact SDK/session API. Sessions help group work per customer/order, yet still require idempotency, lock-loss handling, and workflow side-effect protection.

## 19. Cross-System Transactions and Correctness

Service Bus supports transactions across **certain supported messaging operations**, yet an Azure SQL or PostgreSQL transaction does not automatically combine atomically with a Service Bus `Complete`.

Scenario:

~~~text
Receive message
  |
  v
Commit DB transaction
  |
  v
Complete Service Bus message
~~~

If the process crashes between those steps, the broker still redelivers even though the DB committed. Designing around **at-least-once delivery + idempotent processing** is far more realistic than assuming "one message equals one cross-system transaction."

### Transactional Outbox

For apps that both update a DB and publish new messages, the **outbox pattern** can:

1. Write business data and an outbox row inside the **same DB transaction**.
2. Have an independent publisher read the outbox and send to Service Bus.
3. Mark outbox rows sent idempotently.
4. Have downstream receivers deduplicate by business identifier.

An outbox does not make networks or brokers infallible; it provides a recovery path when the DB commits before message publishing succeeds.

## 20. Lock Renewal vs. Long-Running Task Design

Comparing three approaches:

| Approach | When Suitable | Risks / Limits |
|---|---|---|
| Process within one lock | Short tasks with predictable duration | Fails if duration exceeds `LockDuration` |
| Auto-renew within cap | Moderate-length tasks while worker stays up | Lock loss still possible; CPU/thread/network & renewal caps |
| Offload to durable job | Tasks taking tens of minutes/hours or waiting on humans | Requires ledger, workflow, timeouts, and separate completion flow |

Example design for a report-export job:

~~~text
Service Bus message: GenerateMonthlyReport
        |
        v
Consumer creates job record (idempotent)
        |
        v
Complete message after job record is durably persisted
        |
        v
Job runner executes multi-minute report
        |
        +-- Status = RUNNING
        +-- Status = SUCCEEDED / FAILED
        |
        v
Send result notification via separate workflow
~~~

In this model, the inbound message means **"work request accepted"** rather than "report finished." Make the business contract and job-status API explicit so early `Complete` never misleads clients.

## 21. Queue Settings and Operational Thresholds

Relevant properties managed at the **queue/subscription** level:

| Setting | Impact |
|---|---|
| **LockDuration** | Lock duration for Peek-Lock receives |
| **MaxDeliveryCount** | Broker may auto-dead-letter once exceeded |
| **DefaultMessageTimeToLive** | Default message TTL if not overridden per message |
| **DeadLetteringOnMessageExpiration** | Whether TTL-expired messages move to DLQ |
| **RequiresSession** | Forces entities/receivers to use session semantics |
| **DuplicateDetection** | Drops duplicate sends with identical `MessageId` inside supported window |

### Duplicate Detection Does Not Replace Idempotency

Broker **duplicate detection** filters repeated sends sharing a **`MessageId`** within a configured time window. It does **not** prevent a handler from running twice when **the same message is redelivered after lock loss**, nor does it protect external side effects.

### TTL Does Not Equal LockDuration

- **LockDuration:** a consumer's temporary hold on a received message.
- **TTL:** total valid lifetime of the message per configuration.
- **MaxDeliveryCount:** limit on failed redelivery attempts.

These are independent axes—never add them together or treat them interchangeably.

## 22. Read-Only Inspection with Azure CLI

The following commands **only read configuration**; resource names are illustrative:

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az servicebus namespace show \
  --resource-group "rg-messaging-lab" \
  --name "sb-orders-lab" \
  --query "{name:name,location:location,sku:sku.name}" \
  --output json
~~~

Inspect queue and lock settings:

~~~bash
az servicebus queue show \
  --resource-group "rg-messaging-lab" \
  --namespace-name "sb-orders-lab" \
  --name "payment-jobs" \
  --query "{name:name,lockDuration:lockDuration,maxDeliveryCount:maxDeliveryCount,requiresSession:requiresSession,deadLetterOnExpiry:deadLetteringOnMessageExpiration}" \
  --output json
~~~

Dump full configuration for comparison:

~~~bash
az servicebus queue show \
  --resource-group "rg-messaging-lab" \
  --namespace-name "sb-orders-lab" \
  --name "payment-jobs" \
  --output json
~~~

Some runtime count fields may appear depending on API/CLI version. Cross-check with the Azure portal and metrics for **Active**, **Dead-lettered**, **Scheduled**, **Transfer**, and related counts where supported. Never infer exact worker health from a single message-count snapshot.

### Do Not Use CLI to Mutate Production Queues to "Test Locks"

Changing `LockDuration`, `MaxDeliveryCount`, deleting queues, or draining DLQs immediately impacts live consumers. Run exercises on a dedicated **lab queue**. Production config changes require approval, a change window, rollback criteria, and impact monitoring.

## 23. Microsoft Entra ID, RBAC, and Private Networking

### Worker Identity

Prefer **managed identities** on Azure Functions, Container Apps, VMs, or AKS Workload Identity with the Service Bus SDK wherever supported.

| Component | Recommended Permission |
|---|---|
| Producer | **Azure Service Bus Data Sender** at appropriate scope |
| Consumer | **Azure Service Bus Data Receiver** on target queue/subscription |
| Operator | Separated rights to view configs/metrics/logs vs. replay messages |
| Queue admin | Narrowly scoped RBAC for entity management—never granted to every worker |

Never assign **subscription-wide `Owner`** just to read messages. Shared Access Signatures / connection strings may be used in compatible environments, but must use minimal permissions, live in Key Vault / a secret store, rotate regularly, and never be baked into images or repositories.

### Distinguish Permissions from Network Paths

A worker with valid Azure RBAC can still fail to reach Service Bus if:

- The namespace restricts public network access.
- Private Endpoint, DNS, or routing is misconfigured.
- Firewalls, NSGs, or UDRs block egress.
- Proxy, TLS, or AMQP/WebSocket settings are wrong.

Conversely, healthy network connectivity still returns auth errors or 403 if the identity lacks permissions.

**Peek-Lock does not replace authentication.** Locks restrict concurrent message claims at the broker; they do not stop overly privileged admins from reading sensitive payloads or changing settings.

## 24. Monitoring Locks, Settlement, and Backlogs

A reliable system provides visibility from enqueue through completion:

| Metric / Telemetry | Meaning |
|---|---|
| **Active messages** | Backlog eligible for delivery |
| **Dead-letter message count** | Failed messages requiring investigation |
| **Scheduled / deferred counts or inventory** | Work waiting under specialized mechanics |
| **DeliveryCount** | Indicator of retries and redelivery |
| **MessageLockLost count** | Locks lost during processing or settlement |
| **Complete / Abandon / Dead-letter outcomes** | Breakdown of consumer settlement outcomes |
| **Processing time p50/p95/p99** | Guides `LockDuration`, renewal budget, and concurrency |
| **Lock renewal errors** | Surfaces network, SDK, or overrun failures |
| **Oldest message age** | Longest-waiting job compared against SLA |
| **DLQ reason distribution** | Separates producer, schema, and downstream bugs |
| **Worker CPU / RAM / concurrency** | Reveals resource saturation |
| **Cost per successful job** | Measures end-to-end pipeline efficiency |

Not every item above is a **built-in Azure Monitor metric**. `MessageLockLost`, settlement outcomes, p95, `jobId`, and DLQ reasons typically require **application telemetry** or custom queries. Azure Monitor and Service Bus metrics cover the broker side.

### Non-Leaking Log Sample

~~~json
{
  "jobId": "PAY-001",
  "messageId": "msg-001",
  "deliveryCount": 3,
  "settlement": "COMPLETE",
  "processingDurationMs": 1820,
  "lockRenewalCount": 0,
  "result": "SUCCEEDED"
}
~~~

Never log connection strings, tokens, full personal payloads, card numbers, encryption keys, or sensitive payment details.

### Useful Alerts

- Spike in **dead-lettered** messages over a short window.
- Increase in **MessageLockLost** after changing prefetch or concurrency.
- Queue backlog or message age breaching SLA.
- Repeated **Abandon** calls with the same error type.
- Workers alive yet completing zero messages.
- Renewal failures or p99 processing approaching lock-hold caps.
- Broker/compute cost spikes caused by retry storms.

## 25. Root-Cause Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| `Complete` throws `MessageLockLost` | Lock expired, renewal failed, or connection/receiver interrupted | Compare processing time, `LockedUntil`, network, and renewal logs |
| Message redelivered despite DB write | Worker crashed or settlement failed | Check ledger and enforce idempotency |
| Messages flood DLQ with `MaxDeliveryCount` | Tight retry loop, prolonged backend outage, or bad payload | Classify errors, add backoff, tune `MaxDeliveryCount` and inspect DLQ reason |
| Message no longer shows in normal receives | May be deferred, dead-lettered, completed, or expired | Check queue states and sequence number inventory |
| `ReceiveAndDelete` consumer loses jobs | Message deleted upon delivery before worker committed | Switch to Peek-Lock and add durable processing |
| Raising prefetch caused lock losses | Messages waited too long in client buffer | Lower prefetch; measure buffer wait time and concurrency |
| Auto-renew still loses locks | Exceeded renewal cap, network/CPU starvation, or SDK error | Monitor renewal failures, cap work duration, redesign long jobs |
| Duplicate payments occurred | Missing idempotency or external API lacks idempotency keys | Add ledger unique keys and reconcile side effects |
| Workers receive no messages | Wrong RBAC, queue/session mode, DNS, or Private Endpoint | Verify identity, session requirements, and broker metrics |
| Settlement fails after VM/Container restart | Old receiver closed; lock no longer valid | Support graceful shutdown and safe redelivery |
| Queue active count is 0 yet work remains | Deferred, locked/in-flight, scheduled, or DLQ | Inspect all subqueues/states and job ledger |
| Slow API causes queue backlog growth | Insufficient concurrency or downstream throttling | Measure throughput, p95, 429/503s, limit retries, and scale |

### Six-Step Diagnostic Workflow

1. **Broker:** verify queue/subscription, `LockDuration`, `MaxDeliveryCount`, active and DLQ counts.
2. **Consumer mode:** Peek-Lock or ReceiveAndDelete? Are sessions or prefetch enabled?
3. **Timing:** are processing duration, `LockedUntil`, and renewal budget aligned?
4. **Settlement:** did the worker call `Complete`/`Abandon`/`Defer`/`Dead-letter`, or hit SDK errors?
5. **Side effects:** did the database or external API already commit, and what does the ledger show?
6. **Infrastructure:** identity, network, DNS, worker restarts, quotas, and downstream throttling?

Never immediately raise `LockDuration` on seeing `MessageLockLost` without measuring processing time first; a worker crash or network drop still breaks things even with a longer lock.

## 26. Performance and Cost Optimization

Peek-Lock incurs messaging operation costs and associated worker compute costs. Excessive retries or unbounded lock auto-renewal inflates bills without improving SLAs.

### Variables to Balance

- **LockDuration:** long enough for typical short tasks, not a substitute for long-running workflows.
- **Prefetch:** raises throughput yet risks pre-processing lock expiration if too high.
- **Concurrency:** scales parallel work yet can overload downstream dependencies.
- **MaxDeliveryCount:** enough for transient blips without looping forever on bad data.
- **Retry backoff:** prevents retry storms and wasted API calls.
- **TTL:** matches the business relevance window of the work.
- **Auto-renew budget:** aligned with p99 and application timeouts.
- **DLQ monitoring:** prevents silent buildup of failed records.

### Simple Sizing Example

Suppose:

~~~text
Backlog = 600 messages
One worker processes = 5 messages/minute
SLA requires draining within = 30 minutes

Required capacity = 600 / 30 = 20 messages/minute
Theoretical minimum workers = ceil(20 / 5) = 4
~~~

This excludes cold starts, retries, complex messages, lock renewals, and database rate limits. If each worker processes one message in 12 seconds yet the backing database only permits 10 heavy writes/minute, scaling workers from 4 to 20 only produces 429/503 errors.

Service Bus is billed by tier, operations, and active service terms; Azure Functions, Container Apps, and VMs also carry compute costs, plus logs, Private Endpoints/networking, and dependent data stores. Use Azure Cost Management and current regional tier pricing rather than hardcoding fixed unit prices.

## 27. Case Study: Idempotent Payment Processing

An e-commerce company sends messages to a Service Bus Queue named **payment-jobs**. Each message contains:

~~~json
{
  "jobId": "PAY-2026-00042",
  "orderId": "ORD-2026-00123",
  "amount": 250000,
  "currency": "VND"
}
~~~

Requirements:

- 5 workers run on Azure Container Apps.
- `LockDuration = 60 seconds`.
- Normal processing takes 10 seconds, yet the payment API occasionally takes 2 minutes.
- Some messages are missing **`orderId`**.
- The partner API can execute the payment yet return a response timeout.
- Payment transactions must never be created twice.
- The queue needs a 5-minute SLA monitor from enqueue to completion.

### Tasks

1. Explain why Peek-Lock is chosen over ReceiveAndDelete.
2. Design payload validation before calling the API.
3. Map Complete, Abandon, Defer, and Dead-letter to four business outcomes.
4. Define lock renewal when the API takes ~2 minutes.
5. Explain why `AutoLockRenewer` does not replace an idempotency key.
6. Design the ledger around `jobId` and a unique constraint.
7. Handle the case where the API captured payment yet timed out returning the response.
8. Explain why `prefetch=100` per worker is dangerous here.
9. Design `MaxDeliveryCount`, retry backoff, and DLQ handling.
10. Describe logs and alerts when `MessageLockLost` rises.
11. Describe how managed identity/RBAC and Private Endpoints apply.
12. Propose an intentional fault-injection test where a worker crashes before `Complete`.

### Suggested Solution

Choose Peek-Lock and use **`jobId`** as the idempotency key. Before calling the payment API, check the database to see if the job already succeeded; claim it atomically. When the partner API supports idempotency keys, pass the same `jobId` on every retry. After durable confirmation or partner status reconciliation, record `SUCCEEDED` and `Complete` the message.

When the API times out with unknown status, **never immediately submit a fresh payment request with a new identifier**. Query/reconcile partner status using the idempotency key or a reconciliation job.

If the payload lacks `orderId`, dead-letter it with a clear reason. On transient 503 errors, `Abandon` or apply backoff retries; for runs exceeding the lock, use bounded auto/manual renewal while still handling lock loss. Size prefetch to match real processing times and concurrency.

## 28. Production Checklist

| Area | Evidence to Verify |
|---|---|
| Receive mode | Using `PEEK_LOCK` for critical business workloads |
| Entity config | Appropriate `LockDuration`, `MaxDeliveryCount`, TTL, and sessions |
| Settlement | `Complete` after durable commit; errors accurately classified |
| Defer | Sequence numbers persisted with a reliable retrieval flow |
| Dead-letter | DLQ alerts, sanitized reasons, and replay runbook |
| Renewal | Duration/cap matches p99; renewal failures monitored |
| Idempotency | `JobId`, unique keys/atomic claims, and safe external side effects |
| Prefetch | Never exceeds what can finish before lock timeout |
| Concurrency | Stays within downstream DB/API limits |
| Shutdown | Workers handle SIGTERM/restarts and safe redelivery |
| Identity | Managed identity and scoped `Azure Service Bus Data Receiver` |
| Network | DNS, firewall/Private Endpoint, and AMQP/TLS paths verified |
| Observability | `MessageLockLost`, `DeliveryCount`, settlements, DLQ, and SLA tracked |
| Cost | Budget covers broker, compute, logs, retries, and DLQ |
| Resilience | Tested crashes, timeouts, duplicates, lock expiry, and replay |

## 29. Self-Check Questions

1. What is the difference between `Peek` and `Peek-Lock` receive?
2. Why can `ReceiveAndDelete` lose work if a worker crashes?
3. When receiving with Peek-Lock, does the consumer gain permanent exclusive processing rights?
4. What happens when a locked message is not `Complete`d in time?
5. Should `Complete` be called before or after business results are durably persisted?
6. Why can a successful database commit paired with a failed `Complete` still cause duplicates?
7. Does `Abandon` automatically apply exponential backoff?
8. When should a message be dead-lettered immediately instead of retried?
9. How does `Defer` differ from `Dead-letter` and Scheduled Messages?
10. What happens if you defer a message without persisting its sequence number?
11. How do `LockDuration`, TTL, and `MaxDeliveryCount` differ?
12. Why should `LockToken` never be used as an idempotency key?
13. What does `AutoLockRenewer` do, and what does it NOT guarantee?
14. When `MessageLockLost` occurs, should you retry `Complete` on the old message object?
15. Why can an overly large prefetch cause locks to expire before processing starts?
16. How does a session lock differ from a message lock?
17. Does broker duplicate detection replace an idempotent ledger?
18. Why does an Azure Service Bus transaction not automatically include a database transaction?
19. Which metrics must you measure before raising concurrency or `MaxDeliveryCount`?
20. When a queue's `ActiveMessageCount` is 0, are all jobs guaranteed finished?
21. Which layers can cause 403 errors vs. timeouts to Service Bus?
22. Name three mandatory tests before promoting a payment consumer to production.

## References

- Microsoft Learn — *Message transfers, locks, and settlement*: https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement
- Microsoft Learn — *Service Bus dead-letter queues*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues
- Microsoft Learn — *Message deferral*: https://learn.microsoft.com/azure/service-bus-messaging/message-deferral
- Microsoft Learn — *Service Bus messaging overview*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview
- Microsoft Learn — *Message sessions*: https://learn.microsoft.com/azure/service-bus-messaging/message-sessions
- Microsoft Learn — *Duplicate detection*: https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection
- Microsoft Learn — *Service Bus transactions*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-transactions
- Microsoft Learn — *Authenticate with Microsoft Entra ID*: https://learn.microsoft.com/azure/service-bus-messaging/authenticate-application
- Microsoft Learn — *Azure Service Bus Python SDK*: https://learn.microsoft.com/python/api/overview/azure/servicebus-readme
