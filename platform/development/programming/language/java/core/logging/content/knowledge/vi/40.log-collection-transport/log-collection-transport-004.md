# Container stdout: thu thập và vận chuyển log của ứng dụng Java

## 1. Tổng quan: “log ra stdout của container” nghĩa là gì?

Khi triển khai ứng dụng Java trong Docker, Kubernetes hoặc một nền tảng container tương tự, **stdout** (standard output, file descriptor 1) và **stderr** (standard error, file descriptor 2) của tiến trình ứng dụng thường là hai luồng mà nền tảng container có thể thu thập. Thay vì yêu cầu ứng dụng tự tạo và quản lý file `/var/log/myapp.log` bên trong container, một cách thiết kế phổ biến là:

1. Ứng dụng dùng **logging framework** như Logback, Log4j 2 hoặc JUL để tạo log event có cấu trúc.
2. Appender/handler ghi log đã định dạng vào **stdout** (hoặc stderr theo chính sách).
3. Container runtime ghi nhận các byte/dòng từ hai luồng; tầng hạ tầng quản lý log files hoặc logging driver.
4. Log collector/agent đọc hoặc nhận những bản ghi này, bổ sung metadata container/pod rồi chuyển đến backend lưu trữ, tìm kiếm, cảnh báo.
5. Người vận hành truy vấn bằng `docker logs`, `kubectl logs` hoặc hệ thống log tập trung tùy giai đoạn và khả năng lưu giữ.

**Container stdout** không phải là một sản phẩm broker, database hay giải pháp observability hoàn chỉnh. Nó chỉ là **điểm giao** giữa process Java và cơ chế thu gom log của runtime/orchestrator. Việc gọi `logger.info(...)` và ghi tới stdout **không bảo đảm** record cuối cùng đã được index ở hệ thống tập trung.

### Mục tiêu bài học

Sau bài này bạn có thể:
- Hiểu stdout/stderr và sự khác nhau giữa `System.out.println`, `System.err.println` và ConsoleAppender/Handler.
- Mô tả luồng **Java logger → stdout/stderr → runtime → kubelet/driver → collector → log backend**.
- Cấu hình Java logging để phát sự kiện ra console mà tránh ghi trùng qua nhiều appender.
- Dùng lệnh Docker và Kubernetes để xem log, biết giới hạn về vòng đời container và rotation.
- Thiết kế định dạng **one-event-per-line**, JSON có structured fields, timestamp, severity và correlation ID.
- Nhận biết rủi ro **multiline exception**, dropped logs, blocking/backpressure, restart, container rotation và duplicate ingestion.
- Kiểm thử readback end-to-end và bảo vệ secret/PII trong log.

## 2. Ba khái niệm cần phân biệt

| Khái niệm | Là gì? | Trách nhiệm chính |
| --- | --- | --- |
| **Logging API/framework** | SLF4J + Logback, Log4j 2, `java.util.logging` | Tạo sự kiện, level, message, throwable, MDC, format/routing |
| **stdout/stderr** | Hai luồng byte tiêu chuẩn của tiến trình, thường gắn với file descriptor 1/2 | Xuất dữ liệu từ process; không có query, indexing, retention riêng |
| **Container logging infrastructure** | Docker logging driver, Kubernetes CRI/kubelet, node agent/collector, backend | Capture, gắn metadata, lưu/rotate, chuyển tiếp, truy vấn theo kiến trúc |

**`System.out.println` không phải logging framework.** Nó có thể in một dòng được runtime thu thập, nhưng thiếu level, schema, cấu hình, MDC và quản trị theo logger name. Trong ứng dụng thật, nên dùng logger với ConsoleAppender/Handler có thiết kế phù hợp.

**`stderr` không có nghĩa “chắc chắn đã alert”** và cũng không tự chuyển thành alert severity. Nó là một stream khác. Một số nền tảng/collector gắn nhãn `stream=stderr`, nhưng quy tắc alert nên dựa trên level, error code, metric/SLI và tác động thực tế, không mặc định mọi byte trên stderr là sự cố nghiêm trọng.

**“Đã ghi ra stdout” khác “đã lưu ở backend”.** Giữa hai mốc có thể có buffering, rotation, network outage, agent retry, policy drop và các điểm crash.

## 3. Kiến trúc thu gom điển hình

```text
                    Java application (container)
                    +----------------------------+
Business code ---->|  SLF4J / Log4j 2 / JUL     |
                    |     |                      |
                    |  encoder / appender        |
                    |     |                      |
                    +-----+----------------------+
                          |
                       stdout (fd 1)
                       stderr (fd 2)
                          |
                          v
               Container runtime / CRI
                          |
                  node log files/driver
                          |
                     Log collector
                 (node agent/forwarder)
                          |
                   network transport
                          |
                      Log backend
               parse / index / retention
                          |
                     search / alert
```

Mỗi lớp có một nhiệm vụ:
- **Application:** chọn field an toàn, quyết định level, thêm correlation ID/trace ID, format theo schema.
- **Runtime:** kết nối luồng stdout/stderr của container và triển khai logging driver hoặc ghi file theo đặc tả tương ứng.
- **Node/collector:** nhận/đọc bản ghi, nhận biết nguồn pod/container, xử lý dòng và multiline, giữ checkpoint, retry và batch.
- **Transport:** gửi qua mạng có xác thực/mã hóa, giới hạn backlog và quản lý lỗi.
- **Backend:** parse, index, retention, phân quyền và cung cấp truy vấn/alert.

Có thể bỏ qua một vài tầng hoặc chọn dịch vụ managed khác, nhưng **phải biết tầng nào sở hữu bộ đệm, retry, dung lượng và bằng chứng đã nhận**. Log dùng cho audit bắt buộc có thể cần một cơ chế bền vững riêng, bởi stdout thường là luồng chẩn đoán mang tính best-effort theo pipeline thực tế.

### 3.1. Tại sao ưa chuộng console logging trong container?

Các lợi ích thường có:
- **Không cần quản trị file log trong image/container:** giảm khó khăn về đường dẫn, quyền ghi và cleanup cục bộ.
- **Tương thích công cụ chuẩn:** `docker logs`, `kubectl logs` và collector của nền tảng có thể xem output.
- **Tách trách nhiệm:** ứng dụng chỉ phát event, hạ tầng quyết định nơi lưu, index, rotation và retention.
- **Hỗ trợ scale-out:** mỗi replica ghi ra console; collector bổ sung pod/container metadata.
- **Triển khai nhất quán:** cấu hình log có thể theo môi trường mà không mount thư mục log riêng.
- **Thuận tiện kiểm thử:** một Docker container demo có thể được quan sát ngay qua lệnh logs.

Nhưng stdout không loại bỏ mọi quyết định: ghi đồng bộ có thể **block**, log volume quá lớn có thể gây áp lực tài nguyên, collector có thể drop, node disk vẫn có thể đầy, và việc truy vết sau khi pod bị xóa phụ thuộc hệ thống lưu tập trung.

### 3.2. Khi nào file log vẫn có thể cần?

Một số hệ thống hoặc thư viện cũ yêu cầu file, hoặc audit log cần sink bền vững/append-only riêng. Khi đó cần quản lý:
- Volume/persistence và quyền truy cập.
- Rotation, retention, locking, disk quota và chính sách crash.
- Agent đọc file với offset/checkpoint, xử lý inode/rename/truncate.
- Tránh ghi **cùng một event** vào stdout và file rồi cho collector thu cả hai nguồn khiến log bị nhân đôi.
- Thiết kế tính toàn vẹn nếu là audit bắt buộc; đừng coi log file mặc định là kho giao dịch.

File logging có thể là lựa chọn có chủ đích, nhưng **đừng ghi file trong container chỉ vì thói quen từ máy chủ truyền thống**.

## 4. stdout và stderr của tiến trình Java

Trong Java:
- `System.out` là `PrintStream` chuẩn cho stdout.
- `System.err` là `PrintStream` chuẩn cho stderr.
- Logging framework dùng **handler/appender** được cấu hình; level `ERROR` không tự bắt buộc đi stderr.
- Output có thể có buffering và encoding; cách flush/close phải phù hợp lifecycle.

Ví dụ nhỏ:

```java
// Mảnh minh họa: output thực tế ở hai stream riêng.
System.out.println("service startup complete");
System.err.println("diagnostic: startup validation warning");
```

Khi chạy trực tiếp trong terminal, hai luồng có thể hiển thị cạnh nhau. Khi container runtime thu thập, chúng có thể được lưu dưới các trường `stream=stdout` và `stream=stderr`. **Thứ tự tương đối giữa hai stream không nhất thiết phản ánh chính xác thứ tự theo chương trình**, bởi bộ đệm và cơ chế thu gom riêng. Đừng xây dựng invariant nghiệp vụ dựa vào thứ tự ghép stdout/stderr.

### 4.1. JUL mặc định khác Logback

`java.util.logging.ConsoleHandler` của JDK mặc định xuất tới **`System.err`**, không phải stdout. Vì vậy, chạy một ứng dụng chỉ cấu hình JUL ConsoleHandler không có nghĩa event đi vào stdout, dù `docker logs` vẫn có thể hiển thị cả stdout và stderr.

Với Logback `ConsoleAppender`, có thể chọn `System.out` hoặc `System.err`; Log4j 2 Console appender cũng cho chọn target. Cần xem cấu hình hiện hành thay vì suy từ tên “Console”.

**Không chuyển tất cả lỗi sang stderr chỉ để “đúng truyền thống”** nếu pipeline production chỉ thu stdout. Tốt nhất là thống nhất chính sách thu cả hai stream hoặc định tuyến có chủ đích, rồi dùng trường `level`/`severity` trong record để phân loại.

### 4.2. Đặc tính đồng bộ và hiệu năng

Ngay cả khi logger gọi một appender rất đơn giản, ghi xuống stdout có thể chờ do pipe buffer đầy hoặc tầng đọc phía sau chậm; chi tiết tùy OS, container runtime, logging driver, buffering và cấu hình. Hậu quả tiềm năng:
- Business thread tăng latency khi sync appender chờ.
- Backend/collector chậm gây queue/buffer tăng.
- CPU/GC tăng khi format stack trace lớn hoặc JSON event phức tạp.
- Disk/node storage chịu áp lực bởi log volume.
- Nếu dùng async appender, queue đầy có thể gây **drop hoặc block** theo chính sách của backend; không tự giả định async đồng nghĩa không mất log.

**Mục tiêu là bounded behavior:** giới hạn kích thước event, tránh dump payload, đo queue depth, dropped events, stdout write latency và biết policy khi log sink lỗi.

## 5. Java 17 chạy độc lập: ghi JUL trực tiếp ra stdout

Ví dụ sau dùng **JDK 17**, không cần Maven hay thư viện ngoài. JUL tạo log record và một custom `Handler` chuyển event ra `System.out` **theo từng dòng**, thay vì dùng `ConsoleHandler` mặc định vốn ghi stderr.

Tạo file `ContainerStdoutDemo.java`:

```java
import java.io.PrintStream;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ContainerStdoutDemo {
    private static final class StdoutLineHandler extends Handler {
        private final PrintStream out;

        StdoutLineHandler(PrintStream out) {
            this.out = out;
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            out.println(record.getLevel().getName()
                    + " " + record.getMessage());
        }

        @Override
        public void flush() {
            out.flush();
        }

        @Override
        public void close() {
            flush(); // Không đóng System.out của JVM.
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.container.stdout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler handler = new StdoutLineHandler(System.out);
        logger.addHandler(handler);

        try {
            logger.info("event=service_started service=orders");
            logger.info("event=request_completed service=orders"
                    + " route=/orders status=201 requestId=req-42");
            logger.warning("event=dependency_retry service=orders"
                    + " dependency=inventory attempt=1");
        } finally {
            logger.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ContainerStdoutDemo.java
java ContainerStdoutDemo
```

**Stdout chính xác** trong một JVM mới khi không có code khác can thiệp vào logger:

```text
INFO event=service_started service=orders
INFO event=request_completed service=orders route=/orders status=201 requestId=req-42
WARNING event=dependency_retry service=orders dependency=inventory attempt=1
```

**Stderr của ví dụ:** không có output do code này chủ động tạo.

### 5.1. Vì sao ví dụ hoạt động?

1. `Logger` của JUL tạo ba record có level INFO/INFO/WARNING.
2. `StdoutLineHandler` ghi mỗi record bằng một lời gọi `println`, có ký tự kết thúc dòng, để runtime có thể xử lý các bản ghi text theo dòng.
3. `logger.setUseParentHandlers(false)` ngăn log propagate tới parent/root handler, tránh thêm một bản ghi khác trên stderr qua JUL ConsoleHandler.
4. `handler.setLevel(Level.ALL)` cho phép handler nhận cả record khi logger đang ở level phù hợp.
5. `close()` chỉ flush, **không đóng `System.out`**. Đóng stdout toàn process có thể ảnh hưởng những component khác.
6. Các thông điệp là giá trị cố định, không chứa password, raw request body hay dữ liệu do client tự khai. `requestId=req-42` chỉ là ID giả minh họa.

### 5.2. Giới hạn của demo

- Handler tự viết chỉ để học, **không phải logger production**: không có structured JSON encoder, kiểm soát concurrency nâng cao, retry, queue hay health metrics.
- Một lần `println` cho một record **không tự bảo đảm tính atomic đối với mọi kích thước record và mọi sink**. Đừng dựa vào đó cho message rất lớn hoặc nhiều process cùng ghi.
- Demo không thêm timestamp nên stdout tất định; trong thực tế cần timestamp/correlation metadata được cấu hình đúng và phân biệt event time với ingest time.
- Runtime của Docker/Kubernetes **không chạy trong đoạn Java trên**; chỉ khi chạy chương trình như tiến trình container thì stdout mới được runtime/container logging tiếp nhận.
- Việc `logger.info` chạy xong không chứng minh log đã có mặt trong backend tập trung.

Có thể chạy demo này trong image có JDK phù hợp rồi dùng `docker logs` để quan sát; nội dung **file Java vẫn giống**, còn build image thuộc bước đóng gói/triển khai riêng.

## 6. Cấu hình Logback để ghi stdout

Nhiều ứng dụng Java dùng **SLF4J + Logback**. Với Logback Classic/Core đã có trong classpath, một `logback.xml` minh họa có thể là:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
                service=orders logger=%logger{36}
                traceId=%X{traceId:-} %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

**Lưu ý:** pattern nhiều dòng trong XML ở ví dụ phục vụ đọc; khi vận hành thực nên đặt pattern **trên một dòng** để tránh whitespace/newline ngoài ý muốn làm parser downstream khó xử lý. Một pattern gọn hơn:

```xml
<configuration>
  <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
    <target>System.out</target>
    <encoder>
      <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level service=orders logger=%logger{36} traceId=%X{traceId:-} %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="STDOUT"/>
  </root>
</configuration>
```

Ứng dụng có thể gọi:

```java
// Mảnh tích hợp, yêu cầu SLF4J và backend Logback/Log4j 2.
logger.info("event=order_created orderId={} status={}",
        safeOrderId, "CREATED");
```

Trong đó `safeOrderId` là giá trị đã được duyệt để log. **Dùng `{}` không tự mask secret**. Pattern `%msg` có thể chứa ký tự newline từ input hoặc stack trace nếu message/throwable được xuất; cần chính sách escape và tránh log raw user input.

### 6.1. Vì sao không gắn appender lặp?

Nếu một logger con tham chiếu `STDOUT` và đồng thời propagate lên root cũng tham chiếu `STDOUT`, **một log event có thể xuất hai lần**. Kiểm tra logger additivity và appender references. Không tắt `additivity` bừa bãi nếu đó là cách audit sink ở root được nhận event; phải xác định routing mong muốn.

Nếu hệ thống vừa ghi stdout vừa ghi file và collector thu **cả stdout lẫn file**, một logical event có thể bị index hai lần. Hãy định nghĩa **đường thu gom duy nhất** cho mỗi loại log hoặc có event ID/dedup policy rõ ràng.

### 6.2. Log4j 2 Console appender

Mảnh XML minh họa của **Log4j 2**, cần dependency Log4j 2 tương ứng:

```xml
<Configuration status="WARN">
  <Appenders>
    <Console name="Stdout" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{ISO8601} %-5level %c{1.} - %msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="Stdout"/>
    </Root>
  </Loggers>
</Configuration>
```

`target="SYSTEM_OUT"` chỉ định stdout. `Console` không đồng nghĩa JSON hoặc transport bảo đảm; lựa chọn layout/encoder và các dependency phải phù hợp.

**Không dùng đồng thời nhiều SLF4J providers/bindings** hoặc tự nối các bridge JUL/SLF4J/Log4j 2 thành vòng. Kiểm tra cấu hình runtime khi xuất hiện log lặp, không có log hoặc logging initialization warning.

## 7. Text one-line và structured JSON cho container logs

### 7.1. Tại sao “mỗi event một dòng” hữu ích?

Nhiều công cụ container và log collectors xử lý stream dưới dạng **dòng**. Nếu message một event chứa newline thật, nó có thể trở thành nhiều bản ghi, hoặc cần một quy tắc ghép multiline. Ví dụ:

```text
INFO event=request_completed requestId=req-42
ERROR event=dependency_failure errorCode=DB_TIMEOUT
java.io.IOException: timed out
    at example.Repository.read(Repository.java:42)
    at example.Service.handle(Service.java:18)
```

Nếu mỗi dòng bị index riêng, hai stack frames có thể mất `requestId`/`errorCode` và dễ bị đếm nhầm. Một collector có multiline parser có thể ghép chúng, nhưng **phải cấu hình đúng log format, nguồn và ranh giới event**.

Cách khác là structured JSON **một dòng vật lý mỗi event**, trong đó các dấu xuống dòng bên trong `stack_trace` được encode thành chuỗi escape `\n` thay vì newline thật. Điều này thường giúp parse và correlation dễ hơn.

### 7.2. Schema JSON ví dụ

```json
{"timestamp":"2026-11-10T03:40:00.000Z","level":"INFO","service":"orders","event":"request_completed","route":"/orders","status":201,"request_id":"req-42","trace_id":"trace-demo-7"}
```

Đây là **dữ liệu minh họa**, không phải output từ code JUL ở mục 5. Các field thường hữu ích:
- `timestamp` UTC/ISO 8601 cho thời điểm tạo event, cùng timestamp ingest của nền tảng nếu có.
- `level`/`severity` theo enum ổn định, không suy từ stdout/stderr duy nhất.
- `service`, `environment`, `component`, `version`; hạ tầng bổ sung `pod`/`container`/`namespace` khi có.
- `event`/`error_code`: định danh sự kiện hoặc loại lỗi ổn định để query, không dùng raw exception message làm “mã lỗi”.
- `route` là route template thay vì URL chứa query/token.
- `request_id`, `trace_id`, `span_id` phục vụ liên kết log/tracing theo chính sách; không đưa ID có cardinality cao làm metric label.
- `duration_ms`, `status`, `retry_attempt`, `result` khi được đo đúng.

**JSON phải được tạo bằng encoder chuẩn**, không ghép string thủ công với dữ liệu do user nhập. Encoder cần escape `"`, dấu gạch chéo ngược, newline và ký tự điều khiển đúng quy tắc. Nếu muốn dùng Logback/Log4j 2 JSON layout, xác minh đúng encoder/layout và dependency ở phiên bản thực tế; `ConsoleAppender` không tự biến text thành JSON.

### 7.3. Khi nào stack trace multiline vẫn hợp lý?

Stack trace đầy đủ có giá trị khi sửa bug, nhưng:
- Kiểm tra `Throwable.getMessage()` và cause/suppressed: có thể chứa URI, SQL, header hoặc credential.
- Có thể xuất stack trace ở một field JSON được escape, hoặc dùng multiline parser ở collector.
- Collector phải nhận biết **đầu record** và gắn phần tiếp theo với đúng container/stream. Không ghép bừa các dòng của hai containers khác nhau.
- Giới hạn độ dài/độ sâu stack trace để tránh event quá lớn.
- Cần test log rate cao và trường hợp record bị cắt/chia thành partial fragments bởi runtime.

Đừng dùng parser multiline chỉ vì muốn “log cả request payload”: an toàn dữ liệu luôn là quyết định ở ứng dụng, trước khi vào stdout.

## 8. Docker: runtime ghi nhận stdout thế nào?

Một container chạy Java qua entrypoint phù hợp có thể xuất log:

```dockerfile
# Mảnh Dockerfile minh họa; cần app.jar có sẵn ở build context.
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

**Lưu ý:** Image/tag chỉ để minh họa cách launch Java, không xác nhận một phiên bản image cụ thể đang có sẵn tại thời điểm đọc. Ứng dụng phải đã được đóng gói thành `app.jar` với dependencies và cấu hình console logging. Dockerfile không thay thế việc build artifact.

Dạng `ENTRYPOINT ["java", ...]` khởi chạy Java trực tiếp, tránh shell trung gian không chuyển signal đúng. Nếu buộc dùng shell script, hãy dùng `exec java ...` ở bước cuối để thay thế shell process, giúp signal/shutdown semantics rõ ràng hơn.

Ví dụ xem log container:

```bash
docker run --name orders-demo orders-app:local
docker logs --tail 100 orders-demo
docker logs --since 10m --timestamps orders-demo
docker logs -f orders-demo
docker inspect -f '{{.HostConfig.LogConfig.Type}}' orders-demo
```

Các lệnh trên là **cách thao tác**, không có stdout cố định vì phụ thuộc image/container thật. `docker logs` thường hiển thị stdout và stderr do logging driver lưu/tích hợp; **khả năng truy xuất cụ thể phụ thuộc logging driver và cấu hình Docker**. `--timestamps` thêm timestamp của log record theo cơ chế Docker, không nhất thiết trùng timestamp event do ứng dụng ghi.

### 8.1. Logging driver, rotation và retention

Docker hỗ trợ nhiều logging drivers. Ví dụ `json-file` hoặc `local` có cách lưu/rotation khác nhau; một số drivers chuyển trực tiếp sang hệ thống remote hoặc có cơ chế cache tùy phiên bản/cấu hình.

Không mặc định:
- Mọi host dùng cùng driver hay cùng max-size/max-file.
- `docker logs` luôn đọc được toàn bộ lịch sử khi driver là remote.
- Log sẽ còn sau khi container bị xóa.
- Log được giữ mãi vì ứng dụng đang chạy.
- Docker logging driver có cùng semantics với Kafka hoặc transactional store.

**Cần biết cấu hình runtime và disk budget thực tế**. Nếu log rotation/cap xóa file trước khi collector ship, dữ liệu có thể mất. Nếu không giới hạn volume, node disk có thể đầy. Dung lượng lưu, rotation, persistence và bảo mật là trách nhiệm hạ tầng cần được giám sát.

### 8.2. Blocking và non-blocking delivery

Một số chế độ logging driver/runtime có chính sách **blocking** khi không thể chuyển log, hoặc **non-blocking** với buffer giới hạn và khả năng drop khi đầy. Không suy ra rằng mọi cấu hình đều giống nhau.

Các trade-off:
- Blocking có thể làm tiến trình đợi hoặc tăng latency nếu đường log nghẽn.
- Non-blocking có thể ưu tiên tiếp tục nghiệp vụ nhưng **mất log** khi buffer đầy.
- Appender bất đồng bộ trong JVM còn có queue riêng và có thể mất/bị block trước khi byte đến runtime.
- Nếu hạ tầng mất log ở một tầng, tăng retry của tầng khác không thể khôi phục bytes chưa được lưu.

Với ứng dụng cần audit giao dịch bắt buộc, **stdout không phải cam kết persist exactly-once**. Thiết kế một audit store/outbox có transaction và chính sách riêng cho những event không được phép mất.

## 9. Kubernetes: từ container stdout đến `kubectl logs`

Trong Kubernetes thông thường, container runtime theo giao diện CRI phát log theo định dạng/container log stream mà kubelet biết cách truy cập. Kubelet quản lý logging của containers trên node, trong đó bao gồm cơ chế rotation theo cấu hình node.

Sơ đồ khái niệm:

```text
Java stdout/stderr inside pod
             |
             v
Container runtime (CRI logging)
             |
             v
Node container log files
             |
             +--> kubectl logs via kubelet/API
             |
             +--> node-level log agent (DaemonSet)
                         |
                         v
               centralized logging backend
```

Ở nhiều hệ thống Linux/Kubernetes, log files nằm dưới các đường như `/var/log/pods/...` và symlinks trong `/var/log/containers/...`, nhưng **đừng hardcode một path làm chuẩn duy nhất** khi chưa kiểm tra node OS, runtime và cấu hình cụm.

### 9.1. Các lệnh quan sát log Pod

```bash
kubectl logs pod/orders-abc -c app --tail=100
kubectl logs pod/orders-abc -c app --since=10m --timestamps
kubectl logs -f pod/orders-abc -c app
kubectl logs pod/orders-abc -c app --previous --tail=100
```

`orders-abc` và `app` là **tên minh họa**; thay bằng Pod/container thật. Ý nghĩa:
- `-c app` chỉ định container khi Pod có nhiều containers, tránh nhầm app với sidecar.
- `--tail`, `--since` giới hạn lượng log đọc và thời gian.
- `--timestamps` bổ sung timestamp do lớp container logging cung cấp.
- `-f` tiếp tục theo dõi output trong lúc container chạy.
- `--previous` thử lấy log của lần chạy container đã kết thúc **gần nhất** nếu kubelet còn lưu được; không phải toàn bộ lịch sử restart.

**Giới hạn:** `kubectl logs` là công cụ quan sát log trên node/container theo khả năng hiện có, **không phải kho lưu trữ lâu dài**. Kubelet rotation, pod deletion/eviction, node loss và chính sách storage có thể làm log cũ không truy xuất được. Thực tế Kubernetes chỉ cung cấp phần log đang có theo cơ chế lưu/rotation; không nên phụ thuộc `kubectl logs` để phục vụ kiểm toán dài hạn.

### 9.2. Định dạng CRI và partial lines

Trong những môi trường dùng định dạng log CRI, một entry có thể có timestamp, tên stream `stdout`/`stderr` và marker biểu thị dòng hoàn chỉnh hay một phần (thường được mô tả bằng `F` và `P`). Đây là **metadata ở tầng runtime**, không phải định dạng JSON ứng dụng Java tự viết.

Điểm quan trọng:
- Một Java log event quá lớn có thể bị chia thành **các fragment** ở lớp runtime.
- Collector cần parser phù hợp cho **CRI/Docker format**, có thể phải tái ghép partial fragments, và xử lý multiline stack trace riêng.
- Chỉ tách file theo mỗi newline rồi giả định **mỗi dòng luôn là một event hoàn chỉnh** có thể làm hỏng record lớn.
- Khi gộp, không bao giờ ghép các fragment của hai container/stream khác nhau thành một event.
- Một parser CRI chưa chắc parse được các JSON fields do app viết; thường cần **hai lớp**: parse container envelope trước, parse application message sau.

Đừng tự thiết kế ứng dụng phụ thuộc vào chính xác một path log hoặc marker nội bộ khi chưa xác minh cấu hình runtime/collector.

### 9.3. Pod metadata và labels

Một log agent trên node có thể bổ sung:
- Namespace, Pod name/UID, container name/ID.
- Node name, cluster/region, workload/deployment labels.
- Stream, timestamp lúc runtime ghi nhận, nguồn file.
- Các labels được phép dùng trong indexing và access control.

**Ứng dụng không nhất thiết cần tự in toàn bộ Pod metadata trong mọi message**; nhiều collector làm việc đó ổn hơn. Nhưng app vẫn nên ghi `service`, `event`, `error_code`, `trace_id` nếu cần và tránh phụ thuộc duy nhất vào Pod name vì Pod thay đổi khi redeploy.

Không tự gắn raw secret vào Kubernetes labels/annotations để “tiện tìm log”. Labels cũng có thể xuất hiện trong nhiều hệ thống thu thập/giám sát.

## 10. Collector: từ file node tới backend tìm kiếm

Một DaemonSet hoặc agent có thể dùng Fluent Bit, Vector, OpenTelemetry Collector hoặc một nền tảng khác để đọc container log stream rồi gửi về hệ thống tập trung.

Chức năng phổ biến:
1. **Tail/watch** nguồn log, quản lý offset/checkpoint.
2. **Parse envelope** container runtime (timestamp, stream, partial/complete).
3. **Merge fragments và multiline** nếu định dạng yêu cầu.
4. **Parse application schema** (JSON hoặc text pattern) và chuẩn hóa field.
5. **Enrich metadata** Pod/container/namespace/service.
6. **Filter/transform/redact** theo chính sách bổ sung.
7. **Batch/retry/backoff/buffer** khi backend chậm hoặc ngắt kết nối.
8. **Export** tới backend, có theo dõi lỗi, queue depth, throughput và lost events.

Tên plugin/config của mỗi collector thay đổi theo sản phẩm và phiên bản, nên không copy nguyên một pipeline mẫu từ công cụ này sang công cụ khác mà không xác nhận tài liệu thực tế.

### 10.1. Chọn nguồn duy nhất, tránh ghi lặp

Một lỗi phổ biến là:
- Agent A đọc `/var/log/containers`.
- Agent B cũng đọc cùng nguồn theo một chart khác.
- Hoặc cùng ứng dụng được thu từ stdout và từ file riêng, cả hai gửi về cùng index.

Hệ quả là **duplicate log ingestion**. Nó có thể làm méo log-based alerts, tăng chi phí lưu và khiến một request trông như bị xử lý hai lần. Để điều tra:
- Đếm logger invocation ở Java.
- So sánh raw `kubectl logs`/Docker logs với backend.
- So sánh metadata collector, source path, container ID và ingestion ID.
- Xem retry của shipper khi mất ACK, cơ chế checkpoint và dedup ở destination.

Không xóa log duplicate theo `request_id` một cách mù quáng: một request có thể có nhiều log events hợp lệ. Cần một **event instance identity** và chính sách dedup đúng tầng.

### 10.2. Checkpoint và rotation

Khi node agent tail file, nếu file bị rotate/rename/truncate hoặc container restart, checkpoint phải chỉ ra **đã đọc đến đâu**. Tùy thuật toán, agent có thể:
- Đọc lặp lại một đoạn (duplicate).
- Bỏ sót đoạn khi file biến mất quá nhanh (loss).
- Theo nhầm file nếu fingerprint/identity không đủ ổn định.

Vì vậy:
- Cấu hình rotation đủ dung lượng cho tốc độ log và thời gian mất kết nối lớn nhất dự kiến.
- Theo dõi ingest lag, file tailing errors, backlog và dropped records.
- Test log burst và agent restart.
- Không dựa vào exact-once giữa stdout → collector → backend nếu pipeline không có cơ chế chứng minh điều đó.

### 10.3. Timestamp và thứ tự

Một record có thể có nhiều thời điểm:
- `event_time`: thời điểm application tạo log event.
- `container_time`: thời điểm runtime ghi nhận dòng.
- `ingest_time`: thời điểm backend nhận hoặc index.
- `processing_time`: khi query/alert pipeline xử lý.

Sự khác nhau giữa chúng có thể do buffering, network retry, clock skew hoặc backend queue. **Không mặc định thứ tự ingest là thứ tự nghiệp vụ**. Với workflow quan trọng, dùng correlation ID và sequence/business event ID khi thích hợp, không suy từ log timestamp đơn thuần rằng mọi thao tác đã commit theo thứ tự đó.

Nếu backend parse một log JSON có `timestamp` và node agent cũng có timestamp CRI, cần cấu hình rõ nguồn thời gian được dùng để query/alert. Timezone nên được chuẩn hóa (thường UTC), clock của nodes/services cần được đồng bộ.

## 11. Các rủi ro thực tế của container stdout logging

| Rủi ro | Ví dụ | Cách giảm thiểu |
| --- | --- | --- |
| **Ghi quá nhiều** | DEBUG log mọi request body | Chọn schema allowlist, volume budget, đúng level |
| **Lộ secret/PII** | Token, cookie, mật khẩu, nội dung tài liệu trong log | Loại ngay ở call site; redaction tầng sau chỉ bổ sung |
| **Blocking stdout** | Collector/runtime chậm khiến business thread đợi | Chọn appender/buffer bounded, đo latency và hiểu drop policy |
| **Async queue drop** | Queue đầy khi spike traffic | Metrics về drop, queue depth, cấu hình ưu tiên hợp lý |
| **Rotation mất lịch sử** | Kubelet/Docker xóa file trước agent ship | Đặt size/retention/lag budget, giám sát backlog |
| **Pod/node biến mất** | Pod bị evict, node bị hỏng | Centralization, retention; không dựa duy nhất vào `kubectl logs` |
| **Multiline bị tách** | Java exception bị index thành 30 events | One-line JSON hoặc multiline parser đúng format |
| **Partial log fragments** | Dòng quá dài bị runtime chia | Giới hạn event size, CRI partial recombination |
| **Duplicate collector** | Hai agents đọc cùng file | Quy hoạch pipeline; source/event identification |
| **Duplicate appender** | Root + package logger cùng ConsoleAppender | Kiểm tra additivity/handler tree |
| **Sai severity** | Tất cả gửi stderr nhưng query coi là ERROR | Dùng `level`/`severity` từ app schema |
| **Sai timestamp** | Dashboard dùng ingest time, dữ liệu đến trễ | Ghi event time và định nghĩa parse time |
| **Log injection** | User input chứa CR/LF làm giả record | Encoder chuẩn, giới hạn ký tự/kích thước |
| **Mất log khi crash** | Async queue chưa flush, container bị kill | Shutdown policy, audit store riêng khi bắt buộc |
| **No-data false healthy** | Service chết nên không còn ERROR | Heartbeat/synthetic checks và giám sát pipeline |

### 11.1. Log storm và tài nguyên container

Trong một sự cố dependency, một triệu stack traces có thể gây:
- CPU lớn do formatting và serialization.
- Heap allocations/GC tăng, ảnh hưởng latency.
- Disk pressure trên node dù ứng dụng “không ghi file”.
- Collector phải parse/retry batch lớn, tăng phí ingest.
- Log-based alert đếm retry attempts nhiều lần như nhiều sự cố.

Đừng dùng “in full stack trace cho mỗi retry” làm chiến lược quan sát mặc định. Tách `attempt_failed` khỏi `operation_failed`, dùng error code và metric counters. Khi cần stack trace, giới hạn theo event type/volume và quyền đọc, không làm mất tín hiệu audit bắt buộc.

### 11.2. Container restart và graceful shutdown

Khi Docker/Kubernetes yêu cầu dừng, tiến trình Java cần có cơ hội flush appender/async queue trong khoảng grace period được cấu hình. Cần chú ý:
- Dùng exec-form entrypoint hoặc `exec` trong shell script để signal tới đúng process.
- Có shutdown hook/lifecycle do logging framework quản lý; test với SIGTERM.
- Dừng nhận request/job mới, hoàn tất/ack các thao tác theo contract trước khi thoát.
- Không mặc định `Runtime.addShutdownHook` chạy khi JVM bị kill cưỡng bức, OOM nghiêm trọng hoặc node power-off.
- Với `SIGKILL` hoặc crash đột ngột, buffer trong JVM chưa được flush có thể mất.
- Container stdout và collector downstream cũng có buffer riêng; flush Java logger **không đồng nghĩa** backend đã index toàn bộ log.

Với audit bắt buộc, không đặt cam kết chứng cứ chỉ dựa vào bước shutdown flush.

## 12. Gắn log với request, trace và workload

Một container không chỉ xử lý một request. Trong cùng một phút có thể có hàng nghìn logs từ nhiều threads và async callbacks. Nếu chỉ ghi:

```text
ERROR database timeout
ERROR database timeout
```

sẽ khó biết lỗi nào thuộc request nào. Thay vào đó:

```text
ERROR event=dependency_timeout service=orders operation=create_order requestId=req-42 traceId=trace-demo-7 dependency=inventory
```

Những ID là dữ liệu giả. Trong ứng dụng thật:
- **request ID** do server sinh hoặc được kiểm tra độ dài/ký tự; không tin mù một header tùy ý.
- **trace/span ID** lấy từ tracing context đã được xác minh/chuẩn hóa; đừng dùng làm metric label.
- **service/operation** là field ổn định để query và route.
- **pod/container metadata** được platform/collector thêm sau, không phải ID nghiệp vụ.
- Không ghi password, raw Bearer token, Cookie, request body hoặc SQL bind values vào MDC để “cho đủ context”.
- Nếu dùng MDC/ThreadContext với thread pool, phải cleanup/restore theo scope và propagate đúng qua async boundaries.

**Một log event đủ context ở đúng thời điểm** thường hữu ích hơn năm log không có correlation ID. Trong hệ thống nhiều microservices, kết hợp trace sample, error code, deployment version và source container giúp tìm failure path.

## 13. Security: container stdout vẫn là nơi chứa dữ liệu nhạy cảm

Không phải vì log nằm trong console thay vì file mà nó “tạm thời” hoặc “vô hại”. Dữ liệu có thể được sao chép tới:
- Node log files và backup/snapshot.
- Cluster log collector.
- Centralized index, dashboard, export.
- Notification, incident ticket, chat khi alert template trích message.
- Development/staging nếu ai đó copy raw production logs.

**Cần áp dụng data minimization tại nguồn**:
1. Không log raw credentials, access token, refresh token, password, API key, private key, session cookie hoặc signed URL.
2. Không in whole request/response body, DTO chứa PII, headers hoặc SQL bind values.
3. Dùng route template, result/error code và correlation ID được phép.
4. Dùng structured encoder để escape, không tự nối JSON với raw user input.
5. Đặt role-based access, TLS/mTLS phù hợp, encryption at rest, retention và audit export.
6. Không đưa secret thật vào các ví dụ/test; dùng canary hoàn toàn giả.
7. Khi secret đã lọt pipeline, ngăn ghi tiếp, đánh giá sink/bản sao và revoke/rotate credential theo chính sách; xóa một dòng log không đủ.

Trên Kubernetes, quyền xem Pod logs có thể phụ thuộc RBAC; người có quyền điều tra container logs có thể đọc thông tin nhạy cảm nếu app đã in ra. **Không coi quyền xem `kubectl logs` là giải pháp thay thế cho việc không ghi secret.**

## 14. Kiểm thử end-to-end: stdout có thật sự tới nơi cần?

Một bài test đúng nên kiểm tra **cả ba tầng**:
- Java application có tạo đúng event không?
- Container runtime và công cụ xem log có nhận record không?
- Collector/backend có index đủ, đúng parse, đúng tenant/access và không nhân bản không?

### 14.1. Trên máy phát triển

1. Chạy Java demo, đối chiếu stdout chính xác như mục 5; xác nhận stderr không có output do app tạo.
2. Đóng gói app sử dụng console logging, chạy container.
3. Dùng `docker logs --timestamps` để quan sát; xác nhận level, message, timestamp và số bản ghi.
4. Cho một log event chứa giá trị giả có dấu ngoặc kép/newline, kiểm tra escaping/parsing. **Không dùng bí mật thật**.
5. Thử log rate cao có giới hạn và quan sát CPU, memory, blocking/dropped events theo cấu hình.
6. Restart container, xem log hiện có, thời gian lưu và hậu quả rotation.

### 14.2. Trên Kubernetes/staging

1. Xác định đúng Pod/container, xem bằng `kubectl logs -c app`.
2. Kiểm tra khi Pod có sidecar: không nhầm log ứng dụng với sidecar.
3. Gửi request test có correlation ID được kiểm soát, xác nhận field ở `kubectl logs`.
4. Query backend tập trung theo service/trace/request ID; so khớp số record.
5. Với stack trace, xác nhận collector merge multiline hoặc parse JSON field đúng, không tạo nhiều event độc lập.
6. Test container restart và `--previous` nếu dữ liệu còn; xác minh backend giữ lịch sử theo retention policy dù Pod cũ biến mất.
7. Fault-inject collector/network down **trong staging**: kiểm tra retry, backlog, dropped logs, ingest lag, rotation.
8. Kiểm tra log routing riêng stdout/stderr, timestamp và Kubernetes metadata.
9. Kiểm tra canary giả không xuất hiện ở structured fields, exception text, alert annotations hoặc exports.

Không cần và không nên gây outage production chỉ để kiểm tra đường log. Với hệ thống cần log không mất, bổ sung thiết kế lưu trữ bền vững và các test transaction/crash chuyên biệt.

### 14.3. Những assertion nên có

| Điều kiện | Ý nghĩa kiểm thử |
| --- | --- |
| Ghi 1 INFO event → 1 record ở stdout | Không nhân đôi appender |
| Ghi 1 event → 1 document backend theo policy | Không có duplicate collector/shipper |
| Thêm metadata Pod/container | Enrichment đúng nơi/đúng instance |
| JSON parse thành field level/service/event | Query và alert có thể dùng field ổn định |
| Mất collector trong khoảng ngắn | Queue/retry/loss đúng cấu hình |
| Log burst lớn | Không vượt memory/disk/log-budget ngoài mong đợi |
| CRI partial + multiline | Không mất/ngắt record ngoài policy |
| Container restart/rotation | Recovery/retention đúng, hiểu giới hạn `kubectl logs` |
| Bật DEBUG trong staging | Không vô tình xuất token, body hoặc secrets |
| Appender lỗi hoặc không còn log | Có health/meta-monitoring nhận ra thiếu dữ liệu |

**Quan trọng:** “`docker logs` xem được” chỉ kiểm tra đến runtime. “Backend có một sample record” không chứng minh tất cả log đều đã được vận chuyển. Cần metrics cho emitted, dropped, exported và failed tùy các tầng có hỗ trợ.

## 15. Điều tra khi không thấy log trong container

Thực hiện theo chuỗi câu hỏi để tránh chỉnh bừa:

### 15.1. Ứng dụng có phát event không?
- Log level `INFO/DEBUG` có bị filter ở logger hoặc appender?
- Java dùng JUL ConsoleHandler mặc định ghi stderr còn collector chỉ thu stdout?
- Framework có redirect console vào file hoặc appender không được gắn vào root?
- Có bug initialization, bridge conflict hoặc logger object khác?
- Event đã chạy qua code path hay handler đã throw trước đó?
- Process stdout/stderr có bị đóng hoặc redirect nhầm?

### 15.2. Runtime có nhận stream không?
- Process chính trong container có chạy trực tiếp, hay shell wrapper redirect output sang file?
- Logging driver có cấu hình capture không? `docker logs` có hỗ trợ/cached records theo driver đó không?
- Container có bị restart/xóa hay node log file đã rotate?
- Có limit/size cap hoặc dropped logs ở runtime không?
- Có lỗi định dạng hoặc binary data khiến log khó hiển thị?

### 15.3. Collector có đọc và xuất được không?
- Agent có đọc đúng node/path/pod/container?
- Cấu hình filter có loại mất event hoặc drop mức DEBUG?
- Parser CRI/Docker và multiline có xử lý đúng không?
- Checkpoint có bỏ qua vị trí file sau rotation?
- Backend có từ chối do JSON parse, field size, quota hoặc quyền ghi?
- Có queue backlog, retry storm hoặc network/TLS failure không?

### 15.4. Backend/query có đang hiển thị đúng không?
- Time range có đúng timezone và event-vs-ingest time?
- Labels `service`, `namespace`, `container` có được enrich đúng?
- Truy vấn có vô tình loại stream=stderr?
- Record bị quarantine do mapping/schema issue hoặc retention?
- Người dùng truy vấn có quyền truy cập index/tenant hay không?

**Không vội tăng log level lên TRACE toàn production.** Trước tiên đối chiếu một event kiểm thử an toàn và lần theo từng tầng để tìm điểm biến mất.

## 16. Lỗi phổ biến và cách xử lý

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Viết log ra file trong container và không mount/ship | Log biến mất khi container bị thay thế | Dùng stdout hoặc file collector/persistence đã thiết kế |
| Nghĩ JUL ConsoleHandler in stdout | Record nằm stderr | Cấu hình handler đúng và thu cả stream nếu cần |
| Logger con và root cùng ConsoleAppender | Log trùng | Kiểm tra additivity/routing |
| Chỉ dùng `System.out.println` cho production | Thiếu schema, level, MDC, cấu hình | Dùng logging framework và console appender |
| Ghi stack trace thành nhiều dòng không parser | Mất context, alert count sai | JSON one-line hoặc multiline parser |
| Chuyển binary/request body sang console | Lộ dữ liệu và log storm | Chỉ log metadata/allowlist |
| Dùng `docker logs` làm kho lưu dài hạn | Lịch sử phụ thuộc driver/container | Central logging và retention policy |
| Dùng `kubectl logs --previous` để tìm mọi lần restart | Chỉ có thể thấy một số bản log còn tồn tại | Centralize và truy vấn theo workload/time |
| Đếm stdout lines thành số business operations | Duplicate/partial/multiline làm sai count | Metric outcome, ID và parsing đúng |
| Nghĩ stdout không thể block | Latency/timeout khi đường log nghẽn | Đo throughput, bounded appender/queue |
| Dùng async queue nhưng không đo drop | Silent loss khi quá tải | Health metrics và fallback/audit policy |
| Không có rotation | Node disk đầy, ảnh hưởng workload | Thiết lập retention, quota, alert disk/ingest lag |
| Rotate quá nhanh | Agent chưa đọc kịp đã mất file | Dimension theo worst-case log throughput/outage |
| Tin ingest timestamp là event time | Truy vết thứ tự sai khi retry/backlog | Chuẩn hóa event time/ingest time |
| Gắn request ID vào metric labels | Cardinality lớn | Để ID trong log/trace |
| Thu cả stdout và cùng file log | Duplicate backend documents | Một pipeline chính hoặc dedup theo event identity |
| Alert theo “không có ERROR” | Service/collector chết không phát log | Meta-monitoring và synthetic checks |
| Flush Java rồi tuyên bố backend đã nhận | Runtime/collector còn buffer hoặc lỗi | Theo dõi end-to-end pipeline và ACK có thực |

## 17. Câu hỏi luyện tập

**Câu 1.** Một app Java dùng JUL `ConsoleHandler` mặc định. Pod đã phát log nhưng hệ thống chỉ thu `stdout`. Tại sao người vận hành không thấy log?

**Đáp án:** JUL ConsoleHandler mặc định gửi record đến **stderr**. Nếu agent lọc chỉ stdout, log bị bỏ qua. Cần điều chỉnh routing/cấu hình hoặc collector thu cả hai stream theo chính sách.

**Câu 2.** Một container có 2 replica; cả hai cùng `logger.info` một event. Có được coi là một log record duy nhất không?

**Đáp án:** Không thể kết luận. Mỗi replica/process có thể phát một bản ghi; cần biết chúng có xử lý một business event độc lập hay message redelivery, cùng một event được tạo hai lần, hoặc collector bị duplicate. Dùng business event ID, workload metadata và transaction context phù hợp.

**Câu 3.** `kubectl logs --previous` có bảo đảm xem được tất cả lần restart và log của Pod đã bị xóa không?

**Đáp án:** Không. Dữ liệu phụ thuộc container instance trước còn được kubelet/runtime lưu và rotation; không phải archive. Muốn giữ lịch sử cần backend tập trung/retention riêng.

**Câu 4.** Một stack trace 20 dòng bị log collector nhận thành 20 documents. Có nhất thiết Java đã ném 20 exceptions?

**Đáp án:** Không. Có thể chỉ một throwable được render multiline. Cần parse/merge multiline đúng nguồn và kiểm tra số lần logger được gọi.

**Câu 5.** Một service dùng async appender và Docker logging driver non-blocking. `logger.info` trả về thành công có chứng minh log đã tới backend?

**Đáp án:** Không. Có thể drop ở queue JVM, buffer runtime hoặc collector; cần đo accepted/emitted/dropped/exported và xác nhận các bảo đảm thực tế.

**Câu 6.** Có thể dùng output từ stdout để lưu event thanh toán bắt buộc exactly-once không?

**Đáp án:** Không nên mặc định. Container stdout là đường chẩn đoán theo stream, không phải transactional audit ledger. Với nghĩa vụ bền vững cần cơ chế commit/outbox/idempotency và storage có bảo đảm phù hợp.

**Câu 7.** Một JSON log có trường `timestamp`, collector cũng gắn `time` và backend có `ingest_at`. Nên dùng trường nào để tìm lỗi?

**Đáp án:** Phụ thuộc mục tiêu: event time để biết khi ứng dụng ghi nhận, runtime time để xác định khi container xuất, ingest time để quan sát độ trễ pipeline. Hãy đặt mapping/query nhất quán và không lẫn ba mốc.

**Câu 8.** Khi log backend không nhận được events từ một pod, bước đầu hợp lý nhất là gì?

**Đáp án:** Tìm một event an toàn có thể tái hiện, kiểm tra ứng dụng có phát, `kubectl logs` có nhận, agent có đọc/parse, network/ingest có lỗi và truy vấn có đúng scope/time. Không bật TRACE hoặc log raw request body ngay.

## 18. Checklist đưa container stdout logging vào production

1. **Application emit:** Logger có appender/handler duy nhất được thiết kế; stdout/stderr routing rõ ràng, không nhân đôi qua root/child.
2. **Event schema:** Level, service, event code, correlation ID, timestamp và metadata cần thiết được xuất có cấu trúc; không log raw payload/secret.
3. **One event / line:** Dùng JSON encoder có escaping chuẩn hoặc parser multiline được kiểm thử; có limit event size.
4. **Docker config:** Biết logging driver, cách `docker logs` hoạt động, rotation và storage budget.
5. **Kubernetes config:** Hiểu CRI/node log lifecycle, `kubectl logs` và giới hạn `--previous`/rotation.
6. **Collector:** Có đúng nguồn, parse Docker/CRI đúng, merge partial/multiline, checkpoint và enrich container metadata.
7. **Delivery semantics:** Biết tại đâu có buffer, retry, drop và duplicate; không tuyên bố exactly-once nếu không có bằng chứng.
8. **Performance:** Đo log volume, CPU/GC, sync stdout blocking, async queue depth, disk/network và collector lag.
9. **Security:** Loại secret/PII trước logger, phân quyền đọc/export, mã hóa đường truyền/lưu trữ, retention và incident response.
10. **Correlation:** Request/trace ID qua async boundaries, không dùng ID cardinality cao làm metric labels.
11. **Lifecycle:** Test startup/shutdown, SIGTERM, restart, node loss, log rotation và graceful flush; biết giới hạn khi SIGKILL.
12. **Observability of observability:** Có metrics/alerts cho appender error, collector backlog, dropped events, no-data và storage pressure.
13. **End-to-end validation:** So khớp một event mẫu ở app, Docker/Kubernetes và backend, không dựa riêng vào một công cụ xem log.
14. **Audit exception:** Với bản ghi bắt buộc không được mất, dùng cơ chế bền vững/transactional riêng thay vì chỉ stdout.

## 19. Kết luận

**Container stdout** là ranh giới vận chuyển log tự nhiên giữa ứng dụng Java và nền tảng container. Java vẫn cần **logging framework được cấu hình đúng**, schema ổn định và data minimization; Docker/Kubernetes cung cấp tầng capture, còn log collector/backend chịu trách nhiệm parse, enrich, ship, retention và search.

Thiết kế tốt không chỉ là “log xuất hiện khi chạy `docker logs`”. Hãy đảm bảo:
- Một event phát ra đúng đích, không vô tình nhân đôi hoặc chia sai thành nhiều record.
- stdout/stderr, timestamps, JSON/multiline và CRI fragments được hiểu đúng.
- Rotation, restart, buffer, retry và loss được đo/kiểm thử.
- Không đưa credential/PII vào log hay xem stdout như kho audit transaction.
- Có khả năng truy vết từ log event ở JVM đến backend cuối, kèm health của chính pipeline.

Khi quản trị được cả **nội dung log** lẫn **đường đi của log**, hệ thống Java mới có logging container hữu ích, đáng tin trong giới hạn thiết kế và an toàn để vận hành.