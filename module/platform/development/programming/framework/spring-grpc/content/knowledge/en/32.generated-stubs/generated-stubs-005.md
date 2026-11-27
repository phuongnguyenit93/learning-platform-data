# withDeadline and withCallCredentials

Generated stubs in gRPC Java allow configuring time budgets and authentication information directly per call. Two commonly used APIs are **withDeadline / withDeadlineAfter** to bound RPC duration and **withCallCredentials** to attach credentials to the call's metadata. Both return a new stub because generated stubs are immutable.

In **Spring gRPC**, the common pattern is to manage the channel and base stub according to the application lifecycle, then create a derived stub close to invocation time to apply the business deadline. Credentials can be provided as a shared Spring bean if the implementation is thread-safe and fetches tokens dynamically per RPC. Deadlines and credentials solve two different problems: deadlines bound wait time; credentials prove the caller's identity or access rights.

## 1. Distinguishing the Two APIs

| API | Purpose | Result |
| --- | --- | --- |
| withDeadline(deadline) | Uses an existing absolute expiration point | New stub carrying the specified deadline |
| withDeadlineAfter(duration, unit) | Creates an expiration point from a relative duration at call time | New stub carrying a deadline computed immediately when configured |
| withCallCredentials(credentials) | Attaches a mechanism to produce auth metadata for the RPC | New stub carrying CallCredentials in CallOptions |

Example:

~~~java
var baseStub = PaymentServiceGrpc.newBlockingStub(channel);

var securedStub = baseStub.withCallCredentials(bearerCredentials);

var boundedStub = securedStub.withDeadlineAfter(
    700, TimeUnit.MILLISECONDS);

PaymentResponse response = boundedStub.getPayment(request);
~~~

securedStub and boundedStub are two new objects; baseStub is unchanged. Derived stubs retain previously configured options, so boundedStub has both credentials and a deadline.

## 2. withDeadline and withDeadlineAfter

### Absolute Deadlines

Deadlines are suitable when multiple operations belonging to the same logical request must share one completion cutoff. You can create a deadline once and pass it to child calls:

~~~java
Deadline overall = Deadline.after(
    1200, TimeUnit.MILLISECONDS);

PaymentResponse response = baseStub
    .withDeadline(overall)
    .getPayment(request);
~~~

Deadlines are based on a monotonic clock, avoiding dependence on system wall-clock adjustments while a request is running. Do not store a created deadline in a singleton to reuse across subsequent requests; the expiration point continues ticking.

### Relative Deadlines

withDeadlineAfter is suitable when each RPC has its own budget measured from when the call is prepared:

~~~java
PaymentResponse response = baseStub
    .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

The base stub remains usable for subsequent calls. However, do not create a stub with withDeadlineAfter inside a Spring bean's constructor and keep it long-term. The deadline is computed immediately when the method is called; a long-lived cached stub may expire before the next request starts.

## 3. Preserving the Parent Deadline for Downstream Calls

In a Spring gRPC service, the current RPC may call another service. The downstream budget must stay within the parent request's remaining deadline. You can choose the earlier deadline between the child budget and the current Context's deadline:

~~~java
private PaymentServiceBlockingStub stubForCurrentCall(
        Duration childBudget) {

    if (childBudget.isZero() || childBudget.isNegative()) {
        throw new IllegalArgumentException(
            "childBudget must be positive");
    }

    Deadline child = Deadline.after(
        childBudget.toNanos(), TimeUnit.NANOSECONDS);
    Deadline parent = Context.current().getDeadline();

    if (parent != null && parent.isBefore(child)) {
        child = parent;
    }

    return baseStub.withDeadline(child);
}
~~~

If the parent deadline has already expired, the child call expires as well; do not grant a new duration to extend the request. If the parent service needs time to process the response, subtract that reserve from childBudget before creating the deadline.

When offloading work to another executor, capture Context before submitting and use Context.wrap or fixedContextExecutor. If the parent context is lost, child calls may no longer properly receive the original request's cancellation and deadline.

## 4. withCallCredentials Attaches Credentials to the RPC

CallCredentials is the gRPC Java abstraction for producing authentication metadata for a call. It is suited for bearer tokens, service tokens, or credentials refreshed periodically. Credentials should not be manually embedded into every business request message.

Example of attaching credentials to a stub:

~~~java
CallCredentials credentials = bearerTokenCredentials;

PaymentServiceBlockingStub securedStub =
    PaymentServiceGrpc.newBlockingStub(channel)
        .withCallCredentials(credentials);
~~~

When an RPC is created, gRPC invokes the credential's applyRequestMetadata method to obtain the metadata to send. Credentials can be called repeatedly and across concurrent calls; implementations must be thread-safe.

## 5. Building Non-Blocking Bearer CallCredentials

The example below uses a TokenProvider returning a CompletionStage so token acquisition can be asynchronous. Metadata is only constructed when the call needs credentials:

~~~java
import io.grpc.CallCredentials;
import io.grpc.Metadata;
import io.grpc.SecurityLevel;
import io.grpc.Status;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;

public final class BearerTokenCredentials extends CallCredentials {

    private static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
            "authorization",
            Metadata.ASCII_STRING_MARSHALLER);

    private final TokenProvider tokenProvider;

    public BearerTokenCredentials(TokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public void applyRequestMetadata(
            RequestInfo requestInfo,
            Executor appExecutor,
            MetadataApplier applier) {

        if (requestInfo.getSecurityLevel()
                != SecurityLevel.PRIVACY_AND_INTEGRITY) {
            applier.fail(Status.UNAUTHENTICATED.withDescription(
                "bearer token requires a protected transport"));
            return;
        }

        CompletionStage<String> tokenStage;
        try {
            tokenStage = tokenProvider.fetchAccessToken();
        } catch (RuntimeException ex) {
            applier.fail(Status.UNAUTHENTICATED
                .withDescription("unable to obtain access token")
                .withCause(ex));
            return;
        }

        tokenStage.whenCompleteAsync((token, error) -> {
            if (error != null) {
                applier.fail(Status.UNAUTHENTICATED
                    .withDescription("access token request failed")
                    .withCause(error));
                return;
            }
            if (token == null || token.isBlank()) {
                applier.fail(Status.UNAUTHENTICATED
                    .withDescription("access token is empty"));
                return;
            }

            Metadata headers = new Metadata();
            headers.put(AUTHORIZATION, "Bearer " + token);
            applier.apply(headers);
        }, appExecutor);
    }
}
~~~

TokenProvider is an application interface, for example:

~~~java
public interface TokenProvider {
    CompletionStage<String> fetchAccessToken();
}
~~~

The implementation does not block appExecutor to call the token endpoint. If tokens are cached, you must manage expiry, refresh before expiration, synchronize when multiple RPCs trigger refresh concurrently, and avoid logging tokens. Each call should only receive a valid token for the right audience/scope.

The example checks SecurityLevel to require a transport protecting confidentiality and integrity. Thus, bearer tokens are only sent over TLS; do not downgrade transport security to make tests pass. In tests, use TLS test certificates or appropriate mock credentials/providers.

## 6. Combining Deadlines and Credentials on the Same Stub

The two configuration methods modify different parts of CallOptions, so they can be chained:

~~~java
PaymentResponse response = baseStub
    .withCallCredentials(bearerCredentials)
    .withDeadlineAfter(600, TimeUnit.MILLISECONDS)
    .getPayment(request);
~~~

Or:

~~~java
PaymentResponse response = baseStub
    .withDeadlineAfter(600, TimeUnit.MILLISECONDS)
    .withCallCredentials(bearerCredentials)
    .getPayment(request);
~~~

In both forms, the RPC is invoked on the final stub and carries both the deadline and credentials. Do not discard the stub returned at any step.

Note: CallOptions holds a single CallCredentials. If you call withCallCredentials again on a stub that already has credentials, the new configuration replaces the previous credentials rather than automatically combining them. If multiple authentication metadata sources are needed, merge them intentionally inside a single CallCredentials implementation or design a composite credential provider.

## 7. Deadlines Include Credential Acquisition Time

Token acquisition happens while preparing metadata for the RPC and can consume part of the call's time budget. If the token endpoint is slow, a short deadline can expire before the business request is sent to the server.

Therefore:

- The token provider needs its own timeout and must not wait indefinitely.
- Tokens should be cached safely by expiry/scope to avoid calling the auth server on every RPC when policy permits.
- Do not set a business deadline so short that it ignores authentication time.
- If the deadline expires while fetching a token, do not proceed to send the request with a late-arriving credential.
- Do not create a new deadline after obtaining the token; the call must still obey the original budget.

## 8. Distinguishing CallCredentials from Interceptors and Metadata

| Mechanism | Used For | Notes |
| --- | --- | --- |
| CallCredentials | Per-call authentication credentials | Has async callback, receives call info and security level |
| ClientInterceptor | Cross-cutting behavior such as tracing, correlation IDs, logging, or call policies | Can modify CallOptions or wrap ClientCall |
| Manual Metadata | Call-specific headers | Prone to boilerplate and credential leaks if mismanaged |

Do not put a static bearer token into a shared interceptor if tokens need refreshing or vary by user/tenant. CallCredentials is a better fit for dynamic authentication data. Interceptors can add trace IDs, but should not log authorization metadata.

## 9. Integrating Credentials in Spring

You can register TokenProvider and CallCredentials as beans:

~~~java
@Configuration
public class PaymentCredentialConfiguration {

    @Bean
    CallCredentials paymentCallCredentials(TokenProvider tokenProvider) {
        return new BearerTokenCredentials(tokenProvider);
    }

    @Bean
    PaymentServiceBlockingStub paymentStub(
            ManagedChannel paymentChannel,
            CallCredentials paymentCallCredentials) {
        return PaymentServiceGrpc.newBlockingStub(paymentChannel)
            .withCallCredentials(paymentCallCredentials);
    }
}
~~~

This example assumes the channel is already configured with TLS and managed by Spring. If the starter provides its own channel/stub beans, use the starter's extension points and avoid creating duplicate channels. TokenProvider should be injected from the application's identity/OAuth mechanism; do not hard-code client secrets or access tokens in source code.

Services can create a separate deadline per method:

~~~java
public PaymentResponse getPayment(PaymentRequest request) {
    return paymentStub
        .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
        .getPayment(request);
}
~~~

Credentials are inherited from the base stub, while the deadline is newly created for the logical RPC.

## 10. Testing Deadlines and CallCredentials

Tests should cover:

1. Derived stub with both deadline and credentials; server receives valid authorization metadata.
2. Base stub remains unchanged after creating derived stubs with different deadlines.
3. Call with a short deadline ends with DEADLINE_EXCEEDED when the server is slow.
4. Token provider returns an error or empty token; client does not send an unauthenticated RPC and receives the appropriate authentication error.
5. Transport lacks a secure SecurityLevel; credentials refuse to send the bearer token.
6. Slow token provider; deadline still bounds the total time to prepare and execute the call.
7. Two concurrent calls share the same credential bean yet receive the right token/context per policy.
8. Calling withCallCredentials a second time does not accidentally overwrite required credentials.

In-process transport can be used to test deadlines and callback logic, but tests requiring SecurityLevel.PRIVACY_AND_INTEGRITY need a real TLS transport or isolated credential tests. Do not use trust-all in TLS integration tests.

## 11. Common Pitfalls and How to Handle Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling withDeadlineAfter and discarding the returned stub | Deadline is not applied to the RPC | Invoke the method on the final derived stub |
| Caching a stub with a relative deadline in a singleton | Subsequent calls may expire immediately | Store the base stub, create deadlines per call |
| Using a static token in a long-lived stub | Expired tokens keep getting sent | Use CallCredentials to fetch valid tokens |
| Blocking while fetching tokens on the callback executor | Stalls the metadata-supplying executor | Use an async token provider with a timeout |
| Calling withCallCredentials multiple times expecting accumulation | Previous credentials get replaced | Use a purposeful composite credential |
| Sending bearer tokens over plaintext | Exposes credentials on the network | Require TLS and check security level |
| Creating a new deadline after obtaining the token | Total time exceeds the caller's SLA | Keep one deadline for the entire logical call |

## 12. Takeaways and Self-Check

**withDeadline/withDeadlineAfter bound execution time; withCallCredentials supplies authentication metadata.** Both return a new immutable stub and can be combined on the same derived stub. Use a shared base stub, create deadlines near call time, propagate parent deadlines downstream, and let CallCredentials fetch dynamic tokens asynchronously over TLS.

Self-check:

1. When should you use withDeadline instead of withDeadlineAfter?
2. Why should you not store a stub configured with withDeadlineAfter in a Spring singleton?
3. How does CallCredentials differ from ClientInterceptor in purpose and metadata lifecycle?
4. Why does a token provider need to be asynchronous and have its own timeout?
5. What happens when calling withCallCredentials a second time on a stub that already has credentials?
6. Why must the deadline include token acquisition time?

Combining per-RPC deadlines with CallCredentials properly lets a Spring gRPC client both bound wait time and send credentials safely and consistently without one request's configuration affecting another.
