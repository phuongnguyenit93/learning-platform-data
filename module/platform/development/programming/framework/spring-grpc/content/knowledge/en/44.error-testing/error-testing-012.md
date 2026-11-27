# Asserting Status, Description, and Metadata

In Spring gRPC, an RPC error has three important pieces of information that the client can observe: the canonical status code, the description attached to the status, and the metadata sent in trailers. The status code classifies the outcome so the client can decide how to act; the description helps operators or users understand the error; metadata carries business error codes, request IDs, or machine-readable information agreed upon by both sides.

Error contract tests must verify all three parts at the RPC boundary. A test that only checks whether an exception was thrown is not enough: NOT_FOUND, INVALID_ARGUMENT, and UNAVAILABLE can all surface as StatusRuntimeException yet lead to very different handling. This lesson presents how to construct status/trailers on the server, read them on the client, write stable assertions, and avoid leaking internal data.

## 1. Three Parts of a gRPC Error Response

| Component | Role | How Client Reads It |
| --- | --- | --- |
| Status code | Classifies the RPC outcome per canonical gRPC status | Status.fromThrowable(error).getCode() |
| Description | Short message attached to Status, typically for diagnostics or display | Status.getDescription() |
| Trailers metadata | Additional key/value pairs per contract, e.g., error-code and request ID | StatusRuntimeException.getTrailers() |

For example, an order-not-found error might have:
- Status: NOT_FOUND.
- Description: Order was not found.
- Trailers: error-code=ORDER_NOT_FOUND and x-request-id=req-42.

The status code is the primary control signal. Clients should not parse the description string to decide retries or business branches. If a machine-readable code is needed, define a stable custom trailer key or use a structured error detail per contract. The description can evolve in wording for localization or better UX without changing semantics.

gRPC reserves protocol fields for status and message. Applications do not manually create grpc-status or grpc-message metadata keys; use the Status API to set them and custom keys for application metadata.

## 2. Choose the Right Status Code for the Situation

The status must describe what the client can do next:

| Situation | Appropriate Status | Client Handling |
| --- | --- | --- |
| Request missing ID or malformed | INVALID_ARGUMENT | Fix request |
| Resource does not exist | NOT_FOUND | Show not-found state or handle fallback |
| Resource already exists on creation | ALREADY_EXISTS | Read existing resource or pick another identifier |
| Caller not authenticated | UNAUTHENTICATED | Provide/refresh credentials |
| Caller authenticated but lacks permission | PERMISSION_DENIED | Do not retry unless permissions change |
| Current state does not allow the operation | FAILED_PRECONDITION | Change state first |
| Transaction conflict requiring restart | ABORTED | Retry workflow if safe |
| Dependency temporarily unavailable | UNAVAILABLE | Retry with backoff if operation is safe |
| Quota or resource limit exhausted | RESOURCE_EXHAUSTED | Shed load or wait for quota |
| Deadline expired | DEADLINE_EXCEEDED | Handle uncertain outcome; conditional retry |
| Unexpected server-side error | INTERNAL | Report system error without leaking internal details |

Do not use INTERNAL for every error to mask missing mappings. Nor should you return INVALID_ARGUMENT for dependency failures. The status code is the part of the contract clients rely on to choose retries, ask users to fix input, or stop the operation.

## 3. Construct Status, Description, and Trailers on the Server

gRPC Java represents custom metadata using Metadata.Key. Keys must be lowercase; keys holding bytes end with the -bin suffix. Example defining two ASCII keys:

~~~java
public final class OrderErrorMetadata {
    private OrderErrorMetadata() {}

    public static final Metadata.Key<String> ERROR_CODE =
            Metadata.Key.of(
                    "error-code",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);
}
~~~

Construct a NOT_FOUND error with description and trailers:

~~~java
public final class OrderGrpcErrors {
    private OrderGrpcErrors() {}

    public static StatusRuntimeException notFound(String requestId) {
        Metadata trailers = new Metadata();
        trailers.put(OrderErrorMetadata.ERROR_CODE, "ORDER_NOT_FOUND");
        trailers.put(OrderErrorMetadata.REQUEST_ID, requestId);

        return Status.NOT_FOUND
                .withDescription("Order was not found")
                .asRuntimeException(trailers);
    }
}
~~~

The server handler sends the exception via onError:

~~~java
@GrpcService
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderRepository repository;

    public OrderGrpcService(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<Order> observer) {
        try {
            Order order = repository.findById(request.getOrderId())
                    .orElseThrow(OrderNotFoundException::new);

            observer.onNext(order);
            observer.onCompleted();
        } catch (OrderNotFoundException error) {
            observer.onError(
                    OrderGrpcErrors.notFound("req-test-42"));
        }
    }
}
~~~

req-test-42 is only an illustrative value for tests. In a real application, the request ID should come from per-call metadata/interceptors or tracing context. Do not store the request ID in a mutable field on a singleton service because multiple RPCs can execute concurrently.

Once observer.onError is called, that is the RPC's terminal signal. Do not subsequently call onCompleted or onNext. For unexpected exceptions, map to INTERNAL with a safe description and log the stack trace on the server; do not send SQL, internal hostnames, file paths, tokens, or stack traces in trailers.

## 4. Assert Status Code on the Client

A blocking stub typically throws StatusRuntimeException when an RPC ends with a non-OK status. Use Status.fromThrowable to retrieve the canonical status:

~~~java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("missing")
                        .build()));

Status status = Status.fromThrowable(error);
assertEquals(Status.Code.NOT_FOUND, status.getCode());
~~~

If the test catches StatusRuntimeException directly, it can read error.getStatus(). Using Status.fromThrowable is helpful when the error is wrapped in another exception or passes through a callback layer; it searches the cause chain for a status and may return UNKNOWN if no specific status is found.

Do not only assert the exception type. An accidental change from NOT_FOUND to INTERNAL still makes assertThrows(StatusRuntimeException.class) pass, yet breaks the behavior contract.

## 5. Assert Descriptions Deliberately

Retrieve the description from Status:

~~~java
Status status = Status.fromThrowable(error);
assertEquals("Order was not found", status.getDescription());
~~~

Only assert the exact full description if that wording is part of the public contract and must stay stable. In many APIs, the description is a diagnostic message that can be refined; in those cases verify it is present or satisfies safety rules, while client logic relies on the status code and error-code metadata.

Example checking that the description is non-empty:

~~~java
assertNotNull(status.getDescription());
assertFalse(status.getDescription().isBlank());
~~~

Do not use the description as an error code via string comparisons in production code. Nor should you stuff sensitive data or implementation details into the description, because this value may be forwarded to clients and logged in multiple places.

## 6. Assert Custom Metadata in Trailers

When the server creates a StatusRuntimeException via asRuntimeException(trailers), the client can read custom metadata from getTrailers():

~~~java
Metadata trailers = error.getTrailers();

assertNotNull(trailers);
assertEquals(
        "ORDER_NOT_FOUND",
        trailers.get(OrderErrorMetadata.ERROR_CODE));
assertEquals(
        "req-test-42",
        trailers.get(OrderErrorMetadata.REQUEST_ID));
~~~

Trailers may be null if the server did not send custom metadata or the failure occurred before metadata was constructed. If the contract requires a key, assert trailers is non-null and then assert the value; if a key is optional, treat null as a valid case.

Metadata keys and marshallers must match on both sides. Use ASCII_STRING_MARSHALLER for ASCII values. Use a -bin suffix and BINARY_BYTE_MARSHALLER for binary values:

~~~java
static final Metadata.Key<byte[]> ERROR_DETAIL =
        Metadata.Key.of(
                "error-detail-bin",
                Metadata.BINARY_BYTE_MARSHALLER);
~~~

Do not manually base64-encode bytes before putting them into binary metadata; the gRPC marshaller handles wire encoding. Do not use the same key sometimes as ASCII and sometimes as binary.

## 7. Provider Contract Test Using an In-Process Server

Testing through a generated stub verifies status, description, and trailers flowing through the gRPC runtime. In-process transport is fast and requires no TCP port:

~~~java
class OrderErrorContractTest {
    private Server server;
    private ManagedChannel channel;
    private OrderServiceGrpc.OrderServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .addService(new OrderGrpcService(new MissingOrderRepository()))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName).build();
        stub = OrderServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(1, TimeUnit.SECONDS);
        server.awaitTermination(1, TimeUnit.SECONDS);
    }

    @Test
    void notFoundErrorPreservesStatusDescriptionAndTrailers() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getOrder(
                        GetOrderRequest.newBuilder()
                                .setOrderId("missing")
                                .build()));

        Status status = Status.fromThrowable(error);
        assertEquals(Status.Code.NOT_FOUND, status.getCode());
        assertEquals("Order was not found", status.getDescription());

        Metadata trailers = error.getTrailers();
        assertNotNull(trailers);
        assertEquals(
                "ORDER_NOT_FOUND",
                trailers.get(OrderErrorMetadata.ERROR_CODE));
        assertEquals(
                "req-test-42",
                trailers.get(OrderErrorMetadata.REQUEST_ID));
    }
}
~~~

MissingOrderRepository is a fixture returning Optional.empty(). The test uses the real service implementation and generated blocking stub, so it verifies both the provider mapping and how the client receives the error. In a real test suite, always shut down the channel/server in teardown; a finite deadline prevents tests from hanging when the server does not respond.

In-process tests do not verify TLS, proxies, or network failures. If metadata traverses a gateway/service mesh, add integration tests in the corresponding environment to confirm trailers are forwarded per contract.

## 8. Test That INTERNAL Errors Do Not Leak Information

A dedicated test should verify unexpected errors do not leak internal exceptions:

~~~java
@Test
void unexpectedFailureReturnsSafeInternalError() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stubWithBrokenRepository.getOrder(request));

    Status status = Status.fromThrowable(error);
    assertEquals(Status.Code.INTERNAL, status.getCode());
    assertEquals("Internal server error", status.getDescription());

    String description = status.getDescription();
    assertFalse(description.contains("SELECT"));
    assertFalse(description.contains("jdbc:"));
}
~~~

In production, log the full exception on the server with trace/request IDs and appropriate access controls. Responses sent to the client should contain only a safe message alongside a stable error code. Avoid logging authorization metadata, tokens, or full trailers if they might contain sensitive data.

## 9. Common Assertion Mistakes

| Test Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Only asserting StatusRuntimeException | Does not distinguish NOT_FOUND, INTERNAL, or UNAVAILABLE | Assert Status.Code |
| Parsing description to decide retries | Wording may change or be localized | Use status and error-code metadata |
| Assuming getTrailers is always non-null | Not every error includes custom trailers | Check for null per contract |
| Using uppercase keys or grpc-* keys | Violates application metadata rules | Use lowercase keys; do not hijack protocol prefixes |
| Using ASCII marshaller for bytes | Encoding type mismatches contract | Use -bin suffix and binary marshaller |
| Sending stack traces in description | Exposes implementation and internal details | Use safe messages, log details on server |
| Asserting all unrelated metadata | Tests become brittle when independent keys are added | Assert only keys belonging to the contract |
| Omitting test deadlines | Tests can hang indefinitely | Use finite deadlines and proper teardown |

For metadata that can appear multiple times, define clear cardinality and use getAll(key) to inspect all values. For single-valued keys, test duplicate behavior rather than randomly relying on the first value read.

## 10. Checklist and Self-Check

- [ ] Assert the canonical status code for each business condition.
- [ ] Only assert the exact description if wording is a stable contract.
- [ ] Do not let clients parse descriptions to control retry/business flow.
- [ ] Custom trailer keys use lowercase and the matching marshaller type.
- [ ] Binary metadata uses the -bin suffix and BINARY_BYTE_MARSHALLER.
- [ ] Assert required metadata is present with the expected value.
- [ ] Handle null trailers if allowed by the contract.
- [ ] Unexpected errors return a safe description without leaking stack traces.
- [ ] Provider tests invoke through a generated stub and in-process server.
- [ ] Tests have finite deadlines and release channels/servers.
- [ ] Do not log tokens, credentials, or sensitive metadata.
- [ ] Include integration tests through proxies if production uses a gateway/service mesh.

**Self-Check**

**Question 1.** Why is assertThrows(StatusRuntimeException.class) not enough?

*Answer:* Many canonical statuses are thrown as the same exception type. Tests must verify Status.Code to protect the semantics clients rely on.

**Question 2.** When should you assert the exact description?

*Answer:* When the wording is a public message that must remain stable. If the description is purely diagnostic, avoid treating it as a machine contract and check status/error codes instead.

**Question 3.** Where should a custom error-code be placed?

*Answer:* In custom trailers metadata under a stably defined key, such as error-code. Do not manually create grpc-status or grpc-message because those are protocol fields managed by gRPC.

**Question 4.** Why can getTrailers() be null?

*Answer:* The server may not send custom trailers, or the error may occur before metadata is built. Tests should reflect whether a key is required or optional per contract.

**Question 5.** Why should stack traces not be sent in the description?

*Answer:* The description is transmitted to the client and may appear in logs. Stack traces can expose SQL, file paths, hostnames, or internal details; keep them in controlled server-side logs.

Status, description, and metadata assertions form a testable error contract at the RPC boundary. The status code protects how clients classify errors, the description provides safe human-readable context, and trailers carry structured error codes/request IDs. When provider tests verify all three through a generated stub, Spring gRPC versions can evolve implementations while preserving clear, stable error behavior for consumers.
