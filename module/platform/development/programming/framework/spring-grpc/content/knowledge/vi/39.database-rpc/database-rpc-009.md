# Mapping validation thành INVALID_ARGUMENT

## 1. Ý nghĩa của INVALID_ARGUMENT

Trong **SPRING_GRPC**, client gửi request Protobuf tới server để thực hiện query hoặc command. Request có thể được decode thành công nhưng vẫn chứa dữ liệu sai: identifier rỗng, số lượng âm, chuỗi vượt giới hạn, enum không được hỗ trợ hoặc hai field mâu thuẫn nhau.

gRPC status **INVALID_ARGUMENT** biểu thị request chứa argument không hợp lệ theo contract của API. Client cần sửa dữ liệu đầu vào trước khi gửi lại. Status này không nên dùng cho mọi lỗi khiến operation không thành công.

Phân biệt quan trọng:

- Input sai độc lập với trạng thái hệ thống: thường là INVALID_ARGUMENT.
- Resource tồn tại nhưng trạng thái hiện tại không cho phép thao tác: thường là FAILED_PRECONDITION.
- Resource không tồn tại: NOT_FOUND.
- Giá trị nằm ngoài miền có thể xử lý của một operation/range: có thể là OUT_OF_RANGE theo contract.
- Xung đột cập nhật đồng thời: ABORTED.
- Database/service tạm thời không sẵn sàng: UNAVAILABLE.

Bài tập trung vào cách xác thực request ở biên gRPC và application service, biểu diễn violation có cấu trúc, ánh xạ exception thành INVALID_ARGUMENT, phân biệt validation với business precondition và kiểm thử status qua gRPC.

## 2. Các lớp validation trong một RPC

Validation nên được chia theo trách nhiệm thay vì gom tất cả vào một đoạn kiểm tra trong adapter:

| Lớp | Kiểm tra | Ví dụ |
| --- | --- | --- |
| Decode/protocol | Payload có parse được theo Protobuf contract không | Wire format hỏng, message không deserialize được |
| Structural validation | Field có mặt, đúng format, đúng độ dài/miền giá trị | ID rỗng, amount âm, page_size quá lớn |
| Cross-field validation | Các field trong cùng request có nhất quán không | start_time phải trước end_time |
| Application validation | Input phù hợp use case/API contract | Không cho một request chứa quá nhiều item |
| Domain precondition | Trạng thái hiện tại có cho phép thao tác không | Order đã SHIPPED nên không thể CANCEL |

Structural và cross-field validation thường ánh xạ sang INVALID_ARGUMENT. Domain precondition phụ thuộc dữ liệu hiện tại thường ánh xạ sang FAILED_PRECONDITION. Decode error có thể được gRPC runtime xử lý trước khi method service chạy; không nên giả định mọi lỗi deserialize đều đi qua application validator.

Phân lớp giúp client biết cần sửa request hay chờ trạng thái hệ thống thay đổi.

## 3. Validate sớm ở biên, giữ quy tắc nghiệp vụ trong application layer

gRPC adapter là nơi chuyển Protobuf request thành command nội bộ. Có thể kiểm tra nhanh các điều kiện cấu trúc trước khi gọi application service:

```java
@Override
public void createOrder(
        CreateOrderRequest request,
        StreamObserver<CreateOrderReply> observer) {
    try {
        requestValidator.validate(request);

        CreateOrderResult result =
            orderApplicationService.create(
                toCommand(request)
            );

        observer.onNext(toReply(result));
        observer.onCompleted();
    } catch (RequestValidationException ex) {
        observer.onError(exceptionMapper.toStatus(ex));
    } catch (RuntimeException ex) {
        observer.onError(exceptionMapper.toStatus(ex));
    }
}
```

Adapter không nên chứa toàn bộ logic nghiệp vụ. Application service vẫn phải kiểm tra những invariant cần được bảo vệ dù use case được gọi từ gRPC, REST, batch job hoặc message consumer.

Ví dụ: giới hạn số item tối đa trong một request là API/application constraint; kiểm tra tồn kho hiện tại đủ hay không là business rule phụ thuộc trạng thái database. Hai loại lỗi có thể cần status khác nhau.

## 4. Biểu diễn validation violation có cấu trúc

Không nên chỉ ném IllegalArgumentException với một chuỗi chung nếu client cần biết field nào sai. Một violation có thể chứa:

- Field path: đường dẫn field trong request, ví dụ items[2].quantity.
- Rule/code: mã ổn định như REQUIRED, OUT_OF_RANGE hoặc INVALID_FORMAT.
- Message an toàn, ngắn gọn cho developer/client.
- Không chứa secret, token, dữ liệu cá nhân hoặc toàn bộ payload.

Ví dụ model nội bộ:

```java
public record FieldViolation(
    String field,
    String code,
    String description
) {}

public class RequestValidationException
        extends RuntimeException {
    private final List<FieldViolation> violations;

    public RequestValidationException(
            List<FieldViolation> violations) {
        super("Request validation failed");
        this.violations = List.copyOf(violations);
    }

    public List<FieldViolation> getViolations() {
        return violations;
    }
}
```

Mã lỗi nên ổn định để client có thể xử lý; message có thể thay đổi hoặc được bản địa hóa. Không buộc client phân tích chuỗi description để quyết định logic.

Giới hạn số violation trả về, ví dụ chỉ trả tối đa một số lượng nhỏ đầu tiên. Request có hàng nghìn phần tử sai không nên tạo response lỗi khổng lồ hoặc làm tăng tải server.

## 5. Viết validator cho Protobuf request

Ví dụ một request tạo đơn hàng:

```proto
syntax = "proto3";

package commerce.orders.v1;

message OrderLineInput {
  string product_id = 1;
  int32 quantity = 2;
}

message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLineInput items = 2;
  string idempotency_key = 3;
}
```

Validator có thể kiểm tra cấu trúc và các giới hạn độc lập với database:

```java
@Component
public class CreateOrderRequestValidator {

    public void validate(CreateOrderRequest request) {
        List<FieldViolation> errors = new ArrayList<>();

        if (request.getCustomerId().isBlank()) {
            errors.add(new FieldViolation(
                "customer_id", "REQUIRED",
                "customer_id is required"
            ));
        }

        if (request.getItemsCount() == 0) {
            errors.add(new FieldViolation(
                "items", "REQUIRED",
                "At least one item is required"
            ));
        }

        if (request.getItemsCount() > 100) {
            errors.add(new FieldViolation(
                "items", "TOO_MANY",
                "At most 100 items are allowed"
            ));
        }

        for (int i = 0; i < request.getItemsCount(); i++) {
            OrderLineInput item = request.getItems(i);

            if (item.getProductId().isBlank()) {
                errors.add(new FieldViolation(
                    "items[" + i + "].product_id",
                    "REQUIRED",
                    "product_id is required"
                ));
            }

            if (item.getQuantity() <= 0) {
                errors.add(new FieldViolation(
                    "items[" + i + "].quantity",
                    "OUT_OF_RANGE",
                    "quantity must be positive"
                ));
            }

            if (errors.size() >= 20) {
                break;
            }
        }

        if (!errors.isEmpty()) {
            throw new RequestValidationException(errors);
        }
    }
}
```

Validator không truy vấn database để kiểm tra product có tồn tại hay không. Việc đó thuộc application/domain service vì nó phụ thuộc trạng thái hiện tại. Nếu product không tồn tại, có thể trả NOT_FOUND; nếu product tồn tại nhưng ngừng bán, có thể trả FAILED_PRECONDITION theo contract.

## 6. Proto3 default values và field presence

Proto3 scalar field thường có implicit presence: getter trả giá trị mặc định nếu field không được gửi. Với int32, getter có thể trả 0; với bool là false; với string là chuỗi rỗng.

Điều này ảnh hưởng validation:

- Nếu quantity bắt buộc lớn hơn 0, kiểm tra quantity <= 0 là đủ dù không phân biệt absent với zero.
- Nếu cần phân biệt client không gửi field với client chủ động gửi 0, dùng optional, message wrapper phù hợp hoặc oneof.
- Với update/patch, absent có thể có nghĩa “giữ nguyên”; giá trị mặc định có thể có nghĩa “đặt thành 0/false/empty”.
- Với enum, giá trị 0 nên là *_UNSPECIFIED để server nhận biết client chưa chọn giá trị cụ thể.

Ví dụ explicit presence:

```proto
message UpdateLimitRequest {
  string account_id = 1;
  optional int64 daily_limit = 2;
}
```

Server có thể kiểm tra hasDailyLimit() trước khi validate giá trị. Không suy ra field absent chỉ từ getter bằng 0.

Với message field và oneof, Protobuf cung cấp presence theo cấu trúc; hãy dùng semantics này nhất quán trong validator và mapping sang command.

## 7. Validation format, normalization và Unicode

Validation chuỗi không chỉ là kiểm tra độ dài:

- Trim khoảng trắng nếu contract định nghĩa khoảng trắng đầu/cuối không có ý nghĩa.
- Chuẩn hóa Unicode nếu so sánh identifier hoặc tên theo canonical representation.
- Xác định rõ giới hạn theo byte, code point hay ký tự hiển thị.
- Kiểm tra format bằng parser chuyên dụng khi có thể, ví dụ UUID hoặc email.
- Không dùng regex quá phức tạp có thể gây catastrophic backtracking với input lớn.
- Không thay đổi dữ liệu người dùng âm thầm nếu normalization có thể làm thay đổi ý nghĩa.

Với identifier, nên parse thành kiểu domain cụ thể rồi dùng representation canonical. Với free-text, giới hạn byte/code point và áp dụng policy lưu trữ rõ ràng.

Validation không thay thế escaping hoặc parameterized SQL. Dù input đã validate, luôn dùng prepared statement/repository parameter binding để tránh injection.

## 8. Cross-field validation và oneof

Một request có thể chứa các field riêng lẻ hợp lệ nhưng kết hợp lại không hợp lệ.

Ví dụ khoảng thời gian:

```proto
message SearchRequest {
  google.protobuf.Timestamp from = 1;
  google.protobuf.Timestamp to = 2;
}
```

Quy tắc from <= to là cross-field validation. Validator cần kiểm tra cả hai field có mặt theo contract, timestamp hợp lệ và thứ tự thời gian. Nếu khoảng thời gian quá dài vì giới hạn API, có thể trả INVALID_ARGUMENT vì chính request vượt giới hạn được công bố.

Với oneof, Protobuf bảo đảm tối đa một member được chọn trong message đã parse. Tuy nhiên, validator vẫn cần kiểm tra oneof có member bắt buộc hay chưa và nội dung member được chọn có hợp lệ không.

Khi có nhiều violation, trả field path chính xác để client sửa đúng vị trí. Không chỉ trả “request invalid” nếu contract cần hỗ trợ form hoặc batch client.

## 9. Phân biệt INVALID_ARGUMENT và FAILED_PRECONDITION

Đây là ranh giới quan trọng nhất khi mapping:

| Tình huống | Status thường dùng | Vì sao |
| --- | --- | --- |
| amount âm hoặc bằng 0 | INVALID_ARGUMENT | Input sai độc lập với trạng thái hệ thống |
| page_size vượt giới hạn API | INVALID_ARGUMENT | Argument nằm ngoài contract |
| from_time sau to_time | INVALID_ARGUMENT | Các field trong request mâu thuẫn |
| Order đang SHIPPED nên không thể cancel | FAILED_PRECONDITION | Phụ thuộc trạng thái hiện tại của resource |
| Account bị khóa nên không thể debit | FAILED_PRECONDITION | Điều kiện nghiệp vụ hiện tại không cho phép |
| Product ID hợp lệ nhưng không tồn tại | NOT_FOUND | Resource được tham chiếu không có |
| Version đã cũ do concurrent update | ABORTED | Xung đột concurrency |
| Database tạm không kết nối được | UNAVAILABLE | Lỗi hạ tầng |

Một câu hỏi hữu ích: “Nếu trạng thái database thay đổi nhưng request giữ nguyên, request có trở nên hợp lệ không?” Nếu có, lỗi thường phụ thuộc state và nên cân nhắc FAILED_PRECONDITION. Nếu không, lỗi thường thuộc INVALID_ARGUMENT.

Không dùng INVALID_ARGUMENT để che giấu thiếu quyền; trường hợp đó thường là PERMISSION_DENIED hoặc policy hide-existence đã công bố.

## 10. Ánh xạ validation exception sang INVALID_ARGUMENT

Mapper tập trung giúp mọi RPC trả status nhất quán:

```java
@Component
public class GrpcExceptionMapper {

    public StatusRuntimeException toStatus(Throwable error) {
        if (error instanceof RequestValidationException ex) {
            return Status.INVALID_ARGUMENT
                .withDescription("Request validation failed")
                .asRuntimeException();
        }

        if (error instanceof ResourceNotFoundException) {
            return Status.NOT_FOUND
                .withDescription("Resource not found")
                .asRuntimeException();
        }

        if (error instanceof BusinessPreconditionException) {
            return Status.FAILED_PRECONDITION
                .withDescription("Operation is not allowed")
                .asRuntimeException();
        }

        return Status.INTERNAL
            .withDescription("Unexpected server error")
            .asRuntimeException();
    }
}
```

Trong production, có thể đính kèm danh sách field violations bằng rich error model như google.rpc.BadRequest và StatusProto nếu hệ thống đã dùng grpc-status-details. Khi làm vậy, giữ error code ổn định, giới hạn số violation và không đưa giá trị input nhạy cảm vào detail.

Không gửi stack trace, SQL hoặc exception message nội bộ. Log server lưu cause và correlation ID; client nhận thông tin đủ để sửa request.

## 11. Validate trước database work

Validation cấu trúc nên chạy trước khi lấy connection hoặc mở transaction nếu có thể:

1. Decode request.
2. Validate field presence, format, length và range.
3. Validate cross-field consistency.
4. Tạo command nội bộ.
5. Mở transaction và kiểm tra domain state/database.
6. Commit rồi trả response.

Cách này tránh query vô ích cho request sai và giảm thời gian chiếm connection pool. Tuy nhiên, validation phụ thuộc database như “customer có tồn tại không” phải nằm trong use case/transaction và cần xử lý race condition phù hợp.

Không dựa vào validation ở client. Client có thể cũ, bị lỗi hoặc cố ý gửi payload không hợp lệ; server luôn phải xác thực lại.

## 12. Batch validation và giới hạn tài nguyên

Với RPC nhận danh sách lớn, validation bản thân nó cũng tiêu thụ CPU và memory:

- Đặt giới hạn số item và tổng payload trước khi duyệt sâu.
- Giới hạn số violation được trả về.
- Dừng sớm khi request vượt giới hạn cấu trúc nghiêm trọng.
- Không giữ toàn bộ normalized copy nếu có thể validate theo từng phần.
- Với batch import cho phép partial result, contract phải nói rõ item nào được chấp nhận và item nào bị từ chối.
- Với batch atomic, validate toàn bộ trước khi bắt đầu transaction ghi dữ liệu.

Nếu request vượt giới hạn kích thước transport hoặc không parse được, lỗi có thể xảy ra trước application validator; cấu hình message size và gRPC runtime cần phù hợp. Không dùng INVALID_ARGUMENT để thay thế quota/rate limiting nếu nguyên nhân thực sự là RESOURCE_EXHAUSTED.

## 13. Kiểm thử mapping validation

Cần test validator, application service và gRPC status:

| Test | Điều cần xác nhận |
| --- | --- |
| Required field rỗng | Validation violation đúng field path |
| Số lượng âm/zero | INVALID_ARGUMENT |
| Page size vượt giới hạn | INVALID_ARGUMENT |
| Cross-field range sai | INVALID_ARGUMENT |
| Optional field absent | Presence semantics đúng |
| Enum UNSPECIFIED/unknown | Không bị hiểu thành giá trị hợp lệ |
| Resource không tồn tại | NOT_FOUND, không phải INVALID_ARGUMENT |
| Resource tồn tại nhưng trạng thái cấm | FAILED_PRECONDITION |
| Database outage | Không bị ánh xạ thành INVALID_ARGUMENT |
| Batch quá lớn | Bị chặn trước database work |
| Error detail | Không chứa secret hoặc raw payload |

Ví dụ gRPC integration test:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> blockingStub.createOrder(
        CreateOrderRequest.newBuilder()
            .setCustomerId("")
            .build()
    )
);

assertEquals(
    Status.Code.INVALID_ARGUMENT,
    Status.fromThrowable(error).getCode()
);
```

Ngoài status code, kiểm tra error details/field path nếu contract cung cấp. Test qua server thật để bảo đảm adapter hoặc exception interceptor thực sự chuyển exception thành status đúng.

## 14. Checklist review

- Structural, cross-field và domain validation được phân lớp rõ.
- Request được validate ở server; không tin validation từ client.
- Proto3 presence/default semantics được hiểu đúng.
- Identifier, string length, numeric range và enum được kiểm tra.
- Field path và error code ổn định; violation count có giới hạn.
- Application service giữ invariant ngay cả khi được gọi từ adapter khác.
- INVALID_ARGUMENT chỉ dùng cho input không hợp lệ.
- FAILED_PRECONDITION dùng cho trạng thái hiện tại không cho phép thao tác.
- NOT_FOUND, PERMISSION_DENIED, ABORTED, OUT_OF_RANGE và UNAVAILABLE không bị gom nhầm.
- Validation cấu trúc chạy trước database work khi có thể.
- Batch và payload có giới hạn tài nguyên.
- Error details không rò rỉ dữ liệu nhạy cảm hoặc nội bộ.
- Có unit và gRPC integration tests cho status mapping và các trường hợp dễ nhầm.

Trong **SPRING_GRPC**, INVALID_ARGUMENT cho client biết request phải được sửa trước khi gửi lại. Hãy validate cấu trúc và tính nhất quán của Protobuf request ở biên, giữ invariant nghiệp vụ trong application layer, rồi ánh xạ typed validation violations thành status tại biên gRPC. Phân biệt input sai với resource missing, business precondition, permission và database failure để client chọn đúng cách khắc phục.
