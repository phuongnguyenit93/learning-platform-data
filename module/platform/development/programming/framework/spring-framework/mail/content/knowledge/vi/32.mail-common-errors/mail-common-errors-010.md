# Đóng InputStream trước khi sender đọc xong

Trong **Spring Framework Mail**, một lỗi dễ bỏ sót là **đóng `InputStream` chứa attachment hoặc ảnh inline ngay sau khi tạo `MimeMessage`, trước khi `JavaMailSender` thực sự đọc dữ liệu**. Ứng dụng có thể tạo message không gặp lỗi, nhưng đến lúc gửi mới xuất hiện `IOException`, `MessagingException`, `MailSendException` hoặc attachment bị rỗng, thiếu, không đọc được. Lỗi này thường xuất hiện khi dùng `try-with-resources` không đúng phạm vi, truyền `InputStreamResource` vào `MimeMessageHelper`, chuyển việc gửi sang `@Async`, hoặc tạo message từ tệp tạm rồi xóa tệp trước khi transport sử dụng.

Điểm cần nhớ: **Xây dựng cấu trúc MIME không nhất thiết đồng nghĩa đã đọc toàn bộ nội dung các phần MIME**. Jakarta Mail có thể đọc dữ liệu khi message được serialize, encode hoặc submit cho SMTP transport. Một số nguồn dữ liệu có thể bị gọi lấy stream **nhiều lần**. Vì vậy, chỉ thấy `helper.addAttachment(...)` chạy thành công chưa chứng minh attachment còn đọc được ở lúc gửi.

Bài học này phân tích nguyên nhân, mô hình ownership của stream, những kiểu `Resource` nên và không nên dùng, ảnh hưởng của `@Async` và retry, cách chọn `ByteArrayResource` hoặc `FileSystemResource`, cách xây nguồn dữ liệu mở stream mới mỗi lần, ví dụ Java/Spring hoàn chỉnh, phương pháp kiểm thử và checklist khắc phục trong production.

## 1. Lỗi điển hình: addAttachment thành công, send mới lỗi

Giả sử người dùng tải lên một tệp PDF để ứng dụng gửi bằng email. Lập trình viên mở stream, đưa nó vào helper và đóng ngay sau khi cấu hình message:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.InputStreamResource;
import org.springframework.mail.javamail.MimeMessageHelper;

public void prepareAttachment(
        MimeMessageHelper helper,
        Path pdfPath
) throws Exception {

    try (InputStream input =
                 Files.newInputStream(pdfPath)) {

        // SAI: InputStreamResource giữ một stream có sẵn.
        helper.addAttachment(
                "invoice.pdf",
                new InputStreamResource(input),
                "application/pdf"
        );
    } // input đã bị đóng tại đây.

    // SMTP chưa chắc đã đọc attachment.
}
```

Sau đó:

```java
mailSender.send(mimeMessage);
```

Khi transport cần đọc attachment, nguồn không còn hợp lệ. Tùy cách dựng MIME và thời điểm đọc, lỗi có thể là:

- `java.io.IOException: Stream closed`.
- `jakarta.mail.MessagingException` có nguyên nhân là lỗi đọc stream.
- `org.springframework.mail.MailSendException` bọc nguyên nhân từ Jakarta Mail.
- Lỗi đọc attachment phát sinh trong task nền chứ không xuất hiện ở HTTP request.
- Message đã được gửi nhưng một phần đính kèm không đúng, nếu mã nguồn custom xử lý lỗi sai hoặc thay bằng dữ liệu rỗng.

Không nên dựa vào một thông điệp exception cụ thể: chúng thay đổi theo JDK, provider Jakarta Mail, nguồn lưu trữ và giai đoạn thực thi.

**Lỗi gốc là sai về vòng đời tài nguyên**, không phải thiếu `flush()` hoặc cần thêm `Thread.sleep(...)`.

## 2. Chuỗi thời gian thực tế của một email MIME

Một vòng đời điển hình:

```text
T1: Open InputStream for attachment
            |
            v
T2: Create MimeMessage
            |
            v
T3: MimeMessageHelper.addAttachment(...)
            |
            v
T4: Close InputStream  <--- lỗi nếu stream vẫn cần được đọc
            |
            v
T5: mailSender.send(message)
            |
            v
T6: Jakarta Mail serializes MIME parts
            |
            v
T7: DataHandler / DataSource requests attachment bytes
            |
            v
T8: SMTP transport writes encoded content
```

Với một số nguồn, nội dung có thể được đọc ở giai đoạn khác T7, thậm chí đọc hơn một lần để xây header/transfer encoding hoặc để serialize lại. Không coi sơ đồ trên là thứ tự chi tiết bắt buộc của mọi JavaMail implementation. Điều quan trọng là **có thể tồn tại khoảng cách giữa lúc gắn nguồn dữ liệu và lúc nội dung được tiêu thụ**.

Nếu stream đã đóng hoặc tệp tạm đã bị xóa trong khoảng đó, message không còn khả năng tái đọc đáng tin cậy.

### Hai điều kiện phải đúng

Để attachment hoạt động ổn định:

1. **Dữ liệu còn tồn tại và được phép truy cập** cho đến khi quá trình gửi cần nó kết thúc.
2. **Nguồn MIME cho phép mở stream mới khi thư viện yêu cầu**, trừ khi API cụ thể có hợp đồng khác đã được xác minh.

Chỉ giữ stream mở lâu hơn giải quyết được một phần điều kiện thứ nhất; nó **không giải quyết việc cùng một stream có thể đã bị đọc tới cuối hoặc yêu cầu đọc lại**.

## 3. InputStreamSource được dùng để làm gì?

Trong Spring Core, `InputStreamSource` mô tả một đối tượng có khả năng cung cấp `InputStream`:

```java
import java.io.IOException;
import java.io.InputStream;

public interface InputStreamSource {
    InputStream getInputStream() throws IOException;
}
```

Ý tưởng không phải “đưa cho thư viện một stream đã mở”, mà là **đưa một nguồn có thể cung cấp stream** khi cần.

Với `MimeMessageHelper.addAttachment(...)` và `addInline(...)`, nguồn dữ liệu có thể được Jakarta Mail lấy lại nhiều lần. Một implementation phù hợp phải trả **stream mới, có thể đọc từ đầu**, mỗi khi `getInputStream()` được gọi.

```text
InputStreamSource.getInputStream() -> stream A, position 0
InputStreamSource.getInputStream() -> stream B, position 0
InputStreamSource.getInputStream() -> stream C, position 0
```

Không nên trả lại cùng một object `InputStream` đang ở cuối stream hoặc đã đóng.

### Vì sao helper không đọc tất cả bytes ngay?

Đọc tất cả attachment khi gọi `addAttachment` sẽ tiêu tốn bộ nhớ và thời gian; với file lớn hoặc nguồn từ storage, deferred reading có thể hợp lý. Jakarta Mail tổ chức MIME thông qua `DataHandler`/`DataSource`; phần dữ liệu có thể được lấy ở thời điểm serialize hoặc transport.

Đây là lý do một lời gọi helper “không ném exception” chưa đủ để khẳng định phần đính kèm hợp lệ.

## 4. InputStream và InputStreamSource khác nhau

| Kiểu | Ý nghĩa | Rủi ro khi dùng cho MIME |
|---|---|---|
| `InputStream` | Một phiên đọc đang mở, có vị trí hiện tại | Có thể đóng hoặc bị đọc tới EOF |
| `InputStreamSource` | Nhà cung cấp các phiên đọc | Phải hiện thực trả stream mới khi cần |
| `InputStreamResource` | Bọc một `InputStream` đã mở | Thường là single-use, không phù hợp làm nguồn attachment cần đọc nhiều lần |
| `ByteArrayResource` | Bọc bytes trong bộ nhớ, mỗi lần đọc có stream mới | Ổn định với payload nhỏ/vừa nhưng tăng heap |
| `FileSystemResource` | Bọc đường dẫn/tệp để mở stream mới khi cần | Tệp phải còn tồn tại, không bị đổi trong quá trình gửi |
| `DataSource` của Jakarta Activation | Cung cấp dữ liệu MIME, content type/name | `getInputStream()` cũng phải có lifecycle đúng |

Một sai lầm phổ biến là suy luận:

> “`InputStreamResource` implements `InputStreamSource`, vậy dùng được ở mọi nơi yêu cầu `InputStreamSource`.”

Về kiểu Java, nó có thể được truyền vào. Nhưng **hợp đồng sử dụng MIME cần nguồn có thể đọc lại**, còn `InputStreamResource` đại diện cho một stream đã được mở và có tính single-use. Khớp interface không đồng nghĩa khớp yêu cầu vòng đời.

## 5. Ví dụ đầy đủ về cách làm sai

```java
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.InputStreamResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class BrokenAttachmentMailer {

    private final JavaMailSender mailSender;

    public BrokenAttachmentMailer(
            JavaMailSender mailSender
    ) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            Path invoicePath
    ) throws Exception {

        MimeMessage message =
                mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        message,
                        true,
                        "UTF-8"
                );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn");
        helper.setText("Hóa đơn được đính kèm.");

        try (InputStream input =
                     Files.newInputStream(invoicePath)) {

            helper.addAttachment(
                    "invoice.pdf",
                    new InputStreamResource(input),
                    "application/pdf"
            );
        }

        // Stream đã đóng. Jakarta Mail có thể đọc sau.
        mailSender.send(message);
    }
}
```

Điểm lỗi không chỉ nằm ở `try-with-resources`. Dù chuyển `mailSender.send(message)` vào bên trong khối `try`, `InputStreamResource` vẫn có thể không đáp ứng yêu cầu đọc lại nhiều lần.

Thêm mã `input.mark(0)` hoặc `input.reset()` cũng không phải giải pháp tổng quát: không phải stream nào cũng hỗ trợ mark/reset, dữ liệu có thể quá lớn, và cùng một stream không tương đương các phiên đọc độc lập.

## 6. Cách sửa 1: ByteArrayResource cho attachment nhỏ, có giới hạn

Với attachment có kích thước nhỏ và được giới hạn rõ, có thể đọc bytes vào bộ nhớ **trước khi đóng stream**, sau đó dùng `ByteArrayResource`:

```java
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendSmallInvoice(
        JavaMailSender sender,
        Path invoicePath,
        String recipient
) throws Exception {

    // Chỉ dùng khi đã kiểm soát kích thước file.
    byte[] attachment = Files.readAllBytes(invoicePath);

    MimeMessage message = sender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(
                    message,
                    true,
                    "UTF-8"
            );

    helper.setFrom("billing@example.org");
    helper.setTo(recipient);
    helper.setSubject("Hóa đơn");
    helper.setText("Xem tệp đính kèm.");

    helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(attachment),
            "application/pdf"
    );

    sender.send(message);
}
```

Tại sao cách này hoạt động?

- `ByteArrayResource` giữ mảng bytes độc lập với stream đã đóng.
- Mỗi lần thư viện gọi `getInputStream()`, resource có thể tạo `ByteArrayInputStream` mới bắt đầu từ đầu mảng.
- Không còn phụ thuộc file handle đã đóng trong `try`.
- Nội dung attachment ổn định trong suốt send, miễn ứng dụng không sửa mảng byte gốc.

### Giới hạn quan trọng: bộ nhớ

`Files.readAllBytes(...)` không phù hợp mặc định với file lớn hoặc file không tin cậy. Ví dụ 50 job song song, mỗi job giữ attachment 20 MB, có thể tiêu tốn khoảng 1 GB chỉ riêng attachment bytes trước khi tính MIME encoding và các object khác.

Dùng cách này khi:

- Có **maximum attachment size** rõ.
- Input đã được xác thực/quét theo policy.
- Heap và concurrency đủ.
- Không đẩy hàng trăm attachment bytes vào queue RAM.

Với file lớn, nên dùng nguồn có thể **mở stream mới từ storage khi cần** thay vì giữ toàn bộ trong heap.

## 7. Bounded read thay cho readAllBytes với dữ liệu không tin cậy

Nếu kích thước file do người dùng upload không được tin cậy, kiểm tra metadata size thôi chưa đủ. File có thể thay đổi hoặc nguồn stream có thể cung cấp nhiều hơn dự kiến.

Ví dụ hàm đọc có giới hạn:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

public final class LimitedBytes {

    public static byte[] readAtMost(
            InputStream input,
            long maxBytes
    ) throws IOException {

        if (maxBytes < 0L) {
            throw new IllegalArgumentException(
                    "maxBytes must be nonnegative"
            );
        }

        ByteArrayOutputStream output =
                new ByteArrayOutputStream();

        byte[] buffer = new byte[8192];
        long total = 0L;
        int read;

        while ((read = input.read(buffer)) != -1) {
            total += read;

            if (total > maxBytes) {
                throw new IOException(
                        "Attachment exceeds allowed size"
                );
            }

            output.write(buffer, 0, read);
        }

        return output.toByteArray();
    }
}
```

Cách sử dụng:

```java
byte[] bytes;

try (InputStream input = storage.openInput(ref)) {
    bytes = LimitedBytes.readAtMost(
            input,
            2L * 1024 * 1024
    );
}

// InputStream đã đóng nhưng bytes vẫn còn.
ByteArrayResource resource =
        new ByteArrayResource(bytes);

helper.addAttachment(
        "report.pdf",
        resource,
        "application/pdf"
);

sender.send(message);
```

`storage.openInput` là abstraction do ứng dụng định nghĩa. Trong production cần xử lý riêng empty stream, timeouts, malicious uploads và MIME size sau encoding.

Hàm `readAtMost` giảm nguy cơ đọc vô hạn; nó **không** tự kiểm tra malware, quyền truy cập hay giới hạn dung lượng SMTP sau base64 encoding.

## 8. Cách sửa 2: FileSystemResource cho file có vòng đời ổn định

Nếu attachment đã được lưu thành một file tại đường dẫn ổn định, có thể dùng `FileSystemResource`:

```java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;

Path reportPath =
        Path.of("/app/mail-attachments/report-2026.pdf");

FileSystemResource resource =
        new FileSystemResource(reportPath);

helper.addAttachment(
        "report.pdf",
        resource,
        "application/pdf"
);

mailSender.send(message);
```

`FileSystemResource` có thể mở một stream mới mỗi lần được yêu cầu. Không cần tự mở và giữ một `InputStream` ngay khi thêm attachment.

Tuy nhiên, dữ liệu phải còn tồn tại **cho đến khi Jakarta Mail đọc xong**. Không được xóa, đổi tên hoặc ghi đè tệp quá sớm.

### Chỉ an toàn khi nào?

- File đã được lưu hoàn chỉnh trước khi gửi.
- Worker có quyền đọc file.
- File không bị cleanup trước khi send kết thúc.
- Không có producer khác ghi đè cùng path.
- Nếu gửi bất đồng bộ, file tồn tại trên worker thực thi chứ không chỉ trên HTTP server.
- Khi retry, phiên bản attachment còn truy cập được theo retention.

Một path local trong Pod A **không tự tồn tại trong Pod B**. Với queue hoặc nhiều replicas, dùng object storage hoặc shared storage có policy phù hợp; tránh truyền absolute path tạm qua broker rồi mong worker khác mở được.

## 9. Sai lầm với file tạm và cleanup quá sớm

Ví dụ:

```java
Path temporaryPdf =
        Files.createTempFile("invoice-", ".pdf");

try {
    generatePdf(temporaryPdf);

    MimeMessage message =
            buildMessageWithFile(temporaryPdf);

    // Gửi bất đồng bộ: chỉ nộp task cho executor.
    mailExecutor.execute(
            () -> mailSender.send(message)
    );
} finally {
    Files.deleteIfExists(temporaryPdf);
}
```

Đây là race:

```text
HTTP thread                        Mail worker
    |                                  |
    +-- create temp file               |
    +-- schedule send ---------------->|
    +-- delete temp file               |
    |                             starts later
    |                             opens attachment
    |                                  X file missing
```

Nếu OS cho phép unlink file đang mở, hành vi cũng khác theo platform và thời điểm stream được mở. Không dựa vào hành vi khóa file cụ thể của Windows/Linux để bảo đảm correctness.

### Hướng sửa

- Chuyển attachment sang **storage bền vững** trước khi enqueue.
- Queue chỉ chứa `attachmentId`, `storageKey`, `version`.
- Worker mở nguồn dữ liệu khi thực sự gửi.
- Cleanup dựa trên retention và trạng thái job, không dựa trên việc HTTP method đã trả về.
- Với file tạm thật sự chỉ dùng trong một send đồng bộ, cleanup sau khi lời gọi `send` hoàn tất và không còn đường đọc lại nào.

## 10. Cách sửa 3: InputStreamSource trả stream mới mỗi lần

Khi nguồn dữ liệu nằm ở storage hoặc cần stream từ path, dùng một factory:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.InputStreamSource;

Path path = Path.of("/data/reports/statement.pdf");

InputStreamSource source = new InputStreamSource() {
    @Override
    public InputStream getInputStream()
            throws IOException {
        return Files.newInputStream(path);
    }
};

helper.addAttachment(
        "statement.pdf",
        source,
        "application/pdf"
);

mailSender.send(message);
```

Điểm mấu chốt: mỗi lần `getInputStream()` được gọi, `Files.newInputStream(path)` tạo **một stream mới**.

Có thể viết ngắn bằng lambda:

```java
InputStreamSource source =
        () -> Files.newInputStream(path);

helper.addAttachment(
        "statement.pdf",
        source,
        "application/pdf"
);
```

Đây không phải lời khuyên giữ file handle mở mãi. Nhà cung cấp MIME mở stream **khi cần** và implementation đọc chịu trách nhiệm đóng stream theo hợp đồng thực tế. Ứng dụng không nên chủ động đóng một stream chưa được dùng xong.

### Factory vẫn cần bảo đảm dữ liệu ổn định

Nếu mỗi lần mở path lại đọc một phiên bản khác, MIME có thể không nhất quán giữa các lần đọc. Với retry hoặc nhiều worker, nên chọn **immutable/versioned object** thay vì path có thể bị overwrite.

## 11. Một factory dành cho object storage

Khi attachment được lưu ở S3-compatible storage, blob store, database large object hoặc một abstraction khác, xây nguồn có thể mở stream mới:

```java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.InputStreamSource;

public final class StoredAttachmentSource
        implements InputStreamSource {

    private final AttachmentStore store;
    private final String objectKey;
    private final String version;

    public StoredAttachmentSource(
            AttachmentStore store,
            String objectKey,
            String version
    ) {
        this.store = store;
        this.objectKey = objectKey;
        this.version = version;
    }

    @Override
    public InputStream getInputStream()
            throws IOException {

        return store.openReadStream(
                objectKey,
                version
        );
    }
}

public interface AttachmentStore {

    InputStream openReadStream(
            String objectKey,
            String version
    ) throws IOException;
}
```

`AttachmentStore` là interface ứng dụng định nghĩa. Nếu dùng object storage SDK có exception riêng, adapter có thể chuyển chúng sang `IOException` theo chính sách hoặc xây `DataSource` custom phù hợp.

Ví dụ:

```java
InputStreamSource source =
        new StoredAttachmentSource(
                attachmentStore,
                attachment.objectKey(),
                attachment.version()
        );

helper.addAttachment(
        attachment.safeFilename(),
        source,
        attachment.contentType()
);

mailSender.send(message);
```

### Cần xác nhận contract của storage

- Mỗi `openReadStream` trả stream mới từ byte đầu.
- Object version không thay đổi trong khi gửi.
- Worker có quyền đọc object.
- Token truy cập không hết hạn trước khi worker chạy.
- Có read timeout, size limit và cleanup.
- Không cho object key từ client tự do vượt tenant boundaries.
- Stream lỗi giữa chừng được propagate thay vì im lặng trả EOF.

Một source có thể mở mới nhưng **không giữ dữ liệu ổn định** vẫn có rủi ro khi Jakarta Mail đọc lại.

## 12. InputStreamResource là bẫy phổ biến

`InputStreamResource` của Spring thường bọc **một stream đã được mở**:

```java
InputStream input = Files.newInputStream(path);

InputStreamResource resource =
        new InputStreamResource(input);
```

Nó hữu ích khi một API cần xử lý **single-use stream** trong một lần đọc rõ ràng. Nhưng attachment/inline MIME cần nguồn dữ liệu có thể được lấy lại nhiều lần.

Vì vậy:

| Cách dùng | Đánh giá |
|---|---|
| `new InputStreamResource(input)` rồi `addAttachment` | Không nên |
| `new ByteArrayResource(bytes)` rồi `addAttachment` | Thường phù hợp nếu bytes nhỏ/được giới hạn |
| `new FileSystemResource(path)` rồi `addAttachment` | Phù hợp nếu file tồn tại và bất biến đủ lâu |
| `InputStreamSource` mở stream mới mỗi lần | Phù hợp khi storage hỗ trợ |
| `InputStreamSource` trả cùng input ở mọi lần | Không phù hợp |
| Tạo custom `DataSource` đọc lại được | Phù hợp khi cần điều khiển MIME/content type |

Nếu đang gặp `Stream closed` và thấy `InputStreamResource` trong đường tạo attachment, đó là điểm cần kiểm tra đầu tiên.

## 13. Đừng chỉ di chuyển try-with-resources xuống dưới send

Một cách sửa thường được đề xuất:

```java
try (InputStream input = Files.newInputStream(path)) {
    helper.addAttachment(
            "report.pdf",
            new InputStreamResource(input),
            "application/pdf"
    );

    mailSender.send(message);
}
```

So với đóng trước `send`, cách này có thể tránh stream bị đóng quá sớm trong một trường hợp. Nhưng nó **vẫn không đáp ứng hợp đồng cần mở stream mới khi Jakarta Mail yêu cầu đọc nhiều lần**.

Nếu stream bị đọc từ đầu tới cuối ở lượt thứ nhất, lượt tiếp theo có thể nhận EOF, dù stream chưa đóng.

**Cách sửa đúng trọng tâm là cung cấp nguồn tái đọc được**, không chỉ kéo dài một scope `try`.

## 14. Khi nào try-with-resources thực sự đúng?

`try-with-resources` hoàn toàn đúng nếu ứng dụng **tự đọc hết dữ liệu vào một representation độc lập** rồi mới đóng stream:

```java
byte[] bytes;

try (InputStream input = storage.openReadStream(ref)) {
    bytes = LimitedBytes.readAtMost(input, maxBytes);
}

// Sau đây hoàn toàn không còn phụ thuộc input.
InputStreamSource repeatable =
        new ByteArrayResource(bytes);
```

Hoặc ứng dụng thực hiện một thao tác **đồng bộ và đã hoàn thành tiêu thụ stream bên trong scope**, theo hợp đồng rõ của API nhận stream. Không áp dụng suy luận đó một cách máy móc cho Jakarta Mail MIME source.

### Ai có trách nhiệm đóng stream?

Khi API yêu cầu một `InputStreamSource`/`DataSource`, đối tượng tiêu thụ sẽ gọi `getInputStream()` và thường chịu trách nhiệm đóng các stream do nó mở theo đường đọc của implementation. Ứng dụng cung cấp source phải bảo đảm mỗi stream mới có lifecycle hợp lệ và không chủ động đóng trước khi consumer kết thúc.

Nếu tự viết `DataSource`, wrapper hoặc mã MIME thấp cấp, cần xác định và kiểm thử ownership cụ thể; không giả định mọi framework và mọi API đều tự đóng tất cả stream trong mọi tình huống.

## 15. addInline cũng gặp cùng lỗi

Không chỉ attachment. Ảnh inline sử dụng `Content-ID` cũng có thể được đọc muộn:

```html
<html>
  <body>
    <p>Xin chào!</p>
    <img src="cid:brand-logo" alt="Logo"/>
  </body>
</html>
```

Code nên dùng nguồn repeatable:

```java
MimeMessage message =
        mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Thông báo");

helper.setText(
        "Xin chào!",
        "<p>Xin chào!</p>"
      + "<img src=\"cid:brand-logo\" alt=\"Logo\"/>"
);

helper.addInline(
        "brand-logo",
        new FileSystemResource(
                Path.of("/app/assets/logo.png")
        ),
        "image/png"
);

mailSender.send(message);
```

Đặt `setText(...)` trước `addInline(...)` là thứ tự an toàn được khuyến nghị khi xây cấu trúc MIME liên quan trong `MimeMessageHelper`. File logo phải còn tồn tại tới khi gửi xong, và với distributed workers phải là tài nguyên worker truy cập được.

Nếu ảnh inline được đọc từ stream rồi đóng, lỗi tương tự attachment có thể xảy ra nhưng biểu hiện ở mail client có thể là ảnh bị thiếu hoặc MIME serialization thất bại.

## 16. Attachment stream trong @Async: rủi ro lớn hơn

Một code pattern nguy hiểm:

```java
public void handleUpload(MultipartFile upload) {
    try (InputStream input = upload.getInputStream()) {

        mailAsyncService.sendLater(
                new InputStreamResource(input)
        );

    } catch (IOException ex) {
        throw new IllegalStateException(ex);
    }
}
```

Nếu `sendLater` sử dụng `@Async`:

```java
@Async("mailExecutor")
public void sendLater(
        InputStreamSource attachment
) {
    MimeMessage message =
            buildMessage(attachment);

    mailSender.send(message);
}
```

Caller đóng stream khi scope kết thúc, trong khi async task có thể chưa chạy. Đây là lỗi **resource lifetime vượt khỏi request lifetime**.

Một biến thể khác: `MultipartFile`/`Part` dựa trên tệp tạm trong HTTP request. Khi request hoàn tất, servlet container có thể cleanup resource tạm. Worker chạy sau sẽ không còn nguồn.

### Quy tắc rõ ràng

**Không truyền `InputStream`, `InputStreamResource`, servlet `Part` hoặc request-scoped upload resource trực tiếp qua ranh giới async/queue.**

Thay vào đó:

1. Tiếp nhận upload.
2. Kiểm tra quyền, size/content policy.
3. Lưu dữ liệu ở storage có retention phù hợp.
4. Commit attachment reference/notification job.
5. Đưa **ID/reference** vào worker.
6. Worker mở nguồn dữ liệu từ storage trong lúc thực thi.

## 17. Thiết kế producer–worker an toàn hơn

Một command nhẹ:

```java
public record MailJob(
        String notificationId,
        String recipientRef,
        String templateKey,
        String attachmentId,
        String attachmentVersion
) {
}
```

Tại request handler:

```java
public MailReceipt requestMail(
        MultipartFile upload,
        MailRequest request
) throws IOException {

    StoredAttachment stored =
            attachmentStorage.saveValidated(
                    upload,
                    request.tenantRef()
            );

    MailJob job = new MailJob(
            ids.newNotificationId(),
            request.recipientRef(),
            "invoice-ready",
            stored.id(),
            stored.version()
    );

    outboxRepository.insertPending(job);

    return new MailReceipt(
            job.notificationId(),
            "QUEUED"
    );
}
```

`MailReceipt`, `MailRequest`, `StoredAttachment`, `attachmentStorage` và `outboxRepository` là thành phần minh họa. Trong production cần xác định commit và transaction boundary giữa storage/object và database, xử lý orphan object hoặc job chưa có file, và chỉ trả trạng thái `QUEUED` khi thỏa hợp đồng bền vững.

Worker:

```java
public void processJob(String notificationId) {

    MailJob job = outboxRepository.claim(notificationId);

    StoredAttachment attachment =
            attachmentStorage.findAuthorized(
                    job.attachmentId(),
                    job.attachmentVersion()
            );

    MimeMessage message = mailSender.createMimeMessage();

    // Build helper, subject, body, recipient...

    InputStreamSource source = () ->
            attachmentStorage.openReadStream(
                    attachment.id(),
                    attachment.version()
            );

    helper.addAttachment(
            attachment.safeFilename(),
            source,
            attachment.contentType()
    );

    mailSender.send(message);
}
```

Đây là pseudocode Java ở mức kiến trúc: các biến `helper` và các service phải được khởi tạo/tiêm đầy đủ trong code thực tế, đồng thời catch exception và finalize attempt outcome. Ý chính là **worker xây MIME bằng nguồn đọc còn hiệu lực ở thời điểm gửi**, chứ không nhận object stream đã mở ở HTTP thread.

## 18. Resource truyền qua queue không chỉ sai về kỹ thuật mà còn sai về dữ liệu

Một `InputStream` không phải một payload message bền vững:

- Không serialize được một phiên đọc đang mở thành queue record có nghĩa.
- Có thể phụ thuộc file descriptor của một process.
- Có thể phụ thuộc token hết hạn.
- Có thể chỉ đọc được một lần.
- Sau restart worker không thể tái tạo vị trí đọc.
- Với nhiều replicas, worker khác không sở hữu kết nối/file handle.
- Không có version kiểm soát trường hợp attachment bị thay đổi.

Một hàng đợi bền vững nên chứa:

```json
{
  "notificationId": "notif-421",
  "attachmentRef": "attachment-918",
  "attachmentVersion": "v3",
  "recipientRef": "recipient-31",
  "templateKey": "invoice-ready"
}
```

Không chứa raw attachment bytes trừ khi có lý do thiết kế rõ, kích thước đã giới hạn và broker thực sự cho phép. Tránh đưa presigned URL sống ngắn vào queue dài hạn; nên lưu object key/version và lấy credential hợp lệ khi worker chạy.

## 19. Đọc nhiều lần là yêu cầu thật của MIME

Một nguồn được cài sai:

```java
InputStream opened = Files.newInputStream(path);

InputStreamSource broken = () -> opened;
```

Mọi lời gọi `getInputStream()` trả cùng object.

Tình huống:

```text
First getInputStream():
  reads bytes 0..N, reaches EOF

Second getInputStream():
  same stream already at EOF
  returns no bytes, or throws if closed
```

Nguồn đúng:

```java
InputStreamSource repeatable =
        () -> Files.newInputStream(path);
```

Từng lần trả stream riêng:

```text
read #1 -> new stream, bytes 0..N
read #2 -> new stream, bytes 0..N
read #3 -> new stream, bytes 0..N
```

**Chủ đích là dữ liệu repeatable**, không phải bảo đảm thư viện sẽ luôn gọi chính xác hai lần. Số lần đọc có thể thay đổi theo version, MIME structure và thao tác serialize.

## 20. ByteArrayDataSource và custom DataSource

Ngoài `InputStreamSource`, Jakarta Mail/Activation có `DataSource` để cung cấp MIME content. Một implementation phải xử lý tên, content type và input streams.

Ví dụ `ByteArrayDataSource` (từ Jakarta Mail implementation) có thể phù hợp khi dữ liệu đã ở trong memory:

```java
import jakarta.mail.util.ByteArrayDataSource;

byte[] pdfBytes = generateSmallPdf();

ByteArrayDataSource dataSource =
        new ByteArrayDataSource(
                pdfBytes,
                "application/pdf"
        );
```

Nếu code MIME thấp cấp dùng `DataHandler`:

```java
import jakarta.activation.DataHandler;
import jakarta.mail.internet.MimeBodyPart;

MimeBodyPart part = new MimeBodyPart();
part.setDataHandler(new DataHandler(dataSource));
part.setFileName("invoice.pdf");
```

Với `MimeMessageHelper`, thường nên dùng overload `addAttachment` hơn là dựng MIME structure trực tiếp, trừ khi có yêu cầu đặc biệt.

### Custom DataSource phải trả dữ liệu repeatable

Một `DataSource` custom mà `getInputStream()` luôn trả cùng stream single-use có thể gây đúng lỗi đang bàn. Dù chọn API nào, hợp đồng nguồn dữ liệu phải phù hợp với cách Jakarta Mail tiêu thụ.

Cần dùng đúng namespace phiên bản thư viện: dự án Spring hiện đại thường sử dụng `jakarta.mail.*` và `jakarta.activation.*`; code cũ có thể dùng `javax.mail.*`. Không trộn hai namespace tùy tiện trong cùng ví dụ.

## 21. setContent/saveChanges không bảo đảm bytes đã được đọc hết

Một sai lầm khác:

```java
helper.addAttachment("report.pdf", source);
message.saveChanges();

// Nghĩ rằng sau saveChanges có thể xóa file là không an toàn.
Files.delete(path);

mailSender.send(message);
```

`MimeMessage.saveChanges()` có nhiệm vụ chuẩn bị/update các header cần thiết như `Message-ID`/MIME state theo implementation; nó **không phải cam kết mọi attachment đã được eager-loaded thành bytes nằm hoàn toàn trong message object**.

Tương tự:

- `createMimeMessage()` không đọc file.
- `addAttachment(...)` không chứng minh file đã được serialize.
- `setContent(...)` không bảo đảm đã tải toàn bộ attachment từ storage.
- `saveChanges()` không chuyển mọi nguồn lazy thành snapshot bất biến.

Để xác minh dữ liệu có thể đọc, cần thực sự serialize MIME hoặc gửi qua test transport — và vẫn phải giữ nguồn hợp lệ tới khi real send hoàn tất.

## 22. Test bằng JavaMailSender mock có thể bỏ sót lỗi

Ví dụ:

```java
verify(mailSender).send(any(MimeMessage.class));
```

Test này chỉ chứng minh service gọi `send`. Mockito mock không tự serialize MIME và cũng không đọc attachment stream.

Vì vậy một testcase vẫn có thể xanh dù:

- Stream đã đóng.
- File tạm bị xóa.
- `InputStreamSource` trả cùng stream một lần.
- Attachment là byte rỗng.
- MIME content type sai.
- Ảnh inline có CID không khớp.

**Muốn kiểm tra lifecycle của attachment, test phải kích hoạt quá trình đọc thực sự**, không chỉ verify Java method invocation.

## 23. Test InputStreamSource có thể đọc lại

Ví dụ đơn giản cho factory:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.InputStreamSource;

@Test
void attachmentSourceIsRepeatable() throws Exception {
    Path path = tempDir.resolve("sample.pdf");

    byte[] expected = new byte[] {
            0x25, 0x50, 0x44, 0x46
    };

    Files.write(path, expected);

    InputStreamSource source =
            () -> Files.newInputStream(path);

    byte[] first;
    byte[] second;

    try (InputStream a = source.getInputStream()) {
        first = a.readAllBytes();
    }

    try (InputStream b = source.getInputStream()) {
        second = b.readAllBytes();
    }

    assertThat(first).isEqualTo(expected);
    assertThat(second).isEqualTo(expected);
}
```

`tempDir` là `@TempDir` của JUnit 5 được khai báo ở test class, ví dụ:

```java
@org.junit.jupiter.api.io.TempDir
Path tempDir;
```

Test này xác nhận factory trả dữ liệu lại được; chưa xác nhận cấu trúc MIME và SMTP transport.

### Test trường hợp nguồn single-use

Một fixture có thể cố ý trả cùng `InputStream` sau khi đóng. Kỳ vọng là lần đọc tiếp theo ném exception hoặc không trả dữ liệu như trước. Mục tiêu là chứng minh vì sao `InputStreamResource` không phải lựa chọn đúng, không cần phụ thuộc vào một thông điệp exception cụ thể.

## 24. Test MIME serialization thật, không gửi email ra Internet

Một cách tốt là dựng `MimeMessage` rồi gọi `writeTo(...)` để buộc Jakarta Mail serialize nội dung:

```java
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayOutputStream;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

@Test
void serializesAttachmentAfterSourceIsBuilt()
        throws Exception {

    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    MimeMessage message = sender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(
                    message,
                    true,
                    "UTF-8"
            );

    helper.setFrom("sender@example.org");
    helper.setTo("recipient@example.net");
    helper.setSubject("Test attachment");
    helper.setText("See attachment");

    byte[] expected = {
            1, 2, 3, 4, 5
    };

    helper.addAttachment(
            "bytes.bin",
            new ByteArrayResource(expected),
            "application/octet-stream"
    );

    message.saveChanges();

    ByteArrayOutputStream output =
            new ByteArrayOutputStream();

    message.writeTo(output);

    assertThat(output.toByteArray())
            .isNotEmpty();
}
```

Đây là ví dụ test với JUnit 5 + AssertJ; cần imports `@Test`/`assertThat` phù hợp. Test khẳng định MIME serialize được; muốn chứng minh attachment bytes đúng thì nên parse message kết quả và duyệt MIME tree để so sánh **decoded attachment bytes**, không so sánh raw MIME text vì nó có base64 encoding, boundaries và header thay đổi.

### Vì sao serialize hai lần hữu ích?

Khi source được thiết kế repeatable, có thể serialize cùng message hai lần vào hai `ByteArrayOutputStream` khác nhau và xác nhận cả hai có attachment bytes đúng. Điều đó giúp phát hiện source trả stream single-use.

Không yêu cầu bytes của toàn bộ MIME output phải giống hệt nhau nếu các header/boundaries/timestamps có thể thay đổi; kiểm tra phần attachment đã decode.

## 25. Duyệt MIME tree để kiểm tra attachment

Attachment có thể nằm trong cây `multipart/mixed` hoặc các multipart lồng nhau. Không nên giả định “attachment luôn ở bodyPart index 1”.

Ví dụ helper trích attachment theo filename:

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

public final class MimeAttachmentReader {

    public static List<byte[]> findByFilename(
            Part part,
            String filename
    ) throws Exception {

        List<byte[]> found = new ArrayList<>();
        visit(part, filename, found);
        return found;
    }

    private static void visit(
            Part part,
            String filename,
            List<byte[]> found
    ) throws Exception {

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int index = 0;
                    index < multipart.getCount();
                    index++) {

                visit(
                        multipart.getBodyPart(index),
                        filename,
                        found
                );
            }
            return;
        }

        if (filename.equals(part.getFileName())) {
            try (InputStream in = part.getInputStream()) {
                found.add(in.readAllBytes());
            }
        }
    }
}
```

Test có thể sử dụng:

```java
MimeMessage parsed = new MimeMessage(
        jakarta.mail.Session.getInstance(
                new java.util.Properties()
        ),
        new java.io.ByteArrayInputStream(
                output.toByteArray()
        )
);

List<byte[]> attachments =
        MimeAttachmentReader.findByFilename(
                parsed,
                "bytes.bin"
        );

assertThat(attachments).hasSize(1);
assertThat(attachments.get(0))
        .isEqualTo(expected);
```

Code minh họa kiểm tra một file name cố định. Trong ứng dụng thật, cần chú ý MIME nesting, filenames encoded, limits và trường hợp part không phải attachment nhưng cũng có filename.

## 26. Integration test với SMTP test server

`MimeMessage.writeTo(...)` kiểm tra serialization, nhưng một đường gửi thực tế còn có:

- Kết nối SMTP.
- TLS/AUTH tùy cấu hình.
- Transport serialization ở runtime.
- Exception mapping qua `JavaMailSenderImpl`.
- Worker scheduling/retry.

Có thể dùng **GreenMail**, **Mailpit**, hoặc một SMTP test server được cô lập để nhận thư test, không relay ra Internet.

Kịch bản:

1. Dựng MIME với attachment/inline resources.
2. Gọi `mailSender.send(message)` vào SMTP test server.
3. Nhận message tại server test.
4. Parse MIME và assert file name, content type, decoded bytes, CID.
5. Xác nhận sender/recipient/subject.
6. Thử trường hợp stream đóng sớm và resource repeatable.
7. Thử gửi nhiều lần/retry nếu policy cho phép.

Test không cần credential production hoặc recipient thật. Dùng data test giả, giới hạn kích thước và cleanup resource sau test.

### Lỗi thường bị che bởi mocks

Một Mockito test `verify(send(...))` sẽ không kích hoạt việc đọc attachment. SMTP test server hoặc `MimeMessage.writeTo` mới giúp phát hiện lifecycle vấn đề ở boundary tương ứng.

## 27. Test @Async để tái hiện race

Một test tốt không dựa vào `Thread.sleep(100)` rồi hy vọng worker chậm hơn caller. Dùng `CountDownLatch` để điều khiển thứ tự:

```text
HTTP/request thread:
  open stream
  submit async task
  close stream
  signal worker

Worker:
  wait on latch
  build/serialize MIME
  observe stream closed or missing temp file
```

Sau đó sửa implementation thành **persist attachment rồi truyền attachment reference**, kiểm tra worker vẫn đọc được dữ liệu sau khi request scope đã kết thúc.

Các assertion:

- Với cách sai, attachment stream không còn hợp lệ.
- Với cách đúng, worker mở stream mới và đọc đủ bytes.
- Không có request-scoped `InputStream` trong job payload.
- Retry mở lại được attachment.
- Cleanup chỉ xóa file/object sau retention/deadline.
- Nếu worker crash, job không mất vì object storage còn attachment.

## 28. Retry phải dựng lại message hoặc bảo đảm source repeatable

Một thông báo có thể retry do lỗi SMTP tạm thời. Nếu giữ một `MimeMessage` từ attempt đầu với các nguồn single-use rồi tái sử dụng, lần retry có thể không còn đọc được attachment.

Ví dụ đáng ngại:

```java
MimeMessage message = buildOnceUsingStream();

try {
    sender.send(message);
} catch (MailException firstError) {
    // Không nên retry mù bằng cùng message/single-use streams.
    sender.send(message);
}
```

Vấn đề không chỉ là `InputStream`. Nếu SMTP đã nhận message nhưng response bị mất, retry ngay cũng có thể gây **gửi trùng**. Cần phân loại outcome:

| Outcome | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `SMTP_ACCEPTED` | Transport xác nhận accepted | Không retry chỉ vì chưa có delivery webhook |
| `KNOWN_REJECTED` | Provider từ chối rõ ràng | Retry tùy loại lỗi |
| `UNKNOWN` | Không biết chắc đã accepted | Reconcile hoặc retry có kiểm soát |
| `EXPIRED` | Notification hết giá trị | Không gửi |

Một worker đáng tin cậy thường:

1. Claim notification ID.
2. Tạo attempt ID mới.
3. Load template và attachment references từ storage bền vững.
4. **Dựng MimeMessage mới cho attempt**, với repeatable sources.
5. Gửi trong timeout/quota.
6. Persist accepted/rejected/unknown.
7. Hẹn retry có backoff khi được phép.

Giữ dữ liệu nguồn ổn định qua nhiều attempts quan trọng hơn giữ một object `MimeMessage` trong memory.

## 29. Attachment source phải tồn tại bao lâu?

Có thể nghĩ đến bốn mốc:

```text
REQUEST ACCEPTED
      |
      v
JOB QUEUED
      |
      v
ATTEMPT STARTED
      |
      v
SMTP SUBMISSION FINISHED
      |
      v
JOB FINALIZED / RETRY WINDOW ENDS
```

Nếu chỉ cần gửi đồng bộ một lần, nguồn phải còn đọc được cho tới khi `send` hoàn tất.

Nếu có queue/retry, dữ liệu phải tồn tại ít nhất cho tới khi:

- Thư đã được accepted và không cần xây lại MIME, hoặc
- Job được hủy/expire/fail final và retention cho phép cleanup.

Nếu cần điều tra/đối soát nội dung theo nghĩa vụ, có thể giữ lâu hơn trong storage có policy riêng. Không mặc định lưu tất cả attachment vô thời hạn.

**Không gắn vòng đời attachment với vòng đời HTTP request** nếu job được xử lý bất đồng bộ.

## 30. Dọn file tạm đúng cách trong send đồng bộ

Nếu có một file tạm chỉ dùng cho một send đồng bộ, có thể tổ chức cleanup sau khi `send` kết thúc:

```java
Path temp = Files.createTempFile(
        "mail-report-",
        ".pdf"
);

try {
    renderReportTo(temp);

    MimeMessage message =
            buildWithFileSystemResource(temp);

    mailSender.send(message);

} finally {
    Files.deleteIfExists(temp);
}
```

`buildWithFileSystemResource` là helper do ứng dụng định nghĩa; nó phải dùng nguồn mở được stream mới từ file và dựng message hợp lệ.

Cách này chỉ phù hợp khi:

- `send` thực sự đồng bộ và đã kết thúc mọi lần đọc MIME cần thiết trước khi trả về.
- Không còn worker nền giữ message.
- Không có retry deferred dùng lại path.
- Không có provider callback cần truy cập attachment.
- Cleanup failure được xử lý/quan sát phù hợp.

Nếu nguồn được lưu vào queue để gửi sau, **không** xóa file trong `finally` của producer như vậy.

## 31. Có nên dùng FileSystemResource cho file do người dùng tải lên?

Có thể, nhưng cần thêm lớp bảo vệ:

- Lưu file ở thư mục kiểm soát, không dùng tên file client làm path trực tiếp.
- Kiểm tra authorization theo tenant và notification.
- Giới hạn size và loại file.
- Scan nội dung theo chính sách.
- Đảm bảo file đã ghi xong và immutable trước khi queue job.
- Hạn chế quyền process và cleanup có retention.
- Không log absolute path chứa dữ liệu nhạy cảm.
- Nếu worker trên node khác, bảo đảm storage có thể truy cập bằng object key/version.
- Không cho symbolic link/path traversal dẫn worker tới file ngoài vùng cho phép.
- Theo dõi disk quota và số file chờ.

`FileSystemResource` giải quyết câu chuyện **mở stream mới**, không tự giải quyết security hoặc data lifecycle.

## 32. File name, Content-Type và dữ liệu MIME

Một attachment đúng bytes vẫn có thể không sử dụng được nếu metadata sai.

Nên kiểm tra:

- `attachmentFilename` là tên hiển thị đã sanitize, không phải path đầy đủ.
- `contentType` được xác định theo policy, không tin tuyệt đối input client.
- PDF là `application/pdf` nếu được xác minh đúng.
- Inline image có `Content-ID` khớp `cid:...` trong HTML.
- Charset text/HTML được cấu hình (ví dụ UTF-8).
- MIME tree phù hợp, có thể dùng `MULTIPART_MODE_MIXED_RELATED` khi có attachment và inline resources.
- Attachment bytes không rỗng nếu domain không cho phép file rỗng.

Ví dụ:

```java
helper.setText(
        "Bản text thay thế.",
        "<p>Xem file đính kèm.</p>"
);

helper.addAttachment(
        "hoa-don.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Tên file Unicode cần được kiểm thử ở phiên bản JavaMail/Spring và các mail client mục tiêu nếu khả năng tương thích là yêu cầu nghiệp vụ.

## 33. Có cần đóng mọi InputStream do ứng dụng mở?

Có, với stream **ứng dụng trực tiếp mở và tiêu thụ**:

```java
try (InputStream input = Files.newInputStream(path)) {
    byte[] bytes = LimitedBytes.readAtMost(
            input, maxBytes
    );
    // Process bytes.
}
```

Nhưng khi ứng dụng cung cấp **factory** cho thư viện mở stream về sau:

```java
InputStreamSource source =
        () -> Files.newInputStream(path);
```

không có một stream nào được mở tại thời điểm tạo factory để ứng dụng đóng ngay. Consumer sẽ mở phiên đọc thông qua API và xử lý lifecycle của các stream được trả về theo implementation cụ thể.

**Không viết mã “dọn hết tất cả stream trước khi return”** nếu chính những stream đó được thư viện cần đọc sau return.

## 34. MIME data may be read more than once: vì sao điều này quan trọng?

Một hệ thống có thể:

- `saveChanges()` để cập nhật headers.
- Serialize MIME ra một byte stream.
- Log/test bằng cách viết MIME vào output.
- Submit MIME qua SMTP.
- Retry attempt bằng cùng source.
- Tạo bản preview/testing từ content.

Những thao tác này có thể tạo thêm lần đọc. Nếu source chỉ hỗ trợ một lần, lần sau lỗi dù lần đầu thành công.

Do đó yêu cầu đáng nhớ không phải “đừng đóng stream trong 2 giây”, mà là:

> **Đối với attachment/inline của MimeMessageHelper, hãy cung cấp nguồn dữ liệu có thể tạo một InputStream mới, đọc từ đầu, cho mỗi lần được yêu cầu.**

Mỗi stream riêng có thể đóng sau khi consumer hoàn tất; nguồn dữ liệu gốc cần sống đủ lâu.

## 35. Không dùng available() để kiểm tra attachment còn dữ liệu

Một lỗi chẩn đoán:

```java
if (input.available() == 0) {
    throw new IllegalStateException("Empty file");
}
```

`InputStream.available()` biểu thị ước lượng số byte có thể đọc không bị block trong thời điểm đó, **không phải tổng kích thước file**. Giá trị 0 không có nghĩa hết dữ liệu, và giá trị dương không chứng minh stream còn nguyên vẹn.

Để xác minh:

- Đọc dữ liệu với giới hạn size.
- Kiểm tra byte count thực tế.
- Với nguồn repeatable, mở một stream mới khi cần.
- Test MIME serialization/decoded attachment.
- Không phụ thuộc `available()` hay `markSupported()` cho correctness.

## 36. Error mapping: Stream closed không phải SMTP rejected

Một lỗi đọc attachment có thể xảy ra **trước khi request SMTP hoàn tất**, đôi khi trước cả khi MIME bytes gửi xong. Cần phân biệt:

| Nhóm | Ví dụ | Cách hiểu |
|---|---|---|
| Source data failure | File not found, stream closed, object expired | Không thể dựng/đọc attachment đúng |
| MIME serialization failure | Invalid MIME part, encoding/content handler failure | Message chưa được serialize thành công |
| SMTP transport failure | AUTH/TLS/connect timeout | Kết nối hoặc authentication không thành công |
| SMTP provider rejection | Invalid recipient, policy, throttling | Provider trả kết quả từ chối |
| Unknown submission | Connection lost at ambiguous stage | Chưa biết chắc provider đã nhận hay chưa |

Không map tất cả thành `MAIL_SEND_FAILED` rồi retry vô hạn cùng object stream hỏng.

Nếu source file đã bị xóa vĩnh viễn, retry không tạo lại dữ liệu. Worker cần đưa job tới trạng thái cần sửa dữ liệu hoặc final failure theo policy, thay vì thử mỗi giây.

## 37. Observability: log đủ nhưng không lộ attachment

Những field hữu ích:

```text
notificationId = notif-421
attemptId = attempt-421-02
attachmentRef = att-918
attachmentVersion = v3
sourceType = OBJECT_STORAGE
errorCategory = ATTACHMENT_STREAM_CLOSED
stage = MIME_SERIALIZATION
providerRoute = transactional-primary
```

Không log:

- Nội dung attachment.
- File name nhạy cảm nếu có chứa tên người.
- Absolute path với dữ liệu định danh.
- S3/bucket credentials hoặc presigned URLs.
- Body/OTP/token.
- Raw SMTP AUTH.

Một log an toàn:

```java
log.warn(
        "Mail attachment read failed: "
      + "notificationId={}, attemptId={}, "
      + "attachmentRef={}, stage={}, category={}",
        notificationId,
        attemptId,
        attachmentRef,
        "MIME_SERIALIZATION",
        "SOURCE_UNAVAILABLE"
);
```

Nếu cần stack trace, lưu ở diagnostic log có quyền và retention ngắn. Không đưa nguyên `IOException.getMessage()` vào metric labels hoặc audit vì path và metadata có thể nhạy cảm.

## 38. Metrics nhận diện vấn đề stream và attachment

Các metric minh họa:

| Metric | Ý nghĩa |
|---|---|
| `mail_attachment_open_total` | Lần mở stream từ attachment storage |
| `mail_attachment_open_failure_total` | Mở nguồn thất bại |
| `mail_attachment_read_failure_total` | Đọc stream thất bại |
| `mail_attachment_bytes_read_total` | Tổng bytes thực đọc |
| `mail_mime_serialization_failure_total` | Không thể serialize MIME |
| `mail_send_attempt_total` | SMTP attempts bắt đầu |
| `mail_send_accepted_total` | SMTP accepted |
| `mail_outbox_pending` | Jobs chưa xử lý |
| `mail_outbox_oldest_age_seconds` | Tuổi pending lâu nhất |

Các tên chỉ là đề xuất; không phải toàn bộ metric có sẵn mặc định trong Spring Mail.

Tags có thể dùng `sourceType`, `stage`, `errorCategory` với tập giá trị hữu hạn. Không dùng `attachmentId`, tên file, path hoặc recipient email làm metric tags do cardinality và privacy.

### Tín hiệu chẩn đoán

```text
mail_mime_serialization_failure_total rises
mail_attachment_read_failure_total rises
smtp accepted rate drops
  -> inspect InputStreamSource/resource lifecycle

mail_attachment_open_failure_total rises
  -> storage availability/credentials/retention

mail_outbox_pending grows, attachment errors stable
  -> worker/SMTP throughput/backpressure may be bottleneck
```

## 39. Runbook: Stream closed trong production

### Bước 1 — Khoanh vùng attachment/inline

Kiểm tra exception có liên quan tới `getInputStream`, `DataHandler`, `DataSource`, `MimeMessageHelper.addAttachment` hoặc `addInline` không.

### Bước 2 — Xác định nguồn dữ liệu

- `ByteArrayResource`?
- `InputStreamResource`?
- `FileSystemResource`?
- Custom `InputStreamSource`?
- Object storage `DataSource`?
- Request-scoped `MultipartFile`?

Nếu thấy `InputStreamResource` hoặc factory trả cùng stream, xem xét sửa trước.

### Bước 3 — Xác định thời điểm đóng/xóa

Tìm `try-with-resources`, `finally`, temp file cleanup, upload request completion, object storage retention và cancellation.

### Bước 4 — Xác định ranh giới bất đồng bộ

HTTP request → `@Async`, queue, outbox, scheduled job hoặc worker khác replica. Đối tượng truyền qua ranh giới có phải open stream hoặc path local không?

### Bước 5 — Kiểm tra repeatability

Gọi `getInputStream()` nhiều lần trên test source, đọc bytes và so sánh nội dung. Test `MimeMessage.writeTo` hoặc gửi qua SMTP test server.

### Bước 6 — Sửa theo kích thước và storage

- File nhỏ/giới hạn: `ByteArrayResource`.
- File local ổn định: `FileSystemResource`.
- Object storage/queue: lưu reference và dùng factory tạo stream mới.
- Retry: dựng MIME mới từ dữ liệu bền vững.

### Bước 7 — Phân loại hậu quả đã xảy ra

Không tự resend hàng loạt nếu một số attempts có outcome UNKNOWN. Kiểm tra state/attempts, xác định source failure xảy ra trước hay sau SMTP acceptance khi có bằng chứng, và dùng retry policy có kiểm soát.

### Bước 8 — Theo dõi sau khắc phục

Xác nhận attachment read failures giảm, MIME serialization thành công, SMTP accepted rate phục hồi, queue age giảm và không tăng duplicate messages.

## 40. Các anti-pattern khác

| Anti-pattern | Hậu quả | Thay thế |
|---|---|---|
| `new InputStreamResource(openStream)` cho attachment | Single-use, có thể đóng sớm/EOF | `ByteArrayResource` hoặc source mở mới |
| Đóng stream ngay sau `addAttachment` | Sender đọc muộn thì lỗi | Repeatable source, lifecycle đúng |
| Chỉ chuyển `send` vào trong `try` | Vẫn có thể không đọc lại được | Mỗi `getInputStream` trả stream mới |
| Dùng `InputStreamSource () -> sameStream` | Đọc lần hai EOF | Factory mở nguồn mới |
| Xóa temp file sau enqueue | Worker không tìm thấy file | Storage bền vững và retention |
| Truyền `MultipartFile` qua `@Async` | Request temp resource hết hạn | Persist upload, truyền attachment ID |
| Đưa absolute local path vào broker | Worker khác replica không thấy file | Object key/version |
| Đọc file lớn bằng `readAllBytes` | OOM/high heap | Streaming source và size policy |
| Resource đọc khác phiên bản mỗi lần | MIME không nhất quán | Immutable/versioned object |
| Dùng `saveChanges` rồi xóa file | Content có thể vẫn lazy | Giữ dữ liệu tới send/retry lifecycle |
| Mockito `verify(send)` là test duy nhất | Không đọc attachment | MIME serialization/test SMTP server |
| Retry bằng cùng message single-use | EOF hoặc duplicate gửi | Rebuild per attempt, classify outcome |
| Dùng `available()==0` để biết file rỗng | Kết luận sai | Đọc thực/byte count |
| Log đầy đủ MIME trên lỗi | Rò rỉ PII/OTP/attachment | Structured metadata và redaction |
| Không có timeout/storage retention | Stream treo hoặc object bị xóa | Bounds, retention, monitoring |

## 41. Checklist triển khai

1. Đã xác định ai mở, ai đọc và ai đóng từng `InputStream`.
2. Không dùng `InputStreamResource` single-use làm nguồn MIME attachment/inline.
3. `InputStreamSource.getInputStream()` trả stream mới từ đầu mỗi lần.
4. Nội dung nguồn không bị thay đổi giữa các lần mở trong một attempt.
5. Tệp/object còn tồn tại đến khi submit hoàn tất và trong retry window.
6. Không truyền open stream qua `@Async`, queue hoặc process boundary.
7. Job gửi chứa attachment ID/object key/version, không giữ file handle.
8. Worker mới là nơi load nguồn và dựng MIME cho từng attempt.
9. File nhỏ dùng `ByteArrayResource` chỉ sau khi giới hạn kích thước.
10. File lớn dùng repeatable streaming source và kiểm soát concurrency.
11. Attachment size được kiểm tra khi ingest và khi đọc.
12. Filename/content type được sanitize/validate.
13. Inline CID khớp phần HTML.
14. File local không bị cleanup trước khi `send` xong.
15. Nếu nhiều replicas, storage worker truy cập được.
16. Credential/URL của object storage không bị log/đưa vào queue lâu dài.
17. Dữ liệu retry được bảo toàn; attempt mới dựng message mới.
18. Phân biệt source error, MIME error, SMTP reject và UNKNOWN.
19. Unit test mở nguồn hai lần, so sánh bytes.
20. Test serialize bằng `MimeMessage.writeTo` và inspect MIME tree.
21. Integration test với SMTP test server, không gửi production.
22. Async test tái hiện request cleanup và worker delay.
23. Có metric/alert cho attachment open/read/serialize failures.
24. Có runbook phân loại gửi lại tránh duplicate.
25. Giữ dữ liệu trong storage đúng retention, không vô thời hạn.

## 42. Ghi nhớ

- `MimeMessageHelper.addAttachment(...)` không nhất thiết đọc hết attachment ngay khi được gọi.
- Jakarta Mail có thể lấy stream lúc serialize/gửi và có thể yêu cầu đọc nhiều lần.
- `InputStreamResource` bọc một stream có sẵn và không phải nguồn repeatable phù hợp cho MIME attachment.
- **`InputStreamSource` dùng với MIME nên trả một `InputStream` mới từ đầu ở mỗi lần gọi**.
- `ByteArrayResource` thích hợp với payload nhỏ có giới hạn; dữ liệu không còn phụ thuộc stream ban đầu.
- `FileSystemResource` có thể mở mới stream, nhưng file phải còn tồn tại và ổn định.
- Với object storage, dùng source factory mở stream mới theo object key/version.
- `try-with-resources` không sai; sai là đóng tài nguyên khi consumer vẫn cần hoặc dùng single-use resource ở API cần đọc lại.
- `@Async` và queue làm rủi ro lớn hơn vì producer có thể đóng request stream trước khi worker chạy.
- Không truyền `MultipartFile`, open stream, temp file handle qua hàng đợi bền vững.
- `saveChanges()` không bảo đảm đã snapshot toàn bộ MIME attachment.
- Mock `JavaMailSender.send` đơn thuần không kiểm tra việc đọc bytes; cần `writeTo` hoặc SMTP test server.
- Khi retry, dựng message từ nguồn dữ liệu bền vững thay vì dùng lại stream single-use.
- `Stream closed` là lỗi nguồn/MIME, không tự động là SMTP provider rejection.
- Không retry mù nếu submission outcome có thể là UNKNOWN.
- Giữ log đủ điều tra nhưng không ghi raw attachment, presigned URL hoặc secret.

**Kết luận:** Lỗi **đóng `InputStream` trước khi sender đọc xong** xuất phát từ việc nhầm “đã gắn attachment vào `MimeMessage`” với “dữ liệu attachment đã được tiêu thụ”. Trong Spring Framework Mail, hãy cung cấp **nguồn dữ liệu tái đọc được**, giữ nguồn tồn tại đúng vòng đời gửi/retry và truyền **reference bền vững** thay vì open stream qua các ranh giới bất đồng bộ. Với các nguyên tắc đó, attachment và ảnh inline vẫn được gửi ổn định khi Jakarta Mail đọc muộn, đọc lại, worker chạy ở replica khác hoặc hệ thống cần khôi phục sau lỗi.
