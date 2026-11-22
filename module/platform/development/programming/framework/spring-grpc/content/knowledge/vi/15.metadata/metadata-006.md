# Metadata interceptor

Trong **Spring gRPC**, một lời gọi thường đi qua nhiều lớp xử lý ngoài nghiệp vụ: gắn request ID, truyền token, đọc trace context, đo thời gian, kiểm tra tenant hoặc chọn locale. Nếu mỗi phương thức RPC tự đọc và ghi `io.grpc.Metadata`, logic này sẽ bị lặp, khó kiểm thử và dễ bỏ sót ở các phương thức streaming. **Metadata interceptor** giúp đưa các thao tác chung đó vào một điểm xử lý thống nhất ở client hoặc server.

Interceptor là thành phần của **grpc-java**. Spring gRPC sử dụng hạ tầng này để triển khai client/server từ hợp đồng Protocol Buffers, nên một `ClientInterceptor` hoặc `ServerInterceptor` được thiết kế đúng có thể áp dụng cho cả unary RPC và streaming RPC. Tuy nhiên, interceptor chỉ giúp **đọc, ghi hoặc truyền** metadata; một giá trị có mặt trong header không tự chứng minh tính hợp lệ, danh tính hoặc quyền truy cập.

Sau bài học, bạn có thể:

- Giải thích vị trí interceptor trong vòng đời một lời gọi gRPC và phân biệt interceptor phía client với phía server.
- Viết `ClientInterceptor` để thêm request metadata theo từng RPC và quan sát response headers/trailers.
- Viết `ServerInterceptor` để kiểm tra metadata, tạo `io.grpc.Context` và bổ sung response trailers.
- Đăng ký interceptor vào đúng channel, stub hoặc server trong hệ thống Spring gRPC.
- Xử lý thứ tự interceptor, hủy lời gọi, deadline, retry, streaming, context bất đồng bộ và thông tin nhạy cảm.
- Kiểm thử hành vi metadata thực tế bằng gRPC client/server và phát hiện các sai sót cấu hình thường gặp.

## 1. Metadata interceptor nằm ở đâu?

Trong gRPC, metadata là tập hợp các cặp **key–value** nằm ở headers hoặc trailers của một **lời gọi RPC**. Message Protobuf mang dữ liệu nghiệp vụ; metadata phục vụ thông tin bổ trợ như `x-request-id`, `authorization` hoặc `traceparent`.

Luồng cơ bản:

```text
Client application                      gRPC transport                     Server application
       |                                       |                                     |
       |  [ClientInterceptor]                  |                                     |
       |   - nhận method/call options          |                                     |
       |   - ghi request headers               |                                     |
       |------- headers + protobuf message --->|--------> [ServerInterceptor]       |
       |                                       |          - kiểm tra headers          |
       |                                       |          - tạo Context              |
       |                                       |          - cho phép/từ chối RPC      |
       |                                       |                     |               |
       |                                       |                     v               |
       |                                       |               gRPC service method    |
       |<------ response headers/message ------|<------------------------------------|
       |<------ status + response trailers ----|<------------------------------------|
       |  [ClientCall.Listener]                 |                                     |
       |   - onHeaders(...)                     |                                     |
       |   - onClose(status, trailers)          |                                     |
```

Một interceptor có thể:

1. **Đọc và bổ sung** request metadata trước khi gọi được gửi qua transport.
2. **Quan sát hoặc thay đổi** response headers/trailers theo chính sách.
3. **Từ chối sớm** lời gọi có metadata không hợp lệ bằng gRPC `Status`.
4. **Gắn ngữ cảnh** phục vụ logging, tracing hoặc xử lý nghiệp vụ.

Interceptor **không** tự động thực hiện logic nghiệp vụ hoặc phân quyền tài nguyên. Ví dụ, kiểm tra token có hợp lệ là bước xác thực; quyết định người dùng được sửa đơn hàng cụ thể nào còn cần policy thích hợp.

## 2. Các API chính của grpc-java

| API | Được gọi ở phía nào? | Trách nhiệm chính |
| --- | --- | --- |
| `ClientInterceptor.interceptCall(...)` | Client | Bọc lời gọi mới, nhìn thấy `MethodDescriptor` và `CallOptions` |
| `ClientCall.start(listener, headers)` | Client | Bắt đầu call và gửi request metadata |
| `ClientCall.Listener.onHeaders(...)` | Client | Nhận initial response metadata |
| `ClientCall.Listener.onClose(status, trailers)` | Client | Nhận trạng thái kết thúc và response trailers |
| `ServerInterceptor.interceptCall(...)` | Server | Đọc request metadata trước khi chạy service |
| `ServerCall.sendHeaders(...)` | Server | Gửi initial response headers |
| `ServerCall.close(status, trailers)` | Server | Kết thúc RPC, trả status và trailers |
| `Contexts.interceptCall(...)` | Server | Chạy bước tiếp theo với `io.grpc.Context` đã gắn |
| `Metadata.Key<T>` | Hai phía | Định nghĩa tên key và marshaller cho value |

**Phân biệt hai cặp callback:** phía client có `ClientCall` và `ClientCall.Listener`; phía server có `ServerCall` và `ServerCall.Listener`. Chúng là các điểm can thiệp **khác nhau**. Chẳng hạn, client muốn thêm `authorization` phải làm trước khi gọi `super.start(...)`; server muốn bổ sung trailer phải can thiệp khi `close(...)` được gọi.

Một interceptor có thể bao bọc call bằng các lớp `ForwardingClientCall`, `ForwardingClientCallListener` hoặc `ForwardingServerCall`. Những lớp này chuyển tiếp phần lớn thao tác đến delegate, giúp chỉ sửa callback thực sự cần thiết.

## 3. Quy tắc metadata trước khi viết interceptor

Không nên viết interceptor trước khi thống nhất key và vòng đời value.

| Thuộc tính | Ví dụ | Quy tắc |
| --- | --- | --- |
| Tên key | `x-request-id` | Dùng tên chữ thường, tránh tiền tố `grpc-` dành riêng cho giao thức |
| Kiểu value | `String` | Dùng `Metadata.ASCII_STRING_MARSHALLER` cho chuỗi ASCII |
| Binary key | `x-proof-bin` | Phải kết thúc bằng `-bin` và dùng binary marshaller tương ứng |
| Số lượng value | Một request ID cho một RPC | Xác định cách xử lý khi key lặp |
| Nguồn cung cấp | Gateway hoặc client ứng dụng | Xác định ranh giới tin cậy, chính sách sinh/ghi đè |
| Phạm vi | Từng RPC | Không dùng chung metadata đang được sửa giữa nhiều lời gọi |
| Dữ liệu nhạy cảm | `authorization` | Không đưa token vào log hoặc response headers |

Ví dụ key:

```java
import io.grpc.Metadata;

Metadata.Key<String> requestIdKey =
    Metadata.Key.of(
        "x-request-id", Metadata.ASCII_STRING_MARSHALLER);

Metadata.Key<byte[]> proofKey =
    Metadata.Key.of(
        "x-proof-bin", Metadata.BINARY_BYTE_MARSHALLER);
```

Những tên như `x-request-id` là **quy ước ứng dụng**, không phải header bắt buộc của gRPC. Một header khác như `grpc-timeout` hoặc `grpc-status` được thư viện giao thức quản lý: hãy dùng API deadline và `Status` thay vì tự gắn chúng.

## 4. Client interceptor: thêm request metadata theo từng call

Giả sử dịch vụ cần một `x-request-id` trong mọi RPC. Ta tạo client interceptor sao cho:

- Nếu call có request ID được ứng dụng truyền qua `CallOptions`, dùng ID đó khi hợp lệ.
- Nếu chưa có ID hợp lệ, sinh UUID mới **cho chính RPC đang bắt đầu**.
- Ghi duy nhất một value cho key này để tránh xung đột với interceptor khác.
- Chuyển tiếp trạng thái cuối call và có thể quan sát request ID trong response trailers.

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
import java.util.UUID;

public final class RequestIdClientInterceptor implements ClientInterceptor {

    public static final CallOptions.Key<String> REQUEST_ID_OPTION =
        CallOptions.Key.create("request-id");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id", Metadata.ASCII_STRING_MARSHALLER);

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
                    Metadata headers) {

                String supplied = options.getOption(REQUEST_ID_OPTION);
                final String requestId =
                    supplied != null
                        && supplied.matches("[A-Za-z0-9._-]{1,64}")
                    ? supplied
                    : UUID.randomUUID().toString();

                // Chính interceptor này sở hữu key x-request-id.
                headers.discardAll(REQUEST_ID_HEADER);
                headers.put(REQUEST_ID_HEADER, requestId);

                ClientCall.Listener<RespT> observingListener =
                    new ForwardingClientCallListener
                        .SimpleForwardingClientCallListener<RespT>(
                            responseListener) {
                        @Override
                        public void onClose(Status status, Metadata trailers) {
                            String returnedId = trailers.get(REQUEST_ID_HEADER);
                            // Ghi log có chọn lọc nếu cần: tên RPC,
                            // requestId, returnedId và status.getCode().
                            // Không dump toàn bộ metadata.
                            super.onClose(status, trailers);
                        }
                    };

                super.start(observingListener, headers);
            }
        };
    }
}
```

`CallOptions.Key` mang lựa chọn theo từng call, không phải một header HTTP/2. Value chỉ được chuyển thành metadata khi interceptor gọi `headers.put(...)`. Lời gọi downstream thuộc cùng một tác vụ có thể cố ý dùng lại correlation ID, còn hai RPC độc lập có thể sinh ID khác nhau.

Trong ví dụ, `discardAll(...)` làm rõ quyền sở hữu duy nhất của interceptor với `x-request-id`. Nếu hệ thống cho phép nhiều interceptor sửa cùng key, cần thỏa thuận quy tắc ưu tiên, thay vì để việc ghi đè phụ thuộc ngẫu nhiên vào thứ tự interceptor.

### Gắn interceptor vào generated stub

Giả sử đã có `channel` tới server và lớp `GreeterGrpc` được sinh từ file `.proto`:

```java
GreeterGrpc.GreeterBlockingStub baseStub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(new RequestIdClientInterceptor());

GreeterGrpc.GreeterBlockingStub requestStub =
    baseStub.withOption(
        RequestIdClientInterceptor.REQUEST_ID_OPTION,
        "req-checkout-42");

// requestStub.sayHello(...) gửi x-request-id: req-checkout-42
```

Tên `GreeterGrpc` và `sayHello` chỉ minh họa lớp/method từ hợp đồng Protobuf. `withOption(...)` và `withInterceptors(...)` tạo stub dẫn xuất; hãy cấu hình theo phạm vi caller. Tránh giữ stub có request ID hoặc credential cố định của một người dùng rồi dùng chung cho người dùng khác.

**Lưu ý an toàn:** client interceptor chạy ở đầu mỗi RPC, nhưng **không** thay thế hệ thống xác thực. Nếu cần cung cấp bearer token có thể thay đổi, `CallCredentials` là API chuyên dụng để áp dụng credentials theo lời gọi; đừng dùng request ID làm token.

## 5. Server interceptor: kiểm tra metadata và tạo Context

Server nhận request metadata trước khi chuyển xử lý tới RPC method. Ví dụ dưới đây **yêu cầu đúng một** `x-request-id` hợp lệ; nó đưa ID vào `io.grpc.Context` và thêm ID đó vào response trailers để client đối chiếu.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;

public final class RequestContextServerInterceptor implements ServerInterceptor {

    public static final Context.Key<String> CURRENT_REQUEST_ID =
        Context.key("request-id");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Iterable<String> values = headers.getAll(REQUEST_ID_HEADER);
        if (values == null) {
            return reject(call, "Missing x-request-id");
        }

        Iterator<String> iterator = values.iterator();
        if (!iterator.hasNext()) {
            return reject(call, "Missing x-request-id");
        }

        final String requestId = iterator.next();
        if (iterator.hasNext()
                || requestId == null
                || !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
            return reject(call, "Invalid x-request-id");
        }

        Context scopedContext = Context.current()
            .withValue(CURRENT_REQUEST_ID, requestId);

        ServerCall<ReqT, RespT> decoratedCall =
            new ForwardingServerCall.SimpleForwardingServerCall<ReqT, RespT>(
                    call) {
                @Override
                public void close(Status status, Metadata trailers) {
                    // Chỉ phản hồi ID đã qua kiểm tra; status do gRPC xử lý.
                    trailers.discardAll(REQUEST_ID_HEADER);
                    trailers.put(REQUEST_ID_HEADER, requestId);
                    super.close(status, trailers);
                }
            };

        return Contexts.interceptCall(
            scopedContext, decoratedCall, headers, next);
    }

    private static <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call, String description) {
        call.close(
            Status.INVALID_ARGUMENT.withDescription(description),
            new Metadata());
        return new ServerCall.Listener<ReqT>() {};
    }
}
```

Đây là một **chính sách minh họa**: việc bắt buộc request ID không phải quy định của gRPC. Với hệ thống có client bên ngoài, server cũng có thể tự sinh ID nếu header thiếu hoặc không đáng tin. Các endpoint như health check hoặc reflection có thể cần chính sách riêng.

`Contexts.interceptCall(...)` giúp thực thi bước tiếp theo và các callback liên quan với `Context` đã được gắn. Trong service:

```java
String id = RequestContextServerInterceptor.CURRENT_REQUEST_ID.get();
// Dùng id làm trường log đã được kiểm soát về định dạng.
```

Không dùng `ThreadLocal` tùy tiện thay `io.grpc.Context` để giữ dữ liệu theo RPC. Với các tác vụ chuyển sang executor tự quản, cần truyền context qua các luồng như trình bày ở phần sau.

## 6. Response headers và trailers: chặn ở đúng callback

Thông tin trả về của một RPC có thể gồm **initial response headers**, **message** và **trailers**. `Status` của gRPC được gửi khi kết thúc call.

| Vị trí | Callback phía server | Callback phía client | Ví dụ |
| --- | --- | --- | --- |
| Request metadata | Đọc từ tham số `headers` của `interceptCall(...)` | Ghi trước `ClientCall.start(...)` | `authorization`, `x-request-id` |
| Initial response headers | `ServerCall.sendHeaders(...)` | `ClientCall.Listener.onHeaders(...)` | `x-server-version` |
| Response trailers | `ServerCall.close(status, trailers)` | `ClientCall.Listener.onClose(status, trailers)` | `x-request-id` để hỗ trợ chẩn đoán lỗi |

Nếu muốn thêm thông tin vào **initial response headers**, một server interceptor có thể bọc `sendHeaders(...)`:

```java
// Đoạn minh họa bên trong ForwardingServerCall.
@Override
public void sendHeaders(Metadata responseHeaders) {
    responseHeaders.put(
        Metadata.Key.of(
            "x-server-version", Metadata.ASCII_STRING_MARSHALLER),
        "1.2.0");
    super.sendHeaders(responseHeaders);
}
```

`sendHeaders(...)` phải tuân thủ vòng đời call; không tự gọi nhiều lần hoặc gửi sau khi call đã đóng. Một lỗi RPC có thể kết thúc theo kiểu **trailers-only** nên client không nên mặc định có initial response headers.

Với ví dụ server ở mục 5, ID được thêm vào trailers trong `close(...)`; client đọc nó ở `onClose(...)`. Response trailers thích hợp cho thông tin cần có ở cuối RPC, kể cả khi ứng dụng không tạo message thành công.

Đừng tạo `grpc-status`, `grpc-message` hoặc `grpc-timeout` như custom metadata. Sử dụng `Status` và API deadline của gRPC.

## 7. Đăng ký interceptor trong Spring gRPC

Viết một lớp implement `ClientInterceptor` hoặc `ServerInterceptor` **chưa đủ** để nó chạy. Interceptor phải được gắn vào client call path hoặc server call path thật.

### Phía client

Một cách ở tầng `grpc-java` là gắn trực tiếp trên stub:

```java
GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(
            new RequestIdClientInterceptor());
```

Khi ứng dụng Spring quản lý stub/channel, hãy gắn interceptor thông qua cấu hình client được Spring gRPC hoặc starter đang dùng hỗ trợ. Kiểm tra phạm vi: một interceptor có thể chỉ áp dụng cho một stub/channel, hoặc cho nhiều client nếu được đăng ký toàn cục.

### Phía server

Ở tầng `grpc-java` thuần, có thể bọc service:

```java
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;

// GreeterService là một BindableService của ứng dụng.
ServerServiceDefinition interceptedService =
    ServerInterceptors.intercept(
        new GreeterService(),
        new RequestContextServerInterceptor());

// Đăng ký interceptedService với ServerBuilder hoặc server factory phù hợp.
```

Trong Spring gRPC, phương thức đăng ký server interceptor (qua cấu hình bean, annotation hoặc server factory) phụ thuộc phiên bản và starter đang sử dụng. Hãy chọn **một** cơ chế chính thức trong dự án, kiểm tra scope/order của interceptor và xác minh bằng RPC thử nghiệm. Không giả định rằng chỉ tạo một Spring `@Bean ServerInterceptor` luôn đồng nghĩa nó được tự động gắn vào mọi service ở mọi starter.

### Thứ tự nhiều interceptor

Một ứng dụng có thể cần:

```text
Inbound request
  -> tracing / correlation
  -> authentication
  -> authorization metadata policy
  -> service method
  -> response metadata / status / tracing close
```

Đây là **thứ tự mục tiêu của chính sách**, không phải cam kết thứ tự khi đăng ký interceptor qua bất kỳ API nào. Nhiều interceptor lồng nhau nên thứ tự thực tế còn ảnh hưởng callback phản hồi đi theo chiều ngược lại. Kiểm thử thứ tự được cấu hình ở cả client và server, đặc biệt nếu interceptor cần dữ liệu trong `Context` do interceptor khác tạo.

Nếu tracing và authentication cùng được nhiều framework tự động đăng ký, cần tránh tạo span trùng hoặc xác thực hai lần vô ý. Tách rõ “ai tạo metadata”, “ai kiểm tra metadata” và “ai quyết định quyền”.

## 8. Metadata interceptor với authentication, tracing và locale

Interceptor là vị trí thuận tiện để xử lý những thông tin chung, nhưng mỗi nhóm metadata cần một chính sách khác nhau:

| Metadata | Interceptor có thể làm gì? | Điều không nên làm |
| --- | --- | --- |
| `authorization` | Áp dụng `CallCredentials` ở client; xác minh token trong interceptor/auth layer phía server | Log token; coi header tồn tại là đã xác thực |
| `x-correlation-id` | Chuẩn hóa ID, gắn vào `Context`, hỗ trợ tìm log | Coi ID là bằng chứng danh tính |
| `traceparent`, `tracestate` | Inject/extract bằng propagator OpenTelemetry | Tự sửa trace ID/span ID, cài hai bộ tracing trùng lặp |
| `x-tenant-id` | Nhận tenant được yêu cầu, đối chiếu principal tin cậy | Cho phép đọc dữ liệu chỉ dựa trên ID client gửi |
| `x-locale` | Chọn locale đã cho phép và đưa vào context | Gọi `Locale.setDefault(...)` trên toàn JVM theo mỗi RPC |
| `x-proof-bin` | Đọc/ghi `byte[]` bằng binary marshaller | Tự Base64 thêm lần nữa hoặc đưa payload lớn vào headers |

Nếu cần bearer token thay đổi theo từng call, `CallCredentials` phù hợp với nhiệm vụ cung cấp credentials ở client. Không nên xây dựng một interceptor tự giữ token cố định của một người dùng trong singleton rồi dùng cho nhiều request.

**Bảo mật:** metadata đi qua kết nối gRPC, không được bảo mật chỉ vì nó là binary metadata. Dùng TLS/mTLS theo kiến trúc, xác thực nguồn tin cậy và chỉ ghi log các key nằm trong allowlist. Các trường như token, cookie, thông tin cá nhân và baggage nhạy cảm không nên được dump vào log/trace.

## 9. Deadline, cancellation, retry và streaming

### 9.1. Deadline và cancellation

Interceptor có thể quan sát trạng thái kết thúc nhưng không nên tự đặt header `grpc-timeout`. Ở client, sử dụng:

```java
import java.util.concurrent.TimeUnit;

GreeterGrpc.GreeterBlockingStub timedStub =
    baseStub.withDeadlineAfter(2, TimeUnit.SECONDS);
```

Khi deadline hết, caller có thể nhận `DEADLINE_EXCEEDED`. Nếu người dùng hoặc framework hủy call, logic server nên tôn trọng trạng thái hủy và tránh làm việc không cần thiết. Trong `onClose(...)`, interceptor có thể ghi status code và thời gian đã đo, nhưng không nên biến mọi lời gọi lỗi thành `OK` hoặc nuốt callback.

### 9.2. Retry

Một logical RPC có thể có nhiều attempt nếu cấu hình retry của gRPC cho phép. Interceptor được gọi ở tầng cao hoặc thấp của stack có thể quan sát mức độ khác nhau tùy loại interceptor và cách retry được thực hiện. **Không mặc định** “mỗi attempt chắc chắn tạo một request ID mới” chỉ dựa vào một `ClientInterceptor`.

Hãy định nghĩa request ID đang nhận diện **logical RPC** hay từng **attempt**. Nếu cần tìm từng attempt, bổ sung cách quan sát theo instrumentation/retry policy; không làm thay đổi ngữ nghĩa idempotency của nghiệp vụ. Một ID phục vụ log không tự thay thế idempotency key dùng để chống xử lý trùng.

### 9.3. Streaming RPC

`start(...)` ở client và `interceptCall(...)` ở server diễn ra khi stream bắt đầu. Metadata được gắn ở mức **RPC**, không tự gửi lại ở từng message `onNext(...)`.

| RPC | Metadata gửi khi nào? | Dữ liệu thay đổi theo từng message để ở đâu? |
| --- | --- | --- |
| Unary | Đầu một lời gọi | Trong request/response Protobuf |
| Server streaming | Khi mở RPC | Trong từng response message |
| Client streaming | Khi mở RPC | Trong từng request message |
| Bidirectional streaming | Khi mở RPC | Trong từng message hai chiều |

Với stream dài, cần cân nhắc token hết hạn, phân quyền bị thu hồi, deadline và kiểm soát tài nguyên. Không kỳ vọng đổi token hoặc tenant chỉ bằng cách chỉnh đối tượng `Metadata` sau khi call đã bắt đầu.

## 10. Truyền Context và xử lý bất đồng bộ

`io.grpc.Context` được thiết kế để giữ thông tin theo phạm vi call, ví dụ correlation ID, deadline hoặc trạng thái hủy. Server interceptor có thể dùng `Contexts.interceptCall(...)` để những callback gRPC tiếp theo nhìn thấy context phù hợp.

Nếu service tự đưa công việc sang thread pool, hãy chuyển context:

```java
import io.grpc.Context;
import java.util.concurrent.Executor;

// Trong callback của gRPC, khi context hiện hành còn được gắn:
Context grpcContext = Context.current();
Executor applicationExecutor = /* executor do ứng dụng quản lý */;

applicationExecutor.execute(grpcContext.wrap(() -> {
    String requestId =
        RequestContextServerInterceptor.CURRENT_REQUEST_ID.get();
    // Tiếp tục xử lý với request ID thuộc đúng RPC.
}));
```

Đoạn trên chỉ thể hiện cách truyền **gRPC Context**. `org.slf4j.MDC`, `io.opentelemetry.context.Context` và `LocaleContextHolder` của Spring là những cơ chế khác; có thể phải truyền, thiết lập và khôi phục chúng riêng hoặc dùng executor đã instrument. Tránh để MDC/locale của một request rò sang thread được sử dụng lại cho request khác.

Interceptor cũng cần cẩn thận với callback bất đồng bộ: khi thêm logging, metrics hoặc cleanup, phải bảo đảm callback được chuyển tiếp đúng vòng đời và công việc nặng không chặn executor I/O của gRPC.

## 11. Sai lầm thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| Không thấy header trên server | Client interceptor chưa đăng ký trên stub/channel thực sự được gọi | Kiểm tra đường tạo stub và test RPC đầu cuối |
| Server interceptor có bean nhưng không chạy | Server factory/starter chưa gắn interceptor hoặc sai scope | Đăng ký đúng cơ chế và xác minh bằng test |
| Header có hai giá trị xung đột | Nhiều interceptor hoặc caller cùng ghi một key | Quy định ownership và chính sách trùng key |
| `get(...)` trả về `null` | Sai tên key, khác loại ASCII/binary hoặc header không được gửi | Kiểm tra marshaller, tên key và callback |
| Response trailers không có dữ liệu mong đợi | Server không thêm dữ liệu ở `close(...)` hoặc RPC kết thúc theo đường khác | Bọc đúng `ServerCall` và test cả trường hợp lỗi |
| Log của các request lẫn nhau | Dùng chung `Metadata` mutable hoặc lưu ID trong static/global/thread-local không quản lý | Tạo dữ liệu theo call, dùng `Context` và cleanup |
| Một số method không được xác thực | Interceptor chỉ đăng ký cho một số service | Kiểm tra toàn bộ RPC nhạy cảm, gồm streaming |
| Gặp `UNAUTHENTICATED` dù đã gửi token | Token hết hạn, sai audience/issuer hoặc credential không được gắn đúng call | Kiểm tra luồng credentials và verifier |
| Lời gọi bị chậm | Interceptor chờ I/O đồng bộ ở callback quan trọng | Chuyển logic nặng sang cơ chế phù hợp; đặt timeout/deadline |
| Dữ liệu binary sai | Dùng key thiếu `-bin` hoặc tự Base64 sai | Dùng `byte[]` và binary marshaller đúng quy tắc |
| Trace bị đứt khi async | Không chuyển đúng trace context qua executor | Kiểm tra propagator và context wrapper |
| Lỗi bảo mật khi dùng header từ client | Tin tưởng tenant, role hoặc user ID chưa được xác thực | Dùng principal đã xác minh và policy ở server |

Không giữ giá trị metadata rất lớn. HTTP/2 headers và trailers chịu giới hạn ở server, client, proxy và load balancer. Với payload nghiệp vụ hoặc file lớn, dùng message Protobuf/stream phù hợp.

## 12. Kiểm thử metadata interceptor

**Unit test** giúp xác minh key, cách kiểm tra value và nhánh từ chối. **Integration test** qua client/server gRPC giúp khẳng định interceptor thật sự được đăng ký và hoạt động trong vòng đời call.

Một ma trận kiểm thử cơ bản:

| Tình huống | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Client có request ID trong option | `withOption(..., "req-42")` | Server thấy đúng `req-42` |
| Client không có request ID | Không đặt option | Client sinh ID hợp lệ theo từng RPC |
| Server không nhận request ID | Gọi client không gắn interceptor | `INVALID_ARGUMENT` theo chính sách minh họa |
| Server nhận hai request ID | Gửi hai value cùng key | Bị từ chối, không tùy tiện chọn một |
| RPC thành công | Có metadata hợp lệ | Service chạy với `CURRENT_REQUEST_ID` đúng |
| RPC thất bại sau khi vào service | Service trả lỗi | Client nhận status và ID trong trailers |
| Hai call đồng thời | Cùng channel, ID khác nhau | Không bị chia sẻ ID sai giữa hai RPC |
| Streaming nhiều message | Một RPC có nhiều request/response | Metadata gắn một lần, context vẫn thuộc stream đó |
| Deadline/hủy | RPC kéo dài quá deadline hoặc bị cancel | Status và cleanup đúng, không treo |
| Bảo mật | Header chứa token thử nghiệm | Không xuất hiện token trong log/trailer ngoài chính sách |
| Proxy/TLS | Gọi qua môi trường gần production | Metadata và bảo mật hoạt động qua đường mạng thực |

### Ví dụ kiểm thử tích hợp với in-process transport

Giả sử project có hợp đồng `Greeter` với `GreeterGrpc.GreeterImplBase`, `HelloRequest` và `HelloReply`. Test JUnit 5 dưới đây kiểm tra **đường đi qua interceptor thực**, không chỉ kiểm tra `Metadata.put/get`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class MetadataInterceptorIntegrationTest {

    static class GreeterService extends GreeterGrpc.GreeterImplBase {
        @Override
        public void sayHello(
                HelloRequest request,
                StreamObserver<HelloReply> responseObserver) {

            String id =
                RequestContextServerInterceptor.CURRENT_REQUEST_ID.get();
            responseObserver.onNext(
                HelloReply.newBuilder().setMessage(id).build());
            responseObserver.onCompleted();
        }
    }

    @Test
    void passesRequestIdThroughInterceptors() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                new GreeterService(),
                new RequestContextServerInterceptor()))
            .build()
            .start();

        ManagedChannel channel =
            InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
        try {
            GreeterGrpc.GreeterBlockingStub stub =
                GreeterGrpc.newBlockingStub(channel)
                    .withInterceptors(new RequestIdClientInterceptor())
                    .withOption(
                        RequestIdClientInterceptor.REQUEST_ID_OPTION,
                        "req-42");

            HelloReply reply = stub.sayHello(
                HelloRequest.newBuilder().setName("Lan").build());
            assertEquals("req-42", reply.getMessage());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
```

Đoạn test cần các dependency tương ứng với phiên bản `grpc-java`, JUnit 5 và các lớp generated từ `.proto`. Nó minh họa hành vi; nếu hợp đồng thực tế dùng service/message khác thì thay tên và phương thức tương ứng. `directExecutor()` thuận tiện trong bài kiểm thử nhỏ nhưng không thay thế kiểm thử concurrency, transport mạng hoặc TLS.

Để kiểm tra **response trailers**, bổ sung một client interceptor thu metadata trong `onClose(...)` rồi assert key `x-request-id`, kể cả khi service trả lỗi. Để kiểm tra đường từ chối, tạo lời gọi không gắn interceptor hoặc gắn hai value cho cùng key và assert `Status.Code.INVALID_ARGUMENT`.

## 13. Tình huống thực hành: giám sát RPC đặt hàng

Một ứng dụng Spring gRPC có `CheckoutService` gọi `InventoryService` rồi `PaymentService`. Đội vận hành cần tìm log của một giao dịch, đo độ trễ và bảo đảm client không thể giả danh người dùng khác thông qua metadata.

**Yêu cầu:**

1. Thiết kế một `ClientInterceptor` gắn `x-request-id` với giá trị được sinh theo từng RPC hoặc lấy từ context hợp lệ.
2. Thiết kế `ServerInterceptor` kiểm tra format, từ chối header lặp, đặt request ID vào `io.grpc.Context` và echo ID vào response trailers.
3. Đăng ký interceptor ở cả client và server theo cơ chế của phiên bản Spring gRPC đang dùng; xác minh bằng test.
4. Cấu hình `CallCredentials` hoặc cơ chế bảo mật phù hợp cho token; xác thực và phân quyền ở server, tránh ghi token vào log.
5. Dùng OpenTelemetry instrumentation để quản lý `traceparent`/`tracestate`. Kiểm tra cùng trace ID qua các hop, đồng thời giữ request ID phục vụ log.
6. Kiểm thử unary và streaming RPC, metadata lỗi, deadline, xử lý bất đồng bộ và tình huống proxy làm thay đổi giới hạn header.

**Câu hỏi tự kiểm tra:**

- Khác nhau giữa `ClientInterceptor.interceptCall(...)` và `ServerInterceptor.interceptCall(...)` là gì?
- Tại sao client thêm metadata trong `start(...)` thay vì sau khi đã gửi message?
- Phía client đọc response trailers trong callback nào?
- Vì sao chỉ viết một Spring bean implement `ServerInterceptor` chưa đủ để khẳng định nó chạy?
- Khi có hai interceptor cùng sửa `x-request-id`, nên thống nhất chính sách gì?
- Vì sao request ID không thay thế bearer token, phân quyền hay trace context?
- Khi service đưa công việc sang executor, cần lưu ý điều gì với `io.grpc.Context`, MDC và OpenTelemetry context?
- Trong bidirectional streaming, interceptor có chạy lại khi mỗi message được gửi đi không?

**Ghi nhớ:** Metadata interceptor là nơi tập trung logic **đọc, kiểm tra, thêm và quan sát metadata** trong vòng đời RPC của `grpc-java`. Client interceptor chuẩn bị request headers và lắng nghe phản hồi; server interceptor kiểm tra request headers, tạo context và có thể thêm response headers/trailers. Trong Spring gRPC, hãy đăng ký đúng phạm vi, kiểm thử đường đi thực, thiết kế ownership của metadata key và kết hợp cơ chế xác thực, deadline, tracing, TLS phù hợp để dịch vụ đáng tin cậy.
