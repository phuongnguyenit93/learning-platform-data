# Gắn correlation ID

Khi một yêu cầu đi qua gateway, Spring gRPC service và nhiều backend, log ở từng nơi thường nằm rời rạc. Một **correlation ID** giúp các thành phần ghi cùng một mã tham chiếu để nhóm log của một luồng xử lý. Trong gRPC, cách phổ biến là truyền mã này qua metadata, đưa nó vào gRPC `Context` ở server và tự động gắn lại vào các lời gọi downstream.

Correlation ID phục vụ khả năng truy vết trong log. Nó không phải thông tin xác thực, không chứng minh danh tính caller và cũng không thay thế distributed tracing. Bài này tập trung vào vòng đời một ID qua client, server, lời gọi tiếp theo, retry và streaming.

## 1. Correlation ID khác trace ID như thế nào?

Các hệ thống quan sát có thể dùng nhiều loại định danh:

| Định danh | Phạm vi | Mục đích |
| --- | --- | --- |
| **Correlation ID** | Một yêu cầu nghiệp vụ hoặc một luồng xử lý được quy ước | Tìm các log liên quan trên nhiều service |
| **Trace ID** | Một distributed trace | Gom các span thuộc cùng một trace |
| **Span ID** | Một operation/span trong trace | Xác định từng đoạn xử lý và quan hệ cha/con |
| **Request ID cục bộ** | Một lần nhận request tại một service | Chẩn đoán riêng tại một hop |

Một correlation ID có thể được giữ nguyên qua nhiều service. Trace ID cũng thường được truyền xuyên suốt, nhưng tracing SDK còn tạo span ID mới cho từng operation và quản lý parent/child relationship, sampling và timing. Nếu hệ thống đã dùng OpenTelemetry, hãy tiếp tục truyền W3C Trace Context qua cơ chế tracing; correlation ID có thể bổ sung để tra cứu log theo quy ước nghiệp vụ.

Không đặt token, email, số điện thoại hay dữ liệu cá nhân vào correlation ID. ID nên là chuỗi opaque, không mang ý nghĩa nghiệp vụ và không chứa bí mật.

## 2. Chọn metadata key và quy tắc định dạng

gRPC metadata là header/trailer đi kèm RPC. Dùng một key chữ thường, ví dụ `x-correlation-id`:

```java
import io.grpc.Metadata;

public final class CorrelationMetadata {
    private CorrelationMetadata() {
    }

    public static final Metadata.Key<String> CORRELATION_ID =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);
}
```

Với metadata key:

- Tên key phải viết thường.
- Giá trị chuỗi dùng ASCII marshaller; dữ liệu nhị phân cần key có hậu tố `-bin` và marshaller nhị phân.
- Metadata phù hợp cho ID ngắn và thông tin điều khiển, không phải payload nghiệp vụ.
- Đặt giới hạn độ dài và tập ký tự được chấp nhận để tránh log injection, header quá lớn hoặc dữ liệu bất thường.

Ví dụ dưới đây dùng UUID dạng chuỗi. Nếu hệ thống cần ID do gateway cấp, có thể dùng định dạng opaque khác, miễn là các service thống nhất quy tắc validate.

## 3. Tạo hoặc xác thực ID tại ranh giới server

Server interceptor là nơi phù hợp để đọc ID từ incoming metadata, kiểm tra định dạng và tạo ID nếu request không có. Sau đó, interceptor đưa ID vào gRPC `Context` để service method có thể lấy mà không cần thêm field vào mọi protobuf request.

```java
package com.myshop.grpc.observability;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIdServerInterceptor
        implements ServerInterceptor {

    public static final Context.Key<String> CORRELATION_ID_CONTEXT =
            Context.key("correlation-id");

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String correlationId =
                headers.get(CorrelationMetadata.CORRELATION_ID);

        if (correlationId == null) {
            correlationId = UUID.randomUUID().toString();
        } else if (!SAFE_ID.matcher(correlationId).matches()) {
            call.close(Status.INVALID_ARGUMENT
                    .withDescription("invalid x-correlation-id"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context context = Context.current()
                .withValue(CORRELATION_ID_CONTEXT, correlationId);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Quy tắc trong ví dụ:

- Nếu metadata vắng mặt, server tạo UUID mới cho RPC.
- Nếu caller gửi ID, server chỉ chấp nhận chuỗi theo allowlist và giới hạn độ dài.
- ID không hợp lệ bị từ chối trước khi service implementation chạy.
- `Contexts.interceptCall` bảo đảm context được gắn với callback của call được chuyển tiếp.

Chính sách với ID do caller gửi tùy ranh giới tin cậy. Với API nội bộ sau gateway tin cậy, có thể giữ ID gateway đã tạo sau khi validate. Với endpoint công khai, ID caller gửi vẫn là dữ liệu không tin cậy; có thể chọn ghi nó thành external correlation hint và tạo ID nội bộ riêng. Dù chọn cách nào, tuyệt đối không dùng correlation ID làm căn cứ xác thực hoặc phân quyền.

## 4. Đọc ID trong service và ghi log

Trong service implementation, đọc giá trị từ context:

```java
String correlationId =
        CorrelationIdServerInterceptor.CORRELATION_ID_CONTEXT.get();

log.info("catalog lookup started correlation_id={} product_id={}",
        correlationId, request.getProductId());
```

Đưa ID vào mọi log record thuộc cùng call giúp truy vấn các bước xử lý theo một khóa. Nếu dùng MDC của SLF4J, có thể đặt ID vào MDC trong phạm vi callback và phải xóa trong `finally` để tránh rò context giữa các request chạy trên cùng thread:

```java
String id = CorrelationIdServerInterceptor.CORRELATION_ID_CONTEXT.get();
try {
    MDC.put("correlation_id", id);
    handleRequest(request);
} finally {
    MDC.remove("correlation_id");
}
```

MDC là thread-local trong nhiều logging implementation. gRPC callback có thể chạy trên thread khác nhau; vì vậy không dựa vào MDC được thiết lập ở một thread để tự xuất hiện ở mọi callback. Dùng gRPC Context làm nguồn call-scoped, rồi thiết lập/khôi phục MDC tại từng ranh giới thực thi cần ghi log.

Không ghi correlation ID thành metric label nếu mỗi request có ID riêng. Điều đó tạo cardinality gần như không giới hạn. Dùng ID trong log/tracing attribute có kiểm soát; metrics nên nhóm theo method, status và các nhãn hữu hạn.

## 5. Tự động truyền ID sang downstream bằng client interceptor

Nếu service A gọi service B, client interceptor có thể đọc correlation ID từ gRPC Context hiện tại rồi thêm vào metadata outbound. Nhờ đó, code nghiệp vụ không phải tự sửa từng stub call.

```java
package com.myshop.grpc.observability;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class CorrelationIdClientInterceptor
        implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                String id = headers.get(CorrelationMetadata.CORRELATION_ID);
                if (id == null) {
                    id = CorrelationIdServerInterceptor
                            .CORRELATION_ID_CONTEXT.get();
                }
                if (id == null) {
                    id = UUID.randomUUID().toString();
                }
                headers.put(CorrelationMetadata.CORRELATION_ID, id);
                super.start(listener, headers);
            }
        };
    }
}
```

Thứ tự chọn ID:

1. Giữ ID outbound đã được caller chủ động đặt nếu có.
2. Nếu chưa có, dùng ID trong gRPC Context của incoming RPC.
3. Nếu đây là client call độc lập và không có context, tạo ID mới.

Ở hệ thống production, nên dùng chung hàm validate/normalize cho ID outbound và inbound, đồng thời tránh ghi đè giá trị đã được xác định bởi gateway tin cậy. Client interceptor chỉ truyền metadata; nó không tự tạo một distributed trace hay span.

## 6. Giữ Context khi chạy bất đồng bộ

gRPC Context có hiệu lực trong callback được gắn với call. Khi chuyển việc sang executor tùy chỉnh, context không nhất thiết tự đi theo thread mới. Nếu client interceptor dựa vào context để truyền correlation ID, mất context đồng nghĩa downstream call có thể tạo ID khác.

Chụp context hiện tại và bọc tác vụ:

```java
Context captured = Context.current();

executor.execute(captured.wrap(() -> {
    catalogStub.getProduct(request);
}));
```

Với executor dùng nhiều nơi, có thể bọc executor bằng tiện ích Context của gRPC hoặc truyền ID như một tham số call-scoped trong application layer. Tránh lưu correlation ID vào field mutable của singleton service: nhiều RPC đồng thời sẽ ghi đè giá trị của nhau.

Nếu công việc được đẩy vào queue và xử lý sau khi RPC kết thúc, hãy serialize correlation ID vào message envelope hoặc message headers của hệ thống queue theo một hợp đồng riêng. gRPC Context không tự tồn tại sau khi process nhận request đã kết thúc.

## 7. Retry, fan-out và streaming

**Retry:** các attempt của cùng một thao tác logic thường nên dùng cùng correlation ID để log có thể gom lại. Hãy tạo ID ở tầng ứng dụng trước khi bắt đầu retry hoặc giữ nó trong context xuyên suốt operation. Nếu interceptor tạo UUID mới cho từng call độc lập, các attempt có thể bị tách thành nhiều nhóm log.

Correlation ID chỉ dùng để liên kết quan sát; nó không thay thế idempotency key. Với thao tác ghi có retry, server vẫn cần cơ chế idempotency riêng để tránh thực hiện giao dịch hai lần.

**Fan-out:** khi một request gọi đồng thời nhiều backend, các lời gọi con thường kế thừa cùng correlation ID. Trace instrumentation có thể tạo span con riêng cho từng backend; không tạo correlation ID khác cho từng nhánh nếu muốn nhóm chúng dưới cùng yêu cầu gốc.

**Streaming:** một correlation ID thường gắn với toàn bộ RPC stream, không phải mỗi message. Các message trong cùng stream có thể thêm sequence number hoặc message-specific ID nếu cần phân tích riêng. Khi stream kéo dài lâu, log thêm event type và thời điểm, nhưng tránh lặp payload nhạy cảm.

## 8. Correlation ID và distributed tracing

Nếu ứng dụng dùng OpenTelemetry, tracing instrumentation thường tự truyền `traceparent` qua gRPC metadata. Trace ID liên kết spans; span ID xác định từng đoạn. Correlation ID là khóa bổ sung theo quy ước ứng dụng, có thể được gắn vào log record hoặc span attribute.

Không tự tạo `traceparent` bằng cách đặt correlation ID vào đó. W3C Trace Context có định dạng và semantics riêng; hãy để tracing SDK tạo span, quản lý sampling và propagate context. Có thể ghi cả `correlation_id` và `trace_id` trong log để hỗ trợ hai kiểu tra cứu.

Nếu gateway nhận correlation ID từ caller, hãy giới hạn độ dài và ký tự; nếu dùng làm nhãn hiển thị cho khách hàng, không đưa dữ liệu nội bộ hoặc ID tài nguyên nhạy cảm vào giá trị đó. Chính sách retention và quyền truy cập log vẫn áp dụng như với metadata quan sát khác.

## 9. Đăng ký interceptor và kiểm thử

Core gRPC Java cho phép gắn interceptor vào server/channel builder:

```java
Server server = ServerBuilder.forPort(9090)
        .intercept(new CorrelationIdServerInterceptor())
        .addService(new CatalogGrpcEndpoint(catalogService))
        .build();

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .intercept(new CorrelationIdClientInterceptor())
        .build();
```

Trong Spring gRPC, server và channel thường do framework auto-configure. Đăng ký interceptor qua extension point mà phiên bản Spring gRPC của dự án hỗ trợ; chỉ khai báo class thành bean không tự chứng minh nó đã được gắn vào server/channel. Xác minh bằng integration test thực hiện call qua cấu hình ứng dụng.

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Request không có metadata | Server tạo ID hợp lệ và handler đọc được trong Context |
| Request có ID hợp lệ | Server giữ ID theo chính sách trust boundary |
| Request có ID quá dài hoặc ký tự không cho phép | Server trả `INVALID_ARGUMENT` trước khi handler chạy |
| Server A gọi server B | Client interceptor truyền cùng ID sang B |
| Async task gọi downstream | ID vẫn giữ nguyên khi executor được bọc Context |
| Retry cùng operation | Các attempt có cùng correlation ID |
| Hai RPC đồng thời | ID không bị trộn giữa hai Context |
| Streaming RPC | Các message trong cùng stream dùng cùng ID |

Ngoài test interceptor riêng, nên có test tích hợp xác nhận log ở nhiều service có thể được truy vấn bằng cùng correlation ID mà không ghi raw authorization header hoặc payload.

## 10. Checklist triển khai

- [ ] Metadata key là `x-correlation-id` viết thường, giá trị ngắn và ASCII.
- [ ] ID được validate độ dài/tập ký tự tại ranh giới tin cậy.
- [ ] ID thiếu được tạo theo chính sách nhất quán.
- [ ] Correlation ID không được dùng làm credential, authorization claim hoặc idempotency key.
- [ ] Server lưu ID trong gRPC Context theo từng call.
- [ ] Client interceptor truyền ID hiện hành sang downstream.
- [ ] Context được truyền tường minh qua executor/thread tùy chỉnh.
- [ ] Retry của cùng operation giữ ID ổn định nếu cần gom log.
- [ ] Streaming giữ ID cho toàn bộ call; message ID riêng chỉ thêm khi có nhu cầu.
- [ ] ID nằm trong log có cấu trúc, không nằm trong metric label cardinality cao.
- [ ] Distributed tracing tiếp tục dùng W3C Trace Context/OpenTelemetry riêng.
- [ ] Test xác minh metadata, Context, async, retry, concurrency và registration trong Spring.

**Tự kiểm tra**

**Câu 1.** Correlation ID khác trace ID ở điểm nào?

*Đáp án:* Correlation ID là khóa quy ước để gom log của một yêu cầu/luồng xử lý. Trace ID thuộc distributed tracing và liên kết các span; span ID phân biệt từng operation trong trace.

**Câu 2.** Server có nên tin correlation ID do caller gửi như một danh tính đã xác thực không?

*Đáp án:* Không. Đó là metadata do caller cung cấp, phải validate và chỉ dùng cho correlation. Authentication/authorization cần credential và chính sách riêng.

**Câu 3.** Vì sao client interceptor đọc ID từ gRPC Context?

*Đáp án:* Nó cho phép các lời gọi downstream kế thừa ID của incoming RPC mà không cần thêm tham số vào từng stub call.

**Câu 4.** Khi chuyển xử lý sang executor riêng, điều gì có thể xảy ra nếu không truyền Context?

*Đáp án:* Context không tự đảm bảo xuất hiện trên thread mới; client interceptor có thể không thấy ID gốc và tạo ID khác. Cần bọc task/executor bằng Context hoặc truyền ID tường minh.

**Câu 5.** Có nên tạo correlation ID mới cho từng retry attempt không?

*Đáp án:* Thông thường không nếu các attempt thuộc cùng một operation cần được điều tra cùng nhau. Giữ một ID ổn định; dùng idempotency key riêng để bảo vệ thao tác ghi.

Gắn correlation ID hiệu quả khi ID được tạo hoặc xác thực tại ranh giới, lưu trong Context theo từng RPC và truyền tiếp qua client interceptor. Giữ ID ổn định qua fan-out/retry, không trộn nó với thông tin xác thực hay trace ID, và kiểm thử cả luồng bất đồng bộ để log của các service có thể liên kết đáng tin cậy.
