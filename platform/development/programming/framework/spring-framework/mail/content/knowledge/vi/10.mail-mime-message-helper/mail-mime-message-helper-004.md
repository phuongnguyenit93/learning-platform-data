# Đặt subject và text

Một thông báo email từ ứng dụng Spring thường có hai phần mà người nhận quan tâm đầu tiên: **tiêu đề** (*subject*) để biết thư nói về việc gì và **nội dung** (*text/body*) để đọc chi tiết. Khi sử dụng **Spring Framework Mail**, lớp `MimeMessageHelper` cung cấp các phương thức ngắn gọn để điền hai phần này vào một `MimeMessage`:

~~~java
helper.setSubject("Đơn hàng của bạn đã được xác nhận");
helper.setText("Cảm ơn bạn đã đặt hàng.", false);
~~~

Hai lệnh nhìn đơn giản, nhưng điều cần hiểu nằm phía sau: **Subject là một header của email**, còn **text là nội dung MIME**. Nội dung có thể là văn bản thuần hoặc HTML; một email cũng có thể chứa cả hai dạng để trình đọc thư lựa chọn. Với văn bản tiếng Việt, cần sử dụng charset phù hợp để tránh hiển thị lỗi dấu.

Bài học tập trung vào cách đặt `subject` và `text` đúng mục đích, giải thích các phiên bản quá tải của `setText(...)`, cách chọn plain text hoặc HTML, cấu trúc MIME được tạo ra và những lỗi dễ gặp trong ứng dụng Spring Boot.

## 1. MimeMessageHelper đứng ở đâu trong luồng gửi thư?

`MimeMessageHelper` là lớp hỗ trợ trong package `org.springframework.mail.javamail`. Nó giúp lập trình viên dựng nội dung email thông qua API thuận tiện, thay vì thao tác thủ công với từng header và từng `MimeBodyPart` của Jakarta Mail.

Luồng phổ biến:

~~~mermaid
flowchart LR
    A["Dữ liệu nghiệp vụ"] --> B["Tạo MimeMessage"]
    B --> C["MimeMessageHelper"]
    C --> D["Đặt Subject và Text"]
    D --> E["JavaMailSender.send"]
    E --> F["SMTP relay"]
    F --> G["Hạ tầng nhận email"]
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| `JavaMailSender` | Tạo `MimeMessage` và gửi qua hạ tầng SMTP đã cấu hình. |
| `MimeMessage` | Biểu diễn thông điệp email theo mô hình Jakarta Mail: header, nội dung và các MIME part. |
| `MimeMessageHelper` | Hỗ trợ đặt người gửi, người nhận, Subject, text, HTML, tệp đính kèm và tài nguyên nội tuyến. |
| `setSubject(...)` | Điền **tiêu đề thư**, thuộc nhóm header. |
| `setText(...)` | Điền **nội dung thư**, quyết định dạng plain text/HTML hoặc các bản thay thế. |

`MimeMessageHelper` **không tự gửi thư**. Lời gọi `setSubject` hoặc `setText` chỉ thay đổi đối tượng message đang được chuẩn bị; thao tác gửi chỉ bắt đầu khi ứng dụng gọi `mailSender.send(message)`.

## 2. Tạo helper trước khi đặt subject và text

Ví dụ dưới đây dùng ứng dụng Spring Boot có starter mail và một `JavaMailSender` đã được cấu hình.

### 2.1. Phụ thuộc Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Với Spring Boot sử dụng Jakarta Mail, import các lớp thông điệp từ package `jakarta.mail.*`, trong khi `MimeMessageHelper` vẫn thuộc `org.springframework.mail.javamail`.

### 2.2. Cấu hình SMTP minh họa

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

`smtp.provider.example` chỉ là hostname minh họa. Khi triển khai, cần sử dụng host, port, cơ chế TLS và credential của SMTP provider thực tế. Bí mật nên được lấy từ môi trường hoặc hệ thống quản lý secret; không ghi mật khẩu thật trong repository.

Các thuộc tính cấu hình kết nối này **khác với Subject và Text**. Chúng quyết định ứng dụng gửi thông điệp tới SMTP relay nào, không tự điền nội dung vào một email.

### 2.3. Một message có Subject và plain text

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);

        helper.setSubject("Chào mừng bạn đến với hệ thống");
        helper.setText(
                "Tài khoản của bạn đã được tạo thành công.",
                false
        );

        mailSender.send(message);
    }
}
~~~

Trong constructor:

~~~java
new MimeMessageHelper(message, false, "UTF-8")
~~~

- `message` là đối tượng MIME cần điền dữ liệu.
- `false` có nghĩa ví dụ **không tạo cấu trúc multipart ngay từ đầu**. Điều này phù hợp với một nội dung văn bản đơn giản.
- `"UTF-8"` xác định charset mà helper sử dụng cho các thao tác cần mã hóa ký tự.

Địa chỉ `From` cần được SMTP provider cho phép sử dụng. Để làm ví dụ gọn, mã chưa thêm kiểm tra cú pháp người nhận, xử lý retry hay lưu trạng thái gửi; đó là các trách nhiệm độc lập của ứng dụng.

## 3. setSubject(String): đặt tiêu đề email

Phương thức:

~~~java
helper.setSubject("Xác nhận đăng ký");
~~~

đặt giá trị cho **header `Subject`** của thông điệp. Đây là nội dung thường xuất hiện trong danh sách thư, thông báo trên điện thoại và màn hình chi tiết của ứng dụng đọc email.

Ví dụ:

~~~java
helper.setSubject("Đơn hàng #A102 đã được xác nhận");
~~~

Người đọc thường nhìn thấy:

~~~text
Đơn hàng #A102 đã được xác nhận
~~~

Trong nguồn email thô, dữ liệu có thể xuất hiện ở dạng header tương đương:

~~~text
Subject: =?UTF-8?B?...du-lieu-duoc-ma-hoa...?=
~~~

Đoạn `...du-lieu-duoc-ma-hoa...` trong ví dụ trên chỉ là **placeholder**, không phải Base64 hợp lệ cần giải mã. Thư viện có trách nhiệm tạo chuỗi MIME thực theo quy tắc mã hóa phù hợp.

### 3.1. Subject là header, không phải phần thân

Xét thông điệp:

~~~text
From: notice@example.org
To: buyer@example.net
Subject: Đơn hàng đã được xác nhận
Content-Type: text/plain; charset=UTF-8

Đây là phần nội dung chi tiết của email.
~~~

Dòng `Subject` thuộc phần **header**; phần sau dòng trống mới là **body**. Khi sử dụng `MimeMessageHelper`, không cần tự thêm từ `Subject:` trước chuỗi:

~~~java
// Đúng: truyền giá trị tiêu đề.
helper.setSubject("Đơn hàng đã được xác nhận");

// Không cần và không nên tự kèm tên header:
helper.setSubject("Subject: Đơn hàng đã được xác nhận");
~~~

Cách thứ hai sẽ khiến chữ `Subject:` trở thành một phần của **nội dung tiêu đề**, chứ không phải thao tác tạo header mới.

### 3.2. Subject tiếng Việt và Unicode

Chuỗi Java có thể chứa chữ có dấu, chữ từ nhiều ngôn ngữ và emoji:

~~~java
helper.setSubject("Lịch hẹn của bạn đã được xác nhận 📅");
~~~

Với helper được tạo cùng charset `UTF-8`, thư viện Jakarta Mail có thể chuyển ký tự Unicode của Subject sang dạng header phù hợp, chẳng hạn **MIME encoded-word theo RFC 2047**. Header raw có thể chứa cấu trúc:

~~~text
=?UTF-8?B?...?=
=?UTF-8?Q?...?=
~~~

B và Q là hai cách biểu diễn dữ liệu Unicode bằng các ký tự an toàn cho header email truyền thống. Chúng **không phải phương thức mã hóa bảo mật**. Chương trình đọc thư giải mã header để trình bày chuỗi Subject bình thường.

Một hệ thống email quốc tế hóa cũng có thể hỗ trợ UTF-8 trực tiếp trong header theo các chuẩn thích hợp. Đối với ứng dụng Spring thông thường, việc đưa chuỗi Unicode vào `setSubject(...)` với charset rõ ràng là cách dễ duy trì, thay vì tự tính toán encoded-word.

**Không nên tự gọi Base64 trước khi truyền Subject vào helper.** Nếu gửi chuỗi đã mã hóa vào một API vốn đang chịu trách nhiệm mã hóa header, kết quả có thể bị mã hóa thêm lần nữa hoặc người dùng thấy chuỗi kỹ thuật thay vì tiêu đề.

### 3.3. Độ dài và nội dung Subject

Tiêu đề nên đủ cụ thể để người nhận hiểu email, nhưng không quá dài. Khi Subject chứa dữ liệu từ người dùng hoặc hệ thống ngoài, cần kiểm soát:

- Không để `null`, chuỗi trống hoặc chỉ có khoảng trắng nếu nghiệp vụ yêu cầu có tiêu đề.
- Không đưa mật khẩu, token, mã xác thực hoặc thông tin riêng tư chi tiết vào Subject.
- Hạn chế ký tự điều khiển và các ký tự xuống dòng `CR`/`LF` không phù hợp với header.
- Có giới hạn độ dài theo yêu cầu giao diện và nghiệp vụ; không cắt tùy tiện giữa các ký tự Unicode.
- Không sử dụng nguyên nội dung HTML làm Subject; nó là tiêu đề văn bản chứ không phải vùng hiển thị HTML.

Ví dụ lớp kiểm tra đầu vào:

~~~java
private static String requireSubject(String subject) {
    if (subject == null || subject.isBlank()) {
        throw new IllegalArgumentException(
                "Tiêu đề email không được để trống"
        );
    }

    if (subject.indexOf('\r') >= 0
            || subject.indexOf('\n') >= 0) {
        throw new IllegalArgumentException(
                "Tiêu đề email không được chứa ký tự xuống dòng"
        );
    }

    return subject;
}
~~~

Sau đó gọi:

~~~java
helper.setSubject(requireSubject(subject));
~~~

Cách kiểm tra trên minh họa hai điều kiện cơ bản. Quy định chiều dài, kiểu dữ liệu, ký tự điều khiển khác và nội dung được phép phải được xác định theo yêu cầu của hệ thống.

## 4. setText(String): nội dung văn bản thuần

Phương thức:

~~~java
helper.setText("Xin chào!");
~~~

đặt nội dung **plain text** cho message. Đây là cách phù hợp khi email chỉ có chữ và không cần định dạng HTML.

Ví dụ:

~~~java
helper.setText("""
        Xin chào,

        Yêu cầu hỗ trợ của bạn đã được tiếp nhận.

        Trân trọng,
        Nhóm hỗ trợ
        """);
~~~

Văn bản thuần giữ các dòng và khoảng trắng theo cách xử lý của trình đọc thư. Không có các thẻ HTML như `<p>`, `<strong>` hoặc `<a>` được diễn giải thành phần tử giao diện.

### 4.1. Khi nào dùng plain text?

Plain text đặc biệt phù hợp với:

- Thông báo hệ thống ngắn, có nội dung chủ yếu là chữ.
- Nội dung cần dễ xem trên nhiều ứng dụng đọc thư khác nhau.
- Email không cần bố cục, bảng màu, hình ảnh hoặc trình bày phức tạp.
- Bản thay thế cho nội dung HTML để tăng khả năng đọc khi HTML bị chặn hoặc không được hỗ trợ.

Ví dụ:

~~~text
Xin chào,

Mã yêu cầu hỗ trợ: TKT-1024
Trạng thái: Đã tiếp nhận

Bạn có thể theo dõi yêu cầu trong ứng dụng.
~~~

Nếu nội dung chỉ cần như vậy, `setText(plainText)` thường đủ. Không cần dựng HTML chỉ để hiển thị vài dòng.

### 4.2. Tác dụng của ký tự xuống dòng

Trong plain text, có thể tạo dòng mới bằng ký tự newline trong chuỗi Java:

~~~java
String text = "Xin chào,\n"
        + "\n"
        + "Yêu cầu của bạn đã được tiếp nhận.\n"
        + "\n"
        + "Trân trọng.";
helper.setText(text);
~~~

Việc hiển thị khoảng trắng và xuống dòng có thể khác nhau giữa các ứng dụng đọc mail. Tránh dùng nhiều dấu cách để căn cột hoặc giả định người nhận luôn dùng font monospace.

Trong dữ liệu MIME thô, thư viện có nhiệm vụ chuẩn hóa biểu diễn nội dung và cách xuống dòng phù hợp giao thức email; ứng dụng không cần tự dựng từng dòng MIME theo byte.

## 5. setText(String, boolean): chọn plain text hoặc HTML

Phiên bản quá tải này là một trong những API quan trọng nhất:

~~~java
helper.setText(content, isHtml);
~~~

Ý nghĩa:

- `isHtml = false`: nội dung được coi là **văn bản thuần**.
- `isHtml = true`: nội dung được coi là **HTML**.

Ví dụ so sánh:

~~~java
// Body là văn bản thuần.
helper.setText(
        "Đơn hàng đã được xác nhận.",
        false
);
~~~

và:

~~~java
// Body là HTML.
helper.setText(
        "<p>Đơn hàng đã được <strong>xác nhận</strong>.</p>",
        true
);
~~~

Đây là lựa chọn **loại nội dung**, không phải tùy chọn “gửi thành công”, “bật Unicode” hoặc “bật bảo mật”.

### 5.1. Điều gì xảy ra nếu truyền HTML với false?

~~~java
helper.setText(
        "<h1>Thông báo</h1><p>Xin chào bạn.</p>",
        false
);
~~~

Khi đó, ứng dụng đang khai báo body là plain text. Người nhận có thể thấy nguyên văn các ký tự `<h1>`, `</h1>`, `<p>`, vì trình đọc không được yêu cầu diễn giải chúng như HTML.

### 5.2. Điều gì xảy ra nếu truyền plain text với true?

~~~java
helper.setText(
        "Xin chào,\nYêu cầu của bạn đã hoàn tất.",
        true
);
~~~

Văn bản này sẽ được đánh dấu là HTML. Trình đọc có thể gộp khoảng trắng hoặc hiển thị xuống dòng khác với plain text, vì trong HTML ký tự newline đơn thuần **không tương đương** thẻ `<br>` hoặc `<p>`.

Hãy tạo một nội dung HTML thực sự khi đặt `true`:

~~~java
helper.setText(
        "<p>Xin chào,</p>"
        + "<p>Yêu cầu của bạn đã hoàn tất.</p>",
        true
);
~~~

Không nên dùng `isHtml = true` chỉ vì muốn giữ dấu tiếng Việt: **charset** và **HTML mode** giải quyết hai vấn đề khác nhau.

## 6. setText(String plainText, String htmlText): hai cách biểu diễn cùng nội dung

Một email giao dịch có thể cung cấp **hai phiên bản nội dung**:

- `text/plain` cho trình đọc không hỗ trợ HTML hoặc người dùng ưu tiên dạng văn bản.
- `text/html` cho trình đọc có khả năng trình bày nội dung phong phú.

`MimeMessageHelper` có phiên bản:

~~~java
helper.setText(plainText, htmlText);
~~~

Đây không phải “gửi hai email”. Helper tổ chức hai dạng nội dung trong một cấu trúc MIME kiểu **`multipart/alternative`**, để ứng dụng đọc email chọn dạng nó hỗ trợ.

### 6.1. Ví dụ hai dạng nội dung

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("notice@example.org");
helper.setTo("buyer@example.net");
helper.setSubject("Đơn hàng của bạn đã được xác nhận");

String plainText = """
        Xin chào,

        Đơn hàng #A102 đã được xác nhận.
        Xem thông tin trong tài khoản của bạn.
        """;

String htmlText = """
        <html>
          <body>
            <h2>Đơn hàng đã được xác nhận</h2>
            <p>Đơn hàng <strong>#A102</strong>
               của bạn đã được xác nhận.</p>
            <p>Xem thông tin trong tài khoản của bạn.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);

mailSender.send(message);
~~~

Ở đây constructor nhận `true` để tạo **multipart message**. Điều này quan trọng: phiên bản `setText(plainText, htmlText)` cần một helper hỗ trợ cấu trúc multipart để đặt các phần alternative.

Không dùng constructor non-multipart rồi mong thư viện tự tạo mọi container cần thiết cho API hai nội dung. Với email đơn giản có đúng một text body, constructor với `false` phù hợp; với plain/HTML alternative, nên dùng chế độ multipart.

### 6.2. Vì sao nên có bản plain text?

Một số môi trường email hạn chế HTML; một số người dùng chọn chế độ chỉ đọc văn bản. Bản plain text còn giúp thông điệp duy trì ý nghĩa khi HTML không được diễn giải.

Hai bản nên **tương đương về thông tin quan trọng**. Ví dụ, nếu HTML có ngày hẹn và liên kết hành động thiết yếu, bản plain cũng nên có ngày hẹn và URL đọc được. Không tạo một bản plain trống chỉ để có cho đủ.

Một cấu trúc MIME khái niệm:

~~~text
MIME message
└── multipart/alternative
    ├── text/plain; charset=UTF-8
    └── text/html; charset=UTF-8
~~~

Trong thực tế, tùy chế độ `MimeMessageHelper`, cấu trúc `multipart/alternative` có thể được lồng trong `multipart/mixed` hoặc `multipart/related`. Đừng suy ra vị trí của các part chỉ từ tên phương thức mà không xem cấu trúc MIME thực.

### 6.3. Khi nào không cần hai bản?

Nếu email là một đoạn plain text ngắn, không cần HTML, có thể chỉ gọi `setText(plainText)`. Nếu sản phẩm chọn HTML-only, có thể gọi `setText(htmlText, true)`, nhưng cần hiểu rằng không có bản text/plain thay thế do chính lần gọi đó tạo ra.

Quyết định tạo cả hai là **quyết định về khả năng tương thích và trải nghiệm nhận thư**, không phải bắt buộc về mặt cú pháp đối với mọi email.

## 7. Bảng tổng hợp các phiên bản setText

| Lời gọi | Ý nghĩa | Cấu trúc nội dung |
| --- | --- | --- |
| `setText(String text)` | Đặt văn bản thuần | `text/plain` |
| `setText(String text, false)` | Đặt văn bản thuần tường minh | `text/plain` |
| `setText(String text, true)` | Đặt HTML | `text/html` |
| `setText(String plainText, String htmlText)` | Đặt cả plain text và HTML | `multipart/alternative` (có thể nằm trong container multipart khác) |

Lưu ý khi đọc code: Hai phiên bản có **hai tham số** nhưng ý nghĩa khác nhau hoàn toàn:

~~~java
helper.setText(html, true);
helper.setText(plain, html);
~~~

Ở lời gọi đầu, tham số thứ hai là **boolean**. Ở lời gọi sau, tham số thứ hai là **String**. IDE và trình biên dịch phân biệt chúng qua kiểu tham số.

Nếu một biến `html` có kiểu `String` và bị truyền nhầm vào phiên bản boolean, chương trình không biên dịch; nhưng nếu có sẵn hai chuỗi và chọn nhầm overload, chương trình vẫn có thể tạo message với cấu trúc khác ý định. Nên đặt tên rõ `plainText`, `htmlText` và dùng overload phù hợp.

## 8. Subject và body được mã hóa Unicode khác nhau

Hai phần đều có thể chứa tiếng Việt, nhưng vị trí của chúng trong email khác nhau:

~~~text
Subject: [header MIME của thông điệp]
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

[body của thông điệp]
~~~

**Subject là header:** Jakarta Mail có thể dùng `encoded-word` để biểu diễn Unicode trong header truyền thống. Header raw có thể khác chuỗi Java ban đầu.

**Text là body:** Jakarta Mail đánh dấu loại nội dung như `text/plain` hoặc `text/html` và charset, đồng thời có thể lựa chọn `Content-Transfer-Encoding` thích hợp để chuyển dữ liệu qua email.

Ví dụ:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setSubject("Xin chào – Đơn hàng đã xác nhận ✅");
helper.setText(
        "Cảm ơn bạn. Đơn hàng đã được xử lý.",
        false
);
~~~

Với thông điệp này, cả Subject và text đều có chữ Unicode. Việc chỉ định `UTF-8` giúp thư viện có thông tin charset khi dựng dữ liệu MIME, nhưng **không làm cho hai trường được mã hóa theo cùng một cú pháp**.

### Không mã hóa trước bằng Base64

Đây là một cách làm dễ sai:

~~~java
// Không cần chuyển subject thành Base64 rồi truyền vào helper.
// String encodedSubject = Base64.getEncoder()
//         .encodeToString(subject.getBytes(StandardCharsets.UTF_8));
// helper.setSubject(encodedSubject);
~~~

`setSubject(...)` nhận **văn bản muốn người nhận thấy**, không nhận một trường header MIME đã được dựng thủ công.

Tương tự, không cần tự chuyển body thành Base64 để dùng `setText(...)`. Trừ khi đang triển khai một giao thức tùy chỉnh khác, hãy đưa **nội dung gốc** cho helper và để Jakarta Mail xử lý encoding khi serialize.

## 9. Cấu trúc MIME của text đơn, HTML đơn và multipart

Cùng một nội dung logic, cách dựng có thể tạo cấu trúc khác nhau.

### 9.1. Plain text only

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setSubject("Thông báo");
helper.setText("Yêu cầu đã hoàn tất.");
~~~

Khi biểu diễn dưới dạng raw MIME, phần thân có thể tương tự:

~~~text
Subject: Thong bao
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Yeu cau da hoan tat.
~~~

Ví dụ raw ở trên chỉ minh họa cấu trúc; một Subject/body tiếng Việt có dấu thực tế có thể sử dụng biểu diễn encoding khác.

### 9.2. HTML only

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setSubject("Thông báo");
helper.setText("<p>Yêu cầu đã hoàn tất.</p>", true);
~~~

Phần body thuộc kiểu `text/html`. Lúc này không cần tạo multipart chỉ vì body là HTML.

### 9.3. Plain text + HTML

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setSubject("Thông báo");
helper.setText(
        "Yêu cầu đã hoàn tất.",
        "<p>Yêu cầu đã <strong>hoàn tất</strong>.</p>"
);
~~~

Trường hợp này cần chứa hai MIME part. Jakarta Mail quản lý các boundary để phần `text/plain` và `text/html` không bị trộn vào nhau.

### 9.4. HTML + tệp đính kèm

Nếu thêm PDF hoặc ảnh nội tuyến:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

helper.setSubject("Báo cáo tuần");
helper.setText(
        "Báo cáo tuần đã sẵn sàng.",
        "<p>Báo cáo tuần đã <strong>sẵn sàng</strong>.</p>"
);

helper.addAttachment(
        "report.pdf",
        new ClassPathResource("mail/report.pdf"),
        "application/pdf"
);
~~~

Ví dụ giả định đã import `org.springframework.core.io.ClassPathResource` và tệp `mail/report.pdf` có trên classpath. Chế độ multipart giúp các phần body và attachment được biểu diễn theo cấu trúc phù hợp.

Điểm cần nhớ: **Subject vẫn là header của message**, còn `setText` chỉ xác định những phần nội dung tương ứng. Việc có attachment không làm thay đổi mục đích của `setSubject(...)`.

## 10. Soạn nội dung từ template mà không làm sai Subject/text

Trong ứng dụng thật, Subject và body thường được dựng từ dữ liệu động như tên khách hàng, mã đơn hàng hoặc thời gian hẹn.

~~~java
String subject = "Đơn hàng " + orderCode + " đã được xác nhận";

String plainText = """
        Xin chào,

        Đơn hàng %s của bạn đã được xác nhận.
        """.formatted(orderCode);

helper.setSubject(subject);
helper.setText(plainText, false);
~~~

Việc ghép chuỗi minh họa khá rõ, nhưng khi có nhiều template, đa ngôn ngữ hoặc nhiều biến, nên có tầng render template để chuẩn bị **nội dung logic** trước khi gọi `MimeMessageHelper`.

~~~mermaid
flowchart LR
    A["Dữ liệu đã kiểm tra"] --> B["Template và locale"]
    B --> C["subject / plainText / htmlText"]
    C --> D["MimeMessageHelper"]
    D --> E["MimeMessage"]
~~~

### 10.1. Subject được render như văn bản thuần

Giả sử có template:

~~~text
Đơn hàng {orderCode} đã được xác nhận
~~~

Tầng template thay `{orderCode}` bằng dữ liệu hợp lệ. Không nhúng thẻ HTML để làm đậm Subject; client email không diễn giải Subject như một tài liệu HTML.

Khi có nhiều ngôn ngữ, tạo bản dịch Subject theo locale, rồi đưa chuỗi Unicode cuối cùng vào `setSubject(...)`. Không cần chuyển sang ASCII bằng cách bỏ dấu tiếng Việt.

### 10.2. HTML cần xử lý dữ liệu động theo ngữ cảnh

Giả sử tên khách hàng là nội dung do người dùng nhập. Đoạn sau có rủi ro nếu giá trị được ghép thẳng vào HTML:

~~~java
String html = "<p>Xin chào " + customerName + "</p>";
~~~

Nếu tên chứa ký tự đặc biệt như `<`, `>` hoặc `&`, HTML có thể bị thay đổi. Với dữ liệu không tin cậy, cần sử dụng template engine có cơ chế **escape theo ngữ cảnh HTML** hoặc chức năng escape phù hợp. Không coi `MimeMessageHelper.setText(html, true)` là bộ lọc HTML độc hại: helper chỉ đặt **dạng nội dung HTML**, không tự kiểm định hoặc làm sạch mọi dữ liệu bên trong.

Với URL do bên ngoài cung cấp, cũng phải xác thực scheme, host và quyền truy cập; escape HTML không thay thế việc xác thực URL. Trong email giao dịch, tránh tạo đường dẫn mang token nhạy cảm trong Subject.

### 10.3. Plain text không nên là HTML đã xóa thẻ một cách tùy tiện

Một số ứng dụng muốn tạo bản plain bằng cách loại tất cả các thẻ HTML. Cách này có thể làm mất URL của liên kết, nội dung của bảng hoặc thông tin hành động quan trọng.

Tốt hơn là xây dựng **bản plain có nội dung tương đương**, ví dụ:

~~~text
Xin chào An,

Đơn hàng A102 đã được xác nhận.
Xem chi tiết tại: https://app.example.org/orders/A102
~~~

và HTML:

~~~html
<p>Xin chào An,</p>
<p>Đơn hàng <strong>A102</strong> đã được xác nhận.</p>
<p><a href="https://app.example.org/orders/A102">Xem chi tiết</a></p>
~~~

URL minh họa không đại diện cho dịch vụ thật. Cả hai bản truyền tải cùng thông tin chính, chỉ khác mức trình bày.

## 11. Ví dụ hoàn chỉnh: dịch vụ gửi email với subject, plain và HTML

Giả sử ứng dụng gửi thông báo cập nhật đơn hàng, muốn người nhận có cả nội dung plain text lẫn HTML. Dưới đây là một service đơn giản dùng `JavaMailSender` và `MimeMessageHelper`.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public OrderStatusMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {

        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendStatus(
            String recipient,
            String orderCode,
            String status) throws MessagingException {

        String to = requireText(recipient, "Recipient");
        String code = requireText(orderCode, "Order code");
        String state = requireText(status, "Status");

        // Nội dung nghiệp vụ. Với HTML thực tế, cần escape dữ liệu động.
        String subject = "Cập nhật đơn hàng " + code;

        String plainText = """
                Xin chào,

                Đơn hàng %s có trạng thái: %s.

                Vui lòng đăng nhập ứng dụng để xem chi tiết.
                """.formatted(code, state);

        // Ví dụ đơn giản chỉ sử dụng trạng thái đã được hệ thống kiểm soát.
        // Nếu code/state có thể chứa ký tự HTML, phải escape trước.
        String htmlText = """
                <html>
                  <body>
                    <h2>Cập nhật đơn hàng</h2>
                    <p>Đơn hàng <strong>%s</strong>
                       có trạng thái: <strong>%s</strong>.</p>
                    <p>Vui lòng đăng nhập ứng dụng để xem chi tiết.</p>
                  </body>
                </html>
                """.formatted(code, state);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(fromAddress);
        helper.setTo(to);
        helper.setSubject(requireSubject(subject));
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }

    private static String requireText(
            String value, String fieldName) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " không được để trống"
            );
        }
        return value;
    }

    private static String requireSubject(String value) {
        String subject = requireText(value, "Subject");

        if (subject.indexOf('\r') >= 0
                || subject.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    "Subject không được chứa ký tự xuống dòng"
            );
        }

        return subject;
    }
}
~~~

Cấu hình riêng của ứng dụng:

~~~properties
app.mail.from=${APP_MAIL_FROM}
~~~

Ví dụ trên giả định `orderCode` và `status` là dữ liệu đã được tầng nghiệp vụ kiểm soát và có tập ký tự phù hợp để dùng trực tiếp trong HTML. Nếu chúng đến từ dữ liệu tự do hoặc nguồn không tin cậy, cần **escape HTML theo ngữ cảnh** trước khi render HTML, không chỉ kiểm tra khác rỗng như phương thức `requireText(...)`.

### Phân tích các bước quan trọng

1. `subject` được tạo từ ý nghĩa nghiệp vụ; `plainText` và `htmlText` được dựng như hai cách biểu diễn cùng nội dung.
2. `createMimeMessage()` trả về một đối tượng message mới cho từng yêu cầu gửi.
3. `new MimeMessageHelper(message, true, "UTF-8")` tạo helper có hỗ trợ multipart và charset.
4. `setSubject(...)` đặt tiêu đề vào header Subject.
5. `setText(plainText, htmlText)` đặt các phần thân alternative của MIME message.
6. `mailSender.send(message)` mới thực hiện tương tác SMTP.

**Không tạo một `MimeMessage` singleton và thay Subject/text cho nhiều request đồng thời.** `MimeMessage` là đối tượng mutable; mỗi yêu cầu gửi nên có thông điệp riêng để tránh lẫn người nhận và nội dung.

## 12. Thứ tự gọi setSubject và setText

Đối với message đơn giản, có thể đặt Subject trước Text hoặc ngược lại; hai phương thức tác động đến các vùng dữ liệu khác nhau của thông điệp.

Ví dụ:

~~~java
helper.setSubject("Thông báo");
helper.setText("Nội dung.", false);
~~~

hoặc:

~~~java
helper.setText("Nội dung.", false);
helper.setSubject("Thông báo");
~~~

Hai cách đều có ý nghĩa là đặt một Subject và một body.

Nhưng cần chú ý **các lần gọi setText kế tiếp thường thay thế nội dung body mà helper đang quản lý**, không phải “nối thêm đoạn văn”:

~~~java
helper.setText("Nội dung đầu tiên.", false);
helper.setText("Nội dung thứ hai.", false);
~~~

Không nên mong nhận được:

~~~text
Nội dung đầu tiên.
Nội dung thứ hai.
~~~

Nếu muốn nối hai đoạn, hãy dựng một chuỗi hoàn chỉnh trước khi gọi một lần:

~~~java
String body = """
        Nội dung đầu tiên.

        Nội dung thứ hai.
        """;

helper.setText(body, false);
~~~

Với multipart, đừng trộn tùy tiện nhiều phiên bản `setText(...)` để mong helper ghép thêm nhiều body part. Hãy xác định cấu trúc nội dung cần tạo, chọn overload phù hợp và đặt nội dung chính theo ý định.

### Khi có ảnh nội tuyến, nên đặt Text trước

Với email HTML có hình ảnh tham chiếu bằng `cid:`, cách dùng thường được khuyến nghị là **gọi `setText(...)` trước rồi mới `addInline(...)`**:

~~~java
helper.setText(
        "<p>Xin chào!</p><img src=\"cid:logo\" alt=\"Logo\">",
        true
);
helper.addInline(
        "logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Đoạn này giả định helper được dựng ở chế độ multipart phù hợp và đã import `ClassPathResource`. Thứ tự trên giúp tránh vấn đề tương thích với một số trình đọc email khi nhận diện tài nguyên inline.

Việc thêm ảnh nội tuyến hoặc attachment yêu cầu hiểu cấu trúc MIME; nó không làm thay đổi vai trò của Subject.

## 13. setText có tự gửi thư hoặc đánh dấu đã đọc không?

Không. Một vài tên phương thức trong hệ sinh thái mail có thể gây nhầm lẫn:

- `setSubject(...)` chỉ đặt tiêu đề.
- `setText(...)` chỉ đặt body.
- `saveChanges()` có thể hoàn thiện một số header/metadata MIME khi cần; nó **không gửi SMTP**.
- `JavaMailSender.send(...)` mới nộp message qua SMTP transport.
- Thư được relay chấp nhận **không đồng nghĩa** thư đã đến Inbox hoặc được người nhận mở.

Sơ đồ trạng thái khái niệm:

~~~mermaid
flowchart TD
    A["MimeMessage mới"] --> B["Đặt Subject, Text, From, To"]
    B --> C["Message đã chuẩn bị"]
    C --> D["JavaMailSender.send"]
    D --> E["SMTP relay tiếp nhận hoặc trả lỗi"]
    E --> F["Quy trình chuyển phát về sau"]
~~~

Một phương thức gọi `setText` thành công chỉ cho biết đối tượng được cập nhật theo API; nó không chứng minh body đã được email client hiển thị đúng, không kiểm tra người nhận tồn tại và không xác nhận hạ tầng đã chuyển phát.

## 14. Đọc lại subject và text khi cần quan sát message

Trong quá trình phát triển, có thể kiểm tra các trường của một `MimeMessage` vừa dựng:

~~~java
String subject = message.getSubject();
String contentType = message.getContentType();
boolean isPlainText = message.isMimeType("text/plain");
boolean isHtml = message.isMimeType("text/html");
~~~

`getSubject()` cung cấp cách đọc tiêu đề theo API Jakarta Mail. `getContentType()` cho biết kiểu MIME của đối tượng hiện tại. Tuy nhiên, với message có multipart, cấp ngoài có thể là `multipart/mixed` hoặc `multipart/related` ngay cả khi một part con là `text/html`.

Nếu muốn xem body trực tiếp:

~~~java
Object content = message.getContent();
~~~

Kiểu của `content` có thể là `String`, `Multipart` hoặc dạng dữ liệu khác tùy `Content-Type` và cách message được dựng. **Không ép kiểu luôn thành `String`** với mọi message.

Với email thử nghiệm đơn giản, có thể quan sát MIME đã được serialize:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

static String rawMimeForLocalTest(MimeMessage message)
        throws MessagingException, IOException {

    message.saveChanges();

    ByteArrayOutputStream out = new ByteArrayOutputStream();
    message.writeTo(out);

    return new String(
            out.toByteArray(),
            StandardCharsets.US_ASCII
    );
}
~~~

**Lưu ý:** Đây chỉ là ví dụ quan sát header và ranh giới MIME trong môi trường phát triển với dữ liệu giả; biểu diễn raw MIME có thể chứa các byte không phải ASCII trong một số cấu hình, vì vậy không nên coi phép `new String(..., US_ASCII)` là cách đọc mọi thông điệp Unicode một cách đầy đủ. Nếu cần phân tích MIME thật, hãy dùng API Jakarta Mail hoặc lưu byte nhị phân nguyên vẹn trong công cụ kiểm thử thích hợp.

`writeTo(...)` có thể truy cập dữ liệu tệp đính kèm và tiêu thụ bộ nhớ theo kích thước thông điệp. Không dùng cách này như một bước bắt buộc cho mọi email production, và **không ghi raw MIME chứa dữ liệu khách hàng vào log**.

### Kiểm tra thuộc tính Subject trực tiếp

Khi muốn xem giá trị thô của header:

~~~java
message.saveChanges();

String rawSubject = message.getHeader("Subject", null);
String decodedSubject = message.getSubject();
~~~

`rawSubject` có thể chứa encoded-word hoặc folding của header; `decodedSubject` thuận tiện hơn cho ứng dụng. Đừng viết test phụ thuộc vào **một chuỗi Base64 cụ thể** do thư viện sinh, vì cách mã hóa và chia header có thể thay đổi trong phạm vi chuẩn.

## 15. Xử lý lỗi khi đặt Subject và Text

Các API xây dựng MIME có thể ném `MessagingException`; bên trong quá trình gửi, Spring còn sử dụng các ngoại lệ thuộc nhóm `MailException`. Nên phân biệt lỗi dữ liệu đầu vào với lỗi hạ tầng SMTP.

| Hiện tượng | Khả năng nguyên nhân | Cách tiếp cận |
| --- | --- | --- |
| Subject rỗng | Nghiệp vụ chưa render tiêu đề | Kiểm tra giá trị trước khi gọi `setSubject` |
| Người nhận thấy chữ `<p>` hoặc `<strong>` | Dữ liệu HTML được khai báo như plain text | Sử dụng `setText(html, true)` khi muốn hiển thị HTML |
| Xuống dòng trong nội dung không như mong đợi | Đưa plain text vào HTML mode | Viết HTML đúng nghĩa hoặc dùng plain text |
| Body đúng nhưng Subject lỗi dấu | Charset nguồn hoặc mã hóa header chưa phù hợp | Kiểm tra chuỗi Java trước gửi và cách dùng helper với UTF-8 |
| Không có bản plain text | Chỉ dùng `setText(html, true)` | Cân nhắc `setText(plainText, htmlText)` với multipart |
| Lỗi khi đặt cả plain/HTML | Helper không được tạo ở chế độ multipart phù hợp | Tạo helper với multipart mode trước khi gọi overload hai String |
| HTML hiển thị nội dung không mong muốn | Dữ liệu động chưa được escape | Escape theo ngữ cảnh trong tầng template |
| SMTP báo auth/TLS/connection lỗi | Cấu hình gửi không phù hợp hoặc hạ tầng lỗi | Kiểm tra host, port, credential, TLS và thông báo từ SMTP |
| Email được gửi nhưng không thấy trong Inbox | Bounce, spam, chính sách của hệ thống nhận | Theo dõi trạng thái nhà cung cấp, không chỉ xem lệnh `setText` |

### Tách lỗi dữ liệu và lỗi gửi

Ví dụ một API có thể nhận Subject và body từ tầng nghiệp vụ:

~~~java
if (subject == null || subject.isBlank()) {
    throw new IllegalArgumentException(
            "Subject không hợp lệ"
    );
}

if (body == null || body.isBlank()) {
    throw new IllegalArgumentException(
            "Nội dung email không hợp lệ"
    );
}
~~~

Đây là lỗi dữ liệu cần được xử lý trước khi liên hệ SMTP.

Ngược lại, nếu `mailSender.send(message)` thất bại do kết nối, xác thực hoặc server từ chối, đó là lỗi của **quá trình gửi**. Việc kiểm tra Subject/body trước gửi không thể thay thế cơ chế retry, xử lý bounce hoặc quản trị SMTP.

## 16. Những ngộ nhận cần tránh

### “setSubject chỉ hỗ trợ tiếng Anh không dấu”

Không. Có thể truyền chuỗi Java chứa tiếng Việt có dấu và Unicode. Khi dùng `MimeMessageHelper` và charset phù hợp, Jakarta Mail sẽ xử lý biểu diễn header.

### “setText nhận HTML thì tự hiểu phải hiển thị HTML”

Không phải lúc nào cũng vậy. `setText(String)` đặt plain text. Muốn HTML, cần dùng `setText(String, true)` hoặc phiên bản hai chuỗi plain/HTML.

### “Tham số true của constructor chính là HTML mode”

Không. Trong `new MimeMessageHelper(message, true, "UTF-8")`, `true` biểu thị **multipart mode**. Trong `setText(html, true)`, `true` lại biểu thị **isHtml**. Hai vị trí boolean có ý nghĩa độc lập.

### “Chỉ cần đặt Content-Type là tất cả email reader sẽ hiển thị giống nhau”

Không. Ứng dụng đọc thư có các mức hỗ trợ và chính sách an toàn HTML khác nhau. Thư viện giúp tạo MIME đúng cấu trúc, nhưng CSS, hình ảnh và bố cục có thể bị giới hạn.

### “setText(plain, html) tạo hai email khác nhau”

Không. Nó tạo **hai dạng nội dung trong cùng message** qua cấu trúc MIME alternative. Việc chọn dạng để hiển thị do chương trình đọc thư quyết định.

### “Có thể đặt Subject rồi tự thêm CRLF để chèn header”

Không nên. Subject cần được xử lý như dữ liệu văn bản, không phải một khối header raw. Dữ liệu động có ký tự xuống dòng phải được kiểm tra để tránh lỗi cú pháp và nguy cơ header injection.

### “Mã hóa Base64 cho Subject sẽ giúp bảo mật”

Không. MIME encoded-word dùng để **biểu diễn ký tự**, không phải để giữ bí mật. Email Subject vẫn có thể được hệ thống vận chuyển, lưu trữ và trình đọc giải mã.

### “setText xong là thư đã đến người nhận”

Không. `setText` chỉ thay đổi message. `send` thực hiện nộp thư tới SMTP; chuyển phát cuối cùng và trạng thái đọc cần những cơ chế theo dõi khác.

### “Cần gọi setText nhiều lần để thêm đoạn văn”

Thông thường, hãy tạo **một body hoàn chỉnh** rồi gọi `setText` một lần theo kiểu mong muốn. Các lần đặt nội dung tiếp theo có thể thay thế cấu trúc trước, không có nghĩa nối thêm đoạn.

## 17. Câu hỏi thực hành

**Câu 1.** Đâu là lời gọi thích hợp cho email chỉ chứa văn bản thuần?

~~~java
helper.setText("Xin chào bạn.", false);
~~~

`setText("Xin chào bạn.")` cũng phù hợp. Không cần dùng `true` nếu không muốn HTML.

**Câu 2.** Muốn hiển thị “Hoàn tất” bằng chữ đậm trong HTML thì viết gì?

~~~java
helper.setText(
        "<p>Đã <strong>hoàn tất</strong>.</p>",
        true
);
~~~

Đoạn HTML được truyền như body, còn Subject vẫn được đặt bằng `setSubject(...)`.

**Câu 3.** Có plain text và HTML tương đương. Có nên gọi `setText(plain)` rồi `setText(html, true)` để tạo alternative không?

**Không.** Hãy tạo helper có multipart và gọi `setText(plainText, htmlText)` để biểu diễn hai dạng nội dung cùng một message.

**Câu 4.** `new MimeMessageHelper(message, true, "UTF-8")` có phải đang đặt body HTML không?

**Không.** `true` ở đây yêu cầu chế độ multipart; phải gọi `setText(html, true)` mới khai báo body HTML.

**Câu 5.** Chuỗi Subject là `"Đặt lịch thành công ✅"`. Có cần tự mã hóa Base64 rồi mới gọi `setSubject` không?

**Không.** Đưa chuỗi Unicode gốc vào helper với charset thích hợp; thư viện xử lý mã hóa header.

**Câu 6.** Một người gửi email với body HTML có tên khách hàng lấy từ form. `setText(html, true)` có tự escape tên người dùng không?

**Không.** Cần escape dữ liệu động theo ngữ cảnh HTML trong tầng tạo template; helper chỉ đặt nội dung và loại MIME.

**Câu 7.** `message.getContentType()` trả về `multipart/mixed`. Có nghĩa nội dung không chứa HTML?

**Không.** HTML có thể nằm trong một MIME part con. Cần hiểu cấu trúc multipart thay vì chỉ kiểm tra Content-Type của cấp ngoài.

**Câu 8.** `mailSender.send(message)` trả về mà không báo lỗi. Điều đó chứng minh người nhận đã mở thư?

**Không.** Đây là kết quả bước gửi qua SMTP relay, không phải bằng chứng người nhận đã mở email.

## 18. Mô hình ghi nhớ

Khi sử dụng `MimeMessageHelper` để đặt Subject và Text, có thể ghi nhớ quy trình:

~~~mermaid
flowchart TD
    A["Tạo MimeMessage"] --> B["Tạo MimeMessageHelper với UTF-8"]
    B --> C["Đặt From, To, Subject"]
    C --> D{"Nội dung cần định dạng nào?"}
    D -->|"Chỉ plain text"| E["setText(text)"]
    D -->|"Chỉ HTML"| F["setText(html, true)"]
    D -->|"Plain + HTML"| G["Multipart + setText(plain, html)"]
    E --> H["JavaMailSender.send(message)"]
    F --> H
    G --> H
~~~

Bốn ý quan trọng nhất:

1. **`setSubject(String)` đặt header tiêu đề**, không đặt body và không nên nhận chuỗi raw `Subject: ...`.
2. **`setText(String)` hoặc `setText(text, false)` đặt plain text**; **`setText(html, true)` đặt HTML**.
3. **`setText(plainText, htmlText)` tạo hai cách thể hiện cùng nội dung** và cần helper có cấu trúc multipart phù hợp.
4. **UTF-8, kiểm tra dữ liệu động và bảo mật là những trách nhiệm cần thiết**, nhưng chúng không thay đổi ý nghĩa các API đặt Subject/Text.

Với ứng dụng Spring Boot, mã nghiệp vụ nên chuẩn bị tiêu đề và nội dung cần hiển thị dưới dạng chuỗi Java, xác thực dữ liệu nguồn, chọn overload `setText(...)` theo loại nội dung, rồi để `MimeMessageHelper` và Jakarta Mail tạo thông điệp MIME. Sau đó `JavaMailSender` mới phụ trách việc gửi qua SMTP đã cấu hình.
