# Timeouts, Retries, Exponential Backoff, and Jitter

A Java Spring Boot service calls **Amazon DynamoDB** to read orders, **Amazon S3** to store invoices, and **Amazon SQS** to enqueue background tasks. When a request times out or DynamoDB throttles, retrying without backoff can trigger a retry storm.

Timeouts bound waiting time. Retries recover from transient errors. Exponential backoff and jitter spread out retry attempts. AWS SDK for Java 2.x includes built-in retry strategies, but applications still need to protect idempotency for side effects.

## 1. Learning Objectives

- Distinguish between API call timeout and API attempt timeout.
- Understand standard, adaptive, and legacy retry strategies.
- Configure max attempts, backoff, jitter, and HTTP client timeouts.
- Design idempotent writes and reconciliation.
- Avoid retry amplification, monitor errors, and write tests.

## 2. Timeout Layers

| Timeout | Scope |
|---|---|
| API call timeout | Entire API operation including attempts and backoff |
| API call attempt timeout | A single request attempt |
| Connection timeout | Establishing the TCP connection |
| TLS negotiation timeout | TLS handshake |
| Socket/read timeout | Waiting for response data |
| Write timeout | Sending the request body |
| Connection acquisition timeout | Waiting for a connection from the pool |

AWS SDK for Java 2.x does not set a default API call timeout or API call attempt timeout per current documentation. Configure them to match your application deadline.

Source: https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html

## 3. Retry Strategies

| Strategy | Characteristics |
|---|---|
| Standard | Exponential backoff, jitter, retry quota, and circuit breaking |
| Adaptive | Standard plus a client-side rate limiter |
| Legacy | Older retry behavior for compatibility |

Standard fits most workloads. Adaptive should only be used when the client is isolated to a single resource; throttling on one resource can slow requests to another resource if they share the same client. Legacy should only be kept when backwards compatibility has been evaluated and is required.

Source: https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html

## 4. Defaults Starting in SDK 2.58.0

Starting with AWS SDK for Java 2.x 2.58.0, standard is the default retry strategy per current AWS documentation.

- Most service clients: 3 total attempts, consisting of the initial call and up to two retries.
- DynamoDB and DynamoDB Streams: 4 total attempts under their dedicated default.
- Base transient delay for most clients: 50 ms.
- Base throttling delay: 1 second.
- Backoff includes jitter, with a default maximum delay of 20 seconds.
- Legacy typically performs 4 total attempts for most clients; DynamoDB legacy can perform up to 9.

Check your SDK BOM/version and runtime configuration before relying on defaults.

## 5. Max Attempts and Retry Quota

Max attempts is the total number of attempts, including the initial call:

| Max attempts | Max retries |
|---:|---:|
| 1 | 0 |
| 2 | 1 |
| 3 | 2 |
| 4 | 3 |

The Standard strategy uses a retry quota. Each retry consumes quota; successful requests replenish quota per the SDK's mechanism. Once the quota is exhausted, the SDK still executes the initial attempt but may stop retrying. The retry strategy's circuit breaker can also temporarily halt retries when downstream failures spike.

## 6. Exponential Backoff and Jitter

    delay_limit(retry) = min(max_delay, base_delay × 2^retry)
    delay = random(0, delay_limit)

Full jitter spreads clients out to prevent a thundering herd. The Standard strategy uses exponential backoff with full jitter. Throttling and transient errors have separate base delays; DynamoDB has its own defaults per SDK documentation.

## 7. Retryable vs. Non-Retryable Errors

| Error Type | Example | Retry |
|---|---|---|
| Throttling | Provisioned throughput exceeded | Usually yes, with backoff |
| Transient network | Connection reset, socket timeout | Potentially yes |
| Transient service | Certain 5xx errors | Usually yes |
| Validation | Invalid request field/parameter | No |
| Authorization | Access denied | No |
| Resource missing | Wrong table/bucket/ARN | No |
| Unknown write outcome | Timeout after sending write | Only when idempotent or reconciled |

Do not retry every exception. Retrying permanent errors only increases latency, cost, and downstream load.

## 8. Environment and Profile Configuration

Linux/macOS:

    export AWS_RETRY_MODE=standard
    export AWS_MAX_ATTEMPTS=3

Shared AWS config:

    [profile dev]
    region = ap-southeast-1
    retry_mode = standard
    max_attempts = 3

Precedence order per SDK documentation: explicit configuration in code, environment variables, shared config profile, SDK default.

## 9. Configuring Java Retries

    import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
    import software.amazon.awssdk.core.retry.RetryMode;

    DynamoDbClient client = DynamoDbClient.builder()
        .overrideConfiguration(o -> o
            .retryStrategy(RetryMode.STANDARD)
        )
        .build();

Customizing total attempts:

    DynamoDbClient client = DynamoDbClient.builder()
        .overrideConfiguration(o -> o
            .retryStrategy(b -> b.maxAttempts(4))
        )
        .build();

The configurations above do not automatically set an API call timeout. Configure timeouts separately and avoid increasing attempts to mask throttling.

## 10. Configuring Timeouts with the Apache HTTP Client

    import java.time.Duration;
    import software.amazon.awssdk.core.retry.RetryMode;
    import software.amazon.awssdk.http.apache.ApacheHttpClient;
    import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

    DynamoDbClient client = DynamoDbClient.builder()
        .httpClientBuilder(
            ApacheHttpClient.builder()
                .connectionTimeout(Duration.ofMillis(500))
                .socketTimeout(Duration.ofMillis(1500))
                .connectionAcquisitionTimeout(Duration.ofMillis(500))
        )
        .overrideConfiguration(o -> o
            .retryStrategy(RetryMode.STANDARD)
            .apiCallAttemptTimeout(Duration.ofSeconds(2))
            .apiCallTimeout(Duration.ofSeconds(7))
        )
        .build();

These numbers are examples. Tune them based on p95/p99 latency, request size, Region, VPC, and service SLOs. The project must include the Apache HTTP client module matching the AWS SDK version; for async clients, configure Netty or CRT appropriately.

## 11. Smart Defaults and Per-Request Timeouts

Smart configuration defaults include STANDARD, IN_REGION, CROSS_REGION, MOBILE, AUTO, and LEGACY modes. They can select environment-appropriate HTTP transport defaults, but do not replace business-deadline API call timeouts and attempt timeouts.

Per-request override for a single operation:

    var response = s3.listBuckets(b -> b
        .overrideConfiguration(c -> c
            .apiCallTimeout(Duration.ofSeconds(5))
            .apiCallAttemptTimeout(Duration.ofSeconds(2))
        )
    );

Only the request passed this override uses these timeouts.

## 12. Idempotency and Unknown Outcomes

A timeout after sending a write does not prove the service did not execute the request. For example, DynamoDB may have committed while the response was lost on the way back. Retrying a counter increment, payment charge, or external side effect can execute the action twice.

Use idempotency tokens when supported by the service API. For custom business logic, use stable operation IDs, unique constraints/conditional writes, and persist outcomes in the same transaction. On retry, reuse the exact same token; never generate a fresh token per attempt.

## 13. SDK Retries vs. Application Retries

SDK retries handle errors at the AWS request layer. Application retries handle business workflows. If an API gateway retries twice, the application retries three times, and the SDK retries three times, the theoretical total requests can reach 18.

- Let the SDK handle default transport/service retries.
- Only retry business operations when they are idempotent.
- Enforce an overall end-to-end request deadline.
- Avoid stacked retries across gateway, controller, service, repository, and SDK.
- Offload long-running work to a queue/DLQ when HTTP deadlines are insufficient.

## 14. Observability

Record service/operation, Region, AWS request ID, HTTP status/error code, exception class, total latency, retry count, timeout layer, business operation ID, and trace ID. Never log credentials, PII, or sensitive request payloads.

Monitor API call latency, attempt timeouts, API call timeouts, retry rates, throttling rates, connection pool acquisition timeouts, HTTP errors, 5xx responses, and duplicate business operations. Alert when retries rise even while the final success rate stays high.

## 15. Testing and Runbook

Unit tests should verify attempt limits, delays, jitter, deadlines, non-retryable errors, and idempotency tokens. Integration tests should simulate throttling, 5xx responses, connection resets, read timeouts, TLS failures, and slow responses.

During an incident:
1. Identify the service, operation, Region, and resource.
2. Classify whether it is throttling, 5xx, network, pool acquisition, or timeout.
3. Check the retry mode, max attempts, and SDK version.
4. Inspect request IDs, CloudWatch metrics, retry rates, and HTTP pools.
5. Reduce concurrency if downstream is overloaded.
6. Reconcile writes with unknown outcomes using the idempotency key.
7. After recovery, confirm retry rates and latency return to baseline.

Never raise timeouts or max attempts to mask hot partitions, quota limits, pool exhaustion, or sustained throttling.

## 16. Summary

Timeouts bound waiting; retries handle transient failures; exponential backoff and jitter curb retry storms. Standard is the right choice for most workloads. Adaptive requires per-resource isolation; legacy exists for compatibility.

Max attempts includes the initial call. API call timeout spans attempts and backoff; attempt timeout bounds a single try. HTTP timeouts govern connection, TLS, read/write, and pool acquisition.

Retries do not replace idempotency. A timeout after a write can leave an unknown outcome requiring tokens, conditional writes, or reconciliation. Never let retries across gateway, application, and SDK multiply unchecked.

### Official AWS Documentation

1. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html
2. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html
3. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html
4. https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html
5. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/smart-configuration-defaults.html
6. https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/http-configuration.html
7. https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html
8. https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html
9. https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html
10. https://docs.aws.amazon.com/AmazonS3/latest/API/ErrorResponses.html
11. https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
12. https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html