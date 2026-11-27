# Testing Allow, Deny, and Missing Context

## Learning Objectives

After this lesson, you will be able to:

- Distinguish three authorization outcomes: allow, deny, and missing context.
- Choose the right status for an authenticated principal lacking permissions versus a missing principal.
- Write unit tests for permission policies and integration tests through the gRPC runtime.
- Verify that the interceptor genuinely blocks the handler on deny, rather than returning a status after business code has already executed.
- Verify authentication runs before authorization and both use the shared Context key.
- Test undeclared methods, spoofed metadata, tenant/resource boundaries, and concurrent requests.
- Test streaming RPC authorization, cancellation, and cleanup.
- Organize reusable test fixtures in Spring gRPC applications.

## 1. Three States to Distinguish

In **SPRING_GRPC**, authentication verifies the caller and creates a principal; authorization decides whether the principal is allowed to call a method or act on a resource. When testing, distinguish three commonly confused states:

| State | Principal in Context | Required permission | Expected result |
| --- | --- | --- | --- |
| **Allow** | Verified principal present | Sufficient permissions | RPC proceeds to handler |
| **Deny** | Verified principal present | Missing permission or policy denies | **PERMISSION_DENIED**, handler does not run |
| **Missing context** | No principal | Cannot evaluate caller permissions | **UNAUTHENTICATED**, handler does not run |

**Missing context is not the same as deny.** Deny means the server knows who the caller is, yet policy disallows the action. Missing context means authorization has no trusted principal; usually authentication did not run, credentials were invalid, or Context was not propagated properly.

Distinguishing both cases exposes interceptor configuration bugs. If tests only check for PERMISSION_DENIED, an authentication bug that fails to set the principal can stay hidden.

~~~mermaid
flowchart TD
    A["RPC arrives at server"] --> B{"Verified principal in Context?"}
    B -- "No" --> C["UNAUTHENTICATED"]
    B -- "Yes" --> D{"Policy allows method/resource?"}
    D -- "No" --> E["PERMISSION_DENIED"]
    D -- "Yes" --> F["Invoke service handler"]
    C --> G["Handler does not run"]
    E --> G
    F --> H["Assert business result"]
~~~

A proper authorization test must verify both **status** and **side effects**. Merely observing that the client received PERMISSION_DENIED does not prove the handler did not run before the call closed.

## 2. Identifying Boundaries to Test

Authorization is usually implemented across multiple layers. Each layer needs an appropriate test type:

| Component | What to verify | Appropriate test type |
| --- | --- | --- |
| Permission policy | Mapping of methods/resources to permissions | Unit test |
| Principal and Context key | Principal is stored and read via the exact same key | Unit test and interceptor test |
| Authentication interceptor | Valid credentials produce principal; invalid ones are rejected | Interceptor test |
| Authorization interceptor | Allow/deny/missing context and handler not called on deny | Unit test with fake call or in-process test |
| gRPC server pipeline | Interceptor order, actual status, generated stub | In-process integration test |
| Spring gRPC configuration | Beans/extension points and real server use the right interceptors | Spring application integration test |
| Resource authorization | Tenant, ownership, and domain state | Application/repository integration test |
| Streaming handler | Every message checked and resources cleaned up | Streaming integration test |

Policy unit tests run fast and cover many mappings. However, they do not prove interceptors are registered properly, Context propagates across listeners, or clients actually receive the expected status. Therefore, at least one integration test layer through the gRPC runtime is required.

## 3. Unit Testing the Permission Policy

A policy usually accepts a principal and the full method name from the server-side MethodDescriptor. Tests should cover permitted methods, methods missing permissions, and unmapped methods.

Simple policy example:

~~~java
public final class GrpcMethodPolicy {

    private final Map<String, String> requiredPermissions = Map.of(
            OrderServiceGrpc.getGetOrderMethod().getFullMethodName(),
            "orders:read",
            OrderServiceGrpc.getCancelOrderMethod().getFullMethodName(),
            "orders:cancel");

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        if (principal == null) {
            return false;
        }

        String required = requiredPermissions.get(fullMethodName);
        return required != null
                && principal.hasPermission(required);
    }
}
~~~

JUnit 5:

~~~java
class GrpcMethodPolicyTest {

    private final GrpcMethodPolicy policy = new GrpcMethodPolicy();

    @Test
    void allowsMethodWhenPrincipalHasRequiredPermission() {
        GrpcPrincipal principal = new GrpcPrincipal(
                "user-1",
                "tenant-a",
                Set.of("orders:read"));

        String method =
                OrderServiceGrpc.getGetOrderMethod().getFullMethodName();

        assertTrue(policy.allows(principal, method));
    }

    @Test
    void deniesMethodWhenPermissionIsMissing() {
        GrpcPrincipal principal = new GrpcPrincipal(
                "user-1",
                "tenant-a",
                Set.of("orders:read"));

        String method =
                OrderServiceGrpc.getCancelOrderMethod().getFullMethodName();

        assertFalse(policy.allows(principal, method));
    }

    @Test
    void deniesMethodWithoutExplicitPolicy() {
        GrpcPrincipal principal = new GrpcPrincipal(
                "user-1",
                "tenant-a",
                Set.of("orders:read", "orders:cancel"));

        assertFalse(policy.allows(
                principal,
                "demo.admin.v1.AdminService/DisableAccount"));
    }
}
~~~

These three tests check three core properties:

- The right permission allows the right method.
- A principal missing the permission must be denied.
- An undeclared method must be denied under **deny-by-default**.

Never pass a client-declared method name from metadata as input to the policy. In production, the full method name must come from **call.getMethodDescriptor().getFullMethodName()**. Unit tests can pass strings directly to verify mappings; integration tests verify the interceptor reads the right descriptor.

## 4. Interceptor Tests Must Verify Whether the Handler Runs

An authorization interceptor typically has two branches:

- Allow: call **next.startCall(call, headers)**.
- Deny or missing context: close the call and return an empty listener, without calling next.

You can use a fake ServerCall/ServerCallHandler to unit test this branch, provided the fake accurately models the behavior under test. A stronger approach is calling through an in-process gRPC server with a counter inside the service implementation.

Example service with a side-effect counter:

~~~java
public final class TestOrderService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final AtomicInteger invocations;

    public TestOrderService(AtomicInteger invocations) {
        this.invocations = invocations;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        invocations.incrementAndGet();

        responseObserver.onNext(
                GetOrderResponse.newBuilder()
                        .setOrderId(request.getOrderId())
                        .build());
        responseObserver.onCompleted();
    }
}
~~~

For a deny test, assert both conditions:

~~~java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> blockingStub.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-1")
                        .build()));

assertEquals(
        Status.Code.PERMISSION_DENIED,
        error.getStatus().getCode());

assertEquals(0, invocations.get());
~~~

The counter should represent the entry point of the business handler or a critical side effect. For data-mutating use cases, in addition to the invocation counter, verify the database is unchanged, the outbox has no events, and downstream mocks were not called.

## 5. Using In-Process gRPC to Verify Actual Statuses

grpc-java provides an in-process transport for standing up a server and channel in the same process. Tests do not need to open a TCP port yet still exercise gRPC dispatch, interceptors, and generated stubs.

Commonly needed test dependencies:

- grpc-inprocess matching the application's grpc-core/grpc-stub version.
- JUnit Jupiter.
- Mockito if verifying dependencies were not invoked.
- Spring Boot test if booting actual Spring gRPC configuration.

Fixture skeleton example:

~~~java
class AuthorizationGrpcTest {

    private Server server;
    private ManagedChannel channel;
    private OrderServiceGrpc.OrderServiceBlockingStub blockingStub;
    private final AtomicInteger invocations = new AtomicInteger();

    private void startServer(GrpcPrincipal principal) throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        ServerInterceptor authorization =
                new AuthorizationServerInterceptor(methodPolicy);

        ServerServiceDefinition securedDefinition;

        if (principal == null) {
            securedDefinition = ServerInterceptors.interceptForward(
                    new TestOrderService(invocations).bindService(),
                    authorization);
        } else {
            ServerInterceptor testAuthentication =
                    new PrincipalTestInterceptor(principal);

            securedDefinition = ServerInterceptors.interceptForward(
                    new TestOrderService(invocations).bindService(),
                    testAuthentication,
                    authorization);
        }

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(securedDefinition)
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        blockingStub = OrderServiceGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void stopServer() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }
}
~~~

**PrincipalTestInterceptor** is a test fixture used solely to simulate authentication results. It places the principal under the exact Context key:

~~~java
public final class PrincipalTestInterceptor implements ServerInterceptor {

    private final GrpcPrincipal principal;

    public PrincipalTestInterceptor(GrpcPrincipal principal) {
        this.principal = principal;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Context context = Context.current().withValue(
                GrpcSecurityContext.PRINCIPAL,
                principal);

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

This fixture lets you test authorization independently of JWT or mTLS. It does not replace real authentication tests; maintain separate tests for valid, bad-signature, expired, and wrong-audience tokens/certificates.

API names and dependencies must match the grpc-java version used by the module. If the Spring gRPC starter already manages the server, do not start an extra production server in tests; use the extension point or Spring test context to verify the exact configuration the application runs.

## 6. Testing Allow: Principal Has Sufficient Permissions

An allow test must verify the RPC succeeds and the handler is actually called:

~~~java
@Test
void allowsCallWhenPrincipalHasPermission() throws Exception {
    GrpcPrincipal principal = new GrpcPrincipal(
            "user-1",
            "tenant-a",
            Set.of("orders:read"));

    startServer(principal);

    GetOrderResponse response = blockingStub.getOrder(
            GetOrderRequest.newBuilder()
                    .setOrderId("order-1")
                    .build());

    assertEquals("order-1", response.getOrderId());
    assertEquals(1, invocations.get());
}
~~~

This test proves the principal is placed in Context before authorization runs and the policy sees the expected permissions. If the test returns UNAUTHENTICATED, check the Context key and interceptor ordering before editing the policy.

An allow test should also verify resource scope. A principal with orders:read belonging only to tenant A must not read tenant B's orders. Method permission suffices to call GetOrder, yet resource authorization can still deny it.

## 7. Testing Deny: Principal Exists but Lacks Permission

Deny requires a valid principal whose permission set does not satisfy the method:

~~~java
@Test
void deniesCallWhenPrincipalLacksPermission() throws Exception {
    GrpcPrincipal principal = new GrpcPrincipal(
            "user-1",
            "tenant-a",
            Set.of("orders:read"));

    startServer(principal);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> blockingStub.cancelOrder(
                    CancelOrderRequest.newBuilder()
                            .setOrderId("order-1")
                            .build()));

    assertEquals(
            Status.Code.PERMISSION_DENIED,
            error.getStatus().getCode());

    assertEquals(0, invocations.get());
}
~~~

Crucially, the test must send the RPC that actually requires orders:cancel. Do not merely call the policy directly with a method string and conclude the interceptor protects the endpoint.

For mutations, also check:

- Repository save/update is not called.
- Database state remains unchanged.
- Outbox or event publisher receives no events.
- Payment/inventory clients are not called.
- Audit records the deny decision without logging tokens or sensitive payloads.

## 8. Testing Missing Context: No Principal

Missing context must be tested separately. Start a server with only the authorization interceptor and without registering the test authentication interceptor:

~~~java
@Test
void rejectsCallWhenPrincipalIsMissing() throws Exception {
    startServer(null);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> blockingStub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-1")
                            .build()));

    assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());

    assertEquals(0, invocations.get());
}
~~~

This test verifies authorization does not fabricate a principal, does not fall back to a default user, and does not treat an empty Context as allow.

In production, missing context can occur if the authentication interceptor is unregistered, interceptors run out of order, two different Context keys are used, or Context is not propagated across callbacks. Therefore, when this test fails, inspect the pipeline and shared key before adding fallbacks.

Do not use PERMISSION_DENIED when the caller has not been verified. UNAUTHENTICATED accurately reflects that the server lacks a trusted principal.

## 9. Verifying Interceptor Ordering and Shared Context Key

Authentication must run before authorization. Integration tests must register interceptors in production order and prove authorization reads the principal placed by authentication.

~~~java
ServerServiceDefinition secured =
        ServerInterceptors.interceptForward(
                service.bindService(),
                authenticationInterceptor,
                authorizationInterceptor);
~~~

Bugs to catch:

- Authorization is registered before authentication, so Context has no principal yet.
- Authentication and authorization create two separate Context keys despite identical names.
- Authentication places the principal in Context, yet listener callbacks are not wrapped properly.
- Another interceptor overwrites the principal or sets an untrusted principal.
- Spring configuration registers an interceptor twice or applies it to only one service.

You can add a small test confirming the shared Context key:

~~~java
assertSame(
        GrpcSecurityContext.PRINCIPAL,
        SecurityContextKeys.PRINCIPAL);
~~~

Only one class should own the key. Avoid creating identically named keys across modules and trying to test that they are equivalent; they are distinct keys.

## 10. Testing Unmapped Methods and Spoofed Metadata

Deny-by-default must be verified using a method valid on the server that has no mapping in policy. The result must be PERMISSION_DENIED and the handler must not run.

Additionally, send spoofed metadata such as **x-method-name** with an allowed method name while the client calls an administrative method. Authorization must read the method name from the server-side descriptor:

~~~java
String actualMethod =
        call.getMethodDescriptor().getFullMethodName();
~~~

Tests must prove:

1. Metadata claims GetOrder while the actual RPC is DisableAccount.
2. Policy still evaluates DisableAccount.
3. A caller lacking administrative permission receives PERMISSION_DENIED.
4. The administrative handler does not run.
5. Audit logs the actual method from the descriptor; if storing the claimed method, mark it untrusted.

Never use client-sent metadata or request fields as the source for identifying the executing RPC.

## 11. Testing Tenant and Resource Authorization

Method allow does not equal resource allow. Add tests where the principal holds general permissions yet the resource belongs to another tenant:

| Principal | Method permission | Resource | Result |
| --- | --- | --- | --- |
| Tenant A | orders:read | Order belonging to A | Allow |
| Tenant A | orders:read | Order belonging to B | Deny or NOT_FOUND per contract |
| Tenant A | orders:cancel | Order A in cancelable state | Allow |
| Tenant A | orders:cancel | Order A already shipped | FAILED_PRECONDITION |
| No principal | Not evaluated | Any resource | UNAUTHENTICATED |

Verify repository queries include a tenant predicate, such as **findByTenantIdAndId**, rather than fetching by global ID and comparing tenants in Java afterward. On deny, verify zero mutations or downstream calls.

If the API uses NOT_FOUND to conceal out-of-tenant resources, tests must verify responses are indistinguishable from a resource not existing in the current tenant and do not leak the resource via error details or client logs.

## 12. Testing Context Isolation Across Concurrent RPCs

A serious bug is storing the principal in a mutable field or an uncleaned ThreadLocal. When two RPCs run concurrently, request A can receive request B's principal.

Concurrency tests should:

1. Create two principals with different subjects and tenants.
2. Send two RPCs concurrently through the same server/service instance.
3. Use latches or barriers to overlap processing windows.
4. Record the principal read by each handler.
5. Assert each response and repository query uses the right tenant.
6. Repeat enough times to increase the chance of catching race conditions.

Example expectation:

| RPC | Expected principal | Expected tenant |
| --- | --- | --- |
| Call A | user-a | tenant-a |
| Call B | user-b | tenant-b |

Do not use Thread.sleep to try to trigger races randomly. Use CountDownLatch, CyclicBarrier, or synchronization points inside the test service to control ordering. Run tests with a real executor or multi-threaded executor; a direct executor is useful for simple tests but does not expose all concurrency issues.

After each test, close the channel/server and shut down executors. Do not leave running tasks retaining principals or interfering with subsequent tests.

## 13. Testing Streaming Authorization and Lifecycle

For streaming RPCs, test both stream-open permissions and per-message/resource permissions:

- Missing principal at stream open must return UNAUTHENTICATED and create no subscription.
- Principal lacking method permission must return PERMISSION_DENIED before the handler initializes the stream.
- Client-streaming sending messages for an allowed tenant processes them per contract.
- Subsequent messages referencing another tenant/resource must be rejected before side effects.
- Server-streaming subscribes only to a tenant-scoped data source.
- Bidirectional streams check each command before execution.
- Client cancellation or deadline expiration cleans up subscriptions, queues, and workers.
- Two concurrent streams do not share principal or tenant state.

If the contract supports partial success, test item-level responses for rejected messages and verify the stream only continues in a valid state. If the contract requires terminating the stream, assert the terminal status and confirm no messages/side effects follow afterward.

For cancellation, verify the cleanup callback is invoked once or cleanup is idempotent. Do not merely assert the client canceled; verify server subscriptions and resources were released.

## 14. Testing Error Mapping and Stable Statuses

Statuses to distinguish:

| Condition | Status |
| --- | --- |
| Missing principal or unverified credential | UNAUTHENTICATED |
| Valid principal but missing permission | PERMISSION_DENIED |
| Out-of-scope resource concealed per contract | NOT_FOUND |
| Resource in state preventing the action | FAILED_PRECONDITION |
| Policy dependency cannot evaluate | UNAVAILABLE or DEADLINE_EXCEEDED |

Test based on **Status.Code** and stable reason codes, without parsing free-form status descriptions. Descriptions may change wording or language; they should not serve as the client API contract.

For policy dependency failures, tests must prove fail-closed behavior: without a permission decision, business handlers and downstream services must never be invoked. For UNAVAILABLE, retries may only happen under bounded policies and safe operations.

## 15. Organizing Tests in a Spring gRPC Application

Tests can be organized into three tiers:

**Unit tests** verify policy mappings, principal helpers, and exception/status mappers. These tests do not need to boot Spring or start a server.

**In-process integration tests** verify grpc-java dispatch, generated stubs, interceptor chains, Context, and statuses. This tier is ideal for running many allow/deny/missing-context cases quickly.

**Spring application integration tests** boot the application context and configure the gRPC server per the starter in use. Tests verify interceptor beans/extension points are actually registered, ordering is right, and protected services pass through the chain.

A common mistake is tests manually assembling the right interceptor chain while production Spring configuration forgets to register the interceptor. Standalone in-process tests still pass; only tests booting Spring configuration catch that wiring bug.

Keep test fixtures small, reusing principal builders and server lifecycle helpers. Each test should create its own data, reset counters/mocks, and close channels/servers to avoid execution-order dependencies.

## 16. Minimum Test Matrix

| Group | Required cases | Primary assertion |
| --- | --- | --- |
| Allow | Principal with sufficient permissions | OK status; handler runs |
| Deny | Principal lacking permission | PERMISSION_DENIED; handler does not run |
| Missing context | No principal | UNAUTHENTICATED; handler does not run |
| Policy | Unmapped method | Deny-by-default |
| Pipeline | Authentication before authorization | Principal readable via shared key |
| Spoofed input | Metadata claiming another method | Policy uses server descriptor |
| Tenant | Resource belonging to another tenant | No data returned / no mutation |
| Concurrency | Two concurrent principals | No subject/tenant mixing |
| Streaming | Out-of-scope message | No side effects; proper status/item result |
| Lifecycle | Cancel/deadline | Cleanup executed |
| Spring wiring | Boot application context | Interceptors actually registered |
| Error mapping | Policy dependency unavailable | Fail-closed; infrastructure status |

This serves as the baseline for security regression tests. When adding a new RPC, decide the policy for that method and add corresponding allow/deny tests. Never leave a new method covered only by happy-path tests.

## 17. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Create a policy requiring orders:read for GetOrder and orders:cancel for CancelOrder.
2. Write unit tests for allow, deny, and an unmapped method.
3. Stand up an in-process gRPC server with a test authentication interceptor and an authorization interceptor.
4. Write three separate integration tests: principal with sufficient permissions, principal lacking permissions, and missing context.
5. Use AtomicInteger or mocks to prove the handler does not run on deny/missing context.
6. Send spoofed x-method-name metadata and verify policy still uses the server-side MethodDescriptor.
7. Add tests for tenant/resource checks, concurrency, and streaming message authorization.
8. Boot the Spring application context in an integration test to verify production interceptor wiring.

### Self-Check Questions

**1. How do allow, deny, and missing context differ?**  
Allow has a principal with sufficient permissions; deny has a principal rejected by policy; missing context has no verified principal to evaluate permissions.

**2. Which statuses fit deny and missing context?**  
Deny is typically PERMISSION_DENIED; missing principal is UNAUTHENTICATED.

**3. Why is asserting status insufficient?**  
The handler might have already executed and caused side effects before the status was sent. Assert the handler was not called and data is unchanged.

**4. Do policy unit tests replace interceptor integration tests?**  
No. Unit tests check mappings; integration tests prove Context, interceptor ordering, dispatch, and actual statuses.

**5. Why test unmapped methods?**  
To prove deny-by-default and prevent new RPCs from accidentally becoming open.

**6. How do you test Context isolation?**  
Run two concurrent RPCs with different principals, control overlap with a latch/barrier, and verify each call sees only its own principal.

**7. Is per-message authorization testing needed for streaming?**  
Yes, when messages can reference different resources/actions. Tests must prove denied messages cause no side effects.

**8. Why are Spring application integration tests needed if in-process tests already pass?**  
Because in-process tests assemble the chain manually; they do not prove beans/extension points in production Spring configuration registered the interceptors properly.

## Summary

Authorization testing must distinguish **allow**, **deny**, and **missing context**. Principals with sufficient permissions proceed to the handler; verified principals lacking permissions receive **PERMISSION_DENIED**; missing principals receive **UNAUTHENTICATED**. Tests must verify statuses and prove handlers/business side effects do not execute when denied. Combine policy unit tests, in-process gRPC integration tests, and Spring application integration tests to verify both mappings and real wiring. Adding tests for unmapped methods, spoofed metadata, tenant/resource checks, concurrent requests, streaming, and cancellation prevents authorization regressions.
