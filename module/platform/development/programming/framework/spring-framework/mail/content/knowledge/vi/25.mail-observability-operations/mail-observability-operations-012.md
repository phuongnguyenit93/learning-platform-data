# Kiểm tra health indicator không gửi email thật ngoài ý muốn

Trong hệ thống **Spring Framework Mail**, người vận hành cần biết ứng dụng còn có thể kết nối đến máy chủ SMTP hay không. Spring Boot Actuator hỗ trợ health indicator cho nhiều dependency, trong đó có khả năng kiểm tra mail server khi ứng dụng sử dụng cấu hình tương thích. Tuy nhiên, một phép kiểm tra sức khỏe chạy tự động có thể được gọi liên tục bởi load balancer, Kubernetes, hệ thống monitoring hoặc người quản trị.

Nếu triển khai health check bằng cách tạo `MimeMessage` rồi gọi `JavaMailSender.send(...)`, mỗi lần probe có thể **gửi một email thật**. Tưởng rằng đây chỉ là “email thử”, hệ thống có thể vô tình gửi hàng nghìn thư trong ngày, làm đầy mailbox, tiêu hao quota, kích hoạt giới hạn tốc độ, ảnh hưởng reputation hoặc gửi dữ liệu tới người nhận không mong muốn.

**Nguyên tắc chính: health indicator kiểm tra trạng thái hệ thống, không được tự động tạo tác động gửi email thật.** Với SMTP, nên phân biệt giữa kiểm tra cấu hình, kiểm tra kết nối/xác thực, kiểm tra khả năng worker xử lý và kiểm thử phân phát đầu-cuối. Mỗi mức có chi phí, ý nghĩa và cách triển khai riêng.

Bài học này trình bày cách dùng `JavaMailSenderImpl.testConnection()` và Spring Boot Actuator một cách an toàn, cách tránh gọi `send` trong health endpoint, cấu hình timeout, phân tách liveness/readiness, kiểm thử bằng mock và SMTP test server, cùng quy trình vận hành để không biến cơ chế monitoring thành nguồn phát tán email ngoài ý muốn.

## 1. Vì sao health indicator có thể gây gửi email ngoài ý muốn?

Hãy xét một health indicator tự viết:

```java
// KHÔNG NÊN: mỗi lần health() được gọi lại gửi một email thật.
@Component("unsafeMail")
public class UnsafeMailHealthIndicator implements HealthIndicator {

    private final JavaMailSender mailSender;

    public UnsafeMailHealthIndicator(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public Health health() {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo("operations@example.org");
        message.setSubject("Mail health check");
        message.setText("Checking email");

        mailSender.send(message);

        return Health.up().build();
    }
}
```

Logic trên tưởng như kiểm tra được “email có gửi thành công không”. Nhưng mỗi lần gọi `/actuator/health` hoặc health group có chứa indicator đó, ứng dụng lại phát sinh một lần gửi. Một số hệ thống probe rất thường xuyên, và nhiều replica có thể cùng thực hiện.

Ví dụ minh họa:

```text
3 application replicas
    × 1 health probe every 10 seconds
    × 24 hours

= 25,920 health invocations/day
= up to 25,920 real emails/day nếu mỗi probe gọi send()
```

Con số này chỉ minh họa tác động của cách thiết kế; tần suất thực tế phụ thuộc nền tảng và số endpoint được gọi. Nếu có nhiều hệ thống cùng truy vấn, số lần gửi còn có thể cao hơn.

Tác hại không chỉ là chi phí:

- Hộp thư nhận bị spam bởi email tự động.
- Provider coi hệ thống gửi bất thường và áp dụng throttling/suspension.
- Sự kiện gửi giả làm sai metric và dashboard.
- Email health check lẫn vào email nghiệp vụ, gây nhiễu audit.
- Kiểm tra endpoint có thể làm lộ người nhận hoặc cấu hình nội bộ.
- Một sự cố SMTP làm health probe gửi lại liên tục thay vì tập trung khôi phục.
- Nếu mail chứa dữ liệu môi trường, có nguy cơ rò rỉ thông tin.

**Không dùng `JavaMailSender.send(...)` làm phép thử định kỳ của health endpoint.**

## 2. Phân biệt bốn mức độ kiểm tra

Không phải mọi phép kiểm tra “mail khỏe” đều cần gửi thư. Cần chọn mức nhỏ nhất đủ phục vụ quyết định vận hành.

| Mức | Kiểm tra điều gì? | Có gửi email thật? | Có chứng minh inbox delivery? |
|---|---|---|---|
| **Configuration check** | Host, port, secret reference, timeout và chính sách cấu hình hợp lệ | Không | Không |
| **Connectivity/authentication check** | Có thể kết nối hoặc xác thực với SMTP server hay không | Không | Không |
| **Pipeline health check** | Worker, queue, outbox, backlog và khả năng xử lý đang hoạt động | Không cần | Không |
| **Controlled end-to-end synthetic test** | Hệ thống thực sự submit rồi quan sát mailbox/event trong môi trường được kiểm soát | Có, nhưng chỉ theo lịch/phê duyệt | Chỉ xác nhận theo bằng chứng và phạm vi bài kiểm tra |

Health endpoint thông thường nên tập trung vào configuration, connectivity và pipeline state. End-to-end synthetic test là một **quy trình kiểm thử riêng**, có hạn chế người nhận, quota và tần suất, không phải việc được thực hiện mỗi lần Kubernetes hỏi sức khỏe Pod.

### Connection thành công không đồng nghĩa delivery

Ngay cả khi SMTP server chấp nhận kết nối, xác thực thành công và `testConnection()` trả về bình thường, điều đó **không chứng minh**:

- User và địa chỉ `From` có quyền gửi mọi loại thư.
- Recipient tồn tại hoặc được phép nhận.
- Message vượt qua giới hạn kích thước/nội dung.
- Server đích đã chấp nhận email.
- Thư vào inbox thay vì spam/quarantine.
- Người nhận đã đọc thư.

Health indicator có ý nghĩa chính xác là **một tín hiệu về dependency**, không phải cam kết phân phát.

## 3. Spring Boot MailHealthIndicator hoạt động theo nguyên tắc nào?

Trong cấu hình Spring Boot Actuator phù hợp, health contributor cho mail có thể sử dụng `JavaMailSenderImpl.testConnection()` để đánh giá khả năng kết nối SMTP.

Phương thức `testConnection()` của `JavaMailSenderImpl` thực hiện việc mở một transport connection tới mail server theo cấu hình Jakarta Mail, có thể bao gồm xác thực, rồi đóng kết nối. Nó **không xây một email để gửi**, không có bước gửi MIME body tới recipient và không yêu cầu địa chỉ người nhận.

Luồng được mong đợi:

```text
GET /actuator/health
        |
        v
Mail health indicator
        |
        v
JavaMailSenderImpl.testConnection()
        |
        +-- TCP connect
        +-- SMTP greeting / protocol negotiation
        +-- STARTTLS hoặc implicit TLS theo cấu hình
        +-- AUTH nếu cấu hình yêu cầu
        +-- Close transport
        |
        v
UP hoặc DOWN
```

Không có:

```text
MAIL FROM
RCPT TO
DATA
Message body
Actual email delivery
```

Trong thực tế, trình tự giao thức cụ thể phụ thuộc transport/SMTP server. Điểm quyết định là `testConnection()` thử kết nối và đóng kết nối, **không gọi `send(...)` để submit một message**.

### Điều kiện để indicator tự động có mặt

Tùy phiên bản Spring Boot và auto-configuration, mail health contributor được đăng ký khi có bean/implementation mail sender phù hợp và health mail được bật. Nếu ứng dụng sử dụng sender tự viết, chỉ triển khai `JavaMailSender` interface, hoặc tắt contributor, mail indicator có thể không xuất hiện tự động.

Vì vậy cần quan sát endpoint thực tế và cấu hình của phiên bản dự án. **Không coi việc có dependency `spring-boot-starter-mail` là bằng chứng chắc chắn mail indicator đang hoạt động.**

### Phân biệt các API

| API | Ý nghĩa |
|---|---|
| `JavaMailSender.send(...)` | Submit email thực sự qua transport; có thể tạo outbound mail. |
| `JavaMailSenderImpl.testConnection()` | Thử kết nối/xác thực tới SMTP server; không gửi message. |
| `MimeMessageHelper` | Xây nội dung MIME; tự nó không phải health check. |
| `HealthIndicator.health()` | Trả trạng thái sức khỏe tại thời điểm kiểm tra. |
| `/actuator/health` | Endpoint tổng hợp nhiều indicator theo cấu hình. |

Một health indicator có thể dùng `testConnection()` mà không có recipient. Nếu code health bắt buộc phải tạo `MimeMessage` và gọi `setTo(...)` để chạy được, đó là dấu hiệu cần xem lại thiết kế.

## 4. Cấu hình Spring Boot cho kết nối SMTP có timeout

Ví dụ khi mail provider dùng STARTTLS trên port 587:

```yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "mail.smtp.auth": true
      "mail.smtp.starttls.enable": true
      "mail.smtp.starttls.required": true
      "mail.smtp.connectiontimeout": 3000
      "mail.smtp.timeout": 3000
      "mail.smtp.writetimeout": 3000

management:
  health:
    mail:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Giá trị timeout tính bằng millisecond và chỉ dùng để minh họa. Cần điều chỉnh theo đường truyền, provider và ngân sách health check.

Các property chính:

| Thuộc tính | Vai trò |
|---|---|
| `spring.mail.host` | SMTP endpoint mà ứng dụng sử dụng. |
| `spring.mail.port` | Port submission tương ứng với provider. |
| `spring.mail.username/password` | Credential từ nguồn secret được quản lý. |
| `mail.smtp.auth` | Bật bước xác thực khi provider yêu cầu. |
| `mail.smtp.starttls.enable` | Cho phép STARTTLS. |
| `mail.smtp.starttls.required` | Không tiếp tục theo cách không bảo vệ nếu STARTTLS bắt buộc. |
| `mail.smtp.connectiontimeout` | Giới hạn chờ thiết lập kết nối. |
| `mail.smtp.timeout` | Giới hạn chờ đọc phản hồi. |
| `mail.smtp.writetimeout` | Giới hạn chờ ghi dữ liệu. |
| `management.health.mail.enabled` | Bật/tắt mail health contributor tự động khi điều kiện cấu hình phù hợp. |

**Không đặt mật khẩu thật trong tài liệu, repository hoặc log.** Dùng secret manager, environment variables hoặc cơ chế quản lý credential của nền tảng.

### Nếu provider dùng implicit TLS

Với endpoint yêu cầu TLS ngay khi kết nối, cấu hình có thể dùng:

```yaml
spring:
  mail:
    host: smtp.example.org
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "mail.smtp.auth": true
      "mail.smtp.ssl.enable": true
      "mail.smtp.connectiontimeout": 3000
      "mail.smtp.timeout": 3000
      "mail.smtp.writetimeout": 3000
```

Port 587/465 là quy ước phổ biến, không phải quy tắc cố định cho mọi provider. Kiểm tra thông số chính thức thay vì đổi port theo phỏng đoán khi indicator báo DOWN.

## 5. Dùng testConnection() trực tiếp khi cần kiểm tra kết nối

Với Spring Framework thuần, hoặc khi muốn kiểm soát chính xác thời điểm kiểm tra, có thể gọi `JavaMailSenderImpl.testConnection()`:

```java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpConnectivityProbe {

    private final JavaMailSenderImpl mailSender;

    public SmtpConnectivityProbe(
            JavaMailSenderImpl mailSender
    ) {
        this.mailSender = mailSender;
    }

    public void verifyConnectivity()
            throws MessagingException {
        mailSender.testConnection();
    }
}
```

Phương thức này không truyền recipient hoặc message, nên không thể dùng chính nó để gửi email nội dung thật. Tuy nhiên, nó vẫn **kết nối mạng và có thể thực hiện AUTH**. Đó là một tác động vận hành cần cân nhắc:

- SMTP provider có thể ghi nhận một lần đăng nhập.
- Mỗi lần kiểm tra có thể tiêu hao một connection slot.
- Credential sai có thể gây nhiều lần AUTH thất bại.
- Provider có thể áp dụng rate limit, cảnh báo bảo mật hoặc khóa tài khoản.
- Nếu DNS/TLS/SMTP chậm, request health endpoint cũng chậm.

Do vậy “không gửi email thật” **không có nghĩa là không có chi phí**. Hãy kiểm soát tần suất và timeout của phép kiểm tra.

## 6. Tự viết HealthIndicator an toàn khi cần hành vi riêng

Nếu ứng dụng có yêu cầu đặc biệt, có thể tạo custom indicator dùng `testConnection()`, tuyệt đối không gọi `send(...)`.

Ví dụ:

```java
import jakarta.mail.MessagingException;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;

@Component("smtpConnectivity")
public class SmtpConnectivityHealthIndicator
        implements HealthIndicator {

    private final JavaMailSenderImpl mailSender;

    public SmtpConnectivityHealthIndicator(
            JavaMailSenderImpl mailSender
    ) {
        this.mailSender = mailSender;
    }

    @Override
    public Health health() {
        try {
            mailSender.testConnection();

            return Health.up()
                    .withDetail("check", "smtp-connect-only")
                    .build();
        } catch (MessagingException exception) {
            return Health.down()
                    .withDetail(
                            "errorType",
                            exception.getClass().getSimpleName()
                    )
                    .build();
        }
    }
}
```

Lớp này chỉ gọi `testConnection()`. Nếu TCP, TLS hoặc AUTH lỗi, indicator trả DOWN. Không chứa địa chỉ recipient và không gửi MIME message.

**Những điểm cần hiểu khi áp dụng:**

- Bean inject bằng kiểu `JavaMailSenderImpl`, không phải interface `JavaMailSender`; cách này chỉ phù hợp nếu triển khai thực tế có bean tương ứng.
- Nếu Spring Boot đã đăng ký mail health indicator tự động, có thể tạo **hai phép kiểm tra giống nhau** và nhân đôi số kết nối. Cân nhắc tắt indicator mặc định khi thay bằng custom.
- Trả raw exception message hoặc stack trace qua health detail có thể tiết lộ hostname, account, policy hoặc cấu hình. Ví dụ chỉ trả `errorType`, nhưng ngay cả detail này cũng nên được bảo vệ.
- `Health.down()` ở đây có nghĩa **connectivity probe thất bại tại thời điểm kiểm tra**, không phải toàn bộ email nghiệp vụ đã gửi thất bại.
- Mỗi lần gọi `health()` có thể kết nối SMTP; nếu cần giới hạn tần suất, hãy áp dụng cache hoặc kiểm tra nền có điều phối.

### Chỉ dùng một nguồn health mail

Nếu chọn custom indicator, có thể tắt contributor mail tự động:

```yaml
management:
  health:
    mail:
      enabled: false
```

Sau đó để custom indicator mang tên riêng như `smtpConnectivity`. Trong trường hợp không cần custom behavior, ưu tiên sử dụng built-in mail indicator để giảm code và tránh thêm logic lỗi.

Không đồng thời bật built-in và custom mà không có mục đích, vì mỗi phép kiểm tra có thể tạo một kết nối riêng trên mỗi lượt health.

## 7. Tuyệt đối không dùng send() như bước kiểm tra sức khỏe định kỳ

Một số cách làm nguy hiểm:

```java
// Không nên trong HealthIndicator:
mailSender.send(new SimpleMailMessage());
```

```java
// Không nên: “gửi cho chính mình” vẫn là email thật.
SimpleMailMessage testMail = new SimpleMailMessage();
testMail.setTo("admin@example.org");
testMail.setSubject("Periodic health check");
testMail.setText("Ping");
mailSender.send(testMail);
```

```java
// Không nên: tạo MimeMessage và gửi mỗi lần readiness probe.
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mime, false, "UTF-8");
helper.setTo("monitoring@example.org");
helper.setSubject("Health");
helper.setText("Healthy");
mailSender.send(mime);
```

Không có lý do để đưa `To`, `Cc` hoặc `Bcc` vào một health indicator chỉ nhằm kiểm tra SMTP connectivity.

### Vì sao email gửi tới mailbox test vẫn nguy hiểm trong health endpoint?

Ngay cả địa chỉ test do tổ chức sở hữu cũng có thể gặp:

- Số lượng thư quá lớn vì probe chạy liên tục.
- Spam/abuse alert hoặc quota ở phía provider.
- Chi phí phát sinh theo số lượng message.
- Nhiễu delivery/bounce metrics.
- Mailbox tăng dung lượng ngoài dự kiến.
- Rủi ro người vận hành thay nhầm địa chỉ trong cấu hình.

Nếu cần kiểm thử gửi thật, phải chuyển thành **synthetic monitoring có chủ đích**, được quản lý về tần suất, người nhận và quyền. Không dùng health endpoint vốn có thể được gọi bất kỳ lúc nào.

## 8. Chặn accidental sending ở kiến trúc

Chỉ dựa vào code review “đừng gọi send trong health” không đủ nếu ứng dụng lớn và nhiều người cùng sửa.

Có thể đặt quy tắc:

1. `HealthIndicator` chỉ phụ thuộc một interface `MailConnectivityProbe`, không nhận `JavaMailSender` nếu không cần.
2. `MailConnectivityProbe` chỉ có phương thức `checkConnectivity()` và không chứa API gửi thư.
3. Business mail sender nằm ở lớp khác, không được inject vào health module.
4. Trong unit test, mock sender và xác nhận `send(...)` không được gọi.
5. Khi deploy, route health qua endpoint/health group được kiểm soát.
6. Nếu cần synthetic send, tổ chức workflow khác hoàn toàn với health probe.

Một interface rất hẹp:

```java
public interface MailConnectivityProbe {
    void check() throws Exception;
}
```

Implementation:

```java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class JavaMailConnectivityProbe
        implements MailConnectivityProbe {

    private final JavaMailSenderImpl mailSender;

    public JavaMailConnectivityProbe(JavaMailSenderImpl mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void check() throws MessagingException {
        mailSender.testConnection();
    }
}
```

Health layer:

```java
public final class MailConnectionHealthIndicator
        implements HealthIndicator {

    private final MailConnectivityProbe probe;

    public MailConnectionHealthIndicator(
            MailConnectivityProbe probe
    ) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        try {
            probe.check();
            return Health.up().build();
        } catch (Exception exception) {
            return Health.down().build();
        }
    }
}
```

Thiết kế này làm rõ health chỉ có quyền “probe”; nếu ai đó muốn gửi mail thật, họ không thể gọi `send` qua interface `MailConnectivityProbe` mà phải thay đổi dependency có chủ đích.

## 9. Liveness và readiness không giống nhau

Trong môi trường container, có hai câu hỏi vận hành khác nhau:

- **Liveness:** tiến trình ứng dụng còn sống và có khả năng tiến triển hay không?
- **Readiness:** instance này có nên nhận traffic/công việc mới không?

SMTP là **dịch vụ bên ngoài**. Nếu SMTP tạm thời mất kết nối nhưng ứng dụng vẫn khỏe, liên tục restart Pod thường không sửa được SMTP.

### Vì sao không dùng SMTP làm liveness?

Giả sử nhà cung cấp SMTP gặp sự cố trong 10 phút:

```text
SMTP outage
    |
    v
Mail health DOWN
    |
    v
Liveness DOWN (nếu gộp sai)
    |
    v
Kubernetes restarts application
    |
    v
SMTP vẫn DOWN
    |
    v
Repeat restart loop
```

Việc restart có thể làm mất task `@Async` trong RAM, gián đoạn HTTP request và tăng áp lực lên database, mà không giải quyết nguyên nhân SMTP bên ngoài.

**Không nên đưa một dependency SMTP không bắt buộc vào liveness probe.** Liveness nên phản ánh khả năng tiến triển nội bộ của process.

### Khi nào SMTP ảnh hưởng readiness?

Điều này phụ thuộc thiết kế:

| Kiến trúc | SMTP DOWN có làm readiness DOWN? | Lý do |
|---|---|---|
| API chỉ có nhiệm vụ submit mail đồng bộ và không thể phục vụ khi SMTP down | Có thể, theo SLO và failover policy | Không nên nhận request nếu mọi request chắc chắn không hoàn thành. |
| API đặt đơn hàng, ghi mail outbox rồi gửi nền | Thường không | Tạo đơn vẫn có thể hoạt động; outbox lưu yêu cầu để gửi lại. |
| Worker chuyên gửi mail có queue bền vững | Có thể phản ánh bằng health riêng | Cần quyết định có pause nhận job khi provider lỗi hay không. |
| Ứng dụng có chức năng mail phụ trợ | Thường không | Tránh làm toàn bộ sản phẩm không nhận traffic chỉ vì email lỗi. |

Không có một đáp án chung cho mọi hệ thống. Quan trọng là **không để một dependency optional tự động làm fail toàn bộ readiness** mà không xét kiến trúc.

## 10. Tổ chức health groups cho Kubernetes

Spring Boot Actuator có thể cung cấp health probes riêng cho liveness/readiness theo cấu hình phù hợp.

Một cấu hình cơ bản:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health
```

Các endpoint thường được sử dụng theo mô hình Actuator health groups, ví dụ:

```text
/actuator/health/liveness
/actuator/health/readiness
/actuator/health
```

Nếu muốn readiness không phụ thuộc SMTP, có thể giữ chỉ báo readiness của chính ứng dụng và các dependency thực sự bắt buộc. Ví dụ cấu hình minh họa:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState
```

Khi cần thêm thành phần như database hoặc broker, việc đưa chúng vào readiness phải dựa trên yêu cầu nhận traffic thực tế và tên indicator đang được đăng ký. Không giả định mọi indicator tự động nằm trong liveness/readiness group; hãy kiểm tra cấu hình và kết quả endpoint ở version Spring Boot sử dụng.

### Một nhóm riêng cho SMTP

Nếu cần endpoint kiểm tra mail thủ công, có thể cấu hình một health group riêng, ví dụ:

```yaml
management:
  endpoint:
    health:
      group:
        smtp:
          include: smtpConnectivity
```

Ví dụ này giả định có custom indicator với ID `smtpConnectivity`. Khi đó nhóm SMTP có thể được truy vấn độc lập mà không buộc liveness hoặc readiness phụ thuộc vào SMTP.

Cần xác nhận Spring Boot version, tên contributor và quyền expose group tương ứng. Health group nên được bảo vệ khỏi các truy vấn công khai gây quá tải login SMTP.

## 11. Startup test-connection khác với health probe định kỳ

Spring Boot có tùy chọn kiểm tra kết nối mail khi khởi động ứng dụng:

```yaml
spring:
  mail:
    test-connection: true
```

Tùy phiên bản và auto-configuration, cấu hình này thực hiện kiểm tra kết nối trong giai đoạn startup và có thể khiến startup thất bại khi SMTP không khả dụng.

**Đây không phải lệnh gửi email thật**, nhưng có thể làm ứng dụng không khởi động khi provider tạm thời gặp sự cố.

| Cơ chế | Thời điểm | Gửi thư thật? | Tác động nếu SMTP DOWN |
|---|---|---|---|
| `spring.mail.test-connection` | Khi startup theo cấu hình | Không | Có thể fail startup. |
| Mail HealthIndicator | Khi endpoint/group được truy vấn | Không, nếu dùng connectivity probe chuẩn | Có thể trả DOWN. |
| Custom send test bằng `JavaMailSender.send` | Bất cứ khi nào code gọi | Có | Gửi thư thật hoặc ném lỗi. |
| Scheduled synthetic E2E | Theo lịch có kiểm soát | Có | Ghi kết quả test riêng, không nhất thiết ảnh hưởng readiness. |

Khi email chỉ là tác vụ phụ và có outbox bền vững, nên cân nhắc **không fail toàn bộ startup** chỉ vì SMTP không khả dụng. Worker có thể đợi provider phục hồi; điều quan trọng là yêu cầu gửi không bị mất.

Khi ứng dụng chỉ phục vụ SMTP submission trực tiếp và không có chế độ hoạt động giảm cấp, fail-fast có thể là lựa chọn được cân nhắc. Đây là quyết định theo SLO, không phải mặc định áp dụng mọi hệ thống.

## 12. Health check nên có timeout và ngân sách thời gian

Một health endpoint có thể bị chậm do DNS, TCP, TLS, AUTH hoặc provider trả lời chậm. Nếu không có timeout, mỗi probe có thể giữ một web thread trong thời gian dài.

Cấu hình các timeout phù hợp:

```yaml
spring:
  mail:
    properties:
      "mail.smtp.connectiontimeout": 3000
      "mail.smtp.timeout": 3000
      "mail.smtp.writetimeout": 3000
```

Không nên hiểu rằng ba giá trị `3000 ms` tạo thành một deadline tổng `3 giây` cho mọi trường hợp. Một kết nối có thể trải qua nhiều thao tác I/O; deadline thực có thể dài hơn một timeout đơn lẻ.

Nên tính ngân sách:

```text
Probe interval
Probe timeout
Mail connect/auth timeout
Health cache TTL
Failure threshold
Kubernetes liveness/readiness threshold
```

Ví dụ, nếu kubelet chờ response 1 giây nhưng SMTP thường mất 3 giây để handshake, việc dùng SMTP probe trực tiếp làm readiness sẽ tạo false failure dù provider bình thường theo SLA mail.

### Không để health check tạo áp lực khi hệ thống đã lỗi

Khi SMTP chậm, số health requests đồng thời tăng có thể tạo nhiều kết nối cùng lúc. Một health indicator dùng network cần có cơ chế bảo vệ:

- Timeout rõ.
- Tần suất hữu hạn.
- Có thể cache trạng thái trong khoảng ngắn.
- Giới hạn số phép kiểm tra đồng thời nếu custom.
- Không retry dồn dập bên trong từng lần health call.
- Không log stack trace lặp lại vô hạn.

## 13. Giảm tần suất kiểm tra bằng cache hoặc background probe

`testConnection()` không gửi thư, nhưng mỗi lần gọi vẫn có thể AUTH. Khi ứng dụng có nhiều replica và nhiều monitoring client, chi phí này đáng kể.

Có hai hướng:

### 13.1. Cache health response có thời hạn

Spring Boot Actuator hỗ trợ cấu hình cache cho một số endpoint; ví dụ:

```yaml
management:
  endpoint:
    health:
      cache:
        time-to-live: 20s
```

Thời gian `20s` chỉ minh họa. Cấu hình và hành vi cache cụ thể cần được đối chiếu với phiên bản Spring Boot và health group đang sử dụng.

**Đánh đổi:** cache làm giảm số lần kết nối SMTP nhưng health response có thể phản ánh kết quả của vài giây trước. Cần chọn TTL phù hợp mục tiêu quan sát.

### 13.2. Probe nền và trả last-known status

Một worker được lập lịch có thể chạy `testConnection()` theo tần suất có giới hạn, lưu:

```text
lastProbeTime
lastProbeStatus
lastProbeDuration
lastErrorCategory
```

Health endpoint chỉ đọc snapshot, không tạo kết nối mới trên mỗi request.

Nếu dùng cách này, cần thêm **độ mới của kết quả**. Một kết quả UP từ 2 giờ trước không có giá trị bằng kết quả UP cách đây 20 giây.

Ví dụ trạng thái:

```text
lastProbeStatus = UP
lastProbeAgeSeconds = 18
status = UP

lastProbeStatus = UP
lastProbeAgeSeconds = 7200
status = UNKNOWN or DOWN by explicit policy
```

Không nên tự động để kết quả cũ mãi ở UP khi scheduler đã chết. Đồng thời tránh làm scheduler gửi email thật: probe nền cũng phải chỉ kết nối/xác thực, không submit message.

## 14. Custom snapshot HealthIndicator không cần kết nối mỗi request

Một thiết kế có thể tách việc chủ động kiểm tra và việc trả trạng thái.

Ví dụ model snapshot:

```java
import java.time.Instant;

public record SmtpHealthSnapshot(
        boolean reachable,
        Instant checkedAt,
        String errorCategory
) {
}
```

Probe scheduler cập nhật snapshot sau mỗi `testConnection()`; Actuator health chỉ đọc dữ liệu đó.

Ý tưởng:

```java
public Health health() {
    SmtpHealthSnapshot snapshot = probeState.current();

    if (snapshot == null) {
        return Health.unknown()
                .withDetail("reason", "not_checked_yet")
                .build();
    }

    if (snapshot.checkedAt().isBefore(
            clock.instant().minus(maxSnapshotAge))) {
        return Health.unknown()
                .withDetail("reason", "probe_stale")
                .build();
    }

    return snapshot.reachable()
            ? Health.up().build()
            : Health.down()
                    .withDetail(
                            "errorCategory",
                            snapshot.errorCategory()
                    )
                    .build();
}
```

`probeState`, `clock` và `maxSnapshotAge` là các dependency của ứng dụng, không phải biến toàn cục có sẵn. Cách này minh họa lý do nên dùng snapshot: **không có `send` và không có connect SMTP trong `health()`**.

Nếu status `UNKNOWN` xuất hiện, phản hồi tổng hợp và HTTP status phụ thuộc cấu hình health status mapping; cần kiểm thử để tránh sai chính sách readiness.

## 15. Phân loại lỗi health: kết nối, TLS, AUTH và provider outage

Khi `testConnection()` lỗi, không phải nguyên nhân nào cũng giống nhau.

| Lỗi hoặc hiện tượng | Nhóm nghi vấn | Điều cần làm |
|---|---|---|
| DNS lookup thất bại | DNS/network | Kiểm tra resolver, hostname và mạng của Pod. |
| TCP connection refused | Endpoint/port/firewall | Xác nhận provider host/port và egress rule. |
| Connection/read timeout | Network/provider chậm | Kiểm tra timeout, saturation và outage. |
| TLS handshake failure | TLS mode/chứng chỉ | Kiểm tra STARTTLS vs implicit TLS, trust và protocol. |
| Authentication failed/535 | Credential/policy AUTH | Kiểm tra secret, app password, OAuth2, tài khoản. |
| Rate limit do nhiều lần AUTH | Probe quá dày/provider policy | Giảm tần suất, cache, sửa cấu hình. |
| Kết nối được nhưng gửi nghiệp vụ lỗi | Không nằm trong phạm vi connectivity probe | Kiểm tra From, recipient, message size và policy gửi. |

Health indicator thường chỉ trả UP/DOWN hoặc UNKNOWN. Chi tiết phân loại nên đi vào log và metric nội bộ với danh mục lỗi hữu hạn; không trả raw SMTP exception trong response public.

### Một SMTP error không phải lúc nào cũng là MailAuthenticationException

`testConnection()` có thể ném `MessagingException` hoặc các cause khác nhau. Đừng mặc định mọi lỗi health đều do password sai. Kiểm tra chuỗi cause, thời điểm lỗi, transport mode và policy provider.

Ngược lại, đăng nhập thành công không chứng minh tài khoản có quyền gửi bằng một địa chỉ `From` bất kỳ, vì authorization của sender có thể được áp dụng ở giai đoạn `MAIL FROM` hoặc khi truyền message.

## 16. Cấu hình bảo mật endpoint health

Actuator endpoint phục vụ vận hành, không nên vô tình trở thành nguồn tiết lộ hạ tầng.

Ví dụ cấu hình chỉ hiển thị trạng thái cơ bản:

```yaml
management:
  endpoint:
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
```

Trong môi trường cần xem chi tiết, có thể cho phép người quản trị đã xác thực xem theo policy Spring Security. Không đưa username/password, access token, hostname nội bộ nhạy cảm hoặc raw exception message vào `Health.withDetail(...)`.

### Không cho client tự chọn recipient hoặc SMTP host để “kiểm tra”

Một endpoint dạng:

```text
GET /actuator/health/mail?recipient=...
GET /actuator/health/mail?host=...
```

là dấu hiệu nguy hiểm nếu handler thật sự sử dụng query string để gửi mail hoặc kết nối tới host tùy ý. Nó có thể gây gửi email ngoài ý muốn hoặc SSRF/scanning hạ tầng.

Health endpoint cần kiểm tra **cấu hình đã được triển khai và phê duyệt**, không trở thành API gửi mail hoặc công cụ quét network cho người không tin cậy.

Nếu cần trang quản trị “gửi email thử”, hãy đặt ở endpoint riêng có authentication, authorization, rate limit và audit; không gộp vào Actuator health.

## 17. Thiết kế synthetic end-to-end test an toàn khi thực sự cần

Có trường hợp phải kiểm tra khả năng **gửi và nhận email thật**, chẳng hạn xác minh đường gửi mới trước khi triển khai hoặc kiểm tra deliverability định kỳ có kiểm soát. Khi đó cần một hệ thống synthetic monitoring riêng.

```text
Authorized scheduled job
         |
         v
Select approved test mailbox
         |
         v
Create synthetic notification
         |
         v
Submit via production mail route
         |
         v
Record provider/message ID
         |
         v
Observe controlled test mailbox or provider event
         |
         v
Report synthetic outcome
```

Các điều kiện bắt buộc:

1. **Chỉ gửi đến allowlist mailbox test** do tổ chức quản lý.
2. Có **tần suất và quota cố định**, không phụ thuộc số lần health endpoint bị truy vấn.
3. Subject/body rõ ràng là synthetic, không chứa PII hoặc dữ liệu production.
4. Sử dụng mã synthetic riêng để không lẫn vào số liệu marketing/transactional.
5. Có timeout, retry hữu hạn và chặn gửi trùng.
6. Có audit người/tiến trình kích hoạt.
7. Không dùng user-supplied recipient hoặc URL tùy ý.
8. Có cơ chế dừng test khi provider lỗi hoặc quota gần hết.
9. Nếu cần kiểm tra inbox thật, dùng hộp thư test được giám sát và tiêu chí kiểm tra cụ thể.
10. Không đưa kết quả synthetic trực tiếp vào liveness chỉ vì một lần delivery chậm.

Synthetic test thật có thể xác minh một đường gửi cụ thể; nó vẫn không bảo đảm mọi email nghiệp vụ đi tới inbox của mọi recipient.

### Tách metric của synthetic khỏi mail nghiệp vụ

Nếu hệ thống thực sự gửi email kiểm thử:

```text
mail.synthetic.attempt
mail.synthetic.smtp.accepted
mail.synthetic.delivery.confirmed
mail.synthetic.failure
```

hoặc dùng một `type=synthetic` thuộc danh mục có giới hạn. Không trộn synthetic vào KPI “email giao dịch đã gửi” nếu nghiệp vụ cần số liệu chính xác.

## 18. Kiểm thử bằng Mockito: health() không bao giờ gọi send()

Unit test là một lớp phòng vệ quan trọng khi sửa health indicator.

Ví dụ dùng Mockito, JUnit 5 và AssertJ với custom indicator ở trên:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;
import org.springframework.mail.javamail.JavaMailSenderImpl;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class SmtpConnectivityHealthIndicatorTest {

    @Test
    void healthyProbeOnlyCallsTestConnection()
            throws Exception {

        JavaMailSenderImpl sender =
                mock(JavaMailSenderImpl.class);

        SmtpConnectivityHealthIndicator indicator =
                new SmtpConnectivityHealthIndicator(sender);

        Health health = indicator.health();

        assertThat(health.getStatus())
                .isEqualTo(Status.UP);

        verify(sender).testConnection();

        // Không có bất kỳ tương tác khác, bao gồm mọi overload send().
        verifyNoMoreInteractions(sender);
    }
}
```

Kiểm thử này xác nhận chính xác rằng indicator chỉ tương tác với `testConnection()` và không dùng `JavaMailSender.send(...)`.

### Test khi AUTH thất bại cũng không gửi

```java
import jakarta.mail.AuthenticationFailedException;

@Test
void authenticationFailureReturnsDownWithoutSending()
        throws Exception {

    JavaMailSenderImpl sender =
            mock(JavaMailSenderImpl.class);

    doThrow(new AuthenticationFailedException(
            "Synthetic authentication failure"
    )).when(sender).testConnection();

    SmtpConnectivityHealthIndicator indicator =
            new SmtpConnectivityHealthIndicator(sender);

    Health health = indicator.health();

    assertThat(health.getStatus())
            .isEqualTo(Status.DOWN);

    verify(sender).testConnection();
    verifyNoMoreInteractions(sender);
}
```

Test này cũng có một điều quan trọng: health check phải **trả DOWN đúng ngữ nghĩa** khi connectivity không thành công, thay vì gửi một email khác để “thử lại”.

### Với custom probe interface

Nếu health indicator dùng `MailConnectivityProbe`, có thể fake implementation để kiểm tra:

- Success → UP.
- Failure → DOWN.
- Timeout/stale snapshot → UNKNOWN hoặc DOWN theo contract.
- Mọi nhánh đều không có dependency vào mail sender gửi thật.

Điều này giúp phát hiện thay đổi ngoài ý muốn trước khi code được deploy.

## 19. Integration test với SMTP test server nhưng không gửi thư

Một SMTP server test như GreenMail có thể hỗ trợ kết nối và xác thực mà không phải sử dụng provider production.

Kịch bản:

1. Khởi động SMTP server test ở port ngẫu nhiên/đã được test quản lý.
2. Cấu hình `JavaMailSenderImpl` trỏ tới server test.
3. Gọi `testConnection()` hoặc endpoint health chứa indicator.
4. Xác nhận health UP.
5. Xác nhận **số message mà server test nhận được bằng 0**.
6. Tắt server hoặc dùng sai credential test.
7. Gọi health lần nữa, xác nhận DOWN.
8. Xác nhận vẫn không có email được tạo/gửi.

Ý tưởng test:

```java
@Test
void connectivityCheckDoesNotSubmitMail()
        throws Exception {

    // SMTP server test đã được tạo và khởi động trong fixture.
    JavaMailSenderImpl sender = testMailSender();

    sender.testConnection();

    assertThat(
            testSmtpServer.receivedMessageCount()
    ).isZero();
}
```

`testMailSender()` và `testSmtpServer` là helper/fixture minh họa; API kiểm đếm phụ thuộc test server mà ứng dụng lựa chọn.

### Cần test cả số lần kết nối nếu có yêu cầu tải

Một server test có thể ghi nhận số session. Khi kiểm tra health nhiều lần, xác nhận:

- Không có message nào được nhận.
- Số connect/AUTH phù hợp cơ chế cache/tần suất.
- Connection được đóng.
- Khi server chậm, health không giữ thread vô hạn.

Đây là phần kiểm thử chi phí của health probe, **khác** với việc xác nhận không gửi email thật.

## 20. Kiểm thử Actuator endpoint

Khi ứng dụng dùng Spring Boot, một component/integration test có thể gọi endpoint qua `MockMvc` hoặc test client để xác nhận health response.

Ví dụ ý tưởng:

```java
mockMvc.perform(get("/actuator/health"))
        .andExpect(status().isOk());
```

Một số điều cần xem xét:

- Endpoint có thể trả HTTP 503 khi health tổng hợp DOWN.
- Nếu security được bật, cần test quyền truy cập.
- Health group có thể không chứa mail indicator theo cấu hình.
- Nếu health bị cache, một lần gọi có thể không kích hoạt probe mới.
- `MockMvc` không tự chứng minh không có SMTP send; cần mock/spy sender hoặc test SMTP server nhận 0 message.

Do vậy, một bộ test tốt kết hợp **endpoint response assertions** với **zero-send assertion**.

### Trường hợp phải chặn mọi gửi thật trong test

Nếu test context có scheduler hoặc event listener khác có thể gọi `JavaMailSender.send`, hãy thay sender bằng mock/fake, hoặc cho toàn bộ cấu hình trỏ tới SMTP test server. Không bao giờ để unit/integration test health vô tình dùng credential và SMTP host production.

## 21. Kiểm tra health theo nhiều SMTP route

Một hệ thống có thể có:

- SMTP primary và backup.
- Provider transactional và provider marketing.
- SMTP riêng theo tenant hoặc khu vực.
- API mail provider và SMTP relay chạy song song.

Một indicator duy nhất dùng bean sender mặc định có thể **không đại diện** cho toàn bộ các đường gửi.

Ví dụ:

```text
MailService
    |
    +-- transactional-primary -> SMTP A
    |
    +-- transactional-backup  -> SMTP B
    |
    +-- marketing-route       -> Provider C
```

Khi health SMTP A DOWN nhưng B vẫn dùng được, hệ thống có thể tiếp tục gửi qua failover theo policy. Ngược lại, kiểm tra A thành công không chứng minh B và C đều sẵn sàng.

Các lựa chọn:

1. Health check riêng cho từng route hữu hạn.
2. Health tổng hợp theo contract “có ít nhất một route đủ điều kiện cho loại mail này”.
3. Dashboard/metrics per-route, giữ health endpoint đơn giản.
4. Không probe hàng nghìn route hoặc credential theo tenant trên mỗi request health.

**Không đưa tenant ID tự do vào tên health contributor hoặc metric tag**, vì sẽ tạo tải và cardinality lớn. Với hệ thống rất nhiều route, dùng scheduled probe có giới hạn hoặc sampling có mục đích, cộng dữ liệu trạng thái worker và provider.

## 22. Health của mail pipeline khác health của SMTP

Một health check kết nối SMTP thành công có thể trả UP, trong khi mail vẫn không được xử lý do:

- Worker không chạy.
- Outbox queue tồn đọng.
- Lease bị kẹt.
- Task executor đầy.
- Template renderer lỗi.
- Notification bị chặn do chính sách.
- Rate limit khiến worker chủ động pause.

Vì vậy cần kết hợp **connectivity health** với **metric pipeline**:

| Tín hiệu | Câu hỏi |
|---|---|
| `mail.smtp.connectivity` | Có thể kết nối/xác thực tới mail route không? |
| `mail.outbox.pending` | Hiện có bao nhiêu notification chờ xử lý? |
| `mail.outbox.oldest.age` | Job lâu nhất đã chờ bao lâu? |
| `mail.send.attempt` | Worker có đang thử gửi hay không? |
| `mail.send.failure` | Lỗi SMTP có tăng không? |
| `mail.send.unknown` | Có nhiều attempt không rõ kết quả không? |
| `mail.worker.inflight` | Có bao nhiêu job đang xử lý? |
| `mail.provider.bounced` | Provider có báo nhiều bounce không? |

Tên ở bảng là ví dụ đặt metric, không phải meter do Spring Mail tự xuất ra theo mặc định.

**Health UP không đồng nghĩa mail pipeline đang đạt SLO.** Các metric và alert cần bổ sung để phát hiện nghẽn queue, lỗi hàng loạt và delivery chậm.

## 23. Tránh health indicator làm thay đổi trạng thái nghiệp vụ

Ngoài không gửi mail, health indicator cũng nên tránh các side effect không cần thiết:

- Không tạo row outbox.
- Không tăng retry count của job nghiệp vụ.
- Không đánh dấu một notification đã gửi.
- Không dequeue hoặc ACK message từ broker.
- Không chạy thử các template chứa dữ liệu thật.
- Không sửa quyền hoặc rotate secret.
- Không tạo email attachment/đọc file nhạy cảm.
- Không thay đổi default mail route chỉ để “tự sửa”.
- Không gọi provider webhook handler để giả trạng thái delivered.

Một health indicator có thể **ghi metric kỹ thuật của lần probe** và log trạng thái an toàn; điều đó khác với tác động tới dữ liệu nghiệp vụ.

Nếu cần kiểm tra database/outbox, ưu tiên đọc trạng thái có chi phí giới hạn hoặc snapshot đã được một worker tổng hợp. Không dùng health endpoint để tự động xử lý lại job đang lỗi.

## 24. Bảo vệ khỏi sự cố do probe quá thường xuyên

Ngay cả `testConnection()` không gửi mail thật, cấu hình probe sai vẫn có thể gây sự cố.

### Tình huống: mật khẩu SMTP sai

Nếu mỗi instance gọi AUTH bằng mật khẩu sai quá nhiều lần:

1. Provider ghi nhận nhiều login failure.
2. Hệ thống cảnh báo brute-force hoặc khóa account.
3. Worker gửi email thật cũng không thể xác thực.
4. Health probe tiếp tục làm vấn đề nghiêm trọng hơn.

Hướng xử lý:

- Có interval/caching hợp lý.
- Không retry tức thì nhiều lần trong một health call.
- Khi lỗi AUTH kéo dài, cảnh báo và giảm tần suất probe theo chính sách.
- Sửa secret hoặc auth mechanism trước khi resume.
- Phân biệt lỗi cấu hình vĩnh viễn với timeout tạm thời.

### Tình huống: SMTP server chậm

Nhiều health request cùng chờ SMTP làm cạn web thread, khiến ứng dụng không phản hồi các request khác.

Hướng xử lý:

- Timeout.
- Cache hoặc background probe.
- Giới hạn concurrency.
- Không đặt dependency SMTP external vào liveness.
- Kết hợp alerts trên metric thay vì liên tục ping bằng connection mới.

### Tình huống: endpoint bị truy vấn công khai

Một attacker có thể gửi hàng nghìn request tới health endpoint, làm ứng dụng tạo hàng nghìn kết nối SMTP dù không có email thật. Health endpoint cần được network/security bảo vệ, không chỉ dựa vào “không có thông tin nhạy cảm”.

## 25. Runbook khi health báo DOWN

### Bước 1 — Xác minh indicator nào DOWN

Xem trạng thái tổng và các health group theo quyền truy cập được cấp. Kiểm tra đó là mail connectivity, database, queue hay liveness state.

Không thấy `mail` trong response không có nghĩa SMTP khỏe; có thể indicator bị tắt hoặc chưa được auto-configure.

### Bước 2 — Kiểm tra không có email test thật bị phát sinh

Xác nhận health implementation dùng `testConnection()` hoặc một probe không gửi mail. Nếu phát hiện `send(...)` trong health, cần ngăn việc gọi lặp ngay và chuyển sang thiết kế không gửi.

### Bước 3 — Xác nhận host, port và TLS mode

Dùng cấu hình chính thức của provider. Kiểm tra DNS, network egress, firewall, chứng chỉ và STARTTLS/implicit TLS.

### Bước 4 — Kiểm tra xác thực một cách an toàn

Xem secret có được inject vào runtime không, username format có đúng không, account có bị khóa hay SMTP AUTH bị tắt không. Không in password/token vào log hoặc chạy thử credential liên tục.

### Bước 5 — Xem timeout và tần suất health

Đối chiếu probe interval, cache TTL, SMTP timeout và số replica. Nếu provider bị outage, giảm số kết nối kiểm tra không cần thiết.

### Bước 6 — Kiểm tra nghiệp vụ còn tiếp tục được không

Nếu app có outbox bền vững, nó có thể tiếp tục ghi nhận email trong khi SMTP unavailable. Kiểm tra backlog, worker state và SLA; không restart tất cả Pod chỉ vì mail health DOWN.

### Bước 7 — Khôi phục có kiểm soát

Sau khi sửa SMTP, thực hiện một lần connectivity check an toàn. Sau đó quan sát worker retry backlog theo rate limit. Không tự động phát email synthetic hàng loạt để xác nhận sức khỏe.

## 26. Các lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Hộp thư vận hành nhận nhiều email “Health check” | Indicator gọi `JavaMailSender.send` | Thay bằng `testConnection()`; synthetic test riêng. |
| Health DOWN nhưng email vẫn gửi qua backup | Indicator chỉ kiểm tra primary | Định nghĩa health theo route/failover policy. |
| Health UP nhưng người dùng chưa nhận thư | Probe chỉ kiểm tra connect/auth | Theo dõi submission, provider events, spam/bounce. |
| Endpoint health trả quá chậm | SMTP handshake/TLS/AUTH chậm | Timeout, cache, background probe. |
| SMTP account bị khóa sau deploy | Health liên tục thử sai credential | Giảm frequency, sửa secret, phân loại auth error. |
| Liveness fail khi SMTP bị outage | External mail dependency bị gộp vào liveness | Loại SMTP khỏi liveness, thiết kế readiness đúng. |
| Readiness DOWN làm mất traffic dù outbox vẫn hoạt động | Readiness phụ thuộc mail optional | Định nghĩa group theo khả năng phục vụ thực tế. |
| Chỉ có custom health, không thấy mail built-in | Custom sender/auto-config khác kỳ vọng | Kiểm tra bean, contributor ID, property. |
| Health bị kiểm tra hai lần | Built-in và custom cùng bật | Chỉ giữ indicator cần thiết. |
| Không thấy metric/health sau khởi động | Registry/lazy registration hoặc indicator disabled | Kiểm tra endpoint và điều kiện auto-configuration. |
| Unit test gửi email production | Test context dùng credential thật và gọi send | Mock sender hoặc SMTP test server, assert zero messages. |
| Health 200 OK nhưng worker ngừng | Chỉ kiểm tra SMTP connectivity | Theo dõi queue lag, outbox và worker metrics. |
| Health response lộ địa chỉ tài khoản | Đưa exception/detail không được lọc | Che dữ liệu, hạn chế show-details. |
| Probe background luôn UP dù đã dừng chạy | Snapshot cũ không có age check | Thêm stale threshold và metric probe age. |
| Mail synthetic làm sai dashboard | Gộp mail test với transactional | Tách type/metrics và hạn chế tần suất. |

## 27. Ma trận kiểm thử cần có

Một bộ test cho mail health indicator nên bao gồm:

| Case | Kết quả health | Số email thật |
|---|---|---:|
| `testConnection()` thành công | UP | 0 |
| AUTH bị từ chối | DOWN | 0 |
| SMTP host không reachable | DOWN | 0 |
| TLS handshake thất bại | DOWN | 0 |
| Mail sender chưa được cấu hình | Không có indicator hoặc trạng thái theo contract | 0 |
| 100 lần gọi health liên tiếp | Theo state/probe cache | 0 |
| Hai replica cùng bị scrape | Theo trạng thái của từng replica | 0 |
| Health cache hit | Không cần gọi network mới | 0 |
| Background probe stale | UNKNOWN/DOWN theo policy | 0 |
| Liveness khi SMTP provider down | Không tự bị fail vì SMTP optional | 0 |
| Readiness khi outbox vẫn nhận việc | Theo contract ứng dụng | 0 |
| Synthetic E2E job riêng chạy theo lịch | Trạng thái job riêng | Chỉ số thư đã được phê duyệt, có giới hạn |

Các assert kỹ thuật quan trọng:

- `verify(sender).testConnection()` khi indicator được thiết kế gọi connect một lần.
- `verifyNoMoreInteractions(sender)` để bảo đảm không có overload `send`.
- SMTP test server nhận **0 message** sau health check.
- Không có outbox record được tạo bởi health endpoint.
- Không có recipient, subject hoặc body cần thiết để health hoạt động.
- Các nhánh error không fallback sang gửi mail thật.
- Health group và HTTP status được xác nhận bằng component test.
- Probe không ghi secret hoặc raw SMTP debug vào response.

Không nên chạy test với SMTP production hoặc credential thật; điều đó vừa tăng rủi ro vừa làm test không ổn định.

## 28. Checklist trước khi triển khai production

1. **Mục tiêu health được định nghĩa rõ:** cấu hình, connectivity hay pipeline state.
2. **Không gọi `JavaMailSender.send(...)` trong health indicator** hoặc request handler của endpoint health.
3. Sử dụng built-in mail indicator phù hợp hoặc custom `testConnection()`, không bật cả hai không cần thiết.
4. Không đưa recipient/subject/body vào health probe.
5. SMTP host, port, TLS và timeout khớp cấu hình provider.
6. Tần suất connect/AUTH có giới hạn; có cache hoặc background probe nếu cần.
7. External SMTP không bị đưa vào liveness chỉ vì tiện cấu hình.
8. Readiness phụ thuộc SMTP **chỉ khi điều đó đúng với khả năng phục vụ của ứng dụng**.
9. Health detail không chứa credential, token, raw exception hoặc thông tin nhạy cảm.
10. Health endpoint được bảo vệ về network và quyền truy cập.
11. Có unit test chứng minh mọi nhánh health không gọi `send`.
12. Có integration test với SMTP test server xác nhận zero received messages.
13. Monitoring kết hợp health với queue lag, attempts, errors và provider events.
14. Synthetic send được tách thành job riêng, allowlist recipient, quota, lịch chạy và audit.
15. Có runbook xử lý mail health DOWN mà không gây restart loop hoặc retry storm.
16. Nếu mail là optional dependency, ứng dụng có cơ chế degraded mode/outbox để tiếp tục nghiệp vụ.

## 29. Ghi nhớ

- **Health indicator không phải một API gửi email.** Gọi `JavaMailSender.send(...)` trong health endpoint có thể gửi thư thật mỗi khi monitoring truy vấn.
- `JavaMailSenderImpl.testConnection()` kiểm tra kết nối/xác thực và đóng transport; nó không gửi nội dung MIME tới người nhận.
- Built-in mail health của Spring Boot có thể sử dụng cơ chế connect-only khi auto-configuration phù hợp; cần kiểm tra phiên bản và bean thực tế.
- Kết nối/auth thành công chỉ chứng minh một phần sức khỏe SMTP, **không chứng minh delivery/inbox/read**.
- Dù không gửi thư, mỗi phép connect/AUTH vẫn có chi phí và nguy cơ rate limit/account lock nếu cấu hình sai.
- Cần SMTP timeout, health timeout budget, cache hoặc background probe khi tần suất kiểm tra cao.
- SMTP external dependency không nên mặc định nằm trong **liveness**; dùng readiness theo vai trò thật của ứng dụng và khả năng outbox.
- Nếu custom indicator, giới hạn dependency bằng `MailConnectivityProbe` để giảm nguy cơ gọi nhầm send.
- Test phải xác nhận **zero send calls** và **zero received messages**, cả khi probe thành công lẫn thất bại.
- Nếu cần kiểm thử email đầu-cuối thật, tạo synthetic monitoring riêng với mailbox test, giới hạn tần suất và audit.
- Kết hợp health với metric queue, worker và provider events để có hình ảnh vận hành đầy đủ.

**Kết luận:** Cách kiểm tra health của Spring Framework Mail an toàn là đo **khả năng kết nối hoặc trạng thái pipeline mà không tạo email thật**. Dùng `testConnection()` khi cần kiểm tra SMTP, giữ health endpoint không có tác động gửi thư, kiểm soát tần suất và tách liveness/readiness phù hợp. Khi muốn xác minh end-to-end delivery, triển khai một synthetic test được phê duyệt riêng — không biến mọi lần probe thành một lần gửi email ngoài ý muốn.
