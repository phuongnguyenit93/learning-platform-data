# Đính kèm từ ByteArrayResource

Trong Spring Framework Mail, bạn có thể gửi một tệp đính kèm mà không cần tạo file tạm trên đĩa. Nếu ứng dụng đã có nội dung file dưới dạng **byte[]**, hãy bọc mảng byte đó trong **ByteArrayResource** rồi truyền cho **MimeMessageHelper.addAttachment(...)**.

Cách này phù hợp với dữ liệu được tạo ngay trong bộ nhớ hoặc lấy từ nguồn đã trả về byte, chẳng hạn PDF hóa đơn vừa sinh, CSV báo cáo, ảnh được xử lý, tài liệu đọc từ database hoặc nội dung tải từ object storage. Ứng dụng có thể đưa dữ liệu trực tiếp vào một MIME part của email mà không cần ghi thành file vật lý trước.

Ví dụ cốt lõi:

~~~java
byte[] pdfBytes = pdfGenerator.generate(invoice);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Trong đó:

- **pdfBytes** là byte gốc của file PDF.
- **ByteArrayResource** cung cấp dữ liệu dưới dạng Spring Resource để thư viện mail đọc.
- **invoice.pdf** là tên hiển thị của tệp đính kèm.
- **application/pdf** là MIME type mô tả dữ liệu.
- **addAttachment(...)** thêm một MIME part độc lập vào thông điệp.

Điểm cần nhớ là **truyền byte gốc cho ByteArrayResource, không tự chuyển byte sang Base64 trước khi gọi addAttachment**. Jakarta Mail xử lý việc mã hóa nội dung MIME phù hợp khi tuần tự hóa email.

## 1. ByteArrayResource là gì?

**ByteArrayResource** là một implementation của Spring **Resource**, dùng để biểu diễn dữ liệu đã có sẵn trong một mảng byte. Nó đặc biệt hữu ích khi nguồn dữ liệu không phải file trên filesystem mà là nội dung đang nằm trong bộ nhớ.

~~~java
byte[] content = "Hello from memory".getBytes(StandardCharsets.UTF_8);

ByteArrayResource resource = new ByteArrayResource(content);
~~~

Resource này cho phép các API Spring nhận **InputStreamSource** truy cập dữ liệu. Khi cần đọc, nó cung cấp một InputStream dựa trên byte array đã lưu.

Có thể hình dung:

~~~text
byte[]
  |
  v
ByteArrayResource
  |
  | getInputStream()
  v
InputStream
  |
  v
MimeMessageHelper.addAttachment(...)
  |
  v
MIME attachment part
  |
  v
JavaMailSender.send(...)
~~~

### 1.1. Vì sao không truyền byte[] trực tiếp vào addAttachment?

API của **MimeMessageHelper** nhận một nguồn dữ liệu tương thích với **InputStreamSource** ở các overload thông dụng. byte[] tự nó không triển khai giao diện này.

Do đó, ta cần một adapter:

~~~java
ByteArrayResource resource = new ByteArrayResource(fileBytes);
helper.addAttachment("document.pdf", resource);
~~~

ByteArrayResource đóng vai trò cầu nối giữa mảng byte trong ứng dụng và API nhận một nguồn InputStream.

### 1.2. ByteArrayResource không phải file tạm

Khi dùng:

~~~java
new ByteArrayResource(pdfBytes)
~~~

ứng dụng không tự tạo một file trên đĩa. Dữ liệu vẫn nằm trong bộ nhớ của process Java.

Điều này giúp tránh tạo file tạm, chọn thư mục tạm, quản lý quyền đọc/ghi và xóa file sau khi gửi. Đổi lại, ứng dụng phải tính đến bộ nhớ heap, kích thước byte array và thời điểm dữ liệu được giải phóng.

### 1.3. So sánh các loại Resource

| Resource | Đại diện cho | Trường hợp phù hợp |
| --- | --- | --- |
| **ByteArrayResource** | Dữ liệu có sẵn trong byte[] | PDF/CSV/ảnh được tạo hoặc tải vào bộ nhớ |
| **ClassPathResource** | Tài nguyên trên classpath | Logo, mẫu tài liệu, file tĩnh đóng gói cùng ứng dụng |
| **FileSystemResource** | File trên filesystem | File báo cáo đã được tạo và lưu trên đĩa |
| **InputStreamResource** | Một InputStream có sẵn | Nguồn stream đặc thù, cần chú ý vòng đời |
| **UrlResource** | Tài nguyên qua URL | Trường hợp truy cập URL được kiểm soát |

Không có Resource nào tốt nhất trong mọi tình huống. Hãy chọn theo nguồn dữ liệu và cách thư viện cần đọc nó.

## 2. addAttachment và các overload của MimeMessageHelper

**MimeMessageHelper** cung cấp các overload để thêm file đính kèm. Hai dạng thường dùng:

~~~java
helper.addAttachment(
        "invoice.pdf",
        inputStreamSource
);
~~~

và:

~~~java
helper.addAttachment(
        "invoice.pdf",
        inputStreamSource,
        "application/pdf"
);
~~~

Tham số:

1. **attachmentFilename**: tên file được đề xuất cho người nhận khi tải hoặc lưu attachment.
2. **inputStreamSource**: nguồn byte có thể cung cấp InputStream.
3. **contentType**: MIME type của nội dung, ví dụ application/pdf hoặc text/csv; charset=UTF-8.

Với ByteArrayResource:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Khi biết rõ loại file, truyền contentType tường minh giúp message mô tả dữ liệu rõ ràng. Nếu dùng overload không có contentType, Spring/Jakarta Mail có thể dựa vào cơ chế nhận diện hoặc giá trị mặc định; hành vi cụ thể còn phụ thuộc cách resource và file type map được cấu hình.

### 2.1. Attachment là một MIME part

Một email có attachment thường dùng cấu trúc multipart, ví dụ:

~~~text
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed-001"

--mixed-001
Content-Type: text/plain; charset=UTF-8

Vui lòng xem hóa đơn đính kèm.

--mixed-001
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

[du-lieu-PDF-duoc-ma-hoa]

--mixed-001--
~~~

Phần **[du-lieu-PDF-duoc-ma-hoa]** là ký hiệu minh họa, không phải dữ liệu PDF thật.

Attachment được mô tả bằng các header của MIME part:

- **Content-Type** cho biết loại dữ liệu.
- **Content-Disposition: attachment** gợi ý client trình bày phần này như một tệp đính kèm.
- **filename** cung cấp tên hiển thị.
- **Content-Transfer-Encoding** mô tả cách byte được biểu diễn trong message, thường là base64 với dữ liệu nhị phân.

Ứng dụng Spring không cần tự nối boundary hoặc tạo header trên bằng chuỗi. Hãy để MimeMessageHelper và Jakarta Mail xây dựng MIME part.

### 2.2. Cần bật multipart

Một email đơn giản có thể được tạo bằng **SimpleMailMessage**, nhưng kiểu này không hỗ trợ attachment. Muốn đính kèm file, cần tạo **MimeMessage** và **MimeMessageHelper** ở chế độ multipart.

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);
~~~

**MULTIPART_MODE_MIXED** phù hợp với nội dung thư và các attachment độc lập. Nếu email còn có HTML và ảnh inline, có thể dùng **MULTIPART_MODE_MIXED_RELATED** để thể hiện nhánh related cùng attachment.

Constructor tiện dụng:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

Trong Spring Framework, true bật multipart theo chế độ mặc định **MULTIPART_MODE_MIXED_RELATED**. Khi chỉ cần attachment thông thường, chọn **MULTIPART_MODE_MIXED** tường minh giúp ý định rõ hơn.

## 3. Ví dụ cơ bản: gửi email với PDF từ byte[]

Giả sử ứng dụng đã tạo một hóa đơn PDF trong bộ nhớ và nhận được byte[] từ một service:

~~~java
byte[] pdfBytes = pdfGenerator.generate(invoice);
~~~

Service gửi email:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {

        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalArgumentException(
                    "Nội dung PDF không được để trống"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");
        helper.setText(
                "Xin chào,\n"
                + "Vui lòng xem hóa đơn PDF đính kèm.",
                false
        );

        ByteArrayResource pdfResource =
                new ByteArrayResource(pdfBytes);

        helper.addAttachment(
                "invoice.pdf",
                pdfResource,
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Đoạn code giả định mailSender đã được Spring cấu hình và pdfBytes là dữ liệu PDF hợp lệ được tạo từ một nguồn mà ứng dụng tin cậy. Trong hệ thống thật, recipient cần được xác thực theo nghiệp vụ và kích thước file cần có giới hạn.

### 3.1. Luồng thực hiện

1. Kiểm tra dữ liệu byte không null và không rỗng.
2. Tạo MimeMessage.
3. Khởi tạo MimeMessageHelper với multipart mode.
4. Đặt From, To, Subject và phần thân email.
5. Bọc byte[] trong ByteArrayResource.
6. Gọi addAttachment với tên file và MIME type.
7. Gọi mailSender.send(message) để gửi toàn bộ email.

Một lời gọi send gửi thông điệp chứa cả body lẫn attachment. Không cần gọi send riêng cho file.

### 3.2. Tại sao vẫn cần tên file nếu resource chỉ là byte[]?

Mảng byte không chứa thông tin tên file. Nó chỉ là dữ liệu.

Tên hiển thị được cung cấp riêng:

~~~java
helper.addAttachment(
        "invoice-2026-001.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Tên đó được đưa vào metadata MIME để email client có thể hiển thị và đề xuất tên khi người nhận lưu file. Nó không phải đường dẫn file trên máy gửi và không có nghĩa ứng dụng đã tạo một file vật lý với tên ấy.

## 4. Tạo byte[] từ nội dung được sinh trong bộ nhớ

ByteArrayResource hữu ích khi nguồn dữ liệu được tạo trong chính ứng dụng. Ví dụ, một báo cáo PDF được sinh bởi một thành phần tạo tài liệu.

~~~java
public interface InvoicePdfGenerator {
    byte[] generate(Invoice invoice);
}
~~~

Một thư viện tạo tài liệu có thể ghi nội dung ra **OutputStream**. Ta dùng **ByteArrayOutputStream** để thu nội dung trong bộ nhớ:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;

public byte[] generatePdf(Invoice invoice) throws IOException {
    try (ByteArrayOutputStream output =
                 new ByteArrayOutputStream()) {

        pdfDocumentWriter.write(invoice, output);

        return output.toByteArray();
    }
}
~~~

**pdfDocumentWriter.write(...)** đại diện cho API của thư viện PDF mà dự án sử dụng. Nó ghi byte PDF vào output stream. **toByteArray()** trả về một mảng byte chứa nội dung đã ghi.

Luồng:

~~~text
Invoice
   |
   v
PDF generator
   |
   v
ByteArrayOutputStream
   |
   | toByteArray()
   v
byte[]
   |
   v
ByteArrayResource
   |
   v
MimeMessageHelper.addAttachment()
~~~

Không cần ghi file PDF vào đĩa nếu ứng dụng chỉ cần gửi nó ngay sau khi tạo và kích thước phù hợp với bộ nhớ.

### 4.1. Chi phí bộ nhớ khi dùng ByteArrayOutputStream

**toByteArray()** tạo một mảng byte kết quả. Trong quá trình tạo, buffer nội bộ của ByteArrayOutputStream và mảng được trả về có thể cùng tồn tại trong một khoảng thời gian. Sau đó ByteArrayResource giữ tham chiếu tới byte array, còn quá trình tạo MIME có thể cần thêm buffer hoặc biểu diễn dữ liệu.

Vì thế, một file lớn có thể tiêu tốn nhiều heap hơn kích thước file cuối cùng. Đừng chỉ nhìn vào dung lượng file để ước tính bộ nhớ tối đa.

Với báo cáo nhỏ hoặc vừa, cách làm này đơn giản. Với file lớn, nên cân nhắc tạo file trong storage hoặc dùng một nguồn streaming phù hợp thay vì giữ nhiều bản sao trong heap.

## 5. ByteArrayResource và InputStreamSource: vì sao tính đọc lại quan trọng?

**InputStreamSource** là abstraction được Spring sử dụng để cung cấp InputStream. Các API mail có thể cần truy cập dữ liệu khi tạo hoặc tuần tự hóa MIME message.

Một nguồn dữ liệu phù hợp cần có khả năng cung cấp luồng mới khi được yêu cầu theo hợp đồng của API. **ByteArrayResource** là lựa chọn thuận tiện vì nó dựa trên byte array đã có và có thể tạo một ByteArrayInputStream mới để đọc lại cùng dữ liệu.

~~~java
ByteArrayResource resource =
        new ByteArrayResource(pdfBytes);

InputStream first = resource.getInputStream();
InputStream second = resource.getInputStream();
~~~

Hai lời gọi tạo các luồng đọc từ cùng dữ liệu gốc. Việc đọc hết luồng thứ nhất không làm con trỏ đọc của luồng thứ hai bị tiêu thụ theo.

### 5.1. So sánh với InputStreamResource

**InputStreamResource** thường đại diện cho một InputStream đã được cung cấp. Nguồn này thường được xem là chỉ đọc một lần; sau khi stream đã bị tiêu thụ hoặc đóng, không thể mặc nhiên mở lại cùng dữ liệu.

| Đặc điểm | ByteArrayResource | InputStreamResource |
| --- | --- | --- |
| Nguồn dữ liệu | byte[] trong bộ nhớ | Một InputStream đã có |
| Có thể mở lại | Có thể tạo stream mới từ byte array | Thường không thể đọc lại cùng stream |
| Chi phí bộ nhớ | Giữ toàn bộ byte array | Có thể không cần giữ toàn bộ dữ liệu trong heap, tùy nguồn |
| Phù hợp | Nội dung nhỏ/vừa đã có trong RAM | Nguồn stream đặc thù, một lần hoặc đã được quản lý |
| Dùng cho MIME gửi mail | Thường thuận tiện vì có thể đọc lại | Cần thận trọng về vòng đời và khả năng đọc lại |

Ví dụ có thể gặp:

~~~java
InputStreamResource resource =
        new InputStreamResource(inputStream);

helper.addAttachment("report.pdf", resource);
~~~

Cách này có thể gặp lỗi nếu mail provider cần truy cập resource nhiều lần. Không nên chọn InputStreamResource chỉ vì nghĩ rằng stream luôn tiết kiệm bộ nhớ; phải hiểu API mail và cách nguồn stream hoạt động.

### 5.2. ByteArrayResource không tự sao chép dữ liệu

Khi tạo:

~~~java
ByteArrayResource resource =
        new ByteArrayResource(pdfBytes);
~~~

resource dùng mảng byte được truyền vào. Nếu một thread khác sửa nội dung mảng trong lúc email đang được dựng hoặc gửi, dữ liệu đính kèm có thể thay đổi ngoài ý muốn.

Nếu cần cô lập dữ liệu khỏi caller, có thể tạo defensive copy:

~~~java
byte[] stableBytes = pdfBytes.clone();

ByteArrayResource resource =
        new ByteArrayResource(stableBytes);
~~~

Đổi lại, clone tạo thêm một bản sao trong bộ nhớ. Chỉ nên dùng khi cần bảo vệ tính bất biến hoặc tránh chia sẻ một mảng byte có thể bị sửa. Với file lớn, việc copy cũng làm tăng áp lực heap.

## 6. Chọn MIME type phù hợp với byte[]

MIME type mô tả nội dung của attachment. Nó không chuyển đổi dữ liệu thành định dạng tương ứng.

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Dữ liệu truyền vào phải thật sự là PDF.

| Loại file | MIME type |
| --- | --- |
| PDF | **application/pdf** |
| CSV | **text/csv; charset=UTF-8** |
| TXT | **text/plain; charset=UTF-8** |
| JSON | **application/json** |
| ZIP | **application/zip** |
| PNG | **image/png** |
| JPEG | **image/jpeg** |
| XML | **application/xml** hoặc **text/xml** theo mục đích |
| Dữ liệu nhị phân chưa xác định | **application/octet-stream** |

Ví dụ attachment CSV:

~~~java
byte[] csvBytes = csvContent.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Ví dụ ảnh PNG:

~~~java
helper.addAttachment(
        "chart.png",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

### 6.1. Đừng tin MIME type do người dùng tự khai báo

Nếu file đến từ upload, client có thể gửi Content-Type không đúng với dữ liệu thực. Ví dụ, nội dung không phải PDF nhưng khai báo application/pdf.

MIME type được dùng để mô tả part cho người nhận; nó không phải cơ chế xác minh file. Ứng dụng nên kiểm tra định dạng thực tế theo chính sách, giới hạn dung lượng và loại file được phép gửi.

### 6.2. application/octet-stream dùng khi nào?

Nếu không xác định được loại dữ liệu hoặc muốn trình bày như nội dung nhị phân tổng quát, **application/octet-stream** là kiểu thường dùng.

Tuy nhiên, nếu biết dữ liệu là PDF, CSV hoặc PNG, nên khai báo kiểu cụ thể. Kiểu chính xác giúp email client và hệ thống bảo mật phía nhận xử lý phù hợp hơn.

### 6.3. Không Base64 hóa byte[] trước khi tạo resource

Không làm:

~~~java
byte[] encoded = Base64.getEncoder().encode(pdfBytes);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(encoded),
        "application/pdf"
);
~~~

Ở đây dữ liệu part là chuỗi byte của Base64, không phải byte PDF gốc. Jakarta Mail có thể tiếp tục mã hóa dữ liệu part để truyền, dẫn tới người nhận khôi phục một file chứa chữ Base64 thay vì PDF.

Cách đúng:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Thư viện mail tự xử lý Content-Transfer-Encoding. Hãy cung cấp byte gốc của file.

## 7. Đặt tên attachment khi nguồn chỉ là byte[]

Một byte array không có filename. Tên file được truyền trong **addAttachment**:

~~~java
helper.addAttachment(
        "monthly-report.pdf",
        new ByteArrayResource(reportBytes),
        "application/pdf"
);
~~~

Tên này trở thành thông tin trong MIME header, thường ở **Content-Disposition: attachment; filename=...**. Nó chỉ là tên được đề xuất cho người nhận khi lưu file, không phải đường dẫn trên máy gửi.

### 7.1. Tên hiển thị không phải đường dẫn lưu file

Không dùng đường dẫn tuyệt đối của máy chủ làm filename. Điều này có thể làm lộ cấu trúc filesystem hoặc tạo tên hiển thị không mong muốn. Hãy đặt tên ngắn, rõ nghĩa và chỉ chứa metadata cần công khai.

### 7.2. Kiểm soát filename

Nếu tên được lấy từ dữ liệu bên ngoài, cần giới hạn:

- Độ dài.
- Ký tự điều khiển như CR/LF.
- Ký tự đường dẫn / và \.
- Các tên gây nhầm lẫn hoặc không phù hợp với hệ điều hành.
- Ký tự đặc biệt có thể ảnh hưởng cách header được diễn giải.
- Dữ liệu nhạy cảm trong tên file, như tên khách hàng hoặc mã nội bộ không được phép tiết lộ.

Jakarta Mail xử lý quoting và encoding header theo API MIME, nhưng điều đó không thay thế chính sách đặt tên file của ứng dụng. Không tự nối Content-Disposition bằng chuỗi raw.

### 7.3. Tên file Unicode

Tên tiếng Việt như **báo-cáo-tháng-11.pdf** có thể cần encoding header theo chuẩn MIME. Khi dùng **addAttachment(filename, resource, contentType)**, hãy truyền filename như giá trị API và để thư viện xử lý phần biểu diễn header.

Khả năng hiển thị Unicode filename còn phụ thuộc email client và hệ thống nhận. Nếu cần tương thích rộng, tên ASCII ngắn thường dễ xử lý hơn; nếu yêu cầu giữ Unicode, nên thử nghiệm trên các client mục tiêu.

## 8. Gửi nhiều attachment từ các ByteArrayResource

Một email có thể chứa nhiều file. Gọi **addAttachment** nhiều lần trước khi gửi:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);

helper.addAttachment(
        "chart.png",
        new ByteArrayResource(pngBytes),
        "image/png"
);

mailSender.send(message);
~~~

Cấu trúc khái niệm:

~~~text
multipart/mixed
├── text/plain
│   └── "Các tài liệu được đính kèm."
├── application/pdf
│   └── invoice.pdf
├── text/csv
│   └── orders.csv
└── image/png
    └── chart.png
~~~

Một message có nhiều MIME part vẫn là **một email**. Không cần gọi mailSender.send sau mỗi attachment.

### 8.1. Lặp qua danh sách file

Nếu nghiệp vụ có một danh sách tài liệu:

~~~java
public record MailAttachment(
        String filename,
        byte[] content,
        String contentType
) {}
~~~

Có thể thêm từng file:

~~~java
for (MailAttachment attachment : attachments) {
    helper.addAttachment(
            attachment.filename(),
            new ByteArrayResource(attachment.content()),
            attachment.contentType()
    );
}
~~~

Đây là ví dụ về cấu trúc dữ liệu. Trước khi thêm vào message, ứng dụng cần kiểm tra danh sách không vượt giới hạn số lượng, tổng kích thước, tên file và quyền truy cập từng tài liệu.

### 8.2. Giới hạn tổng dung lượng

Nếu có 10 file, mỗi file 5 MB, tổng dữ liệu thô đã khoảng 50 MB. Khi truyền qua MIME, dữ liệu nhị phân thường được mã hóa Base64, làm kích thước tăng thêm; còn có header, boundary và body email.

Không nên chỉ giới hạn từng file mà quên tổng dung lượng của toàn message. SMTP provider thường có giới hạn kích thước message, và giới hạn có thể được tính trên dữ liệu sau khi mã hóa.

Một chính sách gửi mail có thể giới hạn kích thước mỗi file, tổng byte của tất cả attachment, số lượng attachment và tổng kích thước message sau khi ước tính overhead.

## 9. Ví dụ CSV được tạo trong bộ nhớ rồi gửi đi

Một báo cáo CSV có thể được tạo từ danh sách dữ liệu:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

public byte[] createCsv(List<OrderRow> rows) {
    StringBuilder csv = new StringBuilder();
    csv.append("order_id,total,status\n");

    for (OrderRow row : rows) {
        csv.append(row.orderId()).append(',')
           .append(row.total()).append(',')
           .append(row.status()).append('\n');
    }

    return csv.toString().getBytes(StandardCharsets.UTF_8);
}
~~~

Ví dụ này đơn giản hóa việc escape CSV. Trong ứng dụng thực tế, nếu trường có dấu phẩy, dấu ngoặc kép hoặc newline, hãy dùng thư viện CSV phù hợp thay vì nối chuỗi trực tiếp.

Sau khi tạo byte[]:

~~~java
byte[] csvBytes = createCsv(rows);

helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Nội dung được mã hóa UTF-8. Nếu người nhận mở bằng spreadsheet, cách nhận diện UTF-8 có thể phụ thuộc phần mềm; có thể có yêu cầu BOM hoặc định dạng riêng theo hệ thống nhận, nhưng không nên thêm BOM một cách máy móc nếu hợp đồng dữ liệu không cần.

### 9.1. CSV có dữ liệu do người dùng nhập

Nếu CSV có các trường bắt đầu bằng ký tự như =, +, - hoặc @, một số spreadsheet có thể diễn giải nội dung thành công thức khi người dùng mở file. Đây là vấn đề **CSV formula injection**, khác với MIME attachment.

Nếu CSV được gửi để mở bằng spreadsheet, cần chính sách xử lý trường dữ liệu không tin cậy theo công cụ nhận và yêu cầu nghiệp vụ. Việc bọc byte[] trong ByteArrayResource không làm nội dung CSV an toàn hơn.

## 10. Ví dụ PDF được sinh từ hóa đơn

Giả sử một service tạo PDF bằng một thành phần chuyên biệt:

~~~java
public interface PdfGenerator {
    byte[] generateInvoice(Invoice invoice);
}
~~~

Service điều phối:

~~~java
@Service
public class InvoiceNotificationService {

    private final PdfGenerator pdfGenerator;
    private final InvoiceMailService mailService;

    public InvoiceNotificationService(
            PdfGenerator pdfGenerator,
            InvoiceMailService mailService
    ) {
        this.pdfGenerator = pdfGenerator;
        this.mailService = mailService;
    }

    public void notifyCustomer(Invoice invoice) throws MessagingException {
        byte[] pdf = pdfGenerator.generateInvoice(invoice);

        mailService.sendInvoice(
                invoice.getCustomerEmail(),
                invoice.getNumber(),
                pdf
        );
    }
}
~~~

Mail service:

~~~java
@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNumber,
            byte[] pdfBytes
    ) throws MessagingException {

        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalArgumentException("PDF rỗng");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn " + invoiceNumber);
        helper.setText(
                "Xin chào,\n"
                + "Hóa đơn " + invoiceNumber
                + " được gửi trong file đính kèm.",
                false
        );

        helper.addAttachment(
                "invoice-" + invoiceNumber + ".pdf",
                new ByteArrayResource(pdfBytes),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Đây là ví dụ minh họa. Trong hệ thống thực tế, invoiceNumber phải được chuẩn hóa trước khi dùng trong filename hoặc subject, recipient phải được kiểm tra và byte PDF phải đến từ nguồn đáng tin cậy.

### 10.1. Có cần ghi PDF xuống đĩa trước khi gửi?

Không, nếu PDF đã có trong byte[] và kích thước phù hợp. ByteArrayResource cho phép đưa trực tiếp dữ liệu vào MIME part.

Nếu ứng dụng cần lưu bản PDF cho mục đích khác, ví dụ người dùng tải từ portal hoặc lưu trữ lâu dài, có thể vừa lưu ở storage vừa gửi email. Hai yêu cầu đó độc lập với nhau; gửi email không nên là lý do duy nhất khiến hệ thống phải tạo một file tạm.

## 11. Kết hợp ByteArrayResource với nội dung HTML

Attachment có thể đi cùng HTML:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setFrom("reports@example.org");
helper.setTo("manager@example.net");
helper.setSubject("Báo cáo tháng");

helper.setText(
        "<html><body>"
      + "<h2>Báo cáo đã sẵn sàng</h2>"
      + "<p>Vui lòng tải file CSV đính kèm.</p>"
      + "</body></html>",
        true
);

helper.addAttachment(
        "monthly-report.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);

mailSender.send(message);
~~~

**MULTIPART_MODE_MIXED** ở đây cho phép body và attachment là các phần độc lập. Nếu HTML còn tham chiếu ảnh inline qua **cid:**, hãy dùng cấu trúc **MULTIPART_MODE_MIXED_RELATED** và thêm inline resource bằng **addInline**.

Không nhầm attachment từ ByteArrayResource với inline resource:

- **addAttachment** dành cho file tải riêng.
- **addInline** dành cho resource mà HTML tham chiếu bằng Content-ID.
- Cả hai có thể dùng cùng một nguồn ByteArrayResource, nhưng ý nghĩa MIME và API khác nhau.

## 12. Đính kèm từ dữ liệu database hoặc object storage

Một ứng dụng có thể lưu nội dung file trong database dạng BLOB hoặc lấy từ object storage.

### 12.1. Đọc byte từ database

Ví dụ:

~~~java
byte[] documentBytes = documentRepository
        .findContentById(documentId)
        .orElseThrow();

helper.addAttachment(
        "document.pdf",
        new ByteArrayResource(documentBytes),
        "application/pdf"
);
~~~

Đoạn repository trả về byte[] là minh họa. Trong hệ thống thực tế, cần xem kích thước file, kiểu dữ liệu database, cách tải BLOB và liệu driver có materialize toàn bộ nội dung vào heap hay không.

Nếu document lớn, đọc toàn bộ BLOB vào byte[] có thể làm tăng memory pressure. Có thể cần một chiến lược lưu trữ khác hoặc streaming.

### 12.2. Đọc dữ liệu từ object storage

Nếu SDK của storage trả byte[]:

~~~java
byte[] objectBytes = storageClient.downloadAsBytes(objectKey);

helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(objectBytes),
        "application/pdf"
);
~~~

Cách này đơn giản nhưng thường tải toàn bộ object về memory trước khi gửi.

Nếu SDK cung cấp một stream lớn, hãy cân nhắc tải xuống file tạm được quản lý hoặc dùng một InputStreamSource có thể mở stream mới theo yêu cầu của Jakarta Mail. Không truyền một stream one-shot rồi giả định thư viện chỉ đọc đúng một lần.

### 12.3. Quyền truy cập và nguồn dữ liệu

Trước khi đưa document vào email, ứng dụng cần xác định:

- Người dùng hiện tại có quyền nhận tài liệu này không?
- Tài liệu có thuộc đúng đơn hàng hoặc khách hàng không?
- Dữ liệu có đang ở trạng thái hoàn chỉnh?
- Có cần kiểm tra virus hoặc loại file không?
- Tệp có được phép gửi qua email theo chính sách lưu trữ không?

Một resource đọc được về mặt kỹ thuật không có nghĩa ứng dụng được phép gửi nó cho mọi recipient.

## 13. Quản lý bộ nhớ và hiệu năng

ByteArrayResource rất tiện, nhưng giữ toàn bộ dữ liệu trong heap. Với file nhỏ, điều đó thường đơn giản. Với file lớn hoặc nhiều email đồng thời, cần cân nhắc.

### 13.1. Chi phí cơ bản

Giả sử file gốc có kích thước **N byte**. Khi dùng ByteArrayResource:

1. Byte[] gốc chiếm khoảng N byte trong heap.
2. Nếu tạo defensive copy, có thêm khoảng N byte.
3. Nếu nguồn được tạo bằng ByteArrayOutputStream, buffer nội bộ và kết quả toByteArray có thể cùng tồn tại trong một khoảng thời gian.
4. MIME transport có thể mã hóa và buffer nội dung, làm phát sinh thêm bộ nhớ.
5. Base64 có kích thước xấp xỉ **4/3 dữ liệu gốc**, chưa tính CRLF, header và boundary.

Đây là mô hình ước lượng, không phải cam kết chính xác về allocation của mọi phiên bản thư viện.

Ví dụ, 20 email được gửi đồng thời, mỗi email có một attachment 10 MB. Chỉ riêng byte gốc đã có thể chiếm khoảng 200 MB nếu mỗi email giữ một bản dữ liệu riêng; phần MIME encoding và các buffer khác còn có thể tăng thêm.

### 13.2. Tránh giữ byte[] quá lâu

Sau khi gửi xong và không còn tham chiếu, byte[] có thể được garbage collector thu hồi. Nhưng nếu ứng dụng lưu attachment trong cache, collection hoặc object sống lâu, dữ liệu tiếp tục chiếm heap.

Một số nguyên tắc:

- Chỉ giữ byte[] trong phạm vi cần thiết.
- Không đưa toàn bộ nội dung file vào log.
- Tránh lưu byte[] trong singleton hoặc static collection nếu không có lý do rõ ràng.
- Hạn chế số email attachment lớn được gửi đồng thời.
- Đặt giới hạn kích thước trước khi materialize file vào byte[].
- Theo dõi heap, GC và queue khi gửi mail hàng loạt.

### 13.3. Khi nào nên dùng FileSystemResource?

Nếu file lớn đã được tạo trên đĩa, **FileSystemResource** có thể phù hợp hơn:

~~~java
helper.addAttachment(
        "large-report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf"
);
~~~

Resource đọc từ file theo nhu cầu của thư viện thay vì yêu cầu ứng dụng giữ toàn bộ byte[] trước. Tuy vậy, quá trình tạo MimeMessage và transport vẫn có thể buffer dữ liệu; không nên mặc định FileSystemResource bảo đảm streaming end-to-end không dùng bộ nhớ.

### 13.4. Khi nào nên dùng object storage link thay attachment?

Với tài liệu rất lớn hoặc nhiều file, gửi một link tải có thời hạn có thể giảm kích thước email. Cách này cần thiết kế quyền truy cập, thời hạn, xác thực, logging và thu hồi link phù hợp.

Đây là lựa chọn kiến trúc khác với attachment. Nếu nghiệp vụ yêu cầu người nhận có bản tài liệu ngay trong email và provider cho phép, attachment vẫn có thể là lựa chọn đúng.

## 14. Xử lý lỗi khi tạo và gửi attachment

Các lỗi có thể xuất hiện ở nhiều thời điểm:

| Giai đoạn | Ví dụ lỗi | Ý nghĩa |
| --- | --- | --- |
| Tạo dữ liệu | PDF generator lỗi | Chưa có byte file để gửi |
| Nạp nguồn | byte[] null hoặc rỗng | Attachment không có nội dung hợp lệ |
| Tạo MIME | Sai tên hoặc MIME metadata | Không thể dựng part đúng |
| Đọc resource | Nguồn dữ liệu không cung cấp được stream | MIME serialization thất bại |
| Gửi SMTP | Timeout, AUTH lỗi, recipient bị từ chối | Server không nhận message theo yêu cầu |
| Hậu chuyển phát | Bounce, spam hoặc policy bên nhận | SMTP accept chưa chắc email vào inbox |

**MimeMessageHelper.addAttachment** có thể ném **MessagingException** khi cấu trúc MIME không thể thiết lập. **JavaMailSender.send** có thể ném các loại **MailException** khi gửi thất bại. Lỗi của PDF generator hoặc storage thuộc lớp dữ liệu tạo file.

Nên phân biệt các nhóm này để có cách retry phù hợp.

### 14.1. Không retry mù quáng việc tạo và gửi toàn bộ nghiệp vụ

Giả sử PDF đã tạo thành công, SMTP timeout xảy ra. Nếu retry lại cả transaction tạo hóa đơn, có thể tạo thêm hóa đơn hoặc side effect khác. Hãy tách:

- Tạo hoặc lấy đúng tài liệu cần gửi.
- Dựng message.
- Gửi mail.
- Lưu trạng thái và retry theo event ID hoặc mã nghiệp vụ.

Nếu kết quả SMTP không xác định vì kết nối đứt sau khi server có thể đã nhận DATA, retry có thể tạo email trùng. SMTP không bảo đảm exactly-once delivery.

### 14.2. Ghi nhận lỗi mà không lộ nội dung file

Log có thể ghi mã hóa đơn hoặc mã tác vụ phù hợp, tên loại tài liệu, kích thước byte, MIME type, mã lỗi hoặc loại exception, số lần retry và thời điểm.

Không ghi toàn bộ byte[], nội dung PDF, token, dữ liệu cá nhân hoặc thông tin xác thực SMTP.

### 14.3. Xử lý attachment tùy chọn

Nếu nghiệp vụ cho phép email không có file khi tài liệu chưa sẵn sàng, hãy thể hiện rõ:

~~~java
if (pdfBytes != null && pdfBytes.length > 0) {
    helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
    );
}
~~~

Nếu attachment là bắt buộc, không nên âm thầm bỏ qua file null/rỗng rồi gửi email như thể hóa đơn đã được đính kèm. Hãy báo lỗi nghiệp vụ hoặc chuyển tác vụ sang trạng thái chờ tạo tài liệu.

## 15. Bảo mật dữ liệu trong attachment

Một file đính kèm có thể chứa thông tin nhạy cảm hơn phần body. Việc dùng ByteArrayResource không thay thế kiểm soát bảo mật.

### 15.1. Xác minh quyền nhận tài liệu

Trước khi gửi, cần kiểm tra recipient có được quyền nhận file hay không. Không lấy ID tài liệu từ request rồi gửi file tương ứng mà không kiểm tra quyền truy cập.

### 15.2. Kiểm tra loại file và kích thước

Nếu file đến từ upload hoặc nguồn bên ngoài, kiểm tra loại file thực tế, không chỉ phần mở rộng; giới hạn kích thước trước khi đọc toàn bộ byte; áp dụng malware scanning nếu chính sách yêu cầu; chỉ cho phép những định dạng nghiệp vụ chấp nhận.

### 15.3. Filename không được chứa dữ liệu nhạy cảm

Tên file có thể hiển thị cho người nhận. Không đưa đường dẫn nội bộ, username hệ thống, thư mục lưu trữ, secret hoặc metadata nội bộ vào filename.

### 15.4. Base64 không phải mã hóa bảo mật

MIME thường dùng base64 để biểu diễn dữ liệu nhị phân, nhưng bất kỳ người nào có email đều có thể giải mã. Nếu tài liệu cần bảo vệ, phải dùng cơ chế mã hóa tài liệu hoặc kênh tải có xác thực theo yêu cầu nghiệp vụ; không dựa vào base64.

### 15.5. Giới hạn lưu trữ và retention

Sau khi email được gửi, attachment có thể tồn tại trong mailbox của người nhận và các hệ thống mail trung gian theo chính sách của họ. Việc xóa bản byte[] khỏi heap hoặc xóa file tạm không thu hồi được bản sao đã gửi.

Cần cân nhắc dữ liệu nào được phép gửi email, thời gian lưu trữ và cách xử lý yêu cầu xóa dữ liệu theo chính sách tổ chức.

## 16. So sánh ByteArrayResource với các lựa chọn khác

| Tiêu chí | ByteArrayResource | FileSystemResource | ClassPathResource |
| --- | --- | --- | --- |
| Nguồn | byte[] | File trên đĩa | Tài nguyên classpath |
| Có cần file vật lý? | Không | Có | Không nhất thiết sau khi đóng gói |
| Dữ liệu trong heap | Toàn bộ byte[] được giữ trong heap | Không cần materialize toàn file trước ở tầng Resource | Tùy cách resource được đọc |
| Có thể đọc lại | Có, từ byte array | Thường có thể mở lại file | Thường có thể mở lại resource |
| Phù hợp | Nội dung sinh trong bộ nhớ | Báo cáo lớn đã được lưu | Logo, file tĩnh của ứng dụng |

**InputStreamResource** là một lựa chọn khác nhưng cần hiểu tính one-shot. Không nên thay ByteArrayResource bằng một InputStreamResource bọc stream đã đọc hoặc đã đóng.

### 16.1. Chọn theo nguồn dữ liệu

- File vừa tạo trong bộ nhớ, kích thước nhỏ/vừa: **ByteArrayResource**.
- File báo cáo đã lưu trên filesystem: **FileSystemResource**.
- Logo hoặc mẫu tài liệu đóng gói cùng ứng dụng: **ClassPathResource**.
- Nguồn stream có thể mở lại theo hợp đồng: một **InputStreamSource** phù hợp.
- Tài liệu rất lớn: cân nhắc storage và quy trình tải/gửi được thiết kế cho streaming hoặc link có kiểm soát.

## 17. Tách trách nhiệm tạo file và gửi mail

Một cấu trúc service dễ bảo trì có thể gồm:

~~~text
InvoiceApplicationService
       |
       v
InvoicePdfGenerator
       |
       v
byte[] PDF
       |
       v
InvoiceMailService
       |
       +-- MimeMessage
       +-- MimeMessageHelper
       +-- ByteArrayResource
       +-- addAttachment(...)
       |
       v
JavaMailSender
~~~

PDF generator không cần biết SMTP. Mail service không cần biết cách tính tiền hay dựng trang PDF. Mỗi thành phần có thể kiểm thử riêng.

~~~java
public interface InvoicePdfGenerator {
    byte[] generate(Invoice invoice);
}

public interface InvoiceMailer {
    void send(
            String recipient,
            String invoiceNumber,
            byte[] pdfBytes
    ) throws MessagingException;
}
~~~

Cách tách này giúp thay thư viện PDF hoặc thay nguồn byte mà không phải sửa logic dựng MIME.

### 17.1. Không để transaction database bị kéo dài bởi SMTP

Nếu PDF được tạo từ dữ liệu đơn hàng, hãy xác định transaction boundary phù hợp. Một transaction có thể lấy snapshot dữ liệu và cập nhật trạng thái; tạo PDF và gửi email có thể thực hiện sau commit nếu không cần nằm trong transaction đó.

SMTP là hệ thống bên ngoài và không thể rollback cùng database. Với email quan trọng cần retry bền vững, cân nhắc outbox/queue thay vì giữ transaction database trong lúc chờ gửi.

### 17.2. ByteArrayResource không quyết định thời điểm gửi

ByteArrayResource chỉ biểu diễn dữ liệu. Nó không tự chạy async, không tạo queue, không quản lý retry và không biết transaction đã commit chưa. Các quyết định đó thuộc service điều phối hoặc worker.

## 18. Kiểm thử việc đính kèm từ byte[]

Có thể kiểm tra nhiều lớp mà không phải gửi email tới hộp thư thật.

### 18.1. Kiểm tra dữ liệu nguồn

Đối với PDF, kiểm tra byte[] không null/rỗng và được tạo từ tài liệu hợp lệ. Với CSV, xác nhận encoding và nội dung. Với ảnh, kiểm tra định dạng thực.

### 18.2. Kiểm tra MIME message

Dùng test với MimeMessage hoặc SMTP capture server để xác nhận:

- Message có multipart.
- Có part attachment.
- Filename đúng.
- Content-Type đúng.
- Dữ liệu sau khi giải mã MIME khớp với byte nguồn.
- Body vẫn có nội dung như mong muốn.

Không nên phụ thuộc vào chuỗi boundary ngẫu nhiên hoặc giả định Base64 sẽ xuống dòng đúng một cách cố định.

### 18.3. Kiểm tra lỗi

Các tình huống có thể được kiểm tra riêng:

- byte[] null.
- byte[] rỗng.
- Tệp vượt giới hạn.
- Filename không hợp lệ.
- MIME type không được phép.
- Mail sender ném exception.
- Resource không thể cung cấp dữ liệu.
- SMTP server từ chối message vì kích thước.

Đây là các tình huống kiểm thử có thể áp dụng cho dự án. Việc kiểm thử cụ thể cần được thực hiện trong giai đoạn kiểm thử riêng.

## 19. Những lỗi thường gặp khi dùng ByteArrayResource

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không gọi được addAttachment với byte[] | byte[] không phải InputStreamSource | Bọc trong ByteArrayResource |
| Email không có attachment | Message không được tạo ở chế độ multipart hoặc không gọi addAttachment | Dùng MimeMessageHelper multipart |
| File tải về bị hỏng | Đã Base64 hóa byte trước khi bọc resource hoặc MIME type/byte sai | Truyền byte gốc và khai báo type đúng |
| Tên file không đúng | Không truyền filename rõ ràng | Dùng overload có attachmentFilename |
| MIME type là application/octet-stream | Không khai báo contentType hoặc không nhận diện được | Truyền MIME type tường minh khi biết |
| Gửi file lớn gây OutOfMemoryError | Toàn bộ byte[] và buffer chiếm heap | Giới hạn kích thước, giảm đồng thời, dùng storage/resource khác |
| Lỗi khi đọc stream | Dùng nguồn one-shot không thể mở lại | Dùng ByteArrayResource hoặc nguồn có thể tạo stream mới |
| Dữ liệu thay đổi trước khi gửi | Chia sẻ byte[] mutable với thread khác | Dùng snapshot bất biến hoặc defensive copy khi cần |
| Filename lộ đường dẫn nội bộ | Dùng path làm tên attachment | Đặt tên hiển thị riêng, không dùng đường dẫn |
| Gửi nhầm tài liệu | Không kiểm tra quyền của recipient đối với tài liệu | Authorization trước khi tạo message |
| SMTP từ chối message quá lớn | Tổng kích thước sau MIME vượt giới hạn | Giới hạn file/tổng message hoặc dùng link tải |

## 20. Câu hỏi thường gặp

**1. ByteArrayResource dùng để làm gì khi gửi mail?**

Nó bọc dữ liệu byte[] thành một Spring Resource có thể cung cấp InputStream, phù hợp với overload **MimeMessageHelper.addAttachment(...)** nhận InputStreamSource.

**2. Có cần ghi byte[] ra file trước khi đính kèm không?**

Không. Nếu dữ liệu đã có trong bộ nhớ và kích thước phù hợp, có thể dùng trực tiếp ByteArrayResource.

**3. Có cần Base64 encode trước không?**

Không. Truyền byte gốc. Jakarta Mail xử lý Content-Transfer-Encoding khi tạo MIME message.

**4. Vì sao addAttachment cần filename?**

ByteArrayResource chỉ mang dữ liệu, không tự biết tên file mà người nhận nên thấy. Filename được truyền riêng qua API.

**5. Có thể đính kèm nhiều ByteArrayResource không?**

Có. Gọi addAttachment nhiều lần trước khi gọi send. Mỗi lần tạo thêm một MIME part.

**6. Có thể dùng ByteArrayResource cho CSV không?**

Có. Chuyển nội dung CSV thành byte[] bằng UTF-8 rồi gọi addAttachment với **text/csv; charset=UTF-8**.

**7. ByteArrayResource có đọc được nhiều lần không?**

Có. Nó dựa trên byte array và có thể cung cấp InputStream mới từ dữ liệu đó. Đây là điểm thuận tiện so với một stream chỉ đọc một lần.

**8. Có nên dùng ByteArrayResource cho file 100 MB không?**

Thường cần cân nhắc rất kỹ. Dữ liệu phải nằm trong heap và quá trình tạo MIME có thể dùng thêm buffer. File lớn nên dùng cách lưu/đọc phù hợp hơn, đồng thời tuân theo giới hạn SMTP provider.

**9. ByteArrayResource có tự đặt Content-Type không?**

Không nên dựa vào nó để xác định mọi định dạng. Nếu biết file type, truyền contentType tường minh trong addAttachment.

**10. ByteArrayResource có tự đặt filename không?**

Không. Truyền filename riêng qua addAttachment.

**11. SimpleMailMessage có gửi được attachment không?**

Không. Dùng MimeMessage và MimeMessageHelper với multipart mode.

**12. Có thể dùng cùng byte[] cho attachment và inline image không?**

Có thể tạo resource từ byte[] cho cả addAttachment và addInline, nhưng hai thao tác có ngữ nghĩa MIME khác nhau. Attachment dành cho file tải riêng; inline resource cần Content-ID để HTML tham chiếu.

**13. ByteArrayResource có tự bảo vệ dữ liệu khỏi bị thay đổi không?**

Không nên coi nó là bản sao bất biến của byte[]. Nếu mảng được chia sẻ và bị sửa, nội dung đọc có thể thay đổi. Có thể clone khi cần snapshot độc lập, nhưng cần tính thêm bộ nhớ.

**14. Gửi thành công có chứng minh file đã tới inbox không?**

Không. SMTP chấp nhận message là một mốc; sau đó vẫn có thể xảy ra bounce, lọc spam, giới hạn dung lượng hoặc chính sách của hệ thống nhận.

## 21. Ghi nhớ khi đính kèm từ ByteArrayResource

**ByteArrayResource** cho phép Spring Mail đính kèm nội dung đã có trong **byte[]** mà không cần tạo file vật lý. Hãy tạo **MimeMessage**, khởi tạo **MimeMessageHelper** ở chế độ multipart, bọc dữ liệu trong **ByteArrayResource** rồi gọi **addAttachment(filename, resource, contentType)**.

Truyền byte gốc và để Jakarta Mail xử lý Base64; đặt filename và MIME type chính xác; kiểm soát kích thước, nguồn dữ liệu, quyền nhận và vòng đời byte array. ByteArrayResource có lợi thế đọc lại từ bộ nhớ, nhưng không phù hợp mặc định cho file rất lớn vì toàn bộ dữ liệu nằm trong heap và quá trình tạo MIME có thể phát sinh thêm bộ nhớ.

Khi tài liệu đã nằm trên đĩa hoặc quá lớn, cân nhắc **FileSystemResource** hay một chiến lược lưu trữ/streaming khác. Dù chọn Resource nào, việc đính kèm vẫn là một phần của **MimeMessage**; gửi thư, retry và quản lý transaction là trách nhiệm riêng của tầng ứng dụng.
