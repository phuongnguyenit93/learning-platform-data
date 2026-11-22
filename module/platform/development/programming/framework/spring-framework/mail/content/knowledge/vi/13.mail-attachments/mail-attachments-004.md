# Đính kèm dữ liệu sinh trong bộ nhớ

Trong **Spring Framework Mail**, email có thể đính kèm nội dung được tạo ngay trong lúc xử lý nghiệp vụ: báo cáo PDF, bảng CSV, hóa đơn, file JSON, ảnh biểu đồ hoặc gói ZIP. Không phải lúc nào dữ liệu đó cũng cần được ghi thành file trên ổ đĩa. Ứng dụng có thể sinh nội dung vào **mảng byte (`byte[]`) hoặc bộ đệm trong bộ nhớ**, rồi đưa dữ liệu trực tiếp vào email qua `MimeMessageHelper`.

Cách này hữu ích khi báo cáo được tạo riêng cho từng người nhận, dữ liệu chỉ cần tồn tại trong thời gian gửi, hoặc ứng dụng chạy trong container không có thư mục tạm phù hợp. Tuy nhiên, đính kèm trong bộ nhớ đòi hỏi chú ý đến **khả năng đọc lại stream, kiểu MIME, tên file, kích thước dữ liệu và lượng RAM**. Email được gửi thành công vẫn có thể mang file rỗng hoặc sai định dạng nếu bước tạo dữ liệu và bước đóng gói không được thiết kế đúng.

Bài học trình bày cách tạo attachment từ byte array, `ByteArrayOutputStream`, `ByteArrayResource` và `InputStreamSource`, cách dùng trong Spring Mail, cách kiểm soát dung lượng và bảo mật, cùng các ví dụ CSV/PDF và kiểm tra nội dung MIME.

## 1. Dữ liệu sinh trong bộ nhớ là gì?

Thông thường, quy trình đính kèm file có thể gồm:

```text
Dữ liệu nghiệp vụ
       |
       v
Bộ tạo báo cáo / exporter
       |
       v
ByteArrayOutputStream hoặc byte[]
       |
       v
ByteArrayResource / InputStreamSource
       |
       v
MimeMessageHelper.addAttachment(...)
       |
       v
JavaMailSender.send(...)
       |
       v
SMTP server
```

**Dữ liệu sinh trong bộ nhớ** nghĩa là ứng dụng tạo nội dung file ở RAM và cung cấp các byte đó trực tiếp cho thư viện email. Không cần tạo một đường dẫn như `/tmp/report.pdf` trước khi đính kèm.

Ví dụ:
- Sinh CSV từ danh sách giao dịch rồi gửi cho người quản lý.
- Tạo PDF hóa đơn từ dữ liệu đơn hàng và gửi sau khi thanh toán.
- Xuất JSON hoặc XML làm dữ liệu trao đổi với hệ thống khác.
- Vẽ biểu đồ thành PNG rồi đính kèm vào báo cáo định kỳ.
- Nén một số tài liệu thành ZIP để gửi một lần.

Dữ liệu file vẫn được biểu diễn dưới dạng byte trong bộ nhớ. Khi gửi email, Jakarta Mail đọc dữ liệu, tạo MIME part và mã hóa phù hợp để truyền qua SMTP.

## 2. Các API Spring Mail cần biết

### 2.1. JavaMailSender và MimeMessage

`JavaMailSender` tạo và gửi một `MimeMessage`. Để gửi attachment, cần dùng MIME message thay vì `SimpleMailMessage`:

```java
MimeMessage message = mailSender.createMimeMessage();
```

`SimpleMailMessage` dành cho email text đơn giản. Nó không cung cấp cấu trúc MIME multipart cần thiết để mang file đính kèm.

### 2.2. MimeMessageHelper

`MimeMessageHelper` là tiện ích Spring giúp đặt header và xây dựng các phần MIME. Constructor thường dùng:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");
```

Tham số:
- `message`: email được tạo từ `JavaMailSender`.
- `true`: bật chế độ multipart, cho phép có body và attachment.
- `"UTF-8"`: encoding cho nội dung văn bản phù hợp.

Sau khi tạo helper, có thể gọi `setFrom`, `setTo`, `setSubject`, `setText` và `addAttachment`.

### 2.3. ByteArrayResource

`ByteArrayResource` là Spring Resource bao bọc một mảng byte:

```java
byte[] fileBytes = ...;
ByteArrayResource resource = new ByteArrayResource(fileBytes);
```

Điểm hữu ích là mỗi lần gọi `getInputStream()`, resource có thể tạo một `ByteArrayInputStream` mới từ cùng mảng byte. Đây là đặc tính **đọc lại được (repeatable)**, phù hợp với quá trình chuẩn bị và truyền MIME có thể cần đọc dữ liệu từ nguồn.

Khi dùng `MimeMessageHelper.addAttachment(...)`, truyền tên file và kiểu MIME rõ ràng:

```java
helper.addAttachment(
    "bao-cao.csv",
    new ByteArrayResource(fileBytes),
    "text/csv; charset=UTF-8"
);
```

Tên file được truyền riêng vì `ByteArrayResource` không nhất thiết cung cấp filename có ý nghĩa.

### 2.4. InputStreamSource

`InputStreamSource` là abstraction Spring để cung cấp một `InputStream`:

```java
import java.io.ByteArrayInputStream;
import org.springframework.core.io.InputStreamSource;

InputStreamSource source =
    () -> new ByteArrayInputStream(fileBytes);
```

Điều quan trọng: **mỗi lần `getInputStream()` được gọi, nguồn nên trả về một stream mới có thể đọc từ đầu**. Đừng giữ một stream đã đọc hết rồi trả lại cùng đối tượng mỗi lần. Nếu thư viện cần đọc dữ liệu lần nữa, stream cũ sẽ ở cuối hoặc đã đóng.

`ByteArrayResource` đã triển khai `InputStreamSource`, nên với dữ liệu byte có sẵn thường không cần tự viết lớp nguồn.

## 3. Quy trình tạo và đính kèm dữ liệu trong bộ nhớ

Các bước khuyến nghị:

1. Lấy dữ liệu nghiệp vụ và kiểm tra quyền người nhận.
2. Sinh file thành byte array hoặc nguồn dữ liệu có thể mở stream mới.
3. Xác nhận dữ liệu không rỗng và kích thước nằm trong giới hạn.
4. Tạo `MimeMessage` và `MimeMessageHelper` ở chế độ multipart.
5. Thiết lập người gửi, người nhận, subject và nội dung thư.
6. Gọi `addAttachment(filename, resource, contentType)`.
7. Gửi qua `JavaMailSender`.
8. Ghi nhận kết quả gửi và mã nghiệp vụ, không ghi nội dung file nhạy cảm vào log.

```text
generate bytes
     |
     v
validate size / non-empty / format
     |
     v
create MimeMessage + multipart helper
     |
     v
set headers and body
     |
     v
addAttachment(...)
     |
     v
send(...)
```

Tách bước tạo dữ liệu khỏi bước gửi giúp dễ kiểm tra file trước khi đóng gói và dễ xử lý lỗi theo từng giai đoạn.

## 4. Ví dụ cơ bản: đính kèm byte[] có sẵn

Ví dụ khi một thành phần khác đã tạo ra dữ liệu file:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class AttachmentMailService {

    private final JavaMailSender mailSender;

    public AttachmentMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendFile(
            String recipient,
            byte[] fileBytes) throws MessagingException {

        if (fileBytes == null || fileBytes.length == 0) {
            throw new IllegalArgumentException(
                "Dữ liệu file không được rỗng"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Tệp báo cáo");
        helper.setText(
            "Chào bạn,\nTệp báo cáo được đính kèm trong email này."
        );

        helper.addAttachment(
            "bao-cao.pdf",
            new ByteArrayResource(fileBytes),
            "application/pdf"
        );

        mailSender.send(message);
    }
}
```

Giải thích:
- `fileBytes` chứa byte của file đã tạo.
- Kiểm tra `null` và độ dài để không gửi attachment rỗng ngoài ý muốn.
- `new MimeMessageHelper(message, true, "UTF-8")` bật multipart.
- `addAttachment` nhận tên hiển thị, nguồn byte và content type.
- `application/pdf` mô tả nội dung PDF; phần mở rộng filename nên khớp định dạng thật.
- `mailSender.send(message)` gửi MIME message qua SMTP đã cấu hình.

Ví dụ giả định `fileBytes` thực sự là PDF hợp lệ. Đổi content type thành `application/pdf` không biến dữ liệu bất kỳ thành PDF; **định dạng phải được tạo đúng trước khi đính kèm**.

## 5. Sinh CSV trong bộ nhớ rồi gửi

CSV thường phù hợp với báo cáo giao dịch hoặc dữ liệu cần mở bằng spreadsheet. Có thể dựng nội dung bằng `StringBuilder`, chuyển thành UTF-8 byte array rồi dùng `ByteArrayResource`.

### 5.1. Tạo CSV

Ví dụ một dòng dữ liệu:

```java
public record OrderRow(
    String orderCode,
    String customerName,
    long quantity,
    String amount
) {}
```

Hàm escape CSV cơ bản bao mỗi trường trong dấu ngoặc kép và nhân đôi dấu ngoặc kép nằm bên trong:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;

public class CsvExporter {

    public byte[] export(List<OrderRow> rows) {
        StringBuilder csv = new StringBuilder();
        csv.append("Order,Customer,Quantity,Amount\n");

        for (OrderRow row : rows) {
            csv.append(csvCell(row.orderCode())).append(',');
            csv.append(csvCell(row.customerName())).append(',');
            csv.append(csvCell(Long.toString(row.quantity()))).append(',');
            csv.append(csvCell(row.amount())).append('\n');
        }

        return csv.toString().getBytes(StandardCharsets.UTF_8);
    }

    private static String csvCell(String value) {
        String safe = value == null ? "" : value;
        return "\"" + safe.replace("\"", "\"\"") + "\"";
    }
}
```

Đây là cách escape cấu trúc CSV cho dữ liệu text thông thường. Với dữ liệu có thể được mở bằng Excel hoặc spreadsheet tương tự, cần xem thêm **CSV formula injection**: giá trị do người dùng kiểm soát bắt đầu bằng `=`, `+`, `-` hoặc `@` có thể bị spreadsheet diễn giải như công thức. Nếu xuất dữ liệu không tin cậy, cần chính sách xử lý riêng cho ô text; đồng thời không làm sai các cột số hợp lệ. CSV quoting theo chuẩn dấu phẩy/quote không tự ngăn spreadsheet thực thi công thức.

Với CSV cho người dùng Việt Nam, hãy kiểm tra encoding và cách ứng dụng spreadsheet nhận diện UTF-8. Có thể cần BOM UTF-8 tùy phần mềm đích, nhưng không thêm BOM máy móc nếu hệ thống downstream yêu cầu byte đầu là ký tự đầu tiên của header.

### 5.2. Gửi CSV

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.List;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderReportMailService {

    private final JavaMailSender mailSender;
    private final CsvExporter csvExporter;

    public OrderReportMailService(
            JavaMailSender mailSender,
            CsvExporter csvExporter) {
        this.mailSender = mailSender;
        this.csvExporter = csvExporter;
    }

    public void sendReport(
            String recipient,
            List<OrderRow> rows) throws MessagingException {

        byte[] csvBytes = csvExporter.export(rows);

        if (csvBytes.length == 0) {
            throw new IllegalStateException("CSV được tạo rỗng");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo đơn hàng");
        helper.setText(
            "Báo cáo đơn hàng được đính kèm dưới dạng CSV."
        );

        helper.addAttachment(
            "order-report.csv",
            new ByteArrayResource(csvBytes),
            "text/csv; charset=UTF-8"
        );

        mailSender.send(message);
    }
}
```

CSV được tạo hoàn toàn trong RAM. Không cần ghi `order-report.csv` ra thư mục tạm để sau đó đọc lại. Tuy vậy, nếu báo cáo có hàng triệu dòng, tạo cả chuỗi CSV và byte array có thể tiêu thụ nhiều bộ nhớ; xem phần giới hạn kích thước.

## 6. Sinh PDF bằng ByteArrayOutputStream

Nhiều thư viện tạo PDF có API ghi ra `OutputStream`. Khi đó có thể truyền `ByteArrayOutputStream` để giữ kết quả trong bộ nhớ.

```text
PDF generator
     |
     | write(OutputStream)
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
MimeMessageHelper.addAttachment(...)
```

Ví dụ giả định ứng dụng có một thành phần `PdfReportGenerator` nhận dữ liệu và ghi PDF hợp lệ vào output stream:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.List;

public class PdfReportService {

    private final PdfReportGenerator generator;

    public PdfReportService(PdfReportGenerator generator) {
        this.generator = generator;
    }

    public byte[] createReport(List<OrderRow> rows) throws IOException {
        try (ByteArrayOutputStream output =
                 new ByteArrayOutputStream()) {

            generator.write(rows, output);
            return output.toByteArray();
        }
    }
}
```

`PdfReportGenerator` là abstraction minh họa do ứng dụng định nghĩa; thư viện PDF thực tế có API riêng. `ByteArrayOutputStream` không cần đóng để giải phóng tài nguyên hệ điều hành, nhưng try-with-resources vẫn làm rõ vòng đời. `toByteArray()` trả về một bản sao byte của dữ liệu đã ghi.

Sau đó đính kèm:

```java
byte[] pdfBytes = pdfReportService.createReport(rows);

helper.addAttachment(
    "order-report.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

Nếu thư viện PDF có thể xuất trực tiếp ra byte array, dùng kết quả đó luôn. Nếu nó chỉ ghi ra stream, `ByteArrayOutputStream` là cầu nối đơn giản khi kích thước phù hợp với RAM.

## 7. Ví dụ hoàn chỉnh: tạo PDF và gửi cùng email HTML

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.util.List;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class PdfAttachmentMailService {

    private final JavaMailSender mailSender;
    private final PdfReportService pdfReportService;

    public PdfAttachmentMailService(
            JavaMailSender mailSender,
            PdfReportService pdfReportService) {
        this.mailSender = mailSender;
        this.pdfReportService = pdfReportService;
    }

    public void sendMonthlyReport(
            String recipient,
            List<OrderRow> rows)
            throws IOException, MessagingException {

        // 1. Tạo nội dung file trong bộ nhớ.
        byte[] pdfBytes = pdfReportService.createReport(rows);

        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalStateException(
                "Không tạo được nội dung PDF"
            );
        }

        // 2. Tạo MIME message có multipart.
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED,
            "UTF-8"
        );

        // 3. Đặt thông tin email và body.
        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo tháng");
        helper.setText(
            "Chào bạn,\nBáo cáo tháng được đính kèm dưới dạng PDF.",
            """
            <html>
              <body>
                <h2>Báo cáo tháng</h2>
                <p>Báo cáo chi tiết được đính kèm trong email.</p>
              </body>
            </html>
            """
        );

        // 4. Thêm file được sinh trong RAM.
        helper.addAttachment(
            "monthly-report.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
        );

        // 5. Gửi sau khi hoàn thiện MIME.
        mailSender.send(message);
    }
}
```

Ví dụ giả định `PdfReportService` có thể tạo báo cáo từ `rows` và recipient đã được xác thực/ủy quyền theo nghiệp vụ. Khi gửi thật, cần quản lý exception ở tầng gọi để ghi nhận attempt và xử lý retry có kiểm soát.

Dùng `MULTIPART_MODE_MIXED` khi email có body và các tệp đính kèm độc lập. Nếu email còn có ảnh inline tham chiếu bởi HTML, cân nhắc `MULTIPART_MODE_MIXED_RELATED` và gọi `setText(...)` trước `addInline(...)`; attachment độc lập được thêm bằng `addAttachment(...)`.

## 8. Dùng InputStreamSource khi cần nguồn đọc lại được

`MimeMessageHelper` có overload nhận `InputStreamSource`. Nếu dữ liệu đã có trong byte array, có thể viết:

```java
import java.io.ByteArrayInputStream;
import org.springframework.core.io.InputStreamSource;

byte[] bytes = createFileBytes();

InputStreamSource source =
    () -> new ByteArrayInputStream(bytes);

helper.addAttachment(
    "data.json",
    source,
    "application/json; charset=UTF-8"
);
```

Lambda tạo một stream mới mỗi lần helper hoặc provider yêu cầu đọc dữ liệu. Với byte array có sẵn, `ByteArrayResource` ngắn gọn hơn và thể hiện rõ mục đích.

### 8.1. Vì sao không dùng lại một InputStream đã mở?

Mẫu dễ gây lỗi:

```java
InputStream input = createInputStream();

InputStreamSource oneShot = () -> input;

helper.addAttachment(
    "report.pdf",
    oneShot,
    "application/pdf"
);
```

Nguồn này luôn trả về cùng một stream. Sau khi stream đã đọc đến cuối hoặc bị đóng, lần đọc tiếp theo có thể trả dữ liệu rỗng hoặc ném lỗi. Thư viện mail có thể cần đọc lại nội dung khi chuẩn bị và gửi MIME.

Thay vào đó, cung cấp một factory mở stream mới:

```java
InputStreamSource repeatable = () ->
    storage.openNewStream(reportId);
```

`storage.openNewStream(...)` là API giả định của ứng dụng; mỗi lần gọi phải tạo một stream độc lập bắt đầu từ đầu. Nếu storage chỉ cung cấp stream dùng một lần, có thể spool dữ liệu vào bộ nhớ khi nhỏ hoặc tệp tạm có kiểm soát khi lớn.

### 8.2. ByteArrayResource và InputStreamResource

| Resource | Hành vi thường gặp | Khi phù hợp |
|---|---|---|
| `ByteArrayResource` | Giữ byte array và tạo stream mới từ đầu mỗi lần đọc. | File đã nằm trong RAM, kích thước phù hợp. |
| `InputStreamResource` | Thường đại diện cho stream đã có; không nên giả định đọc lại được. | Nguồn một lần trong API không yêu cầu replay; cần thận trọng khi dùng làm mail attachment. |
| `FileSystemResource` | Mở file từ đường dẫn khi cần đọc. | File tồn tại trên disk và có thể mở lại. |
| `ClassPathResource` | Mở resource đóng gói trong classpath. | File tĩnh trong ứng dụng. |
| `InputStreamSource` tùy biến | Tùy implementation, có thể trả stream mới hoặc stream một lần. | Storage/object store hoặc nguồn động có API mở lại. |

Đối với attachment email, ưu tiên **nguồn có thể mở lại**. Đừng dựa vào việc “đã chạy thử một lần” để kết luận nguồn stream dùng được trong mọi trường hợp.

## 9. Chọn Content-Type và tên file

Một MIME part cần kiểu nội dung phù hợp:

| Định dạng | Filename gợi ý | Content-Type |
|---|---|---|
| PDF | `report.pdf` | `application/pdf` |
| CSV | `report.csv` | `text/csv; charset=UTF-8` |
| JSON | `data.json` | `application/json; charset=UTF-8` |
| XML | `data.xml` | `application/xml; charset=UTF-8` |
| ZIP | `documents.zip` | `application/zip` |
| PNG | `chart.png` | `image/png` |
| JPEG | `photo.jpg` | `image/jpeg` |
| Excel Open XML | `report.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

**Filename, extension và Content-Type cần nhất quán với byte thật.** Không thể đặt `application/pdf` cho dữ liệu CSV rồi kỳ vọng người nhận mở được PDF.

### 9.1. Đặt tên file rõ ràng và an toàn

Ví dụ:

```java
helper.addAttachment(
    "invoice-2026-11.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

Tránh dùng nguyên filename tùy ý từ người dùng hoặc dữ liệu chưa kiểm soát. Tên file nên:
- không chứa đường dẫn như `../../secret.txt`;
- không chứa CR/LF hoặc ký tự điều khiển;
- có phần mở rộng đúng định dạng;
- có độ dài hợp lý;
- không để lộ dữ liệu cá nhân hoặc thông tin nhạy cảm không cần thiết.

Nếu cần filename Unicode, hãy kiểm tra cách các mail client mục tiêu hiển thị tên tệp. Thư viện xử lý encoding header, nhưng khả năng tương thích có thể khác nhau giữa client cũ và mới.

### 9.2. Content-Type không xác minh nội dung

Content-Type là metadata được khai báo. Nếu byte đầu vào bị lỗi hoặc bị tráo, header vẫn có thể nói `application/pdf`. Khi dữ liệu đến từ một bộ tạo file, hãy xử lý exception của exporter, kiểm tra kết quả hợp lệ theo khả năng thư viện tạo file và tránh coi việc kiểm tra vài byte đầu là xác minh đầy đủ.

## 10. Giới hạn bộ nhớ và kích thước email

Đính kèm trong RAM đơn giản nhưng có chi phí bộ nhớ.

### 10.1. Base64 làm email lớn hơn

Dữ liệu nhị phân thường được mã hóa Base64 trong MIME. Dung lượng phần dữ liệu sau mã hóa tăng khoảng **một phần ba** so với byte gốc, chưa tính header, boundary, newline và nội dung body.

| Dữ liệu gốc | Dung lượng Base64 gần đúng |
|---:|---:|
| 300 KB | 400 KB |
| 1 MB | 1,33 MB |
| 5 MB | 6,67 MB |
| 10 MB | 13,33 MB |

Đây chỉ là ước lượng cho payload Base64, không phải kích thước email cuối cùng hoặc giới hạn của provider. SMTP server có thể áp dụng giới hạn theo message size, account, recipient hoặc chính sách khác.

### 10.2. RAM có thể tăng hơn kích thước file

Với một attachment, dữ liệu có thể tồn tại ở nhiều dạng trong cùng thời điểm:
- buffer của bộ tạo file;
- mảng byte trả về từ `toByteArray()`;
- byte array được giữ trong `ByteArrayResource`;
- buffer nội bộ khi Jakarta Mail mã hóa MIME;
- buffer của transport, framework và JVM.

`ByteArrayOutputStream.toByteArray()` tạo một bản sao byte của nội dung đã ghi, nên peak memory có thể cao hơn dung lượng file. Nhiều attachment lớn được tạo đồng thời bởi nhiều worker có thể làm heap tăng mạnh hoặc gây `OutOfMemoryError`.

### 10.3. Đặt giới hạn trước khi tạo hoặc gửi

Nên xác định:
- giới hạn kích thước từng file;
- giới hạn tổng kích thước attachment;
- giới hạn số attachment;
- giới hạn số email đồng thời tạo file;
- giới hạn recipient/worker theo quota provider;
- chính sách khi file vượt giới hạn (từ chối, chia nhỏ hoặc lưu ở kho tài liệu và gửi link an toàn).

Có thể kiểm tra sau khi tạo byte array:

```java
private static final int MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;

if (pdfBytes.length > MAX_ATTACHMENT_BYTES) {
    throw new IllegalArgumentException(
        "File vượt giới hạn cho phép"
    );
}
```

Ngưỡng 5 MB chỉ là ví dụ cho ứng dụng, **không phải giới hạn chung của Spring hoặc SMTP**. Trong thực tế, đặt giới hạn phù hợp với provider sau khi tính overhead MIME và phần body.

Nếu file rất lớn, cân nhắc lưu tại object storage/document service có quyền truy cập phù hợp và gửi **liên kết có thời hạn** thay vì đính kèm. Link cũng cần kiểm soát người nhận, thời hạn, quyền tải và không để token lộ qua log.

## 11. Bảo mật dữ liệu đính kèm

Dữ liệu sinh trong bộ nhớ có thể chứa hóa đơn, thông tin cá nhân, số liệu nội bộ hoặc tài liệu tài chính. Cần bảo vệ từ lúc tạo đến khi email được gửi:

- Xác minh người nhận có quyền nhận đúng báo cáo/tài liệu đó.
- Chỉ tạo những trường dữ liệu cần thiết cho mục đích email.
- Không log byte array, Base64, nội dung PDF/CSV hoặc URL tải có token.
- Không ghi secret, password hoặc access token vào tên file, header hay nội dung.
- Kiểm tra filename để tránh header injection và lộ đường dẫn.
- Hạn chế lưu file trong cache, dump hoặc tệp tạm nếu không cần.
- Nếu email phải mã hóa tài liệu ở mức ứng dụng, cần thiết kế encryption và phân phối khóa riêng; TLS của SMTP chỉ bảo vệ đường truyền theo từng chặng, không tự mã hóa file end-to-end.
- Có chính sách retention cho bản sao ở provider và mailbox người nhận.

Với CSV có thể mở trong spreadsheet, xem xét **formula injection** khi ô chứa dữ liệu người dùng bắt đầu bằng ký tự có thể kích hoạt công thức. CSV quoting không tự ngăn spreadsheet thực thi công thức. Chính sách bảo vệ phải phù hợp với loại dữ liệu và phần mềm người nhận sử dụng.

## 12. Đính kèm nhiều file sinh trong bộ nhớ

Có thể gọi `addAttachment(...)` nhiều lần trên cùng helper:

```java
helper.addAttachment(
    "summary.csv",
    new ByteArrayResource(csvBytes),
    "text/csv; charset=UTF-8"
);

helper.addAttachment(
    "invoice.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);

helper.addAttachment(
    "chart.png",
    new ByteArrayResource(chartBytes),
    "image/png"
);
```

Mỗi part có filename, Content-Type và nguồn byte riêng. Hãy kiểm tra:
- filename không trùng gây người nhận khó phân biệt;
- byte đúng với loại file;
- tổng dung lượng trong giới hạn;
- mỗi resource có thể mở stream mới;
- không đưa tài liệu của một người nhận sang email người khác khi xử lý batch.

Nếu một email được cá nhân hóa cho nhiều người, thông thường nên tạo message riêng cho từng người nhận, với attachment tương ứng quyền truy cập của họ. Không gom danh sách người nhận vào `To` rồi gửi tài liệu cá nhân của từng người.

## 13. Attachment khác inline resource

Hai phương thức có mục đích khác nhau:

| Phương thức | Mục đích | Cách tham chiếu |
|---|---|---|
| `helper.addAttachment(...)` | Tệp đính kèm độc lập để người nhận mở/tải | Filename và Content-Disposition attachment. |
| `helper.addInline(...)` | Tài nguyên phục vụ hiển thị nội dung HTML | HTML tham chiếu bằng `cid:...`, MIME part có Content-ID. |

Ví dụ attachment:

```java
helper.setText("Báo cáo được đính kèm.");
helper.addAttachment(
    "report.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

Ví dụ inline image:

```java
helper.setText(
    "Báo cáo",
    "<html><body><img src=\"cid:chart\"></body></html>"
);
helper.addInline(
    "chart",
    new ByteArrayResource(chartBytes),
    "image/png"
);
```

Với inline, tuân thủ thứ tự **`setText(...)` trước `addInline(...)`** để tạo body và resource liên quan theo cấu trúc MIME phù hợp. Với attachment độc lập, thêm sau khi thiết lập body cũng giúp quy trình dễ đọc và kiểm soát.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
|---|---|---|
| Attachment có kích thước 0 byte | Byte array rỗng, exporter chưa ghi vào output stream | Kiểm tra kết quả exporter trước khi gọi addAttachment. |
| File nhận được không mở được | Content-Type/filename không đúng hoặc byte bị tạo sai | Kiểm tra định dạng thực, exporter và byte đầu ra. |
| Dữ liệu thiếu ở cuối file | Stream đã bị đọc một phần, exporter chưa hoàn tất | Dùng nguồn mở stream mới; hoàn tất exporter trước khi lấy byte. |
| Lần gửi đầu được, lần gửi sau file rỗng | InputStreamSource trả cùng stream dùng một lần | Dùng ByteArrayResource hoặc factory tạo stream mới. |
| Không tìm thấy attachment | Helper không ở multipart mode hoặc code không gọi addAttachment | Bật multipart và kiểm tra MIME source. |
| File có tên kỳ lạ | Không truyền filename riêng hoặc encoding tên file khác client | Truyền filename rõ ràng, test client hỗ trợ Unicode. |
| SMTP từ chối message quá lớn | File và Base64 vượt quota | Giới hạn kích thước, giảm file hoặc gửi link an toàn. |
| Ứng dụng tăng heap/OutOfMemory | Nhiều báo cáo lớn được tạo đồng thời | Giới hạn concurrency, spool hoặc dùng object storage. |
| Tên file chứa đường dẫn/ký tự lạ | Lấy filename thô từ người dùng | Chuẩn hóa và whitelist filename. |
| CSV mở ra bị lỗi dấu | Encoding không phù hợp hoặc client nhận diện sai | Dùng UTF-8, xác định có cần BOM cho phần mềm đích. |
| CSV có ô chạy công thức ngoài ý muốn | Dữ liệu text bắt đầu bằng ký tự spreadsheet đặc biệt | Áp dụng chính sách formula-injection cho các ô text. |
| PDF/CSV bị lộ cho sai người nhận | Tái sử dụng message hoặc byte data sai phạm vi | Gắn dữ liệu với recipient/job; tạo message riêng và kiểm tra quyền. |

### 14.1. Phân biệt lỗi tạo file và lỗi gửi email

```text
Generate report
    | IOException / lỗi exporter
    v
Validate byte[] and size
    | dữ liệu rỗng / quá lớn
    v
Build MimeMessage
    | MessagingException
    v
JavaMailSender.send
    | MailException
    v
SMTP acceptance
    | bounce/delivery event (nếu provider hỗ trợ)
```

Không retry SMTP để khắc phục lỗi PDF exporter. Ngược lại, nếu file đã tạo đúng nhưng SMTP timeout, có thể cần retry send theo outbox và chính sách idempotency riêng.

Một lần `send(...)` thành công thường chỉ cho biết SMTP server đã tiếp nhận thông điệp; không chứng minh file đã được tải xuống hoặc email đã được người nhận mở.

## 15. Kiểm tra MIME attachment

Khi cần chẩn đoán, có thể xem raw source của email nhận hoặc kiểm tra `MimeMessage` trước khi gửi. Một MIME part minh họa:

```text
Content-Type: application/pdf; name="monthly-report.pdf"
Content-Disposition: attachment; filename="monthly-report.pdf"
Content-Transfer-Encoding: base64

[PDF_BYTES_DA_MA_HOA_BASE64]
```

Các header cần đối chiếu:
- `Content-Type`: định dạng dữ liệu.
- `Content-Disposition: attachment`: đánh dấu file là attachment.
- `filename`: tên người nhận thấy.
- `Content-Transfer-Encoding`: cách biểu diễn dữ liệu trong MIME.

Có thể kiểm tra số MIME part trước khi gửi:

```java
message.saveChanges();

Object content = message.getContent();
if (content instanceof jakarta.mail.Multipart multipart) {
    System.out.println("MIME parts: " + multipart.getCount());
}
```

Không in byte file hoặc Base64 vào log. Nếu cần kiểm tra nội dung, hãy so sánh hash trong môi trường test với dữ liệu test đã biết, hoặc trích xuất vào bộ nhớ test có kiểm soát. Raw MIME có thể chứa dữ liệu nhạy cảm và không nên lưu lâu trong log production.

## 16. Bài tập thực hành

### Bài 1 — Đính kèm một byte array
Tạo một mảng byte đại diện nội dung file nhỏ, tạo `MimeMessage` và `MimeMessageHelper` multipart, rồi đính kèm bằng `ByteArrayResource`. Chỉ rõ filename và Content-Type phù hợp.

### Bài 2 — Tạo CSV từ danh sách
Viết exporter nhận danh sách đơn hàng, tạo header và các dòng CSV, escape dấu phẩy/quote, chuyển thành UTF-8 byte array rồi gửi. Thử tên khách hàng chứa dấu phẩy, dấu ngoặc kép và tiếng Việt.

### Bài 3 — Tạo PDF qua OutputStream
Giả lập exporter có phương thức `write(data, outputStream)`. Dùng `ByteArrayOutputStream`, gọi `toByteArray()` sau khi exporter hoàn tất và đính kèm kết quả. Giải thích vì sao `toByteArray()` tạo bản sao dữ liệu.

### Bài 4 — Kiểm tra nguồn stream một lần
Tạo `InputStreamSource` trả về cùng một `ByteArrayInputStream` instance đã đọc hết. Quan sát lần đọc thứ hai. Sửa thành lambda tạo `new ByteArrayInputStream(bytes)` mỗi lần gọi hoặc chuyển sang `ByteArrayResource`.

### Bài 5 — Kiểm tra Content-Type
Đính kèm một file PDF nhưng khai báo `text/csv`. Giải thích vì sao filename/Content-Type sai không chuyển đổi nội dung file và có thể làm mail client xử lý sai.

### Bài 6 — Giới hạn kích thước
Tạo dữ liệu 1 MB, 5 MB và 10 MB; tính ước lượng Base64 payload tăng khoảng một phần ba, rồi quyết định ngưỡng cho phép dựa trên giới hạn provider và concurrency. Không coi các mức này là quota SMTP mặc định.

### Bài 7 — Bảo vệ CSV
Đưa các giá trị `=HYPERLINK(...)`, `+SUM(...)` và `@...` vào cột text. Phân biệt CSV quoting với chính sách formula injection khi file được mở bằng spreadsheet.

### Bài 8 — Nhiều recipient
Một báo cáo chứa thông tin cá nhân của từng khách hàng. Hãy thiết kế job tạo attachment và MIME message riêng cho từng recipient được ủy quyền; không tái sử dụng message/byte data sai phạm vi.

## 17. Tổng kết

Để **đính kèm dữ liệu sinh trong bộ nhớ** với Spring Framework Mail, hãy tạo nội dung file thành `byte[]` hoặc một `InputStreamSource` có thể mở stream mới, rồi truyền vào `MimeMessageHelper.addAttachment(...)` cùng filename và Content-Type đúng. `ByteArrayResource` là lựa chọn đơn giản khi dữ liệu đã có trong RAM; `ByteArrayOutputStream` hữu ích khi thư viện tạo file ghi ra `OutputStream`.

Cách làm này loại bỏ bước ghi/đọc file tạm, nhưng cần kiểm soát **dung lượng, peak memory, khả năng đọc lại, quyền người nhận, tên file, MIME type và nội dung nhạy cảm**. Với file lớn hoặc nhiều job đồng thời, cân nhắc spool có kiểm soát hoặc lưu tài liệu trong object storage rồi gửi link an toàn. Khi đã hoàn thiện byte dữ liệu và MIME, `JavaMailSender` mới thực hiện gửi email qua SMTP.

