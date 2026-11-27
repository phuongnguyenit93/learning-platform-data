# Black-Box Testing over HTTP or the Real Protocol of the Built Binary

After compiling Spring Boot into a GraalVM Native Image, you must test **the exact built binary over the protocol that external clients use**. For web services, that is typically HTTP/HTTPS; for other applications, it may be gRPC, WebSocket, or a custom TCP protocol. The test sends real requests, receives real responses, and verifies observable behavior from outside the process.

This is black-box testing: the test does not call Spring beans directly, does not start an `ApplicationContext` in the same JVM, and does not depend on internal application structure. It starts the executable or container image, waits for readiness, sends requests over a network socket, and verifies status codes, headers, payloads, errors, and business side effects.

For Spring Boot Native Image, this style of testing catches failures that JVM unit tests or `MockMvc` tests can miss: missing reflection/serialization hints, unpackaged resources, native-specific configuration differences from the JVM, JNI libraries failing to load, broken HTTP behavior, unreachable external dependencies, or binaries failing inside the runtime image.

## 1. How Does Black-Box Testing Differ from In-JVM Testing?

Different testing levels answer different questions:

| Testing Level | How It Executes | What Is Verified |
|---|---|---|
| Unit test | Calls methods/classes directly | Small logic units and business rules |
| Spring integration test | Starts ApplicationContext, possibly using a mock web environment | Wiring, configuration, beans, and framework integration |
| `MockMvc` / `WebTestClient` with mock server | Invokes the web layer inside the test context | Mapping, validation, and serialization at the web layer on the JVM |
| Native executable black-box test | Starts the binary and sends requests over HTTP/socket | Behavior of the native artifact in a real runtime |
| Container black-box test | Runs the final image and calls published ports | Binary, OS libraries, image filesystem, user, network, and protocol |

For example, `MockMvc` can prove a controller returns HTTP 201 for a valid request. However, it does not prove that the native executable can start up, load the JSON serializer, locate resources, open a socket, and return a response inside a container.

~~~mermaid
flowchart TD
    A["Build Spring Boot Native Image"] --> B["Package binary into final image"]
    B --> C["Start container or executable"]
    C --> D["Wait for readiness over real protocol"]
    D --> E["HTTP / gRPC / TCP client sends request"]
    E --> F["Verify status, headers, payload"]
    F --> G["Verify side effects and dependencies"]
    G --> H{"Real contract satisfied?"}
    H -->|Yes| I["Save test evidence"]
    H -->|No| J["Collect logs and diagnose native runtime"]
~~~

**The test must connect to the port that real clients will use.** Do not call controller methods, do not access beans directly, and do not swap out the server connector for a mock when the goal is verifying the built binary.

## 2. Define the External Contract Before Writing Tests

A good black-box test begins with the service contract. For each endpoint or operation, record:

- HTTP method or message/gRPC method type.
- Path, query parameters, and required headers.
- Request and response content types.
- Status codes for success and each error category.
- Authentication, authorization, and tenant rules, if applicable.
- Timeouts, retries, idempotency, and payload limits.
- Observable side effects such as created records, emitted events, or state transitions.

Example order creation contract:

| Case | Request | Expected Result |
|---|---|---|
| Valid order creation | `POST /api/orders`, valid JSON | `201 Created`, includes `Location` and JSON containing ID |
| Missing required field | `POST /api/orders`, missing `customerId` | `400 Bad Request` |
| Unauthenticated | No bearer token sent | `401 Unauthorized` |
| Insufficient permissions | Valid token lacking required role | `403 Forbidden` |
| Not found | `GET /api/orders/{id}` with nonexistent ID | `404 Not Found` |
| Repeated idempotent request | Same idempotency key | Does not create duplicate transaction per contract |

Do not just check that the server returns 200. Status codes, headers, and payloads are all part of the contract. If clients rely on `Location`, `ETag`, `Retry-After`, or `Content-Type`, tests must verify them.

## 3. Choose the Exact Artifact to Test

A key principle is to **test the exact artifact you intend to release**. If production runs a container image, test the final image. If production runs the executable directly on a VM, launch that executable on an equivalent host.

Do not build one binary for testing and rebuild a different binary for release without verifying equivalence. Two artifacts can differ in profiles, environment, native hints, resources, or dependencies.

Recommended workflow:

1. Build the native executable once for the target OS/architecture.
2. Package the binary into the final container image according to deployment configuration.
3. Tag or record an immutable digest for the image.
4. Run black-box tests against that exact image.
5. If tests pass, release the exact image digest that was tested.

With Gradle, the common native build task is:

~~~bash
./gradlew nativeCompile
~~~

With Maven, depending on Spring Boot and Native Build Tools configuration:

~~~bash
./mvnw -Pnative package
~~~

Tasks/goals depend on project plugins and profiles. Binary output paths also vary by artifact name and build configuration; use your project's actual output when building the image.

## 4. Running the Binary Directly on the Host

If production runs the executable directly, you can launch the binary from a shell:

~~~bash
SPRING_PROFILES_ACTIVE=blackbox \
SERVER_PORT=18080 \
./application
~~~

In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "blackbox"
$env:SERVER_PORT = "18080"
.\application.exe
~~~

Open another terminal and call the endpoint:

~~~bash
curl --fail --include http://127.0.0.1:18080/actuator/health
~~~

This tests the native executable on the current host. It does not test the final container image, container filesystem, non-root user, or network namespace. If production uses containers, run tests inside the container to cover those factors.

Ensure the process is terminated after tests and stdout/stderr logs are preserved when tests fail. Avoid sharing a single fixed port across concurrent CI jobs; configure per-job ports or use dynamic port mapping.

## 5. Running Inside the Final Container Image

With Docker, start the built image and publish the HTTP port:

~~~bash
docker run -d \
  --name orders-native-blackbox \
  --publish 127.0.0.1:18080:8080 \
  --env SPRING_PROFILES_ACTIVE=blackbox \
  orders-service:native-test
~~~

In this example:

- The application listens on port 8080 inside the container.
- The test host calls port 18080.
- The `blackbox` profile loads configuration meant for the test environment.
- The `orders-service:native-test` image must be the image containing the built native executable.

Inspect the process and logs:

~~~bash
docker ps --filter name=orders-native-blackbox
docker logs orders-native-blackbox
~~~

Call the endpoint from the host:

~~~bash
curl --fail --include http://127.0.0.1:18080/actuator/health
~~~

Do not test by running the binary inside a builder image and assuming the final image works. The builder may include libraries that the runtime image lacks.

## 6. Wait for Readiness Instead of Fixed Sleeps

Native images typically start quickly, yet actual startup time depends on CPU, filesystem, database migrations, and external dependencies. `sleep 2` does not prove the service is ready; it can be too short on slow runners and wasteful on fast runners.

Poll the readiness endpoint with a deadline:

~~~bash
set -euo pipefail

BASE_URL="http://127.0.0.1:18080"
READY_URL="$BASE_URL/actuator/health/readiness"
READY=false

for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error "$READY_URL" >/dev/null 2>&1; then
    READY=true
    break
  fi
  sleep 1
done

if [ "$READY" != "true" ]; then
  echo "Application did not become ready"
  docker logs orders-native-blackbox
  exit 1
fi
~~~

`/actuator/health/readiness` must be enabled and exposed in the test configuration. If the project does not use Actuator readiness groups, substitute the application's own readiness endpoint. The readiness endpoint should reflect conditions needed to accept traffic, such as databases or message brokers being ready.

Distinguish between:

- **Liveness:** the process is alive and does not need to be restarted.
- **Readiness:** the application can accept business requests.
- **Startup:** the application has completed initial startup.

An HTTP 200 from a liveness endpoint does not guarantee the database is ready. Choose the probe matching the test goal.

## 7. Writing HTTP Black-Box Tests with Java HttpClient

You can use JUnit running on the JVM to control a native container and send requests over HTTP. The test code runs on the JVM, while the server under test is the real native image.

Example using Testcontainers:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")
}
~~~

Versions should be managed by your project's compatible dependency management/BOM.

The test starts the image passed via the `NATIVE_TEST_IMAGE` environment variable:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class OrdersNativeBlackBoxTests {

    private static final String IMAGE =
        System.getenv().getOrDefault(
            "NATIVE_TEST_IMAGE",
            "orders-service:native-test"
        );

    @Container
    static final GenericContainer<?> application =
        new GenericContainer<>(DockerImageName.parse(IMAGE))
            .withExposedPorts(8080)
            .withEnv("SPRING_PROFILES_ACTIVE", "blackbox")
            .waitingFor(
                Wait.forHttp("/actuator/health/readiness")
                    .forStatusCode(200)
                    .withStartupTimeout(Duration.ofSeconds(90))
            );

    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    @Test
    void createsOrderThroughRealHttpEndpoint() throws Exception {
        int port = application.getMappedPort(8080);
        URI uri = URI.create(
            "http://localhost:" + port + "/api/orders"
        );

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .header("Content-Type", "application/json")
            .header("Accept", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(
                """
                {
                  "customerId": "C-100",
                  "sku": "SKU-01",
                  "quantity": 2
                }
                """
            ))
            .build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        assertThat(response.statusCode()).isEqualTo(201);
        assertThat(response.headers()
            .firstValue("content-type").orElse(""))
            .contains("application/json");
        assertThat(response.headers()
            .firstValue("location")).isPresent();
        assertThat(response.body()).contains("\"orderId\"");
    }
}
~~~

This example assumes the application exposes an Actuator readiness endpoint and the order creation API returns `201`, `Location`, and JSON containing `orderId`. Replace endpoints, payloads, and assertions with your actual contract. If the API returns `202 Accepted` or uses a different response schema, the test must reflect that contract.

The key point is that requests travel over a TCP socket to the mapped container port. The test does not call controllers or Spring beans inside the test JVM.

## 8. Verifying the Full Response Contract

Do not stop at the status code. A response test can verify:

~~~java
assertThat(response.statusCode()).isEqualTo(201);

assertThat(response.headers()
    .firstValue("content-type").orElse(""))
    .startsWith("application/json");

assertThat(response.headers()
    .firstValue("location"))
    .isPresent();

assertThat(response.body())
    .contains("\"orderId\"")
    .contains("\"status\":\"CREATED\"");
~~~

For stable JSON contracts, parse JSON using Jackson or a JSON assertion library instead of comparing raw strings. String comparison is brittle when field ordering or whitespace changes despite equivalent JSON content.

Fields to verify:

- Required fields are present and have the right types.
- Sensitive fields are not leaked externally.
- Null/omitted fields follow rules.
- Decimals, timestamps, and timezones match the expected format.
- `Content-Type`, charset, and content negotiation are correct.
- Headers such as `Location`, `ETag`, cache headers, or correlation IDs match contract requirements.

One advantage of HTTP black-box tests is that they also exercise response serialization in the native executable. If reflection hints for a DTO are missing, the error may only surface when an endpoint returns a less common data type.

## 9. Testing Validation and Error Responses

A production API must return structured, consistent errors. Send an invalid request:

~~~bash
curl --include \
  --header "Content-Type: application/json" \
  --data '{"customerId":"","quantity":0}' \
  http://127.0.0.1:18080/api/orders
~~~

Verify:

- Status is `400 Bad Request` per contract.
- Response includes an error code or `type/title/detail` if using Problem Details.
- No stack traces, filesystem paths, secrets, or SQL are exposed.
- Field-level validation errors are indicated clearly if supported by the API.
- Content type remains correct.
- Malformed JSON requests are handled cleanly.

A native image can differ from the JVM if serializers, validation metadata, or reflection access are missing. Test valid requests, missing fields, wrong types, out-of-range values, and syntactically invalid JSON payloads.

## 10. Testing Authentication and Authorization over HTTP

If endpoints require tokens, tests must send requests just like real clients:

~~~bash
curl --include \
  --header "Authorization: Bearer $TEST_ACCESS_TOKEN" \
  http://127.0.0.1:18080/api/orders
~~~

At minimum, cover these cases:

| Case | Result to Verify |
|---|---|
| No token sent | `401` |
| Invalid/expired token | `401` |
| Valid token lacking permission | `403` |
| Token with appropriate permission | Business response per contract |
| Token from another tenant | Cannot read/write data outside its tenant |

Use dedicated test-only credentials with short lifetimes and least privilege. If the application uses OAuth2/OIDC, run a test identity provider in a container or use a controllable test issuer. Never depend on production accounts in CI.

Black-box tests also confirm that security filters, JWT decoders, TLS, and key/certificate resources are present in the native runtime.

## 11. Testing State and Business Side Effects

A 201 response alone does not prove the transaction was persisted properly. Verify state via public APIs or test dependencies:

1. Send `POST /api/orders`.
2. Extract the ID from the response or `Location` header.
3. Send `GET /api/orders/{id}`.
4. Verify the business fields were persisted properly.
5. Send update/cancel operations if supported by the contract.
6. Verify state after the operation.

Example:

~~~bash
curl --fail \
  http://127.0.0.1:18080/api/orders/ORDER-100
~~~

If database verification is needed, query the test database after the request completes. However, API-level assertions should remain the primary proof of the external contract; database inspection is supplementary evidence for persistence/integration.

For message-driven services, the HTTP response may only acknowledge that an event was accepted. In that case, wait and verify the outcome via a consumer/API or test broker rather than assuming synchronous processing.

## 12. Running Real Dependencies in the Test Environment

A binary can return 200 on health yet fail when calling a database, Redis, broker, or another HTTP service. Run the required dependencies in an isolated test environment.

Options:

- Testcontainers for PostgreSQL, Redis, Kafka, RabbitMQ, or auxiliary services.
- WireMock/MockServer for external HTTP services.
- Docker Compose for multi-container integration environments.
- Separate database/schema per CI job.
- Dedicated Docker network and internal DNS aliases for containers.

With Testcontainers, the native application can receive the database URL via environment variables:

~~~java
.withEnv(
    "SPRING_DATASOURCE_URL",
    "jdbc:postgresql://orders-db:5432/orders"
)
.withEnv("SPRING_DATASOURCE_USERNAME", "test")
.withEnv("SPRING_DATASOURCE_PASSWORD", "test-only")
~~~

The name `orders-db` must be a network alias resolvable by the application container. Create a shared Docker network and attach both the database container and application container to it. The example above illustrates configuration only; never use test passwords outside test environments.

Test scenarios to check:

- The database is available before the application reports readiness.
- Migrations run successfully.
- The connection pool operates properly.
- Database restarts or dropped connections are handled per contract.
- The message broker sends/receives messages correctly.
- HTTP clients call the right downstream services with appropriate timeouts.

## 13. Testing Timeouts, Retries, and Idempotency

A black-box test can send requests with explicit deadlines:

~~~bash
curl --max-time 5 \
  --fail \
  http://127.0.0.1:18080/api/orders/ORDER-100
~~~

For retryable operations, tests should distinguish:

- Client retries due to timeouts.
- Server processed the request, but the response was lost.
- Server returns transient errors such as `503`.
- Request resent with the same idempotency key.
- Whether duplicate transactions are created.

Do not verify retries solely by checking that 200 is eventually returned. Verify how many times side effects occurred, the final state, and the response code in each scenario.

Timeout tests should enforce an overall time limit so CI cannot hang indefinitely. Document connection timeouts, request timeouts, and the full scenario deadline.

## 14. Testing HTTPS, TLS, and Proxies

If the binary terminates TLS itself, call endpoints over HTTPS with a test certificate and check the handshake, protocol version, hostname verification, and trust chain.

If TLS is terminated at an ingress/reverse proxy, two test layers may be needed:

- Call HTTP directly against the container to test the application contract.
- Call HTTPS through the proxy/ingress to test TLS, forwarded headers, redirects, cookies, and public URLs.

Some bugs only appear when the application receives `X-Forwarded-Proto`, `X-Forwarded-For`, or `Forwarded`. Verify generated links in responses, redirect URIs, and secure cookies under realistic proxy configuration.

Do not disable certificate verification in tests and conclude that TLS works. Use a trusted test CA in the test client and verify proper hostname matching.

## 15. Testing Non-HTTP Protocols

If a service does not expose a REST API, black-box tests still use a real client for that protocol:

| Protocol | How to Test | What to Verify |
|---|---|---|
| gRPC | Stub generated from `.proto`, called over an HTTP/2 channel | RPC status, metadata, deadlines, TLS, and Protobuf serialization |
| WebSocket | Client performs HTTP Upgrade handshake and sends frames | Handshake, subprotocol, messages, ping/pong, and close codes |
| Custom TCP | `Socket`/real protocol client sending byte frames | Framing, encoding, timeouts, connection lifecycle, and errors |
| AMQP | AMQP client connecting to a test broker | Publish/consume, routing keys, ack/nack, and redelivery |
| MQTT | MQTT client connecting to a test broker | Connect, subscribe, QoS, retained messages, and reconnect |

A gRPC test example uses the generated stub and a channel pointing to the native container's exposed port:

~~~java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("localhost", mappedPort)
    .usePlaintext()
    .build();

try {
    OrdersGrpc.OrdersBlockingStub stub =
        OrdersGrpc.newBlockingStub(channel)
            .withDeadlineAfter(5, TimeUnit.SECONDS);

    OrderReply reply = stub.createOrder(
        CreateOrderRequest.newBuilder()
            .setCustomerId("C-100")
            .setSku("SKU-01")
            .setQuantity(2)
            .build()
    );

    assertThat(reply.getOrderId()).isNotBlank();
}
finally {
    channel.shutdownNow();
}
~~~

This is a plaintext gRPC example for an internal test network. In TLS-enabled environments, configure the channel with a test certificate and verify hostnames. Do not send ordinary HTTP/1.1 requests to an HTTP/2-only gRPC port and mistake that error for a native bug.

## 16. Testing Concurrency and Load Limits

A native image may alter startup time and memory footprint, yet behavior under concurrent client traffic still needs verification.

You can use k6, Gatling, or JMeter to:

- Send concurrent requests to critical endpoints.
- Confirm no data is lost or duplicated.
- Inspect latency percentiles and error rates.
- Observe memory, CPU, threads, and connection pools.
- Check payload limits, rate limits, and backpressure.
- Verify the server continues serving requests after traffic bursts.

This is protocol-level load testing; keep it separate from functional smoke tests so results stay clear. Do not pick arbitrary latency thresholds. Use the service's SLO or baseline and run on known infrastructure specifications.

## 17. Collecting Logs and Diagnosing Failed Black-Box Tests

When tests fail, preserve enough evidence to pinpoint whether the failure occurred at startup, networking, native runtime, or contract level.

Details to retain:

- Image tag and digest.
- OS, architecture, and runtime image.
- Test environment/profiles used, with secrets scrubbed.
- Container exit code and startup duration.
- stdout/stderr or `docker logs`.
- Request method, path, status, response headers, and sanitized body.
- Correlation ID/trace ID.
- Logs of dependency containers such as databases or brokers.

Common symptoms:

| Symptom | Investigation Direction |
|---|---|
| Container exits immediately on start | Read startup logs, dynamic libraries, native initialization, and config |
| Health endpoint fails | Check readiness, migrations, dependencies, and port binding |
| Connection refused | Check port mapping, server bind address, and process state |
| HTTP 404 | Check context path, routes, and active profiles |
| HTTP 415 | Check `Content-Type` |
| HTTP 406 | Check `Accept` and content negotiation |
| HTTP 401/403 | Check tokens, roles, issuer, and security configuration |
| HTTP 500 only in native | Check reflection/serialization hints, resources, and stack trace |
| JSON response missing fields | Check serializers, DTO metadata, and inclusion settings |
| Timeout calling downstream | Check DNS, networking, TLS, connection pools, and timeouts |
| Fails only inside container | Check environment, filesystem, user, certificates, and native libraries |

Whenever possible, capture logs even when the test container stops. In CI, use `finally` or cleanup hooks to collect logs before removing containers.

## 18. Cleaning Up Test Resources

Tests must stop containers and close connections whether assertions pass or fail.

In shell scripts:

~~~bash
cleanup() {
  docker logs orders-native-blackbox || true
  docker rm -f orders-native-blackbox >/dev/null 2>&1 || true
}
trap cleanup EXIT
~~~

With Testcontainers, the `@Container` annotation and JUnit extension manage the container lifecycle. For gRPC, WebSocket, or raw TCP clients, close channels/sockets in `finally` or try-with-resources.

Avoid fixed container names when multiple jobs run concurrently. Use unique names per CI run or let Testcontainers manage container names. Tests should be independent and repeatable without leaving behind databases, ports, or temp files that affect subsequent runs.

## 19. Organizing Black-Box Tests in CI

A typical pipeline:

~~~mermaid
flowchart TD
    A["Compile and JVM tests"] --> B["Spring AOT processing"]
    B --> C["Build Native Image"]
    C --> D["Build final container image"]
    D --> E["Record image digest"]
    E --> F["Start native image"]
    F --> G["Wait for readiness"]
    G --> H["HTTP/protocol contract tests"]
    H --> I["Integration tests with dependencies"]
    I --> J["Save logs and test reports"]
    J --> K{"All passed?"}
    K -->|Yes| L["Publish exact image digest"]
    K -->|No| M["Retain artifact and diagnose"]
~~~

Example pipeline commands:

~~~bash
# Build native executable
./gradlew nativeCompile

# Package final image containing the newly built binary
docker build -f Dockerfile.native \
  -t orders-service:native-test .

# Run black-box tests against this exact image
NATIVE_TEST_IMAGE=orders-service:native-test \
  ./gradlew test
~~~

In real projects, separate black-box source sets/tasks from JVM unit tests so they can run independently against the target image. Ensure the Docker image build completes before tests start; never let tests accidentally pull an older cached tag on the runner.

When releasing multi-architecture images, run tests on runners matching each OS/architecture. A single image tag can point to a multi-platform manifest; verify each target platform directly rather than testing one architecture and assuming all others work.

## 20. Distinguishing Binary Tests from Full Deployment Tests

Black-box tests directly targeting the binary verify the contract exposed by the process. They do not automatically verify every production deployment component:

| Scope | Where to Test |
|---|---|
| HTTP handlers, JSON, validation, in-app security | Call the native binary/container directly |
| JNI and shared libraries | Run the binary inside the target runtime image |
| Database, broker, downstream APIs | Run alongside test dependencies or sandbox services |
| TLS termination, ingress, routing | Call through the reverse proxy/ingress |
| DNS, service discovery, network policies | Test in a deployment-equivalent network/platform |
| Secret/config injection | Run using production-like config mechanisms with test values |
| Rolling updates, readiness, shutdown | Test at the orchestrator/deployment layer |

Scope tests by risk and contract. You do not need to deploy the entire production stack for every unit test, but before release run at least one integration pass in an environment close to real deployment.

## 21. Black-Box Test Acceptance Checklist

Before marking a native artifact as passing, verify:

- [ ] Tests ran against the exact built binary/image intended for release.
- [ ] OS, architecture, and runtime image match the target.
- [ ] Process starts and reaches readiness within the deadline.
- [ ] Client sends requests over HTTP or the real protocol.
- [ ] Status codes, headers, content types, and payloads satisfy the contract.
- [ ] Valid requests, invalid inputs, and error responses were tested.
- [ ] Authentication/authorization were tested where applicable.
- [ ] Critical serialization, resource, and JNI paths executed for real.
- [ ] Databases, brokers, and downstream dependencies were tested as needed.
- [ ] Timeouts, retries, and idempotency were verified per contract.
- [ ] Logs and artifact digests are preserved when tests fail.
- [ ] Test containers/processes, ports, and networks are cleaned up.

## 22. Key Takeaways

Black-box testing over HTTP or the real protocol verifies the **observable behavior of the built binary**. Tests must launch the actual executable or final container image, wait for readiness, send requests over real sockets, and assert responses alongside business side effects.

`MockMvc` and unit tests remain valuable for business logic and the web layer, yet they do not replace testing the native runtime. With Spring Boot Native Image, black-box tests are especially critical for uncovering missing hints, broken serializers/resources, unloaded JNI libraries, misconfigurations, and unavailable dependencies.

In CI, build the artifact once, test that exact artifact, save the image digest and logs, and promote the exact digest that passed contract and integration tests. If the application uses gRPC, WebSocket, AMQP, or custom TCP, use a real client for that protocol to verify behavior from the consumer's perspective.

### References

- Spring Boot — Testing: https://docs.spring.io/spring-boot/reference/testing/
- Spring Boot — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Container Images: https://docs.spring.io/spring-boot/reference/packaging/container-images/
- Testcontainers for Java — JUnit 5 Quickstart: https://java.testcontainers.org/quickstart/junit_5_quickstart/
- Testcontainers for Java — Wait Strategies: https://java.testcontainers.org/features/startup_and_waits/
- Java — java.net.http.HttpClient: https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html

APIs, build tasks, and Actuator configurations depend on Spring Boot, GraalVM, JDK, and Testcontainers versions. Follow dependency management and documentation matching the exact versions pinned by your project.
