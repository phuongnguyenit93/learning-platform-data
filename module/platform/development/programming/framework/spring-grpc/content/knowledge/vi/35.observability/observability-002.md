# Latency histogram cho unary và streaming

Đếm số RPC cho biết service nhận bao nhiêu call, nhưng không cho biết caller phải chờ bao lâu. Một method có thể giữ nguyên request rate trong khi latency p99 tăng mạnh do database chậm, queue dài hoặc một số instance suy giảm. Histogram latency giúp quan sát phân phối thời gian RPC, so sánh giữa các method và phát hiện phần đuôi chậm mà giá trị trung bình thường che khuất.

**Latency histogram cho unary và streaming** là cách đo thời lượng RPC và phân phối thời lượng đó theo service/method, status và loại RPC. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là định nghĩa đúng khoảng thời gian được đo, cấu hình Micrometer Timer histogram và đọc p95/p99 cho từng method.

## 1. Latency của một RPC được tính từ đâu tới đâu?

Đối với một RPC, thời lượng thường được đo từ lúc call bắt đầu ở ranh giới instrumentation tới khi call đi vào terminal state:

- Client-side duration: từ lúc client bắt đầu call tới khi nhận onClose.
- Server-side duration: từ lúc server interceptor nhận call tới khi server đóng call hoặc nhận cancellation.
- Unary RPC: thời lượng bao gồm xử lý request và tạo response.
- Streaming RPC: thời lượng của cả call từ lúc mở stream tới khi stream hoàn tất, lỗi hoặc bị hủy.

Hai phép đo client và server không nhất thiết bằng nhau. Client-side duration có thể bao gồm thời gian transport, network, queueing và chờ response; server-side duration phản ánh khoảng thời gian call ở phía server theo vị trí interceptor. Khi đối chiếu hai bên, cần xem chúng là hai góc nhìn khác nhau thay vì trừ trực tiếp để suy ra network latency nếu chưa đồng bộ và xác định ranh giới đo.

Với streaming RPC, thời lượng cả stream không giống latency của từng message. Một server-streaming call tồn tại 20 phút và gửi 10.000 message có RPC duration 20 phút; con số này không nói message đầu tiên tới client sau bao lâu hay khoảng cách giữa hai message là bao nhiêu. Nếu cần các câu hỏi đó, phải tạo metric riêng.

## 2. Phân biệt RPC duration, time-to-first-message và message latency

Nên xác định metric theo câu hỏi vận hành:

| Metric | Bắt đầu | Kết thúc | Dùng để trả lời |
| --- | --- | --- | --- |
| RPC duration | Call bắt đầu | Call terminal | Một RPC tồn tại bao lâu? |
| Time to first response | Call bắt đầu | Message response đầu tiên | Client chờ bao lâu để thấy dữ liệu đầu tiên? |
| Inter-message gap | Message trước được gửi/nhận | Message kế tiếp được gửi/nhận | Stream có khoảng ngừng phát dữ liệu bất thường không? |
| Message processing duration | Bắt đầu xử lý một message | Xử lý message kết thúc | Mỗi message cần bao lâu để xử lý? |
| Stream lifetime | Stream được mở | Stream đóng/cancel | Subscription hoặc phiên streaming tồn tại bao lâu? |

Unary RPC thường dùng RPC duration làm latency chính. Với streaming, RPC duration vẫn hữu ích để đo tuổi thọ call và phát hiện stream bị treo hoặc tồn tại lâu bất thường, nhưng không thay thế time-to-first-message hay message processing duration.

Không đặt một histogram chung cho unary duration và stream lifetime rồi diễn giải p99 như cùng một loại trải nghiệm. Stream thường dài hơn nhiều bậc độ lớn. Có thể dùng metric name riêng, hoặc một label rpc_type có tập giá trị hữu hạn như unary, client_streaming, server_streaming, bidi_streaming. Dashboard nên lọc đúng loại trước khi so sánh.

## 3. Vì sao dùng Histogram thay vì chỉ average?

Average là tổng thời lượng chia số call. Một số ít request rất chậm có thể bị che khuất bởi số lượng lớn request nhanh. Histogram phân phối các quan sát vào những bucket theo ngưỡng thời gian, từ đó cho thấy phần đuôi latency.

Ví dụ 1.000 RPC có 990 call hoàn tất trong 40 ms và 10 call mất 3 giây. Average có thể vẫn trông chấp nhận được, nhưng p99 phản ánh nhóm caller chậm. Histogram giữ số lượng quan sát ở từng khoảng để backend có thể tính quantile gần đúng trên cửa sổ thời gian.

| Thống kê | Ý nghĩa | Hạn chế |
| --- | --- | --- |
| Count | Số lần đo được ghi nhận. | Không cho biết thời gian nhanh/chậm. |
| Sum | Tổng thời lượng của các quan sát. | Không mô tả phân phối. |
| Average | Sum / Count. | Che khuất tail latency. |
| p50 | Trung vị; một nửa quan sát không vượt ngưỡng này. | Không phản ánh nhóm chậm nhất. |
| p95 / p99 | Ngưỡng mà 95% / 99% quan sát không vượt qua. | Là ước lượng từ histogram buckets; độ chính xác phụ thuộc bucket boundaries. |

Micrometer Timer phù hợp để ghi duration. Khi bật percentile histogram hoặc cấu hình service-level objectives, Prometheus exporter có thể xuất bucket series để backend tính quantile. Histogram buckets là dữ liệu tổng hợp được cộng gộp giữa nhiều instance; percentile tính từ bucket histogram phù hợp hơn cho tổng hợp service-wide so với việc lấy trung bình các p99 riêng của từng instance.

## 4. Chọn bucket và SLO

Bucket boundaries cần phản ánh thời gian đáp ứng mà service mong muốn. Với unary RPC nội bộ có SLO dưới vài trăm millisecond, bucket nên dày ở vùng thấp và có các ngưỡng cao hơn để quan sát sự cố:

```text
10 ms, 25 ms, 50 ms, 100 ms, 200 ms,
300 ms, 500 ms, 1 s, 2 s, 5 s
```

Đây chỉ là ví dụ; không dùng cùng một bộ bucket cho mọi method. RPC đọc cache, RPC truy vấn database và RPC gọi nhiều service downstream có đặc tính khác nhau. Hãy chọn bucket quanh ngưỡng SLO, ngưỡng cảnh báo và vùng latency thực tế.

Với streaming, bucket duration của stream có thể cần từ vài giây tới hàng giờ. Nếu mục tiêu là time-to-first-message, tạo Timer riêng với bucket phù hợp cho độ trễ message đầu tiên. Đừng kéo dài bucket unary chỉ để chứa stream lifetime; điều đó làm histogram unary kém hữu ích.

Micrometer cho phép cấu hình serviceLevelObjectives(...) để tạo bucket tương ứng ngưỡng SLO, và publishPercentileHistogram() để xuất histogram phù hợp với backend hỗ trợ. Bucket càng nhiều thì số time series càng tăng theo số tổ hợp label. Chỉ chọn ngưỡng phục vụ câu hỏi vận hành.

## 5. Ghi RPC duration ở server bằng ServerInterceptor

ServerInterceptor có thể lấy tên service/method từ MethodDescriptor, bắt đầu timer khi nhận call và ghi thời lượng khi call đóng hoặc bị hủy. Ví dụ dùng Micrometer:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcLatencyServerInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;

    public RpcLatencyServerInterceptor(MeterRegistry registry) {
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

        Timer.Sample sample = Timer.start(registry);
        AtomicBoolean recorded = new AtomicBoolean();

        java.util.function.Consumer<Status> record =
                status -> {
                    if (recorded.compareAndSet(false, true)) {
                        Timer timer = Timer.builder(
                                        "grpc.server.call.duration")
                                .description("Thời lượng xử lý một gRPC server call")
                                .publishPercentileHistogram()
                                .serviceLevelObjectives(
                                        Duration.ofMillis(10),
                                        Duration.ofMillis(25),
                                        Duration.ofMillis(50),
                                        Duration.ofMillis(100),
                                        Duration.ofMillis(200),
                                        Duration.ofMillis(500),
                                        Duration.ofSeconds(1),
                                        Duration.ofSeconds(2))
                                .tags(
                                        "service", service,
                                        "method", method,
                                        "status", status.getCode().name())
                                .register(registry);
                        sample.stop(timer);
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

Timer.Sample ghi nhận thời điểm bắt đầu; sample.stop(timer) ghi duration vào Timer khi call kết thúc. AtomicBoolean bảo đảm chỉ một terminal path ghi mẫu, kể cả khi onCancel() và close() xảy ra gần nhau.

Server-side onCancel() chỉ cho biết call bị hủy; không nhất thiết xác định được caller chủ động cancel hay deadline hết hạn. Do đó label status ở server có thể là CANCELLED trong khi client quan sát DEADLINE_EXCEEDED. Nếu cần phân biệt nguyên nhân, đối chiếu client metric, deadline context và trace thay vì giả định status hai phía luôn giống nhau.

Ví dụ tạo Timer với cùng cấu hình bucket cho từng meter ID. Trong ứng dụng thực tế, nên gom cấu hình Timer vào một factory/helper dùng chung để tránh lệch bucket giữa các call hoặc giữa các service. Cũng cần xác minh hành vi callback terminal với phiên bản grpc-java đang dùng.

## 6. Ghi duration ở client bằng ClientInterceptor

Client-side duration đo từ lúc client bắt đầu call tới khi listener nhận onClose. Nó bao gồm thời gian client quan sát được, nên hữu ích để đo trải nghiệm caller:

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
import io.micrometer.core.instrument.Timer;

import java.time.Duration;

public final class RpcLatencyClientInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public RpcLatencyClientInterceptor(MeterRegistry registry) {
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

                Timer.Sample sample = Timer.start(registry);
                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                Timer timer = Timer.builder(
                                                "grpc.client.call.duration")
                                        .publishPercentileHistogram()
                                        .serviceLevelObjectives(
                                                Duration.ofMillis(10),
                                                Duration.ofMillis(50),
                                                Duration.ofMillis(100),
                                                Duration.ofMillis(250),
                                                Duration.ofMillis(500),
                                                Duration.ofSeconds(1),
                                                Duration.ofSeconds(2))
                                        .tags(
                                                "service", service,
                                                "method", methodName,
                                                "status", status.getCode().name())
                                        .register(registry);
                                sample.stop(timer);
                                super.onClose(status, trailers);
                            }
                        };

                super.start(monitored, headers);
            }
        };
    }
}
```

Client interceptor phải được gắn vào channel qua ManagedChannelBuilder.intercept(...) hoặc extension point tương ứng của Spring gRPC starter. Một call client có thể được retry nội bộ. Interceptor đặt ở vị trí nào trong interceptor chain và retry machinery sẽ quyết định timer quan sát logical call hay attempt. Nếu cần attempt-level duration, hãy xác minh semantics của instrumentation/version bằng test hoặc dùng instrumentation hỗ trợ attempt metrics.

Không cộng client duration và server duration thành một tổng. Chúng là hai phép đo bao phủ các ranh giới khác nhau và có thể chồng lấp.

## 7. Cấu hình Micrometer Timer trong Spring

Spring Boot thường quản lý MeterRegistry qua Micrometer khi dự án tích hợp metrics dependency phù hợp. Có thể tạo một helper để chuẩn hóa Timer theo service, method và status:

```java
Timer timer = Timer.builder("grpc.server.call.duration")
        .description("gRPC server RPC duration")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(25),
                Duration.ofMillis(50),
                Duration.ofMillis(100),
                Duration.ofMillis(250),
                Duration.ofMillis(500),
                Duration.ofSeconds(1))
        .tags(
                "service", service,
                "method", method,
                "status", status)
        .register(meterRegistry);
```

Timer nên dùng tên nhất quán, unit thời gian nhất quán và bucket phù hợp với loại RPC. Nếu dùng một Timer name cho cả unary và stream, thêm label rpc_type có tập giá trị hữu hạn hoặc tách metric name. Không tạo label động từ request.

Đăng ký interceptor qua lifecycle của gRPC server/channel do starter quản lý. Ví dụ bean chỉ minh họa cách tạo interceptor:

```java
@Configuration
class GrpcLatencyConfiguration {

    @Bean
    RpcLatencyServerInterceptor rpcLatencyServerInterceptor(
            MeterRegistry registry) {
        return new RpcLatencyServerInterceptor(registry);
    }
}
```

Bean này cần được starter hoặc server builder thực sự đăng ký. Không giả định mọi starter tự động gắn mọi bean ServerInterceptor; xác minh bằng một integration test gọi RPC rồi kiểm tra meter xuất hiện. Nếu OpenTelemetry Java agent hoặc gRPC instrumentation library đã thu thập duration, tránh thêm interceptor có cùng metric semantics rồi đếm hai lần.

## 8. Đo streaming duration và time-to-first-message

Server interceptor ở trên đo toàn bộ stream duration: từ lúc server nhận call tới lúc stream đóng/cancel. Đó là metric hữu ích để phát hiện stream tồn tại quá lâu, nhưng không cho biết message đầu tiên tới nhanh hay chậm.

Để đo time-to-first-message ở server-streaming, có thể bọc ServerCall.sendMessage(...) và chỉ ghi lần đầu:

```java
AtomicBoolean firstMessageRecorded = new AtomicBoolean();
long startedNanos = System.nanoTime();

ServerCall<ReqT, RespT> monitored =
        new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
            @Override
            public void sendMessage(RespT message) {
                if (firstMessageRecorded.compareAndSet(false, true)) {
                    Timer.builder("grpc.server.stream.time.to.first.message")
                            .publishPercentileHistogram()
                            .tags("service", service, "method", method)
                            .register(registry)
                            .record(
                                    System.nanoTime() - startedNanos,
                                    TimeUnit.NANOSECONDS);
                }
                super.sendMessage(message);
            }
        };
```

Đây là ví dụ ý tưởng cho server-streaming; trong interceptor hoàn chỉnh, dùng cùng call wrapper với duration recorder và xử lý trường hợp stream đóng mà không gửi message nào. System.nanoTime() phù hợp đo elapsed duration trong một process vì không bị thay đổi bởi chỉnh đồng hồ hệ thống.

Với client-streaming hoặc bidirectional streaming, cần xác định rõ “message đầu tiên” là message request tới server, response tới client hay message đầu tiên được xử lý xong. Đặt metric ở đúng boundary cần quan sát. Đối với message processing duration, đo từng message bằng Timer riêng nhưng không thêm message ID làm label.

## 9. Histogram cho streaming cần bucket riêng

Stream có thể sống vài giây, vài phút hoặc nhiều giờ. Nếu dùng bucket unary 10 ms đến 2 s, phần lớn stream sẽ rơi vào bucket lớn nhất và mất thông tin phân phối. Nếu mở rộng bucket unary tới hàng giờ, quantile của unary lại kém chi tiết.

Một cách tổ chức:

| Metric | Bucket ví dụ | Mục đích |
| --- | --- | --- |
| grpc.server.unary.duration | 10 ms tới 2 s | Latency xử lý unary. |
| grpc.server.stream.lifetime | 1 s tới 1 h | Tuổi thọ server/client/bidi stream. |
| grpc.server.stream.time.to.first.message | 10 ms tới 10 s | Thời gian chờ message đầu tiên. |
| grpc.server.stream.message.processing | 1 ms tới 1 s | Thời gian xử lý mỗi message. |

Ngưỡng chỉ là ví dụ; chọn theo traffic, SLO và loại nghiệp vụ. Một subscription stream được thiết kế chạy cả ngày không nên bị cảnh báo chỉ vì duration dài. Với loại stream này, time-to-first-message, inter-message gap, reconnect count và số stream active có thể hữu ích hơn stream lifetime p99.

## 10. Truy vấn p95/p99 trong Prometheus

Micrometer Prometheus registry thường xuất Timer histogram thành các series bucket, count và sum. Với metric name grpc.server.call.duration, tên sau chuẩn hóa có thể là grpc_server_call_duration_seconds_bucket; tên thực tế phụ thuộc registry/export convention. Kiểm tra endpoint scrape để xác nhận.

Ví dụ tính p95 theo service và method:

```promql
histogram_quantile(
  0.95,
  sum by (le, service, method) (
    rate(grpc_server_call_duration_seconds_bucket[5m])
  )
)
```

p99:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, method) (
    rate(grpc_server_call_duration_seconds_bucket[5m])
  )
)
```

Tách status để xem lỗi và call thành công:

```promql
histogram_quantile(
  0.95,
  sum by (le, service, method, status) (
    rate(grpc_server_call_duration_seconds_bucket[5m])
  )
)
```

Tỷ lệ call vượt 500 ms có thể tính từ bucket phù hợp nếu histogram có boundary đó:

```promql
1 -
(
  sum by (service, method) (
    rate(grpc_server_call_duration_seconds_bucket{le="0.5"}[5m])
  )
  /
  sum by (service, method) (
    rate(grpc_server_call_duration_seconds_count[5m])
  )
)
```

Nếu exporter dùng tên label hoặc bucket khác, sửa query theo series thực tế. Histogram quantile là ước lượng từ bucket boundaries; độ chính xác bị giới hạn bởi độ rộng bucket quanh quantile. Không lấy trung bình p99 của từng instance để tạo p99 toàn service; hãy cộng bucket counts trước rồi mới tính quantile.

## 11. Diễn giải histogram cùng request rate và status

Latency không nên được đọc tách rời traffic và status:

| Dấu hiệu | Cách diễn giải ban đầu | Kiểm tra tiếp |
| --- | --- | --- |
| p50 ổn định, p99 tăng | Một phần request bị chậm, có thể do hot key, pool exhaustion hoặc một instance lỗi. | Histogram theo instance, dependency latency và queue. |
| p50 và p99 cùng tăng | Toàn bộ service có thể đang quá tải hoặc dependency chính chậm. | CPU, thread pool, database, network và request rate. |
| p99 tăng cùng UNAVAILABLE | Connection hoặc endpoint có thể không ổn định; retry làm duration tăng. | Subchannel, retry attempts, endpoint health. |
| p99 tăng cùng DEADLINE_EXCEEDED | Request chạm giới hạn thời gian; caller có thể hủy trước khi server hoàn tất. | Deadline budget, downstream spans và server duration. |
| Stream lifetime tăng | Có thể là hành vi bình thường của subscription dài hạn hoặc stream bị kẹt. | Time-to-first-message, inter-message gap, stream age policy. |
| Count thấp nhưng duration cao | Ít call nhưng mỗi call giữ tài nguyên lâu. | In-flight gauge và stream lifecycle. |

Histogram duration chỉ ghi nhận khi call kết thúc. Một stream đang mở nhiều giờ chưa xuất hiện trong completed-duration histogram cho tới khi nó kết thúc. Vì vậy, kết hợp in-flight gauge hoặc active stream gauge để nhìn thấy call hiện đang tồn tại.

## 12. Cardinality và chi phí histogram

Mỗi tổ hợp label tạo một meter/time series; mỗi histogram có nhiều bucket. Nếu dùng các dimension service, method, status, rpc_type và instance, số series tăng theo tích số lượng giá trị. Thêm request ID, user ID hoặc stream ID sẽ làm cardinality bùng nổ.

Giữ label ở mức hữu hạn:

- service: full Protobuf service name.
- method: method name.
- status: gRPC status code.
- rpc_type: chỉ khi cần, với bốn giá trị RPC type cố định.
- instance/zone: chỉ khi backend và cardinality budget cho phép.

Không dùng message content, metadata tùy ý, exception message, trace ID hoặc client identity làm histogram label. Những dữ liệu chi tiết thuộc trace/log. Không bật percentile histogram trên mọi metric một cách mặc định; chọn method cần theo dõi và bucket cần thiết.

## 13. Kiểm thử latency instrumentation

Test cần xác minh timer bắt đầu và kết thúc đúng lifecycle:

1. Gọi unary RPC thành công; xác minh count tăng một và duration dương.
2. Gọi method trả lỗi; xác minh status tag tương ứng và timer vẫn được ghi.
3. Hủy RPC; xác minh duration được ghi đúng một lần dù onCancel và close có thể cạnh tranh.
4. Gọi server-streaming nhiều message; xác minh RPC duration chỉ ghi một mẫu khi stream kết thúc, không tăng theo từng message.
5. Ghi nhận time-to-first-message riêng; xác minh chỉ có một mẫu cho message đầu tiên.
6. Giữ một stream đang mở; xác minh active stream gauge tăng dù completed histogram chưa có mẫu.
7. Chạy nhiều instance; xác minh Prometheus query cộng bucket trước khi tính p95/p99.
8. Kiểm tra metric labels không chứa request ID, user ID hoặc message ID.

Với test đơn vị, dùng SimpleMeterRegistry để kiểm tra Timer count và total time. Với integration test, dùng in-process gRPC server/channel để xác minh interceptor được đăng ký và callback terminal được quan sát. Nếu cần đo network latency thực tế, bổ sung test qua TCP/TLS; in-process transport không đại diện cho latency mạng production.

Không dùng Thread.sleep() để khẳng định một duration chính xác. Với test timing, đặt một khoảng chờ có kiểm soát bằng latch và kiểm tra các bất biến như timer count, duration lớn hơn 0, không ghi trùng. Đừng assert một số millisecond chính xác trong CI vì lịch chạy và tải máy làm thời gian biến động.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ có average, không thấy tail latency | Chưa bật histogram hoặc bucket không phù hợp. | Bật histogram và chọn bucket quanh SLO. |
| Stream lifetime p99 rất lớn làm dashboard unary khó đọc | Trộn stream duration với unary duration. | Tách metric hoặc lọc rpc_type. |
| Stream đang chạy không xuất hiện trong duration histogram | Timer chỉ ghi khi call kết thúc. | Thêm active stream gauge và age metric. |
| Cancellation không có duration | Chỉ record trong close, bỏ sót onCancel. | Ghi ở cả terminal path với atomic guard. |
| Duration bị ghi hai lần | onCancel và close cùng record. | Dùng recorder idempotent cho mỗi call. |
| p99 mỗi instance thấp nhưng service p99 cao | Một instance có ít traffic hoặc histogram được tổng hợp sai. | Sum bucket counts toàn service rồi tính quantile. |
| Histogram có quá nhiều series | Nhiều label động hoặc quá nhiều bucket. | Giới hạn label và chỉ bật histogram cần thiết. |
| Client và server duration không bằng nhau | Hai metric đo ở hai ranh giới khác nhau. | Giữ direction riêng và phân tích cùng trace. |
| Retry làm client duration tăng | Client timer bao gồm thời gian các attempt/backoff theo vị trí instrumentation. | Xác định logical call/attempt semantics và quan sát retry riêng. |

## 15. Bài tập thực hành

1. Viết ServerInterceptor dùng Micrometer Timer để đo unary RPC duration theo service, method và status.
2. Bật percentile histogram và cấu hình bucket quanh SLO của một method đọc.
3. Viết ClientInterceptor để đo client-observed duration; so sánh với server duration nhưng giữ hai metric riêng.
4. Tạo server-streaming RPC; đo stream lifetime và time-to-first-message bằng hai metric khác nhau.
5. Viết PromQL tính p95/p99 theo service/method và tỷ lệ RPC vượt ngưỡng 500 ms.
6. Kiểm thử success, error, cancellation và stream nhiều message; xác minh một terminal sample cho mỗi RPC.
7. Tạo dashboard tách unary, streaming, status và direction; kết hợp histogram với active stream gauge.
8. Kiểm tra cardinality và xác nhận các label chỉ chứa dimension hữu hạn đã được chọn.

Sau bài này, bạn cần phân biệt RPC duration với time-to-first-message và message latency, dùng Timer histogram để quan sát phân phối unary/streaming phù hợp, ghi terminal duration đúng một lần và tính p95/p99 bằng cách tổng hợp bucket. Khi đọc histogram cùng request rate, status và active stream count, đội vận hành có thể phát hiện tail latency và stream bất thường trong hệ thống Spring gRPC.
