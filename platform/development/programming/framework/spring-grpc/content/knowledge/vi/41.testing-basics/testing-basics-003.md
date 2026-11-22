# Mock application service phía sau adapter

**Chương:** Testing basics  
**Phạm vi:** Spring gRPC (SPRING_GRPC) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này tập trung vào unit test service adapter bằng cách mock application service/use case phía sau adapter. Test gọi trực tiếp generated service implementation, dùng generated request thật, giữ validator và mapper thật, rồi xác nhận adapter chuyển dữ liệu, gọi đúng use case và kết thúc response observer đúng cách.

## 1. Vì sao mock application service phía sau adapter?

Service adapter là ranh giới giữa giao thức gRPC và application layer. Nó nhận generated protobuf request, kiểm tra request ở boundary, chuyển thành command, gọi application service rồi chuyển kết quả thành generated response.

Trong unit test adapter, mục tiêu là xác nhận phần điều phối ở ranh giới này. Không cần database, HTTP server hoặc service phụ thuộc thật. Mock application port giúp test kiểm soát kết quả và lỗi do use case trả về:

- Khi request hợp lệ, adapter gọi đúng use case với command đã map.
- Khi use case trả kết quả, adapter tạo đúng protobuf response.
- Khi use case ném domain exception, adapter chuyển thành gRPC status theo policy.
- Khi request không hợp lệ, adapter không gọi use case.
- Mỗi RPC chỉ phát một terminal signal: onCompleted() hoặc onError().

Mock đúng dependency phía sau adapter giúp cô lập test mà vẫn giữ phần adapter, validator và mapper thật. Nếu mock cả mapper, validator và response observer theo cách quá chi tiết, test có thể chỉ xác nhận các mock đã được gọi mà không phát hiện mapping sai.

## 2. Phân biệt adapter unit test và gRPC integration test

| Loại test | Thành phần thật | Thành phần có thể mock |
| --- | --- | --- |
| Adapter unit test | Generated request, adapter, validator, mapper, response observer ghi nhận | Application use case |
| In-process gRPC test | gRPC server/channel, generated stub, serialization, interceptor | Application use case hoặc repository |
| Integration test | Spring context, gRPC transport, application service và dependency cần thiết | Chỉ các dependency ngoài phạm vi test |
| End-to-end test | Các service và dependency gần môi trường triển khai | Thường hạn chế mock để kiểm tra tích hợp thực |

Adapter unit test gọi method service trực tiếp. Nó không chứng minh protobuf bytes đã đi qua HTTP/2, interceptor đã được đăng ký hoặc TLS hoạt động. Những điều đó thuộc in-process/transport/integration test.

## 3. Kiến trúc ví dụ

Giả sử client gọi RPC tạo thanh toán. Adapter nhận CreatePaymentRequest, validator kiểm tra request, mapper tạo CreatePaymentCommand, use case xử lý và response mapper tạo CreatePaymentResponse.

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

Trong test, validator và mapper là implementation thật. Use case là mock vì đó là dependency mà adapter cần gọi. Recording observer thu nhận response và terminal event để assertion.

## 4. Khai báo application port và model

Application service nên được biểu diễn qua interface mà adapter phụ thuộc vào:

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

Adapter không cần biết use case dùng JDBC, HTTP client hay một domain service nào bên trong. Test chỉ cần kiểm tra command truyền vào và kết quả mà application port trả về.

Giữ application model độc lập với generated protobuf class. Nhờ đó test có thể phát hiện mapper thiếu field hoặc chuyển sai giá trị trước khi logic nghiệp vụ chạy.

## 5. Adapter implementation được kiểm thử

Ví dụ adapter unary:

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

Đoạn code minh họa thứ tự boundary validation → request mapping → application use case → response mapping → observer. Trong dự án thực tế, adapter thường được đăng ký như Spring gRPC service bean theo annotation/starter đang dùng; unit test không cần khởi động Spring để gọi method này.

## 6. Tạo fixture test với Mockito và JUnit 5

Dùng Mockito để mock application port. Tạo validator, mapper và exception mapper thật trong setup:

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

Constructor trong ví dụ cần khớp với dependency thật của dự án. Nếu mapper hoặc validator có dependency, cung cấp dependency thật phù hợp hoặc mock riêng dependency đó; không biến toàn bộ adapter thành một tập mock.

### Dùng generated request thật

Tạo request bằng generated builder:

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

Không mock CreatePaymentRequest. Generated protobuf message có semantics riêng cho default value, field presence, repeated fields và enum. Dùng message thật giúp test kiểm tra đúng cách mapper sẽ hoạt động lúc runtime.

## 7. Recording observer để kiểm tra response lifecycle

Với adapter unit test, một observer ghi nhận sự kiện thường rõ ràng hơn mock StreamObserver:

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

Observer này lưu các response và trạng thái kết thúc. Assertion terminalSignals() == 1 giúp phát hiện adapter gọi cả onError() lẫn onCompleted(), hoặc kết thúc nhiều lần. Với code bất đồng bộ có callback đồng thời, test observer cần thread-safe hoặc đồng bộ hóa; ví dụ hiện tại dành cho handler đồng bộ.

## 8. Test thành công: verify command được gửi tới use case

Test quan trọng nhất kiểm tra adapter tạo đúng command, gọi use case một lần và trả response được map từ kết quả:

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

Không chỉ xác nhận verify(useCase).create(any()). ArgumentCaptor chứng minh adapter truyền đúng dữ liệu đã map. Nếu source account và destination account bị đảo, hoặc amount bị chuyển sai đơn vị, test sẽ phát hiện.

## 9. Test request không hợp lệ: use case không được gọi

Request sai phải kết thúc trước khi gọi application service:

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

Test này xác nhận cả hai điều: validator thực sự chạy trong adapter path và không có side effect từ use case khi request không đạt hợp đồng. Nếu test chỉ gọi validator riêng, nó không phát hiện adapter vô tình gọi use case trước validation.

## 10. Test domain exception từ application service

Khi use case ném exception có kiểu cụ thể, adapter phải đưa exception qua mapper và kết thúc RPC bằng status tương ứng:

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

Đây là test adapter orchestration. Unit test riêng cho exception mapper vẫn cần xác nhận từng exception type, rich error details và trailers; adapter test chỉ cần xác nhận adapter sử dụng mapper và trả đúng status cho tình huống đại diện.

## 11. Kiểm tra lỗi không dự kiến

Không nên để exception nội bộ đi thẳng ra response observer. Nếu use case ném lỗi không được phân loại, exception mapper phải trả status an toàn:

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

Chi tiết exception cần được ghi log phía server theo chính sách redaction và có correlation/trace ID để điều tra. Không dùng exception message làm status description mặc định.

## 12. Mock đúng ranh giới, tránh over-mocking

Mock application service là mục tiêu của bài này. Những thành phần nào nên giữ thật phụ thuộc vào điều test cần chứng minh:

| Thành phần | Khuyến nghị trong adapter unit test | Lý do |
| --- | --- | --- |
| Generated protobuf request | Dùng object thật | Giữ đúng protobuf semantics |
| Service adapter | Dùng object thật | Đây là đối tượng đang kiểm thử |
| Request validator | Thường dùng thật | Xác nhận validation được gọi trước use case |
| Request/response mapper | Thường dùng thật | Kiểm tra mapping thực tế |
| Application use case | Mock | Cô lập database/network và kiểm soát kết quả |
| Response observer | Recording observer | Kiểm tra response và terminal lifecycle |
| Database/HTTP client | Không cần tạo | Thuộc implementation phía sau use case |

Nếu mapper phức tạp và đã có unit test riêng, adapter test có thể mock mapper để cô lập orchestration. Khi đó phải có test khác xác nhận mapper thật. Tránh mock cùng lúc mọi collaborator rồi chỉ verify số lần gọi; test như vậy không chứng minh request được map đúng.

## 13. Kiểm thử adapter cho server-streaming RPC

Với server-streaming, application query có thể trả danh sách hoặc iterator; adapter map từng phần tử thành protobuf message. Mock use case để kiểm tra thứ tự và số lượng response:

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

Test trên minh họa adapter phát đúng response và giữ thứ tự. Nếu production adapter dùng async publisher, database cursor hoặc backpressure, cần test riêng cancellation, demand/readiness và việc dừng producer. Không suy ra transport flow control chỉ từ test gọi method trực tiếp.

## 14. Client-streaming: xác nhận use case chỉ được gọi khi stream hoàn tất

Với client-streaming, adapter thường nhận nhiều generated messages rồi gọi application use case khi inbound stream kết thúc. Test có thể mock batch use case và điều khiển observer đầu vào:

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

Đây là mẫu cho adapter tích lũy một batch có giới hạn. Với stream lớn, không gom toàn bộ message vào memory; dùng batch persistence hoặc streaming application port. Cần test riêng stream bị hủy, message invalid, giới hạn số phần tử và bảo đảm use case không chạy khi chưa có terminal completion hợp lệ.

## 15. Async use case: điều khiển completion trong test

Nếu application service trả CompletionStage hoặc CompletableFuture, không dùng Thread.sleep() để chờ response. Test tạo future có thể điều khiển:

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

Nếu callback chạy trên executor khác, observer cần thread-safe và test phải chờ callback bằng latch/future có timeout. Bổ sung ca future exceptional completion, cancellation và race giữa completion với client cancellation. Không để test phụ thuộc thời gian máy bằng sleep cố định.

## 16. Những điều adapter unit test không chứng minh

Gọi trực tiếp service method không kiểm tra:

- Protobuf serialization/deserialization qua wire.
- HTTP/2 framing, Netty event loop và TLS handshake.
- Đăng ký interceptor, metadata propagation hoặc authentication chain.
- Deadline thực sự được truyền qua channel.
- Load balancing, retry policy và service discovery.
- Streaming flow control ở transport.

Hãy bổ sung in-process gRPC test cho stub/channel/server và integration test phù hợp cho transport/security. Mỗi tầng test trả lời một câu hỏi khác nhau; không cần biến mọi unit test thành full application boot.

## 17. Ma trận test adapter với mocked application service

| Kịch bản | Setup mock | Điều cần xác nhận |
| --- | --- | --- |
| Unary thành công | Use case trả result | Command đúng, response đúng, gọi một lần |
| Request invalid | Không cần stub use case | Use case không được gọi, status INVALID_ARGUMENT |
| Domain not found | Use case ném exception domain | Status NOT_FOUND, không có response thành công |
| Dependency unavailable | Use case ném exception dependency | Status UNAVAILABLE theo mapper |
| Lỗi không dự kiến | Use case ném runtime exception | Status INTERNAL an toàn |
| Server streaming | Query trả nhiều phần tử | Response đúng thứ tự, completion một lần |
| Client streaming | Batch use case được stub | Chỉ gọi sau onCompleted() hợp lệ |
| Async use case | Trả future đang pending | Observer chưa kết thúc trước completion; kết thúc sau đó |
| Cancellation | Hủy call/stream | Không tiếp tục phát response hoặc gọi side effect mới theo policy |

Không phải mọi service đều cần tất cả ca. Chọn test theo RPC shape và behavior thật của adapter.

## 18. Anti-pattern thường gặp

- **Mock generated protobuf request:** làm mất semantics của builder, default và field presence.
- **Mock adapter rồi verify method:** không kiểm thử logic adapter.
- **Mock cả validator và mapper trong mọi test:** bỏ sót lỗi validation/mapping ở boundary.
- **Dùng database thật trong adapter unit test:** làm test chậm và phụ thuộc môi trường.
- **Chỉ verify use case được gọi:** không xác nhận command truyền vào đúng.
- **Không kiểm tra response observer:** bỏ sót adapter quên onCompleted() hoặc gọi terminal nhiều lần.
- **Dùng sleep cho async test:** tạo test chập chờn và chậm.
- **Nhầm unit test với in-process test:** không phát hiện lỗi transport/interceptor.
- **Không test invalid request:** request sai có thể tạo side effect trước khi bị từ chối.

## 19. Tự luyện tập

1. Vì sao adapter unit test nên mock application use case nhưng dùng generated request thật?
2. Dùng ArgumentCaptor để kiểm tra command truyền vào use case như thế nào?
3. Thiết kế test chứng minh request invalid không gọi application service.
4. Với server-streaming, cần kiểm tra thứ tự response và terminal signal ra sao?
5. Với client-streaming, tại sao use case thường chỉ được gọi sau khi inbound stream hoàn tất?
6. Một async use case trả future pending. Làm thế nào kiểm tra observer chưa hoàn tất trước khi future được resolve?
7. Những behavior nào cần in-process hoặc transport integration test thay vì adapter unit test?

**Ghi nhớ:** Mock application service phía sau adapter để kiểm soát kết quả và lỗi, trong khi giữ adapter, generated request, validator và mapper thật để kiểm tra orchestration. Dùng ArgumentCaptor xác nhận command, recording observer xác nhận response và terminal lifecycle, kiểm tra invalid request không tạo side effect. Với streaming/async, điều khiển rõ message và completion; dùng in-process/integration test cho transport, interceptor, TLS và flow control.
