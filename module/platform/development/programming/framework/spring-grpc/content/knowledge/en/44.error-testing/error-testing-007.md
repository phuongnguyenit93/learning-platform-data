# Testing RESOURCE_EXHAUSTED

In gRPC, **RESOURCE_EXHAUSTED** indicates that a required resource has run out or an applied limit has been exceeded. With Spring gRPC, common causes include per-tenant quotas, rate limits, concurrency limits, storage capacity, or message sizes exceeding configuration. Tests must verify the exact status, ensure no side effects occur when a request is rejected, and distinguish quota exhaustion from availability errors.

RESOURCE_EXHAUSTED does not mean the server is down. The server may still be healthy and processing requests from other callers, while one tenant has exhausted its quota or a specific request exceeds the message limit. Therefore, tests must verify the exact scope of the limit: user, tenant, method, server instance, or transport.

## 1. Causes Leading to RESOURCE_EXHAUSTED

| Cause | Limit Scope | Typical Expected Behavior |
| --- | --- | --- |
| Per-tenant/user quota | One tenant or caller | Reject usage exceeding allowance |
| Rate limit | Request count within a time window | Reject requests exceeding rate |
| Concurrency limit | Number of concurrently running tasks | Reject or queue per policy |
| Message size limit | Single request or response | Reject messages exceeding configured size |
| Storage/resource capacity | System storage or capacity | Reject operations requiring more resources |

Distinguish from other statuses:

| Status | Meaning |
| --- | --- |
| RESOURCE_EXHAUSTED | Caller or request exceeded a resource/quota limit |
| UNAVAILABLE | Service or dependency cannot currently serve requests |
| DEADLINE_EXCEEDED | RPC time budget expired |
| INVALID_ARGUMENT | Request data violates contract |
| FAILED_PRECONDITION | Current state does not allow executing the operation |

For example, a tenant that has used up its upload capacity returns RESOURCE_EXHAUSTED; a database disconnection while checking quota returns an appropriate availability error rather than pretending quota is exhausted. A request containing a file larger than the max inbound message size can also be rejected by the transport with RESOURCE_EXHAUSTED before the service handler runs.

## 2. RPC Contract Used in the Example

Suppose a service accepts uploaded content:

~~~proto
syntax = "proto3";

package acme.storage.v1;

option java_multiple_files = true;
option java_package = "com.acme.storage.v1";

service UploadService {
  rpc Upload(UploadRequest) returns (UploadResponse);
}

message UploadRequest {
  string object_name = 1;
  bytes payload = 2;
}

message UploadResponse {
  string object_id = 1;
  int64 stored_bytes = 2;
}
~~~

The tenant is taken from the authenticated principal in the gRPC Context. Do not trust a tenant ID supplied by the client in the payload or metadata when deciding quotas.

Declare a context key shared by the service and the authentication interceptor:

~~~java
import io.grpc.Context;

public final class TenantContext {
    public static final Context.Key<String> TENANT_ID =
        Context.key("authenticated-tenant-id");

    private TenantContext() {}
}
~~~

## 3. Map Quota Exhaustion to RESOURCE_EXHAUSTED

Separate quota checking and storage into two abstractions:

~~~java
public interface QuotaService {
    boolean allows(String tenantId, long requestedBytes);
}

public interface UploadRepository {
    UploadResponse store(
        String tenantId,
        UploadRequest request);
}
~~~

The service checks quota before calling the repository:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class UploadGrpcService
        extends UploadServiceGrpc.UploadServiceImplBase {

    private final QuotaService quotaService;
    private final UploadRepository repository;

    public UploadGrpcService(
            QuotaService quotaService,
            UploadRepository repository) {
        this.quotaService = quotaService;
        this.repository = repository;
    }

    @Override
    public void upload(
            UploadRequest request,
            StreamObserver<UploadResponse> responseObserver) {

        if (request.getObjectName().isBlank()
                || request.getPayload().isEmpty()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("object_name and payload are required")
                    .asRuntimeException());
            return;
        }

        String tenantId = TenantContext.TENANT_ID.get();
        if (tenantId == null) {
            responseObserver.onError(
                Status.UNAUTHENTICATED
                    .withDescription("authentication is required")
                    .asRuntimeException());
            return;
        }

        long requestedBytes = request.getPayload().size();
        if (!quotaService.allows(tenantId, requestedBytes)) {
            responseObserver.onError(
                Status.RESOURCE_EXHAUSTED
                    .withDescription("tenant storage quota exceeded")
                    .asRuntimeException());
            return;
        }

        UploadResponse response = repository.store(tenantId, request);
        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
~~~

This example illustrates the check boundary. In a production system, checking and reserving quota must be atomic or use a reservation/lease; if you only call allows and then write data, two concurrent requests can observe the remaining quota simultaneously and exceed the limit. Reservations should be committed on storage success and released on storage failure.

Do not call the repository, emit events, or send messages before the quota is accepted. If the quota service is unavailable, map the error to the infrastructure condition, such as UNAVAILABLE; do not turn that error into RESOURCE_EXHAUSTED.

## 4. Propagate Tenant Context in Tests

Tests can use a server interceptor to attach an authenticated tenant to the gRPC Context. This interceptor is strictly a fixture for testing service logic:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;

final class TestTenantServerInterceptor
        implements ServerInterceptor {

    private final String tenantId;

    TestTenantServerInterceptor(String tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Context context = Context.current().withValue(
            TenantContext.TENANT_ID, tenantId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

In production, tenant context must come from a verified authentication layer. Do not use arbitrary client-sent headers to construct tenant identity.

## 5. Test Quota Using an In-Process gRPC Server

In-process transport is well-suited for testing quota logic, status mapping, and ensuring the repository is not called when quota is exhausted:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import com.google.protobuf.ByteString;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class UploadQuotaTest {

    private Server server;
    private ManagedChannel channel;
    private UploadServiceGrpc.UploadServiceBlockingStub stub;
    private AtomicInteger repositoryCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        repositoryCalls = new AtomicInteger();

        QuotaService exhaustedQuota =
            (tenantId, requestedBytes) -> false;

        UploadRepository repository = (tenantId, request) -> {
            repositoryCalls.incrementAndGet();
            return UploadResponse.newBuilder()
                .setObjectId("object-123")
                .setStoredBytes(request.getPayload().size())
                .build();
        };

        UploadGrpcService service =
            new UploadGrpcService(exhaustedQuota, repository);

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                service,
                new TestTenantServerInterceptor("tenant-a")))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = UploadServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void exhaustedTenantQuotaReturnsResourceExhaustedBeforeStore() {
        UploadRequest request = UploadRequest.newBuilder()
            .setObjectName("archive.bin")
            .setPayload(ByteString.copyFrom(new byte[1024]))
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.upload(request));

        assertEquals(
            Status.Code.RESOURCE_EXHAUSTED,
            error.getStatus().getCode());
        assertEquals(
            "tenant storage quota exceeded",
            error.getStatus().getDescription());
        assertEquals(0, repositoryCalls.get());
    }
}
~~~

The test example uses a fake quota that always rejects to reproduce a tenant that has exhausted its allowance. The key assertions are the exact status code and that the repository is not called. You can add a test where quota allows the request to prove valid requests are still stored and return the expected size.

directExecutor() works for short, non-blocking handlers. If the quota service calls a database or remote quota server, use an appropriate executor and a separate deadline; do not block transport threads.

## 6. Test Messages Exceeding maxInboundMessageSize

Business quotas and transport size limits are two separate mechanisms. To test the message limit, run a real transport server with a small max inbound message size:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.protobuf.ByteString;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class UploadMessageSizeTest {

    @Test
    void requestLargerThanServerLimitReturnsResourceExhausted()
            throws Exception {
        Server server = ServerBuilder.forPort(0)
            .maxInboundMessageSize(256)
            .addService(new UploadGrpcService(
                (tenantId, bytes) -> true,
                (tenantId, request) -> UploadResponse.getDefaultInstance()))
            .build()
            .start();

        ManagedChannel channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", server.getPort())
            .usePlaintext()
            .build();

        try {
            UploadServiceGrpc.UploadServiceBlockingStub stub =
                UploadServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(2, TimeUnit.SECONDS);

            UploadRequest request = UploadRequest.newBuilder()
                .setObjectName("large.bin")
                .setPayload(ByteString.copyFrom(new byte[4096]))
                .build();

            StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.upload(request));

            assertEquals(
                Status.Code.RESOURCE_EXHAUSTED,
                error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }
}
~~~

The request has a payload larger than the 256-byte limit, so it is rejected by the server transport before the service handler runs. Thus this test verifies the message limit, not the quota service. If the project uses shaded Netty, ensure runtime server/channel providers and dependencies are compatible; do not mix shaded and unshaded classes.

The client also has an inbound message limit for responses. If a response exceeds the client's receive limit, the client can observe RESOURCE_EXHAUSTED even though the server sent the response. When diagnosing, identify whether the limit sits at server request, server response, client inbound, or proxy.

## 7. Distinguish Quota, Rate Limit, and Concurrency Limit

These policies can all use RESOURCE_EXHAUSTED but require different tests:

| Policy | Condition Checked | Assertion |
| --- | --- | --- |
| Cumulative quota | Total bytes/requests in period exceed allowance | Request exceeding remainder is rejected |
| Rate limit | Call count in time window exceeds threshold | Calls exceeding rate receive RESOURCE_EXHAUSTED |
| Concurrency | Active running tasks reach limit | New tasks are rejected or queued per policy |
| Message size | Serialized message exceeds limit | Transport rejects before handler |

For concurrency tests, use latches/barriers to hold the initial calls in flight, then send calls beyond the limit. Do not rely on Thread.sleep() to create races. When releasing the latch, verify permits are returned so subsequent calls can succeed.

## 8. Retries and Client Guidance

Do not automatically retry every RESOURCE_EXHAUSTED:

- Requests exceeding message size cannot succeed by resending the same payload; callers must split the data or change encoding per contract.
- Cumulative quotas require waiting for the next quota period or increasing limits.
- Rate limits can be retried after a wait if the server advertises a reasonable time.
- Concurrency limits can be retried after a short backoff if sufficient overall deadline remains.
- Full storage requires freeing or expanding capacity before retrying.

If the API can determine when to retry, it can return the google.rpc.RetryInfo rich error detail. If no specific time is available, clients use exponential backoff with jitter and cap retry attempts. Do not retry aggressively because it can worsen quota/rate limit pressure.

For write RPCs, use an idempotency key to prevent duplicate data when the server received the request but the response was lost. Retries must stay within the logical operation's overall deadline.

## 9. Rich Error Detail for Quota Failures

When clients need to know which quota was exceeded, you can use the google.rpc.QuotaFailure rich error model. Include only information the caller is authorized to see; do not expose another tenant's quota or internal configuration:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.QuotaFailure;
import com.google.rpc.Status;
import io.grpc.protobuf.StatusProto;

QuotaFailure failure = QuotaFailure.newBuilder()
    .addViolations(QuotaFailure.Violation.newBuilder()
        .setSubject("tenant-storage")
        .setDescription("storage quota exceeded")
        .build())
    .build();

com.google.rpc.Status richStatus = com.google.rpc.Status.newBuilder()
    .setCode(io.grpc.Status.Code.RESOURCE_EXHAUSTED.value())
    .setMessage("resource limit exceeded")
    .addDetails(Any.pack(failure))
    .build();

responseObserver.onError(
    StatusProto.toStatusRuntimeException(richStatus));
~~~

Clients can read the detail using StatusProto.fromThrowable(error) and unpack the corresponding type. If a proxy does not preserve trailers, the basic status code and message must still suffice for the client to handle the error. Do not place sensitive information such as another tenant's remaining quota into details.

## 10. Test Through the Spring Application Context

In-process tests verify service logic and status mapping, but do not prove the starter registers the service, interceptors, quota provider, or transport limits properly. Add Spring integration tests to:

- Boot the application context with a fake quota provider or test implementation.
- Call the RPC through the server managed by the Spring gRPC starter.
- Verify the tenant is extracted from the authenticated principal.
- Verify quota rejection happens before the repository and event publisher.
- Verify max inbound message size is properly configured on the server.
- Verify metadata, rich error details, and TLS if production uses them.

The property name for configuring message size and server extension points depend on the starter/version. Use your project's actual API; do not assume a single property is shared across every Spring gRPC starter.

## 11. Recommended Test Matrix

| Scenario | Status/Result | Side Effect |
| --- | --- | --- |
| Tenant within quota | Success | Stored exactly once |
| Tenant exceeds quota | RESOURCE_EXHAUSTED | Not stored |
| Rate limit threshold exceeded | RESOURCE_EXHAUSTED | Rejected calls not processed |
| Concurrency limit reached | RESOURCE_EXHAUSTED or queued per policy | Permit released when call finishes |
| Request exceeds max inbound size | RESOURCE_EXHAUSTED | Handler does not run |
| Quota provider unavailable | UNAVAILABLE or appropriate infrastructure error | Not faked as quota exhausted |
| Request has invalid fields | INVALID_ARGUMENT | Neither quota checked nor stored |
| Quota replenished | New request succeeds | Stored exactly once |

Tests should verify status code, repository invocations, permit/reservation lifecycle, and recovery behavior. Do not assert only the description because messages may change across versions.

## 12. Takeaways and Self-Check

**Testing RESOURCE_EXHAUSTED** needs to cover both business limits and transport limits. Use an in-process server to test quota/rate/concurrency and prove there are no side effects; use real transport with maxInboundMessageSize to test that oversized requests are rejected before the handler. Distinguish RESOURCE_EXHAUSTED from UNAVAILABLE, retry only when policy permits, and preserve idempotency for write RPCs.

Self-check:

1. Why does an exhausted quota not mean the server is unavailable?
2. Why must quota checks be atomic when multiple requests arrive concurrently?
3. Which test proves the repository is not called when a tenant runs out of quota?
4. Why do messages exceeding max inbound size require a transport test?
5. When can a client retry RESOURCE_EXHAUSTED?
6. Why do write RPCs need an idempotency key when retrying after a resource error?

Testing RESOURCE_EXHAUSTED properly helps Spring gRPC enforce predictable resource limits, protect services from overload, and give clients clear recovery guidance.
