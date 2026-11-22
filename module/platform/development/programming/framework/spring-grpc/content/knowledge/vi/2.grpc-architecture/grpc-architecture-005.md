# Metadata và headers trong cuộc gọi

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **metadata** trong gRPC là gì và phân biệt **request headers**, **response headers**, **trailers** với **protobuf request/response message**.
- Mô tả các HTTP/2 pseudo-header, header gRPC do runtime quản lý và metadata tùy biến đi qua một lời gọi unary hoặc streaming.
- Khai báo, đọc và ghi metadata bằng **io.grpc.Metadata** trong Java; phân biệt **ASCII metadata** với **binary metadata** có hậu tố **-bin**.
- Gắn metadata trên client bằng **ClientInterceptor**, đọc metadata trên server bằng **ServerInterceptor** và truyền request ID qua **io.grpc.Context**.
- Hiểu mối quan hệ giữa **authorization**, **deadline**, **grpc-status**, **TLS** và các giới hạn kích thước headers.
- Thiết kế kiểm thử tích hợp kiểm tra metadata được truyền đúng, xử lý lỗi rõ ràng và tránh rò rỉ thông tin nhạy cảm.

## 1. Metadata là gì trong kiến trúc Spring gRPC?

Trong module **SPRING_GRPC**, client và server trao đổi dữ liệu nghiệp vụ bằng **Protocol Buffers** và gọi nhau qua unary hoặc streaming RPC. Bên cạnh message protobuf, mỗi lời gọi còn cần thông tin ngữ cảnh như mã truy vết, token xác thực, ngôn ngữ, deadline hoặc các chi tiết hỗ trợ chẩn đoán. gRPC gọi nhóm thông tin bổ sung này là **metadata**.

Metadata là tập các cặp **key–value** đi cùng một RPC, thường được ánh xạ vào **HTTP/2 headers** và **trailers**. Nó không phải một trường tự động xuất hiện trong **.proto**. Hai client gọi cùng một RPC method có thể truyền metadata khác nhau mà không làm thay đổi kiểu **GetOrderRequest** hoặc **GetOrderResponse**.

Giả sử dịch vụ Spring gọi:

~~~proto
syntax = "proto3";

package shop.orders.v1;

option java_package = "com.example.orders.v1";
option java_multiple_files = true;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string state = 2;
}
~~~

Trong một lời gọi cụ thể, client có thể gửi:

- **Request message**: **order_id = "A-102"**.
- **Metadata**: **x-request-id = "req-7f2a"**, **authorization = "Bearer …"**.
- **Deadline/call options**: thời hạn tối đa cho RPC, được runtime có thể truyền qua **grpc-timeout**.

Server trả **GetOrderResponse** hoặc gRPC status lỗi. Nó cũng có thể trả metadata ở **initial response headers** và **trailers**, ví dụ phiên bản dịch vụ hoặc thông tin chẩn đoán an toàn.

**Phân biệt quan trọng:** message protobuf chứa dữ liệu nghiệp vụ theo schema; metadata chứa ngữ cảnh của lời gọi; gRPC status xác định lời gọi thành công hay thất bại. Không dùng metadata như một kho lưu trữ payload lớn hoặc thay thế hợp đồng message.

## 2. Metadata xuất hiện ở đâu trong một RPC?

Một unary RPC trên HTTP/2 thường có dạng:

~~~mermaid
sequenceDiagram
    participant C as Spring client + stub
    participant H as gRPC Channel/HTTP2
    participant S as gRPC server
    C->>H: Request metadata + GetOrderRequest
    H->>S: HEADERS (path, content-type, x-request-id)
    H->>S: DATA (protobuf request)
    Note over H,S: Client kết thúc chiều gửi
    S-->>H: HEADERS (response metadata)
    S-->>H: DATA (GetOrderResponse)
    S-->>H: HEADERS trailers (grpc-status, metadata)
    H-->>C: Message + final status
~~~

Bảng vòng đời:

| Giai đoạn | Loại thông tin | Ai thường sử dụng? |
| --- | --- | --- |
| **Request headers** | Đường dẫn RPC, content type, timeout, custom metadata, xác thực | Runtime server, server interceptor, handler qua context |
| **Request DATA** | Một hoặc nhiều request message đã được mã hóa | Deserializer và implementation |
| **Response headers** (*initial metadata*) | Metadata phía server trả trước payload | Client interceptor/callback cấp thấp |
| **Response DATA** | Một hoặc nhiều response message | Client stub/observer |
| **Response trailers** (*trailing metadata*) | **grpc-status**, đôi khi **grpc-message**, custom metadata cuối lời gọi | Runtime client, interceptor, xử lý lỗi |

Cả response headers và trailers đều được truyền bằng HTTP/2 **HEADERS frame**, nhưng chúng có **thời điểm** và **vai trò** khác nhau. Trailers đến cuối RPC. Nếu lời gọi thất bại rất sớm, server có thể trả **trailers-only**, tức response chỉ có một block HEADERS cuối kèm status mà không có response DATA hoặc initial headers riêng.

Với **streaming**, client/server có thể trao đổi nhiều message ở phần DATA, nhưng metadata ban đầu vẫn thuộc **lúc mở RPC**, và trailers vẫn thuộc **lúc kết thúc RPC**. Không có cơ chế metadata headers mới cho từng message ở giữa stream theo cách dùng gRPC thông thường. Muốn gửi thông tin thay đổi theo từng message, hãy khai báo field trong protobuf message.

## 3. Phân biệt ba nhóm header

Không phải mọi header xuất hiện trên HTTP/2 đều là custom metadata do ứng dụng có thể tùy ý tạo.

### 3.1. HTTP/2 pseudo-headers

Ví dụ một request gRPC đi tới service **OrderService**:

~~~text
:method: POST
:scheme: https
:path: /shop.orders.v1.OrderService/GetOrder
:authority: orders.internal.example:443
~~~

Các trường bắt đầu bằng dấu **:** là **HTTP/2 pseudo-headers**, dùng để mô tả request/authority. Runtime gRPC và transport quản lý chúng. Không tự thêm các tên này bằng **Metadata.Key** để đổi service được gọi.

**:path** thể hiện protobuf package, service và method. Nó **không** lấy từ **java_package**; còn host/cổng là phần cấu hình Channel/transport. Khi triển khai sau proxy, cần bảo đảm proxy giữ đúng đường dẫn RPC và hỗ trợ HTTP/2.

### 3.2. Headers được gRPC định nghĩa

Một số header/protocol metadata phổ biến:

| Header hoặc metadata | Ý nghĩa | Nguồn quản lý thường gặp |
| --- | --- | --- |
| **content-type: application/grpc** | Xác định nội dung là gRPC | Runtime |
| **te: trailers** | Cho biết có hỗ trợ HTTP trailers | Runtime/transport |
| **grpc-timeout** | Thời gian còn lại của deadline theo đơn vị quy định trong giao thức | Runtime từ deadline/call options |
| **grpc-encoding** | Thuật toán nén message được sử dụng | Runtime, tùy cấu hình nén |
| **grpc-accept-encoding** | Các dạng nén mà phía nhận hỗ trợ | Runtime |
| **user-agent** | Thông tin client/runtime nếu được gửi | Runtime |
| **grpc-status** | Mã kết thúc RPC, thường ở response trailers | Runtime và server status |
| **grpc-message** | Mô tả lỗi, nếu được cung cấp | Runtime/server |

Các header **grpc-*** thuộc không gian được gRPC dành riêng. Ứng dụng không nên tự đặt custom metadata bắt đầu bằng **grpc-**, và không nên tự viết **grpc-status** thay vì sử dụng API **Status**.

**Deadline** được cấu hình ở mức lời gọi, chẳng hạn **stub.withDeadlineAfter(...)**. gRPC có thể biểu diễn thời gian còn lại qua **grpc-timeout**; ứng dụng không cần tự tính và nhét **grpc-timeout** vào một Metadata map.

### 3.3. Custom application metadata

Những trường như sau có thể do ứng dụng thống nhất:

~~~text
x-request-id: req-7f2a
x-tenant-id: tenant-a
x-client-version: 2026.11
authorization: Bearer <redacted>
~~~

Đây là ví dụ về quy ước tên và giá trị. **x-** không bắt buộc trong gRPC; tên custom metadata chỉ cần thỏa quy tắc của transport/thư viện và tránh trùng trường reserved. **authorization** là trường quen thuộc được truyền qua metadata nhưng nên sử dụng cơ chế **CallCredentials**/xác thực phù hợp cho hệ thống thật.

Đừng tin giá trị **x-tenant-id** do client tự gửi nếu server dùng nó để cấp quyền. Server phải xác thực danh tính và kiểm tra tenant mà caller được phép truy cập. Metadata chỉ là một kênh truyền dữ liệu, không tự cung cấp tính xác thực.

## 4. Quy tắc tên, kiểu và giá trị metadata

Trong gRPC, key metadata là tên ASCII, thường dùng **chữ thường**, chữ số và các ký tự hợp lệ như **-**, **_**, **.**. HTTP/2 yêu cầu tên header chữ thường; grpc-java chuẩn hóa/quản lý theo quy tắc của thư viện. Nên đặt tên đơn giản, dễ hiểu và nhất quán.

Có hai nhóm giá trị metadata:

| Nhóm | Quy ước tên | Dữ liệu ứng dụng | API grpc-java |
| --- | --- | --- | --- |
| **ASCII metadata** | Tên bình thường, ví dụ **x-request-id** | Chuỗi ASCII phù hợp với giao thức | **Metadata.ASCII_STRING_MARSHALLER** |
| **Binary metadata** | Tên bắt buộc có hậu tố **-bin**, ví dụ **x-trace-bin** | Mảng byte | **Metadata.BINARY_BYTE_MARSHALLER** |

Ví dụ khai báo key Java:

~~~java
import io.grpc.Metadata;

public final class RpcMetadataKeys {
    private RpcMetadataKeys() {}

    public static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> CLIENT_VERSION =
            Metadata.Key.of(
                    "x-client-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<byte[]> TRACE_BYTES =
            Metadata.Key.of(
                    "x-trace-bin",
                    Metadata.BINARY_BYTE_MARSHALLER);
}
~~~

Với binary metadata, transport gRPC trên HTTP/2 sử dụng biểu diễn **base64** khi cần đưa bytes vào giá trị header. Trong Java, bạn thao tác trực tiếp với **byte[]**; không nên tự mã hóa base64 rồi truyền vào **BINARY_BYTE_MARSHALLER**, vì như vậy có thể dẫn tới mã hóa hai lần hoặc client/server hiểu sai dữ liệu.

**ASCII_STRING_MARSHALLER** dành cho ASCII phù hợp với metadata, không phải cơ chế truyền tùy ý chuỗi Unicode. Nếu cần truyền tiếng Việt hoặc cấu trúc nhị phân, hãy ưu tiên một protobuf field trong message; hoặc dùng binary metadata khi thực sự là ngữ cảnh RPC.

### 4.1. Sử dụng Metadata trong Java

~~~java
Metadata metadata = new Metadata();

metadata.put(RpcMetadataKeys.REQUEST_ID, "req-7f2a");
metadata.put(RpcMetadataKeys.CLIENT_VERSION, "2026.11");
metadata.put(
        RpcMetadataKeys.TRACE_BYTES,
        new byte[] {0x01, 0x02, 0x03});

String requestId = metadata.get(RpcMetadataKeys.REQUEST_ID);
byte[] trace = metadata.get(RpcMetadataKeys.TRACE_BYTES);
~~~

**Metadata** là container dữ liệu mutable được gRPC sử dụng cho từng trao đổi headers/trailers. Đừng dùng một đối tượng mutable dùng chung rồi thay đổi đồng thời từ nhiều RPC khi không có đồng bộ hóa. Các key có thể lặp trong protocol và API có khả năng đọc nhiều giá trị; nếu nghiệp vụ cần đúng một request ID, hãy xác định quy tắc khi nhận nhiều giá trị, thay vì mặc định an toàn chỉ vì **get()** trả một giá trị.

Với dữ liệu bảo mật, tránh in **Metadata.toString()** hay toàn bộ header ra log. Token, cookie, thông tin khách hàng và correlation ID có thể vô tình xuất hiện trong bản ghi log/traces.

## 5. Gắn request metadata từ client Spring

Client thường muốn tạo **request ID mới cho mỗi RPC**. Có thể dùng **ClientInterceptor** để chặn lúc lời gọi được khởi tạo và bổ sung headers một cách tập trung.

### 5.1. ClientInterceptor gửi request ID

~~~java
package com.example.orders.client;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall
                <ReqT, RespT>(delegate) {

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {

                headers.put(REQUEST_ID, UUID.randomUUID().toString());
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

Ở thời điểm **start(...)**, interceptor nhận container headers của RPC và ghi thêm **x-request-id**. UUID mới được tạo **cho mỗi lần gọi**, phù hợp với tracing của các RPC độc lập. Trong hệ thống phân tán, đôi khi bạn cần **truyền tiếp** correlation ID có sẵn thay vì tạo mới ở mỗi hop; cách lấy ID từ request context phải được thiết kế phù hợp.

Có thể tạo stub sử dụng interceptor trong cấu hình Spring:

~~~java
package com.example.orders.client;

import com.example.orders.v1.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        // Chỉ dùng plaintext trong ví dụ local.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {

        return OrderServiceGrpc.newBlockingStub(
                ClientInterceptors.intercept(
                        orderChannel,
                        new RequestIdClientInterceptor()));
    }
}
~~~

**ClientInterceptors.intercept(...)** tạo Channel wrapper cho stub, chèn logic khi gửi lời gọi; nó không có nghĩa tạo một TCP connection mới. **ManagedChannel** vẫn được dùng chung và cần shutdown khi Spring context đóng.

Với dự án dùng auto-configuration của **Spring gRPC**, cách đăng ký interceptor/stub bean có thể được framework cung cấp sẵn; cần theo API của phiên bản đang dùng để tránh cấu hình hai lần. Ví dụ trên minh họa lớp grpc-java cơ bản bên dưới Spring.

### 5.2. Khi nào sử dụng MetadataUtils?

grpc-java cung cấp các helper như **MetadataUtils.newAttachHeadersInterceptor(metadata)** để gắn một bộ metadata đã có. Helper này thuận tiện trong test hoặc khi giá trị tương đối cố định.

Với token luân chuyển, request ID hoặc dữ liệu thay đổi trên mỗi RPC, cần cơ chế cập nhật **theo từng call**. Tránh giữ một đối tượng **Metadata** mutable dùng chung rồi thay giá trị giữa các thread: nó có thể làm gửi nhầm token hoặc request ID. Một **ClientInterceptor** tạo giá trị trong **start()**, hoặc **CallCredentials** cho xác thực, thường rõ ràng hơn.

## 6. Xác thực và CallCredentials

Thông tin xác thực như bearer token thường truyền bằng metadata, nhưng việc phát hành, làm mới và gắn token cần cơ chế rõ ràng. **CallCredentials** là abstraction grpc-java dành cho thông tin xác thực **theo lời gọi**. Nó phù hợp hơn việc hard-code token trong cấu hình Channel hoặc trong request message protobuf.

Ví dụ tối giản lấy token từ **Supplier** và thêm **authorization**:

~~~java
package com.example.orders.client;

import io.grpc.CallCredentials;
import io.grpc.Metadata;
import io.grpc.Status;
import java.util.concurrent.Executor;
import java.util.function.Supplier;

public final class BearerTokenCredentials extends CallCredentials {

    private static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final Supplier<String> tokenSupplier;

    public BearerTokenCredentials(Supplier<String> tokenSupplier) {
        this.tokenSupplier = tokenSupplier;
    }

    @Override
    public void applyRequestMetadata(
            RequestInfo requestInfo,
            Executor appExecutor,
            MetadataApplier applier) {

        appExecutor.execute(() -> {
            try {
                String token = tokenSupplier.get();

                if (token == null || token.isBlank()) {
                    applier.fail(
                            Status.UNAUTHENTICATED
                                    .withDescription(
                                            "Không có token cho RPC"));
                    return;
                }

                Metadata headers = new Metadata();
                headers.put(AUTHORIZATION, "Bearer " + token);
                applier.apply(headers);
            } catch (Exception ex) {
                applier.fail(
                        Status.UNAUTHENTICATED
                                .withDescription(
                                        "Không thể lấy token cho RPC")
                                .withCause(ex));
            }
        });
    }
}
~~~

Gắn credentials vào stub cho một lời gọi:

~~~java
GetOrderResponse response = stub
        .withCallCredentials(
                new BearerTokenCredentials(tokenSupplier))
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("A-102")
                        .build());
~~~

Trong ví dụ này, **stub** là **OrderServiceGrpc.OrderServiceBlockingStub** và **tokenSupplier** là **Supplier<String>** được ứng dụng cung cấp; cần import thêm **java.util.concurrent.TimeUnit** cùng lớp request/response đã sinh.

Các điểm phải giữ đúng:

- **TLS/mTLS** bảo vệ transport; token trên đường truyền không được xem là an toàn nếu gửi qua plaintext tới môi trường không tin cậy.
- **CallCredentials** thêm thông tin xác thực nhưng **server vẫn phải xác minh token, danh tính, phạm vi quyền và thời hạn**.
- Token không nên xuất hiện trong log, exception description, metric label hoặc tracing span attributes.
- Credential provider cần xử lý token hết hạn, lỗi lấy token và cancellation có kiểm soát; ví dụ trên chỉ minh họa cách gắn headers.

**Không tự đặt header authorization trong mỗi business method** nếu tổ chức đã có cơ chế thống nhất về credentials. Việc xác thực nên được triển khai nhất quán, có kiểm thử và có chính sách rotation.

## 7. Đọc request metadata bằng ServerInterceptor

Phía server, API **ServerInterceptor** có phương thức **interceptCall(...)** nhận **Metadata headers** của RPC. Interceptor thích hợp để ghi nhận request ID, xác thực caller, kiểm soát giới hạn hoặc truyền context đến handler.

### 7.1. Đọc request ID và truyền qua gRPC Context

~~~java
package com.example.orders.server;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class RequestIdServerInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> REQUEST_ID_CONTEXT =
            Context.key("request-id");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID);

        if (requestId == null || requestId.isBlank()) {
            call.close(
                    Status.INVALID_ARGUMENT.withDescription(
                            "Thiếu x-request-id"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context = Context.current()
                .withValue(REQUEST_ID_CONTEXT, requestId);

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Ở ví dụ này, server yêu cầu request ID để minh họa validation. **Trong thiết kế thực tế, hệ thống có thể tự sinh request ID ở ingress khi client không cung cấp**; lựa chọn chấp nhận/từ chối là chính sách ứng dụng, không phải quy định của gRPC.

**Context** của grpc-java mang dữ liệu theo ngữ cảnh thực thi RPC. Nó giúp handler đọc request ID mà không phải thêm **request_id** vào mọi protobuf message:

~~~java
String requestId =
        RequestIdServerInterceptor.REQUEST_ID_CONTEXT.get();
~~~

Giá trị có thể được truy cập trong callback thuộc gRPC Context tương ứng. Khi tự chuyển việc sang executor/thread khác, cần **truyền hoặc gắn lại Context** phù hợp; không giả định một **ThreadLocal** tùy ý sẽ tự theo request qua mọi thread.

Server cần phân biệt **correlation ID** với thông tin đã xác thực. Header **x-request-id** do caller gửi không chứng minh danh tính; có thể phải chuẩn hóa độ dài/ký tự và sinh lại nếu không đáng tin cậy.

### 7.2. Đăng ký interceptor với gRPC server Spring

Ví dụ dùng grpc-java ServerBuilder do Spring quản lý:

~~~java
package com.example.orders.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcServerConfig {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server orderServer(OrderEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(
                        ServerInterceptors.intercept(
                                endpoint,
                                new RequestIdServerInterceptor()))
                .build();
    }
}
~~~

**OrderEndpoint** ở đây là một implementation của lớp cơ sở **OrderServiceGrpc.OrderServiceImplBase**; có thể được quản lý bằng **@Component**. Cơ chế **ServerInterceptors.intercept(...)** gắn interceptor với service đã đăng ký.

Một Spring gRPC starter có thể cung cấp đăng ký service/interceptor tự động; không nên đồng thời khởi tạo server thủ công trên cùng cổng. Nếu thêm nhiều interceptor, cần kiểm tra thứ tự áp dụng để xác thực, logging và xử lý lỗi được thực hiện đúng ý định.

### 7.3. Khi nào nên đưa metadata vào handler?

Các lựa chọn thường gặp:

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Theo dõi **x-request-id** qua tầng nghiệp vụ | Server interceptor đọc và đặt vào **Context** hoặc request-scoped abstraction |
| Xác thực token | Security interceptor / authentication component, sau đó truyền principal đã xác thực |
| Dữ liệu nghiệp vụ phải được lưu hoặc trả về | Đưa vào protobuf message |
| Giới hạn thời gian | Dùng deadline/cancellation của gRPC Context |
| Ghi metrics latency/status | Interceptor hoặc instrumentation của framework |

Tránh để business service phụ thuộc trực tiếp vào mọi tên header; nên tạo abstraction rõ ràng cho ngữ cảnh đã xác thực và những gì service thực sự cần.

## 8. Gửi response headers và trailers từ server

Server có thể phản hồi metadata **trước message** hoặc **khi kết thúc RPC**. Với grpc-java, thao tác với hai luồng này thường được thực hiện bằng **ServerCall** trong interceptor.

### 8.1. ServerInterceptor ghi headers và trailers

Ví dụ thêm tên phiên bản vào initial headers và mã node vào trailers:

~~~java
package com.example.orders.server;

import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ResponseMetadataServerInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> SERVER_NODE =
            Metadata.Key.of(
                    "x-server-node",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata requestHeaders,
            ServerCallHandler<ReqT, RespT> next) {

        ServerCall<ReqT, RespT> decorated =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<ReqT, RespT>(call) {

                    @Override
                    public void sendHeaders(Metadata responseHeaders) {
                        responseHeaders.put(
                                SERVICE_VERSION,
                                "orders-v1");
                        super.sendHeaders(responseHeaders);
                    }

                    @Override
                    public void close(Status status, Metadata trailers) {
                        trailers.put(
                                SERVER_NODE,
                                "node-a");
                        super.close(status, trailers);
                    }
                };

        return next.startCall(decorated, requestHeaders);
    }
}
~~~

**sendHeaders(...)** diễn ra khi runtime chuẩn bị gửi initial metadata. **close(...)** là lúc status/trailers được phát ra. Metadata tùy biến **x-service-version** và **x-server-node** chỉ để minh họa: không nên công bố chi tiết node, topology hoặc version nhạy cảm ra bên ngoài nếu chính sách vận hành không cho phép.

Interceptor có thể được gắn tương tự ví dụ ở mục 7. Trên lỗi xảy ra **trước khi handler gửi headers**, một số đường đi trả **trailers-only**, nên client không được giả định initial response headers luôn tồn tại riêng.

### 8.2. gRPC status thuộc kết thúc RPC

Server báo lỗi bằng API **Status**, chẳng hạn:

~~~java
responseObserver.onError(
        Status.NOT_FOUND
                .withDescription("Không tìm thấy đơn hàng")
                .asRuntimeException());
~~~

Runtime sẽ đóng RPC với status tương ứng. **grpc-status** thuộc protocol và thường được gửi ở trailers; ứng dụng không cần tự nhét **"grpc-status": "5"** vào custom Metadata. Khi thành công, gọi **onNext(...)** rồi **onCompleted()** cho unary; khi thất bại, gọi **onError(...)**, và tuyệt đối không gửi tiếp sau terminal event.

Thông tin lỗi chi tiết mang tính nghiệp vụ có thể dùng **google.rpc.Status** / error details nếu client/server hỗ trợ. Cách này khác với raw custom header và khác với trường **grpc-message**, vốn không nên chứa stack trace hay token.

## 9. Client đọc initial headers và trailers

Client stub thường trả về **protobuf response** hoặc ném **StatusRuntimeException**. Để quan sát response headers và trailers trên cả lời gọi thành công lẫn thất bại, có thể dùng **ClientInterceptor** với listener callback.

Ví dụ dưới đây đọc hai custom metadata key:

~~~java
package com.example.orders.client;

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

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> SERVER_NODE =
            Metadata.Key.of(
                    "x-server-node",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions options,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall
                <ReqT, RespT>(next.newCall(method, options)) {

            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata outgoingHeaders) {

                Listener<RespT> decorated =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<RespT>(
                                        listener) {

                            @Override
                            public void onHeaders(Metadata headers) {
                                String version =
                                        headers.get(SERVICE_VERSION);
                                // Gửi value tới hệ thống metric/log an toàn.
                                super.onHeaders(headers);
                            }

                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                String node =
                                        trailers.get(SERVER_NODE);
                                // Xử lý status, node nếu chính sách cho phép.
                                super.onClose(status, trailers);
                            }
                        };

                super.start(decorated, outgoingHeaders);
            }
        };
    }
}
~~~

Đoạn trên minh họa **vị trí** đọc metadata trong callback; các biến **version**/**node** chưa được sử dụng để tránh đưa quyết định về logging/metrics vào mã mẫu. Trong ứng dụng thật, chuyển dữ liệu cần thiết vào tracing/metric hoặc một collector phù hợp với scope mỗi RPC.

Nếu chỉ cần **trailers khi có lỗi** ở blocking stub, có thể dùng:

~~~java
try {
    stub.getOrder(request);
} catch (io.grpc.StatusRuntimeException ex) {
    io.grpc.Metadata trailers = ex.getTrailers();
    // trailers có thể null; kiểm tra trước khi đọc.
    if (trailers != null) {
        String node = trailers.get(SERVER_NODE);
    }
}
~~~

Ở đây **SERVER_NODE** là key kiểu **Metadata.Key<String>** đã được định nghĩa. **StatusRuntimeException.getTrailers()** không bảo đảm luôn có dữ liệu (ví dụ lỗi xuất hiện trước khi nhận response). Muốn lấy headers/trailers của RPC thành công, nên dùng interceptor/cơ chế capture phù hợp thay vì chỉ dựa vào exception.

Không dùng **client-visible headers** để quyết định bảo mật như tự công nhận tenant/quyền truy cập. Quyết định phân quyền phải được thực thi bằng cơ chế đáng tin cậy ở server.

## 10. Deadline, cancellation, streaming và metadata

### 10.1. Deadline không phải custom header do ứng dụng tự kiểm soát

Client có thể đặt:

~~~java
GetOrderResponse response = stub
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("A-102")
                        .build());
~~~

**TimeUnit** thuộc **java.util.concurrent.TimeUnit**. Trong gRPC, deadline được quản lý ở tầng call options/context; **grpc-timeout** biểu diễn thời lượng còn lại dưới dạng header protocol khi cần. Server nhận thời gian xử lý còn lại và có thể quan sát cancellation khi deadline hết hạn.

Nếu client nhận **DEADLINE_EXCEEDED**, không nên coi request chắc chắn chưa xử lý. Server có thể đã thực hiện thao tác ghi trước khi response đến client; cần idempotency/reconciliation cho những RPC có side effect.

### 10.2. Headers có vòng đời khác streaming messages

Trong một server-streaming RPC, server có thể gửi hàng nghìn response message, nhưng không thể liên tục thay đổi initial metadata sau khi headers đã được gửi. Thông tin cần cập nhật cho từng message phải nằm trong message protobuf.

Ví dụ:

~~~proto
message OrderEvent {
  string order_id = 1;
  string event_id = 2;
  int64 sequence = 3;
  string state = 4;
}
~~~

**event_id** và **sequence** là dữ liệu riêng của từng event. Nếu đưa chúng vào initial metadata, client chỉ thấy giá trị mở đầu RPC và không nhận các thay đổi giữa stream.

Client-streaming/bidirectional streaming có thêm khái niệm **half-close**: **onCompleted()** trên request observer đánh dấu đã hết dữ liệu phía gửi; trailers/status cuối cùng vẫn chỉ có khi RPC kết thúc. Không dùng request half-close để suy rằng response/trailers đã sẵn sàng.

### 10.3. Hủy lời gọi và lỗi connection

Hủy một RPC có thể làm stream của lời gọi kết thúc mà không đóng Channel dùng chung. Mất connection có thể ảnh hưởng nhiều RPC đang truyền; khi đó status và trailers có thể không nhận đủ. Vì vậy, client nên chuẩn bị cho tình huống **không có server response metadata**, kể cả khi đã gửi request headers.

## 11. Bảo mật và giới hạn vận hành

Metadata giúp truyền ngữ cảnh nhưng cũng là nơi dễ phát sinh vấn đề bảo mật, độ tin cậy và hiệu năng.

### 11.1. Tránh lộ dữ liệu nhạy cảm

- **Không log nguyên request/response metadata** nếu có authorization, cookie, session ID hoặc dữ liệu cá nhân.
- Dùng **TLS** cho đường truyền giữa client và server, hoặc mTLS khi kiến trúc yêu cầu xác thực hai chiều. Interceptor chỉ thêm metadata, **không mã hóa** kết nối.
- **Xác minh identity và authorization trên server**. Một metadata key như **x-user-role: admin** từ caller không thể tự trở thành quyền truy cập.
- Chỉ truyền các header thật sự cần thiết, không gửi token đến backend hoặc proxy không liên quan.
- Khi trả lỗi, mô tả phải an toàn; không để lộ access token, stack trace, đường dẫn nội bộ hay chi tiết hạ tầng.

Token phải được quản lý theo vòng đời riêng. Nếu dùng gateway/proxy, kiểm tra nơi TLS kết thúc, cách gateway chuyển tiếp metadata và ranh giới tin cậy giữa gateway với backend.

### 11.2. Giới hạn kích thước và số lượng headers

Headers và trailers phải được mã hóa trong **HTTP/2 header block**. Peer và thư viện có thể áp giới hạn kích thước metadata; giá trị giới hạn phụ thuộc cấu hình server, client và proxy. Metadata vượt giới hạn có thể dẫn đến thất bại lời gọi, đôi khi được ánh xạ sang **RESOURCE_EXHAUSTED** hoặc lỗi transport tùy tình huống.

Do đó:

- Không đưa danh sách lớn, JSON dài, chứng từ hay tài liệu nhị phân vào metadata. Hãy sử dụng protobuf message hoặc nơi lưu dữ liệu chuyên dụng.
- Với custom header, giới hạn độ dài/định dạng, số lượng và tính hợp lệ tại điểm vào.
- Binary metadata vẫn góp vào header budget, kể cả overhead mã hóa trong transport.
- Đặt giới hạn message riêng cho payload protobuf; **header limit** và **message size limit** là hai cơ chế khác nhau.

### 11.3. Cẩn thận về chuẩn hóa và duplicate keys

HTTP/2 header names là chữ thường; gRPC custom metadata keys cũng nên dùng chữ thường thống nhất. Các key như **X-Request-Id** và **x-request-id** có thể được thư viện chuẩn hóa, nhưng tránh phụ thuộc vào cách chuyển đổi này khi thiết kế.

Một key có thể xuất hiện nhiều lần. Nếu ứng dụng cần **một giá trị duy nhất**, hãy xác định chính sách xử lý duplicate thay vì ngầm dùng giá trị đầu tiên/cuối cùng. Với authorization, quyết định cách tiếp nhận và kiểm soát header nhiều giá trị cần gắn với security policy.

## 12. Kiểm thử metadata end-to-end

Kiểm thử handler trực tiếp bằng Java không bao phủ việc gắn metadata qua interceptor. Dùng **grpc-inprocess** để kiểm tra request headers, routing và status qua runtime gRPC mà không mở cổng mạng.

Ví dụ JUnit 5 dưới đây tạo một service unary tối giản, gắn server interceptor kiểm tra request ID và gọi qua client interceptor:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.orders.v1.GetOrderRequest;
import com.example.orders.v1.GetOrderResponse;
import com.example.orders.v1.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class MetadataIntegrationTest {

    @Test
    void interceptorPassesRequestIdToServerContext() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        OrderServiceGrpc.OrderServiceImplBase handler =
                new OrderServiceGrpc.OrderServiceImplBase() {
                    @Override
                    public void getOrder(
                            GetOrderRequest request,
                            StreamObserver<GetOrderResponse> observer) {

                        String id =
                                RequestIdServerInterceptor
                                        .REQUEST_ID_CONTEXT.get();

                        // Dùng context để xác nhận interceptor đã chạy.
                        if (id == null || id.isBlank()) {
                            observer.onError(
                                    Status.INTERNAL
                                            .withDescription(
                                                    "Missing request context")
                                            .asRuntimeException());
                            return;
                        }

                        observer.onNext(
                                GetOrderResponse.newBuilder()
                                        .setOrderId(request.getOrderId())
                                        .setState("PENDING")
                                        .build());
                        observer.onCompleted();
                    }
                };

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(
                        ServerInterceptors.intercept(
                                handler,
                                new RequestIdServerInterceptor()))
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(
                        serverName)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(
                            ClientInterceptors.intercept(
                                    channel,
                                    new RequestIdClientInterceptor()));

            GetOrderResponse response = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("A-102")
                            .build());

            assertEquals("A-102", response.getOrderId());
            assertEquals("PENDING", response.getState());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Bài test giả định các lớp **RequestIdClientInterceptor** và **RequestIdServerInterceptor** ở mục 5 và 7 được khai báo trong package/import phù hợp. Cần thư viện **grpc-inprocess**, grpc-java và JUnit 5 tương thích với nhau. **directExecutor()** chỉ phù hợp test đơn giản và không mô phỏng đầy đủ concurrency/transport thật.

Các tình huống nên kiểm tra tiếp:

| Test | Kỳ vọng |
| --- | --- |
| Gọi server **không có x-request-id** theo policy ví dụ | **INVALID_ARGUMENT**; handler không xử lý |
| Gọi với request ID hợp lệ | Server đọc đúng giá trị qua **Context** |
| Server trả custom initial headers/trailers | Client interceptor quan sát được ở đúng callback |
| Server trả **NOT_FOUND** | Client nhận gRPC status chính xác; trailers có thể có hoặc không |
| Token bị thiếu/hết hạn | **UNAUTHENTICATED**, không lộ token trong message/log |
| Header quá lớn hoặc sai định dạng | Lời gọi bị từ chối theo giới hạn/cấu hình thực tế |
| Streaming kết thúc/hủy | Metadata ban đầu không đổi theo message; status/trailers cuối cùng được xử lý đúng khi có |
| Backend sau reverse proxy | Proxy chuyển tiếp chính xác metadata được cho phép và sử dụng HTTP/2/TLS |

Kiểm thử **in-process** giúp kiểm tra API metadata/interceptor. Nó **không chứng minh** TLS, ALPN, giới hạn header của proxy, gRPC-Web translation hay hành vi nhiều backend đã đúng. Đối với các mục đó, cần thêm kiểm thử với network transport và hạ tầng tương ứng.

## 13. Những lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Server đọc **headers.get(key) == null** | Client chưa gắn metadata, interceptor chưa đăng ký, tên key khác nhau | Kiểm tra interceptor wiring và tên/key marshaller hai phía |
| **UNAUTHENTICATED** dù request message đúng | Token thiếu/hết hạn/sai audience; credentials không được gọi | Xác minh CallCredentials, TLS và chính sách xác thực phía server |
| **PERMISSION_DENIED** sau khi xác thực thành công | Caller không có quyền trên tài nguyên | Kiểm tra authorization dựa trên principal đã xác thực |
| Request ID bị trùng giữa các RPC | Reuse metadata mutable hoặc tạo ID khi khởi động bean | Tạo/propagate ID theo từng call, kiểm soát scope |
| Client không thấy response headers | Server trả trailers-only, không có initial headers riêng | Cho phép headers vắng mặt và xử lý status/trailers |
| Client chỉ kiểm tra HTTP **200** và tưởng RPC thành công | Không đọc **grpc-status** | Xử lý StatusRuntimeException/callback onClose |
| Đọc binary header ra chuỗi sai | Dùng ASCII marshaller hoặc tự base64 sai | Thống nhất key **-bin** và BINARY_BYTE_MARSHALLER |
| Streaming muốn cập nhật header cho từng event | Metadata chỉ có giai đoạn ban đầu/cuối RPC | Đưa thông tin từng event vào protobuf message |
| Lời gọi fail khi gửi nhiều metadata | Quá giới hạn header của peer/proxy | Giảm metadata, giới hạn kích thước và đo header budget |
| Tracing bị mất context khi dùng executor tùy chỉnh | Không propagate grpc **Context** | Bọc/tái gắn Context hoặc dùng instrumentation tương ứng |
| Metadata chứa thông tin nhạy cảm trong logs | Log toàn bộ request headers | Redact/allowlist key, không log token |
| RPC chạy local nhưng fail qua proxy | Proxy bỏ header, sai HTTP/2/TLS, cấu hình auth | Kiểm tra policy chuyển tiếp metadata và đường truyền thực |

Khi điều tra, nên kiểm tra thứ tự: **client đã tạo metadata?** → **interceptor được gắn đúng stub?** → **transport/proxy có nhận được request?** → **server interceptor đọc được headers?** → **handler có Context đúng?** → **status/trailers được trả về?**. Phân tích theo tầng giúp khoanh vùng nguyên nhân trước khi chỉnh cấu hình.

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành: thêm metadata cho OrderService

1. Từ hợp đồng **OrderService/GetOrder** ở mục 1, tạo client và server chạy bằng Spring cùng thư viện grpc-java. Dùng một **ManagedChannel** cho nhiều lời gọi.
2. Thêm **RequestIdClientInterceptor** để tạo **x-request-id** theo từng RPC. Gắn **RequestIdServerInterceptor**, đọc giá trị vào **Context** và kiểm tra logic truy vết trong handler.
3. Cho server trả **x-service-version** trong initial headers và một custom trailer không nhạy cảm. Viết **ResponseMetadataClientInterceptor** để ghi nhận hai giá trị.
4. Thử request không có request ID và xác minh server từ chối theo policy ví dụ. Sau đó đổi policy thành tạo request ID tại ingress nếu thiếu, và mô tả lợi/hại của hai cách.
5. Thêm bearer token bằng **CallCredentials** hoặc cơ chế xác thực được framework hỗ trợ. Test token thiếu, hết hạn và principal không đủ quyền; không ghi token vào log.
6. Đặt deadline 2 giây cho **GetOrder**, mô phỏng server chậm, quan sát **DEADLINE_EXCEEDED**. Giải thích vì sao không nên tự đặt **grpc-timeout** bằng custom Metadata.
7. Chuyển method sang server-streaming ở một ví dụ riêng, phát nhiều event; thử truyền dữ liệu thay đổi giữa các message bằng protobuf fields, không sửa initial headers.
8. Chạy kiểm thử in-process, sau đó kiểm thử thật qua TLS/proxy để xác minh khả năng chuyển tiếp metadata và giới hạn headers.

### Câu hỏi tự kiểm tra

**1. Metadata khác protobuf message ở điểm nào?**  
Metadata đi trong headers/trailers để truyền ngữ cảnh của **RPC**; message protobuf là payload dữ liệu theo **schema** được khai báo trong .proto.

**2. gRPC request headers có thể chứa những thông tin nào?**  
HTTP/2 pseudo-headers, thông tin protocol như **content-type** và **grpc-timeout**, cùng custom metadata như **x-request-id** hoặc **authorization**.

**3. Có nên đặt custom header tên grpc-status không?**  
Không. **grpc-status** thuộc giao thức và được runtime xử lý tại kết thúc RPC. Server dùng API **Status** để báo lỗi.

**4. Vì sao key binary metadata cần hậu tố -bin?**  
Hậu tố giúp gRPC phân biệt binary metadata với ASCII metadata và áp dụng cách biểu diễn tương ứng qua transport. Trong Java, dùng **BINARY_BYTE_MARSHALLER** với **byte[]**.

**5. Một server-streaming RPC gửi 100 message có gửi 100 bộ initial headers không?**  
Không. Metadata ban đầu thuộc **một RPC**, và các message sử dụng DATA trên cùng stream. Thông tin thay đổi giữa message nằm trong payload message.

**6. Client có thể luôn đọc response headers khi RPC thất bại không?**  
Không. Một lỗi có thể dẫn đến **trailers-only** hoặc failure trước khi nhận bất cứ response metadata nào. Client phải xử lý trường hợp headers/trailers vắng mặt.

**7. Tại sao nên dùng CallCredentials cho token thay vì gửi chung trong mọi request message?**  
Token là ngữ cảnh xác thực của lời gọi, cần quản lý phát hành, hết hạn, bảo mật và gắn theo call. **CallCredentials** hỗ trợ cơ chế đó mà không cần sửa schema nghiệp vụ.

**8. Tại sao x-tenant-id không thể được tin tưởng ngay khi server đọc thấy header?**  
Vì caller có thể tự đặt giá trị metadata. Server phải xác thực caller và kiểm tra phạm vi quyền thực tế trước khi sử dụng tenant để quyết định truy cập.

## Tổng kết

Trong Spring gRPC, **metadata** giúp mang thông tin ngữ cảnh của một RPC qua **request headers**, **response headers** và **trailers**. Các trường HTTP/2/gRPC reserved thuộc runtime; custom metadata của ứng dụng được quản lý bằng **Metadata.Key**, các **interceptor** và **CallCredentials** khi phù hợp. Request/response **Protocol Buffers** vẫn giữ vai trò truyền dữ liệu nghiệp vụ, còn **grpc-status** xác định kết quả cuối cùng. Thiết kế metadata tốt đòi hỏi quản lý scope từng call, bảo mật token, giới hạn kích thước, phân biệt initial/trailing metadata và kiểm thử cả interceptor lẫn transport thực tế.

