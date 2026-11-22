# Test INTERNAL không làm lộ chi tiết

Trong **SPRING_GRPC**, khi một lỗi bất ngờ xảy ra trong application use case hoặc hạ tầng, gRPC adapter thường phải trả `INTERNAL` cho client. Status này cho biết server không thể hoàn tất RPC vì lỗi nội bộ. Nó không nên tiết lộ SQL, tên bảng, stack trace, đường dẫn file, hostname, token, secret hoặc message kỹ thuật từ exception.

Một error response an toàn vẫn cần giúp client và đội vận hành tra cứu sự cố. Cách làm phù hợp là trả status `INTERNAL` với description ổn định, kèm một error ID không nhạy cảm qua metadata trailers; phía server ghi nhận error ID và thông tin chẩn đoán theo chính sách log. Bài này trình bày cách thiết kế contract đó và kiểm thử từ mapper, adapter đến góc nhìn client.

## 1. Xác định điều gì được phép lộ ra client

Một exception nội bộ có thể chứa thông tin không thuộc public API:

```text
org.postgresql.util.PSQLException:
  ERROR: duplicate key value violates unique constraint
  Detail: Key (email)=(alice@example.test) already exists.
  SQL: INSERT INTO customer ...
  Connection: jdbc:postgresql://db-prod-03.internal:5432/customer
```

Nếu adapter trả trực tiếp `exception.getMessage()` hoặc stack trace trong Status, client có thể biết cấu trúc database, dữ liệu người dùng, hostname nội bộ hoặc cách triển khai server.

Định nghĩa rõ public error contract:

| Thành phần | Có thể trả cho client? | Quy tắc |
| --- | --- | --- |
| gRPC code `INTERNAL` | Có | Ổn định, máy khách có thể phân loại |
| Description `Internal server error` | Có | Thông điệp chung, không phụ thuộc exception |
| Error ID | Có | Giá trị ngẫu nhiên/duy nhất để tra cứu |
| Exception class | Không cần | Giữ ở telemetry/log nội bộ nếu được phép |
| Exception message | Không | Có thể chứa SQL, dữ liệu hoặc secret |
| Stack trace | Không | Chỉ phục vụ chẩn đoán nội bộ có kiểm soát |
| SQL, hostname, file path | Không | Chi tiết triển khai nội bộ |
| Token, password, key | Không | Secret tuyệt đối không đưa vào response |

Client cần biết RPC thất bại ở mức nào và cung cấp error ID khi báo sự cố. Client không cần biết server dùng database nào, câu SQL nào thất bại hoặc exception được ném từ dòng code nào.

## 2. Giữ mapping lỗi đã biết riêng với lỗi bất ngờ

Không phải mọi lỗi đều là `INTERNAL`. Lỗi có ý nghĩa công khai và đã được định nghĩa phải giữ status tương ứng:

- Request không hợp lệ: `INVALID_ARGUMENT`.
- Tài nguyên không tồn tại: `NOT_FOUND`.
- Caller chưa xác thực: `UNAUTHENTICATED`.
- Caller không đủ quyền: `PERMISSION_DENIED`.
- Xung đột trạng thái nghiệp vụ: `FAILED_PRECONDITION` hoặc `ABORTED` theo semantics.
- Lỗi không dự kiến ở server: `INTERNAL`.

Không biến lỗi nghiệp vụ đã biết thành `INTERNAL` chỉ vì muốn che exception message. Hãy map lỗi đã biết bằng status public phù hợp và dùng description an toàn. Quy tắc của bài này áp dụng cho lỗi bất ngờ mà client không thể xử lý bằng một contract nghiệp vụ cụ thể.

## 3. Tạo error ID và metadata trailer

Error ID nên là mã ngẫu nhiên hoặc định danh duy nhất, không chứa user ID, email, tenant name, SQL key hay dữ liệu nghiệp vụ. UUID là lựa chọn đơn giản.

Khai báo metadata key:

```java
import io.grpc.Metadata;

public final class GrpcErrorMetadata {

    private GrpcErrorMetadata() {
    }

    public static final Metadata.Key<String> ERROR_ID =
            Metadata.Key.of(
                    "x-error-id",
                    Metadata.ASCII_STRING_MARSHALLER);
}
```

Tạo mapper chỉ chịu trách nhiệm dựng response công khai:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class GrpcInternalErrorMapper {

    public StatusRuntimeException toInternal(String errorId) {
        Metadata trailers = new Metadata();
        trailers.put(GrpcErrorMetadata.ERROR_ID, errorId);

        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException(trailers);
    }
}
```

Mapper không nhận exception message để tránh vô tình đưa message đó vào description hoặc trailers. Error ID được tạo ở adapter/error handler, sau đó dùng chung cho log và response.

Không đính kèm `DebugInfo`, stack trace hoặc `google.rpc.ErrorInfo` chứa thông tin triển khai vào một lỗi `INTERNAL` công khai. Nếu API cần machine-readable error category, chỉ gửi reason code đã được duyệt và ổn định; error ID vẫn là cách tra cứu sự cố cụ thể.

## 4. Ghi nhận lỗi nội bộ có kiểm soát

Adapter tạo error ID, ghi log chẩn đoán và trả response chung:

```java
private static final Logger log =
        LoggerFactory.getLogger(CatalogGrpcService.class);

private final Supplier<String> errorIdSupplier;
private final GrpcInternalErrorMapper internalErrors;

private void reportUnexpected(
        RuntimeException cause,
        StreamObserver<?> observer) {

    String errorId = errorIdSupplier.get();

    // Chỉ ghi các trường đã được duyệt; không ghi message hoặc payload.
    log.error(
            "Unexpected gRPC failure: errorId={}, exceptionType={}",
            errorId,
            cause.getClass().getName());

    observer.onError(internalErrors.toInternal(errorId));
}
```

Cách log trên tránh đưa `cause.getMessage()` hoặc stack trace có thể chứa dữ liệu nhạy cảm vào log ứng dụng thông thường. Nếu cần stack trace để điều tra, gửi nó tới diagnostic sink có quyền truy cập hạn chế và cơ chế redaction phù hợp. Không bật log toàn bộ request protobuf hoặc raw metadata để tìm nguyên nhân.

Trong service method:

```java
@Override
public void getItem(
        GetItemRequest request,
        StreamObserver<GetItemReply> observer) {
    try {
        ItemView item = getItemUseCase.execute(
                new GetItemQuery(request.getItemId()));

        observer.onNext(mapper.toProto(item));
        observer.onCompleted();
    } catch (ItemNotFoundException error) {
        observer.onError(Status.NOT_FOUND
                .withDescription("Item not found")
                .asRuntimeException());
    } catch (RuntimeException error) {
        reportUnexpected(error, observer);
    }
}
```

Ví dụ chỉ map một domain error đã biết và gom lỗi bất ngờ vào một đường xử lý. Trong ứng dụng lớn, có thể đặt logic này trong error handler/interceptor dùng chung để các adapter không lặp code.

Không bắt `Throwable` để map mọi thứ thành `INTERNAL`. Các lỗi nghiêm trọng của JVM như `OutOfMemoryError` không nên bị xử lý như một lỗi RPC thông thường.

## 5. Những nơi dễ làm rò rỉ exception detail

Kiểm tra toàn bộ đường đi của lỗi, không chỉ `Status.withDescription`:

1. **Status description**: không dùng `exception.getMessage()`, `toString()` hoặc stack trace.
2. **Metadata trailers**: chỉ đưa error ID hoặc key public đã được cho phép.
3. **Rich error details**: không pack `DebugInfo`, SQL detail hoặc object exception.
4. **Application logs**: không ghi raw token, request payload hoặc message chưa được redaction.
5. **Tracing attributes**: không gắn exception message, SQL parameter hoặc dữ liệu cá nhân vào span tag.
6. **Metrics labels**: không dùng error ID, user ID hoặc exception message làm label có cardinality cao.
7. **Gateway/proxy**: xác nhận lớp trung gian không thay status thành body chứa exception detail.

Error ID nên xuất hiện trong log và trailers với cùng một giá trị. Client gửi ID này cho đội hỗ trợ; người vận hành tìm log theo ID để tra cứu. Không dùng error ID làm authorization credential hoặc cho phép người có ID đọc log trực tiếp.

## 6. Unit test cho error mapper

Unit test kiểm tra code, description, trailers và sự vắng mặt của dữ liệu nội bộ:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class GrpcInternalErrorMapperTest {

    private final GrpcInternalErrorMapper mapper =
            new GrpcInternalErrorMapper();

    @Test
    void returnsGenericInternalWithOnlyErrorIdTrailer() {
        String errorId = "err-test-42";
        StatusRuntimeException result = mapper.toInternal(errorId);

        Status status = Status.fromThrowable(result);
        Metadata trailers = Status.trailersFromThrowable(result);

        assertEquals(Status.Code.INTERNAL, status.getCode());
        assertEquals("Internal server error", status.getDescription());
        assertNotNull(trailers);
        assertEquals(
                errorId,
                trailers.get(GrpcErrorMetadata.ERROR_ID));
        assertEquals(
                Set.of("x-error-id"),
                trailers.keys());
        assertNull(result.getCause());
    }
}
```

Test xác nhận mapper không nhận exception và không gắn cause vào exception gửi cho client. Nếu contract cho phép thêm trailer khác, hãy thay assertion tập key bằng allowlist rõ ràng và kiểm tra từng value.

## 7. Test adapter khi use case ném lỗi chứa secret

Một test quan trọng phải dùng exception message cố ý chứa dữ liệu nhạy cảm giả lập, rồi xác nhận dữ liệu đó không xuất hiện trong observer error:

```java
@Test
void unexpectedFailureDoesNotExposeExceptionMessage() {
    String secret = "db-password=not-for-client";
    RuntimeException failure =
            new IllegalStateException(secret);

    when(getItem.execute(new GetItemQuery("item-42")))
            .thenThrow(failure);

    List<GetItemReply> values = new ArrayList<>();
    AtomicReference<Throwable> receivedError = new AtomicReference<>();
    AtomicBoolean completed = new AtomicBoolean();

    StreamObserver<GetItemReply> observer = new StreamObserver<>() {
        @Override
        public void onNext(GetItemReply value) {
            values.add(value);
        }

        @Override
        public void onError(Throwable error) {
            receivedError.set(error);
        }

        @Override
        public void onCompleted() {
            completed.set(true);
        }
    };

    service.getItem(
            GetItemRequest.newBuilder()
                    .setItemId("item-42")
                    .build(),
            observer);

    Throwable rpcFailure = receivedError.get();
    Status status = Status.fromThrowable(rpcFailure);
    Metadata trailers = Status.trailersFromThrowable(rpcFailure);

    assertEquals(Status.Code.INTERNAL, status.getCode());
    assertEquals("Internal server error", status.getDescription());
    assertFalse(status.getDescription().contains(secret));
    assertNotNull(trailers);
    assertEquals(Set.of("x-error-id"), trailers.keys());
    assertFalse(trailers.toString().contains(secret));
    assertFalse(completed.get());
    assertTrue(values.isEmpty());
}
```

Để test xác định, inject `Supplier<String>` vào adapter; production có thể dùng `() -> UUID.randomUUID().toString()`, còn test trả về một ID cố định. Không phụ thuộc UUID ngẫu nhiên để assert giá trị cụ thể. Test cũng cần xác nhận mapper lỗi bất ngờ được gọi đúng một lần và không có response thành công nào được phát trước lỗi. Các import cần thiết cho ví dụ gồm `List`, `ArrayList`, `AtomicReference`, `AtomicBoolean` và `StreamObserver`.

## 8. Kiểm thử từ góc nhìn gRPC client bằng in-process transport

Direct adapter test xác minh observer callback. In-process gRPC test bổ sung một bước: generated client stub nhận status và trailers qua gRPC call pipeline mà không mở TCP port.

Test scope cần dependency `grpc-inprocess` tương thích với phiên bản grpc-java đang dùng. Khung test:

```java
String serverName = InProcessServerBuilder.generateName();

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(service)
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

try {
    CatalogServiceGrpc.CatalogServiceBlockingStub client =
            CatalogServiceGrpc.newBlockingStub(channel);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> client.getItem(
                    GetItemRequest.newBuilder()
                            .setItemId("item-42")
                            .build()));

    Status status = Status.fromThrowable(error);
    Metadata trailers = Status.trailersFromThrowable(error);

    assertEquals(Status.Code.INTERNAL, status.getCode());
    assertEquals("Internal server error", status.getDescription());
    assertEquals("err-test-42",
            trailers.get(GrpcErrorMetadata.ERROR_ID));
    assertEquals(Set.of("x-error-id"), trailers.keys());
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(5, TimeUnit.SECONDS);
    server.awaitTermination(5, TimeUnit.SECONDS);
}
```

Trong test này, adapter dùng error ID supplier trả về `err-test-42`. In-process transport xác minh status/trailers mà generated client nhìn thấy qua gRPC runtime. Nó không kiểm tra TLS, HTTP/2 socket, proxy hoặc load balancer; các hành vi đó cần network integration test riêng.

## 9. Kiểm thử streaming error

Với server-streaming, server có thể đã gửi một số message trước khi lỗi bất ngờ xảy ra. Adapter phải kết thúc stream bằng một status `INTERNAL` chung và không phát message sau terminal signal.

Test cần xác nhận:

- Các message hợp lệ trước lỗi được giữ nguyên.
- Terminal status là `INTERNAL`.
- Description chỉ là thông điệp chung.
- Trailers chỉ chứa error ID được cho phép.
- Không có `onCompleted()` sau `onError()`.
- Exception detail không xuất hiện trong bất kỳ message/trailer công khai nào.

Các message đã gửi không thể thu hồi. Vì vậy không đặt dữ liệu nhạy cảm vào response trước khi operation đạt điều kiện an toàn để công bố. Với client-streaming/bidirectional streaming, áp dụng cùng nguyên tắc cho response observer và đảm bảo chỉ có một terminal signal.

## 10. Kiểm tra logging và observability

Một response an toàn không đủ nếu log hoặc trace lại làm lộ cùng thông tin. Xác định chính sách riêng cho từng kênh:

| Kênh | Thông tin nên giữ | Thông tin cần loại bỏ/redact |
| --- | --- | --- |
| gRPC response | `INTERNAL`, description chung, error ID | Exception message, stack trace, SQL, secret |
| Application log | Error ID, RPC method, exception type, timestamp | Token, payload, PII và message chưa kiểm duyệt |
| Restricted diagnostics | Stack trace sau redaction, nếu chính sách cho phép | Secret và dữ liệu người dùng không cần thiết |
| Trace/span | RPC method, status code, trace ID | Raw metadata, token, SQL parameter |
| Metrics | Status code, service/method | Error ID, user ID, exception message làm label |

Không dùng error ID làm metrics label vì mỗi lỗi có thể sinh một giá trị mới và làm cardinality tăng không giới hạn. Error ID phù hợp cho log/trailer; metrics nên nhóm theo service, method và status code.

## 11. Những lỗi kiểm thử thường gặp

| Lỗi | Vì sao chưa đủ | Cách sửa |
| --- | --- | --- |
| Chỉ assert code `INTERNAL` | Description hoặc trailers vẫn có thể lộ detail | Assert description và allowlist trailers |
| Chỉ test mapper | Adapter có thể bỏ qua mapper và trả exception message trực tiếp | Test service implementation với exception chứa secret |
| Chỉ test observer trực tiếp | Chưa xác minh client nhận trailers | Thêm in-process gRPC test |
| Log toàn bộ exception vào log chung | Message/stack có thể chứa dữ liệu nhạy cảm | Log error ID/type; dùng diagnostic sink có kiểm soát |
| Đưa stack trace vào `google.rpc.DebugInfo` | Client nhận chi tiết nội bộ | Không gửi debug detail trong public INTERNAL |
| Gửi error ID chứa user/email | Trailer làm lộ dữ liệu cá nhân | Dùng ID ngẫu nhiên không mang ngữ nghĩa |
| Assert `toString()` của Status | Phụ thuộc định dạng không phải contract | Assert code, description và metadata key/value |
| Dùng in-process test để kết luận TLS đúng | In-process không dùng TLS socket | Có network test cho TLS/mTLS |

## 12. Checklist cho một public INTERNAL contract

Trước khi phát hành adapter, xác minh:

- [ ] Lỗi bất ngờ trả `Status.Code.INTERNAL`.
- [ ] Description là thông điệp chung, ổn định.
- [ ] Không có exception cause/message/stack trace trong response.
- [ ] Trailers chỉ chứa error ID và key đã allowlist.
- [ ] Error ID không chứa dữ liệu cá nhân hoặc secret.
- [ ] Log có error ID để tra cứu nhưng không ghi raw request/token.
- [ ] Test dùng exception message giả lập có secret và xác nhận không rò rỉ.
- [ ] In-process client test xác minh status/trailers thực tế.
- [ ] Streaming test xác minh terminal signal và không phát tiếp sau lỗi.
- [ ] Network/security tests kiểm tra gateway, TLS và logging pipeline khi cần.

### Ghi nhớ

**`INTERNAL` phải mô tả lỗi server ở mức công khai, không trở thành kênh phát tán exception detail.** Trả description chung, error ID an toàn qua trailers và giữ thông tin chẩn đoán trong hệ thống nội bộ có kiểm soát. Kiểm thử mapper, adapter và generated client để chứng minh SQL, stack trace, hostname, token hoặc secret không xuất hiện trong status, details hay metadata mà client nhận được.

## Tài liệu tham khảo

- [gRPC — Error Handling](https://grpc.io/docs/guides/error/)
- [gRPC — Status Codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC Java — Status](https://grpc.github.io/grpc-java/javadoc/io/grpc/Status.html)
- [gRPC Java — Metadata](https://grpc.github.io/grpc-java/javadoc/io/grpc/Metadata.html)
- [gRPC Java — InProcessServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/inprocess/InProcessServerBuilder.html)
