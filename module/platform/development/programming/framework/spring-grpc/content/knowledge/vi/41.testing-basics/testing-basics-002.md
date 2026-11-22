# Unit test validation và status mapping

**Chương:** Testing basics  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này tập trung vào unit test cho hai trách nhiệm ở biên service: kiểm tra generated request và ánh xạ exception thành gRPC status. Test cần chứng minh request sai bị từ chối có thể dự đoán, status code/details đúng hợp đồng, status gRPC đã có được bảo toàn và lỗi nội bộ không bị lộ cho client.

## 1. Vì sao phải test validation và status mapping riêng?

Một request protobuf có thể parse thành công nhưng vẫn không hợp lệ theo API. Ví dụ amount bị thiếu, currency sai định dạng hoặc hai account ID giống nhau. Service adapter phải kiểm tra request trước khi gọi use case.

Khi validation thất bại, adapter cần chuyển các vi phạm thành một kết quả gRPC nhất quán, thường là `INVALID_ARGUMENT`. Khi use case ném lỗi, exception mapper cần chọn status phù hợp như `NOT_FOUND`, `FAILED_PRECONDITION`, `PERMISSION_DENIED` hoặc `UNAVAILABLE`. Lỗi không dự kiến cần được ánh xạ thành `INTERNAL` với mô tả an toàn.

Nếu không test riêng hai thành phần:

- Validator có thể bỏ sót field presence hoặc chấp nhận dữ liệu sai.
- Exception mapper có thể đổi nhầm lỗi domain thành `INTERNAL`.
- Một `StatusRuntimeException` đã có trailers có thể bị ghi đè và mất metadata.
- Client có thể nhận stack trace, SQL, token hoặc exception message nội bộ.
- Thay đổi câu chữ description có thể vô tình làm hỏng client nếu client parse text thay vì đọc status/details.

Unit test cho validator và mapper giúp khóa chặt quy tắc này mà không cần khởi động Spring context hoặc gRPC server.

## 2. Phân chia trách nhiệm trước khi viết test

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| Request validator | Kiểm tra presence, format, range, collection và quan hệ field | Truy vấn database hoặc quyết định trạng thái tài khoản |
| Application/domain | Kiểm tra invariant và trạng thái hiện tại | Phụ thuộc gRPC generated exception |
| Exception mapper | Chuyển exception đã phân loại thành gRPC status/details | Trả exception message tùy ý cho client |
| Service adapter | Gọi validator, map request, gọi use case và kết thúc RPC | Lặp logic mapping status ở từng method |

Boundary validation trả danh sách vi phạm có cấu trúc. Exception mapper nhận exception có kiểu cụ thể và quyết định status. Tách hai trách nhiệm giúp test xác định lỗi nằm ở validation hay status mapping.

## 3. Ví dụ protobuf request

Giả sử service tạo lệnh thanh toán:

~~~proto
syntax = "proto3";

package payments.v1;
option java_package = "com.example.payments.grpc";
option java_multiple_files = true;

service PaymentService {
  rpc CreatePayment(CreatePaymentRequest)
      returns (CreatePaymentResponse);
}

message CreatePaymentRequest {
  string source_account_id = 1;
  string destination_account_id = 2;
  optional int64 amount_minor_units = 3;
  string currency = 4;
  repeated string tags = 5;
}

message CreatePaymentResponse {
  string payment_id = 1;
}
~~~

Field `amount_minor_units` là `optional`, vì vậy generated request có `hasAmountMinorUnits()`. Validator có thể phân biệt field bị thiếu với field được gửi có giá trị 0. Các message được tạo bằng generated builder để test dùng đúng protobuf semantics.

## 4. Biểu diễn validation violation

Một violation nên chỉ ra field path và mô tả ngắn. Không gắn giá trị nhạy cảm của request vào lỗi:

~~~java
public record FieldViolation(
        String field,
        String description) {}
~~~

Exception chứa danh sách violations bất biến:

~~~java
import java.util.List;

public final class RequestValidationException
        extends RuntimeException {

    private final List<FieldViolation> violations;

    public RequestValidationException(
            List<FieldViolation> violations) {
        super("Request validation failed");
        this.violations = List.copyOf(violations);
    }

    public List<FieldViolation> violations() {
        return violations;
    }
}
~~~

Việc dùng `List.copyOf()` ngăn code gọi sửa danh sách sau khi exception được tạo. Message exception mang tính tổng quát; field-specific details được giữ trong `violations`.

## 5. Viết request validator

Validator kiểm tra những điều có thể xác định chỉ từ request:

~~~java
import com.example.payments.grpc.CreatePaymentRequest;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class PaymentRequestValidator {

    private static final long MAX_AMOUNT = 10_000_000_000L;
    private static final int MAX_TAGS = 10;

    public List<FieldViolation> validate(
            CreatePaymentRequest request) {
        List<FieldViolation> violations = new ArrayList<>();

        if (request.getSourceAccountId().isBlank()) {
            violations.add(new FieldViolation(
                    "source_account_id", "must not be blank"));
        }
        if (request.getDestinationAccountId().isBlank()) {
            violations.add(new FieldViolation(
                    "destination_account_id", "must not be blank"));
        }
        if (!request.getSourceAccountId().isBlank()
                && request.getSourceAccountId().equals(
                        request.getDestinationAccountId())) {
            violations.add(new FieldViolation(
                    "destination_account_id",
                    "must differ from source_account_id"));
        }

        if (!request.hasAmountMinorUnits()) {
            violations.add(new FieldViolation(
                    "amount_minor_units", "is required"));
        } else if (request.getAmountMinorUnits() <= 0) {
            violations.add(new FieldViolation(
                    "amount_minor_units", "must be greater than zero"));
        } else if (request.getAmountMinorUnits() > MAX_AMOUNT) {
            violations.add(new FieldViolation(
                    "amount_minor_units", "exceeds the API limit"));
        }

        if (!request.getCurrency().matches("[A-Z]{3}")) {
            violations.add(new FieldViolation(
                    "currency", "must be a three-letter uppercase code"));
        }
        if (request.getTagsCount() > MAX_TAGS) {
            violations.add(new FieldViolation(
                    "tags", "contains too many elements"));
        }

        return List.copyOf(violations);
    }
}
~~~

Validator không kiểm tra account có tồn tại hoặc có đủ số dư hay không; các điều kiện đó cần trạng thái hệ thống và thuộc application/domain. Validator cũng không được thực hiện side effect.

## 6. Unit test cho request validator

Test dùng generated request thật. Một test kiểm tra request hợp lệ, test khác kiểm tra nhiều vi phạm cùng lúc:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.payments.grpc.CreatePaymentRequest;
import java.util.List;
import org.junit.jupiter.api.Test;

class PaymentRequestValidatorTest {

    private final PaymentRequestValidator validator =
            new PaymentRequestValidator();

    @Test
    void acceptsValidRequest() {
        CreatePaymentRequest request =
                CreatePaymentRequest.newBuilder()
                        .setSourceAccountId("account-A")
                        .setDestinationAccountId("account-B")
                        .setAmountMinorUnits(25_000)
                        .setCurrency("USD")
                        .addTags("invoice")
                        .build();

        assertTrue(validator.validate(request).isEmpty());
    }

    @Test
    void reportsMissingAndInvalidFields() {
        CreatePaymentRequest request =
                CreatePaymentRequest.newBuilder()
                        .setSourceAccountId("account-A")
                        .setDestinationAccountId("account-A")
                        .setAmountMinorUnits(-1)
                        .setCurrency("usd")
                        .build();

        List<FieldViolation> violations = validator.validate(request);

        assertEquals(3, violations.size());
        assertEquals(
                List.of(
                        "destination_account_id",
                        "amount_minor_units",
                        "currency"),
                violations.stream().map(FieldViolation::field).toList());
    }

    @Test
    void distinguishesAbsentAmountFromZeroAmount() {
        CreatePaymentRequest absent =
                CreatePaymentRequest.newBuilder()
                        .setSourceAccountId("account-A")
                        .setDestinationAccountId("account-B")
                        .setCurrency("USD")
                        .build();
        CreatePaymentRequest zero =
                absent.toBuilder()
                        .setAmountMinorUnits(0)
                        .build();

        List<FieldViolation> absentErrors = validator.validate(absent);
        List<FieldViolation> zeroErrors = validator.validate(zero);

        assertEquals(
                "is required",
                violationFor(absentErrors, "amount_minor_units")
                        .description());
        assertEquals(
                "must be greater than zero",
                violationFor(zeroErrors, "amount_minor_units")
                        .description());
    }

    private FieldViolation violationFor(
            List<FieldViolation> violations,
            String field) {
        return violations.stream()
                .filter(violation -> violation.field().equals(field))
                .findFirst()
                .orElseThrow();
    }
}
~~~

Test `reportsMissingAndInvalidFields` đồng thời xác nhận thứ tự violations ổn định theo thứ tự validator thêm lỗi. Thứ tự không nhất thiết là một phần hợp đồng gRPC, nhưng kết quả xác định giúp test dễ đọc và tránh flakiness.

Nên bổ sung ca cho amount vượt giới hạn và số tags quá nhiều. Không cần test mọi giá trị số; tập trung các biên: thiếu, dưới min, đúng min, đúng max và vượt max.

## 7. Chuyển violations thành INVALID_ARGUMENT

Khi client cần hiển thị lỗi theo field, có thể dùng rich error details chuẩn `google.rpc.BadRequest`. Mapper tạo một detail chứa nhiều `FieldViolation`:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class ValidationStatusFactory {

    public StatusRuntimeException invalidArgument(
            List<FieldViolation> violations) {
        BadRequest.Builder badRequest = BadRequest.newBuilder();
        for (FieldViolation violation : violations) {
            badRequest.addFieldViolations(
                    BadRequest.FieldViolation.newBuilder()
                            .setField(violation.field())
                            .setDescription(violation.description()));
        }

        com.google.rpc.Status richStatus =
                com.google.rpc.Status.newBuilder()
                        .setCode(Status.Code.INVALID_ARGUMENT.value())
                        .setMessage("Request validation failed")
                        .addDetails(Any.pack(badRequest.build()))
                        .build();

        return StatusProto.toStatusRuntimeException(richStatus);
    }
}
~~~

Client đọc status code để phân loại lỗi và unpack `google.rpc.BadRequest` để biết field nào không hợp lệ. Client không cần parse một câu description tự do. Dự án cần dependency tương thích cho `grpc-protobuf` và Google API common protos.

Nếu không dùng rich details, có thể trả `Status.INVALID_ARGUMENT.withDescription("Request validation failed").asRuntimeException()`; khi đó client chỉ nhận lỗi tổng quát. Dù dùng cách nào, description phải ổn định và không chứa dữ liệu nhạy cảm.

## 8. Unit test cho validation status mapping

Test xác nhận cả gRPC status lẫn rich detail:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;
import java.util.List;
import org.junit.jupiter.api.Test;

class ValidationStatusFactoryTest {

    private final ValidationStatusFactory factory =
            new ValidationStatusFactory();

    @Test
    void mapsViolationsToInvalidArgumentAndBadRequestDetails()
            throws Exception {
        StatusRuntimeException error = factory.invalidArgument(
                List.of(
                        new FieldViolation(
                                "amount_minor_units",
                                "must be greater than zero"),
                        new FieldViolation(
                                "currency",
                                "must be a three-letter uppercase code")));

        assertEquals(
                Status.Code.INVALID_ARGUMENT,
                Status.fromThrowable(error).getCode());

        com.google.rpc.Status richStatus =
                StatusProto.fromThrowable(error);
        assertNotNull(richStatus);
        assertEquals(
                Status.Code.INVALID_ARGUMENT.value(),
                richStatus.getCode());

        BadRequest details =
                richStatus.getDetails(0).unpack(BadRequest.class);
        assertEquals(2, details.getFieldViolationsCount());
        assertEquals(
                "amount_minor_units",
                details.getFieldViolations(0).getField());
        assertEquals(
                "currency",
                details.getFieldViolations(1).getField());
    }
}
~~~

Test này phát hiện lỗi phổ biến là code status đúng nhưng detail bị thiếu, field path sai hoặc chỉ trả một vi phạm đầu tiên. Nếu client dựa vào `BadRequest`, cần test cấu trúc detail chứ không chỉ kiểm tra description.

## 9. Thiết kế exception mapper

Exception mapper chuyển lỗi application thành status gRPC. Quy tắc nên dựa trên exception type đã phân loại:

| Exception | gRPC status | Lý do |
| --- | --- | --- |
| `RequestValidationException` | `INVALID_ARGUMENT` | Request vi phạm hợp đồng |
| `AccountNotFoundException` | `NOT_FOUND` | Tài nguyên không tồn tại |
| `InsufficientFundsException` | `FAILED_PRECONDITION` | Trạng thái hiện tại không cho phép thao tác |
| `AuthorizationDeniedException` | `PERMISSION_DENIED` | Caller không có quyền |
| `DependencyUnavailableException` | `UNAVAILABLE` | Dependency tạm thời không sẵn sàng |
| Lỗi không dự kiến | `INTERNAL` | Lỗi server không được công bố chi tiết |
| `StatusRuntimeException` đã có | Giữ nguyên status/trailers | Lỗi đã được biểu diễn bằng gRPC |

Không ánh xạ mọi `IllegalArgumentException` thành `INVALID_ARGUMENT` nếu exception đó có thể phát sinh từ bug nội bộ. Dùng exception validation có kiểu riêng để tránh biến lỗi lập trình thành lỗi client.

## 10. Ví dụ exception mapper

Ví dụ sau giữ nguyên status gRPC đã có, kể cả khi exception được bọc trong một exception khác:

~~~java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class GrpcExceptionMapper {

    private final ValidationStatusFactory validationStatusFactory;

    public GrpcExceptionMapper(
            ValidationStatusFactory validationStatusFactory) {
        this.validationStatusFactory = validationStatusFactory;
    }

    public StatusRuntimeException map(Throwable failure) {
        Throwable grpcFailure = findGrpcFailure(failure);
        if (grpcFailure instanceof StatusRuntimeException runtime) {
            return runtime;
        }
        if (grpcFailure instanceof StatusException checked) {
            Metadata trailers = Status.trailersFromThrowable(checked);
            return Status.fromThrowable(checked)
                    .asRuntimeException(trailers);
        }

        if (failure instanceof RequestValidationException invalid) {
            return validationStatusFactory.invalidArgument(
                    invalid.violations());
        }
        if (failure instanceof AccountNotFoundException) {
            return Status.NOT_FOUND
                    .withDescription("Account not found")
                    .asRuntimeException();
        }
        if (failure instanceof InsufficientFundsException) {
            return Status.FAILED_PRECONDITION
                    .withDescription("Insufficient funds")
                    .asRuntimeException();
        }
        if (failure instanceof AuthorizationDeniedException) {
            return Status.PERMISSION_DENIED
                    .withDescription("Operation is not permitted")
                    .asRuntimeException();
        }
        if (failure instanceof DependencyUnavailableException) {
            return Status.UNAVAILABLE
                    .withDescription("A required dependency is unavailable")
                    .asRuntimeException();
        }

        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }

    private Throwable findGrpcFailure(Throwable failure) {
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());
        Throwable current = failure;
        while (current != null && visited.add(current)) {
            if (current instanceof StatusRuntimeException
                    || current instanceof StatusException) {
                return current;
            }
            current = current.getCause();
        }
        return null;
    }
}
~~~

Đoạn code minh họa giả định các exception domain có kiểu riêng và mapper được Spring quản lý. Dùng identity set để tránh vòng lặp bất thường trong cause chain. Nếu exception gRPC đã tồn tại, mapper giữ nguyên nó hoặc tái tạo status cùng trailers; không biến một `UNAVAILABLE` có metadata retry thành `INTERNAL`.

Không trả `failure.getMessage()` cho client ở nhánh mặc định. Exception nội bộ có thể chứa SQL, tên bảng, connection string, token hoặc dữ liệu người dùng. Chi tiết cần điều tra nên được log ở server qua logging/interceptor có redaction và correlation ID.

## 11. Unit test cho exception-to-status mapping

Test mỗi nhóm exception để khóa status code và description công khai:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.List;
import org.junit.jupiter.api.Test;

class GrpcExceptionMapperTest {

    private final GrpcExceptionMapper mapper =
            new GrpcExceptionMapper(new ValidationStatusFactory());

    @Test
    void mapsDomainExceptionsToExpectedStatuses() {
        assertEquals(
                Status.Code.NOT_FOUND,
                Status.fromThrowable(
                        mapper.map(new AccountNotFoundException()))
                        .getCode());
        assertEquals(
                Status.Code.FAILED_PRECONDITION,
                Status.fromThrowable(
                        mapper.map(new InsufficientFundsException()))
                        .getCode());
        assertEquals(
                Status.Code.PERMISSION_DENIED,
                Status.fromThrowable(
                        mapper.map(new AuthorizationDeniedException()))
                        .getCode());
        assertEquals(
                Status.Code.UNAVAILABLE,
                Status.fromThrowable(
                        mapper.map(new DependencyUnavailableException()))
                        .getCode());
    }

    @Test
    void mapsValidationExceptionToInvalidArgument() {
        StatusRuntimeException mapped = mapper.map(
                new RequestValidationException(
                        List.of(new FieldViolation(
                                "amount_minor_units",
                                "must be greater than zero"))));

        assertEquals(
                Status.Code.INVALID_ARGUMENT,
                Status.fromThrowable(mapped).getCode());
    }

    @Test
    void mapsUnexpectedFailureToSafeInternalStatus() {
        StatusRuntimeException mapped = mapper.map(
                new IllegalStateException("database password=secret"));

        Status status = Status.fromThrowable(mapped);
        assertEquals(Status.Code.INTERNAL, status.getCode());
        assertEquals("Internal server error", status.getDescription());
        assertFalse(status.getDescription().contains("secret"));
    }
}
~~~

Các exception domain trong ví dụ là lớp application riêng. Test không cần mock gRPC server vì đang xác minh logic thuần của mapper. Nếu mapper có logger, có thể kiểm tra log redaction ở test riêng; không nên buộc unit test status mapping phụ thuộc hệ thống logging bên ngoài.

## 12. Bảo toàn status và trailers đã có

Một downstream gRPC client có thể ném `StatusRuntimeException` kèm trailers, ví dụ support reference hoặc retry metadata. Exception mapper không được làm mất chúng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CompletionException;
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

class GrpcExceptionMapperPreservationTest {

    private static final Metadata.Key<String> SUPPORT_REFERENCE =
            Metadata.Key.of(
                    "support-reference",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final GrpcExceptionMapper mapper =
            new GrpcExceptionMapper(new ValidationStatusFactory());

    @Test
    void preservesExistingGrpcStatusAndTrailers() {
        Metadata trailers = new Metadata();
        trailers.put(SUPPORT_REFERENCE, "ref-42");
        StatusRuntimeException original = Status.UNAVAILABLE
                .withDescription("upstream unavailable")
                .asRuntimeException(trailers);

        StatusRuntimeException mapped = mapper.map(original);

        assertSame(original, mapped);
        assertEquals(
                Status.Code.UNAVAILABLE,
                Status.fromThrowable(mapped).getCode());
        assertEquals(
                "ref-42",
                Status.trailersFromThrowable(mapped)
                        .get(SUPPORT_REFERENCE));
    }

    @Test
    void preservesGrpcStatusWrappedByAnotherException() {
        StatusRuntimeException original = Status.DEADLINE_EXCEEDED
                .withDescription("downstream deadline")
                .asRuntimeException();

        StatusRuntimeException mapped =
                mapper.map(new CompletionException(original));

        assertEquals(
                Status.Code.DEADLINE_EXCEEDED,
                Status.fromThrowable(mapped).getCode());
    }

    @Test
    void preservesCheckedGrpcStatusAndTrailers() {
        Metadata trailers = new Metadata();
        trailers.put(SUPPORT_REFERENCE, "checked-ref-7");
        StatusException original = Status.UNAUTHENTICATED
                .withDescription("credentials are invalid")
                .asException(trailers);

        StatusRuntimeException mapped = mapper.map(original);

        assertEquals(
                Status.Code.UNAUTHENTICATED,
                Status.fromThrowable(mapped).getCode());
        assertEquals(
                "checked-ref-7",
                Status.trailersFromThrowable(mapped)
                        .get(SUPPORT_REFERENCE));
    }
}
~~~

Nếu mapper hỗ trợ `StatusException` checked, cũng nên test nhánh đó và xác nhận trailers vẫn tồn tại. Test preservation quan trọng khi adapter bọc lỗi downstream hoặc chuyển đổi exception giữa các layer.

## 13. Adapter phải validate trước khi gọi use case

Adapter nhận generated request, lấy danh sách violations và kết thúc RPC bằng lỗi trước khi gọi application use case. Khi request hợp lệ, adapter mới chuyển tiếp xử lý:

~~~java
import io.grpc.stub.StreamObserver;
import java.util.List;

public class PaymentGrpcService
        extends PaymentServiceGrpc.PaymentServiceImplBase {

    private final PaymentRequestValidator validator;
    private final GrpcExceptionMapper exceptionMapper;
    private final CreatePaymentUseCase useCase;

    public PaymentGrpcService(
            PaymentRequestValidator validator,
            GrpcExceptionMapper exceptionMapper,
            CreatePaymentUseCase useCase) {
        this.validator = validator;
        this.exceptionMapper = exceptionMapper;
        this.useCase = useCase;
    }

    @Override
    public void createPayment(
            CreatePaymentRequest request,
            StreamObserver<CreatePaymentResponse> responseObserver) {
        List<FieldViolation> violations = validator.validate(request);
        if (!violations.isEmpty()) {
            responseObserver.onError(exceptionMapper.map(
                    new RequestValidationException(violations)));
            return;
        }
        try {
            String paymentId = useCase.create(request);
            responseObserver.onNext(
                    CreatePaymentResponse.newBuilder()
                            .setPaymentId(paymentId)
                            .build());
            responseObserver.onCompleted();
        } catch (Exception failure) {
            responseObserver.onError(exceptionMapper.map(failure));
        }
    }
}
~~~

Đoạn code là ví dụ rút gọn; trong ứng dụng thực, request hợp lệ thường được map sang application command trước khi gọi use case. Điểm cần test ở đây là thứ tự: validation thất bại thì không gọi use case và chỉ phát một terminal error.

## 14. Kiểm thử adapter không gọi use case khi request sai

Validator và status mapper có thể đúng riêng lẻ nhưng adapter vẫn gọi use case trước khi kiểm tra request. Một unit test adapter dùng Mockito có thể xác nhận thứ tự:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.*;

import com.example.payments.grpc.CreatePaymentRequest;
import com.example.payments.grpc.CreatePaymentResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PaymentGrpcServiceTest {

    @Mock
    private CreatePaymentUseCase useCase;

    @Mock
    private StreamObserver<CreatePaymentResponse> responseObserver;

    private PaymentGrpcService service;

    @BeforeEach
    void setUp() {
        PaymentRequestValidator validator =
                new PaymentRequestValidator();
        GrpcExceptionMapper exceptionMapper =
                new GrpcExceptionMapper(new ValidationStatusFactory());
        service = new PaymentGrpcService(
                validator, exceptionMapper, useCase);
    }

    @Test
    void invalidRequestDoesNotInvokeUseCase() {
        CreatePaymentRequest request =
                CreatePaymentRequest.newBuilder()
                        .setSourceAccountId("")
                        .setDestinationAccountId("account-B")
                        .setAmountMinorUnits(-1)
                        .setCurrency("usd")
                        .build();

        service.createPayment(request, responseObserver);

        verifyNoInteractions(useCase);
        verify(responseObserver, times(1)).onError(argThat(error ->
                Status.fromThrowable(error).getCode()
                        == Status.Code.INVALID_ARGUMENT));
        verify(responseObserver, never()).onNext(any());
        verify(responseObserver, never()).onCompleted();
    }
}
~~~

Ví dụ minh họa nhấn mạnh rằng request sai phải kết thúc bằng một terminal error và không được tạo response thành công. Khi dùng Mockito, chỉ xác minh những tương tác có ý nghĩa với hợp đồng.

## 15. Ma trận kiểm thử status mapping

| Đầu vào | Status mong đợi | Assertion bổ sung |
| --- | --- | --- |
| Request validation violations | `INVALID_ARGUMENT` | `BadRequest` chứa field paths |
| Account không tồn tại | `NOT_FOUND` | Description tổng quát |
| Không đủ số dư | `FAILED_PRECONDITION` | Không lộ số dư nội bộ |
| Không đủ quyền | `PERMISSION_DENIED` | Không lộ policy/credential |
| Dependency tạm thời lỗi | `UNAVAILABLE` | Bảo toàn trailers nếu lỗi gRPC đã có |
| Deadline downstream | `DEADLINE_EXCEEDED` | Không bị đổi thành `INTERNAL` |
| Exception bất ngờ | `INTERNAL` | Description không chứa exception message |
| StatusException đã có | Giữ nguyên code | Bảo toàn trailers |
| StatusRuntimeException được bọc | Giữ nguyên code | Tìm được gRPC cause |

Không nên test bằng cách so sánh toàn bộ exception message do gRPC runtime tạo. Hãy assert status code, description công khai và typed details. Nếu description không phải contract cho client, chỉ kiểm tra nó không rò rỉ dữ liệu nhạy cảm.

## 16. Những anti-pattern thường gặp

- **Chỉ test exception được ném:** chưa chứng minh status code hoặc rich details đúng.
- **Map mọi RuntimeException thành INVALID_ARGUMENT:** che giấu lỗi server và phân loại sai bug.
- **Map mọi lỗi thành INTERNAL:** client không thể phân biệt lỗi request, domain và dependency.
- **Dùng exception message làm status description:** có thể lộ thông tin nội bộ.
- **Bỏ qua trailers:** làm mất support reference hoặc retry metadata từ downstream.
- **Không test unknown/wrapped gRPC exception:** lỗi đã có status có thể bị đổi thành INTERNAL.
- **Khởi động Spring context cho mapper thuần:** làm test chậm và khó khoanh vùng.
- **Dùng thứ tự collection không ổn định:** khiến assertion chập chờn.
- **Gọi use case trước validation:** request sai vẫn có thể tạo side effect.

## 17. Tự luyện tập

1. Vì sao request validator nên trả field violations thay vì trực tiếp gọi `responseObserver.onError()`?
2. Viết unit test phân biệt amount bị thiếu với amount bằng 0.
3. Khi nào dùng `INVALID_ARGUMENT`, khi nào dùng `FAILED_PRECONDITION`?
4. Vì sao exception mapper phải giữ nguyên trailers của `StatusRuntimeException` từ downstream?
5. Thiết kế test chứng minh exception bất ngờ không làm lộ SQL hoặc token trong status description.
6. Làm thế nào kiểm tra adapter không gọi use case khi validator trả về violations?

**Ghi nhớ:** Unit test validation phải xác nhận field violations, presence và các biên dữ liệu; unit test status mapping phải xác nhận đúng gRPC code, rich details, preservation của status/trailers và mô tả an toàn. Giữ validator, exception mapper và service adapter ở các trách nhiệm riêng, dùng exception có kiểu rõ ràng và không để request sai tạo side effect.
