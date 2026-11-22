# Active stream và stream duration

Với unary RPC, một call thường kết thúc nhanh sau một request và một response. Với server-streaming, client-streaming hoặc bidirectional streaming, call có thể giữ kết nối và tài nguyên trong nhiều phút hoặc nhiều giờ. Chỉ đo request rate và latency của các call đã hoàn tất sẽ bỏ sót những stream đang mở, bị kẹt hoặc chiếm nhiều tài nguyên.

**Active stream và stream duration** là hai góc nhìn bổ sung: active stream cho biết hiện có bao nhiêu stream đang tồn tại; stream duration đo thời gian từ khi stream bắt đầu tới khi kết thúc. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là đo đúng lifecycle của streaming call, cập nhật gauge đúng một lần và diễn giải duration mà không nhầm với latency từng message.

## 1. Phân biệt active stream và stream duration

- **Active stream** là số streaming RPC đã bắt đầu nhưng chưa đi vào terminal state tại thời điểm quan sát.
- **Stream duration** là thời gian từ khi call bắt đầu ở ranh giới instrumentation tới khi call hoàn tất, lỗi hoặc bị hủy.
- **Message latency** là thời gian gửi/nhận hoặc xử lý một message; không đồng nghĩa với stream duration.
- **Time to first message** là thời gian từ lúc mở stream tới message đầu tiên; cũng là một metric riêng.

Ví dụ một subscription mở trong 30 phút và nhận 2.000 message:

- Active stream tăng 1 khi subscription bắt đầu và giảm 1 khi call kết thúc.
- Stream duration ghi một quan sát khoảng 30 phút khi call kết thúc.
- Message count tăng theo số message, không làm active stream tăng.
- Time to first message ghi một quan sát khi message đầu tiên được gửi/nhận.

Một stream đang mở chưa có duration sample trong Timer thông thường, vì Timer ghi nhận khi sample được dừng. Vì vậy, cần active stream gauge để nhìn thấy các call hiện còn tồn tại. Nếu muốn quan sát tuổi của những stream đang mở, có thể bổ sung LongTaskTimer hoặc metric age riêng.

## 2. Xác định loại RPC cần theo dõi

gRPC định nghĩa bốn loại method trong Protobuf:

| Loại RPC | Hướng message | Có phải stream? | Lifecycle |
| --- | --- | --- | --- |
| Unary (MethodType.UNARY) | Một request, một response | Không | Thường ngắn; không đưa vào active stream gauge. |
| Client streaming (MethodType.CLIENT_STREAMING) | Nhiều request, một response | Có | Client gửi nhiều message rồi half-close; server vẫn có thể xử lý trước khi trả response cuối. |
| Server streaming (MethodType.SERVER_STREAMING) | Một request, nhiều response | Có | Server gửi nhiều message rồi đóng response stream. |
| Bidirectional streaming (MethodType.BIDI_STREAMING) | Nhiều message hai chiều | Có | Hai phía trao đổi độc lập cho tới khi call kết thúc. |

Active stream metric nên chỉ tính ba loại streaming. Nếu đếm mọi RPC, đặt tên rõ là active calls thay vì active streams. Tên metric và dashboard cần thống nhất với định nghĩa này.

Lấy loại method từ Protobuf MethodDescriptor thay vì suy ra từ tên method hoặc số message đã quan sát:

~~~java
MethodDescriptor.MethodType type = call.getMethodDescriptor().getType();
boolean streaming = type != MethodDescriptor.MethodType.UNARY;
~~~

## 3. Lifecycle của một stream ở phía server

Ở server, interceptor nhận call trước khi service xử lý. Call kết thúc bình thường khi server đóng ServerCall với terminal status. Nếu peer hủy hoặc mất kết nối, listener có thể nhận onCancel. Hai đường này có thể xảy ra gần nhau, vì vậy việc giảm active count và ghi duration phải idempotent.

~~~mermaid
flowchart TD
    A[Server nhận streaming RPC] --> B[active streams +1]
    B --> C[Timer sample bắt đầu]
    C --> D{Call terminal?}
    D -->|Server close| E[Record status và duration]
    D -->|Peer cancel/disconnect| E
    E --> F[active streams -1]
    F --> G[Cleanup hoàn tất đúng một lần]
~~~

Không giảm active stream ở ServerCall.Listener.onHalfClose. Với client-streaming và bidirectional streaming, onHalfClose chỉ cho biết client đã ngừng gửi request message; server có thể vẫn đang xử lý hoặc tiếp tục gửi response. Active stream chỉ giảm khi toàn bộ RPC kết thúc.

## 4. Chọn metric phù hợp

Một bộ metric cơ bản có thể gồm:

| Metric | Loại | Tags | Ý nghĩa |
| --- | --- | --- | --- |
| grpc.server.active.streams | Gauge | service, method, rpc_type | Số stream hiện đang hoạt động ở server. |
| grpc.server.stream.duration | Timer histogram | service, method, rpc_type, status | Thời gian sống của stream đã kết thúc. |
| grpc.client.active.streams | Gauge | service, method, rpc_type | Số stream client đang giữ. |
| grpc.client.stream.duration | Timer histogram | service, method, rpc_type, status | Thời gian client quan sát từ start tới onClose. |
| grpc.server.stream.messages.received | Counter | service, method | Tổng request message server nhận. |
| grpc.server.stream.messages.sent | Counter | service, method | Tổng response message server gửi. |

Không bắt buộc triển khai tất cả ngay từ đầu. Active gauge và duration histogram thường là cặp tối thiểu để quan sát lifecycle. Message counter hoặc time-to-first-message chỉ thêm khi có câu hỏi vận hành cụ thể.

Giữ metric client và server riêng. Client có thể đã mở call nhưng server chưa nhận được; server có thể đã đóng call nhưng client chưa quan sát terminal callback do transport. Hai gauge vì vậy không nhất thiết bằng nhau.

## 5. Đo active stream ở server bằng ServerInterceptor

Ví dụ sau dùng Micrometer. Interceptor bỏ qua unary RPC, đăng ký một gauge cho từng service/method/type và chỉ giảm gauge, ghi Timer một lần khi call terminal:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class ActiveStreamServerInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;
    private final ConcurrentMap<String, AtomicInteger> activeByMethod =
            new ConcurrentHashMap<>();

    public ActiveStreamServerInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    private AtomicInteger activeCounter(
            String service, String method, String rpcType) {
        String key = service + "|" + method + "|" + rpcType;
        return activeByMethod.computeIfAbsent(key, ignored -> {
            AtomicInteger count = new AtomicInteger();
            Gauge.builder(
                            "grpc.server.active.streams",
                            count,
                            AtomicInteger::get)
                    .description("Số streaming RPC đang hoạt động ở server")
                    .tags(
                            "service", service,
                            "method", method,
                            "rpc_type", rpcType)
                    .register(registry);
            return count;
        });
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        MethodDescriptor<ReqT, RespT> descriptor =
                call.getMethodDescriptor();
        MethodDescriptor.MethodType type = descriptor.getType();
        if (type == MethodDescriptor.MethodType.UNARY) {
            return next.startCall(call, headers);
        }

        String fullMethod = descriptor.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);
        String rpcType = type.name().toLowerCase(Locale.ROOT);

        AtomicInteger active = activeCounter(service, method, rpcType);
        active.incrementAndGet();

        Timer.Sample sample = Timer.start(registry);
        AtomicBoolean finished = new AtomicBoolean();

        java.util.function.Consumer<Status> finish = status -> {
            if (finished.compareAndSet(false, true)) {
                active.decrementAndGet();
                Timer timer = Timer.builder("grpc.server.stream.duration")
                        .description("Thời lượng một streaming RPC phía server")
                        .publishPercentileHistogram()
                        .serviceLevelObjectives(
                                Duration.ofSeconds(1),
                                Duration.ofSeconds(5),
                                Duration.ofSeconds(15),
                                Duration.ofSeconds(30),
                                Duration.ofMinutes(1),
                                Duration.ofMinutes(5),
                                Duration.ofMinutes(15),
                                Duration.ofHours(1))
                        .tags(
                                "service", service,
                                "method", method,
                                "rpc_type", rpcType,
                                "status", status.getCode().name())
                        .register(registry);
                sample.stop(timer);
            }
        };

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        finish.accept(status);
                        super.close(status, trailers);
                    }
                };

        try {
            ServerCall.Listener<ReqT> listener =
                    next.startCall(monitoredCall, headers);
            return new ForwardingServerCallListener
                    .SimpleForwardingServerCallListener<>(listener) {
                @Override
                public void onCancel() {
                    finish.accept(Status.CANCELLED);
                    super.onCancel();
                }
            };
        } catch (RuntimeException failure) {
            finish.accept(Status.fromThrowable(failure));
            throw failure;
        }
    }
}
~~~

Các điểm quan trọng:

- Gauge được đăng ký một lần cho mỗi tổ hợp service/method/rpc_type; map giữ strong reference tới AtomicInteger để giá trị gauge còn sống.
- Mỗi call tăng active trước khi chuyển tới service handler.
- ServerCall.close ghi status và duration khi server đóng call.
- onCancel ghi nhận cancellation nếu peer hủy trước khi server close.
- AtomicBoolean ngăn decrement và Timer record hai lần khi hai terminal path cạnh tranh.
- Nếu khởi tạo listener ném RuntimeException đồng bộ, catch block vẫn giảm active và ghi terminal duration.

Đây là ví dụ instrumentation phía server; khi dùng starter Spring gRPC, đăng ký interceptor qua extension point của starter hoặc server builder mà starter quản lý. Không tạo server riêng chỉ để cài metric interceptor.

## 6. Đo active stream ở client

Client-side stream bắt đầu tại ClientCall.start và kết thúc khi listener nhận onClose. ClientInterceptor có thể dùng cùng nguyên tắc:

1. Lấy full method name và MethodType từ MethodDescriptor.
2. Bỏ qua unary method nếu metric chỉ dành cho stream.
3. Tăng gauge trước khi gọi start trên ClientCall.
4. Tạo Timer.Sample cho client-observed stream duration.
5. Bọc ClientCall.Listener.onClose để giảm gauge và ghi duration/status.
6. Dùng AtomicBoolean để bảo đảm chỉ ghi terminal một lần nếu callback hoặc lỗi đồng bộ cạnh tranh.

Client metric đo từ phía caller, bao gồm thời gian transport và chờ response. Nó có thể dài hơn server duration hoặc kết thúc với status khác server-side metric. Đặt tên riêng grpc.client.active.streams và grpc.client.stream.duration; không cộng trực tiếp với metric server.

Với client streaming, client có thể gọi halfClose sau khi gửi xong request message nhưng vẫn đang chờ response. Không giảm active gauge ở halfClose; chỉ giảm khi onClose báo call đã kết thúc.

## 7. LongTaskTimer cho tuổi của stream đang mở

Timer histogram thông thường chỉ nhận duration khi stream kết thúc. Để quan sát thời lượng của các stream còn đang chạy, Micrometer cung cấp LongTaskTimer:

~~~java
LongTaskTimer activeDuration = LongTaskTimer.builder(
                "grpc.server.stream.active.duration")
        .description("Thời gian đã trôi qua của streaming RPC còn hoạt động")
        .tags(
                "service", service,
                "method", method,
                "rpc_type", rpcType)
        .register(registry);

LongTaskTimer.Sample activeSample = activeDuration.start();

// Khi stream terminal:
activeSample.stop();
~~~

LongTaskTimer theo dõi số task đang chạy và thời lượng của chúng trong khi còn active; khi stop, task rời khỏi tập active. Có thể dùng nó thay cho gauge thủ công hoặc kết hợp với gauge nếu dashboard cần metric tên/semantics rõ ràng. Tránh ghi cùng một khái niệm hai lần rồi cộng các series.

Nếu chỉ cần cảnh báo stream quá tuổi, LongTaskTimer hoặc một cơ chế theo dõi age có thể giúp phát hiện sớm hơn Timer duration hoàn tất. Cần xác định stream dài là bất thường hay được thiết kế như subscription lâu dài; không cảnh báo chỉ vì một stream hợp lệ tồn tại nhiều giờ.

## 8. Đừng nhầm active stream với message flow

Một stream có thể active nhưng không có message trong thời gian dài. Điều này có thể là bình thường nếu stream chờ event, hoặc bất thường nếu producer bị treo. Active count không phân biệt được hai tình huống.

Để hiểu message flow, có thể bổ sung:

- Message sent/received counter.
- Time-to-first-message timer.
- Inter-message gap hoặc thời điểm message gần nhất.
- Backpressure/ready state nếu ứng dụng cần quan sát flow control.
- Stream age và thời gian không có message.

Không cập nhật gauge active theo mỗi message. Một stream gửi 1.000 message vẫn là một active stream. Với bidirectional stream, message hai chiều có thể được đếm ở hai metric riêng.

## 9. Truy vấn active stream và stream duration trong Prometheus

Micrometer Prometheus registry có thể chuẩn hóa tên gauge thành grpc_server_active_streams và Timer histogram thành grpc_server_stream_duration_seconds_bucket. Tên thực tế phụ thuộc registry/exporter; hãy kiểm tra endpoint scrape trước khi sử dụng.

Tổng active stream theo service/method:

~~~promql
sum by (service, method, rpc_type) (
  grpc_server_active_streams
)
~~~

Stream duration p95 trong 15 phút:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, method, rpc_type) (
    rate(grpc_server_stream_duration_seconds_bucket[15m])
  )
)
~~~

Số active stream cao nhất trong 10 phút:

~~~promql
max_over_time(grpc_server_active_streams[10m])
~~~

LongTaskTimer export series có tên khác với Gauge/Timer thường; truy vấn theo tên thực tế do exporter tạo ra. Không giả định mọi registry đặt tên giống nhau.

Duration histogram chỉ chứa stream đã kết thúc trong cửa sổ quan sát. Một stream tồn tại 2 giờ nhưng chưa đóng không đóng góp sample duration cho tới khi terminal. Vì vậy, không dùng p95 duration một mình để kết luận không có stream bị treo.

## 10. Đặt cảnh báo theo tuổi và số lượng stream

Một active stream count cao không tự động là sự cố. Một subscription service có thể được thiết kế giữ hàng nghìn stream. Cần xác định baseline và capacity:

| Tín hiệu | Có thể chỉ ra | Cách đánh giá |
| --- | --- | --- |
| Active stream tăng nhanh | Client reconnect storm hoặc nhiều subscriber mới. | So sánh connect rate, disconnect rate và deployment events. |
| Active stream cao kéo dài | Tải nền lớn hoặc stream không được cleanup. | So với capacity, memory, worker và baseline theo giờ. |
| Stream age p95 tăng | Stream cũ tồn tại lâu hơn dự kiến. | Phân biệt subscription dài hạn với call bị kẹt. |
| Active giảm đột ngột | Server restart, network event hoặc client đồng loạt disconnect. | Đối chiếu status, instance health và rollout. |
| Message gap tăng nhưng active ổn định | Producer/dependency ngừng phát message. | Kiểm tra upstream event rate và backpressure. |

Có thể cảnh báo khi active stream vượt ngưỡng trong một khoảng thời gian, hoặc khi stream age vượt policy của method. Dùng ngưỡng riêng theo service/method/rpc_type; một bidirectional session hợp lệ có thể tồn tại lâu hơn server-streaming query.

## 11. Cardinality và chi phí metrics

Active gauge và duration histogram tạo series theo tổ hợp labels. Dùng các giá trị hữu hạn:

- service: full Protobuf service name.
- method: method name.
- rpc_type: client_streaming, server_streaming hoặc bidi_streaming.
- status: chỉ trên duration Timer sau terminal.
- instance/zone: chỉ khi cardinality budget cho phép và cần điều tra theo locality.

Không gắn stream ID, user ID, account ID, tenant ID, request ID hoặc trace ID vào metric labels. Mỗi stream ID mới có thể tạo một series mới, khiến cardinality tăng theo số phiên. Dùng tracing/logging để theo dõi từng stream; metric chỉ tổng hợp theo method và nhóm có kiểm soát.

Gauge phải có một meter identity ổn định cho mỗi nhóm label, không tạo một Gauge mới cho mỗi stream. Nếu đăng ký gauge với object chỉ tồn tại trong scope call, registry có thể không giữ tham chiếu mạnh và giá trị có thể biến mất. Dùng map giữ các AtomicInteger theo method hoặc dùng LongTaskTimer với lifecycle sample cho từng task.

## 12. Kiểm thử active count và duration

Kiểm thử cần điều khiển thời điểm mở và đóng stream bằng latch/barrier, tránh Thread.sleep để đoán lifecycle:

1. Mở server-streaming RPC và chờ server xác nhận handler bắt đầu; active gauge phải tăng một.
2. Giữ stream chưa hoàn tất; xác minh active gauge vẫn là một và completed duration Timer chưa có sample.
3. Đóng stream bình thường; xác minh active gauge về không và duration Timer count tăng đúng một.
4. Hủy stream từ client; xác minh active giảm một, duration được ghi một lần với status phù hợp phía server.
5. Để deadline hết; xác minh cleanup và active count không bị giữ lại.
6. Gửi nhiều message trong cùng stream; xác minh active count không đổi theo message.
7. Mở nhiều stream cùng method; xác minh gauge bằng số stream đang hoạt động và về không sau khi tất cả terminal.
8. Gọi unary method; xác minh nó không làm tăng active stream gauge.
9. Tạo stream dài chưa đóng; xác minh LongTaskTimer/active age quan sát được task còn hoạt động.

Dùng SimpleMeterRegistry để kiểm tra gauge và Timer trong unit/in-process test. Integration test qua TCP/TLS bổ sung xác minh disconnect thực tế và cleanup khi transport bị ngắt. Mọi latch phải có timeout và được giải phóng trong teardown để test thất bại không giữ worker.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Active stream giảm khi client half-close | Coi half-close là terminal của toàn RPC. | Chỉ giảm khi server call close hoặc nhận onCancel. |
| Gauge tăng nhưng không giảm | Bỏ sót cancellation, exception hoặc terminal path. | Gom cleanup vào một hàm idempotent và kiểm thử mọi terminal path. |
| Active count âm hoặc giảm hai lần | onCancel và close cùng decrement. | Dùng AtomicBoolean guard cho từng call. |
| Stream dài không xuất hiện trong duration histogram | Timer chỉ record khi sample stop. | Dùng active gauge hoặc LongTaskTimer để theo dõi stream đang mở. |
| Dashboard coi stream lifetime dài là latency xấu | Trộn unary latency với stream lifetime. | Tách metric và SLO theo rpc_type. |
| Một stream nhiều message làm active count tăng | Đếm message thay vì call. | Tăng active một lần khi bắt đầu và giảm một lần khi terminal. |
| Gauge biến mất hoặc luôn bằng không | Gauge giữ object tham chiếu yếu nhưng object đã bị thu hồi. | Giữ strong reference trong registry map hoặc dùng LongTaskTimer. |
| Cardinality tăng theo subscriber | Gắn stream ID/user ID vào label. | Chỉ dùng service, method và rpc_type; chi tiết đưa vào trace. |

## 14. Bài tập thực hành

1. Viết ServerInterceptor chỉ theo dõi ba loại streaming RPC, không tính unary vào active stream gauge.
2. Đăng ký Gauge theo service/method/rpc_type và giữ object đếm trong map có lifecycle rõ ràng.
3. Ghi stream duration bằng Micrometer Timer khi ServerCall đóng hoặc call bị hủy.
4. Dùng AtomicBoolean bảo đảm active count giảm và Timer record đúng một lần khi onCancel/close cạnh tranh.
5. Bổ sung LongTaskTimer để quan sát stream đang mở lâu hơn ngưỡng dự kiến.
6. Viết test cho complete, error, explicit cancel, deadline expiry, client half-close và nhiều message.
7. Tạo PromQL dashboard cho active streams, stream duration p95 và số active cao nhất trong 10 phút.
8. Kiểm tra label cardinality và xác minh stream ID/user ID không xuất hiện trong metrics.

Sau bài này, bạn cần phân biệt số stream đang hoạt động với thời lượng của stream đã kết thúc, chỉ tính ba loại streaming RPC, và bảo đảm mỗi call tăng/giảm active count đúng một lần. Kết hợp active gauge, Timer histogram, LongTaskTimer và message-level metrics giúp đội vận hành phát hiện stream bị treo, reconnect bất thường hoặc chiếm tài nguyên lâu trong hệ thống Spring gRPC.
