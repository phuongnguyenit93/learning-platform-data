# Runbook logging trong Java production

## 1. Mục đích và nguyên tắc sử dụng

**Runbook logging** là tài liệu thao tác có thể thực hiện được khi hệ thống ghi, vận chuyển, tìm kiếm hoặc bảo vệ log trong môi trường production gặp sự cố. Runbook phải giúp người trực vận hành trả lời nhanh: **triệu chứng là gì, dữ liệu mất ở chặng nào, mức độ ảnh hưởng, kiểm tra an toàn nào cần làm, khôi phục bằng cách nào, xác minh ra sao và khi nào cần chuyển cấp**.

Đây không phải danh sách các lệnh “xóa file log cho hết đầy đĩa” hoặc “bật DEBUG toàn hệ thống”. Log vừa là dữ liệu vận hành vừa có thể là chứng cứ bảo mật. Hành động khôi phục phải bảo vệ **dịch vụ, bí mật, tính đầy đủ của audit event và khả năng điều tra**.

Runbook áp dụng cho một ứng dụng Java dùng SLF4J với Logback/Log4j2 hoặc `java.util.logging` (JUL), chạy trên VM hoặc Kubernetes, gửi log qua stdout/file/collector tới hệ thống lưu tập trung. Các tên dịch vụ và namespace bên dưới là **mẫu minh họa**, không đại diện môi trường thật.

### Kết quả mong đợi sau khi xử lý

- Xác định **vị trí lỗi thực tế** trên đường log, thay vì chỉ nhìn thấy dashboard trống rồi kết luận ứng dụng không ghi.
- Khôi phục khả năng **phát, chuyển, tìm và xem log** với mức độ mất dữ liệu được đánh giá trung thực.
- Không làm chậm thêm đường request bằng các thay đổi thiếu kiểm soát.
- Không vô tình tạo log chứa password, token, cookie, PII hoặc nội dung thanh toán khi điều tra.
- Với sự kiện audit/security quan trọng, phân biệt **chưa nhìn thấy**, **chậm đến**, **bị drop** và **được lưu bền vững**.
- Ghi rõ ai làm gì, thời điểm, bằng chứng trước/sau, thời hạn giám sát và trạng thái bàn giao.

## 2. Bản đồ một log event trong production

```text
[Request / Job / Business operation]
                 |
                 v
        [Java call-site]
                 |
          [Level / Filter]
                 |
            [Log event]
            /         \
           v           v
  [Sync appender]   [Async queue] --(full: block / discard / fallback)
           |           |
           |           v
           |      [Consumer]
           |           |
           +-----+-----+
                 |
          [Encoder / Layout]
                 |
         [stdout / file / socket]
                 |
         [Node agent / collector]
                 |
          [Buffer / Transport]
                 |
        [Gateway / Ingestion API]
                 |
       [Parser / Pipeline / Index]
                 |
      [Search API / Dashboard / Alert]
                 |
     [Archive / Snapshot / Export]
```

**Định nghĩa điểm quan sát:** một lần gọi `logger.info` hoàn tất **không** bảo đảm backend đã nhận hoặc lưu event. Với async logging, có thể mới enqueue. Collector trả HTTP thành công có thể chỉ xác nhận nhận batch, không chứng minh event đã searchable hoặc nằm trong archive.

### Bảng khoanh vùng lỗi

| Điểm kiểm tra | Bằng chứng cần tìm | Lý do phổ biến |
| --- | --- | --- |
| Call-site | Code thực sự chạy, level phù hợp | Branch không chạy, logger disabled, exception trước log |
| Logger/filter | Effective level, marker/filter | Log bị loại bởi logger, appender hoặc sampling |
| Appender/encoder | Error counters, status, file/stdout | Pattern sai, formatter lỗi, appender không start |
| Async queue | Depth, enqueue wait, dropped, consumer lag | Queue đầy, consumer chậm, chính sách discard |
| Node stdout/file | Event xuất hiện ở nguồn không | File path sai, permission, rotation, disk full |
| Agent/collector | Read offset, parser errors, send/retry | Không mount log, pipeline crash, network/TLS |
| Backend/index | Ingest rate, rejected events, mapping | Quota, index lifecycle, malformed JSON, tenant routing |
| Search/dashboard | Time window, quyền, query, timezone | Sai filter, index alias, field mapping, clock skew |
| Archive/export | Inventory, checksum, restore | Policy retention, snapshot, bản sao không cập nhật |

Đừng đi thẳng đến cấu hình backend khi chưa biết log có tồn tại ở app source hay không. **Đi từ điểm có bằng chứng gần nhất** tới chặng kế tiếp.

## 3. Phân cấp sự cố và trách nhiệm

Mức độ dưới đây là **gợi ý vận hành**; phải đối chiếu với phân loại sự cố của tổ chức.

| Ưu tiên | Tín hiệu | Hành động ban đầu |
| --- | --- | --- |
| **P0 — Bảo mật khẩn cấp** | Token/password/PII có trong log bị truy cập không phù hợp; audit bị sửa/xóa có dấu hiệu tấn công | Kích hoạt ứng cứu bảo mật, bảo toàn bằng chứng, giới hạn phơi lộ và thu hồi secret |
| **P1 — Ảnh hưởng nghiêm trọng** | Mất security/audit event bắt buộc; logging làm dịch vụ ngừng hoặc p99 tăng nghiêm trọng | Incident commander, chủ ứng dụng + nền tảng + bảo mật phối hợp |
| **P2 — Giảm khả năng quan sát** | Log delay nhiều phút, backlog tăng, một phần service không hiện trên dashboard | Khoanh vùng pipeline và áp remediation có kiểm soát |
| **P3 — Lỗi giới hạn phạm vi** | Một logger cấu hình sai, thiếu field không ảnh hưởng audit, dashboard query lỗi | Ticket và thay đổi theo quy trình thông thường |

Tối thiểu cần có các vai trò: **incident owner** điều phối, **application owner** kiểm code/logger, **platform/observability owner** kiểm agent/collector/backend, **security/compliance owner** khi có secret hoặc audit, và **service on-call** khi throughput/latency bị ảnh hưởng.

**Không tự nâng quyền hoặc xóa evidence.** Nếu thao tác vượt phân quyền trực, kích hoạt escalation. Các tình huống pháp lý, xóa dữ liệu cá nhân và legal hold cần đúng người phê duyệt.

## 4. Năm phút đầu: thao tác kiểm tra an toàn

1. **Ghi lại thời điểm phát hiện (UTC)**, service, environment, instance/pod, các tuyến nghiệp vụ bị tác động và triệu chứng cụ thể.
2. **Xác nhận mức ảnh hưởng:** mất mọi log hay chỉ DEBUG, một pod hay mọi pod, chỉ dashboard hay cả alert, có sự kiện audit/security không?
3. **Không bật TRACE/DEBUG toàn cục**, không dump request body, không restart hàng loạt, không xóa file/index để “dọn” khi chưa hiểu nguyên nhân.
4. **Chọn một cửa sổ thời gian đối chiếu** (ví dụ 15 phút) và giữ timezone thống nhất; ghi thời điểm đổi config/deploy.
5. **Lấy bằng chứng ở nguồn** bằng thao tác read-only: metrics, trạng thái pod, log hiện có, collector errors, thời điểm event gần nhất.
6. **Đặt một hypothesis có thể bác bỏ**: “app không phát”, “agent không đọc”, “queue đầy” hoặc “backend index sai”.
7. **Thông báo mức độ ảnh hưởng bằng dữ kiện**, nêu rõ điều chưa xác minh. Tránh tuyên bố “không mất log” chỉ vì producer không báo lỗi.

### Mẫu ghi chú sự cố

```text
Incident ID: INC-20261110-001 (ví dụ)
Detected at: 2026-11-10T03:00:00Z
Service/environment: checkout-api / production
Symptom: event INFO hiển thị trễ trong search backend
First known good event time: 2026-11-10T02:47:00Z
Latest observed ingestion time: 2026-11-10T02:51:00Z
Scope: một deployment, chưa xác nhận các service khác
Business impact: chưa phát hiện lỗi request; audit status đang kiểm tra
Evidence: pod running; collector retry counter tăng
Current hypothesis: ingestion lag, chưa chứng minh event loss
Action owner: observability on-call
Next checkpoint: sau mỗi lần thay đổi có kiểm soát
```

Các giá trị mẫu là **dữ liệu giả**, không phải kết quả đo của hệ thống thật. Không đưa access token, mật khẩu, raw session cookie hay nội dung người dùng vào ticket.

## 5. Bộ lệnh kiểm tra read-only cho Kubernetes

Các ví dụ sau giả sử namespace `prod` và deployment `checkout-api`. **Thay bằng tên đã được xác nhận trong môi trường vận hành**. Chỉ dùng khi có quyền và không làm lộ dữ liệu khi chia sẻ kết quả.

```bash
# Trạng thái pod và instance đang phục vụ
kubectl -n prod get pods -l app=checkout-api -o wide

# Trạng thái deployment, revision và số replica
kubectl -n prod get deployment checkout-api
kubectl -n prod describe deployment checkout-api

# Lấy một phần log gần đây từ deployment;
# lệnh này không chứng minh đã lấy mọi replica.
kubectl -n prod logs deployment/checkout-api --since=15m --tail=100 --timestamps

# Sự kiện hạ tầng và dấu hiệu restart/eviction
kubectl -n prod get events --sort-by=.lastTimestamp
```

**Giới hạn:** `kubectl logs deployment/...` có thể chọn một pod; không coi nó là bản đầy đủ của toàn deployment. Với multi-container, phải chỉ định container hoặc dùng tùy chọn phù hợp; việc `kubectl logs` có thể đọc được bao nhiêu lịch sử phụ thuộc container runtime/node retention. Không suy log “mất” chỉ vì `kubectl logs` không còn file sau pod restart hoặc log rotation.

Lấy thông tin collector từ namespace và selector **thật đã được đội nền tảng xác nhận**. Ví dụ:

```bash
kubectl -n observability get pods -l app=otel-collector -o wide
kubectl -n observability get deployment
```

Selector `app=otel-collector` chỉ minh họa: cluster có thể dùng DaemonSet, Fluent Bit, Vector, OpenTelemetry Collector hoặc nhãn khác. Không chạy restart/delete collector để kiểm tra giả thuyết ban đầu.

### Trường hợp VM hoặc systemd

```bash
# Ví dụ service Java được quản lý bởi systemd
systemctl status checkout-api.service --no-pager
journalctl -u checkout-api.service --since "15 minutes ago" --no-pager

# Đánh giá tình trạng filesystem chứa log khi phù hợp
df -h
```

Không chạy công cụ in toàn bộ environment hoặc cấu hình secret vào ticket. Với file appender, kiểm tra đúng vị trí output thực tế và quyền đọc được cấp.

## 6. Các chỉ số cần mở trên dashboard

Tên dưới đây là **contract metric gợi ý**, không phải metric mặc định của Java, SLF4J, Logback hay mọi collector:

| Chỉ số | Câu hỏi được trả lời |
| --- | --- |
| `logging_events_attempted_total` | Bao nhiêu event được ứng dụng đề nghị ghi? |
| `logging_events_filtered_total` | Bao nhiêu event bị loại theo level/filter chủ đích? |
| `logging_events_enqueued_total` | Bao nhiêu event đã vào async queue? |
| `logging_events_dropped_total` | Có mất event do overload/exception/policy không? |
| `logging_queue_depth` | Backlog hiện tại tăng hay giảm? |
| `logging_enqueue_wait_seconds` | Producer có bị chặn khi queue đầy không? |
| `logging_sink_errors_total` | File/socket/appender ghi lỗi? |
| `collector_received_total` | Collector nhận từ source bao nhiêu event? |
| `collector_sent_total` / `collector_retry_total` | Gửi lên backend có thành công/đang retry? |
| `backend_ingested_total` / `backend_rejected_total` | Backend có nhận/loại dữ liệu? |
| `event_to_search_lag_seconds` | Log đến searchable backend trễ bao lâu? |
| `last_seen_event_timestamp` | Khoảng trống dữ liệu bắt đầu khi nào? |
| `audit_sequence_gaps_total` | Có gap theo cơ chế sequence đã được thiết kế không? |
| `service_request_duration_seconds` | Logging có ảnh hưởng p95/p99 request không? |
| `process_cpu_usage` / GC / heap | Độ tốn tài nguyên khi đổi logging level |

Nếu metrics không tồn tại thì ghi “không instrumented”, không tự đặt số 0. **Số 0 có ý nghĩa khác không có dữ liệu.**

### Lưu ý đối chiếu counters

Một counter “attempted” đo lời gọi logger, “enqueued” đo sự kiện được queue chấp nhận và “backend ingested” đo sau parser thường có **độ trễ và thời điểm reset khác nhau**. Không lấy chúng ở hai cửa sổ lệch nhau rồi kết luận tất cả chênh lệch đều là log bị mất. Ngoài ra, replay/retry và duplicate có thể khiến số ingested lớn hơn số event duy nhất.

Muốn đối soát đáng tin, cần định nghĩa **measurement boundary**, chuẩn hóa event ID, thời gian quan sát, retry semantics và trường hợp filtered by design. Một biểu đồ “messages accepted” không phải bằng chứng dữ liệu đã lưu bền vững.

## 7. Playbook A — Không thấy log trong dashboard

**Triệu chứng:** hệ thống nhận request bình thường nhưng search UI không có log mới; alert sử dụng log cũng không kích hoạt.

### Bước A1. Xác nhận truy vấn và thời gian

- Kiểm tra environment, service, tenant, index/data stream, namespace, route, level filter và query field.
- So sánh event timestamp với ingestion timestamp. Client clock hoặc collector timezone lệch có thể khiến event nằm ngoài cửa sổ tìm kiếm.
- Kiểm tra quyền search: người dùng thiếu quyền có thể thấy kết quả rỗng hoặc lỗi truy vấn.
- Tìm theo event ID/correlation ID đã được **cho phép ghi**, không dùng raw token/email làm filter.

**Không kết luận “app không log” khi mới chỉ xem một dashboard.**

### Bước A2. Ứng dụng thực sự phát event không?

- Endpoint/job có chạy qua log statement không?
- Effective logger level là gì? Logger cha/root có kế thừa mức khác dự kiến không?
- Có filter, marker, sampling hoặc appender threshold loại event?
- Appender khởi tạo thành công chưa? Có lỗi logback config ở startup không?
- Trong Spring Boot, `logging.level.com.example.checkout=INFO` là cấu hình level, không bảo đảm sink sẽ ghi.
- Với JUL, logger và handler đều có level/filter riêng. Với Logback/Log4j2, backend và location filter quyết định acceptance.

Ví dụ **cấu hình Spring Boot minh họa**, không dùng làm mặc định production nếu chưa đánh giá:

```properties
logging.level.root=INFO
logging.level.com.example.checkout=INFO
```

Nếu INFO không xuất hiện, không vội chuyển toàn root sang DEBUG. Xác định trước logger target và nguồn log.

### Bước A3. Có event ở stdout/file không?

Nếu source có log nhưng backend không có, đi tiếp agent/collector. Với async, kiểm queue depth/drops và consumer; khi queue đầy, event có thể bị discard theo policy dù caller không thấy exception.

Nếu source **không có** log, điều tra path code, effective level, filter, appender, file permission hoặc lỗi startup. Không giả định `logger.info()` luôn phát ra một dòng text.

### Bước A4. Collector và backend

- Agent có đang đọc đúng file/container ID không? Offset sau rotation có bị kẹt?
- Collector parser có báo malformed JSON, quá kích thước, bị quota hay lỗi TLS?
- Có thay đổi route/index/tenant mapping trong deployment gần nhất không?
- Backend có bị reject do index read-only, hết quota, mapping conflict hoặc permission?
- Index lifecycle/retention có xóa backing index đang được truy vấn không?

**Hành động an toàn:** sửa config sai trên nhánh đã review, rollback deployment gây lỗi hoặc xử lý kết nối/permission theo owner. Không dùng replay mù từ file cũ trước khi đánh giá duplicate/event ID và khối lượng ingest.

### Đóng playbook A khi

- Cùng một event thử không chứa secret có mặt ở source và sink dự kiến.
- Backend query theo đúng event ID trả dữ liệu trong khoảng SLO.
- Counters và lag ổn định; không còn parser/auth errors tương ứng.
- Đã đánh giá khoảng trống dữ liệu lịch sử và nhu cầu backfill.

## 8. Playbook B — Log đến chậm, collector retry hoặc queue backlog

**Triệu chứng:** source có log nhưng dashboard đến muộn; queue tăng, collector retry hoặc độ trễ ingest vượt SLO.

### Khoanh vùng

1. Kiểm tra **event time vs ingestion time** với vài event đã được phép dùng để đối chiếu.
2. Xem queue ở **Java appender** và buffer ở **agent/collector**; hai chặng có thể bị nghẽn khác nhau.
3. Kiểm throughput nguồn, tốc độ sink, retry/backoff và network/TLS status.
4. Kiểm sink đang xử lý/parse/chỉ mục chậm hay không; có bản ghi quá lớn hoặc malformed?
5. Kiểm điều kiện recent deployment, tăng DEBUG/TRACE, traffic spike và thay encoder.

```text
If incoming_rate > sustained_consumption_rate:
    backlog grows, regardless of queue size
```

Queue lớn có thể chịu burst ngắn nhưng **không tăng năng lực sink về dài hạn**.

### Remediation theo rủi ro

- Giảm **log nhiễu không bắt buộc** tại nguồn bằng thay đổi level/rate-limit đã được review, không drop audit bắt buộc.
- Hạn chế message quá lớn hoặc formatter đắt; không dump body/header/stack trace không cần thiết.
- Xử lý năng lực/độ ổn định collector hoặc backend theo owner, quan sát circuit breaker và throttling.
- Nếu cần scale collector, phải xem partitioning, duplicate, ordering, số kết nối và chi phí; tăng replica không luôn làm nhanh hơn.
- Xác định chính sách khi queue đầy: **block producer**, **discard**, **fallback sync** hay **spool disk**. Mỗi lựa chọn có hệ quả về latency, mất log và độ bền.
- Cần xử lý event đã nằm trong spool theo trình tự có kiểm soát; không xóa queue chỉ để đồ thị depth về 0.

**Không coi độ trễ producer thấp là hệ thống khỏe.** Async appender có thể trả nhanh trong khi collector backlog tăng và backend không searchable.

### Đóng playbook B khi

Queue không tiếp tục tăng ở tải ổn định, log end-to-end lag về trong mục tiêu, retry/drops được ghi nhận, và dữ liệu quá khứ đã được xử lý hoặc phân loại phần không thể khôi phục.

## 9. Playbook C — Log volume tăng đột biến, CPU/disk tăng

**Triệu chứng:** số event hoặc byte log tăng mạnh sau một release, khi có lỗi lặp, brute-force, hoặc do ai đó bật DEBUG/TRACE. CPU, disk I/O, chi phí ingest và request p99 có thể tăng.

### Kiểm tra nhanh

- Bắt đầu tăng từ lúc nào, gắn với version/config change nào?
- Event thuộc package/logger, endpoint hoặc loại exception nào? Dùng **metadata và sample đã sanitize**, tránh in nội dung nhạy cảm.
- Tăng số **event** hay tăng kích thước **mỗi event** (stack trace, JSON fields, body)?
- Collector có bắt đầu drop hoặc queue đầy? Disk quota/rotation gần giới hạn không?
- Logging có đồng bộ trên request thread không? Appender tranh chấp lock hoặc ghi console chậm không?
- Có lỗi nghiệp vụ thật khiến WARN/ERROR tăng không? Không chỉ “giảm logging” mà bỏ qua nguyên nhân.

### Hành động an toàn ưu tiên

1. Nếu đây là **sự cố ứng dụng**, xử lý nguyên nhân phát event lặp; giảm spam chỉ là biện pháp phụ.
2. Với DEBUG/TRACE tạm thời đã bật, **hoàn nguyên đúng logger/package** theo change record nếu có; không đổi root vô kiểm soát.
3. Bỏ log payload/raw object không cần thiết, ưu tiên allowlist trường an toàn.
4. Đánh giá queue policy; block producer có thể ảnh hưởng p99, còn drop có thể làm mất chứng cứ.
5. Kiểm disk/log rotation, không xóa file active hoặc archive đang được tail bởi collector.
6. Nếu storage/budget sắp vượt ngưỡng, mở escalation với platform để tăng tài nguyên hoặc thay routing/retention theo quy trình.

**Đừng xóa file log đang được process giữ file descriptor** để kỳ vọng disk được trả ngay: trên nhiều filesystem, dung lượng có thể chưa thu hồi cho đến khi descriptor được đóng. Cũng không truncate audit file mà không có phê duyệt, vì mất bằng chứng.

### Xác minh

Theo dõi event rate, bytes/sec, CPU, GC, disk free, app p95/p99, dropped events và collector lag sau thay đổi. Một đồ thị CPU giảm không đủ để kết luận thành công nếu log bắt đầu bị drop hàng loạt.

## 10. Playbook D — Logging làm request chậm hoặc ứng dụng treo

**Triệu chứng:** request latency tăng sau thay logging config; thread dump cho thấy appender/write/lock, hoặc async queue chặn producer.

### Nguyên nhân thường gặp

- `logger.debug("{}", expensiveObject.toString())` khiến Java tính đối số trước method call dù DEBUG tắt.
- Formatter JSON, stack trace, caller location, MDC snapshot hoặc serialize object quá lớn.
- Synchronous file/console/network appender trên request thread bị I/O chậm.
- `AsyncAppender` có hàng đợi đầy; tùy policy, producer có thể block hoặc event bị drop.
- Lock contention hoặc encoder/parser lỗi gây retry/flush lặp.
- CPU/GC tăng do allocation khi phát nhiều event.

Ví dụ code **không tối ưu**:

```java
// Trích đoạn không độc lập, cần logger và hàm buildDebugSnapshot().
logger.debug("snapshot={}", buildDebugSnapshot());
```

Dù DEBUG tắt, Java vẫn thực thi `buildDebugSnapshot()` trước khi gọi logger. Cách cân nhắc:

```java
if (logger.isDebugEnabled()) {
    logger.debug("snapshot={}", buildDebugSnapshot());
}
```

Đây vẫn là trích đoạn; nếu appender filter sau đó loại event thì một phần công việc có thể đã xảy ra. Với SLF4J 2.x có fluent supplier API ở một số tình huống, cần test theo phiên bản/backend thật.

### Quy trình điều tra

1. So sánh request latency, throughput, CPU, GC và logging configuration trước/sau khi thay đổi trên **cùng workload**.
2. Nếu có JFR hoặc profiler đã được cho phép, kiểm CPU hot methods, allocations, File/Socket I/O và thread contention.
3. Tách chi phí **call-site**, **queue**, **consumer** và **sink**; đừng chỉ nhìn thời gian `logger.info()` trả về.
4. Cân nhắc điều chỉnh logger chi tiết, formatter/fields hoặc sink theo plan; ưu tiên biện pháp ít thay đổi nhất.
5. Với traffic cao, kiểm ngưỡng queue và behavior khi sink chậm. Thử điều kiện xấu ở staging trước nếu khả thi.
6. Xác minh rằng không hy sinh security/audit records bắt buộc chỉ để giảm p99.

Không giả định “async luôn nhanh và không mất log”. Quyền ưu tiên của dịch vụ và yêu cầu log phải được quyết định trong SLO/incident policy.

## 11. Playbook E — Token, mật khẩu hoặc PII xuất hiện trong log

**Triệu chứng:** một field có secret hoặc dữ liệu nhạy cảm bị ghi vào stdout, stack trace, access log, collector, dashboard hoặc export. Đây là tình huống cần liên hệ security on-call theo chính sách.

### Phản ứng tức thời

1. **Giới hạn lan truyền:** đừng copy raw token vào ticket, chat, ảnh chụp hoặc email; dùng case ID và mẫu đã sanitize.
2. **Giảm phát sinh mới ở nguồn:** xác định logger/encoder/endpoint/HTTP client/exception đang ghi; chọn thay đổi đã review để dừng capture payload hoặc thay bằng trường allowlist.
3. **Thu hồi hoặc rotate secret bị lộ** theo loại secret và phạm vi ảnh hưởng; xóa một dòng log không vô hiệu hóa credential.
4. **Đánh giá phạm vi sao chép:** app file/stdout → collector buffer → index → archive → snapshot → export/link tải.
5. **Kiểm soát quyền truy cập:** tạm hạn chế index hoặc export có nguy cơ nếu được người có thẩm quyền cho phép.
6. **Bảo toàn chứng cứ cần thiết:** giữ timeline, nguồn và ai đã truy cập/export, không tự hủy dữ liệu dưới legal hold hoặc audit requirement.
7. **Khắc phục triệt để:** test regression bằng canary giả, chặn body/header nhạy cảm, kiểm encoding/masking và các logger của dependency.

### Dấu hiệu dễ bỏ sót

- Raw `Authorization`, `Cookie` hoặc `Set-Cookie` trong request/response headers.
- Token nằm trong **query string hoặc path** của reset URL.
- `toString()` của DTO chứa mật khẩu/PII.
- HTTP client DEBUG hoặc exception message chứa raw URI/response body.
- Tracing baggage/MDC được copy vào mọi log.
- Dashboard đã che nhưng raw index/export vẫn còn dữ liệu.

**Không chỉ dựa vào regex ở collector.** Data minimization phải bắt đầu trước khi event được xây. Với dữ liệu không cần thu, giải pháp tốt nhất là **không đưa vào logger**.

### Điều kiện đóng

Có bằng chứng đã chặn phát sinh mới, secret có giá trị đã được xử lý, phạm vi dữ liệu cũ và quyền truy cập đã được phân loại, và security/compliance xác nhận quy trình xử lý hợp lệ. Không tuyên bố “không còn bản sao” khi chưa kiểm tra backup/export.

## 12. Playbook F — Trace ID, request ID hoặc MDC bị thiếu/sai

**Triệu chứng:** tìm theo trace ID không đủ các service, event của request A mang `tenant_id`/`user_id` của B, hoặc event async mất correlation context.

### Nguyên nhân

- Context chưa được tạo hoặc chưa propagate qua thread pool, queue hoặc HTTP client.
- `MDC.put` thiếu `finally` cleanup, thread được tái sử dụng nên rò dữ liệu giữa request.
- Async logger lấy MDC ở thread consumer thay vì snapshot tại producer time.
- `traceparent` hoặc `X-Request-ID` do client đưa vào không được validate.
- Gateway đổi/loại header, downstream tạo trace mới, hoặc log encoder không serialize MDC.
- Field mapping của collector đổi `trace_id` sang tên khác hoặc nằm ở nested object.

### Bước xử lý

1. Chọn một request thử **không chứa secret** với request ID/trace ID được phép dùng.
2. Kiểm ở gateway, HTTP middleware, business event, async worker, collector và backend để tìm chặng mất context.
3. Xác minh ID được tạo/parse theo spec và namespace của hệ thống, không lấy user identity từ trace ID.
4. Kiểm cách lưu/khôi phục MDC trong `try/finally` và propagation trong executor/task context.
5. Kiểm schema encoder: key `trace_id` có bị đổi, thiếu hoặc ghi thành chuỗi rỗng?
6. Kiểm concurrency và tenant isolation bằng test nhiều request cùng lúc.

Trích đoạn SLF4J cần thư viện và ngữ cảnh ứng dụng, **không độc lập**:

```java
String before = org.slf4j.MDC.get("request_id");
org.slf4j.MDC.put("request_id", validatedRequestId);
try {
    handleRequest();
} finally {
    if (before == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", before);
    }
}
```

Đoạn này chỉ lưu/khôi phục **một key**. Với nhiều key, framework context propagation hoặc scoped MDC nên được thiết kế nhất quán; không dùng `MDC.clear()` bừa bãi khi tầng cha còn context hợp lệ.

**Cảnh báo:** `trace_id` đúng format không có nghĩa actor đã được xác thực. Security/audit log cần principal/workload identity đã xác minh, không dựa header do client tự chọn.

## 13. Playbook G — Sai retention hoặc log bị xóa quá sớm

**Triệu chứng:** log chỉ còn vài ngày thay vì retention mong muốn; file/indices/archives bị dọn, hoặc truy vấn lịch sử không có dữ liệu.

### Tách ba phạm vi

| Phạm vi | Cơ chế | Điều cần kiểm |
| --- | --- | --- |
| **File local** | Logback `RollingFileAppender`/Log4j2 Rollover Strategy | Pattern, rollover, maxHistory, totalSizeCap, disk cleanup |
| **Container/node** | Kubelet/container runtime rotation | Giới hạn file trên node, pod restart/eviction, tốc độ ship |
| **Backend/archive** | Index lifecycle, object lifecycle, snapshots | Index age, event time vs ingest time, retention class, legal hold |

**Rotation khác retention** và retention khác **xóa tất cả bản sao**. Backend xóa index chưa có nghĩa archive, snapshot và CSV export đã biến mất.

### Khi nghi xóa quá sớm

1. Dừng mọi thay đổi lifecycle không khẩn cấp; **không tự tắt toàn retention vô thời hạn**.
2. Kiểm event class, policy version, ngày bắt đầu tính tuổi, timezone và index rollover.
3. Xác nhận có hay không bản sao trong archive/snapshot/backup và quyền restore.
4. Kiểm legal hold và thẩm quyền sửa policy; nếu audit bắt buộc có nguy cơ mất, kích hoạt compliance/security.
5. So sánh dữ liệu từ source với backend và ghi rõ phần **có thể đã mất vĩnh viễn**; không giả định restore chắc chắn thành công.
6. Với thay đổi policy, chạy dry-run, impact count/size, approval và rollback plan trước khi áp.

**Không chạy bulk delete/index delete để “test retention” trên production.** Dùng môi trường test và dữ liệu giả để kiểm đợt dọn.

## 14. Playbook H — Audit/security event mất hoặc bị nhân đôi

**Triệu chứng:** một thay đổi quyền đã commit nhưng không tìm thấy event audit; hoặc một giao dịch có nhiều bản ghi SUCCESS do retry.

### Phân biệt trạng thái

- **Attempted:** đã bắt đầu xử lý.
- **Authorized/Denied:** kết quả kiểm tra quyền.
- **Committed:** thay đổi nghiệp vụ đã commit.
- **Enqueued:** event đã vào queue, chưa chắc lưu bền vững.
- **Written/ingested:** sink/backend đã nhận theo định nghĩa riêng.
- **Indexed/searchable:** event có thể query được.
- **Archived:** bản lưu dài hạn được xác nhận theo quy trình.

Nếu application log phát `SUCCESS` trước transaction commit rồi rollback, đó là **sai outcome**, không hẳn “logging mất”. Nếu request tạo async job, HTTP 202 chỉ là accepted, không phải completed.

### Quy trình

1. Định vị business operation/transaction bằng ID được phép dùng.
2. Xác định mốc kết quả thật từ database/outbox hoặc business state.
3. Tìm event ở source, async queue/outbox, collector và backend theo `event.id`/`operation_id`.
4. Đo retry/duplicate và thời gian ingest; tránh đếm số dòng là số thao tác nghiệp vụ nếu có at-least-once delivery.
5. Với audit yêu cầu độ bền cao, đánh giá transactional outbox hoặc dedicated audit store, không phụ thuộc một queue log debug có discard.
6. Nếu nhận thấy chỉnh sửa/xóa evidence trái phép, bảo toàn bằng chứng và báo security ngay.

**Không tự backfill sự kiện lịch sử với actor/outcome tự đoán.** Nếu phải tái dựng, đánh dấu nguồn, thời điểm và độ tin cậy của event tái dựng, giữ trail của hành động bổ sung.

## 15. Playbook I — JSON log, schema hoặc parser đột nhiên lỗi

**Triệu chứng:** collector báo parse error, dashboard thiếu field `trace_id` hoặc number biến thành string sau deploy; log source còn nhưng backend mapping hỏng.

### Kiểm tra

- Event đang là JSONL hay text? Có stack trace nhiều dòng ngoài JSON không?
- Ký tự CR/LF, dấu nháy, Unicode control được escape đúng?
- Key `http.status_code` là number hay string; `duration_ms` dùng đúng đơn vị?
- Backend encoder/Logback layout/Log4j2 JSON Template Layout có thay đổi không?
- Collector parser/mapping đang đọc flat key hay nested object?
- Có duplicate fields, field collision hoặc index mapping conflict?
- Có lỗi do event quá lớn hoặc payload nested sâu không?
- Log chứa dữ liệu untrusted có nguy cơ injection vào dashboard/CSV export không?

Ví dụ JSONL an toàn về **cú pháp**:

```json
{"event.name":"checkout.failed","http.status_code":502,"duration_ms":36,"message":"gateway\nretry"}
```

Ở đây `\n` nằm **trong JSON string sau escaping**, không phải một dấu xuống dòng vật lý giữa hai record.

### Hướng xử lý

1. Capture một **event đã sanitize** ở source và output sau encoder.
2. Parse bằng JSON parser độc lập, kiểm required fields/types.
3. So với schema contract/version đã triển khai.
4. Nếu release/encoder mới làm hỏng format, rollback cấu hình theo change process hoặc rollout bản sửa nhỏ đã test.
5. Đối soát những event bị reject và xử lý replay/backfill nếu thật sự cần, chú ý duplicate.
6. Kiểm cả dashboard/alert query sau khi schema được khôi phục.

Không tự biến malformed JSON thành “hợp lệ” bằng cách loại mọi dấu nháy hoặc dump raw payload vào log lỗi parser.

## 16. Java 17 runnable: mô phỏng cách phân loại snapshot sự cố

Để rèn cách nghĩ theo từng chặng, ví dụ **`LoggingRunbookDemo.java`** dưới đây là **một bộ đánh giá snapshot giả**, không chạm hạ tầng, không gọi network và không xóa log. Chương trình kiểm các counter có cùng **ranh giới và trạng thái đã được đối soát** trong mô hình đơn giản:

- `offered`: event được gửi tới pipeline giả.
- `accepted`: event vào queue giả.
- `consumed`: worker đã lấy khỏi queue.
- `ingested`: backend giả đã nhận theo model.
- `dropped`: event không vào queue do policy.
- `backlog`: event còn chờ trong queue.
- `sensitiveCanaryDetected`: test giả đánh dấu khả năng có secret trong sink.

Vì mô hình đã được đối soát, nó áp đặt `offered = accepted + dropped` và `backlog = accepted - consumed`. **Trong production không áp dụng trực tiếp các đẳng thức này cho counters đọc từ nhiều process/time window** do reset, retry, replay, duplicate, filter, event đến muộn hoặc event đã được xử lý trước cửa sổ quan sát.

Lưu thành tệp **`LoggingRunbookDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public final class LoggingRunbookDemo {
    enum Diagnosis {
        SECRET_EXPOSURE,
        EVENT_LOSS,
        QUEUE_BACKLOG,
        INGEST_LAG,
        HEALTHY
    }

    record Snapshot(
            String name,
            long offered,
            long accepted,
            long consumed,
            long ingested,
            long dropped,
            long backlog,
            boolean sensitiveCanaryDetected) {

        Snapshot {
            Objects.requireNonNull(name, "name");
            if (name.isBlank() || offered < 0 || accepted < 0
                    || consumed < 0 || ingested < 0
                    || dropped < 0 || backlog < 0
                    || dropped > offered
                    || accepted != offered - dropped
                    || consumed > accepted
                    || ingested > consumed
                    || backlog != accepted - consumed) {
                throw new IllegalArgumentException("Inconsistent snapshot");
            }
        }
    }

    private static Diagnosis diagnose(Snapshot s) {
        if (s.sensitiveCanaryDetected()) {
            return Diagnosis.SECRET_EXPOSURE;
        }
        if (s.dropped() > 0) {
            return Diagnosis.EVENT_LOSS;
        }
        if (s.backlog() > 0) {
            return Diagnosis.QUEUE_BACKLOG;
        }
        if (s.ingested() < s.consumed()) {
            return Diagnosis.INGEST_LAG;
        }
        return Diagnosis.HEALTHY;
    }

    public static void main(String[] args) {
        List<Snapshot> samples = List.of(
                new Snapshot("healthy",
                        1000, 1000, 1000, 1000, 0, 0, false),
                new Snapshot("queue_full",
                        1000, 800, 760, 700, 200, 40, false),
                new Snapshot("collector_slow",
                        600, 600, 600, 500, 0, 0, false),
                new Snapshot("worker_backlog",
                        600, 600, 550, 550, 0, 50, false),
                new Snapshot("secret_canary",
                        200, 200, 200, 200, 0, 0, true));

        for (Snapshot snapshot : samples) {
            System.out.println(snapshot.name() + " -> "
                    + diagnose(snapshot)
                    + " | backlog=" + snapshot.backlog()
                    + " dropped=" + snapshot.dropped());
        }

        boolean invalidRejected = false;
        try {
            new Snapshot("bad",
                    10, 9, 9, 9, 0, 0, false);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        if (!invalidRejected) {
            throw new AssertionError("Invalid snapshot was accepted");
        }
        System.out.println("invalid_snapshot -> REJECTED");
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac --release 17 LoggingRunbookDemo.java
java LoggingRunbookDemo
```

**Stdout chính xác:**

```text
healthy -> HEALTHY | backlog=0 dropped=0
queue_full -> EVENT_LOSS | backlog=40 dropped=200
collector_slow -> INGEST_LAG | backlog=0 dropped=0
worker_backlog -> QUEUE_BACKLOG | backlog=50 dropped=0
secret_canary -> SECRET_EXPOSURE | backlog=0 dropped=0
invalid_snapshot -> REJECTED
ALL CHECKS PASSED
```

**Giải thích ý nghĩa giáo dục:**

- `queue_full`: có 200 event bị drop, ưu tiên đánh dấu **EVENT_LOSS** dù cũng có queue backlog và ingestion lag.
- `collector_slow`: không drop/queue backlog trong snapshot nhưng backend có ít event hơn worker đã xử lý, nên **INGEST_LAG**.
- `worker_backlog`: còn 50 event trong queue, nên **QUEUE_BACKLOG**.
- `secret_canary`: cờ giả báo phát hiện canary, ưu tiên **SECRET_EXPOSURE** dù counts cân bằng.
- `invalid_snapshot` bị từ chối do tổng offered không khớp accepted + dropped theo mô hình đồng bộ giả.

**Không dùng bài demo làm hệ thống giám sát production.** Real counters có time window, partitions, đồng hồ, stage semantics và kiểu ack khác nhau; leak detection còn cần canary/secret scanning bảo vệ dữ liệu, không chỉ một boolean. Demo không thay incident priority do tổ chức quyết định và không có tự động remediation.

## 17. Cấu hình logging production: điều chỉnh có kiểm soát

### Mức logger và phạm vi thay đổi

Với Spring Boot, có thể cấu hình level riêng theo package thay vì bật toàn root:

```properties
logging.level.root=INFO
logging.level.com.example.checkout=INFO
logging.level.com.example.checkout.payment=WARN
```

Các giá trị là ví dụ. Một cấu hình như `logging.level.com.example.checkout.payment=DEBUG` có thể giúp điều tra nhưng cần **review nội dung log, thời hạn bật, người phụ trách rollback**, và không được thu token/body/PII. Thay level không tự thay đổi `AccessLogValve`, collector hay backend.

### Ví dụ Logback async, nêu rõ đánh đổi

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>8192</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <appender-ref ref="STDOUT"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

**Đây là cấu hình thử nghiệm để hiểu policy, không phải khuyến nghị sao chép vào production.**

- `queueSize=8192` là giới hạn queue (theo số event), không phải bytes và không giải quyết sustained sink overload.
- `discardingThreshold=0` tắt cơ chế discard sớm mặc định của Logback AsyncAppender đối với event thấp; **không có nghĩa tuyệt đối không bao giờ mất log**, đặc biệt khi crash/termination hoặc lỗi sink.
- `neverBlock=false` khiến producer **có thể bị chặn khi queue đầy**, ảnh hưởng trực tiếp p99 latency của request.
- Với `neverBlock=true`, queue đầy có thể làm mất event thay vì block producer; cần đánh giá khả năng chấp nhận mất dữ liệu.
- Cấu hình pattern text **không tự escape dữ liệu không tin cậy hoặc che secret**; hãy xây message/fields an toàn ở nguồn.
- Nếu cần audit có bảo đảm lưu bền vững, cân nhắc kênh/outbox chuyên dụng thay vì chỉ dựa vào async debug appender.

Trước khi thay policy queue, chạy thử sink chậm, burst traffic, shutdown và failure mode với counters rõ ràng.

### JUL và Log4j2

- **JUL** có level/filter trên cả `Logger` và `Handler`; một level bật tại logger không bảo đảm handler nhận.
- **Log4j2** có nhiều placement của filters, synchronous/async logger, appender và layout; dùng đúng cấu hình phiên bản đang triển khai.
- **SLF4J** là facade; backend mới quyết định encoder/queue/file cụ thể.
- Không copy “mẹo Logback” sang Log4j2/JUL mà không đối chiếu API và phiên bản.

## 18. Quy trình bật DEBUG tạm thời trong sự cố

Một thay đổi cấp log có thể giúp chẩn đoán nhưng cũng có thể tăng volume hoặc lộ secret.

1. **Nêu câu hỏi cần trả lời:** ví dụ “vì sao retry HTTP client tăng” thay vì “muốn xem mọi thứ”.
2. **Xác định package/logger cụ thể**, một vài instance hoặc phạm vi canary nếu hạ tầng hỗ trợ.
3. **Review code/fields có thể xuất hiện ở DEBUG**, đặc biệt headers/body/token và exception.
4. **Thiết lập thời gian kết thúc/điểm kiểm tra và rollback owner**; ghi config version trước thay đổi.
5. **Triển khai qua đường thay đổi được phê duyệt**, không kích hoạt endpoint quản trị công khai.
6. **Theo dõi queue/drops, CPU, GC, disk, collector lag và request p95/p99**.
7. **Thu thập bằng chứng đã sanitize** phục vụ giả thuyết; không copy raw credentials.
8. **Hoàn nguyên và xác minh effective level** trên mọi instance, rồi đóng change record.

Nếu ứng dụng có Spring Boot Actuator `/actuator/loggers`, phải bảo vệ endpoint bằng authentication/authorization và audit thao tác đổi level. Không dùng lệnh hoặc URL công khai trong runbook để bật DEBUG trực tiếp mà không có kiểm soát.

## 19. Rollback và khôi phục: quy tắc trước khi thay đổi production

Mỗi thay đổi phải trả lời được:

| Câu hỏi | Nội dung phải có |
| --- | --- |
| **What** | Thay đúng logger, collector pipeline, deployment, ILM hay sink nào? |
| **Why** | Bằng chứng liên kết thay đổi với triệu chứng |
| **Owner** | Người thực hiện, người phê duyệt và người có quyền rollback |
| **Blast radius** | Một pod, một service, một tenant hay toàn cluster? |
| **Data effect** | Có làm mất/trùng/chậm log, đổi retention hoặc mở rộng quyền đọc không? |
| **Before** | Config version, metrics, event sample đã sanitize |
| **Success criteria** | Lag/drops/errors/request latency ở ngưỡng nào? |
| **Rollback trigger** | Chỉ số hoặc sự kiện nào buộc phải hoàn nguyên? |
| **Rollback method** | Phương pháp đã kiểm thử theo công cụ triển khai hiện hữu |
| **After** | Đối soát source/backend, thời gian giám sát và lịch sử sự cố |

**Ưu tiên thay đổi nhỏ, có thể đảo ngược.** Không restart toàn bộ collector hoặc xóa queue chỉ để xem đồ thị có hết đỏ; hành động đó có thể làm mất dữ liệu chưa gửi.

Khi rolling back config encoder, xem event schema của dữ liệu đang trong queue; collector cũ có thể không parse được event mới, hoặc ngược lại. Với migration index, rollback có thể cần hỗ trợ hai schema đồng thời.

## 20. Khi có khả năng mất log: thông báo như thế nào?

Tách ba nhận định:

- **Chưa tìm thấy:** có thể do time filter, quyền, lag hoặc index query; chưa chứng minh mất.
- **Đang chậm:** source/enqueue có event, collector/backend còn tồn backlog; chưa chắc event cuối sẽ tới.
- **Đã mất:** có counter/ack/gap hoặc bằng chứng cơ chế drop/rotation/crash làm không thể phục hồi event theo pipeline hiện tại.

Tránh khẳng định 100% đã mất hoặc chưa mất chỉ từ một dashboard trống.

**Ví dụ bản cập nhật sự cố có căn cứ:**

```text
03:20 UTC — checkout-api ghi log nguồn bình thường ở các pod đã kiểm tra.
Collector retry tăng; backend ingestion trễ so với event time khoảng vài phút
trên tập mẫu. Chưa có bằng chứng xác nhận mất dữ liệu; counter drop chưa
được instrument đầy đủ nên vẫn còn rủi ro. Không ghi nhận thay đổi business
error rate trong cửa sổ đối chiếu. Observability owner đang khoanh vùng sink.
Thay đổi cấu hình chưa được thực hiện.
```

Nội dung giả trên minh họa cách dùng từ chính xác; không được gửi như báo cáo của một hệ thống thật khi chưa có quan sát tương ứng.

## 21. Kiểm thử runbook định kỳ ở staging

**Runbook phải được diễn tập**, không chỉ được lưu trên wiki. Các bài diễn tập an toàn nên dùng service test, log canary và backend/namespace tách biệt.

| Tình huống thử | Mục đích |
| --- | --- |
| Effective DEBUG bị tắt | Tìm đúng chặng logger/level |
| Thay appender path hoặc giả lập permission denied | Phát hiện sink write error |
| Chặn kết nối collector giả | Phát hiện retry, backlog, data-lag |
| Queue có giới hạn + sink chậm | Thấy block/drop theo policy |
| Bật DEBUG ở package test | Đo CPU/p99/volume và rollback |
| Event có JSON sai kiểu | Chẩn đoán parser/mapping conflict |
| Request với trace ID test | Tìm correlation qua gateway/service/backend |
| MDC không được restore trong code test | Phát hiện context bleed giữa request |
| Canary trong field bí mật giả | Xác minh secret không xuất hiện trong log |
| Replay một batch đã được ingest | Kiểm duplicate semantics |
| Thử index lifecycle trên dữ liệu giả | Xác minh retention, archive, legal hold |
| Shutdown với async queue còn backlog | Đánh giá drain/khả năng mất event |

Đặt tiêu chí **PASS/FAIL** cụ thể cho từng diễn tập: thời gian phát hiện, người nhận alert, thời gian khoanh vùng, số event thất lạc/trùng, khả năng rollback và chất lượng thông tin bàn giao.

Với diễn tập bí mật, dùng `SENSITIVE_CANARY_314` hoặc chuỗi giả tương tự, **không dùng token thật**. Với retention/deletion, dùng dry-run và index/bucket test, không xóa log production.

## 22. Kiểm tra sau remediation và điều kiện đóng incident

Không đóng chỉ vì “dashboard đã có điểm xanh”. Kiểm:

1. Một event test có ID hợp lệ hiện ở **source → collector → backend query** trong cùng cửa sổ và thời gian kỳ vọng.
2. Độ trễ ingest/queue về mức SLO hoặc đang giảm bền vững dưới tải bình thường.
3. Dropped/error counters không tăng bất thường; nếu đã mất dữ liệu, nêu phạm vi và cách khôi phục/đối soát.
4. Request p95/p99, CPU, heap, GC, disk và throughput không suy giảm sau thay đổi.
5. Security/audit events được xác minh độc lập khi có yêu cầu.
6. Không có credential/PII mới phát sinh trong các event thử; backend/export đã được review khi liên quan.
7. Effective configuration đúng trên **mọi instance** chịu ảnh hưởng; rollback đã thực hiện nếu DEBUG tạm thời.
8. Retention/archival không bị thay ngoài ý muốn.
9. Incident owner và service owner xác nhận điều kiện đóng; còn rủi ro tồn đọng được giao người theo dõi.

### Mẫu checklist đóng

```text
[ ] Incident scope và thời gian đã xác nhận
[ ] Điểm lỗi trong pipeline đã xác định bằng bằng chứng
[ ] Config trước/sau và lý do thay đổi đã lưu
[ ] Source, collector, backend readback/ingest đã đối chiếu
[ ] Dropped/duplicated/backlog được định lượng hoặc ghi là chưa xác minh
[ ] Security/audit status đã được owner đánh giá
[ ] Bí mật/PII không tiếp tục lọt vào log
[ ] SLO về latency, throughput và pipeline được đáp ứng
[ ] DEBUG tạm thời và các workaround đã hoàn nguyên/ghi nhận
[ ] Giao việc theo dõi, postmortem và ngăn tái diễn
```

## 23. Post-incident review và cải tiến runbook

Sau sự cố, tổng hợp **timeline theo UTC**, thay đổi cấu hình/deploy, bằng chứng source/backend, các giả thuyết đúng/sai, và quyết định đã được phê duyệt. Một bản review tốt trả lời:

- Vì sao alert/metric không phát hiện sớm?
- Thiếu telemetry ở chặng nào (appender/queue/collector/index)?
- Khi xảy ra lỗi, đã block producer, drop log hay retry và tác động nghiệp vụ ra sao?
- Mức độ mất dữ liệu có thể xác nhận tới đâu; có event quan trọng bị ảnh hưởng không?
- Có nguy cơ dữ liệu nhạy cảm hoặc quyền truy cập quá rộng không?
- Quy trình rollback và phối hợp giữa app/platform/security có bị vướng?
- Bộ test nào ngăn tái diễn lỗi logger level/schema/retention/MDC?
- Runbook nào thiếu command/field/owner rõ ràng và cần bổ sung?

Action items nên có owner, điều kiện hoàn tất và regression test, không chỉ ghi “cần giám sát tốt hơn”.

## 24. Thẻ tra cứu nhanh theo triệu chứng

| Triệu chứng | Kiểm trước tiên | Nhánh runbook |
| --- | --- | --- |
| Search không có log | Query/time/permission → source stdout/file | A |
| Source có, backend trễ | Collector retry, queue, lag, TLS/ingest | B |
| Disk/CPU tăng mạnh | Logging level, event rate/size, sink | C |
| p99 tăng sau thay logging | Async full/block, formatter, thread I/O | D |
| Secret trong log | Dừng lan truyền, security response, revoke/rotate | E |
| Trace/request ID sai | MDC scope, propagation, encoder field | F |
| Log cũ biến mất | File/node vs backend retention, archive/hold | G |
| Audit event thiếu/trùng | Business commit vs event/outbox/ingest | H |
| JSON mapping lỗi | Actual encoder output, parser, schema version | I |

## 25. Checklist duy trì runbook trong production

- [ ] Service và logging owner được nêu rõ; có escalation tới platform và security.
- [ ] Pipeline map cập nhật đúng stack (Logback/Log4j2/JUL, stdout/file, collector, backend).
- [ ] Có metric/alert cho drop, queue, ingest lag, sink errors và storage capacity.
- [ ] Có phương pháp đối soát theo event ID/correlation ID đã kiểm soát.
- [ ] Có câu lệnh read-only kiểm tra pod/VM/source mà không dump secret.
- [ ] Không dùng log level để thay thế security event/audit trail.
- [ ] Biết chính sách backpressure, discard, spool, shutdown và behavior khi sink hỏng.
- [ ] Có runbook xử lý secret leak/PII và quy trình giữ chứng cứ.
- [ ] Có quy tắc bật DEBUG tạm thời, expiry, rollback owner và kiểm soát quyền.
- [ ] Có quy định retention, legal hold, archive, snapshot và backup.
- [ ] Có cách phân biệt missing, delayed, filtered by design và irrecoverable loss.
- [ ] Có kiểm thử concurrency/MDC, JSON schema và end-to-end ingest.
- [ ] Có tiêu chí đóng incident, người xác nhận, postmortem và regression actions.

**Ghi nhớ:** một runbook logging hữu ích không bắt đầu bằng việc “đổi level” hay “restart collector” mà bằng **xác định đúng chặng pipeline, bảo vệ bằng chứng, chọn biện pháp có thể đảo ngược, đo lại kết quả và báo cáo trung thực phần dữ liệu chưa chắc chắn**. Khả năng quan sát của production chỉ đáng tin khi logging có thể được chẩn đoán và khôi phục mà không làm dịch vụ hoặc dữ liệu bảo mật gặp rủi ro mới.

### Tài liệu tham khảo

- [SLF4J Manual](https://www.slf4j.org/manual.html)
- [Logback — Appenders and AsyncAppender](https://logback.qos.ch/manual/appenders.html)
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html)
- [Log4j2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html)
- [Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Kubernetes — Logging architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
- [Kubernetes — kubectl logs](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/)
- [OpenTelemetry — Collector](https://opentelemetry.io/docs/collector/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
