# multipart/mixed cho nội dung và tệp đính kèm

Một email có thể chứa lời nhắn, HTML, hình ảnh và các tệp như PDF, CSV hoặc ZIP. Tuy nhiên, nội dung email được truyền dưới dạng một **thông điệp có cấu trúc MIME**, không phải một chuỗi văn bản rồi nối trực tiếp dữ liệu nhị phân vào cuối thư.

Trong **Spring Framework Mail**, kiểu nội dung **multipart/mixed** là nền tảng quan trọng khi muốn gửi **phần thân email kèm một hoặc nhiều tệp đính kèm**. Từ khóa *mixed* diễn tả rằng một thông điệp chứa nhiều phần độc lập: ví dụ một phần để người nhận đọc và các phần còn lại là những tài liệu được gửi cùng thư.

Một hình dung đơn giản:

~~~text
Email
├── Header: From, To, Subject, MIME-Version, Content-Type
└── multipart/mixed
    ├── Part 1: text/plain       -> Lời nhắn trong email
    ├── Part 2: application/pdf -> Hóa đơn PDF đính kèm
    └── Part 3: text/csv        -> Bảng dữ liệu CSV đính kèm
~~~

Người dùng thường thấy một email có nội dung và hai tệp tải về; một chương trình đọc MIME nhìn thấy **ba body part** được phân cách bằng các boundary. Đây là hai cách nhìn của cùng một thông điệp.

## 1. Vì sao cần MIME và multipart/mixed?

### 1.1. Email văn bản đơn giản

Một email văn bản đơn giản có thể có dạng:

~~~text
From: reports@example.org
To: thao@example.net
Subject: Monthly report
Content-Type: text/plain; charset=UTF-8

Please review the monthly report.
~~~

Phần sau dòng trống ngăn header với body là nội dung văn bản duy nhất. Cấu trúc như vậy không mô tả rõ đâu là một file PDF, đâu là một ảnh nhúng và đâu là nội dung để người nhận đọc.

Nếu chỉ ghép dữ liệu PDF vào sau câu chữ, client email sẽ không tự biết phần nào là tệp có tên riêng, kiểu dữ liệu nào cần tải về hoặc byte nào thuộc tệp.

### 1.2. MIME giải quyết việc biểu diễn nhiều loại nội dung

**MIME (Multipurpose Internet Mail Extensions)** mở rộng cách biểu diễn thông điệp Internet bằng các header như:

- **MIME-Version:** cho biết thông điệp sử dụng cấu trúc MIME, thường là phiên bản 1.0.
- **Content-Type:** mô tả kiểu nội dung, chẳng hạn **text/plain**, **text/html**, **application/pdf** hoặc **multipart/mixed**.
- **Content-Transfer-Encoding:** cho biết nội dung của một part được mã hóa để vận chuyển như thế nào, ví dụ **base64** hoặc **quoted-printable**.
- **Content-Disposition:** gợi ý cách client nên trình bày một phần: **inline** hay **attachment**.
- **Content-ID:** định danh một MIME part, thường dùng khi HTML tham chiếu tài nguyên nhúng.

**multipart/mixed** là một loại **Content-Type** ở cấp thông điệp hoặc cấp part bao, thông báo rằng nội dung bên trong gồm nhiều part độc lập được ghép trong một đơn vị MIME.

### 1.3. MIME nằm ở đâu trong quá trình gửi thư?

Cần tách lớp vận chuyển và lớp biểu diễn:

~~~text
Ứng dụng Spring
    |
    | Tạo MimeMessage gồm header, body và tệp đính kèm
    v
JavaMailSender / Jakarta Mail
    |
    | SMTP: MAIL FROM, RCPT TO, DATA
    v
SMTP server
    |
    | Trong DATA là toàn bộ Internet message có MIME
    v
Máy chủ nhận / ứng dụng đọc thư
    |
    | Phân tích Content-Type và boundary
    v
Hiển thị nội dung + danh sách attachment
~~~

SMTP chịu trách nhiệm **chuyển thông điệp tới người nhận**; MIME cho biết **các byte trong thông điệp có cấu trúc và ý nghĩa gì**. Việc có nhiều MIME part không có nghĩa là phải gọi nhiều lệnh SMTP DATA: thông thường cả cấu trúc multipart được truyền bên trong cùng một lần DATA của giao dịch gửi.

## 2. Cấu trúc chuẩn của một multipart/mixed

Một thông điệp dạng **multipart/mixed** gồm:

1. Header của message, trong đó có **Content-Type: multipart/mixed** cùng tham số **boundary**.
2. Một dòng trống ngăn header tổng với phần nội dung.
3. Các part nối tiếp nhau; mỗi part bắt đầu bằng dấu phân cách boundary.
4. Mỗi part có thể có header riêng, một dòng trống và nội dung riêng.
5. Dấu phân cách đóng cuối cùng có thêm hai dấu gạch ngang **--**.

Ví dụ dưới đây là một email *đầy đủ về mặt cấu trúc minh họa*: phần thân là văn bản, attachment là tệp **note.txt** có nội dung “Hello from attachment.” được mã hóa base64.

~~~text
From: reports@example.org
To: thao@example.net
Subject: Monthly report
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mix-example-001"

--mix-example-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Please read the attached note.

--mix-example-001
Content-Type: text/plain; name="note.txt"
Content-Disposition: attachment; filename="note.txt"
Content-Transfer-Encoding: base64

SGVsbG8gZnJvbSBhdHRhY2htZW50Lg==

--mix-example-001--
~~~

Trong dữ liệu email thực tế, các dòng giao thức dùng kết thúc dòng **CRLF**. Đoạn minh họa trên thể hiện cấu trúc bằng các dòng văn bản để dễ đọc.

### 2.1. Content-Type ở cấp message

~~~text
Content-Type: multipart/mixed; boundary="mix-example-001"
~~~

Dòng này cho biết body của thông điệp không phải một đoạn text/plain đơn lẻ. Đây là một vùng chứa nhiều part và chuỗi **mix-example-001** được sử dụng làm token phân cách.

**multipart/mixed** có hai thành phần chính:

- **multipart**: kiểu nội dung có cấu trúc gồm nhiều part.
- **mixed**: các part là những thành phần độc lập cần được trình bày theo thứ tự phù hợp, thường là lời nhắn và tệp đính kèm.

### 2.2. Boundary: cách tách các part

Mỗi part bắt đầu bằng dòng có **hai dấu gạch ngang trước token boundary**:

~~~text
--mix-example-001
~~~

Sau part cuối cùng, dấu phân cách đóng có **hai dấu gạch ngang bổ sung ở cuối**:

~~~text
--mix-example-001--
~~~

Điều dễ nhầm là **boundary được khai báo là token không có tiền tố hai dấu gạch ngang** trong header. Khi xuất hiện thành dòng phân cách, token mới được thêm tiền tố **--**.

| Vị trí | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Header | boundary="mix-example-001" | Khai báo token phân cách |
| Trước mỗi part | --mix-example-001 | Mở part tiếp theo |
| Sau part cuối | --mix-example-001-- | Kết thúc toàn bộ multipart |
| Header của part | Content-Type: application/pdf | Cho biết kiểu dữ liệu của riêng part đó |

Boundary phải được chọn sao cho không đụng với một dòng dữ liệu có ý nghĩa phân cách trong nội dung các part. Thư viện MIME thường tự tạo token khó trùng, tự lắp dấu phân cách và tự quản lý CRLF. **Không cần tự viết boundary trong mã Spring Mail** khi dùng MimeMessageHelper.

### 2.3. Một part có header riêng

Phần lời nhắn trong ví dụ:

~~~text
--mix-example-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Please read the attached note.
~~~

Tại đây:

- **Content-Type: text/plain** cho biết nội dung là văn bản thuần.
- **charset=UTF-8** xác định cách giải mã byte thành ký tự.
- **Content-Transfer-Encoding: 7bit** phù hợp với dữ liệu ASCII trong ví dụ.
- Dòng trống sau header đánh dấu điểm bắt đầu của **body của part**, khác với phần header tổng của email.

Một part chứa tệp có thể có các header khác:

~~~text
--mix-example-001
Content-Type: text/plain; name="note.txt"
Content-Disposition: attachment; filename="note.txt"
Content-Transfer-Encoding: base64

SGVsbG8gZnJvbSBhdHRhY2htZW50Lg==
~~~

**Content-Disposition: attachment** là tín hiệu phổ biến để email client hiển thị part như tệp đính kèm. Tham số **filename** gợi ý tên file khi lưu. **base64** cho biết nội dung truyền trong body của part là dữ liệu đã được mã hóa, không phải một dòng văn bản cần hiển thị nguyên dạng.

Không nên chỉ dựa vào **filename** để suy ra độ an toàn hoặc loại dữ liệu thực tế. Tên file và Content-Type có thể do bên gửi khai báo sai hoặc cố ý làm giả.

## 3. Tại sao attachment thường được mã hóa base64?

Email và MIME phát triển từ môi trường truyền văn bản. Nội dung nhị phân như PDF, ZIP, ảnh PNG có thể chứa mọi giá trị byte; chuyển nguyên xi mà không dùng cơ chế vận chuyển phù hợp có thể làm hỏng hoặc thay đổi dữ liệu.

**Base64** biểu diễn byte nhị phân bằng tập ký tự ASCII. Ví dụ:

~~~text
Nội dung file: Hello from attachment.
Base64:        SGVsbG8gZnJvbSBhdHRhY2htZW50Lg==
~~~

Đầu nhận dựa vào header **Content-Transfer-Encoding: base64** để giải mã dữ liệu part thành byte gốc.

Các kiểu transfer encoding thường gặp:

| Encoding | Ý nghĩa | Tình huống thường thấy |
| --- | --- | --- |
| **7bit** | Nội dung đã phù hợp miền truyền 7 bit | Văn bản ASCII |
| **quoted-printable** | Giữ phần lớn ký tự ASCII đọc được, mã hóa các byte cần thiết | Email văn bản có dấu hoặc một số byte đặc biệt |
| **base64** | Mã hóa dữ liệu thành ký tự ASCII | PDF, ảnh, tệp nhị phân; đôi khi cả text |
| **8bit** | Cho phép dữ liệu văn bản chứa byte 8 bit khi hạ tầng hỗ trợ đúng cách | Tùy capability và cách vận chuyển của server |

Base64 làm dữ liệu tăng kích thước, về nguyên lý khoảng **4 ký tự cho mỗi 3 byte**, chưa tính xuống dòng và header. Vì vậy, một tệp 15 MB có thể khiến email truyền đi lớn hơn đáng kể 15 MB. Giới hạn kích thước email của SMTP server thường tính trên message đã mã hóa, không chỉ kích thước tệp ban đầu.

**Base64 không mã hóa bảo mật dữ liệu**: ai có nội dung email đều có thể giải mã attachment. Khi gửi tài liệu nhạy cảm, cần áp dụng kiểm soát người nhận và cơ chế bảo vệ phù hợp, thay vì xem base64 là phương pháp giữ bí mật.

### Phân biệt Content-Transfer-Encoding và charset

Hai thông tin này phục vụ hai mục đích:

- **charset=UTF-8**: sau khi thu được byte văn bản, dùng bảng mã nào để chuyển thành ký tự?
- **Content-Transfer-Encoding: base64**: những byte đó đã được biểu diễn thành dữ liệu truyền trên wire bằng cách nào?

Một part có thể đồng thời khai báo:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64
~~~

Khi đọc, client giải mã base64 thành byte rồi giải mã byte theo UTF-8. Đừng nhầm hai bước thành một.

## 4. multipart/mixed và các loại multipart khác

Không phải mọi email có nhiều part đều dùng **multipart/mixed** cho tất cả nội dung. Các subtype khác thể hiện mối quan hệ khác giữa các part.

| Content-Type | Ý nghĩa | Trường hợp sử dụng |
| --- | --- | --- |
| **multipart/mixed** | Những part là các thành phần riêng biệt đi kèm nhau | Nội dung thư + PDF + CSV |
| **multipart/alternative** | Các part là những biểu diễn thay thế của cùng một nội dung | Bản plain text và bản HTML của cùng thông điệp |
| **multipart/related** | Các part có mối liên hệ để cùng tạo một đối tượng trình bày | HTML tham chiếu ảnh nhúng qua Content-ID |
| **multipart/digest** | Tập hợp các thông điệp hoặc nội dung dạng digest | Tổng hợp nhiều thông điệp trong một thư |

Riêng **multipart/form-data** thường gặp khi gửi biểu mẫu HTTP có file upload; nó không đồng nghĩa với **multipart/mixed** trong email dù cùng dùng khái niệm multipart/boundary.

### 4.1. mixed: một lời nhắn và hai tệp riêng

~~~text
multipart/mixed
├── text/plain          -> "Vui lòng xem tài liệu"
├── application/pdf     -> report.pdf (attachment)
└── text/csv            -> data.csv (attachment)
~~~

Đây là mô hình đơn giản, đúng trọng tâm của bài học: những tệp đính kèm là các part độc lập bên cạnh phần nội dung để đọc.

### 4.2. alternative: hai cách hiển thị của cùng nội dung

~~~text
multipart/alternative
├── text/plain -> "Báo cáo đã sẵn sàng"
└── text/html  -> "<p><b>Báo cáo</b> đã sẵn sàng</p>"
~~~

Client thường chọn một biểu diễn phù hợp để hiển thị, không trình bày cả hai như hai tệp đính kèm. Các phiên bản trong **alternative** cần diễn đạt cùng một thông điệp cốt lõi; bản HTML thường đứng sau bản plain text vì là biểu diễn phong phú hơn.

### 4.3. related: HTML và tài nguyên nhúng

~~~text
multipart/related
├── text/html -> <img src="cid:companyLogo">
└── image/png -> Content-ID: <companyLogo>; disposition: inline
~~~

Trong trường hợp này, ảnh dùng để hiển thị **bên trong nội dung HTML**, không chỉ là một tệp độc lập để người dùng tải về. Client dùng **Content-ID** để liên hệ thẻ **cid:** với part chứa ảnh.

Đây là lý do một thư có ảnh nhúng và PDF đính kèm thường cần **cấu trúc multipart lồng nhau**.

## 5. Nội dung HTML và tệp đính kèm: cấu trúc MIME lồng nhau

Giả sử ứng dụng muốn gửi:

- Lời nhắn ở dạng plain text cho client không hiển thị HTML.
- Cùng lời nhắn ở dạng HTML.
- Một tệp PDF để tải về.

Cấu trúc biểu diễn hợp lý là:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
└── application/pdf
    └── Content-Disposition: attachment; filename="report.pdf"
~~~

**Tại sao phải lồng?**

- Nhánh **multipart/alternative** diễn tả hai phiên bản có cùng ý nghĩa của nội dung chính.
- Nhánh **application/pdf** là thành phần đính kèm độc lập với nội dung chính.
- Nút gốc **multipart/mixed** ghép các thành phần đó thành một message.

Một ví dụ MIME thô được rút gọn:

~~~text
MIME-Version: 1.0
From: reports@example.org
To: thao@example.net
Subject: Report
Content-Type: multipart/mixed; boundary="outer-001"

--outer-001
Content-Type: multipart/alternative; boundary="inner-001"

--inner-001
Content-Type: text/plain; charset=UTF-8

Please view the report.

--inner-001
Content-Type: text/html; charset=UTF-8

<p>Please <strong>view the report</strong>.</p>

--inner-001--

--outer-001
Content-Type: application/pdf; name="report.pdf"
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64

[phan-du-lieu-base64-cua-PDF]

--outer-001--
~~~

Dòng **[phan-du-lieu-base64-cua-PDF]** trong ví dụ là ký hiệu minh họa, không phải dữ liệu PDF hợp lệ. Khi ứng dụng thực sự gửi thư, Jakarta Mail sinh và mã hóa byte của file. Mỗi cấp multipart có **boundary riêng**, và client phải đóng đúng boundary của từng cấp.

### 5.1. Khi còn có ảnh nội tuyến

Nếu bản HTML chứa ảnh logo nhúng và email đồng thời có PDF đính kèm, cấu trúc có thể là:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html (tham chiếu cid:logo)
│   └── image/png
│       ├── Content-ID: <logo>
│       └── Content-Disposition: inline
└── application/pdf
    └── Content-Disposition: attachment
~~~

Ở mức ứng dụng, sự khác biệt giữa **ảnh inline** và **PDF attachment** nằm ở quan hệ hiển thị:

- Ảnh inline là tài nguyên liên quan đến HTML; HTML tham chiếu qua **cid:**.
- PDF attachment là tệp độc lập mà người nhận có thể xem/tải riêng.
- Một part không phải mặc định “attachment” chỉ vì nội dung của nó là nhị phân. Cách client hiển thị còn phụ thuộc Content-Type, Content-Disposition, vị trí MIME part và tính tương thích của client.

Không cần tự ghép cây MIME bằng chuỗi khi dùng các API phù hợp của Spring Mail.

## 6. Spring Framework Mail: từ MimeMessage đến MimeMessageHelper

Trong Spring Framework, **JavaMailSender** cung cấp khả năng tạo và gửi thông điệp MIME bằng Jakarta Mail; **MimeMessageHelper** hỗ trợ thiết lập header, nội dung multipart, attachment và inline resource dễ hơn.

Các thành phần cần biết:

| Thành phần | Vai trò |
| --- | --- |
| **JavaMailSender** | Tạo MimeMessage và gửi thông điệp |
| **MimeMessage** | Đại diện email hỗ trợ MIME, header và các phần nội dung |
| **MimeMessageHelper** | Hỗ trợ setTo, setSubject, setText, addAttachment, addInline… |
| **Multipart** / **MimeMultipart** | Đại diện cấu trúc nhiều MIME part ở tầng Jakarta Mail |
| **Resource** / **InputStreamSource** | Nguồn byte cho tệp đính kèm hoặc tài nguyên inline |
| **FileSystemResource** | Resource đọc tệp từ hệ thống file |

Khi làm việc trong ứng dụng Spring Boot, có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Cấu hình SMTP ví dụ trong **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Cấu hình tài khoản gửi và mật khẩu nên được cung cấp qua biến môi trường **SPRING_MAIL_USERNAME**, **SPRING_MAIL_PASSWORD** hoặc kho bí mật tương ứng. Những địa chỉ và domain trong bài chỉ là ví dụ. Cổng SMTP, phương thức TLS và authentication phải phù hợp với máy chủ thực tế.

## 7. Ví dụ gửi nội dung plain text cùng PDF đính kèm

Dưới đây là một dịch vụ Spring nhận đường dẫn báo cáo đã được tạo và gửi nó kèm lời nhắn.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportEmailService {

    private final JavaMailSender mailSender;

    public ReportEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(String recipient, Path reportFile)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("reports@example.org");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo tháng 11");
        helper.setText(
                "Xin chào,\n"
                + "Vui lòng xem báo cáo PDF đính kèm.",
                false
        );

        helper.addAttachment(
                "report.pdf",
                new FileSystemResource(reportFile)
        );

        mailSender.send(message);
    }
}
~~~

Giải thích từng bước:

1. **createMimeMessage()** tạo thông điệp MIME bằng Jakarta Mail.
2. **MULTIPART_MODE_MIXED** yêu cầu helper xây dựng cấu trúc hỗ trợ **multipart/mixed** ở cấp gốc.
3. **setFrom**, **setTo**, **setSubject** khai báo header và người nhận mà thư viện dùng khi gửi.
4. **setText(..., false)** tạo phần nội dung plain text; đối số **false** cho biết đây không phải HTML.
5. **addAttachment("report.pdf", resource)** thêm một MIME part cho file với tên hiển thị **report.pdf**.
6. **mailSender.send(message)** chuyển thông điệp đã được dựng tới mail transport.

Đường dẫn **reportFile** phải trỏ tới tệp thực sự tồn tại và ứng dụng có quyền đọc. Nếu tệp không tồn tại, mất quyền truy cập hoặc bị thay đổi trong lúc gửi, quá trình tạo/truy xuất dữ liệu attachment có thể lỗi. Một hệ thống thực tế nên kiểm soát nguồn gốc, quyền truy cập và vòng đời của tệp trước khi gọi dịch vụ gửi.

Kết quả MIME về mặt ý tưởng:

~~~text
multipart/mixed
├── text/plain
│   └── Xin chào, vui lòng xem báo cáo PDF đính kèm.
└── application/pdf
    ├── Content-Disposition: attachment
    ├── filename="report.pdf"
    └── byte PDF được mã hóa để vận chuyển
~~~

Tên Content-Type thực tế của attachment phụ thuộc nguồn dữ liệu, tên file và cách nhận diện media type. Nếu cần kiểm soát chính xác, có thể dùng overload **addAttachment** cho phép truyền media type.

### 7.1. Tại sao không dùng SimpleMailMessage?

**SimpleMailMessage** dành cho thư văn bản đơn giản với các trường như sender, recipient, subject và text. Nó không phải API để thêm MIME part/tệp đính kèm.

Với tài liệu đính kèm, hãy sử dụng **MimeMessage** và **MimeMessageHelper**. Việc gắn tệp vào nội dung chuỗi của SimpleMailMessage không tự sinh **multipart/mixed**, không có Content-Disposition và không khiến client nhận diện được attachment.

### 7.2. Thêm nhiều tệp vào cùng một email

Có thể gọi **addAttachment** nhiều lần trước khi gửi:

~~~java
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath)
);

helper.addAttachment(
        "transactions.csv",
        new FileSystemResource(csvPath)
);
~~~

Kết quả là một thông điệp mang nhiều attachment part. Thứ tự hiển thị của file ở client có thể khác thứ tự thêm trong mã; không nên đặt yêu cầu nghiệp vụ phụ thuộc tuyệt đối vào vị trí hiển thị của attachment.

### 7.3. Cần gửi MIME attachment với kiểu dữ liệu cụ thể

Ví dụ dùng một nguồn byte ở bộ nhớ mà ứng dụng đã tạo:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] csvBytes = "id,amount\n1,100\n".getBytes(
        java.nio.charset.StandardCharsets.UTF_8
);

helper.addAttachment(
        "transactions.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Trong ví dụ, dữ liệu đủ nhỏ để minh họa **ByteArrayResource**. Với file lớn, có thể cân nhắc **FileSystemResource** hoặc một nguồn streaming phù hợp để giảm việc giữ nhiều bản sao dữ liệu trong RAM.

Khi dùng overload nhận **InputStreamSource**, nguồn dữ liệu phải có khả năng cung cấp luồng đọc phù hợp với cách Jakarta Mail truy cập attachment. Một **InputStreamResource** bọc luồng chỉ đọc được một lần không phải lúc nào cũng phù hợp, vì việc dựng/gửi MIME có thể yêu cầu lấy luồng nhiều lần. **ByteArrayResource** và **FileSystemResource** là những lựa chọn quen thuộc cho dữ liệu lặp lại có thể đọc được.

## 8. Plain text + HTML + attachment trong một message

Ứng dụng thường muốn gửi bản HTML đẹp nhưng vẫn có bản plain text làm phương án thay thế. Khi đó, **setText(String plainText, String htmlText)** của MimeMessageHelper giúp tạo các biểu diễn phù hợp.

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setFrom("reports@example.org");
helper.setTo("thao@example.net");
helper.setSubject("Báo cáo tháng 11");

helper.setText(
        "Báo cáo tháng 11 đã sẵn sàng. Xem PDF đính kèm.",
        "<html><body>"
        + "<p><strong>Báo cáo tháng 11</strong> đã sẵn sàng.</p>"
        + "<p>Xem PDF đính kèm.</p>"
        + "</body></html>"
);

helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath)
);

mailSender.send(message);
~~~

Về logic, phần lời nhắn có hai biểu diễn **text/plain** và **text/html**; attachment vẫn là một phần riêng. Cấu trúc MIME có thể được lồng nhau để giữ đúng quan hệ đó. Client nhận thư chọn bản nội dung phù hợp rồi cung cấp tệp đính kèm để người dùng mở hoặc tải.

Không nên coi **setText(plain, html)** là hai thông điệp khác nhau; đó là **hai cách biểu diễn cùng nội dung** trong một email.

### 8.1. Chọn multipart mode nào trong MimeMessageHelper?

Spring Mail có một số chế độ multipart, đáng chú ý:

| Chế độ | Ý nghĩa và tình huống |
| --- | --- |
| **MULTIPART_MODE_NO** | Không tạo cấu trúc multipart; không phù hợp khi cần addAttachment |
| **MULTIPART_MODE_MIXED** | Tạo root **multipart/mixed**; phù hợp cho nội dung và attachment độc lập |
| **MULTIPART_MODE_RELATED** | Dùng cấu trúc **multipart/related** ở root; nhấn mạnh nội dung và tài nguyên có quan hệ |
| **MULTIPART_MODE_MIXED_RELATED** | Root **multipart/mixed** chứa nhánh **multipart/related** cho nội dung/inline, attachment được đặt phù hợp ở cấp mixed |

Một điểm đặc biệt của API: nếu dùng constructor phổ biến:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8"
);
~~~

thì trong Spring Framework, giá trị **true** kích hoạt multipart bằng chế độ mặc định **MULTIPART_MODE_MIXED_RELATED**. Vì vậy, **true** không bảo đảm rằng mọi part đều được đặt trực tiếp bên dưới một root multipart/mixed đơn giản.

Khi mục tiêu là minh họa rõ cấu trúc **mixed** thuần cho lời nhắn và attachment, có thể chọn **MULTIPART_MODE_MIXED** tường minh. Khi có HTML cùng ảnh inline hoặc cần cấu trúc phổ biến tương thích nhiều client hơn, **MULTIPART_MODE_MIXED_RELATED** thường là lựa chọn thích hợp.

Không nên suy đoán toàn bộ cây MIME chỉ từ số lần gọi **addAttachment**. Cấu trúc thực tế còn phụ thuộc chế độ multipart, cách gọi **setText**, việc thêm inline resource và triển khai cụ thể của thư viện.

## 9. Phân biệt attachment với ảnh inline

Hai lời gọi phổ biến trên **MimeMessageHelper**:

~~~java
helper.addAttachment(
        "company-profile.pdf",
        new FileSystemResource(profilePath)
);

helper.addInline(
        "companyLogo",
        new FileSystemResource(logoPath),
        "image/png"
);
~~~

Tác dụng:

- **addAttachment** thêm nội dung dưới dạng tài liệu đính kèm độc lập, thường có **Content-Disposition: attachment**.
- **addInline** thêm tài nguyên phục vụ nội dung HTML, được tham chiếu bằng **Content-ID** tương ứng.

HTML có thể chứa:

~~~html
<p>Chào mừng bạn!</p>
<img src="cid:companyLogo" alt="Logo công ty">
~~~

Chuỗi **companyLogo** trong **cid:** phải khớp với định danh đã sử dụng trong **addInline**. Nhiều email client chặn hoặc giới hạn việc hiển thị ảnh, nên cần cung cấp văn bản thay thế khi có thể.

Trong những thư có cả HTML, ảnh inline và PDF, có thể dùng:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setText(htmlBody, true);
helper.addInline("companyLogo", logoResource, "image/png");
helper.addAttachment("report.pdf", reportResource);
~~~

Theo hướng dẫn của Spring Mail, khi sử dụng inline resource, nên gọi **setText** trước **addInline** để các email client có thể xử lý tham chiếu inline đúng hơn.

Không nên gửi một hình ảnh với **addAttachment** rồi kỳ vọng thẻ **cid:** trong HTML tự liên kết được với part đó. Một attachment bình thường không nhất thiết mang Content-ID và quan hệ **multipart/related** cần thiết.

## 10. Tên tệp, Content-Type và Content-Disposition

Một MIME part dùng cho attachment có thể có:

~~~text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64
~~~

Các header đóng vai trò khác nhau:

**Content-Type** giúp bên nhận hiểu dạng dữ liệu, ví dụ PDF, CSV, ZIP hoặc generic binary **application/octet-stream**.

**Content-Disposition: attachment** gợi ý hiển thị phần đó như một tài liệu riêng để tải về.

**filename** là tên tệp gợi ý, không phải đường dẫn tuyệt đối trên máy người nhận và không nên được tin dùng như một đường dẫn an toàn.

### 10.1. Đuôi tệp và media type không phải một thứ

Nếu gọi:

~~~java
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath)
);
~~~

thư viện có thể suy ra media type từ tên tệp hoặc cơ chế phát hiện nội dung được cấu hình. Nhưng **đuôi .pdf không bảo đảm byte thực tế là PDF**. Trong hệ thống xử lý file từ người dùng, phải xác minh nội dung và chính sách file ở lớp nghiệp vụ.

Tương tự, đặt Content-Type **application/pdf** không biến một chuỗi văn bản thành PDF; đây chỉ là metadata mô tả loại dữ liệu mà bên gửi khai báo.

### 10.2. Tên tệp có ký tự tiếng Việt

Filename có thể chứa ký tự ngoài ASCII, ví dụ **báo-cáo-tháng-11.pdf**. MIME có quy tắc riêng để biểu diễn header chứa ký tự quốc tế, tùy chuẩn và mức hỗ trợ của client. Khi dùng Jakarta Mail/Spring Mail, hãy ưu tiên API đặt tên file và cấu hình charset đúng; tránh tự nối trực tiếp header không được mã hóa.

Để tương thích với nhiều hệ thống nhận thư, tên tệp ASCII ngắn, có nghĩa như **bao-cao-thang-11.pdf** thường đơn giản hơn. Nếu yêu cầu giữ Unicode, cần thử nghiệm trên các email client mục tiêu.

### 10.3. Filename là dữ liệu không đáng tin cậy

Khi ứng dụng **nhận** email có attachment, không được ghép thẳng filename vào đường dẫn ghi file. Tên do bên gửi khai báo có thể chứa ký tự đặc biệt, đường dẫn tương đối hoặc ký tự gây nhầm lẫn. Cần chuẩn hóa tên, chọn thư mục do ứng dụng quản lý và áp dụng chính sách cho phép loại file.

Khi ứng dụng **gửi** attachment, cũng nên đặt tên rõ ràng để tránh tiết lộ đường dẫn nội bộ như đường dẫn thư mục tạm, tên khách hàng không được phép công khai hoặc tên file từ nguồn chưa qua kiểm soát.

## 11. Những lỗi thường gặp khi dựng multipart/mixed

### 11.1. Dùng setText thay vì addAttachment cho tệp

Sai ý tưởng:

~~~java
message.setText("Đây là file PDF: " + pdfAsBase64);
~~~

Đoạn này chỉ chèn chuỗi base64 vào phần thân text; không tạo MIME part có **Content-Type** và **Content-Disposition** phù hợp. Client sẽ không tự biết cần hiển thị như một tệp có tên.

Cách đúng là tạo **MimeMessageHelper** ở chế độ multipart và gọi **addAttachment** với nguồn byte của file.

### 11.2. Tự nối boundary rồi gửi dưới dạng text/plain

Nếu ứng dụng tạo một chuỗi chứa các dòng **--boundary** và gọi **SimpleMailMessage.setText**, nội dung chỉ là văn bản thông thường. Client sẽ không nhận được header **multipart/mixed** và cấu trúc MIME đúng.

Một thông điệp MIME không chỉ có các dấu phân cách; nó cần header tổng, header part, encoding, CRLF và boundary khớp nhau. Để tránh sai định dạng, dùng các API MIME chuyên dụng.

### 11.3. Quên chế độ multipart

Nếu helper được tạo ở chế độ không multipart rồi gọi **addAttachment**, sẽ không có cấu trúc cần thiết để chứa attachment. Hãy chọn constructor hỗ trợ multipart, ví dụ truyền **MULTIPART_MODE_MIXED** hoặc **true** khi phù hợp.

### 11.4. Đọc một InputStream rồi dùng lại luồng đã cạn

Một attachment có thể cần được Jakarta Mail truy cập trong lúc tuần tự hóa thông điệp. Nếu nguồn dữ liệu chỉ cho đọc một lần, lần đọc tiếp theo có thể bị lỗi hoặc trả dữ liệu rỗng.

Giải pháp là dùng nguồn có thể mở lại như **FileSystemResource**, hoặc lưu byte vào **ByteArrayResource** khi dung lượng đủ nhỏ. Không giữ một InputStream đã sử dụng trong nhiều bước mà không có chiến lược quản lý.

### 11.5. Gửi file quá lớn

Một email không chỉ tính kích thước file gốc: base64, header và cấu trúc MIME làm tăng kích thước truyền. SMTP server có thể từ chối message quá lớn, mail provider có quota riêng, và phía người nhận có thể có giới hạn khác.

Nếu tệp rất lớn, một phương án khác là lưu trên dịch vụ file được kiểm soát quyền truy cập và gửi một liên kết tải phù hợp; phương án này thay đổi mô hình bảo mật và vòng đời file, nên cần thiết kế chủ động.

### 11.6. Gắn attachment nhưng lại mô tả là inline

Một số email client có thể tự hiển thị hình ảnh hoặc preview PDF dù header dùng **attachment**. Không nên dựa vào cách một client hiển thị để suy ra cấu trúc MIME. Hãy xét **Content-Disposition**, quan hệ multipart và **Content-ID**, đồng thời thử nghiệm trên client mục tiêu.

### 11.7. Gửi thành công không đồng nghĩa người nhận thấy attachment

Ngay cả khi SMTP server chấp nhận message, bên nhận vẫn có thể:

- Chặn tệp thuộc loại rủi ro hoặc vượt giới hạn.
- Cách ly thư theo chính sách chống malware.
- Loại bỏ hoặc thay đổi cách xử lý attachment.
- Đưa thư vào spam, trì hoãn hoặc trả về lỗi chuyển phát.

Vì vậy, câu hỏi “thư đã được SMTP chấp nhận chưa?” và “người nhận có mở được attachment không?” cần được theo dõi bằng những tín hiệu khác nhau.

## 12. Cách đọc cấu trúc khi gặp một email thật

Khi thấy một email có lời nhắn và ba tệp đính kèm, hãy đọc từ ngoài vào trong:

~~~text
Message headers
    |
    +-- MIME-Version: 1.0
    +-- Content-Type: multipart/mixed; boundary="outer"
            |
            +-- Part #1: text/plain
            |       lời nhắn
            |
            +-- Part #2: application/pdf
            |       Content-Disposition: attachment
            |       filename="invoice.pdf"
            |       Content-Transfer-Encoding: base64
            |
            +-- Part #3: text/csv
            |       Content-Disposition: attachment
            |       filename="items.csv"
            |
            +-- Part #4: application/zip
                    Content-Disposition: attachment
                    filename="backup.zip"
~~~

Nếu part đầu tiên là **multipart/alternative** thay vì text/plain, tiếp tục phân tích các part con. Nếu có **multipart/related**, tìm các Content-ID và quan hệ với HTML. Cấu trúc MIME có thể có nhiều tầng; một thuật toán xử lý email không nên giả định “body luôn ở part 0 và tất cả part còn lại đều là attachment” cho mọi email trên thế giới.

Trong chính ứng dụng gửi thư bằng Spring, một cách kiểm tra kỹ thuật khi gặp lỗi là quan sát thông điệp đã dựng trong môi trường phát triển:

- Message root có đúng **Content-Type: multipart/mixed** hoặc kiểu multipart mong muốn?
- Body part có đúng **text/plain** hay **text/html**?
- Attachment có **Content-Disposition: attachment**, filename và media type phù hợp?
- Body có còn giữ UTF-8 và ký tự tiếng Việt?
- Dữ liệu nguồn có thể mở và đọc đầy đủ tại thời điểm mail transport sử dụng?
- Nội dung có nằm trong hạn mức kích thước của dịch vụ SMTP?

Các câu hỏi này giúp định hướng chẩn đoán. Việc kiểm tra nội dung thật, gửi thử và đánh giá chất lượng mã sẽ được thực hiện trong giai đoạn kiểm thử riêng của hệ thống, thay vì dựa vào mô tả cấu trúc.

## 13. Minh họa một nghiệp vụ: gửi báo cáo có PDF và CSV

Giả sử ứng dụng có chức năng “gửi báo cáo bán hàng” sau khi tổng hợp dữ liệu. Người nhận cần:

1. Đọc phần lời nhắn ngắn trong email.
2. Mở bản PDF để xem báo cáo được định dạng.
3. Tải CSV để nhập dữ liệu vào hệ thống khác.

Cấu trúc message mong muốn là:

~~~text
From: reports@example.org
To: manager@example.net
Subject: Báo cáo bán hàng tháng 11

multipart/mixed
├── text/plain:
│     "Báo cáo đã được tạo; vui lòng xem các tệp đính kèm."
├── application/pdf:
│     report-november.pdf
└── text/csv:
      report-november.csv
~~~

Đoạn Java minh họa tập trung vào cách khai báo MIME part:

~~~java
public void sendMonthlyReport(
        String recipient,
        Path pdfPath,
        Path csvPath
) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED,
            "UTF-8"
    );

    helper.setFrom("reports@example.org");
    helper.setTo(recipient);
    helper.setSubject("Báo cáo bán hàng tháng 11");

    helper.setText(
            "Báo cáo đã được tạo.\n"
            + "Vui lòng xem tệp PDF và CSV đính kèm.",
            false
    );

    helper.addAttachment(
            "report-november.pdf",
            new FileSystemResource(pdfPath)
    );
    helper.addAttachment(
            "report-november.csv",
            new FileSystemResource(csvPath),
            "text/csv; charset=UTF-8"
    );

    mailSender.send(message);
}
~~~

Ví dụ giả định **mailSender** đã được tiêm vào service; **pdfPath** và **csvPath** đã được xác minh, tạo xong và sẵn sàng đọc. Việc ghi file báo cáo, kiểm tra phân quyền người nhận và quản lý lỗi ở hạ tầng gửi là những trách nhiệm của ứng dụng bao quanh hàm này.

Điểm cần nhận ra: **ba thành phần nội dung được đóng gói thành một MimeMessage**. Phần lời nhắn không cần gửi riêng; hai file không cần gọi **mailSender.send** riêng; thư viện tự tạo cấu trúc multipart và truyền thông điệp qua SMTP theo cấu hình gửi.

## 14. Những câu hỏi giúp củng cố kiến thức

**“Tại sao multipart/mixed cần boundary?”**

Vì toàn bộ MIME message là một luồng dữ liệu có thể chứa nhiều part với header/body riêng. Boundary giúp bên nhận xác định nơi part này kết thúc và part tiếp theo bắt đầu. Thư viện MIME thường tự tạo và xử lý boundary.

**“Mọi part trong multipart/mixed có phải attachment không?”**

Không. Part đầu tiên thường là nội dung chính để hiển thị; các part khác có thể là attachment. Một part cũng có thể là một multipart lồng nhau. Việc nhận diện cần dựa trên cấu trúc, header và ngữ cảnh.

**“Tôi muốn vừa có HTML vừa có PDF thì mixed đã đủ chưa?”**

Có thể dùng root **multipart/mixed** để chứa nội dung HTML và PDF, nhưng nếu muốn có cả plain text lẫn HTML biểu diễn cùng một lời nhắn, nên dùng **multipart/alternative** lồng bên trong mixed. Nếu còn có ảnh inline, có thể bổ sung **multipart/related**.

**“Lời nhắn và PDF có phải là hai email không?”**

Không. Chúng là hai MIME part trong cùng một email. Chúng có thể được vận chuyển bên trong cùng một dữ liệu SMTP DATA.

**“Gọi addAttachment có làm SMTP gửi thêm một message?”**

Không. **addAttachment** thay đổi cấu trúc của MimeMessage, còn **send** thực hiện bước gửi. Số SMTP transaction và recipient phụ thuộc quá trình gửi, không bằng số MIME part.

**“Bên nhận có thể tải file PDF khi part dùng base64 không?”**

Có. Client MIME giải mã Content-Transfer-Encoding để khôi phục byte file, rồi dùng Content-Type/Content-Disposition/filename để quyết định cách hiển thị. Tuy nhiên, việc mở hoặc tải được còn phụ thuộc chính sách của client và hệ thống email nhận.

**“Có thể mã hóa attachment bằng base64 thủ công rồi đặt vào setText không?”**

Không nên. Đó vẫn là nội dung text nếu không tạo MIME part và header đúng. Dùng **addAttachment** để thư viện làm việc với byte file và transfer encoding.

**“Có nhất thiết tự thiết lập Content-Type của PDF không?”**

Không phải lúc nào cũng cần, vì thư viện có thể nhận diện từ tên file hoặc cấu hình media type. Khi cần độ chắc chắn hoặc dữ liệu có đuôi không phổ biến, dùng overload **addAttachment** với content type tường minh.

## 15. Ghi nhớ bản chất multipart/mixed

**multipart/mixed** là cách MIME đóng gói **nội dung email và các tệp đính kèm thành những phần có cấu trúc trong cùng một thông điệp**. Header Content-Type ở cấp gốc khai báo loại multipart và boundary; mỗi part có header và body riêng; các attachment thường dùng **Content-Disposition: attachment** và **Content-Transfer-Encoding: base64**.

Trong Spring Framework Mail, bộ đôi **JavaMailSender** và **MimeMessageHelper** giúp tạo cấu trúc này thông qua các thao tác như **setText** và **addAttachment**. Khi chỉ có lời nhắn và file, **MULTIPART_MODE_MIXED** thể hiện rõ cấu trúc mong muốn. Khi có nhiều phiên bản nội dung hoặc tài nguyên nhúng, các cấu trúc **multipart/alternative** và **multipart/related** có thể lồng bên trong mixed.

Nắm chắc ranh giới này giúp bạn hiểu vì sao một email có thể chứa nhiều file nhưng vẫn là **một message**, biết cách đọc raw MIME khi có lỗi đính kèm, và chọn đúng API khi xây dựng tính năng gửi tài liệu bằng Spring Mail.
