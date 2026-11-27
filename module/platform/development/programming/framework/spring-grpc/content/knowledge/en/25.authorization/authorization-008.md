# Context Carrying Principal and Permissions

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of **io.grpc.Context** in binding a principal and permissions to a specific RPC.
- Distinguish grpc-java's internal Context from metadata transmitted over the network.
- Create an immutable principal from verified credentials and store it using a shared Context key.
- Read the principal in authorization interceptors, adapters, and application services.
- Safely propagate Context across callbacks, executors, and asynchronous tasks.
- Understand how deadlines, cancellation, and child Contexts inherit RPC state.
- Avoid context leaks, principal mix-ups across requests, and storing unnecessary sensitive data.
- Test context propagation and authorization in Spring gRPC applications.

## 1. Context Binds Data to the Lifecycle of an RPC

In **SPRING_GRPC**, a single request often needs the verified caller identity, tenant, and permission set across multiple layers: interceptors, gRPC adapters, and application services. Passing all of this information through every method parameter bloats signatures; using global variables or custom ThreadLocals risks mixing data across requests.

**io.grpc.Context** is grpc-java's mechanism for attaching execution-scoped data to a call. A Context can carry the principal, correlation data, or security information needed while processing an RPC. The current Context is attached by the runtime to the executing thread during callbacks; code can read values via a Context key.

Typical flow:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant A as Authentication interceptor
    participant X as Authorization interceptor
    participant H as Service handler
    participant U as Application use case
    C->>A: RPC + credential metadata
    A->>A: Verify credential
    A->>A: Create immutable principal
    A->>X: Context carrying principal
    X->>X: Read principal and check permission
    X->>H: Allow handler invocation
    H->>U: Process command
    U->>U: Read principal or receive explicit actor
    U-->>C: Response / gRPC status
~~~

Context is suited for data tied to **a single RPC execution**. It is not a place for long-lived sessions, not a shared store across instances, and does not automatically transmit data to another service over the network.

## 2. How Does Context Differ from Metadata?

Metadata is gRPC data sent over the network in request headers or response trailers. Context is an in-process mechanism for passing data across layers/callbacks.

| Characteristic | gRPC Metadata | io.grpc.Context |
| --- | --- | --- |
| Scope | Across client/server boundary | In-process and execution scope |
| Source | Client, server, or interceptor | Server/runtime or internal code |
| Example | Authorization header, trace header | Verified principal, permission set |
| Trust | Input that must be verified | Internal value set by trusted code |
| Forwarded to another service | Can be sent via metadata after filtering | Not automatically sent over network |
| Lifecycle | Tied to request/response metadata | Tied to execution/call context |

Clients may send authorization metadata containing a bearer token. The authentication interceptor reads the token and verifies signature, issuer, audience, expiry, and claims per contract. After verification, the interceptor creates a principal and places it into Context.

Never place arbitrary metadata directly into Context and treat every field as trusted. Values in Context are trustworthy only when the component creating them has authenticated and normalized the data. A custom header x-role: admin remains untrusted input until proven by credentials or a trusted policy source.

## 3. Principal Should Be Immutable and Contain Only Needed Data

The principal represents the verified identity and security attributes needed for decisions. Example:

~~~java
package dev.example.security;

import java.util.Set;

public record GrpcPrincipal(
        String subject,
        String tenantId,
        Set<String> permissions) {

    public GrpcPrincipal {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

Set.copyOf creates a permission set that cannot be modified through external references. Immutability lets callbacks safely read the same principal without worrying that another layer silently mutates permissions while the RPC is running.

Only put necessary data into the principal:

- Verified subject or service identity.
- Verified tenant or tenant scope.
- Permissions/authorities normalized according to policy.
- Specific claims required for authorization decisions.

Do not put raw access tokens, refresh tokens, private keys, full JWT payloads, large database entities, or mutable objects into Context. If a token is needed to call downstream services, keep credentials inside a credential management component and pass only minimal data across controlled boundaries.

A principal should also never be a mutable singleton Spring bean. Each RPC has its own principal, bound to that call's Context.

## 4. Using a Shared Context.Key

To read the exact same value across layers, declare the Context key once:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Context.Key is identity-based; the string name mainly assists debugging. Calling Context.key("authenticated-principal") in two separate classes creates two distinct keys, even with the same name. Therefore, authentication and authorization must import the exact same GrpcSecurityContext.PRINCIPAL.

Avoid declaring keys inside interceptCall or creating a new key per request. The key should be static final and shared across the pipeline.

## 5. Authentication Interceptor Places the Principal into Context

The authentication interceptor is responsible for verifying credentials. After constructing a trusted principal, it creates a child Context using withValue and invokes Contexts.interceptCall so the rest of the pipeline runs inside that Context.

Example credential verification abstraction:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import java.util.Optional;

public interface CredentialAuthenticator {
    Optional<GrpcPrincipal> authenticate(Metadata headers);
}
~~~

Interceptor:

~~~java
package dev.example.security;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class AuthenticationServerInterceptor
        implements ServerInterceptor {

    private final CredentialAuthenticator authenticator;

    public AuthenticationServerInterceptor(
            CredentialAuthenticator authenticator) {
        this.authenticator = authenticator;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        var authenticated = authenticator.authenticate(headers);

        if (authenticated.isEmpty()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context = Context.current().withValue(
                GrpcSecurityContext.PRINCIPAL,
                authenticated.get());

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Contexts.interceptCall invokes the next step under the supplied Context and wraps the listener so callbacks receiving messages/cancellation/close also run within that Context. Consequently, authorization interceptors and handlers can read the principal via Context.current() or the Context key.

If credentials are invalid, the interceptor closes the call with UNAUTHENTICATED, returns an empty listener, and does not forward to the service. Never create a default principal or grant broad permissions just to let the request proceed.

## 6. Authorization Reads the Principal from Context

The authorization interceptor reads the principal using the same key, then checks permissions for the actual method:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class AuthorizationServerInterceptor
        implements ServerInterceptor {

    private final GrpcMethodPolicy policy;

    public AuthorizationServerInterceptor(GrpcMethodPolicy policy) {
        this.policy = policy;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        GrpcPrincipal principal =
                GrpcSecurityContext.PRINCIPAL.get();

        if (principal == null) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        String method =
                call.getMethodDescriptor().getFullMethodName();

        if (!policy.allows(principal, method)) {
            call.close(
                    Status.PERMISSION_DENIED
                            .withDescription("Permission denied"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

Authentication must run before authorization. You can use ServerInterceptors.interceptForward to express the desired order:

~~~java
ServerServiceDefinition securedService =
        ServerInterceptors.interceptForward(
                orderService,
                authenticationInterceptor,
                authorizationInterceptor);

serverBuilder.addService(securedService);
~~~

In the Spring gRPC starter, register interceptors via the extension point/bean registration of the starter version in use. Do not manually create a second server if the starter already manages the server. Write integration tests to verify that authorization actually sees the principal placed into Context by authentication.

## 7. Reading the Principal in Adapters and Application Services

Inside RPC handling callbacks, code can retrieve the current principal:

~~~java
GrpcPrincipal principal =
        GrpcSecurityContext.PRINCIPAL.get();

if (principal == null) {
    throw Status.UNAUTHENTICATED
            .withDescription("Authentication required")
            .asRuntimeException();
}
~~~

The adapter can convert the principal into an explicit actor/command when calling the application service:

~~~java
public GetOrderResponse getOrder(GetOrderRequest request) {
    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    OrderView result = getOrderUseCase.execute(
            principal,
            request.getOrderId());

    return OrderMapper.toProto(result);
}
~~~

Passing the principal explicitly into the use case makes security dependencies visible and easy to unit test. Context helps adapters/interceptors obtain RPC-scoped data; it does not force every domain layer to depend directly on grpc-java.

For transport-independent domain code, translate the principal into an application Actor or CurrentUser type. Avoid calling GrpcSecurityContext.PRINCIPAL.get() everywhere in the domain, as that couples business logic to an implicit execution context.

## 8. Context Is Immutable; withValue Creates a Child Context

Operations on Context do not mutate the current object. withValue returns a child Context containing the added key/value or overriding that key's value:

~~~java
Context parent = Context.current();

Context child = parent.withValue(
        GrpcSecurityContext.PRINCIPAL,
        principal);
~~~

A child Context inherits other values from its parent, including deadline/cancellation state via the Context mechanism. Therefore, do not use Context.ROOT arbitrarily when attaching a principal; doing so detaches work from the current Context and loses information such as deadlines or cancellation.

A Context key can be shadowed in a child Context. This is useful when creating a different execution scope, but you should not swap principals mid-RPC without clear security justification and boundaries. Never use Context as a mutable map shared across requests.

## 9. Propagating Context Across Executors and Async Tasks

Context is attached by grpc-java to callbacks managed by the runtime. When the application offloads work to a custom thread pool or executor, do not assume Context automatically propagates to the new thread.

You can capture the current Context and wrap the task:

~~~java
Context captured = Context.current();

executor.execute(captured.wrap(() -> {
    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    processForTenant(principal.tenantId());
}));
~~~

Or create an executor capable of attaching Context at submission time:

~~~java
Executor contextAwareExecutor =
        Context.currentContextExecutor(executor);

CompletableFuture.supplyAsync(
        () -> useCase.execute(command),
        contextAwareExecutor);
~~~

Capture Context right when creating the task. Never hold onto one RPC's Context and reuse it for another request. If work is enqueued to run after the RPC finishes, consider passing explicit actor/tenant/operation data in the job envelope rather than keeping the entire Context alive long-term.

If tasks run in a scheduler, batch worker, or message consumer with no active RPC, Context.current() may be the default Context with no principal. The worker needs its own identity and verified actor/tenant data per the job's contract.

## 10. Deadlines and Cancellation Travel with Context

Context can carry deadlines and cancellation state. A child Context created with withValue continues to inherit these properties.

Practical implications:

- If the caller cancels the RPC, tasks running with properly propagated Context can observe cancellation and stop early.
- If the deadline expires, downstream work should stop or avoid starting when no budget remains.
- When wrapping an executor, capture the right Context so tasks do not accidentally run as detached work with no deadline.
- If work must continue after the RPC ends, design it as an independent job with its own lifecycle, timeouts, and identity.

Do not hold a request Context longer than necessary. A hung task can retain references to the principal and request-bound data. Clean up listeners, subscriptions, and futures when cancellation occurs.

## 11. Context Does Not Automatically Propagate to Other Services

io.grpc.Context is strictly an execution context within the current process. When a Spring gRPC service calls another gRPC service, Context does not automatically turn into metadata on the outbound request.

If downstream services need to authenticate the caller or workload, the client must send credentials/identity via an explicitly designed mechanism:

- Use service identity or mTLS to verify the workload calling downstream.
- If delegated user identity is required, use appropriate token exchange/delegation; never send a serialized principal object as an arbitrary header.
- Propagate only standardized trace context/correlation metadata.
- Never blindly forward all inbound metadata.
- Downstream independently verifies credentials and builds its own Context principal.

For example, service A may know user U is verified. When calling service B, A cannot simply serialize GrpcPrincipal into x-principal and expect B to trust it. B must authenticate service A and/or a delegated token according to the trust model.

## 12. Avoiding Context Leaks and Security Bugs

Common mistakes:

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating separate Context keys in each interceptor | Authorization cannot read principal | Use one shared static final key |
| Storing principal in a mutable singleton | Concurrent requests overwrite each other's identity | Immutable principal, bound to each call's Context |
| Trusting unverified roles/tenants from metadata | Caller escalates privileges or switches tenants | Verify credentials/membership before creating principal |
| Executor task fails to capture Context | Loses principal, deadline, or cancellation | Use Context.wrap/context-aware executor |
| Retaining RPC Context in long-lived jobs | Incorrect reference retention and lifecycle | Pass actor/tenant explicitly to jobs |
| Using Context.ROOT unnecessarily | Loses parent deadline/cancellation and other values | Create child Context from Context.current() |
| Sending principal object to another service | Violates process trust boundaries | Send verified credentials/delegation |
| Missing null check for principal | Null dereference or fallback to allow | Return UNAUTHENTICATED, never default permissions |
| Logging sensitive tokens/principal fields | Leaks credentials and personal data | Redact and log only minimal identifiers |

Never call attach() and forget detach() in manual code. If you must attach a Context outside Contexts.interceptCall/Context.wrap, always restore the previous Context in a finally block. Prefer built-in wrapper APIs to reduce the risk of Context leaking between tasks sharing threads.

## 13. Testing Context and Principal Propagation

Tests should verify that per-RPC data never mixes and asynchronous callbacks observe the correct Context.

| Case | Expected result |
| --- | --- |
| Valid credential | Principal appears in authorization interceptor |
| Invalid credential | UNAUTHENTICATED; handler does not run |
| Principal lacks permission | PERMISSION_DENIED; handler does not run |
| Two concurrent RPCs with different principals | Each handler reads its own call's subject/tenant |
| Executor wrapped with Context | Task reads the captured principal |
| Executor without Context | No principal; does not fall back to previous request |
| RPC canceled | Task with Context observes cancellation and cleans up |
| Deadline expires | Downstream does not continue indefinitely |
| Child Context using withValue | Inherits parent state and overrides the target key |
| Outbound call to another service | Identity propagated via verified credentials/delegation, not Context objects |

You can use an in-process gRPC test registering production-like authentication/authorization interceptors, invoke through the generated stub, and assert the principal inside the handler. Use a latch/barrier to run two concurrent RPCs with two different principals; this test helps detect improper use of ThreadLocals or mutable fields.

For executors, submit a task while Context holds principal A, wrap Context, and execute; verify the task sees A. Then run a task without Context and verify it does not see principal A. Add cancellation/deadline tests to ensure background work stops or terminates per policy.

## 14. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Create an immutable GrpcPrincipal containing subject, tenant, and permissions.
2. Create GrpcSecurityContext.PRINCIPAL as a shared Context key.
3. Write an authentication interceptor that validates mock credentials and attaches the principal via Context.current().withValue.
4. Use Contexts.interceptCall to pass Context to downstream interceptors/handlers.
5. Write an authorization interceptor reading the same key and returning UNAUTHENTICATED or PERMISSION_DENIED appropriately.
6. Read the principal in the gRPC adapter and pass an explicit actor into the application use case.
7. Run an executor task using Context.current().wrap(...) and verify principal/deadline are preserved.
8. Write integration tests for two concurrent RPCs, cancellation, missing context, and outbound identity propagation.

### Self-Check Questions

**1. What is io.grpc.Context used for?**  
Attaching execution-scoped data to an RPC so interceptors, listeners, and callbacks within the same process can read the right information.

**2. Is Context sent over the network like metadata?**  
No. Context is process-local; to have downstream services verify identity, pass credentials/delegation through metadata per the trust model.

**3. Why must a single Context.Key instance be shared?**  
Because keys are compared by object identity. Two separately created keys, even with identical names, do not read the same value.

**4. What data should a principal contain?**  
Only verified minimal subject, tenant, permissions, and security attributes; never raw tokens or large mutable objects.

**5. Why not use a custom ThreadLocal?**  
Thread pools reuse threads and tasks can hop threads; without exact attach/cleanup management, a prior caller's data can leak into subsequent requests.

**6. Does Context automatically propagate across executors?**  
Never assume so. Capture the current Context and use Context.wrap or a context-aware executor.

**7. Why should a child Context be created from Context.current()?**  
To inherit deadlines, cancellation, and parent values needed for the RPC lifecycle.

**8. When should Context not be retained?**  
When work outlives the RPC or runs in an independent queue/scheduler; pass explicit actor/tenant/operation data and use a separate worker identity.

## Summary

**io.grpc.Context** is the internal execution scope binding a verified principal and permissions to an RPC. The authentication interceptor builds an immutable principal and stores it under a shared Context key; the authorization interceptor, listeners, and handlers read the same value for the right call. Child Contexts inherit deadlines/cancellation, while application-offloaded executor tasks must explicitly capture and wrap Context. Context does not cross the network, does not replace credentials on downstream calls, and should not outlive the RPC. Using minimal principals, a shared key, controlled Context propagation, and concurrent RPC tests prevents identity mix-ups or permission leaks between requests.
