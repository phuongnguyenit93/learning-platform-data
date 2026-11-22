# Đính kèm từ InputStreamSource

## 1. InputStreamSource là gì?

Trong **Spring Framework Mail**, khi email cần đính kèm một file, ứng dụng không nhất thiết phải đọc toàn bộ file thành mảng byte trước khi tạo thông điệp. Spring cung cấp abstraction **InputStreamSource** để mô tả một nguồn có thể mở ra một **InputStream** khi cần.

Interface nằm trong package **org.springframework.core.io** và có hợp đồng đơn giản:

~~~java
package org.springframework.core.io;

import java.io.IOException;
import java.io.InputStream;

public interface InputStreamSource {
    InputStream getInputStream() throws IOException;
}
~~~

Đây là chữ ký khái quát để học; ứng dụng sử dụng interface có sẵn của Spring, không khai báo lại interface này.

Điểm quan trọng là **InputStreamSource mô tả cách lấy stream, không phải bản thân một stream đã mở**. Điều này hữu ích khi thư viện cần đọc nội dung tại thời điểm serialize MIME hoặc gửi email. Một implementation tốt nên trả về **một InputStream mới cho mỗi lần gọi getInputStream()**.

Spring nhấn mạnh yêu cầu này vì những API như JavaMail có thể cần đọc nội dung nhiều lần trong quá trình tạo và gửi attachment. Nếu ứng dụng chỉ đưa vào một stream đã mở và stream đó đã bị đọc hoặc đóng, lần đọc tiếp theo có thể thất bại.

### InputStreamSource khác InputStream như thế nào?

| Kiểu | Ý nghĩa | Vòng đời |
|---|---|---|
| **InputStream** | Một luồng đang mở để đọc byte | Có vị trí đọc hiện tại; thường cần đóng; thường không thể đọc lại từ đầu |
| **InputStreamSource** | Một đối tượng cung cấp phương thức mở luồng | Có thể tạo stream mới khi được yêu cầu |
| **Resource** | Abstraction phong phú hơn của Spring cho tài nguyên | Kế thừa InputStreamSource, có thêm thông tin như mô tả, khả năng tồn tại/đọc được và cách truy cập tùy implementation |

Ví dụ:

~~~java
InputStream stream = Files.newInputStream(path);
~~~

Đoạn này mở một stream cụ thể. Trong khi đó:

~~~java
InputStreamSource source = () -> Files.newInputStream(path);
~~~

Đoạn thứ hai mô tả cách mở stream từ file. Mỗi lần gọi **source.getInputStream()** sẽ yêu cầu mở một stream mới từ path đó.

## 2. Vì sao Spring Mail nhận InputStreamSource?

**MimeMessageHelper** hỗ trợ thêm attachment bằng các phương thức như:

~~~java
helper.addAttachment(String attachmentFilename, InputStreamSource inputStreamSource);
helper.addAttachment(
        String attachmentFilename,
        InputStreamSource inputStreamSource,
        String contentType
);
~~~

Phương thức đầu cho phép helper suy luận loại nội dung theo nguồn tài nguyên hoặc tên file khi có thể. Phương thức thứ hai cho phép ứng dụng chỉ rõ **Content-Type**, ví dụ **application/pdf**.

Luồng tổng quát:

~~~text
Ứng dụng chọn file / dữ liệu
          |
          v
    InputStreamSource
    (cách mở stream)
          |
          v
MimeMessageHelper.addAttachment(...)
          |
          v
MIME body part được tạo cho attachment
          |
          v
JavaMailSender.send(message)
          |
          v
Jakarta Mail đọc dữ liệu và ghi thông điệp
          |
          v
SMTP transport
~~~

Lợi ích của abstraction này:

- **Không phải mở stream quá sớm** chỉ để truyền vào helper.
- **Tách nguồn dữ liệu khỏi cấu trúc MIME**: file có thể đến từ classpath, filesystem, bộ nhớ hoặc một dịch vụ lưu trữ.
- **Hỗ trợ đọc lại** nếu nguồn cung cấp stream mới mỗi lần.
- **Không buộc ứng dụng tự ghép MIME**: Spring và Jakarta Mail xử lý header, boundary, encoding và attachment.
- **Dễ thay đổi nguồn** mà không phải thay toàn bộ logic gửi thư.

InputStreamSource không tự gửi file và cũng không tự kiểm tra quyền truy cập. Nó chỉ cung cấp dữ liệu để tầng MIME dùng khi cần.

## 3. Luồng tạo attachment với MimeMessageHelper

Để đính kèm file, ứng dụng thường tạo **MimeMessage**, bật chế độ multipart cho **MimeMessageHelper**, rồi gọi **addAttachment(...)**:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendReport(JavaMailSender mailSender, String recipient)
        throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            true,
            "UTF-8"
    );

    helper.setFrom("reports@example.com");
    helper.setTo(recipient);
    helper.setSubject("Báo cáo tháng");
    helper.setText("Báo cáo tháng được đính kèm trong email này.");

    helper.addAttachment(
            "monthly-report.pdf",
            new ClassPathResource("reports/monthly-report.pdf"),
            "application/pdf"
    );

    mailSender.send(message);
}
~~~

Ví dụ giả định:

- Ứng dụng đã có bean **JavaMailSender** được cấu hình hợp lệ.
- Tài nguyên **reports/monthly-report.pdf** tồn tại trong classpath.
- Nhà cung cấp SMTP cho phép địa chỉ gửi và kích thước thông điệp này.

Giải thích:

1. **createMimeMessage()** tạo đối tượng MIME mới.
2. **MimeMessageHelper(message, true, "UTF-8")** bật multipart và dùng UTF-8 cho phần văn bản/header phù hợp.
3. **setFrom**, **setTo**, **setSubject** và **setText** thiết lập thông tin email.
4. **addAttachment(...)** thêm một MIME part có tên file hiển thị và nguồn dữ liệu.
5. **send(message)** chuyển thông điệp đã chuẩn bị cho mail transport.

Tham số **true** bật chế độ multipart. Nếu tạo helper ở chế độ không multipart rồi gọi addAttachment, cấu trúc message không có nơi thích hợp để chứa attachment và thao tác có thể thất bại.

## 4. Chọn overload addAttachment phù hợp

Spring Mail cung cấp các overload phổ biến:

~~~java
helper.addAttachment("report.pdf", inputStreamSource);
helper.addAttachment("report.pdf", inputStreamSource, "application/pdf");
~~~

| Tham số | Ý nghĩa |
|---|---|
| **attachmentFilename** | Tên file mà người nhận nhìn thấy trong email client |
| **inputStreamSource** | Nguồn có thể mở InputStream để đọc dữ liệu attachment |
| **contentType** | MIME media type của nội dung, ví dụ application/pdf hoặc image/png |

Ví dụ:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);
~~~

Nên chỉ rõ content type khi nguồn không cung cấp tên file hữu ích, loại file không thể suy luận đáng tin cậy hoặc ứng dụng muốn kiểm soát rõ MIME metadata. **Content-Type phải phù hợp với dữ liệu thật**, không chỉ dựa vào tên file mà người dùng gửi lên.

Tên **attachmentFilename** là tên hiển thị trong thư, không phải đường dẫn để Jakarta Mail tự tìm file. Nguồn dữ liệu mới quyết định byte nào được đọc. Vì thế có thể lấy dữ liệu từ một file trên filesystem nhưng đặt tên hiển thị là **invoice.pdf**.

## 5. Dùng ClassPathResource cho file được đóng gói cùng ứng dụng

Khi file cố định được lưu trong **src/main/resources**, có thể sử dụng **ClassPathResource**:

~~~text
src/
└── main/
    └── resources/
        └── mail/
            ├── terms.pdf
            └── brand-guide.pdf
~~~

Code:

~~~java
import org.springframework.core.io.ClassPathResource;

helper.addAttachment(
        "terms-and-conditions.pdf",
        new ClassPathResource("mail/terms.pdf"),
        "application/pdf"
);
~~~

**ClassPathResource** phù hợp với tài nguyên được đóng gói cùng ứng dụng. Khi chạy từ JAR, tài nguyên vẫn có thể được đọc từ classpath; ứng dụng không cần giả định rằng file nằm trong một thư mục filesystem có thể truy cập trực tiếp.

Điều cần lưu ý:

- Đường dẫn truyền vào ClassPathResource thường tính từ classpath root, ví dụ **mail/terms.pdf**.
- Không thêm tiền tố **src/main/resources** vào đường dẫn runtime.
- Tên file và chữ hoa/thường phải khớp với tài nguyên đã đóng gói.
- Không dùng ClassPathResource cho file người dùng upload vào một thư mục runtime bên ngoài classpath.

Nếu resource không có trong artifact đã build, lỗi đọc có thể xuất hiện khi helper hoặc mail transport yêu cầu mở stream. Việc code biên dịch thành công không chứng minh tài nguyên có mặt trong JAR.

## 6. Dùng FileSystemResource cho file trên máy chủ

Nếu file nằm trên filesystem, **FileSystemResource** là một lựa chọn:

~~~java
import org.springframework.core.io.FileSystemResource;
import java.nio.file.Path;

Path reportPath = Path.of("/var/app/reports/monthly-report.pdf");
FileSystemResource report = new FileSystemResource(reportPath);

helper.addAttachment(
        "monthly-report.pdf",
        report,
        "application/pdf"
);
~~~

FileSystemResource cung cấp stream bằng cách mở file tại đường dẫn đã cấu hình. Với file lớn, cách này tránh phải đọc toàn bộ nội dung vào một byte array trước khi tạo attachment.

Tuy nhiên, đường dẫn phải tồn tại và tiến trình ứng dụng phải có quyền đọc. Ngoài ra:

- Không lấy đường dẫn filesystem tùy ý từ HTTP request rồi đưa trực tiếp vào FileSystemResource.
- Kiểm tra đường dẫn nằm trong thư mục được phép; cân nhắc path traversal và symbolic link.
- File phải còn tồn tại và không bị thay thế/xóa trong lúc gửi.
- Nếu nhiều luồng có thể ghi đè file cùng lúc, hãy dùng tên/version riêng hoặc snapshot bất biến để tránh gửi nội dung khác với nội dung đã kiểm tra.

## 7. Dùng ByteArrayResource khi dữ liệu đã có trong bộ nhớ

Nếu ứng dụng đã có byte array, ví dụ file PDF được tạo từ một thư viện báo cáo, có thể bọc nó bằng **ByteArrayResource**:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] pdfBytes = createInvoicePdf();

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

**ByteArrayResource** là một implementation của Resource dựa trên byte array và có thể cung cấp stream mới đọc từ đầu cho mỗi lần mở. Đây là lựa chọn thuận tiện cho nội dung có kích thước vừa phải đã nằm trong bộ nhớ.

Hạn chế là dữ liệu đã chiếm bộ nhớ. Nếu nhiều email lớn được tạo đồng thời, mỗi byte array và phần MIME được serialize có thể làm tăng áp lực heap đáng kể. Không nên đọc một file rất lớn vào byte[] chỉ vì API addAttachment nhận InputStreamSource.

### Tạo InputStreamSource bằng lambda

Có thể tự cung cấp một nguồn mở stream mới:

~~~java
import java.io.ByteArrayInputStream;
import org.springframework.core.io.InputStreamSource;

byte[] pdfBytes = createInvoicePdf();

InputStreamSource source =
        () -> new ByteArrayInputStream(pdfBytes);

helper.addAttachment("invoice.pdf", source, "application/pdf");
~~~

Mỗi lần **getInputStream()** được gọi, lambda tạo một **ByteArrayInputStream** mới bắt đầu từ byte đầu tiên. Đây là đặc tính quan trọng làm cho source có thể được đọc lặp lại.

Với trường hợp đơn giản, **new ByteArrayResource(pdfBytes)** thường dễ đọc hơn. Lambda hữu ích khi cần tự định nghĩa cách mở nguồn.

## 8. Hợp đồng quan trọng: mỗi lần gọi phải có stream mới

Đây là điểm dễ gây lỗi nhất khi làm việc với InputStreamSource.

**Một InputStream có trạng thái đọc.** Sau khi đã đọc đến cuối, lần đọc tiếp theo không tự quay lại byte đầu. Nếu stream đã đóng, không thể dùng lại để đọc dữ liệu. Trong quá trình tạo và gửi MIME, Jakarta Mail có thể yêu cầu mở dữ liệu attachment thông qua DataSource nhiều hơn một lần.

Do đó, implementation của InputStreamSource nên trả về **một stream mới có thể đọc từ đầu** mỗi lần được gọi.

### Implementation phù hợp

~~~java
InputStreamSource source = () -> Files.newInputStream(reportPath);
~~~

Mỗi lần gọi sẽ mở một stream mới từ file, miễn là file vẫn còn và có thể đọc.

Hoặc:

~~~java
InputStreamSource source = () -> new ByteArrayInputStream(bytes);
~~~

Mỗi lần gọi tạo một stream mới từ cùng byte array.

### Implementation dễ lỗi

~~~java
InputStream stream = Files.newInputStream(reportPath);
InputStreamSource source = () -> stream;
~~~

Ở đây mọi lần gọi đều trả về **cùng một InputStream**. Sau lần đọc đầu, stream có thể đã ở cuối hoặc bị đóng. Lần đọc sau sẽ không còn dữ liệu như mong đợi, hoặc phát sinh IOException.

Không nên giữ một stream đang mở rồi bọc nó bằng lambda để giả vờ rằng nguồn có thể mở lại. **InputStreamSource là abstraction tạo stream, không phải cách đổi tên một stream one-shot.**

## 9. Vì sao InputStreamResource thường không phù hợp cho attachment?

Spring có class **InputStreamResource**, nhưng không phải cứ class nào implement InputStreamSource cũng có thể đọc lặp lại an toàn.

**InputStreamResource** thường đại diện cho một InputStream đã được mở sẵn. Nó được thiết kế cho tài nguyên một lần đọc; các lần gọi tiếp theo có thể trả về stream đã tiêu thụ hoặc không thể mở lại. Một số đường xử lý còn phát sinh lỗi khi cố đọc resource lần thứ hai.

Ví dụ cần thận trọng:

~~~java
InputStream opened = remoteService.openInvoiceStream();
InputStreamResource oneShot = new InputStreamResource(opened);

helper.addAttachment("invoice.pdf", oneShot, "application/pdf");
~~~

Đoạn này truyền một stream đã mở vào helper. Nếu quá trình tạo MIME yêu cầu đọc nguồn thêm lần nữa, stream không còn dữ liệu hoặc đã đóng. Nó cũng khiến vòng đời của stream khó kiểm soát hơn.

**Ưu tiên những nguồn có thể mở lại:**

- **ByteArrayResource** cho dữ liệu vừa phải đã nằm trong bộ nhớ.
- **ClassPathResource** cho file đóng gói trong ứng dụng.
- **FileSystemResource** cho file trên filesystem có thể đọc lại.
- Một **InputStreamSource tùy chỉnh** mở stream mới từ object storage, database hoặc nguồn khác.

Nếu chỉ có một stream từ API bên ngoài, hãy cân nhắc đọc nó thành byte[] với giới hạn dung lượng hoặc ghi ra file tạm rồi cung cấp một nguồn có thể mở lại.

## 10. Ví dụ tự viết InputStreamSource cho file

Khi muốn biểu diễn rõ việc mở file mới mỗi lần, có thể viết một implementation nhỏ:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.core.io.InputStreamSource;

public final class PathInputStreamSource implements InputStreamSource {

    private final Path path;

    public PathInputStreamSource(Path path) {
        this.path = path;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        return Files.newInputStream(path);
    }
}
~~~

Sử dụng:

~~~java
Path reportPath = Path.of("/var/app/reports/report.pdf");
InputStreamSource source = new PathInputStreamSource(reportPath);

helper.addAttachment("report.pdf", source, "application/pdf");
~~~

Mỗi lần gọi **getInputStream()**, implementation yêu cầu hệ điều hành mở file mới. Lớp này phù hợp để minh họa hợp đồng; trong ứng dụng thông thường, có thể dùng trực tiếp **FileSystemResource** để tránh tạo lớp không cần thiết.

### Kiểm soát tính ổn định của file

Mở stream mới không tự bảo đảm nội dung file không thay đổi giữa các lần đọc. Nếu một tiến trình khác ghi đè file trong lúc gửi, hai lần mở có thể đọc nội dung khác nhau. Với attachment quan trọng, hãy:

1. Dùng tên file riêng cho từng lần tạo báo cáo.
2. Hoàn tất ghi file trước khi tạo source.
3. Không sửa file trong suốt thời gian gửi.
4. Chỉ xóa file tạm sau khi lời gọi gửi đã hoàn thành và tài nguyên không còn cần thiết.

## 11. Lấy attachment từ dịch vụ lưu trữ hoặc hệ thống bên ngoài

Trong ứng dụng thực tế, file có thể nằm ở object storage, document service hoặc database. InputStreamSource giúp tách nơi lưu trữ khỏi việc xây MIME.

Ví dụ một dịch vụ lưu trữ cung cấp thao tác mở stream:

~~~java
InputStreamSource source = () -> objectStorage.openStream(
        bucketName,
        objectKey
);

helper.addAttachment(
        "customer-report.pdf",
        source,
        "application/pdf"
);
~~~

**objectStorage.openStream(...)** là API giả định của hệ thống lưu trữ, không phải API Spring. Điều quan trọng là mỗi lần được gọi phải trả về một stream mới đọc cùng một phiên bản object.

### Cần chú ý khi mở stream từ remote storage

- **Có thể đọc lại:** source phải mở một request/stream mới khi được yêu cầu lần nữa.
- **Cùng một phiên bản dữ liệu:** nếu object có thể thay đổi, nên pin version hoặc dùng key bất biến trong suốt quá trình gửi.
- **Timeout:** việc mở stream có thể bị treo do mạng; cần giới hạn thời gian và xử lý lỗi.
- **Quyền truy cập:** credential dùng để tải file phải có quyền tối thiểu cần thiết.
- **Dung lượng:** cần kiểm tra kích thước trước khi gửi để không tạo thông điệp vượt giới hạn SMTP/ESP.
- **Đóng kết nối:** mỗi stream cần được quản lý và đóng đúng cách sau khi được đọc.

Không tạo source bằng cách tải dữ liệu từ một URL tùy ý do người dùng cung cấp. Việc server truy cập URL không được kiểm soát có thể dẫn tới **SSRF**, đọc tài nguyên nội bộ hoặc lạm dụng băng thông.

## 12. Khi nguồn chỉ mở được một lần: byte array hay file tạm?

Một số API trả về một InputStream one-shot, ví dụ response body của HTTP client hoặc stream lấy từ một tiến trình sinh file. Nếu truyền trực tiếp stream này vào helper, có thể vi phạm yêu cầu đọc lại.

Có hai chiến lược phổ biến:

### Chiến lược A — Đọc vào byte array

~~~java
byte[] content;

try (InputStream input = remoteClient.openDocument(documentId)) {
    content = input.readAllBytes();
}

InputStreamSource repeatable = new ByteArrayResource(content);
helper.addAttachment("document.pdf", repeatable, "application/pdf");
~~~

Ưu điểm:

- Dữ liệu nằm trong bộ nhớ và có thể mở lại nhiều lần.
- Code đơn giản, dễ kiểm soát vòng đời stream nguồn.
- Phù hợp với file nhỏ/vừa có giới hạn kích thước rõ ràng.

Hạn chế:

- Toàn bộ file chiếm heap.
- Nhiều attachment đồng thời có thể gây áp lực bộ nhớ.
- **readAllBytes()** không giới hạn dung lượng; không nên dùng trực tiếp với nguồn không tin cậy hoặc file có thể rất lớn.

Trong production, cần kiểm tra kích thước trước hoặc dùng cơ chế đọc có giới hạn để từ chối file quá lớn.

### Chiến lược B — Ghi ra file tạm

~~~java
Path tempFile = Files.createTempFile("mail-attachment-", ".pdf");

try (InputStream input = remoteClient.openDocument(documentId)) {
    Files.copy(input, tempFile, StandardCopyOption.REPLACE_EXISTING);
}

InputStreamSource repeatable = () -> Files.newInputStream(tempFile);
helper.addAttachment("document.pdf", repeatable, "application/pdf");

// Giữ tempFile tồn tại đến khi send(message) hoàn tất.
~~~

Đây là ví dụ minh họa vòng đời; cần bổ sung try/finally để xóa file tạm sau khi gửi hoặc sau khi xử lý lỗi. Không xóa file ngay sau **addAttachment(...)** nếu transport còn chưa đọc nội dung.

Ưu điểm:

- Không giữ toàn bộ file lớn trong heap.
- File có thể được mở lại từ đầu.
- Dễ tính checksum hoặc quét nội dung trước khi gửi.

Hạn chế:

- Cần dung lượng đĩa và chính sách dọn file tạm.
- Cần phân quyền thư mục, tên file an toàn và tránh truy cập đồng thời.
- Phải bảo đảm file không bị xóa trước khi mail transport đọc xong.

### Chọn chiến lược nào?

| Kích thước và nguồn | Cách thường phù hợp |
|---|---|
| Logo hoặc file nhỏ đã có byte[] | **ByteArrayResource** |
| File cố định trong ứng dụng | **ClassPathResource** |
| File lớn đã nằm trên đĩa | **FileSystemResource** |
| Remote object có API mở stream mới | **InputStreamSource tùy chỉnh** |
| Remote response chỉ đọc được một lần, file nhỏ/vừa | Đọc có giới hạn vào **ByteArrayResource** |
| Remote response one-shot, file lớn | Spool ra file tạm rồi mở lại bằng InputStreamSource |

## 13. Tên file và Content-Type của attachment

Hai thông tin này được email client dùng để hiển thị và xử lý file:

- **Filename**: tên hiển thị cho người nhận, ví dụ **invoice-2026.pdf**.
- **Content-Type**: kiểu dữ liệu MIME, ví dụ **application/pdf**, **image/png**, **text/csv**.

Ví dụ:

~~~java
helper.addAttachment(
        "invoice-2026.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf"
);
~~~

### Filename không phải đường dẫn filesystem

Đừng truyền đường dẫn đầy đủ hoặc dữ liệu tùy ý từ người dùng vào filename:

~~~java
// Không nên dùng trực tiếp giá trị upload do người dùng kiểm soát.
helper.addAttachment(upload.getOriginalFilename(), resource);
~~~

Tên file gốc có thể chứa đường dẫn, ký tự điều khiển hoặc tên gây nhầm lẫn. Hãy tạo tên hiển thị an toàn từ nghiệp vụ hoặc làm sạch theo quy tắc của ứng dụng. Ví dụ:

~~~java
String attachmentName = "invoice-" + validatedInvoiceNumber + ".pdf";
~~~

Trong ví dụ, **validatedInvoiceNumber** phải là mã đã được kiểm tra và không chứa ký tự điều khiển hoặc thành phần đường dẫn.

### Content-Type cần phản ánh dữ liệu thật

Không nên tin tuyệt đối vào phần mở rộng file do người dùng cung cấp. Một file tên **report.pdf** chưa chắc là PDF hợp lệ. Nên:

1. Kiểm tra nguồn dữ liệu và quyền truy cập.
2. Xác định định dạng theo quy tắc ứng dụng hoặc kiểm tra chữ ký file khi cần.
3. Giới hạn các loại MIME được phép gửi.
4. Đặt Content-Type tương ứng.
5. Quét malware hoặc áp dụng chính sách kiểm tra file theo yêu cầu hệ thống.

Content-Type chỉ là metadata MIME; nó không chuyển đổi một file sai định dạng thành file hợp lệ và cũng không bảo vệ người nhận khỏi nội dung độc hại.

## 14. Kết hợp attachment với HTML và plain text

Một email có thể vừa chứa bản plain text, HTML và một file đính kèm. Khi đó **MimeMessageHelper** giúp tạo cấu trúc MIME phù hợp:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendInvoice(
        JavaMailSender sender,
        String recipient,
        Path invoicePath
) throws MessagingException {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            true,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("billing@example.com");
    helper.setTo(recipient);
    helper.setSubject("Hóa đơn của bạn");
    helper.setText(
            "Hóa đơn được đính kèm. Vui lòng đăng nhập để xem chi tiết.",
            "<html lang=\"vi\"><body>"
                    + "<h2>Hóa đơn của bạn</h2>"
                    + "<p>Hóa đơn được đính kèm trong email này.</p>"
                    + "</body></html>"
    );

    helper.addAttachment(
            "invoice.pdf",
            new FileSystemResource(invoicePath),
            "application/pdf"
    );

    sender.send(message);
}
~~~

Ví dụ giả định **invoicePath** là file đã được tạo, có quyền đọc và còn tồn tại trong thời gian gửi. **MimeMessageHelper** ở chế độ multipart cho phép kết hợp body với attachment; nếu thêm inline resource, có thể chọn multipart mode phù hợp như **MULTIPART_MODE_MIXED_RELATED**.

Một cấu trúc MIME khái quát:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    └── application/pdf
        └── Content-Disposition: attachment
~~~

Đây là sơ đồ ý nghĩa. Cây MIME chính xác do helper/Jakarta Mail xây dựng có thể khác theo chế độ multipart và có thêm lớp **multipart/related** khi có hình inline.

## 15. Nhiều attachment trong một email

Có thể gọi **addAttachment(...)** nhiều lần trên cùng helper:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);

helper.addAttachment(
        "terms.pdf",
        new ClassPathResource("mail/terms.pdf"),
        "application/pdf"
);

helper.addAttachment(
        "summary.csv",
        new ClassPathResource("mail/summary.csv"),
        "text/csv"
);
~~~

Mỗi lời gọi thêm một MIME part riêng vào cùng thông điệp. Người nhận sẽ thấy các file theo tên attachment được thiết lập.

### Lưu ý khi thêm nhiều file

- Tính **tổng dung lượng** của tất cả attachment cùng body, header và phần MIME encoding.
- Không tạo quá nhiều byte array lớn cùng lúc.
- Kiểm tra quyền người nhận với từng file, không chỉ với email nói chung.
- Đặt filename riêng, rõ ràng và không trùng gây nhầm lẫn.
- Xác định content type cho từng file.
- Nếu một nguồn không đọc được, chuẩn bị cách xử lý lỗi trước khi gửi.

Nếu attachment đến từ nhiều nguồn, có thể lưu một danh sách đối tượng mô tả tên file, content type và InputStreamSource rồi lặp qua danh sách để gọi helper. Tuy nhiên, danh sách này nên được validation trước và mỗi source phải còn khả năng mở stream tại thời điểm gửi.

## 16. Quản lý vòng đời của stream và resource

**Không nên tự mở một InputStream rồi quên đóng** chỉ để truyền nó cho helper. Khi dùng InputStreamSource, hãy để nguồn chịu trách nhiệm mở stream khi được yêu cầu và bảo đảm mỗi stream được quản lý đúng vòng đời.

Một số nguyên tắc:

- Không mở stream ở controller rồi giữ nó xuyên qua nhiều tầng nghiệp vụ.
- Không đóng resource trước khi mail transport đọc xong.
- Không xóa file tạm ngay sau khi gọi addAttachment; giữ nó đến khi **send(...)** hoàn tất hoặc thất bại.
- Với nguồn remote, mỗi lần mở phải có timeout và quyền truy cập thích hợp.
- Không chia sẻ một InputStream có trạng thái đọc giữa nhiều lần gửi hoặc nhiều thread.
- Nếu cùng một source được dùng cho nhiều email, cần chắc chắn nó có thể mở mới và dữ liệu không thay đổi giữa các lần.

### Ví dụ giữ file tạm đến hết lời gọi send

~~~java
Path tempFile = Files.createTempFile("invoice-", ".pdf");

try {
    try (InputStream input = documentService.openInvoice(invoiceId)) {
        Files.copy(
                input,
                tempFile,
                StandardCopyOption.REPLACE_EXISTING
        );
    }

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            true,
            "UTF-8"
    );
    helper.setTo(recipient);
    helper.setFrom("billing@example.com");
    helper.setSubject("Hóa đơn");
    helper.setText("Hóa đơn được đính kèm.");
    helper.addAttachment(
            "invoice.pdf",
            new FileSystemResource(tempFile),
            "application/pdf"
    );

    // Lời gọi gửi cần hoàn tất trước khi file tạm bị xóa.
    mailSender.send(message);
} finally {
    Files.deleteIfExists(tempFile);
}
~~~

Đây là ví dụ đồng bộ, giả định **documentService.openInvoice(...)** trả về InputStream và mailSender.send(...) thực hiện nộp thông điệp trước khi trả về. Nếu ứng dụng chuyển việc gửi sang background task, file phải tồn tại đến lúc task thực sự hoàn thành; không thể xóa ngay khi enqueue.

Trong môi trường nhiều worker, cần quản lý quyền file tạm, tên file duy nhất, cleanup khi process bị dừng đột ngột và dung lượng thư mục tạm.

## 17. Kích thước attachment và hiệu năng

Dùng InputStreamSource **không có nghĩa toàn bộ quá trình gửi luôn streaming với bộ nhớ hằng số**. Jakarta Mail có thể đọc dữ liệu và mã hóa/serialize thông điệp khi gửi; SMTP server cũng có giới hạn kích thước message. Một file lớn có thể làm tăng bộ nhớ, thời gian gửi và dung lượng queue.

Các yếu tố ảnh hưởng:

1. **Kích thước file gốc**.
2. **MIME transfer encoding**: dữ liệu nhị phân thường được mã hóa base64, làm phần biểu diễn lớn hơn dữ liệu gốc.
3. **Số attachment** và tổng kích thước.
4. **Số email gửi đồng thời**.
5. **Hạn mức của SMTP/ESP** và mail server đích.
6. **Cách triển khai transport** và tài nguyên heap/disk của ứng dụng.

### Ước lượng dung lượng

Base64 thường làm dữ liệu nhị phân tăng khoảng một phần ba, chưa kể CRLF, header và boundary MIME. Vì vậy, một file 9 MB có thể chiếm khoảng 12 MB phần base64 trong thông điệp trước khi cộng nội dung khác. Đây là ước lượng để lập ngân sách, không phải kích thước chính xác của mọi email.

Nếu file lớn hoặc có nhiều người nhận, cân nhắc gửi một **liên kết tải xuống an toàn** thay vì đính kèm trực tiếp. Link cần có HTTPS, quyền truy cập, thời hạn và khả năng thu hồi phù hợp; không biến URL công khai thành cách thay thế bảo vệ dữ liệu.

### Giới hạn kích thước phải lấy từ nhà cung cấp

Spring Framework Mail không đặt một giới hạn chung áp dụng cho tất cả SMTP server. Provider có thể giới hạn:

- Kích thước toàn bộ email.
- Kích thước từng file.
- Số lượng attachment.
- Tần suất và tổng dung lượng gửi.
- Số người nhận trong một message.

Ứng dụng nên kiểm tra trước để từ chối hoặc chọn phương thức phân phối khác thay vì chờ SMTP trả lỗi ở cuối quy trình.

## 18. Xử lý lỗi khi nguồn attachment không đọc được

Có thể lỗi xảy ra ở nhiều thời điểm:

| Giai đoạn | Ví dụ lỗi | Hướng điều tra |
|---|---|---|
| Chuẩn bị source | File không tồn tại, quyền đọc bị từ chối | Kiểm tra đường dẫn, classpath và quyền |
| Mở stream | InputStreamSource.getInputStream() ném IOException | Xem nguồn lưu trữ, kết nối remote, vòng đời file |
| Đọc stream | Dữ liệu bị cắt, remote stream timeout | Kiểm tra log nguồn, kích thước và checksum |
| Dựng MIME | Header, filename hoặc content type không hợp lệ | Kiểm tra helper và metadata |
| Nộp SMTP | Message quá lớn, relay từ chối, kết nối lỗi | Xem MailException và SMTP response |
| Sau SMTP acceptance | Mailbox đích bounce hoặc quarantine | Xem event của ESP và chính sách phía nhận |

Trong Spring Mail, các lỗi gửi có thể xuất hiện dưới họ **MailException**, ví dụ **MailSendException**. Khi thao tác với MimeMessageHelper/Jakarta Mail, các lỗi chuẩn bị MIME có thể phát sinh dưới dạng **MessagingException**; lỗi đọc nguồn có thể nằm trong nguyên nhân gốc hoặc được bọc bởi lớp gửi.

Ví dụ phân biệt lỗi nguồn trước khi gọi sender:

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;

try {
    mailSender.send(message);
} catch (MailException ex) {
    // Ghi nhận notification ID, attempt ID và nguyên nhân an toàn.
    // Kiểm tra xem SMTP đã chấp nhận dữ liệu hay chưa trước khi retry.
    throw ex;
}
~~~

Không nên retry vô hạn với nguồn đã mất, file hỏng hoặc sai quyền. Với timeout sau khi gửi DATA, trạng thái có thể chưa rõ: server có thể đã nhận email dù ứng dụng chưa nhận được phản hồi. Retry khi chưa đối soát có thể gây gửi trùng.

## 19. Bảo mật khi gửi file đính kèm

File đính kèm có thể chứa hóa đơn, báo cáo, hồ sơ hoặc dữ liệu cá nhân. **InputStreamSource chỉ giúp cung cấp byte; nó không kiểm soát quyền được phép gửi những byte đó.**

Các bước nên cân nhắc:

1. **Kiểm tra quyền nghiệp vụ:** người nhận có được phép xem file này không?
2. **Kiểm tra nguồn:** file lấy từ đúng bản ghi/tài khoản/tenant hay không?
3. **Giới hạn dung lượng:** ngăn file quá lớn gây cạn bộ nhớ hoặc quota.
4. **Xác định định dạng:** kiểm tra loại dữ liệu thực tế, không tin tuyệt đối filename hay MIME type do người dùng khai báo.
5. **Quét malware:** áp dụng quy trình kiểm tra theo loại file và yêu cầu tổ chức.
6. **Tên file an toàn:** loại bỏ path, ký tự điều khiển hoặc tên gây nhầm lẫn.
7. **Bảo vệ log:** không ghi nội dung file, OTP, token hoặc thông tin nhạy cảm ra log thông thường.
8. **Vòng đời lưu trữ:** xóa file tạm đúng lúc và tuân thủ chính sách retention.

### Tránh path traversal

Không dùng đường dẫn do người dùng nhập trực tiếp:

~~~java
// Không an toàn nếu userPath đến từ request mà không được kiểm soát.
FileSystemResource resource = new FileSystemResource(userPath);
~~~

Thay vào đó, tìm file thông qua ID nghiệp vụ đã xác thực, sau đó resolve nó trong thư mục được phép và kiểm tra đường dẫn thực nằm trong vùng lưu trữ dự kiến. Không chỉ kiểm tra chuỗi bắt đầu bằng thư mục gốc vì symbolic link có thể dẫn ra ngoài phạm vi.

### Không gửi nhầm dữ liệu giữa các tenant

Trong hệ thống nhiều khách hàng/tenant, cần xác thực rằng tài nguyên thuộc đúng tenant trước khi tạo InputStreamSource. Một source mở đúng file nhưng file thuộc người dùng khác vẫn là lỗi phân quyền nghiêm trọng.

## 20. Ví dụ gửi attachment từ dữ liệu sinh trong bộ nhớ

Giả sử ứng dụng tạo một báo cáo PDF bằng thư viện xuất file và nhận lại byte array:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendGeneratedReport(
        JavaMailSender sender,
        String recipient,
        byte[] pdfBytes
) throws MessagingException {
    if (pdfBytes == null || pdfBytes.length == 0) {
        throw new IllegalArgumentException("PDF không có dữ liệu");
    }

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            true,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("reports@example.com");
    helper.setTo(recipient);
    helper.setSubject("Báo cáo đã sẵn sàng");
    helper.setText("Báo cáo PDF được đính kèm trong email này.");
    helper.addAttachment(
            "report.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
    );

    sender.send(message);
}
~~~

Đoạn mã giả định **pdfBytes** đã được tạo từ một nguồn đáng tin cậy và có giới hạn dung lượng phù hợp. Kiểm tra length lớn hơn 0 chỉ phát hiện mảng rỗng, không chứng minh byte array là một PDF hợp lệ. Nếu dữ liệu đến từ người dùng hoặc dịch vụ khác, cần kiểm tra định dạng theo chính sách ứng dụng.

## 21. Ví dụ gửi file lớn từ filesystem

Nếu báo cáo lớn đã được tạo trên đĩa, có thể truyền FileSystemResource để tránh đọc toàn bộ file vào byte array:

~~~java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;

Path reportPath = reportGenerator.createReportFile();

helper.addAttachment(
        "annual-report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf"
);

mailSender.send(message);
~~~

**reportGenerator.createReportFile()** là API giả định của ứng dụng. File cần tồn tại, đọc được và không bị xóa/thay đổi trong thời gian transport sử dụng source. Với file tạm, hãy quản lý cleanup sau khi lời gọi gửi kết thúc và có cơ chế dọn file mồ côi khi process dừng bất thường.

FileSystemResource giảm nhu cầu giữ một byte array của toàn bộ file trong code ứng dụng, nhưng không bảo đảm Jakarta Mail hoặc SMTP transport không cần bộ nhớ bổ sung trong quá trình serialize và gửi.

## 22. Kiểm tra việc tạo MIME và attachment

Khi phát triển, có thể kiểm tra message trước khi gửi thật bằng cách tạo **MimeMessage** với Jakarta Mail Session thử nghiệm và xác nhận nội dung MIME part. Mục tiêu là kiểm tra:

- Có đúng số lượng attachment không.
- Filename có đúng và không chứa đường dẫn ngoài ý muốn không.
- Content-Type phản ánh đúng định dạng.
- Dữ liệu được đọc đầy đủ.
- Plain text/HTML body vẫn đúng khi có attachment.
- Source có thể mở stream mới khi được yêu cầu lại.

Một InputStreamSource đơn giản có thể được kiểm tra số lần mở:

~~~java
AtomicInteger openCount = new AtomicInteger();
byte[] bytes = "sample".getBytes(StandardCharsets.UTF_8);

InputStreamSource source = () -> {
    openCount.incrementAndGet();
    return new ByteArrayInputStream(bytes);
};

InputStream first = source.getInputStream();
InputStream second = source.getInputStream();

// Hai stream là hai đối tượng riêng và đều đọc từ đầu.
~~~

Đây là ví dụ kiểm tra hợp đồng nguồn, không phải kiểm thử SMTP. Việc email được nộp và chuyển phát cần một integration test với SMTP test server hoặc sandbox phù hợp.

Không cần mở file thật của khách hàng hoặc gửi email tới người nhận production để kiểm tra cấu trúc MIME.

## 23. Những lỗi thường gặp khi dùng InputStreamSource

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Attachment rỗng hoặc thiếu byte | Source trả lại stream đã đọc hết | Mở stream mới mỗi lần gọi |
| IOException hoặc lỗi stream đã đóng | Truyền một InputStream one-shot qua InputStreamResource | Dùng ByteArrayResource, FileSystemResource hoặc source có thể mở lại |
| Không tìm thấy file classpath | Đường dẫn runtime sai hoặc resource không được đóng gói | Kiểm tra src/main/resources và classpath path |
| File trên server không đọc được | Sai đường dẫn hoặc quyền filesystem | Kiểm tra đường dẫn và quyền tiến trình |
| Attachment bị gửi nội dung cũ/mới không nhất quán | File bị thay đổi giữa các lần mở | Dùng snapshot/version bất biến |
| Gửi lỗi do không có multipart | Helper được tạo với multipart=false | Bật multipart khi khởi tạo MimeMessageHelper |
| File hiển thị tên lạ | Filename không hợp lệ hoặc không được chuẩn hóa | Đặt tên hiển thị an toàn và rõ ràng |
| File mở sai ứng dụng | Content-Type không đúng | Xác định media type từ định dạng thực tế |
| Email vượt giới hạn | File lớn hoặc nhiều attachment | Kiểm tra quota, tối ưu file hoặc gửi link tải an toàn |
| Heap tăng cao khi gửi đồng thời | Đọc nhiều file lớn vào byte[] | Dùng nguồn repeatable trên disk/remote, giới hạn concurrency |
| File tạm bị mất khi gửi nền | Xóa file ngay sau khi enqueue | Giữ file đến khi worker hoàn tất |
| Retry gửi email trùng | Timeout sau khi SMTP có thể đã nhận message | Ghi attempt, đối soát trạng thái trước retry |
| Gửi nhầm file của tenant khác | Không kiểm tra quyền trước khi tạo source | Xác minh ownership và quyền truy cập theo tenant |

## 24. Lựa chọn InputStreamSource theo tình huống

| Nguồn attachment | Lựa chọn gợi ý | Lý do |
|---|---|---|
| File tĩnh trong JAR | **ClassPathResource** | Đọc từ classpath, không phụ thuộc thư mục làm việc |
| File trên ổ đĩa máy chủ | **FileSystemResource** | Mở lại file theo đường dẫn |
| Byte array có sẵn, kích thước vừa phải | **ByteArrayResource** | Tạo stream mới từ bộ nhớ |
| Nguồn tự mở được stream mới | **InputStreamSource** tùy chỉnh | Kiểm soát cách lấy dữ liệu |
| HTTP response stream one-shot | Đọc có giới hạn vào byte[] hoặc spool file tạm | Không tái sử dụng stream đã tiêu thụ |
| Object storage có version và API stream mới | **InputStreamSource** mở stream theo version | Có thể đọc lại cùng dữ liệu |
| File lớn đã có trên đĩa | **FileSystemResource** | Tránh thêm một byte array lớn trong ứng dụng |

Không có lựa chọn tốt nhất cho mọi trường hợp. Cần cân bằng kích thước, khả năng đọc lại, vòng đời tài nguyên, độ ổn định dữ liệu, độ trễ và mức tiêu thụ bộ nhớ/đĩa.

## 25. Ghi nhớ

**InputStreamSource** là abstraction của Spring để cung cấp một InputStream khi cần. Trong Spring Framework Mail, **MimeMessageHelper.addAttachment(...)** nhận InputStreamSource để tạo MIME part cho file đính kèm. Ứng dụng có thể dùng **ClassPathResource**, **FileSystemResource**, **ByteArrayResource** hoặc implementation riêng, tùy nguồn dữ liệu.

Nguyên tắc quan trọng nhất là **mỗi lần getInputStream() phải có khả năng trả về một stream mới đọc từ đầu**. Tránh bọc một InputStream đã mở hoặc một nguồn one-shot như **InputStreamResource** rồi giả định nó có thể đọc nhiều lần. Với nguồn lớn, ưu tiên cách mở lại từ file hoặc object storage; với dữ liệu nhỏ/vừa trong bộ nhớ, ByteArrayResource đơn giản và thuận tiện.

Khi gửi attachment, bật multipart, cung cấp filename và Content-Type đúng, giữ nguồn còn tồn tại trong suốt quá trình gửi, kiểm soát dung lượng/quyền truy cập và xử lý lỗi ở tầng Spring Mail. **InputStreamSource giải quyết cách cung cấp byte cho MIME; ứng dụng vẫn chịu trách nhiệm bảo đảm byte đó đúng, an toàn và được phép gửi tới người nhận.**
