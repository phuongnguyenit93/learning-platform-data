# Kiểm thử error status và metadata

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và RPC unary hoặc streaming. Bài này tập trung vào kiểm thử kết quả RPC thất bại: status code, status description và metadata đi kèm, đặc biệt là trailing metadata mà server gửi cùng lỗi.

## 1. Một test lỗi RPC cần xác nhận điều gì?

Chỉ kiểm tra rằng client ném `StatusRuntimeException` là chưa đủ. Một kiểm thử có ích cần xác nhận:

1. **Status code:** client nhận đúng mã chuẩn, ví dụ `NOT_FOUND`, `INVALID_ARGUMENT` hoặc `PERMISSION_DENIED`.
2. **Description:** nếu API cam kết mô tả, client nhận mô tả dự kiến; nếu description tùy chọn, client vẫn xử lý được khi nó vắng mặt.
3. **Trailers:** custom metadata cuối RPC có đúng key và value hay không.
4. **Không có dữ liệu thành công giả:** RPC kết thúc lỗi không được bị hiểu nhầm là đã trả response thành công.
5. **Fallback:** client hoạt động khi trailer thiếu, key chưa biết hoặc lỗi đến từ transport và không có custom metadata.

Status code và metadata là một phần hợp đồng API. Test nên kiểm tra hợp đồng đó qua gRPC stub/channel thực, không chỉ gọi mapper trực tiếp.

## 2. Phân biệt request metadata, response headers và trailers

gRPC dùng `Metadata` cho các cặp key/value ở ba vị trí:

| Loại | Hướng | Thời điểm | Cách quan sát ở client |
| --- | --- | --- | --- |
| Request metadata | Client → server | Khi bắt đầu RPC | Server interceptor đọc tham số `headers` |
| Initial response headers | Server → client | Khi response bắt đầu | `ClientCall.Listener.onHeaders()` |
| Trailers | Server → client | Khi RPC kết thúc | `ClientCall.Listener.onClose(status, trailers)`; với lỗi blocking có thể dùng `Status.trailersFromThrowable()` |

Với lỗi RPC, status code và trailers cùng xác định kết quả cuối. Initial response headers không thay thế trailers; request metadata cũng không phải metadata phản hồi.

Ví dụ custom error trailers:

```text
Status:
  code: FAILED_PRECONDITION
  description: Operation is not permitted

Trailers:
  error-code: ACCOUNT_SUSPENDED
  support-reference: req-7f31
  diagnostic-tag-bin: <binary bytes>
```

Client dùng status code để phân loại tổng quát, rồi đọc custom trailer nếu có. Không parse description để tìm mã lỗi.

## 3. Khai báo metadata key nhất quán

Mỗi metadata key cần có tên và marshaller. Key text dùng `ASCII_STRING_MARSHALLER`; key nhị phân phải có hậu tố `-bin` và dùng `BINARY_BYTE_MARSHALLER`.

```java
import io.grpc.Metadata;

public final class ErrorMetadata {
    private ErrorMetadata() {}

    public static final Metadata.Key<String> ERROR_CODE =
            Metadata.Key.of(
                    "error-code",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> SUPPORT_REFERENCE =
            Metadata.Key.of(
                    "support-reference",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<byte[]> DIAGNOSTIC_TAG =
            Metadata.Key.of(
                    "diagnostic-tag-bin",
                    Metadata.BINARY_BYTE_MARSHALLER);
}
```

Key phải được định nghĩa thống nhất giữa server và client. Tên key dùng chữ thường; không dùng tiền tố dành riêng `grpc-`. Không khai báo một key cùng tên với nhiều marshaller khác nhau trong các thành phần của ứng dụng.

## 4. Server trả status và trailers có chủ đích

Ví dụ service kết thúc RPC bằng lỗi `NOT_FOUND` và đính kèm ba trailer:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {

        Metadata trailers = new Metadata();
        trailers.put(ErrorMetadata.ERROR_CODE, "ITEM_NOT_FOUND");
        trailers.put(ErrorMetadata.SUPPORT_REFERENCE, "req-7f31");
        trailers.put(
                ErrorMetadata.DIAGNOSTIC_TAG,
                new byte[] {0x01, 0x02, 0x03});

        responseObserver.onError(
                Status.NOT_FOUND
                        .withDescription("Item not found")
                        .asRuntimeException(trailers));
    }
}
```

Trong Spring gRPC, service thực tế thường được đăng ký bằng annotation/configuration của starter. Test có thể đăng ký implementation trực tiếp với in-process server như ví dụ tiếp theo. Các trailer chỉ chứa mã và reference không nhạy cảm; không gửi payload, token, stack trace hoặc exception message.

## 5. Kiểm thử qua gRPC in-process

In-process transport cho phép test gọi generated stub qua gRPC channel mà không cần mở cổng mạng. Nó vẫn đi qua gRPC call lifecycle, status và metadata serialization của transport nội bộ.

Ví dụ dùng JUnit 5, `grpc-inprocess` và các lớp protobuf/gRPC được sinh:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ErrorMetadataIntegrationTest {

    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void setUp() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new CatalogGrpcService())
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void tearDown() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }

    @Test
    void receivesStatusAndCustomTrailers() {
        CatalogServiceGrpc.CatalogServiceBlockingStub stub =
                CatalogServiceGrpc.newBlockingStub(channel);

        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getItem(
                        GetItemRequest.newBuilder()
                                .setItemId("missing-item")
                                .build()));

        Status status = Status.fromThrowable(error);
        assertEquals(Status.Code.NOT_FOUND, status.getCode());
        assertEquals("Item not found", status.getDescription());

        Metadata trailers = Status.trailersFromThrowable(error);
        assertNotNull(trailers);
        assertEquals(
                "ITEM_NOT_FOUND",
                trailers.get(ErrorMetadata.ERROR_CODE));
        assertEquals(
                "req-7f31",
                trailers.get(ErrorMetadata.SUPPORT_REFERENCE));
        assertArrayEquals(
                new byte[] {0x01, 0x02, 0x03},
                trailers.get(ErrorMetadata.DIAGNOSTIC_TAG));
    }
}
```

Test xác nhận status và cả hai kiểu metadata. Nó không phụ thuộc vào chuỗi exception message hoặc class exception nội bộ của server; chỉ kiểm tra status code, description đã công bố và các trailer key thuộc hợp đồng.

### Vì sao dùng Status.fromThrowable?

`Status.fromThrowable(error)` trích status từ gRPC exception hoặc cause chain. Cách này hữu ích nếu lỗi được bọc trong một exception khác. Không nên so sánh `error.getMessage()` vì chuỗi đó có thể thay đổi hoặc chứa thông tin không dành cho client.

### Vì sao dùng Status.trailersFromThrowable?

`Status.trailersFromThrowable(error)` trả trailing metadata nếu exception mang theo. Giá trị có thể là `null`; test cần kiểm tra trước khi gọi `get(key)`. Với một trailer không bắt buộc, client cũng phải chấp nhận key vắng mặt.

## 6. Kiểm thử lỗi không có custom trailers

Không phải mọi lỗi đều do application mapper tạo ra. Deadline, cancellation, lỗi kết nối hoặc lỗi transport có thể không có trailer nghiệp vụ.

Ví dụ assertion an toàn:

```java
@Test
void handlesStatusWithoutCustomTrailers() {
    StatusRuntimeException error =
            Status.INVALID_ARGUMENT
                    .withDescription("Invalid request")
                    .asRuntimeException();

    Status status = Status.fromThrowable(error);
    assertEquals(Status.Code.INVALID_ARGUMENT, status.getCode());

    Metadata trailers = Status.trailersFromThrowable(error);
    assertTrue(
            trailers == null
                    || trailers.get(ErrorMetadata.ERROR_CODE) == null);
}
```

Test này xác nhận logic client không yêu cầu mọi status phải có custom trailer. Ứng dụng cần fallback theo status code khi trailer thiếu:

```java
String errorCode = trailers == null
        ? null
        : trailers.get(ErrorMetadata.ERROR_CODE);

if (status.getCode() == Status.Code.NOT_FOUND
        && "ITEM_NOT_FOUND".equals(errorCode)) {
    showItemNotFound();
} else if (status.getCode() == Status.Code.NOT_FOUND) {
    showGenericNotFound();
} else {
    handleOtherStatus(status.getCode());
}
```

Không để một trailer thiếu làm phát sinh `NullPointerException` rồi che mất status ban đầu.

## 7. Kiểm thử initial response headers riêng với trailers

Nếu API có gửi initial response headers, hãy kiểm thử chúng qua client interceptor. `onHeaders()` và `onClose(..., trailers)` là hai callback khác nhau:

```java
ClientInterceptor captureMetadata = new ClientInterceptor() {
    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata requestHeaders) {
                super.start(new ForwardingClientCallListener
                        .SimpleForwardingClientCallListener<>(listener) {
                    @Override
                    public void onHeaders(Metadata headers) {
                        // Lưu initial response headers để assertion riêng.
                        captureInitialHeaders(headers);
                        super.onHeaders(headers);
                    }

                    @Override
                    public void onClose(Status status, Metadata trailers) {
                        // Status và trailers là kết quả cuối của RPC.
                        captureFinalStatusAndTrailers(status, trailers);
                        super.onClose(status, trailers);
                    }
                }, requestHeaders);
            }
        };
    }
};
```

Đây là khung minh họa; `captureInitialHeaders` và `captureFinalStatusAndTrailers` là hàm lưu kết quả test, thường dùng `AtomicReference` hoặc một test observer. Khi assertion trên callback bất đồng bộ, đồng bộ bằng latch/future có timeout thay vì `Thread.sleep()`.

Nếu server không gửi initial headers tường minh trước khi lỗi, client có thể không nhận header tùy chỉnh nào. Điều đó không làm mất status/trailers của terminal event. Test phải phản ánh đúng hợp đồng mà server thực sự công bố.

## 8. Kiểm thử status và metadata trong async client

Với async stub, lỗi đến qua `StreamObserver.onError(Throwable)`. Dùng cùng API để đọc status và trailers:

```java
StreamObserver<GetItemResponse> responseObserver =
        new StreamObserver<>() {
    @Override
    public void onNext(GetItemResponse response) {
        fail("RPC này được kỳ vọng kết thúc bằng lỗi");
    }

    @Override
    public void onError(Throwable error) {
        Status status = Status.fromThrowable(error);
        Metadata trailers = Status.trailersFromThrowable(error);

        assertEquals(Status.Code.NOT_FOUND, status.getCode());
        assertNotNull(trailers);
        assertEquals(
                "ITEM_NOT_FOUND",
                trailers.get(ErrorMetadata.ERROR_CODE));
    }

    @Override
    public void onCompleted() {
        fail("Không được hoàn tất thành công");
    }
};

CatalogServiceGrpc.newStub(channel).getItem(request, responseObserver);
```

Trong test thực tế, không nên gọi assertion bất đồng bộ mà không chuyển lỗi assertion về test thread. Dùng `CompletableFuture` để hoàn tất khi `onError` hoặc `onCompleted` chạy, rồi assertion trên thread test với timeout hữu hạn.

Với client streaming hoặc server streaming, cũng kiểm tra số response message trước terminal error. Nếu server đã trả một phần response hợp lệ rồi mới lỗi, hợp đồng cần mô tả rõ dữ liệu nào client được phép giữ; đừng mặc định terminal error xóa các message đã nhận.

## 9. Ma trận kiểm thử error status và metadata

| Ca kiểm thử | Status mong đợi | Metadata/assertion |
| --- | --- | --- |
| Không tìm thấy item | `NOT_FOUND` | Có `error-code=ITEM_NOT_FOUND` |
| Request sai | `INVALID_ARGUMENT` | Trailer có thể vắng mặt; client vẫn xử lý được |
| Không đủ quyền | `PERMISSION_DENIED` | Không gửi token hoặc chi tiết policy nội bộ |
| Credential không hợp lệ | `UNAUTHENTICATED` | Không phản chiếu credential trong description/trailers |
| Dependency tạm thời lỗi | `UNAVAILABLE` | Có thể có support reference; không bắt buộc |
| Deadline hết | `DEADLINE_EXCEEDED` | Không giả định custom trailers luôn tồn tại |
| Lỗi nội bộ bất ngờ | `INTERNAL` | Description chung, không có stack trace |
| Binary trailer | Status theo lỗi | Đọc bằng đúng key `-bin` và binary marshaller |
| Initial response headers | Status cuối có thể là lỗi | Assertion qua `onHeaders()`, tách khỏi trailers |

Kiểm thử nên xác nhận cả giá trị có mặt và trường hợp không có giá trị. Một client vững chắc không phụ thuộc mọi server, proxy hoặc transport đều gửi cùng một tập metadata tùy chọn.

## 10. Các lỗi thường gặp trong test

- **Chỉ assert exception được ném:** không chứng minh status code hoặc metadata đúng.
- **Parse description để suy ra error code:** dễ hỏng khi câu chữ thay đổi; dùng enum status và trailer key.
- **Giả định trailers luôn khác null:** transport error có thể không có custom metadata.
- **Nhầm headers với trailers:** chúng đến ở thời điểm và callback khác nhau.
- **Dùng ASCII marshaller cho byte array:** binary key phải có hậu tố `-bin` và binary marshaller.
- **Không đóng channel/server test:** làm rò rỉ thread và khiến test suite không kết thúc ổn định.
- **Dùng sleep để đợi callback:** tạo test chập chờn; dùng future/latch và timeout.
- **Đưa secret vào fixture rồi chỉ kiểm tra status:** cần assert description/trailers không phản chiếu token hoặc payload nhạy cảm.

## 11. Bảo mật và tương thích metadata

Metadata là dữ liệu client có thể quan sát. Không gửi access token, password, PII, SQL, stack trace hoặc payload lớn trong trailers. Chỉ gửi mã lỗi ổn định, support reference không nhạy cảm và detail nhỏ đã được công bố trong hợp đồng.

Client cần bỏ qua key chưa biết và xử lý key tùy chọn bị thiếu. Khi đổi tên key hoặc đổi semantics của một error code, coi đó là thay đổi hợp đồng: cập nhật tài liệu, test tương thích và kế hoạch rollout client/server. Nếu cần cấu trúc lỗi phong phú, cân nhắc error details protobuf như `google.rpc.BadRequest` hoặc `google.rpc.ErrorInfo` thay vì tự nhồi nhiều thông tin vào chuỗi metadata.

## 12. Tự luyện tập

1. Viết test xác nhận `NOT_FOUND`, description và trailer `error-code` được client nhận đúng qua in-process channel.
2. Vì sao `Status.trailersFromThrowable()` phải được xử lý khi trả về `null`?
3. Một response có initial headers và terminal trailers. Hãy thiết kế hai assertion độc lập cho `onHeaders()` và `onClose()`.
4. Viết test cho binary trailer `diagnostic-tag-bin`; vì sao key cần hậu tố `-bin`?
5. Client nhận `UNAVAILABLE` mà không có custom trailer. Nó cần xử lý thế nào để không phụ thuộc metadata tùy chọn?

**Ghi nhớ:** Kiểm thử error handling phải xác nhận **status code, description và trailers** qua gRPC call thực. Dùng `Status.fromThrowable()` để đọc status, `Status.trailersFromThrowable()` để đọc metadata cuối, xử lý trailer thiếu, và kiểm tra initial headers riêng qua `onHeaders()`. Assertions dựa trên code/key ổn định, không parse chuỗi exception message.
