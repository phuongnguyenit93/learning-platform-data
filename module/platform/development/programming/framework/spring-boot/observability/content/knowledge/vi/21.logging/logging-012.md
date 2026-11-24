# Log retention trong hệ thống Spring Boot

Trong chương **Logging** của module **SPRING_BOOT_OBSERVABILITY**, log retention là chính sách xác định log được giữ trong bao lâu, ở đâu, với mức truy cập nào và được xóa như thế nào khi hết thời hạn. Một hệ thống observability cần giữ đủ log để điều tra lỗi, phân tích sự cố và đáp ứng yêu cầu vận hành; đồng thời phải kiểm soát chi phí lưu trữ, tốc độ truy vấn, dữ liệu cá nhân và nghĩa vụ quản trị dữ liệu.

Log retention không chỉ là cấu hình rolling file trong ứng dụng. Spring Boot có thể ghi log ra console hoặc file, nhưng khi chạy trên container, log thường được runtime/agent thu thập và chuyển tới nền tảng tập trung. **Vòng đời file ở ứng dụng, vòng đời log ở collector và retention trong backend là các lớp riêng biệt.** Cần biết rõ lớp nào đang giữ bản sao dữ liệu và lớp nào chịu trách nhiệm xóa.

Trong **SPRING_BOOT_OBSERVABILITY**, logs kết hợp với Micrometer Observation, metrics và distributed tracing để điều tra lỗi, độ trễ và hành vi ứng dụng. Retention phải cân bằng khả năng tìm kiếm Correlation ID/Trace ID với chi phí và rủi ro lưu dữ liệu nhạy cảm. Giữ log lâu hơn không tự động làm observability tốt hơn nếu log thiếu cấu trúc, không có context hoặc không được quản lý an toàn.

## 1. Log retention giải quyết vấn đề gì?

Một ứng dụng Spring Boot có thể ghi hàng triệu log events mỗi ngày. Nếu giữ không giới hạn, dung lượng và chi phí tăng liên tục; nếu xóa quá sớm, nhóm vận hành không còn dữ liệu để điều tra sự cố phát hiện muộn hoặc đối chiếu xu hướng.

Retention policy trả lời các câu hỏi:

- Log của từng loại sự kiện cần được giữ bao lâu?
- Log nằm trên local disk, volume, object storage hay centralized backend?
- Log nào cần tìm kiếm nhanh, log nào có thể lưu dạng archive rẻ hơn?
- Ai được đọc, export, xóa hoặc giữ lại log?
- Khi hết hạn, dữ liệu bị xóa khỏi index, object store, backup và replica theo cách nào?
- Làm sao chứng minh policy đang được áp dụng và dung lượng vẫn trong budget?

Không nên áp dụng một thời hạn giống nhau cho mọi log. Một dòng debug lặp lại liên tục có giá trị khác với audit event quan trọng, security event hoặc lỗi thanh toán. Phân loại log trước khi chọn retention.

## 2. Phân biệt các lớp lưu trữ log

Một luồng log phổ biến:

```text
Spring Boot application
   |
   +--> console/stdout hoặc rolling file
             |
             v
   Container runtime / node agent
             |
             v
      Log collector / shipper
             |
             v
    Centralized log platform
       |          |          |
       v          v          v
    hot index   warm tier  archive
       |          |          |
       +----------+----------+
                  |
             expiration
                  |
              deletion
```

| Lớp | Trách nhiệm | Ví dụ retention cần quan tâm |
| --- | --- | --- |
| Application file | File log do Logback ghi | Rolling/total size và lịch xóa file cũ |
| Container runtime | Thu nhận stdout/stderr và quản lý file log runtime | Rotation, dung lượng node và giới hạn file |
| Collector/shipper buffer | Đệm log khi backend tạm thời không nhận | Queue capacity, disk buffer và retry |
| Centralized backend | Tìm kiếm, index, dashboard và alert | Index/data stream retention hoặc lifecycle |
| Archive/object storage | Lưu dài hạn với chi phí thấp hơn | Lifecycle expiration và quyền truy cập |
| Backup/replica | Khả năng phục hồi dữ liệu | Retention riêng, xóa lan truyền và chính sách restore |

**Xóa file local không đồng nghĩa log đã bị xóa khỏi backend.** Tương tự, xóa document khỏi index đang hoạt động chưa chắc đã xóa bản archive hoặc backup. Khi thiết kế retention, phải lập bản đồ tất cả bản sao dữ liệu.

## 3. Phân loại log trước khi đặt thời hạn

| Nhóm log | Ví dụ | Giá trị chính | Lưu ý |
| --- | --- | --- | --- |
| Application operational | Request started/completed, dependency timeout | Điều tra vận hành | Có thể có volume cao |
| Error/exception | Lỗi xử lý, lỗi kết nối | RCA và sửa lỗi | Không ghi raw payload/secret |
| Security | Authentication failure, suspicious activity | Phát hiện và điều tra bảo mật | Kiểm soát quyền truy cập chặt |
| Audit/business event | Thay đổi trạng thái quan trọng | Truy vết hoạt động nghiệp vụ | Cần định nghĩa yêu cầu riêng |
| Debug/trace-level application logs | Chi tiết nội bộ | Debug ngắn hạn | Volume lớn, thường tắt ở production |
| Access log | HTTP method, route, status, duration | Phân tích traffic | Tránh raw query string chứa dữ liệu nhạy cảm |

Không tự động coi mọi log có chữ “audit” là audit record đáp ứng yêu cầu pháp lý. Nếu một quy trình cần audit trail có tính toàn vẹn, khả năng kiểm soát chỉnh sửa, định danh actor và thời hạn lưu cụ thể, cần thiết kế một hệ thống audit phù hợp. Log ứng dụng thông thường có thể bị sampling, rotate hoặc drop và không nên được xem là bằng chứng duy nhất.

## 4. Thiết kế retention theo mục đích và mức độ nhạy cảm

Một policy minh họa để bắt đầu thảo luận:

| Phân loại | Ví dụ thời hạn giả định | Lý do |
| --- | ---: | --- |
| Debug chi tiết | 1–3 ngày | Chỉ cần gần thời điểm phát triển/incident |
| Operational logs | 14–30 ngày | Phân tích sự cố và vận hành gần đây |
| Error/security logs | 30–90 ngày | Điều tra sự kiện hiếm và đối chiếu |
| Audit records | Theo policy được phê duyệt riêng | Phụ thuộc nghĩa vụ và quy trình doanh nghiệp |
| Archive ít truy vấn | Theo thỏa thuận lưu trữ | Giảm chi phí khi vẫn cần bảo tồn |

Các con số trên **chỉ là ví dụ kỹ thuật**, không phải khuyến nghị pháp lý hay mặc định phù hợp với mọi tổ chức. Thời hạn thật phải dựa trên mục đích xử lý, hợp đồng, yêu cầu pháp luật áp dụng, điều tra sự cố, chi phí và quyết định của chủ sở hữu dữ liệu.

Nên định nghĩa policy theo thuộc tính ổn định như service, environment, log category, data classification và retention class. Tránh đặt policy theo raw Correlation ID hoặc user ID vì sẽ tạo quá nhiều nhóm và khó vận hành.

### Tách production và non-production

Log dev/test thường có thể giữ ngắn hơn và được phép có verbosity cao hơn trong môi trường cô lập. Production nên ghi mức log và fields đã kiểm soát; bật DEBUG tạm thời cần có thời hạn, phạm vi hẹp và cơ chế tắt tự động. Không đưa log production nhạy cảm sang môi trường dev để kéo dài retention mà không có cơ chế mask/ủy quyền phù hợp.

## 5. Rolling file trong Logback không phải centralized retention

Spring Boot mặc định thường ghi log ra console nếu không cấu hình file logging. Có thể đặt:

```yaml
logging:
  file:
    name: /var/log/orders-service/application.log
  logback:
    rollingpolicy:
      max-file-size: 100MB
      max-history: 7
      total-size-cap: 2GB
```

Ví dụ minh họa cấu hình logging file và rolling policy trong những phiên bản Spring Boot hỗ trợ các property tương ứng. Cần kiểm tra property metadata của version đang dùng. Các giá trị `max-history`, `total-size-cap` và hành vi rolling phụ thuộc loại rolling policy và cách cấu hình thực tế.

Ý nghĩa:

- `logging.file.name` chỉ định file log đích.
- `max-file-size` giới hạn kích thước file trước khi roll.
- `max-history` giới hạn số kỳ/file lịch sử theo rolling policy tương ứng.
- `total-size-cap` giới hạn tổng dung lượng file archive được giữ khi policy hỗ trợ.

Rolling file giúp giới hạn disk local, nhưng không kiểm soát log đã được ship tới Loki, Elasticsearch/OpenSearch, Splunk hoặc backend khác. Collector có thể đã đọc và gửi dữ liệu trước khi file local bị xóa.

**Không dùng rolling file thay cho archive tập trung** nếu yêu cầu cần tìm kiếm liên service hoặc bảo tồn log dài hạn. Local disk thường dễ mất khi pod/node bị thay thế.

### Ví dụ Logback rolling policy trực tiếp

Nếu cần cấu hình Logback cụ thể, có thể dùng `SizeAndTimeBasedRollingPolicy`:

```xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/var/log/orders-service/application.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>
                /var/log/orders-service/archive/application.%d{yyyy-MM-dd}.%i.log.gz
            </fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>2GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Ví dụ cần được điều chỉnh theo version Logback mà Spring Boot BOM quản lý. Không đồng thời cấu hình rolling cho cùng một file trong nhiều appender hoặc vừa tự cấu hình `logback-spring.xml` vừa kỳ vọng mọi property mặc định được áp dụng y hệt. Chọn một nguồn cấu hình rõ ràng và kiểm tra file archive thực tế.

## 6. Log stdout trong container và Kubernetes

Trong containerized deployment, pattern phổ biến là ứng dụng ghi log ra stdout/stderr ở định dạng một event mỗi dòng; runtime hoặc node agent chịu trách nhiệm thu nhận và chuyển tới hệ thống tập trung.

Ưu điểm:

- Ứng dụng không phải tự quản lý file log bền vững trên container filesystem.
- Nền tảng có thể thu gom log đồng nhất từ nhiều service.
- Pod có thể được thay thế mà log đã ship vẫn tồn tại trong backend.
- Resource metadata như namespace, pod, container và node có thể được collector bổ sung.

Tuy nhiên, stdout không tự đảm bảo giữ log vô hạn. Container runtime có thể rotate file, giới hạn dung lượng node hoặc xóa log khi pod/node bị thu hồi. Cần kiểm tra retention/rotation của runtime và shipper, disk pressure, buffering và backend policy.

Tránh ghi đồng thời cùng nội dung ra stdout và rolling file nếu cả hai đều được agent thu gom; điều đó có thể tạo duplicate logs. Nếu cần file audit riêng, xác định rõ collector nào đọc file đó và cách tránh ingest lặp với stdout.

## 7. Retention trong centralized backend

Nền tảng log tập trung thường cung cấp index lifecycle, data stream lifecycle, retention policy, log bucket hoặc object lifecycle. Tên tính năng khác nhau nhưng các bước khái niệm tương tự:

1. Gắn classification/retention class khi ingest hoặc route dữ liệu.
2. Lưu log mới ở tier tối ưu cho tìm kiếm nhanh.
3. Chuyển dữ liệu ít truy vấn sang tier rẻ hơn nếu backend hỗ trợ.
4. Xóa dữ liệu khi vượt thời hạn policy.
5. Kiểm tra replica, snapshot, archive và backup có thời hạn riêng hay không.

```text
Ngày 0–7       Hot: tìm kiếm thường xuyên, latency thấp
Ngày 8–30      Warm: ít truy vấn, chi phí thấp hơn
Ngày 31–90     Archive: truy xuất chậm hơn, lưu dài hạn
Sau ngày 90    Expire: xóa theo policy đã phê duyệt
```

Đây chỉ là mô hình tiering minh họa; không phải mọi backend có đủ hot/warm/cold tier và thời gian chuyển tier có thể khác retention. Cần kiểm tra semantics của nền tảng đang triển khai, bao gồm thời điểm policy chạy, timezone, index rollover, late-arriving logs và cách xử lý dữ liệu được ingest trễ.

### Retention theo index/data stream

Nếu backend tổ chức dữ liệu theo index hoặc data stream, policy có thể gắn với nhóm log theo service/environment/classification. Cần tránh tạo một index cho từng request hoặc từng Correlation ID. Phân vùng quá nhỏ làm tăng chi phí shard, metadata và quản trị.

Khi thay policy, cần xác định policy áp dụng cho dữ liệu mới, dữ liệu cũ hay cả hai. Chỉnh retention setting có thể chỉ ảnh hưởng index/data stream được gắn lifecycle policy; index cũ không tự động được cập nhật nếu chưa attach policy.

## 8. Ước lượng dung lượng và chi phí

Một phép tính sơ bộ:

\[
\text{Raw log volume/day} =
\text{Events/second} \times
\text{Average bytes/event} \times 86.400
\]

Ví dụ một service ghi trung bình 200 log events/giây, mỗi event khoảng 1 KB:

\[
200 \times 1\text{ KB} \times 86.400
= 17.280.000\text{ KB/day}
\]

Tương đương khoảng 17,28 GB/ngày theo đơn vị thập phân, trước compression, index overhead và replication. Nếu giữ 30 ngày, raw volume xấp xỉ 518,4 GB cho service này trong điều kiện tải không đổi.

Đây không phải dung lượng disk cuối cùng. Backend có thể nén tốt hơn hoặc kém hơn tùy độ lặp dữ liệu; index, inverted index, replicas, shard overhead, metadata và backup làm tổng dung lượng thay đổi.

### Các biến ảnh hưởng chi phí

- Số events/giây và kích thước event trung bình/p95.
- Tỷ lệ DEBUG/INFO/WARN/ERROR và log duplication.
- Compression ratio và index overhead.
- Số replicas, shard count và storage tier.
- Retention duration, snapshot và backup policy.
- Ingest, query, egress và archive retrieval charges.

Nên đo log bytes/day theo service, environment và category. Dùng số liệu thực tế nhiều ngày có traffic bình thường, peak và incident; một ngày ít tải không đại diện cho ngân sách tháng.

## 9. Sampling và retention là hai policy khác nhau

Log sampling quyết định **log event nào được phát ra/ingest**. Retention quyết định **log đã lưu được giữ bao lâu**. Hai việc không thay thế nhau.

| Cơ chế | Câu hỏi |
| --- | --- |
| Log level | Ứng dụng có tạo log event ở mức này không? |
| Log sampling/rate limiting | Trong các event đủ điều kiện, event nào được giữ? |
| Collector filtering | Event nào được nhận, enrich, redact hoặc route? |
| Retention | Event đã lưu còn tồn tại tới thời điểm nào? |
| Archive lifecycle | Khi nào dữ liệu được chuyển tier hoặc xóa? |

Ví dụ, giảm INFO log sampling 50% có thể giảm ingest volume nhưng vẫn phải giữ ERROR logs theo policy. Giữ ERROR logs 90 ngày không đảm bảo mọi lỗi đã được ghi hoặc collector không drop. Cần theo dõi dropped events, logging level, sampling rules và storage expiration độc lập.

Đối với tracing, Trace ID/Span ID trong log giúp liên kết với trace nếu trace được sampled và export thành công. Nếu trace bị loại bởi sampling, log vẫn có thể được giữ theo log policy. Không suy ra retention log từ retention trace hoặc ngược lại.

## 10. Correlation ID, Trace ID và dữ liệu nhạy cảm

| Field | Giá trị với điều tra | Rủi ro/cách dùng |
| --- | --- | --- |
| Correlation ID | Tìm log cùng request/workflow | Giữ làm structured field, không làm metric label |
| Trace ID/Span ID | Mở trace và xác định thao tác | Có thể xuất hiện dù trace bị sampled out |
| User/customer ID | Liên hệ nghiệp vụ | Cần pseudonymize hoặc hạn chế quyền truy cập theo policy |
| Session/token/cookie | Có thể nhạy cảm cao | Không log credentials hoặc secrets |
| Raw URL/query | Hữu ích tìm endpoint | Có thể chứa token, email hoặc dữ liệu cá nhân |
| Request/response body | Hữu ích debug một số tình huống | Thường cần tránh hoặc redact/allowlist nghiêm ngặt |

Retention càng dài thì thời gian một bản log nhạy cảm có thể tồn tại càng lâu. Vì vậy, **lọc/redact tại nguồn hoặc collector trước khi lưu** thường an toàn hơn chỉ dựa vào việc xóa khi hết hạn.

Không ghi password, access token, refresh token, cookie, API key, authorization header hoặc dữ liệu thanh toán nhạy cảm vào log. Với trường hợp cần giữ một định danh, dùng dạng pseudonymized/hashed theo thiết kế bảo mật được phê duyệt; hash không mặc nhiên làm dữ liệu vô danh nếu không gian giá trị nhỏ hoặc có thể đối chiếu.

## 11. Legal hold, backup và yêu cầu xóa dữ liệu

Một số sự kiện có thể đang thuộc phạm vi điều tra hoặc yêu cầu bảo tồn dữ liệu được phê duyệt. Trong trường hợp đó, quy trình legal hold hoặc incident hold có thể tạm dừng việc xóa một tập log xác định.

Quy trình nên:

- Xác định owner có quyền phê duyệt hold.
- Giới hạn phạm vi theo dataset, service, thời gian và mục đích.
- Ghi audit event cho thao tác tạo, gia hạn và kết thúc hold.
- Đặt thời hạn review để tránh hold vô thời hạn.
- Khi hold kết thúc, đưa dữ liệu trở lại lifecycle policy.

Backup và snapshot có thể lưu bản sao lâu hơn index đang hoạt động. Nếu có yêu cầu xóa, phải hiểu cách backend/backup thực hiện deletion, expiration và restore. Một bản backup cũ được restore có thể đưa dữ liệu hết hạn trở lại hệ thống; cần quy trình re-apply deletion/retention sau restore.

Không tự ý giữ log lâu hơn policy vì “có thể cần sau này”. Cũng không xóa dữ liệu đang thuộc hold đã được phê duyệt. Thời hạn, hold và deletion phải do data owner/legal/security theo thẩm quyền xác định.

## 12. Bảo vệ truy cập và tính toàn vẹn của log

Retention không chỉ là thời hạn. Log vẫn có thể bị đọc hoặc sửa bởi người không phù hợp nếu quyền truy cập không chặt.

Một mô hình kiểm soát:

- Application team chỉ truy cập dataset/service cần cho nhiệm vụ.
- Security team có quyền mở rộng theo quy trình sự cố.
- Production log access có audit trail.
- Export/download bị giới hạn và có mục đích.
- Sensitive fields được redact trước hoặc trong ingest.
- Audit records quan trọng có kiểm soát chỉnh sửa/immutability riêng.
- Secret dùng để export log được quản lý như credential và rotate.

Nếu yêu cầu forensic/integrity, cần đánh giá immutability, checksum/signature, access audit, clock synchronization và chain of custody. Một file log text thường không tự bảo đảm những thuộc tính này.

## 13. Triển khai và vận hành trong Spring Boot

### 13.1 Chọn output phù hợp nền tảng

- Local development: console hoặc file để dễ xem.
- VM/bare metal: console/agent hoặc rolling file có disk budget.
- Container/Kubernetes: stdout structured logs thường dễ tích hợp với node agent/collector.
- Audit pipeline đặc thù: tách luồng và storage theo yêu cầu đã phê duyệt.

Không tạo file lớn trên ephemeral container filesystem rồi kỳ vọng file còn sau khi pod bị reschedule. Nếu buộc dùng file, xác định volume persistence, permissions, rotation, collector file tailing và disk-pressure behavior.

### 13.2 Dùng structured logging

JSON log giúp backend filter chính xác theo field thay vì parse chuỗi message. Một event minh họa:

```json
{
  "timestamp": "2026-11-22T10:15:02.120Z",
  "level": "ERROR",
  "service.name": "orders-service",
  "environment": "production",
  "correlationId": "req-7f31c8a2",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "event": "payment.authorization.failed",
  "error.type": "TimeoutException",
  "message": "Payment provider timed out"
}
```

Đây là schema minh họa. Tên field nên theo convention đã chọn; không để cùng một loại dữ liệu lúc thì `traceId`, lúc thì `trace_id`, lúc thì nested field tùy service. Đồng nhất schema giúp retention routing và query ổn định.

### 13.3 Theo dõi collector buffer và shipper

Khi backend gián đoạn, shipper có thể giữ buffer trên memory hoặc disk. Cần xác định:

- Buffer capacity và thời gian có thể chịu outage.
- Khi đầy, shipper drop event cũ hay mới, block ứng dụng hay báo lỗi?
- File rotation có thể xóa file trước khi shipper đọc hết không?
- Retry có tạo duplicate không?
- Sau restart, cursor/offset được phục hồi thế nào?

Không để collector chặn request nghiệp vụ vô hạn chỉ vì log backend đang chậm. Logging thường cần fail-safe policy có giới hạn; lựa chọn drop, buffer hoặc backpressure phụ thuộc loại log và yêu cầu đã thống nhất.

## 14. Quy trình đặt và kiểm tra retention policy

1. **Inventory:** liệt kê nguồn log, service, format, destinations, replicas và archive.
2. **Classify:** phân loại operational, error, security, audit, debug và dữ liệu nhạy cảm.
3. **Assign owner:** mỗi dataset có owner chịu trách nhiệm nội dung, quyền truy cập và thời hạn.
4. **Estimate volume:** đo events/day, bytes/event, compression, replicas và growth.
5. **Define policy:** thời hạn hot/warm/archive/expiry và ngoại lệ được phê duyệt.
6. **Configure layers:** rolling file/runtime rotation, collector buffer, backend lifecycle, backup deletion.
7. **Validate expiration:** tạo dữ liệu test có timestamp phù hợp, xác minh đúng lớp xóa theo policy.
8. **Monitor:** theo dõi storage, ingest, oldest retained event, expired data và policy errors.
9. **Review:** rà soát theo thay đổi traffic, incident, nghiệp vụ và yêu cầu quản trị dữ liệu.

### Các chỉ số vận hành nên theo dõi

| Chỉ số | Mục đích |
| --- | --- |
| Log ingest bytes/second và bytes/day | Ước lượng tăng trưởng dung lượng |
| Events/second theo service/level | Tìm nguồn log volume cao |
| Collector queue/buffer utilization | Phát hiện nguy cơ drop |
| Dropped/rejected log records | Đo mất dữ liệu |
| Storage used và forecast | Kiểm soát ngân sách |
| Oldest/newest event timestamps | Nhận biết ingest lag và retention thực |
| Expiration/deletion job failures | Kiểm chứng policy được áp dụng |
| Unauthorized log access/download | Theo dõi bảo mật dữ liệu |

## 15. Bài tập tình huống

Một cụm Spring Boot ghi trung bình 800 log events/giây, mỗi event có kích thước khoảng 1,2 KB. Hệ thống hiện lưu log 30 ngày trên hot storage. Backend bắt đầu vượt ngân sách; team đề xuất giảm retention xuống 7 ngày và xóa toàn bộ file local mỗi đêm.

**Câu hỏi:**

1. Raw log volume mỗi ngày ước lượng bao nhiêu?
2. Vì sao xóa file local không đảm bảo centralized backend chỉ giữ 7 ngày?
3. Cần phân loại log nào trước khi rút retention chung?
4. Những lớp dữ liệu nào cần kiểm tra để bảo đảm expiration thật sự xảy ra?
5. Có thể giảm chi phí mà vẫn giữ dữ liệu cần điều tra bằng cách nào?

**Gợi ý phân tích:**

- Raw volume: 800 × 1,2 KB × 86.400 = 82.944.000 KB/ngày, tương đương khoảng 82,94 GB/ngày theo đơn vị thập phân, chưa tính compression/index/replica.
- File local và centralized backend có lifecycle riêng; collector có thể đã ship log đi trước khi file bị xóa. Backend retention cần được cấu hình riêng.
- Tách debug/operational/error/security/audit; audit có thể có policy riêng được phê duyệt. Không giảm toàn bộ theo một tỷ lệ nếu nhu cầu khác nhau.
- Kiểm tra application rolling files, runtime container logs, collector buffers, backend index/data stream, archive, snapshots và backups.
- Giảm verbose/duplicate logs, chuẩn hóa structured fields, redact dữ liệu, tier hot/warm/archive và chọn retention theo mục đích; không chỉ xóa ngẫu nhiên.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Log lifecycle | Biết file local, runtime, collector, backend và backup là các lớp riêng |
| Classification | Tách operational, error, security, audit và debug |
| Rolling file | Phân biệt rotation với centralized retention |
| Container logs | Hiểu stdout, runtime rotation và node disk limits |
| Backend lifecycle | Biết hot/warm/archive/expiration |
| Capacity planning | Tính bytes/day và ảnh hưởng compression/replica/index |
| Sampling vs retention | Phân biệt event được ghi với thời gian lưu event |
| Correlation fields | Dùng Correlation ID/Trace ID để tìm log, không làm metric labels |
| Privacy/security | Redact secrets, hạn chế quyền truy cập và export |
| Backup/legal hold | Có policy cho hold, deletion và restore |
| Verification | Theo dõi ingest, drop, oldest event và deletion failures |

**Ghi nhớ:** Log retention xác định log được lưu ở đâu, giữ bao lâu, ai có quyền truy cập và khi nào dữ liệu phải hết hạn. Rolling file của Logback, container runtime rotation, collector buffers, centralized backend lifecycle và backup retention là các lớp độc lập. Hãy phân loại log theo mục đích, đo dung lượng, cấu hình expiration ở từng nơi có bản sao, bảo vệ dữ liệu nhạy cảm và xác minh deletion thực tế. Kết hợp metrics, logs có cấu trúc, Correlation ID và trace context giúp điều tra hiệu quả mà vẫn kiểm soát chi phí và vòng đời dữ liệu.
