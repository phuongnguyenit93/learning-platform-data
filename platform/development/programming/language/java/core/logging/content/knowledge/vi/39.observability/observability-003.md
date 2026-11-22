# Log và alert trong Observability cho ứng dụng Java

## 1. Bài toán: có log rồi, khi nào phải cảnh báo?

Một ứng dụng Java liên tục tạo sự kiện: request hoàn tất, kết nối database bị timeout, job chạy lại, message được giao lại, exception được ném, circuit breaker mở. **Log** giúp mô tả những sự kiện đó. **Alert** (cảnh báo) phải giúp người trực vận hành biết **khi nào một tình trạng đủ quan trọng để cần hành động**.

Hai câu hỏi khác nhau:
- **Log:** “Điều gì đã xảy ra tại thời điểm này, với thao tác nào và ngữ cảnh nào?”
- **Alert:** “Có điều bất thường nào đủ ảnh hưởng để cần ai đó xử lý ngay hoặc theo lịch không?”

Ví dụ, một request nhận lỗi 500 có thể tạo log `ERROR` và một metric ghi nhận request thất bại. Điều đó **không có nghĩa** hệ thống nên đánh thức on-call ngay lập tức. Nếu tỷ lệ lỗi tăng liên tục, ảnh hưởng checkout của người dùng và vượt tiêu chí đã thỏa thuận, một alert có thể phù hợp. Ngược lại, một service ngừng gửi telemetry hoàn toàn có thể **không còn dòng ERROR nào** mà vẫn đang gặp sự cố.

**Thông điệp chính:** log là nguồn dữ liệu phục vụ chẩn đoán; alert là **quyết định dựa trên tín hiệu, khoảng thời gian, mức ảnh hưởng và chính sách phản ứng**. Không đồng nhất `logger.error(...)` với “đã gửi cảnh báo”.

Mục tiêu sau bài:
1. Phân biệt log, metric, trace, event và alert trong observability.
2. Hiểu alert dựa trên log, alert dựa trên metric và alert dựa trên SLI/SLO; nhận biết hạn chế của từng loại.
3. Thiết kế rule có window, threshold, minimum traffic, persistence, deduplication, grouping, severity, recovery và no-data policy.
4. Viết ví dụ Java 17 độc lập mô phỏng **log summary và alert state machine** có kết quả stdout cố định.
5. Thiết kế runbook, routing, escalation, dashboard và correlation cho alert hữu ích.
6. Kiểm thử alert để giảm false positive, false negative, alert storm và lộ dữ liệu nhạy cảm.

## 2. Phân biệt log, metric, trace và alert

| Thành phần | Trả lời câu hỏi | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Log** | Sự kiện cụ thể nào đã xảy ra? | `event=db_timeout requestId=req-17` | Có metadata chi tiết; volume có thể lớn |
| **Metric** | Tần suất/mức độ đang thay đổi thế nào? | `http_requests_total{result="error"}` | Dùng để tính rate, ratio, latency; label cần cardinality thấp |
| **Trace** | Một luồng xử lý đi qua các bước nào? | HTTP → order-service → database | Giúp thấy critical path, dependency và bottleneck |
| **Alert rule** | Điều kiện nào cho thấy nguy cơ hoặc ảnh hưởng? | Error ratio vượt ngưỡng đủ lâu | Không chỉ là một log event |
| **Alert instance** | Rule đang kích hoạt cho nhóm nào? | `HighErrorRatio{service="checkout"}` | Có trạng thái FIRING/RESOLVED theo hệ thống quản lý |
| **Notification/page** | Ai nhận thông báo và cần làm gì? | On-call nhận page có runbook | Có routing, grouping, escalation và silence policy |

**Log level không phải alert severity.** `ERROR` thể hiện cách nhà phát triển đánh giá một event ở thời điểm ghi. Alert severity như page/ticket/info phản ánh tác động vận hành và mức khẩn cấp. Một bộ phận có thể chỉ log `WARN` vì retry liên tục nhưng tạo cảnh báo nghiêm trọng khi service không đáp ứng SLO.

**Metric không thay thế log.** Metric cho thấy tỷ lệ lỗi tăng từ 0,2% lên 8%, nhưng log/trace giúp biết request và dependency nào bị ảnh hưởng. Ngược lại, chỉ có log từng request rất khó nhận biết mẫu hình tổng thể nếu không tổng hợp đúng.

**Trace không tự bảo đảm mọi request được quan sát.** Sampling, agent drop và thiếu instrumentation có thể khiến trace không đầy đủ. Khi thiết kế alert, phải biết tín hiệu có độ phủ và độ tin cậy đến mức nào.

## 3. Từ một exception đến alert: đường đi đúng

Một luồng phổ biến:

```text
User request / background job
               |
               v
        Java application
               |
          +----+----+
          |         |
          v         v
    Structured log  Counters/histograms
          |         |
          v         v
     Log collector  Metrics pipeline
          |         |
          +----+----+
               |
               v
     Query / aggregation / SLI
               |
               v
     Rule + window + thresholds
               |
               v
    Alert state: pending / firing
               |
               v
    Dedup + group + route + silence
               |
               v
       Notification / page
               |
               v
  Dashboard + logs + traces + runbook
```

Sơ đồ là **mô hình khái niệm**, không bắt buộc mọi kiến trúc phải gửi log qua cùng hệ thống với metrics. Một số công cụ có log-based alerts trực tiếp trên kho log, một số khác chuyển log thành metric rồi mới đánh giá; lỗi của hệ thống giám sát cần được quan sát riêng.

### 3.1. Ba nguyên tắc

1. **Phát hiện bằng tín hiệu ổn định:** request error rate, latency, backlog, queue lag, tỷ lệ job thất bại, trạng thái dependency hoặc số event bảo mật cần phản ứng.
2. **Điều tra bằng ngữ cảnh:** khi alert mở, truy vấn log/trace theo `service`, `operation`, `error_code`, `trace_id` (nếu phù hợp), deployment version và khoảng thời gian.
3. **Phản ứng có chủ sở hữu:** alert phải chỉ ra ai xử lý, mức khẩn cấp, ảnh hưởng người dùng, bước kiểm tra và cách giảm thiểu.

Không nên dùng việc tăng số dòng `ERROR` làm chỉ tiêu thành công của observability. Mục tiêu là phát hiện sự cố đúng, nhanh, ít nhiễu, và giúp xử lý an toàn.

## 4. Log-based alert: khi nào phù hợp?

**Log-based alert** tính toán một điều kiện từ bản ghi log đã thu thập: số lần có `event=job_failed` trong 10 phút, sự xuất hiện của mã `AUTH_INTEGRITY_VIOLATION`, hoặc tỷ lệ một error code trong các event đã parse.

Cách này hữu ích khi:
- Hệ thống chưa có metric riêng cho một sự kiện hiếm nhưng quan trọng.
- Có một **event code chuẩn hóa**, ví dụ `AUDIT_PIPELINE_WRITE_FAILED`, có thể truy vấn ổn định.
- Muốn phát hiện một chuỗi log mô tả trạng thái subsystem như failover kéo dài hoặc poison message.
- Có log pipeline đủ tin cậy và giới hạn độ trễ ingest đã biết.

Tuy nhiên, cần hiểu rõ rủi ro:

| Rủi ro | Tại sao làm alert sai? |
| --- | --- |
| **Log không đến sink** | Agent down, queue đầy, process crash hoặc network lỗi làm thiếu record |
| **Log ghi trùng** | Logger additivity, retry collector, duplicate delivery làm tăng count giả |
| **Sampling / rate limit** | Dòng log bị bỏ khiến bộ đếm khác số sự kiện thật |
| **Thay đổi text message** | Query dùng substring/regex bị phá khi developer đổi wording |
| **Log level thay đổi** | Event có thể không được ghi ở level cũ |
| **Lệch ingest time** | Sự kiện đến trễ, out-of-order, window bị tính sai |
| **Cardinality cao** | Group theo requestId/userId tạo nhiều alert instances |
| **Thiếu denominator** | “100 lỗi” không cho biết tỷ lệ lỗi khi tổng requests thay đổi |

**Giải pháp:** nếu dùng log alert, dựa vào `event_code`, `service`, `result` và schema được quản lý; kiểm soát duplicate ingest, no-data, và luôn phân biệt **event time** với **ingestion time**. Khi một tín hiệu là SLI quan trọng, thường nên phát **metric counter/histogram ngay tại nơi biết kết quả** và dùng log để điều tra.

## 5. Log ERROR không tự động là một page

Xem ba ví dụ:

**A. Một request bị lỗi ngẫu nhiên:**

```text
ERROR event=payment_dependency_failed errorCode=UPSTREAM_TIMEOUT
```

Chỉ một event chưa xác định được phạm vi tác động, tần suất hay khả năng hồi phục. Có thể ghi counter và trace để điều tra, nhưng page từng exception dễ gây alert fatigue.

**B. Tỷ lệ checkout thất bại trong 10 phút tăng mạnh:**

```text
metric: checkout_requests_total{result="error"} tăng liên tục
metric: checkout_requests_total{result="all"} vẫn có traffic
alert: CheckoutErrorBudgetBurn đang FIRING
```

Đây là mẫu hình tác động người dùng. Có thể đáng page nếu vi phạm chính sách SLO, đủ mức độ ảnh hưởng và có khả năng hành động.

**C. Hệ thống không còn xuất metric/log:**

```text
heartbeat: missing
scrape_target: unavailable
application log: không có dòng mới
```

“Không có ERROR” **không đồng nghĩa** hệ thống khỏe. Với service quan trọng, cần có alert về availability hoặc telemetry missing, được phân biệt với error rate bình thường.

### 5.1. Symptom-first, cause-second

**Symptom alert** phản ánh điều khách hàng nhận thấy: tỷ lệ lỗi cao, latency vượt mục tiêu, đơn hàng không tạo được hoặc dòng message backlog không được xử lý. **Cause alert** phản ánh nguyên nhân tiềm năng: database connection pool gần đầy, GC pause, disk usage, số retries tăng.

Một chính sách hiệu quả thường ưu tiên page theo **symptom có tác động**, còn cause signal hỗ trợ chẩn đoán hoặc ticket. Không có nghĩa loại bỏ toàn bộ cause alerts: một nguy cơ chắc chắn và có hậu quả nghiêm trọng như disk gần hết trước khi ghi audit, certificate sắp hết hạn hoặc queue không thể drain cũng có thể cần cảnh báo chủ động.

## 6. Thiết kế alert rule có ý nghĩa

Một rule tốt không chỉ có `count > 10`. Nó cần trả lời:

1. **Signal:** đo giá trị nào? Từ log, metric, synthetic check hay health signal?
2. **Scope:** service, environment, cluster, region hoặc tenant nào? Tránh nhãn có cardinality cao.
3. **Window:** xét khoảng thời gian nào, cách xử lý dữ liệu đến trễ ra sao?
4. **Threshold:** mức nào đáng lo dựa trên baseline/SLO/khả năng hành động?
5. **Persistence/for:** điều kiện phải giữ bao lâu để loại noise?
6. **Minimum volume:** khi traffic quá thấp, tỷ lệ phần trăm có đủ đáng tin không?
7. **Grouping/dedup:** nhiều instance hỏng cùng nguyên nhân có tạo một incident hay hàng trăm notification?
8. **Recovery:** khi nào alert resolve, có chống flapping/hysteresis?
9. **No-data:** không có mẫu vì service rảnh hay collector bị lỗi?
10. **Owner, severity, runbook:** ai xử lý, cần làm gì, ảnh hưởng gì?

### 6.1. Count, ratio và traffic

Ví dụ trong cùng một cửa sổ:
- 5 lỗi trên 10 requests tương đương 50% lỗi, nhưng sample nhỏ.
- 500 lỗi trên 100.000 requests tương đương 0,5%, nhưng số người bị ảnh hưởng lớn hơn.
- 0 dòng ERROR trong log không chứng minh error rate bằng 0 nếu logging bị drop.

Vì vậy, khi alert theo **error ratio**, cần một denominator rõ ràng, chính sách cho traffic thấp và metric đầy đủ. Một cảnh báo theo **absolute count** có thể phù hợp cho sự kiện hiếm cần xử lý từng lần, ví dụ dữ liệu audit không thể ghi; nhưng phải chỉ ra vì sao count thay cho ratio là có ý nghĩa.

### 6.2. Window, persistence và độ trễ

Đánh giá trên một cửa sổ 1 phút có thể nhạy nhưng dễ nhiễu; cửa sổ 30 phút ổn định hơn nhưng phát hiện chậm hơn. Nếu có `for: 10m`, điều kiện cần được quan sát liên tục theo logic của alert engine trước khi chuyển firing. Thời gian “10m” là cấu hình ví dụ, **không phải best practice chung** cho mọi alert.

Đừng quên:
- Dữ liệu đến trễ hoặc sampling có thể làm các window khác nhau.
- Timezone của dashboard không thay đổi sự cần thiết dùng timestamp nhất quán.
- Cách engine xử lý missing data/stale series ảnh hưởng tới PENDING/FIRING.
- Một query chạy mỗi 30s không đồng nghĩa luôn phản ứng đúng sau 30s.

### 6.3. Recovery và flapping

Nếu alert mở ở tỷ lệ lỗi `> 5%` rồi đóng ngay khi xuống 4,9%, giá trị dao động sát ngưỡng có thể liên tục mở/đóng. Có thể dùng:
- Khoảng điều kiện duy trì trước khi mở.
- Ngưỡng mở/đóng khác nhau (**hysteresis**).
- Window trung bình hoặc nhiều window.
- Cooldown, deduplication và grouping ở alert manager.
- Auto-resolve có kiểm tra dữ liệu thực, thay vì mặc định đóng khi telemetry mất.

Hysteresis không thay thế xem xét nguyên nhân; rule quá chậm có thể bỏ lỡ outage ngắn nhưng nghiêm trọng.

## 7. Alert theo SLI, SLO và error budget

Một **SLI** là chỉ số đo chất lượng được trải nghiệm, chẳng hạn tỷ lệ request thành công hoặc tỷ lệ request dưới ngưỡng latency. **SLO** đặt mục tiêu cho SLI trên một kỳ; **error budget** là phần không đạt được cho phép trong giới hạn mục tiêu đó.

Ví dụ **minh họa**, không phải SLO được áp dụng cho mọi dịch vụ:
- SLO thành công: **99,9%** trong 30 ngày.
- Error budget fraction: `1 - 0.999 = 0.001` (0,1% tổng eligible requests).
- Nếu error ratio thực tế trên một khoảng là **2%**, tốc độ tiêu thụ budget tương đương `0.02 / 0.001 = 20` lần mức bình quân cho phép trong khoảng đang xét.

**Burn rate** giúp liên hệ tỷ lệ lỗi với ngân sách cho phép, thay vì page theo một ngưỡng ngẫu nhiên. Thiết kế alert có thể kết hợp **multi-window, multi-burn-rate**: một window ngắn phát hiện sự cố nhanh, một window dài giảm nhiễu, và các cặp điều kiện phù hợp mức khẩn cấp khác nhau.

Lưu ý:
- SLI phải định nghĩa rõ mẫu số (**eligible requests**) và mẫu tử (**bad requests**). Không dùng “tổng log ERROR” làm mẫu tử nếu một request có nhiều log hoặc một request thất bại không in ERROR.
- Một status 4xx do input sai thường không tương đương lỗi dịch vụ trong availability SLI, nhưng định nghĩa phụ thuộc hợp đồng sản phẩm.
- Với latency SLI, không lấy trung bình không có trọng số của p95 từ nhiều instance rồi coi là p95 toàn hệ thống.
- Đặt SLO cho user-facing journey quan trọng trước, thay vì tự tạo SLO cho mọi dòng log.
- Burn rate threshold và window phải được thiết kế theo error budget policy; các con số trên chỉ để học công thức.

**Mối quan hệ:** Log hỗ trợ điều tra request cụ thể làm SLI xấu; SLO/burn-rate alert cho biết liệu tình trạng đó đáng đánh thức đội vận hành hay không.

## 8. Ví dụ Java 17 chạy độc lập: tách log sự kiện và vòng đời alert

Ví dụ sau dùng `java.util.logging` (JUL) thuộc JDK 17 và một bộ đánh giá giả lập. Nó có hai luồng hiển thị:
- `LOG INFO ...`: tóm tắt số request/lỗi theo từng cửa sổ cố định 1 phút.
- `ALERT OPEN/RESOLVED ...`: sự kiện thay đổi trạng thái cảnh báo. Đây **chỉ là in console**, **không gửi notification, không kết nối Alertmanager và không phải production alert engine**.

Quy tắc demo:
1. Chỉ đánh giá khi có ít nhất **20 requests** trong window.
2. Nếu lỗi từ **20% trở lên**, chuyển trạng thái từ inactive thành active và phát **một** alert OPEN.
3. Khi một window đủ traffic có tỷ lệ lỗi dưới 20%, chuyển từ active thành inactive và phát RESOLVED.
4. Nếu đã active và vẫn vi phạm, không gửi lại OPEN cho mỗi window.
5. Window dưới 20 requests **không tự mở/đóng alert**. Đây là lựa chọn minh họa, không thay thế no-data policy hoàn chỉnh.

Tạo file `LogAndAlertDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogAndAlertDemo {
    private record Window(int minute, long requests, long failures) {}

    private static final class PlainHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println("LOG " + record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    private static final class Evaluator {
        private final Logger logger;
        private boolean active;

        Evaluator(Logger logger) {
            this.logger = logger;
        }

        void evaluate(Window window) {
            logger.info("event=window_summary"
                    + " minute=" + window.minute()
                    + " requests=" + window.requests()
                    + " failures=" + window.failures());

            // Giả định số đo request/failure được tổng hợp chính xác.
            // Không có mẫu đủ lớn thì giữ nguyên trạng thái.
            if (window.requests() < 20) {
                return;
            }

            boolean unhealthy =
                    window.failures() * 100L >= window.requests() * 20L;

            if (unhealthy && !active) {
                active = true;
                System.out.println(
                        "ALERT OPEN rule=high_failure_ratio minute="
                                + window.minute());
            } else if (!unhealthy && active) {
                active = false;
                System.out.println(
                        "ALERT RESOLVED rule=high_failure_ratio minute="
                                + window.minute());
            }
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.observability.alert");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler handler = new PlainHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        try {
            Evaluator evaluator = new Evaluator(logger);
            evaluator.evaluate(new Window(0, 100, 2));
            evaluator.evaluate(new Window(1, 100, 25));
            evaluator.evaluate(new Window(2, 120, 30));
            evaluator.evaluate(new Window(3, 100, 1));
            evaluator.evaluate(new Window(4, 10, 5));
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac LogAndAlertDemo.java
java LogAndAlertDemo
```

**Stdout chính xác** khi chạy trong JVM mới, không có code khác can thiệp logger:

```text
LOG INFO event=window_summary minute=0 requests=100 failures=2
LOG INFO event=window_summary minute=1 requests=100 failures=25
ALERT OPEN rule=high_failure_ratio minute=1
LOG INFO event=window_summary minute=2 requests=120 failures=30
LOG INFO event=window_summary minute=3 requests=100 failures=1
ALERT RESOLVED rule=high_failure_ratio minute=3
LOG INFO event=window_summary minute=4 requests=10 failures=5
```

### 8.1. Diễn giải output

- **Phút 0:** 2/100 = 2%, dưới 20%; chỉ có LOG.
- **Phút 1:** 25/100 = 25%, vượt ngưỡng; chuyển trạng thái sang active, phát **một ALERT OPEN**.
- **Phút 2:** 30/120 = 25%; vẫn vi phạm nhưng alert đã active, **không tạo OPEN thứ hai**.
- **Phút 3:** 1/100 = 1%; đã đủ traffic và dưới ngưỡng, phát **ALERT RESOLVED**.
- **Phút 4:** 5/10 = 50% nhưng chỉ có 10 requests; demo xem dữ liệu ít, giữ trạng thái hiện có và không kích hoạt alert. Chính sách production có thể khác nếu 5 lỗi là sự cố nghiêm trọng của một dịch vụ ít traffic.
- `Logger.setUseParentHandlers(false)` ngăn root handler thêm timestamp/định dạng khác, làm stdout có thể so sánh cố định.
- `PlainHandler` tự in stdout cho mục đích học, không có queue/network, không phải appender production.
- `Alert OPEN/RESOLVED` là **dòng mô phỏng một action bên ngoài logger**, không phải vì gọi `logger.severe` mà mặc định hệ thống có pager.

### 8.2. Vì sao mẫu Java chưa phải alert engine production?

Hạn chế có chủ đích:
- Cửa sổ là các bản ghi `Window` đã tổng hợp; chương trình **không** đếm real HTTP requests, không xử lý dữ liệu đến trễ/out-of-order.
- Không có persistence cho `active`; restart sẽ quên trạng thái cảnh báo và có thể phát OPEN lại.
- Ngưỡng 20%/20 requests mang tính giảng dạy, không phản ánh SLO thực tế.
- Không có moving window, hysteresis, `for` duration, silence, routing, deduplication toàn cụm hoặc escalation.
- Nếu không nhận được window mới, demo **không biết telemetry đã hỏng**; cần no-data/missing heartbeat alert riêng.
- Không có label scope nhiều service, instance, region hoặc tenant; chỉ mô phỏng một rule duy nhất.
- Không bảo đảm các số đếm hợp lệ (ví dụ `failures <= requests`), cũng không chống overflow cho số long phi thực tế. Production cần nguồn metric đáng tin và xử lý validation.
- Dùng `System.out.println` mô phỏng alert không có ACK, retries hay notification delivery. Alertmanager hoặc platform tương đương mới thực hiện các bước này.

**Điểm học cốt lõi:** Nhiều log/bản tóm tắt không đồng nghĩa nhiều page; một rule cần **trạng thái và chính sách**. Đồng thời, log “ALERT OPEN” chỉ là một event, không chứng minh ai đã được thông báo thành công.

## 9. Tích hợp observability trong Java web service

### 9.1. Ghi log theo event code thay vì text tự do

Một log an toàn, có cấu trúc và dễ truy vấn:

```java
// Mảnh code tích hợp SLF4J: logger và biến đã được tạo trong ứng dụng.
logger.warn("event=dependency_failure service={} operation={} "
                + "dependency={} errorCode={} requestId={}",
        "checkout", "place_order", "payment-gateway",
        "UPSTREAM_TIMEOUT", safeRequestId);
```

Đây **không phải chương trình độc lập**. `safeRequestId` phải do server sinh/được xác minh và giới hạn độ dài/ký tự, không dùng raw header tùy ý. Không ghi raw request body, Authorization bearer token, session ID hay payment card details.

Nếu muốn alert từ log, nên query `event=dependency_failure` và `errorCode=UPSTREAM_TIMEOUT` sau khi parser kiểm tra schema, **không** dùng search phrase “failed!” vốn đổi theo ngôn ngữ hoặc exception message.

Nhưng **một dependency failure log chưa chắc tương đương một request cuối cùng thất bại**. Nếu retry thành công, log attempt-level vẫn có nhưng request-level failure metric không tăng. Đây là một lý do không lấy số `WARN`/`ERROR` làm SLI user-facing.

### 9.2. Phát metrics ở ranh giới có kết quả cuối

Trong ứng dụng web Java, middleware/filter/observation layer thường biết HTTP status, duration và route template. Mã ứng dụng nên tạo:
- Counter cho eligible requests theo service/route nhóm/status class hoặc outcome đã chuẩn hóa.
- Counter request thất bại theo **định nghĩa SLI**.
- Histogram latency hoặc hệ thống đo distribution tương ứng.
- Counters cho retry, dependency failures, circuit breaker và logging pipeline health.

Nếu dùng Micrometer/Spring Boot, tên meter và các tag sẵn có **phụ thuộc stack và phiên bản**. Không giả định mọi ứng dụng đều có `http_requests_total` hoặc `outcome=error` như ví dụ rule bên dưới. Hãy **xác minh metric xuất thực tế** trước khi cấu hình alert.

Một API có thể trả 4xx do người dùng nhập sai, không nên tính vào availability SLI nếu hợp đồng SLI loại trường hợp đó. Với batch/message consumer, kết quả cuối có thể là record committed, message acknowledged, DLQ hoặc backlog; không đánh giá như HTTP request nếu semantics khác.

### 9.3. Structured fields với SLF4J 2.x

```java
// Mảnh tích hợp SLF4J 2.x + backend/encoder hỗ trợ key-value.
logger.atError()
      .addKeyValue("event", "operation_failed")
      .addKeyValue("service", "checkout")
      .addKeyValue("operation", "place_order")
      .addKeyValue("error_code", "PAYMENT_DEPENDENCY_UNAVAILABLE")
      .addKeyValue("request_id", safeRequestId)
      .log("Checkout operation failed");
```

`atError()` không tự gửi alert. Các key-value chỉ xuất theo cấu hình backend/encoder. Nếu muốn stack trace, cân nhắc thông tin exception message/cause có thể chứa credential/PII; không đính kèm throwable vào mọi log chỉ vì alert đang firing.

### 9.4. Correlation từ alert về log/trace

Giả sử alert `CheckoutHighErrorRatio` chứa labels `service=checkout`, `environment=prod`, `region=ap-southeast`:
- Mở dashboard với đúng service/environment/region và khoảng thời gian alert.
- Kiểm tra mã lỗi phân bố và version vừa deploy.
- Lọc logs theo `service=checkout` và `error_code`; dùng sample `requestId`/`traceId` **trong log/trace**, không đưa ID duy nhất vào alert label.
- So sánh latency, saturation, dependency errors và thay đổi traffic.
- Từ trace sample, xác định bottleneck tại payment gateway, database hay lỗi local.

**Label group theo request ID/user ID là sai tầng:** nếu 10.000 requests cùng lỗi, một rule sẽ tạo hàng nghìn alert instances. Giữ label dùng để route ở mức **đơn vị có người chịu trách nhiệm**, và giữ ID có cardinality cao trong log/trace.

## 10. Rule minh họa: Prometheus/Alertmanager style

Ví dụ YAML dưới đây **giả định** ứng dụng đã xuất counter `http_requests_total` với nhãn `service` và `result`, trong đó `result="error"` được định nghĩa đúng cho SLI cần đo. Đây không phải tên metric mặc định chắc chắn có ở mọi Java framework.

```yaml
groups:
  - name: checkout-sli
    rules:
      - alert: CheckoutHighErrorRatio
        expr: |
          (
            sum(rate(http_requests_total{service="checkout",result="error"}[5m]))
            /
            clamp_min(
              sum(rate(http_requests_total{service="checkout"}[5m])),
              0.001
            )
          ) > 0.05
          and
          sum(rate(http_requests_total{service="checkout"}[5m])) > 1
        for: 10m
        labels:
          severity: page
          team: checkout
        annotations:
          summary: "Checkout error ratio elevated"
          description: "Investigate checkout outcome and dependency errors"
          runbook_url: "https://example.test/runbooks/checkout-errors"
```

**Không sao chép rule vào production rồi coi nó đã được xác nhận.** Cần hiểu:
1. **Metric names/labels là giả định.** Nếu tên thật khác hoặc `result="error"` không có ở counter tương ứng, expression có thể trả dữ liệu rỗng.
2. `rate(...[5m])` ước lượng tốc độ tăng counter trong 5 phút, không phải tổng số request tuyệt đối. Counter có thể reset, scrape có thể thiếu.
3. Chia cho tổng request rate giúp đánh giá ratio. `clamp_min(...,0.001)` chống chia gần 0, còn vế `>1` là **điều kiện traffic** (đơn vị requests/giây) để tránh page ở lưu lượng cực thấp.
4. `>0.05` nghĩa là hơn 5% lỗi trong cửa sổ; đây là **ngưỡng giả định**, phải khớp nhu cầu/SLO thực tế.
5. `for: 10m` yêu cầu điều kiện được duy trì theo semantics của rule evaluator trước khi trở thành FIRING; không phản ánh độ trễ end-to-end đảm bảo.
6. `severity: page` chỉ là label routing. Nếu Alertmanager/chính sách notification không được cấu hình, label này **không tự gửi SMS hoặc gọi điện**.
7. URL runbook dùng domain ví dụ `example.test`, không phải một runbook đang tồn tại.
8. Rule này chưa có no-data alert, SLO burn-rate, multi-window, regional scoping, inhibition hay xử lý telemetry missing.
9. SLI nên thống nhất nhãn và mẫu số giữa hai counter; không trộn nhiều loại traffic không tương đương.

### 10.1. Alert từ log event trực tiếp

Nếu công cụ log aggregation hỗ trợ, có thể định nghĩa query dạng **pseudocode trung tính**, không phải cú pháp SQL/PromQL chuẩn:

```text
SOURCE = structured_logs
FILTER service == "audit-api"
   AND event == "audit_write_failed"
GROUP BY environment, service
WINDOW = last 5 minutes
CONDITION count > 0
ACTION route to security/on-call with event reference
```

Một event như `audit_write_failed` có thể đáng alert ngay vì liên quan mất dấu vết bắt buộc, nhưng chỉ khi event semantics bảo đảm không phải retry đã được phục hồi và log pipeline có độ tin cậy phù hợp. Nếu chính nơi ghi audit/log lỗi hoàn toàn, nó có thể **không phát event**; cần health/synthetic monitoring độc lập.

## 11. Alert lifecycle: pending, firing, acknowledged, resolved

Một alert rule có thể có trạng thái nội bộ của evaluator và trạng thái xử lý incident:

```text
NORMAL
  |
  | điều kiện vi phạm
  v
PENDING
  |
  | đủ thời gian/persistence
  v
FIRING ---> notification routed
  |              |
  |              v
  |          ACKNOWLEDGED / OWNED
  |              |
  |         investigate / mitigate
  |
  | điều kiện phục hồi
  v
RESOLVED
```

Tùy công cụ, các tên trạng thái khác nhau; **ACKNOWLEDGED không phải trạng thái phổ quát của Prometheus rule** mà thường thuộc hệ thống quản lý thông báo/incident. `RESOLVED` cũng không nhất thiết chứng minh nguyên nhân đã được sửa hoàn toàn, chỉ rằng điều kiện của rule không còn firing theo dữ liệu sẵn có.

Các khái niệm:
- **Pending:** điều kiện vi phạm nhưng chưa đủ thời gian để mở.
- **Firing:** rule thỏa logic kích hoạt.
- **Notification delivered:** công cụ gửi thông báo; có thể bị trễ, lỗi hoặc bị silence.
- **Acknowledged:** người/nhóm đã tiếp nhận incident trong workflow tương ứng.
- **Resolved:** điều kiện rule đã không còn đúng theo logic đánh giá.
- **Silenced/muted:** notification bị chặn theo chính sách; không đồng nghĩa vấn đề đã biến mất.
- **Inhibited:** alert thứ cấp được ngăn khi alert gốc cùng phạm vi đang firing.

**Không thiết kế alert làm thay đổi behavior nghiệp vụ chỉ vì có notification.** Một rule phục vụ con người không thay thế circuit breaker, retry budget, rate limit, transaction rollback hoặc failover của ứng dụng.

## 12. Grouping, deduplication, routing và escalation

Ví dụ một lỗi database gây 200 pods cùng thấy timeout. Nếu mỗi pod tạo một page, on-call có thể bị ngập và khó nhận diện root cause.

**Grouping** gộp các alert cùng service/environment/incident signal để hiển thị một nhóm có ích. **Deduplication** tránh gửi cùng một alert instance lặp vô hạn. **Inhibition** hạn chế alert downstream khi đã có root alert chắc chắn liên quan. **Routing** đưa alert tới đúng đội.

| Chính sách | Mục đích | Ví dụ |
| --- | --- | --- |
| Group by `service,environment,alertname` | Một sự cố nhìn thành một nhóm | 50 pods checkout cùng high error ratio |
| Dedup theo fingerprint/labels ổn định | Không tạo incident mới khi rule vẫn firing | Một alert instance được update |
| Inhibit downstream | Giảm alert phụ khi root outage đã rõ | DB unavailable gây nhiều API failures |
| Escalation | Người trực không phản hồi thì chuyển cấp | On-call sơ cấp → backup |
| Silence có hạn | Bảo trì có kế hoạch, không spam notification | Silence một deployment window |
| Routing theo team/severity | Đúng người xử lý | Page cho user-facing outage, ticket cho nonurgent |

**Bẫy:** Group quá rộng có thể che hai sự cố độc lập; group quá hẹp biến một outage thành hàng nghìn trang. Không dùng request ID, user ID, event ID, full exception message hoặc pod UID làm group key mặc định nếu làm tăng cardinality vô hạn.

Đặt owner cho mỗi rule; khi service đổi đội, cập nhật routing và runbook. Một alert không ai sở hữu có thể nguy hiểm như không có alert.

## 13. Viết alert notification có thể hành động

Một thông báo tốt cần trả lời ngắn gọn:
- **Điều gì đang bị ảnh hưởng?** Dịch vụ, môi trường, khu vực, user journey.
- **Mức tác động và độ tin cậy?** Error ratio, request volume, latency, backlog, ngưỡng.
- **Kể từ khi nào?** Time window, thời điểm firing, tình trạng hiện tại.
- **Hành động đầu tiên?** Kiểm tra dashboard, rollback, dependency status hoặc đánh giá SLO.
- **Đi đâu để tìm bằng chứng?** Link dashboard/log query/trace sample và runbook.
- **Ai chịu trách nhiệm?** Team và escalation policy.

Ví dụ nội dung minh họa:

```text
CheckoutHighErrorRatio [PROD] — FIRING
Impact: checkout 5xx/error ratio over threshold for 10m
Scope: service=checkout, region=ap-southeast
Evidence: dashboard checkout SLI; errors by code; recent deploys
Next: check payment dependency, new version, rollback criteria
Owner: checkout on-call | Runbook: internal/checkout-errors
```

Không đính kèm toàn bộ request body, access token hoặc stack trace chứa bí mật vào Slack, email, SMS hoặc ticket. Notification cũng là **một sink dữ liệu**, có retention và quyền truy cập riêng. Chỉ đưa labels và sample metadata đã được phân loại an toàn.

### 13.1. Runbook phải thật sự hữu ích

Một runbook tốt có:
1. Diễn giải ý nghĩa rule và cách kiểm tra nó đang firing thật hay là telemetry lỗi.
2. Query/dashboard đã kiểm chứng, cùng khoảng thời gian và labels.
3. Các bước triage theo thứ tự tác động: user impact, recent deploy, dependency, saturation, logs/traces.
4. Hành động giảm thiểu an toàn (rollback feature, giảm tải, bypass dependency) cùng **điều kiện và quyền thực hiện**.
5. Tiêu chí xác nhận phục hồi, không chỉ “không còn notification”.
6. Escalation và nơi ghi nhận postmortem.
7. Giới hạn bảo mật, không copy raw secret từ log vào chat/ticket.

Nếu alert không dẫn đến một hành động hoặc quyết định cụ thể, xem xét **giảm severity, chuyển thành dashboard/ticket hoặc bỏ rule**.

## 14. Alert cho hệ thống message và background jobs

Ở consumer Kafka/RabbitMQ/SQS hoặc job scheduler, “một exception” thường không tương đương outage. Hãy đo **kết quả cuối và tiến độ xử lý**:

- **Queue lag/backlog:** số message chưa xử lý/tốc độ xử lý giảm theo SLA.
- **Oldest message age:** độ trễ thực so với yêu cầu nghiệp vụ.
- **Processing failure ratio:** thất bại trên số attempt/unique messages theo semantic đã chọn.
- **DLQ rate/depth:** message vào dead-letter queue hoặc bị loại sau retry.
- **Idempotency duplicates:** số delivery lặp; tăng có thể chỉ ra ack/commit/rebalance có vấn đề.
- **Job missed deadline:** task không hoàn tất theo lịch, dù không có exception.
- **Consumer liveness:** không còn xử lý message khi queue có backlog, thay vì chỉ dựa vào log ERROR.

Khi một message bị giao lại 10 lần, listener có thể ghi 10 dòng warning và một final failure. Nếu alert dựa vào số log warning, nó có thể **khuếch đại tác động của một logical message**. Chọn denominator rõ ràng: attempt failures, unique messages failed hay number of business operations unsuccessful. Mỗi định nghĩa phục vụ một loại alert khác nhau.

Đừng đưa payload message, cookie, credentials hay full headers vào alert. Dùng `eventId` cho trace/log điều tra ở nơi có quyền truy cập; không dùng làm alert label.

## 15. Alert cho lỗi của logging/observability pipeline

Bản thân hệ thống observability có thể hỏng:
- Appender ghi file thất bại.
- Async logging queue đầy và drop event.
- Collector backlog tăng hoặc không gửi được batch.
- Storage/index không sẵn sàng hoặc chi phí/retention vượt giới hạn.
- Scrape target down; metric series biến mất.
- Alert evaluator ngừng chạy hoặc notification delivery thất bại.

Cần **meta-monitoring** hoặc giám sát độc lập cho đường telemetry quan trọng. Ví dụ các chỉ số ổn định:
- `log_events_dropped_total` và queue depth.
- Collector ingest errors, export retries, backlog.
- `up` hoặc health/synthetic checks cho scrape targets nếu dùng Prometheus.
- Alertmanager/notification delivery failures, rule evaluation errors.
- Số lần audit write thất bại tại sink bền vững nếu audit bắt buộc.

Đặc biệt, một rule `count(log ERROR) == 0` không chứng minh hệ thống an toàn. Nếu appender chết, log count cũng bằng 0. Dùng heartbeat/synthetic checks từ góc quan sát độc lập để phát hiện “im lặng bất thường”.

**Đừng log lỗi appender qua chính appender đang hỏng** vì có thể gây đệ quy. Dùng status logger/internal diagnostics và metrics/health channel riêng, có rate limit và failure isolation.

## 16. Bảo mật và quyền riêng tư của log-driven alerts

Log và alert có thể chứa dữ liệu cá nhân, định danh người dùng hoặc bí mật hệ thống. Một exception có thể in raw URL chứa API key; một alert tạo từ raw log có thể chuyển chuỗi đó tới email, điện thoại và hệ thống quản lý incident.

Các nguyên tắc:
1. **Không ghi secret vào log ngay từ nguồn**: password, token, Cookie, private key, signed URL, raw request body hoặc PII không cần thiết.
2. Chỉ cho phép field an toàn trong alert labels và annotations: service, environment, error code, aggregate SLI, runbook link.
3. Đặt quyền đọc, truy vấn, export và retention riêng cho logs, dashboards, alert history và incidents.
4. Không dùng raw exception message làm `alertname`, label hoặc dedup key; đây có thể là dữ liệu nhạy cảm và cardinality cao.
5. Redaction ở collector/alert template là defense in depth; nếu log thô đã được gửi, masking trên dashboard không bảo vệ các sink trước.
6. Hạn chế detail theo kênh notification; SMS/push thường chỉ cần tóm tắt và link đến hệ thống có xác thực.
7. Coi các log chứa user identifiers, IP, session reference hoặc resource ID là dữ liệu phải được đánh giá quyền riêng tư và thời gian lưu.
8. Khi phát hiện credential lọt vào log/alert, áp dụng incident response, revoke/rotate theo chính sách và rà soát mọi bản sao downstream.

**Alert query cũng có thể làm lộ dữ liệu** nếu dùng một label giá trị tự do từ user input. Hãy chuẩn hóa và giới hạn field trước khi đưa vào event.

## 17. Kiểm thử alert: không chỉ kiểm thử Java code

Một alert production cần được kiểm chứng trên toàn tuyến:

| Kiểm thử | Điều cần xác nhận |
| --- | --- |
| Error tăng vượt ngưỡng | Rule pending/firing đúng, đủ persistence |
| Error ngắn rồi phục hồi | Không tạo false page ngoài chính sách |
| Traffic thấp | Minimum sample/volume policy rõ, không chia zero |
| Không có traffic | Phân biệt service rảnh với telemetry mất |
| Logging pipeline drop/duplicate | Log-based alert không suy luận sai số sự kiện |
| Metric counter reset | Query rate hoạt động hợp lý |
| Late/out-of-order ingestion | Window và timestamp semantics được xác nhận |
| Nhiều pods cùng lỗi | Alert grouping tránh page storm |
| Một request nhiều exception logs | Không đếm thành nhiều failed requests |
| Retry thành công | Attempt metric tăng nhưng user-facing error SLI không bị đội lên |
| Alert liên tục vi phạm | Dedup/cooldown không gửi notification vô hạn |
| Alert phục hồi sát ngưỡng | Không flapping quá mức |
| Primary on-call không ACK | Escalation hoạt động theo chính sách |
| Silence trong bảo trì | Silence đúng thời hạn, không che sự cố ngoài phạm vi |
| Notification endpoint down | Có cảnh báo/meta-monitoring và retry phù hợp |
| Service bị deploy/scale | Label routing và SLI không mất coverage |
| Secret giả trong error message | Không xuất ra alert annotation, email, push, ticket |
| Runbook/links | Dashboard và query có dữ liệu đúng scope/time window |

### 17.1. Thử alert bằng tín hiệu tổng hợp

Một chiến lược là phát metric/log **từ test environment**, có gắn tag được kiểm soát và sử dụng event code giả; không cần gây outage thật:
1. Xác minh baseline khi hệ thống khỏe.
2. Tạo một khoảng có lỗi vượt ngưỡng ở staging (hoặc rule test engine).
3. Quan sát PENDING rồi FIRING, thông báo đến **test route**, không đánh thức production on-call.
4. Cho tín hiệu phục hồi, kiểm tra RESOLVED.
5. Kiểm thử thiếu dữ liệu, collector lỗi, metric reset và duplicate ingest.
6. Xác minh runbook, owner, route và các liên kết đến log/trace.
7. Ghi nhận false positive/negative trong alert review và điều chỉnh rule có lý do.

**Không phá database/file production chỉ để test alert.** Với Prometheus style, có thể unit test rule với dữ liệu tổng hợp nếu hệ thống cung cấp công cụ phù hợp; không nhất thiết chạy một outage thật.

### 17.2. Đánh giá chất lượng alert theo thời gian

Theo dõi:
- Tỷ lệ alert có hành động thực sự và tỷ lệ noise.
- MTTD (thời gian phát hiện), MTTA (thời gian ACK), MTTR (thời gian phục hồi) theo định nghĩa rõ.
- Tỷ lệ false pages, notification volume theo on-call, escalation effectiveness.
- Tỷ lệ incidents bị bỏ sót hoặc chỉ phát hiện qua khách hàng.
- Alert coverage cho các user journeys/SLO quan trọng.
- Số rule không có owner/runbook hoặc không còn dữ liệu.

Không biến mục tiêu “giảm số alerts” thành việc **tắt mọi cảnh báo**; chất lượng phải cân đối khả năng phát hiện và chi phí gây phiền nhiễu.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Mỗi `logger.error` gửi page | Alert storm; một request có nhiều errors | Đánh giá SLI/impact, dùng rule và window |
| Đếm raw log lines làm số request lỗi | Log duplicate/sampling/drop làm méo số liệu | Dùng metric request outcome hoặc event identity đúng |
| Query từ substring message | Wording thay đổi; exception chứa dữ liệu tự do | Event code, structured fields, schema version |
| Chỉ đặt ngưỡng count | Traffic thay đổi, thiếu denominator | Rate/ratio + volume và policy phù hợp |
| Chỉ đặt ngưỡng ratio | 1 lỗi/1 request = 100% trên sample rất nhỏ | Minimum volume, multi-window hoặc rule riêng |
| Không có `for` hoặc persistence | Alert flapping khi metric nhiễu | Duration/window/hysteresis theo SLO |
| Đóng alert ngay khi mất telemetry | Có thể che outage thật | No-data/missing telemetry policy |
| Group theo requestId/userId | Hàng nghìn alert instances, cardinality cao | Label ổn định theo service/environment |
| Một error ở dependency làm page mọi callers | Nhiều notifications cùng root cause | Symptom-first, grouping/inhibition |
| Gọi INFO/WARN là không quan trọng | Impact có thể lớn dù log level thấp | Severity theo user impact và policy |
| Tin `ERROR` đồng nghĩa operation failed | Retry thành công vẫn có log attempt failed | Tách attempt-level và final outcome |
| Gửi stack trace/secret vào SMS/chat | Rò rỉ dữ liệu qua alert sink | Metadata an toàn, link truy cập có xác thực |
| Chỉ giám sát application logs | Collector down có thể khiến không còn log | Meta-monitoring, synthetic/heartbeat |
| Không có owner/runbook | Không ai biết xử lý | Gắn team, routing, triage steps |
| Silence không thời hạn | Che sự cố mới | Silence có scope/expiry/approval |
| Dùng rule demo làm production SLO | Ngưỡng không phản ánh hệ thống | Calibration bằng baseline/SLO và incident history |
| Coi log ALERT OPEN là đã page | Không có notification delivery guarantee | Theo dõi alert manager và incident acknowledgment |

## 19. Bài tập và đáp án

**Bài 1.** Một Java service log 100 dòng `ERROR` cho 10 requests thất bại, vì mỗi request retry 10 lần. Nếu log-based alert đếm `ERROR > 50`, điều gì sai?

**Đáp án:** Rule đo **số attempts/log statements**, không phải số requests cuối cùng thất bại. Dùng counter outcome sau retry hoặc định nghĩa alert riêng cho retry pressure; không suy ra 100 failed user requests.

**Bài 2.** 1 lỗi/2 requests trong 5 phút tạo error ratio 50%. Có nên page ngay?

**Đáp án:** Chưa đủ để quyết định. Cần xét minimum traffic, mức nghiêm trọng, SLO, user impact và lịch sử; với nghiệp vụ ít traffic nhưng cực quan trọng, một absolute failure alert riêng có thể đúng hơn.

**Bài 3.** Một alert vẫn FIRING nhưng không ai nhận được Slack notification. Có phải lỗi Java logging?

**Đáp án:** Không nhất thiết. Cần kiểm tra routing, grouping, silence, notification provider, credentials/quota và Alertmanager/incident system. `FIRING` và `notification delivered` là hai trạng thái khác nhau.

**Bài 4.** Application log trống hoàn toàn trong khi người dùng báo không truy cập được. Có thể kết luận error rate bằng 0 không?

**Đáp án:** Không. Service hoặc logging pipeline có thể đã ngừng, collector bị lỗi, hoặc requests không đến được service. Dùng uptime/synthetic check và meta-monitoring.

**Bài 5.** Log collector gửi một batch hai lần sau timeout; alert query đếm từng document như một error. Điều gì xảy ra?

**Đáp án:** Có thể tạo false positive hoặc tăng severity giả. Cần hiểu ingestion semantics, event identity/dedup nếu phù hợp, hoặc dùng metric outcome từ nguồn đáng tin hơn.

**Bài 6.** Một alert có labels `service=checkout, request_id=req-123`. Khi 10.000 requests lỗi, vấn đề gì?

**Đáp án:** `request_id` tạo cardinality cao và nhiều alert instances; không phù hợp làm routing/dedup label. Để ID trong log/trace; alert theo service/env/operation có owner.

**Bài 7.** Trong demo Java, phút 2 có 30 lỗi/120 requests, vì sao không tạo thêm `ALERT OPEN`?

**Đáp án:** Rule đang active từ phút 1; demo chỉ in OPEN khi chuyển inactive → active. Trong hệ thống thật, alert manager đảm nhận dedup và notification repeat interval riêng.

**Bài 8.** Một team muốn alert “disk sử dụng 80%”. Cần hỏi gì trước khi gắn severity page?

**Đáp án:** Tốc độ tăng, còn bao nhiêu thời gian tới mức nguy hiểm, disk phục vụ chức năng nào, có auto-cleanup, có tác động user/audit khi đầy, thời gian phản ứng cần thiết và owner/runbook. Threshold 80% không tự xác định tính khẩn cấp.

## 20. Checklist thiết kế Log và Alert

1. **Tách log và alert:** logger call không đồng nghĩa notification hay incident.
2. Chọn tín hiệu phù hợp: metrics/SLI cho tác động tổng thể, structured log cho event đặc thù và truy vết, trace cho chuỗi xử lý.
3. Rule có scope, window, threshold, persistence, minimum volume, recovery và no-data policy.
4. SLI xác định đúng eligible requests/bad requests, không tính trùng retry và không suy từ số raw ERROR lines.
5. Severity theo user impact và khả năng hành động, không chỉ theo log level.
6. Labels cardinality thấp; request ID/event ID ở log/trace, không làm group key.
7. Có grouping, deduplication, inhibition, routing, escalation và silence có hạn.
8. Alert có owner, dashboard, runbook, link log/trace, thông tin rõ ràng nhưng không chứa bí mật.
9. Có meta-monitoring cho agent/collector/metrics/alert manager; mất dữ liệu không bị coi là HEALTHY.
10. Kiểm thử rule với traffic thấp/cao, retry, log duplicate, metric missing, recovery, notification fail và nhiều instances.
11. Có metrics chất lượng alert (MTTD, false pages, missed incidents, noise) và chu kỳ review.
12. Alert quan trọng được thiết kế theo SLO/error budget, không copy ngưỡng minh họa một cách máy móc.
13. Audit/security events có policy lưu trữ và alert riêng; không sampling mù quáng sự kiện bắt buộc.
14. Khi xảy ra sự cố, điều tra bằng một **correlation workflow** rõ ràng: alert → dashboard → log → trace → dependency → remediation.

**Kết luận:** Trong Observability, **log ghi lại sự kiện; alert chuyển tín hiệu có ý nghĩa thành yêu cầu hành động**. Một hệ thống Java tốt không page theo mỗi `ERROR`, cũng không tự tin rằng không có log đồng nghĩa không có sự cố. Hãy xây dựng event schema ổn định, dùng SLI/metrics và log ở đúng mục đích, định nghĩa rule dựa trên tác động và thời gian, có xử lý alert lifecycle/no-data/dedup, rồi kiểm thử cả tuyến notification. Nhờ vậy đội vận hành vừa phát hiện sự cố cần xử lý, vừa có log và trace đủ tin cậy để tìm nguyên nhân mà không bị nhiễu hoặc rò rỉ dữ liệu.