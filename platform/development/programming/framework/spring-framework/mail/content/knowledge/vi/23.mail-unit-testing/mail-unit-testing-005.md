# Mock JavaMailSender đúng hợp đồng cần kiểm tra

Một service Spring Boot gửi email xác nhận đơn hàng. Lập trình viên tạo mock `JavaMailSender`, gọi phương thức của service rồi kiểm tra `verify(sender).send(any(MimeMessage.class))`. Test xanh, nhưng khi chạy thật người nhận lại không có subject, email HTML thiếu bản plain text, hoặc attachment bị sai tên. Lý do là test chỉ xác nhận **một lời gọi API**, chưa xác nhận **hợp đồng mà service phải thực hiện**.

Một tình huống khác: service gọi `JavaMailSender.send(MimeMessagePreparator)` và dùng lambda để xây dựng message. Mockito mock mặc định **không thực thi lambda preparator**. Test vẫn xanh nếu chỉ kiểm tra `send(...)` được gọi, dù code xây dựng MIME trong lambda có lỗi. Đây là điểm đặc biệt quan trọng khi mock `JavaMailSender`.

Bài học này thuộc chương **Kiểm thử đơn vị** của **Spring Framework Mail**. Mục tiêu không phải mô phỏng một SMTP server trong Mockito. Mục tiêu là xác định đúng ranh giới unit test, mock đúng phương thức JavaMailSender, kiểm tra các giá trị và MIME structure mà ứng dụng hứa tạo, kiểm tra nhánh lỗi và không nhầm việc gọi mock với việc gửi thư thành công.

## 1. Hợp đồng cần kiểm tra là gì?

**Hợp đồng (contract)** trong unit test là hành vi quan sát được mà một thành phần có trách nhiệm bảo đảm cho thành phần khác. Với một mail service, hợp đồng có thể bao gồm:

- **Người nhận:** gửi đúng một hoặc nhiều địa chỉ đã được xác nhận hợp lệ.
- **Người gửi:** dùng địa chỉ From đã được cấu hình và được phép sử dụng.
- **Chủ đề:** subject đúng với loại thông báo và dữ kiện nghiệp vụ.
- **Nội dung:** plain text, HTML, encoding, các giá trị đã được escape đúng ngữ cảnh.
- **Attachment:** đúng tên, Content-Type và nội dung byte, khi use case yêu cầu.
- **Số lần yêu cầu gửi:** một lời gọi submission cho một hành động trong phạm vi unit test.
- **Xử lý lỗi:** không nuốt lỗi hoặc nhầm lỗi chuẩn bị message với lỗi gửi.
- **Không gửi khi không hợp lệ:** dữ liệu sai, người nhận bị từ chối bởi business policy hoặc notification không cần phát.

Không phải hợp đồng nào cũng thuộc `JavaMailSender`. Ví dụ “một domain event chỉ tạo một notification intent” thuộc application/outbox và cần test ở ranh giới khác; “email tới Inbox” thuộc delivery và không thể chứng minh bằng Mockito.

### 1.1. Ba tầng kiểm thử khác nhau

| Tầng | Đối tượng kiểm tra | Công cụ phù hợp | Không thể chứng minh |
|---|---|---|---|
| **Unit test application/mail service** | Dữ liệu truyền cho `JavaMailSender`, validation, exception handling, số lần gọi | Mockito + JUnit, `MimeMessage` thật trong bộ nhớ khi cần | SMTP server sẵn sàng, delivery tới Inbox |
| **Integration test mail adapter** | MIME serialization, SMTP protocol, TLS/AUTH, giao tiếp với test server | GreenMail, Mailpit hoặc SMTP catcher tương thích | Inbox placement tại provider thật |
| **End-to-end/operational test** | Submission qua ESP, bounce/webhook, authentication, provider events | Tài khoản/provider test, mailbox test, hệ thống giám sát | Bảo đảm mọi thư tương lai đều vào Inbox |

**Mockito thay thế cộng tác viên của code đang test; nó không thay thế toàn bộ giao thức SMTP.**

### 1.2. Kiểm tra hành vi thay vì khóa chặt implementation

Ví dụ yêu cầu nghiệp vụ là “gửi một email xác nhận đến địa chỉ của khách hàng, có subject đúng và nội dung rõ ràng”. Việc service dùng một biến cục bộ tên `message` hay `mail` không phải hợp đồng.

Một unit test hữu ích kiểm tra recipient, subject, body và một lần gọi `send`. Một test quá gắn implementation có thể thất bại khi refactor cách tạo `MimeMessageHelper` mà không hề thay đổi email người nhận sẽ thấy.

Ngược lại, `verify(sender).send(any(...))` một mình lại quá yếu vì bỏ qua dữ liệu quan trọng.

## 2. JavaMailSender có nhiều overload: cần mock đúng đường đi

`JavaMailSender` trong Spring hỗ trợ những cách gửi khác nhau, trong đó có:

```java
void send(SimpleMailMessage simpleMessage) throws MailException;
void send(SimpleMailMessage... simpleMessages) throws MailException;

void send(MimeMessage mimeMessage) throws MailException;
void send(MimeMessage... mimeMessages) throws MailException;

void send(MimeMessagePreparator mimeMessagePreparator)
        throws MailException;
void send(MimeMessagePreparator... mimeMessagePreparators)
        throws MailException;

MimeMessage createMimeMessage();
MimeMessage createMimeMessage(InputStream contentStream)
        throws MailException;
```

Danh sách trên minh họa các phương thức thuộc interface/hệ API Spring Mail; `SimpleMailMessage` thuộc API `MailSender` mà `JavaMailSender` kế thừa. Những method tương tự tên nhưng khác parameter type là **các hợp đồng gọi khác nhau**.

| Code trong service | Phải quan sát/test gì? | Bẫy phổ biến |
|---|---|---|
| `sender.send(SimpleMailMessage)` | `SimpleMailMessage` và các field getter | Captor của `MimeMessage` sẽ không thu được message này |
| `sender.createMimeMessage(); sender.send(MimeMessage)` | Stub `createMimeMessage()` trả `MimeMessage` thật, capture `send(MimeMessage)` | Mock `MimeMessage` làm helper thao tác trên đối tượng giả không có nội dung |
| `sender.send(MimeMessagePreparator)` | Capture và **thực thi preparator** trên `MimeMessage` thật hoặc dùng `doAnswer` | Mockito mặc định không chạy lambda |
| `sender.send(SimpleMailMessage[])` | Capture đúng mảng message, kiểm tra số lượng và dữ liệu từng phần tử | Chỉ verify `send(any(SimpleMailMessage.class))` sẽ sai overload |
| `sender.send(MimeMessage[])` | Quan sát các message trong mảng và từng MIME structure | Chỉ kiểm tra một phần tử có thể bỏ qua partial/batch behavior |

### 2.1. Tại sao Mockito dễ gây nhầm overload?

Java chọn overload ở **thời điểm biên dịch** dựa trên kiểu đối số; Mockito cũng dùng kiểu matcher/captor để chọn phương thức được verify.

Ví dụ:

```java
verify(sender).send(any(MimeMessage.class));
```

chỉ kiểm tra đường gửi `MimeMessage` tương ứng, không tự động kiểm tra `send(SimpleMailMessage)` hoặc `send(MimeMessagePreparator)`.

Nên khai báo matcher có kiểu rõ ràng:

```java
verify(sender).send(any(SimpleMailMessage.class));
verify(sender).send(any(MimeMessage.class));
verify(sender).send(any(MimeMessagePreparator.class));
```

Mỗi dòng thuộc một tình huống khác nhau; đừng chép cả ba vào cùng một test nếu service chỉ sử dụng một overload.

### 2.2. Phương thức send trả về void

Không viết:

```java
when(sender.send(any(MimeMessage.class))).thenReturn(true);
```

Vì `send` là `void`, Mockito không thể dùng `when(...).thenReturn(...)` với nó.

Để mô phỏng lỗi, dùng:

```java
doThrow(new MailSendException("SMTP unavailable"))
        .when(sender)
        .send(any(MimeMessage.class));
```

Để mô phỏng hành vi thực thi callback, dùng `doAnswer(...)`. Với happy path thông thường, mock `void` đã không làm gì; `doNothing()` thường không cần thiết.

## 3. Công cụ và cấu trúc bài test

Các ví dụ dùng:

- Java 17+ và cú pháp text block/record khi cần.
- Spring Framework Mail với `JavaMailSender`, `SimpleMailMessage` và `MimeMessageHelper`.
- Jakarta Mail namespace `jakarta.mail.*` tương ứng với Spring Framework hiện đại.
- JUnit Jupiter.
- Mockito với `MockitoExtension`.
- AssertJ để viết assertion dễ đọc.

Ví dụ dependency ở Gradle khi dùng Spring Boot và test starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là khai báo minh họa, không phải lệnh cần chạy trong bài học. Phiên bản thực tế do BOM/dependency management của dự án kiểm soát. Dự án Spring cũ dùng `javax.mail.*` thay vì `jakarta.mail.*`; không trộn hai namespace trong cùng ví dụ.

### 3.1. Test không cần mở Spring context

Một class mail service được inject qua constructor có thể test bằng:

```java
@ExtendWith(MockitoExtension.class)
class RegistrationMailServiceTest {

    @Mock
    JavaMailSender sender;

    RegistrationMailService service;

    @BeforeEach
    void setUp() {
        service = new RegistrationMailService(
                sender,
                "notifications@example.com");
    }
}
```

Các import tiêu biểu:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
```

Cách này không cần `@SpringBootTest`, không cần `application.yml`, không kết nối mạng và thường chạy nhanh. Test fixture cấp giá trị From trực tiếp thay vì cần đọc environment variable.

### 3.2. Constructor injection giúp kiểm thử rõ ràng

Nếu service tạo `new JavaMailSenderImpl()` bên trong method, việc thay thế sender để test sẽ khó hơn. Nên để sender là dependency:

```java
public final class RegistrationMailService {

    private final JavaMailSender sender;
    private final String fromAddress;

    public RegistrationMailService(
            JavaMailSender sender,
            String fromAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
    }

    // Các phương thức business-facing ở bên dưới.
}
```

Production có thể bind địa chỉ From từ cấu hình:

```java
public RegistrationMailService(
        JavaMailSender sender,
        @Value("${app.mail.from}") String fromAddress) {
    this.sender = sender;
    this.fromAddress = fromAddress;
}
```

Trong unit test, gọi constructor với một địa chỉ cố định; không cần nạp Spring container chỉ để inject cấu hình.

## 4. Test SimpleMailMessage: capture dữ liệu thực sự gửi

Đối với email văn bản đơn giản, `SimpleMailMessage` là API phù hợp. Hãy viết service đủ nhỏ để kiểm tra rõ hợp đồng.

### 4.1. Service ví dụ

```java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class RegistrationMailService {

    private final JavaMailSender sender;
    private final String fromAddress;

    public RegistrationMailService(
            JavaMailSender sender,
            String fromAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(String recipient, String displayName) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient is required");
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(recipient);
        message.setSubject("Chào mừng đến với hệ thống");
        message.setText(
                "Xin chào " + displayName
                + ", tài khoản của bạn đã sẵn sàng.");

        sender.send(message);
    }
}
```

Service này không làm SMTP trực tiếp; `JavaMailSender` là collaborator được inject.

### 4.2. Dùng ArgumentCaptor

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;

@ExtendWith(MockitoExtension.class)
class RegistrationMailServiceTest {

    @Mock
    JavaMailSender sender;

    RegistrationMailService service;

    @BeforeEach
    void setUp() {
        service = new RegistrationMailService(
                sender, "notifications@example.com");
    }

    @Test
    void sendsWelcomeWithCorrectPlainTextContract() {
        service.sendWelcome("lan@example.net", "Lan");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender, times(1)).send(captor.capture());

        SimpleMailMessage actual = captor.getValue();

        assertThat(actual.getFrom())
                .isEqualTo("notifications@example.com");
        assertThat(actual.getTo())
                .containsExactly("lan@example.net");
        assertThat(actual.getSubject())
                .isEqualTo("Chào mừng đến với hệ thống");
        assertThat(actual.getText())
                .contains("Xin chào Lan")
                .contains("tài khoản của bạn đã sẵn sàng");
    }
}
```

Test này kiểm tra:

1. Service yêu cầu gửi một `SimpleMailMessage`.
2. Dữ liệu người gửi/người nhận đúng.
3. Subject và body đáp ứng hợp đồng.
4. Không có SMTP call thật, vì `sender` là mock.

### 4.3. Vì sao không chỉ verify(any)?

Test quá yếu:

```java
service.sendWelcome("lan@example.net", "Lan");
verify(sender).send(any(SimpleMailMessage.class));
```

Nó sẽ xanh kể cả khi service đặt `To` thành địa chỉ khác, subject rỗng hoặc body thiếu tên người nhận. `ArgumentCaptor` giúp kiểm tra giá trị có ý nghĩa, không chỉ sự tồn tại của lời gọi.

### 4.4. Kiểm tra trường hợp không được gửi

```java
@Test
void doesNotSendWhenRecipientBlank() {
    assertThatThrownBy(
            () -> service.sendWelcome(" ", "Lan"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Recipient");

    verifyNoInteractions(sender);
}
```

Vì validation diễn ra trước việc tạo/sử dụng sender, test này chứng minh đầu vào thiếu recipient bị chặn ở đúng ranh giới. Trong ứng dụng thực, có thể cần validation địa chỉ email chi tiết hơn ở application boundary; không coi `isBlank()` là xác thực RFC đầy đủ hay xác minh mailbox tồn tại.

### 4.5. Verify đúng số lần, nhưng không suy ra exactly-once phân tán

`times(1)` xác minh trong **một lần thực thi unit test** service gọi mock một lần. Nó không chứng minh các HTTP retries, broker redelivery hoặc nhiều worker sẽ không tạo duplicate notification.

Đảm bảo một sự kiện chỉ tạo một yêu cầu gửi trong hệ thống phân tán cần thêm idempotency key, unique constraint/outbox và integration tests ở tầng persistence.

## 5. Mockito mock JavaMailSender, nhưng MimeMessage nên là thật

`MimeMessage` có logic dữ liệu thực sự: headers, charset, MIME parts, Content-Type, multipart boundaries và attachment. Nếu mock luôn cả `MimeMessage`, nhiều thao tác `MimeMessageHelper.setText(...)` chỉ gọi các method rỗng trên mock, khiến nội dung không tồn tại để kiểm tra.

Mẫu hữu ích:

- **Mock** `JavaMailSender` để ngăn transport thật.
- **Tạo `MimeMessage` thật trong bộ nhớ** với một `jakarta.mail.Session` không cấu hình SMTP.
- **Capture** chính `MimeMessage` được truyền vào `send`.
- **Đọc** các field và MIME part bằng Jakarta Mail API.

### 5.1. Tạo MimeMessage không mở network

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

MimeMessage realMessage =
        new MimeMessage(Session.getInstance(new Properties()));
```

`Session.getInstance(new Properties())` tạo JavaMail session dùng để dựng/đọc message trong bộ nhớ. Tạo đối tượng này **không kết nối SMTP server**. Việc truy cập network chỉ xảy ra nếu test tự mở transport hoặc gọi sender thật theo cách có mạng.

### 5.2. Stub createMimeMessage()

```java
when(sender.createMimeMessage())
        .thenAnswer(invocation ->
                new MimeMessage(
                    Session.getInstance(new Properties())));
```

Vì sao dùng `thenAnswer` tạo message mới? Mỗi lần service gọi `createMimeMessage()` sẽ nhận một object riêng. Nếu cùng một `MimeMessage` được tái sử dụng trong test nhiều lần, nội dung/headers của lần trước có thể ảnh hưởng kết quả, tạo false positive hoặc false negative.

### 5.3. Vì sao `mock(MimeMessage.class)` không phải lựa chọn mặc định?

Ví dụ không phù hợp khi mục tiêu là kiểm tra MIME:

```java
when(sender.createMimeMessage())
        .thenReturn(mock(MimeMessage.class));
```

`MimeMessageHelper` có thể gọi `setContent`, `setRecipients` và những thao tác khác lên mock, nhưng Mockito không tự xây dựng multipart hoặc render nội dung. `verify(sender).send(...)` vẫn có thể pass dù MIME thực tế không đạt hợp đồng.

Chỉ mock `MimeMessage` nếu unit test thật sự cần xác minh tương tác rất hẹp ở lớp bao ngoài; khi muốn xác nhận email gửi ra có gì, dùng message thật là lựa chọn có giá trị hơn.

## 6. Service tạo HTML, plain text và PDF attachment

Giả sử một use case gửi hóa đơn cho khách hàng. Hợp đồng yêu cầu:

- From cố định theo cấu hình.
- Một recipient trong To.
- Subject có mã hóa đơn.
- Cả `text/plain` và `text/html`.
- Charset UTF-8 để hiển thị tiếng Việt.
- PDF attachment có filename và Content-Type đúng.

### 6.1. Production code minh họa

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class InvoiceMailService {

    private final JavaMailSender sender;
    private final String fromAddress;

    public InvoiceMailService(
            JavaMailSender sender,
            String fromAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNo,
            byte[] pdfBytes) {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient is required");
        }

        if (invoiceNo == null || invoiceNo.isBlank()) {
            throw new IllegalArgumentException(
                    "Invoice number is required");
        }

        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalArgumentException(
                    "PDF content is required");
        }

        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom(fromAddress);
            helper.setTo(recipient);
            helper.setSubject("Hóa đơn " + invoiceNo);

            String plainText =
                    "Hóa đơn " + invoiceNo + " đã được phát hành.";

            String html = "<html><body>"
                    + "<p>Hóa đơn <strong>"
                    + escapeHtml(invoiceNo)
                    + "</strong> đã được phát hành.</p>"
                    + "</body></html>";

            helper.setText(plainText, html);
            helper.addAttachment(
                    "invoice-" + invoiceNo + ".pdf",
                    new ByteArrayResource(pdfBytes),
                    "application/pdf");

            sender.send(message);

        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Unable to prepare invoice email", ex);
        }
    }

    private static String escapeHtml(String value) {
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
```

Đây là một ví dụ độc lập của lớp gửi mail, không phải mẫu xử lý toàn bộ business workflow. Trong production, mã hóa đơn/filename phải được kiểm tra theo chính sách, HTML nên được render bằng template engine có auto-escaping, file lớn nên có storage/stream contract phù hợp, và sending thường cần outbox/retry riêng.

Điểm đáng test: **nội dung `MimeMessage` thực** được tạo bởi service, không phải trạng thái nội bộ của `MimeMessageHelper`.

### 6.2. Test capture MimeMessage thật

```java
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class InvoiceMailServiceTest {

    @Mock
    JavaMailSender sender;

    InvoiceMailService service;

    @BeforeEach
    void setUp() {
        service = new InvoiceMailService(
                sender, "billing@example.com");

        when(sender.createMimeMessage())
                .thenAnswer(invocation ->
                        new MimeMessage(
                            Session.getInstance(new Properties())));
    }

    @Test
    void sendsInvoiceWithExpectedHeaders() throws Exception {
        byte[] pdf = "%PDF-1.4\nsample".getBytes(
                StandardCharsets.US_ASCII);

        service.sendInvoice(
                "minh@example.net",
                "HD-1002",
                pdf);

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender, times(1)).send(captor.capture());

        MimeMessage actual = captor.getValue();
        actual.saveChanges();

        InternetAddress from =
                (InternetAddress) actual.getFrom()[0];
        InternetAddress to =
                (InternetAddress) actual
                        .getRecipients(Message.RecipientType.TO)[0];

        assertThat(from.getAddress())
                .isEqualTo("billing@example.com");
        assertThat(to.getAddress())
                .isEqualTo("minh@example.net");
        assertThat(actual.getSubject())
                .isEqualTo("Hóa đơn HD-1002");
        assertThat(actual.isMimeType("multipart/*"))
                .isTrue();
    }
}
```

`saveChanges()` hoàn thiện một số header/metadata MIME trong object test để đọc ổn định hơn. Nó **không gửi qua mạng**. Trong test, không nên assert exact giá trị `Message-ID`, MIME boundary hay ngày gửi nếu chúng do JavaMail tự tạo.

### 6.3. Kiểm tra charset bằng cách đọc nội dung, không kiểm raw header

Với tiếng Việt, mục tiêu chính là khi message được giải mã theo charset thì nội dung còn đúng. Ví dụ service tạo subject “Hóa đơn HD-1002” và test dùng `actual.getSubject()`; Jakarta Mail trả giá trị đã decode.

Không nên kiểm tra subject raw phải trùng một chuỗi encoded-word cụ thể, vì cách gói/fold header có thể thay đổi theo phiên bản/implementation mà vẫn tuân thủ MIME.

Đối với body, đọc `Part.getContent()` từ message thật để xác nhận dấu tiếng Việt và các ký tự đặc biệt còn đúng.

## 7. Đọc multipart theo cấu trúc MIME, không theo vị trí cố định

Một message có cả plain text, HTML và PDF thường có cấu trúc lồng nhau, chẳng hạn:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related (cấu trúc có thể khác theo mode)
    │   └── multipart/alternative
    │       ├── text/plain
    │       └── text/html
    └── application/pdf attachment
```

Không nên giả định:

- `getBodyPart(0)` luôn là plain text.
- `getBodyPart(1)` luôn là HTML.
- PDF luôn ở phần tử cuối.
- Cấu trúc MIME của mọi mode `MimeMessageHelper` giống nhau.

`MimeMessageHelper` hỗ trợ nhiều multipart mode; thư viện mail có thể dùng root mixed, related và alternative theo cách phù hợp. **Test nên tìm part theo Content-Type/disposition**, thay vì khóa cứng vào vị trí.

### 7.1. Helper tìm text/plain và text/html

Ví dụ tiện ích dùng trong test:

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

final class MimeTestSupport {

    private MimeTestSupport() {}

    static String findBodyText(Part part, String mimeType)
            throws Exception {

        boolean isAttachment =
                Part.ATTACHMENT.equalsIgnoreCase(
                        part.getDisposition())
                || part.getFileName() != null;

        if (!isAttachment && part.isMimeType(mimeType)) {
            Object content = part.getContent();

            if (content instanceof String text) {
                return text;
            }
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                String found = findBodyText(
                        multipart.getBodyPart(i), mimeType);

                if (found != null) {
                    return found;
                }
            }
        }

        return null;
    }
}
```

Tiện ích này minh họa cách duyệt cây MIME. Trong test nâng cao có thể cần phân biệt inline resource, multipart/alternative preference và trường hợp `text/plain` attachment. Đối với hợp đồng trong ví dụ, tìm plain/HTML body không có filename hoặc attachment disposition là đủ.

### 7.2. Assertion cho plain text và HTML

Bổ sung vào test đã capture `actual`:

```java
String plain = MimeTestSupport.findBodyText(
        actual, "text/plain");
String html = MimeTestSupport.findBodyText(
        actual, "text/html");

assertThat(plain)
        .contains("Hóa đơn HD-1002")
        .contains("đã được phát hành");

assertThat(html)
        .contains("<strong>HD-1002</strong>")
        .contains("đã được phát hành");
```

Như vậy test kiểm tra **hai phiên bản nội dung** thật, thay vì chỉ `verify(sender).send(...)`.

### 7.3. HTML escaping là một hợp đồng riêng

Khi body HTML có dữ liệu không tin cậy, cần kiểm tra dữ liệu đó không được chèn như markup tùy ý. Ví dụ:

```java
service.sendInvoice(
        "minh@example.net",
        "HD<&1002",
        pdf);

MimeMessage actual = captureSentMimeMessage(sender);

String html = MimeTestSupport.findBodyText(
        actual, "text/html");

assertThat(html)
        .contains("HD&lt;&amp;1002")
        .doesNotContain("<strong>HD<&1002</strong>");
```

`captureSentMimeMessage` trong ví dụ là helper test có thể tự viết dựa trên `ArgumentCaptor<MimeMessage>` như phần trước. Nếu dữ liệu được render bằng Thymeleaf, nên test rendering ở tầng template riêng hoặc qua adapter thật tùy kiến trúc.

### 7.4. Tránh so sánh raw MIME byte-for-byte

Một message có thể được encode base64, quoted-printable hoặc có MIME boundary ngẫu nhiên. Hai message khác bytes nhưng giống hành vi từ góc nhìn người nhận.

Những assertion dễ vỡ:

- So sánh toàn bộ `message.writeTo(outputStream)` với file text cố định.
- Assert exact boundary string.
- Assert thứ tự header không thuộc contract.
- Assert giá trị `Message-ID` ngẫu nhiên.

Chỉ dùng byte-for-byte khi chính **wire representation** là yêu cầu đặc biệt và test được thiết kế có kiểm soát; phần lớn unit test business email không cần khóa chặt đến mức đó.

## 8. Kiểm tra attachment: tên, kiểu MIME và byte content

Đối với hóa đơn, kiểm tra `addAttachment` được gọi là chưa đủ. Bạn cần xác nhận message cuối cùng có attachment đúng.

### 8.1. Tìm attachment theo filename

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

final class AttachmentTestSupport {

    private AttachmentTestSupport() {}

    static Part findAttachment(Part part, String expectedName)
            throws Exception {

        if (expectedName.equals(part.getFileName())) {
            return part;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                Part found = findAttachment(
                        multipart.getBodyPart(i),
                        expectedName);

                if (found != null) {
                    return found;
                }
            }
        }

        return null;
    }
}
```

### 8.2. Assert nội dung thực

```java
Part attachment = AttachmentTestSupport.findAttachment(
        actual, "invoice-HD-1002.pdf");

assertThat(attachment).isNotNull();
assertThat(attachment.isMimeType("application/pdf"))
        .isTrue();

byte[] actualBytes;
try (InputStream in = attachment.getInputStream()) {
    actualBytes = in.readAllBytes();
}

assertThat(actualBytes).containsExactly(pdf);
```

Cần import `java.io.InputStream`. Với `MimeMessageHelper`, attachment có thể được encode qua MIME transfer encoding; `getInputStream()` trả nội dung sau khi decode để so với byte đầu vào.

### 8.3. Nội dung PDF trong unit test

Sử dụng vài bytes giả lập là đủ để kiểm tra adapter **đính kèm đúng bytes**. Nó không chứng minh file là một PDF hợp lệ về mặt cấu trúc hay ứng dụng đọc được; kiểm tra PDF thực sự là phạm vi test khác.

### 8.4. Attachment lớn và InputStreamSource

`ByteArrayResource` phù hợp ví dụ nhỏ; file lớn trong production có thể được đưa qua storage reference/stream. Với `MimeMessageHelper.addAttachment`, cần chú ý nguồn stream phải đáp ứng contract đọc nội dung của Jakarta Mail; một số nguồn có thể bị đọc nhiều lần khi tạo/serialize message.

Unit test nên làm rõ:

- Ai sở hữu stream?
- Dữ liệu có được mở/đọc lặp lại hay không?
- Có đóng resource sau sử dụng không?
- Test có kiểm tra content/filename đúng chứ không chỉ sự tồn tại của object resource?

Không tạo một `InputStream` đã tiêu thụ và đưa vào đường gửi mà không có cơ chế cung cấp stream mới khi API yêu cầu.

## 9. Inline image khác attachment

Email HTML có thể tham chiếu ảnh inline bằng Content-ID (CID):

```html
<img src="cid:company-logo" alt="Logo">
```

Service thường dùng:

```java
helper.setText(html, true);
helper.addInline(
        "company-logo",
        new ByteArrayResource(logoPng),
        "image/png");
```

Với inline resource, contract có thể là:

- HTML chứa `cid:company-logo`.
- MIME part có `Content-ID` tương ứng, thường biểu diễn dưới dạng `<company-logo>`.
- Content-Type `image/png`.
- Disposition/filename phù hợp inline.
- Binary content đúng.

Lưu ý về `MimeMessageHelper`: **gọi `setText(...)` trước `addInline(...)`** là thứ tự được khuyến nghị để một số mail reader liên kết CID part đúng. Unit test MIME có thể xác nhận structure, nhưng **không thể chứng minh mọi mail client sẽ hiển thị giống nhau**.

Không nhầm inline image với attachment mà người nhận tải xuống. Hai loại MIME part có ngữ nghĩa khác dù cùng chứa dữ liệu nhị phân.

## 10. Trường hợp đặc biệt: send(MimeMessagePreparator)

Nhiều service không gọi `createMimeMessage()` trực tiếp. Thay vào đó, chúng truyền callback:

```java
public final class PreparedWelcomeMailService {

    private final JavaMailSender sender;
    private final String fromAddress;

    public PreparedWelcomeMailService(
            JavaMailSender sender,
            String fromAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(String recipient, String name) {
        sender.send((MimeMessagePreparator) mime -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, false, "UTF-8");

            helper.setFrom(fromAddress);
            helper.setTo(recipient);
            helper.setSubject("Chào mừng " + name);
            helper.setText("Xin chào " + name + "!");
        });
    }
}
```

`MimeMessagePreparator` nằm trong package `org.springframework.mail.javamail`; dùng cast trong ví dụ để chọn rõ overload nhận preparator.

### 10.1. Vì sao mock mặc định có thể gây false positive?

Mockito mock của `JavaMailSender` là một object giả. Lời gọi:

```java
sender.send((MimeMessagePreparator) mime -> {
    // Mã xây dựng message ở đây.
});
```

chỉ đi tới phương thức `send` đã mock. Nếu không stub thêm, Mockito **không gọi `prepare(mime)`**, vì callback chỉ được JavaMailSender implementation thật gọi khi gửi.

Test:

```java
service.sendWelcome("lan@example.net", "Lan");
verify(sender).send(any(MimeMessagePreparator.class));
```

chỉ cho biết callback đã được **truyền vào**, không cho biết callback chạy thành công hoặc chuẩn bị message đúng.

### 10.2. Cách 1: capture preparator rồi thực thi trên MimeMessage thật

```java
@Test
void preparatorProducesCorrectWelcomeMime() throws Exception {
    JavaMailSender sender = mock(JavaMailSender.class);

    PreparedWelcomeMailService service =
            new PreparedWelcomeMailService(
                    sender, "hello@example.com");

    service.sendWelcome("lan@example.net", "Lan");

    ArgumentCaptor<MimeMessagePreparator> captor =
            ArgumentCaptor.forClass(
                    MimeMessagePreparator.class);

    verify(sender).send(captor.capture());

    MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties()));

    // Quan trọng: unit test chủ động chạy callback.
    captor.getValue().prepare(message);
    message.saveChanges();

    assertThat(message.getSubject())
            .isEqualTo("Chào mừng Lan");

    InternetAddress to = (InternetAddress) message
            .getRecipients(Message.RecipientType.TO)[0];
    assertThat(to.getAddress())
            .isEqualTo("lan@example.net");

    String plain = MimeTestSupport.findBodyText(
            message, "text/plain");
    assertThat(plain).contains("Xin chào Lan");
}
```

Cần import `MimeMessagePreparator`, `Session`, `Message`, `InternetAddress`, `MimeMessage`, `Properties` và các Mockito/AssertJ API tương ứng.

Đây là cách rõ nhất khi muốn phân biệt:

1. Service đã gửi một preparator.
2. Preparator thực sự xây dựng được message với nội dung đúng.

### 10.3. Cách 2: doAnswer thực thi callback ngay khi send được gọi

```java
@Test
void executesPreparatorThroughMockSender() throws Exception {
    JavaMailSender sender = mock(JavaMailSender.class);
    AtomicReference<MimeMessage> built = new AtomicReference<>();

    doAnswer(invocation -> {
        MimeMessagePreparator preparator =
                invocation.getArgument(
                        0, MimeMessagePreparator.class);

        MimeMessage mime = new MimeMessage(
                Session.getInstance(new Properties()));

        preparator.prepare(mime);
        mime.saveChanges();
        built.set(mime);
        return null; // send(...) là void
    }).when(sender).send(any(MimeMessagePreparator.class));

    PreparedWelcomeMailService service =
            new PreparedWelcomeMailService(
                    sender, "hello@example.com");

    service.sendWelcome("lan@example.net", "Lan");

    verify(sender).send(any(MimeMessagePreparator.class));
    assertThat(built.get()).isNotNull();
    assertThat(built.get().getSubject())
            .isEqualTo("Chào mừng Lan");
}
```

Cần import `java.util.concurrent.atomic.AtomicReference`. Cách này làm mock sender chủ động gọi callback khi service yêu cầu send. Nó hữu ích nếu cần mô phỏng hành vi tương tác với preparator gần với cách implementation thực thi.

**Không dùng `doAnswer` này như mô hình SMTP server**: nó vẫn không mở network, không mô phỏng TLS/AUTH và không cho biết provider sẽ chấp nhận message.

### 10.4. Vì sao không nên mock chính preparator của service?

Nếu service phải tạo preparator từ dữ liệu nghiệp vụ, việc test bằng một preparator giả khác có thể bỏ qua phần code cần kiểm thử. Cách đúng là capture **preparator mà service thực sự truyền**, rồi kiểm tra nó tạo gì.

### 10.5. Lỗi trong preparator và đặc điểm của mock

Implementation thật của `JavaMailSender.send(MimeMessagePreparator)` có thể chuyển lỗi chuẩn bị message thành `MailPreparationException` theo cơ chế Spring Mail. Mockito mock trống không tự chạy callback nên cũng không tự ném lỗi chuẩn bị.

Nếu muốn kiểm tra failure path khi callback lỗi:

- Capture/prep trên `MimeMessage` thật và quan sát exception tại điểm `prepare`.
- Hoặc dùng `doAnswer` mô phỏng quy tắc chuyển lỗi mà application thực sự phụ thuộc, nếu đó là hợp đồng.
- Với yêu cầu xác minh Spring implementation bọc ngoại lệ như thế nào, chuyển sang integration/adapter test phù hợp.

Đừng tạo false confidence chỉ vì mock không ném exception trong khi callback còn chưa chạy.

## 11. Mock overload gửi mảng/batch

`JavaMailSender` có thể nhận nhiều `SimpleMailMessage` hoặc nhiều `MimeMessage` trong một lời gọi batch.

### 11.1. Ví dụ service gửi nhiều SimpleMailMessage

```java
public void sendBatch(List<String> recipients) {
    SimpleMailMessage[] messages = recipients.stream()
            .map(recipient -> {
                SimpleMailMessage mail = new SimpleMailMessage();
                mail.setFrom("notifications@example.com");
                mail.setTo(recipient);
                mail.setSubject("Thông báo");
                mail.setText("Nội dung");
                return mail;
            })
            .toArray(SimpleMailMessage[]::new);

    sender.send(messages);
}
```

Nếu cần kiểm tra hợp đồng batch, có thể dùng:

```java
ArgumentCaptor<SimpleMailMessage[]> captor =
        ArgumentCaptor.forClass(SimpleMailMessage[].class);

service.sendBatch(List.of(
        "a@example.net",
        "b@example.net"));

verify(sender).send(captor.capture());

SimpleMailMessage[] actual = captor.getValue();

assertThat(actual).hasSize(2);
assertThat(actual[0].getTo())
        .containsExactly("a@example.net");
assertThat(actual[1].getTo())
        .containsExactly("b@example.net");
```

Khi dùng Mockito version có cách xử lý varargs đặc thù, matcher/captor mảng cần được chọn đúng kiểu `SimpleMailMessage[]`. Nếu test báo sai overload, kiểm tra chữ ký method được Java chọn và phiên bản Mockito đang dùng.

### 11.2. Không nhầm batch request với delivery từng message

Một lời gọi `send(messages)` có thể gây partial failure trong implementation thật. Mock không mô phỏng mặc định việc một phần tử đã gửi thành công, phần tử khác thất bại.

Nếu application phải xử lý per-recipient status, hãy thiết kế contract/adapter cho phép quan sát kết quả tương ứng và có integration tests. Chỉ capture một mảng không chứng minh việc retry partial failure an toàn.

### 11.3. Vì sao tránh stub varargs quá tổng quát?

Một stub như `doNothing().when(sender).send(any())` có thể không rõ overload hoặc gây lỗi biên dịch trong API overload rộng. Nên dùng matcher có type rõ hoặc capture đúng mảng.

## 12. Kiểm thử lỗi từ JavaMailSender đúng loại

Một unit test tốt không chỉ kiểm tra happy path. Khi sender ném `MailException`, mail service phải thực hiện đúng chính sách:

- Lan truyền lỗi kỹ thuật lên adapter/application boundary?
- Chuyển sang lỗi trung lập của ứng dụng?
- Ghi nhận trạng thái retry/outbox?
- Không đánh dấu notification đã submitted khi chưa có bằng chứng?

Không nên viết code nuốt lỗi:

```java
try {
    sender.send(message);
} catch (MailException ex) {
    log.warn("Could not send mail");
    // Không báo cho caller / không lưu retry.
}
```

Nếu caller tưởng send thành công và đánh dấu business operation hoàn tất, một notification quan trọng có thể bị mất.

### 12.1. Ví dụ service chuyển lỗi

Giả sử application đặt một exception trung lập:

```java
public class NotificationSubmissionException
        extends RuntimeException {

    public NotificationSubmissionException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Adapter/service:

```java
public void submit(OutgoingEmail email) {
    MimeMessage message = buildMimeMessage(email);

    try {
        sender.send(message);
    } catch (MailException ex) {
        throw new NotificationSubmissionException(
                "Mail submission failed", ex);
    }
}
```

`OutgoingEmail`, `buildMimeMessage` và exception là abstraction do ứng dụng sở hữu trong ví dụ; không phải lớp có sẵn trong Spring.

### 12.2. Mockito doThrow cho void send

```java
doThrow(new MailSendException("SMTP server unavailable"))
        .when(sender)
        .send(any(MimeMessage.class));
```

Sau khi gọi service, có thể assert:

```java
assertThatThrownBy(() -> service.submit(email))
        .isInstanceOf(
                NotificationSubmissionException.class)
        .hasCauseInstanceOf(MailSendException.class);

verify(sender, times(1))
        .send(any(MimeMessage.class));
```

Test này kiểm tra lớp chuyển lỗi nhưng **không phân loại được tất cả mã SMTP 4xx/5xx**. Nếu retry policy dựa vào SMTP stage/code, hãy kiểm tra classifier riêng bằng những exception/metadata phù hợp hoặc integration test với test transport.

### 12.3. Authentication, preparation và send errors khác nhau

| Loại lỗi | Nguồn thường gặp | Kiểm tra unit test |
|---|---|---|
| `MailAuthenticationException` | SMTP AUTH | Không đánh dấu thành công, phân loại đúng theo policy |
| `MailSendException` | Transport send failure | Chuyển lỗi/ghi retry theo application contract |
| `MailParseException` | Dữ liệu/format message | Không retry SMTP mù quáng |
| `MailPreparationException` | Chuẩn bị message, đặc biệt đường preparator | Không giả định callback đã chạy trong mock |
| `MessagingException` | Các thao tác Jakarta Mail/MIME | Xác minh code chuẩn bị message xử lý hợp lý |

Không coi mọi `MailException` là tạm thời để retry. Lỗi chứng chỉ TLS, credential sai, dữ liệu MIME không hợp lệ hoặc recipient bị từ chối vĩnh viễn có cách xử lý khác.

### 12.4. Bẫy khi tạo exception giả

Nếu test tạo một `MailSendException("SMTP unavailable")` không có nested cause, test chỉ kiểm tra ứng dụng phản ứng với **loại exception ngoài**. Nó không đủ để chứng minh classifier có thể nhận diện `ConnectException`, `SocketTimeoutException`, SMTP reply code và tình huống submission unknown.

Với classifier, tạo các case riêng có cause chain có cấu trúc và kiểm tra thuật toán phân loại tương ứng; tránh khẳng định test đã bao phủ network semantics khi chưa làm.

## 13. Kiểm thử “không gọi sender” khi business rule từ chối

Một use case có thể cấm gửi trong các trường hợp:

- Người nhận chưa xác minh địa chỉ nếu loại thông báo yêu cầu.
- Một thông báo marketing không có consent.
- Khách hàng đã unsubscribe.
- Event đã được xử lý và notification intent đã tồn tại.
- Email OTP đã hết hạn.
- Không tìm thấy tài liệu đính kèm bắt buộc.

Test tại đúng tầng:

```java
@Test
void doesNotSubmitWhenRecipientIsSuppressed() {
    when(suppressionPolicy.isSuppressed(
            "lan@example.net"))
            .thenReturn(true);

    notificationUseCase.execute(
            notificationFor("lan@example.net"));

    verifyNoInteractions(mailDeliveryPort);
}
```

Ở đây `suppressionPolicy`, `mailDeliveryPort`, `notificationUseCase` là cộng tác viên application-level minh họa. Nếu use case chỉ tạo outbox record, assertion đúng phải là **không tạo intent** chứ không phải `verifyNoInteractions(javaMailSender)`, vì JavaMailSender vốn không được gọi tại use case.

### 13.1. “No interactions” chỉ có ý nghĩa đúng ranh giới

Không nên dùng `verifyNoInteractions(sender)` như một yêu cầu cho mọi test lỗi. Có thể service đã chuẩn bị message và gọi `createMimeMessage()` trước khi phát hiện input sai; khi đó test cần quyết định đây là bug validation order hay chỉ là chi tiết nội bộ.

Khi validation phải diễn ra trước I/O/submission, test “không gửi” có thể dùng:

```java
verify(sender, never())
        .send(any(MimeMessage.class));
```

Điều này kiểm tra đúng “không submit” mà không đòi hỏi “không tạo object” nếu không thuộc hợp đồng.

### 13.2. Không gửi duplicate là hợp đồng của outbox, không phải mock SMTP

Ví dụ một domain event được xử lý hai lần:

```java
handler.handle(event);
handler.handle(event);
```

Nếu handler chỉ ghi outbox, test nên assert **số outbox rows hoặc số lần insert hiệu quả** bằng unique key. Không thể chứng minh hệ thống chống duplicate bằng `verify(sender, times(1))` khi gửi là một tác vụ worker chạy sau transaction.

## 14. Kiểm thử nhiều recipient, Cc và Bcc

Nếu application contract hỗ trợ nhiều recipient, test cần xem recipient type.

```java
InternetAddress[] to = (InternetAddress[])
        Arrays.copyOf(
                actual.getRecipients(Message.RecipientType.TO),
                actual.getRecipients(
                        Message.RecipientType.TO).length,
                InternetAddress[].class);
```

Đoạn trên minh họa thao tác lấy mảng; đơn giản hơn có thể assert trực tiếp từng `Address`:

```java
Address[] toRecipients =
        actual.getRecipients(Message.RecipientType.TO);
Address[] ccRecipients =
        actual.getRecipients(Message.RecipientType.CC);
Address[] bccRecipients =
        actual.getRecipients(Message.RecipientType.BCC);

assertThat(toRecipients).hasSize(1);
assertThat(((InternetAddress) toRecipients[0]).getAddress())
        .isEqualTo("buyer@example.net");
assertThat(ccRecipients).isNullOrEmpty();
assertThat(bccRecipients).isNullOrEmpty();
```

Với thư gửi riêng cho từng khách hàng, không vô tình để danh sách recipient cá nhân trong `To` hoặc `Cc`. Nếu Bcc được sử dụng, test cần phân biệt **envelope recipients** và headers: Bcc có thể hiện diện trong đối tượng message khi chuẩn bị, nhưng không được phơi bày cho người nhận cuối dưới dạng header công khai khi transport xử lý.

Unit test kiểm tra object ở đầu vào sender; hành vi loại bỏ/ẩn Bcc trong SMTP transport cần kiểm thử ở tầng thích hợp.

## 15. Subject, Reply-To và Unicode

### 15.1. Subject có dấu tiếng Việt

```java
helper.setSubject("Xác nhận đơn hàng đã thanh toán");
```

Test:

```java
assertThat(actual.getSubject())
        .isEqualTo("Xác nhận đơn hàng đã thanh toán");
```

Không assert raw encoded-word trong `Subject`. Jakarta Mail có thể mã hóa header theo MIME để vận chuyển và decode khi đọc.

### 15.2. From display name

```java
helper.setFrom(
        new InternetAddress(
                "support@example.com",
                "Bộ phận hỗ trợ",
                "UTF-8"));
```

Test:

```java
InternetAddress from =
        (InternetAddress) actual.getFrom()[0];

assertThat(from.getAddress())
        .isEqualTo("support@example.com");
assertThat(from.getPersonal())
        .isEqualTo("Bộ phận hỗ trợ");
```

Kiểm tra logical decoded value, không khóa cứng cách fold header.

### 15.3. Reply-To

Nếu business contract yêu cầu reply tới bộ phận hỗ trợ, xác minh `Reply-To` riêng:

```java
helper.setReplyTo("helpdesk@example.com");
```

```java
InternetAddress replyTo =
        (InternetAddress) actual.getReplyTo()[0];

assertThat(replyTo.getAddress())
        .isEqualTo("helpdesk@example.com");
```

Đừng nhầm `Reply-To` với envelope `MAIL FROM` hay `Return-Path`; đó là những khái niệm khác trong SMTP/email.

### 15.4. Không tự kiểm tra IP reputation bằng unit test header

From/Reply-To/subject đúng không chứng minh SPF/DKIM/DMARC hoặc PTR đúng. Những cấu hình đó thường thuộc domain DNS và SMTP provider/MTA, không thể chứng minh bằng mock JavaMailSender.

## 16. Ngày giờ, ID và nội dung động: giữ test xác định

Email thường chứa:

- Ngày phát hành hóa đơn.
- Link xác minh có thời hạn.
- Số đơn hàng.
- Tên người nhận.
- Locale/time zone.
- Trace hoặc notification ID.

Nếu dùng `Instant.now()` trực tiếp trong service, assertion có thể phụ thuộc thời gian chạy. Tốt hơn là inject `Clock`:

```java
public final class PasswordResetMailContent {

    private final Clock clock;

    public PasswordResetMailContent(Clock clock) {
        this.clock = clock;
    }

    public String buildExpiryNotice(Duration validity) {
        Instant expiresAt = clock.instant().plus(validity);
        return "Liên kết hết hạn lúc " + expiresAt;
    }
}
```

Trong test:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-12T08:00:00Z"),
        ZoneOffset.UTC);

PasswordResetMailContent content =
        new PasswordResetMailContent(fixedClock);

assertThat(content.buildExpiryNotice(Duration.ofMinutes(15)))
        .contains("2026-11-12T08:15:00Z");
```

Dữ kiện như token, UUID và URL cũng nên được cấp qua dependency/fixture có kiểm soát thay vì tạo ngẫu nhiên rồi assert chuỗi cố định.

### 16.1. Link không chỉ được kiểm bằng contains

Một link xác minh có thể đúng host nhưng sai scheme hoặc chứa token bị escape không đúng. Với link quan trọng, test content factory/template riêng:

- Scheme bắt buộc HTTPS theo policy.
- Host/path thuộc allowlist.
- Token được URL-encode theo ngữ cảnh.
- Query parameters đúng.
- Không đưa secret vào log.
- Hạn dùng không vượt quy tắc nghiệp vụ.

Mockito không thay việc kiểm tra link và escaping; nó chỉ giúp thu được message mà service đã chuẩn bị.

## 17. Unit test với @MockitoBean hoặc @MockBean khi thật sự cần Spring context

Phần lớn test của mail service không cần Spring context. Tuy nhiên, nếu cần kiểm tra wiring hoặc một controller/use case được tạo bởi Spring:

- Trong các phiên bản Spring Framework có hỗ trợ bean override testing, có thể dùng `@MockitoBean` để thay `JavaMailSender` trong test ApplicationContext.
- Một số dự án Spring Boot cũ dùng `@MockBean`; API này đã được thay thế trong các phiên bản mới hơn, nên chọn annotation theo phiên bản thực tế.
- Nếu chỉ test logic của một service thuần constructor injection, `@Mock` và `MockitoExtension` vẫn gọn và nhanh hơn.

Ví dụ hướng tổ chức với một ứng dụng Spring có API bean override tương ứng:

```java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @MockitoBean
    JavaMailSender javaMailSender;

    @Autowired
    OrderWorkflowService workflowService;

    @Test
    void requestsEmailAfterWorkflow() {
        // Cấu hình những dependency cần thiết.
        // Gọi workflowService.
        // Xác minh đúng contract tại ranh giới này.
    }
}
```

Đoạn trên là ví dụ khung, **không phải unit test độc lập**; việc khởi tạo context, transaction listener hoặc async boundary có thể ảnh hưởng thời điểm verify. Không chuyển toàn bộ unit tests thành `@SpringBootTest` chỉ vì muốn mock sender.

### 17.1. Constructor injection vs field injection

Nếu service nhận dependencies trong constructor, test dễ dựng object và chủ động cấu hình. Field injection qua `@Autowired` ở class cần test thường làm unit test nặng hơn hoặc cần reflection để set field.

### 17.2. @InjectMocks không giải quyết mọi vấn đề

Mockito `@InjectMocks` giúp ghép mock vào instance trong nhiều trường hợp, nhưng không thay việc xác định constructor, cấu hình động hoặc giá trị From. Nếu service cần `Clock`, property và template renderer, dựng explicit constructor trong `@BeforeEach` thường dễ đọc và chắc chắn hơn.

## 18. Khi service gửi bất đồng bộ hoặc dùng outbox

Nhiều kiến trúc không gọi `JavaMailSender.send` ngay trong use case. Chẳng hạn:

```text
OrderConfirmed use case
        |
        v
NotificationOutboxRepository.insertIfAbsent(...)
        |
        v
Database commit
        |
        v
Scheduled/queue worker
        |
        v
SpringMailDeliveryAdapter
        |
        v
JavaMailSender.send(...)
```

### 18.1. Hợp đồng unit test của use case

Kiểm tra:

- Event được ánh xạ thành notification intent đúng.
- Idempotency key đúng.
- Dữ liệu cần gửi được lưu.
- Không tạo trùng notification.
- Transaction/policy được điều phối phù hợp.

Không đòi hỏi `verify(javaMailSender).send(...)` trong unit test use case nếu use case không trực tiếp gửi.

### 18.2. Hợp đồng unit test của worker

Kiểm tra:

- Chỉ xử lý notification đã claim hợp lệ.
- Gửi **một attempt** qua mail delivery port.
- Chuyển trạng thái `SUBMITTED` khi transport báo thành công.
- Lưu `RETRY_WAIT` theo backoff với lỗi tạm thời.
- Dừng hoặc đối chiếu khi kết quả submission không rõ.
- Không tạo outbox row mới cho mỗi retry.

Mock outbound port hoặc sender theo ranh giới đang test; đừng mock một dependency quá xa so với lớp đang kiểm tra.

### 18.3. Hợp đồng unit test của SpringMailDeliveryAdapter

Đây mới là nơi phù hợp để mock `JavaMailSender`, capture `MimeMessage` và kiểm tra From/To/Subject/MIME.

Một adapter không nên tự sinh retry không giới hạn trong `send`; application/outbox worker quản lý attempt, trạng thái và idempotency.

### 18.4. Test async cần có điểm đồng bộ rõ ràng

Một test gọi service `@Async` rồi lập tức `verify(sender)` có thể thất bại ngẫu nhiên vì lời gọi gửi chưa chạy. Cần thiết kế synchronization/await phù hợp ở integration test, hoặc test logic bên trong method đồng bộ bằng cách gọi trực tiếp một component được tách riêng.

Không dùng `Thread.sleep(500)` như một cách bảo đảm event đã xử lý. Một sleep cố định không chứng minh hệ thống đã ổn định.

## 19. Phân biệt verify(send) với xác minh SMTP thật

Giả sử test pass:

```java
verify(sender, times(1)).send(any(MimeMessage.class));
```

Điều có thể kết luận: **đoạn code đang test đã gọi mock sender với một đối tượng MimeMessage đúng overload một lần**.

Không thể kết luận:

- DNS SMTP host resolve được.
- TCP port có thể kết nối.
- STARTTLS hoạt động.
- Trust store và certificate chain hợp lệ.
- SMTP AUTH thành công.
- Recipient được MX chấp nhận.
- SPF/DKIM/DMARC hợp lệ.
- Attachment hiển thị giống nhau ở mọi client.
- Provider không bounce.
- Email đã tới Inbox.
- Retry sau process crash sẽ không tạo duplicate.

Những tuyên bố này cần các phép kiểm tra khác. Không viết báo cáo “Email sent successfully” dựa trên Mockito verify; viết đúng là “mail submission request was issued to mocked JavaMailSender”.

## 20. Thiết kế test theo ma trận hợp đồng

Một bảng kiểm tình huống hữu ích cho mail service gửi hóa đơn:

| Case | Dữ kiện đầu vào | Assertion quan trọng |
|---|---|---|
| Happy path | Recipient hợp lệ, mã hóa đơn, PDF bytes | `send(MimeMessage)` một lần; From/To/Subject đúng |
| Plain + HTML | Body có tiếng Việt | Tìm được cả `text/plain` và `text/html`, decode đúng |
| Attachment | PDF bytes và filename | MIME part `application/pdf` có bytes đúng |
| Invalid recipient | Blank/null | Throw validation exception; không submit |
| Missing attachment | Không có file bắt buộc | Không gửi email thiếu hóa đơn |
| HTML special chars | Mã/tên có `&`, `<`, `>` | HTML được escape theo ngữ cảnh |
| Mail transport failure | Sender ném `MailSendException` | Chuyển lỗi/lan truyền đúng, không báo submitted |
| Preparator callback | Service dùng `MimeMessagePreparator` | Capture và thực thi callback trên real message |
| Dynamic date | Có `Clock` cố định | Expiry/date đúng, không phụ thuộc thời gian thực |
| Batch | Hai recipient | Đúng overload array và dữ liệu từng phần tử |
| Outbox duplicate | Cùng event ID được xử lý lại | Không tạo notification intent mới |
| Worker retry | Lỗi tạm thời | Cùng notification ID, next attempt theo policy |
| Submission uncertain | Timeout sau DATA | Không giả định thư chắc chắn chưa được gửi |

Không phải một class unit test phải chứa tất cả case; chia theo trách nhiệm. Đặc biệt, outbox duplicate, worker claim và kết quả SMTP thật thuộc các lớp khác nhau.

## 21. Những lỗi phổ biến khi mock JavaMailSender

### 21.1. Chỉ verify “any message”

`verify(sender).send(any(MimeMessage.class))` không kiểm dữ liệu. Dùng `ArgumentCaptor` và đọc MIME thật nếu nội dung thuộc contract.

### 21.2. Mock MimeMessage thay vì dùng object thật

`MimeMessageHelper` thao tác trên mock có thể không tạo dữ liệu. Dùng `MimeMessage(Session.getInstance(new Properties()))` trong test.

### 21.3. Quên stub createMimeMessage()

Mockito trả `null` mặc định cho phương thức tạo object nếu không stub. Service có thể ném `NullPointerException` trước khi send. Dùng `thenAnswer` trả real MIME riêng cho mỗi lần gọi.

### 21.4. Dùng when/thenReturn với send void

`send(...)` trả `void`. Dùng `doThrow`, `doAnswer` hoặc chỉ `verify`.

### 21.5. Bỏ qua overload

Service gọi `send(SimpleMailMessage)` nhưng test verify `send(MimeMessage)`. Matcher phải đúng kiểu parameter.

### 21.6. Quên thực thi MimeMessagePreparator

Mock `send(preparator)` không chạy callback. Capture callback và gọi `prepare(realMime)` hoặc sử dụng `doAnswer`.

### 21.7. Assert MIME part ở vị trí cố định

Multipart có thể lồng nhau. Duyệt theo MIME type/filename/disposition.

### 21.8. So sánh raw MIME boundary

Boundary, transfer encoding và header folding có thể thay đổi. Test logical content, không chốt bytes toàn bộ message.

### 21.9. Không kiểm charset và tiếng Việt

Một test chỉ có ASCII có thể bỏ qua lỗi mã hóa. Thêm fixture có Unicode và kiểm nội dung đã decode.

### 21.10. Không kiểm filename/bytes của attachment

Một file đính kèm được thêm nhầm loại hoặc dùng bytes rỗng vẫn có thể vượt qua test `send(any(...))`.

### 21.11. Trộn unit test với SMTP thật

Một unit test gọi server bên ngoài sẽ chậm, phụ thuộc mạng/credential và khó tái hiện. Dùng Mockito ở unit layer, SMTP catcher ở integration layer.

### 21.12. Catch exception rồi bỏ qua

Test happy path không phát hiện code nuốt `MailException`. Thêm failure-path test để xác nhận lỗi được xử lý đúng.

### 21.13. Test dựa trên thời gian thực

`Instant.now()` và `Thread.sleep` gây flaky tests. Inject `Clock` và kiểm thời gian cố định.

### 21.14. Dùng @SpringBootTest không cần thiết

Khởi động toàn context chỉ để capture subject/recipient thường quá nặng. Unit test với constructor injection là đủ.

### 21.15. Cho rằng verify times(1) chứng minh exactly-once

Mockito chỉ đếm invocation trong test process. Distributed deduplication cần outbox/unique constraint và kiểm thử riêng.

### 21.16. Quên kiểm tra lệnh không được gửi

Negative tests quan trọng: input invalid, recipient suppressed hoặc notification đã hết hạn phải không submit.

### 21.17. Mock trực tiếp mọi dependency sâu

Nếu test phải mock `MimeMultipart`, `MimeBodyPart`, `InternetAddress` và `MimeMessage` cùng lúc, test có thể đang phụ thuộc quá nhiều chi tiết. Dùng real MIME objects trong bộ nhớ thường đơn giản và chính xác hơn.

### 21.18. Không phân biệt lỗi chuẩn bị và lỗi transport

`MessagingException` khi tạo MIME không giống SMTP `MailSendException`. Kiểm thử hành vi thích hợp của mỗi nhóm.

### 21.19. Tin rằng mock tự bọc MailPreparationException

`JavaMailSenderImpl` thật có logic riêng. Mockito không tự thực thi preparator hay bọc lỗi giống implementation. Muốn chứng minh behavior framework, dùng test phù hợp.

### 21.20. Khóa chặt hệ thống bằng verifyNoMoreInteractions

`verifyNoMoreInteractions(sender)` có thể hữu ích khi thật sự cần ngăn thêm một lời gọi khác, nhưng thường làm test dễ vỡ nếu implementation chỉ thêm thao tác vô hại như tạo object. Hãy xác định rõ tương tác nào thực sự quan trọng trước khi dùng.

## 22. Một quy trình xây dựng test có giá trị

Khi thêm một loại mail mới, quy trình phát triển có thể là:

1. Viết ra contract ở dạng dữ liệu: From, To, Subject, plain/HTML, attachment, tiêu chí không gửi.
2. Chọn API Spring Mail mà service sử dụng: `SimpleMailMessage`, `MimeMessage` hay `MimeMessagePreparator`.
3. Chọn ranh giới test: mail adapter, content renderer, application use case hay outbox worker.
4. Mock **JavaMailSender** nếu adapter thật sự phụ thuộc nó.
5. Với MIME, cấp một `MimeMessage` thật qua `createMimeMessage()` hoặc tự chạy preparator.
6. Capture message/preparator đúng overload.
7. Assert logical field và MIME content; tránh chi tiết ngẫu nhiên.
8. Thêm negative/failure-path tests.
9. Chuyển các khẳng định về SMTP/TLS/delivery sang integration hoặc operational tests.
10. Nếu logic notification có retry/idempotency, kiểm thử chúng ở đúng service/repository/worker.

Đây là quy trình định hướng thiết kế test, không phải yêu cầu chạy một checklist chấm chất lượng ngay trong từng unit test.

## 23. Bài tập thực hành

### Bài 1 — SimpleMailMessage

Viết `WelcomeMailService` nhận `JavaMailSender` qua constructor. Dùng `ArgumentCaptor<SimpleMailMessage>` kiểm tra From, To, Subject và body. Thêm test recipient rỗng không gọi `send`.

### Bài 2 — Sửa test yếu

Cho test:

```java
service.sendInvoice(...);
verify(sender).send(any(MimeMessage.class));
```

Hãy giải thích ít nhất năm lỗi cấu hình/nội dung mà test này không phát hiện được. Viết lại test với `MimeMessage` thật và captor.

### Bài 3 — Stub createMimeMessage

Vì sao `when(sender.createMimeMessage()).thenReturn(mock(MimeMessage.class))` không phù hợp để kiểm tra multipart? Thay bằng `thenAnswer` tạo real message và giải thích lợi ích của instance mới mỗi lần.

### Bài 4 — MimeMessagePreparator

Một service gọi `sender.send(mime -> { ... })`. Test chỉ `verify(sender).send(any(MimeMessagePreparator.class))`. Hãy dùng captor để gọi `prepare` và xác minh subject, recipient và body.

### Bài 5 — doAnswer

Viết một stub `doAnswer` cho `send(MimeMessagePreparator)`, chạy callback trên real `MimeMessage`, lưu message trong `AtomicReference` và xác nhận nội dung đã được xây dựng.

### Bài 6 — Multipart text alternatives

Tạo một message có plain text và HTML. Viết helper duyệt `Multipart` đệ quy để tìm `text/plain` và `text/html` mà không giả định vị trí của part.

### Bài 7 — Attachment

Đính kèm PDF với `ByteArrayResource`. Trong test, tìm MIME part bằng filename, kiểm tra `application/pdf` và so sánh bytes sau khi decode bằng `getInputStream()`.

### Bài 8 — UTF-8 và display name

Thêm From display name “Bộ phận chăm sóc khách hàng” và subject có dấu. Kiểm tra các giá trị đã decode, không so sánh raw header byte.

### Bài 9 — HTML injection

Mã hóa đơn hoặc tên khách hàng có ký tự `<`, `>` và `&`. Tạo test chứng minh HTML được escape; phân biệt với plain text body không cần HTML escape.

### Bài 10 — Exception flow

Mock `JavaMailSender` ném `MailSendException` từ `send(MimeMessage)`. Xác nhận service chuyển sang `NotificationSubmissionException`, giữ original cause và không đánh dấu trạng thái đã submitted.

### Bài 11 — Batch overload

Một service dùng `send(SimpleMailMessage[])`. Capture mảng, assert số lượng và thứ tự người nhận theo hợp đồng. Giải thích vì sao `any(SimpleMailMessage.class)` không khớp overload mảng.

### Bài 12 — Không gửi khi suppressed

Viết notification use case có `SuppressionPolicy`. Xác minh người dùng đã unsubscribe khỏi marketing không tạo notification intent hoặc không gọi mail delivery port tương ứng.

### Bài 13 — Idempotency đúng tầng

Cùng `OrderConfirmed(eventId=E-1)` được xử lý hai lần, nhưng kiến trúc dùng transactional outbox. Hãy chỉ ra vì sao `verify(javaMailSender, times(1))` không phải test đúng và thiết kế assertion ở repository/unique key.

### Bài 14 — Async boundary

Một listener `@Async` gửi email. Hãy giải thích vì sao test dùng `Thread.sleep(100)` dễ flaky và đề xuất cách tách thành component đồng bộ để unit test, hoặc kiểm thử async có synchronization rõ ràng.

### Bài 15 — Contract vs integration

Phân loại các yêu cầu sau theo unit/integration/operational test: subject đúng, TLS trust store hợp lệ, SMTP AUTH thành công, PDF bytes đúng, DKIM pass, gửi một intent cho mỗi event, MX chấp nhận thư, user Inbox placement.

### Bài 16 — Review thiết kế test

Xem một test class có nhiều `@Mock` cho `MimeMessage`, `MimeMultipart`, `MimeBodyPart` và `JavaMailSender`, chỉ verify 20 setter calls. Hãy viết lại theo chiến lược mock duy nhất sender, dùng real MIME objects và assert những field có ý nghĩa.

## 24. Ghi nhớ và tài liệu tham khảo

Để **mock JavaMailSender đúng hợp đồng cần kiểm tra** trong Spring Framework Mail:

1. Xác định **hành vi ứng dụng cam kết** trước khi quyết định verify method nào.
2. `JavaMailSender` có các overload cho `SimpleMailMessage`, `MimeMessage`, `MimeMessagePreparator` và mảng; matcher/captor phải đúng kiểu.
3. `send(...)` trả `void`; dùng `doThrow` và `doAnswer` khi cần, không dùng `when(...).thenReturn(...)`.
4. **Mock JavaMailSender, nhưng dùng MimeMessage thật** trong unit test cần xem nội dung MIME.
5. Stub `createMimeMessage()` trả real message; `thenAnswer` có thể cấp object mới cho mỗi invocation.
6. Dùng `ArgumentCaptor` kiểm tra From, To/Cc/Bcc, Subject, text/plain, text/html, charset và attachment.
7. Duyệt multipart theo MIME type/filename/disposition; đừng giả định vị trí body part hoặc so sánh toàn bộ raw MIME bytes.
8. Với `send(MimeMessagePreparator)`, **Mockito mock không tự chạy callback**: capture rồi `prepare(realMessage)` hoặc dùng `doAnswer`.
9. Kiểm tra cả **không gửi** khi input/policy không hợp lệ và **xử lý lỗi** khi sender ném exception.
10. Dùng `Clock`/fixture ổn định cho dữ liệu động; kiểm nội dung HTML escape/URL theo ngữ cảnh.
11. Unit test của application use case dùng mail port hoặc outbox repository; chỉ mock `JavaMailSender` ở tầng thực sự gọi nó.
12. `verify(sender).send(...)` **không** chứng minh SMTP/TLS/AUTH, SPF/DKIM/DMARC, delivery hay Inbox placement.
13. `times(1)` chỉ đếm lời gọi trong test; distributed idempotency cần unique key/outbox và test riêng.
14. Dùng SMTP catcher/integration test cho giao thức, và provider/operational test cho deliverability.

Tài liệu kỹ thuật nên tham khảo:

- **Spring Framework Reference — Email:** gửi simple mail, MIME mail và cách dùng `JavaMailSender`.
- **Spring Framework API — `JavaMailSender` / `MailSender`:** các overload `send`, `createMimeMessage`, exception contract.
- **Spring Framework API — `MimeMessageHelper`:** plain/HTML alternatives, attachments, inline resources và multipart modes.
- **Spring Framework API — `MimeMessagePreparator`:** chuẩn bị message và đường gửi qua callback.
- **Jakarta Mail API — `MimeMessage`, `Message`, `Multipart`, `Part` và `InternetAddress`:** truy xuất MIME/headers trong bộ nhớ.
- **Mockito Documentation:** `@Mock`, `MockitoExtension`, `ArgumentCaptor`, `doAnswer`, `doThrow`, matchers và varargs.
- **JUnit Jupiter User Guide:** tổ chức unit tests, extension lifecycle và assertion patterns.
- **AssertJ Documentation:** kiểm tra chuỗi, mảng, exception/cause.
- **Spring Framework Test bean override / MockitoBean:** thay bean trong test ApplicationContext khi có nhu cầu integration.
- **Spring Boot Test Reference:** `spring-boot-starter-test` và lựa chọn mock trong context theo phiên bản dự án.
- **GreenMail/Mailpit documentation:** SMTP test server cho integration tests mà không gửi tới hộp thư thật.

**Một unit test đáng tin không dừng ở việc xác nhận `JavaMailSender.send(...)` được gọi.** Nó kiểm tra đúng overload và nội dung hợp đồng; với MIME, nó để Jakarta Mail xây dựng object thật trong bộ nhớ; với preparator, nó thực thi callback; với lỗi, nó kiểm tra phản ứng của ứng dụng. Chỉ khi phân biệt rõ **mock API**, **MIME structure** và **SMTP transport**, bạn mới có test nhanh, ổn định và đủ sức phát hiện những lỗi người nhận thực sự có thể thấy.
