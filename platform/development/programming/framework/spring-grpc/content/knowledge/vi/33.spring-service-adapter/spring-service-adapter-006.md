# Mapping domain error sang Status

Trong **SPRING_GRPC**, service adapter là ranh giới giữa hợp đồng Protocol Buffers và application/domain layer. Adapter nhận request protobuf, chuyển thành lệnh nghiệp vụ, gọi application service, rồi chuyển kết quả về response protobuf. Khi nghiệp vụ thất bại, adapter phải chuyển lỗi domain thành gRPC `Status` phù hợp để client hiểu nguyên nhân và quyết định cách xử lý.

Không nên để domain model phụ thuộc vào `io.grpc.Status` hoặc `StatusRuntimeException`. Domain mô tả điều gì sai theo ngôn ngữ nghiệp vụ; adapter quyết định cách biểu diễn lỗi đó trên giao thức gRPC. Bài này tập trung vào quy tắc mapping, cách triển khai ở unary/streaming RPC, thông tin lỗi an toàn và kiểm thử status.

## 1. Phân biệt domain error và gRPC Status

Một lỗi domain biểu diễn vi phạm quy tắc hoặc trạng thái nghiệp vụ, ví dụ:

- Không tìm thấy mặt hàng tồn kho.
- Số lượng đặt trước lớn hơn số lượng khả dụng.
- Phiên bản dữ liệu không còn khớp khi cập nhật.
- Mã SKU không hợp lệ.
- Đơn hàng đã tồn tại.

gRPC `Status` là cách giao thức biểu diễn kết quả RPC. Nó gồm status code, mô tả tùy chọn và có thể có metadata/trailer hoặc structured details.

| Tầng | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Domain | Nêu lỗi theo ngôn ngữ nghiệp vụ | `StockNotFoundException` |
| Application service | Điều phối use case và giữ quy tắc nghiệp vụ | `reserveStock()` |
| gRPC service adapter | Chuyển request/response và map domain error | `StockGrpcService` |
| gRPC transport | Trả status tới client | `NOT_FOUND` |

Nếu domain trực tiếp ném `StatusRuntimeException`, business code sẽ bị gắn với gRPC. Khi cùng use case được gọi từ REST, message queue hoặc batch job, các adapter khác phải hiểu một ngoại lệ thuộc transport gRPC.

Hãy giữ domain exception độc lập với giao thức. Chỉ adapter hoặc lớp tích hợp gRPC mới cần import `io.grpc.Status`.

## 2. Chọn Status code theo ý nghĩa nghiệp vụ

Status code không chỉ là thông báo lỗi. Client, retry policy, monitoring và API consumer có thể dựa vào code để quyết định hành động.

| Domain condition | gRPC Status | Khi nào dùng |
| --- | --- | --- |
| Request sai định dạng hoặc tham số không hợp lệ | `INVALID_ARGUMENT` | Lỗi có thể xác định từ request, không phụ thuộc trạng thái hệ thống |
| Tài nguyên không tồn tại | `NOT_FOUND` | SKU hoặc order được tham chiếu không có |
| Tạo tài nguyên đã tồn tại | `ALREADY_EXISTS` | Trùng mã định danh hoặc khóa duy nhất |
| Trạng thái hiện tại không cho phép thao tác | `FAILED_PRECONDITION` | Không đủ hàng để reserve, order chưa ở trạng thái được thanh toán |
| Xung đột cập nhật đồng thời | `ABORTED` | Optimistic locking hoặc transaction conflict |
| Giá trị nằm ngoài miền hợp lệ | `OUT_OF_RANGE` | Index/cursor vượt phạm vi hoặc giá trị đo nằm ngoài miền được định nghĩa |
| Hết quota hoặc tài nguyên có giới hạn | `RESOURCE_EXHAUSTED` | Rate/quota limit, dung lượng hoặc capacity bị cạn |
| Chưa xác thực được caller | `UNAUTHENTICATED` | Token thiếu, sai hoặc hết hạn |
| Caller đã xác thực nhưng không đủ quyền | `PERMISSION_DENIED` | Principal không có authority cho RPC |
| Phụ thuộc tạm thời không khả dụng | `UNAVAILABLE` | Service downstream hoặc transport tạm thời không phục vụ |
| Deadline của RPC đã hết | `DEADLINE_EXCEEDED` | Thời gian thực thi vượt deadline |
| Caller hủy RPC | `CANCELLED` | Client đã hủy lời gọi |
| Lỗi bất ngờ trong server | `INTERNAL` | Lỗi nội bộ không thuộc trường hợp đã định nghĩa |

Một số phân biệt quan trọng:

- `INVALID_ARGUMENT` mô tả request sai dù hệ thống đang ở trạng thái nào.
- `FAILED_PRECONDITION` mô tả request có thể hợp lệ nhưng trạng thái hiện tại không cho phép thực hiện.
- `ABORTED` phù hợp với xung đột cần retry một chuỗi thao tác ở mức cao hơn.
- `RESOURCE_EXHAUSTED` dành cho quota/capacity thực sự, không phải cách chung để báo mọi lỗi nghiệp vụ.
- `UNAVAILABLE` có thể phù hợp cho lỗi tạm thời, nhưng không có nghĩa mọi request đều an toàn để retry.
- `INTERNAL` dùng cho lỗi bất ngờ; không gửi stack trace hoặc thông tin hạ tầng vào description trả cho client.

## 3. Tạo domain exception không phụ thuộc gRPC

Ví dụ domain tồn kho:

```java
public abstract class StockDomainException extends RuntimeException {
    protected StockDomainException(String message) {
        super(message);
    }
}

public final class StockNotFoundException
        extends StockDomainException {
    public StockNotFoundException(String sku) {
        super("Stock item not found: " + sku);
    }
}

public final class InsufficientStockException
        extends StockDomainException {
    public InsufficientStockException(String sku) {
        super("Insufficient stock for: " + sku);
    }
}

public final class StockVersionConflictException
        extends StockDomainException {
    public StockVersionConflictException() {
        super("Stock version changed");
    }
}
```

Application service ném lỗi theo nghiệp vụ:

```java
public Stock reserve(String sku, long quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    Stock stock = repository.findBySku(sku)
            .orElseThrow(() -> new StockNotFoundException(sku));

    if (stock.available() < quantity) {
        throw new InsufficientStockException(sku);
    }

    return repository.reserve(
            sku, quantity, stock.version());
}
```

Trong ứng dụng thực tế, có thể dùng một hierarchy `DomainException` chung với error key ổn định, hoặc các exception cụ thể. Điều quan trọng là application/domain layer không cần biết status code gRPC.

Không nên dùng `IllegalArgumentException` cho mọi lỗi nghiệp vụ. Hãy phân biệt lỗi request được adapter validate với lỗi domain như không đủ hàng hoặc xung đột version. Nếu cần, định nghĩa exception riêng để mapper không phải suy đoán từ message string.

## 4. Viết mapper tập trung tại gRPC adapter

Một mapper tập trung giúp các RPC dùng cùng một quy tắc và tránh việc mỗi method tự chọn status khác nhau cho cùng một lỗi.

Ví dụ:

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class GrpcStatusMapper {

    public StatusRuntimeException map(Throwable error) {
        if (error instanceof StockNotFoundException) {
            return Status.NOT_FOUND
                    .withDescription("Stock item not found")
                    .asRuntimeException();
        }

        if (error instanceof InsufficientStockException) {
            return Status.FAILED_PRECONDITION
                    .withDescription("Insufficient stock")
                    .asRuntimeException();
        }

        if (error instanceof StockVersionConflictException) {
            return Status.ABORTED
                    .withDescription("Stock was modified concurrently")
                    .asRuntimeException();
        }

        if (error instanceof IllegalArgumentException) {
            return Status.INVALID_ARGUMENT
                    .withDescription("Request contains an invalid value")
                    .asRuntimeException();
        }

        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }
}
```

Mapper trả mô tả an toàn, ổn định và không phụ thuộc message nội bộ của exception. Không đưa SQL, tên bảng, stack trace, đường dẫn file, token hoặc secret vào status description.

Có thể bổ sung các exception như `OrderAlreadyExistsException` → `ALREADY_EXISTS`, `QuotaExceededException` → `RESOURCE_EXHAUSTED` hoặc `AccessDeniedException` → `PERMISSION_DENIED`. Không map mọi exception không nhận diện thành `INVALID_ARGUMENT`; lỗi đó thường không phải do client.

### 4.1. Giữ nguyên nguyên nhân cho log, không gửi nguyên nhân cho client

Mapper không nên log toàn bộ exception rồi lại để interceptor khác log cùng lỗi, gây duplicate. Chọn một nơi chịu trách nhiệm ghi log với request ID/correlation ID.

Đối với lỗi bất ngờ, log exception đầy đủ ở server:

```java
log.error("Unexpected error while handling GetStock, requestId={}",
        requestId, error);
```

Client chỉ nhận `INTERNAL` với mô tả tổng quát. Đối với lỗi domain đã biết, log ở mức phù hợp (thường `DEBUG` hoặc `INFO` tùy tần suất) để tránh biến các lỗi nghiệp vụ bình thường thành cảnh báo hệ thống.

## 5. Áp dụng mapping trong unary service adapter

Generated server base class cung cấp method nhận request và `StreamObserver` cho response. Adapter gọi application service, map kết quả, rồi kết thúc observer đúng một lần.

```java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class StockGrpcService
        extends StockServiceGrpc.StockServiceImplBase {

    private final StockApplicationService applicationService;
    private final GrpcStatusMapper statusMapper;

    public StockGrpcService(
            StockApplicationService applicationService,
            GrpcStatusMapper statusMapper) {
        this.applicationService = applicationService;
        this.statusMapper = statusMapper;
    }

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        try {
            Stock stock = applicationService.find(request.getSku());
            observer.onNext(toReply(stock));
            observer.onCompleted();
        } catch (StockDomainException
                 | IllegalArgumentException error) {
            observer.onError(statusMapper.map(error));
        } catch (RuntimeException error) {
            log.error("Unexpected GetStock failure", error);
            observer.onError(Status.INTERNAL
                    .withDescription("Internal server error")
                    .asRuntimeException());
        }
    }

    private StockReply toReply(Stock stock) {
        return StockReply.newBuilder()
                .setSku(stock.sku())
                .setAvailable(stock.available())
                .build();
    }
}
```

Đây là ví dụ rút gọn; `log` cần được khai báo theo logging framework của ứng dụng. Có thể đưa xử lý lỗi bất ngờ vào mapper nếu muốn một điểm duy nhất quản lý cả status lẫn log policy.

Các nguyên tắc cần giữ:

- Chỉ gọi `onNext` khi đã có response hợp lệ.
- Gọi `onCompleted` sau response thành công.
- Gọi `onError` khi thất bại; không gọi thêm `onCompleted` sau `onError`.
- Không bắt `Throwable` một cách tùy tiện vì có thể nuốt lỗi nghiêm trọng của JVM.
- Không trả exception message thô từ domain ra client nếu message đó có thể chứa dữ liệu nhạy cảm.

Nếu request không hợp lệ ngay ở adapter, có thể validate trước khi gọi application service và trả `INVALID_ARGUMENT`. Quy tắc nghiệp vụ sâu hơn vẫn nên được xác thực ở application/domain layer để các entry point khác cũng được bảo vệ.

## 6. Mapping cho streaming RPC

Với server-streaming hoặc bidirectional streaming, lỗi có thể xuất hiện sau khi một số message đã được gửi. Khi đó server không thể đổi các message đã gửi thành một response lỗi khác; nó kết thúc stream bằng `onError`.

Ví dụ server-streaming:

```java
@Override
public void watchStock(
        StockRequest request,
        StreamObserver<StockReply> observer) {

    try {
        for (Stock stock : applicationService.watch(request.getSku())) {
            observer.onNext(toReply(stock));
        }
        observer.onCompleted();
    } catch (StockDomainException error) {
        observer.onError(statusMapper.map(error));
    } catch (RuntimeException error) {
        log.error("Unexpected WatchStock failure", error);
        observer.onError(Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException());
    }
}
```

Trong code production, cần xét thêm cancellation, backpressure và vòng đời publisher/stream. Nếu client hủy RPC, dừng việc phát dữ liệu và giải phóng tài nguyên. Không tiếp tục gửi `onNext` sau terminal signal.

Với client-streaming/bidirectional streaming, lỗi có thể xảy ra trong `onNext`, `onCompleted` hoặc xử lý bất đồng bộ. Hãy chuyển lỗi sang đúng observer response và bảo đảm chỉ có một terminal signal. Không dựa vào một `try/catch` bao quanh lúc tạo observer để bắt các exception phát sinh sau đó trên callback/thread khác.

## 7. Trả structured error details khi cần

Status code và description thường đủ cho lỗi đơn giản. Với validation nhiều field hoặc lỗi cần machine-readable metadata, có thể dùng chuẩn Google RPC error details (`google.rpc.Status`, `BadRequest`, `ErrorInfo`, `RetryInfo`).

Ví dụ trả danh sách field validation:

```java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;

BadRequest details = BadRequest.newBuilder()
        .addFieldViolations(
                BadRequest.FieldViolation.newBuilder()
                        .setField("quantity")
                        .setDescription("must be greater than zero"))
        .build();

com.google.rpc.Status status =
        com.google.rpc.Status.newBuilder()
                .setCode(io.grpc.Status.Code.INVALID_ARGUMENT.value())
                .setMessage("Request validation failed")
                .addDetails(Any.pack(details))
                .build();

StatusRuntimeException error =
        StatusProto.toStatusRuntimeException(status);
```

Client có thể dùng `StatusProto.fromThrowable(error)` để đọc structured details và xử lý theo type. Dependency thường cần có `io.grpc:grpc-protobuf` và `com.google.api.grpc:proto-google-common-protos` theo version được quản lý bởi BOM phù hợp.

Chỉ đưa dữ liệu cần thiết cho client vào details. Không gửi stack trace, nội dung database, thông tin xác thực hoặc dữ liệu cá nhân không cần thiết. Client không hiểu rich details vẫn phải có thể xử lý status code cơ bản.

## 8. Metadata trailers và error contract

gRPC có thể đính kèm metadata trailers cùng status cuối. Trailers phù hợp cho thông tin kỹ thuật ngắn như error identifier hoặc correlation ID, nhưng không nên biến chúng thành nơi truyền payload lỗi lớn.

Ví dụ gắn error ID:

```java
Metadata trailers = new Metadata();
Metadata.Key<String> errorIdKey =
        Metadata.Key.of("error-id", Metadata.ASCII_STRING_MARSHALLER);

trailers.put(errorIdKey, errorId);

observer.onError(Status.INTERNAL
        .withDescription("Internal server error")
        .asRuntimeException(trailers));
```

Định nghĩa key metadata nhất quán giữa server và client. Không đưa token, secret hoặc exception message thô vào trailers. Nếu cần lỗi có cấu trúc và đa ngôn ngữ, ưu tiên schema details được version hóa thay vì parsing description text.

## 9. Status code ảnh hưởng retry như thế nào?

Mapping sai status có thể khiến client retry lỗi nghiệp vụ hoặc bỏ qua lỗi tạm thời.

| Status | Hướng xử lý thường gặp |
| --- | --- |
| `INVALID_ARGUMENT` | Sửa request; không retry nguyên trạng |
| `NOT_FOUND` | Kiểm tra resource/key; thường không retry ngay |
| `ALREADY_EXISTS` | Đọc resource hiện có hoặc đổi khóa |
| `FAILED_PRECONDITION` | Thay đổi trạng thái nghiệp vụ trước khi gọi lại |
| `ABORTED` | Có thể retry toàn bộ transaction/use case ở mức cao hơn |
| `RESOURCE_EXHAUSTED` | Tôn trọng quota và retry delay nếu server cung cấp |
| `UNAVAILABLE` | Có thể retry với backoff nếu thao tác an toàn và deadline còn đủ |
| `DEADLINE_EXCEEDED` | Kết quả có thể chưa rõ; kiểm tra idempotency trước khi retry |
| `UNAUTHENTICATED` | Làm mới credential nếu có thể, sau đó thử lại có giới hạn |
| `PERMISSION_DENIED` | Sửa quyền; không retry liên tục |
| `INTERNAL` | Điều tra server; không mặc định retry vô hạn |

Một số thao tác có thể đã hoàn tất ở server dù client nhận `DEADLINE_EXCEEDED` do response về muộn. Với lệnh tạo đơn, thanh toán hoặc reserve tài nguyên, dùng idempotency key để tránh thực hiện trùng khi client retry.

Không map lỗi database timeout thành `INVALID_ARGUMENT`. Nếu lỗi thực sự tạm thời, `UNAVAILABLE` có thể phù hợp; nếu không xác định được trạng thái giao dịch, chọn code và chính sách retry dựa trên semantics của use case.

## 10. Kiểm thử mapping và RPC contract

### 10.1. Unit test cho mapper

Kiểm tra domain exception được chuyển thành đúng code:

```java
import io.grpc.Status;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GrpcStatusMapperTest {

    private final GrpcStatusMapper mapper = new GrpcStatusMapper();

    @Test
    void mapsMissingStockToNotFound() {
        var error = mapper.map(new StockNotFoundException("BOOK-101"));

        assertEquals(
                Status.Code.NOT_FOUND,
                Status.fromThrowable(error).getCode());
    }

    @Test
    void mapsInsufficientStockToFailedPrecondition() {
        var error = mapper.map(
                new InsufficientStockException("BOOK-101"));

        assertEquals(
                Status.Code.FAILED_PRECONDITION,
                Status.fromThrowable(error).getCode());
    }
}
```

Unit test tập trung vào quy tắc mapping, không cần khởi động gRPC server.

### 10.2. Integration test cho service adapter

Gọi generated stub để xác nhận status thực sự tới client:

```java
@Test
void missingStockReturnsNotFoundToGrpcClient() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> blockingStub.getStock(
                    StockRequest.newBuilder()
                            .setSku("MISSING")
                            .build()));

    assertEquals(
            Status.Code.NOT_FOUND,
            Status.fromThrowable(error).getCode());
}
```

Integration test này xác nhận adapter gọi `onError` với status đúng và transport trả status tới client. Bổ sung test cho `INVALID_ARGUMENT`, `FAILED_PRECONDITION`, lỗi bất ngờ `INTERNAL` và streaming terminal error.

Nếu dùng rich details, kiểm tra `StatusProto.fromThrowable(error)` và unpack đúng detail type. Đừng chỉ assert description text vì description có thể thay đổi hoặc được bản địa hóa.

## 11. Những lỗi mapping thường gặp

| Cách làm sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Map mọi exception thành `INTERNAL` | Client không phân biệt lỗi nghiệp vụ | Map domain exception cụ thể |
| Map mọi lỗi thành `INVALID_ARGUMENT` | Retry/monitoring sai và đổ lỗi cho client | Chọn code theo nguyên nhân |
| Trả `exception.getMessage()` nguyên vẹn | Có thể lộ SQL, dữ liệu hoặc chi tiết nội bộ | Dùng description an toàn |
| Domain ném `StatusRuntimeException` | Domain phụ thuộc gRPC | Giữ domain exception thuần |
| Gọi `onError` rồi tiếp tục `onNext` | Vi phạm terminal semantics của stream | Dừng xử lý sau terminal signal |
| Bắt lỗi chỉ ở lúc tạo stream | Bỏ sót lỗi callback bất đồng bộ | Xử lý lỗi trong lifecycle của stream |
| Dùng `UNAVAILABLE` cho lỗi nghiệp vụ cố định | Client retry vô ích | Dùng status thể hiện điều kiện thực tế |
| Retry lệnh không idempotent sau timeout | Có thể tạo tác động trùng | Thiết kế idempotency và deadline |

## 12. Bài tập thực hành

1. Tạo `StockNotFoundException`, `InsufficientStockException` và `StockVersionConflictException` trong domain layer.
2. Viết `GrpcStatusMapper` ánh xạ lần lượt thành `NOT_FOUND`, `FAILED_PRECONDITION` và `ABORTED`.
3. Thêm validation request và trả `INVALID_ARGUMENT` cho SKU rỗng hoặc quantity không hợp lệ.
4. Dùng service adapter kế thừa generated `StockServiceGrpc.StockServiceImplBase` và gọi `observer.onError` khi application service ném domain exception.
5. Viết unit test cho từng nhánh mapper và nhánh fallback `INTERNAL`.
6. Viết integration test gọi generated stub và assert status code nhận được.
7. Bổ sung `google.rpc.BadRequest` cho validation nhiều field và kiểm tra client unpack detail.
8. Viết server-streaming test trong đó lỗi xuất hiện sau một số message; xác nhận stream kết thúc bằng một terminal error.
9. Thử retry với `UNAVAILABLE` và `ABORTED`; xác nhận không retry request không idempotent khi chưa có idempotency key.
10. Review log/trailers để bảo đảm không rò rỉ stack trace, token, secret hoặc dữ liệu nhạy cảm.

### Ghi nhớ

**Domain error mô tả thất bại nghiệp vụ; gRPC Status là cách service adapter công bố thất bại đó qua RPC.** Giữ domain exception độc lập với gRPC, map theo semantics thay vì theo tên exception tùy tiện, kết thúc observer đúng một lần và chỉ gửi mô tả an toàn. Kiểm thử cả mapper lẫn status nhìn thấy từ client; nếu status có thể dẫn tới retry, phải xét deadline và idempotency của thao tác.

## Tài liệu tham khảo

- [gRPC — Status Codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC — Error Handling](https://grpc.io/docs/guides/error/)
- [gRPC Java — Status](https://grpc.github.io/grpc-java/javadoc/io/grpc/Status.html)
- [gRPC Java — StatusRuntimeException](https://grpc.github.io/grpc-java/javadoc/io/grpc/StatusRuntimeException.html)
- [Google API — Error Model](https://cloud.google.com/apis/design/errors)
