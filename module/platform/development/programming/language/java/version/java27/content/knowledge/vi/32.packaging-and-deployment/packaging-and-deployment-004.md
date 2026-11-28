# Cấu hình logging, health check và graceful shutdown trong Java 27

Đóng gói được một ứng dụng Java thành JAR hoặc container mới chỉ là bước đầu. Một dịch vụ có thể khởi động thành công nhưng không phát sinh log đủ hữu ích để chẩn đoán, **báo “khỏe” dù chưa sẵn sàng nhận yêu cầu**, hoặc bị ngắt giữa chừng khi triển khai phiên bản mới. Ba vấn đề này liên quan trực tiếp đến khả năng vận hành (*operability*) của ứng dụng.

Trong **Java 27**, có thể xây dựng các cơ chế nền tảng bằng API vẫn được hỗ trợ:

- **Logging:** `System.Logger` và `java.util.logging` (JUL) trong JDK; hoặc một facade/backend có chính sách cấu hình rõ ràng của dự án.
- **Health checks:** endpoint cung cấp trạng thái *liveness*, *readiness*, và khi cần *startup*; Kubernetes và bộ điều phối dùng kết quả để quyết định khởi động lại hay điều hướng lưu lượng.
- **Graceful shutdown:** phát hiện yêu cầu dừng qua lifecycle/signal thích hợp, **ngừng nhận việc mới**, để việc đang chạy có cơ hội kết thúc, giải phóng tài nguyên rồi dừng trong một thời hạn hữu hạn.

Bài thuộc chương **Đóng gói và triển khai** của module **Java 27 và các kiến thức liên quan**. Ví dụ minh họa dùng `java.util.logging`, `com.sun.net.httpserver.HttpServer` thuộc module JDK `jdk.httpserver`, `Runtime.addShutdownHook` và virtual-thread executor chuẩn. Không cần preview flags. Đây là **máy chủ HTTP nhỏ phục vụ học tập**, không thay thế framework/web server được harden cho production.

## 1. Nhìn toàn bộ vòng đời của một Java service

Ba cơ chế nên được thiết kế cùng vòng đời:

```text
       DEPLOY / START
              │
              ▼
    Khởi tạo cấu hình, logging
              │
              ▼
       Lắng nghe HTTP
              │
       readiness = false
              ▼
    Khởi tạo dữ liệu/dependencies
              │
              ▼
       readiness = true ────────────► Phục vụ request
              │                              │
              │                       Ghi log/metrics
              │                              │
              └──────── SIGTERM / stop ──────┘
                              │
                              ▼
                    readiness = false
                              │
                              ▼
                  Không nhận thêm việc mới
                              │
                              ▼
                 Chờ request in-flight / flush
                              │
                              ▼
                 Đóng server, executor, pool
                              │
                              ▼
                         EXIT JVM
```

**Logging** cho biết hệ thống đi qua những bước nào và gặp lỗi ở đâu. **Readiness** bảo vệ người dùng khỏi pod chưa sẵn sàng hoặc đang drain. **Shutdown** bảo vệ các công việc chưa hoàn thành khi phiên bản cũ được gỡ bỏ.

Một dịch vụ có thể có biến thể vòng đời khác — ví dụ batch worker không có HTTP server — nhưng vẫn cần xác định rõ lúc nào có thể nhận việc và khi nào phải ngừng nhận.

## 2. Logging không phải in ra màn hình tùy ý

`System.out.println(...)` có thể tiện để thử mã, nhưng thiếu quy ước về mức độ, nguồn sự kiện, ngữ cảnh, lỗi và cấu hình. Trong một hệ thống triển khai thực tế, log nên giúp trả lời:

1. **Sự kiện gì đã xảy ra?** Khởi động, tiếp nhận request, retry, lỗi dependency, bắt đầu drain...
2. **Khi nào?** Timestamp cùng múi giờ/định dạng nhất quán.
3. **Mức nghiêm trọng?** INFO, WARNING, SEVERE hoặc policy tương ứng.
4. **Sự kiện thuộc thành phần nào?** Logger name, service, environment, version, instance.
5. **Liên quan request/tác vụ nào?** Request ID, trace ID, transaction ID khi được phép ghi.
6. **Nguyên nhân lỗi?** Exception class, message đã lọc, stack trace khi thích hợp.

Ví dụ log có cấu trúc về mặt ý nghĩa:

```text
2026-11-27T10:00:00Z INFO  service.lifecycle instance=pod-a event=started
2026-11-27T10:00:03Z INFO  service.health    instance=pod-a ready=true
2026-11-27T10:05:00Z WARN  service.lifecycle instance=pod-a event=draining
2026-11-27T10:05:07Z INFO  service.lifecycle instance=pod-a event=stopped
```

Đây là **minh họa nội dung**, không phải định dạng mặc định của JUL. Khi triển khai thật, các trường nên được xuất bằng formatter/backend phù hợp để hệ thống thu thập log phân tích nhất quán.

## 3. Phân biệt System.Logger, JUL và logging framework

Trong Java 27, các lớp logging nền tảng sau vẫn có giá trị:

| Lựa chọn | API | Vai trò | Khi nào phù hợp |
| --- | --- | --- | --- |
| `System.Logger` | `System.getLogger(name)` | Facade logging cấp nền tảng; backend có thể do `LoggerFinder` quyết định | Thư viện hoặc thành phần muốn ít phụ thuộc cụ thể |
| JUL | `java.util.logging.Logger` | Logger, handlers, levels, formatters và cấu hình đi kèm JDK | Ứng dụng nhỏ, demo, module thuần JDK |
| SLF4J | API do thư viện bên ngoài cung cấp | Facade logging phổ biến trong hệ sinh thái | Ứng dụng dùng framework đã chuẩn hóa SLF4J |
| Logback/Log4j 2 | Backend do thư viện bên ngoài cung cấp | Appenders, filters, structured logging và tích hợp nền tảng | Khi cần chính sách logging nâng cao, theo cấu hình được kiểm chứng |

Các API bên ngoài JDK cần dependency và phiên bản tương thích; không nên thêm đồng thời nhiều **binding/backend** mà không hiểu kết quả điều hướng log. Cũng không nên gọi API nội bộ của JDK để thay thế cơ chế logging được công khai.

### 3.1. System.Logger tối giản

```java
public class LoggerApiExample {
    private static final System.Logger LOG =
            System.getLogger(LoggerApiExample.class.getName());

    public static void main(String[] args) {
        LOG.log(System.Logger.Level.INFO, "Ứng dụng bắt đầu");
        LOG.log(System.Logger.Level.WARNING, "Dữ liệu chưa được nạp đủ");
    }
}
```

`System.Logger` là API chuẩn. **Cách hiển thị, lọc và thu thập thực tế** phụ thuộc backend và môi trường chạy. Không mặc định rằng chỉ cần `System.Logger` là đã có JSON log, trace ID hay cơ chế rotation.

### 3.2. JUL tối giản

```java
import java.util.logging.Level;
import java.util.logging.Logger;

public class JulExample {
    private static final Logger LOG =
            Logger.getLogger(JulExample.class.getName());

    public static void main(String[] args) {
        LOG.info("Ứng dụng bắt đầu");
        LOG.log(Level.WARNING, "Không tìm thấy cấu hình tùy chọn");
    }
}
```

Trong JUL, `Logger` quyết định có phát bản ghi hay không, còn `Handler` quyết định bản ghi được gửi đi đâu. `Formatter` trình bày bản ghi. `ConsoleHandler` ghi ra **`System.err`** theo Javadoc; một số hệ thống dùng `System.out` cho application logs, nhưng container log collector thông thường có thể thu cả stdout và stderr.

## 4. Phân cấp mức log và chính sách môi trường

Mức log của JUL:

| Mức | Ý nghĩa gợi ý | Ví dụ |
| --- | --- | --- |
| `SEVERE` | Lỗi nghiêm trọng, thao tác/chức năng có thể thất bại | Không thể bind cổng HTTP |
| `WARNING` | Bất thường cần chú ý, có thể vẫn phục vụ | Dependency đang degraded |
| `INFO` | Sự kiện vận hành chính | Start, ready, drain, stop |
| `CONFIG` | Thông tin cấu hình đã lọc | Feature flags không nhạy cảm |
| `FINE` | Chi tiết chẩn đoán | Quyết định routing/branch |
| `FINER` / `FINEST` | Truy vết rất chi tiết | Điều tra ngắn hạn |
| `OFF` | Không phát bản ghi ở mức logger phù hợp | Trường hợp đặc biệt |
| `ALL` | Cho phép tất cả các mức qua bộ lọc phù hợp | Chẩn đoán có kiểm soát |

Một chính sách đơn giản:

- **Production:** ưu tiên INFO cho lifecycle, WARNING/SEVERE cho sự cố; chỉ bật FINE ở phạm vi hẹp khi điều tra.
- **Local/test:** cho phép log chi tiết hơn, nhưng không biến việc ghi dữ liệu nhạy cảm thành thói quen.
- **Health probe:** không log INFO cho **mỗi lần** kubelet gọi `/live` hay `/ready`; tần suất probe cao dễ làm log nhiễu.
- **Errors:** không log một exception thành stack trace ở mọi tầng xử lý; chọn nơi sở hữu lỗi để tránh bản ghi trùng lặp.

Log level không phản ánh trực tiếp HTTP status. Ví dụ một lỗi validate input trả HTTP 400 không nhất thiết phải là SEVERE, còn lỗi bind cổng khi khởi động thường xứng đáng log SEVERE.

## 5. Cấu hình JUL bằng logging.properties

Có thể đưa cấu hình logging ra ngoài source. Ví dụ tạo file `conf/logging.properties` **trong một ứng dụng minh họa**:

```properties
handlers=java.util.logging.ConsoleHandler

.level=INFO

java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

java.util.logging.SimpleFormatter.format=%1$tFT%1$tT%1$tz %4$s %3$s - %5$s%6$s%n
```

Chạy bằng JDK 27:

```bash
java -Djava.util.logging.config.file=conf/logging.properties JulExample
```

Giải thích:

- `handlers` khai báo `ConsoleHandler` ở root logger.
- `.level` đặt ngưỡng root logger.
- `ConsoleHandler.level` đặt ngưỡng cho chính handler; logger cho qua nhưng handler lọc vẫn có thể không xuất log.
- `java.util.logging.SimpleFormatter.format` quyết định định dạng văn bản; chuỗi `%1$t...` dùng các format arguments được `SimpleFormatter` công bố.
- Cờ `-D...` là system property truyền cho JVM, phải được đưa vào command line **trước tên main class**.

**Đây vẫn là plain-text logging**, không phải JSON logging. Khi cần các field có schema ổn định, dùng formatter/back-end hỗ trợ structured log thay vì tự nối một chuỗi trông giống JSON mà chưa escape ký tự đặc biệt.

### 5.1. Cấu hình log trước khi ứng dụng thực thi

Nên cấu hình logging **trước khi những module đầu tiên phát sinh log**, tránh mất thông tin startup hoặc tạo hai backend khác nhau. Với container, có thể truyền qua Java command line hoặc chính sách runtime của framework.

Không nên sửa toàn bộ root logger programmatically trong các thư viện dùng chung. Thư viện nên để **ứng dụng host** quyết định logging policy.

## 6. Logging vào stdout/stderr trong container

Trong môi trường Docker/Kubernetes, mẫu đơn giản và hiệu quả là:

```text
Java process
     │
     ├── application events ──► stdout/stderr
     │
     └── errors/stacktraces ──► stdout/stderr
                                  │
                                  ▼
                         Container log collection
                                  │
                                  ▼
                       Central logging / alerting
```

Ưu điểm: không cần ứng dụng tự xoay vòng file trong filesystem tạm, tích hợp được pipeline logs của nền tảng, giảm phụ thuộc vào đường dẫn máy chủ.

Tuy nhiên, ghi ra console **không tự bảo đảm log được lưu giữ lâu dài**. Kubernetes/cluster thường có chính sách retention, size limit và log aggregation riêng. Cần kiểm soát lượng log để tránh chiếm disk, CPU hoặc gây backpressure tới logging pipeline.

### 6.1. Tránh ghi thông tin nhạy cảm

Không ghi nguyên văn:

- Mật khẩu, token truy cập, API keys, cookies, Authorization headers.
- Toàn bộ request/response body chứa thông tin cá nhân hoặc dữ liệu thanh toán.
- Chuỗi kết nối có credentials.
- Stack trace kèm secrets bị nhúng vào error message từ hệ thống khác.

Với ID dùng để tương quan log, cần áp dụng chính sách phân loại dữ liệu và retention. Khi log dữ liệu đầu vào của người dùng, tránh để nội dung chứa newline/control characters phá bố cục log hoặc giả mạo các bản ghi khác (*log injection*); structured log formatter có escaping đáng tin cậy giúp giảm rủi ro này.

## 7. Structured logging và request correlation

Một sự kiện có thể chứa các trường:

```json
{
  "timestamp": "2026-11-27T10:05:00Z",
  "level": "INFO",
  "service": "orders",
  "event": "request_completed",
  "request_id": "req-42",
  "duration_ms": 84,
  "status": 200
}
```

Ví dụ JSON trên là **mẫu schema log**, không phải output mặc định từ JUL hoặc Java 27.

Các trường hữu ích:

- `service`, `environment`, `version`, `instance`.
- `trace_id`, `span_id`, `request_id` — nếu hệ thống tracing đã quy định.
- `event` hoặc `operation` có tên ổn định.
- `duration_ms`, `status`, `outcome` để phân tích thành công/thất bại.

Nếu dùng SLF4J MDC hoặc cơ chế tương đương, phải đảm bảo **đặt/xóa context đúng phạm vi** khi thread pool tái sử dụng worker. Với virtual threads, mỗi task có thread riêng nhưng dữ liệu `ThreadLocal` vẫn tốn bộ nhớ; các continuation/executor khác **không tự thừa hưởng mọi context**. Có thể truyền immutable request context một cách tường minh hoặc dùng cơ chế propagation của framework.

**Không dùng tên Thread hoặc carrier thread làm định danh nghiệp vụ**; request ID/trace ID mới là khóa tương quan bền vững.

## 8. Health check cần phân biệt liveness, readiness và startup

Kubernetes hỗ trợ ba loại probe:

| Probe | Câu hỏi | Khi thất bại theo ngưỡng | Nội dung nên kiểm tra |
| --- | --- | --- | --- |
| **Liveness** | Tiến trình còn ở trạng thái có thể tiến triển không? | Kubelet có thể khởi động lại container | Trạng thái nội bộ có ý nghĩa, kiểm tra nhanh |
| **Readiness** | Instance **bây giờ** có nên nhận lưu lượng mới không? | Pod/container bị đánh dấu không ready, loại khỏi lưu lượng Service phù hợp | Init hoàn tất, đang drain? phụ thuộc quan trọng dùng được? |
| **Startup** | Ứng dụng đã khởi tạo thành công chưa? | Container có thể bị restart nếu quá ngưỡng | Điều kiện khởi tạo thực sự có giới hạn thời gian |

Nếu có `startupProbe`, kubelet **chưa chạy liveness/readiness probes** cho tới khi startup probe thành công. Điều này có ích với ứng dụng nạp dữ liệu, khởi tạo cache hoặc thực hiện warmup tương đối lâu.

**Liveness không nên phụ thuộc vào một database bên ngoài đang gặp lỗi thoáng qua.** Nếu database bị mất kết nối khiến liveness fail ở mọi Pod, Kubernetes có thể khởi động lại hàng loạt instance, làm sự cố tồi hơn. Dấu hiệu dependency outage thường phù hợp với **readiness degraded** hơn là “process không còn sống”.

### 8.1. HTTP status cho health endpoints

Quy ước đơn giản:

```text
GET /live
  200 OK  → tiến trình đang phục vụ liveness
  503     → lỗi liveness nghiêm trọng nếu ứng dụng dùng cơ chế này

GET /ready
  200 OK  → sẵn sàng nhận request mới
  503     → chưa ready hoặc đang draining
```

Với Kubernetes HTTP probe, status **200–399** được coi là thành công; status ngoài dải đó là thất bại. Dùng 503 cho chưa sẵn sàng là một lựa chọn rõ ràng, nhưng đường dẫn `/live` và `/ready` **không phải tên do Java/JDK quy định**. Pod manifest phải trỏ đúng endpoint ứng dụng thực sự cung cấp.

### 8.2. Một endpoint /health cho tất cả có thể phản tác dụng

Nếu `/health` thất bại bất cứ khi nào database chậm, sau đó được dùng **đồng thời cho cả liveness và readiness**, một sự cố hạ tầng có thể khiến cả hệ thống liên tục restart.

Hãy xác định contract từng endpoint và mỗi phép probe. Một số framework cung cấp nhiều *health groups*; có thể dùng trực tiếp, không cần tự viết controller nếu framework đã hỗ trợ.

## 9. Health check phải nhanh, rẻ và ổn định

Một endpoint health chạy mỗi vài giây trên hàng trăm Pods có thể tạo lượng truy vấn bất ngờ nếu mọi lần gọi đều chạy:

```text
SELECT COUNT(*) FROM large_table;
```

Đây là ví dụ về **kiểm tra không phù hợp**: có thể tốn tài nguyên, giữ lock hoặc làm timeout, khiến chính probe gây thêm tải.

Thực tế tốt:

1. **Liveness:** chỉ kiểm tra điều kiện nội bộ tối thiểu, không truy vấn dependency tốn kém.
2. **Readiness:** chỉ xác nhận các dependency **bắt buộc** cho đường phục vụ chính; phân biệt thành phần tùy chọn/degraded.
3. Dùng **timeout nhỏ**, cache trạng thái trong khoảng ngắn hoặc background health monitor nếu cần.
4. Tránh gây hiệu ứng dây chuyền: khi database lỗi, mọi Pod không nhất thiết phải thất bại readiness nếu dịch vụ vẫn cung cấp được chức năng thiết yếu khác.
5. Nếu một probe phải trả JSON, tránh tiết lộ stack trace, cấu hình DB hoặc secrets.
6. Bảo đảm probe có khả năng trả lời **ngay cả dưới tải**, không bị chặn vô hạn sau các công việc nghiệp vụ.

Với liveness, “HTTP server còn trả 200” là kiểm tra cơ bản, **không chứng minh mọi worker và business logic còn khỏe**. Nếu ứng dụng có event loop/worker quan trọng dễ deadlock, cần thiết kế health signal phản ánh tình trạng đó nhưng vẫn rẻ và không phụ thuộc vào dịch vụ bên ngoài một cách cực đoan.

## 10. Readiness là trạng thái có chuyển đổi, không phải hằng số true

Một state machine hữu ích:

```text
STARTING
   │ initialization OK
   ▼
READY ───────────► DEGRADED / NOT_READY
   ▲                 │
   └── dependency phục hồi
   │
   └── SIGTERM ─────► DRAINING ───► STOPPED
                          │
                          └── từ chối việc mới
```

Các quy tắc cần xác định:

- Trong lúc startup, **readiness=false** cho tới khi các điều kiện nhận request hoàn tất.
- Sau khi sẵn sàng, readiness có thể **chuyển lại false** nếu mất năng lực phục vụ.
- Khi bắt đầu graceful shutdown, readiness cần **false ngay** và không chuyển true trở lại.
- Liveness có thể vẫn true trong giai đoạn draining khi process còn đang làm sạch; Kubernetes Pod termination đã có cơ chế riêng để loại endpoint khỏi lưu lượng.
- Khi listener đóng, endpoint sẽ không còn nhận yêu cầu.

Trạng thái nên cập nhật thread-safe. Với một cờ đơn giản, `AtomicBoolean` hoặc `volatile` là đủ để các thread khác quan sát thay đổi. Nếu có nhiều điều kiện liên quan, thiết kế một state machine hoặc snapshot nhất quán thay vì nhiều boolean có thể mâu thuẫn.

## 11. Graceful shutdown: thứ tự quan trọng hơn tên API

Khi được yêu cầu dừng có kiểm soát, ứng dụng nên làm theo thứ tự:

1. **Đánh dấu draining:** readiness trở thành false; phát log sự kiện một lần.
2. **Ngăn nhận thêm request/job mới:** listener hoặc message consumer không phát sinh công việc mới.
3. **Cho tác vụ đang chạy cơ hội kết thúc:** chờ có giới hạn.
4. **Giải quyết trạng thái nghiệp vụ:** commit/rollback đúng, ack message hoặc để hệ thống retry theo contract.
5. **Đóng tài nguyên phụ thuộc đúng thứ tự:** HTTP server/consumer, executor, DB pool, client, cache, telemetry exporters.
6. **Flush log/metrics khi được hỗ trợ**, nhưng không đợi vô hạn.
7. **Kết thúc tiến trình** trước khi nền tảng gửi kill cưỡng bức.

```text
SIGTERM
  │
  ▼
ready=false ───► stop accepting new work
                         │
                         ▼
                  wait in-flight (bounded)
                         │
                         ▼
                 close dependencies
                         │
                         ▼
                    process exits
```

Không phải mọi giao dịch đều có thể dừng giữa chừng một cách an toàn. Với công việc dài, cần deadline, cancellation, idempotency và cơ chế resume/retry theo mô hình nghiệp vụ.

**Graceful shutdown không bảo đảm tuyệt đối “không mất request”.** Mất mạng, crash, kernel OOM kill hoặc SIGKILL có thể xảy ra; hệ thống vẫn cần idempotency và timeout ở client.

## 12. Shutdown hook của JVM trong Java 27

Java hỗ trợ đăng ký một thread chạy khi JVM bắt đầu chu trình shutdown thông thường:

```java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> {
            System.err.println("Đang dọn dẹp tài nguyên");
        }, "shutdown-hook")
);
```

`Runtime.addShutdownHook` là API chuẩn đang được hỗ trợ. JVM có thể bắt đầu orderly shutdown do:

- `System.exit(...)` hoặc kết thúc tiến trình theo cách JVM xử lý thành orderly shutdown.
- Tín hiệu kết thúc mà runtime chuyển thành chu trình shutdown, ví dụ **SIGTERM trên cấu hình Linux thông thường**.
- Một số điều kiện khởi động shutdown khác được Javadoc mô tả.

**Không trông chờ shutdown hook khi tiến trình bị `SIGKILL`, bị kernel OOM kill hoặc bị hủy theo cách không có orderly shutdown.**

### 12.1. Những quy tắc của shutdown hooks

- Các hook được bắt đầu **không theo thứ tự đảm bảo**, có thể chạy **đồng thời**. Không tạo nhiều hook phụ thuộc vào thứ tự mà không có điều phối rõ.
- Không đăng ký/hủy đăng ký hook khi shutdown đã bắt đầu.
- Một hook có thể tạo thread mới, nhưng **không nên đợi vô hạn**, vì JVM chỉ kết thúc orderly shutdown sau khi các hooks hoàn tất.
- Trong hook, tránh gọi lại cơ chế chấm dứt dẫn tới vòng lặp; không sử dụng `Runtime.halt` như giải pháp graceful.
- Nên viết cleanup **idempotent**: nếu framework đã gọi stop trước, lần gọi trong hook không làm hỏng trạng thái.
- Các hook không phải công cụ transactional guarantee: nếu DB transaction hoặc publish message bị dở, phải xử lý theo business contract.

Thông thường **một owner duy nhất** chịu trách nhiệm dừng các thành phần theo thứ tự. Framework có lifecycle hooks riêng thì nên tích hợp vào cơ chế lifecycle đó, không vô tình tạo hai đường shutdown cùng đóng một resource.

## 13. Ví dụ Java 27 hoàn chỉnh: HTTP, health và shutdown

Chương trình `GracefulServiceDemo.java` dưới đây sử dụng **chỉ thư viện đi kèm JDK 27**:

- `HttpServer` ở module `jdk.httpserver` cung cấp `/live`, `/ready` và `/work`.
- `java.util.logging` ghi log startup, xử lý request và shutdown.
- `AtomicBoolean` lưu trạng thái readiness và bảo vệ việc dừng lặp.
- `Executors.newVirtualThreadPerTaskExecutor()` chạy mỗi HTTP handler task trên virtual thread.
- `Runtime.addShutdownHook` xử lý dừng có kiểm soát khi JVM nhận orderly shutdown.
- `HttpServer.stop(10)` **chờ handler đang hoạt động** tối đa khoảng 10 giây, sau đó đóng các kết nối còn lại.
- Executor được shutdown, rồi chờ tối đa 5 giây trước khi cố gắng interrupt task chưa kết thúc.

Ví dụ đặt `readiness=true` ngay sau khi HTTP listener bắt đầu vì không có dependency thật. Khi triển khai ứng dụng có database/cache, chỉ đặt true **sau khi** phần khởi tạo bắt buộc đã hoàn tất.

### 13.1. Mã nguồn

Tạo file `GracefulServiceDemo.java`:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class GracefulServiceDemo {

    private static final Logger LOG =
            Logger.getLogger(GracefulServiceDemo.class.getName());

    private static final AtomicBoolean READY = new AtomicBoolean(false);
    private static final AtomicBoolean STOPPING = new AtomicBoolean(false);

    private GracefulServiceDemo() {}

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("0.0.0.0", 8080), 64);

        ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor();
        server.setExecutor(executor);

        server.createContext("/live", exchange -> {
            try (exchange) {
                if (requireGet(exchange)) {
                    reply(exchange, 200, "alive\n");
                }
            }
        });

        server.createContext("/ready", exchange -> {
            try (exchange) {
                if (requireGet(exchange)) {
                    boolean ready = READY.get();
                    reply(exchange, ready ? 200 : 503,
                            ready ? "ready\n" : "not_ready\n");
                }
            }
        });

        server.createContext("/work", GracefulServiceDemo::work);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            if (!STOPPING.compareAndSet(false, true)) {
                return;
            }

            READY.set(false);
            LOG.info("Bắt đầu graceful shutdown: readiness=false");

            // Chặn kết nối/exchange mới, chờ handler đang chạy.
            // delay có đơn vị GIÂY, không phải milliseconds.
            server.stop(10);

            executor.shutdown();
            try {
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    LOG.warning("Executor chưa dừng; yêu cầu interrupt");
                    executor.shutdownNow();
                }
            } catch (InterruptedException interrupted) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            }

            LOG.info("Shutdown hook hoàn tất");
        }, "shutdown-hook"));

        server.start();
        READY.set(true);
        LOG.info("HTTP đang lắng nghe tại :8080; readiness=true");

        // Giữ main thread sống khi chạy như một service.
        // Khi JVM bắt đầu orderly shutdown, hook ở trên chạy.
        new CountDownLatch(1).await();
    }

    private static void work(HttpExchange exchange) {
        try (exchange) {
            if (!requireGet(exchange)) {
                return;
            }

            // Từ chối việc mới nếu bắt đầu draining.
            if (!READY.get()) {
                reply(exchange, 503, "draining\n");
                return;
            }

            LOG.info("Đã nhận /work, virtual="
                    + Thread.currentThread().isVirtual());

            try {
                Thread.sleep(2_000); // Mô phỏng một tác vụ I/O.
                reply(exchange, 200, "completed\n");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                LOG.warning("Tác vụ /work nhận interrupt");
                reply(exchange, 503, "interrupted\n");
            }
        } catch (IOException ioError) {
            LOG.log(Level.WARNING, "Không thể trả HTTP response", ioError);
        }
    }

    private static boolean requireGet(HttpExchange exchange)
            throws IOException {
        if ("GET".equals(exchange.getRequestMethod())) {
            return true;
        }

        exchange.getResponseHeaders().set("Allow", "GET");
        reply(exchange, 405, "method_not_allowed\n");
        return false;
    }

    private static void reply(HttpExchange exchange,
                              int status, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.getResponseHeaders().set(
                "Cache-Control", "no-store");

        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
        // HttpExchange implements AutoCloseable.
        // Các try-with-resources ở handler sẽ đóng exchange.
    }
}
```

### 13.2. Biên dịch và chạy

Vì `HttpServer` thuộc module `jdk.httpserver`, ví dụ trên classpath cần khai báo module:

```bash
javac --add-modules jdk.httpserver -encoding UTF-8 GracefulServiceDemo.java

java --add-modules jdk.httpserver GracefulServiceDemo
```

Ở terminal khác (nếu hệ điều hành có `curl`):

```bash
curl -i http://127.0.0.1:8080/live
curl -i http://127.0.0.1:8080/ready
curl -i http://127.0.0.1:8080/work
```

Các kết quả mong đợi khi ứng dụng đã sẵn sàng:

| Endpoint | HTTP status | Body | Ý nghĩa |
| --- | ---: | --- | --- |
| `GET /live` | 200 | `alive` | Liveness đơn giản |
| `GET /ready` | 200 | `ready` | Đã đánh dấu ready |
| `GET /work` | 200 | `completed` | Hoàn tất sau khoảng 2 giây |
| `POST /work` | 405 | `method_not_allowed` | Demo chỉ cho GET |

Đầu ra log phụ thuộc cấu hình JUL; nội dung được log khi nhận `/work` sẽ nêu `virtual=true` khi executor đang dùng virtual threads như cấu hình trên.

**Không dùng kết quả này như bằng chứng production-ready.** Máy chủ HTTP đi kèm JDK được dùng ở đây để làm rõ lifecycle. Ứng dụng production phải có timeout, giới hạn request size, giới hạn concurrency/downstream, security, TLS/proxy, metrics và nhiều cấu hình vận hành khác.

### 13.3. Gửi yêu cầu dừng

Trên hệ điều hành POSIX, từ một terminal khác có thể gửi:

```bash
kill -TERM <java-pid>
```

`<java-pid>` là placeholder. Một số terminal cũng có thể tạo tín hiệu dừng bằng `Ctrl+C`, tùy hệ điều hành và cách process được khởi chạy.

Khi JVM thực hiện orderly shutdown:

1. Hook đổi `READY` thành false.
2. Server dừng nhận exchange mới.
3. Các handler đang chạy có tối đa khoảng 10 giây để kết thúc qua `HttpServer.stop(10)`.
4. Executor được shutdown; có thêm khoảng chờ tối đa 5 giây cho việc hoàn tất.
5. JVM kết thúc khi shutdown hooks kết thúc.

**Trong bản demo**, `server.stop(10)` được gọi gần như ngay sau `READY=false`. Vì vậy không thể bảo đảm kubelet hoặc một client sẽ kịp quan sát HTTP 503 từ `/ready`: listener có thể đóng trước phép probe tiếp theo. Đây **không phải bug**; khi Pod được đánh dấu Terminating, Kubernetes cũng sẽ đánh dấu endpoint không còn ready ở tầng điều phối.

### 13.4. Những giới hạn cố ý của ví dụ

- `Thread.sleep(2_000)` chỉ mô phỏng blocking work, không tạo I/O thật.
- `CountDownLatch(1).await()` giữ main thread chờ; ví dụ không có UI hay lệnh admin để stop trực tiếp.
- `stop(10)` giới hạn thời gian chờ xử lý HTTP exchanges, **không bảo đảm** mọi tác vụ nghiệp vụ đã commit hoặc flush thành công.
- `executor.shutdownNow()` chỉ **cố gắng interrupt**, không dừng cưỡng bức native I/O hoặc task cố ý bỏ qua interruption.
- Nếu `IOException` xảy ra khi client đã đóng kết nối, log warning có thể xuất hiện; muốn production logging sạch hơn nên phân loại và đo những tình huống này.
- Demo không gắn business transaction, message queue hay framework lifecycle, nên không nên suy diễn có bảo đảm exactly-once.

## 14. Đặt thời hạn shutdown có ngân sách

Giả sử Kubernetes cho **30 giây** để dừng container:

```text
terminationGracePeriodSeconds = 30s
          │
          ├── nhận TERM và vào hook
          ├── mark draining / update readiness
          ├── chờ HTTP in-flight tối đa 10s
          ├── chờ executor tối đa 5s
          ├── cleanup telemetry/resources khác
          └── dự phòng thời gian cho scheduling/OS/container runtime
```

Không phân bổ đúng **30 giây cho một `awaitTermination` duy nhất** nếu sau đó vẫn còn nhiều cleanup stages. Thời hạn tính từ lúc Pod bắt đầu quá trình terminating, còn bao gồm thời gian `preStop` (nếu có) và chi phí overhead khác.

Mô hình tổng:

```text
T_grace >= T_preStop + T_drain + T_close_dependencies + T_flush + T_margin
```

Đây là **bất đẳng thức lập kế hoạch**, không phải một API Kubernetes tự đảm bảo. Một giai đoạn thực tế có thể hết sớm hoặc bị mắc kẹt; cần timeout riêng cho các thao tác phụ thuộc.

### 14.1. Nếu graceful deadline không đủ

Khi hết thời gian, container runtime/kubelet có thể gửi `SIGKILL`. JVM không được bảo đảm chạy thêm bất kỳ hook nào, kể cả flush log hoặc rollback.

Hãy kiểm tra những trường hợp:

- HTTP request dài hơn deadline.
- DB transaction bị deadlock hoặc query timeout.
- Queue consumer đang xử lý message chưa ack.
- Log exporter bị treo trong lúc flush.
- Client giữ keep-alive/streaming response nhiều phút.
- Framework listener đang dừng và bị block bởi một thread không phản hồi interrupt.

Đối với job dài, có thể phải **ngừng lấy job mới**, chờ job đang chạy đến checkpoint, rồi để hệ thống xử lý retry khi process bị kill. Không nên tăng grace period vô hạn thay cho thiết kế idempotent job processing.

## 15. Kubernetes probes: cấu hình tương ứng với Java service

Một ví dụ **Deployment rút gọn nhưng có đủ cấu trúc cốt lõi**:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java27-graceful-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: java27-graceful-demo
  template:
    metadata:
      labels:
        app: java27-graceful-demo
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: app
          image: registry.example.invalid/java27-graceful-demo:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /ready
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /live
              port: http
            periodSeconds: 10
            timeoutSeconds: 1
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 1
            failureThreshold: 2
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              memory: "512Mi"
```

**Thay image bằng artifact thực tế đã xây và kiểm chứng.** `registry.example.invalid/...` cố ý là placeholder, không phải registry có thể pull. Các giá trị request/limit và probe timings chỉ để minh họa; cần đo tải và thời gian startup thực tế.

Giải thích:

- `startupProbe` trỏ `/ready` để cho ứng dụng một **khoảng khởi động**: chỉ khi ứng dụng đã sẵn sàng thì liveness/readiness định kỳ mới bắt đầu. Trong demo, READY được bật nhanh sau khi `server.start()`.
- `livenessProbe` trỏ `/live`, không chạm database hay các dependency ngoài.
- `readinessProbe` trỏ `/ready`, giúp Service loại instance chưa ready khỏi lưu lượng mới.
- `terminationGracePeriodSeconds: 30` cung cấp thời gian cho shutdown path, không bảo đảm mọi cleanup hoàn tất nếu block vô hạn.
- `replicas: 2` là cấu hình ví dụ; actual rollout availability còn phụ thuộc resource capacity, Service routing, termination behavior và deployment strategy.

### 15.1. Độ nhạy probe cần được cân bằng

Các cờ quan trọng:

| Trường | Tác dụng |
| --- | --- |
| `periodSeconds` | Khoảng thời gian thông thường giữa probes |
| `timeoutSeconds` | Khoảng chờ tối đa một phép probe |
| `failureThreshold` | Số lần thất bại liên tiếp trước khi action |
| `successThreshold` | Số lần thành công cần thiết; liveness/startup yêu cầu bằng 1 |
| `initialDelaySeconds` | Delay đầu tiên nếu có nhu cầu |
| `terminationGracePeriodSeconds` | Quỹ thời gian dừng cấp Pod hoặc, với quy tắc hỗ trợ, cấp liveness/startup probe |

Nếu `timeoutSeconds` quá ngắn so với scheduler latency hoặc network path thực tế, probe có thể thất bại giả dưới tải. Nếu `periodSeconds` quá dày và liveness dựa vào dependency ngoài, cluster có thể restart nhiều instance trong một outage.

**Readiness failure không có nghĩa tự động restart container.** Nó chủ yếu khiến Pod không nhận traffic từ các Service phù hợp. **Liveness/startup failure sau ngưỡng** mới dẫn tới hành động restart theo chính sách Pod.

### 15.2. Không cần preStop chỉ để có graceful SIGTERM

Kubernetes thực hiện Pod termination và sẽ đánh dấu các endpoint đang terminating không ready để giảm điều hướng lưu lượng. Hook `preStop` là lựa chọn bổ sung khi có lý do vận hành cụ thể — ví dụ một hệ thống ingress/load balancer bên ngoài cần bước deregister riêng — chứ không phải thành phần bắt buộc của mọi Java service.

Nếu dùng `preStop`:

- Hook thường chạy **trước khi TERM được gửi** cho process.
- **Grace countdown đã bắt đầu trước khi hook chạy**; một hook chờ 20 giây có thể dùng gần hết ngân sách shutdown.
- Không khai báo thêm một endpoint `/drain` công khai không có xác thực chỉ để gọi từ `preStop`; kẻ ngoài có thể lợi dụng làm instance ngừng phục vụ.
- Nếu hệ thống cần proactive drain trước SIGTERM, thiết kế endpoint/lifecycle có kiểm soát và kiểm thử đồng bộ với load balancer.

## 16. Tại sao Docker PID 1 và ENTRYPOINT ảnh hưởng shutdown?

Trong container, process nhận tín hiệu dừng thường là **PID 1** của container (hoặc init process phù hợp). Nếu chạy Java qua một shell wrapper không truyền signal đúng:

```text
container PID 1:  /bin/sh -c "java -jar app.jar"
                     │
                     └─► Java child process
```

Java child có thể **không nhận đúng TERM**, khiến shutdown hook không được chạy như mong đợi. Vì vậy với một Java process chính, thường nên dùng **exec-form ENTRYPOINT**:

```dockerfile
# Đoạn ví dụ trong một Dockerfile, dùng image JDK/JRE 27 đã kiểm chứng.
# base image và đường dẫn JAR cần thay theo môi trường thật.
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Nếu cần wrapper script, script thường nên dùng `exec java ...` ở bước cuối để thay thế shell process bằng Java process. Không chọn shell-form ENTRYPOINT chỉ vì cú pháp ngắn hơn khi hệ thống dựa vào SIGTERM để drain.

### 16.1. Chạy module jdk.httpserver trong runtime image tối giản

Demo dùng `com.sun.net.httpserver.HttpServer`. Nếu đóng gói bằng `jlink` hoặc runtime image tùy chỉnh, cần đảm bảo image **thực sự chứa module `jdk.httpserver`**; nếu không, `--add-modules jdk.httpserver` sẽ không thể resolve module.

Với ứng dụng explicit JPMS, module descriptor có thể khai báo:

```java
module com.example.service {
    requires java.logging;
    requires jdk.httpserver;
}
```

Đây là **fragment descriptor cho trường hợp modularize ứng dụng**. Chương trình classpath ở mục 13 không có `module-info.java` nên dùng `--add-modules jdk.httpserver` trong lệnh chạy.

Với image đã đóng JAR và có Main-Class, command có thể là `java -jar app.jar`; nhưng ví dụ một file `GracefulServiceDemo.class` chưa tự có JAR manifest. Không tự hoán đổi hai kiểu khởi chạy mà bỏ qua quy trình đóng gói.

## 17. Xử lý việc đang chạy: HTTP khác queue worker

Một HTTP request có response đồng bộ có vòng đời tương đối rõ. Một queue consumer có nghiệp vụ khác: **message được ack trước hay sau xử lý?** Nếu shutdown giữa chừng, message có thể được gửi lại.

### 17.1. HTTP request in-flight

Các bước hợp lý:

- Ngừng nhận request mới khi draining.
- Chờ số request in-flight giảm về 0 trong deadline.
- Đối với request vượt hạn, trả lỗi/đóng kết nối theo contract server; client có thể retry.
- Đặt timeout cho database, HTTP client và các thao tác I/O bên dưới để tránh hook bị chặn vô hạn.

Một HTTP response đã gửi tới client **không thể bị rollback** chỉ bằng cách hủy virtual thread. Nên phân biệt giữa việc client chưa nhận được response và nghiệp vụ phía server đã commit.

### 17.2. Message consumer

Đối với worker đọc hàng đợi:

1. Ngừng poll/fetch message mới.
2. Cho các message đang xử lý cơ hội hoàn tất.
3. Commit transaction rồi **ack theo contract của broker** (hoặc thiết kế transaction coordination phù hợp).
4. Nếu chưa hoàn tất, đừng ack “cho sạch queue”; để redelivery và idempotent handler xử lý.
5. Đóng consumer/producer/client một cách có thứ tự.

**At-least-once delivery** có thể tạo xử lý lặp. Graceful shutdown giảm số request/message dở dang nhưng không thay thế business idempotency. Không dùng `finally { ack(); }` vô điều kiện nếu lỗi giữa transaction phải để message retry.

## 18. Quản lý ExecutorService khi dừng

`ExecutorService` trong Java 27 có `shutdown()`, `shutdownNow()`, `awaitTermination(...)` và `close()`.

| Phương thức | Hợp đồng khái quát | Ghi chú |
| --- | --- | --- |
| `shutdown()` | Không nhận task mới, cho task đã nhận cơ hội chạy xong | Không chờ |
| `awaitTermination(timeout, unit)` | Chờ executor đạt trạng thái terminated tối đa một khoảng | Trả boolean |
| `shutdownNow()` | Cố gắng ngắt tasks đang chạy, trả tasks chưa bắt đầu | Không bảo đảm tasks dừng ngay |
| `close()` | Shutdown có trật tự rồi chờ kết thúc | **Không cung cấp timeout giới hạn chờ** riêng |

Trong một request scope hữu hạn, `try (var executor = ...)` có thể rất tiện. Nhưng trong **shutdown hook có deadline**, không nên gọi `close()` rồi giả định nó không chờ lâu: task có thể treo I/O hoặc bỏ qua interruption.

Mẫu chờ có giới hạn:

```java
executor.shutdown();

try {
    if (!executor.awaitTermination(5, java.util.concurrent.TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException interrupted) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là **fragment bên trong lifecycle owner có biến `executor`**, không phải file Java độc lập. Sau `shutdownNow()`, cũng không có bảo đảm task đã kết thúc ngay; nếu cần xử lý sâu hơn, có thể thêm **một thời hạn tổng** và quan sát số task còn lại, không chờ vô hạn.

### 18.1. Virtual threads không làm shutdown tự động “an toàn”

Virtual threads nhẹ khi chờ I/O, nhưng:

- Task có thể giữ DB connection hoặc file descriptors.
- Task có thể chứa transaction chưa commit.
- Một số blocking operation không phản hồi interrupt ngay.
- Hàng nghìn task vẫn có state và dữ liệu giữ trên heap.
- Việc đặt `Future.cancel(true)` chỉ gửi yêu cầu hủy theo khả năng hỗ trợ của task.

Do đó shutdown cần **backpressure, bounded in-flight work, timeout I/O và cleanup** giống như với platform threads.

## 19. Logging trong quá trình dừng: cần đủ, không được kéo dài vô hạn

Những sự kiện nên có log ở mức INFO/WARNING phù hợp:

```text
shutdown_requested
readiness_set_false
listener_stopped
inflight_wait_timeout
executor_forced_shutdown
database_pool_closed
shutdown_completed
```

Đừng log stack trace trên mỗi request bị ngắt do drain nếu đó là hành vi dự kiến, nhưng cũng đừng nuốt mọi lỗi cleanup. Một số lỗi có thể cần WARNING cùng mã nguyên nhân.

Nếu ứng dụng có exporter log/metrics gửi qua mạng, cần:

- Ưu tiên flush **trong deadline tổng**.
- Không để exporter treo khiến JVM bỏ lỡ grace period.
- Không kỳ vọng log cuối luôn được gửi thành công khi container bị SIGKILL.
- Giữ metrics chủ yếu phục vụ monitoring, không phụ thuộc vào `System.out.flush()` để tạo khả năng quan sát hoàn chỉnh.

Ở môi trường nhiều replicas, correlation ID và instance identity giúp liên kết log request trước/sau một lần rollout.

## 20. Quan sát readiness và shutdown bằng metrics

Các metrics hữu ích:

| Metric/đại lượng | Tại sao cần |
| --- | --- |
| Current readiness state | Thấy instance nào đang nhận traffic |
| In-flight request count | Kiểm tra drain có tiến triển không |
| Request duration histogram | Chọn thời hạn drain đủ cho tail latency |
| HTTP response errors / timeout | Phát hiện client bị lỗi trong rollout |
| Queue consumer in-flight/lag | Chọn thời điểm ngừng nhận/ack message |
| Graceful shutdown duration | Xem khoảng thực tế so với grace |
| Forced shutdown/cancellation count | Tìm những tác vụ thường vượt thời hạn |
| Dependency availability/latency | Xác định readiness phụ thuộc điều gì |
| Container restart/OOMKilled count | Phân biệt shutdown dự kiến với crash |
| Log exporter errors/drops | Không suy từ thiếu log thành “không có sự kiện” |

Với virtual threads, **số lượng thread hiện diện** không phải thước đo duy nhất của sức khỏe; cần nhìn lượng in-flight data, connection pool, hàng đợi và memory. Đôi khi một endpoint `/live` vẫn trả 200 nhưng throughput đã suy giảm do downstream chậm hoặc saturation.

## 21. Các tình huống kiểm thử quan trọng

Trước khi tuyên bố graceful deployment hoạt động, kiểm tra **trên cùng cách đóng gói và chạy** sẽ dùng ở production:

| Tình huống | Kỳ vọng |
| --- | --- |
| Ứng dụng vừa start, chưa warmup xong | Readiness 503; liveness/startup theo contract đã chọn |
| Startup hoàn thành | Readiness chuyển 200 |
| Dependency bắt buộc tạm mất | Readiness phản ánh đúng policy; không gây restart storm do liveness |
| Dependency phục hồi | Readiness trở lại 200 nếu chưa draining |
| Endpoint health gọi dày | Không gây DB query nặng/log flood |
| Nhận SIGTERM lúc idle | Listener dừng, tài nguyên đóng, process kết thúc trong deadline |
| Nhận SIGTERM khi `/work` đang chạy | Request trong hạn có cơ hội hoàn tất, task mới bị từ chối |
| Request chạy dài hơn deadline | Có timeout/cancel/error path rõ, không đợi vô hạn |
| SIGKILL hoặc OOM kill | Không trông chờ hook; downstream vẫn nhất quán nhờ retry/idempotency |
| Dừng lặp hoặc lifecycle gọi stop nhiều lần | Không double-close làm crash/chặn vô hạn |
| Log exporter bị lỗi | Shutdown vẫn hữu hạn, lỗi log được xử lý theo policy |
| Một Pod đang Terminating khi rollout | Endpoint không nhận regular traffic; capacity Pod khác vẫn đủ |
| Queue worker dừng giữa transaction | Không ack sai; redelivery/recovery hoạt động |
| Lỗi trong cleanup | Lỗi được ghi nhận, không làm mất nguyên nhân quan trọng |

**Bài demo chỉ mô phỏng** một vài tình huống, nên những mục có database, broker, rollout thực tế cần integration tests bổ sung tương ứng với stack production.

### 21.1. Cách tự kiểm tra demo bằng terminal

Khi demo ở mục 13 đang chạy:

1. Gọi `curl -i http://127.0.0.1:8080/live` và `/ready`.
2. Gọi `/work` rồi gửi tín hiệu TERM trong lúc request đang đợi 2 giây.
3. Quan sát log `readiness=false`, thời gian `server.stop(10)` chờ và trạng thái client.
4. Thử nhiều request đồng thời, trong đó một số request lâu hơn giới hạn drain (với biến thể demo đã thay thời lượng) để xem hành vi timeout.
5. Xác nhận tiến trình thoát và cổng được giải phóng.

Không coi kiểm thử chỉ bằng `Ctrl+C` trên máy phát triển là đủ để xác minh semantics của Docker/Kubernetes; signal forwarding, PID 1, kubelet và ingress routing có thể khác.

## 22. Những lỗi thiết kế thường gặp

| Sai lầm | Vấn đề | Cách phù hợp |
| --- | --- | --- |
| Chỉ dùng `System.out.println` cho mọi sự kiện | Không có log level/policy/context | Dùng logging API và configuration rõ |
| Log mỗi health probe ở INFO | Log flood do kubelet gọi định kỳ | Chỉ log khi trạng thái đổi hoặc debug giới hạn |
| Ghi token/password/header nhạy cảm | Rò rỉ dữ liệu | Lọc/sanitize trước khi log |
| Coi JUL `SimpleFormatter` tạo JSON log | Chỉ định dạng plain text | Dùng structured logging formatter/backend |
| Coi `System.Logger` luôn dùng một backend cố định | Provider có thể được thay | Kiểm tra logging runtime thực tế |
| Dùng cùng `/health` kiểm tra DB cho liveness/readiness | Có thể restart storm khi DB outage | Tách health semantics |
| Gắn liveness vào dependency ngoài | Restart không sửa được dependency | Liveness tập trung tiến trình |
| Readiness luôn true kể cả đang drain | Pod có thể tiếp tục nhận request | Đổi false khi bắt đầu shutdown |
| Startup kéo dài nhưng không có startup probe | Liveness có thể restart trước warmup | Cấu hình startup window |
| Truy vấn DB nặng trong mỗi health check | Probe tự tạo tải | Dùng check nhẹ, timeout/cache |
| Coi readiness failure là yêu cầu restart | Nhầm với liveness | Phân biệt action của kubelet |
| Gọi `server.stop(0)` cho mọi deploy | Có thể cắt ngang in-flight requests | Chọn bounded drain delay phù hợp |
| Quên đóng HTTP exchanges/streams | Rò rỉ kết nối/tài nguyên | `try-with-resources`, đóng exchange |
| Gọi `executor.close()` trong hook mà không kiểm soát task treo | Có thể vượt grace deadline | `shutdown/awaitTermination/shutdownNow` với timeout |
| Nghĩ `shutdownNow()` dừng task tức thì | Interruption mang tính hợp tác | Timeout ở I/O và cancel-aware code |
| Đăng ký nhiều hook phụ thuộc thứ tự | Hook có thể chạy đồng thời | Lifecycle owner điều phối |
| Dùng shell-form ENTRYPOINT không chuyển signal | Java không nhận TERM đúng cách | Exec-form hoặc wrapper dùng `exec` |
| Chờ hook hoạt động khi SIGKILL/OOMKilled | Không có orderly shutdown | Idempotency, retry, crash recovery |
| Đặt `preStop` sleep gần hết grace time | Không còn thời gian drain/cleanup | Lập ngân sách chung, chỉ dùng khi có lý do |
| Dùng public `/drain` không bảo vệ | Người ngoài có thể dừng traffic của instance | Authentication/authorization/internal control |
| Ack queue message dù task thất bại | Mất công việc hoặc sai trạng thái | Chỉ ack khi business step hoàn tất |
| Đóng DB pool trước khi requests đang chạy xong | In-flight requests thất bại | Dừng nhận việc, chờ, sau đó mới đóng dependency |
| Tin health=200 nghĩa toàn bộ service không có lỗi | Probe có phạm vi hẹp | Theo dõi thêm SLI/metrics/traces |
| Không thử rollover/termination thật | Lỗi chỉ lộ khi triển khai | Chaos/integration tests với SIGTERM/Pod deletion |

## 23. Checklist khi đưa Java 27 service lên production

1. **Phân biệt startup, ready và alive chưa?** Mỗi trạng thái có contract rõ.
2. **Các endpoint health có trả nhanh không?** Không truy vấn nặng hoặc tiết lộ secrets.
3. **Probe paths/ports trong manifest khớp ứng dụng chưa?**
4. **Liveness có tránh dependency ngoài gây restart storm không?**
5. **Readiness có trở thành false khi chưa sẵn sàng và đang shutdown không?**
6. **Signal TERM có đến được Java process không?** Xác nhận PID 1 và ENTRYPOINT.
7. **Shutdown hook/lifecycle chỉ có một owner điều phối không?**
8. **Ngừng nhận việc mới trước khi đóng dependencies chưa?**
9. **Thời hạn drain có căn cứ từ tail latency và workload không?**
10. **Grace period tính cả preStop và cleanup chưa?**
11. **HTTP, executor, database pool, broker, telemetry exporter đóng đúng thứ tự chưa?**
12. **Có timeout thật ở network/database/broker không?**
13. **Có idempotency/retry cho trường hợp SIGKILL hoặc mất response không?**
14. **Logging level và output stdout/stderr được cấu hình đúng chưa?**
15. **Có correlation ID/trace ID nếu cần không?** Và không log dữ liệu nhạy cảm?
16. **Có metrics in-flight, shutdown duration và forced cancellation không?**
17. **Custom runtime image có đủ module JDK cần dùng không?**
18. **Framework có lifecycle hook riêng không?** Tránh tự đăng ký shutdown hai lần cho cùng resource.
19. **Đã thử tải rồi xóa Pod khi còn in-flight requests chưa?**
20. **Đã kiểm tra endpoint routing khi rollout nhiều replicas chưa?**
21. **Có chính sách retention của logs, metrics, traces không?**
22. **Đã thử các đường lỗi khó: dependency outage, OOM kill, SIGKILL, cleanup failure chưa?**

**Ghi nhớ:** Trong Java 27, **logging** giúp quan sát, **health checks** điều phối lưu lượng và quyết định restart, còn **graceful shutdown** bảo vệ các tác vụ đang chạy khi deployment thay đổi. Ba cơ chế chỉ có ý nghĩa khi chúng chia sẻ một lifecycle nhất quán và có **deadline**. Khi không thể hoàn tất trong deadline, hệ thống phải có **khả năng retry/idempotency** chứ không chỉ trông chờ vào shutdown hook.

## 24. Tài liệu tham khảo chính thức và liên quan

### 24.1. Java SE 27 / JDK 27

- [`System.Logger` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.Logger.html): logging facade của nền tảng Java.
- [`java.util.logging.Logger` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.logging/java/util/logging/Logger.html): log levels, logger hierarchy và phát log records.
- [`ConsoleHandler` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.logging/java/util/logging/ConsoleHandler.html): ghi log ra `System.err` và cấu hình handler.
- [`SimpleFormatter` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.logging/java/util/logging/SimpleFormatter.html): text log format và `java.util.logging.SimpleFormatter.format`.
- [`LogManager` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.logging/java/util/logging/LogManager.html): cấu hình JUL bằng file properties.
- [`Runtime.addShutdownHook` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runtime.html#addShutdownHook(java.lang.Thread)): chu trình orderly shutdown và hạn chế shutdown hooks.
- [`HttpServer` — Java SE 27 API, module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `setExecutor`, `start`, `stop(int delay)`.
- [`HttpExchange` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): HTTP response, `sendResponseHeaders`, đóng exchange/streams.
- [`ExecutorService` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle, shutdown và `awaitTermination`.
- [`Executors` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor`.

### 24.2. Container và điều phối triển khai

- [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/): các loại probe và ảnh hưởng đến restart/routing.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): cấu hình HTTP probes và ngưỡng đánh giá.
- [Kubernetes — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/): grace period, preStop, TERM/KILL và EndpointSlice terminating state.
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): quy tắc gọi preStop, thời gian và termination signal.
- [Docker — Dockerfile reference: ENTRYPOINT](https://docs.docker.com/reference/dockerfile/#entrypoint): exec-form và shell-form, tác động tới signal forwarding.
