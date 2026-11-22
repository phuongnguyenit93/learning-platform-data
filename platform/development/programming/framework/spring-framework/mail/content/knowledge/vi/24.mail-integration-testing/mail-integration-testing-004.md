# Xác minh MIME tree trên server kiểm thử

## 1. Vì sao cần kiểm thử cấu trúc MIME thực tế?

Trong **Spring Framework Mail**, nhiều ứng dụng dùng **JavaMailSender**, **MimeMessage** và **MimeMessageHelper** để gửi thư HTML, bản thay thế plain text, hình ảnh inline và file đính kèm. Một email có thể được tạo không báo lỗi, phương thức **send(...)** được gọi, thậm chí SMTP server trả thành công, nhưng cấu trúc **MIME (Multipurpose Internet Mail Extensions)** vẫn có thể không như mong muốn.

Ví dụ:

- Email có cả plain text và HTML, nhưng hai phần không nằm trong **multipart/alternative**.
- Hình logo được thêm bằng **addAttachment(...)** thay vì **addInline(...)**, khiến email client hiển thị như file đính kèm.
- HTML dùng **src="cid:brand-logo"** nhưng phần hình không có **Content-ID** tương ứng.
- Một file đính kèm được gắn vào nhánh **multipart/related** dành cho nội dung email thay vì ở nhánh attachment thích hợp.
- Subject và body tiếng Việt bị sai charset hoặc bị so sánh như chuỗi MIME đã mã hóa.
- Danh sách Bcc bị đưa nhầm vào To/Cc hoặc xuất hiện trong MIME DATA gửi tới người nhận.

**Unit test với Mockito** có thể chứng minh service gọi đúng phương thức của **MimeMessageHelper** hoặc tạo được một **MimeMessage** trong bộ nhớ. Nhưng nó không chứng minh đầy đủ rằng tầng transport đã gửi đi cây MIME mong muốn. Với những yêu cầu đó, cần **kiểm thử tích hợp qua SMTP server kiểm thử**, sau đó đọc lại thông điệp mà server thực sự nhận.

Mục tiêu của bài là xây dựng cách kiểm thử xác minh **cấu trúc MIME tree**, **quan hệ cha-con giữa các multipart**, **Content-Type**, **Content-Disposition**, **Content-ID**, nội dung đã giải mã và các trường hợp bảo mật/khả năng tương thích.

## 2. MIME tree là gì?

Email hiện đại không nhất thiết là một khối text. MIME cho phép tổ chức thông điệp thành một **cây các phần (parts)**:

~~~text
MimeMessage
    |
    +-- BodyPart 1
    |     |
    |     +-- BodyPart 1.1
    |     +-- BodyPart 1.2
    |
    +-- BodyPart 2
          |
          +-- ...
~~~

Một **leaf part** có thể chứa plain text, HTML, hình ảnh, PDF hoặc dữ liệu nhị phân. Một **container part** có Content-Type **multipart/**... và chứa nhiều body part con.

Những subtype phổ biến:

| MIME type | Ý nghĩa chính |
|---|---|
| **text/plain** | Nội dung văn bản đơn giản |
| **text/html** | Nội dung HTML của email |
| **multipart/alternative** | Các phiên bản thay thế của cùng một nội dung, thường plain text và HTML |
| **multipart/related** | Một nội dung chính cùng những tài nguyên phụ thuộc như hình được tham chiếu bằng CID |
| **multipart/mixed** | Tập hợp nhiều phần độc lập, thường dùng khi có file đính kèm |
| **image/png** | Hình PNG; có thể dùng inline hoặc attachment tùy metadata/cấu trúc |
| **application/pdf** | Nội dung PDF, thường là attachment |

**Content-Type** biểu thị loại phần. **Content-Disposition** thể hiện cách trình bày như inline hay attachment. **Content-ID** cho phép các phần khác, ví dụ HTML, tham chiếu tới tài nguyên MIME liên quan.

Một cây MIME hợp lệ không chỉ cần “có đủ các file”, mà còn cần **các phần được đặt đúng quan hệ với nhau**.

## 3. Ví dụ MIME tree thường dùng cho email HTML có logo và PDF

Giả sử cần gửi một email gồm:

- Bản plain text dành cho client không hỗ trợ HTML.
- Bản HTML có tham chiếu tới logo bằng CID.
- Hình PNG được nhúng inline.
- File PDF đính kèm.

Một cấu trúc điển hình là:

~~~text
MimeMessage
Content-Type: multipart/mixed
|
+-- Part A: multipart/related
|   |
|   +-- Part A.1: multipart/alternative
|   |   |
|   |   +-- Part A.1.1: text/plain; charset=UTF-8
|   |   |
|   |   +-- Part A.1.2: text/html; charset=UTF-8
|   |                     |
|   |                     +-- HTML: src="cid:brand-logo"
|   |
|   +-- Part A.2: image/png
|                   Content-ID: <brand-logo>
|                   Content-Disposition: inline
|
+-- Part B: application/pdf
            Content-Disposition: attachment
            filename="guide.pdf"
~~~

Cấu trúc trên minh họa cách tổ chức thường gặp khi dùng **MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED** trong Spring.

Ý nghĩa:

1. **multipart/mixed** ở ngoài cùng gom nội dung email và attachment.
2. **multipart/related** gom nội dung HTML với tài nguyên phục vụ hiển thị nội dung đó.
3. **multipart/alternative** gom bản plain text và HTML như các cách trình bày thay thế.
4. **image/png** có Content-ID tương ứng với URL **cid:** trong HTML.
5. **application/pdf** nằm ở nhánh attachment thay vì lẫn vào nhánh HTML.

Trong thực tế, cách sắp xếp có thể khác nhau theo **multipart mode**, phiên bản thư viện, các phần được thêm và cách MIME được chuẩn hóa. Vì vậy, **test nên xác minh ý nghĩa cấu trúc cần thiết**, không chỉ khẳng định mù quáng rằng mọi part luôn nằm ở chỉ số 0, 1 hoặc 2.

## 4. Vì sao phải đọc email từ SMTP server kiểm thử?

Một unit test thường đi theo luồng:

~~~text
MailService
   |
   v
Mock JavaMailSender
   |
   v
ArgumentCaptor<MimeMessage>
   |
   v
Assert trên object trước khi gửi
~~~

Cách này hữu ích để kiểm tra logic tạo thư, nhưng không thực hiện SMTP transport, nên có thể bỏ sót:

- Việc **MimeMessage.saveChanges()** và chuẩn bị header lúc gửi.
- Cách **Content-Transfer-Encoding** được chọn và giải mã.
- Thay đổi header do Jakarta Mail SMTP transport.
- Cách MIME DATA được đưa qua giao thức SMTP.
- Một số khác biệt giữa message trước gửi và message thực tế server nhận.

Kiểm thử tích hợp:

~~~text
JUnit test
    |
    v
Spring Mail service thực
    |
    v
JavaMailSenderImpl thực
    |
    | SMTP over localhost
    v
SMTP test server
    |
    | Capture MIME DATA
    v
MimeMessage đã nhận
    |
    v
MIME tree walker + assertions
~~~

Trong quy trình này, **không gửi thư ra Internet**. Server kiểm thử có thể chạy trong cùng JVM hoặc trong container thử nghiệm, giữ nội dung email để test đọc và phân tích.

Lợi ích là xác minh phần lớn chuỗi **application → Spring Mail → Jakarta Mail → SMTP → server nhận**, thay vì chỉ kiểm tra đối tượng trước transport.

## 5. Chọn SMTP server kiểm thử

Một số lựa chọn thường được dùng:

| Cách | Điểm mạnh | Điểm cần lưu ý |
|---|---|---|
| **GreenMail** | SMTP server nhúng, có thể khởi động/dừng trong JUnit và đọc MimeMessage đã nhận | Cần chọn phiên bản tương thích Jakarta Mail của ứng dụng |
| **Mailpit hoặc MailHog** | SMTP capture server và giao diện/API xem thư | Thường cần process/container và client API để lấy thư |
| **SubEthaSMTP/Wiser** | SMTP test server nhúng, có thể lấy thông điệp đã nhận | Cần xác minh phiên bản và API tương thích |
| **ESP sandbox** | Có thể kiểm tra hành vi nhà cung cấp thực tế | Phụ thuộc tài khoản, quota, mạng và chính sách provider |

Trong các ví dụ dưới đây, dùng **GreenMail** để kiểm thử ngay trong JVM với JUnit. Đây là lựa chọn minh họa; nguyên tắc duyệt **MimeMessage/Multipart/BodyPart** áp dụng cả khi thư được lấy từ Mailpit hoặc một SMTP sandbox khác.

### Tiêu chí chọn công cụ

Một server phù hợp để xác minh MIME tree cần:

- Nhận được SMTP submission từ ứng dụng kiểm thử.
- Cho phép đọc lại **nội dung message sau khi server nhận**, không chỉ bản object được truyền vào mock.
- Giữ được metadata **Content-Type**, MIME boundary, Content-ID và các phần đính kèm.
- Nếu muốn kiểm tra Bcc/envelope, có khả năng quan sát **SMTP RCPT TO** độc lập với MIME headers.
- Khởi động và dọn dẹp cô lập giữa các test.
- Không cần credential sản xuất hoặc kết nối tới người dùng thật.

## 6. Dependency và tương thích Jakarta Mail

Ví dụ với Spring Boot hiện đại:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.icegreen:greenmail:2.1.0'
}
~~~

Đây là một ví dụ phiên bản GreenMail thuộc nhánh **2.x** dành cho môi trường Jakarta Mail. Khi áp dụng vào dự án thật, hãy chọn phiên bản phù hợp với **Spring Boot, Spring Framework, Jakarta Mail và JDK** mà dự án đang sử dụng.

**Cảnh báo về namespace:** Spring Framework 6/Spring Boot 3 sử dụng **jakarta.mail.***; các thư viện test đời cũ có thể vẫn dùng **javax.mail.***. Trộn hai namespace có thể dẫn đến lỗi compile hoặc type mismatch dù tên class trông giống nhau.

Nếu dự án dùng Spring/Jakarta Mail đời khác, điều chỉnh dependency tương ứng. Các ví dụ dưới đây dùng **jakarta.mail**.

## 7. Tổ chức một integration test đáng tin cậy

Thay vì phụ thuộc vào SMTP server được cài ngoài máy, có thể bắt đầu/dừng server trong lifecycle của JUnit:

~~~text
@BeforeEach
    |
    +-- Tạo GreenMail server trên localhost
    +-- Khởi động SMTP listener
    +-- Tạo mailbox recipient thử nghiệm
    +-- Tạo JavaMailSenderImpl trỏ tới server đó

@Test
    |
    +-- Gọi service tạo/gửi email
    +-- Chờ SMTP server nhận thông điệp
    +-- Đọc lại MimeMessage từ GreenMail
    +-- Duyệt MIME tree
    +-- Assert cấu trúc và nội dung

@AfterEach
    |
    +-- Dừng SMTP server
~~~

Ví dụ dưới đây dùng **ServerSetupTest.SMTP** — một cấu hình test định sẵn của GreenMail. Với kiểu setup này, cổng có thể là cổng cố định của thư viện, vì vậy nếu CI chạy nhiều test song song có thể cần cấu hình **port động** hoặc cấp cổng riêng cho từng test instance. Không sử dụng SMTP test server đã cố định port một cách thiếu kiểm soát khi nhiều suite dùng chung môi trường.

## 8. Chuẩn bị fixture có thể kiểm tra

Ví dụ sẽ tạo:

| Thành phần | Giá trị test |
|---|---|
| To | customer@localhost |
| From | notices@example.com |
| Subject | Hóa đơn ORD-123 — đã thanh toán |
| Plain text | Hóa đơn ORD-123 đã được thanh toán. |
| HTML | Một đoạn HTML chứa src="cid:brand-logo" |
| Inline image | File PNG test tại mail/logo.png |
| Attachment | File PDF test tại mail/guide.pdf |

Đặt các fixture nhỏ trong thư mục test resources:

~~~text
src/test/resources/
└── mail/
    ├── logo.png
    └── guide.pdf
~~~

Nên dùng file thử nghiệm nhỏ, hợp lệ và không có thông tin khách hàng. Với bài test xác minh cấu trúc MIME, **không cần attachment lớn** hoặc tài liệu production.

### Vì sao dùng fixture binary thật?

Nếu tạo một mảng byte tùy ý rồi gán Content-Type **image/png**, bạn có thể kiểm tra MIME wrapper nhưng không xác nhận nội dung đó là một ảnh PNG có thể hiển thị. Fixture PNG/PDF thật giúp test có tín hiệu tốt hơn khi cần kiểm tra content type, decoded bytes hoặc cách email client xử lý.

Tuy nhiên, không nên biến bài integration test MIME tree thành bài kiểm tra render ảnh/PDF chi tiết. Việc giải mã và hiển thị ở client là tầng khác.

## 9. Tạo MimeMessage có plain text, HTML, hình inline và attachment

Một phương thức gửi dùng các API Spring Mail:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class InvoiceMailService {

    private final JavaMailSender sender;

    public InvoiceMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice() throws MessagingException {
        MimeMessage message = sender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notices@example.com");
        helper.setTo("customer@localhost");
        helper.setSubject("Hóa đơn ORD-123 — đã thanh toán");

        String plainText =
                "Hóa đơn ORD-123 đã được thanh toán.";

        String htmlText = """
                <html lang="vi">
                  <body>
                    <h1>Hóa đơn ORD-123</h1>
                    <p>Đơn hàng đã được thanh toán.</p>
                    <img src="cid:brand-logo" alt="Logo cửa hàng">
                  </body>
                </html>
                """;

        // Đặt text/HTML trước khi thêm tài nguyên inline.
        helper.setText(plainText, htmlText);

        helper.addInline(
                "brand-logo",
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        helper.addAttachment(
                "guide.pdf",
                new ClassPathResource("mail/guide.pdf"),
                "application/pdf"
        );

        sender.send(message);
    }
}
~~~

Các điểm cần chú ý:

1. **MULTIPART_MODE_MIXED_RELATED** chủ động tạo cấu trúc thích hợp khi có cả attachment và tài nguyên inline.
2. **setText(plainText, htmlText)** tạo hai phiên bản nội dung thay thế. Người nhận không cần nhìn thấy cả hai bản cùng lúc.
3. **addInline("brand-logo", ...)** đặt tài nguyên có Content-ID để HTML dùng **cid:brand-logo** tham chiếu.
4. **addAttachment(...)** thêm file độc lập, không dùng nó thay thế addInline cho logo.
5. **ClassPathResource** có thể cung cấp InputStream mới khi MIME content được đọc lại; tránh dùng một stream chỉ mở được một lần cho tài nguyên có thể phải được đọc nhiều lần.
6. **sender.send(message)** đi qua Jakarta Mail transport thực, thay vì chỉ được ghi nhận bởi Mockito.

**Thứ tự gọi:** Khi dùng MimeMessageHelper với inline resource, nên gọi **setText(...) trước addInline(...)** theo hướng dẫn của Spring. Điều này giúp helper xây dựng quan hệ MIME đúng và tránh các trường hợp phần nội dung/tài nguyên bị sắp xếp không phù hợp.

## 10. Khởi động GreenMail và nối JavaMailSenderImpl

Ví dụ một JUnit 5 integration test tự quản lý SMTP test server:

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

import static org.junit.jupiter.api.Assertions.*;

class InvoiceMimeTreeIT {

    private GreenMail greenMail;
    private InvoiceMailService service;

    @BeforeEach
    void setUp() {
        greenMail = new GreenMail(ServerSetupTest.SMTP);
        greenMail.start();

        greenMail.setUser(
                "customer@localhost",
                "customer",
                "test-only-password"
        );

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(ServerSetupTest.SMTP.getPort());
        sender.setDefaultEncoding("UTF-8");

        service = new InvoiceMailService(sender);
    }

    @AfterEach
    void tearDown() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void receivesInvoiceAsMimeMessage() throws Exception {
        service.sendInvoice();

        assertTrue(
                greenMail.waitForIncomingEmail(5000, 1),
                "SMTP test server không nhận được email"
        );

        MimeMessage[] received = greenMail.getReceivedMessages();
        assertEquals(1, received.length);

        MimeMessage actual = received[0];

        assertEquals(
                "Hóa đơn ORD-123 — đã thanh toán",
                actual.getSubject()
        );
        assertTrue(
                actual.isMimeType("multipart/mixed"),
                "Email phải có nhánh multipart/mixed"
        );
    }
}
~~~

Đây là ví dụ một phép kiểm tra đầu tiên. Các phần tiếp theo sẽ mở rộng từ **actual** để duyệt và xác minh toàn bộ MIME tree.

### Vì sao không dùng mock trong test này?

Trong ví dụ trên, **JavaMailSenderImpl** mở kết nối SMTP thật tới **GreenMail** trên localhost. Test không chỉ kiểm tra gọi phương thức send; nó đòi hỏi server nhận được dữ liệu trước khi phân tích message.

### Cẩn thận với cổng test cố định

**ServerSetupTest.SMTP** dùng một cấu hình port test của GreenMail. Nó tiện minh họa nhưng có thể gây xung đột nếu nhiều test hoặc worker CI chạy song song trên cùng host. Khi triển khai suite lớn:

- Dùng port động do OS cấp và lấy cổng thực tế mà server đang lắng nghe theo API của phiên bản GreenMail đang dùng; hoặc
- Cấp port riêng cho từng test instance/container; hoặc
- Dùng JUnit extension/Testcontainers có hỗ trợ quản lý lifecycle và port mapping.

Không tự gắn port bằng một số ngẫu nhiên rồi cho rằng nó chắc chắn đang rảnh.

### Lưu ý về tài khoản test

GreenMail có thể quản lý mailbox và người dùng nội bộ. Địa chỉ **customer@localhost** và mật khẩu trong ví dụ chỉ thuộc server test, không phải tài khoản dùng gửi email thật. Các test SMTP không nên dùng credentials của nhà cung cấp production.

## 11. Kiểm tra SMTP đã nhận thư trước khi duyệt MIME

Đừng bắt đầu bằng cách kiểm tra **multipart** trước khi xác nhận server đã nhận message. Nếu lỗi DNS, TCP hoặc cấu hình test khiến thư không tới server, những assertion phía sau sẽ gây nhiễu.

Trình tự tốt:

~~~text
service.sendInvoice()
       |
       v
GreenMail.waitForIncomingEmail(...)
       |
       +-- False -> lỗi transport / setup / timeout / mailbox
       |
       v
getReceivedMessages()
       |
       +-- Count sai -> thư thiếu, lặp hoặc mailbox bị dùng chung
       |
       v
getSubject(), getFrom(), getRecipients()
       |
       v
Parse MIME tree
~~~

Nếu test timeout, cần biết:

- **send(...)** có ném MailException không?
- Server đã start trước khi sender gọi chưa?
- Host/port sender có đúng listener test không?
- Recipient có được test server chấp nhận không?
- Có test khác dùng cùng server hoặc cùng port không?
- Test có giả định số message nhận sai khi gửi tới nhiều mailbox không?

**Đừng sửa assertion MIME để che giấu lỗi SMTP setup.** Hai nhóm lỗi nằm ở những tầng khác nhau.

## 12. Đọc Content-Type của MimeMessage đúng cách

Jakarta Mail cho phép:

~~~java
String rawContentType = actual.getContentType();

boolean isMixed =
        actual.isMimeType("multipart/mixed");
~~~

Một Content-Type thực tế có thể trông như:

~~~text
multipart/mixed;
  boundary="----=_Part_17_123456789.1762920000000"
~~~

Chuỗi **boundary** được sinh để phân tách MIME part và thường thay đổi giữa các lần tạo message.

Không nên viết test:

~~~java
assertEquals(
        "multipart/mixed",
        actual.getContentType()
);
~~~

Test trên có thể thất bại vì Content-Type còn chứa tham số **boundary** hoặc charset. Để kiểm tra MIME type, dùng:

~~~java
assertTrue(actual.isMimeType("multipart/mixed"));
~~~

Nếu cần kiểm tra tham số cụ thể, dùng parser kiểu **jakarta.mail.internet.ContentType** hoặc API tương ứng; không tách Content-Type bằng dấu chấm phẩy theo cách thủ công khi giá trị có thể chứa dấu quote.

### MIME type không phân biệt chữ hoa/chữ thường

MIME type và subtype được so sánh không phân biệt chữ hoa/chữ thường về mặt cú pháp. **Part.isMimeType(...)** phù hợp hơn so sánh String với một dạng viết cụ thể.

## 13. Duyệt MIME tree bằng Jakarta Mail

Các API cốt lõi:

- **jakarta.mail.Part**: interface biểu diễn một phần MIME, có Content-Type, disposition, file name, header...
- **jakarta.mail.Multipart**: container chứa nhiều BodyPart.
- **jakarta.mail.BodyPart**: một thành phần con trong Multipart.
- **jakarta.mail.internet.MimeMessage**: message gốc, cũng là một Part.

Một phương thức duyệt đệ quy:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimeTree {

    private MimeTree() {}

    public static List<Part> flatten(Part root)
            throws Exception {
        List<Part> all = new ArrayList<>();
        visit(root, all, 0);
        return List.copyOf(all);
    }

    private static void visit(
            Part part,
            List<Part> all,
            int depth
    ) throws Exception {
        if (depth > 32) {
            throw new IllegalStateException(
                    "Cây MIME vượt giới hạn độ sâu test"
            );
        }

        all.add(part);

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (!(content instanceof Multipart multipart)) {
                throw new IllegalStateException(
                        "Multipart part không trả Multipart"
                );
            }

            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                visit(child, all, depth + 1);
            }
        }
    }
}
~~~

Đây là **helper cho test**, không phải một parser MIME tổng quát có khả năng chống mọi nội dung độc hại. Với MIME từ bên ngoài, cần giới hạn thêm tổng số part, kích thước và tài nguyên đọc. Trong integration test do chính ứng dụng tạo, giới hạn độ sâu và fixture nhỏ giúp tránh việc test đi vào vòng xử lý quá lớn.

### Vì sao chỉ recurse khi part là multipart?

Một leaf như **image/png** hoặc **application/pdf** không có BodyPart con theo cùng cơ chế. Với **message/rfc822** lồng email khác, ứng dụng có thể cần một nhánh parse bổ sung. Bài test ở đây tập trung vào cây MIME của email gửi bằng MimeMessageHelper và không giả định mọi dạng MIME đều là multipart hoặc text.

## 14. In cấu trúc MIME để chẩn đoán

Trong test, có thể tạo một bản mô tả cấu trúc **không chứa body hoặc dữ liệu nhạy cảm**:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public static void printStructure(Part part, int depth)
        throws Exception {
    String indent = "  ".repeat(depth);

    System.out.println(
            indent
            + part.getContentType()
            + " | disposition=" + part.getDisposition()
            + " | filename=" + part.getFileName()
    );

    if (part.isMimeType("multipart/*")) {
        Multipart children = (Multipart) part.getContent();

        for (int i = 0; i < children.getCount(); i++) {
            printStructure(children.getBodyPart(i), depth + 1);
        }
    }
}
~~~

Hàm này chỉ nên dùng cho **fixture thử nghiệm**. Với email thật, filename, Content-ID hoặc metadata vẫn có thể mang dữ liệu cá nhân, nên cần lọc/mask trước khi log production.

Không dump toàn bộ **MimeMessage.writeTo(System.out)** trong log thông thường; body, attachment, token và địa chỉ thật có thể bị tiết lộ.

## 15. Biểu diễn cây để kiểm tra quan hệ cha-con

**MimeTree.flatten(...)** đủ để biết một MIME type có mặt hay không. Tuy nhiên, nó không phân biệt được:

~~~text
Đúng:
  multipart/mixed
    -> multipart/related
        -> multipart/alternative

Sai mục tiêu:
  multipart/mixed
    -> multipart/alternative
    -> multipart/related
~~~

Hai cây trên có thể cùng chứa những subtype **mixed**, **related** và **alternative**, nhưng quan hệ không giống nhau. Một bài test integration nên có thể kiểm tra **alternative là descendant của related** và **attachment ở ngoài nhóm related**.

Có thể xây một mô hình Node cho test:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class MimeNodes {

    private MimeNodes() {}

    public record Node(Part part, List<Node> children) {

        public boolean isType(String mimeType)
                throws MessagingException {
            return part.isMimeType(mimeType);
        }

        public List<Node> all() {
            List<Node> nodes = new ArrayList<>();
            nodes.add(this);
            for (Node child : children) {
                nodes.addAll(child.all());
            }
            return List.copyOf(nodes);
        }

        public Optional<Node> first(String mimeType)
                throws MessagingException {
            for (Node node : all()) {
                if (node.isType(mimeType)) {
                    return Optional.of(node);
                }
            }
            return Optional.empty();
        }

        public List<Node> directChildren(String mimeType)
                throws MessagingException {
            List<Node> result = new ArrayList<>();
            for (Node child : children) {
                if (child.isType(mimeType)) {
                    result.add(child);
                }
            }
            return List.copyOf(result);
        }
    }

    public static Node read(Part part) throws Exception {
        return read(part, 0);
    }

    private static Node read(Part part, int depth)
            throws Exception {
        if (depth > 32) {
            throw new IllegalStateException(
                    "MIME tree depth exceeded"
            );
        }

        List<Node> children = new ArrayList<>();
        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();
            if (multipart.getCount() > 100) {
                throw new IllegalStateException(
                        "MIME multipart có quá nhiều part trong test"
                );
            }
            for (int i = 0; i < multipart.getCount(); i++) {
                children.add(
                        read(multipart.getBodyPart(i), depth + 1)
                );
            }
        }

        return new Node(part, List.copyOf(children));
    }
}
~~~

Các import **IOException** trong ví dụ không bắt buộc khi phương thức dùng **throws Exception**, nhưng có thể dùng nếu muốn khai báo checked exception cụ thể hơn. Mô hình trên cố ý chỉ hỗ trợ multipart lồng nhau và không parse message/rfc822 như một nhánh bổ sung.

Với dữ liệu email từ một nguồn không tin cậy, cần thêm giới hạn **tổng số node, dung lượng MIME và thời gian xử lý**, không chỉ kiểm tra số part của từng multipart.

## 16. Assert cấu trúc mixed → related → alternative

Sau khi GreenMail đã nhận message:

~~~java
MimeNodes.Node root = MimeNodes.read(actual);

assertTrue(root.isType("multipart/mixed"));

MimeNodes.Node related = root
        .first("multipart/related")
        .orElseThrow(() -> new AssertionError(
                "Không có multipart/related"
        ));

MimeNodes.Node alternative = related
        .first("multipart/alternative")
        .orElseThrow(() -> new AssertionError(
                "Alternative không nằm trong nhánh related"
        ));

assertTrue(
        alternative.first("text/plain").isPresent(),
        "Thiếu plain text trong alternative"
);
assertTrue(
        alternative.first("text/html").isPresent(),
        "Thiếu HTML trong alternative"
);
~~~

Các assertion này xác nhận:

1. Root có MIME type **multipart/mixed**.
2. Trong tree có một nhánh **multipart/related**.
3. Bên trong related có **multipart/alternative**.
4. Bản plain text và HTML đều nằm dưới alternative.

Nếu yêu cầu phải đúng **quan hệ trực tiếp**, có thể dùng:

~~~java
assertEquals(
        1,
        root.directChildren("multipart/related").size()
);

assertEquals(
        1,
        related.directChildren("multipart/alternative").size()
);
~~~

Quan hệ trực tiếp phù hợp khi hợp đồng MIME của ứng dụng quy định đúng cây do **MULTIPART_MODE_MIXED_RELATED** tạo. Nếu chấp nhận thêm một lớp container hợp lệ từ thư viện hoặc provider, có thể chỉ cần kiểm tra quan hệ descendant.

**Đừng chỉ kiểm tra số part**: một MIME root có hai part không chứng minh một part là related, phần còn lại là PDF. Cần kiểm tra loại và vị trí của chúng.

## 17. Kiểm tra plain text và HTML đúng nội dung

Từ node alternative, lấy các phần text:

~~~java
MimeNodes.Node plainNode = alternative
        .first("text/plain")
        .orElseThrow();

MimeNodes.Node htmlNode = alternative
        .first("text/html")
        .orElseThrow();

String plainText =
        (String) plainNode.part().getContent();

String htmlText =
        (String) htmlNode.part().getContent();

assertEquals(
        "Hóa đơn ORD-123 đã được thanh toán.",
        plainText
);

assertTrue(
        htmlText.contains("<h1>Hóa đơn ORD-123</h1>")
);
assertTrue(
        htmlText.contains("cid:brand-logo")
);
~~~

Đối với các text part do Jakarta Mail tạo và đọc, **getContent()** thường trả về String đã được decode theo charset. Cách so sánh này tốt hơn việc đọc raw MIME rồi tìm chuỗi HTML trong dữ liệu có thể được quoted-printable hoặc base64.

### Vì sao không assert toàn bộ HTML nếu không cần?

Nếu template tự động chèn khoảng trắng, xuống dòng hoặc thêm một vài attribute không quan trọng, so sánh toàn bộ HTML String có thể khiến test dễ vỡ.

Nên xác định contract:

- Nếu nội dung HTML là output cố định theo template, có thể so sánh toàn bộ.
- Nếu chỉ cần bảo đảm có đúng tham chiếu logo và thông báo, assert những phần quan trọng.
- Nếu cần kiểm tra cây HTML đúng semantics, dùng HTML parser phù hợp ở tầng render test; không nhất thiết gộp vào kiểm thử MIME tree.

### Có thể chỉ kiểm tra nội dung text mà bỏ qua MIME tree không?

Không nên nếu yêu cầu là hỗ trợ các client mail khác nhau. Hai text part tồn tại nhưng được đặt dưới **multipart/mixed** như hai attachment độc lập sẽ có ý nghĩa khác **multipart/alternative**. Test cần kiểm tra **nội dung lẫn quan hệ cấu trúc**.

## 18. Kiểm tra charset và Subject Unicode

Một email tiếng Việt có thể chứa:

~~~text
Subject: Hóa đơn ORD-123 — đã thanh toán
Body:    Đơn hàng đã được thanh toán.
~~~

Khi tạo bằng **MimeMessageHelper(..., "UTF-8")**, có thể assert:

~~~java
assertEquals(
        "Hóa đơn ORD-123 — đã thanh toán",
        actual.getSubject()
);

String plainContent =
        (String) plainNode.part().getContent();

assertTrue(
        plainContent.contains("đã được thanh toán")
);
~~~

**MimeMessage.getSubject()** trả về giá trị đã được giải mã. Không nên assert raw header Subject đúng bằng một chuỗi dạng **=?UTF-8?B?...?=**, vì encoded-word có thể thay đổi cách biểu diễn mà vẫn hợp lệ.

Nếu muốn kiểm tra tham số charset:

~~~java
import jakarta.mail.internet.ContentType;

ContentType contentType = new ContentType(
        plainNode.part().getContentType()
);

assertTrue(
        "UTF-8".equalsIgnoreCase(
                contentType.getParameter("charset")
        )
);
~~~

Nếu charset có thể thay đổi theo chính sách và nội dung vẫn giải mã đúng, tránh assert một charset cụ thể chỉ vì implementation mặc định. Nhưng khi ứng dụng **cam kết UTF-8**, kiểm tra tham số là hợp lý.

### Content-Transfer-Encoding

Các text part có thể được encode bằng:

- **quoted-printable**
- **base64**
- **7bit / 8bit** theo điều kiện và cấu hình

Đó là cách biểu diễn dữ liệu trên đường truyền, không phải nội dung người đọc thấy. Unit/integration test về ý nghĩa email nên dùng **getContent()** hoặc **getInputStream()** để đọc **dữ liệu đã decode**, thay vì so sánh chuỗi wire-format chứa các line break hoặc encoding cụ thể.

## 19. Kiểm tra hình inline và Content-ID

Ví dụ HTML:

~~~html
<img src="cid:brand-logo" alt="Logo cửa hàng">
~~~

Để hình hiển thị được qua CID, MIME tree phải chứa một part với:

- Content-Type thích hợp, ví dụ **image/png**.
- **Content-ID: <brand-logo>** hoặc một cách biểu diễn tương ứng được MIME parser hiểu.
- Quan hệ với nội dung HTML phù hợp, thường cùng nhóm **multipart/related**.
- Dữ liệu hình được đọc thành công.

Ví dụ tìm part:

~~~java
MimeNodes.Node logo = related
        .first("image/png")
        .orElseThrow(() -> new AssertionError(
                "Không có image/png trong related"
        ));

String[] cidHeaders =
        logo.part().getHeader("Content-ID");

assertNotNull(cidHeaders);
assertEquals(1, cidHeaders.length);
assertEquals(
        "<brand-logo>",
        cidHeaders[0].trim()
);
~~~

Ví dụ này giả định application dùng Content-ID đúng **brand-logo**. Nhiều MIME client và thư viện biểu diễn Content-ID trong header bằng dấu góc **<...>**, trong khi HTML tham chiếu bằng **cid:brand-logo** không có dấu góc.

Để test không phụ thuộc vào khoảng trắng hoặc cách trình bày, có thể tạo helper chuẩn hóa:

~~~java
public static String normalizeContentId(String header) {
    String cid = header.trim();
    if (cid.startsWith("<") && cid.endsWith(">")) {
        cid = cid.substring(1, cid.length() - 1);
    }
    return cid;
}
~~~

Sau đó:

~~~java
assertEquals(
        "brand-logo",
        normalizeContentId(cidHeaders[0])
);
~~~

**Không bỏ qua sự khác nhau thực sự giữa các Content-ID**: test phải bắt được trường hợp HTML tham chiếu **cid:brand-logo** nhưng part dùng **other-logo**.

### Kiểm tra disposition của hình

~~~java
String disposition = logo.part().getDisposition();

assertTrue(
        disposition == null
        || disposition.equalsIgnoreCase(Part.INLINE)
);
~~~

Trong MIME, một inline resource có thể được biểu diễn bằng **Content-Disposition: inline** hoặc không có disposition rõ ràng, tùy producer/transport. Khi mục tiêu là hình được tham chiếu qua CID, nên kiểm tra **Content-ID, MIME type và quan hệ related** thay vì bắt buộc phải có một chuỗi disposition duy nhất ở mọi implementation.

Tuy nhiên, nếu contract của ứng dụng **bắt buộc Content-Disposition: inline**, hãy thiết kế assertion chặt hơn và kiểm tra đúng cách helper/provider tạo message trong môi trường sử dụng.

## 20. Kiểm tra dữ liệu inline sau khi decode

Kiểm tra metadata chưa chứng minh dữ liệu hình thực sự được gửi. Có thể so sánh byte:

~~~java
import java.io.InputStream;
import java.util.Arrays;
import org.springframework.core.io.ClassPathResource;

byte[] expectedLogo;
try (InputStream input = new ClassPathResource(
        "mail/logo.png"
).getInputStream()) {
    expectedLogo = input.readAllBytes();
}

byte[] actualLogo;
try (InputStream input = logo.part().getInputStream()) {
    actualLogo = input.readAllBytes();
}

assertArrayEquals(expectedLogo, actualLogo);
~~~

**Part.getInputStream()** cung cấp nội dung part qua API JavaMail; trong trường hợp thông thường dữ liệu Content-Transfer-Encoding được xử lý bởi DataHandler. Vì vậy test so sánh decoded bytes thay vì chuỗi base64 chứa line wrapping có thể thay đổi.

Nên sử dụng fixture nhỏ. Nếu ảnh hoặc attachment lớn, đọc toàn bộ vào bộ nhớ chỉ để assert có thể không thích hợp; thay vào đó dùng digest và giới hạn kích thước.

## 21. Kiểm tra file đính kèm ở nhánh mixed

Một attachment độc lập thường có:

~~~text
Content-Type: application/pdf; name="guide.pdf"
Content-Disposition: attachment; filename="guide.pdf"
Content-Transfer-Encoding: base64
~~~

Trong cây ví dụ, PDF cần nằm **ngoài nhánh related chứa HTML/inline image**, và thuộc **multipart/mixed**.

Có thể tìm PDF ở descendant của root:

~~~java
MimeNodes.Node pdf = root
        .first("application/pdf")
        .orElseThrow(() -> new AssertionError(
                "Thiếu application/pdf attachment"
        ));

assertEquals(
        Part.ATTACHMENT,
        pdf.part().getDisposition()
);
assertEquals(
        "guide.pdf",
        pdf.part().getFileName()
);
~~~

Để kiểm tra vị trí khi cấu trúc được cam kết bởi **MIXED_RELATED**:

~~~java
assertFalse(
        related.first("application/pdf").isPresent(),
        "PDF attachment không nên nằm trong nhánh related"
);

assertTrue(
        root.directChildren("application/pdf").size() == 1,
        "PDF phải là một part trực tiếp dưới mixed"
);
~~~

Việc đính kèm đúng tên và disposition thường quan trọng với trải nghiệm người nhận. Nếu ứng dụng đổi tên attachment theo dữ liệu nghiệp vụ, test nên so sánh tên kỳ vọng của event; không chỉ khẳng định “có một PDF”.

### Kiểm tra decoded bytes của attachment

~~~java
byte[] expectedPdf;
try (InputStream input = new ClassPathResource(
        "mail/guide.pdf"
).getInputStream()) {
    expectedPdf = input.readAllBytes();
}

byte[] actualPdf;
try (InputStream input = pdf.part().getInputStream()) {
    actualPdf = input.readAllBytes();
}

assertArrayEquals(expectedPdf, actualPdf);
~~~

Kết quả này xác nhận dữ liệu đính kèm được bảo toàn qua MIME encoding và SMTP test transport ở phạm vi test. Nó không bảo đảm email client của mọi người nhận có thể mở file, nhưng giúp phát hiện lỗi nguồn dữ liệu, stream một lần hoặc attachment bị cắt.

## 22. Khẳng định không có part bị đặt sai nhánh

Một cây MIME có thể chứa đủ loại cần thiết mà vẫn đặt sai vị trí. Ví dụ HTML và logo bị tách khỏi nhau, hoặc PDF nằm bên trong nhóm related:

~~~text
Sai mục tiêu:

multipart/mixed
|
+-- text/html
+-- multipart/related
|    +-- image/png
|
+-- application/pdf
~~~

Các assertion chỉ đếm **text/html = 1**, **image/png = 1** và **application/pdf = 1** có thể đều pass. Nhưng quan hệ của HTML với logo không phù hợp.

Với **MimeNodes.Node**, có thể assert:

~~~java
assertTrue(
        related.first("text/html").isPresent(),
        "HTML phải ở trong related"
);

assertTrue(
        related.first("image/png").isPresent(),
        "Logo phải ở cùng related với HTML"
);

assertFalse(
        related.first("application/pdf").isPresent(),
        "PDF độc lập không thuộc nội dung related"
);
~~~

Nếu muốn kiểm tra không có part thừa:

~~~java
long htmlCount = root.all().stream()
        .filter(node -> {
            try {
                return node.isType("text/html");
            } catch (jakarta.mail.MessagingException ex) {
                throw new IllegalStateException(ex);
            }
        })
        .count();

assertEquals(1, htmlCount);
~~~

Chỉ cần assertion về số lượng khi đây là một phần của contract. Nếu email hợp lệ có thêm một HTML part trong **message/rfc822** đính kèm, test “đúng một HTML toàn cây” có thể không còn phù hợp. Hãy xác định **phạm vi nhánh** cần kiểm tra.

## 23. Kiểm tra nhiều tài nguyên inline

Email có thể sử dụng logo, icon và banner:

~~~html
<img src="cid:brand-logo" alt="Logo">
<img src="cid:status-icon" alt="Trạng thái">
<img src="cid:offer-banner" alt="Thông tin">
~~~

Ở code Spring:

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

helper.addInline(
        "status-icon",
        new ClassPathResource("mail/status.png"),
        "image/png"
);

helper.addInline(
        "offer-banner",
        new ClassPathResource("mail/banner.png"),
        "image/png"
);
~~~

Kiểm thử nên bảo đảm:

- HTML tham chiếu đủ các CID cần dùng.
- MIME tree có một part phù hợp cho từng CID.
- Không có hai part dùng **Content-ID** trùng nhau trong cùng message nếu nghiệp vụ yêu cầu định danh duy nhất.
- Mỗi tài nguyên có MIME type và decoded bytes tương ứng.
- Các part được tham chiếu nằm trong nhóm related thích hợp.

### Gom các Content-ID

Ví dụ helper cho test:

~~~java
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

public static List<String> contentIds(
        MimeNodes.Node related
) throws Exception {
    List<String> ids = new ArrayList<>();

    for (MimeNodes.Node node : related.all()) {
        String[] headers = node.part().getHeader("Content-ID");

        if (headers != null) {
            for (String header : headers) {
                ids.add(normalizeContentId(header));
            }
        }
    }
    return List.copyOf(ids);
}
~~~

Sau đó:

~~~java
assertEquals(
        Set.of("brand-logo", "status-icon", "offer-banner"),
        Set.copyOf(contentIds(related))
);

assertEquals(
        3,
        contentIds(related).size(),
        "Không được lặp Content-ID"
);
~~~

Helper **normalizeContentId(...)** được định nghĩa ở mục trước. Ví dụ kiểm tra set và số lượng để phát hiện cả thiếu CID lẫn trùng CID.

**Lưu ý:** cú pháp Content-ID có quy tắc riêng, trong đó phần định danh có thể giống message-id. Test không nên tự chuyển lowercase hoặc xóa ký tự tùy tiện; phải so sánh identifier đúng như ứng dụng đã chọn, và xử lý HTML **cid:** URL theo quy tắc phù hợp.

## 24. MIME tree với HTML-only hoặc plain-text-only

Không phải email nào cũng cần đủ bốn loại part. Cấu trúc hợp lý phụ thuộc vào nội dung.

### Email chỉ có plain text

~~~text
MimeMessage
Content-Type: text/plain; charset=UTF-8
~~~

Nếu code:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        false,
        "UTF-8"
);

helper.setText("Thông báo đơn giản.", false);
~~~

Test có thể assert:

~~~java
assertTrue(received.isMimeType("text/plain"));
assertEquals(
        "Thông báo đơn giản.",
        received.getContent()
);
~~~

### Email chỉ có HTML

Nếu service gọi **setText(html, true)** mà không cung cấp plain text alternative, MIME tree có thể đơn giản chỉ chứa **text/html**. Nếu contract yêu cầu fallback plain text, test phải phát hiện **multipart/alternative** hoặc **text/plain** bị thiếu.

### Email có plain text + HTML

Khi không có inline resource hoặc attachment, service có thể dùng **multipart/alternative** trực tiếp mà không cần mixed/related:

~~~text
MimeMessage
└── multipart/alternative
    ├── text/plain
    └── text/html
~~~

Không nên áp dụng cứng một assertion “root luôn phải là multipart/mixed” cho mọi loại email. Hãy chọn cấu trúc kỳ vọng theo **nội dung thực tế và multipart mode** được service dùng.

## 25. Tác động của Multipart Mode trong MimeMessageHelper

Spring **MimeMessageHelper** cung cấp các chế độ multipart. Mỗi chế độ định hướng cách xây dựng cây.

| Mode | Ý định | Điều cần quan sát |
|---|---|---|
| **MULTIPART_MODE_NO** | Thư đơn giản không có multipart | Thường chỉ có một body text; không thích hợp cho nhiều tài nguyên MIME |
| **MULTIPART_MODE_MIXED** | Gộp các part trong mixed | Các part có thể cùng nằm dưới mixed; mức tương thích inline phụ thuộc client |
| **MULTIPART_MODE_RELATED** | Nhóm các part có quan hệ hiển thị | HTML và inline resource có thể nằm dưới related |
| **MULTIPART_MODE_MIXED_RELATED** | Kết hợp attachments và inline resources | Mixed ngoài cùng, related cho phần nội dung/inline |

Chế độ mặc định khi dùng constructor boolean **multipart=true** trong Spring Mail hiện đại thường là **MIXED_RELATED**. Để làm bài integration test về cấu trúc cụ thể dễ đọc và ít mơ hồ, ví dụ chính đã chọn mode bằng hằng:

~~~java
new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

### Vì sao không chọn mode chỉ dựa trên số attachment?

Có file đính kèm không tự bảo đảm inline resource hoạt động tốt trên mọi email client. Nếu ứng dụng cần hiển thị logo cùng HTML và đính kèm PDF riêng, **MIXED_RELATED** là một cấu trúc thích hợp để thử nghiệm. Các client khác nhau có thể có mức hỗ trợ riêng, vì vậy nên kiểm thử trên những client mục tiêu khi yêu cầu hiển thị quan trọng.

### Test cấu trúc để phát hiện thay đổi ngoài ý muốn

Khi developer đổi:

~~~java
MULTIPART_MODE_MIXED_RELATED
~~~

thành:

~~~java
MULTIPART_MODE_MIXED
~~~

test quan hệ **related → alternative + inline** có thể thất bại. Đó là một thay đổi cấu trúc có ý nghĩa, không phải một khác biệt formatting ngẫu nhiên. Nếu thay đổi được chủ đích, cần xác định lại contract MIME mà ứng dụng muốn hỗ trợ.

## 26. Bcc và dữ liệu MIME nhận được bởi SMTP test server

Bcc có một đặc điểm quan trọng: **địa chỉ người nhận kín thường được dùng trong SMTP envelope nhưng không nên xuất hiện trong header của bản MIME DATA giao cho người nhận**.

Ví dụ ứng dụng chuẩn bị:

~~~java
helper.setTo("customer@localhost");
helper.setBcc("audit@localhost");
~~~

Giao thức SMTP có thể sử dụng:

~~~smtp
MAIL FROM:<notices@example.com>
RCPT TO:<customer@localhost>
RCPT TO:<audit@localhost>
DATA
From: notices@example.com
To: customer@localhost
Subject: Hóa đơn ORD-123
...
~~~

Nếu transport xử lý Bcc đúng, header trong DATA gửi cho recipient không làm lộ **audit@localhost**. Tuy nhiên, **MimeMessage trước khi gửi** có thể vẫn chứa trường Bcc để transport biết danh sách recipient.

Vì vậy nên có hai lớp kiểm tra:

1. **Unit test trước send:** kiểm tra **getRecipients(Message.RecipientType.BCC)** trả địa chỉ mong muốn và Bcc không bị gán nhầm vào To/Cc.
2. **Integration test sau SMTP submission:** server capture **MIME DATA thực sự nhận** và, nếu công cụ hỗ trợ, **envelope recipients**. Xác nhận Bcc là recipient của envelope nhưng không lộ trong header được giao.

Một assertion trên message đã được GreenMail tiếp nhận có thể là:

~~~java
assertNull(
        actual.getHeader("Bcc"),
        "MIME DATA không được công khai header Bcc"
);
~~~

**Chú ý về test server:** không phải API trả message nào cũng thể hiện chính xác từng bản giao cuối cùng, và một số server có thể sao chép/rebuild message cho từng mailbox. Khi kiểm tra tính kín đáo của Bcc, phải xác nhận API trả về **DATA đã được transport gửi**, không phải object gốc trước send hoặc bản có metadata được test server thêm vào.

### Vì sao không chỉ xem getAllRecipients()?

**MimeMessage.getAllRecipients()** đọc các header recipient mà message biểu diễn. Nó không phải API kiểm tra chính xác tất cả lệnh **RCPT TO** đã được gửi trên socket. Nếu test cần chứng minh envelope Bcc, phải dùng SMTP test server có thể ghi envelope hoặc API capture tương ứng.

Nếu test server không hỗ trợ xem envelope, vẫn có thể kiểm tra header Bcc không lộ, nhưng phải trình bày rõ giới hạn kiểm chứng: **chưa xác minh được người nhận Bcc đã nằm trong SMTP RCPT TO**.

## 27. Kiểm tra attachment filename có Unicode

Tên file đính kèm có thể là tiếng Việt:

~~~text
Hóa đơn tháng 11.pdf
Báo cáo thanh toán.pdf
~~~

Khi tạo message:

~~~java
helper.addAttachment(
        "Hóa đơn tháng 11.pdf",
        new ClassPathResource("mail/guide.pdf"),
        "application/pdf"
);
~~~

Test nên kiểm tra tên file **đã decode** theo API JavaMail:

~~~java
String receivedName = pdf.part().getFileName();

assertEquals(
        "Hóa đơn tháng 11.pdf",
        receivedName
);
~~~

MIME headers có thể encode filename bằng cách dùng parameter encoding phù hợp với thư viện và cấu hình. Không nên assert raw header chỉ chứa nguyên vẹn chuỗi Unicode. Nếu API nhận được một tên đã encode mà chưa decode theo cấu hình, cần xử lý bằng **MimeUtility** hoặc các API Jakarta Mail phù hợp với phiên bản đang dùng.

### Tên file không nên là đường dẫn người dùng cung cấp

Email attachment filename nên là **tên file hiển thị**, không chứa đường dẫn filesystem như:

~~~text
C:\Users\someone\private\report.pdf
/home/service/secrets/report.pdf
~~~

Khi ứng dụng tạo tên file từ input hoặc đường dẫn, nên chuẩn hóa và chỉ giữ tên cho phép. Integration test có thể xác nhận filename không chứa path nội bộ hoặc ký tự điều khiển. Không đưa file production hoặc dữ liệu nhạy cảm vào fixture thử nghiệm.

## 28. Không phụ thuộc MIME boundary, Message-ID và Date ngẫu nhiên

Một MIME message có thể được serialize thành:

~~~text
Content-Type: multipart/mixed;
  boundary="----=_Part_23_6984725.1762920000000"
Message-ID: <284923.12.1762920000000@example.com>
Date: Thu, 12 Nov 2026 15:30:00 +0700
~~~

Các giá trị này có thể thay đổi ở những lần tạo thư:

- **Boundary** thường được sinh để tách các MIME part.
- **Message-ID** có thể được sinh hoặc sửa trong quá trình saveChanges/transport.
- **Date** có thể phụ thuộc thời điểm chạy.
- **Content-Transfer-Encoding** có thể khác theo charset và dữ liệu.
- **Thứ tự các header** và cách folding có thể thay đổi.

Nếu mục tiêu là cây MIME, không nên làm:

~~~java
assertEquals(expectedRawEml, serializedEml);
~~~

trừ khi ứng dụng thực sự cần kiểm thử byte-for-byte serialization và đã có cách kiểm soát tất cả những trường biến động.

Thay vào đó:

- Dùng **isMimeType(...)** để kiểm tra loại part.
- Duyệt các container để kiểm tra quan hệ.
- Đọc nội dung đã decode và so sánh giá trị có ý nghĩa.
- Kiểm tra Content-ID sau khi xử lý dấu ngoặc góc.
- So sánh attachment filename và decoded bytes.
- Kiểm tra header Subject/From/To bằng API Jakarta Mail.

### Khi nào cần kiểm tra raw MIME?

Đôi lúc ứng dụng có yêu cầu về encoded-word, Content-Transfer-Encoding hoặc tương thích một hệ thống mail cụ thể. Khi đó có thể kiểm tra raw MIME hoặc **EML**, nhưng nên tách thành test chuyên biệt để không khiến toàn bộ suite integration bị phụ thuộc vào chi tiết ngẫu nhiên không liên quan.

## 29. Kiểm tra chính xác số lượng part cần có

Trong bài test cấu trúc, có thể dùng các quy tắc:

~~~text
Expected:
  1 multipart/mixed root
  1 multipart/related under mixed
  1 multipart/alternative under related
  1 text/plain under alternative
  1 text/html under alternative
  1 image/png with Content-ID brand-logo under related
  1 application/pdf attachment under mixed
~~~

Cách này mạnh hơn việc chỉ kiểm tra một vài substring:

~~~java
assertEquals(
        1,
        related.directChildren("image/png").size()
);

assertEquals(
        1,
        root.directChildren("application/pdf").size()
);

assertEquals(
        1,
        alternative.directChildren("text/plain").size()
);

assertEquals(
        1,
        alternative.directChildren("text/html").size()
);
~~~

Các assertion direct child phù hợp cho **cấu trúc đã xác định trong ví dụ**. Một library/template khác có thể xây thêm một lớp multipart hợp lệ, nên trước khi đặt assertion hãy xác định đây là **contract được ứng dụng chủ động chọn** hay chỉ là một chi tiết implementation.

### Kiểm tra không có attachment bất ngờ

Nếu email chỉ được phép đính kèm một PDF, test có thể đếm tất cả part có disposition **attachment** và assert đúng một phần. Cần xem disposition null ở các inline resource; không nên coi mọi part không phải text là attachment.

~~~java
long attachments = 0;

for (MimeNodes.Node node : root.all()) {
    String disposition = node.part().getDisposition();
    if (disposition != null
            && disposition.equalsIgnoreCase(Part.ATTACHMENT)) {
        attachments++;
    }
}

assertEquals(1, attachments);
~~~

Điều này giúp bắt lỗi một logo bị thêm nhầm bằng **addAttachment(...)** trong khi PDF hợp lệ vẫn còn.

## 30. Những tình huống lỗi nên có integration test

Để test có thể phát hiện những sai lầm thực tế, ngoài happy path nên có các ca biến thể:

| Tình huống | Điều test cần phát hiện |
|---|---|
| Gọi **setText(html, true)** nhưng thiếu plain text | Không có alternative như policy yêu cầu |
| Dùng **addAttachment** cho logo | Logo không có quan hệ inline/CID phù hợp |
| HTML tham chiếu sai CID | Content-ID và src="cid:..." không khớp |
| Thiếu image resource ở classpath | Không thể tạo/gửi message như kỳ vọng |
| File attachment đọc một lần rồi hết stream | Decoded bytes bị rỗng, lỗi hoặc khác fixture |
| Dùng **MULTIPART_MODE_MIXED** thay vì **MIXED_RELATED** | Quan hệ MIME tree thay đổi ngoài contract |
| Quên đặt charset | Tiêu đề hoặc nội dung Unicode không đạt kỳ vọng |
| Dùng file name sai | MIME filename khác tên hiển thị cần gửi |
| Bcc bị đưa nhầm vào Cc | Địa chỉ kín xuất hiện trong header công khai |
| Có thêm attachment ngoài quy định | Số part attachment vượt contract |
| Gửi nhiều notification vào cùng server test không reset | Test nhận thư cũ, đếm sai hoặc nhầm message |

Không cần cố tình đưa mọi lỗi vào một integration test khổng lồ. Các trường hợp quan trọng có thể tách thành test nhỏ, mỗi test chỉ kiểm tra một nhóm invariant có tên rõ ràng.

### Ví dụ: phát hiện thiếu CID

Giả sử HTML:

~~~html
<img src="cid:brand-logo">
~~~

nhưng ứng dụng thêm:

~~~java
helper.addInline(
        "other-logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Một test chỉ thấy **image/png** vẫn có thể pass. Test đúng phải so sánh **cid:brand-logo** với Content-ID đã nhận và thất bại khi không khớp.

### Ví dụ: phát hiện sai nhóm multipart

Nếu message có plain text, HTML và PDF nhưng không có **multipart/alternative**, một số email client có thể trình bày cả plain text như một part độc lập thay vì chọn bản HTML. Test cấu trúc sẽ phát hiện vấn đề trước khi phát hành.

## 31. Phân biệt lỗi tạo MIME với lỗi SMTP transport

Một integration test có thể thất bại trước khi GreenMail nhận được thư. Khi đó chưa thể kết luận cây MIME sai.

~~~text
Service
   |
   +-- Lỗi dựng message
   |     -> MessagingException
   |     -> file fixture không tồn tại
   |     -> thiếu content
   |
   v
JavaMailSenderImpl
   |
   +-- Lỗi kết nối SMTP
   |     -> DNS / refused / timeout
   |     -> sai host hoặc port test
   |
   v
GreenMail
   |
   +-- Message được nhận
   |     -> MIME tree assertions
   |
   v
Test kết thúc
~~~

Các lỗi nên được chẩn đoán theo tầng:

- **File fixture không tồn tại:** sửa test resources và đường dẫn.
- **MessagingException khi helper đặt content:** xem cách tạo message.
- **MailSendException từ JavaMailSender:** kiểm tra server start, host, port, timeout hoặc SMTP policy test.
- **waitForIncomingEmail timeout:** xem actual send call, recipient và trạng thái server.
- **Assertion về MIME tree thất bại sau khi nhận:** xem multipart mode, thứ tự addInline/setText, Content-Type hoặc nguồn dữ liệu.

Không tăng thời gian chờ SMTP để sửa một attachment được gắn sai nhánh MIME. Ngược lại, không sửa MIME tree vì test server chưa khởi động.

## 32. Kiểm tra đầu ra trong Spring Boot integration test

Ở ví dụ trước, test tạo **JavaMailSenderImpl** và service thủ công. Cách này đủ để xác minh Spring Mail transport với SMTP server cục bộ mà không cần khởi động toàn bộ ứng dụng.

Nếu mục tiêu là kiểm tra **auto-configuration Spring Boot** và template/service wiring, có thể dùng **@SpringBootTest** cùng các mail properties trỏ tới GreenMail:

~~~text
@SpringBootTest
      |
      +-- Spring tạo JavaMailSender từ application-test.yml
      |
      +-- NotificationService dùng bean thật
      |
      +-- GreenMail server đang chạy trên localhost
      |
      +-- Test đọc và phân tích MIME tree
~~~

Khi đó cần giải quyết thứ tự lifecycle: GreenMail phải có listener sẵn trước khi service bắt đầu gửi. Nếu dùng port động, property **spring.mail.port** phải được cung cấp đúng thời điểm tạo ApplicationContext.

Các lựa chọn phổ biến:

- Dùng JUnit extension quản lý GreenMail trước test và cấp property tương ứng.
- Dùng property động trong Spring test context khi cấu hình server test đã sẵn.
- Dùng Testcontainers/SMTP capture server với mapped port và cấu hình test động.
- Với ví dụ nhỏ, tạo sender thủ công như phần trước để tránh chi phí ApplicationContext.

Đừng hard-code credential production hoặc để **application-test.yml** vô tình trỏ tới SMTP thật. Một integration test chạy trong CI phải có thể thực thi độc lập với Internet.

## 33. Sử dụng SMTP capture server trong container

Thay GreenMail bằng một SMTP capture server chạy trong container cũng là lựa chọn phù hợp nếu dự án đã dùng Testcontainers.

Ví dụ kiến trúc:

~~~text
JUnit/Testcontainers
      |
      +-- Start Mailpit container
      |      |
      |      +-- SMTP port (mapped)
      |      +-- Message inspection API
      |
      +-- Set spring.mail.host/port for test
      |
      +-- Call notification service
      |
      +-- Poll message capture API with bounded timeout
      |
      +-- Retrieve raw MIME/EML or parsed message
      |
      +-- Parse with jakarta.mail.internet.MimeMessage
      |
      +-- Assert MIME tree
~~~

Khi tải raw EML từ API capture server, có thể tạo **MimeMessage** bằng Jakarta Mail:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.util.Properties;

Session session = Session.getInstance(new Properties());

try (InputStream emlInputStream = /* stream từ test server */) {
    MimeMessage parsed = new MimeMessage(
            session,
            emlInputStream
    );

    MimeNodes.Node root = MimeNodes.read(parsed);
    assertTrue(root.isType("multipart/mixed"));
}
~~~

Đây là skeleton; cách gọi API lấy raw EML phụ thuộc phiên bản và chế độ chạy của Mailpit/MailHog. Không tự giả định mọi API trả một message có cùng định dạng JSON hoặc hỗ trợ endpoint giống nhau.

### Vì sao parse raw EML vẫn hữu ích?

Test không phụ thuộc vào cách SMTP capture server biểu diễn MIME tree trong JSON. Ứng dụng có thể dùng **Jakarta Mail** để diễn giải cùng một dạng MIME mà nó gửi, rồi assert các invariant.

Tuy nhiên, khi cần kiểm tra tương thích với những mail client không dùng Jakarta Mail, nên có thêm test hiển thị hoặc client-specific ở một lớp khác. Parser nhất quán không chứng minh mọi client sẽ render giống nhau.

## 34. Cô lập test khi chạy song song trong CI

Một số lỗi integration test không đến từ cấu trúc email mà đến từ môi trường chạy:

- Hai test cùng dùng một SMTP port cố định.
- Server của test trước chưa dừng hoàn toàn.
- Test mới đọc lại message cũ trong inbox.
- Nhiều test cùng gửi tới một mailbox test rồi lấy phần tử **getReceivedMessages()[0]**.
- Một test chạy quá chậm khiến test khác timeout.

### Nguyên tắc cô lập

1. Mỗi test hoặc nhóm test có **SMTP server lifecycle** rõ ràng.
2. Nếu chạy song song, dùng **port được cấp động** hoặc server/container độc lập.
3. Có **mailbox/recipient riêng** cho những test có khả năng chồng lấn.
4. Không dùng một server shared không reset rồi assert tổng message count toàn hệ thống.
5. Có bounded wait thay vì sleep thời gian cố định.
6. Luôn dọn tài nguyên trong **@AfterEach** hoặc extension lifecycle.

Ví dụ cách chờ:

~~~java
assertTrue(
        greenMail.waitForIncomingEmail(5000, 1),
        "Thư không tới SMTP test server trong giới hạn test"
);
~~~

Tốt hơn cách:

~~~java
Thread.sleep(5000);
~~~

vì hàm wait có thể trả về ngay khi đủ số message; còn sleep luôn chờ đủ thời gian, đồng thời không chỉ rõ điều kiện thành công.

Với hệ thống gửi mail bất đồng bộ hoặc dùng outbox, có thể phải polling trạng thái **submitted** và SMTP inbox theo thời gian hữu hạn. Test nên phân biệt:

- Worker chưa lấy được notification.
- Worker đang xử lý.
- SMTP server chưa nhận.
- SMTP server đã nhận nhưng MIME assertion thất bại.

Đừng biến một test về MIME tree thành test phụ thuộc tốc độ của toàn bộ scheduler production nếu không cần kiểm tra pipeline bất đồng bộ.

## 35. Bảo mật và giới hạn khi phân tích MIME từ test server

Email có thể chứa dữ liệu riêng tư. Ngay cả trong integration test, cần lưu ý:

- Dùng **địa chỉ thử nghiệm**, không gửi tới người nhận thật.
- Không dùng OTP, token khôi phục, số thẻ hoặc hóa đơn production làm fixture.
- Không ghi toàn bộ raw EML và decoded attachment vào log CI.
- Bảo vệ artifact log nếu test thất bại.
- Không tải các link hoặc hình ảnh remote từ HTML trong quá trình parse MIME.
- Khi parse MIME không đáng tin cậy, giới hạn độ sâu, tổng part, byte và thời gian xử lý.
- Không tự động mở hoặc thực thi attachment được lấy từ email.
- Không lưu attachment filename thành đường dẫn filesystem mà chưa sanitize.

### Parser MIME không phải trình duyệt

Đọc **text/html** bằng **Part.getContent()** không đồng nghĩa phải render HTML hay tải tài nguyên bên ngoài. Test có thể kiểm tra chuỗi HTML và CID tham chiếu mà không truy cập Internet.

Nếu dùng HTML parser để trích xuất các giá trị **src="cid:..."**, hãy tách biệt những URL remote như **https://...**. Không tự fetch mọi URL chỉ để “xác minh hình”, vì điều đó biến một bài test offline thành truy cập mạng ngoài hoặc có nguy cơ SSRF nếu HTML đến từ nguồn không tin cậy.

### Không dùng fixture có PII

Ví dụ Subject:

~~~text
Hóa đơn ORD-123 — đã thanh toán
~~~

đủ để test Unicode và mapping. Không cần dùng tên, địa chỉ hay email thật của khách hàng.

## 36. Kiểm thử negative case cho MIME tree

Một happy-path test cho thấy **cấu trúc đúng hiện tại**. Các negative case giúp chứng minh assertion có thể phát hiện sai sót.

### Case 1: logo bị thêm như attachment

Thay vì:

~~~java
helper.addInline(
        "brand-logo",
        logoResource,
        "image/png"
);
~~~

code bị sửa thành:

~~~java
helper.addAttachment(
        "logo.png",
        logoResource,
        "image/png"
);
~~~

Test cần thất bại vì:

- Nhánh related không có CID **brand-logo**, hoặc
- Số attachment vượt kỳ vọng, hoặc
- Hình không có quan hệ với HTML theo contract.

### Case 2: thiếu plain text alternative

Nếu code dùng:

~~~java
helper.setText(htmlText, true);
~~~

thay vì:

~~~java
helper.setText(plainText, htmlText);
~~~

và contract yêu cầu cả plain text lẫn HTML, assertion về **multipart/alternative** hoặc **text/plain** phải thất bại.

### Case 3: sai Content-ID

Nếu HTML tham chiếu **cid:brand-logo** còn MIME part có Content-ID **other-logo**, test phải phát hiện mismatch, dù file PNG vẫn tồn tại và có bytes đúng.

### Case 4: attachment không chứa dữ liệu mong muốn

Nếu source resource rỗng hoặc dữ liệu bị cắt, assertion so sánh decoded bytes phải thất bại.

### Case 5: nhánh MIME sai

Nếu service thay mode hoặc tạo MIME tree thủ công làm PDF trở thành part của related, test về parent-child relation phải thất bại.

Các negative case nên dùng test fixture riêng và không cố tình sửa file production chỉ để tạo lỗi. Có thể tạo một composer thử nghiệm nhận tham số mode hoặc dùng đối tượng message được dựng riêng trong test.

## 37. Bộ invariant nên kiểm tra theo loại email

Thay vì mọi email đều dùng một cây MIME duy nhất, có thể xác định contract riêng:

| Loại email | Những invariant quan trọng |
|---|---|
| Plain text đơn giản | text/plain, charset phù hợp, nội dung đúng |
| Plain text + HTML | multipart/alternative, có text/plain và text/html |
| HTML có logo CID | HTML và image/Content-ID trong related, CID tham chiếu khớp |
| HTML + attachment | mixed chứa nội dung và attachment riêng |
| HTML + inline + attachment | mixed → related → alternative, inline image dưới related, attachment dưới mixed |
| Email nhiều attachment | Đúng số lượng, tên, MIME type, disposition và bytes từng file |
| Email nhiều recipient và Bcc | Header To/Cc đúng; Bcc không lộ trong DATA, envelope recipient được xác minh nếu công cụ hỗ trợ |

Khi tổ chức test suite, đặt tên test diễn đạt kết quả cần chứng minh:

~~~text
shouldSendPlainAndHtmlAsAlternatives()
shouldKeepInlineLogoRelatedToHtml()
shouldAttachPdfOutsideRelatedContent()
shouldPreserveUnicodeSubjectAndBody()
shouldNotExposeBccInCapturedMimeData()
shouldPreserveDecodedAttachmentBytes()
~~~

Tên test theo hành vi giúp đọc báo cáo CI dễ hơn tên chỉ mô tả implementation như **testHelper1** hoặc **testMime2**.

## 38. Các sai lầm thường gặp khi test MIME tree

| Sai lầm | Vì sao không phù hợp | Hướng tốt hơn |
|---|---|---|
| Chỉ verify **mailSender.send(any())** | Không kiểm tra nội dung SMTP nhận | Dùng server kiểm thử và đọc MIME |
| Mock toàn bộ MimeMessage | Không phản ánh serialization thật | Dùng MimeMessage thật với transport test |
| Chỉ kiểm tra số attachment | Không biết inline/CID đúng chưa | Kiểm tra vị trí, disposition, Content-ID |
| So sánh raw EML byte-for-byte | Boundary/Message-ID/Date có thể đổi | Assert semantic tree |
| So sánh Content-Type nguyên chuỗi | Có boundary, charset và parameter | Dùng isMimeType và ContentType parser |
| Chỉ tìm text/plain và text/html toàn cây | Có thể sai quan hệ multipart | Kiểm tra chúng ở trong alternative |
| Chỉ assert một image/png tồn tại | HTML có thể tham chiếu CID khác | So sánh HTML cid và Content-ID |
| Xem object trước send là SMTP capture | Không chứng minh transport đã gửi | Đọc từ server test thật |
| Assert Bcc null trên object trước send | Không kiểm tra được Bcc recipient | Tách pre-send và SMTP DATA tests |
| Đọc Bcc từ header để suy ra RCPT TO | Header khác SMTP envelope | Dùng envelope capture nếu cần |
| So sánh chuỗi base64 gốc | Folding và encoding có thể đổi | So sánh decoded bytes |
| Dùng file lớn hoặc dữ liệu khách thật | Test nặng và rủi ro dữ liệu | Dùng fixture nhỏ, giả |
| Dùng SMTP production trong CI | Có side effect và phụ thuộc mạng | Server local/container sandbox |
| Dùng port test cố định cho mọi test chạy song song | Collision và flakiness | Port động hoặc instance cô lập |
| Parse HTML rồi tải mọi URL | Có thể kết nối Internet/SSRF | Chỉ kiểm tra cấu trúc và CID offline |
| Không giới hạn duyệt MIME | Cây sâu hoặc số part lớn gây tốn tài nguyên | Giới hạn độ sâu, node, bytes |

## 39. Runbook khi một assertion MIME tree thất bại

Khi test thất bại, nên điều tra theo thứ tự:

1. **SMTP server có nhận message không?** Nếu không, tập trung vào setup, host, port và exception.
2. **Đúng message chưa?** Xác định Subject/recipient và tránh lẫn inbox từ test khác.
3. **Root Content-Type là gì?** Plain text, alternative, related hay mixed?
4. **Có đúng nhánh multipart không?** Quan sát quan hệ parent-child, không chỉ danh sách phẳng.
5. **Plain text và HTML có trong alternative không?** So sánh nội dung đã giải mã.
6. **HTML tham chiếu CID nào?** So sánh Content-ID của inline parts.
7. **Inline resource nằm ở đâu?** Kiểm tra related, Content-Type và disposition.
8. **Attachment nằm ở đâu?** Kiểm tra mixed, filename, disposition và decoded bytes.
9. **Charset có đúng không?** Dùng getSubject/getContent đã decode, xem Content-Type nếu cần.
10. **Test có phụ thuộc detail ngẫu nhiên không?** Boundary, encoding, Message-ID, header folding hoặc thứ tự không được cam kết.
11. **Server test có chỉnh sửa message không?** Một số proxy/ESP có thể rewrite header hoặc cấu trúc.
12. **Thay đổi có chủ đích không?** Nếu composer đổi multipart mode, cần cập nhật contract test một cách có giải thích, không chỉ xóa assertion bị fail.

### Ví dụ đọc lỗi

~~~text
Expected:
  related -> alternative -> text/plain + text/html

Actual:
  mixed -> text/html + image/png + application/pdf
~~~

Khi thấy khác biệt này, cần xem **multipart mode** và cách composer gọi **setText/addInline/addAttachment**. Chỉ vì server SMTP trả 250 không có nghĩa cấu trúc đã đúng cho email client.

## 40. Tổng kết

**Xác minh MIME tree trên server kiểm thử** là một phép kiểm thử tích hợp quan trọng cho email có HTML, bản plain text thay thế, hình inline và file đính kèm trong Spring Framework Mail.

Quy trình cốt lõi:

1. Tạo email bằng **JavaMailSenderImpl** và **MimeMessageHelper** thực, với nội dung/fixture có thể dự đoán.
2. Gửi qua **SMTP test server** như GreenMail hoặc một SMTP capture server độc lập, không dùng SMTP production.
3. Chờ server nhận và lấy lại **MimeMessage hoặc raw EML** đã nhận.
4. Duyệt **Part / Multipart / BodyPart** để biểu diễn cây MIME.
5. Kiểm tra quan hệ **multipart/mixed → multipart/related → multipart/alternative** khi đó là contract của email có attachment và inline resource.
6. Kiểm tra **Content-Type**, **Content-ID**, **Content-Disposition**, filename, Subject/charset và decoded content/bytes.
7. Kiểm tra Bcc ở đúng tầng: recipient được chọn trước send, còn tính kín đáo được kiểm chứng qua SMTP DATA/envelope khi công cụ hỗ trợ.
8. Tránh phụ thuộc vào boundary, encoded-word, Message-ID hoặc thứ tự header không quan trọng.
9. Cô lập SMTP server, mailbox và fixture để test chạy ổn định trong CI.

**Mục đích không phải kiểm tra Jakarta Mail đã tạo một chuỗi MIME bất kỳ, mà là chứng minh email đã được gửi tới server thử nghiệm với những phần nội dung và quan hệ MIME mà email client cần để hiển thị đúng.** Đây là lớp kiểm chứng bổ sung cho unit test service, trước khi triển khai thực tế và đánh giá khả năng hiển thị trên những email client mục tiêu.


