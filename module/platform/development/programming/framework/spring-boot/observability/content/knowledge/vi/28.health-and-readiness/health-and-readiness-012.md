# Không dùng liveness thay cho business metric trong Spring Boot

> **Chương:** Health và readiness  
> **Bài:** Không dùng liveness thay cho business metric  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Liveness trả lời câu hỏi nào?

Liveness là tín hiệu cho biết process/container còn sống và có khả năng tiếp tục chạy hay không. Trong Kubernetes, khi liveness probe thất bại liên tiếp vượt ngưỡng cấu hình, kubelet có thể restart container. Vì vậy liveness cần phản ánh những tình trạng mà restart process có khả năng khôi phục.

Liveness không phải điểm số chất lượng nghiệp vụ. Nó không trả lời có bao nhiêu đơn hàng được chấp nhận, tỷ lệ thanh toán thành công là bao nhiêu, người dùng có hoàn tất checkout hay không, queue có đang xử lý kịp SLA không, hoặc tỷ lệ request thành công có đạt mục tiêu không. Những câu hỏi đó cần business metrics, service-level indicators (SLIs), logs và traces.

~~~mermaid
flowchart TD
  A["Application process"] --> B["Liveness probe"]
  B --> C{"Process can continue?"}
  C -->|"No"| D["Restart container"]
  C -->|"Yes"| E["Keep process running"]
  F["Business operations"] --> G["Business metrics / SLIs"]
  G --> H["Dashboards and alerts"]
  I["Dependency / request health"] --> J["Readiness probe"]
  J --> K["Route or remove traffic"]
~~~

Nếu dùng liveness để kiểm tra business KPI như tỷ lệ thanh toán thành công, một đợt lỗi nghiệp vụ có thể khiến toàn bộ pods restart. Restart không sửa được business rule, dữ liệu đầu vào sai hoặc payment provider đang lỗi; nó chỉ làm giảm capacity và có thể làm sự cố nặng hơn.

## 2. Phân biệt liveness, readiness và business metrics

Ba cơ chế phục vụ ba quyết định khác nhau:

| Cơ chế | Câu hỏi | Hành động chính |
| --- | --- | --- |
| Liveness | Process có cần restart để phục hồi không? | Restart container khi probe fail theo policy |
| Readiness | Instance hiện có nên nhận traffic mới không? | Thêm/bỏ instance khỏi endpoints phục vụ |
| Business metrics | Nghiệp vụ đang đạt kết quả gì? | Dashboard, alert, SLO review và điều tra |

Ví dụ:
- JVM deadlock hoặc event loop không còn tiến triển: có thể là liveness concern.
- Database tạm thời unavailable và API không thể phục vụ request cần DB: có thể là readiness concern.
- Tỷ lệ đơn hàng bị từ chối vì hết hàng tăng: business metric, không phải liveness failure.
- Payment success rate giảm do payment provider: business/availability metric và có thể ảnh hưởng readiness tùy contract; không tự động là liveness failure.

Một service có thể liveness UP, readiness DOWN và business success rate giảm cùng lúc. Đây không phải mâu thuẫn: process vẫn sống, instance hiện không nên nhận traffic, và kết quả nghiệp vụ đang suy giảm.

## 3. Vì sao không đưa business KPI vào liveness?

Liveness failure thường kích hoạt restart. Nếu probe phụ thuộc vào business KPI, một biến động nghiệp vụ có thể tạo vòng lặp:

1. Payment provider lỗi làm payment success rate giảm.
2. Liveness endpoint đọc KPI và trả DOWN.
3. Kubernetes restart pods.
4. Pods mới phải warm up, mở connections và khởi tạo cache.
5. Capacity giảm trong khi dependency vẫn lỗi.
6. Request timeout tăng và KPI tiếp tục giảm.

Restart không thay đổi trạng thái của provider hoặc dữ liệu nghiệp vụ. Nó chỉ làm tăng tải khởi động và có thể tạo cascading failure.

Business KPI thường được tính trên cửa sổ thời gian, có sample size và baseline. Liveness probe thường được gọi thường xuyên với timeout ngắn. Đưa một metric cửa sổ vào probe tạo semantics không phù hợp và có thể khiến kết quả dao động.

## 4. Ví dụ: tỷ lệ thanh toán thành công không phải liveness

Giả sử checkout service có business metrics:

~~~text
payment_attempts_total
payment_success_total
payment_declined_total
payment_provider_errors_total
~~~

Tỷ lệ thành công có thể được tính trên một cửa sổ:

~~~text
payment_success_ratio =
  increase(payment_success_total[5m])
  /
  increase(payment_attempts_total[5m])
~~~

Nếu payment provider gặp sự cố, tỷ lệ có thể giảm. Đây là tín hiệu cần alert và điều tra. Process checkout vẫn có thể xử lý endpoint khác, ghi nhận trạng thái pending, hoặc trả response theo fallback contract.

Không biến payment_success_ratio < 0.9 thành liveness DOWN. Thay vào đó:
- Alert theo business SLI/SLO.
- Theo dõi provider error rate và latency.
- Kiểm tra traces của payment client calls.
- Đánh giá readiness nếu instance không thể phục vụ capability bắt buộc.
- Giữ liveness gắn với khả năng process tiếp tục hoạt động.

## 5. Ví dụ cấu hình Spring Boot health groups

Spring Boot Actuator có thể cung cấp liveness/readiness health groups. Cấu hình minh họa:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Đưa db vào readiness khi database thực sự cần thiết để instance nhận loại traffic đang xét. Không đưa db hoặc payment provider vào liveness chỉ để business dependency lỗi làm pod restart.

Spring Boot có thể expose probe paths tương ứng như /actuator/health/liveness và /actuator/health/readiness khi probes được bật. Xác minh path, group membership và HTTP mapping trong phiên bản ứng dụng.

### 5.1. Readiness cũng cần chọn dependency có chủ đích

Nếu dependency optional lỗi nhưng service vẫn có fallback, đưa nó vào readiness có thể loại instance khỏi traffic không cần thiết. Ngược lại, nếu database là điều kiện bắt buộc cho mọi request, readiness có thể phản ánh trạng thái database.

Readiness policy nên dựa trên capability của instance và traffic routing contract, không dựa vào một KPI tổng hợp không ổn định.

## 6. Thiết kế liveness check đúng

Liveness nên nhẹ, nhanh, deterministic và không phụ thuộc downstream có thể lỗi độc lập.

Có thể cân nhắc:
- Spring ApplicationAvailability/LivenessState.
- Process-local condition có thể chỉ ra ứng dụng không thể tiến triển.
- Watchdog nội bộ cho deadlock hoặc worker loop bị kẹt nếu có semantics đáng tin cậy.
- Health indicator chỉ kiểm tra thành phần nội bộ thiết yếu và có khả năng phục hồi bằng restart.

Tránh:
- Gọi database hoặc payment provider qua mạng mỗi lần liveness probe.
- Kiểm tra tỷ lệ business success.
- Chạy query nặng hoặc transaction.
- Kiểm tra queue backlog và restart vì queue lớn.
- Dùng health endpoint tổng hợp mọi dependency làm liveness.
- Timeout quá ngắn gây restart do spike tạm thời.

Không phải mọi process-local lỗi đều cần restart. Chỉ đưa vào liveness khi restart là hành động phục hồi hợp lý và đã kiểm thử.

## 7. Business metrics nên đo gì?

Business metrics đo kết quả mà người dùng hoặc tổ chức quan tâm. Chọn metrics theo domain, không lấy số health checks thay cho hoạt động nghiệp vụ.

Ví dụ với order service:

~~~java
@Service
public class OrderMetrics {

    private final Counter accepted;
    private final Counter rejected;

    public OrderMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("orders.submission")
                .tag("outcome", "accepted")
                .register(registry);
        this.rejected = Counter.builder("orders.submission")
                .tag("outcome", "rejected")
                .register(registry);
    }

    public void recordAccepted() {
        accepted.increment();
    }

    public void recordRejected() {
        rejected.increment();
    }
}
~~~

Đây là custom metrics; gọi record tại business boundary sau khi xác định kết quả theo contract. Tránh tăng counter ở nhiều tầng cho cùng một nghiệp vụ.

Các metrics có thể hữu ích: orders submitted/accepted/rejected, payments authorized/declined/failed, checkout completion rate, fulfillment processing duration, queue enqueue-to-completion latency, refund rate hoặc cancellation rate.

Không dùng user ID, order ID, email hoặc raw exception message làm metric labels. Chọn dimensions hữu hạn như operation, outcome, channel group hoặc region group đã chuẩn hóa.

## 8. Business SLI và SLO

SLI là phép đo định lượng một khía cạnh của dịch vụ; SLO là mục tiêu cho SLI trong một cửa sổ thời gian.

Ví dụ:
- Availability SLI: tỷ lệ request đủ điều kiện hoàn tất theo contract.
- Latency SLI: tỷ lệ request hoàn tất dưới ngưỡng.
- Checkout SLI: tỷ lệ checkout attempts đạt kết quả accepted.
- Payment SLI: tỷ lệ payment authorization thành công, loại trừ decline hợp lệ theo định nghĩa nghiệp vụ.

Mục tiêu giả định:
- 99,9% request API đủ điều kiện trả response theo contract trong 30 ngày.
- 95% checkout hoàn tất trong 2 giây.
- Payment provider technical error rate dưới 0,5% trong 5 phút.

Mục tiêu phải dựa trên yêu cầu thực tế và định nghĩa rõ denominator. Không lấy 2xx ratio làm business conversion rate nếu 4xx có thể là kết quả nghiệp vụ hợp lệ.

Liveness không phải SLI. Liveness probe giúp platform tự phục hồi process; SLI/SLO giúp đội ngũ đánh giá trải nghiệm và độ tin cậy dịch vụ.

## 9. Alert theo business metric, không restart theo KPI

Business alerts nên thông báo hoặc kích hoạt runbook, không trực tiếp biến KPI thành liveness result.

Ví dụ:
- Payment technical failure tăng nhanh: alert payment team.
- Checkout completion giảm: alert business/on-call theo severity.
- Fulfillment age vượt SLA: alert queue owner.
- Refund rate tăng bất thường: điều tra release, policy hoặc fraud signals.

Alert tốt thường kết hợp threshold, duration, baseline, traffic volume và error budget. Tránh alert khi chỉ có vài giao dịch khiến tỷ lệ dao động lớn.

~~~mermaid
flowchart TD
  A["Business event"] --> B["Counter / histogram"]
  B --> C["SLI calculation"]
  C --> D{"SLO / alert condition"}
  D -->|"Breached"| E["Notify / incident workflow"]
  D -->|"Healthy"| F["Continue monitoring"]
  G["Liveness probe"] --> H["Restart only if process unhealthy"]
  I["Readiness probe"] --> J["Control traffic admission"]
~~~

Alerting và orchestration là hai vòng điều khiển khác nhau. Alert cung cấp tín hiệu cho incident workflow; liveness điều khiển lifecycle process; readiness điều khiển routing.

## 10. Kết hợp health với metrics, traces và logs

Khi business KPI xấu đi, đi từ triệu chứng đến nguyên nhân:

1. Business metric cho thấy kết quả nào giảm.
2. Service metrics cho biết request rate, latency, errors và saturation.
3. Traces chỉ ra operation/dependency chậm hoặc thất bại.
4. Logs cung cấp sự kiện và exception context.
5. Health/readiness cho biết instance nào còn đủ điều kiện nhận traffic.

Ví dụ payment success giảm:
- Business metric: payment technical errors tăng.
- HTTP client metrics: payment API 5xx/timeout tăng.
- Trace: payment client span chậm hoặc ERROR.
- Logs: timeout/circuit breaker open.
- Readiness: DOWN chỉ nếu service không thể phục vụ capability bắt buộc theo routing contract.

Không biến mọi trace error thành liveness failure. Một trace error là bằng chứng của một operation; process có thể vẫn hoạt động bình thường.

## 11. Queue backlog và worker health

Queue depth, consumer lag và oldest message age là metrics vận hành. Backlog tăng không tự động có nghĩa worker process cần restart.

Các tình huống:
- Producer burst lớn: depth tăng nhưng throughput cũng cao.
- Consumer xử lý chậm do database pool wait: worker sống nhưng bị bottleneck.
- Poison message: một message retry nhiều lần, lag tăng.
- Worker deadlock: process không tiến triển, có thể là liveness concern nếu watchdog phát hiện đáng tin cậy.

Theo dõi arrival rate, successful processing rate, queue depth/consumer lag, oldest message age, processing duration, retry/DLQ count và active consumers.

Alert backlog vượt SLA và điều tra consumer/downstream. Chỉ dùng liveness khi worker process thực sự bị kẹt và restart có khả năng phục hồi; tránh restart liên tục vì queue lớn.

## 12. Readiness khi business capability suy giảm

Readiness có thể phụ thuộc vào khả năng phục vụ một loại traffic, nhưng không nên bị điều khiển bởi KPI tổng hợp không ổn định.

Ví dụ:
- Service chỉ phục vụ read-only khi database replica lỗi: có thể vẫn ready cho read endpoints nếu routing hỗ trợ.
- Payment provider lỗi nhưng order service vẫn nhận đơn ở trạng thái pending: service có thể vẫn ready.
- Một tenant có tỷ lệ lỗi cao: không nên làm tất cả instances not-ready nếu lỗi chỉ thuộc tenant đó.
- Queue consumer không theo kịp nhưng HTTP API vẫn nhận message: API readiness và worker readiness có thể cần đánh giá riêng.

Với service nhiều capability, một boolean readiness tổng có thể quá thô. Dùng health groups hoặc endpoint/probe phù hợp architecture, nhưng giữ semantics rõ cho platform.

## 13. Tránh cardinality và dữ liệu nhạy cảm trong business metrics

Business metrics có dimensions hấp dẫn như customer, product, order hoặc tenant. Đưa ID có độ đa dạng cao vào labels sẽ tạo time series bùng nổ và có thể lộ dữ liệu.

Nên dùng outcome accepted/rejected/pending, operation checkout/payment/refund, channel hoặc region group hữu hạn, reason category như out_of_stock/invalid_request/provider_unavailable.

Không dùng customer_id/order_id/payment_id, email, phone, IP tùy ý, raw exception message hoặc request payload làm labels.

Nếu cần phân tích entity cụ thể, dùng event analytics hoặc hệ thống dữ liệu nghiệp vụ có access control; metrics time series không phải kho lưu từng giao dịch.

## 14. Kiểm thử liveness, readiness và business metrics

Cần test ba cơ chế độc lập.

Liveness tests:
- Process bình thường trả UP.
- Mô phỏng trạng thái process không thể tiến triển theo watchdog đã thiết kế.
- Xác minh dependency outage không tự làm liveness DOWN nếu restart không giải quyết.

Readiness tests:
- Dependency bắt buộc unavailable làm readiness DOWN nếu contract yêu cầu.
- Optional dependency lỗi không nhất thiết loại instance khỏi traffic.
- Dependency hồi phục thì readiness trở lại UP.

Business metrics tests:
- Accepted/rejected/payment failed events tăng đúng counter.
- Một nghiệp vụ chỉ được ghi nhận một lần tại boundary đã chọn.
- KPI tính đúng denominator và time window.
- Metrics labels có cardinality hữu hạn.

Ví dụ test scenario:

~~~java
@Test
void businessRejectionDoesNotChangeProcessLiveness() {
    // Arrange: process liveness is healthy.
    // Act: record a business rejection.
    // Assert: rejection counter increases; liveness remains UP.
}
~~~

Đây là test scenario, cần triển khai theo test framework và health configuration của dự án. Kiểm thử endpoint HTTP thực tế để xác minh status mapping và probe behavior.

## 15. Troubleshooting khi liveness và business metric bị trộn lẫn

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Pods restart khi payment provider lỗi | Liveness gọi provider hoặc dùng payment KPI | Bỏ dependency khỏi liveness; dùng alert/readiness theo contract |
| Restart loop khi DB outage | DB được include vào liveness | Chuyển dependency check sang readiness nếu phù hợp |
| Business KPI xấu nhưng health UP | Health chỉ phản ánh process/dependency check | Tạo business dashboard/alert |
| Health DOWN dù API vẫn phục vụ fallback | Indicator kiểm tra dependency optional | Định nghĩa capability và readiness membership |
| Alert không kích hoạt dù liveness fail | Dựa vào KPI thay vì probe events | Theo dõi probe failure/restart metrics riêng |
| Business success rate dao động mạnh | Sample size thấp hoặc denominator sai | Dùng cửa sổ phù hợp, minimum traffic |
| Metric cardinality tăng | Entity IDs làm labels | Chuẩn hóa dimensions |
| Worker restart liên tục khi lag tăng | Queue backlog dùng làm liveness | Alert lag; kiểm tra progress/dependency |
| Readiness tất cả replicas DOWN | Shared dependency và policy quá rộng | Đánh giá fallback/failure domain |
| Liveness luôn UP dù process treo | Probe không phản ánh progress | Thiết kế watchdog process-local có bounded semantics |
| Business counter tăng gấp đôi | Ghi metric nhiều layer hoặc retry attempts | Chọn business boundary, phân biệt attempt/completion |

### Quy trình điều tra

1. Xác định probe nào fail: startup, liveness hay readiness.
2. Xem pod restart count và probe failure events.
3. Kiểm tra indicator nào thuộc health group.
4. Xác định business metric chỉ là triệu chứng hay capability thật sự mất.
5. Đối chiếu request metrics, traces, logs và dependency health.
6. Xem restart có cải thiện trạng thái hay làm giảm capacity.
7. Tách business alert khỏi process lifecycle policy.
8. Test staging với dependency outage và KPI regression.

## 16. Tình huống thực tế: payment success rate giảm nhưng process vẫn khỏe

**Bối cảnh:** checkout-service có 8 replicas. Payment provider gặp sự cố, payment success ratio giảm từ 99% xuống 60%. API vẫn có thể tạo order pending và phục vụ chức năng khác. Một custom liveness indicator trả DOWN khi payment ratio dưới 90%.

### Bước 1 — nhận diện sai boundary

Liveness probe đang đọc business KPI theo cửa sổ 5 phút. KPI thấp khiến Kubernetes restart pods, dù JVM và request handlers vẫn hoạt động.

### Bước 2 — loại business KPI khỏi liveness

Liveness chuyển về process-local state. Payment ratio tiếp tục được ghi bằng Counter/SLI và alert riêng.

### Bước 3 — đánh giá readiness

Nếu service vẫn nhận order và lưu trạng thái pending, readiness có thể vẫn UP. Nếu deployment mode chỉ phục vụ payment trực tiếp và không có fallback, readiness policy có thể phản ánh capability đó theo contract.

### Bước 4 — bổ sung telemetry

Theo dõi payment provider client latency/error, circuit breaker state, pending orders, retry count và payment completion age. Trace client span giúp điều tra provider timeout.

### Bước 5 — xác minh

Mô phỏng provider outage:
- Liveness vẫn UP.
- Readiness phản ánh đúng khả năng nhận traffic.
- Payment SLI giảm và alert kích hoạt.
- Pod không restart loop.
- Pending orders được theo dõi và xử lý khi provider phục hồi.

**Kết quả mong muốn:** process lifecycle không bị điều khiển bởi business KPI; business degradation vẫn được phát hiện qua telemetry và alert phù hợp.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — phân loại tín hiệu

Liệt kê 10 tình huống: JVM deadlock, DB outage, payment decline tăng, queue lag tăng, invalid request tăng, worker stuck, cache miss tăng, disk full, provider timeout và checkout conversion giảm. Phân loại thành liveness, readiness, business metric hoặc kết hợp.

### Bài tập B — tách liveness/readiness

Cấu hình health groups trong Spring Boot. Đặt livenessState riêng; chỉ đưa dependency bắt buộc vào readiness. Mô phỏng database outage và xác minh pod không restart loop.

### Bài tập C — business metrics

Tạo counters cho orders accepted/rejected và payments authorized/declined/technical_error. Kiểm tra denominator, retry attempts và duplicate recording. Giữ labels hữu hạn.

### Bài tập D — alert theo SLO

Định nghĩa business SLI/SLO cho checkout. Tạo alert khi error budget burn hoặc success ratio giảm trong cửa sổ đủ traffic. Xác minh alert không thay đổi liveness response.

### Bài tập E — queue worker

Mô phỏng queue backlog và worker processing chậm. Theo dõi lag, oldest age, processing duration và DB pool. Chỉ đánh liveness DOWN khi worker process thật sự không thể tiến triển và restart có ý nghĩa.

### Bài tập F — failure drill

Giả lập payment provider timeout trong staging. Xác minh liveness, readiness, business metrics, client traces, logs và pod restart behavior. Viết runbook xử lý KPI regression mà không restart toàn bộ service.

### Câu hỏi tự kiểm tra

1. Liveness probe trả lời câu hỏi nào?
2. Vì sao business success rate không phải liveness signal?
3. Liveness và readiness khác nhau ở hành động platform nào?
4. Khi payment provider lỗi, process có nhất thiết cần restart không?
5. Business SLI/SLO nên được đo bằng dữ liệu nào?
6. Vì sao business KPI theo cửa sổ thời gian không phù hợp với probe ngắn?
7. Queue depth/lag tăng có phải liveness failure không?
8. Khi nào dependency nên ảnh hưởng readiness?
9. Vì sao không nên đưa mọi dependency vào liveness?
10. Làm sao phân biệt HTTP success rate và business conversion rate?
11. Metric labels nào có thể tạo cardinality explosion?
12. Làm thế nào kết hợp metrics, traces và logs khi business KPI suy giảm?
13. Restart loop có thể khuếch đại dependency outage ra sao?
14. Cần test riêng behavior nào cho liveness/readiness/business metrics?
15. Một service nhiều capability nên thiết kế readiness thế nào?

**Tiêu chí hoàn thành:** giải thích liveness/readiness/business metrics; cấu hình health groups đúng; định nghĩa business SLI/SLO; đo business outcomes bằng metrics; alert mà không restart theo KPI; kiểm soát cardinality; kiểm thử dependency outage và KPI regression.

## 18. Ghi nhớ

- Liveness quyết định process có cần restart; không đo chất lượng hoặc tỷ lệ thành công nghiệp vụ.
- Readiness quyết định instance có nên nhận traffic; dependency chỉ nên tham gia khi ảnh hưởng capability phục vụ traffic theo contract.
- Business metrics đo accepted/rejected/failed, conversion, latency và kết quả người dùng quan tâm.
- Business KPI suy giảm thường cần alert, dashboard và điều tra; restart process không sửa business rule hoặc external provider outage.
- Đưa business KPI vào liveness có thể tạo restart loop và giảm capacity đúng lúc hệ thống cần capacity nhất.
- Spring Boot health groups giúp tách livenessState và readinessState khỏi dependency checks.
- Dùng Micrometer Counter/Timer/DistributionSummary với labels hữu hạn để đo business outcomes.
- Định nghĩa SLI/SLO rõ denominator, eligibility, time window và expected business rejections.
- Kết hợp business metrics với HTTP metrics, traces, logs và dependency telemetry để tìm nguyên nhân.
- Test liveness, readiness và business metrics độc lập; xác minh outage không gây restart ngoài ý muốn.

## Tài liệu tham khảo

- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot Reference — Health Groups](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health.groups)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)

