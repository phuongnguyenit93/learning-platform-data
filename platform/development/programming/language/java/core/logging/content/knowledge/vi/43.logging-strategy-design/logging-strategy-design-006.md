# Chọn đích ghi log trong thiết kế chiến lược log Java

## 1. Đích ghi log là gì và tại sao cần thiết kế?

Trong Java, lời gọi `logger.info(...)` tạo ra một **log event**. Nhưng event có thực sự hữu ích không còn phụ thuộc vào nơi nó được chuyển đến: terminal, stdout/stderr của container, file, syslog/journald, log collector, nền tảng tìm kiếm tập trung hoặc kho audit có độ bền cao.

**Chọn đích ghi** là chọn cách **xuất, vận chuyển, lưu giữ và truy xuất** một loại log theo mục đích và ràng buộc vận hành. Đây là quyết định kiến trúc, không chỉ là một tham số `target=System.out`. Một cấu hình sai có thể khiến log:
- Không xuất hiện trong `kubectl logs` vì Java ghi vào file riêng.
- Bị mất khi container restart hoặc file rotate quá nhanh.
- Bị nhân đôi do logger additivity hay hai agents đọc cùng nguồn.
- Làm request chậm khi appender ghi đồng bộ tới remote service.
- Lộ thông tin nhạy cảm ở stdout, file, dashboard, alert hoặc bản export.
- Có sẵn trong console nhưng không bao giờ đến hệ thống truy vấn.
- Không đủ độ bền để làm chứng cứ audit.

**Ý tưởng trung tâm:** không có một đích ghi tối ưu cho mọi trường hợp. Diagnostic logs của microservice, security events và audit events bắt buộc có thể cần các đường đi và mức bảo đảm khác nhau.

### Mục tiêu học tập

Sau bài này bạn có thể:
1. Phân biệt logging API, logger, appender/handler, formatter, stream, collector và backend.
2. Đánh giá stdout, stderr, file, rolling file, syslog, remote transport và central logging.
3. Chọn chiến lược cho JVM trên máy phát triển, VM, Docker/Kubernetes, batch và hệ thống cần audit.
4. Hiểu trade-off về buffering, blocking, async queue, rotation, retry, loss và duplicate.
5. Viết chương trình **Java 17 chạy độc lập** xuất operational event ra stdout và security event ra file tạm.
6. Đọc cấu hình Logback/Log4j 2, thiết kế rule routing và kiểm thử end-to-end.

## 2. Phân biệt các lớp của đường log

Một luồng thường gặp:

```text
Java business code
        |
        v
SLF4J / JUL / Log4j API
        |
        v
Logger + level + filter + context
        |
        v
Handler / Appender / Encoder
        |
        +--------------+-----------------+
        |              |                 |
        v              v                 v
stdout/stderr     Rolling file     Network transport
        |              |                 |
        v              v                 |
Container runtime  File tail agent       |
        |              |                 |
        +--------------+-----------------+
                       |
                  Collector
                       |
               Buffer / Retry / TLS
                       |
                       v
                Central backend
                       |
              Search / Alert / Archive
```

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Logging facade/API** | Giao diện mà code sử dụng | SLF4J, `java.util.logging` |
| **Logger** | Tên logger, mức log, filters, truyền event | `com.example.orders` |
| **Appender/Handler** | Xuất event tới một hoặc nhiều đích | Logback ConsoleAppender, JUL FileHandler |
| **Encoder/Formatter** | Biểu diễn event thành text/JSON | Pattern encoder, structured JSON |
| **Đích trực tiếp** | Nơi JVM ghi bytes | stdout, stderr, file, socket, HTTP |
| **Collector/Agent** | Nhận, parse, enrich, buffer, ship | Agent trên node hoặc service trung gian |
| **Backend** | Lưu/index/truy vấn/retention | Log search service, archive |
| **Audit store** | Lưu bằng chứng bắt buộc theo contract riêng | Transactional table, outbox, protected append-only store |

**Đích trực tiếp khác đích lưu cuối.** Một ConsoleAppender gửi ra stdout; container runtime ghi xuống node; collector lại gửi tới backend. Khi `logger.info` trả về, nó chưa chứng minh rằng backend đã index record.

### 2.1. Event có thể được gửi đến nhiều đích

Một event ở cùng một JVM có thể được fan-out tới stdout và rolling file. Nếu collector thu **cả hai bản**, một business operation có thể trông như tạo hai events. Điều đó là vấn đề **duplicate ingestion**, không chứng minh nghiệp vụ chạy hai lần. Trước khi fan-out, phải biết mỗi đích có mục đích gì và có chồng chéo tuyến thu gom không.

### 2.2. Log level không đồng nghĩa với destination

`ERROR` không mặc định là stderr, `INFO` không nhất thiết là stdout. Mức độ log do framework quyết định; stdout/stderr là luồng dữ liệu. Alert severity lại là quyết định khác, dựa vào tác động và chính sách alert. Không lấy stream hay số dòng ERROR làm đại diện tuyệt đối cho sức khỏe hệ thống.

## 3. Những câu hỏi cần trả lời trước khi chọn đích

| Câu hỏi | Ảnh hưởng tới quyết định |
| --- | --- |
| Log nhằm debug, vận hành, bảo mật hay kiểm toán bắt buộc? | Độ bền, quyền truy cập và khả năng chứng minh |
| Nếu mất 1% INFO logs có chấp nhận được? | Best-effort vs durable pipeline |
| Nếu sink down trong 10 phút, nghiệp vụ được tiếp tục? | Drop, buffer, block hoặc fail closed |
| Peak throughput và kích thước record là bao nhiêu? | Queue, file size, network, CPU và disk |
| Ai cần đọc/truy vấn và trong bao lâu? | Centralization, IAM, retention, archive |
| Dữ liệu có PII hoặc security-sensitive fields? | Classification, encryption, masking, access audit |
| Chạy trên laptop, VM, Docker hay Kubernetes? | Console vs file, filesystem lifecycle |
| Một event có thể bị lặp do retry/collector? | Event ID, idempotent ingestion và count semantics |
| Cần search trong nhiều services? | Correlation ID, collector, structured schema |
| Có ngân sách lưu trữ/index/egress? | Sampling, retention, aggregation và event size |
| Ai sở hữu lỗi pipeline? | Monitoring, runbook, alert và rollback |
| Có thể thay vendor mà không sửa business code? | Facade/backend separation, collector |

**Đừng dùng một rule “mọi log đều tới file X” nếu mỗi loại log có nghĩa vụ khác nhau.** Đồng thời cũng không nên xây dựng hàng chục destinations khi một pipeline đơn giản có thể đáp ứng yêu cầu.

## 4. So sánh các đích ghi phổ biến

| Destination | Ưu điểm | Rủi ro/giới hạn | Trường hợp phù hợp |
| --- | --- | --- | --- |
| **stdout** | Đơn giản, thuận container, không tạo file ứng dụng | Pipe có thể nghẽn; runtime/agent có thể drop/rotate | Container application, CLI |
| **stderr** | Phân tách diagnostic/error trong công cụ hỗ trợ | Không tự gửi alert, thứ tự ghép stdout/stderr không chắc | CLI, chính sách hai streams |
| **Rolling file** | Có file cục bộ, dễ tail bởi agent | Quản trị rotation/disk/permission, ephemeral container | JVM trên VM, hệ thống legacy |
| **Syslog/journald** | Dùng dịch vụ logging của host | Phụ thuộc cấu hình OS, queue, retention, permissions | VM/host-centric deployment |
| **Network appender** | Gửi trực tiếp tới collector/remote endpoint | TLS, timeout, retry, queue và coupling với network | Tích hợp có kiểm soát |
| **Central collector** | Chuẩn hóa format/metadata, batch/retry, đổi backend dễ | Có thể duplicate, drop, lag; không mặc nhiên exactly-once | Microservices, nhiều nodes |
| **Database audit/outbox** | Có thể gắn audit row với business transaction | Tăng storage/write, cần schema và replay | Audit đòi hỏi độ bền cao |
| **Protected audit storage** | Cơ chế bảo vệ tính toàn vẹn, quyền độc lập | Phụ thuộc service contract, chi phí | Compliance/security audit |

**Không có cột “đảm bảo tuyệt đối”.** Mọi giải pháp phải được cấu hình, vận hành và kiểm thử theo yêu cầu cụ thể. Ví dụ stdout có thể đủ cho diagnostic nhưng không có transaction cùng database nghiệp vụ.

## 5. stdout và stderr của JVM

Trong Java:
- `System.out` là standard output.
- `System.err` là standard error.
- JUL `ConsoleHandler` mặc định ghi vào **System.err**.
- Logback `ConsoleAppender` cho chọn `System.out` hoặc `System.err`.
- Log4j 2 `Console` có target `SYSTEM_OUT` và `SYSTEM_ERR`.
- SLF4J là **facade**: đích thật do backend/provider và cấu hình.

Một số nền tảng collector gắn metadata `stream=stdout` hay `stream=stderr`. Nhưng không được suy ra:
- stderr được giữ lâu hơn stdout;
- một `logger.error` trên stderr đồng nghĩa người trực đã được page;
- timestamp/thứ tự hai streams luôn tương đương thứ tự thực thi trong code;
- đã ghi bytes ra stdout tức backend đã lưu;
- một physical line có nghĩa một event đã parse thành công.

### 5.1. Chọn console trong container

Với Java service chạy Docker/Kubernetes, cấu hình phổ biến:

```text
SLF4J + Logback
        |
Structured JSON ConsoleAppender
        |
stdout / stderr
        |
Docker/CRI runtime
        |
Node log files
        |
DaemonSet/collector
        |
Centralized backend
```

Ưu điểm: giảm quản lý file trong container, platform có thể gắn Pod/container/namespace metadata, query tập trung sau khi container bị thay. Nhưng cần biết kubelet rotation, collector checkpoint, ingest lag và backend retention. `kubectl logs` không phải một archive dài hạn.

### 5.2. Khi nào file trong container gây mất log?

Nếu Java ghi `/var/log/app/app.log` nhưng hạ tầng chỉ thu stdout/stderr, `kubectl logs` có thể không thấy log đó. Khi container bị thay, filesystem tạm có thể biến mất. Nếu muốn dùng file, phải có volume/persistence, agent tail file, rotation và owner rõ ràng.

## 6. Rolling file trên VM và hệ thống legacy

File vẫn là lựa chọn hợp lệ khi VM/bare-metal có file collector chuẩn hóa hoặc ứng dụng yêu cầu đường file cụ thể. Trước khi dùng, xác minh:

1. **Permission:** thư mục/file chỉ người cần thiết đọc/ghi, không world-readable nếu chứa dữ liệu nội bộ.
2. **Rotation:** theo size/time, số file giữ lại, xử lý đổi tên và nén.
3. **Disk quota:** log storm không làm đầy partition chứa hệ thống/database.
4. **Concurrency:** không để nhiều process JVM cùng đè/rotate một file nếu handler không hỗ trợ.
5. **Checkpoint:** agent theo dõi file qua rename/truncate/inode changes như thế nào?
6. **Retention:** local files giữ đủ lâu để agent ship và hỗ trợ sự cố ngắn.
7. **Storage security:** encryption, backups/snapshots, quyền export và legal hold nếu cần.
8. **Lỗi ghi:** nếu file không thể mở, appender báo trạng thái nào? Có metric/alert riêng không?
9. **Shutdown:** buffered events có được flush trong grace period hợp lý?
10. **Đường thu gom:** liệu cùng event còn được in stdout để collector khác lấy nữa không?

**Rotation cục bộ không phải retention backend.** Xóa file sau 7 ngày không xóa record đã index trong log service, snapshot, backup hoặc export. Ngược lại, backend giữ 30 ngày không cứu được những bytes mà agent chưa đọc trước khi file bị xóa.

### 6.1. Không biến path thành cơ chế phân quyền

Đặt tên file `security.log` không tự ngăn người có quyền đọc node, volume, backup hoặc root trong container. Classification phải được bảo vệ ở cả appender, file/volume, node, collector và backend. Nếu quyền đọc production logs rất nhạy cảm, cần mô hình hạ tầng phù hợp.

## 7. Ghi trực tiếp qua mạng: chọn khi đã hiểu failure mode

Một remote appender có thể gửi HTTP/gRPC/TCP/UDP hoặc giao thức riêng. Ưu điểm là JVM không cần một file local và có thể đi trực tiếp tới dịch vụ thu gom. Nhưng thêm sự phụ thuộc vào network vào đường thực thi logging.

Các rủi ro:
- Backend trả 429/503 hoặc timeout.
- DNS, TLS, certificate hoặc authentication lỗi.
- Appender buffer/queue tăng rồi đầy.
- Retry sau mất ACK làm duplicate.
- Network path đồng bộ chặn request thread.
- Java process crash khi bytes chưa rời queue.
- Credential ghi trong source/image, có quyền read/export quá rộng.
- Tắt appender trước khi flush xong.
- Thay backend bắt mọi microservice cập nhật dependency/config.

**Hãy định nghĩa hành vi khi sink không sẵn sàng**:
- Diagnostic INFO/DEBUG: thường ưu tiên không gây outage, có bounded buffer và telemetry cho drop.
- Security detection event: cần đánh giá yêu cầu không mất, đặc biệt khi incident đang xảy ra.
- Audit bắt buộc: có thể yêu cầu durable write trước business commit hoặc fail closed theo hợp đồng.
- Không nên cho một request tạo đơn hàng thất bại chỉ vì một DEBUG event không thể gửi, trừ khi requirement bắt buộc quy định khác.

### 7.1. TLS và quyền ingest

Collector/remote endpoint nên yêu cầu xác thực nguồn, TLS/mTLS phù hợp, write-only permissions với scope theo index/tenant. Không để client input điều khiển remote log destination; nếu không, có thể gây exfiltration hoặc SSRF thông qua cấu hình sai. Khi credential hết hạn, cần rotation và báo lỗi riêng, không in nguyên token vào log.

## 8. Collector và backend tập trung

Collector làm nhiều việc hơn chuyển bytes:
- Đọc node container logs, file hoặc journal.
- Parse Docker/CRI envelope gồm timestamp/stream/partial marker.
- Ghép partial/multiline records khi cần.
- Parse application JSON hoặc pattern text.
- Gắn Pod, namespace, service, environment và deployment metadata.
- Lọc/giới hạn kích thước, redact bổ sung theo policy.
- Batch, spool, retry/backoff và ship qua transport an toàn.
- Ghi metrics về parse failures, queue depth, dropped/exported records và ingest lag.

**Lợi ích chiến lược:** thay backend log không nhất thiết sửa toàn bộ Java code; application chỉ phát sự kiện với schema ổn định.

**Giới hạn:** agent cũng có thể bị mất checkpoint, crash, bị quota, file bị rotation, hoặc retry tạo duplicate. Một backend có document trùng không chứng minh Java thực thi hai lần.

### 8.1. Fan-out và duplicate ingestion

Một request có thể tạo ba log events khác nhau, tất cả dùng một `request_id`. Do đó **không dùng request ID làm khóa xóa trùng duy nhất**. Nếu cần dedup trong collector, dùng log event instance identity hoặc idempotent ingestion theo contract. Đồng thời kiểm tra có hai agents đang đọc cùng `/var/log/containers` hoặc cùng event được ship từ stdout và file hay không.

### 8.2. Thời gian có nhiều nguồn

Các trường thời gian có thể gồm:
- `event_time`: JVM tạo event.
- `container_time`: runtime ghi nhận stdout/stderr.
- `ingest_time`: backend nhận/index record.

Dữ liệu đến trễ do retry hoặc buffer khiến thứ tự dashboard khác thứ tự nghiệp vụ. Dùng correlation/trace ID và business event ID khi cần; không suy rằng request đã commit chỉ vì một log có timestamp trước log khác.

## 9. Chọn định dạng song song với đích ghi

Một đích có thể nhận plain text, JSON hay protocol có cấu trúc. Với hệ thống tập trung, **một JSON object trên một dòng vật lý** thường dễ parse và query.

Ví dụ event minh họa:

```json
{"timestamp":"2026-11-10T03:00:00Z","level":"INFO","service":"orders-api","event":"order_created","request_id":"req-42","result":"SUCCESS"}
```

Một schema tốt thường có timestamp, severity, service/env, event code, error code khi có, resource type, route template, duration, correlation/trace ID, outcome và schema version. Không đưa user ID hoặc request ID có cardinality cao làm **metric labels**.

**JSON encoder không tự che dữ liệu nhạy cảm.** Nếu payload có password và encoder tạo JSON đúng cú pháp, password vẫn bị lộ. Chọn allowlist fields ở Java call site và kiểm tra exception message/cause, MDC/ThreadContext và HTTP payload logging.

### 9.1. Multiline exception và partial fragments

Stack trace Java có nhiều dòng. Nếu collector coi mỗi dòng là record độc lập, một exception có thể thành hàng chục events mất context. Hai cách thiết kế thường dùng:
- JSON single-line: stack trace được escape thành `\n` bên trong field; encoder chuẩn bảo đảm JSON escaping.
- Text multiline: collector được cấu hình start-of-record rule để ghép stack frames đúng nguồn container/stream.

Ngay cả JSON một dòng, runtime có thể chia record quá lớn thành **partial fragments**. Collector phải hiểu định dạng CRI/Docker tương ứng, tránh ghép fragments của hai containers khác nhau.

Không log raw request body hoặc full binary upload chỉ để “có đủ dữ liệu”; việc đó làm tăng chi phí và khả năng rò rỉ.

## 10. Demo Java 17: ghi operational event vào stdout, security event vào file

Ví dụ **chạy độc lập trên JDK 17**, không dùng Maven/Gradle, sử dụng JUL `java.util.logging`. Nó cố ý route hai loại event:
- Operational log tới stdout qua `Handler` nhỏ.
- Security event minh họa vào file tạm qua JUL `FileHandler`.
- Sau khi flush file, chương trình đọc lại một event và in thông tin kiểm tra.

Đây chỉ là **mô hình routing**. File tạm không phải audit store bền vững hoặc bất biến, không gắn transaction cùng business operation. Chương trình không mô phỏng container runtime hay network collector.

Tạo file `LogDestinationDemo.java`:

```java
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogDestinationDemo {
    private static final class LineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName()
                    + " " + record.getMessage() + "\n";
        }
    }

    private static final class StdoutHandler extends Handler {
        private final PrintStream out;

        StdoutHandler(PrintStream out) {
            this.out = out;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                out.println("STDOUT " + record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override
        public void flush() {
            out.flush();
        }

        @Override
        public void close() {
            flush(); // Không đóng System.out.
        }
    }

    public static void main(String[] args) throws IOException {
        String fakeSecret = "fake-password-not-real";
        Path file = Files.createTempFile("java-log-route-", ".log");

        Logger operations =
                Logger.getLogger("lesson.destination.operations");
        Logger security =
                Logger.getLogger("lesson.destination.security");

        operations.setUseParentHandlers(false);
        security.setUseParentHandlers(false);
        operations.setLevel(Level.ALL);
        security.setLevel(Level.ALL);

        Handler console = new StdoutHandler(System.out);
        operations.addHandler(console);

        FileHandler fileHandler = null;
        try {
            fileHandler = new FileHandler(file.toString(), true);
            fileHandler.setFormatter(new LineFormatter());
            fileHandler.setLevel(Level.ALL);
            security.addHandler(fileHandler);

            operations.info("event=request_completed"
                    + " route=/orders status=200 requestId=req-42");
            security.warning("event=access_denied"
                    + " actor=anonymous resource=doc-9");

            fileHandler.flush();
            String stored = Files.readString(file, StandardCharsets.UTF_8)
                    .strip();
            System.out.println("FILE " + stored);
            System.out.println("secretInFile="
                    + stored.contains(fakeSecret));
        } finally {
            operations.removeHandler(console);
            console.close();
            if (fileHandler != null) {
                security.removeHandler(fileHandler);
                fileHandler.close();
            }
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy trong môi trường cho phép tạo file tạm:

```bash
javac LogDestinationDemo.java
java LogDestinationDemo
```

**Stdout chính xác**, với JVM mới và file tạm được tạo/ghi bình thường:

```text
STDOUT INFO event=request_completed route=/orders status=200 requestId=req-42
FILE WARNING event=access_denied actor=anonymous resource=doc-9
secretInFile=false
```

**Stderr:** chương trình không cố ý ghi dữ liệu lên stderr.

### 10.1. Giải thích hoạt động

1. `operations` và `security` là hai logger khác nhau. Chúng có handler riêng nên routing không cần lọc theo level.
2. `setUseParentHandlers(false)` tránh propagate lên JUL parent/root handlers, thường ngăn một bản ghi khác xuất stderr.
3. `StdoutHandler` in một dòng operational, không dùng timestamp động nên output cố định.
4. `FileHandler` dùng `LineFormatter` để ghi level/message tới file tạm. `flush()` bảo đảm bytes đã được flush ở tầng stream handler trước khi đọc trong demo; không chứng minh dữ liệu bền vững sau mất điện.
5. `FILE ...` là **dòng chương trình đọc file rồi in ra stdout**, không phải security logger tự gửi event sang stdout.
6. `fakeSecret` chỉ tồn tại trong RAM; không được đưa vào event. `secretInFile=false` kiểm tra file tạm, không chứng minh toàn pipeline production không ghi secrets.
7. `finally` đóng handler và xóa file, tránh giữ lại dữ liệu demo; không đóng `System.out` của JVM.

### 10.2. Những gì demo không chứng minh

- Không có tính bền vững transactional hay append-only audit.
- Không có kiểm soát concurrent writers trên cùng file.
- Không có rotation, quota, retention, encryption, IAM, collector, remote transport.
- Handler tự viết không phải logging backend được thiết kế cho workload đa luồng.
- Nếu process bị kill trước `finally`, file có thể còn.
- Có thể phát lỗi nếu máy không cho tạo/ghi file tạm; đây là điều kiện môi trường, không có stdout chuẩn khi lỗi.
- Không tự escape ký tự điều khiển trong message; production cần encoder/validator.

## 11. Logback: cấu hình đích bằng appender

Với ứng dụng dùng **SLF4J + Logback**, cấu hình `logback.xml` có thể route operational logs ra stdout và một nhóm logger đặc biệt vào file nếu platform có agent tail file phù hợp.

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level service=orders %logger{36} %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="SECURITY_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/var/log/app/security.log</file>
        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>/var/log/app/security.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.security.audit"
            level="INFO" additivity="false">
        <appender-ref ref="SECURITY_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Đây là **cấu hình tích hợp minh họa**, không phải lời khuyên dùng file cho audit bắt buộc. Cần có Logback đúng phiên bản, thư mục có quyền ghi, rotation/volume/collector/retention và quyền đọc phù hợp.

- Root logger nhận `STDOUT`; hạ tầng container thu logs theo console pipeline.
- Logger `com.example.security.audit` đi `SECURITY_FILE` và có `additivity="false"` để không tự chuyển tiếp lên root stdout.
- Nếu bỏ additivity=false, một security event có thể ra cả file lẫn stdout; có thể gây **duplicate ingestion hoặc lộ restricted event ra standard pipeline**.
- Nếu platform chỉ thu stdout, security file sẽ **không được ship** nếu không có file agent.
- `maxHistory` chỉ điều khiển lịch sử rolling files cục bộ theo policy, không quy định backend retention.
- Pattern `%msg` vẫn có thể mang newline hoặc secret; cần data minimization và structured encoding an toàn.

Một ứng dụng container thuần có thể **chỉ dùng một JSON ConsoleAppender**, rồi collector route theo source/metadata/classification đã xác minh. Điều đó giảm file management nhưng phải xác nhận người đọc standard index không thấy records restricted.

### 11.1. SLF4J không quyết định sink

Trong business code:

```java
// Mảnh code tích hợp, yêu cầu SLF4J và backend tương ứng.
logger.info("event=order_created orderId={} status={}",
        safeOrderId, "CREATED");
```

`logger.info` không cho biết dùng Logback hay Log4j 2, file hay stdout. Điều này là ưu điểm của facade: có thể đổi backend/routing theo môi trường. Nhưng `{}` không tự mask dữ liệu; `safeOrderId` phải được chọn/validate đúng chính sách.

### 11.2. Log4j 2 Console appender

```xml
<Configuration status="WARN">
  <Appenders>
    <Console name="Stdout" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{ISO8601} %-5level %c - %msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="Stdout"/>
    </Root>
  </Loggers>
</Configuration>
```

Đây là cấu hình minh họa của **Log4j 2**, không chạy độc lập như Java demo. `SYSTEM_OUT` là stdout, không phải bảo đảm về JSON, TLS, centralization hay persistence. Khi thêm appenders phải review filters, additivity và duplicate routing.

### 11.3. JUL mặc định ghi ConsoleHandler sang stderr

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
```

Mảnh `logging.properties` này chỉ cho JUL xuất console theo default ConsoleHandler; **không ép stdout**. Nếu collector chỉ thu stdout, cần thay handler hoặc đổi pipeline; không suy đoán dựa vào chữ “Console”.

## 12. AsyncAppender, file buffers và network backpressure

Mỗi tầng có thể mất hoặc giữ event tại một điểm:

```text
Caller thread
    |
    | logger level/filter
    v
Async queue (optional) ----> queue overflow: block/drop/reject
    |
    v
Encoder/handler
    |
    | file/pipe/socket write
    v
Container runtime / file agent
    |
    | rotation, checkpoint, retry
    v
Collector
    |
    | batch, TLS, quota, backoff
    v
Backend indexed / retained record
```

**Không đồng nhất các mốc:**
- **Accepted:** event vào logging layer.
- **Emitted:** bytes được ghi tới stdout/file/socket theo contract của appender.
- **Collected:** agent đã nhận/đọc.
- **Exported:** collector gửi theo transport có acknowledgement nào đó.
- **Indexed:** backend lưu và có thể query.
- **Retained:** log tồn tại trong khoảng thời gian policy yêu cầu.

Một appender trả về không nhất thiết chứng minh `Indexed`. Một collector trả ACK cũng chưa chắc tương đương audit transaction.

### 12.1. Blocking vs non-blocking

**Synchronous:** dễ hình dung nhưng network/file/stdout chậm có thể kéo business thread theo. **Asynchronous:** giảm thời gian ở caller khi bình thường, song queue có kích thước, giới hạn và policy khi đầy; crash trước flush có thể mất events.

Các tham số cần review:
- Queue capacity và enqueue timeout.
- Block/drop/reject behavior khi đầy.
- Worker thread và batch flush interval.
- Shutdown grace period và khả năng drain.
- Retention local buffer/spool và quota.
- Số event bị dropped và exporter retries.
- Concurrency và thứ tự giữa nhiều streams.

Đừng nhận định “bật async = không block” hoặc “ghi file = không mất log”. Phải kiểm tra cấu hình backend/version cụ thể.

### 12.2. Dữ liệu đến chậm và duplicate

Collector có thể gửi một batch thành công nhưng mất response ACK; retry làm backend index hai lần. Cũng có trường hợp stdout/file bị thu hai lần. Muốn đếm chính xác business operations, tốt hơn dùng metric/event business có semantics và identity rõ ràng, không dùng số document log thô.

### 12.3. Sự cố của chính pipeline

Khi appender/collector hỏng, không gọi logger.error qua chính appender hỏng để mô tả nó (có thể đệ quy hoặc không xuất được). Dùng internal status logger/health metrics độc lập, alert cho queue/drop/ingest lag và no-data checks.

## 13. Audit bắt buộc có thể cần kho khác stdout/file

Một event như “quản trị viên thay quyền người dùng” có thể cần:
- Actor, action, resource, kết quả thật, occurred_at và event ID.
- Bản ghi không bị xóa/chỉnh tùy ý.
- Đường truy xuất và quyền đọc/xuất riêng.
- Bằng chứng rằng thay đổi nghiệp vụ và audit record **cùng được commit**.
- Retention, legal hold và khả năng tra cứu theo yêu cầu.

Một chiến lược có thể dùng **outbox trong cùng transaction**:

```text
BEGIN TRANSACTION
  update business state
  insert audit/outbox event with unique event_id
COMMIT
   |
   v
Reliable publisher / retry
   |
   v
Protected audit store / downstream index
```

Giới hạn:
- Nếu cả business update và audit insert thuộc **cùng một database transaction**, cả hai có thể commit/rollback cùng nhau.
- Publish từ outbox sau commit có thể gửi lặp khi retry; downstream phải có idempotency/dedup.
- Side effects ngoài transaction (email, third-party API) cần idempotency key/reconciliation riêng.
- Một stdout write hay FileHandler flush **không đảm bảo atomic cùng database commit**.
- Kafka, syslog hay HTTP appender không tự trở thành immutable audit ledger chỉ vì được cấu hình bền hơn.
- Có thể cần append-only/WORM storage, signing, IAM, key management và audit người truy cập tùy yêu cầu.

Không sampling mù quáng sự kiện audit bắt buộc để giảm log volume. Nhưng cũng không ghi raw payload chỉ vì đây là audit; event schema phải chọn field cần thiết.

## 14. Bảo mật và retention theo destination

Một event có thể tồn tại tại:
- Stdout/stderr của process và node container files.
- Rolling file cục bộ, volume và backup.
- Collector queue/buffer hoặc local spool.
- Central index, object storage archive và snapshots.
- Dashboard, export CSV/ZIP, alert, email/chat hoặc incident ticket.

Đây là lý do **quyền đọc dashboard không phải toàn bộ bảo mật log**. Cần xem ingest/read/export/delete/configure/retention và archive IAM riêng.

### 14.1. Ghi đúng dữ liệu từ Java

Không đưa password, refresh/access tokens, API key, private key, session Cookie, raw Authorization header, body hoặc SQL bind values vào log. Dùng event codes, route templates, status, validated IDs và error categories.

Một event có thể là structured JSON hợp lệ nhưng vẫn lộ secret nếu chứa raw DTO. Redaction ở collector/dashboards chỉ là lớp phòng vệ bổ sung; bản gốc có thể đã được ghi ở stdout/file trước đó.

### 14.2. Phân quyền tuyến log

- Collector nên có **ingest-only** tới đúng destination, không read/export toàn hệ thống.
- On-call chỉ đọc datasets thuộc service/team/incident scope.
- Export cần permission và audit riêng, vì dữ liệu rời backend.
- Người sửa pipeline có thể gián tiếp redirect log sang nơi khác; cần change control và audit.
- Backup/object storage cần IAM và encryption keys được quản lý.
- Retention phải được xác định cho cả local file, central backend, archive và file export.

Nếu credential bị lộ trong log production, hãy ngăn việc ghi tiếp, xác định tất cả bản sao/sink, thu hồi hoặc rotate credential theo policy, rà soát quyền đọc và quy trình incident.

## 15. Chi phí: destination rẻ ở code có thể đắt ở vận hành

Ví dụ minh họa: một event 1 KiB, ứng dụng tạo 1.000 events/s. Đây là xấp xỉ 1 MiB/s **trước compression, indexing và replicas**. Nếu chạy liên tục, dung lượng thô mỗi ngày rất lớn; backend index và metadata có thể tăng storage thực tế thêm.

Nguồn chi phí:
1. CPU/GC khi format messages và stack trace.
2. Heap cho queue, serialization và object snapshots.
3. Disk cho rolling file, node logs và spool.
4. Network egress/transport và TLS.
5. Ingest/indexing/search và hot/cold storage.
6. Alert fatigue, false positives và công sức bảo trì pipelines.

Giảm chi phí đúng tầng:
- Không log raw request/response bodies.
- Dùng event schema gọn và mã lỗi ổn định.
- Chỉ log stack trace ở boundary phù hợp, tránh cùng exception được log ba lần.
- Đưa aggregates như error count, latency, queue depth vào **metrics** thay vì dump mọi object.
- Sampling DEBUG/TRACE có kiểm soát; giữ audit theo yêu cầu.
- Chọn retention khác nhau theo classification và mục đích.

**Không biến cost control thành silent loss**: nếu có drop/sampling, phải biết và có metrics; với evidence bắt buộc phải có đường riêng.

## 16. Ma trận lựa chọn theo tình huống

| Tình huống | Đích khởi đầu hợp lý | Điều bắt buộc phải xác nhận |
| --- | --- | --- |
| Java CLI học tập | stdout/stderr qua logger | Level, output, secret-free |
| Spring Boot container | Structured stdout → runtime → collector | Parse, rotation, metadata, loss |
| JVM legacy trên VM | Rolling file → agent | Disk quota, rotation, checkpoint |
| Batch/CI job | Console + archive khi cần | Execution ID, retention, flush |
| Debug traffic cao | Filter hoặc sampling, bounded pipeline | Không lộ PII, volume budget |
| Error diagnostics | Appender chính + central backend | Correlation, exception formatting, dedup |
| Security investigation | Restricted dataset với access audit | MFA/JIT/export restrictions |
| Mandatory admin/payment audit | Transactional outbox/protected store | Atomicity, idempotency, integrity |
| Edge/offline workload | Bounded local encrypted spool + retry | Overflow policy, storage durability |
| SLO alert | Metrics/SLI + alert manager; logs hỗ trợ điều tra | No-data, routing, runbook |

Từng dòng là **gợi ý điểm xuất phát**, không phải quy định bắt buộc. Nếu một container có audit quan trọng nhưng vẫn gửi qua stdout, cần nói rõ vì sao mức best-effort đó đáp ứng hoặc **không đáp ứng** contract.

## 17. Điều tra khi log không đến đích

**Bước 1 — Java có tạo event?** Kiểm tra code path, level, logger name, filter, provider, exception path và cấu hình logging thực tế. Với JUL, kiểm tra mặc định ConsoleHandler đi stderr; với Logback, kiểm tra root/child appenders và additivity.

**Bước 2 — Đích trực tiếp có bytes?** Đối chiếu stdout/stderr, file path, quyền ghi, disk/full quota, process entrypoint, appender errors và async queue drops.

**Bước 3 — Runtime/agent có đọc?** Trên container, dùng `docker logs`/`kubectl logs` theo quyền được cấp. Nếu file, xem agent tail đúng path, rotation/checkpoint. Tránh dùng các công cụ này làm chứng cứ đã centralize.

**Bước 4 — Collector có gửi?** Xem parse failures, multiline/partial handling, filters, TLS, retries, backlog, quota, log agent restarts và các metrics accepted/dropped/exported.

**Bước 5 — Backend có hiển thị?** Kiểm tra index/tenant, time range, event time vs ingest time, query labels, mapping, retention và quyền đọc.

**Bước 6 — Có duplicate?** So số logger invocations với stdout/file và số backend records. Nếu Java xuất một record mà backend có hai, nghi collector/fan-out/retry. Nếu Java đã log hai lần, nghi additivity hoặc duplicated instrumentation.

**Không bật TRACE toàn production** chỉ vì không thấy log. Dùng một event canary giả, đi qua từng chặng, xác định đúng điểm bị mất.

## 18. Kiểm thử thiết kế end-to-end

| Test | Kỳ vọng |
| --- | --- |
| Phát một INFO event | Đúng destination, đúng schema và số record |
| Phát ERROR có Throwable | Có code/context; stack trace parse đúng và không lộ bí mật |
| Child/root logger | Không double emission ngoài chủ đích |
| stdout + file fan-out | Không double ingest sai policy |
| Collector mất mạng | Bounded retry/drop/block như thiết kế |
| Appender async đầy queue | Có metrics và hiệu ứng latency/drop dự kiến |
| File rotate | Agent checkpoint đúng, không silently lose |
| Container restart | Backend giữ lịch sử theo retention riêng |
| CRI partial/multiline | Một event không bị đếm thành nhiều unrelated records |
| Backend trả quota/429 | Recovery hoặc failure policy được kiểm chứng |
| Shutdown/SIGTERM | Drain theo grace period; biết giới hạn SIGKILL |
| Secret giả trong request | Không có ở stdout, file, collector, index, notification |
| Audit outbox sau DB commit | Event tồn tại theo transactional contract |
| Viewer restricted dataset | Backend chặn quyền không hợp lệ |
| No-data collector | Health/synthetic/telemetry alert phát hiện |
| Query sau retry lag | Timestamp và ordering semantics rõ |

Một quy trình staging:
1. Chốt schema và đích thực tế cho từng loại log.
2. Phát event `event=log_pipeline_test` với correlation ID giả.
3. Đếm log tại JVM stdout/file rồi kiểm tra runtime.
4. Truy vấn collector/backend theo time window và service.
5. Thử lỗi network, rotation, restart và parse JSON/multiline trong môi trường test.
6. Đo CPU, memory, latency, queue, disk và dropped records.
7. Thử negative authorization cho các APIs export/search.
8. Ghi lại pipeline diagram, owner và runbook.

Không tạo outage production hay dùng credential thật để chạy thử.

## 19. Sai lầm phổ biến

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| `System.out.println` thay cho logger toàn bộ | Thiếu level, schema, context | Logging framework + appender |
| Nghĩ JUL ConsoleHandler ghi stdout | Collector bỏ stderr | Kiểm tra stream/config |
| Ghi file trong container nhưng không ship | Log biến mất khi pod thay | Console hoặc file agent+volume |
| Rolling file không rotation | Disk đầy | Quota/max history/monitoring |
| Rotate quá nhanh | Agent chưa đọc kịp | Sizing theo burst/outage |
| Direct network appender sync trong request | Backend outage kéo latency | Bounded async/collector |
| Tin async queue là durable | Crash/drop mất event | Biết failure policy; audit store riêng |
| Logback logger con và root cùng appender | Duplicated console records | Xem additivity |
| Tắt additivity không xem routing | Có thể mất audit/security log | Test từng logger path |
| stdout và file ship vào một index | Duplicate ingestion | Chọn canonical source |
| Coi stdout là audit ledger | Không atomic/integrity | Outbox/protected store |
| JSON tự nối raw user input | Log injection, invalid JSON | Encoder chuẩn + validation |
| Log full request body | Lộ secret, chi phí lớn | Allowlist metadata |
| Stack trace thành nhiều physical lines | Sai count/parser | JSON escaped hoặc multiline parser |
| Chỉ dựa vào log ERROR để phát hiện outage | Collector chết thì log biến mất | Meta-monitoring |
| Export log qua shared URL vô hạn | Rò dữ liệu | TTL, IAM, access audit |
| Không biết ai sở hữu sink | Không ai sửa khi pipeline lỗi | Owner và runbook |
| Tính số log là số giao dịch | Duplicate/sampling làm sai | Metric/business event đúng semantics |

## 20. Bài tập và đáp án

**Bài 1.** Một Java service trên Kubernetes dùng JUL ConsoleHandler mặc định. Collector chỉ thu stdout; vì sao không thấy record?

**Đáp án:** ConsoleHandler mặc định ghi **stderr**, không phải stdout. Hãy xác minh pipeline thu cả streams hoặc chuyển handler target phù hợp.

**Bài 2.** Một event được ghi stdout và file, cả hai cùng được ship tới backend. Hai documents có chứng minh Java xử lý hai business requests?

**Không.** Có thể là fan-out cùng một event. Cần so logger invocation, event instance ID và source metadata.

**Bài 3.** JVM đã gọi `FileHandler.flush()` trước khi commit database. Có bảo đảm audit transaction tồn tại nếu JVM crash không?

**Không.** File flush không tạo atomicity với business transaction. Dùng audit/outbox trong cùng transaction hoặc cơ chế bền vững được chứng minh.

**Bài 4.** Remote logger sync gặp network timeout, request latency tăng. Nên xem gì?

**Đáp án:** Đường network logging nằm trên request path; cần xem policy buffer/block/drop, async collector, deadline và business impact.

**Bài 5.** Một file giữ 7 ngày, backend 30 ngày. Xóa local file sau 7 ngày có xóa hết dữ liệu?

**Không.** Backend, backup, snapshots, exports có retention độc lập.

**Bài 6.** Mọi ERROR đi stdout. Có phải cấu hình sai?

**Không nhất thiết.** stdout là stream; event severity nằm trong log record. Điều cần xác minh là collector thu đúng stream và alert dựa trên tín hiệu thích hợp.

**Bài 7.** Không có log lỗi mới suốt một giờ nhưng người dùng không gọi API được. Điều gì có thể xảy ra?

**Đáp án:** Service hoặc telemetry pipeline có thể chết/không ingest. Cần synthetic health và no-data alerts.

**Bài 8.** Vì sao trong `LogDestinationDemo` có dòng `FILE WARNING ...` ở stdout nếu security logger chỉ ghi file?

**Đáp án:** Demo **đọc lại file và in một dòng xác nhận**. Đây không phải lần phát security event trực tiếp qua StdoutHandler.

## 21. Checklist áp dụng

1. **Mục đích:** định nghĩa riêng diagnostic, security và audit logs.
2. **Đích:** biết JVM ghi stdout/stderr/file/network và backend cuối là gì.
3. **Runtime:** thích hợp với VM/container, không bỏ quên file trong filesystem tạm.
4. **Schema:** timestamp, level, event code, service, error code, correlation được kiểm soát.
5. **Data minimization:** không ghi password, token, PII/raw payload không cần thiết.
6. **Routing:** không duplicate hoặc làm mất event do additivity/multiple appenders.
7. **Performance:** đo serialization, CPU/GC, queue, stdout blocking, disk/network.
8. **Failure policy:** mô tả block/drop/retry, restart và shutdown behavior.
9. **Centralization:** agent parse Docker/CRI/file/JSON/multiline và có checkpoint.
10. **Retention:** local rotation, backend retention, backup và export có chủ sở hữu.
11. **Audit:** nếu bắt buộc, chứng minh durability/atomicity/integrity riêng.
12. **IAM:** ingest-only collector; read/export/delete/configure không cấp chung.
13. **Monitoring:** drop/queue/lag/no-data/parse errors và alert owner.
14. **Testing:** end-to-end, failure injection, duplicate/loss, secret canary.
15. **Documentation:** sơ đồ pipeline, route từng logger, runbook sự cố sink.

## 22. Kết luận

**Chọn đích ghi** là chọn đường đi và mức bảo đảm phù hợp cho một loại log, không phải chỉ chọn ConsoleAppender hay FileHandler. Với dịch vụ Java container, **structured stdout → runtime → collector → central backend** thường là lựa chọn đơn giản, dễ quản lý. Với JVM trên VM, **rolling file → file agent** có thể phù hợp nếu rotation, permissions và checkpoints được kiểm soát. Với audit bắt buộc, cần thiết kế **transaction/outbox hoặc protected store** đáp ứng yêu cầu thực tế.

Một thiết kế tốt trả lời được: *log được phát ở đâu, có thể mất/lặp ở bước nào, ai được xem, giữ bao lâu, chi phí thế nào và điều gì xảy ra khi sink lỗi?* Khi các câu hỏi này có đáp án rõ và đã được kiểm thử, logging sẽ hỗ trợ điều tra thay vì gây thêm sự cố hoặc tạo cảm giác an toàn giả.