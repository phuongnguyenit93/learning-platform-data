# Checklist bảo mật Java Logging — Tổng kết và thực hành kiểm tra trước production

## 1. Mục đích của checklist

**Bảo mật logging** không chỉ là không in mật khẩu. Một hệ thống log an toàn phải đồng thời bảo đảm:

1. **Bí mật và quyền riêng tư (confidentiality):** không thu thập hoặc tiết lộ thông tin ngoài mục đích được phép.
2. **Tính toàn vẹn (integrity):** kẻ tấn công không dễ giả mạo, sửa hoặc xóa dấu vết; thông tin về người thực hiện và kết quả phải đáng tin.
3. **Tính sẵn sàng (availability):** pipeline không bị log storm, input quá lớn, queue đầy hoặc disk exhaustion làm tê liệt ứng dụng và việc quan sát.
4. **Khả năng truy vết (accountability):** sự kiện quan trọng có actor, action, target, outcome và thời gian phù hợp mà vẫn không lộ secret.
5. **Quản trị vòng đời:** quyền truy cập, truyền/lưu dữ liệu, retention, backup, xóa, xử lý incident và kiểm thử đều có người chịu trách nhiệm.

Chủ đề **“Checklist bảo mật”** thuộc phần **Tổng kết Java Logging**: mục tiêu là biến những nguyên tắc từ code đến collector thành các mục có thể kiểm tra, gắn bằng chứng và dùng trong code review, kiểm thử tích hợp, phát hành và vận hành.

Ví dụ đường đi của một sự kiện:

```text
HTTP / message / scheduled job
             |
             v
       Java business code
             |
       Allowlist + masking
             |
       JUL / SLF4J / Log4j 2
             |
       Encoder + appender
             |
       stdout / file / socket
             |
       sidecar / node collector
             |
     gateway / log storage / SIEM
             |
      search / alert / archive
```

**Bảo mật phải được áp dụng xuyên suốt.** Nếu code đã che token trong một event nhưng HTTP client debug logger, exception cause, MDC hoặc collector debug log lại ghi bản raw, chính sách vẫn thất bại.

### 1.1. “Log an toàn” không đồng nghĩa “log càng ít càng tốt”

Xóa mọi ngữ cảnh có thể khiến không điều tra được xâm nhập. Ngược lại, ghi mọi request/response để dễ debug có thể biến kho log thành kho chứa PII/secret thứ hai. Mục tiêu là **dữ liệu tối thiểu nhưng đủ điều tra**, với schema rõ và đường lưu được kiểm soát.

Ví dụ:

```text
Nguy hiểm:
INFO Login failed, user=alice@example.com password=letmein123

An toàn hơn:
INFO event=auth.login.result outcome=DENIED reasonCode=BAD_CREDENTIALS requestId=req-101
```

`requestId` là ID đã xác thực hoặc do hệ thống tạo tại trust boundary theo chính sách; không coi một header do client tự đặt là bằng chứng danh tính. Mã `BAD_CREDENTIALS` trong log nội bộ nên tránh phân biệt quá chi tiết “tài khoản tồn tại” hay “mật khẩu sai” nếu điều đó tạo kênh suy đoán tài khoản.

## 2. Xác định tài sản, tác nhân và ranh giới tin cậy

Checklist chỉ có ý nghĩa khi dựa vào **threat model**. Các tình huống thường gặp:

| Tác nhân / lỗi | Nguồn rủi ro | Hậu quả |
| --- | --- | --- |
| Client cố tình nhập chuỗi độc hại | Header, request ID, URL, exception message | Giả dòng log, phá JSON, làm ngập log |
| Lập trình viên log toàn bộ DTO | `toString()`, JSON serialization | Lộ password, token, PII |
| Thư viện bên thứ ba | HTTP/SQL debug logging | Ghi raw headers, query hoặc connection string |
| Insider có quyền đọc log | Dashboard, object storage, backup | Truy cập dữ liệu nhạy cảm vượt nhu cầu |
| Collector hoặc transport lỗi | Buffer, retry, TLS, auth | Log mất, trùng, rò trên đường truyền |
| Kẻ có quyền ghi file/agent | Log path, filesystem permissions | Sửa/xóa bằng chứng, chèn sự kiện giả |
| Bùng nổ event hoặc payload dài | Logging hot path, async queue, disk quota | Tăng latency, OOM, hết disk, mất log |
| Cấu hình/retention sai | Level DEBUG, archive, backup | Tiết lộ kéo dài hoặc xóa bằng chứng sớm |

**Boundary cần phân biệt:** người dùng bên ngoài, Java process, filesystem của host/Pod, collector agent, network gateway, nơi lưu và người truy vấn. Hai thành phần cùng Kubernetes Pod có thể dùng chung volume/failure domain; sidecar không phải biên giới tin cậy tuyệt đối chống ứng dụng bị chiếm quyền.

## 3. Checklist A — Thu thập tối thiểu và phân loại dữ liệu

Trước mỗi dòng log, hãy xác định **vì sao sự kiện này cần tồn tại** và dữ liệu nào thực sự cần.

- [ ] Mỗi event có mục đích cụ thể: vận hành, chẩn đoán, bảo mật hoặc audit.
- [ ] Chỉ ghi những trường thật sự hỗ trợ mục đích đó; ưu tiên **allowlist field**.
- [ ] Không log nguyên request body, response body, cookies, headers hoặc toàn bộ Java object theo mặc định.
- [ ] Không log password, OTP, access/refresh token, private key, secret key, cookie phiên hay recovery code.
- [ ] Dữ liệu cá nhân như email/phone/IP/address/user ID được xem xét theo yêu cầu pháp lý và chính sách nội bộ.
- [ ] Nếu cần một phần identifier, có đánh giá rủi ro tái định danh khi kết hợp với các trường khác.
- [ ] Trường mới trong DTO/event phải được phân loại trước khi đi vào log.
- [ ] Source log thuộc framework/HTTP client/JDBC/ORM/message SDK cũng nằm trong phạm vi kiểm kê.
- [ ] Có chính sách riêng cho log của môi trường dev/test/staging/production; không cho phép production vô tình bật verbose payload logging.
- [ ] Dữ liệu kiểm thử chứa **synthetic secrets**, không dùng credential thật để chứng minh khả năng mask.

### 3.1. Ma trận xử lý dữ liệu

| Loại | Ví dụ | Hành động mặc định |
| --- | --- | --- |
| Secret/credential | `Authorization: Bearer ...`, password, OTP, private key | **DROP** hoặc `[REDACTED]` hoàn toàn |
| Dữ liệu cá nhân | Email, phone, địa chỉ, ngày sinh | **OMIT/MASK** khi không cần giá trị |
| Payment sensitive | PAN, CVV, số tài khoản | **Không log raw**, tuân thủ quy định ngành |
| Identifier kỹ thuật | Correlation ID, message ID, request ID | **ALLOW sau validate**, theo trust policy |
| Mã sự kiện | `order.create.result`, `PERMISSION_DENIED` | **ALLOW theo catalog** |
| Số liệu | `durationMs`, status, attempt | **ALLOW với kiểu dữ liệu rõ** |
| Raw object/payload | DTO, headers map, arbitrary metadata | **DROP mặc định** |
| Exception | Class, safe error code, cause/stack message | Phân tách an toàn theo kênh và mức truy cập |
| Audit entity/actor | Authenticated actor, resource, action, outcome | Theo schema audit, không ghi secret value |

**Data minimization mạnh hơn masking.** Nếu không ghi email vào log thì không cần phải tìm mọi biến thể email để che. Ngược lại, nếu business thực sự cần liên hệ các sự kiện theo chủ thể, có thể dùng reference giả danh do hệ thống phát hoặc HMAC có key và scope thích hợp, nhưng cần đánh giá khả năng liên kết và quản lý key.

## 4. Checklist B — Masking, redaction và xử lý mặc định an toàn

Các thuật ngữ nên dùng chính xác:

- **Omit/drop:** không tạo trường ở event.
- **Full redaction:** thay bằng `[REDACTED]`, không để lộ ký tự của secret.
- **Masking:** che toàn bộ hoặc một phần theo chính sách; masking một phần vẫn có thể tiết lộ thông tin.
- **Pseudonymization/tokenization:** thay identifier bằng tag/token có thể liên kết; không mặc định đồng nghĩa dữ liệu ẩn danh.
- **HMAC có khóa:** có thể dùng cho giả danh có thể liên kết; cần bảo vệ key, xoay key và kiểm soát scope.
- **Encryption:** bảo vệ dữ liệu trong trạng thái mã hóa nhưng có thể giải mã; không thay thế data minimization.

Checklist:

- [ ] Quy tắc xử lý field được tập trung, version hóa và review.
- [ ] Field chưa được phân loại **không rơi về raw logging** khi policy không nhận diện được.
- [ ] Nếu masking/serialization bị lỗi, không `logger.error("raw={}", rawValue)` để debug lỗi masking.
- [ ] Không mặc định giữ bốn ký tự cuối của access token, password, private key hoặc cookie.
- [ ] Không dùng SHA-256(email) không khóa rồi tự nhận đó là ẩn danh; giá trị dễ đoán có thể bị dictionary attack.
- [ ] Kiểm tra masking trong formatted message, structured fields, MDC, exception/cause, markers và custom metadata.
- [ ] Kiểm thử cả appender/file/stdout/remote exporter/collector; không chỉ một đường output.
- [ ] Không để một logger cấu hình riêng bypass bộ xây event an toàn.
- [ ] Có cảnh báo schema violation mà **không** ghi lại raw value vi phạm.
- [ ] Có chủ sở hữu chính sách quyết định khi nào được mở rộng allowlist.

### 4.1. Ví dụ chính sách theo event

Một event `profile.update.result` có thể cần `requestId`, authenticated actor ref, outcome và duration; không nhất thiết cần toàn bộ email/phone cũ và mới.

Một event `config.change.result` có thể cần `settingName`, approved `changeId`, actor và outcome, nhưng **không ghi giá trị trước/sau của trường secret**. Thay vào đó có thể ghi `secretChanged=true` hoặc version/hash phù hợp với policy mà không tiết lộ secret.

Một event `payment.capture.result` cần status và safe payment reference. **Không** đưa full PAN/CVV vào log, kể cả trong lỗi validation hay exception message.

## 5. Checklist C — Logging API và code Java

Lỗi bảo mật thường bắt đầu tại lời gọi logger.

### 5.1. Những mẫu nên loại khỏi code review

```java
// Cần tránh: DTO toString() có thể chứa bí mật.
log.info("request={}", request);

// Cần tránh: in header xác thực.
log.debug("Authorization={}", authorizationHeader);

// Cần tránh: query string có thể chứa token.
log.info("URL={}", requestUrlWithQuery);

// Cần tránh: dump toàn bộ environment/system properties.
log.debug("system={}", System.getProperties());

// Cần tránh: exception message từ dependency có thể chứa dữ liệu thô.
log.error("Downstream error: {}", failure.getMessage());
```

Đây là **mảnh mã để nhận diện anti-pattern**, không phải một file Java chạy độc lập. Tên biến/ `log` giả định ứng dụng đã khai báo.

Thay bằng event có schema:

```java
// Mảnh tích hợp: chỉ truyền dữ liệu đã được kiểm tra/chuyển đổi an toàn.
log.info("event=profile.update.result requestId={} outcome={} durationMs={}",
         safeRequestId, outcomeCode, durationMs);
```

**SLF4J placeholder `{}` không phải sanitizer.** Nó không tự che dữ liệu, không ngăn log injection và không bảo đảm output là field JSON riêng. Với SLF4J 2.x, `addKeyValue` có thể mang field cấu trúc, nhưng phải cung cấp **giá trị đã được xử lý** và dùng encoder/provider phù hợp.

### 5.2. Structured logging phải có schema

- [ ] Event name, outcome, error code là giá trị từ catalog; không lấy trực tiếp input bất định.
- [ ] Request/trace IDs được validate độ dài, định dạng và nguồn tin cậy.
- [ ] Các trường có kiểu ổn định, ví dụ `durationMs` là số, `retryable` là boolean.
- [ ] JSONL có **một event một dòng** và escape newline/control chars đúng chuẩn.
- [ ] Không nhận dynamic field names do client quyết định vì dễ phá index/mapping.
- [ ] Có giới hạn số trường, độ dài string và depth của nested objects.
- [ ] Không dùng string concatenation thủ công để tạo JSON production.
- [ ] Formatter/encoder chỉ xuất các trường được chính sách cho phép; test thực tế trên output.

Ví dụ event an toàn:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "WARN",
  "service": "accounts-api",
  "event": "profile.update.denied",
  "requestId": "req-101",
  "actorRef": "actor-42",
  "outcome": "DENIED",
  "reasonCode": "FORBIDDEN"
}
```

Đây là JSON minh họa, không phải dữ liệu lấy từ một request thực. `actorRef` phải đến từ cơ chế xác thực/ủy quyền phù hợp, không tự động lấy từ tên người dùng mà client khai.

## 6. Java 17 chạy độc lập: kiểm tra checklist tại nguồn

Ví dụ sau chỉ dùng JDK 17, không cần Maven/Gradle/SLF4J. Nó mô phỏng **một bộ xây event an toàn** theo allowlist để minh họa đồng thời ba điều:

1. Bí mật và email bị che **trước** khi gọi JUL.
2. Field ngoài allowlist không bao giờ đi vào message.
3. Request ID có newline/chèn dòng giả bị thay bằng `[INVALID]`.

Hai lần ghi có **output cố định** để học viên có thể đối chiếu sau khi chạy.

Lưu file **`SecureLoggingChecklistDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SecureLoggingChecklistDemo {
    private enum Rule { ID, OUTCOME, REASON, MASK, REDACT }

    private static final Map<String, Rule> POLICY = Map.of(
            "requestId", Rule.ID,
            "actorRef", Rule.ID,
            "outcome", Rule.OUTCOME,
            "reasonCode", Rule.REASON,
            "email", Rule.MASK,
            "authorization", Rule.REDACT
    );

    private static final Set<String> EVENTS = Set.of(
            "profile.update.denied", "profile.update.failed"
    );

    private static String safeId(String value) {
        return value != null
                && value.matches("[A-Za-z0-9_-]{1,32}")
                ? value : "[INVALID]";
    }

    private static String safeEnum(
            Set<String> allowed, String value) {
        return value != null && allowed.contains(value)
                ? value : "[INVALID]";
    }

    private static String safeValue(
            String fieldName, Rule rule, String raw) {
        return switch (rule) {
            case ID -> safeId(raw);
            case OUTCOME -> safeEnum(
                    Set.of("DENIED", "FAILED", "SUCCEEDED"), raw);
            case REASON -> safeEnum(
                    Set.of("FORBIDDEN", "STORAGE_TIMEOUT", "NONE"), raw);
            case MASK -> raw == null ? "-" : "[MASKED]";
            case REDACT -> raw == null ? "-" : "[REDACTED]";
        };
    }

    private static String buildSafeEvent(
            String event, Map<String, String> rawFields) {
        String safeEventName = event != null
                && EVENTS.contains(event) ? event : "event.invalid";

        StringBuilder message = new StringBuilder("event=")
                .append(safeEventName);

        for (Map.Entry<String, String> field
                : rawFields.entrySet()) {
            Rule rule = POLICY.get(field.getKey());
            if (rule == null) {
                continue; // Unknown field: fail-closed, không log raw.
            }

            message.append(' ')
                    .append(field.getKey())
                    .append('=')
                    .append(safeValue(
                            field.getKey(), rule, field.getValue()));
        }

        return message.toString();
    }

    private static void assertNoLeaks(String text) {
        String[] forbidden = {
            "alice@example.com", "Bearer secret-token",
            "4111111111111111", "ERROR forged"
        };
        for (String secret : forbidden) {
            if (text.contains(secret)) {
                throw new AssertionError("A test secret leaked");
            }
        }
        if (text.contains("\n") || text.contains("\r")) {
            throw new AssertionError("Log injection detected");
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.secure-checklist");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler stdout = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        logger.addHandler(stdout);
        try {
            Map<String, String> denied = new LinkedHashMap<>();
            denied.put("requestId", "req-101");
            denied.put("actorRef", "actor-42");
            denied.put("outcome", "DENIED");
            denied.put("reasonCode", "FORBIDDEN");
            denied.put("email", "alice@example.com");
            denied.put("authorization", "Bearer secret-token");
            denied.put("rawBody", "card=4111111111111111");

            String a = buildSafeEvent(
                    "profile.update.denied", denied);
            assertNoLeaks(a);
            logger.info(a);

            Map<String, String> failed = new LinkedHashMap<>();
            failed.put("requestId", "req-102\nERROR forged");
            failed.put("actorRef", "actor-43");
            failed.put("outcome", "FAILED");
            failed.put("reasonCode", "STORAGE_TIMEOUT");
            failed.put("authorization", "Bearer secret-token");

            String b = buildSafeEvent(
                    "profile.update.failed", failed);
            assertNoLeaks(b);
            logger.warning(b);
        } finally {
            logger.removeHandler(stdout);
            stdout.close();
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac SecureLoggingChecklistDemo.java
java SecureLoggingChecklistDemo
```

**Stdout chính xác** khi các kiểm tra thành công:

```text
INFO event=profile.update.denied requestId=req-101 actorRef=actor-42 outcome=DENIED reasonCode=FORBIDDEN email=[MASKED] authorization=[REDACTED]
WARNING event=profile.update.failed requestId=[INVALID] actorRef=actor-43 outcome=FAILED reasonCode=STORAGE_TIMEOUT authorization=[REDACTED]
```

Không xuất hiện raw email, Bearer token, số thẻ thử nghiệm hoặc chuỗi `ERROR forged`. Mức `WARNING` là tên level của **JUL**, không phải `WARN` của SLF4J/Logback. Nếu assertion ném `AssertionError`, chương trình **không phải PASS**.

### 6.1. Phân tích ví dụ

- `POLICY` là allowlist **cụ thể cho event demo**, không phải danh sách đủ cho mọi domain.
- `LinkedHashMap` giữ thứ tự chèn, giúp output ổn định khi formatter in một chuỗi text.
- `safeId` giới hạn cú pháp và độ dài ID; nó **không chứng minh ID do nguồn tin cậy cấp**. App thật còn cần kiểm tra nguồn/trust boundary.
- `safeEnum` buộc outcome và reasonCode thuộc catalog được phê duyệt, không để nội dung ngoại lai đi vào các field đó.
- `MASK` và `REDACT` loại bỏ giá trị thực bằng sentinel hằng; không tạo partial masking.
- `rawBody` không nằm trong allowlist nên bị loại. Việc bỏ unknown field an toàn hơn fallback in object.
- Cùng một field `requestId` ở event thứ hai bị chèn newline, nên bị thay `[INVALID]`, không sinh log line giả.
- `assertNoLeaks` là **smoke assertion trên những synthetic secrets đã biết**, không thay thế property tests hoặc kiểm tra các đường log khác.
- Handler stdout chủ động không dùng parent handlers, timestamp hay formatter mặc định, giúp stdout có thể tái lập.
- Ví dụ **không chứng minh** log remote được lưu, audit có integrity hay encoder JSON production đã an toàn.

### 6.2. Giới hạn cố ý của bản thực hành

**Không copy nguyên lớp demo làm thư viện bảo mật cho production** nếu chưa thiết kế threat model và API phù hợp. Nó chưa xử lý nested object, invalid Unicode, field-level JSON serialization, toàn bộ Unicode normalization, third-party logging, MDC, Throwable, sidecar, archive hoặc dynamic config. Một regex chỉ kiểm tra chữ/số/dấu gạch cho `requestId` cũng không nhận diện mọi secret có dạng ký tự hợp lệ.

Với code thật, nên tập trung chính sách theo **loại sự kiện**, tạo object chỉ chứa giá trị đã kiểm duyệt, hạn chế API nhận `Object` tùy ý, thêm kiểm thử negative và chạy kiểm tra trên output tại sink đích.

## 7. Checklist D — Chống log injection và data poisoning

**Log injection** xảy ra khi attacker-controlled input được nối vào message hoặc log field theo cách làm parser/người xem hiểu sai ranh giới, nội dung hoặc ý nghĩa của sự kiện.

Ví dụ input:

```text
req-102
ERROR user=admin action=grantAccess outcome=SUCCEEDED
```

Nếu ứng dụng in raw requestId trong text log, phần sau newline có thể trông như một event `ERROR` giả. Ngay cả khi dùng JSON, một serializer lỗi hoặc parser/collector cấu hình sai vẫn có thể bị lợi dụng.

Checklist:

- [ ] Không ghép raw user input trực tiếp vào text format; validate/normalize hoặc encode.
- [ ] Escape newline/CR/tab/quote/backslash và control characters phù hợp với format.
- [ ] Nếu dùng JSONL, **một event phải là một JSON object trên một dòng**; dùng JSON encoder có escaping chuẩn.
- [ ] Không để user input quyết định field name, logger name, file path, index name, storage bucket hay destination.
- [ ] Không tin level/status từ client như bằng chứng hệ thống đã làm điều đó.
- [ ] Giới hạn input size và field count trước logging để chống memory/CPU exhaustion.
- [ ] Test CR, LF, CRLF, Unicode, chuỗi quote/backslash, percent-encoding và giá trị cực dài.
- [ ] Với multiline exception, cấu hình collector nhận diện đúng một event thay vì tách stack trace thành các bản ghi độc lập.
- [ ] Với terminal log viewer, cân nhắc escape control/ANSI sequences có thể làm rối cách hiển thị.
- [ ] Ngăn log data poisoning (dữ liệu độc hại khiến truy vấn/alert sai) bằng schema và nguồn trường đáng tin.

**SLF4J `{}` không phải cơ chế chống injection.** Placeholder chỉ định dạng tham số; nếu formatter xuất raw newline, log text vẫn có thể bị chia dòng. JSON encoder chuẩn giúp escape cú pháp nhưng không tự làm input trở thành nguồn đáng tin để quyết định cấp quyền.

## 8. Checklist E — Exception, stack trace và root cause

**Giữ nguyên cause chain** giúp điều tra lỗi, nhưng exception message từ HTTP client, database driver, parser hoặc thư viện có thể mang bí mật.

- [ ] Không bỏ nguyên nhân gốc khi wrap: `new ServiceException("context", original)` khi phù hợp.
- [ ] Không mặc định in `Throwable.getMessage()` của dependency vào message công khai.
- [ ] Kiểm tra đường render **wrapper, cause, suppressed exceptions** và MDC/structured arguments.
- [ ] Phân loại exception bằng **error code ổn định**, không dùng full exception message làm metric label.
- [ ] Chỉ log stack trace ở boundary thực sự cần, tránh nhân bản `ERROR` ở mọi tầng.
- [ ] Validation errors dự kiến không tự động in stack trace dài cho mỗi request.
- [ ] HTTP/gRPC public response không chứa raw stack trace, file path, SQL query, token hay host nội bộ.
- [ ] Kênh log giàu chẩn đoán có ACL/retention thích hợp và renderer được kiểm thử.
- [ ] Không serialize `Throwable` bằng generic JSON object mapper rồi phát cả object graph ngoài kiểm soát.
- [ ] Không làm mất trạng thái của `InterruptedException`; rethrow hoặc restore interrupt theo contract.

Ví dụ mảnh mã tích hợp trong JUL:

```java
// failure là Throwable được phép đưa vào kênh log nội bộ thích hợp.
logger.log(java.util.logging.Level.SEVERE,
        "event=order.persist.failed errorCode=STORAGE_UNAVAILABLE",
        failure);
```

**Cẩn trọng:** truyền `Throwable` giúp backend in stack/cause, nhưng **không tự che** exception message có token. Nếu không được phép xuất raw Throwable, có thể ghi safe summary (`exceptionType`, `errorCode`) ở kênh thường và thiết kế quy trình điều tra hạn chế quyền cho chi tiết sâu. Việc cắt stack trace toàn bộ có thể làm mất khả năng xử lý sự cố; đây là quyết định threat model, không phải một regex chữa mọi lỗi.

## 9. Checklist F — HTTP, messaging, jobs và MDC

### 9.1. HTTP

- [ ] Access event ghi method, route **template**, status, duration, requestId, outcome phù hợp.
- [ ] Không log raw `Authorization`, `Cookie`, `Set-Cookie` hay credential query parameters.
- [ ] Không bật generic request/response body logging ở production nếu chưa có policy.
- [ ] Không tin `X-Forwarded-For`, user-supplied request ID hoặc User-Agent mà không có trust/validation.
- [ ] Không ghi `outcome=SUCCEEDED` trước khi response/business transaction thật sự đạt mốc tương ứng.
- [ ] Không biến HTTP `202 Accepted` thành khẳng định job downstream đã hoàn tất.
- [ ] Dùng error code và request ID trong response công khai thay vì stack trace.

### 9.2. Message consumers

- [ ] Có safe message ID/consumer group/topic/queue, attempt, event, outcome và errorCode.
- [ ] Không log toàn bộ message body hoặc headers khi payload có thể chứa dữ liệu nhạy cảm.
- [ ] Nếu retry/redelivery, phân biệt message ID logic với delivery attempt hoặc offset/broker coordinate.
- [ ] Không coi “processing succeeded”, “ack requested” và “offset committed” là một trạng thái giống nhau.
- [ ] Có idempotency/transaction handling khi message redelivered, không dựa log để chống duplicate side effect.
- [ ] DLQ/quarantine records cũng có ACL và retention vì có thể chứa payload nhạy cảm.
- [ ] Collector và broker client internal DEBUG không in token, password hoặc nội dung message thô.

### 9.3. Scheduled jobs / batch

- [ ] Có `jobName`, `runId`, `attempt`, outcome, counts và duration theo schema.
- [ ] Không dump bản ghi dữ liệu đầu vào/đầu ra để thay thế summary.
- [ ] Nếu batch partial success, không gắn `SUCCEEDED` cho cả job.
- [ ] Khi job fail, scheduler nhận đúng trạng thái thất bại/retry theo contract.
- [ ] Backup/export logs không chứa đường dẫn lộ secret hoặc tên file chứa PII ngoài policy.

### 9.4. MDC và context propagation

- [ ] Chỉ đặt các field allowlisted, ngắn, đã validate vào SLF4J `MDC` hoặc Log4j 2 `ThreadContext`.
- [ ] **Restore/clear trong `finally`** khi thread pool tái sử dụng thread.
- [ ] Dùng cơ chế propagation phù hợp cho executor, `CompletableFuture`, Reactor/WebFlux, scheduler hoặc virtual threads nếu có.
- [ ] Không đưa raw headers, JWT hoặc account object vào thread-local context.
- [ ] `traceId` hỗ trợ tương quan nhưng không phải authenticated principal.
- [ ] Không dùng raw requestId/userId/traceId làm metric label cardinality cao.

Một mảnh tích hợp SLF4J:

```java
import org.slf4j.MDC;

// validatedRequestId được ứng dụng tạo/kiểm tra trước khi dùng.
String previous = MDC.get("requestId");
try {
    if (validatedRequestId == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", validatedRequestId);
    }

    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

Đây không phải file độc lập: cần dependency SLF4J, biến và method `processRequest()` thực tế. Mục đích là **không làm context của request trước rò sang request sau**.

## 10. Checklist G — Truyền, lưu và quyền truy cập log

Một event đã che vẫn có thể mang metadata nhạy cảm; phải bảo vệ đường đi và nơi lưu.

| Ranh giới | Checklist |
| --- | --- |
| **Java → stdout/file** | Quyền file, directory, UID/GID; không ghi vào đường dẫn world-readable |
| **Java → remote appender** | TLS, certificate validation, authentication, timeout/retry hợp lý |
| **Sidecar → gateway** | TLS/mTLS khi phù hợp, identity tối thiểu, egress policy |
| **Gateway → storage** | IAM/RBAC, tenant isolation, encryption at rest, key management |
| **Search/dashboards** | Least privilege, truy vấn được audit, export/download controls |
| **Archive/backup** | Encryption, ACL và retention nhất quán với nguồn |
| **Dev/staging** | Không copy dữ liệu production nhạy cảm vào log test vô kiểm soát |

- [ ] Quyền đọc log phân theo vai trò; người không cần xem PII/stack trace không được cấp quyền mặc định.
- [ ] Có chính sách hạn chế truy cập operator/admin, break-glass và ghi nhận truy cập log khi cần.
- [ ] TLS được xác minh thực sự, không tắt certificate verification cho nhanh.
- [ ] Secret kết nối log gateway được lưu qua secret manager/workload identity phù hợp, không hardcode vào `logback.xml`, YAML công khai hoặc environment dump.
- [ ] File log, archive và temporary spool có quyền/owner đúng; không bị service không liên quan đọc được.
- [ ] Container dùng `runAsNonRoot`, filesystem security context và mount read-only khi tương thích.
- [ ] Không cấp service account token/Kubernetes API privileges cho collector nếu không cần.
- [ ] Phân vùng log nhạy cảm theo tenant hoặc domain theo chính sách truy cập.
- [ ] Có cơ chế thu hồi/rotate key, kiểm tra ảnh hưởng tới dữ liệu mã hóa lịch sử.
- [ ] Không cho phép một API export log tùy ý không xác thực hoặc không giới hạn dữ liệu.

**Encryption in transit và encryption at rest không che dữ liệu khỏi người dùng hợp lệ được cấp quyền đọc.** Vì vậy masking/data minimization vẫn cần thiết, song song với RBAC, encryption, retention và audit truy cập.

## 11. Checklist H — Retention, xóa và tính riêng tư theo thời gian

Dữ liệu nhạy cảm có thể tồn tại ở nhiều nơi:

```text
app.log
  -> rolled app.1.log.gz
  -> node/sidecar spool
  -> gateway buffer
  -> search index
  -> object storage/archive
  -> backup/snapshot
  -> export CSV / screenshots / incident tickets
```

- [ ] Có retention policy theo **mục đích và loại log**: debug, access, security, audit.
- [ ] Giới hạn thời gian lưu theo quy định và nhu cầu điều tra; không lưu vô thời hạn vì tiện.
- [ ] File rotation/cleanup thực tế đáp ứng policy, không chỉ có `maxHistory` trên giấy.
- [ ] Backups, snapshots, DLQ, collector buffers, exported dashboards cũng được tính trong phạm vi dữ liệu.
- [ ] Có quy trình xóa/giảm lưu khi dữ liệu không còn mục đích được phép, phù hợp nghĩa vụ giữ bằng chứng nếu có.
- [ ] Khi phát hiện token/PII đã rò, đánh giá cả dữ liệu **đã được ship và đã được backup**, không chỉ thay masking code.
- [ ] Có phương án hạn chế truy cập, rotate/revoke credentials bị lộ và xử lý incident theo mức độ thực tế.
- [ ] Retention đủ để điều tra sự cố và audit bắt buộc, nhưng không quá dài cho diagnostic logs.
- [ ] Thay đổi retention được thử trên file/period cũ; không xóa nhầm audit bắt buộc.
- [ ] Khi xóa ở một sink, không mặc định đã xóa mọi bản sao trên hệ thống khác.

Retention là một chính sách cần **người chịu trách nhiệm và bằng chứng kiểm tra**. Trong hệ thống có yêu cầu pháp lý, phải cân bằng quyền xóa, legal hold và quy định lưu giữ thực tế; không áp một con số chung cho mọi trường hợp.

## 12. Checklist I — Audit log, danh tính đáng tin và integrity

**Diagnostic log** phục vụ debug và quan sát. **Audit log** chứng minh một hành động bảo mật/nghiệp vụ nhạy cảm đã được thực hiện hoặc thử thực hiện, với yêu cầu riêng về tính đầy đủ và chống sửa xóa.

Một audit event có thể gồm:

```json
{
  "event": "security.permission.change.result",
  "eventId": "evt-1001",
  "actorId": "admin-7",
  "action": "REVOKE_PERMISSION",
  "targetType": "USER_ROLE",
  "targetRef": "role-42",
  "outcome": "SUCCEEDED",
  "changeId": "chg-21",
  "timestamp": "2026-11-10T02:00:00Z"
}
```

Đây là schema minh họa; `actorId` phải đến từ **authenticated security context** và được kiểm soát truy cập, không sao chép tham số `user=admin-7` do client gửi. Nếu không biết actor, ghi trạng thái `UNKNOWN` rõ ràng theo chính sách, không bịa danh tính.

- [ ] Audit các hành động quan trọng: login/deny, phân quyền, thay đổi cấu hình, tạo/xóa khóa, export dữ liệu, truy cập đặc quyền.
- [ ] Có cả **attempt** và **result/outcome** khi cần, gồm thành công, từ chối và lỗi kỹ thuật.
- [ ] Có eventId/operationId để đối chiếu và phát hiện duplicate.
- [ ] Thời gian được lấy từ nguồn đáng tin/đồng bộ và phân biệt `occurredAt` với `ingestedAt` khi cần.
- [ ] Đã định nghĩa rõ sự kiện `SUCCEEDED` sau mốc nào: commit, ack hay chỉ nhận yêu cầu.
- [ ] Các trường secret không được ghi raw trong before/after; có thể ghi `secretChanged=true`.
- [ ] Đường ghi audit có kiểm soát quyền ghi/đọc tách biệt, retention và theo dõi tình trạng.
- [ ] Có cơ chế **tamper-evidence** phù hợp như storage append-only/WORM, hashing/signing có key được quản lý, hoặc bảo vệ hạ tầng; không chỉ dựa vào tên file.
- [ ] Nếu audit sink lỗi, policy quy định fail-open/fail-closed theo loại nghiệp vụ và được thử.
- [ ] Có đối soát giữa business action và audit evidence ở đúng transaction boundary khi hệ thống yêu cầu tính đầy đủ.
- [ ] Không dùng `logger.info(...)` best-effort như cam kết rằng audit đã lưu durable.

**Hash chain không tự chống được attacker có toàn quyền với mọi khóa/file.** Integrity cần đi kèm quản lý khóa, nguồn timestamp tin cậy, tách quyền, append-only storage và kiểm chứng độc lập. Tính không thể chối bỏ cũng không tự có chỉ vì một trường `actorId` trong JSON.

## 13. Checklist J — Chống từ chối dịch vụ qua logging

Một hệ thống có thể bị tấn công gián tiếp qua lượng log:

- Attacker lặp request lỗi để kích hoạt stack trace lớn.
- Input hàng MB được đưa vào logger.
- DEBUG/TRACE bất ngờ mở trên hot path.
- Async logging queue đầy, writer block hoặc drop.
- Collector mất network làm file backlog/ephemeral disk tăng.
- Regex masking tốn CPU hoặc có backtracking tệ.
- Logger/encoder tạo object lớn, làm tăng GC pause.
- Query tìm log với nhãn/cấu trúc cardinality cao làm nghẽn storage/index.

Checklist:

- [ ] Giới hạn độ dài string, số field, nesting depth và size của log event.
- [ ] Có rate limiting/sampling **chỉ cho các loại diagnostic events phù hợp**.
- [ ] Không sampling tùy tiện đối với audit events bắt buộc.
- [ ] Theo dõi log rate, dropped events, async queue depth, encoder latency và bytes/event.
- [ ] Có disk quota, rotation và retention được test; khi disk đầy có chính sách rõ.
- [ ] Có buffer size/retry/backoff giới hạn cho remote logging và collector.
- [ ] Có phát hiện log storm (một lỗi lặp nghìn lần) mà vẫn giữ event tổng hợp/cảnh báo đủ điều tra.
- [ ] Không sử dụng `String.format`, JSON serialization hoặc `toString()` cực đắt khi level đang tắt nếu có thể tránh.
- [ ] Không để logger bị lỗi kéo theo recursive logging vào chính logger đó.
- [ ] Khi log sink lỗi, còn **kênh metrics/health độc lập** để cảnh báo, không chỉ in `ERROR logging failed` vào sink hỏng.

### 13.1. Một số quyết định có đánh đổi

**Block hay drop?** Với diagnostic logs, có thể chọn drop có metric khi queue đầy để giữ latency của ứng dụng. Với audit/security logs, mất bản ghi có thể không chấp nhận được và cần đường lưu bền vững hoặc fail-closed. Không áp chính sách “không bao giờ block” hay “không bao giờ drop” cho mọi log.

**Cắt stack trace?** Giảm bytes và chi phí có thể hợp lý, nhưng cắt mất cause chain sẽ khó điều tra. Dùng chiến lược theo level/event và bảo mật; thử với exception sâu, suppressed exceptions và Unicode.

**Giảm chi phí bằng cách tắt log?** Có thể dùng log level/sampling, nhưng tránh tắt security/audit event bắt buộc theo quy định hoặc chính sách nội bộ.

## 14. Checklist K — Cấu hình và thay đổi runtime

Bản thân **cấu hình logging** là một surface bảo mật:

| Nhóm cấu hình | Rủi ro |
| --- | --- |
| Log level | Bật DEBUG khiến raw payload/SQL/header bị phát |
| Appender destination | Chuyển log sang URL/bucket không tin cậy |
| Encoder/layout | Bỏ masking, đổi JSONL thành multiline, mất escaping |
| Filters | Vô tình loại security events hoặc làm mất exception |
| Retention | Xóa sớm chứng cứ hoặc lưu PII quá lâu |
| Remote endpoint/auth | Tắt TLS validation hoặc lộ credentials |
| Audit logger | Ghi vào sink chung có quyền sửa/xóa |
| Async buffers | Drop/block không đúng policy |

- [ ] Cấu hình log được review như cấu hình bảo mật, có version và rollback.
- [ ] Thay đổi runtime level/destination có authz/approval theo chính sách.
- [ ] Có log/audit về **ai yêu cầu, giá trị nào đổi ở mức an toàn, outcome và changeId**, không ghi secret value.
- [ ] Cấu hình masking không bị tắt chỉ vì bật DEBUG hoặc đổi appender.
- [ ] Không hardcode secrets trong XML/YAML hoặc log trạng thái config chứa secrets.
- [ ] Có kiểm thử startup/reload khi config lỗi: backend có thể fallback không an toàn?
- [ ] Với cluster, kiểm tra cấu hình nhất quán giữa replica sau rollout.
- [ ] Kiểm tra file permissions, path traversal và symbolic links theo threat model khi destination có thể cấu hình.
- [ ] Có cảnh báo khi một security-critical logger bất ngờ ngừng phát event.
- [ ] Sử dụng dependency/encoder/collector bản phù hợp, theo dõi cập nhật bảo mật.

Việc thay đổi config cần phân biệt **success**, **denied**, **failed**, **partial** và **rolled back**. Đừng ghi `AUDIT_APPLIED` khi một nửa replica vẫn dùng cấu hình cũ.

## 15. Checklist L — Third-party dependencies và framework integration

Ứng dụng Java thực tế có thể dùng nhiều library cùng ghi log: Spring Boot, Tomcat/Jetty, JDBC driver, Hibernate, HTTP clients, Kafka, RabbitMQ, scheduler, SDK cloud.

- [ ] Có inventory logging frameworks, bindings/providers, encoders và exporter đang sử dụng.
- [ ] Không vô tình có nhiều SLF4J bindings/providers tạo routing/logging khác dự kiến.
- [ ] Kiểm tra library debug mode có dump `Authorization`, SQL bind values, full HTTP body hoặc raw message payload không.
- [ ] Configuration của framework-level request logging và access log được review.
- [ ] Masking policy che được event từ library hoặc chọn lọc/hạn chế logger của library.
- [ ] Có test khi nâng version encoder/provider, vì tên field và Throwable rendering có thể đổi.
- [ ] Với agent/sidecar, kiểm tra parse errors không làm nó log raw invalid input ra stdout.
- [ ] Container runtime/node collector không thu thập bản raw từ một appender khác.
- [ ] Có danh mục đích xuất log; không vô tình gửi cùng một event qua hai route.
- [ ] Quét vulnerability/SBOM cho logging dependencies và collector image theo chính sách cập nhật.

Không coi một dependency là nguy hiểm chỉ vì nó có chế độ DEBUG; rủi ro phụ thuộc cách ứng dụng bật, cấu hình, dữ liệu nó nhìn thấy và sink cuối.

## 16. Checklist M — Kiểm thử bảo mật có thể lặp lại

Một checklist tốt phải đi kèm **bằng chứng kiểm thử**, không chỉ tick bằng cảm tính.

### 16.1. Unit tests cho policy

| Case | Assertion |
| --- | --- |
| Unknown field | Không có tên/và giá trị raw trong event |
| Email/phone | Không có PII raw, sentinel đúng policy |
| Password/token/cookie | Bỏ hoặc full redact, không giữ suffix |
| Request ID dài > giới hạn | Reject hoặc safe fallback, không in raw |
| CR/LF/tab và quotes | Không tạo dòng log giả, JSON vẫn hợp lệ |
| Value null hoặc type bất ngờ | Theo schema, không tự dump `toString()` |
| Nested object chứa secret | Không serialize object raw |
| ErrorCode ngoài catalog | Không xuất giá trị tùy ý |
| DTO thêm field mới | Test thất bại nếu field chưa phân loại mà được log |
| Exception message chứa URL/token | Không phát raw ra sink không được phép |

### 16.2. Integration tests cho Java logging backend

- [ ] Dùng đúng encoder/formatter production trong test, không chỉ formatter stub.
- [ ] Bắt event ở Logback/Log4j 2/JUL appender hoặc file test riêng.
- [ ] Với JSONL, parse bằng JSON parser thật và assert field types.
- [ ] Kiểm tra message, arguments, MDC, Throwable, cause và suppressed exceptions.
- [ ] Bật DEBUG/TRACE trong môi trường test để tìm các đường raw mới xuất hiện.
- [ ] Tạo concurrency và thread-pool reuse để phát hiện MDC/context leak.
- [ ] Test rotation, compression và startup/reload; archive không lộ dữ liệu raw.
- [ ] Tạo synthetic canary secret khác nhau cho từng đường đi để biết nguồn leak.
- [ ] Kiểm tra không có secret trong status/error log của chính logging backend.

### 16.3. End-to-end tests qua collector/storage

1. Phát một tập `eventId` và synthetic canary theo kịch bản.
2. Đợi dữ liệu đến sink có xác nhận theo semantics hệ thống.
3. Query **mọi index/bucket/tenant** thuộc phạm vi của luồng thử nghiệm.
4. Tìm sự xuất hiện của canary gốc, kể cả bản bị URL/base64 encode khi threat model yêu cầu.
5. Xác minh masking/field schema và event counts.
6. Thử retry, network timeout/429/503, backlog đầy, collector restart và Pod replacement.
7. Kiểm tra missing/duplicate events theo ID, không chỉ số lượng dòng.
8. Kiểm tra rotate/retention và file chưa ship bị xóa có thể tạo mất log không.
9. Kiểm tra quyền người dùng không được cấp quyền có đọc hoặc export được logs không.
10. Ghi bằng chứng test không chứa secret thật, chỉ canary tổng hợp.

**Không dùng secret production làm canary.** Nếu test thất bại, ticket, ảnh chụp dashboard và CI artifact cũng có thể là nơi nhân bản dữ liệu nhạy cảm.

## 17. Checklist N — Bảo mật của alert và dashboard

Log đã được lưu an toàn vẫn có thể rò qua các kênh phụ:

- Alert gửi toàn bộ exception/payload qua email hoặc chat nhóm rộng.
- Dashboard mặc định cho mọi người xem query chứa PII.
- Export CSV gửi ra máy cá nhân không được quản lý.
- API search logs không có tenant filtering hoặc rate limit.
- Metrics lấy `userId`/`requestId`/message làm label high-cardinality và tiết lộ hoạt động cá nhân.
- Saved searches hoặc incident tickets chứa token đã được copy từ log.

Checklist:

- [ ] Alert template chỉ chứa **safe event code, service, severity, correlation ID** và link có kiểm soát quyền.
- [ ] Dashboard/search API thực thi RBAC/ABAC/tenant isolation phù hợp.
- [ ] Không đưa raw exception/PII vào notification nếu không cần.
- [ ] Có kiểm soát download/export, sharing và audit của truy vấn nhạy cảm.
- [ ] Không dùng dynamic identifiers làm metric labels; labels cần tập giá trị hữu hạn.
- [ ] Link vào log phải tuân thủ quyền người xem, không đưa token truy vấn trong URL công khai.
- [ ] Có kiểm soát retention của alert notifications và incident attachments.
- [ ] Công cụ incident response có quy trình xử lý bản ghi chứa credential bị lộ.

Một correlation ID có thể là dữ liệu liên kết hành vi; đừng coi nó luôn vô hại chỉ vì không có tên/email.

## 18. Bảng kiểm nghiệm thu theo vai trò

Có thể dùng ma trận sau trong PR review hoặc security gate:

| Vai trò | Việc cần xác nhận | Bằng chứng |
| --- | --- | --- |
| **Developer** | Event schema, safe fields, exception handling, MDC clear/restore | Unit test, code review |
| **Tech lead** | Log levels, retention phù hợp domain, không double logging | Config review, design decision |
| **Security/AppSec** | Threat model, PII/secret classification, log injection, key/access policy | Security review, canary test |
| **SRE/Platform** | TLS, quotas, rotation, backpressure, collector health, storage ACL | Integration run, dashboards |
| **Data/Compliance** | Retention, data lifecycle, audit obligations, access records | Policy/retention evidence |
| **Release owner** | CI gates, rollback, version compatibility, secret leak response | Release checklist và test reports |

Những mục này là **trách nhiệm gợi ý**, không phải chức danh bắt buộc của mọi tổ chức. Với dự án nhỏ, một người có thể đảm nhiệm nhiều vai trò; điều quan trọng là **có chủ sở hữu thực**.

### 18.1. Phân loại mức ưu tiên lỗi

**Block release** khi có bằng chứng:

- Password/token/private key xuất hiện raw trong log/collector/sink ngoài phạm vi được phép.
- Client input có thể tạo sự kiện giả mạo dẫn tới quyết định bảo mật sai hoặc gây rò dữ liệu.
- Security-critical audit bị mất hoàn toàn không có policy/biện pháp thay thế.
- Log storage/sink không có authz thích hợp hoặc mở public.
- TLS verification bị vô hiệu với đường gửi log nhạy cảm.
- Biện pháp masking lỗi và **fallback sang raw**.

**Cần kế hoạch sửa có thời hạn** khi:

- Một số diagnostic events thiếu errorCode hoặc correlation context nhưng không lộ dữ liệu.
- Retention/rotation thiếu metrics hoặc có rủi ro capacity chưa trực tiếp xảy ra.
- Dữ liệu đã được che nhưng schema không nhất quán giữa service.
- Alert có quá nhiều noise, chưa kiểm soát volume.
- Kiểm thử failover chưa đủ cho tất cả đường collector.

Mức ưu tiên thực tế cần căn cứ mức độ ảnh hưởng, dữ liệu và nghĩa vụ của tổ chức; bảng này là một khung tham khảo.

## 19. Quy trình xử lý khi phát hiện thông tin nhạy cảm trong logs

Khi đã thấy một token hay dữ liệu cá nhân lọt vào log, **chỉ sửa code không đủ**, vì log cũ còn có thể lưu ở nhiều nơi.

1. **Xác nhận phạm vi:** xác định event source, thời gian, môi trường và loại dữ liệu. Không tiếp tục copy raw token qua ticket/chat.
2. **Hạn chế lan truyền:** tắt hoặc chỉnh cấu hình lời gọi log gây leak theo quy trình change control.
3. **Kiểm soát quyền truy cập:** hạn chế tìm kiếm/export tại các sink liên quan trong khi điều tra.
4. **Thu hồi/rotate secret bị lộ** khi phù hợp; token đã lộ không còn được coi an toàn chỉ vì đã bị xóa khỏi log mới.
5. **Đánh giá toàn bộ bản sao:** active files, rolled archives, shipper spool, search indexes, object storage, backup, notification, CI artifacts.
6. **Áp dụng xóa/retention/incident response** phù hợp chính sách pháp lý và điều tra; lưu bằng chứng tối thiểu được bảo vệ nếu phải giữ.
7. **Bổ sung automated tests** với synthetic canary cho đúng đường gây leak.
8. **Đánh giá nguyên nhân hệ thống:** do raw DTO, encoder, config DEBUG, third-party library, exception renderer hay collector?
9. **Rà lại quyền truy cập và audit truy vấn** nếu có nguy cơ đã bị đọc bởi người không có thẩm quyền.
10. **Theo dõi sau sửa:** quét canary và kiểm tra ở sink đích, không chỉ unit test phía JVM.

Không viết câu trả lời incident chung chung “đã mask rồi” nếu dữ liệu lịch sử chưa được đánh giá. Log có thể được replicate sang bucket/index/backup mà source application không biết.

## 20. Những hiểu lầm phổ biến

### 20.1. “Có HTTPS/TLS rồi không cần mask”

TLS bảo vệ trên đường truyền nhưng storage, dashboard, archive và người dùng được cấp quyền vẫn nhìn thấy nội dung. Data minimization/masking vẫn cần.

### 20.2. “JSON encoder tự xóa password”

Serializer chủ yếu đảm bảo cú pháp và escaping. Nó không tự biết dữ liệu nào nhạy cảm và ai được phép đọc. Field policy là việc riêng.

### 20.3. “Regex ở collector che được mọi secret”

Regex dễ bỏ sót encoding, field names lạ, nested values và malformed messages. Collector có thể nằm **sau** nơi raw data đã ghi disk.

### 20.4. “Ẩn bốn ký tự cuối là luôn an toàn”

Partial masking có thể đủ để nhận diện trong một tập dữ liệu nhỏ, nhất là email/phone. Secret như JWT, API key hoặc password thường cần drop/full redact.

### 20.5. “SHA-256(email) là ẩn danh hoàn toàn”

Không. Email có thể bị đoán và hash dễ bị tấn công từ điển. HMAC có khóa cũng vẫn linkable và cần privacy assessment.

### 20.6. “Log DEBUG đang tắt nên không có rủi ro”

Một thay đổi runtime config hoặc debug trong incident có thể bật DEBUG. Quy tắc không log secret phải đúng ở **mọi mức log**.

### 20.7. “Log có actorId thì chứng minh đúng người làm”

Không nếu actorId được client đưa vào hoặc process bị chiếm quyền. Audit cần trusted authentication context và integrity controls.

### 20.8. “MDC tự truyền qua mọi tác vụ bất đồng bộ”

Không. Cơ chế propagation thay đổi theo thread pool, framework và version. Nếu không dọn context, có thể gắn nhầm user/request ID.

### 20.9. “Logback và Log4j 2 có cùng cấu hình”

Không. Provider, appender, encoder, filters và MDC/ThreadContext có API/semantics riêng; phải test trên backend/version thật.

### 20.10. “Cứ log càng nhiều càng điều tra tốt”

Quá nhiều log có thể tăng PII, tạo cost, flooding và giảm signal-to-noise. Log event có ngữ cảnh, schema, rate policy và bảo mật thường tốt hơn dump toàn bộ payload.

### 20.11. “Đã đọc log file tức là hệ tập trung đã lưu”

Không. File tail offset, local buffer, send attempt, remote acknowledgment và storage durability là các mốc riêng. Rotation/retention có thể xóa backlog chưa ship.

### 20.12. “Audit log chỉ cần `logger.info`”

Không với các yêu cầu chống sửa xóa hoặc chứng minh transaction. Audit có thể cần sink append-only, acknowledgement, quyền tách biệt, đối soát và retention bắt buộc.

## 21. Checklist tối giản để dán vào Pull Request

Có thể sử dụng nguyên văn bảng kiểm này trong mô tả PR:

```markdown
### Java Logging Security Gate
- [ ] Không log password, token, cookie, private key, OTP hoặc raw DTO.
- [ ] Chỉ các field đã được phân loại mới vào log; unknown field fail-closed.
- [ ] ID/client input được validate, giới hạn độ dài, escape CR/LF/control.
- [ ] JSONL/structured encoder và Throwable/MDC không làm lộ secret.
- [ ] Không có logger/appender/collector nào ghi bản raw song song.
- [ ] Security event có actor đáng tin, action, target, outcome, thời gian.
- [ ] Log level/retention/remote endpoint chỉ đổi qua change control.
- [ ] TLS, storage ACL, least privilege và retention được kiểm tra.
- [ ] Có capacity/queue/disk backpressure metrics và alert độc lập.
- [ ] Unit, integration và end-to-end synthetic secret canary tests PASS.
- [ ] Lỗi masking không fallback sang ghi raw.
- [ ] Nếu audit bắt buộc, có durability/integrity và failure policy riêng.
```

Bảng kiểm trên là **gate khởi đầu**, không thay thế threat model chi tiết với payment, healthcare, government hoặc những quy định riêng. Điểm quan trọng là mỗi mục quan trọng phải có bằng chứng — file config, test, runbook hoặc quan sát thực tế.

## 22. Cách tổ chức một buổi rà soát bảo mật logging

Một buổi review hiệu quả có thể làm theo trình tự:

1. **Chọn một request flow** chứa dữ liệu nhạy cảm, như login, profile update hoặc payment.
2. Liệt kê mọi điểm phát log: controller, filter, service, repository, HTTP client, DB driver, message consumer, job, exception handler.
3. Lần theo đường output: console, file, sidecar, gateway, search index, archive, alert.
4. Dùng synthetic canary đi qua flow, kiểm tra log có dữ liệu gốc ở bất kỳ chặng nào không.
5. Kiểm tra logs khi request hợp lệ, validation fail, permission denied, timeout, retry, transaction rollback, shutdown.
6. Xác nhận event context, actor, outcome đáng tin và boundary tương ứng với dữ liệu.
7. Cố ý thử input có quote, newline, control chars, payload dài, nested secret và exception chứa URL/token.
8. Kiểm tra rotation/restart, collector mất network và quyền đọc/export logs.
9. Ghi rủi ro, mức ưu tiên và owner; sửa code/config/test, chạy lại.
10. Chỉ phê duyệt khi những mục **bắt buộc** có bằng chứng đáp ứng, không chỉ tick checklist.

Một câu hỏi cuối đáng dùng khi review: **“Nếu attacker điều khiển toàn bộ các string đầu vào của request và xem được một phần dashboard, họ có thể làm ai đó tin vào một hành động không xảy ra, hay lấy lại thông tin nhạy cảm từ log không?”** Đồng thời phải hỏi: **“Nếu log pipeline nghẽn hoặc bị sửa, ta có phát hiện được và có chứng cứ đáng tin nào còn lại?”**

## 23. Tóm tắt nguyên tắc và thứ tự ưu tiên

Để tổng kết Java Logging Security Checklist:

1. **Không tạo secret trong log** là tuyến phòng thủ mạnh nhất.
2. **Allowlist, validation và masking trước logger** giảm rủi ro từ code.
3. **Structured encoding + injection defenses** bảo đảm log khó bị phá parser hoặc giả dòng.
4. **Bảo vệ MDC, Throwable, third-party loggers và mọi appender** ngăn đường bypass.
5. **TLS, encryption at rest, IAM/RBAC và tenant isolation** bảo vệ đường vận chuyển và kho lưu.
6. **Retention, backup controls và incident response** quản lý rủi ro dữ liệu tồn lưu.
7. **Audit events đáng tin, append-only/tamper-evidence và durability policy** phục vụ yêu cầu truy vết cao hơn diagnostic log.
8. **Resource budgets, backpressure, rate limits, metrics và alert độc lập** bảo vệ tính sẵn sàng.
9. **Synthetic canary tests ở mọi sink** tạo bằng chứng rằng chính sách được áp dụng thật.
10. **Review và cập nhật sau mỗi thay đổi code/config/library/collector** tránh regression.

**Kết luận:** Logging bảo mật không phải một bộ lọc regex đặt vào cuối pipeline, mà là một **hợp đồng an toàn từ nguồn sự kiện Java đến nơi lưu và người sử dụng**. Một checklist tốt vừa giữ được khả năng điều tra bằng event code, ID tương quan và outcome đúng ngữ nghĩa, vừa ngăn secret/PII lọt ra, chống giả mạo, kiểm soát tài nguyên và duy trì bằng chứng khi có sự cố. Hãy dùng bảng kiểm như một phần của **code review, CI, deployment review và vận hành liên tục**, với tiêu chí kiểm thử thực tế thay vì chỉ đánh dấu đã làm.
