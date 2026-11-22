# Metric số RPC theo service và method

Khi vận hành hệ thống gRPC, tổng số request của toàn ứng dụng thường không đủ để tìm nguyên nhân sự cố. Một service có thể nhận nhiều RPC đọc, ít RPC ghi nhưng tần suất lỗi của một method cụ thể lại tăng mạnh. Đếm RPC theo service và method giúp biết endpoint nào đang nhận tải, method nào tăng đột biến và thay đổi traffic có liên quan tới rollout hay không.

**Metric số RPC theo service và method** là chỉ số đếm số lần gọi RPC, được phân nhóm bằng tên service và method gRPC ổn định. Bài thuộc chương **Observability** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là định nghĩa đúng một RPC được đếm khi nào, thu thập metric ở server/client và truy vấn số liệu mà không tạo cardinality quá lớn.

## 1. Xác định đơn vị được đếm

Trong gRPC, một RPC là một lần gọi một method của service, ví dụ Inventory.GetStock hoặc Order.CreateOrder. Một RPC có thể là unary hoặc streaming:

- Unary: một request và một response.
- Server streaming: một request, nhiều response message.
- Client streaming: nhiều request message, một response.
- Bidirectional streaming: nhiều message theo cả hai chiều.

Metric số RPC phải đếm **một lần cho mỗi call**, không đếm số message. Một server-streaming call gửi 500 message vẫn là một RPC. Nếu cần biết throughput message, tạo metric riêng như số message gửi/nhận.

Trước khi tạo metric, cần thống nhất metric đang đếm:

| Metric | Thời điểm tăng | Ý nghĩa |
| --- | --- | --- |
| RPC started | Khi call được nhận ở server hoặc bắt đầu ở client. | Lượng call được khởi tạo, kể cả call chưa hoàn tất. |
| RPC completed | Khi call đi tới terminal state. | Lượng call đã kết thúc, phân theo status. |
| RPC in-flight | Tăng khi call bắt đầu, giảm khi call kết thúc. | Số call đang hoạt động tại thời điểm quan sát. |
| RPC attempt | Mỗi lần thử tới một endpoint. | Dùng phân tích retry/failover, nếu instrumentation quan sát được từng attempt. |
| Logical operation | Một ý định nghiệp vụ từ caller. | Có thể bao gồm nhiều RPC attempt hoặc nhiều service call. |

Không cộng các metric này với nhau. Một logical operation có thể tạo nhiều RPC; một RPC streaming có thể mang hàng nghìn message.

## 2. Nhóm theo service và method

Tên service và method nên lấy từ Protobuf method descriptor, không lấy từ URL tự ghép hoặc payload. Ví dụ:

| gRPC full method name | Service label | Method label |
| --- | --- | --- |
| inventory.Inventory/GetStock | inventory.Inventory | GetStock |
| inventory.Inventory/WatchStock | inventory.Inventory | WatchStock |
| orders.OrderService/CreateOrder | orders.OrderService | CreateOrder |

Dùng tên service đầy đủ gồm package để tránh trùng giữa các service có cùng tên ngắn. Method label là tên method trong service. Đây là tập giá trị hữu hạn được định nghĩa trong API, nên phù hợp làm metric labels.

Metric cơ bản nên có:

- Service: tên đầy đủ của Protobuf service.
- Method: tên method của RPC.
- Status: mã kết thúc RPC, ví dụ OK, CANCELLED, DEADLINE_EXCEEDED hoặc UNAVAILABLE.
- Direction: server hoặc client nếu dùng chung một metric family.

Không dùng user ID, order ID, request ID, trace ID, địa chỉ IP tùy biến hoặc nội dung lỗi làm label. Những giá trị này có thể có hàng triệu biến thể và khiến số time series tăng không kiểm soát. Dùng log hoặc trace để điều tra một request cụ thể.

## 3. Chọn Counter cho số lượng RPC

Số lần gọi là đại lượng tích lũy, vì vậy dùng Counter. Counter chỉ tăng; hệ thống metrics backend tính tốc độ tăng trong một cửa sổ thời gian.

Ví dụ định nghĩa metric server:

~~~text
grpc.server.calls.started
  tags: service, method

grpc.server.calls
  tags: service, method, status
~~~

Counter started tăng một lần khi server nhận call. Counter completed tăng đúng một lần khi call đi tới terminal state. Có thể cộng các status để lấy tổng số RPC hoàn tất theo service/method.

Nếu chỉ cần một metric tổng số RPC, metric completed với tag status thường đã đủ. Metric started bổ sung góc nhìn về call được nhận nhưng chưa kết thúc, đặc biệt hữu ích khi so sánh với số call completed trong cùng khoảng thời gian.

Không dùng Gauge để đếm tổng RPC từ lúc ứng dụng khởi động; Gauge có thể tăng và giảm, trong khi tổng call là giá trị tích lũy. Gauge phù hợp cho số call đang hoạt động tại thời điểm hiện tại.

## 4. Thu thập metric server bằng ServerInterceptor

ServerInterceptor nằm ở ranh giới nhận RPC, nên có thể lấy service/method từ MethodDescriptor và ghi nhận status khi call kết thúc. Ví dụ dưới đây dùng Micrometer MeterRegistry:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcCountServerInterceptor implements ServerInterceptor {

    private final MeterRegistry registry;

    public RpcCountServerInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String fullMethod = call.getMethodDescriptor().getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);

        registry.counter(
                "grpc.server.calls.started",
                "service", service,
                "method", method
        ).increment();

        AtomicBoolean recorded = new AtomicBoolean();
        java.util.function.Consumer<Status> recordTerminal = status -> {
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
                        recordTerminal.accept(status);
                        super.close(status, trailers);
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onCancel() {
                // Client cancel/deadline có thể làm server không đi qua close()
                // với một status do application phát ra.
                recordTerminal.accept(Status.CANCELLED);
                super.onCancel();
            }
        };
    }
}
~~~

Interceptor tăng started khi nhận call. Wrapper của ServerCall ghi status thực tế khi server đóng call. onCancel là đường bổ sung cho trường hợp peer hủy call; AtomicBoolean bảo đảm chỉ ghi một terminal count dù cancellation và close xảy ra gần nhau.

Trong một số phiên bản hoặc transport, thứ tự callback terminal có thể khác nhau. Test interceptor với phiên bản grpc-java đang dùng, nhất là race giữa onCancel và close. Nếu onCancel đã ghi CANCELLED trước khi close được gọi, cờ recorded sẽ ngăn ghi thêm lần thứ hai.

Đăng ký interceptor ở server builder hoặc cơ chế global interceptor mà Spring gRPC starter đang dùng. Ví dụ với builder:

~~~java
serverBuilder.intercept(new RpcCountServerInterceptor(meterRegistry));
~~~

Cách đăng ký bean/interceptor cụ thể phụ thuộc starter và phiên bản đang dùng. Nếu starter tự quản lý server, dùng extension point chính thức của starter; tránh tạo thêm một server hoặc một interceptor registration song song ngoài lifecycle của ứng dụng.

## 5. Đo số RPC phía client

Server metric trả lời “service đã nhận và kết thúc bao nhiêu call”. Client metric trả lời “ứng dụng đã gọi method nào và nhận kết quả gì”. Có thể thu thập ở ClientInterceptor:

~~~java
public final class RpcCountClientInterceptor implements ClientInterceptor {

    private final MeterRegistry registry;

    public RpcCountClientInterceptor(MeterRegistry registry) {
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

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                registry.counter(
                        "grpc.client.calls.started",
                        "service", service,
                        "method", methodName
                ).increment();

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

Client và server metric không nhất thiết bằng nhau. Client có thể hủy trước khi server nhận request; server có thể hoàn tất nhưng response bị mất; proxy có thể từ chối call trước khi tới server. Đặt direction rõ ràng để không cộng lẫn hai góc nhìn.

Một lưu ý với retry: metric tại ClientInterceptor thường phản ánh call ở ranh giới interceptor; việc nó đếm logical call hay từng transport attempt phụ thuộc vị trí instrumentation và cơ chế retry trong phiên bản gRPC. Nếu cần số attempt chính xác, dùng instrumentation có khả năng quan sát attempt-level hoặc metric do proxy/control plane cung cấp. Đừng gọi metric client interceptor là attempt count nếu chưa xác minh bằng test.

## 6. Xử lý cancellation và terminal status đúng một lần

Một RPC có nhiều đường kết thúc:

- Server trả response thành công.
- Server trả lỗi bằng status.
- Client chủ động hủy.
- Deadline hết hạn.
- Kết nối hoặc transport gặp lỗi.

Metric completed phải tăng đúng một lần cho mỗi call. Nếu tăng trong cả onCancel và close mà không có cơ chế chống trùng, số RPC CANCELLED có thể bị đếm hai lần.

Ở server, cancellation do client hoặc deadline có thể được quan sát dưới dạng CANCELLED. Client thường phân biệt explicit cancel và deadline expiry bằng status cuối cùng tương ứng: CANCELLED hoặc DEADLINE_EXCEEDED. Vì vậy, server-side metric không phải lúc nào cũng phân loại được nguyên nhân gốc chỉ từ callback onCancel. Nếu cần phân biệt, kết hợp metric client, deadline context và trace; không suy luận rằng mọi server-side CANCELLED đều là người dùng bấm nút cancel.

Đối với streaming RPC, chỉ ghi completed khi toàn bộ call kết thúc. Không tăng counter ở mỗi onNext. Nếu cần đo message, dùng metric riêng:

~~~text
grpc.server.messages.sent
  tags: service, method

grpc.server.messages.received
  tags: service, method
~~~

## 7. Tính request rate và tổng số RPC

Counter lưu tổng tích lũy từ lúc process khởi động hoặc từ lúc backend bắt đầu giữ series. Dashboard thường cần hai dạng:

- **Rate:** số RPC mỗi giây trong cửa sổ gần đây, phù hợp để quan sát tải hiện tại.
- **Increase:** tổng số RPC tăng thêm trong một khoảng thời gian, phù hợp báo cáo theo giờ/ngày.

Nếu Micrometer export sang Prometheus, tên meter grpc.server.calls thường được chuẩn hóa thành grpc_server_calls_total. Ví dụ PromQL:

~~~promql
# RPC mỗi giây theo service và method, gộp mọi status.
sum by (service, method) (
  rate(grpc_server_calls_total[5m])
)

# Tổng RPC hoàn tất trong một giờ theo service và method.
sum by (service, method) (
  increase(grpc_server_calls_total[1h])
)

# RPC theo status để phát hiện lỗi tăng.
sum by (service, method, status) (
  rate(grpc_server_calls_total[5m])
)
~~~

Tên metric và label cuối cùng phụ thuộc registry/exporter và quy tắc chuẩn hóa tên. Kiểm tra endpoint scrape thực tế trước khi đưa query vào dashboard. Nếu dùng OpenTelemetry Collector hoặc backend khác, cú pháp truy vấn sẽ khác nhưng nguyên tắc nhóm theo service/method vẫn giữ nguyên.

Không tính rate bằng cách lấy giá trị counter hiện tại chia cho thời gian process sống nếu mục tiêu là tải trong 5 phút gần nhất. Dùng hàm rate/increase của backend để xử lý counter reset khi process restart.

## 8. Đọc metric cùng status và latency

Chỉ nhìn số RPC có thể gây hiểu nhầm. Traffic tăng có thể là tăng trưởng bình thường hoặc retry storm. Ghép số lượng với status và duration:

| Quan sát | Có thể chỉ ra | Cần kiểm tra |
| --- | --- | --- |
| RPC count tăng, latency ổn định, lỗi thấp | Tải tăng bình thường. | Capacity và xu hướng traffic. |
| RPC count tăng cùng UNAVAILABLE | Retry storm hoặc instance/service không ổn định. | Retry policy, endpoint health, connection state. |
| RPC count ổn định nhưng DEADLINE_EXCEEDED tăng | Service chậm hoặc deadline quá ngắn. | Duration, queueing, dependency latency. |
| Started tăng nhưng completed thấp | Nhiều call đang chạy lâu hoặc terminal instrumentation bị thiếu. | In-flight gauge, stream duration, cleanup path. |
| Một method tăng đột biến | Client mới, loop gọi RPC hoặc thay đổi luồng nghiệp vụ. | Release, caller, trace và request rate. |
| Client count cao hơn server count | Call bị chặn trước server, connection failure hoặc khác biệt cách đếm. | Client/server metrics, proxy và transport. |

Nên bổ sung:

- Histogram duration theo service/method để đo latency.
- Gauge số RPC in-flight theo service/method.
- Counter theo status để tính error rate.
- Retry attempt metric nếu cần phân biệt call logic với lần thử transport.

Không biến một counter thành nhiều loại dữ liệu bằng cách diễn giải lại. Mỗi metric cần có tên, unit, thời điểm cập nhật và semantics rõ ràng.

## 9. Cardinality và thiết kế label

Cardinality là số tổ hợp label khác nhau mà backend phải lưu. Nếu service có 20 method và 6 status, số series cơ bản khoảng 120 cho mỗi direction/instance dimension. Đây thường là quy mô có thể kiểm soát.

Nếu thêm request ID với hàng triệu giá trị, mỗi call có thể tạo một time series mới. Hệ quả là tăng bộ nhớ, chi phí ingest, truy vấn chậm và có thể làm backend metrics quá tải.

Nên dùng:

- Tên service/method lấy từ API descriptor.
- Status code thuộc tập enum hữu hạn.
- Direction với hai giá trị client/server nếu cần dùng chung metric family.
- Region/zone nếu tập giá trị nhỏ, ổn định và thật sự cần cho vận hành.

Tránh:

- User ID, account ID, order ID, tenant ID không giới hạn.
- Trace ID, span ID, request ID.
- Địa chỉ IP/port ephemeral hoặc hostname pod có vòng đời ngắn.
- Exception message, error description hoặc metadata tùy ý.
- Full URL/path có tham số động.

Thông tin định danh từng request thuộc trace/log. Metric dùng để tổng hợp xu hướng và cảnh báo.

## 10. Metric trong hệ thống Spring gRPC

Trong ứng dụng Spring, MeterRegistry thường được quản lý như bean khi dự án tích hợp Micrometer. Interceptor cũng nên được quản lý theo lifecycle ứng dụng và dùng chung registry:

~~~java
@Configuration
class GrpcMetricsConfiguration {

    @Bean
    RpcCountServerInterceptor rpcCountServerInterceptor(
            MeterRegistry meterRegistry) {
        return new RpcCountServerInterceptor(meterRegistry);
    }
}
~~~

Bean trên chỉ tạo interceptor; ứng dụng còn phải đăng ký nó với gRPC server theo extension point của starter đang dùng. Không giả định mọi starter tự động gắn mọi bean ServerInterceptor. Kiểm tra tài liệu/version của starter và xác minh metric xuất hiện sau một RPC test.

Nếu dùng OpenTelemetry Java agent hoặc gRPC instrumentation library đã tự thu thập RPC metrics, tránh cài thêm một interceptor đếm trùng cùng semantics. Có thể dùng metric chuẩn do instrumentation cung cấp hoặc metric custom, nhưng phải ghi rõ nguồn và ý nghĩa. Nếu vừa dùng metric tự viết vừa dùng instrumentation tự động, đặt namespace khác nhau và xác minh không cộng hai lần.

## 11. Kiểm thử metric số RPC

Một test interceptor có thể dùng SimpleMeterRegistry để xác minh counter:

~~~java
@Test
void countsOneCompletedRpcByServiceAndMethod() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    RpcCountServerInterceptor interceptor =
            new RpcCountServerInterceptor(registry);

    // Dùng in-process server gắn interceptor và gọi một RPC thành công.
    // Sau khi client nhận terminal callback, kiểm tra:
    double started = registry.get("grpc.server.calls.started")
            .tag("service", "inventory.Inventory")
            .tag("method", "GetStock")
            .counter()
            .count();

    double completed = registry.get("grpc.server.calls")
            .tag("service", "inventory.Inventory")
            .tag("method", "GetStock")
            .tag("status", "OK")
            .counter()
            .count();

    assertEquals(1.0, started);
    assertEquals(1.0, completed);
}
~~~

Đoạn test trên minh họa phần assertion; fixture in-process cần thực sự gắn interceptor vào server và chờ call hoàn tất trước khi đọc registry. Bổ sung các ca:

1. Gọi hai method khác nhau; xác minh counter tách theo method.
2. Gọi hai service có method cùng tên; xác minh service label ngăn trùng series.
3. Server trả lỗi; xác minh status label phản ánh status cuối.
4. Client cancel; xác minh chỉ có một terminal count dù onCancel và close chạy gần nhau.
5. Gọi streaming RPC nhiều message; xác minh RPC counter chỉ tăng một lần.
6. Retry một call; xác minh semantics logical call/attempt của instrumentation đúng như tài liệu và test.
7. Kiểm tra label set không chứa request ID, user ID hoặc payload.

Test với SimpleMeterRegistry xác minh logic meter trong process. Integration test với Prometheus/OpenTelemetry exporter xác minh tên metric, label và query thực tế sau khi chuẩn hóa.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Một stream dài làm counter tăng theo message | Tăng RPC counter trong onNext. | Chỉ tăng terminal counter một lần mỗi call; tạo message counter riêng. |
| RPC bị đếm hai lần khi cancel | Cả onCancel và close cùng ghi metric. | Dùng AtomicBoolean hoặc lifecycle recorder idempotent. |
| Không biết method nào tăng tải | Chỉ gắn label service hoặc không gắn method. | Lấy full service/method từ MethodDescriptor. |
| Dashboard có quá nhiều series | Dùng user/request/trace ID làm label. | Giữ label hữu hạn; chuyển định danh chi tiết sang trace/log. |
| Client và server count không bằng nhau | Đo ở hai ranh giới khác nhau hoặc lỗi trước khi server nhận call. | Giữ direction riêng và hiểu semantics mỗi metric. |
| Retry làm count cao hơn số thao tác nghiệp vụ | Đếm RPC attempt như logical operation. | Định nghĩa riêng RPC count, attempt count và business operation count. |
| Status CANCELLED bị hiểu là người dùng chủ động hủy | Server không luôn phân biệt được nguyên nhân cancellation. | Đối chiếu client status, deadline và trace. |
| Metric không xuất hiện trong Prometheus | Interceptor chưa được đăng ký hoặc exporter chưa scrape meter. | Kiểm tra server wiring, registry và endpoint scrape. |

## 13. Bài tập thực hành

1. Viết ServerInterceptor đếm RPC started và completed theo full service name, method và status.
2. Kiểm thử unary method và streaming method; chứng minh một stream nhiều message chỉ tăng RPC counter một lần.
3. Thêm ClientInterceptor hoặc instrumentation tương đương để đo client calls; ghi rõ metric đang đếm logical call hay attempt.
4. Export Micrometer metrics sang Prometheus; tạo query rate và increase theo service/method.
5. Tạo dashboard hiển thị RPC rate, status distribution và latency p95 cho từng method.
6. Thêm test cancellation race để xác minh terminal counter không tăng hai lần.
7. Kiểm tra cardinality bằng cách xác nhận metric labels chỉ gồm service, method, status và các dimension hữu hạn được phê duyệt.

Sau bài này, bạn cần định nghĩa được một RPC được đếm ở thời điểm nào, dùng Counter cho tổng call, phân nhóm bằng service/method/status và bảo đảm mỗi call chỉ có một terminal count. Khi kết hợp số RPC với latency, status, in-flight và retry metrics, đội vận hành có thể nhận ra method tăng tải hoặc lỗi trong hệ thống Spring gRPC mà không làm metrics backend quá tải vì cardinality.
