# SLO cho success, latency và availability

Trong **SPRING_GRPC**, một service có thể vẫn nhận kết nối nhưng trả lời chậm, xử lý sai hoặc không phục vụ được một phần RPC. Vì vậy, độ tin cậy cần được đo bằng các chỉ số phản ánh điều client thực sự nhận được: request có được xử lý đúng contract không, response có đến trong thời gian cam kết không và service có sẵn sàng phục vụ hay không.

SLO (Service Level Objective) là mục tiêu định lượng cho một hoặc nhiều SLI (Service Level Indicator). Với gRPC, cần xác định rõ request nào được tính, thế nào là thành công, latency đo từ đâu đến đâu và status nào là lỗi vận hành. Nếu không có định nghĩa nhất quán, dashboard có thể báo service khỏe trong khi client liên tục timeout, hoặc báo lỗi giả vì các request bị từ chối hợp lệ theo nghiệp vụ.

## 1. Phân biệt SLI, SLO và SLA

- **SLI** là phép đo thực tế, ví dụ tỷ lệ RPC hoàn tất đúng contract hoặc tỷ lệ RPC có latency dưới 300 ms.
- **SLO** là mục tiêu cho SLI trong một cửa sổ thời gian, ví dụ 99,9% request đủ điều kiện được phục vụ thành công trong 30 ngày.
- **SLA** là cam kết dịch vụ với khách hàng hoặc bên sử dụng, có thể kèm điều khoản hỗ trợ/tín dụng khi không đạt.

SLO nên phản ánh điều người dùng quan tâm, không chỉ phản ánh trạng thái process. Một pod đang Ready chưa chứng minh mọi RPC đều thành công; một channel đang READY cũng không bảo đảm call kế tiếp hoàn tất đúng hạn.

## 2. Chọn SLI cho success, latency và availability

Ba nhóm chỉ số thường dùng:

| SLI | Câu hỏi | Cách đo phổ biến |
| --- | --- | --- |
| Success | Nghiệp vụ có đạt kết quả mong muốn không? | Số operation thành công / số operation hợp lệ theo quy tắc nghiệp vụ |
| Latency | Request có hoàn tất trong thời gian mục tiêu không? | Số request dưới ngưỡng / tổng request đủ điều kiện |
| Availability | Service có thể tiếp nhận và xử lý request hợp lệ không? | Số request được phục vụ / tổng request đủ điều kiện; hoặc uptime probe với service ít traffic |

Một SLO thực tế có thể gồm nhiều mục tiêu đồng thời:

- 99,9% request đủ điều kiện được phục vụ thành công trong rolling 30 ngày.
- 95% request unary hoàn tất trong 300 ms.
- 99% request unary hoàn tất trong 1 giây.
- Các stream subscription đạt tỷ lệ kết nối thành công và duy trì hoạt động theo chính sách riêng.

Không gộp tất cả thành một con số duy nhất. Success, latency và availability phản ánh các kiểu hỏng khác nhau; mỗi SLI cần có mẫu số và cách phân loại riêng.

## 3. Định nghĩa request đủ điều kiện và kết quả thành công

Trước khi tính tỷ lệ, phải định nghĩa **eligible request**. Ví dụ, chỉ tính RPC thuộc API production, loại health check, reflection, test traffic và method nội bộ không nằm trong SLO người dùng.

Với availability SLI dạng request-based, định nghĩa một **good request** là request đủ điều kiện mà service trả một kết quả được contract cho phép trước deadline của request. Với latency SLI, good request là request hoàn tất trong threshold T. Với business success SLI, chỉ tính operation đạt kết quả nghiệp vụ mong muốn trên tập operation hợp lệ đã xác định.

Một cách phân loại kết quả RPC cho availability là:

| Kết quả RPC | Xử lý trong availability SLI | Lý do |
| --- | --- | --- |
| Response hợp lệ với status OK | Thành công | Server thực hiện contract |
| INVALID_ARGUMENT | Có thể tính là được phục vụ | Request sai nhưng server đã trả lời theo contract |
| NOT_FOUND | Theo contract | Có thể là kết quả nghiệp vụ hợp lệ |
| UNAUTHENTICATED / PERMISSION_DENIED | Có thể tính là được phục vụ | Server đã thực thi authentication/authorization policy |
| UNAVAILABLE / INTERNAL / DATA_LOSS | Thất bại | Service không phục vụ được hoặc lỗi server |
| DEADLINE_EXCEEDED | Thường thất bại về latency/availability | RPC không hoàn tất trong deadline |
| CANCELLED | Phân loại theo nguyên nhân | Caller chủ động bỏ có thể loại khỏi mẫu số; server hủy do overload cần được tính |
| RESOURCE_EXHAUSTED | Theo policy quota/capacity | Quota hợp lệ khác với server cạn tài nguyên |

Điểm quan trọng: **availability không đồng nghĩa với business success**. Nếu caller yêu cầu một SKU không tồn tại và service trả NOT_FOUND đúng contract, đây vẫn là một good request cho availability vì service đã thực hiện contract. Nhưng đó không phải business success. Hãy đo business outcome riêng nếu cần theo dõi tỷ lệ đơn hàng được chấp nhận, thanh toán thành công hoặc reservation thành công.

Với CANCELLED, không thể chỉ nhìn status rồi loại tất cả khỏi mẫu số. Client có thể hủy vì người dùng đổi ý, nhưng server cũng có thể chủ động cancel do shutdown hoặc overload. Dùng client-side telemetry, cancellation reason hoặc policy loại trừ có kiểm soát để tránh che lỗi server.

## 4. Công thức tính SLI

Với request-based availability:

```text
Availability SLI =
  good eligible requests / total eligible requests

Error ratio = 1 - Availability SLI
```

Với latency threshold:

```text
Latency SLI(T) =
  eligible requests completed within T / total eligible requests
```

Ví dụ trong 30 ngày có 2.000.000 request đủ điều kiện, 1.998.200 request được phục vụ thành công:

- Availability = 1.998.200 / 2.000.000 = 99,91%.
- Error ratio = 0,09%.
- Nếu SLO là 99,9%, service đang đạt mục tiêu trong cửa sổ này.

Nếu trong số 2.000.000 request có 1.940.000 request hoàn tất trong 300 ms, latency SLI(300 ms) = 97%. Nếu mục tiêu là 95%, latency đang đạt mục tiêu dù vẫn có thể có một số request rất chậm.

Không tính trung bình latency rồi so với ngưỡng để thay thế latency SLI. Trung bình có thể che một nhóm nhỏ request cực chậm. Dùng histogram để tính tỷ lệ request dưới ngưỡng và theo dõi p50/p95/p99 để hiểu phân phối.

## 5. Chọn cửa sổ thời gian và error budget

SLO thường được đánh giá theo rolling window, ví dụ 7 ngày hoặc 30 ngày. Rolling window giúp nhìn trạng thái gần đây mà không phải đợi hết tháng lịch.

Với SLO availability 99,9%:

```text
Allowed error ratio = 1 - 0.999 = 0.001 = 0.1%

Error budget = eligible requests x 0.1%
```

Nếu có 2.000.000 eligible requests trong cửa sổ, error budget là 2.000 request thất bại. Nếu đã dùng 1.500 request, còn 500 request trong budget.

Error budget giúp quyết định tốc độ release và ưu tiên reliability work. Khi budget tiêu thụ nhanh, nhóm nên giảm rủi ro thay đổi, xử lý nguyên nhân gốc và xem xét rollback/hold deployment theo policy. Khi budget còn khỏe, có thể tiếp tục phát triển trong giới hạn rủi ro đã thống nhất.

Không dùng error budget để hợp thức hóa lỗi lặp lại. SLO là công cụ quản lý rủi ro và ưu tiên công việc, không phải mục tiêu để tối ưu số liệu bằng cách loại request lỗi khỏi mẫu số.

## 6. Đặt SLO theo từng gRPC service và method

Một server có nhiều service có profile latency khác nhau. Không nên áp dụng cùng một threshold cho mọi method.

Ví dụ:

| Service/method | Kiểu xử lý | SLI latency gợi ý |
| --- | --- | --- |
| Inventory/GetStock | Unary, đọc nhanh | Tỷ lệ hoàn tất dưới 150 ms |
| Order/CreateOrder | Unary, có transaction | Tỷ lệ hoàn tất dưới 500 ms |
| Report/Generate | Unary, tác vụ nặng | Tỷ lệ hoàn tất dưới 2 giây hoặc chuyển thành async job |
| Notification/Subscribe | Server streaming dài hạn | Tỷ lệ kết nối thành công, thời gian tới message đầu, tỷ lệ disconnect bất thường |
| Upload/SendChunks | Client streaming | Tỷ lệ upload hoàn tất, throughput và tỷ lệ lỗi theo session |

SLO nên đặt ở cấp service/method khi user experience khác nhau. Có thể có SLO tổng cho API product, nhưng cần dashboard phân rã để xác định method nào đang tiêu thụ error budget.

Tránh label không giới hạn như user ID, order ID, SKU hoặc full request path chứa dữ liệu động. Dùng service, method, status class, outcome và deployment version với tập giá trị hữu hạn.

## 7. Đo latency đúng điểm bắt đầu và kết thúc

Với unary RPC, latency phía client nên đo từ lúc bắt đầu call đến khi nhận response hoặc terminal error. Đây là trải nghiệm end-to-end mà caller cảm nhận; nó bao gồm network, queue, server processing và response path.

Server-side duration thường đo từ lúc server nhận call đến khi đóng call. Hai phép đo không nhất thiết bằng nhau:

- Client latency bao gồm DNS/connect/reconnect, TLS, proxy, network và thời gian chờ phía client.
- Server duration phản ánh thời gian server xử lý sau khi call tới server.
- Downstream span phản ánh thời gian từng dependency.
- Queue wait và connection acquisition giúp giải thích khoảng thời gian trước khi xử lý thực tế.

Đo cả client và server để phân biệt service xử lý chậm với lỗi mạng hoặc client-side queue. Không suy luận client latency chỉ từ server timer.

## 8. Định nghĩa latency cho streaming RPC

Streaming RPC có vòng đời khác unary, nên một latency duy nhất không đủ:

- **Time to first message**: từ lúc client bắt đầu call đến message đầu tiên.
- **Inter-message gap**: khoảng cách giữa hai message liên tiếp.
- **Stream completion duration**: tổng thời gian từ lúc mở đến khi stream kết thúc.
- **Unexpected termination rate**: tỷ lệ stream kết thúc do lỗi ngoài policy.
- **Reconnect success/time**: thời gian client cần để kết nối lại và tiếp tục.

Một subscription có thể tồn tại hàng giờ; nếu đưa toàn bộ duration vào histogram unary, phân phối latency sẽ vô nghĩa. Đặt SLO riêng cho time-to-first-message, message freshness, disconnect và reconnect. Với upload/download streaming, đo thời gian hoàn tất theo kích thước hoặc số chunk để so sánh công bằng.

## 9. Tính đến retry và logical request

Một logical request có thể tạo nhiều attempt do retry. Nếu chỉ đếm server attempts, retry có thể làm request count tăng; nếu chỉ đếm kết quả cuối ở client, lỗi attempt bị che khuất.

Nên có hai góc nhìn:

- **Logical-call SLI phía client**: một thao tác người dùng, từ lần gọi đầu đến kết quả cuối cùng sau retry.
- **Attempt telemetry**: số attempt, status từng attempt, backoff và thời gian mỗi lần.

SLO người dùng thường dựa trên logical call. Attempt metrics giúp tìm retry amplification và backend không ổn định. Nếu retry khiến logical call cuối cùng thành công nhưng latency vượt ngưỡng, availability có thể đạt trong khi latency SLI thất bại.

Với write, chỉ retry khi operation idempotent hoặc có idempotency key. Một attempt bị reset có thể đã commit; gửi lại không có bảo vệ có thể tạo side effect trùng.

## 10. Instrumentation bằng Micrometer

Có thể ghi duration histogram theo service, method và outcome bằng Micrometer. Ví dụ helper dưới đây được gọi khi RPC đã kết thúc:

```java
@Component
public class GrpcSloMetrics {

    private final MeterRegistry registry;

    public GrpcSloMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String service,
            String method,
            String outcome,
            Duration duration) {

        Timer timer = Timer.builder("grpc.server.call.duration")
                .tag("service", service)
                .tag("method", method)
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(150),
                        Duration.ofMillis(300),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(2))
                .register(registry);

        timer.record(duration);
    }
}
```

Timer cung cấp count, total time và histogram/percentile data tùy registry backend. outcome phải là tập giá trị nhỏ như success, caller_error, server_error, unavailable hoặc cancelled; không dùng exception message làm tag.

Trong production, ưu tiên instrumentation/Observation tích hợp sẵn của Spring gRPC hoặc OpenTelemetry nếu đã có. Tránh ghi cùng một RPC hai lần ở nhiều interceptor mà không thống nhất tên metric và semantics. Nếu tự instrument, ghi đúng một terminal event và tính duration bằng monotonic clock như System.nanoTime().

## 11. Phân loại outcome nhất quán

Đặt một classifier dùng chung để client/server dashboard không tự diễn giải status theo cách khác nhau:

```java
public enum RpcOutcome {
    SUCCESS,
    CALLER_ERROR,
    AUTH_REJECTED,
    SERVER_ERROR,
    UNAVAILABLE,
    DEADLINE,
    CANCELLED,
    CAPACITY_REJECTED
}
```

Classifier nên nhận status code và thêm ngữ cảnh cần thiết như cancellation origin, method policy hoặc quota decision. Không thể phân loại chính xác mọi tình huống chỉ từ status code: ví dụ CANCELLED có thể do caller hoặc server; RESOURCE_EXHAUSTED có thể là quota hợp lệ hoặc server capacity failure.

Tách hai metric nếu cần:
- grpc.server.call.outcome: kết quả xử lý ở server.
- grpc.client.logical_call.outcome: kết quả cuối cùng caller nhìn thấy.

Dùng cùng taxonomy và tài liệu hóa policy để dashboard, alert và báo cáo SLO nhất quán.

## 12. Alert theo error budget và burn rate

Alert không nên chỉ dựa trên một ngưỡng lỗi tuyệt đối. Với SLO 99,9%, allowed error ratio là 0,1%. Burn rate được tính:

```text
Burn rate = observed error ratio / allowed error ratio
```

Nếu error ratio trong cửa sổ gần đây là 2%, burn rate = 2% / 0,1% = 20x. Ở tốc độ này, error budget bị tiêu thụ rất nhanh.

Dùng nhiều cửa sổ để phân biệt sự cố lớn với nhiễu ngắn hạn:
- Cửa sổ ngắn phát hiện outage hoặc degradation đột ngột.
- Cửa sổ dài xác nhận mức tiêu thụ budget có ý nghĩa.
- Alert theo service/method có ảnh hưởng lớn, không tạo một alert cho từng user/request.

Latency SLO cũng cần alert khi tỷ lệ request vượt threshold tăng, kể cả khi availability vẫn đạt. Một service trả response hợp lệ nhưng chậm hơn SLA vẫn làm trải nghiệm người dùng suy giảm.

## 13. Dashboard SLO nên hiển thị gì?

Một dashboard đủ dùng nên có:

| Panel | Nội dung |
| --- | --- |
| Availability | Good/eligible requests, error ratio, SLO target |
| Latency | Histogram, p50/p95/p99, tỷ lệ dưới các threshold |
| Error budget | Budget còn lại, burn rate theo cửa sổ |
| gRPC status | Phân bố status theo service/method |
| Client vs server | Logical-call latency so với server duration |
| Retry | Attempts/logical call, retry success, backoff |
| Streaming | Time-to-first-message, inter-message gap, disconnect/reconnect |
| Dependency | Downstream latency, timeout và failure |
| Deployment | Version, rollout time và thay đổi sau release |

Hiển thị traffic volume cùng tỷ lệ. Một tỷ lệ lỗi cao trên 5 request có ý nghĩa khác với tỷ lệ tương tự trên hàng triệu request. Với service ít traffic, synthetic probe từ vị trí bên ngoài có thể giúp phát hiện outage giữa hai request thực.

## 14. Kiểm thử và xác nhận SLO

SLO cần được kiểm chứng bằng test có kiểm soát:

1. Unit test classifier cho từng status và cancellation origin.
2. Integration test gọi generated stub để ghi nhận client logical-call duration.
3. Test server interceptor/metrics đảm bảo đúng một terminal measurement mỗi RPC.
4. Fault injection cho downstream latency, connection failure và server overload.
5. Streaming test đo time-to-first-message và inter-message gap.
6. Load test kiểm tra histogram và error ratio dưới tải dự kiến.
7. Kiểm tra retry không làm che logical-call latency hoặc tạo side effect lặp.
8. Đối chiếu dashboard với số lượng RPC thực tế và log/trace.

Dùng fake clock hoặc clock abstraction khi test cửa sổ thời gian/burn rate để tránh test phụ thuộc đồng hồ thực. Không dùng Thread.sleep để kiểm tra histogram hoặc alert window nếu có thể điều khiển thời gian và sự kiện bằng test fixture.

## 15. Ví dụ xây dựng SLO cho InventoryService

Giả sử InventoryService phục vụ unary reads và writes. Nhóm có thể định nghĩa:

| Mục tiêu | SLO ví dụ | Phạm vi |
| --- | --- | --- |
| Availability | 99,9% eligible logical calls trong 30 ngày | GetStock, ReserveStock |
| Read latency | 95% GetStock dưới 150 ms | Client-side logical call |
| Write latency | 95% ReserveStock dưới 500 ms | Client-side logical call |
| Server capacity | Không vượt ngưỡng rejection đã thống nhất | RESOURCE_EXHAUSTED do capacity |
| Streaming | Không áp dụng cho hai unary method | SLO riêng nếu thêm watch API |

INVALID_ARGUMENT hoặc NOT_FOUND có thể được tính là request được phục vụ theo contract nhưng không phải business success. UNAVAILABLE, INTERNAL và deadline do service xử lý chậm là failure theo policy. Caller cancellation được loại khỏi availability denominator chỉ khi xác định được caller chủ động hủy; cancellation do server overload không được loại.

Sau một tháng, nếu availability đạt 99,95% nhưng read latency chỉ đạt 88% dưới 150 ms, service đạt availability objective nhưng không đạt latency objective. Nhóm cần tối ưu cache, database/index, queue hoặc downstream call thay vì chỉ nhìn status OK.

### Ghi nhớ

**SLO có ý nghĩa khi success, latency và availability được định nghĩa bằng SLI có mẫu số và quy tắc phân loại rõ ràng.** Đo logical RPC ở phía client, server processing và từng downstream stage; phân biệt lỗi server với caller error, cancellation và business outcome; dùng histogram/threshold cho latency, error budget/burn rate cho alert. Với streaming, đặt SLO riêng cho time-to-first-message, message gap và disconnect thay vì trộn duration dài vào unary latency.

## Tài liệu tham khảo

- [Google SRE — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Google SRE — Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [gRPC — OpenTelemetry Metrics](https://grpc.io/docs/guides/opentelemetry-metrics/)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring gRPC — Observability](https://docs.spring.io/spring-grpc/reference/observability.html)
