# Correlation ID và trace context

Một lời gọi gRPC có thể đi qua gateway, dịch vụ đặt hàng, kho hàng và thanh toán trước khi hoàn tất. Khi có lỗi hoặc thời gian xử lý tăng đột biến, log của từng dịch vụ thường nằm ở những hệ thống khác nhau. **Correlation ID** giúp nhận diện các log thuộc cùng một luồng xử lý; **trace context** giúp hệ thống distributed tracing kết nối những *span* thành một *trace* để thấy đường đi và thời gian thực thi.

Trong **Spring gRPC**, cả hai loại thông tin có thể được truyền qua **metadata** của gRPC, còn OpenTelemetry và hệ thống quan sát sử dụng chúng theo những mục đích khác nhau. Thiết kế đúng giúp theo dõi cả unary RPC, streaming RPC và các lời gọi downstream, đồng thời tránh nhầm correlation ID với bằng chứng xác thực hay một trace ID.

Sau bài học, bạn có thể:

- Phân biệt correlation ID, request ID, trace ID, span ID và W3C trace context.
- Hiểu `traceparent`, `tracestate` và `baggage` được truyền như thế nào trong gRPC metadata.
- Thiết kế quy tắc sinh, kiểm tra, kế thừa và ghi log correlation ID qua nhiều service.
- Viết client/server interceptor Java để chuyển correlation ID theo từng RPC.
- Tích hợp gRPC tracing với OpenTelemetry trong Spring, kể cả khi sử dụng executor hoặc streaming.
- Kiểm thử tính liên tục của correlation và quan hệ parent–child giữa các span; xử lý rủi ro về giả mạo, lộ dữ liệu và độ lớn metadata.

## 1. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Vòng đời điển hình | Ví dụ |
| --- | --- | --- | --- |
| **Correlation ID** | Mã ứng dụng dùng để liên kết log/sự kiện của một tác vụ hoặc chuỗi nghiệp vụ | Có thể xuyên qua nhiều RPC, queue và tiến trình bất đồng bộ | `corr-6d3a...` |
| **Request ID** | Mã nhận diện một HTTP/gRPC request cụ thể; đôi khi được dùng như correlation ID | Thường theo từng RPC/request | `req-0042` |
| **Trace ID** | Định danh của một distributed trace | Chung cho các span trong cùng trace | 32 ký tự hex cho 16 byte |
| **Span ID** | Định danh của một thao tác/span riêng | Mỗi span có ID riêng | 16 ký tự hex cho 8 byte |
| **Trace context** | Thông tin cần để dịch vụ nhận lời gọi tiếp nối đúng quan hệ tracing | Được inject/extract tại ranh giới RPC | `traceparent`, `tracestate` |
| **Baggage** | Những cặp key–value ứng dụng được chủ động truyền kèm context giữa các dịch vụ | Phụ thuộc propagator và phạm vi xử lý | `tenant-tier=standard` nếu chính sách cho phép |

**Correlation ID không bắt buộc bằng trace ID.** Một tác vụ kinh doanh có thể liên quan đến nhiều trace, ví dụ xử lý ngay yêu cầu rồi tiếp tục công việc ngày hôm sau trong queue. Ngược lại, một trace có nhiều span nhưng chỉ có một trace ID; từng span vẫn cần span ID riêng.

`x-correlation-id` và `x-request-id` là các **quy ước đặt tên metadata** được nhiều ứng dụng sử dụng, không phải header bắt buộc của gRPC hoặc W3C Trace Context. Hãy chọn một quy ước nhất quán, ghi rõ phạm vi ID và tránh tạo đồng thời nhiều header có cùng mục đích mà không có quy tắc ưu tiên.

## 2. Metadata mang correlation và trace context

gRPC truyền thông tin phụ trợ của lời gọi qua request headers và response headers/trailers. Với các giá trị văn bản ngắn, API `grpc-java` sử dụng `Metadata.Key<String>` và `Metadata.ASCII_STRING_MARSHALLER`.

Các key thường gặp:

| Metadata key | Mục đích | Ai tạo/quản lý? |
| --- | --- | --- |
| `x-correlation-id` | Gắn log và sự kiện theo một chuỗi xử lý nghiệp vụ | Ứng dụng hoặc gateway có chính sách rõ ràng |
| `traceparent` | Mang phiên bản, trace ID, parent span ID và trace flags theo W3C | Tracing instrumentation/propagator |
| `tracestate` | Mang trạng thái mở rộng theo W3C cho các hệ thống tracing | Propagator và nhà cung cấp tracing |
| `baggage` | Mang các key–value được phép lan truyền qua ranh giới dịch vụ | Propagator và ứng dụng |

Đây là **ASCII metadata**. Các key tùy biến có hậu tố `-bin` chỉ phù hợp khi thật sự cần byte nhị phân. Không tự đổi `traceparent` thành `traceparent-bin`; đó không phải tên của W3C Trace Context.

Ví dụ metadata của một lời gọi:

```text
x-correlation-id: corr-8b31f43a
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

`tracestate` và `baggage` là thành phần có điều kiện, nên ví dụ không nhất thiết có chúng. Thư viện tracing có thể tự động thêm `traceparent` khi đã được cấu hình đúng.

## 3. Đọc cấu trúc `traceparent` theo W3C

Đối với phiên bản `00` của W3C Trace Context, dạng tiêu biểu là:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             │  │                                │                │
             │  └─ trace-id: 16 byte, 32 hex      │                │
             │                                   │                │
             └─ version                          └─ parent-id      └─ flags
                                                     8 byte, 16 hex   1 byte, 2 hex
```

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Version | `00` | Phiên bản định dạng traceparent |
| Trace ID | `4bf92f3577b34da6a3ce929d0e0e4736` | Dùng để nhận diện cùng distributed trace |
| Parent ID | `00f067aa0ba902b7` | ID của span ở phía phát metadata, làm cơ sở tạo quan hệ cha–con |
| Trace flags | `01` | Bit lấy mẫu `sampled` được bật trong ví dụ |

Trace ID và parent ID **không được toàn số 0** trong định dạng hợp lệ. Định dạng trace ID/span ID là chuỗi hex theo chuẩn; không lấy một UUID tùy ý rồi ghép trực tiếp vào `traceparent` mà bỏ qua bước chuẩn hóa và kiểm tra định dạng.

**Sampled flag không phải cam kết chắc chắn trace sẽ có mặt trong hệ thống lưu trữ.** Các sampler, chính sách thu thập và collector có thể quyết định dữ liệu nào được ghi hoặc xuất đi. Các dịch vụ nên tuân thủ cách xử lý context của hệ thống tracing đã cấu hình, thay vì tự sửa cờ lấy mẫu.

Khi dịch vụ B nhận một `traceparent` hợp lệ, instrumentation có thể dùng nó làm remote parent rồi tạo **span mới với span ID mới**. Trace ID vẫn được giữ trong cùng trace. Khi B gọi C, metadata outgoing phản ánh span đang hoạt động ở phía B; `parent-id` trên đường truyền vì thế thường khác lần gọi A → B.

`tracestate` bổ sung thông tin theo chuẩn W3C để hỗ trợ nhiều hệ thống tracing phối hợp. `baggage` mang dữ liệu ứng dụng có thể được lan truyền; không dùng nó làm kho bí mật hoặc nguồn cấp quyền, vì các downstream service có thể đọc và chuyển tiếp dữ liệu này.

## 4. Luồng truyền qua nhiều dịch vụ

Giả sử Spring gRPC vận hành ba dịch vụ:

```text
Ứng dụng người dùng
    |
    | x-correlation-id: corr-42
    | traceparent: trace=T1, parent=P1
    v
API Gateway
    |  Server span G1, trace T1
    |  Client span G2, trace T1
    |
    | x-correlation-id: corr-42
    | traceparent: trace=T1, parent=G2
    v
OrderService
    |  Server span O1, trace T1
    |  Client span O2, trace T1
    |
    | x-correlation-id: corr-42
    | traceparent: trace=T1, parent=O2
    v
InventoryService
       Server span I1, trace T1
```

Các tên `T1`, `G2`, `O2` trong sơ đồ là ký hiệu minh họa, **không phải chuỗi hex để đưa vào traceparent**.

Điều cần quan sát:

1. **Correlation ID** của nghiệp vụ là `corr-42`, được giữ nhất quán trên các hop mà chính sách yêu cầu.
2. **Trace ID** giữ nguyên nếu cả chuỗi lời gọi thuộc một trace và context được truyền đúng.
3. **Span ID** khác nhau giữa từng thao tác. Server span thông thường có quan hệ con với client span ở upstream nếu trace context được extract thành công.
4. Khi context bị mất giữa gateway và OrderService, hệ thống tracing có thể tạo trace mới. Log vẫn có thể tìm được nhờ correlation ID, nhưng timeline của một trace sẽ bị đứt.

Correlation ID hỗ trợ tìm kiếm log; tracing cho biết cấu trúc lời gọi, thời lượng, lỗi và quan hệ các span. Một hệ thống quan sát tốt thường sử dụng cả hai thay vì chọn chỉ một.

## 5. Thiết kế vòng đời correlation ID

Cần thống nhất: **ai có quyền tạo ID, khi nào tái sử dụng và khi nào sinh mới**.

### 5.1. Tạo tại ranh giới hệ thống

Tại entry point đáng tin cậy, ví dụ gateway của ứng dụng, có thể:

- Sinh ID ngẫu nhiên đủ khó đoán, chẳng hạn `UUID.randomUUID()`, cho mỗi yêu cầu mới.
- Nếu nhận ID từ upstream **đã được xác thực và được tin cậy**, kiểm tra định dạng/độ dài trước khi giữ lại.
- Nếu nhận ID từ client công cộng, ưu tiên sinh ID riêng do hệ thống quản lý để tránh client gán ID của người khác và làm nhiễu log.
- Chỉ truyền correlation ID qua các dịch vụ có nhiệm vụ xử lý cùng tác vụ; khi mở tác vụ độc lập mới, quyết định rõ cần sinh correlation ID mới hay kế thừa quan hệ với tác vụ cũ.

Ví dụ định dạng ứng dụng:

```text
x-correlation-id: 2a29a1f7-3a20-4ab7-9f94-f147524728c1
```

UUID chỉ là một lựa chọn. ID không chứa tên người dùng, email, số điện thoại hoặc thông tin bí mật; bản thân ID cũng **không chứng minh danh tính hay quyền truy cập**.

### 5.2. Xác thực hình thức và giới hạn

Một chính sách minh họa là chỉ nhận `[A-Za-z0-9._-]` và độ dài từ 1 đến 64 ký tự. Chính sách này:

- Hạn chế ký tự điều khiển và newline có thể phá cấu trúc log.
- Tránh ID quá dài làm phình metadata.
- Giảm nguy cơ dữ liệu tùy ý từ client được đưa vào hệ thống quan sát.

Đây là quy tắc **ứng dụng tự đặt**, không phải quy tắc bắt buộc của gRPC. Một giá trị hợp lệ về định dạng vẫn có thể là giả mạo nếu đến từ nguồn không tin cậy.

### 5.3. Kế thừa qua hop và bất đồng bộ

Khi OrderService gọi InventoryService để phục vụ cùng yêu cầu, giữ correlation ID hoặc ánh xạ nó sang một context do hệ thống kiểm soát. Với job bất đồng bộ hoặc queue, correlation ID có thể được đưa vào metadata của message theo hợp đồng queue; **không mặc định gRPC tự truyền context qua một hệ thống message broker**.

Khi một công việc mới cần tạo trace riêng, có thể giữ correlation ID nghiệp vụ để tìm kiếm liên quan và sử dụng span link hoặc ngữ nghĩa tracing phù hợp. Không tự chỉnh sửa trace ID của span đã được OpenTelemetry tạo.

## 6. Server interceptor: nhận và lưu correlation ID trong gRPC Context

Ở server, `ServerInterceptor` có thể đọc metadata đầu vào, xác thực giá trị và lưu vào `io.grpc.Context`. Ví dụ dưới đây cho phép cấu hình `trustUpstream`: chỉ sử dụng ID bên gửi khi upstream đã nằm trong **ranh giới tin cậy**; ngoài ra server tự sinh ID.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;
import java.util.UUID;

public final class CorrelationIdServerInterceptor implements ServerInterceptor {

    private static final Metadata.Key<String> CORRELATION_HEADER =
        Metadata.Key.of(
            "x-correlation-id",
            Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> CURRENT_ID =
        Context.key("correlation-id");

    private final boolean trustUpstream;

    public CorrelationIdServerInterceptor(boolean trustUpstream) {
        this.trustUpstream = trustUpstream;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Iterable<String> all = headers.getAll(CORRELATION_HEADER);
        String received = null;
        if (all != null) {
            Iterator<String> iterator = all.iterator();
            if (iterator.hasNext()) {
                received = iterator.next();
            }
            // Tránh giá trị mơ hồ từ nhiều header cùng tên.
            if (iterator.hasNext()) {
                call.close(
                    Status.INVALID_ARGUMENT.withDescription(
                        "Multiple correlation IDs"),
                    new Metadata());
                return new ServerCall.Listener<ReqT>() {};
            }
        }

        String effectiveId = trustUpstream && isValid(received)
            ? received
            : UUID.randomUUID().toString();

        Context callContext =
            Context.current().withValue(CURRENT_ID, effectiveId);

        return Contexts.interceptCall(
            callContext, call, headers, next);
    }

    private static boolean isValid(String value) {
        return value != null
            && value.matches("[A-Za-z0-9._-]{1,64}");
    }
}
```

Ví dụ này có ba điểm quan trọng:

1. `Metadata.Key<String>` đi cùng `ASCII_STRING_MARSHALLER` vì correlation ID là chuỗi ASCII.
2. `Contexts.interceptCall(...)` gắn `CURRENT_ID` vào context của lời gọi cho quá trình xử lý ở phía server.
3. `trustUpstream` là cấu hình minh họa. **Không bật nó chỉ vì request đi từ một địa chỉ trong mạng nội bộ**; cần đánh giá authentication, quyền truy cập dịch vụ và khả năng header bị client tự chèn.

Trong service implementation, lấy giá trị đang có bằng:

```java
String correlationId = CorrelationIdServerInterceptor.CURRENT_ID.get();
// Ví dụ: logger.info("ReserveStock correlationId={}", correlationId);
```

`Context` gắn với phạm vi thực thi của gRPC, không phải một biến toàn cục cho tất cả RPC. Nếu công việc chuyển sang executor tự quản, cần truyền context qua executor để không mất ID.

## 7. Client interceptor: gửi correlation ID cho mỗi RPC

Client có thể truyền ID vào `CallOptions` của **stub cho lời gọi cụ thể**. Interceptor đọc option, gắn request metadata và sinh ID mới nếu chưa có.

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class CorrelationIdClientInterceptor implements ClientInterceptor {

    public static final CallOptions.Key<String> CORRELATION_OPTION =
        CallOptions.Key.create("correlation-id");

    private static final Metadata.Key<String> CORRELATION_HEADER =
        Metadata.Key.of(
            "x-correlation-id",
            Metadata.ASCII_STRING_MARSHALLER);

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

                String id = callOptions.getOption(CORRELATION_OPTION);
                if (id == null || id.isBlank()) {
                    id = UUID.randomUUID().toString();
                }
                headers.put(CORRELATION_HEADER, id);
                super.start(responseListener, headers);
            }
        };
    }
}
```

Giả sử một client `GreeterGrpc` đã được sinh từ `.proto` và đã có `channel`:

```java
GreeterGrpc.GreeterBlockingStub baseStub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(new CorrelationIdClientInterceptor());

// Khi code đang xử lý một RPC server có correlation ID hiện hành:
String inherited = CorrelationIdServerInterceptor.CURRENT_ID.get();

GreeterGrpc.GreeterBlockingStub callStub =
    baseStub.withOption(
        CorrelationIdClientInterceptor.CORRELATION_OPTION,
        inherited);

// callStub.sayHello(...) truyền cùng correlation ID cho downstream.
```

`GreeterGrpc` và `sayHello` là tên mẫu cho stub/method từ hợp đồng Protobuf. Trong ứng dụng thực tế, cấu hình client interceptor ở một nơi cố định; tạo stub cụ thể qua `withOption(...)` khi cần truyền ID tương ứng với từng yêu cầu.

**Lưu ý:** giá trị option được dùng lại nếu cùng stub đã cấu hình được chia sẻ. Tránh lưu correlation ID của người dùng A vào một singleton stub rồi tái sử dụng cho người dùng B. Đảm bảo ID đến từ context đã được kiểm tra hoặc tạo bởi hệ thống, không lấy trực tiếp từ input chưa xác minh.

Mã trên **chỉ truyền correlation ID**, chưa tự tạo hoặc kết nối OpenTelemetry span. Tracing instrumentation phải được cấu hình riêng; khi đó hai cơ chế có thể cùng gắn metadata lên một RPC.

## 8. Trace context với OpenTelemetry trong Spring gRPC

Trong distributed tracing, việc truyền trace context gồm hai bước:

1. **Inject ở client:** lấy context của span đang hoạt động và tạo các header theo propagator đã cấu hình.
2. **Extract ở server:** đọc context từ metadata, tạo server span liên quan đến remote parent và đưa span mới vào phạm vi xử lý.

Nếu hệ thống thống nhất dùng **W3C Trace Context**, propagator sẽ quản lý `traceparent` và, khi có, `tracestate`. Nếu dùng W3C Baggage thì propagator thích hợp cần được bật và áp dụng theo chính sách. **Không mặc định rằng gRPC tự động truyền trace context chỉ vì ứng dụng có thư viện OpenTelemetry trên classpath.**

### 8.1. Chọn một cơ chế instrumentation rõ ràng

Trong một ứng dụng Spring gRPC thường có các hướng tích hợp:

- Java agent OpenTelemetry hỗ trợ phiên bản gRPC tương ứng, hoặc instrumentation tự động do nền tảng cung cấp.
- Các interceptor/instrumenter của OpenTelemetry cho `grpc-java` được gắn vào client và server theo hướng dẫn của phiên bản thư viện đang sử dụng.
- Instrumentation thủ công bằng API và propagator của OpenTelemetry khi có lý do đặc biệt.

Ở từng phương án, cần xác minh **cả client và server** đã được instrument và cùng dùng propagator tương thích. Không gắn hai bộ instrumentation tạo span độc lập cho một thao tác mà không chủ định, vì có thể gây span lặp và làm sai thời gian đo.

Khi cần truy xuất định danh đang có để ghi log, API OpenTelemetry Java có thể cung cấp:

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;

SpanContext spanContext = Span.current().getSpanContext();
if (spanContext.isValid()) {
    String traceId = spanContext.getTraceId();
    String spanId = spanContext.getSpanId();

    // Ghi log theo policy: correlationId, traceId, spanId.
    // Không log authorization metadata hoặc baggage nhạy cảm.
}
```

`Span.current()` chỉ trả span hợp lệ khi instrumentation và context propagation đúng tại vị trí thực thi. Nếu span không hợp lệ, không tự tạo một `traceparent` giả chỉ để lấp đầy log.

### 8.2. Phân biệt hai loại Context trong Java

| Kiểu | Phạm vi | Ví dụ |
| --- | --- | --- |
| `io.grpc.Context` | Ngữ cảnh vòng đời gRPC; có thể mang correlation ID hoặc trạng thái hủy | `CorrelationIdServerInterceptor.CURRENT_ID.get()` |
| `io.opentelemetry.context.Context` | Ngữ cảnh của OpenTelemetry; có thể mang span và baggage | `Span.current()` qua context hiện hành |
| `org.slf4j.MDC` | Các trường bổ sung vào log, thường gắn với thread | `correlation_id`, `trace_id` |

Ba cơ chế không phải cùng một đối tượng. Các thư viện instrumentation có thể kết nối context với luồng thực thi nhưng **không nên giả định dữ liệu tự động xuất hiện ở cả ba nơi**. Đặc biệt, truyền `io.grpc.Context` qua executor không mặc nhiên đảm bảo MDC hoặc OpenTelemetry context cũng được truyền nếu executor không được instrument.

### 8.3. Qua executor và streaming

Nếu server tách xử lý sang một executor:

```java
import io.grpc.Context;
import java.util.concurrent.Executor;

// Trong callback gRPC khi context của lời gọi vẫn đang active:
Context grpcContext = Context.current();
Executor executor = /* executor của ứng dụng */;

executor.execute(grpcContext.wrap(() -> {
    String id = CorrelationIdServerInterceptor.CURRENT_ID.get();
    // Xử lý nghiệp vụ; id được kế thừa qua gRPC Context.
}));
```

Đoạn này minh họa **chỉ việc truyền `io.grpc.Context`**. Với OpenTelemetry, dùng executor được instrument hoặc cơ chế context wrapper của OpenTelemetry tương ứng. Nếu ứng dụng ghi log bằng MDC, cần thiết lập và khôi phục các giá trị MDC trong phạm vi callback, tránh để dữ liệu của một request còn tồn tại trên thread được tái sử dụng.

Đối với **server streaming**, **client streaming** và **bidirectional streaming**, metadata được gửi khi bắt đầu RPC. Dữ liệu thay đổi theo **từng message** nên nằm trong Protobuf message. Một stream dài có thể có nhiều sự kiện hoặc span con trong cùng trace theo chiến lược quan sát, nhưng không có header `traceparent` mới tự động trên từng message của stream.

## 9. Ghi log và giám sát đúng cách

Một cấu trúc log hợp lý có thể chứa:

```text
timestamp=2026-11-19T02:00:00Z
service=inventory-service
rpc=ReserveStock
correlation_id=2a29a1f7-3a20-4ab7-9f94-f147524728c1
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
span_id=00f067aa0ba902b7
grpc_status=OK
duration_ms=18
```

Đây là các giá trị **minh họa**. Log có thể lưu ở dạng JSON hoặc cấu trúc key–value phù hợp hệ thống quan sát. Truy tìm sự cố thường gồm:

1. Tìm log bằng `correlation_id` để lấy các sự kiện liên quan đến tác vụ.
2. Lấy `trace_id` từ log ở thời điểm lỗi và mở trace để xem các span, độ trễ và quan hệ gọi dịch vụ.
3. Đối chiếu `grpc_status`, deadline và các span có lỗi để xác định service hoặc thao tác cần điều tra.
4. Nếu trace bị đứt, kiểm tra instrumentation/propagator ở ranh giới dịch vụ và việc truyền context qua executor, job hoặc queue.

Không dùng `trace_id` hay `correlation_id` làm **metric label** cho từng request nếu hệ thống metrics kiểu time series: mỗi ID riêng tạo cardinality rất lớn và dễ làm tăng chi phí lưu trữ. Dùng trace/span attributes, log fields hoặc exemplar theo khả năng của hệ thống quan sát; metric labels nên có số lượng giá trị được kiểm soát.

Correlation ID có thể được server trả về cho client qua response metadata theo hợp đồng ứng dụng nếu việc đó phục vụ hỗ trợ kỹ thuật. Chỉ trả ID đã được tạo/kiểm tra theo chính sách và không kèm bí mật. Việc truyền trace context ở response không phải yêu cầu mặc định để W3C propagator hoạt động.

## 10. Bảo mật và ranh giới tin cậy

Metadata là dữ liệu điều khiển có thể bắt nguồn từ client. **Không coi bất kỳ header nào là chứng cứ nhận dạng hay phân quyền.**

| Nguy cơ | Cách giảm thiểu |
| --- | --- |
| Client tự chọn ID trùng của người khác | Sinh correlation ID mới tại ranh giới công cộng hoặc chỉ chấp nhận từ upstream tin cậy |
| Log injection qua ID chứa newline hoặc ký tự điều khiển | Giới hạn ký tự, độ dài; ghi log có cấu trúc |
| Trace context không hợp lệ hoặc bị làm giả | Dùng W3C propagator chuẩn để kiểm tra; thiết kế chính sách tin cậy tại entry point |
| `baggage` chứa token, email hoặc dữ liệu cá nhân | Chỉ cho phép những key không nhạy cảm, giới hạn dung lượng và điểm truyền |
| Metadata vượt giới hạn HTTP/2 headers | Truyền thông tin ngắn, không nhồi message lớn vào headers |
| Token hoặc secret vô tình xuất hiện trong log | Không dump toàn bộ `Metadata`; dùng allowlist trường được ghi |
| Mất context khi async/streaming | Truyền context bằng API thư viện và kiểm thử trên đúng đường chạy |
| Nhiều thư viện tracing cùng tạo span | Kiểm tra cấu hình agent, Spring observability và gRPC instrumentation để tránh trùng |

`traceparent` và `baggage` là các header truyền ngữ cảnh; dù hoạt động qua TLS, giá trị của chúng vẫn có thể hiện diện ở downstream service và proxy được phép giải mã. Không đặt bí mật vào baggage. Hãy dùng authentication/authorization và TLS/mTLS đúng chính sách bảo mật, độc lập với hệ thống truy vết.

## 11. Kiểm thử khả năng truyền context

Trong Spring gRPC, nên kiểm thử interceptor theo từng bước rồi mới chạy bài kiểm thử tích hợp xuyên dịch vụ. Có thể dùng `InProcessServerBuilder` và `InProcessChannelBuilder` để kiểm tra việc gắn metadata mà không mở cổng mạng; TLS, proxy, load balancer và cấu hình propagator thực tế cần kiểm tra trên môi trường gần sản xuất.

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Không có correlation ID | Gửi RPC không kèm `x-correlation-id` | Server tạo ID mới và gắn vào context |
| ID từ upstream tin cậy | Gửi ID hợp lệ khi `trustUpstream=true` | Server đọc đúng ID, downstream dùng cùng ID |
| Client công cộng tự chọn ID | `trustUpstream=false` | Server tự sinh ID và không coi ID gửi vào là đáng tin |
| ID sai định dạng | Gửi ID có newline hoặc quá 64 ký tự | Bị thay bằng ID hợp lệ hoặc từ chối theo chính sách đã chọn |
| Trùng key | Gửi hai `x-correlation-id` | Server xử lý theo chính sách, ví dụ từ chối `INVALID_ARGUMENT` |
| Hai RPC độc lập | Dùng chung stub không set option | Client interceptor tạo ID mới cho mỗi RPC |
| Hai RPC cùng tác vụ | Dùng stub với `withOption` cùng correlation ID | ID được kế thừa đúng qua các hop |
| Trace context hợp lệ | Instrument cả client/server với W3C propagator | Các span trong cùng trace; parent–child đúng |
| Không có hoặc sai `traceparent` | Gọi qua một hop thiếu instrumentation | Tạo context mới theo chính sách, không crash hoặc tin header sai |
| Qua executor | Chạy xử lý ngoài callback gRPC | Correlation ID và span context được giữ đúng với cơ chế propagation đã cấu hình |
| Streaming | Gửi nhiều message trong một RPC | Headers thuộc cả RPC, không bị nhầm là metadata của từng message |
| Kiểm tra dữ liệu nhạy cảm | Bật log/trace trong test | Không xuất hiện token hoặc baggage nhạy cảm |

### Minh họa unit test quy tắc metadata

Đoạn kiểm thử JUnit 5 sau chứng minh nhiều value cùng key cần được xử lý rõ ràng:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Metadata;
import java.util.Iterator;
import org.junit.jupiter.api.Test;

class CorrelationMetadataTest {
    private static final Metadata.Key<String> KEY =
        Metadata.Key.of(
            "x-correlation-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Test
    void repeatedKeyMustNotBeSilentlyAssumedUnique() {
        Metadata headers = new Metadata();
        headers.put(KEY, "corr-first");
        headers.put(KEY, "corr-second");

        assertEquals("corr-second", headers.get(KEY));
        Iterator<String> values = headers.getAll(KEY).iterator();
        assertEquals("corr-first", values.next());
        assertEquals("corr-second", values.next());
        assertFalse(values.hasNext());
    }
}
```

Test này chỉ kiểm tra thao tác `Metadata`. Muốn khẳng định interceptor đã chạy và server thực sự từ chối header lặp, cần test qua một RPC có đăng ký `CorrelationIdServerInterceptor`. Muốn xác minh **trace continuity**, cần instrumentation thực, span exporter dùng cho test và kiểm tra trace ID/quan hệ parent–child; sự hiện diện của `traceparent` ở dạng chuỗi chưa đủ.

## 12. Tình huống thực hành: tìm nguyên nhân RPC chậm

Ứng dụng bán hàng sử dụng Spring gRPC: `CheckoutService` gọi `InventoryService` để giữ hàng và `PaymentService` để thanh toán. Người dùng báo một giao dịch chậm; log của ba dịch vụ xuất hiện xen kẽ với nhiều người dùng khác.

**Yêu cầu triển khai:**

1. Tại gateway, sinh một correlation ID hợp lệ cho giao dịch; chỉ giữ ID upstream nếu thỏa mãn chính sách tin cậy.
2. Gắn correlation ID vào gRPC metadata khi gọi `CheckoutService`. Các lời gọi xuống inventory và payment sử dụng lại ID trong phạm vi giao dịch.
3. Cấu hình OpenTelemetry instrumentation ở client/server với propagator tương thích. Kiểm tra các span được tạo và trace ID được giữ qua các hop.
4. Ghi log có cấu trúc gồm `correlation_id`, `trace_id`, `span_id`, tên RPC, `grpc_status` và thời gian xử lý. Không ghi thông tin thanh toán, bearer token hay các baggage nhạy cảm.
5. Kiểm thử một RPC bình thường, một RPC quá deadline, một lời gọi qua executor và một tình huống thiếu trace context giữa hai dịch vụ.
6. Dựa trên trace để tìm span tốn thời gian; đối chiếu correlation ID để tìm các log lỗi hoặc sự kiện bất đồng bộ không thuộc cùng trace.

**Câu hỏi tự kiểm tra:**

- Correlation ID khác trace ID và span ID như thế nào?
- Vì sao parent ID trong `traceparent` có thể thay đổi khi một yêu cầu qua nhiều dịch vụ?
- Khi nào nên sinh correlation ID mới tại gateway thay vì tin ID client gửi đến?
- Nếu log có correlation ID giống nhau nhưng trace ID khác nhau, những tình huống nào có thể giải thích?
- Vì sao `baggage` không thích hợp để truyền access token?
- Vì sao truyền `io.grpc.Context` qua executor chưa đủ để khẳng định OpenTelemetry context và MDC cũng đã được chuyển?
- Trong gRPC streaming, metadata có tự thay đổi theo từng Protobuf message không?

**Ghi nhớ:** Correlation ID phục vụ liên kết log theo tác vụ; trace context phục vụ liên kết các span trong distributed tracing. Với Spring gRPC, hãy truyền correlation ID có kiểm soát qua `Metadata` và interceptor, để OpenTelemetry quản lý `traceparent`/`tracestate` và các span, đồng thời kiểm tra propagation qua ranh giới dịch vụ và xử lý bất đồng bộ. ID truy vết hỗ trợ quan sát hệ thống nhưng không thay thế xác thực, phân quyền hoặc bảo vệ dữ liệu.
