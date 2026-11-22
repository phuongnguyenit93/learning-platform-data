# Không tin dữ liệu để tạo header, địa chỉ và template

Một ứng dụng gửi email bằng **Spring Framework Mail** có thể nhận dữ liệu từ form đăng ký, API, hàng đợi sự kiện, database hoặc hệ thống đối tác. Dữ liệu đó thường xuất hiện trong **người nhận**, **Subject**, **Reply-To**, **tên hiển thị**, **MIME header**, **nội dung HTML**, **đường dẫn liên kết**, **tên tệp đính kèm** và **tên template**. Nếu sử dụng trực tiếp những chuỗi không đáng tin để điều khiển cấu trúc email, hệ thống có thể bị lạm dụng để gửi thư sai người, giả mạo thông tin, chèn header, tạo HTML nguy hiểm hoặc truy cập tài nguyên ngoài ý định.

Nguyên tắc trung tâm là **không tin dữ liệu đầu vào để tạo cấu trúc mail**. Đầu vào từ người dùng hoặc hệ thống ngoài chỉ nên là *dữ liệu* được kiểm tra và đặt vào những vị trí cho phép. Các thành phần quyết định hành vi — địa chỉ gửi, danh sách người nhận hợp lệ, loại notification, template được chọn, URL đáng tin và MIME metadata — phải được xác định theo **chính sách của ứng dụng**.

Spring cung cấp **JavaMailSender**, **MimeMessageHelper** và các lớp của **Jakarta Mail** để xây dựng email có cấu trúc. Sử dụng đúng API giúp tránh việc tự lắp ghép raw SMTP/MIME, nhưng **không thay thế validation, authorization, HTML escaping và kiểm soát template**. Bài học này giải thích từng ranh giới tin cậy, kèm ví dụ Java và các trường hợp cần kiểm thử.

## 1. Xác định những nơi dữ liệu đi vào email

Một email giao dịch có thể được xây dựng từ nhiều nguồn:

~~~text
HTTP request / message broker / webhook
                  |
                  v
          Dữ liệu chưa tin cậy
                  |
          +-------+--------+---------+----------+
          |                |         |          |
          v                v         v          v
      Địa chỉ           Subject    Template    Attachment
      To/Reply-To                  variables    filename/path
          |                |         |          |
          +-------+--------+---------+----------+
                  |
                  v
           Mail composition
                  |
                  v
        MimeMessageHelper / Jakarta Mail
                  |
                  v
              SMTP server
~~~

Các trường có tên khác nhau nhưng cùng một vấn đề: **chuỗi bên ngoài có thể đang được sử dụng để quyết định cấu trúc hoặc hành vi của một thông điệp có quyền gửi thư từ hệ thống**.

| Vị trí | Ví dụ đầu vào | Rủi ro nếu tin trực tiếp | Hàng rào phù hợp |
| --- | --- | --- | --- |
| **To/Cc/Bcc** | Email do API gửi lên | Gửi sai người, lạm dụng thành open mail relay | Authorization, parse địa chỉ, allowlist nghiệp vụ, rate limit |
| **From/Sender** | Giá trị client muốn dùng | Giả mạo thương hiệu hoặc tài khoản không được phép | Địa chỉ gửi cố định/đã được xác minh |
| **Reply-To** | Email phản hồi trên form | Chuyển phản hồi tới người khác hoặc header injection | Validate hộp thư; chỉ dùng khi nghiệp vụ cho phép |
| **Subject** | Tên đơn, tên người dùng | Chèn xuống dòng/header nếu ghép raw | Giới hạn độ dài, từ chối control chars, dùng setter |
| **Header tùy chỉnh** | Correlation ID, campaign | Header injection, rò rỉ dữ liệu | Giá trị tạo bởi server, validate định dạng |
| **Template name** | request.template | Render template ngoài ý định, truy cập file template khác | Enum/allowlist, mapping phía server |
| **Template variables** | displayName, comment | HTML/script injection hoặc phishing link | Context-specific escaping, validation theo trường |
| **Link trong HTML** | URL do đối tác gửi | Liên kết giả mạo, scheme độc hại | HTTPS và domain/route policy phía server |
| **Attachment filename** | upload filename | Header sai, path traversal nếu làm đường dẫn | Tên hiển thị an toàn; resource được chọn độc lập |
| **Attachment bytes** | file upload | Nội dung độc hại hoặc sai định dạng | Giới hạn, kiểm tra file, malware policy |

**Validation không thể tách khỏi ngữ cảnh.** Chuỗi có dấu xuống dòng là hợp lý trong phần mô tả văn bản, nhưng không phù hợp cho một header Subject. Một URL hợp lệ về cú pháp có thể vẫn nguy hiểm nếu trỏ đến domain không được phép. Một địa chỉ email đúng cú pháp có thể vẫn không được ứng dụng quyền gửi đến.

## 2. Phân biệt header, SMTP envelope và nội dung body

Một email không chỉ là chuỗi văn bản có To, Subject rồi phần body.

- **SMTP envelope** xác định người gửi/nhận trong quá trình chuyển thư, qua các lệnh như MAIL FROM và RCPT TO.
- **MIME/RFC message headers** chứa các trường như From, To, Subject, Reply-To, Date, Message-ID và Content-Type.
- **Message body** chứa văn bản, HTML hoặc MIME multipart/attachment.

Ví dụ minh họa:

~~~text
SMTP envelope:
    MAIL FROM:<bounce@example.test>
    RCPT TO:<customer@example.test>

Message headers:
    From: Orders <orders@example.test>
    To: customer@example.test
    Reply-To: support@example.test
    Subject: Xác nhận đơn hàng ORD-1528
    MIME-Version: 1.0
    Content-Type: text/plain; charset=UTF-8

Message body:
    Đơn hàng ORD-1528 đã được xác nhận.
~~~

**Header To không phải một cách bảo vệ envelope recipient.** Một hệ thống có thể thêm header To hợp lệ nhưng vô tình sử dụng recipient khác khi chuyển thư, hoặc ngược lại. Trong luồng Spring Mail thông thường, Jakarta Mail lấy recipient từ message để tạo envelope, song ứng dụng vẫn phải kiểm soát địa chỉ trước khi gọi sender.

### Control characters có thể phá vỡ ranh giới header

Các dòng header được tách bằng quy tắc giao thức. Nếu tự nối chuỗi chưa tin cậy vào raw MIME, ký tự **carriage return** và **line feed** (CR, LF) có thể làm thay đổi cách một chuỗi được hiểu thành các dòng header.

Ví dụ payload minh họa về ý tưởng chèn header:

~~~text
Xác nhận đơn hàng
Bcc: unexpected@example.test
~~~

Nếu mã ứng dụng ghép payload với raw header mà không xử lý đúng, chuỗi xuống dòng có thể bị hiểu là một header mới. Đó là **email header injection**. Bài học không giả định mọi phiên bản Jakarta Mail đều có thể bị khai thác bằng cùng một payload; vấn đề là **không để giá trị chưa tin cậy tự quyết định ranh giới header**.

### API có cấu trúc không có nghĩa đầu vào đã được ủy quyền

Một setter như:

~~~java
helper.setTo(recipient);
~~~

giúp thư viện xử lý địa chỉ theo API của nó, thay vì ứng dụng tự lắp ghép raw header. Nhưng nó **không biết người gọi có quyền gửi tới recipient đó không**. Nếu API cho người dùng chọn bất kỳ địa chỉ nào và gửi thư bằng domain của doanh nghiệp, ứng dụng có thể trở thành công cụ phát tán email dù không có lỗi chèn header.

Vì vậy, an toàn cần cả hai:

1. **Structural safety:** xây message bằng API chuyên dụng, validate loại dữ liệu và từ chối control characters tại nơi nhạy cảm.
2. **Business authorization:** người gọi chỉ được gửi loại notification tới những người nhận và địa chỉ gửi mà nghiệp vụ cho phép.

## 3. Không tự ghép raw email hoặc SMTP command

Một cách làm nguy hiểm là tự tạo email bằng nối chuỗi:

~~~java
String rawMessage =
        "From: " + from + "\r\n"
        + "To: " + recipient + "\r\n"
        + "Subject: " + request.subject() + "\r\n"
        + "\r\n"
        + request.body();
~~~

Đoạn mã này cho dữ liệu đầu vào tham gia trực tiếp vào cấu trúc header. Nó còn bỏ qua nhiều chi tiết chuẩn MIME như header encoding, line folding, multipart boundaries và content-transfer-encoding.

Tương tự, không xây lệnh SMTP thủ công:

~~~java
String command = "RCPT TO:<" + request.recipient() + ">";
~~~

Spring Mail/Jakarta Mail đã có API xử lý giao thức. Nếu ứng dụng tự xây raw SMTP command từ input, lỗi ranh giới giao thức có thể nghiêm trọng hơn nhiều so với việc gửi email sai định dạng.

### Dùng MimeMessageHelper

~~~java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, false, "UTF-8");

helper.setFrom("notifications@example.test");
helper.setTo(validatedRecipient);
helper.setSubject(validatedSubject);
helper.setText(plainTextBody, false);

mailSender.send(mimeMessage);
~~~

Ở đây:

- **From** do server quyết định.
- **validatedRecipient** phải qua validation và authorization.
- **validatedSubject** phải qua chính sách header input.
- **plainTextBody** là nội dung text, không phải chuỗi raw header.
- **MimeMessageHelper** xử lý thao tác tạo message.

Với thư HTML/multipart, helper cũng cung cấp overload dành cho HTML, inline resource và attachment; không phải tự thêm boundary trong chuỗi.

## 4. Chính sách xử lý chuỗi dùng trong header

Đối với **Subject**, tên hiển thị, correlation ID hoặc custom header value, nên có chính sách cụ thể:

1. Xác định trường có được để trống không.
2. Giới hạn độ dài theo nghiệp vụ.
3. Từ chối CR, LF, NUL và các ký tự điều khiển không được phép.
4. Không thay đổi dữ liệu theo cách che giấu payload nguy hiểm.
5. Chỉ truyền giá trị đã kiểm tra vào API header có cấu trúc.

### Một helper Java để từ chối control characters

~~~java
import java.util.Objects;

public final class MailHeaderValues {

    private MailHeaderValues() {
    }

    public static String requiredSingleLine(
            String value,
            String fieldName,
            int maxLength
    ) {
        Objects.requireNonNull(fieldName, "fieldName");
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " không được để trống"
            );
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(
                    fieldName + " vượt quá độ dài cho phép"
            );
        }

        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if (Character.isISOControl(ch)) {
                throw new IllegalArgumentException(
                        fieldName + " chứa ký tự điều khiển"
                );
            }
        }

        return value.strip();
    }
}
~~~

Ví dụ dùng cho Subject:

~~~java
String safeSubject = MailHeaderValues.requiredSingleLine(
        request.subject(),
        "subject",
        200
);
helper.setSubject(safeSubject);
~~~

**Giới hạn 200 ký tự là chính sách ví dụ**, không phải giới hạn RFC bắt buộc của Subject. Ứng dụng có thể dùng giới hạn khác theo sản phẩm; thư viện mail có cơ chế encode/fold header riêng. Hàm trên chủ yếu minh họa **không chấp nhận control characters** và giới hạn dữ liệu.

### Không áp dụng cùng quy tắc cho body

Body plain text có thể chứa xuống dòng, tab hoặc nhiều đoạn. Nếu áp helper single-line cho body, ứng dụng sẽ phá hỏng nội dung hợp lệ. Phải validate từng trường theo vị trí đích:

~~~text
Header Subject:      không cho CR/LF
MIME display name:   không cho control chars, validate chiều dài
Correlation ID:      định dạng hẹp do server tạo
Plain text body:     cho phép xuống dòng và ký tự văn bản phù hợp
HTML body:           escape theo ngữ cảnh HTML
~~~

Không nên chỉ xóa mọi ký tự lạ để “làm sạch”, vì có thể thay đổi ý nghĩa nghiệp vụ và khiến input độc hại biến thành một giá trị khác khó phát hiện. Với header, **từ chối đầu vào sai** thường rõ ràng hơn việc cố sửa chuỗi không đáng tin.

## 5. Kiểm tra địa chỉ email bằng Jakarta Mail

Địa chỉ email có cú pháp phức tạp hơn một chuỗi chỉ chứa dấu @. Jakarta Mail cung cấp **InternetAddress** để parse và validate địa chỉ theo các quy tắc mà implementation hỗ trợ.

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

InternetAddress[] addresses =
        InternetAddress.parse(inputAddress, true);

if (addresses.length != 1) {
    throw new IllegalArgumentException(
            "Phải cung cấp đúng một địa chỉ email"
    );
}

InternetAddress address = addresses[0];
address.validate();
~~~

Đoạn mã phân tích địa chỉ theo cú pháp mà Jakarta Mail hỗ trợ; nó **không chứng minh hộp thư tồn tại**, domain đang có MX record hoặc người gửi được quyền dùng địa chỉ đó.

### Một chính sách dành cho trường nhập một mailbox

Giả sử API có field **recipientEmail** và chỉ nhận một địa chỉ dạng mailbox thuần; không cho nhập display name, nhóm địa chỉ hoặc danh sách phân tách bằng dấu phẩy:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class MailAddressPolicy {

    private MailAddressPolicy() {
    }

    public static InternetAddress requireSingleMailbox(String input) {
        String value = MailHeaderValues.requiredSingleLine(
                input,
                "recipientEmail",
                320
        );

        try {
            InternetAddress[] parsed =
                    InternetAddress.parse(value, true);
            if (parsed.length != 1) {
                throw new IllegalArgumentException(
                        "Chỉ được cung cấp một mailbox"
                );
            }

            InternetAddress address = parsed[0];
            if (address.isGroup()) {
                throw new IllegalArgumentException(
                        "Không chấp nhận group address"
                );
            }
            address.validate();

            String mailbox = address.getAddress();
            int at = mailbox == null ? -1 : mailbox.lastIndexOf('@');
            if (at < 1 || at >= mailbox.length() - 1) {
                throw new IllegalArgumentException(
                        "Mailbox phải có local-part và domain"
                );
            }
            if (address.getPersonal() != null
                    || !value.equals(mailbox)) {
                throw new IllegalArgumentException(
                        "Chỉ nhận email thuần, không kèm tên hoặc comment"
                );
            }

            return address;
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Cú pháp địa chỉ email không hợp lệ",
                    ex
            );
        }
    }
}
~~~

**Chính sách trên cố ý hẹp hơn mọi biến thể email hợp lệ theo RFC.** Mục tiêu là một field API dành cho mailbox thuần, không phải hỗ trợ mọi cú pháp header email. Nếu sản phẩm phải hỗ trợ quoted local-part, internationalized email address, domain nội bộ hoặc SMTPUTF8, cần xác định yêu cầu cụ thể, kiểm tra phiên bản Jakarta Mail/provider và thiết kế validation tương ứng thay vì chỉ dựa vào một regex tự viết.

### Ví dụ đầu vào cần phân loại

| Đầu vào | Kết quả mong muốn trong field mailbox thuần | Lý do |
| --- | --- | --- |
| customer@example.test | Chấp nhận nếu được phép nhận | Một mailbox |
| customer+orders@example.test | Có thể chấp nhận | Plus tag thường là local-part hợp lệ |
| Customer Name <customer@example.test> | Từ chối theo policy này | API chỉ nhận địa chỉ, không nhận display name |
| first@example.test, second@example.test | Từ chối | Field chỉ cho một mailbox |
| customer@example.test kèm CR/LF | Từ chối | Control characters |
| group: first@example.test; | Từ chối | Group address không phù hợp |
| Địa chỉ có domain quốc tế | Theo policy/provider đã xác định | Cần xem IDN/SMTPUTF8 support |
| user@example.test nhưng không thuộc đơn hàng | Từ chối ở tầng authorization | Đúng cú pháp không đủ để được gửi |

**Không sử dụng email regex ngắn làm bảo đảm an ninh duy nhất.** Một regex tự chế có thể vừa chặn địa chỉ hợp lệ vừa bỏ sót trường hợp cần kiểm soát. Hãy dùng parser thư viện, chính sách mailbox của ứng dụng và authorization.

### Validation không thay thế deliverability

InternetAddress.validate() chủ yếu kiểm tra cú pháp theo implementation. Nó không kiểm tra:

- Người nhận đã xác minh quyền sở hữu email chưa.
- Người nhận có đang bị chặn hoặc unsubscribe không.
- Domain hay mailbox còn tồn tại không.
- SMTP server có chấp nhận recipient không.
- Nội dung thông báo có được gửi cho người đó không.

Những điều này cần policy nghiệp vụ, xác minh địa chỉ, phản hồi SMTP/provider và quản lý danh sách nhận thư.

## 6. To, Cc, Bcc và kiểm soát quyền gửi

Không nên chấp nhận một danh sách địa chỉ từ client rồi truyền nguyên vào **helper.setTo(...)**, **setCc(...)** hoặc **setBcc(...)** mà chưa kiểm tra.

Một luồng an toàn hơn:

~~~text
Request / Business Event
           |
           v
Kiểm tra user được phép tạo notification?
           |
           v
Truy vấn người nhận theo dữ liệu nghiệp vụ đáng tin cậy
           |
           v
Kiểm tra consent / trạng thái / tenant boundary
           |
           v
Parse từng mailbox, reject invalid
           |
           v
Áp chính sách dedup và phân nhóm To/Cc/Bcc
           |
           v
MimeMessageHelper.setTo/setCc/setBcc
~~~

### Authorization quan trọng hơn quyền tự nhập địa chỉ

Ví dụ một API:

~~~text
POST /orders/ORD-1528/send-confirmation
~~~

Người gọi cung cấp order ID. Server nên tra đơn hàng, kiểm tra quyền truy cập rồi lấy email người nhận từ **đơn hàng/khách hàng đã được xác thực**. Không nên cho client thay thế thành một email bất kỳ và gửi thư nhân danh hệ thống.

Nếu nghiệp vụ cho phép thêm recipient mới, hãy yêu cầu xác minh/quyền rõ ràng và giới hạn loại mail có thể gửi. Ví dụ form “mời đồng nghiệp” cần chống spam, rate limit và chống giả mạo, không được tận dụng quyền gửi hóa đơn của backend.

### Dedup không có một quy tắc phổ quát

Nếu cùng địa chỉ xuất hiện ở To, Cc và Bcc, hệ thống cần một chính sách xác định:

- Có thể giữ một bản duy nhất ở nhóm ưu tiên.
- Có thể từ chối request để yêu cầu làm sạch dữ liệu.
- Có thể xử lý theo recipient ID thay vì so sánh chuỗi email thuần.

Đừng tự lower-case toàn bộ email để dedup mà không hiểu quy tắc local-part; phần domain không phân biệt chữ hoa/thường, còn local-part về mặt giao thức có các lưu ý riêng và provider có quy tắc alias khác nhau. Không tự loại plus tag hoặc dấu chấm theo quy tắc riêng của một provider nếu nghiệp vụ không định nghĩa như vậy.

### Bcc là ranh giới riêng tư

**Bcc** được dùng để tránh lộ danh sách người nhận ẩn cho người nhận khác. Một lỗi nghiêm trọng là:

- Đặt toàn bộ danh sách Bcc vào trường To.
- Render danh sách Bcc vào body hoặc template.
- Ghi raw recipient list trong log chia sẻ rộng.
- Dùng email API tùy biến tạo header Bcc không được xử lý đúng.

Khi gửi thư tới nhiều khách hàng độc lập, nên cân nhắc **một message cho mỗi recipient** để tránh lộ địa chỉ và đơn giản hóa tracking/deduplication. Không dựa hoàn toàn vào Bcc cho các chiến dịch có yêu cầu cá nhân hóa và riêng tư nghiêm ngặt.

### Dùng các API typed addresses

~~~java
InternetAddress to = MailAddressPolicy.requireSingleMailbox(
        trustedRecipientEmail
);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setTo(to);
helper.setFrom("orders@example.test");
helper.setSubject("Xác nhận đơn hàng");
helper.setText("Đơn hàng đã được xác nhận.");
~~~

Việc tách **trustedRecipientEmail** từ dữ liệu nghiệp vụ đã được authorization ra khỏi **InternetAddress** parse sẽ làm rõ hai lớp kiểm soát: **được phép gửi** và **địa chỉ có cú pháp phù hợp**.

## 7. From, Sender, Reply-To và chống giả mạo

Một trong những sai lầm dễ tạo lỗ hổng lạm dụng là dùng địa chỉ do người dùng nhập làm **From** của thư gửi từ SMTP account doanh nghiệp.

Ví dụ không nên:

~~~java
helper.setFrom(request.email());
~~~

Nếu đây là form liên hệ, kẻ tấn công có thể nhập địa chỉ của bất kỳ người nào và khiến hệ thống tạo email trông như được gửi từ họ. Ngoài rủi ro giả mạo, domain người khác có thể không khớp SPF/DKIM/DMARC policy, dẫn đến thư bị đánh dấu spam hoặc từ chối.

### Chọn From từ cấu hình đáng tin cậy

~~~java
private static final String MAIL_FROM =
        "support@example.test";

helper.setFrom(MAIL_FROM);
~~~

Nếu sản phẩm có nhiều tenant/domain được ủy quyền gửi, lựa chọn From phải đi qua **allowlist sender identity** đã được xác minh ở provider, không lấy tùy ý từ request.

### Khi người dùng cần nhận phản hồi

Form liên hệ có thể dùng:

~~~java
helper.setFrom("contact-form@example.test");
helper.setReplyTo(
        MailAddressPolicy.requireSingleMailbox(
                submittedContactEmail
        )
);
~~~

Đây là cách tách người gửi thực tế khỏi địa chỉ nhận phản hồi. Tuy nhiên, **Reply-To cũng là header có thể bị lạm dụng**: cần validate địa chỉ và chỉ sử dụng khi nghiệp vụ cho phép. Nếu đó là địa chỉ người dùng khai báo chưa được xác minh, nội dung email nên ghi rõ “địa chỉ phản hồi do người gửi form cung cấp” chứ không khẳng định quyền sở hữu.

### Không cho request kiểm soát envelope sender tùy ý

Địa chỉ **MAIL FROM** trong SMTP envelope liên quan xử lý bounce/return-path và có thể được cấu hình bằng transport/provider. Nó không phải lúc nào cũng trùng **From** trong visible header.

Không dùng tham số transport hoặc SMTP property do request gửi lên để đổi envelope sender, SMTP host, username hoặc return-path. Đây là cấu hình hạ tầng và sender identity thuộc chính sách server.

### Display name cũng không được ghép raw

Tên người gửi hiển thị cần được tạo bằng API hỗ trợ encoding thay vì nối chuỗi dạng:

~~~java
String rawFrom = request.displayName()
        + " <support@example.test>";
~~~

Ví dụ dùng InternetAddress với charset:

~~~java
import jakarta.mail.internet.InternetAddress;
import java.nio.charset.StandardCharsets;

String displayName = MailHeaderValues.requiredSingleLine(
        configuredBrandName,
        "brandName",
        120
);

InternetAddress from = new InternetAddress(
        "support@example.test",
        displayName,
        StandardCharsets.UTF_8.name()
);

helper.setFrom(from);
~~~

Ví dụ giả định địa chỉ gửi và brand name đều được xác định bởi cấu hình đáng tin cậy; constructor phù hợp có thể ném checked exception, phương thức bao ngoài cần khai báo hoặc xử lý. Thư viện chịu trách nhiệm encode personal name theo cơ chế email header. Việc validate control characters vẫn là lớp phòng vệ độc lập.

## 8. Custom headers, Message-ID và correlation ID

Một hệ thống có thể thêm header phục vụ tracking:

~~~java
message.setHeader(
        "X-Notification-ID",
        validatedNotificationId
);
~~~

Tại đây có hai thành phần:

- **Header name** nên là hằng số hoặc được chọn từ tập cố định do server định nghĩa.
- **Header value** nên có định dạng hẹp, ví dụ UUID, chứ không phải chuỗi tự do từ user.

Không viết:

~~~java
message.setHeader(
        request.headerName(),
        request.headerValue()
);
~~~

Chỉ vì MimeMessage cho phép setHeader không có nghĩa client được quyền chọn mọi header. Người dùng có thể cố gắng can thiệp Return-Path, Reply-To, Content-Type hoặc các header hệ thống khác, gây spoofing hoặc làm sai MIME structure.

### Sử dụng UUID do server tạo

~~~java
import java.util.UUID;

UUID notificationId = UUID.randomUUID();
message.setHeader(
        "X-Notification-ID",
        notificationId.toString()
);
~~~

Nếu ID được lưu trong outbox và dùng qua nhiều lần retry, giữ **notification ID ổn định**. Header này phục vụ correlation; nó **không tự ngăn SMTP gửi trùng** và không thay thế idempotency ở database/provider.

### Message-ID không phải cơ chế authorization

**Message-ID** là định danh phục vụ email processing/threading/tracing, không chứng minh một message được gửi bởi người có quyền. Dù một message có header Message-ID hợp lệ, vẫn cần SPF/DKIM/DMARC và chính sách identity phù hợp; và cũng không nên coi Message-ID là bằng chứng message đã được SMTP chấp nhận hoặc delivered.

### Đừng để dữ liệu nhạy cảm vào headers

Headers có thể được lưu trong log provider, hiển thị ở chế độ “Show original” của email client hoặc đi qua nhiều hệ thống trung gian. Không đặt password reset token, OTP, API key, bearer token, địa chỉ nội bộ nhạy cảm hoặc PII không cần thiết vào custom header, Message-ID hay correlation ID.

## 9. Dữ liệu trong template không phải template source

Một email HTML có thể được render bằng **Thymeleaf**, FreeMarker, Mustache hoặc một template engine khác. Có hai khái niệm cần tách biệt:

1. **Template source**: cấu trúc do developer quản lý, chứa HTML, điều kiện và biểu thức template.
2. **Template data**: các giá trị như tên người nhận, tên sản phẩm, địa chỉ giao hàng hoặc ghi chú.

### Cách sử dụng an toàn

~~~text
Template source cố định và được review
            |
            v
TemplateEngine + Context
            ^
            |
Data model đã validate, được escape theo ngữ cảnh
            |
            v
Email HTML/plain text
~~~

Ví dụ:

~~~java
Context context = new Context(locale);
context.setVariable("recipientName", recipientName);
context.setVariable("orderNumber", orderNumber);

String html = templateEngine.process(
        "mail/order-confirmed",
        context
);
~~~

Ở đây, tên template là hằng số do server quyết định; **recipientName** là dữ liệu được đặt vào Context. Template engine xử lý biểu thức thuộc template source, không phải đánh giá mọi ký tự trong recipientName như source code template.

### Cách làm nguy hiểm: dựng template source từ input

Ví dụ tư duy cần tránh:

~~~java
String rawTemplate =
        "<html><body><p>" + request.displayName()
        + "</p></body></html>";
~~~

Nếu chuỗi này được dùng như HTML cuối cùng, dữ liệu người dùng có thể trở thành markup. Nếu nó được đưa vào một template engine như **source template** rồi đánh giá, dữ liệu có thể ảnh hưởng tới cú pháp/binding mà engine xử lý.

Đây là hai dạng rủi ro khác nhau:

- **HTML injection:** dữ liệu được coi là markup của email.
- **Server-side template injection (SSTI):** dữ liệu không đáng tin được sử dụng như cú pháp hoặc source template để engine đánh giá.

Không phải mọi chuỗi chứa ký hiệu template đều tự động là SSTI. Nếu chuỗi là **giá trị dữ liệu trong Context** và được render qua escaping phù hợp, ký hiệu đó thường chỉ được hiển thị như văn bản. Rủi ro tăng khi ứng dụng **tự ghép template source**, hỗ trợ dynamic expression evaluation hoặc xử lý lặp kết quả render như template mới.

## 10. Thymeleaf: dùng th:text cho dữ liệu văn bản

Một template HTML có thể có:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Xác nhận đơn hàng</h1>

  <p>
    Xin chào,
    <strong th:text="${mail.displayName}">bạn</strong>.
  </p>

  <p>
    Mã đơn:
    <span th:text="${mail.orderNumber}">ORD-000</span>
  </p>

  <p th:text="${mail.customerNote}">
    Ghi chú đơn hàng.
  </p>
</body>
</html>
~~~

**th:text** hiển thị giá trị như nội dung văn bản và thực hiện escaping HTML phù hợp. Ví dụ một tên chứa dấu nhỏ hơn/lớn hơn hoặc chuỗi trông giống tag không được coi như thẻ HTML mới chỉ vì người dùng đã nhập nó.

### Tránh th:utext với dữ liệu người dùng

Thymeleaf có **th:utext** để xuất nội dung không HTML-escape. Ví dụ:

~~~html
<div th:utext="${mail.customerNote}"></div>
~~~

Không nên sử dụng nó cho ghi chú khách hàng, tên người dùng hoặc nội dung không đáng tin. Nếu dữ liệu chứa markup, markup đó có thể được đưa vào email thay vì hiển thị như văn bản.

Email client có các cơ chế lọc HTML khác nhau, và nhiều client chặn script. Nhưng **không nên dựa vào bộ lọc của email client như một hàng rào bảo mật duy nhất**. Markup độc hại vẫn có thể tạo liên kết lừa đảo, bố cục gây nhầm lẫn, ảnh tracking hoặc nội dung không phù hợp.

### Khi thật sự cần rich text từ người dùng

Một số sản phẩm cho phép người dùng soạn nội dung có định dạng, ví dụ thông báo từ quản trị viên hoặc lời nhắn có bold/italic/link.

Khi đó, nên:

1. Xác định rõ định dạng đầu vào (Markdown, một rich-text document model, HTML giới hạn).
2. Chuyển đổi bằng parser đáng tin cậy.
3. **Sanitize HTML theo allowlist** tag/attribute/protocol được phép.
4. Kiểm soát URL của các link và ảnh.
5. Test trên nhiều email client.

Không dùng regex tự chế để “xóa script” rồi coi HTML an toàn. HTML có nhiều cách biểu diễn và thuộc tính khác nhau; cần một HTML sanitizer được thiết kế cho việc đó.

### Không đưa entity đầy đủ vào template context

Nếu truyền nguyên một JPA entity hoặc domain object phức tạp vào Context:

~~~java
context.setVariable("user", userEntity);
~~~

template có thể vô tình truy cập thuộc tính nhạy cảm, lazy association hoặc dữ liệu không liên quan. Ưu tiên mail model có tập trường nhỏ:

~~~java
public record OrderConfirmedMailModel(
        String displayName,
        String orderNumber,
        String customerNote,
        String actionUrl
) {
}
~~~

Một model cụ thể giúp giới hạn dữ liệu được phép xuất hiện trong thư, hỗ trợ review template và tránh coupling trực tiếp tới database entities.

## 11. Escaping HTML không đồng nghĩa URL an toàn

Trong HTML email, ứng dụng thường có nút hành động:

~~~html
<a th:href="${mail.actionUrl}">Xem đơn hàng</a>
~~~

Template engine có thể escape ký tự đặc biệt của attribute, nhưng **escaping không tự kiểm tra scheme/domain hoặc quyền truy cập URL**. Một URL vẫn có thể dẫn người dùng đến nơi không đáng tin nếu nó hợp lệ về cú pháp nhưng trỏ tới domain của kẻ tấn công.

### Những điều cần xác định cho URL

- Chỉ chấp nhận scheme phù hợp, thường là **HTTPS** cho liên kết hành động.
- Host phải thuộc allowlist **chính xác**, không so bằng chuỗi chứa một substring.
- Không cho URL chứa userinfo nếu không cần.
- Chọn port/path theo chính sách.
- Không dùng URL do client cung cấp làm domain gốc cho reset password.
- Kiểm tra open redirect ở endpoint đích.
- Không đưa token nhạy cảm vào log, referrer hoặc analytics ngoài ý định.

### Ví dụ chính sách URL hành động

~~~java
import java.net.URI;
import java.util.Locale;
import java.util.Set;

public final class MailActionUrlPolicy {

    private static final Set<String> ALLOWED_HOSTS = Set.of(
            "app.example.test",
            "accounts.example.test"
    );

    private MailActionUrlPolicy() {
    }

    public static URI requireTrustedHttpsUrl(String rawUrl) {
        if (rawUrl == null || rawUrl.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu URL hành động"
            );
        }

        final URI uri;
        try {
            uri = URI.create(rawUrl);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "URL không hợp lệ",
                    ex
            );
        }

        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException(
                    "Chỉ chấp nhận HTTPS"
            );
        }
        if (uri.getRawUserInfo() != null) {
            throw new IllegalArgumentException(
                    "URL không được chứa userinfo"
            );
        }

        String host = uri.getHost();
        if (host == null
                || !ALLOWED_HOSTS.contains(
                        host.toLowerCase(Locale.ROOT)
                )) {
            throw new IllegalArgumentException(
                    "Host không nằm trong allowlist"
            );
        }
        if (uri.getPort() != -1 && uri.getPort() != 443) {
            throw new IllegalArgumentException(
                    "Port không được phép"
            );
        }

        return uri;
    }
}
~~~

Ví dụ này chủ động chỉ hỗ trợ các hostname ASCII trong allowlist. Nếu cần hỗ trợ internationalized domain names, phải có chính sách IDNA/canonicalization phù hợp. Một hệ thống thực tế còn có thể hạn chế **path prefix**, loại query parameter, fragment và redirect target theo loại notification.

### Không kiểm tra host bằng endsWith không có dấu phân cách

Ví dụ không nên:

~~~java
if (url.contains("example.test")) {
    // Cho phép.
}
~~~

Giá trị sau cũng có thể chứa chuỗi example.test:

~~~text
https://example.test.attacker.invalid/
https://attacker.invalid/redirect?next=example.test
~~~

Việc dùng **URI.getHost()** và allowlist host chính xác giúp tránh nhầm lẫn đơn giản này. Nếu chấp nhận subdomain, chỉ cho phép theo quy tắc có dấu phân cách và bảo đảm chủ sở hữu miền con đáng tin; cũng nên chống DNS rebinding/SSRF nếu URL được fetch ở server.

### Tạo URL từ cấu hình server, không từ Host header tùy ý

Một sai lầm khác là tạo link khôi phục mật khẩu bằng cách lấy domain trực tiếp từ HTTP Host hoặc forwarded host header không được chuẩn hóa:

~~~text
https://<request-host>/reset-password?token=...
~~~

Nếu proxy/backend tin Host header do client điều khiển, email có thể chứa link về domain của kẻ tấn công. Nên dùng **public base URL** đã được cấu hình, hoặc tenant domain đã được xác minh theo allowlist. Điều này giảm nguy cơ **password-reset link poisoning**.

## 12. Template name và fragment phải theo allowlist

Không nên để client điều khiển tên file template:

~~~java
String html = templateEngine.process(
        request.templateName(),
        context
);
~~~

Tùy resolver và cách triển khai, tên template không tin cậy có thể truy cập template ngoài chức năng dự định, gây lỗi đường dẫn hoặc làm lộ nội dung template nội bộ. Với engine hỗ trợ expression evaluation động, cho client cung cấp expression còn có rủi ro khác.

### Chọn template bằng enum hoặc business event

~~~java
public enum NotificationType {
    ORDER_CONFIRMED,
    PASSWORD_RESET,
    ACCOUNT_ACTIVATED
}
~~~

~~~java
public final class MailTemplateCatalog {

    private MailTemplateCatalog() {
    }

    public static String pathFor(NotificationType type) {
        return switch (type) {
            case ORDER_CONFIRMED -> "mail/order-confirmed";
            case PASSWORD_RESET -> "mail/password-reset";
            case ACCOUNT_ACTIVATED -> "mail/account-activated";
        };
    }
}
~~~

~~~java
String templatePath =
        MailTemplateCatalog.pathFor(command.notificationType());

String html = templateEngine.process(templatePath, context);
~~~

Ứng dụng phải xác định **NotificationType** từ thao tác nghiệp vụ đã được ủy quyền. Nếu request gửi enum trực tiếp, vẫn cần kiểm tra user có quyền phát loại thông báo đó. Enum giải quyết rủi ro tên template tùy ý, **không tự cung cấp authorization**.

### Không evaluate expression do người dùng gửi

Các cách làm nguy hiểm gồm:

- Cho user điền expression của template engine rồi evaluate bằng quyền của server.
- Đưa HTML từ user vào một template source sau đó render lại.
- Tạo tên fragment bằng cách nối input vào cú pháp template expression.
- Để webhook bên ngoài chọn template file path bất kỳ.

Với dữ liệu giàu định dạng cần render, chỉ lưu nó như data; dùng cấu trúc template do ứng dụng kiểm soát. Nếu sản phẩm là template editor cho người dùng quản trị, cần sandbox, giới hạn biểu thức và quyền truy cập dữ liệu riêng — đó là một bài toán bảo mật rộng hơn gửi mail thông thường.

### Template version và dữ liệu đã snapshot

Email giao dịch cần retry có thể được render sau thời điểm event xảy ra. Nếu template hoặc dữ liệu nghiệp vụ thay đổi, cùng notification có thể tạo nội dung khác qua các lần retry. Lưu **template code/version** và dữ liệu snapshot cần thiết giúp giải thích được nội dung nào đã gửi.

Không dùng việc “đổi template khi retry” để tạo thêm những side effect bất ngờ. Retry cùng notification và resend có chủ đích nên có hợp đồng riêng.

## 13. Không để nội dung người dùng quyết định HTML structure

Ngoài XSS cổ điển, nội dung HTML email có thể bị lạm dụng để khiến người nhận hiểu sai nguồn gốc thông báo, click vào domain khác hoặc tiết lộ dữ liệu.

### Trường hợp tên sản phẩm chứa markup

Giả sử một sản phẩm trong marketplace được đặt tên:

~~~text
<strong>Giảm giá đặc biệt</strong>
~~~

Nếu ứng dụng nối trực tiếp nó vào HTML:

~~~java
String html = "<p>Sản phẩm: " + productName + "</p>";
~~~

thì phần tên có thể trở thành markup. Nếu đi qua một biến hiển thị bằng **th:text**, dấu nhỏ hơn/lớn hơn được escape thành văn bản; người nhận thấy tên thực tế chứ không phải HTML do sản phẩm cung cấp.

### CSS và attribute động cũng có rủi ro

Các trường như:

~~~html
<div style="background-image: url(...)">
<a href="...">
<img src="...">
~~~

không có cùng semantics với văn bản thuần. Không chỉ cần escape dấu nháy mà còn phải kiểm tra **protocol, host và giá trị CSS/HTML attribute được phép**. Với email giao dịch, nên giữ HTML structure/CSS từ template đáng tin và chỉ dùng biến để chèn các giá trị hiển thị có kiểm soát.

Không dùng input của user để định nghĩa toàn bộ **style**, **href**, **src** hoặc nội dung script nếu không có một cơ chế validation chuyên biệt. Email client có thể sửa, bỏ hoặc cho phép các thành phần khác nhau; không nên đặt an toàn vào sự may rủi của client.

### URL hiển thị và URL đích phải tương ứng

Một email có thể hiển thị:

~~~text
Nhấn để đăng nhập tại app.example.test
~~~

nhưng thẻ HTML lại trỏ tới một domain khác nếu phần href được lấy từ request. Điều này tạo nguy cơ phishing ngay cả khi HTML không có script.

Hãy tạo cả nhãn và URL từ một action model đáng tin cậy; không để người dùng tùy ý gắn nhãn thương hiệu với một URL không được phép.

### Sanitizer khác encoder

**Encoder/escaping** biến dữ liệu văn bản thành dạng an toàn để đặt trong ngữ cảnh cụ thể (HTML text hoặc attribute). **HTML sanitizer** nhận một tài liệu HTML có chủ đích rồi loại bỏ/điều chỉnh các phần không được phép.

Nếu người dùng chỉ nhập tên hoặc ghi chú thông thường, hãy **escape như text**. Chỉ dùng sanitizer khi sản phẩm thật sự cho phép HTML/rich text. Việc cố “sanitize” toàn bộ input ở tầng database thường gây mất dữ liệu và không thay thế escaping tại output.

## 14. Plain text và HTML cùng một hợp đồng dữ liệu

Một email có thể có cả text/plain và text/html:

~~~java
helper.setText(plainText, htmlText);
~~~

Hai phiên bản này nên được render từ **cùng một mail model đã được validation/normalization**:

~~~text
Trusted Order Mail Model
          |
          +--> HTML template (escaped text, trusted URLs)
          |
          '--> Plain template (đầy đủ nội dung thiết yếu)
          |
          v
    MimeMessageHelper.setText(plain, html)
~~~

Một số lỗi liên quan:

- HTML dùng URL đã kiểm tra, plain text dùng URL raw từ request.
- HTML ẩn trường không hợp lệ, plain text vẫn chèn chuỗi chưa kiểm tra.
- HTML dùng tên người nhận từ model, plain text lại nối trực tiếp từ HTTP request.
- HTML có nội dung quan trọng trong ảnh, plain text không có lời giải thích.

Plain text không có HTML injection theo cùng cách HTML, nhưng vẫn có thể chứa **liên kết lừa đảo, thông tin sai hoặc dữ liệu nhạy cảm** nếu đầu vào không được ủy quyền.

### Giới hạn độ dài và dữ liệu bí mật

Đối với trường **customerNote** trong body:

- Giới hạn độ dài hợp lý để tránh email cực lớn.
- Quy định có cho phép dòng mới/tab không.
- Không đưa token, mật khẩu, thông tin thẻ thanh toán hoặc dữ liệu nội bộ vào template nếu không thực sự cần.
- Có thể loại thông tin nhạy cảm ở nguồn thay vì chỉ hy vọng template không hiển thị.

Validation về độ dài là để bảo đảm ổn định và tránh lạm dụng tài nguyên; **escaping** ở điểm render mới xử lý ý nghĩa đặc biệt của ký tự HTML.

## 15. Tên tệp đính kèm không được trở thành đường dẫn hệ thống

File upload thường cung cấp một filename do client khai báo. Nếu ứng dụng dùng tên này như đường dẫn trên server:

~~~java
Path path = uploadDirectory.resolve(
        request.originalFilename()
);
~~~

thì một tên chứa path separators hoặc chuỗi điều hướng thư mục có thể khiến ứng dụng truy cập tệp ngoài thư mục dự kiến nếu không có kiểm soát phù hợp.

**Attachment filename** và **storage resource path** phải được tách thành hai khái niệm:

- **Storage key/path**: do server tạo, dùng để tìm byte file đã được lưu và kiểm tra.
- **Display filename**: tên hiển thị cho người nhận; chỉ là metadata MIME, không phải đường dẫn filesystem.

### Ví dụ tách storage key và display name

~~~java
public record ValidatedAttachment(
        String displayFilename,
        String contentType,
        Resource resource
) {
}
~~~

~~~java
helper.addAttachment(
        attachment.displayFilename(),
        attachment.resource(),
        attachment.contentType()
);
~~~

Record chỉ biểu diễn dữ liệu *sau khi* lớp upload/attachment policy đã kiểm tra; nó không tự validate file. Resource cần được chọn bởi service theo ID hoặc storage key đáng tin, không phải được resolve trực tiếp từ một filename do client gửi.

### Giới hạn filename dùng trong MIME

Một tên hiển thị an toàn có thể tuân theo:

- Không chứa CR/LF hoặc control chars.
- Không chứa đường dẫn tuyệt đối hoặc path separator.
- Không chứa các segment điều hướng thư mục.
- Có độ dài và phần mở rộng phù hợp.
- Không tiết lộ filesystem path, username nội bộ hoặc PII không cần thiết.
- Không có dấu hiệu gây nhầm lẫn, ví dụ extension kép nhằm giả loại file.

Ví dụ một bộ lọc filename tối giản dành cho filename do ứng dụng sinh:

~~~java
public final class AttachmentNames {

    private AttachmentNames() {
    }

    public static String requireSimpleName(String input) {
        String name = MailHeaderValues.requiredSingleLine(
                input,
                "filename",
                180
        );

        if (name.equals(".") || name.equals("..")
                || name.contains("/")
                || name.contains("\\")
                || name.contains("..")) {
            throw new IllegalArgumentException(
                    "Tên file không được chứa đường dẫn"
            );
        }
        return name;
    }
}
~~~

**Đây là ví dụ chính sách filename đơn giản**, không phải bộ lọc đầy đủ mọi nguy cơ về Unicode, tên file hệ điều hành, reserved names hay extension. Với file người dùng upload, nên tạo tên hiển thị từ metadata đã được chuẩn hóa và dùng storage key do server kiểm soát.

### MIME Content-Type cũng không đáng tin nếu lấy từ upload

Một HTTP upload có thể khai báo:

~~~text
Content-Type: image/png
filename="logo.png"
~~~

Nhưng byte thực tế có thể không phải PNG. Dùng **FileTypeMap** suy luận theo extension cũng không xác minh nội dung file. Nếu hệ thống cho phép chuyển tiếp tệp vào email:

1. Áp allowlist loại tệp.
2. Giới hạn kích thước từng tệp và tổng email.
3. Kiểm tra extension, MIME metadata và signature/format theo rủi ro.
4. Quét malware theo chính sách.
5. Tạo MIME type từ kết quả đáng tin phía server.
6. Chỉ đính kèm Resource đã được phép truy cập.

Đừng đổi một file bất kỳ thành application/pdf trong header để nó trông như PDF; Content-Type chỉ mô tả dữ liệu, không chuyển đổi bytes.

### File ZIP, tài liệu Office và nội dung phức tạp

Một tệp ZIP có thể chứa file nguy hiểm hoặc lượng dữ liệu giải nén rất lớn. Một tài liệu Office có thể chứa nội dung chủ động hoặc macro tùy định dạng. Validation có thể cần kiểm tra cấu trúc bên trong theo mức rủi ro, không chỉ nhìn đuôi tệp.

Không giải nén file từ người dùng vào một thư mục chung nếu chưa kiểm soát path traversal trong archive, giới hạn tổng dung lượng giải nén và độ sâu lồng tệp. Đây là một phần của security boundary trước khi tệp trở thành attachment hợp lệ.

## 16. Inline images, URL tải tài nguyên và nguy cơ SSRF

Trong HTML email, ảnh có thể là:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

hoặc:

~~~html
<img src="https://static.example.test/logo.png" alt="Logo">
~~~

**CID image** được đính kèm như inline MIME resource; **remote image** được email client tải từ URL nếu được phép. Hai cách có rủi ro khác nhau.

### Không fetch URL tùy ý từ request

Ví dụ nguy hiểm:

~~~java
URL remote = new URL(request.logoUrl());
byte[] content = remote.openStream().readAllBytes();
~~~

Nếu backend được phép truy cập mạng nội bộ, một URL do user kiểm soát có thể dẫn tới **server-side request forgery (SSRF)** hoặc làm tải nội dung quá lớn. Không tự động biến mọi URL người dùng cung cấp thành byte ảnh inline.

Nếu sản phẩm bắt buộc tải ảnh từ bên ngoài:

- Áp allowlist hostname và scheme.
- Resolve DNS và kiểm tra chặn private/loopback/link-local addresses theo mô hình mạng.
- Kiểm soát redirect đích, không chỉ URL ban đầu.
- Đặt timeout, giới hạn kích thước, loại nội dung và số lần redirect.
- Không chuyển credentials/cookies nội bộ tới URL ngoài.
- Cân nhắc dùng service fetch ảnh tách biệt/sandbox.

Một cách đơn giản hơn cho email giao dịch là dùng **logo Resource cố định** từ classpath hoặc object storage tin cậy, không sử dụng URL upload chưa kiểm tra.

### Content-ID do server quyết định

~~~java
helper.setText(plainBody, htmlBody);
helper.addInline(
        "brand-logo",
        trustedLogoResource,
        "image/png"
);
~~~

HTML phải tham chiếu đúng **cid:brand-logo**. Không cho user chọn Content-ID tùy ý, sửa raw MIME body part hoặc ghi đè Content-Type/Content-Disposition của resource. Cấu trúc multipart/related nên do helper và mail composer kiểm soát.

## 17. SMTP credentials và transport policy là cấu hình server

Dù bài tập trung vào header, địa chỉ và template, ranh giới tin cậy không dừng ở đó. **SMTP host, port, username, password, TLS mode và connection timeout** không nên là tham số request từ người dùng.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Các timeout tính bằng mili giây và chỉ là ví dụ; cần cấu hình theo provider/thực tế triển khai. **Bật TLS/STARTTLS và kiểm tra hostname** phù hợp với server hỗ trợ, không tắt xác minh chứng chỉ để chữa lỗi cấu hình.

Credential nên lấy từ secret manager, environment injection an toàn hoặc cơ chế quản lý bí mật của tổ chức, không hard-code trong code repository. Tránh log session properties có chứa username/password hoặc nội dung AUTH.

### Không cho request chọn SMTP server

Ví dụ không nên:

~~~java
sender.setHost(request.smtpHost());
sender.setUsername(request.smtpUser());
sender.setPassword(request.smtpPassword());
~~~

Đây là việc cho người dùng điều khiển transport của ứng dụng. Ngoài nguy cơ gửi thư ngoài quyền, nó có thể tạo kết nối tới host không mong muốn, rò rỉ credentials hoặc làm hỏng chính sách TLS.

Nếu sản phẩm thực sự cung cấp dịch vụ “bring your own SMTP”, đó là một chức năng quản trị riêng cần xác thực, kiểm tra host, lưu trữ secret, kiểm soát quyền tenant và egress policy; không phải tham số tùy ý của endpoint gửi mail giao dịch.

### Domain authentication và khả năng phát thư

Địa chỉ From đã được xác minh cùng SPF/DKIM/DMARC giúp giảm spoofing và cải thiện khả năng nhận thư. Tuy nhiên các cơ chế này không thể thay thế kiểm soát đầu vào bên trong ứng dụng:

- SPF/DKIM/DMARC không quyết định user có quyền gửi hóa đơn cho người khác.
- DKIM ký một message có nội dung độc hại không làm nội dung đó an toàn.
- Header encoding đúng không ngăn phishing link.

Do đó, cần kiểm soát cả **sender/domain identity** ở tầng SMTP/provider và **business/content integrity** ở tầng ứng dụng.

## 18. Thiết kế luồng gửi email có ranh giới tin cậy rõ

Một kiến trúc dễ quản lý có thể chia thành bốn lớp:

~~~text
HTTP API / Webhook / Domain Event
             |
             v
       Authorization Layer
       - user/tenant permissions
       - event/recipient policy
             |
             v
       Mail Data Preparation
       - query trusted business data
       - normalize/validate fields
       - build server-controlled links
       - select template code from allowlist
             |
             v
       Mail Composition Layer
       - parse mailbox
       - safe headers/from/reply-to
       - render HTML + plain template
       - choose validated attachments
             |
             v
       JavaMailSender / SMTP Provider
       - credentials/TLS/timeouts
       - logging and delivery tracking
~~~

### Trách nhiệm từng lớp

| Lớp | Biết gì? | Không được tin điều gì? |
| --- | --- | --- |
| API/Event handler | Ai yêu cầu thao tác, event nào vừa xảy ra | Địa chỉ gửi, template path, SMTP host do client chọn |
| Business service | Đơn hàng, tài khoản, quyền của người nhận | Quyền chỉ được suy ra từ email string |
| Mail preparation | Những dữ liệu có thể đưa vào notification | Raw URL, raw HTML và raw attachment path |
| Mail composer | Template code, header policy, MIME structure | Field chưa được chuẩn hóa/ủy quyền |
| Transport | SMTP configuration, identity, TLS | Người dùng request tự chọn credentials/host |

### Example: DTO giữa business service và mail composer

~~~java
public record OrderConfirmedNotice(
        String recipientEmail,
        String displayName,
        String orderNumber,
        String actionUrl,
        String customerNote
) {
}
~~~

**OrderConfirmedNotice** không nên được bind trực tiếp từ HTTP request public rồi đưa ngay vào mail composer. Nó phải được tạo bởi business service sau khi xác định đơn hàng thuộc tenant nào, ai là người nhận và nội dung nào hợp lệ.

Nếu thông báo đi qua queue/outbox, record này có thể là dữ liệu snapshot được ký hiệu bằng event ID, có version và quyền đọc cụ thể. Worker phải bảo đảm queue data đến từ nguồn được ủy quyền trước khi sử dụng.

## 19. Ví dụ Spring: gửi email với sender cố định, recipient đã kiểm tra và template cố định

Service dưới đây trình bày cách nối các lớp validation lại với nhau trong một luồng mail:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.net.URI;
import java.util.Locale;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class SecureOrderMailComposer {

    private static final String FROM =
            "orders@example.test";
    private static final String REPLY_TO =
            "support@example.test";
    private static final String TEMPLATE =
            "mail/order-confirmed";

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;

    public SecureOrderMailComposer(
            JavaMailSender mailSender,
            TemplateEngine templateEngine
    ) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
    }

    public void send(OrderConfirmedNotice notice)
            throws MessagingException {

        // Data đã được business service ủy quyền;
        // composer vẫn kiểm tra định dạng trước khi tạo MIME.
        InternetAddress recipient =
                MailAddressPolicy.requireSingleMailbox(
                        notice.recipientEmail()
                );

        String orderNumber =
                MailHeaderValues.requiredSingleLine(
                        notice.orderNumber(),
                        "orderNumber",
                        80
                );

        URI actionUri =
                MailActionUrlPolicy.requireTrustedHttpsUrl(
                        notice.actionUrl()
                );

        String displayName = notice.displayName() == null
                || notice.displayName().isBlank()
                ? "bạn"
                : notice.displayName().strip();

        String note = notice.customerNote() == null
                ? ""
                : notice.customerNote();

        // Validate body field theo chính sách dung lượng của sản phẩm.
        if (displayName.length() > 160 || note.length() > 2000) {
            throw new IllegalArgumentException(
                    "Dữ liệu nội dung email vượt quá độ dài"
            );
        }

        OrderConfirmedMailModel model =
                new OrderConfirmedMailModel(
                        displayName,
                        orderNumber,
                        note,
                        actionUri.toASCIIString()
                );

        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("mail", model);

        // Template code là hằng số của server.
        String html = templateEngine.process(TEMPLATE, context);

        String plain = "Xin chào " + displayName
                + "\nĐơn hàng " + orderNumber
                + " đã được xác nhận."
                + "\nXem đơn hàng: " + actionUri.toASCIIString();

        String subject =
                MailHeaderValues.requiredSingleLine(
                        "Xác nhận đơn hàng " + orderNumber,
                        "subject",
                        200
                );

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom(FROM);
        helper.setReplyTo(REPLY_TO);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plain, html);

        mailSender.send(message);
    }
}
~~~

**OrderConfirmedMailModel** là record đã nêu ở phần trước. Ví dụ giả định đã có template Thymeleaf tên **mail/order-confirmed**, dùng **th:text** để hiển thị displayName, orderNumber và customerNote, cùng **th:href** cho actionUrl đã được kiểm tra.

Những điểm cần ghi nhớ:

- **FROM/REPLY_TO/TEMPLATE** không đến từ request.
- **recipient** được parse theo policy một mailbox, ngoài điều kiện business authorization.
- **Subject** được giới hạn và từ chối control chars.
- **actionUrl** chỉ được dùng khi qua policy HTTPS/host.
- **displayName/customerNote** là dữ liệu văn bản của template, không phải HTML source.
- **HTML và plain** dựa trên cùng một model/nguồn dữ liệu.
- **JavaMailSender** dùng cấu hình vận chuyển phía server.

### Tại sao composer vẫn không tự bảo đảm quyền gửi?

Composer chỉ nhận **OrderConfirmedNotice** và áp các quy tắc cấu trúc. Nếu một API public cho người dùng tự tạo record với recipientEmail tùy ý, vẫn có thể bị lạm dụng. **Authorization phải xảy ra trước khi tạo notice**, dựa trên order ID, tenant ID và người nhận thực sự thuộc nghiệp vụ. Đó là ranh giới không thể thay bằng một hàm parse email.

### Những điểm nên điều chỉnh cho production

Ví dụ tối giản có thể cần mở rộng:

- Dùng mail model riêng cho cả plain và HTML thay vì nối plain bằng chuỗi.
- Locale/timezone lấy từ preference đã được xác minh.
- Gửi qua event AFTER_COMMIT hoặc transactional outbox khi notification phụ thuộc transaction.
- Render nội dung rồi submit qua queue/worker nếu yêu cầu async/retry bền vững.
- Đặt mailFrom/Reply-To từ cấu hình verified sender identity theo môi trường/tenant.
- Ghi correlation ID opaque và trạng thái submission an toàn.
- Kiểm tra danh sách người nhận, suppression/unsubscribe và rate limit.
- Cấu hình SMTP timeout và quan sát lỗi provider.

## 20. Bảo mật khi dùng FreeMarker hoặc template engine khác

Nguyên tắc **template source tin cậy + data model chưa tin cậy** áp dụng cho mọi engine. Cú pháp escaping cụ thể khác nhau.

### Với FreeMarker

Ví dụ cấu hình template theo HTML output format và auto-escaping phù hợp với phiên bản FreeMarker dùng trong dự án. Khi đã bật đúng output format, các interpolation thông thường trong ngữ cảnh được hỗ trợ có thể được HTML-escape.

Không nên cho user nhập tùy ý:

- FTL source để server render bằng quyền ứng dụng.
- Dynamic expression để evaluate trong FreeMarker.
- Template name/path được resolve ra filesystem hoặc classpath.

Nếu sản phẩm cho phép template editor, đó là một chức năng có quyền hạn và sandbox policy riêng, không phải đường gửi mail giao dịch thông thường.

### Với Mustache hoặc engine logic-less

Nhiều engine logic-less có quy tắc escape khác nhau cho interpolation thường và interpolation unescaped. Hãy xem cấu hình thực tế, tránh dùng dạng unescaped cho dữ liệu người dùng. Đừng dựa vào giả định cú pháp của Thymeleaf áp dụng cho Mustache.

### Với một template HTML được tạo sẵn không có engine

Nếu email dùng một HTML fragment cố định và tự thay token bằng Java string replacement, bạn phải bảo đảm dữ liệu được encode đúng theo **ngữ cảnh cụ thể**:

~~~text
HTML text node
HTML attribute value
URL attribute
CSS property
JavaScript context (không nên dùng trong email)
~~~

Một hàm “escapeHTML” tổng quát không nhất thiết làm URL an toàn, và escaping dành cho text node không nên mặc nhiên áp dụng cho mọi ngữ cảnh CSS/URL. Với email giao dịch, dùng template engine và data model rõ ràng thường dễ quản lý hơn raw replacement.

## 21. Đừng dùng database như bằng chứng dữ liệu đã tin cậy

Một hiểu nhầm phổ biến là: “Giá trị đã được lưu trong database nên nó an toàn để đưa vào mail”. Không đúng.

Ví dụ:

1. Người dùng đăng ký với tên hiển thị chứa markup.
2. Ứng dụng lưu nguyên tên vào database.
3. Vài ngày sau, scheduled job lấy tên đó để gửi email.
4. Renderer nối tên vào HTML mà không escape.

Dù tên được đọc từ database, nguồn gốc ban đầu vẫn là dữ liệu chưa tin cậy. Đây là tình huống **stored injection**.

### Theo dõi nguồn dữ liệu, không chỉ nơi đang lưu

| Nguồn hiện tại | Có thể đáng tin cho mục đích nào? | Vẫn cần kiểm tra gì? |
| --- | --- | --- |
| JPA entity | Dữ liệu nghiệp vụ được lưu | Provenance, quyền recipient, escaping |
| Message broker event | Event đã được hệ thống phát | Sender authentication, schema/version, authorization |
| Internal service response | Dữ liệu từ hệ thống khác | API contract, tenant boundary, validation |
| Configuration properties | Một số giá trị do operator quản lý | Secret handling, verified senders, URL allowlist |
| CSV import | Dữ liệu từ file được import | Header/body validation, địa chỉ, injection, size |
| User input | Dữ liệu người dùng cung cấp | Validation và authorization theo từng trường |

**“Internal” không đồng nghĩa “trusted for every use”.** Một microservice có thể lưu tên user hợp lệ cho màn hình web nhưng vẫn chứa nội dung cần HTML-escape khi đưa vào email. Mỗi sink cần kiểm soát riêng.

## 22. Log, exception và khả năng quan sát không được làm lộ dữ liệu

Khi mail gửi thất bại, developer thường bật debug hoặc log toàn bộ message. Điều này hữu ích khi điều tra SMTP nhưng cũng có nguy cơ làm lộ:

- Địa chỉ người nhận, nội dung giao dịch và tên người dùng.
- Password reset link, OTP và magic login link.
- Tên file hoặc nội dung attachment.
- SMTP authentication details.
- Raw MIME headers có correlation hoặc thông tin nội bộ.

### Logging tối thiểu theo notification ID

Ví dụ log có cấu trúc:

~~~text
event=mail_submission_failed
notification_id=ab41...
event_type=ORDER_CONFIRMED
smtp_provider=primary
error_class=MailSendException
status=UNKNOWN
attempt=2
~~~

Các thông tin này đủ để liên hệ mail job với nguồn nghiệp vụ và provider logs mà không nhất thiết ghi nội dung thư. Nếu cần điều tra sâu, có thể bật logging bổ sung trong một khoảng thời gian ngắn với quyền truy cập chặt chẽ, dùng dữ liệu test hoặc dữ liệu đã được redact.

### Không trả exception nguyên văn cho client

Nếu một user không có quyền gửi email cho một recipient, API có thể trả lỗi nghiệp vụ tổng quát:

~~~text
403 Forbidden: Không được phép thực hiện hành động.
~~~

Không trả raw SMTP transcript, credentials, địa chỉ recipient ẩn hoặc stack trace chứa mail model cho người gọi chưa được xác thực.

Khi validation thất bại, dùng mã lỗi ổn định (ví dụ INVALID_RECIPIENT, INVALID_SUBJECT, UNAUTHORIZED_NOTIFICATION, UNTRUSTED_ACTION_URL), đồng thời log chi tiết kỹ thuật theo mức quyền phù hợp.

### Audit các quyết định quan trọng

Với hệ thống gửi thông báo quan trọng, có thể ghi:

- Ai hoặc event nào yêu cầu tạo notification.
- Recipient ID và tenant scope.
- Template code/version được chọn.
- Sender identity đã được xác minh.
- Correlation ID và outcome của attempt.
- Lý do từ chối header/URL/attachment không hợp lệ.

Không cần ghi nguyên payload nguy hiểm vào audit chỉ để phân tích; có thể ghi loại vi phạm, field name và một hash được thiết kế cẩn thận nếu cần đối chiếu.

## 23. Kiểm thử các ranh giới đầu vào

Validation cần có test ở tầng parser, policy, composer và tích hợp MIME. Những test này nên dùng dữ liệu giả; không gửi thật tới địa chỉ ngoài.

### Test từ chối xuống dòng trong Subject

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class MailHeaderValuesTest {

    @Test
    void rejectsCarriageReturnAndLineFeed() {
        String injected =
                "Xác nhận đơn hàng\r\nBcc: unexpected@example.test";

        assertThrows(
                IllegalArgumentException.class,
                () -> MailHeaderValues.requiredSingleLine(
                        injected,
                        "subject",
                        200
                )
        );
    }

    @Test
    void rejectsControlCharacter() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailHeaderValues.requiredSingleLine(
                        "Invoice\u0000Draft",
                        "subject",
                        200
                )
        );
    }
}
~~~

Test này xác nhận policy **từ chối đầu vào** trước khi đưa vào API header. Nó không cần thử xem một phiên bản Jakarta Mail cụ thể có chấp nhận payload ấy hay không.

### Test field recipient chỉ nhận một mailbox

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MailAddressPolicyTest {

    @Test
    void acceptsOneMailbox() {
        assertEquals(
                "customer@example.test",
                MailAddressPolicy
                        .requireSingleMailbox("customer@example.test")
                        .getAddress()
        );
    }

    @Test
    void rejectsAddressListInSingleField() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailAddressPolicy.requireSingleMailbox(
                        "a@example.test, b@example.test"
                )
        );
    }

    @Test
    void rejectsDisplayNameWhenOnlyMailboxIsAllowed() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailAddressPolicy.requireSingleMailbox(
                        "Someone <customer@example.test>"
                )
        );
    }
}
~~~

Test parser/validation này **không kiểm tra authorization**. Cần thêm test service nghiệp vụ để xác nhận user A không thể yêu cầu gửi hóa đơn của user B dù email B đúng cú pháp.

### Test URL chỉ chấp nhận host đáng tin cậy

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MailActionUrlPolicyTest {

    @Test
    void acceptsApprovedHttpsUrl() {
        assertEquals(
                "app.example.test",
                MailActionUrlPolicy.requireTrustedHttpsUrl(
                        "https://app.example.test/orders/ORD-1528"
                ).getHost()
        );
    }

    @Test
    void rejectsLookalikeHost() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailActionUrlPolicy.requireTrustedHttpsUrl(
                        "https://app.example.test.attacker.invalid/"
                )
        );
    }

    @Test
    void rejectsOtherSchemes() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailActionUrlPolicy.requireTrustedHttpsUrl(
                        "javascript:alert(1)"
                )
        );
    }
}
~~~

Đây là test cho một **allowlist của sản phẩm**, không phải bộ kiểm tra URL tổng quát. Nếu sản phẩm cần URL có path parameter, redirect hoặc nhiều domain tenant, test cần thể hiện chính sách đó.

### Test escaping trong HTML template

Một cách kiểm thử ở tầng template:

1. Dùng một mail model có displayName chứa dấu nhỏ hơn, lớn hơn và ký tự nháy.
2. Render bằng template Thymeleaf thực tế dùng **th:text**.
3. Parse HTML đã render.
4. Xác nhận chuỗi user xuất hiện dưới dạng text node, không trở thành một element HTML mới.
5. Xác nhận liên kết actionUrl vẫn trỏ đúng host đã được phép.

Không nên chỉ tìm một chuỗi escape cố định trong raw HTML nếu template engine có thể encode các ký tự hợp lệ theo nhiều biểu diễn tương đương. Kiểm tra **DOM semantics** giúp test phản ánh điều cần bảo vệ: dữ liệu người dùng không được biến thành HTML structure.

### Test không gửi mail khi validation/authorization thất bại

Một test service nên xác nhận:

~~~text
Given: user không sở hữu order
When: yêu cầu gửi hóa đơn cho order đó
Then: authorization error
And: không gọi JavaMailSender
And: không tạo outbox notification mới
~~~

Test an ninh chỉ kiểm tra chuỗi có CRLF là chưa đủ. Một địa chỉ hoàn toàn hợp lệ nhưng không thuộc dữ liệu nghiệp vụ cũng phải bị từ chối.

### Test MIME headers sau khi serialize

Với message có đủ dữ liệu hợp lệ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.test");
helper.setTo(
        MailAddressPolicy.requireSingleMailbox(
                "customer@example.test"
        )
);
helper.setSubject("Xác nhận đơn hàng");
helper.setText(
        "Đơn hàng đã được xác nhận.",
        "<p>Đơn hàng đã được xác nhận.</p>"
);

message.saveChanges();
~~~

Sau đó có thể dùng Jakarta Mail API kiểm tra:

- **From** đúng sender đã được xác minh.
- **Recipient** đúng người nhận.
- **Subject** đúng chuỗi đã chuẩn hóa.
- **Content-Type** của body/part phù hợp.
- Không có header Bcc bất ngờ.
- Attachment và inline resource nằm trong multipart đúng quan hệ nếu có.

Không nên so sánh toàn bộ raw message byte-for-byte vì **Message-ID**, boundary, header folding và transfer encoding có thể được sinh tự động. Dùng parser MIME để kiểm tra cấu trúc thực tế.

## 24. Những lỗi bảo mật thường gặp

### Lỗi 1 — Dùng request.subject() trực tiếp để tạo raw header

Chuỗi CR/LF có thể thay đổi ranh giới header khi code tự ghép MIME.

**Cách xử lý:** reject control characters và dùng MimeMessageHelper.setSubject thay vì nối raw header.

### Lỗi 2 — API cho người dùng nhập bất kỳ To address

Email đúng cú pháp vẫn có thể không phải người nhận được phép.

**Cách xử lý:** kiểm tra quyền theo thực thể nghiệp vụ; lấy recipient từ nguồn được ủy quyền, áp rate limit.

### Lỗi 3 — Lấy From từ form liên hệ

Một người dùng có thể tự xưng là người gửi khác, gây giả mạo và sai DMARC alignment.

**Cách xử lý:** From là sender identity đã xác minh; Reply-To được validate nếu nghiệp vụ cần.

### Lỗi 4 — Cho client gửi tùy ý custom header name

Input có thể cố ảnh hưởng tới header hệ thống hoặc MIME structure.

**Cách xử lý:** header name là hằng số/allowlist; header value có schema và độ dài giới hạn.

### Lỗi 5 — Dùng th:utext cho customerNote

Dữ liệu có thể trở thành HTML markup thay vì text.

**Cách xử lý:** dùng th:text hoặc sanitizer chuyên dụng nếu thật sự cần rich text.

### Lỗi 6 — Chỉ escape HTML rồi tin mọi URL

Một URL có thể được quote/escape đúng mà vẫn trỏ tới website không được phép.

**Cách xử lý:** kiểm tra scheme, host và route bằng chính sách URL riêng.

### Lỗi 7 — Tạo password reset URL từ Host header

Domain của liên kết có thể bị kiểm soát nếu proxy không validate Host/X-Forwarded-Host.

**Cách xử lý:** public base URL do server cấu hình hoặc domain tenant đã xác minh.

### Lỗi 8 — Template path do người dùng nhập

Ứng dụng có thể render template ngoài chức năng hoặc gặp lỗi path resolution.

**Cách xử lý:** dùng enum và catalog mapping, không dùng raw template path.

### Lỗi 9 — Cho phép user nhập template expression

Expression có thể được engine đánh giá trong quyền/context của server nếu triển khai không cách ly.

**Cách xử lý:** user text chỉ là Context data; không cho nhập template source/evaluation API tùy ý.

### Lỗi 10 — Tin filename upload khi tạo path

Path traversal hoặc tên file nhạy cảm có thể ảnh hưởng tới file được đọc.

**Cách xử lý:** storage key do server tạo; filename chỉ là display metadata đã kiểm tra.

### Lỗi 11 — Tin upload Content-Type

Client có thể khai báo image/png dù bytes không phải PNG.

**Cách xử lý:** allowlist, kiểm tra định dạng và malware policy; MIME type dựa trên dữ liệu đã xác minh.

### Lỗi 12 — Fetch ảnh từ mọi URL được gửi trong request

Backend có thể bị SSRF hoặc tải file quá lớn.

**Cách xử lý:** dùng tài nguyên cố định; nếu phải fetch, áp egress/URL/redirect/size policy.

### Lỗi 13 — Dùng cùng validation cho Subject và body

Ký tự xuống dòng là sai ở header nhưng hợp lệ trong body văn bản.

**Cách xử lý:** validation theo ngữ cảnh; escaping ở điểm output.

### Lỗi 14 — Log toàn bộ SMTP session hoặc raw MIME

Log có thể chứa PII, reset token, nội dung giao dịch và credentials.

**Cách xử lý:** log notification ID và phân loại lỗi, hạn chế debug dữ liệu thực.

### Lỗi 15 — Tin rằng DKIM khiến nội dung email an toàn

DKIM chứng minh một quan hệ xác thực/chữ ký ở domain gửi theo tiêu chuẩn, không phải bằng chứng dữ liệu template hoặc URL không độc hại.

**Cách xử lý:** kết hợp identity verification với authorization, validation và escaping nội dung.

### Lỗi 16 — Nghĩ input đã lưu DB nên an toàn

Dữ liệu ban đầu từ user vẫn có thể chứa markup/header-like text.

**Cách xử lý:** giữ chính sách đầu vào khi đọc lại, escape đúng nơi hiển thị và xác minh quyền trước khi gửi.

## 25. Tình huống luyện tập

### Tình huống A — Đầu vào Subject chứa xuống dòng

API nhận một Subject có dòng đầu là tên đơn, dòng tiếp theo trông như header Bcc.

**Hỏi:** nếu dùng MimeMessageHelper.setSubject thì có thể bỏ validation không?

**Đáp:** không nên. Setter có cấu trúc giúp thư viện tạo header đúng API, nhưng ứng dụng vẫn cần chính sách header: từ chối control characters, kiểm soát độ dài và không cho input làm thay đổi semantics. Không tự lắp raw MIME từ input.

### Tình huống B — Địa chỉ đúng cú pháp nhưng thuộc khách hàng khác

Người dùng A có quyền xem đơn hàng của mình và nhập email của người B vào API gửi hóa đơn.

**Hỏi:** InternetAddress.validate() có ngăn được không?

**Đáp:** không. Cú pháp email đúng không chứng minh quyền nhận hóa đơn. Service phải lấy người nhận từ đơn hàng đã được authorization hoặc áp quy trình ủy quyền bổ sung.

### Tình huống C — From được lấy từ email người gửi form

Form liên hệ cho nhập email, backend dùng giá trị đó làm From của thư gửi tới đội hỗ trợ.

**Hỏi:** rủi ro gì?

**Đáp:** user có thể giả mạo người gửi. Nên đặt From là địa chỉ đã xác minh của sản phẩm, rồi dùng Reply-To đã validate nếu cần phản hồi.

### Tình huống D — Display name có dấu nhỏ hơn và lớn hơn

Một khách hàng dùng tên hiển thị giống một thẻ HTML.

**Hỏi:** có nên từ chối mọi dấu nhỏ hơn/lớn hơn không?

**Đáp:** không nhất thiết. Tên hiển thị trong body có thể được giữ nguyên như dữ liệu và render qua th:text để HTML-escape. Nếu tên được dùng trong header, áp thêm chính sách control chars/độ dài và để Jakarta Mail encode header đúng cách.

### Tình huống E — Ghi chú đơn hàng chứa HTML

CustomerNote được đưa vào th:utext để giữ dấu xuống dòng.

**Hỏi:** có an toàn không?

**Đáp:** không nếu note chưa được kiểm soát. Dùng th:text và CSS/template thích hợp để trình bày dòng mới, hoặc sanitizer chuyên dụng nếu nghiệp vụ cho phép rich text. Không dùng th:utext chỉ để xử lý xuống dòng.

### Tình huống F — Action URL trỏ sang domain lạ

Một webhook gửi một URL có scheme HTTPS nhưng host không nằm trong allowlist.

**Hỏi:** escaping HTML attribute có đủ không?

**Đáp:** không. HTTPS và attribute escaping chưa bảo đảm đích tin cậy. URL phải được tạo hoặc kiểm tra theo host/route policy phía server.

### Tình huống G — Domain trông giống domain thật

URL là **https://app.example.test.attacker.invalid/**.

**Hỏi:** kiểm tra contains("app.example.test") có đủ không?

**Đáp:** không. Phải parse URI và kiểm tra hostname theo allowlist chính xác. Nếu cho subdomain, dùng quy tắc phân cách và quyền quản lý domain rõ ràng.

### Tình huống H — Template name đến từ API

Client gửi **templateName=mail/admin/internal-report** cho một endpoint chỉ được phép gửi xác nhận đơn hàng.

**Hỏi:** template engine có nhiệm vụ kiểm tra user được phép dùng template đó không?

**Đáp:** không. Ứng dụng phải map event nghiệp vụ đã được ủy quyền tới template cố định. Không trao quyền chọn template file tùy ý cho client.

### Tình huống I — Template chứa cú pháp nội suy nhập từ người dùng

Người dùng nhập một chuỗi trông giống biểu thức Thymeleaf, được lưu trong displayName.

**Hỏi:** chuỗi đó luôn bị template engine thực thi không?

**Đáp:** không nếu nó chỉ là giá trị Context data được hiển thị như text. Rủi ro phát sinh khi ứng dụng đưa nó vào template source hoặc đánh giá lại kết quả như expression. Giữ phân tách giữa source và data.

### Tình huống J — Upload tên file có đường dẫn

Client gửi originalFilename chứa path segments. Backend dùng trực tiếp tên này trong uploadDirectory.resolve(...).

**Hỏi:** rủi ro gì?

**Đáp:** path traversal hoặc truy cập file không mong muốn. Storage key phải do server tạo; display filename được validate riêng.

### Tình huống K — Attachment có tên PDF nhưng bytes không phải PDF

Upload cung cấp filename hóa đơn có đuôi .pdf và Content-Type application/pdf.

**Hỏi:** có thể tin MIME type từ client không?

**Đáp:** không. Extension và header do client khai báo không chứng minh nội dung. Kiểm tra signature/format, allowlist và malware policy theo yêu cầu.

### Tình huống L — Logo tải từ URL do user nhập

Backend tải URL và thêm ảnh inline vào email.

**Hỏi:** vì sao rủi ro vượt quá HTML injection?

**Đáp:** server có thể bị SSRF và truy cập host nội bộ, tải payload lớn hoặc làm lộ credentials nếu redirect/egress chưa được kiểm soát. Dùng resource tin cậy hoặc policy fetch chặt chẽ.

### Tình huống M — Gửi nhiều khách hàng qua Bcc

Một công việc gửi thông báo cá nhân hóa cho 500 người bằng một message.

**Hỏi:** có nên render danh sách Bcc vào template để người nhận biết còn ai trong danh sách?

**Đáp:** không. Bcc là danh sách ẩn. Với notification độc lập, một message cho mỗi recipient thường hỗ trợ riêng tư, trạng thái gửi và deduplication tốt hơn.

### Tình huống N — Một hệ thống phụ ghi tên khách hàng vào database

Sau đó scheduled job tạo HTML bằng nối chuỗi từ customerName.

**Hỏi:** dữ liệu có an toàn vì được đọc từ database không?

**Đáp:** không. Nguồn gốc ban đầu vẫn có thể là input không tin cậy. Phải HTML-escape theo ngữ cảnh khi render.

### Tình huống O — Log chứa reset token

Khi SMTP lỗi, worker in toàn bộ MIME message và actionUrl chứa token khôi phục mật khẩu.

**Hỏi:** xử lý thế nào?

**Đáp:** log notification ID, error category và trạng thái; hạn chế truy cập debug, redact token và dữ liệu nhạy cảm. Đừng để thông tin dùng để đăng nhập/khôi phục tài khoản xuất hiện trong log.

### Tình huống P — Người dùng tự chọn SMTP host

Một API gửi thông báo nhận smtpHost, smtpUsername và smtpPassword tùy ý.

**Hỏi:** đây có phải chỉ là một cấu hình tiện lợi?

**Đáp:** không với API giao dịch thông thường. Nó trao quyền điều khiển transport và kết nối mạng. Nếu thực sự hỗ trợ SMTP theo tenant, phải xây chức năng quản trị riêng có xác thực, lưu secret, kiểm tra host/egress/TLS và quyền tenant.

## 26. Quy trình bảo vệ dữ liệu trước khi gửi email

~~~text
1. Nhận yêu cầu / event
        |
        v
2. Xác thực nguồn và kiểm tra quyền nghiệp vụ
        |
        v
3. Lấy recipient và sender identity được phép
        |
        v
4. Parse/validate mailbox, subject, custom header values
        |
        v
5. Chọn template từ enum/catalog của server
        |
        v
6. Chuẩn bị mail model tối thiểu
        |
        +--> Validate dữ liệu bắt buộc
        +--> Giới hạn kích thước
        +--> Tạo URL từ domain tin cậy
        +--> Lọc dữ liệu nhạy cảm không cần gửi
        |
        v
7. Render
        |
        +--> HTML với escaping theo ngữ cảnh
        '--> Plain text cùng dữ liệu nghiệp vụ
        |
        v
8. Chuẩn bị MIME
        |
        +--> From/Reply-To/To qua API chuyên dụng
        +--> Header name cố định, value đã kiểm tra
        +--> Resource + filename + content type đã xác minh
        |
        v
9. Gửi bằng JavaMailSender cấu hình SMTP tin cậy
        |
        v
10. Ghi nhận trạng thái và lỗi an toàn
        |
        v
11. Theo dõi provider delivery/bounce khi cần
~~~

### Một checklist cho code review

- **Identity:** Sender From/Reply-To có được kiểm soát, không lấy tùy ý từ request?
- **Authorization:** Người gọi có quyền gửi loại thư tới đúng người nhận không?
- **Address:** Mỗi mailbox đã parse, validate và giới hạn theo policy chưa?
- **Header:** Subject/custom header có bị từ chối CR/LF/control chars và giới hạn độ dài không?
- **Template:** Template source/path có đến từ catalog đáng tin cậy không?
- **Model:** Đã tránh truyền nguyên entity chứa dữ liệu nhạy cảm vào Context chưa?
- **HTML:** Dữ liệu người dùng được render bằng th:text hoặc cơ chế escaping phù hợp chưa?
- **URL:** Action URL được tạo/validate theo HTTPS và host/route policy chưa?
- **Attachment:** Resource được lấy từ storage key đáng tin cậy, filename/MIME type đã kiểm tra chưa?
- **Transport:** SMTP credentials/TLS/host có được quản lý ở server không?
- **Logs:** Có tránh ghi OTP/token/PII/raw SMTP credentials không?
- **Tests:** Đã kiểm tra injection, unauthorized recipient, URL giả và đường dẫn attachment chưa?

Các câu hỏi này là hướng dẫn thiết kế tính an toàn; không phải một công cụ tự động chứng nhận hệ thống đã an toàn. Với luồng mail quan trọng, vẫn cần threat modeling, kiểm thử tích hợp và quy trình bảo mật của tổ chức.

## 27. Nguyên tắc ghi nhớ

~~~text
Không tin input -> không cho tạo cấu trúc header tùy ý
Email đúng cú pháp -> chưa chắc được quyền gửi
From và SMTP identity -> server kiểm soát
Reply-To -> validate và chỉ dùng theo nghiệp vụ
Header value -> reject control chars, giới hạn độ dài
Template source -> code/catalog đáng tin cậy
User text -> dữ liệu, không phải template expression
HTML text -> escape theo đúng ngữ cảnh
HTML link -> escape attribute + validate URL
Attachment filename -> metadata, không phải storage path
Content-Type từ client -> không phải bằng chứng định dạng
SMTP config -> secrets/TLS/host do server kiểm soát
Log lỗi -> metadata tối thiểu, không lộ token và nội dung nhạy cảm
~~~

**Không tin dữ liệu để tạo header, địa chỉ và template** là cách áp dụng *trust boundaries* vào mọi bước xây dựng email trong Spring Framework Mail. **MimeMessageHelper** và **InternetAddress** giúp thao tác với cấu trúc MIME/địa chỉ qua API phù hợp, nhưng không quyết định ai có quyền gửi, sender identity nào được dùng hay URL và template nào đáng tin. Hãy đưa dữ liệu chưa tin cậy qua validation/authorization theo từng trường, giữ sender/header/template structure dưới quyền kiểm soát của ứng dụng, sử dụng escaping đúng ngữ cảnh cho HTML và chỉ gửi các attachment đã được xác minh. Khi những ranh giới này được thiết kế rõ ràng, hệ thống vừa giảm nguy cơ header injection, spoofing, template/HTML injection và SSRF, vừa tạo nền tảng dễ kiểm thử, dễ vận hành cho các luồng email giao dịch.
