# Tên tệp Unicode và xử lý encoding

Trong một module gửi email bằng **Spring Framework Mail**, tệp đính kèm có thể mang tên chứa tiếng Việt hoặc ký tự Unicode, ví dụ:

~~~text
Báo cáo tháng 11.pdf
Hóa đơn Nguyễn An – 2026.xlsx
契約書_注文123.pdf
Résumé – édition finale.docx
~~~

Tên tệp này được hiển thị trong danh sách attachment của email client. Dù bytes của file có thể hoàn toàn đúng, người nhận vẫn có thể thấy tên bị lỗi như `BÃ¡o cÃ¡o.pdf`, dấu hỏi hoặc một chuỗi mã hóa khó hiểu nếu metadata MIME được biểu diễn/giải mã không phù hợp.

Điểm cần phân biệt là **encoding của tên tệp** và **encoding của nội dung tệp** là hai việc riêng. Với PDF, nội dung thường là bytes nhị phân được đóng gói bằng transfer encoding phù hợp; tên Unicode lại nằm trong tham số của header MIME như `Content-Disposition: attachment; filename=...`. Với CSV hoặc TXT, ngoài tên tệp còn phải xác định charset của chính các bytes văn bản.

Spring Mail và Jakarta Mail giúp xây dựng các header MIME cần thiết. Khi sử dụng `MimeMessageHelper`, ứng dụng nên truyền **tên tệp gốc ở dạng Java String** và để thư viện xử lý header theo khả năng tương thích của phiên bản đang dùng; không tự Base64 hoặc URL-encode tên tệp trước khi gọi API gửi mail.

## 1. Tên tệp nằm ở đâu trong một email MIME?

Một attachment là một MIME part nằm trong phần body của thông điệp. Header của part thường mô tả:

- **`Content-Type`:** loại dữ liệu, ví dụ `application/pdf`, `image/png` hoặc `text/csv`.
- **`Content-Transfer-Encoding`:** cách bytes được biểu diễn để truyền, thường là `base64` đối với dữ liệu nhị phân.
- **`Content-Disposition`:** gợi ý nội dung là attachment hay inline, đồng thời có thể chứa tên tệp qua tham số `filename`.
- **`Content-ID`:** định danh phần MIME nếu nội dung được tham chiếu trong HTML, thường dùng với ảnh inline.

Ví dụ rút gọn:

~~~text
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQK...
~~~

Tên `invoice.pdf` nằm trong **header của MIME part**, còn nội dung PDF nằm trong body đã được mã hóa transfer encoding. Đây là hai vùng dữ liệu khác nhau.

Một số thông điệp cũ hoặc hệ thống tương thích có thể còn thấy tham số `name` trong `Content-Type`:

~~~text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
~~~

`name` là cách biểu diễn lịch sử thường gặp; `filename` trong `Content-Disposition` là nơi thường được dùng để chỉ tên tệp tải về. Không nên chỉ dựa vào một header để đoán cách mọi email client hiển thị attachment.

### 1.1. Vì sao tên tệp Unicode khó hơn tên ASCII?

Với tên chỉ chứa ASCII:

~~~text
filename="invoice-2026.pdf"
~~~

Các ký tự như chữ Latin không dấu, chữ số, dấu gạch ngang và dấu chấm có thể biểu diễn trực tiếp trong cú pháp header MIME thông thường. Nhưng tên:

~~~text
filename="Báo cáo tháng 11.pdf"
~~~

có ký tự ngoài ASCII. Các thế hệ email và thư viện mail cũ không thống nhất cách biểu diễn những ký tự này trong tham số header. Vì thế, các chuẩn MIME có cơ chế mở rộng để mang charset và bytes của giá trị Unicode.

## 2. Phân biệt charset, transfer encoding và filename encoding

Ba khái niệm này thường bị gọi chung là “encoding”, nhưng chúng giải quyết các vấn đề khác nhau:

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Charset** | Chuỗi văn bản được chuyển thành bytes theo bảng mã nào? | UTF-8 |
| **Content-Transfer-Encoding** | Bytes của MIME part được biểu diễn thế nào để truyền? | base64, quoted-printable, 7bit |
| **Filename parameter encoding** | Tên tệp Unicode được biểu diễn trong MIME header ra sao? | RFC 2231 extended parameter |

Ví dụ một file CSV:

- **Tên file:** `Báo cáo tháng 11.csv`, cần được biểu diễn đúng trong tham số filename.
- **Bytes nội dung:** chuỗi CSV được chuyển sang bytes bằng UTF-8.
- **Transfer encoding:** bytes CSV có thể được gửi dưới dạng base64 trong MIME part.
- **Content-Type:** `text/csv; charset=UTF-8` mô tả nội dung là CSV và charset của phần text.

Nếu chỉ sửa filename encoding mà bytes CSV được tạo bằng một charset khác, người nhận vẫn có thể mở file và thấy tiếng Việt bị lỗi. Ngược lại, nội dung CSV UTF-8 hoàn toàn đúng nhưng header filename sai vẫn có thể khiến tên tệp bị hỏng.

## 3. RFC 2231: cách chuẩn để biểu diễn tham số Unicode

**RFC 2231** mở rộng cú pháp tham số MIME để biểu diễn giá trị có charset và ngôn ngữ. Với tên tệp Unicode, dạng thường gặp là tham số **extended parameter** có dấu sao:

~~~text
filename*=UTF-8''B%C3%A1o%20c%C3%A1o%20th%C3%A1ng%2011.pdf
~~~

Cấu trúc:

~~~text
filename*=charset'language'percent-encoded-octets
~~~

- `filename*`: dấu `*` cho biết đây là extended parameter.
- `UTF-8`: charset được dùng để giải mã bytes.
- Phần giữa hai dấu nháy đơn là language tag; có thể để trống.
- Phần sau là các octet của tên tệp đã được percent-encode.

Khi giải mã UTF-8, ví dụ trên trở lại tên:

~~~text
Báo cáo tháng 11.pdf
~~~

Trong ví dụ, ký tự `á` được biểu diễn bằng bytes UTF-8 rồi thành `%C3%A1`; dấu cách thành `%20`. Đây là cơ chế mã hóa **tham số MIME**, không phải yêu cầu ứng dụng tự chuyển tên file thành một URL.

### 3.1. Fallback cho email client cũ

Một thông điệp có thể chứa cả tên ASCII dự phòng và giá trị mở rộng:

~~~text
Content-Disposition: attachment;
 filename="report-2026.pdf";
 filename*=UTF-8''B%C3%A1o%20c%C3%A1o%202026.pdf
~~~

Email client hỗ trợ RFC 2231 có thể dùng `filename*` để lấy tên Unicode. Client cũ có thể bỏ qua tham số mở rộng và dùng `filename` ASCII dự phòng. Cách kết hợp này giúp tương thích rộng hơn, nhưng **không bảo đảm mọi client hiển thị giống nhau**.

Nếu tên ASCII dự phòng khác tên Unicode, người dùng ở client cũ sẽ nhìn thấy tên dự phòng. Vì vậy, chọn fallback ngắn, dễ nhận biết và có phần mở rộng đúng, ví dụ `bao-cao-2026.pdf`.

### 3.2. Tên dài và tham số tiếp nối

Header email có giới hạn về độ dài dòng. RFC 2231 cho phép chia một giá trị dài thành các đoạn tham số:

~~~text
filename*0*=UTF-8''Bao%20cao%20thang%2011%20-
filename*1*=%20khach%20hang%20Nguyen%20An.pdf
~~~

Ví dụ chỉ minh họa ý tưởng chia đoạn; khi tạo MIME thực tế, thư viện có thể chọn cách gấp dòng và chia tham số khác. Không nên tự cắt chuỗi Unicode thành từng đoạn ký tự rồi ghép header, vì có thể cắt giữa các bytes UTF-8 hoặc phá cú pháp continuation.

**Để Jakarta Mail xử lý việc mã hóa và gấp header** thay vì tự tạo `filename*0*`, `filename*1*` bằng chuỗi thủ công.

## 4. RFC 2047 encoded-word khác RFC 2231

Một dạng khác mà bạn có thể thấy trong header là:

~~~text
=?UTF-8?B?QsOhbyBjw6FvLnBkZg==?=
~~~

Đây là cú pháp **encoded-word** theo RFC 2047. Nó được thiết kế cho các trường header chứa từ/ngữ văn bản không phải ASCII, chẳng hạn `Subject` hoặc tên hiển thị người gửi.

Đối với tham số MIME như `filename`, cơ chế chuẩn dành cho tham số mở rộng là **RFC 2231**. Một số phần mềm cũ lại dùng RFC 2047 encoded-word bên trong giá trị filename như một cách tương thích riêng. Vì vậy:

- Không mặc định rằng encoded-word trong filename là dạng chuẩn phù hợp với mọi client.
- Không dùng `MimeUtility.encodeText(...)` để encode tên file rồi giả định nó tương đương RFC 2231.
- Không tự nhét chuỗi `=?UTF-8?B?...?=` vào tên filename nếu chưa xác định rõ yêu cầu tương thích của client đích.
- Hãy để Jakarta Mail/Spring Mail tạo parameter theo implementation và cấu hình được hỗ trợ.

### 4.1. `MimeUtility.encodeText` dùng cho trường hợp nào?

Ví dụ:

~~~java
import jakarta.mail.internet.MimeUtility;

String encodedSubject =
        MimeUtility.encodeText("Báo cáo tháng 11", "UTF-8", null);
~~~

`MimeUtility.encodeText` hữu ích khi cần mã hóa một **header text** theo quy tắc MIME encoded-word, ví dụ Subject hoặc tên hiển thị. Khi dùng `MimeMessageHelper.setSubject(...)` hoặc overload tên hiển thị, thư viện có thể tự xử lý header phù hợp; thông thường không cần tự gọi `encodeText` trước.

Tên tệp là tham số MIME có quy tắc riêng. Đừng dùng kết quả `encodeText` làm đầu vào cho `addAttachment(...)`; API attachment cần **tên hiển thị ban đầu**, không phải chuỗi đã mã hóa.

## 5. Đặt tên tệp Unicode bằng MimeMessageHelper

Với Spring Mail, cách thường dùng là `MimeMessageHelper.addAttachment(...)`:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendReport(
        JavaMailSender sender,
        byte[] pdfBytes,
        String recipient) throws MessagingException {

    MimeMessage mime = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, StandardCharsets.UTF_8.name());

    helper.setFrom("reports@example.com");
    helper.setTo(recipient);
    helper.setSubject("Báo cáo tháng 11");
    helper.setText("Báo cáo được đính kèm trong email này.");

    String fileName = "Báo cáo tháng 11 – Nguyễn An.pdf";
    helper.addAttachment(
            fileName,
            new ByteArrayResource(pdfBytes),
            "application/pdf"
    );

    sender.send(mime);
}
~~~

Điểm cần chú ý:

1. `fileName` là tên Unicode gốc dưới dạng `String`.
2. `ByteArrayResource` cung cấp bytes của file PDF; nó không chịu trách nhiệm mã hóa tên file.
3. `application/pdf` là content type của attachment.
4. `MimeMessageHelper` tạo MIME part và đặt tên attachment.
5. `JavaMailSender` gửi toàn bộ `MimeMessage` qua transport đã cấu hình.

**Không** làm như sau:

~~~java
// Không tự Base64/URL-encode tên file trước khi truyền vào helper.
String fileName = Base64.getEncoder()
        .encodeToString("Báo cáo tháng 11.pdf".getBytes(StandardCharsets.UTF_8));

helper.addAttachment(fileName, new ByteArrayResource(pdfBytes));
~~~

Nếu tự mã hóa tên tệp, người nhận có thể nhìn thấy chuỗi Base64 thay vì tên mong muốn; nếu thư viện tiếp tục mã hóa, kết quả có thể bị mã hóa hai lần.

### 5.1. Thiết lập encode filename của Spring

Một số phiên bản Spring Framework cung cấp tùy chọn `MimeMessageHelper.setEncodeFilenames(boolean)` để hỗ trợ mã hóa tên file cho các email client có yêu cầu tương thích. Khi API này có trong phiên bản dự án:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(mime, true, StandardCharsets.UTF_8.name());

helper.setEncodeFilenames(true);
helper.addAttachment(
        "Báo cáo tháng 11.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Hãy xem tài liệu API đúng phiên bản Spring đang dùng trước khi áp dụng. Tùy phiên bản và Jakarta Mail provider, tùy chọn này có thể sử dụng cơ chế MIME encoded-word để cải thiện tương thích với một số client cũ; **không nên mặc định đồng nhất nó với RFC 2231 extended parameter**. Kiểm tra raw MIME và client thực tế nếu cần quyết định bật/tắt.

Nếu phiên bản Spring không cung cấp method này, đừng tự sửa raw header ngay trong service. Trước tiên hãy kiểm tra khả năng RFC 2231 của Jakarta Mail provider và các thuộc tính mail MIME được hỗ trợ.

### 5.2. Dùng FileSystemResource hoặc ClassPathResource

Khi attachment đã tồn tại dưới dạng file:

~~~java
import org.springframework.core.io.FileSystemResource;

FileSystemResource resource =
        new FileSystemResource("/srv/reports/report.pdf");

helper.addAttachment(
        "Báo cáo tháng 11.pdf",
        resource,
        "application/pdf"
);
~~~

Tên hiển thị có thể khác tên file vật lý trên server. Ví dụ, đường dẫn nội bộ là `/srv/reports/report-2026-11.pdf` nhưng tên người nhận thấy là `Báo cáo tháng 11.pdf`. Tách hai giá trị giúp tránh để lộ cấu trúc thư mục hoặc tên lưu trữ nội bộ.

Với resource trong classpath:

~~~java
import org.springframework.core.io.ClassPathResource;

helper.addAttachment(
        "Hướng dẫn sử dụng.pdf",
        new ClassPathResource("mail/guide.pdf"),
        "application/pdf"
);
~~~

Resource phải tồn tại trong artifact đang chạy. Không nên dựa vào đường dẫn làm việc tương đối của process, vì thư mục hiện tại có thể khác giữa local, container và production.

### 5.3. InputStreamSource phải có thể mở stream phù hợp

`MimeMessageHelper` có overload nhận `InputStreamSource`. Khi gửi, thư viện có thể cần đọc resource trong quá trình dựng nội dung MIME; vì vậy nguồn nên có khả năng cung cấp stream mới khi được yêu cầu.

Các lựa chọn thường tiện:

- `ByteArrayResource` cho bytes đã có trong bộ nhớ và kích thước phù hợp.
- `FileSystemResource` cho file có sẵn trên filesystem.
- `ClassPathResource` cho file đóng gói trong classpath.

Thận trọng với `InputStreamResource` hoặc một nguồn chỉ đọc được **một lần**. Nếu stream đã bị tiêu thụ trước khi mail transport đọc, attachment có thể rỗng hoặc lỗi. Đối với file lớn, tránh nạp toàn bộ vào byte array nếu kích thước có thể gây áp lực bộ nhớ; chọn resource/stream có vòng đời rõ ràng.

## 6. Điều khiển thuộc tính MIME ở mức Jakarta Mail

Khi cần làm việc ở mức thấp hơn, ứng dụng có thể tạo `MimeBodyPart` và đặt tên tệp qua API Jakarta Mail. Ví dụ khái quát:

~~~java
import jakarta.mail.Part;
import jakarta.mail.internet.MimeBodyPart;

MimeBodyPart attachment = new MimeBodyPart();
attachment.setDataHandler(dataHandlerForPdf);
attachment.setDisposition(Part.ATTACHMENT);
attachment.setFileName("Báo cáo tháng 11.pdf");
multipart.addBodyPart(attachment);
~~~

`setFileName(...)` nhận tên tệp ở dạng chuỗi; việc tạo header MIME cụ thể được thực hiện bởi Jakarta Mail/provider và cấu hình tương ứng. Không nên tự ghép:

~~~java
attachment.setHeader(
        "Content-Disposition",
        "attachment; filename=\"" + userProvidedName + "\""
);
~~~

Nối chuỗi header như vậy có nguy cơ sai cú pháp, lỗi encoding, gấp dòng không hợp lệ và header injection nếu tên đến từ input không tin cậy. API cấp cao đã có cơ chế xử lý parameter/header; chỉ thao tác thủ công khi có yêu cầu giao thức cụ thể và hiểu rõ tác động tương thích.

### 6.1. Các thuộc tính MIME liên quan tới filename

Jakarta Mail implementation có thể hỗ trợ các thuộc tính cấu hình cho tham số và tên file. Một số thuộc tính thường được nhắc tới:

| Property | Mục đích khái quát | Lưu ý |
| --- | --- | --- |
| `mail.mime.encodeparameters` | Điều khiển việc mã hóa tham số MIME mở rộng theo RFC 2231 ở implementation hỗ trợ | Kiểm tra default và tài liệu provider |
| `mail.mime.decodeparameters` | Điều khiển giải mã tham số MIME mở rộng | Hữu ích khi đọc message; không phải mọi ứng dụng chỉ gửi đều cần cấu hình |
| `mail.mime.encodefilename` | Cơ chế tương thích dùng encoded-word cho tên file trong một số implementation | Không đồng nghĩa với RFC 2231 |
| `mail.mime.decodefilename` | Giải mã tên file dùng cơ chế encoded-word tương thích | Chỉ bật khi có nhu cầu và hiểu ảnh hưởng |

Tên property, default và phạm vi cấu hình có thể phụ thuộc phiên bản Jakarta Mail/provider. Trước khi thay đổi, hãy kiểm tra tài liệu implementation thực tế trong dependency graph. Không đặt hàng loạt property chỉ vì thấy ví dụ trên Internet; một lựa chọn tương thích cũ có thể làm thay đổi cách mọi attachment được gửi/đọc trong ứng dụng.

Nếu cần cấu hình property qua Spring Boot, chúng thường được truyền vào mail session/provider qua nhóm `spring.mail.properties`, ví dụ:

~~~yaml
spring:
  mail:
    properties:
      "[mail.mime.encodeparameters]": true
~~~

Đây chỉ là ví dụ cho implementation hỗ trợ property đó. **Không bật/tắt toàn cục mà chưa thử với provider và email client đích**. Cấu hình MIME toàn cục có thể ảnh hưởng tất cả các thông điệp được gửi trong cùng session.

## 7. Encoding của nội dung attachment

Tên tệp Unicode có thể đúng nhưng nội dung vẫn bị lỗi nếu bytes được tạo sai charset.

### 7.1. Attachment PDF, ảnh hoặc ZIP

PDF, PNG, JPEG, ZIP và các file nhị phân khác nên được truyền dưới dạng **bytes gốc**. Không chuyển bytes thành `String` bằng UTF-8 và không gọi `getBytes()` trên dữ liệu nhị phân:

~~~java
byte[] pdfBytes = Files.readAllBytes(pdfPath);
helper.addAttachment(
        "Hóa đơn tháng 11.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Trong quá trình dựng MIME, thư viện sẽ chọn transfer encoding thích hợp (thường là base64 cho attachment nhị phân). Không cần tự Base64 bytes PDF trước khi đưa vào `ByteArrayResource`.

### 7.2. Attachment TXT/CSV có tiếng Việt

Với dữ liệu text, phải chuyển chuỗi sang bytes theo charset đã chọn:

~~~java
String csvText = """
    Mã đơn,Tên khách hàng,Tổng tiền
    A123,Nguyễn An,220000
    """;

byte[] csvBytes = csvText.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "Báo cáo khách hàng.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Ở đây có hai việc:

- Tên `Báo cáo khách hàng.csv` cần được biểu diễn đúng trong MIME filename parameter.
- Nội dung CSV được encode thành **UTF-8 bytes**, và `Content-Type` khai báo charset phù hợp.

Không dùng `fileName.getBytes(UTF_8)` để thay thế tên tệp; filename là header parameter, không phải body text. Cũng không giả định `Content-Transfer-Encoding: base64` sẽ tự làm cho nội dung CSV thành UTF-8: Base64 chỉ biểu diễn bytes, không quyết định charset của các bytes ấy.

### 7.3. Excel, Word và các định dạng Office

Đối với `.xlsx`, `.docx` và các định dạng Office hiện đại, dữ liệu thường là gói nhị phân ZIP/XML. Hãy dùng bytes do thư viện tạo file cung cấp, đồng thời khai báo MIME type phù hợp:

| Loại file | Content-Type thường dùng |
| --- | --- |
| PDF | `application/pdf` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| ZIP | `application/zip` |
| CSV | `text/csv; charset=UTF-8` khi nội dung là UTF-8 |
| TXT UTF-8 | `text/plain; charset=UTF-8` |
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| DOCX | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |

Content-Type nên được xác định từ loại dữ liệu thực tế hoặc danh sách định dạng được ứng dụng cho phép, không tin tuyệt đối phần mở rộng do người dùng nhập. Khai báo MIME type đúng giúp email client đề xuất cách mở file, nhưng **không xác thực nội dung file là an toàn hay đúng định dạng**.

## 8. Chuẩn hóa và làm sạch tên tệp Unicode

Một tên file được truyền từ người dùng hoặc hệ thống ngoài có thể chứa:

- dấu gạch chéo và chuỗi giống đường dẫn;
- ký tự điều khiển hoặc xuống dòng;
- khoảng trắng đầu/cuối;
- dấu chấm liên tiếp hoặc tên rỗng;
- ký tự Unicode ở dạng tổ hợp khác nhau;
- phần mở rộng không khớp nội dung thật;
- chuỗi quá dài gây khó hiển thị hoặc vượt giới hạn provider.

Trước khi dùng tên làm **tên hiển thị trong email**, ứng dụng nên áp dụng chính sách:

1. Lấy **basename** nếu input có thể là path; không để đường dẫn thư mục máy chủ xuất hiện trong email.
2. Loại bỏ ký tự điều khiển, CR/LF, NUL và những ký tự không được phép theo quy tắc sản phẩm.
3. Giới hạn độ dài theo code point hoặc quy tắc hiển thị, không cắt giữa một surrogate pair.
4. Giữ nguyên ký tự ngôn ngữ cần thiết; có thể chuẩn hóa Unicode về NFC để có biểu diễn nhất quán.
5. Chọn phần mở rộng từ loại file đã được xác định, không chỉ tin tên do client gửi.
6. Nếu tên sau xử lý rỗng hoặc không hợp lệ, tạo tên dự phòng có ID an toàn.

### 8.1. Ví dụ chuẩn hóa Unicode

Unicode có thể biểu diễn một chữ có dấu bằng một code point dựng sẵn hoặc bằng chữ cái cộng dấu kết hợp. Hai chuỗi có thể nhìn giống nhau nhưng có bytes khác nhau.

Java hỗ trợ chuẩn hóa qua `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        originalFileName,
        Normalizer.Form.NFC
);
~~~

NFC giúp tạo dạng chuẩn hóa hợp thành khi có thể. Nó **không** tự loại bỏ path traversal, ký tự điều khiển, tên rỗng hoặc chuỗi quá dài; vẫn cần bước validate/sanitize theo quy tắc ứng dụng.

### 8.2. Không dùng tên file làm đường dẫn lưu trữ

Giả sử người dùng tải lên:

~~~text
../../private/customer-data.pdf
~~~

Tên này không nên được ghép trực tiếp vào một đường dẫn filesystem. Khi lưu file, server nên tạo tên/key nội bộ an toàn (ví dụ UUID hoặc object key riêng), còn tên gốc chỉ được lưu như metadata đã làm sạch để hiển thị cho người nhận.

Khi gửi email:

~~~java
String displayName = "Hồ sơ khách hàng.pdf";
helper.addAttachment(
        displayName,
        new FileSystemResource(trustedStoredFile),
        "application/pdf"
);
~~~

`trustedStoredFile` phải là resource đã được hệ thống xác định và kiểm soát. Tên hiển thị không được dùng để chọn file tùy ý trên server.

### 8.3. Chống header injection

Không cho phép tên file chứa CR/LF hoặc ký tự điều khiển để tạo thêm header:

~~~text
report.pdf"\r\nBcc: victim@example.net
~~~

Thư viện mail có thể kiểm tra một số trường hợp, nhưng ứng dụng vẫn phải xác thực input. Hãy dùng setter của `MimeMessageHelper`/Jakarta Mail thay vì tự ghép `Content-Disposition`. Không cho người dùng truyền raw MIME header hoặc raw filename parameter.

## 9. Ví dụ đầy đủ: gửi PDF có tên tiếng Việt

Một service có thể nhận bytes PDF đã được tạo và gửi cho một người nhận:

~~~java
package com.example.mail.application;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceAttachmentMailService {
    private final JavaMailSender sender;

    public InvoiceAttachmentMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(
            String recipient,
            byte[] pdfBytes,
            String invoiceNumber) throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, StandardCharsets.UTF_8.name());

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn " + invoiceNumber);
        helper.setText(
                "Xin chào,\n\nHóa đơn của bạn được đính kèm trong email này.\n"
        );

        String attachmentName =
                "Hóa đơn " + invoiceNumber + " – Nguyễn An.pdf";
        helper.addAttachment(
                attachmentName,
                new ByteArrayResource(pdfBytes),
                "application/pdf"
        );

        sender.send(mime);
    }
}
~~~

Ví dụ giả định `pdfBytes` đã được tạo từ dữ liệu hợp lệ, `recipient` đã được kiểm tra theo nghiệp vụ và `invoiceNumber` không chứa dữ liệu điều khiển. Nếu tên file được lấy từ input người dùng, cần chạy qua bước chuẩn hóa/validate trước khi truyền vào helper.

### 9.1. Ví dụ CSV UTF-8

~~~java
String csv = """
        Mã đơn,Tên khách hàng,Tổng tiền
        A123,Nguyễn An,220000
        A124,Trần Bình,1250000
        """;

byte[] csvBytes = csv.getBytes(StandardCharsets.UTF_8);
String csvName = "Báo cáo khách hàng tháng 11.csv";

helper.addAttachment(
        csvName,
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Nếu người dùng mở CSV bằng một phần mềm bảng tính cũ, cách phần mềm đó đoán charset có thể khác nhau. UTF-8 là lựa chọn phổ biến; nếu cần hỗ trợ một ứng dụng cụ thể, kiểm tra yêu cầu BOM hoặc định dạng import của ứng dụng đó, nhưng không tự thêm BOM cho mọi loại file.

## 10. Nhiều attachment với nhiều tên Unicode

`MimeMessageHelper` cho phép gọi `addAttachment` nhiều lần:

~~~java
helper.addAttachment(
        "Hóa đơn A123.pdf",
        new ByteArrayResource(invoicePdf),
        "application/pdf"
);

helper.addAttachment(
        "Chi tiết đơn hàng – Nguyễn An.xlsx",
        new ByteArrayResource(orderWorkbook),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
);

helper.addAttachment(
        "Điều khoản dịch vụ.pdf",
        new ClassPathResource("mail/terms.pdf"),
        "application/pdf"
);
~~~

Mỗi part có filename, Content-Type và dữ liệu riêng. Tên Unicode của một attachment không làm thay đổi charset của attachment khác. Nếu email có nhiều file:

- giới hạn số lượng và tổng kích thước;
- xác định rõ thứ tự/ý nghĩa từng file;
- tránh trùng tên khiến người nhận khó phân biệt;
- không thêm một file nội bộ hoặc file tạm ngoài dự kiến;
- kiểm tra từng nguồn dữ liệu còn khả dụng khi gửi/retry.

## 11. Kiểm tra raw MIME để xác định lỗi encoding

Khi email client hiển thị tên tệp sai, không nên đoán ngay rằng file bytes bị lỗi. Hãy xem **raw source/original message** hoặc lưu thông điệp thành `.eml` trong môi trường thử nghiệm.

Ví dụ một part có thể trông như:

~~~text
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment;
 filename="report-2026.pdf";
 filename*=UTF-8''B%C3%A1o%20c%C3%A1o%202026.pdf

JVBERi0xLjQK...
~~~

Các bước kiểm tra:

1. **Tìm đúng MIME part** của attachment, không chỉ xem header message ngoài cùng.
2. **Đọc `Content-Disposition`:** có `filename`, `filename*` hay continuation không?
3. **Giải mã parameter theo chuẩn:** nếu có `filename*`, đọc charset và percent-encoded bytes theo RFC 2231.
4. **Kiểm tra Content-Type và transfer encoding:** xác định nội dung file được mô tả thế nào.
5. **Giải mã bytes attachment và đối chiếu file gốc:** với PDF có thể kiểm tra signature và checksum; với CSV kiểm tra UTF-8.
6. **Thử email client mục tiêu:** các client có thể chọn fallback hoặc xử lý parameter khác nhau.

### 11.1. Phân loại triệu chứng

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Nội dung PDF mở bình thường nhưng tên sai | Filename parameter encoding hoặc cách client giải mã |
| Tên file đúng nhưng CSV lỗi dấu | Charset bytes của CSV và khai báo `charset` |
| Tên hiện thành chuỗi `=?UTF-8?B?...?=` | Client không giải mã encoded-word ở filename hoặc cách encode không phù hợp |
| Tên hiện thành `BÃ¡o cÃ¡o.pdf` | UTF-8 bytes bị diễn giải bằng charset khác hoặc filename bị encode sai |
| Tên bị cắt ở dấu cách/ký tự đặc biệt | Quoting, parameter folding hoặc MIME header không hợp lệ |
| Một client hiển thị đúng, client khác sai | Khác biệt hỗ trợ RFC 2231/2047 và fallback |
| Attachment có kích thước 0 | InputStreamSource một lần, stream bị tiêu thụ, file không tồn tại hoặc nguồn dữ liệu lỗi |
| PDF/Office file không mở được | Bytes bị thay đổi, encode Base64 thủ công hai lần hoặc Content-Type không đúng |

### 11.2. Đừng chỉ xem log của Java

Log cho biết service đã gọi `addAttachment(...)` với tên nào, nhưng không chứng minh header cuối cùng được encode ra sao. Để chẩn đoán, cần xem **MIME đã serialize** sau khi thư viện tạo message. Có thể lưu bản test vào `.eml` trong môi trường local, nhưng phải bảo vệ vì file này có thể chứa địa chỉ, nội dung và attachment thật.

## 12. Kiểm thử tên tệp Unicode

Một test hữu ích cần kiểm tra cả **giá trị đầu vào** và **header được tạo ra**.

### 12.1. Kiểm tra helper được gọi với tên gốc

Unit test có thể mock hoặc capture logic tạo attachment để xác nhận service truyền tên Unicode ban đầu, không phải Base64 hoặc URL-encoded string. Đây là kiểm tra ở tầng ứng dụng.

### 12.2. Integration test với SMTP giả lập

Có thể dùng Mailpit hoặc GreenMail để:

1. Chạy SMTP test server không gửi ra ngoài.
2. Gửi email có tên `Báo cáo tháng 11 – Nguyễn An.pdf`.
3. Lấy raw MIME hoặc tải `.eml` từ test server.
4. Kiểm tra `Content-Disposition` có tham số filename theo chuẩn/provider đã chọn.
5. Giải mã tên theo cơ chế tương ứng và so sánh với tên mong muốn.
6. Lấy bytes attachment và so checksum với file gốc.
7. Thử xem trong những email client mà sản phẩm cần hỗ trợ.

Không nên viết test cứng rằng mọi implementation phải phát ra chính xác một chuỗi header byte-for-byte. Header có thể được gấp dòng, sắp xếp tham số hoặc encode theo cách hợp lệ khác. Nên kiểm tra **ngữ nghĩa sau khi parse/decode**, cùng với một số kiểm tra raw header khi cần tương thích.

### 12.3. Bộ tên mẫu nên thử

| Nhóm | Ví dụ | Điều cần quan sát |
| --- | --- | --- |
| ASCII | `invoice-2026.pdf` | Trường hợp cơ bản |
| Tiếng Việt có dấu | `Báo cáo tháng 11.pdf` | UTF-8 và RFC 2231 |
| Dấu cách và dấu gạch dài | `Hóa đơn – Nguyễn An.pdf` | Parameter quoting/encoding |
| Ký tự CJK | `契約書_注文123.pdf` | Unicode ngoài Latin |
| Ký tự tổ hợp | Tên có dấu ở dạng decomposed | Chuẩn hóa NFC và hiển thị |
| Tên dài | Tên báo cáo có nhiều từ | Folding/continuation |
| Ký tự đặc biệt | Dấu nháy, dấu chấm phẩy | Quoting và sanitize |
| Tên rỗng/độc hại | `../../secret.pdf`, CR/LF | Validation và basename |

## 13. Kích thước, giới hạn và khả năng tương thích

Encoding filename không làm thay đổi đáng kể bytes của file, nhưng header dài hơn có thể cần folding hoặc continuation. Bên cạnh đó, **Base64 làm attachment lớn lên** khoảng một phần ba so với bytes ban đầu, chưa tính header và multipart boundary.

Ví dụ file PDF 9 MB sau Base64 có thể lớn hơn 12 MB. Provider có thể giới hạn kích thước toàn email, không chỉ riêng file. Vì vậy:

- kiểm tra tổng kích thước trước khi gửi;
- tránh đọc nhiều file lớn vào heap cùng lúc;
- chọn resource có khả năng mở stream phù hợp;
- nếu file quá lớn, cân nhắc gửi link tải xuống có xác thực và thời hạn thay vì attachment;
- không đặt thông tin bí mật trong URL tải xuống hoặc tên file.

Khả năng tương thích cũng cần được cân nhắc:

- **Client mới** thường hỗ trợ extended parameter theo RFC 2231.
- **Client cũ** có thể hiểu encoded-word hoặc chỉ tên ASCII fallback.
- **Provider/gateway** có thể viết lại, lọc hoặc chuẩn hóa header.
- **Hệ thống quản lý file của người nhận** có thể áp dụng quy tắc tên riêng, ví dụ thay ký tự không hợp lệ.

Không có một tùy chọn encoding duy nhất bảo đảm mọi hệ thống hiển thị tên Unicode giống hệt nhau. Chọn cách biểu diễn theo chuẩn, cung cấp fallback ASCII khi cần và kiểm thử với client thực tế.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tự Base64 tên tệp trước `addAttachment` | Người nhận thấy chuỗi mã thay vì tên | Truyền tên Unicode gốc |
| Dùng `URLEncoder` cho filename | Dấu cách thành `+`, cú pháp không đúng mục đích MIME | Để Jakarta Mail xử lý RFC 2231 |
| Dùng `MimeUtility.encodeText` cho filename rồi truyền vào helper | Có thể tạo encoded-word không phù hợp hoặc mã hóa hai lần | Phân biệt RFC 2047 với RFC 2231 |
| Nghĩ helper charset UTF-8 tự sửa bytes PDF | Trộn encoding metadata với dữ liệu nhị phân | Giữ bytes file nguyên gốc; charset chỉ áp dụng cho nội dung text |
| Đổi filename nhưng không đặt charset cho CSV | Tên đúng nhưng nội dung CSV lỗi dấu | Tạo bytes UTF-8 và khai báo `text/csv; charset |
| Tự ghép `Content-Disposition` từ input | Sai cú pháp hoặc header injection | Dùng `addAttachment` / `setFileName` |
| Chỉ thử trên một email client | Có thể bỏ sót lỗi tương thích | Test client quan trọng và raw MIME |
| Giữ `InputStream` chỉ đọc được một lần | Attachment có thể rỗng hoặc lỗi | Dùng resource có thể mở stream phù hợp |
| Dùng tên upload làm path trên server | Path traversal hoặc lộ cấu trúc nội bộ | Lưu bằng key an toàn, tên hiển thị tách riêng |
| Tin phần mở rộng do người dùng gửi | MIME type và file thực tế không khớp | Kiểm tra loại file, giới hạn định dạng và nội dung |
| Coi Base64 là mã hóa bảo mật | Bytes có thể giải mã công khai | Dùng cơ chế bảo vệ dữ liệu phù hợp; Base64 chỉ là transfer encoding |

## 15. Checklist thiết kế trong module Spring Mail

Khi thêm một attachment có tên Unicode, hãy xác định:

1. **Tên hiển thị:** tên gốc hay tên do ứng dụng sinh? Có được chuẩn hóa và giới hạn độ dài không?
2. **Nguồn file:** bytes, filesystem, classpath hay object storage? Resource có còn tồn tại khi worker gửi không?
3. **Loại nội dung:** MIME type được xác định từ nội dung đáng tin cậy hay chỉ từ extension?
4. **Nội dung text:** nếu là CSV/TXT, charset bytes là gì và `Content-Type` có khai báo đúng không?
5. **Filename encoding:** Spring/Jakarta Mail version hỗ trợ RFC 2231 ra sao? Có cần fallback cho client cũ không?
6. **Bảo mật:** tên có CR/LF, path separator hoặc dữ liệu nhạy cảm không? File đã được kiểm tra/scan theo chính sách chưa?
7. **Kích thước:** tổng email có vượt giới hạn provider hoặc gây áp lực bộ nhớ không?
8. **Kiểm thử:** raw MIME, tên sau decode, bytes attachment và client đích đã được kiểm tra chưa?

## 16. Tình huống tổng hợp: gửi báo cáo tiếng Việt qua Spring Mail

Một ứng dụng tạo báo cáo tháng cho khách hàng Nguyễn An. File PDF được lưu nội bộ dưới tên:

~~~text
report-2026-11-8842.pdf
~~~

Tên muốn người nhận thấy:

~~~text
Báo cáo tháng 11 – Nguyễn An.pdf
~~~

Luồng phù hợp:

1. **Report service** tạo PDF và lưu bytes hoặc resource ở vị trí được kiểm soát.
2. **Application service** xác định tên hiển thị, chuẩn hóa Unicode, kiểm tra ký tự điều khiển và phần mở rộng.
3. **Mail service** tạo `MimeMessage` và `MimeMessageHelper` với UTF-8.
4. Gọi `addAttachment(displayName, resource, "application/pdf")`, không encode tên thủ công.
5. **Jakarta Mail/provider** xây header MIME và transfer encoding cho dữ liệu.
6. **SMTP provider** nhận thông điệp; email client người nhận parse filename parameter.
7. Nếu tên hiển thị sai, kiểm tra raw `Content-Disposition` và cơ chế RFC 2231/compatibility trước khi thay đổi cấu hình.

Mô hình này tách rõ:

~~~text
Storage key:     report-2026-11-8842.pdf
Display name:    Báo cáo tháng 11 – Nguyễn An.pdf
Content-Type:    application/pdf
Content bytes:   original PDF bytes
Transfer coding: chosen by MIME implementation
Filename coding: MIME parameter encoding handled by mail library
~~~

Tên hiển thị không quyết định file nào được đọc; file lưu trữ không cần mang tên Unicode; content bytes không bị biến đổi để “sửa tên”; và mã gửi mail không phải tự viết raw header. Khi phân tách được những trách nhiệm này, email đính kèm tên Unicode sẽ dễ kiểm soát và tương thích hơn.

### Tài liệu tham khảo

- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** cấu trúc MIME, content type và transfer encoding.
- **RFC 2231 — MIME Parameter Value and Encoded Word Extensions:** extended parameter, charset, language và continuation.
- **RFC 2047 — MIME Message Header Extensions:** encoded-word trong các trường header văn bản.
- **Spring Framework API — `MimeMessageHelper`:** `addAttachment`, `setEncodeFilenames` (nếu có trong phiên bản đang dùng) và cách tạo MIME message.
- **Jakarta Mail API — `MimeBodyPart` / `MimeUtility`:** đặt filename, xử lý header và các cơ chế encoding.
- **Spring Boot Reference — Sending Email:** cấu hình `JavaMailSender` và `spring.mail.*`.
