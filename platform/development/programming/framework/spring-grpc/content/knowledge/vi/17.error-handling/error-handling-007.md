# Lỗi validation và INVALID_ARGUMENT

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và RPC unary hoặc streaming. Bài này tập trung vào việc xác thực request ở ranh giới API và trả gRPC status `INVALID_ARGUMENT` khi dữ liệu client gửi không đáp ứng hợp đồng.

## 1. Khi nào dùng INVALID_ARGUMENT?

`INVALID_ARGUMENT` phù hợp khi **bản thân request không hợp lệ**, bất kể trạng thái hiện tại của hệ thống. Client có thể sửa dữ liệu rồi gửi lại.

Ví dụ:

- Thiếu mã tài khoản nguồn hoặc đích.
- Số tiền nhỏ hơn hoặc bằng 0.
- Hai tài khoản nguồn và đích giống nhau.
- Mã tiền tệ sai định dạng.
- Một trường bắt buộc không được cung cấp.
- Một phần tử trong request lặp lại không đáp ứng quy tắc định dạng.

Không phải mọi thao tác thất bại đều là validation error:

| Tình huống | Status phù hợp thường gặp | Lý do |
| --- | --- | --- |
| `amount_minor_units = 0` | `INVALID_ARGUMENT` | Giá trị request không hợp lệ |
| `source_account_id` rỗng | `INVALID_ARGUMENT` | Thiếu dữ liệu đầu vào |
| Tài khoản hợp lệ về định dạng nhưng không tồn tại | `NOT_FOUND` | Tài nguyên được tham chiếu không có |
| Tài khoản đang bị khóa nên không thể chuyển tiền | `FAILED_PRECONDITION` | Trạng thái nghiệp vụ không cho phép |
| Caller không có quyền truy cập tài khoản | `PERMISSION_DENIED` | Vấn đề authorization |
| Optimistic locking conflict | `ABORTED` | Xung đột đồng thời, có thể cần chạy lại transaction |
| Số tiền vượt hạn mức tài khoản hiện tại | Thường `FAILED_PRECONDITION` hoặc `RESOURCE_EXHAUSTED` theo hợp đồng | Dữ liệu có thể hợp lệ nhưng điều kiện/hạn mức hiện tại không cho phép |

Phân biệt này giúp client biết cần sửa request, kiểm tra tài nguyên, thay đổi điều kiện hay thử lại sau.

## 2. Validation nên diễn ra ở đâu?

Validation có nhiều lớp; mỗi lớp chịu trách nhiệm cho một loại lỗi:

1. **Protocol/transport:** gRPC và protobuf giải mã wire format. Message sai định dạng trên wire có thể bị từ chối trước khi service được gọi.
2. **API validation:** kiểm tra field bắt buộc, định dạng, độ dài, phạm vi số và tính nhất quán giữa các trường. Đây là nơi thường tạo `INVALID_ARGUMENT`.
3. **Domain validation:** kiểm tra quy tắc nghiệp vụ và trạng thái hiện tại. Lỗi ở đây có thể là `FAILED_PRECONDITION`, `NOT_FOUND`, `ALREADY_EXISTS` hoặc status khác.
4. **Authorization:** xác định caller có quyền thực hiện hành động hay không; thường trả `PERMISSION_DENIED` hoặc `UNAUTHENTICATED`.

Không nên đẩy mọi kiểm tra vào domain model hoặc dựa hoàn toàn vào client. Client validation giúp trải nghiệm tốt hơn, nhưng server vẫn phải xác thực lại vì request có thể đến từ phiên bản cũ, tích hợp khác hoặc client không đáng tin cậy.

## 3. Thiết kế protobuf có chủ đích về field presence

Ví dụ API tạo lệnh chuyển tiền:

```proto
syntax = "proto3";

package payments.v1;
option java_package = "com.example.payments.grpc";
option java_multiple_files = true;

service TransferService {
  rpc CreateTransfer(CreateTransferRequest)
      returns (CreateTransferResponse);
}

message CreateTransferRequest {
  string source_account_id = 1;
  string destination_account_id = 2;
  optional int64 amount_minor_units = 3;
  string currency = 4;
  string idempotency_key = 5;
}

message CreateTransferResponse {
  string transfer_id = 1;
  string status = 2;
}
```

Trường `amount_minor_units` dùng `optional int64` để Java generated message có thể phân biệt:

- Client không gửi trường: `hasAmountMinorUnits() == false`.
- Client gửi giá trị 0: `hasAmountMinorUnits() == true`, `getAmountMinorUnits() == 0`.

Với scalar proto3 không có presence, giá trị mặc định như 0 hoặc chuỗi rỗng có thể không cho biết client bỏ trường hay chủ động gửi giá trị mặc định. Dùng `optional`, `oneof` hoặc thiết kế message lồng nhau khi sự khác biệt đó quan trọng với hợp đồng.

Không khai báo field `required` trong proto3. Hãy biểu diễn presence phù hợp và kiểm tra ở server.

## 4. Thu thập lỗi theo field thay vì chỉ báo lỗi đầu tiên

Với request có nhiều trường, trả một danh sách field violation giúp client sửa nhiều lỗi trong một lần. Một violation nên có:

- Tên field theo protobuf path, ví dụ `source_account_id`.
- Mô tả ngắn và an toàn, ví dụ `must not be blank`.
- Có thể có reason/code ổn định nếu hợp đồng cần phân loại chi tiết.

Không đưa giá trị field vào mô tả lỗi. Ví dụ, không trả `account_id=123456789 does not exist` nếu ID có thể nhạy cảm; lỗi “field không hợp lệ” đủ cho validation cú pháp. Lỗi tài nguyên không tồn tại cần được phân loại riêng theo chính sách bảo mật của API.

Một validator đơn giản:

```java
import java.util.ArrayList;
import java.util.List;

public record FieldViolation(String field, String description) {}

public class TransferRequestValidator {

    private static final long MAX_AMOUNT_MINOR_UNITS = 10_000_000_000L;

    public List<FieldViolation> validate(CreateTransferRequest request) {
        List<FieldViolation> errors = new ArrayList<>();

        if (request.getSourceAccountId().isBlank()) {
            errors.add(new FieldViolation(
                    "source_account_id", "must not be blank"));
        }
        if (request.getDestinationAccountId().isBlank()) {
            errors.add(new FieldViolation(
                    "destination_account_id", "must not be blank"));
        }
        if (request.getSourceAccountId().equals(
                request.getDestinationAccountId())
                && !request.getSourceAccountId().isBlank()) {
            errors.add(new FieldViolation(
                    "destination_account_id",
                    "must differ from source_account_id"));
        }

        if (!request.hasAmountMinorUnits()) {
            errors.add(new FieldViolation(
                    "amount_minor_units", "is required"));
        } else if (request.getAmountMinorUnits() <= 0) {
            errors.add(new FieldViolation(
                    "amount_minor_units", "must be greater than zero"));
        } else if (request.getAmountMinorUnits() > MAX_AMOUNT_MINOR_UNITS) {
            errors.add(new FieldViolation(
                    "amount_minor_units", "exceeds the API limit"));
        }

        if (!request.getCurrency().matches("[A-Z]{3}")) {
            errors.add(new FieldViolation(
                    "currency", "must be a three-letter uppercase code"));
        }
        if (request.getIdempotencyKey().isBlank()) {
            errors.add(new FieldViolation(
                    "idempotency_key", "must not be blank"));
        }

        return List.copyOf(errors);
    }
}
```

Đây là validation ở mức API: kiểm tra presence, định dạng và giới hạn kỹ thuật đã công bố. Việc mã tiền tệ có được hỗ trợ, tài khoản có tồn tại hoặc có đủ số dư hay không cần được kiểm tra ở application/domain layer, vì kết quả phụ thuộc dữ liệu và trạng thái hệ thống.

## 5. Trả INVALID_ARGUMENT cùng field violations

gRPC status code cho biết nhóm lỗi. Nếu muốn client biết chính xác field nào không hợp lệ, có thể dùng error details chuẩn `google.rpc.BadRequest` thay vì tự ghép danh sách vào description.

Với dependency protobuf tương ứng cho Google API common protos và gRPC protobuf, server có thể đóng gói `BadRequest` vào `google.rpc.Status`:

```java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.protobuf.StatusProto;
import java.util.List;

public class ValidationStatusFactory {

    public RuntimeException invalidArgument(
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
```

`google.rpc.BadRequest` là error detail có cấu trúc. Client có thể unpack detail và hiển thị lỗi theo field mà không parse chuỗi description. Nếu dự án chưa dùng rich error details, có thể trả `Status.INVALID_ARGUMENT.withDescription("Request không hợp lệ").asRuntimeException()`; khi đó client chỉ biết nhóm lỗi tổng quát.

Không đặt toàn bộ request, giá trị field hoặc exception message vào `BadRequest.FieldViolation.description`. Detail vẫn được truyền tới client và phải tuân thủ cùng nguyên tắc bảo mật như status description và trailers.

## 6. Gọi validator ở Spring gRPC adapter

Adapter kiểm tra request trước khi gọi nghiệp vụ:

```java
@GrpcService
public class TransferGrpcService
        extends TransferServiceGrpc.TransferServiceImplBase {

    private final TransferRequestValidator validator;
    private final ValidationStatusFactory statusFactory;
    private final TransferApplicationService applicationService;

    public TransferGrpcService(
            TransferRequestValidator validator,
            ValidationStatusFactory statusFactory,
            TransferApplicationService applicationService) {
        this.validator = validator;
        this.statusFactory = statusFactory;
        this.applicationService = applicationService;
    }

    @Override
    public void createTransfer(
            CreateTransferRequest request,
            StreamObserver<CreateTransferResponse> responseObserver) {

        var violations = validator.validate(request);
        if (!violations.isEmpty()) {
            responseObserver.onError(
                    statusFactory.invalidArgument(violations));
            return;
        }

        try {
            var result = applicationService.create(request);
            responseObserver.onNext(toProto(result));
            responseObserver.onCompleted();
        } catch (AccountNotFoundException error) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Không tìm thấy tài khoản")
                            .asRuntimeException());
        } catch (AccountStateException error) {
            responseObserver.onError(
                    Status.FAILED_PRECONDITION
                            .withDescription(
                                    "Trạng thái tài khoản không cho phép thao tác")
                            .asRuntimeException());
        }
    }
}
```

Validation được thực hiện trước khi gọi application service, tránh truy vấn hoặc thay đổi dữ liệu cho request sai cú pháp. Các lỗi domain vẫn được ánh xạ riêng; không biến tài khoản không tồn tại thành lỗi validation chỉ vì client truyền ID đó.

Trong ứng dụng thực, cần có fallback an toàn cho lỗi bất ngờ và logging nội bộ. Không gửi stack trace hoặc message thô cho client. Với lỗi đã biết, chỉ gọi một terminal callback: `onError` hoặc cặp `onNext` + `onCompleted`.

## 7. Validation trong streaming RPC

Với client streaming, mỗi message có thể được validate khi nhận `onNext()`, còn điều kiện liên quan toàn batch chỉ có thể xác định khi đã nhận đủ luồng hoặc manifest:

- **Per-message validation:** field bắt buộc, format, kích thước từng message, sequence.
- **Batch validation:** số lượng phần tử, tổng byte, tính duy nhất, hash hoặc manifest.
- **Domain validation:** trạng thái tài nguyên, quota nghiệp vụ, quyền và tính nhất quán với dữ liệu hiện có.

Nếu một message sai, server có thể kết thúc sớm bằng `INVALID_ARGUMENT`. Nếu tất cả message riêng lẻ hợp lệ nhưng batch thiếu phần tử so với manifest, status có thể là `FAILED_PRECONDITION`: điều kiện hoàn tất batch chưa đạt, không phải từng field request sai.

Ví dụ nhánh xử lý:

```java
@Override
public void onNext(BatchItem item) {
    if (terminated) return;

    List<FieldViolation> violations = itemValidator.validate(item);
    if (!violations.isEmpty()) {
        terminated = true;
        responseObserver.onError(
                validationStatusFactory.invalidArgument(violations));
        return;
    }

    accumulator.accept(item);
}
```

Sau khi đã gọi `responseObserver.onError()`, không gửi receipt hoặc gọi `onCompleted()` nữa. Nếu xử lý bất đồng bộ hoặc cancellation có thể chạy trên thread khác, cần đồng bộ trạng thái terminal và cleanup idempotent.

## 8. Client đọc lỗi validation

Nếu server chỉ trả status tổng quát, client kiểm tra `INVALID_ARGUMENT`:

```java
try {
    blockingStub.createTransfer(request);
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);
    if (status.getCode() == Status.Code.INVALID_ARGUMENT) {
        showValidationFailure();
    } else {
        handleOtherRpcFailure(status.getCode());
    }
}
```

Nếu server trả rich error details, client có thể đọc `google.rpc.BadRequest`:

```java
import com.google.rpc.BadRequest;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;

void showFieldErrors(StatusRuntimeException error) {
    com.google.rpc.Status richStatus = StatusProto.fromThrowable(error);
    if (richStatus == null) {
        showGenericValidationError();
        return;
    }

    for (com.google.protobuf.Any detail : richStatus.getDetailsList()) {
        if (detail.is(BadRequest.class)) {
            try {
                BadRequest badRequest = detail.unpack(BadRequest.class);
                for (BadRequest.FieldViolation violation
                        : badRequest.getFieldViolationsList()) {
                    showFieldError(
                            violation.getField(),
                            violation.getDescription());
                }
            } catch (com.google.protobuf.InvalidProtocolBufferException ignored) {
                showGenericValidationError();
            }
        }
    }
}
```

Client phải có fallback khi detail vắng mặt, không nhận diện hoặc không giải mã được. Một client cũ có thể không biết detail mới; status code vẫn phải đủ để xử lý lỗi tổng quát.

## 9. Kiểm thử validation và status

Unit test validator xác nhận từng quy tắc mà không cần mở server:

```java
class TransferRequestValidatorTest {

    private final TransferRequestValidator validator =
            new TransferRequestValidator();

    @Test
    void reportsMissingIdsAndAmount() {
        var request = CreateTransferRequest.newBuilder()
                .setCurrency("USD")
                .setIdempotencyKey("key-1")
                .build();

        var violations = validator.validate(request);

        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("source_account_id")));
        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("destination_account_id")));
        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("amount_minor_units")));
    }

    @Test
    void acceptsSyntacticallyValidRequest() {
        var request = CreateTransferRequest.newBuilder()
                .setSourceAccountId("account-A")
                .setDestinationAccountId("account-B")
                .setAmountMinorUnits(1250)
                .setCurrency("USD")
                .setIdempotencyKey("key-2")
                .build();

        assertTrue(validator.validate(request).isEmpty());
    }
}
```

Integration test qua gRPC in-process cần xác nhận:

| Ca | Kỳ vọng |
| --- | --- |
| Thiếu account ID | `INVALID_ARGUMENT`, có field violation tương ứng |
| Amount bằng 0 hoặc âm | `INVALID_ARGUMENT` |
| Currency sai định dạng | `INVALID_ARGUMENT` |
| Request hợp lệ về cú pháp nhưng tài khoản không tồn tại | `NOT_FOUND` |
| Tài khoản đang bị khóa | `FAILED_PRECONDITION` |
| Lỗi bất ngờ phía server | Status an toàn; không lộ exception message |
| Client cũ không hiểu rich detail | Vẫn xử lý được status code tổng quát |

Kiểm thử status ở ranh giới RPC quan trọng vì unit test validator không chứng minh adapter đã gọi đúng `responseObserver.onError()` hoặc gắn đúng rich details.

## 10. Tự luyện tập

1. Một request có `amount_minor_units = 0`. Vì sao đây là `INVALID_ARGUMENT`, trong khi tài khoản bị khóa lại là `FAILED_PRECONDITION`?
2. Vì sao dùng `optional int64` có thể cần thiết hơn `int64` thông thường khi xác thực trường bắt buộc?
3. Thiết kế ba field violation cho một request có source ID rỗng, amount âm và currency sai định dạng.
4. Client streaming nhận đủ các message hợp lệ nhưng thiếu một phần tử so với manifest. Vì sao `FAILED_PRECONDITION` có thể diễn tả đúng hơn `INVALID_ARGUMENT`?
5. Viết integration test xác nhận client nhận `INVALID_ARGUMENT` và unpack được `google.rpc.BadRequest` mà không cần parse status description.

**Ghi nhớ:** Dùng `INVALID_ARGUMENT` cho request sai về presence, định dạng, phạm vi hoặc tính nhất quán đầu vào. Kiểm tra ở API boundary trước khi gọi nghiệp vụ, trả field violations có cấu trúc khi cần, và phân biệt với lỗi tài nguyên, trạng thái domain, quyền truy cập hoặc xung đột đồng thời. Client có thể giúp kiểm tra sớm, nhưng server luôn là nơi thực thi validation có thẩm quyền.
