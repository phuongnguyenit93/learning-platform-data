# Log sampling: kiểm soát log volume mà vẫn giữ tín hiệu vận hành

> **Chương:** Logging  
> **Bài:** Log sampling  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần log sampling?

Một ứng dụng Spring Boot có thể ghi log cho mỗi HTTP request, mỗi lần gọi dependency, mỗi lần retry và nhiều bước nghiệp vụ. Khi traffic tăng, số lượng log records, dung lượng truyền và chi phí lưu trữ có thể tăng rất nhanh. Một endpoint nhận vài nghìn request mỗi giây, nếu ghi nhiều dòng INFO/DEBUG trên mỗi request, có thể tạo lượng log rất lớn dù không có lỗi.

**Log sampling** là cách chọn một phần log records hoặc một phần sự kiện đủ điều kiện để ghi/xuất, dựa trên policy có chủ đích. Mục tiêu là giảm log volume và chi phí xử lý nhưng vẫn giữ dữ liệu cần thiết để theo dõi sức khỏe hệ thống và điều tra sự cố.

Log sampling cần được thiết kế theo loại log và mục đích:

- Log debug/verbose lặp lại có thể được lấy mẫu mạnh hơn.
- Log thành công tần suất cao có thể chỉ giữ một tỷ lệ hoặc summary.
- Log cảnh báo có thể cần giữ phần lớn hoặc toàn bộ tùy semantics.
- Log lỗi cần được bảo vệ khỏi việc bị loại một cách vô tình.
- Security/audit events có yêu cầu riêng, thường không được áp dụng sampling làm mất sự kiện bắt buộc.

~~~mermaid
flowchart TD
  A["Application emits log event"] --> B["Classify event"]
  B --> C{"Policy"}
  C -->|"Routine / high volume"| D["Sampling / rate limit"]
  C -->|"Error / security / audit"| E["Protected path"]
  D --> F["Selected log records"]
  D --> G["Dropped / counted records"]
  E --> F
  F --> H["Appender / agent / collector"]
  H --> I["Log backend"]
  G --> J["Drop counters / sampling metrics"]
~~~

**Log sampling không phải tắt logging toàn bộ một logger.** Nó là policy chọn records có chủ đích, có thể hoạt động tại ứng dụng, logging backend, agent hoặc collector.

## 2. Phân biệt log sampling, trace sampling và metrics

Ba tín hiệu có pipeline và semantics riêng. Sampling một loại dữ liệu không tự động sampling loại khác.

| Cơ chế | Đối tượng được chọn | Ví dụ |
| --- | --- | --- |
| Log sampling | Log records/sự kiện | Giữ 1% log thành công của request phổ biến |
| Trace sampling | Trace hoặc spans theo sampling decision | Giữ 10% traces ở root sampler |
| Metrics aggregation | Phép đo được tổng hợp theo meter/labels | Counter tăng cho mỗi request; histogram gom phân phối |
| Log level filtering | Log events theo severity | Không phát DEBUG khi production |
| Rate limiting | Giới hạn số event trong một cửa sổ | Tối đa 100 warning/phút |
| Deduplication | Gộp các event giống nhau | Một cảnh báo tổng hợp thay cho hàng nghìn dòng trùng |

Ví dụ: một request không được trace sampler chọn vẫn có thể tạo application log nếu log pipeline cho phép. Ngược lại, một trace được sample không có nghĩa mọi log record trong trace đó đều được giữ.

Không dùng log sample count để suy ra tổng số request nếu policy không giữ toàn bộ records. Metrics Counter/Timer thường là nguồn phù hợp hơn để đo request volume, error rate và latency.

### 2.1. Log sampling không thay thế log level

Log level xác định mức độ chi tiết/quan trọng mà ứng dụng phát ra. Sampling quyết định records đủ điều kiện nào được giữ hoặc chuyển tiếp.

- Giảm production log volume bằng cách cấu hình DEBUG thành INFO/WARN là log-level policy.
- Giữ 1 trong 100 log records INFO cùng loại là sampling policy.
- Giữ tối đa 100 cảnh báo mỗi phút là rate-limiting policy.
- Gộp 500 log record giống nhau thành một summary là deduplication/aggregation.

Các kỹ thuật có thể phối hợp, nhưng cần xác định policy nào chạy trước và record bị loại ở tầng nào.

## 3. Các kiểu log sampling

### 3.1. Probabilistic sampling

Mỗi log event đủ điều kiện được chọn với xác suất p. Ví dụ p=0.1 có nghĩa kỳ vọng giữ khoảng 10% records đủ điều kiện.

Ưu điểm là đơn giản, phân tán và giảm volume theo tỷ lệ tương đối ổn định khi số lượng lớn. Nhược điểm là các record cùng một request có thể bị chọn/bỏ độc lập, và log hiếm quan trọng có thể vô tình bị loại nếu policy không phân loại trước.

### 3.2. Deterministic sampling

Quyết định chọn được tính từ một key ổn định, ví dụ hash của correlation key hoặc request group. Những records có cùng key có thể cùng được chọn hoặc cùng bị bỏ.

Cách này hữu ích để giữ một chuỗi log nhất quán cho một request/session kỹ thuật, nhưng phải cẩn trọng với key có tính nhạy cảm hoặc phân phối không đều. Không dùng raw email, user ID hay token làm sampling key nếu không có yêu cầu và biện pháp bảo vệ thích hợp.

### 3.3. Rate limiting

Policy giới hạn tối đa số records trong một khoảng thời gian, ví dụ giữ tối đa 50 event cùng loại mỗi phút. Rate limit kiểm soát được burst nhưng có thể loại nhiều hơn dự kiến khi traffic tăng.

### 3.4. Deduplication hoặc burst suppression

Khi một lỗi giống nhau lặp lại hàng nghìn lần, hệ thống có thể ghi một record đại diện, sau đó ghi summary như số lần lặp, thời gian đầu/cuối và một số fingerprint đã được chuẩn hóa.

Deduplication không đồng nghĩa chỉ ghi lỗi đầu tiên mãi mãi. Cần có thời hạn/cửa sổ, số đếm và tín hiệu cho biết event đang bị suppression.

| Kiểu policy | Chọn theo | Điểm mạnh | Rủi ro chính |
| --- | --- | --- | --- |
| Probabilistic | Xác suất | Đơn giản, phân tán | Có thể bỏ event hiếm |
| Deterministic | Hash/key ổn định | Giữ nhóm records nhất quán | Key lệch hoặc không an toàn |
| Rate limiting | Ngưỡng theo thời gian | Kiểm soát burst | Có thể che giấu sự cố lớn |
| Deduplication | Fingerprint/nhóm lỗi | Giảm log trùng | Gộp nhầm các lỗi khác nhau |
| Level filtering | Severity | Điều chỉnh độ chi tiết | Bỏ mất context nếu phân loại sai |

## 4. Tính tỷ lệ sampling và số records kỳ vọng

Giả sử có N log events đủ điều kiện và sampler giữ mỗi event với xác suất p. Số records được giữ kỳ vọng:

\[
E[K] = N \times p
\]

Ví dụ ứng dụng phát 2.000.000 log records INFO mỗi ngày, sampling p=0.05:

\[
2{,}000{,}000 \times 0.05 = 100{,}000
\]

Số record kỳ vọng được giữ là 100.000 mỗi ngày. Đây không phải cam kết chính xác; số thực tế dao động theo ngẫu nhiên, volume và policy.

### 4.1. Độ biến động thống kê

Với Bernoulli sampling độc lập:

\[
Var(K)=Np(1-p)
\]

\[
\sigma=\sqrt{Np(1-p)}
\]

Nếu N=1.000 và p=0.1 thì kỳ vọng 100 records, độ lệch chuẩn là khoảng 9,49. Quan sát 90 hoặc 110 records trong một batch nhỏ chưa chứng minh config sai.

### 4.2. Ước lượng dung lượng

Giả sử mỗi record JSON trung bình 800 bytes, N=2 triệu records/ngày và p=0.05:

\[
100{,}000 \times 800 = 80{,}000{,}000\ bytes
\]

Tương đương khoảng 80 MB/ngày dữ liệu chưa tính compression, metadata transport, index overhead và retention. Kích thước thực tế phải đo tại backend vì record có stack trace thường lớn hơn log success đơn giản.

Không lấy kích thước trung bình của một dòng INFO để dự báo toàn bộ log pipeline nếu hệ thống có nhiều exception stack traces hoặc payload khác nhau.

## 5. Xác định loại log được phép sampling

Không nên áp dụng một xác suất duy nhất cho mọi logger và mọi severity.

Một phân loại tham khảo:

| Nhóm | Ví dụ | Chính sách gợi ý |
| --- | --- | --- |
| High-volume success | Request completed, cache hit | Có thể sampling hoặc thay bằng metrics |
| Repetitive diagnostics | Retry attempt, polling status | Sampling/rate limit, có summary |
| Debug details | Chi tiết protocol trong lúc debug | Log level/config theo thời hạn |
| Warning có thể phục hồi | Một dependency chậm nhưng fallback thành công | Rate limit có đếm suppression |
| Error request thất bại | Database unavailable, uncaught exception | Bảo vệ đường log; không sample ngẫu nhiên mặc định |
| Security event | Authentication failure, policy violation | Theo policy security, thường phải giữ đủ sự kiện cần thiết |
| Audit event | Thay đổi quyền, giao dịch bắt buộc audit | Không áp dụng sampling làm mất record bắt buộc |

Bảng là hướng dẫn thiết kế, không phải quy tắc tuyệt đối. Một warning có thể là tín hiệu quan trọng trong hệ thống thanh toán; một error có thể là business outcome được dự kiến. Phân loại theo semantics, yêu cầu vận hành và quy định lưu trữ.

### 5.1. Không để sampling che giấu lỗi hệ thống

Nếu mọi exception đều đi qua một probabilistic filter, một sự cố ảnh hưởng hàng loạt có thể mất phần lớn dấu vết. Tốt hơn là:

- Ưu tiên phát hiện bằng metrics và alert.
- Bảo vệ các error records có giá trị chẩn đoán.
- Giảm các log lặp lại ở tầng retry/polling.
- Nếu cần kiểm soát error burst, dùng rate limit/dedup có suppression counter và summary.
- Có đường log riêng cho audit/security theo yêu cầu.

Nếu log pipeline downstream tự sampling mà ứng dụng không biết, cần theo dõi drop counts ở collector/agent và xác định chính sách cho từng source.

## 6. Sampling trong Spring Boot và logging backend

Spring Boot cung cấp logging integration và cấu hình mức log, nhưng không có một property phổ quát duy nhất tên log-sampling-probability áp dụng cho tất cả logging backend.

Với Spring Boot mặc định dùng Logback trong nhiều ứng dụng, có thể tùy biến appender/filter hoặc dùng agent/collector có sampling processor tương ứng. Với Log4j2, cơ chế filter/appender khác. Cấu hình phải dựa vào backend thật sự.

Ví dụ logging level trong application.yml:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.web: WARN
    example.orders: INFO
~~~

Đây là level filtering, không phải probabilistic sampling. Đừng mô tả việc đổi DEBUG thành INFO là log sampling.

### 6.1. Vì sao không đưa một filter giả định vào mọi Spring Boot app?

Logback, Log4j2, JUL và các agent logging pipeline có API khác nhau. Một filter dùng cho Logback không dùng nguyên trạng cho Log4j2. Kiểm tra logging implementation thực tế, version và nơi event được tạo trước khi chọn giải pháp.

Nếu sampling thực hiện tại collector/agent, ứng dụng có thể phát đủ event nhưng backend nhận một phần. Nếu sampling thực hiện trong appender, event bị loại trước khi ghi file/console. Hai cách có ảnh hưởng khác nhau tới disk I/O, network, chi phí và khả năng dùng local logs khi collector lỗi.

## 7. Ví dụ Logback filter có xác suất

Logback hỗ trợ filter ở appender. Một filter tùy chỉnh có thể quyết định accept/deny event dựa trên logger, level và random value. Ví dụ dưới đây minh họa ý tưởng, cần đóng gói class filter trong ứng dụng và cấu hình đúng theo Logback version.

~~~java
package example.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;

import java.util.concurrent.ThreadLocalRandom;

public class InfoSamplingFilter extends Filter<ILoggingEvent> {
    private double probability = 0.1;

    public void setProbability(double probability) {
        if (probability < 0.0 || probability > 1.0) {
            throw new IllegalArgumentException(
                    "probability must be between 0 and 1");
        }
        this.probability = probability;
    }

    @Override
    public FilterReply decide(ILoggingEvent event) {
        if (event == null) {
            return FilterReply.NEUTRAL;
        }

        // Chỉ sample INFO; giữ WARN/ERROR và các mức còn lại.
        if (!Level.INFO.equals(event.getLevel())) {
            return FilterReply.NEUTRAL;
        }

        return ThreadLocalRandom.current().nextDouble() < probability
                ? FilterReply.ACCEPT
                : FilterReply.DENY;
    }
}
~~~

Filter này chỉ minh họa một policy đơn giản:

- Chỉ áp dụng xác suất cho INFO.
- WARN/ERROR không bị filter này loại.
- Event không xác định trả NEUTRAL để filter/appender tiếp tục xử lý.
- Probability nằm trong khoảng 0.0–1.0.

**Lưu ý quan trọng:** filter trả ACCEPT có thể kết thúc chuỗi filter ở một số cấu hình; filter khác và appender composition cần được kiểm tra theo Logback version. Ví dụ cũng không có counters cho records bị loại, không phân loại logger cụ thể và không đảm bảo giữ log success đại diện theo request. Trước khi dùng production, cần bổ sung metrics, test filter chain, xác định file/console appender và kiểm tra thứ tự filter.

Không gắn filter này toàn cục một cách thiếu chọn lọc. Có thể giới hạn vào logger riêng hoặc appender dành cho nhóm log success volume cao.

## 8. Sampling có tính nhất quán theo request

Probabilistic log sampling độc lập từng record có thể giữ dòng đầu của một request nhưng bỏ dòng cuối, hoặc giữ exception context mà bỏ log mô tả bước trước. Khi điều tra workflow nhiều bước, cách này tạo mảnh dữ liệu rời rạc.

Một lựa chọn tốt hơn cho một số use case là deterministic sampling dựa trên trace ID/correlation key đã có. Mọi log records có cùng key có thể cùng được chọn trong policy.

~~~text
traceId = 4bf92f...
hash(traceId) -> sampling bucket
bucket < threshold -> giữ log group
otherwise -> loại log group đủ điều kiện
~~~

Ưu điểm:

- Các log records của cùng trace có cơ hội được giữ nhất quán.
- Backend có thể tìm được một mẫu workflow tương đối đầy đủ.
- Nhiều service có thể dùng cùng quy tắc nếu key và algorithm thống nhất.

Giới hạn:

- Chỉ có thể dùng key nếu context đã có khi sampling decision xảy ra.
- Trace ID không phải secret nhưng vẫn là identifier; cần giới hạn truy cập/log export.
- Nếu request không có trace context, cần policy fallback.
- Deterministic sampling theo một key phân phối lệch có thể tạo tỷ lệ giữ không đều.
- Các log quan trọng như security/audit không nên bị loại chỉ vì trace group không được chọn.

Không tự viết hash sampler bằng raw string concatenation rồi đưa vào production mà không đánh giá ổn định thuật toán, encoding, salt/version và phân phối key.

## 9. Trace sampling và log sampling có phối hợp được không?

Có thể phối hợp, nhưng phải có chủ đích.

Ví dụ:
- Trace sampler giữ 10% traces.
- Log policy giữ phần lớn ERROR logs.
- Success INFO logs được sample theo trace ID với tỷ lệ 10%.
- Metrics Counter/Timer vẫn ghi mọi request đủ điều kiện.

~~~mermaid
flowchart TD
  A["Request"] --> B["Trace sampler"]
  A --> C["Application logging"]
  A --> D["Metrics"]
  B --> E["Trace retained or dropped"]
  C --> F{"Log category"}
  F -->|"ERROR / protected"| G["Keep"]
  F -->|"Routine INFO"| H["Log sampler"]
  H --> I["Keep selected logs"]
  H --> J["Drop and count"]
  D --> K["Record metrics normally"]
~~~

Nếu muốn success logs tương ứng với trace được sample, log pipeline cần đọc cùng trace sampling context hoặc dùng key/policy thống nhất. Không mặc định Logback tự biết trace sampler đã chọn hay chưa.

Đừng gắn trace ID vào metric label để liên kết signals. Dùng trace/span correlation trong logs và exemplar/links nếu metric backend hỗ trợ.

## 10. Sampling tại application, agent hay Collector?

Log events có thể bị sample ở nhiều tầng:

| Vị trí | Điểm mạnh | Điểm cần lưu ý |
| --- | --- | --- |
| Application/logger filter | Giảm chi phí tạo/ghi log sớm | Cần cẩn thận với classification và local troubleshooting |
| Logging appender | Có thể giới hạn file/console output theo policy | Phụ thuộc backend/version; filter chain dễ cấu hình sai |
| Agent/forwarder | Tách policy khỏi code ứng dụng | Ứng dụng vẫn có thể trả chi phí format/emit trước khi drop |
| Collector processor | Quản lý tập trung nhiều nguồn | Tốn network/ingest trước khi sample; cần processor state/policy |
| Backend ingestion | Policy tập trung, không cần thay app | Có thể vẫn tính phí ingest và truyền dữ liệu trước đó |

Nếu mục tiêu là giảm network/ingest cost, sampling tại agent/collector trước khi gửi backend có thể phù hợp, nhưng sampling trong Collector xảy ra sau khi Collector đã nhận dữ liệu. Muốn giảm chi phí appender/disk, cần policy sớm hơn ở ứng dụng.

Nếu local file logs là nguồn điều tra khi Collector gián đoạn, đừng vô tình loại toàn bộ records ở app trước khi file appender nhận chúng. Có thể dùng appender riêng với chính sách riêng.

## 11. Đo lường records được giữ và bị loại

Sampling không minh bạch sẽ làm người vận hành tưởng rằng ứng dụng không phát log cho một loại sự kiện. Mỗi policy nên có số liệu:

- Tổng log events đủ điều kiện.
- Số records được giữ.
- Số records bị drop/suppressed.
- Tỷ lệ sampling thực tế.
- Số lần filter/collector error.
- Số summary events đại diện cho nhóm đã bị gộp.

Ví dụ metric khái niệm:

~~~text
application_log_events_total{category="routine_info"}
application_log_events_kept_total{category="routine_info"}
application_log_events_dropped_total{category="routine_info",reason="sampled_out"}
application_log_events_suppressed_total{category="retry_warning"}
~~~

Tên trên là ví dụ custom metrics, không phải meter names tự có trong Spring Boot. Dùng label values hữu hạn như category, reason và logger group; không thêm trace ID, request ID hay message text làm label.

Tỷ lệ giữ có thể tính:

\[
keep\_ratio = \frac{kept}{eligible}
\]

Nếu eligible bằng 0, không tính tỷ lệ. So sánh observed ratio với configured probability trên cửa sổ có đủ lượng records. Với rate limiting/dedup, tỷ lệ thực tế phụ thuộc burst và cửa sổ, không phải một probability cố định.

## 12. Structured logging và sampling decision

Structured logs giúp policy phân loại theo event name/category thay vì phân tích chuỗi message dễ thay đổi.

Ví dụ record minh họa:

~~~json
{
  "timestamp": "2026-11-22T10:15:21.104Z",
  "level": "INFO",
  "service.name": "order-service",
  "event.name": "orders.request.completed",
  "log.category": "routine_success",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "duration_ms": 42,
  "outcome": "success"
}
~~~

Một policy có thể chọn event theo log.category hoặc event.name. Không dựa duy nhất vào substring trong message, vì message có thể đổi theo phiên bản hoặc ngôn ngữ.

Structured fields cũng cần allowlist: duration, outcome và service metadata có thể hữu ích; raw user input, request body, credential và PII không nên trở thành field sampling key hoặc field được export mặc định.

## 13. Rate limiting và deduplication cho burst logs

Sampling xác suất không phải giải pháp duy nhất khi một lỗi lặp đi lặp lại. Ví dụ một dependency unavailable khiến hàng nghìn request cùng log một stack trace giống nhau.

Có thể dùng rate limiting/deduplication:

~~~text
Fingerprint: dependency=inventory, exception.type=SocketTimeoutException
Window: 60 seconds

Ghi:
  - event đầu tiên trong window
  - một summary cuối window với suppressed_count
  - một log khi trạng thái hồi phục (nếu có)
~~~

Summary cần chứa:
- Fingerprint đã chuẩn hóa, không chứa message/user input tùy ý.
- Số lần event bị suppression.
- Thời gian đầu và cuối quan sát được.
- Service/dependency/operation có liên quan.
- Một trace exemplar nếu đã có và được phép lưu.

Không gộp các exception khác nguyên nhân chỉ vì message text giống nhau. Cũng cần theo dõi suppressed count; nếu không, nhóm trực vận hành có thể đánh giá thấp quy mô sự cố.

## 14. Bảo mật, audit và retention

Trước khi sampling logs, phân loại data và yêu cầu lưu giữ:

**Security events:** đăng nhập thất bại, thay đổi quyền, truy cập bị từ chối và tín hiệu phát hiện lạm dụng có thể cần được lưu đầy đủ theo chính sách. Không loại bằng sampling thông thường nếu điều đó phá vỡ khả năng phát hiện hoặc điều tra.

**Audit events:** giao dịch hoặc thay đổi cấu hình cần tính đầy đủ/tính toàn vẹn phải đi qua audit/event store có kiểm soát riêng. Application log sampling không nên quyết định sự kiện audit có được lưu hay không.

**Sensitive data:** không sample để che vấn đề lộ dữ liệu. Phải ngăn secret/PII vào log ở nguồn, redaction trước export nếu cần và xử lý retention/access đúng policy.

**Retention:** giảm log volume không thay thế việc thiết kế thời gian lưu, quyền đọc, mã hóa, backup và legal hold. Sampling có thể thay đổi tính đại diện của log history; tài liệu vận hành nên nói rõ policy và thời điểm áp dụng.

## 15. Các lỗi thường gặp khi triển khai log sampling

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Mất ERROR logs | Filter đặt nhầm toàn cục hoặc classification sai | Test mọi severity và protected logger |
| Log success còn nhưng trace không có | Log sampling và trace sampling độc lập | Kiểm tra từng decision/pipeline |
| Trace có nhưng success logs vắng | Log policy sample/dedup records | Kiểm tra sampling counters và event category |
| Tỷ lệ thực không gần probability | Volume ít, filter chain khác, nhiều source hoặc drop sau sample | Đo eligible/kept/dropped ở đúng tầng |
| Burst warning biến mất không có dấu vết | Rate limiter không tạo summary/counter | Theo dõi suppressed count và summary events |
| Local file thiếu log nhưng backend có | Appender filters khác nhau | Kiểm tra appender topology |
| App vẫn tốn CPU dù backend nhận ít log | Sampling ở Collector sau khi app đã format/emit | Cân nhắc filter sớm nếu mục tiêu là giảm application cost |
| Exception stack trace bị mất | Logger ghi message text, encoder/filter loại throwable | Kiểm tra Throwable overload và encoder |
| Sampling theo trace ID không nhất quán | Key/algorithm hoặc context khác nhau giữa service | Thống nhất hashing và propagation |
| Audit record bị drop | Dùng chung sampler với routine logs | Tách audit path và policy |
| Metrics log-drop có cardinality cao | Dùng message/ID làm label | Chỉ dùng category/reason hữu hạn |
| Không biết số record bị loại | Không có eligible/drop counters | Instrument policy và dashboard suppression |

### Quy trình debug

1. Xác định log record được tạo ở logger nào và loại nào.
2. Xác định tầng sampling/filter đang áp dụng.
3. Kiểm tra severity/category và rule có match không.
4. Đo eligible, kept, dropped và suppressed.
5. Kiểm tra appender thứ tự/filter chain.
6. Kiểm tra agent/collector sau khi record rời process.
7. So sánh trace sampling riêng, không suy từ log presence.
8. Kiểm tra protected event path và security/audit policy.

## 16. Tình huống thực tế: request success volume cao và inventory warning burst

**Bối cảnh:** order-service phục vụ nhiều request thành công. Mỗi request tạo log INFO ở controller, service và client. Khi inventory chập chờn, retry loop tạo hàng nghìn WARNING trong vài phút.

### Bước 1 — giữ metrics làm nguồn tổng hợp

Giữ Counter cho request count, success, failure, retry và fallback. Dùng các label có tập giá trị hữu hạn như operation, outcome và dependency. Không giảm Counter theo log sampling.

### Bước 2 — giảm routine INFO

Chọn event category orders.request.completed và áp dụng deterministic hoặc probabilistic sampling ở tỷ lệ đã kiểm thử. Giữ log có trace context nếu policy trace/log consistency yêu cầu.

### Bước 3 — kiểm soát retry warnings

Rate limit warning lặp lại theo fingerprint dependency + exception type. Ghi event đầu tiên, summary với suppressed_count và log hồi phục. Không drop cảnh báo mà không đếm.

### Bước 4 — bảo vệ error/security paths

Log ERROR khi request cuối cùng thất bại tại boundary được chỉ định. Giữ security/audit records theo policy riêng. Không dùng routine sampler cho những loại này.

### Bước 5 — kiểm tra cùng ba signal

Metrics cho thấy số request/retry và tỷ lệ lỗi. Trace được sample cho biết đường đi một số request. Logs còn lại có traceId/spanId để mở đúng trace nếu trace đã được lưu; nếu trace bị bỏ, log vẫn có operation/service/time và correlation key an toàn.

**Kết quả mong muốn:** log volume giảm, error/security signals không bị mất ngoài ý muốn, warning burst có summary và metrics vẫn phản ánh đầy đủ traffic.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — phân loại log events

Tạo event categories: routine_success, retry_warning, dependency_error, security_event và audit_event. Định nghĩa mỗi category được probabilistic sample, rate limit, deduplicate hay protect. Nêu lý do và owner policy.

### Bài tập B — tính volume

Ứng dụng phát 5 triệu log INFO/ngày với p=0.02, mỗi record trung bình 600 bytes. Tính số records kỳ vọng, payload/ngày trước compression và các giả định chưa được tính.

### Bài tập C — kiểm thử Logback filter

Tạo filter chỉ sample INFO. Ghi 10.000 INFO, 100 WARN và 20 ERROR. Đếm eligible/kept/dropped theo category; xác minh WARN/ERROR không bị filter loại. Kiểm tra appender chain và output throwable.

### Bài tập D — deterministic sampling theo trace

Dùng trace ID test làm sampling key cho routine logs. Đảm bảo các records cùng trace nhận cùng decision giữa hai service. Thử request không có trace context và thiết kế fallback. Không dùng ID cá nhân hoặc secret làm key.

### Bài tập E — burst suppression

Mô phỏng một dependency timeout tạo hàng nghìn warning giống nhau. Giới hạn số records trong một cửa sổ, ghi summary suppressed_count và event hồi phục. Đối chiếu với metrics retry/timeout để chứng minh quy mô không bị che.

### Bài tập F — tách signal policies

Đặt trace sampling 10%, log success sampling 5%, error logs protected và metrics ghi đầy đủ. Tạo traffic test, sau đó xác minh số records ở từng pipeline; giải thích vì sao tỷ lệ giữa chúng không cần giống nhau.

### Câu hỏi tự kiểm tra

1. Log sampling khác trace sampling ở điểm nào?
2. Vì sao thay logging level không đồng nghĩa với sampling?
3. Probabilistic sampling có đảm bảo giữ đúng p phần trăm trong mọi phút không?
4. Deterministic sampling có ưu điểm gì khi chọn theo trace ID?
5. Khi nào rate limiting tốt hơn probabilistic sampling?
6. Vì sao không nên dùng routine sampler cho audit events?
7. Sampling ở appender khác sampling ở Collector thế nào về chi phí?
8. Vì sao cần eligible/kept/dropped counters?
9. Làm thế nào bảo đảm ERROR logs không bị filter nhầm?
10. Tại sao metrics vẫn cần ghi đầy đủ khi success logs được sample?
11. Structured event category giúp sampling policy ổn định thế nào?
12. Burst suppression cần summary nào để không che quy mô sự cố?
13. Log có thể còn khi trace bị sampling loại không?
14. Trace có thể còn khi application log bị sample không?
15. Những dữ liệu nào không được dùng làm sampling key hoặc log attribute?

**Tiêu chí hoàn thành:** phân biệt log sampling với trace sampling/level filtering; hiểu probabilistic, deterministic, rate limit và dedup; phân loại protected logs; thiết kế filter/appender đúng backend; đo eligible/kept/dropped; giữ correlation context; kiểm soát bảo mật và kiểm thử burst.

## 18. Ghi nhớ

- Log sampling chọn log records đủ điều kiện để giảm volume; nó độc lập với trace sampling và metrics recording.
- Probability p cho số record kỳ vọng, không bảo đảm tỷ lệ chính xác trong mọi cửa sổ nhỏ.
- Log level filter, probabilistic sampling, deterministic sampling, rate limiting và deduplication là các cơ chế khác nhau.
- Phân loại log theo semantics. Không áp dụng routine sampling làm mất audit/security events hoặc error signals cần thiết.
- Sampling trong appender giảm chi phí ghi tại appender; agent/Collector sampling có thể xảy ra sau khi application đã tạo và gửi record.
- Deterministic sampling theo trace/correlation key có thể giữ nhóm log nhất quán, nhưng cần context, key an toàn và thuật toán ổn định.
- Theo dõi eligible, kept, dropped và suppressed counts. Không để sự kiện bị loại mà không có số liệu.
- Dùng structured event/category để policy ổn định; tránh match theo message text tự do.
- Metrics tiếp tục định lượng request/error/latency; traces mô tả một số lần thực thi; logs cung cấp sự kiện. Không suy tổng request từ số log được giữ.
- Bảo vệ secret/PII, giữ log ownership rõ ràng và xác minh filter chain ở đúng logging backend.

## Tài liệu tham khảo

- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html)
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html)
- [SLF4J Manual](https://www.slf4j.org/manual.html)
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OpenTelemetry Collector — Filter Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/filterprocessor)
- [OpenTelemetry — Sampling concepts](https://opentelemetry.io/docs/concepts/sampling/)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)

