# Creating a Spring Boot gRPC Server

## 1. Project Objective

In **SPRING_GRPC**, we build gRPC services in the Spring ecosystem using Protocol Buffers contracts, auto-generated Java code, and Spring-managed service implementations. This hands-on lesson creates an inventory management server with a unary RPC to look up an item by ID.

Upon completion, the project will be able to:

- Declare services and messages in a protobuf file.
- Generate Java message classes, service descriptors, and server base classes.
- Start the gRPC server alongside the Spring Boot application context.
- Register the implementation using Spring gRPC annotations.
- Return appropriate protobuf responses or gRPC statuses.
- Verify the server using `grpcurl` and service-level tests.

The scope focuses on getting a working server running. Authentication, production TLS, streaming, discovery, and observability are follow-up extensions once the basic path is working.

## 2. Architecture and Directory Structure

Clients do not invoke server Java methods directly. Clients send HTTP/2 gRPC requests targeting the service/method described in the protobuf contract. Generated stubs and descriptors ensure both sides use the same message and RPC definitions.

~~~mermaid
flowchart LR
    P["inventory.proto"] --> G["protoc + gRPC plugin"]
    G --> M["Generated Java messages"]
    G --> S["Generated service base"]
    M --> I["InventoryGrpcService"]
    S --> I
    I --> U["InventoryUseCase"]
    U --> R["InventoryRepository"]
    C["gRPC client / grpcurl"] -->|HTTP/2 + protobuf| V["Spring gRPC server"]
    V --> I
~~~

A simple project structure:

~~~text
inventory-grpc/
  build.gradle.kts
  settings.gradle.kts
  src/
    main/
      proto/
        inventory/v1/inventory.proto
      java/
        com/example/inventory/
          InventoryApplication.java
          grpc/
            InventoryGrpcService.java
          application/
            InventoryUseCase.java
          domain/
            InventoryItem.java
    test/
      java/
        com/example/inventory/grpc/
          InventoryGrpcServiceTest.java
~~~

The generated source directory is typically created by the protobuf plugin inside the build directory. Never edit generated Java files directly; update the contract in the `.proto` file and re-run the generate task.

## 3. Creating the Spring Boot Project and Dependencies

Create a Spring Boot project with a Java toolchain matching your chosen Spring Boot version. Add the Spring gRPC server starter and the protobuf Gradle plugin. The starter provides server integration with Spring; the plugin runs `protoc` to generate message classes and gRPC service code.

Example Gradle Kotlin DSL configuration:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-version>"
    id("com.google.protobuf") version "0.9.5"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.grpc:spring-grpc-spring-boot-starter:<spring-grpc-version>")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.grpc:grpc-inprocess:<grpc-java-version>")
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:<protoc-version>"
    }
    plugins {
        grpc {
            artifact = "io.grpc:protoc-gen-grpc-java:<grpc-java-version>"
        }
    }
    generateProtoTasks {
        all().configureEach {
            plugins {
                grpc {}
            }
        }
    }
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

Replace the version placeholders with compatible versions of Spring Boot, Spring gRPC, the protobuf compiler, and the gRPC Java code generator in your project. Use the dependency management/BOM provided by the starter or project to keep gRPC runtime libraries aligned. Do not manually pick a `grpc-protobuf` or `grpc-stub` version different from the runtime managed by the starter.

If your starter version already manages `grpc-protobuf` and `grpc-stub`, do not redeclare them with independent versions. When generated code reports missing classes or incompatible method errors, inspect the runtime dependency tree and `protoc` plugin versions before modifying source code.

## 4. Declaring the Protobuf Contract

Create `src/main/proto/inventory/v1/inventory.proto`:

~~~proto
syntax = "proto3";

package inventory.v1;

option java_package = "com.example.inventory.grpc.v1";
option java_multiple_files = true;
option java_outer_classname = "InventoryProto";

service InventoryService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
}

message GetItemRequest {
  string item_id = 1;
}

message GetItemResponse {
  string item_id = 1;
  string name = 2;
  int32 available_quantity = 3;
}
~~~

The contract defines one service and one unary method. The request carries the item ID; the response returns the ID, name, and available quantity.

Key rules to observe:

- `package` is the protobuf namespace on the wire and forms part of the full service name.
- `java_package` determines the generated Java package.
- `java_multiple_files = true` generates message classes as separate Java types.
- Field numbers are wire identifiers; never change or reuse published field numbers.
- Do not use `required` in proto3; validate data at the boundary or domain layer.
- When removing a field, reserve its field number and name if needed to prevent accidental reuse later.

The full RPC name in this example is `inventory.v1.InventoryService/GetItem`. Clients must use this exact package, service, and method name.

## 5. Generating Java Messages and gRPC Service Code

The protobuf plugin generates Java classes from `.proto` files. With Gradle, run:

~~~bash
./gradlew clean generateProto
~~~

On Windows:

~~~powershell
.\gradlew.bat clean generateProto
~~~

After code generation, the corresponding artifacts should exist:

- `GetItemRequest` and `GetItemResponse`: protobuf message classes.
- `InventoryServiceGrpc`: gRPC service descriptor, stub types, and server base class.
- `InventoryServiceGrpc.InventoryServiceImplBase`: base class for the server implementation to extend.

The exact names and locations of generated sources depend on the plugin/version. Your IDE may require a Gradle sync or marking the generated source root to recognize the classes. Do not copy generated Java files into `src/main/java`; let the build regenerate them from the contract.

If the task cannot find the `.proto` file, check that it is located under `src/main/proto`. If messages are generated but the service base class is missing, check the gRPC plugin configuration in `generateProtoTasks`.

## 6. Creating the Spring Boot Application

Create the entry point:

~~~java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

Spring Boot creates the application context and initializes configured beans. The Spring gRPC starter integrates the gRPC server with the context lifecycle, allowing the service implementation to be managed as a Spring bean.

Do not manually create an `io.grpc.Server` in `main` when the starter already manages the server. Creating a parallel server manually can cause two listeners, port conflicts, and inconsistent shutdown lifecycles.

## 7. Configuring the gRPC Port

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  grpc:
    server:
      port: 9090
~~~

The property namespace depends on the Spring gRPC starter and version selected. The example above uses the Spring gRPC starter namespace; verify the property reference for your exact version if using a different starter.

If the application also includes Spring MVC/WebFlux, the HTTP server can run on its own port (e.g., 8080) while the gRPC server runs on 9090. Never assume Spring Boot's `server.port` is the gRPC port.

The port can be overridden per environment via environment variables or profiles. When deploying, verify both the port the process actually binds to and the `port`/`targetPort` exposed by the container platform.

## 8. Creating the Application Use Case and Domain Model

Keep business rules outside the gRPC adapter layer. Example domain model:

~~~java
package com.example.inventory.domain;

public record InventoryItem(
        String id,
        String name,
        int availableQuantity) {}
~~~

Item lookup use case:

~~~java
package com.example.inventory.application;

import com.example.inventory.domain.InventoryItem;
import java.util.Optional;

public interface InventoryUseCase {
    Optional<InventoryItem> findById(String itemId);
}
~~~

A simple implementation for this hands-on exercise can use an in-memory map:

~~~java
package com.example.inventory.application;

import com.example.inventory.domain.InventoryItem;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.Optional;

@Service
public class InMemoryInventoryService implements InventoryUseCase {
    private final Map<String, InventoryItem> items = Map.of(
            "item-100", new InventoryItem("item-100", "Keyboard", 12),
            "item-200", new InventoryItem("item-200", "Mouse", 25));

    @Override
    public Optional<InventoryItem> findById(String itemId) {
        return Optional.ofNullable(items.get(itemId));
    }
}
~~~

In-memory data is only for running and testing the server. Real applications should replace it with an appropriate repository and define clear transaction/consistency boundaries if data is updated concurrently.

## 9. Implementing the gRPC Service as a Spring Bean

Create an adapter extending the generated server base class:

~~~java
package com.example.inventory.grpc;

import com.example.inventory.application.InventoryUseCase;
import com.example.inventory.application.ItemNotFoundException;
import com.example.inventory.domain.InventoryItem;
import com.example.inventory.grpc.v1.GetItemRequest;
import com.example.inventory.grpc.v1.GetItemResponse;
import com.example.inventory.grpc.v1.InventoryServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class InventoryGrpcService
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    private final InventoryUseCase inventory;

    public InventoryGrpcService(InventoryUseCase inventory) {
        this.inventory = inventory;
    }

    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {

        String itemId = request.getItemId();
        if (itemId == null || itemId.isBlank()) {
            responseObserver.onError(
                    Status.INVALID_ARGUMENT
                            .withDescription("item_id must not be blank")
                            .asRuntimeException());
            return;
        }

        try {
            InventoryItem item = inventory.findById(itemId)
                    .orElseThrow(() -> new ItemNotFoundException(itemId));

            GetItemResponse response = GetItemResponse.newBuilder()
                    .setItemId(item.id())
                    .setName(item.name())
                    .setAvailableQuantity(item.availableQuantity())
                    .build();

            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (ItemNotFoundException ex) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Item was not found")
                            .asRuntimeException());
        } catch (RuntimeException ex) {
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Unable to retrieve item")
                            .asRuntimeException());
        }
    }
}
~~~

Define the domain/application exception used in the adapter:

~~~java
package com.example.inventory.application;

public final class ItemNotFoundException extends RuntimeException {
    public ItemNotFoundException(String itemId) {
        super("Item not found: " + itemId);
    }
}
~~~

Spring gRPC's `@GrpcService` annotation both marks the service for starter registration and lets Spring manage dependency injection.

The adapter has three responsibilities:

1. Validate data at the RPC boundary.
2. Call the use case and map the domain result to the protobuf response.
3. Translate errors into stable gRPC statuses.

Never return stack traces, SQL messages, hostnames, or sensitive information in the `Status` description. Log exceptions on the server with appropriate correlation/trace context; the client should only receive controlled error details.

Every successful unary RPC must emit exactly one `onNext` followed by one `onCompleted`. On error, emit `onError` and make no further terminal signal calls.

## 10. Error and Status Checking

Agree on a consistent error-mapping strategy between the application and gRPC:

| Scenario | Suggested gRPC Status |
|---|---|
| `item_id` is blank or malformed | INVALID_ARGUMENT |
| Item not found | NOT_FOUND |
| Caller is unauthenticated | UNAUTHENTICATED |
| Caller lacks permission to view item | PERMISSION_DENIED |
| Business state does not allow operation | FAILED_PRECONDITION |
| Downstream dependency temporarily unavailable | UNAVAILABLE |
| RPC exceeded deadline | DEADLINE_EXCEEDED |
| Unexpected error | INTERNAL |

Do not use `INTERNAL` for every domain error. Status codes are part of the contract that clients rely on to decide whether to retry, display an error, or take further action. Avoid returning `UNAVAILABLE` for validation errors, as clients may retry futilely.

For larger systems, move exception mapping into a shared interceptor or error handler so service methods do not duplicate mapping logic. Either way, maintain a uniform status policy.

## 11. Starting and Checking the Server

Run the application:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Check the startup logs:

- The Spring application context started successfully.
- The Spring gRPC server bound to port 9090.
- `InventoryGrpcService` was discovered and registered.
- No port-already-in-use, bean creation, or generated class mismatch errors occurred.

A running server does not guarantee the RPC works yet. Proceed to probe it with a gRPC client to verify the service/method and response.

## 12. Calling the Server with grpcurl

If reflection is enabled on the server, list services:

~~~bash
grpcurl -plaintext localhost:9090 list
~~~

Inspect the service:

~~~bash
grpcurl -plaintext localhost:9090 describe inventory.v1.InventoryService
~~~

Call the unary method:

~~~bash
grpcurl -plaintext \
  -d '{"itemId":"item-100"}' \
  localhost:9090 \
  inventory.v1.InventoryService/GetItem
~~~

The expected response includes `itemId`, `name`, and `availableQuantity`. Try a non-existent ID to confirm the server returns `NOT_FOUND`; try an empty string to confirm `INVALID_ARGUMENT`.

If reflection is disabled, `grpcurl list` cannot enumerate services even when the server is running. Provide the `.proto` file instead:

~~~bash
grpcurl -plaintext \
  -import-path src/main/proto \
  -proto inventory/v1/inventory.proto \
  -d '{"itemId":"item-100"}' \
  localhost:9090 \
  inventory.v1.InventoryService/GetItem
~~~

Do not enable reflection in production solely for debugging convenience if security policy forbids it. You can keep reflection enabled in the development profile or use a build-generated descriptor/protoset.

## 13. Writing Service Tests

Unit tests for the use case should invoke the use case directly using a fake repository. To test the gRPC adapter, generated stubs, protobuf mapping, and statuses without opening TCP sockets, use the in-process gRPC transport.

Example test via generated stub:

~~~java
import com.example.inventory.application.InventoryUseCase;
import com.example.inventory.domain.InventoryItem;
import com.example.inventory.grpc.v1.GetItemRequest;
import com.example.inventory.grpc.v1.GetItemResponse;
import com.example.inventory.grpc.v1.InventoryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class InventoryGrpcServiceTest {
    private Server server;
    private ManagedChannel channel;
    private InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        InventoryUseCase useCase = itemId ->
                itemId.equals("item-100")
                        ? Optional.of(new InventoryItem("item-100", "Keyboard", 12))
                        : Optional.empty();

        server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new InventoryGrpcService(useCase))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        stub = InventoryServiceGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }

    @Test
    void returnsExistingItem() {
        GetItemResponse response = stub.getItem(
                GetItemRequest.newBuilder()
                        .setItemId("item-100")
                        .build());

        assertEquals("Keyboard", response.getName());
        assertEquals(12, response.getAvailableQuantity());
    }

    @Test
    void mapsMissingItemToNotFound() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getItem(
                        GetItemRequest.newBuilder()
                                .setItemId("missing")
                                .build()));

        assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
    }
}
~~~

This example assumes test dependencies include `grpc-inprocess`, JUnit Jupiter, and the `InventoryGrpcService`/`ItemNotFoundException` classes in the packages shown. The `grpc-inprocess` version must align with the gRPC Java runtime and `protoc` plugin. In production test suites, await termination where needed, avoid sharing mutable state across parallel tests, and ensure cleanup even if setup fails.

In-process tests do not prove that TCP, TLS, HTTP/2, port mapping, or proxies work. Keep a small set of integration tests using a real server on an ephemeral/test port to verify transport and deployment configuration.

## 14. Project Completion Checklist

| Item | Completion Criteria |
|---|---|
| Spring Boot project | Application context starts up |
| Dependencies | Starter and gRPC/protobuf runtimes are compatible |
| Protobuf contract | Service, methods, and messages are clearly declared |
| Code generation | Java message classes and gRPC service base exist |
| Server configuration | gRPC port is configured properly |
| Service registration | `@GrpcService` is discovered by the starter |
| Dependency injection | Use case is injected into the adapter |
| Unary response | Sends exactly one response then completes |
| Error mapping | Validation and not-found return appropriate statuses |
| Manual probe | `grpcurl` can invoke the method |
| Automated tests | Unit and in-process tests verify logic and contract |
| Lifecycle | Server is managed alongside the Spring context |

## 15. Common Errors When Creating a Spring Boot gRPC Server

| Symptom | Common Cause | Resolution |
|---|---|---|
| Generated classes not found | Code generation not run or source root not recognized by IDE | Check `src/main/proto`, `generateProto` task, and Gradle sync |
| Message classes exist but service base is missing | gRPC protoc plugin not configured | Check `plugins { grpc {} }` in the generation task |
| Runtime throws `NoClassDefFoundError` | Missing or mismatched gRPC/protobuf runtime versions | Inspect dependency management/BOM and generated code |
| Spring does not register service | Wrong starter annotation or bean outside component scan | Use `@GrpcService` from the right package/version and check startup logs |
| Port bind fails | Port already in use or misconfigured property | Check active listeners and effective gRPC properties |
| Client calls wrong HTTP port | Confusing `server.port` with the gRPC port | Identify the dedicated gRPC server port |
| `UNIMPLEMENTED` | Wrong service/method name or service not registered | Compare protobuf descriptor and server registration |
| `UNAUTHENTICATED` | Invalid security metadata/token | Inspect interceptors and credentials |
| `grpcurl list` fails | Reflection not enabled | Supply `.proto`/protoset to invoke the method |
| Tests leak channels/servers | Missing cleanup of in-process fixtures | Shut down channel/server in test lifecycle hooks |

## 16. Extending After the Basic Server Works

Once the unary server runs reliably, you can extend it capability by capability:

- **TLS/mTLS:** load certificates and trust chains via the starter configuration for your version; verify SAN, SNI, and ALPN `h2`.
- **Authentication/authorization:** validate metadata or client identity, then enforce permissions at the service/use-case boundary.
- **Deadline/cancellation:** require clients to set deadlines and propagate the remaining budget to downstream dependencies.
- **Interceptors:** add shared logging, correlation IDs, metrics, and error mapping.
- **Health/reflection:** enable health checking and reflection according to the deployment environment.
- **Streaming:** add server/client/bidirectional streaming per contract and manage flow control/cancellation.
- **Integration tests:** test TCP, TLS, databases, brokers, and service discovery in an isolated environment.

Do not cram all concerns into a single service method. Keep the adapter thin, keep use cases focused on business logic, and configure infrastructure concerns at the appropriate boundaries.


## 17. Testing Through the Spring-Managed Server

The in-process test in the previous section verifies generated stubs, the service adapter, protobuf mapping, and gRPC statuses without opening a socket. It does not prove that Spring discovered the bean, that the starter bound the listener, or that the port configuration works. To verify the full application path, include at least one integration test that boots the Spring context and invokes the RPC over TCP against the starter-managed server.

The following example uses a dedicated port `19090`. The test exercises the same `InMemoryInventoryService` and `InventoryGrpcService` beans discovered by Spring component scanning:

~~~java
package com.example.inventory.grpc;

import com.example.inventory.grpc.v1.GetItemRequest;
import com.example.inventory.grpc.v1.GetItemResponse;
import com.example.inventory.grpc.v1.InventoryServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = "spring.grpc.server.port=19090")
class InventoryGrpcServerIntegrationTest {
    private ManagedChannel channel;
    private InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    @BeforeEach
    void connectToSpringManagedServer() {
        channel = ManagedChannelBuilder
                .forAddress("localhost", 19090)
                .usePlaintext()
                .build();

        stub = InventoryServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(2, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }

    @Test
    void springRegistersAndServesInventoryRpc() {
        GetItemResponse response = stub.getItem(
                GetItemRequest.newBuilder()
                        .setItemId("item-100")
                        .build());

        assertEquals("item-100", response.getItemId());
        assertEquals("Keyboard", response.getName());
        assertEquals(12, response.getAvailableQuantity());
    }

    @Test
    void springServerReturnsNotFoundForUnknownItem() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getItem(
                        GetItemRequest.newBuilder()
                                .setItemId("missing")
                                .build()));

        assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
    }
}
~~~

This test simultaneously verifies that the Spring context starts, `@GrpcService` is discovered, the starter binds the port, and the generated client can invoke the method. A fixed port is only an example; do not run multiple test classes in parallel on the same port. If your starter/version supports random port assignment and exposes the bound port, prefer that mechanism for parallel test suites.

`usePlaintext()` is used here because local tests do not cross an untrusted network. Separate TLS integration tests should configure test certificates and matching client trust settings. Always set a deadline so failing tests do not hang the suite, and close the channel after each test.

## 18. Lifecycle and Pre-Production Requirements

The Spring gRPC starter manages the server alongside the `ApplicationContext`. Service beans must be instantiated and dependency-injected before receiving traffic; when the context closes, the server is shut down according to the framework lifecycle. Never manually instantiate a second `NettyServer` inside a constructor or business bean when the starter already manages the listener.

Before deploying, review the following areas:

- **Ports and networking:** define the HTTP port and gRPC port separately; map container ports, Kubernetes Service `port`/`targetPort`, selectors, and Ready endpoints accurately. Configure ingress/load balancers to support HTTP/2 and gRPC.
- **TLS/mTLS:** use securely managed certificates and private keys; clients must verify the trust chain and SAN. If mTLS is enabled, the server must trust the client CA and clients must present matching certificates. Configure according to your exact Spring gRPC starter version.
- **Authentication/authorization:** authenticate the principal at the security boundary, enforce authorization per RPC, and never trust a self-declared tenant ID from the client.
- **Deadline/cancellation:** require clients to set reasonable deadlines; propagate the remaining budget downstream and stop cancellable work when a call is cancelled.
- **Message limits:** bound inbound/outbound message sizes and metadata sizes as needed to prevent large payloads from exhausting memory.
- **Observability:** record method name, status code, duration, and correlation ID; mask tokens and personal data from logs.
- **Health/readiness:** accept traffic only when the listener and mandatory dependencies are ready. Distinguish HTTP management health endpoints from the gRPC Health Checking Protocol.
- **Graceful shutdown:** stop accepting new calls, allow in-flight calls time to complete per policy, and then shut down the listener. Streaming producers must stop when the client cancels.
- **Capacity:** choose executors, concurrency limits, and resource policies based on realistic load; never assume one RPC always maps to one dedicated thread.

Properties for TLS, health, reflection, and graceful shutdown vary across starter versions. Use the configuration supported by your pinned version; do not copy properties from a different Spring gRPC library.

## 19. Diagnosing Startup and Service Registration Errors

| Symptom | Possible Cause | Diagnostic Steps |
|---|---|---|
| Spring starts, but the gRPC port is not open | Starter missing, auto-configuration excluded, or misconfigured port | Check dependencies, startup logs, and effective properties |
| Server opens port, but method returns `UNIMPLEMENTED` | Service bean not scanned/bound or wrong method path | Check `@GrpcService`, package, descriptor, and full method path |
| Cannot compile `InventoryServiceImplBase` | gRPC Java sources not generated or missing gRPC plugin | Check `generateProto` and generated source outputs |
| Client receives `UNAVAILABLE` | Server not ready yet, wrong host/port, or transport mismatch | Check listener, container port, network, and TLS/plaintext |
| Client receives `INVALID_ARGUMENT` | Handler ran and validation rejected the request | Check request fields and status contract |
| Test hangs | Missing deadline or unclosed channel/server | Set a deadline, tear down channel, and inspect server logs |
| Two servers fight over the same port | Manual server running alongside auto-configuration or tests sharing a port | Use a single server lifecycle and assign isolated test ports |
| Bean exists, but RPC cannot be called | Bean not bound to server or server not started | Call via generated stub over the listener in an integration test |

When the server fails to open its port, verify whether auto-configuration ran, whether the service bean is within component scan scope, and whether the generated service definition is correct. Do not work around this by creating an extra manual Netty server before verifying the starter; doing so can cause dual listeners, duplicate service registration, and inconsistent shutdown behavior.

**Remember:** Building a Spring Boot gRPC server means wiring a protobuf contract and generated service base into the Spring lifecycle. The protobuf plugin generates messages/stubs; the Spring gRPC starter manages the listener and registration; `@GrpcService` exposes the implementation to the server; use cases hold business logic. Configure the gRPC port accurately, verify with `grpcurl`, test mapping/statuses with in-process tests, and keep at least one integration test calling the Spring-managed server over TCP. Once the unary path works, finalize TLS, security, deadlines, health checks, graceful shutdown, and observability for your deployment environment.
