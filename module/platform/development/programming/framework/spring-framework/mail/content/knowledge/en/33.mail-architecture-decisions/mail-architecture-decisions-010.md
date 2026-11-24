# Evaluating Quota, Cost, and Scalability

When developing email-sending features with **Spring Framework Mail**, initial examples are usually very simple: configure **JavaMailSender**, create a **SimpleMailMessage** or **MimeMessage**, and call **send(...)**. However, taking a system into production raises very different architectural questions: how many messages can be sent per minute, does the SMTP provider limit by connection count or by recipient count, how do you prevent marketing emails from exhausting the quota for OTP emails, and how should costs be budgeted when the user base grows tenfold?

**Quota** is the usage limit imposed by a provider or by the system itself. **Cost** is the total resources and money required to complete the notification lifecycle, not just SMTP fees. **Scalability** is the capability to increase processing volume while preserving delivery time, reliability, security, and controllability.

This lesson focuses on **architectural decisions** for Spring Framework Mail: load modeling; accurately reading provider limit contracts; calculating throughput, burst, backlog, concurrency, and retries; organizing the outbox, workers, and rate limiting; isolating tenants and email types; comparing SMTP with email APIs and multi-provider strategies; cost budgeting, monitoring SLOs, running load tests, and preparing incident plans when quota is exhausted.

> **Key principle:** **JavaMailSender does not grant additional quota on its own**, and **increasing the number of workers does not automatically mean sending more emails**. Effective capacity is constrained by provider quotas, per-domain/recipient limits, connection rates, anti-abuse policies, network, and downstream processing. All pricing and limit figures in the examples below are **illustrative assumptions**, not current quotes or limits of any specific provider.

## 1. Why must quota, cost, and scale be evaluated together?

A mail architecture may satisfy one objective while failing at others:

| Design | Appears to achieve | Risks at high load |
| --- | --- | --- |
| Sending SMTP synchronously inside an HTTP request | Simple, easy to write | Request timeouts, blocked threads, hard to retry |
| Creating 100 workers to send in parallel | Higher throughput | Provider throttling, connection overload |
| Retrying every error immediately | “Will probably get delivered” | Retry storm, extra cost, and duplicate sends |
| A single queue for all emails | Fewer components | Marketing blocks OTP and password resets |
| Splitting emails into multiple recipients per send | Fewer message/API calls | Exposes recipient list, provider counts per recipient |
| Adding a second SMTP provider | Higher availability | Complex suppression, identity, dedup, and failover |
| Storing HTML/attachments in every queue message | Fewer lookups when sending | Expensive queue/storage/network, retains PII longer |
| Measuring only SMTP accepted | Easy to get a green dashboard | Unknown if delivered, bounced, or delayed |

**Proper evaluation** requires looking end-to-end from business event to recipient: one business event may generate one or more notifications; each notification may be submitted multiple times; providers may count quota in different units; and an accepted message can still bounce.

### The optimization goal is not “send as much as possible”

For OTP emails, the goal is usually **low latency and arriving within TTL**. For invoices, the goal is **durability, accuracy, and reconcilability**. For newsletters, the goal may be **cost per recipient, throughput, and compliance**. A single provider and a single shared rate limit may not suit all three.

## 2. High-level architecture of a controlled mail-sending system

~~~text
                 Business Application
                         |
                         v
                  Notification Intent
                         |
             +-----------+-----------+
             |                       |
             v                       v
      Delivery policy           Template resolver
      consent / suppression     locale / revision
             |                       |
             +-----------+-----------+
                         |
                         v
              Transactional Outbox / Queue
                         |
                         v
                  Priority Scheduler
                         |
             +-----------+------------+
             |            |           |
             v            v           v
         Critical      Transactional  Bulk
         OTP / reset   Receipts       Marketing
             |            |           |
             +------------+-----------+
                          |
                          v
                Quota / Rate Controller
                - account / provider
                - tenant / purpose
                - recipient domain
                - concurrency
                          |
                          v
                  Mail Worker Pool
                          |
                          v
                  JavaMailSender / API
                          |
                          v
                  SMTP / ESP Provider
                          |
               +----------+----------+
               |          |          |
               v          v          v
           Accepted    Throttled    Rejected
               |          |          |
               v          v          v
            Track       Retry      Policy / DLQ
               |
               v
         Delivery webhooks / Bounce / Complaint
               |
               v
         Status + Suppression + Analytics
~~~

The **Outbox** durably stores the sending intent. The **Rate controller** enforces limits before connecting to or calling the provider. **Workers** perform rendering/MIME composition and submission. **Delivery feedback** is handled separately because successful SMTP submission does not prove a message reached the recipient's inbox.

### Distinguishing three limit layers

1. **Business policy**: who may receive messages, when, maximum notifications allowed, and whether consent exists.
2. **System capacity**: jobs/second, workers, queues, DB, CPU, memory, network, and storage.
3. **Provider allowance**: daily/monthly quota, messages/second, recipients/message, connections, payload size, reputation, or dynamic throttling.

Scaling layer 2 without scaling layer 3 only causes workers to queue up and receive errors faster.

## 3. Units of measurement must be aligned before calculating

“Sending 1,000 emails” can mean several different things:

| Unit | Example | Why are they different? |
| --- | --- | --- |
| **Business events** | 100 orders confirmed | One event may notify multiple people |
| **Logical notifications** | 100 order confirmation emails | Potentially one email per recipient |
| **Messages submitted** | 100 MIME messages | One message may have multiple recipients |
| **Recipient deliveries attempted** | 120 recipients across 100 messages | Many providers count/bill per recipient |
| **API requests** | 60 requests to an ESP | One request may contain a batch or multiple recipients |
| **SMTP transactions** | 100 MAIL FROM/DATA transactions | Not the same as connection or recipient counts |
| **Attempts** | 107 send attempts due to retries | Can increase traffic/quota/cost |
| **Accepted recipients** | 102 recipients accepted by the provider | Not yet delivered |
| **Delivered** | 98 recipients accepted by destination servers per telemetry | Does not prove it was read |
| **Opened/clicked** | Behavior measured via tracking | Can be skewed by client privacy protection |

If a provider states a quota of **N recipients/day**, a formula based on **N JavaMailSender.send(...) calls/day** can be completely wrong, especially with multiple addresses in To/Cc/Bcc.

### One MIME message with multiple recipients

~~~java
helper.setTo(new String[] {
        "alice@example.test",
        "bob@example.test"
});
helper.setCc("team@example.test");
~~~

From the application's perspective, this may be one **send(message)**. However, the recipient count can be three, aside from provider-specific deduplication rules or separate quota accounting. The exact contract must be confirmed with the provider and actual transport behavior.

### Bcc does not bypass quota

Bcc hides addresses from other recipients, but they are still SMTP recipients. Do not use Bcc as a way to reduce quota usage or replace a bulk-sending strategy with proper consent and segmentation.

## 4. Types of provider quotas

Each provider has a different set of limits. Do not just ask “what is the emails/day quota?”.

| Limit type | What to verify | Architectural impact |
| --- | --- | --- |
| **Recipient count per day** | Counted by UTC, rolling window, or timezone? | Daily capacity and admission control |
| **Send rate** | Recipients/s, messages/s, or requests/s? | Token bucket, pacing |
| **Monthly allowance** | Billing/quota window, overage policy | Budget forecasting, cost alerts |
| **Recipients per message** | To/Cc/Bcc combined? | Fan-out and privacy |
| **Connections** | Concurrent SMTP connections, connect frequency | Connection pool, worker concurrency |
| **Requests per API key** | Burst and sustained limits | API throttling, multi-tenant isolation |
| **Max message size** | Headers + MIME + attachments, encoded size? | Validation before enqueue |
| **Max payload/API batch** | Batch recipients/items/bytes | Batch sizing |
| **Authentication/identity** | Verified sender, domain, DKIM, region | Provider routing |
| **Warm-up/anti-abuse** | Dynamic throttling/new account limits | Ramp-up, backoff |
| **Bounce/complaint policy** | Thresholds, suspension rules | Suppression and deliverability |
| **Account/subaccount quotas** | Are limits split by tenant? | Fairness, dedicated subaccounts |
| **Storage/retention** | Events, attachments, logs, webhooks | Costs beyond sending fees |

### Hard limits vs. soft limits

A **hard limit** is a threshold beyond which requests may be explicitly rejected. A **soft limit** or dynamic throttling depends on reputation, recipient feedback, provider state, or abuse policies. The system must tolerate changing allowances without crashing or triggering a retry storm.

### Higher quota does not equal higher deliverability

A provider raising a limit from 10,000 to 100,000 recipients/day does not guarantee 100,000 messages reach the Inbox. Sending reputation, SPF/DKIM/DMARC, complaints, bounces, and warm-up pacing remain critical.

### Know whether quota is global or multi-dimensional

An account can be constrained simultaneously by **total daily**, **requests/second**, and **destination domain**. The rate controller must enforce **all** relevant constraints; a single global token bucket is not enough.

## 5. Collecting real-world data for capacity planning

Before choosing a worker count or purchasing a provider plan, forecast:

- Number of users/tenants and growth rate.
- Number of business events generating emails per day/hour.
- Average and tail fan-out: how many recipients does each event target?
- Traffic distribution: business hours, batch jobs, peak campaigns.
- Acceptable delay: does OTP have a few-minute TTL or is a digest sent within the day?
- Failure/retry rates by provider and domain.
- Average and p95/p99 MIME size (especially attachments).
- Plain/HTML mix, template rendering, and inline images.
- Bounce/complaint/suppression rates.
- Percentage of emails skipped due to dedup, consent, or expired TTL.
- Number of regions/providers/verified domains to operate.

### Tabulating by purpose

| Purpose | Daily logical notifications (assumed) | Peak pattern | Deadline |
| --- | ---: | --- | --- |
| **OTP/login** | 20,000 | Burst within minutes | Very short |
| **Order receipt** | 45,000 | Follows transaction hours | Minutes |
| **Operational alert** | 5,000 | Incidents create spikes | Short |
| **Marketing** | 150,000 on campaign days | Can be scheduled | Hours |

These figures are strictly **hypothetical examples** to illustrate how to design a model. A marketing day should not rely on average weekday traffic to forecast demand.

### Calculate using percentiles, not just averages

If there are only **10,000 emails/day**, the average is about 0.116 emails/second. Yet 3,000 emails might arrive within a single minute — **50 emails/second** during the peak window. Designing for 0.116 emails/second will fail a “near-instant delivery” requirement during bursts, even though the daily total looks small.

### Align time window definitions

A 24-hour average rate is very different from the rate during a 15-minute campaign. Capacity planning should use at least:

~~~text
Average recipients/day
Peak recipients/minute
Peak recipients/second
Maximum burst duration
Payload size distribution
Allowed delivery delay per purpose
~~~

## 6. Basic throughput formulas

Assume:

- \(E\) = number of business events in a window.
- \(F\) = average recipients per event.
- \(P\) = probability that a notification passes consent/suppression/dedup.
- \(A\) = average attempts per logical recipient that needs sending.
- \(T\) = window length in seconds.

Approximate number of logical recipients that actually need sending:

\[
R_{\text{logical}} = E \times F \times P
\]

Number of recipient attempts:

\[
R_{\text{attempts}} = R_{\text{logical}} \times A
\]

Average attempt rate:

\[
\lambda = \frac{R_{\text{attempts}}}{T}
\]

**Do not assume provider billing is based on attempts.** Some systems bill per accepted recipient, others per request/send, or have free tiers/tiered pricing; the real contract terms must be applied to the matching variables.

### Purely hypothetical example

One month:

~~~text
Business events:               2,000,000
Recipients per event:          1.2
Pass consent/dedup:            90%
Average attempts per recipient: 1.03
~~~

Then:

~~~text
Logical recipients = 2,000,000 * 1.2 * 0.90
                   = 2,160,000

Recipient attempts = 2,160,000 * 1.03
                   = 2,224,800
~~~

If the provider bills per **recipient attempted**, 2,224,800 is the cost model input. If billing is per **recipient accepted**, accepted counts must be measured; they cannot be derived accurately from A alone.

### Peak evaluation

Suppose a batch has 2,400 recipients to process within 60 seconds:

~~~text
Required rate = 2,400 / 60
              = 40 recipients/second
~~~

If the provider cap is 20 recipients/s, the entire batch cannot finish within 60 seconds on that account, even if the server runs 100 threads. It takes at least around 120 seconds just to submit 2,400 recipients at 20/s (ignoring overhead, other traffic, and errors).

### SLOs must reflect real-world limits

Do not claim “99% of OTPs delivered via SMTP under 5 seconds” if a burst of 2,400 OTPs/60s hits a provider allowing only 20 recipients/s without reserved capacity or admission control. Deadlines, peak traffic, and quotas must be satisfied **simultaneously**.

## 7. Send rate, concurrency, and worker pool limits

**Rate** is the number of work units processed per second. **Concurrency** is the number of tasks running simultaneously. They are related, not identical.

Suppose a provider allows up to 20 recipient attempts/second and a single send takes an average of 400 ms. By a **Little's Law**-style relationship in steady state:

\[
L \approx \lambda \times W
\]

With throughput of 20 attempts/second and 0.4 seconds per attempt:

~~~text
Average concurrency ≈ 20 * 0.4 = 8 active attempts
~~~

This does **not mean** configuring exactly 8 threads is always optimal. Latency varies, one attempt may contain multiple recipients, and rendering/DB overhead differs from SMTP time; each stage must be measured and bounded independently.

### Worker count is not send rate

~~~text
40 threads * unlimited sends
    -> may produce 100+ requests/s
    -> provider throttle / reject
    -> retries and queue grow

40 threads + global rate limit 20 recipients/s
    -> attempts are paced
    -> stays within planned quota
~~~

Increasing threads from 20 to 40 when the provider still caps at 20/s only keeps more I/O in flight and does not automatically increase accepted recipients. Too many connections can also cause socket exhaustion, throttling, and memory pressure.

### Sizing by p95 latency

Beyond average latency, measure **p95/p99 submission latency**. If the provider occasionally takes 2 seconds/attempt and you want to sustain 20/s during peaks, worker concurrency may need to exceed 8 so workers do not sit idle. Still enforce the 20/s rate limit and connection cap separately.

### Separating limits

~~~text
Max executor threads:            32
Max concurrent SMTP connections: 12
Provider recipient rate:         20/s
Provider daily recipient cap:    50,000/day
Bulk purpose cap:                 8/s
Critical purpose reserve:        at least 5/s
~~~

This is only an illustrative profile. The system must pick **practical thresholds less than or equal to the provider contract**, leaving headroom for bursts, dynamic throttling, and other systems sharing the same credentials.

## 8. Queue backlog and drain time

When arrival rate exceeds processing rate, backlog grows.

Let:

- \(\lambda\) = arrival rate of work (recipients/second).
- \(\mu\) = effective service rate (recipients/second).
- \(B\) = current backlog (equivalent recipients).

If \(\lambda < \mu\) and both rates are relatively stable, expected time to drain the backlog:

\[
T_{\text{drain}} \approx \frac{B}{\mu-\lambda}
\]

If \(\lambda \geq \mu\), the backlog cannot drain on its own under constant-rate assumptions.

### Example

~~~text
Provider effective rate:    18 recipients/s
Traffic arriving:           10 recipients/s
Backlog currently:           4,800 recipients

Net drain rate = 18 - 10 = 8/s
Approx drain time = 4,800 / 8 = 600 seconds = 10 minutes
~~~

Actual time may be longer due to connection setup, job visibility, per-domain throttling, retries, and quota windows; this is an estimate for decision-making, not a guaranteed SLA.

### During provider downtime

~~~text
Provider capacity: 0/s
New traffic:       8/s
Downtime:          15 minutes

New backlog ≈ 8 * 15 * 60 = 7,200 recipients
~~~

After provider recovery, the system needs a **drain strategy**: pacing within quota, prioritizing time-sensitive notifications, dropping/marking expired OTPs appropriately, and not sending everything all at once.

### Measure job age, not just job count

Two queues with 500 jobs each can be very different:

~~~text
Queue A: oldest pending age = 10 seconds
Queue B: oldest pending age = 3 hours
~~~

For OTP, 3 hours is unacceptable; for a digest, it may not yet be a violation. Dashboards should track backlog by **purpose and oldest age/p95 delay**, not merely pending email count.

## 9. Admission control before queues grow unbounded

If a provider caps at 10,000 recipients/day while the application generates 1,000,000 notifications/day, an infinite queue is not a solution. It simply turns a quota problem into a storage, TTL, and cost problem.

**Admission control** decides whether new work should enter the system based on:

- Delivery purpose and criticality.
- Remaining quota and projected rate.
- Deadline and whether the queue can meet it.
- Suppression/consent and conditions requiring no send.
- Number of currently pending jobs.
- Tenant budget and campaign allocation.
- Failover or rescheduling capability.

### Decisions by email type

| Purpose | When capacity is scarce | Recommended policy |
| --- | --- | --- |
| OTP / reset | Very short deadline | Prioritize capacity, expire cleanly if unsendable in time |
| Fraud/security alert | Critical and potentially urgent | Reserved capacity, tested fallback path |
| Receipt / invoice | Needs audit trail | Durable queue, retry, delay alerting |
| Product activity digest | Can be deferred | Aggregate/schedule, avoid duplicate sends |
| Marketing | Usually schedule-flexible | Throttle, pause, enforce tenant budget |

### Do not hide inability to deliver

If an OTP cannot be sent within its TTL, the system should return a meaningful status such as **TEMPORARILY_UNAVAILABLE** or offer the user an alternative verification method if supported, rather than returning “sent” simply because an outbox row was inserted.

### Bounded queues

Set queue size limits or pending job limits per purpose/tenant. However, do not silently drop critical events: if more work cannot be accepted, apply **backpressure, reject/retry-later at the point of origin**, or use durable policy-driven persistence.

## 10. Daily quota and how to protect reserves

Daily quota imposes a different constraint from per-second rate. An app sending 5 recipients/second (well under a 20/s limit) can still exhaust its daily quota.

### Reservation formula

~~~text
Daily provider allowance:          50,000 recipients
Reserved for security/critical:    10,000 recipients
Reserved for transactional:        25,000 recipients
Bulk marketing budget:             10,000 recipients
Safety/unallocated headroom:        5,000 recipients
~~~

Total allocation equals 50,000. This is an example of **policy budget** management; not all providers support reservations at the infrastructure layer.

If bulk wants to use unused transactional capacity, the scheduler can allow **borrowable capacity** provided it does not erode the critical reserve within the relevant window.

### Window reset must be understood accurately

A provider may use:

- Calendar day in a defined timezone.
- Rolling 24-hour window.
- Billing month.
- Per-minute or per-second sliding window.
- A combination of multiple simultaneous windows.

The application must not assume quota resets at **00:00 server time**. Calculate according to the provider contract, use reliable clock synchronization, and check quota status via API/telemetry when available.

### Sending near the end of a quota window

If 100 recipients remain in the allowance while 500 transactional emails are waiting, a 100-recipient campaign must not consume the remainder before critical jobs are evaluated. Reserves/fairness must act **before sending**, not merely in end-of-day reports.

### Adaptive reserve

During peak periods, critical traffic share may rise. Reserves can be adjusted using data and risk policy; do not unconditionally lock in marketing quota while OTPs are being delayed.

## 11. Rate limiting: algorithms and scope of application

Common mechanisms:

| Algorithm | Idea | Best suited for |
| --- | --- | --- |
| **Token bucket** | Tokens refill at a steady rate, allows burst capacity | Providers with burst + sustained rate |
| **Leaky bucket / pacing** | Relatively smooth output | Avoiding spikes when ESPs are sensitive |
| **Fixed window** | Counts within fixed time intervals | Daily/hourly quotas, requires boundary handling |
| **Sliding window** | Counts attempts in a rolling window | Rolling-window quotas |
| **Concurrency semaphore** | Limits active in-flight I/O | SMTP connections and client resources |
| **Weighted fair scheduling** | Allocates capacity across tenants/purposes | Preventing starvation |

### How does a token bucket operate?

~~~text
Rate:     10 tokens/second
Capacity: 30 tokens

At idle: bucket fills up to 30
Burst:   send up to 30 recipient-units
After:   replenish roughly 10 per second
~~~

If the provider strictly allows **exactly 10 requests/s with no burst**, a bucket capacity of 30 can **violate the quota**. The algorithm and configuration must match actual semantics, rather than picking an arbitrary library default.

### Cost by recipients, not just by messages

A request with 10 recipients must consume **10 tokens** if the limiter protects a recipient quota. If the provider also limits requests/s, add a request-based limiter as well.

### Composite permit

~~~text
Request wants 4 recipients
      |
      +-- Global provider rate permits >= 4?
      +-- Daily account quota has >= 4?
      +-- Tenant budget has >= 4?
      +-- Purpose budget allows?
      +-- Recipient-domain throttle allows?
      '--> SMTP connection slot available?
                    |
                    v
                Submit
~~~

Permit reservation/rollback must be designed for cases where one check fails; do not consume some quotas and abort halfway without well-defined semantics. For provider quotas, after a network failure you **cannot always know** whether an attempt was counted, so local counters are only estimates and require reconciliation.

## 12. Distributed rate limiting across multiple replicas

An in-memory limiter inside each pod:

~~~text
Provider cap: 20 recipients/s

Pod A limiter: 20/s
Pod B limiter: 20/s
Pod C limiter: 20/s

Aggregate possible: 60/s -> exceeds cap
~~~

This is a very common bug when scaling horizontally. If quotas apply to the **same account/API key**, the limiter must coordinate at that same scope.

### Strategies

1. **Central sender pool**: a cluster of workers sharing a central scheduler/limiter.
2. **Distributed token bucket**: atomic state in Redis or a suitable datastore.
3. **Quota leases**: a controller grants small time-window budgets to workers and reclaims expired ones.
4. **Provider-native throttling feedback**: adapts based on response headers/API metrics.
5. **Static partitions**: cleanly splits quota across subaccounts/providers/tenants if the contract permits.

### Know the limiter's failure mode

What happens if Redis or the central limiter is unavailable?

- **Fail closed**: pause submissions, preventing spam and quota violations.
- **Conservative local fallback**: only if per-node minimum quotas were explicitly designed.
- **Fail open**: usually high-risk for provider quotas and critical emails.

The choice depends on purpose and risk, but must be configured and tested rather than left to unclear library behavior.

### Clock and concurrency

Distributed limiters must account for clock skew, atomic updates, network partitions, and TTLs. Relying on timestamps from multiple nodes can corrupt window accounting. Server-side time or a central authority can be used by design.

### Limiters do not replace durable queues

A rate limiter may return **WAIT/NO_PERMIT**; the job must be rescheduled safely rather than sleeping a thread for every email when hundreds of thousands of jobs are backlogged.

## 13. Fairness: preventing one tenant or campaign from monopolizing capacity

In a multi-tenant system, one enterprise customer may schedule 200,000 marketing emails while other tenants only need a few OTPs. A single FIFO queue can push critical jobs behind the entire campaign.

### Traffic classification

~~~text
                        Email intents
                             |
                +------------+------------+
                |            |            |
                v            v            v
             Critical    Transactional    Bulk
               Queue         Queue        Queue
                |            |            |
                +------------+------------+
                             |
                             v
                    Weighted Scheduler
                             |
                      Global Quota Gate
                             |
                       Sender Workers
~~~

An illustrative policy:

~~~text
Critical minimum:      30% of available rate
Transactional minimum: 40%
Bulk maximum:          30% when contention
Unused reserved rate:  borrowable if safe
~~~

These ratios are examples; real allocations must reflect traffic profiles and SLAs. **Strict priority** can also cause bulk starvation if critical traffic is continuous, so balancing/aging strategies are needed for jobs without tight deadlines.

### Weighted fair queueing and priority

| Goal | Approach |
| --- | --- |
| OTP does not wait behind campaigns | Reserved quota/priority lanes |
| Large tenant does not block small tenants | Per-tenant budgets or weighted fair shares |
| Marketing is not starved indefinitely | Aging, campaign windows, minimum shares |
| Invoices are not misordered logically | Per-aggregate sequencing if required by domain |
| Provider quota is not exceeded | Global limiter downstream of scheduler |

### Multi-tenant isolation at the provider

A provider may support subaccounts/API keys with separate quotas. This separates reputation and cost, but you must verify:

- Do subaccounts have **independent quotas or share a parent quota**?
- Are domain verification/DKIM separate?
- Are bounces/complaints attributed per tenant or across the whole account?
- Can billing/usage be broken down by tenant?
- Is moving a tenant to another provider properly authorized by contract?

Do not create dozens of accounts merely to bypass provider quotas or terms; design within policy and legal requirements.

## 14. Retry amplification: more errors burn more quota

If all send attempts have an independent failure probability \(p\) and are retried indefinitely until success, the expected number of attempts is:

\[
A = \frac{1}{1-p}
\]

For example, \(p=0.1\):

~~~text
Expected attempts = 1 / (1 - 0.1)
                  ≈ 1.111 attempts per recipient
~~~

**This model holds only for independent errors and unlimited retries**, and does not reflect a prolonged outage or hard quota exhaustion. Production must cap attempts and enforce deadlines.

With at most \(N\) attempts under the same assumptions:

\[
A_N = \sum_{k=0}^{N-1} p^k
\]

For example, 3 attempts with p=0.1:

~~~text
Expected attempts = 1 + 0.1 + 0.01
                  = 1.11
~~~

### Outages break the independence assumption

When an ESP suffers a 20-minute outage, nearly every retry during that period may fail. If 10,000 jobs retry every 5 seconds:

~~~text
10,000 jobs / 5 seconds = 2,000 attempts/s
~~~

This can be hundreds of times normal traffic, causing a retry storm and extending recovery time. Instead of retrying jobs tightly in lockstep, use **exponential backoff + jitter**, circuit breakers/adaptive throttling, and a coordinating scheduler.

### Retry only appropriate errors

| Outcome category | Example | Handling |
| --- | --- | --- |
| **Transient, definitely not accepted** | Cannot connect to SMTP before sending data | Retry with backoff |
| **Provider throttled** | Rate/quota feedback | Honor Retry-After / wait for window |
| **Permanent recipient reject** | Invalid or disallowed address | Do not retry endlessly; suppress/review |
| **Authentication/config error** | Invalid credentials or verified domain | Pause lane/provider, alert |
| **Template/model invalid** | Missing required variable | Do not retry SMTP; fix content |
| **UNKNOWN SMTP result** | Timeout after DATA when it may have been accepted | Reconciliation/risk policy |
| **Recipient complaint/bounce** | Provider report | Suppression and reputation investigation |

### Retry budget

Beyond send quota, maintain a **retry budget**:

~~~text
Max attempts per notification:        5
Max retry traffic share:             15% of provider capacity
Max age for OTP retry:                before token expiry
Max age for transactional retry:      by business SLA
Max daily tenant retry consumption:  configured budget
~~~

These thresholds are examples, not default optimal values. A retry budget prevents a provider outage from consuming all capacity and causing new traffic to fail as well.

## 15. Why can SMTP outcomes be ambiguous?

A snippet like:

~~~java
sender.send(message);
~~~

may throw an exception when a socket is reset. Yet the exact point of failure matters:

~~~text
Client -> SMTP server: MAIL FROM
Client -> SMTP server: RCPT TO
Client -> SMTP server: DATA + message bytes
Server -> Client:      acceptance response
~~~

If the client finished transmitting DATA but lost the response, **the server may already have accepted the message**. Unconditional retries can deliver two identical emails to the recipient, both consuming fees and quota under provider policy.

### Idempotency differs across transports

Some ESP APIs support a request idempotency key or querying delivery by request ID; standard SMTP has no universal exactly-once mechanism across all providers. Check the actual provider contract.

### Notification identity

~~~text
notificationId: logical business notification
attemptId:      each transport submission attempt
providerId:     accepted message / request ID if reported
templateRevision: pinned content
recipientId:    logical recipient
~~~

Keeping these identifiers separate aids reconciliation and avoids confusing “retrying the same notification” with “creating a new notification”.

### Do not rely on the Message-ID header as guaranteed dedup

The email Message-ID supports correlation/threading, but does not make an SMTP provider automatically deduplicate resubmitted messages. True idempotency requires a business key, provider-supported mechanisms where available, attempt history, and reconciliation.

## 16. Retry backoff, jitter, and quota feedback

A bounded retry schedule can use:

\[
d_k = \min(d_{\max}, d_0 \times 2^{k-1})
\]

Then add jitter, such as picking a random delay within a safe range so all jobs do not wake up simultaneously.

~~~text
Attempt 1: immediate
Attempt 2: after ~1-2 seconds
Attempt 3: after ~2-4 seconds
Attempt 4: after ~4-8 seconds
Attempt 5: after ~8-16 seconds
~~~

**This schedule is illustrative only**; do not use it as-is for OTPs if the remaining TTL is too short or if the quota window requires waiting longer.

### Honor Retry-After

With an ESP HTTP API, the provider may return **429** and **Retry-After** (if supported). The app must parse the header as seconds or an HTTP date per contract while still capping retries by business expiry. SMTP uses 4xx/5xx reply codes and different enhanced status codes; do not map an HTTP status directly onto SMTP by assumption.

### Circuit breaker and bulkhead

When a provider repeatedly times out:

~~~text
Provider A unhealthy
    -> circuit opens
    -> pause A submissions
    -> reschedule eligible jobs
    -> optional failover to preconfigured B
    -> probe A after cool-down
~~~

Do not use a circuit breaker to silently drop notifications or bypass durable status tracking. A **bulkhead** isolates threads/connections/pools per provider or purpose so one slow destination does not exhaust shared resources.

### Retry budget by root cause

A 60-second provider rate limit should be treated differently from a few seconds of network flakiness. **Quota-depleted-until-next-day errors** must not turn into millions of retries within the same window.

## 17. Priority and deadlines for OTP, reset, and security mail

For notifications with deadlines, **total latency** matters more than raw throughput:

\[
T_{\text{end-to-end}} =
T_{\text{enqueue}} +
T_{\text{queue wait}} +
T_{\text{render}} +
T_{\text{quota wait}} +
T_{\text{submit}} +
T_{\text{provider delivery}}
\]

Not every segment can be measured precisely: **provider delivery** may lack telemetry or occur asynchronously. The system should define SLOs around verifiable measurement boundaries, such as **accepted by provider** within a given duration, and not label that as user received.

### TTL-based scheduling

~~~text
OTP created at 10:00:00
OTP expires at 10:05:00

At 10:04:55:
  job still pending
  estimated quota wait = 30 seconds
  -> sending now may be useless
~~~

A scheduler can mark it **EXPIRED** or emit an alternative status notification according to business rules. Do not attempt to send an already-expired token as if it were still useful.

### Deadlines and priority are two different dimensions

A security alert may be critical without having a strict 30-second hard TTL; an OTP has a very short lifespan. The scheduler should consider purpose, deadline, expected completion, and fairness rather than relying solely on a raw integer priority.

### Capacity reserves must be enforced

If a bulk job is allowed to consume the entire daily account quota, a critical reservation on paper has no effect. The admission controller and quota ledger must enforce reservations before every submission, or use separate providers/subaccounts when permitted.

## 18. Batching and fan-out strategies

**Batching** can reduce API or rendering overhead, but must preserve privacy, tracking, and accurate quota accounting.

### One email to multiple recipients is not always appropriate

~~~text
To: alice@example.test, bob@example.test, carol@example.test
Subject: Your account details
~~~

A multi-recipient message is unsuitable for personal accounts, OTPs, content containing private data, or per-recipient unsubscribe tokens. It can also expose email addresses to other recipients.

### ESP Batch APIs differ from multi-recipient MIME

An ESP may allow a single API request containing multiple personalization entries that sends separate messages to each recipient. Read the actual contract:

- Does quota count one API request or all recipients?
- Is the rate limit per batch object or per recipient?
- Is there per-item idempotency?
- Does the response support partial success?
- Does each item have an independent provider ID for reconciliation?
- What is the maximum payload size?

Do not adopt batching just to lower request counts if it makes handling partial failure retries hard to control.

### Batch windows affect latency

Waiting to accumulate 1,000 emails before sending may optimize overhead while delaying OTPs. Batching can be used for marketing/digests and single low-latency submission for critical mail. Batch jobs need configurable max wait times and max sizes.

### Fan-out can be reduced at the business level

Instead of sending 20 emails for 20 minor actions:

~~~text
20 low-priority events
    -> aggregate daily digest
    -> 1 notification
~~~

However, **do not merge** legally required, transactional, or security emails just to save cost if the domain requires separate events. Any optimization must be approved by domain policy.

## 19. Cost structure: more than just email sending fees

A production cost model should compute **total cost of ownership (TCO)**:

\[
C_{\text{total}} =
C_{\text{provider}} +
C_{\text{compute}} +
C_{\text{storage}} +
C_{\text{network}} +
C_{\text{observability}} +
C_{\text{operations}} +
C_{\text{compliance}}
\]

### Cost categories

| Category | Examples | Drivers |
| --- | --- | --- |
| **Provider send charges** | Per recipient, volume tiers, subscription, overage | Higher email/recipient counts |
| **Dedicated IP / warm-up** | Dedicated IP plans, reputation management | Volume/segmentation and deliverability |
| **Compute** | Worker CPU, memory, connections | HTML rendering, MIME/attachments, retries |
| **Database** | Outbox rows, indexes, transactions | Attempts/history/retention |
| **Queue/broker** | Storage, requests, data transfer | Backlog and payload size |
| **Attachments/object storage** | Store/read files, scanning | Count, size, retention |
| **Network egress** | Email/attachment uploads, cross-region | Bytes * attempts |
| **Observability** | Logs, traces, metrics | Cardinality, raw MIME, event volume |
| **Delivery feedback** | Webhook ingestion, event retention | Bounce/delivery/open/click signals |
| **Operations** | On-call, incidents, provider support | Complexity, multi-provider |
| **Compliance/security** | Data residency, audits, encryption, retention | Access controls, retention duration |

No single price list fits all providers. One provider may offer a free tier, another charges a base fee plus a rate per 1,000 recipients, and another bills by API requests or email category. Formulas must reflect the **active contract and pricing schedule** when making purchasing decisions.

## 20. Cost calculation formulas across scenarios

Suppose a provider bills by **billable recipient units**, at price \(p\) per 1,000 units plus a subscription fee \(C_0\):

\[
C_{\text{provider}} =
C_0 + \frac{R_{\text{billable}}}{1000} \times p
\]

If tiers apply, use **piecewise pricing** per bracket rather than multiplying total volume by the final tier rate.

### Hypothetical example (not a quote)

~~~text
Logical recipient volume/month:  2,160,000
Billable units (assumed):        2,160,000
Illustrative price:             0.15 USD / 1,000 units
Illustrative fixed fee:         50 USD/month
~~~

Calculation:

~~~text
Variable fee = 2,160,000 / 1,000 * 0.15 USD
             = 324 USD
Provider estimate = 50 + 324 = 374 USD/month
~~~

This example **intentionally assumes billable = logical recipients**. If the provider bills by attempts, accepted recipients, reserved volume, or volume tiers, the result will differ. Taxes, support plans, IPs, network, and attachment storage are not included either.

### Cost units must be used consistently

You can track:

~~~text
Cost / 1,000 logical notifications
Cost / 1,000 recipient attempts
Cost / 1,000 accepted recipients
Cost / 1,000 delivered recipients (if telemetry is sufficient)
Cost / one successful business notification
~~~

These figures differ. If 100,000 recipients are submitted but only 90,000 are delivered, **cost per 1,000 delivered** is higher than cost per 1,000 submitted, even when the provider unit price stays unchanged.

## 21. Growth scenario modeling and sensitivity analysis

Do not choose a provider based on a single “next month's average cost” projection. Build at least three scenarios:

| Assumption | Base | Growth | Stress |
| --- | ---: | ---: | ---: |
| Logical recipients/month | 1,000,000 | 3,000,000 | 8,000,000 |
| Attempts/recipient | 1.02 | 1.04 | 1.12 |
| Peak recipients/s | 30 | 120 | 400 |
| MIME size p95 | 100 KiB | 150 KiB | 500 KiB |
| Maximum burst | 5 minutes | 15 minutes | 30 minutes |
| Provider outage exercise | 5 minutes | 30 minutes | 2 hours |

**All numbers in this table are exercise assumptions**; they are not verified capabilities of Spring Mail or any provider.

### Which parameters are typically most sensitive?

- **Volume** directly affects provider fees and queue/storage.
- **Peak rate** determines SLO attainment and rate limits.
- **Retry factor** can spike rapidly when a provider fails.
- **Payload size** drives network, memory, and storage.
- **Per-domain delivery rate** can bottleneck even when global provider quota remains available.
- **Outage duration** determines required backlog capacity and recovery drain time.

### Finding the break-even point

Suppose option A has a low fixed fee and high variable fee; option B has a high fixed fee and low unit price. You can solve:

\[
C_{0A}+r\,p_A=C_{0B}+r\,p_B
\]

where \(r\) is thousands of billable units. The crossover threshold is only useful when both options have equivalent **reliability, sender reputation, compliance features, and deliverability**, or when those factors have been evaluated separately.

### Do not overlook migration costs

A provider that is 10% cheaper may cost the team months to integrate event tracking, redo domain verification, and test compatibility. Engineering effort and operational risk can outweigh send-fee savings.

## 22. MIME payload, attachment, and egress costs

A 30 KiB HTML email with no attachments has a completely different profile from an invoice email carrying a 5 MiB PDF.

### Base64 increases transmitted bytes

Binary attachments are typically MIME transfer-encoded (for example, base64). Base64 adds roughly **4/3** overhead before accounting for line wrapping and MIME headers.

~~~text
PDF binary size:      5 MiB
Base64 approximate:   5 * 4/3 ≈ 6.67 MiB
MIME overhead:        headers, boundaries, line breaks, body...
~~~

If sending 10,000 such attachments:

~~~text
Approx encoded payload = 10,000 * 6.67 MiB
                       ≈ 65 GiB
~~~

This is an outbound email payload estimate, not an egress bill: network paths, TLS, and how the provider ingests data can differ. With **multiple retries**, the same bytes may be transmitted repeatedly.

### Why can a 20 MiB file exceed a 25 MiB limit?

Max MIME size often counts the **entire message after encoding**, not just the raw file. A 20 MiB binary becomes roughly 26.7 MiB in base64 before other overhead, so you must not treat the provider's total message limit as the raw attachment limit.

### Should attachments be converted into links?

For large files, you can send a **trusted signed download link** instead of attaching raw bytes:

~~~text
Recipient receives:
  "Your report is ready"
  https://app.example.test/download/opaque-id
~~~

Benefits: lower SMTP egress, lighter emails, and access control. However, it requires:

- Authentication/authorization for the file.
- Signed link TTL and resend policy.
- Data residency and retention.
- Accessibility and mobile experience.
- Avoiding token/file ID leakage in logs or analytics.
- Not mutating the historical file referenced by the email.

Do not replace legally required or mandatory attachments with links if business rules or regulations require direct file delivery.

## 23. Costs of storing the outbox and attempt history

A reliable system needs to store:

~~~text
Notification row
  - notificationId
  - tenant/purpose
  - recipient reference
  - template revision
  - model snapshot reference
  - status and timestamps

Attempt rows
  - attemptId
  - provider
  - started/ended
  - outcome category
  - provider message ID

Delivery events
  - accepted/delivered/bounced/complaint
  - event timestamp
  - source signature validation
~~~

If every email is stored as 2 MiB of raw MIME in the database, 1 million emails generate roughly **2 TB of raw data** before indexes, replicas, and backups. Do not store raw MIME bytes indefinitely for every notification merely to simplify retries.

### Store metadata and content separately

One option:

- The outbox row stores the model reference, template revision, metadata, and status.
- Object storage holds MIME/attachments when retention or business policy requires them.
- Attempt history is separated from the outbox so it can be archived/purged.
- Logs record only redacted IDs and reason codes.
- Content snapshots have dedicated encryption and lifecycle policies.

### Cost of a hot database table

If the outbox only receives INSERTs without archiving, indexes over tens of millions of rows make due-job queries, VACUUM, and backups expensive. You can partition by time/tenant, index on status+available_at, archive terminal jobs, and enforce retention.

### Do not delete everything just to cut storage fees

Invoices, transactional notices, and security events may require audit trails by contract or regulation. Retention must follow **purpose, personal data rules, and applicable regulations**, not storage cost alone.

## 24. Cutting costs by eliminating unnecessary emails

The most effective savings do not necessarily come from picking the cheapest provider. Before sending, the system can eliminate low-value notifications:

1. **Dedup** identical business event + recipient + purpose per policy.
2. **Suppression** for addresses with hard bounces, complaints, or valid unsubscribes.
3. **Consent** enforcement for marketing; never send without valid permission.
4. **Aggregation/digest** for low-priority events.
5. **Debounce** when state changes repeatedly within a short window.
6. **Expiry** dropping OTPs/notifications that lose value before send.
7. **Recipient selection** avoiding unnecessary fan-out.
8. **Correct retry classification** so permanent failures are not re-sent.
9. **Payload optimization** safely compressing stored content when appropriate; email attachments should not always be zipped.
10. **Template/asset reuse** caching immutable sources rather than over-rendering.

### Do not “optimize” by dropping required emails

For security alerts, receipts, or legally/contractually mandated notices, merging or dropping notifications can violate requirements. Any suppression or aggregation must be vetted with the product owner and legal/security teams when applicable.

### Measure impact after suppression

If 10% of unnecessary notifications are filtered before reaching the provider, provider fees drop proportionally per billing basis, but total TCO does not necessarily drop by 10%: most fixed, database, and infrastructure costs may still remain.

## 25. Choosing SMTP relay, ESP API, or a hybrid approach

**Spring Framework Mail** provides an SMTP-sending abstraction built on Jakarta Mail. Some email service providers also offer HTTP APIs with varying support for batching, templates, tagging, event tracking, or idempotency.

| Criterion | SMTP via JavaMailSender | ESP HTTP API |
| --- | --- | --- |
| **Java integration** | Supported out of the box by Spring Mail | Requires SDK/HTTP client/provider adapter |
| **Protocol standard** | Widely supported SMTP, relay-swappable | APIs vary by provider |
| **Quota visibility** | SMTP replies and separate provider dashboard/API | Often includes HTTP headers/quota APIs |
| **Idempotency** | No universal exactly-once guarantee | Supported by some providers; must verify |
| **Per-message metadata** | Headers/custom tracking depending on provider | Often provides dedicated tags/metadata |
| **Batching/personalization** | MIME/recipients managed by the app | May support native batches |
| **Attachments** | MIME parts via Jakarta Mail | Depends on API payload/provider policy |
| **Delivery events** | Typically via provider webhooks/dashboard | Typically includes event endpoints/systems |
| **Vendor portability** | Higher at the basic transport level | API features carry lock-in risk |
| **Throughput** | Depends on SMTP relay/connection reuse | Depends on API quotas/batch behavior |

### When is SMTP a good fit?

- The application already uses Spring Mail and sends moderate volumes.
- Specialized API features are not needed.
- The provider offers a stable SMTP endpoint and adequate quota.
- The team wants a portable transport adapter.

### When is an HTTP API helpful?

- You need per-request quota feedback, tagging, personalization, or easily consumed events.
- Throughput/batch requirements are better supported by the provider's API under contract.
- Features like idempotency keys or webhook correlation are needed and their semantics are verified.

**Do not conclude HTTP APIs are always faster or cheaper than SMTP.** Bottlenecks may lie in account/recipient limits, sender reputation, or destination domains rather than the protocol.

### Keep a transport abstraction

~~~java
public interface MailTransport {
    SubmissionOutcome submit(
            PreparedMail mail,
            SubmissionContext context
    );
}
~~~

**PreparedMail**, **SubmissionContext**, and **SubmissionOutcome** are application-defined contracts. An SMTP adapter uses JavaMailSender, while an API adapter calls the provider SDK; the domain and outbox stay decoupled from any single vendor.

## 26. Comparing single-provider vs. multi-provider

Adding provider B can improve availability, but also brings cost and risk:

| Decision | Single provider | Two providers |
| --- | --- | --- |
| **Integration** | Simple | Must maintain two transports/API models |
| **Sender identities** | One set of verified domains | Verify DKIM/SPF/DMARC per provider |
| **Quota** | One allowance | Multiple allowances, but never assume they sum freely |
| **Reputation** | Concentrated in one place | Must warm up and monitor each provider |
| **Delivery events** | One webhook schema | Must normalize and deduplicate |
| **Outage recovery** | Queue waits for recovery | Failover can continue sending if policy allows |
| **Fixed costs** | Typically lower | Higher fees, testing, monitoring, and support |
| **Incident complexity** | Fewer branches | Must distinguish retries/failover/unknown |

### Failover must not cause duplicate sends

~~~text
Attempt A:
  Send via provider A
  Client timeout after message accepted?
  Outcome UNKNOWN

Naive failover:
  Immediately send via provider B
  -> recipient may get duplicates
~~~

You must distinguish a **proven provider failure before acceptance** from an **unknown submission outcome**. When UNKNOWN, use reconciliation or an explicit business policy on duplicate risk, especially for OTPs/tickets.

### Domain configuration

If two providers send for the same domain, SPF/DKIM/DMARC and Return-Path/bounce handling must be compatible. Failing over without proper sender verification can cause messages to be rejected or harm reputation. Never use provider B as a “backdoor” to bypass an anti-abuse suspension on provider A.

### When is multi-provider worth it?

Examples:

- High volume, mission-critical service.
- Measured RTO/SLO with high provider outage cost.
- Two genuinely independent providers across failure domains.
- Team capacity to operate, test, reconcile, and sync suppression.
- Data policies permit routing through both providers/regions.

If an app sends only a few thousand emails/month without strict availability requirements, **one reliable provider + outbox + monitoring** is usually far simpler.

## 27. Data residency, privacy, and compliance are part of the choice

Emails often contain PII: names, addresses, invoice contents, verification codes, and attachments. A cheap provider in another region may violate data policies.

### Questions to include in vendor evaluation

- Which regions does email data traverse?
- How long does the provider retain raw content, event logs, and attachments?
- Are region pinning options and an appropriate data processing agreement available?
- Is encryption enforced in transit and at rest?
- Are internal access controls/role separation and audit logs in place?
- What is the deletion process for data and backups?
- Do webhooks support signatures and replay protection?
- Can bounce/complaint/suppression data be exported/migrated?
- What are the SLA, support response times, and incident disclosure terms?
- How does the provider support verified domains, DKIM, DMARC, and TLS policies?

### Do not optimize by compromising security

Never disable TLS certificate verification or bypass suppression to achieve higher throughput or lower cost. A security incident can destroy domain reputation and cost far more than SMTP fee savings.

### Do not spread raw MIME widely across the system

Queue messages or debug logs containing raw MIME create multiple copies of PII. Use metadata + references to access-controlled object storage with purpose-based retention and auditing, and never log OTPs or sensitive links.

## 28. Spring Mail configuration and timeouts

An illustrative Spring Boot SMTP configuration (values are examples only):

~~~properties
spring.mail.host=smtp.example.test
spring.mail.port=587
spring.mail.username=${MAIL_USERNAME}
spring.mail.password=${MAIL_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
~~~

Timeouts are in **milliseconds** per JavaMail SMTP properties. **STARTTLS required** mandates upgrading to TLS; hostname verification prevents connecting to an imposter server. Verify the actual truststore/certificates and the provider's port/auth mechanism. Never commit passwords directly in the repository; use secrets/config injection.

### Quota does not live in these properties

~~~properties
spring.mail.properties.mail.smtp.timeout=10000
~~~

bounds wait time, **not** a 10,000-email limit. Provider quotas must be enforced by an application-level rate/quota controller or ESP policy.

### Timeouts prevent hung workers

Without timeouts, a slow socket can block a thread indefinitely. Under heavy load, this exhausts worker concurrency and backs up the queue. However, overly short timeouts can increase UNKNOWN outcomes and retries during transient network slowness; tune based on observed latency.

### MailException and outcomes

Spring Mail provides **MailException** and subclasses (such as MailSendException, MailAuthenticationException). These exceptions help categorize errors, but cannot definitively prove whether an SMTP server accepted a message across all network failures. The transport adapter must record attempt context and handle UNKNOWN cautiously.

## 29. Never send synchronously inside an HTTP request

Easy-to-write code:

~~~java
@PostMapping("/orders/{id}/confirm")
public ResponseEntity<?> confirm(@PathVariable String id) {
    orderService.confirm(id);
    mailSender.send(...);
    return ResponseEntity.ok().build();
}
~~~

However:

- If SMTP takes several seconds, HTTP latency spikes.
- If the client times out and retries the request, the order/email may be duplicated.
- The DB transaction may commit while mail sending fails, producing a misleading response.
- Exhausted SMTP quota causes the business request to fail even after the order is confirmed.
- Bursts tie up HTTP thread pools with SMTP I/O.

### The outbox solution

~~~text
HTTP request
    |
    v
BEGIN DB TRANSACTION
  Update order
  Insert notification outbox row
COMMIT
    |
    v
HTTP response: order confirmed, notification queued

Async worker
    |
    v
Rate / quota permit
    |
    v
JavaMailSender.send(...)
    |
    v
Update attempt status / await delivery events
~~~

In responses/APIs, distinguish **business action completed** from **email submitted/delivered**. Never report “email sent successfully” when only an outbox row was inserted.

### The outbox must participate in the appropriate transaction

If committing the order and inserting the outbox row happen in two decoupled transactions, the worker can lose the sending intent if the process crashes between steps. When business tables and the outbox share a database, commit them atomically. Across separate databases/brokers, use an equivalent pattern or explicitly accept the trade-off.

## 30. Example notification structure and delivery states

A notification record might contain:

~~~java
import java.time.Instant;
import java.util.UUID;

public record NotificationJob(
        UUID notificationId,
        String tenantId,
        String purpose,
        String recipientReference,
        UUID templateRevisionId,
        Instant createdAt,
        Instant availableAt,
        Instant expiresAt,
        int attemptCount
) {
}
~~~

States:

~~~java
public enum NotificationState {
    PENDING,
    IN_FLIGHT,
    RETRY_WAIT,
    ACCEPTED,
    UNKNOWN,
    PERMANENT_FAILED,
    EXPIRED,
    CANCELLED
}
~~~

### State diagram

~~~text
PENDING
  |
  +-- deadline exceeded --> EXPIRED
  |
  '-- quota permit + claim --> IN_FLIGHT
                                |
                 +--------------+----------------+
                 |              |                |
                 v              v                v
              ACCEPTED       RETRY_WAIT         UNKNOWN
                                 |                |
                                 v                v
                              PENDING          RECONCILE
                                 |                |
                                 v                v
                              IN_FLIGHT       terminal or controlled retry
~~~

**ACCEPTED** means the provider/server acknowledged submission based on client-observed feedback, not yet delivered. **UNKNOWN** holds cases where neither acceptance nor rejection can be proven. These states and names are application-defined models.

### Illustrative outbox schema

~~~sql
CREATE TABLE mail_notification_outbox (
    notification_id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    dedup_key VARCHAR(250) NOT NULL,
    purpose VARCHAR(60) NOT NULL,
    recipient_ref VARCHAR(200) NOT NULL,
    template_revision_id UUID NOT NULL,
    payload_ref VARCHAR(255) NOT NULL,
    status VARCHAR(40) NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    lease_token UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mail_notification_business
        UNIQUE (tenant_id, dedup_key)
);

CREATE INDEX idx_mail_notification_due
ON mail_notification_outbox (
    available_at,
    notification_id
)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

This is an application-designed PostgreSQL schema, **not a table created automatically by Spring Mail**. **dedup_key** prevents duplicate intents per business rules; lease_owner/lease_token prevent two workers from sending the same job if claims are implemented atomically with fencing checks.

### Do not hold transactions open during SMTP sends

A worker should:

1. Claim the job using a short transaction.
2. Release the DB lock.
3. Wait for a permit and submit via transport with timeouts.
4. Record the result in a new transaction, checking the lease token/version.

Holding a row lock across network I/O causes a slow provider to trigger database lock contention and throttle throughput.

## 31. Example decoupling the quota controller from JavaMailSender

In Spring, **JavaMailSender** handles composing and SMTP submission. An application-built **quota controller** decides whether a job may begin an attempt.

~~~java
import java.time.Instant;

public record QuotaRequest(
        String provider,
        String accountId,
        String tenantId,
        String purpose,
        String recipientDomain,
        int recipientUnits
) {
}

public record PermitDecision(
        boolean allowed,
        Instant retryAt,
        String reason
) {
}

public interface MailQuotaController {

    PermitDecision tryReserve(
            QuotaRequest request,
            Instant now
    );
}
~~~

### Contract semantics

- **provider/accountId**: avoids over-allocating quota across accounts sharing a provider limit.
- **tenantId/purpose**: enforces budgets and priorities.
- **recipientDomain**: enables domain-specific pacing when needed.
- **recipientUnits**: if quota counts recipients, a 3-recipient message needs 3 units.
- **retryAt**: earliest time to retry acquiring a permit, instead of sleeping indefinitely in the worker.

### Do not confuse “permit” with “send accepted”

A permit is **permission to attempt sending under local policy**; it does not prove the provider counted quota or accepted the message. After sending, record the attempt outcome and reconcile quota against provider telemetry.

### Atomic reservation

If 10 workers simultaneously call **tryReserve** when a bucket has 5 tokens left, at most 5 total units may be granted under proper semantics; the method must not read the token count and update it without locking.

### Multiple concurrent quota windows

A single request may require:

~~~text
global recipients/second
global recipients/day
tenant recipients/day
purpose recipients/minute
destination domain pacing
SMTP connection concurrency
~~~

The application can perform composite checks via a central quota ledger/atomic script or an allocation scheduler; simply defining a tryReserve method does not automatically guarantee atomicity across stores.

## 32. Example worker and non-blocking reschedule mechanism

A worker should not do:

~~~java
while (!quotaAvailable) {
    Thread.sleep(1000);
}
~~~

for every notification; tens of thousands of jobs would tie up threads/connections or cause excessive polling. Instead, record **availableAt** and yield the worker slot to another job.

### Domain contracts

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface MailOutboxStore {
    List<ClaimedMailJob> claimDue(
            String workerId,
            int maxJobs,
            Instant now
    );

    void reschedule(
            UUID notificationId,
            UUID leaseToken,
            Instant nextAt,
            String reason
    );

    void markAccepted(
            UUID notificationId,
            UUID leaseToken,
            String providerMessageId
    );

    void markUnknown(
            UUID notificationId,
            UUID leaseToken,
            String reason
    );
}

public record ClaimedMailJob(
        UUID notificationId,
        UUID leaseToken,
        String tenantId,
        String purpose,
        String provider,
        String accountId,
        String recipientDomain,
        int recipientUnits,
        Instant expiresAt,
        String payloadReference
) {
}
~~~

These types are **application models**, not Spring Mail APIs. **claimDue** must be atomic and lease-safe; result-recording methods must verify the lease token so an old worker cannot overwrite a new worker's state.

### Illustrative dispatcher service

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class MailDispatchService {

    private final MailOutboxStore store;
    private final MailQuotaController quotas;
    private final PreparedMailSender sender;
    private final Clock clock;

    public MailDispatchService(
            MailOutboxStore store,
            MailQuotaController quotas,
            PreparedMailSender sender,
            Clock clock
    ) {
        this.store = store;
        this.quotas = quotas;
        this.sender = sender;
        this.clock = clock;
    }

    public void dispatchBatch(String workerId, int maxJobs) {
        List<ClaimedMailJob> batch = store.claimDue(
                workerId, maxJobs, clock.instant()
        );

        for (ClaimedMailJob job : batch) {
            Instant now = clock.instant();

            if (job.expiresAt() != null
                    && !now.isBefore(job.expiresAt())) {
                // Production: mark EXPIRED under matching lease.
                continue;
            }

            QuotaRequest request = new QuotaRequest(
                    job.provider(),
                    job.accountId(),
                    job.tenantId(),
                    job.purpose(),
                    job.recipientDomain(),
                    job.recipientUnits()
            );

            PermitDecision permit = quotas.tryReserve(
                    request, now
            );

            if (!permit.allowed()) {
                Instant nextAt = permit.retryAt() != null
                        ? permit.retryAt()
                        : now.plus(Duration.ofSeconds(10));
                store.reschedule(
                        job.notificationId(),
                        job.leaseToken(),
                        nextAt,
                        permit.reason()
                );
                continue;
            }

            SubmissionOutcome result = sender.submit(job);

            switch (result.status()) {
                case ACCEPTED -> store.markAccepted(
                        job.notificationId(),
                        job.leaseToken(),
                        result.providerMessageId()
                );
                case UNKNOWN -> store.markUnknown(
                        job.notificationId(),
                        job.leaseToken(),
                        result.reason()
                );
                case RETRYABLE -> store.reschedule(
                        job.notificationId(),
                        job.leaseToken(),
                        now.plus(Duration.ofSeconds(30)),
                        result.reason()
                );
                case PERMANENT_FAILURE -> {
                    // Production: mark PERMANENT_FAILED
                    // under matching lease.
                }
            }
        }
    }
}

public interface PreparedMailSender {
    SubmissionOutcome submit(ClaimedMailJob job);
}

public record SubmissionOutcome(
        SubmissionStatus status,
        String providerMessageId,
        String reason
) {
}

public enum SubmissionStatus {
    ACCEPTED, RETRYABLE, PERMANENT_FAILURE, UNKNOWN
}
~~~

This example intentionally **leaves out the EXPIRED/PERMANENT_FAILURE branches**, lease heartbeat, provider reply classification, and full backoff policy. It simply illustrates that **quota denial leads to rescheduling** rather than sleeping threads, and **UNKNOWN** is not automatically treated as RETRYABLE. Production must implement the two missing branches before use.

### Be careful with claimed batches not yet sent

If **claimDue** fetches 500 jobs with a 30-second lease while the dispatcher processes sequentially and each SMTP attempt takes 1 second, the leases of the later jobs may expire before their turn. Limit batch size, renew leases properly, or claim only when matching worker/permit capacity is available.

### Do not issue permits and forget them

If a quota token is reserved before a job expires or is cancelled, the controller needs an appropriate refund/capacity accounting policy. With provider daily quota, a successful local reservation does not necessarily mean the provider consumed quota.

## 33. Example Spring scheduling and worker pool

A scheduler in Spring Boot can trigger the dispatcher periodically:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class MailSchedulerConfig {
}

@Component
public class MailDispatchScheduler {

    private final MailDispatchService dispatch;

    public MailDispatchScheduler(MailDispatchService dispatch) {
        this.dispatch = dispatch;
    }

    @Scheduled(fixedDelayString = "${app.mail.dispatch.delay-ms:1000}")
    public void tick() {
        dispatch.dispatchBatch("worker-instance-1", 20);
    }
}
~~~

**worker-instance-1** is only a placeholder; with multiple replicas, use a meaningful instance identity and claim leases from the database. The **@Scheduled** annotation runs on every instance with scheduling enabled and does not automatically perform cluster-wide leader election. Nor should you assume a 1000 ms fixedDelay achieves 20 emails/s: actual throughput depends on pending jobs, latency, batch size, worker threads, permits, and schedules.

### Decoupling scheduling from the send pool

You can configure:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class MailWorkersConfig {

    @Bean("mailSendExecutor")
    ThreadPoolTaskExecutor mailSendExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-send-");
        executor.initialize();
        return executor;
    }
}
~~~

This is a **bounded** worker pool, yet by itself it does not guarantee a global rate limit, does not guarantee outbox durability, and does not control SMTP connection counts without a separate semaphore/controller. Using the executor requires a rejection/backpressure policy; do not queue hundreds of thousands of tasks in memory.

### SMTP connection reuse must be evaluated

Do not assume every **JavaMailSender.send(message)** call maintains a persistent SMTP connection safely shared across threads. Spring's JavaMailSenderImpl manages transport according to how it is invoked; connection pooling/reuse across calls must be verified against the implementation and provider. Optimize connection setup only without exceeding connection quotas, TLS/auth requirements, and concurrency safety.

## 34. Safety when composing MIME inside workers

A worker may need to:

~~~text
Outbox job with pinned template revision
      |
      v
Load model snapshot
      |
      v
Render subject + text/plain + text/html
      |
      v
Validate recipient, sender profile, URLs
      |
      v
Compose MimeMessage
      |
      v
Add inline assets / attachments
      |
      v
Submit via transport adapter
~~~

### Do not store MimeMessage as the primary queue payload

A **MimeMessage** may hold resources, streams, or metadata that are awkward to serialize and can bloat storage. Typically, store **notification ID + template revision + model reference + attachment references**, then compose in the worker.

### Payload size can affect concurrency

Suppose 40 workers concurrently load 20 MiB attachments into RAM:

~~~text
40 * 20 MiB ≈ 800 MiB just for binary attachments
~~~

That excludes MIME base64, HTML, heap overhead, and Java objects. To scale, bound attachment sizes, use appropriate streaming/resource handling, and load-test memory. Do not crank worker count high when p99 MIME size is large.

### Validate MIME size before transport

A job too large for the provider will fail even after 100 retries. Estimate/bound the encoded payload before submission. If exact size is not yet known, validate raw file sizes and include a safety margin for base64/header overhead; verify the provider's total-message limit.

### Plain text and HTML from the same template model

When sending HTML, provide a useful **text/plain** alternative where appropriate. This improves content quality and compatibility, not quota. Rendering HTML and plain text incurs overhead; cache immutable template sources, never personalized output shared across users.

## 35. SLO/SLA: measuring the right moments and outcomes

A mail system has multiple milestones:

~~~text
Notification created
        |
        v
Outbox committed
        |
        v
Worker claimed
        |
        v
Quota permit acquired
        |
        v
Provider accepted
        |
        v
Recipient mail server accepted / delivered event
        |
        v
User opened/read (not always measurable)
~~~

### Candidate SLO definitions

| SLO | Measurement boundary | Caveat about meaning |
| --- | --- | --- |
| **Queue admission latency** | Notification intent → outbox committed | Says nothing about SMTP |
| **Time to first attempt** | Outbox committed → worker first try | Reflects scheduler/quota capacity |
| **Time to provider acceptance** | Outbox committed → accepted | Measurable from app and responses |
| **Delivery latency** | Outbox created → provider delivered signal | Depends on webhook telemetry |
| **Expired unsent ratio** | Jobs hitting TTL before attempt/success | Critical for OTP |
| **Acceptance success rate** | Accepted / attempted | Not Inbox placement |
| **Duplicate suppression rate** | Duplicate intents prevented from sending | Depends on business key/policy |

### SLOs should be segmented by purpose

An illustrative SLO:

~~~text
Critical OTP:
  99% eligible notifications accepted by provider
  within 30 seconds, excluding explicit provider outages
  only if contract actually allows such exclusion

Transactional receipt:
  99.9% accepted within 5 minutes

Marketing:
  99% accepted within scheduled 4-hour campaign window
~~~

All numbers are **illustrative assumptions**. Do not treat them as production defaults. If an SLO excludes provider outages, the exclusion calculation must be disclosed transparently to avoid “greenwashing reports” by omitting major incidents.

### Track p95/p99 instead of the mean

A 2-second mean does not rule out a subset of OTPs waiting 10 minutes. Measure percentiles of **queue wait, quota wait, SMTP submit latency, and end-to-end acceptance latency**, broken down by tenant/purpose/provider enough to locate bottlenecks without exploding metric cardinality.

### Error budget and capacity

If an SLO is 99.9%, the error allowance by that definition is 0.1% of events in the window. When backlogs, throttling, or provider outages burn through error budget, adjust rollouts/campaigns and capacity reservations instead of merely adding workers.

## 36. Observability: quota and delivery status

Application-implemented metrics:

| Logical metric | Type | Meaning |
| --- | --- | --- |
| **mail_outbox_pending_jobs** | Gauge | Number of pending jobs |
| **mail_outbox_oldest_age_seconds** | Gauge | Age of the oldest pending job |
| **mail_outbox_expired_total** | Counter | Number of jobs reaching TTL |
| **mail_send_attempts_total** | Counter | Attempts by outcome |
| **mail_send_acceptance_total** | Counter | Accepted recipients/messages, clear unit definition |
| **mail_send_throttled_total** | Counter | Throttling/rate rejections |
| **mail_send_unknown_total** | Counter | Uncertain outcomes |
| **mail_send_latency_seconds** | Histogram/Timer | Submit latency |
| **mail_quota_remaining_units** | Gauge | Local/provider-reported allowance, clear source |
| **mail_quota_denials_total** | Counter | Local controller permit denials |
| **mail_quota_wait_seconds** | Histogram/Timer | Time spent waiting for quota |
| **mail_retry_attempts_total** | Counter | Retries by reason |
| **mail_provider_connection_failures_total** | Counter | Network/TLS/auth failures |
| **mail_delivery_bounced_total** | Counter | Bounces from provider feedback |
| **mail_delivery_complaints_total** | Counter | Complaints |
| **mail_monthly_billable_units_estimate** | Gauge | Estimated billable units |

**These are illustrative logical names**, not built-in metrics provided by Spring Framework Mail. Many monitoring registries append **_total** automatically to counters or enforce naming conventions; check actual exported names.

### Keep labels low-cardinality

~~~text
provider=primary|secondary
purpose=critical|transactional|bulk
result=accepted|throttled|retryable|unknown|permanent
region=region-a|region-b
tenant_tier=free|business|enterprise
~~~

Do not put recipient emails, notificationId, Message-ID, subject, raw provider error strings, or attempt IDs into metric labels, as doing so explodes cardinality and leaks PII. Detailed IDs belong in access-controlled logs/traces with defined TTLs.

### Define units directly in dashboards

A gauge **mail_quota_remaining_units=1000** is meaningless unless you know whether units are recipients/day, requests/minute, or SMTP connections. Store bounded **quota_kind** and **window** labels, documenting the update source and staleness.

### Provider quota feedback can be stale

Provider dashboards may lag or rate-limit APIs may report estimates. Local counters and authoritative provider usage can diverge; maintain a reconciliation job and safety margins. Never treat stale data as proof of available capacity for a burst.

## 37. Delivery webhooks, bounces, and suppression

Accepted submission does not guarantee delivery to the final mailbox. When a provider supplies feedback:

~~~text
SMTP/API ACCEPTED
     |
     v
Provider processing
     |
     +--> DELIVERED
     +--> SOFT_BOUNCE
     +--> HARD_BOUNCE
     +--> COMPLAINT
     '--> DEFERRED / UNKNOWN
                |
                v
         Event ingestion service
                |
                v
         Update notification state
                |
                v
         Suppression / reputation policy
~~~

### Webhooks must be authenticated

Never trust an HTTP POST claiming “delivered” simply because it hit the webhook URL. Require signature verification, timestamp/replay protection, TLS, allowlisting where appropriate, and store provider event IDs to prevent duplicate processing.

### Events can arrive out-of-order or duplicated

Providers may redeliver webhooks or send a delivery event before the accepted event is committed in the database due to system lag. Consumers must be idempotent, retain event timestamps, and apply state transitions per provider semantics; never let an older webhook overwrite a newer state.

### Suppression protects both cost and reputation

Continuing to send to hard-bounced addresses raises costs and damages reputation. When a user unsubscribes from marketing, stop marketing per consent policy; do not apply a blanket suppression that accidentally blocks mandatory security emails when inappropriate for the purpose.

### Cost per delivered requires reliable feedback

If the provider does not emit comprehensive delivered signals, do not fabricate an exact “cost per delivered” metric from accepted counts. You can report **accepted cost** or **estimated delivery cost** clearly labeled as an estimate.

## 38. Load testing before increasing quota

A load test should answer:

1. How many jobs/second can the system enqueue?
2. Does the quota controller enforce the aggregate limit across multiple replicas?
3. Does the worker pool maintain stable CPU/RAM/connections?
4. How fast does the outbox drain after an outage?
5. Do critical messages still meet deadlines under heavy bulk traffic?
6. When the provider throttles, are retries controlled or do they cause a storm?
7. How do large p95/p99 payloads impact memory and egress?
8. Does multi-provider fallback introduce duplicates or drop suppression state?

### Do not load-test against real recipient mailboxes

Sending hundreds of thousands of synthetic emails to real addresses can violate provider policies, harm reputation, and annoy recipients. Use a **fake transport, SMTP sink/fixture, local test server, or provider sandbox** per contract. If volume testing against a real provider is required, coordinate quota/support and use an authorized environment.

### Test matrix

| Scenario | Input | Observed criteria |
| --- | --- | --- |
| **Steady state** | 50% quota for several hours | Stable backlog, steady resources |
| **Short burst** | 10x baseline for 2 minutes | Bounded queue growth, critical SLO |
| **Long campaign** | 100% bulk allowance | Does not consume critical reserve |
| **Provider throttle** | Inject 429 or SMTP temporary replies | Backoff/jitter, bounded retry share |
| **Provider outage** | 0 capacity for 30 minutes | Durable backlog, recovery drain |
| **Network timeout UNKNOWN** | Server accepts but response drops | No blind resend |
| **Large attachments** | p95/p99 MIME size | Heap, egress, encoding overhead |
| **Cluster scale** | 1 → 4 → 16 replicas | Aggregate provider rate stays within cap |
| **Tenant hotspot** | One tenant sends 90% of traffic | Fairness for other tenants |
| **Daily quota near empty** | Only 1% allowance left | Reserve preserved for critical |
| **Cache/DB slowdown** | Outbox DB latency rises | Bounded workers, no duplicate claims |
| **Delivery feedback storm** | Webhook bursts/duplicates | Signature/dedup, no state corruption |

### Test environment model

~~~text
Load generator
      |
      v
Notification API / Business event simulator
      |
      v
Outbox database
      |
      v
1/4/16 worker replicas
      |
      v
Shared quota controller
      |
      v
Fake MailTransport
  - deterministic latency distribution
  - injected accepts/failures/throttles
  - records recipient units/s
      |
      v
Metrics and assertions
~~~

Crucially, the fake transport must model **provider units** (recipients, requests, windows), not merely count method calls. It can intentionally inject failures to test retry amplification.

## 39. Example quota testing with a fake controller

A small contract:

~~~java
public interface MailQuotaController {
    PermitDecision tryReserve(QuotaRequest request, java.time.Instant now);
}
~~~

Test logic for a provider cap of 20 recipient-units in a fixed-second window:

~~~text
Given:
  Global quota allows at most 20 recipient-units/second.
  5 workers concurrently request 6 recipient-units each.

When:
  All attempt reservation in the same second.

Then:
  Total allowed units <= 20.
  Remaining requests are denied/rescheduled.
  No worker exceeds account allocation due to race.
~~~

### Important negative test

If each pod uses its own 20/s limiter:

~~~text
Pod A: 20/s
Pod B: 20/s
Aggregate: 40/s
Expected global cap: 20/s
=> Test must fail for naive design
~~~

### Testing window refreshes

A fixed window may allow 20 units at the end of second A and 20 at the start of second B — 40 units in a short sliding interval. If the provider enforces a strict **rolling-window**, a fixed-second limiter is not equivalent. Test against actual window semantics.

### Testing expired jobs

~~~text
Given:
  OTP job expires at 10:05:00
  Quota next eligible at 10:05:20

Then:
  Job should not be queued to send an already invalid OTP
  Mark expired / surface a meaningful retry alternative
~~~

Do not test that a retry loop will “eventually deliver”, because the goal has a deadline.

### Testing failure after provider acceptance

Fake transport:

~~~text
1. Records message as accepted.
2. Simulates connection reset before client sees response.
3. Returns UNKNOWN.
~~~

Expected: the system records UNKNOWN and applies reconciliation/policy, **not immediately submitting again on another provider**. This test is especially critical when failover exists.

## 40. Runbook: approaching daily quota exhaustion

Scenario:

~~~text
Provider daily allowance: 50,000 recipients
Reported used:           49,300
Local estimated pending:  2,000
Critical expected:           500
Bulk expected:             1,500
~~~

If jobs run FIFO, bulk may consume the remaining 700 units, leaving incoming critical jobs with no quota.

### Step 1 — Verify units and window

- Is 49,300 measured in recipients/day or requests/day?
- Do provider reports lag?
- Does the daily window reset by timezone, rolling 24h, or a fixed schedule?
- Do other applications share the same account/API key?
- Does the provider also enforce per-second rates or subaccount limits?

### Step 2 — Switch traffic to priority policy

1. Pause/reschedule bulk or campaigns per operator authorization.
2. Protect reserves for OTP, security, and receipts per SLO.
3. Do not increase worker count just because quota is low.
4. Update estimated next eligible times for unsent jobs.
5. If critical queues still exceed allowance, trigger approved escalation, provisioning, or failover.

### Step 3 — Check jobs with deadlines

Do not send OTPs once tokens have expired. Other notifications can remain in the durable outbox until the next window, but delays must be surfaced clearly; never report sent while still queued.

### Step 4 — Quota recovery

After the window resets or the provider expands quota:

~~~text
Rate limit remains active.
Critical queue drains first within fairness policy.
Transactional queue drains next.
Bulk queue resumes at controlled pace.
~~~

Do not run **send all pending immediately**; a sudden burst can violate per-second quotas even after daily quota resets.

### Step 5 — Long-term adjustment

Analyze growth, campaign scheduling, suppression, dedicated capacity, and provider contracts. Configure capacity alerts before reaching 1% remaining quota rather than firefighting daily.

## 41. Runbook: provider throttling or outage

### Symptoms

~~~text
mail_send_throttled_total rises
mail_quota_wait_seconds rises
mail_outbox_oldest_age_seconds rises
SMTP timeout/reply 4xx increases
~~~

Do not conclude all 4xx replies indicate the same quota error; SMTP enhanced codes and provider diagnostics must be interpreted against the contract.

### Procedure

1. Confirm whether the fault is connection/auth/TLS or an actual rate limit.
2. Check allowance, account reputation, and restrictions.
3. Slow submission pacing or open the circuit breaker if appropriate.
4. Apply Retry-After/backoff + jitter for transient cases.
5. Ensure retry traffic share does not starve capacity.
6. Do not infinitely retry permanent recipient failures or auth misconfigurations.
7. Consider failover only when outcomes are safely known or reconciled.
8. Inspect backlog and expired jobs after recovery.
9. Document the incident by purpose and user impact.

### Do not solve by increasing parallelism

Adding pods or threads usually worsens throttling when a provider is constraining traffic. Lower the attempt rate, fix the root cause, and ramp back up gradually based on feedback.

### Unknown outcomes during outages

If a worker times out after transmitting a message, you cannot prove it was “not sent”. An **UNKNOWN** outbox item requires inspecting provider logs/message IDs when available or applying business risk policy; do not blindly fail over and resend without knowing.

### Preparing for next time

Maintain circuit breakers/health status, quota gauges, retry budgets, failover dry runs, and runbooks specifying who is authorized to switch providers, pause campaigns, or raise budgets.

## 42. Runbook: unexpected cost spike

A cost spike does not necessarily reflect user growth. Possible causes include:

- Retry storms.
- Duplicate business notifications.
- A marketing campaign targeting the wrong list/segment.
- An abused tenant or leaked account credentials.
- Larger or more numerous attachments.
- Provider tier shifts or billing basis changes.
- Increased cross-region egress and logs/observability volume.
- The same event republished repeatedly due to an outbox/consumer bug.
- Broken suppression sending to hard-bounced recipients.

### Analyzing “cost per meaningful unit”

~~~text
Monthly spend
    |
    +-- Provider send fee
    +-- Fixed fees and extra services
    +-- Egress / large payloads
    +-- Storage / logs
    '-- Operations

Compare against:
    logical notifications
    recipient attempts
    accepted recipients
    delivered events (if trustworthy)
    business actions triggering email
~~~

If **attempts/logical recipient** jumps from 1.02 to 1.40, that may signal a retry storm. If logical notifications quadruple without an increase in business events, look for duplicate fan-out or loops.

### Remediation steps

1. Break down costs by provider, tenant, purpose, and day.
2. Cross-check attempts, accepted counts, bounces, and webhooks.
3. Inspect retry ratios by error category.
4. Reconcile actual billable units from provider invoices/usage APIs.
5. Audit campaign schedules, recipient selection, and consent.
6. Check bytes per message, attachments, retention, and log volume.
7. Apply controlled budgets/pauses to non-critical traffic.
8. Fix the root cause rather than merely buying more quota.

### Per-tenant chargeback/showback

A multi-tenant platform can display estimated cost by tenant. However, clearly document how shared fixed costs are allocated and note that provider-billed units may differ from local units. Avoid treating estimates as official invoices before reconciliation.

## 43. Choosing an architecture for real-world contexts

Not every application needs 20 services and multiple providers. A good choice balances reliability with operational cost.

| Context | Recommended architecture | Key considerations |
| --- | --- | --- |
| **Internal app, infrequent email** | Spring Mail + small job queue + timeouts | Sender configuration and error handling |
| **SaaS with moderate transactional mail** | DB outbox + workers + global rate limiter | Reliability, quota, tenant isolation |
| **OTP with short deadlines** | Priority lane + reserved capacity + expiry | Latency, fallback policy |
| **Bulk newsletter** | Scheduler + per-campaign pacing + suppression | Reputation, cost, consent |
| **Large multi-tenant** | Fair queues + shared/distributed quota + subaccounts | Fairness, billing, reputation |
| **High-availability business-critical** | Outbox + multi-provider adapters + reconciliation | Unknown outcomes, domains, compliance |
| **Large reports/attachments** | Object storage + secure links or streaming | Egress, privacy, TTL |
| **Strict audit/financial** | Pinned templates/models + attempt history + feedback | Retention, accurate submission statuses |

### Ordered decision flow

~~~text
What are the email purposes and deadlines?
                  |
                  v
What is peak recipient rate + daily/monthly volume?
                  |
                  v
What units/limits does provider actually enforce?
                  |
                  v
Can one provider satisfy rate + quota + compliance + SLO?
           |                                  |
          Yes                                No
           |                                  |
           v                                  v
Single provider + outbox                Evaluate larger tier,
+ global limiter                        second provider, batching,
           |                              or changed requirements
           +----------------+-----------------+
                            |
                            v
              What must be durable/traceable?
                            |
                            v
                  Build retry + UNKNOWN policy
                            |
                            v
                 Load test and instrument cost
                            |
                            v
                 Rollout with safety headroom
~~~

### Disqualifying conditions

A low-cost provider that fails data residency or lacks required domain verification is not a valid option. Likewise, an architecture with high raw throughput that delivers OTPs after TTL expiration fails the business goal.

## 44. Capacity design example for a commerce platform

Suppose a platform has hypothetical traffic:

~~~text
Normal day:
  OTP:            15,000
  Receipts:       35,000
  Alerts:          2,000
  Total logical:  52,000 recipients

Peak event:
  3,000 OTP requests over 2 minutes

Bulk campaign:
  120,000 recipients over 3 hours

Provider fictional profile:
  100,000 recipient units/day
  40 recipient units/s sustained
~~~

### Observations on daily quota

A normal day of 52,000 units already consumes over half the daily quota, so a 120,000-recipient campaign **cannot complete within the same day** under a 100,000 allowance even without normal traffic. You must spread across multiple windows, legitimately raise the allowance, route to separate capacity, or adjust the campaign target.

### Observations on OTP burst

~~~text
3,000 recipients / 120 s = 25 recipients/s
~~~

This sits below the 40/s cap, leaving only about 15/s for other traffic **if the cap is shared**, before counting retries. Reserved rate/priority and latency measurement are required rather than dividing 40/s via FIFO.

### Observations on campaign rate

~~~text
120,000 recipients / (3 * 3,600 s)
≈ 11.1 recipients/s
~~~

This campaign rate fits within the assumed 40/s sustained limit, yet daily quota remains the bottleneck. This illustrates that **rate and volume windows are independent constraints**.

### Preliminary decisions

- Do not send the entire campaign in a single day under the current quota.
- Reserve a dedicated lane for OTP and transactional mail.
- Have the campaign scheduler pace delivery across permitted windows/quotas.
- Use a DB outbox + atomic claim + expiry for OTPs.
- Use a distributed limiter because multiple replicas share one account.
- Monitor remaining daily quota, p95 acceptance latency, and retry budget.
- Measure costs and negotiate tiers if volume grows sustainably.

This example does not claim any real provider offers these exact specs; it demonstrates how to analyze constraints before selecting technology.

## 45. Common architectural mistakes

### Mistake 1 — Counting method calls as recipient counts

**Problem:** a single send(message) call can carry multiple To/Cc/Bcc recipients. If the provider counts per recipient, local quota accounting is wrong.

**Solution:** track the exact units defined by the provider and count recipients before each attempt.

### Mistake 2 — Sizing capacity by daily average

**Problem:** traffic concentrated into 1 minute can be hundreds of times higher than the daily average.

**Solution:** forecast peak per-second/per-minute rates, burst duration, and SLOs.

### Mistake 3 — Adding threads when throttled with 429

**Problem:** worsens throttling and retry storms.

**Solution:** apply pacing, a global limiter, backoff, and quota feedback.

### Mistake 4 — Giving each pod a 20/s limiter against a 20/s account cap

**Problem:** aggregate rate scales with pod count and exceeds the account quota.

**Solution:** use a distributed limiter or bounded quota partitions whose sum stays within limit.

### Mistake 5 — Enforcing a daily limiter without a per-second limiter

**Problem:** even with 10,000 daily units left, a burst of 1,000 requests/s gets rejected.

**Solution:** enforce composite constraints across all windows.

### Mistake 6 — Enforcing a per-second limiter without a daily budget

**Problem:** rate always stays below the per-second cap, yet the daily quota still runs out.

**Solution:** maintain a quota ledger aligned with exact rolling/calendar windows.

### Mistake 7 — Using one FIFO queue for OTP and marketing

**Problem:** critical emails get stuck behind massive marketing batches.

**Solution:** use priority lanes, reserves, and fair scheduling.

### Mistake 8 — Strict priority starving bulk permanently

**Problem:** bulk traffic never drains when critical traffic stays steady.

**Solution:** implement fairness, aging, policy-driven borrowing, and separate SLOs.

### Mistake 9 — Waiting for permits with Thread.sleep per job

**Problem:** ties up threads and fails to scale under large backlogs.

**Solution:** use availableAt/rescheduling and release worker slots.

### Mistake 10 — Treating an infinite queue as a quota solution

**Problem:** backlogs, storage costs, and expired jobs grow indefinitely.

**Solution:** apply admission control, bounded queues/backpressure, and scheduling.

### Mistake 11 — Retrying every exception immediately

**Problem:** causes amplification, extra cost, duplicate sends, and overload.

**Solution:** use error classification, backoff/jitter, circuit breakers, and retry budgets.

### Mistake 12 — Treating a timeout as proof of non-delivery

**Problem:** the provider may have accepted the message before the client lost the response.

**Solution:** track UNKNOWN state/reconciliation and avoid blind failover.

### Mistake 13 — Using Message-ID as guaranteed idempotency

**Problem:** SMTP does not automatically deduplicate resubmissions by Message-ID.

**Solution:** maintain business notification keys, attempt logs, and provider-supported idempotency.

### Mistake 14 — Treating SMTP accepted as delivered

**Problem:** messages can still bounce, defer, or land in spam.

**Solution:** decouple provider acceptance from delivery feedback.

### Mistake 15 — Tracking only total emails sent

**Problem:** hides quota headroom, latency, backlog age, expired OTPs, and costs.

**Solution:** emit metrics broken down by units, purpose, window, and state.

### Mistake 16 — Multiplying provider per-1,000 rate by Java send calls

**Problem:** the billing basis may be recipients, attempts, API usage, or tiers.

**Solution:** model from the provider invoice/usage contract and reconcile regularly.

### Mistake 17 — Ignoring MIME base64 overhead

**Problem:** attachments near the size cap get rejected.

**Solution:** validate total encoded message size with a safety margin.

### Mistake 18 — Scaling worker count regardless of heap

**Problem:** large attachments cause heap pressure/OOM even if the SMTP cap is unchanged.

**Solution:** benchmark p95/p99 payloads, bound concurrency, and stream payloads.

### Mistake 19 — Sending emails inside a DB transaction

**Problem:** network I/O holds locks open and cannot be atomic with SMTP.

**Solution:** use a transactional outbox and independent workers.

### Mistake 20 — Claiming too many outbox jobs at once

**Problem:** leases expire before later jobs are sent, allowing two workers to submit the same job.

**Solution:** claim within real capacity, use heartbeats/fencing, and reschedule cleanly.

### Mistake 21 — Failing over every UNKNOWN attempt

**Problem:** provider A may have accepted it; provider B sends a duplicate.

**Solution:** use reconciliation, explicit risk policies, and provider IDs.

### Mistake 22 — Assuming multi-provider automatically multiplies legitimate quota

**Problem:** accounts may share parent allowances or differ in warm-up/reputation, and must never bypass suspensions.

**Solution:** verify contracts, domain identities, and independent failure domains.

### Mistake 23 — Not syncing suppression across providers

**Problem:** recipients who unsubscribed or hard-bounced on A still receive mail via B.

**Solution:** maintain a shared suppression policy and idempotent event ingestion.

### Mistake 24 — Ignoring data residency for a cheaper provider

**Problem:** email data/attachments may traverse unauthorized regions.

**Solution:** treat compliance as a prerequisite before optimizing price.

### Mistake 25 — Logging raw MIME to track costs

**Problem:** leaks PII/tokens and inflates logging expenses.

**Solution:** log redacted metadata/bytes/IDs with clear retention limits.

### Mistake 26 — Billing from local estimates without reconciliation

**Problem:** local counters drift from provider invoices due to retries, partial successes, or window boundaries.

**Solution:** run periodic usage reconciliation and clearly label estimates.

### Mistake 27 — Sending expired OTPs after an outage

**Problem:** useless spam, wasted cost, and poor user experience.

**Solution:** check expiry before both first and subsequent attempts.

### Mistake 28 — Upgrading tiers without cutting redundant mail

**Problem:** keeps paying to send duplicate, unconsented, or expired notifications.

**Solution:** enforce dedup, suppression, and business-level aggregation first.

### Mistake 29 — Load-testing against real user mailboxes

**Problem:** damages sender reputation, wastes cost, and annoys users.

**Solution:** use a fake provider, test fixture, or authorized sandbox.

### Mistake 30 — Promising exactly-once because an outbox exists

**Problem:** lost SMTP responses or broker redeliveries can still cause multiple attempts.

**Solution:** maintain stable notification identities, idempotency, and UNKNOWN policies; communicate delivery guarantees accurately.

## 46. Case-study exercises and solutions

### A. 2,400 recipients in one minute, provider cap 20/s

**Question:** will adding 100 workers meet the 60-second deadline?

**Answer:** no. Rate-limited throughput is at most around 1,200 units per minute without burst allowance; you need a legitimately higher quota/rate, shifted traffic distribution, or a revised deadline. Queues still buffer work but do not increase provider throughput.

### B. 3 pods, each with a 10/s limiter, provider cap 15/s

**Question:** what is the risk?

**Answer:** aggregate rate can reach 30/s, double the cap. Use a central/distributed rate controller or partition quotas so the sum never exceeds 15/s.

### C. 100 sends, each with 3 recipients

**Question:** if the provider bills per recipient, does this consume 100 or 300 units?

**Answer:** up to 300 recipient slots before considering duplicates or provider-specific rules. Never assume 100 merely because 100 send calls occurred.

### D. Outbox has 10,000 marketing jobs; an OTP waits 20 seconds

**Question:** how should the scheduler be optimized?

**Answer:** use priority lanes and reserved critical capacity instead of a shared FIFO queue. Monitor TTLs and P99 acceptance latency separately for OTPs.

### E. SMTP authentication fails after secret rotation

**Question:** should it retry every second?

**Answer:** no. This is typically a config/auth error; halt or trip the circuit breaker, alert, and fix credentials. Infinite retries only grow the backlog and connection attempts.

### F. Network reset after DATA

**Question:** can it immediately resend via provider B?

**Answer:** only after reconciliation or under an explicit risk policy accepting potential duplicates. A timeout does not prove provider A rejected the message.

### G. Provider has a low monthly fee but stores content in a disallowed region

**Question:** should it be chosen for lower price?

**Answer:** no. Data residency, privacy, and contractual obligations are mandatory constraints.

### H. 20 MiB PDF attachment, 25 MiB max MIME limit

**Question:** is the 20 MiB file guaranteed to send?

**Answer:** no. Base64 expands size by roughly 33%, plus MIME overhead, potentially exceeding 25 MiB. Validate encoded size or send a secure download link if policy permits.

### I. Provider quota has 100 units left, bulk wants 100, and OTPs are expected

**Question:** should bulk consume the rest?

**Answer:** no if policy reserves critical capacity. The quota scheduler/admission controller must protect the reserve or apply proper priority.

### J. Daily cap is not exhausted, yet the provider throttles constantly

**Question:** why?

**Answer:** per-second, request, connection, or domain limits may be exceeded, or dynamic reputation throttling may be active. Daily volume is only one constraint.

### K. Queue is empty, yet delivered rate drops

**Question:** will scaling workers help?

**Answer:** unlikely. An empty queue and steady accepted counts show submission is not the bottleneck; inspect bounces, destination server behavior, authentication/reputation, and provider events.

### L. Cost rises while business events stay flat

**Question:** what should be investigated first?

**Answer:** recipient fan-out, duplicate notifications, retry attempts, payload bytes, provider billing units, and logs; this often signals a retry or loop bug rather than real demand growth.

### M. One tenant sends 90% of traffic

**Question:** should quota be partitioned per tenant?

**Answer:** if fairness/SLAs require it, use weighted shares/budgets and optionally subaccounts; check parent quota sharing and reputation isolation.

### N. OTP has 10 seconds TTL left; quota is next available in 40 seconds

**Question:** keep it queued until a permit arrives?

**Answer:** no if the token will already be invalid. Mark EXPIRED and give the client/UX a proper fallback instead of sending a dead token.

### O. Provider API accepts a batch of 1,000 recipients

**Question:** does it cost only one quota unit?

**Answer:** never assume so. One API request may count as 1,000 recipient units, and partial successes must be tracked per item. Read the specific contract.

### P. Outbox worker acquires a permit, then crashes before SMTP

**Question:** should this count as consumed quota?

**Answer:** separate local reservations from provider usage. Local capacity may be reclaimed by policy, but never treat the local ledger as an authoritative billing report.

### Q. Outbox worker sends successfully, then crashes before markAccepted

**Question:** how should retries work?

**Answer:** the outcome is UNKNOWN to a new worker. Use attempt history and provider reconciliation where available; never resend blindly by default.

### R. Worker load test hits 400 sends/s while provider cap is 50 recipients/s

**Question:** does the system scale well?

**Answer:** the local benchmark proves compose/attempt speed, not permitted provider throughput. End-to-end capacity must account for limiters, quotas, and provider acceptance.

### S. Marketing wants to send a newsletter immediately after daily cap is hit

**Question:** can secondary accounts be spun up to bypass the limit?

**Answer:** do not design to evade policies. Request a provider-approved quota increase, reschedule appropriately, or adjust the contract.

### T. One provider is 15% cheaper but lacks signed delivery webhooks

**Question:** how to decide?

**Answer:** evaluate total cost alongside security, integration, and observability requirements. Do not compare price per 1,000 recipients alone when trustworthy delivery states and verifiable events are required.

## 47. Architecture Decision Record template for mail systems

When deciding to switch providers or scale up, write an **Architecture Decision Record (ADR)** so the team can explain why specific quota, cost, and reliability trade-offs were chosen.

~~~text
Title:
  Mail delivery capacity and provider strategy

Status:
  Proposed / Accepted / Superseded

Context:
  - Business purposes: OTP, receipts, campaigns
  - Daily/monthly logical recipients
  - Peak units/second and burst duration
  - Payload size p95/p99
  - Current provider quotas and billing terms
  - Delivery/privacy/security requirements

Decision drivers:
  - Critical acceptance latency SLO
  - Quota headroom and retry budget
  - Data residency and authentication
  - Operational complexity
  - Total cost of ownership

Options:
  A. Single SMTP provider + durable outbox
  B. Single ESP HTTP API + durable outbox
  C. Primary + secondary provider with failover

Chosen option:
  ...

Expected capacity:
  - Recipients/day
  - Recipients/second sustained
  - Burst reserve
  - Backlog drain time after 30-minute outage

Failure policy:
  - Retryable / permanent / UNKNOWN
  - TTL and expiry
  - Reconciliation and dedup
  - Circuit breaker and incident controls

Cost assumptions:
  - Billable unit definition
  - Base/variable price
  - Storage/egress/compute/on-call
  - Growth sensitivity

Validation:
  - Fake-provider load tests
  - Quota aggregation across replicas
  - Deliverability/security review
  - Provider contract and invoice reconciliation

Revisit triggers:
  - 75% daily quota usage for sustained period
  - p99 SLO failure
  - Vendor pricing change
  - New region/compliance requirement
  - Retry/UNKNOWN ratio outside budget
~~~

These triggers are **illustrative templates**; choose thresholds based on SLOs, reserves, and traffic profiles. Writing an ADR avoids the pitfall of “switching tech for a vendor discount” while ignoring failure behavior or total cost.

### Direct questions an ADR must answer

1. What are the actual quota and billing units?
2. If the provider operates at 50% capacity, do critical notifications still meet deadlines?
3. When quota runs out, which traffic is paused first?
4. If SMTP accepts but the response is lost, what does the system do?
5. Who is authorized to pause bulk mail or switch providers?
6. To what level can recipient delivery status be verified?
7. Which metrics show that the backlog exceeds drain capacity?
8. If recipient volume grows 5x, which components must change?

## 48. Pre-deployment and scaling checklist

### Data and load modeling

- Define **event → logical notification → recipients → attempts**.
- Produce average, p95, p99, and burst-window estimates.
- Forecast monthly/quarterly volume and campaign traffic.
- Profile payload sizes, attachments, and retention.
- Define deadlines/SLOs by purpose, not just total emails/day.
- Track duplicate/suppression/consent rates to avoid over- or under-estimating.

### Provider contract

- Know quotas in terms of recipients/messages/API requests.
- Know daily/monthly and rate windows, timezone, and reset semantics.
- Know connection, max MIME size, and batch limits.
- Know how quota usage/remaining is reported and its update lag.
- Verify domains, SPF/DKIM/DMARC, TLS, and auth mechanisms.
- Verify regions, data processing terms, and retention.
- Know bounce/complaint reporting and signed webhook support.
- Establish escalation/support paths for quota increases.

### Cost

- Distinguish billable units from send attempts.
- Account for fixed, variable, and tier/overage charges.
- Account for compute/DB/queue/egress/attachments/monitoring/on-call.
- Model base/growth/stress scenarios.
- Track cost per logical/accepted/delivered unit with clear definitions.
- Set budget alerts and tenant showback/chargeback if multi-tenant.
- Reconcile against invoices rather than relying solely on local estimates.

### Throughput and worker design

- Use a durable outbox/queue whenever reliability is required.
- Bound worker concurrency and configure sensible timeouts.
- Use a global/distributed limiter matching the quota scope.
- Enforce both rate and volume windows.
- Enforce per-purpose/tenant fairness and critical reserves.
- Apply per-domain pacing if required by providers or delivery behavior.
- Reschedule on permit denial instead of sleeping worker threads.
- Claim jobs atomically with leases/fencing and proper batch sizing.
- Never hold DB transactions open across SMTP I/O.

### Retries and availability

- Classify retryable, permanent, throttled, and UNKNOWN outcomes.
- Implement exponential backoff/jitter, retry budgets, and expiry.
- Implement circuit breakers/bulkheads and health checks.
- Review multi-provider failover for UNKNOWN outcomes.
- Maintain a shared suppression policy and webhook deduplication.
- Never claim exactly-once SMTP.
- Prepare runbooks for quota exhaustion, outages, provider rejections, and cost spikes.

### Security and privacy

- Never log credentials or raw tokens.
- Validate template and recipient links.
- Enforce MIME/attachment size limits and storage/streaming policies.
- Treat data residency as a hard constraint.
- Authenticate webhooks with replay protection and idempotency.
- Enforce suppression/consent according to purpose.
- Define retention and access controls for content and attempt history.

### Testing and operations

- Use fake/sandbox providers that accurately model quota units and windows.
- Test multiple replicas without exceeding the global cap.
- Test bursts, outages, recovery/draining, and retry storms.
- Test expired OTPs and priority fairness.
- Test large MIME + attachments and memory usage.
- Test UNKNOWN-after-acceptance and provider failover.
- Monitor oldest pending age, remaining quota, and p99 time to acceptance.
- Compare estimated vs. provider-reported usage/cost.
- Trigger alerts before quota/budget actually runs dry.
- Plan tier/capacity upgrades before forecast thresholds are breached.

## 49. Summary of core principles

~~~text
JavaMailSender
    = SMTP transport abstraction
    != quota manager
    != durable job queue
    != delivery confirmation

Business events
    != logical notifications
    != recipient units
    != send attempts
    != provider billable units

Daily quota
    != per-second rate
    != concurrent connection limit

More threads/pods
    != more provider allowance

Peak throughput
    -> size by burst and deadlines, not average/day

Queue backlog
    -> watch oldest age and net drain rate

Global quota across pods
    -> distributed coordination

Critical vs bulk
    -> reserved capacity and fair scheduling

Retry
    -> classify failures, backoff, jitter, budget

UNKNOWN submission
    -> reconciliation, not automatic double-send

Transactional outbox
    -> durable intent
    != exactly-once SMTP

MIME attachments
    -> encoding overhead, storage, network cost

Provider billing
    -> verify unit and price tiers

SMTP accepted
    != delivered
    != opened

Best provider choice
    -> quota + SLO + reputation + security + compliance
       + operations + total cost
~~~

**Evaluating quota, cost, and scalability** in Spring Framework Mail is an **end-to-end** architectural decision, not just picking an SMTP host or setting a thread count for JavaMailSender. Start by defining the **true load units** (business events, notifications, recipients, and attempts), align quota windows with peak traffic and business deadlines, and build a **durable outbox, cluster-wide limiter, fair scheduler, and controlled retry policy**. Costs must encompass **provider fees, storage, bandwidth, attachments, compute, logging, and operations**, while separating **accepted** from **delivered**. With proper metrics, load testing via fake/sandbox providers, explicit UNKNOWN policies, and quota-exhaustion runbooks, the system can scale without sacrificing critical email delivery, data safety, or budget.
