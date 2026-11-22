# File shipper trong Java Core Logging: thu thập và vận chuyển log từ file

## 1. File shipper là gì?

**File shipper** là một tiến trình hoặc agent chuyên theo dõi file log trên máy, đọc các byte mới được ứng dụng ghi, đóng gói thành những bản ghi và **vận chuyển** tới Collector, message broker hoặc hệ thống log tập trung. Trong Java, ứng dụng thường phát thông điệp qua `java.util.logging` (JUL), SLF4J/Logback hoặc Log4j2; appender/handler ghi xuống file và shipper đọc file đó độc lập với ứng dụng.

```text
Java application
      |
      | logger.info(...) / logger.error(...)
      v
Logback / Log4j2 / JUL file handler
      |
      | append bytes
      v
app.log, app.log.1, ...             <- rotation/retention
      |
      v
File shipper
  discover -> read -> frame -> parse -> enrich
       -> buffer -> retry -> send -> checkpoint
      |
      v
Collector / broker / log backend
      |
      v
Search, dashboard, alert
```

Từ “shipper” nhấn mạnh công việc vận chuyển; thuật ngữ liên quan gồm **tailer**, **log agent**, **harvester**, **collector file input**. File shipper không thay thế logger API hoặc business logic. Nó **không thể thu lại** một sự kiện DEBUG đã bị tắt trước khi ghi file, và không tự bảo đảm một log đã đọc sẽ được index/query tại đích.

Một pipeline tốt phải trả lời được: agent đang đọc **file nào**, **từ vị trí byte nào**, đã **xử lý tới đâu**, một dòng có **hoàn chỉnh không**, đã được phía nhận **ACK theo cấp độ nào**, và khi process/file/đường mạng thay đổi thì **mất, trùng hoặc đọc lại** ra sao.

## 2. Khi nào cần file shipper?

Những trường hợp phổ biến:

- Java service chạy trên VM/bare metal, ghi rolling files, cần gom log từ nhiều máy về một backend.
- Một máy chạy nhiều ứng dụng; shipper gắn `service.name`, environment, host và version vào record trước khi gửi.
- Doanh nghiệp muốn tách nhiệm vụ: ứng dụng chỉ ghi file, agent có credential/network permission để chuyển dữ liệu.
- Cần buffer, retry và state/checkpoint độc lập với vòng đời của Java process.
- Có ứng dụng legacy chỉ có `FileHandler` hoặc file appender, chưa tích hợp exporter.

Nhưng **không phải cứ có Java logging là phải dùng file shipper**. Trên Kubernetes, cách thường được khuyến khích là ghi log ra **stdout/stderr** và để node agent thu container logs. Ứng dụng cũng có thể phát OTLP Logs qua SDK/appender/Collector tương thích. Nếu vừa đọc stdout vừa ship file chứa cùng event, backend có thể thấy log trùng và tốn ingest/storage gấp đôi.

| Môi trường | Mô hình thường chọn | Rủi ro phải kiểm |
| --- | --- | --- |
| VM hoặc bare metal | Rolling file + local agent | File permissions, rotation, registry, disk đầy |
| Kubernetes | Stdout/stderr + node-level collection | Container runtime rotation, pod/node restart |
| Container có file riêng | Sidecar/agent đọc shared volume | Ephemeral volume, startup/shutdown sequencing, duplication |
| Serverless | Platform logging hoặc telemetry exporter | File không sống đủ lâu, không có agent |
| Audit nghiệp vụ bắt buộc | Durable audit/outbox và đường export phù hợp | File shipper không nguyên tử với DB transaction |

Một lựa chọn “trung gian” có thể là Java ghi vừa stdout vừa file. Chỉ làm vậy khi có **mục đích riêng cho từng sink** và chính sách chống trùng; không tự bật cả hai rồi đo số log ở backend như một bộ đếm nghiệp vụ.

## 3. Vòng đời một file log

Các bước khái quát:

1. **File discovery:** quét đường dẫn/glob, ví dụ `/var/log/orders/*.log`, xác định file đang tồn tại và file mới.
2. **File identity:** nhận ra file theo danh tính ổn định trong phạm vi hỗ trợ (inode/device, file key, fingerprint...), thay vì chỉ theo tên.
3. **Open/read:** đọc bytes từ một offset, xử lý những byte mới được append.
4. **Framing:** xác định ranh giới event theo LF/CRLF hoặc multiline parser.
5. **Parsing/enrichment:** parse JSON/text, gắn metadata service/host, chỉnh timestamp và redact nếu cần.
6. **Buffer/output:** xếp queue, batch, nén nếu có, gửi tới Collector hoặc backend.
7. **ACK/commit:** ghi lại tiến độ tại thời điểm phù hợp với hợp đồng delivery.
8. **Cleanup:** đóng reader, xử lý rotation/truncation, kiểm checkpoint và retention.

```text
File discovery
    |
    +-- app.log     identity=A   offset=1200
    +-- app.log.1   identity=B   offset=9800
    |
Reader/harvester per file
    |
records with event boundaries
    |
queue + retry + output
    |
registry/checkpoint
```

Tên component cụ thể khác nhau giữa Filebeat, Fluent Bit, Vector và OpenTelemetry Collector. Không giả định một tùy chọn có cùng tên/hành vi trên các shipper.

### Offset được tính bằng byte, không phải ký tự

Nếu file UTF-8 dài 25.000 byte, checkpoint `offset=12.000` chỉ một **vị trí trong chuỗi byte**. Java `String.length()` là số UTF-16 code units, không thể dùng thay offset byte của file. Với tiếng Việt và ký tự Unicode, một ký tự có thể được mã hóa thành nhiều byte UTF-8.

Để reader chính xác, shipper cần xử lý **byte boundaries**, đồng thời decoder phải tránh giải mã một sequence chưa hoàn chỉnh. Offset được cập nhật sau khi đã xác định record và tùy hợp đồng commit/ACK.

### File path không phải file identity

Tên `app.log` có thể trỏ tới file cũ hôm qua và một file hoàn toàn mới hôm nay. Khi rename/rotate, cùng file có thể đổi tên nhưng vẫn giữ identity. Chỉ lưu `app.log + offset` có thể làm:

- Đọc lại toàn bộ dữ liệu cũ khi không nhận ra identity đã có.
- Bỏ qua phần đầu file mới vì dùng offset của file cũ.
- Bỏ sót đoạn cuối của file đã bị rename nhưng vẫn còn bytes chưa đọc.

Một số shipper sử dụng inode/device trên Linux, file key trên hệ thống tệp khác hoặc fingerprint nội dung đầu file. Mỗi chiến lược có giới hạn: inode có thể được tái sử dụng, fingerprint có thể chưa đủ dữ liệu khi file quá ngắn, copytruncate giữ identity dù nội dung thay đổi. Cần thử với **filesystem và rotation policy thật**.

## 4. Framing: ghép byte thành một log event

File được ghi thành **byte stream**, không phải một danh sách object Java. Mỗi lần logger gọi `write` không nhất thiết bằng đúng một lần shipper đọc. Một event có thể được ghi thành nhiều mảnh; cũng có thể một lần đọc mang nhiều events.

Ví dụ sau lần ghi thứ nhất:

```text
INFO started\n
WARN partial
```

Đọc tới đây chỉ có **một dòng hoàn chỉnh**. Lần ghi thứ hai:

```text
 warning\n
ERROR timeout\n
```

Shipper cần gửi tổng cộng ba events: `INFO started`, `WARN partial warning` và `ERROR timeout`. Nếu xuất `WARN partial` ngay ở lần đầu, event có thể bị cắt sai.

Điểm quan trọng khi thiết kế framing:

- **Line delimiter:** thường LF (`\n`), có thể nhận CRLF (`\r\n`); tránh lưu ký tự CR thừa trong message.
- **Unterminated final line:** shipper có thể giữ lại cho tới khi có LF, timeout hoặc file close/rotate theo chính sách; không mặc định được gửi.
- **Max record length:** dòng rất dài có thể bị truncate/reject; cần metric parse error/drop và giới hạn payload ở nguồn.
- **Charset:** UTF-8 nhất quán từ Java encoder qua shipper; decoder cần chính sách malformed bytes.
- **Nhiều writers:** bytes có thể xen kẽ khi nhiều process ghi cùng file mà không có cơ chế khóa/format phù hợp.
- **Buffered I/O:** logger có thể chờ flush; shipper chỉ đọc được bytes đã hiện diện trên file.

**Đừng dùng `URLDecoder` hoặc xử lý text theo ký tự để tính offset file.** Cần phân biệt parsing message với vị trí byte của reader.

## 5. Rolling file và hai kiểu rotation quan trọng

### Rename-and-create

```text
Trước:
  app.log    (identity A, size 10 MB)

Rotation:
  rename app.log -> app.log.1
  create new app.log

Sau:
  app.log.1  (identity A, có thể còn tail chưa đọc)
  app.log    (identity B, đọc từ offset 0)
```

Shipper cần tiếp tục đọc phần còn lại của identity A dù đường dẫn đổi, đồng thời tạo reader mới cho identity B. Nếu ứng dụng vẫn giữ file descriptor cũ, nó có thể tiếp tục ghi vào file đã rename; cần xác định khi nào đóng reader A an toàn.

### Copytruncate

```text
copy app.log to app.log.1
truncate app.log to length 0
application continues writing app.log
```

Ở copytruncate, identity của file active có thể **không đổi** nhưng kích thước giảm về 0. Rủi ro nghiêm trọng: ứng dụng ghi bytes mới **giữa copy và truncate**, các bytes đó chưa nằm trong bản copy nhưng bị xóa khi truncate. Shipper không thể tái tạo dữ liệu đã biến mất khỏi cả hai file. Reset offset khi thấy size nhỏ hơn checkpoint có thể giúp đọc lại, **không sửa được race mất bytes**.

Khi có lựa chọn, thường ưu tiên rolling do framework logging phối hợp và shipper hỗ trợ identity/rename hơn là dùng copytruncate không được kiểm chứng. Tuy nhiên cần thử thực tế với hệ điều hành, appender, writer và agent; không có chiến lược phù hợp tuyệt đối cho mọi nền tảng.

### Compression và retention

File rotate có thể chuyển sang `.gz` hoặc bị xóa theo retention. Nhiều tail shippers **không tự đọc file nén như một active log**; việc nén/xóa trước khi shipper hoàn tất sẽ làm mất khả năng gửi. Phải điều chỉnh:

- File giữ trên đĩa lâu hơn **worst-case shipper lag + recovery margin**.
- Glob và cơ chế identity không đọc trùng active/rotated.
- Shipper còn truy cập được file cũ sau rename, ngay cả khi appender đã chuyển file.
- Compression không chạy quá sớm khiến agent mất bản gốc chưa gửi.
- Disk quota và retention được giám sát để không làm Java process bị ảnh hưởng khi đích log ngừng nhận.

Không nên chỉ đặt `maxHistory=1` rồi mong pipeline chịu được sự cố mạng kéo dài cả ngày.

## 6. Checkpoint, ACK và delivery semantics

### Checkpoint thực sự nghĩa là gì?

Một registry/checkpoint có thể lưu vị trí đã **đọc**, đã **parse**, đã **xếp queue**, hoặc đã được **output ACK**. Sự khác biệt quyết định mất/trùng log khi crash.

```text
Read from file
   |
Parse event
   |
Enqueue
   |
Send to destination
   |
ACK at some layer
   |
Commit checkpoint
```

Nếu checkpoint ghi trước khi event được gửi thành công, crash ở khoảng trống sau đó có thể tạo **data loss**. Nếu gửi xong nhưng ACK bị mất rồi retry, backend có thể nhận **duplicate**. “Agent đã ship thành công” còn cần định nghĩa là Collector nhận HTTP 200, message broker durable commit, hay event đã queryable ở storage cuối.

| Mức bảo đảm | Ý nghĩa giới hạn | Đánh đổi |
| --- | --- | --- |
| **At-most-once** | Một event được thử gửi tối đa một lần theo contract | Có thể mất khi failure |
| **At-least-once** | Event có thể được gửi lại sau lỗi trong các điều kiện đảm bảo đã nêu | Có thể trùng, cần dedup |
| **Exactly-once effect** | Kết quả logic chỉ được áp dụng một lần trong ranh giới có transaction/idempotency | Không tự có từ tailing hay retry; phải thiết kế backend |
 
Log event nên có **event ID ổn định** khi cần đối chiếu hoặc chống trùng. Một request có thể tạo nhiều log events, vì vậy `request_id` không luôn là khóa dedup thích hợp. Ngay cả khi same exception được log ở nhiều tầng, đó là **duplicate semantic logging**, khác với một event gửi lại nhiều lần do mất ACK.

**Audit/billing bắt buộc** không nên chỉ dựa vào file shipper để đồng bộ với thay đổi dữ liệu nghiệp vụ. Để đảm bảo atomicity giữa transaction DB và audit event, có thể cần transactional outbox hoặc kho audit bền vững riêng.

## 7. Ví dụ Java 17 chạy độc lập: byte offset và partial line

Chương trình sau dùng **chỉ JDK 17+**. Nó tạo file log tạm, ghi một dòng hoàn chỉnh và một dòng chưa kết thúc, sau đó mô phỏng ba lần poll của shipper. State được lưu ở một file checkpoint riêng; mỗi lần poll lấy offset từ file đó.

Ví dụ chỉ chứng minh **offset theo byte và framing theo LF**; nó cố ý không mô phỏng cloud backend, rotation, ACK hay giao dịch. Không dùng code này làm shipper production.

Lưu thành tệp **`FileShipperDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FileShipperDemo {
    private static void ship(Path logFile, Path checkpointFile)
            throws IOException {
        long offset = Files.exists(checkpointFile)
                ? Long.parseLong(
                        Files.readString(
                                checkpointFile,
                                StandardCharsets.UTF_8).trim())
                : 0L;

        // Demo đơn giản: đọc toàn bộ file nhỏ vào RAM.
        byte[] bytes = Files.readAllBytes(logFile);
        if (offset < 0 || offset > bytes.length) {
            throw new IOException("Checkpoint does not match file size");
        }

        int start = Math.toIntExact(offset);
        int committed = start;

        for (int i = start; i < bytes.length; i++) {
            if (bytes[i] != (byte) '\n') {
                continue;
            }

            int length = i - start;
            if (length > 0 && bytes[i - 1] == (byte) '\r') {
                length--;
            }

            String line = new String(
                    bytes, start, length, StandardCharsets.UTF_8);
            System.out.println("SHIP " + line);

            start = i + 1;
            committed = start;
        }

        Files.writeString(
                checkpointFile,
                Integer.toString(committed),
                StandardCharsets.UTF_8);
        System.out.println("CHECKPOINT=" + committed);
    }

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("file-shipper-demo-");
        Path logFile = folder.resolve("app.log");
        Path checkpointFile = folder.resolve("checkpoint.txt");

        try {
            Files.writeString(
                    logFile,
                    "INFO started\nWARN partial",
                    StandardCharsets.UTF_8);

            ship(logFile, checkpointFile);

            Files.writeString(
                    logFile,
                    " warning\nERROR timeout\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.APPEND);

            ship(logFile, checkpointFile);
            ship(logFile, checkpointFile);
        } finally {
            Files.deleteIfExists(checkpointFile);
            Files.deleteIfExists(logFile);
            Files.deleteIfExists(folder);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac FileShipperDemo.java
java FileShipperDemo
```

**Stdout chính xác:**

```text
SHIP INFO started
CHECKPOINT=13
SHIP WARN partial warning
SHIP ERROR timeout
CHECKPOINT=48
CHECKPOINT=48
```

Giải thích:

1. `INFO started\n` dài **13 bytes** UTF-8 (ở đây toàn bộ ký tự là ASCII), nên checkpoint lần một là 13. `WARN partial` chưa có LF nên bị giữ lại.
2. Ứng dụng append ` warning\nERROR timeout\n`, tạo hai record hoàn chỉnh. Reader tiếp tục từ byte 13, xuất `WARN partial warning` rồi `ERROR timeout`.
3. Hai record mới chiếm lần lượt 21 và 14 byte, tính cả LF. Offset mới là 13 + 21 + 14 = **48**.
4. Poll thứ ba không có newline sau offset 48 nên chỉ in `CHECKPOINT=48`, không gửi lại các dòng trước.

**Những giới hạn không được bỏ qua:**

- `Files.readAllBytes` nạp cả file vào memory, không thích hợp file lớn; production dùng streaming reader/buffer và resource management.
- Không lưu **file identity**, không tự phát hiện rename/recreate/copytruncate. Khi file mới có size ≥ offset cũ, demo có thể bỏ đầu file; khi nhỏ hơn nó ném exception.
- Checkpoint chỉ lưu số offset, không atomic/fsync; crash giữa ghi checkpoint có thể để state hỏng.
- In `SHIP` ra stdout **không phải ACK bền vững của backend**. Crash sau khi xuất nhưng trước khi checkpoint có thể làm replay; checkpoint trước gửi có thể làm mất.
- Không có file watcher, bounded queue, retry, dedup, TLS, authentication, record size limit hoặc parallel file handling.
- Decoder `new String(bytes,...,UTF_8)` trong demo có thể thay thế malformed bytes bằng ký tự thay thế; shipper thực cần chính sách lỗi encoding.
- Một newline tương ứng một record, nên text stack trace nhiều dòng cần multiline parser hoặc JSON Lines.

Ý nghĩa của ví dụ là làm rõ quy tắc **partial record không được coi đã xử lý xong** và **offset không phải số dòng**.

## 8. Định dạng log cho shipper: text, multiline và JSON Lines

### Log text và stack trace

Một Java exception thường được formatter text ghi thành nhiều dòng:

```text
2026-01-01T10:00:00Z ERROR Payment failed
java.net.SocketTimeoutException: Read timed out
    at com.example.PaymentClient.call(PaymentClient.java:51)
    at com.example.OrderService.submit(OrderService.java:99)
```

Nếu shipper đọc từng LF thành một event, backend sẽ có nhiều bản ghi riêng thay vì một exception. Muốn đúng cần **multiline framing**: nhận diện dòng bắt đầu record, gộp những dòng tiếp theo tới record sau. Quy tắc phải kiểm case message do client cung cấp chứa chuỗi trông giống timestamp, tránh merge/split sai.

### JSON Lines

Nếu formatter ghi một JSON object trên một dòng, các newline trong stack trace được encode thành chuỗi JSON:

```json
{"timestamp":"2026-01-01T10:00:00Z","severity":"ERROR","service.name":"checkout-api","event.name":"dependency.failed","exception.type":"java.net.SocketTimeoutException","message":"Payment failed","stack":"Read timed out\nat PaymentClient.call(...)"}
```

JSON Lines thường dễ frame/parse theo LF, nhưng **không đồng nghĩa tự động có đủ dữ liệu hoặc không lỗi**. Encoder phải escape control characters, shipper parser phải đọc đúng schema, giới hạn kích thước và chuyển field/timestamp đúng kiểu. Nếu một dòng JSON vượt max line size của shipper, có thể bị cắt hoặc bỏ.

**Đừng log raw user input** chứa newline rồi nối thẳng thành text line: nó có thể gây log injection, làm parser hiểu nhầm actor, severity hoặc event. Nên dùng structured encoder được kiểm chứng và validation tại nguồn.

Các field hữu ích để tìm kiếm:

| Field | Mục tiêu |
| --- | --- |
| `timestamp` | Event time, để truy theo thời gian xảy ra |
| `severity` | INFO/WARN/ERROR với mapping nhất quán |
| `service.name` / `environment` | Phân biệt service, deployment, tenant theo chính sách |
| `event.name` / `error.code` | Search theo loại sự kiện/mã lỗi ổn định |
| `request_id`, `trace_id` | Correlation qua service |
| `exception.type` | Phân nhóm Java exception |
| `log.file.path` | Chẩn đoán nguồn file; không để thành metric label cardinality cao tùy ý |

Một bộ parser có thể nhận JSON rồi thêm host/pod metadata; phải thống nhất field owner. Đừng cho input client tự thay `service.name` hoặc `tenant_id` dùng để phân quyền search.

## 9. Ghi file từ Java: JUL và Logback

### JUL FileHandler

Java JDK có `java.util.logging.FileHandler` và hỗ trợ pattern/limit/count/append. Một chương trình tối thiểu:

```java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public final class JulFileLoggingExample {
    public static void main(String[] args) throws IOException {
        Logger logger = Logger.getLogger("example.file.logging");
        logger.setUseParentHandlers(false);

        FileHandler handler = new FileHandler(
                "app-%g.log", 1_000_000, 3, true);
        handler.setFormatter(new SimpleFormatter());
        logger.addHandler(handler);
        try {
            logger.info("Started application");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Lưu thành `JulFileLoggingExample.java` và chạy `javac JulFileLoggingExample.java`, `java JulFileLoggingExample` nếu muốn thử thêm. Chương trình ghi file trong working directory; tên thực tế phụ thuộc `%g`, rotation, hệ điều hành và tình trạng file. `SimpleFormatter` là text, không có JSON schema hoặc guarantee shipper sẽ đọc đúng stack trace. `FileHandler` có policy rotation riêng; test cấu hình agent với file name/index và quyền ghi.

### Logback RollingFileAppender

Ví dụ cấu hình **minh họa** cho ứng dụng đã có Logback dependency:

```xml
<configuration>
  <appender name="FILE"
      class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/app.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>logs/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
      <maxHistory>7</maxHistory>
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

Đây là **pattern text**, không phải JSON Lines. Kiểm thư mục `logs`, version Logback, mức log, flush policy, rolling và maxHistory thực tế. Rotation với nén archive có thể tương tác với shipper: nên thử khi agent đang lag, file vừa bị rename, file mới được tạo và appender còn giữ descriptor cũ.

Log4j2 có `RollingFile` appender và các policy tương ứng, nhưng syntax XML/YAML và lifecycle khác Logback; không dùng trực tiếp cấu hình Logback để cấu hình Log4j2.

Trong môi trường đa process, tránh để nhiều JVM cùng ghi một file mà không có cơ chế phối hợp; file riêng theo service/instance thường dễ ship và dễ gắn metadata hơn.

## 10. Một số file shippers phổ biến

File shippers có thể được triển khai làm service trên máy, node agent, sidecar hoặc phần của observability pipeline.

| Công cụ | Khái niệm chính | Điều cần kiểm theo phiên bản |
| --- | --- | --- |
| **Filebeat** | File input/filestream, harvester và state registry | File identity, checkpoint, close/ignore policy, rotation, output ACK |
| **Fluent Bit** | Tail input, parser, filter và output plugins | State DB, multiline, buffer storage, rotation wait, retry |
| **Vector** | File source, transforms và sinks | Fingerprint, checkpoint, multiline, disk buffer và acknowledgements |
| **OpenTelemetry Collector filelog receiver** | Đọc file và đưa events vào logs pipeline | Distribution có receiver hay không, storage extension, parsing và exporter |

Tên tùy chọn, cấu hình YAML và ngữ nghĩa “ACK” **không giống nhau** trên mọi sản phẩm hoặc mọi phiên bản. Trước khi triển khai, tạo bảng cấu hình yêu cầu:

```text
source paths / globs
file identity policy
starting position for an unseen file
checkpoint/registry storage and persistence
line framing / multiline / max event size
encoding / timestamp / JSON parsing
metadata enrichment and redaction
bounded memory/disk queue and batch settings
destination TLS/auth and retry policy
rotation, compressed archives and retention
self-metrics, healthcheck and failure alerts
```

Không áp một cấu hình mẫu vào production nếu chưa biết bản build hỗ trợ option đó. Đặc biệt, **OpenTelemetry Collector filelog receiver** có thể không được đóng gói trong mọi distribution; chỉ cài một Collector binary và cấu hình `filelog` không chắc đủ.

## 11. Buffering, backpressure và sự cố backend

Giả sử Java tạo log **nhanh hơn** tốc độ agent gửi. File vẫn tiếp tục lớn lên, queue agent có thể đầy; nếu rotation xóa file cũ trước khi agent đọc đủ thì mất log.

```text
Java writer: 2 MB/s
     |
     v
app.log grows
     |
File shipper reads
     |
memory/disk queue --> network --> backend
     |                              |
     +-- queue full                 +-- timeout/429/503
         |                              |
      pause/drop                    retry/backoff
```

Các chính sách cần có:

- **Bounded queue:** giới hạn RAM/disk, có metrics depth/bytes/age. Không giả định memory buffering sống qua process crash.
- **Retry:** với network timeout, backend 429/503, exponential backoff/jitter và giới hạn phù hợp. Retry có thể tạo duplicate.
- **Backpressure:** agent có thể tạm ngừng đọc file. Java vẫn ghi file; disk và retention trở thành buffer cuối cùng.
- **Poison events:** một record JSON lỗi quá dài hoặc parse không hợp lệ cần xử lý theo policy, không làm pipeline kẹt vô hạn mà không có cảnh báo.
- **Disk full:** appender/file writer có thể thất bại, ảnh hưởng nghiệp vụ; cần quota, rotation, alerts và chính sách fail-open/fail-closed theo loại event.
- **Shutdown:** chờ flush/ACK trong deadline hợp lý, có state phục hồi; không tuyên bố mọi sự kiện được giữ chỉ vì process thoát “gracefully”.

Một mô hình sizing thô:

```text
source_bytes_per_second
  ≈ events_per_second × average_serialized_bytes_per_event

buffer_bytes_needed (ước tính)
  ≳ peak_bytes_per_second × expected_destination_outage_seconds
```

Chỉ là ước tính: batching, compression, metadata, disk overhead, duplication và buffer format làm nhu cầu thực khác đi. Với 2 MB/s trong 30 phút, log mới sinh ra khoảng **3.600 MB** trước overhead; buffer chỉ 500 MB không thể chứa đầy đủ nếu backend không nhận trong toàn khoảng.

File retention phải lớn hơn worst-case backlog/recovery có margin, nếu không shipper có khả năng vẫn đang hoạt động nhưng **event quá cũ đã bị xóa**.

## 12. File shipper trong Kubernetes và môi trường ephemeral

Trong Kubernetes, đường chuẩn thường là Java ghi stdout/stderr, container runtime quản lý logs ở node và DaemonSet collector thu thập. Nếu ứng dụng ghi file riêng bên trong container nhưng node agent chỉ đọc stdout, những file đó có thể **không bao giờ tới backend**.

Một số lựa chọn:

1. **Stdout/stderr + node agent:** đơn giản về app, nhưng phải kiểm runtime rotation, pod metadata, node disk và agent lifecycle.
2. **File trên shared volume + sidecar:** appender và shipper cùng nhìn thấy file; cần quản lý volume permissions, startup/shutdown ordering và resource requests/limits.
3. **File trên persistent volume + agent:** file có thể sống qua pod restart tùy PV và chính sách; cần kiểm file identity/ownership/retention.
4. **Direct telemetry exporter:** appender/SDK gửi trực tiếp qua protocol có buffering phù hợp; không có file tailing nhưng cần tự kiểm retry/shutdown/backpressure.

**Không đọc đồng thời stdout và file cùng chứa một event** trừ khi có một chiến lược rõ để phân biệt nguồn hoặc dedup. Đừng giả định sidecar chắc chắn chạy tới khi đọc hết mọi file khi pod bị kill: shutdown grace period và termination order phải được thử.

Trong serverless hoặc ephemeral compute, việc dùng một file local rồi mong shipper bên ngoài đọc sau khi instance bị xóa là một thiết kế rất dễ mất log.

## 13. Bảo mật của file, shipper và đường xuất

Dữ liệu log có thể chứa request context, stack traces, identifiers hoặc thông tin cá nhân. Shipper phải tuân thủ nguyên tắc **quyền tối thiểu và bảo vệ dữ liệu từ nguồn**:

- Java application chỉ có quyền ghi vào thư mục log cần thiết; shipper được đọc những file cần ship và ghi registry/buffer ở thư mục riêng.
- Không dùng glob quá rộng vô tình thu thập secrets, audit trails của tenant khác hoặc file không thuộc phạm vi.
- Thận trọng với symlinks và file path do đối tượng không tin cậy điều khiển, tránh shipper đọc sang vùng dữ liệu ngoài policy.
- Credential của output phải được bảo vệ bằng secret store/credential provider, không hardcode token trong source, log message hoặc config được chia sẻ công khai.
- Dùng TLS và xác thực endpoint ở các ranh giới mạng cần bảo vệ; cấp quyền ingest vào đúng project/tenant/environment.
- Không ghi password, access token, session cookie, private key hay dữ liệu cá nhân không cần thiết **từ Java call site**. Redaction tại shipper không xóa được dữ liệu đã nằm trên local disk.
- JSON encoder và parser phải escape newline/CR/control chars để tránh log injection, và phải xác thực actor/tenant/severity từ nguồn đáng tin.
- Quyền **search/export/delete** logs tại backend nên tách với quyền ingest của agent; thời hạn lưu tại file, queue và backend tuân theo chính sách.
- Với audit bắt buộc, cần cơ chế chống sửa trái phép, durability và reconciliation riêng; một file log bình thường không tự là bằng chứng bất biến.

Shipper có thể thêm service/host/pod metadata, nhưng không nên cho một field từ message do client cung cấp ghi đè danh tính hệ thống hoặc tenant scope used for access control.

## 14. Metadata, request ID và trace correlation

Một event có thể được bổ sung metadata khi ship:

```json
{
  "timestamp": "2026-01-01T10:00:03Z",
  "severity": "ERROR",
  "service.name": "orders-api",
  "deployment.environment.name": "prod",
  "host.name": "vm-01",
  "log.file.path": "/var/log/orders/app.log",
  "event.name": "order.process.failed",
  "request_id": "req-42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error.code": "DOWNSTREAM_TIMEOUT",
  "message": "Payment provider timed out"
}
```

Đây là schema minh họa, không phải tên field được mọi backend tự map. Trong ứng dụng Java, `MDC`/`ThreadContext` có thể đưa `request_id`, `trace_id` vào event. Nhưng MDC thường gắn theo thread và **không tự lan truyền qua mọi ExecutorService/CompletableFuture/reactive task**; cần context propagation phù hợp và dọn context sau tác vụ.

Khi agent parse JSON, phải phân biệt field do ứng dụng tạo với field deployment/agent tạo, cũng như quy tắc xử lý nếu tên key trùng. Không tạo `request_id` giả tại agent vì nó không thể biết toàn bộ luồng request nếu ứng dụng không truyền.

Để tìm lỗi, truy log theo service/time/error code rồi mở timeline theo request/trace ID. Không đưa request ID hay trace ID làm **metric labels cardinality cao**, dù chúng hữu ích trong log search.

## 15. Quan sát và giám sát sức khỏe shipper

Một shipper “process is running” không chứng minh nó đang đọc/gửi dữ liệu. Nên theo dõi:

| Chỉ số quan sát | Mục đích |
| --- | --- |
| `files_discovered` / `files_active` | Input có tìm đúng file và reader đang tồn tại không |
| `bytes_read_total` | Tốc độ đọc và khả năng bắt kịp nguồn |
| `events_parsed_total` | Số record được parse |
| `parse_errors_total` | JSON/multiline/encoding không đúng |
| `queue_depth` / `queue_usage_bytes` | Backlog, buffer pressure |
| `events_sent_total` | Lượng event đã thử gửi |
| `events_acked_total` | Số được xác nhận ở mức output contract |
| `events_dropped_total` | Bị bỏ do limits/filter/failure |
| `output_retries_total` | Lỗi network/quota/output |
| `oldest_unshipped_event_age` | Event chưa giao cũ nhất |
| `checkpoint_errors_total` | Registry không lưu/khôi phục đúng |
| `ingestion_lag_seconds` | Event xảy ra đến khi backend có thể query được nếu đo được |

**Các tên metric chỉ là gợi ý thiết kế**, không phải metric mặc định của mọi Filebeat/Fluent Bit/Vector/Collector. Mapping đúng tên hiện có của công cụ và xem chúng trong dashboard.

Một **end-to-end canary test**:

1. Java ghi một event ID duy nhất, không chứa secret.
2. Xác nhận log được flush vào file và có record hoàn chỉnh, JSON parse đúng nếu dùng JSON.
3. Theo dõi agent discovery/reader/output.
4. Query backend theo event ID với time window phù hợp trong thời hạn SLO.
5. Kiểm metadata, số lần xuất hiện, thời gian ingest và các event liên quan.
6. Lặp sau restart app/agent, rotation, network partition và quota/429.

Không dùng `Thread.sleep(1000)` rồi kết luận ACK; dùng điều kiện chờ và timeout, đo đúng điểm thành công.

## 16. Chẩn đoán các sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| File có log nhưng backend không có | Sai glob, permission, agent off, exporter lỗi, query sai | Input discovery, agent metrics, time window, destination |
| Sau restart bị gửi lại nhiều log | Registry mất hoặc starting position về đầu | Checkpoint persistence, file fingerprint, version migration |
| Mất đầu file mới khi rotate | Offset cũ được áp vào file identity mới | Identity/rename/create tests |
| Mất log cuối file cũ | Reader đóng quá sớm, archive bị nén/xóa | Rotate wait, lifecycle, retention |
| Mất vài dòng lúc copytruncate | Race copy/truncate | Chọn rolling khác hoặc chấp nhận risk theo policy |
| Một exception thành nhiều events | Stack trace text bị tách LF | Multiline parser hoặc JSON Lines |
| JSON bị cắt/hỏng | Max line length, malformed encoding, partial line | Framing, parser errors, size limits |
| Log tiếng Việt sai ký tự | Charset mismatch hoặc UTF-8 cắt byte | Source encoder, agent decoder |
| Backend nhận trễ | Queue, retry, 429/503, mạng chậm | Oldest event age, queue depth, exporter errors |
| Một event xuất hiện hai lần | ACK loss/retry, checkpoint reset, hai agents | Event ID, owner/input policy, dedup |
| Request ID mất | Logger/encoder không ghi MDC hoặc context bị rơi | App logger, propagation, JSON parser |
| Disk đầy | Writer nhanh hơn shipper, retention/quota chưa phù hợp | Disk use, output throughput, rotation |
| Một số file bị bỏ qua | Ignore policy, file too old, fingerprint threshold | Input rules và identity metrics |
| CPU/memory shipper cao | Regex/multiline đắt, nhiều files, queue lớn | Profile, bounded state, parser tuning |
| Log chứa bí mật bị chuyển đi | App ghi secrets, chỉ redact quá muộn | Fix tại nguồn, review file+queue+backend |

Không tự xóa registry và replay mọi file như một cách chữa chung: điều đó có thể đẩy hàng triệu duplicate events vào backend. Cần hiểu state, file identity, phạm vi và chính sách khôi phục trước khi thao tác.

## 17. Kiểm thử cần có trước production

| Kịch bản | Kỳ vọng |
| --- | --- |
| Java ghi một JSON line đầy đủ | Một event được parse và gửi theo contract |
| Ghi event thành nhiều lần chưa có LF | Partial line không bị xuất sai |
| CRLF, Unicode đa byte | Decoder giữ đúng giá trị và byte offset |
| Stack trace multiline | Gộp đúng một event, không nuốt event kế tiếp |
| Rename/create | File cũ được drain, file mới bắt đầu từ offset phù hợp |
| Copytruncate | Rủi ro mất bytes được đo, không tuyên bố zero-loss |
| Compressed/expired archive | Không xóa log chưa ship theo policy |
| Restart Java/agent | Checkpoint và file identity còn đúng |
| Crash sau send trước ACK | Quan sát behavior retry/duplicate |
| Mất mạng/HTTP 429/503 | Bounded queue, retry, backoff, cảnh báo |
| Full disk/permission denied | Không làm hỏng ứng dụng ngoài failure policy |
| Nhiều agent cùng path | Có single owner/dedup, không nhân đôi ngoài ý muốn |
| Kubernetes pod restart | State/volume/stdout collection sống theo yêu cầu |
| Secret/PII trong message | Không ghi bí mật tại nguồn, redaction đúng |
| Auth/TLS sai đích | Export lỗi rõ ràng, không gửi dữ liệu không an toàn |
| End-to-end query | Event ID tìm được trong deadline, schema/metadata đúng |

Với kiểm thử hệ thống, cần xem log từ Java, file contents, registry/checkpoint, agent queue, Collector/output metrics và search backend. Chỉ test một hàm `readLine` không chứng minh một pipeline vận chuyển log đáng tin.

## 18. Sai lầm phổ biến

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Đọc lại toàn file mỗi poll | Tốn I/O, tạo duplicate | Offset + checkpoint |
| Chỉ lưu tên path | Không nhận diện rotation | File identity/fingerprint theo platform |
| Dùng số ký tự làm offset UTF-8 | Bắt đầu sai byte sau restart | Offset tính bằng byte |
| Ship dòng chưa có newline | Event hỏng hoặc bị chia | Buffer partial record |
| Checkpoint trước khi gửi thành công | Mất dữ liệu khi crash | Commit theo ACK contract |
| Coi retry = exactly-once | Có thể nhận trùng | Event ID, idempotent sink |
| Không kiểm copytruncate | Có thể mất bytes không khôi phục | Test race, chọn policy phù hợp |
| Nén/xóa rotated file quá sớm | Reader không thể đọc phần còn lại | Retention > lag + margin |
| Dùng text stack trace không multiline | Một exception thành nhiều records | Multiline parser hoặc JSON |
| Thu stdout và file trùng nhau | Volume/backend cost tăng | Một đường thu hoặc dedup rõ |
| Không lưu registry qua restart | Re-ingest/missing tùy start policy | Persistent checkpoint |
| Chỉ kiểm agent alive | Không thấy backlog/drop/parse errors | Metrics, canary và alert |
| Ghi token vào file rồi chỉ redact ở Collector | Đã lộ tại local disk | Data minimization từ call site |
| Dùng file shipper làm audit atomic với DB | Có thể commit business nhưng mất log | Transactional outbox/audit storage |

## 19. Checklist triển khai file shipper cho Java

- [ ] Đã xác định file shipper là lựa chọn đúng, thay vì stdout/OTLP theo môi trường?
- [ ] Java appender ghi đúng level, file path, UTF-8 và rolling policy?
- [ ] Log được format JSON Lines hoặc có multiline parser đáng tin cho stack trace?
- [ ] Agent có file identity, byte offset, checkpoint và xử lý rename/create/copytruncate?
- [ ] File retention có lớn hơn worst-case backlog, recovery và rotation delay?
- [ ] Delivery ACK, retry, dedup, buffer và failure policy đã được định nghĩa và test?
- [ ] Khi backend 429/503 hoặc mạng mất, agent có bounded queue/backoff và alerts?
- [ ] Có tránh hai shippers hoặc hai sink thu cùng event không mong muốn?
- [ ] File, checkpoint, credentials và network dùng quyền tối thiểu/TLS phù hợp?
- [ ] Secrets/PII không được ghi từ logger; các trường do client cung cấp được escape?
- [ ] Event chứa timestamp, service/environment, event name và request/trace ID khi cần?
- [ ] Metrics bytes read, parse errors, drops, queue backlog, retries và ingest lag có dashboard?
- [ ] Đã kiểm log rotation, restart, full disk, lost ACK, UTF-8, multiline, retention và pod deletion?
- [ ] Có canary end-to-end xác nhận event ID tìm thấy ở backend trong deadline?

**Kết luận:** file shipper là **cầu nối giữa file log Java và hệ thống quan sát tập trung**. Chỉ đọc thêm dòng mới là chưa đủ: thiết kế còn phải giải quyết **file identity, rotation, partial line, byte checkpoint, ACK/retry, độ bền và quyền truy cập**. Hãy dùng logger/encoder phù hợp để tạo event có cấu trúc, shipper chuyên dụng để thu/vận chuyển, và phép đo end-to-end để chứng minh log đến nơi khi cần.
