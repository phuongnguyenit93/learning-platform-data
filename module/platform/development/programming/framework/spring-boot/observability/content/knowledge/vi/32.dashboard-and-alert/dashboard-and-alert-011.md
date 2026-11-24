# Alert theo health state

Trong chương **Dashboard và alert** của mô-đun **SPRING_BOOT_OBSERVABILITY**, alert theo health state là cách phát hiện và thông báo khi trạng thái sức khỏe của ứng dụng hoặc dependency chuyển sang trạng thái cần hành động. Spring Boot Actuator cung cấp health indicators và health groups như `readiness` và `liveness`; metrics backend như Prometheus thu thập tín hiệu và đánh giá alert rules theo chu kỳ. Kết hợp đúng các lớp này giúp đội vận hành phát hiện instance không còn nhận traffic, process cần được kiểm tra hoặc dependency quan trọng đang gặp sự cố.

Một health endpoint trả `DOWN` không tự động gửi notification. Cần có đường đi từ health state tới scrape target hoặc metric, rule đánh giá, Alertmanager và người nhận. Cũng cần xác định trạng thái nào thực sự cần alert: readiness DOWN có thể chỉ là một pod đang rollout; liveness DOWN thường dẫn đến restart; dependency optional DOWN có thể chỉ cần dashboard theo dõi. Alert nên phản ánh tác động và hành động cần thiết, tránh báo động cho mọi lần state thay đổi ngắn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích health state của Actuator và cách chuyển nó thành tín hiệu alert.
2. Phân biệt liveness, readiness và health của dependency.
3. Chọn điều kiện alert dựa trên tác động tới người dùng và service.
4. Kết hợp Actuator health groups với metrics backend.
5. Viết Prometheus alert rules có for, severity và labels ổn định.
6. Phân biệt scrape failure với trạng thái DOWN thật của ứng dụng.
7. Hạn chế alert flapping bằng thời gian duy trì, grouping và inhibition.
8. Thiết kế dashboard cho trạng thái hiện tại và lịch sử chuyển trạng thái.
9. Kiểm thử alert rules bằng dữ liệu mẫu và fault injection.
10. Viết runbook gắn với từng alert để người trực có thể hành động.

## 2. Từ health endpoint tới notification

Actuator health endpoint cung cấp trạng thái tại thời điểm được gọi. Prometheus hoặc hệ thống monitoring phải scrape một endpoint/metric phù hợp; alert rule đánh giá dữ liệu đã scrape; Alertmanager hoặc dịch vụ tương đương group, deduplicate, inhibit và route notification.

~~~mermaid
flowchart LR
    App["Spring Boot + Actuator"]
    Health["Health groups / health metrics"]
    Scrape["Prometheus scrape"]
    Rules["Alert rules"]
    AM["Alertmanager"]
    Notify["On-call / chat / ticket"]
    Runbook["Dashboard + runbook"]
    App --> Health --> Scrape --> Rules --> AM --> Notify
    Notify --> Runbook
~~~

| Lớp | Trách nhiệm |
| --- | --- |
| Actuator | Đánh giá health indicators và trả status/group. |
| Micrometer/Prometheus registry | Expose metrics có thể scrape. |
| Prometheus | Lưu time series và đánh giá alert expressions. |
| Alertmanager | Group, deduplicate, inhibit và route alerts. |
| On-call/runbook | Xác định tác động, chẩn đoán và khôi phục. |

Không giả định chỉ expose `/actuator/health` là Prometheus đã có metric `health=DOWN`. Nếu scrape endpoint health JSON, Prometheus cần exporter/integration hoặc collector chuyển đổi response thành metric. Một lựa chọn khác là phát health state thành gauge/counter từ ứng dụng, hoặc dùng blackbox probe để theo dõi HTTP endpoint availability. Hãy xác minh metric thực tế trước khi viết rule.

## 3. Chọn health state cần alert

Health state có nhiều ý nghĩa. Trước khi tạo alert, xác định state đó đại diện cho process, khả năng nhận traffic hay dependency.

| Health state | Ý nghĩa | Hành động monitoring thường phù hợp |
| --- | --- | --- |
| Liveness DOWN | Process không ở trạng thái có thể tiếp tục hoạt động. | Theo dõi restart loop và số replicas; cảnh báo khi tác động kéo dài. |
| Readiness DOWN | Instance chưa sẵn sàng nhận traffic. | Theo dõi số instance ready và tỷ lệ capacity còn lại. |
| Database DOWN | Dependency database không healthy theo indicator. | Alert theo mức ảnh hưởng tới request path, pool và error rate. |
| Optional service DOWN | Dependency không thiết yếu đang lỗi. | Dashboard hoặc warning nếu degraded mode vẫn hoạt động. |
| Health endpoint unreachable | Probe không thể lấy health response. | Phân biệt app down với network/scrape failure. |

Không gửi page cho từng instance readiness DOWN trong rollout bình thường nếu deployment controller đã xử lý. Một alert theo service-level availability hoặc số replicas ready thấp thường phản ánh tác động tốt hơn.

Liveness DOWN có thể được Kubernetes dùng để restart container. Alert nên quan sát restart loop, crash frequency và ảnh hưởng tới capacity thay vì chỉ lặp lại sự kiện restart đơn lẻ.

## 4. Thiết kế health groups phù hợp cho alerting

Health groups nên được tạo theo quyết định vận hành:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
        external:
          include: search,partnerApi
~~~

Ví dụ trên chỉ phù hợp nếu database là dependency bắt buộc cho khả năng nhận traffic. Nếu ứng dụng có cache/fallback/degraded mode, cần quyết định readiness theo contract thực tế. Không đưa remote dependency vào liveness chỉ vì nó quan trọng với nghiệp vụ.

Một group riêng cho external services có thể giúp dashboard hiển thị degraded dependencies mà không tự động loại instance khỏi traffic. Tên và membership cần ổn định để rules không thay đổi bất ngờ khi bean được thêm/bớt.

Bảo vệ health details bằng authorization. Monitoring probe chỉ cần status tối thiểu; không expose connection strings, hostnames hoặc exception messages cho người dùng không có quyền.

## 5. Health state cần được biểu diễn thành metric

Prometheus alert rules hoạt động trên time series. Có vài cách để chuyển health state thành metrics:
- Micrometer health metrics nếu version và integration cung cấp.
- Custom gauge với giá trị ổn định, ví dụ 1 cho UP và 0 cho DOWN.
- Prometheus blackbox probe kiểm tra endpoint availability.
- Collector đọc Actuator health và xuất trạng thái thành metrics.

Không tạo metric name hoặc label value động theo mỗi lần state thay đổi. Metric contract nên có tên và label set ổn định.

Ví dụ custom gauge minh họa:

~~~java
@Component
class DependencyHealthMetric {

    private final AtomicInteger healthy = new AtomicInteger(1);

    DependencyHealthMetric(MeterRegistry registry) {
        Gauge.builder("app.dependency.health", healthy, AtomicInteger::get)
                .tag("dependency", "catalog-db")
                .register(registry);
    }

    void markUp() {
        healthy.set(1);
    }

    void markDown() {
        healthy.set(0);
    }
}
~~~

Đây chỉ là ví dụ về gauge số. Trong production, không nên duy trì health state thứ hai độc lập với HealthIndicator vì hai trạng thái có thể lệch nhau. Tốt hơn là dùng một nguồn sự thật và adapter/collector chuyển đổi trạng thái đó sang metric. Tránh gọi health check nặng mỗi lần scrape.

## 6. Phân biệt app health với scrape health

Prometheus có metric `up` cho scrape target. `up == 0` nghĩa là Prometheus không scrape được target thành công; nó không chứng minh ứng dụng đã trả health DOWN. Nguyên nhân có thể là process không chạy, port đóng, network policy/firewall/DNS lỗi, scrape path/port sai, TLS/authentication cấu hình sai hoặc timeout.

Ngược lại, target có thể scrape thành công (`up == 1`) trong khi health group báo DOWN. Hai tín hiệu trả lời hai câu hỏi khác nhau và nên có alert/runbook riêng.

Ví dụ alert scrape failure:

~~~yaml
groups:
  - name: spring-boot-availability
    rules:
      - alert: SpringBootScrapeFailed
        expr: up{job="spring-boot"} == 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Không scrape được Spring Boot target"
          description: "Kiểm tra process, network, port, TLS và scrape configuration."
~~~

Rule này cảnh báo monitoring path bị lỗi. Nó không thay thế alert về readiness hoặc business availability.

## 7. Alert theo readiness và service capacity

Một instance readiness DOWN không phải lúc nào cũng cần page. Theo dõi số replicas ready và desired replicas để đánh giá capacity toàn service.

Ví dụ nếu Kubernetes state metrics được thu thập:

~~~yaml
- alert: SpringBootReadyReplicasLow
  expr: |
    kube_deployment_status_replicas_available{
      namespace="production",
      deployment="order-service"
    }
    <
    kube_deployment_spec_replicas{
      namespace="production",
      deployment="order-service"
    }
  for: 5m
  labels:
    severity: page
  annotations:
    summary: "Order service thiếu replicas sẵn sàng"
    description: "Số replicas available thấp hơn số replicas mong muốn trong 5 phút."
~~~

Tên metric và labels phụ thuộc kube-state-metrics/version/deployment. Nếu không có Kubernetes metrics, dùng service discovery hoặc application metrics tương đương. Tránh hard-code ví dụ vào môi trường mà không xác minh labels.

Có thể alert khi tỷ lệ ready thấp hơn ngưỡng:

~~~promql
sum by (namespace, deployment) (kube_deployment_status_replicas_available)
/
sum by (namespace, deployment) (kube_deployment_spec_replicas)
< 0.8
~~~

Cần xử lý trường hợp desired replicas bằng 0 và phân biệt rollout có chủ đích. Alert capacity nên phản ánh khả năng phục vụ traffic, không chỉ một pod đang thay thế.

## 8. Alert cho dependency health

Dependency alert nên gắn với tác động thực tế. Ví dụ database health DOWN trong vài phút có thể cần cảnh báo, nhưng nếu health indicator timeout do probe query quá nặng thì alert có thể phản ánh chính health check overload.

Một metric trạng thái có label bounded có thể được dùng:

~~~promql
app_dependency_health{dependency="catalog-db"} == 0
~~~

Ví dụ rule:

~~~yaml
- alert: SpringBootCriticalDependencyDown
  expr: app_dependency_health{dependency=~"catalog-db|message-broker"} == 0
  for: 3m
  labels:
    severity: page
  annotations:
    summary: "Dependency thiết yếu đang DOWN"
    description: "Kiểm tra dependency health, connection pool, error rate và trace liên quan."
~~~

Không gắn dependency URL, hostname động, tenant ID hoặc exception message vào labels. Dùng logical dependency name với tập giá trị nhỏ. Nếu dependency optional, dùng warning hoặc dashboard-only signal tùy degraded mode.

## 9. for, flapping và alert stability

Health state có thể đổi nhanh trong lúc deploy, restart hoặc dependency chập chờn. Alert rule với `for` yêu cầu expression duy trì đúng trong một khoảng thời gian trước khi alert chuyển sang firing.

~~~yaml
- alert: SpringBootReadinessDegraded
  expr: app_readiness_status == 0
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Instance chưa sẵn sàng"
~~~

Chọn `for` dựa trên scrape interval, health indicator timeout, readiness propagation/rollout duration, mức độ nghiêm trọng khi capacity giảm và thời gian hệ thống chịu được degraded mode.

Không đặt `for` quá dài khiến incident quan trọng bị phát hiện muộn. Cũng không đặt quá ngắn khiến một scrape miss đơn lẻ tạo page. Dùng `for` để lọc transient condition; dùng grouping/inhibition để giảm notification storm.

Alertmanager có thể group theo alertname, service, cluster hoặc namespace. Inhibition có thể suppress alert chi tiết khi alert cấp cao hơn đã firing, ví dụ suppress từng pod alerts khi toàn cluster outage đã được xác nhận. Không group quá rộng đến mức che mất hai incidents độc lập.

## 10. Severity, routing và ownership

Severity nên gắn với tác động và thời gian phản ứng:

| Severity | Khi nào dùng | Route gợi ý |
| --- | --- | --- |
| page/critical | Service mất khả năng phục vụ hoặc capacity dưới ngưỡng an toàn. | On-call ngay lập tức. |
| warning | Một dependency/instance degraded nhưng còn capacity. | Kênh vận hành hoặc ticket. |
| info | Chuyển trạng thái dự kiến, rollout hoặc maintenance. | Dashboard/event log. |

Mỗi alert nên có owner/team, service/environment/cluster labels ổn định, summary mô tả tác động, description nêu tín hiệu và hướng kiểm tra, runbook reference đã được xác thực, routing policy và escalation rõ.

Không đưa dynamic identifiers vào labels chỉ để hiển thị trong notification. Annotations phù hợp hơn cho nội dung giải thích; labels cần bounded để grouping ổn định.

## 11. Dashboard cho health state

Dashboard nên thể hiện cả trạng thái hiện tại và xu hướng:
- Tổng số instances UP/ready.
- Desired vs available replicas.
- Readiness/liveness failures theo thời gian.
- Dependency health theo logical name.
- Restart count và restart rate.
- Scrape up theo target.
- HTTP error rate/latency khi health degraded.
- Alert state và deployment annotations.

Không dùng một đèn xanh tổng hợp duy nhất để kết luận hệ thống khỏe. Dashboard tốt cho phép drill-down từ service capacity sang instance, rồi tới dependency và traces/logs liên quan.

~~~mermaid
flowchart TD
    Service["Service health overview"]
    Service --> Capacity["Ready / desired replicas"]
    Service --> Probe["Liveness and readiness"]
    Service --> Dependencies["Dependency states"]
    Service --> Scrape["Scrape availability"]
    Capacity --> Instance["Instance drill-down"]
    Dependencies --> Metrics["Latency / errors / pool metrics"]
    Instance --> Trace["Trace and log investigation"]
~~~

Dùng annotations cho deploy/maintenance windows để người trực phân biệt trạng thái chuyển đổi có chủ đích với incident.

## 12. Kiểm thử alert rules

Alert rule cần được test bằng input series mẫu. Với Prometheus, dùng `promtool test rules` để xác minh expression, `for` duration, labels và annotations.

Ví dụ test file khái niệm:

~~~yaml
rule_files:
  - alerts.yml

evaluation_interval: 1m

tests:
  - interval: 1m
    input_series:
      - series: 'app_readiness_status{service="order-service",instance="a"}'
        values: '1 0 0 0 0'
    alert_rule_test:
      - eval_time: 4m
        alertname: SpringBootReadinessDegraded
        exp_alerts:
          - exp_labels:
              service: order-service
              instance: a
              severity: warning
~~~

Test format và expected labels cần khớp Prometheus version. Nếu rule có `for: 2m`, chọn evaluation time đủ sau khi expression bắt đầu thỏa điều kiện. Thêm test cho healthy state, DOWN ngắn hơn for, DOWN kéo dài, recovery, readiness của một instance nhưng capacity còn đủ, scrape failure tách biệt health DOWN và dependency optional chỉ tạo warning.

Ngoài rule tests, chạy integration test cho health metric adapter/collector để bảo đảm metric phản ánh cùng source of truth với Actuator health.

## 13. Fault injection và kiểm thử vận hành

Dùng môi trường test/staging để tạo trạng thái có kiểm soát:
- Làm health indicator trả DOWN.
- Ngắt database/broker test dependency.
- Làm endpoint health timeout.
- Dừng một instance để kiểm tra up.
- Làm readiness REFUSING_TRAFFIC trong rollout giả lập.
- Khôi phục dependency và xác minh alert resolved.
- Gửi nhiều transitions để kiểm tra flapping/grouping.

Không fault-inject trực tiếp trên production nếu chưa có change/incident authorization. Dùng canary/staging và giới hạn blast radius. Kiểm tra notification đến đúng route, có owner và runbook, không chỉ xác minh Prometheus expression.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Health DOWN nhưng không có alert | Chưa có metric adapter/scrape hoặc rule sai metric name. | Kiểm tra health endpoint, scrape target và series thực tế. |
| up == 0 nhưng app vẫn healthy | Scrape path/network/TLS/auth lỗi. | Kiểm tra Prometheus target page và kết nối từ scraper. |
| Alert firing trong rollout bình thường | for ngắn hoặc rule theo từng pod. | Dùng service capacity và rollout-aware policy. |
| Alert chập chờn | Health indicator timeout ngắn, dependency flapping hoặc thiếu for. | Kiểm tra latency, timeout, scrape interval và grouping. |
| Readiness DOWN nhưng không ảnh hưởng traffic | Instance dư capacity hoặc group quá nghiêm. | Đối chiếu desired/available replicas và degraded mode. |
| Toàn service bị page vì optional dependency | Optional group bị dùng như readiness/page signal. | Tách dependency alert theo criticality. |
| Alert không resolve sau khi health UP | Series stale, rule expression/labels hoặc scrape lag. | Kiểm tra latest samples và evaluation state. |
| Notification lặp quá nhiều | Grouping/inhibition/repeat interval sai. | Rà soát Alertmanager routing tree. |
| Alert không có runbook | Rule thiếu annotation hoặc ownership metadata. | Bổ sung owner, action và runbook reference. |
| Dashboard UP nhưng users gặp lỗi | Health indicators không phản ánh business path. | Đối chiếu HTTP SLI, latency, error rate và traces. |

## 15. Runbook: alert health state đang firing

1. Xác định alert name, service, environment, cluster và affected instances.
2. Kiểm tra alert expression và thời điểm bắt đầu firing.
3. Xác minh Prometheus scrape up để phân biệt scrape failure với health DOWN.
4. Truy vấn health group tương ứng qua management interface được phép.
5. Kiểm tra readiness/liveness và số replicas available so với desired.
6. Xác định dependency indicator đang DOWN và đối chiếu dependency latency/error metrics.
7. Kiểm tra deployment/maintenance events gần thời điểm alert.
8. Mở traces/logs có correlation để tìm nguyên nhân; không dựa vào health status đơn lẻ.
9. Đánh giá service capacity và user impact trước khi scale/restart.
10. Áp dụng runbook dependency/service tương ứng; tránh restart hàng loạt khi shared dependency đang outage.
11. Theo dõi alert resolved và xác minh readiness/capacity trở lại bình thường.
12. Ghi nhận nguyên nhân, thời gian phát hiện/khôi phục và điều chỉnh rule nếu false positive.

## 16. Bài tập tự kiểm tra

### Bài 1 — Readiness DOWN một pod

Một pod readiness DOWN trong rollout nhưng service vẫn đủ replicas. Có nên page ngay không?

**Đáp án:** Thường không. Theo dõi capacity và rollout context; chỉ page khi available replicas/capacity xuống dưới ngưỡng hoặc tác động người dùng xuất hiện.

### Bài 2 — up == 0

Prometheus báo up == 0 nhưng operator gọi health endpoint trực tiếp thấy UP. Khả năng nào cần kiểm tra?

**Đáp án:** Scrape path/port, DNS, network policy, TLS/authentication hoặc timeout giữa Prometheus và target. up đo scrape success, không phải application health status.

### Bài 3 — Health DOWN không có metric

Actuator trả DOWN nhưng Prometheus không có series health. Nguyên nhân thường gặp?

**Đáp án:** Health JSON chưa được chuyển thành metric; thiếu adapter/exporter hoặc scrape config. Expose endpoint không tự tạo gauge health trong mọi setup.

### Bài 4 — Alert flapping

Dependency health đổi UP/DOWN mỗi 20 giây. Cách giảm notification storm?

**Đáp án:** Kiểm tra probe timeout/cadence và dependency latency, dùng for phù hợp, group alerts và inhibition. Không tăng for quá dài nếu service đang mất khả năng phục vụ.

### Bài 5 — Optional dependency

Search service DOWN nhưng fallback cache vẫn phục vụ request. Nên đặt severity nào?

**Đáp án:** Thường là warning hoặc dashboard signal theo degraded-mode policy, không page như service outage nếu user impact và capacity vẫn trong SLO.

### Bài 6 — Dashboard xanh nhưng request lỗi

Health groups UP nhưng HTTP 5xx tăng. Cần bổ sung tín hiệu gì?

**Đáp án:** HTTP error rate, latency/SLO, dependency metrics và traces. Health indicators chỉ phản ánh checks đã cấu hình, không đại diện toàn bộ business correctness.

## 17. Checklist triển khai

- [ ] Health groups phản ánh đúng liveness, readiness và dependency criticality.
- [ ] Có nguồn metric rõ ràng cho health state; không giả định JSON tự thành metric.
- [ ] Scrape up được alert riêng với application health.
- [ ] Alert theo service capacity khi phù hợp, không page mọi pod readiness transition.
- [ ] Dependency optional có severity/routing phù hợp degraded mode.
- [ ] Rules có for dựa trên scrape cadence và user impact.
- [ ] Labels ổn định, bounded; không chứa request/tenant/trace IDs hoặc exception messages.
- [ ] Alert có owner, severity, summary, description và runbook.
- [ ] Alertmanager grouping, inhibition và repeat interval được kiểm tra.
- [ ] Dashboard hiển thị ready/desired replicas, dependency states và scrape health.
- [ ] HTTP error rate/latency được dùng bổ sung cho health state.
- [ ] Prometheus rule tests bao phủ healthy, transient DOWN, sustained DOWN và recovery.
- [ ] Integration test xác minh health adapter dùng đúng source of truth.
- [ ] Fault injection được chạy trong staging/canary với blast radius giới hạn.
- [ ] Notification được xác minh đến đúng on-call route.
- [ ] Có runbook và quy trình review false positives sau incident.

**Ghi nhớ:** Alert theo health state cần một pipeline rõ từ Actuator health group tới metric, rule, Alertmanager và runbook. Phân biệt readiness/liveness với dependency health và scrape availability; alert theo tác động/capacity, dùng for cùng grouping để giảm flapping, giữ labels bounded và kiểm thử cả firing lẫn recovery. Health state là một tín hiệu vận hành; kết hợp nó với HTTP SLI, metrics, logs và traces để quyết định hành động.
