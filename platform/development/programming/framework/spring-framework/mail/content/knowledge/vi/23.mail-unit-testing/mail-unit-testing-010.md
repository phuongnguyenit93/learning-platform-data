# Kiểm tra lỗi khi địa chỉ hoặc resource không hợp lệ

Trong Spring Framework Mail, email có thể thất bại ngay từ bước **chuẩn bị dữ liệu**, trước khi ứng dụng kết nối tới SMTP server. Một địa chỉ người nhận sai cú pháp, một địa chỉ chứa ký tự điều khiển, file đính kèm không tồn tại hoặc resource không thể mở stream đều có thể làm cho việc dựng message bị lỗi. Nếu các trường hợp này không được kiểm thử, sự cố có thể chỉ xuất hiện sau khi deploy, khi worker xử lý hàng đợi hoặc thậm chí khi Jakarta Mail bắt đầu serialize MIME message để gửi.

**Kiểm thử đơn vị lỗi khi địa chỉ hoặc resource không hợp lệ** có mục tiêu: cung cấp đầu vào xấu một cách có kiểm soát, xác nhận ứng dụng **từ chối hoặc báo lỗi đúng loại**, và xác nhận **không phát sinh thao tác gửi email ngoài ý muốn**.

Trong hệ sinh thái Spring Mail, cần phân biệt:

- **SimpleMailMessage:** chủ yếu là dữ liệu cho email plain text; các setter không phải một dịch vụ xác minh mailbox hay kiểm tra tài nguyên.
- **MimeMessage + MimeMessageHelper:** dựng message MIME, có thể parse địa chỉ qua Jakarta Mail và gắn attachment/inline resource.
- **Resource / InputStreamSource:** nguồn byte của attachment hoặc inline image; việc có thể mở stream và đọc đủ dữ liệu là một trách nhiệm khác với việc kiểm tra địa chỉ.
- **JavaMailSender.send(...):** ranh giới side effect chuyển message qua transport SMTP.

Nên kiểm thử từng ranh giới bằng **JUnit 5**, **Mockito**, đối tượng MIME thật được tạo trong bộ nhớ và resource giả lập. **Không cần gửi email tới người nhận thật** để kiểm tra lỗi nhập liệu, file thiếu hoặc lỗi đọc stream.

## 1. Vì sao phải tách lỗi dữ liệu khỏi lỗi SMTP?

Một luồng xử lý điển hình:

~~~text
Business DTO / request
        |
        v
Validate mail addresses
        |
        v
Validate subject / filename / resource
        |
        v
Read or prepare resource bytes
        |
        v
Build SimpleMailMessage or MimeMessage
        |
        v
JavaMailSender.send(...)
        |
        v
SMTP connection / delivery attempt
~~~

Lỗi có thể xảy ra tại bất kỳ bước nào.

| Giai đoạn | Lỗi ví dụ | Điều nên kiểm thử |
| --- | --- | --- |
| DTO đầu vào | Recipient null, subject rỗng | Từ chối trước khi gọi sender |
| Address validation | Sai cú pháp, nhiều mailbox ở trường chỉ cho phép một | Exception và không gửi |
| Header validation | CR/LF trong Subject hoặc filename | Không dựng header từ dữ liệu xấu |
| Resource lookup | File classpath không tồn tại | Lỗi rõ ràng, không coi file rỗng là hợp lệ |
| Resource read | IOException, stream đóng, thiếu quyền | Phân loại lỗi đọc, không gọi send |
| Resource content | File rỗng, quá lớn, loại dữ liệu không được phép | Từ chối theo hợp đồng ứng dụng |
| MIME building | AddressException hoặc MessagingException | Không nhầm với lỗi SMTP provider |
| SMTP transport | AUTH, TLS, RCPT TO, DATA hoặc timeout | Đây là nhóm kiểm thử tích hợp/transport riêng |

Một **unit test của dữ liệu** không cần tạo kết nối mạng. Điều cần kiểm chứng là lệnh gửi không được thực hiện nếu dữ liệu cần thiết chưa đạt yêu cầu.

## 2. Khái niệm "địa chỉ không hợp lệ" cần được định nghĩa rõ

Một địa chỉ có thể không phù hợp ở những mức khác nhau:

1. **Null hoặc blank:** không có dữ liệu.
2. **Sai cú pháp:** chuỗi không biểu diễn đúng một mailbox theo quy tắc ứng dụng hỗ trợ.
3. **Không phù hợp hợp đồng:** chuỗi chứa display name, nhóm địa chỉ hoặc nhiều địa chỉ trong một trường chỉ cho phép một.
4. **Chứa ký tự điều khiển:** có CR/LF hoặc control character ở vị trí có thể ảnh hưởng header.
5. **Không được phép theo nghiệp vụ:** recipient thuộc danh sách chặn hoặc domain không được gửi.
6. **Mailbox không tồn tại:** phải có tín hiệu phù hợp từ server hoặc quy trình xác minh; kiểm tra cú pháp đơn thuần không chứng minh điều này.

**InternetAddress.validate() không xác nhận mailbox thật sự tồn tại**. Một unit test không nên kết nối tới máy chủ của domain bất kỳ chỉ để kết luận địa chỉ có nhận được email hay không.

### 2.1. Ví dụ địa chỉ nên bị từ chối theo hợp đồng đơn mailbox

~~~text
null
""
"     "
"invalid-address"
"alice@@example.net"
"alice@example.net, bob@example.net"
"alice@example.net\r\nBcc: outside@example.net"
~~~

Những chuỗi trên giúp kiểm tra nhiều nhóm lỗi khác nhau. Hãy xác định rõ test đang kiểm tra **validation do ứng dụng đặt ra** hay hành vi parse của Jakarta Mail; không suy diễn rằng tất cả phiên bản parser sẽ xử lý mọi chuỗi lỗi giống hệt nhau.

### 2.2. Tránh một regex ASCII quá đơn giản

Một regex kiểu:

~~~text
^[^@]+@[^@]+\.[^@]+$
~~~

có thể vừa chấp nhận đầu vào không phù hợp vừa loại bỏ các trường hợp hợp lệ theo tiêu chuẩn email. Với địa chỉ quốc tế hóa, quoted local-part, IDN hoặc SMTPUTF8, cần chính sách hỗ trợ cụ thể.

Một cách phù hợp cho unit test là: **định nghĩa hợp đồng đầu vào mà sản phẩm thực sự hỗ trợ**, sử dụng parser thư viện khi cần, rồi kiểm tra thêm các ràng buộc nghiệp vụ. Parser và hợp đồng sản phẩm không phải một.

## 3. SimpleMailMessage không thay thế validation

Với email plain text:

~~~java
SimpleMailMessage message = new SimpleMailMessage();

message.setFrom("notifications@example.org");
message.setTo("invalid-address");
message.setSubject("Thông báo");
message.setText("Nội dung");
~~~

Việc gọi setter để lưu chuỗi vào SimpleMailMessage không phải một giao dịch SMTP và không chứng minh địa chỉ đúng cú pháp. Một lỗi có thể được phát hiện về sau tại tầng gửi, hoặc provider có thể xử lý theo cách riêng.

Do đó, không viết test dựa trên giả định rằng mọi chuỗi sai đều lập tức làm **SimpleMailMessage.setTo(...)** ném exception.

### 3.1. Validation nên nằm trước khi tạo message

~~~text
Recipient input
      |
      v
Address validation
      |
      +-- Invalid -> reject
      |
      v
SimpleMailMessage.setTo(...)
      |
      v
MailSender.send(...)
~~~

Một service có thể dùng validator riêng trước khi tạo SimpleMailMessage.

### 3.2. Unit test hợp đồng

Với đầu vào sai:

- Validator ném exception đã định nghĩa.
- Không tạo một lệnh gửi tới MailSender.
- Không tự thay recipient sai bằng một địa chỉ mặc định nguy hiểm.
- Không âm thầm bỏ recipient và gửi sang người khác.

Với đầu vào hợp lệ:

- Trường To/From/Reply-To chứa đúng giá trị.
- Không tự bổ sung CC/BCC.
- Chủ đề và body không bị thay đổi ngoài hợp đồng.

## 4. MimeMessageHelper và Jakarta Mail có thể phát hiện lỗi sớm hơn

Khi sử dụng **MimeMessageHelper**:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        "UTF-8"
);

helper.setTo("alice@example.net");
~~~

Một số API của helper sẽ parse địa chỉ và có thể phát sinh **jakarta.mail.internet.AddressException**, vốn thuộc hệ phân cấp **MessagingException**.

Tuy nhiên, **không phải mọi lỗi đều phát sinh ngay tại helper.set...**. Đặc biệt, việc gắn Resource có thể chỉ đăng ký nguồn dữ liệu; dữ liệu thật đôi khi được đọc khi MIME part được serialize hoặc send.

Vì vậy, cần biết test đang đặt câu hỏi nào:

- Parser có từ chối một chuỗi địa chỉ không?
- Ứng dụng có từ chối dữ liệu sai trước khi gọi helper không?
- Resource có thể được đọc không?
- Attachment có thể được đọc nhiều lần nếu transport yêu cầu không?
- Khi dữ liệu không hợp lệ, có tránh được lời gọi JavaMailSender.send không?

Những câu hỏi này cần test ở các ranh giới khác nhau.

## 5. Resource trong Spring Mail là gì?

**Resource** là một abstraction của Spring để truy cập dữ liệu qua classpath, file, URL hoặc nguồn khác. Nhiều Resource cũng cung cấp InputStreamSource để Jakarta Mail đọc byte.

Các loại thường gặp:

| Loại | Vai trò thường gặp | Điều cần chú ý |
| --- | --- | --- |
| **ClassPathResource** | File đóng gói trong ứng dụng | Sai path có thể chỉ lộ ra khi mở stream |
| **FileSystemResource** | File trên filesystem | File có thể bị xóa, đổi quyền, thay đổi sau kiểm tra |
| **ByteArrayResource** | Nội dung byte đã có sẵn trong bộ nhớ | Có thể cung cấp stream mới từ byte[] |
| **InputStreamResource** | Bao một InputStream đã mở | Thường không phù hợp nếu transport cần đọc lại stream |
| **UrlResource** | Dữ liệu từ URL | Có thể tạo I/O mạng; cần kiểm soát nguồn và SSRF |

Không phải mọi Resource đều được đảm bảo là **tệp PDF thật**, dù filename kết thúc bằng .pdf. Một resource còn tồn tại cũng có thể rỗng, sai nội dung hoặc không thể đọc.

### 5.1. Resource có thể được đọc muộn

Ví dụ:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);
~~~

Code này mô tả attachment bằng một nguồn dữ liệu. Tùy overload và cách Jakarta Mail serialize, việc đọc stream có thể xảy ra muộn hơn bước addAttachment.

Do vậy, **không nên khẳng định mọi resource bị thiếu sẽ ném exception ngay tại addAttachment**. Nếu nghiệp vụ yêu cầu fail-fast, hãy kiểm tra và đọc dữ liệu trước khi cho phép gửi.

### 5.2. exists() là hữu ích nhưng không tuyệt đối

~~~java
Resource resource = new ClassPathResource("mail/invoice.pdf");

if (!resource.exists()) {
    throw new IllegalArgumentException(
            "Attachment resource does not exist"
    );
}
~~~

Kiểm tra exists() giúp lỗi rõ hơn. Nhưng vẫn cần mở stream vì:

- Quyền đọc có thể không đủ.
- Resource có thể thay đổi giữa kiểm tra và đọc.
- Nguồn remote có thể không đáp ứng mặc dù metadata cho biết tồn tại.
- Một số Resource có semantics exists/isReadable khác nhau.

**Kiểm tra đọc thực tế** là bước quyết định khi cần chuẩn bị nội dung attachment một cách xác định.

## 6. Kiến trúc kiểm thử: tách chuẩn bị khỏi gửi

Một cách tổ chức rõ ràng:

~~~text
StatementMailRequest
       |
       v
MailInputValidator
       |
       +-- Address / subject / filename
       |
       v
ResourceLoader / ContentChecker
       |
       +-- exists / readable / bounded read
       |
       v
StatementMimeFactory
       |
       +-- MimeMessageHelper
       |
       v
StatementDeliveryService
       |
       v
JavaMailSender.send(...)
~~~

Ưu điểm:

- Test validation mà không dựng MIME.
- Test resource bằng byte[] hoặc stream giả.
- Test việc tạo MIME trong bộ nhớ.
- Test service không gọi send nếu dữ liệu sai.
- Test ngoại lệ xảy ra khi resource đọc thất bại, không phụ thuộc mạng.
- Dễ phân loại lỗi dữ liệu với lỗi SMTP tạm thời.

Ví dụ dưới đây đặt validation và resource loading trong một factory cho dễ theo dõi. Trong dự án lớn, có thể tách chúng thành nhiều class mà vẫn giữ nguyên ranh giới trách nhiệm.

## 7. Khai báo request chứa dữ liệu và Resource

Một DTO Java đơn giản:

~~~java
import org.springframework.core.io.Resource;

public record StatementMailRequest(
        String recipient,
        String subject,
        String body,
        String attachmentFilename,
        Resource attachment
) {}
~~~

Các trường được kỳ vọng:

- **recipient:** một mailbox phù hợp hợp đồng.
- **subject:** một dòng, không rỗng.
- **body:** nội dung văn bản, không rỗng.
- **attachmentFilename:** tên file dùng trong MIME header, không phải đường dẫn tùy ý.
- **attachment:** nguồn dữ liệu có thể đọc.

Record không tự validate những dữ liệu này. Factory hoặc tầng validation cần đưa ra quyết định rõ ràng trước khi tạo MIME message.

## 8. Ví dụ factory fail-fast cho địa chỉ và attachment

Factory dưới đây nhận một request cần đính kèm PDF, kiểm tra dữ liệu, đọc attachment có giới hạn kích thước, rồi tạo **MimeMessage** trong bộ nhớ. Nó **không gọi send**.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Objects;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class StatementMimeFactory {

    private static final int MAX_PDF_BYTES = 1_048_576;

    private final JavaMailSender mailSender;

    public StatementMimeFactory(JavaMailSender mailSender) {
        this.mailSender =
                Objects.requireNonNull(mailSender, "mailSender");
    }

    public MimeMessage prepare(StatementMailRequest request)
            throws MessagingException {

        Objects.requireNonNull(request, "request");

        String recipient = validateMailbox(
                request.recipient(),
                "recipient"
        );

        String subject = validateSingleLine(
                request.subject(),
                "subject"
        );

        String body = validateBody(request.body());

        String filename = validateFilename(
                request.attachmentFilename()
        );

        byte[] pdf = readPdf(request.attachment());

        MimeMessage mimeMessage =
                mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("billing@example.org");
        helper.setReplyTo("support@example.org");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(body, false);

        helper.addAttachment(
                filename,
                new ByteArrayResource(pdf),
                "application/pdf"
        );

        return mimeMessage;
    }

    static String validateMailbox(
            String raw,
            String field
    ) {
        String value = validateSingleLine(raw, field);

        // Quy tắc sản phẩm: yêu cầu mailbox có local-part
        // và domain; không hỗ trợ dạng địa chỉ chỉ là local name.
        int at = value.indexOf('@');

        if (at <= 0 || at == value.length() - 1) {
            throw new IllegalArgumentException(
                    field + " must be a mailbox address"
            );
        }

        try {
            InternetAddress address =
                    new InternetAddress(value, true);

            address.validate();

            if (address.isGroup()
                    || !value.equals(address.getAddress())
                    || address.getPersonal() != null) {
                throw new IllegalArgumentException(
                        field + " must contain one mailbox only"
                );
            }

            return value;
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    field + " has invalid syntax",
                    ex
            );
        }
    }

    static String validateSingleLine(
            String raw,
            String field
    ) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank"
            );
        }

        String value = raw.trim();

        for (int i = 0; i < value.length(); i++) {
            if (Character.isISOControl(value.charAt(i))) {
                throw new IllegalArgumentException(
                        field + " contains a control character"
                );
            }
        }

        return value;
    }

    static String validateBody(String body) {
        if (body == null || body.isBlank()) {
            throw new IllegalArgumentException(
                    "body must not be blank"
            );
        }

        return body;
    }

    static String validateFilename(String raw) {
        String value = validateSingleLine(
                raw,
                "attachmentFilename"
        );

        if (value.equals(".") || value.equals("..")
                || value.indexOf('/') >= 0
                || value.indexOf('\\') >= 0) {
            throw new IllegalArgumentException(
                    "attachmentFilename must be a plain filename"
            );
        }

        if (!value.toLowerCase(java.util.Locale.ROOT)
                .endsWith(".pdf")) {
            throw new IllegalArgumentException(
                    "Only PDF attachment filenames are allowed"
            );
        }

        return value;
    }

    static byte[] readPdf(Resource resource) {
        if (resource == null) {
            throw new IllegalArgumentException(
                    "attachment must not be null"
            );
        }

        if (!resource.exists() || !resource.isReadable()) {
            throw new IllegalArgumentException(
                    "attachment resource is unavailable"
            );
        }

        try (InputStream input = resource.getInputStream()) {
            byte[] bytes = input.readNBytes(
                    MAX_PDF_BYTES + 1
            );

            if (bytes.length == 0) {
                throw new IllegalArgumentException(
                        "attachment resource is empty"
                );
            }

            if (bytes.length > MAX_PDF_BYTES) {
                throw new IllegalArgumentException(
                        "attachment exceeds allowed size"
                );
            }

            return bytes;
        } catch (IOException ex) {
            throw new UncheckedIOException(
                    "Cannot read attachment resource",
                    ex
            );
        }
    }
}
~~~

### 8.1. Tại sao kiểm tra trước createMimeMessage()?

Factory cố ý kiểm tra địa chỉ, subject, filename và resource **trước** khi gọi **mailSender.createMimeMessage()**. Điều đó cho phép unit test xác nhận không có tương tác với mail sender khi input đã sai.

Đây là lựa chọn thiết kế giúp test dễ hơn, không phải yêu cầu bắt buộc của Jakarta Mail. Một factory khác có thể tạo MimeMessage trước rồi kiểm tra; khi đó test nên assert **không gọi send**, thay vì bắt buộc createMimeMessage chưa được gọi.

### 8.2. Tại sao phải đọc resource thành byte[]?

**ByteArrayResource** có thể cung cấp stream mới từ cùng dữ liệu, phù hợp trường hợp Jakarta Mail cần đọc part nhiều lần khi chuẩn bị hoặc serialize.

Đọc trước còn giúp phát hiện sớm:

- IOException khi mở/đọc.
- Resource rỗng.
- Tệp quá giới hạn ứng dụng.
- Resource không tồn tại hoặc không đọc được.

### 8.3. Giới hạn kích thước đọc

Cách đọc:

~~~java
byte[] bytes = input.readNBytes(MAX_PDF_BYTES + 1);
~~~

giúp phát hiện input vượt giới hạn bằng cách đọc **tối đa một byte hơn mức cho phép**, thay vì gọi readAllBytes() trên một nguồn lớn không kiểm soát.

Đây là giới hạn dữ liệu của ví dụ, không phải giới hạn mặc định của Spring Mail. Khi dùng attachment lớn, cần thiết kế giới hạn bộ nhớ, streaming hoặc storage phù hợp.

### 8.4. Kiểm tra extension chưa chứng minh file là PDF

Điều kiện filename kết thúc bằng .pdf **không xác nhận bytes là PDF hợp lệ**. Nếu nghiệp vụ yêu cầu chỉ nhận tài liệu PDF thật, cần thêm kiểm tra loại nội dung và định dạng ở thành phần chuyên trách. Không chỉ dựa vào file extension hoặc MIME type do client cung cấp.

### 8.5. Validation địa chỉ là policy của ví dụ

Factory yêu cầu chuỗi biểu diễn một mailbox và có dấu @, đồng thời không chấp nhận display name trong trường recipient. Một hệ thống hỗ trợ cú pháp email đặc biệt hoặc SMTPUTF8 có thể cần policy khác. Không xem helper validateMailbox như implementation hoàn chỉnh mọi chuẩn email.

## 9. Service gửi tách biệt factory

Một service thực hiện side effect có thể rất ngắn:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class StatementDeliveryService {

    private final StatementMimeFactory factory;
    private final JavaMailSender mailSender;

    public StatementDeliveryService(
            StatementMimeFactory factory,
            JavaMailSender mailSender
    ) {
        this.factory = factory;
        this.mailSender = mailSender;
    }

    public void send(StatementMailRequest request)
            throws MessagingException {

        MimeMessage message = factory.prepare(request);
        mailSender.send(message);
    }
}
~~~

**Thứ tự này có ý nghĩa**:

~~~text
Factory.prepare(request)
      |
      +-- Invalid -> exception
      |               |
      |               v
      |            No send
      |
      +-- Valid -> MimeMessage
                       |
                       v
                JavaMailSender.send
~~~

Nếu resource không thể đọc, service không chuyển message tới transport. Khi gửi thực sự thất bại, đó là một nhóm lỗi khác với validation/resource preflight.

## 10. Test địa chỉ sai bằng JUnit 5 ParameterizedTest

JUnit 5 có thể chạy cùng một kiểm thử với nhiều dữ liệu xấu.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class StatementAddressValidationTest {

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {
            " ",
            "invalid-address",
            "@example.net",
            "alice@@example.net",
            "alice@example.net, bob@example.net",
            "alice@example.net\r\nBcc: outside@example.net"
    })
    void rejectsInvalidMailbox(String address) {
        assertThrows(
                IllegalArgumentException.class,
                () -> StatementMimeFactory.validateMailbox(
                        address,
                        "recipient"
                )
        );
    }
}
~~~

Đây là test của **validator ứng dụng trong ví dụ**. Chúng không gửi SMTP và không dựa vào việc mailbox thật có tồn tại.

### 10.1. Vì sao có NullAndEmptySource và ValueSource?

- **@NullAndEmptySource**: kiểm thử null và chuỗi rỗng.
- **@ValueSource**: kiểm thử khoảng trắng, thiếu dấu @, nhiều @, danh sách địa chỉ sai hợp đồng và CR/LF.

Nếu sản phẩm cho phép một cú pháp khác, hãy thay đổi policy và test cùng nhau.

### 10.2. Test địa chỉ hợp lệ

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

@Test
void acceptsSupportedMailbox() {
    assertEquals(
            "an@example.net",
            StatementMimeFactory.validateMailbox(
                    "  an@example.net  ",
                    "recipient"
            )
    );
}
~~~

Kiểm tra positive case rất cần thiết: một validator sai có thể từ chối mọi địa chỉ và vẫn vượt qua tất cả negative test.

### 10.3. Không kiểm tra sự tồn tại mailbox bằng unit test

Không nên cho test gọi DNS hoặc SMTP VRFY tới domain thật. Unit test chỉ cần xác định **dữ liệu có hợp đồng hợp lệ hay không**. Kết quả chuyển phát là trách nhiệm của SMTP/provider và telemetry tương ứng.

## 11. Test From, To, Reply-To, CC và BCC

Những trường địa chỉ này có tác động khác nhau.

| Trường | Rủi ro nếu không hợp lệ | Cần test gì? |
| --- | --- | --- |
| **From** | Sender không đúng/không được phép | Đến từ cấu hình được kiểm soát, cú pháp hợp lệ |
| **To** | Gửi sai người hoặc không có người nhận | Đúng recipient, không rỗng, không chèn danh sách bất ngờ |
| **Reply-To** | Phản hồi đến người ngoài ý muốn | Giá trị đúng, không lấy từ input tùy tiện |
| **CC** | Lộ thông tin cho người nhận bản sao | Chỉ người được phép, không thêm ngầm |
| **BCC** | Lộ dữ liệu qua envelope hoặc gửi ngoài chính sách | Chỉ thêm theo nghiệp vụ, không để giá trị cũ |

Nếu một trường chứa nhiều địa chỉ, hãy xác định rõ chính sách khi:

- Mảng null.
- Mảng rỗng.
- Có phần tử null hoặc blank.
- Có phần tử sai cú pháp.
- Có địa chỉ bị lặp.
- Người nhận xuất hiện ở nhiều nhóm To/CC/BCC.

### 11.1. Fail toàn message hay bỏ recipient không hợp lệ?

Hai chính sách có thể khác nhau:

- **All-or-nothing:** nếu có bất kỳ địa chỉ không hợp lệ, không gửi message.
- **Partial acceptance ở tầng ứng dụng:** lọc người nhận sai và gửi cho phần còn lại, nhưng phải có hợp đồng rõ, ghi nhận ai bị loại và xem xét quyền riêng tư.

Không âm thầm bỏ một recipient trong email giao dịch nếu điều đó làm mất thông báo quan trọng hoặc khiến dữ liệu gửi sai nhóm.

### 11.2. Bcc không phải biện pháp thay thế validation

Dù Bcc có thể ẩn khỏi header hiển thị, SMTP server vẫn nhận envelope recipient. Một Bcc sai hoặc ngoài ý muốn vẫn dẫn tới việc gửi sai người.

### 11.3. Test dữ liệu người gửi cấu hình sai

Nếu From/Reply-To được lấy từ configuration, kiểm thử cấu hình qua một validator hoặc factory riêng. Không nên đợi SMTP trả 550 hoặc 553 mới biết một giá trị cấu hình bị lỗi cú pháp.

## 12. Test không có thao tác gửi khi recipient không hợp lệ

Đây là một test tương tác ở ranh giới JavaMailSender:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;

class StatementDeliveryServiceTest {

    @Test
    void doesNotUseMailSenderForInvalidRecipient() {
        JavaMailSender sender = mock(JavaMailSender.class);
        StatementMimeFactory factory =
                new StatementMimeFactory(sender);

        StatementDeliveryService service =
                new StatementDeliveryService(factory, sender);

        StatementMailRequest request = new StatementMailRequest(
                "invalid-address",
                "Thông báo sao kê",
                "Vui lòng xem file đính kèm.",
                "statement.pdf",
                new ByteArrayResource(
                        "test-pdf".getBytes(StandardCharsets.UTF_8)
                )
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> service.send(request)
        );

        verifyNoInteractions(sender);
    }
}
~~~

Vì factory kiểm tra recipient trước khi gọi createMimeMessage, không có lời gọi nào tới mock sender.

### 12.1. Nếu kiến trúc không tách như ví dụ

Một factory khác có thể gọi createMimeMessage trước khi validate. Khi đó hãy kiểm tra tối thiểu:

~~~java
verify(sender, never()).send(
        any(MimeMessage.class)
);
~~~

Không bắt test phải khớp một thứ tự nội bộ không thuộc hợp đồng.

### 12.2. Điều test này không khẳng định

Nó không chứng minh server sẽ chấp nhận các địa chỉ hợp lệ. Nó chỉ chứng minh **đầu vào sai theo policy không dẫn tới lời gọi send**.

## 13. Test trường Subject chứa ký tự điều khiển

Header injection là một nhóm lỗi đầu vào có tác động bảo mật.

Ví dụ input:

~~~text
Báo cáo tháng 11
Bcc: outside@example.net
~~~

Nếu ứng dụng tự ghép raw header từ chuỗi đó, dữ liệu có thể bị hiểu sai khi serialize. Dù các API Jakarta Mail có cơ chế xử lý header riêng, **validation input một dòng vẫn hữu ích** khi hợp đồng không cho phép newline trong subject.

Ví dụ test:

~~~java
@Test
void rejectsCarriageReturnOrNewlineInSubject() {
    String injected = "Sao kê\r\nBcc: outside@example.net";

    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.validateSingleLine(
                    injected,
                    "subject"
            )
    );
}
~~~

### 13.1. Kiểm tra các control character khác

Không chỉ có CR và LF. Một số ký tự điều khiển khác có thể làm log và header khó đọc hoặc gây mơ hồ. Factory ví dụ dùng **Character.isISOControl(...)** để áp dụng chính sách single-line chặt chẽ.

### 13.2. Body là trường nhiều dòng

Không dùng cùng validator single-line cho body. Email plain text thường cần xuống dòng hợp lệ.

Mục tiêu là phân biệt:

- **Header-like fields:** một dòng, kiểm tra control characters.
- **Body:** nhiều dòng được phép; vẫn cần kiểm tra nội dung và độ dài theo nghiệp vụ.

### 13.3. Dữ liệu Unicode tiếng Việt

Các chuỗi như **“Thông báo sao kê”** hoặc **“Nguyễn Ánh”** không phải ký tự điều khiển và cần được xử lý đúng. Không loại bỏ dấu tiếng Việt chỉ để tránh lỗi header.

## 14. Kiểm thử Resource không tồn tại

Một ClassPathResource có thể được tạo thành công dù path được truyền không trỏ tới file có thật.

~~~java
Resource resource =
        new ClassPathResource("mail/missing.pdf");
~~~

Việc tạo object Resource không đồng nghĩa đã mở stream và xác nhận nội dung. Test nên kiểm tra logic **preflight** trong ứng dụng.

### 14.1. Test bằng mock Resource

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;

@Test
void rejectsMissingResource() {
    Resource resource = mock(Resource.class);

    when(resource.exists()).thenReturn(false);

    IllegalArgumentException ex = assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.readPdf(resource)
    );

    assertEquals(
            "attachment resource is unavailable",
            ex.getMessage()
    );

    verify(resource).exists();
    verify(resource, never()).getInputStream();
}
~~~

Mock giúp test không phụ thuộc file nào thực sự tồn tại trong classpath.

### 14.2. Khi nào dùng ClassPathResource thật?

Có thể có một integration/resource packaging test xác nhận một template hoặc attachment mẫu thực sự được đóng gói vào classpath. Đây là câu hỏi khác: **file build có chứa đúng resource không?**

Unit test về nhánh xử lý resource thiếu nên dùng fake/mock, tránh phụ thuộc packaging của toàn project.

## 15. Kiểm thử Resource tồn tại nhưng không đọc được

Một resource có thể tồn tại nhưng không đọc được, hoặc permission bị từ chối.

~~~java
@Test
void rejectsUnreadableResource() {
    Resource resource = mock(Resource.class);

    when(resource.exists()).thenReturn(true);
    when(resource.isReadable()).thenReturn(false);

    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.readPdf(resource)
    );

    verify(resource, never()).getInputStream();
}
~~~

Nếu Resource trả isReadable=false, factory từ chối trước khi mở stream.

### 15.1. Không dùng permission của OS để test nhánh này

Một test đổi quyền file có thể không hoạt động giống nhau trên Windows, Linux, container hoặc khi chạy dưới quyền quản trị. Mockito cho phép mô phỏng đúng điều kiện mà không phụ thuộc hệ điều hành.

### 15.2. isReadable() không thay thế getInputStream()

Ngay cả khi isReadable() trả true, getInputStream() vẫn có thể ném IOException. Cần kiểm thử riêng nhánh này.

## 16. Kiểm thử IOException khi mở resource

Ví dụ resource cho biết có thể đọc, nhưng khi mở stream lại lỗi:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.UncheckedIOException;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;

@Test
void wrapsIOExceptionWhenStreamCannotBeOpened()
        throws Exception {

    Resource resource = mock(Resource.class);

    when(resource.exists()).thenReturn(true);
    when(resource.isReadable()).thenReturn(true);

    when(resource.getInputStream())
            .thenThrow(new IOException("simulated read failure"));

    UncheckedIOException ex = assertThrows(
            UncheckedIOException.class,
            () -> StatementMimeFactory.readPdf(resource)
    );

    assertInstanceOf(IOException.class, ex.getCause());
}
~~~

Đây là lỗi **đọc tài nguyên**, không phải SMTP 4xx/5xx. Retry cùng dữ liệu có thể hữu ích nếu nguồn chỉ gián đoạn tạm thời, nhưng nếu file bị xóa hoặc đường dẫn sai thì cần sửa dữ liệu/hệ thống.

### 16.1. Giữ nguyên cause

Bọc IOException trong UncheckedIOException giúp tầng gọi thấy một exception runtime có cause gốc. Không nên nuốt IOException và trả về byte[] rỗng vì khi đó email có thể được gửi với attachment sai.

### 16.2. Không log nội dung file khi đọc lỗi

Một IOException không yêu cầu dump attachment hoặc đường dẫn nhạy cảm. Nên log một định danh resource hợp lệ và loại lỗi theo chính sách.

## 17. Kiểm thử file rỗng

Một file có thể tồn tại và đọc được nhưng không có byte nào. Nếu nghiệp vụ yêu cầu PDF có nội dung, đó là đầu vào không hợp lệ.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;

@Test
void rejectsEmptyAttachment() {
    ByteArrayResource empty =
            new ByteArrayResource(new byte[0]);

    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.readPdf(empty)
    );
}
~~~

**ByteArrayResource** rất thuận tiện để kiểm thử nội dung mà không cần tạo file tạm.

### 17.1. Khi nào file rỗng có thể hợp lệ?

Tùy hợp đồng. Một attachment dạng placeholder có thể cho phép 0 byte trong một số hệ thống. Khi đó test phải phản ánh rule thật, không áp đặt cứng logic từ ví dụ PDF.

### 17.2. Empty khác missing

- **Missing:** resource không được tìm thấy hoặc không thể truy cập.
- **Empty:** resource tồn tại nhưng độ dài 0.

Phân biệt hai lỗi giúp thông báo vận hành rõ hơn và tránh sửa nhầm vấn đề.

## 18. Kiểm thử giới hạn kích thước resource

Một resource lớn bất thường có thể làm tiêu thụ bộ nhớ hoặc khiến SMTP provider từ chối vì kích thước.

Factory ví dụ có giới hạn một MiB:

~~~java
private static final int MAX_PDF_BYTES = 1_048_576;
~~~

Test:

~~~java
@Test
void rejectsAttachmentLargerThanLimit() {
    byte[] oversized = new byte[1_048_577];

    ByteArrayResource resource =
            new ByteArrayResource(oversized);

    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.readPdf(resource)
    );
}
~~~

### 18.1. Đọc có giới hạn giúp tránh memory spike

Trong bài toán file upload hoặc remote resource, không nên luôn gọi readAllBytes() khi chưa có kích thước tối đa. Một input lớn có thể làm tăng memory usage trong worker.

### 18.2. Kích thước MIME gửi đi có thể lớn hơn byte gốc

Attachment nhị phân thường được biểu diễn trong MIME bằng Base64, làm dữ liệu truyền đi lớn hơn byte ban đầu. Vì vậy, giới hạn ứng dụng trên file gốc cần chừa biên cho giới hạn message mà provider đặt ra.

### 18.3. Test đúng ngưỡng

Nếu hợp đồng cho phép tối đa 1_048_576 byte, nên có thêm trường hợp đúng bằng ngưỡng được chấp nhận và hơn ngưỡng một byte bị từ chối. Đây là boundary-value testing.

## 19. Kiểm thử filename không hợp lệ

Tên file dùng trong Content-Disposition là metadata người nhận nhìn thấy. Nếu nhận trực tiếp từ input, cần tránh những giá trị không phù hợp.

Ví dụ cần từ chối theo factory mẫu:

~~~text
null
""
" "
"../invoice.pdf"
"..\\invoice.pdf"
"folder/invoice.pdf"
"invoice.pdf\r\nBcc: someone@example.net"
"invoice.exe"
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@ValueSource(strings = {
        "../invoice.pdf",
        "..\\invoice.pdf",
        "folder/invoice.pdf",
        "invoice.pdf\r\nBcc: someone@example.net",
        "invoice.exe"
})
void rejectsUnsafeAttachmentFilename(String filename) {
    assertThrows(
            IllegalArgumentException.class,
            () -> StatementMimeFactory.validateFilename(filename)
    );
}
~~~

### 19.1. Filename không phải resource path

Không ghép filename do người dùng cung cấp trực tiếp thành path đọc file:

~~~java
// Không nên:
new FileSystemResource(
        uploadDirectory + "/" + userProvidedFilename
);
~~~

Điều đó có thể tạo lỗi **path traversal** hoặc truy cập file ngoài thư mục cho phép.

Trong thiết kế an toàn, nên dùng resource đã được hệ thống xác thực và truy xuất bằng internal ID; tên file hiển thị là dữ liệu riêng được kiểm soát.

### 19.2. Chỉ kiểm tra đuôi .pdf chưa đủ

Một filename kết thúc .pdf không chứng minh nội dung là PDF. Nếu cần kiểm tra định dạng, thực hiện validation bytes hoặc parser phù hợp ở tầng riêng và test các trường hợp giả mạo content type.

### 19.3. Tên file Unicode

Tên như **“Hóa đơn tháng 11.pdf”** có thể là yêu cầu hợp lệ. Validation nên bảo vệ khỏi control/path characters chứ không tự loại mọi ký tự tiếng Việt.

## 20. ByteArrayResource và stream có thể đọc lại

Jakarta Mail có thể cần mở stream của một MIME part nhiều hơn một lần, ví dụ trong quá trình tính/serialize nội dung. Vì thế, InputStreamSource dùng cho attachment cần có khả năng cung cấp dữ liệu ổn định theo contract của overload liên quan.

**ByteArrayResource** thường phù hợp khi bytes đã được đọc vào bộ nhớ:

~~~java
byte[] bytes = ...;

ByteArrayResource resource = new ByteArrayResource(bytes);

helper.addAttachment(
        "invoice.pdf",
        resource,
        "application/pdf"
);
~~~

### 20.1. Test có thể đọc stream nhiều lần

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;

@Test
void byteArrayResourceCanBeReadRepeatedly()
        throws Exception {

    byte[] expected = new byte[] {1, 2, 3, 4};
    ByteArrayResource resource =
            new ByteArrayResource(expected);

    byte[] first;
    byte[] second;

    try (InputStream in = resource.getInputStream()) {
        first = in.readAllBytes();
    }

    try (InputStream in = resource.getInputStream()) {
        second = in.readAllBytes();
    }

    assertArrayEquals(expected, first);
    assertArrayEquals(expected, second);
}
~~~

### 20.2. InputStreamResource cần thận trọng

**InputStreamResource** thường bao một stream đã mở và không đảm bảo có thể tạo lại một stream mới sau khi stream đó bị tiêu thụ. Một số overload của MimeMessageHelper còn có kiểm tra để tránh nguồn stream kiểu này vì Jakarta Mail có thể cần đọc lại.

Không viết test kỳ vọng InputStreamResource là repeatable trong mọi trường hợp. Nếu nguồn ban đầu chỉ cho đọc một lần, có thể đọc vào byte[] với kích thước giới hạn hoặc lưu trong một vùng tạm được quản lý và cung cấp InputStreamSource phù hợp.

### 20.3. Không cố retry một stream đã tiêu thụ

Nếu một lần gửi thất bại và worker muốn retry, không nên tái sử dụng một InputStream đã đọc hết. Cần một nguồn dữ liệu có thể tái mở hoặc một snapshot byte ổn định.

## 21. Kiểm thử MimeMessage thật mà không có SMTP

**JavaMailSenderImpl.createMimeMessage()** có thể tạo MimeMessage trong bộ nhớ mà không mở kết nối SMTP. Có thể dùng nó để kiểm tra kết quả dựng MIME.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class StatementMimeFactoryTest {

    @Test
    void buildsExpectedMimeWithoutSmtp() throws Exception {
        JavaMailSenderImpl sender =
                new JavaMailSenderImpl();

        StatementMimeFactory factory =
                new StatementMimeFactory(sender);

        byte[] pdfBytes =
                "PDF fixture".getBytes(StandardCharsets.UTF_8);

        StatementMailRequest request =
                new StatementMailRequest(
                        "an@example.net",
                        "Sao kê tháng 11",
                        "Xin chào Nguyễn An, xem file đính kèm.",
                        "statement.pdf",
                        new ByteArrayResource(pdfBytes)
                );

        MimeMessage message = factory.prepare(request);
        message.saveChanges();

        InternetAddress from =
                (InternetAddress) message.getFrom()[0];

        InternetAddress to =
                (InternetAddress) message.getRecipients(
                        Message.RecipientType.TO
                )[0];

        assertEquals(
                "billing@example.org",
                from.getAddress()
        );
        assertEquals(
                "an@example.net",
                to.getAddress()
        );
        assertEquals(
                "Sao kê tháng 11",
                message.getSubject()
        );

        MimeMultipart mixed =
                (MimeMultipart) message.getContent();

        assertEquals(2, mixed.getCount());

        assertTrue(
                mixed.getBodyPart(0).getContentType()
                        .toLowerCase(java.util.Locale.ROOT)
                        .startsWith("text/plain")
        );

        assertEquals(
                "statement.pdf",
                mixed.getBodyPart(1).getFileName()
        );

        byte[] actualPdf;

        try (InputStream in =
                     mixed.getBodyPart(1).getInputStream()) {
            actualPdf = in.readAllBytes();
        }

        assertArrayEquals(pdfBytes, actualPdf);
    }
}
~~~

### 21.1. Test đang xác minh điều gì?

- MimeMessage có From và To dự kiến.
- Subject giữ nội dung Unicode.
- Có body text và một attachment.
- Filename đúng.
- Attachment có bytes đúng sau khi lấy từ MIME part.

### 21.2. Test không kiểm tra SMTP server

Không có lời gọi **send(...)**. Vì vậy, test không cần host, username, password hoặc network.

### 21.3. MIME structure phụ thuộc mode của helper

Ví dụ cố ý dùng **MULTIPART_MODE_MIXED** để cấu trúc đơn giản cho test. Nếu ứng dụng dùng **MULTIPART_MODE_MIXED_RELATED** hoặc inline resources, MIME có thể lồng multipart. Khi đó assertion cần đi theo cấu trúc thực tế, không mặc định body part số 1 luôn là attachment.

## 22. Kiểm tra resource lỗi không gọi send bằng Mockito

Test kết hợp factory thật với JavaMailSender mock, nhằm xác nhận service fail-fast trước transport.

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;

@Test
void missingAttachmentDoesNotTriggerSend() {
    JavaMailSender sender = mock(JavaMailSender.class);

    StatementMimeFactory factory =
            new StatementMimeFactory(sender);

    StatementDeliveryService service =
            new StatementDeliveryService(factory, sender);

    Resource resource = mock(Resource.class);
    when(resource.exists()).thenReturn(false);

    StatementMailRequest request =
            new StatementMailRequest(
                    "an@example.net",
                    "Sao kê",
                    "Nội dung thông báo.",
                    "statement.pdf",
                    resource
            );

    assertThrows(
            IllegalArgumentException.class,
            () -> service.send(request)
    );

    verifyNoInteractions(sender);
}
~~~

Test minh họa trạng thái **không có kết nối, không có message gửi đi** do dữ liệu resource sai.

Nếu implementation tạo MimeMessage trước khi kiểm tra resource, test có thể chỉ cần:

~~~java
verify(sender, never()).send(any(MimeMessage.class));
~~~

Điều cần bảo vệ là **không có side effect gửi**, không phải luôn cấm tạo Java object.

## 23. Kiểm tra positive path qua ArgumentCaptor

Chỉ có negative tests không đủ. Nếu factory luôn ném exception, mọi test đầu vào xấu vẫn có thể pass.

Đối với dữ liệu hợp lệ, xác nhận service gửi chính message được dựng.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;

@Test
void validRequestPassesMimeMessageToSender()
        throws Exception {

    JavaMailSender sender = mock(JavaMailSender.class);

    MimeMessage message =
            new MimeMessage(Session.getInstance(new Properties()));

    when(sender.createMimeMessage()).thenReturn(message);

    StatementMimeFactory factory =
            new StatementMimeFactory(sender);

    StatementDeliveryService service =
            new StatementDeliveryService(factory, sender);

    StatementMailRequest request =
            new StatementMailRequest(
                    "an@example.net",
                    "Sao kê",
                    "Vui lòng xem báo cáo.",
                    "statement.pdf",
                    new ByteArrayResource(new byte[] {1, 2, 3})
            );

    service.send(request);

    ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

    verify(sender, times(1)).send(captor.capture());

    assertEquals("Sao kê", captor.getValue().getSubject());

    verify(sender, times(1)).createMimeMessage();
    verifyNoMoreInteractions(sender);
}
~~~

Mockito chỉ mô phỏng ranh giới JavaMailSender. Nó không gửi email thật.

### 23.1. Vì sao captor hữu ích?

Nó cho thấy service không chỉ gọi send một cách chung chung mà truyền một MimeMessage có dữ liệu mong đợi.

### 23.2. Không cần assert mọi MIME part ở service test

MIME factory test đã kiểm tra nội dung chi tiết. Service test chỉ cần xác nhận đúng đối tượng được tạo và gửi đúng số lần, để tránh lặp assertion không cần thiết.

## 24. Lỗi Resource có thể phát sinh khi serialize hoặc send

Không phải mọi mã nguồn đều thực hiện preflight read như factory ví dụ.

~~~text
helper.addAttachment(resource)
       |
       v
MimeMessage giữ DataHandler/DataSource
       |
       v
message.writeTo(...) hoặc transport send
       |
       v
getInputStream() được gọi
       |
       +-- IOException
~~~

Do đó, một test chỉ gọi addAttachment rồi assert không có exception **không bảo đảm attachment có thể gửi**.

### 24.1. Nếu muốn phát hiện lỗi trước SMTP

Có hai hướng:

1. **Preflight resource:** mở và kiểm tra stream trước send, như factory ví dụ.
2. **Serialize MIME vào buffer test:** gọi message.writeTo(OutputStream) trong kiểm thử để buộc đọc dữ liệu mà không kết nối SMTP.

Ví dụ chỉ dành cho MIME nhỏ trong test:

~~~java
ByteArrayOutputStream out =
        new ByteArrayOutputStream();

message.saveChanges();
message.writeTo(out);

assertTrue(out.size() > 0);
~~~

Việc serialize có thể làm lộ lỗi stream ở thời điểm muộn. Với attachment lớn, không nên xây dựng một production preflight bằng cách serialize toàn bộ email vào bộ nhớ không giới hạn.

### 24.2. Phân biệt MIME serialization với SMTP transport

Một message serialize được vào buffer chưa chắc sẽ được SMTP provider chấp nhận. Ngược lại, resource lỗi ở giai đoạn serialize chưa phải SMTP reply 4xx/5xx.

### 24.3. Một lỗi có thể bị bọc trong exception khác

IOException từ Resource có thể được bọc thành MessagingException hoặc Spring MailException khi đi qua các tầng. Khi viết test của factory tự đọc stream, bạn có thể assert UncheckedIOException trực tiếp. Khi test transport, cần đọc cause chain và không giả định exception ngoài cùng luôn giống nhau ở mọi phiên bản.

## 25. Kiểm thử inline resource

Inline image dùng cơ chế tương tự attachment nhưng có thêm **Content-ID** để HTML tham chiếu.

Ví dụ:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setText(
        "<html><body><img src=\"cid:companyLogo\"></body></html>",
        true
);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Các trường hợp test:

- Resource ảnh không tồn tại.
- Resource mở stream thất bại.
- Image bytes rỗng nếu bị cấm.
- MIME type khai báo không phù hợp.
- Content-ID dùng trong HTML không trùng ID được add.
- Resource không thể đọc lại.
- Ảnh vượt giới hạn kích thước.
- Inline resource bị gắn nhầm thành attachment hoặc ngược lại.

### 25.1. Content-ID không phải filename

HTML tham chiếu **cid:companyLogo**. Nó phải khớp với Content-ID của part inline, không phụ thuộc vào tên file trên classpath.

### 25.2. Thứ tự thêm inline resource

Khi dùng MimeMessageHelper, thông thường cần thiết lập body HTML trước rồi mới addInline để tránh vấn đề tương thích ở một số mail client.

### 25.3. Không dùng inline Resource để đọc URL tùy ý

Một URL do người dùng cung cấp có thể dẫn đến SSRF hoặc truy cập hạ tầng nội bộ. Nếu ứng dụng hỗ trợ image từ URL, cần cơ chế tải riêng với allowlist, timeout, giới hạn byte và chính sách mạng; unit test phải bao gồm URL bị từ chối.

## 26. Test lỗi do path traversal và nguồn không đáng tin

Một request có thể chứa:

~~~text
attachmentPath = ../../private/secret.pdf
~~~

Nếu hệ thống dùng path này để mở FileSystemResource mà không có ràng buộc, ứng dụng có thể đọc file ngoài phạm vi được phép.

Kiến trúc tốt hơn:

~~~text
Request attachmentId
        |
        v
Authorization check
        |
        v
Lookup trusted metadata
        |
        v
Resolve resource in approved storage
        |
        v
Read with size/type policy
~~~

Unit test nên kiểm tra:

- Attachment ID người dùng không được quyền truy cập → bị từ chối.
- Path vượt root được phép → bị từ chối.
- URL tới địa chỉ nội bộ/cấm → bị từ chối nếu nguồn là URL.
- Filename chứa separator → bị từ chối theo policy.
- Nội dung file rỗng/quá lớn → bị từ chối.
- Resource không tồn tại → báo lỗi, không gửi mail.

Không dùng validation của **attachmentFilename** như giải pháp duy nhất nếu code còn nhận một **resource path** khác. Filename hiển thị và nơi đọc file là hai dữ liệu cần kiểm soát riêng.

## 27. Resource là nội dung byte, không phải chuỗi UTF-8 bắt buộc

PDF, PNG và các binary attachments phải được xử lý như byte.

Không làm:

~~~java
String text = new String(
        pdfBytes,
        StandardCharsets.UTF_8
);

byte[] converted = text.getBytes(
        StandardCharsets.UTF_8
);
~~~

Việc giải mã file nhị phân thành text có thể làm hỏng dữ liệu.

Đúng:

~~~java
helper.addAttachment(
        "statement.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Với CSV hoặc TXT, charset có ý nghĩa khi chuyển nội dung text thành byte. Một test có thể kiểm tra UTF-8 nếu đó là hợp đồng của attachment text.

### 27.1. MIME type là một phần hợp đồng

Test có thể xác nhận attachment được khai báo **application/pdf** khi dùng PDF, và **image/png** khi dùng PNG. Nhưng khai báo MIME type không chứng minh file có định dạng đó.

### 27.2. Dữ liệu bị cắt cụt cũng cần kiểm tra

Với tài liệu có checksum, độ dài hoặc signature hợp lệ, có thể test bảo toàn bytes/size trước khi gửi. Đừng chỉ assert rằng InputStream trả về ít nhất một byte.

## 28. Test lỗi ứng dụng có cần mock SMTP không?

Đối với dữ liệu địa chỉ sai, resource không tồn tại hoặc stream IOException, **không cần SMTP mock server**. Unit test có thể dùng:

- JUnit 5.
- Mockito mock Resource.
- ByteArrayResource.
- JavaMailSender mock.
- JavaMailSenderImpl để dựng MimeMessage trong bộ nhớ.

SMTP capture server hoặc fake transport hữu ích ở kiểm thử tích hợp, khi cần biết:

- Message có thể được serialize và gửi qua transport.
- SMTP trả 550 tại RCPT TO.
- AUTH/TLS được cấu hình phù hợp.
- Provider có partial-recipient acceptance.
- Connection có thể timeout sau DATA.

Không nhầm **địa chỉ sai cú pháp** (unit test) với **mailbox không tồn tại** (kết quả từ server/provider có thể đến sau gửi).

## 29. Phân loại lỗi để chọn chính sách retry

Một hệ thống dùng outbox hoặc worker có thể phân loại:

| Lỗi | Nhóm | Hành động thường hợp lý |
| --- | --- | --- |
| To null hoặc blank | Input invalid | Sửa dữ liệu, không retry nguyên trạng |
| AddressException khi chuẩn bị | Input/MIME invalid | Kiểm tra nguồn, không retry mù |
| Subject có CR/LF sai hợp đồng | Header input invalid | Từ chối và sửa |
| Attachment path sai | Resource config/data | Sửa path, không retry cùng dữ liệu |
| File không tồn tại | Resource unavailable | Kiểm tra nguồn, retry nếu có thể xuất hiện về sau theo hợp đồng |
| Permission denied | Resource access | Sửa quyền, không retry dồn dập |
| Stream tạm thời đứt | Resource I/O | Có thể retry có giới hạn nếu nguồn có thể phục hồi |
| File rỗng/truncated | Invalid content | Sửa/đối soát file |
| File quá lớn | Policy violation | Không retry với cùng bytes |
| AUTH 535 | SMTP account/config | Dừng retry mù, sửa credentials |
| SMTP 421/450 tạm thời | Transport transient | Backoff và retry có giới hạn |
| Timeout sau DATA | Unknown outcome | Cân nhắc gửi trùng và đối soát |

Không gom mọi IllegalArgumentException, UncheckedIOException, MessagingException và MailException thành một nhóm **retryable**.

### 29.1. Validation fail-fast giảm lãng phí retry

Nếu một outbox job chứa đường dẫn file sai, việc thử gửi 100 lần không tự tạo ra file. Dấu hiệu là lỗi cấu hình hoặc dữ liệu chưa hợp lệ, không phải SMTP tạm thời.

### 29.2. Resource biến mất sau commit

Nếu outbox chỉ lưu path đến một file tạm, file có thể bị dọn trước khi worker chạy. Cần quyết định lưu snapshot bytes, storage object bền vững hoặc một tham chiếu có retention đủ dài.

Unit test kiểm tra file thiếu giúp phát hiện nhánh lỗi, nhưng thiết kế retention/storage mới giải quyết nguyên nhân hệ thống.

## 30. Đảm bảo test không rò rỉ dữ liệu

Để kiểm thử lỗi:

- Dùng recipient ở domain ví dụ như example.net.
- Dùng PDF/PNG bytes giả, không dùng tài liệu khách thật.
- Không chứa mật khẩu hoặc token thật trong fixture.
- Không log toàn bộ MIME message chỉ để quan sát lỗi.
- Không đưa đường dẫn chứa dữ liệu nhạy cảm ra log rộng quyền.
- Không gọi URL thật hoặc SMTP thật khi không cần.
- Nếu dùng một file tạm, đảm bảo xóa theo quy trình test và không tạo bản sao không cần thiết.

### 30.1. Exception message nên đủ hữu ích nhưng không chứa secret

Ví dụ hợp lý:

~~~text
attachment resource is unavailable
~~~

Thay vì:

~~~text
Cannot open C:\private\users\customer-42\statement.pdf
~~~

nếu đường dẫn thật là dữ liệu cần bảo vệ. Có thể lưu một resource reference nội bộ, không phải raw path.

### 30.2. Không in raw recipient trong log validation

Trong nhiều hệ thống, email là dữ liệu cá nhân. Một unit test không cần chứng minh exception message phải chứa email thật; nên kiểm tra loại lỗi và trường bị từ chối.

## 31. Ma trận test đầy đủ cho địa chỉ và resource

| Nhóm | Input | Kết quả mong đợi |
| --- | --- | --- |
| Recipient | null | Reject, no send |
| Recipient | empty/blank | Reject, no send |
| Recipient | thiếu local-part hoặc domain | Reject theo policy |
| Recipient | nhiều địa chỉ trong một trường | Reject hoặc xử lý theo hợp đồng |
| Recipient | control character/CRLF | Reject, no send |
| Recipient | địa chỉ có Unicode được hỗ trợ | Accept theo policy ứng dụng |
| From/Reply-To | cấu hình sai | Reject trước send |
| CC/BCC | có phần tử không hợp lệ | Không âm thầm gửi cho phần còn lại |
| Subject | blank | Reject |
| Subject | có CR/LF | Reject |
| Body | null hoặc blank | Reject nếu hợp đồng yêu cầu text |
| Resource | null | Reject |
| Resource | exists=false | Reject |
| Resource | isReadable=false | Reject |
| Resource | getInputStream() ném IOException | Propagate/wrap, no send |
| Resource | 0 byte | Reject nếu nội dung bắt buộc |
| Resource | vừa bằng giới hạn | Accept |
| Resource | vượt giới hạn 1 byte | Reject |
| Resource | InputStream không lặp lại | Không đưa thẳng vào contract yêu cầu reread |
| Resource | byte hợp lệ | MimeMessage chứa đúng bytes |
| Filename | path separator hoặc CRLF | Reject |
| Filename | Unicode hợp lệ | Accept nếu product hỗ trợ |
| Content type | khác loại cho phép | Reject/điều chỉnh theo policy |
| Inline image | CID không khớp HTML | Phát hiện bằng test cấu trúc/nội dung |
| Service | input invalid | Không gọi JavaMailSender.send |
| Service | input valid | Gọi send đúng một lần với message mong đợi |

Ma trận này là tài liệu thiết kế **test input và expected behavior**. Những chính sách như file rỗng có hợp lệ hay không, giới hạn byte, hỗ trợ IDN/SMTPUTF8 phải được lựa chọn theo nhu cầu ứng dụng.

## 32. Anti-pattern thường gặp

### 32.1. Chỉ assert message != null

~~~java
assertNotNull(message);
~~~

Một message có recipient sai, Subject rỗng hoặc attachment thiếu vẫn có thể khác null. Hãy assert trường cụ thể hoặc test fail-fast.

### 32.2. Coi setTo luôn xác nhận địa chỉ

**SimpleMailMessage.setTo(...)** chủ yếu lưu dữ liệu. Không dựa vào nó để kiểm tra mailbox tồn tại hoặc mọi lỗi cú pháp.

### 32.3. Chỉ gọi addAttachment rồi kết luận resource đọc được

Việc đọc stream có thể bị trì hoãn. Nếu cần chắc chắn trước send, kiểm tra resource preflight hoặc serialize trong test.

### 32.4. Retry mọi IOException

File path sai hoặc permission denied ổn định sẽ không được sửa chỉ bằng retry nhanh.

### 32.5. Dùng InputStreamResource đã bị tiêu thụ

Một nguồn chỉ đọc một lần có thể thất bại khi Jakarta Mail đọc lại. Hãy dùng ByteArrayResource hoặc nguồn có khả năng mở stream mới.

### 32.6. Dùng file thật trong mọi unit test

Test phụ thuộc filesystem sẽ chậm, khó di chuyển và dễ hỏng do môi trường. Ưu tiên mock Resource và ByteArrayResource cho unit test.

### 32.7. Bỏ qua null trong array recipients

Một danh sách có ba recipient, trong đó một phần tử null, cần được xử lý theo policy rõ ràng. Không âm thầm gửi phần còn lại nếu nghiệp vụ không cho phép.

### 32.8. Dùng display filename làm filesystem path

Đây là nguy cơ path traversal. Phải tách tên hiển thị và resource reference nội bộ đã được cấp quyền.

### 32.9. Mock tất cả, kể cả object cần kiểm tra

Nếu muốn biết MimeMessage có đúng địa chỉ và attachment, hãy dựng MimeMessage thật trong bộ nhớ. Chỉ mock ranh giới cần cô lập.

### 32.10. Chạy SMTP thật trong unit test

Điều đó khiến test phụ thuộc network, account, provider và có thể vô tình gửi tới người dùng. Unit test dữ liệu nên độc lập SMTP.

## 33. Câu hỏi thường gặp

**1. Vì sao kiểm thử lỗi địa chỉ quan trọng dù SMTP sẽ từ chối?**

Vì phát hiện lỗi sớm giúp tránh tạo side effect, giảm retry vô ích và cung cấp thông báo rõ ràng. SMTP có thể từ chối vì nhiều nguyên nhân khác nhau, không phải một validator ứng dụng.

**2. SimpleMailMessage.setTo("bad-address") có luôn ném exception không?**

Không nên giả định như vậy. SimpleMailMessage là một holder dữ liệu plain text. Kiểm tra cú pháp nên ở tầng ứng dụng hoặc transport phù hợp.

**3. InternetAddress.validate() có biết mailbox tồn tại không?**

Không. Nó chỉ kiểm tra cú pháp theo API, không xác thực người dùng sở hữu mailbox hay provider sẽ nhận thư.

**4. Khi nào dùng MimeMessageHelper thay SimpleMailMessage?**

Khi cần HTML, multipart, attachment, inline resource hoặc các tính năng MIME phong phú. SimpleMailMessage phù hợp email văn bản thuần.

**5. Vì sao addAttachment không chắc ném lỗi file thiếu ngay?**

Một số luồng Jakarta Mail lưu nguồn dữ liệu vào MIME part và mở stream khi serialize/send. Nếu muốn fail-fast, hãy đọc và kiểm tra trước.

**6. ByteArrayResource có ưu điểm gì cho unit test?**

Nó chứa bytes trong bộ nhớ, không phụ thuộc file thật và có thể cung cấp InputStream mới để đọc lại.

**7. InputStreamResource có nên dùng cho attachment không?**

Cần thận trọng vì một stream đã mở thường chỉ dùng được một lần; một số helper overload còn từ chối nguồn không thể mở lại. Nếu cần đọc lặp, sử dụng nguồn repeatable.

**8. Khi resource.exists() trả true, có thể bỏ thử getInputStream() không?**

Không. Resource có thể vẫn không đọc được do permission, mạng hoặc thay đổi trạng thái. Cần test lỗi mở/đọc stream.

**9. Có nên test file rỗng là lỗi không?**

Nếu hợp đồng yêu cầu nội dung không rỗng thì có. Nếu sản phẩm cho phép file 0 byte, expected behavior phải khác.

**10. Có cần kiểm tra giới hạn kích thước không?**

Có nếu hệ thống có giới hạn tài nguyên hoặc provider. Test ở ngưỡng bằng limit và vượt limit một byte là hữu ích.

**11. Có nên kiểm tra file extension .pdf không?**

Có thể là một rule hiển thị, nhưng extension không xác nhận nội dung là PDF. Cần validation content riêng nếu nghiệp vụ yêu cầu.

**12. Vì sao cần test CR/LF trong Subject và filename?**

Để không đưa control character ngoài hợp đồng vào các trường header và tránh nguy cơ injection hoặc nội dung header sai.

**13. Unit test MimeMessage có cần SMTP account không?**

Không. Có thể dùng JavaMailSenderImpl.createMimeMessage() hoặc new MimeMessage(Session.getInstance(...)) để dựng message trong bộ nhớ.

**14. Làm sao biết service không gửi khi resource thiếu?**

Mock JavaMailSender, gọi service với Resource thiếu, assert exception và verify sender.send không được gọi.

**15. Có thể giả lập lỗi permission mà không đổi quyền file thật không?**

Có. Mock Resource.isReadable() trả false hoặc Resource.getInputStream() ném IOException.

**16. Một attachment đọc được một lần có đủ không?**

Không chắc. MIME provider có thể đọc lại. Cần nguồn repeatable hoặc snapshot bytes khi thiết kế yêu cầu.

**17. Test serialize MIME có thay thế integration test SMTP không?**

Không. Nó kiểm tra việc tạo/serialize message, không xác minh authentication, TLS, RCPT TO hoặc phản hồi SMTP server.

**18. Mailbox không tồn tại có kiểm thử đơn vị được không?**

Có thể kiểm thử **logic xử lý** khi provider trả một tín hiệu user unknown bằng fake, nhưng không thể xác nhận một mailbox thật tồn tại chỉ bằng unit test của địa chỉ.

**19. Nếu attachment bị thay đổi giữa kiểm tra và send thì sao?**

Đó là vấn đề thời điểm đọc và độ bền của nguồn. Snapshot bytes hoặc storage object có version/checksum có thể giúp giữ nội dung nhất quán.

**20. Có nên retry khi resource bị lỗi?**

Tùy nguyên nhân. Lỗi tạm thời có thể retry có giới hạn; file mất, path sai, nội dung rỗng hoặc quá lớn thường cần sửa dữ liệu/cấu hình trước.

## 34. Ghi nhớ về kiểm tra lỗi khi địa chỉ hoặc resource không hợp lệ

**Kiểm thử lỗi địa chỉ và resource là kiểm thử ranh giới đầu vào trước khi email được gửi.** Trong Spring Framework Mail, không nên dựa vào SimpleMailMessage setters để xác minh mailbox; hãy định nghĩa chính sách địa chỉ rõ ràng, kiểm tra null/blank/cú pháp, phân biệt một recipient với danh sách, kiểm soát From/To/Reply-To/CC/BCC và từ chối control characters ở header.

Đối với attachment hoặc inline resource, **Resource tồn tại chưa có nghĩa có thể đọc được**. File có thể thiếu, không có quyền, rỗng, quá lớn hoặc chỉ hỗ trợ một InputStream đã bị tiêu thụ. Hãy test riêng exists, isReadable, getInputStream, IOException, byte length, filename, content type và khả năng đọc lại. Khi cần fail-fast, đọc có giới hạn và dùng ByteArrayResource hoặc nguồn repeatable trước khi giao MIME cho transport.

Sử dụng **JUnit 5, Mockito, fake Resource, ByteArrayResource và MimeMessage thật trong bộ nhớ** để kiểm tra cả nhánh hợp lệ và không hợp lệ. Negative test cần xác nhận **không gọi JavaMailSender.send(...)** khi dữ liệu bị từ chối; positive test cần xác nhận message được dựng đúng và chuyển cho sender đúng số lần. Không biến những test này thành SMTP integration test, không retry mù lỗi dữ liệu cố định, và không dùng dữ liệu người dùng thật trong fixture.

**Chuẩn bị message thành công khác với SMTP chấp nhận message, và SMTP chấp nhận khác với người nhận đã nhận/đọc email.** Khi tách các ranh giới này, test trở nên nhanh, xác định được và phát hiện lỗi dữ liệu trước khi phát sinh side effect gửi thư.
