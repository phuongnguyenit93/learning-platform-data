# Header injection và kiểm soát dữ liệu đầu vào

Một ứng dụng Spring có thể gửi email từ dữ liệu do người dùng nhập: địa chỉ liên hệ, tên người gửi, tiêu đề, nội dung phản hồi, mã đơn hàng hoặc tên tệp đính kèm. Nếu dữ liệu đó được đưa vào **email header** mà không kiểm soát, kẻ tấn công có thể thử chèn ký tự xuống dòng để làm cho một giá trị bị diễn giải thành nhiều trường header. Đây là dạng **email header injection**, thường được nhắc đến cùng kỹ thuật **CRLF injection**.

Ví dụ, trường “Tiêu đề” trên biểu mẫu liên hệ chỉ nên trở thành giá trị của header **Subject**. Nhưng nếu ứng dụng tự ghép các dòng header bằng chuỗi và không kiểm tra đầu vào, một giá trị chứa chuỗi xuống dòng có thể khiến phần sau được hiểu như một header mới.

Trong **Spring Framework Mail**, cách phòng vệ chủ đạo là **xác định rõ trường dữ liệu nào được phép ảnh hưởng đến header nào, kiểm tra đầu vào theo từng loại trường và để Jakarta Mail/Spring Mail tạo cấu trúc thông điệp**. Thư viện email giúp xây dựng message theo định dạng chuẩn; ứng dụng vẫn phải kiểm soát quyền lựa chọn người nhận, địa chỉ gửi, giá trị tùy biến và nội dung do bên ngoài cung cấp.

## 1. Header email nằm ở đâu?

Một email theo định dạng Internet message gồm **khối header**, một **dòng trống**, rồi **phần thân (body)**. Ví dụ:

~~~text
From: support@example.org
To: customer@example.net
Reply-To: helpdesk@example.org
Subject: Xac nhan yeu cau
Date: Thu, 12 Nov 2026 08:00:00 +0000
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Chung toi da nhan duoc yeu cau cua ban.
~~~

Các dòng **From**, **To**, **Reply-To**, **Subject** và **Content-Type** là header. Dòng trống đánh dấu ranh giới giữa header với body.

Ở tầng định dạng email, các dòng được phân cách bằng cặp ký tự điều khiển **CRLF**:

- **CR** (carriage return): ký tự **\r**, mã 0x0D.
- **LF** (line feed): ký tự **\n**, mã 0x0A.
- **CRLF**: chuỗi **\r\n**, dùng để kết thúc một dòng theo định dạng Internet message.

Body của email có thể chứa nhiều dòng văn bản. Nhưng **đầu vào dành cho một giá trị header đơn** không được tự ý quyết định nơi kết thúc dòng header và nơi bắt đầu một header mới.

### Header không phải phong bì SMTP

Cần phân biệt cấu trúc email với giao thức vận chuyển SMTP:

~~~text
SMTP envelope:
  MAIL FROM:<mailer@example.org>
  RCPT TO:<customer@example.net>

SMTP DATA:
  From: support@example.org
  To: customer@example.net
  Subject: Xac nhan yeu cau

  Noi dung email...
~~~

- **MAIL FROM / RCPT TO** là lệnh và địa chỉ ở lớp SMTP envelope.
- **From / To / Cc / Bcc / Reply-To / Subject** là các trường liên quan đến message và hành vi gửi thư; một số địa chỉ được thư viện dùng để xác định envelope recipients.
- **MIME header** như Content-Type hoặc Content-Disposition mô tả cấu trúc và cách hiển thị các phần nội dung.

Header injection nhắm vào cách dựng hoặc diễn giải **khối header của message**. Nó liên quan nhưng không đồng nhất với việc thao túng lệnh SMTP, thao túng người nhận hay việc hiển thị HTML trong nội dung thư.

## 2. Header injection xảy ra như thế nào?

Giả sử một hệ thống tự dựng raw email như sau:

~~~java
String rawMessage =
        "From: support@example.org\r\n"
      + "To: support-team@example.org\r\n"
      + "Subject: " + userInput + "\r\n"
      + "\r\n"
      + "Yeu cau tu khach hang";
~~~

Nếu **userInput** là một tiêu đề hợp lệ, ví dụ **Can ho tro dat hang**, kết quả là một Subject bình thường.

Nhưng nếu đầu vào chứa ký tự xuống dòng và văn bản trông giống một trường header:

~~~text
Can ho tro dat hang\r\nBcc: unexpected@example.net
~~~

thì raw message được ghép có thể trở thành:

~~~text
From: support@example.org
To: support-team@example.org
Subject: Can ho tro dat hang
Bcc: unexpected@example.net

Yeu cau tu khach hang
~~~

Đây là minh họa **cách cú pháp bị thay đổi khi ứng dụng nối chuỗi thiếu an toàn**; không có nghĩa mọi thư viện, SMTP server hay email client sẽ chấp nhận hoặc vận chuyển phần header được thêm vào. Kết quả thực tế còn phụ thuộc vào parser, hành vi chuẩn hóa, thư viện và các lớp kiểm soát phía sau.

Vấn đề nằm ở ranh giới tin cậy: **người dùng được phép cung cấp nội dung của Subject nhưng không được phép cung cấp cấu trúc header hoặc mở thêm một Bcc**.

### Vì sao chuỗi \r\n đặc biệt nguy hiểm trong header?

Trong một chuỗi Java, hai escape **\r** và **\n** tạo các ký tự CR và LF. Khi một hệ thống ghép chuỗi đó trực tiếp vào vùng header của raw message, CRLF có thể kết thúc dòng hiện tại. Dữ liệu tiếp theo có thể bị diễn giải như một trường mới.

Một số dấu xuống dòng có thể xuất hiện từ nhiều nguồn:

- Textarea hoặc request HTTP chứa ký tự xuống dòng thật.
- Dữ liệu được nhập từ CSV, webhook, log hoặc dịch vụ ngoài.
- Giá trị đã qua giải mã URL hoặc JSON.
- Giá trị được khôi phục từ database vốn chứa dữ liệu không tin cậy.
- Một header của email nhận được rồi được chuyển tiếp vào header của email mới.

Do đó, **dữ liệu lấy từ database không tự động là dữ liệu an toàn**. Cần xem nguồn gốc và cách nó được đưa vào email cuối cùng.

### Header injection có thể gây hậu quả gì?

Tùy ứng dụng và cách dựng thông điệp, các hậu quả có thể gồm:

1. **Bổ sung hoặc thay đổi header người nhận** nếu hệ thống diễn giải header chèn và sử dụng chúng để gửi.
2. **Giả mạo metadata hiển thị**, chẳng hạn tên người gửi, Reply-To hoặc tiêu đề trong một số đường xử lý.
3. **Làm hỏng cấu trúc MIME**, ảnh hưởng đến cách client nhận, hiển thị hoặc phân tích email.
4. **Vượt qua logic nghiệp vụ**, ví dụ gửi nội dung đặt hàng đến địa chỉ ngoài danh sách được cho phép nếu có lỗi ở cách xác định recipients.
5. **Làm sai log hoặc báo cáo**, khi ký tự điều khiển được tái sử dụng không an toàn trong các bản ghi sự kiện gửi thư.

Không nên khẳng định một chuỗi cụ thể luôn “gửi lén được email”: có những triển khai đã chặn xuống dòng trong header, không lấy recipient từ header chèn, hoặc từ chối message sai định dạng. Điều quan trọng là **không cho đầu vào không tin cậy quyết định cấu trúc email**.

## 3. Các trường dữ liệu cần quan tâm

Không phải mọi trường trong email có cùng quy tắc kiểm tra. Trước tiên phải xác định **dữ liệu sẽ đi vào đâu**.

| Dữ liệu | Ví dụ | Nguy cơ hoặc điều cần kiểm soát |
| --- | --- | --- |
| **To / Cc / Bcc** | Địa chỉ người nhận | Không chấp nhận nhiều địa chỉ ngoài dự kiến, display name không được phép hoặc recipient trái quyền |
| **From** | Địa chỉ gửi | Không cho người dùng tự nhận danh tính gửi thuộc tổ chức nếu không được phép |
| **Reply-To** | Email khách hàng muốn nhận phản hồi | Cần parse đúng một mailbox, tránh giá trị có xuống dòng hoặc địa chỉ khác ý định |
| **Subject** | Tiêu đề liên hệ, tên đơn hàng | Chặn CR/LF và ký tự điều khiển; giới hạn độ dài |
| **Tên hiển thị (personal name)** | “Nguyễn An” | Kiểm tra ký tự điều khiển, độ dài và cách hiển thị; giao cho thư viện mã hóa header |
| **Custom header** | X-Request-Id | Không để bên ngoài tùy ý đặt tên header hoặc giá trị chứa xuống dòng |
| **MIME filename** | invoice.pdf | Tránh ký tự điều khiển, đường dẫn, tên quá dài và rò rỉ metadata; dùng API attachment |
| **Body dạng plain text** | Nội dung yêu cầu hỗ trợ | Xuống dòng có thể hợp lệ; phải tách khỏi vùng header |
| **Body dạng HTML** | Email marketing, thông báo HTML | Cần escape/sanitize HTML theo ngữ cảnh; header validation không bảo vệ HTML |

Điểm dễ mắc lỗi là áp dụng **một hàm “sanitize” chung** cho mọi trường. Một hàm xóa newline có thể phù hợp với Subject nhưng lại phá hỏng một tin nhắn nhiều dòng trong body. Ngược lại, vì textarea cho phép newline nên không được suy ra Subject cũng nên cho phép newline.

## 4. Phân biệt các kiểu tấn công liên quan

### 4.1. Header injection

Mục tiêu là thay đổi cấu trúc hoặc giá trị header bằng đầu vào vượt khỏi giới hạn của một field. Dấu hiệu kinh điển là **CRLF** trong giá trị lẽ ra chỉ là một dòng.

### 4.2. SMTP command injection

Mục tiêu là làm thay đổi lệnh gửi ở lớp giao thức SMTP, chẳng hạn lệnh thao tác envelope hoặc trình tự lệnh được phát ra. Đây là lớp khác với header của Internet message.

Khi dùng **JavaMailSender/Jakarta Mail**, thư viện thường đảm nhiệm việc tạo lệnh SMTP. Không tự xây dựng phiên SMTP từ các chuỗi địa chỉ lấy trực tiếp từ người dùng. Dù vậy, kiểm soát recipient ở tầng nghiệp vụ vẫn cần thiết: một địa chỉ cú pháp hợp lệ có thể là người nhận hoàn toàn không được phép.

### 4.3. HTML injection trong body

Nếu email được gửi ở dạng HTML:

~~~java
helper.setText(html, true);
~~~

thì **html** được hiểu là markup. Nếu nối trực tiếp dữ liệu người dùng vào đó, họ có thể chèn thẻ và thuộc tính HTML làm thay đổi nội dung hiển thị. Giải pháp là **escape nội dung động theo ngữ cảnh HTML** hoặc dùng template engine có cơ chế escaping phù hợp; nếu ứng dụng cố ý cho phép một phần HTML, cần sanitizer theo chính sách rõ ràng.

Chặn **\r\n** trong Subject không ngăn được HTML injection ở body. Ngược lại, escape HTML không thay thế việc kiểm tra CRLF trong header.

### 4.4. Spoofing tên người gửi và địa chỉ

Một email có thể hiển thị **“Bộ phận kế toán”** dù địa chỉ thực là một mailbox không liên quan. Đây có thể là dạng gây nhầm lẫn hiển thị, dù không có CRLF injection.

Vì thế, ứng dụng phải phân biệt **tên hiển thị** với **địa chỉ thực**, và xác định địa chỉ nào được phép xuất hiện trong **From**, **Reply-To**, **To/Cc/Bcc**.

## 5. Nguyên tắc kiểm soát đầu vào: kiểm tra theo đích sử dụng

Một chiến lược an toàn nên được áp dụng ngay khi dữ liệu đi từ bên ngoài vào một trường có ý nghĩa cấu trúc.

### 5.1. Chỉ chấp nhận một mailbox khi chỉ cần một mailbox

Nếu trường **email người liên hệ** chỉ cần một địa chỉ, không được cho người dùng nhập:

~~~text
an@example.net, other@example.net
~~~

rồi đưa cả chuỗi vào một API có thể hiểu thành danh sách người nhận.

Tương tự, các biến thể có dấu phân cách, tên hiển thị, comments hoặc cú pháp khác có thể được email parser hỗ trợ trong một số tình huống, nhưng ứng dụng **không buộc phải chấp nhận mọi cú pháp mà parser có thể hiểu**. Với một ô input chỉ dành cho địa chỉ đơn lẻ, chính sách có thể yêu cầu **một địa chỉ mailbox không kèm display name**.

### 5.2. Từ chối CR, LF và ký tự điều khiển trong header một dòng

Các trường như Subject, nhãn người gửi, tên hiển thị và mã tùy biến nên:

- Từ chối ký tự **CR** và **LF** đến từ người dùng.
- Từ chối các control character không phù hợp như **NUL** và các ký tự điều khiển C0/C1 theo chính sách.
- Giới hạn độ dài; tránh chấp nhận cả megabyte trong Subject.
- Áp dụng quy tắc riêng cho trường: mã request có thể chỉ cho phép UUID/ASCII, trong khi Subject có thể cần dấu tiếng Việt và emoji.
- Xử lý lỗi xác thực rõ ràng, không âm thầm “sửa” dữ liệu gây nguy hiểm rồi giả định người dùng đã nhập đúng.

**Lưu ý:** chuẩn email cho phép các header dài được **gấp dòng (folding)** theo quy tắc của RFC, và tên/tiêu đề Unicode có thể được mã hóa thành các dạng an toàn để truyền. Điều này **không có nghĩa** nên chấp nhận raw CRLF do người dùng nhập. Để Jakarta Mail tạo cách gấp dòng và mã hóa cần thiết từ giá trị đã được kiểm tra.

### 5.3. Không dùng việc “xóa \r và \n” làm biện pháp duy nhất

Ví dụ hàm sau không phải một chính sách đầy đủ:

~~~java
String cleaned = input.replace("\r", "").replace("\n", "");
~~~

Nó có thể biến một input bị tấn công thành một chuỗi khác ngoài ý định và bỏ qua các kiểu control/giới hạn/trạng thái đầu vào. Trong nhiều trường hợp, **từ chối giá trị không hợp lệ** là hành vi rõ ràng hơn: người dùng nhận thông báo sửa lại tiêu đề, còn hệ thống không gửi thư với dữ liệu đã bị biến đổi âm thầm.

Có thể chuẩn hóa khoảng trắng hoặc trim ở các trường đã được định nghĩa cho phép, nhưng phải **kiểm tra trước hoặc đồng thời với bước chuẩn hóa** và không biến dữ liệu không hợp lệ thành một recipient khác.

### 5.4. Không dùng regex quá đơn giản để “xác thực mọi địa chỉ email”

Một regex như:

~~~regex
.+@.+
~~~

không đủ để parse cú pháp địa chỉ trong các tình huống thực tế. Ngược lại, một regex dài cố gắng bao phủ toàn bộ RFC email thường khó bảo trì và vẫn không thay thế được parser chuyên dụng.

Trong Java, có thể dùng **jakarta.mail.internet.InternetAddress** để parse và validate địa chỉ, sau đó **áp dụng các quy tắc nghiệp vụ bổ sung**: một mailbox duy nhất, không kèm tên hiển thị nếu input chỉ dành cho địa chỉ, không có control character, độ dài phù hợp và domain/recipient được phép.

**Địa chỉ đúng cú pháp không đồng nghĩa mailbox tồn tại**, không chứng minh người dùng sở hữu địa chỉ và không bảo đảm SMTP server sẽ chấp nhận thư.

### 5.5. Giới hạn độ dài, số lượng và quyền gửi

Validation cũng cần quan tâm đến:

- Giới hạn độ dài Subject, display name, filename và các giá trị header tùy biến.
- Giới hạn số người nhận trong một yêu cầu, tổng kích thước email và tốc độ gửi.
- Quyền quyết định địa chỉ gửi/nhận: một người dùng bình thường không được đặt Bcc tới địa chỉ tùy ý nếu nghiệp vụ không cho phép.
- Chính sách cho phép domain hoặc tài khoản, nếu ứng dụng chỉ gửi trong phạm vi nhất định.
- Tính nhất quán giữa địa chỉ đã xác thực trong hồ sơ và địa chỉ đầu vào ở request.

Những giới hạn này giải quyết cả vấn đề lạm dụng dịch vụ gửi thư, ngay cả khi dữ liệu không chứa CRLF.

## 6. Cách dùng API của Spring Mail để tránh dựng header bằng chuỗi

Spring Framework Mail thường được dùng qua **JavaMailSender** và **MimeMessageHelper**. Chúng cung cấp các phương thức được thiết kế cho các trường cụ thể:

~~~java
helper.setFrom("noreply@example.org");
helper.setTo("support@example.org");
helper.setReplyTo("customer@example.net");
helper.setSubject("Yêu cầu hỗ trợ");
helper.setText("Nội dung phản hồi", false);
~~~

Lợi ích của cách này là ứng dụng truyền **giá trị trường** cho thư viện thay vì tự ghép:

~~~text
From: ...
To: ...
Subject: ...

Body...
~~~

Thư viện phụ trách các chi tiết về định dạng Internet message, MIME, mã hóa và việc gửi qua transport.

Tuy nhiên, **API riêng cho từng field không tự chứng minh dữ liệu nghiệp vụ là hợp lệ**. Ví dụ một phương thức đặt recipient có thể chấp nhận một địa chỉ cú pháp đúng nhưng không được phép; một Subject quá dài hoặc chứa control character có thể bị xử lý khác nhau tùy phiên bản thư viện. Vì vậy, **validation đầu vào và kiểm soát quyền vẫn phải được thực hiện ở ứng dụng**.

### Những API cần nhận diện

| API | Công việc phù hợp |
| --- | --- |
| **MimeMessageHelper.setTo(...)** | Thiết lập người nhận chính |
| **setCc(...) / setBcc(...)** | Thiết lập người nhận sao chép/copy ẩn |
| **setFrom(...)** | Thiết lập địa chỉ, có thể có tên hiển thị |
| **setReplyTo(...)** | Thiết lập địa chỉ trả lời |
| **setSubject(...)** | Thiết lập tiêu đề |
| **setText(..., false)** | Gửi body plain text |
| **setText(..., true)** | Gửi body HTML |
| **addAttachment(...)** | Tạo part đính kèm có metadata MIME tương ứng |
| **MimeMessage.setHeader(...)** | Đặt một header trực tiếp; cần đặc biệt kiểm soát tên và giá trị |

Đừng chuyển từ **setSubject()** sang **setHeader("Subject", dữ liệu tự ghép)** chỉ để vượt qua validation hoặc encoding của helper.

## 7. Ví dụ Spring Boot: biểu mẫu liên hệ gửi tới hộp thư hỗ trợ cố định

Giả sử trang web có biểu mẫu gồm:

- **email**: địa chỉ khách hàng để nhân viên phản hồi.
- **name**: tên khách hàng.
- **subject**: tiêu đề yêu cầu.
- **message**: nội dung nhiều dòng.

Ứng dụng chỉ được gửi tới **support@example.org**. Người dùng không quyết định To, Cc, Bcc hoặc From. Email khách hàng xuất hiện trong **Reply-To** sau khi được kiểm tra là một mailbox đơn.

### 7.1. Mô hình request

~~~java
public record ContactRequest(
        String email,
        String name,
        String subject,
        String message
) {}
~~~

Không cần cho client gửi các trường **from**, **to**, **bcc**, **mailHeaders** trong request nếu nghiệp vụ không sử dụng chúng. Thiết kế DTO là một bước quan trọng để giảm khả năng đầu vào không tin cậy điều khiển cấu trúc email.

### 7.2. Dịch vụ gửi thư với validation theo trường

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ContactMailService {

    private final JavaMailSender mailSender;

    public ContactMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(ContactRequest request) throws MessagingException {
        if (request == null) {
            throw new IllegalArgumentException("Thiếu yêu cầu liên hệ");
        }

        String replyTo = requireSingleMailbox(request.email());
        String name = requireSingleLine(request.name(), "Tên", 100);
        String subject = requireSingleLine(
                request.subject(), "Tiêu đề", 160
        );
        String body = requireBody(request.message());

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, "UTF-8"
        );

        helper.setFrom("noreply@example.org");
        helper.setTo("support@example.org");
        helper.setReplyTo(replyTo);
        helper.setSubject("Liên hệ: " + subject);

        helper.setText(
                "Tên khách hàng: " + name + "\n"
                + "Email liên hệ: " + replyTo + "\n\n"
                + body,
                false
        );

        mailSender.send(message);
    }

    private static String requireSingleMailbox(String raw) {
        String value = requireSingleLine(
                raw, "Email", 254
        );

        try {
            InternetAddress[] addresses =
                    InternetAddress.parse(value, true);

            if (addresses.length != 1) {
                throw new IllegalArgumentException(
                        "Chỉ cho phép một địa chỉ email"
                );
            }

            InternetAddress address = addresses[0];
            address.validate();

            // Chỉ cho phép dạng mailbox đơn, không có display name
            // hoặc danh sách địa chỉ.
            if (address.getPersonal() != null
                    || !value.equals(address.getAddress())) {
                throw new IllegalArgumentException(
                        "Email phải là một địa chỉ mailbox đơn"
                );
            }

            return address.getAddress();
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Địa chỉ email không hợp lệ", ex
            );
        }
    }

    private static String requireSingleLine(
            String raw, String field, int maxCodePoints
    ) {
        if (raw == null) {
            throw new IllegalArgumentException(
                    field + " không được để trống"
            );
        }

        // Kiểm tra input gốc trước khi trim.
        boolean invalidControl = raw.codePoints().anyMatch(
                cp -> Character.isISOControl(cp)
                        || cp == 0x2028
                        || cp == 0x2029
        );

        if (invalidControl) {
            throw new IllegalArgumentException(
                    field + " chứa ký tự điều khiển hoặc ngắt dòng"
            );
        }

        String value = raw.strip();

        if (value.isEmpty()
                || value.codePointCount(0, value.length()) > maxCodePoints) {
            throw new IllegalArgumentException(
                    field + " trống hoặc vượt quá độ dài cho phép"
            );
        }

        return value;
    }

    private static String requireBody(String raw) {
        if (raw == null || raw.isBlank()
                || raw.length() > 20_000) {
            throw new IllegalArgumentException(
                    "Nội dung trống hoặc quá dài"
            );
        }

        return raw;
    }
}
~~~

Trong ví dụ này, **requireSingleLine** từ chối các ký tự control của đầu vào trước khi đưa vào header một dòng. Đoạn kiểm tra còn xét **U+2028** và **U+2029**, là các ký tự ngắt dòng Unicode ở tầng hiển thị, nhằm tránh các tình huống xuống dòng gây nhầm lẫn trên giao diện/log. Đây là **chính sách nhập liệu của ứng dụng**, không phải tuyên bố rằng mọi ký tự Unicode đó đều tương đương CRLF theo cú pháp SMTP.

**InternetAddress.parse(..., true)** yêu cầu parser đọc địa chỉ theo chế độ strict; **validate()** kiểm tra thêm cú pháp theo khả năng của Jakarta Mail. Điều kiện **value.equals(address.getAddress())** giới hạn ví dụ ở input một mailbox thuần, không phải display name hay danh sách. Kiểm tra cú pháp vẫn cần được kết hợp với chính sách domain, cơ chế xác minh sở hữu địa chỉ và yêu cầu SMTPUTF8 nếu hệ thống hỗ trợ địa chỉ quốc tế hóa.

### 7.3. Vì sao không dùng email khách hàng làm From?

Thiết kế thiếu phù hợp thường là:

~~~java
helper.setFrom(request.email());
~~~

Trường hợp này giao cho khách hàng quyết định danh tính người gửi của tổ chức. Dù input có là một địa chỉ đúng cú pháp, việc dùng nó làm **From** có thể khiến email bị đánh giá là giả mạo hoặc không phù hợp với SPF, DKIM, DMARC và chính sách nhà cung cấp.

Cách trong ví dụ:

~~~java
helper.setFrom("noreply@example.org");
helper.setReplyTo(replyTo);
~~~

giữ **From** là địa chỉ do hệ thống kiểm soát, còn **Reply-To** là địa chỉ khách hàng đã qua kiểm tra. Khi nhân viên bấm trả lời, email client thường đề xuất gửi tới Reply-To. Điều này phù hợp với nhu cầu “phản hồi cho người liên hệ” mà không thay đổi danh tính gửi.

**Reply-To cũng là một header có ảnh hưởng đến luồng làm việc.** Việc khách hàng được phép đặt Reply-To không có nghĩa mọi người dùng được phép đưa địa chỉ tùy ý vào mọi email hoặc có quyền sử dụng đó để tự động chuyển thông tin nhạy cảm. Chính sách nghiệp vụ vẫn cần được quyết định rõ.

### 7.4. Vì sao tên khách hàng nằm trong body?

Trong ví dụ, **name** được trình bày dưới dạng text:

~~~text
Tên khách hàng: Nguyễn An
Email liên hệ: an@example.net

Tôi cần hỗ trợ đơn hàng...
~~~

Tên không được tự động ghép vào header **From**. Nếu thực sự cần tên hiển thị ở header, nên dùng API đặt **personal name** của MimeMessageHelper/InternetAddress, sau khi đã kiểm tra giá trị. Thư viện sẽ xử lý phần mã hóa ký tự header thích hợp; không tự nối chuỗi như **"From: " + name + " <...>"**.

### 7.5. Vì sao body được phép có newline?

Nội dung biểu mẫu có thể là:

~~~text
Xin chào,

Tôi gặp lỗi khi thanh toán.
Mã đơn hàng: 1234

Mong được hỗ trợ.
~~~

Đây là body nhiều dòng hợp lệ. Với **helper.setText(body, false)**, chuỗi được đưa vào phần nội dung plain text; xuống dòng trong body không đồng nghĩa với việc khai báo header mới, miễn là thư viện dựng message đúng và ứng dụng không lấy body ghép vào raw header.

Body vẫn cần kiểm soát kích thước, dữ liệu nhạy cảm, nội dung tự động xử lý và chính sách chống lạm dụng; những kiểm soát đó khác với việc cấm CRLF trong header.

## 8. Cách kiểm tra địa chỉ To, Cc, Bcc đúng nhu cầu

Các trường recipient là nơi header injection liên hệ trực tiếp đến **việc một email sẽ được gửi tới ai**.

### 8.1. Một địa chỉ so với một danh sách địa chỉ

Nếu tính năng **gửi hóa đơn** chỉ cho phép một khách hàng, nên parse một địa chỉ duy nhất rồi gọi:

~~~java
helper.setTo(validatedRecipient);
~~~

Nếu tính năng **thông báo nhóm** cho phép nhiều người nhận, không nên nhận một chuỗi tùy ý và coi đó là danh sách đã an toàn. Có thể định nghĩa DTO nhận danh sách có cấu trúc:

~~~java
public record GroupMailRequest(
        java.util.List<String> recipients,
        String subject,
        String message
) {}
~~~

Sau đó:

1. Giới hạn số phần tử.
2. Kiểm tra từng phần tử là một mailbox đơn.
3. Loại bỏ phần tử trùng theo chính sách rõ ràng.
4. Xác định người gửi có quyền gửi tới tập địa chỉ đó hay không.
5. Chuyển danh sách đã được chấp nhận thành mảng địa chỉ dùng cho **setTo** hoặc API tương ứng.

Ví dụ:

~~~java
String[] addresses = request.recipients().stream()
        .map(ContactMailService::validatedMailbox)
        .distinct()
        .toArray(String[]::new);

helper.setTo(addresses);
~~~

Đây là **minh họa nguyên tắc xử lý danh sách**, không phải đoạn mã cắm trực tiếp vào class ở mục trước: tên helper **validatedMailbox** chỉ đại diện hàm kiểm tra một địa chỉ. Trong ứng dụng thật, dùng một hàm validation đã được định nghĩa nhất quán và áp dụng giới hạn số người nhận trước khi dựng message.

### 8.2. Không cho client tự đặt Bcc nội bộ

Một hệ thống có thể cần Bcc một mailbox lưu trữ tuân thủ chính sách. Nếu đó là yêu cầu cố định của tổ chức, hãy đặt trong cấu hình server:

~~~java
helper.setBcc("audit@example.org");
~~~

Không nên nhận trường **bcc** tùy ý từ request công khai rồi chuyển vào lệnh gửi, vì một địa chỉ hoàn toàn hợp lệ vẫn có thể là nơi nhận dữ liệu ngoài dự kiến. **Header validation chỉ chặn input sai cấu trúc; authorization quyết định ai được nhận nội dung.**

### 8.3. Bcc và ranh giới bảo mật

Thông thường, Jakarta Mail gửi Bcc như recipient của envelope mà không công khai địa chỉ đó trong header To/Cc mà các người nhận khác nhìn thấy. Tuy nhiên:

- Bcc không thay thế kiểm soát quyền đọc nội dung.
- Việc tự dựng raw header Bcc có thể làm lộ địa chỉ hoặc gây sai cấu trúc.
- Log của hệ thống gửi vẫn có thể chứa địa chỉ Bcc cho mục đích vận hành.
- Người nhận Bcc có thể tự tiết lộ danh tính khi trả lời.

Vì vậy, đừng dùng Bcc làm cơ chế phân quyền hoặc bảo vệ tài liệu mật.

## 9. Subject và tên hiển thị: giá trị một dòng nhưng vẫn cần Unicode

Một tiêu đề hợp lệ có thể chứa tiếng Việt:

~~~text
Subject: Xác nhận đặt hàng tháng 11
~~~

Tên người gửi cũng có thể là:

~~~text
Nguyễn An
~~~

Không có lý do phải loại bỏ toàn bộ ký tự ngoài ASCII. Cách đúng là kiểm tra **ký tự điều khiển và giới hạn trường**, rồi để thư viện mã hóa header cho phù hợp với chuẩn MIME/Internet message.

### 9.1. Header folding là việc của thư viện

Các header dài có thể được biểu diễn thành nhiều dòng theo quy tắc **folding** được định nghĩa trong chuẩn email. Việc gấp dòng hợp lệ có quy tắc riêng; dòng tiếp nối thường có whitespace ở đầu và thuộc cùng header.

Điều này khác với một input chứa:

~~~text
Chủ đề hợp lệ\r\nBcc: ...
~~~

Ở đây, dữ liệu cố ý mang ký tự kết thúc dòng rồi bắt đầu một tên header khác. Ứng dụng không nên để người dùng điều khiển việc gấp dòng hay tạo header mới từ một trường Subject.

Thư viện như Jakarta Mail có thể xử lý encoding/folding khi dựng thông điệp. Không nên tự “chèn \r\n cho đẹp” vào giá trị Subject.

### 9.2. Tên hiển thị khác với địa chỉ email

Ví dụ một địa chỉ gồm personal name và mailbox:

~~~text
"Nguyễn An" <an@example.net>
~~~

Đây là cấu trúc khác với chuỗi mailbox thuần:

~~~text
an@example.net
~~~

Nếu một form chỉ hỏi “Email”, có thể quy định chỉ nhận mailbox. Nếu form còn hỏi “Tên hiển thị”, lưu vào trường riêng và dùng API cho personal name. Không ghép tên và địa chỉ theo mẫu chuỗi raw mà thiếu kiểm tra dấu ngoặc kép, control character hoặc ngữ nghĩa của parser.

### 9.3. Những ký tự gây nhầm lẫn khi hiển thị

Ngoài CRLF, tên hiển thị có thể chứa ký tự điều khiển định hướng chữ, ký tự vô hình hoặc chuỗi dễ gây hiểu nhầm khi copy/paste. Những ký tự này không nhất thiết tạo header mới, nhưng có thể khiến địa chỉ hoặc tên hiển thị trông khác dữ liệu gốc.

Với trường nhạy cảm về danh tính, ứng dụng có thể áp dụng thêm chính sách Unicode, hiển thị địa chỉ thật ở cạnh tên, hoặc dùng các định danh đã được xác minh. **Đừng đánh đồng mọi vấn đề hiển thị Unicode với CRLF injection**; cách phòng vệ và tác động khác nhau.

## 10. Custom header: chỉ dùng tên trường do ứng dụng xác định

Ứng dụng đôi khi thêm metadata để đối chiếu sự kiện gửi:

~~~text
X-Request-Id: 7e3d02ec-38b1-4e28-b0ef-c8546feac80a
~~~

Một cách phù hợp là sử dụng **tên header cố định trong code** và **giá trị do server tạo từ dữ liệu có cấu trúc**:

~~~java
java.util.UUID requestId = java.util.UUID.randomUUID();
message.setHeader("X-Request-Id", requestId.toString());
~~~

Ví dụ này dùng API mức thấp **MimeMessage.setHeader** nhưng không lấy tên header từ request. Giá trị là UUID do ứng dụng tạo, nên có định dạng giới hạn rõ ràng.

Trường hợp nguy hiểm hơn là:

~~~java
message.setHeader(request.headerName(), request.headerValue());
~~~

Nếu API công khai cho phép người dùng đặt mọi tên và giá trị header, kẻ tấn công có thể tìm cách tạo hoặc ghi đè các trường có ý nghĩa hệ thống như **From**, **Reply-To**, **Subject**, **Content-Type** hoặc metadata điều khiển xử lý email. Ngay cả khi thư viện chặn CRLF, nguy cơ **thay đổi ngữ nghĩa header hợp lệ** vẫn tồn tại.

Nếu nghiệp vụ bắt buộc có custom header do người dùng điều khiển một phần, cần:

- Danh sách tên header cố định được cho phép hoặc ánh xạ từ các key nghiệp vụ.
- Validation value theo loại dữ liệu cụ thể, không nhận đoạn raw header.
- Quy định không cho ghi đè các trường hạ tầng hoặc trường chứa thông tin xác thực.
- Giới hạn độ dài và số lượng header.
- Phân quyền và ghi nhận sự kiện nghiệp vụ khi thay đổi metadata nhạy cảm.

Một số header như **Date**, **Message-ID** và metadata MIME có quy tắc riêng; nên để thư viện hoặc thành phần gửi thích hợp quản lý khi không có yêu cầu chính đáng khác.

## 11. Attachment filename và MIME header cũng là dữ liệu có cấu trúc

Khi gửi file đính kèm, thông điệp có thể gồm:

~~~text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64
~~~

Nếu tên tệp do khách hàng cung cấp, đó cũng là input không tin cậy được đưa vào **tham số MIME header**. Không được tự tạo header như:

~~~java
String disposition =
        "attachment; filename=\"" + uploadedName + "\"";
message.setHeader("Content-Disposition", disposition);
~~~

Một tên có dấu ngoặc kép, ký tự điều khiển hoặc ngữ nghĩa đường dẫn có thể làm thay đổi cách parser hiểu tham số, tùy cách tạo và giải mã.

Trong Spring Mail, nên dùng API attachment:

~~~java
helper.addAttachment(
        safeFilename,
        new org.springframework.core.io.FileSystemResource(filePath)
);
~~~

Thư viện hỗ trợ tạo MIME part, Content-Disposition và encoding cần thiết. Ứng dụng vẫn nên:

1. Quy định tên hiển thị có độ dài và ký tự phù hợp.
2. Không để đường dẫn nội bộ hoặc secret lọt vào filename.
3. Không dùng filename không tin cậy để ghép đường dẫn đọc/ghi file.
4. Kiểm tra loại và dung lượng file theo nghiệp vụ.
5. Chỉ gửi file mà người dùng hiện tại được quyền truy cập.

**Filename hợp lệ về cú pháp không có nghĩa file an toàn**, và MIME encoding không phải cơ chế chống phần mềm độc hại.

## 12. Khi dữ liệu đến từ email nhận được

Một hệ thống có thể đọc email khách hàng rồi tạo thư chuyển tiếp, ticket hoặc câu trả lời tự động. Dữ liệu ở header của **email nhận** cũng cần được coi là không tin cậy:

- Header **Subject** có thể chứa giá trị lạ hoặc đã được MIME-encode.
- Header **From** có thể bị giả mạo hoặc có display name đánh lừa.
- Header **Reply-To** có thể khác From.
- Một email có thể chứa nhiều header trùng tên hoặc cấu trúc không đúng dự kiến.
- Tên attachment, Content-ID và các tham số MIME có thể chứa dữ liệu bất thường.

Nếu ứng dụng đọc **Subject** từ thư nhận rồi đặt lại nó làm Subject của thư gửi, hãy xử lý như một đầu vào không tin cậy mới. Nếu ứng dụng dùng **Reply-To** từ thư nhận làm người nhận của email trả lời tự động, còn cần chính sách chống gửi tự động đến địa chỉ không phù hợp và các vòng lặp auto-reply.

Không nên lấy nguyên khối header của email khách hàng và chèn vào một email mới. Nếu muốn trích dẫn metadata trong body, có thể trình bày dưới dạng văn bản đã được escape theo ngữ cảnh hoặc đính kèm thư gốc theo đúng cơ chế MIME.

### Đọc header thô khác với dùng trường đã được parse

Với Jakarta Mail, có thể lấy các trường đã được parser diễn giải thông qua các API tương ứng. Tuy nhiên, parser cung cấp dữ liệu cấu trúc **không đồng nghĩa với kiểm tra quyền hoặc độ tin cậy nghiệp vụ**. Ví dụ một địa chỉ trong header From có thể được parse thành công nhưng vẫn thuộc người gửi giả danh.

Nếu cần bảo đảm người gửi đã được xác thực, phải dựa thêm trên cơ chế xác thực và đánh giá email của hạ tầng nhận (SPF/DKIM/DMARC), chính sách tin cậy của hệ thống và luồng xác minh nghiệp vụ phù hợp.

## 13. Kiểm tra theo lớp: DTO, validation, mail builder, transport

Một ứng dụng Spring gửi thư từ request có thể tổ chức các lớp như sau:

~~~text
HTTP request / webhook / database
             |
             v
        Input DTO
             |
             v
   Validation theo từng field
   - single mailbox cho Reply-To
   - single line cho Subject
   - độ dài cho name/body
   - quyền truy cập người nhận
             |
             v
      Mail composition
   - From cố định theo cấu hình
   - To được server quyết định
   - Reply-To đã parse
   - Subject đã kiểm soát
   - Body bằng setText
             |
             v
  JavaMailSender / Jakarta Mail
             |
             v
     SMTP transport / provider
~~~

Không nên chỉ kiểm tra ở controller rồi để các luồng khác như scheduler, event consumer hoặc batch import gọi trực tiếp một mail service nhận raw header. Mỗi API nội bộ tạo thông điệp cần có hợp đồng rõ ràng về dữ liệu đã kiểm tra, hoặc thực hiện validation tại ranh giới riêng của nó.

Một thiết kế có thể tách giá trị **địa chỉ đã được parse** và **tiêu đề đã được kiểm tra** thành kiểu dữ liệu riêng, giúp giảm khả năng truyền nhầm body vào Subject. Nhưng các kiểu đó phải thật sự được xây dựng qua đường validation, không thể chỉ đổi tên biến để biến dữ liệu trở nên đáng tin cậy.

## 14. Những ca kiểm tra có thể dùng khi xây dựng chức năng gửi thư

Khi phát triển tính năng gửi thư, cần kiểm tra cả giá trị thông thường và input bất thường. Bảng dưới mô tả **hành vi kỳ vọng của ứng dụng**; đây là các tình huống nên kiểm thử trong môi trường phát triển, không phải kết quả của một lần chạy test tại đây.

| Dữ liệu nhập | Trường | Kết quả kỳ vọng |
| --- | --- | --- |
| **Xác nhận đơn hàng** | Subject | Được chấp nhận |
| **Thông báo tháng 11** | Subject | Được chấp nhận, giữ nguyên tiếng Việt |
| Giá trị chứa **\r** hoặc **\n** | Subject | Bị từ chối trước khi dựng message |
| Giá trị chứa **NUL** | Subject | Bị từ chối |
| Tiêu đề vượt giới hạn độ dài | Subject | Bị từ chối có thông báo phù hợp |
| **an@example.net** | Email đơn | Được parse thành một mailbox |
| Hai địa chỉ phân cách dấu phẩy | Email đơn | Bị từ chối nếu form chỉ cho phép một mailbox |
| Chuỗi có display name | Email đơn | Bị từ chối nếu chính sách chỉ cho phép mailbox thuần |
| Địa chỉ của người ngoài phạm vi được phép | To/Bcc | Bị từ chối dù đúng cú pháp |
| Nội dung có nhiều đoạn xuống dòng | Body plain text | Được giữ dòng trong phần thân |
| Chuỗi chứa ký tự HTML đặc biệt | Body HTML | Được escape/sanitize theo template và ngữ cảnh |
| Tên file chứa ký tự điều khiển | Filename | Bị từ chối hoặc được xử lý theo chính sách tên file được định nghĩa |

Nên quan sát **message đã tạo** trong một SMTP test server hoặc công cụ capture thư, tập trung vào ranh giới header/body và danh sách recipients thực sự. Tránh gửi dữ liệu kiểm thử có tính chất tấn công đến hộp thư bên ngoài hoặc một địa chỉ không thuộc quyền kiểm soát.

Một vài tình huống nên kiểm tra bổ sung: chuỗi Unicode dài, tên hiển thị có dấu, đầu vào JSON đã qua nhiều lần decode, request có trường Bcc không được khai báo trong DTO, và việc lỗi validation có ngăn gọi **mailSender.send(...)** hay không.

## 15. Các sai lầm thường gặp

### 15.1. Tin rằng dùng Jakarta Mail là đủ, không cần validation

Dùng API chuyên dụng giảm nguy cơ tự ghép sai cú pháp. Nhưng thư viện không biết một khách hàng có được phép gửi đến **finance@example.org** hay không. Validation, quyền gửi và giới hạn người nhận là trách nhiệm của ứng dụng.

### 15.2. Chỉ kiểm tra ký tự “@” trong địa chỉ

Chuỗi có **@** chưa chắc là mailbox hợp lệ. Cần parse và kiểm tra theo loại input; sau đó áp dụng chính sách địa chỉ và xác minh sở hữu khi cần.

### 15.3. Xóa mọi ký tự xuống dòng trong toàn bộ request

Body của email hợp lệ có thể nhiều dòng. Hãy từ chối newline trong **header một dòng**, đồng thời giữ nguyên newline cần thiết trong **body plain text**. Dùng chính sách riêng theo trường.

### 15.4. Tin toàn bộ dữ liệu đã lưu trong database

Dữ liệu có thể đã được người dùng nhập từ trước và được lưu nguyên dạng. Khi đưa vào header của một email mới, nó lại đi qua một **trust boundary** và cần được kiểm tra theo cách dùng mới.

### 15.5. Cho phép user tùy ý gửi To hoặc Bcc

Địa chỉ đúng cú pháp vẫn có thể là người nhận trái phép. Quy tắc nghiệp vụ phải xác định ai được nhận những thông tin nào. Nếu ứng dụng là biểu mẫu liên hệ tới bộ phận hỗ trợ, **To** nên được cấu hình ở server thay vì lấy từ input công khai.

### 15.6. Tự ghép dòng Content-Disposition để đặt filename

Tên tệp là tham số MIME có cách quoting và mã hóa riêng. Sử dụng **addAttachment** và kiểm tra tên trước khi đưa vào API.

### 15.7. Nghĩ rằng HTML escaping xử lý được header injection

Escaping HTML chỉ phục vụ ngữ cảnh HTML. Nó không kiểm tra CRLF trong Subject hay cú pháp của recipient. Mỗi loại output cần kiểm soát phù hợp.

### 15.8. Tự chuẩn hóa để biến input bất thường thành hợp lệ

Các biến đổi như bỏ xuống dòng, bỏ dấu phẩy hoặc cắt bừa chuỗi có thể làm thay đổi người nhận hay tiêu đề mà người dùng không nhận ra. Với những trường xác định cấu trúc email, nên **từ chối dữ liệu không hợp lệ** và yêu cầu sửa.

## 16. Các câu hỏi thường gặp

**Có nên chặn toàn bộ ký tự Unicode trong Subject không?**

Không. Subject có thể chứa tiếng Việt và nhiều ngôn ngữ khác. Nên kiểm soát control character, độ dài và những trường hợp hiển thị có rủi ro theo chính sách; giao phần mã hóa header hợp lệ cho thư viện.

**Nếu Subject có xuống dòng do người dùng nhấn Enter thì sao?**

Với một field Subject được định nghĩa là một dòng, từ chối hoặc yêu cầu người dùng sửa lại. Nếu giao diện cần cho phép mô tả nhiều dòng, hãy đặt dữ liệu đó vào một trường **body** riêng.

**Chặn \r\n có đủ an toàn không?**

Chặn CRLF giải quyết một cơ chế quan trọng của header injection, nhưng chưa đủ cho toàn bộ bài toán: còn cú pháp địa chỉ, danh sách recipient, spoofing, custom header, MIME filename, giới hạn dữ liệu và quyền gửi. Cần kiểm soát theo trường và theo nghiệp vụ.

**InternetAddress.validate() có xác minh email tồn tại không?**

Không. Nó kiểm tra cú pháp theo thư viện, không kiểm tra quyền sở hữu mailbox, sự tồn tại của tài khoản hoặc khả năng chuyển phát.

**Tại sao không đặt email khách hàng làm From để dễ trả lời?**

Vì From thể hiện danh tính gửi và có thể xung đột với chính sách xác thực miền email. Thường nên giữ From thuộc miền/tài khoản hệ thống và dùng **Reply-To** đã kiểm tra nếu muốn nhân viên trả lời về địa chỉ khách hàng.

**Tự thêm header "X-Correlation-Id" có nguy hiểm không?**

Không nhất thiết. Nếu tên trường cố định trong code, giá trị do server sinh hoặc được kiểm tra đúng định dạng và không cho phép ghi đè trường nhạy cảm, custom header có thể hữu ích cho việc đối chiếu. Rủi ro xuất hiện khi cho đầu vào ngoài hệ thống quyết định tùy ý tên và nội dung header.

**Có thể tin rằng send() chạy không lỗi thì mọi người nhận đều an toàn và đã nhận thư?**

Không. API gửi thư hoàn tất không chứng minh người nhận đã đọc; cũng không chứng minh danh sách recipient ban đầu đã tuân thủ chính sách nghiệp vụ. Việc xác định recipient hợp lệ phải diễn ra trước khi gọi gửi.

**Nếu dùng template engine thì sao?**

Template engine giúp dựng body, đặc biệt là HTML, nhưng không tự giải quyết mọi header injection khi ứng dụng đưa dữ liệu vào From, Reply-To hoặc Subject. Cần phân biệt quy tắc escape của body với quy tắc validation của header.

## 17. Ghi nhớ khi xây dựng email bằng Spring Framework Mail

**Email header là dữ liệu có cấu trúc.** Một giá trị như Subject, Reply-To hay filename không nên có quyền quyết định vị trí kết thúc header hoặc tạo một trường mới. Mẫu lỗi điển hình là dùng dữ liệu không tin cậy có chứa **CRLF** để ghép raw email.

Để xử lý đúng trong ứng dụng Spring:

- **Xác định ranh giới quyền:** From và người nhận nội bộ do server kiểm soát; những trường user được sửa phải được định nghĩa tường minh.
- **Kiểm tra theo loại dữ liệu:** một mailbox cần parser và chính sách một địa chỉ; Subject/tên hiển thị cần loại bỏ đầu vào có ký tự điều khiển bằng cách từ chối; body nhiều dòng có quy tắc khác.
- **Dùng API chuyên dụng:** JavaMailSender/MimeMessageHelper và Jakarta Mail dựng header, MIME và transport; không tự nối raw header từ request.
- **Bảo vệ các ngữ cảnh khác:** HTML cần escape/sanitize, attachment cần kiểm tra tên và dữ liệu, log cần tránh rò rỉ hoặc thể hiện sai dữ liệu.
- **Phân biệt cú pháp với quyền:** địa chỉ hợp lệ về mặt kỹ thuật vẫn có thể không được phép nhận email.

Hiểu được sự khác nhau giữa **header**, **body**, **MIME part** và **SMTP envelope** sẽ giúp xác định đúng nơi cần kiểm soát dữ liệu đầu vào. Khi ứng dụng giữ được ranh giới đó, người dùng có thể nhập nội dung liên hệ bình thường mà không được phép thay đổi cấu trúc hay danh sách gửi thư của hệ thống.
