# Viết quy trình xử lý sự cố cùng điều kiện xác nhận phục hồi

Runbook cho Spring Cloud Circuit Breaker cần hướng dẫn người trực đi từ tác động của khách hàng tới dependency gây lỗi, sau đó khôi phục lưu lượng theo từng bước có thể kiểm chứng. Trạng thái `OPEN` là cơ chế bảo vệ, không phải bằng chứng duy nhất cho thấy toàn bộ API đang hỏng. Một incident chỉ được xem là phục hồi khi chất lượng phục vụ, dependency, tài nguyên và hành vi fallback đều trở lại giới hạn đã thống nhất.

Bài học này dùng Resilience4j làm ví dụ triển khai trong Spring Cloud CircuitBreaker. Quy trình cũng áp dụng được cho ứng dụng dùng implementation khác, nhưng tên metric, cách chuyển trạng thái và công cụ kiểm tra phải được điều chỉnh theo provider và Release Train đang chạy.

## 1. Mục tiêu và phạm vi của runbook

Runbook phải giúp người trực trả lời được năm câu hỏi:

1. Khách hàng đang bị ảnh hưởng ở API, route, khu vực hoặc nhóm request nào?
2. Dependency nào chậm, lỗi, quá tải hoặc không thể kết nối?
3. Circuit Breaker, TimeLimiter, Bulkhead và fallback đang phản ứng ra sao?
4. Biện pháp nào giảm tác động mà không làm dependency chịu thêm tải?
5. Những điều kiện đo được nào chứng minh có thể khôi phục lưu lượng và đóng incident?

Trước khi xảy ra sự cố, nhóm dịch vụ cần điền các thông tin sau vào runbook triển khai thực tế:

| Thông tin | Ví dụ | Giá trị cần xác nhận trong dự án |
| --- | --- | --- |
| Dịch vụ và API sở hữu | `order-service`, `GET /orders/{id}` | Tên service, owner, route quan trọng |
| Dependency được bảo vệ | `inventory`, `payment`, `profile` | Breaker ID và endpoint đích |
| Người trực và kênh sự cố | On-call backend, incident channel | Lịch trực, escalation và owner dependency |
| SLO phục vụ | Availability 99,9%, p95 dưới 800 ms | SLO đã được phê duyệt |
| Giới hạn timeout | Client timeout 1,5 s; TimeLimiter 1,8 s | Deadline thực tế theo từng dependency |
| Chính sách fallback | Cache tối đa 60 giây cho tồn kho | Tuổi dữ liệu và nghiệp vụ cho phép |
| Nguồn quan sát | Actuator, Prometheus, Grafana, tracing | URL nội bộ, dashboard và quyền truy cập |

Không dùng các giá trị minh họa trong bài làm cấu hình production mà chưa so sánh với SLA, lưu lượng, capacity và hợp đồng dữ liệu của hệ thống.

## 2. Chuẩn bị trước khi có incident

Runbook chỉ hữu ích khi người trực có thể tìm được đúng thông tin mà không phải đọc mã nguồn trong lúc sự cố đang diễn ra. Chuẩn bị trước:

- Danh sách breaker ID, dependency, owner, timeout, failure threshold, slow-call threshold, `waitDurationInOpenState` và số lời gọi được phép ở `HALF_OPEN`.
- Dashboard có request rate, tỷ lệ lỗi, p95/p99, SLO/error budget, fallback, trạng thái breaker, timeout, Bulkhead và connection pool.
- Link tới dashboard dependency, health check, tracing, log và quy trình escalation của nhóm sở hữu dependency.
- Quy tắc fallback: dữ liệu nào được phép cũ, tuổi tối đa, khi nào phải trả `unavailable`, khi nào không được phép fallback.
- Biện pháp giảm tải đã được thử nghiệm: giới hạn concurrency, tắt chức năng không thiết yếu, giảm traffic, cache đã kiểm soát hoặc shed load.
- Cách triển khai/rollback cấu hình và người có quyền phê duyệt thay đổi production.
- Các điều kiện xác nhận phục hồi và thời gian quan sát ổn định sau khi phục hồi.

Ví dụ cấu hình Resilience4j cần được ghi lại cùng breaker ID:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 3

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 1500ms
```

Đây chỉ là ví dụ để runbook có dữ liệu cụ thể. Trong production, ghi giá trị thực tế đã triển khai, nguồn cấu hình (profile, environment, config server hoặc properties) và phiên bản ứng dụng. Không giả định file YAML trong repository luôn phản ánh cấu hình runtime.

## 3. Khi nào mở incident?

Ưu tiên tác động khách hàng và SLO. Breaker chuyển sang `OPEN` có thể chỉ ra dependency đang gặp vấn đề, nhưng fallback có thể vẫn phục vụ request đúng hợp đồng. Ngược lại, API có thể vi phạm SLO dù breaker vẫn `CLOSED`.

| Tín hiệu | Phân loại gợi ý | Hành động ban đầu |
| --- | --- | --- |
| Tỷ lệ 5xx hoặc timeout API vượt SLO liên tục, có đủ lưu lượng | Incident phục vụ khách hàng | Mở incident, xác định route và vùng ảnh hưởng |
| p95/p99 vượt SLO, error budget burn nhanh | Incident hiệu năng | Kiểm tra dependency latency, queue và pool |
| Breaker quan trọng `OPEN` kéo dài, fallback tăng mạnh | Warning cần điều tra; nâng mức nếu SLI suy giảm | Kiểm tra dependency và chất lượng fallback |
| Bulkhead rejection tăng, queue/thread pool cạn | Quá tải hoặc nghẽn tài nguyên | Giảm concurrency/traffic và kiểm tra tác vụ bị kẹt |
| Một lần `OPEN` ngắn, API vẫn đạt SLO, fallback hợp lệ | Sự kiện bảo vệ | Theo dõi, chưa cần page chỉ vì trạng thái |

Điều kiện alert phải có cửa sổ thời gian và ngưỡng lưu lượng phù hợp. Một request lỗi đơn lẻ không nên tạo page nếu SLO không bị đe dọa. Cảnh báo breaker `OPEN` có thể ở mức warning khi chưa có tác động phục vụ.

## 4. Quy trình xử lý sự cố

### Bước 1 — Xác nhận tác động và phạm vi

Trong vài phút đầu, người trực cần ghi lại:

- Thời điểm bắt đầu và alert đã kích hoạt.
- API/route, khu vực, tenant hoặc nhóm khách hàng bị ảnh hưởng.
- Request rate, tỷ lệ lỗi, timeout, p95/p99 và SLO/error budget hiện tại.
- Phiên bản ứng dụng, pod/instance và thay đổi cấu hình hoặc triển khai gần nhất.
- Tỷ lệ request dùng fallback và liệu dữ liệu fallback có còn hợp lệ.

Kiểm tra dashboard ở cấp API trước, sau đó phân rã theo instance và dependency. Không suy ra toàn hệ thống hỏng chỉ từ một breaker của một pod.

### Bước 2 — Xác định dependency và cơ chế đang kích hoạt

Đối chiếu breaker ID với metric và trace:

- `CLOSED` cùng failure rate/slow-call rate tăng: dependency có thể đang suy giảm nhưng breaker chưa đạt ngưỡng hoặc chưa đủ mẫu.
- `OPEN` và `not permitted` tăng: breaker đang chặn lời gọi; xem thời điểm mở, lỗi/slow call trước đó và dependency tương ứng.
- `HALF_OPEN` liên tục quay lại `OPEN`: các lời gọi thăm dò vẫn thất bại hoặc chậm; dependency chưa ổn định hoặc đang nhận quá nhiều tải.
- TimeLimiter timeout tăng trong khi client request vẫn treo: kiểm tra cancellation, HTTP client timeout và worker thread còn bị chiếm.
- Bulkhead rejection/queue tăng: kiểm tra số worker, queue capacity, tác vụ blocking và thời gian xử lý.
- Fallback tăng nhưng API vẫn trả 2xx: xác minh cache freshness và ngữ nghĩa phản hồi; status code thành công không tự chứng minh dữ liệu đúng.

Trace một số request đại diện để xác nhận thời gian nằm ở DNS/connect, connection pool, response, xử lý nội bộ hay fallback. Kiểm tra lỗi 4xx riêng để không nhầm lỗi nghiệp vụ của caller với lỗi sức khỏe dependency.

### Bước 3 — Bảo vệ hệ thống và giới hạn tác động

Chọn biện pháp theo nguyên nhân và runbook đã phê duyệt:

- Giảm hoặc tạm dừng traffic không thiết yếu tới dependency đang quá tải.
- Hạn chế concurrency ở caller hoặc Bulkhead để không tạo thêm hàng đợi vô hạn.
- Giảm retry hoặc tạm tắt retry cho lỗi đang khuếch đại tải; giữ tổng thời gian thử lại trong deadline của request.
- Dùng cache/snapshot chỉ khi dữ liệu còn trong tuổi tối đa và nghiệp vụ cho phép.
- Từ chối sớm request không thiết yếu nếu không còn capacity, thay vì giữ thread/connection vô hạn.
- Escalate tới owner của dependency kèm timestamp, request ID qua log/trace, tỷ lệ lỗi, latency và số lượng request.

Không bỏ qua Circuit Breaker hoặc ép `CLOSED` chỉ để khôi phục request rate. Không tăng `permittedNumberOfCallsInHalfOpenState` trong lúc dependency còn quá tải. Không tăng queue capacity để che một dependency xử lý chậm.

### Bước 4 — Khôi phục dependency trước khi tăng lưu lượng

Nhóm sở hữu dependency cần xác nhận nguyên nhân đã được xử lý: instance khỏe, connection/database pool không cạn, lỗi hạ tầng đã ổn định, latency nằm trong ngưỡng và không còn backlog tăng liên tục.

Kiểm tra bằng health endpoint hoặc synthetic request nhẹ được phê duyệt. Health check phải đại diện cho khả năng phục vụ thực tế nhưng không tạo một đợt tải lớn. Nếu dependency phụ thuộc tiếp vào database hoặc hệ thống khác, kiểm tra các thành phần đó trước khi tuyên bố phục hồi.

Không dùng một response 200 đơn lẻ làm bằng chứng phục hồi. Quan sát tỷ lệ thành công, latency, saturation và lỗi theo một cửa sổ đủ dài so với lưu lượng và chu kỳ tải của dependency.

### Bước 5 — Cho phép Circuit Breaker thử phục hồi

Khi hết `waitDurationInOpenState`, Resilience4j có thể chuyển sang `HALF_OPEN` để cho phép số request thăm dò giới hạn. Nếu `automaticTransitionFromOpenToHalfOpenEnabled` tắt, việc chuyển trạng thái có thể được kích hoạt bởi lời gọi tiếp theo sau khi thời gian chờ đã hết; không nhầm trạng thái `OPEN` hiển thị trong lúc không có traffic với bằng chứng dependency vẫn lỗi.

Trong giai đoạn này:

- Theo dõi số probe được phép và kết quả thành công/thất bại.
- Giữ traffic không thiết yếu ở mức thấp để probe không cạnh tranh với tải lớn.
- Quan sát breaker theo từng instance; không chỉ nhìn một metric tổng.
- Nếu breaker quay lại `OPEN`, tiếp tục bảo vệ dependency, tìm nguyên nhân còn sót và chờ chu kỳ phục hồi tiếp theo.
- Nếu probe thành công và breaker về `CLOSED`, tiếp tục theo dõi trước khi mở lại toàn bộ traffic.

Không gửi probe nhân tạo liên tục bằng script hoặc health checker tần suất cao. Tôn trọng `permittedNumberOfCallsInHalfOpenState` và cơ chế bảo vệ đang cấu hình.

### Bước 6 — Tăng traffic có kiểm soát

Khôi phục theo từng bước: mở lại một phần traffic hoặc một nhóm instance trước, quan sát, rồi mới tăng tiếp. Sau mỗi bước, so sánh:

- API request success/error ratio và p95/p99.
- Dependency success/error ratio và response latency.
- Circuit Breaker state, failure rate, slow-call rate và not-permitted calls.
- TimeLimiter timeout, Bulkhead rejection, queue và connection pool.
- Fallback rate, fallback failure và tuổi dữ liệu cache.

Nếu bất kỳ điều kiện phục hồi nào bị vi phạm, dừng tăng traffic và quay lại biện pháp giảm tải. Không triển khai đồng loạt cấu hình mới trên tất cả instance khi chưa xác nhận một canary hoạt động ổn định.

## 5. Điều kiện xác nhận phục hồi

Incident chỉ được đánh dấu phục hồi khi các gate đã định nghĩa trước được đáp ứng. Bảng dưới là mẫu có thể điều chỉnh theo SLO và baseline của dịch vụ:

| Gate | Điều kiện xác nhận mẫu | Bằng chứng cần lưu |
| --- | --- | --- |
| Dependency availability | Tỷ lệ lỗi 5xx/kết nối dưới 1% trong ít nhất 10 phút, không có đợt lỗi mới | Dashboard dependency, health/synthetic check |
| Dependency latency | p95 dưới timeout budget đã thống nhất; p99 không vượt deadline phục vụ | HTTP client metrics, trace và dashboard latency |
| Circuit Breaker | Các breaker liên quan đã trở lại `CLOSED` và ổn định ít nhất 10–15 phút; không liên tục mở lại | State gauge/event theo từng instance và breaker ID |
| Probe result | Các lời gọi được cấp quyền ở `HALF_OPEN` thành công theo cấu hình | Circuit Breaker event, log và số request thực tế |
| Caller SLI | API success rate và latency trở lại SLO trong cửa sổ quan sát | Dashboard SLI/SLO và error budget |
| Timeout and Bulkhead | Timeout, rejection, queue depth và active worker trở về baseline/capacity an toàn | TimeLimiter/Bulkhead metrics và executor metrics |
| Fallback quality | Fallback rate giảm về baseline; không có dữ liệu stale vượt tuổi tối đa; fallback error bằng 0 hoặc ngưỡng đã duyệt | Counter fallback, cache age và log nghiệp vụ |
| Backlog and resources | Queue, connection pool, CPU, memory và thread count ổn định; backlog không tiếp tục tăng | Dashboard tài nguyên và dependency |

Các con số 1%, 10 phút, 10–15 phút chỉ là ví dụ. Chọn cửa sổ dài hơn thời gian mở mạch và đủ bao phủ một chu kỳ tải đại diện. Nếu traffic thấp, bổ sung synthetic check có kiểm soát thay vì dựa vào một tỷ lệ tính từ vài request.

Điều kiện `CLOSED` phải được xác nhận theo từng instance. Resilience4j thường giữ trạng thái trong registry cục bộ của từng process; metric tổng hợp có thể che việc một pod vẫn `OPEN`. Không giả định các replica chia sẻ một state duy nhất trừ khi ứng dụng đã xây dựng cơ chế đồng bộ riêng.

## 6. Cẩn trọng khi restart hoặc rollout

Restart ứng dụng có thể làm mất state Circuit Breaker đang lưu trong bộ nhớ process và instance mới thường bắt đầu với trạng thái mới. Điều đó không chứng minh dependency đã phục hồi. Nếu restart đồng loạt, nhiều instance có thể cùng gửi lại traffic tới dependency ngay sau khi lên, tạo một đợt tải đột ngột.

Nếu restart là một phần của biện pháp khắc phục đã được phê duyệt:

- Dùng rolling restart hoặc canary, giữ giới hạn traffic trong khi instance mới khởi động.
- Xác nhận dependency đã đủ capacity trước khi tăng số instance nhận traffic.
- Theo dõi breaker state, request rate, latency và fallback sau từng nhóm instance.
- Không coi việc breaker chuyển về `CLOSED` sau restart là điều kiện phục hồi độc lập.

## 7. Ma trận triệu chứng và hành động

| Triệu chứng | Nguyên nhân cần kiểm tra | Hành động ưu tiên |
| --- | --- | --- |
| `OPEN`, not-permitted tăng, API SLI vẫn tốt | Fallback đang bảo vệ thành công; dependency vẫn có thể lỗi | Giữ traffic được kiểm soát, kiểm tra dependency và freshness fallback |
| `OPEN`, API 5xx tăng | Fallback thiếu hoặc không hợp lệ; route phụ thuộc trực tiếp | Giảm traffic, khôi phục dependency, xem lại hợp đồng fallback |
| `CLOSED`, timeout và p95 tăng | Ngưỡng chưa đạt, thiếu mẫu, timeout/client pool hoặc slow-call threshold không phù hợp | Điều tra latency, giảm concurrency, xác nhận cấu hình breaker |
| `HALF_OPEN` rồi `OPEN` liên tục | Dependency chưa ổn định, probe lỗi hoặc tải phục hồi quá lớn | Giữ giảm tải, sửa dependency, không tăng probe tùy tiện |
| Bulkhead full, queue tăng | Tác vụ blocking bị treo, pool nhỏ hoặc dependency chậm | Kiểm tra worker/client timeout, shed load, giới hạn concurrency |
| TimeLimiter timeout tăng nhưng thread vẫn bận | Cancellation không dừng được I/O hoặc client timeout quá dài | Kiểm tra timeout tầng client và hành vi interrupt/cancel |
| Fallback rate tăng nhưng status 2xx ổn định | API đang dùng cache hoặc dữ liệu dự phòng nhiều | Kiểm tra freshness, tính đúng nghiệp vụ và SLI riêng cho degraded response |
| Chỉ một pod có breaker `OPEN` | Dependency path, network hoặc tải riêng của pod | Phân tích theo instance, không chỉ nhìn aggregate |

## 8. Ví dụ truy vấn phục vụ điều tra

Các query dưới đây minh họa cách xem dữ liệu Prometheus. Tên metric và label phải được xác nhận tại `/actuator/prometheus` của phiên bản đang chạy trước khi đưa vào runbook.

**Breaker đang OPEN theo ID:**

```promql
max by (instance, name) (resilience4j_circuitbreaker_state{state="open"})
```

**Lời gọi Circuit Breaker thất bại theo ID:**

```promql
sum by (instance, name) (rate(resilience4j_circuitbreaker_calls_seconds_count{kind="failed"}[5m]))
```

**Lời gọi bị từ chối:**

```promql
sum by (instance, name) (rate(resilience4j_circuitbreaker_not_permitted_calls_total[5m]))
```

**Timeout của TimeLimiter:**

```promql
sum by (instance, name) (rate(resilience4j_timelimiter_calls_total{ kind="timeout"}[5m]))
```

**Tỷ lệ HTTP 5xx của caller:**

```promql
sum(rate(http_server_requests_seconds_count{job="order-service",status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count{job="order-service"}[5m])), 0.001)
```

Không copy query nếu metric name của registry khác. Ví dụ, timer/counter có thể được chuẩn hóa thành hậu tố `_seconds_count` hoặc `_total`; xác nhận metric thực tế và kiểu dữ liệu trước khi dùng. Luôn giữ `instance` hoặc `pod` trong query điều tra để thấy khác biệt giữa replica.

## 9. Ghi nhận quyết định và bàn giao

Trong incident channel hoặc ticket, ghi lại theo mẫu:

```text
Incident ID:
Service / route:
Dependency / breaker ID:
Start time / detection source:
Customer impact and affected region:
API SLI/SLO at detection:
Breaker states by instance:
Timeout / Bulkhead / fallback symptoms:
Containment actions and approver:
Dependency recovery evidence:
HALF_OPEN probe results:
Traffic restoration steps:
Recovery gates and observation window:
Incident resolved time:
Follow-up owner and due date:
```

Không đưa token, mật khẩu, dữ liệu cá nhân hoặc payload nhạy cảm vào ticket/log. Dùng trace ID hoặc request ID đã được chính sách nội bộ cho phép để nối dữ liệu giữa các hệ thống.

## 10. Sau incident: ngăn tái diễn

Sau khi dịch vụ ổn định, thực hiện review theo dữ liệu:

- Xác định nguyên nhân gốc và yếu tố góp phần: dependency, network, pool, timeout, retry, cấu hình hoặc thay đổi triển khai.
- Đối chiếu `failureRateThreshold`, `slowCallRateThreshold`, `minimumNumberOfCalls`, sliding window và `waitDurationInOpenState` với dữ liệu thật; không chỉnh threshold chỉ để giảm số alert.
- Xem lại timeout của caller, HTTP client và gateway để deadline lồng nhau hợp lý.
- Kiểm tra Bulkhead capacity, queue, executor và khả năng cancellation của client.
- Đánh giá fallback: freshness, tính đúng nghiệp vụ, tỷ lệ fallback thành công và trường hợp fallback cũng thất bại.
- Cải thiện dashboard, alert, runbook và synthetic check nếu người trực thiếu bằng chứng khi quyết định.
- Tạo action item có owner, hạn hoàn thành và cách xác nhận.

Không biến post-incident review thành thay đổi cấu hình tự động. Mọi điều chỉnh threshold, timeout, retry hoặc fallback cần được kiểm thử với tải đại diện và có kế hoạch rollback.

## 11. Checklist đóng incident

- [ ] Tác động khách hàng đã trở về SLO trong cửa sổ quan sát đã thống nhất.
- [ ] Dependency đã ổn định về tỷ lệ lỗi, latency và capacity.
- [ ] Các breaker liên quan đã được kiểm tra theo từng instance và không mở lại trong thời gian xác nhận.
- [ ] `HALF_OPEN` probes thành công; không có probe bất thường hoặc traffic tăng đột ngột.
- [ ] Timeout, Bulkhead rejection, queue và connection pool trở lại mức an toàn.
- [ ] Fallback giảm về baseline; dữ liệu stale không vượt giới hạn nghiệp vụ.
- [ ] Không còn backlog hoặc tác vụ blocking tồn đọng sau timeout.
- [ ] Các thay đổi khẩn cấp đã được ghi lại, có owner và kế hoạch hoàn nguyên nếu cần.
- [ ] Incident timeline, bằng chứng phục hồi và action items đã được lưu.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker – Resilience4J](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): factory, cấu hình instance, TimeLimiter, Bulkhead và metrics.
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): state machine, sliding window, HALF_OPEN permissions và event publisher.
- [Resilience4j – Micrometer](https://resilience4j.readme.io/docs/micrometer): metrics cho Circuit Breaker, TimeLimiter và Bulkhead.
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics, tags, histogram và export.
- [Prometheus – Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): truy vấn time series và label trong PromQL.
