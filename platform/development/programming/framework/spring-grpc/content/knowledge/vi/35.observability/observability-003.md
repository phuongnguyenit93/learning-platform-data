# Status code distribution

Đếm tổng số RPC và đo latency cho biết tải và tốc độ xử lý, nhưng chưa giải thích được vì sao call thất bại. Phân phối gRPC status code cho thấy tỷ lệ thành công, timeout, cancellation, lỗi đầu vào, lỗi quyền truy cập và lỗi hạ tầng. Khi nhóm status theo service và method, đội vận hành có thể nhận ra một method bắt đầu trả UNAVAILABLE sau rollout hoặc DEADLINE_EXCEEDED tăng ở một dependency cụ thể.

**Status code distribution** là phân phối số RPC kết thúc theo mã trạng thái gRPC, thường được nhóm theo service, method và phía quan sát. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là thu thập terminal status đúng một lần, đọc phân phối status ở client/server và dùng dữ liệu để phân biệt lỗi nghiệp vụ với lỗi hạ tầng.

## 1. Status code là kết quả cuối của một RPC

gRPC dùng status code để biểu diễn kết quả cuối cùng của RPC. Một call hoàn tất thành công có status OK; call thất bại hoặc bị hủy có một status khác. Status được truyền cùng terminal event, thường qua trailers của HTTP/2.

Metric status distribution phải đếm **một lần cho mỗi RPC khi call đi vào terminal state**. Không tăng counter mỗi khi server gửi message hoặc client nhận message. Một server-streaming RPC gửi 10.000 message rồi hoàn tất bằng OK vẫn đóng góp một call vào nhóm OK.

Nên tách rõ các đại lượng:

| Đại lượng | Được đếm khi nào? | Câu hỏi |
| --- | --- | --- |
| RPC started | Khi call bắt đầu ở ranh giới instrumentation. | Có bao nhiêu call được khởi tạo/nhận? |
| RPC completed by status | Khi call kết thúc, gắn terminal status. | Call kết thúc với status nào? |
| RPC in-flight | Tăng khi bắt đầu, giảm khi kết thúc. | Hiện có bao nhiêu call đang chạy? |
| Message count | Mỗi message được gửi hoặc nhận. | Stream trao đổi bao nhiêu message? |
| Logical operation | Khi một ý định nghiệp vụ bắt đầu/kết thúc. | Một thao tác nghiệp vụ thành công hay thất bại? |

Status distribution thường dựa trên RPC completed. Nếu chỉ đo started, không thể biết call kết thúc thành công hay thất bại. Nếu chỉ đo completed, có thể bỏ sót các call đang chạy lâu; dùng thêm in-flight gauge để theo dõi chúng.

## 2. Các status code cần nhận diện

gRPC định nghĩa một tập mã status hữu hạn. Đây là các giá trị phù hợp để làm metric label:

| Status | Ý nghĩa thường gặp | Hướng điều tra |
| --- | --- | --- |
| OK | RPC hoàn tất thành công. | Theo dõi như baseline thành công. |
| CANCELLED | Call bị caller hoặc context liên quan hủy. | Kiểm tra client lifecycle, deadline và disconnect. |
| UNKNOWN | Lỗi không được ánh xạ sang status cụ thể. | Kiểm tra exception mapping và log server. |
| INVALID_ARGUMENT | Request không hợp lệ độc lập với trạng thái hệ thống. | Kiểm tra validation và caller contract. |
| DEADLINE_EXCEEDED | Call không hoàn tất trong deadline. | Kiểm tra latency, queue và dependency. |
| NOT_FOUND | Tài nguyên được yêu cầu không tồn tại. | Kiểm tra identifier và dữ liệu. |
| ALREADY_EXISTS | Tài nguyên hoặc khóa duy nhất đã tồn tại. | Kiểm tra create semantics và idempotency. |
| PERMISSION_DENIED | Caller không có quyền thực hiện thao tác. | Kiểm tra authorization policy. |
| RESOURCE_EXHAUSTED | Hết quota hoặc tài nguyên. | Kiểm tra rate limit, thread/connection pool và capacity. |
| FAILED_PRECONDITION | Trạng thái hệ thống chưa đáp ứng điều kiện để thực hiện. | Kiểm tra state transition và prerequisite. |
| ABORTED | Operation bị hủy do conflict hoặc điều kiện concurrency. | Kiểm tra transaction/conflict và retry ở tầng phù hợp. |
| OUT_OF_RANGE | Giá trị nằm ngoài miền hợp lệ. | Kiểm tra range và pagination cursor. |
| UNIMPLEMENTED | Method hoặc chức năng chưa được hỗ trợ. | Kiểm tra version API và server implementation. |
| INTERNAL | Lỗi nội bộ không nên được xem là lỗi request thông thường. | Kiểm tra exception, invariant và dependency. |
| UNAVAILABLE | Service hoặc transport hiện không thể phục vụ. | Kiểm tra instance, network, load balancer và dependency. |
| DATA_LOSS | Mất hoặc hỏng dữ liệu nghiêm trọng. | Điều tra persistence, replication và recovery. |
| UNAUTHENTICATED | Caller chưa được xác thực hợp lệ. | Kiểm tra credential, token và authentication. |

Status code là hợp đồng giữa service và caller, không phải bản phân loại nguyên nhân hoàn hảo. Ví dụ, UNAVAILABLE có thể do server dừng, proxy lỗi hoặc dependency không sẵn sàng. DEADLINE_EXCEEDED không chứng minh server chưa commit side effect. CANCELLED ở server cũng không nhất thiết có nghĩa người dùng đã bấm nút hủy; deadline hết hạn hoặc peer disconnect có thể dẫn tới trạng thái cancellation ở phía server.

## 3. Nhóm status để đọc tình trạng hệ thống

Dashboard thường cần ba góc nhìn:

- **Success rate:** tỷ lệ RPC kết thúc bằng OK.
- **Error/status distribution:** tỷ lệ từng status khác OK.
- **Status volume:** số lượng tuyệt đối của từng status theo thời gian.

Không gộp mọi status khác OK thành một nhóm duy nhất. INVALID_ARGUMENT tăng có thể là caller gửi request sai; UNAVAILABLE tăng có thể là vấn đề hạ tầng; PERMISSION_DENIED tăng có thể là thay đổi policy. Hành động xử lý rất khác nhau.

Có thể nhóm status cho mục đích tổng quan, nhưng vẫn giữ metric gốc theo từng status:

| Nhóm quan sát | Status tiêu biểu | Cách dùng |
| --- | --- | --- |
| Thành công | OK | Baseline và success rate. |
| Caller/request | INVALID_ARGUMENT, NOT_FOUND, ALREADY_EXISTS, OUT_OF_RANGE | Theo dõi contract, validation và dữ liệu đầu vào. |
| Identity/access | UNAUTHENTICATED, PERMISSION_DENIED | Theo dõi authentication và authorization. |
| Capacity/state | RESOURCE_EXHAUSTED, FAILED_PRECONDITION, ABORTED | Theo dõi quota, concurrency và state machine. |
| Availability/runtime | UNAVAILABLE, INTERNAL, UNKNOWN, UNIMPLEMENTED, DATA_LOSS | Điều tra hạ tầng, lỗi phần mềm và tương thích API. |
| Lifecycle/time | CANCELLED, DEADLINE_EXCEEDED | Theo dõi caller cancellation, timeout và thời gian xử lý. |

Nhóm này là cách tổ chức dashboard; không thay đổi status code gRPC và không nên dùng một label group thay cho label status nếu cần điều tra chi tiết.

## 4. Thiết kế metric và label

Một metric completed ở server có thể được đặt tên như sau:

```text
grpc.server.calls
  type: Counter
  tags: service, method, status

grpc.client.calls
  type: Counter
  tags: service, method, status
```

Tên service/method lấy từ Protobuf MethodDescriptor, ví dụ:

| Full method name | service | method |
| --- | --- | --- |
| inventory.Inventory/GetStock | inventory.Inventory | GetStock |
| orders.OrderService/CreateOrder | orders.OrderService | CreateOrder |

Status lấy từ Status.Code.name(), là một tập hữu hạn. Nếu dùng chung metric family cho client và server, thêm label direction với hai giá trị client/server; cách đơn giản hơn là giữ metric name riêng để tránh nhầm lẫn.

Không thêm request ID, trace ID, user ID, order ID, exception message hoặc metadata tùy ý làm label. Mỗi giá trị mới có thể tạo một time series mới; các identifier có cardinality lớn sẽ làm metrics backend tốn bộ nhớ và chi phí ingest. Dùng trace/log cho từng request, metric cho xu hướng tổng hợp.

## 5. Thu thập status phía server bằng ServerInterceptor

ServerInterceptor nhìn thấy method khi server nhận call và có thể bọc ServerCall để ghi status khi call đóng. Cần xử lý thêm callback onCancel vì một call bị peer hủy có thể không đi qua đường close do application chủ động:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcStatusServerInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;

    public RpcStatusServerInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String fullMethod =
                call.getMethodDescriptor().getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        AtomicBoolean recorded = new AtomicBoolean();
        java.util.function.Consumer<Status> record = status -> {
            if (recorded.compareAndSet(false, true)) {
                registry.counter(
                        "grpc.server.calls",
                        "service", service,
                        "method", method,
                        "status", status.getCode().name()
                ).increment();
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        record.accept(status);
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                record.accept(Status.CANCELLED);
                super.onCancel();
            }
        };
    }
}
```

AtomicBoolean bảo đảm một terminal count cho mỗi call nếu onCancel và close cùng xảy ra. Server-side onCancel được ghi nhận là CANCELLED vì đó là trạng thái cancellation mà server quan sát. Nó không nhất thiết cho biết client-side status cuối là CANCELLED hay DEADLINE_EXCEEDED.

Interceptor phải được đăng ký vào server đang được Spring gRPC starter quản lý. Cách đăng ký phụ thuộc starter/version: dùng extension point chính thức hoặc server builder do starter cung cấp. Không tạo server thứ hai chỉ để gắn metric interceptor.

## 6. Thu thập status phía client bằng ClientInterceptor

Client-side onClose nhận status cuối mà ứng dụng client quan sát được. Đây là nơi phù hợp để đo phân phối status từ góc nhìn caller:

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
import io.micrometer.core.instrument.MeterRegistry;

public final class RpcStatusClientInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public RpcStatusClientInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        String fullMethod = method.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String methodName = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {

                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                registry.counter(
                                        "grpc.client.calls",
                                        "service", service,
                                        "method", methodName,
                                        "status", status.getCode().name()
                                ).increment();
                                super.onClose(status, trailers);
                            }
                        };
                super.start(monitored, headers);
            }
        };
    }
}
```

Gắn interceptor vào channel bằng ManagedChannelBuilder.intercept(...) hoặc extension point tương ứng của Spring starter. Một client call có thể có retry nội bộ; vị trí interceptor trong call chain quyết định instrumentation quan sát logical call hay từng attempt. Không đặt tên metric là attempt count nếu chưa xác minh semantics của phiên bản và retry mechanism đang dùng.

## 7. Vì sao status phía client và server có thể khác?

Client và server quan sát call ở hai đầu transport. Trong một số tình huống, status được ghi nhận ở hai phía có thể khác nhau:

| Tình huống | Server có thể ghi | Client có thể thấy |
| --- | --- | --- |
| Server trả lỗi có status | Status application trả về, ví dụ NOT_FOUND. | Cùng status nếu response tới được client. |
| Client chủ động cancel | onCancel, thường ghi CANCELLED. | CANCELLED. |
| Client deadline hết | Context server bị cancellation; interceptor có thể ghi CANCELLED nếu onCancel đến trước close. | DEADLINE_EXCEEDED. |
| Server đã close OK nhưng response bị mất trên transport | Server đã ghi OK. | UNAVAILABLE hoặc lỗi transport khác. |
| Client không kết nối được tới server | Server có thể không nhận call nên không có server metric. | UNAVAILABLE hoặc DEADLINE_EXCEEDED. |

Do đó, không cộng server counter và client counter để ra “tổng số RPC”. Chúng là hai góc nhìn độc lập. Nếu cần phân tích nguyên nhân, liên kết bằng trace context hoặc request correlation trong log, không dùng trace ID làm metric label.

## 8. Tính status rate và error ratio trong Prometheus

Giả sử Micrometer Counter grpc.server.calls được export thành grpc_server_calls_total. Tốc độ RPC theo status:

```promql
sum by (service, method, status) (
  rate(grpc_server_calls_total[5m])
)
```

Tổng request rate theo service và method:

```promql
sum by (service, method) (
  rate(grpc_server_calls_total[5m])
)
```

Tỷ lệ status khác OK:

```promql
sum by (service, method) (
  rate(grpc_server_calls_total{status!="OK"}[5m])
)
/
sum by (service, method) (
  rate(grpc_server_calls_total[5m])
)
```

Tỷ lệ UNAVAILABLE:

```promql
sum by (service, method) (
  rate(grpc_server_calls_total{status="UNAVAILABLE"}[5m])
)
/
sum by (service, method) (
  rate(grpc_server_calls_total[5m])
)
```

Tỷ lệ phần trăm có thể nhân kết quả với 100 trong query hoặc định dạng ở dashboard. Khi mẫu số bằng 0, query có thể trả NaN/không có dữ liệu; dashboard nên hiển thị no traffic thay vì báo lỗi 0% một cách gây hiểu nhầm.

Tên metric và label sau export phụ thuộc registry/exporter. Hãy kiểm tra series thực tế trước khi dùng query. Nếu metric có thêm direction, lọc direction=server hoặc client để không trộn hai phía.

## 9. Diễn giải status distribution theo method

Một status tăng cần được đặt trong ngữ cảnh request rate, latency và thay đổi triển khai:

| Dấu hiệu | Khả năng cần xem xét | Hướng xử lý |
| --- | --- | --- |
| UNAVAILABLE tăng đột ngột ở nhiều method | Instance, network, proxy hoặc dependency không sẵn sàng. | Kiểm tra subchannel, health, rollout và hạ tầng. |
| DEADLINE_EXCEEDED tăng ở một method | Method hoặc dependency của nó chậm hơn ngân sách. | Đọc latency histogram, deadline và downstream spans. |
| RESOURCE_EXHAUSTED tăng | Quota hoặc capacity bị chạm. | Kiểm tra rate limit, concurrency, pool và retry storm. |
| INVALID_ARGUMENT tăng sau release | Client/server contract hoặc validation thay đổi. | So sánh version client, proto contract và request validation. |
| UNAUTHENTICATED tăng | Credential hết hạn, token sai hoặc identity provider lỗi. | Kiểm tra authentication metadata và token issuer. |
| PERMISSION_DENIED tăng | Policy quyền thay đổi hoặc caller thiếu quyền. | Kiểm tra authorization rule; không tự retry. |
| CANCELLED tăng | Caller rời đi, context cha bị hủy hoặc transport lifecycle thay đổi. | Đối chiếu client metrics, deadline và tracing. |
| INTERNAL/UNKNOWN tăng | Exception chưa được ánh xạ hoặc lỗi không dự kiến. | Kiểm tra log có trace ID và exception mapping. |

Một status có thể hợp lệ trong nghiệp vụ. Ví dụ NOT_FOUND khi tra một tài nguyên không tồn tại không nhất thiết là sự cố. Cần định nghĩa baseline/alert theo method và kỳ vọng sản phẩm, không cảnh báo mọi status khác OK với cùng mức độ nghiêm trọng.

## 10. Phân biệt status với exception và HTTP status

Status gRPC là kết quả của RPC, không phải HTTP status code. gRPC thường chạy trên HTTP/2, nhưng HTTP status ở tầng transport và gRPC status ở trailers có semantics khác nhau. Không ánh xạ máy móc HTTP 404 thành gRPC NOT_FOUND hoặc HTTP 503 thành UNAVAILABLE nếu chưa hiểu nguồn lỗi.

Ở server, application nên chuyển lỗi nghiệp vụ sang status có chủ đích:

```java
throw Status.NOT_FOUND
        .withDescription("Không tìm thấy inventory item")
        .asRuntimeException();
```

Không đưa stack trace hoặc dữ liệu nhạy cảm vào description trả về client. Ghi chi tiết exception ở server log với trace/correlation ID.

Ở client, có thể đọc status từ throwable:

```java
Status status = Status.fromThrowable(failure);
Status.Code code = status.getCode();

if (code == Status.Code.UNAVAILABLE) {
    // Áp dụng chính sách retry nếu operation an toàn.
}
```

Nếu throwable không chứa status gRPC có thể nhận diện, Status.fromThrowable thường trả UNKNOWN. Do đó UNKNOWN tăng có thể là dấu hiệu exception chưa được map hoặc lỗi ngoài gRPC.

## 11. Retry ảnh hưởng tới status distribution

Retry làm cách nhìn status phức tạp hơn:

- Một logical client call có thể có attempt thất bại rồi attempt sau thành công.
- Client cuối cùng có thể nhận OK dù một attempt trước đó gặp UNAVAILABLE.
- Server đã nhận các attempt trước vẫn ghi nhận status của từng RPC mà nó xử lý.
- Instrumentation ở client có thể chỉ ghi terminal status của logical call, tùy vị trí interceptor và retry implementation.

Vì vậy, client/server status distribution không nhất thiết bằng nhau. Nếu cần biết số attempt, retry success, retry exhaustion và số call logic, tạo metric riêng theo instrumentation có semantics đã xác minh. Không suy số lần retry bằng cách trừ server count và client count.

Retry policy phải phù hợp với status và semantics của operation:

| Status | Nguyên tắc thường dùng |
| --- | --- |
| UNAVAILABLE | Có thể retry với backoff/jitter nếu operation an toàn và còn deadline. |
| RESOURCE_EXHAUSTED | Chỉ retry khi lỗi mang tính tạm thời và policy có giới hạn; retry có thể làm quá tải nặng hơn. |
| ABORTED | Có thể cần retry toàn bộ transaction/operation ở tầng nghiệp vụ. |
| FAILED_PRECONDITION | Chỉ thử lại sau khi điều kiện tiên quyết được thay đổi. |
| DEADLINE_EXCEEDED | Không giả định operation chưa commit; cần idempotency/status lookup trước retry. |
| CANCELLED | Thường tôn trọng ý định caller; không tự retry một call caller đã bỏ. |
| INVALID_ARGUMENT, PERMISSION_DENIED, UNAUTHENTICATED | Thường cần sửa request/credential/policy thay vì retry nguyên trạng. |

Đây là nguyên tắc vận hành, không phải bảng retry mặc định cho mọi service. Retryable status phải được cấu hình theo method, idempotency và ngân sách deadline.

## 12. Status distribution cho unary và streaming

Status counter vẫn đếm một lần cho mỗi RPC dù call là unary hay streaming. Có thể thêm label rpc_type với tập giá trị cố định:

| rpc_type | Ví dụ |
| --- | --- |
| unary | Một request, một response. |
| client_streaming | Nhiều request message, một response. |
| server_streaming | Một request, nhiều response message. |
| bidi_streaming | Nhiều message theo cả hai chiều. |

Với stream dài, status chỉ xuất hiện khi stream kết thúc. Một stream đang mở không thuộc bất kỳ terminal status counter nào cho tới khi complete, error hoặc cancel. Dùng active stream gauge để quan sát số stream hiện đang tồn tại.

Không đếm từng onNext thành một RPC status. Nếu muốn theo dõi message-level errors, hãy tạo metric riêng và định nghĩa rõ message processing outcome khác với terminal status của toàn stream.

## 13. Kiểm thử status instrumentation

Dùng SimpleMeterRegistry và in-process gRPC server/channel để xác minh interceptor ghi đúng status:

1. Gọi unary RPC thành công; xác minh một counter có status OK.
2. Cho service trả NOT_FOUND; xác minh status label là NOT_FOUND.
3. Gọi hai method khác nhau; xác minh series tách theo method.
4. Hủy client call; xác minh server terminal count chỉ tăng một lần dù onCancel và close cạnh tranh.
5. Đặt deadline ngắn; so sánh client DEADLINE_EXCEEDED với status cancellation mà server quan sát.
6. Gọi streaming RPC nhiều message; xác minh terminal counter chỉ tăng một lần khi stream kết thúc.
7. Mô phỏng client không kết nối được; xác minh client có status nhưng server không có completed call nếu request chưa tới server.
8. Kiểm tra label không chứa request ID, trace ID hoặc dữ liệu từ metadata tùy ý.

Test cần chờ terminal callback hoặc latch từ server trước khi đọc registry. Không dùng sleep cố định để đoán lúc counter đã tăng. Với exporter thực tế, kiểm tra thêm tên metric và label sau khi Prometheus/OpenTelemetry chuẩn hóa.

## 14. Dashboard và cảnh báo

Một dashboard status distribution hữu ích nên có:

- Stacked time series hoặc bảng tỷ lệ status theo service/method.
- Success rate và error ratio theo cửa sổ 5 phút.
- UNAVAILABLE, DEADLINE_EXCEEDED, RESOURCE_EXHAUSTED và INTERNAL riêng.
- Request rate để đặt error ratio vào đúng mẫu số.
- Latency p95/p99 để phân biệt chậm với lỗi tức thời.
- Client/server direction để nhận biết call bị lỗi trước khi tới server.

Alert nên dựa trên cả tỷ lệ và số lượng tối thiểu. Ví dụ, 1 lỗi trên 2 request tạo error ratio 50% nhưng có thể chưa đủ bằng chứng cho một sự cố diện rộng. Ngược lại, 2% lỗi trên hàng chục nghìn RPC có thể ảnh hưởng nhiều caller. Dùng cửa sổ thời gian, minimum traffic và severity theo method/SLO.

## 15. Cardinality và bảo mật

Status là tập enum nhỏ nên phù hợp làm label. Service và method cũng là tập hữu hạn theo API. Tuy nhiên, không nên thêm:

- Request ID, trace ID, span ID.
- User, account, tenant hoặc order ID.
- Exception message, stack trace hoặc status description.
- Metadata tùy ý do client gửi.
- Địa chỉ endpoint ephemeral nếu tập giá trị không được kiểm soát.

Status description có thể chứa dữ liệu nhạy cảm nếu application đưa nội dung request vào đó. Metric chỉ dùng code name; log/trace cần lọc dữ liệu và tuân thủ chính sách bảo mật. Không xuất raw authorization metadata hoặc token để giải thích UNAUTHENTICATED.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đếm status theo từng message | Tăng counter trong onNext. | Ghi một terminal status cho mỗi RPC; message metric riêng. |
| CANCELLED bị đếm hai lần | onCancel và close đều tăng counter. | Dùng AtomicBoolean/lifecycle recorder idempotent. |
| Server và client status không giống nhau | Hai phía quan sát khác ranh giới và thời điểm. | Giữ metric riêng; đối chiếu trace và deadline context. |
| Mọi lỗi đều bị gộp thành INTERNAL | Exception mapping quá tổng quát. | Map lỗi nghiệp vụ và lỗi hạ tầng sang status đúng. |
| Coi mọi status khác OK là sự cố nghiêm trọng | Một số status là kết quả nghiệp vụ bình thường. | Alert theo method, baseline và SLO. |
| Retry làm client thấy OK dù server có lỗi | Attempt lỗi trước được retry thành công. | Theo dõi logical call và attempt riêng. |
| Status metric có cardinality cao | Gắn description hoặc ID vào label. | Chỉ dùng service, method, status và dimension hữu hạn. |
| Server không có metric nhưng client có UNAVAILABLE | Call lỗi trước khi tới server. | Theo dõi client-side status và transport/proxy. |

## 17. Bài tập thực hành

1. Viết ServerInterceptor ghi counter theo full service name, method và terminal status.
2. Viết ClientInterceptor ghi status cuối ở client và giữ metric direction riêng.
3. Kiểm thử OK, NOT_FOUND, INVALID_ARGUMENT, UNAVAILABLE, CANCELLED và DEADLINE_EXCEEDED.
4. Tạo PromQL cho status rate, success rate và error ratio theo service/method.
5. Kiểm thử race onCancel/close để xác minh mỗi RPC chỉ tạo một terminal sample.
6. Bật retry cho một unary read idempotent; so sánh client logical status với server attempt status.
7. Gọi streaming RPC nhiều message; xác minh status counter chỉ tăng khi toàn stream kết thúc.
8. Tạo dashboard phân biệt caller/request errors, availability errors, deadline và authentication errors.

Sau bài này, bạn cần biết thu thập status distribution theo service/method, hiểu khác biệt giữa status client và server, tránh đếm trùng khi cancellation, và đọc tỷ lệ lỗi trong ngữ cảnh request rate, latency, retry và loại RPC. Phân phối status rõ ràng giúp đội vận hành xác định đúng lớp cần điều tra trong hệ thống Spring gRPC mà không làm metrics backend quá tải vì cardinality.
