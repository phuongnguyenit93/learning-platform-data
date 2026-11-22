# Metadata key và value trong gRPC

Trong một lời gọi gRPC, thông điệp Protocol Buffers mô tả **dữ liệu nghiệp vụ**, còn **metadata** chuyển thông tin bổ trợ cho việc xử lý lời gọi: định danh truy vết, thông tin xác thực, ngôn ngữ ưu tiên, phiên bản client hoặc dấu hiệu phục vụ quan sát hệ thống. Với Spring gRPC, ta vẫn làm việc với mô hình metadata của `grpc-java`; các interceptor phía client và server là vị trí thường dùng để tạo, đọc và kiểm soát dữ liệu này.

Sau bài học, bạn có thể:

- Phân biệt metadata với trường của message Protobuf và với trạng thái RPC.
- Chọn đúng tên `key`, kiểu `value` ASCII hoặc binary, và hiểu cách xử lý các giá trị trùng `key`.
- Đọc, ghi metadata bằng `io.grpc.Metadata` trong Java; gắn metadata vào client và đọc tại server qua interceptor.
- Xác định metadata đi trong request headers, response headers hay trailers; tránh can thiệp vào các header do gRPC quản lý.
- Thiết kế cách kiểm thử và bảo vệ metadata khi dùng Spring gRPC trong hệ thống nhiều dịch vụ.

## 1. Metadata nằm ở đâu trong một lời gọi gRPC?

Metadata là tập hợp các cặp **key–value** được gắn với *một lần gọi RPC*. Nó không phải là một phần của message khai báo trong file `.proto`. Vì vậy, thay đổi metadata thông thường không đòi hỏi sửa hợp đồng message hay sinh lại Java code từ Protobuf.

Trong giao thức gRPC trên HTTP/2, metadata được chuyển qua các header và trailer. Một lời gọi unary có thể được hình dung như sau:

```text
Client                                      Server
  |                                          |
  |-- Request headers ---------------------->|  metadata đầu vào:
  |   x-request-id: 7b9...                  |  x-request-id, authorization, ...
  |   authorization: Bearer ...             |
  |-- Protobuf request message ------------->|  dữ liệu nghiệp vụ
  |                                          |
  |<--------------------- Response headers --|  metadata đầu ra ban đầu
  |<-------------- Protobuf response message |  dữ liệu nghiệp vụ
  |<---------------------------- Trailers ---|  grpc-status, grpc-message, ...
  |                                          |
```

Đây là sơ đồ logic: một số lời gọi lỗi có thể kết thúc bằng **trailers-only**, không có message phản hồi hay response headers riêng. Với server streaming, client streaming hoặc bidirectional streaming, metadata đầu lời gọi vẫn gắn với **RPC**, không tự xuất hiện lại trên từng message trong luồng.

So sánh ba loại dữ liệu:

| Loại | Ví dụ | Nên dùng khi |
| --- | --- | --- |
| Trường message Protobuf | `order_id`, `quantity`, `customer_note` | Dữ liệu nghiệp vụ thuộc hợp đồng API, cần kiểm tra kiểu và tương thích phiên bản |
| Metadata ứng dụng | `x-request-id`, `x-client-version`, `authorization` | Thông tin điều khiển, bảo mật hoặc truy vết gắn với toàn bộ lời gọi |
| Metadata giao thức do gRPC quản lý | `grpc-timeout`, `grpc-status`, `grpc-message` | Thời hạn, kết quả và chi tiết trạng thái của RPC; dùng API gRPC tương ứng |

**Nguyên tắc chọn nơi lưu:** nếu thông tin là một phần ý nghĩa của yêu cầu hoặc phản hồi mà người dùng API cần hiểu, hãy đặt nó vào message Protobuf. Nếu thông tin phục vụ hạ tầng xử lý một cuộc gọi, metadata thường phù hợp hơn.

## 2. Quy tắc đặt tên metadata key

Một metadata key xác định cách diễn giải value. Trong gRPC Java, key được biểu diễn bằng `Metadata.Key<T>`, trong đó `T` là kiểu Java sau khi chuyển đổi dữ liệu.

| Quy tắc | Cách áp dụng |
| --- | --- |
| Tên key không phân biệt chữ hoa/chữ thường ở mức giao thức | Chủ động dùng chữ thường để thống nhất, ví dụ `x-request-id` |
| Tên hợp lệ dùng các ký tự ASCII chữ, số, dấu `-`, `_` và `.` | Chọn tên ngắn, rõ nghĩa; tránh khoảng trắng và ký tự Unicode |
| Key binary **phải có hậu tố** `-bin` | Ví dụ `x-proof-bin` ứng với value dạng `byte[]` |
| Các tên bắt đầu bằng `grpc-` được dành cho giao thức | Không đặt custom key như `grpc-my-token` |
| Header HTTP/2 dạng `:method`, `:path`, `:authority` là thành phần vận chuyển | Không tự thêm chúng qua `Metadata` |
| Có thể xuất hiện nhiều value cho cùng một key | Xác định rõ ứng dụng chấp nhận một hay nhiều giá trị |

Một số ví dụ:

| Key | Kiểu value | Mục đích |
| --- | --- | --- |
| `x-request-id` | ASCII string | Liên kết log giữa các dịch vụ |
| `x-client-version` | ASCII string | Ghi nhận phiên bản client để hỗ trợ tương thích |
| `authorization` | ASCII string | Mang thông tin xác thực, ví dụ bearer token |
| `x-proof-bin` | Binary bytes | Mang dữ liệu nhị phân có định dạng do hai phía thỏa thuận |

Đặt tên có tiền tố `x-` là một quy ước dễ nhận biết trong ứng dụng, **không phải** điều kiện bắt buộc của gRPC. Các cặp key–value tùy biến vẫn cần được hai phía thống nhất về ý nghĩa và kiểu dữ liệu.

## 3. Value ASCII và binary khác nhau như thế nào?

### 3.1. Metadata dạng ASCII

Value của key thông thường là chuỗi ASCII. Chúng phù hợp với mã truy vết, mã ngôn ngữ, version hoặc giá trị nhận dạng ngắn. Đừng mặc định chuỗi Unicode như tiếng Việt có thể gửi nguyên dạng trong ASCII metadata; nếu dữ liệu cần biểu diễn Unicode hoặc cấu trúc phức tạp, cân nhắc đưa vào Protobuf hoặc sử dụng một định dạng mã hóa được định nghĩa rõ ràng.

Với `grpc-java`, bộ chuyển đổi thông dụng là `Metadata.ASCII_STRING_MARSHALLER`:

```java
import io.grpc.Metadata;

Metadata.Key<String> requestIdKey =
    Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

Metadata headers = new Metadata();
headers.put(requestIdKey, "req-2026-00042");

String requestId = headers.get(requestIdKey);
System.out.println(requestId); // req-2026-00042
```

### 3.2. Metadata dạng binary

Binary metadata dùng cho chuỗi byte. Key phải kết thúc bằng `-bin`; trong Java, sử dụng `Metadata.BINARY_BYTE_MARSHALLER`:

```java
Metadata.Key<byte[]> proofKey =
    Metadata.Key.of("x-proof-bin", Metadata.BINARY_BYTE_MARSHALLER);

byte[] proof = new byte[] {0x01, 0x02, 0x7F};
headers.put(proofKey, proof);

byte[] receivedProof = headers.get(proofKey);
```

Khi truyền qua HTTP/2, binary metadata được mã hóa theo quy tắc giao thức (sử dụng Base64 trên đường truyền). **Thư viện gRPC xử lý việc này**: trong mã Java, bạn làm việc với `byte[]` và không cần tự mã hóa Base64 trước khi gọi `put`. Nếu tự Base64 rồi đưa chuỗi vào binary key, hai phía sẽ dễ hiểu sai dữ liệu.

Binary metadata không đồng nghĩa với dữ liệu được mã hóa bảo mật. Nếu mang thông tin nhạy cảm, vẫn cần TLS, kiểm soát quyền truy cập và chính sách ghi log phù hợp.

### 3.3. Lặp key và cách lấy value

Một `Metadata` có thể giữ nhiều value cho cùng key:

```java
Metadata.Key<String> tagKey =
    Metadata.Key.of("x-tag", Metadata.ASCII_STRING_MARSHALLER);

Metadata metadata = new Metadata();
metadata.put(tagKey, "internal");
metadata.put(tagKey, "priority");

String oneValue = metadata.get(tagKey);       // Giá trị cuối cùng: priority
Iterable<String> allValues = metadata.getAll(tagKey);
// allValues chứa cả "internal" và "priority"
```

`get(key)` trả về giá trị cuối cùng đã ghi cho key, hoặc `null` nếu không có; `getAll(key)` cho các giá trị tương ứng, hoặc `null` nếu vắng mặt. Đừng suy luận rằng mọi key chỉ có một value; với các key quan trọng như `authorization`, ứng dụng nên xác định rõ chính sách khi xuất hiện nhiều giá trị, tránh vô tình chọn một giá trị không mong muốn.

`Metadata` là đối tượng có thể thay đổi. Nên tạo metadata theo phạm vi lời gọi hoặc để interceptor bổ sung nó cho từng lần gọi; tránh dùng chung một đối tượng đang được sửa từ nhiều luồng.

## 4. Request headers, response headers và trailers

Cùng là metadata nhưng **vị trí xuất hiện** quyết định thời điểm sử dụng:

| Vị trí | Hướng truyền | Ví dụ | Khi nào đọc/ghi? |
| --- | --- | --- | --- |
| Request headers | Client → server | `x-request-id`, `authorization` | Client thêm trước khi bắt đầu RPC; server đọc trước khi chuyển xử lý cho service |
| Initial response headers | Server → client | `x-server-version`, thông tin định tuyến | Server gửi khi bắt đầu phản hồi; client nhận trước hoặc cùng quá trình xử lý kết quả |
| Response trailers | Server → client | `grpc-status`, `grpc-message`, chi tiết lỗi tùy biến | Gửi khi kết thúc RPC, kể cả RPC thất bại |

Ở tầng API, `grpc-status` là mã kết quả của RPC, ví dụ `OK`, `INVALID_ARGUMENT`, `UNAUTHENTICATED` hoặc `DEADLINE_EXCEEDED`. Trong Java, nên dùng `io.grpc.Status` và các phương thức gRPC để kết thúc lời gọi, không tự tạo custom metadata key mang tên `grpc-status`.

Đối với thông tin lỗi do ứng dụng tự định nghĩa, có thể dùng một trailer riêng (ví dụ `x-error-id`) nếu hai phía thống nhất. Phần lớn lỗi nghiệp vụ có cấu trúc vẫn cần cân nhắc sử dụng cơ chế error details theo chuẩn gRPC hoặc một thiết kế API rõ ràng, thay vì nhồi toàn bộ dữ liệu lỗi vào header.

## 5. Gắn metadata vào gRPC client bằng interceptor

Giả sử dự án đã sinh `GreeterGrpc` từ một file `.proto` và đã có `Channel` kết nối tới server. Mục tiêu là sinh **request ID mới cho mỗi RPC**, kể cả khi dùng lại cùng một stub:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class RequestIdClientInterceptor implements ClientInterceptor {

    private static final Metadata.Key<String> REQUEST_ID_KEY =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> responseListener,
                    Metadata headers) {

                headers.put(REQUEST_ID_KEY, UUID.randomUUID().toString());
                super.start(responseListener, headers);
            }
        };
    }
}
```

Gắn interceptor và deadline cho stub:

```java
import java.util.concurrent.TimeUnit;

GreeterGrpc.GreeterBlockingStub stub = GreeterGrpc.newBlockingStub(channel)
    .withInterceptors(new RequestIdClientInterceptor())
    .withDeadlineAfter(2, TimeUnit.SECONDS);

// stub.sayHello(...) sẽ gửi x-request-id trong request headers.
```

Trong ví dụ, mỗi lần gọi `start(...)` sẽ thêm một UUID mới. Cơ chế `withDeadlineAfter(...)` dùng API gRPC để thiết lập deadline; thư viện sẽ lo phần metadata giao thức tương ứng. Không nên tự đặt `grpc-timeout` bằng `Metadata.put`.

Nếu chỉ cần metadata **cố định** cho một trường hợp đơn giản, `io.grpc.stub.MetadataUtils.newAttachHeadersInterceptor(metadata)` cũng có thể gắn một bộ header đã chuẩn bị. Interceptor tự tạo request ID như trên phù hợp hơn khi value phải đổi theo từng lần gọi.

## 6. Đọc và kiểm tra metadata tại gRPC server

Server interceptor nhận request headers **trước** khi chuyển lời gọi cho service. Ví dụ dưới đây quy định `x-request-id` là bắt buộc và đưa nó vào `io.grpc.Context` để code xử lý có thể đọc:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class RequestIdServerInterceptor implements ServerInterceptor {

    private static final Metadata.Key<String> REQUEST_ID_KEY =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    private static final Context.Key<String> REQUEST_ID_CONTEXT =
        Context.key("request-id");

    public static String currentRequestId() {
        return REQUEST_ID_CONTEXT.get();
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID_KEY);
        if (requestId == null || requestId.isBlank()) {
            call.close(
                Status.INVALID_ARGUMENT.withDescription(
                    "x-request-id is required"),
                new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context =
            Context.current().withValue(REQUEST_ID_CONTEXT, requestId);

        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Trong phương thức RPC phía server, có thể gọi `RequestIdServerInterceptor.currentRequestId()` để lấy request ID đã được interceptor gán. `Context` thuộc luồng thực thi gRPC của lời gọi; nếu tự chuyển sang executor hoặc luồng bất đồng bộ khác, cần truyền context đúng cách để không mất giá trị.

**Lưu ý về ví dụ:** quy định phải có request ID là một **chính sách minh họa**. Trong hệ thống thực tế, server cũng có thể tự sinh ID nếu client không gửi. Nếu client cung cấp ID để ghi log, cần giới hạn độ dài và định dạng trước khi đưa vào hệ thống quan sát.

### Tích hợp trong Spring gRPC

Spring gRPC cho phép xây dựng dịch vụ trên `grpc-java`, do đó `ClientInterceptor` và `ServerInterceptor` ở trên có thể tái sử dụng. Hãy đăng ký interceptor theo cơ chế cấu hình server/client của phiên bản Spring gRPC hoặc starter đang dùng. Cách khai báo global interceptor, phạm vi áp dụng và thứ tự thực thi có thể khác nhau theo phiên bản; cần kiểm tra cấu hình thực tế của ứng dụng.

Ở phía client, cấu hình để interceptor được gắn vào đúng stub/channel. Ở phía server, bảo đảm interceptor chạy trên dịch vụ cần kiểm tra metadata. Nếu có nhiều interceptor (xác thực, tracing, logging), cần thiết kế rõ thứ tự và trách nhiệm của chúng.

## 7. Metadata liên quan gì đến xác thực, deadline và tracing?

### Xác thực

`authorization` thường chứa thông tin xác thực do client gửi. Tuy nhiên, việc **có header** không có nghĩa client đã được xác thực: server phải xác minh chữ ký, thời hạn, đối tượng phát hành và quyền theo phương án bảo mật của hệ thống. Một custom header như `x-user-id` không nên được xem là danh tính đáng tin cậy nếu chưa được một thành phần tin cậy kiểm chứng.

Trong `grpc-java`, `CallCredentials` là một lựa chọn để gắn thông tin xác thực theo lời gọi. Với kết nối qua mạng, sử dụng TLS để bảo vệ dữ liệu trên đường truyền; metadata tự nó không bảo đảm bí mật. Không ghi token, cookie hoặc dữ liệu nhạy cảm vào log/trace, kể cả ở mức debug.

### Deadline và hủy lời gọi

`grpc-timeout` là metadata do giao thức quản lý. Thay vì tự điền header này, client Java gọi `withDeadlineAfter(...)` hoặc `withDeadline(...)`. Khi deadline hết, client có thể nhận `DEADLINE_EXCEEDED`; code server nên kiểm tra trạng thái hủy và ngừng công việc không còn cần thiết. Khi tạo RPC xuống dịch vụ khác, cần chú ý truyền deadline phù hợp để tránh lời gọi con tiếp tục chạy vô hạn.

### Truy vết phân tán

Một request ID ứng dụng giúp tìm log theo lời gọi, nhưng **không thay thế** trace ID và span ID của tracing phân tán. Hệ thống dùng OpenTelemetry có thể truyền ngữ cảnh truy vết qua metadata theo bộ propagator được cấu hình. Ưu tiên cấu hình instrumentation/propagator thống nhất giữa các dịch vụ, tránh mỗi interceptor tự tạo một kiểu trace header khác nhau.

### Streaming

Với streaming RPC, client gửi metadata khi khởi tạo call, rồi truyền nhiều message Protobuf. Nếu một thông tin thay đổi theo **từng message** (ví dụ số thứ tự, thời điểm đo hoặc thuộc tính từng bản ghi), hãy đưa nó vào message Protobuf. Không cố dùng request metadata để mang các giá trị thay đổi liên tục trong luồng. Kết quả cuối cùng của streaming RPC vẫn được báo qua status/trailers.

## 8. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Server không tìm được metadata | Sai tên key, nhầm ASCII và `-bin`, interceptor chưa được đăng ký | Thống nhất key và marshaller, kiểm tra cấu hình interceptor ở cả hai phía |
| Dữ liệu binary sai sau khi giải mã | Tự mã hóa Base64 trước khi dùng binary marshaller | Gửi `byte[]` trực tiếp; để gRPC thực hiện chuyển đổi trên đường truyền |
| Truyền được trong unary nhưng không cập nhật theo streaming message | Metadata chỉ gắn theo RPC | Đưa giá trị thay đổi theo message vào Protobuf |
| Request ID luôn giống nhau | Tạo ID duy nhất khi khởi tạo stub/interceptor | Sinh ID trong `start(...)` cho từng call |
| Client nhận `UNAUTHENTICATED` dù có header | Token sai/hết hạn hoặc server không tin cậy giá trị gửi đến | Kiểm tra quá trình cấp và xác minh credentials; không chỉ kiểm tra sự hiện diện |
| Lỗi ở proxy trước khi tới service | Tổng kích thước header/trailer vượt giới hạn hạ tầng | Giữ metadata gọn; chuyển payload lớn sang message hoặc nơi lưu phù hợp |
| Log bị lộ secret | Ghi toàn bộ `Metadata` vào log | Chỉ log key được phép và che giá trị nhạy cảm |
| Mất request ID khi chuyển sang xử lý bất đồng bộ | Không chuyển tiếp `Context` qua executor | Sử dụng cơ chế truyền context của gRPC phù hợp với kiểu xử lý |

Metadata không phải kho lưu dữ liệu tự do. Value lớn làm tăng chi phí truyền, có thể vượt giới hạn header của server, proxy hoặc load balancer. Không dùng metadata để mang file, JSON lớn hay các đối tượng nghiệp vụ phức tạp.

## 9. Chiến lược kiểm thử

Với Spring gRPC, có thể kiểm thử interceptor bằng server/client gRPC trong bộ kiểm thử tích hợp. `InProcessServerBuilder` và `InProcessChannelBuilder` của `grpc-java` hữu ích cho các bài kiểm tra không cần mở cổng mạng, nhưng kiểm thử TLS hoặc hành vi của proxy cần môi trường kết nối thực.

| Ca kiểm thử | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| ASCII hợp lệ | Client gửi `x-request-id: req-42` | Server đọc đúng `req-42` |
| Thiếu key bắt buộc theo ví dụ | Không gửi `x-request-id` | Server trả `INVALID_ARGUMENT` với mô tả phù hợp |
| Binary round-trip | Gửi `x-proof-bin` với mảng byte chứa cả byte không in được | Server nhận đúng từng byte |
| Key lặp | Gửi hai value cho `x-tag` | `getAll` lấy được cả hai; xử lý theo chính sách đã thống nhất |
| Hai RPC liên tiếp | Dùng lại một stub đã gắn interceptor | Mỗi RPC có request ID khác nhau |
| Deadline quá ngắn | Client đặt deadline ngắn hơn thời gian xử lý | Caller nhận trạng thái deadline phù hợp và server có khả năng xử lý hủy |
| Streaming nhiều message | Tạo một stream có nhiều message | Metadata gắn với lời gọi; dữ liệu biến thiên được đọc từ từng message |
| Bảo mật/quan sát | Gửi token thử nghiệm và bật log | Không lộ token; chỉ log ID và trường đã cho phép |

Khi test metadata có trailer, hãy bắt metadata ở sự kiện kết thúc RPC (`onClose(status, trailers)` của client interceptor). Giá trị trong trailer chỉ chắc chắn xuất hiện khi call kết thúc, vì vậy không nên kiểm tra nó ngay sau khi nhận message đầu tiên.

## 10. Tình huống thực hành

Một hệ thống Spring gRPC có client `checkout-service` gọi unary RPC `InventoryService.ReserveStock` để giữ hàng, sau đó có thể gọi một streaming RPC để nhận tiến độ xử lý. Nhóm muốn liên kết log từ hai dịch vụ và tránh tạo request chạy quá lâu.

1. Thống nhất custom key `x-request-id` là ASCII metadata. Client tạo ID cho mỗi yêu cầu người dùng và truyền cùng ID qua các RPC liên quan, đồng thời giữ span context của tracing theo cơ chế riêng.
2. Client thiết lập deadline bằng API stub. `inventory-service` đọc request ID tại server interceptor, kiểm tra định dạng và đưa vào `Context` để các log của RPC sử dụng.
3. Trường `product_id`, `quantity` và trạng thái giữ hàng được định nghĩa trong message Protobuf; chúng không được chuyển sang metadata chỉ vì có thể mã hóa thành chuỗi.
4. Nếu nghiệp vụ cần gửi mã chứng thực nhị phân chuyên dụng, hai phía thỏa thuận key `x-proof-bin` và biểu diễn value bằng `byte[]`; nếu dùng token chuẩn, ưu tiên cơ chế credentials và xác thực phù hợp.
5. Với streaming, trạng thái tiến độ được đưa vào từng response message. Server kết thúc stream bằng gRPC status; nếu trả lỗi thì client đọc status và, khi có, error details/trailers.

**Bài tập tự kiểm tra:**

- Vì sao `x-request-id` hợp lý hơn `grpc-request-id` cho metadata tùy biến?
- Nếu ứng dụng gửi value nhị phân có byte `0x00`, nên dùng marshaller nào và vì sao không tự Base64?
- Khi nào dùng `getAll` thay cho `get`?
- Một trường `discount_code` quyết định cách tính giá phải đặt ở metadata hay request message? Giải thích theo hợp đồng API.
- Vì sao đặt header `authorization` mà bỏ qua xác minh token là không đủ để bảo vệ RPC?

**Kết luận:** Metadata là kênh mang ngữ cảnh của lời gọi gRPC qua các cặp key–value. Thiết kế đúng bắt đầu từ việc phân biệt ASCII và binary, chọn vị trí headers/trailers, quản lý vòng đời theo từng RPC và dùng API của `grpc-java` cho status, deadline và credentials. Khi triển khai trong Spring gRPC, hãy kiểm thử cả đường đi của metadata qua interceptor và các ranh giới bảo mật, mạng, luồng xử lý.
