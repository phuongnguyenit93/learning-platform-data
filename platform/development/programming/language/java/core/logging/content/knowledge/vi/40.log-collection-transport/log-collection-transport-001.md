# Log collector trong Java: thu thập và vận chuyển log từ ứng dụng tới hệ thống tập trung

## 1. Mục tiêu

Trong một chương trình Java, lời gọi **logger.info**, **logger.warn** hay **logger.error** chỉ là điểm tạo ra sự kiện log. Muốn tìm log từ nhiều instance, nhiều container và nhiều dịch vụ tại một nơi, cần thu thập log từ nguồn, chuyển đổi về dạng thống nhất, chuyển tiếp đáng tin cậy và lưu vào backend thích hợp.

**Log collector** là thành phần thu nhận log từ file, stdout/container runtime hoặc giao thức telemetry, có thể parse, bổ sung metadata, lọc, gom batch và export tới một hoặc nhiều đích. Collector không đồng nghĩa với **SLF4J, JUL, Logback, Log4j2**, và cũng không phải mặc định là database hay dashboard.

Bài học giúp bạn:

- Phân biệt logger, appender/handler, agent, collector gateway, exporter, storage và viewer.
- Thiết kế luồng **Java → file/stdout/OTLP → collector → backend**.
- Hiểu mô hình **agent, sidecar, Kubernetes DaemonSet và gateway**.
- Hiểu pipeline **receiver → processor → exporter**, cùng parsing, enrichment, batch, queue, retry, checkpoint.
- Chạy ví dụ Java 17 độc lập mô phỏng **producer ghi file → collector đọc theo offset**, bao gồm duplicate sau khi restart không lưu checkpoint.
- Đọc cấu hình OpenTelemetry Collector minh họa và phân biệt component thuộc bản core/contrib.
- Biết kiểm thử file rotation, multiline Java stack trace, mất log, log trùng, log sai tenant, backend outage.
- Thiết lập metric và runbook để điều tra khi một event không xuất hiện trong dashboard.

## 2. Các tầng của hệ thống logging

Một kiến trúc thường gặp:

~~~text
Java Service A                    Java Service B
    |                                  |
    v                                  v
SLF4J/Logback                     JUL/Log4j2
    |                                  |
    v                                  v
stdout / file / OTLP              stdout / file / OTLP
    |                                  |
    +-------------+--------------------+
                  v
           Agent / Collector
                  |
                  +-- Receiver: file tail / OTLP / source khác
                  +-- Parser: JSON Lines, text, multiline
                  +-- Processor: enrich, redact, filter, batch
                  +-- Queue / retry / storage (khi hỗ trợ)
                  +-- Exporter: gửi backend/gateway
                  |
                  v
          Log storage / index
                  |
                  v
         Search / dashboard / alert
~~~

| Thành phần | Trách nhiệm | Điều không được mặc định |
| --- | --- | --- |
| **Logger API** | Tạo event từ mã Java. | Event đã được ghi bền vững. |
| **Logging backend** | Lọc, format và gửi tới handler/appender. | Collector đã nhận event. |
| **Agent gần nguồn** | Đọc log trên host, node hoặc pod. | Có thể đọc mọi file hoặc không bao giờ mất log. |
| **Collector gateway** | Nhận từ nhiều agent hoặc SDK; xử lý và chuyển tiếp. | Là hệ thống lưu trữ vĩnh viễn. |
| **Exporter** | Gửi dữ liệu sang backend hoặc collector khác. | Backend đã index và tìm được log. |
| **Storage/index** | Lưu, tra cứu, lưu giữ, phân quyền. | Không có record bị mất trước lúc ingest. |
| **Viewer** | Hiển thị và truy vấn dữ liệu đã lưu. | Truy vấn âm tính chứng minh log bị mất. |

Một event có thể không xuất hiện vì nhiều nguyên nhân: logger lọc DEBUG đúng policy, FileAppender lỗi disk, agent đọc sai path, parser lỗi, processor drop, exporter queue đầy, backend từ chối ingest hoặc dashboard tìm sai tenant/thời gian. **Mỗi ranh giới cần có bằng chứng riêng.**

## 3. Ba đường thu thập phổ biến của Java

### 3.1. Ghi stdout/stderr

~~~text
Java logger
   → ConsoleAppender / ConsoleHandler
   → container runtime / host log
   → agent
   → gateway / storage
~~~

Ưu điểm: ứng dụng không cần tự quản lý nhiều file; hợp với container. Nhưng cần kiểm tra **stdout hay stderr**, quyền đọc log runtime, container log rotation và cơ chế agent đọc dữ liệu. Ví dụ **JUL ConsoleHandler** thường ghi stderr, trong khi một ConsoleAppender khác có thể ghi stdout.

**Không mặc định stdout chống được mọi sự cố**: runtime có buffer, file log của container có retention, collector có thể chậm và node vẫn có thể mất dữ liệu khi disk đầy.

### 3.2. Ghi file rồi tail

~~~text
Java FileHandler / RollingFileAppender
   → /var/log/my-service/application.log
   → file receiver / tailing agent
   → processing + export
   → storage
~~~

Phù hợp hệ thống đang dùng log file hoặc cần buffer gần nguồn. Phải quản lý: **đường dẫn, quyền đọc, format, file rotation, timestamp, offset/checkpoint, disk quota, age của file cũ**. Nếu container thay thế trước khi agent đọc hết file trong ephemeral filesystem, log có thể biến mất.

### 3.3. Gửi telemetry qua OTLP

~~~text
Java logger + bridge/SDK/provider phù hợp
   → OTLP gRPC/HTTP exporter
   → Collector OTLP receiver
   → processors/exporters
   → backend
~~~

Ưu điểm: dữ liệu có cấu trúc phù hợp OpenTelemetry; có thể dùng cùng hệ sinh thái tracing/metrics. Nhược điểm: cần dependency/provider/exporter đúng, cấu hình endpoint, TLS, credentials, batch, queue và lifecycle shutdown. Không phải chỉ thêm một thư viện OpenTelemetry vào classpath là mọi SLF4J log sẽ tự động truyền đi.

**Tránh gửi cùng một event vào backend bằng hai đường không cần thiết**. Ví dụ cùng một log được gửi bằng OTLP trực tiếp và đồng thời bị agent tail từ stdout có thể thành **duplicate**.

## 4. Mô hình triển khai collector

| Mô hình | Đặt ở đâu? | Khi nào phù hợp? | Rủi ro |
| --- | --- | --- | --- |
| **Host agent** | Một process trên VM/host. | Máy có nhiều ứng dụng ghi file. | Quyền file, shared host, resource. |
| **Sidecar** | Container bên cạnh ứng dụng trong cùng Pod. | Cấu hình riêng theo workload, shared volume. | Chi phí mỗi Pod, vòng đời và shutdown. |
| **DaemonSet** | Thường một agent trên mỗi Kubernetes node. | Thu log container tập trung theo node. | hostPath và quyền truy cập log của nhiều Pod. |
| **Collector gateway** | Pool/deployment riêng. | Routing, centralized credentials, batch, policy và export. | Điểm nghẽn, overload, HA, retry. |
| **Direct SDK** | Phần instrumentation chạy trong JVM. | Gửi structured telemetry trực tiếp. | Chi phí SDK, network, resource và app lifecycle. |

Hệ phân tán thường dùng **agent → gateway**:

~~~text
Node A → Agent A ──+
Node B → Agent B ──+──> Gateway pool ──> Backend
Node C → Agent C ──+
~~~

Agent nắm nguồn file/container; gateway có thể kiểm soát route theo backend, credentials và export policy. Nhưng hai tầng tạo thêm các mốc phải giám sát: **agent accepted**, **gateway accepted**, **exporter sent**, **backend indexed**.

Chọn kiểu triển khai theo nơi dữ liệu phát sinh, yêu cầu isolation, số workload, lượng log và khả năng vận hành. Không có quy tắc rằng Java phải chạy sidecar hay bắt buộc dùng DaemonSet.

## 5. Pipeline OpenTelemetry Collector

OpenTelemetry Collector là một ví dụ phổ biến cho kiến trúc **receivers / processors / exporters**, ngoài ra còn có connectors và extensions.

### 5.1. Receiver

Receiver nhận log từ một hoặc nhiều nguồn:

- **filelog**: tail file theo glob, quản lý đọc file và các parsing operators.
- **otlp**: nhận telemetry qua OTLP HTTP hoặc gRPC.
- Các receiver khác có thể nhận dữ liệu từ những protocol/runtime cụ thể tùy bản phân phối.

Một receiver **được khai báo nhưng không được gắn vào service.pipelines.logs** thì chưa tham gia pipeline. Không dùng một tên receiver mà binary thực tế không đóng gói.

### 5.2. Processor

Processor có thể thực hiện:

- **Filter** những sự kiện có chủ đích bỏ.
- **Transform** field hoặc severity.
- **Resource enrichment**: service.name, deployment.environment.name, host/k8s metadata.
- **Redaction** theo chính sách dữ liệu.
- **Memory limiting** để giảm nguy cơ quá tải.
- **Batch** để giảm số lần gửi.

**Thứ tự xử lý quan trọng.** Memory limiter thường đặt đầu pipeline; batch thường đặt sau các bước lọc/transform trong những cấu hình dùng batch processor. Nếu filter loại WARN/ERROR vì rule sai, dữ liệu có thể mất dù logger Java phát event đúng.

### 5.3. Exporter

Exporter chuyển dữ liệu tới một hệ đích, ví dụ Collector gateway hoặc backend hỗ trợ OTLP. Exporter có thể hỗ trợ **sending queue, timeout và retry_on_failure**. Với debug exporter, dữ liệu được hiển thị để thử nghiệm, **không phải lưu bền vững vào kho production**.

Một exporter khai báo mà không được liệt kê trong service.pipelines.logs cũng không tự hoạt động.

### 5.4. Extensions và connectors

- **Extension** có thể cung cấp storage, authentication, health hoặc diagnostics.
- **Connector** có thể chuyển dữ liệu giữa các pipelines khi thiết kế cần.

Không phải mọi application log pipeline cần connector. Nếu cấu hình file storage extension mà quên thêm vào **service.extensions**, persistent queue có thể không hoạt động theo dự kiến.

## 6. Chuẩn hóa schema và định dạng log

Log collector làm việc dễ hơn nếu ứng dụng phát **structured logs**, tránh phụ thuộc regex trên message text.

Ví dụ một JSON log record:

~~~json
{
  "timestamp": "2026-11-10T03:20:01Z",
  "severity_text": "WARN",
  "event": "inventory.slow",
  "service.name": "order-service",
  "deployment.environment.name": "staging",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http.route": "/orders/{id}",
  "duration_ms": 920,
  "message": "Inventory call was slow"
}
~~~

Đây là dữ liệu minh họa, không phải output mặc định của Logback hay JUL.

| Field | Dùng để làm gì? | Chú ý |
| --- | --- | --- |
| **Timestamp** | Thời điểm event xảy ra ở nguồn. | Có timezone/UTC rõ ràng. |
| **Observed timestamp** | Lúc collector nhận event. | Có thể khác do backlog/clock skew. |
| **Severity** | Phân loại INFO/WARN/ERROR hoặc JUL levels. | Ánh xạ đúng backend, không suy ra từ HTTP status. |
| **Body** | Nội dung event. | Không để token/secret hoặc message quá dài. |
| **Service name** | Biết dịch vụ phát sự kiện. | Lấy từ deployment đáng tin cậy. |
| **Environment** | dev/test/staging/prod. | Không để staging gửi nhầm production. |
| **Trace ID** | Ghép logs với traces. | Có thể vắng; không tự tạo ID giả. |
| **Logger name** | Nhận diện class/package/category. | Giúp cấu hình level và tìm đúng nguồn. |
| **Event ID** | Phát hiện replay/duplicate khi cần. | Không bảo đảm dedup chỉ vì có ID. |
| **Tenant ID** | Phân vùng dữ liệu khách hàng. | Phải xác thực phạm vi; không tin client tự khai. |

### JSON Lines

Với file tail, mô hình **một JSON object trên mỗi dòng vật lý** là một lựa chọn dễ parse. Chuỗi message chứa CR/LF phải được **JSON encoder** escape trong string. Không tự nối JSON bằng dấu nháy hoặc dấu phân cách thô.

Một exception có stack trace nhiều dòng nên được serialise thành **một JSON string field** hoặc collector phải có cấu hình **multiline parser**. Không thể mặc nhiên coi mỗi dòng stack trace là một log event độc lập.

### Resource so với thuộc tính của event

Trong OpenTelemetry log data model, một số field mô tả **nguồn phát** (resource attributes, ví dụ service.name), còn một số mô tả **sự kiện** (log record attributes, ví dụ http.response.status_code). Phân biệt hai nhóm giúp chuẩn hóa pipeline và giảm việc lặp metadata trong mọi message.

## 7. Java 17 chạy độc lập: mô phỏng file collector

Chương trình sau minh họa cơ chế:

1. JUL Logger ghi hai event qua FileHandler vào file tạm.
2. FileCollector đọc file và in dạng đã chuẩn hóa.
3. Checkpoint đơn giản là **số dòng đã đọc trong RAM**.
4. Poll lần hai không in lại event.
5. Java append thêm một event; collector chỉ đọc dòng mới.
6. Mô phỏng restart **không lưu checkpoint**: collector mới đọc lại từ đầu, tạo nguy cơ log trùng.

Định dạng test là **LEVEL|event.name|event_id** với giá trị do chương trình kiểm soát. Đây **không phải định dạng production an toàn cho input không tin cậy**. Mục tiêu là cơ chế đọc và checkpoint, không phải viết một file tailer hoàn chỉnh.

### 7.1. File LogCollectorDemo.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogCollectorDemo {

    record Event(Level level, String payload) {
    }

    private static void writeBatch(
            Path path, boolean append, List<Event> events)
            throws IOException {

        Logger logger = Logger.getLogger("demo.orders.Application");
        Level previousLevel = logger.getLevel();
        boolean previousUse = logger.getUseParentHandlers();

        FileHandler file = new FileHandler(path.toString(), append);
        file.setEncoding(StandardCharsets.UTF_8.name());
        file.setLevel(Level.ALL);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + "|"
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);
        logger.addHandler(file);

        try {
            for (Event event : events) {
                logger.log(event.level(), event.payload());
            }
        } finally {
            logger.removeHandler(file);
            file.close();
            logger.setLevel(previousLevel);
            logger.setUseParentHandlers(previousUse);
        }
    }

    static final class FileCollector {
        // Checkpoint RAM; collector moi khong biet offset cu.
        private int nextLine = 0;

        void poll(Path path) throws IOException {
            List<String> lines = Files.readAllLines(
                    path, StandardCharsets.UTF_8);
            int from = nextLine;

            for (int i = from; i < lines.size(); i++) {
                String[] fields = lines.get(i).split("\\|", -1);

                boolean valid = fields.length == 3
                        && Set.of("INFO", "WARNING", "SEVERE")
                                .contains(fields[0])
                        && fields[1].matches("[a-z]+\\.[a-z]+")
                        && fields[2].matches("evt-\\d{3}");

                if (!valid) {
                    System.out.println("REJECT line=" + (i + 1));
                    continue;
                }

                System.out.println("INGEST service=orders"
                        + " level=" + fields[0]
                        + " event=" + fields[1]
                        + " event_id=" + fields[2]);
            }

            nextLine = lines.size();
            System.out.println("POLL new_lines="
                    + (lines.size() - from)
                    + " checkpoint=" + nextLine);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory(
                "java-log-collector-demo-");
        Path file = dir.resolve("application.log");

        writeBatch(file, false, List.of(
                new Event(Level.INFO,
                        "order.created|evt-001"),
                new Event(Level.WARNING,
                        "inventory.slow|evt-002")));

        FileCollector collector = new FileCollector();
        collector.poll(file);
        collector.poll(file);

        writeBatch(file, true, List.of(
                new Event(Level.SEVERE,
                        "payment.failed|evt-003")));

        collector.poll(file);

        System.out.println("RESTART without checkpoint:");
        FileCollector restarted = new FileCollector();
        restarted.poll(file);
    }
}
~~~

### 7.2. Biên dịch và chạy

Với JDK 17 trở lên:

~~~bash
javac LogCollectorDemo.java
java LogCollectorDemo
~~~

**Stdout dự kiến** trong một lần chạy thành công:

~~~text
INGEST service=orders level=INFO event=order.created event_id=evt-001
INGEST service=orders level=WARNING event=inventory.slow event_id=evt-002
POLL new_lines=2 checkpoint=2
POLL new_lines=0 checkpoint=2
INGEST service=orders level=SEVERE event=payment.failed event_id=evt-003
POLL new_lines=1 checkpoint=3
RESTART without checkpoint:
INGEST service=orders level=INFO event=order.created event_id=evt-001
INGEST service=orders level=WARNING event=inventory.slow event_id=evt-002
INGEST service=orders level=SEVERE event=payment.failed event_id=evt-003
POLL new_lines=3 checkpoint=3
~~~

### 7.3. Giải thích kết quả

- File được tạo trong một **thư mục tạm duy nhất**, tránh ghi đè file có sẵn. Đường dẫn ngẫu nhiên không được in ra, nên stdout ổn định.
- Logger được đặt level ALL, gắn FileHandler duy nhất và chặn parent handlers để không tự in thêm qua ConsoleHandler của JUL.
- Formatter chỉ ghi level và payload cố định, không có timestamp hoặc thread ID.
- FileHandler được **đóng trước lúc FileCollector đọc**, nên dữ liệu đã đi qua bước flush của handler.
- FileCollector lưu **nextLine** trong RAM; poll không có dòng mới thì new_lines=0.
- Sau append=true, event thứ ba nằm ở cuối file, được đọc một lần bởi collector ban đầu.
- Collector mới khởi tạo với nextLine=0 sẽ đọc lại cả ba record. Đây là **replay**; nếu downstream không deduplicate theo event ID thì có thể có log trùng.

### 7.4. Giới hạn của mô phỏng

**Không dùng chương trình này làm collector production** vì:

- Files.readAllLines đọc cả file vào RAM ở mỗi poll; không phù hợp file lớn.
- Offset là **số dòng**, không lưu byte offset, inode/file identity hoặc fingerprint.
- Không xử lý file rotation, rename, truncate, symlink hoặc multiple writers.
- Checkpoint chỉ ở RAM, mất khi restart.
- Không có network exporter, queue, retry, ACK hoặc persistent storage.
- Dòng parse lỗi bị in REJECT rồi vẫn tăng checkpoint; production cần policy quarantine/retry rõ ràng khi dữ liệu quan trọng.
- Không có TLS, authentication, redaction, rate limit hoặc multi-tenant isolation.
- Field format với dấu pipe không an toàn nếu input người dùng có delimiter/CRLF. Nên dùng encoder JSON thực.
- Mã demo chỉ test một thread và không kiểm chứng backend đã lưu event.

**Bài học cốt lõi:** file collector là thành phần **có trạng thái đọc**. Vị trí checkpoint, cách xử lý restart và quan hệ với exporter queue quyết định khả năng replay, mất dữ liệu hoặc duplicate.

## 8. Cấu hình OpenTelemetry Collector minh họa

Ví dụ dưới đây giả định một bản **OpenTelemetry Collector có filelog receiver** (thường là bản **contrib** hoặc distribution khác có component này). Không mặc định filelog có trong mọi bản core.

Giả sử log ở **/tmp/java-logs/application.log** trên một máy Linux thử nghiệm. Tạo file **collector.yaml**:

~~~yaml
receivers:
  filelog:
    include:
      - /tmp/java-logs/*.log
    start_at: beginning
    encoding: utf-8

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 256
    spike_limit_mib: 64
  batch: {}

exporters:
  debug: {}

service:
  pipelines:
    logs:
      receivers: [filelog]
      processors: [memory_limiter, batch]
      exporters: [debug]
~~~

**Cách hiểu:**

- **filelog** nhận các file khớp glob, bắt đầu từ beginning khi phù hợp trạng thái nguồn.
- **memory_limiter** giới hạn áp lực memory; cần chỉnh theo tài nguyên thực.
- **batch** gom telemetry để xuất.
- **debug** ghi dữ liệu để kiểm tra pipeline; **không phải kho lưu trữ production**.
- **service.pipelines.logs** thực sự bật và nối các component.

Đây là **cấu hình minh họa cần binary và môi trường phù hợp**, không phải một đoạn Java hoặc bảo đảm tự chạy trên mọi OS. Các component/config options có thể thay đổi theo release; hãy validate với binary đang dùng.

### 8.1. Kiểm tra binary và cấu hình

Ví dụ với binary tên **otelcol-contrib** đã được cài đặt hợp lệ:

~~~bash
otelcol-contrib components
otelcol-contrib validate --config=collector.yaml
otelcol-contrib --config=collector.yaml
~~~

Tên executable có thể khác theo packaging hoặc OS. Lệnh **components** dùng để xem distribution có **filelog, memory_limiter, batch, debug** không. Lệnh **validate** giúp phát hiện config không hợp lệ trước khi chạy.

Tạo dữ liệu thử trên Linux:

~~~bash
mkdir -p /tmp/java-logs
printf 'INFO order-created\nWARN inventory-slow\n' \
  > /tmp/java-logs/application.log
~~~

Dòng vừa tạo là **plain text để test receiver**, không phải JSON Lines và không cùng thư mục tạm Java của phần 7. Cần xác nhận đường dẫn **trong filesystem mà collector nhìn thấy**; khi collector chạy trong container, host path phải được mount đúng.

**Không dùng debug exporter trong production có PII hoặc secret** nếu nó sẽ in payload qua kênh có quyền đọc rộng. Khi chuyển sang backend thật, cần exporter, auth, TLS, queue và retention thích hợp.

### 8.2. Khi chạy rồi không có log

Kiểm tra lần lượt:

1. Binary thật có component filelog hay không.
2. Config file được đọc đúng.
3. service.pipelines.logs có tham chiếu filelog và exporter.
4. Glob path khớp file thật trong **filesystem của process collector**.
5. Process có quyền đọc file và traverse thư mục.
6. start_at có đang ở cuối file cũ nên chỉ chờ dòng mới không.
7. Debug exporter output đang ở stdout/stderr nào.
8. Receiver/processor có lỗi parse/filter hoặc memory limiter từ chối không.

Không tự đổi root logger Java sang DEBUG nếu vấn đề thực sự nằm ở agent đọc sai file.

## 9. Sending queue, retry và persistent storage

Trong production, Collector/gateway thường gửi qua mạng:

~~~text
Received events
      |
      v
Sending queue ---> Network exporter ---> Destination
      ^                   |
      +----- retry -------+
~~~

Ví dụ exporter **mang tính thiết kế**, chưa dùng được vì endpoint là tên giả:

~~~yaml
exporters:
  otlphttp:
    endpoint: https://otel-gateway.example.invalid
    sending_queue:
      enabled: true
      queue_size: 1000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 10m
~~~

**example.invalid** chỉ là placeholder phi kết nối. Muốn chạy cần endpoint thật, TLS trust, authentication và cấu hình đầy đủ trong **service.pipelines.logs**. Một số tên/giá trị exporter helper có thể khác theo phiên bản.

### 9.1. Sending queue không đồng nghĩa zero-loss

Queue giúp chịu **outage ngắn**. Nhưng:

- Queue hữu hạn có thể đầy khi backend chậm.
- Retry có giới hạn thời gian/capacity.
- Collector crash sẽ mất phần chỉ có trong RAM.
- Backend có thể đã nhận batch nhưng ACK thất lạc; retry có thể tạo duplicate.
- Sai credentials hoặc policy permission không tự được sửa nhờ retry.

**queue_size** thường tính theo **request/batch** ở exporter, không phải số log records. Dung lượng RAM thực tế còn phụ thuộc kích thước event và batch.

### 9.2. Persistent queue là một lớp bổ sung

Một số exporter hỗ trợ **file_storage extension** cho sending queue:

~~~yaml
extensions:
  file_storage:
    directory: /var/lib/otelcol/queue

exporters:
  otlphttp:
    endpoint: https://otel-gateway.example.invalid
    sending_queue:
      enabled: true
      storage: file_storage
      queue_size: 5000

service:
  extensions: [file_storage]
  pipelines:
    logs:
      receivers: [otlp]
      exporters: [otlphttp]
~~~

**Đây là đoạn minh họa chưa hoàn chỉnh**, thiếu khai báo receiver otlp và các chi tiết kết nối. Nó chỉ cho thấy **file_storage cần được khai báo và bật**, exporter tham chiếu storage.

Persistent queue có thể giúp phục hồi những batch còn chờ khi collector restart. Nhưng **disk đầy, mất volume, hỏng storage, retry exhaustion hoặc queue đầy** vẫn có thể gây mất dữ liệu. Nếu directory nằm trên ephemeral volume của container, tên "persistent" không có nghĩa còn dữ liệu sau Pod bị thay.

### 9.3. Phân biệt checkpoint và exporter queue

- **Source checkpoint:** file reader đã đọc tới vị trí nào.
- **Exporter sending queue:** event đã qua receiver/processors nhưng chưa giao xong tới đích.

Có checkpoint bền vững mà queue không bền vững có thể mất phần **đã đọc nhưng chưa gửi** sau crash nếu cơ chế ACK không phù hợp. Có queue bền vững nhưng mất checkpoint có thể **đọc lại file cũ**. Phải test cả hai trạng thái cùng pipeline.

## 10. File rotation, multiline và lifecycle

### 10.1. Rotation

Một file receiver thực phải xử lý:

- **Rename/create:** file cũ được đổi tên; file mới tạo cùng đường dẫn.
- **Copy/truncate:** nội dung file cũ được copy, rồi file nguồn bị làm rỗng.
- Quyền file mới có thể khác file cũ.
- File rotate có thể bị xóa trước khi agent đọc hết.
- Collector restart có thể mất mapping offset/file identity.

OpenTelemetry **File Log Receiver** hỗ trợ các cơ chế rotation phổ biến dựa vào nhận dạng file/fingerprint, nhưng kết quả vẫn phụ thuộc cấu hình, thời gian giữ file cũ, quyền truy cập và đặc tính filesystem. Không tự mặc định mọi rotation tool tương thích hoàn hảo.

### 10.2. start_at beginning và end

- **beginning:** hữu ích cho backfill/test; khi không có checkpoint phù hợp có thể đọc lại toàn file.
- **end:** phù hợp khi chỉ muốn log mới sau lúc bắt đầu theo dõi, nhưng có thể bỏ qua log lịch sử.

Checkpoint hiện có, version receiver và cách file được nhận dạng còn ảnh hưởng hành vi. Đừng chỉ nhìn **start_at** rồi kết luận collector chắc chắn không lặp hoặc không bỏ sót.

### 10.3. Java stack trace multiline

Một lỗi Java có thể có nhiều dòng:

~~~text
ERROR order.failed
java.lang.IllegalStateException: stock mismatch
    at com.example.orders.OrderService.reserve(OrderService.java:42)
Caused by: java.io.IOException: downstream unavailable
~~~

Nếu filelog đọc **mỗi dòng là một record**, stack trace sẽ thành những event thiếu level, timestamp. Hai giải pháp:

1. **Ưu tiên JSON Lines**, đưa stack trace vào một field string đã escape.
2. Với text legacy, cấu hình **multiline parser** xác định dòng bắt đầu event mới, timeout và giới hạn record size.

Tránh regex quá rộng khiến **hai sự kiện độc lập bị ghép làm một**. Test cả exception có **Caused by**, suppressed exceptions và log từ nhiều thread.

### 10.4. Restart, shutdown và file deletion

Collector có thể chưa đọc hết file khi application đóng. Nếu container log bị xóa sớm hoặc volume tạm biến mất, **queue/retry ở Collector không thể khôi phục những bytes chưa từng đọc**. Cần phối hợp application shutdown, log runtime retention, shipper lag và collector lifecycle.

## 11. Metadata và correlation

Một log đã tập trung nhưng thiếu **service.name, environment hoặc trace_id** sẽ khó dùng để điều tra.

Các trường thường hữu ích:

- **service.name**: dịch vụ nguồn.
- **deployment.environment.name**: dev/test/staging/prod.
- **logger.name**: class/package Java phát log.
- **host.name / host.id**: vị trí chạy khi được phép.
- **k8s.namespace.name / k8s.pod.name**: metadata Kubernetes khi có.
- **severity_text / severity_number**: mức log.
- **trace_id / span_id**: tương quan tracing nếu có.
- **event_id**: phát hiện duplicate/gaps cho các event quan trọng.
- **tenant_id**: phân vùng khách hàng với quyền đọc phù hợp.

Metadata cần có **nguồn đáng tin**. Không dùng client header làm tenant_id để cấp quyền hay route vào index nhạy cảm mà không xác thực. Một traceId được chép từ header cũng cần validate; nếu async context propagation bị hỏng, Collector không thể tự suy ra traceId đúng từ message không có ID.

**Cardinality:** không dùng URL thô chứa UUID làm metric label hoặc partition key nếu backend không phù hợp. Dùng **route template**, ví dụ **/orders/{id}**, và tách request ID vào trường có cơ chế index phù hợp.

## 12. Bảo mật cho pipeline log

Các lớp kiểm soát cần thiết:

| Ranh giới | Biện pháp |
| --- | --- |
| **Java application** | Không log password, access token, API key, Cookie, raw PII không cần thiết. |
| **Encoder** | Structured JSON và escaping đúng format; tránh log injection. |
| **Local file/stdout** | Quyền đọc tối thiểu, disk/rotation/retention phù hợp. |
| **Agent** | Chỉ mount/đọc những nguồn được phép; account không có quyền thừa. |
| **Collector receiver** | Bảo vệ cổng mạng; authentication khi nhận từ nguồn ngoài. |
| **Processor** | Redaction/filter theo chính sách, nhưng không thay thế bảo vệ ở nguồn. |
| **Exporter** | TLS, endpoint hợp lệ, scoped credentials, retry an toàn. |
| **Backend** | Tenant/environment isolation, RBAC, retention, encryption, audit truy cập. |
| **Dashboard/export** | Quyền truy vấn, chia sẻ, tải xuống và data residency phù hợp. |

**Redact ở Collector không thể xóa bản raw đã tồn tại trên node/file.** Nếu Java đã ghi secret vào stdout, việc processor xóa secret trước storage chỉ bảo vệ một phần đường đi. Phải sửa ứng dụng và xử lý bản sao đã phát sinh.

**Debug exporter** chỉ nên dùng trong môi trường thử nghiệm được kiểm soát. Nếu nó in log nhạy cảm vào Collector stderr, bạn đã tạo thêm một nơi cần phân quyền đọc.

**Log injection**: user input chứa CR/LF hoặc delimiter có thể tạo dòng log giả nếu được format thành text không escape. Giữ message/template cố định, validate IDs, dùng encoder structured và kiểm thử tới cả parser của Collector.

## 13. Collector observability: nhìn thấy đường đi của log

Một hệ thống thu log cần **tự có metric/health check**. Nếu Collector gặp lỗi nhưng chỉ thông báo bằng chính pipeline đang hỏng, rất khó phát hiện.

Một số chỉ số OpenTelemetry Collector có thể cung cấp, tùy phiên bản:

| Metric | Ý nghĩa |
| --- | --- |
| **otelcol_receiver_accepted_log_records** | Receiver chấp nhận record vào pipeline. |
| **otelcol_receiver_refused_log_records** | Receiver/pipeline từ chối log record. |
| **otelcol_exporter_sent_log_records** | Exporter báo gửi thành công. |
| **otelcol_exporter_send_failed_log_records** | Lỗi gửi; có thể đang retry, chưa chắc đã mất. |
| **otelcol_exporter_enqueue_failed_log_records** | Không thể enqueue, nguy cơ mất. |
| **otelcol_exporter_queue_size** | Độ dài queue hiện tại. |
| **otelcol_exporter_queue_capacity** | Tổng sức chứa queue. |
| **Process CPU / memory / uptime** | Sức khỏe của Collector process. |
| **Parse errors / file lag / dropped by reason** | Phụ thuộc receiver/backend, giúp định vị lỗi. |

Các tên metrics có thể đổi theo Collector version; xác nhận telemetry endpoint và danh sách metrics đang xuất.

**Không trừ ngay accepted - sent rồi gọi đó là số mất**: dữ liệu có thể còn trong batch, queue hoặc retry; multiple pipelines/sampling có thể ảnh hưởng mẫu số. Muốn đo completeness, dùng **event IDs của một tập thử nghiệm** và chờ đủ thời gian ingest.

### Cảnh báo gợi ý

- **refused/enqueue failed** tăng liên tục ở pipeline buộc phải giữ log.
- Queue utilization cao kéo dài và oldest pending age tăng.
- Exporter send failures kéo dài hơn sức chịu outage.
- Collector restart/OOM, persistent queue disk gần đầy.
- Log throughput từ một service giảm về 0 trong khi traffic vẫn có.
- Parsing errors tăng sau deployment thay format.
- Ingestion delay vượt SLO.

Không có một ngưỡng phần trăm đúng cho mọi ứng dụng; cần hiệu chỉnh theo lưu lượng, kích thước event và yêu cầu giữ dữ liệu.

## 14. At-most-once, at-least-once và duplicate

**At-most-once**: chỉ thử gửi một lần, ít duplicate nhưng có thể mất nếu lỗi.

**At-least-once**: retry/replay khi lỗi, giảm rủi ro mất nhưng có thể gửi trùng.

**Exactly-once**: cần hợp đồng end-to-end về identity, storage và acknowledgement; **không mặc định được bảo đảm** bởi FileAppender + Filelog Receiver + OTLP.

Tình huống điển hình:

~~~text
Collector gửi evt-001 tới backend
Backend đã lưu evt-001
ACK trên mạng bị mất
Collector retry evt-001
Backend có thể lưu thêm bản sao
~~~

Nếu cần so khớp, dùng **event_id**, source identity và quy tắc dedup của backend hoặc consumer. Với log vận hành thông thường có thể chấp nhận một số duplicate đã đo. Nhưng với **business event bắt buộc không được mất** (thanh toán, thay đổi trạng thái), cần transaction, outbox và broker/store bền vững phù hợp, không coi logger là durable event bus.

## 15. Hiệu năng và backpressure

Một collector có thể nhận record nhanh hơn khả năng backend nhận. Khi đó:

- Queue tăng.
- Batch chờ lâu hơn.
- Memory/disk pressure tăng.
- Khi đầy, pipeline có thể trả lỗi, block hoặc drop tùy component.
- Retry kéo dài gây độ trễ ingest.
- Một số log chỉ xuất hiện nhiều phút sau event time.

Các biện pháp:

1. Giới hạn volume ngay tại source; không in DEBUG mỗi vòng lặp production.
2. Sử dụng batching ở vị trí phù hợp để giảm network requests.
3. Đo **records/giây và bytes/giây**, không chỉ count.
4. Giới hạn queue theo burst và outage mà hệ thống cần chịu.
5. Thêm retry with backoff cho lỗi tạm; lỗi auth/TLS cấu hình sai cần sửa thực sự.
6. Scale agent/gateway theo CPU, RAM, queue và throughput khi hợp lý.
7. Thiết lập size limits để tránh một record rất lớn làm nghẽn pipeline.
8. Dùng compression nếu được hỗ trợ và đo trade-off CPU.
9. Phân biệt log có thể sampling với sự kiện audit/critical không được bỏ tùy tiện.
10. Kiểm tra thời gian drain lúc shutdown.

**Tăng queue size không chữa tận gốc backend chậm kéo dài**. Queue vô hạn tăng rủi ro OOM; queue RAM lớn tăng lượng log có thể mất khi process bị kill.

## 16. Test end-to-end theo từng ranh giới

Một test lý tưởng dùng tập event IDs giả, rồi xác minh ở từng mốc:

~~~text
Java emits evt-001
  → stdout/file có evt-001
  → receiver accepted evt-001
  → processor giữ evt-001
  → exporter gửi evt-001
  → backend index evt-001
  → query tìm được evt-001
~~~

### Ma trận kiểm thử

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Baseline 10 event IDs | Đúng số lượng và đúng schema/tenant. |
| INFO/WARN/ERROR từ Java | Severity mapping nhất quán. |
| CR/LF trong message | JSON Lines không sinh record giả. |
| Java stack trace multiline | Không tách thành nhiều event ngoài contract. |
| Dấu tiếng Việt, emoji | UTF-8 không bị hỏng. |
| File rotate rename/create | Không bỏ sót đoạn cuối hay đọc lại quá nhiều. |
| File copy/truncate | Offset/file identity đúng. |
| Collector restart | Checkpoint và queue phục hồi theo chính sách. |
| Queue full | Có metric drop/refused, không mất âm thầm. |
| Backend offline rồi phục hồi | Retry hồi phục trong giới hạn. |
| ACK thất lạc | Duplicate được phát hiện bằng event ID. |
| Collector không có quyền file | Lỗi được quan sát, không tự bịa log. |
| Source path/glob sai | Test phát hiện log không được nhận. |
| K8s Pod restart | Kiểm tra runtime retention và lag. |
| Hai đường stdout + OTLP | Không ingest cùng event hai lần ngoài ý muốn. |
| Tenant A/B | Không route hoặc query chéo tenant. |
| TLS/auth sai | Fail closed, không tự downgrade kết nối. |
| Oversized event | Có policy reject/truncate và metric. |
| Storage index chậm | Phân biệt late arrival với loss. |

Đừng chỉ so một query không có kết quả rồi kết luận event mất. Cần biết **mốc nào cuối cùng nhìn thấy event_id** và trong khoảng thời gian nào.

## 17. Quy trình điều tra khi thiếu log

Ví dụ ứng dụng orders có log:

~~~text
WARN inventory.slow event_id=evt-804
~~~

nhưng dashboard không thấy record.

**Bước 1:** Xác định logger thực sự phát sự kiện và appender đã ghi vào đâu. Kiểm tra effective level, exception và output.

**Bước 2:** Đọc nguồn được phép (stdout/file) theo event_id. Nếu file có log, xác minh agent có quyền đọc đúng path/glob và checkpoint.

**Bước 3:** Kiểm tra receiver accepted/refused, parsing/multiline, processor filter và metadata routing. Một event bị filter có chủ đích khác với queue drop ngoài ý muốn.

**Bước 4:** Kiểm tra exporter queue, retry, send failures, TLS/auth, endpoint và tình trạng gateway/backend.

**Bước 5:** Truy vấn backend theo service/environment/tenant và **event timestamp lẫn ingest timestamp**; xem index lag, retention và quyền đọc.

**Bước 6:** Sửa đúng điểm lỗi rồi thêm test/alert tại ranh giới đó. Không bật DEBUG root toàn production chỉ để chẩn đoán pipeline đang quá tải.

### Gợi ý từ triệu chứng

| Triệu chứng | Nơi cần kiểm tra |
| --- | --- |
| File có event, receiver accepted=0 | Glob, mount, permissions, start_at, offset. |
| Receiver accepted tăng, exporter sent không tăng | Processor drop, queue, network, retry. |
| Exporter sent tăng, dashboard không thấy | Backend index, tenant, timestamp, query. |
| Duplicate sau restart | Offset checkpoint, replay, exporter retry, hai agents. |
| Chỉ mất stack trace | Multiline parser, size limit, escaping. |
| Chỉ thiếu một Pod | Runtime log path, node agent, namespace routing. |
| Sau deployment mới bị lỗi | Schema, config version, level và permission drift. |

## 18. Những lỗi phổ biến

**1. Nghĩ collector và logging framework là một.** Java tạo log, collector vận chuyển log.

**2. Nghĩ logger.info() trả về là event đã được index.** Còn nhiều tầng xử lý phía sau.

**3. Khai báo receiver nhưng quên service.pipelines.logs.** Component không được bật.

**4. Dùng binary Collector thiếu filelog.** Core và contrib/distributions có components khác nhau.

**5. Hai agents cùng tail file.** Có thể sinh duplicate.

**6. Đồng thời xuất stdout và OTLP cho cùng event vào một backend.** Dễ trùng.

**7. Không lưu checkpoint nhưng dùng start_at beginning sau restart.** Có thể replay cả file.

**8. Dùng start_at end rồi đòi backfill dữ liệu cũ.** Có thể bỏ qua phần trước lúc theo dõi.

**9. Dùng số dòng làm checkpoint production.** Không xử lý chính xác rotation/truncation.

**10. Không cấu hình multiline cho text stack trace.** Một exception thành nhiều records.

**11. Parser tin dấu phân cách trong dữ liệu từ client.** Log injection/field injection.

**12. Tăng queue size thay vì sửa backend quá tải.** Độ trễ và memory pressure có thể tăng.

**13. Có retry nên khẳng định không bao giờ mất.** Queue đầy, retry timeout, disk failure vẫn có thể mất.

**14. Đặt persistent queue trên volume tạm.** Restart thay Pod có thể xóa queue.

**15. Không có collector internal telemetry.** Không biết pipeline đã chặn ở đâu.

**16. Gán tenant dựa hoàn toàn vào header không tin cậy.** Rủi ro gửi log sai nơi hoặc vi phạm phân quyền.

**17. Redact chỉ ở storage.** Raw log đã có thể nằm trên host và collector.

**18. Dùng debug exporter với dữ liệu nhạy cảm.** Tạo bản sao payload ở log collector.

**19. Không test quyền file sau rotate.** File mới có thể khác owner/group.

**20. Dùng log đếm request tuyệt đối khi pipeline có sampling/drop.** Metrics và log có semantics khác.

**21. Nhầm event timestamp với observed timestamp.** Query sai thời gian gây cảm giác mất.

**22. Quên verify destination.** Debug exporter PASS chưa có nghĩa backend production đã nhận/index.

## 19. Checklist trước khi triển khai

- [ ] Xác định nguồn log của JVM: stdout, file hoặc OTLP.
- [ ] Biết chính xác backend/provider đang dùng: JUL, Logback, Log4j2...
- [ ] Mỗi event có một đường xuất chính vào backend, trừ khi nhân bản có chủ đích.
- [ ] Binary collector có receiver/processor/exporter cần thiết.
- [ ] Receiver được khai báo **và bật trong logs pipeline**.
- [ ] Glob, path, mount, permission được test trên hạ tầng thật.
- [ ] JSON Lines hoặc multiline parser có test Unicode/CRLF.
- [ ] Resource fields service/environment/tenant đến từ nguồn đáng tin.
- [ ] Không log secret hoặc dữ liệu cá nhân không cần thiết.
- [ ] TLS/auth/RBAC cho agent, gateway, backend và dashboard.
- [ ] File rotation/retention không xóa file trước khi shipper đọc.
- [ ] Checkpoint/queue/retry đáp ứng khoảng outage mục tiêu.
- [ ] Queue và memory/disk limits có cảnh báo trước khi đầy.
- [ ] Metrics accepted/refused/sent/failed/queue có thể quan sát.
- [ ] Đã test restart, backend outage, duplicate, partial writes và schema changes.
- [ ] Query trên backend xác minh event_id sau khi index, không chỉ nhìn debug exporter.
- [ ] Có runbook và người chịu trách nhiệm cho mỗi tầng.

## 20. Bài tập

1. Chạy **LogCollectorDemo.java**, giải thích từng dòng **POLL** và vì sao restart sinh replay.
2. Thử sửa FileCollector để lưu checkpoint vào một file nhỏ. Nếu file nguồn rotate hoặc truncate, số dòng có còn đủ không?
3. Thiết kế event_id để kiểm tra duplicate sau exporter retry.
4. Chỉ ra bốn khối trong collector.yaml: receiver, processor, exporter, service pipeline.
5. Giải thích vì sao filelog receiver không phải component luôn có trong bản core.
6. Thiết kế test Java stack trace multiline và so sánh với JSON Lines.
7. Một dịch vụ ghi WARN vào file nhưng dashboard không thấy: nêu bằng chứng cần thu ở từng tầng.
8. Giải thích vì sao retry trên exporter không tự bảo toàn những log agent **chưa đọc**.
9. Thiết kế cách ly tenant A/B để một request có tenant header giả không thể định tuyến log sai.
10. Trong môi trường test cô lập, giả lập gateway offline rồi phục hồi; đo queue, retries, missing và duplicate event IDs.
11. Mô tả rủi ro khi dùng cùng một record vừa qua OTLP trực tiếp vừa qua node agent.
12. Viết cảnh báo cho collector queue quá đầy, backend send failures và log ingestion bị dừng đột ngột.

## 21. Kết luận

**Log collector kết nối hệ thống logging Java với hạ tầng quan sát tập trung.** Nó nhận record qua receiver, xử lý metadata/parser/filter, rồi gửi tới backend bằng exporter. Hiểu rõ **offset, rotation, queue, retry, storage, bảo mật và metrics** giúp phân biệt log được lọc có chủ đích với log bị mất, duplicate hoặc đơn giản là không tìm được trong dashboard.

Ba nguyên tắc cần ghi nhớ:

1. **Tách đúng trách nhiệm:** logger/backends trong JVM tạo event; collector thu thập và chuyển tiếp; storage/index chịu trách nhiệm tra cứu và retention.
2. **Theo dõi ranh giới:** đo accepted/refused/sent/failed/queue và dùng event ID khi cần kiểm tra completeness.
3. **Không tuyên bố zero-loss chỉ vì có retry:** checkpoint, persistent queue và ACK giúp giảm rủi ro nhưng không tạo exactly-once end-to-end mặc định.

### Tài liệu tham khảo chính thức

- OpenTelemetry Collector Configuration: https://opentelemetry.io/docs/collector/configuration/
- OpenTelemetry Collector Resiliency: https://opentelemetry.io/docs/collector/resiliency/
- OpenTelemetry Collector Internal Telemetry: https://opentelemetry.io/docs/collector/internal-telemetry/
- File Log Receiver (Collector Contrib): https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver
- OpenTelemetry Collector Exporter Helper: https://github.com/open-telemetry/opentelemetry-collector/tree/main/exporter/exporterhelper
- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Oracle Java SE 17 FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle Java SE 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html