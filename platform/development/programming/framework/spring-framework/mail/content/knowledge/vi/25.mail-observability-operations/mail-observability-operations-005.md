# Ẩn hoặc băm dữ liệu người nhận trong log

## 1. Vấn đề: cần theo dõi gửi mail nhưng không nên đưa địa chỉ người nhận vào log

Trong ứng dụng **Spring Framework Mail**, đội vận hành thường cần trả lời: email xác nhận đơn hàng đã được gửi chưa, thất bại ở bước nào, số lần retry bao nhiêu, provider có bị chậm không, sự cố có ảnh hưởng một nhóm job không? Những câu hỏi này thường được giải quyết bằng application log, distributed tracing, metrics và dữ liệu trạng thái trong database.

Địa chỉ người nhận là thông tin có thể nhận diện một người hoặc một tổ chức. Nếu ghi trực tiếp địa chỉ vào mọi dòng log, dữ liệu đó có thể được sao chép qua nhiều hệ thống:

~~~text
Order / Notification application
           |
           +-- JavaMailSender / SMTP client
           |
           +-- Application logs
                    |
                    +-- Container stdout
                    +-- Log collector / agent
                    +-- Centralized log storage
                    +-- Dashboard / alerts
                    +-- Export to incident ticket
                    +-- Backup / archive
~~~

Một địa chỉ người nhận xuất hiện trong log có thể tiếp cận nhiều người hơn so với dữ liệu nghiệp vụ trong database. Log còn thường có retention và quyền truy cập khác, vì thế **không nên xem log là nơi an toàn để lưu đầy đủ email người nhận**.

Ví dụ không nên:

~~~java
log.info("Sending notification to {}", recipientEmail);
log.warn("Mail to {} failed: {}", recipientEmail, ex.getMessage());
~~~

Ngay cả khi dùng SLF4J parameterized logging, giá trị thực vẫn được đưa vào log sau khi format. Dấu `{}` chỉ trì hoãn việc nối chuỗi, **không tự che giấu dữ liệu**.

Thay vào đó, một log đủ phục vụ vận hành có thể là:

~~~text
event=mail_submission_finished
mailJobId=job-7f3a
notificationType=ORDER_RECEIPT
recipientToken=v2:0e8c4f... (HMAC rút gọn)
attempt=2
result=SMTP_ACCEPTED
durationMs=724
~~~

Trong ví dụ, `mailJobId` là định danh job ngẫu nhiên; `recipientToken` là pseudonym phục vụ đối chiếu được tạo theo chính sách. Nếu chỉ cần truy vết một job thì **thậm chí không cần recipientToken**.

**Mục tiêu của bài:** lựa chọn khi nào không ghi email, khi nào che một phần, khi nào dùng HMAC có khóa; triển khai với Spring Mail; tránh rò địa chỉ qua exception, MIME, SMTP debug và hệ thống quan sát; kiểm thử rằng log không chứa dữ liệu người nhận thật.

## 2. Phân biệt dữ liệu nghiệp vụ, log, metric và audit

Không phải mọi nơi lưu thông tin đều có vai trò như nhau.

| Thành phần | Mục đích | Nên chứa địa chỉ email đầy đủ? |
|---|---|---|
| Customer database | Quản lý người dùng, thông tin liên hệ | Có thể cần, theo quyền và chính sách dữ liệu |
| Mail outbox/job store | Gửi đúng người nhận, retry | Có thể cần, phải bảo vệ và có retention |
| Application log | Tìm lỗi, trace luồng xử lý | Mặc định không |
| Metrics | Đếm thành công/lỗi/độ trễ | Không; tránh label theo email |
| Distributed tracing | Theo request, dependency, latency | Mặc định không |
| Security audit | Ghi nhận thao tác có ý nghĩa và người chịu trách nhiệm | Chỉ lưu mức cần thiết, có kiểm soát riêng |
| Support/admin UI | Tra cứu sự cố theo quyền | Có thể hiển thị có điều kiện, không dùng như log công khai |

Với một mail job có ID ổn định, log có thể chỉ cần:

~~~text
jobId=job-7f3a notificationType=ORDER_RECEIPT status=RETRY
errorCode=SMTP_TEMPORARY_FAILURE attempt=3
~~~

Người có quyền phù hợp có thể tra cứu job tương ứng trong hệ thống nghiệp vụ để biết người nhận. Đây thường là thiết kế tốt hơn việc gắn email vào mọi sự kiện log.

### Data minimization trước khi masking

Thứ tự ưu tiên:

1. **Không ghi** trường recipient nếu không cần.
2. Dùng ID job/sự kiện không chứa email hoặc mã khách hàng dễ suy ra.
3. Nếu phải hiển thị một chút thông tin cho người vận hành, cân nhắc masking.
4. Nếu cần tương quan cùng một recipient qua nhiều job, cân nhắc HMAC có khóa.
5. Chỉ dùng địa chỉ email thật trong kênh tra cứu có authorization, audit và retention rõ ràng.

Không cần “băm cho bằng được” nếu metric hoặc log không có lý do giữ danh tính người nhận. Việc loại bỏ dữ liệu ngay tại nguồn tốt hơn gửi dữ liệu rồi cố xóa trên hệ thống tập trung.

## 3. Nhận diện mọi vị trí dễ làm lộ người nhận

Khi ứng dụng dùng `JavaMailSender`, địa chỉ có thể xuất hiện ở nhiều chỗ ngoài dòng log do lập trình viên viết.

| Nguồn | Ví dụ dữ liệu có thể lộ | Hướng kiểm soát |
|---|---|---|
| Log lúc tạo message | `to=user@example.test` | Bỏ hoặc thay recipient |
| SMTP error/exception | Server nhắc lại địa chỉ bị từ chối | Log mã lỗi đã chuẩn hóa |
| Stack trace với exception message | Địa chỉ, domain, SMTP response | Giới hạn Throwable logging, sanitization |
| JavaMail/Jakarta Mail debug | `RCPT TO:<user@example.test>` | Tắt protocol debug trong production |
| `MimeMessage.toString()` / raw message | Header To/Cc/Bcc, nội dung | Không dump toàn bộ message |
| Outbox payload dump | Recipient trong JSON | Whitelist fields được log |
| MDC/baggage | `recipient=user@example.test` | Chỉ thêm correlation ID an toàn |
| HTTP request/response logging | Email trong body/query | Redact hoặc loại route/field |
| Queue/broker client logging | Payload chứa recipient | Không log nguyên payload |
| Tracing span attributes | `messaging.destination.recipient` | Dùng thuộc tính ít nhạy cảm |
| Metrics labels | `recipient=...` | Không đưa email vào label |
| Log/alert enrichment | Thêm email từ DB theo jobId | Không tự enrich PII mặc định |

**Bcc đặc biệt nhạy cảm.** Dù Bcc thường không xuất hiện như header thông thường ở message cuối đến người nhận, danh sách Bcc vẫn có thể có trong input ứng dụng, SMTP envelope, exception hoặc debug trace. Không chỉ che `To` rồi bỏ qua `Cc`/`Bcc`.

### Ví dụ đường rò bất ngờ

~~~java
try {
    mailSender.send(message);
} catch (Exception ex) {
    log.error("Cannot send mail", ex);
}
~~~

Không thấy địa chỉ email được nối trực tiếp vào dòng log, nhưng exception hoặc nested cause từ SMTP server **có thể chứa địa chỉ người nhận**. Vì vậy `log.error(..., ex)` không mặc định an toàn về dữ liệu.

Tương tự, logging một request DTO như `log.debug("Request {}", request)` có thể khiến `record.toString()` hoặc Lombok `@ToString` đưa recipient, Bcc hoặc payload vào log. Không nên dựa vào việc level là DEBUG để coi dữ liệu đó không cần bảo vệ.

## 4. Che một phần (masking), băm thông thường và HMAC khác nhau thế nào?

Ba cơ chế giải quyết các nhu cầu khác nhau:

| Cách | Ví dụ minh họa | Lợi ích | Giới hạn |
|---|---|---|---|
| Không ghi | `jobId=job-7f3a` | Không để lộ recipient | Không nhóm log theo người nhận |
| Masking | `a***@example.test` | Dễ nhìn để hỗ trợ thủ công | Vẫn có thể nhận diện; domain và ký tự đầu lộ |
| SHA-256 thuần | `sha256(email)` | Cùng input cho cùng digest | Dễ thử từ điển trên không gian email có thể đoán |
| HMAC-SHA-256 có khóa | `v2:8d...` | Khó tính lại nếu không có khóa; hỗ trợ đối chiếu | Vẫn là pseudonym có thể liên kết |
| Token ngẫu nhiên tra bảng | `recipientRef=7a5c...` | Không phụ thuộc cấu trúc email | Cần lưu mapping có quyền truy cập |

Đối với logging production:

- **Masking** phù hợp khi người vận hành cần một gợi ý hiển thị có kiểm soát.
- **HMAC** phù hợp khi cần một khóa tương quan ổn định nhưng không muốn địa chỉ email xuất hiện trong log.
- **SHA-256 thuần của email** thường không phải lựa chọn bảo mật tốt cho mục tiêu chống suy ra địa chỉ.

### Vì sao SHA-256(email) chưa chắc bảo vệ được email?

Địa chỉ email có tính dự đoán và có thể nằm trong danh sách công khai hoặc dữ liệu đã bị rò. Một người có thể:

1. Thu thập danh sách email ứng viên.
2. Tính SHA-256 cho từng email theo cách chuẩn hóa của ứng dụng.
3. So sánh digest với giá trị trong log.
4. Xác định người nào nằm trong log.

Không cần “giải mã hash”; chỉ cần thử các ứng viên. Vì vậy, **không coi hash không khóa là ẩn danh hóa đủ mạnh** cho recipient trong log.

HMAC dùng một **khóa bí mật**:

\[
\operatorname{recipientToken} =
  \operatorname{HMAC}_{K}(\operatorname{canonicalEmail})
\]

Người có bản log nhưng không có khóa `K` không thể tự tính digest của danh sách email ứng viên theo cách tương tự. Tuy nhiên, nếu khóa bị lộ, khả năng đối chiếu từ điển trở lại. HMAC cũng không ngăn người có quyền truy cập ứng dụng yêu cầu tính token của một địa chỉ đã biết, trừ khi việc gọi hàm được kiểm soát.

## 5. Masking: dùng khi cần hỗ trợ người vận hành nhận biết một phần

Ví dụ giao diện hỗ trợ có thể hiển thị:

~~~text
minh.anh@example.test -> m***@example.test
admin@small-company.test -> a***@small-company.test
~~~

Cách này khiến người vận hành ít phải nhìn địa chỉ đầy đủ, nhưng **không xóa hết khả năng định danh**:

- Domain hiển thị có thể xác định một tổ chức nhỏ.
- Một local-part chỉ dài một ký tự hoặc tên hiếm vẫn dễ đoán.
- Kết hợp thời gian gửi, loại thông báo và tenant có thể xác định người nhận.
- Mỗi địa chỉ được che theo cách nhất quán vẫn có thể liên kết giữa các log.

Nếu cần bảo vệ mạnh hơn, có thể che cả domain (`m***@***`), chỉ hiển thị `[redacted-email]` hoặc không log.

### Hàm masking tối giản để minh họa

~~~java
public final class RecipientMasker {
    private RecipientMasker() {
    }

    public static String mask(String email) {
        if (email == null || email.isBlank()) {
            return "[recipient-unavailable]";
        }

        int at = email.lastIndexOf('@');
        if (at <= 0 || at == email.length() - 1) {
            return "[recipient-invalid]";
        }

        String local = email.substring(0, at);
        String domain = email.substring(at + 1);

        // Chỉ minh họa policy cho mailbox đơn giản.
        String first = local.substring(0, 1);
        return first + "***@" + domain;
    }
}
~~~

Hàm trên **không phải một email parser RFC đầy đủ** và vẫn để lộ domain. Nó phù hợp để minh họa cơ chế che trong bối cảnh đầu vào là một mailbox đơn giản đã được ứng dụng validation. Với ứng dụng thực tế, trước hết parse mailbox đúng cách hoặc áp chính sách luôn thay bằng chuỗi `[redacted]` nếu dữ liệu không đáng tin.

Không nên “mask” một chuỗi chứa nhiều địa chỉ bằng cách tìm ký tự `@` cuối cùng rồi cho rằng đã xử lý mọi recipient. Đối với danh sách To/Cc/Bcc, hãy xử lý **từng mailbox có cấu trúc**.

## 6. Khi nào không nên giữ domain trong log?

Giả sử email gửi tới `cfo@very-small-firm.example`. Sau khi mask thành `c***@very-small-firm.example`, domain vẫn chỉ rõ doanh nghiệp, thời điểm và loại email có thể tiết lộ mối quan hệ kinh doanh.

Các trường hợp nên che toàn bộ hoặc dùng token thay cho domain:

- Email bệnh viện, tài chính, nhân sự hoặc thông báo bảo mật.
- Hệ thống gửi đến các doanh nghiệp nhỏ với domain riêng.
- Subscription cho nhóm người nhận có tính nhạy cảm.
- Log được chia sẻ rộng với vendor, external support hoặc nhiều team.
- Các báo cáo tổng hợp theo tên domain không thực sự cần để vận hành.

Nếu cần đo deliverability theo provider/domain, cân nhắc **nhóm domain có kiểm soát** như `GMAIL`, `OUTLOOK`, `OTHER` dựa trên danh sách cố định, nhưng vẫn phải xem xét khả năng rò thông tin với nhóm hiếm. Không đưa mọi domain vào metric label vì cardinality và rủi ro dữ liệu.

## 7. Chuẩn hóa địa chỉ email trước khi tạo HMAC

HMAC của cùng một chuỗi byte luôn cho cùng một kết quả với cùng khóa. Nhưng những chuỗi nhìn giống một địa chỉ có thể khác nhau:

~~~text
User@Example.COM
User@example.com
 user@example.com 
"User" <User@example.com>
~~~

Nếu muốn đối chiếu theo mailbox, ứng dụng cần xác định **quy tắc chuẩn hóa (canonicalization)** trước khi băm. Quy tắc này phải ổn định và được dùng thống nhất tại mọi nơi tạo token.

### Đừng tùy tiện lower-case toàn bộ email

Theo cách định danh địa chỉ Internet mail, **domain** không phân biệt chữ hoa/thường; **local-part** về mặt giao thức có thể có quy tắc so khớp riêng theo hệ thống nhận. Nhiều nhà cung cấp phổ biến xử lý local-part không phân biệt hoa/thường, nhưng không được suy rộng điều này cho mọi domain.

Ví dụ:

~~~text
User@example.com
user@example.com
~~~

Nếu ứng dụng tự chuyển cả hai thành `user@example.com`, token sẽ giống nhau, dù chính sách nhận diện mailbox của tổ chức hoặc provider có thể không cho phép gộp chúng. Vì vậy một chính sách an toàn khi chưa có bằng chứng khác là **giữ nguyên local-part** và chỉ chuẩn hóa domain.

Tương tự, không tự động:

- Xóa phần `+tag` sau dấu cộng: plus addressing không có cùng semantics trên mọi provider.
- Bỏ dấu chấm ở local-part vì một provider cụ thể có quy tắc đó.
- Loại dấu nháy trong quoted local-part bằng regex tùy ý.
- Chuyển Unicode local-part bằng một phép normalization chưa được giao thức và sản phẩm định nghĩa.

### Ví dụ canonicalization có giới hạn rõ ràng

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import java.net.IDN;
import java.util.Locale;

public final class RecipientCanonicalizer {
    private RecipientCanonicalizer() {
    }

    public static String canonicalMailbox(String input)
            throws AddressException {
        if (input == null || input.isBlank()) {
            throw new AddressException("Recipient is required");
        }

        InternetAddress parsed = new InternetAddress(input, true);
        parsed.validate();

        String mailbox = parsed.getAddress();
        if (mailbox == null) {
            throw new AddressException("Mailbox is missing");
        }

        int at = mailbox.lastIndexOf('@');
        if (at <= 0 || at == mailbox.length() - 1) {
            throw new AddressException("Invalid mailbox");
        }

        String localPart = mailbox.substring(0, at);
        String domain = mailbox.substring(at + 1);
        String asciiDomain;

        try {
            asciiDomain = IDN.toASCII(
                    domain, IDN.USE_STD3_ASCII_RULES)
                    .toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException ex) {
            throw new AddressException("Invalid domain");
        }

        return localPart + "@" + asciiDomain;
    }
}
~~~

Ví dụ sử dụng `InternetAddress` của Jakarta Mail để tách mailbox, giữ local-part và chuẩn hóa domain về IDNA ASCII/chữ thường. Đây là **quy tắc của ứng dụng minh họa**, không phải một parser/validator có thể bảo đảm mọi biến thể SMTPUTF8, quoted local-part hoặc địa chỉ quốc tế. Với hệ thống chấp nhận đầy đủ email quốc tế, cần chọn một thư viện và chính sách canonicalization phù hợp, kiểm thử trên dữ liệu thực và giữ backward compatibility.

### Chuẩn hóa là một quyết định sản phẩm

Nếu hệ thống đã lưu định danh người nhận theo một `recipient_id` ổn định và duy nhất, dùng `recipient_id` cho correlation có thể đơn giản hơn canonicalize email. Nhưng ID đó cũng có thể là dữ liệu cá nhân giả danh và phải được bảo vệ. Không lấy địa chỉ email làm correlation key chỉ vì nó sẵn có.

Khi thay đổi canonicalization, **cùng mailbox có thể nhận token mới**. Vì vậy cần quản lý phiên bản của chính sách, ví dụ `v2`, để không so sánh nhầm token được tạo bởi hai thuật toán khác nhau.

## 8. Tạo recipient token bằng HMAC-SHA-256 trong Java

Đối với trường hợp cần nhận diện rằng nhiều mail job thuộc cùng một recipient nhưng không muốn log địa chỉ thật, có thể dùng HMAC-SHA-256 với một khóa bí mật của hệ thống quan sát.

Thiết kế cơ bản:

~~~text
Recipient hợp lệ
       |
       v
Canonicalize mailbox
       |
       v
UTF-8 bytes
       |
       v
HMAC-SHA-256(secret key, bytes)
       |
       v
Lấy 128 bit đầu nếu policy chấp nhận
       |
       v
recipientToken = v1:<32 hex characters>
~~~

Ví dụ mã Java 17+:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class RecipientTokenService {
    private static final String ALGORITHM = "HmacSHA256";
    private static final int TOKEN_BYTES = 16;

    private final SecretKeySpec key;
    private final String keyVersion;

    public RecipientTokenService(
            byte[] secretKey,
            String keyVersion) {
        Objects.requireNonNull(secretKey, "secretKey");
        if (secretKey.length < 32) {
            throw new IllegalArgumentException(
                    "Use at least 32 bytes of key material");
        }
        if (keyVersion == null || keyVersion.isBlank()) {
            throw new IllegalArgumentException(
                    "Key version is required");
        }

        this.key = new SecretKeySpec(
                secretKey.clone(), ALGORITHM);
        this.keyVersion = keyVersion;
    }

    public String token(String recipient)
            throws jakarta.mail.internet.AddressException {
        String canonical =
                RecipientCanonicalizer.canonicalMailbox(recipient);

        try {
            // Không chia sẻ Mac instance giữa các thread.
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(key);
            byte[] digest = mac.doFinal(
                    canonical.getBytes(StandardCharsets.UTF_8));

            byte[] shortDigest =
                    Arrays.copyOf(digest, TOKEN_BYTES);
            return keyVersion + ":"
                    + HexFormat.of().formatHex(shortDigest);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                    "Recipient tokenization unavailable", ex);
        }
    }
}
~~~

Điểm quan trọng:

- `HmacSHA256` là thuật toán HMAC được dùng rộng rãi.
- Khóa được cấp từ nguồn bí mật, không hardcode trong mã nguồn.
- Mỗi lần gọi tạo một `Mac` mới; không dùng chung một `Mac` mutable cho nhiều thread của mail executor.
- Input được mã hóa UTF-8 sau canonicalization.
- `HexFormat` yêu cầu Java 17+.
- `TOKEN_BYTES=16` chỉ giữ 128 bit đầu của kết quả HMAC để token ngắn hơn; nếu muốn biên độ chống collision cao hơn, có thể giữ đủ 32 byte.
- `keyVersion` là nhãn phiên bản công khai; **không chứa khóa thực**.

128 bit đầu của HMAC là đủ lớn cho nhiều bài toán correlation log thông thường, nhưng mọi thiết kế cần xem xét số lượng định danh và độ dài token. Nếu cần tính toàn vẹn hoặc bảo mật theo một giao thức cụ thể, không mặc định việc rút gọn là phù hợp.

### Tạo khóa bằng CSPRNG, không từ password dễ đoán

Ví dụ sinh 32 byte:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

byte[] key = new byte[32];
new SecureRandom().nextBytes(key);
String encoded =
        Base64.getEncoder().encodeToString(key);

// Lưu encoded trong secret manager; không log/commit giá trị.
~~~

Đoạn này **chỉ minh họa cách tạo khóa**. Không đặt code sinh khóa mới trong constructor khởi động ứng dụng ở mỗi lần deploy, vì như vậy các instance sẽ tạo recipient token khác nhau và không thể correlation ổn định. Khóa cần được cấp qua secret store có quản lý lifecycle.

### Tách khóa recipient logging khỏi các secret khác

Không dùng:

- SMTP password làm khóa HMAC.
- JWT signing key dùng chung.
- Encryption key của database dùng lại.
- Secret hardcode trong test fixture để chạy production.

Nếu khóa HMAC bị lộ, phải rotate mà không ảnh hưởng SMTP credential và các hệ thống authentication khác. Tách khóa giúp giảm phạm vi tác động của mỗi sự cố.

## 9. Cấp khóa HMAC cho Spring mà không lộ giá trị

Một lựa chọn là tạo bean `RecipientTokenService` bằng cấu hình Spring đọc từ secret store hoặc environment do hạ tầng cung cấp. Ví dụ Java configuration:

~~~java
import java.util.Base64;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class RecipientLoggingConfiguration {

    @Bean
    RecipientTokenService recipientTokenService(
            Environment environment) {
        String encoded = environment.getRequiredProperty(
                "MAIL_LOG_HMAC_KEY_B64");
        String version = environment.getRequiredProperty(
                "MAIL_LOG_HMAC_KEY_VERSION");

        byte[] key = Base64.getDecoder().decode(encoded);
        try {
            return new RecipientTokenService(key, version);
        } finally {
            java.util.Arrays.fill(key, (byte) 0);
        }
    }
}
~~~

`Environment` đọc thuộc tính mà ứng dụng được cấp. Hạ tầng cần bảo đảm `MAIL_LOG_HMAC_KEY_B64` và `MAIL_LOG_HMAC_KEY_VERSION` có trong runtime; có thể lấy từ secret manager, secret volume hoặc cơ chế injection của deployment.

Xóa mảng byte tạm là một biện pháp hạn chế bản sao còn lại trong bộ nhớ, **không thể bảo đảm mọi bản sao secret được xóa hoàn toàn** vì chuỗi Base64 đầu vào là Java String và có thể đã tồn tại trong hệ thống cấu hình. Không đưa secret vào `toString()`, log cấu hình hoặc exception.

### Tại sao không dùng salt công khai giống nhau để “thay HMAC”?

Một số code dùng:

~~~java
// Không phải HMAC và không chống được dictionary attack
// nếu salt đã được lưu cùng log hoặc công khai.
sha256("public-salt:" + email)
~~~

Nếu attacker biết salt, họ vẫn có thể thử các email ứng viên. Trong mô hình chống đối chiếu từ điển từ bản log bị lộ, cần **khóa bí mật** hoặc một hệ thống pseudonymization có kiểm soát, không chỉ một salt công khai.

### Chính sách khác nhau theo môi trường

Nên dùng khóa khác nhau cho development, staging và production để không thể so token giữa các môi trường chỉ dựa trên log. Nếu có tenant yêu cầu tách riêng, có thể dùng khóa theo tenant hoặc cơ chế derive key được thiết kế đúng, nhưng phải tính tới vận hành và key rotation.

Không chuyển bảng mapping giữa token và địa chỉ thật vào log; làm vậy phá mục tiêu của HMAC.

## 10. HMAC tạo pseudonym, không tạo dữ liệu ẩn danh tuyệt đối

Một token ổn định có thể liên kết nhiều sự kiện:

~~~text
recipientToken=v1:ab12... notificationType=PASSWORD_RESET
recipientToken=v1:ab12... notificationType=PAYMENT_RECEIPT
recipientToken=v1:ab12... notificationType=SECURITY_ALERT
~~~

Ngay cả khi không thấy địa chỉ email, người đọc log vẫn biết các sự kiện xảy ra với **cùng một người nhận**. Kết hợp tenant, thời gian, loại thông báo và job data có thể làm lộ thông tin về hành vi người dùng.

Do đó:

- Xem HMAC recipient token là **dữ liệu giả danh (pseudonymous data)** cần bảo vệ, không tự coi là dữ liệu đã ẩn danh hoàn toàn.
- Chỉ log token ở các sự kiện thật sự cần correlation.
- Hạn chế quyền query/search token và export kết quả.
- Tránh dùng token làm label metric hoặc tracing attribute ở phạm vi công khai.
- Giảm thời gian retention nếu correlation dài hạn không cần.
- Cân nhắc thay token ổn định toàn hệ thống bằng token theo job/campaign khi chỉ cần liên kết trong một phạm vi.

### Phân tách theo phạm vi (scope)

Một token duy nhất cho mọi loại email giúp tìm mọi job của cùng recipient, nhưng tăng khả năng liên kết:

~~~text
Scope toàn hệ thống:
    HMAC(K, canonicalEmail)

Scope theo mục đích:
    HMAC(K, "newsletter:" + canonicalEmail)
    HMAC(K, "security:" + canonicalEmail)
~~~

Nếu hệ thống không cần biết người đăng ký newsletter cũng là người nhận security alert, **không dùng cùng token giữa hai miền dữ liệu**. Một cách tốt hơn về mặt quản lý khóa là derive subkey cho từng phạm vi bằng KDF phù hợp; nếu chọn đưa prefix mục đích vào dữ liệu HMAC, phải định nghĩa chuỗi serialization không mơ hồ và version hóa chính sách.

## 11. Rotation khóa và thời hạn tương quan

Một khóa HMAC ổn định sẽ cho token ổn định. Khi rotate từ `v1` sang `v2`:

~~~text
Trước rotation:
recipientToken=v1:839a...

Sau rotation:
recipientToken=v2:af57...
~~~

Hai token này **không thể so sánh trực tiếp**, dù đến từ cùng địa chỉ. Đây vừa là đặc tính bảo mật, vừa là ảnh hưởng vận hành phải được tính trước.

Chiến lược thông dụng:

1. Định nghĩa chu kỳ rotation theo chính sách tổ chức.
2. Cấp một khóa mới từ secret store, gắn `keyVersion` mới.
3. Triển khai cùng cấu hình trên mọi replica cần tạo token tương quan.
4. Ghi token mới cho các sự kiện sau cutover.
5. Giữ khóa cũ chỉ nếu có nhu cầu tra cứu chuyển tiếp được phê duyệt, trong một kho khóa có quyền hạn chế.
6. Thu hồi/xóa khóa cũ khi không còn nhu cầu và chính sách cho phép.

**Không được ghi cả token v1 và v2 cho mỗi recipient trong log chỉ để nối lịch sử**, vì điều này làm mất một phần lợi ích của rotation và tăng khả năng liên kết. Nếu có nhu cầu điều tra được phê duyệt xuyên giai đoạn, nên dùng một công cụ kiểm soát quyền thực hiện lookup thay vì phơi bày mapping trong log chung.

### Key rotation và canonicalization version là hai thứ khác nhau

`keyVersion` thay đổi khi đổi khóa; `canonicalizationVersion` thay đổi khi đổi quy tắc chuẩn hóa mailbox. Hệ thống lớn có thể cần mô tả cả hai trong tài liệu thiết kế/token metadata. Không được suy luận “token khác tức hai người nhận khác” nếu token được tạo qua hai phiên bản không tương thích.

## 12. Nhiều người nhận: To, Cc và Bcc cần cùng một chính sách

Ứng dụng có thể tạo email tới:

~~~java
helper.setTo(toRecipients);
helper.setCc(ccRecipients);
helper.setBcc(bccRecipients);
~~~

Không được log raw `Arrays.toString(toRecipients)` hoặc object `MimeMessage` khi debug. Nếu phải quan sát số người nhận, log **số lượng** và loại:

~~~text
event=mail_submission_start
mailJobId=job-7f3a
recipientCount=3
toCount=1
ccCount=1
bccCount=1
notificationType=MONTHLY_REPORT
~~~

Nếu cần token theo từng người nhận, nên xử lý từng mailbox với chính sách rõ ràng và cân nhắc:

- Không hiển thị danh sách token đầy đủ nếu một email gửi tới hàng nghìn người; log sẽ rất lớn và tăng nguy cơ liên kết.
- Bcc không nên bị ghi lộ chỉ vì debug mode đang chạy.
- Một số SMTP exceptions có thể chứa danh sách recipient bị từ chối; không gọi `toString()` trên mảng địa chỉ/exception khi log.
- Nếu số lượng người nhận là thông tin nhạy cảm trong bối cảnh nhỏ, có thể dùng bucket (1, 2–5, 6–20, hơn 20) thay vì số chính xác.

Với notification cá nhân hóa, cách đơn giản là **một job/recipient** với `jobId` riêng. Nhưng đó là quyết định thiết kế gửi mail, không phải lý do bắt buộc để luôn tạo recipient token.

## 13. Log có cấu trúc: chỉ cho phép trường đã được phê duyệt

Cách hạn chế rò dữ liệu hiệu quả hơn việc “tìm và thay mọi email trong chuỗi” là **thiết kế schema log có danh sách trường được phép (allowlist)**.

Ví dụ sự kiện khi bắt đầu gửi:

~~~text
event=mail_submission_started
jobId=job-7f3a
notificationType=ORDER_RECEIPT
templateVersion=v3
attempt=1
provider=PRIMARY_SMTP
~~~

Khi hoàn tất:

~~~text
event=mail_submission_finished
jobId=job-7f3a
notificationType=ORDER_RECEIPT
result=SMTP_ACCEPTED
attempt=1
durationMs=608
~~~

Khi thất bại:

~~~text
event=mail_submission_failed
jobId=job-7f3a
notificationType=ORDER_RECEIPT
errorCode=SMTP_TEMPORARY_FAILURE
attempt=2
retryScheduled=true
~~~

Không có địa chỉ email, subject đầy đủ, raw HTML, attachment name nhạy cảm hoặc token truy cập trong ba sự kiện trên. Nếu cần tìm các job cùng người nhận, thêm `recipientToken` theo policy, không thêm recipient thật.

### Nguyên tắc chọn trường

| Trường | Thường nên log? | Lưu ý |
|---|---|---|
| `event` / `phase` | Có | Enum/giá trị cố định |
| `mailJobId` | Có nếu là ID ngẫu nhiên | Không tự encode email vào job ID |
| `notificationType` | Có cân nhắc | Loại quá nhạy cảm có thể cần tên tổng quát |
| `templateId` / `version` | Có | Không dùng subject cá nhân hóa làm template ID |
| `attempt` / `durationMs` | Có | Hữu ích cho retry/latency |
| `providerId` | Có | Danh sách provider cố định |
| `smtpStatusClass` / `errorCode` | Có | Chỉ mã đã chuẩn hóa |
| `recipientCount` | Có cân nhắc | Có thể bucket theo chính sách |
| `recipientToken` | Khi cần correlation | HMAC có khóa, hạn chế quyền đọc |
| `recipientEmail` | Mặc định không | Nếu buộc dùng, chuyển sang kênh tra cứu có bảo vệ |
| `subject` | Mặc định không | Thường chứa tên, số đơn, nội dung |
| `exception.getMessage()` | Không mặc định | Có thể chứa địa chỉ và SMTP response |
| `MimeMessage` / raw MIME | Không | Có To/Cc/Bcc, body và attachment |

### Không log nguyên DTO/map của job

~~~java
// Dễ rò dữ liệu nếu record.toString() chứa recipient.
log.info("Mail job {}", mailJob);

// Dễ rò cả body, headers, Bcc hoặc token.
log.debug("Mail payload {}", payload);
~~~

Thay bằng các field được chọn riêng:

~~~java
log.info(
        "event=mail_job_created jobId={} notificationType={}",
        mailJob.id(),
        mailJob.notificationType());
~~~

`notificationType` nên là enum hoặc string đã được kiểm soát; không lấy một tên tùy ý do client nhập nếu có khả năng chứa PII.

## 14. Tích hợp RecipientTokenService vào một logger riêng

Một component chuyên tạo log mail giúp hạn chế việc từng service tự log địa chỉ người nhận theo nhiều cách khác nhau.

~~~java
import jakarta.mail.internet.AddressException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class MailSafeLogger {
    private static final Logger log =
            LoggerFactory.getLogger(MailSafeLogger.class);

    private final RecipientTokenService tokens;

    public MailSafeLogger(RecipientTokenService tokens) {
        this.tokens = tokens;
    }

    public void submissionStarted(
            String jobId,
            String notificationType,
            String recipient,
            int attempt) {

        String recipientToken = safeToken(recipient);
        log.info(
                "event=mail_submission_started "
                    + "jobId={} notificationType={} "
                    + "recipientToken={} attempt={}",
                jobId,
                notificationType,
                recipientToken,
                attempt);
    }

    public void submissionFailed(
            String jobId,
            MailFailureCode code,
            int attempt) {
        log.warn(
                "event=mail_submission_failed "
                    + "jobId={} errorCode={} attempt={}",
                jobId, code, attempt);
    }

    private String safeToken(String recipient) {
        try {
            return tokens.token(recipient);
        } catch (AddressException ex) {
            return "[invalid-recipient]";
        }
    }
}
~~~

Ở đây `MailFailureCode` là một enum ứng dụng tự định nghĩa. Logger cố ý **không** nhận `Throwable` để tránh những người gọi vô tình truyền stack trace chứa SMTP transcript hoặc địa chỉ email.

Đối với nguồn dữ liệu không đáng tin, `jobId` và `notificationType` cũng phải là giá trị đã được sinh/validate ở server. Một attacker có thể chèn CR/LF vào string nhận từ request để tạo log injection nếu hệ thống không xử lý. Structured logging và validation cần áp cho **mọi field**, không chỉ recipient.

### Tokenization lỗi thì sao?

Trong ví dụ, địa chỉ cú pháp không hợp lệ được thay bằng một marker chung, không log input. Nếu khóa HMAC bị thiếu, lỗi `IllegalStateException` có thể làm nghiệp vụ dừng hoặc cần fallback không có token; chọn chính sách rõ ràng:

- **Mail gửi vẫn được phép nhưng không log token:** log `recipientToken=[unavailable]` qua đường an toàn và phát metric cấu hình lỗi.
- **Fail closed theo compliance:** dừng một luồng gửi nếu tổ chức yêu cầu mọi submission phải có correlation pseudonym hợp lệ.

Không fallback sang `recipient.toString()` hoặc `sha256(email)` chỉ vì HMAC service bị lỗi. Hãy tách việc tạo token khỏi logic xác định có được phép gửi mail hay không, tùy yêu cầu nghiệp vụ.

## 15. Đừng log exception từ JavaMailSender một cách vô điều kiện

`JavaMailSender.send(...)` có thể ném các subtype `MailException`, ví dụ:

- `MailAuthenticationException` khi xác thực SMTP thất bại.
- `MailSendException` khi gửi message gặp lỗi.
- `MailPreparationException` khi lỗi trong preparator.
- Các exception nền như `MessagingException` hoặc exception chuyên biệt SMTP/địa chỉ.

Một SMTP server có thể trả phản hồi:

~~~text
550 5.1.1 Recipient <person@example.test> does not exist
~~~

Nếu Spring Mail exception chứa nguyên thông điệp đó, cách log:

~~~java
log.warn("SMTP failed: {}", ex.getMessage());
log.error("Mail sending error", ex);
~~~

đều có thể đưa địa chỉ ra log. Ngay cả khi ứng dụng không đưa recipient vào message, **provider có thể echo địa chỉ trong lỗi**.

### Phân loại lỗi thành mã đã được kiểm soát

~~~java
public enum MailFailureCode {
    AUTHENTICATION_FAILED,
    SMTP_TEMPORARY_FAILURE,
    SMTP_PERMANENT_FAILURE,
    SMTP_SUBMISSION_UNKNOWN,
    MIME_PREPARATION_FAILED,
    RESOURCE_READ_FAILED,
    UNCLASSIFIED_MAIL_FAILURE
}
~~~

Một hàm phân loại thận trọng:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailPreparationException;

public final class MailFailureClassifier {
    private MailFailureClassifier() {
    }

    public static MailFailureCode classify(MailException ex) {
        if (ex instanceof MailAuthenticationException) {
            return MailFailureCode.AUTHENTICATION_FAILED;
        }
        if (ex instanceof MailPreparationException) {
            return MailFailureCode.MIME_PREPARATION_FAILED;
        }
        return MailFailureCode.UNCLASSIFIED_MAIL_FAILURE;
    }
}
~~~

Đoạn code cố ý **không tự gắn nhãn SMTP temporary/permanent chỉ từ tên `MailSendException`**: cần phân tích chính xác nested cause, SMTP response code và giai đoạn giao thức. Nếu không có đủ bằng chứng, dùng mã `UNCLASSIFIED_MAIL_FAILURE` hoặc `SMTP_SUBMISSION_UNKNOWN` theo semantics đã xác định.

### Ví dụ catch trong service

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;

public void submit(
        String jobId,
        MimeMessage message,
        int attempt) {
    try {
        mailSender.send(message);
    } catch (MailException ex) {
        MailFailureCode code =
                MailFailureClassifier.classify(ex);

        safeLogger.submissionFailed(jobId, code, attempt);
        // Lưu trạng thái/retry theo policy.
        // Không log ex.getMessage() hoặc ex ở đây.
        throw ex;
    }
}
~~~

Ví dụ mô tả một method của component có sẵn `mailSender` và `safeLogger`; cần import `jakarta.mail.internet.MimeMessage`. Khi **ném lại exception**, một lớp phía trên hoặc framework có thể ghi stack trace và làm rò dữ liệu. Vì vậy chính sách bảo vệ log phải áp **xuyên suốt pipeline**, gồm scheduler, consumer, HTTP exception handler và AOP boundary, chứ không chỉ ở một catch.

Không nên nuốt exception chỉ để “giấu địa chỉ”. Logic retry phải vẫn nhận biết thất bại, còn log vận hành sử dụng mã đã được làm sạch.

## 16. Kiểm soát các exception chứa địa chỉ bên trong

`MailSendException` có thể cung cấp thông tin về message thất bại và các nested exception. Ví dụ, một map của các message không gửi thành công có thể chứa `MimeMessage` làm key và exception làm value. Nếu dump map trực tiếp:

~~~java
// Không an toàn cho dữ liệu mail; đừng log raw.
log.warn("Failed messages: {}", ex.getFailedMessages());
~~~

bạn có thể đưa thông tin message hoặc exception của SMTP ra log tùy cách đối tượng được biểu diễn.

**Chỉ trích xuất phần metadata không chứa recipient** như:

- Số message thất bại.
- Phân loại theo mã lỗi tổng quát đã được chuẩn hóa.
- Provider identifier cố định.
- Thời gian, attempt count và job ID.

Ví dụ:

~~~java
import org.springframework.mail.MailSendException;

if (ex instanceof MailSendException sendException) {
    int failedCount =
            sendException.getFailedMessages().size();
    log.warn(
            "event=mail_submission_failed "
                + "jobId={} failedMessageCount={}",
            jobId, failedCount);
}
~~~

Không in map keys/values hoặc `getMessageExceptions()` trực tiếp. Nếu cần kiểm tra nguyên nhân sâu để gắn mã SMTP, hãy làm trong bộ phân loại đáng tin cậy và **chỉ trả enum/mã** cho lớp logging.

### SMTP response code và recipient trong cùng một chuỗi

Ví dụ:

~~~text
550 5.1.1 user@example.test unknown
421 4.7.0 temporary rate limit for user@example.test
~~~

Có thể dùng mã `550` hoặc `421` làm tín hiệu chẩn đoán nếu parser có thể lấy một cách đáng tin cậy, nhưng **không được log nguyên cả dòng phản hồi**. Ngay cả mã SMTP cũng cần hiểu đúng phase: sự cố kết nối sau khi gửi DATA có thể tạo kết quả không chắc chắn, không nên suy luận retry an toàn chỉ từ chuỗi lỗi.

## 17. JavaMail/Jakarta Mail protocol debug: nguồn rò địa chỉ rất lớn

Khi bật debug của Jakarta Mail, thư viện có thể ghi chi tiết giao thức SMTP:

~~~text
DEBUG SMTP: connecting to host smtp.example.test
MAIL FROM:<noreply@example.test>
RCPT TO:<customer@example.test>
DATA
...
~~~

Nó có thể chứa recipient, sender, thông tin SMTP handshake và tùy chế độ/implementation có thể lộ dữ liệu xác thực hoặc nội dung thư. Do đó **không bật protocol-level debug mặc định ở production**.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    properties:
      mail.debug: false
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

`mail.debug=false` tắt debug ở mức Jakarta Mail session theo property tương ứng, nhưng cần rà thêm những nơi có thể bật:

- Code gọi `Session.setDebug(true)`.
- Code thiết lập debug output qua `Session.setDebugOut(...)`.
- Cấu hình mail provider khác hoặc logger của implementation.
- JVM system properties và cấu hình môi trường.
- Logger category DEBUG/TRACE ghi SMTP transport hoặc nội dung mail.
- Container stdout/stderr collector.

**Không giả định tắt Spring application logger sẽ chặn mọi SMTP debug output.** Jakarta Mail có thể dùng luồng debug output riêng; hãy kiểm tra cấu hình session/provider và cách runtime thu thập stdout.

### Khi buộc phải điều tra bằng protocol debug

Nếu tình huống khẩn cấp cần SMTP trace:

1. Ưu tiên môi trường test, fake recipient và SMTP sink.
2. Bật debug cho một khoảng thời gian ngắn, theo phê duyệt vận hành.
3. Giới hạn phạm vi instance/job/tài khoản test.
4. Kiểm soát nơi lưu output và quyền truy cập.
5. Loại bỏ token, credential, recipient, subject và nội dung trước khi chia sẻ.
6. Tắt lại debug và xác nhận cấu hình không còn bật.
7. Xóa/giảm retention của dữ liệu debug theo chính sách.

Không dùng `mail.debug.auth=true` hoặc cơ chế tương tự để phơi thông tin xác thực nhằm “dễ debug” trên production.

## 18. Không dump MimeMessage hoặc raw MIME vào log

Một cách chẩn đoán thường thấy:

~~~java
ByteArrayOutputStream out = new ByteArrayOutputStream();
message.writeTo(out);
log.debug("Raw email: {}", out.toString(StandardCharsets.UTF_8));
~~~

Việc này có thể đưa vào log:

- Header `From`, `To`, `Cc` và các header khác.
- `Subject` chứa tên khách hàng/số đơn.
- Nội dung HTML/text.
- Link reset hoặc OTP.
- Binary attachment đã được encode.
- Message-ID và metadata nội bộ.

**Đừng dump raw MIME lên log tập trung.** Với kiểm thử MIME, dùng file fixture giả/SMTP sink và các assertion theo cấu trúc thay vì log toàn bộ byte. Nếu cần điều tra một email thật, dùng kho chẩn đoán có quyền đặc biệt, thời hạn lưu ngắn và audit truy cập; log ứng dụng chỉ chứa tham chiếu tới ca điều tra, không chứa raw body.

### Header Bcc cần được bảo vệ ngay cả khi không xuất hiện cuối cùng

Đừng khẳng định “Bcc không có trong email nhận nên không lo”. Bcc vẫn có thể tồn tại ở tầng input, object `MimeMessage` trước khi gửi, SMTP recipient list hoặc exception. Chính sách logging phải áp trước khi dữ liệu đi qua mọi thành phần, không chỉ dựa vào việc mail client có ẩn Bcc khi hiển thị.

## 19. MDC và correlation ID: không truyền recipient theo thread

**Mapped Diagnostic Context (MDC)** thường được dùng để tự động gắn một số field vào mọi dòng log trong cùng thread:

~~~java
MDC.put("requestId", requestId);
MDC.put("recipient", recipientEmail); // Không nên.
~~~

Khi một ứng dụng thêm recipient vào MDC, mọi thư viện và component ghi log trong thread đó có thể vô tình đưa recipient ra hệ thống tập trung. Nếu MDC được copy sang executor, phạm vi rò còn rộng hơn.

Thay bằng:

~~~java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored =
        MDC.putCloseable("mailJobId", jobId)) {

    mailSender.send(message);
} finally {
    // putCloseable sẽ xóa key ở cuối phạm vi này;
    // nếu key đã có giá trị cũ, cần tự quản lý việc khôi phục.
}
~~~

`mailJobId` nên là ID ổn định không được tạo bằng cách ghép email hay subject. Nếu cần correlation theo recipient, tạo HMAC token ở một số sự kiện đã cho phép, không đặt token vào mọi dòng log chỉ vì tiện.

### @Async và context propagation

`@Async("mailTaskExecutor")` chuyển công việc sang thread khác. MDC của HTTP request thread **không tự truyền** sang worker; nếu dùng `TaskDecorator` để copy MDC, hãy xác định những field được phép copy.

~~~text
HTTP request thread
  MDC: requestId, userEmail, recipient
                |
                v
      Copy toàn bộ MDC?
                |
                +-- Rò userEmail/recipient sang worker log

Thiết kế tốt hơn:
  Command: jobId, notificationType, allowed metadata
                |
                v
  Mail worker MDC: mailJobId, traceId, phase
~~~

Đừng chỉ bảo đảm cleanup bằng `MDC.clear()` rồi quên rằng dữ liệu nhạy cảm đã được log trước khi clear. Quy tắc tốt nhất là **không đưa recipient vào MDC ngay từ đầu**. Với thread pool, cần khôi phục hoặc xóa context trong `finally` để tránh dữ liệu của task trước rò vào task sau.

## 20. Distributed tracing và trace baggage cũng là nơi chứa dữ liệu

OpenTelemetry và các hệ tracing có thể nhận attributes từ application code, HTTP instrumentation, message broker hoặc logging bridge. Ví dụ không nên:

~~~text
span=mail.smtp.submit
attributes:
  mail.recipient=user@example.test
  mail.subject=Your password reset link
  mail.body=...
~~~

Ngay cả khi không in vào application log, tracing backend có thể giữ span attributes với retention, quyền truy cập và export khác. Vì thế quy tắc loại PII phải áp cho:

- Span attributes và span events.
- Trace baggage và context propagation.
- Log-to-trace correlation.
- Message queue/broker attributes.
- Error/exception event details.

Thiết kế tốt hơn:

~~~text
span=mail.smtp.submit
attributes:
  mail.notification_type=ORDER_RECEIPT
  mail.provider=PRIMARY_SMTP
  mail.attempt=2
  mail.result=ACCEPTED
  mail.recipient_count_bucket=1
~~~

`traceId` và `spanId` giúp liên kết hoạt động giữa các service mà không cần địa chỉ email. Tuy nhiên, trong một số hệ thống trace ID có thể được nối tới request/account trong database hoặc hệ thống observability khác. Do đó chúng vẫn cần quyền truy cập, retention và chính sách export phù hợp.

### Không đưa recipient vào baggage

Baggage thường được truyền qua ranh giới service, đôi khi đến cả downstream không thuộc ứng dụng. Nếu đặt `recipientEmail` hoặc một pseudonym ổn định vào baggage, dữ liệu có thể đi xa hơn dự tính. Dùng correlation ID ngẫu nhiên, phạm vi tối thiểu và chỉ những key cần cho distributed tracing.

## 21. Metrics: không dùng email hoặc HMAC làm label

Một metric thường được lưu thành nhiều time series theo tập label:

~~~text
mail_submission_total{
  recipient="customer@example.test",
  result="success"
}
~~~

Đây là anti-pattern vì:

1. Recipient là dữ liệu cá nhân bị ghi vào hệ thống metrics.
2. Mỗi email tạo một label value mới, gây **high cardinality**.
3. Lượng time series lớn làm tăng chi phí lưu trữ và có thể làm hệ metrics không ổn định.
4. Một người có quyền xem metric có thể tìm địa chỉ và lịch sử gửi.

Thay bằng:

~~~text
mail_submission_total{
  notification_type="ORDER_RECEIPT",
  provider="PRIMARY_SMTP",
  result="SMTP_ACCEPTED"
}
~~~

Nếu cần phân tích theo recipient, tìm qua hệ thống job/audit có quyền truy cập thích hợp. **HMAC token cũng không phù hợp làm label metrics**: nó vẫn có cardinality cao và vẫn có khả năng liên kết người nhận.

### Ví dụ Micrometer với tag cố định

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MailMetrics {
    private final MeterRegistry registry;

    public MailMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordSubmission(
            String notificationType,
            String result) {
        Counter.builder("mail_submission_total")
                .tag("notification_type", notificationType)
                .tag("result", result)
                .register(registry)
                .increment();
    }
}
~~~

`notificationType` và `result` phải đến từ enum hoặc danh sách giá trị đã được duyệt, không phải input tùy ý. `mail_submission_total` trong ví dụ là tên logic của metric ở application; backend Prometheus có thể xử lý hậu tố `_total` theo convention riêng. Nên thống nhất naming với dự án.

Một số metric hữu ích khác:

| Metric | Mục đích | Label nên có |
|---|---|---|
| Submission attempts | Số lần thử gửi | Provider, loại thông báo, result |
| SMTP latency | Độ trễ submission | Provider, result |
| Outbox backlog | Số job đang chờ | Status, loại thông báo |
| Retry count | Số job cần thử lại | Loại lỗi tổng quát |
| Authentication failures | Phát hiện secret/provider lỗi | Provider |
| Invalid recipient count | Theo dõi dữ liệu đầu vào lỗi | Loại thông báo, nguồn |
| Mail task rejection | Executor quá tải | Tên executor cố định |

Không dùng `recipientToken`, `mailJobId`, subject, exception message hoặc SMTP response nguyên văn làm tag. Một số field chỉ thích hợp cho **log có kiểm soát**, không thích hợp cho metrics.

## 22. Outbox và retry: lưu dữ liệu thật đúng nơi, log chỉ metadata

Với **transactional outbox**, bảng job có thể cần giữ recipient thật để worker gửi lại sau crash. Điều đó không có nghĩa worker được phép dump toàn bộ row vào log.

Ví dụ outbox record:

~~~json
{
  "id": "mail-job-7f3a",
  "notificationType": "ORDER_RECEIPT",
  "recipient": "customer@example.test",
  "status": "RETRY",
  "attemptCount": 3,
  "lastErrorCode": "SMTP_TEMPORARY_FAILURE"
}
~~~

Log tương ứng:

~~~text
event=mail_job_retry_scheduled
jobId=mail-job-7f3a
notificationType=ORDER_RECEIPT
attempt=3
errorCode=SMTP_TEMPORARY_FAILURE
nextAttemptBucket=1m_5m
~~~

Outbox payload được bảo vệ bằng database access policy, encryption và retention theo yêu cầu. Log không nên chứa `recipient`, toàn bộ payload, raw MIME hoặc nested SMTP exception.

### Không lưu raw exception làm last_error theo thói quen

Một số hệ thống ghi:

~~~java
job.setLastError(ex.toString());
~~~

Giá trị này có thể mang địa chỉ người nhận hoặc nội dung trả về từ provider. Dù nằm trong database chứ không phải log, nó vẫn làm tăng bản sao dữ liệu nhạy cảm và dễ bị lộ khi admin UI hoặc log về sau dump row.

Thay vào đó:

~~~text
lastErrorCode=SMTP_TEMPORARY_FAILURE
lastErrorPhase=RCPT_TO
lastErrorAt=...
attemptCount=3
~~~

Nếu thật sự cần raw diagnostic cho một sự cố đặc biệt, lưu trong kênh có quyền hạn chế, thời hạn ngắn và audit truy cập; không dùng trường text tự do được sao chép qua mọi hệ thống.

### Một job có thể có nhiều recipient

Nếu một email chứa nhiều To/Cc/Bcc, lỗi một recipient có thể ảnh hưởng một phần message. Log nên dùng `jobId`, số lượng recipient bị từ chối và mã nguyên nhân tổng quát. Dữ liệu danh tính cụ thể chỉ được tra cứu qua job store theo quyền. Không biến danh sách failed addresses từ `MailSendException` thành log chung.

## 23. Structured logging và redaction filter: chọn lớp bảo vệ nào?

Có hai chiến lược:

**Chiến lược A — Chỉ xuất trường đã cho phép tại nguồn (ưu tiên)**

~~~text
Mail service
   |
   v
SafeMailEvent(jobId, type, outcome, attempt)
   |
   v
Structured log encoder
   |
   v
Log collector
~~~

Không có trường email ở đối tượng log. Đây là cách đơn giản nhất để tránh thông tin bị đưa đi ngay từ đầu.

**Chiến lược B — Redaction filter ở pipeline**

~~~text
Application logs
   |
   v
Redaction / processor
   |
   v
Centralized log storage
~~~

Một filter ở encoder/collector là biện pháp **phòng vệ bổ sung** cho các đường rò chưa nhận diện. Nhưng nó không thể bảo đảm mọi trường hợp:

- Địa chỉ có thể nằm trong quoted display name, một chuỗi JSON, một stack trace hoặc nested exception.
- MIME header có thể bị fold qua nhiều dòng.
- Dữ liệu có thể được Base64/quoted-printable encode.
- Địa chỉ quốc tế hoặc mailbox cú pháp đặc biệt khó bắt bằng regex đơn giản.
- Dữ liệu có thể đã đi qua stdout, sidecar hoặc forwarder **trước khi redaction xảy ra**.

Vì vậy **không dựa hoàn toàn vào regex thay email trong log line**. Thiết kế không log PII tại nguồn trước, filter chỉ để giảm thiểu lỗi sót.

### Regex thay chuỗi không phải email parser

Ví dụ một regex đơn giản:

~~~text
[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+
~~~

có thể phát hiện địa chỉ phổ biến, nhưng không bao phủ đầy đủ RFC email syntax, Unicode, quoted local-part hoặc các trường hợp multiline/header encoding. Nó cũng có thể nhận nhầm một chuỗi kỹ thuật thành email.

Một pipeline có thể dùng redaction theo **tên field có cấu trúc** (`recipient`, `to`, `cc`, `bcc`) cùng với các rule bổ sung cho unstructured data. Không có filter nào thay cho việc xác định luồng dữ liệu từ đầu.

## 24. Bảo vệ HTTP logging, message consumer và admin UI

Ngay cả khi mail sender log an toàn, **đường vào** của mail request có thể bị log trước:

~~~http
POST /api/send-notification
Content-Type: application/json

{
  "recipient": "customer@example.test",
  "template": "ORDER_RECEIPT"
}
~~~

Nếu HTTP request logging middleware ghi toàn bộ body, recipient đã bị lộ trước khi `JavaMailSender` chạy. Tương tự:

- Spring MVC/WebFlux request logging.
- API gateway access log có query string chứa email.
- Kafka/RabbitMQ consumer ghi nguyên message.
- Admin endpoint xuất outbox record dạng JSON.
- AOP aspect log toàn bộ method arguments.
- Error handler trả hoặc log nguyên request/exception.

Cần bảo vệ từ **entrypoint đến egress**, không chỉ mail adapter.

### Một chính sách input/output rõ ràng

| Ranh giới | Cách làm |
|---|---|
| HTTP/API | Không log body/recipient hoặc cấu hình field redaction |
| Application service | Chỉ log jobId/type/outcome |
| Outbox DAO | Không dump entity/payload |
| Broker consumer | Không log raw event chứa recipient |
| MIME composer | Không log MimeMessage hoặc attachment |
| SMTP adapter | Không log raw exception/protocol transcript |
| Central collector | Thêm redaction filter, quyền, retention |
| Support UI | Lookup theo jobId, cấp quyền và audit |

### Đừng dùng email trong URL query nếu có lựa chọn khác

Một endpoint như:

~~~text
GET /mail-status?email=customer@example.test
~~~

dễ bị ghi vào access log/proxy/browser history. Nên dùng job ID hoặc endpoint tra cứu có authorization, không đặt email vào query chỉ để thuận tiện tìm log. Đối với unsubscribe URL có token, token đó cũng phải được coi là dữ liệu nhạy cảm và tránh xuất ra log.

## 25. Unit test tính ổn định và phạm vi của recipient HMAC token

Trước khi đưa HMAC token vào hệ thống quan sát, cần xác định hai tính chất:

1. Cùng canonical mailbox và cùng khóa/phiên bản tạo cùng token.
2. Token không chứa raw mailbox và không được thay thế bằng SHA-256 thuần.

Ví dụ JUnit 5 + AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Arrays;
import org.junit.jupiter.api.Test;

class RecipientTokenServiceTest {

    private RecipientTokenService newService(
            byte keyByte, String version) {
        // Khóa cố định chỉ để test; không dùng trong production.
        byte[] key = new byte[32];
        Arrays.fill(key, keyByte);
        return new RecipientTokenService(key, version);
    }

    @Test
    void stableForSameMailboxAndDomainCase()
            throws Exception {
        RecipientTokenService service =
                newService((byte) 0x42, "v1");

        String first =
                service.token("Alice@Example.COM");
        String second =
                service.token("Alice@example.com");

        assertThat(first).isEqualTo(second);
        assertThat(first).startsWith("v1:");
        assertThat(first).doesNotContain("Alice");
        assertThat(first).doesNotContain("example.com");
    }

    @Test
    void changesWhenKeyOrVersionChanges()
            throws Exception {
        String recipient = "Alice@example.com";

        String v1 = newService((byte) 1, "v1")
                .token(recipient);
        String v2 = newService((byte) 2, "v2")
                .token(recipient);

        assertThat(v1).isNotEqualTo(v2);
    }

    @Test
    void doesNotSilentlyLowercaseLocalPart()
            throws Exception {
        RecipientTokenService service =
                newService((byte) 1, "v1");

        assertThat(service.token("Alice@example.com"))
                .isNotEqualTo(
                        service.token("alice@example.com"));
    }
}
~~~

Đây là unit test cho **canonicalization policy đã chọn** và cơ chế HMAC, không phải khẳng định hai địa chỉ local-part khác hoa/thường nhất định là hai mailbox khác nhau trong mọi provider.

### Test khi input không hợp lệ

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.mail.internet.AddressException;
import org.junit.jupiter.api.Test;

class CanonicalizationFailureTest {
    @Test
    void refusesMalformedAddress() {
        assertThatThrownBy(() ->
                RecipientCanonicalizer.canonicalMailbox(
                        "not-an-email"))
                .isInstanceOf(AddressException.class);
    }
}
~~~

Không nên log địa chỉ không hợp lệ trong catch của validator. Nếu kẻ tấn công đưa chuỗi tùy ý vào trường email, việc log input có thể làm lộ token hoặc tạo log injection dù parser đã từ chối.

### Test không đủ để chứng minh bảo mật của khóa

Một unit test tính đúng HMAC không chứng minh secret được cấp an toàn ở runtime. Cần kiểm soát secret store, secret rotation, quyền đọc và khả năng log cấu hình. Không ghi khóa test vào tài liệu triển khai như một khóa production.

## 26. Unit test bảo đảm log mail không chứa địa chỉ thật

Đối với dự án dùng **Logback** trong test (một lựa chọn phổ biến với Spring Boot), có thể dùng `ListAppender` để capture output của logger và kiểm tra rằng message không chứa email:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import java.util.Arrays;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class MailSafeLoggerTest {
    @Test
    void logsRecipientTokenInsteadOfRawEmail() {
        byte[] key = new byte[32];
        Arrays.fill(key, (byte) 7);
        RecipientTokenService tokens =
                new RecipientTokenService(key, "test-v1");
        MailSafeLogger safeLogger =
                new MailSafeLogger(tokens);

        Logger logger = (Logger) LoggerFactory
                .getLogger(MailSafeLogger.class);
        ListAppender<ILoggingEvent> appender =
                new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        try {
            safeLogger.submissionStarted(
                    "job-123",
                    "ORDER_RECEIPT",
                    "secret.person@example.test",
                    1);

            String output = appender.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .collect(Collectors.joining("\n"));

            assertThat(output)
                    .contains("job-123")
                    .contains("recipientToken=test-v1:")
                    .doesNotContain("secret.person@example.test")
                    .doesNotContain("secret.person")
                    .doesNotContain("example.test");
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

Test chỉ xác minh output của component `MailSafeLogger` khi sử dụng Logback. Nó chưa kiểm tra toàn bộ hệ thống:

- SMTP protocol debug có bật hay không.
- HTTP middleware, Kafka consumer hoặc outbox DAO có log recipient.
- Logback JSON encoder/collector có tự enrich thêm field chứa email.
- Exception ở framework boundary có bị ghi nguyên stack trace.

Vì vậy nên có integration test hoặc test cấu hình cho những đường rò chính, ngoài unit test của logger.

### Test phải chạy độc lập khi nhiều class ghi cùng logger

`ListAppender` tạm thời gắn vào logger dùng chung. Nếu test chạy song song hoặc nhiều thread cùng ghi, output có thể chứa dòng của test khác. Có thể tạo logger riêng cho test, khóa phạm vi test, hoặc điều chỉnh isolation phù hợp. Luôn detach appender trong `finally` để không gây tác dụng phụ.

### Negative assertion với exception nhạy cảm

Một bài test có thể tạo thông điệp lỗi chứa recipient giả:

~~~java
String simulatedProviderResponse =
        "550 5.1.1 <secret.person@example.test> unknown";
~~~

Rồi kiểm tra bộ phân loại chỉ trả một `MailFailureCode` an toàn và đường logging không in raw response. Không tạo test cố tình log toàn bộ exception rồi trông chờ filter “luôn chắc chắn” xóa sạch mọi email.

## 27. Kiểm thử các đường rò ngoài logger

Một ma trận kiểm thử tốt nên bao phủ nhiều ranh giới:

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| TC-01 | Mail gửi thành công | Log chỉ có jobId/type/result, không raw recipient |
| TC-02 | SMTP auth thất bại | Log mã AUTHENTICATION_FAILED, không password hay địa chỉ |
| TC-03 | SMTP 550 echo recipient | Exception chain không bị in ra log thông thường |
| TC-04 | MailSendException chứa map message thất bại | Không dump `failedMessages` hoặc `MimeMessage` |
| TC-05 | To/Cc/Bcc cùng tồn tại | Không log danh sách raw addresses |
| TC-06 | @Async mail worker | MDC chỉ có key được phép, cleanup sau task |
| TC-07 | Outbox retry job | Log metadata/retry, không dump payload JSON |
| TC-08 | HMAC cùng mailbox, cùng key | Token nhất quán |
| TC-09 | HMAC đổi key | Token đổi và version rõ ràng |
| TC-10 | Domain viết hoa/IDN | Canonicalization nhất quán theo policy |
| TC-11 | Email có plus tag | Không tự xóa tag nếu policy chưa cho phép |
| TC-12 | Recipient có địa chỉ invalid | Không echo input vào log |
| TC-13 | HTTP request chứa email | Request logging không in body/query nhạy cảm |
| TC-14 | Broker message chứa recipient | Consumer logging không dump payload |
| TC-15 | Jakarta Mail debug | Production config không bật protocol transcript |
| TC-16 | Metrics | Label không chứa email, token, job ID |
| TC-17 | Distributed trace | Attributes/baggage không chứa recipient |
| TC-18 | Log export/alert | Không tự enrich raw email từ database |
| TC-19 | Key rotation | Token version mới, không lộ mapping trong log |
| TC-20 | Một incident cần tìm recipient | Lookup có authorization và audit riêng |

Đây là **tập tình huống kiểm thử chức năng/bảo mật cho code**, không phải thay cho một lượt QA nội dung tài liệu. Mỗi môi trường cần chọn cách kiểm tra phù hợp với framework logging, mail provider và observability stack đang chạy.

### Không chạy SMTP production trong unit test

Các test về redaction, HMAC và exception classification có thể sử dụng recipient giả `@example.test`, mock sender và simulated provider response. Không cần gửi email thật hoặc kích hoạt SMTP protocol debug để xác minh chính sách logging.

## 28. Tìm sự cố khi log không chứa địa chỉ email

Một phản đối phổ biến là: “Nếu không ghi địa chỉ, đội hỗ trợ làm sao biết email của khách hàng có gửi không?”

Có thể dùng quy trình tra cứu theo quyền:

~~~text
Nhân viên hỗ trợ nhận yêu cầu khách hàng
          |
          v
Xác thực quyền tra cứu và mục đích
          |
          v
Tra mail job theo orderId / accountId
trong giao diện có kiểm soát
          |
          v
Nhận jobId và trạng thái
          |
          v
Tra centralized log bằng jobId
          |
          v
Xem lỗi và retry, không cần email trong log
~~~

Nếu phải tra nhiều job của cùng recipient mà hệ thống không có user ID đáng tin, một công cụ nội bộ có thể:

1. Nhận email từ người có quyền.
2. Canonicalize theo cùng policy.
3. Tính HMAC theo đúng key version.
4. Trả token hoặc kết quả tra cứu được giới hạn, có audit.
5. Không ghi email đầu vào của công cụ vào application log.

**Không công khai API “hash email bất kỳ” mà không có rate limit và authorization.** Một endpoint như vậy có thể bị dùng làm oracle để tính token cho danh sách email ứng viên, làm giảm lợi ích của HMAC.

### Correlation ID nên được thiết kế từ đầu

Một `jobId` ngẫu nhiên hoặc ID opaque là công cụ chẩn đoán tốt:

- Thêm vào record outbox.
- Ghi khi tạo job, claim, retry và submit.
- Gắn vào trace để nối các service.
- Trả về trong giao diện quản trị phù hợp.
- Không encode raw recipient trong ID.

Một job ID chưa chắc là dữ liệu ẩn danh tuyệt đối nếu nội bộ có thể map tới người dùng; vẫn cần hạn chế quyền truy cập. Nhưng nó giúp tránh phơi địa chỉ qua nhiều hệ thống cùng lúc.

## 29. Phân quyền, retention và khả năng xóa dữ liệu log

Masking hoặc HMAC không thay cho governance. Với dữ liệu liên kết được tới người nhận, cần xác định:

- Ai có quyền xem log chi tiết và recipient token?
- Ai có quyền export log ra hệ thống bên ngoài?
- Log giữ bao lâu theo môi trường và loại thông báo?
- Có cần xóa/giảm thông tin khi yêu cầu xóa dữ liệu hợp lệ phát sinh?
- Ai được truy cập khóa HMAC hoặc công cụ tính token?
- Điều tra sự cố cần giữ dữ liệu bao lâu và có audit không?
- Backup/replica của log và secret có cùng retention và access policy không?

Một chính sách minh họa:

| Loại dữ liệu | Nơi lưu | Kiểm soát |
|---|---|---|
| Recipient thật | DB nghiệp vụ/outbox | Encryption, RBAC, retention |
| Recipient HMAC token | Log khi thật sự cần | Quyền đọc, thời hạn, không export rộng |
| Key HMAC | Secret manager | Quyền workload, rotate, audit |
| Job ID | Log/tracing | Không encode email, truy cập theo vai trò |
| Raw SMTP transcript | Không lưu mặc định | Chỉ điều tra có phê duyệt, xóa sớm |
| Thông tin lỗi chuẩn hóa | Log/outbox | Enum/code cố định, không raw provider response |

**HMAC ổn định có thể khiến việc xóa thông tin một người khỏi log đã lưu phức tạp hơn.** Nếu retention hoặc quyền xóa là yêu cầu đáng kể, cân nhắc không log token hoặc sử dụng token có phạm vi/tuổi thọ ngắn thay vì một pseudonym xuyên nhiều năm.

Không mặc định việc xóa khóa HMAC cũng tương đương xóa mọi dữ liệu liên quan: các event có thể vẫn được liên kết qua job ID, tenant, timestamp hoặc metadata khác.

## 30. Quy trình xử lý khi phát hiện email đã rò vào log

Giả sử một thay đổi code đã thêm `recipient` vào log production. Cần coi đây là sự cố quản trị dữ liệu, không chỉ một lỗi format:

1. **Ngăn nguồn rò:** tắt protocol debug, rollback hoặc sửa log event tại nguồn.
2. **Xác định phạm vi:** môi trường nào, thời gian bắt đầu/kết thúc, logger/collector/backup nào đã nhận dữ liệu.
3. **Hạn chế truy cập tạm thời:** khóa export hoặc dashboard rộng, đảm bảo chỉ nhân sự có trách nhiệm xử lý.
4. **Đánh giá mức độ:** loại dữ liệu xuất hiện, có Bcc, token, subject, attachment hay chỉ mailbox?
5. **Thực hiện quy trình xóa/retention:** xử lý bản sao tại centralized logs, archive, ticket và backup theo khả năng hệ thống/chính sách.
6. **Điều tra nguyên nhân:** application statement, exception formatting, raw DTO, SMTP debug, tracing hay collector enrichment?
7. **Bổ sung test/guardrail:** ngăn đúng đường rò tái diễn.
8. **Theo dõi và thông báo phù hợp:** thực hiện nghĩa vụ nội bộ/pháp lý áp dụng mà không tự kết luận chỉ từ việc nhìn thấy một dòng log.

Không chỉ xóa dòng ở dashboard nếu log đã được sao chép đến nhiều sink. Cũng không nên dùng thêm một log chứa email để “thống kê các email đã lộ”.

## 31. Những anti-pattern thường gặp

### 31.1. Chỉ thay `@` thành `[at]`

~~~text
customer@example.test -> customer[at]example.test
~~~

Đây không phải masking hiệu quả. Người đọc dễ dàng khôi phục địa chỉ, trong khi nhiều hệ thống tìm kiếm vẫn có thể nhận diện nó.

### 31.2. Băm SHA-256 thuần rồi công bố là ẩn danh

Email có thể được đoán từ danh sách ứng viên và tính lại digest. Nếu cần token tương quan chống thử từ điển từ bản log bị lộ, dùng HMAC với khóa bảo mật và giới hạn quyền gọi.

### 31.3. Dùng SMTP password làm HMAC key

Khi một secret bị lộ hoặc rotate, cả hệ thống SMTP và cơ chế pseudonymization bị ảnh hưởng. Tách khóa theo mục đích; không dùng chung credential.

### 31.4. Tạo HMAC key ngẫu nhiên mỗi lần service khởi động

~~~java
byte[] key = new byte[32];
new SecureRandom().nextBytes(key);
// Tạo mới ở mỗi replica/startup: token không còn ổn định.
~~~

Với correlation liên phiên, tất cả replica cần cùng một khóa bí mật được cấp từ secret store theo chính sách. Không dùng seed từ thời gian khởi động hoặc host name.

### 31.5. Lower-case local-part và xóa plus-tag vô điều kiện

`Alice+orders@example.com` không nhất thiết tương đương `alice@example.com` với mọi mail provider. Canonicalization cần được định nghĩa theo dữ liệu sản phẩm, không bê một quy tắc của provider phổ biến áp cho toàn Internet.

### 31.6. Log token HMAC trong mọi metric label

Token vẫn có cardinality cao và tạo liên kết hành vi. Metric nên dùng tên loại email, provider và status có tập giá trị giới hạn; recipient correlation thuộc log hoặc job store có kiểm soát.

### 31.7. Log raw exception khi hệ thống đang lỗi

~~~java
log.error("SMTP error for mail job", ex);
~~~

Provider có thể echo email trong message hoặc nested exception. Hãy log error code và ID đã được kiểm soát; đường ghi diagnostic chi tiết phải được cô lập.

### 31.8. Bật `mail.debug` để chẩn đoán mọi sự cố

SMTP transcript có thể chứa `RCPT TO`, sender, auth và data. Không bật ở production theo mặc định; khi cần, sử dụng môi trường sandbox và quy trình debug có thời hạn.

### 31.9. Log `toString()` của job, MIME message hoặc request

Một thay đổi thêm field `bcc` hoặc `recipient` vào DTO có thể bất ngờ làm log lộ nhiều dữ liệu. Log theo schema allowlist và kiểm soát các điểm sử dụng `@ToString`/Lombok, serialization hoặc AOP logging.

### 31.10. Mask trước khi ghi log nhưng vẫn gửi raw email trong MDC

Một dòng log an toàn không bù lại việc mọi log khác đều có MDC chứa recipient. Hãy kiểm soát cả logging context, tracing và baggage.

### 31.11. Chỉ redaction ở central collector

Dữ liệu có thể đã đi qua stdout, agent, buffer, node log và forwarder trước khi được che. Redaction ở sink là phòng vệ bổ sung; loại dữ liệu ở nguồn là ưu tiên.

### 31.12. Coi recipientToken là vô hại vì không thể giải mã trực tiếp

Token ổn định giúp liên kết hoạt động của người nhận và có thể trở thành định danh giả. Bảo vệ truy cập và retention; không công khai token và công cụ tính token cho mọi người dùng.

### 31.13. Dùng email làm job ID

~~~text
jobId=customer@example.test:ORDER_RECEIPT:3
~~~

Ngay cả khi các trường recipient khác đã được xóa, `jobId` vẫn mang email. Hãy dùng ID ngẫu nhiên/opaque không encode dữ liệu cá nhân.

### 31.14. “Khôi phục” sự cố bằng cách xuất toàn bộ mail history vào ticket

Export log/job data chứa email và nội dung sang issue tracker hoặc chat công khai có thể mở rộng phạm vi rò. Hãy cung cấp jobId, errorCode, traceId và bản dữ liệu đã được làm sạch; chỉ xem recipient thật trong công cụ có quyền.

## 32. Quy trình triển khai trong một ứng dụng Spring Mail

Một lộ trình có thể làm theo từng giai đoạn:

1. **Xác định nhu cầu quan sát:** phải tìm theo job hay thật sự cần correlation theo recipient?
2. **Liệt kê nguồn chứa email:** controller, request logging, outbox, service, SMTP adapter, exception, MDC, tracing, metrics và debug.
3. **Thiết kế schema log allowlist:** event, jobId, notificationType, outcome, attempt, duration, errorCode.
4. **Chọn policy recipient:** mặc định không log; masking cho UI hạn chế; HMAC khi thật sự cần correlation.
5. **Định nghĩa canonicalization:** domain, local-part, IDN, policy version và các trường hợp không hợp lệ.
6. **Cấp khóa HMAC riêng:** secret store, ít nhất 32 byte khóa ngẫu nhiên theo ví dụ, version và rotation.
7. **Tạo SafeMailLogger:** component chuyên tạo log theo schema, không nhận raw exception.
8. **Phân loại exception:** chỉ phát mã lỗi/phase được duyệt, không in nguyên provider message.
9. **Tắt protocol debug:** kiểm tra cấu hình Jakarta Mail và các logger/luồng output liên quan.
10. **Giữ MDC/tracing an toàn:** chỉ dùng ID, tên event và thuộc tính không nhạy cảm.
11. **Làm sạch metrics:** tag cardinality thấp, không dùng email hoặc HMAC token làm label.
12. **Bảo vệ outbox/admin lookup:** raw email chỉ nằm trong data store có quyền và retention.
13. **Viết test:** HMAC ổn định, malformed recipient, Logback capture, simulated SMTP error có email.
14. **Kiểm tra deployment:** HTTP/proxy/collector không enrich lại email vào log.
15. **Theo dõi và review:** phát hiện regression sau khi đổi mail provider, logging framework hoặc middleware.

### Mẫu phân chia trách nhiệm

~~~text
Application service
    |
    +-- creates mail job with opaque ID
    +-- stores recipient in protected outbox
    |
    v
Mail worker
    |
    +-- loads recipient for SMTP
    +-- computes optional HMAC token
    +-- emits safe event with jobId
    |
    v
JavaMailSender
    |
    +-- SMTP, protocol debug disabled
    |
    v
Safe outcome mapping
    |
    +-- result/errorCode
    +-- attempt and duration
    |
    v
Log/trace/metrics without raw recipient
~~~

Hãy áp quyền truy cập và vòng đời cho cả **dữ liệu thật trong outbox** lẫn **dữ liệu giả danh trong observability**. Việc tách chúng về mặt kỹ thuật giúp giảm phạm vi lộ thông tin mà vẫn giữ khả năng chẩn đoán.

## 33. Câu hỏi thường gặp

**Có nên luôn log recipient đã che một phần?** Không. Nếu `jobId` và trạng thái đủ để tìm lỗi, không ghi recipient là tốt nhất. Masking chỉ dùng khi có nhu cầu rõ ràng.

**Masking `u***@example.com` có phải ẩn danh không?** Không. Domain và một phần local-part vẫn có thể giúp suy ra người nhận, nhất là khi kết hợp thời gian và loại email.

**SHA-256(email) có thể đảo ngược không?** Digest không phải phép mã hóa hai chiều, nhưng attacker có thể thử từ điển địa chỉ email và so digest. Đây là rủi ro chính với hash không khóa.

**HMAC-SHA-256 có bảo đảm token không chứa PII?** HMAC không hiển thị địa chỉ trực tiếp nhưng token vẫn là một định danh giả có thể liên kết hoạt động. Quyền truy cập, retention và phạm vi sử dụng vẫn cần kiểm soát.

**Vì sao phải có keyVersion trong token?** Để biết token được tạo bằng khóa nào khi rotate. Không so trực tiếp hai token từ các key version khác nhau và kết luận đây là hai người nhận.

**Có cần băm toàn bộ email theo chữ thường không?** Không mặc định. Domain không phân biệt hoa/thường, local-part có semantics phụ thuộc hệ thống. Cần chính sách canonicalization rõ ràng và nhất quán.

**Có nên bỏ `+tag` hoặc dấu chấm trong email Gmail?** Không dùng quy tắc provider riêng làm mặc định toàn hệ thống. Nếu sản phẩm có chuẩn hóa đặc thù đã được xác minh, hãy tách và version hóa quy tắc đó.

**Tại sao không dùng recipient HMAC token làm Prometheus label?** Token có cardinality cao và vẫn liên kết người nhận. Metric nên có tập label nhỏ và không mang định danh cá nhân.

**Có thể ghi đầy đủ `ex.getMessage()` nếu đã mask recipient trước đó?** Không chắc. Exception và SMTP response có thể tự chứa địa chỉ, domain hoặc body. Hãy log mã lỗi an toàn và kiểm soát stack trace.

**Đã tắt log DEBUG của ứng dụng, có còn rò SMTP không?** Có thể. Jakarta Mail có session debug output riêng, logger của provider hoặc cấu hình runtime khác. Cần kiểm soát tất cả nguồn.

**SMTP có thể đưa email vào exception dù ứng dụng không log recipient?** Có. Provider có thể trả lỗi chứa `RCPT TO` hoặc địa chỉ bị từ chối. Không in raw exception ra log chung.

**Có nên log `MimeMessage` để debug ảnh inline/attachment?** Không trong production. Dùng MIME unit test, SMTP sink, file giả hoặc kho diagnostic có quyền hạn chế khi thật sự cần.

**To, Cc và Bcc có phải dùng cùng policy không?** Có. Bcc đặc biệt cần chú ý vì có thể xuất hiện trong SMTP envelope hoặc debug dù không được hiển thị trong mail người nhận.

**Nếu cần tìm toàn bộ lỗi gửi tới một người thì làm sao?** Dùng hệ thống lookup theo quyền từ account/order/email để lấy jobId; nếu thật sự cần, tính HMAC trong công cụ nội bộ có audit và tra token, không công khai raw address trong log.

**Cần log HMAC cho mọi recipient hay chỉ một số?** Chỉ những sự kiện có nhu cầu correlation. Một token ổn định được ghi quá thường xuyên có thể tiết lộ lịch sử hoạt động dù không lộ địa chỉ.

**Nếu key HMAC bị lộ thì sao?** Rotate, đánh giá khả năng đối chiếu từ điển từ log cũ, hạn chế truy cập và xử lý theo quy trình incident response. Đừng coi các token được tạo bằng khóa đã lộ là bảo vệ mạnh nữa.

**Có thể chỉ đặt một regex redaction trong Logback?** Không nên dùng làm biện pháp duy nhất. Regex không bao phủ đầy đủ MIME, Unicode, multiline, encoded content và log trước filter. Cần loại dữ liệu ở nguồn.

**Thông tin SMTP status `550` có an toàn để log không?** Mã số đã được trích xuất/kiểm soát thường hữu ích; tránh log cả raw response vì nó có thể chứa địa chỉ và thông tin provider.

**Ẩn recipient trong log có ngăn được rò từ outbox không?** Không. Outbox vẫn phải lưu thông tin cần gửi và cần chính sách quyền, encryption, retention và audit riêng.

**Có cần kiểm tra logging của HTTP và broker không?** Có. Email có thể bị ghi vào log ở đầu vào trước khi tới mail service; chính sách cần xuyên suốt pipeline.

## 34. Tổng kết

Trong **Spring Framework Mail**, quan sát hệ thống gửi thư không yêu cầu mặc định ghi địa chỉ người nhận vào log. Phần lớn sự cố có thể chẩn đoán bằng **jobId, notificationType, trạng thái, attempt, thời gian xử lý, provider và errorCode đã chuẩn hóa**.

Khi cần giảm khả năng lộ thông tin:

1. **Không log recipient** nếu không có yêu cầu tương quan thực sự.
2. **Masking** chỉ là che một phần, vẫn có thể làm lộ domain hoặc danh tính.
3. **HMAC-SHA-256 với khóa bí mật** phù hợp hơn SHA-256 thuần khi cần token ổn định để correlation; quản lý key, version và canonicalization rõ ràng.
4. **Không log raw MailException, MimeMessage hoặc SMTP debug transcript**, vì những dữ liệu đó có thể chứa To/Cc/Bcc, địa chỉ bị từ chối và nội dung.
5. **Không dùng email/HMAC làm metric label**, không đưa recipient vào MDC, tracing baggage hoặc request logs.
6. **Bảo vệ dữ liệu ở mọi lớp**: ứng dụng, outbox, HTTP, broker, SMTP client, collector, dashboard và công cụ tra cứu.

Một ví dụ log lý tưởng:

~~~text
event=mail_submission_failed
jobId=job-7f3a
notificationType=ORDER_RECEIPT
provider=PRIMARY_SMTP
errorCode=SMTP_TEMPORARY_FAILURE
attempt=3
retryScheduled=true
~~~

Nếu cần đối chiếu nhiều job của cùng người nhận, bổ sung recipient HMAC token theo chính sách quyền và retention; không đưa địa chỉ email thật vào chuỗi log.

**Nguyên tắc cốt lõi:** log phải đủ để vận hành, nhưng không nên trở thành bản sao phân tán của database khách hàng. Giảm dữ liệu từ nguồn, dùng pseudonym có khóa khi cần và kiểm tra tất cả đường có thể làm lộ người nhận sẽ giúp hệ thống mail vừa quan sát được vừa bảo vệ tốt hơn quyền riêng tư.
