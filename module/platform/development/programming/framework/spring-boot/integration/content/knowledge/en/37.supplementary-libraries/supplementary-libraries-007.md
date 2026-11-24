# gRPC, Protobuf, and Components Requiring Configuration Outside Spring Boot

In Spring Boot integration systems, REST/JSON fits many public HTTP APIs; JMS or message brokers support asynchronous work handoff; and **gRPC** is an option for services calling one another over strongly typed contracts, typically using **Protocol Buffers (protobuf)** for data representation and **HTTP/2** as the transport protocol. gRPC is especially useful for high-frequency internal RPCs, generated client/server stubs, compact payloads, and streaming. However, a completed RPC does not equal a message durably stored in a broker.

This lesson belongs to the **Supplementary Libraries** chapter of the **SPRING_BOOT_INTEGRATION** module, which examines integrating HTTP clients, databases, caches, message brokers, and Spring Integration adapters. The focus here is data contracts, configuration, transactions, errors, duplicate handling, testing, and observability in gRPC flows. We will distinguish what **gRPC Java/protobuf** provides from what **the Spring Boot application or infrastructure must configure itself**. Adding the grpc-java library to the classpath does not automatically guarantee that the application has opened a gRPC port, registered services, created client channels, configured TLS, or defined deadlines. Integration starters can automate parts of this, but specific capabilities depend on the chosen version and library.

## 1. How Does gRPC Fit into the Integration Picture?

Suppose `checkout-service` needs to check inventory before creating an order. A synchronous processing flow might look like:

~~~mermaid
sequenceDiagram
    participant C as checkout-service
    participant I as inventory-service (gRPC)
    participant D as Inventory database
    C->>I: CheckAvailability(request) - HTTP/2
    I->>D: Read inventory
    D-->>I: Stock snapshot
    I-->>C: CheckAvailabilityResponse
~~~

gRPC forwards a method call from client to server and returns a response or an error status. This creates a real-time dependency: when the server is slow or unavailable, the caller must have deadlines and an error-handling policy. To recover work when a processing service is offline for hours, you need a queue/broker or an event store with proper persistence.

| Component | Primary Function | What It Does Not Solve Automatically |
| --- | --- | --- |
| **Protobuf** | Declares schemas, field numbers, data types, and binary encoding | Business validation, auth, transactions |
| **gRPC Java** | RPC stubs, HTTP/2 transport, statuses, metadata, deadlines, streaming | Complete Spring Boot lifecycle and policy integration |
| **Spring Boot** | Beans, dependency injection, configuration, services/transactions, app lifecycle | Generating protobuf or implicitly creating every gRPC endpoint from the grpc-java dependency alone |
| **Broker/JMS** | Delivers messages by queue/topic and broker policies | Fully replacing synchronous RPC |
| **Infrastructure** | DNS, LB, ingress, TLS, certificates, network policies, health, and observability | Knowing schema compatibility between two services |

### Four Types of RPC

| Type | Service Method Form in Proto | Examples |
| --- | --- | --- |
| Unary | `rpc Check(A) returns (B);` | Checking inventory, fetching prices |
| Server streaming | `rpc Watch(A) returns (stream B);` | Streaming status updates over a connection |
| Client streaming | `rpc Upload(stream A) returns (B);` | Uploading multiple data chunks |
| Bidirectional streaming | `rpc Exchange(stream A) returns (stream B);` | Two-way data exchange session |

Streaming is a transmission stream over a connection with flow control. It does not by default store history, track offsets, or replay messages after a consumer goes offline. Resume/replay requirements must be designed with explicit state and storage.

## 2. Designing a Protobuf Contract: From `.proto` File to Java Stubs

Create `src/main/proto/inventory/v1/inventory.proto`:

~~~proto
syntax = "proto3";

package integration.inventory.v1;

option java_multiple_files = true;
option java_package = "com.example.integration.inventory.v1";
option java_outer_classname = "InventoryContractProto";

service InventoryService {
  rpc CheckAvailability(CheckAvailabilityRequest)
      returns (CheckAvailabilityResponse);
}

message CheckAvailabilityRequest {
  string sku = 1;
  int32 requested_quantity = 2;
  string request_id = 3;
}

message CheckAvailabilityResponse {
  bool available = 1;
  int64 stock_version = 2;
  string warehouse_id = 3;
}
~~~

At build time, `protoc` generates Java message classes, while the `protoc-gen-grpc-java` plugin generates service/stub code. With `java_multiple_files = true`, Java code includes classes such as `CheckAvailabilityRequest`, `CheckAvailabilityResponse`, and `InventoryServiceGrpc`. Clients use `InventoryServiceGrpc.newBlockingStub(channel)` or asynchronous stub variants; servers extend `InventoryServiceGrpc.InventoryServiceImplBase`.

In protobuf, **field numbers are wire identities**, not display order. `string sku = 1` and `int32 requested_quantity = 2` cannot have their field numbers changed arbitrarily once a contract is published. `java_package` controls the Java package; `package` controls the protobuf namespace and forms part of the full RPC method name on the wire. Changing `package`, service name, or method name can break clients even if the payload remains compatible.

### Defaults, Presence, and Validation

In `proto3`, a scalar string defaults to empty, numbers to 0, and booleans to false. For scalar fields without presence tracking, the server cannot easily distinguish "client omitted the field" from "client sent the default value". When this distinction matters, use `optional` or `oneof`:

~~~proto
message UpdateInventoryRequest {
  string sku = 1;

  optional int32 target_quantity = 2;

  oneof adjustment {
    int32 increase_by = 3;
    int32 decrease_by = 4;
  }
}
~~~

Generated code can provide `hasTargetQuantity()` for `optional` fields. `oneof` expresses mutually exclusive choices, though the server must still check for neither branch set, negative numbers, or invalid SKUs. Protobuf only validates wire structure/types; business rules stay in the application service.

For monetary data, avoid `float` and `double` when precision is required: use `int64` in minor units paired with currency code, or an explicitly defined decimal schema. For timestamps, use `google.protobuf.Timestamp` or a clearly agreed time format. For enums, define value 0 as `UNSPECIFIED` so a default unset value is never interpreted as a valid business state.

### Schema Compatibility Over Time

| Change | Assessment | Action Needed |
| --- | --- | --- |
| Adding a new field with an unused number | Usually wire-compatible | Handle default values and old consumers |
| Renaming a field while keeping number/type | Potentially wire-compatible | Check generated code, JSON mappings, and API docs |
| Removing an old field | Potentially wire-compatible | Use `reserved` so numbers/names are not reused |
| Changing a field number | Breaking | Create a new field or version the API |
| Changing field type or meaning | Risk of breaking | Check both wire types and semantics |
| Renaming service/RPC/protobuf package | Breaking for RPC routing | Version method/service and update clients |
| Adding a new RPC | Usually keeps old RPCs working | Only invoke once the server supports it |

Example when retiring previously published fields:

~~~proto
message StockSnapshot {
  string sku = 1;
  reserved 2, 5;
  reserved "legacy_location";
  int64 version = 3;
}
~~~

Never reuse tags 2 and 5 with a different meaning. Store `.proto` files in version control or a centrally managed contract artifact, generate code in CI, and check compatibility when multiple services cannot upgrade simultaneously. "Protobuf compatibility" is only half the story: if an older consumer does not understand a new enum value or new business requirement, the contract can still be behaviorally incompatible.

## 3. Dependencies and Code-Generation Steps You Must Configure

Using plain grpc-java, common artifacts include:

| Artifact | Role |
| --- | --- |
| `io.grpc:grpc-protobuf` | Integrates protobuf marshallers for RPCs |
| `io.grpc:grpc-stub` | Client stubs, `StreamObserver`, and support APIs |
| `io.grpc:grpc-netty-shaded` | HTTP/2 Netty transport with shaded dependencies |
| `io.grpc:grpc-services` | Supporting services such as gRPC health/reflection if used |
| `io.grpc:grpc-inprocess` | In-process server/channel for unit/integration tests |
| `com.google.protobuf:protobuf-java` | Protobuf runtime; must match the `protoc` version used |
| `protoc` + `protoc-gen-grpc-java` | Generates Java messages and Java gRPC code during build |

Partial `pom.xml` example using the gRPC BOM:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>io.grpc</groupId>
      <artifactId>grpc-bom</artifactId>
      <version>${grpc.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>io.grpc</groupId>
    <artifactId>grpc-protobuf</artifactId>
  </dependency>
  <dependency>
    <groupId>io.grpc</groupId>
    <artifactId>grpc-stub</artifactId>
  </dependency>
  <dependency>
    <groupId>io.grpc</groupId>
    <artifactId>grpc-netty-shaded</artifactId>
  </dependency>
</dependencies>
~~~

`grpc.version` must be chosen and managed consistently by the project; the BOM aligns gRPC artifacts but does not replace aligning `protobuf-java`, `protoc`, and the generator. If missing-class or wrong-method errors appear between runtime and generated code, check the dependency tree and version alignment before editing business code.

With Maven, one way to generate Java sources is `protobuf-maven-plugin` together with `os-maven-plugin`:

~~~xml
<build>
  <extensions>
    <extension>
      <groupId>kr.motd.maven</groupId>
      <artifactId>os-maven-plugin</artifactId>
      <version>${os.maven.plugin.version}</version>
    </extension>
  </extensions>

  <plugins>
    <plugin>
      <groupId>org.xolstice.maven.plugins</groupId>
      <artifactId>protobuf-maven-plugin</artifactId>
      <version>${protobuf.maven.plugin.version}</version>
      <configuration>
        <protocArtifact>
          com.google.protobuf:protoc:${protobuf.version}:exe:${os.detected.classifier}
        </protocArtifact>
        <pluginId>grpc-java</pluginId>
        <pluginArtifact>
          io.grpc:protoc-gen-grpc-java:${grpc.version}:exe:${os.detected.classifier}
        </pluginArtifact>
      </configuration>
      <executions>
        <execution>
          <goals>
            <goal>compile</goal>
            <goal>compile-custom</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

This is a **configuration skeleton**; you must declare `grpc.version`, `protobuf.version`, `os.maven.plugin.version`, and `protobuf.maven.plugin.version` properties matching your project. Never pick arbitrary versions at random, as the generator, runtime, and JDK must all be compatible. With Gradle, the `com.google.protobuf` plugin serves the same role. CI must run code generation, compilation, and contract tests before publishing artifacts.

Some `protoc`/JDK combinations emit `@javax.annotation.Generated`, while modern JDKs do not bundle that annotation API; in that case you need the annotation dependency in compile scope or a compatible generator configuration. This is a **generated-code** annotation concern, independent of Spring Boot's `jakarta.*` namespace transition.

### Spring gRPC Integration Starters Are Another Option

Annotations such as `@GrpcService` and `@GrpcClient` normally belong to a specific **integration starter**, not core grpc-java. Selecting a starter requires verifying its supported Spring Boot/JDK versions, server/channel auto-configuration, TLS, interception, metrics, health, shutdown, and testing. Never both start a server via a starter and manually open another server on the same port via `NettyServerBuilder`; establish a single management mechanism.

The following examples use **grpc-java + manual Spring beans** to illustrate every component developers must configure.

## 4. Implementing a gRPC Server in a Spring Boot Application

An endpoint receives a protobuf request, validates inputs, calls a Spring service, and returns a response or error status. For a transactional Spring service, place SQL logic in the container-managed service layer; the gRPC endpoint handles only conversion and error mapping.

### 4.1. Java Endpoint

~~~java
package com.example.integration.inventory;

import com.example.integration.inventory.v1.CheckAvailabilityRequest;
import com.example.integration.inventory.v1.CheckAvailabilityResponse;
import com.example.integration.inventory.v1.InventoryServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

@Component
public class InventoryGrpcEndpoint
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    private final InventoryApplicationService inventory;

    public InventoryGrpcEndpoint(InventoryApplicationService inventory) {
        this.inventory = inventory;
    }

    @Override
    public void checkAvailability(
            CheckAvailabilityRequest request,
            StreamObserver<CheckAvailabilityResponse> observer) {

        if (request.getSku().isBlank()
                || request.getRequestedQuantity() <= 0) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("sku and quantity must be valid")
                    .asRuntimeException());
            return;
        }

        try {
            var snapshot = inventory.check(
                    request.getSku(), request.getRequestedQuantity());

            var response = CheckAvailabilityResponse.newBuilder()
                    .setAvailable(snapshot.available())
                    .setStockVersion(snapshot.stockVersion())
                    .setWarehouseId(snapshot.warehouseId())
                    .build();

            observer.onNext(response);
            observer.onCompleted();
        } catch (InventoryNotFoundException ex) {
            observer.onError(Status.NOT_FOUND
                    .withDescription("SKU not found")
                    .asRuntimeException());
        } catch (Exception ex) {
            observer.onError(Status.INTERNAL
                    .withDescription("Unable to check inventory")
                    .asRuntimeException());
        }
    }
}
~~~

In this example, `InventoryApplicationService` and `InventoryNotFoundException` are project-defined business types. A simple contract for this service is:

~~~java
public interface InventoryApplicationService {
    InventorySnapshot check(String sku, int requestedQuantity);
}

public record InventorySnapshot(
        boolean available, long stockVersion, String warehouseId) {
}
~~~

The implementation can use JPA/JDBC and `@Transactional(readOnly = true)`. When relying on Spring transaction proxies, the gRPC endpoint must call through the Spring-managed service bean so advice runs properly. Never expect gRPC to create transactions on its own.

For unary RPCs, the success path is **`onNext(response)` followed by `onCompleted()`**; the error path is **`onError(exception)`**, terminating the call. Never call both success and error for the same request. Never expose stack traces or secret data in status descriptions. Use a trace ID to correlate internal error logs.

### 4.2. Ports and Lifecycle

A web application might serve REST on `server.port: 8080` while a separate Netty gRPC server listens on `9090`. Configuring Spring Boot's `server.port` does not automatically open a gRPC port.

~~~yaml
server:
  port: 8080

app:
  grpc:
    server:
      port: 9090
~~~

Configuring the server as Spring beans:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcServerConfiguration {

    @Bean
    Server grpcServer(
            InventoryGrpcEndpoint endpoint,
            @Value("${app.grpc.server.port:9090}") int port) {
        return NettyServerBuilder.forPort(port)
                .addService(endpoint)
                .build();
    }

    @Bean
    SmartLifecycle grpcServerLifecycle(Server grpcServer) {
        return new SmartLifecycle() {
            private volatile boolean running;

            @Override
            public void start() {
                try {
                    grpcServer.start();
                    running = true;
                } catch (IOException ex) {
                    throw new IllegalStateException(
                            "Unable to open gRPC port", ex);
                }
            }

            @Override
            public void stop() {
                grpcServer.shutdown();
                try {
                    if (!grpcServer.awaitTermination(
                            10, TimeUnit.SECONDS)) {
                        grpcServer.shutdownNow();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    grpcServer.shutdownNow();
                } finally {
                    running = false;
                }
            }

            @Override
            public boolean isRunning() {
                return running;
            }
        };
    }
}
~~~

Calling `build()` on a server does not `start()` it. `SmartLifecycle` ties starting and stopping the server to Spring, managing resources during shutdown. For graceful draining in production, flip readiness before stopping new requests and give in-flight RPCs a bounded grace window. Containers/ingress must expose and route port 9090; do not declare only HTTP port 8080 and expect gRPC to appear.

This minimal example does not yet enable TLS, interceptors, or health; those components are covered in the sections below.

## 5. Client Configuration: ManagedChannel, Stubs, and Deadlines

`ManagedChannel` is a resource meant to be reused across requests; never create a new channel per RPC call. Protobuf stubs are lightweight wrappers built over a channel that can attach per-call deadlines, metadata, or call options.

~~~yaml
app:
  grpc:
    inventory:
      host: inventory.internal
      port: 9090
      tls-enabled: true
~~~

~~~java
import com.example.integration.inventory.v1.InventoryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel inventoryChannel(
            @Value("${app.grpc.inventory.host}") String host,
            @Value("${app.grpc.inventory.port}") int port,
            @Value("${app.grpc.inventory.tls-enabled:true}") boolean tls) {

        ManagedChannelBuilder<?> builder =
                ManagedChannelBuilder.forAddress(host, port);

        if (tls) {
            builder.useTransportSecurity();
        } else {
            builder.usePlaintext(); // Use only when the network model permits.
        }
        return builder.build();
    }

    @Bean
    InventoryServiceGrpc.InventoryServiceBlockingStub inventoryStub(
            ManagedChannel inventoryChannel) {
        return InventoryServiceGrpc.newBlockingStub(inventoryChannel);
    }
}
~~~

When multiple similar channels exist, use bean names, `@Qualifier`, or a factory to avoid wrong injections. `shutdown()` initiates channel termination; if the application needs to wait for in-flight RPCs to finish, manage `awaitTermination` with bounded application lifecycle hooks.

Unary call example:

~~~java
import com.example.integration.inventory.v1.CheckAvailabilityRequest;
import com.example.integration.inventory.v1.InventoryServiceGrpc;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    public InventoryGateway(
            InventoryServiceGrpc.InventoryServiceBlockingStub stub) {
        this.stub = stub;
    }

    public boolean isAvailable(String sku, int quantity, String requestId) {
        var request = CheckAvailabilityRequest.newBuilder()
                .setSku(sku)
                .setRequestedQuantity(quantity)
                .setRequestId(requestId)
                .build();

        try {
            var response = stub.withDeadlineAfter(
                    700, TimeUnit.MILLISECONDS)
                    .checkAvailability(request);
            return response.getAvailable();
        } catch (StatusRuntimeException ex) {
            if (ex.getStatus().getCode() == Status.Code.NOT_FOUND) {
                throw new IllegalArgumentException(
                        "SKU does not exist", ex);
            }
            // Do not treat UNAVAILABLE or DEADLINE_EXCEEDED as out of stock.
            throw ex;
        }
    }
}
~~~

A deadline is a **time budget for an RPC**. Do not give every consecutive downstream call the entire upstream API SLA. If checkout has 1,500 ms to respond and must call inventory, shipping, and payment, budget each step, leave time for local work, and return a response.

`BlockingStub` is easy to read, but holds a thread waiting on I/O; if the app uses WebFlux or needs high concurrency, consider async/future stubs with an appropriate executor and avoid blocking the event loop.

## 6. gRPC Components That Must Be Configured Outside Boot

| Component | Typical Owner | Consequence If Omitted |
| --- | --- | --- |
| Protoc/generator and code build | Maven/Gradle, CI | Missing stubs, runtime/generated-code drift |
| Server port, bind, lifecycle | Starter or Spring beans | Server fails to listen or port conflicts |
| Service registration | Server bootstrap | `UNIMPLEMENTED` because service isn't registered |
| ManagedChannel/stub/shutdown | Client integration layer | Connection leaks, excessive channel creation |
| DNS, service discovery, and LB | Platform plus client | Traffic hits only one endpoint or drops when scaling |
| TLS/mTLS, CA, rotation | Security, platform, service | Cleartext exposure or handshake failures |
| AuthN/AuthZ | Interceptors and policies | Weak authentication, unauthorized RPC calls |
| Deadlines, retries/backoff | Caller | Hanging requests, retry storms, duplicate writes |
| Health/readiness and graceful shutdown | Service/platform | Traffic sent to unready pods |
| Metrics, tracing, logs | Observability stack | Blind to RPC timeouts and latency |
| HTTP/2, ingress, and gateway | Network/ingress/mesh | Proxy fails to pass gRPC or cuts streaming |
| Schema compatibility | Contract repository, CI | Client/server disagree on contract |

### gRPC Ports and HTTP/2

A Netty-based gRPC Java server usually opens a dedicated port. Configure container ports, Kubernetes Services/Ingress, proxies, TLS/ALPN, or HTTP/2 cleartext (h2c) per your architecture. Long-lived HTTP/2 connections load-balance differently from many short HTTP/1.1 requests. DNS returning multiple IPs does not guarantee individual RPCs distribute evenly across pods; test actual resolvers and load balancing.

### Browsers and gRPC-Web

Browsers cannot generally invoke binary gRPC the same way a Java client does. When frontends need to call services, teams typically use gRPC-Web with a compatible proxy or expose a REST/JSON gateway. Gateways must be checked for request/response trailer support, max message sizes, streaming, idle timeouts, and error mapping; never assume any HTTP/1.1 reverse proxy passes gRPC intact.

### TLS and mTLS

`useTransportSecurity()` on a channel requires TLS and verifies the server against the configured trust store. `NettyServerBuilder.forPort()` in the earlier example did not enable TLS; a TLS client cannot complete a handshake against such a plaintext server. Illustrative server-side TLS setup:

~~~java
var server = NettyServerBuilder.forPort(port)
        .useTransportSecurity(certChainFile, privateKeyFile)
        .addService(endpoint)
        .build();
~~~

`certChainFile` and `privateKeyFile` here are `java.io.File` instances obtained from secrets or config files. In production, manage CAs, hostnames/SANs, rotation, certificate file permissions, and trust stores. **mTLS** additionally configures client certificates/trust so the server verifies the caller's certificate, often via Netty's SSL context or a clearly bounded mesh. TLS authenticates the channel; **authorization** must still verify principals/permissions per method. Never trust a client-supplied `userId` payload field as a verified identity.

Server-side interceptors typically authenticate bearer tokens or client identities, populate claims in `io.grpc.Context`, propagate correlation/trace IDs, and enforce resource limits. Metadata such as `Authorization` must be protected; never log tokens, passwords, keys, or sensitive payloads. Return `UNAUTHENTICATED` when credentials are missing/invalid, and `PERMISSION_DENIED` when authenticated but lacking permission.

## 7. Errors, Deadlines, Retries, and Once-Only Business Effects

gRPC separates standard status codes from protobuf response fields. Client designs must distinguish them:

| Status | When It Occurs | Suggested Action |
| --- | --- | --- |
| `OK` | RPC completed normally | Inspect business response fields |
| `INVALID_ARGUMENT` | Invalid SKU/quantity | Fix input; do not retry blindly |
| `NOT_FOUND` | SKU does not exist | Handle differently from `available=false` |
| `FAILED_PRECONDITION` | Current state prohibits operation | Read/update business state |
| `ALREADY_EXISTS` | Resource already exists | Check conflicts and idempotency |
| `UNAUTHENTICATED` | Missing or invalid credentials | Handle authentication |
| `PERMISSION_DENIED` | Client lacks authorization | Handle permissions |
| `RESOURCE_EXHAUSTED` | Quota/capacity exhausted | Backoff, limit concurrency |
| `UNAVAILABLE` | Connection or service unavailable | Controlled retry if operation is safe |
| `DEADLINE_EXCEEDED` | Wait budget expired | Outcome may be unknown; check idempotency |
| `INTERNAL` | Unexpected server failure | Record trace, investigate; hide sensitive details |

### Deadline Exceeded Does Not Mean the Server Rolled Back

Suppose a client calls `ReserveStock`, the server commits SQL, and the response is lost as the deadline expires. The client sees `DEADLINE_EXCEEDED` even though stock **was already deducted**. If the client retries with a fresh creation request lacking an idempotency key, stock may be deducted a second time. Retrying on status codes alone is insufficient; business semantics matter too.

Design pattern for write RPCs:

1. Client generates a stable `requestId` for an operation and reuses the same ID across retries.
2. Server persists `(callerIdentity, requestId)` in an idempotency table with a unique constraint inside the same transaction updating business data.
3. Already-completed requests return the recorded outcome; in-progress requests return a consistent contract state.
4. Bound retries with backoff/jitter inside the overall deadline; log outcomes and idempotency keys.

If a business operation commits to a database and emits a JMS/Kafka event, gRPC does not make those two steps atomic. Use mechanisms like a **transactional outbox** or an explicitly designed and tested distributed coordination architecture. A successful RPC does not prove downstream broker messages were persisted.

### Cancellation and Retry Storms

When a caller cancels an RPC, the server may receive a cancellation signal, but cancellation does not undo side effects already performed. Long-running work should poll cancellation and stop unnecessary processing when safe. Retries must stay within a budget; many upstreams retrying simultaneously against an overloaded service can bring it down faster. Cap attempt counts, send rates, and concurrent RPCs, adding circuit breakers/bulkheads where appropriate.

## 8. Streaming, Backpressure, and Resumption

gRPC streaming lets servers and clients exchange multiple messages over one RPC. However, it requires managing:

- Stream lifetimes, reconnects, and idle timeouts across proxies/meshes.
- Flow control and backpressure when the sender outpaces the receiver; `ServerCallStreamObserver` exposes APIs to observe readiness and cancellation.
- Executors, thread safety, and context propagation under asynchronous handling.
- Message size limits, buffering, max concurrent streams, and keepalives.
- Ordering, duplicates, and resume tokens when receivers cannot afford missed items.

Example streaming contract:

~~~proto
service InventoryUpdates {
  rpc WatchStock(WatchStockRequest) returns (stream StockChange);
}

message WatchStockRequest {
  string sku = 1;
  int64 after_version = 2;
}

message StockChange {
  string sku = 1;
  int64 version = 2;
  int32 available_quantity = 3;
}
~~~

`after_version` only works if the server **actually** maintains a change table, outbox, or event log capable of querying from a version and handling gaps/retention. A proto field does not automatically create replay capability. If you must retain millions of events or read history by offset, a durable event broker/log usually fits better than treating a gRPC stream as the sole source of truth.

## 9. Health, Tracing, Metrics, and Operations

Spring Boot Actuator exposes application/JVM health on the web port, yet HTTP health on `8080` does not prove the gRPC server on `9090` started and registered its services. You can implement the **gRPC Health Checking Protocol** (`grpc.health.v1.Health`) via grpc-java's supporting services. Readiness should reflect whether the gRPC server is ready for RPCs and critical dependencies; during shutdown, stop routing new traffic before terminating in-flight calls.

**Server reflection** lets tools like `grpcurl` inspect descriptors without carrying `.proto` files. Enable it only on permitted networks/environments; reflection exposes the service/method catalog. When disabled, tests can still use `.proto` files or prebuilt descriptor sets.

Monitor at minimum:

| Signal | Decision Value |
| --- | --- |
| RPC counts by full method and status | Spot concentrated failures |
| Latency histograms, p95/p99 | Track SLAs and tail latency |
| `DEADLINE_EXCEEDED`, cancellations | Detect slow responses or caller timeouts |
| Active RPCs/streams, payload bytes | Detect resource saturation |
| Retry counts and failure rates | Alert on retry storms |
| Channel connectivity / TLS errors | Separate DNS, network, and certificate issues |
| Trace spans across services | Follow requests across gateways, gRPC, and DBs |
| Idempotency hits and business failures | Distinguish RPC transport from business outcomes |

Micrometer/OpenTelemetry offer instrumentation libraries; check version compatibility and how they plug into your grpc-java setup or starter. Spring Boot web metrics do not cover gRPC calls by default. Server/client interceptors should propagate trace context in metadata; log method, status, latency, `requestId`, and `traceId` instead of raw payloads or tokens.

## 10. Testing Both gRPC Logic and Transport

### 10.1. In-Process Tests

You can use `grpc-inprocess` to test request/response mapping without opening TCP ports. JUnit 5 + Mockito example:

~~~java
import com.example.integration.inventory.v1.CheckAvailabilityRequest;
import com.example.integration.inventory.v1.InventoryServiceGrpc;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.*;

class InventoryGrpcEndpointTest {

    @Test
    void returnsAvailableStock() throws Exception {
        var inventory = mock(InventoryApplicationService.class);
        when(inventory.check("SKU-1", 2))
                .thenReturn(new InventorySnapshot(true, 13L, "WH-1"));

        String name = InProcessServerBuilder.generateName();
        var server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new InventoryGrpcEndpoint(inventory))
                .build()
                .start();
        var channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            var stub = InventoryServiceGrpc.newBlockingStub(channel);
            var request = CheckAvailabilityRequest.newBuilder()
                    .setSku("SKU-1")
                    .setRequestedQuantity(2)
                    .build();

            var response = stub.checkAvailability(request);

            assertTrue(response.getAvailable());
            verify(inventory).check("SKU-1", 2);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This example uses the interface/record from Section 4 and requires JUnit, Mockito, and `grpc-inprocess` test dependencies. `directExecutor()` is handy for small tests, not a production configuration for handlers that may block.

### 10.2. Real Integration Testing Over HTTP/2

In-process tests do not verify TLS, HTTP/2, DNS, ingress, proxies, or load balancing. Cover these scenarios:

| Scenario | What to Verify |
| --- | --- |
| Server opens real gRPC port | Call unary RPC over TCP/HTTP2, not just a Spring context load test |
| Invalid input | `INVALID_ARGUMENT`, no DB writes |
| Missing SKU | `NOT_FOUND`, distinct from out-of-stock |
| Short deadline | Caller gets `DEADLINE_EXCEEDED`; server observes cancellation |
| Wrong CA/hostname | TLS handshake rejected safely |
| Gateway/Ingress | gRPC routes and streaming work without unintended connection drops |
| Different contract versions | Old client + new server and vice versa per support matrix |
| Replayed `requestId` | Write side effect occurs only once |
| Pod stops mid-RPC | Readiness/graceful shutdown works per policy |
| Two or more replicas | Requests distribute and fail over as designed |
| Monitoring | Status, latency, and trace IDs appear accurately |

When adopting a starter, also test whether the server auto-registers, property bindings, interceptor ordering, and starter resource cleanup. Even when unit tests pass, run real-network tests with the certificates and policies of your target environment.

## 11. Choosing gRPC, REST, or Messaging

| Scenario | Usually Suitable Technology | Additional Components to Design |
| --- | --- | --- |
| Internal services needing sync RPC and typed contracts | **gRPC/protobuf** | Stubs, channels, deadlines, TLS, observability |
| Public/browser APIs needing easy inspection and caching | **HTTP REST/JSON** | Contracts, auth, statuses, retries, caching |
| Work queued for offline workers | **JMS queue or appropriate broker** | Ack, redelivery, DLQ, idempotency |
| One event broadcast to multiple business groups | **Topic/event bus** | Subscriptions, retention, schemas/versions |
| Live status streams | **gRPC streaming** if clients/proxies support it | Reconnects, flow control, resume |
| Storing/replaying months of history | **Dedicated event log/store** | Offsets, retention, replay, schema migrations |

An architecture can combine them: `checkout-service` calls `inventory-service` via gRPC to read stock synchronously, then writes the order and outbox inside a single database transaction to publish `OrderPlaced` via a broker. Each technology handles the responsibility it was built for.

### Pre-Deployment Checklist

1. Finalize `.proto` contracts, field numbering rules, versioning, and compatibility.
2. Align grpc-java BOM, protobuf runtime, `protoc`, and generator versions; generate code in CI.
3. Choose a compatible starter or explicitly wire server beans, service registration, lifecycle, `ManagedChannel`, and stubs.
4. Configure ports, DNS/resolvers, load balancing, proxies/ingress, HTTP/2, and resource limits.
5. Enable TLS/mTLS at proper boundaries, enforce AuthN/AuthZ via interceptors, and manage secrets/certificates.
6. Design deadlines, cancellation, retries/backoff, and per-method idempotency.
7. Separate SQL transactions, RPCs, and message publishing; use outbox when durable coordination is required.
8. Add health/readiness, metrics, tracing, secure logging, and graceful shutdown.
9. Test contracts, in-process mapping, and real-network/TLS/scale integration before release.

**Key takeaway:** protobuf describes contracts and data; gRPC provides remote calls and streaming; Spring Boot manages the application. Build codegen, registration, server/channel lifecycles, TLS, discovery, deadlines, retries, health, and observability are integration responsibilities that must be explicitly configured and tested. gRPC gives service-to-service calls strong structure, but does not automatically replace durable messaging systems or business data transactions.
