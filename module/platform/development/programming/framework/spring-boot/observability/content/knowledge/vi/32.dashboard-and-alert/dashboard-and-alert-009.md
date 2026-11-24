# Alert theo error rate trong Spring Boot

Error rate cho biết tỷ lệ request hoặc operation thất bại trong một khoảng thời gian. Đây là tín hiệu quan trọng để phát hiện regression sau deployment, dependency outage, lỗi cấu hình và sự cố làm suy giảm trải nghiệm người dùng. Tuy nhiên, một con số phần trăm đơn lẻ không đủ để quyết định có cần đánh thức on-call hay không: 100% lỗi trên một request trong một phút có thể chỉ là traffic rất thấp, trong khi 1% lỗi trên hàng chục nghìn request mỗi phút có thể ảnh hưởng nhiều người dùng.

**Alert theo error rate** là cảnh báo dựa trên tỷ lệ operation thất bại so với tổng số operation đủ điều kiện trong một cửa sổ thời gian. Để alert có ý nghĩa, cần định nghĩa rõ numerator, denominator, phạm vi traffic, phân loại lỗi, traffic tối thiểu và mức độ ảnh hưởng theo SLO. Trong Spring Boot, Micrometer có thể ghi request metrics; Prometheus hoặc hệ thống tương đương thu thập và đánh giá time series; Alertmanager hoặc nền tảng alerting định tuyến thông báo tới nhóm chịu trách nhiệm.

Bài học thuộc chương **Dashboard và alert** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực. Bài này tập trung vào cách định nghĩa error-rate SLI, viết query, chọn ngưỡng và xây dựng alert có thể hành động.

## Mục tiêu học tập

1. Định nghĩa error rate bằng numerator và denominator nhất quán.
2. Phân biệt HTTP server errors, business failures và dependency errors.
3. Xây dựng error-rate SLI từ Micrometer metrics.
4. Viết PromQL tính tỷ lệ lỗi theo cửa sổ thời gian.
5. Xử lý traffic thấp, counter reset và thiếu dữ liệu.
6. Chọn ngưỡng alert dựa trên SLO và mức ảnh hưởng.
7. Áp dụng multi-window, multi-burn-rate alerts.
8. Giảm false positives bằng minimum traffic và grouping hợp lý.
9. Định tuyến cảnh báo theo severity, service và ownership.
10. Kiểm thử alert rules và dùng logs/traces để điều tra.

## 1. Error rate là gì?

Error rate là tỷ lệ operation được xác định là thất bại trong tổng số operation được quan sát:

```text
error_rate = failed_operations / total_operations

error_rate_percent = error_rate * 100
```

Ví dụ trong 5 phút có 10.000 HTTP requests, 250 request được phân loại là lỗi:

```text
error_rate = 250 / 10000 = 0.025 = 2.5%
```

Công thức chỉ có ý nghĩa khi numerator là tập con của denominator và cả hai dùng cùng scope, label dimensions và time window.

### 1.1. Chọn operation được đo

Với HTTP API, có thể dùng số request server hoàn tất. Với message consumer, có thể dùng message processing attempts hoặc business messages được xử lý. Với scheduled task, có thể dùng execution failures trên tổng execution. Không gộp các loại operation khác semantics vào cùng một error-rate SLI.

### 1.2. HTTP status không phải toàn bộ business error

HTTP 5xx thường là server-side failures; 4xx thường thể hiện request không hợp lệ hoặc bị từ chối theo contract. Tuy nhiên, phân loại SLI tùy sản phẩm:
- 5xx thường được tính là lỗi dịch vụ.
- 4xx do client gửi sai có thể không tính vào availability SLI.
- 429 có thể là overload/throttling và cần theo dõi riêng.
- Một API có thể trả HTTP 200 nhưng payload biểu thị business operation thất bại; nếu đó là outcome người dùng quan tâm, cần business metric riêng.

Không coi mọi status 4xx là service outage, cũng không bỏ qua 429 nếu người dùng không thể hoàn thành workload.

## 2. Xác định numerator và denominator

Trước khi viết alert, ghi rõ định nghĩa SLI:

| Thành phần | Ví dụ cho HTTP API |
|---|---|
| Scope | Một service hoặc route class |
| Denominator | Tổng request hợp lệ đã hoàn tất |
| Numerator | Request thuộc nhóm lỗi theo policy |
| Window | 5 phút, 1 giờ hoặc 6 giờ |
| Exclusions | Health probes, static assets hoặc route không thuộc SLO |
| Grouping | service, environment, route template |
| Owner | Team chịu trách nhiệm service |

Numerator và denominator phải có cùng filter. Nếu denominator loại health checks nhưng numerator vẫn chứa health-check failures, tỷ lệ sẽ sai.

### 2.1. Route template, không phải raw path

Dùng route template như /orders/{id} hoặc route label ổn định. Raw path chứa order ID có thể tạo cardinality cao và khiến alert tách thành hàng nghìn series. Route template cũng giúp xác định endpoint nào có lỗi mà không lộ identifier.

### 2.2. Phân loại lỗi có chủ đích

Tách lỗi theo category hữu ích:
- server error;
- timeout;
- throttling;
- dependency failure;
- validation/client error;
- business rejection.

Không thêm exception message hoặc raw SQL/URL làm label. Dùng tập error categories nhỏ, được chuẩn hóa.

## 3. Metrics trong Spring Boot

Spring Boot Actuator và Micrometer có thể ghi HTTP server request metrics khi instrumentation phù hợp được bật. Một meter phổ biến là http.server.requests; registry sẽ chuyển tên theo convention riêng, ví dụ Prometheus thường dùng dạng http_server_requests_seconds_count cho timer count.

Tên và tags thực tế phụ thuộc Spring Boot, Micrometer, web stack và registry version. Trước khi viết rule, kiểm tra /actuator/metrics, /actuator/prometheus hoặc scrape output của ứng dụng.

Các dimensions thường hữu ích:
- method;
- uri/route template;
- status;
- outcome;
- exception;
- service/environment qua resource hoặc scrape labels.

Không giả định mọi version đều cung cấp cùng tag keys. Kiểm tra series thực tế và tránh đưa user ID, request ID, trace ID, raw URL hoặc exception message vào metric labels.

### 3.1. Counter và timer

Micrometer Timer thường cung cấp count và total time; Prometheus registry có thể expose timer count như counter. Error-rate query thường dùng rate() trên counter count, không dùng tổng duration để tính tỷ lệ lỗi.

### 3.2. Counter reset

Khi process restart, counter có thể reset về 0. Prometheus rate() xử lý counter reset khi tính tốc độ tăng trong range vector. Không tự lấy chênh lệch hai instant samples rồi chia nếu không xử lý reset và scrape gaps.

## 4. PromQL tính error rate

Giả sử Prometheus scrape metric http_server_requests_seconds_count và có label status, service. Ví dụ query:

```promql
sum(rate(http_server_requests_seconds_count{
  service="checkout",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  service="checkout"
}[5m]))
```

Kết quả là tỷ lệ request 5xx trên tổng request trong 5 phút. Nếu muốn phần trăm, nhân 100.

### 4.1. Tránh chia cho zero

Khi không có traffic, denominator bằng 0 hoặc không có series. Không coi giá trị NaN/absent là error rate bằng 0 một cách vô điều kiện. Alert nên có điều kiện traffic đủ lớn hoặc tách riêng no-traffic alert nếu service cần có traffic liên tục.

### 4.2. Theo route

Có thể group theo route template:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_count{
    service="checkout",
    status=~"5.."
  }[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count{
    service="checkout"
  }[5m])
)
```

Dùng route labels có cardinality thấp. Với dashboard, group theo service/route; với paging, thường cần tổng service SLI để tránh một route ít traffic tạo nhiều alerts nhỏ.

### 4.3. Chọn status filter

Nếu SLI chỉ tính 5xx, query status=~"5.." là ví dụ. Nếu 429 thuộc policy lỗi, thêm status 429 hoặc dùng outcome/error category đã chuẩn hóa. Nếu 4xx client errors không thuộc SLO, không đưa vào numerator.

## 5. Traffic thấp và minimum request volume

Một tỷ lệ trên denominator nhỏ dễ dao động. Ví dụ một request lỗi trên hai request tạo error rate 50%, nhưng mức ảnh hưởng tuyệt đối có thể thấp. Cần kết hợp tỷ lệ với request volume.

Ví dụ điều kiện traffic:

```promql
sum(rate(http_server_requests_seconds_count{
  service="checkout"
}[5m])) * 300 > 100
```

Biểu thức minh họa yêu cầu hơn 100 requests trong cửa sổ 5 phút. Chọn minimum volume theo traffic profile và mức rủi ro; không sao chép ngưỡng ví dụ cho mọi service.

### 5.1. Không có traffic cũng có thể là sự cố

Với service phải nhận traffic liên tục, request rate bằng 0 có thể biểu thị routing/DNS/gateway failure. Đây là alert availability/traffic riêng, không nên ép error rate thành 100% khi không có request.

### 5.2. Traffic burst

Khi traffic tăng đột ngột, error rate có thể dao động do rollout, autoscaling hoặc dependency warm-up. Dùng cửa sổ đủ dài và multi-window để phân biệt spike rất ngắn với burn kéo dài.

## 6. Ngưỡng alert dựa trên SLO

Nếu SLO availability là 99.9% trong 30 ngày, error budget tương ứng là 0.1% request được phép thất bại trong kỳ. Ngưỡng alert nên phản ánh tốc độ tiêu thụ budget (burn rate), không chỉ một phần trăm tùy ý.

```text
error_budget_fraction = 1 - availability_slo
burn_rate = observed_error_rate / error_budget_fraction
```

Ví dụ SLO 99.9%, error budget fraction = 0.001. Nếu error rate hiện tại là 1%, burn rate = 10 lần tốc độ cho phép trung bình.

### 6.1. Error budget và user impact

Cùng error rate có thể có ảnh hưởng khác nhau tùy traffic, endpoint và user journey. Một route checkout thất bại có thể nghiêm trọng hơn một route optional. Xác định SLI theo workload người dùng và SLO đã được thống nhất.

### 6.2. Warning và paging

- Warning: lỗi tăng nhưng budget chưa bị tiêu thụ quá nhanh hoặc ảnh hưởng còn giới hạn.
- Page: burn rate cao, kéo dài và có khả năng làm cạn error budget trước khi hết kỳ SLO.

Severity cần gắn với action cụ thể: warning tạo ticket/notify team; page đánh thức on-call.

## 7. Multi-window, multi-burn-rate alert

Một cửa sổ dài phản ánh xu hướng nhưng phát hiện chậm; cửa sổ ngắn phản ứng nhanh nhưng nhạy với noise. Multi-window alert kết hợp cả hai để chỉ page khi burn rate cao ở cả short và long windows.

Ví dụ burn-rate query cho SLO 99.9%:

```promql
(
  sum(rate(http_server_requests_seconds_count{service="checkout",status=~"5.."}[5m]))
  /
  sum(rate(http_server_requests_seconds_count{service="checkout"}[5m]))
) > 14.4
and
(
  sum(rate(http_server_requests_seconds_count{service="checkout",status=~"5.."}[1h]))
  /
  sum(rate(http_server_requests_seconds_count{service="checkout"}[1h]))
) > 14.4
```

Ví dụ trên dùng burn-rate threshold 14.4 lần error budget và hai cửa sổ 5 phút/1 giờ. Production rule cần thêm minimum traffic, xử lý denominator zero và xác minh các windows phù hợp kỳ SLO. Có thể dùng các cặp window khác theo thời gian phát hiện mong muốn.

### 7.1. Burn rate không phải error percentage

Burn rate là error rate chia cho error budget fraction. Với SLO 99.9%, burn rate 14.4 tương ứng error rate 1.44% (14.4 × 0.1%). Đọc đúng đơn vị để không nhầm threshold.

### 7.2. Alert dài hạn

Dùng cửa sổ dài hơn như 6 giờ hoặc 24 giờ để phát hiện budget bị tiêu thụ chậm nhưng liên tục. Alert này thường có severity thấp hơn page nhanh, tùy policy on-call.

## 8. Prometheus alert rule minh họa

Ví dụ rule đơn giản:

```yaml
groups:
  - name: checkout-error-rate
    rules:
      - alert: CheckoutHighErrorRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              service="checkout",
              status=~"5.."
            }[5m]))
            /
            sum(rate(http_server_requests_seconds_count{
              service="checkout"
            }[5m]))
          ) > 0.02
        for: 10m
        labels:
          severity: warning
          team: commerce
        annotations:
          summary: "Checkout API error rate is elevated"
          description: "5xx ratio exceeded 2% for 10 minutes."
```

Rule này minh họa cấu trúc Prometheus alerting rule; cần bổ sung guard cho traffic thấp/denominator zero và điều chỉnh service labels theo scrape config. Ngưỡng 2% không phải mặc định phù hợp mọi hệ thống.

### 8.1. for duration

for: 10m yêu cầu expression tiếp tục true trong 10 phút trước khi alert firing. Nó giảm noise ngắn hạn nhưng làm chậm phát hiện. Với page burn-rate, thường dùng cửa sổ ngắn/dài kết hợp thay vì chỉ kéo dài for.

### 8.2. Labels và annotations

Labels dùng để grouping/routing: severity, team, service, environment. Annotations mô tả vấn đề và link runbook/dashboard. Không gắn request ID, trace ID hay raw exception vào alert labels; chúng tạo alert fingerprint khác nhau và gây alert flood.

## 9. Dashboard error rate

Dashboard nên hiển thị đồng thời:
- Error rate (%) theo service và route class.
- Failed requests/sec và total requests/sec.
- 4xx, 5xx, 429 tách riêng nếu hữu ích.
- Latency p50/p95/p99.
- Traffic volume.
- Deployment markers.
- Dependency error/latency.
- SLO/error budget burn rate.

### 9.1. Tỷ lệ và số lượng tuyệt đối

Error rate cao với volume thấp và error count cao với volume lớn là hai tình huống khác nhau. Hiển thị cả tỷ lệ và số request lỗi mỗi giây để người trực đánh giá quy mô ảnh hưởng.

### 9.2. Grouping

Dashboard overview theo service; drill-down theo route template, method, status và dependency. Không group theo user/session/request ID.

### 9.3. Correlate deployment

Thêm deployment annotations hoặc release markers vào dashboard. Nếu error rate tăng ngay sau rollout, so sánh version/replica, trace lỗi và thay đổi configuration. Không mặc định deployment là nguyên nhân; dùng evidence.

## 10. Error classification và ownership

Một alert cần trả lời ai xử lý và lỗi thuộc lớp nào. Chuẩn hóa error category và service ownership. Ví dụ:
- application: unhandled exception hoặc bug;
- dependency: database/remote API failure;
- capacity: saturation, throttling hoặc queue overload;
- client: malformed/unauthorized request;
- unknown: chưa phân loại.

Nếu error rate cao do một dependency chung, alert của nhiều service có thể cùng firing. Grouping theo dependency/impact và liên kết runbook giúp tránh nhiều pages trùng cho cùng incident.

## 11. Kiểm thử alert rules

Alert rule phải được test trước khi đưa production. Với Prometheus, dùng promtool test rules hoặc test framework tương ứng.

Kịch bản nên gồm:
1. Không có lỗi, traffic bình thường.
2. Error rate vượt threshold liên tục.
3. Spike lỗi ngắn hơn for/window.
4. Traffic thấp với một vài errors.
5. Không có traffic.
6. Counter reset sau restart.
7. Một route lỗi nhưng toàn service vẫn trong SLO.
8. 429 tăng do throttling.
9. Missing series/scrape target down.
10. Multi-window burn-rate chỉ firing khi cả windows đạt điều kiện.

### 11.1. Synthetic time series

Tạo test samples cho success/failure counters qua nhiều timestamps. Kiểm tra alert state pending/firing/inactive và labels/annotations. Không chỉ chạy query tại một instant vì for duration cần lịch sử.

### 11.2. Kiểm tra routing

Dùng Alertmanager test receiver hoặc notification sink giả lập để xác minh grouping, inhibition, repeat interval và receiver. Không gửi test page tới on-call production.

## 12. Chẩn đoán alert error rate

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Alert firing nhưng user không thấy lỗi | 4xx/client errors bị tính vào numerator | Kiểm tra SLI classification |
| Error rate 100% khi traffic thấp | Denominator rất nhỏ | Minimum volume và absolute count |
| Error rate NaN | Denominator zero/missing series | Query guard và no-traffic alert |
| Alert không firing dù 5xx tăng | Sai labels/status tags hoặc query | Inspect raw series và PromQL |
| Alert firing sau restart | Counter reset hoặc scrape gap | Dùng rate() và kiểm tra target |
| Một route tạo nhiều alerts | Raw path/high-cardinality labels | Route template và alert grouping |
| Alert trễ | Window/for quá dài | Multi-window và detection budget |
| Alert chập chờn | Window ngắn, traffic ít hoặc threshold nhạy | Volume guard và sustained condition |
| Dashboard và alert khác số | Different filters/windows/aggregation | Đồng bộ SLI definition |
| Nhiều services page cùng lúc | Shared dependency outage | Group theo dependency/incident |
| 429 không được phát hiện | Policy bỏ throttling khỏi error category | SLI riêng cho throttling |
| Alert không có owner | Thiếu team/service labels | Metadata ownership và routing |

### Quy trình điều tra

1. Xác nhận alert expression, window, labels và severity.
2. Kiểm tra numerator/denominator raw series.
3. Xác minh status/outcome classification.
4. Kiểm tra traffic volume và scrape gaps.
5. Xem error rate cùng failed requests/sec và latency.
6. So sánh route, service version và deployment markers.
7. Mở traces đại diện cho lỗi để tìm dependency/exception.
8. Đối chiếu logs theo trace ID; không đưa trace ID vào metric labels.
9. Xác định lỗi tập trung ở app, dependency, capacity hay client.
10. Ghi incident timeline và điều chỉnh rule sau khi có evidence.

## 13. Các anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách phù hợp |
|---|---|---|
| Alert theo một lỗi duy nhất | Noise khi traffic thấp | Minimum volume và sustained window |
| Coi mọi 4xx là server failure | Error rate phóng đại | SLI classification |
| Chỉ theo phần trăm | Không thấy absolute impact | Hiển thị request volume/error count |
| Chia cho zero/missing series | NaN hoặc false clear | Guard và no-traffic alert riêng |
| Dùng raw URL làm label | Cardinality và alert flood | Route template |
| Dùng exception message làm label | Series/alert fingerprint bùng nổ | Error category |
| Ngưỡng không liên quan SLO | Page quá nhiều hoặc quá muộn | Burn-rate policy |
| Chỉ dùng cửa sổ ngắn | False positives | Multi-window |
| for duration quá dài cho mọi page | Phát hiện muộn | Window theo detection objective |
| Gộp nhiều services không cùng owner | Không biết ai xử lý | Service/team routing |
| Dùng trace sampling làm error counter | Mẫu traces không đại diện tổng request | Metrics counter không sample |
| Không test rule | Lỗi query/routing tới production | promtool và mock receiver |

## 14. Checklist production

1. **SLI:** numerator/denominator được định nghĩa và phê duyệt?
2. **Scope:** service/route/workload rõ ràng?
3. **Classification:** 4xx, 5xx, 429 và business failures được phân loại?
4. **Metrics:** counter/timer labels ổn định, low-cardinality?
5. **Query:** rate() dùng đúng counter và cùng filters?
6. **Traffic:** minimum volume và no-traffic behavior được xử lý?
7. **SLO:** thresholds/burn rates gắn với error budget?
8. **Windows:** short/long windows phù hợp detection objective?
9. **Severity:** warning/page có action và owner rõ?
10. **Routing:** service/team/environment labels đúng?
11. **Annotations:** có dashboard, runbook và impact description?
12. **Dashboard:** hiển thị rate, absolute count, traffic và latency?
13. **Correlation:** deployment/dependency context sẵn có?
14. **Cardinality:** không có IDs, raw paths hoặc exception messages?
15. **Tests:** traffic thấp, reset, missing series, spike và sustained errors?
16. **Routing tests:** mock receiver không gửi page thật?
17. **Runbook:** on-call có bước kiểm tra numerator/denominator và traces?
18. **Review:** SLI/rules được xem lại khi API contract hoặc SLO đổi?

## 15. Câu hỏi tự đánh giá

**Câu 1.** Error rate được tính như thế nào?

**Gợi ý:** Số operation thất bại chia cho tổng operation đủ điều kiện trong cùng scope và time window.

**Câu 2.** Vì sao cần định nghĩa numerator và denominator trước khi viết query?

**Gợi ý:** Hai tập phải cùng scope/filter; nếu khác nhau, tỷ lệ không phản ánh đúng SLI.

**Câu 3.** Có nên tính mọi HTTP 4xx là service error không?

**Gợi ý:** Không mặc định. Phân loại theo contract; client errors thường tách khỏi availability SLI, còn 429 cần policy riêng.

**Câu 4.** Vì sao error rate 50% trên hai request có thể không cần page?

**Gợi ý:** Volume thấp; cần minimum traffic và absolute impact để tránh false positive.

**Câu 5.** Prometheus rate() giúp gì khi counter reset?

**Gợi ý:** Ước lượng tốc độ tăng và xử lý counter reset trong range vector.

**Câu 6.** Burn rate là gì?

**Gợi ý:** Observed error rate chia cho error budget fraction được phép theo SLO.

**Câu 7.** Multi-window alert có lợi ích gì?

**Gợi ý:** Kết hợp phản ứng nhanh của cửa sổ ngắn với độ ổn định của cửa sổ dài.

**Câu 8.** Vì sao không dùng raw path hoặc trace ID làm alert labels?

**Gợi ý:** Tạo cardinality/fingerprint cao, khiến alert bị phân mảnh và khó grouping.

**Câu 9.** Dashboard error rate nên hiển thị thêm gì ngoài phần trăm?

**Gợi ý:** Total traffic, failed requests/sec, latency, route breakdown và deployment markers.

**Câu 10.** Khi alert firing, nên bắt đầu điều tra từ đâu?

**Gợi ý:** Kiểm tra numerator/denominator, volume, classification, route/version rồi mở traces/logs đại diện.

## Kết luận

**Alert theo error rate chỉ đáng tin khi SLI có numerator, denominator và phạm vi traffic được định nghĩa nhất quán.** Trong Spring Boot, dùng Micrometer request metrics để ghi nhận request outcomes, Prometheus rate() để tính tỷ lệ và alert rules để đánh giá điều kiện theo cửa sổ thời gian. Kết hợp minimum traffic, absolute error volume, SLO burn rate và multi-window để hạn chế false positives mà vẫn phát hiện sự cố nhanh. Dashboard nên hiển thị error rate cùng traffic, latency và deployment markers; alert cần owner, severity, runbook và test routing. Khi cảnh báo xảy ra, kiểm tra raw series rồi dùng logs/traces để tìm nguyên nhân ở application, dependency hoặc capacity.
