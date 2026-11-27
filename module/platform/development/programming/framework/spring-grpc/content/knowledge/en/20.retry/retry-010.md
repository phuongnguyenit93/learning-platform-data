# Retry via service config

## 1. Where does service config control retries?

In **Spring gRPC**, retry policies are typically declared in **gRPC service config** on the client side. Service config attaches behavior to a specific service or method, allowing the client channel to automatically retry eligible RPCs without writing resend loops at every stub call site.

A service config can contain multiple `methodConfig` entries. Each entry identifies one or more methods by Protobuf service name and optional method name, then attaches policies such as retry, timeout, or wait-for-ready.

For retries, the client channel reads `retryPolicy` and applies it when:

- The RPC matches the configured service/method name.
- The attempt terminates with a status listed in `retryableStatusCodes`.
- The call has not committed and the runtime still holds the data needed for replay.
- `maxAttempts`, deadline, and retry budget have not been exhausted.
- No pushback or throttling requires stopping retries.

Service config is a **client-side** configuration. The server still needs to return statuses that match the root cause; it does not automatically retry requests on behalf of the client.

## 2. Structure of a service config

JSON example for two methods of `catalog.v1.CatalogService`:

```json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService",
          "method": "GetItem"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "2s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [
          "UNAVAILABLE"
        ]
      }
    },
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService",
          "method": "SearchItems"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 3,
        "initialBackoff": "0.1s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [
          "UNAVAILABLE",
          "RESOURCE_EXHAUSTED"
        ]
      }
    }
  ]
}
```

Here:

- `GetItem` retries only `UNAVAILABLE`, up to four total attempts.
- `SearchItems` retries `UNAVAILABLE` and `RESOURCE_EXHAUSTED`, up to three attempts.
- Each method has its own backoff, matching its different SLA and load tolerance.

The service name is the full name consisting of the Protobuf package and service name: `catalog.v1.CatalogService`. The method name is the RPC name in the service: `GetItem`, not the Java method name or stub class name.

### 2.1. Applying to an entire service

If an entry in `name` specifies only `service` and omits `method`, the policy applies to all methods in that service:

```json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 3,
        "initialBackoff": "0.2s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
```

A service-level policy is convenient, yet may not fit every method. For example, `GetItem` may be safe to retry while `CreateItem` has side effects. Prefer configuring each method explicitly when semantics differ; avoid a broad policy that accidentally enables retries for non-idempotent commands.

## 3. Meaning of retryPolicy fields

| Field | Meaning | Notes |
| --- | --- | --- |
| `maxAttempts` | Maximum total attempts, including the initial one | Not the number of extra retries; runtime may enforce implementation limits |
| `initialBackoff` | Base waiting interval before the first retry | Uses duration string format, e.g. `"0.2s"` |
| `maxBackoff` | Cap on base waiting interval | Does not reset the deadline |
| `backoffMultiplier` | Backoff growth factor | Typically used for exponential backoff |
| `retryableStatusCodes` | Statuses that can trigger a retry | Select only recoverable errors |

A few points to remember:

- `maxAttempts = 4` means at most four total attempts, equivalent to at most three additional retries. According to the gRPC retry guide, this value is capped at a maximum of 5.
- gRPC applies backoff and jitter according to its runtime mechanism; service config does not have a `jitter` field to pick a custom algorithm.
- `DEADLINE_EXCEEDED` should not be added arbitrarily: the server may have already executed side effects while the response arrived late.
- `RESOURCE_EXHAUSTED` should be retried only if it indicates temporary overload; fixed quotas or oversized payloads will not self-recover.
- Statuses outside the list terminate the call without retrying under that policy.

## 4. Attaching service config to a gRPC Java channel

gRPC Java accepts service config as a `Map<String, ?>`. You can build the map directly:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;

Map<String, Object> retryPolicy = Map.of(
        "maxAttempts", 4.0,
        "initialBackoff", "0.2s",
        "maxBackoff", "2s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "catalog.v1.CatalogService",
                "method", "GetItem")),
        "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig =
        Map.of("methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .enableRetry()
        .defaultServiceConfig(serviceConfig)
        .build();
```

In the Java example, numeric values are represented as `Double` (`4.0`, `2.0`) to match how gRPC Java parses JSON-like service config maps. Durations remain strings with unit suffixes.

`enableRetry()` enables retries on the channel. Verify that the channel configuration does not call `disableRetry()`; if retries are disabled, declaring a policy will not cause attempts to be resent.

Channels should be created once and managed by the application lifecycle. Do not create a new channel per RPC just to change `maxAttempts`; doing so increases connections, threads, and management overhead.

## 5. Default service config vs. name resolver config

gRPC Java can receive service config from two sources:

- **Resolver-provided service config:** the name resolver, typically tied to DNS or service discovery, provides config for the target.
- **Default service config:** attached by the application via `defaultServiceConfig(...)` on the channel builder.

`defaultServiceConfig` is the fallback configuration when the resolver does not provide a service config. If the resolver provides its own config, the resolver's config takes precedence under gRPC's service config mechanism. Consequently, the configuration in code is not necessarily the final policy running in production.

This matters when moving from local to Kubernetes/service discovery:

1. Local environments may use the default config declared in the application.
2. Production DNS resolvers may obtain service config from DNS TXT records or the corresponding resolver.
3. Actual policies can differ across environments if resolvers return different configs.
4. You must observe/configure which service config sources are allowed and verify the effective policy.

Do not place conflicting retry policies across multiple sources without governance. When an incident occurs, operations teams need to know which policy the client is actually using, not just what is written in source code.

## 6. Service config in a Spring gRPC application

Spring gRPC manages client channel/stub creation based on application configuration. The service config must be attached to **the builder/channel before the channel is built**. Exact integration depends on the Spring gRPC version and how the project creates channels:

- If the application creates `ManagedChannel` directly, attach `defaultServiceConfig` as shown above.
- If the application uses a channel factory or Spring-managed bean, configure retry at the channel builder customization hook provided by that version.
- If channels are created by another library, identify clearly where service config is configured and where shutdown is managed.

Do not assume that injecting a generated stub automatically means retries are enabled. Whichever channel the stub uses determines retry behavior via that channel and its effective service config.

Example of organizing configuration in an application:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import com.example.catalog.v1.CatalogServiceGrpc;

@Configuration
public class CatalogClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel catalogChannel() {
        Map<String, Object> retryPolicy = Map.of(
                "maxAttempts", 4.0,
                "initialBackoff", "0.2s",
                "maxBackoff", "2s",
                "backoffMultiplier", 2.0,
                "retryableStatusCodes", List.of("UNAVAILABLE"));

        Map<String, Object> methodConfig = Map.of(
                "name", List.of(Map.of(
                        "service", "catalog.v1.CatalogService",
                        "method", "GetItem")),
                "retryPolicy", retryPolicy);

        Map<String, Object> config =
                Map.of("methodConfig", List.of(methodConfig));

        return ManagedChannelBuilder
                .forAddress("catalog.internal", 9090)
                .enableRetry()
                .defaultServiceConfig(config)
                .build();
    }

    @Bean
    CatalogServiceGrpc.CatalogServiceBlockingStub catalogStub(
            ManagedChannel catalogChannel) {
        return CatalogServiceGrpc.newBlockingStub(catalogChannel);
    }
}
```

This is an example of Spring Java config managing its own channel. If the project already uses a Spring gRPC channel factory, do not create an extra parallel channel; pass the same configuration into the existing builder/customizer to maintain a single source for connection management and shutdown.

## 7. Retry throttling in service config

When many RPCs fail continuously, retries can add load right when the server is overloaded. Service config supports `retryThrottling` at the config level:

```json
{
  "retryThrottling": {
    "maxTokens": 10,
    "tokenRatio": 0.1
  },
  "methodConfig": [
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService",
          "method": "GetItem"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "2s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
```

Retry throttling maintains a token budget, initialized at `maxTokens`:

- Retryable failures decrement tokens.
- Successes increment tokens by `tokenRatio`, up to `maxTokens`.
- When tokens drop below half of `maxTokens`, the runtime throttles retries for the target.

Throttling helps curb retry amplification as errors spike. It does not replace `maxAttempts`, backoff, or deadlines, nor does it make non-retryable statuses retryable.

## 8. Server pushback and client policy

Service config specifies which statuses can be retried and how to back off. The server can still send retry pushback to instruct the client to wait or stop retrying. In gRPC, pushback is sent via the special metadata `grpc-retry-pushback-ms`.

- A positive value requests waiting the specified number of milliseconds.
- A negative value requests not retrying that call.
- Pushback does not grant extra deadline and does not increase `maxAttempts`.

Do not build an outer manual retry loop to bypass pushback. If the server is protecting itself from overload, a client that keeps retrying can worsen the outage.

## 9. Method matching and policy scope

Service config matches RPCs by full name:

```text
/catalog.v1.CatalogService/GetItem
 |--------------------------| |---|
         service              method
```

Common configuration mistakes:

| Misconfiguration | Consequence |
| --- | --- |
| Using Java package instead of Protobuf package | Does not match service name |
| Using generated stub class name | Does not match service name |
| Wrong casing in method name | Policy does not apply to the RPC |
| Omitting method when intending to configure one RPC | Policy may apply broadly to the entire service |
| Correct config but stub uses a different channel | RPC does not receive the expected policy |
| Resolver provides a different config | Default config in code may not be the effective config |

Check the method name in the `.proto` file and the full RPC path. A helpful observation technique is to log the method name from client/server interceptors and compare it against the `name` entry in service config.

## 10. Runtime conditions still bound retries

Service config does not bypass core gRPC conditions:

1. **Retryable status:** the ending error must be in `retryableStatusCodes`.
2. **Attempt budget:** `maxAttempts` has not been reached; this includes the initial attempt and implementations may enforce a maximum cap.
3. **Commitment:** the call has not committed; receiving response headers or exceeding the retry buffer can commit the call.
4. **Deadline:** budget remains for backoff and the next attempt.
5. **Pushback/throttling:** the runtime has not been instructed to stop or throttle retries.
6. **Replay safety:** the business operation must be safe when the request is re-executed; write commands require idempotency.

For client-streaming and bidirectional streaming, once the call commits, service config cannot resume the stream from the last message. An application-layer reconnect/resume protocol with sequences, cursors, or idempotency keys is needed.

## 11. Testing service config

There should be an integration test using a real gRPC server/channel over loopback to verify the runtime applies the policy. A test server can return `UNAVAILABLE` twice and then succeed:

```java
import java.util.concurrent.atomic.AtomicInteger;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import com.example.catalog.v1.CatalogServiceGrpc;
import com.example.catalog.v1.GetItemRequest;
import com.example.catalog.v1.GetItemResponse;

AtomicInteger calls = new AtomicInteger();

CatalogServiceGrpc.CatalogServiceImplBase service =
        new CatalogServiceGrpc.CatalogServiceImplBase() {
    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {
        int attempt = calls.incrementAndGet();
        if (attempt <= 2) {
            responseObserver.onError(
                    Status.UNAVAILABLE.asRuntimeException());
            return;
        }
        responseObserver.onNext(GetItemResponse.newBuilder()
                .setItemId(request.getItemId())
                .build());
        responseObserver.onCompleted();
    }
};
```

Create a test channel with a service config having `maxAttempts=3` and retrying `UNAVAILABLE`, then call `GetItem`. Assertions should verify that the client receives a successful response and the server received exactly three attempts. This test must ensure the server does not send response headers before the status on the two failing attempts; otherwise the call could commit and not retry.

Cases to test:

| Scenario | Expected result |
| --- | --- |
| Method matches config, two `UNAVAILABLE`, then succeeds | Client retries and receives response |
| Method without a retry policy entry | Another method's configured retry is not applied |
| Status `INVALID_ARGUMENT` | Does not retry if status is not in the list |
| `maxAttempts` reached | No attempt exceeds the limit |
| Deadline expires during backoff | Call stops, no attempt starts after deadline |
| Resolver provides service config | Verify effective config from resolver source |
| Retry throttling depletes tokens | Retries are throttled once threshold is reached |
| Server pushback requests stopping | Client does not continue retrying that call |
| Call fails after committing | Do not expect automatic replay |
| Write command retried | Same idempotency key creates no duplicate side effects |

Do not merely test that the JSON/map parses successfully. Verify actual attempt counts, final status, total elapsed time, and behavior of methods not matching the policy.

## 12. Observing and operating service config

A policy is only useful when operations teams know it is in effect. Monitor:

- RPC name and service config source (default or resolver).
- Attempt count per logical call.
- Status of each attempt and final status.
- Actual backoff, remaining deadline, and calls terminated by timeout.
- Whether retry throttling/pushback was triggered.
- Retry success rate and extra requests added by retries.

Do not log sensitive payloads or credentials to investigate retries. Correlation IDs/trace IDs should be preserved across attempts if instrumentation supports it, while distinguishing attempt numbers so traces are not mistaken for multiple independent business operations.

When changing policies in production, roll out at the method scope, monitor error/load rates, and keep a rollback plan. Raising `maxAttempts` can increase downstream load; do not treat it as a default fix for outages.

## 13. Common mistakes

1. **Declaring a retry policy without attaching it to the client channel.** The server does not apply policies on behalf of the client.
2. **Using the wrong service/method name.** The policy exists but never matches the RPC.
3. **Assuming `defaultServiceConfig` always wins.** Resolver-provided config can take precedence.
4. **Creating a channel per request.** Increases resources and makes managing retry state harder.
5. **Applying service-level retry to every method.** Can accidentally enable retries for non-idempotent commands.
6. **Ignoring deadlines/commitment.** Config cannot replay calls that have committed or exceeded deadlines.
7. **Nesting retries across multiple layers.** Downstream requests can grow exponentially.
8. **Not testing attempt counts.** A successful final response alone does not prove the policy applied correctly.
9. **Treating retry throttling as a global rate limit.** It regulates retries, and does not replace admission control or rate limits for new requests.

## 14. Practice exercises

For `catalog.v1.CatalogService`:

1. Create separate service configs for `GetItem` and `SearchItems`, each with different statuses, backoff, and `maxAttempts`.
2. Attach the config to a Java channel; verify the Spring stub uses that exact channel.
3. Create a test server returning `UNAVAILABLE` twice then succeeding; verify attempt count.
4. Add a `CreateItem` method with side effects and verify it is not mistakenly covered by a read policy.
5. Test both default service config and resolver-provided config; determine which config is effective.
6. Enable retry throttling, simulate rising failures, and observe retries being throttled.
7. Set a short deadline and verify the call stops before exhausting the attempt budget.

**Completion criteria:** learners can author and attach service configs for the right methods, understand effective config sources, explain runtime retry conditions, and test attempt counts, deadlines, throttling, and policy scope.

### References

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, backoff, commitment, and throttling.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): service config structure and method matching.
- [gRPC Java ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): `defaultServiceConfig()`, `enableRetry()`, and channel configuration.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): client channel and stub integration in Spring.
