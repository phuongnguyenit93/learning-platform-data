# Đọc MimeMessage trong test và xác minh header

Khi sử dụng **Spring Framework Mail**, một unit test tốt không chỉ kiểm tra rằng `JavaMailSender.send(...)` đã được gọi. Nó còn cần xác minh **email được chuẩn bị đúng**: địa chỉ người gửi và người nhận, tiêu đề, `Reply-To`, các header ứng dụng, charset, nội dung plain text/HTML và cấu trúc MIME khi có attachment.

Trong Java, email phức tạp thường được biểu diễn bằng `jakarta.mail.internet.MimeMessage`. Spring hỗ trợ tạo và điền message qua `JavaMailSender` và `MimeMessageHelper`. Unit test có thể dùng **Mockito** để không kết nối SMTP thật, nhưng vẫn tạo một đối tượng `MimeMessage` thật rồi đọc lại các thuộc tính của nó bằng Jakarta Mail.

Ví dụ mong muốn:

~~~text
OrderReceiptMailer
    |
    +-- JavaMailSender.createMimeMessage()
    |       -> MimeMessage thật, chỉ nằm trong bộ nhớ
    |
    +-- MimeMessageHelper.setFrom/setTo/setSubject/setText
    |       -> header và MIME parts được thiết lập
    |
    +-- JavaMailSender.send(mimeMessage)
            -> Mockito capture, không thực hiện kết nối SMTP
            -> Test đọc MimeMessage và assert từng thuộc tính
~~~

Mục tiêu của bài này là thực hành đọc `MimeMessage` trong test, hiểu API lấy header đúng cách, kiểm tra nội dung MIME và tránh những assertion dễ sai vì cách Jakarta Mail mã hóa hoặc serialize message.

## 1. Kiểm thử ở đúng ranh giới

Giả sử ứng dụng gửi email xác nhận đơn hàng:

- `From`: `orders@notify.example.com`;
- `To`: địa chỉ khách hàng;
- `Cc`: bộ phận tài chính;
- `Bcc`: mailbox kiểm toán;
- `Reply-To`: bộ phận hỗ trợ;
- `Subject`: tiêu đề tiếng Việt có số đơn;
- `X-Template-Id`: mã template để hỗ trợ chẩn đoán;
- body gồm cả plain text và HTML.

Một assertion đơn giản:

~~~java
verify(mailSender).send(any(MimeMessage.class));
~~~

chỉ chứng minh service đã gọi một overload `send` với một đối tượng phù hợp. Nó **không chứng minh** email được gửi tới đúng người, có đúng subject hoặc không thiếu header.

Ngược lại, unit test **không thể** chứng minh SMTP server đã chấp nhận email hay email vào Inbox; nó không dùng kết nối SMTP thật.

### 1.1. Những loại kiểm thử liên quan

| Loại test | Kiểm tra được | Không khẳng định được |
| --- | --- | --- |
| Unit test với Mockito + MimeMessage thật | API mail service tạo From/To/Subject/header/MIME đúng | SMTP credentials, mạng, delivery |
| Unit test của renderer | Template biến dữ liệu thành plain text/HTML phù hợp | SMTP gửi thành công |
| Integration test với SMTP test server | SMTP protocol, message được nộp cho server giả lập | Inbox delivery ở provider thật |
| Provider sandbox/integration test | Hành vi SMTP/API, xác thực, quota trong môi trường test | Mọi mailbox provider luôn nhận thư |
| Provider event/delivery monitoring | Delivery/bounce theo thông tin provider | Người nhận chắc chắn đã đọc thư |

Đối với **kiểm thử đơn vị**, cách nhẹ nhất là mock transport và đọc đối tượng MIME được service tạo.

## 2. Phân biệt MimeMessage, MimeMessageHelper và JavaMailSender

| Thành phần | Vai trò |
| --- | --- |
| `JavaMailSender` | Interface Spring tạo và gửi `MimeMessage` |
| `MimeMessage` | Đối tượng Jakarta Mail chứa header và nội dung MIME |
| `MimeMessageHelper` | API tiện ích để đặt From, To, Cc, Bcc, Reply-To, Subject, text, attachment |
| `Session` của Jakarta Mail | Cấu hình/ngữ cảnh dùng khi tạo MimeMessage |
| `Transport` | Thành phần thực sự giao tiếp SMTP khi có gửi thật |
| `ArgumentCaptor<MimeMessage>` | Công cụ Mockito lấy message đã truyền vào mock |

### 2.1. Chỉ mock sender, không mock MimeMessage

Một lỗi thường gặp:

~~~java
@Mock MimeMessage mimeMessage;
@Mock JavaMailSender mailSender;
~~~

Nếu mock cả `MimeMessage`, các phương thức `setHeader`, `setRecipients` và `setContent` trên object mock không tự lưu dữ liệu. Test sau đó gọi `getSubject()` hoặc `getRecipients()` có thể nhận `null`, trừ khi viết rất nhiều stubbing không cần thiết.

Nên tạo **MimeMessage thật trong bộ nhớ**:

~~~java
Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
~~~

Khi service gọi `MimeMessageHelper`, Jakarta Mail lưu thông tin thật trên object. Mock `JavaMailSender` chỉ ngăn việc kết nối SMTP, còn phần xây message chạy thực.

### 2.2. Không cần SMTP host để tạo MimeMessage

~~~java
Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
~~~

Đoạn này không mở socket và không cần username/password. `Session` dùng để tạo đối tượng message. Trong unit test, không cần cấu hình `mail.smtp.host` chỉ để kiểm tra header.

## 3. Dependency cho unit test

Một dự án Spring Boot thông thường có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Hoặc Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot starter test thường cung cấp JUnit Jupiter, Mockito và AssertJ qua dependency management phù hợp. Khi không dùng Spring Boot, cần khai báo các dependency tương ứng theo phiên bản Spring/Jakarta Mail/JUnit/Mockito của dự án.

**Package cần chú ý:** Spring Framework 6 / Spring Boot 3 trở lên sử dụng Jakarta Mail với các import kiểu `jakarta.mail.*`. Dự án Spring 5 hoặc JavaMail cũ có thể sử dụng `javax.mail.*`. Không trộn hai namespace trong cùng ví dụ/codebase nếu runtime dependency không tương thích.

## 4. Service minh họa cần kiểm thử

Xét service gửi biên nhận đơn hàng. Để tập trung vào MIME/header, service nhận plain text và HTML đã được renderer chuẩn bị hợp lệ; không thực hiện truy vấn database hoặc render template.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderReceiptMailer {
    private final JavaMailSender mailSender;

    public OrderReceiptMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReceipt(
            String recipient,
            String orderNumber,
            String plainText,
            String htmlText) {

        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                    StandardCharsets.UTF_8.name()
            );

            helper.setFrom("orders@notify.example.com");
            helper.setTo(recipient);
            helper.setCc("finance@example.com");
            helper.setBcc("audit@example.com");
            helper.setReplyTo("support@example.com");

            helper.setSubject(
                    "Xác nhận đơn hàng " + orderNumber);
            helper.setText(plainText, htmlText);

            message.setHeader("X-Template-Id", "order-receipt");
            message.setHeader("X-Notification-Type", "ORDER_RECEIPT");
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot prepare order receipt email", ex);
        }

        mailSender.send(message);
    }
}
~~~

Giả định:

- Email To/From/Cc/Bcc là địa chỉ đã được xác định và kiểm tra tại application boundary.
- `orderNumber` đã được xác thực theo domain rule.
- `plainText` và `htmlText` được tạo bởi renderer an toàn, có escaping phù hợp; không chèn HTML do người dùng nhập vào mà không escape.
- `orders@notify.example.com`, `finance@example.com` và `audit@example.com` chỉ là địa chỉ ví dụ.

Trong thiết kế production, sender identity, địa chỉ audit, Reply-To và template ID có thể là cấu hình theo tenant, domain nghiệp vụ hoặc profile gửi. Việc hard-code trong ví dụ chỉ làm rõ những header cần kiểm thử.

## 5. Tạo unit test với Mockito và JUnit 5

Test có thể dùng `@ExtendWith(MockitoExtension.class)` và mock `JavaMailSender`.

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class OrderReceiptMailerTest {

    @Mock
    JavaMailSender mailSender;

    OrderReceiptMailer mailer;

    @BeforeEach
    void setUp() {
        when(mailSender.createMimeMessage())
                .thenAnswer(invocation -> new MimeMessage(
                        Session.getInstance(new Properties())
                ));

        mailer = new OrderReceiptMailer(mailSender);
    }

    @Test
    void sendsOneMimeMessage() {
        mailer.sendReceipt(
                "alice@example.net",
                "A123",
                "Đơn hàng A123 đã xác nhận.",
                "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
        );

        verify(mailSender, times(1))
                .send(any(MimeMessage.class));
    }
}
~~~

Các điểm cần hiểu:

- `mailSender` là mock, nên lời gọi `send(...)` không kết nối SMTP.
- `createMimeMessage()` được stub để trả **MimeMessage thật**.
- Mỗi lần create sẽ có đối tượng mới, giảm nguy cơ test ảnh hưởng nhau.
- Không cần `@SpringBootTest` hay khởi động toàn bộ application context chỉ để kiểm tra một service có constructor injection.
- Mockito mock của method `void send(...)` mặc định không làm gì, nếu không có stub khác.

Test trên mới kiểm tra số lần gọi. Bước tiếp theo là **capture** object gửi đi.

## 6. Capture MimeMessage bằng ArgumentCaptor

~~~java
import jakarta.mail.internet.MimeMessage;
import org.mockito.ArgumentCaptor;

@Test
void capturesPreparedMessage() throws Exception {
    mailer.sendReceipt(
            "alice@example.net",
            "A123",
            "Đơn hàng A123 đã xác nhận.",
            "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
    );

    ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

    verify(mailSender).send(captor.capture());

    MimeMessage actual = captor.getValue();
    assertNotNull(actual);
    assertEquals(
            "Xác nhận đơn hàng A123",
            actual.getSubject()
    );
}
~~~

`ArgumentCaptor` lấy **chính đối tượng** được truyền cho `send(...)`. Sau đó, ta dùng API Jakarta Mail để kiểm tra dữ liệu thực tế.

### 6.1. Vì sao getSubject() tốt hơn đọc header Subject thô?

Một tiêu đề tiếng Việt có thể được mã hóa theo cú pháp MIME:

~~~text
Subject: =?UTF-8?B?...?=
~~~

Đây là dạng ví dụ của encoded-word, không phải một chuỗi subject cụ thể.

`MimeMessage.getSubject()` trả lại tiêu đề ở dạng đã được giải mã cho code Java. Do đó:

~~~java
assertEquals("Xác nhận đơn hàng A123", actual.getSubject());
~~~

thường ổn định hơn việc so sánh `actual.getHeader("Subject", null)` với chuỗi tiếng Việt thô. Test cần so sánh **ngữ nghĩa hiển thị**, không phụ thuộc cách thư viện chọn Base64 hay Quoted-Printable cho header.

## 7. Đọc From, To, Cc, Bcc và Reply-To

Jakarta Mail cung cấp:

~~~java
Address[] getFrom();
Address[] getRecipients(Message.RecipientType type);
Address[] getReplyTo();
~~~

### 7.1. From

~~~java
import jakarta.mail.Address;
import jakarta.mail.internet.InternetAddress;

Address[] from = actual.getFrom();
assertNotNull(from);
assertEquals(1, from.length);

InternetAddress sender = (InternetAddress) from[0];
assertEquals(
        "orders@notify.example.com",
        sender.getAddress()
);
~~~

Không nên dùng `from[0].toString()` nếu địa chỉ có display name, ví dụ:

~~~text
"Cửa hàng" <orders@notify.example.com>
~~~

`toString()` có thể bao gồm cả tên và encoding, nên nếu chỉ muốn kiểm tra mailbox, dùng `InternetAddress.getAddress()`.

### 7.2. To, Cc và Bcc

~~~java
import jakarta.mail.Message;

Address[] to = actual.getRecipients(Message.RecipientType.TO);
Address[] cc = actual.getRecipients(Message.RecipientType.CC);
Address[] bcc = actual.getRecipients(Message.RecipientType.BCC);

assertEquals(
        "alice@example.net",
        ((InternetAddress) to[0]).getAddress()
);
assertEquals(
        "finance@example.com",
        ((InternetAddress) cc[0]).getAddress()
);
assertEquals(
        "audit@example.com",
        ((InternetAddress) bcc[0]).getAddress()
);
~~~

Nếu message không có recipient ở một nhóm, phương thức có thể trả `null`. Đừng tự gọi `.length` trên kết quả chưa được kiểm tra.

Ví dụ kiểm tra không có Cc:

~~~java
Address[] cc = actual.getRecipients(Message.RecipientType.CC);
assertTrue(cc == null || cc.length == 0);
~~~

### 7.3. Reply-To

~~~java
Address[] replyTo = actual.getReplyTo();
assertNotNull(replyTo);
assertEquals(
        "support@example.com",
        ((InternetAddress) replyTo[0]).getAddress()
);
~~~

Lưu ý: `MimeMessage.getReplyTo()` có thể trả địa chỉ From như giá trị fallback khi **không có header Reply-To**. Nếu test cần xác minh service **thực sự đặt header Reply-To**, nên kiểm tra thêm:

~~~java
assertNotNull(actual.getHeader("Reply-To"));
~~~

Việc chỉ thấy `getReplyTo()` trả đúng địa chỉ trùng với From chưa đủ chứng minh header đã được set.

### 7.4. Nhiều recipient: so sánh theo tập hợp khi thứ tự không phải hợp đồng

Với một danh sách To, không nên luôn ép thứ tự nếu business contract chỉ quy định tập người nhận. Helper:

~~~java
import jakarta.mail.Address;
import jakarta.mail.internet.InternetAddress;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

static Set<String> mailboxes(Address[] addresses) {
    if (addresses == null) {
        return Set.of();
    }

    return Arrays.stream(addresses)
            .map(address -> ((InternetAddress) address).getAddress())
            .collect(Collectors.toSet());
}
~~~

Assert:

~~~java
assertEquals(
        Set.of("alice@example.net", "bob@example.net"),
        mailboxes(actual.getRecipients(Message.RecipientType.TO))
);
~~~

Khi cần phát hiện địa chỉ trùng, chỉ dùng `Set` có thể che mất duplicate. Có thể so sánh list hoặc số lượng trước khi chuyển thành set.

### 7.5. Bcc không được hiểu sai

Trong **MimeMessage trước khi gửi**, `getRecipients(BCC)` có thể trả các địa chỉ Bcc vì message object vẫn cần biết envelope recipients. Nhưng khi một email được truyền đi, header Bcc thường được loại bỏ khỏi bản hiển thị đến người nhận theo cách xử lý của transport/provider.

Vì vậy:

- Unit test trước gửi có thể assert `getRecipients(BCC)` để chứng minh service chuẩn bị đúng người nhận ẩn.
- **Không** assert rằng `MimeMessage` trước gửi không chứa Bcc header nếu service chủ động đặt Bcc.
- Unit test này **không chứng minh** bản message người nhận cuối cùng không lộ Bcc; để xác minh hành vi truyền/giao thư cần test SMTP/provider phù hợp.
- Không ghi danh sách Bcc vào To/Cc hoặc custom header công khai.

## 8. Đọc header tùy biến

Ứng dụng có thể đặt một header riêng để hỗ trợ định tuyến hoặc chẩn đoán:

~~~java
message.setHeader("X-Template-Id", "order-receipt");
message.setHeader("X-Notification-Type", "ORDER_RECEIPT");
~~~

Đọc lại:

~~~java
String[] templateHeaders =
        actual.getHeader("X-Template-Id");

assertNotNull(templateHeaders);
assertEquals(1, templateHeaders.length);
assertEquals("order-receipt", templateHeaders[0]);
~~~

Hoặc lấy dạng chuỗi:

~~~java
assertEquals(
        "ORDER_RECEIPT",
        actual.getHeader("X-Notification-Type", null)
);
~~~

### 8.1. getHeader(name) và getHeader(name, delimiter)

| Method | Kết quả |
| --- | --- |
| `getHeader("X-Template-Id")` | Mảng `String[]` chứa các giá trị header, có thể `null` |
| `getHeader("X-Template-Id", null)` | Một chuỗi ghép theo semantics API, có thể `null` |
| `getAllHeaders()` | Enumeration các header hiện có |
| `getMatchingHeaders(names)` | Enumeration header có tên thuộc danh sách |
| `getNonMatchingHeaders(names)` | Enumeration header còn lại |

Header name về mặt giao thức là **case-insensitive**. Nên truy vấn bằng tên header thay vì parse toàn bộ raw message và kỳ vọng một cách viết hoa/thường cụ thể.

### 8.2. Header có thể xuất hiện nhiều lần

Một số header có thể có nhiều value. Nếu service dùng `addHeader(...)` thay cho `setHeader(...)`, giá trị mới được thêm chứ không nhất thiết ghi đè giá trị cũ.

~~~java
message.addHeader("X-Tag", "order");
message.addHeader("X-Tag", "important");
~~~

Khi kiểm tra:

~~~java
assertArrayEquals(
        new String[] { "order", "important" },
        message.getHeader("X-Tag")
);
~~~

Nếu contract không quy định thứ tự, kiểm tra tập giá trị thay vì hard-code thứ tự. Tránh nối nhiều value thành một chuỗi rồi so sánh khi những dấu phân cách có thể tạo kết quả mơ hồ.

### 8.3. Header có thể được fold thành nhiều dòng

Header dài có thể được **fold** theo quy tắc MIME/RFC, ví dụ:

~~~text
X-Long-Info: first part
 second part
~~~

Không nên so sánh nguyên văn toàn bộ message bằng một string nếu thứ bạn cần kiểm chứng là một header có ý nghĩa. Dùng API `getHeader`, hoặc parse một serialized MimeMessage mới trong test dành riêng cho serialization.

## 9. Kiểm thử subject tiếng Việt và charset

Email có thể chứa Unicode ở:

- Subject;
- display name của From/To;
- plain text body;
- HTML body;
- attachment filename.

Với `MimeMessageHelper(..., "UTF-8")`, ví dụ:

~~~java
helper.setSubject("Xác nhận đơn hàng A123");
~~~

Assert trực tiếp:

~~~java
assertEquals(
        "Xác nhận đơn hàng A123",
        actual.getSubject()
);
~~~

Nếu đọc raw header, có thể nhận encoded-word. Không ép raw header phải chứa chữ “Xác nhận” dưới dạng UTF-8 hiển thị như trong mã nguồn.

### 9.1. Content-Type và charset

Một phần nội dung có thể có:

~~~text
Content-Type: text/plain; charset=UTF-8
~~~

hoặc:

~~~text
Content-Type: text/html; charset=UTF-8
~~~

Trong multipart message, **root Content-Type** thường là `multipart/*` chứ không phải `text/plain` hoặc `text/html`. Vì vậy, kiểm tra:

~~~java
assertTrue(actual.isMimeType("multipart/*"));
~~~

thích hợp hơn việc đòi:

~~~java
assertTrue(actual.isMimeType("text/html")); // Sai với root multipart.
~~~

Để xác minh charset, có thể truy cập body part chứa text:

~~~java
import jakarta.mail.internet.ContentType;

ContentType type = new ContentType(bodyPart.getContentType());
assertTrue(
        "UTF-8".equalsIgnoreCase(type.getParameter("charset"))
);
~~~

Đoạn này minh họa khi đã có `bodyPart` chứa text. Trong test thực, charset parameter có thể được thư viện chuẩn hóa cách viết hoa/thường; quan trọng là charset được giải mã đúng, không phải chuỗi Content-Type giống hệt từng ký tự.

### 9.2. Tránh kiểm tra Content-Transfer-Encoding cứng nhắc

Với Unicode, thư viện có thể lựa chọn `quoted-printable` hoặc `base64` tùy nội dung, phiên bản và quá trình serialization.

Thông thường nên assert:

- decoded Subject bằng `getSubject()`;
- decoded body string bằng `getContent()`;
- charset là UTF-8 hoặc encoding mong đợi.

Chỉ kiểm tra chính xác `Content-Transfer-Encoding` nếu đó thật sự là contract của ứng dụng và test tập trung vào MIME serialization.

## 10. Đọc nội dung text/plain và text/html trong multipart

Với:

~~~java
helper.setText(
        "Đơn hàng A123 đã xác nhận.",
        "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
);
~~~

`MimeMessageHelper` có thể tạo cấu trúc MIME lồng nhau.

Ví dụ sơ đồ:

~~~text
MimeMessage
└── multipart/mixed
    └── multipart/related
        └── multipart/alternative
            ├── text/plain; charset=UTF-8
            └── text/html; charset=UTF-8
~~~

Cấu trúc minh họa này phụ thuộc vào mode của `MimeMessageHelper`, phiên bản thư viện và việc có inline resource/attachment. **Không nên viết test chỉ đi vào `getBodyPart(0).getBodyPart(1)` một cách cứng nhắc** nếu mục tiêu chỉ là kiểm tra có plain text và HTML.

### 10.1. Duyệt MIME tree thay vì đoán vị trí

Hàm tiện ích dành cho test:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static boolean hasTextPart(
        Part part,
        String mimeType,
        String expectedSubstring) throws Exception {

    if (part.isMimeType(mimeType)) {
        Object content = part.getContent();
        return content instanceof String text
                && text.contains(expectedSubstring);
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            if (hasTextPart(
                    multipart.getBodyPart(i),
                    mimeType,
                    expectedSubstring)) {
                return true;
            }
        }
    } else if (content instanceof Part nestedPart) {
        return hasTextPart(
                nestedPart,
                mimeType,
                expectedSubstring);
    }

    return false;
}
~~~

Hàm này:

1. Nếu part hiện tại có MIME type cần kiểm tra, đọc nội dung đã được Jakarta Mail decode.
2. Nếu part chứa `Multipart`, duyệt từng body part.
3. Nếu part chứa nested `Part` (ví dụ một message lồng), đi sâu thêm.
4. Không phụ thuộc vào vị trí tuyệt đối của plain/HTML.

Đây là utility phục vụ test; trong hệ thống xử lý MIME không đáng tin cậy từ bên ngoài, cần thêm giới hạn kích thước và độ sâu traversal để chống nội dung độc hại hoặc quá lớn.

### 10.2. Test plain và HTML

~~~java
@Test
void containsBothPlainAndHtmlAlternatives() throws Exception {
    mailer.sendReceipt(
            "alice@example.net",
            "A123",
            "Đơn hàng A123 đã xác nhận.",
            "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
    );

    ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);
    verify(mailSender).send(captor.capture());

    MimeMessage actual = captor.getValue();

    assertTrue(hasTextPart(
            actual,
            "text/plain",
            "Đơn hàng A123 đã xác nhận."
    ));

    assertTrue(hasTextPart(
            actual,
            "text/html",
            "<strong>A123</strong>"
    ));
}
~~~

Test này kiểm tra nội dung đã được chuẩn bị, không khẳng định HTML sẽ hiển thị giống nhau trên Gmail, Outlook và các email client khác.

### 10.3. text/plain khác text/html

Đừng chỉ assert có HTML và bỏ qua phần plain text nếu application contract đòi email có thể đọc bởi client không hỗ trợ HTML.

Ví dụ:

~~~text
Plain:
  Đơn hàng A123 đã xác nhận.

HTML:
  <p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>
~~~

Hai nội dung có thể trình bày khác nhau nhưng nên diễn đạt cùng thông tin cốt lõi. Có thể test những dữ liệu nghiệp vụ quan trọng (mã đơn, số tiền, link) xuất hiện trong cả hai, thay vì assert mọi ký tự giống nhau.

## 11. Header có ở root và ở body part

Trong MIME, header không chỉ tồn tại ở root `MimeMessage`:

~~~text
MimeMessage headers:
  From
  To
  Subject
  MIME-Version
  Content-Type: multipart/mixed

BodyPart headers:
  Content-Type: text/html; charset=UTF-8
  Content-Transfer-Encoding: quoted-printable
~~~

Nếu gọi:

~~~java
actual.getHeader("Content-Type");
~~~

ta đang đọc **root** Content-Type, thường là multipart. Muốn kiểm tra charset của HTML, cần đọc `getContentType()` trên **body part HTML**, không dựa vào root.

Tương tự:

- `Content-Disposition` của attachment thường ở attachment part;
- `Content-ID` của ảnh inline ở ảnh part;
- `Content-Transfer-Encoding` có thể khác nhau giữa các part.

Đây là lý do test MIME thường cần duyệt cây `Multipart` thay vì chỉ dùng `MimeMessage.getHeader(...)`.

## 12. Kiểm tra attachment bằng cấu trúc MIME

Giả sử service thêm hóa đơn:

~~~java
import org.springframework.core.io.ByteArrayResource;

helper.addAttachment(
        "invoice-A123.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Một assertion trên root như:

~~~java
assertTrue(actual.isMimeType("application/pdf")); // Không đúng cho root
~~~

không phù hợp. PDF là một body part nằm trong `multipart/*`.

### 12.1. Tìm attachment part

Hàm minh họa:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static boolean hasAttachmentNamed(
        Part part,
        String expectedName) throws Exception {

    String disposition = part.getDisposition();
    if (Part.ATTACHMENT.equalsIgnoreCase(disposition)
            && expectedName.equals(part.getFileName())) {
        return true;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            if (hasAttachmentNamed(
                    multipart.getBodyPart(i),
                    expectedName)) {
                return true;
            }
        }
    }
    return false;
}
~~~

Trong test:

~~~java
assertTrue(
        hasAttachmentNamed(actual, "invoice-A123.pdf")
);
~~~

Lưu ý:

- Tên file Unicode có thể được MIME-encode; Jakarta Mail có thể decode khi gọi `getFileName()` tùy cấu hình/thư viện.
- Có attachment mà `Content-Disposition` không phải một giá trị đơn giản như mong đợi nếu message do provider khác tạo; test cần bám contract của service đang tạo message.
- Chỉ thấy filename không đủ chứng minh bytes đúng. Nếu yêu cầu chính xác, có thể đọc `part.getInputStream()` và so sánh checksum/byte array trên attachment part.
- Không log toàn bộ PDF hay bí mật trong test output.

### 12.2. Ảnh inline khác attachment

Với:

~~~java
helper.addInline(
        "company-logo",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

service có thể tạo một part có header:

~~~text
Content-ID: <company-logo>
Content-Disposition: inline
Content-Type: image/png
~~~

Trong HTML, tham chiếu có thể là `cid:company-logo`.

Để kiểm tra, tìm part có `Content-ID` tương ứng và MIME type `image/png`. Không giả định ảnh inline nằm tại một body part index cố định. Điều quan trọng là CID được tham chiếu trong HTML phải khớp với content ID của part.

## 13. Header chuẩn khác với custom header

Các header có ý nghĩa riêng ở tầng Internet Message Format/MIME:

| Header | Cách kiểm tra nên ưu tiên |
| --- | --- |
| `From` | `getFrom()` và `InternetAddress.getAddress()` |
| `To`, `Cc`, `Bcc` | `getRecipients(RecipientType)` |
| `Reply-To` | `getReplyTo()` và khi cần `getHeader("Reply-To")` |
| `Subject` | `getSubject()` để nhận chuỗi đã decode |
| `Sent-Date` / `Date` | `getSentDate()` sau khi ngày được thiết lập |
| `Message-ID` | `getMessageID()` sau khi message được lưu/serialize phù hợp |
| `Content-Type` | `getContentType()` hoặc `isMimeType()` trên đúng Part |
| `Content-Disposition` | `Part.getDisposition()` |
| `Content-ID` | `Part.getHeader("Content-ID")` |
| `X-Template-Id` | `getHeader("X-Template-Id")` |

Ưu tiên API typed khi có. Parsing bằng regex trên toàn bộ message thường dễ bị ảnh hưởng bởi header folding, encoding, boundary và line ending.

### 13.1. Header không nên chứa dữ liệu bảo mật

Không đưa:

- mật khẩu SMTP;
- OAuth access/refresh token;
- mã OTP rõ;
- secret dùng để ký link;
- thông tin thanh toán nhạy cảm;
- dữ liệu cá nhân không cần thiết.

vào `X-*` header chỉ để hỗ trợ debug. Header có thể được chuyển tiếp và lưu lại bởi nhiều mail server. Dùng local job ID/correlation ID không nhạy cảm nếu cần truy vết.

### 13.2. Header injection

Nếu header value được ghép trực tiếp từ input tùy ý có CR/LF, có rủi ro **header injection**:

~~~text
User input:
  user-supplied-value\r\nBcc: attacker@example.net
~~~

Trong application boundary, phải validate/sanitize input phù hợp; không cho user tự kiểm soát `From`/`Bcc` hoặc các header chính sách. Unit test có thể kiểm tra dữ liệu không hợp lệ bị từ chối và `mailSender.send` không được gọi.

Không chỉ dựa vào `InternetAddress.validate()` để bảo đảm địa chỉ thực sự tồn tại hoặc được SMTP server chấp nhận; nó chủ yếu kiểm tra cú pháp theo API.

## 14. Khi nào cần gọi saveChanges() trong test?

`MimeMessage` có trạng thái trong bộ nhớ. Các thao tác tạo message bằng helper đặt nhiều header/part trước khi gửi, nhưng một số header như `Date`, `Message-ID`, `MIME-Version` hoặc `Content-Transfer-Encoding` có thể được tạo/cập nhật khi **saveChanges** hoặc **serialization**.

Ví dụ:

~~~java
MimeMessage message = new MimeMessage(
        Session.getInstance(new Properties())
);
// Set From, To, Subject, content...

message.saveChanges();
String messageId = message.getMessageID();
~~~

Khi `JavaMailSender` là mock, `send` không thực thi phần chuẩn bị/transport thật. Vì vậy, nếu test đang kiểm tra `Message-ID` được Jakarta Mail tạo tự động nhưng chưa gọi `saveChanges()`, có thể thấy `null` hoặc kết quả khác kỳ vọng.

**Không gọi `saveChanges()` cho mọi test mà không cần thiết.** Với From/To/Subject/custom header, có thể đọc ngay sau khi helper đã set. Với test serialization, hãy có bước save/serialize rõ ràng.

### 14.1. Không hard-code Message-ID ngẫu nhiên

Không nên:

~~~java
assertEquals(
        "<fixed-message-id@example.com>",
        actual.getMessageID()
);
~~~

nếu code không đặt Message-ID cố định. Thư viện có thể sinh giá trị chứa thời gian, random/counter hoặc host. Nếu contract chỉ yêu cầu Message-ID tồn tại sau serialization:

~~~java
actual.saveChanges();
assertNotNull(actual.getMessageID());
~~~

Đừng xem Message-ID là idempotency key bảo đảm SMTP loại bỏ email trùng; đây là các khái niệm khác nhau.

### 14.2. Date và timezone

Nếu service dùng `helper.setSentDate(...)` hoặc `message.setSentDate(...)` với clock được inject, có thể assert giá trị gần như chính xác theo một `Clock.fixed(...)`.

Nếu Date do Jakarta Mail tự tạo khi save, không nên hard-code timestamp theo thời gian máy test. Timezone cũng ảnh hưởng định dạng raw header. Tốt hơn là:

- inject `Clock` khi thời gian là business contract;
- kiểm tra `Date` đã được set, hoặc so sánh `Instant`/`Date` typed;
- không so sánh nguyên văn chuỗi timezone trong header.

### 14.3. saveChanges() có thể làm thay đổi message

`saveChanges()` không chỉ là “getter”. Nó có thể tạo hoặc cập nhật header và thông tin MIME. Nếu test chỉ cần kiểm tra dữ liệu mà service đặt, hãy tránh thay đổi message trước assertion. Nếu test nhằm xác minh serialized MIME, gọi save/serialize có chủ đích trong một test riêng.

## 15. Serialize MimeMessage khi cần kiểm tra raw MIME

Đôi khi cần xem nội dung MIME thực tế, chẳng hạn kiểm tra header folding, boundary hoặc khả năng parser đọc message sau khi lưu.

Có thể serialize vào memory:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

actual.saveChanges();

ByteArrayOutputStream out = new ByteArrayOutputStream();
actual.writeTo(out);

byte[] rawMime = out.toByteArray();
String preview = new String(
        rawMime,
        StandardCharsets.ISO_8859_1
);
~~~

**Không dùng `preview` để assert Unicode tiếng Việt hiển thị trực tiếp.** Raw MIME có encoded-word, quoted-printable, base64 và các MIME boundary. ISO-8859-1 chỉ giúp quan sát từng byte theo một cách không làm mất byte ở bước chuyển sang string, không phải giải mã đúng nội dung MIME.

Để kiểm tra round-trip, parse lại:

~~~java
import java.io.ByteArrayInputStream;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

MimeMessage reparsed = new MimeMessage(
        Session.getInstance(new Properties()),
        new ByteArrayInputStream(rawMime)
);

assertEquals(
        "Xác nhận đơn hàng A123",
        reparsed.getSubject()
);
~~~

Round-trip test hữu ích nếu sản phẩm cần lưu raw MIME cho queue/retry hoặc trao đổi với một mail transport độc lập.

### 15.1. Vì sao không snapshot toàn bộ raw MIME?

Một test:

~~~java
assertEquals(expectedRawMessage, preview);
~~~

thường rất mong manh, vì:

- MIME boundary có thể thay đổi;
- Date/Message-ID có thể được sinh;
- header order hoặc folding thay đổi;
- encoding chọn Base64 hay Quoted-Printable;
- CRLF và cách line wrapping phụ thuộc thư viện;
- thay đổi phiên bản Jakarta Mail có thể gây diff dù ý nghĩa message không đổi.

Chỉ snapshot raw MIME khi chính định dạng byte-level là contract, ví dụ tích hợp chữ ký/canonicalization. Với nghiệp vụ, assert theo API parsed/semantic sẽ bền vững hơn.

## 16. Xác minh header của email marketing

Ngoài From/Subject/Reply-To, email marketing có thể cần:

~~~text
List-Unsubscribe: <https://offers.example.com/u/opaque-token>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

Trong test, kiểm tra:

~~~java
assertEquals(
        "<https://offers.example.com/u/opaque-token>",
        actual.getHeader("List-Unsubscribe", null)
);

assertEquals(
        "List-Unsubscribe=One-Click",
        actual.getHeader("List-Unsubscribe-Post", null)
);
~~~

Nếu URL có token được tạo động, không hard-code toàn bộ token. Có thể kiểm tra URL đúng host, scheme HTTPS, path, chữ ký/expiry theo contract, hoặc dùng token generator giả kiểm soát được.

**Lưu ý:** có header unsubscribe không có nghĩa endpoint thực sự hoạt động hoặc provider/email client sẽ hiển thị nút hủy đăng ký. Đó là integration/behavior test riêng. Hơn nữa, không tự thêm header marketing vào mọi email giao dịch nếu không phù hợp chính sách.

### 16.1. Header thường do provider thêm sau khi nộp thư

Một số header có thể chỉ xuất hiện trên bản message đã đi qua SMTP/ESP, ví dụ:

- `Received`;
- `Authentication-Results` của mail receiver;
- `DKIM-Signature` khi ESP là bên thực hiện ký;
- `Return-Path` được xử lý trong quá trình giao thư;
- provider-specific tracking/delivery headers.

Unit test của service trước SMTP **không nên bắt buộc** những header đó có mặt, trừ khi chính service của ứng dụng chịu trách nhiệm tạo chúng.

Không thể chứng minh SPF/DKIM/DMARC pass chỉ bằng cách đọc `MimeMessage` trước khi gửi. Cần test DNS/ESP/receiver phù hợp.

## 17. Xác minh địa chỉ có display name

Một From có thể được tạo như:

~~~java
helper.setFrom(
        new InternetAddress(
                "orders@notify.example.com",
                "Cửa hàng Ví dụ",
                "UTF-8"
        )
);
~~~

Trong test:

~~~java
InternetAddress from =
        (InternetAddress) actual.getFrom()[0];

assertEquals(
        "orders@notify.example.com",
        from.getAddress()
);
assertEquals("Cửa hàng Ví dụ", from.getPersonal());
~~~

Nếu đọc raw `From` header, display name có thể được encoded theo RFC 2047. `getPersonal()` thường trả tên đã decode. Test nên xác minh mailbox và personal name **riêng**, thay vì so sánh một chuỗi `toString()`.

### 17.1. Multiple From/Sender

Trong đa số email ứng dụng, `From` là một mailbox được cấp quyền gửi. RFC có quy tắc riêng nếu nhiều mailbox xuất hiện trong From và `Sender` được sử dụng. Không tự tạo cấu trúc này nếu không hiểu yêu cầu giao thức và chính sách provider.

Nếu service đặt `Sender`, test nên xác minh riêng header đó; `getFrom()` và `getSender()` không có cùng vai trò. Với Spring Mail, From/Reply-To thường là những giá trị cần kiểm tra trước tiên.

## 18. Test trường hợp không gửi khi validation thất bại

Test header đúng cần đi cùng test **không tạo/gửi message** khi request không hợp lệ.

Ví dụ một application boundary từ chối địa chỉ không được phép:

~~~java
@Test
void rejectsUnauthorizedSenderBeforeSending() {
    assertThrows(
            IllegalArgumentException.class,
            () -> applicationService.submitMail(
                    "attacker@example.net",
                    "spoofed-from@example.org",
                    "subject"
            )
    );

    verify(mailSender, never())
            .send(any(MimeMessage.class));
}
~~~

Đây là pseudo-test với `applicationService` có chính sách sender allowlist; không phải method của `OrderReceiptMailer` ví dụ. Kiểm tra:

- địa chỉ From chỉ lấy từ cấu hình/identity được cấp quyền;
- recipient được validate và kiểm tra authorization;
- không chấp nhận ký tự điều khiển trong header value;
- không đưa dữ liệu bí mật vào header;
- subject và custom header có giới hạn độ dài hợp lý;
- lỗi chuẩn bị message không bị nuốt rồi gọi send với message thiếu trường.

### 18.1. Đừng dùng verifyNoInteractions nếu đã gọi createMimeMessage

Nếu service tạo message trước khi validate, mock `JavaMailSender` đã nhận lời gọi `createMimeMessage()`. Test dùng:

~~~java
verifyNoInteractions(mailSender);
~~~

sẽ thất bại ngay cả khi `send(...)` chưa được gọi. Nếu mục đích là kiểm tra **không gửi ra transport**, assertion đúng trọng tâm hơn là:

~~~java
verify(mailSender, never())
        .send(any(MimeMessage.class));
~~~

Nếu kiến trúc yêu cầu validation xảy ra **trước khi tạo MIME**, khi đó có thể kiểm tra không gọi `createMimeMessage()`; đây là một contract khác.

## 19. Mockito ArgumentCaptor và lỗi overload/varargs

`JavaMailSender` có các overload hỗ trợ một hoặc nhiều message. Khi capture, hãy kiểm tra chính lời gọi mà code production sử dụng.

Ví dụ gửi một message:

~~~java
ArgumentCaptor<MimeMessage> captor =
        ArgumentCaptor.forClass(MimeMessage.class);

verify(mailSender).send(captor.capture());
~~~

Nếu service gọi:

~~~java
mailSender.send(message1, message2);
~~~

thì signature/varargs khác; cần capture từng argument hoặc mảng theo cách phù hợp với phiên bản Mockito và overload. Không mặc định `getValue()` sẽ chứa tất cả messages của một batch.

Nếu code dùng:

~~~java
mailSender.send(mimeMessagePreparator);
~~~

thì test cần capture `MimeMessagePreparator` hoặc stub `send(MimeMessagePreparator)` để thực thi preparator trên `MimeMessage` thật. Mockito không tự chạy callback/preparator được truyền vào mock.

### 19.1. Test MimeMessagePreparator

Ví dụ service dùng:

~~~java
mailSender.send(mimeMessage -> {
    MimeMessageHelper helper =
            new MimeMessageHelper(mimeMessage, "UTF-8");
    helper.setTo("alice@example.net");
    helper.setSubject("Thông báo");
    helper.setText("Nội dung");
});
~~~

Khi `JavaMailSender` là mock, callback **không tự thực thi**. Có thể dùng `doAnswer` để tạo message thật:

~~~java
import org.springframework.mail.javamail.MimeMessagePreparator;

doAnswer(invocation -> {
    MimeMessagePreparator preparator =
            invocation.getArgument(0);
    MimeMessage realMessage = new MimeMessage(
            Session.getInstance(new Properties())
    );

    preparator.prepare(realMessage);
    capturedMessages.add(realMessage);
    return null;
}).when(mailSender)
  .send(any(MimeMessagePreparator.class));
~~~

`capturedMessages` là một `List<MimeMessage>` do test tạo trước. Sau khi gọi service, đọc message trong list và assert From/To/Subject tương tự các ví dụ trước.

Điểm khác nhau:

- `send(MimeMessage)`: service thường đã chuẩn bị message trước khi mock nhận lời gọi.
- `send(MimeMessagePreparator)`: service truyền callback, mock cần chủ động chạy callback nếu test muốn kiểm tra nội dung.

Nếu không chạy preparator, test chỉ xác nhận service gửi callback chứ không xác nhận email bên trong callback được chuẩn bị đúng.

## 20. Một ví dụ test tổng hợp cho header

Dưới đây là một test tập trung vào các header quan trọng; sử dụng service và setup ở các phần trên.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

@Test
void preparesCorrectRecipientsSubjectAndHeaders()
        throws Exception {

    mailer.sendReceipt(
            "alice@example.net",
            "A123",
            "Đơn hàng A123 đã xác nhận.",
            "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
    );

    ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);
    verify(mailSender, times(1)).send(captor.capture());

    MimeMessage actual = captor.getValue();

    assertEquals(
            "orders@notify.example.com",
            ((InternetAddress) actual.getFrom()[0]).getAddress()
    );
    assertEquals(
            "alice@example.net",
            ((InternetAddress) actual.getRecipients(
                    Message.RecipientType.TO)[0]).getAddress()
    );
    assertEquals(
            "finance@example.com",
            ((InternetAddress) actual.getRecipients(
                    Message.RecipientType.CC)[0]).getAddress()
    );
    assertEquals(
            "audit@example.com",
            ((InternetAddress) actual.getRecipients(
                    Message.RecipientType.BCC)[0]).getAddress()
    );
    assertEquals(
            "support@example.com",
            ((InternetAddress) actual.getReplyTo()[0]).getAddress()
    );
    assertNotNull(actual.getHeader("Reply-To"));
    assertEquals(
            "Xác nhận đơn hàng A123",
            actual.getSubject()
    );
    assertEquals(
            "order-receipt",
            actual.getHeader("X-Template-Id", null)
    );
    assertEquals(
            "ORDER_RECEIPT",
            actual.getHeader("X-Notification-Type", null)
    );
}
~~~

Test này không sử dụng network, nhưng đọc giá trị đã được lưu bởi Jakarta Mail và giúp phát hiện các lỗi:

- địa chỉ From bị đổi nhầm;
- thiếu Bcc/Reply-To;
- email gửi cho recipient sai;
- subject thiếu order number hoặc lỗi encoding;
- template header bị thiếu hoặc sai giá trị;
- service không gọi `send`.

Nếu application contract quy định không được có Cc/Bcc, hãy assert `null`/empty tương ứng thay vì dùng cùng fixture trên.

## 21. Những anti-pattern thường gặp

| Anti-pattern | Vì sao không tốt | Cách thay |
| --- | --- | --- |
| Chỉ `verify(send(any()))` | Không biết nội dung/header đúng không | ArgumentCaptor + MimeMessage typed getters |
| Mock cả MimeMessage | Getter không tự phản ánh setter | Dùng MimeMessage thật trong bộ nhớ |
| Bắt buộc SMTP test server trong mọi unit test | Test chậm, nhiều phụ thuộc | Mock JavaMailSender |
| So sánh raw Subject với Unicode trực tiếp | MIME encoded-word làm sai assertion | `getSubject()` |
| Assert root `Content-Type=text/html` với multipart | Root thực tế là multipart | Duyệt body parts |
| Hard-code body part index | Cấu trúc MIME lồng thay đổi | Recursive MIME traversal |
| Hard-code boundary và Message-ID | Thư viện có thể sinh động | Assert semantic/round-trip |
| Coi Bcc phải vắng mặt trên object trước-send | Bcc vẫn cần cho envelope | Assert recipient, test transport riêng |
| Coi `getReplyTo()` khẳng định header Reply-To có mặt | Có thể fallback về From | Kiểm tra thêm raw header |
| Assert raw Content-Transfer-Encoding cố định | Encoding hợp lệ có nhiều kiểu | Đọc decoded content |
| Coi `send` mock trả bình thường là SMTP thành công | Mock không kết nối mạng | Integration test SMTP riêng |
| Assert DKIM-Signature do ESP thêm trong unit test | Provider ký sau khi submit | Test domain/provider/receiver |
| Không stub `createMimeMessage()` | Mock trả null | Trả MimeMessage thật |
| Không chạy MimeMessagePreparator callback | Không có message được chuẩn bị | `doAnswer` gọi `prepare` |
| `saveChanges()` ở mọi assertion | Có thể thay đổi header động | Chỉ dùng khi test serialize |
| Log raw MIME chứa dữ liệu thật | Rò rỉ recipient/body/token | Fixture giả, log tối thiểu |

## 22. Checklist khi viết unit test MimeMessage

### Setup

- [ ] Mock `JavaMailSender`, không gọi SMTP thật.
- [ ] Stub `createMimeMessage()` trả `MimeMessage` thật với `Session` trong bộ nhớ.
- [ ] Nếu dùng `MimeMessagePreparator`, mock phải thực thi preparator có kiểm soát.
- [ ] Không khởi động toàn bộ Spring context nếu constructor injection đơn giản đã đủ.

### Header và recipient

- [ ] Kiểm tra đúng From mailbox và display name nếu có.
- [ ] Kiểm tra To/Cc/Bcc bằng `getRecipients()`.
- [ ] Kiểm tra Reply-To; khi cần, kiểm tra header thực sự có mặt.
- [ ] Kiểm tra subject Unicode bằng `getSubject()`.
- [ ] Kiểm tra custom header bằng `getHeader()`.
- [ ] Kiểm tra không có header nhạy cảm hoặc sai chính sách.

### MIME

- [ ] Kiểm tra plain text và HTML bằng MIME tree traversal.
- [ ] Không hard-code thứ tự body part nếu contract không quy định.
- [ ] Kiểm tra charset và nội dung đã decode.
- [ ] Kiểm tra attachment filename/content type/bytes khi thuộc contract.
- [ ] Kiểm tra CID inline và liên kết HTML khi có.

### Tính ổn định và giới hạn

- [ ] Không hard-code Date, Message-ID, boundary hoặc raw header folding nếu không cần.
- [ ] Chỉ gọi `saveChanges()` khi muốn kiểm tra serialization hoặc header do thư viện sinh.
- [ ] Test invalid input không gọi `send`.
- [ ] Không coi unit test là bằng chứng SMTP/ESP delivery hoặc DKIM/DMARC.
- [ ] Không dùng email người thật, secret và token trong fixture/log.

## 23. Những điều cần nhớ

- **MimeMessage là cấu trúc dữ liệu thật**, có thể tạo và đọc hoàn toàn trong bộ nhớ mà không cần SMTP.
- **JavaMailSender nên được mock**, còn `MimeMessage` nên là object thật để các setter/getter của Jakarta Mail hoạt động.
- `ArgumentCaptor<MimeMessage>` giúp lấy message service đã chuyển cho `send`.
- Đọc From/To/Cc/Bcc/Reply-To bằng API typed; không parse raw header khi không cần.
- `getSubject()` phù hợp để assert tiêu đề tiếng Việt đã decode.
- `getHeader()` dùng cho custom header; chú ý giá trị null, nhiều lần xuất hiện và header folding.
- Root MIME có thể là `multipart/*`; body plain/HTML và attachment nằm trong các part lồng nhau.
- `saveChanges()` và `writeTo()` có thể sinh/cập nhật những header như Message-ID/Date/MIME metadata.
- **Bcc trong MimeMessage trước gửi** không đồng nghĩa Bcc sẽ xuất hiện công khai ở email cuối.
- Test với sender mock chứng minh **cấu trúc email được chuẩn bị**, không chứng minh SMTP acceptance, delivery hoặc inbox placement.

Khi kiểm thử Spring Framework Mail, cách chắc chắn và dễ bảo trì là **capture MimeMessage thật rồi kiểm tra ý nghĩa của nó bằng Jakarta Mail API**. Nhờ vậy, unit test phát hiện được lỗi cấu hình người nhận, tiêu đề, header, charset và MIME parts mà vẫn chạy nhanh, không cần SMTP server và không phụ thuộc những byte động sinh ra khi message được serialize.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper` và gửi MIME.
- **Spring Framework API — JavaMailSender:** các overload `send(MimeMessage)`, `send(MimeMessagePreparator)`.
- **Spring Framework API — MimeMessageHelper:** các hàm set From/To/Cc/Bcc/Reply-To/Subject/Text và multipart modes.
- **Jakarta Mail API — MimeMessage:** `getFrom`, `getRecipients`, `getReplyTo`, `getSubject`, `getHeader`, `saveChanges`, `writeTo`.
- **Jakarta Mail API — Multipart, BodyPart và Part:** duyệt MIME tree, Content-Type, Content-ID và attachment.
- **JUnit Jupiter User Guide:** cấu trúc unit test và assertions.
- **Mockito Documentation:** `ArgumentCaptor`, `verify`, `when`, `doAnswer` và `MockitoExtension`.
- **RFC 5322 — Internet Message Format:** header email, mailbox syntax và cấu trúc message.
- **RFC 2045–2049 — MIME:** Content-Type, transfer encoding, charset, encoded words và multipart.
- **RFC 2369 và RFC 8058:** `List-Unsubscribe` và one-click unsubscribe khi kiểm thử header marketing.
