# Realtime Listeners and Application Data Synchronization

A learner opens a Java learning app on their phone, marks a lesson as completed, and then switches to their laptop. They expect the status to appear almost immediately on both devices, even over flaky networks. **Cloud Firestore realtime listeners** let the UI receive data changes automatically, while **local cache, offline persistence, and pending writes** create a responsive experience. However, "realtime" does not mean the server has confirmed the data or that every conflict has been resolved according to business rules.

In the **Firestore and Firebase** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson connects Firebase Authentication, Security Rules, Cloud Run/GKE, IAM, and Cloud Monitoring to build verifiable synchronization flows. Examples use **Cloud Firestore, the modular Firebase Web SDK**, and a study task list app; **Firebase Realtime Database** is a different product and does not use the same `onSnapshot()` API. Content prioritizes **Firestore Core/Standard** behavior; if using Enterprise/Pipeline operations, check the separate support scope and pricing model.

**After this lesson, you will be able to:**

1. Listen to changes on a **single document** or **query** with `onSnapshot()` and detach listeners cleanly with the UI lifecycle.
2. Distinguish the initial snapshot, `docChanges()`, `fromCache`, and `hasPendingWrites`.
3. Design offline behavior, reconnection recovery, and concurrent updates across devices.
4. Write access-compliant queries, test Security Rules, and avoid overly broad listeners.
5. Estimate document reads/cost, monitor errors, and test synchronization using the Firebase Emulator.

## 1. Firestore's Realtime Mechanism

When a client calls `onSnapshot(refOrQuery, callback)`, the SDK attaches a listener, delivers a **snapshot of the current state**, and then emits events whenever results change. The SDK may return cached data first and synchronize from the server afterward. For a query, the SDK keeps updating documents **belonging to the result set** as they are added, modified, or removed from that set.

~~~mermaid
sequenceDiagram
    participant A as Web A
    participant C as Local cache A
    participant F as Firestore
    participant B as Web B
    A->>F: Listen query /users/uid/tasks
    C-->>A: Cached snapshot if available
    F-->>A: Current snapshot from server
    B->>F: Write completed task
    F-->>A: Task change matching query
    A->>A: Update UI
    A->>F: Unsubscribe when leaving screen
~~~

| Concept | Meaning | What NOT to infer |
| --- | --- | --- |
| **Document listener** | Watches a single document at a specific path. | Does not watch an entire collection or related documents. |
| **Query listener** | Watches the set of documents matching filters, ordering, and limit. | Not a "subscription to every event" across the database. |
| **Initial snapshot** | Current state delivered by the SDK when the listener starts. | Does not default to "only new changes after opening the screen." |
| **`docChanges()`** | `added`, `modified`, `removed` changes between query snapshots. | `removed` does not necessarily mean deleted; it may simply no longer match the query. |
| **`unsubscribe()`** | Stops receiving events when a screen/component no longer needs data. | Does not delete Firestore data or cancel writes already sent. |

### 1.1. Document and query snapshots

For a document listener, check `snapshot.exists()` before calling `snapshot.data()`: a document might not exist yet or may have been deleted. For a query listener, `snapshot.docs` contains the currently matching documents, and `snapshot.empty` indicates an empty result set.

The **first query snapshot** typically emits `added` changes for every existing matching document. If you use `docChanges()` to append rows to UI without distinguishing initialization, you can accidentally create duplicates. Pick **one** of two approaches: rebuild the list from `snapshot.docs` for small sets, or maintain state keyed by document ID and apply diffs.

### 1.2. The Firebase SDK is not an authorization system

Realtime transport only delivers changes. **Firebase Authentication** establishes user identity; **Firestore Security Rules** define read/write permissions for mobile/web clients; **IAM** governs server SDKs and administrative services. A working listener does not guarantee a user cannot read someone else's documents.

Access boundaries must live **on the server via Rules/IAM**, not merely as JavaScript filters hiding rows that do not belong to the user.

## 2. Modular Web SDK Example: Listening and Detaching Properly

Assume the Firebase project is configured and the user has signed in with Firebase Authentication. Data lives at:

~~~text
users/{uid}/tasks/{taskId}
  title: string
  done: boolean
  updatedAt: timestamp
~~~

Each user has their own subcollection. This path structure helps Rules verify ownership while ensuring queries only read that user's study tasks. Do not rely on paths alone for authorization: Security Rules must still be configured.

### 2.1. Configuring Firebase and connecting to Firestore

~~~javascript
// firebase-client.js — use the real WEB config of an approved project.
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const app = initializeApp({
  apiKey: "WEB_API_KEY",
  authDomain: "YOUR_PROJECT.firebaseapp.com",
  projectId: "YOUR_PROJECT",
  appId: "YOUR_WEB_APP_ID"
});
export const auth = getAuth(app);
export const db = getFirestore(app);
~~~

**A Firebase Web config is not a service account private key**; even so, configure Authorized Domains properly, add App Check where appropriate, enforce Rules, and monitor quotas. Never place service account JSON keys, private API secrets, or IAM credentials in a frontend bundle.

### 2.2. Listening to a single document

~~~javascript
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "./firebase-client.js";

export function listenTask(uid, taskId, render, reportError) {
  const ref = doc(db, "users", uid, "tasks", taskId);
  const unsubscribe = onSnapshot(
    ref,
    (snap) => {
      render(snap.exists()
        ? { id: snap.id, ...snap.data() }
        : null);
    },
    (error) => reportError(error.code)
  );
  return unsubscribe;
}

// Example: const stop = listenTask(uid, taskId, render, reportError);
// When leaving the page, call stop() to detach the listener.
~~~

When Rules deny access or the query is invalid, the error callback fires and **that listener stops emitting events**; fix the root cause before re-subscribing rather than retrying blindly on `permission-denied`.

### 2.3. Listening to a scoped and bounded query

~~~javascript
import {
  collection, query, orderBy, limit, onSnapshot
} from "firebase/firestore";
import { db } from "./firebase-client.js";

export function listenRecentTasks(uid, onData, onError) {
  const tasks = collection(db, "users", uid, "tasks");
  const q = query(tasks, orderBy("updatedAt", "desc"), limit(20));

  return onSnapshot(q, (snapshot) => {
    // For small lists, rebuilding state is simple and safe.
    const rows = snapshot.docs.map((d) => ({
      id: d.id, ...d.data()
    }));
    onData(rows);
  }, onError);
}
~~~

This query returns **at most 20 tasks** that contain `updatedAt`, sorted descending. If a newer task pushes an older task past the 20th slot, the older task emits `removed` from the result set **due to the limit**, even though the document still exists in Firestore.

In React apps, attach the listener in `useEffect` and **return unsubscribe** in the cleanup function when `uid` changes or the component unmounts. Never create listeners on every render or inside the listener's own callback; that multiplies connections, events, and cost.

### 2.4. Applying only query diffs using `docChanges()`

When lists are larger and you want to update individual items rather than rebuilding all state, diff by **document ID**:

~~~javascript
import { onSnapshot } from "firebase/firestore";

// q is the query created in Section 2.3.
const stateById = new Map();
const stop = onSnapshot(q, (snapshot) => {
  for (const change of snapshot.docChanges()) {
    const id = change.doc.id;
    if (change.type === "removed") {
      stateById.delete(id);
    } else { // added or modified
      stateById.set(id, { id, ...change.doc.data() });
    }
  }
  render([...stateById.values()]);
}, (error) => showError(error.code));
~~~

This snippet **illustrates the diff algorithm**; `q`, `render`, and `showError` must be supplied by the calling screen, and `stateById` must be cleared when switching queries or users. A `Map` does not automatically maintain `orderBy` sorting on edits; if the UI needs strict ordering, use `snapshot.docs` or apply `oldIndex/newIndex` from document changes.

## 3. Latency Compensation: Displaying Data Before Server Confirmation

When a client updates Firestore, the SDK can fire local events immediately before the write reaches the server (*latency compensation*). This boosts UX, but you must distinguish:

| Property | `true` means | What the UI should do |
| --- | --- | --- |
| `snapshot.metadata.hasPendingWrites` | The snapshot contains local changes not yet confirmed by the server. | Show "Syncing"; do not claim saved to server. |
| `snapshot.metadata.fromCache` | Snapshot came from the local cache and may be stale or incomplete. | Show "Data may not be up to date"; do not assume online status. |
| Both are `false` | No pending local writes in the snapshot, and snapshot data came from the server. | Can indicate synced as of snapshot time; still does not replace separate business transaction confirmation. |

By default, listeners **do not fire when only metadata changes**. Enable `includeMetadataChanges: true` if the UI needs to transition explicitly from "Sending" to "Synced" even when field values remain identical.

### 3.1. Tracking pending writes and data source

~~~javascript
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "./firebase-client.js";

export function watchSyncStatus(uid, taskId, show) {
  const ref = doc(db, "users", uid, "tasks", taskId);
  return onSnapshot(
    ref,
    { includeMetadataChanges: true },
    (snapshot) => show({
      data: snapshot.exists() ? snapshot.data() : null,
      pending: snapshot.metadata.hasPendingWrites,
      fromCache: snapshot.metadata.fromCache
    }),
    (error) => show({ error: error.code })
  );
}
~~~

Example updating a task:

~~~javascript
import { doc, updateDoc, serverTimestamp } from "firebase/firestore";
import { db } from "./firebase-client.js";

export async function completeTask(uid, taskId) {
  const ref = doc(db, "users", uid, "tasks", taskId);
  // The listener may display 'done: true' before the Promise resolves.
  await updateDoc(ref, {
    done: true,
    updatedAt: serverTimestamp()
  });
  // Promise resolved: the write is confirmed by the server.
}
~~~

If `updateDoc()` is rejected (e.g., denied by Rules), the SDK rejects the Promise and reverts local state to match the server. Always **catch Promise errors** rather than relying solely on `hasPendingWrites=false` to confirm write success.

**Note on `serverTimestamp()`:** while pending, the timestamp may appear as an estimate, null, or the prior value depending on read options/SDK. Therefore UI must never rely on a local pending timestamp as authoritative proof of transaction completion order.

### 3.2. Waiting for all writes issued before a point in time

When an app needs to confirm "All changes made before this moment have synced," the Web SDK provides:

~~~javascript
import { waitForPendingWrites } from "firebase/firestore";
import { db } from "./firebase-client.js";

export async function waitForSync() {
  await waitForPendingWrites(db);
}
~~~

It waits only for writes **pending at the time of the call**, not writes started afterward. It can reject if the **signed-in user changes**; when offline, waiting can hang indefinitely. Never block the UI unconditionally: show a "Waiting for network" state with an exit path.

### 3.3. Distinguishing a listener from transaction confirmation

~~~mermaid
sequenceDiagram
    participant UI as UI
    participant SDK as SDK/cache
    participant DB as Firestore server
    UI->>SDK: updateDoc(done=true)
    SDK-->>UI: Snapshot pending=true (optimistic)
    SDK->>DB: Commit write
    alt Allowed and commit succeeds
      DB-->>SDK: Ack
      SDK-->>UI: Metadata pending=false
    else Denied / error
      DB-->>SDK: Error
      SDK-->>UI: Promise rejects and state reconciles
    end
~~~

**Takeaway:** "visible in my UI" is different from "committed by Firestore," which is different from "business workflow completed." For payments, exam submissions, or issuing certificates, have a backend validate the transaction and return an explicit outcome instead of treating an optimistic snapshot as final.

## 4. Offline Persistence and Reconnection Sync

Cloud Firestore mobile/web SDKs can cache accessed data locally, permitting certain reads/listeners/writes while offline. On reconnection, the SDK flushes pending changes and refreshes listeners. Support level, default cache, and configuration APIs **vary by platform**.

### 4.1. Web: memory cache vs persistent cache

The current modular Web SDK offers:

~~~javascript
import { initializeApp } from "firebase/app";
import {
  initializeFirestore,
  memoryLocalCache,
  persistentLocalCache,
  persistentMultipleTabManager
} from "firebase/firestore";

const app = initializeApp(firebaseConfig); // config for the lab project

// CHOOSE ONE at initialization time:
const dbMemory = initializeFirestore(app, {
  localCache: memoryLocalCache()
});

// Or, in a different Firebase app/instance:
// const dbPersistent = initializeFirestore(app, {
//   localCache: persistentLocalCache({
//     tabManager: persistentMultipleTabManager()
//   })
// });
~~~

These two options are **mutually exclusive on the same app instance**: call `initializeFirestore` **once** before using Firestore. `memoryLocalCache()` is the default when unspecified; `persistentLocalCache()` persists across sessions and can use a multi-tab manager when multiple tabs run concurrently.

**Privacy warning:** browser persistent cache survives tab closes and **is not automatically cleared on sign-out**. Do not enable it on kiosks, shared computers, or untrusted devices without assessing risk. When switching users on the same device, detach the previous user's listeners, clear UI state, and apply an explicit cache management policy; signing out **does not erase cached data from disk**.

### 4.2. Write conflicts when two devices go offline

Suppose a phone and laptop both edit a document's `title` field offline and later reconnect one after another:

- Each device initially sees its own **local change**.
- Upon reconnection, writes upload to the server; for multiple updates to the **same document**, Firestore applies **last-write-wins**.
- The other device receives the newer snapshot, which can make the task title "flip back" from its earlier local state.

**Last-write-wins is not smart business merging.** Never let two devices edit one monolithic object holding long text, progress, and critical permissions if the final write could overwrite another user's valid changes.

| Need | Better design |
| --- | --- |
| Toggle an independent flag | `updateDoc()` updating only the target field, avoiding full-document overwrites with stale data. |
| Completion/like counters | `increment(1)` where appropriate; never read–add–write manually on the client. |
| Tag sets | `arrayUnion()`/`arrayRemove()` where semantics match, watching document size. |
| Changes depending on existing data | **Transaction** while online, with conflict checks/resolution. |
| Complex collaborative document editing | Design revisions/merges/CRDTs or backend coordination; Firestore listeners alone do not merge text. |
| Multi-document writes without prior reads | Atomic **write batch**; mobile/web SDKs can queue them offline. |

**Firestore transactions fail when the client is offline**; do not portray transactions as an offline-first solution for all edits. For workflows needing strict consistency (inventory-checked orders, payments), use a Cloud Run/backend service with validation, transactions, or reliable workflows.

## 5. Securing Listeners with Authentication and Security Rules

A continuously attached listener is still an **authorized read request**. Security Rules apply to Web/Apple/Android SDKs, including listeners; **server SDKs use IAM and are not governed by Security Rules in the same way**.

### 5.1. Rules for per-user data

Minimal example for a **lab project** following `users/{uid}/tasks/{taskId}`:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/tasks/{taskId} {
      allow read, write: if request.auth != null
                         && request.auth.uid == userId;
    }
  }
}
~~~

This rule lets signed-in users access **only tasks under their own UID path**. It illustrates **ownership**, not a complete production ruleset: add type checks, `title` length bounds, allowed update fields, valid states, size limits, admin roles, and protection for other documents. Never apply `allow read, write: if true` to a database holding real data.

**The authenticated UID must come from Firebase Auth**, never accepting a client-sent `uid` field as proof of access. Before switching accounts or signing out, detach old listeners and clear displayed lists so the previous account's data does not linger on the same device.

### 5.2. Security Rules do not auto-filter queries

Suppose a shared `tasks` collection has an `ownerUid` field and Rules only allow reading documents where `ownerUid == request.auth.uid`. The client **cannot** run:

~~~javascript
// WRONG: could return another user's tasks, so Rules reject the whole query.
onSnapshot(collection(db, "tasks"), handleSnapshot);
~~~

The query must satisfy the Rules condition:

~~~javascript
import { collection, query, where, onSnapshot } from "firebase/firestore";

const q = query(
  collection(db, "tasks"),
  where("ownerUid", "==", auth.currentUser.uid)
);
const stop = onSnapshot(q, handleSnapshot, handleError);
~~~

This is an **alternative model** to the path structure in Section 2; you do not need both collections in one lab. Rules evaluate **whether a query could possibly return an unauthorized document**, rather than inspecting each document and silently stripping rows with another UID. Thus, a query missing its security filter can fail with `permission-denied` even if all existing documents happen to belong to one user.

### 5.3. Sign-in and listener lifecycle

~~~javascript
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "./firebase-client.js";
import { listenRecentTasks } from "./tasks.js";

let stopTasks = null;
const stopAuth = onAuthStateChanged(auth, (user) => {
  stopTasks?.();
  stopTasks = null;
  clearTaskUI();  // Do not retain the previous account's list.

  if (user) {
    stopTasks = listenRecentTasks(
      user.uid,
      renderTasks,
      (error) => showTaskError(error.code)
    );
  }
});

// When closing the entire screen:
// stopTasks?.();
// stopAuth();
~~~

`clearTaskUI`, `renderTasks`, and `showTaskError` are application callbacks. This pattern shows the lifecycle; in React/Vue, wire these into appropriate hooks and cleanups. Never reuse a listener opened with user A's permissions for user B.

### 5.4. When do you need a backend instead of a client listener?

Client listeners suit data that the user is **permitted to read directly**. For payment outcomes, moderation, tenant aggregations, or complex authorization logic, consider a Cloud Run/GKE backend using IAM that writes a **display-safe projection** into Firestore and lets the client listen only to that projection. **Never ship service account keys or Admin SDK credentials to the browser.**

## 6. Query Design, Performance, and Realtime Cost

A listener is not an "unlimited free connection." When attached, Firestore delivers the initial result set to the client and then pushes relevant updates. Large queries increase initialization latency, network/memory usage, and document reads.

### 6.1. When should you use a listener?

| Need | Approach | Rationale |
| --- | --- | --- |
| One currently open task | `onSnapshot(docRef)` | Watches only the displayed document. |
| User's 20 latest tasks | `onSnapshot(query(...limit(20)))` | Bounds results and avoids listening to the whole collection. |
| Historical list of 100,000 tasks | One-time query + cursor pagination | Never load and keep 100,000 documents in a UI listener. |
| Hourly summary reports | Backend aggregate, cache, or one-shot query | No need to subscribe to every minor mutation. |
| Event stream changing thousands of times/sec | Evaluate another sync model / periodic roll-ups | Risk of latency, cost, and result-set churn. |

**A `limit(20)` query does not freeze the initial 20 documents:** as sort values change, a document can enter while another leaves the result set, causing read charges and UI updates. Add indexes for filters/orders when the SDK flags them; indexes never replace Security Rules.

### 6.2. How listener billing works

For **Firestore Standard document reads**:

- **Initial snapshot:** returned documents typically count as reads; minimum charges and index-entry reads also apply depending on query type.
- **While listening:** a document **added to or updated within** the result set can incur a read; a document **removed from the result set due to data changes** also counts as a read. Actually deleting a document does not incur a read for that delete event.
- **Reconnection:** with offline persistence **disabled**, disconnecting and reconnecting can bill as a fresh query. With persistence **enabled**, disconnections exceeding **30 minutes** can bill as a fresh query.
- **Rules using `get()`/`exists()`** can generate extra document reads during evaluation.

**Simple estimate example:** 500 concurrent users open a screen where each listener initially returns 20 tasks, generating roughly **10,000 document reads for the initial load** (before index entries, Rules, reconnects, and updates). If users repeatedly close and reopen the screen, reads grow with each listener re-initialization. This is not an exact bill forecast; check your **edition, current pricing table, usage, and quotas**. Firestore Enterprise uses a **read units/real-time update units** model that differs from Standard.

### 6.3. Optimizing without sacrificing correctness

1. Listen **only when the screen needs it**; detach promptly and avoid duplicate listeners.
2. Use filters, `orderBy`, `limit`, and cursors instead of large offsets for historical pagination.
3. Keep documents compact, updating specific fields rather than rewriting entire objects repeatedly.
4. If a screen only needs summary state, maintain a **summary projection/snapshot** updated by business logic rather than listening to hundreds of child documents.
5. Avoid unnecessary writes to documents watched by large numbers of clients.
6. Track document reads/writes, index entries, and traffic per feature instead of assuming idle connections cost nothing.

### 6.4. Realtime at scale: do not confuse it with event streaming

A Firestore realtime query starts with an initial query snapshot and then receives updates from a changelog mechanism; during load balancing or transient issues, listeners may resync. Keep **initial queries fast** and listened datasets small.

Firestore listeners excel at synchronizing **UI state**, whereas high-throughput business event streams requiring independent replay/retention or multiple consumers usually fit Pub/Sub with worker processors. Both services pair well: Pub/Sub processes events, and a backend updates a summary document in Firestore for realtime UI delivery.

## 7. Hands-On: Syncing Two Devices with the Firebase Emulator

**Goal:** test listeners, local writes, offline mode, reconnection, and per-user authorization **without writing documents to production Firestore**. The emulator runs **on your development machine** with mock data and test accounts.

### 7.1. Preparation

Requires Node.js, npm, Firebase CLI, and a **separate lab directory**—never a production deployment directory. Inside that directory:

~~~bash
npm install firebase
npm install --global firebase-tools

# Initialize Firestore Rules and select Authentication and Firestore emulators.
# Run ONLY in a new LAB folder; do not overwrite real project configs.
firebase init firestore
firebase init emulators

# Start only the 2 configured emulators (illustrative ports 8080/9099).
firebase emulators:start --only firestore,auth --project demo-sync-lab
~~~

`firebase init` writes config files in your lab folder; if you lack global npm install permissions, use your policy-approved CLI installation or `npx`. Never point the SDK at a real project while testing offline/permissions, and verify the actual ports chosen in your lab folder's `firebase.json`.

In the **lab's `firestore.rules`**, use the rule from Section 5.1, ensuring no accidental public rules exist. Across emulator clients, point the SDK to the same `demo-sync-lab` project ID to prevent environment mismatches.

### 7.2. Configuring the client for the emulator

Create a test web page with Firebase modules and connect to the emulators **immediately after initialization**, before any database/Auth operations:

~~~javascript
import { initializeApp } from "firebase/app";
import {
  getAuth, connectAuthEmulator, signInAnonymously
} from "firebase/auth";
import {
  getFirestore, connectFirestoreEmulator,
  collection, doc, setDoc, updateDoc, onSnapshot,
  serverTimestamp, disableNetwork, enableNetwork
} from "firebase/firestore";

const app = initializeApp({
  apiKey: "demo-key",
  authDomain: "demo-sync-lab.firebaseapp.com",
  projectId: "demo-sync-lab",
  appId: "demo-app"
});
const auth = getAuth(app);
const db = getFirestore(app);
connectAuthEmulator(auth, "http://127.0.0.1:9099");
connectFirestoreEmulator(db, "127.0.0.1", 8080);

// Anonymous user ONLY on the Auth emulator.
const { user } = await signInAnonymously(auth);
const tasksRef = collection(db, "users", user.uid, "tasks");
const taskRef = doc(tasksRef, "lesson-java-1");

const stop = onSnapshot(
  taskRef,
  { includeMetadataChanges: true },
  (s) => console.log("snapshot", {
    exists: s.exists(),
    data: s.data(),
    pending: s.metadata.hasPendingWrites,
    cache: s.metadata.fromCache
  }),
  (e) => console.error("listen error", e.code)
);

await setDoc(taskRef, {
  title: "Complete Java Lesson 1",
  done: false,
  updatedAt: serverTimestamp()
});

// Simulate network loss on the Firestore SDK only, keeping the tab open:
await disableNetwork(db);
const pending = updateDoc(taskRef, {
  done: true, updatedAt: serverTimestamp()
});
// Do not await 'pending' while still offline: the Promise may wait indefinitely.
await enableNetwork(db);
await pending; // Confirmed by the emulator backend.

// When closing the screen or finishing the lab:
stop();
~~~

This snippet uses **top-level await** inside a JavaScript module; run it via a dev server/bundler supporting `firebase/*` imports rather than pasting directly into a non-module console. This is lab code only: never deploy `demo-key` values to production. If your emulators use different ports, update both `connect*Emulator` calls before testing.

### 7.3. Expected test suite

| Step | Action | Expected observation |
| --- | --- | --- |
| 1 | Open tab, sign in user A, attach listener | Snapshot receives empty doc or existing lab data. |
| 2 | `setDoc` a task, then open a second tab with same UID | Both sessions see the new state after syncing with the emulator. |
| 3 | `disableNetwork` on one tab, then `updateDoc` | That tab sees local change and `pending=true`. |
| 4 | `enableNetwork` and await the update Promise | `pending=false`, other tab receives new snapshot after server ack. |
| 5 | Sign in user B in another browser profile | User B **cannot** read the document under user A's path. |
| 6 | Unsubscribe, then modify data from another tab | Detached callback no longer updates UI. |
| 7 | Disconnect both, edit same field on two devices, reconnect | **Last-write-wins** conflict occurs, requiring application-level handling. |

**Two tabs in the same browser may share Firebase Auth state**, so use a separate browser profile or isolated session when testing two **different UIDs**. To test persistent cache, configure it at initialization in a **separate lab** and verify device data-retention policies. Never use real learner data when testing offline caching.

### 7.4. Testing Security Rules

Define expected outcomes before running:

- User A reads/writes tasks under `users/A/tasks`: **allow**.
- User A reads/writes under `users/B/tasks`: **deny**.
- Unauthenticated read on personal tasks: **deny**.
- Broad query across users in a shared collection without an owner constraint: **deny**.

Use the **Rules Unit Testing SDK** or **Emulator UI**/test client to execute both allowed and denied cases. Never conclude Rules are safe simply because the UI hides buttons for viewing other users' data.

### 7.5. Lab cleanup

Stop listeners and dev servers, shut down the Emulator Suite, and remove mock data and test directories per policy. Emulators do not alter real databases by default, **only provided the SDK actually connected to the emulator before sending any requests**. Verify project ID, hostname, and logs; never run collection deletes in a production project to clean up an exercise.

## 8. Listener and Sync Troubleshooting Runbook

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Listener returns `permission-denied` | Not signed in, wrong UID/path, query fails to prove authorization | Inspect auth state, Security Rules, and filters/paths; test in Rules Emulator. |
| Listener asks for an index | Multi-filter/order query lacks a composite index | Create the suggested index after review; never relax Rules to "fix" index errors. |
| New tab shows stale data before fresh data | Snapshot served from cache, weak network, or not yet synced | Surface `fromCache`, wait for server updates, never treat cache as absolute truth. |
| UI shows "saved" and then reverts | Optimistic local write rejected/overwritten by server | Handle Promise errors, track `hasPendingWrites`, `serverTimestamp`, and conflict policies. |
| One user's data remains after logout | Listener/state not cleaned up; persistent cache remains on device | Detach listeners, clear UI, evaluate persistent cache policy on shared devices. |
| RAM or reads climb during navigation | Every render/mount adds a listener without detaching | Manage one subscription per query; unsubscribe on unmount. |
| `removed` fires even though document was not deleted | Left result set due to filter, order, or `limit` | Check query and diff by document ID; never delete DB records based on UI diff events. |
| Two devices overwrite each other | Last-write-wins on same document, no versioning/merge | Split fields, check revisions, use online transactions or backend conflict resolution. |
| Screen needs to load thousands of docs | Overly broad query, missing index, or poor screen design | Use `limit`, cursors, projections; measure initial snapshot latency and read counts. |
| Frequent reconnects drive up cost | Listeners detach/reopen, persistence off, or long offline gaps | Reduce re-subscribes, keep screen-scoped listeners stable, review offline policies and usage. |

**Investigation order:** verify UID/auth and path → SDK errors → cache/pending state → query/index/Rules → network/reconnects → usage/billing. On `permission-denied`, never retry in a tight loop or disable Rules; fix the authorization condition and run negative tests before deploying.

## 9. Scenario Exercises

### A — Syncing learning progress across two devices

While the phone is offline, a learner marks a lesson `done=true`. Meanwhile, the online laptop edits the same task's title. When the phone regains connectivity, the UI on both devices may change again.

**Task:** distinguish optimistic updates from server commits and describe how to reduce accidental overwrites.

**Solution approach:** display `hasPendingWrites` and `fromCache`; only announce saved after the write Promise resolves/acks. Update only the specific **field** changed rather than calling `setDoc` with a whole stale object from cache; if two clients edit the very same field, use revisions/online transactions or backend conflict rules. Never trust client-clock timestamps.

### B — Dashboard opening too many listeners

An admin page attaches one listener per task, adds another listener on every render, and never detaches them on route changes. The browser slows down and document reads spike.

**Task:** redesign the listening strategy.

**Solution approach:** listen to **a single filtered/limited query** for the visible list using `docChanges` or `snapshot.docs`; attach a single-document listener only when opening a detail view. Register inside component lifecycle hooks, detach in cleanup, and avoid recreating queries unnecessarily. Measure query size, active subscriptions, and reads before and after.

### C — Read denied even though "all tasks are mine"

Rules only allow reading documents where `ownerUid == request.auth.uid`, yet the app listens to the entire `tasks` collection and filters by UID in JavaScript.

**Task:** explain the error and fix it without exposing data.

**Solution approach:** Rules **are not filters**. The query must include `where("ownerUid", "==", uid)`, or move data into a `users/{uid}/tasks` subcollection with matching Rules. Test that another user cannot read the owner's tasks.

### D — Confirming payment from a pending snapshot

A user clicks "Pay," the frontend directly sets `orders/{id}.paid=true`, and the listener displays "Paid," even though Security Rules later reject the write.

**Task:** redesign the flow safely.

**Solution approach:** have the backend verify the payment provider, validate signatures/idempotency, and write the server-authoritative status; the Firestore listener **only displays** the backend-written status. Never allow clients to freely edit `paid` or treat an optimistic write as proof of completed payment.

### E — Rough screen-open read estimate

Each user opens a dashboard 4 times/day; each open creates a query listener returning 25 tasks with no updates while open. There are 2,000 users/day.

**Task:** estimate initial document reads under the simple model and name factors that alter the real figure.

**Solution approach:** `2,000 × 4 × 25 = 200,000` initial-load document reads, **before** considering minimum charges, index entries, security-rule reads, reconnects, cache/persistence, and edition billing. Use sensible session lifetimes, bounded queries, avoid duplicate listeners, and check real usage metrics—never weaken security or drop needed data just to save reads.

### F — Offline transaction failure

An app tries to use a transaction to deduct a course enrollment seat while the device is offline.

**Task:** why can this not be guaranteed, and what is the alternative?

**Solution approach:** Firestore transactions **do not succeed offline**. You can record a **pending reservation request** via an offline queue if business logic permits, while a backend handles concurrency and confirms seat availability before transitioning status to "Enrolled." Never declare stock exhausted or payment committed from local state alone.

## 10. Pre-Deployment Checklist

| Check | Acceptance criterion |
| --- | --- |
| **Correct data** | Listener targets the right doc/query with `limit` and matching index; docs missing `orderBy` fields handled. |
| **Lifecycle** | Each screen opens only necessary listeners; unsubscribes on unmount, account switch, or query change. |
| **Sync state** | UI distinguishes cached data, pending writes, server acknowledgments, and rejected writes. |
| **Offline** | Offline devices degrade gracefully; conflicts and retries have clear resolution rules. |
| **Security** | Firebase Auth + Security Rules have allow/deny unit tests; server SDK uses least-privilege IAM. |
| **Privacy** | Persistent cache enabled only when appropriate for device and data sensitivity; logout clears UI state. |
| **Performance** | Initial queries are fast, result sets are small, and p95/p99 UI latency and reads/writes are measured. |
| **Reliability** | Tested offline mode, multi-tab sync, user switching, missing indexes, `permission-denied`, and write conflicts. |
| **Business logic** | Financial/enrollment states are confirmed by a trusted component, never optimistic events. |

### Self-check

1. **Does `onSnapshot()` return only changes occurring after attachment?** — No; the listener delivers the initial state first, then subsequent updates.
2. **Does `docChanges().removed` guarantee the document was deleted?** — No; it may simply no longer match the query/filter/limit.
3. **Does `hasPendingWrites=true` confirm the server committed the write?** — The opposite; unconfirmed local writes are still pending.
4. **Does `fromCache=false` prove all related business steps finished?** — No; it only reflects the snapshot's source.
5. **Why is `includeMetadataChanges` needed?** — To receive callbacks when only metadata like pending/cache status changes.
6. **Does signing out automatically clear persistent cache?** — No; explicit cache and device policies are required.
7. **Can a mobile/web Firestore transaction complete while offline?** — No.
8. **Do Security Rules filter individual unauthorized documents out of a query?** — No; the entire query can be rejected.
9. **Does the Firestore server SDK depend on Security Rules like client SDKs?** — No; it uses IAM/server permissions.
10. **Why are longer-lived listeners often better than constantly re-opening them?** — Reduces repeated initial query executions while the app still needs data, depending on caching/reconnects/billing.

## 11. Official Documentation

- [Firestore — Listen to realtime updates](https://firebase.google.com/docs/firestore/query-data/listen): document/query listeners, metadata, `docChanges`, unsubscribe, and errors.
- [Firestore — Offline access](https://firebase.google.com/docs/firestore/manage-data/enable-offline): memory/persistent cache, resync, and last-write-wins.
- [Firestore — Security Rules and queries](https://firebase.google.com/docs/firestore/security/rules-query): why Rules are not filters, owner-scoped queries.
- [Firestore — Transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions): atomic writes, transaction retries, and offline behavior.
- [Firestore — Understand billing](https://firebase.google.com/docs/firestore/pricing): query listener reads, index entries, Rules, and reconnects in Standard.
- [Firestore — Enterprise pricing](https://firebase.google.com/docs/firestore/enterprise/pricing): read units/real-time updates model when using Enterprise.
- [Firestore — Realtime queries at scale](https://firebase.google.com/docs/firestore/real-time_queries_at_scale): query initialization, changelog, large listeners, and costs.
- [Firebase Local Emulator Suite](https://firebase.google.com/docs/emulator-suite/install_and_configure): configuring Auth/Firestore emulators and project IDs.
- [Firestore Web modular API reference](https://firebase.google.com/docs/reference/js/firestore): `onSnapshot`, `waitForPendingWrites`, cache, and network controls.
- [Firebase Security Rules testing](https://firebase.google.com/docs/rules/emulator-setup): testing allow/deny with the emulator before deployment.

**Conclusion:** Realtime listeners make interfaces respond rapidly as data changes, yet correct synchronization requires **managing listener lifecycles, distinguishing local from server state, resolving conflicts, and enforcing Security Rules/IAM**. Good designs bound result sets, handle offline states without losing data, protect users, and are verified by **real errors, sync latency, and document reads**—not merely by watching the UI update immediately.
