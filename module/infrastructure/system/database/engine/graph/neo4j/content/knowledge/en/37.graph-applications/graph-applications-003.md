# Fraud Detection Through Account, Device, and Transaction Links

## 1. From Individual Transactions to a Network of Signals

In finance, e-commerce, or digital wallet applications, a single transaction may look completely normal if you inspect only **amount, timestamp, and sender**. However, risk can become apparent when connecting that transaction to **multiple accounts sharing a device**, a **verified fraud-linked account**, or a money-transfer chain through several intermediary accounts.

**Neo4j** fits this need well because its **property graph** model represents entities and links directly:

- **Account:** business account with a stable key, belonging to a tenant/organization.
- **Device:** device or device identifier normalized under security policy.
- **Transfer/Transaction:** transaction event with its own ID, timestamp, and amount.
- **Relationship:** Account **USED_DEVICE** Device; Account **SENT** Transfer; Transfer **TO** Account.
- **RiskCase/Review:** evidence, investigation decisions, and verification timestamps.

This lesson belongs to the **Graph Applications** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module, illustrating how to use **Cypher**, constraints/indexes, relationship/path queries, and optionally **Neo4j Graph Data Science (GDS)** to turn links into **explainable investigative signals**. The end covers implementation with the **Java Driver/Spring Data Neo4j**, testing, and bias/false-positive controls.

> **Business boundary:** an account sharing a device, IP, or recipient with a risky account **does not by itself prove fraud**. The device could be a public terminal, a family device, or share a generic ID; the transaction could be legitimate. The rules and scores in this lesson are **technical illustrations** only and must be evaluated with labeled data and proper review workflows before making real decisions.

### 1.1. Why Is a Graph Better Than Querying Separate Tables Alone?

A relational database can certainly represent all of the information above, but queries detecting **multi-hop connections** may require joining tables repeatedly. In a graph, relationship hops are represented directly:

~~~text
Account A-100 --USED_DEVICE--> Device D-SHARED
Account A-900 --USED_DEVICE--> Device D-SHARED

Account A-100 --SENT--> Transfer T-101 --TO--> Account A-200
Account A-200 --SENT--> Transfer T-102 --TO--> Account A-900
~~~

From that pattern you can ask:

1. **Which accounts share the same device?**
2. **Which accounts are one device away from a confirmed fraud account?**
3. **Is there a transfer chain A → B → C within a short time window?**
4. **Which groups of accounts form a connected component?**
5. **Which signals contribute to an account's review priority?**

A graph does not make every question automatically fast or accurate. **Proper modeling, identity constraints, traversal bounds, input data quality, and result explainability** still determine system quality.

## 2. Designing the Account – Device – Transaction Model

### 2.1. Three Core Nodes and Two Link Patterns

~~~mermaid
flowchart LR
  A["Account<br/>tenantId, accountId"] -->|"USED_DEVICE<br/>firstSeen, lastSeen"| D["Device<br/>tenantId, deviceKey, isPublic"]
  A -->|"SENT"| T["Transfer<br/>tenantId, transferId<br/>amountMinor, occurredAt"]
  T -->|"TO"| B["Account<br/>tenantId, accountId"]
  C["Other account"] -->|"USED_DEVICE"| D
~~~

| Entity / relationship | Important properties | Why needed |
|---|---|---|
| **DemoFraudAccount** | **tenantId**, **accountId**, confirmedFraud | Business key; fraud label comes only from verified outcomes |
| **DemoFraudDevice** | **tenantId**, **deviceKey**, **isPublic** | Identifies devices within permitted scope; excludes public terminals |
| **DemoFraudTransfer** | **tenantId**, **transferId**, **amountMinor**, **occurredAt**, **status** | Each transfer is an independent event |
| **DEMO_FR_USED_DEVICE** | **firstSeen**, **lastSeen** | Account–device link with observed timestamps |
| **DEMO_FR_SENT** | Does not need to carry amount | Connects transaction source to a specific Transfer |
| **DEMO_FR_TO** | Does not need to carry amount | Connects Transfer to the receiving account |

**Why should Transfer be a node?** A transaction has an ID, amount, status, timestamp, lookup needs, potential state updates, and auditability. Using an **Account → Transfer → Account** model stores events with a unique **transferId** while avoiding collapsing multiple transfers from the same sender to the same recipient into a single relationship.

In simple cases, you could also store **(:Account)-[:TRANSFERRED {transactionId, amount, time}]->(:Account)**. However, when you need refunds, approvals, disputes, merchants, sessions, and multiple transaction states, a **Transfer node** is usually much cleaner for event lifecycle management.

### 2.2. Do Not Confuse "Same Device ID" with "Same Person"

**deviceKey** is the output of an enterprise-managed identification mechanism, such as a pseudonymous device token or policy-compliant fingerprint. It can change, be reset, be spoofed, or collide. Therefore:

- Never use `deviceKey` as an **Account business key**.
- Never automatically merge two Accounts solely because they share a `deviceKey`.
- Never assume one `deviceKey` maps to a single person.
- Track **observation source**, confidence, TTL, and observation timestamps.
- Sensitive identifiers (IP, cookies, device fingerprints, phone numbers) require collection and retention rules compliant with law and policy.

**tenantId** appears on all three labels because the example assumes a multi-tenant system. Identical `deviceKey` strings across two tenants **must never be linked** unless the organization has legal and policy authorization for cross-tenant processing.

### 2.3. Observation Time vs. Transaction Time

Distinguish:

| Timestamp | Meaning | Purpose |
|---|---|---|
| **Transfer.occurredAt** | Business timestamp when the transaction occurred | Ordering money flow, detecting rapid transfers |
| **USED_DEVICE.firstSeen** | First recorded use of the device by the account | Assessing link history |
| **USED_DEVICE.lastSeen** | Most recent recorded use of the device by the account | Filtering stale links |
| **ingestedAt** (if present) | Timestamp when the event reached the system | Measuring ingestion lag and replays |
| **confirmedAt** (if present) | Timestamp when a case conclusion was verified | Preventing future label leakage during offline training/eval |

Do not infer that an account used a device **continuously from `firstSeen` to `lastSeen`**. Those two timestamps are not a log of every login. If session-level precision is required, model **Login/DeviceObservation** as a separate event with an **eventId**.

## 3. Preparing Practice Data and Constraints

All examples in this lesson use labels starting with **DemoFraud** and relationships starting with **DEMO_FR_**. Run them on a **fresh or clean test database**, not one holding real data. The account/device IDs below are completely synthetic.

### 3.1. Ensuring Unique Business Keys

~~~cypher
CREATE CONSTRAINT demo_fraud_account_key IF NOT EXISTS
FOR (a:DemoFraudAccount)
REQUIRE (a.tenantId, a.accountId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_fraud_device_key IF NOT EXISTS
FOR (d:DemoFraudDevice)
REQUIRE (d.tenantId, d.deviceKey) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_fraud_transfer_key IF NOT EXISTS
FOR (t:DemoFraudTransfer)
REQUIRE (t.tenantId, t.transferId) IS UNIQUE;
~~~

Composite uniqueness constraints prevent creating **two nodes with the same label** and the same full key tuple; Neo4j backs them with indexes. **Uniqueness does not automatically forbid nodes missing part of the key.** In production, enforce pre-write validation or a **node key constraint** if supported by your edition.

### 3.2. Creating Accounts and Devices

~~~cypher
CREATE
  (a100:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-100', confirmedFraud: false
  }),
  (a200:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-200', confirmedFraud: false
  }),
  (a900:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-900', confirmedFraud: true
  }),
  (a300:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-300', confirmedFraud: false
  }),
  (a400:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-400', confirmedFraud: false
  }),
  (a500:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-500', confirmedFraud: false
  }),
  (b100:DemoFraudAccount {
    tenantId: 'bank-b', accountId: 'A-100', confirmedFraud: false
  }),
  (shared:DemoFraudDevice {
    tenantId: 'bank-a', deviceKey: 'D-SHARED', isPublic: false
  }),
  (publicDevice:DemoFraudDevice {
    tenantId: 'bank-a', deviceKey: 'D-PUBLIC', isPublic: true
  }),
  (private:DemoFraudDevice {
    tenantId: 'bank-a', deviceKey: 'D-PRIVATE', isPublic: false
  }),
  (other:DemoFraudDevice {
    tenantId: 'bank-a', deviceKey: 'D-OTHER', isPublic: false
  }),
  (bshared:DemoFraudDevice {
    tenantId: 'bank-b', deviceKey: 'D-SHARED', isPublic: false
  }),
  (a100)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T08:00:00Z'),
    lastSeen: datetime('2026-11-20T08:00:00Z')
  }]->(shared),
  (a200)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T08:30:00Z'),
    lastSeen: datetime('2026-11-20T08:30:00Z')
  }]->(shared),
  (a900)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T09:00:00Z'),
    lastSeen: datetime('2026-11-20T09:00:00Z')
  }]->(shared),
  (a100)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-20T07:00:00Z'),
    lastSeen: datetime('2026-11-20T07:00:00Z')
  }]->(private),
  (a300)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T10:00:00Z'),
    lastSeen: datetime('2026-11-20T10:00:00Z')
  }]->(publicDevice),
  (a400)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T10:30:00Z'),
    lastSeen: datetime('2026-11-20T10:30:00Z')
  }]->(publicDevice),
  (a500)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T11:00:00Z'),
    lastSeen: datetime('2026-11-20T11:00:00Z')
  }]->(publicDevice),
  (a400)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-20T09:00:00Z'),
    lastSeen: datetime('2026-11-20T09:00:00Z')
  }]->(other),
  (b100)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-20T08:00:00Z'),
    lastSeen: datetime('2026-11-20T08:00:00Z')
  }]->(bshared);
~~~

**Device structure:**

| Device | Tenant | Linked accounts | Context |
|---|---|---|---|
| **D-SHARED** | bank-a | A-100, A-200, A-900 | Device to review due to link with A-900 |
| **D-PUBLIC** | bank-a | A-300, A-400, A-500 | Public device; do not draw conclusions from account count |
| **D-PRIVATE** | bank-a | A-100 | Another private device of A-100 |
| **D-OTHER** | bank-a | A-400 | Another private device of A-400 |
| **D-SHARED** | bank-b | A-100 | Different tenant node, unconnected to bank-a |

**confirmedFraud: true** on A-900 is only a **synthetic verified label** for building test cases. In a real system, store verification source, decision timestamp, appeal/correction status, and label usage scope. **A-100 and A-200 are not labeled fraudulent** simply for being linked to A-900.

### 3.3. Creating Transfers with Timestamps and Amounts

~~~cypher
MATCH (a100:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-100'}),
      (a200:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-200'}),
      (a900:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-900'}),
      (a300:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-300'}),
      (a400:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-400'}),
      (a500:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-500'})
CREATE
  (t101:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-101',
    amountMinor: 400000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T09:00:00Z')
  }),
  (t102:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-102',
    amountMinor: 350000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T10:00:00Z')
  }),
  (t103:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-103',
    amountMinor: 10000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T10:30:00Z')
  }),
  (t104:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-104',
    amountMinor: 15000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T11:00:00Z')
  }),
  (t105:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-105',
    amountMinor: 450000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T11:30:00Z')
  }),
  (a100)-[:DEMO_FR_SENT]->(t101)-[:DEMO_FR_TO]->(a200),
  (a200)-[:DEMO_FR_SENT]->(t102)-[:DEMO_FR_TO]->(a900),
  (a300)-[:DEMO_FR_SENT]->(t103)-[:DEMO_FR_TO]->(a400),
  (a500)-[:DEMO_FR_SENT]->(t104)-[:DEMO_FR_TO]->(a300),
  (a200)-[:DEMO_FR_SENT]->(t105)-[:DEMO_FR_TO]->(a900);
~~~

Verification table:

| Transfer | From | To | amountMinor | UTC Time |
|---|---|---|---:|---|
| T-101 | A-100 | A-200 | 400000 | Nov 20, 09:00 |
| T-102 | A-200 | A-900 | 350000 | Nov 20, 10:00 |
| T-103 | A-300 | A-400 | 10000 | Nov 20, 10:30 |
| T-104 | A-500 | A-300 | 15000 | Nov 20, 11:00 |
| T-105 | A-200 | A-900 | 450000 | Nov 20, 11:30 |

**amountMinor** uses the smallest business unit; there is no specific currency unit in this fixture. These are not real bank amounts. If a system supports multiple currencies, store **currency** and convert under controlled rules before summing or comparing thresholds.

**Expected counts:** 7 Accounts, 5 Devices, 5 Transfers, 9 `USED_DEVICE` edges, 5 `SENT` edges, and 5 `TO` edges. This includes the A-100/A-200/A-900 group with a shared device and sequential transfers; the A-300/A-400/A-500 group on a public device; and one independent `bank-b` account.

## 4. Safe Data Ingestion: Stable Keys, Idempotency, and Late Data

### 4.1. MERGE on Business Keys, Not Mutable Properties

In an ingestion pipeline, a **transferId** event may be redelivered due to retries or message brokers. An unconditional **CREATE** would duplicate transactions. Use uniqueness constraints and `MERGE` on **(tenantId, transferId)**.

~~~cypher
// $tenantId, $transferId, $amountMinor, $occurredAt, $status
// come from a validated and normalized payload.
MERGE (t:DemoFraudTransfer {
  tenantId: $tenantId,
  transferId: $transferId
})
ON CREATE SET
  t.amountMinor = $amountMinor,
  t.occurredAt = datetime($occurredAt),
  t.status = $status,
  t.ingestedAt = datetime()
RETURN t.transferId AS transferId;
~~~

If the event already exists, **ON CREATE SET** does not overwrite `amount` or `occurredAt`. This illustrates a **create-once** policy; if real transactions can be amended or reversed, manage explicit versions or distinct event types rather than silently ignoring updates.

**Important:** the same `transferId` with a different payload must be treated as a **data conflict** unless a defined correction workflow exists. Plain `MERGE` without payload comparison can mask upstream ID reuse bugs. Production designs need payload fingerprints/versions, conflict checks, and atomic transactions creating the node alongside its source/destination edges.

### 4.2. Preserving Account and Device Identities

~~~cypher
MERGE (a:DemoFraudAccount {
  tenantId: $tenantId,
  accountId: $accountId
})
ON CREATE SET a.confirmedFraud = false
MERGE (d:DemoFraudDevice {
  tenantId: $tenantId,
  deviceKey: $deviceKey
})
ON CREATE SET d.isPublic = false
MERGE (a)-[u:DEMO_FR_USED_DEVICE]->(d)
ON CREATE SET
  u.firstSeen = datetime($observedAt),
  u.lastSeen = datetime($observedAt)
ON MATCH SET
  u.firstSeen = CASE
    WHEN datetime($observedAt) < u.firstSeen
      THEN datetime($observedAt) ELSE u.firstSeen END,
  u.lastSeen = CASE
    WHEN datetime($observedAt) > u.lastSeen
      THEN datetime($observedAt) ELSE u.lastSeen END;
~~~

This example keeps **one aggregated edge** per Account–Device pair, recording `firstSeen`/`lastSeen`. If you need exact login counts, add **DeviceObservation** nodes keyed by `eventId` rather than incrementing counters inside a retryable callback. Never treat this aggregated edge as proof that two accounts were active **at the exact same time**.

Create related nodes and edges inside a **single transaction** when an event requires atomic consistency. In the Java Driver, **executeWrite** may retry the callback on transient errors: logic must be idempotent and must not trigger external payment/email calls inside the callback.

### 4.3. Late-Arriving Data and Event Time

Do not use **ingestion-time `datetime()`** as the transaction timestamp when upstream provides a reliable **occurredAt**. A transfer occurring at 09:00 but ingested at 12:00 must sit in its true chronological position in the A → B → C chain.

Your design should include:

- Non-duplicate **eventId/transferId**.
- Separation of **occurredAt** and **ingestedAt**.
- **Event versions** or correction events if data can be amended.
- **Watermarks** for windowed aggregations matching upstream latency.
- **Replay mechanisms** that do not create duplicate nodes/edges or double risk scores.

If a transaction is only **PENDING**, whether it counts toward "transferred funds" must be explicitly defined. The examples below mainly examine **status = 'SETTLED'**.

## 5. Detecting Accounts Sharing a Device

### 5.1. Finding Account Pairs with Shared Devices

~~~cypher
MATCH (a:DemoFraudAccount {tenantId: $tenantId})
      -[:DEMO_FR_USED_DEVICE]->
      (d:DemoFraudDevice {tenantId: $tenantId})
      <-[:DEMO_FR_USED_DEVICE]-
      (b:DemoFraudAccount {tenantId: $tenantId})
WHERE a.accountId < b.accountId
WITH a, b,
     count(DISTINCT d) AS sharedDeviceCount,
     collect(DISTINCT d.deviceKey) AS sharedDevices
RETURN a.accountId AS accountA,
       b.accountId AS accountB,
       sharedDeviceCount,
       sharedDevices
ORDER BY sharedDeviceCount DESC, accountA, accountB;
~~~

Set **$tenantId = 'bank-a'**. Results include the pairs:

| accountA | accountB | sharedDevices |
|---|---|---|
| A-100 | A-200 | D-SHARED |
| A-100 | A-900 | D-SHARED |
| A-200 | A-900 | D-SHARED |
| A-300 | A-400 | D-PUBLIC |
| A-300 | A-500 | D-PUBLIC |
| A-400 | A-500 | D-PUBLIC |

The condition **a.accountId < b.accountId** avoids emitting both **(A,B)** and **(B,A)** as well as self-pairs **(A,A)**. Because both accounts are already scoped to one tenant, lexicographical comparison of `accountId` within that scope is valid. Real graphs may have multiple device types and multiple edges from the same source: **count(DISTINCT d)** prevents double-counting devices when an account has multiple observation records.

**Pitfall:** the query detects *connections*, not fraud verdicts. The three pairs in the **D-PUBLIC** group may be completely legitimate.

### 5.2. Measuring How "Popular" a Device Is

~~~cypher
MATCH (d:DemoFraudDevice {tenantId: $tenantId})
      <-[:DEMO_FR_USED_DEVICE]-
      (a:DemoFraudAccount {tenantId: $tenantId})
WITH d, count(DISTINCT a) AS accountCount
RETURN d.deviceKey AS deviceKey,
       d.isPublic AS isPublic,
       accountCount
ORDER BY accountCount DESC, deviceKey;
~~~

In **bank-a**, both **D-SHARED** and **D-PUBLIC** have **3 Accounts**, while **D-PRIVATE** and **D-OTHER** have **1**. A naive rule saying "a device with 3+ accounts is fraud" would **conflate** the group needing review with the public terminal group.

**How to improve:** incorporate device metadata (**isPublic**, device type, ID provider, confidence), account-switching frequency, concurrent activity, anomalous verification counts, and confirmed fraud rate. For high-degree hubs such as corporate NAT IPs, airports, or public Wi-Fi, **down-weight, exclude from certain models, or apply context-aware thresholds**.

### 5.3. Considering Only Observations Within a Time Window

~~~cypher
MATCH (a:DemoFraudAccount {tenantId: $tenantId})
      -[u1:DEMO_FR_USED_DEVICE]->
      (d:DemoFraudDevice {tenantId: $tenantId})
      <-[u2:DEMO_FR_USED_DEVICE]-
      (b:DemoFraudAccount {tenantId: $tenantId})
WHERE a.accountId < b.accountId
  AND u1.firstSeen <= datetime($to)
  AND u1.lastSeen >= datetime($from)
  AND u2.firstSeen <= datetime($to)
  AND u2.lastSeen >= datetime($from)
RETURN a.accountId AS accountA,
       b.accountId AS accountB,
       d.deviceKey AS deviceKey,
       u1.lastSeen AS lastSeenA,
       u2.lastSeen AS lastSeenB
ORDER BY accountA, accountB, deviceKey;
~~~

Parameters **$from** and **$to** are timezone-aware ISO-8601 strings with **from <= to**, e.g., **2026-11-20T00:00:00Z** to **2026-11-21T00:00:00Z**. These predicates only check whether **both `firstSeen`–`lastSeen` intervals overlap the window**, not whether both logins occurred in the same hour. To prove temporal overlap, use **event-level observations**.

## 6. Finding Links to Confirmed Fraud Accounts

In the fixture, **A-900** in `bank-a` has the synthetic label **confirmedFraud = true**. An investigative rule might inspect which accounts share a **non-public device** with A-900.

~~~cypher
MATCH (a:DemoFraudAccount {tenantId: $tenantId})
      -[:DEMO_FR_USED_DEVICE]->
      (d:DemoFraudDevice {tenantId: $tenantId})
      <-[:DEMO_FR_USED_DEVICE]-
      (known:DemoFraudAccount {tenantId: $tenantId})
WHERE known.confirmedFraud = true
  AND a <> known
  AND d.isPublic = false
RETURN a.accountId AS accountToReview,
       known.accountId AS confirmedAccount,
       collect(DISTINCT d.deviceKey) AS connectingDevices
ORDER BY accountToReview;
~~~

For **bank-a**, the result is:

~~~text
A-100  A-900  ["D-SHARED"]
A-200  A-900  ["D-SHARED"]
~~~

**Proper interpretation:** A-100 and A-200 are linked via a device to a verified account. This is a **reason for further review**, not a conclusion about the account owner's intent or culpability.

### 6.1. Connection Paths Do Not Imply Causality

The path:

~~~text
A-100 -> D-SHARED <- A-900
~~~

shows that two accounts were observed on the same `deviceKey`. It **does not** prove that A-100 controls A-900, that their money transfers are related, or that both accounts used the device at the same time.

Better risk assessment requires multiple independent signal groups: authentication data, account-holder verification, transaction behavior, history, and account-takeover indicators. Avoid double-counting evidence: **a single login** must not be counted as three independent signals merely because it appears in three tables/relationships.

### 6.2. Deep Links Must Be Bounded

An overly broad query traversing dozens of hops across all **Account/Device/Transfer** nodes easily causes **graph explosion**: one public IP can connect millions of accounts. In online investigation queries, start with **1–2 well-defined hops** before expanding conditionally.

Never use **shortestPath()** to claim a "lowest-risk path": Cypher's shortest path minimizes **hop count**, not trust weights. If weighted path algorithms are needed, define per-edge costs and use an appropriate method (such as GDS) before interpreting results.

## 7. Tracing Transfer Chains Through Intermediary Accounts

### 7.1. Direct Transfers to a Confirmed Account

~~~cypher
MATCH (src:DemoFraudAccount {tenantId: $tenantId})
      -[:DEMO_FR_SENT]->
      (t:DemoFraudTransfer {tenantId: $tenantId})
      -[:DEMO_FR_TO]->
      (dest:DemoFraudAccount {tenantId: $tenantId})
WHERE dest.confirmedFraud = true
  AND t.status = 'SETTLED'
RETURN src.accountId AS sender,
       dest.accountId AS recipient,
       t.transferId AS transferId,
       t.amountMinor AS amountMinor,
       t.occurredAt AS occurredAt
ORDER BY occurredAt;
~~~

In **bank-a**, there are **T-102** and **T-105**, both from **A-200** to **A-900**. This is a **money-flow signal**, distinct from shared-device links.

### 7.2. Two-Hop Transfers A → B → C in Time Order

~~~cypher
MATCH (src:DemoFraudAccount {
        tenantId: $tenantId, accountId: $sourceId
      })
      -[:DEMO_FR_SENT]->(t1:DemoFraudTransfer)
      -[:DEMO_FR_TO]->(mid:DemoFraudAccount)
      -[:DEMO_FR_SENT]->(t2:DemoFraudTransfer)
      -[:DEMO_FR_TO]->(dest:DemoFraudAccount {
        tenantId: $tenantId
      })
WHERE dest.confirmedFraud = true
  AND mid.tenantId = $tenantId
  AND t1.tenantId = $tenantId
  AND t2.tenantId = $tenantId
  AND t1.status = 'SETTLED'
  AND t2.status = 'SETTLED'
  AND t1.occurredAt < t2.occurredAt
  AND t2.occurredAt <= t1.occurredAt + duration({hours: 24})
RETURN src.accountId AS source,
       mid.accountId AS intermediary,
       dest.accountId AS destination,
       t1.transferId AS firstTransfer,
       t2.transferId AS secondTransfer,
       t1.occurredAt AS firstAt,
       t2.occurredAt AS secondAt
ORDER BY firstAt, secondAt;
~~~

Set **$tenantId = 'bank-a'** and **$sourceId = 'A-100'**. The output contains two chains:

~~~text
A-100 -> T-101 -> A-200 -> T-102 -> A-900
A-100 -> T-101 -> A-200 -> T-105 -> A-900
~~~

Both chains share **the same T-101**, so they must not be counted as **two independent transfers from A-100** to A-200. They are merely **two path combinations** traversing two different outgoing transfers from A-200.

In anti-money-laundering workflows, this pattern **does not yet prove** that funds from T-101 funded T-102/T-105. You still need detailed fund tracing, balances, timing, channels, and business rules. "A path exists" only supplies an investigative hypothesis.

### 7.3. Detecting Repeated Transfers Within a Window

~~~cypher
MATCH (src:DemoFraudAccount {tenantId: $tenantId})
      -[:DEMO_FR_SENT]->
      (t:DemoFraudTransfer {tenantId: $tenantId})
      -[:DEMO_FR_TO]->
      (dest:DemoFraudAccount {tenantId: $tenantId})
WHERE t.status = 'SETTLED'
  AND t.occurredAt >= datetime($from)
  AND t.occurredAt < datetime($to)
WITH DISTINCT src, dest, t
WITH src, dest,
     count(t) AS transferCount,
     sum(t.amountMinor) AS totalAmountMinor,
     collect(t.transferId) AS transferIds
WHERE transferCount >= $minTransfers
RETURN src.accountId AS sender,
       dest.accountId AS receiver,
       transferCount,
       totalAmountMinor,
       transferIds
ORDER BY transferCount DESC, sender, receiver;
~~~

For **bank-a**, window **2026-11-20T00:00:00Z → 2026-11-21T00:00:00Z**, and **minTransfers = 2**, the result is A-200 → A-900: **2 transfers**, total **800000** minor units, IDs **T-102, T-105**.

**Note:** summing amounts is only meaningful when all transactions share the same currency and valid status; the fixture omits currency so it only demonstrates the summation pattern. In multi-currency systems, group by currency or convert using audited exchange rates and timestamps.

**Why `WITH DISTINCT src, dest, t` before `SUM`?** If anomalous data has multiple `SENT`/`TO` edges for the same Transfer, `MATCH` can produce duplicate rows for a single transaction. Using `count(DISTINCT t)` while still doing `sum(t.amountMinor)` would inflate the total amount. Deduplicating on the **(source, destination, Transfer)** tuple before `SUM` keeps pair aggregations semantically consistent; the system should still detect and repair invariant-violating graph data.

## 8. Combining Signals into an Investigation Priority Score

### 8.1. From Signals to Explainable Features

An investigation output is useful when it returns **reasons**:

| Feature | Meaning | Expected Value in Fixture |
|---|---|---|
| **knownFraudSharedDeviceNeighbors** | Number of confirmed-risk accounts sharing a **non-public device** | A-100 = 1; A-200 = 1 |
| **transfersToConfirmedCount** | Number of direct SETTLED transfers to confirmed accounts in window | A-200 = 2; A-100 = 0 |
| **sharedDeviceDegree** | How many accounts use a given device | D-SHARED = 3; D-PUBLIC = 3 |
| **twoStepTransferPaths** | Number of two-hop transfer chains in window | A-100 to A-900 has 2 example paths |
| **recentAccountAge / newDevice** | Did the account/device appear recently? | Insufficient data in fixture |

**Features are not verdicts.** A variable can carry strong signal in one product segment and weak signal in another. Only use features with precise definitions of window, source data, reliability, lag, and deduplication.

### 8.2. Building an Illustrative Score from Two Independent Signals

For example, assign **40 points** when at least one confirmed fraud account shares a non-public device, and **30 points** when there is at least one direct transfer to that account during the day. Scores fall in **0–70** because there are only two signals; this is **not a fraud probability**.

~~~cypher
MATCH (a:DemoFraudAccount {tenantId: $tenantId})
WHERE a.confirmedFraud = false
CALL (a) {
  MATCH (a)-[:DEMO_FR_USED_DEVICE]->(d:DemoFraudDevice)
        <-[:DEMO_FR_USED_DEVICE]-(known:DemoFraudAccount)
  WHERE d.tenantId = a.tenantId
    AND d.isPublic = false
    AND known.tenantId = a.tenantId
    AND known.confirmedFraud = true
    AND known <> a
  RETURN count(DISTINCT known) AS knownNeighbors
}
CALL (a) {
  MATCH (a)-[:DEMO_FR_SENT]->(t:DemoFraudTransfer)
        -[:DEMO_FR_TO]->(known:DemoFraudAccount)
  WHERE t.tenantId = a.tenantId
    AND known.tenantId = a.tenantId
    AND known.confirmedFraud = true
    AND t.status = 'SETTLED'
    AND t.occurredAt >= datetime($from)
    AND t.occurredAt < datetime($to)
  RETURN count(DISTINCT t) AS transfersToKnown
}
WITH a, knownNeighbors, transfersToKnown,
     (CASE WHEN knownNeighbors > 0 THEN 40 ELSE 0 END) +
     (CASE WHEN transfersToKnown > 0 THEN 30 ELSE 0 END)
       AS reviewScore
RETURN a.accountId AS accountId,
       knownNeighbors,
       transfersToKnown,
       reviewScore
ORDER BY reviewScore DESC, accountId;
~~~

**Version note:** the **CALL (a) { ... }** variable scope clause is supported starting in **Neo4j 5.23**; on older versions, use an importing **WITH a** inside the subquery per that version's syntax, though the older style is deprecated in modern releases.

For tenant **bank-a** and the Nov 20, 2026 window:

| Account | knownNeighbors | transfersToKnown | reviewScore |
|---|---:|---:|---:|
| **A-200** | 1 | 2 | **70** |
| **A-100** | 1 | 0 | **40** |
| A-300 | 0 | 0 | 0 |
| A-400 | 0 | 0 | 0 |
| A-500 | 0 | 0 | 0 |

**Exclude A-900 from the unverified-account scoring table** because it is already a confirmed label in the fixture. **Do not** interpret a score of 70 as a 70% fraud probability. Weights 40/30 are teaching rules, not empirically calibrated and carrying no statistical meaning.

### 8.3. Why Separate Subqueries?

Joining multiple devices, multiple transfers, and multiple destination accounts inside a single `MATCH` causes Cartesian row multiplication: **3 devices × 5 transfers** creates 15 rows even though there are only 3 and 5 distinct events. Counting or summing directly after that join easily **inflates features**.

Two **CALL (a)** subqueries compute each evidence group independently with **count(DISTINCT ...)**, then merge results per account. This controls row explosion and keeps score provenance clear.

For very large datasets, consider computing features in windowed pipelines instead of querying all relationships per request. However, caching features requires **TTL, versioning, freshness tracking, and reproducibility checks**.

## 9. Extending with Graph Data Science: Components and Similarity

**Neo4j Graph Data Science (GDS)** is an algorithm library that must be separately installed/licensed (or supported by your environment). It is not a built-in feature of core Cypher across all deployments.

### 9.1. Weakly Connected Components (WCC) to Find Linked Clusters

In an Account–Device network, **WCC** finds groups of nodes reachable from one another when **ignoring edge direction**. It answers "which accounts belong to the same device-linked cluster?", but **does not** conclude that the cluster is a fraud ring.

Example projecting a graph containing only Accounts, Devices, and `USED_DEVICE` relationships:

~~~cypher
CALL gds.graph.project(
  'demoFraudSignals',
  ['DemoFraudAccount', 'DemoFraudDevice'],
  {
    DEMO_FR_USED_DEVICE: {
      orientation: 'UNDIRECTED'
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Because `UNDIRECTED` loads both directions, the projected relationship count can be double the original Neo4j edge count. The sample dataset has **12 nodes** across those two labels and **9 `USED_DEVICE` edges in the database**; do not assume the projected relationship count is always 9.

Run WCC:

~~~cypher
CALL gds.wcc.stream('demoFraudSignals')
YIELD nodeId, componentId
WITH componentId, gds.util.asNode(nodeId) AS n
WHERE n:DemoFraudAccount
  AND n.tenantId = 'bank-a'
RETURN componentId,
       count(n) AS accountCount,
       collect(n.accountId) AS accountIds
ORDER BY accountCount DESC, componentId;
~~~

In tenant `bank-a`, there are two three-member account groups:

- **{A-100, A-200, A-900}**: linked through **D-SHARED**.
- **{A-300, A-400, A-500}**: linked through **D-PUBLIC**.

**componentId is a technical ID**, carries no risk classification meaning, and is not guaranteed to remain stable across projection rebuilds. The dataset also has a separate component for `bank-b`; the query above filters output to `bank-a` accounts only.

**Important:** the example projection includes both tenants because it uses a label-based native projection. Run this only in **a test environment where you are authorized over all data**. In a multi-tenant product, data must be isolated **before entering a named graph**, using separate databases, tenant-filtered Cypher projections, or an equivalent verified isolation mechanism; filtering in **RETURN** does not guarantee the analytical model isolated tenant data.

### 9.2. Node Similarity: Similar Accounts by Device Neighborhood

**Node Similarity** compares two accounts based on their sets of linked devices. For example, given device sets:

\[
D(A\!-\!100)=\{D\!-\!SHARED,D\!-\!PRIVATE\},
\quad D(A\!-\!200)=\{D\!-\!SHARED\}
\]

Jaccard similarity:

\[
J(A,B)=\frac{|D(A)\cap D(B)|}{|D(A)\cup D(B)|}
\]

Accordingly, **J(A-100, A-200) = 1/2 = 0.5**, while **J(A-200, A-900) = 1** because both only have `D-SHARED` in the fixture. Likewise, the three accounts using **D-PUBLIC** would also score high similarity without implying fraud.

GDS documentation supports **gds.nodeSimilarity.stream** with metrics such as **JACCARD**, **OVERLAP**, **COSINE** and parameters **topK**, **similarityCutoff**, **upperDegreeCutoff**. To compare **the set of devices each account connects to**, the projection should keep the **Account → Device direction** and restrict compared nodes to Accounts; do not reuse an **UNDIRECTED** projection built for WCC and assume similarity results have the same semantics.

On large graphs, Node Similarity can be memory- and compute-intensive. Check memory estimation, filter tenants before projection, exclude or down-weight public hubs, and set an appropriate `topK`. A similarity score measures **structural similarity**, not probability of common ownership or a legal finding.

### 9.3. Dropping the Named Graph After the Exercise

~~~cypher
CALL gds.graph.drop('demoFraudSignals')
YIELD graphName
RETURN graphName;
~~~

This **removes the in-memory GDS projection**; it does not delete underlying nodes or relationships in the database. In production applications, named graphs require a lifecycle/refresh policy because they **do not automatically synchronize** as new accounts or transfers are written to the database.

## 10. Controlling False Positives and Signal Integrity

### 10.1. Reasons a Connection Is Not Suspicious

| Scenario | Easy Misinterpretation | How to Reduce Noise |
|---|---|---|
| **Public terminal/device** | Dozens of accounts share a `deviceKey` | `isPublic` metadata, device degree cutoffs, segment-specific policies |
| **Shared NAT / Wi-Fi** | Many accounts share one IP | Do not treat IP as a personal device identifier |
| **Family / corporate** | Multiple legitimate users share a machine | Historical analysis, verified owner context, step-up verification |
| **Reset / recycled device** | A device token appears on another person | TTL, `firstSeen`/`lastSeen`, ID provenance |
| **Account takeover (ATO)** | Fraud link does not mean the account owner is at fault | Account takeover workflows and user recovery support |
| **Refund / chargeback** | A Transfer looks like new money flow | Meaningful status and transaction type filtering |
| **Two graph paths sharing one event** | Counted as multiple independent proofs | `count(DISTINCT transferId/eventId)`, source deduplication |
| **Stale data** | A fraud label was overturned but features still retain it | Versioning, refreshes, correction workflows, and TTL |

**Never treat hop count or device count as a standalone "risk score"** without statistical grounding. Many edges can stem from a single benign cause (a community terminal), while a short path to a fraud account can happen by coincidence.

### 10.2. Avoiding Leakage in Offline Training or Evaluation

If a model is evaluated as of **Nov 20**, **confirmedFraud** labels only verified on **Nov 25** must not be used as features known on the 20th. Doing so causes **temporal leakage**: evaluation metrics look great offline but fail to reproduce in production.

Record:

- **Event occurrence time** and **system ingestion time**.
- **Fraud label verification timestamp**, source, and mutable state.
- Graph snapshot/version, feature definitions, and evaluation data window.
- Train/validation/test splits partitioned by **time and entity**, avoiding cross-entity/cluster leakage across splits.

In operations, never overwrite a fraud label "back in time" and evaluate as if it were known beforehand.

### 10.3. Measuring Precision, Recall, and Investigation Load

For alerts requiring human review:

\[
\text{Precision}=\frac{TP}{TP+FP},\qquad
\text{Recall}=\frac{TP}{TP+FN}
\]

Here TP/FP/FN are only meaningful when you have **sufficiently reliable ground truth**, including clear rules for confirming real fraud. The set of "accounts ever reviewed by investigators" is **not necessarily** the set of confirmed fraud.

Besides precision/recall, track:

- **Alert volume** per day/tenant and duplicate-alert rate.
- **False-positive rate** across segments with valid ground truth.
- **Time from event to detection**, investigation handling time, and case outcomes.
- **Data freshness**, missing event counts, and label correction frequency.
- **Analyst override rate**, appeal/correction rate, and impact on legitimate users.

The goal is not maximizing flagged accounts, but **directing investigative capacity toward well-evidenced cases while minimizing harm from false alarms**.

## 11. Security and Governance of Linked Data

Attributes covering accounts, devices, and money flows are highly sensitive. Graphs amplify inference capabilities about users, so you must constrain **stored data**, **query depth**, and **result access**.

### 11.1. Data Minimization

- Use **pseudonymous IDs / `deviceKey`** instead of raw hardware identifiers whenever possible.
- Never store passwords, access tokens, full payment card data, or biometrics inside the investigation graph.
- Treat **IPs and device fingerprints** as noisy signals, not absolute proof of identity.
- Design retention aligned with processing purpose; define data deletion/rectification and propagation to caches/projections.
- Log **basis, purpose, access rights, and audit trails** for anyone viewing cases.

**Hashing does not automatically anonymize data**: low-entropy originals can be guessed; deterministic tokens that link across sources still carry re-identification risk. Protect keys/salts, permissions, and sharing boundaries under security policy.

### 11.2. Enforcing Tenant Isolation at Every Step

Checking **WHERE a.tenantId = ...** only in the final clause is insufficient if earlier clauses pulled another tenant's data into a shared computation. In multi-tenant systems:

1. Constraints use appropriate tenant keys.
2. Account–Device and Account–Transfer–Account links must be **verified same-tenant** or governed by approved cross-tenant rules.
3. Cypher queries are parameterized and scoped by tenant **at entry points and across expansions**.
4. GDS projections and feature computations must be isolated **before computing**, not just at display time.
5. Roles follow least privilege; investigators can only view datasets belonging to assigned cases.

A particularly dangerous bug is keying Device nodes by a global **deviceKey** when policy requires tenant scoping. Two organizations sharing the same `deviceKey` string could then be joined together, producing false conclusions.

### 11.3. Human Rights and Accountability for Explanations

Graph signals should output an **evidence list**: which device, when, which transfer, which path, why they were linked, and whether data is missing. High-impact actions such as **freezing accounts, denying service, or reporting misconduct** require proper business/legal workflows, impact assessments, and appeal mechanisms.

**Never use sensitive attributes or discriminatory proxies** as unfounded features. Monitor fairness, false-positive disparities, and consistency across user groups using data-protection-compliant methods.

## 12. Deployment Architecture: Event-Driven and Batch Detection

### 12.1. Recommended Processing Flow

~~~mermaid
flowchart LR
  E["Transaction/Login events"] --> V["Validate + normalize + deduplicate"]
  V --> G["Neo4j: Account/Device/Transfer"]
  G --> C["Cypher features / GDS batch"]
  C --> R["Rules / scoring / ranking"]
  R --> Q["Case review queue"]
  Q --> H["Human review + outcomes"]
  H --> F["Feedback, audit, and model monitoring"]
~~~

**The transaction path** and **the detection path** should have clear failure boundaries: a successful payment request must not assume alerting graph writes have completed if consumers lag. When using a message queue, track **eventId**, processing state, retries, and lag monitoring so you know how far behind the graph is.

### 12.2. Two Computation Modes

| Mode | Best For | Points to Watch |
|---|---|---|
| **Online Cypher** | Current-account checks, device sharing, 1–2 hop queries | Requires indexes, time/depth bounds, and fan-out safeguards |
| **Batch graph analytics / GDS** | Connected components, similarity, network-wide features | Needs projection memory, data can be stale, periodic refresh needed |
| **Hybrid** | Fast rule checks enriched with batch features | Must track feature timestamp/version and fallback when features are missing |

GDS is not required for every API request. A simple rule like "which accounts share a non-public device with a confirmed account?" runs cleanly in fixed-depth Cypher with proper indexes. GDS pays off when problems shift to **network-wide analytics** with measured resource budgets.

### 12.3. Java Driver: Reading Parameterized Signals

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public final class FraudSignalQueries {

    public record SharedDeviceEvidence(
            String otherAccountId, String deviceKey) {}

    public static List<SharedDeviceEvidence> findAccountsSharingDevices(
            Driver driver,
            String database,
            String tenantId,
            String accountId) {

        try (var session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> tx.run("""
                MATCH (a:DemoFraudAccount {
                  tenantId: $tenantId, accountId: $accountId
                })-[:DEMO_FR_USED_DEVICE]->
                (d:DemoFraudDevice {tenantId: $tenantId})
                <-[:DEMO_FR_USED_DEVICE]-
                (other:DemoFraudAccount {tenantId: $tenantId})
                WHERE other <> a
                  AND d.isPublic = false
                RETURN DISTINCT other.accountId AS otherAccountId,
                       d.deviceKey AS deviceKey
                ORDER BY otherAccountId, deviceKey
                LIMIT 100
                """, Map.of(
                    "tenantId", tenantId,
                    "accountId", accountId
                )).list(row -> new SharedDeviceEvidence(
                    row.get("otherAccountId").asString(),
                    row.get("deviceKey").asString()
                )));
        }
    }
}
~~~

On the fixture, calling **findAccountsSharingDevices(driver, "neo4j", "bank-a", "A-100")** returns **A-200** and **A-900** via `D-SHARED`, without leaking `bank-b`. **LIMIT 100** caps returned records, but **does not guarantee low traversal cost before `LIMIT`** if a hub generates many paths: profile and implement filtering/degree cutoffs.

Keep a single shared **Driver** per application; create/close **Session** per unit of work and never share across threads concurrently. Never concatenate client-supplied **tenantId/accountId** into Cypher strings; pass parameters as shown. Configure timeouts, connection pools, read privileges, and fallback behavior when the graph/feature service is temporarily unavailable.

### 12.4. Spring Data Neo4j and Event Mapping

With Spring Data Neo4j, distinguish:

- **@Node** for Account, Device, and Transfer.
- **@Relationship** for `USED_DEVICE`, `SENT`, and `TO`, preserving link direction.
- **Business IDs** and uniqueness constraints differ from internal framework IDs.
- **@Transactional** can wrap creating a Transfer + endpoint links in one transaction when configured properly.
- Complex queries counting paths, computing risk scores, or calling GDS are better suited to **Neo4jClient/custom Cypher** than forcing every analytics query through entity mapping.

Avoid loading an entire subgraph into Java objects just to count a few features; dense relationships can cause huge queries and heap pressure. Return **aggregated result DTOs** and load detailed evidence paths only when an investigator opens a case.

## 13. Optimizing Queries on Large Graphs

### 13.1. Starting from Selectively Keyed Nodes

~~~cypher
EXPLAIN
MATCH (a:DemoFraudAccount {
  tenantId: $tenantId,
  accountId: $accountId
})-[:DEMO_FR_USED_DEVICE]->(d:DemoFraudDevice)
RETURN d.deviceKey AS deviceKey;
~~~

With the composite uniqueness constraint on Account, the planner can use an **index seek** to locate the source node before expanding to devices. Inspect **EXPLAIN** on test data and **PROFILE** on safe read queries to compare **Rows**, **DB Hits**, and actual fan-out width.

**EXPLAIN does not execute the query**, whereas **PROFILE does**; never run `PROFILE` on production `CREATE`/`MERGE` statements if you only want to inspect the plan.

### 13.2. Bounding Hops, Windows, and Hubs

- Anchor with constrained **tenantId + accountId** or **transferId**.
- Traverse **explicit relationship types**; never use unbounded **[*1..]** on production graphs.
- Distinguish **public/NAT devices** from high-confidence personal devices with dedicated cutoff rules.
- Bound **occurredAt windows** when tracing money flows and exclude irrelevant transaction statuses.
- Use **DISTINCT** on entity/event IDs when one event creates multiple paths.
- Estimate GDS projection query cost and refresh cost before exposing features in an API.
- Enforce **timeouts**, pagination, and investigative query quotas so core transaction traffic is unaffected.

Note that **Account–Device** relationships can reach huge degrees. A device linked to \(n\) accounts creates roughly \(n(n-1)/2\) **unordered account pairs**: for 10,000 accounts, that is **49,995,000 pairs**. Systems must detect hubs and handle them specially rather than dumping all pairs to a dashboard.

### 13.3. Indexes for Time-Range Queries

If queries frequently fetch many Transfers within a tenant over an **occurredAt** range, consider a matching range index:

~~~cypher
CREATE RANGE INDEX demo_fraud_transfer_time IF NOT EXISTS
FOR (t:DemoFraudTransfer)
ON (t.tenantId, t.occurredAt);
~~~

An index does not replace the **transferId** constraint, nor does it guarantee every query will use the time index. Check **SHOW INDEXES** (must be `ONLINE`), **EXPLAIN/PROFILE**, selectivity, and write frequency. Extra indexes increase write overhead and disk usage, so only add them based on workload evidence.

### 13.4. Projections and Feature Caches Can Go Stale

A GDS named graph **does not auto-update** after Cypher transactions in the database. If an account uses a new device after projection time, WCC on the stale graph will not see that link. You must define:

- Projection creation/refresh cadence.
- Feature computation timestamps and versions.
- Data window / retention limits.
- Behavior when features are missing or stale.
- How to audit features against the data actually available at decision time.

## 14. Testing Correctness and Preventing False Alerts

### 14.1. Fixture Assertions

After creating the sample data:

~~~cypher
MATCH (a:DemoFraudAccount)
RETURN count(a) AS accounts;
~~~

~~~cypher
MATCH (d:DemoFraudDevice)
RETURN count(d) AS devices;
~~~

~~~cypher
MATCH (t:DemoFraudTransfer)
RETURN count(t) AS transfers;
~~~

Expect **7, 5, 5**. Verify the edges as well:

~~~cypher
MATCH ()-[u:DEMO_FR_USED_DEVICE]->()
RETURN count(u) AS usageLinks;
~~~

~~~cypher
MATCH ()-[s:DEMO_FR_SENT]->()
RETURN count(s) AS sendLinks;
~~~

~~~cypher
MATCH ()-[r:DEMO_FR_TO]->()
RETURN count(r) AS receiveLinks;
~~~

Expect **9, 5, 5**. Counts are only part of testing: matching counts can still hide **cross-tenant leaks or wrong endpoints**.

### 14.2. Checking Tenant and Endpoint Invariants

~~~cypher
MATCH (a:DemoFraudAccount)-[:DEMO_FR_USED_DEVICE]->
      (d:DemoFraudDevice)
WHERE a.tenantId IS NULL
   OR d.tenantId IS NULL
   OR a.tenantId <> d.tenantId
RETURN a.accountId AS accountId, d.deviceKey AS deviceKey;
~~~

~~~cypher
MATCH (src:DemoFraudAccount)-[:DEMO_FR_SENT]->
      (t:DemoFraudTransfer)-[:DEMO_FR_TO]->
      (dest:DemoFraudAccount)
WHERE src.tenantId IS NULL OR dest.tenantId IS NULL
   OR t.tenantId IS NULL
   OR src.tenantId <> t.tenantId
   OR dest.tenantId <> t.tenantId
RETURN t.transferId AS transferId,
       src.tenantId AS sourceTenant,
       dest.tenantId AS destinationTenant;
~~~

Both queries must return **0 rows**. Also verify that each Transfer has **exactly one** incoming `SENT` edge and **exactly one** outgoing `TO` edge:

~~~cypher
MATCH (t:DemoFraudTransfer)
OPTIONAL MATCH (:DemoFraudAccount)-[s:DEMO_FR_SENT]->(t)
WITH t, count(s) AS senders
OPTIONAL MATCH (t)-[r:DEMO_FR_TO]->(:DemoFraudAccount)
WITH t, senders, count(r) AS receivers
WHERE senders <> 1 OR receivers <> 1
RETURN t.transferId AS transferId, senders, receivers;
~~~

The result must be **0 rows**. This is the contract for this example; if Transfers can involve multiple parties, update the model and assertions accordingly.

### 14.3. Test Cases Required Before Production

| Test Case | Expected Outcome |
|---|---|
| Two accounts sharing `D-SHARED` | Detected as linked pair; not automatically labeled fraudulent |
| `D-PUBLIC` group | Structurally linked, but does **not** increment shared-with-confirmed non-public feature |
| `A-100` and `A-200` with `A-900` | Evidence points to `D-SHARED` |
| `A-200` sends `T-102` and `T-105` | **2** transfers, illustrative total 800000 |
| `A-100` through `A-200` to `A-900` | Two event paths; `T-101` is not counted as two transfers |
| `bank-b` also has `A-100` and `D-SHARED` | Never linked into `bank-a` when tenant scoping is right |
| Same `transferId` re-ingested | Does not create a second Transfer node |
| Same `transferId` with different amount | Flags conflict/correction rather than silently accepting |
| Late-arriving event | Positioned by `occurredAt`; proper watermark/correction handling |
| Adding accounts to `D-PUBLIC` | Does not flood investigators with alerts from one hub |
| `confirmedFraud` overturned | Features/cases reflect the newly effective state |
| Unrefreshed GDS graph | Output carries staleness timestamp, never masquerading as real-time |

### 14.4. Do Not Use Production Data for Examples

In tests/CI, use **synthetic data** like this fixture. If benchmarking on anonymized production data is necessary, verify PII stripping, protection of sensitive link topology, and access controls. Replacing names with fake IDs while keeping every real connection **does not guarantee anonymization**.

## 15. Operating Alerts and Investigation Workflows

### 15.1. What Should an Alert Contain?

Instead of returning only:

~~~json
{"accountId":"A-200","riskScore":70}
~~~

store reproducible evidence, for example:

~~~json
{
  "tenantId": "bank-a",
  "accountId": "A-200",
  "reviewPriorityScore": 70,
  "ruleVersion": "demo-1",
  "features": {
    "confirmedNeighborsOnNonPublicDevice": 1,
    "transfersToConfirmedInWindow": 2
  },
  "evidenceRefs": ["D-SHARED", "T-102", "T-105"],
  "needsHumanReview": true
}
~~~

This is a **sample payload**, not output from a real fraud system and not a replacement for an audit trail. With real data, evidence references require fine-grained access control and mechanisms for **corrections, retention, snapshots, and rule versioning**.

### 15.2. Review and Feedback

A standard workflow includes:

1. **Detect:** rules generate signals and evidence, not automatic verdicts.
2. **Prioritize:** rank by confidence, potential impact, and investigative capacity.
3. **Review:** analysts inspect link paths, sources, and timestamps.
4. **Decide:** decide under proper procedures with clear accountability and evidence.
5. **Feedback:** record verification outcomes, deduplicate alerts, and version features.
6. **Audit:** log all data access and every decision change.

Never use a heuristic rule from a lesson to **automatically lock real users**. Aside from false positives, attackers can deliberately forge device links to "poison the graph" and get innocent users flagged.

### 15.3. Runbook for Sudden Signal Spikes

| Symptom | Causes to Check | Action |
|---|---|---|
| Device-sharing alerts jump sharply | NAT IP mistakenly used as `deviceKey`, ingestion duplicates | Check schema/source; do not immediately assume fraud surged |
| One WCC cluster grows huge | Public device / hub degree | Analyze degrees, tenant filters, and hub filtering |
| Counts exist without evidence | Rule dropped event IDs or metadata | Restore provenance and explanation paths |
| Many Transfers missing sender/receiver | Partial ingestion, broken transaction boundaries | Check constraints, idempotent workflows, and replay |
| Risk scores shift after refresh | Stale GDS named graph / cached features | Verify versions, timestamps, and refresh schedules |
| False-positive rate climbs | Poor segment thresholds, noisy device data | Recalibrate against ground truth, monitor, and review |
| Cross-tenant results mix | Unscoped Devices, late query/projection filtering | Halt affected pipeline, isolate, and audit data access |
| API slows during graph expansion | High-degree hubs, deep traversals, missing indexes | Run read `PROFILE`, bound fan-out, and enforce budgets |

## 16. Practice Exercises

### Exercise 1 — Modeling the Domain Correctly

Design a graph for Account, Device, and Transfer with stable business keys. Explain why Transfer may need a **dedicated node** rather than a direct Account → Account relationship, and why **tenantId** must be part of the key in the fixture.

### Exercise 2 — Detecting Shared Devices

Write a Cypher query returning account pairs sharing a device in **bank-a**, without duplicating `(A,B)` and `(B,A)`. Cross-check the six pairs in Section 5; explain why **D-PUBLIC** alone should not trigger fraud alerts.

### Exercise 3 — Paths to Verified Accounts

Find `A-100` and `A-200` linked to `A-900` via **D-SHARED**, excluding **isPublic = true**. Present the gathered evidence, unknown facts, and how to store them in a review case.

### Exercise 4 — Two-Hop Transfer Chains

Rewrite the `A-100 → A-200 → A-900` query with a maximum **2-hour** window from the first transfer to the second. In the fixture, are pairs `T-101/T-102` and `T-101/T-105` still valid? Why must an initial transfer appearing in two paths not be counted twice?

### Exercise 5 — Computing Features Without Cross-Multiplication

Compare **knownNeighbors** and **transfersToKnown** for `A-100` and `A-200`. Explain why each count must be computed separately before combining them into a score, and why 70 points is not a fraud probability.

### Exercise 6 — Evaluating GDS WCC

Run the projection and WCC on the sample graph. Explain why both `bank-a` account groups have three members yet **one group uses a public device**. Propose how to filter or down-weight hubs, and identify the risk if a projection lacks tenant isolation.

### Exercise 7 — Replay and Correction

A message broker redelivers the same transferId **T-105** with an identical payload; later, it sends an amount correction event with a higher version. Design keys, transactions, idempotency, and correction policies so no second Transfer is created and conflicts are never silently masked.

### Exercise 8 — User-Safe Processes

A new account gets linked to `D-SHARED`, but the account holder reports having used a public computer. Create an investigation checklist, a way to record counter-evidence, label update procedures, and false-positive metrics. Clearly distinguish **graph signals** from **investigation conclusions**.

## 17. Summary

**Graph-based fraud detection is not merely counting who has the most links.** Neo4j's value lies in representing the **Account – Device – Transfer network**, querying shared-device patterns, intermediary money-flow paths, and connected components with verifiable evidence trails.

A reliable pipeline progresses through:

**Proper identity keys → timestamped/event-ID transaction data → constraints and idempotent ingestion → bounded relationship/path Cypher → isolated, non-cross-multiplied features → GDS where needed → transparent scoring → human review and correction.**

Mandatory principles are **isolating tenants prior to computation**, **denoising public devices/hubs**, **preventing temporal leakage**, **measuring false positives**, and **protecting personal data**. In real applications, a connection path is only an **investigative hypothesis**, never sufficient proof for assigning blame.

### Official Documentation

- [Neo4j Cypher Manual – MATCH and graph patterns](https://neo4j.com/docs/cypher-manual/current/clauses/match/)
- [Neo4j Cypher Manual – MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual – Create uniqueness constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual – CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/)
- [Neo4j Cypher Manual – EXPLAIN and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j GDS – Native graph projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
- [Neo4j GDS – Weakly Connected Components](https://neo4j.com/docs/graph-data-science/current/algorithms/wcc/)
- [Neo4j GDS – Node Similarity](https://neo4j.com/docs/graph-data-science/current/algorithms/node-similarity/)
- [Neo4j Java Driver Manual – Transactions and retries](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Bookmarks and causal consistency](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
