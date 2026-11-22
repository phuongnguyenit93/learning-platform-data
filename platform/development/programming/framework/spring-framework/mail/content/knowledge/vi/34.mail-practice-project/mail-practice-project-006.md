# Kiểm thử message bằng mock JavaMailSender — dự án thực hành Spring Framework Mail

## 1. Mục tiêu của bài thực hành

Trong dự án Spring Framework Mail, logic gửi email thường nằm giữa nghiệp vụ và hệ thống SMTP. Khi một giao dịch hoàn tất, service phải tạo đúng message: địa chỉ nhận, địa chỉ gửi, tiêu đề, nội dung, loại MIME và những điều kiện được phép gửi. **Mock `JavaMailSender`** cho phép kiểm thử những quyết định này nhanh, có thể lặp lại và **không gửi email ra Internet**.

Sau bài thực hành, bạn sẽ:

1. Tổ chức một project Spring Boot dùng `spring-boot-starter-mail`, JUnit 5 và Mockito.
2. Viết service gửi `SimpleMailMessage` và một service gửi `MimeMessage` với plain text, HTML và tệp đính kèm.
3. Thay `JavaMailSender` bằng mock trong unit test; không cần SMTP credentials.
4. Dùng `verify`, `times`, `never`, `ArgumentCaptor` và `verifyNoInteractions` để kiểm tra lời gọi và nội dung.
5. Tạo `MimeMessage` **thật** với Jakarta Mail trong test nhưng vẫn mock phần gửi, rồi đọc cấu trúc MIME để kiểm tra.
6. Mô phỏng `MailException`, kiểm tra nhánh thất bại và tránh đánh dấu message đã giao thành công khi chưa có bằng chứng.
7. Hiểu khi nào mock đủ, khi nào cần test server SMTP hoặc nhà cung cấp thật.

**Kết quả cần đạt:** Một bộ unit test không phụ thuộc network; mỗi assertion chứng minh được một hành vi cụ thể của application, không tự tuyên bố đã kiểm chứng deliverability.

> Giới hạn bằng chứng: `verify(sender).send(message)` chứng minh một lời gọi tới mock. Nó **không** chứng minh SMTP relay đã nhận, mailbox tồn tại, email vào Inbox hoặc người nhận đã đọc. Đây là bài thực hành về **message composition và orchestration**, không phải phép đo tỉ lệ thư giao tới Inbox.

## 2. Bối cảnh dự án

Giả sử ứng dụng thương mại điện tử cần gửi biên nhận khi đơn hàng đã được xử lý. Với mỗi yêu cầu, service cần:

- Chỉ tạo message khi recipient và order ID hợp lệ.
- Hỏi một chính sách nghiệp vụ xem có được gửi email giao dịch tới recipient không.
- Gửi từ `billing@example.test`, có `Reply-To` là `support@example.test`.
- Tiêu đề chứa mã đơn hàng; body chứa lời xác nhận.
- Khi policy từ chối, **không gọi sender**.
- Nếu sender ném lỗi, **không nuốt lỗi rồi báo thành công**.

Một yêu cầu khác cần gửi hóa đơn có hai phiên bản plain text/HTML cùng attachment. Ở đó ta sẽ dùng `MimeMessageHelper`.

### Sơ đồ các thành phần

~~~mermaid
flowchart LR
    A["Business event / API"] --> B["ReceiptMailService"]
    B --> C["RecipientPolicy"]
    B --> D["JavaMailSender"]
    D --> E["SMTP relay"]
    T["JUnit + Mockito"] -. "mock policy" .-> C
    T -. "mock sender" .-> D
~~~

Trong unit test, D bị thay bằng Mockito mock nên **mũi tên D → E không thực sự diễn ra**. Đây là chủ đích: test tập trung vào hành vi của service.

## 3. Công cụ và phiên bản

Các ví dụ sử dụng:

| Thành phần | Vai trò |
| --- | --- |
| Java 17 trở lên | Records, `String.isBlank()`, Java Time |
| Spring Boot tương thích với Jakarta Mail | Dependency injection và mail starter |
| Spring Framework Mail | `JavaMailSender`, `SimpleMailMessage`, `MimeMessageHelper` |
| Jakarta Mail | `MimeMessage`, `Session`, `Multipart`, `Part` |
| JUnit Jupiter (JUnit 5) | Viết các test case |
| Mockito + Mockito JUnit Jupiter | Tạo mock, inject mock, verify/capture |
| Gradle hoặc Maven | Quản lý dependencies và chạy test |

Ví dụ đặt trên Spring Framework 6+/Spring Boot 3+ với namespace `jakarta.mail`. Nếu project còn dùng một thế hệ cũ với `javax.mail`, phải chọn đúng dependency/namespace của toàn project; **không trộn `javax.mail.MimeMessage` với `jakarta.mail.internet.MimeMessage`**.

### Gradle dependencies

Nếu khởi tạo project từ Spring Initializr, chọn **Spring Boot**, **Java**, **Spring Boot Starter Mail**, **Spring Boot Starter Test**. Trong `build.gradle` sử dụng dependency management của Spring Boot đã chọn:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.mockito:mockito-junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ở một số phiên bản Spring Boot, `spring-boot-starter-test` đã bao gồm Mockito/JUnit Jupiter; khai báo rõ `mockito-junit-jupiter` giúp ý định dễ đọc. Để dependency management quản lý version tương thích, tránh tự trộn những version Mockito/Jakarta Mail khác nhau.

### Maven dependencies

Nếu dùng Maven và Spring Boot parent/BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đoạn XML là phần `dependencies`, không phải toàn bộ `pom.xml`. Nếu project không sử dụng Spring Boot parent/BOM, phải quản lý versions tương thích.

### Không cấu hình SMTP thật cho unit test

Bài test Mockito tạo `JavaMailSender` giả, nên không cần:

~~~text
spring.mail.host
spring.mail.port
spring.mail.username
spring.mail.password
~~~

Không dùng tài khoản Gmail/corporate SMTP, mật khẩu hoặc recipient thật để chạy các test này. Đó vừa không cần thiết, vừa làm unit test chậm, phụ thuộc mạng và có thể gửi nhầm email.

## 4. Cấu trúc project tham khảo

~~~text
src/
  main/
    java/com/example/mail/
      RecipientPolicy.java
      ReceiptMailService.java
      HtmlReceiptMailService.java
  test/
    java/com/example/mail/
      ReceiptMailServiceTest.java
      ReceiptMailServiceFailureTest.java
      HtmlReceiptMailServiceTest.java
      MailTestSupport.java
~~~

Các tệp ở đây là **cấu trúc mẫu để bạn tự thực hành**. Không cần tạo một controller thật hoặc khởi động toàn bộ Spring context để unit test các service: Mockito có thể khởi tạo object bằng constructor.

## 5. Tạo interface RecipientPolicy

Đầu tiên, tách quyết định “được gửi email giao dịch hay không” khỏi transport.

**`src/main/java/com/example/mail/RecipientPolicy.java`**

~~~java
package com.example.mail;

public interface RecipientPolicy {
    boolean canReceiveTransactionalMail(String recipient);
}
~~~

Interface này là seam để mock trong test. Trong ứng dụng thật, implementation có thể kiểm tra account status, suppression theo category, quyền truy cập và chính sách nghiệp vụ. **Không suy ra rằng marketing unsubscribe tự động chặn mọi email giao dịch bắt buộc**; mỗi category cần rule phù hợp.

### Vì sao không đặt chính sách vào JavaMailSender?

`JavaMailSender` không biết order có hợp lệ, recipient có thuộc tenant hoặc user đã unsubscribe loại mail nào. Những quyết định ấy thuộc tầng nghiệp vụ, có thể kiểm thử độc lập. Mock sender không thay thế kiểm tra quyền/consent.

## 6. Viết service dùng SimpleMailMessage

**`src/main/java/com/example/mail/ReceiptMailService.java`**

~~~java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class ReceiptMailService {

    private final JavaMailSender mailSender;
    private final RecipientPolicy recipientPolicy;

    public ReceiptMailService(
            JavaMailSender mailSender,
            RecipientPolicy recipientPolicy) {
        this.mailSender = mailSender;
        this.recipientPolicy = recipientPolicy;
    }

    public void sendReceipt(String recipient, String orderId) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient must not be blank");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "Order ID must not be blank");
        }

        if (!recipientPolicy.canReceiveTransactionalMail(recipient)) {
            return;
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("billing@example.test");
        message.setReplyTo("support@example.test");
        message.setTo(recipient);
        message.setSubject("Receipt for order " + orderId);
        message.setText(
                "Your order " + orderId + " has been recorded.");

        mailSender.send(message);
    }
}
~~~

### Giải thích luồng

1. Constructor injection nhận hai dependency.
2. Input rỗng gây `IllegalArgumentException`, không gọi policy và sender.
3. Recipient bị policy từ chối → kết thúc trước khi dựng message.
4. Nếu được phép, code tạo `SimpleMailMessage` với những trường cần kiểm tra.
5. Gọi `mailSender.send(message)`; đó là **transport boundary**.

Trong môi trường production, `billing@example.test` phải được thay bằng địa chỉ From/domain được nhà cung cấp cho phép; `.test` chỉ dùng làm dữ liệu ví dụ. Service cũng cần authentication/authorization, template/version, error policy và outbox nếu yêu cầu bảo đảm gửi sau commit; những thành phần đó không cần thiết để học kỹ thuật mock message.

### Không nuốt exception để giả thành công

Ví dụ cố tình **không** viết:

~~~java
try {
    mailSender.send(message);
} catch (Exception ignored) {
    System.out.println("Email delivered");
}
~~~

Nếu transport lỗi, việc báo “delivered” hoàn toàn không có căn cứ. Với mô hình outbox, dispatcher có thể bắt `MailException` rồi lưu `RETRY_PENDING`, `FAILED_PERMANENT` hoặc `SUBMISSION_UNKNOWN` theo bằng chứng; không thể dùng một `boolean sent` cho mọi trạng thái.

## 7. Unit test đầu tiên với MockitoExtension

**`src/test/java/com/example/mail/ReceiptMailServiceTest.java`**

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class ReceiptMailServiceTest {

    @Mock
    JavaMailSender mailSender;

    @Mock
    RecipientPolicy recipientPolicy;

    @InjectMocks
    ReceiptMailService service;

    @Captor
    ArgumentCaptor<SimpleMailMessage> messageCaptor;

    @Test
    void createsExpectedReceiptAndInvokesMailSenderOnce() {
        String to = "buyer@example.test";
        when(recipientPolicy.canReceiveTransactionalMail(to))
                .thenReturn(true);

        service.sendReceipt(to, "order-184");

        verify(mailSender).send(messageCaptor.capture());
        verifyNoMoreInteractions(mailSender);

        SimpleMailMessage actual = messageCaptor.getValue();
        assertEquals("billing@example.test", actual.getFrom());
        assertEquals("support@example.test", actual.getReplyTo());
        assertEquals(1, actual.getTo().length);
        assertEquals(to, actual.getTo()[0]);
        assertEquals(
                "Receipt for order order-184",
                actual.getSubject());
        assertEquals(
                "Your order order-184 has been recorded.",
                actual.getText());
    }
}
~~~

### Ý nghĩa của annotation

| Annotation | Vai trò |
| --- | --- |
| `@ExtendWith(MockitoExtension.class)` | Khởi tạo và quản lý Mockito mocks trong JUnit 5 |
| `@Mock` | Tạo đối tượng giả cho dependency |
| `@InjectMocks` | Đưa mocks vào constructor/field thích hợp của service |
| `@Captor` | Khởi tạo `ArgumentCaptor` |
| `@Test` | Đánh dấu test method |

Trong ví dụ, `ReceiptMailService` không dùng Spring container; Mockito tạo service và inject mocks. Đây là **unit test thuần**: rất phù hợp để chạy trong mỗi pull request.

### Ý nghĩa từng assertion

- `verify(mailSender).send(messageCaptor.capture())`: lời gọi `send(SimpleMailMessage)` đã diễn ra đúng một lần theo mặc định của `verify`.
- `verifyNoMoreInteractions(mailSender)`: không có tương tác **khác** với mock sender ngoài lời gọi đã verify.
- `assertEquals(...)`: các trường của message đúng.
- Không có assertion nào đo việc mở TCP socket hoặc nhận SMTP `250`.

### Vì sao phải stub RecipientPolicy?

Với Mockito mock, một phương thức trả `boolean` thông thường trả `false` mặc định. Nếu quên:

~~~java
when(recipientPolicy.canReceiveTransactionalMail(to))
        .thenReturn(true);
~~~

service sẽ rẽ sang nhánh không gửi, và `verify(mailSender).send(...)` thất bại. Đây là lỗi **setup fixture**, không phải bằng chứng SMTP provider có vấn đề.

## 8. Dùng verify, times, never và verifyNoInteractions

Mockito cung cấp một số cách kiểm tra tương tác:

~~~java
verify(mailSender).send(any(SimpleMailMessage.class));
verify(mailSender, times(1))
        .send(any(SimpleMailMessage.class));
verify(mailSender, never())
        .send(any(SimpleMailMessage.class));
verifyNoInteractions(mailSender);
~~~

Các câu lệnh chỉ là **ví dụ độc lập**, không đặt cả bốn vào cùng một test đã gọi sender vì kỳ vọng `times(1)` và `never()` sẽ mâu thuẫn.

| Lệnh | Dùng khi |
| --- | --- |
| `verify(mock).method(...)` | Kiểm tra đúng một lần cho lời gọi cụ thể |
| `verify(mock, times(n))` | Kiểm tra chính xác n lần |
| `verify(mock, never())` | Kiểm tra một overload/argument không được gọi |
| `verifyNoInteractions(mock)` | Không có lời gọi nào tới mock |
| `verifyNoMoreInteractions(mock)` | Không còn tương tác chưa verify |
| `ArgumentCaptor` | Lấy object được truyền vào và assert thuộc tính |

Không nên dùng `verifyNoMoreInteractions()` một cách máy móc trong mọi test nếu thay đổi không liên quan có thể khiến test quá giòn. Chỉ dùng khi **việc không có lời gọi ngoài ý muốn** thực sự là yêu cầu.

### Tránh kiểm tra sai overload

`JavaMailSender` có các overload như:

~~~java
send(SimpleMailMessage message)
send(SimpleMailMessage... messages)
send(MimeMessage mimeMessage)
send(MimeMessage... mimeMessages)
send(MimeMessagePreparator mimeMessagePreparator)
~~~

Một test `verify(sender).send(any(SimpleMailMessage.class))` **không tự kiểm tra mọi overload**. Với từng đường gửi, phải biết service dùng `SimpleMailMessage`, `MimeMessage` hay `MimeMessagePreparator`. Khi verify varargs hoặc array, cần chọn matcher/captor tương ứng với chữ ký được gọi.

## 9. Unit test nhánh không được gửi

Một bài test thực hành quan trọng: policy không cho gửi transactional mail tới một recipient.

~~~java
package com.example.mail;

import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class ReceiptMailSuppressionTest {

    @Mock
    JavaMailSender mailSender;

    @Mock
    RecipientPolicy recipientPolicy;

    @InjectMocks
    ReceiptMailService service;

    @Test
    void doesNotSendWhenPolicyDisallowsRecipient() {
        String to = "blocked@example.test";
        when(recipientPolicy.canReceiveTransactionalMail(to))
                .thenReturn(false);

        service.sendReceipt(to, "order-184");

        verify(recipientPolicy)
                .canReceiveTransactionalMail(to);
        verifyNoInteractions(mailSender);
    }
}
~~~

**Điều được chứng minh:** Với policy mock trả `false`, service không gọi `JavaMailSender`. Đây là một business invariant có giá trị.

**Điều chưa được chứng minh:** Mọi đường gửi khác trong hệ thống, như worker retry, manual replay hoặc provider fallback, đều kiểm tra cùng policy. Để bảo đảm không có đường bypass, cần thêm integration tests ở workflow tương ứng.

## 10. Test validation: input sai không được chạm sender

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import static org.mockito.Mockito.mock;

class ReceiptMailValidationTest {

    @Test
    void rejectsBlankRecipientWithoutSending() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        assertThrows(IllegalArgumentException.class,
                () -> service.sendReceipt(" ", "order-184"));

        verifyNoInteractions(sender, policy);
    }

    @Test
    void rejectsMissingOrderIdWithoutSending() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        assertThrows(IllegalArgumentException.class,
                () -> service.sendReceipt(
                        "buyer@example.test", null));

        verifyNoInteractions(sender, policy);
    }
}
~~~

Các test xác minh **blank/null guard** trong ví dụ. Chúng chưa kiểm tra cú pháp RFC của email, DNS hoặc mailbox tồn tại; nếu project có `InternetAddress`/Bean Validation, hãy test riêng validator đó và đừng gọi nó là deliverability test.

## 11. Mô phỏng MailException

Trong production, lời gọi SMTP có thể thất bại do connection, authentication, relay policy, recipient hoặc timeout. Trong unit test, mock tạo **exception có chủ đích**:

**`src/test/java/com/example/mail/ReceiptMailServiceFailureTest.java`**

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.mail.MailSendException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class ReceiptMailServiceFailureTest {

    @Test
    void propagatesSenderFailure() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        String to = "buyer@example.test";
        when(policy.canReceiveTransactionalMail(to))
                .thenReturn(true);

        doThrow(new MailSendException(
                "Simulated SMTP failure"))
                .when(sender)
                .send(any(SimpleMailMessage.class));

        assertThrows(MailSendException.class,
                () -> service.sendReceipt(to, "order-184"));

        verify(sender, times(1))
                .send(any(SimpleMailMessage.class));
    }
}
~~~

`JavaMailSender.send(...)` là phương thức `void`, nên cú pháp Mockito phổ biến để dựng lỗi là `doThrow(...).when(sender).send(...)`.

### Ý nghĩa đúng của test

Test chứng minh exception **được mock dựng** đi qua service theo kỳ vọng. Nó không chứng minh `MailSendException` ngoài đời luôn mang cùng thông tin/phase. Không giả định mọi `MailException` là tạm thời và đều retryable.

### Phân loại lỗi phải được test ở đúng lớp

Một kiến trúc có thể có `MailTransportAdapter` chuẩn hóa lỗi thành:

~~~text
NETWORK_TEMPORARY
SMTP_AUTH_FAILURE
RECIPIENT_PERMANENT
CONTENT_REJECTED
SUBMISSION_UNKNOWN
~~~

Unit test của retry policy có thể dùng các category này làm input. Nhưng **test adapter** cần simulated SMTP replies ở đúng phase (EHLO, AUTH, RCPT TO, DATA) để kiểm tra phân loại thực tế.

## 12. Nhận biết ranh giới `MailException` và `MessagingException`

Khi soạn MIME:

- `MimeMessageHelper` hoặc Jakarta Mail operations có thể ném `jakarta.mail.MessagingException`.
- Lời gọi `JavaMailSender.send(...)` thường báo lỗi vận chuyển qua `org.springframework.mail.MailException` và các subtype.

Trong cùng service, cần phân biệt **lỗi build message** với **lỗi gửi message**:

~~~text
Template model -> MIME creation -> JavaMailSender -> SMTP
       |                |                |
  business error   MessagingException   MailException
~~~

Các loại exception cụ thể khác nhau theo code, dependency và transport. Test không nên chỉ `catch (Exception)` rồi đánh dấu `SENT`. Nếu parse/validation lỗi trước transport, **đừng tự báo SMTP attempt đã thất bại** vì có thể chưa hề kết nối.

## 13. Chuyển sang HTML: vì sao cần MimeMessage thật?

`SimpleMailMessage` phù hợp plain text. Với HTML, plain text alternative, attachment hoặc inline resources, dùng `MimeMessage` và `MimeMessageHelper`:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mime, true, "UTF-8");
helper.setText(
        "Your receipt is ready.",
        "<html><body><p>Your receipt is ready.</p></body></html>"
);
sender.send(mime);
~~~

Nếu mock `JavaMailSender` mà không stub `createMimeMessage()`, Mockito có thể trả **null** vì đây là method trả về object. Truyền null vào `MimeMessageHelper` làm test lỗi ở fixture, không phải bằng chứng production MIME không hoạt động.

### Test MIME nên mock cái gì?

**Mock phần gửi** (`JavaMailSender.send`) nhưng **tạo `MimeMessage` thật** để có thể đọc được headers, multipart, charset và attachment thực.

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
Session session = Session.getInstance(new Properties());
when(sender.createMimeMessage())
        .thenAnswer(invocation -> new MimeMessage(session));
~~~

Cách này không kết nối SMTP. Dùng session của Jakarta Mail trong bộ nhớ, gửi `MimeMessage` vào mock và capture object để kiểm tra.

## 14. Viết HtmlReceiptMailService với attachment

**`src/main/java/com/example/mail/HtmlReceiptMailService.java`**

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class HtmlReceiptMailService {

    private final JavaMailSender mailSender;
    private final RecipientPolicy recipientPolicy;

    public HtmlReceiptMailService(
            JavaMailSender mailSender,
            RecipientPolicy recipientPolicy) {
        this.mailSender = mailSender;
        this.recipientPolicy = recipientPolicy;
    }

    public void sendReceipt(
            String recipient,
            String orderId) throws MessagingException {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient must not be blank");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "Order ID must not be blank");
        }
        if (!recipientPolicy.canReceiveTransactionalMail(recipient)) {
            return;
        }

        MimeMessage mime = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("billing@example.test");
        helper.setReplyTo("support@example.test");
        helper.setTo(recipient);
        helper.setSubject("Receipt for order " + orderId);

        String plain = "Your receipt for " + orderId + " is ready.";
        String html = "<html><body><p>Your receipt for "
                + orderId + " is ready.</p></body></html>";

        // Trong ứng dụng thật, escape dữ liệu trước khi chèn vào HTML.
        helper.setText(plain, html);

        byte[] receipt = ("Receipt: " + orderId)
                .getBytes(StandardCharsets.UTF_8);
        helper.addAttachment(
                "receipt.txt",
                new ByteArrayResource(receipt),
                "text/plain");

        mailSender.send(mime);
    }
}
~~~

### Điểm cần hiểu

- `MimeMessage` thật chứa cấu trúc dữ liệu MIME.
- `MimeMessageHelper(..., true, "UTF-8")` bật multipart và thiết lập encoding.
- `helper.setText(plain, html)` tạo **plain text alternative và HTML version**.
- `ByteArrayResource` trả một stream mới từ bytes khi cần; phù hợp fixture nhỏ.
- `addAttachment` đưa tệp đính kèm vào MIME.
- `mailSender.send(mime)` là lời gọi được mock trong unit test.

**Bảo mật:** Biến `orderId` ở code minh họa được nối trực tiếp vào HTML để đơn giản hóa. Production phải escape hoặc render qua template engine có auto-escaping; không nối nội dung người dùng tùy ý vào HTML. Test MIME structure không thay thế XSS/content validation.

### Không gửi dữ liệu thực trong bài tập

`receipt.txt` là tệp giả sinh trong bộ nhớ. Không dùng hóa đơn thật hoặc token thật. Với attachment lớn, cần giới hạn byte/memory, content type, malware scan và retention phù hợp; bài thực hành chỉ xác minh MIME composition.

## 15. Test MimeMessage với mock sender và Jakarta Mail Session

**`src/test/java/com/example/mail/HtmlReceiptMailServiceTest.java`**

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class HtmlReceiptMailServiceTest {

    @Test
    void createsMimeMessageAndInvokesSender() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);

        when(policy.canReceiveTransactionalMail(
                "buyer@example.test")).thenReturn(true);

        Session session = Session.getInstance(new Properties());
        when(sender.createMimeMessage())
                .thenAnswer(invocation -> new MimeMessage(session));

        HtmlReceiptMailService service =
                new HtmlReceiptMailService(sender, policy);

        service.sendReceipt("buyer@example.test", "order-184");

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);
        verify(sender).send(captor.capture());
        verify(sender).createMimeMessage();

        MimeMessage actual = captor.getValue();
        actual.saveChanges();

        assertEquals(
                "Receipt for order order-184",
                actual.getSubject());
        assertEquals(
                "buyer@example.test",
                actual.getRecipients(Message.RecipientType.TO)[0]
                        .toString());
        assertEquals(
                "billing@example.test",
                actual.getFrom()[0].toString());
        assertTrue(actual.isMimeType("multipart/*"));
    }
}
~~~

### Tại sao cần `saveChanges()`?

`MimeMessage.saveChanges()` có thể hoàn thiện/generate một số headers và chuẩn bị serialization trong test. Nó không gửi message. `MimeMessage` thật giúp assert headers/content structure thay vì chỉ verify `MimeMessageHelper` được gọi.

### Test này chưa kiểm tra hết

Nó mới kiểm tra subject, recipient, sender và multipart. Chỉ vì `isMimeType("multipart/*")` là true chưa chứng minh có đủ **text/plain**, **text/html** hoặc attachment bytes đúng. Bước tiếp theo sẽ duyệt cây MIME để kiểm tra những nội dung đó.

## 16. Duyệt cây multipart thay vì đoán part index

MIME message có thể lồng nhiều lớp:

~~~text
multipart/mixed
  |
  +-- multipart/related or multipart/alternative
  |      |
  |      +-- text/plain
  |      +-- text/html
  |
  +-- text/plain attachment: receipt.txt
~~~

Nếu code dùng `MimeMessageHelper` với mixed/related nesting, `getBodyPart(0)` chưa chắc là `text/plain`. **Không viết test cố định HTML luôn là part số 1**.

Một helper đệ quy có thể thu thập leaf parts:

**`src/test/java/com/example/mail/MailTestSupport.java`**

~~~java
package com.example.mail;

import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

public final class MailTestSupport {

    private MailTestSupport() {
    }

    public record MimeParts(
            List<String> plainBodies,
            List<String> htmlBodies,
            List<String> attachmentNames) {
    }

    public static MimeParts inspect(Part root) throws Exception {
        List<String> plain = new ArrayList<>();
        List<String> html = new ArrayList<>();
        List<String> attachments = new ArrayList<>();
        collect(root, plain, html, attachments);
        return new MimeParts(plain, html, attachments);
    }

    private static void collect(
            Part part,
            List<String> plain,
            List<String> html,
            List<String> attachments) throws Exception {

        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();
            for (int i = 0; i < multipart.getCount(); i++) {
                collect(multipart.getBodyPart(i),
                        plain, html, attachments);
            }
            return;
        }

        if (Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition())) {
            attachments.add(part.getFileName());
            return;
        }

        if (part.isMimeType("text/plain")) {
            plain.add((String) part.getContent());
        } else if (part.isMimeType("text/html")) {
            html.add((String) part.getContent());
        }
    }
}
~~~

Helper này dành cho fixture đơn giản. Production MIME có thể chứa `message/rfc822` lồng trong, inline resources, attachment thiếu disposition và streaming parts; nếu test cần bao phủ chúng, mở rộng đệ quy và logic phân loại. Không tái sử dụng helper này như một parser bảo mật cho email nhận từ nguồn không tin cậy.

## 17. Assert plain text, HTML và attachment name

Bổ sung vào test MIME:

~~~java
MailTestSupport.MimeParts parts =
        MailTestSupport.inspect(actual);

assertEquals(1, parts.plainBodies().size());
assertEquals(1, parts.htmlBodies().size());
assertEquals(1, parts.attachmentNames().size());

assertEquals(
        "Your receipt for order-184 is ready.",
        parts.plainBodies().get(0));

assertEquals(
        "<html><body><p>Your receipt for order-184 "
                + "is ready.</p></body></html>",
        parts.htmlBodies().get(0));

assertEquals("receipt.txt",
        parts.attachmentNames().get(0));
~~~

Với `MimeMessageHelper.setText(plain, html)`, plain text và HTML là hai biểu diễn của cùng một thông điệp; có thể cần xem cả charset, headers và layout khi nghiệp vụ quan trọng. Không bỏ qua plain text chỉ vì UI preview thường render HTML.

### Nếu muốn kiểm tra bytes đính kèm

Tên file đúng không chứng minh nội dung file đúng. Một helper kiểm tra attachment bytes theo cây:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;

static byte[] findAttachment(Part part, String filename)
        throws Exception {
    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();
        for (int i = 0; i < multipart.getCount(); i++) {
            byte[] result = findAttachment(
                    multipart.getBodyPart(i), filename);
            if (result != null) {
                return result;
            }
        }
        return null;
    }

    if (Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())
            && filename.equals(part.getFileName())) {
        try (var stream = part.getInputStream()) {
            return stream.readAllBytes();
        }
    }
    return null;
}
~~~

Và:

~~~java
assertArrayEquals(
        "Receipt: order-184".getBytes(
                java.nio.charset.StandardCharsets.UTF_8),
        findAttachment(actual, "receipt.txt"));
~~~

Các đoạn `findAttachment` là helper test; đặt vào cùng test class hoặc support class với visibility/import phù hợp. Test fixture nhỏ nên `readAllBytes()` phù hợp. **Không đọc toàn bộ attachment không giới hạn của user vào memory** trong code production.

## 18. Kiểm tra HTML escaping như một yêu cầu độc lập

Một MIME test có thể xanh dù HTML không an toàn:

~~~java
String html = "<p>Hello " + customerName + "</p>";
~~~

Nếu `customerName` chứa ký tự HTML, nội dung có thể bị thay đổi ngoài dự kiến. Với Spring template engine có auto-escaping hoặc encoder tương ứng, hãy kiểm thử rằng:

- Dữ liệu text được escape đúng ngữ cảnh HTML.
- URL attributes được validate/encode và không cho scheme nguy hiểm.
- Không cho người dùng tùy ý đưa scripts, active HTML hoặc remote resources.
- Không để template string từ nguồn không tin cậy trở thành executable instructions.

Một unit test của template renderer có thể so sánh output đã escape, rồi MIME test kiểm tra output được đặt vào `text/html`. **Mock JavaMailSender không tự bảo vệ khỏi HTML injection**.

## 19. Không cần @SpringBootTest cho mọi unit test

Ví dụ constructor injection:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
RecipientPolicy policy = mock(RecipientPolicy.class);
ReceiptMailService service =
        new ReceiptMailService(sender, policy);
~~~

Đủ để kiểm tra logic của service. `@SpringBootTest` khởi tạo nhiều bean hơn, tăng thời gian và có thể kéo theo external configuration không cần thiết. Đừng chọn full Spring context chỉ để dùng Mockito.

### Khi nào cần Spring context test?

Khi cần kiểm tra:

- `@Configuration` chọn đúng implementation.
- Bean qualifiers/routing giữa nhiều mail senders.
- Properties binding.
- Transaction interceptors và application events.
- Async scheduling/outbox integration.

Một context test có mock `JavaMailSender` vẫn là **wiring/integration around a mock**, không phải SMTP transport integration.

## 20. Dùng @MockitoBean/@MockBean trong Spring context

Với các phiên bản Spring Framework hỗ trợ `@MockitoBean`, có thể thay sender bean trong application context:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class ReceiptContextTest {

    @MockitoBean
    JavaMailSender mailSender;

    @Autowired
    ReceiptMailService receiptMailService;

    @Test
    void applicationServiceUsesInjectedSender() {
        // Test fixture phải cấu hình RecipientPolicy
        // để cho phép recipient test.
        receiptMailService.sendReceipt(
                "buyer@example.test", "order-184");

        verify(mailSender)
                .send(any(SimpleMailMessage.class));
    }
}
~~~

Đây là **khung minh họa**: context phải có bean `ReceiptMailService` và một `RecipientPolicy` phù hợp, ví dụ registration cấu hình test. Lớp service ví dụ chưa được đánh dấu `@Service` nên không tự được Spring scan. Muốn chạy nguyên test theo Spring context cần đăng ký service và policy qua cấu hình/annotation thích hợp.

Với phiên bản Spring Boot cũ hơn, có thể dùng `@MockBean` thay `@MockitoBean`, tùy thư viện và deprecation status. **Không trộn annotation của version mới vào project cũ** mà không kiểm tra compatibility.

### Cảnh báo về phạm vi kiểm thử

`@SpringBootTest` không tự biến test thành SMTP end-to-end. Khi bean transport bị mock, không có socket được mở từ sender. Tên test nên là `applicationServiceUsesInjectedSender`, không phải `mailDeliveredToRecipient`.

## 21. Bài tập bổ sung: kiểm tra Reply-To, Cc và Bcc

Đối với `SimpleMailMessage`, `Reply-To` và `Cc`/`Bcc` là những thuộc tính cần test riêng nếu nghiệp vụ sử dụng.

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("billing@example.test");
message.setReplyTo("support@example.test");
message.setTo("buyer@example.test");
message.setCc("accounting@example.test");
message.setBcc("audit@example.test");
message.setSubject("Receipt");
message.setText("Your receipt is ready.");
~~~

Captor assertions:

~~~java
assertArrayEquals(
        new String[] { "buyer@example.test" },
        actual.getTo());
assertArrayEquals(
        new String[] { "accounting@example.test" },
        actual.getCc());
assertArrayEquals(
        new String[] { "audit@example.test" },
        actual.getBcc());
assertEquals(
        "support@example.test",
        actual.getReplyTo());
~~~

`actual` ở đây là `SimpleMailMessage` lấy từ `ArgumentCaptor` của test tương ứng. `assertArrayEquals` được static import từ `org.junit.jupiter.api.Assertions`.

### Điều Bcc test không chứng minh

Trong SMTP thực, Bcc recipients thường xuất hiện ở **SMTP envelope** chứ không nên lộ trong headers được giao. Việc assert `getBcc()` của `SimpleMailMessage` chỉ kiểm tra service đã đặt recipient; nó không chứng minh SMTP client xây đúng RCPT TO, hoặc bản MIME đã giao không lộ Bcc. Muốn kiểm tra, dùng local SMTP server/transport fixture có thể quan sát envelope và message headers riêng.

### Cẩn trọng với nhiều recipients

Nếu service gửi một email chứa nhiều To/Cc/Bcc, từng recipient có thể được accepted hoặc rejected khác nhau. Một mock sender không biết các recipient outcomes; không kết luận “tất cả đã nhận” từ `verify(sender).send(message)`.

## 22. Kiểm thử nhiều email được tạo từ một batch

Giả sử service xử lý một danh sách notification. Có hai cách triển khai:

**Cách A: gọi `send(message)` cho từng phần tử**

~~~java
for (SimpleMailMessage message : messages) {
    mailSender.send(message);
}
~~~

Test có thể capture từng lời gọi:

~~~java
ArgumentCaptor<SimpleMailMessage> captor =
        ArgumentCaptor.forClass(SimpleMailMessage.class);

verify(mailSender, times(2)).send(captor.capture());
assertEquals(2, captor.getAllValues().size());
~~~

**Cách B: gọi overload varargs một lần**

~~~java
mailSender.send(messages.toArray(
        new SimpleMailMessage[0]));
~~~

Trong trường hợp này, một lần gọi `send(SimpleMailMessage... messages)` có thể chứa nhiều items. Test phải verify đúng overload/array mà service đã gọi:

~~~java
ArgumentCaptor<SimpleMailMessage[]> batchCaptor =
        ArgumentCaptor.forClass(SimpleMailMessage[].class);

verify(mailSender).send(batchCaptor.capture());
assertEquals(2, batchCaptor.getValue().length);
~~~

Các đoạn ví dụ là những **kiểu triển khai thay thế nhau** và cần đặt trong test class có biến `messages` và `mailSender` tương ứng.

### Mockito, varargs và overloaded methods

Mockito có thay đổi cách matching varargs giữa các major versions. Với array overload, có thể dùng `ArgumentCaptor<SimpleMailMessage[]>` hoặc test dựa trên array được truyền vào với kiểu/overload tường minh theo version hiện hành. Nếu `verify` không khớp, kiểm tra lời gọi thực và chữ ký method; **không hạ assertion xuống `verifyNoMoreInteractions` vô nghĩa chỉ để test xanh**.

### Chú ý: một batch method không bảo đảm all-or-nothing

Mock không chạy SMTP, nên `send(array)` không cho biết khi một message thất bại liệu các message trước đã accepted hay chưa. Nếu cần test partial failures, dùng adapter integration và status per notification/recipient.

## 23. Kiểm thử với MimeMessagePreparator

`JavaMailSender` cho phép gửi qua `MimeMessagePreparator`: ứng dụng truyền một callback soạn message, sender triển khai tạo `MimeMessage` và gọi callback.

Một service:

~~~java
package com.example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class PreparedNoticeService {

    private final JavaMailSender sender;

    public PreparedNoticeService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendNotice(String recipient, String text) {
        sender.send(mime -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, "UTF-8");
            helper.setFrom("notices@example.test");
            helper.setTo(recipient);
            helper.setSubject("Notification");
            helper.setText(text);
        });
    }
}
~~~

Nếu chỉ:

~~~java
verify(sender).send(any(MimeMessagePreparator.class));
~~~

thì bạn xác minh callback được truyền tới mock, **không xác minh callback đã chạy và đặt message đúng**. Mockito mock không tự execute callback.

### Dùng doAnswer để gọi preparator với MIME thật

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

class PreparedNoticeServiceTest {

    @Test
    void invokesPreparatorAndBuildsExpectedMime()
            throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        AtomicReference<MimeMessage> captured =
                new AtomicReference<>();

        doAnswer(invocation -> {
            MimeMessagePreparator preparator =
                    invocation.getArgument(0);

            MimeMessage realMime = new MimeMessage(
                    Session.getInstance(new Properties()));
            preparator.prepare(realMime);
            realMime.saveChanges();
            captured.set(realMime);
            return null;
        }).when(sender).send(any(MimeMessagePreparator.class));

        PreparedNoticeService service =
                new PreparedNoticeService(sender);
        service.sendNotice(
                "buyer@example.test", "Your order is ready.");

        verify(sender).send(any(MimeMessagePreparator.class));
        MimeMessage actual = captured.get();

        assertEquals("Notification", actual.getSubject());
        assertEquals(
                "buyer@example.test",
                actual.getRecipients(Message.RecipientType.TO)[0]
                        .toString());
        assertEquals(
                "Your order is ready.",
                actual.getContent().toString());
    }
}
~~~

Đây là một cách test **callback preparation** bằng MIME thật nhưng vẫn không gọi SMTP. Chú ý stub `doAnswer` đã chọn overload `send(MimeMessagePreparator)` tường minh.

### Khi nào nên dùng doAnswer?

Khi hành vi quan trọng nằm trong callback/deferred code, `verify(callback passed)` không đủ. Có thể chủ động invoke callback trong test rồi assert kết quả. Tuy nhiên test phải nói rõ đây là **execution mô phỏng bởi test**, không phải JavaMailSender thật đã gửi thư.

## 24. Tránh test phụ thuộc vào SMTP host hoặc Internet

Đơn vị mã đang test:

~~~java
ReceiptMailService service =
        new ReceiptMailService(mockSender, mockPolicy);
~~~

Không cần bật:

~~~text
SMTP_HOST
SMTP_USERNAME
SMTP_PASSWORD
VPN
Internet access
~~~

Việc test phụ thuộc network khiến:

- CI flaky do DNS, TLS hoặc provider outage.
- Test vô tình gửi email tới người thật.
- Phải cấp secrets cho nơi không cần thiết.
- Lỗi trở nên khó tái hiện.
- Test chậm và không còn đúng tính chất unit.

Tập trung vào **deterministic inputs/outputs và mocks**. Khi cần kiểm tra SMTP transport, hãy tạo một suite riêng sử dụng fake SMTP hoặc provider account được cấp phép.

### Guardrail quan trọng cho CI

Nếu project có configuration profile dùng production SMTP, unit test **không được** tự chọn profile đó. Unit test với Mockito không khởi động Spring context nên an toàn khỏi auto-configured transport. Với context tests, bảo đảm mail sender đã được thay bằng mock hoặc trỏ tới test server được kiểm soát.

## 25. Dùng dữ liệu test tách khỏi dữ liệu khách hàng

Các địa chỉ thuộc domain reserved `.test` có ích cho test data:

~~~text
buyer@example.test
blocked@example.test
support@example.test
billing@example.test
~~~

Chúng chỉ đóng vai trò fixtures. Không cố gửi tới các địa chỉ này qua SMTP thực rồi mong mailbox tồn tại; `.test` không phải hạ tầng mail production.

Nên dùng order IDs giả, tên giả và attachment nhỏ sinh trong memory. Tránh copy raw production email, OTP, mật khẩu hoặc thông tin nhạy cảm vào test resources.

### Dynamic dates và test determinism

Nếu subject chứa ngày, không gọi `LocalDate.now()` trực tiếp trong service rồi assert ngày theo môi trường CI. Inject `Clock`:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        java.time.Instant.parse("2026-11-20T02:00:00Z"),
        ZoneOffset.UTC);
LocalDate date = LocalDate.now(fixed);
~~~

Test có thể dự đoán chính xác subject/body. `Clock.fixed` chỉ giúp kiểm soát thời gian application; nó không kiểm tra mail delivery thực.

## 26. Bài tập về retry: một lời gọi trong test không phải exactly-once

Test sau:

~~~java
verify(sender, times(1)).send(any(SimpleMailMessage.class));
~~~

chứng minh một lời gọi trong **một execution của test**. Trong production có thể xảy ra:

~~~text
Worker A calls SMTP
Relay accepts message
Worker A crashes before updating database
Queue redelivers notification
Worker B calls SMTP again
~~~

Mock test trên service riêng không phát hiện lỗi này. Muốn test chống duplicate qua restart, cần:

- Durable outbox/ledger với idempotency key.
- Atomic claim hoặc lease giữa workers.
- Attempt tracking.
- Transaction boundary giữa database và SMTP.
- Cách xử lý `SUBMISSION_UNKNOWN` khi không biết relay đã accepted.
- Integration tests với worker crash và queue redelivery.

### Mục tiêu unit test cho retry policy

Một policy nhỏ có thể quyết định:

~~~java
package com.example.mail;

public final class RetryPolicy {
    public boolean shouldRetry(
            FailureKind failure,
            int attempts,
            int maxAttempts,
            boolean expired) {
        return !expired
                && attempts < maxAttempts
                && failure == FailureKind.TEMPORARY;
    }
}

enum FailureKind {
    TEMPORARY,
    PERMANENT,
    AUTHENTICATION,
    UNKNOWN_OUTCOME
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RetryPolicyTest {

    private final RetryPolicy policy = new RetryPolicy();

    @Test
    void retriesOnlyTemporaryFailuresWithinBudget() {
        assertTrue(policy.shouldRetry(
                FailureKind.TEMPORARY, 1, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.PERMANENT, 1, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.AUTHENTICATION, 1, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.UNKNOWN_OUTCOME, 1, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.TEMPORARY, 3, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.TEMPORARY, 1, 3, true));
    }
}
~~~

Đây là **logic policy thuần**, không cần mock SMTP. Điều chưa được chứng minh là adapter ngoài đời phân loại exception đúng thành `FailureKind` và worker persist `availableAt` đúng. Kiểm tra đó thuộc integration test.

## 27. Kiểm thử không gửi khi thông điệp hết hạn

Với email OTP hoặc lời nhắc, thời hạn là điều kiện nghiệp vụ:

~~~java
if (!clock.instant().isBefore(notification.expiresAt())) {
    repository.markExpired(notification.id());
    return;
}
mailSender.send(message);
~~~

Trong unit test:

1. Inject `Clock.fixed` sau `expiresAt`.
2. Stub repository lấy đúng notification.
3. Gọi worker.
4. Verify `markExpired(id)`.
5. Verify `mailSender` không có send invocation.

### Vì sao đây vẫn là mock test?

Nó xác minh một worker sẽ không **yêu cầu gửi** khi hết hạn trong điều kiện giả lập. Nếu production có một đường gửi thứ hai bypass logic hoặc một worker chạy từ snapshot cũ, phải dùng integration tests với transaction/version để kiểm tra.

## 28. Kiểm thử Outbox: service nghiệp vụ không nên gửi trực tiếp

Trong một hệ thống có transaction nghiệp vụ, có thể thiết kế:

~~~text
confirmPayment()
    |
    +-- update payment status in database
    |
    +-- insert mail outbox record
    |
    +-- COMMIT

background worker:
    claim due outbox record
    render and send via JavaMailSender
    store submission outcome
~~~

Trong trường hợp này, một test:

~~~java
verify(mailSender).send(any(SimpleMailMessage.class));
~~~

**ngay sau `confirmPayment()`** có thể là dấu hiệu thiết kế sai, vì payment service không nên gọi SMTP trong transaction. Unit test thích hợp hơn là:

~~~java
verify(outboxRepository).insert(any(MailOutboxRecord.class));
verifyNoInteractions(mailSender);
~~~

`MailOutboxRecord` và `outboxRepository` ở đây là **tên thành phần giả định**, không phải Spring Mail classes sẵn có. Đoạn code minh họa điều cần verify.

### Kiểm tra khác nhau ở các boundary

| Thành phần | Test bằng mock gì? | Assert |
| --- | --- | --- |
| Payment service | Outbox repository | Có yêu cầu mail đúng dữ liệu, không SMTP call trong transaction |
| Notification renderer | Template engine/data source | Body/MIME đúng |
| Mail dispatch worker | JavaMailSender | Đã gọi sender khi job hợp lệ |
| Retry handler | Repository + failure classifier | Lưu trạng thái/availableAt phù hợp |
| Provider event consumer | Event repository | Cập nhật delivery projection sau event được xác thực |

Đừng cố dùng một `JavaMailSender` mock để chứng minh toàn bộ workflow từ thanh toán tới Inbox. Mỗi boundary có bằng chứng riêng.

## 29. Transaction và @Async: những gì mock không tự bảo đảm

Một method:

~~~java
@Async
public void sendLater(String to) {
    mailSender.send(buildMessage(to));
}
~~~

có thể chạy ở thread khác. Nếu unit test gọi trực tiếp object không qua Spring proxy, `@Async` không tự tạo thread; nếu gọi qua proxy thật, assertion chạy ngay có thể xảy ra **trước** khi send.

### Chọn tầng test đúng

- Unit test thuần: gọi method trực tiếp, kiểm tra logic đồng bộ.
- Context integration: kiểm tra `@Async`/proxy/executor thực, dùng synchronization đáng tin thay vì `Thread.sleep` ngẫu nhiên.
- Durable scheduling: kiểm tra outbox/queue persistence khi process restart.

`@Async` không tự lưu job bền vững. Một mock test xanh không chứng minh email vẫn được gửi nếu JVM chết trước khi task chạy.

### Test không nên sleep tùy ý

~~~java
Thread.sleep(500);
verify(mailSender).send(any(SimpleMailMessage.class));
~~~

Đây là test dễ flaky dưới CI tải cao. Nếu integration test thực sự kiểm tra async, dùng `CompletableFuture`, latch, Awaitility hoặc event/status completion có timeout rõ; không phải chỉ chờ một số mili giây rồi đoán.

## 30. Dùng captor cho message bất biến và tránh mutation sau send

Mockito capture **reference của object** được truyền vào. Nếu service sau khi gọi `send(message)` tiếp tục sửa cùng `SimpleMailMessage` instance, captor về cuối test có thể nhìn thấy trạng thái **sau mutation**, không nhất thiết là trạng thái tại lúc gọi send.

Ví dụ không nên làm:

~~~java
mailSender.send(message);
message.setTo("other@example.test");
~~~

Test:

~~~java
verify(mailSender).send(captor.capture());
~~~

có thể đọc recipient cuối cùng đã bị thay đổi. Để kiểm tra snapshot tại invocation time, dùng `doAnswer` tạo bản sao cần thiết trong callback:

~~~java
java.util.concurrent.atomic.AtomicReference<SimpleMailMessage>
        snapshot = new java.util.concurrent.atomic.AtomicReference<>();

doAnswer(invocation -> {
    SimpleMailMessage input = invocation.getArgument(0);
    snapshot.set(new SimpleMailMessage(input));
    return null;
}).when(mailSender).send(any(SimpleMailMessage.class));
~~~

Sau đó assert `snapshot.get()`. Constructor copy `SimpleMailMessage(SimpleMailMessage original)` hỗ trợ sao chép các trường của message ở thời điểm mock được gọi. Với `MimeMessage`, snapshot có thể được thực hiện qua serialization bytes hoặc test-specific immutable extraction, vì MIME object cũng mutable.

### Khi nào phải dùng snapshot?

Chỉ khi object sau send có nguy cơ được sửa hoặc dùng lại, hoặc khi muốn assert chính xác state tại invocation. Với service ví dụ không sửa message sau khi gửi, `ArgumentCaptor` đơn giản thường là đủ.

## 31. Mockito strict stubbing và test có thể đọc được

Với `MockitoExtension`, strict stubbing có thể giúp phát hiện stubs không được dùng. Ví dụ:

~~~java
when(policy.canReceiveTransactionalMail("unused@example.test"))
        .thenReturn(true);
~~~

nếu test lại gọi `service.sendReceipt("buyer@example.test", ...)`, stub không phù hợp. Test có thể bị cảnh báo hoặc thất bại vì setup không nhất quán.

Thay vì thêm `lenient()` khắp nơi, hãy:

- Stub đúng dữ liệu mỗi test.
- Không stub những method nhánh đó không gọi.
- Dùng `@BeforeEach` chỉ cho setup thật sự dùng chung.
- Tách tests cho nhánh allow/deny.
- Không tự động bật `RETURNS_DEEP_STUBS` để tránh phải thiết kế dependency seam rõ.

### Không mock quá sâu

Nếu test có chuỗi:

~~~java
when(sender.getSession().getTransport("smtp")
        .isConnected()).thenReturn(true);
~~~

bạn đang mock sâu vào transport implementation thay vì kiểm tra hành vi service. `JavaMailSender` là abstraction đủ tốt để mock ở boundary; việc kiểm tra Jakarta Mail transport nên thuộc integration test.

## 32. Tách message builder nếu logic phức tạp

Một service vừa tìm dữ liệu, quyết định recipient, render template, tạo attachment, gọi SMTP và cập nhật database sẽ khó test. Có thể tách:

~~~mermaid
flowchart LR
    A["Business decision"] --> B["MailMessageFactory"]
    B --> C["Prepared MIME"]
    C --> D["JavaMailSender"]
    D --> E["SMTP"]
~~~

Các thành phần:

- `RecipientPolicy`: quyền được gửi.
- `MailMessageFactory`: tạo message đúng subject/body/headers.
- `JavaMailSender`: transport boundary.
- `DeliveryStateRepository`: ghi submission/attempt state.

**Lợi ích kiểm thử:** factory có thể dùng Jakarta Mail thật trong test mà không phải mock sender; dispatcher test verify `sender.send`; policy test không cần MIME. Mỗi test trả lời một câu hỏi rõ hơn.

### Đừng refactor chỉ để tất cả đều có mock

Với một service ngắn như `ReceiptMailService`, constructor injection và một test captor đã đủ. Tách thêm abstraction chỉ khi độ phức tạp, tái sử dụng hoặc boundary vận hành thật sự cần.

## 33. Test case negative: template không được phép

Giả sử nghiệp vụ có một `TemplatePolicy`:

~~~java
public interface TemplatePolicy {
    boolean mayUseTemplate(String templateKey);
}
~~~

Service có thể kiểm tra:

~~~java
if (!templatePolicy.mayUseTemplate(templateKey)) {
    throw new IllegalArgumentException(
            "Template is not allowed");
}
~~~

Unit test tương ứng nên:

1. Stub `templatePolicy.mayUseTemplate("unknown")` trả false.
2. `assertThrows` khi gọi service.
3. `verifyNoInteractions(mailSender)`.

Test sẽ không cần gửi thư để chứng minh một template không được phép bị chặn. Nếu template data chứa HTML hoặc link không tin cậy, test input sanitization/rendering riêng.

## 34. Test case negative: attachment không hợp lệ

Với email có attachment, application có thể yêu cầu:

- File thuộc allowlist MIME/extension theo nghiệp vụ.
- Dung lượng không vượt hạn mức.
- File đã được scanner phân loại phù hợp.
- Không lấy filename hoặc đường dẫn do user tự gửi làm storage path.
- Nội dung đã được tải theo đúng version/hash.

Trong unit test của dispatch service, mock một `AttachmentPolicy` trả `REJECTED` và verify `JavaMailSender` không được gọi. Nhưng nếu muốn chứng minh actual MIME bytes được encode đúng, cần MIME test thật. Nếu muốn chứng minh malware scanner thực, cần test tích hợp scanner được cấp phép; một mock verdict `CLEAN` không biến attachment thành thực sự sạch.

### Không coi “đã tạo MIME” là đã scan

~~~text
MIME parse/build successful != Malware-free attachment
~~~

Test phải phân biệt rõ mục tiêu để không báo sai về bảo mật.

## 35. Bảng tổng hợp assertion theo hành vi cần chứng minh

| Yêu cầu | Kiểu test | Assertion phù hợp |
| --- | --- | --- |
| Đúng recipient | Unit + mock | `ArgumentCaptor.getTo()` |
| Đúng From/Reply-To | Unit + mock | `getFrom()`, `getReplyTo()` |
| Đúng subject/plain body | Unit + mock | `getSubject()`, `getText()` |
| Không gửi recipient bị chặn | Unit + mock | `verifyNoInteractions(sender)` |
| Input rỗng bị từ chối | Unit + mock | `assertThrows`, no interactions |
| Sender ném lỗi được propagate | Unit + mock | `doThrow`, `assertThrows` |
| Không gửi quá một lần trong một call | Unit + mock | `times(1)` |
| Batch có N messages | Unit + mock | Captor array hoặc `getAllValues()` |
| Plain và HTML được tạo đúng | MIME unit | Duyệt MIME tree, kiểm decoded content |
| Attachment bytes đúng | MIME unit | Part disposition/name/bytes |
| Header Bcc không lộ trong message được giao | SMTP integration | Quan sát envelope và transmitted header |
| TLS/STARTTLS hoạt động | SMTP integration | Real negotiation với test relay |
| Relay thực trả SMTP 250 | SMTP integration | SMTP transcript/server capture |
| Provider credentials thật hợp lệ | Authorized provider smoke test | Provider acceptance |
| Bounce/delivery events được xử lý | Webhook integration | Signature, dedup, projection |
| Email vào Inbox seed | Controlled mailbox observation | Folder location của seed |
| Người nhận đã đọc | Product-level confirmation nếu có | Hành động thực có xác thực |

**Không dùng unit mock để “điền thay” kết quả SMTP/provider/mailbox.** Khi chưa quan sát, trạng thái thích hợp là `UNKNOWN`, không phải `DELIVERED`.

## 36. Ma trận các tình huống cần thực hành

| ID | Kịch bản | Điều cần kiểm tra |
| --- | --- | --- |
| U01 | Recipient hợp lệ, policy cho phép | Một `SimpleMailMessage` đúng trường |
| U02 | Recipient rỗng | Throw validation, không gọi policy/sender |
| U03 | Order ID rỗng | Throw validation, không gửi |
| U04 | Policy từ chối | Không gọi sender |
| U05 | From đúng identity | Captor kiểm tra From |
| U06 | Reply-To đúng | Captor kiểm tra Reply-To |
| U07 | Subject chứa đúng order ID | Captor kiểm subject |
| U08 | Body plain text đúng | Captor kiểm text |
| U09 | Một lời gọi gửi | `times(1)` |
| U10 | SMTP được mô phỏng lỗi | `doThrow`, `assertThrows` |
| U11 | Policy được gọi một lần | `verify(policy)` |
| U12 | Retry policy gặp temporary failure | Cho phép retry khi còn budget |
| U13 | Retry policy gặp permanent failure | Không retry |
| U14 | Retry policy gặp unknown outcome | Không retry mù |
| U15 | Notification expired | Không gửi |
| U16 | Template không được phép | Không gửi |
| U17 | Attachment bị reject | Không gọi sender |
| U18 | Batch gửi từng phần tử | Captor getAllValues |
| U19 | Batch dùng varargs overload | Captor array và số phần tử |
| U20 | Message bị sửa sau send | Snapshot trong doAnswer |
| M01 | MimeMessage được tạo thật | Stub `createMimeMessage` trả MIME |
| M02 | MIME From/To/Subject | Capture MimeMessage và assert |
| M03 | MIME plain alternative | Parse MIME tree |
| M04 | MIME HTML alternative | Parse MIME tree |
| M05 | MIME UTF-8 Unicode | Decoded content giữ ký tự |
| M06 | Attachment filename | MIME part disposition/name |
| M07 | Attachment bytes | Read test fixture stream |
| M08 | Inline resource (mở rộng) | Content-ID và HTML `cid:` khớp |
| M09 | Callback preparator | doAnswer invoke callback |
| M10 | MIME build fail | No transport submission khi build chưa hoàn tất |
| I01 | Mockito context với sender bị thay | Service wiring nhưng không có SMTP socket |
| I02 | Local SMTP nhận message | Test relay nhận MIME |
| I03 | Local SMTP reply 4xx/5xx | Adapter xử lý lỗi đúng phase |
| I04 | Provider delivered webhook | Status delivery từ event verified |
| I05 | SMTP outcome unknown | Không tự động resend |

Đây là **ma trận test đề xuất**, không phải kết quả test đã thực thi. Khi review bài tập, đánh dấu case nào được code và chạy trong môi trường nào; đừng tự suy ra test pass chỉ từ việc thấy đoạn mã trong tài liệu.

## 37. Test nâng cao: dùng @ParameterizedTest cho invalid input

Khi nhiều input cần cùng một quy tắc, JUnit 5 có thể giảm trùng lặp:

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mail.javamail.JavaMailSender;

class ReceiptMailParameterizedTest {

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = { " ", "   " })
    void rejectsBlankRecipients(String recipient) {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        assertThrows(IllegalArgumentException.class,
                () -> service.sendReceipt(recipient, "order-184"));

        verifyNoInteractions(sender, policy);
    }
}
~~~

Test này kiểm null/empty/whitespace, không phải xác minh địa chỉ email RFC hoặc mailbox tồn tại. Nếu muốn test `InternetAddress`, hãy viết một test riêng cho validator với những input cú pháp cụ thể.

### Tránh assertion quá mức

`null`, chuỗi rỗng và whitespace đều bị validation hiện tại từ chối. Nhưng một chuỗi `not-an-email` **không** bị chặn bởi `isBlank()`; muốn chặn phải thêm validator thật vào implementation. **Đừng viết test mong đợi reject mọi địa chỉ sai trong khi service chỉ kiểm blank**.

## 38. Khi cần kiểm tra nội dung động hoặc localization

Subject/body có thể được tạo theo locale:

~~~text
vi-VN: Xác nhận đơn hàng order-184
en-US: Receipt for order order-184
~~~

Unit test của message composition nên cung cấp `Locale` hoặc một template renderer mock/fixture rồi capture `SimpleMailMessage`. Với template thật, test riêng:

- Vietnamese dấu không bị hỏng trong MIME.
- Placeholders được resolve đúng.
- Plain text/HTML đồng nhất về nội dung.
- Các giá trị tiền/ngày tháng được định dạng theo locale và timezone được cung cấp.
- Escape HTML để dữ liệu user không biến thành markup.

Một mock sender không có trách nhiệm render template. Nếu giả cả renderer và sender, test chỉ kiểm tra **service orchestration**, không chứng minh template output đúng. Để test template output, dùng renderer thật hoặc snapshot/fixture đã định nghĩa.

## 39. Giảm false positive trong test

Một bài test có thể xanh nhưng không bảo vệ yêu cầu:

~~~java
verify(sender).send(any(SimpleMailMessage.class));
~~~

Nếu developer vô tình đổi recipient từ `buyer@example.test` sang `attacker@example.test`, test vẫn xanh vì `any(...)` không kiểm nội dung.

### Cải thiện bằng capture

~~~java
ArgumentCaptor<SimpleMailMessage> captor =
        ArgumentCaptor.forClass(SimpleMailMessage.class);

verify(sender).send(captor.capture());
assertArrayEquals(
        new String[] { "buyer@example.test" },
        captor.getValue().getTo());
~~~

**Nguyên tắc:** Dùng `any(...)` khi chỉ cần chứng minh có lời gọi; dùng captor hoặc `argThat` khi những thuộc tính bên trong là yêu cầu nghiệp vụ.

### Khi nào dùng argThat?

Với một điều kiện đơn giản:

~~~java
verify(sender).send(argThat((SimpleMailMessage msg) ->
        msg.getSubject().startsWith("Receipt for order ")
                && msg.getTo() != null
                && msg.getTo().length == 1));
~~~

Với nhiều thuộc tính, `ArgumentCaptor` thường dễ đọc và cho thông báo lỗi rõ hơn. Nếu sử dụng `argThat` với method overload, chỉ định type trong lambda như ví dụ để Java compiler chọn đúng overload.

### Không assert những chi tiết không quan trọng

Nếu business chỉ cần subject chứa mã đơn và body đã thông qua renderer, không nhất thiết assert mọi whitespace của template ở orchestration unit test. Để tránh test giòn, tách test template content ra khỏi test dispatch.

## 40. Chọn mức test theo rủi ro

| Thay đổi trong PR | Test có lợi nhất |
| --- | --- |
| Chọn recipient từ order | Unit test policy + captor |
| Đổi tiêu đề email | Message composition test |
| Thêm HTML alternative | MIME parse test |
| Thêm attachment | MIME structure/bytes + security policy |
| Đổi sender bean/route | Spring wiring/config test |
| Đổi SMTP port/TLS/auth | SMTP integration/staging smoke test |
| Đổi provider | Provider auth/events + canary |
| Đổi retry policy | Policy unit + dispatch integration |
| Đổi outbox claim | Database concurrency integration |
| Đổi DKIM/domain | DNS/received-message authentication |
| Muốn cải thiện Inbox placement | Seed tests + production telemetry |

Chạy thêm test ở tầng có thể quan sát rủi ro, thay vì tăng số lượng Mockito tests vô hạn nhưng không mở rộng bằng chứng.

## 41. Lưu ý về verify của overloaded send

Một số API của `JavaMailSender`:

~~~java
void send(SimpleMailMessage simpleMessage);
void send(SimpleMailMessage... simpleMessages);
void send(MimeMessage mimeMessage);
void send(MimeMessage... mimeMessages);
void send(MimeMessagePreparator mimeMessagePreparator);
void send(MimeMessagePreparator... mimeMessagePreparators);
~~~

Ví dụ nếu implementation gọi:

~~~java
mailSender.send(mimeMessage);
~~~

thì verify cần:

~~~java
verify(mailSender).send(any(MimeMessage.class));
~~~

không phải:

~~~java
verify(mailSender).send(any(SimpleMailMessage.class));
~~~

Hai loại message khác nhau, và Mockito chỉ xác minh method signatures được gọi thực.

### Kiểm tra exception tương ứng

Nếu code gọi `send(MimeMessage)`, stub:

~~~java
doThrow(new MailSendException("simulated"))
        .when(mailSender)
        .send(any(MimeMessage.class));
~~~

Stub cho `SimpleMailMessage` overload sẽ không áp dụng. Khi test bất ngờ “không throw”, kiểm tra bạn có đang stub nhầm overload hay không.

### Dùng qualifier khi có nhiều JavaMailSender beans

Trong Spring context có thể có sender chính và sender cho marketing. Một `@Mock` thuần được truyền qua constructor đúng là một dependency rõ ràng; với `@MockitoBean` ở context, phải biết bean nào bị thay. Nếu có nhiều candidates, dùng name/qualifier phù hợp version Spring để tránh test pass trên mock khác với sender production đang dùng.

## 42. Test error policy mà không cho phép gửi trùng

Một failure path có thể có:

~~~text
Sender throws MailException
  |
  +-- record attempt
  +-- normalize failure
  +-- if temporary and safe: schedule retry
  +-- if permanent: stop
  +-- if unknown outcome: reconcile
~~~

Đối với **unit test**, mock JavaMailSender có thể ném lỗi và mock repository để assert đúng state update.

~~~java
doThrow(new MailSendException("temporary-test"))
        .when(sender).send(any(SimpleMailMessage.class));

// Gọi dispatcher dưới test, rồi kiểm tra repository
// đã ghi trạng thái/lý do theo policy được cung cấp.
~~~

Nhưng phải nhớ:

1. Một `MailSendException` dựng trong Mockito không tự chứng minh lỗi là SMTP 451/421 hoặc xảy ra trước DATA.
2. Một lỗi socket sau DATA có thể đã được relay accepted.
3. Không tăng retry count dựa trên `verify(times(1))` mà bỏ qua physical SMTP attempts.
4. Không giả định `Message-ID` có thể ngăn duplicate ở mọi recipient.

Muốn kiểm failure phase, dùng một SMTP server có thể trả code và đóng kết nối ở phase xác định.

## 43. Bổ sung một test kiểm tra không gửi khi policy bị exception

Nếu policy service thất bại, lựa chọn hợp lý với một hệ thống nhạy cảm thường là **không gửi cho tới khi xác minh được quyền**:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class ReceiptPolicyFailureTest {

    @Test
    void stopsBeforeSendingWhenPolicyIsUnavailable() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        String to = "buyer@example.test";
        when(policy.canReceiveTransactionalMail(to))
                .thenThrow(new IllegalStateException(
                        "Policy service unavailable"));

        assertThrows(IllegalStateException.class,
                () -> service.sendReceipt(to, "order-184"));

        verifyNoInteractions(sender);
    }
}
~~~

Trong một hệ thống thật, policy failure có thể được phân loại và đưa notification vào `HOLD` hoặc `RETRY_PENDING` theo business rule. Bài test trên chỉ chứng minh service **không bypass policy** để gửi khi không thể xác minh điều kiện.

## 44. Tài liệu hóa đúng kết quả của test

Thay vì report:

~~~text
All emails successfully delivered in JUnit tests.
~~~

hãy viết:

~~~text
JUnit/Mockito unit tests:
  - Receipt service invoked JavaMailSender with expected fields.
  - Invalid and suppressed recipients caused zero send calls.
  - Simulated MailSendException propagated correctly.
  - MIME message contained plain/HTML alternatives and attachment.

Not measured:
  - Production SMTP connectivity or credentials.
  - Relay acceptance, bounce/delivery outcomes.
  - Inbox placement and human engagement.
~~~

Đây là **mẫu cách viết báo cáo**, không phải kết quả một lần chạy thực tế. Điều quan trọng là không tuyên bố những điều test không quan sát.

### Khi hiển thị cho người dùng cuối

Một business flow có thể dùng trạng thái:

| State | Cách diễn giải |
| --- | --- |
| `QUEUED` | Hệ thống đã nhận yêu cầu |
| `PROCESSING` | Worker đang xử lý |
| `SUBMITTED` | Relay/provider đã accepted submission |
| `DEFERRED` | Provider/receiver đang trì hoãn |
| `BOUNCED` | Có bằng chứng không giao được |
| `DELIVERED` | Nguồn provider/DSN báo delivered theo định nghĩa |
| `SUBMISSION_UNKNOWN` | Không rõ outcome sau transport |
| `INBOX_OBSERVED` | Một mailbox được phép quan sát thấy ở Inbox |

Mock unit test không được tự ghi trạng thái `SUBMITTED` hay `DELIVERED` vào database production. Các state này phải xuất phát từ transport/provider/recipient observation tương ứng.

## 45. Nếu muốn thêm SMTP integration test, mở một suite riêng

Sau khi đã thành thạo mock, bước mở rộng có thể dùng GreenMail, Wiser, Mailpit hoặc một fake SMTP server có khả năng capture:

~~~text
ReceiptMailService
      |
      v
JavaMailSenderImpl (real)
      |
      v
Local SMTP test server
      |
      v
Captured MIME + SMTP conversation
~~~

### Những điều local integration kiểm tra thêm

- Client mở socket và giao tiếp SMTP tới test server.
- Server test có nhận message không.
- SMTP envelope khác MIME header thế nào.
- MIME serialize có tương thích với Jakarta Mail transport không.
- Timeout, invalid RCPT, lỗi AUTH/TLS giả lập được xử lý theo policy ra sao.

### Những điều vẫn chưa được kiểm chứng

- SMTP production account sống và được phép gửi.
- SPF/DKIM/DMARC alignment khi đi qua Internet.
- Domain/IP reputation.
- Recipient mailbox routing, spam filtering hoặc Inbox placement.

**Local SMTP test không phải Internet deliverability test.** Tách suite để tăng bằng chứng đúng tầng mà không biến mọi unit test thành network test.

### Điều kiện an toàn

Không kết nối SMTP production khi chạy bài tập; dùng server local hoặc provider sandbox được ủy quyền. Khi dùng local server, đặt host `127.0.0.1`, cổng riêng, dữ liệu test và không sử dụng credentials thật.

## 46. Trình tự thực hành từ đầu đến cuối

Một cách làm mạch lạc:

<escape>1.</escape> **Khởi tạo project.** Tạo Spring Boot application với Mail starter, Spring Boot Test và Mockito JUnit Jupiter.

<escape>2.</escape> **Định nghĩa boundary.** Tạo `RecipientPolicy` và `ReceiptMailService` dùng constructor injection.

<escape>3.</escape> **Viết test thành công.** Stub policy trả true, gọi service và capture `SimpleMailMessage`.

<escape>4.</escape> **Assert nội dung.** Kiểm tra To, From, Reply-To, subject, body và đúng một send invocation.

<escape>5.</escape> **Viết test không gửi.** Policy false và input blank phải làm mock sender không có interactions.

<escape>6.</escape> **Viết test lỗi.** Cấu hình `doThrow` cho `send(SimpleMailMessage)`, assert exception được xử lý theo hợp đồng.

<escape>7.</escape> **Tạo service MIME.** Dùng `MimeMessageHelper` với plain/HTML và attachment.

<escape>8.</escape> **Stub MIME factory.** Khi test, `createMimeMessage()` trả `new MimeMessage(Session.getInstance(...))`.

<escape>9.</escape> **Capture và inspect.** Duyệt multipart để đọc plain, HTML và attachment thay vì chỉ assert `multipart/*`.

<escape>10.</escape> **Thử negative cases.** Đổi recipient/order ID, làm policy ném lỗi, tạo attachment lỗi và quan sát đúng nhánh guard.

<escape>11.</escape> **Đọc báo cáo theo phạm vi.** Unit tests xanh nghĩa service và MIME composition đúng theo assertions, không có SMTP thật.

<escape>12.</escape> **Chọn mở rộng phù hợp.** Nếu dự án cần chứng minh transport, bổ sung local SMTP integration suite riêng.

Không cần chạy server Spring Boot thật cho các tests Mockito thuần. Chạy suite qua Gradle/Maven của project đã cấu hình khi tự thực hành; các lệnh cụ thể:

~~~bash
./gradlew test
~~~

hoặc:

~~~bash
./mvnw test
~~~

Trên Windows, dùng wrapper phù hợp (ví dụ `gradlew.bat test` hoặc `mvnw.cmd test`). Các lệnh trên là **hướng dẫn người học**, không phải test đã được chạy để tạo bài viết này.

## 47. Đọc kết quả test theo từng bước

Khi chạy test trong project của người học, các outcome có thể là:

| Hiện tượng | Nguyên nhân cần xét |
| --- | --- |
| `Wanted but not invoked` | Service không gọi đúng method/branch, policy default false, hoặc nhầm overload |
| `Too many actual invocations` | Service gọi sender nhiều lần hơn kỳ vọng |
| `UnnecessaryStubbingException` | Stub không được dùng, fixture không đúng nhánh |
| `NullPointerException` tại `createMimeMessage()` | Mock mặc định trả null, chưa stub MIME thật |
| `ClassCastException` khi parse MIME part | Test giả định content là String/Multipart sai loại |
| Assertion subject sai | Message builder/template logic sai hoặc dữ liệu test không nhất quán |
| Assertion attachment sai | MIME helper structure, content type, disposition hoặc bytes khác |
| `NoSuchMethodError` / class loading | Trộn version Jakarta Mail/Spring/Mockito |
| Mockito không thể inject | Constructor/bean setup không khớp |
| Network error trong một unit test | Có sender thật hoặc external dependency chưa được mock |
| CI pass nhưng production mail không tới | Test không quan sát SMTP/provider/mailbox; cần runbook vận hành |

### Khi Mockito nói không có invocation

Kiểm tra theo thứ tự:

1. Input validation có throw hoặc return sớm không?
2. Policy mock có stub trả true không?
3. Service có nhận **đúng mock instance** bạn đang verify không?
4. Service gọi `send(MimeMessage)` hay `send(SimpleMailMessage)`?
5. Lời gọi xảy ra sync hay ở worker/async thread?
6. Có nhánh gửi qua outbox thay vì sender trực tiếp không?

Không bắt đầu bằng cách thêm `lenient()` hoặc thay `times(1)` bằng `atLeastOnce()` để ép test xanh. Hãy tìm đúng hành vi đang diễn ra.

## 48. Khi test MIME chỉ thấy multipart nhưng thiếu HTML

Nguyên nhân thường gặp:

- Service gọi `helper.setText(plain)` thay vì `helper.setText(plain, html)`.
- HTML bị đặt nhầm là plain text.
- Test chỉ duyệt body part cấp đầu, bỏ qua multipart lồng.
- Attachment text/plain bị nhầm là plain alternative.
- Code build lỗi trước khi gọi sender.

Một MIME inspector nên:

1. Gọi `saveChanges()` nếu cần chuẩn bị message để inspect.
2. Duyệt cây `Multipart` đệ quy.
3. Kiểm tra `Part.ATTACHMENT` trước khi phân loại text.
4. Thu thập `text/plain`, `text/html` theo MIME type.
5. Đối chiếu decoded contents với fixture.

Nếu production cần inline image, `multipart/related` có thể lồng trong mixed và alternative; không cố định chỉ có hai leaf parts.

## 49. Khi test có dữ liệu Unicode

Ví dụ một subject tiếng Việt:

~~~java
helper.setSubject("Biên nhận đơn hàng số 184");
helper.setText(
        "Đơn hàng của bạn đã được ghi nhận.",
        "<p>Đơn hàng của bạn đã được ghi nhận.</p>");
~~~

Test nên parse `MimeMessage` thật và assert `getSubject()`, decoded plain/HTML giữ đúng Unicode. Không chỉ `verify(sender.send(any()))`, vì assertion đó không biết ký tự đã được encode thế nào.

### Không assert raw MIME header text một cách quá cứng

MIME có thể dùng encoded-word/transfer encoding khác nhau nhưng vẫn tương đương sau decode. Nếu mục tiêu là bảo toàn nội dung người đọc thấy, ưu tiên assert **decoded subject/body**; khi cần kiểm header wire format, viết test riêng với kỳ vọng rõ theo Jakarta Mail implementation.

## 50. Một số lỗi thiết kế test thường gặp

### 50.1. Mock sender xong tuyên bố email đã vào Inbox

Sai phạm vi. Chỉ có lời gọi mock được verify; cần SMTP/provider/mailbox evidence ở tầng tương ứng.

### 50.2. Unit test dùng tài khoản SMTP thật

Không cần thiết, dễ flaky và có nguy cơ gửi nhầm. Dùng mock trong unit; test server riêng cho transport.

### 50.3. Chỉ dùng `any(SimpleMailMessage.class)`

Không phát hiện recipient/subject/body bị sai. Dùng captor và assert các trường quan trọng.

### 50.4. Stub policy mặc định false mà quên `thenReturn(true)`

Service không gửi, verify thất bại. Chọn fixture đúng branch.

### 50.5. `createMimeMessage()` trả null

Mockito mock không tạo MIME thật. Stub bằng `Session` và `new MimeMessage`.

### 50.6. Mock cả MimeMessageHelper và MimeMessage

Chỉ chứng minh calls, không kiểm tra được actual multipart và encoding. Sử dụng MIME thật trong composition test.

### 50.7. Assert `multipart/*` rồi cho rằng HTML đúng

Multipart có thể chỉ chứa attachment. Kiểm tra cả text/plain, text/html và nội dung.

### 50.8. Dùng part index cố định

MIME có thể nested. Duyệt recursive parts với disposition/type.

### 50.9. Dùng `verifyNoInteractions` sau một call đã verify

Nó yêu cầu không có tương tác nào, không phù hợp sau sender đã được gọi. Có thể dùng `verifyNoMoreInteractions` khi muốn không có interactions khác.

### 50.10. Nhầm overload `send(MimeMessage)` và `send(SimpleMailMessage)`

Stub/verify sai chữ ký khiến test sai. Chỉ rõ message type.

### 50.11. Gộp batch thành một giả định exactly-once

Unit times(1) không chứng minh qua restart hoặc partial recipient failure.

### 50.12. Callback MimeMessagePreparator không được chạy

Mock chỉ nhận callback; nếu cần kiểm tra nội dung, `doAnswer` invoke preparator với MIME thật.

### 50.13. Gắn @SpringBootTest rồi nghĩ test có mạng thật

Nếu sender bean bị thay mock thì vẫn không có SMTP I/O.

### 50.14. Tự động retry mọi MailException

Lỗi permanent/auth/unknown outcome cần chính sách khác. Test failure classifier ở tầng adapter.

### 50.15. Assert status DELIVERED ngay sau sender.send()

Ngay cả sender thật trả bình thường cũng chỉ chứng minh submission accepted. Delivery được quan sát sau đó.

### 50.16. Xóa hoặc bỏ qua suppression để test gửi

Đừng thay business policy trong production để ép email tới; trong test dùng fixture có quyền.

### 50.17. Gửi test mail tới người lạ

Không cần. Dùng `.test` fixtures, mock và authorized seed mailbox khi thực sự đo placement.

### 50.18. Dùng dữ liệu khách hàng thật trong unit tests

Tăng rủi ro riêng tư, nhất là khi CI logs xuất thất bại assertions. Dùng dữ liệu giả.

### 50.19. Dùng sleep tùy ý cho async tests

Dễ flaky. Dùng synchronization/status có timeout và environment đúng tầng.

### 50.20. Captor đọc object đã bị sửa sau invocation

Khi message mutable được tái sử dụng, cân nhắc snapshot ngay trong `doAnswer`.

### 50.21. Mockito strict stubs bị tắt toàn cục

Che mất fixture sai. Stub đúng branch; chỉ dùng lenient có mục đích và phạm vi hẹp.

### 50.22. Test chỉ tăng coverage chứ không assert hành vi quan trọng

Một test gọi service rồi không verify output/call/exception không bảo vệ yêu cầu. Viết assertions theo acceptance criteria.

### 50.23. Test thay đổi khi refactor nhỏ không đổi hành vi

Tránh assert những implementation details không quan trọng. Ưu tiên kết quả message fields và business guards.

### 50.24. Không phân biệt test-only success với provider delivery status

Một mock không được tạo bằng chứng delivery production. Dùng tên log/status đúng nguồn.

## 51. Bài tập tự triển khai 1: thêm Message-ID nghiệp vụ

Yêu cầu: mỗi thông điệp mang một business correlation ID để thuận tiện truy vết.

### Cách tiếp cận

Với `MimeMessage`, có thể đặt một header tùy chỉnh:

~~~java
mime.setHeader("X-Notification-ID", notificationId);
~~~

Header này chứa **business reference**, không phải một cơ chế xác thực. Không dùng token bí mật hoặc dữ liệu cá nhân có thể nhận diện trực tiếp trong header. Khi dùng `SimpleMailMessage`, không có API tùy chỉnh arbitrary headers tương tự; nếu cần, chuyển sang `MimeMessage`.

### Test cần viết

1. Dùng Mockito mock `JavaMailSender`.
2. Stub `createMimeMessage()` để trả Jakarta Mail MIME thật.
3. Gọi service với `notificationId` test.
4. Capture `MimeMessage`.
5. Assert:

~~~java
assertEquals(
        "notif-184",
        actual.getHeader("X-Notification-ID", null));
~~~

6. Verify sender được gọi một lần.

### Không kết luận quá mức

Header tùy chỉnh được tạo đúng không bảo đảm provider giữ nguyên header, recipient server sử dụng nó hoặc mailbox tự deduplicate dựa trên header đó.

## 52. Bài tập tự triển khai 2: inline resource trong HTML

Yêu cầu: HTML body tham chiếu một logo theo Content-ID, không lấy logo trực tiếp từ URL bên ngoài.

Ví dụ phần HTML:

~~~html
<html>
  <body>
    <img src="cid:brand-logo" alt="Brand logo">
    <p>Your receipt is ready.</p>
  </body>
</html>
~~~

Nếu dùng `MimeMessageHelper`:

~~~java
helper.setText(plainText, htmlText);
helper.addInline(
        "brand-logo",
        new ByteArrayResource(validPngBytes),
        "image/png");
~~~

Trong bài thực hành, `validPngBytes` phải đến từ **ảnh PNG fixture hợp lệ**. Đừng truyền vài byte text rồi dán nhãn `image/png` vì MIME type sẽ không khớp actual content.

### Test cần kiểm tra

- Có body part `text/html` chứa `cid:brand-logo`.
- Có MIME part với `Content-ID` thích hợp.
- `Content-Type` phù hợp với loại ảnh.
- Phần inline không bị nhầm thành attachment download bắt buộc.
- Sender mock nhận MIME và không thực hiện SMTP I/O.

### Chú ý MIME nesting

Khi có inline và attachment đồng thời, helper có thể tạo `multipart/mixed` chứa `multipart/related` và `multipart/alternative` lồng nhau. Dùng helper đệ quy; không giả định mọi part ở root.

### Không kiểm chứng email client rendering bằng mock

MIME đúng không bảo đảm mọi email client sẽ hiển thị giống nhau. Nếu sản phẩm có yêu cầu visual rendering, cần preview/mail-client testing riêng với dữ liệu test hợp lệ.

## 53. Bài tập tự triển khai 3: kiểm tra một notification không gửi trùng trong cùng lần xử lý

Yêu cầu: nếu service nhận cùng business event hai lần **trong một transaction/test context**, tầng nghiệp vụ chỉ tạo một outbox entry.

Hướng thiết kế:

~~~text
businessKey = orderId + notificationCategory
outboxRepository.insertIfAbsent(businessKey, payloadRef)
~~~

### Test unit

Mock repository mô phỏng lần đầu insert thành công và lần thứ hai duplicate. Assert:

- Service trả cùng notification ID hoặc có quy tắc duplicate rõ.
- Không tạo thêm sender attempt trong business transaction.
- Không ghi hai records logic khác nhau cho cùng business key.

### Test tích hợp bắt buộc nếu muốn bảo đảm cạnh tranh

Database phải có unique constraint hoặc atomic upsert. Mockito `verify(repository, times(1))` trong một execution không chứng minh hai HTTP requests cùng lúc không tạo trùng. Để xác minh cạnh tranh, chạy integration test với database thật và transaction boundaries tương ứng.

## 54. Bài tập tự triển khai 4: sender failure không được biến thành DELIVERED

Giả sử notification worker có status:

~~~text
PENDING
PROCESSING
SUBMITTED
RETRY_PENDING
FAILED_PERMANENT
SUBMISSION_UNKNOWN
~~~

Yêu cầu:

1. Khi message chưa hợp lệ, không gọi sender.
2. Khi `send()` ném một lỗi đã chuẩn hóa là temporary, ghi retry schedule nếu còn budget.
3. Khi error permanent, ghi terminal failure.
4. Khi transport outcome chưa rõ, không tự resend.
5. Khi `send()` trả bình thường, ghi `SUBMITTED` chứ không `DELIVERED`.

### Test bằng Mockito

~~~text
Given: sender mock, repository mock, normalized error policy
When:  dispatcher sends valid message
Then:  verify sender invoked
       verify recordSubmissionAccepted()
       never recordDelivered()
~~~

Phần `recordSubmissionAccepted()`/`recordDelivered()` là method tên miền giả định của repository, không phải Spring Mail API. Bạn có thể tự định nghĩa interface và thêm unit tests cho worker.

### Phần mock chưa chứng minh

Không có lời gọi SMTP thật; việc biến exception thành category và hành vi relay cần test integration riêng. Nếu sender trả bình thường trong mock, đó là **một giả lập transport success**, không phải provider accepted trong môi trường thực.

## 55. Đề bài mở rộng: test multiple recipients và privacy

Yêu cầu: một email được gửi tới `To`, có thêm `Cc` và `Bcc`, nhưng người nhận Bcc không được xuất hiện trong subject/body.

### Viết test

- Capture `SimpleMailMessage` để assert `getTo()`, `getCc()`, `getBcc()`.
- Assert text/subject không chứa email address ẩn.
- Với MIME, assert headers phù hợp và không tự thêm `Bcc:` không đúng quy tắc.
- Nếu cần chứng minh **envelope recipients** thực, dùng local SMTP server có thể xem RCPT TO.

### Một điểm thường bị bỏ qua

Khi send tới nhiều recipients, provider status có thể khác nhau từng người. Mock không phân biệt partial acceptance, nên hệ thống quan trọng nên lưu per-recipient delivery state và test adapter tương ứng.

## 56. Kịch bản mẫu để người học tự kiểm tra

### Kịch bản A: một biên nhận hợp lệ

**Given**

~~~text
recipient = buyer@example.test
orderId = order-184
policy = ALLOWED
~~~

**When** service `sendReceipt(...)` được gọi.

**Then**:

~~~text
mock send invocations = 1
From = billing@example.test
Reply-To = support@example.test
To = buyer@example.test
Subject = Receipt for order order-184
Body = Your order order-184 has been recorded.
~~~

Không có SMTP network.

### Kịch bản B: policy từ chối

**Given** `policy.canReceiveTransactionalMail(...)` trả false.

**Then** `verifyNoInteractions(mailSender)`.

### Kịch bản C: recipient rỗng

**Given** recipient là chuỗi whitespace.

**Then** `IllegalArgumentException`, không gọi policy hoặc sender.

### Kịch bản D: sender giả lập lỗi

**Given** Mockito `doThrow(new MailSendException(...))`.

**Then** service ném exception theo hợp đồng đã viết, không báo delivered.

### Kịch bản E: MIME HTML + attachment

**Given** fixture `order-184`.

**Then**:

~~~text
MIME Subject = Receipt for order order-184
To = buyer@example.test
text/plain contains order-184
text/html contains order-184
attachment name = receipt.txt
attachment bytes = UTF-8("Receipt: order-184")
~~~

Kiểm tra bằng Jakarta Mail MIME parser, còn `JavaMailSender` vẫn là mock.

## 57. Tiêu chí hoàn thành bài thực hành

Sau khi tự tạo project và chạy test, có thể dùng checklist:

### Project và dependency

- [ ] Dùng Java version phù hợp với Spring Boot/Spring Framework đã chọn.
- [ ] Có Spring Mail starter.
- [ ] Có JUnit Jupiter/Mockito JUnit Jupiter.
- [ ] Unit tests không cần SMTP host/password.
- [ ] Không dùng mailbox hoặc tài khoản thật trong fixtures.

### SimpleMailMessage

- [ ] Có service dùng constructor-injected `JavaMailSender`.
- [ ] Có `RecipientPolicy` riêng.
- [ ] Test recipient/order ID hợp lệ.
- [ ] Test From, Reply-To, To, subject và body qua ArgumentCaptor.
- [ ] Test `send()` được gọi đúng một lần ở nhánh hợp lệ.
- [ ] Test policy từ chối không gọi sender.
- [ ] Test blank input không gọi sender.
- [ ] Test `MailSendException` được xử lý theo hợp đồng.

### MimeMessage

- [ ] Service có plain text và HTML alternative.
- [ ] Test mock `createMimeMessage()` trả Jakarta Mail MIME thật.
- [ ] Test `send(MimeMessage)` và capture object.
- [ ] Assert headers, UTF-8 và MIME structure.
- [ ] Duyệt multipart lồng, không cố định part index.
- [ ] Test attachment name và bytes.
- [ ] Không đưa dữ liệu người dùng vào HTML thiếu escaping.

### Mức độ bằng chứng

- [ ] Tên unit tests không chứa tuyên bố `DELIVERED` không có căn cứ.
- [ ] Không dùng unit mock để kết luận SMTP connectivity/inbox placement.
- [ ] Có kế hoạch local SMTP integration nếu cần test transport.
- [ ] Tách trạng thái `SUBMITTED` và `DELIVERED` trong mô hình production.
- [ ] Không tự retry `SUBMISSION_UNKNOWN` hoặc đã accepted.

Checklist là hướng tự thực hành. Nó **không xác nhận** project của người đọc đã chạy hoặc rằng mọi test trong bài đã được thực thi trên một ứng dụng cụ thể.

## 58. Câu hỏi tự kiểm tra

**1. Vì sao nên mock JavaMailSender trong unit test?**

Để kiểm tra message fields, business guards và lời gọi transport boundary một cách nhanh, deterministic, không mở SMTP socket.

**2. Khi Mockito verify `send()` thành công, điều gì được chứng minh?**

Một lời gọi với arguments phù hợp đã xảy ra trên mock trong execution test; không chứng minh external delivery.

**3. ArgumentCaptor dùng để làm gì?**

Lấy object message được truyền cho mock để assert `To`, `From`, `Reply-To`, subject, body hoặc MIME.

**4. Khác nhau giữa `verifyNoInteractions` và `verifyNoMoreInteractions`?**

`verifyNoInteractions` yêu cầu mock chưa bị gọi; `verifyNoMoreInteractions` yêu cầu không còn tương tác chưa verify.

**5. Một Mockito boolean method chưa stub thường trả gì?**

Thông thường trả `false`; điều này có thể khiến service đi vào nhánh không gửi.

**6. Vì sao dùng `doThrow` cho `send()`?**

Vì `send()` trả `void`, nên dùng mẫu Mockito `doThrow(...).when(mock).send(...)`.

**7. Vì sao một mock `createMimeMessage()` có thể trả null?**

Vì Mockito không tự tạo `MimeMessage` thật; cần stub factory cho test MIME.

**8. Cách tạo MimeMessage thật mà không kết nối SMTP?**

Dùng `new MimeMessage(Session.getInstance(new Properties()))` trong test.

**9. Vì sao không nên mock luôn MimeMessage?**

Nếu muốn kiểm tra MIME headers, encoding, multipart và decoded content, cần object MIME thật có thể inspect/serialize.

**10. `MimeMessageHelper.setText(plain, html)` tạo gì?**

Hai phiên bản nội dung plain text và HTML, thường biểu diễn bằng multipart alternative trong cây MIME.

**11. Vì sao duyệt MIME parts đệ quy?**

Multipart có thể lồng mixed/related/alternative; HTML không phải lúc nào cũng nằm ở một chỉ số cố định.

**12. Test attachment name đủ chứng minh bytes đúng chưa?**

Chưa. Cần tìm attachment part và đối chiếu content bytes của fixture.

**13. Test nội dung Unicode nên assert raw header encoded text hay decoded content?**

Tùy mục tiêu; để kiểm văn bản hiển thị, ưu tiên decoded subject/body. Header wire encoding cần test riêng.

**14. Khi dùng `MimeMessagePreparator`, mock tự chạy callback không?**

Không. Có thể dùng `doAnswer` để invoke callback với MIME thật khi cần test nội dung.

**15. `@SpringBootTest` có tự tạo SMTP integration test không?**

Không. Nếu `JavaMailSender` là mock, test không thực hiện network transport.

**16. Unit test có cần `spring.mail.password` không?**

Không. Mockito mock không kết nối SMTP; không đưa secrets vào test code.

**17. Có thể kiểm SPF/DKIM/DMARC bằng Mockito không?**

Không. Cần kiểm DNS/authentication và nhận message qua đường mail thật được ủy quyền.

**18. Test gửi một recipient có chứng minh toàn batch delivered không?**

Không. Từng recipient có thể được accepted/rejected/bounced khác nhau.

**19. Tại sao một lời gọi `times(1)` không bảo đảm exactly-once sau crash?**

Vì production có thể redeliver job sau khi SMTP accepted nhưng DB chưa ghi kết quả.

**20. Khi SMTP provider accepted, ứng dụng nên gọi trạng thái gì?**

Thường là `SUBMITTED` hoặc `ACCEPTED` với nghĩa rõ ràng; `DELIVERED` cần thêm bằng chứng delivery.

**21. Vì sao một exception có thể không có nghĩa thư chưa gửi?**

Mất final reply sau DATA khiến application không biết relay đã accepted hay chưa.

**22. Có nên retry ngay khi sender mock ném MailSendException?**

Không có quy tắc chung. Cần phân loại lỗi, phase, ngân sách và khả năng duplicate; dữ liệu mock chỉ minh họa lỗi.

**23. Vì sao không nên dùng tài khoản SMTP thật trong CI unit test?**

Vì gây phụ thuộc mạng/secrets, flaky tests và nguy cơ gửi nhầm.

**24. Nếu service dùng `send(MimeMessage)`, verify `send(SimpleMailMessage)` có đúng không?**

Không. Đó là các overload khác nhau; matcher phải chọn đúng type.

**25. Khi test callback, `verify(send(any(Preparator.class)))` có chứng minh headers đúng không?**

Chưa. Test phải thực thi preparator trên MIME thật và inspect nội dung.

**26. Captor có lưu snapshot tự động của message tại invocation không?**

Không; thường giữ reference. Nếu object mutable bị sửa về sau, cần snapshot theo nhu cầu test.

**27. Muốn chứng minh SMTP client thực gửi dữ liệu, dùng test gì?**

Dùng local/scripted SMTP integration với `JavaMailSenderImpl` thật và test relay.

**28. Local SMTP server nhận thư có chứng minh recipient Gmail vào Inbox không?**

Không. Nó chỉ chứng minh test relay nhận submission.

**29. Nếu muốn kiểm khả năng vào Inbox, phải dùng nguồn nào?**

Mailbox/seed account được phép hoặc hệ thống đo placement có định nghĩa rõ, cùng provider events và sample/window phù hợp.

**30. Nếu recipient bị policy chặn, điều quan trọng nhất cần assert?**

`JavaMailSender` không có lời gọi gửi và nhánh policy được áp dụng đúng.

**31. Với mã OTP đã hết hạn, mock sender nên có bao nhiêu lời gọi?**

Không có lời gọi nào nếu expiry guard đang hoạt động và yêu cầu không được phép gửi.

**32. Có nên đặt tên test là `emailDeliveredSuccessfully` khi chỉ verify sender?**

Không. Nên đặt tên theo hành vi đã quan sát: `createsExpectedMessageAndInvokesSender`.

## Kết luận

**Kiểm thử message bằng mock `JavaMailSender` là một kỹ thuật nền tảng trong dự án thực hành Spring Framework Mail.** Khi dùng đúng, Mockito giúp kiểm chứng chính xác recipient, From, Reply-To, subject, nội dung, chính sách chặn gửi, số lần gọi và việc xử lý lỗi mà không cần SMTP server hoặc Internet. Với `SimpleMailMessage`, dùng `ArgumentCaptor` để đọc các trường. Với HTML/attachment, hãy tạo `MimeMessage` thật bằng Jakarta Mail, mock `createMimeMessage()` và `send()`, rồi duyệt MIME tree để kiểm tra nội dung và bytes.

Tuy nhiên, **test xanh chỉ có giá trị trong phạm vi nó thật sự quan sát**. `verify(sender).send(...)` không chứng minh SMTP accepted, provider delivered, thư vào Inbox hay người dùng đã đọc. Vì thế, đặt tên test đúng mục tiêu, tách tầng unit/MIME/integration/provider, không đánh dấu `DELIVERED` chỉ vì mock không ném lỗi, và bổ sung SMTP integration/observability khi yêu cầu sản phẩm vượt quá message composition.

Sau bài này, bạn có thể tự viết một bộ unit tests **nhanh, tường minh, an toàn và hữu ích cho CI**, đồng thời biết chính xác khi nào cần rời khỏi Mockito để kiểm chứng hành vi transport và deliverability trong môi trường được kiểm soát.
