# Separating Client Adapters from Business Code

When an application service calls a generated gRPC stub directly, business code has to know about `HelloRequest`, `StatusRuntimeException`, deadlines, and Protobuf types. That couples business code to the remote communication contract. When `.proto` changes or the application switches to another service, multiple business classes may have to change with it.

A **client adapter** creates a boundary between the application and gRPC: it accepts a request in the application's own language, converts it into Protobuf, calls the generated stub, and translates the gRPC response or error into a result/exception understood by the application service. Business code depends only on an interface owned by the application. This structure follows the ports and adapters (hexagonal) architecture and fits the Spring client section of the **SPRING_GRPC** module: developing clients/servers from Protocol Buffers contracts and generated Java code, supporting unary/streaming RPCs, metadata, deadlines, statuses, interceptors, TLS, testing, and observability.

## 1. The Boundary Between Business Code and gRPC

A call flow should look like this:

```mermaid
flowchart LR
    A[Application Service] --> B[InventoryPort]
    B --> C[GrpcInventoryAdapter]
    C --> D[Generated gRPC Stub]
    D --> E[ManagedChannel]
    E --> F[gRPC Server]
```

- **Port** is an interface belonging to the application/domain layer. It describes what capability the application needs using the application's own types.
- **Adapter** implements the port using a specific technology. In this lesson, the adapter uses a generated gRPC stub.
- **Business service** orchestrates business rules through the port; it needs no knowledge of Protobuf requests/responses or gRPC statuses.

The dependency rule is: business code defines what it needs; the adapter depends on the business contract to fulfill it. Never let domain packages import `io.grpc` or Java packages generated from `.proto`.

## 2. Designing a Port Around Business Needs

Suppose the business needs to check stock availability by SKU. The port should describe the outcome the application requires, not mirror the RPC's raw shape:

```java
package com.example.inventory.application;

public interface InventoryPort {
    StockAvailability getAvailability(Sku sku);
}
```

Types paired with the port live in their own files inside the application package. `Sku.java`:

```java
package com.example.inventory.application;

public record Sku(String value) {
    public Sku {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("SKU must not be empty");
        }
        value = value.trim();
    }
}
```

`StockAvailability.java`:

```java
package com.example.inventory.application;

public record StockAvailability(int availableUnits) {
    public StockAvailability {
        if (availableUnits < 0) {
            throw new IllegalArgumentException("Available units cannot be negative");
        }
    }
}
```

`InventoryPort` neither returns `StockReply` nor accepts `StockRequest`. If the gRPC server adds technical fields, renames its Protobuf package, or changes transport, the port can remain intact as long as business semantics do not change.

A port should reflect the application's true semantics. If the domain needs to check stock, `getAvailability` is far clearer than a generic interface like `GrpcClient.call(byte[])`. Avoid overly broad abstractions that force business services to know RPC names, Protobuf messages, or status codes again.

## 3. An Adapter Translating Between Application Models and Protobuf

Suppose the gRPC contract defines a `GetStock` RPC:

```protobuf
syntax = "proto3";

package inventory.v1;

option java_package = "com.example.contract.inventory";
option java_multiple_files = true;

service Inventory {
  rpc GetStock (StockRequest) returns (StockReply);
}

message StockRequest {
  string sku = 1;
}

message StockReply {
  int32 available_units = 1;
}
```

After running `protoc` and the `protoc-gen-grpc-java` plugin, the client has `InventoryGrpc`, `StockRequest`, and `StockReply`. Those types appear only inside the adapter:

```java
package com.example.inventory.infrastructure.grpc;

import com.example.contract.inventory.InventoryGrpc;
import com.example.contract.inventory.StockReply;
import com.example.contract.inventory.StockRequest;
import com.example.inventory.application.InventoryIntegrationException;
import com.example.inventory.application.InventoryItemNotFoundException;
import com.example.inventory.application.InventoryPort;
import com.example.inventory.application.Sku;
import com.example.inventory.application.StockAvailability;
import com.example.inventory.application.InventoryUnavailableException;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class GrpcInventoryAdapter implements InventoryPort {

    private final InventoryGrpc.InventoryBlockingStub stub;

    public GrpcInventoryAdapter(InventoryGrpc.InventoryBlockingStub stub) {
        this.stub = stub;
    }

    @Override
    public StockAvailability getAvailability(Sku sku) {
        StockRequest request = StockRequest.newBuilder()
                .setSku(sku.value())
                .build();

        try {
            StockReply reply = stub
                    .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
                    .getStock(request);

            return new StockAvailability(reply.getAvailableUnits());
        } catch (StatusRuntimeException failure) {
            throw mapFailure(failure);
        }
    }

    private RuntimeException mapFailure(StatusRuntimeException failure) {
        Status.Code code = failure.getStatus().getCode();

        return switch (code) {
            case NOT_FOUND -> new InventoryItemNotFoundException(failure);
            case UNAVAILABLE, DEADLINE_EXCEEDED ->
                    new InventoryUnavailableException(failure);
            default -> new InventoryIntegrationException(failure);
        };
    }
}
```

The exceptions below live as separate files in the application package. `InventoryItemNotFoundException.java`:

```java
package com.example.inventory.application;

public class InventoryItemNotFoundException extends RuntimeException {
    public InventoryItemNotFoundException(Throwable cause) {
        super("Item not found in inventory system", cause);
    }
}
```

`InventoryUnavailableException.java`:

```java
package com.example.inventory.application;

public class InventoryUnavailableException extends RuntimeException {
    public InventoryUnavailableException(Throwable cause) {
        super("Inventory service is currently unavailable", cause);
    }
}
```

`InventoryIntegrationException.java`:

```java
package com.example.inventory.application;

public class InventoryIntegrationException extends RuntimeException {
    public InventoryIntegrationException(Throwable cause) {
        super("Unable to complete request to inventory service", cause);
    }
}
```

These exceptions use only application Java types and `Throwable` as the cause. The adapter still inspects `Status.Code` to pick the mapping branch, while the application package needs no dependency on `io.grpc`. The original exception is preserved as the cause for internal logging; messages exposed upward stay under application control.

**Mapping must follow operation semantics.** `NOT_FOUND` on `GetStock` can signify that the SKU does not exist; on another RPC, the same status might mean a wrong route or another missing dependency resource. Never establish a blanket global rule saying every `NOT_FOUND` represents the same domain error. Likewise, `UNAVAILABLE` and `DEADLINE_EXCEEDED` usually indicate an unavailable or slow dependency, yet do not automatically permit retrying side-effecting operations.

## 4. Business Services Depend Only on the Port

The application service uses `InventoryPort` and domain/application types without importing gRPC:

```java
package com.example.order.application;

import com.example.inventory.application.InventoryPort;
import com.example.inventory.application.Sku;
import com.example.inventory.application.StockAvailability;
import org.springframework.stereotype.Service;

@Service
public class CheckOrderAvailability {

    private final InventoryPort inventory;

    public CheckOrderAvailability(InventoryPort inventory) {
        this.inventory = inventory;
    }

    public AvailabilityResult check(String rawSku) {
        StockAvailability stock = inventory.getAvailability(new Sku(rawSku));

        if (stock.availableUnits() == 0) {
            return AvailabilityResult.OUT_OF_STOCK;
        }
        return AvailabilityResult.AVAILABLE;
    }

    public enum AvailabilityResult {
        AVAILABLE,
        OUT_OF_STOCK
    }
}
```

The business service does not know whether the call uses blocking gRPC, REST, or an in-memory test fake. It only knows it asks for inventory and receives `StockAvailability`. This is the core benefit of an adapter: technical changes at the boundary do not spill into business rules.

## 5. Spring Wiring: Letting the Container Select the Adapter

In Spring configuration, `GrpcInventoryAdapter` is registered with `@Component` and receives the generated stub via its constructor. The stub is provided by a `@Bean` created from a configured `ManagedChannel`:

```java
@Bean
InventoryGrpc.InventoryBlockingStub inventoryBlockingStub(
        @Qualifier("inventoryChannel") ManagedChannel channel) {
    return InventoryGrpc.newBlockingStub(channel);
}
```

Because `GrpcInventoryAdapter` is the sole implementation of `InventoryPort`, Spring injects it into `CheckOrderAvailability`. If an application has multiple implementations (for example, a primary gRPC adapter and a fake/local implementation), use `@Qualifier` or `@Primary` to select one explicitly. Never let business services call `new GrpcInventoryAdapter(...)` themselves; the container handles wiring infrastructure dependencies.

The adapter is the proper place to set RPC deadlines, select stubs, convert Protobuf models, and map statuses. Shared interceptors for logging/tracing/metrics can be attached at the channel level so every adapter using that channel is observed consistently. Avoid putting cross-cutting observability code into business services.

## 6. Testing Business Code Without a gRPC Server

Because the business service depends only on `InventoryPort`, business rules can be tested with a tiny fake implementation:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.inventory.application.InventoryPort;
import com.example.inventory.application.Sku;
import com.example.inventory.application.StockAvailability;
import org.junit.jupiter.api.Test;

class CheckOrderAvailabilityTest {

    @Test
    void reportsOutOfStockWhenInventoryReturnsZero() {
        InventoryPort inventory = sku -> new StockAvailability(0);
        var service = new CheckOrderAvailability(inventory);

        assertEquals(
                CheckOrderAvailability.AvailabilityResult.OUT_OF_STOCK,
                service.check("SKU-42"));
    }

    @Test
    void reportsAvailableWhenStockExists() {
        InventoryPort inventory = sku -> new StockAvailability(5);
        var service = new CheckOrderAvailability(inventory);

        assertEquals(
                CheckOrderAvailability.AvailabilityResult.AVAILABLE,
                service.check("SKU-42"));
    }
}
```

These two tests do not start a Spring context, require no generated code, and open no channels. They test business rules directly. You can add a fake throwing `InventoryUnavailableException` to verify that the service handles dependency failures according to the use case's policy.

## 7. Testing the Adapter Against gRPC Separately

The adapter needs a separate suite of tests to verify translation between the two worlds:

1. Use `grpc-inprocess` to create a test server implementing `Inventory/GetStock`.
2. Create an in-process channel and a generated `InventoryBlockingStub`, then construct `GrpcInventoryAdapter` via its constructor.
3. Send a `Sku`; verify the server receives the expected `StockRequest.sku` and the response converts into `StockAvailability`.
4. Have the server return `NOT_FOUND`, `UNAVAILABLE`, or `INVALID_ARGUMENT`; verify the adapter throws the right application exception and retains the gRPC exception as its cause.
5. Close the channel/server in `finally` or via test lifecycle hooks.

Adapter tests do not need to instantiate the whole business service. Conversely, business service tests should not need a gRPC server. This separation makes it immediately clear whether a bug lives in Protobuf/transport mapping or in business rules.

In-process tests verify RPC logic, yet they do not test DNS, TLS, proxies, or real networked HTTP/2. Integration tests over TCP/TLS remain necessary for deployment risks. When you also want to verify Spring wiring, add a context test checking that `InventoryPort` resolves to `GrpcInventoryAdapter` with configured stub and channel beans.

## 8. When Should You Use an Adapter and When Should You Skip It?

| Scenario | Approach |
| --- | --- |
| Multiple business services need the same gRPC dependency | Create a shared port and adapter to centralize mapping/timeouts/transport. |
| Protobuf evolves frequently while domain contracts stay stable | Keep mapping inside the adapter to isolate change scope. |
| Need to fake dependencies in business logic tests | Inject a port and provide a fake implementation. |
| Small application, one simple use case, minimal business logic | Injecting a stub into a compact gateway may suffice; avoid creating layers just to pass through one line. |
| Multiple transports may swap in and out | Define one port with separate adapters for gRPC, REST, or local implementations. |

An adapter is not an end in itself. It pays off when it establishes a real boundary: converting types, translating errors, shielding the domain from protocol details, and keeping tests independent. If an adapter merely forwards every argument and response without adding value, consider keeping the structure simpler.

## 9. Common Design Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Business service imports generated Protobuf classes | Domain becomes locked to the gRPC contract. | Define types and ports in domain language. |
| Port throws `StatusRuntimeException` | Transport details leak across the boundary. | Adapter translates errors into semantic application exceptions. |
| Adapter returns raw `StockReply` | Business code must understand the Protobuf schema. | Map to `StockAvailability` or an appropriate application type. |
| One global mapper assigns identical meaning to every status | `NOT_FOUND` or `FAILED_PRECONDITION` gets misinterpreted across use cases. | Map per operation and business contract. |
| Adapter blindly retries every failure | Can duplicate write operations or exceed total deadlines. | Let retry policy account for idempotency and use-case rules. |
| Business service builds channels/stubs itself | Hard to control lifecycle and hard to test. | Let Spring manage channels/stubs; inject them into the adapter via constructor. |
| Business tests must boot a gRPC server | Slow tests that conflate transport errors with domain bugs. | Fake the port in unit tests; test the adapter separately. |

## 10. Practice Exercises

1. Define `InventoryPort` using application types such as `Sku` and `StockAvailability`, without importing generated gRPC packages.
2. Implement `GrpcInventoryAdapter` using `InventoryBlockingStub`, mapping Protobuf requests/responses and setting an appropriate deadline.
3. Map `NOT_FOUND`, `UNAVAILABLE`, `DEADLINE_EXCEEDED`, and unexpected errors into application exceptions preserving the cause.
4. Refactor the business service to depend solely on `InventoryPort`; verify no `io.grpc` or Protobuf imports remain in the business package.
5. Write business unit tests using a fake port and adapter tests using a gRPC in-process server.
6. Swap the gRPC adapter for a fake or alternative implementation in a Spring test context to confirm the business service is transport-independent.

After this lesson, you should recognize that the port belongs to the application, the adapter belongs to integration, and business services should depend only on the port. Protobuf conversion, deadline setting, gRPC status handling, and generated stub management live in the adapter/client infrastructure. That boundary lets Spring gRPC clients evolve protocols, simplify testing, and keep business rules stable.
