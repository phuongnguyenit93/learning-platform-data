# Testing PERMISSION_DENIED

In gRPC, **PERMISSION_DENIED** indicates that the caller has been authenticated but does not have permission to perform the requested action. With Spring gRPC, testing this status requires proving that the authorization policy actually rejects the principal, the service returns the correct status, and the business operation does not run after being denied.

PERMISSION_DENIED must be distinguished from UNAUTHENTICATED: in the first case the caller's identity is known but lacks permission; in the second case identity has not been verified or credentials are invalid. This lesson uses the GetPayroll RPC to test an authenticated principal that lacks permission to read payroll data.

## 1. Define the Authentication and Authorization Boundary

The security flow typically has two steps:

1. **Authentication:** verify the token, certificate, or credentials; produce a trusted principal.
2. **Authorization:** check whether the principal has permission to perform the action on the specific resource.

Example:

| Situation | Status |
| --- | --- |
| Missing credentials or invalid/expired token | UNAUTHENTICATED |
| Valid token but missing PAYROLL_READ permission | PERMISSION_DENIED |
| Caller has permission but employee ID does not exist | NOT_FOUND |
| Malformed employee ID | INVALID_ARGUMENT |
| Payroll database temporarily unavailable | UNAVAILABLE |

Do not use PERMISSION_DENIED to represent every security failure. If authentication has not succeeded, the server does not yet have a trusted principal to evaluate permissions.

## 2. RPC Contract and Authenticated Principal

Protobuf example:

~~~proto
syntax = "proto3";

package acme.payroll.v1;

option java_multiple_files = true;
option java_package = "com.acme.payroll.v1";

service PayrollService {
  rpc GetPayroll(GetPayrollRequest) returns (GetPayrollResponse);
}

message GetPayrollRequest {
  string employee_id = 1;
}

message GetPayrollResponse {
  string employee_id = 1;
  int64 gross_amount_minor = 2;
  string currency = 3;
}
~~~

The principal should be built from verified information in the authentication layer. Example internal model:

~~~java
import java.util.Set;

public record AuthenticatedPrincipal(
    String subject,
    String tenantId,
    Set<String> authorities) {}
~~~

Attach the principal to the gRPC Context using a shared key:

~~~java
public final class AuthenticatedPrincipalContext {
    public static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
        Context.key("authenticated-principal");

    private AuthenticatedPrincipalContext() {}
}
~~~

The application's authentication interceptor must verify credentials first, then attach the principal to the context:

~~~java
AuthenticatedPrincipal principal =
    verifiedIdentityResolver.authenticate(headers);

Context context = Context.current().withValue(
    AuthenticatedPrincipalContext.PRINCIPAL,
    principal);

return Contexts.interceptCall(context, call, headers, next);
~~~

This snippet runs after token/certificate verification; do not take subject, tenant, or role from client-supplied metadata and treat it as an authenticated identity. If authentication fails, the interceptor returns UNAUTHENTICATED and does not invoke the service handler.

## 3. Check Permissions Before Accessing Data

Separating policy from the service implementation allows testing authorization independently and keeps permission logic consistent:

~~~java
public interface PayrollAuthorization {
    boolean canReadPayroll(
        AuthenticatedPrincipal principal,
        String employeeId);
}

public interface PayrollRepository {
    Optional<PayrollRecord> findByEmployeeIdAndTenantId(
        String employeeId,
        String tenantId);
}
~~~

The service checks the principal and permissions before reading data:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class PayrollGrpcService
        extends PayrollServiceGrpc.PayrollServiceImplBase {

    private final PayrollAuthorization authorization;
    private final PayrollRepository repository;

    public PayrollGrpcService(
            PayrollAuthorization authorization,
            PayrollRepository repository) {
        this.authorization = authorization;
        this.repository = repository;
    }

    @Override
    public void getPayroll(
            GetPayrollRequest request,
            StreamObserver<GetPayrollResponse> responseObserver) {

        String employeeId = request.getEmployeeId();
        if (employeeId.isBlank()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("employee_id must not be blank")
                    .asRuntimeException());
            return;
        }

        AuthenticatedPrincipal principal =
            AuthenticatedPrincipalContext.PRINCIPAL.get();
        if (principal == null) {
            responseObserver.onError(
                Status.UNAUTHENTICATED
                    .withDescription("authentication is required")
                    .asRuntimeException());
            return;
        }

        if (!authorization.canReadPayroll(principal, employeeId)) {
            responseObserver.onError(
                Status.PERMISSION_DENIED
                    .withDescription("caller cannot read payroll")
                    .asRuntimeException());
            return;
        }

        Optional<PayrollRecord> result =
            repository.findByEmployeeIdAndTenantId(
                employeeId, principal.tenantId());

        if (result.isEmpty()) {
            responseObserver.onError(
                Status.NOT_FOUND
                    .withDescription("payroll resource not found")
                    .asRuntimeException());
            return;
        }

        PayrollRecord payroll = result.get();
        responseObserver.onNext(GetPayrollResponse.newBuilder()
            .setEmployeeId(employeeId)
            .setGrossAmountMinor(payroll.grossAmountMinor())
            .setCurrency(payroll.currency())
            .build());
        responseObserver.onCompleted();
    }
}
~~~

PayrollRecord is an internal data type for this example. In a Spring application, PayrollGrpcService is typically registered through the starter's service registration mechanism and receives PayrollRepository via constructor injection. Checking permissions before calling the repository ensures rejected requests do not access payroll data. Repository queries also bind tenantId from the authenticated principal; do not trust a tenant ID passed by the caller in the request or metadata.

For APIs with a policy to hide resource existence, you may intentionally return NOT_FOUND instead of PERMISSION_DENIED in certain cases. In that case, apply it consistently and ensure queries are scoped by tenant/principal, avoiding leaks via timing or side effects.

## 4. Test PERMISSION_DENIED with an In-Process Server

In-process transport runs the service and generated blocking stub in the same JVM. Tests can install a fixture-only server interceptor to inject an authenticated principal into Context; this interceptor simulates the output of the authentication layer, not the production credential verification mechanism.

Test interceptor:

~~~java
final class TestPrincipalServerInterceptor
        implements ServerInterceptor {

    private final AuthenticatedPrincipal principal;

    TestPrincipalServerInterceptor(
            AuthenticatedPrincipal principal) {
        this.principal = principal;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Context context = Context.current().withValue(
            AuthenticatedPrincipalContext.PRINCIPAL,
            principal);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

JUnit 5 test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PayrollGrpcServiceTest {

    private Server server;
    private ManagedChannel channel;
    private PayrollServiceGrpc.PayrollServiceBlockingStub stub;
    private AtomicInteger repositoryCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        repositoryCalls = new AtomicInteger();

        AuthenticatedPrincipal principal =
            new AuthenticatedPrincipal(
                "user-17", "tenant-a", Set.of("PROFILE_READ"));

        PayrollAuthorization authorization =
            (caller, employeeId) -> false;

        PayrollRepository repository = (employeeId, tenantId) -> {
            repositoryCalls.incrementAndGet();
            return Optional.empty();
        };

        PayrollGrpcService service =
            new PayrollGrpcService(authorization, repository);

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                service,
                new TestPrincipalServerInterceptor(principal)))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = PayrollServiceGrpc.newBlockingStub(channel)
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
    void authenticatedCallerWithoutPermissionGetsPermissionDenied() {
        GetPayrollRequest request = GetPayrollRequest.newBuilder()
            .setEmployeeId("employee-42")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getPayroll(request));

        assertEquals(
            Status.Code.PERMISSION_DENIED,
            error.getStatus().getCode());
        assertEquals(
            "caller cannot read payroll",
            error.getStatus().getDescription());
        assertEquals(0, repositoryCalls.get());
    }
}
~~~

authorization returns false, while the interceptor supplies a valid principal. Thus the test proves the exact **authenticated but unauthorized** case. The repositoryCalls == 0 assertion ensures the service rejects the call before accessing data. directExecutor() is appropriate because the handler in this example is non-blocking; if the handler performs I/O or waits on a latch, use an appropriate executor so it does not block the test thread.

## 5. Test Adjacent Security Branches

Testing only PERMISSION_DENIED is not enough to prove the authentication/authorization boundary is right. Add these cases:

| Principal/Permission | Expected Result | Repository |
| --- | --- | --- |
| No principal | UNAUTHENTICATED | Not called |
| Valid principal, missing PAYROLL_READ | PERMISSION_DENIED | Not called |
| Authorized principal, malformed employee ID | INVALID_ARGUMENT | Not called |
| Authorized principal, resource does not exist | NOT_FOUND | Queried by tenant |
| Authorized principal, resource belongs to valid tenant | Success | Queried by tenant |
| Database error | UNAVAILABLE or appropriate infrastructure mapping | Not converted into a permission error |

A success test must verify that a user with the right authority receives the response, while a user lacking that authority cannot read the data even when knowing a valid employee ID. Also test the tenant boundary: read permission in tenant A does not automatically grant access to tenant B resources.

## 6. Do Not Test by Trusting Client-Sent Headers

An unsafe test often adds x-user-id or x-role to metadata and lets the service treat that as the principal. This only tests header reading, not authentication. Clients can forge those values themselves.

In service authorization tests, use a test-only server interceptor as in the example above to simulate an already verified principal. In authentication integration tests, send fake/valid tokens via the real credential mechanism and verify the authentication interceptor:

- A valid token produces a principal with the expected subject, tenant, and authorities.
- A missing, invalidly signed, wrong-issuer, or expired token returns UNAUTHENTICATED.
- A valid token lacking permission returns PERMISSION_DENIED.
- Forged role or tenant metadata cannot elevate the caller's privileges.

Do not use the test principal interceptor in production. Do not log access tokens, private claims, or sensitive information.

## 7. Check Policy and Side Effects

For read RPCs, tests verify the repository is not called when authorization fails. For write RPCs, stronger checks are required:

1. Policy rejects before any transaction creates or updates data.
2. No domain events are emitted, no messages are sent, and no downstream services are called.
3. No success audit event is written; if denial auditing is needed, write a dedicated event with restricted access.
4. No resource state or cache is modified.
5. When policy permits, the operation still respects tenant scope and business rules.

Do not only assert the status code. A service might return PERMISSION_DENIED after having already performed a side effect; test repository/mock invocations and data state to catch this bug.

## 8. Status Description and Information Leak Prevention

The status description is sent back to the caller. Keep messages short, stable, and free of internal rules, specific roles, user lists, or sensitive resource data. For example, caller cannot read payroll is sufficient for a public API; policy details can be recorded in a separately protected audit log.

If the API must hide resources from callers, the decision to return NOT_FOUND must be applied consistently for both non-existent and out-of-scope resources. Do not let status, message, response time, or side effects reveal a difference.

## 9. Test Through the Spring Application Context

In-process tests verify the service implementation, principal context, and status mapping. They do not prove that the Spring starter has properly registered the interceptors or authentication provider. Add integration tests that boot the application context to verify:

- The authentication interceptor runs before the service handler.
- A valid token creates the expected principal.
- The authorization policy reads authorities from the verified principal.
- Interceptors do not turn PERMISSION_DENIED into UNKNOWN.
- Repositories and downstream services are not called upon denial.
- TLS, metadata, and credentials work over a real transport if required by deployment.

How interceptors are registered depends on the starter/version. Use the server interceptor extension point of the library in use; do not assume every Spring gRPC starter shares the same annotations or properties.

## 10. Recommended Test Matrix

| Category | Scenario | Assertion |
| --- | --- | --- |
| Authentication | Missing or invalid token | UNAUTHENTICATED |
| Authorization | Valid principal but lacking permission | PERMISSION_DENIED |
| Resource | Authorized but resource does not exist | NOT_FOUND |
| Tenant | Authorized in a different tenant | Denied or hidden per policy |
| Side effect | Rejected request | No repository read/write beyond required policy checks; no downstream call |
| Success | Authorized principal and valid resource | Expected response |
| Error mapping | Blocking/async client | Both receive the exact status |
| Spring wiring | Real application context | Authentication and authorization interceptors registered properly |

Prefer asserting Status.Code.PERMISSION_DENIED rather than only comparing description strings. Messages may change, whereas status semantics must remain stable for clients and retry policies.

## 11. Takeaways and Self-Check

**Testing PERMISSION_DENIED** must use an authenticated principal that lacks permission, verify the server returns the exact status, and ensure the forbidden operation is not executed. Use gRPC Context to pass the principal from the authentication interceptor, separate authorization policy from the repository, and test with an in-process server and generated blocking stub. Add Spring integration tests to verify interceptors/credentials are wired properly in the application context.

Self-check:

1. Why does PERMISSION_DENIED differ from UNAUTHENTICATED?
2. Why must the principal come from a verified authentication layer rather than client-sent metadata?
3. Why must tests verify that the repository is not called when policy denies access?
4. When can an API return NOT_FOUND instead of PERMISSION_DENIED to prevent resource enumeration?
5. How do you ensure permissions for one tenant do not apply to another tenant's resources?
6. Which parts of Spring authentication integration can an in-process test not prove?

Testing authorization properly helps Spring gRPC enforce policies consistently, prevent unauthorized access, and ensure data is neither read nor modified after a request has been denied.
