# Dashboard error rate cho Spring Boot

Error rate cho biết tỷ lệ request kết thúc với lỗi trong một khoảng thời gian. Đây là một trong những tín hiệu quan trọng nhất để đánh giá độ tin cậy của HTTP service: latency có thể tăng nhẹ mà người dùng chưa nhận thấy, nhưng error rate tăng thường cho thấy request đang thất bại rõ ràng. Một dashboard tốt cần cho biết lỗi đang tăng hay giảm, ảnh hưởng tới route nào, bắt đầu từ khi nào và có liên quan tới dependency hoặc lần triển khai gần đây hay không.

Bài **Dashboard error rate** thuộc chương **Dashboard và alert** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể định nghĩa numerator/denominator của error rate, phân biệt HTTP 4xx và 5xx theo mục tiêu vận hành, xây dựng PromQL từ HTTP server metrics, thiết kế dashboard theo service/route/status, tránh sai số ở traffic thấp, đặt alert theo cửa sổ thời gian và nối dashboard với logs/traces để điều tra.

## 1. Error rate đo điều gì?

Error rate là tỷ lệ request được xem là thất bại trong tổng số request được đánh giá trong cùng một khoảng thời gian:

\[
\text{Error rate} =
\frac{\text{Failed requests}}{\text{Total requests}}
\times 100\%
\]

Ví dụ trong 5 phút, service nhận 10.000 requests và có 250 requests thất bại:

\[
\frac{250}{10\,000}\times 100\% = 2.5\%
\]

Hai thành phần phải dùng cùng scope và cùng time window:

- **Numerator:** số request được phân loại là lỗi.
- **Denominator:** tổng số request thuộc cùng service/route/traffic scope.

Nếu numerator đếm 5xx nhưng denominator chỉ đếm 2xx, tỷ lệ không còn biểu diễn error rate của traffic. Nếu numerator loại probe traffic nhưng denominator vẫn bao gồm probe traffic, tỷ lệ cũng bị lệch.

Error rate là tỷ lệ, không phải số lỗi tuyệt đối. 100 lỗi trong 1.000 requests tương đương 10%; 100 lỗi trong 1 triệu requests chỉ là 0,01%. Dashboard nên hiển thị cả error count/rate và total request rate để người xem hiểu quy mô ảnh hưởng.

## 2. Chọn định nghĩa lỗi phù hợp với service

Không phải mọi HTTP 4xx đều là lỗi của server. Ví dụ 400 có thể là input không hợp lệ, 401 là chưa xác thực, 403 là thiếu quyền và 404 có thể là tài nguyên không tồn tại theo contract. Những response này có thể là kết quả nghiệp vụ dự kiến.

Một phân loại phổ biến:

| Nhóm | Ví dụ | Có tính vào service error rate? |
| --- | --- | --- |
| 2xx | 200, 201, 204 | Không |
| 3xx | 301, 304 | Thường không, tùy semantics |
| 4xx do client | 400, 401, 403, 404, 409, 422 | Thường theo dõi riêng |
| 5xx do service/gateway | 500, 502, 503, 504 | Thường có |
| Transport failure | Timeout, connection reset, request không có response | Cần metric riêng hoặc instrumentation phù hợp |

Định nghĩa phải theo SLO và contract của API. Với một API mà 404 biểu thị lỗi nghiệp vụ quan trọng, có thể theo dõi riêng hoặc đưa vào một error budget cụ thể. Đừng dùng một quy tắc toàn cục cho mọi endpoint nếu semantics khác nhau.

Nên có ít nhất ba chỉ số:

1. Server error rate: tỷ lệ 5xx trên tổng request.
2. Client error rate: tỷ lệ 4xx trên tổng request, có thể tách 401/403/404/409/422.
3. Request failure/timeout rate: các lỗi không thể hiện thành HTTP response nếu instrumentation có thể ghi nhận.

## 3. HTTP server metrics trong Spring Boot

Với Spring Boot Actuator và Micrometer, HTTP server requests thường được ghi nhận qua một Timer. Trong Prometheus, các series phổ biến có tên gần với:

```text
http_server_requests_seconds_count
http_server_requests_seconds_sum
http_server_requests_seconds_max
```

Các label thường gặp gồm method, status, uri, exception và outcome. Tên series/labels có thể thay đổi theo Spring Boot, Micrometer version, registry convention và framework adapter. Trước khi viết dashboard, mở endpoint Prometheus của chính ứng dụng để xác minh metric names và label keys thực tế.

Ví dụ cấu hình expose endpoint Prometheus:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Endpoint này cần được bảo vệ theo network/authentication policy. Prometheus scraper phải truy cập đúng management endpoint và service discovery phải gắn labels service/instance phù hợp.

## 4. Xây dựng numerator và denominator bằng PromQL

Giả sử metric của ứng dụng có labels status, uri, method. Query sau minh họa request rate tổng:

```promql
sum(rate(http_server_requests_seconds_count[5m]))
```

Request rate 5xx:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
```

Error rate 5xx:

```promql
100 *
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

Đây là ví dụ cơ bản. Nếu muốn tỷ lệ theo service, thêm cùng label filter vào cả numerator và denominator. Nếu dashboard có nhiều service, group theo service ở cả hai phía:

```promql
100 *
sum by (service) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (service) (
  rate(http_server_requests_seconds_count[5m])
)
```

Label service phải tồn tại trong series. Nếu Prometheus target labels được gắn ở scrape layer, query có thể dùng label đó; nếu không, điều chỉnh theo schema thực tế.

## 5. Tỷ lệ theo route

Service-level error rate cho biết sức khỏe tổng thể, nhưng không chỉ ra endpoint nào đang lỗi. Có thể group theo route template:

```promql
100 *
sum by (uri) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

Dùng route template như /api/orders/{id}, không dùng raw request URI như /api/orders/12345. Route template giúp gom dữ liệu và giữ cardinality có giới hạn.

Khi một route có ít traffic, tỷ lệ có thể nhảy từ 0% lên 100% chỉ vì một request lỗi. Hiển thị request count/rate bên cạnh tỷ lệ và tránh xếp hạng route chỉ dựa trên phần trăm khi denominator rất nhỏ.

## 6. Theo dõi 4xx và 5xx riêng

Client error rate:

```promql
100 *
sum(rate(http_server_requests_seconds_count{status=~"4.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

Server error rate:

```promql
100 *
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

Có thể tách các status thường gặp:

```promql
sum by (status) (
  rate(http_server_requests_seconds_count{status=~"4..|5.."}[5m])
)
```

Không gộp 4xx và 5xx vào một alert duy nhất nếu đội vận hành cần hành động khác nhau. Ví dụ 401 tăng có thể là client credential/configuration issue; 503 tăng có thể là service overload hoặc dependency unavailable.

## 7. Xử lý zero traffic và low traffic

Khi denominator bằng 0, phép chia error rate không có ý nghĩa. PromQL có thể trả về no data/NaN tùy biểu thức và series hiện diện. Không ép giá trị thành 0 một cách thiếu suy nghĩ, vì “không có request” không giống “có request và không lỗi”.

Có thể dùng query có guard:

```promql
(
  100 *
  sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
)
and
sum(rate(http_server_requests_seconds_count[5m])) > 0
```

Với alert, kết hợp error rate với request volume tối thiểu để tránh cảnh báo từ một request lỗi:

```promql
(
  100 *
  sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
  /
  sum(rate(http_server_requests_seconds_count[5m]))
) > 5
and
sum(rate(http_server_requests_seconds_count[5m])) > 1
```

Ngưỡng 5% và 1 request/giây chỉ là ví dụ. Chọn ngưỡng theo SLO, traffic baseline, criticality và error budget. Đối với route quan trọng nhưng ít traffic, có thể cần alert theo số lỗi tuyệt đối hoặc synthetic checks thay vì chỉ theo tỷ lệ.

## 8. Loại trừ health probes và traffic không đại diện người dùng

Kubernetes liveness/readiness probes thường tạo request định kỳ. Nếu đưa probe traffic vào denominator, service-level request rate có thể bị phóng đại khi user traffic thấp. Nếu probe route thất bại, error rate có thể tăng do orchestration checks chứ không phải user request.

Nếu metric có route label ổn định, có thể loại health paths:

```promql
sum(
  rate(http_server_requests_seconds_count{
    status=~"5..",
    uri!~"/actuator/health.*"
  }[5m])
)
```

Phải áp dụng cùng filter vào denominator. Không loại traffic bằng raw URI nếu route label không chuẩn hóa. Cũng không loại mọi request nội bộ theo cách che khuất lỗi thực; ghi rõ scope dashboard là user traffic, internal traffic hay toàn bộ server requests.

## 9. Dashboard error rate nên có những panel nào?

Một dashboard phục vụ incident response nên trả lời lần lượt: có lỗi không, mức độ ảnh hưởng ra sao, lỗi ở đâu và bắt đầu khi nào.

| Panel | Hiển thị | Câu hỏi |
| --- | --- | --- |
| Service error rate | 5xx % theo thời gian | Tỷ lệ lỗi hiện tại và xu hướng? |
| Request volume | Requests/second | Denominator có đủ lớn để diễn giải tỷ lệ? |
| Error count/rate | 4xx và 5xx riêng | Có bao nhiêu lỗi và loại nào tăng? |
| Error by status | 500/502/503/504 | Status nào chiếm phần lớn? |
| Error by route | Top routes theo 5xx rate/count | Endpoint nào bị ảnh hưởng? |
| Latency | p50/p95/p99 | Lỗi có đi cùng latency tăng không? |
| Instance breakdown | Error rate theo instance/pod | Lỗi tập trung ở một replica? |
| Deployment markers | Version/release timeline | Có trùng thời điểm deploy/config change? |
| Dependency signals | DB, messaging, downstream errors | Có dependency nào liên quan? |

Nên đặt service-level panels ở đầu dashboard, sau đó mới đến route/instance breakdown. Tránh đưa hàng trăm routes vào một panel mặc định; dùng top-k và drilldown.

## 10. Kết hợp error rate với latency và saturation

Error rate đơn độc không giải thích nguyên nhân. Kết hợp ba nhóm RED:

- **Rate:** request rate.
- **Errors:** error rate/count.
- **Duration:** request latency distribution.

Thêm saturation signals như CPU throttling, memory pressure, thread pool saturation, Hikari pending connections, queue depth và downstream connection errors.

Một số mẫu diễn giải:

| Error rate | Latency | Saturation/dependency | Hướng điều tra |
| --- | --- | --- | --- |
| Tăng | Tăng | CPU cao | CPU saturation hoặc workload mới |
| Tăng | Tăng | Hikari pending cao | DB connection pool hoặc query/transaction |
| Tăng | Bình thường | Dependency 5xx tăng | Downstream failure hoặc timeout mapping |
| Tăng | Bình thường | Một pod có lỗi | Instance-specific config/resource |
| 4xx tăng | Bình thường | Không có dependency lỗi | Client behavior, auth hoặc API contract |
| 5xx tăng sau deploy | Tăng hoặc bình thường | Không rõ | So sánh version, config và traces |

Đây là gợi ý định hướng, không phải kết luận tự động. Dùng traces/logs để xác minh một request cụ thể thất bại ở controller, service, database hay downstream client.

## 11. Alert error rate theo cửa sổ thời gian

Alert chỉ dựa trên một mẫu ngắn dễ nhạy với spike. Một rule đơn giản:

```yaml
groups:
  - name: spring-boot-http-errors
    rules:
      - alert: HighHttp5xxRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
            /
            sum(rate(http_server_requests_seconds_count[5m]))
          ) > 0.05
          and
          sum(rate(http_server_requests_seconds_count[5m])) > 1
        for: 10m
        labels:
          severity: page
        annotations:
          summary: HTTP 5xx rate is elevated
          description: Check service error dashboard and recent traces.
```

Rule này chỉ minh họa. Production cần thêm label service/environment, scope filter, runbook URL và ngưỡng dựa trên SLO. Nếu metric không có series khi service không có traffic, cần kiểm tra no-data behavior của alerting system.

Với service có SLO, alert theo error budget burn rate thường hữu ích hơn một threshold cố định. Burn-rate alert kết hợp nhiều time windows để phát hiện cả sự cố nhanh ảnh hưởng lớn lẫn suy giảm kéo dài. Cần dùng cùng SLI definition với SLO; không dùng numerator khác nhau giữa dashboard và alert.

## 12. Error budget và SLO

Nếu SLO availability là 99,9%, error budget cho phép tối đa 0,1% requests thất bại trong cửa sổ đánh giá. Error rate 5xx 0,1% không nhất thiết là mức an toàn ở mọi thời điểm; nếu traffic thấp hoặc lỗi tập trung vào một route critical, tác động có thể lớn.

Ví dụ:

\[
\text{Availability} = 1 - \text{Error rate}
\]

Với error rate 0,2%, availability theo định nghĩa đó là 99,8%. Chỉ đúng khi numerator/denominator khớp chính xác với SLI đã định nghĩa.

Dashboard nên cho thấy:

- SLO target và current SLI.
- Error budget remaining.
- Burn rate theo nhiều cửa sổ.
- Tổng request volume.
- Route/operation critical có error riêng nếu SLO áp dụng theo route.

Không coi mọi HTTP 4xx là availability failure nếu SLO không định nghĩa chúng là lỗi service.

## 13. Cardinality và labels

Error dashboard thường group theo status, method, route, service, environment và instance. Những labels này cần có tập giá trị hữu hạn hoặc được quản lý:

- Dùng route template, không dùng raw path.
- Không dùng request ID, trace ID, user ID, order ID hoặc exception message làm metric labels.
- Không đưa query string vào uri label.
- Giữ status ở dạng mã/nhóm hữu hạn.
- Tránh label chứa dynamic hostnames hoặc arbitrary tenant names nếu số lượng lớn.

Cardinality cao làm tăng memory và chi phí query của Prometheus, đồng thời dashboard có thể chậm hoặc vượt giới hạn series. Nếu cần drilldown theo trace ID, chuyển từ metric sang exemplar/trace link hoặc logs có correlation.

## 14. Liên kết dashboard với logs và traces

Metrics cho biết xu hướng và mức độ; logs/traces cung cấp chi tiết để tìm nguyên nhân.

Quy trình drilldown:

1. Chọn time window mà error rate tăng.
2. Chọn route/status/instance có lỗi nổi bật.
3. Mở logs cùng khoảng thời gian, lọc theo service, route và error category.
4. Nếu có trace correlation/exemplars, mở một trace lỗi đại diện.
5. Kiểm tra span error, downstream latency, database calls và messaging operations.
6. Đối chiếu deployment marker, config changes và dependency dashboards.

Không đưa trace ID thành metric label. Dùng exemplar hoặc link từ log/trace context để chuyển từ aggregate metric tới một execution cụ thể.

## 15. Kiểm thử error-rate dashboard và alert rules

Kiểm thử cần bảo vệ cả định nghĩa SLI và PromQL:

| Test | Điều cần chứng minh |
| --- | --- |
| Numerator test | Chỉ các status được định nghĩa là lỗi được tính |
| Denominator test | Tổng requests dùng cùng scope/time window |
| 4xx/5xx split | Client và server errors được phân biệt |
| Zero traffic test | Không traffic không bị hiển thị thành 0% lỗi một cách sai nghĩa |
| Low traffic test | Một lỗi đơn lẻ không tạo alert ngoài policy |
| Probe exclusion test | Probe được loại khỏi cả numerator và denominator nếu dashboard là user traffic |
| Route aggregation test | Route template gom IDs thành một series |
| Alert rule test | for/window/threshold hoạt động theo SLO |
| Dashboard consistency | Panel và alert dùng cùng SLI definition |

Ví dụ dữ liệu test logic:

```text
Window: 5 minutes
Total requests: 1000
2xx: 970
4xx: 20
5xx: 10

Server error rate = 10 / 1000 * 100 = 1%
Client error rate = 20 / 1000 * 100 = 2%
All non-2xx rate   = 30 / 1000 * 100 = 3%
```

Prometheus rule tests có thể dùng promtool test rules để kiểm tra alert expression với series fixture. Dashboard JSON/provisioning cũng nên được version control và review cùng SLI definition.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Error rate cao bất thường | Numerator/denominator khác scope | So sánh filters và labels ở hai query |
| Error rate luôn 0 | Status label/meter name sai hoặc 5xx chưa được ghi | Kiểm tra raw series và server instrumentation |
| Query trả no data | Service chưa scrape, label không tồn tại hoặc zero traffic | Kiểm tra target health và series schema |
| Một lỗi làm route thành 100% | Denominator rất nhỏ | Hiển thị request volume và áp dụng minimum traffic |
| Probe làm tăng denominator | Health traffic được tính cùng user requests | Loại probe khỏi cả numerator và denominator |
| 404 bị tính thành server failure | Error policy gộp mọi non-2xx | Tách 4xx/5xx theo SLO |
| Dashboard theo route quá nhiều series | Raw URI hoặc ID nằm trong label | Dùng route template và top-k |
| Alert nhấp nháy | Window ngắn, thiếu for/minimum volume | Dùng multi-window và ngưỡng theo baseline |
| Alert không kích hoạt khi service im lặng | No-data semantics chưa được thiết kế | Tách no-traffic alert khỏi error-rate alert |
| Metric panel và alert lệch nhau | Hai nơi dùng SLI definitions khác | Dùng query/recording rule chung |

## 17. Tình huống thực tế: 5xx tăng sau khi triển khai

**Bối cảnh giả định:** Sau deployment, orders-service có 5xx error rate tăng từ 0,05% lên 4%. Request rate không đổi, p95 latency tăng và lỗi tập trung ở route /api/orders/{id}.

Quy trình:

1. **Xác nhận SLI:** kiểm tra numerator/denominator, loại probe traffic và so sánh cùng time window trước/sau deploy.
2. **Khoanh vùng route/status:** xem 500/502/503/504 và instance breakdown để biết lỗi tập trung ở đâu.
3. **So sánh latency:** xác định lỗi có đi cùng request duration tăng hay không.
4. **Mở traces:** chọn trace lỗi để xem exception/span và downstream dependency chậm.
5. **Đối chiếu logs:** lọc exception category và deployment version; không log token hoặc raw sensitive payload.
6. **Kiểm tra dependencies:** DB pool pending, query latency, messaging backlog và downstream error rates.
7. **Quyết định rollback/fix:** dựa trên impact, error budget và nguyên nhân đã xác minh.
8. **Xác minh:** theo dõi error rate, request volume, latency và alert state sau remediation.

Một dashboard tốt rút ngắn thời gian từ phát hiện tới khoanh vùng. Nó không thay thế việc xác minh bằng trace, log và dữ liệu dependency.

## 18. Bài tập tự kiểm tra

**Bài 1.** Vì sao error rate cần numerator và denominator cùng scope?

*Gợi ý:* Nếu filter khác nhau, tỷ lệ không còn đại diện cho phần requests bị lỗi trong tổng traffic đó.

**Bài 2.** Có nên mặc định tính mọi 4xx là server error không?

*Gợi ý:* Không. 4xx thường phản ánh client/input/auth semantics; theo dõi riêng và áp dụng SLO policy.

**Bài 3.** Một route có 1 request và 1 lỗi. Vì sao không nên kết luận service đang có 100% error rate?

*Gợi ý:* Denominator quá nhỏ; xem volume, service-level aggregate và minimum traffic policy.

**Bài 4.** Vì sao loại probe traffic phải áp dụng ở cả hai query?

*Gợi ý:* Nếu chỉ loại numerator hoặc denominator, tỷ lệ sẽ bị lệch.

**Bài 5.** Vì sao route template tốt hơn raw URI?

*Gợi ý:* Route template giới hạn cardinality và gom request cùng endpoint semantics.

**Bài 6.** Khi 5xx và p95 latency cùng tăng, nên drilldown vào đâu?

*Gợi ý:* Traces của request lỗi, logs theo error category, DB/downstream latency và saturation.

**Bài 7.** Error rate dashboard và alert có nên dùng hai định nghĩa khác nhau không?

*Gợi ý:* Không. Chúng phải dùng cùng SLI definition để tránh dashboard xanh trong khi alert đỏ hoặc ngược lại.

**Bài 8.** Vì sao no traffic không đồng nghĩa error rate bằng 0?

*Gợi ý:* Không có denominator thì không thể tính tỷ lệ; cần biểu diễn no data/no traffic riêng.

## 19. Ghi nhớ

- Error rate là failed requests chia total requests trong cùng scope/time window; hiển thị thêm request volume và error count.
- Tách 4xx và 5xx theo API contract/SLO; không mặc định mọi client error là server availability failure.
- Dùng HTTP server request metrics của Micrometer và xác minh tên meter/labels thực tế trước khi viết PromQL.
- Tính numerator/denominator với cùng filters; xử lý zero traffic và low traffic rõ ràng.
- Dùng route template, status, method, service và environment labels có cardinality kiểm soát; không đưa IDs hoặc raw URI vào metrics.
- Dashboard nên có error rate, request volume, status/route breakdown, latency, instance và deployment/dependency context.
- Alert cần window, for, minimum traffic và SLO/error-budget policy; panel và alert phải dùng cùng SLI definition.
- Drilldown từ metric aggregate sang logs/traces bằng correlation/exemplars, rồi đối chiếu DB, messaging và downstream telemetry.
