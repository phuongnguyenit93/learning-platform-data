# Xóa tệp tạm sau khi gửi hoặc thất bại

Trong **Spring Framework Mail**, một email có thể đính kèm PDF, CSV, ảnh hoặc tài liệu được tạo trong lúc xử lý nghiệp vụ. Nhiều ứng dụng tạo các file này trong thư mục tạm rồi dùng `MimeMessageHelper.addAttachment(...)` để gửi. Sau khi thao tác gửi kết thúc, file tạm cần được dọn dẹp để tránh chiếm dung lượng ổ đĩa, lưu dữ liệu cá nhân quá lâu hoặc làm đầy filesystem.

Vấn đề không chỉ là gọi `Files.delete(...)`. Ứng dụng phải xác định **ai sở hữu file**, **khi nào thư viện không còn cần đọc file**, **điều gì xảy ra khi gửi lỗi**, và **có cần giữ file để retry hay không**. Nếu xóa quá sớm, attachment có thể rỗng hoặc quá trình gửi thất bại. Nếu chỉ xóa khi gửi thành công, file có thể bị bỏ lại sau exception. Nếu xóa ngay sau lần thử đầu tiên trong một hệ thống có retry, worker có thể không còn dữ liệu để gửi lại.

Nguyên tắc cơ bản:

> Tệp tạm do một lần gửi tạo ra phải có một chủ sở hữu rõ ràng và một điểm kết thúc vòng đời. Với gửi đồng bộ, dọn file trong `finally` sau khi lời gọi gửi kết thúc. Với gửi bất đồng bộ hoặc có retry, chỉ dọn khi công việc đã kết thúc theo chính sách lưu trữ.

## 1. Vòng đời của một attachment tạm

Một quy trình gửi email có attachment thường gồm các bước:

1. Tạo nội dung file (ví dụ PDF hóa đơn).
2. Ghi bytes vào một file tạm có tên duy nhất.
3. Tạo `MimeMessage` và khai báo attachment bằng một `Resource` trỏ tới file.
4. Gọi `JavaMailSender.send(...)`.
5. Khi thao tác gửi đồng bộ kết thúc, xóa file tạm nếu không còn cần dùng.
6. Nếu xóa thất bại, ghi nhận để dọn lại; không để lỗi dọn file che mất kết quả gửi.

~~~mermaid
flowchart TD
    A["Tạo nội dung attachment"] --> B["Tạo file tạm duy nhất"]
    B --> C["Ghi bytes vào file"]
    C --> D["Tạo MimeMessage + addAttachment"]
    D --> E["JavaMailSender.send"]
    E --> F{"Lời gọi gửi kết thúc?"}
    F -->|Thành công| G["Thực hiện cleanup"]
    F -->|Exception| G
    G --> H{"Xóa file thành công?"}
    H -->|Có| I["Kết thúc vòng đời file"]
    H -->|Không| J["Log an toàn / ghi nhận cleanup retry"]
~~~

**Điểm dọn dẹp là sau khi `send(...)` trả về hoặc ném exception**, không phải ngay sau `addAttachment(...)`. Phương thức gửi của Spring Mail/Jakarta Mail thường xử lý transport đồng bộ trong lời gọi đó; trong lúc dựng và truyền MIME, thư viện có thể cần đọc resource. Xóa trước khi lời gọi gửi hoàn tất có thể khiến dữ liệu không còn sẵn sàng.

Điều này giả định sender thực hiện gửi đồng bộ như `JavaMailSenderImpl` thông thường. Nếu ứng dụng bọc sender bằng một cơ chế bất đồng bộ tùy chỉnh, cần xác định thời điểm future/callback thực sự hoàn tất việc đọc attachment trước khi cleanup.

## 2. Vì sao phải xóa cả khi gửi thành công lẫn thất bại?

File tạm có thể chứa dữ liệu cá nhân hoặc thông tin nghiệp vụ: hóa đơn, báo cáo, địa chỉ khách hàng, số liệu giao dịch. Nếu file còn sót lại, nó có thể:

- làm tăng dung lượng thư mục temp theo thời gian;
- bị đọc bởi process hoặc tài khoản có quyền truy cập filesystem;
- xuất hiện trong backup, snapshot hoặc công cụ giám sát;
- gây lỗi tạo file mới khi đĩa đầy;
- làm lộ dữ liệu sau khi job đã hết thời hạn xử lý.

Ví dụ, một service tạo 100 file PDF mỗi giờ, mỗi file 5 MB. Nếu không dọn file, dung lượng có thể tăng khoảng 500 MB mỗi giờ (chưa tính overhead). Trong môi trường container có filesystem giới hạn, điều này có thể làm ứng dụng ngừng tạo file hoặc ảnh hưởng các thành phần khác.

### 2.1. Gửi thành công

Khi `sender.send(mime)` trả về bình thường, transport đồng bộ đã hoàn tất thao tác nộp thư theo hợp đồng của sender. Nếu attachment chỉ được tạo để phục vụ lần gửi đó và không cần giữ cho mục đích khác, có thể xóa file tạm ngay sau đó.

Lưu ý: **gửi thành công không đồng nghĩa email đã đến Inbox hoặc người nhận đã tải file**. JavaMailSender thường chỉ cho biết thao tác gửi/nộp thư không phát sinh lỗi đồng bộ. File tạm có thể được dọn sau khi transport đã dùng xong bytes, không cần chờ người nhận mở thư.

### 2.2. Gửi thất bại

Lỗi có thể xảy ra khi:

- tạo hoặc ghi file thất bại;
- resource không đọc được;
- tạo MIME message lỗi;
- SMTP host không truy cập được;
- xác thực SMTP thất bại;
- server từ chối người nhận hoặc nội dung;
- kết nối bị timeout trong quá trình gửi.

Với một lần gửi đồng bộ không có retry, file tạm cũng cần được xóa trong mọi nhánh exception. Nếu chỉ viết cleanup sau `send(...)`, dòng xóa sẽ không được chạy khi `send` ném exception.

## 3. Dùng try/finally để bảo đảm cleanup

Java cung cấp `try/finally` để chạy phần dọn dẹp dù khối gửi kết thúc bình thường hay phát sinh exception.

Ví dụ:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TemporaryFileCleanup {
    private static final Logger log =
            LoggerFactory.getLogger(TemporaryFileCleanup.class);

    public void process(Path tempFile) throws IOException {
        try {
            // Đọc hoặc gửi file.
            sendAttachment(tempFile);
        } finally {
            try {
                Files.deleteIfExists(tempFile);
            } catch (IOException cleanupException) {
                log.warn(
                        "Could not delete temporary attachment file",
                        cleanupException
                );
            }
        }
    }

    private void sendAttachment(Path path) {
        // Thực hiện thao tác gửi đồng bộ.
    }
}
~~~

`finally` được chạy khi khối `try` kết thúc, kể cả khi có exception. `Files.deleteIfExists(...)` xóa file nếu còn tồn tại; nếu file đã được xóa trước đó thì không báo lỗi chỉ vì nó không tồn tại.

Trong ví dụ, cleanup exception được ghi log và không ném lại để **không che lấp lỗi gửi ban đầu**. Nếu gửi đã thành công nhưng cleanup thất bại, cũng không nên tự động báo “gửi email thất bại” chỉ vì file tạm chưa xóa được; việc nộp thư và việc dọn file là hai kết quả độc lập.

### 3.1. Tránh để cleanup exception che lỗi gửi

Một cách viết dễ gây nhầm:

~~~java
try {
    sender.send(mime);
} finally {
    Files.delete(tempFile); // Có thể ném IOException.
}
~~~

Nếu `sender.send(...)` ném `MailException` nhưng `Files.delete(...)` cũng ném `IOException`, exception trong `finally` có thể trở thành exception mà tầng gọi nhìn thấy, làm mất ngữ cảnh lỗi gửi ban đầu.

Có hai cách quản lý:

- **Ghi nhận cleanup failure riêng** và không ném nó như kết quả gửi thất bại; phù hợp khi email đã được nộp và cleanup có janitor xử lý lại.
- **Dùng try-with-resources** với một resource có `close()`; Java tự gắn exception khi đóng vào `suppressed exceptions` nếu khối chính đã thất bại. Tuy nhiên, cần thiết kế sao cho lỗi close sau khi gửi thành công không bị hiểu nhầm là gửi thất bại và kích hoạt gửi trùng.

## 4. Ví dụ hoàn chỉnh: tạo PDF tạm, gửi và xóa

Giả sử ứng dụng đã có bytes PDF được tạo từ dữ liệu hóa đơn. Ta ghi bytes ra file tạm, dùng `FileSystemResource` để đính kèm, rồi xóa file trong `finally`:

~~~java
package com.example.mail.application;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private static final Logger log =
            LoggerFactory.getLogger(InvoiceMailService.class);

    private final JavaMailSender sender;

    public InvoiceMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNumber,
            byte[] pdfBytes)
            throws IOException, MessagingException {

        Path tempFile = Files.createTempFile("invoice-", ".pdf");
        String tempId = tempFile.getFileName().toString();

        try {
            Files.write(tempFile, pdfBytes);

            MimeMessage mime = sender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom("billing@example.com");
            helper.setTo(recipient);
            helper.setSubject("Hóa đơn " + invoiceNumber);
            helper.setText(
                    "Hóa đơn của bạn được đính kèm trong email này."
            );
            helper.addAttachment(
                    "Hóa đơn " + invoiceNumber + ".pdf",
                    new FileSystemResource(tempFile.toFile()),
                    "application/pdf"
            );

            sender.send(mime);
        } finally {
            try {
                Files.deleteIfExists(tempFile);
            } catch (IOException cleanupException) {
                // Ghi nhận cleanup riêng, không biến lỗi dọn file
                // thành kết luận rằng email chưa được nộp.
                log.warn(
                        "Could not clean temporary invoice file: {}",
                        tempId,
                        cleanupException
                );
            }
        }
    }
}
~~~

Luồng hoạt động:

1. `Files.createTempFile(...)` tạo một file tạm duy nhất trong thư mục tạm mặc định của hệ điều hành.
2. `Files.write(...)` ghi nội dung PDF.
3. `FileSystemResource` cung cấp file cho `MimeMessageHelper`.
4. `addAttachment(...)` thêm MIME part có tên hiển thị và content type.
5. `sender.send(mime)` thực hiện thao tác gửi đồng bộ.
6. Dù bước ghi, dựng MIME hoặc gửi có lỗi, `finally` vẫn cố gắng xóa file.

Tên file trên đĩa được hệ điều hành tạo riêng, ví dụ `invoice-8349271.pdf`; tên hiển thị cho người nhận là `Hóa đơn INV-2026-001.pdf`. Tách hai tên giúp tránh để lộ tên lưu trữ nội bộ và cho phép dùng tên hiển thị có Unicode.

### 4.1. Vì sao tạo file trước khối try?

`Files.createTempFile(...)` phải trả về một `Path` trước khi khối `finally` có thể xóa nó. Nếu việc tạo file thất bại thì chưa có file nào để dọn và exception được truyền lên. Sau khi path đã được tạo, mọi bước ghi file, dựng MIME và gửi đều nằm trong `try` để `finally` bảo đảm cleanup.

Nếu `Files.write(...)` thất bại một phần, file có thể vẫn tồn tại; `finally` vẫn cố xóa nó.

### 4.2. Dùng thư mục temp riêng của ứng dụng

Có thể tạo file trong một thư mục được quản lý riêng:

~~~java
Path tempDirectory = Path.of("/var/app/mail-tmp");
Files.createDirectories(tempDirectory);

Path tempFile = Files.createTempFile(
        tempDirectory,
        "invoice-",
        ".pdf"
);
~~~

Thư mục riêng giúp:

- giới hạn nơi ứng dụng tạo file;
- đặt quyền truy cập theo user chạy service;
- thống kê dung lượng và tuổi file;
- chạy tác vụ dọn file mồ côi theo prefix/TTL;
- không xóa nhầm file tạm của process khác.

Trên Windows, Linux và container, quyền filesystem được thiết lập khác nhau. Hãy bảo đảm thư mục chỉ cho tài khoản ứng dụng và các tiến trình được cấp quyền đọc cần thiết truy cập. Với tài liệu nhạy cảm, cân nhắc volume mã hóa và retention phù hợp.

## 5. Dùng helper quản lý file tạm

Nếu nhiều service cần cùng quy tắc tạo và dọn file, có thể gom vòng đời vào một lớp nhỏ. Lớp này tạo file, cung cấp `Path` và tự dọn khi đóng:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class TemporaryAttachment implements AutoCloseable {
    private static final Logger log =
            LoggerFactory.getLogger(TemporaryAttachment.class);

    private final Path path;
    private final String cleanupId;

    private TemporaryAttachment(Path path) {
        this.path = path;
        this.cleanupId = path.getFileName().toString();
    }

    public static TemporaryAttachment create(
            Path directory,
            String prefix,
            String suffix) throws IOException {
        Files.createDirectories(directory);
        Path path = Files.createTempFile(directory, prefix, suffix);
        return new TemporaryAttachment(path);
    }

    public Path path() {
        return path;
    }

    @Override
    public void close() {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ex) {
            log.warn(
                    "Could not clean temporary attachment: {}",
                    cleanupId,
                    ex
            );
        }
    }
}
~~~

Sử dụng:

~~~java
try (TemporaryAttachment temp =
             TemporaryAttachment.create(
                     Path.of("/var/app/mail-tmp"),
                     "invoice-",
                     ".pdf")) {

    Files.write(temp.path(), pdfBytes);

    MimeMessage mime = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, "UTF-8");
    helper.setTo(recipient);
    helper.setSubject("Hóa đơn");
    helper.setText("Vui lòng xem file đính kèm.");
    helper.addAttachment(
            "invoice.pdf",
            new FileSystemResource(temp.path().toFile())
    );

    sender.send(mime);
}
~~~

Khi rời khỏi khối `try`, Java gọi `close()` dù có exception. Trong ví dụ, `close()` bắt lỗi xóa và ghi log để không làm thay đổi kết quả gửi đã hoàn tất. Nếu tổ chức muốn cleanup failure trở thành lỗi có thể giám sát, helper có thể ghi một sự kiện/metric hoặc tạo cleanup task thay vì âm thầm bỏ qua.

**Không dùng helper này để quản lý file gốc do người dùng tải lên hoặc file thuộc một quy trình khác.** Nó chỉ nên sở hữu file tạm mà chính nó tạo. Nếu nhận một `Path` có sẵn từ bên ngoài, không được tự động xóa file đó khi đóng trừ khi ownership được chuyển giao rõ ràng.

## 6. Có nên dùng ByteArrayResource thay cho file tạm?

Không phải attachment nào cũng cần ghi xuống filesystem. Nếu nội dung đã có trong bộ nhớ và kích thước nhỏ/vừa, có thể đính kèm trực tiếp:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Ưu điểm:

- không tạo file tạm;
- không cần cleanup filesystem;
- phù hợp với dữ liệu bytes đã được tạo sẵn và có kích thước giới hạn.

Nhược điểm:

- toàn bộ bytes chiếm heap trong thời gian sống của object;
- nhiều email đồng thời với attachment lớn có thể gây áp lực bộ nhớ;
- nếu queue/job cần retry qua restart, byte array trong bộ nhớ không phải storage bền vững.

### 6.1. Chọn theo kích thước và nguồn dữ liệu

| Nguồn/đặc điểm | Cách thường phù hợp |
| --- | --- |
| PDF nhỏ đã có trong byte array | `ByteArrayResource` |
| File đã được tạo trên filesystem | `FileSystemResource` |
| File tĩnh đóng gói trong ứng dụng | `ClassPathResource` |
| File lớn, có thể mở stream nhiều lần | Resource/`InputStreamSource` có vòng đời đọc rõ |
| File cần retry sau restart | Object storage hoặc spool bền vững có ID/version |
| Dữ liệu chỉ tồn tại trong một lần gửi đồng bộ | Byte array hoặc temp file, tùy giới hạn bộ nhớ |

Việc chọn resource không thay đổi nguyên tắc: nếu tạo file tạm, xác định chủ sở hữu và thời điểm cleanup; nếu dùng bytes trong memory, xác định giới hạn kích thước và thời điểm giải phóng tham chiếu.

## 7. Khi nào an toàn để xóa file sau send?

Với `JavaMailSenderImpl` và transport Jakarta Mail thông thường, `send(...)` thực hiện thao tác gửi đồng bộ: khi phương thức trả về hoặc ném lỗi, lần gọi đó đã kết thúc. Đây là mốc thích hợp để dọn file chỉ dùng cho lần gửi ấy.

Tuy nhiên, cần kiểm tra kiến trúc nếu:

- sender là wrapper tự triển khai, chỉ enqueue việc gửi rồi trả về ngay;
- service gọi `@Async` và truyền đường dẫn file sang executor khác;
- một callback hoặc publisher chưa hoàn thành việc serialize MIME;
- resource được dùng lại bởi một tác vụ khác sau khi gửi;
- hệ thống cần giữ file để retry hoặc điều tra lỗi.

### 7.1. Không xóa ngay sau addAttachment

Không nên:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(tempFile.toFile())
);

Files.deleteIfExists(tempFile); // Quá sớm.
sender.send(mime);
~~~

`addAttachment` thiết lập part và nguồn dữ liệu; tùy thời điểm provider đọc resource, bytes có thể chưa được tiêu thụ. File phải còn tồn tại trong suốt quá trình gửi.

### 7.2. Không xóa ngay khi producer enqueue job bất đồng bộ

Giả sử producer tạo file và enqueue:

~~~java
queue.add(new MailJob(tempFile.toString(), recipient));
Files.deleteIfExists(tempFile); // Worker có thể chưa đọc file.
~~~

Worker chỉ nhận một đường dẫn tới file đã bị xóa. Nếu producer và worker chạy trên hai máy/container khác nhau, đường dẫn local còn có thể không tồn tại trên máy worker ngay từ đầu.

Trong mô hình bất đồng bộ, **producer không xóa file sau enqueue** nếu job vẫn cần file. Quyền cleanup thuộc về thành phần quản lý vòng đời job/artifact, sau khi worker đã hoàn tất hoặc job bị hủy/đánh dấu hết hạn.

## 8. Gửi bất đồng bộ và retry: giữ file tới khi nào?

Một lần thử gửi có thể thất bại tạm thời. Nếu email cần retry, xóa attachment ngay trong `finally` của **mỗi lần thử** sẽ làm lần thử sau không còn file để đọc.

Hãy phân biệt:

- **Cleanup sau một attempt:** chỉ phù hợp nếu không còn retry hoặc dữ liệu có thể được tạo lại an toàn.
- **Cleanup sau terminal state:** phù hợp với queue có retry; chỉ xóa khi job đã hoàn tất, bị hủy hoặc hết chính sách retry.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING
    PROCESSING --> SUBMITTED: sender hoàn tất không lỗi
    PROCESSING --> RETRY_WAIT: lỗi có thể thử lại
    RETRY_WAIT --> PROCESSING: tới thời điểm retry
    PROCESSING --> FAILED_FINAL: hết retry hoặc lỗi vĩnh viễn
    SUBMITTED --> CLEANUP
    FAILED_FINAL --> CLEANUP
    CLEANUP --> [*]
~~~

`SUBMITTED` biểu thị sender đã hoàn tất thao tác nộp thư; nó không khẳng định Inbox delivery. Nếu provider gửi webhook bounce sau đó, đó là trạng thái vận chuyển/delivery riêng, không có nghĩa phải giữ file PDF tạm của lần gửi ban đầu.

### 8.1. Job nên tham chiếu artifact bền vững

Nếu worker có thể chạy sau khi process producer dừng, không nên dựa vào file tạm trong thư mục hệ điều hành của producer. Một lựa chọn là lưu attachment vào object storage hoặc vùng spool bền vững:

~~~text
Producer
  |
  +--> tạo file -> upload artifact với key/version
  |
  +--> enqueue MailJob:
          jobId
          recipient
          subject
          artifactKey
          artifactVersion
  |
Worker
  |
  +--> tải đúng artifact version
  +--> tạo MimeMessage
  +--> gửi
  +--> cập nhật trạng thái job
  |
Cleanup policy
  |
  +--> xóa artifact khi job terminal và retention cho phép
~~~

Payload chỉ giữ ID hoặc key của artifact, không cần chứa đường dẫn local. Artifact cần có quyền truy cập giới hạn và phiên bản bất biến để retry luôn dùng đúng file.

### 8.2. Không xóa file khi retry còn khả năng xảy ra

Ví dụ:

~~~text
Job J-100:
  status = RETRY_WAIT
  attempts = 1
  attachmentKey = invoices/2026/INV-100.pdf
  retryAt = 2026-11-12T10:05:00Z
~~~

Ở trạng thái `RETRY_WAIT`, file/artifact vẫn phải được giữ. Chỉ khi:

- gửi đã được nộp thành công và job không cần retry;
- job bị hủy theo nghiệp vụ;
- hết số lần thử và được đánh dấu `FAILED_FINAL`;
- hoặc hết retention theo chính sách;

thì cleanup mới có thể xóa artifact. Nếu hệ thống cho phép retry thủ công sau `FAILED_FINAL`, cần quyết định giữ file trong thời gian chờ hỗ trợ hay yêu cầu tạo lại artifact.

### 8.3. Lỗi gửi không phải lúc nào cũng biết chắc SMTP đã nhận hay chưa

Nếu client mất kết nối sau khi đã truyền nội dung nhưng trước khi nhận phản hồi cuối cùng, ứng dụng có thể không biết server đã chấp nhận thư hay chưa. Retry có thể tạo email trùng.

Đây là vấn đề **idempotency và trạng thái gửi**, không giải quyết được bằng việc giữ hay xóa file. Job cần ID ổn định, số lần thử, thời điểm và trạng thái. Nếu provider hỗ trợ idempotency key hoặc tra cứu message ID, hãy sử dụng theo contract của họ. Với SMTP thuần, không nên hứa hẹn exactly-once chỉ dựa vào một queue.

## 9. Dọn file tạm khi ứng dụng bị dừng đột ngột

`finally` chạy khi luồng Java thoát khỏi khối try theo cách thông thường, bao gồm exception. Nhưng không bảo đảm được gọi khi:

- process bị kill cưỡng bức;
- máy/container bị mất điện hoặc bị xóa ngay;
- JVM crash;
- node bị thu hồi trước khi cleanup chạy;
- hệ thống filesystem gặp lỗi nghiêm trọng.

Vì vậy, production có thể cần một **janitor job** để tìm và dọn file tạm mồ côi sau một khoảng thời gian.

### 9.1. Thiết kế thư mục riêng và prefix nhận diện

Ví dụ:

~~~text
/var/app/mail-tmp/
  invoice-a83f....pdf
  report-1b29....csv
  attachment-7e10....zip
~~~

Chỉ xóa những file:

- nằm trong thư mục riêng do mail service quản lý;
- có prefix/metadata nhận diện của ứng dụng;
- cũ hơn TTL đã định;
- không được job đang chạy tham chiếu;
- không bị khóa/đang sử dụng bởi một worker khác nếu hệ điều hành hoặc ứng dụng cần kiểm tra điều đó.

Không chạy lệnh xóa đệ quy trên thư mục temp dùng chung của toàn máy. Điều đó có thể xóa file thuộc ứng dụng hoặc người dùng khác.

### 9.2. Ví dụ janitor đơn giản

Một job định kỳ có thể xóa file cũ hơn một khoảng thời gian, trong **thư mục mail temp riêng**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailTempJanitor {
    private static final Logger log =
            LoggerFactory.getLogger(MailTempJanitor.class);

    private final Path tempDirectory =
            Path.of("/var/app/mail-tmp");

    private final Duration maxAge = Duration.ofHours(24);

    @Scheduled(fixedDelayString = "PT1H")
    public void removeOldFiles() {
        if (!Files.isDirectory(tempDirectory)) {
            return;
        }

        Instant cutoff = Instant.now().minus(maxAge);

        try (Stream<Path> files = Files.list(tempDirectory)) {
            files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName()
                            .toString().startsWith("mail-"))
                    .forEach(path -> deleteIfExpired(path, cutoff));
        } catch (IOException ex) {
            log.warn("Could not scan mail temporary directory", ex);
        }
    }

    private void deleteIfExpired(Path path, Instant cutoff) {
        try {
            Instant modifiedAt = Files.getLastModifiedTime(path).toInstant();
            if (modifiedAt.isBefore(cutoff)) {
                Files.deleteIfExists(path);
            }
        } catch (IOException ex) {
            log.warn("Could not clean an old mail temporary file", ex);
        }
    }
}
~~~

Để job chạy, ứng dụng cần bật scheduling bằng cấu hình phù hợp (ví dụ `@EnableScheduling`). Ví dụ này chỉ là janitor cơ bản, **không đủ cho mọi hệ thống retry**: nếu một job hợp lệ có thể chờ hơn 24 giờ, janitor có thể xóa file đang cần. Production nên kiểm tra trạng thái job/artifact trước khi xóa, hoặc dùng storage lifecycle policy dựa trên trạng thái/retention được quản lý.

### 9.3. Kiểm soát đường dẫn và symlink

Nếu đường dẫn được lấy từ job hoặc database, không nối chuỗi tùy ý với thư mục temp:

~~~java
Path candidate = tempDirectory.resolve(untrustedName).normalize();
if (!candidate.startsWith(tempDirectory.normalize())) {
    throw new SecurityException("Invalid temporary file path");
}
~~~

Kiểm tra này giúp phát hiện một số path traversal cơ bản. Trong môi trường có thể bị người khác tạo symlink hoặc thay đổi filesystem đồng thời, cần thêm chính sách quyền truy cập, kiểm tra loại file thực tế và thao tác filesystem an toàn theo nền tảng. Cách tốt hơn là lưu **opaque ID** do ứng dụng sinh thay vì nhận tên đường dẫn từ bên ngoài.

## 10. Không nhầm xóa file với xóa an toàn tuyệt đối

`Files.deleteIfExists(path)` yêu cầu filesystem xóa entry của file. Điều đó **không bảo đảm bytes đã bị ghi đè hoặc biến mất vật lý** ngay lập tức khỏi thiết bị lưu trữ. Với SSD, copy-on-write filesystem, snapshot, backup hoặc storage phân tán, việc xóa tên file không đồng nghĩa không thể khôi phục dữ liệu.

Nếu attachment chứa thông tin nhạy cảm:

- giới hạn quyền đọc thư mục temp;
- dùng volume/storage mã hóa ở mức phù hợp;
- giới hạn thời gian tồn tại và backup/snapshot;
- giảm dữ liệu nhạy cảm có trong file;
- dùng cơ chế xóa/retention theo yêu cầu pháp lý và chính sách tổ chức;
- không ghi bytes, nội dung file hoặc đường dẫn có thông tin cá nhân vào log.

Không nên tự viết hàm ghi đè bytes rồi xóa và tuyên bố “secure delete” trên mọi filesystem. Cách đó không thể bảo đảm với SSD, journaling, snapshot hoặc storage được quản lý bởi nền tảng khác.

## 11. Quản lý nhiều file tạm trong một email

Một email có thể có nhiều attachment:

~~~java
List<Path> temporaryFiles = new ArrayList<>();
~~~

Nếu tạo từng file, phải đảm bảo **mọi file đã tạo đều được dọn**, kể cả khi tạo file thứ ba thất bại sau khi hai file đầu đã được tạo.

Ví dụ:

~~~java
List<Path> temporaryFiles = new ArrayList<>();

try {
    Path invoice = createTemporaryInvoice();
    temporaryFiles.add(invoice);

    Path detail = createTemporaryDetail();
    temporaryFiles.add(detail);

    Path terms = createTemporaryTerms();
    temporaryFiles.add(terms);

    MimeMessage mime = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, "UTF-8");

    helper.setTo(recipient);
    helper.setSubject("Hồ sơ đơn hàng");
    helper.setText("Các tài liệu được đính kèm.");

    helper.addAttachment(
            "Hóa đơn.pdf",
            new FileSystemResource(invoice.toFile())
    );
    helper.addAttachment(
            "Chi tiết.xlsx",
            new FileSystemResource(detail.toFile())
    );
    helper.addAttachment(
            "Điều khoản.pdf",
            new FileSystemResource(terms.toFile())
    );

    sender.send(mime);
} finally {
    for (Path path : temporaryFiles) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ex) {
            log.warn("Could not clean a temporary mail attachment", ex);
        }
    }
}
~~~

Ví dụ giả định các hàm `createTemporary...` trả về file đã tạo và có logger `log`. Mỗi path được thêm vào danh sách ngay sau khi tạo thành công, vì vậy nếu bước tạo tiếp theo thất bại thì các file trước đó vẫn được dọn trong `finally`.

Một helper quản lý nhiều attachment có thể giảm lặp code, nhưng cần bảo đảm:

- chỉ lưu những file mà helper sở hữu;
- không xóa file nguồn do caller sở hữu;
- không bỏ qua file đã tạo khi bước ghi dữ liệu thất bại;
- ghi nhận cleanup failure mà không che lỗi gửi;
- không dọn file còn cần cho retry.

## 12. Khi file tạm được tạo từ InputStream

Có thể nhận nội dung từ một nguồn stream và ghi vào file:

~~~java
Path tempFile = Files.createTempFile("attachment-", ".bin");
try {
    try (InputStream input = sourceStream) {
        Files.copy(
                input,
                tempFile,
                StandardCopyOption.REPLACE_EXISTING
        );
    }

    // Dùng tempFile làm attachment rồi gửi.
} finally {
    try {
        Files.deleteIfExists(tempFile);
    } catch (IOException ex) {
        log.warn("Could not clean temporary attachment", ex);
    }
}
~~~

`InputStream` cần được đóng sau khi copy. File tạm được giữ cho tới khi sender hoàn tất đọc resource. Nếu stream chỉ đọc được một lần, việc ghi ra file có thể giúp worker đọc lại file khi cần, nhưng nếu có retry qua restart thì file cần nằm trên storage bền vững thay vì thư mục tạm của process.

Với resource của Spring, hãy hiểu rõ `InputStreamSource` có thể được mở nhiều lần hay không. Một nguồn chỉ cấp stream một lần không phù hợp với mọi cách xử lý MIME, vì provider có thể yêu cầu mở lại trong lúc serialize hoặc tính toán nội dung.

## 13. Xử lý lỗi cleanup riêng với lỗi gửi

Một thao tác gửi email và một thao tác xóa file có hai kết quả độc lập:

| Gửi | Cleanup | Ý nghĩa | Hành động |
| --- | --- | --- | --- |
| Thành công | Thành công | Mail đã được nộp; file đã được dọn | Kết thúc |
| Thất bại | Thành công | Mail attempt lỗi; file đã được dọn | Phân loại lỗi gửi, retry theo chính sách |
| Thành công | Thất bại | Mail đã được nộp; file còn sót | Ghi cleanup failure và dọn lại, tránh gửi lại chỉ vì cleanup |
| Thất bại | Thất bại | Mail attempt lỗi; file còn sót | Ghi cả hai lỗi; cleanup job/ops xử lý file |

### 13.1. Vì sao cleanup failure không nên tự kích hoạt retry email?

Giả sử:

1. SMTP server chấp nhận email và `sender.send(...)` trả về.
2. `Files.deleteIfExists(...)` thất bại do permission hoặc file đang bị khóa.
3. Service ném một exception tổng quát.
4. Tầng gọi hiểu nhầm rằng gửi thất bại và retry.

Kết quả có thể là **hai email giống nhau**, dù lỗi ban đầu chỉ là cleanup. Do đó, hãy lưu trạng thái nộp thư riêng với trạng thái cleanup. Nếu cleanup lỗi, tạo metric/log/cleanup record; không thay đổi `SUBMITTED` thành `FAILED_TO_SEND`.

### 13.2. Không log dữ liệu nhạy cảm

Log nên có:

~~~text
mailJobId=job-812
attachmentId=att-44
cleanupResult=FAILED
errorType=AccessDeniedException
~~~

Tránh log:

- toàn bộ bytes của file;
- nội dung hóa đơn hoặc báo cáo;
- token hoặc dữ liệu xác thực;
- đường dẫn đầy đủ chứa tên khách hàng/mã hồ sơ nhạy cảm nếu không cần;
- toàn bộ email body.

Một ID ngẫu nhiên do ứng dụng sinh đủ để truy vết file temp trong phần lớn tình huống.

## 14. Kiểm thử cleanup khi gửi thành công và thất bại

Nên kiểm tra hai nhánh cơ bản:

1. Khi sender trả về bình thường, file tạm không còn tồn tại.
2. Khi sender ném exception, file tạm vẫn được cleanup.

Một cách test là trích xuất logic tạo file và gửi vào một service dùng thư mục temp riêng. JUnit có `@TempDir` để quản lý thư mục trong test:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;

class TemporaryInvoiceMailServiceTest {
    @TempDir
    Path tempDirectory;

    @Test
    void removesTemporaryFileAfterSuccessfulSend() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        TemporaryInvoiceMailService service =
                new TemporaryInvoiceMailService(sender, tempDirectory);

        Path created = service.createAndSend("customer@example.net");

        assertFalse(Files.exists(created));
        verify(sender).send(org.mockito.ArgumentMatchers.any(
                jakarta.mail.internet.MimeMessage.class));
    }

    @Test
    void removesTemporaryFileWhenSendFails() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        doThrow(new MailSendException("SMTP unavailable"))
                .when(sender).send(
                        org.mockito.ArgumentMatchers.any(
                                jakarta.mail.internet.MimeMessage.class));

        TemporaryInvoiceMailService service =
                new TemporaryInvoiceMailService(sender, tempDirectory);

        Path created = service.createAndSend("customer@example.net");

        assertFalse(Files.exists(created));
    }
}
~~~

Đoạn test là **khung minh họa**: để có thể kiểm tra path sau khi phương thức đã ném exception, service có thể nhận một callback/observer test hoặc tách thành một thành phần tạo file có thể theo dõi. Một thiết kế test rõ hơn là truyền một `TemporaryAttachmentStore` fake ghi lại path được tạo, rồi xác nhận file không tồn tại sau mỗi nhánh. Không nên bắt exception rồi giả định path được trả về nếu method không thể trả về do exception.

### 14.1. Tách store để test rõ ràng

Ví dụ interface:

~~~java
public interface TemporaryAttachmentStore {
    Path create(String prefix, String suffix) throws IOException;
    void deleteQuietly(Path path);
}
~~~

Service nhận store qua constructor. Trong test, store thật có thể dùng `@TempDir` và giữ lại path cuối cùng; store giả có thể ghi nhận các lần tạo/xóa. Nhờ vậy, kiểm tra cleanup không phụ thuộc vào việc truy cập thư mục hệ thống hoặc đoán tên file.

### 14.2. Kiểm thử cả lỗi tạo/ghi file

Ngoài lỗi SMTP, cần xét:

- thư mục temp không tồn tại hoặc không có quyền ghi;
- filesystem hết dung lượng;
- ghi file thất bại giữa chừng;
- resource không mở được;
- attachment quá lớn;
- xóa file bị từ chối quyền hoặc file đang bị lock.

Nếu file chưa được tạo, không có gì để xóa. Nếu file đã được tạo nhưng ghi dở, cleanup vẫn cần được thực hiện. Nếu cleanup thất bại, phải có cách quan sát và xử lý file mồ côi.

## 15. Lưu ý về file lớn và tài nguyên hệ thống

Đối với attachment lớn, việc dùng temp file thường giảm áp lực heap so với giữ toàn bộ bytes trong một `byte[]`, nhưng đổi lại cần quản lý filesystem:

- giới hạn dung lượng tối đa của file được phép gửi;
- giới hạn tổng dung lượng attachment của một email;
- đặt quota cho thư mục temp;
- theo dõi dung lượng trống, số lượng file và tuổi file;
- dọn file mồ côi theo TTL;
- giới hạn số worker xử lý attachment đồng thời;
- đặt timeout cho quá trình tạo và gửi.

Ví dụ nếu 20 worker cùng tạo file 50 MB, nhu cầu dung lượng tạm có thể vượt 1 GB. Dù mỗi lần gửi cuối cùng đều xóa file, vẫn cần đủ không gian cho các lần gửi đang diễn ra đồng thời.

Nếu provider giới hạn tổng kích thước message, cần tính thêm Base64 overhead và MIME headers. Khi file vượt giới hạn, cân nhắc gửi URL tải xuống có xác thực và thời hạn thay vì đính kèm.

## 16. Trường hợp file tạm là dữ liệu nhạy cảm

Hóa đơn, sao kê, báo cáo cá nhân và tài liệu nội bộ có thể chứa dữ liệu cần bảo vệ. Việc xóa file sau gửi là một phần của vòng đời dữ liệu, nhưng không thay thế các biện pháp khác.

### 16.1. Quyền truy cập thư mục

- Chọn thư mục riêng của ứng dụng.
- Chỉ tài khoản chạy service được phép tạo/đọc file.
- Không lưu file tạm trong thư mục web public hoặc thư mục được đồng bộ ra ngoài.
- Không cấp quyền đọc rộng cho mọi user trên máy chủ.
- Với container, xem xét volume mount và quyền của user bên trong container.

### 16.2. Tên file ngẫu nhiên

`Files.createTempFile` tạo tên duy nhất, giảm nguy cơ va chạm và đoán tên. Không tự tạo tên kiểu:

~~~java
Path path = tempDirectory.resolve(
        "invoice-" + customerName + ".pdf");
~~~

Tên khách hàng có thể chứa ký tự không an toàn, gây lộ thông tin và tạo đường dẫn khó kiểm soát. Dùng prefix cố định, suffix theo loại file và để API tạo phần tên ngẫu nhiên.

### 16.3. Xóa không đồng nghĩa xóa vật lý an toàn

Lệnh xóa file không đảm bảo dữ liệu đã biến mất khỏi SSD, snapshot hoặc backup. Nếu yêu cầu bảo mật cao:

- mã hóa volume hoặc storage;
- giảm dữ liệu nhạy cảm ghi ra disk;
- áp dụng retention cho backup/snapshot;
- dùng storage có cơ chế crypto-erasure phù hợp nếu được hỗ trợ;
- không tuyên bố secure erase chỉ dựa vào `Files.deleteIfExists`.

## 17. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ xóa file sau `send` mà không dùng finally | File còn sót khi send ném exception | Cleanup trong `finally` hoặc resource owner |
| Xóa ngay sau `addAttachment` | Provider có thể chưa đọc file | Giữ file đến khi gửi đồng bộ kết thúc |
| Dùng file local cho job chạy trên node khác | Worker không tìm thấy path | Lưu artifact ở storage dùng chung/bền vững |
| Xóa file ở producer ngay sau enqueue | Worker chưa đọc được attachment | Worker/artifact lifecycle quản lý cleanup |
| Xóa file sau lần thử đầu dù còn retry | Retry thiếu attachment | Giữ file tới terminal state |
| Cleanup exception ghi đè lỗi SMTP | Mất nguyên nhân chính, retry sai | Ghi cleanup failure riêng, giữ nguyên kết quả send |
| Dùng cùng file temp cho nhiều worker | Một worker xóa khi worker khác còn đọc | Mỗi job/attempt có artifact riêng hoặc reference counting rõ |
| Janitor xóa mọi file cũ trong temp hệ thống | Xóa file của ứng dụng khác hoặc job hợp lệ | Dùng thư mục riêng, prefix, TTL và kiểm tra job state |
| Log đường dẫn/nội dung nhạy cảm | Rò rỉ thông tin | Dùng ID opaque và log trạng thái tối thiểu |
| Coi delete là secure erase | Dữ liệu có thể còn trong snapshot/SSD | Encryption at rest và retention |
| Dùng ByteArrayResource cho file rất lớn | Áp lực heap, GC và OOM | Dùng file/resource/stream có vòng đời phù hợp |

## 18. Quy trình vận hành cleanup cho mail service

Một module gửi mail có attachment có thể thống nhất quy trình:

1. **Tạo artifact:** sinh file bằng tên ngẫu nhiên trong thư mục riêng hoặc storage bền vững.
2. **Ghi nhận ownership:** gắn ID job/attachment và xác định thành phần chịu trách nhiệm xóa.
3. **Dựng MIME:** truyền resource và tên hiển thị; không tự xóa khi helper mới khai báo attachment.
4. **Thực hiện gửi:** giữ resource còn đọc được trong toàn bộ lần gửi đồng bộ.
5. **Phân loại kết quả:** nộp thư thành công, lỗi retryable, lỗi vĩnh viễn hoặc trạng thái không xác định.
6. **Quyết định retention:** nếu retry còn khả năng, giữ artifact; nếu job terminal, lên lịch cleanup.
7. **Cleanup:** xóa file/artifact do service sở hữu; ghi nhận lỗi xóa riêng.
8. **Janitor:** dọn file mồ côi sau TTL có kiểm tra quyền sở hữu và trạng thái job.
9. **Giám sát:** theo dõi số file, dung lượng, tuổi file, cleanup failures và job tồn đọng.

### 18.1. Các metric hữu ích

| Metric | Ý nghĩa |
| --- | --- |
| `mail_temp_files_created_total` | Tổng số file tạm đã tạo |
| `mail_temp_files_deleted_total` | Tổng số file đã xóa thành công |
| `mail_temp_cleanup_failures_total` | Số lần cleanup thất bại |
| `mail_temp_storage_bytes` | Dung lượng hiện dùng trong thư mục mail temp |
| `mail_temp_oldest_file_age_seconds` | Tuổi của file cũ nhất còn tồn tại |
| `mail_attachment_size_bytes` | Kích thước attachment theo phân phối |
| `mail_jobs_waiting_for_retry` | Số job còn cần artifact để thử lại |

Metric nên dùng ID hoặc nhãn có cardinality được kiểm soát; không đưa địa chỉ email, tên file tùy ý hoặc job ID duy nhất thành label Prometheus vì có thể tạo cardinality quá lớn.

## 19. Tình huống tổng hợp: hóa đơn gửi đồng bộ và gửi qua queue

### 19.1. Gửi đồng bộ trong một request/job

Nếu service tạo file, gọi `JavaMailSender.send` ngay và không retry sau khi method kết thúc:

~~~text
Create temp PDF
    -> Build MimeMessage
    -> sender.send(...)
    -> finally delete temp PDF
~~~

Đây là trường hợp phù hợp với `try/finally` ở phần 4. File chỉ tồn tại trong vòng đời của lời gọi service.

### 19.2. Gửi bất đồng bộ có retry

Nếu người dùng tạo đơn hàng và worker sẽ gửi email sau:

~~~text
Order transaction
    -> Create immutable mail job
    -> Store attachment artifact durably
    -> Enqueue job with artifact key/version

Worker attempt 1
    -> Read artifact
    -> Build MIME
    -> SMTP temporary failure
    -> Keep artifact; schedule retry

Worker attempt 2
    -> Read same artifact version
    -> SMTP submission succeeds
    -> Mark job SUBMITTED
    -> Cleanup artifact when retention policy permits
~~~

Trong mô hình này, `finally` của lần thử thứ nhất có thể chỉ đóng stream/resource của **attempt**, không được xóa artifact dùng chung cho retry. Việc xóa artifact thuộc về job lifecycle sau khi trạng thái đã terminal và các consumer không còn tham chiếu tới nó.

Nếu có nhiều job dùng chung một artifact, cần quản lý tham chiếu hoặc sao chép artifact theo job. Không xóa khi một consumer hoàn tất nếu consumer khác còn cần.

## 20. Những điều cần nhớ

- File tạm chỉ được xóa bởi **thành phần sở hữu nó**.
- Với gửi đồng bộ, giữ file đến khi `send(...)` kết thúc; đặt cleanup trong `finally`.
- Dọn cả nhánh thành công và thất bại, kể cả khi lỗi xảy ra trong lúc ghi file.
- Không để cleanup exception che lỗi gửi; tách trạng thái send và cleanup.
- Không xóa artifact khi queue/job vẫn còn khả năng retry.
- Không truyền đường dẫn local cho worker chạy ở máy khác; dùng storage bền vững với key/version.
- Janitor chỉ dọn file thuộc ứng dụng, trong thư mục riêng, theo TTL và trạng thái job.
- `Files.deleteIfExists` không phải cơ chế secure erase.
- Dùng bytes trong memory cho file nhỏ; dùng resource/file/storage phù hợp cho attachment lớn.

Với Spring Framework Mail, một vòng đời attachment đáng tin cậy không chỉ dừng ở `addAttachment(...)`. Ứng dụng phải kiểm soát từ lúc tạo file, cung cấp resource cho MIME, hoàn tất thao tác gửi, xử lý retry và cuối cùng xóa dữ liệu theo chính sách. Khi **ownership, thời điểm cleanup và trạng thái job** được xác định rõ, hệ thống tránh được file rác, giảm nguy cơ lộ dữ liệu và không vô tình xóa mất attachment mà worker vẫn cần.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper` và attachment resources.
- **Spring Framework API — `FileSystemResource` / `ByteArrayResource`:** cung cấp dữ liệu attachment.
- **Java API — `Files.createTempFile`, `Files.deleteIfExists`, `Files.copy`:** tạo, ghi, sao chép và xóa file.
- **Java Language/API — try/finally và try-with-resources:** quản lý tài nguyên và exception khi đóng.
- **Jakarta Mail API:** `MimeMessage`, `MimeBodyPart`, `DataHandler` và quá trình serialize MIME.
- **Spring Framework — Task Execution and Scheduling:** xử lý công việc bất đồng bộ và tác vụ dọn dẹp định kỳ.
