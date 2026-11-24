# Runbook gắn với alert

Một alert báo tỷ lệ lỗi HTTP 5xx vượt ngưỡng lúc nửa đêm. On-call engineer cần biết service nào bị ảnh hưởng, dashboard nào mở trước, cách xác định lỗi bắt đầu sau deployment hay do dependency, và hành động giảm thiểu nào an toàn. Nếu alert chỉ có tên metric cùng một con số, người nhận phải tự tìm context trong lúc incident đang diễn ra. Runbook gắn với alert biến tín hiệu thành quy trình điều tra có thể thực hiện và kiểm chứng.

Bài **Runbook gắn với alert** thuộc chương **Dashboard và alert** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Một alert tốt phải dẫn tới hành động cụ thể. Runbook cần nêu impact, điều kiện kích hoạt, mức độ ưu tiên, bước xác minh, đường dẫn dashboard/log/trace, biện pháp giảm thiểu, tiêu chí recovery và người cần escalation. Các bước phải an toàn, có thứ tự và phân biệt rõ quan sát với thay đổi production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích quan hệ giữa alert rule, annotation và runbook.
2. Viết runbook có thể thực thi cho Spring Boot observability incidents.
3. Phân biệt symptom, hypothesis, diagnosis và mitigation.
4. Liên kết alert với dashboard panels, logs, traces và deployment events.
5. Chọn severity, duration window và impact criteria.
6. Thiết kế Prometheus alert annotations có runbook URL và service context.
7. Viết bước triage có thứ tự, tránh thay đổi cấu hình mù quáng.
8. Định nghĩa rollback, recovery và verification criteria.
9. Quản lý ownership, escalation và incident communication.
10. Kiểm thử runbook bằng tabletop hoặc fault-injection exercises.

## 2. Alert và runbook làm hai việc khác nhau

Alert phát hiện một điều kiện cần chú ý; runbook hướng dẫn người nhận hiểu và xử lý điều kiện đó.

| Thành phần | Trả lời câu hỏi |
|---|---|
| Alert name | Điều gì đang bất thường? |
| Summary | Triệu chứng chính là gì? |
| Description | Service/instance/impact nào liên quan? |
| Severity | Mức độ phản ứng cần thiết? |
| Dashboard link | Tình hình thay đổi thế nào theo thời gian? |
| Runbook link | Cần làm gì tiếp theo? |
| Logs/traces link | Bằng chứng chi tiết nằm ở đâu? |
| Owner/escalation | Ai chịu trách nhiệm nếu chưa xử lý được? |

Alert không nên chứa toàn bộ runbook trong annotation. Annotation cần ngắn, có context và link ổn định; runbook chứa quy trình đầy đủ và được cập nhật cùng hệ thống.

~~~mermaid
flowchart TD
    A["Metric / SLO signal"] --> B["Alert rule"]
    B --> C["Notification with context"]
    C --> D["Runbook"]
    D --> E["Confirm impact"]
    E --> F["Investigate evidence"]
    F --> G["Mitigate safely"]
    G --> H["Verify recovery"]
    H --> I["Close / follow-up"]
~~~

## 3. Cấu trúc tối thiểu của một runbook

Một runbook nên có các phần:
1. **Tên alert và mục đích:** mô tả symptom, không chỉ lặp metric name.
2. **Severity và impact:** người dùng/chức năng nào bị ảnh hưởng, mức độ nào.
3. **Trigger:** metric, threshold, window, labels và điều kiện alert duration.
4. **Dashboard:** link tới panel liên quan và time range mặc định.
5. **Triage:** các bước xác minh đầu tiên.
6. **Hypotheses:** nguyên nhân thường gặp và bằng chứng phân biệt.
7. **Mitigation:** hành động giảm ảnh hưởng, điều kiện áp dụng và rollback.
8. **Recovery:** tiêu chí xác nhận hệ thống ổn định.
9. **Escalation:** owner, nhóm phụ thuộc và thời điểm chuyển cấp.
10. **Follow-up:** ghi nhận timeline, nguyên nhân gốc và action items.

Tránh runbook chỉ có danh sách nguyên nhân chung chung. Mỗi bước nên nói rõ cần xem gì và kết quả đó dẫn tới bước nào.

## 4. Severity và user impact

Severity phải phản ánh tác động và urgency, không chỉ mức metric vượt ngưỡng.

| Mức | Ví dụ | Phản ứng |
|---|---|---|
| Critical / SEV-1 | Phần lớn request quan trọng thất bại hoặc service unavailable | Gọi incident response ngay |
| High / SEV-2 | Một capability chính suy giảm rõ, workaround hạn chế | On-call xử lý và cập nhật incident |
| Warning | Resource pressure hoặc latency tăng nhưng SLO chưa vi phạm | Theo dõi, điều tra trong giờ làm việc hoặc theo policy |
| Info | Thay đổi bất thường cần ghi nhận | Không paging nếu chưa có impact |

Định nghĩa severity theo incident policy của tổ chức. Không tự tạo một hệ thống SEV mới nếu công ty đã có chuẩn. Alert paging cần có minimum traffic hoặc symptom corroboration để tránh cảnh báo khi sample volume quá thấp.

## 5. Viết alert annotation có context

Ví dụ Prometheus alert rule:

~~~yaml
groups:
  - name: spring-boot-http
    rules:
      - alert: SpringBootHighHttp5xxRate
        expr: |
          sum by (service) (rate(http_server_requests_seconds_count{
            status=~"5.."
          }[5m]))
          /
          clamp_min(sum by (service) (
            rate(http_server_requests_seconds_count[5m])
          ), 1)
          > 0.05
        for: 10m
        labels:
          severity: page
          team: order-platform
        annotations:
          summary: "HTTP 5xx rate is elevated for {{ $labels.service }}"
          description: "More than 5% of requests failed for 10 minutes."
          dashboard_url: "https://monitoring.example/d/order-service"
          runbook_url: "https://runbooks.example/spring-boot/http-5xx"
~~~

Ví dụ minh họa; metric name, labels, routing và threshold phải khớp Prometheus exposition thực tế của ứng dụng. Không copy URL example vào production. Cân nhắc thêm environment, cluster hoặc bounded route label nếu cần phân biệt blast radius.

Annotation nên giúp người nhận bắt đầu ngay: service/environment, symptom và threshold/window, dashboard URL, runbook URL, owner/team hoặc escalation channel theo convention nội bộ. Không nhúng token, credentials, customer data hoặc URL chứa secrets vào alert annotations.

## 6. Runbook mẫu: HTTP 5xx rate cao

**Mục tiêu:** Xác định phạm vi lỗi, phân biệt application regression với dependency outage và giảm impact.

### 6.1 Xác nhận impact

1. Mở dashboard được link từ alert.
2. Xác nhận service, environment, cluster và thời điểm bắt đầu.
3. So sánh 5xx rate với total request rate; kiểm tra traffic có đủ lớn không.
4. Xem lỗi tập trung ở route template nào, status nào và instance nào.
5. Kiểm tra latency p95/p99 và các SLO đang vi phạm.
6. Xác nhận lỗi từ synthetic checks hoặc user-facing signals nếu có.

Nếu 5xx rate tăng nhưng request volume gần bằng 0, kiểm tra denominator và telemetry gap trước khi kết luận incident lớn.

### 6.2 Thu thập bằng chứng

- Mở logs theo service, environment và time window; tìm exception class/error.type.
- Mở traces của các request lỗi; xem server span và downstream spans.
- So sánh deployment/configuration changes với thời điểm alert bắt đầu.
- Kiểm tra dependency health, timeout, retry và connection pool metrics.
- Phân biệt lỗi ở application validation, database, remote HTTP hay gateway.

Không tìm bằng cách thêm user ID/email vào metric labels. Dùng trace ID hoặc correlation ID có quyền truy cập phù hợp để điều tra một request.

### 6.3 Mitigation

Chọn hành động theo bằng chứng:
- Nếu regression bắt đầu ngay sau release và rollback đã được xác nhận an toàn, thực hiện rollback theo deployment procedure.
- Nếu một dependency đang rate-limit, áp dụng fallback/circuit breaker theo policy đã được kiểm thử.
- Nếu một route cụ thể gây tải bất thường, giảm traffic hoặc disable feature bằng cơ chế đã được phê duyệt.
- Nếu pool exhausted, xác định connection leak/slow query trước khi điều chỉnh pool.
- Nếu database outage, phối hợp owner database và tránh restart đồng loạt các pods khỏe.

Mọi thay đổi production phải theo incident/change policy của tổ chức và được ghi lại trong timeline.

### 6.4 Recovery criteria

Chỉ đóng alert khi:
- 5xx rate trở về baseline trong cửa sổ xác nhận.
- Request rate đủ lớn để kết quả có ý nghĩa.
- p95/p99 và các SLO liên quan ổn định.
- Dependency errors/timeouts giảm.
- Không còn instance lỗi hoặc restart loop.
- Dashboard không có missing telemetry che khuất tình hình.

## 7. Runbook mẫu: HTTP latency cao

**Trigger:** p95/p99 latency vượt budget trong một cửa sổ liên tiếp.

1. Xác nhận route, service, region/cluster và thời gian.
2. So sánh request rate, error rate và in-flight requests.
3. Mở saturation dashboard: CPU, throttling, heap/GC, threads và executor queues.
4. Kiểm tra HikariCP active/idle/max/pending và acquisition wait.
5. Kiểm tra HTTP client pool wait, downstream latency, timeout và retries.
6. Mở slow traces để tìm span chiếm phần lớn thời gian.
7. Xác định request chờ local queue, database, remote API hay lock.
8. Chọn mitigation ở bottleneck đã xác định; tránh tăng đồng thời mọi pool.
9. Theo dõi latency, backlog và error rate sau thay đổi.
10. Xác nhận latency trở về SLO trong thời gian ổn định đã định.

Không kết luận CPU là nguyên nhân chỉ vì latency cao. CPU thấp cùng pool pending cao thường chỉ ra waiting/saturation ở dependency hoặc connection pool.

## 8. Runbook mẫu: Database connection pool exhausted

**Trigger:** Connection acquisition timeout hoặc pending threads tăng kéo dài.

### Triage

1. Xác nhận pool name, service instance và thời điểm bắt đầu.
2. So sánh active, idle, max, pending và acquisition duration.
3. Xem connection usage duration và transaction duration nếu có.
4. Mở traces của request chậm để tìm DB spans dài hoặc transaction giữ connection.
5. Kiểm tra database availability, connection limit, locks và slow queries.
6. So sánh deployment/configuration change gần nhất.

### Hypotheses

| Hypothesis | Bằng chứng cần tìm |
|---|---|
| Slow query/lock | DB span dài, query/lock wait tăng |
| Connection leak | Active không giảm sau workload, usage duration bất thường |
| Traffic burst | Arrival rate tăng cùng concurrency |
| Pool quá nhỏ | Pending tăng dưới tải bình thường, DB còn capacity |
| Database giới hạn connections | DB connection count gần server limit |
| Transaction giữ connection lâu | Transaction duration cao hoặc external call nằm trong transaction |

### Mitigation và recovery

- Giảm incoming load nếu traffic burst gây quá tải.
- Dừng hoặc rollback release tạo query/transaction regression theo procedure.
- Xử lý leak/long transaction ở code path đã xác định.
- Chỉ tăng pool khi DB server còn capacity và tổng connection budget đã được tính.
- Xác nhận pending/acquisition wait về baseline và DB latency ổn định.

Không tăng pool size mù quáng; tổng pool size của mọi replicas có thể vượt giới hạn database.

## 9. Runbook mẫu: Queue backlog hoặc consumer lag

**Trigger:** Oldest message age, queue wait hoặc consumer lag vượt SLO.

1. Xác nhận queue/topic, consumer group và message type.
2. So sánh arrival rate với completion throughput.
3. Kiểm tra queue depth, oldest age, in-flight/unacked và retry/dead-letter rate.
4. Kiểm tra consumer instances, concurrency, partition assignment và rebalance.
5. Xem processing duration và dependency spans trong consumer.
6. Phân biệt worker thiếu capacity với downstream DB/API chậm.
7. Kiểm tra poison messages/retry loop có chiếm worker không.
8. Tăng consumer capacity chỉ khi downstream dependencies còn headroom.
9. Nếu cần, pause/limit producer hoặc route message theo policy đã định nghĩa.
10. Theo dõi backlog drain rate và end-to-end age đến khi trở về mục tiêu.

Kafka offset lag là số records/offset distance; không chuyển trực tiếp thành thời gian chờ nếu chưa xét throughput và record age.

## 10. Runbook mẫu: Telemetry exporter hoặc Collector mất dữ liệu

**Trigger:** Export failures, queue occupancy hoặc dropped spans/records tăng.

1. Xác nhận application business SLO có bị ảnh hưởng hay chỉ telemetry pipeline.
2. Kiểm tra SDK queue size/capacity, dropped spans và exporter duration.
3. Kiểm tra Collector receiver rate, refused records, memory limiter và exporter queue.
4. Kiểm tra backend throttling, 429/503, network và DNS/TLS errors.
5. Xác định điểm mất dữ liệu đầu tiên: SDK, network, Collector hay backend.
6. Giảm telemetry volume theo policy: sampling traces bình thường, lọc noisy health checks, rate-limit repetitive logs.
7. Giữ metrics về availability, latency và telemetry drops nếu pipeline còn capacity.
8. Khôi phục exporter/backend và drain queue với tốc độ có giới hạn.
9. Xác nhận dropped rate giảm, queue age ổn định và request latency không bị ảnh hưởng.
10. Ghi rõ khoảng thời gian telemetry không đầy đủ để người đọc dashboard không hiểu nhầm dữ liệu là zero.

Không để telemetry export chậm làm block request thread. Telemetry loss phải được thể hiện rõ và có alert riêng.

## 11. Dashboard, logs và traces trong runbook

Runbook nên liên kết trực tiếp tới:
- Service overview dashboard.
- Saturation dashboard.
- Dependency dashboard (DB, HTTP client, messaging).
- Logs query với service/environment/time range được điền sẵn.
- Trace search theo trace ID hoặc error/latency filter.
- Deployment timeline.
- Health/readiness endpoint hoặc platform status.
- Relevant SLO/error budget panel.

Link cần ổn định, có quyền truy cập phù hợp và tránh query string chứa secrets/PII. Nếu dashboard có variable, dùng service/environment labels đã chuẩn hóa.

Một bước điều tra nên nói rõ bằng chứng nào cần tìm. Ví dụ: mở trace chậm nhất và kiểm tra span DB client; nếu DB span chiếm phần lớn latency, chuyển sang DB pool/query runbook.

## 12. Ownership và escalation

Mỗi alert cần có owner rõ ràng. Runbook nên nêu:
- Primary on-call team.
- Dependency owner (database, platform, messaging, network).
- Khi nào gọi incident commander.
- Điều kiện escalation nếu không xác định được nguyên nhân trong thời gian mục tiêu.
- Kênh cập nhật incident theo quy trình nội bộ.
- Ai có quyền rollback hoặc thay đổi traffic/configuration.

Không gắn một cá nhân cụ thể vào runbook nếu lịch trực thay đổi thường xuyên; dùng team alias hoặc on-call service được quản lý tập trung.

## 13. Runbook phải an toàn và dễ thực thi

Các bước runbook cần:
- Bắt đầu bằng read-only diagnosis.
- Nêu rõ lệnh/query có tác động production.
- Có precondition và expected result.
- Ghi rollback path cho mitigation.
- Không yêu cầu chia sẻ credentials hoặc PII.
- Không hướng dẫn restart/scale/disable feature nếu chưa có điều kiện an toàn.
- Không dùng một hành động cho mọi nguyên nhân.
- Có timestamp/timezone và cách ghi incident timeline.

Nếu runbook chứa command, dùng placeholder an toàn cho namespace/service và yêu cầu xác nhận context trước khi chạy. Không lưu token hoặc password trong URL, command history hay documentation.

## 14. Kiểm thử và bảo trì runbook

Runbook không được coi là hoàn tất chỉ vì có nội dung. Kiểm thử:
1. Alert rule có firing với synthetic metrics theo đúng threshold/window.
2. Annotation links mở đúng dashboard và runbook.
3. Query có labels thực tế, không dùng metric name giả định.
4. On-call engineer có quyền truy cập dashboard/logs/traces.
5. Các bước triage dẫn tới evidence có thể tìm được.
6. Mitigation có owner và rollback path.
7. Recovery criteria có thể đo bằng metrics.
8. Tabletop exercise xác nhận người mới có thể làm theo.
9. Sau incident, cập nhật nguyên nhân mới và loại bỏ bước lỗi thời.
10. Định kỳ kiểm tra links, ownership và version/config changes.

Gắn runbook review date hoặc owner metadata trong hệ thống documentation. Không hardcode date/owner trong alert rule nếu đã có source of truth khác.

## 15. Troubleshooting runbook và alert quality

| Vấn đề | Nguyên nhân có thể | Cách cải thiện |
|---|---|---|
| Alert firing nhưng không có impact | Threshold quá nhạy hoặc thiếu minimum traffic | Correlate với SLO/user impact |
| On-call không biết bắt đầu ở đâu | Summary/links thiếu context | Thêm dashboard, service, environment và runbook URL |
| Runbook có quá nhiều bước chung chung | Không gắn bước với hypothesis/evidence | Viết decision path theo symptom |
| Mitigation làm incident nặng hơn | Không có precondition/rollback | Thêm safety checks và expected result |
| Dashboard không có dữ liệu | Telemetry gap hoặc sai label | Thêm no-data detection và kiểm tra exporter |
| Alert lặp lại sau khi xử lý | Recovery window quá ngắn hoặc root cause chưa giải quyết | Đặt stable recovery window và follow-up |
| Nhiều team nhận cùng alert | Routing/ownership không rõ | Xác định primary owner và dependency escalation |
| Runbook links hỏng | Dashboard/document moved | Kiểm tra links tự động hoặc định kỳ |
| Query không chạy | Metric name/labels khác thực tế | Validate với scrape output và registry |
| Không thể xác nhận recovery | Không có measurable exit criteria | Định nghĩa SLO, baseline và stable window |

## 16. Playbook: từ alert tới đóng incident

**Tình huống:** On-call nhận alert có runbook link.

1. Acknowledge theo on-call policy và xác nhận service/environment.
2. Đọc summary, severity, trigger window và impact.
3. Mở dashboard link, xác nhận symptom độc lập.
4. Chọn runbook theo alert; không chạy mitigation trước khi thu thập evidence.
5. Ghi incident start time và các thay đổi gần nhất.
6. Kiểm tra logs/traces/metrics theo thứ tự runbook.
7. Nêu hypothesis và bằng chứng xác nhận/bác bỏ.
8. Thực hiện mitigation đã được phép, ghi lại thay đổi và rollback path.
9. Theo dõi recovery criteria trong stable window.
10. Đóng alert/incident theo policy; ghi timeline, root cause, data gaps và follow-up actions.
11. Cập nhật runbook nếu có bước không đúng hoặc thiếu bằng chứng.

Nếu telemetry bị thiếu trong incident, ghi nhận data gap và dùng health/platform signals độc lập để tránh kết luận sai.

## 17. Bài tập tự kiểm tra

**Bài 1 — Alert contract.** Alert nào cần runbook URL? Một annotation tối thiểu nên chứa những context nào?

**Bài 2 — Severity.** CPU tăng cao nhưng request SLO bình thường. Vì sao có thể chỉ cần warning thay vì paging?

**Bài 3 — HTTP 5xx.** Hãy nêu thứ tự xác minh impact, logs/traces và deployment changes trước mitigation.

**Bài 4 — Pool exhaustion.** Vì sao tăng HikariCP maximum pool size có thể làm database outage nặng hơn?

**Bài 5 — Queue backlog.** Những metrics nào phân biệt producer burst với consumer/downstream bottleneck?

**Bài 6 — Telemetry loss.** Vì sao runbook cần ghi rõ khoảng thời gian telemetry không đầy đủ?

**Bài 7 — Recovery.** Vì sao không đóng incident ngay khi metric vừa xuống dưới threshold một lần?

**Bài 8 — Safety.** Một runbook đề xuất restart toàn bộ pods khi DB health DOWN. Bạn sẽ yêu cầu bổ sung điều kiện gì?

### Gợi ý trả lời

1. Alert actionable/paging cần runbook URL; tối thiểu service/environment, symptom, threshold/window, dashboard và owner.
2. Chưa có user impact và có thể còn headroom; cần xem run queue/throttling và latency trước khi page.
3. Xác nhận request volume/route/status, mở dashboard, kiểm tra logs/traces/dependencies, so deployment timeline rồi mới chọn mitigation.
4. Tổng connections từ mọi replicas có thể vượt DB limit, tăng contention và làm database quá tải.
5. Arrival/completion rate, queue depth, oldest age, consumer lag, processing duration, retries và downstream latency.
6. Người xem dashboard cần biết missing telemetry không phải zero errors/traffic.
7. Cần stable recovery window và kiểm tra SLO/dependencies để tránh flapping hoặc false recovery.
8. Kiểm tra liveness/process health, dependency outage, readiness policy, blast radius, rollback và chỉ restart khi có bằng chứng process cần restart.

## 18. Tài liệu tham khảo chính thức

- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): alert expressions, labels, annotations và duration.
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/): grouping, routing, inhibition và notification.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): alert theo user impact và SLO.
- [Google SRE Workbook — Incident Response](https://sre.google/workbook/incident-response/): incident roles, communication và response process.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics instrumentation và Micrometer integration.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): trace context, sampling và exporter.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle và signal handlers.
- [OpenTelemetry Collector — Resiliency](https://opentelemetry.io/docs/collector/resiliency/): telemetry queue/retry và pipeline reliability.

**Ghi nhớ:** Alert phát hiện symptom; runbook biến symptom thành các bước xác minh, chẩn đoán, mitigation và recovery có thể kiểm chứng. Mỗi alert cần owner, severity, impact, dashboard/log/trace links và tiêu chí đóng rõ ràng. Bắt đầu bằng read-only evidence, chỉ thay đổi production khi hypothesis có bằng chứng và có rollback path. Kiểm thử links, query, quyền truy cập và tabletop exercises định kỳ để runbook hữu ích khi incident thực sự xảy ra.

