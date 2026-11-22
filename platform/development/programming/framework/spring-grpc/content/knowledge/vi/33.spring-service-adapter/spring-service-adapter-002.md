# Validate protobuf request tại boundary

**Chương:** Spring service adapter  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và server/client cho unary hoặc streaming RPC. Bài này tập trung vào việc kiểm tra request ngay tại ranh giới service adapter: xác định dữ liệu protobuf nào hợp lệ theo hợp đồng API, trả lỗi có cấu trúc và ngăn request sai đi vào application use case.

## 1. Boundary validation giải quyết vấn đề gì?

Generated request là message Java mà gRPC runtime tạo ra sau khi giải mã protobuf payload. Đối tượng đó có kiểu và getter rõ ràng, nhưng điều đó **không chứng minh nội dung request hợp lệ về mặt nghiệp vụ API**.

Ví dụ một request tạo chuyển khoản có thể được giải mã thành công nhưng vẫn chứa:

- ID tài khoản rỗng.
- Số tiền bằng 0 hoặc âm.
- Mã tiền tệ sai định dạng.
- Danh sách dòng chuyển khoản rỗng hoặc quá dài.
- Hai trường có quan hệ không hợp lệ.
- Một enum numeric value mà phiên bản server chưa nhận diện.

Nếu adapter chuyển ngay request đó vào application service, các lớp bên trong phải tự phòng vệ trước dữ liệu đầu vào sai. Điều này làm validation bị phân tán và có thể gây side effect trước khi phát hiện lỗi.

Boundary validation đặt một cổng rõ ràng:

```text
HTTP/2 + protobuf bytes
          |
          v
    gRPC protobuf parser
          |
          v
   Generated request object
          |
          v
  Spring gRPC service adapter
          |
          +--> Validate request structure and constraints
          |          |
          |          +--> Invalid: INVALID_ARGUMENT
          |
          v
   Map to application command
          |
          v
   Application use case
          |
          v
   Map result to protobuf response
```

Mục tiêu là từ chối sớm request không đáp ứng hợp đồng, trả lỗi nhất quán và chỉ gọi use case sau khi request vượt qua validation.

## 2. Phân biệt protobuf parsing với semantic validation

Hai bước này xảy ra ở hai tầng khác nhau:

| Tầng | Kiểm tra | Ví dụ thất bại |
| --- | --- | --- |
| Protobuf parsing | Wire format có thể giải mã thành message theo schema hay không | Tag/wire type sai, payload bị cắt, length-delimited field không đầy đủ |
| Boundary validation | Giá trị đã giải mã có đáp ứng quy tắc request của API hay không | ID rỗng, amount âm, thiếu field bắt buộc, tổ hợp field không hợp lệ |
| Domain/application | Thao tác có hợp lệ với trạng thái hiện tại của hệ thống hay không | Tài khoản bị khóa, không đủ số dư, đơn hàng đã giao |

Service method chỉ nhận được generated request sau khi gRPC runtime đã parse payload thành công. Lỗi parse thường xảy ra trước khi handler được gọi; cách transport chuyển lỗi marshalling thành status cụ thể phụ thuộc runtime và cấu hình. Không dựa vào parser để thực hiện validation nghiệp vụ.

Boundary validation nên tập trung vào những điều có thể quyết định từ request và hợp đồng API. Ví dụ “amount phải lớn hơn 0” là validation tại boundary; “tài khoản có đủ số dư hay không” phụ thuộc trạng thái hệ thống và thuộc domain/application.

## 3. Thiết kế protobuf để validation có thể phân biệt presence

Ví dụ hợp đồng:

```proto
syntax = "proto3";

import "google/protobuf/timestamp.proto";

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
  repeated TransferTag tags = 5;
  oneof schedule {
    google.protobuf.Timestamp execute_at = 6;
    bool execute_immediately = 7;
  }
}

message TransferTag {
  string key = 1;
  string value = 2;
}

message CreateTransferResponse {
  string transfer_id = 1;
}
```

Với scalar proto3 thông thường, getter trả giá trị mặc định nếu field không xuất hiện. Nếu cần phân biệt “không gửi” với “gửi giá trị 0”, dùng `optional`:

```java
if (!request.hasAmountMinorUnits()) {
    // Field bị thiếu.
} else if (request.getAmountMinorUnits() <= 0) {
    // Field có mặt nhưng giá trị không hợp lệ.
}
```

Message field có presence riêng; `oneof` cung cấp case enum; repeated field có thể rỗng và cần kiểm tra số phần tử. Hãy chọn schema thể hiện đúng điều API cần biết, vì validator không thể khôi phục thông tin presence đã bị schema làm mất.

## 4. Các nhóm quy tắc cần kiểm tra tại boundary

Một validator thường kiểm tra các nhóm sau:

| Nhóm | Ví dụ | Kiểm tra |
| --- | --- | --- |
| Required/presence | `amount_minor_units` | `hasAmountMinorUnits()` |
| String format | Account ID, currency | Không rỗng, độ dài, regex hoặc parser chuyên dụng |
| Numeric range | Amount, quantity | Min/max theo hợp đồng |
| Collection | Repeated tags | Số phần tử tối thiểu/tối đa, trùng key |
| Nested message | Mỗi transfer tag | Kiểm tra field con và tạo path cụ thể |
| Cross-field | Source và destination | Hai ID không được giống nhau |
| oneof | Lịch thực thi | Phải có một nhánh hợp lệ nếu API yêu cầu |
| Enum | Loại giao dịch | Từ chối `UNRECOGNIZED` hoặc giá trị không được hỗ trợ |
| Payload size | Chuỗi, bytes, số message | Giới hạn theo hợp đồng và giới hạn transport |

Validation phải có giới hạn chi phí. Không duyệt một collection khổng lồ hoặc chạy regex phức tạp trước khi áp dụng giới hạn kích thước phù hợp. Giới hạn message của transport và giới hạn số phần tử theo nghiệp vụ là hai lớp bảo vệ bổ sung.

## 5. Tạo kết quả validation theo field

Thay vì ném exception ngay khi gặp lỗi đầu tiên, validator có thể thu thập nhiều vi phạm để client sửa trong một lần. Mỗi vi phạm gồm:

- Field path theo tên protobuf, ví dụ `source_account_id` hoặc `tags[2].key`.
- Mô tả ngắn, ổn định và an toàn.
- Có thể có reason code nếu client cần xử lý theo loại lỗi.

Ví dụ model kết quả:

```java
public record FieldViolation(
        String field,
        String description) {}
```

Validator không phụ thuộc gRPC status. Nó chỉ trả về những vấn đề tìm thấy trong request:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class TransferRequestValidator {

    private static final int MAX_TAGS = 20;
    private static final long MAX_AMOUNT = 10_000_000_000L;

    public List<FieldViolation> validate(
            CreateTransferRequest request) {
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
        Set<String> keys = new HashSet<>();
        for (int index = 0; index < request.getTagsCount()
                && index < MAX_TAGS; index++) {
            TransferTag tag = request.getTags(index);
            if (tag.getKey().isBlank()) {
                violations.add(new FieldViolation(
                        "tags[" + index + "].key", "must not be blank"));
            } else if (!keys.add(tag.getKey())) {
                violations.add(new FieldViolation(
                        "tags[" + index + "].key", "must be unique"));
            }
        }

        if (request.getScheduleCase()
                == CreateTransferRequest.ScheduleCase.SCHEDULE_NOT_SET) {
            violations.add(new FieldViolation(
                    "schedule", "a schedule option is required"));
        }

        return List.copyOf(violations);
    }
}
```

Validator chỉ kiểm tra tối đa `MAX_TAGS` phần tử sau khi đã ghi nhận lỗi vượt giới hạn. Với request lớn hơn nhiều, nên áp dụng message-size limit ở server và giới hạn collection ở boundary để tránh tốn CPU/memory.

Currency regex ở ví dụ chỉ kiểm tra hình dạng ba chữ in hoa; nó không chứng minh mã tiền tệ được hệ thống hỗ trợ. Kiểm tra danh mục currency được hỗ trợ có thể thuộc application policy hoặc domain service tùy hợp đồng.

## 6. Chuyển validation violations thành INVALID_ARGUMENT

gRPC status `INVALID_ARGUMENT` phù hợp khi request sai về presence, format, range hoặc cấu trúc. Để client hiển thị lỗi theo field mà không parse description, có thể dùng rich error detail chuẩn `google.rpc.BadRequest`.

Ví dụ factory:

```java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.protobuf.StatusProto;
import java.util.List;

@Component
public class ValidationStatusFactory {

    public RuntimeException invalidArgument(
            List<FieldViolation> violations) {
        BadRequest.Builder details = BadRequest.newBuilder();
        for (FieldViolation violation : violations) {
            details.addFieldViolations(
                    BadRequest.FieldViolation.newBuilder()
                            .setField(violation.field())
                            .setDescription(violation.description()));
        }

        com.google.rpc.Status richStatus =
                com.google.rpc.Status.newBuilder()
                        .setCode(Status.Code.INVALID_ARGUMENT.value())
                        .setMessage("Request validation failed")
                        .addDetails(Any.pack(details.build()))
                        .build();

        return StatusProto.toStatusRuntimeException(richStatus);
    }
}
```

`google.rpc.BadRequest` là error detail có cấu trúc. Client có thể unpack detail và hiển thị lỗi cho đúng field. Dự án cần dependency tương ứng cho Google API common protos và `grpc-protobuf`. Nếu không dùng rich details, vẫn có thể trả `Status.INVALID_ARGUMENT.withDescription("Request không hợp lệ").asRuntimeException()`; client khi đó chỉ nhận được nhóm lỗi tổng quát.

Không đưa giá trị nhạy cảm của field vào `description`. Ví dụ, không trả nguyên account ID, token, email hoặc payload. Metadata và error details đều đến client, nên phải tuân thủ cùng nguyên tắc bảo mật như status description.

## 7. Gọi validator trước application use case

Adapter generated service base nhận request, gọi validator và chỉ map sang command khi không còn violation:

```java
@GrpcService
public class TransferGrpcService
        extends TransferServiceGrpc.TransferServiceImplBase {

    private final TransferRequestValidator validator;
    private final ValidationStatusFactory statusFactory;
    private final CreateTransferUseCase useCase;
    private final TransferRequestMapper requestMapper;
    private final TransferResponseMapper responseMapper;
    private final GrpcExceptionMapper exceptionMapper;

    public TransferGrpcService(
            TransferRequestValidator validator,
            ValidationStatusFactory statusFactory,
            CreateTransferUseCase useCase,
            TransferRequestMapper requestMapper,
            TransferResponseMapper responseMapper,
            GrpcExceptionMapper exceptionMapper) {
        this.validator = validator;
        this.statusFactory = statusFactory;
        this.useCase = useCase;
        this.requestMapper = requestMapper;
        this.responseMapper = responseMapper;
        this.exceptionMapper = exceptionMapper;
    }

    @Override
    public void createTransfer(
            CreateTransferRequest request,
            StreamObserver<CreateTransferResponse> responseObserver) {

        List<FieldViolation> violations = validator.validate(request);
        if (!violations.isEmpty()) {
            responseObserver.onError(
                    statusFactory.invalidArgument(violations));
            return;
        }

        try {
            CreateTransferCommand command =
                    requestMapper.toCommand(request);
            TransferResult result = useCase.execute(command);
            responseObserver.onNext(responseMapper.toProto(result));
            responseObserver.onCompleted();
        } catch (AccountNotFoundException missing) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Không tìm thấy tài khoản")
                            .asRuntimeException());
        } catch (InsufficientBalanceException precondition) {
            responseObserver.onError(
                    Status.FAILED_PRECONDITION
                            .withDescription("Không đủ số dư để thực hiện")
                            .asRuntimeException());
        } catch (Exception failure) {
            responseObserver.onError(exceptionMapper.map(failure));
        }
    }
}
```

Ví dụ tập trung vào thứ tự xử lý. Trong ứng dụng thực, lỗi bất ngờ cần được log ở server qua exception mapper/interceptor có kiểm soát; không lộ stack trace hoặc message nội bộ cho client. Không bắt `Throwable` để che các lỗi JVM nghiêm trọng.

Việc validator chạy trước use case giúp request sai không tạo transaction, không gọi downstream và không phát sinh side effect. Tuy nhiên, domain vẫn phải bảo vệ invariant vì trạng thái có thể thay đổi giữa lúc boundary validation và lúc transaction thực thi.

## 8. Phân biệt boundary validation với lỗi domain

Không nên biến mọi điều kiện thất bại thành `INVALID_ARGUMENT`:

| Tình huống | Status thường phù hợp | Tầng quyết định |
| --- | --- | --- |
| Account ID rỗng | `INVALID_ARGUMENT` | Boundary |
| Amount âm | `INVALID_ARGUMENT` | Boundary |
| Danh sách tags có key trùng | `INVALID_ARGUMENT` nếu hợp đồng cấm trùng | Boundary |
| Account ID hợp lệ nhưng không tồn tại | `NOT_FOUND` | Application/domain |
| Tài khoản bị khóa | `FAILED_PRECONDITION` | Domain |
| Caller không có quyền chuyển tiền | `PERMISSION_DENIED` | Security/authorization |
| Optimistic locking conflict | `ABORTED` | Persistence/application |
| Dependency tạm thời không sẵn sàng | `UNAVAILABLE` | Dependency adapter |
| Vượt quota được cấp | `RESOURCE_EXHAUSTED` | Policy/capacity |

Quy tắc thực tế: nếu chỉ nhìn request là kết luận được nó vi phạm hợp đồng, đó thường là boundary validation. Nếu cần đọc trạng thái hiện tại, xác định quyền hoặc phối hợp transaction, lỗi thuộc tầng tương ứng.

## 9. Bean Validation và protobuf validation libraries

Không nên giả định generated protobuf message tự động có Jakarta Bean Validation annotations hoặc Spring MVC `@Valid` sẽ tự chạy trên gRPC method. gRPC service base không đi qua MVC controller pipeline.

Có ba cách triển khai:

1. **Validator thủ công:** phù hợp với quy tắc nhỏ, rõ ràng; dễ kiểm thử và không phụ thuộc code generation plugin.
2. **Validation library tích hợp protobuf:** có thể khai báo constraint trong schema hoặc rule set riêng rồi validate generated message tại adapter/interceptor. Cần xác minh plugin, runtime dependency và phiên bản tương thích.
3. **Bean Validation trên command nội bộ:** map request sang DTO/command có annotation rồi gọi `Validator.validate()`; cách này hữu ích nếu ứng dụng đã có quy tắc validation trên DTO.

Dù chọn cách nào, vẫn cần xác định nơi thực thi và cách ánh xạ violations thành gRPC status. Không để một validation framework tự quyết định status qua exception mặc định mà không có adapter mapping rõ ràng.

## 10. Validation trong streaming RPC

Với client-streaming hoặc bidirectional streaming, request không chỉ là một message. Cần phân biệt:

- **Per-message validation:** mỗi message có field đúng format, giá trị trong range và kích thước hợp lệ.
- **Stream-level validation:** tổng số message, thứ tự sequence, uniqueness, checksum hoặc điều kiện hoàn tất.
- **Domain validation:** trạng thái tài nguyên và quyền khi áp dụng toàn bộ batch.

Ví dụ mỗi message được validate khi nhận:

```java
return new StreamObserver<UploadLine>() {
    private final AtomicBoolean terminated = new AtomicBoolean(false);
    private int received;

    @Override
    public void onNext(UploadLine line) {
        if (terminated.get()) {
            return;
        }
        List<FieldViolation> violations = lineValidator.validate(line);
        if (!violations.isEmpty()) {
            if (terminated.compareAndSet(false, true)) {
                batch.discard();
                responseObserver.onError(
                        statusFactory.invalidArgument(violations));
            }
            return;
        }
        received++;
        batch.accept(line);
    }

    @Override
    public void onError(Throwable error) {
        terminated.set(true);
        batch.discard();
    }

    @Override
    public void onCompleted() {
        if (!terminated.compareAndSet(false, true)) {
            return;
        }
        try {
            batchValidator.validateComplete(batch, received);
            UploadResult result = uploadUseCase.finish(batch);
            responseObserver.onNext(toProto(result));
            responseObserver.onCompleted();
        } catch (RequestValidationException invalid) {
            responseObserver.onError(
                    statusFactory.invalidArgument(
                            List.of(new FieldViolation(
                                    "items", "stream is incomplete"))));
        } catch (Exception failure) {
            responseObserver.onError(exceptionMapper.map(failure));
        }
    }
};
```

Đây là skeleton minh họa; các dependency `lineValidator`, `batch`, `batchValidator` và mapper thuộc ứng dụng. Code thực tế phải giới hạn số message và dung lượng batch, xử lý cleanup khi client cancel, và bảo đảm callback observer được gọi tuần tự. Không tích lũy một stream không giới hạn trong memory chỉ để đợi validation cuối cùng.

Nếu từng message hợp lệ nhưng tổng stream vi phạm manifest hoặc thiếu phần tử, lỗi có thể là `FAILED_PRECONDITION` tùy hợp đồng; không phải mọi lỗi stream-level đều là lỗi field của một request đơn lẻ.

## 11. Kiểm thử boundary validation

Kiểm thử nên tách validator, status factory và adapter:

| Mức test | Nội dung |
| --- | --- |
| Validator unit test | Presence, range, format, nested path, repeated limit, duplicate và cross-field |
| Status factory unit test | Code là `INVALID_ARGUMENT`, detail `BadRequest` chứa đúng field violations |
| Adapter test | Request lỗi không gọi use case; request hợp lệ gọi use case đúng một lần |
| In-process gRPC test | Client nhận đúng status và unpack được rich error details |
| Streaming test | Message sai kết thúc stream đúng một lần; không có response thành công sau terminal error |

Ví dụ validator unit test:

```java
class TransferRequestValidatorTest {

    private final TransferRequestValidator validator =
            new TransferRequestValidator();

    @Test
    void reportsMissingAmountAndInvalidAccountIds() {
        CreateTransferRequest request =
                CreateTransferRequest.newBuilder()
                        .setCurrency("USD")
                        .build();

        List<FieldViolation> violations = validator.validate(request);

        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("source_account_id")));
        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("destination_account_id")));
        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("amount_minor_units")));
    }

    @Test
    void rejectsSameSourceAndDestination() {
        CreateTransferRequest request =
                CreateTransferRequest.newBuilder()
                        .setSourceAccountId("account-A")
                        .setDestinationAccountId("account-A")
                        .setAmountMinorUnits(500)
                        .setCurrency("USD")
                        .setExecuteImmediately(true)
                        .build();

        List<FieldViolation> violations = validator.validate(request);

        assertTrue(violations.stream().anyMatch(
                v -> v.field().equals("destination_account_id")));
    }
}
```

Với adapter test, mock use case và xác nhận `verifyNoInteractions(useCase)` khi request invalid. Với in-process test, gọi generated blocking stub rồi kiểm tra `Status.fromThrowable(error).getCode()`; nếu dùng rich details, unpack `google.rpc.BadRequest` và kiểm tra field path.

## 12. Bảo mật, tương thích và hiệu năng

- Không phản chiếu nguyên giá trị field nhạy cảm vào error description.
- Giới hạn độ dài string, số repeated elements và kích thước message.
- Không log toàn bộ protobuf request khi validation thất bại; payload có thể chứa PII hoặc credential.
- Không từ chối mọi unknown protobuf field theo mặc định; unknown fields hỗ trợ forward compatibility khi client/server khác phiên bản.
- Với enum value chưa biết, xử lý `UNRECOGNIZED` rõ ràng nếu field ảnh hưởng semantics.
- Giữ field path và error code ổn định để client có thể xử lý mà không parse câu văn.
- Đo thời gian validation nếu request có nested collection lớn; tránh validator có độ phức tạp không kiểm soát.

## 13. Tự luyện tập

1. Vì sao protobuf parsing thành công không đồng nghĩa request hợp lệ theo hợp đồng API?
2. Khi nào cần khai báo scalar proto3 là `optional` để validator phân biệt field thiếu với giá trị mặc định?
3. Thiết kế field violations cho request có amount âm và phần tử thứ ba trong tags bị trùng key.
4. Vì sao account ID đúng định dạng nhưng không tồn tại thường không phải `INVALID_ARGUMENT`?
5. Viết adapter test chứng minh use case không được gọi khi validator trả về ít nhất một violation.
6. Với client streaming, phân biệt lỗi của từng message với lỗi tổng thể khi stream kết thúc.

**Ghi nhớ:** Validate protobuf request tại boundary sau khi gRPC runtime tạo generated message và trước khi gọi application use case. Kiểm tra presence, format, range, collection, nested fields và quan hệ giữa các field; trả `INVALID_ARGUMENT` cùng field violations có cấu trúc khi cần. Giữ lỗi trạng thái tài nguyên, quyền, concurrency và dependency ở đúng tầng; giới hạn kích thước, bảo vệ dữ liệu và kiểm thử cả validator lẫn gRPC adapter.
