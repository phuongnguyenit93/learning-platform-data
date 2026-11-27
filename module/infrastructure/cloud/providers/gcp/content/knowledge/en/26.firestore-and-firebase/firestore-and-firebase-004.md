# Transactions, Batched Writes, and Update Contention in Firestore

Two customers click **Place Order** at the same moment when only one unit of a product remains. If the application reads `available=1` and then independently writes `available=0` across two separate requests, both customers may be told their order succeeded. This is a **lost update / overselling** bug caused by an unprotected read–modify–write under concurrent access.

**Cloud Firestore** provides **transactions**, **batched writes**, and **atomic field transforms** to handle different scenarios. A transaction reads state and then decides writes consistently; a batch groups multiple writes into one atomic commit; transforms like `increment()` update a field on the server without the app reading first. Picking the wrong tool can break business logic, trigger `ABORTED` under high contention, or inflate read/write costs.

This lesson belongs to the **Firestore and Firebase** chapter of module `CLOUD_PROVIDERS_GCP`, connecting data practices with IAM, VPC, Cloud Run/GKE/Compute Engine, Cloud Storage, and CI/CD. Examples use **Firestore Native mode – Core operations**, Java 21 on the server, and the Firebase Web SDK on the client. Do not assume verbatim applicability to **Firestore in Datastore mode**, **MongoDB compatibility**, or **Enterprise Pipeline operations**.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish transactions, batched writes, atomic transforms, and standalone writes.
2. Explain atomicity, commit-time consistency, retries, and transaction callback re-execution.
3. Use a Java transaction to **check inventory and write an order** without overselling.
4. Use a Firebase Web batched write when **no prior read is needed** to decide the writes.
5. Distinguish **pessimistic/optimistic** concurrency control across SDKs.
6. Identify a **hot document**, reduce contention, and design idempotency keys.
7. Distinguish server-side IAM from client-side **Firestore Security Rules** on Web/Mobile.
8. Test concurrency with the **Firebase Local Emulator Suite**, read metrics, and estimate cost.

## 1. Firestore Data and the Scope of a Single Commit

Firestore stores data in **documents** grouped into **collections**. E-commerce example:

~~~text
inventory/sku-01
  available: 1
  updatedAt: timestamp

orders/request-abc
  sku: "sku-01"
  quantity: 1
  state: "RESERVED"

profiles/user-123
  displayName: "Lan"
  updatedAt: timestamp
~~~

A document has a specific path, such as `inventory/sku-01`; concurrent writes to the same document can contend. Transactions and batched writes can modify **multiple documents** in a single atomic commit: **either all writes succeed, or none are applied**.

**Scope limit:** this atomicity covers changes within the **Firestore database**, not Cloud SQL, Pub/Sub publishing, sending emails, payment APIs, or Cloud Storage uploads. Multi-system workflows need idempotency, an outbox, or reconciliation mechanisms.

## 2. The Lost Update Bug When Reading and Writing Separately

Two requests read inventory concurrently:

~~~mermaid
sequenceDiagram
    participant A as Customer A
    participant F as Firestore
    participant B as Customer B
    A->>F: GET inventory/sku-01
    F-->>A: available = 1
    B->>F: GET inventory/sku-01
    F-->>B: available = 1
    A->>F: UPDATE available = 0
    B->>F: UPDATE available = 0
    Note over A,B: Both may create orders if code lacks protection
~~~

The alarming outcome is not that the final value is 0, but that **two orders are created for the same single unit of stock**. Whenever write decisions depend on data just read, you need a **transaction** to coordinate reads and commits. Never execute two separate `get()` and `update()` calls and call that "checking inventory."

Even `increment(-1)` is **insufficient** when business rules require `available >= 0`: the transform decrements atomically, but it does not enforce the "in stock before deducting" precondition.

## 3. Transactions: Read First, Write Later, and Auto-Retry

A Firestore transaction groups read and write operations, providing **serializable isolation at commit time**. If underlying data changes and invalidates the transaction, the SDK can **re-run the entire callback** with a fresh snapshot.

~~~mermaid
flowchart TD
    S["Start transaction"] --> R["Read orderId + inventory"]
    R --> C{"Order already exists?"}
    C -->|Yes| E["Return ALREADY_EXISTS"]
    C -->|No| K{"available >= qty?"}
    K -->|No| O["Return OUT_OF_STOCK"]
    K -->|Yes| W["Buffer update inventory + create order"]
    W --> COMMIT{"Commit valid?"}
    COMMIT -->|Yes| OK["CREATED"]
    COMMIT -->|"Contention / ABORTED"| RETRY["SDK retries callback (bounded)"]
    RETRY --> R
~~~

**Critical rules:**

- **All reads must occur before writes** inside the same transaction; do not read again inside the callback to "check whether a buffered write took effect."
- Reads inside a transaction see a consistent snapshot per Firestore semantics; **writes only take effect upon a successful commit**.
- The callback can execute **multiple times**; never send emails, process payments, publish to Pub/Sub, or mutate React state inside it.
- The SDK retries a **bounded** number of times under contention; once exhausted, it may return `ABORTED: Too much contention on these documents. Please try again.`.
- **Transactions fail when the client is offline**; Web/Mobile apps must never assume offline checkout will succeed.

### 3.1. Serializable does not mean both requests succeed

If only one unit remains and two transactions try to buy concurrently: one request commits, while the other retries, sees `available=0`, and returns `OUT_OF_STOCK`. This is the **correct outcome**, not a system failure. Distinguish out-of-stock from `ABORTED`/`DEADLINE_EXCEEDED`.

## 4. Batched Writes: Atomic Multi-Writes Without Prior Reads

A **batched write** bundles `set()`, `update()`, and `delete()` operations and commits them together. It fits when values and conditions are already known and you do not need to read current documents to decide.

~~~mermaid
flowchart LR
    UI["Firebase Web client"] --> BATCH["Batched write"]
    BATCH --> P["profiles/user-123<br/>updatedAt"]
    BATCH --> A["profiles/user-123/activity/event-01"]
    P --> ATOMIC["Single commit: all or nothing"]
    A --> ATOMIC
~~~

| Criterion | Transaction | Batched write |
| --- | --- | --- |
| Read documents inside operation | **Yes**, reads before writes | **No** |
| Write multiple documents atomically | Yes | Yes |
| Auto-rerun callback on contention | Yes, bounded SDK retries | No callback to retry |
| Check stock `available >= qty` | **Suitable** | Cannot enforce with a batch alone |
| Offline Web/Mobile device | Transaction **fails** | Can be **queued to sync when online** per SDK/config |
| Best fit | Read–check–write, cross-document invariants | Multiple predetermined writes |
| Cost | Reads + writes; retries can add reads/latency | Writes billed individually despite single commit |

**Do not confuse "atomic batch" with "conditional batch."** If two clients read `available=1` outside and both commit batches based on stale reads, the system will still oversell.

## 5. Atomic Field Transforms: Simpler When Updating a Single Field

Firestore offers server-executed field transforms:

- `increment(n)`: add/subtract numbers without a client read–modify–write cycle.
- `arrayUnion(...)` / `arrayRemove(...)`: add/remove elements per Firestore semantics.
- `serverTimestamp()`: record server-side time.

Example incrementing view count from the Web SDK:

~~~javascript
import { doc, updateDoc, increment, serverTimestamp } from "firebase/firestore";

// db is the Firestore instance initialized from the Firebase app.
await updateDoc(doc(db, "products", "sku-01"), {
  viewCount: increment(1),
  lastViewedAt: serverTimestamp()
});
~~~

This is an **atomic update on a single document**, not a workflow-checking transaction. `increment` handles concurrent additions without lost updates, but:

- It does not enforce non-negative inventory on its own.
- If **two separate business requests** are retried, it can increment twice; request/event idempotency is still needed.
- A single document still faces practical throughput limits, contention, and index/write costs.

For rapidly growing counters, consider a **sharded/distributed counter**; for non-negative inventory, use a transaction or a reservation/queue architecture enforcing invariants.

## 6. Pessimistic and Optimistic Concurrency

Firestore defines a **concurrency mode** at the database level:

| Mechanism | Behavior | Context |
| --- | --- | --- |
| **PESSIMISTIC** | Server transactions lock read documents to block conflicting writes until commit/timeout | Default in **Firestore Standard edition** |
| **OPTIMISTIC** | Does not lock documents up front; detects conflicts at commit and retries | Default in **Firestore Enterprise edition** |
| **Web/Mobile SDK** | Emulates optimistic transactions using preconditions on document versions | **Always** uses this behavior regardless of database mode |

These details apply to **Firestore Native/Core operations**. Server SDKs (Java/Go/Node.js) follow the database's concurrency control mode; **Web/Mobile SDKs always use optimistic emulation**. Never assume a Web client holds pessimistic locks just because a Standard database runs in PESSIMISTIC mode.

### 6.1. Why does application location matter?

Server SDKs using locks in PESSIMISTIC mode can make other operations wait. If Cloud Run/GKE runs **far from the Firestore database region**, network latency keeps locks held longer and increases contention. Place server workers near the database and keep callbacks short before scaling concurrency.

### 6.2. When do you get ABORTED?

When many transactions try to modify the **same document**, some wait or retry. If retries/timeouts are exhausted, the SDK returns `ABORTED`. Do not interpret every `ABORTED` as data loss; inspect **hot documents, transaction duration, client region, and concurrency load**.

## 7. Data Design for the Inventory Problem

~~~text
inventory/sku-01
  available: 2

orders/request-100
  sku: "sku-01"
  quantity: 1
  state: "RESERVED"
~~~

**Business invariants:**

1. `available >= 0` on every valid commit.
2. The same `requestId` never creates two order documents.
3. On successful commit, **deduct inventory and create the order in the same transaction**.
4. When an API call retries due to network issues, **reuse the exact same requestId**.

With `orders/{requestId}`, the callback reads the order first. If it exists and the payload matches, return `ALREADY_EXISTS`; if the same `requestId` arrives with a different payload, report an **idempotency conflict** rather than silently accepting it.

**Limitation:** a single `inventory/sku-01` document can become a **hot document** during a flash sale. Transactions guarantee correctness, **not infinite throughput**. At extreme load, use reservations/queues, partition inventory by warehouse/lot, or allocate capacity explicitly—never shard arbitrarily in ways that break inventory invariants.

## 8. Java Server SDK: Idempotent Order Transaction

Java 21 example using the **Cloud Firestore Java server client** in a lab project. Primary Maven dependency:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>libraries-bom</artifactId>
      <version>26.90.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-firestore</artifactId>
  </dependency>
</dependencies>
~~~

Place the above in a Java 21 Maven `pom.xml`; the BOM pins an illustrative version and must be updated to a production-approved version. Java uses **Application Default Credentials** in real environments, while the **Firestore Emulator** uses `FIRESTORE_EMULATOR_HOST` in the lab.

### 8.1. Runnable class example

~~~java
package lab.firestore;

import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.Map;
import java.util.Objects;

public class InventoryLab {
    public static void main(String[] args) throws Exception {
        String projectId = System.getenv("GOOGLE_CLOUD_PROJECT");
        if (projectId == null || projectId.isBlank()) {
            throw new IllegalArgumentException("Set GOOGLE_CLOUD_PROJECT");
        }
        if (args.length == 0) {
            throw new IllegalArgumentException("Use: seed | order REQUEST_ID");
        }

        try (Firestore db = FirestoreOptions.newBuilder()
                .setProjectId(projectId).build().getService()) {
            if ("seed".equals(args[0])) {
                if (System.getenv("FIRESTORE_EMULATOR_HOST") == null) {
                    throw new IllegalStateException("Seed only in emulator");
                }
                // Seed only on a clean emulator; never reset production inventory.
                db.collection("inventory").document("sku-01")
                    .set(Map.of("available", 2L)).get();
                System.out.println("Seeded available=2");
                return;
            }
            if (!"order".equals(args[0]) || args.length != 2) {
                throw new IllegalArgumentException("Use: order REQUEST_ID");
            }

            String requestId = args[1];
            if (!requestId.matches("[a-zA-Z0-9_-]{1,80}")) {
                throw new IllegalArgumentException("Invalid requestId");
            }

            DocumentReference stockRef =
                db.collection("inventory").document("sku-01");
            DocumentReference orderRef =
                db.collection("orders").document(requestId);

            String result = db.runTransaction(tx -> {
                // ALL reads must occur before any write operations.
                DocumentSnapshot order = tx.get(orderRef).get();
                DocumentSnapshot stock = tx.get(stockRef).get();

                if (order.exists()) {
                    if (!Objects.equals(order.getString("sku"), "sku-01")
                        || !Objects.equals(order.getLong("quantity"), 1L)) {
                        throw new IllegalStateException("IDEMPOTENCY_CONFLICT");
                    }
                    return "ALREADY_EXISTS";
                }

                Long available = stock.exists()
                    ? stock.getLong("available") : null;
                if (available == null) {
                    throw new IllegalStateException("MISSING_INVENTORY");
                }
                if (available < 1L) {
                    return "OUT_OF_STOCK";
                }

                tx.update(stockRef, "available", available - 1L);
                tx.create(orderRef, Map.of(
                    "sku", "sku-01",
                    "quantity", 1L,
                    "state", "RESERVED"
                ));
                return "CREATED";
            }).get();

            System.out.println("requestId=" + requestId + " result=" + result);
        }
    }
}
~~~

**Key point:** `available` and the order document commit together. When two distinct request IDs compete for the last unit, the SDK may retry, yet the outcome is strictly **one reserved, one out of stock**. When the same `requestId` is retried, the second attempt sees the existing order and does not deduct inventory again.

**Never call Pub/Sub, send emails, or charge payments inside `runTransaction(...)`**: the callback may execute multiple times. When you need to publish `OrderReserved`, write an outbox document in the same transaction and process it via an idempotent relay; Firestore event triggers can also redeliver and require deduplication.

### 8.2. What else is needed before production?

- Authenticate `requestId` from the caller and bind it to **user/tenant/payload hash**; prevent other clients from reusing IDs.
- Validate purchase eligibility, warehouse/lot stock, and pricing logic without trusting raw client inputs.
- Return distinct error codes for `OUT_OF_STOCK`, `IDEMPOTENCY_CONFLICT`, `ABORTED`, and `PERMISSION_DENIED`.
- Configure deadlines/backoff and concurrency within Cloud Run/GKE limits; never retry infinitely.
- Guard external side effects outside Firestore using an outbox/idempotency design.

## 9. Firebase Web SDK: Batched Writes When No Reads Are Needed

Example assuming the client has initialized the Firebase app and holds `db` from `getFirestore()`, `uid` from Firebase Authentication, and a stable `eventId`:

~~~javascript
import {
  doc, writeBatch, serverTimestamp
} from "firebase/firestore";

// db: Firestore instance; uid: request.auth.uid in Security Rules.
async function saveProfileAndActivity(db, uid, eventId, displayName) {
  const profileRef = doc(db, "profiles", uid);
  const activityRef = doc(db, "profiles", uid, "activity", eventId);

  const batch = writeBatch(db);
  batch.set(profileRef, {
    displayName,
    updatedAt: serverTimestamp()
  }, { merge: true });
  batch.set(activityRef, {
    type: "profile_updated",
    at: serverTimestamp()
  });
  await batch.commit();
}
~~~

**Both documents are written together or both fail.** This works when writes are known upfront and do not depend on reading current values. If you must check "does the user still have update quota?" against another document, **switch to a transaction or a controlled server endpoint**.

With Web/Mobile SDKs, batched writes **can be queued while offline and synced upon reconnection**; do not display "committed to server" when only local UI state has updated. For order placement or stock reservation, require a commit confirmation from the backend.

## 10. Firestore Security Rules vs Server IAM

There are two access paths:

| Path | Primary authorization mechanism |
| --- | --- |
| **Firebase Web/Mobile SDK** | Firebase Authentication + **Firestore Security Rules**, optionally paired with App Check |
| **Java server SDK on Cloud Run/GKE/VM** | **Google Cloud IAM** via ADC/workload identity; **bypasses Security Rules** |
| **REST/RPC server** | IAM/tokens and API scopes, not client Rules |

Sample Rules letting each user update their profile and create their own audit record, while inventory/orders can only be written by a trusted backend:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /profiles/{uid} {
      allow read: if request.auth != null && request.auth.uid == uid;
      allow create, update: if request.auth != null
        && request.auth.uid == uid
        && request.resource.data.keys().hasOnly(["displayName", "updatedAt"]);

      match /activity/{eventId} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow create: if request.auth != null
          && request.auth.uid == uid
          && request.resource.data.keys().hasOnly(["type", "at"])
          && request.resource.data.type == "profile_updated";
        allow update, delete: if false;
      }
    }
    match /inventory/{sku} {
      allow read: if request.auth != null;
      allow write: if false;
    }
    match /orders/{orderId} {
      allow read, write: if false; // Backend serves data to authorized callers.
    }
  }
}
~~~

This is an **illustrative Rules sample** that must be tested before deployment. Server SDKs using IAM **are not blocked by these allow/deny Rules**; the backend must authenticate callers, validate payloads, and enforce least-privilege IAM on its runtime service account.

### 10.1. getAfter() for cross-document invariants

In Security Rules, `getAfter(path)` reads the state **after an atomic set of operations but before commit**, letting you enforce that two documents update together. However, it is limited to **10 document-access calls per operation** and **20 per entire transaction/batch**; exceeding these can return `PERMISSION_DENIED`. Reads inside Rules can **be billed**, even if the request is denied. Never push complex business logic entirely into Rules.

## 11. Update Contention and Hot Documents

A **hot document** is written—or read inside transactions—by too many clients concurrently, such as:

~~~text
counters/global-likes
inventory/sku-flash-sale
rooms/room-001/currentSeats
~~~

This causes lock waits, retries, `ABORTED` errors, high latency, and poor throughput. Pick a mitigation matching your business invariant:

| Solution | Best fit | Notes |
| --- | --- | --- |
| `increment()` | Unconditional add/subtract under moderate load | Still gets hot at high QPS |
| **Distributed/sharded counter** | Likes/views/count aggregates | Reading totals requires summing shards or roll-ups; does not enforce stock invariants alone |
| Partition by warehouse/tenant | Independent resource pools per group | Enforce invariants per partition |
| Queue/reservation service | Flash sales, extreme inventory write contention | Requires coordination and expiry/compensation |
| Shorten transactions, colocate region | Long locks/retries from network distance or slow callbacks | Does not cure contention on a single shared key |
| Rate limiting/backpressure | Prevent requests from overwhelming capacity | Return controlled errors or retry guidance |

**Do not blindly scale up Cloud Run instances or GKE Pods** if all of them mutate `inventory/sku-flash-sale`: scaling out can actually worsen contention.

### 11.1. Are sharded counters a solution for inventory?

For instance, each page view picks a random document in `counters/{id}/shards/{shardId}` and calls `increment(1)`; the total is the sum of shards. This distributes hot writes, **but increases reads and aggregation cost**. For finite inventory that must stay non-negative, never treat shards as "independent stock buckets" without a safe allocation/reservation algorithm.

## 12. Transaction, Batch, and Bulk Operation Limits

| Limit/characteristic | What to remember |
| --- | --- |
| API request size | **10 MiB** per transaction/commit request |
| Transaction time limit | **270 seconds**, with a **60-second idle expiration** |
| Lock deadline | Locks may be released if a transaction runs too long (e.g., **20 seconds** per documentation) |
| Field transforms on a single document | Max **500 transforms** in a single Commit/transaction |
| Security Rules access calls | **10 per operation, 20 per atomic batch/transaction** |
| Large batched writes | Index updates and payload size can exceed limits |
| Bulk operations | Server **BulkWriter** or parallel writes when whole-dataset atomicity is unnecessary |

**Do not confuse "500 field transforms on a single document" with "every batch is strictly capped at 500 writes."** Practical limits also depend on request size, index fan-out, Security Rules, and edition. Large batches can be slow, and a single invalid write fails the entire batch.

To import hundreds of thousands of documents, split into manageable units. **BulkWriter/parallel writes do not create an atomic transaction across the entire dataset.**

## 13. Firestore Emulator Lab: Transactions and Contention

Use the **Firebase Local Emulator Suite** to avoid modifying real databases or incurring charges while learning.

### 13.1. Maven and emulator configuration

Requires Java 21, Maven, Node.js, Firebase CLI, and a dedicated lab directory. In `pom.xml`, alongside the dependencies from Section 8, add plugins:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.14.0</version>
      <configuration><release>21</release></configuration>
    </plugin>
    <plugin>
      <groupId>org.codehaus.mojo</groupId>
      <artifactId>exec-maven-plugin</artifactId>
      <version>3.6.4</version>
    </plugin>
  </plugins>
</build>
~~~

Create `firebase.json` in a **separate lab folder**, choosing a project ID starting with `demo-`:

~~~json
{
  "firestore": { "rules": "firestore.rules" },
  "emulators": {
    "firestore": { "port": 8080 }
  }
}
~~~

Create `firestore.rules` using the sample Rules from Section 10, then start:

~~~bash
firebase emulators:start \
  --only firestore \
  --project demo-firestore-tx
~~~

In another Java terminal:

~~~bash
export GOOGLE_CLOUD_PROJECT=demo-firestore-tx
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
~~~

**Important:** `FIRESTORE_EMULATOR_HOST` contains only `host:port`, **without `http://`**. If running Java inside a container, `127.0.0.1` is the container's loopback; point to a host address reachable by the emulator. Emulated data may be lost on shutdown unless exported/imported.

### 13.2. Run the Java lab and verify idempotency

Place `InventoryLab` in `src/main/java/lab/firestore/InventoryLab.java` of your Maven project; against a **clean** emulator:

~~~bash
mvn -q compile exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="seed"

mvn -q compile exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="order request-100"

# Resend the SAME requestId:
mvn -q compile exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="order request-100"
~~~

**Expected:** first run prints `CREATED`, second prints `ALREADY_EXISTS`; stock drops from 2 to 1 and is **not decremented again**. Inspect documents in the Emulator UI or read via SDK.

### 13.3. Competing for the last unit

Open **two terminals** and run them nearly simultaneously:

~~~bash
# Terminal A
mvn -q exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="order request-101"

# Terminal B
mvn -q exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="order request-102"
~~~

**Expected:** only one request claims the last unit; the other gets `OUT_OF_STOCK`, total valid CREATED orders is 2 (including `request-100`), and stock is 0. If the Emulator experiences too little contention to trigger a retry, that **does not prove production will never see ABORTED**.

### 13.4. Negative tests

- Try the **same requestId with a different payload**: production must report a conflict, not reuse the old record.
- Try writing `inventory/sku-01` directly from Web/Mobile SDK: Rules must reject it.
- Try writing a profile from an unauthenticated client: Rules must reject it.
- Try a profile/activity batch with valid auth: either both write or neither writes.
- Try Web/Mobile offline: transaction fails; batch can queue per SDK/config.
- Monitor `ABORTED`, retry counts, and latency during load tests in a test project.

**The Emulator does not replace staging** for verifying real throughput, multi-region latency, index performance, or production contention.

## 14. Production Delivery: Cloud Run/GKE and Idempotency

For a Java backend API:

1. Authenticate the caller before trusting `requestId`, binding it to user/tenant/payload.
2. Validate `sku`, `qty`, ownership, pricing, and reservation expiry.
3. Keep transactions short; make no external service calls inside callbacks.
4. On `OUT_OF_STOCK`, return an appropriate business error (e.g., HTTP `409 Conflict`).
5. If `ABORTED` exhausts SDK retries, return a retryable response instructing backoff with the **same requestId**.
6. If commit succeeded but the HTTP response was lost, retrying with the same ID must return **ALREADY_EXISTS**.
7. Publish events via an outbox/relay or reliable pattern; ensure consumers are idempotent too.
8. Set bounded concurrency/deadlines and SLO-based alerts.

Firestore transactions **do not guarantee exactly-once payment** in external APIs. Use payment-provider idempotency keys and an outbox/reconciliation job when no shared transaction exists.

## 15. Observability, Troubleshooting, and Cost

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| `ABORTED: Too much contention...` | Many transactions on the same document, slow callback, distant region | Find hot keys, lower concurrency, redesign data model |
| `DEADLINE_EXCEEDED` | Slow transactions/queries, network latency, or lock waits | Measure latency, indexes, and retry policies |
| `FAILED_PRECONDITION` | Invalid read/write ordering or unmet precondition | Perform all reads before writes; inspect SDK error |
| `PERMISSION_DENIED` from Web | Security Rules/auth/App Check | Inspect Rules and Emulator tests |
| `PERMISSION_DENIED` from Java server | IAM/project/database/credentials | Check ADC, runtime SA, and roles |
| Entire batch fails | One invalid write or Rules deny, request/index limit | Split batch, validate each write and Rules |
| Negative inventory | `increment(-1)` without checking invariants | Use transaction `stock >= qty` on a server endpoint |
| Duplicate orders | Unstable requestId or side effects outside DB | Stable unique ID, idempotency, and outbox |
| Writes slow down at scale | Hot document/index or distant clients | Key Visualizer/metrics, distribute load |
| Rising bill | Reads from retries, writes/indexes, Rules lookups | Billing, usage dashboard, log retries |

**Firestore costs** depend on edition/location, document reads/writes/deletes, storage/indexes, network, and add-on features. A batch of 20 writes is still billed for **20 writes**, not "one transaction = one write." Rules `get()/exists()/getAfter()` calls and retries can increase operations and latency. Cloud Billing budget alerts are **not a hard spending cap**.

Monitor Cloud Monitoring/Logging and Firestore usage: request counts, `ABORTED`/`RESOURCE_EXHAUSTED` statuses, latency, reads/writes, and index/storage growth; add application metrics for **orders created, out-of-stock, duplicates skipped, and retry counts**. For hot keys, use **Key Visualizer** where supported.

## 16. Synthesis Scenario: Limited-Stock Flash Sale

An e-commerce team has 200 units of a discounted item and 50,000 concurrent Firebase Web users. A Java backend runs on Cloud Run and stores orders in Firestore.

**Flawed design:** every client reads `inventory/flash-01` directly, updates `available`, and creates `orders/randomId`, generating a new ID on retry. Result: overselling, duplicate orders, hard-to-enforce Rules, and one overloaded hot document.

**Viable design:**

| Requirement | Solution |
| --- | --- |
| No overselling | Backend transaction reads stock and writes order in one commit |
| No duplicate orders on retry | Stable `requestId`, `orders/{requestId}` |
| Prevent clients from altering stock | Security Rules deny; least-privilege backend IAM |
| Massive flash sale | Admission control/queue/reservations, test warehouse inventory partitioning |
| Prevent duplicate events | Outbox/stable `eventId` and idempotent consumers |
| Observability | `ABORTED`, p95, business success rates, cost |
| Recovery | Bounded retries, backpressure, reconciliation |

**Decision:** transactions solve **correctness** within tolerable contention. Once a hot stock document becomes the bottleneck, you must **change the architecture/data model**, not merely add Cloud Run CPU.

## 17. Self-Check Exercises

**Question 1.** Two clients read stock `1` and separately write `0`. Why are two orders created?

*Answer:* Decisions were based on stale state; reads and writes were not atomic.

**Question 2.** When do you choose a batched write instead of a transaction?

*Answer:* When writes are predetermined, no current state needs to be read to decide them, and all-or-nothing atomicity is required.

**Question 3.** How many times can a transaction callback run?

*Answer:* Multiple times when the SDK retries on contention; never place external side effects inside the callback.

**Question 4.** Does `increment(-1)` guarantee non-negative stock?

*Answer:* No. It atomically updates a field without verifying `available >= 1`.

**Question 5.** If Standard uses pessimistic mode, do Firebase Web transactions hold locks too?

*Answer:* No. Web/Mobile always uses optimistic emulation; server SDKs follow the database concurrency mode.

**Question 6.** A batch has two documents and the second write is denied by Rules: what happens?

*Answer:* The entire batch fails to commit; there is no partial success.

**Question 7.** Why does `orders/{requestId}` prevent duplicate requests?

*Answer:* Retries of the same request share the same document ID; the transaction checks it before deducting stock.

**Question 8.** Is a Firestore transaction atomic with publishing to Pub/Sub?

*Answer:* No. Use an outbox, idempotent relay/consumer, or reconciliation.

**Question 9.** Can an offline client run a balance-checking transaction and commit when back online?

*Answer:* No. Transactions fail offline; batched writes can queue.

**Question 10.** Why does adding more Cloud Run instances increase `ABORTED` errors?

*Answer:* More concurrent transactions compete for the same hot document.

**Question 11.** Does the 500 limit mean every batch is capped at 500 writes?

*Answer:* No. The documented quota is **500 field transforms on a single document** per Commit/transaction; request size, indexes, and Rules limits also apply.

**Question 12.** Can the Java server SDK be denied by Firestore Security Rules?

*Answer:* No. Server SDKs use IAM; Rules govern Web/Mobile clients.

**Question 13.** If you already use a transaction, why do you still need an idempotency key?

*Answer:* An HTTP request can be retried if the commit succeeded but the HTTP response was lost.

**Question 14.** Can a sharded counter be used for a very hot likes counter?

*Answer:* Yes; it distributes writes, though reading totals costs more, and it does not replace stock transactions.

## 18. Pre-Production Checklist

- [ ] Distinguished read-dependent writes (**transaction**) from predetermined writes (**batch**).
- [ ] Transaction reads precede writes; callbacks contain no external side effects.
- [ ] SDK retries are bounded; app handles `ABORTED`, timeouts, and business errors separately.
- [ ] Stock/quota/order uniqueness protected by transactions and stable IDs.
- [ ] Concurrency and hot documents controlled; load-tested under realistic traffic distributions.
- [ ] Atomic transforms used only when complex business preconditions are not needed.
- [ ] Web/Mobile Security Rules covered by tests; server SDK uses least-privilege IAM.
- [ ] Transactions/batches stay within request size, duration, transforms, and Rules access limits.
- [ ] Offline behavior handled clearly: batches can queue, transactions fail offline.
- [ ] Never open Rules to full public access for a "quick test" in production.
- [ ] HTTP, Pub/Sub, and event-trigger retries are idempotent.
- [ ] Monitored `ABORTED`, latency, duplicates skipped, reads/writes, and Billing.
- [ ] Data location, backups/PITR, index growth, and budgets reviewed.
- [ ] Tested identical `requestId`, concurrent distinct requests, last-unit stock, and backend crashes.

## 19. Conclusion

**Transactions** protect read–check–write decisions; **batched writes** bundle atomic writes when no reads are required; **atomic transforms** handle simple server-side field updates. None of these tools automatically span Pub/Sub/Cloud SQL/payments or eliminate single-document contention limits.

For Java/Firebase, the reliable pattern is **authenticate → check invariants in a transaction → commit with a stable requestId → handle retries idempotently → monitor contention and cost**. When a hot document becomes the bottleneck, **redesign the data model/coordination**, not just the instance count.

## Official References

- [Firestore transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions)
- [Transaction contention and concurrency modes](https://firebase.google.com/docs/firestore/transaction-data-contention)
- [Firestore best practices](https://firebase.google.com/docs/firestore/best-practices)
- [Firestore quotas and limits](https://firebase.google.com/docs/firestore/quotas)
- [Firestore Security Rules conditions/getAfter](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [Firebase Local Emulator Suite](https://firebase.google.com/docs/emulator-suite/connect_firestore)
- [Distributed counters](https://firebase.google.com/docs/firestore/solutions/counters)
- [Firestore offline persistence](https://firebase.google.com/docs/firestore/manage-data/enable-offline)
- [Java Firestore transaction sample](https://cloud.google.com/firestore/docs/samples/firestore-transaction-document-update)
- [Firestore pricing](https://firebase.google.com/docs/firestore/pricing)
