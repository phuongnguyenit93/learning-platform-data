# Remote appender trong Java Logging: gửi log qua mạng, độ tin cậy và vận hành

## 1. Remote appender là gì?

**Remote appender** là một thành phần của logging framework đưa log event ra khỏi tiến trình Java và gửi tới **một đích ở xa** qua mạng, thay vì chỉ ghi vào console hoặc file cục bộ. Đích đó có thể là log receiver, Syslog server, máy chủ thu thập riêng, HTTP ingest endpoint hoặc gateway chuyển tiếp tới hệ thống observability.

Trong ứng dụng dùng SLF4J/Logback, Log4j 2 hay một bridge tới OpenTelemetry, đường đi có thể như sau:

```text
Business code
    |
    v
logger.info(...), logger.error(...)
    |
    v
Logger -> Filter -> Encoder / Layout
    |
    +---- Console/File appender ----------------> local logs
    |
    +---- Remote appender -> socket/HTTP/TLS ---> Receiver
                                                 |
                                                 v
                                          Queue/Collector
                                                 |
                                                 v
                                         Central log backend
```

Trong chủ đề **Thu thập và vận chuyển**, câu hỏi quan trọng nhất không phải “làm sao gửi một String lên TCP?” mà là:

- Log có được **chấp nhận** vào queue của appender không?
- Có được **gửi qua mạng** thành công không?
- Receiver có **đọc, giải mã và chấp nhận** event không?
- Backend có **lưu bền vững** record đó không?
- Khi network/receiver lỗi, ứng dụng sẽ **block, retry, buffer, drop hay fallback**?
- Log được gửi bằng giao thức, encoding, bảo mật và schema nào?
- Nếu cần audit thật sự không mất dữ liệu, remote appender có đủ đáp ứng không?

**Nguyên tắc quan trọng:** Một lời gọi `log.info(...)` không đồng nghĩa log đã được lưu tại hệ thống tập trung. Ngay cả TCP connection hoặc HTTP 2xx cũng cần được diễn giải theo **contract của receiver**; đừng tự coi đó là xác nhận đã persist vĩnh viễn.

## 2. Remote appender khác console appender, file appender và collector agent

| Thành phần | Vai trò | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| Console appender | Ghi stdout/stderr | Đơn giản, hợp container, ít phụ thuộc mã ứng dụng | Phải có runtime/agent thu thập |
| File appender | Ghi file cục bộ | Có buffer/rotation; có thể giữ bản trước khi ship | Disk, quyền ghi, rotation, dung lượng |
| Remote appender | Java trực tiếp đẩy log tới remote receiver | Không cần tail file để truyền log; latency ingest có thể thấp | Network failure có thể ảnh hưởng logger; retry/drop khó |
| Log shipper/sidecar/daemon | Đọc file hoặc stdout rồi ship | Tách lifecycle gửi mạng khỏi request thread | Thêm thành phần vận hành và queue/spool |
| OpenTelemetry SDK/agent + OTLP | Export telemetry theo protocol | Có resource, trace correlation, Collector integration | Phải cấu hình exporter/processor/collector đúng |
| Message broker/outbox | Lưu event qua cơ chế có contract riêng | Có thể hỗ trợ ack/replay/durability tùy cấu hình | Không còn là logging appender đơn giản; thêm thiết kế |

Không có lựa chọn luôn tốt nhất. Với ứng dụng container/cloud, **stdout → agent/collector → backend** thường dễ triển khai và tách trách nhiệm hơn gửi socket trực tiếp từ mỗi JVM. Với hệ thống cần chuyển tiếp đặc biệt hoặc có collector gần ứng dụng, remote appender vẫn có giá trị.

Cần phân biệt **Logback SocketAppender** (một implementation cụ thể) với khái niệm remote appender nói chung. Mỗi framework/protocol có wire format, queue, TLS, failure handling và tương thích receiver khác nhau.

## 3. Các lớp của một lần vận chuyển log

```text
t0  Application tạo event
t1  Logger/filter cho phép event
t2  Async queue nhận event (nếu có)
t3  Encoder biến event thành bytes
t4  Socket/HTTP client gửi bytes
t5  Remote listener nhận và parse bytes
t6  Receiver trả ACK/HTTP success (nếu protocol có)
t7  Collector/queue xử lý và export
t8  Backend lưu/index và cho phép query
```

Từng dấu mốc có một ý nghĩa khác nhau. Nếu `t2` thành công, chỉ biết event vào queue của process; crash ngay sau đó vẫn có thể mất. Nếu `t4` trả thành công, dữ liệu có thể mới vào buffer của OS. Nếu `t6` có ACK, cần xem ACK xác nhận **đã nhận vào bộ nhớ, đã vào queue bền vững hay đã commit vào storage**. Nếu log xuất hiện trong dashboard ở `t8`, phải xét độ trễ ingest, indexing và retention.

### 3.1. Phân biệt transport reliability và application durability

**TCP** mang một luồng byte có thứ tự, có cơ chế retransmission ở tầng transport. Nó không tự bảo đảm receiver đã giải mã event, ghi database, replicate hoặc index thành công. Đặc biệt, khi peer đóng kết nối, caller có thể tưởng vài lần write vẫn thành công cho đến khi lỗi socket được phát hiện.

**UDP** không có kết nối và không có cơ chế ACK/retransmission của TCP. Nó phù hợp với một số Syslog pipelines đơn giản nhưng không phù hợp với yêu cầu không mất log khi mạng lỗi.

**HTTP** có status code và response; một HTTP 2xx thường cho biết receiver đã xử lý request theo contract HTTP của endpoint. Nó **không luôn có nghĩa log đã lưu bền vững** ở backend cuối cùng.

**OTLP/HTTP hoặc OTLP/gRPC** có protocol phản hồi và mã lỗi tiêu chuẩn, có thể hỗ trợ retry theo quy tắc của OTLP. Nhưng việc Collector nhận event vẫn không tự tạo durability end-to-end: còn processor, exporter, sending queue, backend và retention phía sau.

| Dấu hiệu | Có thể kết luận | Không thể kết luận chỉ từ dấu hiệu đó |
| --- | --- | --- |
| `logger.info` return | Caller tiếp tục chạy | Event đã đi tới remote server |
| Async queue offer thành công | Queue đã nhận event | Event đã được ghi durable |
| `Socket.write`/`flush` không lỗi | Dữ liệu đã được giao cho tầng socket/stream theo API | Receiver đã xử lý và persist |
| TCP peer ACK ở tầng transport | Byte stream được phía TCP peer xác nhận theo cơ chế protocol | Application receiver đã ghi DB |
| HTTP 2xx | Ingest endpoint trả thành công theo contract của nó | Backend cuối đã durable/không thể mất |
| Application ACK sau parse | Receiver đã chấp nhận đến checkpoint nêu trong protocol | Đã fsync/replicate nếu ACK không cam kết điều đó |
| Backend query thấy event | Record đã được query tại thời điểm ấy | Bản ghi luôn tồn tại, chưa bị retention xóa |

**Nếu log là bằng chứng giao dịch phải giữ được**, cần thiết kế nguồn dữ liệu bền vững (audit store/outbox/event store) ở tầng nghiệp vụ; remote appender thường là một kênh quan sát best-effort, không thay thế transaction.

## 4. Giao thức và format: receiver phải hiểu đúng bytes gửi tới

Một sai lầm phổ biến là chỉ nhìn port rồi cho rằng hai phần mềm tương thích. Ví dụ mở TCP socket đến `4318` không biến các dòng text thành **OTLP/HTTP**: cổng 4318 thường dùng HTTP với protobuf/JSON theo OTLP schema; receiver không thể đọc text tùy ý như dữ liệu OTLP chuẩn.

Các cặp thường gặp:

| Sender | Wire format / transport | Receiver cần hỗ trợ |
| --- | --- | --- |
| Log4j 2 Socket appender + PatternLayout | Text/bytes qua TCP/UDP/TLS, tùy cấu hình | Listener biết framing/encoding tương ứng |
| Log4j 2 HTTP appender | HTTP request với body do Layout tạo | HTTP endpoint và schema mà endpoint chấp nhận |
| Logback SocketAppender truyền thống | Serialized logging events, không phải NDJSON text | Receiver tương thích protocol Logback và trust boundary |
| Syslog appender | Syslog message theo RFC/format được cấu hình | Syslog receiver đúng version/transport/framing |
| OpenTelemetry log exporter | OTLP/gRPC hoặc OTLP/HTTP | OTLP receiver |
| File/console shipper | File lines, JSON lines hoặc container logs | Filelog/stdout collector và parser thích hợp |

**Framing** là cách phân biệt ranh giới giữa các event. TCP là **stream**, không phải chuỗi “mỗi write = một message”:
- Một log line có thể đến qua nhiều lần read.
- Nhiều log lines có thể được gom vào một lần read.
- Nếu dùng NDJSON, mỗi event phải là **một JSON object trên một dòng**, escape newline ở field bên trong.
- Với Syslog TCP, framing có thể dùng độ dài hoặc delimiter tùy chuẩn/cấu hình.
- Với protobuf/OTLP, dùng framing và content-type của protocol, không tự nối String tùy tiện.

Cả hai phía phải thống nhất `charset=UTF-8`, layout, line termination, timestamps/timezone, maximum event size và cách giải mã exception/multiline.

## 5. Java 17+ chạy độc lập: TCP sender/receiver có ACK ở mức ứng dụng

Ví dụ này mô phỏng cơ chế **một remote appender gửi các event tới receiver** qua TCP loopback. Receiver đọc **hai dòng text có delimiter newline** và trả `ACK 1`, `ACK 2` sau khi đưa event vào **bộ nhớ**.

Ví dụ chỉ để học **wire framing và acknowledgment**, không phải triển khai một logging framework production. Không có TLS, disk persistence, retry, xác thực hoặc dead-letter queue; nó chỉ bind `127.0.0.1`/loopback nên không mở listener ra Internet.

Lưu file `RemoteAppenderDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public final class RemoteAppenderDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        List<String> received = new ArrayList<>();
        AtomicReference<IOException> receiverError = new AtomicReference<>();

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            listener.setSoTimeout(3000);
            Thread receiver = new Thread(() -> {
                try (Socket socket = listener.accept();
                     BufferedReader input = new BufferedReader(
                             new InputStreamReader(
                                     socket.getInputStream(),
                                     StandardCharsets.UTF_8));
                     BufferedWriter output = new BufferedWriter(
                             new OutputStreamWriter(
                                     socket.getOutputStream(),
                                     StandardCharsets.UTF_8))) {
                    socket.setSoTimeout(3000);
                    for (int sequence = 1; sequence <= 2; sequence++) {
                        String event = input.readLine();
                        if (event == null) {
                            throw new IOException("Unexpected end of stream");
                        }
                        received.add(event);
                        output.write("ACK " + sequence);
                        output.newLine();
                        output.flush();
                    }
                } catch (IOException ex) {
                    receiverError.set(ex);
                }
            }, "log-receiver");

            receiver.start();
            List<String> acknowledgments = new ArrayList<>();

            try {
                try (Socket client = new Socket(loopback,
                        listener.getLocalPort());
                     BufferedWriter output = new BufferedWriter(
                             new OutputStreamWriter(
                                     client.getOutputStream(),
                                     StandardCharsets.UTF_8));
                     BufferedReader input = new BufferedReader(
                             new InputStreamReader(
                                     client.getInputStream(),
                                     StandardCharsets.UTF_8))) {
                    client.setSoTimeout(3000);
                    List<String> events = List.of(
                            "seq=1 event=order.created",
                            "seq=2 event=order.saved");

                    for (int index = 0; index < events.size(); index++) {
                        int sequence = index + 1;
                        output.write(events.get(index));
                        output.newLine();
                        output.flush();

                        String expected = "ACK " + sequence;
                        String actual = input.readLine();
                        if (!expected.equals(actual)) {
                            throw new IOException("Invalid ACK: " + actual);
                        }
                        acknowledgments.add(actual);
                    }
                }
            } finally {
                receiver.join();
            }

            if (receiverError.get() != null) {
                throw receiverError.get();
            }

            for (String event : received) {
                System.out.println("receiver.accepted=" + event);
            }
            System.out.println("client.acks="
                    + String.join(", ", acknowledgments));
            System.out.println("durability=in-memory-only");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 RemoteAppenderDemo.java
java RemoteAppenderDemo
```

**Stdout chính xác trong điều kiện chạy bình thường trên loopback:**

```text
receiver.accepted=seq=1 event=order.created
receiver.accepted=seq=2 event=order.saved
client.acks=ACK 1, ACK 2
durability=in-memory-only
```

Giải thích:

1. `new ServerSocket(0, 1, loopback)` chọn port còn trống và chỉ bind loopback, tránh hard-code port thường đã bị chiếm.
2. Receiver đọc `readLine()`: newline là **event delimiter**, không phụ thuộc số lần TCP read.
3. Sender dùng `BufferedWriter` và `flush()` để đẩy từng dòng ra stream.
4. Receiver giữ event trong `ArrayList` và gửi `ACK n`, sender mới gửi event kế tiếp.
5. Kết quả được in **sau khi `receiver.join()`**, nên stdout không phụ thuộc race giữa hai thread.
6. `ACK n` là **quy tắc ứng dụng tự viết**, không phải TCP ACK. Trong ví dụ nó chỉ xác nhận receiver đọc event và lưu ở bộ nhớ.
7. Nếu tiến trình receiver chết sau khi trả ACK, hai event **vẫn có thể mất** vì không có fsync hay durable queue.
8. Timeouts giúp tránh chờ vô hạn trong một số lỗi thử nghiệm; code này **chưa xử lý production recovery, TLS, reconnect, idempotency và security**.

Ví dụ chỉ có hai event, một kết nối và một receiver thread. Không tự dùng nó làm logger production hoặc expose listener ra mạng. Muốn “ít mất log hơn”, cần contract ACK rõ ràng, queue bền vững, retry/dedup và kiểm thử failure injection.

## 6. Logback SocketAppender: định dạng không phải text tùy ý

Logback Classic cung cấp `ch.qos.logback.classic.net.SocketAppender` để gửi logging events tới remote server. Khác nhiều Socket appenders dựa vào text layout, SocketAppender của Logback truyền **serialized logging events** và **không yêu cầu một `PatternLayout` đi kèm**.

Ví dụ `logback.xml` trong một ứng dụng đã có Logback:

```xml
<configuration>
    <appender name="REMOTE"
              class="ch.qos.logback.classic.net.SocketAppender">
        <remoteHost>127.0.0.1</remoteHost>
        <port>4560</port>
        <reconnectionDelay>10000</reconnectionDelay>
    </appender>

    <root level="INFO">
        <appender-ref ref="REMOTE"/>
    </root>
</configuration>
```

**Đây không phải ví dụ plug-and-play với chương trình `RemoteAppenderDemo.java` ở trên.** Receiver của demo chỉ hiểu text UTF-8 theo dòng; Logback SocketAppender gửi serialized events theo wire format riêng, nên hai bên **không tương thích**.

Cần hiểu:
- `remoteHost` và `port` xác định địa chỉ receiver tương thích.
- `reconnectionDelay` điều khiển khoảng retry kết nối lại theo hành vi của phiên bản Logback đang sử dụng.
- Khi remote server không sẵn sàng, SocketAppender có thể **bỏ log events**; reconnect không đồng nghĩa replay toàn bộ dữ liệu lúc downtime.
- SocketAppender dựa vào TCP và queue/buffering nội bộ tùy phiên bản; nó **không phải durable disk spool**.
- Receiver cần tương thích với serialized event protocol và phải được bảo vệ trong mạng đáng tin cậy.
- **Không deserialize Java objects từ client không tin cậy**: dữ liệu serialized ở ranh giới mạng tiềm ẩn nguy cơ bảo mật. Ưu tiên định dạng có schema an toàn và receiver hiện đại khi phải đi qua ranh giới trust.

Nếu cần TLS, kiểm tra các appender hỗ trợ TLS/SSL của Logback, certificate management và cấu hình của phiên bản cụ thể. Đừng cho rằng ví dụ TCP plain ở loopback là cấu hình production an toàn.

### 6.1. Gửi Logback qua HTTP/JSON hay OTLP thì sao?

Logback bản thân không có nghĩa mọi đường gửi đều dùng `SocketAppender`. Hệ thống có thể:
- Ghi JSON lines vào stdout/file rồi dùng shipper.
- Sử dụng appender/encoder hỗ trợ HTTP/JSON từ thư viện được kiểm duyệt.
- Dùng OpenTelemetry Java agent/SDK và logging integration tương thích để xuất logs qua OTLP.

Mỗi đường có **format và semantics khác nhau**. Không kết nối Logback SocketAppender thẳng vào OTLP receiver và kỳ vọng Collector tự hiểu; cần một protocol bridge/receiver đúng loại.

## 7. Log4j 2 Socket Appender: text, TCP, UDP và TLS

Log4j 2 có network `Socket` appender. Khi đặt `PatternLayout`, nó có thể gửi text qua TCP/UDP/TLS tùy cấu hình. Ví dụ **local test** với receiver text trên `127.0.0.1:5514`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Socket name="REMOTE_TCP"
                host="127.0.0.1"
                port="5514"
                protocol="TCP"
                connectTimeoutMillis="1500"
                immediateFail="true">
            <PatternLayout charset="UTF-8"
                pattern="%d{ISO8601} %-5p [%t] %c - %m%n"/>
        </Socket>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="REMOTE_TCP"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là **cấu hình Log4j 2 Core**, cần một receiver *đã hỗ trợ* UTF-8 text lines và đang lắng nghe port 5514. Nó **không** nói receiver sẽ tự parse các field trace/service; muốn structured logs thì chọn layout/schema phù hợp cho receiver.

Các thuộc tính:
- `host/port`: đích remote.
- `protocol=TCP`: luồng byte có thứ tự trong một connection, không có application ACK từng event.
- `connectTimeoutMillis`: giới hạn thời gian tạo kết nối; cần bổ sung chính sách xử lý khi remote down.
- `immediateFail`: cách appender xử lý khi socket không sẵn, không bảo đảm replay.
- `PatternLayout`: bytes văn bản có newline kết thúc record.
- `status="WARN"` là level của internal status logger, không phải ngưỡng business logs.

**Không đưa toàn bộ exception multiline vào một text-line protocol rồi giả định receiver vẫn giữ một event.** Nên dùng JSON escaping/NDJSON hoặc một protocol có framing rõ và giới hạn message size.

### 7.1. TCP, UDP và SSL/TLS không đồng nghĩa nhau

| Transport | Đặc điểm | Phù hợp với |
| --- | --- | --- |
| TCP | Reliable ordered byte stream ở một connection; không có app-level ACK mặc định | Remote receiver cần text/syslog liên tục |
| UDP | Message-oriented, không bảo đảm delivery/ordering | Một số local/legacy syslog, loss chấp nhận được |
| TLS over TCP | TCP cộng mã hóa/xác thực server (và có thể mTLS) | Logs ra khỏi trust boundary |
| HTTP(S) | Request/response, status code, body schema | Ingest API có contract rõ |
| OTLP/gRPC hoặc OTLP/HTTP | Telemetry protocol có schema và response semantics | OTel Collector/compatible backend |

Log4j 2 hỗ trợ TLS cho network appenders; cần certificate trust, verify host name và optional mTLS theo deployment. **Không tắt xác minh certificate/hostname chỉ để sửa lỗi kết nối**. Với socket TLS, đừng mặc định hostname validation đã bật như HTTP client; hãy cấu hình và kiểm chứng nó thực sự hoạt động.

Đối với Syslog, format (RFC 3164 hoặc RFC 5424), transport (UDP/TCP/TLS) và framing phải thống nhất với receiver. Port 514/6514 là quy ước phổ biến, **không phải chứng minh rằng mọi endpoint ở port đó dùng cùng encoding/protocol**.

## 8. Log4j 2 HTTP Appender: có response nhưng vẫn phải xét latency

Log4j 2 cung cấp HTTP Appender gửi event qua HTTP. Ví dụ này dùng endpoint **giả định có tồn tại trong môi trường nội bộ** và chấp nhận một text log event ở request body; triển khai thật phải biết endpoint yêu cầu schema gì:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Http name="REMOTE_HTTP"
              url="https://logs.example.internal/ingest"
              method="POST"
              connectTimeoutMillis="1500"
              readTimeoutMillis="2000"
              verifyHostName="true">
            <PatternLayout charset="UTF-8"
                pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </Http>
    </Appenders>

    <Loggers>
        <Root level="WARN">
            <AppenderRef ref="REMOTE_HTTP"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là **cấu hình minh họa**, không có một server thực được cung cấp tại domain đó. Chỉ hoạt động nếu endpoint thật có TLS certificate hợp lệ và chấp nhận body do Layout tạo. Nếu endpoint muốn JSON/OTLP, **phải dùng encoding/protocol tương ứng**, không đổi URL là đủ.

Theo tài liệu Log4j 2 Network Appenders, HTTP Appender gửi từng event bằng HTTP và **mặc định có thể blocking**: khi receiver/network chậm, lời gọi logger có thể mất đáng kể thời gian. Nó có lỗi khi HTTP status không thuộc 2xx; cách lỗi ảnh hưởng caller phụ thuộc `ignoreExceptions` và pipeline (không nên dùng nó thay thiết kế nghiệp vụ).

Không để `connectTimeoutMillis` hoặc `readTimeoutMillis` mặc định vô hạn trong đường request latency-sensitive mà không hiểu hậu quả; giá trị trong ví dụ chỉ là con số tham khảo cần điều chỉnh theo môi trường.

### 8.1. Đặt AsyncAppender phía trước có đủ không?

Một mẫu thường dùng với Log4j 2:

```xml
<Async name="ASYNC_REMOTE" bufferSize="1024" blocking="false">
    <AppenderRef ref="REMOTE_HTTP"/>
</Async>
```

Đây là **fragment** nằm trong `<Appenders>` của một cấu hình Log4j 2 đã có `REMOTE_HTTP`, không phải file hoàn chỉnh. Nó đặt queue in-memory giữa producer và HTTP appender.

Điều này cải thiện latency của caller trong nhiều trường hợp, nhưng:
- Queue có giới hạn; với `blocking=false` có thể **drop** khi đầy.
- Worker gửi qua mạng vẫn có thể bị chậm, retry hoặc lỗi.
- JVM crash có thể mất các event còn trong queue.
- Async worker không tự lưu durable.
- Nếu là log audit bắt buộc, cấu hình kiểu này **không đáp ứng yêu cầu zero-loss**.

Có thể chọn `blocking=true` để ưu tiên không drop khi queue đầy, nhưng producer có thể bị chặn; cần gắn quyết định này vào SLO, request timeout và tiêu chí chấp nhận sự cố.

## 9. OpenTelemetry/OTLP: remote logs hiện đại có schema và Collector

Trong hệ thống observability, một đường đi là:

```text
Java application / agent / logging bridge
              |
              v
        OTLP exporter
       (HTTP or gRPC)
              |
              v
       OTel Collector
    receiver -> processor
              |
              v
         exporter queue
              |
              v
    Backend logs storage
```

OTLP có **schema** cho log record, resource attributes, trace/span IDs và severity. Đừng nhầm với text logger chuyển thẳng qua TCP. Các đường OTLP phổ biến:
- `4317`: OTLP/gRPC theo quy ước thông thường.
- `4318`: OTLP/HTTP theo quy ước thông thường.
- Chúng có thể được cấu hình dùng port khác tùy deployment.

### 9.1. Cấu hình Collector local cho logs

Ví dụ **local development**: Collector nhận OTLP/HTTP trên loopback và in dữ liệu qua debug exporter:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "127.0.0.1:4318"

processors:
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

Ý nghĩa:
- `receivers.otlp.protocols.http` nhận **OTLP/HTTP**, không nhận raw text TCP.
- `batch` gom telemetry theo chính sách của Collector.
- `debug` chỉ phục vụ thử nghiệm, có thể ghi dữ liệu nhạy cảm vào chính log của Collector.
- `service.pipelines.logs` phải kích hoạt receiver/processor/exporter; khai báo component riêng không đủ.

Cấu hình này **không phải production**: không có auth, TLS, backend storage, persistent queue, retry policy và access control. Khi app chạy trong container khác, loopback của mỗi container là khác nhau; sửa địa chỉ theo topology, không mở công khai port ingest mà thiếu bảo vệ.

Nếu dùng agent/SDK, cần kiểm tra rằng logs từ SLF4J/Logback/Log4j 2 đã thực sự được bridge/export theo version và instrumentation. Chỉ đặt `OTEL_LOGS_EXPORTER=otlp` không chứng minh mọi dòng `logger.info` tự đi vào OTLP.

### 9.2. OTLP response và retryable errors

OTLP/HTTP có hướng dẫn retry cho các tình huống như `429 Too Many Requests`, `502`, `503` và `504`; lỗi `400 Bad Request` do payload vĩnh viễn không hợp lệ **không nên retry mù**. Nếu receiver yêu cầu giảm tải qua `Retry-After`, client nên tuân theo contract. Hãy để exporter/SDK/Collector xử lý retry đúng protocol, có backoff và jitter; không tự đặt `while(true)` retry vô hạn trong request thread.

**Một response thành công ở collector là một ranh giới chấp nhận dữ liệu**, nhưng có thể vẫn còn nhiều bước chuyển tới backend. Để đánh giá durability, xem gửi queue có persistent storage hay không, retry window, backend ack và khả năng crash/restart.

## 10. Bốn chính sách xử lý khi remote destination không khả dụng

Giả sử Java phát log 1.000 events/s nhưng remote receiver down 2 phút. Có 120.000 events mới phát sinh. Cần quyết định xử lý chúng ra sao:

| Chiến lược | Kết quả | Rủi ro |
| --- | --- | --- |
| Drop khi remote down | Application không bị nghẽn do log | Mất thông tin observability |
| Block producer | Thường hạn chế mất event ở một queue tạm thời | Request latency tăng, thread pool/availability bị ảnh hưởng |
| Queue in-memory | Hấp thụ outage ngắn | Queue đầy sau một thời gian; crash mất backlog |
| Spool file/durable queue | Có thể khôi phục backlog qua restart tùy thiết kế | Disk full, durability/rotation/ack phức tạp |

Không có “free lunch”: không thể bảo đảm **zero loss + zero latency + unbounded outage + bounded resources** đồng thời. Thiết kế phải xác định error budget cho logging và độ ưu tiên của workload.

### 10.1. Backpressure

Khi tốc độ producer > consumer, queue depth tăng. Nếu queue là bounded, một lúc nào đó phải:
- Chặn producer.
- Bỏ event có chọn lọc.
- Trả lỗi cho caller.
- Chuyển sang spool/receiver khác có giới hạn tài nguyên.
- Hạn chế log volume tại nguồn.

Đừng đặt queue size vô hạn để “không bao giờ mất log”: heap có thể tăng, GC nặng hoặc OOM khiến ứng dụng mất cả khả năng xử lý nghiệp vụ.

### 10.2. Queue size tính như thế nào?

Giả sử mỗi event trung bình 1,5 KiB **sau encode**, nguồn 2.000 events/s, receiver down 90 giây. Chỉ riêng dữ liệu thô cần gần:

```text
2,000 events/s × 90 s = 180,000 events
180,000 × 1.5 KiB = 270,000 KiB ≈ 263.7 MiB
```

Đây **chưa tính** object overhead, queue nodes, headers, GC và số bản sao trong memory. Con số chỉ minh họa cách ước tính; event size thực cần đo ở production và cao điểm có thể tăng mạnh.

Nếu spool xuống disk, còn phải tính retention, file system capacity, fsync, compaction, readback và data security. Capacity planning cần **thời gian outage mục tiêu + burst volume + consumer catch-up rate**, không chỉ nhân rate trung bình.

### 10.3. Khi remote hồi phục, backlog có thoát hết không?

Nếu producer tiếp tục 2.000 events/s và remote chỉ xử lý 2.100 events/s, sau outage backlog sẽ tiêu với tốc độ ròng **100 events/s**. Với 180.000 events tồn, cần khoảng **30 phút** để giải phóng backlog, giả định không thêm lỗi và event rate giữ nguyên.

Vì vậy một queue lớn không giải quyết toàn bộ vấn đề. **Catch-up throughput** phải lớn hơn input rate đủ đáng kể, hoặc cần sampling/throttle/policy fallback rõ.

## 11. Retry, duplicate, ordering và idempotency

Remote transports có ba failure phổ biến:

1. **Chưa gửi được:** lỗi DNS/connect/handshake trước khi receiver nhận.
2. **Đã gửi, mất phản hồi:** receiver có thể đã chấp nhận event nhưng sender timeout; retry tạo **duplicate**.
3. **Receiver ACK nhưng backend downstream lỗi:** ứng dụng tưởng đã xong, nhưng log vẫn có thể mất nếu pipeline thiếu durability.

Từ đó nảy sinh các mức bảo đảm:

| Mô hình | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| At-most-once | Không cố replay event đã nghi gửi | Có thể mất event |
| At-least-once | Retry tới khi có xác nhận theo policy | Có thể có duplicate |
| Effectively-once/idempotent consume | Dedupe bằng event ID/sequence trong phạm vi lưu trữ | Cần state, retention, transactional design |
| Exactly-once end-to-end | Yêu cầu contract end-to-end và transactional boundary rất chặt | Không được tự nhận chỉ nhờ TCP/ACK |

### 11.1. Event ID và deduplication

Nếu bắt buộc hỗ trợ retry/dedupe, có thể gắn `event_id` do application/pipeline phát hành khi event được tạo. Giữ nguyên ID qua retries. Receiver/store có thể dedup trong **một cửa sổ và phạm vi cụ thể**. Nhưng một UUID tự nó không bảo đảm idempotency; cần có logic lưu trạng thái/unique constraint/checkpoint.

Không nên dedup chỉ theo message text: hai request hợp lệ có thể sinh cùng câu `"payment failed"`. Nếu không có event ID, dùng trace/span/operation/sequence giúp điều tra nhưng không tự tạo duy nhất tuyệt đối.

### 11.2. Ordering

TCP giữ thứ tự bytes trên một connection. Nhưng:
- Nhiều producer threads có thể enqueue theo thứ tự khác thứ tự nghiệp vụ.
- Nhiều sockets/receivers/partitions không tạo **global order**.
- Retry có thể khiến event cũ xuất hiện sau event mới.
- Backend có thể sort theo ingestion timestamp thay vì event timestamp.
- Queue riêng ở nhiều appender không chia sẻ FIFO.

Khi cần thứ tự logic, gắn sequence/version theo **request/aggregate/stream** đúng phạm vi; không dựa vào thứ tự các dòng trên dashboard để quyết định transaction order.

## 12. Security: TLS, mTLS, authentication và kiểm soát quyền riêng tư

Remote appender đưa dữ liệu **ra khỏi JVM**. Đây là một ranh giới bảo mật:

- **TLS:** mã hóa đường truyền và xác minh server certificate/hostname. Không tắt verifyHostName một cách tùy tiện.
- **mTLS:** xác thực hai chiều khi kiến trúc yêu cầu; quản lý client certificate và private key.
- **Authentication:** token/API key cho HTTP/OTLP exporter nếu backend yêu cầu. Lưu trong secret manager hoặc injection được quản lý, không hard-code vào source/log.
- **Authorization:** receiver phải giới hạn tenant/service được ingest và giới hạn quyền truy vấn.
- **Network segmentation:** endpoint chỉ mở cho workload được phép; cân nhắc egress policies/firewall.
- **Least privilege:** người xem log không tự động được quyền xem credential của ứng dụng.
- **Retention:** log index và backup có thời gian lưu phù hợp.
- **Sanitization tại nguồn:** không log access token, password, session cookie, JDBC connection URL có secret, raw request body hoặc dữ liệu cá nhân không cần thiết.

Một lỗi cực nguy hiểm: cấu hình remote appender có auth header, rồi bật internal DEBUG và log toàn bộ HTTP request của exporter. **Token của chính exporter** có thể bị ghi vào log, tạo vòng lặp rò rỉ. Cần bảo vệ cả internal status logging, diagnostics và secret rotation.

### 12.1. Rủi ro Java serialization

Một số remote logging implementations lịch sử trao đổi **serialized Java objects**. Đây không phải generic JSON line và không phù hợp mở cho untrusted clients. Deserialization không an toàn có thể tạo bề mặt tấn công; hãy ưu tiên protocol có schema/validation rõ ràng, dùng endpoint được kiểm soát và cập nhật framework khi triển khai.

Không xây public socket server dùng `ObjectInputStream.readObject()` để chấp nhận bất kỳ bytes nào từ Internet như một “log receiver đơn giản”.

### 12.2. Credential rotation và TLS errors

Khi certificate hết hạn/rotate, remote logs có thể đột ngột ngừng xuất; kiểm tra TLS handshake, truststore, SAN/hostname verification, đồng hồ hệ thống và network ACL. Đừng vội đổi thành TCP plain để “fix” mà làm lộ dữ liệu vận hành. Với exporter auth, tránh in token vào exception/headers trong logs khi debug.

## 13. Container/Kubernetes: vì sao stdout + agent thường là đường dễ vận hành

Trong môi trường container, một kiến trúc phổ biến:

```text
Java App 1 -> stdout/stderr ----\
Java App 2 -> stdout/stderr -----+--> node/container log collector
Java App 3 -> stdout/stderr ----/                |
                                              queue/batch
                                                  |
                                               backend
```

Điểm mạnh:
- Application tập trung vào nghiệp vụ và local logging.
- Runtime/shipper thu log theo instance/pod metadata.
- Có thể thay đổi đường ship mà không rebuild mỗi service.
- Một collector dùng chung có thể áp policy/retention/ACL/schema nhất quán.

Nhưng đây **không tự là zero-loss**. Container runtime có rotation/retention, collector có offsets/queue, node disk có thể đầy và pod có thể bị kill trước khi stdout được ship. Cần tính độ bền của từng tầng và kiểm tra shutdown/restart.

### 13.1. Dùng remote appender trực tiếp trong container khi nào?

Có thể hợp lý khi:
- Collector/gateway gần workload có endpoint được quản lý.
- Muốn OTLP logs có resource metadata/trace correlation.
- Framework có exporter chuẩn cùng chính sách retry.
- Tổ chức muốn telemetry qua một secured endpoint thay vì file tail.

Cần cẩn trọng:
- `127.0.0.1` trong app container **không phải** node host hay Collector container khác nếu không share network namespace.
- Service discovery/DNS, TLS, proxy, sidecar lifecycle cần được kiểm tra.
- Nếu vừa ship stdout vừa export log OTLP vào **cùng một index**, có thể có duplicate.
- Pod bị terminate cần drain queue trong shutdown budget; não trạng “flush xong là persisted” không có bảo đảm end-to-end.

## 14. AsyncAppender và remote destination: không để mạng đi vào critical path

Nếu một HTTP appender gửi một request mạng cho **mỗi** log trong thread xử lý HTTP request của ứng dụng, network latency có thể chi phối request latency. Với 10 log records/request và 50 ms round-trip mỗi HTTP call (đơn giản hóa), overhead lý thuyết có thể tăng hàng trăm ms khi gửi tuần tự.

Dùng AsyncAppender hoặc exporter batch để giảm blocking. Nhưng phải khai báo rõ:
- Queue size và data structure.
- Full-queue policy: block, drop hoặc fallback.
- Retry/backoff và circuit breaker.
- Thời gian dừng để flush/drain.
- Số worker và concurrency.
- Thứ tự xử lý qua nhiều connection.
- Bảo vệ dữ liệu trong in-memory/disk buffers.

**Async không đồng nghĩa reliable.** Queue in-memory giúp latency trung bình, nhưng crash và outage kéo dài vẫn gây loss. Ngược lại, ép `blocking=true` ở mọi log có thể kéo sập service khi backend logging chậm; phải cân nhắc availability của ứng dụng.

### 14.1. Chọn policy theo severity

Một thiết kế có thể:
- DEBUG/INFO: best-effort; có sampling hoặc drop khi queue áp lực.
- WARN/ERROR: ưu tiên đường gửi đáng tin hơn, retention/troubleshooting riêng.
- Audit/security events bắt buộc: **không chỉ trông vào remote appender**; dùng durable store/transaction.

Không nên chỉ dựa level ERROR để khẳng định “không mất”; trong crash network/queue, mọi level đều có thể mất trừ khi đã thiết kế durability. Cũng không nhất thiết mọi WARN đều quan trọng hơn một INFO nghiệp vụ đã được chuẩn hóa; policy theo **event class** thường rõ hơn level thuần túy.

### 14.2. Graceful shutdown

Khi Kubernetes gửi SIGTERM:
1. Ngừng nhận workload mới khi thích hợp.
2. Cho in-flight requests hoàn tất trong grace period.
3. Đóng logging framework/exporter và cho queue drain.
4. Xác minh thời gian timeout/remaining events.
5. Ghi số liệu shutdown diagnostics nếu có kênh phù hợp.

Nếu JVM bị kill cưỡng bức hoặc process crash, không đảm bảo finally/shutdown hook chạy. Một thiết kế zero-loss cần durability trước khi crash, không chỉ thêm sleep khi exit.

## 15. Monitoring chính remote logging pipeline

Không chỉ quan sát app logs; bản thân đường vận chuyển phải có metrics/health:

| Metric gợi ý | Ý nghĩa | Khi nào đáng cảnh báo |
| --- | --- | --- |
| `remote_log_queue_depth` | Số event chờ gửi | Tăng liên tục hoặc gần capacity |
| `remote_log_queue_capacity` | Sức chứa tối đa | Mức sử dụng cao kéo dài |
| `remote_log_events_dropped_total` | Event bị bỏ | Tăng liên tục, đặc biệt event quan trọng |
| `remote_log_send_errors_total` | Gửi/encode lỗi | Spike sau deploy/rotation/TLS |
| `remote_log_retry_total` | Số lần retry | Xu hướng tăng, network/backend bất ổn |
| `remote_log_ack_latency_ms` | Delay tới ACK có định nghĩa rõ | p95/p99 cao so với SLO |
| `collector_exporter_queue_size` | Backlog exporter | Tăng cùng backend errors |
| `collector_exporter_queue_capacity` | Sức chứa collector queue | Queue gần đầy, nguy cơ drop |
| `log_ingest_delay_seconds` | Chênh event-to-observed/index time | Tăng do queue/retry/clock skew |
| `log_source_vs_backend_count` | Sai lệch lượng event | Phát hiện loss/duplicate khi đo được |

**Các tên trên là mẫu khái niệm**, không bảo đảm là tên metrics chính thức của Logback, Log4j 2 hoặc OTel Collector trong mọi phiên bản. Khi triển khai, xem metrics thực sự mà framework/Collector xuất (ví dụ họ `otelcol_exporter_queue_size` và capacity trong Collector) rồi đặt dashboard tương ứng.

Đếm số log bằng một query backend có thể không phản ánh nguồn do sampling/filter/retention, vì vậy đo counters tại nguồn và từng chặng nếu muốn phát hiện loss.

### 15.1. Tự giám sát nhưng tránh vòng lặp lỗi

Khi remote appender lỗi, nó có thể ghi internal error vào **StatusLogger**/diagnostic logger. Nếu internal error lại đi qua chính remote appender đang down, có thể tạo nhiễu hoặc vòng lặp. Nên dùng **kênh fallback local được kiểm soát** (stderr/file riêng) cho lỗi của logging infrastructure; hạn chế tần suất để không spam vô hạn.

Không đặt log success cho mọi event ở INFO chỉ để chứng minh đã ship: việc tự log trạng thái shipping có thể làm traffic tăng và khiến hệ thống tự gây nghẽn.

## 16. Một kế hoạch kiểm thử failure injection

Thử từng lớp để hiểu contract trước khi production:

| Test | Thao tác | Quan sát mong đợi |
| --- | --- | --- |
| Normal send | Receiver hoạt động | Event parse được, đúng schema và ID |
| No listener | Tắt receiver | Connect timeout/error theo policy, app không treo ngoài giới hạn |
| Network blackhole | Chặn outbound | Timeout hữu hạn, retry/backoff và queue bounded |
| TLS bad certificate | Dùng certificate không hợp lệ ở lab | Kết nối thất bại, không silently downgrade |
| Wrong port/protocol | Gửi text TCP vào OTLP/HTTP | Receiver reject, không coi là ingest success |
| Queue full | Gửi nhanh hơn receiver | Block/drop/fallback đúng policy; metric tăng |
| Receiver crash before ACK | Kill khi chưa xác nhận | Sender retry theo contract, không assume delivered |
| Receiver crash after ACK | ACK rồi kill trước durable write | Nhìn rõ giới hạn của ACK in-memory |
| Lost ACK | Receiver nhận nhưng sender timeout | Retry có thể duplicate; dedupe nếu thiết kế |
| Disk full | Fill spool trong lab | Policy/quota/health thông báo và không phá dữ liệu khác |
| Restart sender | JVM stop khi queue còn backlog | Biết event nào được/không được giữ |
| Restart Collector | Collector exporter queue tồn | Xem memory vs persistent queue, loss window |
| Malformed multiline | Gửi stack trace chứa newline | Framing/JSON parser không tách sai event |
| Oversized event | Payload lớn bất thường | Rejection/truncation policy minh bạch |
| Log chứa synthetic secret | Cài canary test | Không xuất ra bất kỳ sink/alert/trace nào |
| Dual pipeline | stdout shipper + OTLP trực tiếp | Không duplicate cùng event ngoài dự kiến |
| Clock skew | Điều chỉnh giờ lab | Query sort không làm sai source timestamp |
| High volume | Burst trong giờ cao điểm | CPU, heap, latency app và queue được đo |

Đừng dùng token thật hoặc mở public receiver cho load test. Nếu cần reproduce TLS/certificate failures, dùng môi trường biệt lập với certificate lab. Sau thử nghiệm, dọn synthetic records theo chính sách và trả lại logging levels bình thường.

### 16.1. Kiểm thử độ chính xác của payload

Giả sử ứng dụng phát một event:

```json
{
  "event_id": "evt-demo-1",
  "event": "order.created",
  "level": "INFO",
  "service.name": "orders-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "order_id": "demo-42"
}
```

Đây là schema tổng hợp, không phải bắt buộc của OTLP. Nếu dùng NDJSON, payload phải escape newline và quote đúng. Kiểm tra:
- Một event tại nguồn thành bao nhiêu records tại receiver?
- Tên field và types có còn đúng sau parser?
- Các trường trace/resource có còn nguyên?
- Timestamp có bị đổi sang observed/ingest time không?
- Có duplicate/truncation/encoding error khi có tiếng Việt?
- Có bí mật lọt qua exception/MDC/structured fields không?

Một phép test chỉ nhìn “có HTTP 200” là **chưa đủ**; cần đọc lại event ở receiver hoặc backend theo phạm vi test được phép.

## 17. Troubleshooting theo triệu chứng

### 17.1. App có log nhưng backend không thấy

Kiểm tra theo thứ tự:
1. Logger level/filter có tạo event không?
2. Appender đã được root/logger tham chiếu chưa?
3. Có queue overflow/drop hoặc sampling ở nguồn không?
4. Hostname, port, DNS, route, firewall, security group có đúng không?
5. TLS handshake, truststore, hostname verification, credentials có lỗi không?
6. Receiver có support **đúng protocol/format** không?
7. Receiver được khai báo nhưng đã gắn vào active pipeline chưa?
8. Collector processors có drop/mutate event không?
9. Exporter queue/retry/backend có chậm/hỏng không?
10. Query dashboard có đúng time range, environment, service và tenant không?

Không đọc tràn lan các log credential hoặc dump raw network traffic lên ticket. Sử dụng synthetic event có event ID dễ tìm.

### 17.2. App bị chậm khi logging tăng

Khả năng:
- HTTP remote appender đang synchronous.
- Connect/read timeout quá dài hoặc vô hạn.
- Async queue full khiến producer block.
- Encoder JSON/caller data/stack trace tốn CPU.
- Worker/fallback disk đang nghẽn.
- DNS/TLS handshake liên tục vì không reuse connection.
- Log storm tự gây ra bởi lỗi logging infrastructure.

Đo request latency khi bật/tắt remote path trong lab, queue depth, thread dumps, connection timing và event size. Không tắt toàn bộ ERROR logging để “cứu hiệu suất” mà không có kế hoạch giữ tín hiệu cần thiết.

### 17.3. Missing events sau downtime

Đọc contract thực tế:
- Logback SocketAppender có thể bỏ event lúc remote unavailable.
- Log4j 2 Socket TCP không có application ACK mặc định.
- AsyncAppender queue in-memory có giới hạn và crash loss.
- Collector exporter queue có thể bị overflow/retry hết hạn.
- Stdout/file rotation có thể xóa trước khi ship.
- Backend có thể dùng retention/filter.

Không tuyên bố chắc chắn “TCP đã gửi nên không thể mất”; so source event counters với receiver/backend counts và event IDs.

### 17.4. Log bị trùng

Các nguyên nhân:
- Logger gắn cùng appender ở root và logger con do additivity.
- Console/file shipper và OTLP bridge cùng ingest một logical event.
- Retry sau lost ACK.
- Consumer đọc lại checkpoint/offset hoặc service xử lý nghiệp vụ lại.
- Client thực tế gọi logger hai lần.

Dùng event ID, trace ID, resource identity và retry attempt để phân biệt duplicate transport với hai sự kiện nghiệp vụ khác nhau. Không dedup bằng message text thuần túy.

### 17.5. Log sai thứ tự

Nguyên nhân có thể là nhiều threads, sockets, async queues, retries, clock skew hoặc backend sort. TCP chỉ bảo đảm bytes theo thứ tự trên **một connection**. Nếu thứ tự nghiệp vụ là yêu cầu, cần sequence/version đúng phạm vi ở tầng nghiệp vụ, không phụ thuộc thứ tự hiển thị của log.

## 18. Những anti-pattern nên tránh

**Một — gửi HTTP remote sync cho mọi DEBUG log:** request business bị phụ thuộc network/collector.

**Hai — dùng TCP write thành công như bằng chứng persisted:** byte stream không phải application-level durable ACK.

**Ba — dùng UDP cho audit bắt buộc:** không có delivery guarantee phù hợp.

**Bốn — mở receiver Java serialization ra Internet:** bề mặt tấn công không cần thiết, phải dùng trust boundary/schema an toàn.

**Năm — queue in-memory vô hạn:** heap/GC/OOM, không giải quyết outage kéo dài.

**Sáu — bật blocking với timeout vô hạn trên request path:** backend logging có thể làm cả dịch vụ mất availability.

**Bảy — retry ngay trong `log.info` vô hạn:** kéo dài latency và có thể duplicate.

**Tám — giữ token/PII trong raw log rồi chỉ mask ở Collector:** dữ liệu đã rời JVM và đi qua nhiều buffer/sink.

**Chín — cấu hình Logback SocketAppender vào cổng OTLP:** protocol không tương thích.

**Mười — gửi stdout và OTLP vào cùng một index không dedupe:** một event xuất hai lần.

**Mười một — bỏ qua graceful shutdown/drain:** event tồn ở queue bị mất khi pod dừng.

**Mười hai — chỉ nhìn app logs để biết remote appender đang khỏe:** khi chính remote path lỗi, logs có thể không tới. Dùng metrics/health độc lập.

**Mười ba — quên resource identity:** thiếu service.name, environment, instance, trace ID khiến log tập trung khó dùng.

**Mười bốn — in hết exception và request body:** có thể lộ credential, dữ liệu cá nhân và biến một sự cố thành sự cố security.

## 19. Checklist chọn giải pháp và triển khai

### Trước khi chọn công nghệ

1. Xác định **mục đích**: observability best-effort hay audit phải giữ bền vững?
2. Xác định **phạm vi outage** cần chịu: 30 giây, vài phút hay nhiều giờ?
3. Xác định **nguy cơ mất log** được chấp nhận theo event class.
4. Đo event rate/size trung bình và peak; tính queue/spool capacity và catch-up throughput.
5. Chọn một transport/protocol/format mà receiver thực hỗ trợ.
6. Chọn log source path: direct remote, stdout/file shipper hay OTLP. Tránh double ingest.

### Khi cấu hình

7. Cấu hình hostname/port, DNS, TLS/mTLS, auth và verify hostname.
8. Đặt connect/read timeouts, retry/backoff, bounded queue và overflow policy.
9. Chuẩn hóa structured fields, timestamp, service name, trace/request ID.
10. Không xuất credential, PII nhạy cảm, raw headers/query/bind values.
11. Xem xét một kênh fallback local cho **diagnostic của logging infrastructure**.
12. Nếu cần durability, xác định khi nào ACK được phát và dữ liệu nằm ở đâu sau restart.

### Sau khi triển khai

13. Test normal delivery, wrong protocol, network down, receiver restart, queue full, lost ACK và duplicate.
14. Theo dõi drops, retries, queue depth, export failures, ingest delay và CPU/heap.
15. Kiểm thử graceful shutdown và forced crash trong môi trường an toàn.
16. Kiểm tra sample events end-to-end trên backend: encoding, timestamp, metadata và trace correlation.
17. Rà soát retention, quyền đọc log, secret rotation và TLS certificate lifecycle.
18. Tài liệu hóa **delivery guarantee thật sự** thay vì viết chung “reliable logging”.

**Kết luận:** Remote appender là cầu nối từ logging event của JVM tới hệ thống thu thập qua mạng. Nó thuận tiện, nhưng **không tự tạo tính bền vững** chỉ vì dùng TCP, TLS, HTTP hay async queue. Thiết kế tốt phải thống nhất format/protocol, xác định ACK ở tầng nào, có chính sách queue–retry–overflow rõ, bảo vệ dữ liệu và kiểm thử bằng failure injection. Khi nhu cầu là audit bắt buộc hoặc giao dịch không được mất, hãy thiết kế một nguồn ghi bền vững ở tầng nghiệp vụ thay vì chỉ phụ thuộc vào remote logging.

## Tài liệu tham khảo

- [Logback – Network Appenders, SocketAppender](https://logback.qos.ch/manual/appenders-network.html).
- [Apache Log4j 2 – Network Appenders, Socket/HTTP/TLS](https://logging.apache.org/log4j/2.x/manual/appenders/network.html).
- [Apache Log4j 2 – Asynchronous loggers](https://logging.apache.org/log4j/2.x/manual/async.html).
- [OpenTelemetry – OTLP specification: acknowledgments và retryable responses](https://opentelemetry.io/docs/specs/otlp/).
- [OpenTelemetry – Collector receiver OTLP](https://github.com/open-telemetry/opentelemetry-collector/tree/main/receiver/otlpreceiver).
- [OpenTelemetry – Collector resiliency, retry và persistent queue](https://opentelemetry.io/docs/collector/resiliency/).
- [OpenTelemetry – Collector troubleshooting](https://opentelemetry.io/docs/collector/troubleshooting/).
- [OpenTelemetry – Logs data model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- [Java SE 17 – ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html).
- [Java SE 17 – Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html).
- [RFC 5424 – The Syslog Protocol](https://www.rfc-editor.org/rfc/rfc5424).
- [RFC 5425 – Transport Layer Security (TLS) Transport Mapping for Syslog](https://www.rfc-editor.org/rfc/rfc5425).
- [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).