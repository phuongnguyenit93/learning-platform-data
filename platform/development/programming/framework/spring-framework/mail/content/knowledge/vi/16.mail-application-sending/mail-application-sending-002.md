# Xây MailService với hợp đồng rõ ràng

Trong một ứng dụng Spring, nhiều nghiệp vụ có thể cần gửi email: xác nhận đăng ký, thông báo đơn hàng, đặt lại mật khẩu, gửi hóa đơn hoặc báo cáo. Nếu mỗi controller và service tự inject `JavaMailSender` rồi tự tạo `MimeMessage`, cấu hình SMTP, cách xử lý lỗi và quy tắc người nhận sẽ bị lặp lại ở nhiều nơi.

Một **MailService** tập trung hóa thao tác gửi mail và cung cấp một **hợp đồng (contract) rõ ràng** cho các thành phần gọi nó. Hợp đồng này phải trả lời được:

- Ứng dụng cần cung cấp dữ liệu nào để yêu cầu gửi?
- Ai chịu trách nhiệm chọn địa chỉ From và cấu hình SMTP?
- Nội dung text/HTML được biểu diễn ra sao?
- Khi method trả về bình thường, điều gì đã được bảo đảm?
- Khi gửi thất bại, service báo lỗi theo cách nào?
- Service có gửi đồng bộ hay chỉ tiếp nhận một job vào queue?
- Ai chịu trách nhiệm validation, retry, log và theo dõi trạng thái?

Một thiết kế tốt giúp tầng nghiệp vụ chỉ cần nói **“hãy gửi thông báo này cho người nhận này”**, còn chi tiết Spring Mail, Jakarta Mail và SMTP được giữ trong phần triển khai.

## 1. MailService nằm ở đâu trong ứng dụng?

Một cách tổ chức thường gặp:

~~~text
Controller / Event handler / Scheduler
                 |
                 v
       Application service
                 |
                 v
             MailService
          (application port)
                 |
                 v
        SmtpMailService
       (infrastructure adapter)
                 |
                 v
          JavaMailSender
                 |
                 v
           SMTP server
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Controller / event handler** | Nhận yêu cầu hoặc sự kiện và gọi use case phù hợp |
| **Application service** | Xác định khi nào cần gửi, chọn dữ liệu nghiệp vụ và người nhận |
| **MailService contract** | Định nghĩa dữ liệu đầu vào, hành vi và lỗi mà caller có thể dựa vào |
| **SmtpMailService** | Chuyển request thành MIME message và gọi Spring Mail |
| **JavaMailSender** | Gửi message qua transport đã được cấu hình |
| **SMTP provider** | Tiếp nhận thư, áp dụng chính sách gửi và tiếp tục chuyển thư |

MailService không nên tự truy vấn toàn bộ database để đoán nội dung, cũng không nên để controller biết SMTP host, password hay cách tạo MIME part. Tầng nghiệp vụ chuẩn bị dữ liệu cần gửi; adapter chịu trách nhiệm chuyển dữ liệu đó thành email.

### 1.1. Vì sao không gọi JavaMailSender trực tiếp ở mọi nơi?

Nếu nhiều lớp cùng gọi trực tiếp:

~~~java
@Service
class OrderService {
    private final JavaMailSender mailSender;
    // Tự tạo MimeMessage và cấu hình From/Subject/Body.
}

@Service
class AccountService {
    private final JavaMailSender mailSender;
    // Lặp lại cách tạo và gửi email.
}

@RestController
class SupportController {
    private final JavaMailSender mailSender;
    // Lại tự gửi mail từ controller.
}
~~~

Các vấn đề dễ xuất hiện:

- Mỗi nơi đặt From hoặc Reply-To khác nhau.
- Có nơi gửi HTML, nơi khác gửi text nhưng không có fallback.
- Cấu hình charset, timeout hoặc attachment không nhất quán.
- Lỗi SMTP bị bắt và xử lý theo những cách khác nhau.
- Unit test phải mock API hạ tầng ở nhiều tầng.
- Khi đổi từ SMTP sang một nhà cung cấp email qua HTTP API, phải sửa nhiều lớp nghiệp vụ.

Một MailService tập trung tạo một điểm để áp dụng chính sách chung và thay đổi cách gửi mà không buộc mọi caller biết chi tiết transport.

## 2. Hợp đồng rõ ràng phải mô tả hành vi, không chỉ tên method

Một interface chỉ có:

~~~java
public interface MailService {
    void send();
}
~~~

chưa phải hợp đồng hữu ích. Caller không biết gửi tới ai, nội dung nào, lỗi được biểu diễn thế nào hay thời điểm nào được xem là hoàn tất.

Hợp đồng cần mô tả ít nhất bốn nhóm:

1. **Input:** recipient, subject, body, loại nội dung và metadata cần thiết.
2. **Policy:** địa chỉ From, encoding, giới hạn người nhận, cách xử lý HTML và attachment.
3. **Completion:** method gửi đồng bộ hay tiếp nhận công việc bất đồng bộ.
4. **Failure:** lỗi validation, chuẩn bị MIME, xác thực SMTP, kết nối hoặc provider từ chối.

Ví dụ một hợp đồng đồng bộ:

~~~java
public interface MailService {
    /**
     * Gửi một email qua transport đã cấu hình.
     *
     * Khi method trả về bình thường, sender đã hoàn tất thao tác
     * gửi/nộp message theo contract của transport.
     * Điều đó không xác nhận thư đã tới Inbox hoặc đã được đọc.
     *
     * Ném MailServiceException nếu không thể chuẩn bị hoặc gửi message.
     */
    void send(OutgoingMail mail);
}
~~~

Caller có thể dựa vào quy tắc này để quyết định ghi nhận trạng thái, hiển thị lỗi hoặc thực hiện retry theo chính sách.

## 3. Chọn API cho MailService

Có nhiều mức abstraction. Không có một chữ ký duy nhất phù hợp mọi ứng dụng; điều quan trọng là API thể hiện đúng nhu cầu và không để chi tiết hạ tầng rò ra ngoài.

### 3.1. API nghiệp vụ chuyên biệt

Nếu ứng dụng có vài loại email cố định, có thể định nghĩa method theo use case:

~~~java
public interface OrderMailService {
    void sendOrderConfirmation(OrderConfirmationMailData data);
    void sendShippingUpdate(ShippingUpdateMailData data);
}
~~~

Ưu điểm:

- Caller không thể tùy ý gửi subject/body bất kỳ.
- Tên method diễn tả nghiệp vụ.
- Mỗi loại email có model dữ liệu riêng.
- Dễ gắn template, locale và quy tắc người nhận cho từng use case.

Nhược điểm là interface có thể tăng nhanh khi ứng dụng có nhiều loại email. Các method chuyên biệt cũng có thể dùng chung một thành phần gửi generic ở tầng dưới.

### 3.2. API gửi mail tổng quát

Một module cần gửi nhiều loại message có thể dùng:

~~~java
public interface MailService {
    void send(OutgoingMail mail);
}
~~~

`OutgoingMail` là một command có hợp đồng cụ thể. Nó không phải một chuỗi HTML tùy ý và cũng không chứa đối tượng `MimeMessage`. Caller cung cấp dữ liệu ở mức ứng dụng; phần triển khai chịu trách nhiệm tạo message.

Ưu điểm:

- Một implementation có thể phục vụ nhiều use case.
- Có thể dùng lại cơ chế đặt recipient, subject, body và encoding.
- Dễ thay thế SMTP adapter bằng provider adapter nếu giữ nguyên ngữ nghĩa.

Rủi ro là API tổng quát có thể trở thành một “cổng gửi bất kỳ nội dung nào” nếu không có validation và kiểm soát caller. Vì vậy, không nên mở endpoint công khai nhận nguyên `OutgoingMail` từ người dùng bên ngoài mà không có policy.

### 3.3. Kết hợp hai tầng

Trong ứng dụng lớn, cách kết hợp thường rõ ràng:

~~~text
OrderNotificationService
        |
        | OrderConfirmationMailData
        v
MailTemplateRenderer
        |
        | plain text + HTML
        v
MailService (generic application port)
        |
        v
SmtpMailService
        |
        v
JavaMailSender
~~~

Use case chuyên biệt quyết định **khi nào gửi và dữ liệu nào được phép gửi**. MailService tổng quát chỉ nhận một email đã được chuẩn bị. Cách này vừa giữ ngữ nghĩa nghiệp vụ, vừa tránh lặp code MIME/SMTP.

## 4. Thiết kế model đầu vào bất biến

Một request gửi mail nên là dữ liệu có cấu trúc, thay vì một danh sách tham số dài:

~~~java
public record MailBody(
        String plainText,
        String html) {
}

public record OutgoingMail(
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String replyTo,
        String subject,
        MailBody body,
        String correlationId) {
}
~~~

Ví dụ này mới mô tả hình dạng. Một hợp đồng thực tế nên kiểm tra dữ liệu ngay khi tạo object.

### 4.1. MailBody: quy định rõ nội dung được hỗ trợ

Một email giao dịch thường nên có plain text và có thể có HTML:

~~~java
import java.util.Objects;

public record MailBody(
        String plainText,
        String html) {

    public MailBody {
        if (plainText == null || plainText.isBlank()) {
            throw new IllegalArgumentException(
                    "plainText must not be blank");
        }

        if (html != null && html.isBlank()) {
            html = null;
        }
    }

    public boolean hasHtml() {
        return html != null;
    }
}
~~~

Hợp đồng này chọn quy tắc: **plain text luôn bắt buộc**, HTML là tùy chọn. Nếu có HTML, adapter gửi hai alternative; nếu không, adapter gửi plain text đơn giản. Điều đó giúp mọi email đều có fallback đọc được.

Nếu sản phẩm có trường hợp hợp lệ chỉ gửi HTML, có thể nới lỏng quy tắc này nhưng cần ghi rõ hành vi khi thiếu plain text. Đừng để một implementation tự sinh text bằng cách xóa thẻ HTML theo cách không kiểm soát rồi gọi đó là fallback tốt.

### 4.2. OutgoingMail: recipient và metadata

~~~java
import java.util.List;
import java.util.Objects;

public record OutgoingMail(
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String replyTo,
        String subject,
        MailBody body,
        String correlationId) {

    public OutgoingMail {
        to = immutableAddresses(to, "to");
        cc = immutableAddresses(cc, "cc");
        bcc = immutableAddresses(bcc, "bcc");

        if (to.isEmpty()) {
            throw new IllegalArgumentException(
                    "At least one To recipient is required");
        }

        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                    "subject must not be blank");
        }
        rejectHeaderBreaks(subject, "subject");

        if (replyTo != null) {
            requireNonBlank(replyTo, "replyTo");
            rejectHeaderBreaks(replyTo, "replyTo");
        }

        Objects.requireNonNull(body, "body");
    }

    private static List<String> immutableAddresses(
            List<String> addresses,
            String fieldName) {
        Objects.requireNonNull(addresses, fieldName);
        List<String> copy = List.copyOf(addresses);
        copy.forEach(address -> {
            requireNonBlank(address, fieldName + " address");
            rejectHeaderBreaks(address, fieldName + " address");
        });
        return copy;
    }

    private static void requireNonBlank(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
    }

    private static void rejectHeaderBreaks(String value, String name) {
        if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    name + " must not contain CR/LF");
        }
    }
}
~~~

Các quyết định trong ví dụ:

- `to` là bắt buộc và phải có ít nhất một địa chỉ.
- `cc` và `bcc` có thể là danh sách rỗng.
- `replyTo` có thể không có.
- `subject` bắt buộc và không được chứa CR/LF để tránh header injection.
- `body` phải tồn tại và tuân theo quy tắc plain-text fallback.
- `List.copyOf` tạo snapshot không cho sửa danh sách sau khi command được tạo.
- `correlationId` giúp liên kết log/tracing với nghiệp vụ; không phải secret hoặc bằng chứng idempotency.

Kiểm tra trên chỉ là **validation cơ bản**. Nó không chứng minh địa chỉ mailbox tồn tại, người nhận có quyền nhận nội dung hay domain được phép gửi. Những quy tắc đó thuộc tầng nghiệp vụ và chính sách mail.

### 4.3. Vì sao không đưa From vào request?

Với ứng dụng thông thường, địa chỉ `From` là chính sách của hệ thống:

~~~yaml
app:
  mail:
    from: no-reply@example.com
    reply-to: support@example.com
~~~

Nếu mọi caller được tự chọn `From`, một endpoint có thể bị lạm dụng để gửi mail giả danh người khác. Tốt hơn là adapter đọc From từ cấu hình đã được kiểm soát. Nếu có nhiều sender identity hợp lệ, hãy dùng một enum/value object hoặc policy được allowlist, không nhận địa chỉ tùy ý từ request công khai.

### 4.4. Vì sao không đưa JavaMailSender hoặc MimeMessage vào contract?

Không nên:

~~~java
public interface MailService {
    void send(MimeMessage message);
}
~~~

hoặc:

~~~java
public interface MailService {
    JavaMailSender sender();
}
~~~

Những chữ ký này làm caller phụ thuộc vào Jakarta Mail/Spring Mail. Khi đổi provider hoặc cách đóng gói nội dung, tầng nghiệp vụ cũng phải thay đổi. Contract nên diễn đạt **ý định gửi email**, không phải đối tượng nội bộ của thư viện.

## 5. Cài đặt MailService bằng JavaMailSender

Sau khi có contract và model, adapter SMTP chuyển request thành `MimeMessage`.

### 5.1. Interface

~~~java
public interface MailService {
    void send(OutgoingMail mail);
}
~~~

### 5.2. Implementation

~~~java
package com.example.mail.infrastructure;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class SmtpMailService implements MailService {
    private final JavaMailSender sender;
    private final String fromAddress;
    private final String defaultReplyTo;

    public SmtpMailService(
            JavaMailSender sender,
            @Value("${app.mail.from}") String fromAddress,
            @Value("${app.mail.reply-to:}") String defaultReplyTo) {
        this.sender = sender;
        this.fromAddress = fromAddress;
        this.defaultReplyTo = defaultReplyTo;
    }

    @Override
    public void send(OutgoingMail mail) {
        MimeMessage mime = sender.createMimeMessage();

        try {
            boolean multipart = mail.body().hasHtml();
            MimeMessageHelper helper = new MimeMessageHelper(
                    mime,
                    multipart,
                    StandardCharsets.UTF_8.name()
            );

            helper.setFrom(fromAddress);
            helper.setTo(mail.to().toArray(String[]::new));

            if (!mail.cc().isEmpty()) {
                helper.setCc(mail.cc().toArray(String[]::new));
            }
            if (!mail.bcc().isEmpty()) {
                helper.setBcc(mail.bcc().toArray(String[]::new));
            }

            String replyTo = mail.replyTo() != null
                    ? mail.replyTo()
                    : defaultReplyTo;
            if (replyTo != null && !replyTo.isBlank()) {
                helper.setReplyTo(replyTo);
            }

            helper.setSubject(mail.subject());

            if (mail.body().hasHtml()) {
                helper.setText(
                        mail.body().plainText(),
                        mail.body().html()
                );
            } else {
                helper.setText(mail.body().plainText());
            }
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Could not prepare MIME message",
                    mail.correlationId(),
                    ex
            );
        }

        try {
            sender.send(mime);
        } catch (MailException ex) {
            throw new MailSubmissionException(
                    "Mail transport could not submit the message",
                    mail.correlationId(),
                    ex
            );
        }
    }
}
~~~

Trong đoạn code:

1. `JavaMailSender` được inject qua constructor; đây là dependency hạ tầng.
2. `From` lấy từ cấu hình, không lấy tùy ý từ caller.
3. `To`, `Cc`, `Bcc` và `Reply-To` được đặt từ request đã kiểm tra.
4. `MimeMessageHelper` tạo plain text hoặc multipart alternative.
5. Charset UTF-8 giúp xử lý nội dung tiếng Việt.
6. Lỗi chuẩn bị MIME và lỗi gửi transport được chuyển thành các loại exception của MailService.

`MimeMessageHelper` có các method có thể ném `MessagingException`, vì vậy khối chuẩn bị được xử lý riêng. `JavaMailSender.send(...)` có thể ném `MailException` của Spring; lỗi này được phân loại thành lỗi submission.

Đây là ví dụ cho **Spring Boot 3.x / Spring Framework 6**, dùng namespace `jakarta.mail`. Ứng dụng thuộc thế hệ Spring cũ cần dùng API/package tương ứng với phiên bản đang chạy.

### 5.3. Đặt tên exception theo ý nghĩa

Có thể định nghĩa một nhóm exception:

~~~java
public abstract class MailServiceException extends RuntimeException {
    private final String correlationId;

    protected MailServiceException(
            String message,
            String correlationId,
            Throwable cause) {
        super(message, cause);
        this.correlationId = correlationId;
    }

    public String correlationId() {
        return correlationId;
    }
}
~~~

Lỗi chuẩn bị message:

~~~java
public final class MailPreparationException
        extends MailServiceException {

    public MailPreparationException(
            String message,
            String correlationId,
            Throwable cause) {
        super(message, correlationId, cause);
    }
}
~~~

Lỗi nộp thư:

~~~java
public final class MailSubmissionException
        extends MailServiceException {

    public MailSubmissionException(
            String message,
            String correlationId,
            Throwable cause) {
        super(message, correlationId, cause);
    }
}
~~~

Trong dự án Java, mỗi public class ở ví dụ này nên được đặt trong file riêng. Có thể bổ sung loại lỗi validation hoặc lỗi provider cụ thể nếu caller thật sự cần phân biệt; không cần tạo một exception class cho mọi nguyên nhân nhỏ.

## 6. Hợp đồng về thành công: gửi xong có nghĩa gì?

Một trong những phần quan trọng nhất của contract là định nghĩa **thành công**.

Với interface đồng bộ:

~~~java
mailService.send(mail);
~~~

nếu method trả về bình thường, điều đó thường có nghĩa:

- ứng dụng đã tạo message;
- Spring Mail đã hoàn tất lần gọi transport;
- transport không báo lỗi đồng bộ trong quá trình nộp thư.

Nó **không** chứng minh:

- email đã đến Inbox;
- thư không bị spam hoặc quarantine;
- mailbox còn tồn tại;
- người nhận đã mở hoặc đọc thư;
- attachment đã được tải xuống.

SMTP server có thể chấp nhận thư rồi tiếp tục xử lý, chuyển tiếp hoặc trả bounce sau đó. Nếu sản phẩm cần theo dõi delivery, phải có cơ chế provider event, DSN hoặc webhook riêng.

### 6.1. Không đặt tên trạng thái là DELIVERED quá sớm

Nếu service chỉ gọi `JavaMailSender`, trạng thái hợp lý có thể là:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `CREATED` | Yêu cầu gửi đã được tạo ở tầng ứng dụng |
| `SUBMITTING` | Đang thực hiện lần gửi |
| `SUBMITTED` | Transport hoàn tất thao tác nộp thư mà không báo lỗi |
| `SUBMISSION_FAILED` | Lần nộp thư báo lỗi |
| `DELIVERED` | Provider xác nhận đã giao theo sự kiện/contract của provider |
| `BOUNCED` | Provider báo thư bị trả lại |

Không nên dùng `DELIVERED` chỉ vì `send(...)` không ném exception. Cách đặt tên trạng thái chính xác giúp dashboard, retry và hỗ trợ khách hàng không đưa ra kết luận sai.

### 6.2. Nếu cần biết message ID?

`JavaMailSender.send(...)` trả về `void`. Một số provider có message ID riêng hoặc API tra cứu trạng thái, nhưng không thể giả định mọi SMTP server trả một ID thống nhất qua interface Spring Mail.

Nếu nghiệp vụ cần theo dõi, có thể:

- gắn correlation ID của ứng dụng vào log/job;
- cấu hình listener hoặc provider-specific integration để lấy ID khi được hỗ trợ;
- lưu mapping giữa application job ID và provider message ID;
- nhận webhook/DSN để cập nhật trạng thái sau gửi.

Không tự tạo một chuỗi UUID rồi gọi đó là SMTP message ID. ID do ứng dụng sinh có thể giúp truy vết, nhưng khác với ID được transport/provider cấp.

## 7. Hợp đồng về lỗi và retry

Caller cần biết lỗi nào được báo và ai quyết định retry. Một interface tốt không nên nuốt exception:

~~~java
public void send(OutgoingMail mail) {
    try {
        sender.send(mime);
    } catch (MailException ex) {
        log.warn("Mail submission failed", ex);
        // Không trả về bình thường nếu lần gửi đã thất bại.
        throw new MailSubmissionException(
                "Mail submission failed",
                mail.correlationId(),
                ex
        );
    }
}
~~~

Đây là ý tưởng; implementation thực tế cần tránh log hai lần cùng exception nếu tầng trên cũng log. Quan trọng là **không bắt lỗi rồi chỉ ghi log và tiếp tục như thể thành công**.

### 7.1. Phân loại lỗi

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Input không hợp lệ | Thiếu To, Subject rỗng, header chứa CR/LF | Từ chối request; sửa dữ liệu, không retry nguyên trạng |
| Chuẩn bị MIME | Lỗi tạo part, resource không đọc được | Kiểm tra nội dung/resource; chỉ thử lại nếu nguyên nhân có thể thay đổi |
| Authentication | Credentials sai hoặc hết hiệu lực | Sửa secret/quyền provider; retry liên tục không giải quyết được |
| Kết nối tạm thời | Timeout, server tạm ngừng | Có thể retry với backoff và giới hạn |
| Provider policy | Người gửi/domain không được phép hoặc nội dung bị từ chối | Cần sửa policy hoặc dữ liệu; không retry vô hạn |
| Kết quả không xác định | Mất kết nối sau khi truyền dữ liệu nhưng trước phản hồi cuối | Cân nhắc nguy cơ thư đã được nhận và có thể gửi trùng |

Không phải mọi `MailException` đều retryable. Cần xem exception cụ thể, root cause, trạng thái job và contract của provider.

### 7.2. Ai chịu trách nhiệm retry?

Với gửi đồng bộ trực tiếp, caller có thể quyết định hiển thị lỗi hoặc chuyển sang luồng xử lý khác. Với gửi giao dịch quan trọng, retry nên do một **job processor/queue** quản lý thay vì lặp vòng gọi send ngay trong request HTTP.

Một cách phân tầng:

~~~text
OrderService
    |
    v
MailJobPublisher
    |
    v
Queue / Outbox
    |
    v
MailWorker
    |
    v
MailService.send(...)
    |
    v
SMTP transport
~~~

Worker quyết định:

- đánh dấu job thành công sau khi transport hoàn tất;
- đưa lỗi tạm thời vào retry với backoff;
- đưa lỗi vĩnh viễn vào trạng thái cuối hoặc dead-letter queue;
- ghi lại số lần thử và nguyên nhân;
- giữ attachment/artifact nếu retry còn cần.

MailService vẫn có thể giữ contract đồng bộ ở bên trong worker. Điều này làm rõ khác biệt giữa **gửi email** và **tiếp nhận một công việc gửi email**.

## 8. Phân biệt send() và enqueue()

Một lỗi thiết kế thường gặp là một method tên `send(...)` thực ra chỉ đưa message vào queue rồi trả về. Caller nghĩ email đã được nộp cho SMTP, trong khi mới chỉ có job được lưu.

Nếu có queue, nên dùng contract khác:

~~~java
public interface MailJobPublisher {
    MailJobId enqueue(OutgoingMail mail);
}
~~~

Ví dụ ID:

~~~java
public record MailJobId(String value) {
}
~~~

Hai hành vi khác nhau:

| Method | Khi trả về bình thường | Lỗi có thể gặp |
| --- | --- | --- |
| `MailService.send(mail)` | Lần gọi transport đã hoàn tất theo contract sender | Chuẩn bị MIME, SMTP, provider |
| `MailJobPublisher.enqueue(mail)` | Job đã được queue/outbox tiếp nhận theo contract lưu trữ | Queue unavailable, DB failure, validation |

`enqueue` thành công không có nghĩa email đã được gửi. Job có thể nằm chờ, bị retry, bị hủy hoặc cuối cùng thất bại. API và trạng thái phải phản ánh sự khác biệt này.

### 8.1. Vì sao không chỉ thêm @Async vào send()?

Ví dụ:

~~~java
@Async
public void send(OutgoingMail mail) {
    sender.send(...);
}
~~~

Caller nhận được return ngay khi công việc được gửi sang executor (nếu việc dispatch thành công), không biết transport đã hoàn tất hay chưa. Nếu method trả về `void`, lỗi phát sinh trong thread bất đồng bộ cũng không thể được caller bắt theo cách thông thường.

`@Async` có thể hữu ích cho tác vụ nền, nhưng contract nên diễn đạt rõ:

~~~java
@Async
public CompletableFuture<MailSubmissionResult> sendAsync(
        OutgoingMail mail) {
    // ...
}
~~~

Ngay cả future cũng chỉ cho biết kết quả của task trong process; nó không thay thế durable queue, retry sau restart hay delivery webhook. Với email giao dịch, job/outbox thường dễ kiểm soát hơn một executor trong bộ nhớ.

## 9. Tách render template khỏi gửi mail

MailService không nhất thiết phải biết cách dựng HTML từ dữ liệu đơn hàng. Có thể tách một renderer:

~~~java
public interface MailContentRenderer {
    MailBody renderOrderConfirmation(
            OrderConfirmationMailData data,
            Locale locale);
}
~~~

Application service:

~~~java
public class OrderNotificationService {
    private final MailContentRenderer renderer;
    private final MailService mailService;

    public OrderNotificationService(
            MailContentRenderer renderer,
            MailService mailService) {
        this.renderer = renderer;
        this.mailService = mailService;
    }

    public void notifyOrderConfirmed(Order order, Customer customer) {
        OrderConfirmationMailData data =
                OrderConfirmationMailData.from(order, customer);

        MailBody body = renderer.renderOrderConfirmation(
                data,
                Locale.forLanguageTag("vi-VN")
        );

        OutgoingMail mail = new OutgoingMail(
                List.of(customer.email()),
                List.of(),
                List.of(),
                null,
                "Xác nhận đơn hàng " + order.publicReference(),
                body,
                "order-confirmed-" + order.id()
        );

        mailService.send(mail);
    }
}
~~~

Đây là ví dụ về luồng trách nhiệm:

- Order service biết đơn hàng nào vừa được xác nhận.
- Mapper tạo dữ liệu email đã chọn lọc.
- Renderer tạo plain text và HTML.
- MailService gửi nội dung đã render.

Các kiểu `Order`, `Customer` và `OrderConfirmationMailData` là model nghiệp vụ minh họa. Không nên để renderer tự truy vấn repository hoặc tự quyết định khách hàng nào được nhận thư.

### 9.1. Có thể dùng một interface MailService cho cả plain và HTML

Vì `MailBody` đã mô tả hai dạng nội dung, MailService không cần có method riêng như:

~~~java
sendPlainText(...);
sendHtml(...);
sendPlainAndHtml(...);
~~~

trừ khi mỗi loại có hành vi nghiệp vụ khác nhau. Một model body có plain text bắt buộc và HTML tùy chọn có thể diễn đạt đầy đủ ba trường hợp:

| Body | Kết quả |
| --- | --- |
| Chỉ có plain text | Gửi text/plain |
| Plain text + HTML | Gửi multipart/alternative |
| Plain text + HTML rỗng/null | Gửi plain text theo quy tắc chuẩn hóa |

Không nên dùng boolean như `isHtml` đi kèm một chuỗi body chung nếu nó khiến caller khó biết nội dung đang được hiểu là gì. Một kiểu dữ liệu có tên rõ ràng dễ đọc và mở rộng hơn.

## 10. Cấu hình SMTP thuộc về infrastructure

Một MailService contract không nên yêu cầu caller truyền host, port, username hoặc password mỗi lần gửi. Các giá trị đó thuộc cấu hình môi trường.

Ví dụ `application.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM:no-reply@example.com}
    reply-to: ${MAIL_REPLY_TO:support@example.com}
~~~

Spring Boot có thể auto-configure `JavaMailSender` khi starter và cấu hình mail phù hợp có mặt. `app.mail.from` và `app.mail.reply-to` là thuộc tính do ứng dụng định nghĩa; implementation đọc chúng để áp dụng policy.

### 10.1. Không đưa secret vào model hoặc log

Không thiết kế:

~~~java
new OutgoingMail(
        smtpUsername,
        smtpPassword,
        smtpHost,
        ...
);
~~~

Credentials được quản lý bởi môi trường chạy hoặc secret manager. Caller chỉ cung cấp dữ liệu thư. Điều này giúp rotate secret mà không sửa mọi call site hoặc payload đang chờ.

Không log:

- SMTP password, OAuth token hoặc API key;
- toàn bộ body có dữ liệu cá nhân;
- recipient list đầy đủ nếu không cần cho tracing;
- attachment bytes hoặc nội dung file.

Có thể log correlation ID, loại email, trạng thái và mã lỗi đã được làm sạch.

### 10.2. Nhiều sender identity

Nếu ứng dụng có nhiều địa chỉ From, chẳng hạn billing và support, không nên để caller truyền bất kỳ địa chỉ nào:

~~~java
public enum MailSenderProfile {
    GENERAL,
    BILLING,
    SUPPORT
}
~~~

Một policy map profile sang địa chỉ đã được cấu hình:

~~~java
public interface MailSenderIdentityResolver {
    String resolve(MailSenderProfile profile);
}
~~~

Caller chọn profile theo use case; adapter chỉ dùng địa chỉ nằm trong allowlist. Cần xác minh các địa chỉ/domain này được SMTP provider cho phép gửi.

## 11. Validation ở đúng tầng

Validation cần được chia theo ý nghĩa:

| Kiểm tra | Tầng phù hợp | Ví dụ |
| --- | --- | --- |
| Đơn hàng tồn tại và đã xác nhận | Domain/application | Không gửi mail xác nhận cho đơn chưa hợp lệ |
| Người dùng có quyền nhận thông báo | Application/security policy | Không cho client gửi tới địa chỉ tùy ý |
| Có ít nhất một To | Model/contract | `OutgoingMail` constructor |
| Subject không chứa CR/LF | Model/contract | Chặn header injection |
| Địa chỉ có cú pháp phù hợp | Boundary/adapter hoặc value object | Parse địa chỉ trước khi tạo MIME |
| From thuộc sender identity được phép | Configuration/policy | Không giả danh địa chỉ tùy ý |
| Link dùng host được phép | Application/renderer | Không nhận URL ngoài tùy ý |
| SMTP credentials hợp lệ | Infrastructure/runtime | Secret manager và provider |

Không nên gom tất cả vào một method khổng lồ. Ví dụ, kiểm tra người dùng có quyền nhận hóa đơn là quy tắc nghiệp vụ; kiểm tra MIME helper có tạo được header không là chi tiết hạ tầng.

### 11.1. Kiểm tra địa chỉ email không xác nhận mailbox tồn tại

Một chuỗi có cú pháp hợp lệ không chứng minh:

- domain có nhận email;
- mailbox tồn tại;
- người dùng kiểm soát mailbox;
- server đích sẽ chấp nhận thư.

Có thể dùng parser phù hợp để kiểm tra cú pháp, nhưng xác nhận địa chỉ tài khoản thường cần quy trình verification. Đừng gọi regex đơn giản là “xác minh email” và cũng đừng gửi thử thư để kiểm tra mọi địa chỉ trước khi nghiệp vụ cho phép.

### 11.2. Chống lạm dụng MailService

Nếu MailService được gọi từ API, cần:

- xác thực caller;
- kiểm tra recipient có liên quan tới tài khoản/giao dịch;
- giới hạn tần suất;
- giới hạn số recipient và kích thước nội dung;
- kiểm soát From/Reply-To;
- tránh cho người dùng truyền raw HTML hoặc header;
- áp dụng chính sách chống spam và audit phù hợp.

Một MailService tổng quát rất hữu ích ở bên trong ứng dụng nhưng không nên biến thành một open relay qua REST API.

## 12. Kiểm thử MailService

Hợp đồng rõ ràng giúp unit test không cần kết nối SMTP thật. Có thể mock `JavaMailSender` và xác nhận adapter tạo đúng MIME message.

### 12.1. Test validation của request

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class OutgoingMailTest {
    @Test
    void rejectsMailWithoutToRecipient() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OutgoingMail(
                        List.of(),
                        List.of(),
                        List.of(),
                        null,
                        "Subject",
                        new MailBody("Body", null),
                        "correlation-1"
                )
        );
    }

    @Test
    void rejectsLineBreakInSubject() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OutgoingMail(
                        List.of("alice@example.net"),
                        List.of(),
                        List.of(),
                        null,
                        "Hello\r\nBcc: victim@example.net",
                        new MailBody("Body", null),
                        "correlation-2"
                )
        );
    }
}
~~~

Test này kiểm tra quy tắc đầu vào ở cấp model; không cần Spring context hoặc SMTP.

### 12.2. Test adapter với JavaMailSender mock

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.internet.MimeMessage;
import jakarta.mail.Session;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class SmtpMailServiceTest {
    @Test
    void createsMessageWithExpectedHeaders() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        MimeMessage mime = new MimeMessage(
                Session.getInstance(new Properties()));
        when(sender.createMimeMessage()).thenReturn(mime);

        MailService service =
                new SmtpMailService(sender, "no-reply@example.com", "");

        OutgoingMail request = new OutgoingMail(
                List.of("alice@example.net"),
                List.of("team@example.com"),
                List.of(),
                null,
                "Thông báo A123",
                new MailBody("Đơn hàng đã xác nhận.", null),
                "order-A123"
        );

        service.send(request);

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);
        verify(sender).send(captor.capture());

        MimeMessage sent = captor.getValue();
        assertEquals("Thông báo A123", sent.getSubject());
        assertEquals(
                "alice@example.net",
                sent.getRecipients(
                        jakarta.mail.Message.RecipientType.TO)[0].toString()
        );
        assertEquals(
                "team@example.com",
                sent.getRecipients(
                        jakarta.mail.Message.RecipientType.CC)[0].toString()
        );
    }
}
~~~

Đây là ví dụ minh họa. Constructor của `SmtpMailService` và các import phải khớp implementation trong project; test có thể dùng helper để parse địa chỉ nếu muốn so sánh chính xác. Vì sender được mock, test này xác nhận message được dựng và chuyển cho sender, không chứng minh SMTP thực sự chấp nhận thư.

### 12.3. Test lỗi submission

~~~java
doThrow(new MailSendException("SMTP unavailable"))
        .when(sender)
        .send(any(MimeMessage.class));

assertThrows(
        MailSubmissionException.class,
        () -> service.send(request)
);
~~~

Test xác nhận adapter không nuốt lỗi và caller nhìn thấy exception theo contract của ứng dụng.

### 12.4. Integration test bằng SMTP giả lập

Để kiểm tra kết nối và MIME thực tế, có thể dùng Mailpit hoặc GreenMail trong môi trường test:

1. Khởi động SMTP test server.
2. Cấu hình ứng dụng trỏ tới host/port test.
3. Gọi MailService bằng request mẫu.
4. Kiểm tra server test nhận được message.
5. Xem From, To, Cc, Subject, charset, plain text, HTML và attachment.
6. Kiểm tra lỗi khi server dừng hoặc credentials sai.

Không dùng SMTP production trong unit test; test không nên gửi thư thật tới khách hàng.

## 13. Ghi log, tracing và quan sát hoạt động

Một MailService được dùng ở nhiều nơi cần khả năng truy vết mà không ghi lộ nội dung.

Thông tin có thể hữu ích:

~~~text
event=mail_submission
correlationId=order-confirmed-A123
mailType=ORDER_CONFIRMATION
transport=smtp
result=SUBMITTED
durationMs=342
~~~

Khi thất bại:

~~~text
event=mail_submission
correlationId=order-confirmed-A123
result=FAILED
exceptionType=MailSendException
retryableCandidate=true
~~~

`retryableCandidate` chỉ nên là phân loại sơ bộ dựa trên exception/root cause, không phải khẳng định mọi lỗi thuộc nhóm đó đều được retry.

### 13.1. Không dùng correlation ID như idempotency key một cách ngầm định

Correlation ID giúp liên kết các log của cùng một nghiệp vụ. Nó không tự ngăn gửi hai email. Để chống job trùng, cần:

- một ID sự kiện/job ổn định;
- unique constraint hoặc idempotency store nếu cần;
- trạng thái xử lý được lưu bền vững;
- quy tắc retry và xử lý kết quả không xác định.

Nếu một order event được phát hai lần, MailService generic không thể tự biết đó là cùng một thông báo trừ khi contract có business key và tầng điều phối thực hiện deduplication.

### 13.2. Metric cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| `mail_send_attempts_total` | Số lần thử gửi |
| `mail_submission_success_total` | Số lần transport hoàn tất không lỗi |
| `mail_submission_failures_total` | Số lần gửi báo lỗi |
| `mail_submission_duration_seconds` | Thời gian thực hiện thao tác gửi |
| `mail_queue_depth` | Số job đang chờ nếu có queue |
| `mail_retry_total` | Số lần retry |
| `mail_bounce_total` | Số bounce nhận từ provider nếu có tích hợp |

Không dùng địa chỉ email, subject hoặc correlation ID riêng lẻ làm label metric vì cardinality có thể tăng không giới hạn. Metric nên gắn nhãn theo loại mail, provider hoặc kết quả ở mức có kiểm soát.

## 14. Cấu trúc package tham khảo

Một module nhỏ có thể tổ chức:

~~~text
com.example.mail
  application/
    MailService.java
    OutgoingMail.java
    MailBody.java
    MailServiceException.java
    MailPreparationException.java
    MailSubmissionException.java
  infrastructure/
    SmtpMailService.java
    MailConfiguration.java
  template/
    MailContentRenderer.java
    ThymeleafMailContentRenderer.java
  notification/
    OrderNotificationService.java
    OrderConfirmationMailData.java
~~~

Tên package có thể khác theo kiến trúc. Điều cần giữ là:

- Contract và model ở vị trí caller có thể phụ thuộc mà không cần biết SMTP implementation.
- Adapter Spring Mail nằm trong infrastructure.
- Template renderer chịu trách nhiệm tạo body, không gửi SMTP.
- Use case nghiệp vụ quyết định lúc nào và cho ai gửi.

Với một ứng dụng nhỏ, không cần tạo quá nhiều package/interface. Có thể bắt đầu bằng một service cụ thể rồi tách contract khi có nhiều caller, cần test độc lập hoặc có khả năng thay transport.

## 15. Những anti-pattern cần tránh

| Anti-pattern | Vấn đề | Thiết kế tốt hơn |
| --- | --- | --- |
| Controller gọi `JavaMailSender` trực tiếp | HTTP layer phụ thuộc hạ tầng mail | Controller gọi application use case |
| `MailService.send(to, subject, body)` với danh sách tham số dài | Khó mở rộng và dễ nhầm thứ tự | Dùng request model có tên field |
| Truyền `MimeMessage` qua interface nghiệp vụ | Rò rỉ Jakarta Mail/Spring Mail | Dùng model ở cấp ứng dụng |
| Cho caller tự đặt From tùy ý | Có thể giả danh sender | From từ config hoặc sender profile allowlist |
| Bắt `MailException` rồi chỉ log | Caller tưởng gửi thành công | Ném exception theo contract |
| Gọi `send` nhưng thực tế chỉ enqueue | Ngữ nghĩa hoàn tất không rõ | Dùng method `enqueue` riêng |
| Dùng `@Async void` mà không quan sát lỗi | Caller không biết kết quả task | Future hoặc durable job contract |
| MailService tự truy vấn entity tùy ý | Trộn nghiệp vụ và hạ tầng | Caller chuẩn bị dữ liệu |
| Truyền toàn bộ entity vào template | Lộ trường, lazy loading | DTO/model riêng cho email |
| Dùng một object message mutable giữa nhiều thread | Race condition, sai recipient/body | Request immutable và message mới mỗi lần |
| Retry mọi lỗi | Lặp lỗi credentials/policy, có thể gửi trùng | Phân loại lỗi và backoff có giới hạn |
| Gọi trạng thái gửi là DELIVERED | Nhầm SMTP submission với Inbox delivery | Dùng SUBMITTED; delivery dựa vào provider event |
| Log toàn bộ body/recipient | Rò rỉ dữ liệu cá nhân | Log ID, loại thư và trạng thái tối thiểu |

## 16. Mở rộng contract khi có attachment

Nếu MailService cần hỗ trợ file đính kèm, không nên vội thêm một `List<File>` vào request rồi giữ đường dẫn local tùy ý. Cần định nghĩa:

- tên hiển thị;
- content type;
- nguồn bytes/resource;
- giới hạn kích thước;
- quyền sở hữu và vòng đời resource;
- xử lý cleanup khi gửi xong hoặc thất bại;
- giữ artifact ra sao khi job cần retry.

Ví dụ một model đơn giản cho attachment bytes:

~~~java
public record MailAttachment(
        String fileName,
        String contentType,
        byte[] content) {

    public MailAttachment {
        Objects.requireNonNull(fileName, "fileName");
        Objects.requireNonNull(contentType, "contentType");
        Objects.requireNonNull(content, "content");
        content = content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
~~~

Defensive copy giúp caller không sửa bytes sau khi request được tạo. Tuy nhiên, kiểu này giữ toàn bộ file trong heap; với file lớn hoặc gửi bất đồng bộ, nên dùng artifact storage có key/version và quyền truy cập rõ ràng.

Không để một request model giữ `InputStream` mở qua queue hoặc serialize sang JSON. Stream có vòng đời và trạng thái đọc; nó không phải payload bất biến phù hợp cho công việc chờ xử lý.

## 17. Khi nào nên tách nhiều interface?

Một service tổng quát có thể đủ cho module nhỏ. Khi yêu cầu tăng, có thể tách:

~~~java
public interface MailService {
    void send(OutgoingMail mail);
}

public interface MailJobPublisher {
    MailJobId enqueue(OutgoingMail mail);
}

public interface MailContentRenderer {
    MailBody render(
            String templateId,
            Object model,
            Locale locale);
}
~~~

Nhưng không nên tạo interface chỉ để mỗi class có một method mà không có ranh giới hữu ích. Một tiêu chí tốt là **caller cần phụ thuộc vào khả năng nào?**

- Caller gửi ngay: phụ thuộc `MailService`.
- Caller chỉ tạo job nền: phụ thuộc `MailJobPublisher`.
- Use case cần dựng nội dung: phụ thuộc `MailContentRenderer`.
- Worker gửi job: phụ thuộc `MailService` và artifact provider nếu cần.

Việc tách interface giúp test và thay adapter độc lập; quá nhiều lớp không có contract rõ ràng chỉ làm luồng gọi khó hiểu.

## 18. Tình huống tổng hợp: gửi xác nhận đơn hàng

Giả sử một đơn hàng được xác nhận. Tầng nghiệp vụ có dữ liệu:

~~~text
orderNumber = A123
customerEmail = alice@example.net
customerName = Nguyễn An
total = 220000 VND
~~~

Luồng đồng bộ:

1. `OrderService` hoàn tất quy tắc xác nhận đơn.
2. `OrderNotificationService` tạo model nội dung chỉ chứa dữ liệu cần gửi.
3. `MailContentRenderer` tạo plain text và HTML từ model.
4. `OutgoingMail` đóng gói To, Subject, Body và correlation ID.
5. `MailService.send(...)` được gọi.
6. `SmtpMailService` tạo MIME message và dùng `JavaMailSender`.
7. Nếu method trả về bình thường, tầng ứng dụng ghi nhận **SUBMITTED** theo contract; nếu có exception, phân loại lỗi.

~~~mermaid
sequenceDiagram
    participant O as OrderService
    participant N as OrderNotificationService
    participant R as MailContentRenderer
    participant M as MailService
    participant S as JavaMailSender
    participant P as SMTP provider

    O->>N: orderConfirmed(order)
    N->>R: render(model, locale)
    R-->>N: plainText + html
    N->>M: send(OutgoingMail)
    M->>S: create MimeMessage
    M->>S: send(message)
    S->>P: SMTP submission
    P-->>S: response
    S-->>M: return / MailException
    M-->>N: normal return / MailServiceException
~~~

Nếu sản phẩm không muốn request HTTP phải đợi SMTP, use case có thể ghi outbox/job rồi trả về trạng thái **ACCEPTED_FOR_PROCESSING** cùng job ID. Worker thực hiện cùng contract gửi đồng bộ ở bước sau. Không dùng cùng một từ “sent” cho hai mốc khác nhau.

## 19. Checklist hợp đồng trước khi triển khai

Trước khi viết implementation, hãy ghi rõ:

| Câu hỏi | Quyết định cần có |
| --- | --- |
| Caller gửi gì? | Request model có recipient, subject, body và metadata |
| Body có định dạng nào? | Plain text bắt buộc, HTML tùy chọn hay quy tắc khác |
| From do ai chọn? | Cấu hình hoặc sender identity policy |
| Có hỗ trợ To/Cc/Bcc/Reply-To không? | Quy tắc rõ và giới hạn số người nhận |
| Method đồng bộ hay bất đồng bộ? | `send` hoàn tất transport hay `enqueue` tiếp nhận job |
| Thành công có nghĩa gì? | Submission hoàn tất, không mặc định delivery |
| Lỗi được báo thế nào? | Validation, preparation, submission và retry policy |
| Ai quyết định retry? | Caller/job processor; không retry mù mọi exception |
| Ai tạo nội dung? | Renderer nhận model đã chuẩn bị |
| Ai sở hữu attachment? | Resource lifecycle và cleanup rõ ràng |
| Log lưu gì? | Correlation ID, loại thư, kết quả; tránh PII/secret |
| Test ở đâu? | Model, adapter mock và SMTP integration test |

## 20. Những điều cần nhớ

- **MailService là một hợp đồng ứng dụng**, không phải nơi để mọi caller truy cập trực tiếp SMTP.
- Dùng request model có tên field rõ ràng thay cho một method với nhiều tham số khó đọc.
- Giữ request bất biến để tránh thay đổi recipient/body sau khi gửi sang thread hoặc queue khác.
- From và thông tin SMTP nên do cấu hình/policy kiểm soát.
- Tách renderer/template khỏi thao tác gửi để test và bảo trì độc lập.
- Với email HTML, nên có plain-text alternative và dùng MIME đúng cách.
- Method `send` đồng bộ chỉ báo transport hoàn tất thao tác nộp thư; không khẳng định Inbox delivery.
- Nếu chỉ enqueue, hãy đặt tên và trả job ID để caller hiểu công việc mới được tiếp nhận.
- Không nuốt exception; phân loại lỗi và để tầng phù hợp quyết định retry.
- Không log secret hoặc toàn bộ nội dung email.

Một MailService tốt không cần có hàng chục method. Nó cần một **hợp đồng đủ rõ để caller biết phải cung cấp gì, có thể mong đợi điều gì và xử lý thất bại ra sao**. Khi contract tách biệt khỏi Spring Mail implementation, ứng dụng có thể thay đổi SMTP provider, cách render template hoặc cách thực hiện job nền mà không buộc toàn bộ nghiệp vụ thay đổi theo.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `MailSender`, `JavaMailSender` và `MimeMessageHelper`.
- **Spring Boot Reference — Sending Email:** starter mail, `JavaMailSender` auto-configuration và `spring.mail.*`.
- **Jakarta Mail API:** `MimeMessage`, `Message`, `Multipart` và các ngoại lệ mail.
- **Spring Framework — Task Execution and Scheduling:** executor và `@Async`.
- **Java API — Records, `List.copyOf` và immutable value types:** thiết kế request model ổn định.
- **RFC 5321 — Simple Mail Transfer Protocol:** thao tác SMTP submission và phản hồi từ server.
- **RFC 2045–2049 — MIME:** plain text, HTML, multipart và attachment.
