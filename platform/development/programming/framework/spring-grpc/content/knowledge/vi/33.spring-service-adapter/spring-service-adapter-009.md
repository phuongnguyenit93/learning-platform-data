# Context và metadata trong adapter

Trong **SPRING_GRPC**, gRPC service adapter nhận request protobuf, đọc thông tin đi kèm lời gọi, chuyển dữ liệu thành command ứng dụng và gọi use case. Hai cơ chế quan trọng ở ranh giới này là **gRPC Metadata** và **gRPC Context**. Metadata mang thông tin qua wire cùng RPC; Context giữ dữ liệu theo phạm vi lời gọi trong process đang xử lý.

Adapter thường dùng interceptor để đọc Metadata, xác thực hoặc chuẩn hóa thông tin, rồi đưa giá trị đã được kiểm chứng vào Context. Service implementation và callback có thể đọc Context để lấy request ID, tenant, principal, deadline hoặc trạng thái cancellation mà không phải truyền tham số transport qua mọi method.

## 1. Metadata và Context khác nhau thế nào?

**Metadata** là tập key-value được gửi cùng RPC dưới dạng HTTP/2 headers hoặc trailers. Client dùng metadata để gửi authorization token, trace context, request ID hoặc tenant hint. Server đọc metadata trong interceptor trước khi dispatch tới service.

**Context** là cơ chế propagation nội bộ của gRPC Java. Context giữ các giá trị có phạm vi theo lời gọi, đồng thời hỗ trợ deadline và cancellation. Context không được serialize và gửi qua mạng; nó được truyền trong quá trình xử lý RPC trong một process.

| Đặc điểm | Metadata | Context |
| --- | --- | --- |
| Phạm vi | Đi qua wire cùng RPC | Nội bộ process đang xử lý |
| Nơi thường đọc | Client/server interceptor, call listener | Service method, callback, interceptor |
| Dữ liệu | Key-value với marshaller | Typed key-value và cancellation/deadline |
| Mục đích | Truyền header/trailer | Propagate request-scoped state |
| Tự động liên kết | Không tự xuất hiện trong Context | Không tự gửi sang peer khác |

Một metadata key như `x-request-id` có thể được interceptor đọc và đưa vào `io.grpc.Context`. Việc đó là thao tác bridge do ứng dụng thực hiện; gRPC không tự chuyển mọi metadata thành Context value.

## 2. Quy ước metadata key và kiểu dữ liệu

Metadata key phải dùng chữ thường ASCII. Key tùy chỉnh thường dùng dấu gạch nối, ví dụ `x-request-id` hoặc `x-tenant-id`. Key chứa dữ liệu nhị phân phải kết thúc bằng `-bin` và dùng binary marshaller.

Khai báo key một lần dưới dạng hằng số:

```java
import io.grpc.Metadata;

public final class GrpcMetadataKeys {
    private GrpcMetadataKeys() {}

    public static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of("x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> TENANT_HINT =
            Metadata.Key.of("x-tenant-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<byte[]> BINARY_CONTEXT =
            Metadata.Key.of("x-context-bin",
                    Metadata.BINARY_BYTE_MARSHALLER);
}
```

Dùng marshaller phù hợp với kiểu dữ liệu. Không tự mã hóa byte array thành chuỗi tùy ý rồi đặt vào ASCII key nếu protocol đã hỗ trợ binary metadata.

Metadata không phải nơi truyền payload nghiệp vụ lớn. Giữ header nhỏ, tránh gửi object JSON hoặc danh sách quyền dài qua metadata. Payload nghiệp vụ thuộc protobuf request; metadata dành cho thông tin điều khiển và ngữ cảnh.

## 3. Đưa Metadata vào Context bằng ServerInterceptor

Interceptor chạy trước service method và có thể tạo Context mới chứa dữ liệu đã đọc từ metadata. Dùng `Contexts.interceptCall` để Context có hiệu lực trong quá trình dispatch và callback của server call.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;

public final class RequestContextInterceptor
        implements ServerInterceptor {

    public static final Context.Key<String> REQUEST_ID =
            Context.key("request-id");
    public static final Context.Key<String> TENANT_HINT =
            Context.key("tenant-hint");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(GrpcMetadataKeys.REQUEST_ID);
        String tenantHint = headers.get(GrpcMetadataKeys.TENANT_HINT);

        Context context = Context.current();
        if (requestId != null) {
            context = context.withValue(REQUEST_ID, requestId);
        }
        if (tenantHint != null) {
            context = context.withValue(TENANT_HINT, tenantHint);
        }

        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Ví dụ này đưa request ID và tenant hint vào Context. Tenant hint từ client vẫn là dữ liệu không đáng tin cậy. Authentication hoặc application service phải kiểm tra tenant đó thuộc phạm vi principal đã xác thực trước khi dùng nó để truy cập dữ liệu. Không biến header do client tự gửi thành danh tính đã được xác minh.

Nếu metadata bắt buộc bị thiếu hoặc sai định dạng, interceptor có thể đóng call bằng status phù hợp trước khi dispatch. Request ID thường chỉ phục vụ quan sát nên server có thể tạo ID fallback; tenant hoặc credential bắt buộc cần được kiểm tra theo contract bảo mật.

## 4. Đọc Context trong service implementation

Sau khi interceptor cài Context, service method có thể đọc các key đã định nghĩa:

```java
@Override
public void getStock(
        StockRequest request,
        StreamObserver<StockReply> observer) {

    String requestId =
            RequestContextInterceptor.REQUEST_ID.get();

    String tenantHint =
            RequestContextInterceptor.TENANT_HINT.get();

    GetStockQuery query = new GetStockQuery(
            verifiedTenantFor(tenantHint), request.getSku());

    StockView result = applicationService.getStock(query);
    observer.onNext(replyMapper.toProto(result));
    observer.onCompleted();
}
```

Đây là ví dụ minh họa việc đọc Context tại adapter. Trong kiến trúc nhiều tầng, nên chuyển các giá trị cần thiết thành một kiểu application context thuần Java, ví dụ `RequestMetadata` hoặc `ExecutionContext`, rồi truyền rõ ràng vào use case. Không để application/domain import `io.grpc.Context` chỉ để đọc tenant hoặc request ID.

Một service method không nên lưu Context vào field của singleton Spring bean. Context thuộc một RPC cụ thể; lưu nó vào field có thể khiến hai request đồng thời nhìn thấy dữ liệu của nhau.

## 5. Tenant hint không phải tenant đã xác thực

Header `x-tenant-id` chỉ là giá trị client đề xuất. Nếu server dùng nó để chọn database schema, tenant partition hoặc quyền truy cập, phải xác minh caller có quyền với tenant đó.

Một luồng an toàn:

1. Authentication interceptor xác minh token hoặc client certificate.
2. Server lấy principal và claims từ kết quả xác thực đáng tin cậy.
3. Adapter kiểm tra tenant hint có nằm trong tập tenant mà principal được phép truy cập không.
4. Chỉ tenant đã xác minh mới được đặt vào Context hoặc chuyển thành application request context.
5. Application service vẫn kiểm tra authorization nghiệp vụ cần thiết.

Không tin các header như `x-user-id`, `x-role` hoặc `x-is-admin` nếu chúng chỉ do client gửi. Danh tính và quyền phải đến từ cơ chế authentication/authorization đã xác minh.

Thứ tự và cách kết hợp interceptor authentication với interceptor context phải nhất quán. Nếu context interceptor chạy trước khi authentication hoàn tất, nó chỉ nên giữ dữ liệu thô; principal/tenant đã xác thực phải được đưa vào Context sau bước xác minh.

## 6. Gửi Metadata từ gRPC client

Client có thể gắn metadata cố định cho một channel bằng interceptor. Ví dụ, tên workload hoặc client version:

```java
Metadata headers = new Metadata();
Metadata.Key<String> clientName = Metadata.Key.of(
        "x-client-name", Metadata.ASCII_STRING_MARSHALLER);
headers.put(clientName, "order-worker");

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("inventory.internal:9090")
        .useTransportSecurity()
        .intercept(MetadataUtils.newAttachHeadersInterceptor(headers))
        .build();
```

Interceptor trên gắn cùng bộ headers vào các call qua channel. Không dùng cách này cho request ID cần thay đổi theo từng RPC, vì request ID sẽ bị cố định theo metadata object đã attach.

Với giá trị động theo từng call, dùng client interceptor tự tạo metadata trong `start` hoặc dùng `CallCredentials` cho credential xác thực. Ví dụ interceptor request ID:

```java
public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    private final Supplier<String> requestIdSupplier;

    public RequestIdClientInterceptor(
            Supplier<String> requestIdSupplier) {
        this.requestIdSupplier = requestIdSupplier;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {
                headers.put(
                        GrpcMetadataKeys.REQUEST_ID,
                        requestIdSupplier.get());
                super.start(listener, headers);
            }
        };
    }
}
```

Ví dụ cần các import gRPC Java tương ứng và một `Supplier` tạo ID mới cho từng call. Không ghi đè request ID đã được tracing framework tạo sẵn; hãy thống nhất nguồn phát sinh và quy tắc propagation trong ứng dụng.

## 7. Propagate metadata khi gọi downstream service

Một service trung gian đôi khi nhận RPC rồi gọi một gRPC service khác. Không sao chép toàn bộ inbound metadata sang downstream một cách mù quáng.

Chỉ propagate các key có ý nghĩa và được phép chia sẻ:
- Trace context theo chuẩn OpenTelemetry/W3C.
- Correlation/request ID nội bộ.
- Tenant đã được xác minh và được downstream contract chấp nhận.
- Credential phù hợp với danh tính mà service trung gian dùng khi gọi downstream.

Không forward raw authorization token của caller nếu kiến trúc yêu cầu service trung gian dùng service identity riêng hoặc token exchange. Không forward metadata nội bộ, hop-by-hop hoặc key không rõ nguồn gốc. Với nhiều downstream service, mỗi đích có thể có audience và credential khác nhau.

Tracing nên dùng OpenTelemetry instrumentation và propagator tương ứng để inject/extract trace context. Không tự chế header thay thế `traceparent` nếu hệ thống đã chuẩn hóa W3C Trace Context.

## 8. Context chứa deadline và cancellation

gRPC Context không chỉ giữ dữ liệu do ứng dụng thêm. Context hiện tại của RPC còn có thể mang deadline và trạng thái cancellation.

Đọc deadline:

```java
Context context = Context.current();
Deadline deadline = context.getDeadline();

if (deadline != null && deadline.isExpired()) {
    throw new IllegalStateException("RPC deadline expired");
}
```

Kiểm tra cancellation trước khi tiếp tục công việc tốn tài nguyên:

```java
if (Context.current().isCancelled()) {
    return;
}
```

Có thể đăng ký listener để dừng tác vụ khi client hủy RPC hoặc deadline hết:

```java
Context context = Context.current();
context.addListener(
        cancelledContext -> cancellationToken.cancel(),
        Runnable::run);
```

`cancellationToken` ở đây là abstraction của ứng dụng để báo cho công việc đang chạy dừng lại. Listener không tự rollback database hoặc hoàn tác side effect đã commit. Use case phải kiểm tra cancellation tại các điểm an toàn và giải phóng tài nguyên phù hợp.

Không dùng deadline như một giá trị metadata do client tự khai báo. Deadline gRPC là một phần của call options/protocol propagation và được phản ánh trong Context ở server.

## 9. Propagate Context sang executor bất đồng bộ

Context hiện tại có thể được truy cập trong callback do gRPC quản lý. Nhưng khi ứng dụng tự chuyển công việc sang executor, không nên giả định mọi executor đều tự mang Context sang thread khác.

Chụp Context tại thời điểm nhận call và wrap tác vụ:

```java
Context grpcContext = Context.current();

executor.execute(grpcContext.wrap(() -> {
    String requestId =
            RequestContextInterceptor.REQUEST_ID.get();
    worker.process(requestId);
}));
```

Có thể dùng `Context.currentContextExecutor(executor)` nếu muốn executor tự wrap các task được submit trong Context hiện tại. Chọn cách phù hợp với lifecycle và bảo đảm task không chạy sau khi request đã bị hủy mà vẫn tiếp tục tạo side effect.

Context propagation không đồng nghĩa propagation của mọi thread-local khác. MDC logging, Spring SecurityContext và transaction context có cơ chế riêng. Nếu cần mang chúng qua executor, cấu hình cơ chế tương ứng; không giả định `io.grpc.Context` tự động sao chép tất cả.

## 10. Context và transaction không phải một cơ chế

Context giúp truyền request-scoped data và cancellation/deadline; Spring transaction quản lý transaction resource. Chúng có lifecycle và propagation rules khác nhau.

- `Context.current()` không mở transaction database.
- `@Transactional` không tự đưa gRPC metadata vào application service.
- Context cancellation không tự rollback một transaction đã commit.
- JDBC/JPA transaction thường gắn với thread; Context có thể được wrap sang executor nhưng transaction không vì thế tự chuyển theo.
- Khi gọi application method trên worker thread, hãy mở transaction qua Spring proxy ở chính thread đó nếu operation cần transaction.

Nếu use case cần request ID hoặc tenant, truyền application context rõ ràng. Nếu use case cần transaction, đặt transaction boundary ở application service. Không dùng Context như service locator để truy cập repository, Spring bean hoặc mọi dependency của request.

## 11. Bảo vệ dữ liệu và giới hạn metadata

Metadata có thể được ghi vào log, proxy hoặc tracing system. Vì vậy:

- Không gửi password, private key, refresh token hoặc secret trong metadata.
- Không log raw Authorization header hoặc access token.
- Không tin tenant/user/role header chưa xác minh.
- Giữ metadata nhỏ; header quá lớn có thể bị transport/proxy từ chối.
- Dùng binary key kết thúc bằng `-bin` cho dữ liệu nhị phân.
- Chọn allowlist các key được forward tới downstream.
- Dùng request ID để truy vết, không dùng nó làm credential hoặc bằng chứng authorization.
- Tránh đặt dữ liệu cá nhân nhạy cảm vào correlation ID hoặc baggage.

Nếu cần truyền thông tin xác thực, dùng TLS và cơ chế credential phù hợp như gRPC CallCredentials hoặc security integration của Spring gRPC. Metadata chỉ là phương tiện mang credential, không tự xác minh credential.

## 12. Kiểm thử Metadata và Context

Một bộ test adapter nên kiểm tra cả đường truyền metadata và context isolation:

1. Gửi `x-request-id` từ client; xác nhận service đọc được cùng giá trị qua Context key.
2. Không gửi request ID; xác nhận server tạo fallback hoặc xử lý theo contract.
3. Gửi tenant hint không được phép; xác nhận request bị từ chối trước khi truy cập dữ liệu tenant.
4. Gửi hai RPC đồng thời với request ID khác nhau; xác nhận không rò Context giữa các call.
5. Hủy RPC hoặc để deadline hết; xác nhận listener/cancellation signal được kích hoạt.
6. Chuyển công việc sang executor; xác nhận Context được wrap và request ID còn đúng.
7. Gọi downstream; xác nhận chỉ metadata được allowlist mới được propagate.
8. Xác nhận log không chứa raw token hoặc secret.

Ví dụ kiểm thử Context bridge có thể dùng in-process server/channel để gửi metadata và assert giá trị mà service nhận được. In-process transport phù hợp cho logic interceptor/context; nó không thay thế integration test cần xác minh TLS, HTTP/2 hoặc proxy propagation.

## 13. Lỗi thường gặp

| Triệu chứng/cách làm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Service không đọc được metadata | Chưa gửi header hoặc key/marshaller không khớp | Dùng key hằng số chung và kiểm tra interceptor |
| `Context.Key.get()` trả `null` | Interceptor chưa gắn value hoặc metadata vắng mặt | Kiểm tra thứ tự đăng ký và chính sách fallback |
| Request ID của nhiều call giống nhau | Gắn metadata cố định cho toàn channel | Tạo metadata theo từng call |
| Tenant header bị giả mạo | Tin dữ liệu client gửi như danh tính | Xác minh với principal/claims trước khi dùng |
| Context mất trong executor | Task chạy trên thread không được wrap | Dùng `Context.wrap` hoặc context-aware executor |
| Context bị rò giữa request | Lưu request state vào field singleton hoặc tự attach/detach sai | Dùng `Contexts.interceptCall` và Context key theo RPC |
| Downstream nhận token không phù hợp | Forward toàn bộ inbound metadata | Allowlist key và dùng credential theo audience/identity |
| Client timeout nhưng server vẫn chạy | Công việc không kiểm tra cancellation | Propagate cancellation signal tới operation |
| Log lộ token | Ghi toàn bộ metadata | Redact Authorization và secret keys |

## 14. Bài tập thực hành

1. Tạo `Metadata.Key` cho request ID và tenant hint bằng ASCII marshaller.
2. Viết `ServerInterceptor` đưa request ID vào `Context.Key`.
3. Đọc request ID trong generated service implementation và truyền thành application request context thuần Java.
4. Thêm authentication interceptor; chỉ đặt principal/tenant đã xác minh vào Context sau bước xác thực.
5. Viết client interceptor tạo request ID riêng cho từng RPC.
6. Wrap một tác vụ executor bằng `Context.current().wrap(...)` và kiểm tra request ID được giữ đúng.
7. Đăng ký cancellation listener và dừng công việc khi RPC bị hủy.
8. Viết test hai RPC đồng thời để chứng minh Context không rò giữa request.
9. Viết downstream client chỉ propagate trace context và tenant đã được xác minh.
10. Kiểm tra log/tracing để bảo đảm token, secret và dữ liệu nhạy cảm không bị ghi lại.

### Ghi nhớ

**Metadata là dữ liệu đi cùng RPC trên wire; Context là trạng thái theo phạm vi lời gọi trong process.** Interceptor đọc Metadata và đưa những giá trị đã được xác minh vào Context để service/callback sử dụng. Hãy giữ Context ở adapter, truyền application context thuần Java vào use case, propagate rõ ràng qua executor và chỉ forward metadata được allowlist. Deadline/cancellation, authentication, transaction và tracing có cơ chế riêng; kết hợp chúng có chủ đích thay vì coi tất cả là một loại context.

## Tài liệu tham khảo

- [gRPC — Metadata](https://grpc.io/docs/guides/metadata/)
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html)
- [gRPC Java — ServerInterceptor](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerInterceptor.html)
- [gRPC Java — MetadataUtils](https://grpc.github.io/grpc-java/javadoc/io/grpc/stub/MetadataUtils.html)
- [gRPC — Deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC — Cancellation](https://grpc.io/docs/guides/cancellation/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
