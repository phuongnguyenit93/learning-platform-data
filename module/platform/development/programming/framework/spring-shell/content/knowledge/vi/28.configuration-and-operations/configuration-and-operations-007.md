# Ghi nhận tên lệnh, thời lượng và kết quả nhưng che dữ liệu nhạy cảm

Trong ứng dụng dòng lệnh, log giúp trả lời những câu hỏi vận hành quan trọng: người dùng hoặc service account đã chạy lệnh nào, lệnh bắt đầu trong ngữ cảnh nào, mất bao lâu và kết thúc thành công hay thất bại? Những thông tin này hữu ích khi điều tra sự cố, theo dõi thao tác quản trị và đối chiếu hoạt động giữa nhiều hệ thống.

Tuy nhiên, command line cũng thường mang theo dữ liệu nhạy cảm như token, mật khẩu, email, mã khách hàng, đường dẫn riêng tư hoặc nội dung file. Ghi toàn bộ dòng lệnh, argument, `CommandContext` hay kết quả trả về có thể biến log thành nơi lưu trữ bí mật ngoài ý muốn.

Thiết kế phù hợp là tạo một audit event nhỏ với các trường được cho phép rõ ràng: tên command, actor tham chiếu, correlation ID, thời lượng, outcome và error code đã chuẩn hóa. Không đưa raw arguments, raw output hoặc exception message vào audit event. Bài này dùng API Spring Shell 4.0.4.

## 1. Phân biệt audit log, application log và metrics

Ba loại dữ liệu này có mục tiêu khác nhau:

| Loại | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Audit event | Ai đã thực hiện hành động nào và kết quả ra sao? | Actor `usr_8f2a` chạy `customer import`, thành công sau 820 ms |
| Application log | Ứng dụng gặp vấn đề gì và cần chẩn đoán thế nào? | Database timeout khi ghi batch thứ 4 |
| Metric | Hệ thống hoạt động nhanh/chậm và ổn định ra sao theo thời gian? | p95 thời lượng `customer import` là 1,2 giây |

Không nên dùng một dòng log chứa toàn bộ input và stack trace để phục vụ cả ba mục tiêu. Audit event cần schema ổn định và tối thiểu; application log có thể chứa diagnostics trong hệ thống được kiểm soát; metric cần nhãn có số lượng giá trị hữu hạn.

## 2. Chọn trường được phép ghi

Trước khi triển khai, hãy xác định schema audit event. Ví dụ:

| Trường | Nội dung | Quy tắc |
|---|---|---|
| `event` | Loại sự kiện | Giá trị cố định `shell.command.completed` |
| `command` | Tên command | Tên khai báo tĩnh trong ứng dụng |
| `actor_ref` | Người hoặc service account thực hiện | ID giả danh hoặc mã tham chiếu đã được duyệt |
| `correlation_id` | Liên kết log của cùng một lần xử lý | ID do ứng dụng/tracing tạo, không chứa dữ liệu người dùng |
| `duration_ms` | Thời lượng thực thi | Đo bằng đồng hồ monotonic |
| `outcome` | Kết quả tổng quát | `SUCCESS` hoặc `FAILURE` |
| `error_code` | Nhóm lỗi | Mã cố định như `VALIDATION_FAILED`, `UNEXPECTED` |

Một audit event có thể trông như sau:

```json
{
  "event": "shell.command.completed",
  "command": "customer import",
  "actor_ref": "usr_8f2a",
  "correlation_id": "01J9Q8K7Z5M2",
  "duration_ms": 820,
  "outcome": "SUCCESS",
  "error_code": "NONE"
}
```

Event không chứa tên khách hàng, email, token, đường dẫn file, nội dung argument hoặc dữ liệu trả về. Nếu đội vận hành cần thêm thông tin, hãy thêm từng trường sau khi phân loại độ nhạy và xác định mục đích sử dụng.

## 3. Vì sao không nên log toàn bộ command line?

Một lệnh có thể chứa bí mật trực tiếp trong option:

```bash
customer api configure --token "secret-value"
```

Nếu ghi nguyên dòng lệnh, bí mật có thể xuất hiện trong log collector, artifact, shell history hoặc bản sao lưu. Tương tự, command có thể nhận email, mã hồ sơ, đường dẫn chứa tên người dùng hoặc dữ liệu cá nhân.

Các nguồn dễ vô tình làm lộ dữ liệu gồm:

- `String[] args` lúc khởi động process.
- Dòng lệnh thô do terminal đọc được.
- `CommandContext.parsedInput()` và các option/argument đã parse.
- `CommandOption.value()`.
- `CommandContext.toString()`.
- Mảng tham số truyền vào command method hoặc `ProceedingJoinPoint.getArgs()`.
- Chuỗi kết quả command, exception message và stack trace.
- Shell history hoặc script file có chứa giá trị bí mật.

Trong Spring Shell 4, `CommandContext` là một record chứa `ParsedInput`, `CommandRegistry`, `PrintWriter` và `InputReader`. `toString()` do Java record sinh ra thể hiện các thành phần của record; vì vậy log `CommandContext` hoặc `parsedInput` có thể làm lộ input. `CommandOption` cũng có trường `value` chứa giá trị option lúc chạy.

Nguyên tắc an toàn là không serialize toàn bộ context và không duyệt toàn bộ argument để ghi log. Chỉ tạo audit event từ các trường allowlist đã được chọn trước.

## 4. Không log secret ngay từ thiết kế command

Nếu có thể, đừng truyền password, access token hoặc private key như một option thông thường. Giá trị command line có thể bị lưu trong shell history, process listing, CI log hoặc telemetry của môi trường chạy.

Ưu tiên các cách sau:

- Lấy secret từ secret manager hoặc cơ chế quản lý credential của nền tảng.
- Inject secret vào process bằng cơ chế bảo mật của CI/CD hoặc container runtime.
- Đọc từ file secret được mount với quyền tối thiểu và vòng đời ngắn.
- Với phiên tương tác, dùng input reader có cơ chế nhập password phù hợp và không echo nội dung ra terminal.
- Truyền một tham chiếu không nhạy cảm tới secret thay vì truyền giá trị secret.

Ví dụ command chỉ nhận tên cấu hình credential:

```text
customer api configure --credential-ref production-customer-api
```

Service dùng `credential-ref` để tra secret từ kho được bảo vệ. Audit event có thể ghi tên command và kết quả, nhưng không ghi secret hoặc nội dung cấu hình sau khi giải mã.

Biến môi trường cũng cần được bảo vệ: không dump toàn bộ environment vào log và không in giá trị secret khi báo lỗi cấu hình.

## 5. Đo thời lượng bằng đồng hồ monotonic

Không dùng `LocalDateTime.now()` hoặc `Instant.now()` để tính thời lượng. Đồng hồ hệ thống có thể được đồng bộ hoặc điều chỉnh trong lúc command chạy. `System.nanoTime()` phù hợp để đo khoảng thời gian vì nó là đồng hồ monotonic, không biểu diễn thời điểm lịch.

```java
long startedAt = System.nanoTime();

try {
    customerService.importCustomers();
}
finally {
    long elapsedNanos = System.nanoTime() - startedAt;
    long durationMs = elapsedNanos / 1_000_000;
}
```

Nếu cần ghi thời điểm bắt đầu/kết thúc, dùng `Instant.now()` riêng cho timestamp. Dùng `nanoTime()` để tính elapsed time và `Instant` để ghi mốc thời gian lịch.

## 6. Xác định đúng ranh giới cần audit

Có nhiều thời điểm trong vòng đời command:

```text
Nhận input
    |
    v
Parse và resolve command
    |
    v
Kiểm tra availability / bind argument
    |
    v
Gọi command method
    |
    v
Xử lý kết quả và render output
    |
    v
Kết thúc lần thực thi
```

Một aspect đặt quanh method `@Command` ghi thời lượng method và outcome của lời gọi method đó. Nó không tự bao phủ lỗi parse, command không tồn tại, command không khả dụng hoặc lỗi xảy ra sau khi method trả về trong giai đoạn render output.

Hãy quyết định cần ghi nhận phạm vi nào:

- **Command method audit:** phù hợp để ghi các thao tác nghiệp vụ đã đi vào method command.
- **Command dispatch audit:** cần thêm lớp điều phối quanh command executor nếu muốn ghi kết quả sau khi Spring Shell trả `ExitStatus`.
- **Process/attempt audit:** cần lớp runner hoặc process supervisor nếu phải ghi cả lỗi parse, command không tồn tại và lỗi khởi động.

Không mô tả một aspect quanh method như thể nó ghi nhận mọi lần người dùng thử chạy command. Với yêu cầu audit toàn diện, cần kiểm tra cả các đường lỗi trước và sau method.

## 7. Dùng AOP để ghi thời lượng method `@Command`

Spring Shell 4 đánh dấu command bằng annotation `org.springframework.shell.core.command.annotation.Command` trên method của một Spring bean. Có thể dùng Spring AOP để bao quanh các method có annotation này.

Thêm AOP starter nếu ứng dụng chưa có:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
```

Tạo record audit chỉ chứa các trường an toàn:

```java
public record CommandAuditEvent(
        String command,
        String actorRef,
        String correlationId,
        long durationMs,
        String outcome,
        String errorCode) {
}
```

Định nghĩa interface lấy actor hiện tại. Implementation có thể tích hợp Spring Security hoặc service account của ứng dụng, nhưng chỉ trả về mã tham chiếu đã được phép ghi:

```java
public interface AuditActorProvider {

    String currentActorReference();
}
```

Aspect đo thời lượng và ghi outcome:

```java
import java.util.concurrent.TimeUnit;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.slf4j.MDC;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Aspect
@Component
class CommandAuditAspect {

    private final CommandAuditSink auditSink;
    private final AuditActorProvider actorProvider;

    CommandAuditAspect(
            CommandAuditSink auditSink,
            AuditActorProvider actorProvider) {
        this.auditSink = auditSink;
        this.actorProvider = actorProvider;
    }

    @Around(value = "@annotation(command)", argNames = "joinPoint,command")
    public Object audit(
            ProceedingJoinPoint joinPoint,
            Command command) throws Throwable {

        String commandName = command.name().length == 0
                ? ((MethodSignature) joinPoint.getSignature()).getMethod().getName()
                : String.join(" ", command.name());

        String actorRef = currentActorReference();
        String correlationId = safeLabel(MDC.get("traceId"));
        long startedAt = System.nanoTime();
        String outcome = "SUCCESS";
        String errorCode = "NONE";

        try {
            return joinPoint.proceed();
        }
        catch (Throwable exception) {
            outcome = "FAILURE";
            errorCode = classify(exception);
            throw exception;
        }
        finally {
            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt);

            CommandAuditEvent event = new CommandAuditEvent(
                    commandName,
                    actorRef,
                    correlationId,
                    durationMs,
                    outcome,
                    errorCode);

            try {
                auditSink.append(event);
            }
            catch (RuntimeException auditFailure) {
                // Fallback diagnostics; không ghi input hoặc exception message của command.
                System.getLogger(CommandAuditAspect.class.getName()).log(
                        System.Logger.Level.ERROR,
                        "Unable to append shell command audit event: " + commandName);
            }
        }
    }

    private static String classify(Throwable exception) {
        if (exception instanceof CustomerValidationException) {
            return "VALIDATION_FAILED";
        }
        if (exception instanceof CustomerNotFoundException) {
            return "NOT_FOUND";
        }
        return "UNEXPECTED";
    }

    private static String safeLabel(String value) {
        if (value == null || value.isBlank()) {
            return "unknown";
        }
        String bounded = value.substring(0, Math.min(value.length(), 80));
        return bounded.replaceAll("[\\r\\n\\p{Cntrl}]", "_");
    }

    private String currentActorReference() {
        try {
            return safeLabel(actorProvider.currentActorReference());
        }
        catch (RuntimeException actorLookupFailure) {
            return "unknown";
        }
    }
}
```

`CustomerValidationException` và `CustomerNotFoundException` là exception nghiệp vụ của ứng dụng. Hàm `classify(...)` trả mã cố định, không ghi `exception.getMessage()` vì message có thể chứa input, SQL hoặc dữ liệu cá nhân.

`safeLabel(...)` chỉ dùng cho các nhãn actor/correlation có nguồn từ ứng dụng. Nó thay control character và giới hạn độ dài. Không dùng hàm này như bộ lọc bí mật cho raw command line; raw input không nên được đưa vào event ngay từ đầu.

Nếu actor provider tạm thời không lấy được chủ thể, ví dụ dùng `unknown` và phát diagnostics riêng. Đừng để lỗi tra actor làm command nghiệp vụ không được chạy, trừ khi chính sách bảo mật của use case yêu cầu phải có actor xác thực trước khi thực hiện.

Aspect trên ghi `SUCCESS` khi method trả bình thường và `FAILURE` khi method ném exception. Nếu ứng dụng biểu diễn thất bại bằng một object kết quả trả về thay vì exception, hãy mở rộng outcome classifier để kiểm tra kiểu kết quả đó hoặc ghi event tường minh trong command adapter.

Ví dụ lấy tên từ `@Command.name()` giả định annotation chứa toàn bộ tên command. Nếu class dùng `@CommandGroup(prefix = "customer")` và method chỉ khai báo `@Command(name = "import")`, cần ghép prefix từ `@CommandGroup` hoặc ánh xạ method sang một audit name cố định để event ghi `customer import`. Không ghi nhầm tên method ngắn thành tên command đầy đủ.

Nếu dự án còn dùng Spring Shell 3.3, command method thường được đánh dấu bằng `@ShellMethod` trong `org.springframework.shell.standard`. Khi đó, đổi pointcut sang annotation của 3.3 và lấy tên từ metadata `key`; không trộn `@Command` 4.x với API command 3.x trong cùng ví dụ.

## 8. Tạo sink ghi audit bằng structured logging

Tách việc tạo event khỏi nơi ghi log giúp kiểm thử schema độc lập và có thể thay sink sau này.

```java
public interface CommandAuditSink {

    void append(CommandAuditEvent event);
}
```

Implementation dùng SLF4J fluent key-value API:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
class StructuredCommandAuditSink implements CommandAuditSink {

    private static final Logger log =
            LoggerFactory.getLogger("AUDIT.SHELL_COMMAND");

    @Override
    public void append(CommandAuditEvent event) {
        var builder = "SUCCESS".equals(event.outcome())
                ? log.atInfo()
                : log.atWarn();

        builder
                .addKeyValue("event", "shell.command.completed")
                .addKeyValue("command", event.command())
                .addKeyValue("actor_ref", event.actorRef())
                .addKeyValue("correlation_id", event.correlationId())
                .addKeyValue("duration_ms", event.durationMs())
                .addKeyValue("outcome", event.outcome())
                .addKeyValue("error_code", event.errorCode())
                .log("Spring Shell command completed");
    }
}
```

Spring Boot hỗ trợ structured logging dạng JSON như ECS, GELF và Logstash. Ví dụ bật ECS cho console:

```yaml
logging:
  structured:
    format:
      console: ecs
```

Structured logging giúp hệ thống thu thập log đọc các key-value riêng biệt thay vì phải parse một chuỗi tự do. Vẫn phải giới hạn giá trị được ghi; JSON không tự làm cho dữ liệu nhạy cảm trở nên an toàn.

## 9. Correlation ID và actor reference

Correlation ID giúp nối một command với các log liên quan ở service, database gateway hoặc HTTP client. Nếu ứng dụng dùng tracing, lấy trace ID hiện có từ tracing/MDC thay vì tự tạo nhiều ID không liên kết.

Actor reference xác định chủ thể thực hiện hành động. Có thể là user ID giả danh, service account ID hoặc một nhãn như `scheduler`. Không nên ghi username/email đầy đủ nếu audit chỉ cần phân biệt chủ thể.

Nếu cần liên kết ổn định với một ID nhạy cảm, dùng HMAC với khóa bí mật do hệ thống quản lý. Hash không khóa của email hoặc số điện thoại thường có thể bị dò bằng từ điển; không coi SHA-256 trực tiếp là ẩn danh hóa.

Không đưa correlation ID, actor ID hoặc session ID vào metric tag. Các giá trị này có thể tạo cardinality rất lớn. Chúng phù hợp với log/tracing, còn metrics nên dùng nhãn có tập giá trị nhỏ.

## 10. Không ghi raw output hoặc kết quả nghiệp vụ

Method command có thể trả về `String`, DTO, bảng hoặc một object khác để Spring Shell render. Không nên log `result.toString()` một cách tổng quát.

Kết quả có thể chứa:

- Email, tên, địa chỉ hoặc mã hồ sơ.
- Token vừa tạo hoặc thông tin credential.
- Nội dung file, câu truy vấn hoặc dữ liệu khách hàng.
- Đường dẫn tuyệt đối chứa username hoặc tên dự án nội bộ.
- Dữ liệu lỗi do hệ thống bên ngoài trả về.

Trong audit event, ghi `outcome=SUCCESS` hoặc `outcome=FAILURE`. Nếu cần số liệu tổng hợp, chỉ ghi các trường đã được phê duyệt như `records_processed` hoặc `records_rejected`, sau khi xác nhận chúng không tiết lộ thông tin cá nhân trong ngữ cảnh ứng dụng.

Không dùng độ dài output hoặc một đoạn đầu output làm đại diện mặc định. Ngay cả một đoạn ngắn cũng có thể chứa secret.

## 11. Mask, omit hay pseudonymize?

Không phải dữ liệu nhạy cảm nào cũng cần được che theo cùng cách:

| Cách xử lý | Khi nào phù hợp | Lưu ý |
|---|---|---|
| Omit | Giá trị không cần cho mục đích audit | Lựa chọn mặc định tốt nhất |
| Mask | Người vận hành cần nhận diện một phần giá trị | Phần còn lại vẫn có thể là dữ liệu cá nhân |
| Pseudonymize | Cần liên kết nhiều event của cùng một chủ thể | Dùng HMAC hoặc token tham chiếu có kiểm soát |
| Encrypt | Có yêu cầu lưu trường nhạy cảm có thể khôi phục | Khóa và quyền truy cập phải được quản lý riêng |

Ví dụ email được mask có thể là `a***@example.com`, nhưng ngay cả phần domain hoặc ký tự đầu vẫn có thể nhận diện một người trong hệ thống nhỏ. Chỉ ghi dạng mask nếu mục đích và chính sách dữ liệu cho phép.

Không dùng regex để cố tìm mọi token hoặc PII trong một dòng log tự do rồi mới che. Tốt hơn là xây dựng event từ allowlist và không đưa raw value vào event.

## 12. Ngăn log injection

Input do người dùng kiểm soát có thể chứa newline, carriage return hoặc ký tự điều khiển. Nếu ghi trực tiếp vào log văn bản, kẻ tấn công có thể tạo dòng giả hoặc làm sai cấu trúc log.

Các nguyên tắc cần áp dụng:

- Ưu tiên structured logging với encoder JSON đúng chuẩn.
- Giữ message template cố định và dùng key-value/placeholder.
- Sanitize mọi chuỗi không tin cậy trước khi ghi.
- Loại CR/LF và control characters khỏi label tự do.
- Giới hạn độ dài các trường có thể thay đổi.
- Không ghép raw input vào message bằng string concatenation.
- Validate event fields; nếu một field không hợp lệ, bỏ hoặc thay field đó nhưng vẫn giữ các dữ kiện audit an toàn còn lại.

Parameterized logging giảm lỗi định dạng nhưng tự nó không bảo vệ khỏi CR/LF injection. Encoder structured phải escape đúng và ứng dụng vẫn cần giới hạn dữ liệu đầu vào.

## 13. Exception message và stack trace cần được xử lý riêng

Exception message đôi khi chứa nội dung input, câu SQL, đường dẫn, hostname nội bộ hoặc response từ hệ thống khác. Vì vậy, audit event chỉ nên ghi error code đã chuẩn hóa.

Diagnostics chi tiết có thể được ghi ở logger riêng với quyền truy cập hẹp hơn, retention phù hợp và quy tắc redaction riêng. Không tự động chuyển toàn bộ exception message sang audit event.

Một quy ước ví dụ:

| Tình huống | Audit event | Diagnostics log |
|---|---|---|
| Validation thất bại | `VALIDATION_FAILED` | Tên field và quy tắc lỗi đã lọc, nếu được phép |
| Không tìm thấy tài nguyên | `NOT_FOUND` | Resource type và mã tham chiếu an toàn |
| Database timeout | `DEPENDENCY_TIMEOUT` | Stack trace và dependency name trong log hạn chế |
| Lỗi lập trình | `UNEXPECTED` | Stack trace trong hệ thống diagnostics |

Không trả stack trace cho người dùng terminal chỉ vì đang bật debug. Thông báo command nên ngắn gọn và dùng correlation ID để người vận hành tra cứu diagnostics có quyền truy cập.

## 14. Ghi nhận command status và thời lượng bằng metrics

Log ghi từng event; metrics giúp theo dõi xu hướng. Có thể dùng Micrometer `Timer` với tag `command` và `outcome`:

```java
Timer.builder("spring.shell.command.duration")
        .description("Thời lượng thực thi command Spring Shell")
        .tag("command", commandName)
        .tag("outcome", outcome)
        .register(meterRegistry)
        .record(durationNanos, TimeUnit.NANOSECONDS);
```

Các tag phù hợp là tên command tĩnh, kết quả và có thể là nhóm chức năng. Không dùng email, username, actor ID, correlation ID, tên file hoặc raw option value làm tag. Mỗi giá trị tag mới có thể tạo một time series riêng và làm hệ thống metrics tăng cardinality nhanh chóng.

Nếu cần alert khi command thất bại, dùng counter theo `command` và `outcome`; nếu cần latency, dùng timer/histogram. Không dùng audit log làm nguồn duy nhất cho dashboard hiệu năng.

## 15. Giới hạn của AOP và trường hợp cần audit rộng hơn

Spring AOP chỉ hỗ trợ method execution join point trên Spring beans. Aspect ở trên có một số giới hạn:

- Chỉ bắt method có `@Command` và thực sự đi qua Spring proxy.
- Tự gọi một method khác trong cùng bean (self-invocation) không đi qua proxy, nên advice có thể không chạy cho lời gọi đó.
- Không bắt lỗi parser hoặc command không tồn tại vì chưa gọi tới command method.
- Không bao trọn thời gian render kết quả sau khi method trả về.
- Với method trả `CompletableFuture`, aspect kết thúc khi method trả future; muốn đo toàn bộ tác vụ bất đồng bộ phải ghi event khi future hoàn tất.

Nếu cần audit tất cả command attempt, kể cả input sai hoặc command không tìm thấy, cần đặt instrumentation ở lớp runner/dispatch hoặc process supervisor. Spring Shell 4 có `CommandExecutor.execute(CommandContext)` trả về `ExitStatus`, nhưng không nên tự suy ra rằng một aspect quanh method đã bao phủ toàn bộ executor lifecycle.

Với command được đăng ký bằng `Command.Builder`, method annotation pointcut không áp dụng. Hãy bọc execution function bằng một audit decorator hoặc dùng một lớp dispatcher chung để các command programmatic và annotation-based có cùng schema audit.

## 16. Lựa chọn thời điểm ghi audit và độ tin cậy

Audit log có thể được ghi đồng bộ ngay sau command hoặc được gửi bất đồng bộ tới hệ thống tập trung. Mỗi cách có trade-off:

| Cách ghi | Ưu điểm | Rủi ro |
|---|---|---|
| Ghi đồng bộ vào logger | Đơn giản, event gần với thời điểm command kết thúc | I/O logging có thể tăng latency; appender lỗi có thể làm mất event |
| Gửi qua queue | Tách command khỏi hệ thống lưu log, dễ mở rộng | Có thể mất event nếu queue không bền hoặc chưa flush khi process dừng |
| Transactional outbox | Gắn event nghiệp vụ với transaction dữ liệu | Cần worker gửi event và quản lý retry/deduplication |
| Audit store append-only | Dễ kiểm soát truy cập và truy vết | Cần vận hành retention, backup và integrity |

Quyết định audit failure có làm command thất bại hay không phải được nêu rõ. Với telemetry vận hành thông thường, có thể fail-open để lỗi sink không chặn command và phát cảnh báo riêng. Với audit bắt buộc để đáp ứng yêu cầu kiểm soát, cần một cơ chế lưu bền như outbox hoặc audit store và xác định fail-closed ở các thao tác quan trọng. Không nên vô tình chọn policy chỉ vì `logger.info()` không ném exception.

## 17. Bảo vệ log sau khi đã ghi

Redaction ở ứng dụng mới là bước đầu. Hệ thống lưu trữ log cũng cần kiểm soát:

- Quyền đọc theo vai trò và mục đích công việc.
- Mã hóa khi truyền và khi lưu nếu môi trường yêu cầu.
- Retention và xóa theo chính sách dữ liệu.
- Theo dõi truy cập, export và thay đổi cấu hình logging.
- Tách audit stream khỏi log debug có độ nhạy cao hơn.
- Đồng bộ thời gian giữa các node hoặc ghi timestamp UTC rõ ràng.
- Giới hạn quyền sửa/xóa event đối với hệ thống audit quan trọng.

Không giữ log vô thời hạn nếu không có mục đích và cơ sở phù hợp. Log cũng là dữ liệu cần quản trị, không phải nơi lưu trữ miễn phí cho mọi thông tin runtime.

## 18. Kiểm thử để chứng minh secret không xuất hiện

Kiểm thử audit không chỉ xác nhận event được ghi. Cần xác nhận những trường không được phép ghi thực sự vắng mặt.

Các tình huống cần kiểm thử:

| Tình huống | Kỳ vọng |
|---|---|
| Command thành công | Có tên command, duration, actor ref, outcome `SUCCESS` |
| Command ném validation exception | Có outcome `FAILURE`, error code `VALIDATION_FAILED` |
| Command ném lỗi bất ngờ | Chỉ ghi mã `UNEXPECTED`, không ghi exception message |
| Argument chứa token giả | Token không xuất hiện trong serialized audit event |
| Input chứa CR/LF | Không tạo thêm dòng log giả |
| Actor reference quá dài | Bị giới hạn độ dài hoặc từ chối |
| Không có trace ID | Dùng giá trị fallback đã quy định |
| Audit sink bị lỗi | Hành vi tuân theo fail-open/fail-closed policy |
| Command method chạy async | Duration được đo theo đúng ranh giới đã công bố |
| Unknown command / parse error | Được ghi bởi instrumentation ở lớp phù hợp nếu yêu cầu audit bao gồm attempt đó |

Ví dụ kiểm tra event bằng mock sink:

```java
String secret = "test-token-do-not-log";

commands.rotateCredential(secret);

ArgumentCaptor<CommandAuditEvent> captor =
        ArgumentCaptor.forClass(CommandAuditEvent.class);
verify(auditSink).append(captor.capture());

CommandAuditEvent event = captor.getValue();
assertThat(event.command()).isEqualTo("customer credential rotate");
assertThat(event.outcome()).isEqualTo("SUCCESS");
assertThat(event.durationMs()).isGreaterThanOrEqualTo(0);
assertThat(event.toString()).doesNotContain(secret);
```

Test cần gọi command bean qua Spring proxy để xác nhận AOP thực sự được áp dụng. Ngoài unit test, thêm một test tích hợp đọc output structured log và kiểm tra token giả không xuất hiện trong bất kỳ field nào.

## 19. Bài tập thực hành

Ứng dụng có ba command quản trị:

1. `customer import --file ...` nhập dữ liệu khách hàng.
2. `customer credential rotate --credential-ref ...` thay credential.
3. `customer delete --customer-id ...` xóa khách hàng.

Hãy thiết kế audit logging với yêu cầu:

- Ghi tên command, actor reference, correlation ID, thời lượng, outcome và error code.
- Không ghi raw argument, token, email, nội dung file hoặc kết quả command.
- Dùng AOP cho method `@Command` và ghi rõ phạm vi mà aspect bao phủ.
- Phân biệt validation failure, not found và unexpected failure bằng mã cố định.
- Dùng structured JSON logging.
- Tạo metric duration và failure count chỉ với tag có cardinality thấp.
- Kiểm thử CR/LF injection, secret leakage, sink failure và command exception.
- Đề xuất cách audit parser error và unknown command ở lớp runner/process.
- Xác định retention, quyền đọc log và chính sách fail-open/fail-closed.

**Kết quả cần nộp:** schema `CommandAuditEvent`, `AuditActorProvider`, aspect hoặc wrapper, sink structured logging, cấu hình logging, test redaction và tài liệu chính sách audit.

## 20. Checklist trước khi bật audit logging

- [ ] Event schema có allowlist trường được phép ghi.
- [ ] Tên command lấy từ metadata tĩnh, không từ raw input.
- [ ] Actor được biểu diễn bằng reference đã được duyệt.
- [ ] Duration đo bằng `System.nanoTime()`.
- [ ] Outcome và error code có tập giá trị cố định.
- [ ] Không log `CommandContext`, `ParsedInput`, `CommandOption.value()` hoặc `getArgs()`.
- [ ] Không log raw output, secret, exception message hoặc stack trace vào audit stream.
- [ ] Label không tin cậy được sanitize và giới hạn độ dài.
- [ ] Structured logging encode dữ liệu đúng định dạng.
- [ ] Correlation ID được dùng nhất quán và không làm metric cardinality tăng.
- [ ] Metrics chỉ dùng tag có số lượng giá trị nhỏ.
- [ ] Đã ghi rõ giới hạn AOP và các lỗi parse/dispatch nằm ngoài phạm vi.
- [ ] Async command được đo đến đúng thời điểm hoàn tất.
- [ ] Audit sink failure tuân theo policy đã công bố.
- [ ] Log store có quyền truy cập, retention và integrity phù hợp.
- [ ] Test chứng minh token/PII giả không xuất hiện trong audit event.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 API — `@Command`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4.0.4 API — `@CommandGroup`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/CommandGroup.html)
- [Spring Shell 4.0.4 API — `CommandContext`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html)
- [Spring Shell 4.0.4 API — `CommandOption`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html)
- [Spring Shell 4.0.4 API — `CommandExecutor`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandExecutor.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Boot — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
