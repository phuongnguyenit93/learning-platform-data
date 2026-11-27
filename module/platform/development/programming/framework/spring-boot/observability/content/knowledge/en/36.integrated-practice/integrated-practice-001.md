# Creating a Custom Observation for a Use Case

In the **SPRING_BOOT_OBSERVABILITY** module, Micrometer Observation provides a unified API to record application activity and connect that data to metrics, logs, and distributed tracing. Spring Boot already integrates instrumentation for many components such as the HTTP server, HTTP client, and certain data access libraries. However, these technical instrumentations do not fully capture business semantics. A use case such as creating an order, reserving inventory, or confirming a payment needs its own observation so that teams understand which business operation is running and how long it takes.

This practice exercise builds a custom observation for the create-reservation use case in an inventory system. The observation wraps the business boundary, uses a stable name, attaches attributes with appropriate cardinality, and lets ObservationRegistry forward data to configured handlers. The same approach can be applied to other use cases in Spring Boot.

## 1. Choosing the Right Boundary to Observe

Before writing code, identify which activity actually provides operational value. For the reservation creation flow, a request may pass through these steps:

1. The REST controller receives the create-reservation command.
2. The use case validates information and orchestrates business logic.
3. The inventory gateway calls the data store or another inventory service.
4. The use case returns the result to the controller.

Spring Boot may already create observations for the HTTP request and the HTTP client. A custom observation should describe the business step owned by the application, for example **inventory.reservation.create**. As a result, the trace can display both the HTTP request and the reservation creation activity inside that request.

Avoid creating a custom observation just to duplicate the entire duration of the HTTP request. Choose a boundary with independent meaning that may require latency measurement, outcome classification, or error investigation. If a use case calls multiple components, the business observation can become the parent span for technical spans produced by client or repository instrumentation.

A good name must remain stable across deployments. Use a name that describes the domain and action; do not embed order IDs, SKUs, URLs, or request data into the name.

## 2. Choosing the Name and Attributes for the Observation

For the create-reservation use case, the following details can be defined:

| Component | Example Value | Purpose |
| --- | --- | --- |
| Observation name | inventory.reservation.create | Identify the type of business operation |
| Contextual name | create inventory reservation | Make the trace easier to read |
| Low-cardinality key | inventory.channel | Group by web, mobile, or partner |
| High-cardinality key | order.id | Help locate a specific execution in traces |

Observation name and contextual name serve different roles. The observation name is a stable identifier used in conventions and handlers. The contextual name provides a more human-readable description for someone viewing the trace.

Low-cardinality key-values must have a finite, controlled set of values. For example, a sales channel only has the values web, mobile, and partner. These attributes are suitable for grouping metrics. High-cardinality key-values such as order.id can have a huge number of values; use them only when the tracing backend needs that attribute to investigate a specific trace. Do not put dynamic IDs into metric labels.

Do not put sensitive data such as access tokens, passwords, email addresses, phone numbers, or payment data into an observation. High-cardinality does not mean you can store arbitrary data.

## 3. Preparing Dependencies and ObservationRegistry

For a Spring Boot application, add Actuator to use the observability capabilities integrated by Spring Boot. Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

To export metrics, the application needs to add a registry matching the backend in use, such as the Micrometer Prometheus registry. To export distributed traces, a corresponding tracing bridge and exporter are needed, such as the Micrometer Tracing bridge for OpenTelemetry along with OTLP configuration. Specific dependencies depend on the project's backend and Spring Boot version.

In a Spring Boot configuration with Actuator, ObservationRegistry is provided via auto-configuration. Inject the Spring-managed registry into the use case. Do not create a separate ObservationRegistry per request or per service, because observations need to pass through the same handler pipeline and context propagation of the application.

Constructor injection example:

~~~java
@Service
public class CreateReservationUseCase {

    private final ObservationRegistry observationRegistry;
    private final InventoryGateway inventoryGateway;

    public CreateReservationUseCase(
            ObservationRegistry observationRegistry,
            InventoryGateway inventoryGateway) {
        this.observationRegistry = observationRegistry;
        this.inventoryGateway = inventoryGateway;
    }
}
~~~

Imports in the example are omitted to focus on the observability part. In project code, use the actual packages of the existing domain models and gateways.

## 4. Creating a Custom Observation for the Use Case

First, define the input data and result of the use case. This example assumes the domain already has the corresponding data types:

~~~java
public record ReservationCommand(
        String orderId,
        String sku,
        int quantity,
        SalesChannel channel) {
}

public record ReservationResult(
        String reservationId,
        ReservationStatus status) {
}
~~~

InventoryGateway represents the gateway communicating with the data store or inventory service:

~~~java
public interface InventoryGateway {

    ReservationResult reserve(
            String orderId,
            String sku,
            int quantity);
}
~~~

Create the observation right at the boundary of the use case:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class CreateReservationUseCase {

    private final ObservationRegistry observationRegistry;
    private final InventoryGateway inventoryGateway;

    public CreateReservationUseCase(
            ObservationRegistry observationRegistry,
            InventoryGateway inventoryGateway) {
        this.observationRegistry = observationRegistry;
        this.inventoryGateway = inventoryGateway;
    }

    public ReservationResult execute(ReservationCommand command) {
        return Observation
                .createNotStarted(
                        "inventory.reservation.create",
                        observationRegistry)
                .contextualName("create inventory reservation")
                .lowCardinalityKeyValue(
                        "inventory.channel",
                        command.channel().name().toLowerCase(Locale.ROOT))
                .highCardinalityKeyValue("order.id", command.orderId())
                .observe(() -> inventoryGateway.reserve(
                        command.orderId(),
                        command.sku(),
                        command.quantity()));
    }
}
~~~

The key part is the chain that creates the observation and calls **observe**. The API manages the observation lifecycle for the supplier: starting the observation, opening a scope while the business logic runs, recording an error if the supplier throws an exception, and stopping the observation when the supplier completes. As a result, you do not need to write try/finally manually to close the observation in the standard case.

The name **inventory.reservation.create** does not change with orderId or sku. The sales channel is recorded as a low-cardinality key-value because the enum's value set is controlled. order.id is recorded as a high-cardinality key-value to support trace investigation if the tracing handler and backend are configured to accept this attribute.

The example above assumes SalesChannel is an enum controlled by the application. Use Locale.ROOT when converting the enum to lowercase to avoid host locale-dependent results.

## 5. How Observation Works with Technical Layers

When the use case runs within the observation's scope, instrumentations invoked inside can continue using the current context. If InventoryGateway uses an instrumented HTTP client, the client observation can become a child span of the business observation. If the gateway accesses the database through an instrumented library, the database span can also appear in the same trace.

An illustrative trace:

~~~text
HTTP POST /reservations
└── inventory.reservation.create
    └── HTTP inventory-service
        └── database query
~~~

This is an illustrative relationship; actual spans depend on the libraries, handlers, and exporters configured. If the gateway calls an uninstrumented service, the custom observation still records the overall duration of the use case, but it does not automatically create details for individual operations inside the gateway.

ObservationRegistry coordinates the registered ObservationHandlers. A registry may have a handler that creates meters, a handler that creates spans, or custom handlers. Creating an observation via the API does not by itself guarantee data is exported to a backend: the application must have the corresponding handlers and exporters.

In a configuration with a metrics handler, an observation can be mapped to a timer or meter according to conventions. In a tracing configuration, an observation can become a span. Logs can correlate trace ID/span ID when logging and tracing integration is enabled. Each signal has its own mapping rules, so verify the actual output of the system.

## 6. Handling Business Outcomes and Errors

The Observation API automatically records exceptions thrown inside the supplier passed to observe and ends the observation lifecycle before propagating the exception to the caller. Therefore, if InventoryGateway throws an exception when the inventory service is unreachable, the tracing handler can receive the error information and the span reflects the appropriate status according to configuration.

Not every unsuccessful business outcome is an exception. For example, being out of stock can be a valid use case outcome with status REJECTED. If you need to analyze outcomes such as SUCCESS, REJECTED, or RETRYABLE, represent them with a low-cardinality key-value that has a finite set of values. Only add the attribute after the outcome has been determined and before the observation stops; when you need precise control over this timing, you can manage the lifecycle using start, openScope, and stop inside try/finally.

Example classification rules:

| Outcome | Suggested Low-Cardinality Value |
| --- | --- |
| Reservation created successfully | success |
| Insufficient inventory | rejected |
| Inventory service temporarily unavailable | unavailable |

Do not put exception messages, stack traces, orderId, or SKU into low-cardinality key-values. Highly variable data will cause cardinality to spike if used as metric labels. Detailed error content should be recorded via controlled logs and span events/attributes in accordance with data policy.

## 7. When Is a Custom Observation.Context or Convention Needed?

The example above uses the direct API because the use case only needs a name, contextual name, and a few simple key-values. When multiple use cases share the same structure or need to share naming logic, you can build a custom context and convention.

A custom context is appropriate when an observation needs to carry structured business data throughout its lifecycle, such as reservation type, sales channel, and processing outcome. A convention centralizes how data in the context is converted into observation name, contextual name, low-cardinality key-values, and high-cardinality key-values.

When building a convention:

- Only put attributes with a finite value domain into low-cardinality key-values.
- Keep the observation name stable, independent of IDs or request content.
- Use high-cardinality key-values selectively and comply with data policies.
- Use supportsContext so the convention applies only to its matching context type.
- Reuse a convention when multiple use cases share the same semantics; avoid creating a catch-all convention that is hard to control.

Do not create a custom context or convention just to change one observation name. Start with the direct API, then extract a convention when a clear need for sharing emerges.

## 8. Testing a Custom Observation

Testing the use case should verify both the business outcome and that the observation is created with the expected name. You can use a standalone ObservationRegistry in a unit test and register a simple handler to capture observation names:

~~~java
ObservationRegistry registry = ObservationRegistry.create();
List<String> observationNames = new ArrayList<>();

registry.observationConfig().observationHandler(
        new ObservationHandler<Observation.Context>() {
            @Override
            public boolean supportsContext(Observation.Context context) {
                return true;
            }

            @Override
            public void onStart(Observation.Context context) {
                observationNames.add(context.getName());
            }
        });

CreateReservationUseCase useCase =
        new CreateReservationUseCase(registry, inventoryGateway);

useCase.execute(command);

assertThat(observationNames)
        .contains("inventory.reservation.create");
~~~

This snippet is an illustrative body of a JUnit test; declare the appropriate fixtures, mock InventoryGateway, and imports in your project. You can extend the handler to inspect low-cardinality key-values and verify that the observation is stopped after the use case completes.

Additional test cases to include:

1. The use case returns a successful result and the gateway is called with the right arguments.
2. The gateway throws an exception; the exception is propagated to the caller and the observation still finishes.
3. Calling the same use case with different orderIds and SKUs; the observation name remains unchanged.
4. Changing the channel across enum values; the low-cardinality value accurately reflects the channel.
5. Verifying that dynamic IDs do not appear in low-cardinality key-values.

Unit tests confirm that the application creates observations. Integration tests confirm that the configured handlers and exporters actually send meters or spans to the backend. When running integration tests, verify that the trace contains the business span, technical spans have proper parent-child relationships, and attributes appear on the right signal types.

## 9. Verifying in the Runtime Environment

After integrating the custom observation, execute a create-reservation request and check each signal in turn:

- **Metrics:** find the timer or meter matching the observation's convention; verify that tags only contain values with controlled cardinality.
- **Traces:** find the business span with the stable name and check child spans for the HTTP client or database if those components are instrumented.
- **Logs:** confirm that logs within the execution scope carry trace ID/span ID when correlation is configured.
- **Errors:** trigger a gateway failure scenario in a test environment and confirm the span reflects the error while execution duration is still recorded.
- **Cardinality:** send multiple requests with different orderIds and SKUs; confirm that the number of metric series does not grow with the number of IDs.

If metrics appear but traces are missing, check the tracing handler, bridge, exporter, endpoint, and sampling probability. If the trace has the business span but lacks child spans, check gateway instrumentation and context propagation. If no signals appear at all, check whether ObservationRegistry has matching handlers and whether dependencies/configurations have been loaded.

Sampling may cause some traces not to be exported even though the observation still ran. Therefore, do not conclude a custom observation is broken from the absence of a single trace. Use a test handler to verify the observation lifecycle and metrics to monitor overall behavior; then inspect traces with an appropriate sampling rate in a test environment.

## 10. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Naming the observation with orderId or SKU | Creates many metric series and makes aggregation difficult | Use a fixed business name |
| Putting an ID into a low-cardinality key | Cardinality spikes sharply | Move to high-cardinality if traces truly need it |
| Creating a new registry in each use case | Does not share handlers and context | Inject the Spring-managed ObservationRegistry |
| Creating an observation duplicating HTTP instrumentation | Trace has redundant spans and metrics are hard to interpret | Choose a meaningful business boundary |
| Forgetting to stop the observation when managing lifecycle manually | Scope or span may leak | Use observe or try/finally with stop |
| Assuming creating an observation equals exporting it | No data in backend when handlers/exporters are missing | Check handlers, bridge, and exporter |
| Using sensitive data as attributes | Risk of leaking data in telemetry | Filter, mask, or remove sensitive data |

## 11. Finalizing the Use Case According to Team Conventions

When bringing custom observations to production, align names and key-values with the teams owning related services. An observation catalog should document the name, business meaning, instrumentation location, allowed low-cardinality keys, and owner. This helps dashboards, alerts, and trace queries stay consistent across releases.

A good custom observation has three traits: it describes the right business boundary, provides sufficient attributes for analysis, and keeps cardinality within operational limits. Start from a concrete use case, use the Observation API with the Spring Boot-managed registry, and verify metrics, traces, and logs at the output. Only extract a shared context or convention when multiple use cases share the same representation.
