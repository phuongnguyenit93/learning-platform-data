# Sidecar collector trong Java Logging — Thu thập và vận chuyển log cạnh ứng dụng

## 1. Khái niệm và vai trò

**Sidecar collector** là một tiến trình/container chạy **cùng đơn vị triển khai** với ứng dụng để đọc log hoặc telemetry, xử lý dữ liệu ở gần nguồn rồi chuyển tiếp tới một hệ thống thu thập tập trung. Trong Kubernetes, sidecar thường nằm **cùng Pod** với container ứng dụng, có thể dùng chung volume và network namespace, nhưng vẫn là một container với image, process, tài nguyên và cấu hình riêng.

Trong Java, Logback, Log4j 2, JUL hoặc thư viện logging khác quyết định **sự kiện được tạo, cấp độ, định dạng, nơi ghi**. Sidecar giải quyết một bước khác: **phát hiện nguồn, đọc, parse, thêm metadata, buffer, retry và ship** tới collector/gateway/storage.

```text
                      Một Kubernetes Pod
 +---------------------------------------------------------+
 |  Java application container                             |
 |    Service -> SLF4J/Logback -> /shared-logs/app.jsonl    |
 |                                  |                      |
 |              shared volume       |                      |
 |                                  v                      |
 |  Collector sidecar container                            |
 |    Tail/File input -> Parse -> Enrich -> Buffer -> Send  |
 +----------------------------------------------+----------+
                                                |
                                           Network + TLS
                                                |
                                     Log gateway / collector
                                                |
                                         Search / retention
```

Đây chỉ là một luồng điển hình. Một sidecar có thể nhận log qua **localhost TCP/HTTP hoặc OTLP** thay vì đọc file; việc đọc file là một lựa chọn, không phải định nghĩa bắt buộc. Những agent có thể được dùng theo mô hình sidecar gồm **Fluent Bit**, **Vector**, **OpenTelemetry Collector**, hoặc collector nội bộ.

**Sidecar không đồng nghĩa lưu trữ bền vững.** Một agent có thể đọc file thành công nhưng không gửi được dữ liệu; dữ liệu có thể nằm trong queue chưa được remote xác nhận. Trước khi đánh giá độ tin cậy, cần phân biệt từng chặng.

## 2. Phân biệt logger, collector và nơi lưu

| Tầng | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Application logging** | Tạo log event, level/filter, Throwable, MDC, encoding, output | JUL, Logback, Log4j 2 |
| **Sidecar collector** | Tail/receive, checkpoint, parse, enrich, batch, retry, chuyển tiếp | Fluent Bit tail input |
| **Gateway / centralized collector** | Nhận từ nhiều agent, route, xác thực, giới hạn tải | Gateway cho logs/OTLP |
| **Log storage** | Retention, indexing, truy vấn, phân quyền và cảnh báo | Hệ thống logging tập trung |

Một dòng `logger.info("...")` **không chứng minh** sidecar đã đọc; `tail` đã nhận **không chứng minh** remote đã lưu; output plugin trả kết quả cũng chưa chắc tương đương dữ liệu được lưu bền vững hay replicated. Hợp đồng delivery phải được xác định rõ theo từng sản phẩm và hệ đích.

Sự khác nhau giữa ba kiểu trạng thái:

```text
Java emitted ----> file closed/flushed
                  |
                  v
Sidecar consumed -> local buffer/checkpoint
                  |
                  v
Remote accepted -> persisted / acknowledged according to sink
```

Nếu tổ chức yêu cầu **audit log bắt buộc lưu**, chỉ dùng một hàng đợi trong RAM hoặc file trên volume ephemeral không đủ để khẳng định không mất log.

## 3. Khi nào nên chọn sidecar collector?

Có thể xem xét khi:

- Ứng dụng Java hiện tại ghi **file** và cần ship nhưng không muốn gắn SDK gửi log từ xa vào JVM.
- Mỗi service cần **parser hoặc routing đặc thù** mà node collector chung khó quản lý.
- Muốn áp dụng cấu hình thu thập riêng theo Pod/tenant, ví dụ thêm nhãn service, biến đổi format trước khi gửi.
- Cần nhận qua localhost receiver để tránh để Java app giao tiếp trực tiếp với backend lưu log.
- Một hệ thống legacy chưa có cấu trúc stdout logging phù hợp.
- Hạ tầng có yêu cầu quan sát và sửa lỗi sidecar **độc lập tương đối** với chu kỳ deploy code Java.

Tuy nhiên, sidecar tăng chi phí: mỗi Pod thêm container, CPU, RAM, filesystem I/O, cấu hình, security surface, image và vòng đời cần theo dõi. Với nhiều Pod, chi phí nhân lên tương ứng. Sidecar cũng chia sẻ **failure domain Pod**: đầy disk hoặc CPU starvation do sidecar có thể ảnh hưởng application.

### 3.1. So sánh với giải pháp khác

| Mô hình | Điểm mạnh | Đánh đổi |
| --- | --- | --- |
| **Java gửi trực tiếp** qua appender/OTLP | Có ngữ cảnh ứng dụng và trace ngay tại nguồn | Network, buffer và lỗi export có thể tác động JVM |
| **Sidecar per Pod** | Cấu hình riêng; có thể đọc local file, dùng localhost | Thêm tài nguyên và lifecycle trên mọi Pod |
| **DaemonSet per node** | Ít agent hơn nếu nhiều Pod trên node; thu thập stdout container | Agent cần quyền truy cập log node, chính sách đa ứng dụng |
| **Stdout/stderr + nền tảng** | Phù hợp hệ sinh thái Kubernetes, ít logic file riêng trong app | Phụ thuộc runtime/node collector và retention của nền tảng |
| **Gateway ở giữa** | Tập trung auth, routing, batching | Thêm hop, cần scale và HA |

Nếu Java app đã log ra console theo định dạng chuẩn và một DaemonSet đọc được container logs, **không nên tự động thêm sidecar** chỉ vì muốn thu thập log. Nên đo yêu cầu thật và chọn kiến trúc ít thành phần nhất vẫn đáp ứng được.

## 4. Sidecar có tự nhìn thấy stdout của container Java không?

**Không theo mặc định.** Mỗi container có stdout/stderr riêng. Việc nằm cùng Pod không khiến stdout của container ứng dụng tự trở thành file `/shared-logs/app.log` để sidecar đọc.

Các đường dữ liệu hợp lệ:

```text
[A] Java FileAppender -> shared volume -> sidecar tail

[B] Java OTLP/appender -> localhost receiver -> sidecar output

[C] Java stdout -> container runtime -> node collector (không cần sidecar)
```

Ở [A], phải mount **cùng volume** vào cả app và sidecar. Ở [B], cấu hình receiver, client retry/timeout và chính sách bảo mật ở localhost. Ở [C], file log runtime của node thường không được mount thẳng vào một sidecar trong Pod; tác nhân trên node/container logging pipeline phụ trách.

Không nên cấu hình vừa appender trực tiếp tới central collector, vừa sidecar tail cùng event, vừa node agent thu stdout của sidecar nếu không xác định rõ: một event có thể bị **thu thập nhiều lần**.

## 5. Hợp đồng dữ liệu giữa ứng dụng Java và sidecar

Nếu chọn shared-file, cần thống nhất:

| Thuộc tính | Cần xác định |
| --- | --- |
| **Path** | Java ghi path nào, sidecar đọc cùng volume/path nào |
| **Encoding** | UTF-8 hay encoding khác |
| **Framing** | Mỗi log event một dòng JSONL, hay multiline text |
| **Schema** | Timestamp, level, event code, service, traceId, errorCode |
| **Rotation** | Ai xoay file, naming pattern, tuổi thọ archive |
| **Retention** | File tồn tại bao lâu khi sidecar/network bị lag |
| **Checkpoint** | Offset DB ở đâu, còn sau sidecar restart/Pod replacement không |
| **Delivery** | Sự kiện nào được coi đã gửi/được nhận/lưu bền vững |
| **Security** | Giá trị nào bị redact; ai có thể đọc/ghi volume |
| **Resource budget** | RAM, CPU, local ephemeral storage và quota |

Một event JSONL (giá trị minh họa):

```json
{"timestamp":"2026-01-01T00:00:00Z","level":"INFO","event":"order.accepted","service":"orders-api","traceId":"a471ecbb7ef0473a8bf1dce250fd4d13","requestId":"req-01"}
```

**JSON Lines** có lợi vì từng dòng là một JSON object hoàn chỉnh. Với Throwable, stack trace nhiều dòng nên được encoder **escape trong một field JSON**; không để raw newline làm vỡ một record thành nhiều dòng. Nếu nguồn dùng text pattern, sidecar cần multiline parser có timeout/giới hạn kích thước phù hợp.

Trước khi ghi, phải loại password, API key, token, PII dư thừa. Collector có thể bổ sung/ẩn bớt fields nhưng **không thể thu hồi bí mật đã ghi ra file hoặc đã bị một tiến trình khác đọc**.

## 6. Java 17 độc lập: tạo JSONL để sidecar có thể tail

Ví dụ này sử dụng JDK 17, **không cần broker, Kubernetes, Logback hoặc dependency ngoài**. Nó ghi ba sự kiện JSONL vào một file. Để kết quả tái lập, dữ liệu là hằng số: đây **không phải JSON serializer cho input chưa tin cậy** và không phải backend logging production.

Lưu **`SidecarLogProducerDemo.java`**:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;

public class SidecarLogProducerDemo {
    private static void writeEvent(
            BufferedWriter out, String event, String correlationId)
            throws IOException {

        // Chỉ dùng dữ liệu hằng đã kiểm soát trong demo.
        String json = """
                {"timestamp":"2026-01-01T00:00:00Z","level":"INFO","event":"%s","correlationId":"%s"}
                """.formatted(event, correlationId).strip();

        out.write(json);
        out.newLine();
    }

    public static void main(String[] args) throws IOException {
        Path target = Path.of(
                args.length == 1 ? args[0] : "sidecar-demo.jsonl");

        // TRUNCATE chỉ giúp demo chạy lại cho kết quả xác định.
        try (BufferedWriter out = Files.newBufferedWriter(
                target, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE)) {
            writeEvent(out, "request_received", "req-01");
            writeEvent(out, "validation_passed", "req-01");
            writeEvent(out, "request_completed", "req-01");
        }

        List<String> lines =
                Files.readAllLines(target, StandardCharsets.UTF_8);

        if (lines.size() != 3) {
            throw new AssertionError("Expected exactly three events");
        }

        System.out.println("file=" + target.getFileName());
        System.out.println("eventsWritten=" + lines.size());
        System.out.println("latestEvent=" + lines.get(2));
    }
}
```

Biên dịch/chạy trong thư mục thử nghiệm có quyền ghi:

```bash
javac SidecarLogProducerDemo.java
java SidecarLogProducerDemo
```

**Stdout chính xác** khi chạy không có đối số:

```text
file=sidecar-demo.jsonl
eventsWritten=3
latestEvent={"timestamp":"2026-01-01T00:00:00Z","level":"INFO","event":"request_completed","correlationId":"req-01"}
```

File `sidecar-demo.jsonl` được tạo cùng thư mục, có **3 dòng JSONL**, thứ tự receive → validation → completed. Đọc file với `cat sidecar-demo.jsonl` (Linux/macOS), hoặc `Get-Content sidecar-demo.jsonl` (PowerShell).

Nếu có shared volume với path `/shared-logs` writable, có thể thử:

```bash
java SidecarLogProducerDemo /shared-logs/app.jsonl
```

Chương trình sẽ báo lỗi nếu thư mục không tồn tại hoặc không có quyền ghi. **Không chạy lệnh này lên file log thật**: ví dụ sử dụng `TRUNCATE_EXISTING`, cố ý xóa dữ liệu trước đó khi chạy lại. Ứng dụng thực tế phải dùng file append/rolling đúng lifecycle.

### 6.1. Điều gì được và chưa được kiểm chứng?

- `newBufferedWriter` ghi UTF-8; `try-with-resources` đóng writer.
- Mỗi event ghi một newline, thuận tiện cho tail theo dòng.
- Dùng Java text block và `String.formatted` yêu cầu Java 17+ tương thích.
- `String.formatted` **không escape JSON** cho dữ liệu tùy ý. Dùng serializer/encoder thực thụ với message, MDC và Throwable ở production.
- `Files.readAllLines` kiểm tra file được tạo; **không chứng minh** collector đã nhận hay đích đã lưu.
- Close/flush không mặc định tương đương `fsync`/durability trước mất điện.
- Đối với logging throughput cao, không nên tự thay toàn bộ backend bằng một `BufferedWriter` đơn giản thiếu rotation và error policy.

Nếu Java container chỉ ghi một lần rồi thoát, collector có thể chưa ship kịp. Ví dụ mô phỏng file contract, **không** đưa ra bảo đảm lifecycle hoặc delivery của Pod.

## 7. Java production: Logback ghi file cho sidecar

Ví dụ `logback.xml` cho ứng dụng dùng **SLF4J + Logback Classic**:

```xml
<configuration>
    <appender name="SIDE_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/shared-logs/app.jsonl</file>

        <rollingPolicy
          class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>/shared-logs/archive/app.%d{yyyy-MM-dd}.%i.jsonl.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>3</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
        </rollingPolicy>

        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="SIDE_FILE"/>
    </root>
</configuration>
```

Đây là **cấu hình tích hợp**, không thể chạy bằng JDK thuần. Cần Logback Classic, SLF4J và dependency **logstash-logback-encoder** tương thích; `LogstashEncoder` không phải class có sẵn trong Logback Core. Cần mount `/shared-logs` writable và xác minh thư mục archive được tạo/quản lý phù hợp.

Giải thích:

1. `app.jsonl` là **file active** để sidecar tail.
2. Rolling policy xoay theo size và date, archive theo pattern `%d` và `%i`.
3. `maxHistory=3` tương ứng **số kỳ lịch sử** theo pattern (ở đây thường là ngày), không phải luôn chỉ còn ba file.
4. `totalSizeCap` được áp dụng theo chính sách cleanup của backend; vẫn cần theo dõi dung lượng disk thật.
5. JSON encoder có thể serialize log event thành một JSON object mỗi dòng, bao gồm stack trace theo cấu hình. Hãy kiểm chứng với phiên bản encoder thực tế.
6. Sidecar đọc `app.jsonl` cần theo dõi đúng file identity/rename; nếu archive bị nén/xóa trước khi tail hết, log có thể thiếu.

Mảnh mã SLF4J:

```java
// Mã tích hợp trong một ứng dụng có SLF4J.
log.info("event=order.accepted orderId={}", safeOrderId);
```

`{}` chỉ format message, không tự biến đối số thành field JSON riêng, không redact secret và không bảo đảm log đã đến collector. Muốn structured fields, dùng API/encoder phù hợp với schema đã định.

**Không dùng external logrotate và RollingFileAppender cùng lúc trên cùng file** nếu không có thiết kế phối hợp cụ thể. Rename, reopen và copytruncate không đúng thời điểm có thể gây mất hoặc đọc trùng.

## 8. Kubernetes demo: shared volume và Fluent Bit sidecar

Một ví dụ độc lập minh họa **luồng file → sidecar** mà chưa cần build image Java:

- Container `application` dùng shell để giả lập Java app append một JSONL event mỗi vài giây.
- Container `collector` chạy **Fluent Bit**, tail file trên shared volume.
- Output **stdout của collector** giúp xem bản ghi; **chưa ship tới remote backend**.
- Volume `/state` giữ DB offset trong vòng đời Pod.

Lưu **`sidecar-log-demo.yaml`**:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sidecar-collector-config
data:
  fluent-bit.conf: |
    [SERVICE]
        Flush          1
        Daemon         Off
        Log_Level      info

    [INPUT]
        Name           tail
        Path           /shared-logs/app.jsonl
        Tag            java.app
        DB             /state/tail.db
        Read_from_Head On
        Rotate_Wait    30
        Mem_Buf_Limit  5MB
        Skip_Long_Lines On

    [OUTPUT]
        Name           stdout
        Match          java.*
---
apiVersion: v1
kind: Pod
metadata:
  name: sidecar-log-demo
spec:
  automountServiceAccountToken: false
  terminationGracePeriodSeconds: 30
  volumes:
    - name: shared-logs
      emptyDir: {}
    - name: collector-state
      emptyDir: {}
    - name: collector-config
      configMap:
        name: sidecar-collector-config
  containers:
    - name: application
      image: busybox:1.36
      command: ["/bin/sh", "-c"]
      args:
        - |
          n=0
          while true; do
            n=$((n + 1))
            printf '{"timestamp":"2026-01-01T00:00:00Z","level":"INFO","event":"tick","seq":%s}\n' "$n" >> /shared-logs/app.jsonl
            sleep 2
          done
      volumeMounts:
        - name: shared-logs
          mountPath: /shared-logs

    - name: collector
      image: cr.fluentbit.io/fluent/fluent-bit:3.2.10
      args: ["-c", "/fluent-bit/etc/fluent-bit.conf"]
      volumeMounts:
        - name: shared-logs
          mountPath: /shared-logs
          readOnly: true
        - name: collector-state
          mountPath: /state
        - name: collector-config
          mountPath: /fluent-bit/etc/fluent-bit.conf
          subPath: fluent-bit.conf
          readOnly: true
```

Đây là **manifest thử nghiệm**, không phải cấu hình production. Tag image là phiên bản minh họa: khi triển khai thật phải kiểm tra image/tag tồn tại, tương thích, được vá và **pin digest đáng tin cậy**. Không coi các version demo là bản mới nhất.

Nếu cluster test đã có `kubectl` và quyền trên namespace:

```bash
kubectl apply -f sidecar-log-demo.yaml
kubectl get pod sidecar-log-demo
kubectl logs pod/sidecar-log-demo -c collector
```

Dữ liệu `kubectl logs` phụ thuộc thời gian Pod khởi động, format output Fluent Bit và tốc độ ghi, nên **không có stdout cố định**. Dọn chính những tài nguyên demo:

```bash
kubectl delete -f sidecar-log-demo.yaml
```

Không chạy trên namespace production hoặc chia sẻ volume log thật.

### 8.1. Những điều cần quan sát từ manifest

- Writer và sidecar cùng mount volume `shared-logs`. Sidecar chỉ đọc log; state/checkpoint nằm trên volume khác.
- `Read_from_Head On` yêu cầu tail đọc từ đầu khi chưa có checkpoint phù hợp; không có nghĩa mỗi restart luôn đọc lại toàn bộ file.
- `DB /state/tail.db` giúp agent ghi checkpoint, nhưng **không phải cơ chế end-to-end ACK** và không bền xuyên Pod bị xóa.
- `Rotate_Wait 30` cung cấp khoảng theo dõi file sau rotation theo semantics plugin; không bảo đảm toàn bộ backlog được đọc khi file bị xóa quá nhanh.
- `Mem_Buf_Limit 5MB` giới hạn buffer của input; khi đầy có thể làm input pause và tăng lag.
- `Skip_Long_Lines On` có thể **bỏ qua dòng quá dài** theo cấu hình tail, cần cân nhắc nếu exception stack traces lớn hoặc audit bắt buộc lưu.
- `OUTPUT stdout` chỉ ghi ra stdout của sidecar. Nếu có một node collector khác đọc stdout đó, đường dữ liệu gồm **hai chặng** và có thể bị trùng nếu không kiểm soát.

Khi thay container shell bằng Java image thật, cho Logback hoặc Java process ghi vào `/shared-logs/app.jsonl`; cấu hình collector có thể giữ nguyên nếu định dạng tương thích.

### 8.2. K8s sidecar thường và native sidecar

Manifest trên đặt collector trong `spec.containers` như một container thông thường. Những phiên bản Kubernetes phù hợp cũng có mô hình **restartable init container** cho native sidecar, với điều kiện và thứ tự startup/shutdown khác.

**Không suy ra** Pod có hai containers là collector luôn khởi động trước app, hoặc luôn dừng sau app. Nếu cần collector ready trước khi ứng dụng phát log, cần áp dụng cơ chế ordering/probing tương ứng. Shared file còn tồn tại trong cùng Pod có thể giúp app ghi trước rồi sidecar đọc sau, nhưng nó không tạo một durable queue.

## 9. `emptyDir`, vòng đời Pod và độ bền checkpoint

Trong Kubernetes, **`emptyDir` sống cùng Pod**:

- Nếu **container** ứng dụng hoặc sidecar restart bên trong cùng Pod, volume thường còn.
- Nếu **Pod bị xóa/thay thế**, dữ liệu trên `emptyDir` không còn. Không dùng nó để hứa bảo toàn log qua Pod recreation.
- Nếu Pod bị evict vì cạn ephemeral storage hoặc node hỏng, dữ liệu có thể mất.
- Shared volume và checkpoint được mount read/write đúng quyền mới có tác dụng.
- Disk quota, inode, filesystem pressure, cleanup và log file growth có thể làm hỏng cả app lẫn sidecar.

Có thể dùng PVC hoặc filesystem buffering nếu kiến trúc cần hồi phục tốt hơn, nhưng PVC cũng cần thiết kế ownership, access modes, cleanup và phục hồi khi Pod đổi node. **Durable volume không tự tạo durable remote delivery**: còn cần protocol acknowledgment, retry, dedup và failover.

## 10. File tail, offset, inode và log rotation

Tail collector thường nhớ **file identity** và **vị trí đọc**:

```text
T0  app.jsonl         inode A, collector đã đọc tới offset 800
T1  app.jsonl -> app.1 (rename file A)
T2  app.jsonl mới    inode B, offset ban đầu = 0
T3  collector đọc nốt A nếu còn theo dõi, rồi B
T4  retention/archiver có thể nén/xóa A
```

Các nguy cơ:

1. Agent bị dừng đúng lúc rename/rotation.
2. File cũ bị nén hoặc xóa **trước khi sidecar đọc hết**.
3. Offset DB mất, agent bắt đầu lại từ đầu hoặc bỏ qua file, tùy cấu hình.
4. Inode bị tái sử dụng hoặc metadata không đủ để nhận diện file.
5. Writer dùng **copytruncate**: có cửa sổ mất dữ liệu giữa copy và truncate.
6. Một dòng log rất dài bị skip hoặc split.
7. Agent đang pause vì buffer đầy trong khi retention vẫn xóa file.

Đừng hiểu `Rotate_Wait` hoặc một checkpoint DB là bằng chứng “exactly once”. Khi retry sau timeout, log còn có thể bị gửi trùng ở phía đích.

### 10.1. Retention phải đủ cho thời gian backlog

Giả sử:

- `R`: tốc độ ghi log trung bình, bytes/giây.
- `T`: thời gian tối đa dự kiến collector/downstream không vận chuyển được.
- `M`: dung lượng dự phòng cho burst, file đang nén, overhead.

Một ước lượng sơ bộ:

```text
buffer_required_bytes ≈ R × T + M
```

Ví dụ: tốc độ **100 KiB/giây** trong **20 phút** tạo khoảng **117 MiB dữ liệu thô**, chưa tính dự phòng. Nếu shared volume chỉ đủ vài chục MiB hoặc retention xóa file sau vài phút, sidecar không thể thu lại các byte đã biến mất.

Đây là mô hình capacity đơn giản, **không phải guarantee**. Tốc độ tăng theo burst, compression ratio, disk write latency và cấu hình queue có thể thay đổi kết quả.

### 10.2. Tránh hai chủ thể rotation

Nếu Logback đã có `RollingFileAppender`, đừng đồng thời cho external `logrotate` thao tác trên cùng file trừ khi thiết kế đã kiểm chứng. Với **copytruncate**, record ghi giữa copy và truncate có thể bị mất. Với rename và process không reopen, writer có thể tiếp tục ghi vào inode cũ.

Cần test trên filesystem và OS thực tế; hành vi lock/rename giữa Windows, Linux và network mount khác nhau.

## 11. Buffer, retry và backpressure

```text
read -> parse -> local queue -> output plugin -> remote endpoint
           |        |               |
        invalid   full         429 / timeout / 503
           |        |               |
      reject/tag   pause         retry/backoff
```

Khi downstream tạm mất kết nối, sidecar có thể retry hoặc spool xuống disk nếu agent/config hỗ trợ. Nhưng nếu buffer đầy:

- **Input pause:** file backlog tăng; rotation/retention có thể xóa log chưa đọc.
- **Drop policy:** một phần event bị bỏ.
- **Filesystem buffering:** giảm rủi ro RAM overflow nhưng disk vẫn hữu hạn.
- **Blocking writer:** với một số tích hợp qua network hoặc file I/O đầy disk, latency của Java app có thể tăng.
- **Restart/Pod loss:** buffer trên `emptyDir` có thể biến mất.

Phải phân biệt bốn trạng thái: **đã đọc file → đã enqueue local → đã gửi request → remote đã xác nhận/persist**. Tên metric và log event không nên đánh đồng các mốc đó.

Nếu audit yêu cầu không mất dữ liệu, một sidecar best-effort + file ephemeral là **không đủ**. Cần thiết kế bền vững tại nguồn hoặc outbox/gateway đáng tin, xác nhận và đối soát theo business contract.

### 11.1. Hai loại nghẽn độc lập

**JVM logging backend:** Console/FileAppender có thể ghi chậm hoặc lỗi vì disk. AsyncAppender có thể block/drop khi queue đầy.

**Collector sidecar:** input tail có thể pause vì buffer hoặc output không tiến triển; file trên volume tăng, cuối cùng chạm quota.

Chuyển network transport ra sidecar giúp giảm một số công việc trong JVM, nhưng **không loại bỏ áp lực shared disk và CPU/memory Pod**.

## 12. Bảo mật và quyền riêng tư

Một collector là tiến trình có khả năng đọc dữ liệu ứng dụng, thường có network egress. Cần coi nó là một thành phần bảo mật thực sự:

1. **Least privilege:** app chỉ có quyền ghi nơi cần; collector mount log read-only và state riêng.
2. **Service account token:** nếu không cần Kubernetes API, không tự mount token; manifest demo dùng `automountServiceAccountToken: false`.
3. **Pod security:** chạy non-root khi image/permissions cho phép; read-only root filesystem, seccomp và giới hạn capabilities theo chính sách.
4. **Credentials:** không hardcode token vào `logback.xml`, ConfigMap hoặc log; dùng secret/identity thích hợp cho output remote.
5. **Transport:** TLS và certificate validation cho đường gửi tới remote, authentication/authorization của log gateway.
6. **Egress:** giới hạn network destination cần thiết; sidecar không nên được mặc định truy cập mọi endpoint.
7. **Redaction tại nguồn:** loại password, API key, JWT, session cookie, PII không cần thiết trước khi ghi file.
8. **Log injection:** dữ liệu user-controlled có newline/control characters; dùng JSON serializer/encoder an toàn, giới hạn size.
9. **Retention:** cả file local, spool, gateway và storage trung tâm đều cần retention và quyền đọc phù hợp.
10. **Supply chain:** quản lý versions/digests, quét image collector, theo dõi cập nhật plugin.

Sidecar cùng Pod và dùng shared volume **không phải ranh giới chống sửa xóa log tuyệt đối**. Nếu kẻ tấn công chiếm quyền ghi file ứng dụng, họ có thể chỉnh dữ liệu trước khi sidecar đọc. Với audit nhạy cảm, cần kênh lưu và integrity controls độc lập.

## 13. Enrichment, MDC và trace context

Một application event có thể chứa:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "level": "ERROR",
  "logger": "com.example.OrderService",
  "event": "order.failed",
  "errorCode": "STORAGE_UNAVAILABLE",
  "traceId": "1ad2c3ba78544956bacccf011c467f20",
  "requestId": "req-01"
}
```

Sidecar có thể bổ sung `service.name`, `deployment.environment`, Pod/namespace/container/node/cluster từ nguồn metadata hợp lệ. Không cần chèn mọi Kubernetes label: các nhãn có cardinality cao và dữ liệu nhạy cảm tạo chi phí/risks.

- **Application context** như `requestId`, `errorCode`, `operationId` nên được Java app xác định.
- **Deployment context** như namespace, Pod, container nên lấy từ orchestrator hoặc agent metadata.
- **Untrusted context** như HTTP User-Agent, client-supplied IDs và message payload cần validate, sanitize và giới hạn.

MDC của SLF4J hoặc `ThreadContext` của Log4j 2 giúp đưa trace/request context vào log. Trong executor/async callbacks, context **không tự lan qua mọi thread**; cần propagate và clear/restore đúng. Sidecar không thể tạo lại trace context đã bị bỏ quên trong JVM.

Raw `traceId`, `requestId`, user ID hoặc message không nên dùng làm metric label; hãy dùng nhóm/nhãn hữu hạn.

## 14. Multiline Throwable và JSONL parsing

Java stack trace thường nhiều dòng:

```text
ERROR OrderService - request failed
java.lang.IllegalStateException: unable to process
    at com.example.OrderService.process(...)
Caused by: java.io.IOException: connection refused
```

Đó là **text minh họa**, không phải stdout chương trình.

Với line-oriented tail:

- Nếu backend in multiline text, sidecar cần multiline parser để ghép các dòng thành một event; có timeout, regex bắt đầu và memory limit.
- Nếu backend ghi JSONL, stack trace phải được **escape thành string JSON** trong một event; kiểm tra encoder thực tế.
- Nếu line quá dài, plugin có thể skip/drop theo cấu hình; bật `Skip_Long_Lines` không phải giải pháp lossless.
- Nếu appender chia record không đúng, collector có thể parse lỗi hoặc đếm một exception thành nhiều event.
- Nếu exception chứa secret, JSON encoder không tự quyết định phải redact những fields nào.

Nên thử với cause chain, suppressed exceptions, nested JSON và một exception rất dài. Kiểm tra dữ liệu **cuối tại sink**, không chỉ JSON hợp lệ trong file Java.

## 15. Startup, restart và graceful shutdown

### 15.1. Startup

Ứng dụng có thể ghi trước khi collector sẵn sàng. Nếu có shared file và retention đủ, collector có thể đọc sau từ đầu khi file xuất hiện; nhưng `Read_from_Head`, file discovery và checkpoint phải được cấu hình/test thực tế.

Nếu app đẩy log tới sidecar receiver qua localhost, một lỗi kết nối ở startup có thể làm mất event hoặc chặn request tùy SDK/appender. Cần retry, giới hạn timeout và readiness policy phù hợp.

Manifest ở mục 8 dùng **container thường**, không khẳng định thứ tự khởi động. Với Kubernetes native sidecar dạng restartable init container ở phiên bản phù hợp, startup/shutdown semantics có khác; cần hiểu đúng loại container đang dùng.

### 15.2. Restart

- Restart **sidecar container** trong cùng Pod: `emptyDir` thường vẫn giữ file và checkpoint.
- Restart **Java container** trong cùng Pod: file vẫn còn, nhưng appender có thể append/rotate/recreate tùy config.
- **Pod bị xóa/replace**: `emptyDir` và DB offset có thể mất; log chưa ship có thể biến mất.
- Restart sau outage có thể tạo log trùng do remote đã nhận batch nhưng local agent chưa kịp ghi nhận trạng thái.

### 15.3. Shutdown

Ứng dụng nên ngừng nhận công việc mới, flush/close logger theo contract. Collector cần cơ hội tail và gửi backlog trong grace period. Với sidecar là container thường, **không mặc định collector luôn là container cuối dừng**; với native sidecar các quy tắc lifecycle phụ thuộc phiên bản và cấu hình.

Một `sleep` cố định trong Java không chứng minh collector đã gửi xong. Nếu yêu cầu delivery nghiêm ngặt, phải dùng receipt/ack thật và durable storage; nếu best-effort, nêu rõ cửa sổ mất dữ liệu chấp nhận được.

### 15.4. Health và availability

Collector lỗi chưa chắc khiến Java app chết. Có nên làm Pod NotReady vì collector không sẵn sàng? Tùy chính sách:

- Diagnostic logs best-effort: có thể cho app tiếp tục, đồng thời cảnh báo.
- Security/audit logs bắt buộc: có thể yêu cầu fail-closed hoặc giới hạn thao tác nhạy cảm.
- Readiness gắn với sidecar có thể ảnh hưởng availability của cả service.

**Collector process chạy** không đồng nghĩa **remote sink đang ghi thành công**. Health cần phản ánh điều kiện mục tiêu, không chỉ PID.

## 16. Monitoring và cảnh báo

Các nhóm metric nên xem xét (tên dưới **chỉ là gợi ý**, không phải metric mặc định của mọi agent):

| Metric/tín hiệu | Ý nghĩa |
| --- | --- |
| `logs_produced_total` | Số sự kiện JVM phát theo instrumentation |
| `collector_records_read_total` | Số record sidecar đọc |
| `collector_records_sent_total` | Số gửi thành công theo semantics output |
| `collector_output_retries_total` | Số lần retry output |
| `collector_output_errors_total` | Lỗi output |
| `collector_buffer_bytes` | Buffer memory/disk |
| `collector_tail_lag_bytes` | File backlog chưa đọc |
| `collector_dropped_records_total` | Số event bị bỏ/skip |
| `collector_invalid_records_total` | Parse hoặc framing lỗi |
| `log_ingestion_lag_seconds` | Thời gian từ event tới sink |
| `sidecar_restarts_total` | Sidecar restart nhiều lần |
| Disk/inode/ephemeral storage usage | Khả năng volume bị đầy |

Alert quan trọng gồm collector không gửi log trong khi app vẫn ghi, retry tăng, buffer/spool gần đầy, log lag tăng, parse errors, event quá dài bị skip, sidecar bị OOMKilled, file rotation quá nhanh hoặc dữ liệu audit đối soát thiếu.

**Không chỉ log cảnh báo vào chính pipeline đang lỗi.** Metrics/health cần đường quan sát độc lập đủ mức để phát hiện sự cố ingest.

## 17. Kiểm thử end-to-end

Một chiến lược có thể tái lập:

1. Tạo một namespace/Pod và volume **riêng cho test**.
2. Java producer tạo `N` event JSONL với `eventId` duy nhất và những trường an toàn.
3. Quan sát file thực tế và sidecar tail/checkpoint.
4. Chờ output được xác nhận theo đúng backend, không chỉ thấy dòng trong stdout.
5. Truy vấn sink sau ingest rồi so sánh **tập ID**, số bản ghi thiếu, trùng và thứ tự theo contract.
6. Giả lập sink chậm hoặc trả 429/503; đo buffer, retry, lag và khả năng phục hồi.
7. Restart riêng sidecar container, rồi riêng Java container.
8. Xoay file bằng backend thật, bao gồm rename, compression và retention.
9. Thử pod replacement để xác định giới hạn `emptyDir`.
10. Đánh giá cả p95/p99 latency ứng dụng, CPU/RAM và disk khi collector bị nghẽn.

| Kịch bản | Kỳ vọng kiểm chứng |
| --- | --- |
| File chưa tồn tại lúc collector start | Agent phát hiện file khi được tạo |
| Writer ghi liên tục | Event được tail, không phá JSON |
| Sidecar start muộn | Đọc đúng theo checkpoint/read-from-head policy |
| Sidecar restart | Offset/spool còn đúng mức; không missing ngoài policy |
| Pod bị xóa | Hiểu rõ dữ liệu `emptyDir` mất |
| Logback rollover | Agent theo dõi file active và file cũ theo thiết kế |
| Rotate + nén/xóa | Không mất log chưa ship trong cửa sổ retention dự kiến |
| Copytruncate | Đánh giá được race mất/trùng |
| Mất network | Có retry/backoff và cảnh báo |
| Buffer đầy | Hành vi pause/drop được đo |
| Dòng JSON lớn | Bị parse/skip theo policy, không im lặng mất dữ liệu quan trọng |
| Throwable multiline | Log event không bị chia sai |
| Header/metadata độc hại | Không log injection, không lộ secret |
| Hai nguồn cùng ghi | Không nhầm service/container source |
| Output timeout rồi retry | Biết cách nhận diện duplicate ở sink |
| Collector OOM/restart | Có metric và recovery path |
| Graceful/forced shutdown | Đánh giá số pending events còn lại |

Với audit bắt buộc lưu, cần kiểm thử receipt/transaction/durable buffer riêng. **File tail + emptyDir + retry thường chỉ tạo một pipeline best-effort hoặc các mức bảo đảm có điều kiện**, không phải exactly-once xuyên Pod crash.

## 18. Quy trình xử lý sự cố sidecar không có log

Khi application vẫn xử lý request nhưng không thấy log tập trung, kiểm tra lần lượt:

1. **Nguồn:** logger level/filter, Logback appender, encoder và path thực sự của JVM.
2. **File:** file có được tạo trên đúng shared volume? Quyền app ghi và sidecar đọc có đúng?
3. **Framing:** JSONL hợp lệ, đúng newline/UTF-8? Có lines quá dài hoặc multiline?
4. **Sidecar input:** Path/Tag/DB file discovery, có bị pause hoặc checkpoint ở offset sai?
5. **Buffer:** queue/memory/disk storage có đầy, plugin có skip/drop?
6. **Output:** endpoint, TLS, authentication, network policy, HTTP 429/503, timeout/retry.
7. **Sink:** routing/index, timestamps, retention, query filter và quyền tìm kiếm.
8. **Rotation:** archive có bị nén/xóa trước khi agent theo kịp, path/inode bị đổi?
9. **Lifecycle:** Pod vừa replace, `emptyDir` hoặc offset DB đã mất?
10. **So sánh ID:** producer tạo bao nhiêu, sidecar đọc bao nhiêu, remote nhận bao nhiêu?

Nếu sink nhận trùng, kiểm tra retry sau timeout, hai tuyến ingest song song, checkpoint mất hoặc nhiều collectors cùng đọc file. Nếu thiếu dữ liệu, kiểm tra drop/skip, rotation, filesystem quota và Pod replacement.

## 19. Những hiểu lầm cần tránh

### “Sidecar tự động thấy stdout của Java”

Sai. Cần shared file, localhost receiver hoặc cơ chế runtime/node collector. Cùng Pod không đủ.

### “Có sidecar là application log không thể mất”

Sai. Backend có thể filter, AsyncAppender có thể drop, file có thể bị xóa, agent có thể pause và Pod có thể mất dữ liệu ephemeral.

### “Offset DB là xác nhận remote đã lưu”

Sai. Offset đọc file và acknowledgment của hệ đích là hai mốc khác nhau.

### “`emptyDir` tồn tại mãi qua mọi restart”

Sai với Pod deletion/replacement. Volume không phải durable record store xuyên vòng đời Pod.

### “Sidecar luôn tiết kiệm hơn DaemonSet”

Không mặc định. Sidecar per Pod có thêm tài nguyên cho từng Pod; DaemonSet dùng chung agent theo node.

### “`Read_from_Head On` làm mỗi restart đọc lại tất cả”

Không đúng khi checkpoint DB còn hợp lệ. Cần hiểu hành vi file state cụ thể.

### “JSON encoder tự xử lý mọi bảo mật”

Không. Serializer escape cú pháp JSON nhưng **secret/PII trong field vẫn bị lưu** nếu ứng dụng gửi vào.

### “File rollover xong là log chắc chắn đã ship đủ”

Không. Collector có thể lag; archive có thể nén/xóa trước khi đọc xong.

### “Collector stdout là đã gửi tới storage”

Không. Đây là output demo; còn cần node agent hoặc remote output để đưa tới hệ tập trung.

### “Tăng bộ đệm không giới hạn là đáng tin hơn”

Không. Bộ đệm quá lớn có thể làm đầy RAM/disk và ảnh hưởng app; phải có capacity, retention, backpressure và alert.

## 20. Checklist triển khai

- [ ] Xác định lý do cần sidecar thay vì stdout + node/DaemonSet collector.
- [ ] Chọn rõ dữ liệu đi qua shared volume, localhost receiver hay OTLP.
- [ ] Thống nhất format JSONL/UTF-8, schema, event ID, trace context và redaction.
- [ ] Cấp quyền read-only cho collector đối với nguồn khi có thể, state riêng writable.
- [ ] Không giả định sidecar đọc được stdout container khác tự động.
- [ ] Kiểm tra offset DB, rename/inode, `Read_from_Head`, rotation và retention.
- [ ] Đánh giá `emptyDir` lifecycle, disk quota, PVC nếu cần, buffer và retry budget.
- [ ] Chỉ tuyên bố delivery guarantee tại ranh giới có bằng chứng xác nhận thật.
- [ ] Thiết kế JSON encoder cho Throwable và test long lines/multiline.
- [ ] Theo dõi parse/drop/retry/lag, queue và ephemeral storage.
- [ ] Bảo vệ transport với TLS/auth, giảm Kubernetes permissions và kiểm soát secrets.
- [ ] Kiểm thử network outage, collector restart, Pod replacement, rollover và shutdown.
- [ ] Tránh log trùng do đồng thời dùng appender remote, sidecar và node agent.
- [ ] Đảm bảo collector health có kênh quan sát độc lập khi đường log lỗi.
- [ ] Đối với audit bắt buộc, bổ sung durable capture/ack/integrity, không chỉ file ephemeral.

**Kết luận:** **Sidecar collector** giúp ứng dụng Java **tách việc tạo log khỏi việc thu thập và vận chuyển**, đồng thời áp dụng pipeline riêng cho mỗi workload. Nhưng cần vận hành như một hệ thống hoàn chỉnh: **logger/encoder → nguồn file hoặc receiver → offset/rotation → buffer/retry → remote acknowledgment → lưu trữ**. Sidecar chỉ là một mắt xích; độ tin cậy phải được kiểm thử ở từng ranh giới và khi xảy ra lỗi thật.
