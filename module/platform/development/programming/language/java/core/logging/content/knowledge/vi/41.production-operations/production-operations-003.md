# Theo dõi lỗi ghi log trong Java Core Logging

## Mục tiêu học tập

Bài học thuộc nhóm **Vận hành production**, với chủ đề **Theo dõi lỗi ghi log**. Logging là công cụ quan sát hệ thống, nhưng **bản thân đường logging cũng có thể hỏng**. Ứng dụng vẫn chạy và trả HTTP 200 trong khi appender không thể ghi file, async queue lặng lẽ loại event, stdout bị nghẽn, log agent không đẩy được dữ liệu hoặc collector nhận được nhưng index không lưu. Nếu chỉ tìm thông báo lỗi trong chính log pipeline đang hỏng, người vận hành có thể hoàn toàn không nhìn thấy cảnh báo.

Bài này hướng dẫn xây dựng khả năng **tự giám sát logging pipeline** từ JVM tới hệ thống tìm kiếm, phân biệt lỗi ghi log với lỗi nghiệp vụ, phát hiện log bị mất/đến trễ, và thiết kế cơ chế cảnh báo độc lập, đáng tin.

Sau bài này, bạn có thể:

- Phân biệt **lỗi tại logger/formatter**, **lỗi appender/handler**, **queue overflow**, **stdout/file**, **agent/collector**, **backend/index** và **lỗi truy vấn**.
- Xác định ranh giới của các chỉ số: `log call`, `event eligible`, `event accepted`, `write attempted`, `write succeeded`, `collector acknowledged`, `searchable`.
- Theo dõi cảnh báo từ `java.util.logging.ErrorManager`, Logback status, Log4j 2 status, metrics của agent/collector và tín hiệu hạ tầng.
- Viết chương trình **Java 17 độc lập** mô phỏng lỗi write/flush, thu nhận sự kiện lỗi qua ErrorManager và chứng minh không nhầm “logger đã gọi” với “đã ghi thành công”.
- Thiết kế metrics, dashboard và cảnh báo theo lỗi, độ trễ, backlog và khối lượng log bất thường.
- Sử dụng **canary log** và đối chiếu end-to-end để phát hiện mất log im lặng, kể cả lúc logging system không tự báo lỗi.
- Xử lý sự cố production với runbook an toàn: bảo vệ dữ liệu audit, tránh recursion, không tùy tiện tắt TLS hoặc phát tán log nhạy cảm.
- Kiểm thử failure injection và hồi phục: disk full, permission, rotation, agent crash, queue full, collector outage, index lag và shutdown.

**Nguyên tắc quan trọng:** Một log event đã được tạo, đã enqueue hoặc thậm chí appender trả về **không tự chứng minh** dữ liệu đã được lưu bền vững và có thể truy vấn. Theo dõi lỗi ghi log cần quan sát các ranh giới khác nhau và có **kênh giám sát độc lập** với chính log pipeline.

## 1. Thế nào là “lỗi ghi log”?

Các sự cố thường được gọi chung là “log không lên” nhưng nguyên nhân rất khác nhau:

| Hiện tượng | Ví dụ | Tầng cần xem đầu tiên |
| --- | --- | --- |
| Không có event được tạo | Effective log level đang chặn DEBUG hoặc filter `DENY` | Logger level, filter, cấu hình profile |
| Có event nhưng appender không ghi được | File thiếu quyền, disk full, encoder exception | Handler/Appender, filesystem, status diagnostics |
| Producer bị chặn khi logging | Sync write chậm, async queue full và policy block | Thread dump, caller latency, queue occupancy |
| Event bị drop ở async queue | Queue full, discarding policy | AsyncAppender/AsyncLogger metrics và policy |
| Đã ghi stdout/file nhưng agent không đọc | Agent down, sai glob/path, container driver lỗi | File/stdout, log shipper |
| Agent đọc được nhưng không gửi | TLS handshake, auth token, network timeout, retry backlog | Agent exporter, network, collector endpoint |
| Collector nhận nhưng không xử lý | Parser reject, transform/filter loại event, quota | Collector pipeline và rejection counters |
| Backend nhận nhưng chưa searchable | Indexing lag, shard reject, retention/permission | Storage/index/query |
| Tìm không thấy do truy vấn sai | Sai namespace, timezone, query filter hoặc quyền đọc | Search/query layer |
| Log xuất trùng | Root additivity, file + stdout cùng ingest, retry không idempotent | Routing và event ID |

**Lỗi ghi** khác **log bị lọc có chủ đích**. Nếu INFO bị sampling 10%, phần còn lại mất khỏi index theo chính sách, không được báo là “90% ghi lỗi”. Ngược lại, event đã được sampler chọn nhưng bị async queue drop không được gộp vào `sampled_out`. Phải tách rõ các counter để báo cáo trung thực.

### Bốn trạng thái thường bị đánh đồng

```text
logger called
    |
    v
event admitted / sampled-in
    |
    v
appender/queue accepted
    |
    v
sink write completed
    |
    v
shipper / collector acknowledged
    |
    v
backend durable / searchable
```

Đây là sơ đồ khái niệm; một kiến trúc cụ thể có thể không có tất cả các bước. “Write completed” có thể chỉ là một syscall hoặc thư viện đã flush buffer, **không nhất thiết fsync xuống disk**. HTTP 2xx từ collector có thể có nghĩa “received” chứ chưa “indexed”. Mỗi hop cần định nghĩa **thế nào là thành công** trước khi chọn metric và SLO.

## 2. Vẽ toàn bộ đường đi của log trước khi giám sát

Ví dụ kiến trúc Java trong container:

```text
Java logger
   |
   +-- Logback / Log4j2 / JUL handler
   |         |
   |         +-- sync/async queue, encoder, filters
   |
   v
stdout or application log file
   |
   v
container runtime / node filesystem
   |
   v
log shipper / agent
   |
   v
gateway / collector
   |
   +-- authentication / parser / filter / batching
   |
   v
message broker / ingest service
   |
   v
index / storage / query / alert
```

Một hệ thống khác có thể dùng appender gửi HTTP/gRPC trực tiếp, broker trước collector hoặc multi-region forwarding. Không áp checklist “collector” máy móc vào ứng dụng chỉ có file local; thay vào đó, vẽ **đúng đường thật** của từng loại log.

Theo dõi mỗi hop bằng hai chiều:

1. **Positive:** event đi qua hop và được chấp nhận theo contract.
2. **Negative:** không bị loại sai tuyến, không trùng, không bị rò sang sink ít bảo mật hơn.

Nếu service có hai route (application console và security audit), cần tách các SLI; một dashboard chỉ nhìn tổng volume có thể không nhận thấy **đường audit đã ngừng** nhưng console vẫn hoạt động.

## 3. Phân loại lỗi ở Java logging framework

### 3.1. java.util.logging (JUL)

Trong JDK, `java.util.logging.Logger` phát `LogRecord` tới `Handler`. Một `Handler` có thể từ chối event do level/filter, format sai, ghi tới file/socket/console hoặc ném/ghi nhận lỗi tùy implementation.

JUL cung cấp `java.util.logging.ErrorManager` và phương thức bảo vệ `Handler.reportError(...)`. Custom Handler có thể báo các mã lỗi thông dụng:

| Mã ErrorManager | Ý nghĩa khái quát |
| --- | --- |
| `GENERIC_FAILURE` | Lỗi chung của handler |
| `WRITE_FAILURE` | Không thể ghi thông tin |
| `FLUSH_FAILURE` | Không thể flush dữ liệu |
| `CLOSE_FAILURE` | Không thể đóng tài nguyên |
| `OPEN_FAILURE` | Không thể mở destination |
| `FORMAT_FAILURE` | Không thể format một record |

**ErrorManager không phải hệ thống telemetry production đầy đủ.** Default behavior của implementation có thể chỉ xuất một số thông báo lên stderr để tránh spam; không nên dùng việc “mỗi lần lỗi đều có một dòng stderr” như SLO. Cần instrumentation riêng cho counters, health và alert khi policy yêu cầu.

Chú ý:

- `Logger#log(...)` có thể trả về bình thường dù một Handler báo lỗi nội bộ. Không mặc định retry business operation chỉ vì logger return.
- Một custom `Handler` tự viết cần **bắt và report lỗi phù hợp**; không phát log báo lỗi qua chính handler đang hỏng, vì có nguy cơ recursion.
- `ErrorManager.error(...)` là callback; đừng làm network call đồng bộ chậm hoặc throw exception từ callback này trong production.
- Các loại lỗi như “disk full”, “permission denied” hay “format error” nên được phân loại, nhưng **không đưa raw message chứa secret** vào metric labels.
- Nếu Handler chỉ gọi `reportError` lúc write thất bại, các sự kiện bị loại **trước khi Handler nhận** sẽ không được tính bởi counter này.

### 3.2. SLF4J + Logback

SLF4J là façade; Logback Classic/Core cung cấp appenders và status infrastructure khi dùng Logback backend. Những tín hiệu quan trọng:

- Status messages do appender, encoder, rolling policy hoặc hệ thống config phát ra.
- `StatusManager` và listener/status console nếu cấu hình tương ứng; phải kiểm tra phiên bản và lifetime của các status entries.
- File appender không mở được, rolling/rotation lỗi, encoder lỗi, write/flush/close gặp vấn đề.
- `AsyncAppender` có bounded queue, discarding policy và `neverBlock`; queue full có thể tạo **producer blocking** hoặc **event drop**, tùy cấu hình.
- Logger level/filter trước appender có thể loại event có chủ đích, không được tính là write failure.

**Logback status ≠ metrics chuẩn hóa mặc định.** Một số status chỉ ghi ở startup hoặc khi component báo lỗi, không có counter đầy đủ cho mọi event thất bại. Nếu production cần SLI, dùng instrumentation/metrics adapter phù hợp, kiểm tra overhead và khả năng xuất số liệu độc lập.

Một ví dụ cấu hình Logback mang tính minh họa:

```xml
<configuration debug="true">
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Trong Logback, `debug="true"` có thể xuất thông tin trạng thái cấu hình trong lúc khởi tạo, hữu ích để tìm lỗi loader/appender. **Không coi đây là cấu hình production giám sát lỗi đầy đủ** hoặc nên bật vĩnh viễn ở mọi dịch vụ. Các status messages có thể chứa tên file/endpoint hoặc chi tiết hệ thống; điều chỉnh theo quy trình bảo mật và volume.

### 3.3. Log4j 2

Log4j 2 có **StatusLogger**/status reporting cho lỗi nội bộ và cấu hình. Tùy chế độ logger/async/appender:

- Một network appender có thể retry, không enqueue, buffer đầy, drop hoặc phát cảnh báo theo semantics của phiên bản.
- `ignoreExceptions` của một số appenders ảnh hưởng việc exception từ appender có được chuyển lên caller hay được xử lý trong framework; phải kiểm tra cấu hình cụ thể.
- AsyncLogger/AsyncAppender có queue-full policies. Khi đầy, caller có thể chịu chi phí hoặc event bị bỏ theo chiến lược được cấu hình.
- Startup config errors có thể khiến appender không hoạt động dù ứng dụng vẫn khởi chạy.

Không áp tên thuộc tính `neverBlock` của Logback cho Log4j 2. Cần xác minh backend thực tế, version đang chạy, status channels, và metrics từ các thành phần liên quan; không giả định tất cả đều có `dropped_events_total` xuất sẵn.

### 3.4. Framework và logging bridge

Spring Boot, Quarkus hoặc các môi trường khác có thể cấu hình level/root appenders, redirect JUL sang SLF4J hoặc dùng các logging bridges. Khi thấy “không có log”, kiểm tra:

- Binding/provider SLF4J thực tế và thông báo startup.
- Config file đang được load trong environment hiện tại.
- Logger hierarchy, package level và filters.
- Có nhiều backend/bridge gây vòng lặp hoặc route bất ngờ không.
- Lỗi từ appender đến JUL/logback/log4j2 có được đưa ra kênh diagnostics nào.

**Không dựa vào file `logback.xml` trong repo nếu production đang dùng một config override khác.** Theo dõi config effective/version và test thực tế qua event có ID duy nhất.

## 4. Mục tiêu giám sát: phát hiện lỗi, không gây thêm lỗi

Một hệ thống theo dõi lỗi ghi log không nên phụ thuộc hoàn toàn vào **chính sink đang lỗi**. Nếu file/collector hỏng, ghi `logger.error("log shipper failed")` vào cùng file/collector có thể không tới đâu và còn gây recursion/queue pressure.

Thiết kế thường có các lớp độc lập:

1. **In-process counters/gauges** trong bộ nhớ JVM, được xuất qua metrics endpoint hoặc hệ thống monitoring độc lập.
2. **Internal status diagnostics** của logger/backend cho việc gỡ lỗi tại máy, có giới hạn volume và redaction.
3. **Host/container metrics** cho disk space/inodes, file descriptors, CPU/GC, stdout driver, network.
4. **Agent/collector metrics** cho input accepted, exporter success/failure, queue depth, retry, bytes.
5. **End-to-end canary** phát một event không nhạy cảm và quan sát nó tại đúng sink/backend.
6. **Alert routing độc lập** (monitoring/pager) không chờ hệ thống log search xử lý được chính sự cố của nó.

Không cần làm “hệ thống giám sát không bao giờ lỗi”. Nhưng nên tránh một failure domain duy nhất khiến **cả log và cảnh báo mất log cùng biến mất**. Nếu metrics endpoint cũng ở cùng node và node down, phải có hạ tầng health checks/node alerts khác để nhận ra.

## 5. Cần đo những ranh giới nào?

Các event có thể bị loại ở nhiều điểm. Một bộ metrics tốt cần định nghĩa **đúng mẫu số**.

| Metric gợi ý | Đếm ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `logging_calls_total` | Tại wrapper/call site nếu có | Tổng lời gọi đã qua điểm instrumentation; không tự bao gồm mọi logger của thư viện |
| `logging_events_eligible_total` | Sau level/filter theo định nghĩa | Những event đáng xét trước sampling |
| `logging_events_sampled_out_total` | Sampling policy | Bỏ chủ động theo chính sách |
| `logging_events_admitted_total` | Điểm sau sampling | Những event được quyết định giữ |
| `logging_appender_received_total` | Khi appender/handler nhận record | Không phản ánh event bị loại trước đó |
| `logging_sink_write_attempts_total` | Trước thao tác write ở sink | Số lần thử ghi, có thể có retries |
| `logging_sink_write_failures_total` | Khi write thật báo lỗi | Sự cố ghi ở sink đó |
| `logging_sink_write_success_total` | Khi API write báo thành công | Chưa chắc durable hay collector đã nhận |
| `logging_queue_dropped_total` | Async queue/admission | Log mất do queue policy/overflow, không phải sampling |
| `logging_queue_depth` | Queue của appender/agent | Mức backlog hiện tại |
| `logging_enqueue_block_seconds` | Khi caller chờ enqueue | Tác động logging lên latency ứng dụng |
| `logging_agent_input_total` | Agent đã nhận/đọc | Log từ file/stdout đã đi qua agent |
| `logging_export_failures_total` | Agent/collector exporter | Thất bại gửi tới hop tiếp theo |
| `logging_collector_accepted_total` | Collector receiver | Collector chấp nhận event theo API contract |
| `logging_collector_rejected_total` | Parser/quota/security policy | Event bị loại tại collector |
| `logging_indexed_total` | Backend/index | Event đã được lưu/searchable theo định nghĩa |
| `logging_end_to_end_lag_seconds` | Canary theo event ID | Từ phát event đến backend nhìn thấy |

Đây là **tên metric đề xuất**, không phải các metric mặc định có mặt ở mọi JUL/Logback/Log4j 2/OpenTelemetry Collector. Khi triển khai cần đối chiếu tên và semantics thật của các thành phần, kể cả version và cardinality.

### Cách thiết kế label

Nhãn hợp lý gồm `service`, `environment`, `sink`, `error_category`, `outcome` và `policy_version` với tập giá trị giới hạn. **Không** dùng `trace_id`, `request_id`, `message_id`, user ID, path tự do hoặc raw exception message làm Prometheus metric labels. Các giá trị nhiều biến thể sẽ làm tăng cardinality và có thể làm chính monitoring bị quá tải.

Ví dụ một bộ lỗi ghi:

```text
logging_sink_write_failures_total{
  service="checkout",
  environment="production",
  sink="application-file",
  error_category="permission_denied"
}
```

Đây là dạng exposition **minh họa**, không phải một metric được Java tự xuất. Muốn có bộ đếm, phải instrument tại đúng điểm thực hiện write/error callback. Không đếm 10 lần nếu một lỗi ở tầng dưới làm 10 dòng status trùng, trừ khi định nghĩa metric là số lần report thay vì số event mất.

## 6. Lỗi “im lặng”: vì sao chỉ nghe status là chưa đủ?

Một số nguyên nhân mất log không tạo exception ở ứng dụng:

- `DEBUG` bị tắt hoặc logger level được thay khi deploy.
- Filter hoặc sampler loại event vì key thiếu hoặc sai.
- Async queue đầy và policy drop không báo lỗi cho caller.
- Container stdout/file còn dữ liệu nhưng agent đang đọc nhầm đường dẫn.
- Agent đọc được nhưng bị giới hạn queue/disk spool rồi drop.
- Collector transform loại sự kiện hợp lệ theo rule sai.
- Query dùng timezone/index/tenant không đúng nên kết quả 0.
- Collector/backend rơi vào eventual consistency, log chưa searchable.

Do đó cần **tín hiệu độc lập về sự có mặt của event**. Một canary log có ID/sequence cố định theo từng lượt phát là một lựa chọn hữu ích. Không chỉ dựa vào “có log gần đây” vì việc đó có thể là log từ service khác, máy khác hoặc một instance khỏe trong khi instance khác đã mất log.

### Heartbeat khác canary

- **Heartbeat** thường kiểm tra hoạt động sống của service/agent; nếu dùng chung logging path, mất heartbeat có thể chỉ ra sự cố nhưng chưa xác định hop lỗi.
- **Canary log** là event thử có `event_id`, source timestamp, service/instance và destination kỳ vọng; hệ thống kiểm tra **đúng event này** đã tới backend trong deadline.
- **Synthetic trace** có thể kiểm tra correlation từ một request giả xuyên services; lưu ý trace sampling/log sampling không tự đảm bảo mọi event synthetic được giữ.

Canary nên ở tuyến đã được phê duyệt, không chứa secret, tránh flood và không nhầm với audit nghiệp vụ. Nếu pipeline có sampling/filter, phải **bypass có kiểm soát hoặc thiết kế canary phù hợp rule**, để sự vắng mặt không chỉ vì canary chủ động bị lấy mẫu ra.

## 7. Java 17 độc lập: mô phỏng lỗi write và flush bằng ErrorManager

Ví dụ sau dùng **JDK 17+**, không cần Maven, JUnit hoặc thư viện ngoài. Chương trình chủ động mô phỏng một Handler làm hai việc:

1. Nhận ba `LogRecord` từ JUL; hai record được đưa vào **sink giả in-memory**, một record bị mô phỏng write failure.
2. Khi `flush()`, mô phỏng flush failure và báo qua `ErrorManager` tùy biến.

Tất cả output và error count là **deterministic**. Handler báo lỗi qua `reportError(...)`, không dùng chính logger để ghi thông báo lỗi. Custom ErrorManager chỉ tăng counter, tránh phụ thuộc stdout/stderr có thể hỏng.

Chú ý: **“accepted” trong ví dụ là được lưu vào List trong bộ nhớ**, không đại diện ghi file thành công, fsync hoặc backend durable. Các ranh giới ấy cần integration test riêng.

### File `LogWriteFailureMonitoringDemo.java`

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.ErrorManager;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogWriteFailureMonitoringDemo {
    private static final class CountingErrorManager
            extends ErrorManager {
        private final AtomicInteger writeFailures =
                new AtomicInteger();
        private final AtomicInteger flushFailures =
                new AtomicInteger();
        private final AtomicInteger otherFailures =
                new AtomicInteger();

        @Override
        public void error(String message, Exception exception, int code) {
            if (code == WRITE_FAILURE) {
                writeFailures.incrementAndGet();
            } else if (code == FLUSH_FAILURE) {
                flushFailures.incrementAndGet();
            } else {
                otherFailures.incrementAndGet();
            }
        }

        int writesFailed() {
            return writeFailures.get();
        }

        int flushesFailed() {
            return flushFailures.get();
        }

        int othersFailed() {
            return otherFailures.get();
        }
    }

    private static final class SimulatedSinkHandler extends Handler {
        private final List<String> accepted = new ArrayList<>();
        private int recordsReceived;

        SimulatedSinkHandler(ErrorManager errorManager) {
            setLevel(Level.ALL);
            setErrorManager(errorManager);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            recordsReceived++;

            // Một lỗi I/O giả lập, không đụng filesystem thật.
            if ("evt-2".equals(record.getMessage())) {
                reportError("synthetic write failure",
                        new IOException("disk unavailable"),
                        ErrorManager.WRITE_FAILURE);
                return;
            }
            accepted.add(record.getMessage());
        }

        @Override
        public void flush() {
            reportError("synthetic flush failure",
                    new IOException("flush unavailable"),
                    ErrorManager.FLUSH_FAILURE);
        }

        @Override
        public void close() {
        }

        int received() {
            return recordsReceived;
        }

        List<String> acceptedIds() {
            return List.copyOf(accepted);
        }
    }

    private static void require(boolean condition, String name) {
        if (!condition) {
            throw new IllegalStateException(
                    "Assertion failed: " + name);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logwrite.monitor");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CountingErrorManager diagnostics = new CountingErrorManager();
        SimulatedSinkHandler sink =
                new SimulatedSinkHandler(diagnostics);
        logger.addHandler(sink);

        try {
            logger.info("evt-1");
            logger.warning("evt-2");
            logger.info("evt-3");
            sink.flush();

            List<String> accepted = sink.acceptedIds();
            require(sink.received() == 3, "received count");
            require(accepted.equals(List.of("evt-1", "evt-3")),
                    "accepted events");
            require(diagnostics.writesFailed() == 1,
                    "write failures");
            require(diagnostics.flushesFailed() == 1,
                    "flush failures");
            require(diagnostics.othersFailed() == 0,
                    "other failures");

            System.out.println("handler_received="
                    + sink.received());
            System.out.println("fake_sink_accepted="
                    + accepted.size());
            System.out.println("write_failures="
                    + diagnostics.writesFailed());
            System.out.println("flush_failures="
                    + diagnostics.flushesFailed());
            System.out.println("accepted_ids="
                    + String.join(",", accepted));
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
javac LogWriteFailureMonitoringDemo.java
java LogWriteFailureMonitoringDemo
```

**stdout chính xác:**

```text
handler_received=3
fake_sink_accepted=2
write_failures=1
flush_failures=1
accepted_ids=evt-1,evt-3
test=PASS
```

### Giải thích kết quả

1. `Logger` đang bật `Level.ALL`, `Handler` cũng bật `Level.ALL`; cả ba event tới Handler, không bị level filter chặn.
2. Khi nhận `evt-2`, Handler gọi `reportError(..., WRITE_FAILURE)` và không thêm event đó vào danh sách được chấp nhận. Đây là lỗi write **giả lập tại Handler**, không phải mất log do sampling.
3. Sau ba event, gọi `sink.flush()`. Handler báo một `FLUSH_FAILURE` giả lập nhưng không xóa hai event đã được lưu vào danh sách.
4. `CountingErrorManager#error` nhận mã lỗi và tăng bộ đếm tương ứng; nó không gọi logger hay in exception, nên không có recursion hoặc dòng stderr xen giữa.
5. Assertions kiểm tra số event Handler nhận, danh sách được chấp nhận và số lỗi theo loại. Chỉ khi tất cả đúng mới in `test=PASS`.
6. `setUseParentHandlers(false)` ngăn JUL parent handlers phát thêm output không liên quan. Handler được detach/close ở `finally` để không ảnh hưởng test khác.
7. Đây là test **tuần tự trong một thread**. `ArrayList`/`recordsReceived` không thread-safe nếu nhiều thread cùng gọi `publish`; khi triển khai Handler shared giữa threads, phải dùng cấu trúc/counters phù hợp hoặc đồng bộ theo contract của implementation.

### Chúng ta đã chứng minh được gì?

- Bộ đếm ở **đúng điểm Handle.reportError** phát hiện một write failure và một flush failure.
- **Số record nhận ≠ số record giả lập được ghi thành công.**
- Không cần dựa vào log error cùng pipeline để biết lỗi.
- Lời gọi `logger.warning("evt-2")` trả về bình thường trong chương trình dù sink báo write failure nội bộ.

Chúng ta **chưa chứng minh** khả năng recovery, fsync, network delivery, retention hoặc collector index. Trong production, việc một Handler báo lỗi có thể được format/in qua implementation khác; custom handler phải biết báo lỗi trong các nhánh lỗi thật. Các lỗi của appender bên thứ ba không tự động đi vào `CountingErrorManager` của Handler này.

### Thí nghiệm học tập

- Đổi điều kiện lỗi thành `"evt-3"`: assertion danh sách accepted sẽ fail; test bắt được thay đổi tuyến lỗi.
- Bỏ `sink.flush()`: assertion flush failures sẽ fail; chứng minh lỗi flush là một ranh giới riêng.
- Đổi level logger thành `Level.SEVERE`: cả INFO/WARNING bị loại trước Handler, nên `handler_received=3` không còn đúng.
- Bỏ `reportError(...)` trong nhánh thất bại: số event accepted giảm nhưng counter write failures không tăng; đây là **silent loss**. Bài học là instrumentation ở đúng failure path quan trọng.
- Thêm Handler thứ hai nhận event: phải xác định liệu test đo failure của một sink hay tổng tất cả sinks, tránh xem fan-out có chủ đích là duplicate bất thường.

## 8. Từ ErrorManager đến production metrics

Trong môi trường thật, không nên lấy nguyên `ArrayList` của chương trình làm sink. Một custom adapter có thể dùng counters thread-safe của metrics library tổ chức đang dùng.

Pseudocode minh họa:

```text
on handler receives record:
    received_counter.increment()
    try:
        write_record_to_sink(record)
        successful_write_counter.increment()
    catch known write exception:
        write_failure_counter.increment(error_category)
        report_internal_error_without_using_same_logger()
        apply documented sink failure policy
```

Đây là **pseudocode**; contract khác nhau nếu write bất đồng bộ hay buffer. Nếu `write_record_to_sink` chỉ enqueue, đặt tên `enqueue_success` thay cho `write_success`. Nếu exception xảy ra khi format thì tăng `format_failure`, đừng gộp vào `disk_failure`.

### Cẩn thận với callback lỗi

- Callback nên **rẻ, không chặn**, vì thường chạy trong caller/worker quan trọng.
- Counter có thể dùng `LongAdder` hoặc primitive của metrics SDK được dùng thật, tùy concurrency/performance. Không tự dùng `int++` không đồng bộ giữa nhiều threads.
- Dùng error category từ allowlist: `disk_full`, `permission_denied`, `timeout`, `tls_failure`, `format_failure`. Không để exception message tùy ý thành label.
- Không ghi log khác qua cùng appender từ `ErrorManager.error` hoặc Logback error callback.
- Cần test khi chính metrics exporter lỗi: không được tạo vòng lặp tăng lỗi rồi gọi logger tiếp tục.
- ErrorManager chỉ phản ánh **lỗi được handler báo**; metrics từ queue và collector phải được instrument riêng.

## 9. Theo dõi file, stdout và rotation

### 9.1. File appender

Một service ghi log tới file có thể gặp:

- Parent directory không tồn tại hoặc không có quyền.
- File bị khóa/permission thay đổi sau deploy.
- Disk hết dung lượng hoặc hết inode.
- Filesystem chuyển read-only, I/O error hoặc latency rất cao.
- File rotation/rename/truncate làm appender tiếp tục ghi vào inode cũ; shipper có thể đọc sai.
- Rolling policy xóa file trước khi shipper đọc xong hoặc tạo quá nhiều file.
- File descriptor leak, ulimit quá thấp hoặc quota container/volume.

Theo dõi **filesystem free bytes/inodes**, số write errors, appender status, file size/last update, open file descriptors, rotate counters, shipper offsets và ingest lag.

**Đừng xem file size không tăng là lỗi chắc chắn.** Lưu lượng có thể bằng 0 theo nghiệp vụ hoặc level/sampling đã thay đổi. Kết hợp tín hiệu traffic/eligible events và canary.

### 9.2. Stdout/container logging

Nhiều ứng dụng Java container ghi ra stdout/stderr rồi runtime/agent thu thập. Rủi ro:

- Stdout pipe/driver bị nghẽn làm sync ConsoleAppender chặn application thread.
- Container logging driver cắt/bỏ event khi áp quota hoặc rotate.
- Agent daemonset/sidecar không chạy, thiếu permission đọc container log.
- Pod bị thay/evict trước khi buffer được ship.
- Log entry bị chẻ/truncate do multiline stack trace hoặc kích thước message lớn.
- Timestamp/metadata của container không khớp với app timestamp.

Theo dõi **stdout/stderr pipeline** và agent, không chỉ Java appender. Nếu appender báo write success vào stdout, điều đó không chứng minh log đã tới collector.

### 9.3. Rotation test

Một bài test có thể:

1. Phát event trước rotation, xác nhận file/agent đã thấy.
2. Kích hoạt rotation trong staging hoặc qua một cấu hình test.
3. Phát event sau rotation và theo dõi file descriptor/shipper offsets.
4. Kiểm tra event không biến mất và không bị đọc trùng ngoài ý muốn.
5. Kiểm tra disk/inode không tăng không giới hạn.
6. Kiểm tra lại quyền file mới và cấu hình retention.

Không can thiệp file log production bằng xóa/rename thủ công khi chưa có quy trình, vì có thể làm mất chứng cứ hoặc khiến appender ghi vào inode cũ.

## 10. Async logging: queue full, drop và tác động lên ứng dụng

AsyncAppender/AsyncLogger giúp tách phần ghi chậm khỏi business thread, nhưng vẫn có thể làm mất log hoặc làm ứng dụng bị chặn khi queue đầy.

```text
application threads
     |
     v
async queue (bounded) ---> writer thread ---> file/stdout/network
     ^                        |
     |                        v
     +--- full / backpressure / write error
```

Các tín hiệu cần đo:

- `queue_depth` và `queue_capacity` (cùng timestamp quan sát).
- `enqueue_attempts`, `enqueue_success`, `enqueue_dropped`.
- `producer_block_duration` hoặc histogram logger-call duration.
- `worker_write_latency`, `flush_latency`, `worker_unhealthy`.
- `discarded_by_policy` tách khỏi `dropped_due_to_overflow`.
- `shutdown_pending_events` và `shutdown_drain_failures` nếu SDK hỗ trợ.

**Một enqueue thành công không phải một write thành công.** Sự khác biệt đặc biệt quan trọng lúc collector tắc nghẽn: queue có thể chứa nhiều event nhưng backend chỉ nhận vài event/giây. Khi queue đầy, production có thể:

- Chặn caller chờ chỗ trống.
- Loại event theo chính sách discard.
- Drop ngay để giữ latency.
- Ghi đồng bộ trên caller trong một số cơ chế/policy.
- Buffer/disk-spool theo thiết kế của agent/exporter.

Không kết luận “async logging không bao giờ block”. Khi phát hiện p99 request tăng cùng queue occupancy cao, lấy thread dump/JFR ở môi trường được phép và kiểm tra appender đang chờ lock/I/O/queue.

### Phân biệt blocked, dropped và delayed

| Tình huống | Biểu hiện | Cần báo động |
| --- | --- | --- |
| Producer chờ enqueue | Caller latency/p99 tăng, nhiều threads waiting | Ảnh hưởng application availability |
| Queue nhận nhưng writer chậm | Queue depth và event age tăng | Nguy cơ đầy queue và chậm điều tra |
| Queue drop INFO theo policy | Drop counter tăng, logger caller vẫn nhanh | Dữ liệu quan sát bị mất có chủ đích/overload tùy rule |
| ERROR event cũng drop | Critical delivery gap theo policy | Sự cố nghiêm trọng nếu ERROR cần full retention |
| Writer lỗi khi flush | Appender ErrorManager/status báo lỗi | Không đảm bảo buffer đã được đẩy |
| Collector/index chậm | JVM/appender có thể bình thường, visibility lag tăng | Người vận hành tìm log muộn hoặc không thấy |

Để giám sát chủ động, đặt cảnh báo **trước khi queue đầy** và cảnh báo riêng khi đã drop; tỷ lệ sử dụng 90% trong một phút có thể nguy hiểm tùy burst, nhưng không phải ngưỡng chuẩn chung. Hiệu chỉnh theo volume và throughput của service.

## 11. Theo dõi agent, collector và backend

Trong pipeline nhiều hop, metric ở Java không đủ. Phải quan sát **agent/collector xuất đi và nhận về**.

### 11.1. Agent/shipper

Xem:

- Bytes/records đọc từ stdout/file.
- Input parser errors, multiline errors, truncated records.
- Export requests, request failures, retry attempts, timeout.
- Queue/spool utilization và thời gian tồn backlog.
- Last successful export timestamp hoặc age của oldest pending batch.
- Process availability/restart count, OOM/CPU/memory.
- TLS certificate expiry, authentication failures, proxy/DNS errors.

Nếu agent sống nhưng không đọc file vì glob sai, liveness check có thể vẫn PASS. Canary log và agent input counters sẽ phát hiện sự lệch này.

### 11.2. Collector

Xem số record **accepted**, **refused/rejected**, **filtered by policy**, **exported**, **failed** và pending queue theo processor/exporter thực tế. Đừng mặc định tên metric hoặc semantics cố định giữa các version/distributions của OpenTelemetry Collector, Fluent Bit, Vector, Filebeat hoặc hệ thống khác.

Một collector có thể nhận record rồi:

- Drop theo filter/transform có chủ đích.
- Từ chối vì schema/quota.
- Retry/queue khi backend không sẵn sàng.
- Mất batch vì queue/spool không còn chỗ.
- Export thành công nhưng backend chưa searchable.

Khi dùng OpenTelemetry, phân biệt logs/metrics/traces pipelines; lỗi exporter logs không nhất thiết hiện trong metrics của trace exporter. Truy vấn đúng pipeline, endpoint, tenant và routing configuration.

### 11.3. Backend/index

Theo dõi:

- Ingest request rate, errors/rejections, queue/backlog.
- Shard/index write failures hoặc indexing lag.
- Storage capacity, retention/rollover và quota.
- Search/query availability và permissions.
- Khả năng truy vấn canary event theo `event_id`, `service`, `environment`, `timestamp`.
- Tình trạng nhân đôi do retry/fan-out, mapping conflict, field truncation.

**Một query trả về 0 record không tự chứng minh event đã mất.** Có thể truy vấn sai index, namespace, timezone, policy, eventual consistency hoặc ID đã bị transform. Khi điều tra, đi từ hop gần nguồn nhất đã xác nhận event tới được, rồi lần lượt kiểm tra hop tiếp theo.

## 12. Canary log: kiểm tra từ nguồn đến nơi tìm kiếm

Một canary tốt có các thuộc tính:

- Event code cố định, ví dụ `logging.pipeline.canary`.
- `canary_id` duy nhất cho mỗi lượt phát, ví dụ `svcA-instance2-20261110T090000Z-7f2a`.
- `service`, `environment`, `instance` và `emitted_at`.
- Không có token, PII, dữ liệu nghiệp vụ hoặc raw payload nhạy cảm.
- Đi qua **đúng tuyến** cần kiểm tra, không có shortcut bypass toàn collector.
- Sampling/filter được cấu hình sao cho event canary không bị bỏ do policy thông thường.
- Một checker độc lập đợi event ở backend với deadline phù hợp và ghi nhận thời gian nhận/search.
- Có giới hạn tần suất để canary không trở thành nguồn log storm.

Ví dụ record JSON:

```json
{
  "event": "logging.pipeline.canary",
  "canary_id": "checkout-a1-20261110T090000Z-7f2a",
  "service": "checkout",
  "environment": "production",
  "instance": "checkout-a1",
  "emitted_at": "2026-11-10T09:00:00Z"
}
```

Đây là **event mẫu**, không phải schema mặc định của Java/collector. Canary chỉ chứng minh **một tuyến đã thành công tại thời điểm kiểm tra**. Nó không chứng minh mọi log event tương lai hoặc mọi đường audit đều không mất. Nếu route có nhiều sinks, cần canary độc lập hoặc assertion rõ cho từng route.

### Tín hiệu canary quan trọng

- `canary_emitted_total` tại nguồn giám sát độc lập.
- `canary_seen_total` tại backend theo event ID.
- `canary_missing_total` sau deadline quan sát.
- `canary_delivery_lag_seconds`: emitted-to-searchable delay.
- `canary_duplicate_total`: số event ID xuất hiện nhiều lần ngoài policy.
- `last_successful_canary_at` cho từng service/instance/route.

Canary có thể được phát ít lần một phút hoặc theo chính sách thích hợp; không có nhịp chuẩn cho mọi hệ thống. Nếu pipeline ít traffic, canary định kỳ giúp phát hiện “im lặng vì lỗi” mà không cần traffic nghiệp vụ.

**Lưu ý về đồng hồ:** Nếu đo `emitted_at` ở một node và `searchable_at` ở node khác, clock skew có thể gây latency âm. Nếu cần SLO chính xác, dùng hệ thống thời gian đồng bộ hoặc đo elapsed bằng checker theo contract nhất quán; cảnh báo clock drift riêng.

## 13. Xây dashboard và cảnh báo production

Một dashboard tốt phải trả lời câu hỏi **“đang mất log ở đâu và ảnh hưởng gì?”**, không chỉ vẽ một biểu đồ log volume.

### Nhóm 1: tín hiệu tại JVM

- Handler/Appender write failures theo loại lỗi và sink.
- Async queue occupancy, dropped/discarded events, worker health.
- Logger call p95/p99 và blocked enqueue duration.
- Number of logger config/load errors hoặc rolling policy failures.
- Critical event counters từ nguồn nghiệp vụ/audit nếu có.
- Số instance có metrics hiện diện; missing metrics cũng là tín hiệu quan trọng.

### Nhóm 2: hạ tầng trung gian

- Disk free bytes/inodes, FD usage, container restarts.
- Agent input/output records, rejected and retry totals.
- TLS/auth failures, collector availability/latency.
- Pending queue age/spool utilization.
- Ingest refused/rejected, exporter errors.

### Nhóm 3: end-to-end

- Canary missing rate theo service/environment/route.
- Median/p95/p99 emitted-to-searchable lag nếu đủ dữ liệu và đồng hồ hợp lệ.
- Số instance không có canary thành công trong khoảng kiểm tra.
- Record counts theo expected route, nhưng có tính đến sampling/filter/retry.
- Critical-audit reconciliation gap (khi có kho authoritative).

### Ví dụ rule cảnh báo cần hiệu chỉnh

| Tên cảnh báo | Điều kiện ví dụ | Mức độ/hành động |
| --- | --- | --- |
| **AppenderWriteFailure** | `increase(write_failures[5m]) > 0` tại sink critical | Triage ngay, xem disk/permission/status |
| **AsyncQueueNearCapacity** | Queue occupancy cao liên tục và tăng | Kiểm tra sink throughput, giảm noise an toàn |
| **LoggingQueueDropped** | Overflow drops tăng trong 5 phút | Điều tra chính sách drop và tác động tới logs |
| **CollectorExportFailure** | Export errors tăng + oldest pending batch già | Kiểm tra TLS/auth/network/collector |
| **CanaryMissing** | Không tìm thấy canary trong deadline và đủ dữ kiện | Truy vết từng hop; tách query lỗi với delivery lỗi |
| **CanaryLagHigh** | p95 delivery-to-search vượt ngân sách đã duyệt | Điều tra queue/backlog/index |
| **CriticalAuditGap** | Business events committed vượt audit events đã xác nhận sau deadline | Kiểm tra outbox/store/reconciliation |
| **MetricsMissing** | Service/agent không xuất metrics quá thời hạn | Phân biệt service down và monitoring down |

Các điều kiện là **minh họa**, không phải rule copy-paste trực tiếp cho Prometheus; tên metric và vector labels thực tế phải được định nghĩa trước. Với critical audit, ngưỡng `>0` có thể hợp lý nhưng chỉ khi counter đáng tin, có tránh alert do restart/cold start và được nhóm vận hành chấp thuận.

### Không dùng số log lines đơn thuần làm error rate

Ví dụ ứng dụng nhận 10.000 requests, sinh 2 lỗi nghiệp vụ nhưng code log ERROR 3 lần/lỗi vì nhiều tầng catch-and-rethrow. Dashboard đếm 6 ERROR lines sẽ phóng đại lỗi. Trường hợp ngược lại, logging sink down khiến dashboard thấy 0 ERROR lines dù dịch vụ đang lỗi rất nhiều.

Để có **business error rate** hay SLO, dùng request counters, transaction outcomes hoặc metrics tại nguồn độc lập với log sampling/delivery. Logs hỗ trợ điều tra chi tiết, không phải nguồn duy nhất cho mẫu số/tử số nếu pipeline có thể mất.

## 14. SLO/SLI: định nghĩa khả năng quan sát trung thực

Một số chỉ số hữu ích:

### 14.1. Tỷ lệ xuất log được chọn

Nếu có instrumentation đầy đủ tại một appender:

\[
\text{Appender write success rate} =
\frac{\text{successful writes}}{\text{write attempts}}
\]

Chỉ dùng khi mỗi attempt/success được đếm nhất quán. Nếu một event được retry 3 lần, **successful writes / write attempts** không còn là tỷ lệ event duy nhất được giao thành công. Phải nêu rõ đơn vị (attempts hay unique events).

### 14.2. Tỷ lệ canary tới backend

\[
\text{Canary delivery ratio} =
\frac{\text{unique canary IDs observed by deadline}}
{\text{unique canary IDs emitted and eligible}}
\]

Phải bỏ các lượt canary chưa quá deadline, phân biệt do policy filter có chủ đích, và đảm bảo checker có quyền truy vấn đúng. Nếu backend query lỗi, checker có thể kết luận **UNKNOWN** thay vì tự gắn “missing” cho toàn bộ event.

### 14.3. Độ trễ hiển thị

\[
\text{Visibility lag} =
t_{\text{searchable}} - t_{\text{emitted}}
\]

Nếu hai timestamp ở hai đồng hồ không đồng bộ, đây là ước lượng có thể sai lệch. Có thể sử dụng source event timestamp và backend observed timestamp với ghi chú về đồng bộ thời gian; không dùng độ trễ âm như bằng chứng sự kiện đi ngược thời gian.

### 14.4. Không thể giả định 100% delivery từ “không có lỗi”

Nếu event không được instrument hoặc lỗi im lặng, write failure counter bằng 0 **không đủ chứng minh** không mất log. Canaries, end-to-end reconciliation và controls theo route bổ trợ cho status counters.

Mỗi SLO cần nêu rõ **phạm vi service/route, thời hạn, thời điểm tính, loại log, event ID và điều kiện loại trừ hợp lệ**. Một SLO cho DEBUG sample không nhất thiết giống audit log bắt buộc, và một log tại stdout không tương đương “durable backend event”.

## 15. Nguyên tắc khi log pipeline thất bại

Một chính sách sự cố cần được quyết định **trước** lúc gặp outage.

### 15.1. Giữ ứng dụng hoạt động hay dừng?

- **Fail-open:** business tiếp tục dù log delivery thất bại, đồng thời có monitoring/alert và cơ chế buffer/recovery theo mức độ quan trọng. Phù hợp với nhiều diagnostic logs.
- **Fail-closed:** từ chối thao tác nếu không thể bảo đảm ghi audit bắt buộc theo contract. Có thể phù hợp với thay đổi nhạy cảm, nhưng cần thiết kế, kiểm thử và đánh giá tác động availability.

Không áp cùng chính sách cho mọi dòng log. Ví dụ “thêm DEBUG để điều tra” không nên làm dịch vụ thanh toán ngừng phục vụ chỉ vì collector chậm. Ngược lại, một audit event bắt buộc có thể cần đường lưu bền vững/trust boundary riêng thay vì best-effort logging.

### 15.2. Bounded buffering, retry và backpressure

- Queue bounded giúp tránh RAM vô hạn nhưng cần policy khi đầy.
- Disk spool có thể tăng khả năng phục hồi outage ngắn, nhưng cần quota, at-rest security, permission và retention.
- Retry có backoff/jitter, deadline và phân loại lỗi; không retry vô hạn với auth 401/403 hoặc payload invalid.
- Failure khi đã gửi nhưng chưa nhận ACK có thể dẫn đến duplicate sau retry; dùng event ID và idempotency nếu cần.
- Ghi rõ khi nào một event được coi là “accepted”, “sent”, “acknowledged” và “durable”.
- Tránh tự fallback sang HTTP/plaintext hoặc sink ít an toàn khi TLS/authorization fail.
- Khi disk spool đầy, không được âm thầm xóa audit/security events ngoài chính sách.

### 15.3. Không tạo vòng lặp báo lỗi

Một tình huống nguy hiểm:

```text
appender.write() throws IOException
   |
   v
error handler calls logger.error("write failed")
   |
   v
same appender.write() throws IOException
   |
   v
... recursive failure / log storm
```

Cách giảm nguy cơ:

- ErrorManager/status callback chỉ cập nhật counter hoặc báo qua kênh nội bộ được thiết kế không phụ thuộc cùng sink.
- Gửi pager/alert từ metrics backend/health checker độc lập.
- Throttle internal diagnostics, tránh in stack trace cho mỗi event mất.
- Nếu cần log thông báo về logging failure, dùng channel được cách ly và có mức tải/khả năng thất bại đã đánh giá.
- Thử inject failure để chứng minh không có recursion hoặc deadlock.

## 16. Triage và runbook xử lý sự cố production

Khi nhận cảnh báo canary missing hoặc write failure, tiến hành có thứ tự:

1. **Xác minh ảnh hưởng người dùng:** request latency, availability, business error rate, audit compliance; xem đây có phải sự cố riêng của quan sát hay đang ảnh hưởng dịch vụ.
2. **Khoanh vùng tuyến:** service, environment, instance, logger name, appender, file/stdout, agent, collector, index/tenant và thời gian.
3. **Xác minh event gốc:** source metric hoặc canary ID cho biết event được định phát chưa? Policy level/filter/sampling có loại nó chủ động không?
4. **Kiểm tra JVM:** Logback/Log4j2/JUL internal status, write/flush errors, queue depth, dropped events, thread dumps khi p99 tăng.
5. **Kiểm tra host/container:** disk space, inodes, permission, file descriptor, stdout driver, rotation, pod restarts và OOM.
6. **Kiểm tra agent:** có đọc file/stdout đúng path không? Input records có tăng? Exporter retry, spool, auth/TLS errors thế nào?
7. **Kiểm tra collector:** receivers accepted/refused, processors, exporters, queues, filtering policies, limits, schema errors.
8. **Kiểm tra backend:** index write/reject/lag, mapping, retention, query permissions và timezone; xác minh có thể search một event biết chắc đã tới.
9. **Giảm tải đúng chính sách:** giảm DEBUG/INFO noisy, sửa sink/collector, tăng throughput hoặc backpressure có kiểm soát. Không tắt audit/security bắt buộc hay vô hiệu hóa TLS để “log lên lại”.
10. **Xác minh hồi phục:** canary qua deadline, queue drain, write errors dừng, critical event gap được reconciliation, p95/p99 ứng dụng phục hồi.
11. **Bù dữ liệu nếu được phép:** re-ship từ disk spool/outbox, idempotency/dedup, audit trail của backfill; không tự dựng lại event chưa từng được ghi.
12. **Postmortem:** ghi rõ điểm đầu tiên log mất, phạm vi thiếu dữ liệu, thời gian phát hiện, tín hiệu thiếu và action items.

### Mẫu bảng điều tra theo hop

| Điểm | Bằng chứng có thể thu | Kết luận hợp lệ |
| --- | --- | --- |
| Caller/metric | `events_admitted_total` tăng | Event đủ điều kiện đã đi qua sampling |
| Handler/Appender | `received` tăng, `write_failures` tăng | Lỗi tại sink/handler có khả năng làm mất event |
| Local file/stdout | Có record với test ID | Thành công ở local sink này |
| Agent | Đọc được ID và export pending | Đã vào agent nhưng chưa xác nhận downstream |
| Collector | Ingest/accepted theo ID hoặc batch | Collector đã nhận theo semantics của nó |
| Backend | ID searchable đúng index/tenant | Đã nhìn thấy ở backend trong thời hạn quan sát |

Tránh kết luận “lỗi ở collector” khi chỉ mới biết console không có event: vấn đề có thể nằm ở logger level. Ngược lại nếu local file có event mà backend không có, không nên sửa logger source một cách mù quáng.

## 17. Failure-injection tests cần có trước khi production

Một bộ test đáng tin không chỉ chạy happy path.

| ID | Kịch bản | Điều phải quan sát |
| --- | --- | --- |
| F1 | Handler custom gặp IOException khi write | Counter write failure tăng, không recursive logging |
| F2 | Formatter/encoder lỗi | Format failure/status xuất đúng loại, không nhầm disk full |
| F3 | Không mở được file appender | Startup status/health phản ánh, không silent |
| F4 | Disk full hoặc inode full trên volume staging | Write errors, backlog/drop, alert, recovery |
| F5 | File rotation khi agent đang đọc | Không mất/dup vượt policy, offsets/permissions đúng |
| F6 | Console/stdout pipe chậm | Caller latency/blocked threads/queue occupancy được đo |
| F7 | Async queue đầy | Block/drop theo policy, metrics riêng cho deliberate sampling và overflow |
| F8 | Agent process bị kill/restart | Canary missing, spool recovery, backlog drain |
| F9 | Collector timeout/TLS/auth fail | Retry có giới hạn, queue age tăng, không plaintext fallback |
| F10 | Backend index reject do schema | Collector rejection metrics, event ID được truy vết |
| F11 | Backend query unavailable | Checker trả UNKNOWN/QUERY_ERROR, không báo tất cả events mất |
| F12 | Service không có traffic | Canary hoặc expected idle policy, tránh alert sai do log volume thấp |
| F13 | Một trong nhiều replicas mất log | Per-instance canary/metrics phát hiện, không bị tổng volume che |
| F14 | Bật DEBUG hàng loạt | Sampling/rate limiting, disk/queue budgets và business p99 |
| F15 | Shutdown với pending async events | Drain/flush theo budget, số event chưa lưu được ghi nhận |
| F16 | Audit sink mất kết nối | Fail-open/closed theo policy, critical event reconciliation |
| F17 | Sink đã hồi phục nhưng agent backfill | Duplicate event IDs, index lag và quota được theo dõi |
| F18 | Log chứa canary secret giả | Không rò payload bí mật vào diagnostic/status/alert |

**Không chạy test disk full, kill collector hoặc sửa permission trên production tùy tiện.** Dùng staging, isolated volumes/containers hoặc fault injection được tổ chức phê duyệt, có rollback/cleanup. Một test chỉ tắt endpoint rồi nhìn số log giảm không đủ; cần biết logger/backend có ghi nhận lỗi thế nào và business có bị ảnh hưởng.

### Kiểm thử cảnh báo

Đừng chỉ chứng minh metrics tăng. Hãy kiểm tra thêm:

- Rule/alert thực sự chuyển sang firing với nhãn và severity đúng.
- Alert routing tới nhóm chịu trách nhiệm qua kênh độc lập.
- Dashboard có đường điều tra theo service, route, instance và error category.
- Alert có cơ chế chống flood khi nhiều pods cùng lỗi.
- Recovery/clear condition không “đóng” sự cố trước khi backlog/critical gap được xử lý.
- Runbook link, escalation và chủ sở hữu được cập nhật theo môi trường.

## 18. Một ví dụ phân tích lỗi thực tế

**Tình huống minh họa:** Sau khi nâng cấp container, ứng dụng Java vẫn trả API bình thường nhưng dashboard log không có record mới. Query theo request ID trả về rỗng. Không nên kết luận ứng dụng không tạo log.

Các bước:

1. Metrics request vẫn tăng; source logging counter có các event INFO/ERROR đủ điều kiện.
2. ConsoleAppender/JUL Handler không có write errors; local stdout có canary event ID.
3. Log agent metrics `input_records` không tăng, dù pod running.
4. Kiểm tra runtime path thấy agent còn dùng glob của định dạng container log cũ.
5. Sửa config agent ở staging, xác nhận canary được đọc và index hiển thị.
6. Rollout config đúng quy trình, monitor oldest pending backlog và lưu phạm vi dữ liệu có thể đã mất.
7. Cập nhật regression test cho path/format và alert “source canary emitted but not ingested”.

**Đây là ví dụ giả định**, không phải một sự cố đã xảy ra hay kết quả kiểm thử thực tế. Điểm học tập: write failures trong JVM bằng 0 hoàn toàn có thể đi cùng với **mất log tại agent**.

### Một tình huống khác: disk full gây chậm service

Nếu FileAppender đồng bộ chậm hoặc lỗi khi disk đầy, caller có thể bị ảnh hưởng. Đồng thời application error logs có thể không ghi được nên chính việc “log disk full” lại biến mất. Dấu hiệu thay thế: filesystem alerts, p99 request, thread dump, async queue occupancy, ErrorManager/status. Cách xử lý đúng là khôi phục dung lượng/quota hoặc tuyến sink theo runbook, không tiếp tục tăng log ERROR vào cùng ổ đang đầy.

## 19. Lỗi vận hành thường gặp

| Nhận định sai / lỗi thiết kế | Vì sao sai | Thực hành đúng |
| --- | --- | --- |
| “Không có ERROR log tức là không có lỗi” | Logger/sink/collector có thể hỏng hoặc bị filter | Dùng metrics nghiệp vụ, tracing, canary và status độc lập |
| “logger.info trả về nghĩa là log đã lưu” | Có thể chỉ enqueue hoặc write buffer | Định nghĩa ACK/durability theo hop |
| “App có file log mới nghĩa là backend có log” | Agent, collector hoặc index có thể lỗi | Truy vết từng hop bằng event ID |
| “Chỉ cần theo dõi Logback StatusManager” | Không biết mọi downstream drops/ingest failures | Kết hợp JVM, agent/collector/backend và canary |
| “Không thấy status error là đã ổn” | Silent filtering, queue discard và query sai không nhất thiết tạo error | Cross-check counts + synthetic events |
| “Queue lớn hơn giải quyết mọi nghẽn” | Tốc độ sink vẫn thấp hơn sản lượng lâu dài | Sửa throughput/volume, quan sát backlog age |
| “AsyncAppender không block business” | Queue full policy có thể block hoặc synchronous fallback | Đo enqueue wait và caller p99 |
| “Bật thêm ERROR logging để xem tại sao logger lỗi” | Có thể recursive failure hoặc log storm | Metrics/status channel tách biệt |
| “Collector báo 2xx = đã searchable/durable” | Response semantics có thể chỉ ACK ingest | Xác minh backend/index separately |
| “Ghi log lỗi từng attempt bằng raw exception” | Lộ PII/secret và tăng chi phí | Error categories, redaction và throttled diagnostics |
| “Sampled-out và dropped đều là mất log do lỗi” | Sampling là policy, overflow là failure/overload | Hai counters riêng với mẫu số rõ |
| “Tổng log volume ổn nghĩa là mọi pod ổn” | Một pod mất log bị các pod khác che | Per-instance/route canaries |
| “Canary không thấy => collector mất log chắc chắn” | Query sai, clock skew, chưa qua deadline | Phân biệt UNKNOWN/QUERY_ERROR/MISSING |
| “Mọi event đã ghi một lần là exactly-once” | Retry/fan-out/republish có thể duplicate | Stable event ID và idempotent pipeline |
| “Lỗi ghi log phải làm request fail” | Tùy mức quan trọng, thường diagnostic logs best-effort | Chọn fail-open/closed theo requirement |
| “TLS lỗi thì chuyển tạm HTTP” | Rò log nhạy cảm và mất identity verification | Sửa cert/trust/auth đúng quy trình |

## 20. Checklist production readiness

- [ ] Đã vẽ đầy đủ logging routes từ JVM tới sink cuối, gồm audit/security riêng nếu có?
- [ ] Đã phân biệt level filter, intentional sampling, queue overflow, write errors và backend rejection?
- [ ] Có metrics hoặc status signal từ logger/handler/appender phù hợp với backend thực tế?
- [ ] Lỗi ghi của appender không bị ghi đệ quy qua chính appender đang hỏng?
- [ ] Có counters ở các ranh giới `received`, `admitted`, `write attempted`, `write success/failure` khi cần?
- [ ] Có queue depth/capacity, blocked enqueue duration và dropped event counters nếu dùng async logging?
- [ ] Có filesystem free bytes/inodes, FD quota, container stdout/rotation monitoring?
- [ ] Agent/collector có metrics input, output, retry, rejected, backlog age và auth/TLS failure?
- [ ] Backend có ingest/index rejection và query visibility monitoring?
- [ ] Có canary log end-to-end không nhạy cảm, unique ID, deadline và checker độc lập?
- [ ] Có phân biệt canary NOT_SEEN với QUERY_ERROR/UNKNOWN?
- [ ] Metrics labels không chứa message ID, trace ID, user ID hoặc raw exception message?
- [ ] Alert theo service/environment/route/instance, không bị tổng volume che lỗi từng replica?
- [ ] Có policy riêng cho audit/critical events, durability và reconciliation?
- [ ] Fail-open/fail-closed, retry, spool, backpressure và shutdown đã được tài liệu hóa?
- [ ] Đã thử failure injection trong staging và xác minh alert thực sự tới nhóm vận hành?
- [ ] Có runbook, owner, escalation, rollback và postmortem/recovery plan?
- [ ] Không tự hạ cấp TLS, bỏ certificate validation hoặc gửi log nhạy cảm sang sink rộng quyền khi lỗi?
- [ ] Khi đã khôi phục, đã kiểm tra backlog drain, event ID duplicates, khả năng backfill và phạm vi dữ liệu mất?
- [ ] Không coi số counter thất bại bằng 0 là bằng chứng tuyệt đối không mất log?

**Tiêu chí hoàn thành:** Bạn xác định được log bị mất ở hop nào; đọc được tín hiệu lỗi từ JUL/Logback/Log4j 2 và hạ tầng; thiết kế metrics/canary/alert không lệ thuộc chính pipeline lỗi; chạy được ví dụ Java 17 phân biệt handler received, fake sink accepted, write failure và flush failure; và trình bày được runbook phục hồi có bảo vệ log quan trọng.

## 21. Câu hỏi tự kiểm tra

1. Vì sao `logger.error(...)` trả về bình thường vẫn có thể tương ứng với một lỗi ghi log?
2. Trong JUL, `Handler.reportError` và `ErrorManager` giúp theo dõi những lỗi nào? Chúng **không** giúp phát hiện những lỗi nào?
3. Logback `StatusManager` có phải counter mặc định của mọi event mất trên collector không?
4. Tại sao cần tách `sampled_out` khỏi `queue_dropped`?
5. Nếu stdout có canary nhưng agent input không tăng, nên kiểm tra những gì trước?
6. Nếu collector accepted tăng nhưng backend không tìm thấy event, có thể lỗi ở hop nào?
7. Vì sao một query trả về zero không phải bằng chứng chắc chắn log đã mất?
8. Khi queue async đầy, những tín hiệu nào cho thấy ứng dụng đang bị chặn bởi logging?
9. Vì sao metrics exporter/status callback không được gọi cùng logger/appender đang báo lỗi?
10. Tại sao “write success” không tự đồng nghĩa fsync hoặc backend durability?
11. Canary có chứng minh mọi audit event đã được lưu không? Cần thêm cơ chế gì với audit bắt buộc?
12. Làm sao phân biệt pipeline im lặng vì không có traffic với pipeline đã mất toàn bộ log?
13. Vì sao không dùng `trace_id` hay raw exception message làm metric labels?
14. Khi một replica mất log nhưng các replicas khác vẫn gửi đều, cảnh báo tổng volume có thể che sự cố ra sao?
15. Nếu TLS certificate của agent hết hạn, tại sao không tự động fallback sang plaintext?
16. Khi collector outage và agent retry, có thể có duplicate event hay không?
17. Mục tiêu của failure-injection test với disk full là gì ngoài việc tạo IOException?
18. Một ErrorManager callback bị lỗi liên tục có thể tạo những rủi ro production nào?
19. Nếu backend query unavailable, checker nên kết luận `MISSING` hay `UNKNOWN`?
20. Khi incident kết thúc, cần xác minh điều gì trước khi đóng sự cố log delivery?

## Tài liệu tham khảo

- [Java SE 17 — ErrorManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ErrorManager.html) — cơ chế nhận lỗi của Handler, các mã WRITE/FLUSH/OPEN/FORMAT.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — publish, flush, close và reportError.
- [Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — effective levels, hierarchy và xử lý records.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html) — config/status messages và status listener.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — FileAppender, ConsoleAppender, AsyncAppender và hành vi queue.
- [Apache Log4j 2 — Status Logger](https://logging.apache.org/log4j/2.x/manual/status-logger.html) — internal diagnostics/status.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html) — các appender và lỗi liên quan.
- [OpenTelemetry Collector — Internal Telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/) — theo dõi metrics của collector pipeline.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — log record, observed timestamp và ngữ nghĩa logging.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — security, data minimization, integrity và logging failure.
