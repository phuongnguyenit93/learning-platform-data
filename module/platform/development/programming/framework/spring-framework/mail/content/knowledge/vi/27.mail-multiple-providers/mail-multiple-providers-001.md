# Abstraction chung cho nhiều SMTP provider

Một hệ thống Spring Framework Mail có thể phải gửi email qua nhiều dịch vụ SMTP: nhà cung cấp A chuyên email giao dịch, nhà cung cấp B phục vụ marketing, một relay nội bộ dành cho cảnh báo và một SMTP account riêng cho từng khách hàng doanh nghiệp. Nếu mỗi chức năng nghiệp vụ tự chọn host, username, port và cách gọi `JavaMailSender`, code sẽ nhanh chóng bị phụ thuộc vào nhà cung cấp, khó chuyển tuyến, khó đo lường và dễ gửi nhầm thư hoặc thông tin đăng nhập.

Giải pháp là thiết kế một **abstraction chung cho nhiều SMTP provider**: nghiệp vụ tạo một yêu cầu gửi email có cấu trúc ổn định; một thành phần routing chọn profile đã được phê duyệt; một adapter của từng profile chịu trách nhiệm xây dựng và submit MIME qua SMTP; phần retry, outbox và tracking quản lý kết quả theo **email logic**, không theo ngoại lệ kỹ thuật ngẫu nhiên.

Cần phân biệt rõ: sử dụng chung interface **không** có nghĩa tất cả provider có cùng giới hạn, cùng SMTP response, cùng cơ chế bounce, cùng DKIM hoặc hỗ trợ idempotency giống nhau. Abstraction tốt thống nhất các phần có cùng ý nghĩa, đồng thời giữ nguyên những khác biệt ảnh hưởng tới tính đúng đắn và khả năng giao thư.

Bài học này thiết kế mô hình từ đầu tới cuối với **Spring Boot, JavaMailSender, cấu hình nhiều SMTP profiles, provider registry, routing, retry/failover có kiểm soát, phân biệt SMTP submission với delivery**, bảo mật tenant và bộ kiểm thử nhiều nhà cung cấp.

## 1. Khi nào cần abstraction chung?

Ví dụ một ứng dụng SaaS có các nhu cầu sau:

| Nguồn email | Kênh gửi | Quy tắc đặc thù |
|---|---|---|
| Xác nhận đơn hàng | SMTP Provider A | Ưu tiên độ trễ thấp, giữ audit từng message |
| Newsletter | SMTP Provider B | Quota và suppression khác email giao dịch |
| Cảnh báo vận hành | Relay nội bộ | Chỉ cho phép domain và recipient thuộc tổ chức |
| Email cho tenant doanh nghiệp | SMTP profile riêng | Credential, domain và hạn mức tách theo tenant |
| Dự phòng khi provider sự cố | Provider C đã chuẩn bị | Chỉ được chuyển khi submission **chưa được chấp nhận** hoặc có chính sách xử lý outcome rõ ràng |

Nếu code nghiệp vụ viết trực tiếp:

```java
if (transactional) {
    sendWithProviderA(...);
} else if (marketing) {
    sendWithProviderB(...);
} else {
    sendWithInternalRelay(...);
}
```

rồi lặp lựa chọn đó ở hàng chục service, hệ thống sẽ gặp:
- hardcode nhà cung cấp trong nghiệp vụ;
- cấu hình TLS và timeout không nhất quán;
- thiếu một nơi quyết định rate limit, quota và policy;
- khó viết unit test không dùng SMTP thật;
- khó thống kê tổng số attempts và kết quả theo provider;
- có nguy cơ failover gửi trùng hoặc sai danh tính miền;
- thay nhà cung cấp cần sửa nhiều business classes.

**Mục tiêu:** code nghiệp vụ yêu cầu “gửi loại thông báo này theo danh tính được phép”, chứ không phải “kết nối host SMTP X bằng port Y”.

## 2. Bốn lớp trách nhiệm cần tách

```text
OrderService / IdentityService / MarketingService
                 |
                 | EmailCommand (email logic)
                 v
       OutboundMailApplicationService
        - authorize recipient
        - idempotency / outbox
        - choose mail category
                 |
                 v
          ProviderRouter
        - policy / tenant
        - route / quotas
        - health eligibility
                 |
                 v
        MailSubmissionPort
        (provider-neutral interface)
                 |
       +---------+----------+
       |                    |
       v                    v
 SmtpAdapter A         SmtpAdapter B
 JavaMailSender A      JavaMailSender B
       |                    |
       v                    v
 Provider A SMTP       Provider B SMTP
       |                    |
       +---------+----------+
                 |
                 v
        Receiving mail systems
```

Mỗi lớp có trách nhiệm:

1. **Application/service nghiệp vụ:** quyết định email nào được gửi, nội dung gì, ai được nhận và mỗi hành động tạo bao nhiêu email logic.
2. **Router/policy:** chọn tuyến phù hợp giữa các provider đã được phê duyệt.
3. **Submission adapter:** biến nội dung thành MIME, kết nối SMTP và trả outcome theo contract chung.
4. **Outbox và delivery tracker:** lưu attempt, retry, reconcile, webhook/bounce và trạng thái tiếp theo.

Không gộp bốn trách nhiệm này vào một lớp `MailUtil.sendAnything(...)` nhiều tham số tùy chọn.

## 3. Xác định điều gì là chung, điều gì không chung

Các phần có thể chuẩn hóa:
- message key của ứng dụng;
- sender identity đã được phê duyệt;
- người nhận và danh mục thông báo;
- subject, plain text và HTML;
- metadata không nhạy cảm dùng để trace;
- attempt ID và provider route đã chọn;
- outcome submission ở mức `ACCEPTED`, `RETRYABLE_FAILURE`, `PERMANENT_FAILURE` hoặc `UNKNOWN`;
- yêu cầu không retry vô hạn;
- logs/metrics theo message key và provider.

Những điểm phải giữ khả năng cấu hình hoặc mở rộng:
- SMTP host/port và TLS mode;
- cơ chế AUTH: password, app password, OAuth2 hoặc relay không AUTH theo policy;
- hạn mức request, connection, daily quota;
- From/envelope sender và custom return-path;
- DKIM signing domain và domain verification;
- lỗi SMTP/phản hồi provider cụ thể;
- hỗ trợ provider message ID, dashboard, webhook và suppression;
- giới hạn attachment/message size;
- định nghĩa và thời hạn idempotency nếu dùng provider HTTP API.

**Một abstraction dùng được không được che mất trạng thái `UNKNOWN` hoặc giả định có một capability mà SMTP chuẩn không cung cấp.**

## 4. Phân biệt ba mốc trong vòng đời email

```text
Email request persisted
    |
    | API 202: queued in outbox
    v
Worker selects provider
    |
    | JavaMailSender.send(...)
    v
SMTP server accepts submission
    |
    | SMTP 250 at the applicable phase
    v
Provider queue / transfer
    |
    | provider retries delivery when deferred
    v
Receiving mail server
    |
    | delivery event if supported
    v
Application delivery status
```

- `QUEUED`: application đã lưu yêu cầu xử lý.
- `SMTP_ACCEPTED`: upstream SMTP/relay đã chấp nhận submission theo kết quả mà client quan sát được.
- `DELIVERED`: có bằng chứng phù hợp từ provider/receiver về việc giao tới server đích, theo định nghĩa event của provider.

Một `send(...)` không ném exception **không chứng minh email đã vào Inbox hoặc đã được mở**.

Điều này quan trọng khi đổi provider: nếu provider A đã accepted email và báo `deferred` ở bước delivery, application **không nên gửi tiếp một bản mới qua provider B** chỉ vì B đang khỏe.

## 5. Thiết kế dữ liệu chung cho một email logic

Một request không nên chứa SMTP password hoặc cho phép caller cung cấp arbitrary SMTP host.

Ví dụ model Java 17+:

```java
package com.example.mail;

public enum MailCategory {
    TRANSACTIONAL,
    SECURITY,
    MARKETING,
    INTERNAL_ALERT
}

public record EmailCommand(
    String messageKey,
    String tenantId,
    MailCategory category,
    String recipient,
    String subject,
    String plainText,
    String htmlText,
    String templateVersion
) {}
```

Ý nghĩa:
- `messageKey`: định danh **một email logic**, ổn định qua các attempt.
- `tenantId`: ranh giới phân quyền và chọn profile, không tự lấy từ dữ liệu chưa xác thực.
- `category`: routing policy dựa trên loại thông báo, không dựa vào tên provider hardcode trong business code.
- `recipient`: phải được kiểm tra quyền và chính sách nhận mail.
- `subject/plainText/htmlText`: nội dung đã render hoặc snapshot theo quy tắc nghiệp vụ.
- `templateVersion`: hỗ trợ truy nguyên chính xác nội dung được sử dụng.

Một hệ thống lớn có thể không lưu toàn bộ body trong outbox mà lưu reference hoặc snapshot được mã hóa. Điều đó phụ thuộc dữ liệu, yêu cầu audit, retention và cách retry.

### 5.1. Request không phải một lần thử gửi

Ví dụ:

```text
messageKey = msg-1001
   |
   +-- attempt-1 -> provider-A -> TEMPORARY_FAILURE
   |
   +-- attempt-2 -> provider-A -> SMTP_ACCEPTED
                                   |
                                   +-- delivery deferred
                                   +-- delivery accepted
```

Dù attempt thay đổi, `messageKey` giữ nguyên. Nếu user chủ động yêu cầu gửi một thông báo mới sau đó, application có thể tạo message key mới theo business policy.

### 5.2. Không để domain model phụ thuộc vào SMTP internals

Không nên yêu cầu tầng nghiệp vụ tạo:
- `jakarta.mail.Session`;
- `MimeMessage`;
- `Transport`;
- `MessagingException`;
- `mail.smtp.ssl.enable`.

Những khái niệm này thuộc adapter. Business layer chỉ nên dùng value objects và outcomes có ý nghĩa trong hệ thống.

## 6. Interface submission chung

Abstraction nên phản ánh **submission**, không hứa delivery:

```java
package com.example.mail;

import java.time.Instant;

public interface MailSubmissionPort {

    SubmissionReceipt submit(
        EmailCommand command,
        String providerKey,
        String attemptId
    );
}

public record SubmissionReceipt(
    String messageKey,
    String attemptId,
    String providerKey,
    Instant acceptedAt
) {}
```

`SubmissionReceipt` trong mẫu này có nghĩa **SMTP submission được client quan sát là thành công**. Với generic SMTP, receipt **không bắt buộc** chứa provider message ID vì protocol không cam kết một ID thống nhất có thể dùng truy vấn trạng thái.

Những extension có thể có:

```java
public record ProviderMetadata(
    String rfcMessageId,
    String providerMessageId,
    String smtpQueueId
) {}
```

Các trường phải có ý nghĩa rõ, được hỗ trợ bởi adapter/provider tương ứng và có thể để trống; không tự gán RFC `Message-ID` thành provider queue ID.

### 6.1. Trả lỗi bằng taxonomy thống nhất

```java
public enum FailureCategory {
    RETRYABLE,
    PERMANENT,
    UNKNOWN
}

public final class SubmissionFailure
        extends RuntimeException {

    private final FailureCategory category;
    private final String safeCode;
    private final String providerKey;

    public SubmissionFailure(
            FailureCategory category,
            String safeCode,
            String providerKey,
            Throwable cause) {
        super(safeCode, cause);
        this.category = category;
        this.safeCode = safeCode;
        this.providerKey = providerKey;
    }

    public FailureCategory category() {
        return category;
    }

    public String safeCode() {
        return safeCode;
    }

    public String providerKey() {
        return providerKey;
    }
}
```

`safeCode` là mã đã chuẩn hóa như `SMTP_451_BEFORE_DATA` hoặc `AUTH_CONFIG_ERROR`, không phải toàn bộ raw exception chứa địa chỉ mail, SMTP replies nhạy cảm hoặc token.

**Chỉ những trường hợp đã được chứng minh là an toàn để thử lại mới nên chuyển `RETRYABLE`.** Lỗi timeout không rõ server đã nhận DATA hay chưa phải được đánh dấu `UNKNOWN` khi không có bằng chứng kết luận.

### 6.2. Một interface chung không tự mang lại exactly-once

Ngay cả với `messageKey` và `attemptId`:
- SMTP không mặc định deduplicate theo custom header.
- Hai lần gọi `send(...)` có thể tạo hai bản email.
- Một send đã được server chấp nhận không thể rollback bằng transaction database.
- Failover sau kết quả không rõ có thể tạo duplicate ở provider mới.

Abstraction phải để application lưu và xử lý sự không chắc chắn này, không che giấu bằng một giá trị `boolean success`.

## 7. Cấu hình nhiều SMTP provider tập trung

Trong Spring Boot, có thể đặt namespace ứng dụng riêng:

```yaml
app:
  outbound-mail:
    providers:
      primary:
        host: smtp-a.example.net
        port: 587
        username: ${SMTP_A_USERNAME}
        password: ${SMTP_A_PASSWORD}
        verified-from: receipts@example.com
        implicit-tls: false

      secondary:
        host: smtp-b.example.net
        port: 465
        username: ${SMTP_B_USERNAME}
        password: ${SMTP_B_PASSWORD}
        verified-from: receipts@example.com
        implicit-tls: true

      alerts:
        host: relay.internal.example
        port: 587
        username: ${SMTP_ALERT_USERNAME}
        password: ${SMTP_ALERT_PASSWORD}
        verified-from: alerts@example.com
        implicit-tls: false
```

**Tất cả hostname, account và domain trên đều là ví dụ.** Profile production phải dùng thông số được provider/hạ tầng cấp, được xác minh quyền sử dụng From domain và bảo vệ secret.

### 7.1. Bind cấu hình bằng ConfigurationProperties

```java
package com.example.mail;

import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.outbound-mail")
public record MultiSmtpProperties(
    Map<String, SmtpAccount> providers
) {
    public record SmtpAccount(
        String host,
        int port,
        String username,
        String password,
        String verifiedFrom,
        boolean implicitTls
    ) {}
}
```

Đây là một model Spring Boot 3 dùng constructor binding cho record. Khi ứng dụng có nhiều điều kiện đặc thù, bổ sung validation:
- `host` không rỗng;
- `port` trong phạm vi hợp lệ;
- TLS mode được profile hỗ trợ;
- credential được cung cấp theo policy;
- From domain đã xác minh;
- không được có provider key trùng hoặc profile thiếu.

Không in đối tượng `MultiSmtpProperties` ra log vì record có thể chứa password.

### 7.2. Tạo sender được cấu hình một lần cho mỗi profile

```java
package com.example.mail;

import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
@EnableConfigurationProperties(MultiSmtpProperties.class)
public class MultiSmtpConfiguration {

    @Bean
    ProviderRegistry providerRegistry(MultiSmtpProperties config) {
        Map<String, SmtpProviderBinding> bindings =
            new HashMap<>();

        config.providers().forEach((providerKey, account) -> {
            JavaMailSender sender = buildSender(account);

            bindings.put(
                providerKey,
                new SmtpProviderBinding(
                    providerKey,
                    account.verifiedFrom(),
                    sender
                )
            );
        });

        return new ProviderRegistry(bindings);
    }

    private static JavaMailSender buildSender(
            MultiSmtpProperties.SmtpAccount account) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(account.host());
        sender.setPort(account.port());
        sender.setUsername(account.username());
        sender.setPassword(account.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();

        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        if (account.implicitTls()) {
            props.put("mail.smtp.ssl.enable", "true");
        } else {
            props.put("mail.smtp.starttls.enable", "true");
            props.put("mail.smtp.starttls.required", "true");
        }

        return sender;
    }
}
```

Đoạn trên minh họa profile dùng SMTP AUTH bằng username/password. Với OAuth2 hoặc relay không AUTH, adapter/configuration factory cần hỗ trợ contract riêng, không thể giả định mọi SMTP provider cùng xác thực bằng password.

**Lưu ý về vòng đời:** các sender được tạo ở startup và được giữ trong registry ổn định. Không sửa `setHost`, `setUsername` hoặc `setPassword` của cùng một instance khi nhiều worker đang gửi.

### 7.3. Registry immutable để tránh chọn sai provider

```java
package com.example.mail;

import java.util.Map;
import org.springframework.mail.javamail.JavaMailSender;

public record SmtpProviderBinding(
    String providerKey,
    String verifiedFrom,
    JavaMailSender sender
) {}

public final class ProviderRegistry {

    private final Map<String, SmtpProviderBinding> providers;

    public ProviderRegistry(
            Map<String, SmtpProviderBinding> providers) {
        this.providers = Map.copyOf(providers);
    }

    public SmtpProviderBinding require(String providerKey) {
        SmtpProviderBinding binding =
            providers.get(providerKey);

        if (binding == null) {
            throw new IllegalArgumentException(
                "Unknown or disabled mail provider"
            );
        }

        return binding;
    }
}
```

Một registry immutable giúp ngăn thay đổi routing/credential ngay trong business method. Nếu cần hot reload:
- dựng registry/senders mới từ cấu hình đã xác minh;
- chuyển sang phiên bản mới một cách atomic ở tầng service;
- có quy tắc xử lý active sends và hủy tài nguyên cũ;
- kiểm soát cấu hình bởi người có quyền;
- kiểm thử credential rotation và profile rollback.

Đừng giữ một `JavaMailSenderImpl` singleton rồi mutate account theo mỗi tenant/recipient.

## 8. SMTP adapter triển khai interface chung

Với registry và model trên, một adapter có thể dùng bất kỳ provider SMTP nào nếu profile hợp lệ.

```java
package com.example.mail;

import java.time.Clock;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MultiSmtpSubmissionAdapter
        implements MailSubmissionPort {

    private final ProviderRegistry registry;
    private final MailFailureClassifier classifier;
    private final Clock clock;

    public MultiSmtpSubmissionAdapter(
            ProviderRegistry registry,
            MailFailureClassifier classifier,
            Clock clock) {
        this.registry = registry;
        this.classifier = classifier;
        this.clock = clock;
    }

    @Override
    public SubmissionReceipt submit(
            EmailCommand command,
            String providerKey,
            String attemptId) {

        SmtpProviderBinding binding =
            registry.require(providerKey);

        MimeMessage mime = binding.sender().createMimeMessage();

        try {
            MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom(binding.verifiedFrom());
            helper.setTo(command.recipient());
            helper.setSubject(command.subject());

            if (command.htmlText() == null
                    || command.htmlText().isBlank()) {
                helper.setText(command.plainText(), false);
            } else {
                helper.setText(
                    command.plainText(),
                    command.htmlText()
                );
            }

            mime.setHeader(
                "X-Application-Message-Key",
                command.messageKey()
            );
            mime.setHeader("X-Mail-Attempt-ID", attemptId);

        } catch (MessagingException ex) {
            throw new SubmissionFailure(
                FailureCategory.PERMANENT,
                "MIME_BUILD_ERROR",
                providerKey,
                ex
            );
        }

        try {
            binding.sender().send(mime);
        } catch (MailException ex) {
            throw classifier.classify(providerKey, ex);
        }

        return new SubmissionReceipt(
            command.messageKey(),
            attemptId,
            providerKey,
            clock.instant()
        );
    }
}
```

`MailFailureClassifier` là interface/service của ứng dụng, được giới thiệu ở mục tiếp theo. Đoạn adapter minh họa:
- Chọn sender từ **registry**, không từ host tùy ý của người gọi.
- Gán From theo profile đã verified.
- Tạo `MimeMessage`/`MimeMessageHelper` riêng cho mỗi attempt.
- Gắn tracing headers không chứa secret.
- Dựng email trước khi gọi mạng.
- Chuyển lỗi gửi qua một classifier có nhận biết đặc tính SMTP.
- Trả `SubmissionReceipt` khi lời gọi submission hoàn tất không lỗi đồng bộ.

Khi dùng production:
- Cần validate `EmailCommand` trước khi tới adapter, đặc biệt recipient, subject, plain text và quyền tenant.
- Các trường header phải được kiểm soát độ dài/ký tự để tránh header injection; ID nên là giá trị được tạo và xác thực bởi server.
- Nếu lỗi khi build MIME do dữ liệu thiếu hoặc malformed, phân loại permanent theo contract; các lỗi hạ tầng nội bộ như thiếu bộ nhớ cần xử lý riêng, không vơ tất cả thành lỗi người dùng.
- Nếu exception sau khi bắt đầu SMTP, classifier phải **tránh khẳng định chưa gửi** khi có khả năng server đã nhận message.
- Đừng lưu password hoặc thông tin MIME nhạy cảm trong log.

### 8.1. Clock bean tường minh

Trong application có thể cung cấp:

```java
@Bean
Clock mailClock() {
    return Clock.systemUTC();
}
```

Với JUnit, thay bằng `Clock.fixed(...)` để test receipt timestamps, retry schedule và deadline một cách deterministic.

### 8.2. Vì sao không trả boolean?

`boolean sent` không phân biệt:
- kết nối chưa được tạo;
- SMTP reject trước DATA;
- lỗi xác thực;
- TLS hostname mismatch;
- SMTP accepted;
- timeout sau DATA, kết quả không xác định;
- email đang được provider retry delivery.

Một kết quả hoặc exception có taxonomy rõ giúp downstream quyết định retry/failover an toàn hơn.

## 9. Phân loại lỗi theo đúng tầng và thông tin có thật

Contract classifier:

```java
package com.example.mail;

import org.springframework.mail.MailException;

public interface MailFailureClassifier {
    SubmissionFailure classify(
        String providerKey,
        MailException exception
    );
}
```

Một số nhóm lỗi cần phân biệt:

| Nhóm | Ví dụ | Quyết định gợi ý |
|---|---|---|
| **Pre-submission / build** | Recipient format sai, MIME construction fail | Dừng, sửa dữ liệu/template; không retry mù |
| **Configuration** | Sai credentials, chứng chỉ/TLS hostname không hợp lệ | Cảnh báo và sửa cấu hình; không retry dồn dập |
| **Transient before acceptance** | SMTP 421/451 tại giai đoạn được xác định chưa chấp nhận message | Retry có backoff và quota |
| **Permanent rejection** | SMTP 550/554 theo response rõ ràng | Dừng hoặc xử lý riêng theo recipient/provider policy |
| **Outcome unknown** | Connection mất sau DATA trước phản hồi cuối | Reconciliation; không resubmit ngay |
| **Delivery deferred** | Provider đã accepted và đang chờ giao đích | Không retry SMTP submission ở application |

Mã SMTP và exception cần được đọc trong ngữ cảnh:
- SMTP command `MAIL FROM`, `RCPT TO` hoặc `DATA`;
- code phản hồi 4xx/5xx và enhanced status;
- nested cause (socket, TLS, Jakarta Mail);
- có partial recipient acceptance hay không;
- server đã accepted end-of-DATA chưa;
- provider documentation và chính sách.

Không viết:

```java
catch (MailException ex) {
    // Sai: mọi lỗi gửi đều có thể retry an toàn.
    retryThroughAnotherProviderImmediately();
}
```

Lời gọi `JavaMailSender.send(...)` có thể ném `MailSendException`, `MailAuthenticationException` hoặc lỗi khác. Tên exception ngoài cùng **không đủ để kết luận mọi recipient chưa nhận thư**. Đặc biệt, một kết nối mất sau khi relay nhận DATA có thể tạo kết quả `UNKNOWN`.

## 10. ProviderRouter: chọn tuyến theo policy, không theo cảm tính

Không nên cho mọi business service tự chọn `providerKey` từ một chuỗi tùy ý.

Một router có thể nhận metadata đã xác thực:

```java
package com.example.mail;

public record RouteContext(
    String tenantId,
    MailCategory category,
    String fromDomain,
    String region
) {}

public interface ProviderRouter {
    String choosePrimary(RouteContext context);
}
```

Một vài quy tắc hợp lệ:
- `TRANSACTIONAL` → Provider A;
- `MARKETING` → Provider B;
- `INTERNAL_ALERT` → relay nội bộ;
- tenant doanh nghiệp có hợp đồng riêng → profile riêng;
- region được phép xử lý dữ liệu → provider trong region tương ứng;
- provider đang bảo trì → chọn tuyến dự phòng **nếu thông báo chưa được submit và policy cho phép**.

### 10.1. Rule table dễ kiểm soát hơn chuỗi if rải rác

| Đầu vào | Provider được phép | Ưu tiên |
|---|---|---|
| Transactional, tenant thường | A, C | A trước |
| Marketing, có opt-in | B | B |
| Internal alert | Internal relay | Internal |
| Tenant enterprise X | Dedicated X | Dedicated |
| Không có quyền gửi | Không provider nào | Từ chối |

Router phải dùng tenant identity từ context đã xác thực, không tin `tenantId` được client tùy ý cung cấp.

### 10.2. Chọn tuyến nên ổn định cho một attempt

Lưu `providerKey` đã chọn cùng attempt. Nếu job retry, router có thể xem xét lại policy nhưng phải ghi rõ:
- attempt trước dùng provider nào;
- vì sao chuyển;
- có bằng chứng chưa accepted không;
- From/domain và recipient policy vẫn hợp lệ không;
- account/quota mới có cho phép không.

Không chọn provider mới mỗi lần bất kỳ chỉ vì danh sách đang đảo thứ tự.

## 11. Load balancing khác failover

Hai chiến lược thường bị gộp:

**Load balancing:** phân phối các **email logic khác nhau** qua nhiều providers để dùng quota hoặc phân tải.

**Failover:** khi một attempt gặp vấn đề, cân nhắc chuyển **cùng email logic** sang provider khác.

Ví dụ:

```text
Load balancing
  msg-100 -> A
  msg-101 -> B
  msg-102 -> A

Failover
  msg-100 attempt-1 -> A (không accepted, được xác minh)
          attempt-2 -> B (SMTP_ACCEPTED)
```

Load balancing thường ít rủi ro duplicate hơn vì mỗi email có một tuyến chủ động. Failover cần xác minh outcome của lần gửi trước.

### 11.1. Không failover ngay sau timeout không rõ kết quả

Một tình huống:

```text
Application                    Provider A
   |---- SMTP DATA ------------>|
   |---- end-of-DATA ----------->|
   |                             | accepted to queue
   |<---- response lost ---------X
   |
   | timeout -> sends to Provider B
   v
Provider B accepts another copy
```

Người nhận có thể nhận **hai email**. Nếu classifier không biết A đã nhận chưa, lưu `UNKNOWN`, tra cứu provider log/API/webhook nếu có hoặc xử lý theo chính sách chấp nhận rủi ro đã được phê duyệt.

Một interface chung không thể biến generic SMTP thành exactly-once.

### 11.2. Khi nào failover có thể hợp lý?

Các trường hợp có thể xem xét:
- Provider A được phát hiện không khả dụng **trước khi mở submission**.
- Kết nối tới A thất bại rõ ràng trước khi chuyển nội dung/thực hiện SMTP DATA.
- A trả từ chối rõ ràng cho đúng recipient/giai đoạn, và policy cho phép gửi qua B.
- A bị disable bởi route policy trước khi job bắt đầu.
- Provider/API hỗ trợ idempotency/reconciliation theo contract và bảo đảm xử lý an toàn.

Vẫn cần:
- giới hạn số tuyến dự phòng;
- kiểm tra sender domain và quyền dữ liệu;
- rate limit/quota của provider B;
- không tự retry lỗi permanent như invalid recipient;
- lưu attempt history;
- cảnh báo failover bất thường.

### 11.3. Provider accepted nhưng delivery deferred

Nếu A đã accepted và provider A đang retry delivery vì receiver tạm trả lỗi, **không tự động gửi lại qua B**. Deferred là trạng thái downstream của provider, không phải tín hiệu rằng application submission thất bại.

Muốn thiết kế backup delivery channel cho email cực kỳ quan trọng, phải có chính sách riêng về trùng lặp, thời hạn, recipient consent và khả năng đối soát, không coi đó là retry mặc định.

## 12. Outbox và idempotency xuyên nhiều provider

Một cách tổ chức:

```text
Business event
   |
   v
DB transaction:
  business update
  email_outbox(messageKey, PENDING, category, templateVersion)
   |
   v
Outbox dispatcher
   |
   v
Claim email job
   |
   v
Route policy -> providerKey
   |
   v
mail_send_attempt(
    messageKey,
    attemptId,
    providerKey,
    status=SENDING
)
   |
   v
Submission adapter
   |
   +--> SMTP_ACCEPTED
   +--> RETRY_WAIT
   +--> FAILED_PERMANENT / DEAD_LETTER
   +--> UNKNOWN
```

### 12.1. Schema tham khảo

```sql
CREATE TABLE email_outbox (
    message_key         VARCHAR(64) PRIMARY KEY,
    business_event_key  VARCHAR(160) NOT NULL,
    tenant_id           VARCHAR(80) NOT NULL,
    category            VARCHAR(40) NOT NULL,
    status              VARCHAR(32) NOT NULL,
    next_attempt_at     TIMESTAMP NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE email_send_attempt (
    attempt_id          VARCHAR(64) PRIMARY KEY,
    message_key         VARCHAR(64) NOT NULL,
    provider_key        VARCHAR(80) NOT NULL,
    attempt_number      INTEGER NOT NULL,
    started_at          TIMESTAMP NOT NULL,
    finished_at         TIMESTAMP,
    outcome             VARCHAR(32) NOT NULL,
    safe_error_code     VARCHAR(120),
    provider_message_id VARCHAR(255),
    CONSTRAINT fk_attempt_message
        FOREIGN KEY (message_key)
        REFERENCES email_outbox(message_key),
    CONSTRAINT uq_attempt_number
        UNIQUE (message_key, attempt_number)
);
```

Nếu ứng dụng cần truy vết delivery:
- lưu thêm provider events trong bảng riêng;
- unique theo provider event ID thích hợp;
- xử lý duplicate, out-of-order webhook;
- map provider message ID/custom metadata về message key.

### 12.2. Một request tạo một email logic

Khi client gửi lại HTTP request vì timeout:
- dùng `Idempotency-Key` và unique constraint;
- không tạo hai outbox items nếu đó là cùng một hành động;
- giữ message key cho mọi attempt;
- không phụ thuộc vào việc A/B có idempotency phía SMTP hay không.

Nếu phải gửi **một email hoàn toàn mới** do user yêu cầu hợp lệ, tạo message key mới theo business policy, không coi đó là retry.

### 12.3. Claim và lease

Hai worker không được cùng gửi một outbox row. Dùng atomic claim/lease hoặc broker visibility semantics thích hợp. Fencing token ngăn stale worker ghi đè DB state, nhưng không thể thu hồi SMTP submission đã xảy ra khi worker mất lease.

Hãy thiết kế timeout/lease, retry budget và trạng thái `UNKNOWN` cùng nhau. Không chuyển mọi job `SENDING` hết lease về `PENDING` để gửi lại mà không có chính sách reconciliation.

## 13. SPF, DKIM, DMARC và From identity khi đổi provider

Đây là lỗi thường bị bỏ qua: Provider B có thể nhận SMTP AUTH thành công nhưng **chưa được ủy quyền gửi bằng domain của doanh nghiệp**.

Ví dụ:
- Header From: `receipts@example.com`.
- Provider A ký DKIM với `d=example.com`.
- Provider B mặc định ký DKIM với `d=provider-b.example`.
- Provider B dùng envelope sender thuộc domain của họ.

Khi gửi qua B, SPF và DKIM có thể pass đối với **domain của provider**, nhưng không aligned với `example.com` của Header From. DMARC có thể fail.

### 13.1. Trước khi kích hoạt provider dự phòng

Cần xác minh:
1. Domain From đã được verified trong account B.
2. SPF/return-path/bounce domain dùng tại B phù hợp.
3. DKIM signer của B dùng aligned domain hoặc có thiết kế khác làm DMARC pass.
4. DMARC policy được kiểm thử với email nhận thực tế.
5. Bounce/suppression/unsubscribe sync theo policy.
6. Email có thể được gửi từ IP/region của B theo chính sách bảo mật.
7. B có quyền gửi đúng loại email và giới hạn throughput tương ứng.

**Đăng nhập SMTP thành công không đồng nghĩa đã có đủ domain authentication hoặc deliverability.**

### 13.2. Header From khác envelope MAIL FROM

Trong Spring:

```java
helper.setFrom("receipts@example.com");
```

thường đặt header From. SMTP envelope sender có thể được điều khiển qua `mail.smtp.from` của Jakarta Mail hoặc được provider tự thiết lập bằng custom return-path/bounce domain. Không tự thêm một `Return-Path` header rồi tưởng SMTP `MAIL FROM` đã đổi.

Một profile chung nên lưu và kiểm tra:
- verified Header From;
- envelope sender policy;
- DKIM signing domain;
- allowed sender identities.

### 13.3. Suppression và recipient consent

Nếu provider A đã suppress người nhận do hard bounce hoặc spam complaint, chuyển sang B không được dùng để **né suppression**. Application cần có policy/registry liên nhà cung cấp theo yêu cầu pháp lý, consent và bảo vệ reputation.

Đối với marketing, user opt-out phải được áp dụng **trước routing**, không phụ thuộc nhà cung cấp nào đang sẵn sàng.

## 14. Bảo mật trong hệ thống đa nhà cung cấp và đa tenant

Khi dùng nhiều profiles, các rủi ro lớn nhất là:
- chọn sai SMTP account;
- gửi From bằng domain chưa verified;
- lộ credential giữa tenants;
- gửi dữ liệu của tenant A tới provider/region không được phép;
- SSRF từ hostname SMTP do user điều khiển;
- ghi logs chứa body, API token hoặc password;
- cho phép failover sang dịch vụ chưa được hợp đồng/consent chấp thuận.

### 14.1. Không để HTTP client tự chỉ định SMTP host

Không nên có API:

```json
{
  "smtpHost": "arbitrary-host.example",
  "smtpPort": 25,
  "smtpPassword": "client-supplied-secret",
  "recipient": "someone@example.net"
}
```

rồi application tin trực tiếp và tạo kết nối. Ngoài spam abuse, nó còn có thể biến server thành SMTP proxy/SSRF channel.

Thay vào đó:
- caller chọn **chức năng nghiệp vụ**;
- backend xác thực tenant và policy;
- router chọn **provider key từ allowlist nội bộ**;
- account/secret chỉ được cấu hình bởi admin có quyền;
- kiểm soát DNS/IP/egress khi cần SMTP host động.

### 14.2. Ranh giới tenant và sender profile

Một tenant chỉ được dùng profile được liên kết với tenant đó. Thậm chí hai tenants dùng cùng provider brand, vẫn có thể có:
- credential khác nhau;
- From domains khác nhau;
- quota và billing khác nhau;
- region/data residency khác nhau;
- suppression lists khác nhau.

Test cần bao gồm tình huống tenant X cố yêu cầu profile của tenant Y và bị từ chối trước khi adapter gửi.

### 14.3. Secret và TLS

Với mỗi SMTP profile:
- lấy credential từ environment/secret manager được bảo vệ;
- giữ `STARTTLS required` hoặc implicit TLS đúng endpoint;
- bật hostname verification;
- tin CA hợp lệ, không sử dụng `ssl.trust=*`;
- thiết lập socket timeouts;
- có quy trình rotation;
- không log raw SMTP AUTH, passwords hoặc MIME body.

Không giảm bảo mật để tăng tốc failover.

## 15. Provider capability model: tránh giả định mọi thứ đồng nhất

Một số hệ thống cần phân biệt provider hỗ trợ:
- SMTP AUTH phương thức nào;
- batch size/connection reuse tới mức nào;
- custom MAIL FROM;
- SMTPUTF8;
- giới hạn kích thước message;
- provider message ID;
- delivery webhook;
- API tra cứu trạng thái;
- idempotency key của HTTP Email API;
- throttling hoặc quota khác nhau.

Có thể mô tả các khả năng đã được xác minh trong config:

```java
public record ProviderCapabilities(
    boolean customEnvelopeSender,
    boolean supportsSmtpUtf8,
    boolean deliveryWebhook,
    boolean statusLookup,
    boolean apiIdempotency,
    long maxMessageBytes
) {}
```

**Lưu ý:** `apiIdempotency` liên quan provider HTTP API cụ thể, không có nghĩa generic SMTP transport của provider sẽ tự deduplicate. `statusLookup` và `deliveryWebhook` cũng chỉ có nghĩa nếu đã thiết lập account, metadata và quyền API phù hợp.

Đừng biến capability flags thành giá trị dự đoán. Quản lý theo tài liệu/hợp đồng thực tế và integration tests.

### 15.1. Khi nào không nên ép mọi provider vào cùng adapter?

Nếu provider C hỗ trợ gửi qua HTTPS API với template ID, batch jobs và idempotency token, còn A/B chỉ có SMTP, vẫn có thể dùng **chung application port** nhưng cần hai loại adapter:

```text
OutboundMailPort
    |
    +--> SmtpSubmissionAdapter
    |      -> JavaMailSender
    |
    +--> HttpEmailApiAdapter
           -> Provider API client
```

Application không cần biết protocol trong business flow, nhưng response/error mapping khác nhau phải được giữ ở adapter. Không giả định email API có semantics giống SMTP `250` hoặc rằng SMTP có mọi đặc tính của API.

## 16. Quản lý timeout, quota, concurrency và backpressure

Một provider có thể có:
- giới hạn số SMTP connections đồng thời;
- giới hạn messages/giây;
- quota/ngày;
- giới hạn file đính kèm;
- chính sách riêng cho transactional/marketing;
- rate limits theo IP, account hoặc tenant.

Nếu worker tăng số threads không giới hạn, kết quả có thể là:
- nhiều `421`/`451`;
- TLS/AUTH handshakes dồn dập;
- retry storm;
- heap tăng do MIME attachments;
- người nhận bị gửi trùng sau timeout;
- các profiles khác bị ảnh hưởng bởi một provider quá tải.

### 16.1. Giới hạn theo provider thay vì một giới hạn toàn hệ thống

Ví dụ điều phối:

```text
Durable email outbox
       |
       v
Provider router
       |
       +--> Queue A -> A concurrency limit -> SMTP A
       |
       +--> Queue B -> B concurrency limit -> SMTP B
       |
       +--> Queue Internal -> Internal limit -> relay
```

Từng provider có:
- concurrency semaphore/worker allocation;
- rate limiter;
- retry policy;
- circuit breaker/health signal;
- backlog/latency metrics;
- quota reservation hoặc budget.

Với nhiều pods, semaphore trong một JVM chỉ giới hạn **một instance**. Muốn giới hạn toàn account/provider phải phối hợp giữa instances hoặc phân chia quota rõ ràng.

### 16.2. Retry không được khuếch đại sự cố

Một provider không sẵn sàng 5 phút có thể khiến rất nhiều jobs đến hạn cùng lúc. Dùng:
- exponential backoff có jitter;
- retry budget theo attempt count và elapsed time;
- circuit breaker hoặc route disable;
- giới hạn concurrency;
- dead letter sau khi hết ngân sách;
- `UNKNOWN` reconciliation thay vì gửi ngay sang provider khác.

Routing health nên là tín hiệu hỗ trợ quyết định **trước khi submission**, không dùng như bằng chứng rằng message đang gửi ở một provider khác chắc chắn chưa được nhận.

### 16.3. Timeout và lease phải phối hợp

Ví dụ socket read timeout 30 giây nhưng worker lease 10 giây có thể khiến job bị claim lại trước khi attempt cũ xong. Nếu worker mới gửi qua provider khác, rủi ro duplicate tăng.

Cần thiết kế:
- timeout connect/read/write phù hợp;
- lease đủ dài hoặc heartbeat;
- fencing khi ghi kết quả DB;
- xử lý stale/unknown attempts;
- không retry khi chưa biết upstream đã nhận hay chưa.

## 17. Tái sử dụng JavaMailSender, không chia sẻ MIME message

Một sender/profile có thể được nhiều service dùng chung sau khi cấu hình hoàn tất. Nhưng mỗi email/attempt nên tạo:
- `MimeMessage` mới;
- `MimeMessageHelper` mới;
- headers theo message key và attempt ID;
- nguồn dữ liệu/attachment được kiểm soát.

Không giữ một `MimeMessage` trong field của singleton rồi sửa recipient/body theo từng request. Điều đó có thể tạo lỗi gửi sai người và lộ dữ liệu giữa tenants.

### 17.1. Reuse bean không đồng nghĩa reuse TCP connection

`JavaMailSenderImpl` có thể giữ Jakarta Mail `Session` và configuration lâu dài nhưng **không bảo đảm tái sử dụng cùng SMTP socket qua mọi lời gọi `send(...)`**. Generic SMTP connection pooling cũng không tự xuất hiện chỉ vì có một bean singleton.

Có thể gửi nhiều `MimeMessage` trong một lời gọi `send(messages...)` để giảm một phần chi phí connect/TLS/AUTH ở các triển khai hỗ trợ, nhưng cần xử lý partial failures theo từng message. Không nên batch nhiều providers/tenants chung một sender.

### 17.2. Attachment và inline resources

Với email có attachment:
- validate file type/size và quyền truy cập;
- phân biệt plain/HTML/inline resources;
- dùng `InputStreamSource` có thể mở stream lại khi cần;
- không cache email MIME chứa dữ liệu cá nhân của tenant này để dùng cho tenant khác;
- giới hạn heap và concurrency theo kích thước message.

Nếu chuyển tuyến provider khác, đảm bảo attachment còn tồn tại và nội dung nghiệp vụ vẫn giống snapshot đã được phê duyệt. Nhà cung cấp có thể có các giới hạn kích thước MIME khác nhau.

## 18. Tracking xuyên nhà cung cấp: dùng định danh của ứng dụng

Không nên dùng provider message ID làm **khóa duy nhất** của email logic vì:
- các provider có format khác nhau;
- một provider có thể không trả ID trong generic SMTP;
- failover tạo một attempt mới;
- webhook có thể đến trễ hoặc không đầy đủ;
- một email có nhiều recipient cần theo dõi riêng.

Khuyến nghị:

```text
Application messageKey: msg-1001
  |
  +-- attempt att-A
  |      provider: A
  |      outcome: RETRYABLE_FAILURE
  |
  +-- attempt att-B
         provider: B
         outcome: SMTP_ACCEPTED
         providerMessageId: optional
         |
         +-- delivery event: deferred
         +-- delivery event: delivered
```

### 18.1. Tracing headers

Adapter có thể thêm:

```java
mime.setHeader(
    "X-Application-Message-Key",
    command.messageKey()
);
mime.setHeader(
    "X-Mail-Attempt-ID",
    attemptId
);
```

Chúng giúp đối soát khi provider bảo toàn header, nhưng người nhận có thể xem raw headers. Không đưa:
- secret;
- tenant authentication token;
- dữ liệu nhạy cảm;
- internal database ID nếu nó tiết lộ cấu trúc hoặc thông tin bảo mật.

Đây là **tracing**, không phải SMTP-level idempotency.

### 18.2. Webhook khác SMTP receipt

Một provider có thể gửi `delivered`, `bounced`, `deferred`; provider khác có thể không cung cấp webhook. Chuẩn hóa event khi có dữ liệu:

```java
public enum DeliveryEventType {
    DEFERRED,
    DELIVERED,
    BOUNCED,
    DROPPED,
    COMPLAINT
}
```

Nhưng cần lưu raw provider event/reference trong vùng bảo vệ phù hợp để chẩn đoán. Không tự suy ra `DELIVERED` khi provider chỉ trả `SMTP_ACCEPTED`.

### 18.3. Webhook phải chống trùng và sai thứ tự

- Xác minh chữ ký/provider authentication.
- Dedupe theo event ID do provider hỗ trợ.
- Liên kết provider-specific ID về message key/attempt.
- Lưu event history.
- Không cho một event deferred đến muộn xóa bỏ delivered đã được xác nhận.
- Không để webhook từ provider A làm thay trạng thái attempt của B.
- Bảo vệ recipient và bounce reason khỏi truy cập trái phép.

## 19. Testing abstraction chung bằng unit tests

Unit tests nên tách router, adapter và orchestration. Không cần SMTP server thật để kiểm tra logic chọn provider.

### 19.1. Test routing

Ví dụ một router policy đơn giản:

```java
public final class StaticProviderRouter
        implements ProviderRouter {

    @Override
    public String choosePrimary(RouteContext context) {
        return switch (context.category()) {
            case TRANSACTIONAL, SECURITY -> "primary";
            case MARKETING -> "secondary";
            case INTERNAL_ALERT -> "alerts";
        };
    }
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class StaticProviderRouterTest {

    @Test
    void routesTransactionalMailToPrimary() {
        ProviderRouter router = new StaticProviderRouter();

        RouteContext context = new RouteContext(
            "tenant-test",
            MailCategory.TRANSACTIONAL,
            "example.com",
            "allowed-region"
        );

        assertThat(router.choosePrimary(context))
            .isEqualTo("primary");
    }
}
```

Trong hệ thống thật, router cần kiểm tra tenant/profile allowlist, category policy và region. `StaticProviderRouter` chỉ minh họa việc tách routing ra khỏi SMTP transport.

### 19.2. Test adapter dùng sender mock và MIME thật

```java
import static org.mockito.Mockito.*;
import static org.assertj.core.api.Assertions.*;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class MultiSmtpAdapterTest {

    @Test
    void choosesExpectedSenderAndBuildsMessage() {
        JavaMailSender primary = mock(JavaMailSender.class);

        MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties())
        );
        when(primary.createMimeMessage()).thenReturn(mime);

        ProviderRegistry registry = new ProviderRegistry(
            Map.of(
                "primary",
                new SmtpProviderBinding(
                    "primary",
                    "receipts@example.com",
                    primary
                )
            )
        );

        Clock fixedClock = Clock.fixed(
            Instant.parse("2026-11-12T08:00:00Z"),
            ZoneOffset.UTC
        );

        MailFailureClassifier classifier =
            (providerKey, ex) -> new SubmissionFailure(
                FailureCategory.UNKNOWN,
                "SMTP_UNKNOWN",
                providerKey,
                ex
            );

        MailSubmissionPort port =
            new MultiSmtpSubmissionAdapter(
                registry, classifier, fixedClock
            );

        EmailCommand command = new EmailCommand(
            "msg-1001",
            "tenant-test",
            MailCategory.TRANSACTIONAL,
            "customer@example.net",
            "Xác nhận đơn hàng",
            "Xin chào Nguyễn Thị Ánh.",
            "<p>Xin chào Nguyễn Thị Ánh.</p>",
            "v1"
        );

        SubmissionReceipt receipt =
            port.submit(command, "primary", "att-1");

        verify(primary).send(mime);

        assertThat(receipt.providerKey())
            .isEqualTo("primary");
        assertThat(receipt.messageKey())
            .isEqualTo("msg-1001");

        assertThat(mime.getSubject())
            .isEqualTo("Xác nhận đơn hàng");
    }
}
```

Ví dụ này kiểm tra:
- adapter lấy đúng sender;
- tạo MIME trong bộ nhớ;
- gửi qua mock, không kết nối SMTP;
- receipt ghi đúng provider/message key.

Test có thể được mở rộng để capture `From`, `To`, text/plain, text/html, charset và headers. Nó **không chứng minh SMTP provider thật đã accepted**.

### 19.3. Test isolation giữa providers

Với hai mock senders, test nên assert:
- route primary chỉ gọi sender A;
- route secondary chỉ gọi sender B;
- tenant không có quyền dùng profile thì **không sender nào được gọi**;
- route không tồn tại bị từ chối;
- không thay cấu hình From/credential của profile khác.

Một test route thành công chưa đủ nếu hệ thống có nhiều tenant hoặc categories nhạy cảm.

## 20. Integration tests với hai SMTP endpoints

Để chứng minh abstraction hoạt động với hai SMTP profiles, dùng **hai SMTP sandbox instances** hoặc test harness có thể quan sát message độc lập.

```text
Integration test
       |
       v
ProviderRouter + MultiSmtpAdapter
       |
       +--> JavaMailSender A -> SMTP test server A
       |
       +--> JavaMailSender B -> SMTP test server B
```

Các case quan trọng:
1. Route A gửi một email, chỉ SMTP server A nhận.
2. Route B gửi một email, chỉ SMTP server B nhận.
3. Cấu hình From, Reply-To, envelope sender theo account policy.
4. STARTTLS/implicit TLS đúng endpoint nếu SMTP test harness hỗ trợ.
5. Invalid certificate hoặc hostname bị từ chối, không fallback plaintext.
6. Provider A trả lỗi transient trước DATA: workflow lưu retry/failover có kiểm soát.
7. Provider A disconnect sau DATA: kết quả `UNKNOWN`, không tự gửi qua B.
8. Provider B bị rate limit: worker giới hạn concurrency/retry.
9. Batch có partial failure: không retry các messages accepted.
10. Restart app không làm mất outbox/provider attempt history.

### 20.1. SMTP sandbox không luôn mô phỏng được mọi lỗi

GreenMail, Mailpit hoặc một fake SMTP server khác có thể kiểm tra happy path, MIME và routing. Nhưng không phải tất cả hỗ trợ:
- response 451 tại RCPT TO;
- response 421 tại connect;
- ngắt kết nối đúng sau dấu kết thúc DATA;
- partial recipient acceptance;
- server timeout/mTLS.

Để test lỗi ở từng phase, cần một **fault-injecting SMTP server** phù hợp. Không tạo outage trên provider production chỉ để chứng minh retry.

### 20.2. Database integration test cần backend thật

Nếu mục tiêu là kiểm thử atomic claim, unique constraints, outbox durability và dead letter, hãy dùng PostgreSQL/MySQL tương ứng production (có thể qua Testcontainers), không mock repository rồi gọi đó là integration test.

SMTP sandbox kiểm thử transport; database Testcontainers kiểm thử persistence; provider E2E kiểm thử event/delivery với tài khoản sandbox được phép.

## 21. Failover test cases cần đặc biệt nghiêm ngặt

Một ma trận hướng dẫn:

| Kịch bản ở Provider A | Có thể gửi ngay qua B? | Vì sao |
|---|---|---|
| Router chọn B trước khi A được gọi | Có, nếu B được phép | Chưa có submission tới A. |
| A bị disable trước attempt và không có side effect | Có | Không có bản email đang được A xử lý. |
| TCP connect tới A không thành công chắc chắn, chưa gửi DATA | Có thể | Còn phải kiểm tra retry budget và B policy. |
| A trả 451 rõ ràng trước khi accepted | Có thể sau backoff/chính sách | Lỗi transient nhưng tránh retry storm. |
| A từ chối recipient vĩnh viễn | Không tự động | Có thể là lỗi địa chỉ/chính sách, B không được dùng để né. |
| A accepted SMTP submission | Không | A đã chịu trách nhiệm chuyển thư. |
| A accepted rồi báo deferred | Không | Provider đang retry delivery. |
| Timeout sau end-of-DATA, không thấy reply | **Không tự động** | Outcome `UNKNOWN`, nguy cơ duplicate. |
| A trả authentication failure | Không chỉ vì B còn sống | Cần đánh giá secret/config và quyền chuyển account. |
| B chưa có aligned DKIM/verified From | Không | Có thể khiến DMARC fail hoặc vi phạm domain policy. |
| Recipient đã hard-bounce/opt-out | Không | Không được né suppression bằng provider khác. |

Test nên kiểm tra không chỉ “B có được gọi hay không”, mà cả:
- attempt count;
- provider route history;
- status trong outbox;
- retry due time;
- error category;
- log/audit event;
- suppression and authorization checks.

## 22. Vận hành và quan sát theo provider

Một abstraction chung cần log/metrics đủ tách lỗi của từng nhà cung cấp.

| Metric | Ý nghĩa |
|---|---|
| `mail_submit_attempts_total{provider,outcome}` | Số attempts theo provider và kết quả |
| `mail_submit_duration_seconds{provider}` | Độ trễ submission |
| `mail_route_selected_total{provider,category}` | Phân bố traffic |
| `mail_provider_failover_total{from,to,reason}` | Số lượt failover, tại sao |
| `mail_provider_circuit_state{provider}` | Trạng thái circuit breaker |
| `mail_provider_active_connections{provider}` | Số active connections nếu đo được thật |
| `mail_outbox_age_seconds{category}` | Backlog/latency |
| `mail_unknown_total{provider}` | Kết quả cần đối soát |
| `mail_dead_letter_total{reason}` | Job dừng tự động |
| `mail_delivery_events_total{provider,type}` | Delivered/deferred/bounced/complaint nếu provider hỗ trợ |

Các metric trên là tên minh họa. Không nhất thiết mọi provider cho phép quan sát chính xác active SMTP connections, vì `JavaMailSender` không phơi bày một connection pool metric chung.

### 22.1. Structured log

```json
{
  "event": "mail.submission_attempt",
  "messageKey": "msg-1001",
  "attemptId": "att-2",
  "providerKey": "secondary",
  "category": "TRANSACTIONAL",
  "outcome": "SMTP_ACCEPTED",
  "durationMs": 821,
  "routeReason": "approved-failover"
}
```

Tránh log:
- SMTP username/password hoặc OAuth access token;
- raw MIME body/attachment;
- email recipient nếu không cần và chưa được bảo vệ;
- verification/reset tokens;
- secret IDs hoặc connection properties nhạy cảm.

### 22.2. Alert có ý nghĩa

- Provider A có tỷ lệ 4xx hoặc TLS failure tăng đột ngột.
- Quota còn ít hoặc rate limit bị chạm liên tục.
- Failover tăng cao ngoài dự kiến.
- `UNKNOWN` tồn đọng lâu, chưa có reconciliation.
- Provider B không còn DKIM aligned hoặc domain verification hết hiệu lực.
- Hard bounce/complaint tăng trên một route.
- Outbox backlog vượt SLA.
- Một tenant sử dụng sai SMTP identity.
- Webhook delivery của provider ngừng đến.

Alert nên hỗ trợ câu hỏi “hỏng route nào, email logic nào, cần sửa cấu hình hay cần chờ”, không chỉ báo “mail service unavailable”.

## 23. Quy trình thêm provider mới

Một checklist triển khai thực tế:

### 23.1. Provision và bảo mật

- [ ] Tạo SMTP account theo nguyên tắc quyền tối thiểu.
- [ ] Xác minh SMTP host/port, TLS mode và AUTH.
- [ ] Lưu secret trong secret manager, không hardcode.
- [ ] Bật hostname verification/trust chain hợp lệ.
- [ ] Có socket timeouts và quota/concurrency config.
- [ ] Hạn chế nơi workload được phép kết nối tới provider.

### 23.2. Domain và deliverability

- [ ] Xác minh quyền dùng From domain.
- [ ] Cấu hình envelope sender/custom bounce domain theo provider.
- [ ] Cấu hình DKIM signing với domain aligned.
- [ ] Xác minh SPF/DKIM/DMARC bằng mailbox test.
- [ ] Đồng bộ suppression/unsubscribe/complaint policy.
- [ ] Phân biệt transaction vs marketing reputation/traffic.

### 23.3. Application integration

- [ ] Thêm profile vào registry, không hardcode trong business services.
- [ ] Khai báo tenant/category/region permissions.
- [ ] Kiểm thử router chọn đúng route.
- [ ] Kiểm thử submit và MIME qua SMTP sandbox.
- [ ] Test classifier cho các lỗi có thật của provider.
- [ ] Xác nhận retry/failover không gửi trùng ở case `UNKNOWN`.
- [ ] Lưu provider key ở mọi attempt.
- [ ] Nếu có webhook/API, mapping ID và event có bảo vệ.

### 23.4. Rollout

- [ ] Chạy smoke test với mailbox được phép.
- [ ] Triển khai traffic nhỏ có kiểm soát.
- [ ] Quan sát latency, 4xx/5xx, bounce, complaint.
- [ ] Xác nhận rate limit và quota.
- [ ] Có điều kiện tắt provider/rollback routing.
- [ ] Không failover toàn bộ backlog khi chưa biết trạng thái submission.
- [ ] Tài liệu hóa owner của profile, incident runbook và secret rotation.

## 24. Lỗi thiết kế thường gặp

### “Một interface chung nghĩa là mọi provider hoàn toàn giống nhau”

Không. Interface chung chỉ chứa semantics thật sự tương đương. Credential, bounce, quotas, webhook và idempotency có thể khác; abstraction phải phơi bày capability hoặc adapter-specific handling phù hợp.

### “SMTP AUTH thành công là gửi được bằng mọi From domain”

Không. Provider có thể chỉ chấp nhận verified sender; receiving MTA còn kiểm tra SPF/DKIM/DMARC. Phải xác minh domain authentication trên **mọi route dự kiến dùng**.

### “Có exception thì thử Provider B ngay”

Không. Nếu A đã nhận DATA nhưng app mất response, B có thể tạo duplicate. Outcome `UNKNOWN` cần reconciliation hoặc quyết định chấp nhận rủi ro được ghi nhận.

### “Chỉ cần thay host/username của singleton trước mỗi request”

Không. Cấu hình mutable có thể bị trộn giữa các thread và tenants. Dùng profiles ổn định, registry hoặc thiết kế lifecycle rõ ràng.

### “Dùng cùng RFC Message-ID ở A và B là SMTP tự dedupe”

Không. RFC Message-ID và custom message key không phải idempotency protocol được SMTP bảo đảm.

### “Provider deferred nghĩa là đổi provider”

Không. Sau SMTP accepted, provider có thể tự retry delivery. Deferred chưa có nghĩa submission thất bại.

### “Một outbox status là đủ”

Không hẳn. Cần attempt history với provider key và error category để biết đã gửi qua đâu, đã accepted hay unknown, có thể replay an toàn hay không.

### “Mọi provider cùng nhận một lượng load như nhau”

Không. Quota, reputation, region, category, SLA và sức khỏe thực tế khác nhau. Router phải dựa trên policy, không chỉ random.

### “Bật nhiều workers là tối ưu throughput”

Không. Tăng workers có thể vượt quota, tạo 4xx và retry storm. Rate limiter, concurrency limit, backlog metrics và benchmark quan trọng hơn số threads đơn thuần.

### “Chỉ cần unit test mock sender là đã test multi-provider”

Không. Unit test xác nhận policy/adapter logic, nhưng routing qua hai SMTP endpoints, TLS, partial failure và database outbox cần integration tests riêng.

## 25. Bài tập thực hành

### Bài 1 — Thiết kế port chung

Tạo `EmailCommand`, `MailSubmissionPort`, `SubmissionReceipt` và `SubmissionFailure`. Mô tả rõ vì sao receipt chỉ là SMTP submission accepted, không phải delivered.

### Bài 2 — Hai SMTP profiles

Cấu hình hai provider trong `application.yml`, một STARTTLS port 587 và một implicit TLS port 465. Tạo `ProviderRegistry` immutable và xác minh không thể chọn provider key không tồn tại.

### Bài 3 — Adapter dùng JavaMailSender

Viết adapter lấy sender từ registry, tạo `MimeMessage` mới, gắn message key và attempt ID. Unit test bằng Mockito, không gọi SMTP thật.

### Bài 4 — Router theo loại email

Định tuyến `TRANSACTIONAL` sang A, `MARKETING` sang B và `INTERNAL_ALERT` sang relay. Test mọi trường hợp bằng JUnit.

### Bài 5 — Quyền tenant

Một tenant chỉ được sử dụng sender profile riêng. Viết test chứng minh tenant khác không thể ép router chọn credential/account của tenant này.

### Bài 6 — Domain verification

Provider A có DKIM `d=example.com`, Provider B dùng `d=vendor.example`. Với Header From `receipts@example.com`, phân tích vì sao chuyển sang B có thể DMARC fail và cách cấu hình provider B hợp lệ.

### Bài 7 — Lỗi SMTP 451

Cho A trả một lỗi transient được xác định trước DATA. Kiểm tra retry policy có backoff và giới hạn lượt thử; nếu policy cho failover, xác nhận B chỉ được dùng khi đủ điều kiện.

### Bài 8 — Timeout sau DATA

Giả lập A đã có thể nhận DATA nhưng client timeout. Test job chuyển `UNKNOWN`, **B không được gọi**, và có reconciliation record.

### Bài 9 — Provider deferred

Sau khi A accepted, nhận webhook deferred. Test không tạo submission thứ hai qua B. Sau đó nhận delivered và cập nhật delivery status đúng.

### Bài 10 — Outbox attempts

Thiết kế SQL để lưu hai attempts cùng message key nhưng provider khác nhau. Xác nhận unique `(message_key, attempt_number)`, giữ nguyên lịch sử dù job hoàn tất.

### Bài 11 — Rate và concurrency

Giả sử A giới hạn thấp hơn B. Thiết kế dispatcher với concurrency/rate limit theo provider; giải thích vì sao semaphore trong từng pod chưa giới hạn toàn bộ cluster.

### Bài 12 — Secret rotation

Thay credential của provider A khi nhiều workers đang gửi. Đề xuất cách tạo sender/profile mới rồi chuyển traffic có kiểm soát, không mutate singleton.

### Bài 13 — SMTP integration với hai servers

Dùng hai SMTP test servers. Route email A vào endpoint A, B vào endpoint B; xác nhận từng server chỉ nhận message được định tuyến tới mình.

### Bài 14 — Suppression toàn hệ thống

Provider A đánh dấu hard bounce/complaint. Chứng minh router không cho marketing email chuyển sang B để né suppression nếu recipient không còn đủ điều kiện.

### Bài 15 — Provider HTTP API

Thêm một adapter HTTP Email API dưới cùng application port. Xác định những capability chỉ HTTP API có thể hỗ trợ như idempotency key, provider ID và status lookup; không áp đặt vào SMTP generic.

### Bài 16 — Webhook sai thứ tự

Giả lập một event `delivered` rồi event `deferred` cũ từ A đến muộn. Thiết kế event history, dedupe và state machine để không lùi trạng thái.

### Bài 17 — Khôi phục sự cố

A outage, B đã sẵn sàng domain verification, có 2.000 queued jobs và 30 `UNKNOWN`. Lập kế hoạch chuyển **những job chưa submit** tới B theo quota, giữ các UNKNOWN để reconcile thay vì gửi lại tất cả.

### Bài 18 — Quan sát hiệu năng

Thiết kế metric/dashboard tách A, B, internal relay: queue age, submit p95, 4xx/5xx, failover rate, unknown count và provider delivery events.

## 26. Tổng kết

**Abstraction chung cho nhiều SMTP provider** giúp Spring Framework Mail tách quyết định nghiệp vụ khỏi cấu hình, giao thức và đặc tính của nhà cung cấp. Nó không nhằm che mọi khác biệt mà nhằm **chuẩn hóa đúng phần chung và giữ lộ ra những khác biệt quyết định tính an toàn của việc gửi email**.

Các nguyên tắc quan trọng:

1. Business layer tạo **email logic** với message key; không trực tiếp thao tác `JavaMailSenderImpl` hoặc SMTP credentials.
2. `ProviderRouter` quyết định tuyến theo tenant, category, domain, region và policy; `ProviderRegistry` giữ những sender profiles đã cấu hình an toàn.
3. `MailSubmissionPort` chuẩn hóa submission outcome; adapter Spring dùng `JavaMailSender`, tạo `MimeMessage` riêng cho mỗi attempt.
4. **Tái sử dụng sender profiles nhưng không mutate singleton khi có concurrent sends**, cũng không chia sẻ `MimeMessage` mutable giữa các email.
5. Đừng nhầm `SMTP_ACCEPTED` với `DELIVERED`. Sau accepted, provider có thể đang tự retry delivery.
6. **Failover chỉ khi an toàn.** Timeout không rõ kết quả phải giữ `UNKNOWN` và reconciliation; gửi qua provider B ngay có thể tạo duplicate.
7. Mọi provider dự phòng đều phải được chuẩn bị **verified From, SPF/DKIM/DMARC alignment, suppression policy, TLS và quota** trước khi nhận traffic.
8. Outbox, idempotency, attempt history và provider-specific IDs giúp trace, retry và vận hành xuyên các tuyến.
9. Test policy/adapter bằng mock và in-memory MIME; test nhiều SMTP endpoints, TLS, database persistence và failure injection ở integration suite.
10. Đo lường theo provider, đặt rate/concurrency limits và có incident runbook; **không giả định thêm provider đồng nghĩa throughput hay deliverability sẽ tự tăng**.

Khi ranh giới được thiết kế đúng, bạn có thể thay đổi nhà cung cấp, thêm profile cho tenant hoặc mở tuyến dự phòng mà không phải viết lại mọi service nghiệp vụ, đồng thời vẫn bảo toàn kiểm soát về danh tính miền, trạng thái email và nguy cơ gửi trùng.
