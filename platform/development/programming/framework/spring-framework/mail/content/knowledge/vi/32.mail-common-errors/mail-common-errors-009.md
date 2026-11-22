# Dùng ByteArrayResource nhưng đặt tên attachment không đúng

## 1. Vấn đề thường gặp trong Spring Framework Mail

Trong **Spring Framework Mail**, một tình huống rất phổ biến là ứng dụng tạo nội dung tệp trong bộ nhớ — ví dụ hóa đơn PDF, báo cáo Excel, CSV hoặc một tài liệu sinh từ template — rồi đính kèm nội dung đó vào email bằng `ByteArrayResource`.

Đoạn code thường bắt đầu như sau:

~~~java
byte[] pdfBytes = invoicePdfGenerator.generate(invoice);
ByteArrayResource resource =
        new ByteArrayResource(pdfBytes);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setTo(customerEmail);
helper.setSubject("Hóa đơn");
helper.setText("Hóa đơn được đính kèm.", false);

helper.addAttachment(resource.getFilename(), resource);
mailSender.send(message);
~~~

Nhìn qua, câu lệnh `resource.getFilename()` có vẻ hợp lý. Nhưng **`ByteArrayResource` không mang tên tệp mặc định**, nên `getFilename()` thường trả về `null`. Khi đưa giá trị đó vào đối số `attachmentFilename` của `MimeMessageHelper.addAttachment(...)`, ứng dụng có thể bị lỗi kiểm tra tham số ngay tại bước xây dựng email.

Ngay cả khi thay bằng một tên không có đuôi mở rộng như `"report"`, email có thể gửi được nhưng chương trình đọc mail hiển thị attachment khó hiểu, tự nhận dạng sai loại nội dung hoặc không có tên như người dùng mong đợi.

**Bản chất lỗi:** nội dung byte của tệp, đối tượng `Resource` và **tên tệp trong MIME attachment** là ba thứ khác nhau. Khi dùng `ByteArrayResource`, hãy truyền **tên attachment hợp lệ, có chủ đích** cho `MimeMessageHelper.addAttachment(...)`, thay vì cho rằng `ByteArrayResource` biết tên đó.

## 2. Cách sửa nhanh và đúng

Với nội dung PDF sinh trong bộ nhớ:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.com");
helper.setSubject("Hóa đơn tháng 11");
helper.setText("Vui lòng xem hóa đơn trong tệp đính kèm.", false);

byte[] pdfBytes = invoicePdfGenerator.generate(invoice);
ByteArrayResource resource = new ByteArrayResource(pdfBytes);

// Tên attachment đến từ nghiệp vụ, không đến từ getFilename().
helper.addAttachment(
        "hoa-don-thang-11.pdf",
        resource,
        "application/pdf");

mailSender.send(message);
~~~

Phần `invoicePdfGenerator` và `invoice` là thành phần nghiệp vụ minh họa. Địa chỉ email và tên file ở đây chỉ là dữ liệu giả.

Điểm cần nhớ:

- Đối số **thứ nhất** là tên file người nhận sẽ thấy, ví dụ `hoa-don-thang-11.pdf`.
- Đối số **thứ hai** là nguồn nội dung; `ByteArrayResource` trả lại một luồng đọc từ mảng byte.
- Đối số **thứ ba** là MIME content type; `application/pdf` cho PDF, `text/csv` cho CSV.
- `MimeMessageHelper(message, true, "UTF-8")` bật multipart để có thể thêm attachment và cấu hình charset cho phần văn bản.
- `setText(...)` cấu hình nội dung email; `addAttachment(...)` cấu hình phần MIME attachment riêng.
- Tệp PDF phải **thực sự chứa byte PDF hợp lệ**; đổi tên hay content type không chuyển byte bất kỳ thành PDF.

Với phần lớn trường hợp, **chỉ sửa cách truyền filename** đã giải quyết được lỗi chính:

~~~java
// Sai: ByteArrayResource#getFilename() trả về null.
helper.addAttachment(resource.getFilename(), resource);

// Đúng: cung cấp tên tệp rõ ràng.
helper.addAttachment("invoice-2026-11.pdf", resource);

// Rõ ràng hơn khi muốn kiểm soát MIME content type.
helper.addAttachment(
        "invoice-2026-11.pdf",
        resource,
        "application/pdf");
~~~

Không cần kế thừa `ByteArrayResource` hoặc viết một cơ chế lưu file tạm chỉ để đặt tên attachment.

## 3. ByteArrayResource thực chất là gì?

`ByteArrayResource` nằm trong `org.springframework.core.io`. Nó bọc một `byte[]` trong một abstraction thuộc họ `Resource`, thường được dùng khi dữ liệu đã có sẵn trong RAM.

Ví dụ:

~~~java
byte[] bytes = new byte[] {1, 2, 3, 4};

ByteArrayResource resource =
        new ByteArrayResource(bytes);

long size = resource.contentLength();     // 4
String description = resource.getDescription();
String filename = resource.getFilename(); // null theo mặc định
~~~

Những khả năng hữu ích:

- `getInputStream()` trả một `ByteArrayInputStream` để đọc dữ liệu.
- Nguồn byte có thể được đọc lại nhiều lần (khác với một nguồn chỉ có một stream dùng một lần).
- `contentLength()` xác định từ độ dài mảng byte.
- `getDescription()` là thông tin mô tả Resource, **không phải tên file gửi qua email**.
- `getFilename()` không được `ByteArrayResource` gán dựa vào mô tả hoặc nội dung.

Điều này giải thích tại sao:

~~~java
new ByteArrayResource(pdfBytes)
~~~

không tương đương:

~~~text
A PDF file on disk with a filesystem filename.
~~~

Một đối tượng trong bộ nhớ không có path hoặc tên file vật lý để Spring suy ra.

### Khác biệt giữa Resource và attachment MIME

`Resource` là abstraction cho cách **đọc dữ liệu**. Còn một MIME attachment cần ít nhất **payload** và metadata như Content-Disposition, filename, Content-Type. `MimeMessageHelper` kết hợp các thông tin này khi tạo phần MIME.

~~~text
byte[] PDF data
    |
    v
ByteArrayResource
    |
    | supplies bytes
    v
MimeMessageHelper.addAttachment(
    attachmentFilename,
    inputStreamSource,
    contentType
)
    |
    v
MIME body part with headers + bytes
    |
    v
Mail client renders attachment
~~~

## 4. Hai constructor ByteArrayResource thường gây hiểu nhầm

Spring có constructor `ByteArrayResource(byte[])` và constructor `ByteArrayResource(byte[], String description)`.

Nhiều người viết:

~~~java
ByteArrayResource resource =
        new ByteArrayResource(
                pdfBytes,
                "invoice-november.pdf");

helper.addAttachment(resource.getFilename(), resource);
~~~

và kỳ vọng constructor hai tham số đã đặt filename. **Không đúng.** Đối số thứ hai là `description`; nó giúp mô tả đối tượng Resource cho thông báo chẩn đoán, không được tự động coi là `getFilename()`.

Ví dụ minh họa:

~~~java
ByteArrayResource resource = new ByteArrayResource(
        "hello".getBytes(java.nio.charset.StandardCharsets.UTF_8),
        "my-report.txt");

System.out.println(resource.getDescription());
System.out.println(resource.getFilename());
~~~

`getDescription()` chứa chuỗi mô tả có liên quan tới `my-report.txt`, còn `getFilename()` vẫn là `null`. Vì vậy vẫn phải viết:

~~~java
helper.addAttachment("my-report.txt", resource);
~~~

**Quy tắc:** `description` là metadata của `Resource`; `attachmentFilename` là metadata của MIME part. Không tráo hai khái niệm này.

## 5. MimeMessageHelper.addAttachment nhận những thông tin nào?

Các overload hay dùng của `MimeMessageHelper` bao gồm:

~~~java
addAttachment(String attachmentFilename,
              InputStreamSource inputStreamSource)

addAttachment(String attachmentFilename,
              InputStreamSource inputStreamSource,
              String contentType)
~~~

Trong ngữ cảnh này:

| Tham số | Chức năng | Giá trị minh họa |
|---|---|---|
| `attachmentFilename` | Tên attachment trong email | `receipt-583.pdf` |
| `inputStreamSource` | Cung cấp stream đọc byte | `new ByteArrayResource(pdfBytes)` |
| `contentType` | MIME media type của phần đính kèm | `application/pdf` |

Khi sử dụng overload không truyền `contentType`, helper có thể suy ra media type từ tên attachment qua cơ chế `FileTypeMap` của nó. Do đó **đuôi mở rộng chính xác** vừa giúp người nhận nhận diện file vừa giúp hệ thống đoán content type.

Nếu ứng dụng phải hỗ trợ định dạng riêng, hoặc không muốn phụ thuộc type detection theo tên, nên truyền content type tường minh:

~~~java
helper.addAttachment("export.csv", resource, "text/csv");
helper.addAttachment("report.pdf", resource, "application/pdf");
helper.addAttachment(
        "archive.zip", resource, "application/zip");
~~~

Content type chỉ là khai báo MIME. **Nó không sửa dữ liệu bị lỗi, không chứng minh file an toàn và không tự thêm extension vào filename.**

### Trường hợp truyền tên null hoặc rỗng

Không nên truyền:

~~~java
helper.addAttachment(null, resource);
helper.addAttachment("", resource);
~~~

Tên null/rỗng không có ngữ nghĩa attachment hợp lệ trong ứng dụng. Helper thường kiểm tra tên không null; với tên rỗng hoặc tên chỉ khoảng trắng, ứng dụng cần chủ động validation. Đừng chờ mail client hiển thị một tên kỳ lạ mới xử lý.

## 6. File name không phải MIME content type

Khi nhận email, mail client quan tâm tới nhiều header:

~~~text
Content-Type: application/pdf; name="receipt-583.pdf"
Content-Disposition: attachment; filename="receipt-583.pdf"
Content-Transfer-Encoding: base64
~~~

Đây là **ví dụ dạng MIME**; chuỗi header/encoding thực tế có thể khác tùy Jakarta Mail, charset và khách đọc mail.

Ba khía cạnh:

1. **Filename:** cách file được gợi ý đặt tên khi người nhận tải về.
2. **Content-Type:** loại nội dung ứng dụng khai báo.
3. **Payload:** các byte thực sự được gửi trong MIME body part.

Ví dụ:

| Filename | Content-Type | Payload | Kết quả |
|---|---|---|---|
| `report.pdf` | `application/pdf` | Byte PDF hợp lệ | Phù hợp |
| `report` | `application/pdf` | Byte PDF hợp lệ | Có thể thiếu extension khi tải |
| `report.pdf` | `application/octet-stream` | Byte PDF hợp lệ | Một số client vẫn mở được, metadata kém rõ |
| `report.pdf` | `application/pdf` | Byte CSV | **Sai nội dung** dù metadata có vẻ đúng |
| `report.csv` | `text/csv` | Byte CSV UTF-8 | Phù hợp; nên xem xét charset/BOM theo client |
| `report.xlsx` | MIME XLSX chuẩn | Byte XLSX hợp lệ | Phù hợp |

Vì vậy sửa filename **khác với sửa content type**; một lỗi có thể đi cùng lỗi còn lại.

## 7. Vì sao lỗi có thể xuất hiện trước khi gọi send?

Đoạn code:

~~~java
helper.addAttachment(resource.getFilename(), resource);
mailSender.send(message);
~~~

có thể thất bại ngay tại `addAttachment(...)` nếu filename là null. Đó không phải lỗi SMTP và **không có nghĩa provider đã nhận submission**.

Một số loại lỗi theo giai đoạn:

| Giai đoạn | Dấu hiệu | Hướng kiểm tra |
|---|---|---|
| Tạo Resource | `pdfBytes` null/không có dữ liệu | PDF generator và input |
| Chọn tên file | `resource.getFilename() == null` | Tạo tên tường minh |
| `addAttachment(...)` | Argument validation/MIME construction | Filename, content type, multipart mode |
| Render MIME | Header filename, encoding hoặc MIME type không như ý | Kiểm tra MIME part trước khi gửi |
| `mailSender.send(...)` | Auth/TLS/SMTP rejection/timeout | Transport và provider, tách khỏi filename |
| Client mở mail | Hiển thị tên khác hoặc attachment bị chặn | MIME headers, client policy, malware/security |

Đừng coi `IllegalArgumentException` tại bước dựng MIME là một lỗi tạm thời của SMTP rồi retry theo exponential backoff. Một lỗi tên file sẽ lặp lại cho đến khi sửa code hoặc dữ liệu.

## 8. Các biến thể code sai và cách sửa

### 8.1. Lấy tên từ ByteArrayResource.getFilename()

~~~java
ByteArrayResource bytes = new ByteArrayResource(pdfBytes);
helper.addAttachment(bytes.getFilename(), bytes); // Sai.
~~~

Sửa:

~~~java
helper.addAttachment("invoice.pdf", bytes, "application/pdf");
~~~

### 8.2. Nhầm description thành filename

~~~java
ByteArrayResource bytes =
        new ByteArrayResource(pdfBytes, "invoice.pdf");
helper.addAttachment(bytes.getFilename(), bytes); // Vẫn sai.
~~~

Sửa:

~~~java
helper.addAttachment("invoice.pdf", bytes, "application/pdf");
~~~

### 8.3. Dùng tên file không có extension

~~~java
helper.addAttachment("invoice-583", bytes);
~~~

Điều này có thể tạo một attachment có tên nhưng khó nhận diện kiểu file; type detection cũng có thể không như mong đợi. Sửa:

~~~java
helper.addAttachment(
        "invoice-583.pdf", bytes, "application/pdf");
~~~

### 8.4. Đặt sai extension

~~~java
helper.addAttachment(
        "invoice-583.txt", pdfBytesResource, "application/pdf");
~~~

MIME type nói PDF nhưng filename nói TXT. Tên phải phản ánh **định dạng byte thực sự**; đừng thêm đuôi chỉ để vượt qua một validation.

### 8.5. Tự đặt một tên path tuyệt đối

~~~java
helper.addAttachment(
        "C:\\company\\internal\\customer-583.pdf",
        resource);
~~~

Người nhận có thể nhìn thấy một đường dẫn nội bộ hoặc tên gây nhầm lẫn, tùy client. Chỉ truyền basename an toàn:

~~~java
helper.addAttachment(
        "customer-583.pdf", resource, "application/pdf");
~~~

### 8.6. Dùng addInline cho file cần tải về

~~~java
helper.addInline("report.pdf", resource, "application/pdf");
~~~

`addInline(...)` có semantics **nội dung nhúng theo Content-ID**, không phải cách thông thường để tạo file đính kèm với filename tùy ý. Với tài liệu người nhận cần tải, sử dụng `addAttachment(...)`.

## 9. Ví dụ hoàn chỉnh: gửi hóa đơn PDF từ byte[]

Giả sử một use case đã tạo được byte PDF qua component nghiệp vụ:

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
    private final InvoicePdfGenerator pdfGenerator;

    public InvoiceMailService(
            JavaMailSender mailSender,
            InvoicePdfGenerator pdfGenerator) {
        this.mailSender = mailSender;
        this.pdfGenerator = pdfGenerator;
    }

    public void sendInvoice(Invoice invoice)
            throws MessagingException {

        byte[] pdfBytes = pdfGenerator.generate(invoice);
        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalStateException(
                    "Generated invoice PDF is empty");
        }

        String filename =
                "invoice-" + invoice.safeReference() + ".pdf";

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(invoice.recipientEmail());
        helper.setSubject(
                "Hóa đơn " + invoice.safeReference());
        helper.setText(
                "Xin chào, vui lòng xem hóa đơn đính kèm.",
                false);

        helper.addAttachment(
                filename,
                new ByteArrayResource(pdfBytes),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

`Invoice` và `InvoicePdfGenerator` là các thành phần minh họa của ứng dụng. Phương thức `invoice.safeReference()` được giả định trả **mã nghiệp vụ đã được kiểm soát** (ví dụ chữ, số và dấu gạch ngang), không phải dữ liệu nhập thô của người dùng.

### Vì sao khai báo multipart mode tường minh?

`MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED` hỗ trợ mô hình gồm body content và các phần attachment/inline. Việc dùng constructor `new MimeMessageHelper(message, true, "UTF-8")` cũng là cách phổ biến để bật multipart, nhưng tên mode tường minh giúp người đọc biết code đang tạo MIME đa phần.

Thứ tự `setText(...)` rồi `addAttachment(...)` giữ ví dụ dễ hiểu. Với nội dung inline (hình CID), thứ tự còn có ý nghĩa tương thích với một số mail client, được giải thích sau.

### Lưu ý transaction và exception

`sendInvoice(...)` không nên được gọi bên trong transaction ghi hóa đơn nếu yêu cầu tính nhất quán giữa nghiệp vụ và email. SMTP submission không rollback cùng database. Khi cần gửi tin cậy, hãy ghi mail intent trong **transactional outbox**, sau đó worker dựng MIME và submit.

`MessagingException` có thể xuất hiện ở bước chuẩn bị MIME; lỗi SMTP thường được Spring Mail bọc trong các `MailException` tương ứng. Cần phân loại lỗi theo giai đoạn để không retry những tệp bị đặt tên sai.

## 10. Ví dụ CSV sinh trong bộ nhớ

CSV dễ gặp lỗi tên tệp khi xuất dữ liệu động:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;

String csv = "id,amount\r\n"
        + "INV-1001,250000\r\n"
        + "INV-1002,180000\r\n";

byte[] csvBytes = csv.getBytes(StandardCharsets.UTF_8);
ByteArrayResource csvResource =
        new ByteArrayResource(csvBytes);

helper.addAttachment(
        "invoice-export-2026-11.csv",
        csvResource,
        "text/csv; charset=UTF-8");
~~~

Ở đây tên file không được lấy từ `csvResource.getDescription()` hay `getFilename()` mà được đặt từ ngữ cảnh báo cáo.

### CSV mở bằng Excel không đúng dấu tiếng Việt?

Đó thường là vấn đề **mã hóa nội dung CSV/ứng dụng mở file**, không phải lỗi tên attachment. Các yếu tố cần xem:

- Byte nội dung được tạo bằng UTF-8 hoặc charset mong muốn chưa?
- File chứa dấu phân tách `,`, `;` hoặc tab theo yêu cầu người dùng?
- Excel ở môi trường sử dụng có kỳ vọng UTF-8 BOM không?
- Các trường chứa dấu phẩy, dấu nháy kép hoặc xuống dòng đã được quote CSV đúng chưa?
- Phần mềm tải file có giữ nguyên byte attachment không?

Việc đổi filename từ `report` thành `report.csv` cải thiện nhận diện nhưng **không tự sửa lỗi encoding trong dữ liệu**.

### CSV formula injection

Khi CSV chứa dữ liệu do người dùng cung cấp, các ô bắt đầu bằng `=`, `+`, `-` hoặc `@` có thể bị spreadsheet software diễn giải như công thức. Nên thiết kế encoding/escaping phù hợp khi xuất CSV cho môi trường spreadsheet. Đây là bảo vệ nội dung, tách biệt với cách đặt tên file.

## 11. Ví dụ Excel XLSX và MIME type phù hợp

Một attachment Excel hiện đại:

~~~java
byte[] xlsxBytes = exportService.generateXlsx(report);

helper.addAttachment(
        "sales-2026-11.xlsx",
        new ByteArrayResource(xlsxBytes),
        "application/vnd.openxmlformats-officedocument."
                + "spreadsheetml.sheet");
~~~

Trong code Java, chuỗi content type được ghép từ hai literal cho dễ đọc; giá trị MIME thực tế là một chuỗi liên tục.

Tránh đặt tên `report.xls` cho byte của tệp `.xlsx`: XLS và XLSX là hai định dạng khác nhau. Không thể đổi định dạng chỉ bằng extension.

### Nếu file đang có trên đĩa

Nếu producer đã tạo sẵn tệp ở filesystem, không cần tải toàn bộ vào `byte[]`:

~~~java
import org.springframework.core.io.FileSystemResource;
import java.io.File;

FileSystemResource file =
        new FileSystemResource(new File(
                "/srv/reports/monthly-sales.xlsx"));

helper.addAttachment(
        "monthly-sales.xlsx",
        file,
        "application/vnd.openxmlformats-officedocument."
                + "spreadsheetml.sheet");
~~~

`FileSystemResource` có thể mang filename từ path, nhưng vẫn nên truyền **tên hiển thị do ứng dụng chọn**. Tên nội bộ `/srv/reports/monthly-sales.xlsx` không cần bị tiết lộ cho người nhận.

Đường dẫn trên chỉ minh họa; trong production phải đảm bảo file do hệ thống tạo ra, không xây đường dẫn từ user input một cách thiếu kiểm soát.

## 12. So sánh các loại Resource khi đính kèm email

| Loại | Nguồn dữ liệu | `getFilename()` | Đọc lại stream | Khi nào phù hợp |
|---|---|---|---|---|
| `ByteArrayResource` | `byte[]` trong RAM | Thường `null` | Có, tạo stream mới từ byte[] | PDF/CSV/XLSX vừa phải đã sinh trong bộ nhớ |
| `FileSystemResource` | Tệp trên filesystem | Thường là basename | Có thể mở stream mới | Tệp lớn hoặc có sẵn trên đĩa |
| `ClassPathResource` | Resource trong classpath | Thường có tên resource | Thường đọc lại được tùy nguồn | Tệp tĩnh như hướng dẫn/tài liệu mẫu |
| `InputStreamResource` | Một `InputStream` đã mở | Không tự có filename đáng tin | Thường chỉ một lần | Thường **không phù hợp** cho MIME attachment cần đọc lại |
| `InputStreamSource` tự viết | Nguồn cung cấp stream | Không có `getFilename()` ở interface | Phụ thuộc implementation | Storage lớn, cần mở mới mỗi lần |

### Vì sao InputStreamResource hay gây lỗi khác?

`MimeMessageHelper.addAttachment(...)` yêu cầu nguồn stream có thể được mở khi MIME được serialize. `InputStreamResource` thường đại diện **một stream đã được mở**, báo `isOpen() == true` và không bảo đảm trả lại stream mới. Helper có thể từ chối hoặc gặp lỗi đọc lại.

Ví dụ cần tránh:

~~~java
InputStream input = storage.openStream(key);
InputStreamResource resource =
        new InputStreamResource(input);

helper.addAttachment("export.pdf", resource);
~~~

Nếu dữ liệu nhỏ, dùng `ByteArrayResource`. Nếu tệp lớn, dùng `FileSystemResource` hoặc một `InputStreamSource` được thiết kế để **mỗi lần getInputStream() trả một stream mới**, với thời hạn tồn tại dữ liệu phù hợp tới khi gửi.

### InputStreamSource có tên file không?

`InputStreamSource` chỉ mô tả cách cung cấp `InputStream`. Nó không cam kết có path hay filename. Tên MIME vẫn là tham số `attachmentFilename` của helper, bất kể nội dung đến từ bộ nhớ, filesystem hay object storage.

## 13. Vì sao đặt filename trong addAttachment tốt hơn kế thừa Resource?

Có thể viết một subclass của `ByteArrayResource` để override `getFilename()`:

~~~java
public final class NamedByteArrayResource
        extends ByteArrayResource {
    private final String filename;

    public NamedByteArrayResource(
            byte[] bytes, String filename) {
        super(bytes);
        this.filename = filename;
    }

    @Override
    public String getFilename() {
        return filename;
    }
}
~~~

Class minh họa này hợp lệ về mặt ý tưởng nếu một API của ứng dụng thực sự cần một `Resource` có tên. Tuy nhiên, đối với `MimeMessageHelper.addAttachment(...)`:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes));
~~~

là đủ và thường rõ ràng hơn. Việc thêm subclass có thể làm người đọc tưởng rằng helper sẽ tự dùng `getFilename()` khi truyền resource, trong khi API của helper **yêu cầu filename tường minh**.

Subclass chỉ có ích khi bạn thực sự cần thuộc tính filename đi cùng Resource qua nhiều layer. Nếu dùng cách này, vẫn phải validate filename và không giả định rằng mọi consumer sẽ tự lấy `getFilename()`.

## 14. Tên attachment nên được lấy từ đâu?

Một tên tốt thường có các phần:

~~~text
<document-type>-<safe-reference>-<date>.<extension>
~~~

Ví dụ:

- `invoice-INV-583-2026-11.pdf`
- `sales-report-2026-11.xlsx`
- `support-attachments-2026-11.zip`
- `statement-2026-Q4.csv`

Nguồn dữ liệu ưu tiên:

1. **Document type** do server xác định.
2. **Business reference** đã được kiểm soát và không tiết lộ thông tin không cần thiết.
3. **Ngày/kỳ báo cáo** ở định dạng ổn định, không phụ thuộc locale.
4. **Extension** tương ứng với loại byte thực tế đã tạo.

Không nên dùng trực tiếp:

- Email của người nhận trong filename.
- Tên đầy đủ hoặc số giấy tờ nhạy cảm.
- Đường dẫn tạm trên máy chủ.
- Chuỗi subject gốc của email.
- Tên upload không kiểm tra từ người dùng.
- Tên chứa `../` hoặc ký tự điều khiển.

### Tên file là dữ liệu hiển thị tới bên ngoài

Ngay cả khi attachment được mã hóa truyền qua TLS, người nhận vẫn thấy filename và có thể chuyển tiếp hoặc lưu. Không nhét thông tin nhạy cảm vào tên tệp chỉ vì nó không nằm trong body.

## 15. Dùng extension đúng để hỗ trợ content type detection

Một số overload của `addAttachment` xác định content type thông qua tên tệp:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes));
~~~

Với cấu hình chuẩn, `.pdf` thường được nhận diện là `application/pdf`. Nhưng danh sách MIME mappings có thể phụ thuộc phiên bản/framework và cấu hình type map.

Khi cần hành vi xác định, nên truyền type:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

Không đặt `filename="invoice.pdf"` rồi chỉ định `contentType="text/plain"` nếu dữ liệu là PDF. Sự bất nhất có thể khiến phần mềm nhận mail quyết định theo những cách khác nhau.

### Extension cũng không quyết định bảo mật

Một file tên `invoice.pdf` có thể chứa nội dung không hợp lệ hoặc nguy hiểm. Hệ thống nhận mail có thể quét/quarantine attachment dựa trên byte thực tế, loại file, domain reputation hoặc chính sách bảo mật riêng. Không dùng filename để khẳng định file an toàn.

## 16. Tên file Unicode, dấu tiếng Việt và khả năng tương thích

Ví dụ tên tiếng Việt:

~~~text
Hóa đơn tháng 11.pdf
Báo cáo doanh thu quý IV.xlsx
Tổng hợp yêu cầu.csv
~~~

MIME headers có các quy tắc mã hóa tên chứa ký tự ngoài ASCII, và các mail client có mức độ hỗ trợ khác nhau. Jakarta Mail/Spring Mail có cơ chế ghi header filename; ứng dụng không nên tự nối chuỗi chứa dấu tiếng Việt trực tiếp vào raw MIME header mà không hiểu quy tắc encoding.

Để tương thích cao với nhiều email clients, có thể cân nhắc sử dụng tên **ASCII an toàn**:

~~~text
hoa-don-thang-11.pdf
bao-cao-doanh-thu-q4.xlsx
~~~

Đây là lựa chọn tương thích, không phải quy tắc bắt buộc cấm Unicode.

### Các điểm cần kiểm tra khi Unicode bị lỗi

- Charset của message/body có được cấu hình, ví dụ `UTF-8`?
- Jakarta Mail implementation đang xử lý filename parameters như thế nào?
- Có code nào tự sửa header `Content-Disposition` hoặc `Content-Type` sau khi helper tạo part không?
- Có proxy/gateway nào viết lại MIME headers?
- Mail client đang hiển thị filename theo thông số nào?
- Tên attachment được tạo từ một nguồn dữ liệu dùng encoding khác không?

Spring `MimeMessageHelper` có thiết lập liên quan tới cách mã hóa filename, chẳng hạn `setEncodeFilenames(boolean)`, tùy phiên bản Spring. Tuy nhiên, bật/tắt một tùy chọn không thể thay thế việc kiểm tra tương thích MIME giữa Jakarta Mail và client đích. Những cơ chế như MIME encoded-word và RFC 2231 parameters có lịch sử hỗ trợ khác nhau; nên kiểm thử trên phiên bản/framework/provider thực tế.

## 17. Chuẩn hóa tên file động trước khi đưa vào MIME

Khi tên attachment được ghép từ dữ liệu nghiệp vụ, cần tránh ký tự không phù hợp trên các hệ điều hành và các ký tự điều khiển trong headers.

Một **chính sách đơn giản** cho tên file có thể là:

- Chỉ dùng basename, không dùng đường dẫn tuyệt đối hoặc thư mục.
- Không có ký tự xuống dòng `CR`/`LF`, NUL hoặc control characters.
- Không có `/`, `\\`, dấu hai chấm và các ký tự đặc biệt dễ gây lỗi trên Windows.
- Có extension đã biết từ **định dạng file thật**, không lấy extension tùy ý từ client.
- Giới hạn độ dài để tránh attachment name quá dài.
- Tránh tên nhạy cảm, `.`, `..` hoặc tên dành riêng của filesystem.

### Tốt nhất: tạo tên từ một cấu trúc có kiểm soát

Ví dụ với business ID đã được giới hạn:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public final class InvoiceAttachmentNames {
    private InvoiceAttachmentNames() {
    }

    public static String fromInvoice(
            String invoiceCode, LocalDate issueDate) {
        if (invoiceCode == null
                || !invoiceCode.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException(
                    "Invalid invoice code");
        }
        if (issueDate == null) {
            throw new IllegalArgumentException(
                    "Issue date is required");
        }

        return "invoice-" + invoiceCode + "-"
                + issueDate.format(
                        DateTimeFormatter.ISO_LOCAL_DATE)
                + ".pdf";
    }
}
~~~

Sử dụng:

~~~java
String filename = InvoiceAttachmentNames.fromInvoice(
        "INV-583", LocalDate.of(2026, 11, 12));

helper.addAttachment(
        filename,
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

Kết quả:

~~~text
invoice-INV-583-2026-11-12.pdf
~~~

Phương pháp này tốt vì extension được server chọn từ loại tài liệu, còn phần biến đổi đã được giới hạn rõ ràng.

### Nếu buộc phải nhận tên upload từ người dùng

Một tên như:

~~~text
../../internal/secrets.pdf
invoice.pdf\r\nX-Custom-Header: suspicious
report.pdf.exe
~~~

không nên được đưa nguyên vẹn vào attachment filename hoặc tên file trên filesystem. Hãy có một bộ xác minh tên riêng cho upload và chính sách loại file; cần phân biệt:

- **Tên hiển thị an toàn** trong email.
- **Tên lưu trữ** do server tạo (thường là opaque ID).
- **Extension hợp lệ** dựa trên định dạng file đã được kiểm tra.

Các bước strip path/truncate đơn giản không đủ để bảo đảm nội dung upload an toàn hoặc ngăn mọi biến thể path traversal; với file untrusted còn cần kiểm tra authorization, content scanning, size limits và storage policy.

## 18. Content-Disposition: attachment hay inline?

Email MIME có thể chứa những phần được hiển thị theo hai mục đích:

| Cơ chế | Header thường gặp | Ý nghĩa |
|---|---|---|
| Attachment | `Content-Disposition: attachment` | Người nhận thấy file tải về |
| Inline | `Content-Disposition: inline` và/hoặc `Content-ID` | Ảnh/nội dung nhúng trong HTML |

Đính kèm báo cáo PDF:

~~~java
helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

Nhúng logo vào HTML:

~~~java
helper.setText(
        "<html><body>"
                + "<p>Xin chào!</p>"
                + "<img src='cid:companyLogo' alt='Logo'/>"
                + "</body></html>",
        true);

helper.addInline(
        "companyLogo",
        new ByteArrayResource(logoPngBytes),
        "image/png");
~~~

Trong ví dụ HTML, `companyLogo` là **Content-ID reference**, không phải filename đính kèm. Một số mail clients vẫn có thể hiển thị inline resources dưới mục attachment, nhưng semantics gửi đi khác nhau.

### Thứ tự setText và addInline

Với HTML nhúng CID, nên gọi `setText(...)` trước `addInline(...)` để tránh các vấn đề tương thích ở một số email clients. Còn với file người dùng cần tải, dùng `addAttachment(...)` tường minh.

## 19. Không tự chỉnh Content-Disposition bằng header string thô

Đôi khi developer thấy filename không đúng rồi thử sửa bằng:

~~~java
// Không khuyến nghị như giải pháp mặc định:
bodyPart.setHeader(
        "Content-Disposition",
        "attachment; filename=" + userProvidedName);
~~~

Rủi ro:

- Tên chứa dấu nháy kép, dấu chấm phẩy hoặc Unicode có thể cần encoding.
- Đưa dữ liệu không tin cậy vào raw header có thể tạo vấn đề an toàn.
- Header có thể bị ghi đè hoặc trở nên không nhất quán với `Content-Type`.
- Logic MIME thủ công khó kiểm thử giữa nhiều clients.

`MimeMessageHelper.addAttachment(filename, source, contentType)` đã cung cấp đúng tầng abstraction để ứng dụng truyền tên, content type và dữ liệu. Chỉ can thiệp raw MIME headers khi có yêu cầu tương thích cụ thể, hiểu chuẩn MIME và có test trên mail clients đích.

### Nếu client hiển thị “noname”

Đừng vội thêm một header bất kỳ. Hãy kiểm tra MIME thực tế:

1. Có attachment part hay không?
2. `Content-Disposition` có `attachment` và filename không?
3. `Content-Type` có type đúng và name parameter nếu có không?
4. Filename có được mã hóa/giải mã chính xác không?
5. File có byte thực và nội dung đúng không?
6. Gateway/client có sửa header hoặc tách file không?

Một tên không đúng trong Outlook nhưng đúng trong Thunderbird có thể là vấn đề tương thích MIME/filename parameters, không nhất thiết do `ByteArrayResource`. Cần phân biệt bằng cách kiểm tra MIME trước khi gửi và mail nhận được.

## 20. Nguồn byte phải còn hợp lệ khi email được serialize

`MimeMessageHelper.addAttachment(...)` không có nghĩa toàn bộ dữ liệu đã được chuyển ngay vào một email byte array hoàn chỉnh tại thời điểm gọi. Việc thực sự serialize MIME có thể diễn ra muộn hơn, trong `mailSender.send(...)` hoặc khi `message.writeTo(...)`.

Với `ByteArrayResource`, dữ liệu được giữ trong mảng byte và mỗi lần `getInputStream()` có thể trả một stream mới. Đó là một lý do khiến nó phù hợp cho attachment trong bộ nhớ.

### Không sửa mảng byte khi worker khác đang gửi

Sai về mặt ownership dữ liệu:

~~~java
byte[] sharedBuffer = pdfGenerator.generate(invoice);
ByteArrayResource resource =
        new ByteArrayResource(sharedBuffer);

helper.addAttachment("invoice.pdf", resource, "application/pdf");

// Một thread khác có thể sửa sharedBuffer trước khi MIME được đọc.
java.util.Arrays.fill(sharedBuffer, (byte) 0);

mailSender.send(message);
~~~

`ByteArrayResource` không phải cơ chế immutable deep-copy bytes. Nó có thể giữ tham chiếu tới mảng được cung cấp. Nếu bytes có thể bị nơi khác sửa, cần thiết kế ownership ổn định hoặc sao chép:

~~~java
byte[] stableBytes = java.util.Arrays.copyOf(
        generatedBytes, generatedBytes.length);

ByteArrayResource resource =
        new ByteArrayResource(stableBytes);
~~~

Sao chép giúp cô lập nội dung nhưng **tăng chi phí bộ nhớ**. Với dữ liệu lớn hoặc throughput cao, nên chọn storage/streaming design phù hợp thay vì copy nhiều lần.

### Attachment là dữ liệu có vòng đời

Nếu một job nằm trong outbox nhiều giờ, đừng đặt một `ByteArrayResource` trong biến RAM rồi hy vọng nó tồn tại qua process restart. Lưu file/payload vào kho bền vững được bảo vệ; khi đến lượt gửi, worker tải dữ liệu và tạo Resource mới. Chỉ ghi vào outbox payload reference/version, không lưu Java object.

## 21. Đọc nhiều lần: ByteArrayResource khác InputStreamResource

Một nguồn phù hợp với mail attachment nên có thể trả một stream **mới, đọc được từ đầu** khi bên gửi yêu cầu:

~~~java
ByteArrayResource resource =
        new ByteArrayResource(pdfBytes);

try (var first = resource.getInputStream();
     var second = resource.getInputStream()) {
    // Hai streams độc lập đều đọc từ đầu mảng byte.
}
~~~

Nếu dùng một stream một lần:

~~~java
InputStreamResource oneShot =
        new InputStreamResource(
                new java.io.ByteArrayInputStream(pdfBytes));
~~~

thì phần MIME có thể yêu cầu stream nhiều lần để đo/serialize nội dung. `InputStreamResource` thường không cho phép đọc lại như vậy, và helper có thể từ chối nguồn đang mở.

Giải pháp:

- Dữ liệu nhỏ: `ByteArrayResource`.
- Tệp trên đĩa: `FileSystemResource`.
- Object storage: `InputStreamSource` với `getInputStream()` mở **luồng mới mỗi lần**, cùng một payload version.

Một custom stream source cần bảo đảm **nội dung không bị thay đổi giữa các lần mở**. Nếu object ở storage có thể bị overwrite, lần read lại có thể là file khác với lần đầu.

## 22. Dung lượng attachment: ByteArrayResource không thích hợp cho mọi file

Ví dụ một PDF 20 MiB:

~~~text
PDF bytes in byte[]             ~20 MiB
Potential render/copy buffers   additional memory
MIME Base64 representation      roughly 4/3 payload + line overhead
Concurrent sends               multiplied by active jobs
~~~

Số liệu trên chỉ là ước lượng đơn giản; mức sử dụng heap thực sự phụ thuộc implementation, có copy hay không, việc serialize/stream và GC. Không lấy đúng 4/3 làm tổng memory footprint của một email.

Khi 100 workers cùng giữ file 20 MiB:

\[
100 \times 20\text{ MiB} = 2000\text{ MiB}
\]

chỉ riêng các byte gốc đã khoảng 2 GiB, chưa tính MIME objects, copies và buffer khác.

Các lựa chọn:

1. Giảm concurrency đối với attachment lớn.
2. Không tải tất cả jobs/attachment vào RAM trước khi có SMTP slot.
3. Kiểm tra file size và provider message-size limits.
4. Dùng file-backed `Resource` hoặc storage stream có thể mở lại khi phù hợp.
5. Dùng link tải qua storage được bảo vệ nếu chính sách sản phẩm cho phép, thay vì đính kèm file quá lớn.

**Giới hạn kích thước provider có thể tính theo MIME encoded bytes**, không chỉ `byte[].length`. Vì vậy file 20 MiB có thể tạo message lớn đáng kể hơn 20 MiB.

## 23. Đừng để lỗi tên attachment thành SMTP retry storm

Trong hệ thống production, trình tự tốt:

~~~text
Mail job due
    |
    v
Load payload and choose filename
    |
    v
Validate filename / MIME type / content
    |
    +-- Invalid -> PREPARATION_FAILED
    |             audit + remediation
    |
    v
Acquire provider quota/concurrency permit
    |
    v
Submit via JavaMailSender
    |
    v
Classify SMTP outcome
~~~

Đặt tên file sai là **lỗi chuẩn bị message**, thường có tính quyết định:

~~~text
INVALID_ATTACHMENT_FILENAME
EMPTY_ATTACHMENT_PAYLOAD
ATTACHMENT_CONTENT_TYPE_MISMATCH
ATTACHMENT_TOO_LARGE
~~~

Không retry liên tục cùng input vì sẽ luôn cho cùng lỗi. Nếu sau này sửa dữ liệu/template/filename, có thể thực hiện replay một cách có kiểm soát.

### Nên validate trước khi xin quota

Nếu biết chắc attachment filename rỗng hoặc payload không tồn tại, đừng tiêu token rate limiter rồi mới để helper ném exception. Preflight:

- Filename hợp lệ, extension đúng.
- Payload có thể truy xuất.
- Attachment size dưới giới hạn sản phẩm/provider.
- MIME type phù hợp với định dạng thực.
- Người nhận và sender được phép.

Tuy vậy, việc dựng MIME trước quota gate có thể tốn CPU/memory. Có thể làm preflight nhẹ trước admission và serialize đầy đủ **gần lúc gửi**, với cơ chế quản lý permit theo policy.

## 24. Unit test: chứng minh getFilename() không có tên

Trước khi sửa lỗi, có thể viết test tái hiện giả định sai bằng JUnit 5 và AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;

class ByteArrayResourceFilenameTest {

    @Test
    void plainByteArrayResourceDoesNotHaveFilename() {
        ByteArrayResource resource =
                new ByteArrayResource(
                        "test-data".getBytes(StandardCharsets.UTF_8));

        assertThat(resource.getFilename()).isNull();
        assertThat(resource.contentLength()).isEqualTo(9);
    }

    @Test
    void descriptionDoesNotBecomeFilename() {
        ByteArrayResource resource =
                new ByteArrayResource(
                        new byte[] {1, 2, 3},
                        "report.pdf");

        assertThat(resource.getDescription())
                .contains("report.pdf");
        assertThat(resource.getFilename()).isNull();
    }
}
~~~

Test thứ hai giải thích rõ constructor hai tham số chỉ truyền description.

### Test lỗi addAttachment với null filename

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

class InvalidAttachmentNameTest {

    @Test
    void cannotUseByteArrayResourceFilenameAsAttachmentName()
            throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        MimeMessageHelper helper = new MimeMessageHelper(
                sender.createMimeMessage(), true, "UTF-8");

        ByteArrayResource resource =
                new ByteArrayResource(new byte[] {1, 2, 3});

        assertThatThrownBy(
                () -> helper.addAttachment(
                        resource.getFilename(), resource))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Lỗi cụ thể và nội dung message có thể khác theo phiên bản Spring, nên test tập trung vào contract filename không hợp lệ thay vì assert nguyên văn tiếng Anh của exception. Không có lệnh SMTP nào được gọi trong test.

## 25. Unit test: kiểm tra tên và byte đính kèm thực tế

Không nhất thiết gửi email thật để kiểm tra MIME attachment. `JavaMailSenderImpl.createMimeMessage()` có thể tạo một `MimeMessage` tại chỗ. Sau khi `MimeMessageHelper` cấu hình, dùng Jakarta Mail đọc lại các phần MIME.

Ví dụ kiểm tra filename ASCII, Content-Type và byte payload:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

class MailAttachmentMimeTest {

    @Test
    void attachmentHasExpectedFilenameAndContent()
            throws Exception {
        byte[] data = "a,b\r\n1,2\r\n"
                .getBytes(StandardCharsets.UTF_8);

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("sender@example.test");
        helper.setTo("recipient@example.test");
        helper.setSubject("Báo cáo");
        helper.setText("Đính kèm báo cáo CSV.", false);

        helper.addAttachment(
                "report-2026-11.csv",
                new ByteArrayResource(data),
                "text/csv; charset=UTF-8");

        mime.saveChanges();
        Multipart content = (Multipart) mime.getContent();
        BodyPart attachment = findAttachment(content);

        assertThat(attachment).isNotNull();
        assertThat(attachment.getFileName())
                .isEqualTo("report-2026-11.csv");
        assertThat(attachment.isMimeType("text/csv")).isTrue();

        try (InputStream input = attachment.getInputStream()) {
            assertThat(input.readAllBytes())
                    .containsExactly(data);
        }
    }

    private static BodyPart findAttachment(Multipart multipart)
            throws Exception {
        for (int index = 0;
                index < multipart.getCount();
                index++) {

            BodyPart part = multipart.getBodyPart(index);
            if (Part.ATTACHMENT.equalsIgnoreCase(
                    part.getDisposition())) {
                return part;
            }

            Object child = part.getContent();
            if (child instanceof Multipart nested) {
                BodyPart found = findAttachment(nested);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }
}
~~~

Trong `MimeMessageHelper` có các multipart modes khác nhau, nên test **đệ quy qua multipart lồng nhau** thay vì luôn giả định attachment nằm ở `getBodyPart(1)`. Phần body text và inline images có thể thay đổi cấu trúc MIME.

### Test này xác minh gì?

- Attachment part tồn tại.
- Filename do helper đặt là đúng.
- Content type có ngữ nghĩa `text/csv`.
- Payload trả về bằng đúng bytes đã đưa vào.
- Có thể thực hiện hoàn toàn trong memory, không cần credential SMTP và không gửi thư thật.

Test này không chứng minh một email client cụ thể sẽ đặt tên 100% giống nhau hoặc không có gateway rewrite. Với Unicode hoặc filename cực dài, còn cần integration test phù hợp.

## 26. Inspect raw MIME để tìm lỗi header

Khi cần xác định lỗi nằm ở Spring helper hay mail client, có thể serialize một **email test với nội dung giả**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

mimeMessage.saveChanges();
ByteArrayOutputStream raw = new ByteArrayOutputStream();
mimeMessage.writeTo(raw);

String mimeText = raw.toString(
        StandardCharsets.ISO_8859_1);
System.out.println(mimeText);
~~~

Từ đó kiểm tra:

~~~text
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="..."

--...
Content-Type: text/plain; charset=UTF-8

...
--...
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

...
~~~

Đây là **mô phỏng**; header order, boundary, encoding và MIME nesting không nhất thiết đúng từng dòng trên mọi Jakarta Mail version.

### Không in raw MIME của email khách hàng

Đoạn `System.out.println(mimeText)` chỉ phù hợp với **test fixture giả**. Raw MIME chứa body, recipient, attachment và thông tin nhạy cảm; không được log nguyên MIME trong production để “kiểm tra tên file”.

Production observability nên ghi:

~~~text
event=mail_attachment_prepared
mailJobId=opaque-job-583
attachmentType=INVOICE_PDF
fileExtension=pdf
sizeBytes=16384
filenameValidation=PASSED
~~~

Nếu cần điều tra một message thật, dùng quy trình access-controlled diagnostic, masking và retention ngắn.

## 27. Integration test với SMTP sink

Sau khi unit test MIME, nên có integration test bằng một SMTP sink/test server như Mailpit hoặc GreenMail, tránh gửi tới người nhận thật.

Luồng:

~~~text
Spring Mail service
    |
    v
JavaMailSender configured for SMTP sink
    |
    v
SMTP sink receives message
    |
    v
Read saved message's MIME parts
    |
    +-- Content-Disposition: attachment
    +-- Filename: report-2026-11.pdf
    +-- Content-Type: application/pdf
    +-- Bytes: expected fixture
~~~

Những kịch bản:

| Kịch bản | Kết quả mong đợi |
|---|---|
| ByteArrayResource + filename đúng | Attachment hiện tên đúng |
| ByteArrayResource + getFilename() | Bị chặn ở bước dựng MIME |
| Filename thiếu extension | Phát hiện metadata không đạt contract nghiệp vụ |
| PDF bytes với MIME PDF | MIME part đúng loại và byte |
| Tên Unicode hợp lệ | Đọc lại filename theo khả năng Jakarta Mail/client đích |
| Nhiều attachment | Mỗi part có tên đúng, không lẫn bytes |
| HTML + inline logo + PDF attachment | Inline và attachment có semantics khác nhau |
| Tệp lớn | Kiểm tra max size/memory/transport |
| Server trả lỗi SMTP | Không phân loại thành lỗi filename |
| Job retry | Mỗi attempt dựng MIME với filename/content version dự kiến |

SMTP sink cho phép kiểm tra email thực sự được submit dưới dạng MIME mà không gây spam ngoài hệ thống. Tuy nhiên nó không mô phỏng toàn bộ hành vi của Gmail, Outlook hoặc các gateway doanh nghiệp; với yêu cầu tương thích đặc biệt, cần kiểm tra trên các clients mục tiêu bằng tài khoản thử nghiệm.

## 28. Tên trùng giữa nhiều attachments trong một email

Nếu một message đính kèm hai báo cáo:

~~~java
helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(firstPdf),
        "application/pdf");

helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(secondPdf),
        "application/pdf");
~~~

thì cả hai MIME parts có thể mang **cùng tên hiển thị**. Không có gì đảm bảo mail client tự tạo tên dễ hiểu; khi tải về, người dùng có thể thấy `report (1).pdf`, overwrite warning hoặc các hành vi khác nhau.

Thay vì phụ thuộc client tự giải quyết:

~~~java
helper.addAttachment(
        "invoice-INV-583.pdf",
        new ByteArrayResource(firstPdf),
        "application/pdf");

helper.addAttachment(
        "payment-receipt-INV-583.pdf",
        new ByteArrayResource(secondPdf),
        "application/pdf");
~~~

Chọn tên có ngữ nghĩa theo từng attachment. Khi có nhiều phiên bản của cùng file, thêm version/date hoặc reference đã kiểm soát.

### Không dùng raw file path để tránh trùng

Không nên tạo tên `/tmp/report-1234.pdf` hoặc một tên chứa full object storage key. Tính duy nhất của filename trong email nên dựa vào ID nghiệp vụ an toàn, không làm lộ cấu trúc server.

## 29. Nếu dùng custom Multipart hoặc DataSource thay vì ByteArrayResource

`MimeMessageHelper` cũng có các overload sử dụng `DataSource` hoặc `File` tùy API. Những lựa chọn này vẫn có khái niệm filename cho MIME.

Ví dụ với `ByteArrayDataSource` của Jakarta Mail implementation:

~~~java
import jakarta.mail.util.ByteArrayDataSource;

ByteArrayDataSource dataSource =
        new ByteArrayDataSource(
                pdfBytes, "application/pdf");

helper.addAttachment(
        "invoice-583.pdf",
        dataSource);
~~~

DataSource cung cấp dữ liệu và content type; **tên hiển thị của MIME attachment vẫn được truyền rõ trong addAttachment**. Nếu tự tạo body part không qua helper, người viết phải tự xử lý Content-Disposition, filename encoding và vòng đời dữ liệu cẩn thận hơn.

### Đừng nhầm DataSource.getName() với tên mong muốn

Tên do DataSource tự mô tả có thể không phải filename cho người nhận. Khi dùng `MimeMessageHelper.addAttachment(attachmentFilename, dataSource)`, lập trình viên vẫn cần chọn filename rõ ràng phù hợp với nội dung.

## 30. Tách lỗi nội dung, tên file và lỗi gửi SMTP

Một pipeline gửi mail đủ rõ sẽ chia thành các phase:

~~~text
1. Resolve business record
2. Generate attachment bytes
3. Determine filename + content type
4. Validate attachment size and policy
5. Compose MimeMessage
6. Submit SMTP
7. Persist submission outcome
~~~

Các mã lỗi nội bộ có thể là:

| Phase | Mã nội bộ gợi ý | Có retry SMTP ngay? |
|---|---|---|
| Resolve | `BUSINESS_DATA_MISSING` | Không; cần dữ liệu hợp lệ |
| Generate | `PDF_GENERATION_FAILED` | Tùy nguyên nhân generator |
| Filename | `INVALID_ATTACHMENT_FILENAME` | Không; sửa tên |
| Payload | `EMPTY_ATTACHMENT` | Không; kiểm tra nguồn |
| Size | `ATTACHMENT_EXCEEDS_LIMIT` | Không; giảm/chuyển phương thức gửi |
| MIME composition | `MIME_PREPARATION_FAILED` | Cần phân loại rõ nguyên nhân |
| SMTP auth | `SMTP_AUTH_FAILED` | Không retry nóng với cùng credential |
| SMTP temp reject | `SMTP_TEMPORARY_REJECTION` | Có thể retry với backoff |
| Network ambiguous | `SMTP_OUTCOME_UNKNOWN` | Không retry mù |
| Accepted | `SMTP_SUBMITTED` | Không gửi lại chỉ vì chưa có delivery event |

Lỗi filename là lỗi **trước submission**, không nên bị đếm như một SMTP provider throttle hoặc chiếm số lần retry của hệ thống mail transport.

## 31. Bảng chẩn đoán nhanh khi attachment không hiện đúng tên

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra | Hướng sửa |
|---|---|---|---|
| `attachmentFilename must not be null` hoặc lỗi argument tương đương | Dùng `ByteArrayResource.getFilename()` | In/inspect giá trị filename **trong test** | Truyền tên tường minh cho `addAttachment` |
| Constructor `ByteArrayResource(bytes, name)` vẫn không có filename | `name` là description | Test `getFilename()` | Không dùng description làm filename |
| Tệp hiển thị `noname` | MIME part thiếu/khó đọc filename | Inspect `Content-Disposition` | Truyền tên hợp lệ, kiểm tra encoding/header |
| Tệp chỉ có tên `report` | Không có extension | Xem tham số addAttachment | Dùng `report.pdf`/`report.csv` |
| Tệp có tên `report.pdf.txt` | Ghép extension hai lần | Inspect filename builder | Quản lý extension một lần từ format |
| Tên trùng ở nhiều attachments | Các part dùng cùng filename | Inspect tất cả MIME parts | Thêm reference/version |
| PDF được báo “file không hợp lệ” | Bytes không phải PDF hoặc bị cắt | Test content bytes/size | Sửa generator/stream, không chỉ filename |
| Ứng dụng mở bằng chương trình sai | Extension/content type mismatch | Kiểm tra tên, type và content | Đồng bộ cả ba |
| Tên tiếng Việt bị lỗi dấu | Header encoding hoặc mail client compatibility | Test raw MIME và nhiều clients | Charset/encoding policy, cân nhắc ASCII |
| Attachment không thấy ở client | Inline thay vì attachment | Kiểm tra disposition | Dùng `addAttachment` cho file tải |
| Lỗi `Resource is already open` hoặc không đọc được stream lần hai | Dùng `InputStreamResource` | Kiểm tra `isOpen`/repeatability | Dùng ByteArrayResource hoặc stream source mở mới |
| Email gửi được nhưng attachment rỗng | Byte[] không có dữ liệu hoặc source fail | Unit test payload length/readback | Validate bytes trước compose |
| Mail có file đúng tên trong sink nhưng client đổi tên | Gateway/client rewrite | So sánh MIME trước/sau provider | Điều tra policy/client tương thích |
| Một số emails lỗi còn emails khác bình thường | Filename động chứa dữ liệu không hợp lệ | Ghi reason code, xem builder | Sanitize/validate input |
| Máy chủ hết heap khi gửi nhiều PDF | ByteArrayResource giữ nhiều byte[] | Heap/GC metrics | Bounded concurrency, file-backed resources |

### Đừng sửa sai tầng

Nếu stack trace cho thấy `IllegalArgumentException` tại `MimeMessageHelper.addAttachment(...)`, việc tăng SMTP timeout hoặc đổi password không giải quyết được. Ngược lại, nếu MIME test đã pass nhưng SMTP trả `AuthenticationFailedException`, việc sửa filename cũng không giải quyết lỗi đăng nhập.

Luôn tìm **giai đoạn đầu tiên xảy ra lỗi** trước khi thay đổi cấu hình.

## 32. Đặt filename động trong hệ thống có retry/outbox

Một hệ thống production có thể tạo email job trong database rồi gửi sau nhiều phút:

~~~text
Order created
     |
     v
Outbox mail job
  invoiceId = INV-583
  payloadVersion = 2
  attachmentKind = INVOICE_PDF
     |
     v
Worker loads payload
     |
     v
Filename builder
  invoice-INV-583.pdf
     |
     v
ByteArrayResource + addAttachment
     |
     v
SMTP submission
~~~

Tốt hơn là lưu:

~~~json
{
  "mailJobId": "opaque-id-583",
  "attachmentKind": "INVOICE_PDF",
  "businessRef": "INV-583",
  "payloadVersion": 2
}
~~~

thay vì lưu toàn bộ byte[] hoặc một Java Resource instance trong RAM. Worker tự xác định tên theo policy khi gửi, và có thể ghi **filename version** để bảo đảm các lần retry dùng metadata ổn định nếu cần.

### Có nên đặt lại tên giữa các lần retry?

Nếu cùng một intent gửi hóa đơn đã phát hành, nên giữ **tên và nội dung nhất quán** giữa các lần thử:

~~~text
Attempt 1: invoice-INV-583.pdf
Attempt 2: invoice-INV-583.pdf
~~~

Nếu đổi tên thành `invoice-final-v7.pdf` trong lần retry thứ hai chỉ vì template đã được cập nhật, người nhận có thể nhận hai phiên bản khác nhau khi outcome attempt đầu còn không rõ. Cần chính sách snapshot/versioning của payload và filename.

### Không tạo duplicate intent chỉ vì sửa tên

Nếu job trước đó có lỗi filename trước SMTP submission, có thể sửa generator rồi replay theo cơ chế có kiểm soát. Không cần tạo nhiều email jobs mới cho cùng business event mà không có idempotency key. Dùng status `PREPARATION_FAILED` hoặc reason code tương đương để phân biệt với SMTP rejected.

## 33. Filename và quyền riêng tư

Tên attachment có thể làm lộ:

- Họ tên khách hàng.
- Số hóa đơn hoặc mã hợp đồng có tính định danh.
- Địa chỉ email/điện thoại.
- Mã bệnh nhân, tài khoản ngân hàng hoặc thông tin khác.
- Tên nội bộ dự án hoặc đường dẫn file server.

Ngay cả email được gửi đúng người nhận, file có thể được tải, forward hoặc lưu ở máy khác. Một tên như:

~~~text
medical-records-john-doe-2026.pdf
~~~

có thể không phù hợp với chính sách tối thiểu hóa dữ liệu, trong khi:

~~~text
document-INV-583.pdf
~~~

có thể đủ cho trải nghiệm người dùng nếu `INV-583` là mã không nhạy cảm. Điều này phụ thuộc nghiệp vụ; tránh đưa thông tin định danh thừa vào filename.

### Khác biệt giữa đường dẫn lưu trữ và tên tải xuống

~~~text
Internal object key:
  tenants/42/private/invoices/INV-583/pdf/v2/7c31a...

Public attachment filename:
  invoice-INV-583.pdf
~~~

Không dùng object key làm filename vì có thể tiết lộ cấu trúc storage và tenant ID. Hãy tách display name khỏi storage reference.

### Kiểm soát tên do người dùng đặt

Nếu cho phép khách hàng tự chọn tên:

1. Kiểm tra quyền sử dụng tài liệu.
2. Xác minh format/mime type.
3. Giới hạn length và ký tự gây lỗi.
4. Loại bỏ hoặc từ chối control characters và path separators.
5. Kiểm tra policy về PII và nội dung nhạy cảm.
6. Không ghi raw name vào metrics label.
7. Dùng tên lưu trữ độc lập, không tạo file path từ tên này.

## 34. Có nên đặt MIME type thành application/octet-stream?

`application/octet-stream` biểu thị dữ liệu nhị phân chung. Với một file định dạng không biết rõ, đây có thể là fallback hợp lý. Nhưng nếu chắc chắn có PDF:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

rõ ràng hơn:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/octet-stream");
~~~

về mặt semantics nội dung.

Tuy nhiên, **đừng dùng MIME type để lừa mail client**. Nếu bytes là file thực thi hoặc nội dung nguy hiểm, đổi tên thành `invoice.pdf` và khai báo `application/pdf` không làm nó trở thành PDF an toàn. Gateway có thể kiểm tra payload và quarantine.

### Content-Type không phải phép xác thực file

Đối với file do hệ thống tự tạo từ thư viện đã kiểm soát, type thường được biết từ generator. Với file upload từ nguồn không tin cậy, phải có kiểm tra định dạng và bảo mật riêng: signature/magic number, thư viện parse an toàn, antivirus policy, file-size limits và authorization. Đừng chỉ tin extension hoặc HTTP upload Content-Type.

## 35. Dùng dữ liệu attachment qua HTTP response và email khác nhau ra sao?

Một API download thường đặt:

~~~http
Content-Disposition: attachment; filename="invoice.pdf"
Content-Type: application/pdf
~~~

trong **HTTP response headers**. Khi gửi email, `MimeMessageHelper.addAttachment(...)` tạo **MIME body part headers** có ngữ nghĩa liên quan nhưng không phải cùng API.

Đừng copy nguyên:

~~~java
response.setHeader(
        "Content-Disposition",
        "attachment; filename=invoice.pdf");
~~~

vào một controller rồi cho rằng email cũng tự có attachment. HTTP header trên response không sửa `MimeMessage` được gửi qua SMTP.

Tương tự, `ByteArrayResource` trong một HTTP `ResponseEntity<Resource>` có thể cần cách cung cấp filename qua HTTP headers; `ByteArrayResource.getFilename()` không thay đổi vì dùng ở web layer. Tên file cần được đặt tường minh ở **tầng đang tạo output metadata**.

## 36. Một helper tiện dụng cho attachment từ byte[]

Trong ứng dụng có nhiều định dạng xuất file, có thể gom logic validation và addAttachment:

~~~java
import jakarta.mail.MessagingException;
import java.util.Objects;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MailAttachmentSupport {
    private MailAttachmentSupport() {
    }

    public static void addBytes(
            MimeMessageHelper helper,
            String filename,
            String contentType,
            byte[] bytes) throws MessagingException {

        Objects.requireNonNull(helper, "helper");
        Objects.requireNonNull(bytes, "bytes");

        if (bytes.length == 0) {
            throw new IllegalArgumentException(
                    "Attachment must not be empty");
        }
        if (filename == null
                || filename.isBlank()
                || filename.contains("/")
                || filename.contains("\\")
                || filename.indexOf((char) 13) >= 0
                || filename.indexOf((char) 10) >= 0) {
            throw new IllegalArgumentException(
                    "Invalid attachment filename");
        }
        if (contentType == null || contentType.isBlank()) {
            throw new IllegalArgumentException(
                    "Attachment content type is required");
        }

        helper.addAttachment(
                filename,
                new ByteArrayResource(bytes),
                contentType);
    }
}
~~~

Ví dụ sử dụng:

~~~java
MailAttachmentSupport.addBytes(
        helper,
        "invoice-INV-583.pdf",
        "application/pdf",
        pdfBytes);
~~~

**Giới hạn của helper này:** nó chỉ minh họa contract cơ bản. Trong production cần thêm max bytes, allowlist extensions/content types, giới hạn chiều dài tên, lọc ký tự điều khiển Unicode, các tên đặc biệt trên hệ điều hành và kiểm tra loại nội dung thực. Một filename trông hợp lệ không có nghĩa bytes là PDF đúng chuẩn hoặc đã qua security scanning.

### Vì sao nên dùng helper?

Khi nhiều services cùng gửi attachment, việc tập trung logic giúp tránh người viết tiếp theo lại dùng:

~~~java
helper.addAttachment(
        byteArrayResource.getFilename(),
        byteArrayResource);
~~~

Helper cũng tạo một vị trí thống nhất để sửa MIME policy/charset hoặc kích thước file mà không phải thay ở hàng chục email templates.

## 37. Quy trình xử lý sự cố khi người dùng báo sai tên file

Giả sử khách hàng nhận email hóa đơn nhưng attachment tên `noname`, `attachment` hoặc `invoice.pdf.txt`.

**Không bắt đầu bằng việc gửi lại hàng loạt email.** Trước tiên, xác định lỗi xảy ra trước SMTP, trong MIME output hay tại mail client.

~~~mermaid
flowchart TD
    A[Tên attachment bị sai] --> B{Email đã được submit thành công?}
    B -- Không --> C[Kiểm tra lỗi khi tạo MimeMessage]
    C --> D{ByteArrayResource.getFilename null?}
    D -- Có --> E[Truyền explicit filename vào addAttachment]
    D -- Không --> F[Kiểm tra validation/content type/multipart]
    B -- Có --> G[Kiểm tra MIME test/sink]
    G --> H{MIME part có filename đúng?}
    H -- Không --> I[Sửa filename builder/header encoding]
    H -- Có --> J[So sánh mail client/gateway]
    J --> K[Kiểm tra Unicode, MIME rewrite, security policy]
~~~

### Bước 1. Xem đoạn code tạo attachment

Tìm pattern:

~~~java
new ByteArrayResource(...)
resource.getFilename()
helper.addAttachment(...)
~~~

Đặc biệt chú ý:

~~~java
ByteArrayResource resource =
        new ByteArrayResource(bytes, "report.pdf");
helper.addAttachment(resource.getFilename(), resource);
~~~

Tên trong constructor hai tham số là description, không tự trở thành filename.

### Bước 2. Xác định metadata ứng dụng mong muốn

Ví dụ:

~~~text
documentKind = INVOICE_PDF
safeReference = INV-583
desiredFilename = invoice-INV-583.pdf
desiredMimeType = application/pdf
payloadSize = 32768 bytes
~~~

Tất cả là dữ liệu giả trong hướng dẫn. Đừng lấy tên file trực tiếp từ request user hoặc từ storage key dài.

### Bước 3. Tái hiện trong unit test

Không cần credential thật hoặc kết nối Internet. Dùng `JavaMailSenderImpl.createMimeMessage()` và `MimeMessageHelper` để tạo fixture, rồi assert `BodyPart.getFileName()`, `isMimeType(...)` và stream bytes.

Nếu test MIME thất bại, sửa application code trước khi điều tra provider.

### Bước 4. Kiểm tra SMTP sink

Nếu unit test đúng nhưng thư nhận qua sink sai, so sánh kết quả dựng MIME và bản được sink nhận. Có thể có code sửa header/attachment trên đường gửi.

### Bước 5. So sánh client đích

Nếu MIME ở sink đúng, gửi thử email giả đến các mail clients mục tiêu để xem vấn đề về Unicode/filename encoding hoặc chính sách gateway. Chỉ thử trong phạm vi được cho phép và không dùng email chứa dữ liệu thật.

### Bước 6. Xử lý mail jobs đã lỗi

Nếu email **chưa được gửi** vì lỗi filename, có thể sửa cấu hình rồi replay job theo cơ chế được phê duyệt. Nếu provider **đã accepted**, không resend hàng loạt chỉ vì một khách hàng báo tên hiển thị lạ; phải xét nguy cơ email trùng, nội dung nhạy cảm và chiến lược support.

## 38. Những anti-pattern cần tránh

### 38.1. Dùng Resource.getFilename() cho mọi loại Resource

~~~java
helper.addAttachment(resource.getFilename(), resource);
~~~

`ByteArrayResource`, custom `InputStreamSource` hoặc những resource không gắn file path có thể không có filename. Khi tạo attachment, chọn tên rõ ràng ở application layer.

### 38.2. Nhầm ByteArrayResource description là filename

~~~java
new ByteArrayResource(bytes, "invoice.pdf");
~~~

Không đặt được filename chỉ bằng constructor này. `addAttachment("invoice.pdf", resource)` vẫn là lời gọi cần thiết.

### 38.3. Chọn đuôi .pdf cho mọi attachment

Tệp có byte CSV hoặc XLSX không trở thành PDF khi đổi tên. Đuôi, MIME type và byte format cần nhất quán.

### 38.4. Để trống filename vì nghĩ mail client tự đặt

Tên rỗng/null có thể bị helper từ chối hoặc hiển thị khó hiểu. Hãy yêu cầu filename hợp lệ và có extension phù hợp.

### 38.5. Lấy đường dẫn filesystem làm tên tải xuống

~~~text
C:\\internal\\temp\\invoice.pdf
/srv/app/private/tenant-42/invoice.pdf
~~~

Path nội bộ có thể lộ thông tin hệ thống; chỉ dùng basename được kiểm soát.

### 38.6. Gửi trực tiếp tên file từ request không validate

Tên có ký tự điều khiển, `../` hoặc chuỗi nhạy cảm cần bị kiểm tra hoặc thay bằng tên server-side.

### 38.7. Dùng addInline thay addAttachment

`addInline(...)` dùng cho nội dung nhúng Content-ID, không phải attachment thông thường để tải.

### 38.8. Tự ghi raw MIME headers từ chuỗi untrusted

Filename có quy tắc quoting và encoding. `MimeMessageHelper` là API thích hợp hơn khi không có yêu cầu MIME đặc biệt.

### 38.9. Dùng InputStreamResource cho stream chỉ đọc được một lần

Serialization có thể cần mở lại stream. Với byte[] dùng `ByteArrayResource`; với file lớn dùng nguồn trả stream mới.

### 38.10. Làm rỗng hoặc chỉnh byte[] trước khi send

`ByteArrayResource` giữ byte[] để đọc về sau; nếu buffer bị sửa giữa chừng, attachment có thể sai nội dung.

### 38.11. Tạo hàng nghìn ByteArrayResource lớn cùng lúc

Gây tăng heap và GC, đặc biệt khi MIME/base64 có buffering. Áp giới hạn size/concurrency, dùng file-backed storage khi phù hợp.

### 38.12. Retry SMTP khi addAttachment ném lỗi tham số

Đây thường là lỗi input/chuẩn bị thư, không phải provider unavailable. Retry không sửa được filename null.

### 38.13. Dùng application/octet-stream cho mọi định dạng mà không cân nhắc

Fallback chung có thể khiến client không nhận diện đúng file. Khi biết loại tài liệu, khai báo MIME type đúng.

### 38.14. Test chỉ kiểm tra mailSender.send đã được gọi

Một Mockito verify `send(...)` không chứng minh MIME part có filename chính xác. Cần kiểm tra `MimeMessage` được tạo và `BodyPart.getFileName()` trong test.

### 38.15. Giả định attachment luôn là MIME part thứ hai

Thư có HTML alternative, inline logo và nested multipart có thể thay đổi thứ tự. Tìm part theo disposition/filename, không hardcode index.

### 38.16. Kết luận lỗi do Spring chỉ vì Gmail/Outlook hiển thị khác

So sánh raw MIME trước và sau gateway. Vấn đề có thể nằm ở encoding, client policy hoặc gateway rewriting, không phải `ByteArrayResource`.

### 38.17. Log raw MIME để debug lỗi tên file

Raw MIME có thể chứa PII, attachment và secret; dùng test fixture giả và log metadata an toàn.

### 38.18. Dùng tên file độc nhất bằng email cá nhân của người nhận

Filename là dữ liệu hiển thị và có thể được forward. Dùng mã nghiệp vụ không nhạy cảm/opaque reference.

### 38.19. Tạo subclass chỉ để helper không cần filename

`MimeMessageHelper.addAttachment(...)` vẫn yêu cầu đối số filename. Subclass không cần thiết nếu application có thể truyền tên tường minh.

### 38.20. Coi filename đúng là bằng chứng attachment hợp lệ

Tên, content type và payload cần được kiểm tra riêng. Một `invoice.pdf` có nội dung rỗng/sai định dạng vẫn là attachment lỗi.

## 39. Bài tập thực hành

### Bài tập 1: sửa lỗi null filename

Code ban đầu:

~~~java
byte[] data = reportService.exportPdf(reportId);
ByteArrayResource source =
        new ByteArrayResource(data, "report.pdf");

helper.addAttachment(source.getFilename(), source);
~~~

Yêu cầu:

1. Giải thích vì sao `getFilename()` không trả `report.pdf`.
2. Sửa code để đính kèm tên `report-2026-11.pdf`.
3. Khai báo MIME type PDF.
4. Viết JUnit test kiểm tra filename.

Lời giải:

~~~java
byte[] data = reportService.exportPdf(reportId);
ByteArrayResource source = new ByteArrayResource(data);

helper.addAttachment(
        "report-2026-11.pdf",
        source,
        "application/pdf");
~~~

Lý do: constructor hai tham số đặt description, không phải filename; tên MIME phải do application chỉ định tại `addAttachment(...)`.

### Bài tập 2: phân biệt ba định dạng

Cho ba byte arrays do những generator chuyên biệt tạo:

~~~java
byte[] pdf = pdfService.generate();
byte[] csv = csvService.generate();
byte[] xlsx = xlsxService.generate();
~~~

Hãy gắn ba attachment với tên:

~~~text
monthly-report.pdf
monthly-data.csv
monthly-table.xlsx
~~~

và MIME type chính xác:

~~~java
helper.addAttachment(
        "monthly-report.pdf",
        new ByteArrayResource(pdf),
        "application/pdf");

helper.addAttachment(
        "monthly-data.csv",
        new ByteArrayResource(csv),
        "text/csv; charset=UTF-8");

helper.addAttachment(
        "monthly-table.xlsx",
        new ByteArrayResource(xlsx),
        "application/vnd.openxmlformats-officedocument."
                + "spreadsheetml.sheet");
~~~

Gợi ý mở rộng: test ba attachment bằng cách duyệt tất cả MIME parts, xác minh tên, type và byte payload, không dựa vào thứ tự part.

### Bài tập 3: filename từ dữ liệu không tin cậy

Giả sử request chứa:

~~~text
filename = "../../private/report.pdf"
~~~

Không dùng chuỗi đó trực tiếp trong email hay làm filesystem path. Hãy:

1. Xác định loại report được phép từ server-side business event.
2. Sinh một tên do server kiểm soát, ví dụ `report-REQ-583.pdf`.
3. Giới hạn format, length, MIME type và size.
4. Dùng một storage key độc lập với tên hiển thị.
5. Không log tên gốc hoặc path nhạy cảm ra metrics.

Lời giải nên phản ánh việc **chọn tên hợp lệ**, không chỉ xóa hai dấu chấm rồi tin mọi phần còn lại.

## 40. Câu hỏi thường gặp

**Vì sao `ByteArrayResource.getFilename()` lại trả về `null`?** Vì `ByteArrayResource` chỉ bọc dữ liệu byte trong bộ nhớ, không đại diện cho một file path. Nó không tự biết tên mà người nhận cần thấy. Hãy cung cấp filename qua `MimeMessageHelper.addAttachment(...)`.

**`ByteArrayResource(bytes, "report.pdf")` có đặt filename không?** Không. Tham số thứ hai là description cho `Resource`. `getFilename()` không tự được gán theo description.

**Tôi đã truyền `new ByteArrayResource(bytes)`, vì sao `addAttachment(...)` vẫn yêu cầu tên?** Đó là thiết kế API: nguồn dữ liệu và tên MIME attachment là hai thông tin tách biệt. Tên nằm ở đối số `attachmentFilename`.

**Câu lệnh sửa nhanh nhất là gì?** Dùng `helper.addAttachment("report.pdf", new ByteArrayResource(bytes), "application/pdf")`, nếu bytes thực sự là PDF và filename phù hợp nghiệp vụ.

**Có nên sửa `ByteArrayResource` bằng subclass để override `getFilename()` không?** Chỉ khi một luồng code khác thật sự cần Resource có tên. Với Spring Mail, truyền filename trực tiếp vào `addAttachment(...)` thường đơn giản và rõ hơn.

**Có thể truyền null filename và để mail client tự đặt không?** Không nên. Tên null thường bị API kiểm tra và là lỗi chuẩn bị MIME; tên hiển thị cần được xác định rõ từ ứng dụng.

**Nếu không có extension thì email vẫn gửi được không?** Có thể, tùy input và helper. Nhưng người nhận có thể khó mở file và content type detection có thể kém chính xác. Nên đặt extension đúng.

**Có cần truyền content type không?** Overload chỉ nhận filename và source thường có thể suy ra type từ tên. Với các định dạng cần đảm bảo, nên truyền type tường minh để tránh phụ thuộc MIME map.

**`application/octet-stream` có sai không?** Không phải lúc nào cũng sai; đó là type nhị phân chung. Nhưng nếu biết tệp là PDF/CSV/XLSX, type chuyên biệt giúp metadata chính xác hơn.

**Tôi dùng `filename="report.pdf"` nhưng người nhận vẫn thấy `report.txt`?** Kiểm tra Content-Type, Content-Disposition, MIME part thực, client/gateway rewriting và byte format. Có thể đoạn code khác sửa header sau `addAttachment(...)`.

**Tên tiếng Việt có dấu có được không?** Có thể, nhưng cần lưu ý MIME filename encoding và mức độ hỗ trợ giữa các clients. Tên ASCII an toàn là một lựa chọn tương thích khi không bắt buộc Unicode.

**`MimeMessageHelper.setEncodeFilenames(true)` có phải cách sửa tất cả tên Unicode lỗi?** Không. Nó liên quan tới cách mã hóa filename ở một số phiên bản/helper. Cần xét Jakarta Mail, MIME standards và mail clients đích; không có một lựa chọn bảo đảm mọi client.

**Có nên tự tạo header Content-Disposition?** Thường không. `MimeMessageHelper.addAttachment(...)` đã cung cấp API phù hợp. Chỉnh header thủ công dễ gặp lỗi quoting/Unicode/injection.

**`addInline(...)` khác `addAttachment(...)` như thế nào?** `addInline` phục vụ nội dung nhúng qua Content-ID, thường là ảnh HTML. `addAttachment` tạo phần đính kèm để tải.

**Tại sao `InputStreamResource` không được khuyến nghị?** Nó thường đại diện một stream đã mở và không bảo đảm đọc lại. MIME serialization có thể yêu cầu mở stream nhiều lần; `ByteArrayResource` hoặc nguồn có khả năng mở lại sẽ phù hợp hơn.

**Có thể dùng FileSystemResource thay ByteArrayResource không?** Có, khi file đã nằm trên filesystem và vòng đời file đủ lâu cho việc gửi. Vẫn nên chọn tên tải xuống tường minh, thay vì tiết lộ đường dẫn nội bộ.

**ByteArrayResource có copy byte[] không?** Không nên giả định nó deep-copy mảng truyền vào. Khi dữ liệu có thể bị sửa đồng thời, hãy đảm bảo ownership ổn định hoặc sao chép có chủ đích.

**Dùng ByteArrayResource cho PDF 100 MB có tốt không?** Cần cân nhắc. Mảng byte lớn và nhiều submissions đồng thời làm tăng heap/GC, trong khi MIME Base64 còn làm kích thước message lớn hơn. Nên đánh giá file-backed resource, quota, size limit hoặc link tải.

**Vì sao attachment rỗng dù tên đúng?** Có thể generator trả bytes rỗng, stream bị đọc hết hoặc bị cắt giữa chừng. Kiểm tra size và bytes trong unit test; sửa filename không thể tạo ra nội dung.

**Có thể đổi tên `.csv` thành `.xlsx` để Excel mở tốt hơn không?** Không. XLSX là một định dạng file riêng; đổi extension không chuyển nội dung CSV thành XLSX.

**Tại sao có hai file cùng tên trong email?** Ứng dụng có thể gọi `addAttachment(...)` hai lần với cùng filename. Nên sinh tên khác nhau theo document kind/reference, thay vì dựa vào mail client tự đổi tên.

**Có cần test bằng email production thật không?** Không. Phần lớn lỗi filename và MIME có thể kiểm tra bằng `MimeMessage` tại chỗ, JUnit và SMTP sink. Dùng client thật chỉ cho những tình huống tương thích cần thiết, với dữ liệu giả.

**`mailSender.send(...)` thành công có nghĩa attachment được người nhận mở được không?** Không. Nó chỉ xác nhận quá trình SMTP submission hoàn tất theo góc nhìn client. Mail gateway có thể chặn file hoặc client không mở được nội dung; cần kiểm tra delivery/attachment riêng.

**Nếu `addAttachment(...)` ném `IllegalArgumentException`, có nên retry không?** Không retry SMTP liên tục với cùng filename null. Đây thường là lỗi chuẩn bị email, cần sửa input hoặc code.

**Nếu tên file lấy từ tên khách hàng thì sao?** Cần cân nhắc quyền riêng tư và ký tự không an toàn. Thường tốt hơn dùng business reference được phép công khai hoặc tên tài liệu chung.

**Có thể dùng tên file từ URL của object storage?** Không nên lấy nguyên URL hay key làm tên MIME, vì có thể lộ path/token và tạo tên khó đọc. Chọn display name riêng.

**Có cần lưu filename trong outbox không?** Tùy chính sách. Có thể lưu một filename đã được xác thực hoặc lưu document kind/reference/version để worker sinh tên ổn định. Không lưu Resource Java object vào DB.

**Nếu job retry sau khi filename policy đổi thì sao?** Nên có version/snapshot policy với tài liệu đã phát hành để tránh các attempts của cùng job tạo nội dung/tên khác nhau ngoài dự kiến.

**Dùng một tên file cố định `attachment.pdf` cho tất cả email có được không?** Về kỹ thuật có thể, nhưng người dùng sẽ khó phân biệt tài liệu sau khi tải về. Một tên theo business context an toàn sẽ dễ sử dụng hơn.

**Khi inspect MIME, tại sao attachment không nằm ở body part thứ hai?** Multipart MIME có thể lồng nhiều cấp, đặc biệt khi email vừa có plain text, HTML, inline images và attachments. Nên duyệt các parts dựa trên disposition/filename.

**Làm sao tránh lộ nội dung khi debug?** Dùng fixture giả trong unit test. Trong production chỉ log metadata an toàn như file extension, size, document kind, internal job ID và error reason code.

## 41. Quy trình chuẩn để tránh lặp lại lỗi

Khi một chức năng mới cần gửi file đính kèm từ dữ liệu bộ nhớ, thực hiện theo trình tự:

1. **Xác định định dạng nội dung:** PDF, CSV, XLSX, ZIP hoặc loại khác.
2. **Tạo byte hợp lệ:** gọi generator phù hợp, kiểm tra dữ liệu không null/rỗng và size limit.
3. **Sinh tên từ nghiệp vụ:** dùng document kind, safe business reference, period/date; không lấy `ByteArrayResource.getFilename()`.
4. **Kiểm tra filename:** basename, length, extension, ký tự điều khiển, quyền riêng tư.
5. **Chọn MIME content type:** phù hợp byte format thực sự.
6. **Tạo `ByteArrayResource`** cho file vừa phải; chọn file-backed/reopenable source khi file lớn.
7. **Tạo multipart message:** `MimeMessageHelper(message, true, "UTF-8")` hoặc mode tường minh.
8. **Đặt From/To/Subject/Body:** dữ liệu hợp lệ, sender identity được phép.
9. **Gọi `addAttachment(filename, resource, contentType)`:** tên tường minh.
10. **Test MIME trước SMTP:** xác nhận filename, content type và bytes.
11. **Kiểm thử sink/client khi cần:** đặc biệt nếu dùng Unicode hoặc nhiều inline/attachments.
12. **Phân loại exception:** lỗi tên/file là lỗi preparation, không phải SMTP temporary throttle.
13. **Triển khai qua outbox nếu cần độ tin cậy:** giữ payload reference và metadata ổn định qua retry.
14. **Quan sát an toàn:** log mã lỗi, extension, size và ID opaque, không raw MIME/PII.

### Ví dụ mẫu cuối cùng

~~~java
byte[] attachmentBytes = documentGenerator.generate(document);
String attachmentName = "document-"
        + document.safeReference() + ".pdf";

if (attachmentBytes == null
        || attachmentBytes.length == 0) {
    throw new IllegalStateException(
            "Document generator returned empty data");
}

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("documents@example.com");
helper.setTo(recipientEmail);
helper.setSubject("Tài liệu của bạn");
helper.setText("Vui lòng xem file đính kèm.", false);

helper.addAttachment(
        attachmentName,
        new ByteArrayResource(attachmentBytes),
        "application/pdf");

mailSender.send(message);
~~~

Trong code production, `document.safeReference()` và sender/recipient phải qua các quy tắc nghiệp vụ, authorization và validation phù hợp. `documentGenerator` và `document` là giả lập.

## 42. Tổng kết

Lỗi **“Dùng ByteArrayResource nhưng đặt tên attachment không đúng”** thường bắt nguồn từ một giả định:

> Vì `ByteArrayResource` là một `Resource` nên `getFilename()` phải trả về tên file đã tạo.

**Giả định đó không đúng.** `ByteArrayResource` chứa byte[], không tự có tên file; thậm chí constructor hai tham số `ByteArrayResource(bytes, description)` cũng chỉ gắn mô tả.

Cách dùng cốt lõi:

~~~java
byte[] pdfBytes = pdfGenerator.generate();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.addAttachment(
        "invoice-583.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

Ba giá trị cần tách biệt:

~~~text
ByteArrayResource  -> nguồn byte
attachmentFilename -> tên hiển thị khi tải về
contentType        -> loại MIME khai báo
~~~

Những lưu ý chính:

1. **Không dùng `ByteArrayResource.getFilename()` để tự lấy tên attachment.** Tạo tên hợp lệ từ dữ liệu nghiệp vụ.
2. **Không nhầm description với filename.** Constructor hai tham số không giải quyết lỗi tên file.
3. **Tên, extension, Content-Type và byte format phải nhất quán.** Một filename đẹp không sửa được file rỗng/sai định dạng.
4. **Dùng đúng abstraction:** `addAttachment` cho file tải về, `addInline` cho nội dung CID trong HTML.
5. **Chọn nguồn nội dung có thể đọc lại:** `ByteArrayResource` cho dữ liệu bộ nhớ phù hợp, file-backed/reopenable stream cho file lớn.
6. **Kiểm thử trực tiếp MIME part** bằng `getFileName()`, `getContentType()` và byte stream; không cần gửi email thật để bắt lỗi filename.
7. **Bảo vệ dữ liệu:** không dùng path nội bộ, tên người nhận nhạy cảm hoặc chuỗi điều khiển trong attachment name.
8. **Phân loại lỗi đúng:** lỗi filename là lỗi chuẩn bị email, không phải SMTP outage cần retry vô hạn.

Khi ứng dụng chủ động xác định **tên attachment tại thời điểm xây dựng MIME**, việc đính kèm các báo cáo PDF, CSV, XLSX hoặc tài liệu sinh trong bộ nhớ sẽ rõ ràng và dễ kiểm thử hơn, đồng thời tránh một nhóm lỗi gây khó hiểu cho người nhận và người vận hành.
