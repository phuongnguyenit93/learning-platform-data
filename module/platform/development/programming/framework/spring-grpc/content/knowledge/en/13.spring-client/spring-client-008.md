# Default Client Timeouts

A gRPC client may call a server successfully in development yet hold requests for far too long when the server slows down, the network stalls, or an endpoint stops responding. A common cause is calls lacking a **deadline**. In gRPC Java, if the client sets no deadline and no timeout policy comes from service configuration, a call can keep waiting until it finishes, is cancelled, or the connection fails.

In a Spring application, we generally want a **default timeout** so every RPC has a reasonable time limit, while still letting specific business flows set their own deadline when needed. This lesson focuses on configuring a default policy, precedence with explicit deadlines, choosing timeouts by RPC type, and verifying expiration behavior. It belongs to the Spring client section of the **SPRING_GRPC** module, where clients are built from Protocol Buffers contracts and generated Java stubs while handling metadata, statuses, interceptors, TLS, streaming, testing, and reliability.

## 1. A Client Timeout Is Actually an RPC Deadline

In gRPC, the client bounds an RPC's duration with a **deadline**: an absolute point in time after which the call is considered expired. Java APIs usually accept a duration and convert it into a deadline, for example:

```java
HelloReply reply = greeterStub
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .sayHello(request);
```

`withDeadlineAfter(2, SECONDS)` produces a stub instance with a deadline for that call. If the RPC has not completed within two seconds, the client ends the call with status `DEADLINE_EXCEEDED`. The deadline covers the entire client-side RPC budget, including waiting for connection/readiness and communicating with the server; it does not measure only how long the server spends inside its business method.

Distinguish these concepts:

| Concept | Meaning | Does It Replace an RPC Deadline? |
| --- | --- | --- |
| RPC deadline / timeout | Time limit a single call is allowed to remain active. | This is the mechanism you should use to bound RPCs. |
| Connection timeout | Time or policy related to establishing the transport connection. | No. A channel can reconnect; each RPC still needs its own deadline. |
| Keepalive | Mechanism for probing HTTP/2 connection liveness with pings. | No. Keepalive does not cap how long an RPC may run. |
| Retry backoff | Wait interval between retry attempts. | No. Retry attempts still consume the RPC's deadline budget. |
| HTTP request timeout | Time limit an upstream HTTP request waits for the application. | No. Propagate remaining budget down to the RPC so the RPC does not outlive the originating request. |

By default, gRPC Java does not attach a finite deadline to every RPC automatically. Thus, if the application applies no default policy and callers omit `withDeadlineAfter(...)`, an RPC can wait for a very long time. That is why clients should configure a default timeout.

## 2. Choosing an Appropriate Default Policy

A default timeout should reflect how long the application can afford to wait for the remote service, rather than picking an arbitrary number for every case. A small data lookup typically has a tight budget; an aggregation RPC or multi-step operation may need longer. For streaming, a timeout generally applies to the **entire stream duration**, so a short value like two seconds may fit a unary RPC yet break a subscription meant to stay open longer.

When choosing values, consider:

- **SLOs and actual latency:** use high-percentile latency distributions (such as p95/p99), plus budget for network and client-side processing.
- **Upstream request timeouts:** if an HTTP request is only allowed three seconds, a gRPC call should not have a five-second deadline.
- **Number of RPCs in a business flow:** if one request calls multiple services sequentially, the total budget must cover those steps; do not grant the full timeout afresh at every step without accounting for elapsed time.
- **RPC type:** unary calls usually have short deadlines; server/client/bidirectional streaming need policies aligned with stream lifetime and cancellation support.
- **Retries:** retry attempts share the call's time budget; too short a timeout leaves retries no room to finish.

For instance, an application might set defaults of 2 seconds for `SayHello`, 800 milliseconds for `GetStock`, and 30 seconds for a report-generation RPC. Exact values should be validated against measurements and system SLOs.

## 3. Setting Default Timeouts with gRPC Service Config

gRPC supports per-service and per-method configuration via **Service Config**. In gRPC Java, `ManagedChannelBuilder.defaultServiceConfig(...)` accepts a configuration map. Each `methodConfig` can apply a timeout to one method or all methods of a service.

The example below sets a two-second default timeout for every RPC in service `greeting.v1.Greeter`, unless a more specific method config is declared:

```java
import java.util.List;
import java.util.Map;

Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(
                Map.of(
                        "name", List.of(
                                Map.of("service", "greeting.v1.Greeter")
                        ),
                        "timeout", "2s"
                )
        )
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///greeter.internal:7443")
        .useTransportSecurity()
        .defaultServiceConfig(serviceConfig)
        .build();
```

The service name under `name` must match the full name in the Protobuf contract: package `greeting.v1` plus service `Greeter`. To target a specific method, add `"method", "SayHello"` to the `name` map. `timeout` is a duration string in Service Config format, such as `"800ms"`, `"2s"`, or `"1m"`.

You can define different timeouts per method:

```java
Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(
                Map.of(
                        "name", List.of(Map.of(
                                "service", "inventory.v1.Inventory",
                                "method", "GetStock")),
                        "timeout", "800ms"
                ),
                Map.of(
                        "name", List.of(Map.of(
                                "service", "inventory.v1.Inventory",
                                "method", "WatchStock")),
                        "timeout", "30s"
                )
        )
);
```

In this example, `GetStock` gets a tight budget while `WatchStock` is allowed to run longer. For an unbounded stream, a 30-second deadline will still terminate the stream after 30 seconds; if the business case needs a long-lived subscription, design stream lifetime management, heartbeats, cancellation, and resubscription instead of treating a long timeout as an infinite stream.

`defaultServiceConfig(...)` is **the channel's default configuration**. If a `NameResolver` supplies its own Service Config, the resolver-provided configuration may take precedence depending on gRPC behavior and channel settings. Therefore, when using DNS or service discovery, inspect the actual config the client receives; do not assume the default map always overrides resolver-distributed config. If you want centralized control via static config, align the environment's resolver/service-config policy.

## 4. Putting Default Timeouts into Spring Boot Configuration

To vary timeouts across environments without editing Java code, place them in `application.yml`:

```yaml
app:
  grpc:
    greeter:
      target: dns:///greeter.internal:7443
      default-timeout: 2s
```

Bind the configuration to a `Duration`:

```java
package com.example.client;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.grpc.greeter")
public record GreeterClientProperties(
        String target,
        Duration defaultTimeout) {

    public GreeterClientProperties {
        if (target == null || target.isBlank()) {
            throw new IllegalArgumentException("gRPC target must not be empty");
        }
        if (defaultTimeout == null || defaultTimeout.isZero()
                || defaultTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "default-timeout must be greater than 0");
        }
    }
}
```

Spring Boot converts `2s` into `Duration.ofSeconds(2)`. In production systems, enforce an upper bound so a misconfiguration cannot make RPCs wait excessively. When calling `toNanos()` or `toMillis()` to build a deadline, also guard against huge durations overflowing or tiny durations rounding down to 0.

## 5. Approach 1: Applying a Default via a Client Interceptor

A client interceptor can attach a deadline when a call has no explicit deadline yet. This is useful when you want **a uniform fallback** for all methods passing through a channel without adding `withDeadlineAfter(...)` in every application service.

`DefaultDeadlineInterceptor.java`:

```java
package com.example.client;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.Deadline;
import io.grpc.MethodDescriptor;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class DefaultDeadlineInterceptor implements ClientInterceptor {

    private final Duration defaultTimeout;

    public DefaultDeadlineInterceptor(Duration defaultTimeout) {
        if (defaultTimeout == null || defaultTimeout.isZero()
                || defaultTimeout.isNegative()) {
            throw new IllegalArgumentException(
                    "defaultTimeout must be greater than 0");
        }
        this.defaultTimeout = defaultTimeout;
    }

    @Override
    public <RequestT, ResponseT> ClientCall<RequestT, ResponseT> interceptCall(
            MethodDescriptor<RequestT, ResponseT> method,
            CallOptions callOptions,
            Channel next) {

        CallOptions effectiveOptions = callOptions;
        if (callOptions.getDeadline() == null) {
            long timeoutNanos = defaultTimeout.toNanos();
            effectiveOptions = callOptions.withDeadline(
                    Deadline.after(timeoutNanos, TimeUnit.NANOSECONDS));
        }

        return next.newCall(method, effectiveOptions);
    }
}
```

The interceptor only sets a deadline when `CallOptions` does not already have one. If the application service called `stub.withDeadlineAfter(500, MILLISECONDS)`, the interceptor keeps the 500 ms deadline instead of replacing it with the 2-second default. That is the semantics of a **default**: fill in when absent, without overriding a specific policy chosen by the caller.

Register the interceptor on the channel:

```java
package com.example.client;

import com.example.contract.grpc.GreeterGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GreeterClientProperties.class)
public class GreeterClientConfiguration {

    @Bean(name = "greeterChannel", destroyMethod = "shutdown")
    ManagedChannel greeterChannel(GreeterClientProperties properties) {
        return ManagedChannelBuilder.forTarget(properties.target())
                .useTransportSecurity()
                .intercept(new DefaultDeadlineInterceptor(
                        properties.defaultTimeout()))
                .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterBlockingStub(
            @org.springframework.beans.factory.annotation.Qualifier("greeterChannel")
            ManagedChannel channel) {
        return GreeterGrpc.newBlockingStub(channel);
    }
}
```

In this example, the target uses TLS; when running locally without TLS, configure `usePlaintext()` under a development profile. The channel is managed by Spring and `destroyMethod` initiates shutdown when the context closes. The interceptor applies to every RPC traversing this channel, so if one channel handles both unary and streaming methods, the default timeout must suit all of them or you should switch to per-method policies in Service Config.

**Note when combining Service Config and interceptors:** both mechanisms can influence RPC deadlines. Avoid configuring two conflicting values without defining effective precedence. Choose one primary default source and use explicit caller deadlines for special cases. If the system receives Service Config from a resolver, verify precedence and effective deadlines with integration tests.

## 6. Approach 2: Per-Method Defaults Using Service Config in Spring

When timeouts need to vary by method, Service Config usually expresses intent more clearly than a single global interceptor. Build the config map inside a dedicated configuration class:

```java
package com.example.client;

import com.example.contract.grpc.GreeterGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GreeterClientProperties.class)
public class GreeterServiceConfigClientConfiguration {

    @Bean(name = "greeterChannel", destroyMethod = "shutdown")
    ManagedChannel greeterChannel(GreeterClientProperties properties) {
        Map<String, ?> serviceConfig = Map.of(
                "methodConfig", List.of(
                        Map.of(
                                "name", List.of(Map.of(
                                        "service", "greeting.v1.Greeter",
                                        "method", "SayHello")),
                                "timeout", properties.defaultTimeout().toMillis() + "ms"
                        )
                )
        );

        return ManagedChannelBuilder.forTarget(properties.target())
                .useTransportSecurity()
                .defaultServiceConfig(serviceConfig)
                .build();
    }

    @Bean
    GreeterGrpc.GreeterBlockingStub greeterBlockingStub(ManagedChannel greeterChannel) {
        return GreeterGrpc.newBlockingStub(greeterChannel);
    }
}
```

This is an **alternative** to the interceptor configuration in section 5. Do not place two `@Configuration` classes defining the same `greeterChannel` and `greeterBlockingStub` beans in the same context. Service Config applies the timeout to the declared method; if you want a service-wide default across all methods, omit the `method` field and keep only the service name under `name`.

When configuring per method, ensure the service/method strings match the exact names in `.proto`, including the package. A typo prevents the method from matching the intended config and leaves the RPC without that timeout. Tests should invoke the real method against a slow server and verify `DEADLINE_EXCEEDED`, rather than merely checking that the map was constructed.

## 7. How Can Callers Override with Custom Timeouts?

A default timeout should not take away per-operation deadline control. A fast inventory lookup might require 300 ms; an aggregated report might need 5 seconds. The caller creates a per-RPC stub variant:

```java
import com.example.contract.grpc.HelloRequest;
import com.example.contract.grpc.HelloReply;
import java.util.concurrent.TimeUnit;

HelloRequest request = HelloRequest.newBuilder()
        .setName("Lan")
        .build();

// Use an explicit 500 ms deadline for latency-sensitive operations.
HelloReply quickReply = greeterStub
        .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
        .sayHello(request);

// No deadline set by caller: use the client's default policy.
HelloReply normalReply = greeterStub.sayHello(request);
```

With the interceptor from section 5, the first call keeps 500 ms and the second call gets the default timeout. `withDeadlineAfter(...)` returns a new stub; the shared stub bean is untouched after a request. If a caller sets a deadline longer than the default, the illustrative interceptor still preserves the caller's deadline because it only fills in missing deadlines. If your organization wants a **maximum cap** instead of a fallback default, write an interceptor that compares both deadlines and picks the earlier one; that is a distinct policy and should be named and tested explicitly.

If a request runs inside an existing gRPC `Context` that already carries a deadline, gRPC Java can apply the shorter remaining context deadline when creating an outbound RPC. When propagating budget from an HTTP request to gRPC, pass the **remaining time**, rather than resetting the original full timeout at every service hop.

## 8. How Deadlines Affect the Server and Retries

When a client sets a deadline, gRPC propagates remaining timeout information over the wire. The server can detect when an RPC expires or is cancelled and stop work if its implementation checks context/cancellation. That prevents the server from continuing to burn resources on a request the client is no longer waiting for.

However, a deadline **is not a transaction rollback**. If the server already wrote data before expiration, the client receiving `DEADLINE_EXCEEDED` does not mean the operation never happened. For order-creation, payment, or inventory-update RPCs, use idempotency keys, status checks, and appropriate retry contracts.

When enabling retries via Service Config, attempts consume the RPC's deadline budget; do not treat each attempt as getting a fresh default timeout. For example, if an RPC has a two-second deadline and the first attempt takes 1.5 seconds, the next attempt only has the remaining budget. Backoff and retry policies must fit within the overall budget.

Distinguish statuses during diagnosis:

| Status | Meaning | How to Investigate |
| --- | --- | --- |
| `DEADLINE_EXCEEDED` | RPC did not finish before its deadline. | Check latency, server load, caller deadline, and default timeout. |
| `UNAVAILABLE` | Service/transport temporarily unavailable. | Check DNS, network, TLS, server health, and retry policy. |
| `CANCELLED` | Call cancelled by caller, context, or system. | Determine whether the upstream request was cancelled or the app is shutting down. |
| `RESOURCE_EXHAUSTED` | Server or transport rejected the call due to resource/policy limits. | Check load, quotas, message size limits, and retry-after guidance if any. |
| `INVALID_ARGUMENT` | Request invalid per contract/business rules. | Fix request data; increasing the timeout usually will not help. |

Do not convert every `DEADLINE_EXCEEDED` into `UNAVAILABLE` at the application layer. Preserving the distinction yields more accurate metrics and better retry decisions.

## 9. Default Timeouts with Streaming RPCs

A streaming RPC's deadline applies to **the entire RPC**, not the maximum gap between two messages. If a server-streaming RPC is designed to stream data continuously for 10 minutes while the channel has a 2-second default timeout, the stream will terminate prematurely even though the server is healthy.

Three common design approaches:

1. **Per-method timeout:** use Service Config to give streaming methods a longer limit while keeping unary methods short.
2. **Caller-supplied deadline:** use `withDeadlineAfter(...)` matching the specific job's lifetime; when a stream must last long, pick an intentional bound.
3. **Long-lived streams with resubscription:** avoid an unbounded single RPC if the system needs connection management; use cancellation, heartbeats, resume tokens/offsets, and application-driven reconnection.

Do not confuse a deadline with an idle timeout. If the requirement is "cancel the stream when no message arrives for 30 seconds," you need an inactivity monitor or heartbeat mechanism; a 30-second deadline cancels the stream 30 seconds after it starts even if messages arrive steadily.

With client-streaming and bidirectional-streaming RPCs, the client must also handle `onError`/`onCompleted` callbacks, close the request observer, and cancel cleanly on deadline expiration. On an async stub, expiration status usually arrives in `onError(Throwable)`; use `Status.fromThrowable(error)` to read `DEADLINE_EXCEEDED`.

## 10. Testing Default Timeouts

Tests should prove three distinct behaviors:

- An RPC without an explicit deadline receives the default timeout.
- An RPC with a shorter explicit deadline keeps that shorter deadline.
- A slow RPC exceeding the limit terminates with `DEADLINE_EXCEEDED`, completing the callback or blocking call cleanly.

You can use a gRPC in-process server with an implementation that intentionally delays its response. Run tests on an appropriate executor so slow server work does not block the test thread itself; use a `CountDownLatch` or scheduler to control response timing instead of long, flaky `Thread.sleep()` calls. When testing deadlines, leave enough margin so CI scheduling jitter does not cause flakiness.

Conceptual test example with a blocking stub:

```java
// Test Greeter server does not send a response within the timeout window.
// Channel is configured with DefaultDeadlineInterceptor(Duration.ofMillis(100)).
assertThrows(StatusRuntimeException.class, () ->
        greeterBlockingStub.sayHello(request));
```

After the assertion, verify `Status.fromThrowable(exception).getCode()` equals `DEADLINE_EXCEEDED`. This snippet assumes the test server holds the RPC long enough for the deadline to expire before replying; release any latches and shut down the server/channel in `finally` so the test leaks no resources.

For an async stub, use an observer or a `CompletableFuture` to wait with a bounded test timeout, then verify the error flows to `onError`. If using `CompletableFuture.get(...)`, do so only in tests and always pass a timeout for the test wait itself; never turn production async calls into blocking calls by calling `.get()` right after the RPC.

In-process tests verify gRPC client/server deadline logic and status handling, but they do not test TLS, DNS, proxies, or HTTP/2 over the network. Use TCP/TLS integration tests when verifying timeouts in deployment-like environments. Also test that the server reacts to cancellation, rather than only verifying the client stopped waiting while the server kept performing expensive work.

## 11. Observing Timeouts in Production

A default timeout is only useful when operations teams know it is taking effect and can tune it from real telemetry. Monitor by **service/method**:

- Total RPC count and `DEADLINE_EXCEEDED` rate.
- p50/p95/p99 latency compared against configured timeouts.
- Retry counts, attempt counts, and backoff time if retries are enabled.
- `CANCELLED` RPC rate, distinguishing client disconnects from application shutdowns.
- Streaming methods ending due to deadlines and actual stream durations.

Logs should include method, logical client name, status, and correlation/trace ID. Never log auth tokens or secret metadata. Avoid using request IDs as metric labels due to high cardinality. When timeout rates spike, inspect server load, network latency, resolvers, pools/executors, and upstream deadlines before simply raising the timeout. Increasing timeouts can make requests wait longer and pile up concurrent work, worsening overload incidents.

## 12. Common Mistakes

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| RPC hangs indefinitely even though channel is connected | Missing deadline on caller and no default policy. | Set a default timeout via Service Config/interceptor or an explicit deadline. |
| Raising connect timeout still leaves RPCs hanging | Confusing connect/keepalive with RPC deadlines. | Bound each RPC's duration. |
| Interceptor overwrites a 300 ms deadline with 2 seconds | Interceptor unconditionally replaces deadlines. | Apply default only when caller set none; if a max cap is needed, pick the earlier deadline. |
| Unary calls work fine but streams get cut off early | Short global default applied to all methods. | Configure per-method timeouts or separate stream policies. |
| Second service call times out past the HTTP request limit | Granting the full default instead of remaining time. | Propagate remaining deadline/budget across layers. |
| Retries push the RPC past business budgets | Treating each attempt as having an unbounded fresh timeout. | Keep an overall deadline, cap retries, and bound backoff. |
| Client gets `DEADLINE_EXCEEDED` yet data was written | Server committed before receiving cancellation. | Use idempotency keys and business-state checks. |
| Service Config has no effect as expected | Wrong service/method name or resolver supplies another config. | Verify full method name and effective Service Config. |
| Timeout configured as 0 or excessively large | Property values were not validated. | Validate `Duration` when Spring binds/constructs beans. |

## 13. Practice Exercises

1. Build a Spring gRPC client with `default-timeout: 2s`, configure a default deadline via an interceptor, and call a unary RPC without a caller-specified timeout.
2. Set a 300 ms deadline in an application service; verify the interceptor preserves that specific deadline.
3. Switch to Service Config and configure distinct timeouts for `GetStock` and `WatchStock`; verify the exact service/method names from `.proto`.
4. Make the server delay its response past the deadline; verify the blocking stub throws `StatusRuntimeException` with status `DEADLINE_EXCEEDED` and the async stub invokes `onError`.
5. Test a server-streaming RPC emitting messages continuously longer than the default timeout. Contrast whole-stream deadlines with idle timeouts and adjust the policy appropriately.
6. Configure an HTTP timeout shorter than the gRPC default and pass remaining time down to the client; observe the upstream request expiring before the RPC if budget is not propagated properly.
7. Enable retries for an idempotent read RPC, measure total time across attempts, and verify everything stays within the overall deadline.

After this lesson, you should be able to explain why gRPC Java does not automatically assign a finite deadline to every call, how to configure default timeouts with Service Config or interceptors, how to preserve explicit caller deadlines, and why timeouts must fit each method and streaming RPC lifetime. That is the foundation for Spring gRPC clients that bound wait times, curb request pile-ups, and operate reliably when remote services slow down or lose connectivity.
