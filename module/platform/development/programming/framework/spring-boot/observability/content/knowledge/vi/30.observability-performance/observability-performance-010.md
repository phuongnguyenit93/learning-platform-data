# Log volume budget cho Spring Boot

## 1. Mục tiêu và bối cảnh

Logs giúp điều tra lỗi và hiểu hành vi hệ thống, nhưng mỗi log event đều có chi phí: CPU để tạo/serialize, I/O để ghi, network để chuyển tiếp, storage để index và thời gian để người vận hành tìm kiếm. Khi traffic tăng hoặc một lỗi lặp lại hàng nghìn lần mỗi giây, logging không có giới hạn có thể làm tăng chi phí, gây nghẽn pipeline và thậm chí làm ứng dụng chậm hơn.

**Log volume budget** là ngân sách có thể đo và quản lý cho lượng log được tạo, chuyển tiếp và lưu trữ trong một khoảng thời gian. Ngân sách cần gắn với mục tiêu vận hành: giữ đủ sự kiện quan trọng để điều tra, đồng thời kiểm soát bytes, event rate, retention và chi phí.

Bài thuộc chương **Hiệu năng observability** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể:
1. Ước tính log volume từ event rate và kích thước trung bình.
2. Phân bổ budget theo service, environment, severity và loại event.
3. Giảm log noise bằng sampling, aggregation và deduplication.
4. Giữ lại error, security và audit events theo yêu cầu.
5. Thiết kế structured logging với field ổn định và cardinality có kiểm soát.
6. Đặt retention, ingestion và storage targets.
7. Đo overhead và kiểm thử logging dưới tải.

**Baseline:** Spring Boot 3.5.x, Java 17+, SLF4J/Logback và log collector tập trung. Các con số minh họa; budget thực tế phụ thuộc backend, index strategy, compression và yêu cầu lưu trữ.

## 2. Log volume gồm những gì?

Không chỉ số dòng log quyết định chi phí. Cần phân biệt:

| Đại lượng | Ý nghĩa | Đơn vị thường dùng |
| --- | --- | --- |
| Event rate | Số log events được tạo | events/second (EPS) |
| Average event size | Kích thước trung bình mỗi event sau serialize | bytes/event |
| Ingest volume | Dữ liệu đi vào collector/backend | MB/GB mỗi ngày |
| Indexed volume | Dữ liệu sau parse/index | GB mỗi ngày |
| Retained volume | Dữ liệu đang được giữ | GB/TB |
| Query volume | Dữ liệu được đọc khi tìm kiếm/alert | bytes scanned |

JSON logs có thể lớn hơn pattern text vì lặp field names và metadata. Compression giảm kích thước truyền/lưu, nhưng không nhất thiết giảm chi phí indexing hoặc query theo cùng tỷ lệ.

## 3. Tính ngân sách cơ bản

Công thức gần đúng:

```text
raw_bytes_per_day = events_per_second
                    × average_event_bytes
                    × 86,400

ingest_GB_per_day = raw_bytes_per_day / 1,000,000,000
```

Ví dụ service tạo trung bình 250 events/second, mỗi event 900 bytes:

```text
250 × 900 × 86,400 = 19,440,000,000 bytes/day
                    ≈ 19.44 GB/day (decimal)
```

Đây là volume raw trước compression, replication và index overhead. Nếu backend giữ 14 ngày, raw retained volume xấp xỉ 272.16 GB cho service này, chưa tính replicas/indexes.

Để lập kế hoạch capacity, tính thêm:
- Peak EPS, không chỉ average EPS.
- Burst duration và số replicas của service.
- JSON field growth theo release.
- Compression ratio thực đo.
- Replication factor và index overhead.
- Retention theo tier/severity.
- Retry/replay khi collector hoặc backend gián đoạn.

### 3.1. Budget phải có đơn vị và phạm vi

Một budget hữu ích nói rõ:
- Scope: service, cluster, environment hoặc tenant tier.
- Window: phút, giờ, ngày hoặc tháng.
- Limit: EPS, bytes/day hoặc bytes/month.
- Alert threshold: mức cảnh báo trước khi chạm limit.
- Owner: đội chịu trách nhiệm.
- Exception policy: log nào không được drop.

Ví dụ budget mẫu:

| Scope | Target minh họa | Alert |
| --- | ---: | ---: |
| Một service production | 20 GB/day raw | 80% budget |
| Error events | Không drop có chủ đích | Bất kỳ drop nào |
| Debug logs production | Chỉ bật có thời hạn | Khi vượt allowlist |
| Security/audit events | Theo retention policy riêng | Delivery failure |

Không áp một con số chung cho mọi service. API gateway, batch processor và low-traffic admin service có profile log khác nhau.

## 4. Phân bổ budget theo severity và event class

Không phải mọi log event có giá trị như nhau. Một policy có thể chia:

| Class | Ví dụ | Chính sách |
| --- | --- | --- |
| ERROR | Request thất bại, dependency unavailable | Giữ event; deduplicate/rate-limit alert khi cần nhưng bảo toàn evidence |
| WARN | Retry, fallback, degraded mode | Giữ theo event semantics; aggregate lỗi lặp |
| INFO | Business lifecycle milestones | Chọn event có giá trị vận hành, tránh log từng bước nhỏ |
| DEBUG/TRACE | Payload diagnostics, internal state | Tắt mặc định ở production; bật có scope/expiry |
| SECURITY/AUDIT | Login failure, privilege change, data access audit | Theo policy bảo mật/audit, không drop tùy tiện |

Severity không phải tiêu chí duy nhất. Một INFO event có thể là audit record bắt buộc; một ERROR lặp hàng triệu lần có thể cần aggregation để không làm nghẽn pipeline, nhưng phải giữ counter/summary và đại diện sự kiện.

## 5. Đo volume thực tế

Đừng chỉ ước tính từ source code. Đo ở ít nhất hai điểm: application process và collector/backend.

Các số liệu cần thu:
- EPS theo service, environment, severity và logger.
- Bytes/second trước và sau compression.
- Top logger/event names theo volume.
- Tỷ lệ duplicate/repeated messages.
- Drop count, queue depth và exporter retry.
- CPU time và allocation dành cho logging.
- Backend ingest/index latency và storage growth.

Structured log schema giúp group theo event name thay vì parse message text. Ví dụ event field `event.name=payment.authorization.failed` ổn định hơn việc group theo message có chứa order ID.

## 6. Structured logging để giảm noise

Log event nên có field ổn định, message ngắn và context hữu ích:

```json
{
  "timestamp": "2026-11-22T10:15:30Z",
  "level": "WARN",
  "service": "order-service",
  "environment": "production",
  "event.name": "order.retry.scheduled",
  "dependency": "inventory",
  "attempt": 2,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Inventory request will be retried"
}
```

Đây là schema minh họa. Tránh đưa request body, credentials, raw SQL parameters hoặc personal data vào event. Dùng traceId/spanId để chuyển sang trace khi cần, thay vì lặp toàn bộ execution detail trong mọi log line.

### 6.1. Dùng event code ổn định

Ưu tiên event name/code có vocabulary hữu hạn:
- `payment.authorization.started`
- `payment.authorization.failed`
- `inventory.lookup.timeout`
- `order.retry.scheduled`

Không đưa ID vào event name hoặc logger name. Message có thể mô tả ngữ cảnh, nhưng query/dashboard nên dựa trên field ổn định.

## 7. Sampling, aggregation và deduplication

Ba kỹ thuật này giải quyết các vấn đề khác nhau:

| Kỹ thuật | Tác dụng | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Sampling | Chỉ giữ một tỷ lệ events thuộc nhóm cho phép sample | Có thể bỏ mất một sự kiện hiếm nhưng quan trọng |
| Aggregation | Gộp nhiều lần lặp thành summary/count/window | Mất chi tiết từng occurrence |
| Deduplication | Loại bản ghi trùng do retry/duplicate delivery | Có thể nhầm hai event hợp lệ giống nhau |

### 7.1. Sampling cho log thông thường

Sampling phù hợp hơn với high-volume diagnostic events như successful polling hoặc repetitive debug messages. Ví dụ giữ 1% thành công nhưng giữ lỗi theo policy:

```java
if (random.nextDouble() < 0.01) {
    log.debug("Cache refresh completed");
}
```

Đây chỉ là minh họa. Trong production, sampling nên deterministic theo request/trace key khi cần giữ các log liên quan cùng một operation; tránh random sampling độc lập từng dòng khiến một trace có log rời rạc khó điều tra.

Không sample security/audit records hoặc events bắt buộc theo compliance. Error logs cũng cần policy rõ: giữ một số representative events, aggregate repeated failures và phát metric/counter cho tổng số lần xảy ra.

### 7.2. Aggregation cho lỗi lặp

Thay vì ghi stack trace đầy đủ cho mọi lần cùng một lỗi, có thể:
1. Ghi một event đầu tiên với exception class và dependency.
2. Tăng counter cho mọi occurrence.
3. Gom số lần lặp theo time window và error fingerprint an toàn.
4. Ghi summary định kỳ, ví dụ `failure_count=1842` trong 1 phút.
5. Vẫn giữ một số mẫu đại diện và các transition quan trọng.

Fingerprint không được chứa raw message/PII; dùng exception class, operation code và error category đã chuẩn hóa.

## 8. Không dùng log sampling thay cho metrics

Nếu mục tiêu là biết chính xác số lần xảy ra, hãy dùng counter/metrics. Log sampling làm mất event-level detail theo chủ đích, do đó số log còn lại không đại diện cho tổng count nếu không ghi sampling rate/weight.

Ví dụ:
- Metrics counter đếm tất cả retry attempts.
- Logs giữ một mẫu retry thành công và mọi transition bất thường theo policy.
- Traces sample theo trace-level policy.

Không cộng số sampled log lines rồi coi đó là tổng số lỗi. Nếu cần ước tính, phải biết sampling probability và chấp nhận sai số; với operational counts, metrics thường phù hợp hơn.

## 9. Spring Boot và Logback

Spring Boot mặc định dùng Logback khi dùng logging starter. Có thể cấu hình log levels theo package:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
    com.example.orders.diagnostics: WARN
```

Đặt DEBUG/TRACE ở production chỉ trong scope nhỏ và có thời hạn. Khi dùng structured logging, chọn encoder/schema nhất quán; không log cùng event ở controller, service và global exception handler.

Ví dụ tránh log lặp:

```java
public Order submit(OrderCommand command) {
    // Business method propagates exception to the HTTP boundary.
    return orderRepository.save(map(command));
}
```

Global boundary có thể ghi một event failure với trace context và exception phù hợp policy. Các layer dưới chỉ bổ sung log khi có thông tin riêng cần thiết, không ghi cùng stack trace rồi rethrow.

### 9.1. Async logging

Async appender giảm blocking I/O ở application thread nhưng có queue hữu hạn. Khi queue đầy, logging framework có thể block hoặc drop events tùy cấu hình. Cần:
- Theo dõi queue depth và dropped-event counters.
- Chọn queue size theo burst và memory budget.
- Xác định behavior khi queue đầy: block, drop low-priority hoặc fallback.
- Không giả định async logging đảm bảo delivery.
- Test shutdown/flush và collector outage.

## 10. Retention và storage tiers

Log volume budget liên quan trực tiếp retention. Giữ mọi event cùng thời gian và cùng mức index thường không cần thiết.

Ví dụ phân tầng:

| Tier | Dữ liệu | Retention minh họa |
| --- | --- | ---: |
| Hot | Error, recent operational logs cần search nhanh | 7 ngày |
| Warm | Operational logs đã giảm index/chi phí | 30 ngày |
| Cold/archive | Audit/security records theo policy | Theo yêu cầu tổ chức |

Đây chỉ là ví dụ; retention phải theo pháp lý, hợp đồng, security policy và mục đích xử lý dữ liệu. Không rút ngắn audit retention chỉ để giảm chi phí.

Giảm chi phí có thể thực hiện bằng:
- Loại bỏ field không cần index.
- Giảm cardinality và số lượng dynamic fields.
- Nén trước khi lưu archive.
- Dùng index lifecycle/data tiering.
- Áp dụng retention khác nhau theo event class.
- Xóa dữ liệu hết hạn ở replicas và backup theo quy trình.

## 11. Ước tính budget với peak traffic

Giả sử service có 6 replicas, mỗi replica tạo trung bình 40 EPS, peak 3 lần average, event size trung bình 700 bytes.

```text
average EPS = 6 × 40 = 240
peak EPS    = 240 × 3 = 720
raw GB/day  = 240 × 700 × 86,400 / 1,000,000,000
            ≈ 14.52 GB/day
```

Capacity collector cần chịu peak gần 720 EPS hoặc 504 KB/s raw trong ví dụ này. Nếu burst kéo dài, queue chỉ trì hoãn việc chạm backend capacity; nó không loại bỏ volume.

Budget nên có headroom cho deployment rollout, incident bursts và debug windows. Không lập capacity đúng bằng average.

## 12. Alerting và budget enforcement

Thiết lập cảnh báo khi:
- Ingest bytes đạt 70-80% budget.
- EPS vượt baseline trong nhiều window.
- Async queue/drop count tăng.
- Collector exporter retry hoặc backend ingest lag tăng.
- Error log rate tăng đột biến.
- Retention/storage forecast vượt capacity.

Enforcement có thể giảm DEBUG/INFO noisy events trước, nhưng không drop audit/security events hoặc các error transitions quan trọng mà không có policy được duyệt.

Trong incident, có thể mở diagnostics tạm thời theo runbook: scope service/endpoint, severity, thời hạn, owner, data classification và kế hoạch tắt. Sau incident, xác nhận log level trở lại baseline.

## 13. Kiểm thử logging dưới tải

Test nên đo cả correctness và overhead:
1. Tạo traffic representative với success, errors, retries và burst.
2. Đo EPS và bytes/event ở baseline.
3. So sánh CPU, allocation, GC và request latency khi bật structured logging.
4. Giả lập collector chậm/mất kết nối để kiểm tra queue/drop behavior.
5. Xác nhận error/audit events được giữ theo policy.
6. Kiểm tra sampling rate và event counts không bị hiểu nhầm.
7. Kiểm tra không có PII/secrets trong logs.
8. Kiểm tra shutdown flush và recovery sau outage.

Không dùng một benchmark chỉ có message ngắn để đại diện cho production JSON logs có stack traces và MDC fields.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ingest tăng đột biến | Retry loop hoặc error lặp tạo nhiều stack traces | Aggregate/deduplicate và giữ counter tổng |
| Storage tăng dù EPS ổn định | Event size tăng, thêm fields hoặc stack trace dài | Phân tích bytes/event và schema diff |
| Request latency tăng khi logging bật | Synchronous I/O, serialization hoặc appender block | Đo logging overhead và cấu hình async có queue policy |
| Log bị mất khi backend chậm | Async queue đầy hoặc exporter drop | Theo dõi drop counters, queue và retry policy |
| Search tốn kém | Quá nhiều fields được index hoặc cardinality cao | Chọn field index, normalize values |
| Debug không đủ dữ liệu | Sampling quá mạnh hoặc không giữ representative events | Điều chỉnh policy và liên kết metrics/traces |
| Tổng error count không khớp log count | Logs sampled/aggregated | Dùng metrics counter làm nguồn đếm |
| Một lỗi xuất hiện nhiều lần ở các layer | Nhiều layer log rồi rethrow | Chọn một logging boundary |
| Budget bị vượt vào giờ cao điểm | Chỉ tính average, bỏ qua peak/replica count | Capacity theo peak và headroom |
| Audit events biến mất | Áp sampling/drop chung cho mọi severity | Tách audit pipeline và retention policy |
| Debug level còn bật sau incident | Không có expiry/owner cho temporary config | Tự động hóa runbook và xác minh baseline |

## 15. Checklist production

- [ ] Budget có scope, unit, time window, owner và alert threshold.
- [ ] Ước tính cả average và peak EPS/bytes.
- [ ] Structured log schema có event names ổn định.
- [ ] Không log secrets, PII hoặc request body không cần thiết.
- [ ] Sampling chỉ áp dụng cho event classes được phép.
- [ ] Error/security/audit events có policy bảo toàn riêng.
- [ ] Metrics counter là nguồn đếm chính xác cho operational totals.
- [ ] Aggregation/dedup giữ summary và representative evidence.
- [ ] Async queue, drop count và exporter retry được giám sát.
- [ ] Retention/index/storage tier phù hợp data policy.
- [ ] Temporary DEBUG/TRACE có owner, scope và expiry.
- [ ] Load test bao gồm burst và collector outage.

## 16. Câu hỏi tự luyện

1. Log volume budget khác giới hạn số dòng log thế nào?
2. Tính raw GB/day từ EPS và average event size ra sao?
3. Vì sao cần capacity theo peak thay vì average?
4. Sampling, aggregation và deduplication giải quyết vấn đề gì?
5. Vì sao không nên sample security/audit events tùy tiện?
6. Vì sao metrics counter phù hợp hơn sampled logs để đếm tổng lỗi?
7. Async appender có thể drop logs khi nào?
8. Event name ổn định giúp giảm query noise ra sao?
9. Retention tiers ảnh hưởng chi phí và điều tra thế nào?
10. Những chỉ số nào cần alert để phát hiện budget breach?
11. Vì sao cần test collector outage và shutdown flush?
12. Làm thế nào mở DEBUG tạm thời mà không để quên trong production?

## Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Logback — Configuration](https://logback.qos.ch/manual/configuration.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

