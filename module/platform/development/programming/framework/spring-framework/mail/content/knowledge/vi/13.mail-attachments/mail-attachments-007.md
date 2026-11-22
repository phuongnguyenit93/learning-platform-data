# Kích thước tệp và giới hạn message trong Spring Framework Mail

Khi gửi email có tệp đính kèm, ứng dụng phải kiểm soát hai thứ khác nhau: **dung lượng của từng tệp** và **kích thước của toàn bộ email sau khi đóng gói thành MIME**. Một PDF 8 MB không nhất thiết tạo ra email 8 MB. Dữ liệu nhị phân thường được mã hóa Base64, MIME còn thêm header và boundary, còn body có thể chứa HTML, plain text và ảnh nội tuyến. Vì vậy, message cuối cùng có thể lớn hơn đáng kể so với tổng dung lượng các file gốc.

Trong Spring Framework Mail, `MimeMessageHelper` cung cấp các phương thức như `addAttachment(...)` để đưa file vào email. Helper giúp xây cấu trúc MIME, nhưng **không tự đặt ra giới hạn dung lượng phù hợp với SMTP provider, không thay thế kiểm tra file upload và không bảo đảm email sẽ được máy chủ nhận chấp nhận**. Ứng dụng cần xây một bước kiểm soát kích thước trước khi gửi.

Bài học này tập trung vào cách đo và giới hạn tệp đính kèm, ước lượng overhead MIME, xử lý file lớn, quản lý bộ nhớ, cấu hình ngưỡng theo nhà cung cấp và tích hợp kiểm tra vào luồng `JavaMailSender`.

## 1. Phân biệt kích thước file và kích thước email

Giả sử ứng dụng gửi email hóa đơn gồm:

- Một bản HTML khoảng 90 KB.
- Một bản plain text khoảng 2 KB.
- Một file PDF 6 MB.
- Một ảnh logo inline 100 KB.
- Một ảnh biên nhận JPEG 1,5 MB.

Có ít nhất ba con số cần theo dõi:

1. **File size**: dung lượng file gốc trên filesystem/object storage.
2. **Part size**: dung lượng mỗi phần sau khi đưa vào cấu trúc MIME và mã hóa truyền.
3. **Message size**: tổng dung lượng thông điệp MIME đã serialize, gồm headers, body, boundaries và mọi attachment/inline part.

Ví dụ sơ đồ:

~~~text
Nguồn nội dung
  |
  +--> HTML body: 90 KB
  +--> Plain text: 2 KB
  +--> PDF gốc: 6 MB
  +--> Logo inline: 100 KB
  +--> Ảnh biên nhận: 1.5 MB
           |
           v
     MimeMessageHelper
           |
           v
     MIME message
       - message headers
       - multipart boundaries
       - text/plain part
       - text/html part
       - image parts
       - application/pdf part
       - transfer-encoding overhead
           |
           v
       SMTP submission
           |
           v
     SMTP relay / ESP
~~~

Nếu chỉ cộng dung lượng file gốc, ứng dụng có thể đánh giá thấp message cuối. Nếu chỉ đo HTML, ứng dụng bỏ sót gần như toàn bộ attachment. Nếu chỉ đo MIME cuối, ứng dụng có thể biết thư quá lớn nhưng khó xác định file nào gây ra vấn đề. Một quy trình tốt đo cả thành phần và tổng thể.

### Các loại giới hạn không nên nhầm lẫn

| Giới hạn | Áp dụng cho | Ví dụ kiểm soát |
| --- | --- | --- |
| Kích thước mỗi file | Một attachment cụ thể | PDF tối đa 10 MB |
| Tổng dung lượng file gốc | Tất cả file được chọn | Tổng attachment tối đa 15 MB |
| Kích thước MIME message | Toàn bộ email đã đóng gói | Serialized message tối đa theo budget nội bộ |
| Số lượng attachment | Số MIME parts kiểu attachment | Tối đa 5 file |
| Số lượng recipient | To/Cc/Bcc hoặc envelope recipients | Theo quota SMTP provider |
| Kích thước HTML | Nội dung markup | Ngăn template quá lớn hoặc bị clipping |
| Giới hạn provider | Chính sách SMTP/API | Message size, attachment size, recipient count |
| Giới hạn ứng dụng | Quy tắc nghiệp vụ và tài nguyên hệ thống | Hạn mức theo tenant, loại email hoặc người dùng |

Những giới hạn này cần được kiểm tra độc lập. Một email có thể nằm dưới tổng message limit nhưng vẫn vi phạm giới hạn một attachment; ngược lại, từng file có thể hợp lệ nhưng cộng lại khiến message vượt ngưỡng.

## 2. Vì sao attachment làm email lớn hơn file gốc?

MIME là định dạng dùng để đóng gói nhiều loại nội dung trong một email. Một attachment nhị phân thường được truyền bằng `Content-Transfer-Encoding: base64`.

Base64 chuyển mỗi nhóm 3 byte đầu vào thành 4 ký tự đầu ra. Dung lượng cơ bản tăng xấp xỉ 4/3, tức khoảng 33,3%, chưa tính xuống dòng và header MIME.

Công thức ước lượng:

~~~text
base64Length = 4 × ceil(originalBytes / 3)
~~~

Ví dụ một file có 6.000.000 byte:

~~~text
Base64 length
  = 4 × ceil(6,000,000 / 3)
  = 8,000,000 ký tự ASCII
~~~

Khi MIME xuống dòng dữ liệu Base64 theo các dòng có độ dài giới hạn (thường 76 ký tự), còn có thêm CRLF. Ngoài ra, mỗi part có header riêng như `Content-Type`, `Content-Disposition`, `Content-Transfer-Encoding`, boundary phân tách và các metadata khác.

### Hàm ước lượng Base64

~~~java
public final class AttachmentSizeEstimator {

    private AttachmentSizeEstimator() {}

    public static long base64Length(long originalBytes) {
        if (originalBytes < 0) {
            throw new IllegalArgumentException("Size must not be negative");
        }

        return 4L * ((originalBytes + 2L) / 3L);
    }

    public static long base64WithLineBreaks(long originalBytes) {
        long encodedBytes = base64Length(originalBytes);
        long lineCount = (encodedBytes + 75L) / 76L;

        // Ước lượng CRLF giữa các dòng, không cộng CRLF cuối.
        long crlfBytes = Math.max(0L, lineCount - 1L) * 2L;
        return encodedBytes + crlfBytes;
    }
}
~~~

Ví dụ trên là **ước lượng cho một part Base64**, không phải phép đo chính xác toàn bộ email. Một số part text có thể dùng quoted-printable hoặc 7bit; thư viện quyết định transfer encoding theo nội dung và cấu hình. Đừng cộng hệ số 4/3 cho toàn bộ HTML một cách máy móc.

### Ví dụ tính nhẩm

| File gốc | Base64 cơ bản (xấp xỉ) | Ý nghĩa |
| ---: | ---: | --- |
| 100 KB | 133,4 KB | Chưa tính CRLF và MIME headers |
| 1 MB | 1,34 MB | Một attachment có thể tăng đáng kể |
| 5 MB | 6,67 MB | Tổng message còn có body và các part khác |
| 10 MB | 13,34 MB | Có thể vượt một số giới hạn message phổ biến |

Bảng chỉ minh họa tỷ lệ Base64 theo MB decimal; kích thước thực tế phụ thuộc cách MIME serialize. Provider có thể tính message theo cách riêng, do đó không lấy bảng này làm cam kết giao thư.

## 3. Đọc kích thước file trước khi tạo MimeMessage

Với file nằm trên filesystem, dùng `Files.size(path)`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path invoice = Path.of("/data/invoices/invoice-2026-001.pdf");
long fileBytes = Files.size(invoice);
~~~

`Files.size(...)` đọc metadata của file, không cần nạp toàn bộ nội dung vào heap. Đây là cách đơn giản và hiệu quả khi nguồn attachment là file trên đĩa.

Nếu file được quản lý bởi Spring `Resource`, có thể dùng `contentLength()` khi resource hỗ trợ kích thước đáng tin cậy:

~~~java
Resource resource = new ClassPathResource("mail/terms.pdf");
long bytes = resource.contentLength();
~~~

Tuy nhiên, không phải mọi `Resource` đều biết trước độ dài. Với một số stream hoặc nguồn dữ liệu động, `contentLength()` có thể không phù hợp hoặc phải đọc nội dung. Khi cần đếm chính xác, có thể đọc stream theo buffer:

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;

public final class ResourceSizer {

    private ResourceSizer() {}

    public static long count(Resource resource) throws IOException {
        long total = 0L;
        byte[] buffer = new byte[8192];

        try (InputStream input = resource.getInputStream()) {
            int read;
            while ((read = input.read(buffer)) != -1) {
                total += read;
            }
        }

        return total;
    }
}
~~~

Đếm theo stream không cần tạo một mảng byte có kích thước bằng file. Nhưng cần bảo đảm resource có thể mở một stream mới khi bước gửi bắt đầu. Không dùng một `InputStream` đã bị đọc hết cho cả preflight và attachment.

### Giữ số đo dưới dạng long

Kích thước file có thể lớn hơn giới hạn của kiểu `int`. Nên dùng `long` cho bytes, phép cộng tổng và budget:

~~~java
long maxAttachmentBytes = 10L * 1024 * 1024;
long totalAttachmentBytes = 0L;

for (Path path : files) {
    totalAttachmentBytes += Files.size(path);
}
~~~

Khi cộng nhiều file, cần cân nhắc overflow nếu dữ liệu có thể đến từ nguồn không tin cậy hoặc có số lượng lớn. Ứng dụng thực tế thường giới hạn số file và dung lượng mỗi file trước khi cộng.

## 4. Đặt giới hạn cho từng file và tổng attachment

Không nên chỉ có một giới hạn tổng. Một file cực lớn có thể gây áp lực bộ nhớ, virus scanning hoặc timeout dù tổng các file khác nhỏ.

Ví dụ policy:

- Mỗi attachment tối đa 10 MB.
- Tổng file gốc tối đa 15 MB.
- Tối đa 5 attachment.
- Chỉ chấp nhận PDF, PNG và JPEG cho loại email hóa đơn.
- Tổng MIME message phải thấp hơn budget cấu hình của provider với margin.

Các con số chỉ là ví dụ. Hạn mức thực tế phải dựa trên nhà cung cấp SMTP, loại email và tài nguyên hệ thống.

### Ví dụ kiểm tra danh sách file

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class AttachmentPolicy {

    private final long maxFileBytes;
    private final long maxTotalBytes;
    private final int maxFiles;

    public AttachmentPolicy(
            long maxFileBytes,
            long maxTotalBytes,
            int maxFiles) {
        this.maxFileBytes = maxFileBytes;
        this.maxTotalBytes = maxTotalBytes;
        this.maxFiles = maxFiles;
    }

    public long validate(List<Path> files) throws IOException {
        if (files == null || files.size() > maxFiles) {
            throw new IllegalArgumentException(
                "Too many attachments");
        }

        long total = 0L;

        for (Path path : files) {
            long size = Files.size(path);

            if (size > maxFileBytes) {
                throw new IllegalArgumentException(
                    "An attachment exceeds the per-file limit");
            }

            if (size > maxTotalBytes - total) {
                throw new IllegalArgumentException(
                    "Attachments exceed the total size limit");
            }

            total += size;
        }

        return total;
    }
}
~~~

Điều kiện `size > maxTotalBytes - total` tránh cộng vượt giới hạn trước khi phát hiện. Tuy nhiên, đây chỉ là kiểm tra kích thước. Trước khi gửi, ứng dụng còn cần xác minh file nằm trong vùng lưu trữ được phép, loại nội dung thực tế và trạng thái an toàn của file.

## 5. Tạo email có attachment bằng MimeMessageHelper

`SimpleMailMessage` chỉ dành cho email text cơ bản. Khi cần file đính kèm, dùng `MimeMessage` cùng `MimeMessageHelper`.

Ví dụ:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.File;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailer {

    private final JavaMailSender mailSender;

    public InvoiceMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, File invoice)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");
        helper.setText(
            "Vui lòng xem hóa đơn trong tệp đính kèm.",
            false
        );

        helper.addAttachment(
            invoice.getName(),
            new FileSystemResource(invoice)
        );

        mailSender.send(message);
    }
}
~~~

Tham số `true` trong constructor `MimeMessageHelper` bật multipart, cho phép thêm attachment. Helper tạo các MIME parts và xử lý header cần thiết.

Đoạn code trên minh họa cách đính kèm file; production cần kiểm tra giới hạn file, tổng MIME và chính sách file trước khi gọi `send`. Không nên đợi provider từ chối mới phát hiện người dùng tải lên file quá lớn.

### Dùng Resource thay cho File

Spring hỗ trợ `Resource`:

~~~java
helper.addAttachment(
    "terms-and-conditions.pdf",
    new ClassPathResource("mail/terms-and-conditions.pdf")
);
~~~

Hoặc file trong vùng lưu trữ:

~~~java
helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(invoicePath)
);
~~~

Tên hiển thị attachment nên được kiểm soát riêng. Không sử dụng nguyên đường dẫn filesystem làm filename gửi tới người nhận; chỉ dùng tên file đã chuẩn hóa, không chứa path separator hoặc ký tự điều khiển.

## 6. Đo toàn bộ MIME message trước khi gửi

Đo file gốc hữu ích để kiểm tra từng attachment. Nhưng muốn biết message đã dựng lớn bao nhiêu, cần serialize `MimeMessage` sau khi thêm đủ nội dung và attachment.

Jakarta Mail cung cấp `MimeMessage.writeTo(OutputStream)`. Có thể ghi vào một stream chỉ đếm byte thay vì lưu toàn bộ message thành một mảng byte.

### CountingOutputStream

~~~java
import java.io.OutputStream;

public final class CountingOutputStream extends OutputStream {

    private long count;

    @Override
    public void write(int value) {
        count++;
    }

    @Override
    public void write(byte[] buffer, int offset, int length) {
        if (length < 0) {
            throw new IndexOutOfBoundsException();
        }
        count += length;
    }

    public long getCount() {
        return count;
    }
}
~~~

### Serializer đo MIME

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;

public final class MimeMessageSizer {

    private MimeMessageSizer() {}

    public static long serializedBytes(MimeMessage message)
            throws MessagingException, IOException {
        message.saveChanges();

        CountingOutputStream output = new CountingOutputStream();
        message.writeTo(output);

        return output.getCount();
    }
}
~~~

Gọi `saveChanges()` giúp hoàn thiện các header/MIME metadata do Jakarta Mail quản lý trước khi serialize.

### Vì sao đây là phép đo gần với message thực tế?

Nó bao gồm các phần mà phép đo file riêng lẻ không có:

- Header của message.
- Header của từng MIME part.
- Boundary phân cách multipart.
- Nội dung plain text và HTML.
- Ảnh inline.
- Attachment sau transfer encoding.
- Các metadata MIME khác.

Tuy nhiên, đây là kích thước **serialized message ở thời điểm đo**, không nhất thiết bằng chính xác số byte mà SMTP server tính. SMTP transport còn có framing, kết thúc DATA, dot-stuffing cho các dòng bắt đầu bằng dấu chấm và có thể bổ sung header. Provider cũng có thể áp dụng cách tính riêng.

Vì thế, dùng serialized size làm preflight estimate với margin an toàn; không coi nó là cam kết rằng server sẽ chấp nhận thư.

### Cẩn trọng với DataSource chỉ đọc một lần

`writeTo(...)` có thể đọc nội dung các attachment để serialize. Nếu DataSource dùng stream chỉ đọc một lần, bước đo có thể tiêu thụ stream trước khi `send(...)` chạy.

Ưu tiên `FileSystemResource`, `ClassPathResource` hoặc `InputStreamSource` có khả năng mở stream mới cho mỗi lần đọc. Không tạo một `InputStream` duy nhất rồi trả lại cùng stream cho mọi lần gọi.

## 7. Ví dụ preflight đầy đủ trước khi gửi

Ví dụ dưới đây kết hợp giới hạn file gốc, kiểm tra số lượng file và đo serialized MIME:

~~~java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class DocumentMailer {

    private static final long MAX_FILE_BYTES = 10L * 1024 * 1024;
    private static final long MAX_TOTAL_FILE_BYTES = 15L * 1024 * 1024;
    private static final long MAX_MIME_BYTES = 20L * 1024 * 1024;
    private static final int MAX_FILE_COUNT = 5;

    private final JavaMailSender mailSender;

    public DocumentMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String subject,
            String body,
            List<Path> attachments)
            throws IOException, MessagingException {

        validateAttachmentFiles(attachments);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("documents@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(body, false);

        for (Path path : attachments) {
            helper.addAttachment(
                safeDisplayName(path),
                new FileSystemResource(path)
            );
        }

        long mimeBytes = MimeMessageSizer.serializedBytes(message);

        if (mimeBytes > MAX_MIME_BYTES) {
            throw new IllegalArgumentException(
                "The complete email exceeds the configured message budget");
        }

        mailSender.send(message);
    }

    private void validateAttachmentFiles(List<Path> files)
            throws IOException {
        if (files == null || files.size() > MAX_FILE_COUNT) {
            throw new IllegalArgumentException(
                "Attachment count exceeds the configured limit");
        }

        long total = 0L;

        for (Path path : files) {
            if (path == null || !Files.isRegularFile(path)) {
                throw new IllegalArgumentException(
                    "Attachment is not a regular file");
            }

            long size = Files.size(path);

            if (size > MAX_FILE_BYTES) {
                throw new IllegalArgumentException(
                    "An attachment exceeds the per-file limit");
            }

            if (size > MAX_TOTAL_FILE_BYTES - total) {
                throw new IllegalArgumentException(
                    "Attachments exceed the total file size limit");
            }

            total += size;
        }
    }

    private String safeDisplayName(Path path) {
        Path name = path.getFileName();
        return name == null ? "attachment" : name.toString();
    }
}
~~~

Các giới hạn trong ví dụ là giá trị minh họa. Một ứng dụng thực tế nên đọc chúng từ cấu hình, không hard-code trong service. Hàm `safeDisplayName` cũng chỉ là ví dụ đơn giản; nếu filename đến từ người dùng, cần chuẩn hóa và loại bỏ ký tự điều khiển, path separator và tên không hợp lệ trước khi sử dụng.

Ví dụ chưa triển khai kiểm tra MIME type thực tế, malware scanning, tenant quota hoặc xác minh quyền đọc file. Đây là những bước cần thiết tùy theo nguồn attachment và yêu cầu bảo mật.

## 8. Giới hạn message của SMTP provider

Mỗi SMTP relay hoặc Email Service Provider (ESP) có thể áp dụng các giới hạn khác nhau:

- Kích thước toàn bộ message.
- Kích thước từng attachment.
- Tổng dung lượng attachment.
- Số lượng attachment.
- Số lượng người nhận trong một message.
- Kích thước header hoặc số lượng header.
- Tốc độ gửi và số kết nối đồng thời.
- Tổng dung lượng gửi theo ngày/tháng.
- Loại MIME hoặc phần mở rộng file được phép.

Không có một giá trị giới hạn chung cho mọi SMTP server. Một nhà cung cấp có thể giới hạn 10 MB, nhà cung cấp khác 25 MB hoặc một mức khác; mailbox provider phía nhận cũng có chính sách riêng. Cần đọc tài liệu của **provider đang sử dụng**, kiểm tra cấu hình account và xác nhận cách họ tính kích thước.

### Giới hạn của SMTP DATA và SIZE extension

SMTP có thể quảng bá extension `SIZE` trong phản hồi `EHLO`, cho biết giới hạn message mà server công bố. Client/transport có thể dùng thông tin này trong quá trình gửi tùy implementation và phiên bản thư viện.

Tuy nhiên:

- Không phải mọi server đều quảng bá `SIZE`.
- Giá trị server công bố có thể khác giới hạn theo account hoặc policy.
- Provider có thể từ chối dựa trên tổng message hoặc quy tắc bổ sung.
- Server nhận cuối cùng có thể áp dụng giới hạn khác relay gửi.
- Một email được relay chấp nhận vẫn có thể bounce hoặc bị từ chối ở chặng tiếp theo.

Do đó, ứng dụng nên có budget riêng và vẫn xử lý SMTP reply khi gửi thật.

### Đặt budget thấp hơn giới hạn provider

Giả sử provider công bố giới hạn message 25 MB decimal. Không nên đặt budget ứng dụng đúng bằng 25 MB, vì MIME overhead, header bổ sung và cách tính khác nhau có thể khiến message vượt giới hạn.

Một chính sách có thể dùng margin, ví dụ budget nội bộ 20 MB. Đây chỉ là minh họa; giá trị phải được chọn từ tài liệu provider và số đo thực tế.

## 9. Cấu hình giới hạn theo môi trường và nhà cung cấp

Nên tách budget khỏi mã nguồn:

~~~yaml
app:
  mail:
    attachments:
      max-file-bytes: 10485760
      max-total-bytes: 15728640
      max-count: 5
    message:
      max-serialized-bytes: 20971520
~~~

Tạo lớp cấu hình:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailAttachmentProperties(
    AttachmentLimits attachments,
    MessageLimits message
) {
    public record AttachmentLimits(
        long maxFileBytes,
        long maxTotalBytes,
        int maxCount
    ) {}

    public record MessageLimits(
        long maxSerializedBytes
    ) {}
}
~~~

Đăng ký cấu hình bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` phù hợp với ứng dụng.

Có thể dùng profile để điều chỉnh môi trường:

- Local/test: giới hạn nhỏ để phát hiện lỗi nhanh, SMTP test server.
- Staging: giới hạn gần production và kiểm tra provider sandbox.
- Production: giới hạn theo hợp đồng SMTP/ESP, có margin.
- Tenant-specific: giới hạn riêng nếu hợp đồng hoặc chính sách account khác nhau.

Không để client gửi lên một giá trị `maxFileBytes` tùy ý để quyết định giới hạn thực tế. Ngưỡng phải do server quản lý.

## 10. Kiểm tra file upload trước khi biến nó thành attachment

Nếu attachment xuất phát từ người dùng upload, việc kiểm tra trước khi gửi email chỉ là **lớp kiểm tra thứ hai**. Nên kiểm soát file ngay tại upload boundary:

1. Kiểm tra kích thước request và file riêng lẻ.
2. Giới hạn số file và tổng bytes theo user/tenant.
3. Kiểm tra phần mở rộng theo allowlist nghiệp vụ.
4. Đọc file signature/magic bytes hoặc dùng thư viện nhận diện nội dung; không tin `Content-Type` do browser gửi lên.
5. Chuẩn hóa tên file để không chứa path traversal, CR/LF hoặc ký tự điều khiển.
6. Lưu file vào vùng storage không cho phép thực thi.
7. Quét malware theo yêu cầu bảo mật.
8. Giới hạn thời gian và tài nguyên khi xử lý archive, PDF hoặc file ảnh phức tạp.
9. Chỉ cho phép email service đính kèm file đã qua trạng thái kiểm tra phù hợp.

### Không tin phần mở rộng file

Một file có tên `invoice.pdf` không nhất thiết là PDF. Kẻ gửi có thể đổi tên executable hoặc nội dung khác thành `.pdf`. Kiểm tra phần mở rộng hữu ích cho policy và trải nghiệm, nhưng cần kiểm tra nội dung thực tế.

Ví dụ với PDF, có thể kiểm tra MIME type bằng một thư viện nhận diện nội dung và/hoặc signature phù hợp. Không dựa duy nhất vào `Files.probeContentType(path)`, vì kết quả phụ thuộc hệ điều hành và cấu hình MIME database.

### Kiểm soát tên hiển thị

Tên file đính kèm là dữ liệu hiển thị trong email header `Content-Disposition`. Trước khi đưa filename vào helper, nên:

- Lấy basename, không gửi đường dẫn tuyệt đối.
- Loại bỏ CR, LF và ký tự điều khiển.
- Giới hạn độ dài.
- Không để tên file chứa thông tin nội bộ như path máy chủ hoặc username.
- Dùng tên dễ hiểu với người nhận.

`MimeMessageHelper` có overload hỗ trợ filename encoding, nhưng không thay thế việc chuẩn hóa đầu vào.

## 11. File lớn, streaming và bộ nhớ

Không nên đọc tất cả attachment vào `byte[]` chỉ để kiểm tra kích thước hoặc gửi mail:

~~~java
byte[] file = Files.readAllBytes(path);
helper.addAttachment("large.pdf", new ByteArrayResource(file));
~~~

Cách này giữ toàn bộ file trong heap. Khi nhiều worker cùng gửi file lớn, bộ nhớ cần thiết có thể tăng nhanh. Ví dụ 20 worker cùng nạp 10 MB mỗi file đã cần khoảng 200 MB cho các mảng file thô, chưa tính Base64, MIME buffers, object overhead và phần còn lại của ứng dụng.

Ưu tiên resource có thể mở stream:

~~~java
helper.addAttachment(
    "large-report.pdf",
    new FileSystemResource(path)
);
~~~

Khi dùng resource/stream, cần lưu ý:

- Resource phải còn tồn tại và đọc được trong suốt thời gian serialize/gửi.
- Nếu bước preflight serialize MIME rồi bước send serialize lại, resource phải mở được stream mới.
- Không xóa file tạm trước khi `send(...)` hoàn tất.
- Nếu file nằm trên object storage, dùng resource adapter có stream mở mới và timeout phù hợp.
- Kiểm soát số worker đồng thời để tránh quá tải disk, network và heap.

Streaming giảm nhu cầu giữ file gốc trong một mảng byte, nhưng không có nghĩa toàn bộ quá trình gửi luôn zero-copy hoặc không có buffer. Jakarta Mail và SMTP transport vẫn có thể dùng bộ đệm và thực hiện encoding trong quá trình serialize.

### Tách xử lý file khỏi luồng HTTP

Nếu người dùng upload file rồi ứng dụng gửi email ngay trong request, request có thể chờ upload, scan, MIME serialization và SMTP submission. Với file lớn, nên cân nhắc:

~~~text
HTTP upload
    |
    v
Validate size / type / permission
    |
    v
Store file + metadata
    |
    v
Create notification/outbox record
    |
    v
Return response
    |
    v
Mail worker
    |
    +--> load attachment resource
    +--> recheck size and status
    +--> build MIME message
    +--> preflight serialized size
    +--> JavaMailSender.send(...)
    |
    v
Record attempt / provider result
~~~

Worker có thể giới hạn concurrency, retry có backoff và xử lý lỗi mà không giữ request HTTP mở lâu.

## 12. Trường hợp nên gửi link thay vì attachment

Không phải file nào cũng cần đính kèm trực tiếp. Với tài liệu lớn, có thể gửi link tải nếu hệ thống có cơ chế truy cập an toàn.

| Tình huống | Cách cân nhắc |
| --- | --- |
| PDF hóa đơn nhỏ, người nhận cần lưu ngay | Attachment có thể thuận tiện |
| Báo cáo vài chục MB | Link tải có xác thực thường phù hợp hơn |
| Bộ ảnh lớn | Album/download page hoặc object storage link |
| Tài liệu chứa dữ liệu cá nhân | Link có xác thực, kiểm tra quyền và audit |
| File cần cập nhật sau khi gửi | Link tới tài liệu hiện tại thay vì bản đính kèm cố định |
| File phải được lưu nguyên trạng cùng email | Attachment có thể phù hợp nếu nằm trong giới hạn |

Một link tải an toàn cần:

- HTTPS.
- Kiểm tra quyền truy cập tại server.
- Token có phạm vi và thời hạn phù hợp nếu dùng signed URL.
- Không để lộ ID tuần tự dễ đoán hoặc dữ liệu cá nhân trong URL.
- Có thể thu hồi hoặc hết hạn khi tài liệu không còn được phép tải.
- Ghi nhận truy cập theo chính sách riêng tư.
- Tránh hành động nhạy cảm chỉ bằng GET nếu link scanner có thể tự truy cập.

Link tải không tự động tốt hơn attachment. Nếu người nhận cần bản tài liệu bất biến đi kèm hồ sơ email hoặc cần làm việc offline, attachment có thể là lựa chọn phù hợp hơn.

## 13. Attachment và ảnh inline có cùng làm tăng message size không?

Có. Cả attachment và ảnh inline đều được đóng gói thành MIME parts. Khác biệt chủ yếu là cách chúng được tham chiếu và hiển thị:

- Attachment thường có `Content-Disposition: attachment` để email client hiển thị như file tải về.
- Ảnh inline thường có `Content-ID` và được HTML tham chiếu qua `cid:...`, thường ở phần `multipart/related`.
- Cả hai đều chứa dữ liệu file trong MIME nếu không phải URL từ xa.
- Cả hai có thể cần Base64 transfer encoding.

Ví dụ ảnh inline:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);

helper.setText(
    "Xem nội dung trong email.",
    "<html><body><img src=\\"cid:logo\\"></body></html>"
);

helper.addInline(
    "logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
~~~

Ví dụ attachment:

~~~java
helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(invoicePath)
);
~~~

Trong cả hai trường hợp, khi kiểm soát tổng dung lượng message, cần đo serialized MIME sau khi đã thêm đủ parts.

### URL ảnh từ xa khác với ảnh inline

Nếu HTML chứa:

~~~html
<img src="https://static.example.com/banner.jpg" alt="Banner">
~~~

thì MIME chỉ chứa markup và URL; file ảnh không nằm trong message. Điều đó giảm message size, nhưng ảnh có thể bị email client chặn, tải qua proxy hoặc không hiển thị. Nên theo dõi asset remote riêng và không đặt thông tin thiết yếu chỉ trong ảnh.

## 14. Giới hạn theo từng loại email và tenant

Một ứng dụng có thể gửi nhiều loại thư:

- OTP hoặc thông báo bảo mật: thường không cần attachment.
- Xác nhận đơn hàng: có thể đính kèm hóa đơn nhỏ.
- Báo cáo vận hành: có thể cần CSV/PDF.
- Newsletter: thường dùng ảnh remote hoặc inline.
- Email hỗ trợ: có thể đính kèm ảnh chụp màn hình.

Không nên dùng một budget duy nhất cho tất cả loại email nếu nhu cầu khác nhau. Có thể định nghĩa policy theo template hoặc message category:

| Loại email | Max attachment count | Max single file | Max total MIME |
| --- | ---: | ---: | ---: |
| OTP/security | 0 | 0 | 200 KB |
| Transactional notice | 2 | 5 MB | 8 MB |
| Invoice | 1 | 10 MB | 15 MB |
| Operations report | 5 | 10 MB | 20 MB |
| Newsletter | Theo chiến lược asset | Theo asset policy | Theo ESP |

Các con số chỉ là minh họa. Nếu tenant dùng SMTP account riêng, budget có thể khác theo hợp đồng và provider. Không cho phép tenant tự nâng giới hạn vượt quá policy hệ thống.

Một lớp policy có thể nhận `MailCategory`, `tenantId` và metadata attachment, rồi trả về hạn mức áp dụng. Không nên đặt logic chọn provider/tenant vào `MimeMessageHelper`; helper chỉ nên xây message theo quyết định của lớp nghiệp vụ/hạ tầng.

## 15. Xử lý lỗi khi message vượt giới hạn

Khi provider từ chối message vì quá lớn, lỗi có thể xuất hiện ở SMTP DATA hoặc dưới dạng lỗi API tùy dịch vụ. Mã lỗi và nội dung phản hồi không giống nhau giữa các nhà cung cấp. Không nên gán cứng một mã SMTP duy nhất cho mọi trường hợp vượt size.

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Message bị từ chối ngay khi gửi | Tổng MIME vượt giới hạn provider | Đo serialized MIME, giảm file hoặc chuyển sang link |
| Một file bị từ chối dù tổng thư còn nhỏ | Vượt giới hạn per-attachment hoặc định dạng không được phép | Kiểm tra từng file và policy |
| Gửi chậm hoặc timeout | File lớn, network chậm, server xử lý lâu | Giới hạn size, timeout, queue và concurrency |
| OutOfMemoryError khi gửi hàng loạt | Đọc file vào byte arrays hoặc quá nhiều worker đồng thời | Dùng Resource/stream, giới hạn concurrency |
| Email vào được relay nhưng bounce sau đó | Hệ thống nhận cuối có giới hạn hoặc policy khác | Theo dõi bounce/event từ ESP |
| Attachment bị hỏng | Stream đã bị tiêu thụ, file thay đổi hoặc MIME part sai | Dùng resource đọc lại được và kiểm tra file snapshot |
| Tên file lỗi dấu | Encoding filename không đúng hoặc tên đầu vào không hợp lệ | Dùng helper và chuẩn hóa filename |
| File có phần mở rộng hợp lệ nhưng không mở được | Nội dung thực tế không khớp extension | Kiểm tra MIME/signature và scan file |

### Retry có giúp với lỗi size không?

Nếu message không thay đổi, retry không giải quyết được lỗi vượt giới hạn. Cần thay đổi nội dung: giảm ảnh, nén/resize, bỏ attachment không cần thiết hoặc chuyển sang link tải.

Nếu timeout xảy ra trong quá trình SMTP DATA, kết quả có thể không chắc chắn: relay có thể đã nhận thư nhưng client chưa nhận được phản hồi cuối. Retry mù có thể gửi trùng. Cần lưu delivery/attempt ID và đối soát với provider khi có thể.

## 16. Theo dõi kích thước và không ghi dữ liệu nhạy cảm vào log

Nên ghi nhận số đo để biết template hoặc loại email nào thường vượt budget:

~~~json
{
  "deliveryId": "delivery-2026-001",
  "template": "invoice-email",
  "attachmentCount": 1,
  "attachmentBytes": 6291456,
  "htmlBytes": 82100,
  "serializedMimeBytes": 8543000,
  "maxMimeBytes": 20000000,
  "preflight": "accepted"
}
~~~

Các chỉ số hữu ích:

- Số bytes của từng attachment.
- Tổng bytes file gốc.
- HTML/plain-text bytes.
- Serialized MIME bytes.
- Số attachment và số recipient.
- Tỷ lệ message bị chặn bởi preflight.
- Tỷ lệ SMTP rejection do size.
- Thời gian serialize và gửi.
- Số job chờ trong queue.

Không ghi nội dung file, Base64, HTML đầy đủ hoặc dữ liệu cá nhân chỉ để đo size. Nếu cần đối chiếu file, có thể ghi file ID nội bộ hoặc hash được kiểm soát thay vì nội dung.

## 17. Kiểm thử giới hạn attachment

Có thể kiểm thử policy mà không cần SMTP server. Ví dụ dùng JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class AttachmentPolicyTest {

    @Test
    void rejectsTooManyAttachments() {
        AttachmentPolicy policy =
            new AttachmentPolicy(1024, 4096, 2);

        assertThrows(
            IllegalArgumentException.class,
            () -> policy.validate(List.of(
                Path.of("a.pdf"),
                Path.of("b.pdf"),
                Path.of("c.pdf")
            ))
        );
    }
}
~~~

Test này cần file fixture tồn tại nếu policy đọc `Files.size`; trong test thực tế có thể tạo temporary files với nội dung và kích thước xác định. Ngoài ra nên kiểm tra:

- File đúng bằng giới hạn được chấp nhận.
- File lớn hơn giới hạn bị từ chối.
- Tổng các file vượt ngưỡng bị từ chối.
- Số lượng attachment vượt giới hạn bị từ chối.
- File không tồn tại hoặc không phải regular file bị xử lý đúng.
- Serialized MIME vượt budget bị từ chối trước khi gọi sender.
- Resource có thể đọc lại sau bước đo.
- Message vẫn có attachment đúng sau khi gửi qua SMTP test server.

### Kiểm tra MIME bằng SMTP test server

Unit test chỉ kiểm tra logic policy. Integration test có thể gửi email tới SMTP test server cục bộ, sau đó đọc raw message để xác nhận:

- `Content-Type` và multipart boundary.
- Attachment filename và MIME type.
- `Content-Transfer-Encoding`.
- Dữ liệu attachment sau khi decode có hash giống file gốc.
- Kích thước serialized gần với số đo preflight.
- Email client nhận được cấu trúc message mong muốn.

Không dùng SMTP production trong unit test. Không gửi fixture chứa dữ liệu thật tới mailbox người dùng.

## 18. Một số lưu ý khi dùng Spring Boot và Jakarta Mail

### Timeout không phải giới hạn kích thước

Các thuộc tính:

~~~properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
~~~

kiểm soát thời gian thao tác socket, không đặt giới hạn attachment hoặc MIME size. Một file 30 MB vẫn có thể được gửi nếu provider cho phép và timeout đủ; ngược lại, file 1 MB vẫn có thể thất bại do mạng hoặc policy.

### spring.servlet.multipart không phải mail attachment limit

Spring Boot có các thuộc tính multipart cho upload HTTP, ví dụ giới hạn file và request upload. Chúng kiểm soát dữ liệu **đi vào ứng dụng qua HTTP**, không tự động giới hạn email được gửi ra qua `JavaMailSender`.

Nếu file upload rồi được đính kèm, cần kiểm tra ở cả hai ranh giới:

1. Upload request: giới hạn request/file, số lượng, quyền và nội dung.
2. Mail send: giới hạn attachment, tổng MIME, provider policy và quota.

Không dùng một thuộc tính upload làm bằng chứng rằng mọi message gửi đi đều nằm trong giới hạn SMTP.

### Không đặt file path do người dùng kiểm soát trực tiếp

Nếu request chứa đường dẫn file, không tạo `FileSystemResource` từ chuỗi đó một cách tùy ý. Người dùng có thể thử truy cập file ngoài thư mục cho phép. Hãy nhận file ID, tra metadata trong storage do ứng dụng quản lý và xác minh người gửi có quyền đính kèm file đó.

## 19. Quy trình ra quyết định khi có tệp đính kèm

Trước khi gửi email có attachment, có thể theo luồng:

~~~text
Nhận yêu cầu gửi email
        |
        v
Xác định loại email và policy
        |
        v
Kiểm tra quyền truy cập file
        |
        v
Kiểm tra số lượng / file size / tổng file size
        |
        v
Kiểm tra type, filename, malware status
        |
        v
Tạo MimeMessage + MimeMessageHelper
        |
        v
Thêm body, inline parts và attachments
        |
        v
Serialize MIME để đo tổng message
        |
        v
Nằm trong budget với margin?
        |
      +---+---+
      |       |
     Không    Có
      |       |
      v       v
Tối ưu / link  JavaMailSender.send()
tải / từ chối        |
                     v
             Lưu kết quả submission
~~~

Nếu vượt budget, ứng dụng nên trả lỗi nghiệp vụ rõ ràng hoặc chuyển sang phương án link tải. Không gửi thử để “xem provider có nhận không” khi ứng dụng đã biết message vượt ngưỡng của mình.

## 20. Ghi nhớ

Khi làm việc với attachment trong Spring Framework Mail, cần quản lý đồng thời file và toàn bộ email:

- Đo file gốc bằng `Files.size(...)` hoặc stream counting; dùng `long` cho bytes.
- Đặt giới hạn cho từng file, tổng attachment và số lượng file.
- Nhớ Base64 làm dữ liệu nhị phân tăng khoảng một phần ba, chưa tính MIME overhead.
- Dựng đầy đủ `MimeMessage` rồi serialize bằng `writeTo(...)` vào counting stream để đo preflight.
- Xem serialized MIME là ước lượng gần với message được gửi, không phải bảo đảm chính xác về SMTP wire size hoặc cách provider tính quota.
- Dùng `MimeMessageHelper` và `Resource` để đính kèm file; ưu tiên nguồn có thể mở stream mới.
- Không nạp file lớn vào `byte[]` chỉ để đo hoặc gửi; kiểm soát worker concurrency và vòng đời resource.
- Kiểm tra file ngay từ upload boundary: quyền truy cập, type thực tế, tên, scan và quota.
- Đặt budget theo provider, tenant và loại email; dành margin an toàn.
- Khi file lớn, cân nhắc link tải có xác thực thay cho attachment.
- Theo dõi size metrics và provider errors mà không ghi nội dung nhạy cảm vào log.

`MimeMessageHelper` giúp thêm tệp vào email đúng cấu trúc MIME, còn giới hạn dung lượng là trách nhiệm của lớp ứng dụng và cấu hình vận hành. Khi kiểm tra file gốc, đo message cuối và áp dụng budget trước `JavaMailSender.send(...)`, hệ thống có thể phát hiện email quá lớn sớm, giảm lỗi SMTP và bảo vệ tài nguyên khi gửi nhiều thư đồng thời.
