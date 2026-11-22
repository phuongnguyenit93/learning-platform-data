# withInterceptors và metadata

Generated stub của gRPC Java cho phép gắn **ClientInterceptor** bằng phương thức **withInterceptors(...)**. Interceptor quan sát hoặc điều chỉnh một RPC ở tầng call, còn **Metadata** mang các header phụ trợ như request ID, tenant, locale hoặc thông tin tracing. Kết hợp hai cơ chế này giúp client Spring gRPC áp dụng chính sách chung cho nhiều method mà không đưa dữ liệu điều khiển vào Protobuf message.

Trong Spring gRPC, có thể tạo stub nền từ channel do ứng dụng hoặc starter quản lý, gắn interceptor một lần rồi tạo stub dẫn xuất theo deadline hoặc CallCredentials cho từng RPC. Stub là immutable: mỗi thao tác cấu hình trả về stub mới. Interceptor nên stateless hoặc thread-safe vì cùng một instance có thể xử lý nhiều call đồng thời.

## 1. Metadata là gì và dùng khi nào?

Metadata là tập các key-value được truyền cùng RPC ở lớp giao thức. Nó thường dùng cho thông tin phụ trợ không thuộc dữ liệu nghiệp vụ của request:

- Request ID và trace/correlation ID.
- Tenant hoặc locale đã được xác thực.
- Thông tin định tuyến hoặc phiên bản client.
- Credential xác thực, nếu dùng cơ chế phù hợp như CallCredentials.
- Header và trailer phục vụ chẩn đoán hoặc điều khiển call.

Metadata không thay thế field trong Protobuf. Nếu một giá trị là dữ liệu nghiệp vụ mà service cần xử lý, lưu trữ hoặc validate theo schema, hãy đặt nó trong request message. Metadata phù hợp với ngữ cảnh giao tiếp, bảo mật và quan sát ở tầng RPC.

Metadata của gRPC được truyền dưới dạng HTTP/2 headers và trailers. Tên key phải viết thường. Key dạng text dùng ASCII marshaller; key nhị phân phải kết thúc bằng hậu tố **-bin** và dùng binary marshaller. Không tự tạo key bắt đầu bằng grpc- vì đây là namespace dành cho giao thức.

## 2. Khai báo Metadata.Key đúng kiểu

Ví dụ khai báo request ID dạng ASCII:

~~~java
private static final Metadata.Key<String> REQUEST_ID_HEADER =
    Metadata.Key.of(
        "x-request-id",
        Metadata.ASCII_STRING_MARSHALLER);
~~~

Một metadata nhị phân có thể khai báo như sau:

~~~java
private static final Metadata.Key<byte[]> SIGNATURE_HEADER =
    Metadata.Key.of(
        "x-payload-signature-bin",
        Metadata.BINARY_BYTE_MARSHALLER);
~~~

Không dùng ASCII marshaller cho byte array tùy ý. Ngược lại, không dùng binary marshaller cho giá trị text thông thường. Giữ key được khai báo tĩnh để client và server dùng cùng tên, kiểu và marshaller.

Metadata không phải nơi lưu payload lớn. Header có giới hạn kích thước ở client, proxy và server; gửi dữ liệu lớn trong metadata có thể làm RPC bị từ chối hoặc tăng chi phí parse ở mọi hop.

## 3. ClientInterceptor thêm metadata vào mỗi call

ClientInterceptor được gọi khi gRPC tạo client call. Để thêm header request, bọc ClientCall và bổ sung metadata trong phương thức start:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.Context;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    static final Context.Key<String> REQUEST_ID_CONTEXT =
        Context.key("request-id");

    static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        Context callContext = Context.current();
        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                String requestId =
                    callContext.get(REQUEST_ID_CONTEXT);

                if (requestId != null
                        && headers.get(REQUEST_ID_HEADER) == null) {
                    headers.put(REQUEST_ID_HEADER, requestId);
                }

                super.start(responseListener, headers);
            }
        };
    }
}
~~~

Interceptor capture Context khi call được tạo, rồi đọc request ID khi start. Nếu caller đã đặt header tương ứng, ví dụ giữ nguyên giá trị đó. Interceptor không lưu request ID vào field vì cùng instance có thể phục vụ nhiều request song song.

## 4. Gắn interceptor bằng withInterceptors

Generated stub có thể nhận interceptor và trả về một stub mới:

~~~java
PaymentServiceGrpc.PaymentServiceBlockingStub paymentStub =
    PaymentServiceGrpc.newBlockingStub(channel)
        .withInterceptors(new RequestIdClientInterceptor());
~~~

Sau đó gọi RPC trong context có request ID:

~~~java
String requestId = requestContext.requestId();
Context callContext = Context.current().withValue(
    RequestIdClientInterceptor.REQUEST_ID_CONTEXT,
    requestId);

PaymentResponse response;
Context previous = callContext.attach();
try {
    response = paymentStub
        .withDeadlineAfter(500, TimeUnit.MILLISECONDS)
        .getPayment(request);
} finally {
    callContext.detach(previous);
}
~~~

Context được attach trong phạm vi call và detach trong finally để không rò rỉ giá trị sang tác vụ khác trên cùng thread. Trong code bất đồng bộ, cần giữ context đúng cho thời điểm tạo call; nếu offload sang executor, dùng Context.wrap(...) hoặc fixedContextExecutor(...).

Nếu phiên bản gRPC Java đang dùng không cung cấp withInterceptors trên generated stub, có thể bọc channel trước khi tạo stub bằng ClientInterceptors.intercept(channel, interceptor). Chỉ chọn một vị trí gắn interceptor cho cùng mục đích để tránh thêm header hoặc thực thi logic hai lần.

## 5. Interceptor theo từng stub và interceptor theo channel

Có hai phạm vi thường dùng:

| Cách gắn | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| stub.withInterceptors(...) | Stub dẫn xuất và các call tạo từ stub đó | Một nhóm client hoặc một service cần policy riêng |
| ClientInterceptors.intercept(channel, ...) | Các stub được tạo từ channel đã bọc | Chính sách chung cho mọi service dùng channel đó |

Ví dụ bọc channel:

~~~java
Channel interceptedChannel = ClientInterceptors.intercept(
    channel,
    new RequestIdClientInterceptor(),
    new ClientMetricsInterceptor());

PaymentServiceGrpc.PaymentServiceBlockingStub paymentStub =
    PaymentServiceGrpc.newBlockingStub(interceptedChannel);
~~~

Không gắn cùng một interceptor ở cả channel và stub nếu không có chủ đích. Một request có thể đi qua logic lặp, tạo metadata trùng hoặc ghi metric hai lần. Thứ tự interceptor cũng ảnh hưởng thứ tự wrapping ClientCall; hãy kiểm tra thứ tự thực tế bằng test khi interceptor phụ thuộc nhau.

## 6. Truyền metadata từ server interceptor

ServerInterceptor có thể đọc metadata đầu vào trước khi service implementation chạy. Ví dụ lấy request ID và đưa vào gRPC Context để handler, logger hoặc tracing code truy cập:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;

public final class RequestIdServerInterceptor
        implements ServerInterceptor {

    private static final Context.Key<String> REQUEST_ID_CONTEXT =
        Context.key("request-id");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID_HEADER);
        if (requestId == null || requestId.isBlank()) {
            return next.startCall(call, headers);
        }

        Context context = Context.current().withValue(
            REQUEST_ID_CONTEXT, requestId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Đăng ký interceptor trên server builder hoặc qua cơ chế customizer của Spring gRPC starter đang sử dụng. Không giả định mọi starter dùng cùng annotation hoặc property. Nếu request ID bắt buộc, hãy validate và trả status phù hợp; nếu chỉ phục vụ tracing, có thể tạo ID mới khi thiếu theo policy hệ thống.

Metadata do client gửi là dữ liệu không tin cậy. Không dùng tenant ID hoặc user ID trong header làm căn cứ authorization nếu chưa xác minh chúng bằng credential và policy phía server.

## 7. Metadata cho authentication: khi nào dùng CallCredentials?

Có thể thêm authorization header bằng ClientInterceptor, nhưng với token động hoặc credential cần refresh, **CallCredentials** thường phù hợp hơn. CallCredentials có callback chuyên biệt để lấy metadata xác thực cho từng call và nhận thông tin security level.

Phân biệt:

- Dùng ClientInterceptor cho request ID, trace ID, locale hoặc metadata cross-cutting không bí mật.
- Dùng CallCredentials cho bearer token hoặc credential có vòng đời/refresh riêng.
- Dùng Protobuf request field cho dữ liệu nghiệp vụ.

Không hard-code access token trong interceptor singleton. Không log authorization metadata, cookie hoặc secret. Chỉ gửi bearer token qua TLS; server vẫn phải xác minh token và quyền truy cập.

## 8. Metadata response và trailers

Server có thể gửi metadata ban đầu và trailers khi call kết thúc. Initial metadata thường được gửi trước response body; trailers được gửi ở cuối để mang thông tin như request ID, mã chẩn đoán hoặc trạng thái phụ trợ.

Không nên dùng trailers để truyền dữ liệu nghiệp vụ quan trọng mà client cần xử lý như response chính. Trailers có thể không đến khi transport bị ngắt đột ngột. Dùng response message cho kết quả nghiệp vụ và gRPC status cho kết quả thành công/thất bại của call.

Tránh đưa stack trace, SQL, token hoặc dữ liệu cá nhân vào trailers. Metadata và trailers có thể được ghi log ở proxy hoặc observability agent; chỉ đưa thông tin cần thiết và đã được phép chia sẻ.

## 9. Giới hạn và bảo mật metadata

Các nguyên tắc an toàn:

1. Dùng tên key chữ thường, ASCII và có namespace riêng như x-request-id.
2. Key nhị phân kết thúc bằng -bin và dùng BINARY_BYTE_MARSHALLER.
3. Không đặt key tùy chỉnh trong namespace grpc- hoặc HTTP/2 pseudo-header.
4. Giữ metadata nhỏ; không truyền payload hoặc danh sách lớn trong header.
5. Xác thực mọi giá trị metadata đến từ client trước khi dùng cho authorization hoặc routing.
6. Không log token, secret, cookie hoặc dữ liệu nhạy cảm.
7. Tránh ghi cùng key nhiều lần nếu ứng dụng chỉ mong đợi một giá trị.
8. Cân nhắc giới hạn metadata ở proxy/server để chống request header quá lớn.

Metadata có thể bị proxy lọc hoặc biến đổi theo cấu hình. Nếu một header phải đi xuyên nhiều hop, cần xác minh allowlist/forwarding policy trên gateway và service mesh.

## 10. Kiểm thử interceptor và metadata

Nên kiểm thử các hành vi:

- Client interceptor thêm x-request-id khi Context có giá trị.
- Header caller đã đặt được giữ nguyên theo policy.
- Hai RPC đồng thời không dùng nhầm request ID của nhau.
- Server interceptor đọc header và đưa giá trị vào Context của handler.
- Metadata nhị phân dùng đúng key suffix -bin và marshaller.
- Stub nền không bị thay đổi sau withInterceptors.
- Interceptor chỉ được gắn một lần, tránh duplicate header hoặc metric.
- Authorization dùng CallCredentials và không bị ghi log.
- Proxy thực tế forward metadata cần thiết nhưng loại bỏ header không được phép.

Có thể dùng gRPC in-process server/channel để kiểm tra logic interceptor và Context. Với TLS, proxy hoặc metadata filtering, cần integration test qua transport và hạ tầng tương ứng; in-process test không xác minh được hành vi của gateway.

## 11. Ghi nhớ và tự kiểm tra

**withInterceptors(...) tạo stub mới có interceptor; Metadata mang header/trailer phụ trợ của RPC.** Dùng interceptor để gắn request ID hoặc tracing metadata, dùng Context để truyền dữ liệu theo call, dùng CallCredentials cho credential động và Protobuf cho dữ liệu nghiệp vụ. Metadata phải đúng kiểu marshaller, nhỏ, được xác thực và không chứa secret bị log.

Tự kiểm tra:

1. Vì sao interceptor phải thêm header trong ClientCall.start(...)?
2. withInterceptors(...) khác ClientInterceptors.intercept(channel, ...) ở phạm vi áp dụng thế nào?
3. Vì sao không nên lưu request ID theo field trong interceptor dùng chung?
4. Khi nào nên dùng CallCredentials thay vì thêm authorization bằng ClientInterceptor?
5. Vì sao metadata key nhị phân phải kết thúc bằng -bin?
6. Vì sao tenant ID trong metadata chưa đủ để xác thực tenant?

Kết hợp generated stub immutable, interceptor stateless và metadata có kiểm soát giúp client Spring gRPC áp dụng request context nhất quán, quan sát được call và giữ ranh giới rõ ràng giữa metadata, credential và dữ liệu nghiệp vụ.
