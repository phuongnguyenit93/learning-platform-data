# Mocking application services behind the adapter

**Chapter:** Testing basics  
**Scope:** Spring gRPC (SPRING_GRPC) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson focuses on unit testing a service adapter by mocking the application service/use case behind the adapter. Tests invoke the generated service implementation directly, use real generated requests, keep real validators and mappers, and verify that the adapter transforms data, calls the right use case, and terminates the response observer properly.

## 1. Why mock the application service behind the adapter?

The service adapter is the boundary between the gRPC protocol and the application layer. It receives a generated protobuf request, validates the request at the boundary, maps it to a command, calls the application service, and maps the result back to a generated response.

In adapter unit tests, the goal is to verify orchestration at this boundary. No database, HTTP server, or real downstream services are needed. Mocking the application port lets tests control the results and errors returned by the use case:

- When the request is valid, the adapter invokes the right use case with the mapped command.
- When the use case returns a result, the adapter builds the right protobuf response.
- When the use case throws a domain exception, the adapter maps it to a gRPC status according to policy.
- When the request is invalid, the adapter does not invoke the use case.
- Each RPC emits only one terminal signal: onCompleted() or onError().

Mocking only the dependency behind the adapter isolates the test while keeping the adapter, validator, and mapper real. If you also mock the mapper, validator, and response observer in excessive detail, the test may merely confirm that mocks were called without catching mapping bugs.

## 2. Distinguishing adapter unit tests from gRPC integration tests

| Test type | Real components | Components that can be mocked |
| --- | --- | --- |
| Adapter unit test | Generated request, adapter, validator, mapper, recording response observer | Application use case |
| In-process gRPC test | gRPC server/channel, generated stub, serialization, interceptor | Application use case or repository |
| Integration test | Spring context, gRPC transport, application service, and needed dependencies | Only dependencies outside the test scope |
| End-to-end test | Services and dependencies close to deployment environment | Usually minimal mocking to test real integration |

Adapter unit tests call service methods directly. They do not prove that protobuf bytes traversed HTTP/2, interceptors are registered, or TLS works. Those belong to in-process/transport/integration tests.

## 3. Example architecture

Suppose a client calls an RPC to create a payment. The adapter receives CreatePaymentRequest, the validator checks the request, the mapper creates CreatePaymentCommand, the use case processes it, and the response mapper creates CreatePaymentResponse.

~~~mermaid
sequenceDiagram
    participant T as Unit test
    participant A as PaymentGrpcService
    participant V as Request validator
    participant M as Request/response mapper
    participant U as Mock application use case
    participant O as Recording observer
    T->>A: createPayment(generated request, observer)
    A->>V: validate(request)
    V-->>A: no violations
    A->>M: toCommand(request)
    M-->>A: application command
    A->>U: create(command)
    U-->>A: application result
    A->>M: toProto(result)
    M-->>A: generated response
    A->>O: onNext(response)
    A->>O: onCompleted()
~~~

In the test, the validator and mapper are real implementations. The use case is mocked because it is the dependency the adapter must invoke. A recording observer captures responses and terminal events for assertions.

## 4. Declaring the application port and model

The application service should be represented via an interface that the adapter depends on:

~~~java
public record CreatePaymentCommand(
        String sourceAccountId,
        String destinationAccountId,
        long amountMinorUnits,
        String currency) {}

public record PaymentResult(String paymentId) {}

public interface CreatePaymentUseCase {
    PaymentResult create(CreatePaymentCommand command);
}
~~~

The adapter does not need to know whether the use case uses JDBC, an HTTP client, or an internal domain service. The test only needs to verify the command passed in and the result returned by the application port.

Keep application models independent of generated protobuf classes. That allows tests to catch missing fields or wrong value conversions in the mapper before business logic runs.

## 5. Adapter implementation under test

Example unary adapter:

~~~java
import io.grpc.stub.StreamObserver;
import java.util.List;

public class PaymentGrpcService
        extends PaymentServiceGrpc.PaymentServiceImplBase {

    private final PaymentRequestValidator validator;
    private final PaymentRequestMapper requestMapper;
    private final PaymentResponseMapper responseMapper;
    private final GrpcExceptionMapper exceptionMapper;
    private final CreatePaymentUseCase useCase;

    public PaymentGrpcService(
            PaymentRequestValidator validator,
            PaymentRequestMapper requestMapper,
            PaymentResponseMapper responseMapper,
            GrpcExceptionMapper exceptionMapper,
            CreatePaymentUseCase useCase) {
        this.validator = validator;
        this.requestMapper = requestMapper;
        this.responseMapper = responseMapper;
        this.exceptionMapper = exceptionMapper;
        this.useCase = useCase;
    }

    @Override
    public void createPayment(
            CreatePaymentRequest request,
            StreamObserver<CreatePaymentResponse> responseObserver) {
        List<FieldViolation> violations = validator.validate(request);
        if (!violations.isEmpty()) {
            responseObserver.onError(
                    exceptionMapper.map(
                            new RequestValidationException(violations)));
            return;
        }

        try {
            CreatePaymentCommand command =
                    requestMapper.toCommand(request);
            PaymentResult result = useCase.create(command);
            responseObserver.onNext(responseMapper.toProto(result));
            responseObserver.onCompleted();
        } catch (RuntimeException failure) {
            responseObserver.onError(exceptionMapper.map(failure));
        }
    }
}
~~~

This code illustrates the sequence: boundary validation → request mapping → application use case → response mapping → observer. In a real project, the adapter is typically registered as a Spring gRPC service bean per the active annotation/starter; unit tests do not need to start Spring to invoke this method.

## 6. Creating the test fixture with Mockito and JUnit 5

Use Mockito to mock the application port. Instantiate real validator, mapper, and exception mapper objects in setup:

~~~java
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PaymentGrpcServiceTest {

    @Mock
    private CreatePaymentUseCase useCase;

    private PaymentGrpcService service;

    @BeforeEach
    void setUp() {
        service = new PaymentGrpcService(
                new PaymentRequestValidator(),
                new PaymentRequestMapper(),
                new PaymentResponseMapper(),
                new GrpcExceptionMapper(new ValidationStatusFactory()),
                useCase);
    }
}
~~~

The constructor in the example should match your project's real dependencies. If a mapper or validator has dependencies, supply appropriate real ones or mock only those specific dependencies; do not turn the entire adapter setup into a collection of mocks.

### Using real generated requests

Build requests with generated builders:

~~~java
private CreatePaymentRequest validRequest() {
    return CreatePaymentRequest.newBuilder()
            .setSourceAccountId("account-A")
            .setDestinationAccountId("account-B")
            .setAmountMinorUnits(25_000)
            .setCurrency("USD")
            .build();
}
~~~

Do not mock CreatePaymentRequest. Generated protobuf messages have specific semantics for default values, field presence, repeated fields, and enums. Using real messages ensures tests verify how the mapper behaves at runtime.

## 7. Recording observer to check response lifecycle

For adapter unit tests, an event-recording observer is usually clearer than mocking StreamObserver:

~~~java
import io.grpc.stub.StreamObserver;
import java.util.ArrayList;
import java.util.List;

final class RecordingObserver<T> implements StreamObserver<T> {

    private final List<T> values = new ArrayList<>();
    private Throwable error;
    private boolean completed;
    private int terminalSignals;

    @Override
    public void onNext(T value) {
        if (terminalSignals > 0) {
            throw new AssertionError("onNext after terminal signal");
        }
        values.add(value);
    }

    @Override
    public void onError(Throwable failure) {
        terminalSignals++;
        error = failure;
    }

    @Override
    public void onCompleted() {
        terminalSignals++;
        completed = true;
    }

    List<T> values() {
        return List.copyOf(values);
    }

    Throwable error() {
        return error;
    }

    boolean completed() {
        return completed;
    }

    int terminalSignals() {
        return terminalSignals;
    }
}
~~~

This observer records responses and completion state. Asserting terminalSignals() == 1 catches adapters that call both onError() and onCompleted(), or terminate multiple times. For asynchronous code with concurrent callbacks, the test observer must be thread-safe or synchronized; the current example is for synchronous handlers.

## 8. Success test: verify the command sent to the use case

The most important test verifies that the adapter builds the right command, invokes the use case once, and returns the response mapped from the result:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

@Test
void mapsRequestCallsUseCaseAndReturnsResponse() {
    when(useCase.create(any(CreatePaymentCommand.class)))
            .thenReturn(new PaymentResult("payment-123"));

    RecordingObserver<CreatePaymentResponse> observer =
            new RecordingObserver<>();

    service.createPayment(validRequest(), observer);

    ArgumentCaptor<CreatePaymentCommand> commandCaptor =
            ArgumentCaptor.forClass(CreatePaymentCommand.class);
    verify(useCase, times(1)).create(commandCaptor.capture());

    CreatePaymentCommand command = commandCaptor.getValue();
    assertEquals("account-A", command.sourceAccountId());
    assertEquals("account-B", command.destinationAccountId());
    assertEquals(25_000, command.amountMinorUnits());
    assertEquals("USD", command.currency());

    assertEquals(1, observer.values().size());
    assertEquals("payment-123",
            observer.values().get(0).getPaymentId());
    assertNull(observer.error());
    assertTrue(observer.completed());
    assertEquals(1, observer.terminalSignals());
    verifyNoMoreInteractions(useCase);
}
~~~

Do not stop at verify(useCase).create(any()). ArgumentCaptor proves the adapter passes the accurately mapped data. If source account and destination account were swapped, or the amount converted to the wrong units, the test will catch it.

## 9. Invalid request test: use case is not called

An invalid request must terminate before invoking the application service:

~~~java
import io.grpc.Status;

@Test
void invalidRequestDoesNotInvokeApplicationUseCase() {
    CreatePaymentRequest invalid = CreatePaymentRequest.newBuilder()
            .setSourceAccountId("account-A")
            .setDestinationAccountId("account-A")
            .setAmountMinorUnits(-1)
            .setCurrency("usd")
            .build();
    RecordingObserver<CreatePaymentResponse> observer =
            new RecordingObserver<>();

    service.createPayment(invalid, observer);

    verifyNoInteractions(useCase);
    assertTrue(observer.values().isEmpty());
    assertNotNull(observer.error());
    assertEquals(
            Status.Code.INVALID_ARGUMENT,
            Status.fromThrowable(observer.error()).getCode());
    assertFalse(observer.completed());
    assertEquals(1, observer.terminalSignals());
}
~~~

This test verifies two things: the validator actually runs in the adapter path, and no side effects occur in the use case when the request fails contract validation. Testing the validator in isolation would not detect an adapter that accidentally calls the use case prior to validation.

## 10. Testing domain exceptions from the application service

When the use case throws a typed exception, the adapter must pass it through the mapper and terminate the RPC with the corresponding status:

~~~java
@Test
void mapsApplicationNotFoundFailureToGrpcStatus() {
    when(useCase.create(any(CreatePaymentCommand.class)))
            .thenThrow(new AccountNotFoundException());

    RecordingObserver<CreatePaymentResponse> observer =
            new RecordingObserver<>();

    service.createPayment(validRequest(), observer);

    verify(useCase, times(1)).create(any(CreatePaymentCommand.class));
    assertTrue(observer.values().isEmpty());
    assertEquals(
            Status.Code.NOT_FOUND,
            Status.fromThrowable(observer.error()).getCode());
    assertFalse(observer.completed());
    assertEquals(1, observer.terminalSignals());
}
~~~

This is an adapter orchestration test. Dedicated unit tests for the exception mapper still need to verify every exception type, rich error details, and trailers; the adapter test only needs to verify that the adapter uses the mapper and returns the right status for a representative case.

## 11. Checking unexpected errors

Internal exceptions must not leak straight to the response observer. If the use case throws an unclassified error, the exception mapper must return a safe status:

~~~java
@Test
void hidesUnexpectedApplicationFailureFromClient() {
    when(useCase.create(any(CreatePaymentCommand.class)))
            .thenThrow(new IllegalStateException(
                    "database password=secret"));

    RecordingObserver<CreatePaymentResponse> observer =
            new RecordingObserver<>();

    service.createPayment(validRequest(), observer);

    Status status = Status.fromThrowable(observer.error());
    assertEquals(Status.Code.INTERNAL, status.getCode());
    assertEquals("Internal server error", status.getDescription());
    assertFalse(status.getDescription().contains("secret"));
    assertEquals(1, observer.terminalSignals());
}
~~~

Exception details should be logged server-side under a redaction policy with a correlation/trace ID for investigation. Never use the exception message as the default status description.

## 12. Mock at the right boundary, avoid over-mocking

Mocking the application service is the goal of this lesson. Which components stay real depends on what the test needs to prove:

| Component | Recommendation in adapter unit tests | Reason |
| --- | --- | --- |
| Generated protobuf request | Use real object | Preserves protobuf semantics |
| Service adapter | Use real object | This is the unit under test |
| Request validator | Usually use real object | Verifies validation runs before the use case |
| Request/response mapper | Usually use real object | Verifies real mapping |
| Application use case | Mock | Isolates database/network and controls outcomes |
| Response observer | Recording observer | Verifies responses and terminal lifecycle |
| Database/HTTP client | Not needed | Implementation detail behind the use case |

If a mapper is complex and already has dedicated unit tests, an adapter test may mock the mapper to isolate orchestration. In that case, other tests must verify the real mapper. Avoid mocking every collaborator at once and only verifying call counts; such tests do not prove requests are mapped properly.

## 13. Testing adapters for server-streaming RPCs

For server-streaming, an application query may return a list or iterator; the adapter maps each element into a protobuf message. Mock the use case to check response order and count:

~~~java
@Test
void streamsApplicationResultsInOrder() {
    when(listPaymentsUseCase.list("customer-7"))
            .thenReturn(List.of(
                    new PaymentView("payment-1", 100),
                    new PaymentView("payment-2", 200)));

    RecordingObserver<PaymentMessage> observer =
            new RecordingObserver<>();

    service.listPayments(
            ListPaymentsRequest.newBuilder()
                    .setCustomerId("customer-7")
                    .build(),
            observer);

    assertEquals(2, observer.values().size());
    assertEquals("payment-1",
            observer.values().get(0).getPaymentId());
    assertEquals("payment-2",
            observer.values().get(1).getPaymentId());
    assertTrue(observer.completed());
    assertEquals(1, observer.terminalSignals());
    verify(listPaymentsUseCase).list("customer-7");
}
~~~

The test above demonstrates that the adapter emits the right responses and preserves order. If the production adapter uses an async publisher, database cursor, or backpressure, test cancellation, demand/readiness, and stopping the producer separately. Do not infer transport flow control solely from direct method-call tests.

## 14. Client-streaming: verify the use case runs only when the stream completes

For client-streaming, the adapter often receives multiple generated messages and invokes the application use case once the inbound stream ends. Tests can mock the batch use case and drive the inbound observer:

~~~java
@Test
void invokesBatchUseCaseAfterAllMessagesArrive() {
    when(uploadUseCase.finish(any(UploadCommand.class)))
            .thenReturn(new UploadResult(2));

    RecordingObserver<UploadSummary> response =
            new RecordingObserver<>();
    StreamObserver<UploadLine> requestObserver =
            service.upload(response);

    requestObserver.onNext(UploadLine.newBuilder()
            .setProductId("product-A")
            .setQuantity(1)
            .build());
    requestObserver.onNext(UploadLine.newBuilder()
            .setProductId("product-B")
            .setQuantity(1)
            .build());

    verifyNoInteractions(uploadUseCase);

    requestObserver.onCompleted();

    verify(uploadUseCase, times(1)).finish(any(UploadCommand.class));
    assertEquals(2, response.values().get(0).getAcceptedCount());
    assertTrue(response.completed());
    assertEquals(1, response.terminalSignals());
}
~~~

This pattern suits adapters accumulating a bounded batch. For large streams, do not buffer all messages in memory; use batch persistence or a streaming application port. Separately test stream cancellation, invalid messages, element count limits, and ensure the use case does not run without valid terminal completion.

## 15. Async use cases: controlling completion in tests

If the application service returns a CompletionStage or CompletableFuture, do not use Thread.sleep() to wait for the response. Create a controllable future in the test:

~~~java
@Test
void completesRpcWhenApplicationFutureCompletes() {
    CompletableFuture<PaymentResult> pending =
            new CompletableFuture<>();
    when(asyncUseCase.create(any(CreatePaymentCommand.class)))
            .thenReturn(pending);

    RecordingObserver<CreatePaymentResponse> observer =
            new RecordingObserver<>();

    asyncService.createPayment(validRequest(), observer);

    assertTrue(observer.values().isEmpty());
    assertEquals(0, observer.terminalSignals());

    pending.complete(new PaymentResult("payment-async-9"));

    assertEquals(
            "payment-async-9",
            observer.values().get(0).getPaymentId());
    assertTrue(observer.completed());
    assertEquals(1, observer.terminalSignals());
}
~~~

If callbacks run on another executor, the observer must be thread-safe and the test must wait for callbacks using a latch/future with a timeout. Add cases for future exceptional completion, cancellation, and races between completion and client cancellation. Never make tests depend on wall-clock time via fixed sleeps.

## 16. What adapter unit tests do not prove

Calling service methods directly does not verify:

- Protobuf serialization/deserialization over the wire.
- HTTP/2 framing, Netty event loops, and TLS handshakes.
- Interceptor registration, metadata propagation, or authentication chains.
- Deadlines actually propagated across the channel.
- Load balancing, retry policies, and service discovery.
- Transport-level streaming flow control.

Add in-process gRPC tests for stubs/channels/servers and appropriate integration tests for transport/security. Each test layer answers a different question; there is no need to turn every unit test into a full application boot.

## 17. Test matrix for adapters with mocked application services

| Scenario | Mock setup | What to verify |
| --- | --- | --- |
| Successful unary | Use case returns result | Correct command, correct response, called once |
| Invalid request | No use case stub needed | Use case not called, status INVALID_ARGUMENT |
| Domain not found | Use case throws domain exception | Status NOT_FOUND, no success response |
| Dependency unavailable | Use case throws dependency exception | Status UNAVAILABLE per mapper |
| Unexpected error | Use case throws runtime exception | Safe status INTERNAL |
| Server streaming | Query returns multiple elements | Responses in order, completed once |
| Client streaming | Batch use case stubbed | Only invoked after valid onCompleted() |
| Async use case | Returns pending future | Observer not finished before completion; finished afterward |
| Cancellation | Cancel call/stream | No further responses emitted or new side effects invoked per policy |

Not every service needs every case. Choose tests matching the RPC shape and actual adapter behavior.

## 18. Common anti-patterns

- **Mocking generated protobuf requests:** loses builder, default, and field presence semantics.
- **Mocking the adapter and verifying its methods:** does not test adapter logic.
- **Mocking both validator and mapper in every test:** misses validation/mapping bugs at the boundary.
- **Using a real database in adapter unit tests:** slows down tests and introduces environment dependencies.
- **Only verifying the use case was called:** fails to confirm the command passed in is correct.
- **Not checking the response observer:** misses adapters forgetting onCompleted() or calling terminal signals multiple times.
- **Using sleep for async tests:** creates flaky and slow tests.
- **Confusing unit tests with in-process tests:** misses transport/interceptor errors.
- **Not testing invalid requests:** bad requests may trigger side effects before being rejected.

## 19. Self-practice

1. Why should adapter unit tests mock the application use case while using real generated requests?
2. How do you use ArgumentCaptor to verify the command passed to the use case?
3. Design a test proving that an invalid request does not call the application service.
4. For server-streaming, how should you verify response ordering and terminal signals?
5. For client-streaming, why is the use case typically invoked only after the inbound stream completes?
6. An async use case returns a pending future. How do you verify the observer has not completed before the future resolves?
7. Which behaviors require in-process or transport integration tests instead of adapter unit tests?

**Remember:** Mock the application service behind the adapter to control results and errors, while keeping the adapter, generated requests, validator, and mapper real to verify orchestration. Use ArgumentCaptor to verify commands, a recording observer to verify responses and terminal lifecycle, and verify that invalid requests cause no side effects. For streaming/async, explicitly control messages and completion; use in-process/integration tests for transport, interceptors, TLS, and flow control.
