# Idempotency of unary RPCs

## 1. Why do unary RPC retries require idempotency?

Suppose the client calls `CreateOrder`. The server writes the order to the database, but the connection drops before the response reaches the client. The client only sees `UNAVAILABLE` or `DEADLINE_EXCEEDED`; it does not know whether the server created the order or not. If it resends the request as a new operation, the server could create **two orders** for the same user intent.

**Idempotency** enables the server to recognize multiple submissions of the same logical operation and ensure they do not produce duplicate side effects. For unary RPCs, a common approach is for the client to send a stable **idempotency key**; the server stores the key along with a request fingerprint and the produced result.

The goal is not to force the network to deliver only once. The network can retransmit, responses can be lost, and the client may not know the outcome. The goal is to ensure repeated calls with the same key produce **one consistent business outcome** within the key retention period.

After this lesson, learners can design an idempotency key for a unary RPC, atomically store the key and result in Spring, handle concurrent duplicate requests, distinguish key reuse with a different payload, and test retries without creating duplicate side effects.

## 2. Idempotency is not equivalent to exactly-once delivery

Three concepts must be distinguished:

| Concept | Meaning |
| --- | --- |
| At-most-once effect by key | A logical operation creates at most one protected side effect within the key/retention scope |
| At-least-once delivery | The client or infrastructure may resend the request until a result is received |
| Exactly-once delivery | The network guarantees the request is delivered literally once; this is not a gRPC guarantee |

gRPC retry can generate multiple attempts for the same logical RPC. Application-layer idempotency prevents those attempts from re-executing the side effect. However, if a side effect lives outside the database transaction—such as calling a payment gateway or sending an email—simply storing the key in the service's database is not enough to guarantee the external side effect happens once.

Therefore, describe the guarantee precisely: **same scope, same key, and same request fingerprint will return the same stored result; a key must not be reused for a different request**. The guarantee holds only while the record is retained and across systems whose side effects are protected.

## 3. Designing an idempotency key

A good key should satisfy:

- **Stable across retries:** the client generates the key once for one business intent and keeps it unchanged across all attempts.
- **Sufficiently unique:** a random UUID/ULID or an identifier generated with appropriate uniqueness.
- **Scoped:** combine tenant/principal, method name, and key to avoid collisions across different customers or APIs.
- **Free of secrets:** keys may appear in logs and traces; do not embed access tokens, card numbers, or sensitive data.
- **Bounded retention:** the server publishes how long records are kept and what happens when a key expires.

Example:

```text
scope = tenant-17
method = orders.v1.OrderService/CreateOrder
idempotency_key = 01JQ7M9K2Y...
```

The unique key in storage can be the triple `(tenant_id, method_name, idempotency_key)`. Do not rely on a global key alone if the system serves multiple tenants or multiple methods.

### 3.1. Generate the key on the client, not anew per attempt

The client generates the key before invoking the RPC and stores it inside the command object:

```java
String key = UUID.randomUUID().toString();
CreateOrderRequest request = CreateOrderRequest.newBuilder()
        .setIdempotencyKey(key)
        .setCustomerId("customer-42")
        .setProductCode("BOOK-17")
        .setQuantity(2)
        .build();

CreateOrderResponse response = stub
        .withDeadlineAfter(3, TimeUnit.SECONDS)
        .createOrder(request);
```

If the caller decides to retry after the call ends, it must use the **same request and the same key**. Generating a new UUID for the next attempt causes the server to treat it as a brand-new operation. Only when the user intentionally creates a new order should a new key be generated.

In applications that must recover after a client process restart, the key and payload of the pending operation may need to be persisted on the client before sending.

## 4. Put the key in Protobuf or metadata?

For a unary operation, placing the key in the request message is clear, easy to test, and easy to store alongside business data:

```proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.v1";

service OrderService {
  rpc CreateOrder(CreateOrderRequest) returns (CreateOrderResponse);
}

message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  string product_code = 3;
  int32 quantity = 4;
}

message CreateOrderResponse {
  string order_id = 1;
  string status = 2;
}
```

You can pass the key via gRPC metadata if that is a platform-wide convention, provided header names, validation, interceptors, and storage are standardized. Do not send the key in both metadata and the body without defining which source is authoritative if the two values differ.

In this lesson, the key lives in Protobuf so its tie to the business operation is explicit.

## 5. Fingerprinting to detect improper key reuse

Checking only the key is not enough. A client might accidentally send the same key with a different payload:

```text
First attempt: key=K, product=BOOK-17, quantity=2
Subsequent attempt: key=K, product=BOOK-17, quantity=5
```

If the server inspects only the key, it might return the first request's result for the second request even though the intent changed. Therefore, the server must compute a **request fingerprint** from the business-meaningful fields, for example:

[
fingerprint = SHA256(canonical(customer, product, quantity))
]

Rules:

- Canonicalize data before hashing: field ordering, encoding, default values, and numeric representation must be consistent.
- Do not include the idempotency key itself in the fingerprint.
- Hash only fields that affect the business outcome; exclude trace IDs, deadlines, or transport metadata.
- If the same key arrives with a different fingerprint, return a conflict error, typically `ALREADY_EXISTS` or a contract-defined status.

Do not run an uncontrolled hash over arbitrary JSON strings if field order or formatting can vary. Use a stable canonical representation, such as a serializer with deterministic rules or a normalized field sequence.

## 6. Storing idempotency records atomically

A minimal table might look like this:

```sql
CREATE TABLE grpc_idempotency (
    tenant_id          VARCHAR(100) NOT NULL,
    method_name        VARCHAR(200) NOT NULL,
    idempotency_key    VARCHAR(160) NOT NULL,
    request_hash       VARCHAR(64) NOT NULL,
    response_type      VARCHAR(200),
    response_payload   BYTEA,
    created_at         TIMESTAMP NOT NULL,
    expires_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, method_name, idempotency_key)
);
```

The primary key constraint is the critical part: it guarantees that two concurrent transactions cannot both create records for the same scope/key. Checking with a `SELECT` followed by an `INSERT` without a unique constraint is unsafe because two requests can both see "not found".

When side effects live in the same database, a strong implementation pattern is:

1. Start a transaction.
2. Attempt to insert the idempotency record with an atomic operation such as `INSERT ... ON CONFLICT DO NOTHING`.
3. If the insert succeeds, the current transaction is the owner: apply the business change and store the response in the record.
4. Commit both the business change and the response in the same transaction.
5. If the insert does not succeed, read the existing record, compare fingerprints, and return the stored response.

When two concurrent requests use the same key, the unique constraint forces the later transaction to wait for the first transaction's outcome or receive a conflict. After the first transaction commits, the later request reads the stored response; if the first transaction rolls back, the later request can acquire the key and execute the operation.

### 6.1. Why must the response be stored in the same transaction?

Suppose the service creates an order and then saves the idempotency response in a separate transaction. If the service crashes between the two steps, the order already exists while the idempotency record does not; a retry could create a second order.

Putting **the business change and the idempotency response in the same transaction** ensures both commit or both roll back together, as long as they reside in the same transactional database.

Do not commit a separate `IN_PROGRESS` record and then process side effects in another transaction without a lease/recovery mechanism. If the process dies after claiming the key, the record could stay stuck forever. A split-transaction claim model requires an owner token, lease expiry, heartbeat, or explicit recovery mechanism.

## 7. Processing flow in a Spring service

The service should distinguish three outcomes from the idempotency store layer:

| Claim outcome | Behavior |
| --- | --- |
| `OWNER` | The current request owns the key and executes |
| `REPLAY` | Key and fingerprint match a completed record; return stored response |
| `KEY_CONFLICT` | Key was already used for a different fingerprint; reject |

An abstraction helps clarify the business flow:

```java
import io.grpc.StatusRuntimeException;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final IdempotentOrderHandler handler;

    public OrderGrpcService(IdempotentOrderHandler handler) {
        this.handler = handler;
    }

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<CreateOrderResponse> observer) {
        try {
            CreateOrderResponse response = handler.execute(request);
            observer.onNext(response);
            observer.onCompleted();
        } catch (StatusRuntimeException error) {
            observer.onError(error);
        } catch (RuntimeException error) {
            observer.onError(Status.INTERNAL
                    .withDescription("Failed to create order")
                    .asRuntimeException());
        }
    }
}
```

The idempotency logic lives in the application handler, not in transport callbacks:

```java
import com.google.protobuf.InvalidProtocolBufferException;
import io.grpc.Status;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentOrderHandler {
    private final IdempotencyStore idempotencyStore;
    private final OrderRepository orderRepository;
    private final RequestFingerprint fingerprint;

    public IdempotentOrderHandler(
            IdempotencyStore idempotencyStore,
            OrderRepository orderRepository,
            RequestFingerprint fingerprint) {
        this.idempotencyStore = idempotencyStore;
        this.orderRepository = orderRepository;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public CreateOrderResponse execute(CreateOrderRequest request) {
        if (request.getIdempotencyKey().isBlank()) {
            throw Status.INVALID_ARGUMENT
                    .withDescription("idempotency_key is required")
                    .asRuntimeException();
        }
        if (request.getQuantity() <= 0) {
            throw Status.INVALID_ARGUMENT
                    .withDescription("quantity must be greater than 0")
                    .asRuntimeException();
        }

        String tenantId = currentTenantId();
        String method = "orders.v1.OrderService/CreateOrder";
        String hash = fingerprint.forCreateOrder(request);

        IdempotencyStore.Claim claim = idempotencyStore.claimOrLoad(
                tenantId, method, request.getIdempotencyKey(), hash);

        return switch (claim.kind()) {
            case REPLAY -> decodeStoredResponse(claim.responsePayload());
            case KEY_CONFLICT -> throw Status.ALREADY_EXISTS
                    .withDescription(
                            "idempotency_key already used for a different request")
                    .asRuntimeException();
            case OWNER -> {
                Order order = orderRepository.save(
                        new Order(request.getCustomerId(),
                                request.getProductCode(),
                                request.getQuantity()));
                CreateOrderResponse response = CreateOrderResponse
                        .newBuilder()
                        .setOrderId(order.getId().toString())
                        .setStatus("CREATED")
                        .build();
                idempotencyStore.complete(claim.recordId(),
                        response.toByteArray(),
                        "orders.v1.CreateOrderResponse");
                yield response;
            }
        };
    }

    private String currentTenantId() {
        // Retrieve tenant from the authenticated security context.
        return "tenant-from-auth-context";
    }

    private CreateOrderResponse decodeStoredResponse(byte[] payload) {
        try {
            return CreateOrderResponse.parseFrom(payload);
        } catch (InvalidProtocolBufferException error) {
            throw Status.DATA_LOSS
                    .withDescription("Corrupted idempotency response")
                    .withCause(error)
                    .asRuntimeException();
        }
    }
}
```

`IdempotencyStore.claimOrLoad()` must be implemented using a unique constraint and atomic database operations as described earlier, not a plain `findByKey()` followed by `save()`. `complete()` persists the serialized response in **the same transaction** as `OrderRepository.save()`. Types such as `Claim`, `RequestFingerprint`, and the repository are application abstractions that must be implemented for the database in use.

The example uses modern Java `switch` expressions. If the project targets an older Java version, replace it with a switch statement. `currentTenantId()` is the integration point with the security context; do not take an unauthenticated tenant from the request.

## 8. Side effects outside the database

A database transaction cannot roll back an HTTP call to a payment provider, email service, or message broker that already succeeded. For example:

1. The service creates an order in the database.
2. The service calls the payment provider and payment succeeds.
3. The service crashes before saving the idempotency response.
4. The client retries; the service could call the payment provider a second time.

To protect a chain of side effects:

- Pass the same idempotency key when calling downstream providers if the provider supports it.
- Write a **transactional outbox** entry in the same transaction as the order and idempotency response.
- A worker reads the outbox and publishes events; consumers also deduplicate by event ID.
- Persist processing state and downstream results so execution can resume after a crash.

Idempotency must be implemented across every boundary where side effects occur. Storing request/response only in the first service does not provide exactly-once across the entire distributed system.

## 9. TTL and expiration policy

Idempotency records need retention long enough to cover the window during which clients can retry or users resubmit an operation because they did not receive a result. Upon expiration:

- A client resending an old key may be treated as a new operation once the record has been deleted.
- Records should not be deleted immediately after returning the first response.
- TTL must be published as part of the contract and fit retry windows, offline queues, and client recovery.
- Cleanup should delete in batches, avoiding one giant delete job that locks or overloads the database.

If business rules forbid duplicates over a long horizon, an additional business unique constraint—such as an order code beyond the idempotency key—may be needed. Idempotency retention does not replace long-lived business invariants.

## 10. Testing idempotency

Key tests:

| Scenario | Assertion |
| --- | --- |
| Same key, same payload, called twice sequentially | Both responses have the same order ID; only one order is created |
| Same key, same payload, two concurrent requests | Unique constraint guarantees one owner; the other request replays the result |
| Same key, different payload | Returns conflict error; creates no second side effect |
| Different tenant, same key | Two independent scopes per contract |
| Server commits but response is lost | Retry with the same key returns the stored response |
| First transaction rolls back | Subsequent request can acquire the key and execute the operation |
| Stored response fails to parse | Reports data/record error; creates no new side effect |
| Record reaches TTL | Behavior matching the retention contract is verified |
| Downstream side effect | Outbox/provider idempotency prevents duplicate side effects |

In particular, test **concurrency** using two simultaneous requests and verify the number of business records equals one. Sequential tests do not catch race conditions between `SELECT` and `INSERT`.

## 11. Common mistakes

1. **Generating a new key on every retry.** The server will treat each attempt as a new operation.
2. **Storing only the key without a fingerprint.** The same key could be reused with a different payload and receive the wrong result.
3. **Using SELECT then INSERT without a unique constraint.** Two concurrent requests can both become owners.
4. **Saving the idempotency record after committing business changes in a separate transaction.** A crash in between can cause duplicate side effects.
5. **Returning `Accepted` before acquiring processing ownership.** The client believes the request was accepted even though the server has not yet protected the key.
6. **Leaving TTL or cleanup unbounded.** The idempotency table can grow indefinitely.
7. **Assuming a DB transaction protects external payment/email calls.** Downstream idempotency or an outbox is required.
8. **Calling idempotency "exactly-once delivery".** It is an application/business-layer guarantee within a specific scope and retention window.

## 12. Practice exercises

For `orders.v1.OrderService/CreateOrder`:

1. Add `idempotency_key` to the Protobuf request and create a table with a unique key over tenant, method, and key.
2. Compute a fingerprint from customer, product, and quantity; exclude the key from the fingerprint.
3. Perform atomic insert/claim, create the order, and store the response in the same transaction.
4. Send two concurrent requests with the same key/payload; verify only one order exists and both callers receive the same order ID.
5. Send the same key with a different quantity; verify the server returns conflict and does not create a second order.
6. Simulate a lost response after commit; retry with the same key and verify the response is replayed.
7. Add a transactional outbox for the `OrderCreated` event and test that the consumer does not process duplicates.

**Completion criteria:** same key and same payload return the same result; same key with a different payload is rejected; concurrent requests create no duplicate side effects; side effects outside the database have their own idempotency mechanism.

### References

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy and RPC replay limits.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): statuses ending a call.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transactions in Spring applications.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
