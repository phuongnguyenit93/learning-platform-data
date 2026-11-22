# Deadline exceeded và cancellation

Deadline và cancellation đều có thể kết thúc một RPC trước khi caller nhận được kết quả mong muốn, nhưng chúng mô tả hai tín hiệu khác nhau. Deadline đặt giới hạn thời gian cho call; cancellation báo rằng call không còn cần tiếp tục. Khi deadline hết hạn, gRPC hủy call và client thường nhận status DEADLINE_EXCEEDED. Khi caller chủ động hủy, client thường nhận CANCELLED. Ở server, cả hai trường hợp đều có thể xuất hiện như một tín hiệu cancellation của context hoặc listener.

**Deadline exceeded và cancellation** trong observability là theo dõi số call hết deadline, số call bị hủy, thời điểm tín hiệu đến server và thời gian công việc thực sự dừng/cleanup. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là không nhầm status client với tín hiệu cancellation server, đo đúng terminal event và lần theo deadline qua chuỗi downstream.

## 1. Deadline và cancellation khác nhau ở mục đích

- **Deadline** là thời điểm tuyệt đối mà RPC không còn được phép tiếp tục chờ kết quả. Client đặt deadline hoặc timeout; gRPC tính thời gian còn lại khi call chạy.
- **Cancellation** là tín hiệu kết thúc sớm một call vì caller không còn quan tâm, parent call bị hủy, deadline hết hạn hoặc transport không còn khả dụng.
- **DEADLINE_EXCEEDED** là status client thường quan sát khi deadline của RPC hết hạn trước khi hoàn tất.
- **CANCELLED** là status client thường quan sát khi call bị hủy chủ động hoặc context cha bị hủy trước khi deadline kết thúc.

Deadline có thể kích hoạt cancellation. Vì vậy, deadline expiry và cancellation có quan hệ nhân quả nhưng không đồng nghĩa. Một call có thể bị cancel trước deadline; một call có deadline nhưng hoàn tất bình thường sẽ không bị cancel.

Ví dụ:

| Tình huống | Client thường thấy | Server có thể quan sát |
| --- | --- | --- |
| Client chủ động gọi cancel trước deadline | CANCELLED | Context bị cancel, listener nhận onCancel. |
| Deadline hết trước khi server hoàn tất | DEADLINE_EXCEEDED | Context bị cancel, listener nhận onCancel. |
| Parent RPC bị cancel khi child RPC đang chạy | Parent và child thường kết thúc CANCELLED ở phía client tương ứng | Child server nhận cancellation signal. |
| Kết nối bị đứt khi call đang chạy | Thường là UNAVAILABLE hoặc lỗi transport tùy tình huống | Server có thể nhận cancellation/disconnect nếu phát hiện được. |
| RPC hoàn tất trước deadline | OK hoặc status nghiệp vụ | Server đóng call bình thường. |

Không suy ra nguyên nhân chỉ từ một metric server-side CANCELLED. Server biết call đã bị hủy, nhưng không phải lúc nào cũng biết caller chủ động cancel, deadline vừa hết hay transport bị ngắt.

## 2. Status client và tín hiệu server là hai góc nhìn

Ở client, terminal callback onClose nhận status cuối cùng mà caller quan sát được. Đây là nguồn đáng tin cậy để đếm DEADLINE_EXCEEDED và CANCELLED theo đúng status client.

Ở server, hai điểm thường được dùng để phát hiện call bị hủy:

- ServerCall.Listener.onCancel(): transport thông báo peer đã hủy hoặc call không còn hoạt động.
- Context.CancellationListener: context của RPC bị hủy; phù hợp để thông báo cho công việc bất đồng bộ đang chạy.

Hai callback server này không phải hai lần cancellation độc lập. Chọn một ranh giới làm nguồn metric chính cho mỗi RPC; có thể dùng listener khác để dừng worker nhưng phải tránh đếm cùng một call hai lần.

Khi onCancel xảy ra, có thể kiểm tra deadline của Context để biết deadline đã hết tại thời điểm quan sát hay chưa. Đây chỉ là tín hiệu hỗ trợ phân tích, không phải bằng chứng tuyệt đối về nguyên nhân: explicit cancel có thể đến đúng lúc deadline đã hết, và transport disconnect cũng có thể xảy ra đồng thời. Dùng nhãn như deadline_expired_at_observation thay vì gắn nhãn nguyên nhân chắc chắn.

## 3. Vì sao phải theo dõi cả số lượng và tỷ lệ?

Một counter cho biết tổng số call kết thúc bằng status; rate cho biết tốc độ xuất hiện trong một cửa sổ; error ratio đặt số lỗi cạnh tổng số call. Ba cách nhìn trả lời các câu hỏi khác nhau:

| Chỉ số | Câu hỏi |
| --- | --- |
| Deadline exceeded count | Có bao nhiêu call hết deadline? |
| Deadline exceeded rate | Trong vài phút gần đây, lỗi này xuất hiện nhanh đến mức nào? |
| Deadline exceeded ratio | Bao nhiêu phần trăm call của method bị hết deadline? |
| Client cancelled count | Có bao nhiêu call bị caller hủy? |
| Server cancellation observed | Server đã nhận bao nhiêu tín hiệu cancellation? |
| Cancellation cleanup duration | Sau tín hiệu cancel, server mất bao lâu để dừng công việc và cleanup? |

Không gộp DEADLINE_EXCEEDED, CANCELLED và UNAVAILABLE thành một counter generic timeout. UNAVAILABLE thường liên quan khả năng phục vụ/transport; CANCELLED liên quan lifecycle call; DEADLINE_EXCEEDED thể hiện ngân sách thời gian đã hết.

## 4. Định nghĩa metric theo ranh giới

Một bộ metric có thể dùng:

~~~text
grpc.client.calls
  type: Counter
  tags: service, method, status

grpc.server.calls.cancel.observed
  type: Counter
  tags: service, method, deadline_expired_at_observation

grpc.server.cancel.cleanup.duration
  type: Timer
  tags: service, method

grpc.server.calls.inflight
  type: Gauge
  tags: service, method
~~~

Client counter đếm terminal status mà client nhận. Server cancellation counter đếm tín hiệu server quan sát; nó không phải bản sao chính xác của client CANCELLED/DEADLINE_EXCEEDED. Cleanup Timer đo khoảng từ lúc server nhận cancellation tới lúc công việc thuộc RPC đã dừng và resource được giải phóng. In-flight gauge giúp nhận ra call còn bị giữ sau khi caller đã rời đi.

Labels nên có tập giá trị hữu hạn:

- service: full Protobuf service name.
- method: tên method.
- status: một trong các gRPC status code.
- deadline_expired_at_observation: true/false/unknown nếu thực sự cần phân tích.

Không đưa request ID, trace ID, user ID, deadline timestamp, exception message hoặc metadata tùy ý vào labels. Những dữ liệu chi tiết thuộc trace/log.

## 5. Đếm terminal status phía client

ClientInterceptor có thể đếm status khi listener nhận onClose. Ví dụ dùng Micrometer Counter:

~~~java
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

public final class DeadlineStatusClientInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public DeadlineStatusClientInterceptor(MeterRegistry registry) {
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
~~~

onClose là terminal callback của ClientCall; interceptor đếm tại đây để mỗi logical call có một status cuối ở ranh giới quan sát này. Nếu instrumentation nằm bên trong hoặc bên ngoài retry layer, semantics có thể là một logical call hoặc một attempt. Xác minh vị trí interceptor và retry implementation trước khi gọi metric này là attempt count.

Gắn interceptor vào channel qua ManagedChannelBuilder.intercept hoặc extension point mà Spring gRPC starter cung cấp. Nếu starter quản lý channel, không tạo channel thứ hai chỉ để gắn metrics.

## 6. Quan sát cancellation phía server

ServerInterceptor có thể đếm tín hiệu onCancel và kiểm tra deadline của context tại thời điểm đó:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.TimeUnit;

public final class ServerCancellationMetricsInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;

    public ServerCancellationMetricsInterceptor(
            MeterRegistry registry) {
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

        Context rpcContext = Context.current();
        Deadline deadline = rpcContext.getDeadline();

        ServerCall.Listener<ReqT> listener =
                next.startCall(call, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                boolean expired = deadline != null
                        && deadline.isExpired();
                registry.counter(
                        "grpc.server.calls.cancel.observed",
                        "service", service,
                        "method", method,
                        "deadline_expired_at_observation",
                        deadline == null ? "unknown"
                                : Boolean.toString(expired)
                ).increment();
                super.onCancel();
            }
        };
    }
}
~~~

Metric này có tên cancel.observed để thể hiện đúng điều server biết. Nhãn deadline_expired_at_observation chỉ mô tả trạng thái của Deadline tại thời điểm callback; không đổi nó thành source=deadline một cách tuyệt đối. Nếu muốn phân loại nguyên nhân chính xác hơn, đối chiếu status client hoặc trace.

Interceptor phải được đăng ký vào server do Spring gRPC starter quản lý. Nếu ứng dụng đã có interceptor tập trung đếm terminal status, hãy tích hợp callback cancellation vào cùng lifecycle recorder để tránh hai metric cùng được diễn giải là một tổng số cancellation.

## 7. Dừng công việc bất đồng bộ khi RPC bị hủy

Nhận cancellation signal không tự động dừng mọi công việc do ứng dụng tạo ra. Một database query, executor task, message subscription hoặc downstream RPC có thể tiếp tục chạy nếu handler không truyền tín hiệu tới nó.

Trong handler, đăng ký Context.CancellationListener và cleanup tài nguyên:

~~~java
Context rpcContext = Context.current();
AtomicBoolean stopped = new AtomicBoolean();

Context.CancellationListener cancellationListener = ignored -> {
    if (stopped.compareAndSet(false, true)) {
        worker.cancel(true);
        downstreamCall.cancel(
                "Parent RPC cancelled",
                null);
    }
};

rpcContext.addListener(cancellationListener, Runnable::run);

try {
    startWork();
} finally {
    rpcContext.removeListener(cancellationListener);
    cleanupResources();
}
~~~

Đây là skeleton minh họa; worker và downstreamCall phải được tạo, lưu và quản lý đúng lifecycle trước khi listener có thể dùng chúng. Trong code thực tế, bảo vệ race khi cancellation đến trước khi handle được gán: lưu cờ cancelled, rồi hủy handle ngay khi handle xuất hiện. Cleanup phải idempotent vì nhiều đường terminal có thể cạnh tranh.

Đối với blocking operation, interrupt chỉ có tác dụng nếu API và code thực sự phản ứng với interrupt. JDBC driver, native call hoặc thư viện bên thứ ba có thể không dừng ngay. Dùng API cancel/close riêng của resource nếu có, đặt timeout ở dependency và kiểm tra worker đã thoát trước khi xem cleanup hoàn tất.

## 8. Truyền deadline còn lại tới downstream RPC

Một request thường đi qua nhiều service. Nếu mỗi service đặt một timeout mới bằng toàn bộ timeout ban đầu, tổng thời gian chuỗi có thể vượt ngân sách caller. Downstream nên dùng phần deadline còn lại:

~~~java
Deadline parentDeadline = Context.current().getDeadline();
if (parentDeadline == null) {
    return inventoryStub.getStock(request);
}

long remainingNanos =
        parentDeadline.timeRemaining(TimeUnit.NANOSECONDS);

if (remainingNanos <= 0) {
    throw Status.DEADLINE_EXCEEDED
            .withDescription("Parent RPC deadline đã hết")
            .asRuntimeException();
}

return inventoryStub
        .withDeadlineAfter(remainingNanos, TimeUnit.NANOSECONDS)
        .getStock(request);
~~~

gRPC Java có cơ chế Context/deadline propagation trong các call phù hợp, nhưng khi tạo task nền, đổi executor hoặc chủ động dựng call độc lập, phải xác minh context hiện tại được truyền và deadline được giữ. Không đặt lại một timeout đầy đủ cho mỗi hop. Nếu cần dành thời gian cho bước tổng hợp/response cuối, trừ phần ngân sách dự phòng trước khi gọi downstream.

Khi parent hết deadline, child RPC đang chạy cần nhận cancellation. Kiểm thử cả deadline propagation lẫn child cleanup; chỉ kiểm tra client parent nhận DEADLINE_EXCEEDED chưa chứng minh downstream đã dừng.

## 9. Prometheus: deadline exceeded và cancellation rate

Giả sử Micrometer Counter grpc.client.calls được export thành grpc_client_calls_total:

~~~promql
# Client deadline exceeded mỗi giây theo service/method.
sum by (service, method) (
  rate(grpc_client_calls_total{status="DEADLINE_EXCEEDED"}[5m])
)
~~~

Client cancelled mỗi giây:

~~~promql
sum by (service, method) (
  rate(grpc_client_calls_total{status="CANCELLED"}[5m])
)
~~~

Tỷ lệ deadline exceeded trên tổng call:

~~~promql
sum by (service, method) (
  rate(grpc_client_calls_total{status="DEADLINE_EXCEEDED"}[5m])
)
/
sum by (service, method) (
  rate(grpc_client_calls_total[5m])
)
~~~

Tỷ lệ cancellation signal được server quan sát:

~~~promql
sum by (service, method) (
  rate(grpc_server_calls_cancel_observed_total[5m])
)
~~~

Tên metric/label cuối cùng phụ thuộc registry và exporter; xác minh endpoint scrape trước khi dùng query. Server cancellation observed không nên chia cho client CANCELLED rồi coi kết quả là tỷ lệ đối chiếu chính xác, vì server signal có thể bao gồm deadline expiry và transport disconnect.

Nếu mẫu số bằng 0, dashboard nên hiển thị no traffic. Alert nên kết hợp tỷ lệ với số call tối thiểu để tránh báo động từ một vài request.

## 10. Đo thời gian cleanup sau cancellation

Một server có thể nhận cancellation ngay nhưng worker vẫn chạy thêm nhiều giây. Đây là khoảng thời gian quan trọng vì công việc đã không còn giá trị với caller nhưng vẫn tiêu thụ CPU, thread, connection hoặc quota downstream.

Đo cleanup duration từ lúc cancellation được quan sát tới khi:

1. Worker đã dừng hoặc xác nhận không còn xử lý.
2. Downstream call đã được cancel/terminal.
3. Subscription, cursor, statement và resource thuộc call đã được giải phóng.
4. In-flight gauge đã giảm.

Timer có thể ghi một sample cho mỗi call bị cancel. Nếu cần theo dõi task cleanup đang chạy, dùng LongTaskTimer. Không dừng timer ngay khi gọi worker.cancel(true); phải chờ tới lúc công việc thực sự kết thúc hoặc cleanup đạt điều kiện hoàn tất.

## 11. Đọc deadline/cancellation cùng latency và status

Các tín hiệu cần được đọc cùng nhau:

| Dấu hiệu | Khả năng | Điều tra |
| --- | --- | --- |
| DEADLINE_EXCEEDED tăng, p99 tăng | Service hoặc dependency chậm hơn deadline budget. | Latency theo method, downstream spans, queue. |
| DEADLINE_EXCEEDED tăng, server duration thấp | Client budget có thể đã tiêu hao trước khi request tới server hoặc network/queue phía client chậm. | Client span, deadline còn lại khi server bắt đầu. |
| CANCELLED tăng, DEADLINE_EXCEEDED ổn định | Caller bỏ call, UI/request lifecycle đổi hoặc parent bị hủy. | Client cancellation source, parent trace và disconnect. |
| Server cancel observed tăng nhưng client CANCELLED không tăng tương ứng | Deadline expiry hoặc transport disconnect có thể đóng góp vào server signal. | Client status, deadline expiry tại callback và proxy logs. |
| Cleanup duration cao | Worker/dependency không phản ứng nhanh với cancellation. | Interrupt handling, driver cancel, executor queue và child RPC. |
| In-flight không giảm sau cancel | Listener/worker/resource bị giữ hoặc terminal cleanup thiếu. | Thread dump, active task và cleanup path. |

Không tăng deadline chỉ để làm dashboard xanh. Deadline cần phản ánh SLO caller và ngân sách của toàn chuỗi; tăng quá mức có thể làm request giữ tài nguyên lâu hơn khi hệ thống đã suy giảm.

## 12. Trace và log để tìm nguyên nhân

Metric cho biết xu hướng; trace giúp lần theo một call cụ thể:

- Ghi deadline/timeout được cấu hình ở client và thời gian còn lại khi mỗi service bắt đầu xử lý.
- Tạo child span cho downstream RPC và thể hiện thời gian chờ từng dependency.
- Ghi terminal status ở mỗi span, đồng thời đánh dấu cancellation observed ở server.
- Ghi thời điểm worker bắt đầu cleanup và thời điểm cleanup hoàn tất.
- Dùng trace ID trong log để liên kết client, parent server và child service.

Không ghi token, authorization metadata, payload nhạy cảm hoặc toàn bộ exception description vào metric/log. Trace sampling cần đủ bao phủ lỗi hiếm nhưng nghiêm trọng; có thể ưu tiên sample các call DEADLINE_EXCEEDED hoặc cleanup duration vượt ngưỡng.

## 13. Kiểm thử deadline exceeded và cancellation

Dùng in-process gRPC server/channel và latch để điều khiển thời điểm handler bắt đầu, bị hủy và kết thúc:

1. **Explicit cancel:** client gọi cancel khi handler đang chờ; client nhận CANCELLED, server nhận cancellation signal và worker dừng.
2. **Deadline expiry:** client đặt deadline ngắn hơn thời gian handler xử lý; client nhận DEADLINE_EXCEEDED, server nhận cancellation signal và cleanup hoàn tất.
3. **Parent-child propagation:** parent RPC gọi child RPC; hủy hoặc hết deadline parent và xác minh child nhận cancellation.
4. **Deadline budget:** xác minh downstream nhận phần thời gian còn lại thay vì timeout ban đầu được cấp lại.
5. **Race khi tạo handle:** cancellation tới trước khi child call/worker handle được lưu; khi handle xuất hiện, nó phải bị hủy ngay.
6. **Cleanup idempotency:** cho onCancel và close chạy gần nhau; xác minh cleanup và metric chỉ ghi một lần.
7. **Blocking dependency:** mô phỏng API không phản ứng với interrupt; xác minh timeout/cancel API riêng và cleanup policy.
8. **Client/server metric:** so sánh DEADLINE_EXCEEDED phía client với cancellation observed phía server, không giả định chúng có cùng status label.

Dùng CountDownLatch hoặc barrier thay cho Thread.sleep. Mỗi latch phải có timeout và được mở trong teardown để test thất bại không giữ worker vô hạn. Bổ sung một số test TCP/TLS để kiểm tra peer disconnect; in-process transport không mô phỏng đầy đủ network partition hoặc proxy timeout.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gộp CANCELLED và DEADLINE_EXCEEDED | Xem mọi cancellation là timeout. | Giữ client terminal status riêng; server signal có metric riêng. |
| Server cancellation counter được xem là explicit user cancel | onCancel không xác định duy nhất nguyên nhân. | Đặt tên cancel_observed và đối chiếu client status/trace. |
| Deadline downstream dài hơn parent | Mỗi hop cấp lại timeout đầy đủ. | Truyền deadline còn lại và dành ngân sách cho bước cuối. |
| Client đã timeout nhưng worker vẫn chạy | Application không truyền cancellation vào task/resource. | Context listener, cancel API, interrupt hợp tác và cleanup. |
| Cleanup duration luôn rất nhỏ | Timer dừng ngay khi gửi cancel thay vì khi worker dừng. | Ghi tới thời điểm cleanup thực sự hoàn tất. |
| CANCELLED bị đếm hai lần | onCancel và Context listener cùng tăng một counter. | Chọn một metric boundary hoặc dùng lifecycle guard chung. |
| Retry chạy sau deadline | Retry policy không bị giới hạn bởi ngân sách tổng hoặc application tự retry sai. | Giữ deadline tổng, giới hạn attempt và backoff. |
| Tăng timeout che khuất dependency chậm | Alert chỉ dựa vào deadline status. | Đọc deadline cùng latency histogram và downstream spans. |

## 15. Bài tập thực hành

1. Viết ClientInterceptor đếm terminal status DEADLINE_EXCEEDED và CANCELLED theo service/method.
2. Viết ServerInterceptor đếm cancellation observed, kèm deadline_expired_at_observation có giá trị true/false/unknown.
3. Tạo một handler bất đồng bộ; đăng ký Context.CancellationListener để hủy worker và downstream RPC.
4. Truyền deadline còn lại từ parent tới child RPC và kiểm tra child không vượt ngân sách parent.
5. Đo cancellation cleanup duration từ lúc nhận tín hiệu tới khi resource được giải phóng.
6. Viết PromQL cho deadline rate, cancellation rate và deadline ratio theo method.
7. Kiểm thử explicit cancel, deadline expiry, parent-child cancellation và race khi handle chưa được tạo.
8. Tạo dashboard kết hợp deadline status, server cancellation observed, p99 latency, in-flight calls và cleanup duration.

Sau bài này, bạn cần phân biệt status deadline/cancel ở client với cancellation signal ở server, truyền deadline còn lại qua downstream và xác minh worker/resource thực sự dừng. Kết hợp status counters, cleanup duration, latency và trace giúp đội vận hành phát hiện call hết ngân sách thời gian cũng như công việc tiếp tục chạy sau khi caller đã hủy trong hệ thống Spring gRPC.
