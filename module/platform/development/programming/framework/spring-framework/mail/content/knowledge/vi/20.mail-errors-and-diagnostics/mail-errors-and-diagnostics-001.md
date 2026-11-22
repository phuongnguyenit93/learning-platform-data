# MailParseException khi tạo message không hợp lệ

## 1. Bối cảnh: tạo email thành công không chỉ là tạo một chuỗi văn bản

Trong **Spring Framework Mail**, một email có thể gồm người gửi, người nhận, tiêu đề, nội dung text/plain, HTML, ảnh inline và attachment. Để gửi qua SMTP, các thành phần này phải được biểu diễn theo định dạng **MIME (Multipurpose Internet Mail Extensions)** và các quy tắc của Internet Message Format.

Ở mức đơn giản, ứng dụng có thể gửi `SimpleMailMessage`. Khi cần HTML, Unicode, nhiều body part hoặc attachment, ứng dụng thường dùng `JavaMailSender`, `MimeMessage` và `MimeMessageHelper`.

~~~text
Dữ liệu ứng dụng
   |
   v
Validation / xây dựng mail model
   |
   v
MimeMessageHelper / MimeMessage
   |
   v
Chuẩn bị và mã hóa MIME
   |
   v
JavaMailSender.send(...)
   |
   v
SMTP server
~~~

Vấn đề là **lỗi có thể xuất hiện ở nhiều giai đoạn khác nhau**:

- Dữ liệu đầu vào không hợp lệ, ví dụ địa chỉ email thiếu phần domain.
- Header của message đã được đọc từ nguồn bên ngoài có định dạng không đúng.
- Dữ liệu MIME thô bị cắt cụt hoặc cấu trúc multipart không nhất quán.
- Bộ mã ký tự hoặc Content-Transfer-Encoding của một MIME part không phù hợp.
- `MimeMessagePreparator` thất bại khi đặt người nhận, nội dung hoặc attachment.
- MIME được tạo thành công nhưng SMTP từ chối hoặc kết nối gặp sự cố.

Tên exception **`MailParseException`** dễ khiến người đọc nghĩ rằng cứ có bất kỳ thông tin email nào sai thì Spring luôn ném exception này. Thực tế, nó chủ yếu liên quan đến **không thể phân tích nội dung mail message** ở ranh giới đọc/parse, và cần được phân biệt với lỗi **chuẩn bị nội dung** hoặc lỗi **gửi qua SMTP**.

**Ý chính:** Phải xác định đang thất bại khi *đọc MIME*, *chuẩn bị MimeMessage* hay *submit lên SMTP* rồi mới chọn cách sửa và retry. Không nên coi mọi lỗi tạo email là lỗi kết nối mail server.

## 2. MailParseException là gì?

`org.springframework.mail.MailParseException` là một exception thuộc hệ thống Spring Mail, biểu thị việc một mail message **không thể được parse** theo cách Spring đang thực hiện. Nó thuộc nhóm `MailException` (runtime exception).

Tình huống điển hình là ứng dụng nhận một email ở dạng **raw RFC 822/MIME bytes** từ file, message store hoặc hệ thống khác, rồi cố chuyển dữ liệu đó thành `MimeMessage`.

Ví dụ luồng:

~~~text
File .eml / raw MIME InputStream
              |
              v
JavaMailSender.createMimeMessage(InputStream)
              |
              +-- parse thành MimeMessage thành công
              |
              +-- lỗi trong quá trình parse
                         |
                         v
                   MailParseException
~~~

Với Spring JavaMailSender, API thường thấy:

~~~java
MimeMessage message = mailSender.createMimeMessage();
~~~

Tạo một message rỗng để ứng dụng tự điền nội dung. Cách khác:

~~~java
MimeMessage restored =
        mailSender.createMimeMessage(rawMimeInputStream);
~~~

Cách thứ hai phải **đọc và parse dữ liệu MIME đã có**. Nếu nội dung thô gây lỗi parse, `MailParseException` là exception cần chú ý.

Không có quy tắc rằng mọi message sai đều dẫn đến MailParseException ngay khi constructor chạy. Parser MIME có thể chấp nhận một số cấu trúc thiếu chuẩn để tương thích email thực tế; một số lỗi chỉ bộc lộ khi truy cập header/body part hoặc serialize về sau. Vì thế cần kiểm tra cả exception chain, thời điểm lỗi và dữ liệu đầu vào.

## 3. Phân biệt các exception quan trọng trong Spring Mail

Spring cung cấp nhiều loại exception để phân loại vấn đề:

| Exception | Bản chất thường gặp | Giai đoạn cần điều tra |
|---|---|---|
| `MailParseException` | Không thể parse mail message | Đọc raw MIME / tạo message từ dữ liệu đã có |
| `MailPreparationException` | Lỗi khi thực thi công việc chuẩn bị message | `MimeMessagePreparator`, template, helper hoặc dữ liệu |
| `MailAuthenticationException` | Không xác thực được với mail server | SMTP AUTH / credential |
| `MailSendException` | Lỗi gửi message, có thể nhiều message hoặc recipient | SMTP transport, server response, kết nối |
| `MailException` | Nhóm lỗi chung của Spring Mail | Cần xem subtype và nguyên nhân gốc |

Trong Jakarta Mail, một số exception khác cũng thường xuất hiện:

| Exception bên dưới | Ví dụ |
|---|---|
| `jakarta.mail.MessagingException` | Lỗi chuẩn bị/đọc MIME hoặc thao tác message |
| `jakarta.mail.internet.AddressException` | Địa chỉ email có cú pháp không hợp lệ |
| `jakarta.mail.internet.ParseException` | Một cú pháp MIME/header không được parser chấp nhận |
| `java.io.IOException` | Lỗi đọc stream hoặc resource khi xử lý nội dung |

**Không nên đồng nhất MailParseException với AddressException.** Một địa chỉ người nhận sai cú pháp có thể gây `AddressException` trong quá trình gọi `MimeMessageHelper.setTo(...)`; nếu lỗi đó xảy ra bên trong một `MimeMessagePreparator` được truyền cho `JavaMailSender.send(...)`, Spring có thể bọc nó bằng `MailPreparationException`. Đường đi exception cụ thể phụ thuộc overload API và lúc lỗi phát sinh.

### Ba tình huống dễ nhầm

**Tình huống A — Parse dữ liệu MIME có sẵn**

~~~java
MimeMessage message = mailSender.createMimeMessage(inputStream);
~~~

Đọc raw MIME từ `inputStream`. Nếu thư viện không parse được, hướng điều tra là dữ liệu nguồn, header, boundary, stream và các phần MIME.

**Tình huống B — Tạo message mới bằng helper**

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");
helper.setTo(recipient);
helper.setText(html, true);
~~~

Khi `recipient` hoặc một tham số khác sai, các API `MimeMessageHelper` có thể ném `MessagingException` hoặc subtype liên quan. Đây là vấn đề **xây dựng message**; không được mặc định kết luận sẽ luôn là `MailParseException`.

**Tình huống C — Gửi message qua SMTP**

~~~java
mailSender.send(message);
~~~

Nếu message đã tạo hợp lệ nhưng server SMTP không kết nối được hoặc từ chối yêu cầu, hướng điều tra là `MailSendException`, `MailAuthenticationException`, provider policy và phản hồi SMTP. Không sửa MIME parser khi nguyên nhân là sai credential.

## 4. Nắm rõ cấu trúc MIME để hiểu lỗi parse

Một raw MIME message hợp lệ về mặt cấu trúc thường có header, một dòng trống rồi đến body:

~~~mime
From: noreply@example.test
To: customer@example.test
Subject: Confirmation
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o, =C4=91=C6=A1n h=C3=A0ng =C4=91=C3=A3 x=C3=A1c nh=E1=BA=ADn.
~~~

Header cho biết body là text/plain UTF-8 được biểu diễn bằng quoted-printable. Mail client/Jakarta Mail phải diễn giải các header liên quan rồi decode phần body.

Một message có attachment có thể gồm các MIME part phân tách bằng boundary:

~~~mime
From: noreply@example.test
To: customer@example.test
Subject: Receipt
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mail-boundary-123"

--mail-boundary-123
Content-Type: text/plain; charset=UTF-8

Your receipt is attached.
--mail-boundary-123
Content-Type: application/pdf; name="receipt.pdf"
Content-Disposition: attachment; filename="receipt.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK...
--mail-boundary-123--
~~~

Những yếu tố cần khớp:

1. Boundary khai báo trong `Content-Type` phải tương ứng với các delimiter trong body.
2. Mỗi MIME part có header riêng và phần nội dung.
3. Có dòng trống phân cách header với body/part body.
4. Các trường như Content-Type, charset và transfer encoding phải mô tả đúng dữ liệu.
5. Message cần được đọc đầy đủ, tránh stream bị cắt giữa chừng.

Một raw message không nhất thiết phải có mọi header thường thấy để parser tiếp nhận; Jakarta Mail có thể chấp nhận một số dữ liệu không chuẩn. Tuy nhiên, header/body sai có thể làm parse thất bại, làm body part bị diễn giải nhầm, hoặc chỉ gây lỗi lúc ứng dụng truy cập nội dung.

## 5. Các nguyên nhân thường gặp khi gặp MailParseException

| Nhóm nguyên nhân | Dấu hiệu | Điều cần kiểm tra |
|---|---|---|
| Input stream hỏng hoặc đọc thất bại | IOException, stream bị đóng sớm | Nguồn file, stream lifecycle, filesystem/network |
| Raw MIME bị cắt | Thiếu phần body hoặc boundary cuối | Kích thước thực đọc so với kích thước nguồn |
| Header có cú pháp không chuẩn | Thông tin Content-Type hoặc tham số MIME không parse được | Header thô, ký tự điều khiển, dấu nháy |
| Multipart boundary không nhất quán | Part bị gộp, thiếu part hoặc parse lỗi | Giá trị boundary và các dòng delimiter |
| Content-Transfer-Encoding sai | Body decode lỗi hoặc dữ liệu hỏng | Base64, quoted-printable, raw bytes |
| Charset không phù hợp | Nội dung tiếng Việt sai dấu | Content-Type charset, byte encoding gốc |
| Part lồng nhau có cấu trúc lạ | Lỗi xuất hiện khi duyệt body | Multipart/alternative, related, mixed |
| Dữ liệu header có CR/LF không mong muốn | Header bị tách dòng ngoài ý định | Nguồn header và đầu vào không tin cậy |
| File .eml không thực sự chứa raw MIME | Parser gặp nội dung định dạng khác | Loại file, BOM, nội dung đầu tệp |
| Parser gặp giới hạn/khác biệt phiên bản | Hành vi thay đổi giữa môi trường | Jakarta Mail implementation, strictness properties |

Không phải mọi nguyên nhân trong bảng sẽ **luôn** tạo MailParseException. Chẳng hạn charset sai có thể chỉ làm nội dung bị lỗi dấu nhưng việc parse vẫn thành công; attachment sai Base64 có thể chỉ lỗi khi đọc data stream. Cần dựa trên stack trace và giai đoạn thực sự xảy ra lỗi.

### Ví dụ raw MIME bị cắt cụt

~~~mime
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="b-abc"

--b-abc
Content-Type: text/plain

Hello
--b-abc
Content-Type: application/pdf
Content-Transfer-Encoding: base64

JVBERi0xLjQK...
~~~

Message này thiếu dấu đóng `--b-abc--`. Tùy parser, nó có thể bị từ chối, vẫn parse nhưng thiếu nội dung, hoặc báo lỗi khi duyệt/serialize. Vì vậy **không chỉ dựa vào việc không có exception** để khẳng định dữ liệu MIME thô hoàn toàn hợp lệ.

## 6. Tái hiện lỗi theo ranh giới parse dữ liệu MIME

Giả sử ứng dụng nhận file `.eml` từ một hệ thống khác và cần nạp lại trước khi gửi hoặc phân tích:

~~~java
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.mail.MailParseException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class RawMailImportService {
    private final JavaMailSender sender;

    public RawMailImportService(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage readRawMessage(Resource resource)
            throws IOException {
        try (InputStream input = resource.getInputStream()) {
            return sender.createMimeMessage(input);
        } catch (MailParseException ex) {
            // Dữ liệu email thô không được parser chấp nhận.
            // Ghi loại lỗi và ID bản ghi ở lớp gọi;
            // không log nguyên body mail.
            throw ex;
        }
    }
}
~~~

`JavaMailSender.createMimeMessage(InputStream)` nhận một stream chứa raw MIME và có thể biểu diễn lỗi parse bằng Spring `MailParseException`. Với code trên, nguồn `Resource` có thể là file nội bộ, object storage adapter hoặc một nguồn lưu trữ khác mà ứng dụng kiểm soát.

**Lưu ý vòng đời stream:** Hàm trên đóng input stream sau khi tạo `MimeMessage`. Tùy implementation và cách đọc part, nội dung có thể được buffer hoặc parse lười (lazy parsing). Khi tích hợp với nguồn stream đặc biệt, cần bảo đảm message có thể tiếp tục đọc được nội dung theo cách thư viện hỗ trợ; không mặc định mọi InputStream đều có vòng đời giống nhau.

### Kiểm tra ngữ cảnh lỗi

Khi exception xảy ra, cần xác định:

- ID tệp hoặc outbox event đang xử lý.
- Dữ liệu MIME được lấy từ đâu, phiên bản pipeline nào tạo ra nó.
- Số byte dự kiến và số byte thực đọc.
- Phase đang parse header, duyệt part hay decode body.
- Exception type gốc và nested cause.
- Có tình trạng retry nguồn đọc file hoặc download một phần hay không.

Không nên in toàn bộ MIME message trong production log vì nó có thể chứa địa chỉ email, token, nội dung riêng tư và file đính kèm.
## 7. Lỗi tạo message mới không nhất thiết là MailParseException

Một ứng dụng thông thường không nạp raw MIME mà tạo email từ dữ liệu nghiệp vụ:

~~~java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mimeMessage, true, "UTF-8");
helper.setTo(customerEmail);
helper.setSubject("Thông báo đơn hàng");
helper.setText(html, true);
~~~

Ở đây không có bước “parse từ `.eml`”; `MimeMessage` bắt đầu ở trạng thái rỗng. Các lỗi thường liên quan:

- `customerEmail` không hợp lệ.
- Nội dung từ template hoặc model còn thiếu trường bắt buộc.
- `MimeMessageHelper` được tạo không đúng chế độ multipart.
- Inline image/attachment không đọc được.
- Giá trị header có ký tự không phù hợp.
- Phần chuẩn bị message đã bị exception từ một service khác.

Chúng là lỗi **preparation/composition** chứ không nhất thiết được Spring phân loại thành `MailParseException`.

Ví dụ dùng `MimeMessagePreparator`:

~~~java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public void sendNotification(
        JavaMailSender sender,
        String recipient,
        String html) {

    MimeMessagePreparator preparator = message -> {
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");
        helper.setFrom("notifications@example.test");
        helper.setTo(recipient);
        helper.setSubject("Thông báo từ hệ thống");
        helper.setText(html, true);
    };

    sender.send(preparator);
}
~~~

Nếu `preparator.prepare(...)` ném exception, Spring mail sender có thể bọc lỗi này thành `MailPreparationException`. Nếu preparation hoàn tất nhưng SMTP transport thất bại, exception có thể thuộc loại `MailSendException` hoặc `MailAuthenticationException`.

**Cùng một giá trị sai đầu vào có thể dẫn tới kiểu exception khác nhau tùy API và giai đoạn mà ứng dụng sử dụng.** Không nên viết một catch duy nhất `MailParseException` rồi cho rằng đã bao phủ mọi message không hợp lệ.

### Lỗi không thể đọc resource trước khi SMTP

Ví dụ:

~~~java
helper.setText(html, true);
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/missing-logo.png"),
        "image/png");
~~~

Nếu resource không tồn tại, lỗi có thể xảy ra khi tạo hoặc serialize MIME, tùy overload và cách Jakarta Mail đọc resource. Đây là lỗi chuẩn bị nội dung/đọc dữ liệu, không phải SMTP authentication. Đừng xử lý nó bằng cách đổi port SMTP hoặc tăng thời gian retry mạng.

## 8. Chuẩn hóa và xác thực dữ liệu trước khi tạo MIME

Cách phòng ngừa hiệu quả nhất là **đưa dữ liệu không hợp lệ ra khỏi pipeline trước khi gọi các API mail**. Không giao toàn bộ trách nhiệm validation cho `MimeMessageHelper`.

### Xác thực địa chỉ email

Có thể dùng `InternetAddress` để kiểm tra cú pháp ở mức địa chỉ Internet mail:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class MailAddressValidator {
    private MailAddressValidator() {
    }

    public static InternetAddress requireAddress(
            String raw) throws AddressException {
        if (raw == null || raw.isBlank()) {
            throw new AddressException("Email address is required");
        }

        InternetAddress address = new InternetAddress(raw, true);
        address.validate();
        return address;
    }
}
~~~

Sử dụng:

~~~java
InternetAddress recipient =
        MailAddressValidator.requireAddress(request.recipient());

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, false, "UTF-8");

helper.setFrom("noreply@example.test");
helper.setTo(recipient);
helper.setSubject(request.subject());
helper.setText(request.body(), false);
~~~

Kiểm tra cú pháp địa chỉ **không chứng minh mailbox tồn tại**, không bảo đảm domain có MX record và không bảo đảm SMTP provider nhận người nhận đó. Nếu hệ thống có chính sách chỉ cho phép một số domain hoặc recipient đã được xác minh, phải kiểm tra thêm ở application layer.

### Phân biệt địa chỉ mailbox và display name

`"Nguyễn Văn A <a@example.test>"` gồm hai phần: display name và mailbox address. Với người gửi có tên tiếng Việt, nên truyền display name và charset qua API phù hợp:

~~~java
import jakarta.mail.internet.InternetAddress;

InternetAddress sender = new InternetAddress(
        "noreply@example.test",
        "Bộ phận chăm sóc khách hàng",
        "UTF-8");

helper.setFrom(sender);
~~~

Không tự nối header `From:` bằng chuỗi từ request rồi gán raw vào MIME. Hãy dùng API cấu trúc của Jakarta Mail để thư viện encode các header cần thiết.

### Xác thực subject

Subject không phải dữ liệu nhị phân và không nên được dựng bằng cách chèn raw CR/LF. Một model có thể áp dụng các quy tắc:

- Subject bắt buộc không null, không blank với loại email cụ thể.
- Giới hạn độ dài hợp lý theo sản phẩm.
- Không chấp nhận CR (`\r`), LF (`\n`) hoặc ký tự điều khiển không mong muốn.
- Dùng Unicode String, để Jakarta Mail xử lý header encoding.
- Không tự Base64 subject rồi truyền encoded-word như một subject bình thường.

Ví dụ:

~~~java
public static String requireSubject(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException("Subject is required");
    }
    if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
        throw new IllegalArgumentException(
                "Subject must not contain CR/LF");
    }
    if (value.length() > 300) {
        throw new IllegalArgumentException("Subject is too long");
    }
    return value;
}
~~~

Ngưỡng 300 ở ví dụ là **quy tắc ứng dụng minh họa**, không phải độ dài tối đa cố định của SMTP. Header thực tế có cơ chế folding và encoded-word; thư viện chịu trách nhiệm chuyển chuỗi Unicode thành các header phù hợp.

### Không coi HTML escaping là MIME parsing

Nếu body HTML có tên khách hàng chứa `<b>` hoặc `&`, cần escape dữ liệu khi render template; đây là vấn đề HTML injection, không phải MailParseException. Sử dụng `th:text` trong Thymeleaf cho text thông thường hoặc cơ chế HTML escaping tương đương.

Ngược lại, nội dung body đã được escape đúng nhưng cấu trúc multipart sai vẫn có thể hiển thị không đúng. **Validation dữ liệu, escaping HTML và cấu trúc MIME là ba trách nhiệm khác nhau.**

## 9. Dựng MimeMessage đúng cách bằng MimeMessageHelper

Một service chỉ gửi HTML có thể sử dụng:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class CustomerMailComposer {
    private final JavaMailSender sender;

    public CustomerMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage compose(
            String recipient,
            String subject,
            String html) throws MessagingException {

        InternetAddress recipientAddress =
                MailAddressValidator.requireAddress(recipient);
        String validatedSubject = requireSubject(subject);

        if (html == null || html.isBlank()) {
            throw new IllegalArgumentException("HTML body is required");
        }

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name());

        helper.setFrom("noreply@example.test");
        helper.setTo(recipientAddress);
        helper.setSubject(validatedSubject);
        helper.setText(html, true);

        return message;
    }
}
~~~

Ví dụ giả định có import `jakarta.mail.internet.InternetAddress` và phương thức `requireSubject` được triển khai như phần trước. Trong dự án thực tế, nên đặt validator vào thành phần rõ ràng thay vì copy hàm vào nhiều service.

### Vì sao multipart=false vẫn dùng được cho HTML?

Một email có duy nhất `text/html` không cần multipart để gửi. Tham số `true` trong `setText(html, true)` có nghĩa **body này là HTML**; nó không giống tham số `multipart` trong constructor của helper.

So sánh:

~~~java
// Một body HTML; không có attachment hoặc inline image.
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setText(html, true);
~~~

~~~java
// Có inline image hoặc attachment: phải dùng multipart.
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
helper.setText(html, true);
helper.addInline("logo", logoResource, "image/png");
~~~

Nhầm lẫn hai boolean này có thể khiến code gọi `addInline` trên helper không được cấu hình multipart, dẫn đến lỗi preparation.

### Khi có plain và HTML alternative

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
helper.setText(
        "Đơn hàng ORD-001 đã được xác nhận.",
        "<html lang=\"vi\"><body>"
            + "<p>Đơn hàng <strong>ORD-001</strong>"
            + " đã được xác nhận.</p>"
            + "</body></html>");
~~~

`setText(plainText, htmlText)` tạo hai phiên bản nội dung, giúp client chọn dạng hỗ trợ. Đừng truyền ngược HTML vào đối số plain text, vì khi đó client có thể hiển thị nguyên thẻ HTML hoặc đọc sai phần alternative.

## 10. Multipart không đúng có thể gây lỗi muộn

Khi email có ảnh inline và attachment, cấu trúc MIME thường bao gồm các quan hệ:

~~~text
multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     |
  |     |     +-- text/plain
  |     |     +-- text/html
  |     |
  |     +-- image/png
  |           Content-ID: <brand-logo>
  |
  +-- application/pdf
        Content-Disposition: attachment
~~~

Đây là cây khái quát; cấu trúc cụ thể phụ thuộc vào multipart mode và cách helper dựng message.

Các lỗi có thể xảy ra:

- Khai báo boundary ở header nhưng không có delimiter tương ứng trong body raw.
- Thêm image bằng attachment thay vì inline part.
- HTML tham chiếu `cid:brand-logo` nhưng image part có Content-ID khác.
- Đặt attachment vào related group dù nó không phải tài nguyên của HTML.
- Tạo multipart hierarchy thủ công nhưng quên đóng hoặc gắn một child part.
- Dùng Content-Type không khớp dữ liệu thật.

**Phân biệt lỗi cú pháp với lỗi hiển thị:** CID không khớp có thể khiến ảnh mất nhưng hoàn toàn không gây MailParseException, vì cả hai part vẫn là MIME hợp lệ. Một attachment có tên sai hoặc client không hỗ trợ SVG cũng có thể chỉ làm giao diện không như mong muốn. Không phải mọi ảnh không hiện đều là lỗi parse.

### Trình tự khi thêm inline resource

Spring khuyến nghị gọi `addInline` **sau** `setText`:

~~~java
helper.setText(html, true);
helper.addInline("brand-logo", logoResource, "image/png");
helper.addAttachment("invoice.pdf", pdfResource, "application/pdf");
~~~

Thứ tự ngược có thể làm một số mail client gặp khó khăn khi tìm các resource liên quan. Tuy nhiên, lỗi này thường được nhìn thấy ở phía hiển thị, không nhất thiết ném MailParseException khi gửi.

## 11. Charset, header encoding và transfer encoding là các lớp khác nhau

Khi email tiếng Việt bị sai dấu, cần xác định lỗi ở lớp nào:

| Lớp | Vai trò | Ví dụ |
|---|---|---|
| Java Unicode String | Chứa dữ liệu ứng dụng | `"Xin chào"` |
| Charset của MIME text part | Mô tả cách mã hóa ký tự thành byte | `charset=UTF-8` |
| Content-Transfer-Encoding | Mã hóa byte cho việc truyền MIME | `base64` hoặc `quoted-printable` |
| MIME header encoding | Biểu diễn ký tự không phải ASCII trong header | RFC 2047 encoded-word |
| Email client renderer | Giải mã và hiển thị nội dung | Font, HTML/CSS và khả năng hỗ trợ |

Ví dụ body:

~~~mime
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin ch=C3=A0o!</p>
~~~

Body được quoted-printable encode; client phải decode thành UTF-8 rồi hiển thị ký tự tiếng Việt. Nếu metadata encoding không khớp byte thực tế, nội dung có thể lỗi dấu dù parser không ném exception.

Subject có thể xuất hiện trong raw MIME như:

~~~mime
Subject: =?UTF-8?B?Q2Fmw6k=?=
~~~

Client decode thành `Café`. Đừng đọc raw header rồi suy luận rằng ký tự `=?UTF-8?...?=` trong source là lỗi parse; đây là cách encode header hợp lệ.

### Không dùng String.getBytes() không chỉ định charset

Khi tạo hoặc lưu raw MIME text bằng API Java, hãy chỉ định charset phù hợp:

~~~java
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
~~~

Nhưng **không thể** giả định toàn bộ một MIME message có thể được tạo đúng chỉ bằng cách nối các chuỗi UTF-8. Các binary part có transfer encoding, header folding và MIME boundary riêng. Đối với email mới, hãy để Jakarta Mail xây dựng MIME từ các part; đối với email nhận từ ngoài, dùng MIME parser thay vì parse bằng `String.split(...)` theo boundary thủ công.

## 12. Đọc và chẩn đoán exception chain

Đối với `MailParseException`, câu hỏi quan trọng nhất là: **nguyên nhân gốc nằm ở đâu?**

Đường đi có thể là:

~~~text
MailParseException (Spring Mail)
    |
    +-- MessagingException (Jakarta Mail)
            |
            +-- ParseException / IOException / nested cause
~~~

Đây là sơ đồ khái niệm. Không phải mọi lỗi đều có đúng ba tầng hoặc đúng kiểu exception này.

Một hàm lấy chuỗi nguyên nhân đơn giản:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class ExceptionChain {
    private ExceptionChain() {
    }

    public static List<String> typeNames(Throwable failure) {
        List<String> names = new ArrayList<>();
        Throwable current = failure;
        int depth = 0;

        while (current != null && depth++ < 16) {
            names.add(current.getClass().getName());
            Throwable next = current.getCause();
            if (next == current) {
                break;
            }
            current = next;
        }
        return names;
    }
}
~~~

Hàm này chỉ ghi **tên lớp exception**, không tự in nội dung mail hoặc dữ liệu người nhận. Khi cần message của exception, hãy đảm bảo chúng không chứa thông tin nhạy cảm và chỉ log trong mức độ chi tiết cần thiết.

Với Jakarta Mail, `MessagingException` còn có khái niệm *next exception* ngoài chuỗi cause thông thường:

~~~java
import jakarta.mail.MessagingException;

if (failure instanceof MessagingException messaging) {
    Exception next = messaging.getNextException();
    if (next != null) {
        // Ghi nhận type của next, không in payload mail.
        String type = next.getClass().getName();
    }
}
~~~

Vì thế, điều tra lỗi SMTP/MIME nên xem cả cause và nested exceptions do Jakarta Mail cung cấp nếu chúng có mặt, thay vì chỉ đọc message của exception ngoài cùng.

## 13. Quy trình chẩn đoán MailParseException trong ứng dụng Spring

Khi production xuất hiện lỗi, nên đi theo thứ tự có khả năng thu hẹp nguyên nhân thay vì sửa cấu hình SMTP ngay.

~~~mermaid
flowchart TD
    A[Mail processing failed] --> B{Có đang đọc raw MIME InputStream?}
    B -- Có --> C[Kiểm tra nguồn file/stream và kích thước]
    C --> D[Kiểm tra exception chain + raw headers an toàn]
    D --> E{Parser thực sự từ chối MIME?}
    E -- Có --> F[Quarantine bản ghi và xác định lỗi cấu trúc]
    E -- Không --> G[Kiểm tra lúc duyệt part hoặc decode]
    B -- Không --> H[Đang tạo MimeMessage mới]
    H --> I{Lỗi trước khi gọi send?}
    I -- Có --> J[Validate recipient/subject/template/resource]
    I -- Không --> K[Kiểm tra SMTP code/network/provider]
    G --> L[Phân loại nguồn dữ liệu và cơ chế xử lý]
    F --> L
    J --> L
    K --> L
~~~

### Bước 1 — Xác định API đang được gọi

Nhìn vị trí stack trace:

- `createMimeMessage(InputStream)`: tập trung vào stream và raw MIME.
- `new MimeMessageHelper(...)` hoặc `helper.setTo/setText/addInline`: tập trung vào chuẩn bị message.
- `sender.send(MimeMessagePreparator)`: xem lỗi gốc bên trong preparator.
- `sender.send(MimeMessage)`: nếu preparation thành công, kiểm tra serialize/SMTP transport.
- `part.getContent()` hoặc `message.getContent()`: lỗi có thể chỉ xuất hiện khi đọc một part do lazy parsing/decoding.

### Bước 2 — Xác nhận dữ liệu nguồn có đầy đủ

Khi raw MIME đến từ file hoặc object storage:

- Xác minh file có tồn tại và ứng dụng có quyền đọc.
- So sánh kích thước file nguồn và số byte thực nhận.
- Xác nhận quá trình upload/download đã hoàn tất trước khi parse.
- Nếu có checksum, kiểm tra checksum với dữ liệu đã lưu.
- Kiểm tra nguồn không phải file HTML/PDF được đổi tên thành `.eml`.
- Tránh thao tác với stream đã bị đọc một phần hoặc đóng trước khi library dùng.

Khi dữ liệu đến từ queue/broker, cần xem payload có bị giới hạn kích thước hay chuyển đổi giữa byte và String không. Một số hệ thống làm mất byte hoặc thay đổi newline khi encode/decode thông điệp, khiến MIME không còn giống bản gốc.

### Bước 3 — Phân tích header với dữ liệu kiểm soát

Một số dấu hiệu hữu ích:

- `Content-Type` có giá trị là `multipart/...` nhưng không có boundary.
- Boundary trong body khác boundary khai báo.
- Header có dấu nháy chưa đóng hoặc tham số bất thường.
- Không có dòng trống giữa header và body ở đoạn dữ liệu được tạo thủ công.
- Message thiếu các byte cuối khi có attachment lớn.
- Content-Transfer-Encoding bị khai báo sai so với dữ liệu thực.

Hãy phân tích trên **một bản MIME được khử nhạy cảm trong môi trường thử nghiệm**, không đưa email người dùng vào công cụ công cộng. Nếu cần tái hiện, giữ lại cấu trúc header/boundary nhưng thay toàn bộ recipient, subject nhạy cảm và body thật bằng dữ liệu giả.

### Bước 4 — Xác định lỗi có ổn định không

Nếu cùng một blob MIME luôn gây lỗi ở cùng một bước, khả năng cao đây là lỗi dữ liệu/cấu trúc. Retry không thay đổi nội dung thường không giúp ích.

Nếu lỗi chỉ xuất hiện ngẫu nhiên khi đọc file qua mạng và biến mất sau khi tải lại, có thể là lỗi I/O tạm thời. Cần kiểm tra checksum và trạng thái hoàn tất upload, không vội coi blob bị hỏng vĩnh viễn.

### Bước 5 — Phân loại trạng thái cuối

Một hệ thống có job/outbox nên phân biệt:

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `INVALID_INPUT` | Dữ liệu nghiệp vụ không hợp lệ | Từ chối trước khi compose |
| `MIME_PARSE_FAILED` | Raw MIME không parse được | Quarantine/DEAD và điều tra nguồn |
| `MIME_PREPARATION_FAILED` | Không dựng được message | Sửa template, resource, recipient |
| `SMTP_RETRYABLE` | Transport/provider gặp lỗi tạm thời | Retry có backoff |
| `SMTP_PERMANENT` | SMTP từ chối vì lý do không tự khắc phục | DEAD hoặc xử lý thủ công |
| `SMTP_UNKNOWN` | Không rõ SMTP đã chấp nhận hay chưa | Đối soát hoặc retry theo chính sách |
| `SUBMITTED` | Server SMTP chấp nhận message | Theo dõi delivery riêng nếu cần |

Các tên trạng thái này là gợi ý ở cấp ứng dụng, không phải các enum mặc định của Spring Mail.

## 14. Quy tắc retry: lỗi parse thường không cần thử lại SMTP

Một lỗi `MailParseException` do cùng một raw MIME blob không hợp lệ thường có tính **deterministic**. Nếu bạn thử lại parse đúng các byte ấy bằng cùng parser mà không thay gì, nhiều khả năng lỗi vẫn tồn tại.

Ví dụ quy trình:

~~~text
Read raw MIME blob
      |
      +-- Read failed vì object storage timeout
      |        |
      |        v
      |    Retry việc lấy dữ liệu
      |
      +-- Đọc hoàn tất, checksum đúng
      |        |
      |        v
      |    Parse thất bại ổn định
      |        |
      |        v
      |    Quarantine / sửa dữ liệu nguồn
      |
      +-- Parse thành công
               |
               v
           Compose / send
~~~

**Không retry SMTP khi chưa có MimeMessage hợp lệ để gửi.** Nếu message không được dựng thành công, SMTP server chưa hề nhận yêu cầu submission tương ứng từ job đó.

### Ngoại lệ quan trọng: nguồn dữ liệu thay đổi giữa các lần đọc

Một file có thể đang được upload dở, hoặc object storage trả dữ liệu không nhất quán do lỗi pipeline. Trong trường hợp này, retry bước *lấy dữ liệu* sau khi xác nhận upload hoàn tất có thể hợp lý. Không nên gọi đó là “retry MailParseException” mà không hiểu tại sao dữ liệu lần sau khác lần trước.

### SMTP lỗi sau khi bắt đầu truyền message

Nếu message đã được tạo và gửi tới SMTP nhưng connection mất giữa chừng, kết quả có thể không rõ. Khi SMTP đã nhận body và trả lời thành công nhưng ứng dụng chưa lưu trạng thái, retry có thể gửi trùng. Vì vậy lỗi transport cần chính sách riêng, khác hoàn toàn lỗi parse một MIME blob cố định.

## 15. Logging có cấu trúc và bảo vệ dữ liệu

Log hữu ích cần giúp tìm ra **bước nào** thất bại mà không phải sao chép toàn bộ email.

Ví dụ record log ở cấp application:

~~~text
event=mail_processing_failed
mailJobId=job-7f3e
phase=parse_raw_mime
exceptionType=org.springframework.mail.MailParseException
sourceType=object_storage
rawMimeBytes=187436
attempt=1
correlationId=req-84f0
classification=MIME_PARSE_FAILED
~~~

Hãy cân nhắc chỉ ghi những trường cần vận hành. Đặc biệt:

- Không log đầy đủ `From`, `To`, `Cc`, `Bcc` nếu không cần.
- Không log reset token, OTP, body HTML, attachment hoặc raw MIME.
- Không in stack trace chứa dữ liệu nhạy cảm lên hệ thống log công cộng.
- Không dùng subject làm label metric vì dữ liệu nhạy cảm và cardinality cao.
- Giới hạn thời gian giữ lại log/quarantine blob và quyền truy cập.

### Tách error code khỏi nội dung exception

Exception message từ thư viện có thể thay đổi theo version và có thể chứa một phần dữ liệu đầu vào. Thay vì để application logic dựa vào việc `message.contains("boundary")`, hãy chuẩn hóa error code:

~~~java
public enum MailProcessingFailureCode {
    INVALID_RECIPIENT,
    INVALID_SUBJECT,
    MIME_PARSE_FAILED,
    MIME_PREPARATION_FAILED,
    RESOURCE_READ_FAILED,
    SMTP_AUTH_FAILED,
    SMTP_SUBMISSION_FAILED,
    SMTP_SUBMISSION_UNKNOWN
}
~~~

Đừng suy luận mã lỗi chi tiết hơn bằng chứng thực tế. Nếu parser chỉ trả một exception chung và không chỉ rõ chính xác header nào sai, ghi `MIME_PARSE_FAILED` thay vì khẳng định một boundary cụ thể bị lỗi.

### Hạn chế lưu raw MIME để điều tra

Một raw MIME message có thể chứa:

- Địa chỉ email và tên thật.
- Dữ liệu đơn hàng, thanh toán, thông tin cá nhân.
- Link với token truy cập.
- Attachment chứa tài liệu nội bộ.
- Thông tin header phản ánh hạ tầng vận chuyển.

Nếu cần giữ file lỗi để tái hiện, hãy lưu trong kho được mã hóa, hạn chế quyền, quy định thời hạn xóa và dùng ID tham chiếu trong log. Dữ liệu giả hoặc đã khử nhạy cảm nên là lựa chọn mặc định cho tài liệu, issue tracker và ví dụ test.

## 16. Không nên tự sửa raw MIME bằng thao tác chuỗi tùy tiện

Một số đoạn code cố “sửa” email:

~~~java
String raw = new String(rawBytes, StandardCharsets.UTF_8);
raw = raw.replace("\\n", "\\r\\n");
raw = raw.replace("boundary=bad", "boundary=good");
byte[] fixedBytes = raw.getBytes(StandardCharsets.UTF_8);
~~~

Cách tiếp cận này **không an toàn về mặt tính toàn vẹn dữ liệu**:

- MIME có thể chứa binary part hoặc dữ liệu encoded theo nhiều charset.
- Toàn bộ raw MIME không nhất thiết là một văn bản Unicode thông thường.
- Chuẩn hóa newline không phân biệt boundary line, header folding và body text.
- Thay chuỗi boundary trong header nhưng không đổi delimiter thật có thể làm lỗi nặng hơn.
- Chuyển byte sang String rồi chuyển lại có thể phá dữ liệu không phải UTF-8.

Nếu cần sửa raw MIME do hệ thống tự tạo, hãy sửa **bộ tạo message từ nguồn dữ liệu chuẩn** rồi serialize lại bằng Jakarta Mail. Nếu đang xử lý email nhận từ hệ thống bên ngoài, lưu bản gốc và thiết kế parser/quarantine có kiểm soát; không “repair” một cách mù để vượt qua exception.

### Phần nào nên tạo bằng API thay vì nối chuỗi?

| Thành phần | Cách nên làm |
|---|---|
| From/To/Reply-To | `InternetAddress` và helper methods |
| Subject Unicode | `setSubject` nhận Java String |
| Body plain text | `setText(text, false)` |
| Body HTML | `setText(html, true)` |
| Plain + HTML | `setText(plain, html)` |
| Inline image | `addInline(contentId, resource, mediaType)` |
| Attachment | `addAttachment(filename, resource, mediaType)` |
| Cấu trúc multipart | Để `MimeMessageHelper` quản lý khi có thể |

Nối raw header/body thủ công chỉ nên dùng khi có nhu cầu đặc biệt và hiểu rõ Internet Message Format, MIME boundary, charset và transfer encoding.

## 17. Tách lỗi MIME khỏi lỗi HTML template

Một template email có thể thất bại trước khi tạo MIME:

~~~text
Template context missing required value
        |
        v
Thymeleaf render exception
        |
        v
Không tạo được HTML
        |
        v
Chưa có SMTP submission
~~~

Một template khác render thành HTML hợp lệ nhưng chứa nội dung sai:

~~~html
<p>Mã đơn hàng: null</p>
~~~

Đây là lỗi **ngữ nghĩa dữ liệu**, có thể vẫn gửi qua SMTP thành công. Không có MailParseException nào bắt buộc phải xảy ra.

Vì vậy cần hai lớp kiểm soát:

1. **Validation trước rendering** cho trường bắt buộc, recipient, subject, URL và dữ liệu nghiệp vụ.
2. **Kiểm tra MIME composition** cho charset, part structure, Content-ID và attachment.

Nếu email được tạo bằng template engine rồi truyền vào `MimeMessageHelper`, lỗi template thường nên được phân loại thành `MIME_PREPARATION_FAILED` hoặc `TEMPLATE_RENDER_FAILED` theo quy ước ứng dụng, thay vì gắn nhãn `MailParseException`.

## 18. Kiểm thử MIME round-trip không cần SMTP server

Một kiểm thử hữu ích là dựng message từ dữ liệu hợp lệ, serialize thành raw byte, parse lại và xác nhận nội dung sau decode. Kiểm thử này không gửi email thật nhưng chứng minh ứng dụng tạo ra một MIME message có thể được Jakarta Mail đọc lại.

Ví dụ với **JUnit Jupiter** và **AssertJ**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

class MailMimeRoundTripTest {
    @Test
    void roundTripsVietnameseSubjectAndHtmlBody() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage original = new MimeMessage(session);

        MimeMessageHelper helper = new MimeMessageHelper(
                original,
                false,
                StandardCharsets.UTF_8.name());
        helper.setFrom("noreply@example.test");
        helper.setTo("customer@example.test");
        helper.setSubject("Đơn hàng đã xác nhận ✅");
        helper.setText(
                "<html lang=\"vi\"><body>"
                    + "<p>Xin chào, đơn hàng của bạn đã được xác nhận.</p>"
                    + "</body></html>",
                true);

        original.saveChanges();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        original.writeTo(output);

        JavaMailSenderImpl parser = new JavaMailSenderImpl();
        MimeMessage parsed = parser.createMimeMessage(
                new ByteArrayInputStream(output.toByteArray()));

        assertThat(parsed.getSubject())
                .isEqualTo("Đơn hàng đã xác nhận ✅");
        assertThat(parsed.isMimeType("text/html")).isTrue();
        assertThat((String) parsed.getContent())
                .contains("Xin chào, đơn hàng của bạn");
    }
}
~~~

Trong test:

- `saveChanges()` cập nhật các thông tin MIME cần thiết trước serialization.
- `writeTo(...)` chuyển message thành byte, bao gồm header/transfer encoding.
- `createMimeMessage(InputStream)` parse lại từ byte, kiểm tra đường đi đọc MIME.
- `getSubject()` và `getContent()` được dùng để xem dữ liệu sau decode.
- Không có SMTP host, username hoặc password; test không gọi `send(...)`.

Test này cố ý dùng một `text/html` part đơn giản. Nếu message có multipart/alternative, inline images hoặc attachment, `getContent()` có thể trả `Multipart` thay vì `String`; khi đó cần duyệt cây part.

### Duyệt part theo loại nội dung

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import jakarta.mail.MessagingException;

static String findHtmlBody(Part part)
        throws MessagingException, IOException {
    if (part.isMimeType("text/html")) {
        Object content = part.getContent();
        return content instanceof String text ? text : null;
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();
        for (int i = 0; i < multipart.getCount(); i++) {
            String html = findHtmlBody(multipart.getBodyPart(i));
            if (html != null) {
                return html;
            }
        }
    }
    return null;
}
~~~

Đoạn code tìm body HTML trong cây multipart cơ bản. Với email rất phức tạp, có thể có `message/rfc822` lồng bên trong hoặc nhiều HTML alternative; ứng dụng cần chính sách chọn part đúng ngữ nghĩa. Không giả định part số 0 luôn là HTML.

## 19. Kiểm thử input không hợp lệ mà không phụ thuộc parser strictness

Một test quan trọng là xác minh **dữ liệu sai được chặn trước khi dựng message**:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.mail.internet.AddressException;
import org.junit.jupiter.api.Test;

class MailAddressValidatorTest {
    @Test
    void rejectsMalformedRecipient() {
        assertThatThrownBy(() ->
                MailAddressValidator.requireAddress("not-an-email"))
                .isInstanceOf(AddressException.class);
    }

    @Test
    void rejectsMissingRecipient() {
        assertThatThrownBy(() ->
                MailAddressValidator.requireAddress("   "))
                .isInstanceOf(AddressException.class);
    }
}
~~~

Một test khác cho subject:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class MailSubjectValidatorTest {
    @Test
    void rejectsHeaderLineBreak() {
        String suspicious =
                "Receipt\r\nBcc: hidden@example.test";

        assertThatThrownBy(() -> requireSubject(suspicious))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

`requireSubject` là phương thức validation minh họa ở phần trước. Bài test này phát hiện dữ liệu header có CR/LF không mong muốn và từ chối nó trước khi sử dụng Jakarta Mail.

### Vì sao không nên assert “MIME sai bất kỳ phải ném MailParseException”?

Các parser mail thực tế thường có chế độ **tolerant parsing** để đọc email ngoài đời không hoàn toàn chuẩn. Chẳng hạn:

- Thiếu closing boundary có thể bị parser chấp nhận một phần.
- Header bị thiếu có thể dẫn đến giá trị null, không phải exception.
- Content-Type sai có thể khiến nội dung bị diễn giải thành part khác.
- Lỗi Base64 có thể chỉ xuất hiện khi đọc body stream.

Do đó, một test tự tạo một raw string “trông có vẻ sai” rồi assert `MailParseException` có thể không ổn định giữa các phiên bản Jakarta Mail. Test cần:

1. Biết chính xác lỗi nào được implementation đang dùng báo ra.
2. Kiểm tra trạng thái/semantic của message sau parse, không chỉ “constructor không ném exception”.
3. Tách test **validation do ứng dụng quản lý** khỏi test **khả năng chịu lỗi của parser**.
4. Nếu cần test catch branch, mô phỏng exception tại abstraction boundary bằng mock/stub thay vì phụ thuộc một raw sample thiếu chuẩn không được parser cam kết từ chối.

### Test lỗi I/O khi đọc dữ liệu

Nếu input được tải từ object storage, dùng fake resource ném IOException để kiểm tra rằng hệ thống phân loại nó là **resource read failure** có thể retry, không gộp với malformed MIME:

~~~java
InputStreamSource brokenSource = () -> {
    throw new IOException("Temporary object storage failure");
};
~~~

Test này mô tả lỗi lấy stream; không phải ví dụ bảo đảm `MailParseException`. Tách hai trường hợp giúp logic retry không đưa một MIME blob hỏng vào vòng retry mạng vô hạn.

## 20. Xử lý MailParseException trong workflow gửi mail

Nếu ứng dụng nhập raw MIME rồi gửi lại, có thể tổ chức một service xử lý kết quả:

~~~java
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ImportedMailDispatcher {
    private final JavaMailSender sender;
    private final MailJobStateStore jobStore;

    public ImportedMailDispatcher(
            JavaMailSender sender,
            MailJobStateStore jobStore) {
        this.sender = sender;
        this.jobStore = jobStore;
    }

    public void dispatch(String jobId, Resource rawMime) {
        MimeMessage message;

        try (InputStream stream = rawMime.getInputStream()) {
            message = sender.createMimeMessage(stream);
        } catch (MailParseException ex) {
            jobStore.markDead(jobId, "MIME_PARSE_FAILED");
            return;
        } catch (IOException ex) {
            jobStore.scheduleRetry(jobId, "RESOURCE_READ_FAILED");
            return;
        }

        try {
            sender.send(message);
            jobStore.markSubmitted(jobId);
        } catch (MailSendException ex) {
            jobStore.recordSubmissionFailure(jobId, ex);
        }
    }
}
~~~

`MailJobStateStore` là interface do ứng dụng định nghĩa, không phải API có sẵn của Spring. Mục đích ví dụ là chỉ ra **ranh giới phân loại**:

- Lỗi parse raw MIME được xử lý trước lời gọi send.
- Lỗi đọc nguồn tạm thời được tách khỏi lỗi dữ liệu hỏng.
- Lỗi SMTP xảy ra ở giai đoạn submission và có chính sách riêng.

Đây là khung minh họa, chưa bao gồm mọi subtype `MailException`, lease/idempotency, security/quarantine và việc parse lười có thể phát sinh lỗi muộn. Trong hệ thống thực, worker cần catch các exception tương ứng ở mỗi giai đoạn, lưu trạng thái theo transaction riêng và không được đánh dấu `SUBMITTED` nếu submission chưa được xác nhận.

### Vấn đề vòng đời stream khi gửi lại MIME đã nhập

Tùy nguồn và implementation, parser có thể đọc/buffer một phần hoặc toàn bộ message khi constructor chạy. Nếu sau đó `send(...)` cần đọc lại part từ nguồn đã đóng, có thể gặp lỗi. Đối với workflow import/send lại, cần lựa chọn cách giữ dữ liệu ổn định:

- Lưu blob MIME vào file tạm an toàn hoặc object storage rồi tạo nguồn đọc lại được.
- Giới hạn kích thước và checksum dữ liệu trước khi parse.
- Xác nhận `MimeMessage` có thể serialize lại sau khi nguồn InputStream được giải phóng.
- Với nguồn one-shot, có thể phải tạo bản byte/file trung gian hoặc deserialize bằng API phù hợp.

Đừng biến một ngoại lệ I/O khi serialize attachment sau này thành kết luận “MIME parser không hiểu header” nếu bằng chứng thực tế là resource đã không còn đọc được.

## 21. Khi import MIME, cần giới hạn kích thước và tài nguyên

Một input `.eml` từ hệ thống bên ngoài có thể chứa attachment rất lớn hoặc nhiều nested part. Dù parser xử lý cú pháp được, việc đọc toàn bộ message vào bộ nhớ có thể gây áp lực heap.

Một chính sách nhận đầu vào an toàn nên có:

- Giới hạn kích thước raw MIME trước khi parse.
- Giới hạn số lượng attachment và kích thước mỗi attachment khi đọc nội dung.
- Giới hạn độ sâu của multipart hoặc message lồng nhau nếu cần.
- Timeout và giới hạn byte khi tải từ object storage hoặc URL.
- Chỉ chấp nhận nguồn dữ liệu đã được xác thực/được phép.
- Không render HTML bên ngoài trong bối cảnh đặc quyền.
- Kiểm tra loại file thực, không chỉ dựa vào tên `.eml`.
- Có chính sách quarantine khi phát hiện payload không đáng tin.

Ví dụ với file local do ứng dụng quản lý:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public MimeMessage readBoundedMail(Path path) throws Exception {
    long maxBytes = 10L * 1024 * 1024;

    if (Files.size(path) > maxBytes) {
        throw new IllegalArgumentException("Raw MIME is too large");
    }

    try (InputStream stream = Files.newInputStream(path)) {
        return sender.createMimeMessage(stream);
    }
}
~~~

Đây chỉ là kiểm tra kích thước file trước khi đọc, phù hợp khi file nằm trong vùng lưu trữ được quản lý. Nếu file có thể bị thay thế/ghi thêm đồng thời giữa `Files.size(...)` và `newInputStream(...)`, cần cơ chế snapshot hoặc giới hạn byte trong quá trình đọc. Với network stream không có size đáng tin, cần bounded reader thật sự. Không tin `Content-Length` của đầu vào chưa được xác thực là bảo đảm kích thước tuyệt đối.

Giá trị 10 MiB chỉ minh họa. Ngưỡng thực tế phụ thuộc loại email, giới hạn provider, memory budget, kích thước attachment và chính sách sản phẩm.

## 22. Phân biệt lỗi parse với lỗi kết nối và authentication

Một application log có thể ghi chung “Cannot send email” cho nhiều nguyên nhân. Tuy nhiên hướng xử lý phụ thuộc giai đoạn:

~~~text
Input / template / raw MIME
         |
         +-- Validation failed
         |
         +-- MIME parse failed
         |
         +-- MIME preparation failed
         |
         v
MimeMessage hợp lệ
         |
         v
SMTP connection + authentication
         |
         +-- Connection refused/timeout
         |
         +-- Authentication rejected
         |
         v
MAIL FROM / RCPT TO / DATA
         |
         +-- SMTP 4xx / 5xx
         |
         v
SMTP accepted
         |
         v
Delivery / mailbox processing
~~~

Ví dụ, việc sửa host/port hoặc mật khẩu SMTP **không khắc phục được** một `MailParseException` do raw MIME có header không parse được. Ngược lại, sửa Content-Type của template không giải quyết được lỗi `535 Authentication credentials invalid`.

| Thông tin quan sát | Khả năng chính | Bước xử lý |
|---|---|---|
| Stack trace ở `createMimeMessage(InputStream)` | Raw MIME parsing | Kiểm tra input bytes, stream, header |
| Exception trong `MimeMessagePreparator` | Composition/preparation | Kiểm tra model, recipient, template, resource |
| `AddressException` trước khi send | Địa chỉ không hợp lệ | Validation email address |
| Lỗi `MailAuthenticationException` | SMTP authentication | Secret/config/account policy |
| Connect timeout khi submit | Network/provider | Timeout, DNS, firewall, SMTP availability |
| Provider trả SMTP 4xx | Lỗi tạm thời hoặc rate limit | Retry có backoff theo chính sách |
| Provider trả SMTP 5xx | Thường là lỗi permanent tùy mã | Kiểm tra recipient/sender/domain/policy |
| SMTP accepted nhưng client không hiển thị ảnh | Rendering/MIME relationship | Kiểm tra CID, multipart, email client |

Phân loại giai đoạn trước rồi mới kiểm tra chính xác nested exception. Một lỗi có thể phát sinh khi Jakarta Mail serialize message trong `send(...)` chứ không nhất thiết nằm ở network, vì thế không nên kết luận chỉ từ tên phương thức top-level.

## 23. Config SMTP đúng không thể sửa một MIME blob hỏng

Trong Spring Boot, cấu hình sender có thể là:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: \${SMTP_USERNAME}
    password: \${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Những thuộc tính này điều khiển kết nối và SMTP behavior. Chúng **không làm parser tự sửa header MIME sai**, không bổ sung multipart boundary bị thiếu và không chuyển một file PDF đổi tên thành một raw email hợp lệ.

Phân biệt rõ:

- **MIME parsing:** cách thư viện hiểu cấu trúc raw message.
- **MIME composition:** cách ứng dụng dựng header, body và part.
- **SMTP transport:** cách message được submit qua mạng.

Cấu hình charset khi dùng `MimeMessageHelper(..., "UTF-8")` giúp dựng các text part phù hợp nhưng không sửa được một raw MIME đã hỏng byte trước khi được nhập.

## 24. Những anti-pattern khi xử lý MailParseException

### 24.1. Bắt mọi MailException rồi retry ngay

~~~java
try {
    processMail(job);
} catch (MailException ex) {
    retryImmediately(job);
}
~~~

Nếu nguyên nhân là blob MIME không hợp lệ, lặp vô hạn không làm dữ liệu đổi. Retry dồn dập gây tăng tải, làm đầy backlog và che khuất lỗi nguồn. Phải phân loại parse, preparation, authentication và submission.

### 24.2. Gộp lỗi ứng dụng thành “SMTP unavailable”

Nếu template không render được hoặc recipient sai cú pháp, hệ thống không nên hiển thị “SMTP server down”. Một mã lỗi sai sẽ dẫn đội vận hành kiểm tra sai thành phần, gây chậm khắc phục và có thể tăng số lần retry không cần thiết.

### 24.3. Chỉ catch MailParseException ở mọi nơi

~~~java
try {
    helper.setTo(recipient);
    helper.setText(html, true);
    sender.send(message);
} catch (MailParseException ex) {
    // Không bao phủ tất cả lỗi preparation hoặc SMTP.
}
~~~

Ví dụ trên không xử lý đầy đủ `MessagingException`, `MailPreparationException` và các subtype Spring Mail khác. Hãy catch theo ranh giới rõ ràng và giữ cause để phân loại.

### 24.4. Bỏ qua lỗi rồi vẫn đánh dấu email đã gửi

~~~java
try {
    sender.send(message);
} catch (Exception ex) {
    logger.warn("Ignoring mail failure");
}
job.markSubmitted(); // Sai ý nghĩa trạng thái.
~~~

`SUBMITTED` chỉ nên được ghi khi có bằng chứng SMTP submission thành công. Nếu parse/preparation thất bại, chưa có mail hợp lệ được gửi. Nếu transport outcome không chắc chắn, dùng trạng thái tương ứng thay vì tự khẳng định thành công.

### 24.5. Log toàn bộ raw MIME để debug nhanh

Đưa raw MIME lên log production có thể làm lộ OTP, token, attachment và dữ liệu cá nhân. Hãy log phase, correlation ID, kích thước, exception type và các metadata đã được làm sạch. Nếu cần giữ blob lỗi, lưu vào kho có kiểm soát với retention rõ ràng.

### 24.6. Tự chia email bằng String.split

Không tự tách MIME bằng `split("--boundary")` hoặc parse header bằng cách tìm dấu `:` đầu tiên trong toàn bộ message. Các header có thể được fold, body có thể chứa dữ liệu mã hóa, boundary có quy tắc riêng. Hãy dùng Jakarta Mail.

### 24.7. Giả định parse thành công nghĩa message đủ nghĩa nghiệp vụ

Một MIME message không có `To`, có Subject rỗng hoặc chứa dữ liệu cũ có thể vẫn được parse. Việc “đọc được MIME” không đồng nghĩa “đủ điều kiện để gửi”. Cần validation riêng cho use case và chính sách gửi.

### 24.8. Bắt lỗi bằng cách thay mọi ký tự lạ thành dấu hỏi

Chuyển đổi charset không đúng có thể làm mất dữ liệu gốc. Nếu mất byte trước khi encode, không có thuộc tính MIME nào khôi phục lại được nội dung. Sửa tại nguồn và bảo toàn dữ liệu Unicode/byte khi chuyển qua các hệ thống.

### 24.9. Retry raw MIME ở cùng dữ liệu nhưng không giữ bản gốc

Nếu pipeline “sửa” blob theo mỗi lần retry, dữ liệu có thể thay đổi không kiểm soát và không thể điều tra. Nên giữ bản raw ban đầu có checksum, ghi nhận phiên bản parser/pipeline và tạo bản đã chỉnh sửa như artifact riêng khi thật sự cần.

## 25. Bộ tình huống kiểm tra cho ứng dụng Spring Mail

Một bộ test gọn nhưng hữu ích có thể gồm:

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| TC-01 | Tạo HTML + Subject tiếng Việt hợp lệ | MIME serialize và parse lại được |
| TC-02 | Recipient thiếu ký tự @ | Validation từ chối trước khi gửi |
| TC-03 | Recipient null/blank | Validation từ chối |
| TC-04 | Subject có CR/LF | Validation từ chối |
| TC-05 | Template thiếu field bắt buộc | Preparation thất bại, không gọi SMTP |
| TC-06 | File ảnh/attachment không tồn tại | Lỗi resource/preparation được phân loại |
| TC-07 | Raw MIME từ file hợp lệ | `createMimeMessage(InputStream)` tạo message |
| TC-08 | Raw MIME hỏng theo parser đang sử dụng | Lỗi parse được báo/quarantine đúng |
| TC-09 | Nguồn đọc InputStream ném IOException | Phân loại lỗi đọc, không gán nhầm malformed MIME |
| TC-10 | Multipart có HTML và inline CID | Có image part và Content-ID khớp |
| TC-11 | SMTP AUTH sai | Phân loại authentication, không coi là parse |
| TC-12 | SMTP timeout trước submission | Retry theo chính sách transport |
| TC-13 | Kết quả sau DATA không chắc chắn | Không tự động ghi nhận delivery/exactly-once |
| TC-14 | Một job lỗi trong batch | Các job khác vẫn được xử lý độc lập |

Nên dùng:

- **Unit tests** cho model/recipient/subject validation và error classification.
- **MIME round-trip tests** với `MimeMessage.writeTo(...)` và `createMimeMessage(InputStream)`.
- **Database tests** nếu job/outbox có state transition và retry.
- **SMTP sink integration tests** khi cần xác minh raw MIME được gửi qua giao thức.
- **Client rendering tests** khi vấn đề nằm ở HTML/inline image.

Không dùng tài khoản SMTP production hoặc người nhận thật để tái hiện lỗi parser. Test MIME có thể chạy hoàn toàn trong bộ nhớ và không cần credential.

## 26. Vận hành batch mail khi có message hỏng

Nếu worker xử lý nhiều outbox record trong một batch, một raw MIME hỏng không nên làm **mất trạng thái của cả batch**:

~~~text
Batch:
  Job A -> parse thành công -> send
  Job B -> MailParseException -> quarantine
  Job C -> parse thành công -> send

Worker tiếp tục xử lý các job độc lập
và ghi kết quả riêng cho từng job.
~~~

Các nguyên tắc:

1. Mỗi job có ID/correlation ID ổn định.
2. Lỗi parse một job được ghi thành trạng thái riêng, không nuốt exception rồi mất record.
3. Nếu dữ liệu hỏng cố định, không retry vô hạn.
4. Nếu lỗi I/O tạm thời, retry có backoff và giới hạn.
5. Không coi SMTP acceptance là delivery cuối cùng.
6. Nếu SMTP outcome không chắc chắn, phải cân nhắc duplicate trước khi retry.
7. Không xóa dữ liệu quan trọng trước khi trạng thái và audit được commit.
8. Nếu worker crash, job chưa hoàn tất có thể được claim lại theo lease, không phụ thuộc queue RAM thuần.

### Metric cần theo dõi

| Metric | Ý nghĩa |
|---|---|
| `mail_parse_failure_total` | Số lỗi parse raw MIME |
| `mail_preparation_failure_total` | Số lỗi tạo/chuẩn bị email |
| `mail_resource_read_failure_total` | Số lỗi đọc input/resource |
| `mail_submission_failure_total` | Số lỗi SMTP submission |
| `mail_job_dead_total` | Số job cần can thiệp |
| `mail_job_retry_count` | Số job đang chờ retry |
| `mail_job_oldest_pending_age` | Thời gian chờ dài nhất |
| `mail_processing_duration` | Thời gian xử lý theo phase |

Metric nên có tag theo **phase**, **error code** và **loại email** ở mức cardinality thấp. Không đặt nguyên `recipient`, `subject`, `jobId` hoặc exception message làm metric label.

### Alerting

Một vài tình huống đáng cảnh báo:

- MailParseException tăng đột biến ngay sau khi deploy thay đổi pipeline MIME.
- Tất cả job nhập từ cùng một nguồn đều parse thất bại.
- Tỷ lệ lỗi resource read tăng cùng lúc object storage có sự cố.
- SMTP AUTH lỗi hàng loạt dù MIME round-trip test vẫn thành công.
- Backlog job bị DEAD/UNKNOWN tăng hoặc không được xử lý.

Thông tin này giúp xác định liệu cần rollback thay đổi MIME serializer, điều tra data ingestion hay sửa SMTP provider config.

## 27. Câu hỏi thường gặp

**MailParseException có nghĩa SMTP server đang lỗi không?** Không. Nó thường chỉ ra vấn đề khi parse mail message. SMTP connection và authentication là những giai đoạn khác.

**Cứ thiếu Subject hoặc To là parser ném MailParseException?** Không nhất thiết. MIME parser có thể đọc được message thiếu một số header. Ứng dụng phải validation trường bắt buộc theo nghiệp vụ.

**Tại sao cùng một email raw parse được trong client nhưng thất bại trong ứng dụng?** Các parser có thể khác nhau về mức tolerant parsing, cấu hình và cách đọc part. Cần so sánh raw bytes, implementation/version và giai đoạn lỗi; không suy diễn rằng một bên chắc chắn sai.

**MailParseException và MailPreparationException khác nhau thế nào?** Parse exception hướng tới việc không đọc/parse được mail message; preparation exception hướng tới lỗi khi chạy logic dựng/chuẩn bị message, chẳng hạn trong MimeMessagePreparator.

**Lỗi sai địa chỉ người nhận luôn là MailParseException?** Không. Nó thường liên quan AddressException/MessagingException hoặc lỗi preparation tương ứng; nếu server từ chối recipient hợp lệ về cú pháp thì lại là lỗi SMTP.

**Đổi charset sang UTF-8 có tự sửa được raw MIME hỏng không?** Không. UTF-8 chỉ giải quyết biểu diễn văn bản khi byte và metadata nhất quán. Boundary sai, nguồn bị cắt hoặc stream lỗi không được sửa bằng đổi charset.

**Có thể parse MIME bằng cách ép toàn bộ InputStream thành UTF-8 String?** Không nên. Một raw MIME message có thể chứa nhiều part với transfer encoding và charset khác nhau; cách ép toàn bộ có thể phá dữ liệu.

**Một file .eml thiếu closing boundary có chắc bị từ chối không?** Không. Mức tolerant parsing của Jakarta Mail có thể cho phép parse một phần. Test nên kiểm tra ngữ nghĩa/part thực nhận, không dựa vào một mẫu “sai” tùy ý.

**Có nên retry MailParseException vô hạn?** Không. Với raw bytes hỏng cố định, cần quarantine và sửa nguồn. Chỉ retry phần đọc/tải nếu có bằng chứng lỗi tạm thời hoặc dữ liệu nguồn có thể chưa hoàn tất.

**Nếu đã gọi send rồi mới lỗi, đó là lỗi parse hay SMTP?** Cần đọc stack trace và nested cause. Serialization MIME có thể diễn ra trong quá trình gửi; không kết luận chỉ dựa trên tên method.

**SMTP gửi thành công có nghĩa body MIME đúng không?** Không. Server có thể chấp nhận một message mà email client hiển thị không như mong đợi. Cần kiểm thử MIME và rendering độc lập.

## 28. Quy trình xử lý đề xuất

~~~text
1. Nhận request hoặc raw MIME.
2. Validate nguồn dữ liệu, kích thước và quyền truy cập.
3. Nếu dựng email mới: validate recipient, subject, model/template.
4. Nếu nhập raw MIME: parse bằng Jakarta Mail, không tự split.
5. Nếu có MailParseException:
      - ghi ID/phase/cause type an toàn
      - xác định lỗi nguồn đọc hay cấu trúc cố định
      - retry fetch nếu tạm thời, quarantine nếu blob hỏng
6. Nếu lỗi preparation: sửa model/template/resource, không retry SMTP mù.
7. Serialize và kiểm tra MIME khi cần chẩn đoán.
8. Gửi qua JavaMailSender.
9. Phân loại SMTP acceptance, rejection hoặc UNKNOWN.
10. Ghi trạng thái theo từng job và theo dõi metric.
~~~

**Nguyên tắc cuối cùng:** `MailParseException` là tín hiệu cần điều tra **ranh giới parse message**, không phải tên chung cho mọi email không gửi được. Trong Spring Framework Mail, hãy phân biệt parse dữ liệu MIME có sẵn, dựng message bằng `MimeMessageHelper` và gửi qua SMTP; validation dữ liệu trước khi tạo, đọc rõ exception chain, kiểm thử round-trip, bảo vệ raw MIME và áp dụng retry đúng phase. Phân loại đúng lỗi sẽ giúp xử lý nhanh hơn, tránh gửi trùng và tránh để một message hỏng làm tắc nghẽn toàn bộ hệ thống mail.
