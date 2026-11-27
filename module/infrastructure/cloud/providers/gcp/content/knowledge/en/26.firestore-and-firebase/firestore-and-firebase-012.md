# Hands-On Java Backend Using Firestore and the Firebase Admin SDK

The Orders app provides a web/mobile UI for customers to view and place orders. Firebase Authentication authenticates users, a **Spring Boot Java backend** verifies ID tokens, and **Cloud Firestore** stores orders and inventory. This keeps sensitive business logic on the server, leverages a managed document database, and deploys cleanly to Cloud Run or GKE without operating database servers.

This lesson belongs to the **Firestore and Firebase** chapter of the `CLOUD_PROVIDERS_GCP` module, connecting projects, IAM/VPC, Cloud Run, GKE, data security, deployment, and cost monitoring. We will build a compact API featuring **authentication, owner-scoped order reads, idempotent order transactions**, and testing via the Firebase Emulator Suite.

> All projects, UIDs, URLs, and orders below are test data only. The Firebase Admin SDK holds **server-side** privileges—never embed it in web/mobile apps or ship service account keys to clients. Commands that create resources, deploy, or write to Firestore can incur charges; run them only in an authorized sandbox.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the Firebase client SDK, Firebase Admin SDK, and Google Cloud Firestore server client.
2. Initialize the Admin SDK using **Application Default Credentials (ADC)**, using `FirestoreClient` and `FirebaseAuth` under a Firebase project.
3. Verify **Firebase Authentication ID tokens** on the backend and enforce per-`uid` authorization.
4. Write Java APIs to read and create documents, atomically update inventory in transactions, and handle retries/idempotency.
5. Filter/paginate data, understand composite indexes, and apply document design principles.
6. Test with the **Firestore/Auth emulators**, distinguishing client Security Rules tests from server IAM.
7. Deploy to Cloud Run with a least-privilege service account, monitor errors/latency, and control cost.

## 2. Architecture and Trust Boundaries

```mermaid
flowchart LR
  WEB["Web / Mobile client"] -->|"Sign in"| AUTH["Firebase Authentication"]
  AUTH -->|"Firebase ID token"| WEB
  WEB -->|"HTTPS + Bearer Firebase ID token"| API["Spring Boot API<br/>Cloud Run / GKE"]
  API -->|"FirebaseAuth.verifyIdToken"| AUTH
  API -->|"Admin SDK / Firestore server API<br/>IAM service account"| DB["Cloud Firestore<br/>orders, inventory"]
  WEB -.->|"Optional direct client SDK<br/>Security Rules"| DB
  API --> OBS["Cloud Logging / Monitoring"]
```

| Component | Which SDK/credential? | Scope of control |
| --- | --- | --- |
| Web/mobile | Firebase Authentication client SDK; Firestore client SDK if accessing directly | User ID token, **Firestore Security Rules** for direct access |
| Java backend | Firebase Admin Java SDK + Firestore server client, ADC/Workload Identity | **Google Cloud IAM** for server identity; backend-enforced authorization |
| Firebase Auth | Issues and verifies user identities | Token is **proof of identity**, not automatic permission to read every document |
| Firestore | Document/collection database | Atomic transactions, indexes, TTL, and storage |
| Cloud Run/GKE | Service/workload identity and networking | Never bake static JSON keys into containers |

**Core rule:** Firestore **server client libraries and the Firebase Admin SDK bypass Firestore Security Rules** and are governed by **IAM**. Therefore, Security Rules like `request.auth.uid == resource.data.ownerUid` do not protect a Java endpoint using the Admin SDK. The backend must verify tokens, owners, roles, tenants, and fields for every operation itself. <https://firebase.google.com/docs/firestore/security/test-rules-emulator>

### 2.1. Distinguishing three token types

| Token | Issued by | Purpose |
| --- | --- | --- |
| **Firebase ID token** | Firebase Authentication after client sign-in | Client sends in `Authorization: Bearer ...`; Java verifies with `FirebaseAuth.verifyIdToken` |
| **Firebase custom token** | Server Admin SDK | Client uses it to **sign in to Firebase Auth**, never sent directly as an API Bearer ID token |
| **Google-signed ID token for Cloud Run IAM** | Google identity/Service Account | Protects Cloud Run via `roles/run.invoker`; **different from a Firebase ID token** |

If a backend serves web/mobile users over a public Cloud Run URL, it typically allows requests to reach the **HTTP ingress layer** per policy and requires a **Firebase ID token + business authorization inside the app**; this does not mean an "unsecured API." If Cloud Run is locked down as IAM-private, callers need a **Google-signed ID token** for the Cloud Run layer, which a Firebase ID token alone cannot satisfy. Choose the right ingress, API Gateway/LB/WAF, and App Check architecture for your threat model.

## 3. Preparing the Firebase Project and Firestore

Example setup:

| Component | Illustrative value |
| --- | --- |
| Google Cloud/Firebase project ID | `orders-lab` |
| Firestore database | `(default)`, **Native mode / Standard edition** |
| Region | Close to the app, chosen at database creation |
| Firebase Auth sign-in | Email/password in **sandbox** |
| Backend | Java 21, Spring Boot 3.5.x, Firebase Admin Java 9.12.0 |
| Collections | `inventory/{sku}` and `orders/{orderId}` |

**Before writing code:**

1. Create/select the **same Google Cloud project** and add Firebase to it if not already enabled.
2. Enable Firebase Authentication and a sign-in provider (e.g., Email/Password) in the Firebase console; create test accounts only.
3. Create a Cloud Firestore **Native mode** database in an appropriate region. Region/multi-region, edition, and database ID affect APIs, latency, and cost; never change them casually once the app holds data.
4. In Google Cloud, enable required APIs and create a **runtime service account** with appropriately scoped Firestore read/write permissions.
5. Install JDK 21, Maven or Maven Wrapper, `gcloud` CLI, and Firebase CLI for emulators. The Java server Admin SDK does not need a Firebase client configuration API key.

Read-only verification commands:

```bash
PROJECT_ID="orders-lab"
gcloud config get-value project
gcloud firestore databases list --project="$PROJECT_ID"
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="config.name:firestore.googleapis.com"
```

On Cloud Run, **ADC automatically picks up the runtime service account's identity** without exporting `GOOGLE_APPLICATION_CREDENTIALS`. On a dev laptop, use `gcloud auth application-default login` when calling sandbox Firestore or use the Emulator Suite; for the Firebase Auth Admin SDK, user ADC has specific constraints and may require a matching OAuth client ID. Never download a static service account private key just to "make it work."

## 4. Maven Project and Initializing the Firebase Admin SDK

Example application structure:

```text
orders-backend/
  pom.xml
  src/main/java/com/example/orders/
    OrdersApplication.java
    FirebaseConfiguration.java
    OrdersController.java
  src/main/resources/application.properties
  Dockerfile                       # optional when deploying to Cloud Run
```

### 4.1. Dependency configuration

Minimal `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>orders-backend</artifactId>
  <version>1.0.0</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>com.google.firebase</groupId>
      <artifactId>firebase-admin</artifactId>
      <version>9.12.0</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

At the time of writing, Firebase Admin Java **9.12.0 (11/2026)** supports App Check verification in Java; this illustrative version was verified from the [release notes](https://firebase.google.com/support/release-notes/admin/java). In production, apply patches and scan dependencies, avoiding incompatible BOM/dependency overrides. The Firebase Admin SDK already brings in `com.google.cloud.firestore.*` Java classes; do not add a second Firestore dependency for this basic example.

### 4.2. `FirebaseConfiguration.java`

```java
package com.example.orders;

import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.firestore.Firestore;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.cloud.FirestoreClient;
import java.io.IOException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FirebaseConfiguration {
  @Bean(destroyMethod = "delete")
  FirebaseApp firebaseApp(@Value("${app.firebase.project-id}") String projectId)
      throws IOException {
    FirebaseOptions options = FirebaseOptions.builder()
        .setCredentials(GoogleCredentials.getApplicationDefault())
        .setProjectId(projectId)
        .build();
    return FirebaseApp.initializeApp(options);
  }

  @Bean
  FirebaseAuth firebaseAuth(FirebaseApp app) {
    return FirebaseAuth.getInstance(app);
  }

  @Bean
  Firestore firestore(FirebaseApp app) {
    return FirestoreClient.getFirestore(app);
  }
}
```

**Initialize once per JVM lifecycle.** This code assumes a single Spring application owns the default `FirebaseApp`; if tests or multiple contexts initialize multiple apps in one JVM, use distinct app names or controlled cleanup—never call `initializeApp` per request. `FirestoreClient.getFirestore(app)` returns the shared Firestore instance bound to that app.

### 4.3. `OrdersApplication.java` and `application.properties`

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
  public static void main(String[] args) {
    SpringApplication.run(OrdersApplication.class, args);
  }
}
```

```properties
app.firebase.project-id=${GOOGLE_CLOUD_PROJECT:demo-orders}
server.address=0.0.0.0
server.port=${PORT:8080}
```

**Never let `demo-orders` become the production project because of a forgotten environment variable.** In real deployments, require `GOOGLE_CLOUD_PROJECT` to match your Firebase Auth/Firestore project and verify deployed values. For a named database other than `(default)`, use the `FirestoreClient.getFirestore(app, databaseId)` overload and keep IAM/app config aligned.

## 5. Verifying Firebase ID Tokens and Checking Ownership

After signing in with the **Firebase Authentication client SDK**, the frontend retrieves an ID token via `currentUser.getIdToken()` and sends it on every HTTPS request:

```http
GET /api/orders/EXAMPLE_ORDER_ID HTTP/1.1
Host: api.example.com
Authorization: Bearer FIREBASE_ID_TOKEN_FROM_CLIENT
```

The backend calls `FirebaseAuth.verifyIdToken(token)` to check **signature, expiration, and Firebase project/audience**, then extracts `uid` from the verified token. **Never use `ownerUid` from query params or body to make access decisions.** A Firebase ID token can be revoked or disabled before expiry: `verifyIdToken(token, true)` checks revocation/disabled status at the cost of an extra network call and latency; choose policies per endpoint sensitivity.

Scenarios that must be rejected:

| Request | Expected outcome |
| --- | --- |
| Missing Bearer token or invalid/expired token | `401 Unauthorized` |
| Valid Firebase token from a **different project** | `401` due to failed verification |
| User A reads user B's order | `404` or `403` per non-disclosure policy |
| Valid UID lacking admin rights to view others' data | `403`; never rely solely on "user is logged in" |
| Google Cloud service-account token passed as a Firebase token | Rejected by `verifyIdToken` |

In multi-endpoint apps, use a **Spring Security filter/interceptor** to verify tokens and populate `SecurityContext` instead of duplicating auth checks in every controller. The sample below uses a small helper for clarity—it is **not a complete security framework**.

## 6. Java Backend: Atomic Order Creation, Idempotency, and Reads

Sample document model:

```text
inventory/
  sku-001
    available: 100

orders/
  <idempotencyKey>
    ownerUid: "<Verified Firebase UID>"
    sku: "sku-001"
    quantity: 2
    status: "CREATED"
    createdAt: <server timestamp>
```

To keep the example simple while supporting retries, the client sends a unique random **Idempotency-Key** (e.g., a UUID v4 without hyphens works cleanly), reusing the same key when retrying an operation. The backend uses that key as the document ID and **within one transaction** reads any existing order, reads inventory, deducts stock, and creates the order. In large multi-tenant systems, derive the document key from **`hash(uid + operationId)`** to prevent cross-user ID collisions or guessing; the lab example checks `ownerUid` and request fields before returning an existing order.

### 6.1. `OrdersController.java`

```java
package com.example.orders;

import com.google.cloud.firestore.*;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseAuthException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {
  private final Firestore db;
  private final FirebaseAuth auth;

  public OrdersController(Firestore db, FirebaseAuth auth) {
    this.db = db;
    this.auth = auth;
  }

  public record CreateOrder(String sku, long quantity) {}

  private String requireUid(String authorization) {
    if (authorization == null || !authorization.startsWith("Bearer ")) {
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }
    try {
      String token = authorization.substring("Bearer ".length());
      return auth.verifyIdToken(token).getUid();
    } catch (FirebaseAuthException ex) {
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
          "Invalid Firebase ID token");
    }
  }

  @PostMapping
  public ResponseEntity<Map<String, Object>> create(
      @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false)
          String authorization,
      @RequestHeader("Idempotency-Key") String operationId,
      @RequestBody CreateOrder request) throws Exception {

    String uid = requireUid(authorization);
    if (!operationId.matches("[A-Za-z0-9_-]{8,64}")
        || request.sku() == null
        || !request.sku().matches("[A-Za-z0-9_-]{1,40}")
        || request.quantity() <= 0 || request.quantity() > 100) {
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
    }

    DocumentReference orderRef =
        db.collection("orders").document(operationId);
    DocumentReference stockRef =
        db.collection("inventory").document(request.sku());

    String orderId;
    try {
      orderId = db.runTransaction(tx -> {
        // ALL reads must occur before writes in a Firestore transaction.
        DocumentSnapshot old = tx.get(orderRef).get();
        if (old.exists()) {
          if (!uid.equals(old.getString("ownerUid"))
              || !request.sku().equals(old.getString("sku"))
              || !Objects.equals(request.quantity(), old.getLong("quantity"))) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "Idempotency key already used");
          }
          return orderRef.getId();
        }

        DocumentSnapshot stock = tx.get(stockRef).get();
        Long available = stock.getLong("available");
        if (available == null || available < request.quantity()) {
          throw new ResponseStatusException(HttpStatus.CONFLICT,
              "Insufficient stock");
        }

        tx.update(stockRef, "available", available - request.quantity());
        Map<String, Object> order = new HashMap<>();
        order.put("ownerUid", uid);
        order.put("sku", request.sku());
        order.put("quantity", request.quantity());
        order.put("status", "CREATED");
        order.put("createdAt", FieldValue.serverTimestamp());
        tx.create(orderRef, order);
        return orderRef.getId();
      }).get(20, TimeUnit.SECONDS);
    } catch (java.util.concurrent.ExecutionException ex) {
      // ApiFuture.get() wraps business exceptions thrown from the transaction callback.
      // Avoid turning a 409 into a 500 due to the Future wrapper.
      if (ex.getCause() instanceof ResponseStatusException businessError) {
        throw businessError;
      }
      throw ex; // Production: ControllerAdvice classifies Firestore errors.
    }

    return ResponseEntity.status(HttpStatus.CREATED)
        .body(Map.of("id", orderId, "status", "CREATED"));
  }

  @GetMapping("/{orderId}")
  public ResponseEntity<Map<String, Object>> get(
      @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false)
          String authorization,
      @PathVariable String orderId) throws Exception {

    String uid = requireUid(authorization);
    if (!orderId.matches("[A-Za-z0-9_-]{8,64}")) {
      throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
    DocumentSnapshot doc =
        db.collection("orders").document(orderId)
          .get().get(10, TimeUnit.SECONDS);

    // Do not reveal the existence of someone else's order.
    if (!doc.exists() || !uid.equals(doc.getString("ownerUid"))) {
      throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
    return ResponseEntity.ok(Map.of(
        "id", doc.getId(),
        "sku", doc.getString("sku"),
        "quantity", doc.getLong("quantity"),
        "status", doc.getString("status")));
  }
}
```

### 6.2. Why does this pattern prevent double stock deduction on callback retries?

**A Firestore transaction can re-run its callback** if a read document was modified by another transaction. By reading both **`orderRef` and `stockRef` before writing**, a retried request with the same operation ID—or a contending transaction—re-evaluates current state instead of deducting stock again against stale numbers.

| Test | Expected |
| --- | --- |
| Two requests with distinct `operationId`s buying the last SKU | Only one transaction with enough stock commits; the other fails with 409 |
| Resending the same `operationId` and payload | Returns the same order ID; stock does not decrement a second time |
| Same `operationId` with changed SKU/quantity/user | Reports conflict; does not leak data or create a new order |
| Expired token or UID mismatch on document | 401 or 404; never returns another user's data |
| Firestore timeout after commit followed by client retry with same key | Returns the already-created order without overwriting inventory |

**Never call payment APIs, publish to Pub/Sub, or send emails inside a transaction callback**: the callback may run multiple times even though only one final transaction commits. For multi-service workflows, write an **outbox event** inside the same transaction and publish after commit to an idempotent consumer. Using `Idempotency-Key` directly as the document ID is illustrative only; production needs protection against key guessing/collisions, input bounds, request fingerprints, expiry, and audit logs.

### 6.3. Production error handling

This controller stays concise to focus on Firestore and Auth; it omits `@ControllerAdvice` for classifying `ExecutionException`, `TimeoutException`, `RESOURCE_EXHAUSTED`, `UNAVAILABLE`, `FAILED_PRECONDITION`, HTTP rate limits, and trace correlation. In production:

- Distinguish `400/401/403/404/409` (client/business) from `503/504` (transient backend errors).
- Never return stack traces, sensitive document bodies, or access tokens to clients.
- Never retry a raw POST with a **new `operationId`** when commit status is unknown; check the old `operationId` first.
- Set appropriate request deadlines and bound concurrency to avoid connection/transaction storms.
- Write race-condition and endpoint-authorization tests, not just happy-path tests.

## 7. Querying User Data, Pagination, and Indexes

An order list query can filter by `ownerUid` and sort descending by `createdAt`. **Always take the UID from the verified Firebase token**, never letting clients pass an arbitrary UID to read:

```java
// Inside a controller/service, given Firestore db and verified uid.
Query firstPage = db.collection("orders")
    .whereEqualTo("ownerUid", uid)
    .orderBy("createdAt", Query.Direction.DESCENDING)
    .limit(20);

QuerySnapshot first = firstPage.get().get(10, TimeUnit.SECONDS);
for (QueryDocumentSnapshot doc : first.getDocuments()) {
  // Map to a response DTO; avoid returning unnecessary raw fields.
  System.out.println(doc.getId());
}

// When at least one document is returned, fetch the next page via cursor:
if (!first.getDocuments().isEmpty()) {
  QueryDocumentSnapshot last =
      first.getDocuments().get(first.size() - 1);
  Query nextPage = firstPage.startAfter(last);
  QuerySnapshot second = nextPage.get().get(10, TimeUnit.SECONDS);
}
```

This is an **illustrative Java snippet**, not a full REST method. Combining `whereEqualTo + orderBy` may require a **composite index**; when a query fails with an index error, Firestore provides instructions to create it. Manage indexes via IaC/CI and wait for index builds before shifting traffic. `orderBy("createdAt")` only returns documents containing that field; backfill legacy records cleanly.

Avoid large `offset` pagination: Firestore may still bill reads for skipped documents. Cursor pagination with `startAfter(lastSnapshot)` is more efficient, though UIs still need to handle items shifting while paging. Always cap page size and returned fields—never load an entire collection into RAM to filter.

## 8. Running Locally with the Firebase Emulator Suite

Firebase emulators let you test **Firestore/Auth on your development machine** without touching production data. The Firestore emulator defaults to `127.0.0.1:8080` and Auth emulator to `127.0.0.1:9099`; Spring Boot runs on **port 8081** to avoid port collisions.

### 8.1. One-time setup and launch

```bash
# RUN IN THE LAB PROJECT; do not modify production files/modules.
# Install Firebase CLI per docs; run firebase init emulators once
# to select Firestore + Authentication and generate firebase.json.
firebase init emulators

# Terminal 1: emulator with a mock project ID; never use a real project.
firebase emulators:start --only firestore,auth --project demo-orders
```

In the backend terminal:

```bash
# Terminal 2: use these variables ONLY on your LOCAL MACHINE.
export GOOGLE_CLOUD_PROJECT="demo-orders"
export FIRESTORE_EMULATOR_HOST="127.0.0.1:8080"
export FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9099"
export PORT=8081

# FirebaseConfiguration still uses ADC; set up valid local ADC
# via gcloud auth application-default login if not yet present.
./mvnw -B spring-boot:run
```

`FIRESTORE_EMULATOR_HOST` must **not contain `http://`**. When `FIREBASE_AUTH_EMULATOR_HOST` is set, the Admin SDK accepts **unsigned** Auth emulator ID tokens for testing: **never set this variable in Cloud Run/GKE production**. Always keep project IDs aligned across the emulator, Admin SDK, and Firebase client. If the service fails to start due to missing ADC, configure local dev ADC—never generate a long-lived service account key just to boot the emulator.

### 8.2. Seed test inventory data

You can create `inventory/sku-001` with integer field `available=5` in the **Firestore emulator UI**, or via the emulator's local REST API:

```bash
# WRITE ONLY TO THE EMULATOR on localhost; never call production Firestore.
curl -sS -X PATCH \
  "http://127.0.0.1:8080/v1/projects/demo-orders/databases/(default)/documents/inventory/sku-001" \
  -H "Content-Type: application/json" \
  -d '{"fields":{"available":{"integerValue":"5"}}}'
```

### 8.3. Create a test Firebase user and call the backend

Use the **Authentication emulator** UI or REST API to create a mock user. REST example:

```bash
# AUTH EMULATOR ONLY; NEVER USE REAL CREDENTIALS.
curl -sS -X POST \
  "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signUp?key=demo-key" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.test","password":"demo-password-12345","returnSecureToken":true}'
```

The response includes a mock `idToken`; store it in `FIREBASE_ID_TOKEN` in your local terminal—**never print or commit tokens into docs or repositories**. Outside the emulator, obtain a real **Firebase client SDK** ID token rather than substituting `gcloud auth print-identity-token`:

```bash
# CALL LOCAL BACKEND ONLY using token from Auth emulator.
OPERATION_ID="order-demo-0001"

curl -sS -X POST "http://127.0.0.1:8081/api/orders" \
  -H "Authorization: Bearer $FIREBASE_ID_TOKEN" \
  -H "Idempotency-Key: $OPERATION_ID" \
  -H "Content-Type: application/json" \
  -d '{"sku":"sku-001","quantity":2}'

curl -sS "http://127.0.0.1:8081/api/orders/$OPERATION_ID" \
  -H "Authorization: Bearer $FIREBASE_ID_TOKEN"
```

Inspect inventory again in the emulator: `available` dropped from 5 to 3. Re-sending the **same operation ID and payload** must not reduce stock to 1. Calling with **another user's** ID token must not reveal the order. If the token is missing or `FIREBASE_AUTH_EMULATOR_HOST` does not match, the backend must return 401.

### 8.4. Firestore Security Rules vs testing the Admin SDK

If web/mobile clients read Firestore directly, you can enforce a *read only your own orders* policy:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /orders/{orderId} {
      allow read: if request.auth != null
                  && request.auth.uid == resource.data.ownerUid;
      allow write: if false;
    }
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

This policy governs **Firebase web/mobile SDKs**. To test Rules, use a client SDK or `@firebase/rules-unit-testing` with the Firestore emulator and mocked `auth.uid`. **The Admin SDK bypasses Rules even when connected to the emulator**; never conclude Security Rules are safe simply because Java server tests pass.

## 9. Cloud Run Deployment and Least-Privilege IAM

On Cloud Run, the runtime service account needs Firestore permissions (typically `roles/datastore.user` for reads/writes). That is a broad database-level data role; **it does not restrict by document `ownerUid`**. Scope permissions to the right project/database and enforce authorization in the backend; for read-only workloads, consider a read-only role.

Illustrative Bash commands (**modifies IAM and uses billable services**):

```bash
PROJECT_ID="orders-lab"
REGION="asia-southeast1"
RUNTIME_SA="orders-api@$PROJECT_ID.iam.gserviceaccount.com"

gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  cloudbuild.googleapis.com \
  --project="$PROJECT_ID"

gcloud iam service-accounts create orders-api \
  --project="$PROJECT_ID" \
  --display-name="Orders Firebase backend runtime"

# Grant Firestore read/write access to the exact runtime identity.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/datastore.user"

# MODIFIES / BILLABLE: builds and deploys from source once the project already has
# Firebase Auth, Firestore, the Maven project, and Cloud Build permissions.
gcloud run deploy orders-backend \
  --source=. \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service-account="$RUNTIME_SA" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --allow-unauthenticated
```

`--allow-unauthenticated` only permits HTTP requests to reach Cloud Run **without a Google IAM Invoker token**. The sample `/api/orders` endpoints **still require a valid Firebase ID token and verify `ownerUid`**. For systems that must avoid public ingress, configure Cloud Run as private behind an authorized Google identity caller, API Gateway, or Load Balancer—**a Firebase ID token alone never satisfies `roles/run.invoker`**. Add rate limiting, CORS allowlists, App Check, and Cloud Armor as your threat model dictates.

If the service account or APIs already exist, check before recreating or re-granting; manage resources via IaC. Cloud Run source deploys require a **build identity** with its own build/push permissions—never grant project-wide Editor just to fix build errors. Never set `FIREBASE_AUTH_EMULATOR_HOST` or `FIRESTORE_EMULATOR_HOST` in production; otherwise the backend could connect to the wrong endpoint or accept unsigned test tokens.

## 10. App Check, Custom Claims, and Business Authorization

**Firebase Authentication** proves **who** is calling; **App Check** attests requests originate from a registered app (additional abuse protection); **authorization** decides what that user can do. None replaces the others.

Firebase Admin Java **9.12.0+** supports `FirebaseAppCheck.verifyToken()` and optional **replay protection** for sensitive endpoints:

```java
// Snippet inside a Spring Boot HTTP filter:
String appCheckToken = request.getHeader("X-Firebase-AppCheck");
if (appCheckToken == null || appCheckToken.isBlank()) {
  response.sendError(401);
  return;
}
FirebaseAppCheck.getInstance(firebaseApp).verifyToken(appCheckToken);
// Continue verifying the Firebase ID token and checking business permissions.
```

This snippet **omits imports and exception handling and is not a complete filter**. When using replay protection, grant required permissions, inspect `isAlreadyConsumed()` per documentation, and request **limited-use tokens** on the client. Avoid enabling token consumption on every endpoint without evaluating latency and cost.

For admin roles, Firebase custom claims can carry `admin=true`, but only a **trusted server** may set claims; read values from the verified ID token and plan for token refresh/revocation. **Never accept `role: "admin"` from a JSON request body.** In multi-tenant systems, the backend must still verify access to the current tenant rather than checking a boolean flag alone.

## 11. Reliability, Observability, and Cost

### 11.1. Signals to monitor

| Signal | Failure mode | Remediation |
| --- | --- | --- |
| HTTP `401/403` | Invalid/expired ID token or insufficient permissions | Check Firebase project, token audience, Auth/emulator flags |
| HTTP `404` | Order missing or owned by another UID | Avoid leaking another user's document existence |
| Firestore `ABORTED` | Transactions contending on the same inventory doc | Bounded auto-retries; reduce hotspots |
| `RESOURCE_EXHAUSTED` / `UNAVAILABLE` | Quotas, traffic spikes, network/API faults | Rate limiting, backoff, and SLO monitoring |
| p95 latency & Firestore reads/writes | N+1 queries, missing indexes, or distant region | Optimize queries, pagination, and data model |
| Firestore reads/writes/index storage | Cost rises after rollout | Cap page size, avoid redundant reads, prune unused indexes |
| Cloud Run CPU/memory/concurrency | Resource contention or request thread saturation | Bound concurrency; offload async work |

Log structured fields—`requestId`, safely handled `operationId`, collection/operation name, error code, and latency; **never log Firebase ID tokens, refresh tokens, passwords, raw UIDs, or sensitive document payloads** unless policy permits. Configure alerts on error rates, p95 latency, and quotas rather than Pod counts alone.

### 11.2. Accurate cost accounting

Firestore bills for **document reads/writes/deletes, index-entry reads on applicable query types, storage, network, and enabled features**. Transactions may re-read/re-write on retries; large `offset` pagination inflates billed reads, whereas well-indexed queries reduce scanning.

- Store only fields that actually serve queries; large fields and arrays rapidly expand index and storage footprint.
- Avoid hot documents (such as one `inventory/sku-001` receiving heavy concurrent orders); evaluate reservations/sharding and verify correctness before scaling.
- Use TTL for temporary data where appropriate, keeping in mind **TTL deletes are billed** and are not instantaneous.
- For bulk updates, evaluate **BulkWriter/batches** and current limits instead of one giant transaction.
- Set per-project Billing budgets/alerts, plus quotas and rate limits to stop runaway test traffic.

**Never treat Firestore as a free cache**: every read/query can incur charges, even when returning few results, per service billing units. For complex relational joins, broad analytics, or extremely hot transactions, evaluate Cloud SQL, AlloyDB, Spanner, or BigQuery depending on requirements.

## 12. Real-World Scenario: Last Unit in Stock

Inventory holds `inventory/sku-001.available = 1`. Two legitimate users, A and B, simultaneously send `POST /api/orders` to buy one unit each.

```mermaid
sequenceDiagram
  participant A as User A
  participant B as User B
  participant API as Spring Boot
  participant DB as Firestore transaction
  A->>API: POST (operationId A, qty 1)
  B->>API: POST (operationId B, qty 1)
  API->>DB: T1 read inventory.available = 1
  API->>DB: T2 read inventory.available = 1
  DB-->>API: T1 commit: available=0 + order A
  DB-->>API: T2 conflict; rerun callback
  API->>DB: T2 re-read available=0
  DB-->>B: Order B rejected: insufficient stock
  API-->>A: Order A created
```

**Expected result:** only one order is created and stock stays non-negative. If the transaction callback had called a payment API, **the retry could charge twice**; keep payments separate using an outbox/idempotency or compensating workflow. This is why a Firestore transaction protects Firestore data **without becoming a distributed transaction across external services**.

### 12.1. Test scenarios

| Test | Condition | Passing outcome |
| --- | --- | --- |
| New order | Valid token A; sufficient stock | 201, creates order with `ownerUid=A`, stock decrements once |
| Retried request | Same token, key, and payload | Returns same order ID; stock does not decrement again |
| Key reuse | Same key with different payload or UID | 409, no unauthorized access |
| Competing requests | Two distinct keys, 1 unit left | One succeeds, one reports insufficient stock |
| User B reads A's order | Valid token B, order A's ID | 404/403, no order details leaked |
| Expired token | Invalid Bearer token | 401; zero Firestore writes |
| Firestore unavailable | Transient backend failure | Classified 503/504; same idempotency key kept on retry |
| Direct Firestore SDK client | Rules restrict reads to owner UID | Denied when reading someone else's order |

### 12.2. Production checklist beyond this sample

Real applications also need **authorization middleware**, Jakarta Bean Validation, logging/trace correlation, timeouts/rate limits, global exception handlers, automated tests, index migrations, rollbacks, monitoring, and PII governance. For payments, maintain a **payment state machine**, forbid invalid state transitions, and ensure webhooks/events are idempotent—never treat a `status="CREATED"` document as proof of completed payment.

## 13. Common Errors and Diagnostics

| Symptom | Common cause | Check steps |
| --- | --- | --- |
| `FirebaseApp with name [DEFAULT] already exists` | Admin SDK initialized multiple times in one JVM | Initialize once via Spring bean; clean up in tests |
| `Unable to determine Project ID` | ADC lacks project or env var misconfigured | Set project ID explicitly in `FirebaseOptions`; check runtime identity |
| Backend returns 401 on a real Firebase token | Wrong Firebase project, expired token, or custom/Google ID token mix-up | Check issuer/audience/SDK sign-in; align project ID |
| Emulator tokens accepted in a live environment | `FIREBASE_AUTH_EMULATOR_HOST` leaked to production | Remove variable and add a startup config guard |
| Firestore `PERMISSION_DENIED` | Runtime service account lacks data role | Verify IAM scope on project/database and ADC principal |
| Security Rules deny yet Admin SDK writes | Server SDK **bypasses rules by design** | Audit IAM, backend authorization, and API tests |
| `FAILED_PRECONDITION: index required` | Filter/order query lacks a composite index | Create index from error link/IaC; wait for build |
| Order created twice after HTTP retry | Client generated a new `operationId` after timeout | Reuse same idempotency key; check stored request fingerprint |
| Frequent `ABORTED` on inventory doc | Too many transactions contending on one document | Measure contention, throttle requests, design reservations |
| Emulator data missing | Wrong port/project ID or missing `FIRESTORE_EMULATOR_HOST` | Check env vars right before starting JVM |
| List returns fewer docs than expected | `orderBy` drops docs missing the field, or pagination/filter bug | Inspect schema/indexes, cursors, and legacy records |
| Firestore bill spikes | Unbounded queries, index entries, logs, repeated reads/retries | Query Explain/usage metrics, page limits, Billing alerts |

## 14. Practice Exercises

### Exercise A — Initialize the right identities

Explain why the Java backend uses ADC on Cloud Run while the mobile client uses the Firebase Auth client SDK. Identify three failures caused by shipping a service account JSON inside a mobile app or passing a Firebase custom token directly as an API Bearer token.

### Exercise B — Firestore Emulator

Run the Auth/Firestore emulators with `demo-orders`, seed `inventory/sku-001.available=5`, create a mock user, and call `POST /api/orders` with the emulated token. Verify the written document has the right owner. Why should you never point emulator commands at a production project?

### Exercise C — UID-based authorization

Create two users in the Auth emulator. User A places an order, and user B learns the `orderId`. Write a test proving the backend refuses to return A's order data. Explain why writing Firestore Security Rules alone is insufficient when the Java API uses the Admin SDK.

### Exercise D — Transactions and retries

Only one unit remains in stock. Simulate two concurrent POSTs with two different operation IDs. Verify only one order commits. Repeat with the same key: why does inventory not decrement twice? What happens if you send an email directly inside the transaction callback?

### Exercise E — Queries and indexes

Write a Java query filtering `ownerUid`, sorting `createdAt DESC`, and fetching 20 orders. Test removing the composite index or fetching too many rows. Explain when a composite index is required and why cursor pagination is preferred.

### Exercise F — Firebase ID token and App Check

Design a filter protecting the order endpoint: verify the Firebase ID token, reject disabled users per policy, verify App Check if present, and pass the verified principal/UID to the service. Identify which parts are **authentication**, **app attestation**, and **authorization**.

### Exercise G — Cloud Run and least privilege

Design a runtime service account holding only necessary Firestore read/write permissions; explain when a Cloud Run service with public HTTP ingress can still be secured with Firebase Auth and when Google IAM Invoker is needed instead. Name two emulator environment variables that must never be set in production.

### Exercise H — SLOs and cost

An app has 100,000 users, each opening their order list 10 times/day. Estimate document reads by page size and caching strategy; propose pagination, indexes, budget alerts, and a way to test a concurrency hotspot on one SKU. Pick up to six monitoring signals to catch regressions.

### Self-check questions

1. How do the Firebase Admin SDK for Java and the Firebase Web SDK differ in execution environment and permissions?
2. Does a backend using the Firestore server SDK enforce Firestore Security Rules?
3. How do a Firebase ID token and a custom token differ?
4. Does a valid ID token automatically grant permission to read all orders?
5. Why use a stable operation ID when a POST might be retried?
6. What constraints apply to read/write order and callback retries in a Firestore transaction?
7. When are composite indexes and cursor-based pagination required?
8. Why must Auth emulator flags never be enabled in Cloud Run production?
9. At which layers do `roles/datastore.user` and `ownerUid` enforce permissions?
10. Does App Check replace Firebase Authentication or authorization?

## 15. Checklist and Official Documentation

- [ ] Firebase project and Firestore database have the right mode, ID, region, and Billing.
- [ ] Java 21, Spring Boot, and Firebase Admin SDK versions and dependencies verified.
- [ ] Admin SDK initialized once via ADC; Cloud Run/GKE uses workload service accounts.
- [ ] Firebase ID tokens verified; UID used to enforce per-document authorization.
- [ ] Transactions keep inventory and orders atomic with stable idempotency keys.
- [ ] Queries use limits, cursors, and required indexes while avoiding hot documents.
- [ ] Auth/Firestore emulator tests cover invalid tokens, cross-user reads, retries, and concurrency.
- [ ] Client Firestore Security Rules and backend IAM/authorization tested **separately**.
- [ ] No emulator flags or static secrets in production; safe logging, SLOs, and Billing alerts enabled.

Firebase and Google Cloud documentation:

- [Firebase Admin SDK Java setup](https://firebase.google.com/docs/admin/setup)
- [Firebase Admin Java release notes](https://firebase.google.com/support/release-notes/admin/java)
- [Firestore server client quickstart](https://firebase.google.com/docs/firestore/quickstart-server)
- [FirestoreClient Java API](https://firebase.google.com/docs/reference/admin/java/reference/com/google/firebase/cloud/FirestoreClient)
- [Verify Firebase ID tokens](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Detect revoked sessions](https://firebase.google.com/docs/auth/admin/manage-sessions)
- [Firestore transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions)
- [Query data and indexes](https://firebase.google.com/docs/firestore/query-data/indexing)
- [Firestore query cursors](https://firebase.google.com/docs/firestore/query-data/query-cursors)
- [Security Rules with emulator](https://firebase.google.com/docs/firestore/security/test-rules-emulator)
- [Connect Firestore emulator](https://firebase.google.com/docs/emulator-suite/connect_firestore)
- [Connect Auth emulator](https://firebase.google.com/docs/emulator-suite/connect_auth)
- [Verify App Check tokens from backend](https://firebase.google.com/docs/app-check/custom-resource-backend)
- [Firestore server IAM](https://cloud.google.com/firestore/native/docs/security/iam)
- [Firestore best practices](https://firebase.google.com/docs/firestore/best-practices)
- [Cloud Run deploy Java from source](https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-java-service)
- [Firestore pricing](https://cloud.google.com/firestore/pricing)

**Remember:** Clients authenticate with Firebase Auth, while Java backends use the **Firebase Admin SDK/ADC** to verify ID tokens and access Firestore via IAM. Because **server SDKs bypass Security Rules**, the backend must enforce per-document authorization itself. Use transactions and idempotency keys for sensitive workflows, test with emulators, monitor SLOs/costs, and never let emulator configs or service account keys leak into production.
