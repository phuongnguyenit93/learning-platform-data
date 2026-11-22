# Kiểm thử subject, From, To, Cc và Bcc

## 1. Mục tiêu kiểm thử địa chỉ và tiêu đề email

Trong ứng dụng dùng **Spring Framework Mail**, một email không chỉ cần gửi thành công qua SMTP mà còn phải có **tiêu đề (Subject)** và các địa chỉ **From, To, Cc, Bcc** đúng với quy tắc nghiệp vụ. Chỉ một lỗi nhỏ khi ánh xạ dữ liệu vào header cũng có thể khiến thông báo không tới người cần nhận, được gửi tới sai nhóm hoặc làm lộ người nhận.

Ví dụ:

- Email xác nhận đơn hàng phải gửi **To** đúng khách hàng sở hữu đơn.
- **From** phải là địa chỉ được hệ thống cho phép gửi, không lấy tùy ý từ request.
- **Cc** chỉ chứa những người được phép biết có thư gửi chung.
- **Bcc** được dùng khi cần gửi cho người nhận bổ sung nhưng không muốn công khai danh sách đó với những người nhận khác.
- **Subject** phải nói đúng sự kiện, mã đơn và ngôn ngữ đã chọn.

Vì vậy, khi kiểm thử đơn vị lớp gửi email, cần xác nhận **đúng dữ liệu được đưa vào đối tượng mail trước lúc gửi**, thay vì chỉ xác nhận phương thức send được gọi một lần.

Trong Spring Framework Mail có hai hướng thường gặp:

1. **SimpleMailMessage** — phù hợp email plain text đơn giản.
2. **MimeMessage** tạo qua **JavaMailSender** và hỗ trợ bởi **MimeMessageHelper** — phù hợp email có HTML, tên hiển thị, nhiều nội dung MIME hoặc attachment.

Với cả hai, có thể dùng **JUnit 5** và **Mockito** để chặn lời gọi gửi và kiểm tra thuộc tính đã được đặt, **không cần kết nối SMTP thật**.

## 2. Hiểu đúng subject, From, To, Cc và Bcc

| Trường | Vai trò | Điều cần xác minh trong unit test |
|---|---|---|
| **Subject** | Tiêu đề mà người nhận nhìn thấy | Đúng thông điệp, ngôn ngữ, biến nghiệp vụ; không null/trống trái chính sách |
| **From** | Địa chỉ tác giả/người gửi hiển thị | Đúng địa chỉ gửi được cấp quyền |
| **To** | Người nhận chính | Đúng đối tượng nghiệp vụ, số lượng và địa chỉ |
| **Cc** | Người nhận bản sao công khai | Đúng danh sách được phép thấy nhau |
| **Bcc** | Người nhận bản sao kín | Có mặt trong danh sách người nhận gửi, không bị đưa nhầm vào To/Cc |

Sơ đồ:

~~~text
Business event / Notification request
               |
               v
      Notification service
               |
               +-- Subject = "Đơn hàng ORD-101 đã giao"
               +-- From    = "orders@example.com"
               +-- To      = ["buyer@example.net"]
               +-- Cc      = ["agent@example.com"]
               +-- Bcc     = ["audit@example.com"]
               |
               v
      SimpleMailMessage / MimeMessage
               |
               v
         JavaMailSender.send(...)
~~~

### Một phân biệt liên quan: From không phải SMTP envelope sender

**From** trong email là header hiển thị, còn **SMTP MAIL FROM** là envelope sender dùng trong giao thức SMTP để xác định reverse-path/bounce address. Kiểm thử **MimeMessage.getFrom()** xác nhận header From; nó **không** chứng minh transport sẽ dùng giá trị đó cho lệnh MAIL FROM. Nếu nghiệp vụ yêu cầu bounce address riêng, cần kiểm tra cấu hình SMTP transport hoặc tích hợp với provider ở một lớp test khác.

### Bcc không đồng nghĩa với mã hóa nội dung

Bcc chỉ nhằm hạn chế người nhận khác nhìn thấy danh sách địa chỉ Bcc. Nó không mã hóa nội dung email, không bảo đảm quyền truy cập mailbox và không thay thế kiểm tra phân quyền. Các test Bcc cũng cần phân biệt **đối tượng MimeMessage trước khi gửi** với **dữ liệu MIME thực tế ở phiên SMTP**.

## 3. Phạm vi của một unit test

Unit test lý tưởng kiểm tra lớp chịu trách nhiệm **tạo dữ liệu email**:

~~~text
JUnit 5 test
      |
      v
NotificationService thực
      |
      v
JavaMailSender được mock bằng Mockito
      |
      v
Captor lấy SimpleMailMessage/MimeMessage
      |
      v
Assertions: Subject, From, To, Cc, Bcc
~~~

Unit test có thể chứng minh:

- Service chọn đúng recipient dựa trên dữ liệu đã truyền.
- Service đã đặt header và subject vào đúng message.
- Service không đưa địa chỉ Bcc vào To/Cc.
- Service gọi JavaMailSender với đối tượng đã được chuẩn bị.
- Dữ liệu tùy chọn như Cc và Bcc được xử lý đúng khi rỗng.

Unit test **không chứng minh**:

- SMTP server có thật sự chấp nhận email hay không.
- Provider có thay đổi From hoặc reverse-path không.
- Email đã vào Inbox hoặc bị lọc Spam không.
- Danh sách Bcc có được loại khỏi dữ liệu header truyền tới recipient bởi transport không.
- Tất cả client hiển thị Subject giống nhau.

Những điều đó cần **integration test với SMTP test server/ESP sandbox** hoặc kiểm thử hệ thống theo môi trường cho phép.

## 4. Dependency cho ví dụ

Ví dụ Spring Boot dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter mail cung cấp integration Spring Mail/Jakarta Mail cho phần triển khai, còn starter test thường cung cấp JUnit Jupiter, Mockito và assertions dùng trong ví dụ. Nếu dự án dùng Spring Framework thuần hoặc đã quản lý dependency riêng, cần thêm những thư viện tương ứng với phiên bản đang sử dụng.

Với hệ Spring Boot 3 / Spring Framework 6 trở lên, các ví dụ sử dụng package **jakarta.mail** thay vì **javax.mail** của thế hệ cũ.

### Các thành phần kiểm thử

- **JUnit 5**: chạy test và kiểm tra kết quả bằng assertEquals, assertArrayEquals, assertThrows...
- **Mockito**: mock JavaMailSender, chặn lời gọi send, dùng ArgumentCaptor.
- **Jakarta Mail**: cho phép tạo MimeMessage thật trong bộ nhớ để kiểm tra header.
- **Không cần @SpringBootTest** cho những bài test thuần của một service dùng constructor injection.

## 5. Ví dụ ứng dụng: gửi email plain text với SimpleMailMessage

Trước tiên xét email không có HTML hoặc attachment. Khi đó **SimpleMailMessage** dễ tạo và dễ kiểm thử.

Định nghĩa đầu vào:

~~~java
import java.util.List;

public record PlainMailRequest(
        String subject,
        String from,
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String body
) {
}
~~~

Service tạo thông điệp:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class PlainMailService {

    private final JavaMailSender mailSender;

    public PlainMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(PlainMailRequest request) {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setSubject(request.subject());
        message.setFrom(request.from());
        message.setTo(request.to().toArray(String[]::new));

        if (!request.cc().isEmpty()) {
            message.setCc(request.cc().toArray(String[]::new));
        }
        if (!request.bcc().isEmpty()) {
            message.setBcc(request.bcc().toArray(String[]::new));
        }

        message.setText(request.body());

        mailSender.send(message);
    }
}
~~~

Service này giả định request đã được kiểm tra đầu vào và các list không null. Trong ứng dụng thật cần xác thực recipient, bảo đảm sender thuộc danh sách cho phép và xử lý lỗi dữ liệu. Mục tiêu của ví dụ là **kiểm thử việc gán field**, không phải xây dựng toàn bộ hệ thống email.

Các phương thức SimpleMailMessage:

| Setter | Getter để test |
|---|---|
| setSubject(String) | getSubject() |
| setFrom(String) | getFrom() |
| setTo(String...) | getTo() |
| setCc(String...) | getCc() |
| setBcc(String...) | getBcc() |
| setText(String) | getText() |

Các getter của danh sách người nhận có thể trả về **null** nếu field chưa từng được gán. Đây là điểm cần lưu ý khi kiểm thử trường hợp optional.

## 6. Test SimpleMailMessage bằng Mockito ArgumentCaptor

Ví dụ unit test với JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class PlainMailServiceTest {

    @Test
    void sendsCorrectSubjectAndAddresses() {
        JavaMailSender sender = mock(JavaMailSender.class);
        PlainMailService service = new PlainMailService(sender);

        PlainMailRequest request = new PlainMailRequest(
                "Đơn hàng ORD-101 đã giao",
                "orders@example.com",
                List.of("buyer@example.net"),
                List.of("agent@example.com"),
                List.of("audit@example.com"),
                "Đơn hàng ORD-101 đã được giao."
        );

        service.send(request);

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage actual = captor.getValue();

        assertEquals(
                "Đơn hàng ORD-101 đã giao",
                actual.getSubject()
        );
        assertEquals(
                "orders@example.com",
                actual.getFrom()
        );
        assertArrayEquals(
                new String[] { "buyer@example.net" },
                actual.getTo()
        );
        assertArrayEquals(
                new String[] { "agent@example.com" },
                actual.getCc()
        );
        assertArrayEquals(
                new String[] { "audit@example.com" },
                actual.getBcc()
        );
        assertEquals(
                "Đơn hàng ORD-101 đã được giao.",
                actual.getText()
        );
    }
}
~~~

### Test này kiểm chứng gì?

1. **Service thật** được thực thi.
2. **JavaMailSender** bị mock, nên không gửi ra mạng.
3. **ArgumentCaptor** lấy đúng đối tượng SimpleMailMessage mà service chuyển cho sender.
4. Assertions so sánh Subject, From, To, Cc, Bcc và body.

Đáng chú ý là **JavaMailSender.send** có nhiều overload. Dùng **ArgumentCaptor<SimpleMailMessage>** giúp Mockito chọn đúng overload **send(SimpleMailMessage)**, thay vì nhầm với overload dành cho MimeMessage hoặc mảng message.

## 7. Kiểm tra Cc/Bcc tùy chọn trong SimpleMailMessage

Không phải email nào cũng có Cc và Bcc. Ví dụ notification một người nhận chỉ cần To:

~~~java
@Test
void leavesCcAndBccUnsetWhenListsAreEmpty() {
    JavaMailSender sender = mock(JavaMailSender.class);
    PlainMailService service = new PlainMailService(sender);

    service.send(new PlainMailRequest(
            "Mã xác nhận",
            "security@example.com",
            List.of("owner@example.net"),
            List.of(),
            List.of(),
            "Mã xác nhận của bạn đã được tạo."
    ));

    ArgumentCaptor<SimpleMailMessage> captor =
            ArgumentCaptor.forClass(SimpleMailMessage.class);
    verify(sender).send(captor.capture());

    SimpleMailMessage actual = captor.getValue();

    assertArrayEquals(
            new String[] { "owner@example.net" },
            actual.getTo()
    );
    assertNull(actual.getCc());
    assertNull(actual.getBcc());
}
~~~

Ví dụ này cần static import **assertNull** của JUnit 5. Hai assertion null phản ánh **triển khai PlainMailService hiện tại không gọi setCc/setBcc nếu list rỗng**.

Nếu service chọn gọi **setCc(new String[0])** hoặc **setBcc(new String[0])**, biểu diễn nội bộ có thể là mảng rỗng thay vì null. Test nên ràng buộc **quy tắc nghiệp vụ** (không có người nhận phụ) và contract của service, không phụ thuộc tùy tiện vào một cách biểu diễn nếu không quan trọng.

### Kiểm tra nhiều To và Cc

~~~java
assertArrayEquals(
        new String[] {
            "buyer@example.net",
            "co-owner@example.net"
        },
        actual.getTo()
);

assertArrayEquals(
        new String[] {
            "support@example.com",
            "manager@example.com"
        },
        actual.getCc()
);
~~~

Nếu ứng dụng định nghĩa thứ tự recipient có ý nghĩa, có thể kiểm tra mảng theo thứ tự như trên. Nếu quy tắc chỉ yêu cầu **tập người nhận**, nên so sánh theo tập để test không phụ thuộc thứ tự mà nghiệp vụ không cam kết.

## 8. Khi nào nên dùng MimeMessage thay cho SimpleMailMessage?

**SimpleMailMessage** biểu diễn email text đơn giản với các thuộc tính thông dụng. Khi ứng dụng cần định dạng MIME, tên người gửi có dấu, HTML, inline image hoặc attachment, thường cần **MimeMessage** và **MimeMessageHelper**.

| Nhu cầu | SimpleMailMessage | MimeMessage + MimeMessageHelper |
|---|---|---|
| Subject, From, To, Cc, Bcc | Có | Có |
| Plain text | Có | Có |
| HTML | Không dành cho HTML MIME | Có |
| Plain text + HTML alternative | Không | Có |
| Attachment | Không | Có |
| Inline resources | Không | Có |
| Display name có Unicode | Không có API riêng như MimeMessageHelper | Có |
| Các MIME headers phức tạp | Hạn chế | Có |

Với MimeMessage, assertion nên đọc **đối tượng MimeMessage thực tế**, không tìm getter trên MimeMessageHelper. Helper là lớp hỗ trợ cấu hình; các trường được lưu vào message.

## 9. Tạo một service dùng MimeMessageHelper

Đầu vào minh họa:

~~~java
import java.util.List;

public record MimeMailRequest(
        String subject,
        String from,
        List<String> to,
        List<String> cc,
        List<String> bcc,
        String body
) {
}
~~~

Service:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MimeMailService {

    private final JavaMailSender mailSender;

    public MimeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(MimeMailRequest request)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name()
        );

        helper.setSubject(request.subject());
        helper.setFrom(request.from());
        helper.setTo(request.to().toArray(String[]::new));

        if (!request.cc().isEmpty()) {
            helper.setCc(request.cc().toArray(String[]::new));
        }
        if (!request.bcc().isEmpty()) {
            helper.setBcc(request.bcc().toArray(String[]::new));
        }

        helper.setText(request.body(), false);
        mailSender.send(message);
    }
}
~~~

Ở đây:

- **createMimeMessage()** tạo đối tượng MimeMessage.
- **MimeMessageHelper** đặt Subject và recipient vào header của message.
- Tham số **false** trong constructor cho biết ví dụ không cần multipart.
- **UTF-8** hỗ trợ tiêu đề và nội dung tiếng Việt.
- **setText(body, false)** tạo nội dung plain text.
- **send(message)** gọi tầng SMTP abstraction.

Đây là một service minh họa chỉ tập trung vào việc gán header. Dữ liệu đầu vào cần được validate ở boundary phù hợp trước khi gọi service. Trong ứng dụng thật, có thể chuyển **MessagingException** thành exception của tầng application hoặc Spring Mail tùy thiết kế.

## 10. Mock JavaMailSender nhưng dùng MimeMessage thật

Khi unit test MimeMessage, một cách thực dụng là **mock JavaMailSender** nhưng trả về **MimeMessage thật được tạo trong bộ nhớ**:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);

when(sender.createMimeMessage()).thenAnswer(invocation ->
        new MimeMessage(
                Session.getInstance(new Properties())
        )
);
~~~

Lý do:

- **MimeMessageHelper** cần tương tác với hành vi MIME thật để encode và gán các trường.
- Nếu mock luôn **MimeMessage**, những setter/getter nội bộ có thể không hoạt động như một message thật; test phải dựng nhiều stub không cần thiết.
- **Session.getInstance(new Properties())** không tự mở kết nối SMTP.
- Lời gọi **send(message)** vẫn đi tới mock; không có email thật được gửi.

Chỉ có **MimeMessage** là đối tượng thật ở đây; **JavaMailSender** là mock.

## 11. Unit test đầy đủ Subject, From, To, Cc và Bcc của MimeMessage

Ví dụ test có thể viết độc lập:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.util.Arrays;
import java.util.List;
import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class MimeMailServiceTest {

    @Test
    void sendsExpectedSubjectAndRecipientHeaders() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);

        when(sender.createMimeMessage()).thenAnswer(invocation ->
                new MimeMessage(
                        Session.getInstance(new Properties())
                )
        );

        MimeMailService service = new MimeMailService(sender);

        service.send(new MimeMailRequest(
                "Đơn hàng ORD-101 đã giao",
                "orders@example.com",
                List.of("buyer@example.net"),
                List.of("agent@example.com"),
                List.of("audit@example.com"),
                "Đơn hàng đã được giao thành công."
        ));

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender).send(captor.capture());

        MimeMessage actual = captor.getValue();

        assertEquals(
                "Đơn hàng ORD-101 đã giao",
                actual.getSubject()
        );

        assertEquals(
                List.of("orders@example.com"),
                emailAddresses(actual.getFrom())
        );

        assertEquals(
                List.of("buyer@example.net"),
                emailAddresses(
                        actual.getRecipients(Message.RecipientType.TO)
                )
        );

        assertEquals(
                List.of("agent@example.com"),
                emailAddresses(
                        actual.getRecipients(Message.RecipientType.CC)
                )
        );

        assertEquals(
                List.of("audit@example.com"),
                emailAddresses(
                        actual.getRecipients(Message.RecipientType.BCC)
                )
        );
    }

    private static List<String> emailAddresses(Address[] addresses) {
        if (addresses == null) {
            return List.of();
        }

        return Arrays.stream(addresses)
                .map(address -> ((InternetAddress) address).getAddress())
                .toList();
    }
}
~~~

**emailAddresses(...)** là helper của test chuyển các **InternetAddress** thành chuỗi email để dễ so sánh. Với header Internet email thông thường, các Address thường là InternetAddress. Nếu ứng dụng sử dụng address type khác, helper cần xử lý phù hợp thay vì cast không kiểm tra.

### Điều quan trọng về overload

**JavaMailSender** có overload khác nhau cho **MimeMessage** và **SimpleMailMessage**. Trong test trên, captor được định kiểu **MimeMessage**, nên **verify(sender).send(captor.capture())** nhắm đúng lời gọi **send(MimeMessage)**.

Nếu code sản xuất gọi **send(MimeMessage[])**, phải dùng một captor cho mảng hoặc xác minh từng phần tử theo cách phù hợp; test ví dụ này không khẳng định mọi overload đều tương đương.

## 12. Vì sao đọc MimeMessage.getRecipients thay vì đọc raw header?

Jakarta Mail cung cấp:

~~~java
actual.getFrom();
actual.getSubject();
actual.getRecipients(Message.RecipientType.TO);
actual.getRecipients(Message.RecipientType.CC);
actual.getRecipients(Message.RecipientType.BCC);
~~~

Đây là API có ngữ nghĩa phù hợp để kiểm tra địa chỉ:

- **getFrom()** trả về mảng Address, không phải một String.
- **getSubject()** trả về tiêu đề đã được decode theo cơ chế của Jakarta Mail.
- **getRecipients(...)** trả các Address theo loại To, Cc hoặc Bcc.
- Field không tồn tại có thể trả **null**.

Tránh chỉ so sánh:

~~~java
assertEquals(
        "buyer@example.net",
        actual.getHeader("To", null)
);
~~~

Kết quả raw header có thể bị ảnh hưởng bởi cách encode tên hiển thị, folding hoặc định dạng nhiều địa chỉ; so sánh chuỗi nguyên dạng dễ khiến test thất bại dù email hợp lệ. **getRecipients(...)** phản ánh ý nghĩa địa chỉ rõ hơn.

Tuy vậy, nếu mục tiêu là kiểm tra wire/header serialization, một test thấp tầng có thể kiểm tra header đã encode. Đó là mục tiêu khác với unit test logic chọn recipient.

## 13. Kiểm tra Subject tiếng Việt và Unicode

Subject thường chứa tên người dùng, mã đơn hoặc thông báo tiếng Việt có dấu:

~~~text
Đơn hàng ORD-101 đã được xác nhận
Lịch hẹn của bạn đã thay đổi
Mã khôi phục tài khoản
~~~

Khi dùng MimeMessageHelper với UTF-8, unit test nên so sánh **giá trị sau decode**:

~~~java
assertEquals(
        "Đơn hàng ORD-101 đã được xác nhận",
        actual.getSubject()
);
~~~

Lợi ích:

- Kiểm tra renderer/service chọn đúng nội dung.
- Tránh phụ thuộc cú pháp MIME encoded-word cụ thể.
- Không yêu cầu biết Jakarta Mail sẽ gấp dòng header ra sao.

Không nên viết test buộc Subject raw phải bằng một chuỗi ASCII cố định như:

~~~text
=?UTF-8?B?...?=
~~~

Header có thể được mã hóa theo những hình thức hợp lệ khác nhau. Chỉ khi đang kiểm thử **serialization/transport** thì mới nên kiểm tra định dạng MIME ở tầng thấp.

### Trường hợp Subject có biến nghiệp vụ

~~~java
String expectedSubject =
        "Thanh toán thành công cho đơn " + orderCode;

assertEquals(expectedSubject, actual.getSubject());
~~~

Đảm bảo biến được lấy từ đúng đối tượng nghiệp vụ và không bị lẫn với một event khác. Không dùng dữ liệu mang tính thời điểm hoặc ngẫu nhiên trong subject test nếu chưa khống chế nguồn thời gian/ID.

## 14. From có display name: kiểm tra địa chỉ và tên riêng

Trong ứng dụng thực, người dùng có thể nhìn thấy:

~~~text
From: Cửa hàng Ví dụ <orders@example.com>
~~~

Để tạo header này, có thể dùng:

~~~java
helper.setFrom(
        "orders@example.com",
        "Cửa hàng Ví dụ"
);
~~~

Unit test có thể kiểm tra cả hai thành phần:

~~~java
InternetAddress senderAddress =
        (InternetAddress) actual.getFrom()[0];

assertEquals(
        "orders@example.com",
        senderAddress.getAddress()
);
assertEquals(
        "Cửa hàng Ví dụ",
        senderAddress.getPersonal()
);
~~~

**getPersonal()** trả tên hiển thị đã được decode khi Jakarta Mail hỗ trợ. Trong test, đừng chỉ kiểm tra **getFrom()[0].toString()** vì chuỗi đó có thể chứa encoded-word hoặc dấu quote tùy cách biểu diễn hợp lệ.

Một email có thể có nhiều tác giả trong header From theo định dạng mail, nhưng đa số email giao dịch trong ứng dụng nên sử dụng một địa chỉ From đã được phê duyệt. Nếu service có quy tắc chỉ cho phép một From, hãy kiểm tra đúng số lượng.

## 15. So sánh danh sách To, Cc và Bcc theo tập khi phù hợp

Một service có thể được phép thay đổi thứ tự recipient mà không làm thay đổi ý nghĩa nghiệp vụ. Khi đó việc assert mảng theo thứ tự không cần thiết có thể làm test dễ vỡ.

Ví dụ:

~~~java
import java.util.Set;

Set<String> recipients = Set.copyOf(
        emailAddresses(
                actual.getRecipients(Message.RecipientType.CC)
        )
);

assertEquals(
        Set.of(
                "sales@example.com",
                "support@example.com"
        ),
        recipients
);
~~~

**Lưu ý về duplicate:** chuyển List sang Set sẽ làm mất thông tin số lượng và các phần tử lặp. Nếu nghiệp vụ yêu cầu **không gửi trùng recipient**, cần kiểm tra riêng số lượng hoặc quy tắc dedup. Không chỉ so sánh Set rồi cho rằng dữ liệu không có duplicate.

### Kiểm tra trường hợp không có Cc/Bcc

Với MimeMessage:

~~~java
assertEquals(
        List.of(),
        emailAddresses(
                actual.getRecipients(Message.RecipientType.CC)
        )
);

assertEquals(
        List.of(),
        emailAddresses(
                actual.getRecipients(Message.RecipientType.BCC)
        )
);
~~~

Helper test chuyển null thành List.of() để thể hiện rõ **không có người nhận thuộc loại đó**, tránh phụ thuộc vào null hay mảng rỗng.

## 16. Kiểm thử Bcc đúng: có người nhận nhưng không bị đưa vào To hoặc Cc

Bcc là trường cần kiểm tra đặc biệt vì lỗi dữ liệu có thể tiết lộ người nhận kín cho các người nhận khác.

Ở **mức unit test chuẩn bị MimeMessage**, có thể xác nhận:

~~~java
List<String> to = emailAddresses(
        actual.getRecipients(Message.RecipientType.TO)
);
List<String> cc = emailAddresses(
        actual.getRecipients(Message.RecipientType.CC)
);
List<String> bcc = emailAddresses(
        actual.getRecipients(Message.RecipientType.BCC)
);

assertEquals(
        List.of("customer@example.net"),
        to
);
assertEquals(
        List.of("manager@example.com"),
        cc
);
assertEquals(
        List.of("audit@example.com"),
        bcc
);

assertFalse(to.contains("audit@example.com"));
assertFalse(cc.contains("audit@example.com"));
~~~

Ví dụ cần import **assertFalse** của JUnit 5. Các assertion xác nhận **audit@example.com** được phân loại là Bcc chứ không nằm trong To hoặc Cc.

### Bcc header trước khi gửi khác Bcc header sau transport

Một nhầm lẫn thường gặp là viết test:

~~~java
// Không đúng mục tiêu đối với MimeMessage đang được chuẩn bị.
assertNull(actual.getRecipients(Message.RecipientType.BCC));
~~~

Nếu đã gọi **helper.setBcc(...)**, trong đối tượng **MimeMessage trước khi gửi**, danh sách Bcc cần còn truy xuất được để mail transport biết người nhận. Một unit test kiểm tra đối tượng pre-send nên **kỳ vọng có Bcc**, không xóa nó chỉ để đạt một assertion “không lộ”.

Quy tắc bảo mật thực sự cần kiểm tra ở chặng vận chuyển là:

- Địa chỉ Bcc được dùng làm recipient hợp lệ ở **SMTP envelope**.
- Người nhận To/Cc và Bcc không nhìn thấy danh sách Bcc trong **header của bản email được giao**.
- Không có chỗ nào trong **body, Subject hoặc các header tùy chỉnh** vô tình chép danh sách Bcc.

Hành vi header Bcc trên đường truyền phụ thuộc vào transport, việc tạo message và hạ tầng gửi. Vì vậy muốn khẳng định Bcc không bị lộ trong MIME DATA thực tế, cần test với **SMTP test server** và quan sát message được gửi đi, không chỉ đọc object trước khi send.

## 17. Integration test để kiểm tra quyền riêng tư của Bcc

Một test có thể dùng SMTP sandbox hoặc SMTP test server nhận kết nối cục bộ:

~~~text
Spring service
       |
       | RCPT TO:<customer@example.net>
       | RCPT TO:<audit@example.com>
       |
       | DATA:
       |   From: orders@example.com
       |   To: customer@example.net
       |   Subject: Xác nhận đơn hàng
       |   (không lộ audit@example.com)
       v
SMTP test server
       |
       +--> lưu envelope recipients
       +--> lưu MIME DATA thực tế
~~~

Các điều cần assert:

1. SMTP envelope có **customer@example.net** và **audit@example.com**.
2. MIME DATA mà các recipient nhận được không công khai danh sách Bcc.
3. Không có header To/Cc nào vô tình chứa audit@example.com.
4. Nếu service dùng header tùy chỉnh chứa ID nội bộ, header đó không tiết lộ dữ liệu không được phép.

Một số test server lưu message và envelope tách biệt, một số khác lưu raw SMTP session. Cần chọn công cụ có khả năng quan sát **cả envelope và DATA**, bởi chỉ xem header của một MimeMessage trước khi gửi không cung cấp đủ bằng chứng.

Không sử dụng tài khoản người nhận thật hoặc SMTP production chỉ để kiểm thử tính kín đáo của Bcc.

## 18. To/Cc/Bcc và chính sách phân quyền

Một email có thể có cấu trúc hợp lệ nhưng vẫn gửi sai người.

Ví dụ một đơn hàng thuộc khách hàng A, nhưng service vô tình dùng email khách hàng B:

~~~text
Order owner: A
Expected To: a@example.net
Actual To: b@example.net
~~~

MimeMessage hoàn toàn hợp lệ về cú pháp. Unit test phải kiểm tra **mapping nghiệp vụ**, không chỉ kiểm tra một địa chỉ có dấu @.

Nên chuẩn bị dữ liệu test có thể phân biệt rõ:

~~~text
ownerEmail      = owner@example.net
otherUserEmail  = other@example.net
supportEmail    = support@example.com
auditEmail      = audit@example.com
~~~

Assertions nên chỉ ra đúng vai trò:

~~~java
assertEquals(
        List.of("owner@example.net"),
        emailAddresses(
                actual.getRecipients(Message.RecipientType.TO)
        )
);
~~~

Nếu ứng dụng nhiều tenant, các bài test còn nên xác minh:

- Không thêm admin của tenant khác vào Cc.
- Không dùng địa chỉ From của thương hiệu/tenant khác.
- Người dùng không thể chỉ định một Bcc tùy ý mà vượt quyền.
- Không vô tình gửi dữ liệu của tenant A tới recipient của tenant B.

Đây là lỗi về **phân quyền và định tuyến thông tin**, không phải lỗi SMTP. Những test ở tầng application có thể dùng fake repository hoặc dữ liệu in-memory thay vì cần database thật.

## 19. Kiểm tra From không phụ thuộc input không tin cậy

Ví dụ API nhận yêu cầu gửi email:

~~~json
{
  "orderId": "ORD-101",
  "requestedFrom": "attacker@outside.example"
}
~~~

Nếu ứng dụng lấy **requestedFrom** trực tiếp để gọi **helper.setFrom(...)**, người dùng có thể cố mạo danh một sender hoặc phá vỡ xác thực domain.

Nên thiết kế service lấy From từ cấu hình do ứng dụng kiểm soát:

~~~java
public final class CustomerNotificationService {

    private final JavaMailSender sender;
    private final String approvedFrom;

    public CustomerNotificationService(
            JavaMailSender sender,
            String approvedFrom
    ) {
        this.sender = sender;
        this.approvedFrom = approvedFrom;
    }

    // Khi tạo message:
    // helper.setFrom(approvedFrom);
}
~~~

Unit test có thể đưa một request chứa **requestedFrom** giả mạo rồi xác nhận message thực tế vẫn dùng **approvedFrom**. Nếu ứng dụng cho phép chọn nhiều From theo tenant hoặc nhóm sản phẩm, hãy kiểm tra chính sách lựa chọn và danh sách domain được xác minh.

Không hard-code địa chỉ gửi cố định chỉ vì dễ test. Có thể inject configuration/port và kiểm tra nó được dùng đúng; giữ phần chọn sender ở tầng nghiệp vụ phù hợp.

## 20. Test recipient trùng giữa To, Cc và Bcc

Một recipient có thể vô tình xuất hiện đồng thời trong nhiều trường:

~~~text
To:   customer@example.net
Cc:   support@example.com
Bcc:  customer@example.net
~~~

Hậu quả tùy mail transport và provider: người nhận có thể nhận nhiều lần hoặc cách hiển thị không khớp mục đích. Nếu quy tắc nghiệp vụ là **mỗi địa chỉ chỉ xuất hiện ở một nhóm**, cần test trước khi gửi.

Ví dụ khi xây dựng model:

~~~java
Set<String> all = new HashSet<>();

for (String recipient : to) {
    assertTrue(all.add(recipient));
}
for (String recipient : cc) {
    assertTrue(all.add(recipient));
}
for (String recipient : bcc) {
    assertTrue(all.add(recipient));
}
~~~

Đây là cách minh họa kiểm tra duplicate cho dữ liệu test đã được chuẩn hóa. Với sản phẩm thật, quy tắc so sánh email cần được xác định rõ:

- Domain email không phân biệt chữ hoa/chữ thường theo DNS.
- Local-part theo tiêu chuẩn email không nên bị giả định lúc nào cũng case-insensitive, dù nhiều provider xử lý như vậy.
- Dấu chấm và plus addressing có thể có ý nghĩa khác nhau giữa các provider.

Không xóa dấu chấm, bỏ suffix sau dấu cộng hoặc lower-case toàn bộ địa chỉ theo quy tắc riêng của một nhà cung cấp để tạo thuật toán dedup cho mọi domain.

## 21. Test Subject không rỗng và không bị ánh xạ sai

Tùy yêu cầu nghiệp vụ, email có thể bắt buộc có subject có ý nghĩa. Ví dụ đơn hàng đã giao không nên có:

~~~text
Subject: null
Subject: ""
Subject: "Untitled"
~~~

Với service có validation, có thể test:

~~~java
@Test
void rejectsBlankSubjectBeforeSending() {
    JavaMailSender sender = mock(JavaMailSender.class);
    ValidatingMailService service = new ValidatingMailService(sender);

    IllegalArgumentException exception = assertThrows(
            IllegalArgumentException.class,
            () -> service.send(requestWithSubject("   "))
    );

    assertEquals(
            "Subject must not be blank",
            exception.getMessage()
    );
    verifyNoInteractions(sender);
}
~~~

**ValidatingMailService** và **requestWithSubject(...)** là thành phần ví dụ ứng dụng cần triển khai; chúng không phải API mặc định của Spring Mail. Test chỉ có ý nghĩa nếu contract của service thực sự quy định subject không được blank và validation diễn ra trước khi tương tác mail sender.

Với nội dung subject có dữ liệu do người dùng nhập, cần cân nhắc cả ký tự xuống dòng, dữ liệu không hợp lệ hoặc dấu hiệu header injection. Kiểm tra đầu vào ở boundary và dùng API tạo MIME đúng cách thay vì nối raw SMTP header thủ công.

## 22. Test khi To thiếu hoặc không có recipient hợp lệ

Một tình huống cần chính sách rõ ràng là email không có **To**, nhưng có Cc hoặc Bcc. Về mặt SMTP, recipient có thể được cung cấp qua các loại địa chỉ khác nhau. Tuy vậy, **nhiều ứng dụng nghiệp vụ yêu cầu ít nhất một người nhận chính** để tránh lỗi định tuyến.

Ví dụ chính sách:

~~~text
Business rule:
    To không được rỗng với email xác nhận đơn hàng.

Input:
    To  = []
    Cc  = ["agent@example.com"]
    Bcc = ["audit@example.com"]

Expected:
    Reject request trước khi gửi.
~~~

Nếu hệ thống cho phép email chỉ có Bcc, đừng áp dụng rule “phải có To” một cách tuyệt đối. Thay vào đó cần định nghĩa ít nhất một **SMTP recipient** và kiểm tra đúng chính sách hiển thị người nhận của loại email đó.

Test nên xác minh cả **không gọi mailSender.send(...) khi request không hợp lệ**, để tránh tạo tác dụng phụ trước khi validation kết thúc.

## 23. Kiểm tra input null và list không thể thay đổi

Với các record chứa List, cần quyết định xử lý null:

- **Null**: dữ liệu chưa được cung cấp hoặc có lỗi ở caller.
- **List rỗng**: một danh sách recipient cố ý không có phần tử.

Nếu contract quy định các list không bao giờ null, có thể tạo snapshot phòng thủ:

~~~java
import java.util.List;
import java.util.Objects;

public record SafeMailRequest(
        String subject,
        String from,
        List<String> to,
        List<String> cc,
        List<String> bcc
) {
    public SafeMailRequest {
        subject = Objects.requireNonNull(subject);
        from = Objects.requireNonNull(from);
        to = List.copyOf(Objects.requireNonNull(to));
        cc = List.copyOf(Objects.requireNonNull(cc));
        bcc = List.copyOf(Objects.requireNonNull(bcc));
    }
}
~~~

**List.copyOf** tạo bản không sửa được và không cho phần tử null. Để trống Cc/Bcc, caller cần truyền **List.of()**. Service không bị ảnh hưởng nếu caller chỉnh sửa một ArrayList sau khi tạo request.

Nếu sản phẩm muốn mặc định null thành list rỗng, cách khác cũng có thể hợp lý, nhưng nên thể hiện rõ trong constructor và unit test. Đừng để NullPointerException ở đoạn **request.cc().isEmpty()** là cách duy nhất báo dữ liệu sai.

## 24. Test nhiều người nhận mà không nối địa chỉ thủ công

**MimeMessageHelper** có overload nhận mảng địa chỉ:

~~~java
helper.setTo(new String[] {
        "primary@example.net",
        "second@example.net"
});

helper.setCc(new String[] {
        "support@example.com",
        "manager@example.com"
});

helper.setBcc(new String[] {
        "audit@example.com",
        "compliance@example.com"
});
~~~

Ưu điểm là từng địa chỉ được xử lý theo API tương ứng. Tránh tự ghép một chuỗi header nhiều địa chỉ khi đã có API dành riêng cho recipient.

Test:

~~~java
assertEquals(
        Set.of(
                "primary@example.net",
                "second@example.net"
        ),
        Set.copyOf(
                emailAddresses(
                        actual.getRecipients(Message.RecipientType.TO)
                )
        )
);
~~~

Nếu danh sách có thể chứa duplicate, thêm assertion đếm riêng để không che giấu chúng bằng Set.

Một bài test về recipient không nên chỉ xác nhận **getAllRecipients().length**. Hai message có cùng tổng số recipient nhưng mapping giữa To/Cc/Bcc khác nhau vẫn có thể tạo hậu quả nghiệp vụ rất khác nhau.

## 25. Kiểm tra số lần gửi và tránh tác dụng phụ trong unit test

Một test chỉ xác nhận các header nhưng không xác nhận service thực sự gọi JavaMailSender vẫn có thể bỏ sót lỗi luồng điều khiển.

Ví dụ:

~~~java
ArgumentCaptor<MimeMessage> captor =
        ArgumentCaptor.forClass(MimeMessage.class);

verify(sender, times(1)).send(captor.capture());
~~~

Nếu service phải gửi đúng một thư, **times(1)** thể hiện rõ contract đó. Mockito mặc định cũng xem **verify(sender).send(...)** là một lần cho invocation được chỉ định.

Với request không hợp lệ:

~~~java
verify(sender, never()).send(any(MimeMessage.class));
~~~

Ví dụ trên cần static import **times**, **never** và **any**. Khi service có thể tạo message trước khi phát hiện lỗi, cần quyết định có chấp nhận lời gọi **createMimeMessage()** hay không; việc quan trọng nhất thường là **không gọi send** khi validation thất bại.

### Đừng kiểm tra thứ tự không có ý nghĩa

Một test không cần xác nhận rằng **setSubject** được gọi trước **setTo** nếu thứ tự setter không ảnh hưởng tới kết quả hoặc contract.

Test tốt ưu tiên:

- Subject cuối cùng đúng.
- Header From đúng.
- Danh sách To/Cc/Bcc đúng.
- Đúng số lần gửi.
- Không gửi khi dữ liệu không hợp lệ.

Chỉ kiểm tra thứ tự phương thức khi thứ tự đó thực sự tạo ra hành vi quan trọng.

## 26. Kiểm tra lỗi tạo MIME riêng với lỗi gửi SMTP

Khi tạo **MimeMessage**, những lỗi như địa chỉ không hợp lệ hoặc xử lý MIME có thể ném **MessagingException**. Khi gọi **JavaMailSender.send(...)**, tầng Spring Mail có thể ném **MailException** tùy lỗi gửi.

Nên phân biệt hai pha:

~~~text
PREPARE
  Create MimeMessage
  Set Subject / From / To / Cc / Bcc
  Set MIME body
      |
      v
SUBMIT
  JavaMailSender.send(...)
~~~

Một unit test có thể mô phỏng lỗi ở send bằng Mockito:

~~~java
import org.springframework.mail.MailSendException;

doThrow(new MailSendException("SMTP unavailable"))
        .when(sender)
        .send(any(MimeMessage.class));
~~~

Sau đó chạy service và kiểm tra cách ứng dụng xử lý lỗi theo contract: để exception lan lên, chuyển thành lỗi nghiệp vụ hay ghi notification retry. Không nên tự động thử lại toàn bộ lời gọi gửi chỉ vì có MailSendException; có những lỗi SMTP có kết quả không rõ và có thể gây gửi trùng.

### Không nhầm test header với test retry

Mục tiêu bài này là **Subject/From/To/Cc/Bcc**. Nếu service còn xử lý retry, nên có test riêng cho chính sách retry để tránh một test trộn quá nhiều hành vi không liên quan.

Ví dụ một test header chỉ nên thiết lập mock sender như một cộng tác viên ghi nhận lời gọi, không cần dựng SMTP server hoặc kiểm tra connection timeout.

## 27. Kiểm thử khi subject/recipient đến từ template

Trong nhiều ứng dụng, Subject không phải literal mà được render từ template và dữ liệu nghiệp vụ:

~~~java
String subject = subjectRenderer.render(
        "order.shipped.subject",
        Map.of(
                "orderCode", order.getCode(),
                "customerName", order.getCustomerName()
        )
);
~~~

Nếu dùng renderer riêng, có hai cách kiểm thử:

**Test resolver/template riêng:** kiểm tra template key, dữ liệu và ngôn ngữ tạo ra subject mong muốn.

**Test service gửi mail:** cấp subject đã được render hoặc một renderer fake rồi kiểm tra giá trị thực sự đặt vào MimeMessage.

Ví dụ:

~~~java
when(subjectRenderer.render(
        eq("order.shipped.subject"),
        anyMap()
)).thenReturn("Đơn ORD-101 đã gửi đi");
~~~

Sau khi service chạy:

~~~java
assertEquals(
        "Đơn ORD-101 đã gửi đi",
        actual.getSubject()
);
~~~

**subjectRenderer** trong ví dụ là interface riêng của ứng dụng, không phải thành phần mặc định của Spring Mail. Dùng Mockito để giữ test ở phạm vi lựa chọn và gán Subject, thay vì phụ thuộc vào hệ thống template file thực.

### Dữ liệu định dạng theo locale

Nếu ứng dụng hỗ trợ nhiều ngôn ngữ, nên có trường hợp:

~~~text
locale=vi-VN -> Subject: Đơn hàng đã được xác nhận
locale=en-US -> Subject: Your order is confirmed
~~~

Unit test cần kiểm tra cùng một event với locale khác nhau nhưng **recipient và From vẫn đúng**. Không thay đổi người nhận chỉ vì ngôn ngữ của nội dung đổi.

## 28. Test với JUnit 5 parameterized

Khi có nhiều loại notification nhưng cùng quy tắc From/To/Cc/Bcc, có thể dùng parameterized test để tránh sao chép nhiều test giống nhau.

Ví dụ kiểm thử loại thông báo và subject:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class MailSubjectPolicyTest {

    @ParameterizedTest
    @CsvSource({
        "ORDER_PAID, Thanh toán đã được ghi nhận",
        "ORDER_SHIPPED, Đơn hàng đang được giao",
        "ORDER_CANCELLED, Đơn hàng đã bị hủy"
    })
    void mapsEventToCorrectSubject(
            String eventType,
            String expectedSubject
    ) {
        String result = subjectPolicy.subjectFor(eventType);

        assertEquals(expectedSubject, result);
    }
}
~~~

Đây là khung minh họa: **subjectPolicy** cần là một object được khởi tạo trong test theo implementation của ứng dụng, không phải biến có sẵn của JUnit. Đoạn này tập trung vào việc mapping event sang subject.

Nếu muốn kiểm tra toàn bộ message cùng một lần, có thể dùng **@MethodSource** để cung cấp dữ liệu gồm:

- Event type.
- Expected Subject.
- Expected From.
- Danh sách To.
- Danh sách Cc.
- Danh sách Bcc.

Khi số ca kiểm thử nhiều, nên đặt tên test case để khi lỗi có thể biết ngay event và recipient policy nào sai.

## 29. Test khi có nhiều sender hoặc nhiều thương hiệu

Một hệ thống có thể dùng nhiều account SMTP:

~~~text
Transactional sender:
  From: receipts@example.com

Security sender:
  From: security@example.com

Support sender:
  From: support@example.com
~~~

Từng loại email cần dùng đúng From và đúng sender bean. Khi service nhận **JavaMailSender** qua constructor hoặc **@Qualifier**, có thể test riêng từng service với mock của sender tương ứng.

Ví dụ:

~~~java
JavaMailSender transactionalSender = mock(JavaMailSender.class);
JavaMailSender securitySender = mock(JavaMailSender.class);

// Tạo service dựa trên constructor của ứng dụng.
// Thực hiện gửi email bảo mật.

verify(securitySender).send(any(MimeMessage.class));
verify(transactionalSender, never())
        .send(any(MimeMessage.class));
~~~

Đây là cấu trúc ý tưởng; cần định nghĩa service và stub **createMimeMessage()** nếu nhánh gửi tạo MimeMessage. Nó hữu ích để ngăn một thông báo nhạy cảm vô tình đi qua sender marketing hoặc From của thương hiệu khác.

### Test multi-tenant

Nếu một tenant có địa chỉ From riêng, hãy dùng ít nhất hai tenant khác nhau:

~~~text
Tenant A:
  From = a-notifications@a.example
  To   = user-a@customer.example

Tenant B:
  From = b-notifications@b.example
  To   = user-b@customer.example
~~~

Test luồng gửi tenant A không được chứa recipient hoặc From của tenant B. Không dùng dữ liệu test giống hệt cho các tenant, vì test sẽ không phát hiện việc tráo tenant.

## 30. Test khi sender nhận mảng message

Spring Mail hỗ trợ gửi nhiều **SimpleMailMessage** hoặc **MimeMessage** trong một lời gọi. Khi batch là yêu cầu thực của service, cần kiểm tra từng phần tử:

~~~java
ArgumentCaptor<MimeMessage[]> captor =
        ArgumentCaptor.forClass(MimeMessage[].class);

verify(sender).send(captor.capture());

MimeMessage[] batch = captor.getValue();
assertEquals(2, batch.length);
~~~

Sau đó đọc **getSubject()**, **getFrom()** và **getRecipients(...)** cho từng message theo notification ID/test fixture.

Nếu thứ tự batch không được contract bảo đảm, không nên giả định message[0] luôn là loại A. Thay vào đó có thể ánh xạ theo ID hoặc subject duy nhất của dữ liệu thử, miễn không dùng thông tin nhạy cảm trong log.

### Bcc trong batch

Một lỗi nguy hiểm là dùng lại một MimeMessage rồi chỉ thay To giữa các vòng lặp mà quên xóa Cc/Bcc cũ. Khi đó người nhận của thư trước có thể bị giữ lại trong thư sau.

Test nên tạo hai notification có **danh sách recipient hoàn toàn khác nhau**, rồi kiểm tra:

- Message A chỉ chứa các recipient của A.
- Message B chỉ chứa các recipient của B.
- Không có địa chỉ từ B xuất hiện trong To/Cc/Bcc của A và ngược lại.

Nếu service được thiết kế tạo **MimeMessage mới cho mỗi thông báo**, test có thể assert hai phần tử là hai object độc lập và mỗi object có header riêng.

## 31. Có nên kiểm tra header bằng snapshot text?

Một snapshot kiểu:

~~~text
From: orders@example.com
To: buyer@example.net
Cc: agent@example.com
Bcc: audit@example.com
Subject: =?UTF-8?...?=
~~~

nghe có vẻ tiện lợi, nhưng có nhược điểm:

- Tên hiển thị có thể được encode bằng các phương thức MIME hợp lệ khác nhau.
- Thứ tự header có thể thay đổi.
- Header dài có thể bị fold qua nhiều dòng.
- MIME boundary và các thông số khác có thể thay đổi.
- Việc lưu raw Bcc và dữ liệu recipient vào snapshot có thể tạo rủi ro thông tin.

Với unit test logic định tuyến email, **assert theo API có ngữ nghĩa** thường rõ ràng và bền vững hơn:

~~~java
actual.getSubject();
actual.getFrom();
actual.getRecipients(Message.RecipientType.TO);
actual.getRecipients(Message.RecipientType.CC);
actual.getRecipients(Message.RecipientType.BCC);
~~~

Nếu cần snapshot, chỉ snapshot những trường ổn định đã được chuẩn hóa, và dùng dữ liệu test giả không nhạy cảm.

## 32. Giữ test độc lập, nhanh và có thể lặp lại

Một unit test email nên:

- Không gửi SMTP thật.
- Không đọc dữ liệu production hoặc tài khoản email thật.
- Không phụ thuộc thời gian hệ thống nếu subject dùng ngày tháng; inject Clock hoặc truyền thời điểm cố định.
- Không phụ thuộc vào thứ tự không được nghiệp vụ cam kết.
- Không cần khởi tạo toàn bộ Spring application context nếu chỉ test một service với constructor injection.
- Không ghi email address nhạy cảm vào test log.
- Dùng các địa chỉ thuộc domain ví dụ, không phải địa chỉ của người dùng thực.

### Dùng Clock nếu subject có ngày giờ

Ví dụ subject có ngày:

~~~text
Thông báo ngày 12/11/2026
~~~

Nếu code gọi **LocalDate.now()** trực tiếp, test có thể thất bại vào hôm khác. Có thể inject **java.time.Clock**:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Khi renderer dùng Clock này, ngày trong Subject được dự đoán chính xác. Lưu ý Instant trong ví dụ có thể tương ứng thời điểm khác nhau theo múi giờ; test cần định nghĩa rõ timezone của thông báo.

## 33. Dùng MockitoExtension và @Mock khi có nhiều dependency

Ở các ví dụ đầu, mock được tạo thủ công:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
~~~

Với service có nhiều dependency, có thể dùng Mockito extension của JUnit Jupiter:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

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
class MimeMailServiceWithExtensionTest {

    @Mock
    private JavaMailSender sender;

    private MimeMailService service;

    @BeforeEach
    void setUp() {
        when(sender.createMimeMessage()).thenAnswer(invocation ->
                new MimeMessage(
                        Session.getInstance(new Properties())
                )
        );

        service = new MimeMailService(sender);
    }

    @Test
    void usesExpectedSender() throws Exception {
        service.send(new MimeMailRequest(
                "Thông báo tài khoản",
                "security@example.com",
                java.util.List.of("owner@example.net"),
                java.util.List.of(),
                java.util.List.of(),
                "Có một thay đổi liên quan tài khoản."
        ));

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender).send(captor.capture());

        MimeMessage actual = captor.getValue();
        assertEquals(
                "Thông báo tài khoản",
                actual.getSubject()
        );
    }
}
~~~

Ví dụ cần static import **assertEquals** từ JUnit Jupiter. **MockitoExtension** khởi tạo mock và quản lý lifecycle của Mockito trong test class. Nó không mở Spring context hay kết nối SMTP.

Nếu trong mỗi test service tạo nhiều message hoặc gửi theo logic khác nhau, có thể chọn setUp phù hợp. Tránh stub những lời gọi không được sử dụng ở test cụ thể nếu đang dùng strict stubbing; nên để test rõ hành vi thay vì thêm lenient stubs khắp nơi.

## 34. Tách trách nhiệm giữa resolver và mail transport

Một thiết kế dễ kiểm thử thường gồm:

~~~text
OrderEvent
   |
   v
MailRecipientResolver
   -> trả To, Cc, Bcc theo nghiệp vụ
   |
   v
MailSubjectRenderer
   -> trả Subject theo locale/event
   |
   v
MailMessageFactory
   -> tạo SimpleMailMessage / MimeMessage
   |
   v
JavaMailSender
~~~

Với cách chia này có thể kiểm thử theo lớp:

| Đối tượng test | Nội dung chính |
|---|---|
| **RecipientResolverTest** | Ai được vào To, Cc, Bcc cho một event? |
| **SubjectRendererTest** | Subject theo event, locale và dữ liệu nghiệp vụ |
| **MessageFactoryTest** | Mapping Subject/From/To/Cc/Bcc vào object mail |
| **NotificationServiceTest** | Gọi factory, sender đúng số lần và đúng loại thư |
| **SMTP integration test** | Transport xử lý envelope, Bcc, MIME, submission như thế nào? |

Không nhất thiết tách thành năm class cho một ứng dụng rất nhỏ. Nhưng nếu lượng rule tăng, việc gom cả chọn recipient, render nội dung, MIME và retry trong một service sẽ khiến unit test vừa dài vừa khó xác định lỗi.

## 35. Ví dụ bảng kịch bản test theo loại email

Giả sử hệ thống có các loại notification:

| Email | Subject kỳ vọng | From kỳ vọng | To | Cc | Bcc |
|---|---|---|---|---|---|
| Xác nhận đặt hàng | Đơn ORD-101 đã được tạo | orders@example.com | buyer@example.net | Không có | audit@example.com |
| Xác nhận thanh toán | Đã nhận thanh toán ORD-101 | billing@example.com | buyer@example.net | Không có | finance-audit@example.com |
| Cảnh báo bảo mật | Thông báo bảo mật tài khoản | security@example.com | owner@example.net | Không có | Không có |
| Yêu cầu hỗ trợ | Yêu cầu hỗ trợ T-202 | support@example.com | agent@example.com | supervisor@example.com | Không có |

Một tập test tối thiểu có thể lấy những kịch bản này làm fixture. Từng test xác nhận:

1. Subject thuộc đúng loại email.
2. From đúng account hoặc domain được phép.
3. To đúng đối tượng sở hữu notification.
4. Cc chỉ có khi quy tắc yêu cầu.
5. Bcc không lẫn vào To/Cc.

Các giá trị trên chỉ là ví dụ; không phải chính sách bắt buộc của Spring Framework Mail.

### Vì sao nên dùng địa chỉ khác nhau?

Nếu cả To, Cc và Bcc đều dùng **test@example.com**, một đoạn code gán nhầm list có thể vẫn vượt qua một số assertion kém chặt chẽ. Fixture nên dùng địa chỉ khác nhau và khác vai trò để test phát hiện mapping sai.

## 36. Các lỗi kiểm thử thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ dùng verify(sender).send(any()) | Không biết Subject/From/To/Cc/Bcc có đúng không | Dùng ArgumentCaptor và assertions |
| Mock cả MimeMessage | Setter/getter MIME không phản ánh đối tượng thật nếu không stub thủ công | Dùng MimeMessage thật trong bộ nhớ |
| Assert raw Subject encoded-word | Test phụ thuộc biểu diễn MIME | Dùng MimeMessage.getSubject() |
| So sánh raw To/Cc header | Dễ sai vì display name và header folding | Dùng getRecipients(...) |
| Không kiểm tra Bcc | Có thể gán nhầm recipient kín vào To/Cc | Assert riêng danh sách Bcc |
| Assert Bcc phải null trước send | Bỏ qua recipient kín được chuẩn bị hợp lệ | Đọc Bcc pre-send; test secrecy ở transport |
| Dùng getAllRecipients() để kiểm tra từng vai trò | Không phát hiện To/Cc/Bcc bị tráo | Assert theo RecipientType |
| Chỉ so sánh Set recipients | Không phát hiện duplicate | Kiểm tra số lượng nếu cần |
| Luôn yêu cầu Cc/Bcc không null | Test phụ thuộc biểu diễn khi unset | Chuẩn hóa null thành danh sách rỗng nếu phù hợp |
| Dùng chung fixture email cho mọi tenant | Không phát hiện rò rỉ recipient giữa tenant | Dùng địa chỉ riêng rõ vai trò |
| Khởi động SMTP thật trong unit test | Chậm, khó lặp và gây side effect | Mock JavaMailSender |
| Dùng @SpringBootTest cho service đơn giản | Tăng thời gian và phụ thuộc môi trường | Constructor injection với JUnit/Mockito |
| Không kiểm tra From | Có thể gửi sai thương hiệu hoặc identity | Assert From và chính sách chọn sender |
| Kiểm tra số recipient nhưng không kiểm tra địa chỉ | Không phát hiện gửi nhầm người | So sánh địa chỉ cụ thể |
| Cho rằng send không ném exception nghĩa là delivered | Nhầm submission với chuyển phát | Integration/provider event cho delivery |
| Dùng test pre-send để khẳng định Bcc không lộ trong SMTP DATA | Kiểm tra sai tầng | SMTP test server kiểm tra envelope và DATA |

## 37. Cách xử lý khi một test header thất bại

Các triệu chứng thường gặp:

### Subject thực tế null

Kiểm tra service có gọi **setSubject(...)** hay không, và renderer có trả null không. Nếu test đang đọc raw MIME header, chuyển sang API **getSubject()** cho mục tiêu ngữ nghĩa.

### From khác dự kiến

Kiểm tra cấu hình sender, mapping From theo tenant hoặc liệu request có được phép override From không. Đối với MimeMessage có display name, đọc **InternetAddress.getAddress()** và **getPersonal()** riêng.

### To và Cc bị tráo

Kiểm tra đoạn mapping **request.to()** với **helper.setTo(...)** và **request.cc()** với **helper.setCc(...)**. Dùng fixture có địa chỉ khác nhau rõ ràng.

### Bcc vắng mặt trong MimeMessage trước khi gửi

Kiểm tra service có gọi **helper.setBcc(...)** với danh sách không rỗng không. Nếu Bcc là optional, xem policy đã thực sự chọn recipient kín chưa. Không nhầm kiểm tra pre-send với kiểm tra header được gửi qua SMTP.

### Mock sender không ghi nhận lời gọi

Kiểm tra service có gọi **send(SimpleMailMessage)**, **send(MimeMessage)** hay overload mảng. ArgumentCaptor cần có đúng kiểu tương ứng. Nếu dùng nhiều sender bean, kiểm tra mock nào thực tế được inject.

### Test Unicode thất bại

Kiểm tra charset được dùng khi tạo MimeMessageHelper. Tránh so sánh raw encoded-word nếu mục tiêu là Subject người dùng nhìn thấy. Bảo đảm test source được lưu UTF-8.

### Test dùng list rỗng nhưng nhận null

Kiểm tra service có bỏ qua setter Cc/Bcc khi danh sách rỗng hay không. Nếu đó là hành vi chủ ý, nên kiểm tra “không có recipient” thay vì bắt buộc field phải là mảng rỗng.

## 38. Quy trình kiểm thử đề xuất

Khi viết unit test cho một email mới, có thể đi theo trình tự:

1. Xác định **event nghiệp vụ** tạo email.
2. Xác định **Subject kỳ vọng** theo event và locale.
3. Xác định **From được cấp quyền**.
4. Xác định chính xác danh sách **To**, **Cc**, **Bcc**.
5. Chuẩn bị fixture có địa chỉ riêng biệt, không trùng vai trò ngoài ý muốn.
6. Mock **JavaMailSender**; nếu dùng MIME, trả **MimeMessage thật trong bộ nhớ**.
7. Gọi service đang được kiểm thử.
8. Dùng **ArgumentCaptor** lấy message chuyển cho sender.
9. Assert Subject, From, từng RecipientType và số lần gửi.
10. Bổ sung ca không có Cc/Bcc, nhiều recipient và input sai khi chính sách yêu cầu.
11. Dành test transport riêng cho **Bcc privacy, SMTP envelope, MIME serialization và delivery**.

Đây là quy trình áp dụng để tác giả phần mềm thiết kế test, không phải sự thay thế cho xác minh SMTP thực tế.

## 39. Ghi nhớ

Để kiểm thử **Subject, From, To, Cc và Bcc** trong Spring Framework Mail, trước tiên chọn đúng đối tượng:

- Với **SimpleMailMessage**, dùng **Mockito ArgumentCaptor<SimpleMailMessage>**, sau đó đọc **getSubject(), getFrom(), getTo(), getCc(), getBcc()**.
- Với **MimeMessage**, mock **JavaMailSender.createMimeMessage()** để trả một **MimeMessage thật trong bộ nhớ**, rồi capture lời gọi send. Đọc **getSubject(), getFrom()** và **getRecipients(Message.RecipientType.TO/CC/BCC)**.
- Với **From có tên hiển thị**, kiểm tra riêng **InternetAddress.getAddress()** và **getPersonal()**.
- Với **Subject Unicode**, so sánh nội dung đã decode thay vì raw MIME header.
- Với **Cc/Bcc rỗng**, kiểm tra đúng quy tắc nghiệp vụ; không mặc định null và empty array luôn có ý nghĩa khác nhau.

Đặc biệt, **Bcc cần được kiểm tra ở hai tầng**: unit test xác nhận địa chỉ Bcc được chuẩn bị đúng và không bị đưa vào To/Cc; integration test xác nhận transport không công khai Bcc trong nội dung/header tới người nhận ngoài phạm vi. Không dùng unit test trên MimeMessage trước khi gửi để tuyên bố đã xác minh tính kín đáo trên đường truyền.

**Một bài kiểm thử email tốt phải chỉ ra chính xác ai được nhận, ai được nhìn thấy nhau và người nhận sẽ thấy tiêu đề/người gửi nào.** Mockito giúp xác nhận những quyết định đó một cách nhanh, độc lập với SMTP; kiểm thử integration bổ sung bằng chứng về cách mail transport thực sự chuyển tiếp thông điệp.




