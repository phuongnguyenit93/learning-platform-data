# Streaming attachment khi có thể

## 1. Vì sao attachment lớn là bài toán hiệu năng?

Trong **Spring Framework Mail**, một ứng dụng có thể gửi hóa đơn PDF, báo cáo CSV, bản sao kê, ảnh hoặc tài liệu đính kèm bằng `JavaMailSender` và `MimeMessageHelper`. Khi tệp nhỏ, việc đọc toàn bộ nội dung thành mảng byte rồi gắn vào email thường đơn giản. Nhưng với tệp lớn hoặc nhiều email được gửi đồng thời, cách này có thể làm tăng đột biến **heap memory, thời gian GC, thời gian chờ SMTP và lượng dữ liệu phải truyền**.

Ví dụ cách làm dễ gây áp lực bộ nhớ:

~~~java
byte[] attachmentBytes = Files.readAllBytes(reportPath);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
helper.setTo("customer@example.com");
helper.setFrom("reports@example.com");
helper.setSubject("Báo cáo");
helper.setText("Xem báo cáo đính kèm.");
helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(attachmentBytes),
        "application/pdf");

mailSender.send(message);
~~~

`Files.readAllBytes` tạo một mảng chứa **toàn bộ tệp trong heap**. Nếu một báo cáo 40 MiB được gửi đồng thời bởi 20 worker, riêng các mảng dữ liệu gốc có thể đã chiếm xấp xỉ 800 MiB, chưa kể object của Spring/Jakarta Mail, buffer mạng, MIME encoding và dữ liệu của ứng dụng.

Một lựa chọn thường tốt hơn là dùng tài nguyên hỗ trợ mở **InputStream mới từ file** khi SMTP transport đọc nội dung:

~~~java
FileSystemResource attachment =
        new FileSystemResource(reportPath);

helper.addAttachment(
        "report.pdf",
        attachment,
        "application/pdf");
mailSender.send(message);
~~~

Ở đây, ứng dụng không cần chủ động đọc toàn bộ file thành `byte[]` trước khi gắn vào MIME message. Thư viện mail có thể mở stream từ file trong quá trình chuẩn bị/serialize nội dung.

> **Điểm cốt lõi:** “Streaming attachment” trong bài này nghĩa là **cấp nội dung theo luồng, không tự materialize toàn bộ payload vào heap trước khi gửi**. Nó **không** bảo đảm toàn bộ pipeline Spring → Jakarta Mail → SMTP server không dùng buffer, không đọc lại stream hoặc có memory footprint bằng O(1) trong mọi phiên bản/transport. Hãy kiểm thử và đo trên stack thực tế.

## 2. Tệp đính kèm đi qua những lớp nào?

Đường đi điển hình:

~~~text
Business request / scheduled job
                |
                v
Report generator / disk / object storage
                |
                v
Spring Resource / InputStreamSource / DataSource
                |
                v
MimeMessageHelper.addAttachment(...)
                |
                v
Jakarta Mail MIME part / DataHandler
                |
                v
MIME serialization + Base64 / transfer encoding
                |
                v
JavaMailSender / SMTP transport
                |
                v
SMTP server / relay
~~~

Ứng dụng kiểm soát cách đọc dữ liệu ban đầu, còn quá trình tạo MIME/ghi qua SMTP thuộc thư viện và nhà cung cấp transport. Cần hiểu ít nhất ba giới hạn:

1. **Memory:** Đọc tệp vào mảng byte có chi phí heap tỷ lệ với kích thước tệp. Dùng file/stream có thể tránh bước materialize đó.
2. **Network:** Email attachment nhị phân thường được mã hóa Base64, làm kích thước dữ liệu trên dây tăng đáng kể.
3. **SMTP/provider:** Mail server có thể từ chối email vượt giới hạn kích thước hoặc timeout, dù ứng dụng tự streaming rất hiệu quả.

### 2.1. MIME không chỉ chứa file gốc

Một message có HTML, plain text và attachment có thể có cấu trúc:

~~~text
MimeMessage (multipart/mixed)
├── multipart/alternative
│   ├── text/plain; charset=UTF-8
│   └── text/html; charset=UTF-8
└── application/pdf
    ├── Content-Disposition: attachment; filename="report.pdf"
    └── Content-Transfer-Encoding: base64
~~~

Cấu trúc thật có thể lồng `multipart/related` hoặc các part khác khi dùng inline resource; không nên cứng nhắc giả định chỉ có một cách tổ chức MIME tree.

### 2.2. Vì sao file 20 MiB có thể thành thư lớn hơn 20 MiB?

Base64 biểu diễn ba byte dữ liệu bằng bốn ký tự, tức kích thước cơ bản khoảng \(4/3\) lần file nhị phân, chưa tính xuống dòng, MIME boundary, header, HTML/text và overhead SMTP.

Ví dụ ước lượng:

| Dữ liệu nhị phân | Base64 thô xấp xỉ | Kích thước message thực tế |
| --- | --- | --- |
| 1 MiB | 1,33 MiB | Lớn hơn 1,33 MiB do wrapping/header |
| 10 MiB | 13,33 MiB | Lớn hơn 13,33 MiB |
| 25 MiB | 33,33 MiB | Lớn hơn 33,33 MiB |
| 50 MiB | 66,67 MiB | Lớn hơn 66,67 MiB |

Đây là **ước lượng, không phải con số SIZE chính xác**: chuẩn MIME thường xuống dòng Base64 theo các đoạn ngắn, làm tăng thêm byte. Một thư còn chứa nhiều part và metadata. Nếu provider giới hạn 25 MiB **cho toàn message**, không thể gắn một file nhị phân 25 MiB rồi mong SMTP vẫn chấp nhận.

### 2.3. Streaming không làm biến mất giới hạn SMTP

Giả sử SMTP server chỉ chấp nhận message tối đa 20 MiB. Một input file 19 MiB vẫn có thể vượt giới hạn sau Base64 và MIME overhead. Worker nên kiểm tra **ước lượng kích thước cuối** trước khi thực hiện SMTP call, nhưng kết quả chính thức vẫn thuộc server/provider.

Không tính ngưỡng bằng một công thức duy nhất rồi coi đó là bảo đảm. Với message nhiều phần, tên file Unicode, HTML, inline images hoặc nội dung đã có transfer encoding khác, cần cộng thêm overhead hợp lý và xử lý trường hợp SMTP từ chối.

## 3. Các nguồn dữ liệu đính kèm trong Spring

`MimeMessageHelper` có các overload cho attachment nhận `File`, `InputStreamSource` hoặc `DataSource` tùy trường hợp. Trong Spring Framework, `Resource` mở rộng `InputStreamSource`, nên nhiều loại `Resource` có thể dùng trực tiếp.

| Nguồn | Đặc điểm | Khi phù hợp | Điều cần lưu ý |
| --- | --- | --- | --- |
| `FileSystemResource` | Mở stream từ file mỗi lần được yêu cầu | File lớn đã có trên ổ đĩa | File phải tồn tại đến lúc gửi hoàn tất |
| `PathResource` | Nguồn từ `Path`, có khả năng mở stream mới | File trên filesystem | Quyền đọc, xóa tệp tạm, symlink |
| `ByteArrayResource` | Giữ toàn bộ `byte[]` trong heap | File nhỏ hoặc dữ liệu đã ở memory | Chi phí heap tỷ lệ kích thước |
| `InputStreamResource` | Thường bao bọc một stream đã mở | Một số API đọc một lần | **Không phù hợp** cho nguồn attachment cần đọc lặp lại |
| Custom `InputStreamSource` | Factory mở stream mới khi được gọi | Object storage, generated content ổn định | Phải tạo stream mới và quản lý thời gian sống |
| `jakarta.activation.DataSource` | Cấp stream, content type, name | Tích hợp chuyên sâu với Jakarta Mail | Cần implement contract và đóng stream đúng |

Với tệp lớn trên disk, **`FileSystemResource` hoặc `PathResource` thường là lựa chọn dễ hiểu và ít rủi ro nhất**. Nếu dữ liệu đến từ HTTP, S3/object store hoặc database, có thể cần một luồng chuyển vào tệp tạm được giới hạn dung lượng trước khi gửi.

### 3.1. ByteArrayResource: đơn giản nhưng dùng heap

~~~java
byte[] bytes = reportGenerator.toByteArray();
helper.addAttachment(
        "report.csv",
        new ByteArrayResource(bytes),
        "text/csv");
~~~

Ưu điểm: dữ liệu ổn định, có thể đọc lại qua stream mới từ cùng mảng byte. Nhược điểm: **mảng byte đã tồn tại toàn bộ trong heap**, dù method có tên `getInputStream`.

`ByteArrayResource` phù hợp khi dữ liệu nhỏ, ví dụ file vài KiB hoặc mảng đã tồn tại từ một API khác. Không cần cấm nó hoàn toàn; hãy lựa chọn theo kích thước thực tế và concurrency.

### 3.2. InputStreamResource: vì sao dễ gây lỗi?

Đoạn sau cần tránh:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    helper.addAttachment(
            "report.pdf",
            new InputStreamResource(input),
            "application/pdf");
}

mailSender.send(message);
~~~

Có ít nhất hai vấn đề:

1. `try-with-resources` đã đóng stream **trước** khi `send` thực sự cần đọc.
2. Một `InputStreamResource` bao bọc stream đơn lẻ thường **không thể đọc lại**. Jakarta Mail có thể yêu cầu đọc part nhiều hơn một lần khi xác định nội dung, encoding hoặc serialize.

Trong Spring, contract của `InputStreamSource` dành cho MIME attachment yêu cầu **mỗi lần `getInputStream()` phải trả về một stream mới**, vì JavaMail có thể gọi nhiều lần. Một nguồn single-use không đáp ứng giả định này.

### 3.3. FileSystemResource: ví dụ ngắn

~~~java
import org.springframework.core.io.FileSystemResource;

import java.nio.file.Path;

Path reportPath = Path.of("/data/reports/invoice-123.pdf");
FileSystemResource resource = new FileSystemResource(reportPath);

helper.addAttachment(
        "invoice.pdf",
        resource,
        "application/pdf");
mailSender.send(message);
~~~

`FileSystemResource` cho phép thư viện mở stream khi cần. Nhưng nó **không đóng băng nội dung file**: nếu worker khác thay/xóa file giữa lúc chuẩn bị message và lúc transport đọc, email có thể lỗi hoặc gửi nội dung khác mong muốn.

Hãy sử dụng nguồn file đã hoàn tất, không chỉnh sửa, giữ quyền sở hữu và không xóa cho tới khi `send` kết thúc.

## 4. Quy tắc quan trọng: nguồn phải đọc lại được

Với attachment, nhiều lập trình viên nghĩ rằng chỉ cần mở stream một lần rồi “gắn” vào message. Tuy nhiên, dữ liệu MIME có thể được truy cập nhiều lần. Vì vậy, nguồn nội dung nên có tính chất:

- **Fresh stream:** mỗi lần gọi `getInputStream()` tạo một stream độc lập.
- **Stable bytes:** các lần đọc của cùng một delivery phải cho nội dung tương đương, không âm thầm đổi phiên bản.
- **Available until send completes:** không đóng/xóa nguồn trước khi serialization hoàn tất.
- **Bounded resource usage:** hạn chế kích thước, số connection mở và thời gian đọc.
- **Safe close:** luồng mở ra được đóng bởi phần sử dụng hoặc bởi lớp cung cấp khi hợp đồng yêu cầu.

Một `InputStreamSource` custom đơn giản từ file:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.core.io.InputStreamSource;

public final class RepeatableFileSource implements InputStreamSource {

    private final Path file;

    public RepeatableFileSource(Path file) {
        this.file = file;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        return Files.newInputStream(file);
    }
}
~~~

Mỗi lần `getInputStream` được gọi sẽ mở một descriptor mới tới file. Đây là một adapter giáo dục; trong ứng dụng thông thường, `FileSystemResource` đã có hành vi tương tự và không cần viết lại.

**Không implement**:

~~~java
InputStream in = remoteApi.openStream();
InputStreamSource bad = () -> in;  // trả cùng stream lần thứ hai
~~~

Source kiểu này có thể trả về stream đã bị đọc hết hoặc đã đóng khi Jakarta Mail truy cập lại, gây lỗi attachment trống hoặc `IOException` khó tái hiện.

### 4.1. Đọc lại được nhưng không đồng nghĩa an toàn nếu file thay đổi

Ví dụ:

~~~text
T1: report.pdf version A
T2: MimeMessageHelper references report.pdf
T3: a separate process overwrites report.pdf with version B
T4: SMTP transport reads report.pdf
~~~

Email có thể chứa phiên bản B thay vì phiên bản A. Với báo cáo tài chính hoặc hóa đơn, cần giữ một snapshot nhất quán: tệp tạm có tên/ID riêng và không chỉnh sửa; hoặc object storage có immutable version/ETag, đồng thời bảo đảm mọi lần mở stream truy cập cùng phiên bản.

## 5. Mẫu gửi attachment từ file bằng JavaMailSender

Ví dụ service đồng bộ:

~~~java
package com.example.mail;

import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {

    private final JavaMailSender mailSender;

    public ReportMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(
            String recipient,
            Path immutableReportFile) throws MessagingException {

        if (!Files.isRegularFile(immutableReportFile)
                || !Files.isReadable(immutableReportFile)) {
            throw new IllegalArgumentException(
                    "Report attachment is unavailable");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo tháng");
        helper.setText(
                "Vui lòng xem báo cáo đính kèm.",
                "<p>Vui lòng xem báo cáo đính kèm.</p>");

        helper.addAttachment(
                "report.pdf",
                new FileSystemResource(immutableReportFile),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

Đoạn code cho thấy **cách gắn một file đã tồn tại**. Nó không phải cơ chế kiểm tra bảo mật file đầy đủ: production cần hạn chế nơi `Path` đến từ, xác thực quyền đọc, loại bỏ symlink/path traversal theo policy, kiểm tra dung lượng và loại nội dung.

### 5.1. Đặt attachment name đúng mục đích

`attachmentFilename` là tên **người nhận sẽ nhìn thấy**, khác với đường dẫn filesystem:

~~~java
helper.addAttachment(
        "bao-cao-thang-11.pdf",            // display filename
        new FileSystemResource(path),      // internal source
        "application/pdf");               // declared MIME type
~~~

Không dùng trực tiếp đường dẫn nội bộ làm tên attachment (ví dụ `C:\\private\\reports\\customer-123.pdf`) vì có thể lộ cấu trúc hệ thống. Với filename lấy từ người dùng, cần chuẩn hóa/loại control characters, CR/LF và path separator; không tin tên file như bằng chứng loại nội dung.

### 5.2. Attachment khác inline resource

`MimeMessageHelper.addAttachment(...)` dùng cho file mà người đọc có thể tải/xem như attachment. `addInline(contentId, ...)` thường dùng logo, ảnh nhúng được tham chiếu từ HTML qua `cid:...`:

~~~java
helper.setText(
        "<p>Báo cáo tháng</p><img src=\"cid:brand-logo\" />",
        true);
helper.addInline(
        "brand-logo",
        new FileSystemResource(logoFile),
        "image/png");
~~~

Inline resources cũng có thể bị encode và làm message lớn hơn. Với ảnh lớn, không nên sử dụng inline chỉ vì có thể đọc từ stream; cân nhắc tối ưu ảnh hoặc phương án dẫn link phù hợp chính sách bảo mật/email client.

## 6. Từ HTTP, object storage hoặc report generator tới file tạm

Không phải attachment nào cũng đã nằm trên filesystem. Ứng dụng có thể lấy dữ liệu từ:

- Object storage như S3 hoặc một dịch vụ tương đương.
- Hệ thống tạo PDF, CSV, XLSX.
- Một dịch vụ nội bộ trả nội dung qua HTTP.
- Database blob hoặc document store.
- File được người dùng upload và đã qua kiểm tra.

Trong những trường hợp đó, một chiến lược thực dụng là **đọc nguồn theo từng buffer và ghi vào file tạm có giới hạn dung lượng**, sau đó gửi với `FileSystemResource`. Đây không phải streaming hoàn toàn từ đầu đến cuối, nhưng tránh việc giữ nguyên attachment trong heap suốt quá trình gửi.

~~~text
Remote source / report generator
                  |
                  | InputStream / OutputStream
                  v
           Bounded copy loop
             buffer 8 KiB
                  |
                  v
       Temporary file on local disk
                  |
                  v
         FileSystemResource
                  |
                  v
        MimeMessageHelper
                  |
                  v
        JavaMailSender.send(...)
                  |
                  v
     Delete temp after send finishes
~~~

### 6.1. Vì sao không dùng InputStream.readAllBytes?

Ví dụ cần tránh với nguồn không bị giới hạn:

~~~java
try (InputStream input = remoteStorage.open(objectKey)) {
    byte[] bytes = input.readAllBytes();
    helper.addAttachment(
            "report.zip",
            new ByteArrayResource(bytes),
            "application/zip");
}
~~~

`readAllBytes` có thể làm heap phình ra, vượt quota hoặc gây `OutOfMemoryError` nếu response lớn hơn dự kiến. Một giá trị `Content-Length` từ nguồn bên ngoài cũng không đủ để bảo vệ vì có thể thiếu, sai hoặc bị thay đổi.

Thay bằng vòng copy có **hard limit dựa trên số byte thực tế đã đọc**.

### 6.2. Bounded spool: tạo file tạm không vượt quota

Ví dụ helper dùng Java 17+:

~~~java
package com.example.mail.attachment;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.springframework.core.io.InputStreamSource;

public final class AttachmentStager {

    private AttachmentStager() {
    }

    /**
     * Source phải được ứng dụng ủy quyền trước khi tới đây.
     * temporaryDirectory là thư mục riêng, không public.
     */
    public static Path stageBounded(
            InputStreamSource source,
            Path temporaryDirectory,
            long maxBytes) throws IOException {

        if (maxBytes <= 0) {
            throw new IllegalArgumentException(
                    "maxBytes must be positive");
        }

        Path staged = Files.createTempFile(
                temporaryDirectory, "mail-attachment-", ".tmp");
        boolean completed = false;

        try (InputStream in = source.getInputStream();
             OutputStream out = Files.newOutputStream(
                     staged,
                     StandardOpenOption.WRITE,
                     StandardOpenOption.TRUNCATE_EXISTING)) {

            byte[] buffer = new byte[8192];
            long total = 0;
            int read;

            while ((read = in.read(buffer)) != -1) {
                if (read == 0) {
                    continue;
                }
                if (read > maxBytes - total) {
                    throw new IOException(
                            "Attachment exceeds configured byte limit");
                }
                out.write(buffer, 0, read);
                total += read;
            }

            completed = true;
            return staged;
        } finally {
            if (!completed) {
                Files.deleteIfExists(staged);
            }
        }
    }
}
~~~

Đặc điểm:

- Buffer dùng cho copy chỉ khoảng 8 KiB, không bằng kích thước toàn tệp.
- Kiểm soát tổng số byte **thực tế** đọc được, không chỉ tin header.
- Đóng input và output khi copy hoàn tất hoặc xảy ra lỗi.
- Xóa file tạm chưa hoàn chỉnh khi lỗi copy, bao gồm khi vượt `maxBytes`.
- Trả về đường dẫn của file snapshot sau khi dữ liệu đã được ghi xong.

Trong thực tế, kiểm tra quyền với `temporaryDirectory`, filesystem quota, free space và giới hạn nguồn là trách nhiệm của tầng quản lý staging. Nếu lỗi cleanup xảy ra cùng lúc với lỗi đọc, cần thu thập cả nguyên nhân gốc và lỗi dọn dẹp (Java try-with-resources hỗ trợ suppressed exception; phần `finally` ở ví dụ này là bản rút gọn).

Đối với file không tin cậy, nên kiểm tra MIME/content, signature và malware theo chính sách sau khi stage. `maxBytes` chỉ giới hạn kích thước, **không** chứng minh file an toàn.

### 6.3. Gửi tệp tạm và xóa sau khi `send` trả về

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.InputStreamSource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class StagedMailService {

    private final JavaMailSender mailSender;
    private final Path tempDirectory;

    public StagedMailService(
            JavaMailSender mailSender, Path tempDirectory) {
        this.mailSender = mailSender;
        this.tempDirectory = tempDirectory;
    }

    public void sendAttachment(
            String recipient,
            InputStreamSource source) throws IOException, MessagingException {

        long limit = 15L * 1024 * 1024; // Ví dụ: tối đa 15 MiB input.
        Path staged = AttachmentStager.stageBounded(
                source, tempDirectory, limit);

        try {
            MimeMessage mime = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom("reports@example.com");
            helper.setTo(recipient);
            helper.setSubject("Báo cáo đính kèm");
            helper.setText(
                    "Xin xem file đính kèm.",
                    "<p>Xin xem file đính kèm.</p>");
            helper.addAttachment(
                    "report.pdf",
                    new FileSystemResource(staged),
                    "application/pdf");

            mailSender.send(mime);
        } finally {
            Files.deleteIfExists(staged);
        }
    }
}
~~~

`JavaMailSender.send` ở ví dụ này là lời gọi **đồng bộ**: sau khi lời gọi hoàn tất hoặc ném exception, phương thức không tiếp tục đọc stream để gửi ở background theo contract sử dụng thông thường. Từ đó, tầng staging có thể xóa tệp trong `finally`.

**Nhưng không được bê nguyên vòng đời này vào luồng async** nếu `send` chỉ được lên lịch để chạy sau: file có thể bị xóa khi worker chưa kịp mở. Trường hợp bất đồng bộ được trình bày ở phần tiếp theo.

Ngoài ra, `Files.deleteIfExists` có thể thất bại do quyền truy cập hoặc file descriptor đang mở. Production cần log/metric lỗi cleanup và một sweeper có TTL để xử lý file mồ côi sau crash.

### 6.4. Không tải toàn bộ file tạm từ URL tùy ý

Nếu nguồn là URL do người dùng cung cấp, không trực tiếp:

~~~java
URL url = URI.create(userInput).toURL();
InputStreamSource source = url::openStream;
~~~

Đường đi này có thể dẫn tới **SSRF**, truy cập IP nội bộ, metadata service, tài nguyên localhost hoặc redirect sang host khác. Thay vào đó, chỉ đọc từ một danh mục storage được ủy quyền hoặc qua client có allowlist host/scheme, giới hạn redirect, thời gian kết nối/đọc, kích thước và tenant authorization.

Với object store, dùng key/version được xác thực theo tenant và storage client do ứng dụng kiểm soát, không lấy một URL bất kỳ từ HTTP request rồi tải.

## 7. Gửi trực tiếp từ object storage bằng repeatable stream

Nếu object storage hỗ trợ mở một stream mới với cùng phiên bản dữ liệu, có thể cung cấp custom `InputStreamSource` mà **không cần ghi file tạm**:

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.InputStreamSource;

public final class VersionedObjectSource
        implements InputStreamSource {

    private final ObjectStorageClient storage;
    private final String bucket;
    private final String objectKey;
    private final String versionId;

    public VersionedObjectSource(
            ObjectStorageClient storage,
            String bucket,
            String objectKey,
            String versionId) {
        this.storage = storage;
        this.bucket = bucket;
        this.objectKey = objectKey;
        this.versionId = versionId;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        // Mỗi lần gọi phải là một remote stream mới
        // từ cùng immutable object version.
        return storage.openVersion(
                bucket, objectKey, versionId);
    }
}
~~~

`ObjectStorageClient` và `openVersion` là **abstraction giả định do ứng dụng xây dựng**, không phải API Spring hoặc S3 có sẵn với chữ ký đó. Ý tưởng:

1. Xác thực tenant/người yêu cầu có quyền đọc object.
2. Lấy version ID hoặc một immutable content reference.
3. Kiểm tra metadata kích thước, content type, checksum khi có.
4. Trả stream mới ở mỗi `getInputStream` cho đúng version.
5. Áp dụng request timeout, retry limit, connection pool limit và close response stream.
6. Bảo đảm stream vẫn truy cập được cho tới khi MIME serialization kết thúc.

Ví dụ gắn vào message:

~~~java
InputStreamSource content = new VersionedObjectSource(
        storage, bucket, objectKey, versionId);

helper.addAttachment(
        "monthly-report.pdf",
        content,
        "application/pdf");
mailSender.send(message);
~~~

### 7.1. Nhược điểm của remote streaming trực tiếp

Trường hợp này tiết kiệm disk tạm nhưng phát sinh các vấn đề mới:

- Jakarta Mail có thể **đọc stream nhiều lần**; mỗi lần có thể mở một HTTP request và tải cùng object.
- Remote connection timeout có thể làm SMTP serialization dừng giữa chừng.
- Object bị xóa hoặc credential hết hạn giữa các lần đọc.
- Một lần tải thất bại có thể khiến kết quả SMTP không rõ ràng nếu xảy ra lúc đang truyền DATA.
- Network source và SMTP output phụ thuộc hai dịch vụ; một dịch vụ chậm có thể giữ connection của dịch vụ kia lâu.
- Nếu client object store tự buffering toàn bộ response, chiến lược này vẫn không đạt mục tiêu về memory.

Do đó, với email giao dịch quan trọng hoặc file lớn cần gửi lặp, **spool sang file tạm có quota** thường dễ kiểm soát hơn remote stream trực tiếp, dù sử dụng thêm disk I/O.

### 7.2. Khi nào remote streaming phù hợp?

Có thể cân nhắc khi:

- File có kích thước đã biết, nhỏ hoặc trung bình so với ngưỡng mail policy.
- Object bất biến, có version ID và kiểm tra quyền rõ ràng.
- Storage client có stream thật, không buffer toàn bộ.
- Thời gian mở stream ổn định và thấp.
- Hệ thống giới hạn concurrency, timeouts và retry.
- Stack Jakarta Mail đang dùng đã được kiểm thử với source có thể đọc lại.

Không chọn chỉ vì tên API là `InputStream`. Cần đo memory, số lần mở stream và thời gian gửi thật dưới tải.

## 8. Attachment được tạo bằng PDF/CSV renderer

Nhiều dịch vụ gửi mail tạo file báo cáo **ngay trong request**:

~~~java
byte[] pdf = invoiceGenerator.generatePdfBytes(order);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdf),
        "application/pdf");
~~~

Nếu `generatePdfBytes` đã tạo một mảng lớn thì chuyển sang `InputStreamSource` phía sau **không lấy lại được bộ nhớ của giai đoạn render**. Cần đổi interface của renderer để **ghi vào OutputStream** hoặc file.

### 8.1. Generate trực tiếp tới file

Ví dụ abstraction:

~~~java
public interface InvoiceRenderer {
    void writePdf(InvoiceData invoice, OutputStream output)
            throws IOException;
}
~~~

Worker có thể:

~~~java
Path staged = Files.createTempFile(
        privateTempDirectory, "invoice-", ".pdf");
try {
    try (OutputStream out = Files.newOutputStream(staged)) {
        renderer.writePdf(invoiceData, out);
    }

    long inputBytes = Files.size(staged);
    if (inputBytes > attachmentPolicy.maxInputBytes()) {
        throw new IOException("Generated invoice exceeds mail limit");
    }

    helper.addAttachment(
            "invoice.pdf",
            new FileSystemResource(staged),
            "application/pdf");
    mailSender.send(message);
} finally {
    Files.deleteIfExists(staged);
}
~~~

Các biến `renderer`, `invoiceData`, `privateTempDirectory`, `attachmentPolicy`, `helper` và `message` là thành phần giả định của ứng dụng. Đây là một đoạn minh họa đặt trong service đồng bộ, không phải một chương trình độc lập.

Lưu ý: vì ví dụ kiểm tra kích thước **sau khi render**, nó vẫn có thể tốn quá nhiều disk trước khi phát hiện giới hạn. Nếu renderer có thể xuất dữ liệu rất lớn hoặc input không đáng tin cậy, hãy dùng **bounded OutputStream**, per-job disk quota và hard stop khi vượt giới hạn ngay trong lúc render.

### 8.2. CSV lớn: ghi theo dòng thay vì tạo một chuỗi khổng lồ

Tránh:

~~~java
String csv = rows.stream()
        .map(this::toCsvLine)
        .collect(Collectors.joining("\\n"));
byte[] all = csv.getBytes(StandardCharsets.UTF_8);
~~~

Với hàng triệu dòng, chuỗi kết quả và mảng bytes có thể rất lớn. Thay bằng `BufferedWriter` ghi từng dòng:

~~~java
try (BufferedWriter writer = Files.newBufferedWriter(
        staged, StandardCharsets.UTF_8)) {
    writer.write("orderId,amount,status");
    writer.newLine();

    for (OrderRow row : rows) {
        writer.write(csvEncoder.encode(row));
        writer.newLine();
    }
}
~~~

`csvEncoder` phải escape dấu phẩy, dấu nháy và newline theo CSV rules; nếu file được mở trong spreadsheet software và dữ liệu đến từ người dùng, còn cần xử lý CSV/formula injection theo policy. Với tập dữ liệu rất lớn, `rows` nên là iterator/cursor/batch, không phải một list chứa toàn bộ dataset.

CSV phù hợp với mô hình “tạo từng phần → file tạm → attachment” khi renderer support incremental output.

## 9. Vòng đời tệp khi gửi mail bất đồng bộ

Trong các hệ thống sản xuất, email thường được gửi bằng `@Async`, message broker hoặc outbox worker. Một lỗi phổ biến là tạo attachment tạm trong HTTP request, truyền đường dẫn sang worker rồi **xóa file khi request kết thúc**.

Ví dụ cần tránh:

~~~java
public void createAndQueueReport() throws IOException {
    Path temp = generateReportToTempFile();
    try {
        asyncSender.sendLater(temp); // chỉ lên lịch, chưa đọc file
    } finally {
        Files.deleteIfExists(temp); // quá sớm!
    }
}
~~~

Nếu `sendLater` thực sự chạy trên thread khác, tệp có thể đã biến mất trước khi worker tạo MIME content. Lỗi có thể xuất hiện không ổn định tùy tốc độ scheduler, khiến integration test pass nhưng production thất bại.

### 9.1. Cách 1: tạo và xóa tệp trong cùng worker

Ưu tiên khi việc generate report đủ nhanh và worker có quyền truy cập dữ liệu:

~~~text
Business transaction
   |
   +--> Store outbox: reportId + recipientId
   |
   v
COMMIT
   |
   v
Async/outbox worker
   |
   +--> Authorize report
   +--> Generate immutable temp file
   +--> Build MIME from FileSystemResource
   +--> JavaMailSender.send
   +--> Record outcome
   +--> Delete temp in finally
~~~

Ví dụ skeleton:

~~~java
@Service
public class AsyncReportMailWorker {

    private final ReportStagingService staging;
    private final JavaMailSender mailSender;
    private final DispatchResultService results;

    public AsyncReportMailWorker(
            ReportStagingService staging,
            JavaMailSender mailSender,
            DispatchResultService results) {
        this.staging = staging;
        this.mailSender = mailSender;
        this.results = results;
    }

    @Async("mailExecutor")
    public CompletableFuture<Void> sendReport(ReportJob job) {
        Path temp = null;
        try {
            temp = staging.createImmutableReport(job.reportId());

            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");
            helper.setFrom("reports@example.com");
            helper.setTo(job.recipient());
            helper.setSubject("Báo cáo đã tạo");
            helper.setText("Xem báo cáo đính kèm.");
            helper.addAttachment(
                    "report.pdf",
                    new FileSystemResource(temp),
                    "application/pdf");

            mailSender.send(message);
            results.recordSmtpAccepted(job.deliveryId());
            return CompletableFuture.completedFuture(null);
        } catch (Exception ex) {
            results.recordDispatchError(job.deliveryId(), ex);
            return CompletableFuture.failedFuture(ex);
        } finally {
            if (temp != null) {
                staging.deleteOrScheduleCleanup(temp);
            }
        }
    }
}
~~~

`ReportStagingService`, `ReportJob` và `DispatchResultService` là **abstraction do ứng dụng tự triển khai**. Snippet minh họa **ownership của tệp tạm nằm trong worker**; khi đưa vào production, phải tách lỗi SMTP khỏi lỗi database ghi `SENT`, vì SMTP có thể đã chấp nhận message nhưng ghi trạng thái bị lỗi. Đồng thời, xử lý riêng exception cleanup để nó không che mất lỗi gốc.

Lưu ý: `@Async` hoạt động qua Spring proxy; self-invocation trong cùng bean có thể không chạy bất đồng bộ. `@Async` và Future cũng **không tự bảo đảm công việc sống qua process restart**. Nếu email quan trọng, lưu outbox/job bền vững và cho worker lấy lại sau crash.

### 9.2. Cách 2: pre-stage ở object storage rồi worker tải lại

Với report quá tốn CPU để tạo lại mỗi lần worker retry:

~~~text
Report service
  |
  +--> Generate report once
  +--> Upload immutable object version
  +--> Save objectKey/versionId in outbox
  |
  v
Mail worker
  |
  +--> Resolve authorized object version
  +--> Stage bounded temp file or repeatable stream
  +--> Send via SMTP
  +--> Record outcome
  +--> Cleanup local temp
~~~

Không gửi `InputStream` đang mở qua message queue. Stream là tài nguyên gắn với process/connection, không phải một payload bền vững có thể serialize và khôi phục. Lưu **tham chiếu bất biến** như object key/version ID, cùng checksum/size metadata nếu cần.

### 9.3. Nếu tệp tạm phải sống qua nhiều lần retry

Cần một mô hình sở hữu rõ ràng:

| Nguồn | Vòng đời hợp lý |
| --- | --- |
| Tệp có sẵn, bất biến trên shared storage | Giữ đến khi delivery hoàn tất/TTL theo policy |
| Tệp tạm tạo riêng trong worker | Xóa trong `finally` sau attempt |
| Object storage version | Giữ đến khi hết retry deadline/retention; mỗi attempt mở lại |
| Tệp staging được share giữa các worker | Cần lease/refcount/ownership, không xóa khi vẫn có người dùng |

Không dựa vào `deleteOnExit()` như chiến lược cleanup chính: nó chỉ chạy khi JVM kết thúc theo một số điều kiện và không xử lý được crash cưỡng bức, disk quota trong quá trình chạy hay file tồn tại qua nhiều ngày.

### 9.4. Crash và cleanup mồ côi

Vì `finally` không chạy nếu process bị kill, nên tệp tạm có thể còn trên disk. Một sweeper định kỳ có thể:

1. Duyệt **đúng thư mục staging riêng** của ứng dụng.
2. Chỉ xem những file mang định danh/manifest hợp lệ của staging.
3. Đối chiếu trạng thái job/lease và tuổi tệp.
4. Không xóa file đang được worker xử lý hoặc cần cho retry.
5. Xóa file hết hạn và ghi metric cleanup.

Không triển khai một cleanup job dựa trên `Files.walk(/tmp)` xóa tùy tiện vì có thể tác động tới file của ứng dụng khác hoặc file đang được sử dụng.

## 10. Concurrency và giới hạn tài nguyên

Streaming giúp giảm áp lực heap của **mỗi attachment** nhưng không loại bỏ nhu cầu giới hạn số email đang gửi đồng thời.

Giả sử mỗi email chứa một file 60 MiB. Nếu cho 50 worker cùng stage vào disk:

\[
\mathrm{staging\ disk\ budget} \approx 50 \times 60\ \mathrm{MiB}
= 3000\ \mathrm{MiB}
\]

Chưa tính metadata, file tạo dở, đồng thời có job retry hoặc tệp đang đợi cleanup. Nếu filesystem chỉ còn 1 GiB, hệ thống sẽ gặp `No space left on device` dù heap vẫn còn nhiều.

### 10.1. Giới hạn số worker đang gửi

Cấu hình Spring `ThreadPoolTaskExecutor` minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class MailExecutorConfiguration {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.initialize();
        return executor;
    }
}
~~~

Đây là thông số **minh họa**, không phải mặc định phù hợp mọi ứng dụng. Với attachment lớn, 8 worker có thể đã vượt quota disk hoặc SMTP concurrency nếu mỗi worker giữ nhiều file/connection. Cần đo:

- P95/p99 thời gian tạo file, gửi SMTP và cleanup.
- Kích thước attachment trung bình/lớn nhất.
- Disk staging còn trống và quota mỗi worker.
- Mức đồng thời provider cho phép.
- Số kết nối object storage và SMTP đang mở.
- Tỷ lệ lỗi/timeout khi tăng concurrency.

Queue trong executor cũng phải có giới hạn. Nếu job đã được ghi bền vững trong outbox, không cần đẩy hàng triệu task lên một in-memory executor queue; worker có thể claim theo batch dựa trên capacity còn trống.

### 10.2. Backpressure khi attachment lớn

Một chính sách:

~~~text
Job due
   |
   v
Attachment limit check
   |
   +--> Too large -> reject / link-based delivery
   |
   v
Acquire staging + SMTP capacity
   |
   +--> No capacity -> leave PENDING/RETRY, schedule later
   |
   v
Stage -> send -> cleanup -> release capacity
~~~

Nếu không có capacity, nên giữ job ở trạng thái chờ hợp lệ hoặc trả lỗi quá tải rõ ràng trước khi job được nhận. **Không claim hàng loạt job rồi ngủ lâu trong worker** làm lease hết hạn và tăng duplicate risk.

### 10.3. RAM vẫn cần giám sát

Ngay cả khi nguồn là file:

- Jakarta Mail có thể giữ buffer hoặc metadata MIME.
- Renderer HTML có thể tạo chuỗi lớn.
- Tệp rất lớn có thể được thư viện bên thứ ba materialize để tính checksum, scan hoặc encode.
- TLS/socket buffer và attachment parsing có chi phí memory.
- JVM GC và concurrent workers có thể tạo peak.

Không kết luận từ tên `FileSystemResource` rằng memory sẽ luôn cố định. Dùng profiler/heap metrics và benchmark có tải thực tế.

## 11. SMTP timeouts và giới hạn kích thước

Một attachment đọc theo stream vẫn phải được gửi qua **kết nối SMTP có thời gian chờ và giới hạn message size**. Trong Spring Boot với SMTP transport hỗ trợ các property Jakarta Mail, có thể đặt:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 20000
      "[mail.smtp.writetimeout]": 30000
~~~

Các giá trị tính bằng millisecond và chỉ mang tính ví dụ. Chúng nên được đặt dựa trên mạng, provider, kích thước attachment và SLA. Với implicit TLS, cấu hình `mail.smtp.ssl.enable` theo endpoint và port phù hợp thay vì áp STARTTLS một cách máy móc.

### 11.1. Ba loại timeout không giống nhau

| Thuộc tính | Bảo vệ bước nào? |
| --- | --- |
| `mail.smtp.connectiontimeout` | Chờ thiết lập TCP connection |
| `mail.smtp.timeout` | Chờ đọc dữ liệu/response từ SMTP server |
| `mail.smtp.writetimeout` | Thời gian chờ khi ghi socket (tùy transport implementation) |

Đặt timeout tránh treo vô hạn nhưng **không bảo đảm** mọi trường hợp network/remote source sẽ dừng tức thì hoặc worker sẽ được giải phóng ngay khi Future timeout. Một số implementation dùng thread phụ để áp dụng write timeout; cần kiểm tra hành vi và chi phí tài nguyên trên transport đang chạy.

Nếu stream lấy từ object store qua HTTP, **timeout của storage client phải được cấu hình riêng**; SMTP timeout không bảo vệ mọi thao tác tải attachment từ service khác.

### 11.2. SMTP SIZE và giới hạn provider

SMTP server có thể công bố extension `SIZE` và giới hạn message body/overall message theo policy. Nhà cung cấp còn có thể giới hạn:

- Kích thước một message sau MIME encoding.
- Tổng số recipient hoặc attachment mỗi email.
- Các MIME type/extension bị cấm.
- Kích thước một attachment riêng.
- Throughput, quota theo giờ/ngày hoặc số kết nối.

Ứng dụng nên kiểm tra kích thước **trước khi gọi send** để tránh tốn thời gian dựng/sending một message chắc chắn vượt giới hạn, nhưng vẫn cần xử lý trường hợp SMTP từ chối.

### 11.3. Một hàm ước lượng overhead

Với một file binary, một công thức gần đúng:

\[
\mathrm{base64Bytes}(n) = 4 \left\lceil \frac{n}{3} \right\rceil
\]

Để ước lượng một email thực tế, còn phải cộng line breaks, các headers, content text/HTML, MIME boundary và các attachment khác. Vì vậy, **không lấy giới hạn SMTP trừ một con số cố định như 100 bytes rồi bảo đảm hợp lệ**.

Ví dụ nếu chính sách nội bộ là message tối đa 20 MiB, có thể đặt input limit của một attachment nhỏ hơn nhiều so với 20 MiB, dành buffer an toàn cho MIME overhead và phần nội dung khác. Sau đó đo message thực tế bằng test SMTP sink.

### 11.4. Không retry vô hạn khi server từ chối size

Nếu SMTP server trả lỗi terminal vì message quá lớn, retry cùng attachment nguyên trạng thường không có ích. Hãy:

1. Ghi error code có cấu trúc, ví dụ `SMTP_MESSAGE_TOO_LARGE`.
2. Đưa job tới `FAILED`/dead letter hoặc chọn kênh gửi khác theo nghiệp vụ.
3. Thông báo cho người dùng hoặc operator bằng nội dung không lộ dữ liệu nhạy cảm.
4. Nếu phù hợp, tạo link tải file có quyền truy cập thay vì attachment.

Một `MailSendException` đơn thuần chưa đủ để kết luận transient hay permanent; cần xem SMTP response/cause và giai đoạn lỗi.

## 12. Khi nào không nên gửi attachment mà nên gửi link?

Streaming giúp giảm bộ nhớ ứng dụng, nhưng email vẫn phải mang toàn bộ dữ liệu đã encode qua SMTP. Với báo cáo lớn hoặc dữ liệu có tính riêng tư cao, đôi khi **gửi đường dẫn tải tài liệu** tốt hơn gắn file.

| Phương án | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Gắn attachment nhỏ | Người nhận có bản sao ngay trong email | Tăng size, bị giới hạn mail server |
| Gắn file bằng `FileSystemResource` | Tránh load toàn bộ file vào heap trước khi gửi | Vẫn chuyển toàn bộ bytes qua SMTP |
| Direct remote repeatable stream | Có thể tránh tệp tạm | Remote fetch nhiều lần; network coupling |
| Spool file tạm rồi gửi | Ổn định, dễ giới hạn và đọc lại | Dùng disk quota, cần cleanup |
| Link tải từ storage/portal | Email nhẹ, dễ quản lý quyền và cập nhật file | Người nhận cần truy cập link, link có thể hết hạn |

### 12.1. Link có kiểm soát truy cập

Một email có thể chứa:

~~~html
<p>Báo cáo tháng đã sẵn sàng.</p>
<p>
  <a href="https://portal.example.com/reports/123">
    Xem và tải báo cáo
  </a>
</p>
~~~

Đây là URL minh họa. Với tài liệu nhạy cảm:

- Yêu cầu người dùng đăng nhập và kiểm tra quyền truy cập khi tải.
- Hoặc dùng signed URL thời hạn ngắn, chỉ cấp đúng object/version và mục đích.
- Không đặt thông tin nhạy cảm trong URL nếu có thể tránh.
- Cân nhắc khả năng URL xuất hiện trong email forward, browser history, proxy/CDN logs hoặc link preview.
- Đặt thời hạn hợp lý; với báo cáo cần truy cập dài ngày, portal được xác thực thường phù hợp hơn token gửi một lần.
- Đảm bảo link dùng HTTPS, có giới hạn download/rate và audit khi cần.

**Không tự chuyển mọi attachment sang link** nếu người nhận cần file offline, yêu cầu tuân thủ bắt buộc đính kèm hoặc hạ tầng không cho phép truy cập portal. Chọn giải pháp theo hợp đồng nghiệp vụ và khả năng của người nhận.

### 12.2. Quy tắc chọn theo kích thước

Một bộ policy nội bộ có thể như sau:

~~~text
File size <= configured small threshold
    -> ByteArrayResource acceptable if data already in memory

File moderate and stored on disk
    -> FileSystemResource or PathResource

File remote, moderate size, requires stable snapshot
    -> Stage bounded temp file and send

File large / uncertain size / near provider limit
    -> Reject attachment or offer authenticated download link
~~~

Không có “file nhỏ”, “file vừa” hay “file lớn” theo một ngưỡng chung cho tất cả ứng dụng. Một hệ thống chạy 2 GiB heap với 50 workers khác một hệ thống chạy 16 GiB heap với 2 workers. Ngưỡng phải được cấu hình và đo.

## 13. Bảo mật attachment trong luồng streaming

Attachment thường chứa dữ liệu có giá trị: hóa đơn, hợp đồng, thông tin khách hàng, token, báo cáo nội bộ. Khi chuyển sang file/stream, cần bảo vệ cả **đọc nguồn, staging, gửi và cleanup**.

### 13.1. Kiểm tra quyền truy cập trước khi mở nguồn

Giả sử request có `reportId`. Dữ liệu này **không đủ** để cho phép đọc file:

~~~text
Authenticated user / tenant
              |
              v
Authorize(reportId, tenantId, action=SEND_REPORT)
              |
              v
Resolve immutable object version / trusted file
              |
              v
Stage + send
~~~

Không ghép trực tiếp giá trị request thành path:

~~~java
// Không an toàn nếu reportId do người dùng kiểm soát:
Path file = Path.of("/reports/" + reportId + ".pdf");
~~~

Cách này có thể dẫn tới path traversal/symlink issues hoặc truy cập báo cáo của tenant khác nếu thiếu kiểm tra. Dùng repository lookup được ủy quyền để lấy object reference tin cậy.

### 13.2. File tạm phải nằm trong vùng riêng

Một thư mục staging nên:

- Không nằm trong static web root hoặc thư mục được file server expose.
- Có permission/ACL giới hạn cho service account.
- Có disk quota/monitoring và chính sách cleanup.
- Không dùng chung không kiểm soát với tác vụ người dùng khác.
- Không để filename chứa dữ liệu cá nhân hoặc secret.
- Tránh đọc/ghi qua symlink tùy ý; nếu có luồng cần xử lý file từ thư mục không tin cậy, phải xử lý race/TOCTOU phù hợp.

`Files.createTempFile` giúp sinh tên khó trùng và tạo file mới, nhưng **không thay thế kiểm soát thư mục và quyền truy cập**. Trong môi trường multi-tenant hoặc có attacker local, cân nhắc filesystem sandbox và ownership riêng.

### 13.3. Kiểm tra loại file và nội dung

`Content-Type: application/pdf` do ứng dụng khai báo không chứng minh bytes thực sự là PDF. Nếu file do người dùng upload hoặc nguồn không tin cậy, có thể cần:

- Allowlist MIME/file type theo nghiệp vụ.
- Kiểm tra magic bytes/định dạng thực tế.
- Malware scanning và quarantine trước khi gửi.
- Chặn file thực thi hoặc attachment nguy hiểm theo policy.
- Giới hạn số file và tổng dung lượng của email.
- Không tự động decompress archive không có giới hạn; chống ZIP bomb.
- Xác định attachment name an toàn, không có newline/control characters.

Đừng coi việc đọc bằng stream là bước “sanitize” nội dung. Streaming chỉ là chiến lược xử lý I/O và memory.

### 13.4. Bảo mật kênh SMTP

Ngay cả khi file tạm được bảo vệ trên disk, payload gửi ra ngoài vẫn đi qua SMTP. Với server yêu cầu xác thực:

- Dùng STARTTLS bắt buộc hoặc implicit TLS theo endpoint.
- Bật hostname/certificate verification.
- Không log password, access token hoặc nội dung attachment.
- Giới hạn timeout.
- Không gửi tới arbitrary recipient do request chưa được authorize.

Ví dụ production phải dùng credential từ biến môi trường, file secret hoặc secret manager, không hard-code trong code hoặc Docker image.

### 13.5. Không log dữ liệu binary hoặc raw MIME

Không làm:

~~~java
log.debug("attachment={}", Arrays.toString(bytes));
log.debug("mime={}", mimeMessage.getContent());
~~~

Các log này có thể làm tràn dung lượng, rò rỉ dữ liệu hoặc kích hoạt read/serialization không mong muốn. Thay bằng metadata an toàn:

~~~text
event=mail.attachment.staged
deliveryId=opaque-uuid
attachmentType=pdf
attachmentBytes=1832401
sourceKind=object-storage
stagingDurationMs=310
~~~

Không dùng attachment filename, object key chứa PII hoặc delivery ID làm **metric label** vì có thể tạo high-cardinality và rò rỉ thông tin.

## 14. Giám sát memory, disk và thời gian streaming

Nếu chuyển từ `ByteArrayResource` sang `FileSystemResource` mà chỉ kiểm tra rằng email “gửi thành công”, chưa đủ để đánh giá cải thiện hiệu năng. Nên đo cả nguồn và đích:

| Metric | Ý nghĩa |
| --- | --- |
| `mail_attachment_input_bytes` | Kích thước input của mỗi attachment |
| `mail_attachment_count` | Số tệp trên mỗi message |
| `mail_attachment_staging_duration_seconds` | Thời gian copy/generate ra file tạm |
| `mail_attachment_staging_inflight` | Số job đang chiếm disk staging |
| `mail_attachment_staging_disk_bytes` | Dung lượng staging đang sử dụng |
| `mail_attachment_rejected_total` | Số attachment bị từ chối theo lý do |
| `mail_attachment_cleanup_failed_total` | Số lần xóa file tạm thất bại |
| `mail_smtp_send_duration_seconds` | Thời gian `JavaMailSender.send` |
| `mail_smtp_failure_total` | Lỗi gửi theo taxonomy hữu hạn |
| `jvm_memory_used_bytes` | Heap/non-heap do JVM/micrometer quan sát |
| `jvm_gc_pause_seconds` | Dấu hiệu áp lực GC |

### 14.1. Metric cardinality

Nhãn nên là những tập giá trị hữu hạn:

~~~text
attachment_type=pdf|csv|xlsx|other
source_kind=file|object_storage|generated
result=accepted|too_large|io_error|mime_error
~~~

Không thêm `recipient`, `filePath`, `objectKey`, `deliveryId` vào mỗi series. Dùng structured log/trace có quyền truy cập kiểm soát để truy vết một delivery cụ thể.

### 14.2. Đo toàn bộ pipeline

~~~text
T0  authorize file / validate metadata
T1  start generate or fetch
T2  staging finished
T3  create MIME / attach resource
T4  SMTP send begins
T5  SMTP send returns/errors
T6  outbox result committed
T7  temporary file removed
~~~

Từ đó có thể đo:

- `T2 - T1`: thời gian tạo/tải file.
- `T5 - T4`: thời gian SMTP transport.
- `T6 - T0`: thời gian xử lý job đến lúc commit.
- `T7 - T2`: khoảng file staging tồn tại.

Đừng gộp tất cả vào một con số “SMTP duration”. Nếu object storage tải chậm, việc tăng SMTP timeout không sửa nguyên nhân.

### 14.3. Đánh giá heap theo concurrency

Ví dụ benchmark:

~~~text
Case A: readAllBytes + ByteArrayResource
  20 parallel mails, attachment 20 MiB each

Case B: FileSystemResource
  20 parallel mails, attachment 20 MiB each

Observe:
  peak heap used
  GC pause
  per-mail SMTP duration
  throughput
  staging disk usage
  failure/timeout count
~~~

Cùng một workload, message body và SMTP sink được dùng cho cả hai cách. Không khẳng định kết quả trước khi đo, vì framework và transport có thể có buffering riêng. Nếu dùng file tạm, cần tính cả chi phí disk I/O và cleanup.

## 15. Kiểm thử streaming attachment

Có ba mức test bổ sung cho nhau:

1. **Unit test source contract:** nhiều lần `getInputStream` phải tạo stream đọc được và nội dung ổn định.
2. **MIME test:** attachment có tên, content type và bytes đúng sau serialization.
3. **SMTP integration test:** server giả lập nhận message lớn vừa phải và nội dung không bị hỏng, không dùng SMTP production.

### 15.1. Test repeatability của InputStreamSource

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.InputStreamSource;

import static org.assertj.core.api.Assertions.assertThat;

class AttachmentSourceTest {

    @Test
    void createsFreshStreamForEachRead() throws Exception {
        byte[] expected = "Nội dung kiểm thử"
                .getBytes(StandardCharsets.UTF_8);
        AtomicInteger opens = new AtomicInteger();

        InputStreamSource source = () -> {
            opens.incrementAndGet();
            return new ByteArrayInputStream(expected);
        };

        byte[] first;
        byte[] second;
        try (InputStream a = source.getInputStream();
             InputStream b = source.getInputStream()) {
            assertThat(a).isNotSameAs(b);
            first = a.readAllBytes();
            second = b.readAllBytes();
        }

        assertThat(first).isEqualTo(expected);
        assertThat(second).isEqualTo(expected);
        assertThat(opens.get()).isEqualTo(2);
    }
}
~~~

Đây là test contract; dùng một mảng nhỏ trong **test** là hợp lý. Nó không chứng minh mọi lần đọc của remote object storage có dữ liệu giống nhau; với storage, cần kiểm tra version pinning và retry.

### 15.2. Test bounded staging

Những kịch bản:

| Input | Mong đợi |
| --- | --- |
| Nhỏ hơn `maxBytes` | Tạo file tạm đúng byte |
| Bằng `maxBytes` | Chấp nhận theo policy |
| Lớn hơn `maxBytes` | Ném lỗi có kiểm soát, xóa file tạm dở |
| InputStream ném `IOException` giữa chừng | Không để lại file hoàn chỉnh giả |
| InputStream bất thường trả nhiều chunk | Tổng byte vẫn bị chặn đúng |
| Storage metadata nói nhỏ nhưng stream thực tế lớn | Chặn theo số byte thực đọc |
| Thiếu quyền ghi disk | Ghi nhận staging failure, không gọi SMTP |
| Delete thất bại | Có metric/sweeper để xử lý file mồ côi |

Không dùng stream vô hạn trong test không có timeout; dùng synthetic source có giới hạn để dễ tái lập.

### 15.3. Test MIME bằng Jakarta Mail

Một email multipart có thể được duyệt đệ quy để tìm part mang filename cụ thể:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class MimeAttachmentTestSupport {

    public static Part findAttachment(
            Part part, String filename) throws Exception {

        if (filename.equals(part.getFileName())) {
            return part;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                Part result = findAttachment(child, filename);
                if (result != null) {
                    return result;
                }
            }
        }
        return null;
    }
}
~~~

Đây là helper test cho message đã biết và có kích thước giới hạn, không phải parser MIME untrusted hoàn chỉnh. Sau khi tìm part, test có thể mở `getInputStream`, đọc fixture nhỏ và so sánh bytes. Không so sánh raw MIME byte-for-byte vì boundary, `Date`, `Message-ID` và transfer encoding có thể khác giữa các lần.

### 15.4. SMTP integration test với Mailpit/GreenMail

Một SMTP sink như Mailpit hoặc GreenMail cho phép:

- Gửi qua `JavaMailSender` thật.
- Quan sát attachment name/content type.
- Lấy raw MIME hoặc `MimeMessage` nếu công cụ hỗ trợ.
- Kiểm tra message không bị cắt, nội dung giải mã khớp fixture.
- Đo thời gian gửi với file kích thước xác định.

Ví dụ kịch bản integration:

~~~text
Create 5 MiB fixture with known checksum
  |
  v
Write immutable temp file
  |
  v
Attach via FileSystemResource
  |
  v
Send to local SMTP test server
  |
  v
Read captured message / attachment part
  |
  v
Compare decoded bytes or checksum
  |
  v
Assert temp file cleaned up
~~~

Với file 5 MiB, không bắt buộc phải giữ cả fixture và captured attachment trong heap của cùng một test nếu đang đo memory. Có thể so checksum theo stream để tránh làm biến dạng kết quả benchmark.

SMTP sink chỉ chứng minh server test đã nhận message. Nó không chứng minh Gmail/Outlook sẽ chấp nhận file, không kiểm tra spam filter hay giới hạn kích thước của SMTP provider production.

### 15.5. Test async cleanup

Kịch bản tái hiện lỗi phổ biến:

~~~text
Request stage file
Request submits async job
Request scope ends
Worker begins later
Expected: file still available or worker restages from stable source
Worker sends
Expected: cleanup after completion
~~~

Nếu kiến trúc đã chuyển ownership vào worker, hãy test:

- File không bị xóa trước khi worker đọc.
- File được xóa sau `send` thành công.
- File được xóa khi `send` ném exception và kết quả được ghi đúng.
- Nếu process crash, sweeper có thể xử lý file mồ côi sau TTL.
- Hai worker không cùng sử dụng rồi xóa một file shared mà không có lease/refcount.

Không dựa vào `Thread.sleep` cố định để test async; dùng Awaitility, event latch hoặc trạng thái outbox có timeout.

## 16. Các lỗi thường gặp khi “streaming” attachment

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `OutOfMemoryError` khi gửi tệp lớn | `readAllBytes`, `ByteArrayOutputStream` hoặc renderer buffer toàn bộ | Đổi sang stream/file, đo heap toàn pipeline |
| Attachment có kích thước 0 byte | Dùng stream single-use đã bị đọc hết | Dùng `FileSystemResource` hoặc `InputStreamSource` mở stream mới |
| `Stream closed` lúc gửi | Đóng InputStream trước khi Jakarta Mail đọc | Giữ source sống đến khi `send` xong |
| `FileNotFoundException` trong worker async | Request xóa temp trước khi worker bắt đầu | Stage trong worker hoặc chuyển ownership rõ ràng |
| File gửi khác version dự kiến | File bị overwrite giữa chuẩn bị và send | Dùng immutable snapshot/object version |
| Remote storage bị gọi nhiều lần | Jakarta Mail mở stream nhiều lần | Stage file tạm hoặc tính trước chi phí remote re-read |
| SMTP gửi rất chậm dù heap thấp | Đọc disk/network chậm, mail provider throttle | Đo từng giai đoạn, quota và send duration |
| SMTP trả lỗi size limit | MIME/Base64 làm message lớn hơn file | Ước lượng message, giới hạn file đầu vào, chuyển link |
| Disk staging đầy | Nhiều worker cùng tạo temp hoặc cleanup lỗi | Disk quota, concurrency limit, TTL sweeper |
| Gửi lại gây duplicate | SMTP đã accepted nhưng DB update lỗi | UNKNOWN/reconciliation, idempotency theo khả năng provider |
| File đính kèm sai tên hoặc lộ path | Truyền path nội bộ làm display filename | Dùng display name an toàn, chuẩn hóa tên |
| File có phần mở rộng PDF nhưng không hợp lệ | Tin filename/content-type không kiểm tra bytes | Validate content, policy và quét malware khi cần |
| Lỗi khi tải qua HTTP từ URL người dùng | SSRF, timeout hoặc redirect bất ngờ | Dùng storage client được kiểm soát, allowlist/authorization |
| Tệp chưa hoàn chỉnh vẫn được gửi | Bắt đầu send trước khi generator đóng output | Hoàn tất stage rồi mới thêm attachment |
| Lỗi cleanup che mất exception SMTP | `finally` ném exception thứ hai | Xử lý/log cleanup riêng và bảo toàn nguyên nhân gốc |
| Gửi được local nhưng fail production | Khác giới hạn SMTP/TLS/attachment policy | Test staging/provider, giới hạn nội bộ an toàn |

### 16.1. “Attachment stream closed” sau khi dùng try-with-resources

Vấn đề:

~~~java
InputStream stream = storage.open(...);
try (stream) {
    helper.addAttachment(
            "file.pdf",
            new InputStreamResource(stream),
            "application/pdf");
}
mailSender.send(message);
~~~

`addAttachment` **không đồng nghĩa** thư viện đã đọc và giữ toàn bộ bytes ngay tại thời điểm gọi. Sau `try`, stream đóng nhưng MIME content vẫn cần đọc trong quá trình send.

Cách sửa:

~~~java
FileSystemResource resource =
        new FileSystemResource(stagedFile);
helper.addAttachment("file.pdf", resource, "application/pdf");
mailSender.send(message);
~~~

Hoặc dùng `InputStreamSource` có khả năng mở **fresh remote stream** ở mỗi lần gọi, nếu version/data ổn định và latency được kiểm soát.

### 16.2. Tưởng rằng InputStreamResource sẽ tự tiết kiệm heap

`InputStreamResource` không mang cùng nghĩa với một factory tạo stream mới. Nó thường chứa stream đã mở, có thể chỉ đọc một lần. Đổi từ `ByteArrayResource` sang `InputStreamResource` mà không hiểu contract có thể chuyển lỗi OOM sang lỗi MIME/closed stream, chứ không phải một tối ưu an toàn.

Nếu đã có file, hãy dùng `FileSystemResource`. Nếu chưa có file và dữ liệu được generate/tải một lần, hãy stage vào file có giới hạn và dùng nguồn đọc lại được.

### 16.3. Xóa file trước khi SMTP transport serialize

Vấn đề có thể xuất hiện ở các flow như:

~~~text
createMimeMessage
helper.addAttachment(file)
delete(file)
mailSender.send(message)   <-- file missing
~~~

Không có bảo đảm rằng `addAttachment` đã nạp bytes vào MIME part ngay lập tức. Phải giữ file nguyên vẹn cho tới khi `mailSender.send` hoàn tất. Với async, đặc biệt lưu ý ranh giới thread/process.

### 16.4. Không biết lỗi xuất hiện ở nguồn hay SMTP

Ví dụ:

~~~text
Object storage read fails mid-stream
  |
  v
Jakarta Mail MIME serialization fails
  |
  v
MailException or nested IOException
~~~

Không nên tự gọi mọi lỗi này là “SMTP server rejected recipient”. Cần ghi phase như `ATTACHMENT_FETCH`, `ATTACHMENT_STAGE`, `MIME_BUILD`, `SMTP_SEND` và `STATE_UPDATE` khi có thể xác định.

Nếu lỗi nguồn xảy ra sau khi SMTP DATA đã bắt đầu truyền, kết quả từ phía relay có thể trở nên mơ hồ. Retry cần policy tránh duplicate tương tự các lỗi SMTP network khác.

## 17. Mẫu thiết kế cho email có attachment lớn

Ví dụ ứng dụng gửi báo cáo hằng ngày cho một nhóm khách hàng:

~~~text
Scheduler
   |
   v
Create report request (not binary payload)
   |
   v
Database transaction
  - save report metadata
  - insert mail outbox PENDING
   |
   v
Outbox dispatcher
   |
   v
Worker claims one delivery
   |
   +--> Resolve authorized immutable report version
   |
   +--> Inspect size/type/recipient policy
   |
   +--> Choose:
   |       A. Small file already in memory
   |          -> ByteArrayResource
   |       B. File on disk
   |          -> FileSystemResource
   |       C. Remote file
   |          -> bounded temp stage or repeatable source
   |       D. Too large
   |          -> secure download link / terminal policy
   |
   +--> Build MIME and validate attachment metadata
   |
   +--> SMTP send with TLS and timeouts
   |
   +--> Persist SENT / RETRY / FAILED / UNKNOWN
   |
   +--> Cleanup temporary resources
   |
   v
Metrics + attempt history + alerts
~~~

### 17.1. Trạng thái nghiệp vụ và trạng thái file

Nên tách:

| Trạng thái delivery | Trạng thái nguồn file | Hành động |
| --- | --- | --- |
| `PENDING` | Report chưa generate | Worker generate khi đến lượt |
| `PROCESSING` | File temp đang tạo | Không gửi nếu dữ liệu chưa hoàn tất |
| `PROCESSING` | Immutable temp ready | Build MIME và gửi |
| `RETRY` | Temp đã dọn; object version còn | Tạo temp mới ở attempt kế tiếp |
| `SENT` | Không cần temp | Xóa theo retention, giữ report nếu nghiệp vụ cần |
| `FAILED` | Object/reference còn để điều tra | Dọn temp, lưu error code và audit |
| `UNKNOWN` | SMTP outcome chưa rõ | Đối soát trước khi resend |

Không lưu `InputStream`, file descriptor hoặc tham chiếu tới đường dẫn temp **chỉ tồn tại trong một container** vào outbox như thể worker sau restart sẽ đọc được. Outbox nên lưu object ID và version bền vững, worker tự stage lại trong attempt mới.

### 17.2. Lưu checksum và content length để đối soát

Nếu yêu cầu tệp không được thay đổi qua retry, có thể lưu:

~~~text
report_version_id
declared_content_length
sha256_checksum
mime_type
safe_display_filename
~~~

Khi stage, đọc stream và tính digest theo từng buffer; sau khi hoàn tất, so sánh checksum với metadata đáng tin cậy nếu có. Điều này giúp phát hiện dữ liệu sai phiên bản hoặc bị thay đổi. Nhưng:

- SHA-256 checksum không thay thế quyền truy cập/malware scan.
- Tính digest có chi phí I/O/CPU và có thể yêu cầu đọc dữ liệu một lần.
- Với nguồn remote, metadata phải được lấy từ một nguồn đáng tin cậy; không tin checksum do người dùng tự khai làm bằng chứng xác thực.
- Không log nội dung của file để đối soát.

## 18. Câu hỏi thường gặp

**“Spring Framework Mail có hỗ trợ streaming attachment không?”**  
`MimeMessageHelper` có thể nhận `Resource`/`InputStreamSource`/`DataSource`, cho phép cấp nội dung qua stream thay vì yêu cầu sẵn toàn bộ `byte[]`. Tuy nhiên, việc transport có buffer hay đọc lại như thế nào còn phụ thuộc Jakarta Mail implementation và đường gửi SMTP.

**“Cứ dùng FileSystemResource là memory sẽ luôn O(1)?”**  
Không thể bảo đảm toàn pipeline như vậy. Nó tránh một bước giữ toàn bộ bytes do ứng dụng tạo trước, nhưng renderer, MIME layer, transfer encoding, network library và số worker đồng thời vẫn có thể sử dụng bộ nhớ đáng kể.

**“Vì sao JavaMail có thể gọi getInputStream nhiều lần?”**  
Để chuẩn bị/serialize MIME content và xử lý encoding, implementation có thể cần đọc content hơn một lần. Vì vậy contract của `InputStreamSource` dùng cho attachment phải cung cấp stream mới mỗi lần, không tái sử dụng stream đã đọc.

**“InputStreamResource có dùng được cho attachment lớn không?”**  
Thường không nên khi nó bọc một stream chỉ đọc một lần. `FileSystemResource` hoặc custom repeatable `InputStreamSource` phù hợp hơn. Nếu nguồn không đọc lại được, có thể spool một lần vào tệp tạm.

**“ByteArrayResource có luôn sai?”**  
Không. Với file nhỏ hoặc dữ liệu đã tồn tại dưới dạng `byte[]`, nó đơn giản và có thể đọc lại. Vấn đề là bộ nhớ khi file lớn hoặc concurrency cao.

**“Nếu object nằm trên S3, có thể mở stream trực tiếp không?”**  
Có thể nếu storage client mở một stream mới mỗi lần, file được pin theo version ổn định, quyền truy cập hợp lệ và latency/timeout được giới hạn. Cần kiểm thử vì Jakarta Mail có thể mở nhiều lần và tạo nhiều lượt tải.

**“Tại sao phải spool vào file tạm nếu đã có InputStream?”**  
Vì nhiều stream từ HTTP/DB chỉ đọc một lần và có thể biến mất/hết hạn trước khi SMTP cần đọc lại. Tệp tạm tạo một snapshot ổn định, có thể đọc nhiều lần với chi phí disk.

**“Có cần dùng try-with-resources cho stream không?”**  
Có cho stream mà ứng dụng trực tiếp mở và xử lý, như lúc copy sang file tạm. Nhưng không được đóng một stream được dự định dùng sau đó khi `send` còn chưa chạy. Với `FileSystemResource`, stream thường được tạo khi thư viện cần đọc.

**“File tạm có thể xóa ngay sau helper.addAttachment không?”**  
Không. `addAttachment` gắn nguồn nội dung, không bảo đảm MIME đã được serialize. Hãy giữ file tới khi `JavaMailSender.send` hoàn tất; với async, file phải sống tới khi worker hoàn tất.

**“Sử dụng @Async làm gì nếu gửi attachment vẫn chậm?”**  
`@Async` chuyển công việc khỏi thread caller, giúp request không phải chờ SMTP, nhưng không làm việc tạo file/gửi qua mạng nhanh hơn và không tự tạo job bền vững. Cần executor có giới hạn hoặc outbox/queue để quản lý capacity và retry.

**“SMTP giới hạn 25 MB, vậy file 25 MB có gửi được không?”**  
Thường không an toàn để giả định. MIME/Base64 làm message lớn hơn file gốc và còn headers, HTML, attachment khác. Cần giới hạn input thấp hơn và đo/kiểm tra theo provider.

**“Có thể gửi attachment 500 MB bằng streaming không?”**  
Kỹ thuật streaming giúp giảm heap nhưng không loại bỏ giới hạn email. Một tệp 500 MB thường vượt policy của nhiều email provider và không phù hợp với email attachment. Nên cân nhắc link tải được ủy quyền.

**“Gắn link tải có luôn an toàn hơn attachment?”**  
Không tự động. Link có thể bị forward, leak trong log hoặc hết hạn. Dữ liệu nhạy cảm cần portal auth hoặc signed URL đúng phạm vi/thời hạn và audit.

**“Nếu ứng dụng gửi 20 email cùng một file thì có cần tạo 20 bản sao?”**  
Không nhất thiết. Có thể dùng một nguồn file bất biến dùng chung và mỗi send mở stream riêng. Nhưng cần kiểm soát ownership, số đọc đồng thời và không xóa file khi worker khác đang dùng. Với dữ liệu cá nhân theo recipient, hãy tránh dùng chung nhầm file.

**“Remote stream đọc thất bại thì chắc chắn SMTP chưa nhận email?”**  
Không luôn đúng. Nếu lỗi xảy ra khi MIME đang truyền vào SMTP và client không nhận phản hồi cuối, kết quả có thể không rõ. Cần ghi stage/outcome và retry policy tính tới khả năng duplicate.

**“Có nên đặt attachment vào database BLOB rồi đọc ra?”**  
Tùy kiến trúc. Database blob có thể hợp lý nhưng có áp lực storage và DB I/O. Nếu ORM load toàn bộ BLOB vào heap, đặt nó trong một InputStreamSource ở bước sau vẫn không cải thiện memory. Cần API streaming thực sự và contract read-repeatable/snapshot.

**“Làm sao kiểm tra streaming đã tiết kiệm bộ nhớ?”**  
Dùng cùng workload và cùng kích thước file, so peak heap/GC, send duration, disk I/O và throughput giữa `readAllBytes` với `FileSystemResource`. Test một message nhỏ thành công chưa chứng minh tối ưu khi concurrency cao.

**“Có nên dùng InputStreamSource mở URL do người dùng nhập?”**  
Không trực tiếp. URL tùy ý có thể gây SSRF hoặc redirect tới hạ tầng nội bộ. Hãy dùng nguồn file đã được authorize và client có giới hạn host, protocol, redirect, timeout và size.

**“Dùng DeleteOnExit để dọn mọi file temp có đủ không?”**  
Không. File có thể tồn tại rất lâu trước khi JVM dừng, và crash cưỡng bức không bảo đảm dọn. Cần `finally`, quota và sweeper theo TTL/ownership.

**“Có nên gọi CompletableFuture.get ngay sau submit mail?”**  
Chỉ khi caller thực sự cần chờ. Gọi `get` ngay trong HTTP request có thể làm mất lợi ích async. Với delivery quan trọng, trả job ID và theo dõi trạng thái durable trong outbox.

**“Mail server giả lập có chứng minh tệp sẽ tới Gmail/Outlook không?”**  
Không. Nó chỉ kiểm tra SMTP submission và MIME content trong môi trường test. Provider thật có thêm giới hạn kích thước, lọc nội dung, malware và deliverability policy.

## 19. Checklist triển khai streaming attachment

### Chọn nguồn dữ liệu

1. Xác định kích thước attachment trung bình, tối đa và số email đồng thời.
2. Nếu file đã nằm trên disk, ưu tiên `FileSystemResource` hoặc `PathResource` thay cho `Files.readAllBytes` khi file lớn.
3. Nếu dữ liệu nhỏ và đã ở dạng `byte[]`, `ByteArrayResource` vẫn có thể phù hợp.
4. Không dùng `InputStreamResource` single-use cho attachment có thể bị đọc nhiều lần.
5. Với custom `InputStreamSource`, trả stream mới trên **mỗi lần gọi**.
6. Bảo đảm những lần đọc cùng một delivery có cùng nội dung/immutable version.
7. Nếu nguồn chỉ có thể đọc một lần, stage sang file tạm có giới hạn byte trước khi gửi.

### Giới hạn tài nguyên

8. Có max attachment bytes và max message size policy, tính MIME/Base64 overhead.
9. Kiểm tra size bằng số byte thực đọc, không chỉ tin `Content-Length`.
10. Có quota cho thư mục staging và giới hạn worker concurrent.
11. Giới hạn timeout cho SMTP **và** remote storage client.
12. Nếu file gần/vượt giới hạn provider, cân nhắc gửi link tải có quyền truy cập.
13. Không tạo toàn bộ report trong `ByteArrayOutputStream` rồi mới “stream” nếu mục tiêu là giảm heap.

### Vòng đời và độ tin cậy

14. Chỉ thêm attachment sau khi output file đã hoàn tất và đóng.
15. Giữ file nguồn tồn tại và không thay đổi cho tới khi `JavaMailSender.send` kết thúc.
16. Với `@Async`, tạo và cleanup temp trong worker hoặc chuyển quyền sở hữu có kiểm soát.
17. Không lưu stream đang mở hoặc container-local temp path như job payload bền vững.
18. Có cleanup `finally` và sweeper cho file còn sót sau crash.
19. Có state/outbox khi cần retry bền vững và phân biệt SMTP accepted với database state commit.
20. Chấp nhận rằng SMTP thuần không bảo đảm exactly-once; xử lý outcome mơ hồ.

### Bảo mật

21. Xác thực tenant và quyền đọc báo cáo trước khi mở file/object.
22. Không lấy URL hoặc filesystem path tùy ý từ người dùng để stream.
23. Dùng thư mục staging riêng với ACL/permission phù hợp.
24. Validate loại file, filename, size và malware theo chính sách.
25. Gửi SMTP qua TLS phù hợp; không log credential, file bytes hoặc raw MIME.
26. Kiểm soát retention và quyền truy cập object storage/temp file.

### Kiểm thử và quan sát

27. Test `getInputStream` nhiều lần trả fresh stream với cùng bytes.
28. Test staging vượt kích thước, lỗi giữa chừng và cleanup.
29. Test MIME filename/content type/attachment bytes và Unicode.
30. Test bằng SMTP sink hoặc container, không dùng SMTP production.
31. Test async file lifetime và worker retry sau restart.
32. Đo peak heap, GC pause, SMTP duration, disk staging và throughput.
33. Có metric/alert khi staging đầy, cleanup thất bại hoặc SMTP size limit bị từ chối.

## 20. Sơ đồ quyết định lựa chọn

~~~text
Cần gửi file đính kèm qua Spring Mail?
                 |
                 v
      Có thực sự cần attachment?
         |                 |
        Có               Không
         |                 |
         v                 v
    Kiểm tra size       Gửi link tới portal/
    và policy          storage được ủy quyền
         |
         v
   File quá lớn / vượt message limit?
         |                 |
        Có               Không
         |                 |
         v                 v
    Dùng link hoặc    File có sẵn trên disk?
    fail rõ ràng          |             |
                         Có           Không
                          |             |
                          v             v
                  FileSystemResource  Nguồn có thể mở
                          |            stream mới?
                          |             |         |
                          |            Có       Không
                          |             |         |
                          |             v         v
                          |         Versioned   Stage bounded
                          |         stream      temp file
                          |             |         |
                          +-------------+---------+
                                        |
                                        v
                           Limit concurrent sending
                                        |
                                        v
                            Build MIME + addAttachment
                                        |
                                        v
                               JavaMailSender.send
                                        |
                          +-------------+-------------+
                          |                           |
                          v                           v
                       Success                    Exception
                          |                           |
                          v                           v
                  SMTP_ACCEPTED               Classify outcome
                          |                           |
                          +-------------+-------------+
                                        |
                                        v
                            Record state and cleanup
~~~

Sơ đồ trên mô tả một quy trình quyết định **trước khi** gửi. Khi nguồn là object storage, direct stream chỉ nên được chọn nếu version/read-repeatability, network timeout và độ tin cậy được kiểm chứng; nếu không, chọn file tạm là phương án có ít biến số hơn.

## 21. Tóm tắt thực hành

Khi tối ưu attachment cho Spring Framework Mail, ba quy tắc mang lại nhiều giá trị nhất:

**1. Tránh tạo một mảng byte lớn khi không cần.** Với file đã tồn tại, `FileSystemResource` thường tốt hơn `Files.readAllBytes` rồi `ByteArrayResource`.

**2. Nguồn phải đọc lại được và tồn tại đến khi send kết thúc.** `InputStreamSource` phải mở stream mới cho mỗi lượt đọc; đừng gắn một `InputStreamResource` single-use và đóng nó trước khi gửi. Với nguồn một lần, spool sang file tạm được kiểm soát.

**3. Streaming không phá được giới hạn SMTP.** File vẫn được encode vào MIME, phải được upload qua mạng, chịu quota provider và timeout. Nếu tệp quá lớn, gửi một link tải an toàn thường hợp lý hơn tiếp tục tăng memory/timeout.

### Ví dụ rất ngắn để ghi nhớ

~~~java
// Thay vì:
helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(Files.readAllBytes(reportPath)),
        "application/pdf");

// Với file lớn đã tồn tại, ưu tiên:
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf");

// Giữ reportPath ổn định tới sau:
mailSender.send(message);
~~~

**Kết luận:** “Streaming attachment khi có thể” không có nghĩa chỉ thay loại `Resource` trong một dòng Java rồi mặc định hiệu năng đã được giải quyết. Thiết kế bền vững phải xét **nguồn file, khả năng mở stream nhiều lần, snapshot bất biến, lifecycle trong worker, giới hạn heap/disk/concurrency, MIME/Base64 overhead, timeout SMTP và an toàn dữ liệu**. Khi chọn đúng giữa resource từ file, bounded staging, remote repeatable stream hoặc link tải, ứng dụng Spring Framework Mail có thể xử lý attachment lớn ổn định hơn mà không đánh đổi tính đúng đắn và khả năng vận hành.
