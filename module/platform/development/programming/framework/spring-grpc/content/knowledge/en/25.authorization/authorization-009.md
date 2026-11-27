# Context Carrying Principal and Permissions

## Learning Objectives

After this lesson, you will be able to:

- Explain why gRPC needs an execution context to carry the verified principal and permissions across callbacks of the same RPC.
- Distinguish **io.grpc.Context** from gRPC Metadata and from long-lived sessions.
- Create an immutable, minimal principal and place it into Context using a shared **Context.Key**.
- Combine the authentication interceptor, authorization interceptor, and service handler in the proper order.
- Propagate Context across executors, CompletableFutures, and asynchronous callbacks without mixing up identities.
- Understand the relationship between Context, deadlines, and cancellation.
- Recognize process boundaries: Context does not automatically propagate to other gRPC services.
- Test context propagation, concurrent requests, and missing-principal cases to catch context leaks.

## 1. Why Do We Need a Context Carrying the Principal?

In **SPRING_GRPC**, an RPC typically passes through multiple layers: authentication interceptor, authorization interceptor, gRPC adapter, and application service. These layers may need the same verified information such as subject, tenant, and permissions. If every layer independently parses tokens or interprets metadata, security logic easily becomes duplicated and inconsistent.

**io.grpc.Context** is grpc-java's mechanism for binding data to an execution scope. The server can attach a principal after verifying credentials; subsequent interceptors and callbacks for that same RPC read that principal without requiring the client to resend identity in every message.

Context solves passing data within one process and within a call's processing lifecycle. It does not validate tokens, does not decide permissions on its own, does not store long-lived sessions, and does not replace a database or identity provider.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant A as Authentication interceptor
    participant Z as Authorization interceptor
    participant H as Service handler
    participant U as Application use case
    C->>A: RPC + credential metadata
    A->>A: Verify credential
    A->>A: Create immutable principal
    A->>Z: Context carrying principal
    Z->>Z: Read principal and check permission
    Z->>H: Allow handler to run
    H->>U: Command + actor
    U-->>C: Response or gRPC status
~~~

An RPC has one active execution context at any point in its processing. When the runtime invokes callbacks inside that context, code can retrieve the principal bound to the call. When another request runs concurrently, that request has its own Context; one request's principal is never shared with another.

## 2. How Does Context Differ from Metadata and Sessions?

Metadata is gRPC data transmitted over the network in request headers or response trailers. Context is an in-process mechanism for passing data across the execution flow. Sessions or server-side stores have lifecycles longer than a single RPC.

| Characteristic | gRPC Metadata | io.grpc.Context | Session/store |
| --- | --- | --- | --- |
| Scope | Over the network | In-process | May span many requests |
| Lifecycle | Request/response metadata | Execution/call scope | Per TTL or logout flow |
| Source | Client, server, interceptor | Runtime or internal code | Database/cache/session service |
| Example | Bearer token, trace header | Verified principal, deadline | Refresh session, user preferences |
| Trust | Input must be verified | Trusted based on component that set value | Per store access control |
| Auto-forwarded to other services | Can be selectively forwarded | No | Not automatic |

Clients can send bearer tokens in Metadata. The authentication interceptor reads the token and verifies signature, issuer, audience, expiry, and claims per contract. Then the interceptor constructs a normalized principal and places it into Context.

Never copy all Metadata into Context and treat every field as trusted. Client-sent headers like x-role or x-tenant-id remain untrusted input until verified by appropriate credentials or policy sources.

## 3. Principal Should Be Immutable and Contain Only Needed Data

The principal represents the verified identity and security attributes. Example:

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

A record together with Set.copyOf prevents the principal from being modified through external references. This matters because multiple callbacks may read the principal while the RPC runs. Context itself is immutable, but values stored inside Context do not automatically become immutable. If you place a mutable object in Context, other code can still mutate that object.

Keep only the information needed for decisions:

- Verified subject or service identity.
- Verified tenant or allowed tenant set.
- Normalized permissions/authorities.
- Minimal claims required for authorization.

Do not place raw access tokens, refresh tokens, private keys, full JWT payloads, large database entities, or unnecessary personal data into Context. Context is not a secret vault; its values can be observed by code running in the same process.

A principal must also never be a mutable singleton Spring bean. Each RPC must have the principal corresponding to that call's own caller.

## 4. Using a Shared Context.Key

To read the same principal across multiple layers, declare the key once:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Context.Key is an identity-based object. The string name such as authenticated-principal helps with debugging, but it is not a mechanism that makes two independent keys automatically equivalent. If the authentication interceptor calls Context.key once and the authorization interceptor calls Context.key again, they hold two different keys despite having the same name.

Therefore:

- Declare the key as static final in a shared class.
- Authentication and authorization import that exact key.
- Never create keys inside interceptCall or per request.
- Never create another key with the same name in another module expecting it to read the same value.

When reading the principal, null means the current Context has no principal yet. Treat it as unauthenticated and deny; never synthesize a default principal or fall back to a previous caller.

## 5. Authentication Interceptor Places the Principal into Context

The authentication interceptor is responsible for verifying credentials and creating the principal. Verification can be extracted behind an abstraction so JWT, mTLS, or identity providers can be swapped without changing how Context is used:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import java.util.Optional;

public interface CredentialAuthenticator {
    Optional<GrpcPrincipal> authenticate(Metadata headers);
}
~~~

The interceptor attaches the principal after successful verification:

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

withValue creates a child Context containing the principal. Contexts.interceptCall executes the next step of the pipeline in that Context and wraps the listener so RPC callbacks continue running under the corresponding Context. Thus, the authorization interceptor and service handler can read the same principal.

If credentials are invalid, the interceptor closes the call with UNAUTHENTICATED and does not call next. Never attach an empty principal or broad permissions to let the request proceed.

## 6. Authorization Interceptor Reads the Same Principal

The authorization interceptor uses the exact key set by authentication:

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

        String fullMethodName =
                call.getMethodDescriptor().getFullMethodName();

        if (!policy.allows(principal, fullMethodName)) {
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

Authentication must run before authorization. With grpc-java, this ordering can be expressed when wrapping the service:

~~~java
ServerServiceDefinition securedService =
        ServerInterceptors.interceptForward(
                orderService,
                authenticationInterceptor,
                authorizationInterceptor);

serverBuilder.addService(securedService);
~~~

In the Spring gRPC starter, register interceptors through the extension point/bean registration supported by the starter version in use. Do not create a second server if the starter already manages the server. Write integration tests to verify that authorization sees the principal placed into Context by authentication.

If principal is null, return UNAUTHENTICATED. If principal exists but lacks permission, return PERMISSION_DENIED. Do not call next.startCall after denying; the handler must not execute.

## 7. Reading the Principal in the gRPC Adapter and Passing to the Use Case

In the adapter, read the current principal and convert it into an explicit actor/command:

~~~java
public GetOrderResponse getOrder(GetOrderRequest request) {
    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    if (principal == null) {
        throw Status.UNAUTHENTICATED
                .withDescription("Authentication required")
                .asRuntimeException();
    }

    OrderView result = getOrderUseCase.execute(
            principal,
            request.getOrderId());

    return OrderMapper.toProto(result);
}
~~~

Passing the principal or an application Actor type into the use case makes security dependencies explicit in method signatures and easy to unit test. Context helps interceptors/adapters retrieve RPC-bound data; it does not force every domain layer to depend on grpc-java.

For a transport-independent domain model, translate the principal into an application Actor/CurrentUser type. Avoid having the domain call GrpcSecurityContext.PRINCIPAL.get() everywhere, as that creates hidden dependencies on the execution context.

Method-level authorization in the interceptor is still insufficient for all operations. The use case must check tenant, ownership, and specific resource permissions before business actions. Context only carries data for making decisions; it does not enforce authorization itself.

## 8. Immutable Context and Child Contexts

Context is not mutated in place. withValue returns a child Context with the new key/value:

~~~java
Context parent = Context.current();

Context child = parent.withValue(
        GrpcSecurityContext.PRINCIPAL,
        principal);
~~~

A child Context inherits other values from its parent. This matters because the current Context may hold deadlines, cancellation, and other RPC data. When attaching a principal, usually create a child Context from Context.current() rather than arbitrarily using Context.ROOT.

A Context key can be shadowed in a child Context. This technique is useful when creating a separate execution scope, but you should not swap principals mid-RPC without clear security boundaries. Never use Context as a mutable map shared across requests.

A single Context can hold different values under multiple keys. Choose meaningful key names, limit the amount of data, and avoid placing objects with large lifecycles into Context since references may be retained for the duration of the task.

## 9. Propagating Context Across Executors and CompletableFuture

grpc-java manages Context for RPC callbacks. However, when the application manually hands work off to a thread pool or executor, do not assume Context automatically propagates to the new thread.

Capture the current Context and wrap the task:

~~~java
Context captured = Context.current();

executor.execute(captured.wrap(() -> {
    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    processForTenant(principal.tenantId());
}));
~~~

Or create an executor that attaches Context when creating the wrapper:

~~~java
Executor contextAwareExecutor =
        Context.currentContextExecutor(executor);

CompletableFuture.supplyAsync(
        () -> useCase.execute(command),
        contextAwareExecutor);
~~~

Capture Context inside the RPC callback, at the point where the principal is already present. Context.wrap or currentContextExecutor attaches the captured Context when the task runs and restores the previous Context after the callback finishes.

Never save one request's Context and reuse it for another request. If work is enqueued to run after the RPC has ended, pass the required actor, tenant, and operation in a protected job envelope rather than keeping the entire request Context alive long-term.

If tasks run in a scheduler, batch worker, or message consumer with no active RPC, Context.current() may contain no principal. Workers must have their own service identity and verify actor/tenant from the job contract; never use a previous request's Context as a fallback.

## 10. Deadlines and Cancellation Bound to Context

Context can carry deadlines and cancellation state. A child Context created from the current Context continues to inherit lifecycle state via grpc-java's mechanism.

That helps tasks tied to an RPC coordinate their lifecycle:

- When the caller cancels the RPC, tasks running with properly propagated Context can observe cancellation and stop early.
- When the deadline expires, downstream work should stop or avoid starting when no budget remains.
- When wrapping an executor, capture Context at the right time so tasks do not accidentally run as detached work with no deadline.
- When work must continue after the RPC ends, turn it into an independent job with its own timeout and identity.

You can inspect the current Context:

~~~java
Context current = Context.current();

if (current.isCancelled()) {
    return;
}

Deadline deadline = current.getDeadline();
if (deadline != null && deadline.isExpired()) {
    return;
}
~~~

Do not hold a request Context longer than needed. A hung task can retain references to the principal and request-bound data. When cancellation occurs, clean up listeners, subscriptions, buffers, and futures appropriately.

## 11. Context Does Not Automatically Propagate to Other Services

io.grpc.Context is strictly an execution context within the current process. When Spring gRPC service A calls service B, Context does not automatically turn into metadata on the outbound request.

If downstream needs to authenticate the caller or workload, the client must send credentials/identity via an explicitly designed mechanism:

- Use service identity or mTLS to authenticate the workload calling downstream.
- If delegated user identity is required, use appropriate token exchange or delegation.
- Propagate only standardized trace context/correlation metadata.
- Never blindly forward all inbound metadata.
- Downstream independently verifies credentials and creates its own Context principal.

For example, service A may know user U is verified. When calling service B, A cannot serialize GrpcPrincipal into x-principal and expect B to trust it. B needs to verify service A and/or a delegated token per the trust model. An internal Java object is not an inter-service credential.

## 12. Avoiding Context Leaks and Unnecessary Security Data

Common mistakes:

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating separate Context keys in each interceptor | Authorization cannot read principal | Use one shared static final key |
| Storing principal in a mutable singleton | Concurrent requests overwrite each other's identity | Immutable principal, bound to each call's Context |
| Trusting unverified roles/tenants from metadata | Caller escalates privileges or switches tenants | Verify credentials/membership before creating principal |
| Executor task fails to capture Context | Loses principal, deadline, or cancellation | Use Context.wrap or context-aware executor |
| Retaining RPC Context in long-lived jobs | Improper reference retention and lifecycle | Pass actor/tenant explicitly to jobs |
| Using Context.ROOT unnecessarily | Loses parent deadline/cancellation and other values | Create child Context from Context.current() |
| Sending principal object to another service | Violates process trust boundaries | Send verified credentials/delegation |
| Missing null check for principal | Null dereference or fallback to allow | Return UNAUTHENTICATED, never default permissions |
| Logging sensitive tokens/principal fields | Leaks credentials and personal data | Redact and log only minimal identifiers |

Never call attach() and forget detach() in manual code. If you must attach Context outside Contexts.interceptCall or Context.wrap, always restore the previous Context in a finally block. Prefer built-in wrapper APIs to reduce the risk of Context leaking across tasks sharing threads.

Context is merely a mechanism for passing data; it does not make the data inside safe on its own. Keep the principal immutable, free of raw tokens, restrict log access, and do not store sensitive data in keys readable by components that do not need it.

## 13. Testing Context and Principal Propagation

Tests must verify per-RPC data never mixes and asynchronous callbacks observe the right Context.

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
| Outbound call to another service | Identity passed via verified credentials/delegation, not Context objects |

Use an in-process gRPC test registering production-like authentication/authorization interceptors, call through the generated stub, and assert the principal in the handler. Use a latch/barrier to run two concurrent RPCs with two different principals; this test helps detect improper use of ThreadLocals or mutable fields.

For executors, create a task while Context has principal A, wrap Context, and execute; verify the task sees A. Then run a task without Context and verify it does not see principal A. Add cancellation/deadline tests to ensure background work stops or terminates per policy.

Another important test is intentionally declaring two Context keys with the same name but different instances in a test fixture to prove authorization cannot read the principal. Then use the shared key and verify the request succeeds properly. This test guards against refactoring errors that accidentally create duplicate-named keys.

## 14. Hands-On Exercise and Self-Check Questions

### Hands-On Exercise

1. Create an immutable GrpcPrincipal containing verified subject, tenant, and permissions.
2. Create GrpcSecurityContext.PRINCIPAL as a shared Context key.
3. Write an authentication interceptor validating mock credentials and attaching the principal via Context.current().withValue.
4. Use Contexts.interceptCall to pass Context to downstream interceptors/handlers.
5. Write an authorization interceptor reading the same key and returning UNAUTHENTICATED or PERMISSION_DENIED as appropriate.
6. Read the principal in the gRPC adapter and pass an explicit actor into the application use case.
7. Run an executor task using Context.current().wrap or Context.currentContextExecutor and verify principal/deadline are preserved.
8. Write integration tests for two concurrent RPCs, cancellation, missing context, and outbound identity propagation.

### Self-Check Questions

**1. What is io.grpc.Context used for?**  
Binding data to the RPC's execution scope so interceptors, listeners, and callbacks in the same process can read the right information.

**2. Is Context sent over the network like metadata?**  
No. Context is process-local; for downstream services to verify identity, pass credentials/delegation via metadata per the trust model.

**3. Why must a single Context.Key instance be shared?**  
Because keys use object identity. Two separately created keys with the same name do not read the same value.

**4. What data should a principal contain?**  
Only verified minimal subject, tenant, permissions, and security attributes; never raw tokens or large mutable objects.

**5. Why not use a custom ThreadLocal?**  
Thread pools reuse threads and tasks can switch threads; without exact attach/cleanup management, a prior caller's data can leak to later requests.

**6. Does Context automatically propagate across executors?**  
Never assume so. Capture the current Context and use Context.wrap or a context-aware executor.

**7. Why should child Contexts be created from Context.current()?**  
To inherit deadlines, cancellation, and parent values needed for the RPC lifecycle.

**8. When should Context not be retained?**  
When work outlives the RPC or runs in an independent queue/scheduler; pass explicit actor/tenant/operation data and use a separate identity for the worker.

## Summary

**io.grpc.Context** is the internal execution scope binding a verified principal and permissions to an RPC. The authentication interceptor builds an immutable principal and places it under a shared Context key; the authorization interceptor, listeners, and handlers read the same value in the right call. Child Contexts inherit deadlines/cancellation, while tasks offloaded by the application to executors must explicitly capture and wrap Context. Context does not cross the network, does not replace credentials when calling downstream, and should not outlive the RPC. Using minimal principals, a shared key, controlled Context propagation, and concurrent RPC tests avoids identity mix-ups or permission leaks between requests.
