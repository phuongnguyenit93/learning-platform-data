# Metadata từ client sang server

Trong một lời gọi gRPC, client thường cần gửi thêm thông tin để server hiểu **ngữ cảnh của lời gọi**: request ID để tìm log, phiên bản ứng dụng, locale hoặc credentials. Những thông tin này có thể được gửi dưới dạng **request metadata** qua HTTP/2 headers. Phía server nhận chúng trong API `io.grpc.Metadata` trước khi xử lý message Protobuf.

Trong Spring gRPC, đường đi này được triển khai trên nền `grpc-java`. Client có thể gắn metadata vào từng call bằng `ClientInterceptor` hoặc cơ chế credentials; server đọc metadata ở `ServerInterceptor`, kiểm tra giá trị và chuyển dữ liệu đã được chấp nhận vào `io.grpc.Context` cho service. Hiểu rõ ranh giới này giúp tránh việc lặp code trong từng RPC và tránh tin nhầm dữ liệu do client tự khai.

Sau bài học, bạn có thể:

- Mô tả đường đi của request metadata từ client qua transport đến server.
- Tạo metadata key ASCII và binary, rồi gắn value vào call ở client.
- Đọc, kiểm tra value và xử lý key lặp trong server interceptor.
- Chuyển metadata đã được kiểm tra sang service bằng `io.grpc.Context`.
- Hiểu metadata được gửi một lần ở đầu unary hoặc streaming RPC và không tự động truyền sang RPC downstream.
- Đăng ký interceptor trong ứng dụng Spring gRPC và kiểm thử đường đi client–server.

## 1. Đường đi của request metadata

Request metadata thuộc về **một lời gọi RPC**. Client chuẩn bị metadata khi bắt đầu call; gRPC chuyển nó qua HTTP/2 request headers; server nhận và đưa các cặp key–value vào đối tượng `Metadata`.

```text
Client application          ClientInterceptor        HTTP/2 transport        ServerInterceptor        Service
       |                           |                       |                       |                   |
       | gọi stub.method(...)      |                       |                       |                   |
       |-------------------------->|                       |                       |                   |
       |                           | thêm request metadata |                       |                   |
       |                           |---------------------->|                       |                   |
       |                           |                       | request headers      |                   |
       |                           |                       |---------------------->|                   |
       |                           |                       |                       | đọc/kiểm tra      |
       |                           |                       |                       | Metadata          |
       |                           |                       |                       | tạo Context      |
       |                           |                       |                       |------------------>|
       |                           |                       |                       |                   |
       |                           |                       |       Protobuf message|------------------>|
       |                           |                       |                       |                   |
```

Trình tự có ý nghĩa:

1. Ứng dụng gọi phương thức trên generated stub.
2. Client interceptor được gọi để tạo `ClientCall`; khi call bắt đầu, interceptor có thể bổ sung request headers.
3. gRPC gửi headers cùng với quá trình mở RPC. Metadata đã được gửi không thể sửa bằng cách thay đổi đối tượng Java sau đó.
4. Server interceptor nhận `Metadata headers` trong `interceptCall(...)`, trước khi service xử lý request message.
5. Server kiểm tra metadata, tạo context phù hợp rồi chuyển call cho interceptor kế tiếp hoặc service.
6. Service xử lý message Protobuf trong phạm vi call đã có ngữ cảnh.

Server không nhận trực tiếp một chuỗi HTTP/2 header thô để tự parse. `grpc-java` đã chuyển dữ liệu vận chuyển thành `Metadata` và áp dụng marshaller tương ứng. Vì vậy, code server nên sử dụng `Metadata.Key<T>` thay vì tự giải mã header ở tầng socket.

## 2. Chọn dữ liệu nào để gửi bằng metadata?

Metadata phù hợp với thông tin **bổ trợ cho toàn bộ RPC**, ví dụ:

| Thông tin | Ví dụ key | Lý do |
| --- | --- | --- |
| Mã yêu cầu | `x-request-id` | Liên kết log của một lời gọi |
| Phiên bản client | `x-client-version` | Phân tích tương thích hoặc hỗ trợ sự cố |
| Ngôn ngữ ưu tiên | `x-locale` | Chọn nội dung hiển thị nếu API có chính sách địa phương hóa |
| Credentials | `authorization` | Chuyển thông tin xác thực theo cơ chế đã thỏa thuận |
| Trace context | `traceparent`, `tracestate` | Liên kết span trong distributed tracing |

Nếu dữ liệu là **nội dung nghiệp vụ** mà service cần xử lý, hãy đặt nó trong message Protobuf. Ví dụ `order_id`, `quantity`, `shipping_address` và danh sách sản phẩm thuộc request message. Không chuyển các trường này sang metadata chỉ để tránh sửa `.proto`.

Một nguyên tắc hữu ích: metadata được xác định khi mở call và áp dụng cho cả RPC; message Protobuf được gửi theo nội dung và số lượng message của phương thức unary hoặc streaming.

## 3. Khai báo key ở client và server

Hai phía cần thống nhất tên key và kiểu value. `Metadata.Key<T>` kết hợp tên với marshaller chuyển đổi dữ liệu Java khi gửi/nhận.

### ASCII metadata

Các chuỗi ngắn như request ID và client version dùng `Metadata.ASCII_STRING_MARSHALLER`:

```java
import io.grpc.Metadata;

static final Metadata.Key<String> REQUEST_ID =
    Metadata.Key.of(
        "x-request-id",
        Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<String> CLIENT_VERSION =
    Metadata.Key.of(
        "x-client-version",
        Metadata.ASCII_STRING_MARSHALLER);
```

Tên metadata key dùng chữ thường và ký tự ASCII hợp lệ. Các key bắt đầu bằng `grpc-` thuộc phạm vi dành riêng của giao thức; không tự tạo key ứng dụng như `grpc-my-request-id`.

### Binary metadata

Nếu thực sự cần gửi dãy byte, key phải kết thúc bằng `-bin` và dùng `Metadata.BINARY_BYTE_MARSHALLER`:

```java
static final Metadata.Key<byte[]> CAPABILITIES =
    Metadata.Key.of(
        "x-client-capabilities-bin",
        Metadata.BINARY_BYTE_MARSHALLER);
```

Trên đường truyền, gRPC xử lý biểu diễn Base64 của binary metadata. Ở code Java, client vẫn đưa `byte[]` gốc vào `put(...)`, server nhận lại `byte[]`; không tự Base64 trước khi dùng binary marshaller. Binary metadata không đồng nghĩa với mã hóa bảo mật.

### Thỏa thuận giữa hai phía

Một hợp đồng metadata cần xác định ít nhất:

- Tên key và kiểu ASCII/binary.
- Ý nghĩa, định dạng và giới hạn độ dài của value.
- Key bắt buộc hay tùy chọn; giá trị mặc định nếu vắng mặt.
- Chính sách khi key xuất hiện nhiều lần.
- Thành phần nào được phép tạo hoặc ghi đè value.
- Server phản hồi ra sao khi value sai định dạng hoặc không được phép.

Không có một bộ custom metadata key tự động được sinh từ file `.proto`. Hợp đồng này thường được ghi trong tài liệu API, cấu hình client/server và kiểm thử tích hợp.

## 4. Gắn metadata ở client bằng ClientInterceptor

`ClientInterceptor` nhìn thấy phương thức RPC, `CallOptions` và channel tiếp theo. Nó có thể bọc `ClientCall` để thêm headers trong `start(...)`, ngay trước khi call bắt đầu gửi request.

Ví dụ dưới đây truyền `x-request-id` theo từng RPC. Nếu ứng dụng không cung cấp ID qua `CallOptions`, interceptor tạo UUID mới:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class RequestMetadataClientInterceptor
        implements ClientInterceptor {

    public static final CallOptions.Key<String> REQUEST_ID_OPTION =
        CallOptions.Key.create("request-id");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> CLIENT_VERSION_HEADER =
        Metadata.Key.of(
            "x-client-version",
            Metadata.ASCII_STRING_MARSHALLER);

    private final String clientVersion;

    public RequestMetadataClientInterceptor(String clientVersion) {
        this.clientVersion = clientVersion;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> responseListener,
                    Metadata headers) {

                String suppliedId =
                    callOptions.getOption(REQUEST_ID_OPTION);
                String requestId =
                    suppliedId != null
                        && suppliedId.matches("[A-Za-z0-9._-]{1,64}")
                    ? suppliedId
                    : UUID.randomUUID().toString();

                // Interceptor này sở hữu hai key ứng dụng bên dưới.
                headers.discardAll(REQUEST_ID_HEADER);
                headers.put(REQUEST_ID_HEADER, requestId);

                headers.discardAll(CLIENT_VERSION_HEADER);
                headers.put(CLIENT_VERSION_HEADER, clientVersion);

                super.start(responseListener, headers);
            }
        };
    }
}
```

`CallOptions.Key` là nơi lưu lựa chọn cho một call; nó không tự trở thành header. Interceptor đọc option rồi ghi value vào `Metadata`. Việc dùng `discardAll(...)` ở đây thể hiện rõ interceptor chịu trách nhiệm cho hai key này và bảo đảm không gửi nhiều value ngoài ý muốn.

Gắn interceptor vào generated stub:

```java
GreeterGrpc.GreeterBlockingStub baseStub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(
            new RequestMetadataClientInterceptor("2.4.0"));

GreeterGrpc.GreeterBlockingStub callStub =
    baseStub.withOption(
        RequestMetadataClientInterceptor.REQUEST_ID_OPTION,
        "req-order-42");

// callStub.sayHello(...) sẽ gửi request metadata.
```

`GreeterGrpc`, `channel` và `sayHello(...)` là tên minh họa cho code được sinh từ `.proto`. Trong ứng dụng thực tế, dùng stub tương ứng với service của bạn. Interceptor có thể được gắn vào một stub cụ thể hoặc channel dùng chung; phạm vi đó quyết định những RPC nào nhận metadata.

### Gắn metadata trực tiếp cho một call

Khi chỉ có một call đơn giản, có thể tạo `Metadata` và dùng tiện ích `MetadataUtils` của phiên bản `grpc-java` tương ứng để attach headers:

```java
Metadata headers = new Metadata();
headers.put(REQUEST_ID, "req-manual-42");

GreeterGrpc.GreeterBlockingStub oneCallStub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(
            MetadataUtils.newAttachHeadersInterceptor(headers));
```

Đây là lựa chọn gọn cho trường hợp cố định. Nếu metadata phải thay đổi theo từng RPC, cần chú ý vòng đời và khả năng tái sử dụng stub/interceptor. Với credentials, ưu tiên `CallCredentials` hoặc tích hợp bảo mật phù hợp để xử lý việc cấp token, làm mới và áp dụng theo call.

## 5. Server nhận metadata ở ServerInterceptor

`ServerInterceptor.interceptCall(...)` nhận ba thành phần quan trọng:

- `ServerCall`: call phía server, dùng để gửi headers hoặc đóng call với status/trailers.
- `Metadata headers`: request metadata do client gửi.
- `ServerCallHandler next`: chuyển tiếp tới interceptor tiếp theo hoặc service.

Ví dụ sau kiểm tra request ID và client version, từ chối header lặp, rồi đưa giá trị đã chấp nhận vào `io.grpc.Context`:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;

public final class RequestMetadataServerInterceptor
        implements ServerInterceptor {

    public static final Context.Key<String> REQUEST_ID =
        Context.key("request-id");
    public static final Context.Key<String> CLIENT_VERSION =
        Context.key("client-version");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> CLIENT_VERSION_HEADER =
        Metadata.Key.of(
            "x-client-version",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        final String requestId;
        final String clientVersion;
        try {
            requestId = singleValue(headers, REQUEST_ID_HEADER);
            clientVersion = singleValue(headers, CLIENT_VERSION_HEADER);
        } catch (IllegalArgumentException ex) {
            return reject(call, "Repeated request metadata");
        }

        if (requestId == null
                || !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
            return reject(call, "Missing or invalid x-request-id");
        }

        if (clientVersion == null
                || clientVersion.length() > 32
                || !clientVersion.matches("[A-Za-z0-9.+_-]+")) {
            return reject(call, "Missing or invalid x-client-version");
        }

        Context context = Context.current()
            .withValue(REQUEST_ID, requestId)
            .withValue(CLIENT_VERSION, clientVersion);

        return Contexts.interceptCall(context, call, headers, next);
    }

    private static String singleValue(
            Metadata headers, Metadata.Key<String> key) {
        Iterable<String> values = headers.getAll(key);
        if (values == null) {
            return null;
        }
        Iterator<String> iterator = values.iterator();
        if (!iterator.hasNext()) {
            return null;
        }
        String value = iterator.next();
        if (iterator.hasNext()) {
            throw new IllegalArgumentException("Duplicate metadata");
        }
        return value;
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

Quy tắc bắt buộc request ID và client version ở đây là **chính sách minh họa**. Nếu một client hợp lệ không có client version, ứng dụng có thể cho phép thiếu và dùng giá trị `unknown`; nếu request ID thiếu, server có thể tự sinh ID thay vì từ chối. Hãy chọn chính sách phù hợp với hợp đồng API và áp dụng nhất quán.

### Tại sao dùng getAll thay vì chỉ get?

`Metadata` có thể chứa nhiều value cho cùng key. `get(key)` trả về value cuối cùng hoặc `null` nếu không có; `getAll(key)` cho phép server nhận biết key lặp. Với key có tính duy nhất như request ID, authorization hoặc tenant selection, việc chấp nhận nhiều value mà không có chính sách có thể khiến các lớp xử lý hiểu khác nhau.

Không phải mọi key đều bắt buộc duy nhất. Nếu một key được thiết kế để lặp, cần định nghĩa thứ tự và ý nghĩa của từng value. Không gộp hoặc tách thủ công header ở tầng chuỗi nếu `Metadata` đã cung cấp API typed.

## 6. Service đọc metadata đã được kiểm tra

Sau khi server interceptor gắn context, service method có thể đọc giá trị theo phạm vi call:

```java
String requestId =
    RequestMetadataServerInterceptor.REQUEST_ID.get();
String clientVersion =
    RequestMetadataServerInterceptor.CLIENT_VERSION.get();

logger.info(
    "RPC received: requestId={}, clientVersion={}",
    requestId,
    clientVersion);
```

Ví dụ này chỉ ghi hai giá trị đã qua kiểm tra hình thức. Nếu cần xác thực danh tính, phải có interceptor/credentials riêng và không được suy ra người dùng từ request ID hoặc client version.

`io.grpc.Context` gắn dữ liệu với call thay vì lưu vào biến toàn cục. Khi code chuyển sang executor riêng, hãy truyền context phù hợp:

```java
import io.grpc.Context;
import java.util.concurrent.Executor;

Context callContext = Context.current();
Executor executor = applicationExecutor;

executor.execute(callContext.wrap(() -> {
    String requestId =
        RequestMetadataServerInterceptor.REQUEST_ID.get();
    // Xử lý tiếp trong đúng ngữ cảnh RPC.
}));
```

`io.grpc.Context` không tự động đồng nhất với OpenTelemetry context, Spring `LocaleContextHolder` hoặc SLF4J MDC. Nếu cần trace/span hoặc locale trong thread khác, sử dụng cơ chế propagation tương ứng và khôi phục trạng thái sau khi xử lý.

## 7. Metadata từ client không tự động chuyển sang RPC downstream

Một điểm quan trọng khi xây dựng microservice: request metadata nhận ở server chỉ gắn với **call hiện tại**. Nếu OrderService gọi InventoryService, đó là một RPC mới với `ClientCall` mới. gRPC không tự động sao chép toàn bộ inbound metadata sang outbound call.

Luồng đúng:

```text
Client A                 OrderService                    InventoryService
   |                          |                                  |
   | x-request-id: req-42     |                                  |
   |------------------------->|                                  |
   |                          | đọc, kiểm tra, lưu Context        |
   |                          |                                  |
   |                          | tạo RPC downstream               |
   |                          | x-request-id: req-42              |
   |                          |--------------------------------->|
   |                          |                                  | đọc metadata
   |                          |                                  |
```

OrderService cần **chọn lọc** những key được phép truyền tiếp. Không sao chép mù quáng mọi headers: inbound metadata có thể chứa token chỉ dành cho một audience, thông tin do client công cộng tự khai hoặc giá trị nhạy cảm.

Ví dụ lấy request ID đã kiểm tra từ context và gắn vào call downstream:

```java
String verifiedRequestId =
    RequestMetadataServerInterceptor.REQUEST_ID.get();

InventoryGrpc.InventoryBlockingStub downstream =
    InventoryGrpc.newBlockingStub(inventoryChannel)
        .withInterceptors(
            new RequestMetadataClientInterceptor("2.4.0"))
        .withOption(
            RequestMetadataClientInterceptor.REQUEST_ID_OPTION,
            verifiedRequestId);

// downstream.reserveStock(...) gửi request ID đã được chọn lọc.
```

Trong ứng dụng thực tế, có thể thiết kế một client interceptor đọc correlation context từ cơ chế propagation chung thay vì phải gọi `withOption(...)` ở từng vị trí. Dù dùng cách nào, cần giữ rõ ranh giới: **giá trị inbound đã kiểm tra** mới được phép trở thành metadata outbound.

Trace context nên được inject/extract bằng OpenTelemetry propagator hoặc instrumentation tương ứng. Không tự sao chép `traceparent` như một chuỗi tĩnh nếu điều đó làm sai parent span của lời gọi downstream.

## 8. Request metadata với unary và streaming RPC

Metadata được gắn ở đầu RPC, vì vậy cách nhận ở server interceptor giống nhau đối với các kiểu phương thức:

| Loại RPC | Request metadata được gửi khi nào? | Message được gửi khi nào? |
| --- | --- | --- |
| Unary | Một lần khi bắt đầu call | Một request message |
| Server streaming | Một lần khi mở call | Một request message, sau đó nhiều response message |
| Client streaming | Một lần khi mở call | Nhiều request message |
| Bidirectional streaming | Một lần khi mở call | Nhiều request và response message độc lập theo luồng |

Server interceptor xử lý metadata trước khi service nhận message đầu tiên. Với streaming, các callback `onMessage(...)` tiếp theo vẫn thuộc call đã có context đó. Không cần lặp `x-request-id` trong từng message chỉ để server biết chúng thuộc cùng RPC.

Nếu tenant, sequence number hoặc một thuộc tính thực sự thay đổi theo từng message, đó là dữ liệu của message Protobuf và cần được kiểm tra ở từng message. Không cố sửa request metadata sau khi stream đã bắt đầu.

## 9. Spring gRPC: đăng ký client và server interceptor

`ClientInterceptor` và `ServerInterceptor` là API của `grpc-java`; Spring gRPC cung cấp cách tích hợp chúng vào channel/client và server theo phiên bản, starter và cấu hình ứng dụng đang dùng.

### Client

Ở tầng generated stub, có thể gắn interceptor trực tiếp:

```java
GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(
            new RequestMetadataClientInterceptor("2.4.0"));
```

Nếu channel hoặc stub do Spring quản lý, đăng ký interceptor tại điểm cấu hình client mà phiên bản Spring gRPC hỗ trợ. Xác minh interceptor thực sự nằm trên đường gọi mà bean sử dụng; tạo bean Java nhưng không gắn vào channel sẽ không làm metadata tự xuất hiện.

### Server

Với `grpc-java`, có thể bọc service bằng interceptor:

```java
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;

ServerServiceDefinition interceptedService =
    ServerInterceptors.intercept(
        new GreeterService(),
        new RequestMetadataServerInterceptor());

// Đăng ký interceptedService qua ServerBuilder/server factory.
```

Trong Spring gRPC, hãy dùng cơ chế đăng ký server interceptor của phiên bản/starter đang triển khai. Không mặc định một `@Bean ServerInterceptor` sẽ tự động áp dụng cho mọi service trong mọi phiên bản. Kiểm tra:

- Interceptor có được gắn vào đúng server/service không?
- Nó áp dụng cho tất cả method hay chỉ một nhóm method?
- Thứ tự với tracing, authentication và authorization có đúng không?
- Endpoint health/reflection có cần chính sách khác không?
- Có test khẳng định request metadata thực sự tới interceptor không?

### Thứ tự interceptor và trách nhiệm

Một chuỗi xử lý thường cần tracing/correlation, authentication, authorization và service method. Thứ tự cụ thể phụ thuộc cơ chế đăng ký và cách các interceptor bọc call. Hãy xác định ai tạo ID, ai xác minh credentials, ai chọn tenant và ai ghi log; không để nhiều interceptor cùng ghi đè một key mà không có quy ước.

## 10. Lỗi và bảo mật khi nhận metadata

| Tình huống | Phản hồi hoặc xử lý gợi ý | Lý do |
| --- | --- | --- |
| Thiếu metadata bắt buộc | `INVALID_ARGUMENT` hoặc giá trị mặc định theo hợp đồng | Request không đáp ứng yêu cầu ứng dụng |
| Key có nhiều value ngoài chính sách | `INVALID_ARGUMENT` | Tránh cách diễn giải mơ hồ |
| Credentials thiếu hoặc không hợp lệ | `UNAUTHENTICATED` | Không xác minh được caller |
| Caller đã xác thực nhưng không đủ quyền | `PERMISSION_DENIED` | Không được phép thực hiện thao tác |
| Dịch vụ xác minh phụ thuộc bị lỗi | `UNAVAILABLE` hoặc status hạ tầng thích hợp | Không coi lỗi hạ tầng là credentials hợp lệ |
| Deadline hết | `DEADLINE_EXCEEDED` | Dùng deadline API của gRPC |

Các mã trên được trả qua `io.grpc.Status`; không tự ghi `grpc-status` như một custom key. Mô tả lỗi không nên chứa token, thông tin tenant bí mật hoặc toàn bộ header nhận được.

**Ranh giới tin cậy:** client có thể tự gửi `x-tenant-id`, `x-user-id`, `x-role` hoặc `x-client-version`. Chỉ một số giá trị là thông tin mô tả; chúng không phải danh tính đã xác thực. Server phải xác minh credentials và kiểm tra quyền trước khi dùng dữ liệu để truy cập tài nguyên.

**TLS và proxy:** TLS bảo vệ metadata trên kết nối được mã hóa. Nếu proxy kết thúc TLS rồi mở kết nối khác tới server, cần đánh giá bảo vệ chặng tiếp theo và chính sách tin cậy proxy. Không log toàn bộ `Metadata`, đặc biệt là `authorization`, cookie, baggage hoặc dữ liệu cá nhân.

**Giới hạn kích thước:** request metadata đi qua HTTP/2 headers và chịu giới hạn từ gRPC client/server, proxy hoặc load balancer. Chỉ gửi value nhỏ, không gửi JSON lớn, file hoặc danh sách quyền trong headers. Giới hạn thực tế phụ thuộc cấu hình của các thành phần triển khai.

## 11. Kiểm thử đường đi client sang server

Unit test `Metadata.put/get` chỉ xác minh API lưu trữ cục bộ. Để chứng minh client interceptor được gọi và server interceptor thực sự nhận metadata, cần một **integration test có gRPC channel và server**.

`InProcessServerBuilder` và `InProcessChannelBuilder` của `grpc-java` hữu ích cho test không cần mở cổng mạng. Chúng phù hợp để kiểm tra đường đi interceptor và context; TLS, proxy, HTTP/2 network behavior và giới hạn header vẫn cần môi trường kết nối thực.

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Metadata ASCII | Client gửi `x-request-id: req-42` | Server đọc đúng `req-42` |
| Metadata tùy chọn bị thiếu | Bỏ `x-client-version` | Server dùng mặc định hoặc xử lý theo hợp đồng |
| Metadata bắt buộc bị thiếu | Bỏ request ID nếu chính sách yêu cầu | Server trả status đã định nghĩa |
| Key lặp | Gửi hai value cùng `x-request-id` | Server phát hiện qua `getAll` và xử lý nhất quán |
| Binary metadata | Gửi `x-client-capabilities-bin` với `byte[]` | Server nhận lại đúng các byte |
| Hai RPC đồng thời | Mỗi call có request ID khác | Không trộn context giữa hai call |
| Downstream RPC | Server nhận ID đã kiểm tra rồi gọi service khác | Client downstream chỉ gửi key được chọn lọc |
| Streaming | Nhiều message trong một stream | Metadata thuộc call, context ổn định theo stream |
| Authentication | Gửi token sai/hết hạn | `UNAUTHENTICATED`, không chạy service |
| TLS/proxy | Chạy qua đường mạng triển khai | Metadata tới đúng server và secret không lộ |

### Ví dụ integration test tối giản

Giả sử `.proto` đã sinh `GreeterGrpc`, `HelloRequest` và `HelloReply`. Service test trả request ID đã được server interceptor đưa vào context:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class ClientToServerMetadataTest {

    static class TestGreeter extends GreeterGrpc.GreeterImplBase {
        @Override
        public void sayHello(
                HelloRequest request,
                StreamObserver<HelloReply> observer) {
            String id =
                RequestMetadataServerInterceptor.REQUEST_ID.get();
            observer.onNext(
                HelloReply.newBuilder().setMessage(id).build());
            observer.onCompleted();
        }
    }

    @Test
    void clientMetadataReachesServerContext() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                new TestGreeter(),
                new RequestMetadataServerInterceptor()))
            .build()
            .start();

        ManagedChannel channel =
            InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();
        try {
            GreeterGrpc.GreeterBlockingStub stub =
                GreeterGrpc.newBlockingStub(channel)
                    .withInterceptors(
                        new RequestMetadataClientInterceptor("2.4.0"))
                    .withOption(
                        RequestMetadataClientInterceptor.REQUEST_ID_OPTION,
                        "req-42");

            HelloReply reply = stub.sayHello(
                HelloRequest.newBuilder().setName("Mai").build());
            assertEquals("req-42", reply.getMessage());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
```

Ví dụ cần dependency `grpc-inprocess`, JUnit 5 và các lớp được sinh từ `.proto`; tên package/method tùy dự án. `directExecutor()` giúp test nhỏ gọn nhưng không mô phỏng đầy đủ scheduling và concurrency trong production. Nên bổ sung test cho key lặp, metadata thiếu và status lỗi.

Nếu cần xác minh response trailers, tạo client listener quan sát `onClose(status, trailers)` và kiểm tra key được server thêm. Nếu cần xác minh TLS hoặc proxy, dùng môi trường tích hợp có cùng kiểu transport và cấu hình tương đương triển khai.

## 12. Bài tập vận dụng

Một hệ thống Spring gRPC có `CheckoutService.PlaceOrder`. Client cần gửi request ID, phiên bản ứng dụng và một mảng byte nhỏ mô tả capability. Server phải đọc các value trước khi service thực thi và ghi lại request ID trong log.

**Yêu cầu:**

1. Khai báo `x-request-id`, `x-client-version` là ASCII key và `x-client-capabilities-bin` là binary key.
2. Viết client interceptor để gắn metadata trong `ClientCall.start(...)`; request ID phải được tạo hoặc lấy theo từng call.
3. Viết server interceptor để phát hiện metadata thiếu, sai định dạng và key lặp; trả status rõ ràng.
4. Chuyển request ID và client version đã kiểm tra vào `io.grpc.Context`; service đọc context mà không tự parse headers.
5. Nếu CheckoutService gọi InventoryService, chỉ truyền tiếp các metadata được phép sau khi xác minh; không sao chép mù quáng toàn bộ inbound headers.
6. Viết integration test chứng minh metadata từ client tới server context và một test xác minh trường hợp bị từ chối.

**Câu hỏi tự kiểm tra:**

- Client interceptor thêm metadata ở callback nào?
- Server interceptor nhận request metadata trước hay sau khi service xử lý message đầu tiên?
- Vì sao `Metadata` không phải một `Map<String, String>` thông thường?
- Khi nào dùng `getAll(...)` thay vì `get(...)`?
- Vì sao metadata inbound không tự động có mặt ở RPC downstream?
- Với streaming RPC, metadata được gửi một lần hay một lần cho mỗi message?
- Vì sao không được dùng `x-user-id` do client gửi làm bằng chứng danh tính?
- Integration test cần kiểm tra điều gì mà unit test `Metadata.put/get` không chứng minh được?

**Ghi nhớ:** Request metadata đi từ client sang server khi một RPC bắt đầu. Client interceptor chuẩn bị headers; gRPC vận chuyển chúng; server interceptor nhận `Metadata`, kiểm tra và chuyển dữ liệu đã chấp nhận vào context cho service. Trong Spring gRPC, hãy đăng ký interceptor đúng phạm vi, chỉ truyền tiếp metadata được phép, kiểm tra cả key lặp và dữ liệu không tin cậy, rồi xác minh toàn bộ đường đi bằng integration test.
