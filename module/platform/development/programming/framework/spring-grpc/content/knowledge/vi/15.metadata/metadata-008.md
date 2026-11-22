# Metadata từ server về client

Metadata không chỉ đi từ client đến server. Trong gRPC, server có thể gửi thông tin bổ trợ về phía client qua **initial response headers** và **response trailers**. Hai loại metadata này đều thuộc một RPC, nhưng được gửi ở những thời điểm khác nhau: headers xuất hiện khi server bắt đầu phản hồi; trailers được gửi khi RPC kết thúc cùng trạng thái gRPC.

Trong Spring gRPC, các API này đến từ `grpc-java`. Service có thể gửi response headers bằng `ServerCallStreamObserver.sendHeaders(...)`; server interceptor có thể bổ sung trailers khi `ServerCall.close(...)`; client nhận headers ở `ClientCall.Listener.onHeaders(...)` và nhận trailers cùng status ở `onClose(...)`.

## 1. Phân biệt response headers và trailers

| Đặc điểm | Initial response headers | Response trailers |
| --- | --- | --- |
| Thời điểm | Đầu phần phản hồi, trước message đầu tiên | Khi RPC kết thúc |
| API phía server | `ServerCall.sendHeaders(...)` hoặc `ServerCallStreamObserver.sendHeaders(...)` | `ServerCall.close(status, trailers)` |
| Callback phía client | `ClientCall.Listener.onHeaders(...)` | `ClientCall.Listener.onClose(status, trailers)` |
| Dữ liệu phù hợp | Phiên bản server, khả năng đã thương lượng, mã chẩn đoán ban đầu | Request ID để đối chiếu, mã lỗi ứng dụng ngắn, thông tin kết thúc |
| Số lần | Tối đa một lần cho một RPC | Một lần khi call đóng |

Sơ đồ một unary RPC:

```text
Client                                             Server
  |                                                  |
  |---------------- request ------------------------>|
  |                                                  |
  |<------------- initial response headers ----------|  onHeaders(...)
  |<------------- response message ------------------|  onMessage(...)
  |<------------- trailers + grpc-status ------------|  onClose(status, trailers)
  |                                                  |
```

Với server streaming, response headers vẫn được gửi tối đa một lần trước message đầu tiên; nhiều response message tiếp theo được chuyển qua stream; trailers chỉ xuất hiện khi stream hoàn tất hoặc kết thúc lỗi. Client streaming và bidirectional streaming cũng tuân theo nguyên tắc metadata gắn với **toàn bộ RPC**, không gắn riêng cho từng message.

Một số lỗi có thể kết thúc theo dạng **trailers-only**: client nhận status và trailers mà không có initial response headers hoặc message. Vì vậy, logic xử lý lỗi không được phụ thuộc vào việc `onHeaders(...)` luôn được gọi.

## 2. Server gửi initial response headers

Trong implementation của service, gRPC cung cấp `ServerCallStreamObserver` cho phép gửi headers trước message đầu tiên. Ví dụ:

```java
import io.grpc.Metadata;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;

private static final Metadata.Key<String> SERVER_VERSION =
    Metadata.Key.of(
        "x-server-version",
        Metadata.ASCII_STRING_MARSHALLER);

@Override
public void getInfo(
        InfoRequest request,
        StreamObserver<InfoReply> responseObserver) {

    ServerCallStreamObserver<InfoReply> serverObserver =
        (ServerCallStreamObserver<InfoReply>) responseObserver;

    Metadata responseHeaders = new Metadata();
    responseHeaders.put(SERVER_VERSION, "1.4.0");

    // Phải gửi headers trước message đầu tiên.
    serverObserver.sendHeaders(responseHeaders);

    InfoReply reply = InfoReply.newBuilder()
        .setMessage("Service is ready")
        .build();
    serverObserver.onNext(reply);
    serverObserver.onCompleted();
}
```

`InfoRequest`, `InfoReply` và `getInfo` là tên ví dụ được sinh hoặc triển khai từ hợp đồng Protobuf. Trong gRPC server thực tế, runtime cung cấp `ServerCallStreamObserver` cho service; chỉ gọi `sendHeaders(...)` một lần và trước khi phát message. Không gọi nó sau `onNext(...)` hoặc sau khi call đã đóng.

Chỉ đưa vào response headers dữ liệu ngắn mà client cần biết sớm, chẳng hạn phiên bản server hoặc một lựa chọn đã thương lượng. Không gửi token, thông tin nội bộ nhạy cảm hay payload nghiệp vụ lớn. Nếu server không cần metadata ban đầu, có thể để gRPC gửi headers mặc định khi bắt đầu response.

## 3. Server bổ sung trailers bằng interceptor

Service API dựa trên `StreamObserver` thường không cung cấp một tham số trailers trực tiếp khi gọi `onCompleted()` hoặc `onError()`. Một `ServerInterceptor` có thể bọc `ServerCall` và bổ sung metadata ở thời điểm `close(status, trailers)`.

Ví dụ sau phản hồi request ID đã được kiểm tra ở đầu call:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ResponseTrailersInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> RESPONSE_REQUEST_ID =
        Metadata.Key.of(
            "x-response-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata requestHeaders,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = requestHeaders.get(REQUEST_ID);
        // Chỉ phản hồi ID đã qua kiểm tra định dạng ở lớp tin cậy.
        final String safeRequestId =
            requestId != null
                && requestId.matches("[A-Za-z0-9._-]{1,64}")
            ? requestId
            : null;

        ServerCall<ReqT, RespT> wrappedCall =
            new ForwardingServerCall.SimpleForwardingServerCall<ReqT, RespT>(
                    call) {
                @Override
                public void close(Status status, Metadata trailers) {
                    if (safeRequestId != null) {
                        trailers.discardAll(RESPONSE_REQUEST_ID);
                        trailers.put(RESPONSE_REQUEST_ID, safeRequestId);
                    }
                    // Giữ nguyên status gốc và các trailers khác.
                    super.close(status, trailers);
                }
            };

        return next.startCall(wrappedCall, requestHeaders);
    }
}
```

Interceptor trên chỉ minh họa việc bổ sung trailer. Trong ứng dụng thật, request ID cần được kiểm tra tại ranh giới tin cậy; nếu thiếu hoặc không hợp lệ, server có thể tự sinh ID thay vì echo giá trị client gửi. Không dùng trailer để trả lại bearer token, dữ liệu cá nhân hoặc stack trace.

Điểm quan trọng là gọi `super.close(status, trailers)` với **status gốc**. Việc thêm metadata chẩn đoán không được làm thay đổi kết quả nghiệp vụ hoặc che mất `UNAUTHENTICATED`, `PERMISSION_DENIED`, `DEADLINE_EXCEEDED` hay status khác.

## 4. Client nhận response headers và trailers

Client interceptor có thể bọc listener để quan sát metadata trả về. `onHeaders(...)` nhận initial response headers; `onClose(...)` nhận status cuối cùng và trailers:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;

public final class ResponseMetadataClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> SERVER_VERSION =
        Metadata.Key.of(
            "x-server-version",
            Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> RESPONSE_REQUEST_ID =
        Metadata.Key.of(
            "x-response-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions options,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, options);

        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> responseListener,
                    Metadata requestHeaders) {

                ClientCall.Listener<RespT> listener =
                    new ForwardingClientCallListener
                        .SimpleForwardingClientCallListener<RespT>(
                            responseListener) {
                        @Override
                        public void onHeaders(Metadata headers) {
                            String version = headers.get(SERVER_VERSION);
                            // Có thể lưu version đã đọc vào telemetry/log
                            // theo allowlist; không dump toàn bộ headers.
                            super.onHeaders(headers);
                        }

                        @Override
                        public void onClose(Status status, Metadata trailers) {
                            String requestId =
                                trailers.get(RESPONSE_REQUEST_ID);
                            // Đối chiếu requestId với log khi cần.
                            // Status vẫn là kết quả chính thức của RPC.
                            super.onClose(status, trailers);
                        }
                    };

                super.start(listener, requestHeaders);
            }
        };
    }
}
```

Đoạn code chỉ đọc metadata và chuyển tiếp callback. Nếu ứng dụng cần trả thông tin lên tầng gọi, hãy chuyển **giá trị đã trích xuất** qua một đối tượng kết quả hoặc telemetry phù hợp; không giữ đối tượng `Metadata` mutable để dùng sau callback.

Client nên xử lý status trước tiên. Trailer tùy biến là thông tin bổ trợ: nó có thể vắng mặt, đặc biệt khi server/proxy kết thúc call sớm hoặc phản hồi theo dạng trailers-only. Không xem `x-response-request-id` là bằng chứng xác thực server; danh tính server được bảo vệ bằng TLS/mTLS và cấu hình trust thích hợp.

## 5. Metadata trả về trong các tình huống thường gặp

| Tình huống | Client có thể nhận | Cách xử lý |
| --- | --- | --- |
| Unary thành công | Headers, một message, trailers và `OK` | Đọc server version ở `onHeaders`, trạng thái cuối ở `onClose` |
| Unary lỗi trước message | Có thể trailers-only với status lỗi | Không phụ thuộc initial headers hoặc response message |
| Server streaming | Headers một lần, nhiều message, trailers khi stream kết thúc | Dùng headers cho thông tin chung; xử lý từng message riêng |
| Client/bidirectional streaming | Response headers khi server bắt đầu phản hồi, trailers lúc kết thúc | Không chờ trailer để xử lý từng message |
| Deadline hết hoặc client hủy | Status tương ứng, metadata tùy đường kết thúc | Giữ nguyên status; trailer tùy biến có thể không có |
| Proxy/gateway từ chối trước server | Có thể không có metadata ứng dụng do server tạo | Không giả định mọi response đều đi qua interceptor của service |

Một số lưu ý về thứ tự:

- Server chỉ gửi initial headers một lần. Nếu service gọi `sendHeaders(...)`, lần gọi phải xảy ra trước message đầu tiên.
- Server gửi trailers khi đóng call. Sau khi đóng, không gửi thêm message hoặc metadata.
- Client nhận message và callback metadata theo vòng đời gRPC. `onClose(...)` báo kết thúc call; không xử lý thêm message sau callback này.
- Trong streaming, trailers chỉ có khi stream kết thúc, không phải sau mỗi message.

## 6. Thiết kế response metadata an toàn

Response metadata thường được proxy, gateway, SDK và hệ thống quan sát đọc. Vì vậy, chỉ nên trả những giá trị client thực sự cần.

**Nên dùng:**

- Phiên bản server hoặc mã capability đã thương lượng.
- Request/correlation ID đã được server kiểm tra hoặc tạo.
- Mã chẩn đoán ngắn, không nhạy cảm để hỗ trợ liên hệ log.
- Metadata cần thiết theo hợp đồng API và có giới hạn độ dài rõ ràng.

**Không nên dùng:**

- Access token, refresh token, cookie hoặc credential.
- Stack trace, câu SQL, đường dẫn nội bộ hoặc chi tiết triển khai.
- Thông tin cá nhân, tenant secret hoặc dữ liệu nghiệp vụ lớn.
- Các key dành riêng cho gRPC như `grpc-status`, `grpc-message` hoặc `grpc-timeout`.

Metadata được truyền qua HTTP/2 headers/trailers nên chịu giới hạn dung lượng từ client, server, proxy và load balancer. Không dùng response trailers làm kênh truyền payload. Nếu cần trả cấu trúc lỗi nghiệp vụ phong phú, cân nhắc message lỗi hoặc error details theo thiết kế API, trong khi status gRPC vẫn biểu thị kết quả RPC.

TLS bảo vệ metadata trên kết nối được mã hóa; nếu proxy kết thúc TLS, cần xem xét cả chặng proxy–server. Không log toàn bộ trailers hoặc headers nếu có nguy cơ chứa dữ liệu nhạy cảm. Dùng allowlist các key an toàn.

## 7. Kiểm thử response metadata

Unit test có thể xác minh cách tạo key và đọc value, nhưng cần **integration test qua server/client** để khẳng định headers/trailers thật sự được gửi và callback client nhận đúng vị trí.

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Initial headers | Server gửi `x-server-version` trước `onNext` | Client đọc được trong `onHeaders` |
| Trailers thành công | Server đóng call với `x-response-request-id` | Client đọc được trong `onClose` cùng `OK` |
| Trailers khi lỗi | Service kết thúc với status lỗi | Status gốc không bị thay đổi; trailer tùy biến chỉ có nếu server đã thêm |
| Trailers-only | Server/gateway từ chối trước response message | Client xử lý status dù không có initial headers |
| Streaming | Server gửi nhiều message rồi đóng stream | Headers chỉ một lần, trailers ở cuối |
| Header trùng | Server hoặc interceptor ghi trùng custom key | Client/server xử lý theo chính sách đã định nghĩa |
| Metadata thiếu | Server không gửi custom key | Client xử lý giá trị vắng mặt bình thường |
| TLS/proxy | Gọi qua transport gần production | Metadata đến đúng client, không lộ secret |

### Ví dụ test logic nhận trailers

Phần cốt lõi của client listener có thể được kiểm tra bằng một listener giả:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.Metadata;
import io.grpc.Status;
import org.junit.jupiter.api.Test;

class ResponseMetadataTest {
    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-response-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Test
    void readsRequestIdFromTrailersAndKeepsStatus() {
        Metadata trailers = new Metadata();
        trailers.put(REQUEST_ID, "req-42");

        Status status = Status.OK;
        assertEquals("req-42", trailers.get(REQUEST_ID));
        assertEquals(Status.Code.OK, status.getCode());
    }
}
```

Test nhỏ trên chỉ kiểm tra metadata và status cục bộ. Integration test cần khởi tạo in-process gRPC server/channel hoặc transport thực, đăng ký server interceptor, gửi RPC và assert callback `onHeaders`/`onClose`. Với TLS, proxy và lỗi trailers-only, cần kiểm thử trên môi trường tương ứng vì in-process transport không mô phỏng đầy đủ HTTP/2.

## 8. Bài tập vận dụng

Một `OrderService.GetOrder` viết bằng Spring gRPC cần trả phiên bản server trong response headers và request ID trong response trailers. Client SDK phải thu thập hai giá trị để hỗ trợ chẩn đoán.

**Yêu cầu:**

1. Server gửi `x-server-version` qua `ServerCallStreamObserver.sendHeaders(...)` trước response message đầu tiên.
2. Server interceptor bọc `ServerCall.close(...)` để thêm `x-response-request-id` nếu request ID đã được kiểm tra.
3. Client interceptor đọc `x-server-version` trong `onHeaders(...)` và `x-response-request-id` trong `onClose(status, trailers)`.
4. Không thay đổi status gốc khi thêm trailers; kiểm thử cả `OK` và status lỗi.
5. Thực hiện thêm một test streaming để xác nhận headers chỉ gửi đầu stream và trailers chỉ gửi khi stream kết thúc.
6. Thực hiện test trailers-only hoặc lỗi từ gateway để bảo đảm client không giả định `onHeaders(...)` luôn được gọi.

**Câu hỏi tự kiểm tra:**

- Khác nhau giữa response headers và response trailers là gì?
- Khi nào service phải gọi `ServerCallStreamObserver.sendHeaders(...)`?
- Client đọc initial response metadata và trailers ở callback nào?
- Vì sao không thể dựa vào response headers để xử lý mọi lỗi RPC?
- Interceptor bọc `ServerCall.close(...)` cần giữ nguyên điều gì?
- Vì sao response metadata không nên chứa access token hoặc stack trace?
- Với server streaming, metadata có được gửi lại sau từng response message không?

**Ghi nhớ:** Metadata từ server về client có hai điểm nhận chính: **initial response headers** ở đầu phản hồi và **trailers** khi RPC kết thúc. Server dùng API gửi headers hoặc bọc thao tác đóng call; client đọc headers trong `onHeaders(...)` và trailers cùng status trong `onClose(...)`. Trong Spring gRPC, hãy giữ status gốc, coi metadata tùy biến là dữ liệu bổ trợ, xử lý trường hợp trailers-only và kiểm thử cả unary lẫn streaming.
