# Log sampling trong Java Core Logging

## Mục tiêu học tập

Bài học thuộc nhóm **Observability**, chủ đề **Log sampling**. Trong một hệ thống Java có lưu lượng lớn, mỗi request, message hoặc thao tác nền có thể sinh hàng chục dòng log. Việc gửi toàn bộ DEBUG/INFO lên collector có thể làm tăng CPU, I/O, băng thông, chi phí lưu trữ và độ nhiễu khi điều tra. **Log sampling** là chủ động chọn một phần các log event theo một chính sách có thể giải thích, nhằm giữ tín hiệu quan sát hữu ích trong một ngân sách tài nguyên xác định.

Sau bài này, bạn có thể:

- Phân biệt **sampling**, **filter theo level**, **rate limiting**, **aggregation**, **deduplication** và **log loss ngoài ý muốn**.
- Giải thích các kiểu lấy mẫu ngẫu nhiên, xác định theo trace/request ID, theo tỷ lệ, theo ngưỡng, theo mức nghiêm trọng và theo ngữ cảnh.
- Quyết định **sampling ở đâu** trong pipeline Java → appender → agent → collector, đặc biệt khi muốn tiết kiệm chi phí tạo log ngay tại nguồn.
- Xây dựng chiến lược không làm biến mất các sự kiện lỗi, bảo mật, audit hoặc nghiệp vụ quan trọng theo chính sách.
- Chạy ví dụ Java 17 độc lập với quyết định sampling xác định và kiểm tra LogRecord thực sự đến Handler.
- Áp dụng nguyên lý tương tự khi dùng SLF4J/Logback, Log4j 2, tracing và OpenTelemetry mà không nhầm khái niệm sampling logs với sampling traces.
- Đánh giá sai lệch thống kê, tác động lên dashboard/alert và cách ghi nhận số event bị lọc.
- Kiểm thử sampling dưới tải, kiểm tra correlation và tránh tạo log storm, rò dữ liệu hay mất log âm thầm.

**Nguyên tắc:** Sampling là một chính sách **bỏ có chủ đích**, không phải lời hứa rằng mọi log đã được giữ chắc chắn được lưu bền vững. Log quan trọng phải được phân loại theo yêu cầu thực tế trước khi quyết định có được sampling hay không.

## 1. Vì sao cần log sampling?

Một service xử lý 5.000 request/giây, mỗi request phát 10 event INFO/DEBUG, sẽ tạo khoảng 50.000 log event/giây trước khi tính lỗi, stack trace hoặc các background jobs. Nếu mỗi event trung bình 500 byte thì chỉ riêng payload thô khoảng 25 MB/giây, chưa tính giao thức, index, bản sao, compression và metadata. Con số minh họa cho thấy việc log tất cả mọi thứ có thể vượt năng lực collector hoặc ngân sách lưu trữ.

Sampling giúp:

1. Giảm log volume từ các hoạt động có mật độ cao nhưng ít giá trị điều tra, như healthcheck thành công, cache hit, heartbeat, các request thông thường.
2. Giữ một mẫu có khả năng giúp phân tích hành vi đại diện ở môi trường staging/production.
3. Tập trung log chi tiết theo request/trace được chọn, thay vì giữ từng event ngẫu nhiên làm đứt chuỗi nguyên nhân.
4. Giảm chi phí serializer/appender/agent **nếu quyết định được thực hiện đủ sớm**.
5. Giảm noise và tránh collector/queue bị quá tải làm ảnh hưởng application latency.

Nhưng sampling cũng có chi phí về tri thức: sự kiện bị loại khỏi sample sẽ không thể tìm lại trong log sink đó. Vì vậy cần thêm **metrics tổng đếm**, **tracing** và chính sách bảo toàn critical events để không đánh đồng “không thấy log” với “sự kiện không xảy ra”.

### Một phép tính đơn giản

Giả sử một nhóm log INFO có tỷ lệ giữ `p=0,10`. Trong mô hình chọn độc lập, kỳ vọng cứ 100 event sẽ giữ khoảng 10 event. Nhưng trong mỗi khoảng nhỏ có thể giữ 8, 13 hoặc thậm chí 0 event. **Sampling 10% không phải giới hạn chính xác 10 event trên mỗi 100 event.**

Nếu mục tiêu là không vượt **100 event/giây**, một sampler xác suất `p=0,10` không bảo đảm giới hạn đó khi đầu vào tăng lên 100.000 event/giây. Khi cần giới hạn tốc độ, phải cân nhắc rate limiter/token bucket hoặc cơ chế quota riêng.

## 2. Khái niệm: sampling không đồng nghĩa với filtering hay dropping

| Cơ chế | Câu hỏi nó giải quyết | Tính chất |
| --- | --- | --- |
| **Level filter** | Event ở mức `DEBUG` có được phát khi logger đặt `INFO`? | Quyết định theo độ nghiêm trọng, thường deterministic |
| **Log sampling** | Trong những event đủ điều kiện, event/trace nào được giữ? | Giữ một tập con theo policy, có thể xác suất hoặc deterministic |
| **Rate limiting** | Tối đa bao nhiêu event hoặc bytes trong một thời gian? | Hạn chế tốc độ hoặc quota; có thể kết hợp sampling |
| **Deduplication** | Các event tương đương bị lặp có thể gộp không? | Cần khóa và khoảng thời gian/định nghĩa tương đương |
| **Aggregation** | Có thể thay từng event bằng thống kê tổng hợp? | Giữ các counters/histograms thay vì log chi tiết |
| **Drop do overload** | Queue đầy, appender hoặc collector lỗi đã làm mất bao nhiêu event? | Không phải mẫu thống kê hợp lệ nếu không có chính sách xác suất biết trước |
| **Retention** | Log đã lưu sẽ bị xóa sau bao lâu? | Xử lý ở vòng đời lưu trữ, không phải lựa chọn event ban đầu |

**Một pipeline có thể dùng nhiều cơ chế nối tiếp.** Chẳng hạn logger level loại TRACE/DEBUG toàn cục, custom sampler giữ 10% INFO của package nhiều noise, WARN/ERROR được giữ, sau đó agent có quota và collector có ingest filter. Khi debug, phải biết **từng tầng** có thể loại event; không được gọi mọi trường hợp “không tìm thấy log” là sampling.

### Sampling trước hay sau khi định dạng?

Ví dụ đường đi:

```text
Java call site
  |
  +-> evaluate arguments / create message
  |
  +-> logger level gate
  |
  +-> early sampling decision (nếu có)
  |
  +-> event object / expensive formatting
  |
  +-> appender -> async queue -> stdout/file/network
  |
  +-> log shipper -> collector sampling -> index
```

Đây là **sơ đồ khái niệm**, thứ tự thực tế phụ thuộc framework và cách gọi API. Một sampling filter gắn ở collector có thể giảm chi phí index nhưng **không giảm** CPU tạo message trong Java, lưu lượng appender, serialization hay băng thông giữa JVM và collector. Một sampling filter thực thi trước khi event được tạo/format có thể giảm thêm chi phí tại nguồn, nhưng không tránh được Java đánh giá những đối số đắt tiền **trước lời gọi method**, nếu code caller đã tính chúng.

## 3. Những loại log không nên sampling tùy tiện

Trước khi chọn p=10%, phải phân loại log.

| Nhóm event | Chính sách thường phù hợp | Vì sao |
| --- | --- | --- |
| DEBUG/TRACE của luồng bình thường | Sampling mạnh hoặc tắt theo environment | Rất nhiều và chủ yếu phục vụ điều tra chi tiết |
| INFO của các request thành công, healthcheck, cache hit | Sampling/aggregation/rate limit theo nhu cầu | Số lượng lớn, metrics thường đủ cho tổng quan |
| WARN do retry tạm thời, có thể tự phục hồi | Policy theo tần suất/loại lỗi; giữ summary và terminal outcome | Tránh log storm, nhưng cần biết tình trạng retry |
| ERROR không xử lý được | Thường giữ đầy đủ theo chính sách, có alert/metric riêng | Có giá trị điều tra cao; một số hệ thống vẫn cần quota bảo vệ |
| Audit/security decisions bắt buộc | **Không sampling nếu yêu cầu audit cần lưu toàn bộ** | Có thể liên quan nghĩa vụ pháp lý và chứng cứ |
| Chuyển tiền, thay đổi quyền, xóa dữ liệu | Đường sự kiện/transactional audit riêng | Không phụ thuộc vào sampler của log chẩn đoán |
| Dữ liệu nhạy cảm | **Redact/minimize trước mọi log** | Sampling 1% không biến việc lộ secret thành an toàn |
| Exception không thường xuyên | Có thể giữ đầy đủ và phân loại theo error code | Lỗi hiếm dễ biến mất trong mẫu ngẫu nhiên |

Không có quy tắc chung rằng “WARN/ERROR luôn được lưu” ở mọi hệ thống: backend vẫn có thể gặp overflow, network outage, retention hoặc filter khác. Nói chính xác là **sampler của bạn không chủ động loại** những level đó theo chính sách, còn delivery/durability phải được kiểm thử riêng.

Một event `ERROR` chứa token trong stack trace vẫn vi phạm bảo mật nếu được giữ 100%. **Redaction và sampling giải quyết hai bài toán khác nhau.**

## 4. Các chiến lược sampling

### 4.1. Random/Bernoulli sampling

Với mỗi event đủ điều kiện, sinh một biến ngẫu nhiên `u` nằm trong khoảng [0,1), giữ khi `u < p`. Nếu `p=0,05`, event có xác suất giữ 5%. Ưu điểm: dễ hiểu, rẻ, không yêu cầu khóa ổn định. Nhược điểm: các log cùng request có thể bị giữ/bỏ độc lập, làm đứt chuỗi điều tra.

Pseudocode:

```text
if event.isCritical:
    KEEP
else if randomUniform0to1() < 0.05:
    KEEP
else:
    DROP
```

**Không lấy random sampling để bảo đảm mỗi cửa sổ chính xác một quota.** Một burst rất ngắn vẫn có thể tạo nhiều event được giữ. Với hệ thống quan sát một sự cố hiếm gặp, random có thể bỏ qua toàn bộ chuỗi log liên quan nếu không có rule ưu tiên sự kiện lỗi.

### 4.2. Deterministic/hash-based sampling

Thay vì rút random cho từng event, có thể băm **một khóa ổn định** như trace ID hoặc request ID và chọn nếu hash thuộc tập bucket được giữ. Cùng khóa và cùng cấu hình sẽ có cùng quyết định.

```text
bucket = stableHash(traceId) mod 100
keep = bucket < 10
```

Đây là **pseudocode**. Một implementation production nên dùng hash có phân bố ổn định, được kiểm thử với kiểu ID của hệ thống, cách chuẩn hóa key nhất quán và chính sách version hóa. Dùng `String.hashCode()` đơn giản trong bài học giúp hiểu quy tắc, nhưng **không phải hàm băm mật mã** và chưa chắc cho phân bố tốt với mọi tập khóa.

Lợi ích: các log INFO/DEBUG thuộc cùng trace có cùng quyết định, nên khi một trace được giữ, nhóm log chi tiết có xu hướng đi cùng nhau. Nhưng:

- Nếu WARN/ERROR luôn được giữ, một trace bị bỏ sampling vẫn có thể có error log. Đây là **override theo độ nghiêm trọng**, không phải mâu thuẫn.
- Nếu trace ID thiếu/không hợp lệ, phải có fallback rõ ràng, không tự dùng một hằng `null` rồi vô tình đưa tất cả vào cùng bucket.
- Nếu p thay đổi trong lúc request kéo dài, cùng trace có thể nhận quyết định khác giữa các lần gọi. Muốn nhất quán toàn trace, giữ sampling decision/phiên bản policy trong context hoặc đảm bảo cấu hình ổn định theo yêu cầu.
- Nếu từng service dùng hash khác nhau, cùng một trace có thể được sample ở A nhưng bị bỏ ở B; cần policy liên dịch vụ nhất quán hoặc định nghĩa rõ phạm vi.
- Nếu key do client không đáng tin tự chọn, client có thể thử ID cho đến khi lọt mẫu. Không dùng rule sampling làm boundary bảo mật/authorization.

### 4.3. Fixed interval: một trong N

Ví dụ giữ mỗi event thứ 100 do một counter tăng:

```text
if counter.incrementAndGet() % 100 == 0:
    KEEP
else:
    DROP
```

Pseudocode này minh họa nhịp đều, dễ giới hạn tương đối với lưu lượng ổn định. Tuy nhiên nó phụ thuộc **thứ tự arrival**, không giữ nguyên trace context, có thể bị bias nếu traffic có chu kỳ tương quan với counter. Counter trên từng JVM/pod không tạo ra quota toàn cluster; nếu restart counter từ đầu, chu kỳ thay đổi. `AtomicLong` có thể giúp cập nhật an toàn trong một process, nhưng không đồng bộ giữa các replicas.

### 4.4. Rate limiting và token bucket

Token bucket cho phép burst ngắn nhưng hạn chế tốc độ trung bình. Ví dụ bucket tối đa 100 tokens, nạp 20 tokens/giây, mỗi event giữ tiêu tốn một token. Khi hết token, event có thể bị drop, defer hoặc chuyển qua policy khác.

Khác biệt với Bernoulli:

- Sampling xác suất p áp dụng **theo tỷ lệ đầu vào**: volume đầu ra tăng theo traffic.
- Token bucket tập trung vào **mức volume tuyệt đối**: nếu traffic tăng mạnh, tỷ lệ giữ thực tế giảm.

Một thiết kế thường kết hợp: sample 10% DEBUG theo trace rồi áp quota cuối để bảo vệ sink. Nhưng khi quota cuối drop event ngẫu nhiên không cùng trace, trace đã chọn có thể mất một số dòng. Nếu yêu cầu giữ toàn bộ trace chi tiết, phải tính **budget theo trace** và cách admission/scheduling tương ứng.

### 4.5. Adaptive sampling

Policy thay đổi dựa trên traffic, queue depth, CPU, log bytes hoặc budget chi phí. Ví dụ giảm tỷ lệ giữ INFO từ 10% xuống 1% khi ingest rate vượt ngưỡng. Cần chú ý:

- Công khai/ghi metric `sampling_policy_version` và **effective sampling probability**; dashboard phải biết sự thay đổi.
- Có hysteresis và giới hạn tốc độ đổi policy để tránh dao động liên tục.
- Phân biệt việc hạ tỷ lệ sampling có chủ đích với event drop do queue overflow.
- Không cho phép thích nghi tự bỏ audit/security hay lỗi critical ngoài quyền chính sách.
- Không đặt quyền điều khiển mức ưu tiên log dựa trên metadata không đáng tin.

### 4.6. Reservoir sampling và mẫu đại diện theo cửa sổ

Reservoir sampling chọn **k phần tử từ một stream** với các điều kiện thống kê nhất định mà không cần biết trước tổng số phần tử. Nó hữu ích khi muốn mẫu kích thước cố định sau một khoảng hoặc một tập dữ liệu, nhưng có hạn chế: cần giữ trạng thái và **chờ đủ dữ liệu/cửa sổ** để biết mẫu cuối; không phù hợp trực tiếp với yêu cầu “gửi ngay từng log nếu được chọn” nếu muốn bảo toàn đúng xác suất mẫu. Trong hệ thống nhiều pod, cần thiết kế merge hoặc quota theo shard.

Đừng tự gọi một token bucket hoặc “mỗi N event” là reservoir sampling; chúng có cơ chế, độ thiên lệch và điều kiện tính xác suất khác nhau.

## 5. Head-based, tail-based và error-aware sampling

Trong tracing, **head-based sampling** thường quyết định ở đầu một trace trước khi biết kết quả. **Tail-based sampling** quyết định sau khi đã quan sát đủ dữ liệu của trace, ví dụ giữ trace có error hoặc latency cao. Log sampling có thể lấy ý tưởng tương tự, nhưng **không đồng nghĩa** rằng logging framework Java hoặc OpenTelemetry Logs SDK tự động cung cấp tail sampling cho logs.

### Head-based chọn sớm

Nếu ngay khi request đến, ứng dụng tạo sampling decision theo trace ID:

- Có thể bỏ log chi tiết ở nguồn, tiết kiệm allocation/transport.
- Các event trong cùng trace có thể dùng chung quyết định.
- Nhưng nếu request về sau thất bại, log đầu trace có thể đã bị bỏ và không thể khôi phục.
- WARN/ERROR override giúp giữ mốc lỗi nhưng không làm xuất hiện lại INFO/DEBUG đã drop.

### Tail-based giữ sau khi biết outcome

Muốn giữ **toàn bộ log của những request chậm/lỗi**, có thể buffer log trong một phạm vi có giới hạn cho đến khi request hoàn tất; khi biết outcome, quyết định flush hay discard.

```text
request starts
   |
   +-- buffer limited INFO/DEBUG events, keyed by request/trace
   |
request finishes
   |
   +-- if ERROR / slow / selected route -> flush captured context
   |
   +-- otherwise -> keep small sample or discard
```

Đây là **thiết kế tùy biến**, không phải tính năng mặc định được bảo đảm. Cần giới hạn RAM, kích thước event, thời gian sống của buffer, cách xử lý request bị treo/worker crash, cleanup khi timeout và khả năng cô lập tenant. Nếu buffer chứa dữ liệu nhạy cảm, phải áp redaction trước khi lưu vào buffer, không đợi tới lúc flush.

Tail-based không tự làm mất vấn đề overload: phải xác định điều gì xảy ra nếu số request đang mở quá lớn, queue đầy hoặc shutdown trước lúc quyết định. Một phương án an toàn là giữ **metrics tổng thể**, giữ log terminal quan trọng ngay, chỉ buffer log bổ trợ có quota.

### Kết hợp với tracing

Một hệ thống có thể dùng:

- Trace sampling theo policy của OpenTelemetry.
- Log sampling độc lập theo level/logger/trace ID.
- Correlation field `trace_id` và `span_id` trên những log được giữ.

**Trace được sampled không nhất thiết đồng nghĩa mọi log mang trace ID đó sẽ được lưu.** Ngược lại một log ERROR có thể được giữ dù trace của nó không được xuất. Cần thiết kế truy vấn và kỳ vọng người vận hành dựa trên thực tế ấy.

## 6. Thiết kế sampling policy có thể kiểm toán

Trước khi code, hãy mô tả chính sách bằng bảng:

| Nhóm | Điều kiện | Tỷ lệ/chiến lược | Quyết định ưu tiên |
| --- | --- | --- | --- |
| Audit/security bắt buộc | `event_category=AUDIT` | Không sample theo log policy | Luôn **eligible to keep**, sink bền vững riêng |
| Lỗi nghiêm trọng | `level=ERROR` hoặc `SEVERE` | Bypass sampler chung | Giữ event lỗi và exception type an toàn |
| WARN do timeout còn retry | `event_code=downstream.timeout` | Có thể rate limit log chi tiết, giữ terminal summary | Theo error category và outcome |
| INFO request thông thường | `event_code=request.completed` | 5–20% theo trace ID nếu phù hợp | Ghi tỷ lệ/thứ tự thay đổi policy |
| DEBUG của package nhiều noise | `logger=com.example.chatty.*` | 1% hoặc tắt ở production | Cấu hình theo logger |
| Healthcheck thành công | `event_code=healthcheck.ok` | Aggregate thành metric; có thể giữ mẫu hiếm | Không che healthcheck failure |

**Các tỷ lệ 1%, 5%, 20% là ví dụ minh họa**, không phải khuyến nghị chung. Giá trị thực phải lấy từ volume, nhu cầu truy vết, chi phí, đặc tính sự cố và yêu cầu compliance.

### Thứ tự áp dụng rule

Một policy có thể xét:

1. **Data minimization/redaction:** xác định thông tin được phép ghi; không bao giờ dựa vào sampling để che secret.
2. **Classify severity/category:** audit, security, error, info/debug, message type, service.
3. **Critical override:** các sự kiện được duyệt là bắt buộc không bị sampler chủ động drop.
4. **Eligible sampling:** hash/rate/random với p đã được config.
5. **Appender/sink routing:** đưa log được giữ đến đúng đích.
6. **Transport/durability:** kiểm tra queue, collector và retention riêng.

Thứ tự kỹ thuật thực tế có thể khác giữa các backend; yêu cầu cốt lõi là **critical không bị áp sampler chung** và redaction vẫn hoạt động trên mọi tuyến. Nếu một custom sampler ở appender làm mất log INFO trước khi security policy phát hiện đó là audit event, cấu hình đã đặt sai trách nhiệm.

### Ai được phép điều chỉnh sampling?

Sampling production có thể làm thiếu dữ liệu phục vụ điều tra. Thay đổi nên có owner, review, phạm vi service/logger, thời điểm hiệu lực, version, rollback, dashboard kiểm tra và alert nếu critical path bị ảnh hưởng. Không cho client công khai tự set header `sample_rate=0` để vô hiệu hóa log lỗi. Với dynamic config, cần bảo đảm policy được tải an toàn và có default khi config service mất kết nối.

## 7. Ví dụ Java 17: sampling nhất quán theo trace ID

Ví dụ chạy độc lập **JDK 17+**, không cần SLF4J, Logback, broker hay collector. Chương trình:

1. Dùng một policy đơn giản: **WARN/ERROR luôn được phép ghi**, INFO/DEBUG chỉ giữ nếu `Math.floorMod(traceId.hashCode(), 4) == 0` (khoảng 1 trong 4 bucket), event thiếu trace ID được giữ để tránh mất dữ liệu khó chẩn đoán.
2. Gọi `java.util.logging.Logger` cho những event được giữ, gắn handler in-memory để kiểm tra **LogRecord thực sự được phát**.
3. Đếm các quyết định KEEP/DROP, xác minh nội dung/level và tính nhất quán của trace.
4. Không dùng ngẫu nhiên hay đồng hồ, do đó stdout xác định.

**Giới hạn minh họa:** `String.hashCode()` không phải hash mật mã, và dữ liệu đầu vào thật có thể phân bố không đều. Khi làm production sampling nên dùng hash phân phối ổn định được kiểm chứng, hoặc thư viện sampling đã có contract; cùng một chính sách không tự bảo đảm tỷ lệ chính xác 25% ở tập nhỏ.

Tạo file **`LogSamplingDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogSamplingDemo {
    enum Severity {
        DEBUG, INFO, WARN, ERROR
    }

    record Event(String traceId, Severity severity, String code) {
    }

    static boolean selected(String traceId) {
        return Math.floorMod(traceId.hashCode(), 4) == 0;
    }

    static boolean keep(Event event) {
        if (event.severity() == Severity.WARN
                || event.severity() == Severity.ERROR) {
            return true;
        }
        if (event.traceId() == null || event.traceId().isBlank()) {
            return true;
        }
        return selected(event.traceId());
    }

    static Level toJulLevel(Severity severity) {
        return switch (severity) {
            case DEBUG -> Level.FINE;
            case INFO -> Level.INFO;
            case WARN -> Level.WARNING;
            case ERROR -> Level.SEVERE;
        };
    }

    static String displayTrace(String traceId) {
        return traceId == null || traceId.isBlank()
                ? "none" : traceId;
    }

    public static void main(String[] args) {
        List<Event> input = List.of(
                new Event("trace-A", Severity.INFO, "cache.hit"),
                new Event("trace-A", Severity.DEBUG, "cache.lookup"),
                new Event("trace-B", Severity.INFO, "checkout.started"),
                new Event("trace-D", Severity.INFO, "checkout.started"),
                new Event("trace-D", Severity.DEBUG, "inventory.lookup"),
                new Event("trace-C", Severity.WARN, "downstream.slow"),
                new Event("trace-B", Severity.ERROR, "payment.failed"),
                new Event("", Severity.INFO, "no.trace"),
                new Event("trace-E", Severity.INFO, "user.viewed"));

        Logger logger = Logger.getLogger("demo.sampling");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        List<String> captured = new ArrayList<>();
        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    captured.add(record.getLevel().getName() + " "
                            + record.getMessage());
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        sink.setLevel(Level.ALL);
        logger.addHandler(sink);

        int kept = 0;
        int dropped = 0;

        try {
            for (Event event : input) {
                boolean accepted = keep(event);
                String trace = displayTrace(event.traceId());

                System.out.println("decision="
                        + (accepted ? "KEEP" : "DROP")
                        + " level=" + event.severity()
                        + " trace=" + trace
                        + " event=" + event.code());

                if (accepted) {
                    kept++;
                    logger.log(toJulLevel(event.severity()),
                            "event=" + event.code() + " trace=" + trace);
                } else {
                    dropped++;
                }
            }

            List<String> expected = List.of(
                    "INFO event=checkout.started trace=trace-D",
                    "FINE event=inventory.lookup trace=trace-D",
                    "WARNING event=downstream.slow trace=trace-C",
                    "SEVERE event=payment.failed trace=trace-B",
                    "INFO event=no.trace trace=none");

            if (!captured.equals(expected)
                    || kept != 5 || dropped != 4
                    || selected("trace-A")
                    || !selected("trace-D")) {
                throw new IllegalStateException(
                        "Sampling assertions failed");
            }

            System.out.println("kept=" + kept);
            System.out.println("dropped=" + dropped);
            System.out.println("captured=" + captured.size());
            System.out.println("trace_consistency=PASS");
            System.out.println("test=PASS");
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LogSamplingDemo.java
java LogSamplingDemo
```

**stdout chính xác:**

```text
decision=DROP level=INFO trace=trace-A event=cache.hit
decision=DROP level=DEBUG trace=trace-A event=cache.lookup
decision=DROP level=INFO trace=trace-B event=checkout.started
decision=KEEP level=INFO trace=trace-D event=checkout.started
decision=KEEP level=DEBUG trace=trace-D event=inventory.lookup
decision=KEEP level=WARN trace=trace-C event=downstream.slow
decision=KEEP level=ERROR trace=trace-B event=payment.failed
decision=KEEP level=INFO trace=none event=no.trace
decision=DROP level=INFO trace=trace-E event=user.viewed
kept=5
dropped=4
captured=5
trace_consistency=PASS
test=PASS
```

### Tại sao kết quả đúng?

- `trace-A` và `trace-B` không thuộc bucket 0 trong phép hash modulo 4, nên các event INFO/DEBUG tương ứng bị bỏ.
- `trace-D` thuộc bucket 0; hai event có cùng trace ID được giữ cùng nhau.
- WARN của `trace-C` và ERROR của `trace-B` được giữ **dù trace không thuộc sample**; override severity hoạt động như chính sách đề ra.
- Event không có trace được giữ theo fallback có chủ đích. Trong hệ thống traffic có nhiều event không trace, fallback này có thể làm volume tăng; cần monitor và lựa chọn khác nếu phù hợp, nhưng không được drop âm thầm.
- JUL dùng `Level.FINE` cho DEBUG, `Level.WARNING` cho WARN và `Level.SEVERE` cho ERROR. Handler capture thật 5 event đã vượt qua quyết định sampling; nó không chứng minh collector/index đã nhận.
- `setUseParentHandlers(false)` tránh output không kiểm soát từ root logger trong chương trình minh họa.
- Các assertions so sánh **toàn bộ danh sách** log được capture với kỳ vọng, kiểm tra số KEEP/DROP và phép chọn bucket của trace. Chỉ sau khi tất cả đúng, chương trình in `test=PASS`.

Đây là một **sampling gate tại call site**, không phải implementation chính thức của Logback/Log4j 2. Trong ứng dụng production, một phương án trung tâm hóa ở logger filter hoặc wrapper thường dễ đảm bảo nhất quán hơn việc lập trình `if (selected)` lặp ở nhiều service.

### Thử nghiệm bổ sung

1. Đổi bucket modulus từ 4 sang 2, giữ nguyên assertions: test có thể fail vì tập sample thay đổi. Nếu muốn thay p, phải cập nhật và kiểm thử lại kỳ vọng.
2. Đổi `keep` để WARN cũng dùng hash: dòng `downstream.slow` sẽ mất và expected list không còn đúng. Đây là regression test cho chính sách critical override.
3. Đổi cùng trace ID của một event thành `trace-E`: các event không còn liên kết trace consistency. Điều này minh họa vì sao ID phải được propagate đúng qua async threads/services.
4. Thêm nhiều event thiếu trace: output tăng vì fallback đang keep-all; điều này không phải bug Java nhưng là vấn đề budget cần phát hiện bằng metric.

## 8. Logback: nên dùng logger filter hay appender filter?

Với SLF4J + Logback Classic, có ít nhất hai nơi đặt logic lọc:

- **TurboFilter** hoạt động ở đường gọi logger trong Logback, có thể từ chối trước khi tạo `ILoggingEvent` trong nhiều tình huống, nhờ đó tránh một phần allocation/formatting không cần thiết.
- **Appender filter** chạy ở từng appender và quyết định event có tới sink cụ thể hay không; lúc này event thường đã được tạo, nên không tiết kiệm toàn bộ chi phí caller.
- **Collector filter** diễn ra sau khi JVM/appender đã gửi; tiết kiệm ingestion/indexing downstream, không loại chi phí nguồn.

Cần kiểm tra **đúng framework và phiên bản**. `TurboFilter` là khái niệm riêng của Logback Classic, không phải một API chuẩn của SLF4J. Các kết quả `DENY`, `NEUTRAL` và `ACCEPT` cũng cần hiểu ở từng tầng: `NEUTRAL` là **tiếp tục xét các rule khác**, không phải bảo đảm event sẽ được ghi ở mọi sink.

### Ví dụ TurboFilter theo trace ID

Đoạn Java sau là **lớp tích hợp Logback**, không chạy độc lập với `javac` nếu thiếu dependency. Nó chủ động drop INFO/DEBUG thuộc package noisy khi trace ID không vào bucket sample, để WARN/ERROR và các logger khác đi qua bình thường.

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.turbo.TurboFilter;
import ch.qos.logback.core.spi.FilterReply;
import org.slf4j.MDC;
import org.slf4j.Marker;

public final class TraceSamplingTurboFilter extends TurboFilter {
    @Override
    public FilterReply decide(Marker marker, Logger logger,
                              Level level, String format,
                              Object[] params, Throwable throwable) {
        if (!logger.getName().startsWith("com.example.chatty.")) {
            return FilterReply.NEUTRAL;
        }

        // Giữ WARN, ERROR và mức quan trọng hơn theo rule.
        if (level.isGreaterOrEqual(Level.WARN)) {
            return FilterReply.NEUTRAL;
        }

        // Chỉ sample INFO và DEBUG trong logger noisy.
        if (level != Level.INFO && level != Level.DEBUG) {
            return FilterReply.NEUTRAL;
        }

        String traceId = MDC.get("trace_id");
        if (traceId == null || traceId.isBlank()) {
            return FilterReply.NEUTRAL;
        }

        boolean selected =
                Math.floorMod(traceId.hashCode(), 10) == 0;
        return selected ? FilterReply.NEUTRAL : FilterReply.DENY;
    }
}
```

**Cấu hình Logback minh họa** (đặt class trên trong classpath):

```xml
<configuration>
    <turboFilter class="com.example.logging.TraceSamplingTurboFilter"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level trace=%X{trace_id} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="DEBUG">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Trong ví dụ XML, class phải nằm đúng package đã cấu hình; Java snippet chưa khai báo `package` nên khi dùng thực tế cần đưa file vào `com.example.logging` và thêm package declaration hoặc chỉnh `class` đúng fully-qualified name. Đây là cấu hình dạy nguyên lý, **không phải khuyến nghị để root DEBUG toàn bộ production**. Dùng logger levels của production phù hợp và giới hạn đúng package mục tiêu.

Phân tích:

1. Chỉ logger có tên bắt đầu `com.example.chatty.` bị áp sampler; các logger khác trả `NEUTRAL`.
2. WARN/ERROR đi tiếp các rule khác, **không bị filter này từ chối**; nhưng effective level/appender filter vẫn có thể loại chúng ở tầng sau nếu cấu hình khác.
3. Missing trace ID được cho qua để tránh mất dữ liệu không có correlation; cần monitor missing-context rate và volume.
4. `Math.floorMod(...,10)==0` chọn một trong 10 buckets theo demo hash; việc phân bố thực tế cần kiểm thử với trace ID production.
5. MDC được đọc trong caller context ở thời điểm TurboFilter quyết định; với async boundaries cần kiểm tra context propagation và cleanup.
6. Filter không tự thực hiện redaction hoặc phân quyền. Nếu log chứa secret, sampling không làm nó an toàn.

**Giới hạn kỹ thuật:** Rule ở đây áp dụng cho INFO và DEBUG của một package, không phân biệt từng event code. Nếu một INFO audit/security bất ngờ nằm trong `com.example.chatty.*`, nó có thể bị sample. Khi production, phải tách audit route hoặc bổ sung phân loại đáng tin ở điểm sớm hơn; không dựa vào level một mình. Vì vậy cần regression test với event codes quan trọng trong package đó.

### Unit và integration test TurboFilter

- Gắn `ListAppender` vào logger thử nghiệm, phát nhiều trace IDs, xác nhận event count và level.
- Test negative: các event noisy không được chọn không đi vào ListAppender/sink.
- Test positive: WARN/ERROR và logger ngoài package không bị sampling filter chặn.
- Test missing MDC: có policy fallback rõ, không ghi nhầm trace của request trước.
- Test parent/additivity và async sink: tránh bản sao ở root hoặc mất event sau sampling.
- Test reload sampling policy: cùng trace quyết định có thay đổi ngoài ý muốn không?
- Test dưới tải: filter có thread-safe, allocation ít, không dùng lock nóng hoặc random shared contention không?

Nếu cần sử dụng cùng rule cho nhiều ngôn ngữ/services, nên định nghĩa policy và thuật toán băm **trong tài liệu giao thức**, không tự cho rằng Java `String.hashCode()` sẽ giống băm của Go/Python/Node.

## 9. Log4j 2, SLF4J và các thư viện khác

**SLF4J** là logging façade. Nó không tự quyết định việc tất cả backends phải hỗ trợ một sampler thống nhất. Log4j 2, Logback, java.util.logging và collector có cấu trúc filter khác nhau.

Với **Log4j 2**, có thể áp dụng điều kiện sampling qua custom Filter tại logger/logger configuration/appender, hoặc dùng routing/config hiện có. Một filter có thể trả `DENY`/`NEUTRAL`/`ACCEPT`, nhưng cần kiểm tra **nơi** nó được gắn; một Filter ở AppenderRef có ý nghĩa và thời điểm khác Filter ở LoggerConfig. Không copy API `TurboFilter` từ Logback sang Log4j 2.

Các điểm khi chọn implementation:

| Vị trí | Tiết kiệm gì? | Vấn đề cần kiểm tra |
| --- | --- | --- |
| Wrapper/call-site guard | Có thể tránh tạo event/expensive message tại nơi gọi | Phải dùng nhất quán, dễ bỏ sót khi code gọi logger trực tiếp |
| Logger-level/custom early filter | Có thể giảm allocation và overhead từ sớm | Semantics/filter ordering, level, logger hierarchy |
| Appender filter | Giảm traffic tới appender/sink đó | Event đã được tạo; fan-out có thể giữ ở sink khác |
| Async queue admission | Giảm tải worker/queue theo rule | Phải phân biệt deliberate sampling với overflow drop |
| Agent/collector processor | Giảm gửi xuống backend hoặc indexing | JVM vẫn chịu chi phí trước đó; metadata/correlation phải còn |
| Backend ingest/index rule | Giảm lưu và search | Không tiết kiệm băng thông/CPU upstream; retention/audit risk |

**Không có cấu hình chung cho mọi appender.** Đọc tài liệu phiên bản backend và exporter thực tế, đặc biệt các tính năng route/filter/sampling thay đổi theo version. Dùng integration tests để xác minh toàn bộ tuyến chứ không chỉ nhìn file XML.

### Dùng SLF4J parameterized logging đúng cách

```java
logger.debug("payload={} request_id={}",
        expensiveSerialize(payload), requestId);
```

Đây là trích đoạn, giả sử biến và logger tồn tại. **`expensiveSerialize(payload)` vẫn được Java gọi trước khi method `debug` chạy**, ngay cả khi DEBUG bị tắt hoặc sau đó bị sampling filter từ chối. Một điều kiện đủ sớm có thể tránh việc đó:

```java
if (logger.isDebugEnabled() && samplingPolicy.keep(requestId)) {
    logger.debug("payload={} request_id={}",
            expensiveSerialize(payload), requestId);
}
```

Đây cũng chỉ là **đoạn tích hợp**, không phải chương trình JDK độc lập. Khi một TurboFilter có thể ảnh hưởng `isDebugEnabled`, cần kiểm tra semantics thực tế; nếu check enabled mà sampler đã được áp một lần, rồi gọi `keep` nữa với **random sampling**, có thể làm tỷ lệ giữ thấp hơn dự kiến. Với deterministic sampling theo ID, hai quyết định thường giống nhau, nhưng có thể lệch nếu policy thay đổi giữa hai lời gọi. Thiết kế một **điểm quyết định duy nhất** hoặc cache decision trong scope khi cần ổn định.

## 10. Tính nhất quán theo trace, request và message

### 10.1. Lấy mẫu theo event hay theo trace?

Nếu chọn độc lập từng event với p=10%, một request có 20 log có thể giữ vài dòng lẻ tẻ. Điều đó hữu ích cho một số phép đo phân phối đơn giản, nhưng khó tái dựng chuỗi xử lý.

Lấy mẫu theo trace ID chọn **cả một nhóm log chi tiết** theo cùng một quyết định. Tuy nhiên xác suất “giữ một event” và “giữ một trace” khác nhau về ý nghĩa thống kê. Một trace dài 100 log và một trace ngắn 2 log có xác suất chọn **trace bằng nhau** nếu sample đều theo trace, nhưng trace dài đóng góp nhiều event/bytes khi được giữ. Vì vậy, sample 10% traces **không bảo đảm** 10% bytes hoặc đúng 10% event.

### 10.2. Message processing và retry

Trong message-driven Java, một message có thể được retry trên worker khác:

- Nếu muốn theo dõi toàn bộ một **logical message**, lấy khóa ổn định `message_id`/`operation_id` được quản lý tin cậy.
- Nếu muốn theo dõi riêng từng delivery, dùng `delivery_id`/`attempt_id` và chấp nhận policy sampling có thể khác giữa attempts.
- Nếu log terminal failure/failed retry bắt buộc phải giữ, override sampling cho nó; đừng tự coi mọi retry attempt là một sự kiện độc lập mang cùng giá trị.
- Không lấy broker offset hoặc delivery tag làm khóa ổn định xuyên retry nếu chúng thay đổi khi republish/requeue.
- Nếu thiếu khóa ổn định, cần fallback và metric đo tỷ lệ missing-context.

### 10.3. Distributed tracing và OpenTelemetry

OpenTelemetry thường cung cấp các khái niệm **sampling cho trace spans** như ParentBased hoặc TraceIdRatioBased ở tracer. Những sampler này quyết định việc ghi spans; **không nên suy ra chúng tự sample hoặc giữ logs theo cùng tỷ lệ**. Logs có thể được thu qua logger instrumentation, SDK exporter, file agent hoặc Collector với cấu hình processors khác.

Trong một hệ thống thiết kế tốt, có thể:

1. Propagate `trace_id`/`span_id` ở context phù hợp.
2. Ghi trường trace ID vào structured logs.
3. Quyết định giữ log chi tiết theo stable hash trace ID **độc lập hoặc có liên kết** với trace sampling.
4. Giữ ERROR theo chính sách ngay cả khi trace spans không được xuất.
5. Kiểm tra Collector processors/filters được dùng thật; không tự nói “OpenTelemetry auto-sample log events” nếu pipeline chưa cấu hình chức năng đó.

**Sampling tại Collector** có thể được cấu hình để drop/filter hoặc dùng processor phù hợp theo phiên bản và distribution. Đừng áp dụng một cấu hình Tail Sampling Processor dành cho trace rồi khẳng định đã tail-sample log record. Cần xác minh implementation có hỗ trợ loại tín hiệu `logs` và semantics mong muốn.

## 11. Tác động thống kê: mẫu không phải toàn bộ dân số

Nếu một tập event được chọn **độc lập** với xác suất biết trước `p`, có thể ước tính tổng đếm bằng cách cộng trọng số `1/p` cho các event giữ lại. Ví dụ 120 event được giữ từ một tập với p=0,10 thì một ước lượng tổng có thể là khoảng 1.200 event. **Đó là ước lượng, không phải bằng chứng chính xác có 1.200 event.**

Với xác suất khác nhau cho từng event, một dạng ước lượng tổng là:

\[\widehat{N} = \sum_{i \in \mathrm{sample}} \frac{1}{p_i}\]

Đây là ý tưởng kiểu Horvitz–Thompson cho tổng dưới điều kiện inclusion probabilities thích hợp; nó không cứu được mọi thiên lệch do quota, queue overflow, downstream data loss hoặc rule phụ thuộc chính kết quả phân tích.

### Những rủi ro khi diễn giải sample

- **Level-aware sampling:** ERROR giữ 100%, INFO giữ 10%. Không nhân toàn bộ log count với 10; phải chia theo nhóm/loại sự kiện và xác suất tương ứng.
- **Trace sampling:** log events thuộc cùng trace phụ thuộc nhau. Số event trong trace có phân phối khác nhau, nên độ bất định lớn hơn cách tính đơn giản cho các event độc lập.
- **Adaptive p:** policy thay đổi theo tải; phải có `policy_version`/`effective_p` tại thời điểm quyết định nếu muốn ước lượng.
- **Missing context:** fallback giữ tất cả hoặc bỏ tất cả, tạo một nhóm có xác suất khác hẳn các trace có ID.
- **Tail/error-aware:** chọn trace vì có error/latency cao. Sample này có bias theo outcome; không thể dùng như mẫu đại diện ngẫu nhiên cho mọi request.
- **Rate limiting:** event tới trước có thể được giữ, event tới sau bị drop khi hết token; xác suất inclusion không còn như Bernoulli p.
- **Collector overflow:** log bị mất ngoài ý muốn làm số đã sample và số đã lưu khác nhau.

Nếu cần **tổng request, error rate, SLO, p95/p99 latency**, nên đo bằng metrics/histograms tại nguồn hoặc telemetry có thiết kế thống kê đúng, thay vì suy ngược mù từ số sampled log lines. Sampling không thay thế sự thật nghiệp vụ.

### Sampling và truy vấn log hiếm

Nếu một event xảy ra xác suất thấp trong một khoảng thời gian, random sampling 1% có thể khiến toàn bộ event hiếm biến mất. Để điều tra sự kiện hiếm, có thể giữ 100% event code/error category quan trọng và sample mạnh các event thông thường. Phải xác định nhóm critical **trước** khi drop và kiểm tra trường hợp error phát sinh sau một chuỗi INFO đã bị bỏ.

## 12. Theo dõi tính hiệu quả và log loss

Một implementation sampling có trách nhiệm cần đo được không chỉ volume output mà cả **những quyết định loại event**.

Các metrics tham khảo:

| Metric | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `logging_events_eligible_total` | Số event đủ điều kiện vào sampling rule | Có thể không thấy các event bị logger level chặn trước đó |
| `logging_events_selected_total` | Số event sampler quyết định KEEP | Không phải số event đã được backend lưu |
| `logging_events_sampled_out_total` | Số event bị loại chủ động bởi sampler | Tách khỏi queue overflow và sink failures |
| `logging_sampling_ratio` | Tỷ lệ KEEP / eligible theo rule | Cần gắn policy/version, bounded labels |
| `logging_queue_dropped_total` | Số event rơi do quá tải queue nếu đo được | Khác deliberate sampling |
| `logging_sink_write_errors_total` | Lỗi khi ghi stdout/file/network | Có thể mất log sau quyết định KEEP |
| `logging_collector_ingest_total` | Số event collector tiếp nhận | Có thể khác JVM selected vì các hop khác |
| `logging_bytes_sent_total` | Băng thông xuất log | Cho biết chi phí thực tế |
| `logging_critical_events_total` | Số critical events tại nguồn, theo policy | Giúp phát hiện critical delivery gap |
| `logging_sampling_policy_changes_total` | Số lần policy cập nhật | Hữu ích khi dashboard đột ngột giảm volume |

Tên metrics chỉ minh họa, **không tự có sẵn** trong SLF4J/Logback/Log4j 2/Collector. Phải thiết kế collector và mức cardinality phù hợp. Không dùng `trace_id`, `request_id`, `user_id` làm label của metrics tổng hợp; chúng có cardinality lớn, làm tăng chi phí monitoring.

**Điểm đo quan trọng:** Một metric gọi `selected_total` ở JVM không chứng minh event được lưu. Nếu logging appender async drop hoặc collector lỗi, cần có counters và reconciliation tại các hop. Đừng khai báo “sampling 10%” rồi đo 1% output và kết luận code sampler sai; có thể các tầng sau đang loại thêm.

## 13. Bảo mật và tính đúng đắn

Sampling có thể giảm lượng dữ liệu được lưu, nhưng không phải kỹ thuật bảo vệ dữ liệu:

- **Không log secrets** như password, token, API key, cookies, raw personal data trừ khi có yêu cầu đã được duyệt.
- Log injection từ user-controlled string vẫn nguy hiểm với cả event được lấy mẫu; dùng structured logging và escaping đúng.
- Một trace ID do client tự đặt có thể bị thao túng; không coi nó là khóa bảo mật hoặc cơ chế quota đáng tin.
- Sự kiện audit/security có thể cần retention/immutable storage và đầy đủ theo nghĩa vụ; đừng đặt chung với sampler DEBUG/INFO.
- Nếu sampler dùng deterministic ID, người dùng có thể đoán/chọn key để khiến message được giữ hoặc bỏ, đặc biệt khi hàm hash công khai. Điều đó không làm sampling mất tính hữu ích cho observability, nhưng có nghĩa nó không thể thay thế kiểm soát truy cập hay rate limit chống DoS.
- Nếu người dùng có nhiều tenant, một thay đổi sampling policy cần đảm bảo không làm rò log của tenant A sang sink của tenant B; routing và authorization độc lập với sampling.
- Khi lỗi collector làm mất logs, không tự fallback sang endpoint HTTP/plaintext hoặc sink rộng quyền chỉ để “cứu” sample.

**Event data chất lượng hơn số lượng.** 100% những log thiếu trace ID, error code hoặc chứa token không tốt hơn một tập log được chuẩn hóa, lấy mẫu có kiểm soát và kết hợp metrics/tracing.

## 14. Performance: sampling có thật sự giảm chi phí?

Điều quan trọng là đặt sampling đủ sớm. Một ví dụ Java:

```java
logger.debug("payload={}", expensiveSerialize(payload));
```

Dù DEBUG tắt, biểu thức `expensiveSerialize(payload)` vẫn được Java đánh giá trước khi gọi method. Nếu dùng sampling filter ở appender, việc serialize payload tại caller vẫn xảy ra.

Có thể tránh chi phí bằng guard khi có một decision service đủ sớm:

```java
boolean eligible = logger.isDebugEnabled();
boolean selected = samplingPolicy.keep(traceId);
if (eligible && selected) {
    logger.debug("payload={}", expensiveSerialize(payload));
}
```

Đây là **trích đoạn**, các biến/logger/samplingPolicy cần tích hợp trong ứng dụng. Chú ý điều kiện `eligible && selected` nếu viết tách như trên vẫn đã gọi `samplingPolicy.keep` dù DEBUG tắt. Muốn tránh luôn cả chi phí tính sampling decision khi DEBUG disabled, gộp:

```java
if (logger.isDebugEnabled() && samplingPolicy.keep(traceId)) {
    logger.debug("payload={}", expensiveSerialize(payload));
}
```

Nhưng tránh áp **hai sampler xác suất độc lập** ở guard và filter/backend sau đó nếu không có chủ đích. Nếu hai tầng giữ 10% độc lập, tỷ lệ kết hợp khoảng 1% với giả định độc lập, không phải 10%. Với multi-hop, phải biết tỷ lệ và semantics ở từng tầng.

### Chi phí chính bản thân sampling

- Hashing trace ID ngắn thường rẻ hơn serialize payload lớn, nhưng vẫn cần benchmark trên data thực.
- Random trong nhiều thread nên dùng API thread-safe phù hợp; đừng tạo new Random/secure hash nặng cho mỗi event nếu không cần.
- Rate limiter toàn cục dùng lock nóng có thể làm tăng contention; cân nhắc per-shard quota và fairness.
- Buffer tail sampling có thể làm tăng heap và GC pauses, đặc biệt khi trace kéo dài hoặc log payload lớn.
- Lấy mẫu ở appender có thể tiết kiệm I/O nhưng không giảm toàn bộ CPU format trước đó.

Benchmark cần đo **logger call p50/p95/p99**, allocation, CPU, bytes/s, queue depth, số event selected, số event received ở sink và effect lên throughput nghiệp vụ. Một benchmark chỉ đo nhanh hơn nhưng có nhiều dropped critical logs là chưa đạt.

## 15. Kiểm thử log sampling

### 15.1. Ma trận kiểm thử policy

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| S1 | Same trace ID, INFO/DEBUG trong cùng policy | Quyết định KEEP/DROP nhất quán |
| S2 | TRACE/DEBUG bị level filter chặn trước | Không tạo event ở sink, không nhầm thành sampler drop |
| S3 | WARN/ERROR thuộc trace bị sample out | Critical override giữ log theo rule |
| S4 | Audit/security event INFO | Không bị rule noisy INFO loại nếu policy yêu cầu full retention |
| S5 | Trace ID thiếu/rỗng/không hợp lệ | Fallback rõ ràng, metric đếm missing context |
| S6 | Nhiều service dùng cùng algorithm/version | Quyết định tương thích với cùng ID nếu đó là yêu cầu |
| S7 | Thay sampling p trong lúc request còn mở | Giữ nhất quán theo contract hoặc ghi nhận policy version |
| S8 | Tập ID mang tiền tố/định dạng khác | Hash distribution không thiên lệch quá mức |
| S9 | Burst gấp 100 lần traffic bình thường | Không hiểu sampler xác suất như hard rate limit |
| S10 | Queue đầy sau quyết định KEEP | Drop/blocked metrics riêng, không báo thành công giả |
| S11 | Collector timeout/retry | Không tạo duplicate ngoài policy, counts quan sát được |
| S12 | Redaction/canary secret | Không rò secret trong bất kỳ log sample nào |
| S13 | Multi-thread/MDC propagation | Không gắn trace ID của request trước vào event sau |
| S14 | Fan-out nhiều appenders | Kiểm tra sampling diễn ra ở phạm vi nào, không tạo log lệch tuyến ngoài policy |
| S15 | Dynamic sampling config rollback | Sau rollback quyết định và metrics trở về policy cũ |
| S16 | Sampled logs làm báo cáo error rate | Dashboard không suy ra sai tổng từ mức p không đồng nhất |

### 15.2. Unit test

Test nên kiểm tra **hàm quyết định** không phụ thuộc logger backend:

- Với trace ID cụ thể, decision đúng.
- Hai event khác level nhưng cùng trace và thuộc group sampling có decision giống nhau.
- WARN/ERROR bypass policy.
- Null/blank key xử lý đúng.
- Thay version/seed/hash làm tập sample thay đổi có kiểm soát.
- Với một tập ID độc lập đủ lớn, tỷ lệ thực nghiệm gần mục tiêu trong khoảng sai số đã tính; **không** assert đúng 10% cho 10 mẫu.

Với random sampler, test nên inject pseudo-random source hoặc seed test để assertion có tính xác định; không dùng random production global làm kết quả unit test cố định. Với token bucket, inject clock điều khiển được; `Clock.fixed` có thể phù hợp để kiểm tra refill theo thời gian, còn đo duration thực tế cần nguồn thời gian đơn điệu.

### 15.3. Integration test logging backend

Gắn in-memory Handler/ListAppender vào logger của ứng dụng:

1. Phát một nhóm event đã biết, mỗi event có test ID.
2. So sánh danh sách được giữ **và bị loại**, đúng level/logger/routing.
3. Với Logback TurboFilter, xác nhận filter được nạp và có hiệu lực ở logger name đúng, không chỉ tồn tại một class.
4. Kiểm tra event audit/ERROR vẫn đến đúng sink và không rơi vào route sai.
5. Thay level/config rồi xem effective filter ordering.
6. Với async appender, chờ drain hoặc signal; không kết luận “không log” chỉ vì query ngay lập tức.

### 15.4. End-to-end test

Sau khi có event IDs duy nhất:

- Xác minh JVM selected count theo policy.
- Xem appender/file/stdout nhận bao nhiêu.
- Xem agent/collector/index nhận bao nhiêu và schema có còn `trace_id`/`event_code`.
- Đặt deadline để truy vấn backend eventual-consistent.
- Đối chiếu các event bị sampled out không được xuất ở sink mà rule quản lý.
- Thử pipeline outage, burst, CPU pressure, restart và policy reload.
- Đánh giá liệu sampling có giảm **bytes và chi phí thực** hay chỉ giảm log hiển thị trên dashboard.
- Khôi phục cấu hình và dọn test events theo quy trình.

### 15.5. Các assertions cần tránh

- `sampleRate == keptCount/totalCount` cho mỗi batch nhỏ: random sampling có variance.
- “Không có dòng ERROR” = không có lỗi: logs có thể bị lọc, drop, thiếu ingestion hoặc lỗi diễn ra ở nơi khác.
- “Trace đã được sampled” = mọi log cùng trace còn nguyên: còn các filters, appenders và collector.
- “10% traces” = “10% events/bytes”: trace có độ dài khác nhau.
- “Appender nhận” = “Index lưu bền vững”: đó là hai acknowledgement boundaries.
- “Không tìm thấy token ở log sample” = source không log token: cần test ở nguồn/encoder và tất cả sinks được phép.

## 16. Troubleshooting các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Gần như không còn INFO | Tỷ lệ p quá thấp, ID phân bố lệch, logger level, collector filter | Kiểm tra từng hop và counts eligible/selected |
| Mất hết log của một trace đã sample | Hash/seed/policy khác nhau giữa services, thiếu context hoặc filter khác | So stable key, policy version và sampling decision |
| WARN/ERROR biến mất | Early level/filter/routing rule hoặc overload, critical override không chạy | Test event ở call site, appender và backend |
| Volume tăng đột biến khi tracing lỗi | Fallback keep-all cho missing trace ID | Đo missing-context ratio và tạo fallback có budget |
| Gấp đôi log sau deploy | Fan-out appenders, root additivity hoặc collector đọc cả file/stdout | Dedup theo event ID, kiểm tra route và hierarchy |
| Sample 10% nhưng ingest chỉ 2% | Queue drops, collector quota, filter downstream | So selected vs sink/collector counters |
| Sample 10% nhưng số bytes vẫn rất lớn | Trace được chọn quá dài, exception stack lớn hoặc p tính theo trace | Đo bytes per event/trace và heavy tails |
| Log success nhiều nhưng error hiếm | Severity-aware policy, đây có thể là hành vi đúng | Chia nhóm theo rule và probability |
| Dashboard error rate sai | Dùng sampled INFO làm denominator nhưng ERROR full | Dùng metrics authoritative hoặc trọng số đúng |
| Sampling làm chậm caller | Hash/lock nặng hoặc sampling xảy ra sau expensive serialization | CPU profile, p99, allocation và vị trí filter |
| MDC trace ID không đúng | Thread pool tái sử dụng, không cleanup/propagate | Test concurrent context, restore MDC ở finally |
| Một client điều khiển được sample | Dùng raw client-controlled ID làm bucket key | Cấp/validate ID đáng tin, không dùng sampler làm security gate |
| Config đổi p nhưng không thấy tác động | Policy cache, filter chưa reload, nhiều pods có version khác | Kiểm tra effective config theo instance và metrics |
| Tìm log theo event time bị thiếu | Ingest lag, clock skew hoặc index query sai | So event timestamp, observed timestamp, namespace |

## 17. Runbook triển khai và điều chỉnh tỷ lệ sampling

1. **Xác định mục tiêu:** giảm chi phí index 50%, giảm bytes/s hoặc đảm bảo giữ trace mẫu cho điều tra? Mỗi mục tiêu dẫn đến lựa chọn khác nhau.
2. **Đo baseline:** events/s, bytes/s, CPU, collector throughput, queue depth, error ratio và chi phí trước sampling.
3. **Phân loại sự kiện:** audit/security/critical, ERROR, WARN có giá trị, INFO/DEBUG nhiều noise; ghi rõ policy và owner.
4. **Chọn key:** trace ID, request ID, operation ID, message ID hoặc event ID; xác định ý nghĩa của việc lấy mẫu theo **đơn vị nào**.
5. **Chọn thuật toán:** random, deterministic hash, rate limiting hoặc adaptive; ghi p, seed, version và missing-context fallback.
6. **Chọn vị trí:** early logger filter nếu cần giảm CPU và bytes tại nguồn; collector nếu chỉ cần giảm downstream index và có lý do.
7. **Viết test:** unit deterministic, negative/critical, test khác ngôn ngữ nếu muốn đồng nhất across services.
8. **Triển khai giới hạn:** canary trên một service/pod, đo selected, sampled-out, sink drops và log visibility.
9. **Đánh giá dashboard:** sửa alert/error-rate/SLO nếu trước đó dựa vào log count không điều chỉnh.
10. **Theo dõi overload:** khi queue/collector hỏng, không che số dropped critical events bằng số selected.
11. **Ghi nhận thay đổi:** ai thay p, lúc nào, ở nhóm nào, khả năng rollback, tính nhất quán policy versions.
12. **Đánh giá định kỳ:** traffic, error patterns và giá trị điều tra thay đổi; p cũ có thể không còn phù hợp.

Một rollout an toàn không nhất thiết bắt đầu từ p rất thấp. Nếu thiếu baseline metrics, giảm sampling 100 lần ngay có thể làm mất dữ liệu điều tra đúng lúc một release mới tạo lỗi. Hãy thay đổi từng nhóm log và xác nhận nguồn dữ liệu thay thế cho các chỉ số quan trọng trước khi cắt.

## 18. Checklist ôn tập

- [ ] Tôi phân biệt được sampling, filtering, rate limiting, aggregation và loss do overload.
- [ ] Tôi biết sampling theo event khác sampling theo trace/request/message.
- [ ] Tôi biết deterministic hash giúp correlation nhưng không tự bảo đảm phân bố hoàn hảo.
- [ ] Tôi không dùng `String.hashCode()` như một hash bảo mật hoặc giả định tương thích với mọi ngôn ngữ.
- [ ] Tôi có chính sách rõ cho WARN/ERROR, audit/security, business critical và event thiếu trace ID.
- [ ] Tôi không coi sampling là cách thay thế redaction, privacy controls hoặc authorization.
- [ ] Tôi biết filter ở collector không tiết kiệm CPU tạo log tại JVM.
- [ ] Tôi tránh xây message đắt tiền trước khi kiểm tra enabled level/sampling decision.
- [ ] Tôi đo cả eligible/selected/sampled-out lẫn drops/ingest downstream.
- [ ] Tôi không dùng sampled log counts trực tiếp làm toàn bộ request/error rates.
- [ ] Tôi hiểu sampling traces trong OpenTelemetry không tự động sampling Java logs theo cùng quyết định.
- [ ] Tôi đã test policy với các trường hợp positive, negative, missing context, concurrency và dynamic change.
- [ ] Tôi có test end-to-end khi cần chứng minh log đến backend, không chỉ Handler nhận.
- [ ] Tôi có cơ chế rollback và ghi nhận version khi thay sampling ratio.
- [ ] Tôi hiểu rằng error log được bypass sampler vẫn có thể mất vì sink/queue failure.

**Tiêu chí hoàn thành:** Bạn có thể trình bày khi nào nên chọn sampling theo trace, vì sao WARN/ERROR thường cần ngoại lệ, viết và chạy `LogSamplingDemo.java`, tự kiểm tra số event giữ/bỏ, phân biệt sample selection với log delivery và xây một sampling policy đo được, an toàn với hệ thống quan sát thực tế.

## 19. Câu hỏi tự kiểm tra

1. Nếu giữ 10% log INFO, có phải cứ đúng 100 event sẽ giữ đúng 10 event không?
2. Một request có 20 log; sampling từng event có khác gì sampling cả trace?
3. Vì sao sampling 10% traces không đồng nghĩa chỉ giữ 10% bytes?
4. Nếu collector drop 50% event sau khi JVM sampler đã giữ 10%, có nên gọi đó là “sampler 5%” không?
5. Khi một log ERROR nằm trong trace không được chọn, hành vi nào thường hữu ích cho chẩn đoán?
6. Tại sao không nên áp sampling cho audit/security events bắt buộc?
7. Điều gì xảy ra nếu cùng trace ID được hash bằng các thuật toán khác nhau ở hai services?
8. Tại sao sampling filter ở appender không tránh được Java đã tính `expensiveSerialize(payload)`?
9. Giữa random sampling, hash-based sampling và token bucket, cơ chế nào giới hạn tương đối và cơ chế nào có thể giới hạn tốc độ?
10. Tail-based sampling logs có cần buffer không? Những rủi ro memory/crash/timeout nào?
11. Nếu một request bị lỗi sau khi INFO đã bị drop, ERROR override có khôi phục INFO không?
12. Một dashboard tính error rate từ số dòng ERROR full và INFO sampled sẽ bị thiên lệch thế nào?
13. Khi trace ID thiếu và fallback keep-all, điều gì có thể xảy ra trong một đợt lỗi propagation?
14. Vì sao một sampling decision dựa trên raw client-controlled ID không thay thế rate limiting và security?
15. Trong Logback, `TurboFilter` và appender filter khác nhau về vị trí/chí phí như thế nào?
16. Làm sao kiểm thử rằng custom filter trả `NEUTRAL` cho WARN mà vẫn có WARN ở sink?
17. Nếu thay p trong lúc một trace chạy, làm sao giữ consistency giữa các event?
18. Vì sao không dùng `message_id` làm metric label cho các bộ đếm sampled-out?

## Tài liệu tham khảo

- [Oracle Java SE 17 — String.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode()) — hash deterministic của chuỗi và giới hạn của ví dụ.
- [Oracle Java SE 17 — Math.floorMod](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#floorMod(int,int)) — modulo không âm khi hash âm.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — logger, level và handlers trong ví dụ.
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — thu log records để kiểm tra.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — TurboFilter, appender filter và FilterReply.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — logger hierarchy, enabled levels và additivity.
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html) — filters tại các tầng logging.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/) — khái niệm sampling trong tracing và các yếu tố liên quan.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — log records và mối liên hệ với trace.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — bảo mật và dữ liệu nhạy cảm trong logging.
