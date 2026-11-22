# Agent trên máy chủ trong Java Logging: thu thập, đệm và vận chuyển log

## 1. Agent trên máy chủ là gì?

Trong kiến trúc logging, **host logging agent** là tiến trình chạy trên máy chủ, máy ảo hoặc node để đọc log được sinh ra bởi một hay nhiều ứng dụng, bổ sung metadata, xử lý định dạng, đệm khi mạng gặp sự cố và chuyển log tới collector, message broker hoặc backend observability.

Ví dụ một Java service ghi log qua SLF4J + Logback ra stdout hoặc rolling file. Một agent như **Fluent Bit, Filebeat, Vector** hoặc **OpenTelemetry Collector triển khai ở vai trò agent** có thể thu thập các bản ghi ấy mà ứng dụng không phải tự kết nối trực tiếp tới mọi đích.

~~~text
Java service A --- stdout/file ---+
                                  |
Java service B --- stdout/file ---+--> Host agent
                                  |      |
Other host logs --- journald -----+      +--> Parse/enrich/filter
                                         +--> Memory/disk buffer
                                         +--> Batch/retry
                                                 |
                                                 v
                                        TLS / network gateway
                                                 |
                                                 v
                                         Collector / storage
                                                 |
                                                 v
                                         Search / alerts / SIEM
~~~

Agent không phải là **logger**, **MDC adapter**, **broker**, hay **bản thân hệ thống lưu trữ cuối**. Logger phát event; agent tiếp nhận và vận chuyển event theo pipeline được cấu hình. Việc agent trả về thành công khi đọc một dòng không có nghĩa backend đã nhận hoặc lưu bền vững dòng đó.

Mục tiêu học bài này: biết đặt agent ở đâu, chọn source nào, bảo đảm framing/offset/rotation, điều chỉnh buffering và backpressure, kiểm soát quyền riêng tư, kiểm tra cơ chế retry và xác minh pipeline từ Java service đến backend.

## 2. Vì sao không để mỗi ứng dụng tự đẩy mọi log?

Ứng dụng có thể gửi log trực tiếp qua HTTP/OTLP/TCP hoặc appender chuyên dụng. Cách này có trường hợp hợp lý, nhưng host agent đem lại các ưu điểm:

- **Tách trách nhiệm:** code Java tập trung vào nghiệp vụ; vận chuyển, retry, endpoint, credentials và batch do agent quản lý.
- **Dùng chung tài nguyên:** nhiều tiến trình có thể chia sẻ một pipeline thu thập thay vì mỗi app có client riêng.
- **Thống nhất cấu hình:** metadata host/service, policy redaction, routing, sampling cho log chẩn đoán và TLS được quản lý tập trung.
- **Giảm phụ thuộc trực tiếp:** khi backend tạm lỗi, agent có thể giữ dữ liệu trong hàng đợi, theo giới hạn dung lượng và chính sách.
- **Quan sát hệ thống ngoài Java:** systemd journal, container logs, một số log hệ điều hành hoặc daemon có thể được thu cùng luồng.
- **Đổi backend:** ứng dụng chỉ cần giữ log schema ổn định, agent/collector điều chỉnh output.

Tuy nhiên agent cũng có chi phí và điểm lỗi riêng: CPU parse, memory queue, disk spool, volume log, độ trễ, deadlocks do full disk, quyền đọc file và sự cố cấu hình. **Có agent không đồng nghĩa log được giao exactly-once**. Retry sau ACK mất có thể tạo trùng; thiếu buffer bền vững hoặc retention ngắn có thể làm mất event.

## 3. Agent, sidecar, gateway và collector khác nhau ra sao?

| Vai trò | Triển khai | Thường chịu trách nhiệm |
| --- | --- | --- |
| **Host agent** | Mỗi VM/node, systemd service hoặc Windows service | Đọc nhiều nguồn cục bộ, theo dõi vị trí file, gửi log |
| **Kubernetes DaemonSet** | Một hoặc một nhóm pod agent trên mỗi node đủ điều kiện | Thu container stdout/stderr và host-level logs |
| **Sidecar** | Cùng pod/đơn vị triển khai với app | Đọc volume/log riêng của workload |
| **Central gateway/collector** | Service tập trung, có load balancing và HA | Nhận từ agents, enrich, route và export |
| **Logging backend** | Search/warehouse/object store/SIEM | Lưu, index, retention và truy vấn |
| **Java logging provider** | Bên trong JVM, ví dụ Logback | Tạo/format event theo level/context |

Một sản phẩm có thể đảm nhiệm nhiều vai trò tùy cấu hình. Ví dụ **OpenTelemetry Collector** có thể chạy trên node như agent hoặc ở tầng gateway. Tên công cụ không xác định duy nhất vị trí triển khai.

**DaemonSet không có nghĩa là một agent cho mỗi pod**: thường là per-node; điều này ảnh hưởng quyền mount path, tên namespace, resource limits và cách chọn log source. Sidecar có ranh giới sở hữu gần app nhưng tăng số tiến trình khi có nhiều pod. Host-level agent đơn giản hơn về quản trị tập trung trên node, song cần cách phân biệt dữ liệu của nhiều workload.

## 4. Chọn nguồn log từ Java application

Một host agent có thể đọc các nguồn sau:

| Nguồn | Cách ghi từ Java | Điểm cần lưu ý |
| --- | --- | --- |
| **stdout/stderr** | ConsoleAppender / standard streams | Container runtime hoặc service manager thường là tầng lưu log đầu tiên |
| **Rolling file** | RollingFileAppender | Rotation, inode/file identity, rename, copytruncate, quyền truy cập |
| **systemd journal** | JVM stdout/stderr chạy dưới systemd | Journal cursor, persistence, permissions, rate limiting |
| **Container log files** | stdout/stderr được runtime ghi trên node | Pod/container metadata và rotation do runtime/kubelet quản lý |
| **Windows event sources** | App/host integration đặc thù | Provider và API nguồn thay đổi theo môi trường |
| **Socket hoặc OTLP receiver** | Appender/SDK xuất trực tiếp theo protocol | Cần endpoint/batching và không phải "tail file" |

**Không thu đồng thời cùng một event từ hai đường không có chủ đích.** Ví dụ app vừa ghi console vừa ghi file, agent thu cả hai sẽ tạo duplicate ở backend. Thiết lập rõ **source of truth**, nếu phải thu nhiều đường thì phải có strategy phân biệt/deduplicate.

Với ứng dụng trong container, ưu tiên hiểu đường đi stdout → runtime logs → node agent. File nằm trong filesystem riêng của container không nhất thiết có thể được host agent đọc, trừ khi volume/mount/driver hỗ trợ.

Với JVM chạy trên VM, có thể dùng console dưới systemd journal hoặc file; quyết định dựa trên chính sách retention, rotation, quyền truy cập và khả năng thu của agent.

## 5. Định dạng event: ưu tiên cấu trúc có hợp đồng

Một agent làm việc ổn định hơn khi ứng dụng xuất **một log event trên một dòng JSON (NDJSON/JSON Lines)**, nếu framework và pipeline hỗ trợ. Ví dụ:

~~~json
{"timestamp":"2026-11-10T03:15:00Z","level":"INFO","service":"order-api","event":"order_accepted","requestId":"req-42","durationMs":18}
~~~

**JSON serializer** phải escape các ký tự xuống dòng, dấu ngoặc kép và control characters trong string. Không tự nối JSON từ raw user input; một object hợp lệ không tự bảo đảm dữ liệu nhạy cảm đã được redact.

Các trường hữu ích:

| Field | Nguyên tắc |
| --- | --- |
| timestamp | Thời gian phát event, có timezone/UTC rõ ràng |
| level | DEBUG/INFO/WARN/ERROR do logger quyết định |
| service, version, environment | Metadata ít biến động; có thể enrich tại agent |
| host.name, node, container.id | Metadata nguồn, tránh giả mạo từ payload |
| event/eventCode | Giá trị chuẩn hóa, không phải đoạn text tùy ý |
| requestId, traceId, spanId | Định danh correlation đã validate |
| loggerName, threadName | Phục vụ điều tra Java |
| exception.type, stacktrace | Dữ liệu lỗi theo schema và policy |
| message | Dành cho mô tả, không dùng làm nguồn duy nhất của alert |
| schemaVersion | Giúp parser chuyển đổi định dạng có kiểm soát |

Nếu app xuất timestamp lẫn agent thêm timestamp nhận, cần phân biệt **event time** và **ingestion time**. Không thay event timestamp bằng giờ agent mà không lưu trường riêng khi việc này làm sai timeline.

**Message ID và trace ID không nên làm metric labels** do cardinality cao; giữ chúng trong log/traces, dùng metrics tổng hợp cho throughput và lỗi.

## 6. Các stage bên trong host agent

Một pipeline trừu tượng:

~~~text
Source read
    |
    v
Framing (line / journal entry / protocol frame)
    |
    v
Parser (JSON, regex hoặc multiline)
    |
    v
Enrichment (host, service, env, source)
    |
    v
Filter / transform / redaction
    |
    v
Memory queue hoặc filesystem-backed buffer
    |
    v
Batch + compress nếu được hỗ trợ
    |
    v
Transport (TLS / mTLS / authenticated protocol)
    |
    v
Remote acknowledgment
    |
    v
Advance durable checkpoint / release buffered record
~~~

Đây là **mô hình logic**, thứ tự thực tế giữa parse, buffer, read checkpoint và send phụ thuộc agent/plugin. Có implementation cập nhật **file read offset** trước khi remote ACK nhưng lưu bản record trong disk buffer đã chấp nhận; do vậy không được suy ra một cơ chế duy nhất từ hình vẽ.

Điểm cần hiểu là hai loại trạng thái khác nhau:

- **Read position/checkpoint:** agent đã đọc đến vị trí nào của nguồn.
- **Delivery/persisted buffer state:** dữ liệu đã được lưu bền vững ở đâu và còn chờ destination ACK hay không.

Một pipeline có thể đọc đến EOF mà vẫn còn hàng nghìn event chưa gửi; nếu chỉ nhìn offset đã tăng thì chưa thể gọi vận chuyển hoàn tất.

## 7. Offset, cursor và state persistence

Khi tail file, agent cần biết lần trước đã đọc đến đâu để tránh đọc lại toàn bộ khi restart. Với file thường, trạng thái có thể liên quan đến **file identity + byte offset** (cách nhận dạng cụ thể tùy hệ điều hành và agent). Với journald thường dùng **journal cursor**; với protocol stream có thể dùng sequence, ACK hoặc state khác.

Tránh hai giả định:

1. **Offset tăng đồng nghĩa backend đã nhận.** Sai: offset có thể mô tả đọc nguồn, không phải gửi remote.
2. **Restart từ đúng offset bảo đảm exactly-once.** Sai: nếu remote đã nhận nhưng ACK mất, retry có thể gửi trùng. Nếu checkpoint quá sớm và buffer bị mất, event có thể không còn để gửi.

Một thiết kế vững cần định nghĩa:

- State/checkpoint file hoặc database nằm ở đâu và có persist qua restart không.
- File identity có nhận diện được file sau rename rotation không.
- Agent đồng bộ read offset với spool như thế nào.
- Remote ACK có nghĩa là đã nhận, đã queue hay đã lưu bền vững (theo protocol).
- Mất state file dẫn đến đọc lại từ đầu, từ cuối hay policy recovery nào.
- Backup state có đi cùng backup logs/buffer không, và restore có gây duplicate/truncation không.

**Chọn delivery semantics rõ ràng.** At-least-once thường là mục tiêu thực dụng khi chấp nhận duplicate và có buffering/retry; không tuyên bố exactly-once chỉ vì có file offset checkpoint.

## 8. File rotation: rename khác copytruncate

Các ứng dụng Java dùng RollingFileAppender có thể rotate theo kích thước/thời gian. Hai mẫu vận hành phổ biến có tác động khác nhau:

### Rename/create

~~~text
Trước:
  app.log   (inode A)  <- JVM ghi

Rotation:
  app.log -> app.log.1 (inode A)
  app.log mới (inode B) <- JVM bắt đầu ghi
~~~

Agent cần tiếp tục đọc **phần chưa xử lý của inode A** và bắt đầu theo dõi file mới B. Nếu chỉ theo tên app.log mà không theo file identity và khoảng chờ rotation, có thể mất hoặc trùng đoạn chuyển tiếp.

### Copytruncate

~~~text
app.log được copy sang archive, sau đó truncate tại chỗ
~~~

Nếu app ghi trong khoảng copy và truncate, bytes có thể bị mất khỏi cả bản archive lẫn file hiện tại; agent cũng khó nhận biết vị trí mới nếu file giảm kích thước. **Ưu tiên tránh copytruncate khi thiết kế muốn độ tin cậy cao**, nếu stack rolling/logger hỗ trợ rename/create phù hợp.

Các thử nghiệm quan trọng:

- Rotate khi file đang được ghi liên tục.
- Restart agent giữa rotation và chưa gửi hết buffer.
- Nhiều file trùng pattern; file archive có bị đọc lại không?
- File bị xóa sớm trước khi agent kịp đọc.
- Disk space khi rolling/archive và agent spool cùng chia một partition.
- Quyền của agent đối với file mới sau rotation có được kế thừa đúng không?

Đừng thay đổi rotation policy chỉ theo cảm giác; phải đo lag, kiểm tra behavior plugin và thử trên môi trường gần production.

## 9. Multiline Java exception và framing

Java stack trace truyền thống có nhiều dòng:

~~~text
2026-11-10T03:15:00Z ERROR event=order_failed requestId=req-42
java.lang.IllegalStateException: payment unavailable
    at example.OrderService.pay(OrderService.java:42)
    at example.OrderHandler.handle(OrderHandler.java:18)
Caused by: java.io.IOException: connection closed
    at example.HttpClient.call(HttpClient.java:73)
~~~

Nếu agent coi **mỗi dòng vật lý là một event**, stack trace bị tách thành nhiều record thiếu timestamp/level/requestId. Nếu agent gom multiline quá rộng, có thể trộn stack trace của hai threads hoặc hai ứng dụng.

Giải pháp ưu tiên:

1. **Structured JSON một event trên một dòng**, stacktrace là string được JSON-escape.
2. Nếu phải dùng text logs, cấu hình **multiline parser** có quy tắc bắt đầu/kết thúc event đúng với pattern logging thực tế.
3. Đặt giới hạn số dòng/bytes và timeout flush của multiline buffer.
4. Test nested causes, suppressed exceptions, dòng bắt đầu bằng timestamp giả và payload CR/LF.
5. Kiểm tra parser có làm hỏng Unicode hoặc nhầm hai events do concurrency không.

**Không có regex multiline duy nhất đúng cho mọi ứng dụng Java.** Stack trace có thể đi qua custom throwable formatting, async appender, JSON encoder và runtime wrapper, cần kiểm tra dữ liệu thật.

**Log forging:** nếu user có thể chèn newline và chuỗi timestamp/level giả, parser theo mẫu dòng có thể hiểu phần message đó thành event khác. Validate ID, output-escape dữ liệu không tin cậy và ưu tiên NDJSON đúng chuẩn.

## 10. Ví dụ Java 17: mô phỏng host agent đọc file và chuyển theo ACK

Ví dụ độc lập sau tạo một file log UTF-8 tạm thời, đọc từng dòng, mô phỏng một collector sẽ **từ chối lần gửi đầu của event thứ hai**, retry, rồi cập nhật checkpoint logic sau ACK. Nó minh họa **cách suy nghĩ về delivery**, không phải một agent production có khả năng tail file đang tăng, network/TLS hay spool trên disk.

Tạo file **HostLogAgentDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class HostLogAgentDemo {

    private static boolean collectorAck(String event, int attempt) {
        boolean transientFailure =
                event.contains("\"event\":\"retry\"") && attempt == 1;
        return !transientFailure;
    }

    public static void main(String[] args) throws Exception {
        Path source = Files.createTempFile("host-log-agent-", ".jsonl");
        try {
            Files.write(source, List.of(
                    "{\"event\":\"start\",\"requestId\":\"req-42\"}",
                    "{\"event\":\"retry\",\"requestId\":\"req-42\"}",
                    "{\"event\":\"finish\",\"requestId\":\"req-42\"}"),
                    StandardCharsets.UTF_8);

            List<String> events = Files.readAllLines(
                    source, StandardCharsets.UTF_8);
            int checkpoint = 0;
            int acknowledgments = 0;

            for (int index = 0; index < events.size(); index++) {
                String event = events.get(index);
                int attempt = 1;
                boolean acknowledged = false;

                while (!acknowledged && attempt <= 2) {
                    System.out.println("send line=" + (index + 1)
                            + " attempt=" + attempt);
                    acknowledged = collectorAck(event, attempt);
                    if (acknowledged) {
                        System.out.println("ack line=" + (index + 1));
                    } else {
                        System.out.println("retry line=" + (index + 1));
                        attempt++;
                    }
                }

                if (!acknowledged) {
                    throw new IllegalStateException(
                            "unacknowledged log event");
                }
                checkpoint = index + 1;
                acknowledgments++;
            }

            System.out.println("checkpoint=" + checkpoint
                    + " acknowledgments=" + acknowledgments);
        } finally {
            Files.deleteIfExists(source);
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac HostLogAgentDemo.java
java HostLogAgentDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
send line=1 attempt=1
ack line=1
send line=2 attempt=1
retry line=2
send line=2 attempt=2
ack line=2
send line=3 attempt=1
ack line=3
checkpoint=3 acknowledgments=3
~~~

Giải thích:

- **Files.write / readAllLines** tạo và đọc ba bản ghi JSON một dòng, sử dụng UTF-8.
- **collectorAck** là một phương thức mô phỏng xác nhận từ collector; không gửi network request thật.
- Event có tên **retry** bị từ chối ở attempt=1, nên sẽ được gửi lại và nhận ACK ở attempt=2.
- **checkpoint** chỉ được tăng sau ACK logic trong ví dụ; sau ba event, giá trị là 3.
- **acknowledgments=3** đếm các event đã nhận ACK theo mô hình, không phải bằng chứng remote storage thực tế.
- File tạm được xóa trong finally; không có thread background.
- Ví dụ **không có persistent checkpoint**, cũng không xử lý rename/copytruncate, partial lines, concurrent writers, batch partial ACK, transport TLS, dead-letter, clock skew hay crash giữa send và ACK.
- Trong một host agent thực, checkpoint có thể đại diện **byte offset** hoặc journal cursor, còn dữ liệu chưa ACK có thể nằm trong **filesystem-backed queue**. Không nên dùng line index để thay thế byte offset khi tail UTF-8 production.

**Bài học:** một lần đọc file và một lần gửi chưa đồng nghĩa hoàn tất. Cần kiểm tra mốc đã nhận ACK, trạng thái buffer và khả năng retry/restart; kể cả khi ACK đúng, duplicate vẫn có thể xảy ra nếu ACK remote bị mất sau khi nơi nhận đã lưu.

## 11. Ví dụ cấu hình agent đọc file: Fluent Bit

Một cấu hình dạng **classic Fluent Bit** có thể minh họa vị trí của tail input, state DB, filesystem storage và output. Ví dụ này dành cho môi trường lab; tên plugin/option, behavior và yêu cầu bảo mật cần kiểm tra với **phiên bản Fluent Bit được triển khai**.

File cấu hình minh họa:

~~~ini
[SERVICE]
    Flush              1
    Log_Level          info
    storage.path       /var/lib/fluent-bit/storage

[INPUT]
    Name               tail
    Path               /var/log/myapp/*.jsonl
    Tag                java.app
    DB                 /var/lib/fluent-bit/tail.db
    Read_from_Head     Off
    Refresh_Interval   5
    storage.type       filesystem

[OUTPUT]
    Name               forward
    Match              java.app
    Host               log-gateway.example.net
    Port               24224
    Retry_Limit        False
    tls                On
    tls.verify         On
~~~

Giải thích từng ý tưởng:

- **tail input** đọc các file khớp với path; file phải tồn tại hoặc được tạo bởi Java service.
- **DB** lưu state tail nhằm hỗ trợ restart; volume chứa DB cần có quyền và lifecycle đúng.
- **Read_from_Head Off** là một quyết định bootstrap: file mới được phát hiện có thể không gửi lại lịch sử đã tồn tại. Hành vi còn phụ thuộc DB, plugin version và cấu hình.
- **storage.type filesystem** cho phép pipeline dùng cơ chế buffering trên filesystem theo policy của engine/plugin, nhưng cần giới hạn dung lượng và hiểu semantics thực tế.
- **forward output** gửi đến gateway hỗ trợ giao thức tương ứng; **tls On** và **tls.verify On** chỉ hữu ích khi endpoint có chứng chỉ hợp lệ/trust chain đúng.
- **Retry_Limit False** biểu thị ý định retry không giới hạn theo plugin; không có nghĩa dữ liệu không thể mất nếu đầy disk, file nguồn bị xóa hoặc quá tải kéo dài.
- Địa chỉ **log-gateway.example.net** chỉ là tên miền minh họa dành cho lab, không phải dịch vụ đang hoạt động. Cấu hình phải được thay bằng endpoint do tổ chức quản lý và kiểm chứng kết nối.

Không đưa credential hoặc private key trực tiếp vào log; nếu agent cần client certificate/token, quản lý qua secret store và file permission phù hợp. Cấu hình riêng của forward receiver/gateway phải hỗ trợ TLS/protocol tương ứng; nếu không, agent sẽ kết nối thất bại.

Một deployment production còn cần **memory/disk quota, output timeout, monitoring, file rotation behavior, service lifecycle, crash recovery và giới hạn retry**. Không copy cấu hình trên để vận hành môi trường thật mà chưa kiểm thử các điều kiện ấy.

## 12. Triển khai agent trên VM hoặc bare metal

Khi chạy như systemd service trên Linux, nên xác định:

- **User/group riêng** có quyền tối thiểu để đọc nguồn log.
- Agent có quyền ghi vào **state DB** và **spool directory** riêng.
- State/spool nằm trên filesystem phù hợp, không tự mất khi restart nếu muốn resume.
- Service có chính sách restart, rate limiting và shutdown đủ thời gian flush.
- Số lượng file handles, CPU, memory và disk được giám sát.
- Quyền file mới sau rotation không làm agent mất quyền đọc.
- Kết nối collector sử dụng TLS, xác thực và cấu hình retry hợp lệ.
- Logs của chính agent được thu theo tuyến hợp lý nhưng tránh **recursive ingestion**.

Với systemd journald, có thể đọc journal thay vì tail text file nếu plugin/agent hỗ trợ. Khi đó offset file được thay bằng journal cursor/state; cần xem cấu hình persistent journal và quyền đọc journal. Nếu journal rate limiting/drop xảy ra trước khi agent đọc, agent không thể khôi phục những dòng chưa từng được lưu.

**Không chạy agent bằng root chỉ để né lỗi permission** khi một ACL/group hoặc chính sách quyền hẹp hơn là đủ. Quyền cao không cần thiết làm tăng tác động của plugin lỗi hoặc host bị xâm nhập.

## 13. Kubernetes: DaemonSet, volume và metadata

Trong Kubernetes, mẫu thường gặp là một agent DaemonSet đọc log container trên node. Cần hiểu đường đi:

~~~text
Java container stdout/stderr
          |
          v
Container runtime creates node log
          |
          v
Node agent (DaemonSet)
          |
          v
Kubernetes metadata enrichment
          |
          v
Collector / storage
~~~

Những điều cần kiểm tra:

- Node log path/mount đúng với runtime và cấu hình cluster.
- Pod/namespace/container metadata được gắn từ nguồn tin cậy; không cho application tự giả mạo mọi field.
- Có tránh thu trùng stdout và application log files không.
- Agent có chạy trên mọi node cần quan sát, kể cả node có taints/tolerations khác nhau.
- Quyền hostPath/RBAC/serviceAccount được giới hạn.
- Nếu pod bị xóa, node container log và state cursor còn được giữ đủ thời gian để thu hết không.
- Resource requests/limits của agent không gây eviction thường xuyên.
- Rotation bởi kubelet/runtime và log truncation được kiểm thử.
- Agent health check và rollout không làm mất state hoặc đồng loạt gián đoạn ingestion.

Khi cần isolation mạnh hoặc log format đặc thù từng workload, sidecar có thể phù hợp; nhưng làm tăng số processes, CPU/memory và complexity. Cần tránh tự giả định "sidecar luôn đáng tin hơn DaemonSet".

## 14. Buffering, retry và backpressure

Trong môi trường mạng không ổn định, agent thường có memory buffer hoặc filesystem-backed queue:

~~~text
Input throughput (logs/s)
        |
        v
Queue/backlog -------------------> Retry/batch output
        |                               |
        v                               v
Memory + disk quotas              Remote ACK/timeout
        |
        +--> warning / throttle / drop / pause input
~~~

**Backpressure** là khi downstream không theo kịp, pipeline phải điều tiết tốc độ hoặc xử lý tình trạng queue đầy theo chính sách. Các hậu quả có thể gồm:

- Agent tạm dừng đọc file; nguồn vẫn tiếp tục ghi.
- Filesystem spool tăng kích thước và có thể chạm dung lượng.
- Queue memory đầy; plugin có thể block, drop hoặc back off tùy cấu hình.
- Collector timeout, agent retry làm log đến muộn hoặc duplicate.
- Rotation xóa file nguồn khi agent chưa kịp đọc hết → mất event.
- Disk cùng partition đầy có thể làm **Java application cũng không ghi được log hoặc data**, tăng tác động sự cố.

Một policy phải trả lời:

1. Bao nhiêu bytes/records tối đa ở memory/disk?
2. Khi vượt giới hạn, **pause input, block app, drop mới, drop cũ** hay chuyển tuyến dự phòng?
3. Log levels/event classes nào được ưu tiên? Có audit logs bắt buộc không?
4. Có cảnh báo threshold trước khi disk đầy không?
5. Khi storage/network phục hồi, agent drain queue với tốc độ nào và có làm backend quá tải không?
6. ACK từ backend thật sự bảo đảm gì: nhận request, queue durable hay lưu trữ cuối?
7. Buffer có được mã hóa và phân quyền không nếu chứa PII/secret?

**Không mô tả "retry vô hạn" như một bảo đảm không mất dữ liệu.** Nếu disk hết, policy xóa spool, node bị hủy hoặc nguồn rotate mất file, retry không thể lấy lại bytes đã biến mất.

## 15. At-most-once, at-least-once và duplicate records

Điều cần thiết kế không chỉ là kết nối mạng có retry, mà là **semantics toàn tuyến**:

| Semantics | Điều có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Best effort / at-most-once | Một event có thể mất nếu transport lỗi | Dùng cho diagnostic logs không bắt buộc |
| At-least-once trong phạm vi được hỗ trợ | Retry có thể làm event xuất hiện nhiều lần | Idempotent writes/dedup ở backend nếu cần |
| Exactly-once end-to-end | Cần giao thức/state và atomicity ở mọi boundary | Không mặc định từ tail DB hoặc ACK |

Ví dụ failure window:

~~~text
Agent sends event E
      |
      v
Collector stores E
      |
      +--> ACK response lost
                |
                v
            Agent retries E
                |
                v
       Backend may see duplicate E
~~~

Nếu muốn dedup, cần chọn event identifier rõ ràng (ví dụ eventId từ ứng dụng, hoặc ID ổn định do pipeline tạo theo content/source và policy). Không dùng hash message text như "ID duy nhất" mà không cân nhắc hai events hợp lệ có nội dung giống hệt.

**Một message log không phải một message nghiệp vụ**: việc duplicate ở backend observability có thể không ảnh hưởng business side effect, nhưng làm tăng số lượng alert/metric nếu tính theo log count. Dashboard nên biết cách đếm và loại trùng khi policy yêu cầu.

## 16. Truyền log an toàn: transport và quyền truy cập

Host agent chạy gần dữ liệu nguồn, thường có quyền đọc nhiều file/service. Cần áp dụng nguyên tắc **least privilege**:

- Chỉ mount/read đúng log paths; hạn chế đọc home directories, secrets và file ngoài scope.
- State DB và spool có permission đúng, không world-readable.
- TLS/mTLS hoặc authentication phù hợp giữa agent và gateway; xác minh certificate, không tắt verification để "cho chạy".
- Quản lý credential trong secret store hoặc file cấp quyền hẹp; rotate định kỳ theo policy.
- Redact/omit dữ liệu nhạy cảm **tại ứng dụng** khi có thể; processor tại agent là phòng vệ bổ sung.
- Kiểm soát schema/allowlist metadata để agent không gửi nhầm private header, environment secrets hoặc toàn bộ payload.
- Bảo vệ chống **log forging** và injection khi parse, đặc biệt với text multiline.
- Hạn chế quyền đọc dashboard/index và retention phù hợp.

**Không dựa vào TLS để che dữ liệu đã ghi vào file nguồn hoặc spool**. TLS bảo vệ trên đường truyền; file và state vẫn cần filesystem access controls, encryption at rest theo chính sách và retention.

**Không coi requestId/traceId là bí mật nhưng cũng không mặc định là vô hại**: các ID động có thể liên kết hoạt động của người dùng hoặc tiết lộ cấu trúc hạ tầng, nên cần phân quyền và thời gian lưu thích hợp.

## 17. Tài nguyên: CPU, memory, disk và network

Công suất của agent phụ thuộc:

- **Số nguồn log**, số file tails và tần suất scan.
- **Event rate** và kích thước bình quân, nhất là khi stack trace dài.
- CPU parse JSON/regex/multiline và metadata enrichment.
- Buffer memory, disk spool, tốc độ disk và độ bền của filesystem.
- Batching, compression, network RTT, bandwidth và remote throttling.
- Số output destinations và chính sách routing/replication.
- Mức độ log DEBUG/TRACE của các JVM trên host.

Một ước lượng capacity ban đầu:

~~~text
raw_bytes_per_second ≈ events_per_second × average_encoded_event_bytes

spool_bytes_needed ≈ raw_bytes_per_second × outage_seconds
                     × overhead_factor
~~~

**overhead_factor** phản ánh metadata/encoding, indices, batch framing và retry; giá trị thực phải đo. Một số nguồn nén được rất tốt, một số JSON payload entropy cao kém hiệu quả; không lấy compression ratio cố định làm cam kết.

Ví dụ mang tính tính toán: nếu có 2.000 events/s, mỗi event sau encode trung bình 500 bytes, raw throughput khoảng 1.000.000 bytes/s (xấp xỉ 1 MB/s theo hệ thập phân). Mất mạng 10 phút có thể tích lũy khoảng 600 MB dữ liệu raw, chưa tính overhead. **Kết quả thực tế** phụ thuộc nén, cấu hình queue và log burst.

Đặt disk watermark, timeout, retry/backoff và alert **trước** giới hạn cứng. Nếu dùng một partition cho app data và spool, cần đặc biệt thận trọng với disk-full cascade.

## 18. Health và metrics của agent

Một host agent cần tự được giám sát. Những chỉ số hữu ích:

| Metric hoặc dấu hiệu | Diễn giải |
| --- | --- |
| input_records_total / input_bytes_total | Nguồn được đọc bao nhiêu |
| output_sent / output_acknowledged | Đã gửi/được xác nhận theo protocol |
| output_errors / retries | Destination gặp lỗi hoặc đang retry |
| buffer_queue_depth / buffer_bytes | Backlog còn tồn |
| buffer_dropped / discarded | Dữ liệu bị bỏ theo policy |
| tail_files_open / watched | Số file đang theo dõi |
| checkpoint_age / read_lag | State có tiến triển không |
| input_parse_errors | Số dòng lỗi format/JSON/multiline |
| ingestion_delay | Khoảng cách event time đến received time |
| spool_disk_usage | Dung lượng queue trên disk |
| last_successful_export | Lần cuối destination xác nhận thành công |
| agent_restarts | Có crash loop hay rollout bất thường |

Tên metric trên là **khái niệm minh họa**, không phải tên chuẩn có sẵn trong mọi agent. Khi triển khai, chọn metric do sản phẩm/phiên bản thật xuất.

Một agent còn sống không có nghĩa đang thu đúng file: health check nên gồm khả năng đọc nguồn, tiến trình checkpoint, queue, output ACK và end-to-end synthetic canary khi có thể.

Không tạo **vòng lặp agent tự thu vô hạn chính log của nó**. Nếu agent phát lỗi transport vào cùng nguồn mà nó đang thu, một sự cố mạng có thể nhân log volume liên tục. Cần tách pipeline hoặc filter tags và rate-limit agent diagnostics.

## 19. Runbook điều tra khi log từ Java không xuất hiện

Khi ứng dụng có câu logger nhưng backend không có event:

1. **Kiểm tra Java:** logger level/filter có bật? Event được xuất ra stdout/file nào, encoding gì?
2. **Kiểm tra nguồn cục bộ:** file tồn tại, permission, symlink, rotation, stdout driver/journald có giữ dòng?
3. **Kiểm tra agent source:** path/tag/input plugin có khớp, state DB/cursor có đúng, agent có đang tail file mới?
4. **Kiểm tra parser:** JSON parse, multiline grouping, time parser, field limits; có record bị drop/quarantine?
5. **Kiểm tra queue:** backlog, disk fullness, memory limits, input pause, dropped records.
6. **Kiểm tra output:** DNS, TLS certificate, authentication, port, remote 429/5xx/throttle, retry rate.
7. **Kiểm tra collector:** receiver đang sống, route/index/schema đúng, filter nào loại record, backend có giới hạn quota?
8. **Kiểm tra search:** time range/timezone, service/env filter, retention, ingest delay, index alias.
9. **Đối soát:** kiểm tra số records ở input, spool, ACK và backend trong một time window đã xác định.
10. **Giải thích trạng thái:** ghi rõ stage cuối đã được chứng minh, còn thiếu bằng chứng ở đâu; không tự gọi "application không log" khi agent đọc sai path.

Tình huống thường gặp:

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm chứng |
| --- | --- | --- |
| Sau restart log cũ bị gửi lại | State DB mất/đổi volume hoặc read-from-head khác | So DB/cursor policy, event IDs |
| Log mới sau rotation biến mất | Agent theo tên file, không đọc inode cũ/file mới | Test rename/create và rotate wait |
| Dòng stack trace tách nhiều event | Multiline parser thiếu/sai | Kiểm tra raw source và parser output |
| Backend nhận trễ theo phút | Queue backlog hoặc remote throttle | Buffer/ACK/ingestion delay |
| Chỉ một service thiếu log | Permission, path/tag/config khác | So service stdout/file và agent inputs |
| Host đầy disk | Spool không giới hạn hoặc nguồn quay vòng lỗi | Disk watermark, queue policy |
| Log trùng gấp đôi | Thu stdout + file hoặc retry ACK lost | Source config, event IDs, transport |
| Có log ERROR nhưng không thấy requestId | MDC chưa set, encoder bỏ field, parse lỗi | Kiểm Java event và collector schema |
| TLS handshake liên tục lỗi | Trust chain/endpoint/protocol mismatch | Agent error counters và cert config |
| Agent healthy nhưng backend rỗng | Input path rỗng, route sai, output bị filter | Canary end-to-end, từng stage metrics |

## 20. Kiểm thử trước khi lên production

Một bộ test tối thiểu trong staging:

| Case | Điều cần chứng minh |
| --- | --- |
| Java service phát NDJSON hợp lệ | Agent parser nhận đúng một event, Unicode không hỏng |
| Stack trace nhiều dòng | Multiline grouping đúng hoặc JSON string escape đúng |
| Restart agent | Không mất nguồn chưa gửi; duplicate nằm trong semantics chấp nhận |
| Rename rotation | File cũ được đọc hết, file mới được theo dõi |
| Copytruncate | Hiểu và đánh giá rủi ro mất bytes, chọn policy phù hợp |
| Collector down 5–10 phút | Spool giữ trong quota, retry rồi drain sau recovery |
| Queue/disk gần đầy | Backpressure/pause/drop đúng policy và có cảnh báo |
| Backend ACK lost | Có thể duplicate; idempotency/dedup theo yêu cầu |
| File permission change | Agent báo lỗi rõ, không âm thầm bỏ nguồn |
| Container reschedule/node restart | Log persistence và source visibility đúng contract |
| Parser gặp payload CR/LF | Không tạo forged event hoặc phá multiline |
| Dữ liệu có token giả | Redaction policy chặn trước sink ngoài phạm vi |
| TLS certificate expired | Export từ chối kết nối không an toàn, có alert |
| Nhiều Java services cùng host | Tags/service/host metadata không lẫn |
| Agent log self-ingestion | Không nhân sự kiện vô hạn |
| Ứng dụng log burst | CPU/memory/spool nằm trong resource budget |

**Không tắt TLS verification hoặc đẩy dữ liệu nhạy cảm thật để kiểm thử.** Dùng canary events không chứa bí mật, môi trường được cấp quyền và endpoint test.

Để kiểm tra **end-to-end**, tạo event canary có eventId ổn định, timestamp và service rõ, sau đó xác minh backend nhận trong SLA. Một test chỉ nhìn agent process running **không chứng minh** collector đã lưu thành công.

## 21. Những lỗi cấu hình thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ log ra file nhưng agent đọc stdout | Không thu được nguồn mong muốn | Chuẩn hóa source path và runtime |
| Thu cả file lẫn stdout không chủ đích | Duplicate | Quyết định source of truth |
| Không có state DB/checkpoint | Restart đọc lại hoặc bỏ lịch sử | Persistent state, kiểm thử restore |
| Dùng copytruncate không đánh giá | Có nguy cơ mất bytes khi rotate | Ưu tiên rename/create phù hợp |
| Đọc stack trace từng dòng | Sai số event và mất correlation | NDJSON hoặc multiline parser |
| Retry vô hạn không có disk quota | Full disk, ảnh hưởng app | Buffer limits, alert, overflow policy |
| Đặt spool cạnh business data không giới hạn | Cascade disk-full failure | Tách dung lượng/quota và watermark |
| Cấu hình output không xác thực | Bị chặn kết nối hoặc rò dữ liệu | TLS/mTLS/auth phù hợp |
| Chỉ xem offset tail | Nhầm đọc nguồn với giao thành công | Đo buffer, ACK, backend ingestion |
| Dùng message text làm ID/dedup key | Dễ đếm thiếu/nhầm legitimate repeat | Stable eventId và semantics rõ |
| Regex chung để redact payload | Có thể bỏ sót secrets | Minimize ở Java source, field allowlist |
| Chạy agent bằng root không cần thiết | Mở rộng blast radius | Least privilege và file ACL |
| Không monitor agent log drops | Thiếu bằng chứng nhưng không ai biết | Metrics, canary và runbook |

## 22. Checklist áp dụng

| Hạng mục | Tiêu chí |
| --- | --- |
| Architecture | Rõ app/logger, host agent, gateway, backend |
| Sources | stdout/file/journal không trùng, agent đọc đúng path |
| Schema | JSON/text encoding, event time và metadata rõ |
| Cursor | State DB/offset/cursor persist, restart đã kiểm thử |
| Rotation | Rename/copytruncate, inode identity, archive retention |
| Multiline | Java Throwable/stack trace được framing đúng |
| Delivery | ACK/buffer/retry semantics được tài liệu hóa |
| Disk/queue | Có quota, backpressure/overflow policy và alert |
| TLS/auth | Verify certificate, bảo vệ credentials |
| Access control | Agent có quyền tối thiểu, spool không public |
| Privacy | Không phát raw token/PII; log forging được ngăn |
| Health | Queue, retries, parse/drop rate, agent restart được giám sát |
| Reliability | Đã thử outage/restart/rotation/ACK lost |
| Validation | Có canary end-to-end và đối soát nguồn–backend |
| Operations | Runbook truy ra điểm đứt và điều kiện khôi phục |

**Kết luận:** agent trên máy chủ là lớp **thu thập và vận chuyển** log giữa Java logging provider và backend. Để pipeline đáng tin, không chỉ cấu hình một đường tail file: cần hiểu **source framing, file identity/rotation, offset/cursor, filesystem buffer, ACK/retry, backpressure, TLS, privacy và khả năng quan sát chính agent**. Với kiến trúc có thể kiểm chứng, người vận hành biết log đang được tạo ở JVM, đang chờ trong agent hay đã tới backend—và biết khi nào chỉ có một giả định chứ chưa có bằng chứng.