# Thêm attachment từ File, InputStream và Resource

Trong **Spring Framework Mail**, `MimeMessageHelper` giúp ứng dụng gửi email có tệp đính kèm (*attachment*) mà không cần tự dựng các ranh giới MIME, tự mã hóa Base64 hay ghép header email bằng chuỗi. Tuy nhiên, tệp đính kèm có thể đến từ nhiều nguồn khác nhau: một file đang nằm trên ổ đĩa, dữ liệu được sinh ngay trong bộ nhớ, một tài nguyên trong classpath hoặc một luồng byte từ hệ thống lưu trữ.

Điểm quan trọng không chỉ là truyền được dữ liệu vào `addAttachment(...)`. **Jakarta Mail có thể cần đọc dữ liệu nhiều lần trong quá trình chuẩn bị và gửi MIME message.** Vì thế, việc phân biệt `File`, `InputStream`, `InputStreamSource` và `Resource` có ý nghĩa trực tiếp đối với khả năng gửi thành công, sử dụng bộ nhớ và xử lý lỗi.

Bài học trình bày cách thêm attachment từ các nguồn này, lựa chọn overload phù hợp của `MimeMessageHelper`, xác định `Content-Type`, xử lý stream an toàn và tổ chức mã gửi mail trong Spring Boot.

## 1. Attachment là gì trong cấu trúc MIME?

Một email không chỉ gồm chuỗi `Subject` và `Text`. Khi có file đính kèm, email thường được biểu diễn dưới dạng **MIME multipart message**, trong đó phần thân thư và mỗi attachment là một **MIME part** riêng.

Ví dụ cấu trúc khái niệm:

```text
MimeMessage
└── multipart/mixed
    ├── text/plain; charset=UTF-8
    │   └── "Hóa đơn tháng này được đính kèm."
    ├── application/pdf
    │   ├── Content-Disposition: attachment
    │   ├── filename="invoice.pdf"
    │   └── dữ liệu PDF được mã hóa phù hợp cho email
    └── text/csv
        ├── Content-Disposition: attachment
        ├── filename="orders.csv"
        └── dữ liệu CSV
```

Một part đính kèm thường có các header như:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64
```

Ba thông tin cần phân biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| `Content-Type` | Loại nội dung, ví dụ `application/pdf`, `image/png` hoặc `text/csv` |
| `Content-Disposition` | Cách mail client xử lý part; `attachment` thường khiến tệp xuất hiện ở khu vực đính kèm |
| `Content-Transfer-Encoding` | Cách byte được biểu diễn để vận chuyển, thường là `base64` với dữ liệu nhị phân |

Khi dùng `MimeMessageHelper.addAttachment(...)`, **ứng dụng cung cấp tên file, nguồn dữ liệu và tùy chọn media type**; helper kết hợp Jakarta Mail tạo phần MIME tương ứng.

**Không tự chuyển byte PDF thành một chuỗi văn bản rồi gọi `setText(...)`.** Nội dung của PDF, ZIP hay PNG phải được chuyển đến attachment như **byte gốc**.

## 2. Các overload `addAttachment(...)` thường gặp

`MimeMessageHelper` cung cấp nhiều cách thêm attachment:

```java
// Nguồn là file vật lý.
helper.addAttachment(String attachmentFilename, File file);

// Nguồn byte có thể cung cấp InputStream mới.
helper.addAttachment(
        String attachmentFilename,
        InputStreamSource inputStreamSource
);

// Nguồn byte và media type được chỉ định rõ.
helper.addAttachment(
        String attachmentFilename,
        InputStreamSource inputStreamSource,
        String contentType
);

// Nguồn dữ liệu theo Jakarta Activation.
helper.addAttachment(
        String attachmentFilename,
        DataSource dataSource
);
```

Các dòng trên là **minh họa chữ ký phương thức**, không phải những lệnh Java hoàn chỉnh có thể chạy riêng lẻ.

| Nguồn dữ liệu | Đối tượng nên dùng | Khi nào phù hợp? |
| --- | --- | --- |
| File trên đĩa | `java.io.File` | Tệp đã tồn tại dưới đường dẫn cụ thể |
| File trên đĩa theo abstraction Spring | `FileSystemResource` | Muốn dùng API `Resource` để đọc file |
| Resource đóng gói trong ứng dụng | `ClassPathResource` | Đính kèm tài liệu mẫu hoặc file có sẵn trong classpath |
| Byte đã có trong RAM | `ByteArrayResource` | PDF/CSV được sinh ra trong bộ nhớ |
| Nguồn stream cần mở mới mỗi lần | `InputStreamSource` tự triển khai | File/object storage hoặc nguồn truy xuất tùy chỉnh |
| Một `InputStream` đang mở sẵn | **Không nên truyền trực tiếp như nguồn chỉ đọc một lần** | Cần chuyển thành nguồn **mở lại được** hoặc lưu tạm |

Điểm chung: `MimeMessageHelper` cần **một nguồn byte đủ ổn định** trong suốt quá trình tạo và gửi email.

## 3. Chuẩn bị Spring Boot và `JavaMailSender`

Để gửi mail trong Spring Boot, ứng dụng thường dùng starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Ví dụ `application.yml` với SMTP submission hỗ trợ STARTTLS trên cổng 587:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

Giá trị trong `${...}` là placeholder môi trường theo cú pháp Spring sau khi ghi file. Cổng 587/STARTTLS chỉ phù hợp khi máy chủ hỗ trợ chế độ đó; những endpoint dùng implicit TLS trên 465 cần thiết lập khác. Credential SMTP nên lấy từ môi trường hoặc secret manager, không hardcode.

`spring.mail.default-encoding=UTF-8` hỗ trợ ký tự tiếng Việt trong **các phần văn bản**. Nó không thay đổi byte PDF hay tự xác định `Content-Type` cho attachment.

### 3.1. Tạo MIME message có chế độ multipart

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Tài liệu đính kèm");
helper.setText("Vui lòng xem tài liệu trong email.", false);
```

Tham số `true` trong constructor bật chế độ **multipart**. Đây là tiền đề khi thêm attachment bằng helper. Nếu tạo helper không ở chế độ multipart rồi gọi `addAttachment(...)`, thao tác không phù hợp với cấu trúc message và có thể gây `IllegalStateException`.

Tham số `"UTF-8"` là **charset** cho nội dung văn bản, không phải một media type và không có nghĩa file nhị phân sẽ được chuyển thành chuỗi UTF-8.

### 3.2. `MULTIPART_MODE_MIXED_RELATED` khi thư có cả HTML và file

Với email HTML, ảnh inline và attachment, có thể chọn chế độ:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
```

Helper có thể tổ chức các phần MIME dạng `multipart/mixed` và `multipart/related` để tách attachment với tài nguyên inline liên quan đến nội dung HTML. Cấu trúc cụ thể phụ thuộc việc thêm các part; ứng dụng không cần tự đặt `boundary`.

Trong ví dụ chỉ có text và attachment, `new MimeMessageHelper(message, true, "UTF-8")` đã đủ cho mục đích minh họa.

## 4. Cách 1 — Thêm attachment từ `java.io.File`

Khi tệp đã nằm trên ổ đĩa, cách trực tiếp là:

```java
import java.io.File;

File file = new File("/srv/app/reports/invoice.pdf");
helper.addAttachment("invoice.pdf", file);
```

`File` là đối tượng mô tả **đường dẫn tới file**, không phải toàn bộ byte của file đã được nạp vào RAM. Jakarta Mail có thể đọc dữ liệu của file khi chuẩn bị/serialize message.

### 4.1. Ví dụ một service gửi file từ đĩa

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

@Service
public class FileAttachmentMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public FileAttachmentMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendReport(String recipient, Path reportPath)
            throws MessagingException {
        if (!Files.isRegularFile(reportPath) ||
                !Files.isReadable(reportPath)) {
            throw new IllegalArgumentException("Report file is unavailable");
        }

        File reportFile = reportPath.toFile();
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name()
        );

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Báo cáo định kỳ");
        helper.setText("Báo cáo được gửi trong tệp đính kèm.", false);

        helper.addAttachment("report.pdf", reportFile);

        mailSender.send(message);
    }
}
```

Ví dụ **giả định file thật sự là PDF** và nằm trên một filesystem mà đường dẫn `Path` có thể chuyển thành `File`. Nếu file là CSV hoặc XLSX, tên file và media type cần thay đổi theo định dạng thực tế.

Ở mức nghiệp vụ, cần đảm bảo file không bị xóa, đổi tên hoặc ghi đè khi Jakarta Mail đang đọc. Một kiểm tra `Files.isReadable(...)` trước đó **không bảo đảm** file sẽ vẫn tồn tại vào mọi thời điểm sau; khi có nhiều process cùng thao tác, nên dùng tệp tạm riêng hoặc cơ chế snapshot thích hợp.

### 4.2. Ưu điểm và hạn chế của `File`

Ưu điểm:

- Code ngắn khi file đã được tạo trên ổ đĩa.
- Không cần tạo sẵn `byte[]` của toàn bộ file trong bộ nhớ ứng dụng.
- Có thể mở file lại qua đường dẫn khi thư viện cần đọc nhiều lần.

Hạn chế:

- File phải tồn tại và được cấp quyền đọc trên máy chạy ứng dụng.
- Tài nguyên trong JAR hoặc object storage không nhất thiết có đường dẫn `File` hợp lệ.
- File có thể bị xóa/thay đổi giữa thời điểm tạo message và thời điểm Jakarta Mail đọc.
- Thao tác với đường dẫn từ người dùng có thể dẫn tới **path traversal** hoặc truy cập file không được phép nếu không kiểm soát.
- Dù không tự nạp tất cả byte vào `byte[]`, đường gửi vẫn tiêu thụ RAM, CPU và dung lượng truyền; không có bảo đảm “zero-copy”.

**Không đưa trực tiếp một đường dẫn tùy ý do client cung cấp vào `new File(...)` rồi gửi**. File phải được chọn từ tập hợp mà ứng dụng có quyền truy cập theo nghiệp vụ.

## 5. Cách 2 — `InputStream` và `InputStreamSource`

Đây là phần dễ nhầm nhất.

### 5.1. Một `InputStream` đang mở là luồng đọc có trạng thái

`InputStream` của Java đại diện cho một luồng byte đang được đọc:

```java
InputStream stream = Files.newInputStream(path);
```

Sau khi các byte đã được tiêu thụ, stream thường **không tự quay về đầu**. Một số implementation hỗ trợ đánh dấu và quay lại qua `mark/reset`, nhưng không nên giả định có thể đọc lại toàn bộ nội dung hoặc mở stream thêm lần nữa từ cùng một instance.

Trong khi đó, quá trình tạo MIME message có thể cần đọc attachment **hơn một lần**; chẳng hạn để xác định transfer encoding hoặc viết phần dữ liệu ra luồng gửi. Do vậy, API của `MimeMessageHelper` nhận **`InputStreamSource`**, không phải một `InputStream` đơn lẻ.

### 5.2. `InputStreamSource` là một factory cho stream

`InputStreamSource` thuộc package:

```java
import org.springframework.core.io.InputStreamSource;
```

Về ý nghĩa, nó có hợp đồng:

```java
InputStream getInputStream() throws IOException;
```

Mỗi lần được gọi, implementation phù hợp phải có khả năng cung cấp **một luồng mới đọc được cùng nội dung**. Với MIME attachment, đây là điều kiện quan trọng để dữ liệu không bị hết giữa chừng hoặc phát sinh lỗi khi thư viện cần truy cập lại.

```text
Một InputStream đang mở:
  stream -> đọc hết -> không chắc có thể đọc lại

InputStreamSource phù hợp:
  getInputStream() -> stream A -> đọc/đóng
  getInputStream() -> stream B -> đọc/đóng
                         cùng byte nội dung
```

Không phải mọi class implement `InputStreamSource` đều có cùng khả năng đọc lại. **`InputStreamResource` là trường hợp cần đặc biệt thận trọng**, vì nó thường bọc một stream đã được mở từ trước.

### 5.3. Ví dụ dùng `InputStreamSource` mở file mới mỗi lần

Nếu cần tự viết một nguồn có thể mở lại:

```java
import org.springframework.core.io.InputStreamSource;

import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("/srv/app/reports/monthly.csv");
InputStreamSource source = () -> Files.newInputStream(path);

helper.addAttachment(
        "monthly.csv",
        source,
        "text/csv; charset=UTF-8"
);
```

Mỗi lần Jakarta Mail gọi `source.getInputStream()`, `Files.newInputStream(path)` sẽ trả về một stream mới. **Không nên dùng lambda đóng trên một `InputStream` đã mở sẵn rồi trả đi trả lại đúng instance đó**:

```java
InputStream openedOnce = Files.newInputStream(path);

// Không phù hợp: cùng một stream được trả lại ở mọi lần gọi.
InputStreamSource oneShot = () -> openedOnce;
```

`InputStreamSource` phù hợp khi tài nguyên không phải `File` hoặc cần logic mở stream riêng. Nếu chỉ đọc một file local đơn giản, `FileSystemResource` thường gọn và rõ hơn.

### 5.4. Nếu đã nhận được đúng một `InputStream` từ nguồn ngoài

Giả sử một API hoặc SDK trả về một `InputStream` **chỉ sử dụng được một lần**. Hai chiến lược phổ biến:

**Chiến lược A — tài liệu nhỏ hoặc vừa: đưa byte vào bộ nhớ.**

```java
import org.springframework.core.io.ByteArrayResource;

byte[] bytes;
try (InputStream input = upstreamStream) {
    bytes = input.readAllBytes();
}

helper.addAttachment(
        "document.pdf",
        new ByteArrayResource(bytes),
        "application/pdf"
);
```

`ByteArrayResource` có thể tạo một `ByteArrayInputStream` mới trên cùng mảng byte ở mỗi lần truy cập. Đổi lại, ứng dụng giữ toàn bộ nội dung trong RAM. Với file dung lượng lớn hoặc nhiều email gửi đồng thời, cách này có thể tiêu hao bộ nhớ đáng kể.

**Chiến lược B — tài liệu lớn: ghi vào file tạm có quản lý.**

```java
Path temp = Files.createTempFile("mail-attachment-", ".pdf");

try (InputStream input = upstreamStream) {
    Files.copy(input, temp, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
}

// Thực hiện trong thời gian temp vẫn tồn tại:
helper.addAttachment(
        "document.pdf",
        new org.springframework.core.io.FileSystemResource(temp),
        "application/pdf"
);

mailSender.send(message);

// Chỉ dọn file tạm sau khi quá trình gửi đã hoàn thành
// hoặc sau khi xử lý lỗi, tốt nhất bằng khối finally.
```

Đoạn thứ hai minh họa **một phần của workflow**, giả định `helper`, `message` và `mailSender` đã được chuẩn bị. Trong code sản xuất, cần đưa thao tác sao chép, gửi và xóa file tạm vào cấu trúc `try/finally` để tránh rò rỉ file khi có lỗi; không xóa file trước lúc JavaMail đã đọc xong.

Nếu hệ thống có thể gọi lại API tải object và nhận một stream mới cho cùng dữ liệu, cũng có thể xây `InputStreamSource` mở lại object. Cần bảo đảm dữ liệu không đổi giữa các lần đọc hoặc sử dụng version/ETag/định danh bất biến của object.

## 6. Cách 3 — Các loại `Resource` của Spring

`org.springframework.core.io.Resource` là abstraction cho nguồn tài nguyên. Các implementation phổ biến có thể đọc từ filesystem, classpath hoặc bộ nhớ. `Resource` cũng cung cấp khả năng lấy `InputStream`; do đó có thể truyền một resource thích hợp cho overload `addAttachment(..., InputStreamSource)`.

### 6.1. `FileSystemResource` — tệp trên ổ đĩa

```java
import org.springframework.core.io.FileSystemResource;

FileSystemResource resource =
        new FileSystemResource("/srv/app/reports/invoice.pdf");

helper.addAttachment("invoice.pdf", resource, "application/pdf");
```

`FileSystemResource` giữ abstraction `Resource` và có thể mở lại file qua đường dẫn. Nó tiện khi những service khác trong ứng dụng cũng đã sử dụng Spring Resource API.

Tương tự `File`, file phải còn tồn tại và truy cập được trong thời gian gửi. Việc có một `FileSystemResource` không có nghĩa byte của file đã được chụp thành một bản sao bất biến.

### 6.2. `ClassPathResource` — tài nguyên đóng gói cùng ứng dụng

Ví dụ ứng dụng có file:

```text
src/main/resources/mail/guide.pdf
```

Có thể đính kèm:

```java
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource =
        new ClassPathResource("mail/guide.pdf");

helper.addAttachment(
        "guide.pdf",
        resource,
        "application/pdf"
);
```

`ClassPathResource` hữu ích với tài liệu hướng dẫn, mẫu nội dung hoặc file cố định được đóng gói khi build ứng dụng.

**Không nên ép `ClassPathResource` thành `File` bằng `getFile()` khi ứng dụng chạy trong executable JAR**. Resource đóng gói bên trong JAR không nhất thiết là một file độc lập trên filesystem. Đường đọc bằng `getInputStream()` của resource thường phù hợp hơn.

### 6.3. `ByteArrayResource` — byte trong bộ nhớ

Khi ứng dụng tự sinh PDF hoặc CSV, dữ liệu có thể đã nằm trong `byte[]`:

```java
import org.springframework.core.io.ByteArrayResource;

byte[] pdfBytes = invoicePdfGenerator.generate(order);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Ở đây `invoicePdfGenerator.generate(order)` là **hàm nghiệp vụ minh họa**, không phải API được Spring Mail cung cấp.

`ByteArrayResource`:

- Không cần tạo một file trên ổ đĩa.
- Có khả năng cung cấp stream mới cho những lần đọc tiếp theo.
- Thích hợp khi byte đã có sẵn trong bộ nhớ.
- Không phù hợp nếu phải giữ quá nhiều tệp rất lớn cùng lúc.

Khi đính kèm byte của file, **đừng gọi `new String(pdfBytes, UTF_8)`** rồi gửi như text, vì byte nhị phân có thể không biểu diễn được bằng UTF-8 và sẽ bị hỏng.

### 6.4. `InputStreamResource` — trường hợp dễ dùng sai

`InputStreamResource` thường mô tả một `InputStream` đã mở sẵn, nên nó có đặc tính **one-shot**, tức không được thiết kế như một factory có thể cung cấp luồng mới cho nhiều lần đọc.

Ví dụ cần tránh:

```java
import org.springframework.core.io.InputStreamResource;

InputStream input = Files.newInputStream(path);

// Không phù hợp làm MIME attachment nếu thư viện cần đọc lại.
InputStreamResource resource = new InputStreamResource(input);
helper.addAttachment("report.pdf", resource, "application/pdf");
```

`MimeMessageHelper` có thể từ chối `Resource` đang chứa stream mở, hoặc quá trình gửi có thể lỗi nếu nguồn chỉ đọc được một lần. Với file có `Path`, nên thay bằng `FileSystemResource`. Với byte đã đọc vào RAM, dùng `ByteArrayResource`. Với nguồn phải tải lại, dùng `InputStreamSource` cung cấp stream **mới** mỗi lần.

### 6.5. Bảng so sánh các `Resource`

| Resource | Nơi giữ dữ liệu | Có thể mở lại dữ liệu? | Lưu ý |
| --- | --- | --- | --- |
| `FileSystemResource` | File trên filesystem | Thường có, nếu file vẫn tồn tại | Hợp với file local; chú ý quyền đọc và vòng đời file |
| `ClassPathResource` | Classpath/JAR hoặc thư mục classpath | Thường có | Không giả định luôn có `File` |
| `ByteArrayResource` | Mảng `byte[]` trong RAM | Có | Chi phí bộ nhớ tăng theo số lượng và kích thước file |
| `InputStreamResource` | Stream có sẵn | **Không bảo đảm** | Tránh làm attachment khi JavaMail cần đọc lại |
| `Resource` tùy chỉnh | Tùy implementation | Phải kiểm tra hợp đồng cụ thể | Quan trọng là cung cấp stream mới và byte ổn định |

## 7. File và Resource khác nhau ở điều gì?

Cả `File` và `Resource` đều có thể đại diện cho nội dung nằm trên filesystem, nhưng abstraction và cách sử dụng khác nhau.

| Tiêu chí | `File` | `Resource` |
| --- | --- | --- |
| Kiểu trong API | `java.io.File` | `org.springframework.core.io.Resource` |
| Biểu diễn file vật lý | Trực tiếp | Có thể qua `FileSystemResource` |
| Hỗ trợ classpath trong JAR | Không phải abstraction phù hợp | `ClassPathResource` |
| Hỗ trợ byte trong RAM | Không trực tiếp | `ByteArrayResource` |
| Có phương thức `getInputStream()` | Đọc qua API Java khác như `Files.newInputStream(...)` | Có trong Resource |
| Dùng với `MimeMessageHelper` | Overload `addAttachment(filename, File)` | Overload nhận `InputStreamSource` |
| Đảm bảo dữ liệu bất biến | Không | Không phải mọi Resource đều bất biến |

Nên chọn theo **vị trí dữ liệu** và **lifecycle**, không chỉ theo độ dài code. Nếu một service đã quản lý file trên đĩa bằng `Path`, dùng `File` hoặc `FileSystemResource` đều hợp lý. Nếu tài liệu nằm trong classpath hoặc đã là `byte[]`, `Resource` thường linh hoạt hơn.

## 8. Xác định `Content-Type` cho attachment

Đối với MIME part, tên file và `Content-Type` không phải một thứ. Ví dụ:

```text
Tên file: invoice.pdf
Media type: application/pdf

Tên file: report.csv
Media type: text/csv

Tên file: logo.png
Media type: image/png
```

Khi dùng overload không truyền `contentType`, `MimeMessageHelper` có thể dựa vào **`FileTypeMap`** để đoán MIME type từ tên file. Trong nhiều trường hợp, điều này hoạt động tốt với extension phổ biến. Nhưng mapping phụ thuộc cấu hình/thư viện và **không kiểm tra byte thật của file**.

Nếu ứng dụng đã biết chắc dữ liệu do mình tạo là PDF:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Điều này rõ ràng hơn so với việc suy đoán type từ `invoice.pdf`. Những giá trị phổ biến:

| Định dạng | `Content-Type` thường dùng |
| --- | --- |
| PDF | `application/pdf` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| CSV | `text/csv` |
| JSON | `application/json` |
| ZIP | `application/zip` |
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| DOCX | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| Chưa xác định | `application/octet-stream` |

**Đặt `Content-Type` đúng không làm thay đổi byte dữ liệu**. Nếu file PDF đã hỏng, khai báo `application/pdf` không tự sửa được nó.

### CSV và charset

Nếu hệ thống xuất CSV theo UTF-8, có thể biểu diễn media type:

```java
helper.addAttachment(
        "report.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
```

Điều này chỉ có ý nghĩa nếu `csvBytes` thực sự đã được tạo theo UTF-8. Nó cũng **không thay thế** các quy ước CSV như dấu phân cách, quoting hoặc cách công cụ spreadsheet diễn giải dữ liệu.

### `Content-Transfer-Encoding` không phải `Content-Type`

Với byte nhị phân, thư viện thường dùng base64. Nhưng `base64` không phải media type:

```text
Content-Type: application/pdf
Content-Transfer-Encoding: base64
```

Ứng dụng thông thường không cần tự chuyển byte PDF thành base64 rồi truyền kết quả vào `addAttachment(...)`. Làm vậy có thể tạo tệp chứa chính chuỗi base64 thay vì dữ liệu PDF gốc.

## 9. Một ví dụ Spring Boot sử dụng đủ ba loại nguồn

Giả sử hệ thống có ba phương thức gửi:

1. Gửi file PDF đã có trên ổ đĩa.
2. Gửi CSV được sinh trong bộ nhớ.
3. Gửi tài liệu hướng dẫn đóng gói trong classpath.

Ta có thể dùng một service thống nhất việc tạo MIME message. Phần này chỉ minh họa đường gửi email; việc xác thực người nhận, sinh file, lưu kết quả gửi và xử lý retry cần được thiết kế theo nghiệp vụ.

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

@Service
public class AttachmentMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public AttachmentMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendPdfFile(String recipient, Path file)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = newHelper(message, recipient);

        helper.setSubject("Báo cáo PDF");
        helper.setText("Vui lòng xem báo cáo đính kèm.", false);
        helper.addAttachment(
                "report.pdf",
                new FileSystemResource(file),
                "application/pdf"
        );

        mailSender.send(message);
    }

    public void sendCsvBytes(String recipient, byte[] csv)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = newHelper(message, recipient);

        helper.setSubject("Dữ liệu CSV");
        helper.setText("Vui lòng xem dữ liệu đính kèm.", false);
        helper.addAttachment(
                "data.csv",
                new ByteArrayResource(csv),
                "text/csv; charset=UTF-8"
        );

        mailSender.send(message);
    }

    public void sendGuide(String recipient)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = newHelper(message, recipient);

        helper.setSubject("Tài liệu hướng dẫn");
        helper.setText("Tài liệu hướng dẫn nằm trong attachment.", false);
        helper.addAttachment(
                "guide.pdf",
                new ClassPathResource("mail/guide.pdf"),
                "application/pdf"
        );

        mailSender.send(message);
    }

    private MimeMessageHelper newHelper(
            MimeMessage message,
            String recipient
    ) throws MessagingException {
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name()
        );
        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        return helper;
    }
}
```

Trong ví dụ, `FileSystemResource(file)` là nguồn đọc từ filesystem; `ByteArrayResource(csv)` giữ byte CSV có sẵn; `ClassPathResource("mail/guide.pdf")` đọc tài nguyên trong classpath. Cả ba đều được truyền như nguồn byte cho `addAttachment(...)`.

**Đoạn code giả định những nguồn dữ liệu đã hợp lệ:** `file` là PDF có thật và được phép đọc; `csv` là các byte CSV theo UTF-8; `guide.pdf` đã được đóng gói trong `src/main/resources/mail/`. Nếu giả định không đúng, lỗi phải được xử lý ở tầng tạo/kiểm tra dữ liệu.

## 10. Thêm nhiều attachment trong một email

Một email có thể chứa nhiều file. Chỉ cần gọi `addAttachment` nhiều lần **trên cùng một helper multipart**:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8"
);

helper.setFrom("reports@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Bộ tài liệu tháng này");
helper.setText("Gồm PDF và CSV.", false);

helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource("/srv/reports/invoice.pdf"),
        "application/pdf"
);
helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);

mailSender.send(message);
```

Jakarta Mail sẽ tổ chức những attachment thành các MIME part riêng. **Không** gọi `setText(...)` với toàn bộ dữ liệu nhị phân đã nối lại, và không cần tự tạo `multipart/mixed` header bằng tay.

### Tên file trùng nhau

Nếu thêm hai attachment đều có `attachmentFilename = "report.pdf"`, email có thể chứa hai part có cùng tên hiển thị. Mail client có thể trình bày hoặc lưu hai file theo cách khác nhau. Nên đặt tên phân biệt rõ, ví dụ `report-sales.pdf` và `report-stock.pdf`, đặc biệt khi hệ thống xuất nhiều báo cáo.

## 11. Phân biệt attachment với ảnh inline

Attachment thường được xử lý như một tệp người dùng tải xuống. **Inline resource** phục vụ nội dung HTML, ví dụ logo được tham chiếu qua `cid:logo`.

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn và biểu trưng");

helper.setText(
        "<p>Hóa đơn nằm trong tệp đính kèm.</p>"
            + "<img src=\"cid:logo\" alt=\"Logo\"/>",
        true
);

helper.addInline(
        "logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

mailSender.send(message);
```

`addInline(...)` dùng **Content-ID** để liên kết ảnh với HTML; `addAttachment(...)` tạo phần đính kèm. Với `MimeMessageHelper`, nên đặt `setText(...)` **trước** khi thêm inline resources để có cấu trúc phù hợp với nhiều mail client.

Media type `image/png` chỉ giúp mô tả dữ liệu; không bảo đảm mọi mail client sẽ hiển thị hình inline theo cùng một cách.

## 12. Vòng đời stream: ai mở, ai đóng, và đọc lại khi nào?

Một lỗi hay gặp không nằm ở `Content-Type` mà ở thời điểm resource bị đóng hoặc thay đổi.

```text
Ứng dụng tạo message
        |
        | addAttachment(filename, source)
        v
MimeMessage giữ tham chiếu tới nguồn
        |
        | thư viện có thể đọc nguồn để xác định đặc tính dữ liệu
        v
JavaMail/Jakarta Mail serialize MIME
        |
        | có thể đọc nguồn lần khác để viết byte thực
        v
SMTP transport
        |
        v
Mail server chấp nhận hoặc từ chối
```

Vì vậy:

- Không bảo đảm rằng toàn bộ byte đã được sao chép ngay tại lời gọi `addAttachment(...)`.
- Không đóng một stream dùng chung rồi kỳ vọng helper có thể đọc lại nó.
- Không xóa file tạm ngay sau khi gắn vào helper nhưng trước khi hoàn tất `send(...)`.
- Với nguồn có thể thay đổi, cần bảo đảm các lần đọc cho ra cùng nội dung.
- Nếu nguồn dữ liệu là remote object, quy tắc retry/mở lại phải phù hợp với API của hệ thống đó.

### Dọn file tạm với `try/finally`

Một mẫu quản lý vòng đời file tạm:

```java
Path temporary = Files.createTempFile("mail-report-", ".pdf");
try {
    Files.write(temporary, pdfBytes);

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, true, "UTF-8"
    );

    helper.setFrom("reports@example.org");
    helper.setTo("customer@example.net");
    helper.setSubject("Báo cáo");
    helper.setText("Vui lòng xem file đính kèm.");
    helper.addAttachment(
            "report.pdf",
            new FileSystemResource(temporary),
            "application/pdf"
    );

    mailSender.send(message);
} finally {
    Files.deleteIfExists(temporary);
}
```

Đây là **đoạn logic bên trong một method**, giả định `mailSender`, `pdfBytes` và các import cần thiết đã tồn tại. Trong Java, exception có thể phát sinh ở thao tác ghi, gửi hoặc xóa; ứng dụng thực tế cần chính sách ghi log và xử lý lỗi phù hợp. File chỉ được xóa khi lời gọi gửi đồng bộ đã kết thúc. Nếu chuyển việc gửi sang một worker bất đồng bộ, vòng đời file cần kéo dài đến thời điểm worker không còn sử dụng nó.

**Lưu ý:** xác nhận `send(...)` hoàn tất không chứng minh email đã được giao tới Inbox. Nó chỉ phản ánh kết quả quá trình gửi ở tầng ứng dụng/SMTP submission tương ứng.

## 13. Bảo mật khi đính kèm file

Attachment có thể mang dữ liệu nhạy cảm hoặc nội dung không an toàn. `MimeMessageHelper` là công cụ đóng gói MIME, **không phải công cụ chống malware hay kiểm soát truy cập**.

Những nguyên tắc cần thiết:

1. **Xác thực quyền đọc tài liệu:** người gửi yêu cầu phải có quyền truy cập nội dung được gửi.
2. **Xác định đúng người nhận:** kiểm tra To/Cc/Bcc theo nghiệp vụ trước khi gửi file.
3. **Hạn chế đường dẫn:** không lấy nguyên một đường dẫn do người dùng nhập rồi đọc mọi file hệ thống.
4. **Không tin filename hoặc media type từ upload:** cần kiểm tra loại dữ liệu theo chính sách cho phép.
5. **Giới hạn kích thước:** xét cả kích thước file gốc lẫn overhead mã hóa MIME.
6. **Không đưa secret vào tên attachment:** tên file có thể xuất hiện ở mail client và log.
7. **Quản lý vòng đời file tạm:** đặt tại vị trí có quyền phù hợp, xóa sau khi gửi hoặc thất bại.
8. **Không log byte hoặc nội dung nhạy cảm:** chỉ ghi metadata cần thiết và mã lỗi.
9. **Cân nhắc link tải an toàn với file lớn/nhạy cảm:** email có thể được chuyển tiếp và lưu ở nhiều hệ thống.

### Path traversal là gì trong ngữ cảnh này?

Giả sử API cho phép người gọi truyền:

```text
GET /send-report?path=../../confidential/data.csv
```

Nếu backend nối trực tiếp chuỗi path với thư mục gốc rồi gửi file, người gọi có thể tìm cách chọn file ngoài phạm vi được phép. Nên lấy file theo **ID nghiệp vụ**, tra cứu metadata do server kiểm soát và giới hạn tài nguyên trong thư mục/không gian lưu trữ được ủy quyền.

Đừng coi tên `invoice.pdf` hay `Content-Type: application/pdf` là bằng chứng file an toàn. Tên/metadata có thể bị giả mạo.

## 14. Dung lượng, Base64 và hiệu năng

Attachment thường được mã hóa base64 để đi qua email. Với một file nhị phân có `N` byte, riêng dữ liệu base64 thường dài xấp xỉ `4/3 × N`, chưa tính ký tự xuống dòng và các header MIME.

Ví dụ định tính:

```text
File gốc:             9 MB
Base64 (xấp xỉ):     12 MB
MIME headers/lines:  cộng thêm overhead
Toàn bộ email:       lớn hơn file gốc
```

Vì vậy, nếu SMTP provider giới hạn kích thước **toàn bộ message** ở mức nào đó, không thể chọn file gần sát giới hạn và mặc định email sẽ được chấp nhận.

So sánh nhanh:

| Nguồn | Chi phí bộ nhớ ứng dụng | Đặc điểm cần lưu ý |
| --- | --- | --- |
| `File` / `FileSystemResource` | Không cần nạp toàn bộ file vào một `byte[]` của service | Vẫn có buffer/overhead khi gửi và phụ thuộc file còn tồn tại |
| `ByteArrayResource` | Giữ toàn bộ byte trong RAM | Dễ dùng với file nhỏ/vừa, tốn RAM với file lớn |
| `ClassPathResource` | Thường đọc từ classpath khi cần | Phù hợp nội dung tĩnh, không lý tưởng cho file người dùng thay đổi |
| `InputStreamSource` tùy chỉnh | Tùy cách implement | Cần mở lại stream; có thể phát sinh chi phí truy xuất nhiều lần |

**Không có phương án nào tự động bỏ qua giới hạn SMTP hoặc quota của nhà cung cấp.** Với số lượng email lớn, cần tính đồng thời số kết nối, bộ nhớ, dung lượng gửi và chính sách retry.

## 15. Phân biệt lỗi chuẩn bị attachment và lỗi SMTP

Lỗi đính kèm có thể phát sinh ở nhiều tầng:

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy file | Sai đường dẫn, file đã xóa | Kiểm tra vị trí file và vòng đời |
| Không đọc được file | Quyền đọc, lock hoặc I/O | Kiểm tra quyền truy cập và tình trạng filesystem |
| Attachment có 0 byte | Nguồn stream đã bị đọc hết hoặc trả nội dung rỗng | Đảm bảo nguồn mở stream mới và byte nguồn đúng |
| `InputStreamResource` bị từ chối | Resource đang giữ stream mở, không phù hợp đọc lại | Dùng `FileSystemResource`/`ByteArrayResource` |
| File PDF nhận được bị hỏng | Byte nguồn sai, bị chuyển thành String, hoặc dữ liệu đổi giữa các lần đọc | So sánh byte nguồn và cách tạo resource |
| File có tên đúng nhưng icon/preview sai | `Content-Type` thiếu hoặc không phù hợp | Dùng overload có `contentType` tường minh |
| Mail client không nhận diện attachment | Cấu trúc MIME/`Content-Disposition` sai | Dùng `MimeMessageHelper` multipart thay vì tự viết header |
| Thư bị từ chối vì kích thước | Giới hạn SMTP/provider, overhead base64 | Giảm file, nén phù hợp hoặc dùng link tải |
| SMTP yêu cầu xác thực | Credential/cấu hình TLS sai | Kiểm tra submission endpoint và SMTP AUTH |
| Gửi xong nhưng người nhận chưa thấy | Thư còn trong queue, bị lọc hoặc bounce ở chặng sau | Dùng log/queue/delivery event của provider |

### Những loại exception cần phân biệt

- **`MessagingException`** (Jakarta Mail) có thể phát sinh khi chuẩn bị nội dung, người nhận hoặc MIME part.
- **`MailException`** và các subclass của Spring có thể xuất hiện khi sử dụng `JavaMailSender.send(...)`.
- **`IOException`** có thể phát sinh khi đọc stream/file ở các bước ứng dụng quản lý.
- **`IllegalArgumentException`** hoặc lỗi trạng thái có thể phát sinh nếu truyền resource không hợp lệ hoặc helper chưa ở chế độ multipart.

Không nên bắt mọi lỗi rồi retry vô hạn. Nếu file nguồn đã hỏng hoặc không có quyền đọc, retry SMTP sẽ không giải quyết vấn đề. Nếu gặp lỗi mạng tạm thời, cần retry có giới hạn và cân nhắc tình huống **SMTP server có thể đã nhận thư dù client chưa nhận được phản hồi cuối**, tránh gửi trùng không kiểm soát.

## 16. Những sai lầm thường gặp

### Sai lầm A: truyền `InputStreamResource` cho một stream chỉ dùng một lần

```java
InputStream stream = Files.newInputStream(path);
helper.addAttachment(
        "invoice.pdf",
        new InputStreamResource(stream),
        "application/pdf"
);
```

Vấn đề: nguồn không hứa hẹn tạo stream mới ở lần đọc tiếp theo. Đúng hướng hơn là:

```java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(path),
        "application/pdf"
);
```

Nếu nguồn chỉ có một stream từ dịch vụ ngoài, lưu byte trong RAM hoặc file tạm rồi sử dụng nguồn có thể đọc lại.

### Sai lầm B: tạo helper không multipart

```java
MimeMessageHelper helper = new MimeMessageHelper(message);
helper.addAttachment("invoice.pdf", resource);
```

Thao tác đính kèm cần MIME multipart. Khi biết trước có attachment:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8"
);
```

### Sai lầm C: đưa byte nhị phân vào `setText`

```java
helper.setText(new String(pdfBytes, StandardCharsets.UTF_8));
```

`setText` dành cho văn bản. Phép chuyển một mảng byte PDF thành text có thể gây mất dữ liệu. Hãy dùng `addAttachment(...)` với byte gốc.

### Sai lầm D: xóa file trước khi `send`

```java
helper.addAttachment("report.pdf", new FileSystemResource(tempPath));
Files.delete(tempPath);
mailSender.send(message);
```

Ở đây đường dẫn đã biến mất trước thời điểm thư viện có thể cần đọc file. Hãy giữ file cho tới khi thao tác gửi đồng bộ kết thúc, rồi dọn trong `finally`.

### Sai lầm E: chọn MIME type theo extension chưa tin cậy

Một upload có filename `invoice.pdf` có thể chứa dữ liệu khác. FileTypeMap không kiểm tra chữ ký PDF. Chỉ chọn `application/pdf` khi định dạng đã được ứng dụng xác định hoặc kiểm tra phù hợp.

### Sai lầm F: thêm attachment bằng cách đặt raw header thủ công

```java
message.setHeader("Content-Type", "application/pdf");
```

Lệnh này **không** tự tạo một attachment part; nó còn có thể khiến top-level MIME header mâu thuẫn với body. Để tạo attachment, dùng `MimeMessageHelper.addAttachment(...)` ở chế độ multipart.

## 17. Các tình huống vận dụng

### Tình huống 1: hóa đơn PDF được tạo trực tiếp trong bộ nhớ

Ứng dụng có:

```java
byte[] invoice = invoiceService.renderPdf(orderId);
```

`invoiceService.renderPdf(orderId)` là API nghiệp vụ minh họa. Lựa chọn phù hợp:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoice),
        "application/pdf"
);
```

Không cần tạo file tạm nếu dữ liệu nhỏ/vừa và đã có trong RAM.

### Tình huống 2: đính kèm một file lớn có sẵn trên máy chủ

Ứng dụng biết đường dẫn tới file đã được phép gửi.

Lựa chọn phù hợp:

```java
helper.addAttachment(
        "archive.zip",
        new FileSystemResource(archivePath),
        "application/zip"
);
```

Không cần đọc toàn bộ file vào `byte[]` chỉ để gửi. Tuy nhiên, kích thước thư sau Base64 và giới hạn SMTP vẫn cần được xem xét.

### Tình huống 3: file hướng dẫn nằm trong JAR

Lựa chọn:

```java
helper.addAttachment(
        "guide.pdf",
        new ClassPathResource("mail/guide.pdf"),
        "application/pdf"
);
```

Không phụ thuộc vào việc resource bên trong JAR có thể chuyển thành `java.io.File` hay không.

### Tình huống 4: SDK chỉ trả về stream đọc một lần

Nên lựa chọn giữa:

- Nạp byte qua `readAllBytes()` rồi dùng `ByteArrayResource` khi file đủ nhỏ và có giới hạn kích thước hợp lý.
- Sao chép stream sang file tạm và dùng `FileSystemResource` khi file lớn, đồng thời bảo đảm dọn file.
- Nếu API hỗ trợ mở lại cùng một object bất biến, tạo `InputStreamSource` mà `getInputStream()` gọi API đó ở mỗi lần.

Không trả lại cùng một `InputStream` đã tiêu thụ qua `InputStreamSource`.

### Tình huống 5: email có cả logo inline và báo cáo PDF

Tạo helper multipart phù hợp, dùng `setText(html, true)`, thêm logo bằng `addInline("logo", resource, "image/png")` và PDF bằng `addAttachment("report.pdf", resource, "application/pdf")`. Hai thao tác này tạo **hai loại MIME part có vai trò khác nhau**.

### Tình huống 6: mail client mở file CSV sai ký tự tiếng Việt

Kiểm tra byte CSV thật có được tạo bằng UTF-8 hay không, lựa chọn `Content-Type: text/csv; charset=UTF-8` khi phù hợp, và xét cách phần mềm mở CSV. `spring.mail.default-encoding=UTF-8` của text body không tự chuyển đổi toàn bộ nội dung file CSV mà ứng dụng đã sinh bằng charset khác.

## 18. Bảng quyết định nhanh

| Câu hỏi | Lựa chọn nên cân nhắc |
| --- | --- |
| File đang tồn tại trên filesystem? | `File` hoặc `FileSystemResource` |
| Byte đã có sẵn trong RAM? | `ByteArrayResource` |
| Tài nguyên nằm trong classpath/JAR? | `ClassPathResource` |
| Nguồn cung cấp một stream mới cho mỗi lần gọi? | `InputStreamSource` phù hợp |
| Chỉ có một stream đã mở? | Chuyển sang byte[] hoặc file tạm; tránh `InputStreamResource` one-shot |
| Đã biết rõ định dạng của dữ liệu? | Dùng overload `addAttachment(filename, source, contentType)` |
| Có nhiều file đính kèm? | Gọi `addAttachment` nhiều lần trên cùng helper multipart |
| Có hình ảnh được tham chiếu trong HTML? | Dùng `addInline` với Content-ID phù hợp |
| Có giới hạn kích thước email? | Tính overhead MIME/Base64; cân nhắc link tải an toàn |
| File có thể bị thay đổi/xóa khi gửi? | Giữ snapshot ổn định, quản lý vòng đời trước và trong `send` |

## 19. Kết luận

`MimeMessageHelper.addAttachment(...)` cho phép Spring Framework Mail đính kèm dữ liệu từ nhiều nguồn mà ứng dụng không phải tự viết giao thức MIME. **`File`** phù hợp với tệp trên đĩa; **`FileSystemResource`** và **`ClassPathResource`** tận dụng abstraction của Spring; **`ByteArrayResource`** hữu ích khi dữ liệu đã có trong RAM; còn **`InputStreamSource`** là hợp đồng cho nguồn cung cấp stream đọc lại được.

Điểm mấu chốt khi gửi attachment từ luồng byte là: **Jakarta Mail có thể mở nguồn nhiều lần, nên mỗi lần phải đọc được cùng nội dung**. Bên cạnh đó, phải tạo helper ở chế độ multipart, sử dụng `Content-Type` đúng với dữ liệu, giữ nguyên byte nhị phân và quản lý vòng đời file/stream cho tới khi quá trình gửi kết thúc. Những nguyên tắc này giúp email có attachment ổn định hơn, dễ mở rộng và ít gặp lỗi mất hoặc hỏng dữ liệu.
