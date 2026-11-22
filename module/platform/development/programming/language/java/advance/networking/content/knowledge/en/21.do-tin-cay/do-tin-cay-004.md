# Idempotency, Request IDs, and Unknown Outcomes After Disconnection

## 1. The reliability problem: the client loses the response after the server has committed

The client sends a command to create a transaction, and the server executes it successfully and returns a response. However, if the connection drops **after the commit and before the response reaches the client**, the client only sees an `IOException`/timeout and **does not know whether the business operation has completed or not**. Blindly retrying can create a duplicate transaction. This is the **unknown outcome** problem, which is completely different from a request that was definitely rejected by the server.

~~~text
CLIENT                                     SERVER
 POST amount=100, key=op-42 --------------> processes and commits receipt=R-1
                          X <------------- response is lost
 Client: UNKNOWN                            Server: COMPLETED
 POST amount=100, key=op-42 --------------> recognizes key, returns cached R-1
 201 receipt=R-1 <------------------------ does not create a 2nd effect
~~~

There are at least three possibilities that lead to the same network error on the client: the request never reached the server; the request arrived and is still processing/rolled back; or the request was **committed** but the response was lost. **It is impossible to distinguish these three possibilities solely from an exception on the client side.** The system must have a way to query the operation or retry with the same logical ID to recover the result.

Lesson objectives: understand idempotency, distinguish between request ID and idempotency key, design a server-side deduplication mechanism, handle unknown outcome situations, clearly understand the limits of "exactly once", and examine two Java 17+ examples running on HTTP loopback without Internet access.

## 2. What does idempotency actually mean?

An operation is **idempotent** when repeating that operation multiple times still produces the same **requested business effect** as executing it once:

~~~text
effect(op, op, op) == effect(op)
~~~

For example, the same command "set user status to ACTIVE" can be idempotent: the final state is still ACTIVE. Calling POST "create new transaction" three times is not idempotent by default: it can create three transactions. However, a POST with an `Idempotency-Key` contract properly enforced by the server can allow **resending the same logical operation multiple times while creating only one business effect**.

**Idempotency does not mean the responses of two calls must be byte-for-byte identical.** A DELETE command to remove an item might return 204 the first time and 404 the next time, yet the desired effect "item does not exist" remains the same. Access logs/metrics may be recorded multiple times even though the business effect is idempotent.

| Term | Definition | Guarantee |
| --- | --- | --- |
| **Idempotency** | Repeating the same logical operation has the same intended effect | Requires a server/operation contract |
| **At-most-once effect** | Each operation occurs at most once | May not have occurred yet; still must distinguish UNKNOWN |
| **At-least-once delivery** | Retrying to attempt delivering the request at least once | May run side effects multiple times if deduplication is missing |
| **Exactly-once end-to-end** | An effect occurs exactly once across all processes/networks/downstreams | Not automatically achieved by headers or a local map |

You should not claim "exactly once" when only checking whether a request has ever appeared in a `HashMap`. What needs to be defined is the **boundary of the real effect**, transaction scope, crash window, retries, and retention.

## 3. Are HTTP methods idempotent by default?

RFC 9110 Section 9.2.2 specifies that safe methods (GET/HEAD, etc.), PUT, and DELETE have **idempotent semantics**; POST is **not idempotent by default**.

| Method | Typical Semantics | Retry Assessment |
| --- | --- | --- |
| `GET`/`HEAD` | Read/metadata, safe/idempotent | Can be retried according to quota/timeout policy |
| `PUT` | Put/replace a resource at a specific URI | Same request has the same desired state; response may differ |
| `DELETE` | Delete the specified resource | Can be idempotent even if subsequent calls return 404 |
| `POST` | Process according to the resource, usually creating a new resource/effect | Needs a dedicated idempotency definition to retry safely |

The RFC also warns against automatically retrying non-idempotent requests if you do not know the idempotency semantics or do not know that the first request has not been applied. In practice, retries can occur at the client, proxy, and intermediate layers; backend deduplication is still necessary. Switching the method from POST to PUT **does not automatically guarantee** that a payment gateway in another system will charge only once.

## 4. Request ID, operation ID, and idempotency key

Three identifiers that are often conflated:

- **requestId/correlation ID**: used for logging and tracing a single HTTP attempt. A new retry may have a new request ID.
- **operationId/Idempotency-Key**: identifies **a single business intent**; every retry attempt of the same intent must use the **same key**.
- **resourceId/receiptId**: ID of the resource or result created by the server. Used for lookup/reconciliation.

~~~text
Logical operation: transfer 100 to B
  Idempotency-Key: op-42
  Attempt 1: requestId=req-A -> lost response
  Attempt 2: requestId=req-B -> server returns receipt=R-1
  Business result: only one operation R-1

NEW logical operation: transfer another 100 to B
  Idempotency-Key: op-43
  Business result: creates receipt=R-2
~~~

The `Idempotency-Key` header **is not automatically interpreted by Java HttpClient or every server**. It only has meaning if the API contract defines the key, scope, payload fingerprint, returned result, retention, and retry behavior. If a service uses a different header/field name, you must follow that exact contract.

**Scope:** the server should bind the key to the tenant/principal and the operation type (method + endpoint or resource), preventing two users with the same key string from affecting each other. A trace ID alone cannot replace a stable idempotency key during retries.

## 5. Designing the contract between client and server

An example HTTP request:

~~~http
POST /transfers HTTP/1.1
Content-Type: application/json
Idempotency-Key: 7ce60a9a-4f18-452c-93ad-3f801ea39d4b

{"from":"A","to":"B","amount":100,"currency":"VND"}
~~~

*This is an illustrative HTTP message, not a standalone runnable client example.*

The contract should answer:

1. **Who generates the key?** The client/orchestrator creates a unique key for the logical operation and persists it before sending (using a random UUID or a suitable stable ID).
2. **What does "same request" mean?** The server compares the key + **the fingerprint of the business-affecting payload**. Same key with different amount/receiver -> conflict, do not create a new operation.
3. **What result does the server retain?** Status, response status/body/resource ID, and retention duration. Retrying with the same key + fingerprint returns the known status/result.
4. **What if two requests with the same key arrive concurrently?** It must atomically claim one owner; the subsequent request waits/receives pending/replays; do not run duplicate side effects.
5. **What happens when the key expires?** TTL/retention must be clearly published. Retrying too late must not be assumed safe if the record has already been cleaned up.
6. **Access control?** The key must be bound to the principal/tenant; never return someone else's receipt just because they guessed the right key.

A status/receipt endpoint allows the client to query `GET /operations/{operationId}` instead of guessing the outcome when receiving an `IOException`.

## 6. Recommended state machine for an operation

~~~text
               new scoped key
 ABSENT ------------------------------> IN_PROGRESS
                                             |
                              apply effect + commit result
                                             v
                                         COMPLETED
                                             |
                     same key + same payload -> replay result

 In-progress duplicate -> wait/poll/pending, DO NOT apply a 2nd time.
 Same key + other payload -> CONFLICT, DO NOT apply another effect.
 FAILED/UNKNOWN -> distinguish rolled-back errors from uncertain effects.
~~~

`IN_PROGRESS` **does not always mean "has not called downstream yet"**. If a worker sent a request to a payment gateway and then crashed, the pending record might correspond to a transaction that was already charged. Do not delete pending records and rerun without reconciliation.

If all effects reside within a single database, storing the effect + result in one transaction with a unique key is stronger. When calling an external service, you need a downstream idempotency key or outbox/inbox + reconciliation; local state is not enough.

## 7. After a disconnect, what is the right mindset?

~~~text
Scenario A:
 Client --X--> Server  (request did not arrive)
 Effect = 0

Scenario B:
 Client -----> Server (processing)
         <---X        Effect may be uncertain

Scenario C:
 Client -----> Server (commits R-1)
         <---X        Effect = 1 but response is lost
~~~

Errors such as `IOException`, EOF, connection reset, and `HttpTimeoutException` can leave the state as **UNKNOWN** if the client has sent or may have sent the request. Do not use "network failed" as proof that "DB rolled back". Even if the client cancels a `CompletableFuture`, the server may have already received and processed the request.

**UX policy:** in financial operations, display "Verifying result" and provide a status lookup. Do not automatically open a new transaction with a new idempotency key when the old outcome is still unclear.

## 8. Safe retries: same key, same payload, with a deadline

Client workflow:

~~~text
1. Generate operationId once and persist it before sending.
2. Send request with operationId + payload matching the contract.
3. If COMMITTED result is received: save receipt and stop.
4. If PENDING is received: poll operationId, do not create a new effect.
5. If CONFLICT is received: stop, check key/payload reuse.
6. If I/O timeout/disconnect: mark UNKNOWN, query status.
7. If allowed by contract: retry with SAME key + SAME intent/payload.
8. Limit attempt count, total deadline, exponential backoff + jitter.
9. If TTL is exceeded or reconciliation fails: escalate UNKNOWN, do not retry blindly.
~~~

HTTP 429/503 or `Retry-After` can suggest backoff, **but does not automatically authorize retrying a non-idempotent POST**. Distinguish validation errors (400), authorization errors (401/403), fingerprint conflict (409), pending (202), and transport errors. When the client/gateway/queue all retry, every layer must preserve the same logical key to prevent duplicates.

## 9. Java 17+: demonstrating a server commit followed by a lost HTTP response

The first lab runs an `HttpServer` on `127.0.0.1` and an `HttpClient` in the same JVM. The server uses `ConcurrentHashMap.compute` to store `Stored(payload, receipt)` with a scoped key, and an `AtomicInteger` to count side effects. It intentionally **closes the exchange after applying the effect but before sending the response headers the first time**. The client encounters an `IOException` and thus treats the outcome as unknown. On retry, the server finds the old key, returns receipt R-1, and does not increment the effect count.

**Important:** the store here is **only the memory of a single process**, not a durable database at all. `ConcurrentHashMap.compute` demonstrates per-key atomicity within the JVM; it does **not** guarantee across nodes/restarts, nor does it make a payment gateway exactly-once. The demo server reads the body with `readAllBytes()` before checking its size, which is unsuitable for production (size must be capped while streaming).

Create the file `UnknownOutcomeRetryDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class UnknownOutcomeRetryDemo {
    record Stored(String payload, String response) {}
    record Decision(int status, String response, boolean replayed,
                    boolean newlyApplied) {}

    private static final ConcurrentHashMap<String, Stored> STORE =
            new ConcurrentHashMap<>();
    private static final AtomicInteger EFFECTS = new AtomicInteger();
    private static final AtomicBoolean DROP_FIRST_RESPONSE = new AtomicBoolean(true);

    private static void respond(HttpExchange exchange, Decision decision)
            throws IOException {
        byte[] bytes = decision.response().getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.getResponseHeaders().set(
                "Idempotency-Replayed", Boolean.toString(decision.replayed()));
        exchange.sendResponseHeaders(decision.status(), bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static void transfer(HttpExchange exchange) throws IOException {
        try {
            if (!"POST".equals(exchange.getRequestMethod())) {
                exchange.sendResponseHeaders(405, -1);
                return;
            }
            String key = exchange.getRequestHeaders()
                    .getFirst("Idempotency-Key");
            if (key == null || key.isBlank() || key.length() > 64) {
                exchange.sendResponseHeaders(400, -1);
                return;
            }
            byte[] body = exchange.getRequestBody().readAllBytes();
            if (body.length > 128) {
                exchange.sendResponseHeaders(413, -1);
                return;
            }
            String payload = new String(body, StandardCharsets.UTF_8);
            String scopedKey = "demo-user|POST|/transfers|" + key;
            AtomicReference<Decision> answer = new AtomicReference<>();
            STORE.compute(scopedKey, (ignored, previous) -> {
                if (previous != null) {
                    if (!previous.payload().equals(payload)) {
                        answer.set(new Decision(409,
                                "key reused with different payload", false, false));
                    } else {
                        answer.set(new Decision(201, previous.response(), true, false));
                    }
                    return previous;
                }
                int receiptNumber = EFFECTS.incrementAndGet();
                String receipt = "receipt=R-" + receiptNumber;
                answer.set(new Decision(201, receipt, false, true));
                return new Stored(payload, receipt);
            });
            Decision decision = answer.get();
            if (decision.newlyApplied()
                    && DROP_FIRST_RESPONSE.compareAndSet(true, false)) {
                // Simulate: server applied the effect, then the connection
                // disappeared before it could send HTTP response headers.
                return;
            }
            respond(exchange, decision);
        } finally {
            exchange.close();
        }
    }

    private static HttpRequest request(String endpoint, String key, String payload) {
        return HttpRequest.newBuilder(URI.create(endpoint))
                .timeout(Duration.ofSeconds(5))
                .header("Idempotency-Key", key)
                .header("Content-Type", "text/plain; charset=utf-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        payload, StandardCharsets.UTF_8))
                .build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        server.setExecutor(pool);
        server.createContext("/transfers", UnknownOutcomeRetryDemo::transfer);
        server.start();
        try {
            String endpoint = "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/transfers";
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1).build();
            HttpRequest first = request(endpoint, "op-42", "transfer=100");
            boolean unknownOutcome = false;
            try {
                client.send(first, HttpResponse.BodyHandlers.ofString());
            } catch (IOException expected) {
                unknownOutcome = true;
            }
            if (!unknownOutcome) {
                throw new AssertionError("expected an intentionally lost response");
            }
            System.out.println("first attempt: outcome unknown to client");

            HttpResponse<String> retry = client.send(
                    request(endpoint, "op-42", "transfer=100"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("same-key retry: " + retry.statusCode()
                    + " " + retry.body());
            System.out.println("replayed: " + retry.headers()
                    .firstValue("Idempotency-Replayed").orElse("missing"));
            System.out.println("effects after retry: " + EFFECTS.get());

            HttpResponse<String> mismatch = client.send(
                    request(endpoint, "op-42", "transfer=999"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("same key, other payload: " + mismatch.statusCode());
            System.out.println("effects after conflict: " + EFFECTS.get());

            HttpResponse<String> distinct = client.send(
                    request(endpoint, "op-43", "transfer=100"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("new-key request: " + distinct.statusCode()
                    + " " + distinct.body());
            System.out.println("final effects: " + EFFECTS.get());
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Compile/run:

~~~bash
javac UnknownOutcomeRetryDemo.java
java UnknownOutcomeRetryDemo
~~~

Exact stdout:

~~~text
first attempt: outcome unknown to client
same-key retry: 201 receipt=R-1
replayed: true
effects after retry: 1
same key, other payload: 409
effects after conflict: 1
new-key request: 201 receipt=R-2
final effects: 2
~~~

## 10. Explaining the output of the lost-response example

**First attempt:** `Idempotency-Key: op-42`, payload `transfer=100`. The server claims the key `demo-user|POST|/transfers|op-42` and creates `receipt=R-1`; then the code intentionally skips sending headers and calls `exchange.close()` in `finally`. Because the client receives no HTTP response, it prints `first attempt: outcome unknown to client`. In the test source code we know the effect occurred, but a real client must not infer that from an I/O error.

**Proper retry:** same key `op-42` and identical payload, the server returns `201 receipt=R-1` along with the demo header `Idempotency-Replayed: true`. The counter `effects after retry: 1` proves the in-memory effect did not repeat.

**Improper reuse:** same `op-42` but `transfer=999` returns `409`, counter remains 1. Do not "fix" a 409 by changing the key when the old request might have already been applied; this can cause duplicates/unintended effects.

**New operation:** `op-43` with the same amount is a **different** logical operation, so it creates `receipt=R-2`, counter 2. Same payload **does not necessarily** mean the same business operation: a new ID is what distinguishes a new intent from a retry.

The `Idempotency-Replayed` header in the demo is a **custom application convention**, not something every API returns. Returning HTTP 201 on replay is also a policy choice; some systems return the exact original response, while others return 200 with the resource ID.

## 11. Concurrent duplicates: the race bug of containsKey + put

An anti-pattern:

~~~java
if (!store.containsKey(key)) {
    externalCharge();              // Two threads can call this at the same time.
    store.put(key, result);
}
~~~

*The snippet above is **intentionally flawed pseudocode**; the variables `store`, `key`, `result`, and `externalCharge` do not form a standalone program.*

Two threads can both see "key does not exist yet" and both execute the charge. In the end, the map has only **one record**, but the customer was charged **twice**. Within a single JVM, `ConcurrentHashMap.compute` provides atomic per-key remapping, suitable for demonstrating **in-memory** race prevention. In a multi-pod system, each JVM has its own map, so there must still be a **unique constraint/atomic claim in a durable DB**.

You should also not call an external payment gateway **inside `compute`** and conclude it is "safe"; the external network is not part of the map's transaction and can commit while the response is lost.

## 12. Java 17+: eight concurrent duplicate requests record only one effect

The `ConcurrentKeyDedupDemo` program sends **8 parallel POSTs** using `HttpClient.sendAsync`, with the same `Idempotency-Key: batch-7` and payload `amount=42`. The server uses `ConcurrentHashMap.compute` for the key combined with principal/endpoint, so only the first request in the **test JVM** creates the stored record and increments the effect count; the remaining seven requests receive the cached result.

The code prints **totals** instead of relying on request completion order (which is non-deterministic). It sends an additional request with the same key but a different payload to verify conflict handling.

Create the file `ConcurrentKeyDedupDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentKeyDedupDemo {
    record Stored(String payload, String response) {}

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Stored> stored = new ConcurrentHashMap<>();
        AtomicInteger applied = new AtomicInteger();
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService handlers = Executors.newFixedThreadPool(8);
        server.setExecutor(handlers);
        server.createContext("/operations", exchange -> {
            try {
                byte[] bytes = exchange.getRequestBody().readAllBytes();
                String payload = new String(bytes, StandardCharsets.UTF_8);
                String key = exchange.getRequestHeaders()
                        .getFirst("Idempotency-Key");
                if (!"POST".equals(exchange.getRequestMethod())
                        || key == null || key.isBlank() || bytes.length > 128) {
                    exchange.sendResponseHeaders(400, -1);
                    return;
                }
                AtomicBoolean fresh = new AtomicBoolean();
                Stored record = stored.compute("demo-user|POST|/operations|" + key,
                        (ignored, previous) -> {
                            if (previous != null) return previous;
                            fresh.set(true);
                            int number = applied.incrementAndGet();
                            return new Stored(payload, "created=R-" + number);
                        });
                int status = record.payload().equals(payload) ? 201 : 409;
                String result = status == 201
                        ? record.response() : "different payload";
                exchange.getResponseHeaders().set(
                        "Idempotency-Replayed",
                        Boolean.toString(status == 201 && !fresh.get()));
                byte[] reply = result.getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status, reply.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(reply);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            String endpoint = "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/operations";
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
                    .timeout(Duration.ofSeconds(8))
                    .header("Idempotency-Key", "batch-7")
                    .POST(HttpRequest.BodyPublishers.ofString("amount=42"))
                    .build();
            List<CompletableFuture<HttpResponse<String>>> futures =
                    java.util.stream.IntStream.range(0, 8)
                            .mapToObj(i -> client.sendAsync(
                                    request, HttpResponse.BodyHandlers.ofString(
                                            StandardCharsets.UTF_8)))
                            .toList();

            CompletableFuture.allOf(
                    futures.toArray(CompletableFuture<?>[]::new))
                    .get(15, TimeUnit.SECONDS);
            List<HttpResponse<String>> results =
                    futures.stream().map(CompletableFuture::join).toList();
            long successes = results.stream()
                    .filter(r -> r.statusCode() == 201).count();
            long replays = results.stream().filter(r ->
                    r.headers().firstValue("Idempotency-Replayed")
                            .orElse("false").equals("true")).count();
            System.out.println("successful responses: " + successes);
            System.out.println("replayed responses: " + replays);
            System.out.println("side effects: " + applied.get());
            System.out.println("stored keys: " + stored.size());

            HttpRequest conflict = HttpRequest.newBuilder(URI.create(endpoint))
                    .timeout(Duration.ofSeconds(5))
                    .header("Idempotency-Key", "batch-7")
                    .POST(HttpRequest.BodyPublishers.ofString("amount=999"))
                    .build();
            HttpResponse<String> mismatch = client.send(conflict,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("same-key conflict status: "
                    + mismatch.statusCode());
            System.out.println("side effects after conflict: " + applied.get());
        } finally {
            server.stop(0);
            handlers.shutdownNow();
        }
    }
}
~~~

Compile/run:

~~~bash
javac ConcurrentKeyDedupDemo.java
java ConcurrentKeyDedupDemo
~~~

Stdout:

~~~text
successful responses: 8
replayed responses: 7
side effects: 1
stored keys: 1
same-key conflict status: 409
side effects after conflict: 1
~~~

`successful responses: 8` here is the number of HTTP 201 responses, **not eight side effects**. `replayed responses: 7` is seven reads of the cached result. `side effects: 1` is the actual number of times the in-memory code applied the record-creation logic. If running tests across multiple JVMs/DBs or killing processes, another durable mechanism is needed — do not extrapolate unit demo results into production guarantees.

## 13. Which idempotency records must be durable?

A reference schema:

| Field | Example | Role |
| --- | --- | --- |
| `tenant_id` | tenant-A | Namespace and authorization |
| `operation_type` | POST:/transfers | Distinguishes business operation type |
| `idempotency_key` | op-42 | Logical operation |
| `request_fingerprint` | SHA-256 of canonical payload | Prevents reusing key with different intent |
| `state` | IN_PROGRESS/COMPLETED | Tracks claim and recovery |
| `resource_id` | transfer-R-1 | Queries the created transaction |
| `http_status`, `response_body` | 201, receipt | Enables replaying the result |
| `created_at`, `expires_at` | timestamps | TTL/retention |
| `lease_version` | version/worker | Prevents stale worker from reclaiming pending |

Typical unique key: `UNIQUE(tenant_id, operation_type, idempotency_key)`. When the key already exists, you must check the fingerprint and status rather than starting a second effect. Scoping keys by tenant prevents leaking another user's cached response.

If the database allows placing the effect and result record in **the same transaction**, the goal is an **atomic commit**. If the business side effect resides in another payment gateway, an internal DB transaction **does not span** the transaction at the gateway: you need a downstream idempotency key, outbox/inbox, bounded retries, and reconciliation.

## 14. Transactions, unique constraints, and the crash window

A pseudocode flow:

~~~text
BEGIN TRANSACTION
  INSERT scoped idempotency key IF ABSENT (unique index)
  If already exists:
    compare fingerprint; different -> conflict
    if COMPLETED -> return saved result
    if IN_PROGRESS -> pending/wait/reconcile
  If claim succeeds:
    perform business update in the same DB transaction
    save resource ID, status, body, or receipt
    transition state to COMPLETED
COMMIT

Send HTTP response. If the response is lost, the record remains for replay.
~~~

This is a **conceptual algorithm**, not direct SQL for every RDBMS. Production must account for isolation levels, deadlocks, unique constraint violations, transaction retries, crash recovery, and side effects outside the DB.

Example of a severe risk:

~~~text
1. Server calls gateway CHARGE op-42
2. Gateway charges successfully
3. Server crashes before saving COMPLETED
4. Client times out, retries op-42
5. Server does not know the gateway already charged, risking a duplicate call
~~~

To handle this, you must have a downstream operation ID/idempotency key accepted by the gateway and a lookup/reconciliation endpoint. Do not automatically delete `IN_PROGRESS` because a lease expired: the worker might have already completed the external work. Outbox/inbox or saga patterns may fit depending on the architecture.

## 15. Canonical request fingerprint and conflict

The same key must correspond to the same intent: amount, currency, account, recipient, item ID, or attributes that change the effect. A consistent fingerprint/canonicalization method is required.

~~~json
{"amount":100,"currency":"VND"}
{"currency":"VND","amount":100}
~~~

In JSON, the two versions above can represent the **same intent** when keys and data are properly canonicalized, even though the byte order differs. Conversely:

~~~json
{"amount":100,"currency":"VND"}
{"amount":999,"currency":"VND"}
~~~

Represents a **different intent** and must return a conflict if the key is reused. A SHA-256 hash is merely a means to create a fingerprint, not a substitute for validation, authorization, and normalization. Do not include a trace ID that changes on every retry in the business fingerprint. Version your canonicalization when updating the schema/API.

The demo uses **exact String comparison** so the code focuses on the deduplication mechanism; it is not a JSON canonicalizer and does not handle Unicode normalization, JSON equivalent values, floating-point numbers, or complex financial properties.

## 16. IN_PROGRESS, TTL, and proper recovery

**IN_PROGRESS** can represent three real states: downstream not yet called, called and waiting, or committed downstream but the server has not yet received the result. Allow only one worker to hold the claim/lease at a time, using a fencing token or unique constraint to prevent a stale worker from continuing to write; combine with **reconciling external results** when a process restarts.

**TTL has no universal HTTP/JDK default.** An API may keep cached results for 24 hours, seven days, or longer depending on requirements; the duration is part of the contract. A key whose TTL expires while the client still retries after 48 hours could be treated as a new operation and create a duplicate — dangerous for payments. Business receipts/ledgers must be stored more durably than short-term response caches.

Retention should balance storage quotas and retry windows; clearly specify whether expiration will reject, transition to UNKNOWN requiring reconciliation, or allow a new key. Do not silently treat a recently expired key as an unprocessed intent.

## 17. Recognizing responses, HTTP errors, and transport errors

| Client observes | Can conclude | Typical policy |
| --- | --- | --- |
| 201 + valid receipt | Business response confirming resource creation | Save receipt, stop retrying |
| 200 + replayed result | API returned the result per contract | Update completed status |
| 202 + PENDING | Server accepted request, no final result yet | Poll by operationId |
| 409 + fingerprint mismatch | Key reused for a different intent | Stop, alert, do not arbitrarily change key |
| 429/503 | Server overloaded/temporarily rejecting | Backoff if operation is idempotent |
| TCP reset/EOF/read timeout | **Outcome may be UNKNOWN** | Query status or retry same key |
| Future cancellation | Client requested cancellation, rollback not guaranteed | Query/reconcile |
| Status endpoint 404 | Record may not exist yet, expired, or replication lag | Check retention/contract, do not guess |
| HTTP 500/502/504 | Server error, no proof effect did not occur | Do not retry with a new key |
| Request 400/401/403 | Input/auth error, usually requires config/fix | Avoid unconditional retry |

Do not conflate non-2xx HTTP statuses with Java `IOException`. `HttpClient.send` can return an `HttpResponse` containing status 500 normally at the HTTP level; the future only completes exceptionally on I/O/processing errors. Never deduce whether a server charge occurred solely from an error class.

## 18. Java HttpClient: request timeout and future cancellation

Snippet demonstrating a client sending a POST with a stable key:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.org/transfers"))
        .timeout(Duration.ofSeconds(5))
        .header("Idempotency-Key", operationId)
        .POST(HttpRequest.BodyPublishers.ofString(payload))
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
future.whenComplete((response, error) -> {
    if (error != null) {
        // UNKNOWN: query operation status/retry per contract, do not conclude failed.
        return;
    }
    // Check status, resourceId/receipt, and save final state.
});
~~~

*Illustrative snippet inside a class with `client`, `operationId`, `payload`, and imports; not a standalone runnable program.*

`sendAsync` returns a `CompletableFuture<HttpResponse<T>>`; `join()` can throw `CompletionException` when exceptional. `send` can throw `IOException`. `HttpRequest.Builder.timeout` limits the HTTP request duration; it **does not prove** the server rolled back on timeout.

`CompletableFuture.cancel(true)` on an HTTP future is a cancellation request; it **does not guarantee the request has not reached/been processed by the server**. If the server already charged, closing TCP or resetting an HTTP/2 stream does not automatically reverse the charge. For non-idempotent POSTs, do not use cancel + resend with a new key as a retry mechanism.

## 19. Security, resource limits, and observability

- **Keys must have sufficient entropy**; avoid using email, account numbers, access tokens, or PII directly as keys. Limit key length/header size and the number of new keys per tenant.
- **Scope by principal/tenant + operation type** so the same key from two users cannot read/overwrite each other's results. Even after authentication, you must still check authorization against the resource.
- **Do not log sensitive payloads** or full cached responses. Log safe operation IDs, attempt trace IDs, state transitions, result codes, and durations.
- **Read request bodies with limits from the start.** Both demos intentionally use `readAllBytes()` for small mock bodies before checking size; do not copy that pattern for an Internet-facing server. Use a capped streaming read and reject when exceeded.
- **Limit in-flight operations**, HTTP connections, timeouts, and DB locks. Duplicate requests during `IN_PROGRESS` can wait with a bound, return pending/Retry-After, or point to a status endpoint.
- **Do not indefinitely cache all 5xx errors**; which error types can be replayed or retried depends on the contract and transaction outcome. Always distinguish validation errors before side effects from errors after a possible commit.
- **Limit auto-retries across multiple layers**: application, SDK, gateway, queue. Share the logical key so retries do not create duplicate effects, and use exponential backoff + jitter.
- **Separate durable audit ledgers/receipts** from TTL caches, especially for payments and multi-step transactions.

## 20. Test matrix for idempotency

| Fault injection | How to test | What to verify |
| --- | --- | --- |
| Sequential duplicate | Send same key/payload twice | One effect, accurate response replay |
| Concurrent duplicate | Multiple threads/clients with same key | Atomic claim, no duplicate charge |
| Same key, different payload | Reuse key with new amount | Conflict, no change to effect |
| New key with same payload | Execute a new intent | New effect allowed per contract |
| Lost response after commit | Close connection after effect | Client UNKNOWN, retry/poll recovers |
| Crash before DB commit | Kill process mid-transaction | No false COMPLETED |
| Crash after commit before HTTP response | Kill after COMMIT | Retry returns stored result |
| External gateway already charged | Drop downstream response | Reconcile via provider operation ID |
| Stuck IN_PROGRESS | Worker crash, lease expired | Fencing, reconcile before reclaim |
| Key past TTL | Retry after expiration | No duplicate violating policy |
| HTTP 429/503/timeout | Retry policy + jitter/deadline | No storm, same key preserved |
| Wrong tenant/key collision | Two principals use same key string | No leaked cached receipt |
| Restart/multi-instance | Two+ server nodes | DB/unique index guarantees claim |
| Partial body/client cancel | Interrupt during upload/response wait | Do not guess commit solely from I/O error |

The two Java programs in this lesson prove **in-memory** deduplication and response loss while a single JVM stays alive. Do not treat them as durability tests for DB/process crashes, external gateways, or multi-node setups.

## 21. Common misconceptions

| Misconception | Reality | How to fix |
| --- | --- | --- |
| "IOException means the transaction failed." | Response may be lost after commit | Mark UNKNOWN, look up status |
| "HTTP 500 proves nothing was written." | May fail after applying effect | Reconcile |
| "Retrying POST with a new key is safe." | A new key is a new operation | Keep the old key for retries |
| "Adding Idempotency-Key is enough by itself." | Server must enforce the contract | Key + fingerprint + durable dedup |
| "requestId is always the deduplication key." | requestId is per HTTP attempt | Separate operationId |
| "PUT/DELETE must return the same status." | Idempotency is about desired effect | Check final state |
| "POST is idempotent by default." | Not according to RFC 9110 | Define explicitly |
| "containsKey then put is atomic." | Race condition between threads | Atomic claim |
| "ConcurrentHashMap is enough for a cluster." | Each JVM has its own map | DB transaction/unique index |
| "Unique key guarantees gateway won't double-charge." | External effect is outside the DB | Downstream idempotency + reconcile |
| "IN_PROGRESS means not charged yet." | Gateway may have received the call | Inspect pending state |
| "Expired key still prevents duplicates." | Record may be gone | Retention/ledger |
| "Cancelling future rolls back the server." | Cancel is only a request | Query status |
| "Every 5xx response is retryable." | May have committed; contracts vary | Classify errors |
| "Payload hash replaces auth." | Hash grants no access rights | Scope principal + auth |
| "ReadAllBytes then check limit is enough." | Allocation already happened | Capped streaming read |
| "A cached 201 means exactly-once end-to-end." | Does not solve crashes/downstream | Define transaction boundary |

## 22. Self-check questions

**1.** A client sends a POST and loses the response. Can it immediately notify the user "failed" and generate a new operation ID?

*Answer:* No. The client is in the UNKNOWN state; the server may have already committed. It must query/retry with the same ID according to the contract.

**2.** What should be done when the same key `op-42` is sent with a different payload amount?

*Answer:* Conflict, do not apply a second effect; do not silently alter the content of the old operation.

**3.** Why does `ConcurrentHashMap.compute` not prove exactly-once in a three-pod system?

*Answer:* Each pod has its own map and loses it on restart. Without a transaction with the DB/downstream, double effects can still occur.

**4.** Can `DELETE /items/7` returning 204 the first time and 404 the second time be idempotent?

*Answer:* Yes. The intended effect that the item no longer exists is the same even though the responses differ.

**5.** Does `CompletableFuture.cancel(true)` make a payment gateway reverse a charge?

*Answer:* No. Client cancellation is not a downstream rollback.

**6.** If a key's TTL expires after one day, is it strictly safe for the client to retry after three days?

*Answer:* No. The server may have forgotten the key; a longer-lived ledger/retention or reconciliation is needed.

**7.** If the same key and payload are sent concurrently while IN_PROGRESS, should two jobs be created?

*Answer:* No. One owner processes it, and the other waits/polls/returns pending/replays.

**8.** Do the trace ID and operation ID need to be identical?

*Answer:* No. The trace ID can differ per HTTP attempt; the operation ID must remain stable across retries of a single logical intent.

## 23. Practice exercises

1. Run `UnknownOutcomeRetryDemo`, point out where the server recorded the effect and intentionally closed the exchange before headers. Explain why the client only knows UNKNOWN even though the test program knows the effect occurred.
2. Change the key of the first retry from `op-42` to `op-999`; observe the effect count increase, and explain why this retry is dangerous.
3. Keep `op-42` but change `transfer=100` to `transfer=101`; verify HTTP 409 and that the effect count remains 1.
4. In `ConcurrentKeyDedupDemo`, increase 8 to 16 requests, track the number of `replayed responses` and `side effects`; do not rely on completion order.
5. Intentionally use `containsKey` then `put` in a multi-threaded test, observe the race condition, and explain why it must be replaced with an atomic claim.
6. Design a record `Outcome(operationId,state,status,receipt,error)` so the application has UNKNOWN/PENDING/COMPLETED/FAILED instead of a boolean.
7. Add `GET /operations/{id}` to the local server (must authenticate the principal in a real version) and write a client that polls after losing a response.
8. Design an SQL schema with `UNIQUE(tenant_id,operation_type,idempotency_key)`, a transaction writing the effect + result in the same DB, and test conflict/concurrency/crash scenarios.
9. Simulate the gateway having charged while the server crashes before COMPLETED; design downstream idempotency, outbox, and reconciliation.
10. Write a retry policy for 429/503/timeout with exponential backoff + jitter and a max total deadline; preserve the key and payload.
11. Design result cache retention/TTL separately from the durable ledger, avoiding duplicate transactions caused by retries after expiry.
12. Test two tenants using the same key string without being able to read/overwrite each other's results.
13. Change the fingerprint from a raw string to JSON canonicalization + SHA-256; ensure changing JSON property order does not cause a false conflict.
14. Write a fault-injection matrix before/after transaction commit, before/after HTTP response, and before/after downstream call, distinguishing recoverability.

## Official References

- [RFC 9110 Section 9.2.2 — HTTP Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110#section-9.2.2): idempotency semantics, PUT/DELETE/safe methods, and retrying upon communication failure.
- [`HttpClient` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, IO failures, and cancellation.
- [`HttpRequest` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request headers, timeout, body publisher.
- [`HttpResponse` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): status, headers, body.
- [`CompletableFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion, cancel, whenComplete, allOf.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic per-key compute in memory.
- [`HttpServer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): the demo's loopback HTTP server.
