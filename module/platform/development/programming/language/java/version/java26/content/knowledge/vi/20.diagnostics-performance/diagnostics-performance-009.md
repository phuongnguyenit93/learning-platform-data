# Giới hạn dữ liệu nhạy cảm trong log và bản ghi chẩn đoán

Log, Java Flight Recorder (JFR), thread dump, heap dump và fatal error log giúp tìm lỗi và phân tích hiệu năng. Nhưng các artifact này có thể chứa dữ liệu người dùng, thông tin xác thực, địa chỉ mạng, câu lệnh SQL, đường dẫn file, tên thread hoặc trạng thái nội bộ của ứng dụng. Khi gửi chúng tới hệ thống log tập trung, đội hỗ trợ hoặc nhà cung cấp, dữ liệu chẩn đoán có thể trở thành một kênh rò rỉ thông tin.

Trong phạm vi module JAVA_VERSION_JAVA26, nội dung này bổ sung lớp vận hành an toàn cho các cải tiến HTTP, pattern matching, structured concurrency, Vector API, bảo mật và tối ưu JVM: khi đo hiệu năng hoặc điều tra lỗi của các thành phần đó, dữ liệu thu được vẫn phải được giới hạn theo mục đích.

Nguyên tắc quan trọng là **giới hạn dữ liệu ngay khi tạo bản ghi**. Chỉ thu thập trường thật sự cần cho câu hỏi chẩn đoán, tránh ghi raw request/response và secret, đặt thời hạn lưu trữ, giới hạn người có quyền đọc. JFR cung cấp các cơ chế bật/tắt event, giới hạn stack trace, giới hạn kích thước/thời gian recording và lọc event bằng `jfr scrub`; các cơ chế đó giúp giảm dữ liệu nhưng không tự động che mọi giá trị nhạy cảm trong một field tùy ý.

Java 26 có các API logging và JFR ổn định. Không có preview/incubator feature cần bật cho các ví dụ trong bài. JDK 26 cũng không tự động redacts mọi password, token hay PII trong log ứng dụng hoặc JFR custom event; thiết kế event và chính sách vận hành của ứng dụng vẫn quyết định dữ liệu nào được ghi. [Java 26 `Logger`](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html) · [Java 26 JFR `Event`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html) · [JDK 26 `jfr` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html).

## 1. Phân loại các loại dữ liệu chẩn đoán

Không phải mọi bản ghi đều có cùng mức rủi ro. Trước khi bật log hoặc tạo recording, xác định dữ liệu nào có thể xuất hiện trong từng artifact.

| Artifact | Nội dung thường có | Rủi ro cần kiểm soát |
|---|---|---|
| Application log | Message, exception, request ID, user ID, URL, header, SQL, dữ liệu nghiệp vụ. | Token, password, PII, payload, thông tin thanh toán hoặc dữ liệu tenant có thể bị ghi nguyên văn. |
| JVM unified log (`-Xlog`) | GC, safepoint, class loading, JIT, container, runtime subsystem và đường dẫn file. | Log mức `debug`/`trace` có thể tiết lộ cấu trúc runtime, tên class, đường dẫn, cấu hình hoặc thông tin môi trường. |
| JFR recording (`.jfr`) | Event runtime, thread samples, stack trace, I/O metadata, custom event fields, heap statistics. | Custom fields có thể chứa dữ liệu ứng dụng; event hệ thống có thể tiết lộ host, file path, thread name hoặc property. |
| Thread dump | Thread name, trạng thái, stack trace, monitor/lock và thông tin chờ. | Thread name có thể nhúng ID, tenant hoặc URL; stack trace tiết lộ class, method và call path nội bộ. |
| Heap dump | Object graph, String, byte array, collection, object đang được giữ trong heap. | Có thể chứa access token, session, password tạm thời, dữ liệu cá nhân và nội dung request chưa được giải phóng. |
| Fatal error log (`hs_err_pid*.log`) | Thông tin JVM, thread, stack, native frames, command line và môi trường tùy phiên bản/nền tảng. | `-XX:+ExtensiveErrorReports` có thể ghi thêm thông tin nhạy cảm; file lỗi cần được bảo vệ như artifact nội bộ. |
| Security/debug trace | TLS, Kerberos, JAAS, PKIX, OCSP, provider và quá trình xác thực. | Có thể chứa dữ liệu giao thức, địa chỉ, byte dump hoặc thông tin cấu hình bảo mật. |

Một phân loại thực tế:

- **Có thể ghi rộng:** mã sự kiện, kết quả thành công/thất bại, thời lượng, phiên bản ứng dụng, correlation ID ngẫu nhiên.
- **Chỉ ghi sau khi giảm định danh:** tenant reference, account reference, tên dịch vụ, hostname hoặc đường dẫn đã chuẩn hóa.
- **Không ghi vào log/JFR thông thường:** password, access/refresh token, session cookie, Authorization header, private key, secret key, OTP, dữ liệu thẻ thanh toán, request/response body có PII, thông tin đăng nhập database.
- **Chỉ thu thập trong điều tra có kiểm soát:** heap dump, security debug trace chi tiết, profile có stack trace sâu, dữ liệu GC roots và fatal error report mở rộng.

Việc một trường không được xem là secret vẫn có thể làm lộ dữ liệu cá nhân hoặc kiến trúc nội bộ. IP, email, tên thread, tenant ID, URL query và tên file đều có thể nhạy cảm theo ngữ cảnh.

## 2. Thiết kế application log theo allow-list

Application log nên mô tả **sự kiện đã xảy ra**, không sao chép toàn bộ đối tượng đầu vào. Hãy tạo một schema log có các trường cho phép và chỉ ghi những trường đó.

Ví dụ log một lần xác thực thanh toán:

```text
event=payment.authorization
requestId=6e17a7f4-5e90-4a42-bb50-8e31c1b7a921
result=DECLINED
reasonCode=ISSUER_UNAVAILABLE
durationMs=184
```

Các trường này đủ để tìm request tương ứng, thống kê lỗi và đo thời gian. Không cần ghi:

```text
Authorization: Bearer eyJ...
Cookie: SESSION=...
cardNumber=...
cvv=...
requestBody={...}
```

### Ví dụ với `java.util.logging`

```java
import java.util.UUID;
import java.util.logging.Level;
import java.util.logging.Logger;

final class PaymentService {
    private static final Logger LOG =
            Logger.getLogger(PaymentService.class.getName());

    void authorize(PaymentCommand command) {
        // Sinh correlation ID ngẫu nhiên; không dùng email hoặc token làm ID.
        String requestId = UUID.randomUUID().toString();
        long started = System.nanoTime();

        try {
            AuthorizationResult result = performAuthorization(command);
            long durationMs = (System.nanoTime() - started) / 1_000_000;

            LOG.log(Level.INFO,
                    "event=payment.authorization requestId={0} result={1} durationMs={2}",
                    new Object[]{requestId, result.code(), durationMs});
        } catch (PaymentGatewayException failure) {
            long durationMs = (System.nanoTime() - started) / 1_000_000;

            // Không ghi nguyên exception message nếu message có thể chứa URL,
            // header hoặc payload từ gateway.
            LOG.log(Level.WARNING,
                    "event=payment.authorization requestId={0} result=ERROR "
                            + "causeType={1} durationMs={2}",
                    new Object[]{requestId,
                            failure.getClass().getSimpleName(), durationMs});

            // Nếu cần stack trace/payload để điều tra, gửi vào kênh sự cố riêng
            // có quyền truy cập và thời hạn lưu trữ chặt hơn.
        }
    }

    private AuthorizationResult performAuthorization(PaymentCommand command)
            throws PaymentGatewayException {
        throw new UnsupportedOperationException("Example only");
    }
}
```

Ví dụ dùng `requestId` ngẫu nhiên để liên kết các log record trong cùng một request. Không tạo correlation ID bằng cách hash email, số điện thoại hoặc account number rồi coi đó là ẩn danh: giá trị có không gian đoán nhỏ vẫn có thể bị dò ngược. Nếu cần liên kết ổn định giữa các hệ thống, dùng một mã tham chiếu ngẫu nhiên hoặc pseudonym được tạo bằng cơ chế có khóa và quản lý khóa riêng.

### Tránh `toString()` và exception message không kiểm soát

Không ghi trực tiếp các đối tượng có thể chứa secret:

```java
// Không nên: toString() có thể in mọi field của request.
LOG.info("incoming request=" + request);

// Không nên: exception message có thể chứa URL, SQL hoặc response body.
LOG.log(Level.WARNING, "request failed", exception);
```

Hãy tạo thông điệp an toàn bằng các trường đã chọn. Với lỗi cần stack trace, phân loại exception và quyết định rõ nơi được phép nhận stack trace. Đừng giả định rằng mọi thư viện đều loại bỏ token khỏi exception message.

### Filter và Formatter không phải lớp bảo vệ duy nhất

`java.util.logging.Logger` kiểm tra log level trước, tạo `LogRecord`, gọi `Filter` nếu có rồi chuyển record tới `Handler`. Formatter có thể chạy sau đó, thậm chí việc format có thể bị trì hoãn. Filter hữu ích để bỏ record theo level hoặc điều kiện, nhưng không phải cơ chế tự động nhận diện và redacts mọi secret. Nếu secret đã được nối vào message hoặc đặt trong parameter, việc xóa ở một formatter không đảm bảo mọi handler hoặc sink khác đều không nhìn thấy nó.

Giảm dữ liệu ngay trước khi tạo `LogRecord`; dùng Filter/Formatter như lớp phòng vệ bổ sung. Với framework logging khác, áp dụng cùng nguyên tắc ở API và appender tương ứng.

## 3. Không ghi secret vào URL, SQL và exception

Một số dạng log có vẻ vô hại nhưng thường mang dữ liệu nhạy cảm:

| Nguồn | Ví dụ rủi ro | Cách ghi an toàn hơn |
|---|---|---|
| URL | Query string chứa `access_token`, email, reset code. | Ghi scheme/host/path đã chuẩn hóa; loại query và fragment hoặc chỉ giữ tên tham số đã allow-list. |
| HTTP header | `Authorization`, `Cookie`, `Set-Cookie`, API key. | Chỉ ghi tên header cần chẩn đoán và trạng thái có/không; không ghi value. |
| SQL | Bind parameter chứa email, số tài khoản, nội dung tìm kiếm. | Ghi operation, bảng logic, thời gian và số hàng; không ghi giá trị bind. |
| Exception | Message có thể chứa endpoint, response body hoặc query. | Ghi loại exception, mã lỗi nội bộ và request ID; stack trace chỉ vào sink có kiểm soát. |
| Thread name | `worker-user-12345` hoặc email trong tên thread. | Dùng tên thread chức năng như `payment-worker-3`. |
| Metric label | User ID hoặc request ID làm label. | Dùng label có cardinality thấp như service, operation, status; correlation ID để trong log có kiểm soát. |

Regex che chuỗi như `password=...` có thể hữu ích với dữ liệu legacy nhưng không thay thế allow-list. Secret có thể xuất hiện dưới nhiều encoding, tên field, định dạng JSON, URL encoding hoặc trong exception message không theo mẫu. Nếu phải redact ở gateway/appender, kiểm thử nhiều dạng đầu vào và kiểm tra tất cả sink, bao gồm file local, console, agent và log collector.

## 4. Thiết kế JFR custom event không chứa payload nhạy cảm

JFR ghi các event có timestamp, duration và payload. Ứng dụng có thể định nghĩa event riêng bằng cách kế thừa `jdk.jfr.Event`. Các field được khai báo sẽ trở thành dữ liệu trong `.jfr`; field kiểu `String` có thể chứa bất kỳ chuỗi nào mà code gán vào đó. Vì vậy, không đặt raw request, token hoặc object `toString()` vào custom event.

Ví dụ event chỉ lưu mã sự kiện, correlation ID ngẫu nhiên, kết quả và thời lượng:

```java
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Enabled;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

@Name("com.example.PaymentAuthorization")
@Label("Payment Authorization")
@Category({"Application", "Payment"})
@Description("Records the outcome and duration of an authorization attempt")
@Enabled(false) // Chỉ ghi khi recording được cấu hình bật event này.
final class PaymentAuthorizationEvent extends Event {
    @Label("Request ID")
    String requestId;

    @Label("Result")
    String result;

    @Label("Duration")
    long durationMillis;
}

final class PaymentInstrumentation {
    static void record(String requestId, String result, long durationMillis) {
        PaymentAuthorizationEvent event = new PaymentAuthorizationEvent();

        // Không tốn công thu thập/format nếu event không được ghi.
        if (!event.shouldCommit()) {
            return;
        }

        event.requestId = requestId; // ID ngẫu nhiên, không phải PII/credential.
        event.result = result;       // Mã kết quả cố định, không phải message tự do.
        event.durationMillis = durationMillis;
        event.commit();
    }

    static void configure(Recording recording) {
        recording.enable(PaymentAuthorizationEvent.class)
                .withoutStackTrace();
    }
}
```

`@Enabled(false)` đặt event ở trạng thái không ghi mặc định. Recording được cấp quyền có thể bật event bằng `Recording.enable(...)`. `Event.shouldCommit()` cho biết event có được ghi theo setting và threshold của các recording đang chạy; dùng nó trước khi tính toán dữ liệu đắt tiền. `withoutStackTrace()` tránh ghi stack trace cho event này khi stack không cần thiết.

Các lựa chọn trên giảm lượng dữ liệu và overhead, nhưng **không thay thế kiểm tra field**. Nếu code gán access token vào `requestId`, token vẫn được ghi khi event được bật. Hãy dùng kiểu/mã dữ liệu đã allow-list, không thêm field “rawMessage” để tiện debug.

### Event mặc định và stack trace

JFR event được bật mặc định trừ khi cấu hình hoặc annotation tắt nó. Khi thiết kế custom event có khả năng chứa thông tin nhạy cảm, cân nhắc `@Enabled(false)` để chỉ bật trong recording có chủ đích. Stack trace có thể giúp tìm nguồn phát sinh, nhưng cũng làm lộ tên class, package, đường dẫn và bối cảnh xử lý; chỉ bật khi cần.

JFR `EventSettings` hỗ trợ `withoutStackTrace()`, `withThreshold(...)`, `withPeriod(...)` và `with(...)`. Threshold/period/throttle giảm số event được ghi, không phải chức năng che field. Không đặt kỳ vọng rằng một threshold cao sẽ loại bỏ mọi event chứa secret.

## 5. Chọn event JFR theo câu hỏi chẩn đoán

Không nên bật mọi event ở mức chi tiết cao trong thời gian dài. Hãy bắt đầu từ câu hỏi cần trả lời:

| Câu hỏi | Dữ liệu thường cần | Dữ liệu có thể không cần |
|---|---|---|
| Vì sao latency tăng? | Execution samples, monitor contention, GC pauses, socket/file I/O duration. | Custom request payload, header hoặc body. |
| Vì sao heap tăng? | Allocation, heap summary/statistics và object lifetime cần thiết. | Toàn bộ heap dump nếu chỉ cần xu hướng allocation. |
| Vì sao GC pause kéo dài? | GC, safepoint, heap region và pause duration. | Event ứng dụng chứa thông tin người dùng. |
| Vì sao TLS/Kerberos thất bại? | Security debug trace có giới hạn thời gian, endpoint và mã lỗi. | Hex dump hoặc raw protocol data nếu không cần. |
| Vì sao một tác vụ nghiệp vụ thất bại? | Custom event có operation code, outcome, duration và correlation ID. | Raw request, token, credential và dữ liệu nghiệp vụ. |

JDK 26 cung cấp `default.jfc` và `profile.jfc`. `default.jfc` thu thập một tập dữ liệu có overhead thấp, phù hợp recording chạy liên tục; `profile.jfc` thu thập nhiều thông tin hơn và có thể gây overhead lớn hơn, nên dùng trong khoảng thời gian ngắn khi cần. Kiểm tra file cấu hình thực tế của JDK đang triển khai; đừng giả định mọi event đều bật hoặc tắt giống nhau giữa các phiên bản.

## 6. Tạo JFR configuration giảm dữ liệu không cần thiết

Dùng `jfr configure` để tạo một `.jfc` riêng dựa trên `default.jfc`. Ví dụ dưới đây tắt các event ghi giá trị property khởi tạo nếu việc chẩn đoán không cần biết chúng:

```bash
jfr configure \
    --output restricted.jfc \
    jdk.InitialSystemProperty#enabled=false \
    jdk.InitialSecurityProperty#enabled=false
```

Các event này có ích khi điều tra cấu hình JVM/JDK, nhưng cũng có thể tiết lộ system properties hoặc security properties. Chỉ bật chúng trong recording có kiểm soát khi câu hỏi chẩn đoán yêu cầu. Tùy nhu cầu, có thể tắt thêm event I/O, file, socket hoặc custom event không cần cho mục tiêu điều tra. Kiểm tra danh sách event bằng `jfr metadata` và file `.jfc` của JDK cụ thể trước khi áp dụng.

Khởi động recording với cấu hình đã giới hạn:

```bash
java \
  -XX:StartFlightRecording:settings=restricted.jfc,filename=app.jfr,maxage=30m,maxsize=256m \
  -jar application.jar
```

`maxage` và `maxsize` giới hạn dữ liệu được giữ trong disk repository của recording. Chúng giúp tránh recording tăng vô hạn; chúng không phải chính sách xóa file đã dump ra một thư mục khác. Quản lý riêng file `.jfr` sau khi dump.

### Cấu hình event tại runtime bằng `Recording`

```java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;
import java.nio.file.Path;
import java.time.Duration;

static void capture(Path destination) throws Exception {
    Configuration configuration = Configuration.getConfiguration("default");

    try (Recording recording = new Recording(configuration)) {
        recording.setName("bounded-diagnostic-recording");
        recording.setMaxAge(Duration.ofMinutes(30));
        recording.setMaxSize(256L * 1024 * 1024);
        recording.setToDisk(true);

        // Không thu thập các property nếu chúng không cần cho điều tra.
        recording.disable("jdk.InitialSystemProperty");
        recording.disable("jdk.InitialSecurityProperty");

        // Chỉ bật custom event cần thiết và không ghi stack trace.
        recording.enable(PaymentAuthorizationEvent.class)
                .withoutStackTrace();

        recording.start();
        runDiagnosticWorkload();
        recording.stop();
        recording.dump(destination);
    }
}
```

Đoạn code minh họa việc giới hạn event và thời gian lưu trong repository. `Recording.dump(...)` ghi dữ liệu ra file; file đích vẫn phải được bảo vệ bằng quyền truy cập, mã hóa lưu trữ và retention policy của hệ thống. `Recording.close()` giải phóng dữ liệu gắn với recording trong JVM, nhưng không xóa một file `.jfr` đã dump ra disk.

## 7. Dùng `jfr scrub` trước khi chia sẻ recording

Nếu một recording đã được tạo, `jfr scrub` có thể tạo một file mới bằng cách chỉ giữ hoặc loại bỏ event, category và thread theo bộ lọc:

```bash
jfr scrub \
    --exclude-events 'com.example.PaymentDebugPayload,jdk.InitialSystemProperty' \
    input.jfr \
    shareable.jfr
```

Hoặc chỉ giữ nhóm event đã duyệt:

```bash
jfr scrub \
    --include-categories 'GC,Java Application' \
    input.jfr \
    shareable.jfr
```

`jfr scrub` lọc **toàn bộ event** theo tên, category hoặc thread. Đây không phải công cụ chỉnh sửa field để thay một chuỗi password bằng `[REDACTED]`. Nếu event `com.example.PaymentDebugPayload` có một field chứa token, hãy loại cả event đó khỏi file chia sẻ; nếu vẫn cần thông tin chẩn đoán, tạo custom event mới chỉ chứa trường đã allow-list.

Phân biệt các lệnh:

| Lệnh | Tác dụng | Có thay đổi file recording gốc không? |
|---|---|---|
| `jfr print --events ... input.jfr` | Chỉ hiển thị các event được chọn ra stdout. | Không. |
| `jfr summary input.jfr` | Hiển thị thống kê số lượng event và kích thước. | Không. |
| `jfr scrub ... input.jfr output.jfr` | Tạo recording mới sau khi lọc event/category/thread. | Không; tạo file output riêng. |

Không coi `jfr print --events` là biện pháp xóa dữ liệu: file gốc vẫn chứa tất cả event. Sau khi scrub, kiểm tra output:

```bash
jfr summary shareable.jfr
jfr print --events 'com.example.PaymentAuthorization' shareable.jfr
```

Đọc output bằng công cụ JFR/JMC để xác nhận các event nhạy cảm đã bị loại. Nếu không thể chứng minh file mới không còn dữ liệu cần bảo vệ, không chia sẻ file đó. Giữ bản gốc trong vùng điều tra hạn chế quyền truy cập theo quy trình nội bộ; không ghi đè bản gốc trước khi xác minh bản đã lọc.

## 8. Bảo vệ heap dump, thread dump và fatal error log

JFR không phải artifact duy nhất cần bảo vệ.

### Heap dump

Heap dump có thể chứa gần như toàn bộ object đang được giữ trong heap: session, token, object request, dữ liệu cache, nội dung message và chuỗi tạm thời. Tạo heap dump chỉ khi có câu hỏi cần trả lời, ví dụ tìm object giữ reference gây memory leak.

```bash
jcmd <pid> GC.heap_dump /secure-diagnostics/app-heap.hprof
```

`jcmd` là công cụ được Oracle khuyến nghị thay cho các lệnh cũ như `jmap` trong nhiều tác vụ chẩn đoán. Heap dump phải được xem như dữ liệu có mức nhạy cảm cao: giới hạn người đọc, mã hóa khi lưu/truyền, không gửi qua ticket công khai và xóa theo thời hạn đã duyệt.

### Thread dump

Thread dump thường ít nhạy cảm hơn heap dump nhưng vẫn có thể tiết lộ tên thread, tên class/method, lock và call path. Tên thread do ứng dụng đặt có thể nhúng URL hoặc định danh; dùng tên theo vai trò kỹ thuật (`http-worker-4`, `payment-consumer-2`), không đưa email, tenant hoặc user ID vào tên thread.

```bash
jcmd <pid> Thread.print
```

Nếu thread dump được ghi vào log collector, áp dụng quyền truy cập và retention tương tự log vận hành; không giả định stack trace luôn vô hại.

### Fatal error log và error report mở rộng

JVM tạo fatal error log khi gặp lỗi không thể phục hồi. Có thể định vị file bằng `-XX:ErrorFile`:

```bash
java \
  -XX:ErrorFile=/secure-diagnostics/hs_err_pid%p.log \
  -jar application.jar
```

`-XX:+ExtensiveErrorReports` bật thêm thông tin trong error file; tài liệu JDK 26 cảnh báo nội dung có thể lớn và chứa thông tin nhạy cảm. Tùy chọn này mặc định tắt. Chỉ bật khi điều tra cần dữ liệu bổ sung và có vùng lưu trữ được bảo vệ.

Nếu dùng `-XX:+HeapDumpOnOutOfMemoryError`, cấu hình `-XX:HeapDumpPath` tới thư mục riêng có quyền hạn chế. Không đặt heap dump cạnh file log công khai hoặc thư mục web có thể tải xuống.

## 9. Kiểm soát security debug và JVM unified logging

`-Xlog` là hệ thống log thống nhất cho các thành phần JVM. Hãy bật đúng tag và level cần chẩn đoán, giới hạn file rotation và tránh `all=trace` kéo dài trong production.

Ví dụ chỉ ghi GC info và giới hạn số file:

```bash
java \
  -Xlog:gc=info:file=/secure-diagnostics/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar application.jar
```

Unified logging tập trung vào các thành phần JVM; nó không tự hiểu trường nào trong application log là password. Nếu ứng dụng ghi secret ra stdout/stderr, redirect stdout/stderr vào file hoặc container log collector vẫn có thể lưu secret đó.

`java.security.debug` và các thuộc tính debug của GSS/Kerberos/JSSE hữu ích cho điều tra bảo mật nhưng cần giới hạn thời gian và quyền truy cập. Oracle cảnh báo một số debug trace có thể chứa dữ liệu nhạy cảm; `certpath,ocsp,verbose` có thể in hexadecimal dump của OCSP request/response. Không bật `java.security.debug=all` như cấu hình mặc định production.

```bash
# Chỉ bật trong cửa sổ điều tra có kiểm soát.
java -Djava.security.debug=certpath,ocsp -jar application.jar
```

Khi kết thúc điều tra, tắt debug, đóng recording, thu hồi quyền truy cập tạm thời và xử lý file theo retention policy. Không gửi log bảo mật chi tiết tới kênh có người nhận rộng hơn nhóm cần điều tra.

## 10. Quyền truy cập recording và kênh chẩn đoán

JFR có thể được điều khiển bằng `jcmd`, API trong tiến trình hoặc `FlightRecorderMXBean` qua JMX. Quyền tạo, dump, đọc và điều khiển recording vì vậy cần được quản lý giống quyền đọc log bảo mật.

- Chỉ cho phép tài khoản hệ điều hành hoặc service account được phê duyệt attach vào JVM.
- Nếu môi trường không cần attach runtime, cân nhắc `-XX:+DisableAttachMechanism`; tùy chọn này làm các công cụ attach như `jcmd` không thể điều khiển JVM, nên phải đánh giá ảnh hưởng tới vận hành trước khi bật.
- Nếu dùng JMX từ xa, bật xác thực, TLS, giới hạn network access và cấp quyền MBean tối thiểu. Không mở cổng JMX không xác thực ra mạng công khai.
- Đặt file `.jfr`, `.hprof`, `hs_err_pid*.log` và GC/security log trong thư mục riêng; dùng ACL/permissions giới hạn, mã hóa at rest và mã hóa khi chuyển file.
- Không gắn file recording vào ticket, chat hoặc object storage công khai. Dùng kho hỗ trợ có kiểm soát và thời hạn xóa cụ thể.
- Ghi lại ai đã tạo, tải xuống, phân tích và chia sẻ artifact; chỉ cấp quyền theo thời gian điều tra.

JFR disk repository mặc định dùng thư mục tạm của hệ thống. `-XX:FlightRecorderOptions:repository=...` có thể đặt thư mục repository riêng; `preserve-repository` điều khiển việc giữ file repository sau khi JVM thoát và mặc định là `false`. Không bật giữ repository lâu dài nếu chưa có lý do và chính sách bảo vệ phù hợp.

## 11. Giới hạn thời gian và kích thước lưu trữ

Một recording chạy lâu có thể tích lũy nhiều dữ liệu. Đặt giới hạn ngay khi bắt đầu:

| Cơ chế | Tác dụng |
|---|---|
| `maxage` / `Recording.setMaxAge(Duration)` | Chỉ giữ dữ liệu trong một khoảng thời gian; chunk cũ hơn bị loại khỏi repository. |
| `maxsize` / `Recording.setMaxSize(long)` | Giới hạn kích thước dữ liệu trên disk; chunk cũ bị xóa để nhường chỗ. |
| `duration` / `Recording.setDuration(Duration)` | Tự dừng recording sau khoảng thời gian định trước. |
| `filename` / `Recording.setDestination(Path)` | Xác định nơi file recording được ghi ra. |
| `Recording.close()` | Giải phóng dữ liệu recording trong JVM. |

Nếu không đặt max age hoặc max size, disk repository có thể tăng không giới hạn. Giới hạn repository không tự xóa các file `.jfr` đã dump, heap dump hoặc file đã được copy sang nơi khác; cần retention job hoặc quy trình xóa riêng cho các artifact đó.

Ví dụ recording giới hạn 15 phút và 128 MB:

```bash
java \
  -XX:StartFlightRecording:settings=default,filename=incident.jfr,duration=15m,maxage=15m,maxsize=128m \
  -jar application.jar
```

`default` là cấu hình JFR có sẵn của JDK. Nếu cần thêm thông tin, tạo `.jfc` riêng bằng `jfr configure`, kiểm tra các event được bật và đo overhead trước khi triển khai.

## 12. Quy trình xử lý sự cố có kiểm soát

Một quy trình ngắn gọn giúp đội vận hành vừa có dữ liệu chẩn đoán vừa giảm nguy cơ lộ dữ liệu:

1. **Xác định câu hỏi:** latency, GC, memory leak, deadlock, TLS hay lỗi nghiệp vụ. Chỉ thu thập event cần cho câu hỏi đó.
2. **Chọn mức dữ liệu:** bắt đầu với JFR `default.jfc` hoặc JVM log mức `info`; chỉ tăng sang `profile`, stack trace sâu, security debug hoặc heap dump khi có lý do.
3. **Kiểm tra schema:** rà soát application log và custom JFR event để chắc chắn không có raw body, header, password, token, PII hoặc object `toString()`.
4. **Giới hạn recording:** đặt duration, max age, max size, event settings và stack trace theo nhu cầu.
5. **Bảo vệ đầu ra:** ghi vào thư mục riêng, ACL chặt, mã hóa và giới hạn người được tải file.
6. **Phân tích tại vùng tin cậy:** ưu tiên `jfr summary`, event filter và JMC; chỉ xuất phần cần thiết cho báo cáo.
7. **Scrub trước khi chia sẻ:** dùng `jfr scrub` để loại event/category/thread không cần; kiểm tra file output và hiểu rằng công cụ không redact từng field.
8. **Kết thúc và dọn dẹp:** tắt debug/recording, thu hồi quyền tạm, xóa artifact hết hạn và ghi nhận người nhận file.

Nếu phát hiện secret đã bị ghi vào artifact, xem artifact như một bản sao của secret: hạn chế truy cập, xóa khỏi các sink và bản sao theo quy trình, đồng thời rotate/revoke credential nếu cần. Chỉ xóa log ở một dashboard không đảm bảo bản sao ở agent, buffer, archive hoặc backup đã biến mất.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| JFR là binary nên không chứa dữ liệu nhạy cảm. | JFR có thể chứa String fields, stack traces, I/O metadata và custom event payload. Binary chỉ là định dạng lưu trữ. |
| Bật JFR mặc định thì JDK tự che password/token. | Không có redaction tổng quát cho mọi event field; ứng dụng phải giới hạn dữ liệu từ lúc tạo event. |
| `jfr print --events` xóa event khác khỏi recording. | Lệnh này chỉ lọc nội dung hiển thị; file gốc vẫn nguyên vẹn. Dùng `jfr scrub` để tạo file mới đã lọc event. |
| `jfr scrub` thay một field secret bằng `[REDACTED]`. | `jfr scrub` lọc event/category/thread, không phải field-level redaction. Nếu một event có secret, loại cả event hoặc tạo recording mới an toàn. |
| `withoutStackTrace()` loại mọi dữ liệu nhạy cảm. | Nó chỉ tắt stack trace cho event; các field payload vẫn được ghi như thường. |
| `threshold`, `period` và `throttle` là bộ lọc secret. | Chúng giới hạn tần suất hoặc thời lượng event, không che nội dung field. |
| Heap dump chỉ chứa thông tin GC. | Heap dump chứa object graph và có thể bao gồm token, session, PII và dữ liệu nghiệp vụ. |
| Thread dump không nhạy cảm vì không có heap object. | Thread name, stack frame và lock context vẫn có thể tiết lộ thông tin nội bộ. |
| `-XX:+ExtensiveErrorReports` nên bật mặc định để dễ debug. | JDK 26 mặc định tắt; tài liệu cảnh báo error report mở rộng có thể chứa dữ liệu nhạy cảm. |
| Giới hạn `maxage`/`maxsize` sẽ xóa mọi file đã dump. | Các giới hạn này áp dụng cho disk repository; file output và heap dump cần retention riêng. |
| Hash email/user ID là ẩn danh. | Hash không khóa có thể bị dò bằng dictionary; dùng mã tham chiếu ngẫu nhiên hoặc pseudonym có khóa và quản lý riêng. |

## 14. Checklist trước khi bật logging/recording

- [ ] Đã xác định mục tiêu chẩn đoán và chỉ bật các event/log cần thiết.
- [ ] Không ghi password, token, cookie, private key, OTP, dữ liệu thanh toán hoặc raw request/response body.
- [ ] Đã dùng allow-list cho trường log và custom JFR event.
- [ ] Không ghi object `toString()` hoặc exception message chưa kiểm tra.
- [ ] Correlation ID là giá trị ngẫu nhiên/opaque, không mã hóa trực tiếp PII.
- [ ] Đã cân nhắc thread name, URL query, SQL bind, file path và host/IP là dữ liệu có thể nhạy cảm.
- [ ] Custom JFR event dùng `@Enabled(false)` nếu không cần ghi mặc định; `shouldCommit()` trước khi thu thập dữ liệu đắt tiền.
- [ ] Đã tắt stack trace cho event không cần trace; hiểu stack trace không phải lớp redaction.
- [ ] Đã dùng `.jfc` giới hạn event và kiểm tra cấu hình JFR của đúng JDK.
- [ ] Đã đặt duration, max age và max size cho recording; có retention riêng cho file dump.
- [ ] Đã dùng `jfr scrub` để lọc event trước khi chia sẻ và xác minh output; không nhầm với `jfr print`.
- [ ] Heap dump, thread dump, JFR và fatal error log nằm trong vùng lưu trữ hạn chế quyền, được mã hóa và có thời hạn xóa.
- [ ] Security debug và `-XX:+ExtensiveErrorReports` chỉ bật khi có lý do và trong thời gian kiểm soát.
- [ ] Đã bảo vệ `jcmd`/attach và JMX theo mô hình vận hành.
- [ ] Có quy trình xử lý và rotate credential nếu phát hiện secret đã bị ghi ra ngoài.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `java.util.logging.Logger`](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html)
- [Java SE 26 — `LogRecord`](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/LogRecord.html)
- [Java SE 26 — JFR `Event`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Java SE 26 — JFR `Recording`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Java SE 26 — JFR `EventSettings`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [Java SE 26 — JFR package settings](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [The `jfr` Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [The `java` Command — JDK 26, JFR and Error Reports](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Troubleshooting Memory Leaks — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
- [Troubleshooting Security — JDK 26](https://docs.oracle.com/en/java/javase/26/security/troubleshooting-security.html)
- [JDK 26 Release Notes — JFR event defaults](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)

*Cập nhật nội dung: 27-11-2026. API logging/JFR trong bài là API ổn định. JFR scrub lọc event, category và thread; không redact từng field. Dữ liệu log, recording và dump cần được giới hạn ngay từ nguồn, bảo vệ khi lưu trữ và xóa theo retention policy.*
