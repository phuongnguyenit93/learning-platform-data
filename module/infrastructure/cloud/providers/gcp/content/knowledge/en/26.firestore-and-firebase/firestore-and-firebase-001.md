# Firestore Database Modes and Selection Criteria

> **Chapter:** Firestore and Firebase  
> **Lesson:** Firestore Database Modes and Selection Criteria  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases, while learning how to select services, protect resources, automate deployments, and monitor reliability and cost. For Java applications combined with Firebase or Google Cloud, **choosing the right Firestore database mode** is an early architectural decision: it affects APIs, SDKs, data models, queries, security, and future migration paths.

Firestore is a managed NoSQL document database service. **You should not stop at the old "Native vs Datastore" comparison**: current Google Cloud documentation distinguishes between **database edition** (Standard or Enterprise) and **data access mode** (Native, Datastore compatibility, or MongoDB compatibility). These two choices constrain each other.

**Quick takeaway:** new applications using Firebase SDKs and realtime/offline typically choose **Firestore Native**; applications requiring legacy Datastore APIs choose **Standard + Datastore mode**; applications wanting to use MongoDB drivers/MQL consider **Enterprise + MongoDB compatibility**; if using Native but needing an advanced query engine/Pipeline operations, evaluate **Enterprise + Native mode**. Each case still requires verifying performance and total cost.

Project, collection, user, and configuration examples in this lesson are hypothetical. The `gcloud firestore databases create` command can create billable resources and a permanent location setting; only run it in an authorized sandbox. This document is self-contained, though it intentionally focuses on **selection criteria** rather than serving as a comprehensive Firestore operations manual.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **edition** from **data access mode**, and identify the supported combinations.
2. Describe **Firestore in Native mode**, **Firestore in Datastore mode**, and **Firestore with MongoDB compatibility**.
3. Explain Firestore **Standard vs Enterprise** in terms of query engine, indexing, realtime/offline capabilities, and billing model.
4. Select the appropriate mode for **Firebase mobile/web**, **Java backends on Cloud Run/GKE**, **legacy App Engine Datastore**, and **MongoDB workloads**.
5. Model document data, design queries, and avoid SQL relational assumptions.
6. Distinguish **Firebase Authentication + Firestore Security Rules** from **server Java SDK + IAM**.
7. Inspect a database's edition/mode/location via CLI and create a lab database in a controlled manner.
8. Use the Java Firestore SDK with a **named database**, and understand how it differs from Datastore/MongoDB clients.
9. Evaluate migration, indexes, security, consistency, scaling, backups, and cost.
10. Complete the architecture exercises and production checklist.

## 2. Two Axes of Firestore Selection: Edition and Data Access Mode

~~~mermaid
flowchart TD
    Start["Need a Firestore database"]
    E{"Choose edition"}
    S["Standard"]
    Ent["Enterprise"]
    N1["Native mode<br/>Firestore Core API"]
    D["Datastore mode<br/>Datastore API"]
    N2["Native mode<br/>Core + Pipeline API"]
    M["MongoDB compatibility<br/>MongoDB drivers/MQL"]
    Start --> E
    E --> S
    E --> Ent
    S --> N1
    S --> D
    Ent --> N2
    Ent --> M
~~~

| Edition | Supported data access mode | Meaning |
|---|---|---|
| **Standard** | **Native** | Firebase SDK/mobile/web, Firestore Core SDKs, standard query engine |
| **Standard** | **Datastore** | Datastore API compatibility, legacy applications depending on Datastore |
| **Enterprise** | **Native** | Firestore Core **and Pipeline operations**, advanced query engine |
| **Enterprise** | **MongoDB compatibility** | Access via supported MongoDB-compatible APIs/drivers and BSON/MQL |

**Mode is not a "pricing tier" and edition is not an "API type."** For example, two databases both in **Native mode** can use two different editions, leading to differences in indexing, querying, and pricing. Each database selects one data access mode; **a single database cannot simultaneously accept the Datastore API and provide the full Firestore Native SDK**.

### 2.1. Are Firestore, Firebase, and Cloud Datastore three separate databases?

- **Cloud Firestore** is Google Cloud's database service, used from both the Google Cloud console and the Firebase ecosystem.
- **Firebase** is an application development platform; Firebase Authentication and client SDKs support connecting to Firestore Native mode.
- **Cloud Datastore** is the earlier API/ecosystem. Firestore in Datastore mode provides a **Datastore API compatibility** layer, primarily for workloads with historical dependencies.
- **Firestore with MongoDB compatibility** uses MongoDB-compatible APIs/drivers and **is not automatically MongoDB Atlas or a MongoDB server with feature-for-feature parity**.

UI/SDK labels and older guides may use simpler categorizations; when designing new systems, verify the actual **edition + data access mode + database ID + location**.

### 2.2. Can a single project have multiple databases?

**Yes**, Firestore supports multiple databases within a project, with editions/modes tailored to each database. For instance, you can have a Native database for a Firebase app and a Datastore-mode database serving a legacy app, within current product limits.

However, keep in mind:

- Client SDKs usually default to the **`(default)`** database. For a **named database**, you must specify its ID explicitly.
- **App Engine Datastore** has constraints tied to the `(default)` database and supported editions/modes; do not treat an arbitrary named database as a drop-in replacement.
- Security Rules, IAM, indexes, backups/PITR, metrics, and location may need to be managed **per database**.
- The **free tier** is not multiplied by the number of databases: typically only **one database per project** receives the free tier under current rules.

## 3. Firestore in Native Mode: For Modern Applications

### 3.1. The collection/document model

~~~text
orders                      (collection)
└── order-a71c               (document)
    ├── customerId: "u-42"
    ├── tenantId: "shop-a"
    ├── status: "CREATED"
    ├── amountMinor: 129900
    ├── createdAt: timestamp
    └── lines                 (subcollection)
        └── line-1            (document)
            ├── sku: "SKU-9"
            └── quantity: 2
~~~

Key concepts:

- **Collection:** a named group of documents.
- **Document:** a set of field-value pairs (string, number, boolean, timestamp, array, map, reference, etc.).
- **Subcollection:** a collection nested under a document path; deleting a parent document does not automatically delete all data in its subcollections.
- **Document reference/path:** a structured identifier used to read, write, and query.
- **Transactions/batched writes:** for multi-document changes within supported constraints; not arbitrary SQL transactions with JOINs and foreign keys.

**Native fits** when you need web/iOS/Android SDKs, **realtime listeners**, offline caching/synchronization, and a data model designed around your application's access patterns. Java backends on Cloud Run/GKE can also use **Firestore server client libraries** with this mode.

### 3.2. Realtime and offline

Firebase/Firestore mobile & web SDKs can support:

- **Realtime listeners** that update documents/queries when data changes.
- **Offline cache/persistence** depending on the SDK/platform and supported configuration.
- Synchronization when connectivity returns, following rules for offline writes and conflict behavior.

**Do not confuse:** realtime/offline support in **Firestore Native Core operations** does not mean every **Enterprise Pipeline query** supports realtime/offline. With Enterprise Native, check the database's **realtime updates configuration** and the supported API scope.

### 3.3. How Native queries differ from SQL

~~~text
Fetch orders for a user:
collection("orders")
  .whereEqualTo("customerId", "u-42")
  .whereEqualTo("status", "CREATED")
  .orderBy("createdAt")
~~~

Important points:

- Firestore Native Standard relies on **indexes** for queries; queries combining multiple fields may require a **composite index**.
- There are no SQL foreign keys or arbitrary joins in **Standard Core queries**. Design around read patterns and accept some controlled duplication.
- Transactions have their own semantics and limits; do not assume PostgreSQL locking behavior.
- Document size in **Native mode** for both Standard and Enterprise is limited to **1 MiB** per current documentation; do not stuff large PDFs/images into documents. Use Cloud Storage for files and store metadata in Firestore.

## 4. Firestore in Datastore Mode: Compatibility for Legacy Applications

Datastore mode provides the Datastore API for systems already built around **entities, kinds, keys, namespaces, and ancestor queries**.

| Component | Datastore API | Firestore Native API |
|---|---|---|
| Record type | **Entity** | **Document** |
| Data group | **Kind** | **Collection** |
| Identifier | **Key** / key path | Document reference/path |
| Parent-child relationship | Ancestor/entity group | Document/subcollection hierarchy |
| Java SDK | `google-cloud-datastore` | `google-cloud-firestore` |
| Firebase mobile/web realtime | **No** | **Yes** via Native Core when configured appropriately |
| Firestore Security Rules for Firebase SDK | **Not used in the Native way** | **Yes** for mobile/web clients |
| Best fit | Legacy App Engine/Datastore | New applications using the Firestore API |

### 4.1. Why would you still choose Datastore mode?

If an App Engine Java application already uses Datastore `Entity`/`Key`/`Query`, immediately rewriting the entire data model, indexes, and code to Native can increase risk without delivering urgent benefits. Datastore compatibility keeps the application running while enabling a planned, gradual transition.

**Google Cloud documentation recommends Datastore compatibility primarily for workloads already depending on Datastore APIs.** For new applications without legacy API constraints, you generally **do not choose Datastore mode** just because the code runs on a Java backend. Native mode also supports server-side Java.

### 4.2. Datastore mode does **not** unlock Native features

A Datastore-mode database **does not automatically support**:

- Firebase Native mobile/web SDKs and Firestore realtime/offline listeners.
- The full Firestore Native query surface.
- Native's indexing and query system.
- Firebase Firestore Security Rules as used with Native client SDKs.

**Do not assume** that changing the Java library import from `Datastore` to `Firestore` lets you reuse the same database immediately. This is a mode/API boundary, not just a difference in class names.

## 5. Firestore with MongoDB Compatibility: Enterprise Edition

This is a **data access mode of Firestore Enterprise** designed for applications that want to use **MongoDB drivers, BSON types, and MongoDB Query Language (MQL) within the supported feature set**.

~~~mermaid
flowchart LR
    Java["Java service<br/>MongoDB driver"]
    Conn["TLS + OIDC / auth<br/>loadBalanced mode"]
    Mongo["Firestore Enterprise<br/>MongoDB compatibility"]
    Query["MQL/BSON<br/>supported subset"]
    Java --> Conn --> Mongo --> Query
~~~

### 5.1. When it fits

- The project has existing **MongoDB drivers/models/data access code** and wants to evaluate Firestore managed infrastructure.
- The team relies on a subset of MQL/BSON and MongoDB tooling already supported by the service.
- You need the Enterprise query engine and a cost/scale model that matches actual volume.

### 5.2. Dangerous assumptions

- **It is not 100% binary/feature compatible** with every MongoDB/Atlas release. You must cross-check **supported MongoDB versions, commands, operators, drivers, index types, and transaction limits** before migrating.
- Clients must use Google-supported settings, including **TLS**, **load-balanced mode**, and **disabled retryable writes** per current connection guidance.
- **Java MongoDB driver 5.x** is one documented supported line; OIDC authentication also has its own minimum driver version.
- With MongoDB compatibility, the document limit can be up to **16 MiB** (unlike Native's 1 MiB); verify this against the edition documentation and your specific workload.
- **You cannot use Firebase Native realtime listeners/Security Rules as the same API** on a MongoDB-compatibility database.
- A MongoDB application with specialized aggregations/procedures/indexes still needs a proof-of-concept; do not promote it as "just swap the URI and you're done."

### 5.3. Java verification steps

~~~text
1. Create an Enterprise database with MongoDB compatibility.
2. Retrieve the connection string using official Google Cloud tools.
3. Choose a supported Java MongoDB driver; configure TLS/auth.
4. Enable loadBalanced and disable retryWrites per the documentation.
5. Run the test suite for CRUD, queries, aggregations, and transactions.
6. Compare indexes, p95/p99 latency, and billing.
7. Prepare a rollback plan to the original database before cutover.
~~~

**Do not hand-craft a connection string from just the project ID and hostname.** Firestore MongoDB compatibility uses a **database UID** and specific connection requirements; obtain the URI from the Google Cloud Console/CLI and keep credentials secure.

## 6. Standard vs Enterprise: Same Native, Different Behavior

| Criterion | Standard + Native | Enterprise + Native |
|---|---|---|
| Query API | Firestore **Core operations** | Core **and Pipeline operations** |
| Engine | Standard query engine | Advanced query engine |
| Single-field indexes | Created automatically by default | **Not created automatically** |
| Queries missing an index | Usually rejected, requiring a matching index | **Can execute via scan**, but risks high latency/cost |
| Composite / custom indexes | Configured when queries require them | Decided and optimized explicitly with supported index types |
| Realtime/offline Core | Supported via Firebase SDK | Supports Core when matching capability is configured |
| Pipeline advanced queries | No | Yes |
| Native document size | Up to **1 MiB** | Up to **1 MiB** |
| Billing focus | Document reads/writes/deletes, index entries, storage, egress | **Byte-based read/write units**, storage, egress |
| Primary fit | Most standard Firebase/mobile & Java applications | Advanced querying, intensive performance and index management needs |

**Enterprise features do not mean always faster or cheaper.** If an application queries large collections without creating indexes on Enterprise, the engine may scan large numbers of documents, increasing latency and read units even though the query succeeds.

### 6.1. Query and cost example

A Java API runs:

~~~text
orders where tenantId = "shop-a"
  and status = "PAID"
  order by createdAt desc
  limit 20
~~~

- **Standard:** requires a compatible index; if a composite index is missing, create the suggested index and test.
- **Enterprise Native:** the query can run without an index, but scans lots of data at high volume; use **Query Explain/Insights** and create an appropriate index.
- **Datastore mode:** must be rewritten using the Datastore API, following Datastore indexes/rules.
- **Mongo compatibility:** written in compatible MQL/driver, verifying supported operators and index plans.

The same logical query can have significantly different **APIs, indexes, and billing**. When benchmarking, compare **cost per transaction meeting SLO** rather than just unit read price.

### 6.2. When should you choose Enterprise?

Consider it if the workload has one or more of these requirements:

- Needs advanced **Pipeline operations** beyond the Core API.
- Has many dynamic queries and wants flexible index management tailored to the workload.
- Is evaluating MongoDB compatibility.
- Has specific performance/tail-latency targets measured in a representative environment.
- Has validated the Enterprise billing model across query bytes, storage, and network.

**Do not upgrade all databases to Enterprise just because the word "Enterprise" sounds safer.** Standard still supports backups/PITR, IAM, encryption, and high availability depending on configuration.

## 7. Mode Selection Matrix for Java and Firebase Architectures

| Scenario | First choice | Why | Check further |
|---|---|---|---|
| Realtime chat on Android/iOS/web | **Standard + Native** | Firebase SDK, listeners, and offline | Security Rules, indexes, read amplification |
| Java Orders API on Cloud Run, CRUD/order status | **Standard + Native** | Java Firestore SDK, managed NoSQL, low ops | Transaction patterns, composite indexes, tenant authorization |
| Java backend with highly complex dynamic queries | **Enterprise + Native** | Advanced Core/Pipeline, flexible indexing | Scans, supported Pipeline features, billing |
| Legacy App Engine Java using Datastore API | **Standard + Datastore** | Preserves code/entities/keys/indexes | Default DB constraints and migration plan |
| Java service using MongoDB driver/MQL | **Enterprise + MongoDB compatibility** | Reuses compatible drivers/data model | Supported commands, TLS/OIDC, retryWrites |
| Java API needing heavy JOINs, foreign keys, SQL transactions | **Cloud SQL/AlloyDB** before Firestore | Relational and integrity requirements | DB TCO, SQL schema, concurrency |
| Event analytics/OLAP scanning large datasets | **BigQuery** before Firestore | Large-scale analytical queries | Ingestion, latency, cost |
| Only storing files/PDFs/images | **Cloud Storage** + Firestore metadata | Blob storage is a better fit | Access control and object lifecycle |

**Do not pick Firestore thinking "serverless means no design needed."** NoSQL eliminates database server administration, but **data modeling, indexes, access rules, hotspots, backups, observability, and billing** remain the team's responsibility.

## 8. Security: Firebase Security Rules Are Not Google Cloud IAM

### 8.1. Two different client types

~~~mermaid
flowchart LR
    Mobile["Mobile/Web app"]
    Auth["Firebase Authentication"]
    Rules["Firestore Security Rules"]
    Native["Firestore Native database"]
    Java["Java API on Cloud Run"]
    ADC["Runtime Service Account + IAM"]
    Mobile --> Auth --> Rules --> Native
    Java --> ADC --> Native
~~~

| Client | Auth/authorization mechanism | What to remember |
|---|---|---|
| Mobile/web using Firebase client SDK | Firebase Authentication + **Firestore Security Rules** | Rules check access per user/document |
| Java server using Google Cloud Firestore client | **Application Default Credentials + IAM** | **Bypasses Firestore Security Rules** |
| Firebase Admin SDK | Google credentials + IAM | Server privilege; does not go through Rules |
| Datastore-mode server client | Google Cloud IAM | Does not use Firebase Rules like Native |
| MongoDB-compatible client | Mode-specific authentication/authorization | Does not use Firebase Rules by default |

**Critical mistake:** setting Firestore Rules to `allow read, write: if false` and assuming the Java server cannot read the database. **Server SDKs bypass Security Rules** and use IAM permissions. Conversely, granting `roles/datastore.user` to the Cloud Run runtime service account **does not grant access** to a Firebase mobile client denied by Rules.

### 8.2. Rules example for an orders app

A sample Rules policy that **allows reading only the signed-in user's documents**, permits minimal order creation, and forbids direct client updates/deletes:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /orders/{orderId} {
      allow read: if request.auth != null
                  && resource.data.ownerUid == request.auth.uid;

      allow create: if request.auth != null
                    && request.resource.data.ownerUid == request.auth.uid
                    && request.resource.data.status == 'CREATED'
                    && request.resource.data.keys().hasOnly(
                         ['ownerUid', 'status', 'createdAt']);

      allow update, delete: if false;
    }
  }
}
~~~

**Rules are not a query result filter.** A client querying `orders` **without** constraining `ownerUid` can be rejected even if some documents belong to that user; design compatible queries/rules and test them with the **Firebase Emulator Suite**. This sample blocks clients from setting `status=PAID` themselves, but it is **not complete business validation** (creation time, field catalog, and receipts); payment transitions should go through a Java backend with validation/transactions.

### 8.3. The Java backend must enforce tenant checks

If a Cloud Run Java service uses a runtime SA with permission to read the `orders` collection, it must:

1. Verify the HTTP caller's JWT/session.
2. Derive `tenantId`/`uid` from the verified identity; **never trust caller-supplied headers**.
3. Query/read the right documents and enforce authorization in the domain layer.
4. Log business access audits while avoiding PII/credential logging.
5. Apply IAM least privilege to the workload SA, avoiding `Owner/Editor`.

Firestore Rules **do not protect against authorization bugs in a Java server** because server IAM already grants access within its assigned scope.

## 9. Lab A — Safely Inspect Edition, Mode, and Location

**Read-only commands**, no resource creation or deletion:

~~~bash
gcloud auth list
gcloud config get-value project

gcloud firestore databases list \
  --project=PROJECT_ID

gcloud firestore databases describe \
  --project=PROJECT_ID \
  --database="(default)"
~~~

For a named database, replace `(default)` with the actual ID. Inspect:

- **edition**: STANDARD/ENTERPRISE;
- **type / access mode**: FIRESTORE_NATIVE, DATASTORE_MODE, or Enterprise capability flags;
- **locationId**;
- **deleteProtectionState**;
- indexes, TTL, backups/PITR, and other settings where supported.

**Do not infer mode from the database name alone**; a database named `orders-native` can still be in another mode if created incorrectly. Before running the Java SDK, verify the actual ID, project, and edition/mode on the resource.

### 9.1. Create Standard + Native for the lab

**This command creates a database and may incur charges.** Choose a location supported by Firestore Standard that meets data residency requirements:

~~~bash
gcloud firestore databases create \
  --project=PROJECT_ID \
  --database=orders-native-lab \
  --location=asia-southeast1 \
  --edition=standard \
  --type=firestore-native \
  --delete-protection
~~~

`--delete-protection` guards against accidental deletion. If you want to clean up after the lab, you must **intentionally disable deletion protection** before deleting; never delete databases owned by other teams. If the app uses Firebase web/mobile, configure **restrictive Security Rules** on the newly created database before allowing client access.

### 9.2. Create Standard + Datastore for a legacy app

Illustrates **an alternative option**; you do not have to create both databases:

~~~bash
gcloud firestore databases create \
  --project=PROJECT_ID \
  --database=legacy-datastore-lab \
  --location=asia-southeast1 \
  --edition=standard \
  --type=datastore-mode \
  --delete-protection
~~~

This database uses the **Datastore API**, **not** the Native SDK. For legacy App Engine Datastore, check `(default)` database and project/App Engine location constraints; a new named database **does not automatically replace** the application's default datastore.

### 9.3. Create Enterprise + Native when advanced queries are needed

Per current Firestore Enterprise guidance, sample configuration:

~~~bash
gcloud firestore databases create \
  --project=PROJECT_ID \
  --database=orders-enterprise-lab \
  --location=LOCATION_SUPPORTED_BY_ENTERPRISE \
  --edition=enterprise \
  --enable-firestore-data-access \
  --no-enable-mongodb-compatible-data-access \
  --enable-realtime-updates \
  --delete-protection
~~~

**Replace location with an actual value supported by the edition.** If you want MongoDB-compatible APIs, choose **Enterprise + MongoDB compatibility** when creating the database; **do not** enable both APIs simultaneously just to share collections across both drivers. Check database creation flags in the latest CLI reference.

**Location cannot be changed after database creation.** For databases containing data, plan a migration when changing mode/edition rather than relying on a one-click operation. Management docs allow changing the **Native/Datastore type of an empty database** under supported conditions, but that is not a migration strategy for production systems holding data.

## 10. Lab B — Java 17 Accessing Firestore Native

This is the **Java server SDK**, suitable for Cloud Run/GKE/Compute Engine, **not a Firebase mobile client**. It uses the **runtime principal's ADC** and is governed by IAM.

### 10.1. Maven dependencies

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>firestore-mode-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
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
</project>
~~~

The BOM version is an **example that must be pinned and compatibility-checked**, not a claim that it is the latest; replace it with a version tested in CI and review advisories before upgrading.

### 10.2. Java creating and querying a document

Place in `src/main/java/com/example/FirestoreOrdersDemo.java`:

~~~java
package com.example;

import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.FieldValue;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import com.google.cloud.firestore.QueryDocumentSnapshot;
import java.util.List;
import java.util.Map;

public final class FirestoreOrdersDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: FirestoreOrdersDemo PROJECT_ID DATABASE_ID");
        }

        String projectId = args[0];
        String databaseId = args[1];

        try (Firestore db = FirestoreOptions.newBuilder()
                .setProjectId(projectId)
                .setDatabaseId(databaseId)
                .build()
                .getService()) {

            DocumentReference orderRef =
                db.collection("orders").document("order-lab-001");

            Map<String, Object> order = Map.of(
                "ownerUid", "demo-user",
                "tenantId", "shop-a",
                "status", "CREATED",
                "amountMinor", 129900L,
                "createdAt", FieldValue.serverTimestamp());

            // create() fails if the document already exists; run only once
            // or use a different test ID in the sandbox.
            orderRef.create(order).get();

            List<QueryDocumentSnapshot> found = db.collection("orders")
                .whereEqualTo("tenantId", "shop-a")
                .whereEqualTo("status", "CREATED")
                .get()
                .getDocuments();

            for (QueryDocumentSnapshot doc : found) {
                System.out.println(doc.getId()
                    + " => " + doc.getString("status"));
            }
        }
    }
}
~~~

**Notes:**

- `setDatabaseId(...)` is critical when using a **named database**, because the SDK defaults to `(default)`.
- `create()` does not overwrite an existing document; re-running may throw `ALREADY_EXISTS`, which is expected demo behavior. In production, choose an appropriate idempotency key and write strategy.
- Adding a sort on `createdAt` to a query combining filters in Standard may require a **composite index**.
- `FieldValue.serverTimestamp()` is a timestamp assigned by the Firestore server.
- **The Java server client bypasses Firestore Security Rules**, so the runtime service account needs appropriate IAM permissions, such as data access permissions from `roles/datastore.user` when needed. Use a dedicated service account and avoid granting Owner/Editor.
- **Never commit service account JSON keys into the Maven repo.** On Cloud Run/GKE, use the runtime identity; on a laptop, sign in to ADC via your organization's approved workflow.

### 10.3. If the backend still uses the Datastore API

Do not switch to `FirestoreOptions` on a Datastore-mode database. Another SDK illustration:

~~~java
import com.google.cloud.datastore.Datastore;
import com.google.cloud.datastore.DatastoreOptions;
import com.google.cloud.datastore.Entity;
import com.google.cloud.datastore.Key;

// Dependency: com.google.cloud:google-cloud-datastore
Datastore datastore = DatastoreOptions.newBuilder()
    .setProjectId("PROJECT_ID")
    .build()
    .getService();

Key key = datastore.newKeyFactory()
    .setKind("Order")
    .newKey("order-lab-001");

Entity orderEntity = Entity.newBuilder(key)
    .set("status", "CREATED")
    .set("tenantId", "shop-a")
    .build();

datastore.put(orderEntity); // Creates/updates a real entity if executed.
~~~

This is an **illustrative Java snippet**, not a standalone compilable program. `DatastoreOptions`/`Entity`/`Key` reflect the Datastore model. If a project has multiple databases, you must configure the target database according to actual SDK capabilities and project architecture; do not assume the Datastore client always picks the right named database.

## 11. Indexes, Scaling, Consistency, and Data Modeling

### 11.1. Never run arbitrary queries without measuring cost

| Issue | Standard Native | Enterprise Native |
|---|---|---|
| Complex query missing an index | May fail reporting a missing index | May run via a very expensive scan |
| Indexes on rarely used fields | Usually has automatic single-field indexes | Not created automatically, reducing write/index overhead if well managed |
| Frequent queries | Create composite indexes when requested | Create indexes intentionally based on explain/insights |
| Changing query code | May require deploying indexes first | May run immediately, but performance/cost changes |

Orders API scenario: querying by `tenantId` and `status` scales with document count. If there are 100,000 orders and only 50 need to be shown, you need an appropriate **index/query plan**. Never pull the entire collection into Java to filter; doing so increases reads and risks leaking cross-tenant data.

### 11.2. Avoiding hotspots

- **Do not** use sequential document IDs like `order-000001`, `order-000002` at high write rates; prefer auto-IDs/random IDs or controlled distributed keys.
- Avoid concentrating heavy writes onto **a single counter document**; consider distributed counters/aggregation.
- With indexed monotonically increasing timestamps at high write rates, consult best practices on **index exemptions, traffic ramp-up, and 500/50/5 guidance** for your edition/volume; do not assume a fixed throughput cap for every database.
- Do not turn a single document into an unbounded list of all order lines; watch the 1 MiB Native limit and write contention.
- Data modeling should start from **query patterns**, not by copying a multi-JOIN PostgreSQL ERD verbatim.

### 11.3. Consistency and transactions

Firestore provides **strongly consistent queries** and supports API transactions/batched writes. However:

- Transactions have specific retry, size/time limit, and collision behaviors.
- Do not assume relational constraints or foreign keys.
- Offline client writes and listener UIs can show local state before server confirmation; applications must handle pending writes/conflicts.
- Financial/inventory data requires idempotency and invariant design, not merely relying on using a NoSQL database.

If a business workflow requires heavy cross-table joins, long transactions, and SQL constraints, **Cloud SQL/AlloyDB** may be a better fit than Firestore.

## 12. Migration Between Modes/Editions: A Separate Project, Not an Arbitrary Flag Change

### 12.1. When is migration needed?

- Legacy App Engine Datastore preparing to launch realtime mobile features.
- A Standard Native workload needing Enterprise Core/Pipeline.
- A MongoDB application evaluating Firestore with MongoDB compatibility.
- Needing to change location or separate data residency into another project.

**Do not assume** you can simply toggle `--edition` or `--type` on a database with data. The safe option is to **create a target database**, migrate data/configuration, verify, and cut over with rollback. For Standard Native → Enterprise Native, documentation guides toward **Firestore import/export or Dataflow Firestore-to-Firestore**.

### 12.2. Migration runbook

~~~mermaid
flowchart TD
    Plan["Inventory APIs, data model,<br/>indexes, rules, IAM, costs"]
    New["Create target database<br/>edition/mode/location"]
    Copy["Export/import or<br/>transformation pipeline"]
    Validate["Compare data, queries,<br/>transactions, and performance"]
    Cut["Cut over client traffic<br/>and observe"]
    Rollback["Rollback plan and<br/>cleanly stop dual-write"]
    Plan --> New --> Copy --> Validate --> Cut --> Rollback
~~~

1. **Inventory** SDKs/APIs, schema, documents/entities, indexes, security rules, IAM, TTL, backups/PITR, triggers, and integrations.
2. **Choose edition/mode/region** for the target database; verify `(default)` database and App Engine constraints.
3. **Transfer data** via export/import or Dataflow where a suitable workflow exists; for Datastore → Native or Mongo compatibility, map out **data model and API differences** separately.
4. **Rebuild configuration**: indexes, Rules, IAM, TTL, backups, PITR, CMEK, metrics/triggers. Dataflow migration **does not automatically transfer all configuration**.
5. **Verify functionality**: document counts, references, timestamps, nulls, queries, transactions, security tests, p95/p99, and billing.
6. **Manage writes during copy**: choose a maintenance window, or idempotent CDC/dual-write if needed; a single export does not guarantee a consistent snapshot across ongoing writes.
7. **Cut over** SDKs to the exact database ID; monitor errors/lag/cost; keep a clear rollback path and do not delete the source immediately.
8. **Clean up** once production stability is verified and retention/compliance approvals are obtained.

**An easy detail to miss:** Firebase/client SDKs may **default to `(default)`**. After migrating to a named database, update client configuration and security rules for the **target database**, otherwise the app may keep reading/writing the old DB.

## 13. Location, Billing, and Operations

### 13.1. Location is a hard-to-change decision

Firestore supports **regional** and **multi-region** locations within published edition/location availability. Choose based on:

- **Data residency** and regulatory requirements.
- **Latency** between applications and the database, especially the Cloud Run/GKE region.
- **Availability/durability** and regional fault tolerance.
- **Operation/storage/network egress costs** per location.
- Co-location with other services, such as Cloud Functions/Eventarc/BigQuery exports.

**Once a database is created, its location cannot be changed directly.** For the `(default)` database, location may be constrained by the project/Firebase/App Engine **default Google Cloud resource location** set earlier. Do not accept the console default without checking requirements.

### 13.2. Conceptual billing comparison

| Factor | Standard | Enterprise |
|---|---|---|
| Data operations | Typically counts document reads/writes/deletes and index-entry reads where applicable | Charges read/write units based on **bytes processed** |
| Indexing | Automatic index storage/write overhead | Indexing is an explicit choice; scans can consume many reads |
| Storage | Charged by storage volume/snapshots per configuration | Charged by storage volume and related features |
| Network egress | May apply | May apply |
| Realtime listeners | Can increase read counts as data changes | Core operations also require measuring reads/bytes and config |
| Free tier | Per limits and eligible database | Per limits and eligible database |

For example, suppose an app opens a page listing 20 orders per view, and each user refreshes 50 times/day; 10,000 users/day generates substantial reads even if documents are small. On Enterprise, **unindexed queries scanning large datasets** can produce a markedly different bill than Standard. Use **Cloud Billing Reports, Pricing Calculator, Query Explain/Insights**, and sample traffic—never guess pricing from the edition name.

### 13.3. Operational fundamentals

- Use **IAM least privilege** for Java servers and Firebase Security Rules for mobile/web.
- Enable **delete protection**, backups, PITR, and retention aligned with RPO/RTO needs.
- Monitor **latency, error rate, reads/writes, index/storage, query scans, and quotas**.
- Verify **Firestore index/Rules deployment** in CI/CD before deploying code.
- Protect Cloud Functions/Eventarc triggers against retries causing duplicate side effects.
- Separate Firestore document reads from static assets/files stored in Cloud Storage.
- Verify recoverability and billing of **named databases** independently.

## 14. Common Troubleshooting

| Symptom | Possible cause | Check steps |
|---|---|---|
| Java SDK returns `NOT_FOUND` for a document visible in UI | Java points to `(default)` instead of the named database | `setDatabaseId`, project ID, and path |
| Mobile SDK gets `PERMISSION_DENIED` | Firestore Security Rules / Firebase Auth mismatch | Rules, user token, query constraints |
| Java SDK accesses data despite deny-all Rules | Server SDK uses **IAM**, bypassing Rules | Runtime service account/IAM policy |
| Java server gets `PERMISSION_DENIED` | Missing Firestore IAM data permissions | ADC principal and `roles/datastore.user` or custom role |
| Standard Native query demands an index | Missing composite index | Create the suggested index and wait for build |
| Enterprise query runs slowly | Query scans many documents due to missing index | Query Explain/Insights, create index |
| Datastore SDK lacks realtime listeners | Datastore mode does not support Firebase Native API | Keep Datastore or plan migration |
| Mongo driver fails to connect | Misconfigured TLS/loadBalanced/retryWrites/OIDC driver | Official URI, driver support/config |
| Two clients in the same project see different results | Using different database IDs/modes | Project + database ID + SDK type |
| New data hits hotspots | Sequential IDs/single document or indexed timestamp | Document IDs, write workload, index exemptions |
| Data migration missing indexes | Export/import/Dataflow did not carry all config | Recreate indexes/Rules/TTL/backup settings at target |
| Billing spikes after switching to Enterprise | Scans, byte-based units, storage, or traffic | Query Explain and Billing Reports |
| DB created in wrong region | Location is immutable after creation | Create another DB, migrate, and cut over |
| Firebase console shows Rules but Java still has full access | Confused trust boundaries | Test client Rules, audit server IAM |

### 14.1. Three-step runbook to isolate which layer is failing

1. **Right DB?** Check project ID, database ID, edition/mode, location, and Java client target.
2. **Right identity?** For Firebase mobile/web: token + Rules; for Java server: ADC/IAM; for Mongo: authentication mechanism + supported driver.
3. **Right query/index?** Check fields/collection, required indexes, query plan, tenant data, and quotas. Only then tune SDK/retries/capacity.

Never "fix" `PERMISSION_DENIED` by opening Rules to `allow read, write: if true` or granting project Owner.

## 15. Case Study: Omnichannel Retail Application

**Hypothetical scenario:** RetailOne has:

- A mobile app displaying realtime order status and caching offline.
- A **Java Orders API** on Cloud Run managing orders and authorization.
- A legacy App Engine service using Datastore `Customer` entities.
- Another team testing the Java MongoDB driver for a product recommendation system.
- Millions of documents, flash-sale traffic, and strict cost controls.

### 15.1. Decisions by workload

| Workload | Recommended edition/mode | Why |
|---|---|---|
| Mobile order tracking | **Standard + Native** | Realtime/offline Firebase SDK |
| Java Orders API | **Standard + Native** (same DB as mobile if sharing data contract) | Java server SDK + IAM, business logic control |
| Legacy App Engine Datastore | **Standard + Datastore** within its scope | Preserves Datastore API until migration is ready |
| Java Mongo-compatible recommendation service | **Enterprise + MongoDB compatibility** for POC | Validate MQL/driver compatibility and byte-based billing |
| Historical analytics/reporting | **BigQuery** via appropriate pipeline | Avoid using Firestore as the primary OLAP store |

**Do not cram all data into one database just to use a single SDK.** A single Google Cloud project can host multiple databases, provided default/named DBs and network/IAM/rules are managed cleanly; some workloads should use a completely different database service as required.

### 15.2. Securing order data

~~~mermaid
flowchart LR
    User["Firebase mobile user"]
    Auth["Firebase Auth + Rules"]
    F["Firestore Native orders"]
    Java["Cloud Run Java Orders API"]
    IAM["Java runtime SA + IAM"]
    Legacy["Legacy App Engine"]
    DS["Firestore Datastore mode"]
    User --> Auth --> F
    Java --> IAM --> F
    Legacy --> DS
~~~

- Mobile only reads orders for the verified `ownerUid` and cannot set `status=PAID` directly.
- Java Orders API verifies user JWT/tenant, executes transaction logic, and updates Firestore.
- Java runtime uses a **user-managed service account** with least-privilege IAM; Rules **do not** restrict the server SDK.
- Legacy App Engine keeps Datastore data isolated until a tested migration is ready.
- The MongoDB workload must measure support/query cost; **do not swap out the original API overnight**.

### 15.3. Verification plan

1. Measure **p95 latency**, query reads, index scans, and write throughput under representative traffic.
2. Measure listeners across concurrent users and reconnect effects.
3. Run Rule tests with the Firebase Emulator: user A cannot read user B's orders.
4. Audit Java IAM: verify the exact service account and ensure no overly broad read permissions.
5. Benchmark Standard Native vs Enterprise Native if queries genuinely require upgrading.
6. POC the MongoDB driver with CRUD/MQL/transaction tests and measure actual billing.
7. Verify backups/PITR, location, indexes, and data transfer costs.
8. Choose cutover/rollback procedures based on data contracts, not product labels.

## 16. Exercises and Self-Assessment

### Exercise 1 — The two axes: mode and edition

An engineer says: "Firestore Enterprise is just MongoDB mode; Native only exists in Standard."

**Question:** Where is this statement wrong? List all four primary supported edition/mode combinations.

**Hint:** Enterprise also has Native Core/Pipeline; Standard has Native and Datastore.

### Exercise 2 — Realtime chat application

A mobile/web app needs realtime messaging and offline caching; a Java server moderates content.

**Question:** Which mode/edition do you choose first? Which authorization mechanisms do the two client groups use?

**Hint:** Native; Firebase Authentication/Rules for the app, IAM/domain validation for the Java server.

### Exercise 3 — Legacy App Engine

An App Engine Java service has used `Datastore`/`Entity` for years. The team wants Firebase listeners simply by importing the Firestore SDK.

**Question:** Can they keep the Datastore-mode database and just swap the SDK?

**Hint:** No; they must evaluate a database model/API migration, not just a dependency change.

### Exercise 4 — Missing index on Enterprise

A Standard Native query fails due to a missing composite index. After moving the same query to Enterprise Native, it runs, but p99 spikes severalfold.

**Question:** Why? What should you inspect to fix it?

**Hint:** Enterprise can execute scans because indexes are optional; use Query Explain and create intentional indexes.

### Exercise 5 — Java access vs Rules

Rules are set to `allow read: if false`, yet the Java server still reads all data.

**Question:** Is this a Rules bug? Which layer must you control?

**Hint:** The server Java SDK bypasses Rules and relies on runtime IAM and app authorization.

### Exercise 6 — Named database

The project has `(default)` and `orders-native-lab`. The Java code uses `FirestoreOptions.getDefaultInstance().getService()` and cannot see newly written orders.

**Question:** Which option must be set? How do you verify the actual resource?

**Hint:** `setDatabaseId("orders-native-lab")` and the right project, verified with `gcloud firestore databases describe`.

### Exercise 7 — MongoDB-compatible Java

An app uses MongoDB Java driver 5.x and heavy aggregations. The team wants to move to Firestore Enterprise MongoDB compatibility.

**Question:** What must be verified before moving to production?

**Hint:** Supported MQL/operators, driver/OIDC, TLS/load-balanced, retryable writes, indexes, latency/cost, and rollback.

### Exercise 8 — Choosing a database for complex relationships

An accounting system has many related tables, long transactions, foreign keys, and JOINs.

**Question:** Why should you not default to Firestore? Which GCP candidates fit better?

**Hint:** Cloud SQL or AlloyDB for suitable relational/transactional workloads.

### Exercise 9 — Location and cost

A team created a database in a region far from users, storing large datasets with many scanning queries. Later they want to "change region" with a single setting.

**Question:** Can it be changed directly? What must be done, and which costs should be measured?

**Hint:** Location is immutable; create a target DB, migrate, verify, and cut over; monitor read/write units, egress, storage, and indexes.

### Exercise 10 — Integration design

Build a decision matrix for a Java Orders API, a Firebase mobile app, and a legacy Datastore app. For each workload state:

- Edition/mode and API/SDK;
- Document/entity data model, index/query access patterns;
- Firebase Security Rules or IAM;
- Region, realtime/offline, consistency;
- Cost, scaling, backups, and migration strategy.

**Hint:** Do not force legacy Datastore onto the Native SDK, and do not rely on Firebase Rules to protect the Java server.

## 17. Production Checklist

- [ ] Identified **edition** and **data access mode** separately, not mistaking Enterprise for Mongo-only.
- [ ] Chose Native for new apps needing Firebase mobile/web SDKs; Datastore only when legacy API dependencies exist.
- [ ] For Mongo compatibility, tested supported commands, drivers, auth, TLS, indexes, and retry semantics.
- [ ] Verified database ID, `(default)` vs named database, project, and location.
- [ ] Selected region/multi-region based on latency, data residency, availability, and cost.
- [ ] Configured Firestore Security Rules for mobile/web and tested with the emulator.
- [ ] Java server uses runtime service account + IAM, **not Security Rules**.
- [ ] No hardcoded service account keys or client secrets in the Java repository.
- [ ] Data model follows query patterns; SQL JOINs/foreign keys are not copied into Standard Native.
- [ ] Document IDs and write patterns avoid hotspots/single-document contention.
- [ ] Standard Native queries have complete indexes; Enterprise queries are checked for scans with intentional indexes created.
- [ ] Measured p95/p99, throughput, reads/writes, storage, egress, and billing for realistic traffic.
- [ ] Evaluated pricing differences between Standard document operations and Enterprise byte-based units.
- [ ] Realtime/offline expectations match the exact SDK/Core mode and feature configuration.
- [ ] Configured delete protection, backups/PITR/TTL aligned with RPO/RTO and budget.
- [ ] Migration includes data validation, indexes/Rules/IAM transfer, cutover, and rollback.
- [ ] CI/CD validates Security Rules, indexes, query changes, and database IDs.
- [ ] Monitoring/alerting covers errors, latency, quota/index/storage, and IAM changes.
- [ ] Never delete data sources or change the type of a populated database just to test features.

## 18. Official Google Cloud and Firebase Documentation

Check current documentation on editions/modes, SDKs, pricing, and limits before going to production:

- [Firestore — Editions overview](https://docs.cloud.google.com/firestore/native/docs/editions-overview)
- [Firebase — Firestore editions overview](https://firebase.google.com/docs/firestore/editions)
- [Firebase — Enterprise edition modes](https://firebase.google.com/docs/firestore/enterprise/overview-enterprise-edition-modes)
- [Firestore — Choose between Firestore APIs](https://docs.cloud.google.com/datastore/docs/firestore-or-datastore)
- [Firestore — Create and manage databases](https://docs.cloud.google.com/firestore/native/docs/manage-databases)
- [Firestore — Native vs Enterprise indexing](https://docs.cloud.google.com/firestore/native/docs/enterprise-index-overview)
- [Firestore — MongoDB compatibility](https://docs.cloud.google.com/firestore/mongodb-compatibility/docs)
- [Firestore — MongoDB connection requirements](https://docs.cloud.google.com/firestore/mongodb-compatibility/docs/connect)
- [Firestore — Supported MongoDB drivers](https://docs.cloud.google.com/firestore/mongodb-compatibility/docs/supported-data-types-drivers)
- [Firebase — Firestore Security Rules](https://firebase.google.com/docs/firestore/security/get-started)
- [Firebase — Test Security Rules with Emulator](https://firebase.google.com/docs/firestore/security/test-rules-emulator)
- [Firebase — SDKs and client libraries](https://firebase.google.com/docs/firestore/client/libraries)
- [Firestore — Location selection](https://docs.cloud.google.com/firestore/native/docs/locations)
- [Firestore — Best practices](https://docs.cloud.google.com/firestore/native/docs/best-practices)
- [Firestore — Migrate Standard to Enterprise](https://docs.cloud.google.com/firestore/native/docs/migrate-standard-to-enterprise)
- [Firestore — Export/import data](https://docs.cloud.google.com/firestore/native/docs/manage-data/export-import)
- [Firestore Java — FirestoreOptions.Builder](https://docs.cloud.google.com/java/docs/reference/google-cloud-firestore/latest/com.google.cloud.firestore.FirestoreOptions.Builder)

**Key takeaway:** **Mode determines the API/SDK and how applications access data; edition also determines the query engine, indexing, and billing model.** For new systems needing Firebase realtime/offline, typically start with **Standard + Native**. Keep **Datastore mode** for legacy APIs; evaluate **Enterprise + Native** when advanced querying is needed and **Enterprise + MongoDB compatibility** when MongoDB driver dependencies exist. Whichever combination you choose, verify **database ID, Firebase Rules vs IAM permissions, query/index costs, location, and migration plans** before release.
