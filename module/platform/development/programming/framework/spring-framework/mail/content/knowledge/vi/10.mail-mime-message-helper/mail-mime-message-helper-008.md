# Tên attachment và kiểu nội dung

Một ứng dụng Spring Boot gửi hóa đơn điện tử cho khách hàng. File trên máy chủ có tên `8f6c9e0a-7a62-4b59-9bc9.pdf`, nhưng người nhận cần thấy **`hoa-don-DH1024.pdf`** trong email. Cùng lúc đó, email client phải hiểu đây là tệp PDF chứ không phải một đoạn văn bản thuần. Nếu hóa đơn có tên tiếng Việt, chẳng hạn `Hóa đơn tháng 11.pdf`, bài toán còn liên quan đến cách mã hóa **tên tệp trong header MIME**.

Trong **Spring Framework Mail**, `MimeMessageHelper` giúp giải quyết các nhu cầu ấy bằng các phương thức như:

```java
helper.addAttachment("hoa-don-DH1024.pdf", pdfResource, "application/pdf");
```

Ba tham số trên không giống nhau: **tên tệp hiển thị**, **nguồn dữ liệu**, và **kiểu nội dung MIME**. Hiểu được từng phần giúp ứng dụng tạo email dễ đọc, đúng định dạng, có khả năng tương thích và không vô tình tiết lộ đường dẫn nội bộ hoặc tin tưởng sai loại file.

## 1. Attachment là gì trong một email MIME?

**Attachment** là một phần nội dung (*MIME body part*) được gửi cùng thông điệp email, thường để người nhận xem hoặc tải về như một tệp độc lập.

Một email chứa văn bản và PDF có thể được tổ chức như sau:

```text
MimeMessage
├── From: billing@example.com
├── To: customer@example.net
├── Subject: Hóa đơn đơn hàng DH1024
└── multipart/mixed
    ├── text/plain; charset=UTF-8
    │   └── "Vui lòng xem hóa đơn đính kèm."
    └── application/pdf
        ├── Content-Disposition: attachment; filename="hoa-don-DH1024.pdf"
        ├── Content-Transfer-Encoding: base64
        └── [dữ liệu PDF đã được mã hóa để vận chuyển]
```

Đây là cấu trúc minh họa: ranh giới multipart, tên tham số, encoding và thứ tự header thực tế do thư viện Jakarta Mail tạo ra. Một email còn có thể chứa HTML, hình ảnh inline hoặc nhiều attachment.

Các thành phần cần phân biệt:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Tên attachment** (*filename*) | Tên gợi ý để email client hiển thị/lưu file | `hoa-don-DH1024.pdf` |
| **MIME content type** | Chỉ định loại dữ liệu trong MIME part | `application/pdf` |
| **Nguồn dữ liệu** | Cung cấp byte thực của file cho transport | `FileSystemResource`, `ByteArrayResource`, `DataSource` |
| **Content-Disposition** | Gợi ý nên hiển thị dạng tệp đính kèm hay nội dung inline | `attachment` |
| **Content-Transfer-Encoding** | Cách biểu diễn byte trên đường vận chuyển MIME | `base64` |
| **Content-ID** | Định danh để tham chiếu một part trong HTML, thường dùng cho hình inline | `<brand-logo>` |

Không nên xem tất cả những thứ này là “đuôi file”. Tên `report.pdf` chỉ là chuỗi metadata; file có thật sự là PDF hay không phụ thuộc **byte nội dung** và cách ứng dụng tạo/kiểm tra nó.

### 1.1. Tên file trên đĩa và tên hiển thị trong email là hai thứ khác nhau

Ví dụ:

```text
Đường dẫn nguồn:
    /srv/app/storage/2026/11/8f6c9e0a-7a62-4b59.pdf

Tên attachment gửi cho khách:
    hoa-don-DH1024.pdf
```

Khi sử dụng `MimeMessageHelper.addAttachment(...)`, ứng dụng thường truyền **tên hiển thị** ở tham số đầu tiên và nguồn dữ liệu ở tham số tiếp theo. Nhờ vậy không phải đưa đường dẫn file nội bộ hoặc mã định danh lưu trữ vào header cho người nhận.

Ví dụ:

```java
FileSystemResource pdf =
        new FileSystemResource(Path.of(
                "storage", "2026", "11", "8f6c9e0a-7a62-4b59.pdf"));

helper.addAttachment("hoa-don-DH1024.pdf", pdf, "application/pdf");
```

Trong email, tên mong muốn là `hoa-don-DH1024.pdf`. `MimeMessageHelper` không thay đổi tên file vật lý trên đĩa.

## 2. Content-Type và Content-Disposition: hai header khác mục đích

### 2.1. `Content-Type` cho biết kiểu dữ liệu

MIME part có thể chứa:

```text
Content-Type: application/pdf
```

Ý nghĩa: part được mô tả là tệp **PDF**. Một vài loại thường gặp:

| Nội dung | MIME type phổ biến |
|---|---|
| PDF | `application/pdf` |
| Plain text | `text/plain` |
| HTML | `text/html` |
| CSV | `text/csv` |
| JSON | `application/json` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| ZIP | `application/zip` |
| Microsoft Word (.docx) | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| Microsoft Excel (.xlsx) | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| Kiểu nhị phân chưa rõ | `application/octet-stream` |

**Kiểu MIME là metadata do bên gửi khai báo, không phải cơ chế xác minh an toàn của file.** Một người có thể đặt tên `photo.png` cho dữ liệu không phải PNG hoặc gửi nội dung HTML với tên đuôi `.txt`. Ứng dụng nhận không nên tin hoàn toàn vào `Content-Type` hay extension khi quyết định xử lý file không tin cậy.

### 2.2. `Content-Disposition` mô tả ý định hiển thị

Ví dụ:

```text
Content-Disposition: attachment; filename="hoa-don-DH1024.pdf"
```

- **`attachment`**: gợi ý email client trình bày nội dung như file đính kèm.
- **`filename`**: gợi ý tên tệp khi lưu hoặc hiển thị.

Ngược lại, nội dung HTML tham chiếu hình ảnh có thể dùng:

```text
Content-Disposition: inline
Content-ID: <brand-logo>
Content-Type: image/png
```

Tuy nhiên, **email client là bên quyết định cách hiển thị cuối cùng**. Một số client cho phép xem PDF ngay trong giao diện; một số client lại hiển thị hình inline như attachment. Đó không nhất thiết là lỗi của Spring Mail.

### 2.3. `Content-Transfer-Encoding` không phải Content-Type

Một PDF nhị phân thường được chuyển sang base64 để vận chuyển an toàn qua email:

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="hoa-don-DH1024.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJcTl8uXrp...
```

Trong ví dụ:

- `application/pdf` là **loại nội dung được khẳng định**.
- `attachment` là **cách hiển thị được gợi ý**.
- `base64` là **cách biểu diễn byte trong MIME part khi vận chuyển**.

`base64` không làm PDF trở thành văn bản thuần và cũng không mã hóa bảo mật nội dung. Email client giải mã base64 để lấy lại byte file gốc.

## 3. `MimeMessageHelper.addAttachment(...)` hoạt động ra sao?

Trong Spring Boot, khi cần gửi attachment, dùng `JavaMailSender` để tạo `MimeMessage` và `MimeMessageHelper` ở **chế độ multipart**.

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.file.Path;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn đơn hàng DH1024");
helper.setText("Vui lòng xem tệp PDF đính kèm.", false);

FileSystemResource pdf = new FileSystemResource(
        Path.of("storage", "invoice.pdf"));
helper.addAttachment("hoa-don-DH1024.pdf", pdf, "application/pdf");

mailSender.send(message);
```

Ở đây:

1. `createMimeMessage()` tạo đối tượng email do Jakarta Mail biểu diễn.
2. Constructor `MimeMessageHelper(message, true, "UTF-8")` kích hoạt **multipart** và đặt charset sử dụng khi helper tạo nội dung.
3. `addAttachment(...)` thêm một MIME part dạng attachment.
4. `mailSender.send(message)` gửi **chính đối tượng message** đã được helper xây dựng.

Nếu dùng constructor với `multipart=false`, `addAttachment(...)` không thể tạo cấu trúc multipart đúng yêu cầu; helper sẽ báo lỗi. Hãy chọn chế độ multipart ngay từ khi tạo helper.

### 3.1. Các overload thường dùng

Các cách thêm attachment phổ biến:

```java
// 1. File vật lý
helper.addAttachment("report.pdf", pdfFile);

// 2. Resource đọc được từ file
helper.addAttachment("report.pdf", new FileSystemResource(pdfFile));

// 3. Resource và content type tường minh
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(pdfFile),
        "application/pdf");

// 4. Byte array trong bộ nhớ và content type tường minh
helper.addAttachment(
        "export.csv",
        new ByteArrayResource(csvBytes),
        "text/csv");

// 5. Jakarta Activation DataSource
helper.addAttachment("report.pdf", dataSource);
```

Trong đoạn minh họa, `pdfFile` là `java.io.File`, `csvBytes` là `byte[]`, và `dataSource` là một `jakarta.activation.DataSource` đã được chuẩn bị. `ByteArrayResource`, `FileSystemResource` thuộc `org.springframework.core.io`.

Chọn overload dựa trên **nguồn byte thực có sẵn** và mức độ bạn muốn kiểm soát `Content-Type`, chứ không phải chỉ dựa trên đuôi tệp.

### 3.2. Khi không truyền content type, thư viện lấy ở đâu?

Một số overload cho phép bỏ tham số `contentType`. Khi ấy helper có thể dùng **`FileTypeMap`** để suy ra kiểu nội dung theo **tên attachment** và cấu hình mapping của môi trường.

Điều này tiện cho các đuôi quen thuộc, nhưng có giới hạn:

- Mapping có thể không nhận biết các extension riêng hoặc mới.
- Mapping theo tên **không kiểm tra byte thực**.
- Cùng một file có thể được phân loại khác nhau nếu mapping/runtime thay đổi.
- Nếu không nhận ra, có thể rơi về kiểu nhị phân chung như `application/octet-stream`.

Với tệp do ứng dụng **tự sinh và biết chính xác định dạng**, nên chỉ định content type tường minh:

```java
helper.addAttachment(
        "invoice.pdf", new FileSystemResource(invoicePath), "application/pdf");
```

Với tệp không tin cậy do người dùng tải lên, **không được lấy mỗi extension để quyết định file an toàn**. Cần kiểm tra định dạng và thực thi chính sách upload trước khi cho phép email mang tệp đó đi.

## 4. Tên attachment được đưa vào header như thế nào?

Thông điệp MIME có thể có các trường sau:

```text
Content-Type: application/pdf; name="hoa-don-DH1024.pdf"
Content-Disposition: attachment; filename="hoa-don-DH1024.pdf"
Content-Transfer-Encoding: base64
```

Đây là **ví dụ cấu trúc**. Một số thư viện/client có thể tạo `filename` trong `Content-Disposition`, `name` trong `Content-Type`, hoặc cả hai để tương thích. Khi cần xác định tên file, không nên suy ra rằng **cả hai tham số luôn có mặt**.

### 4.1. Filename không phải đường dẫn

Tên:

```text
hoa-don-DH1024.pdf
```

khác với đường dẫn:

```text
/var/app/data/customers/1024/invoice.pdf
C:\services\billing\exports\invoice.pdf
```

Chỉ cần gửi **tên hiển thị**, không gửi đường dẫn nội bộ. Việc lộ đường dẫn có thể tiết lộ cấu trúc hệ thống hoặc tên thư mục nhạy cảm.

Tham số `attachmentFilename` trong `addAttachment` là metadata dành cho email client; không nên trộn nó với cơ chế xác định **file nguồn**.

### 4.2. Thế nào là một filename dễ tương thích?

Những tên có tính tương thích cao thường:

- Ngắn, có ý nghĩa cho người nhận: `invoice-DH1024.pdf`.
- Có đuôi khớp với định dạng thực tế: PDF thì `.pdf`, CSV thì `.csv`.
- Không chứa CR, LF, NUL hoặc ký tự điều khiển.
- Không chứa dấu phân cách đường dẫn `/`, `\` hoặc thông tin thư mục.
- Không quá dài; tránh gây khó khăn cho client và hệ điều hành người nhận.
- Không dùng tên gây hiểu nhầm, ví dụ `invoice.pdf.exe` hoặc đuôi tệp khác bản chất nội dung.

Tên hiển thị **không nhất thiết bằng tên file trên server**. Ứng dụng có thể lưu file theo UUID để chống trùng và gửi tên rõ ràng cho khách hàng.

## 5. Tên attachment tiếng Việt, Unicode và cơ chế mã hóa

Một tên file có thể là:

```text
Hóa đơn tháng 11.pdf
Bảng đối soát – Quý IV.xlsx
Hồ sơ Nguyễn Văn An.zip
```

Những tên này chứa ký tự Unicode. Trong MIME truyền thống, các tham số header cần **biểu diễn an toàn trên đường vận chuyển**; không thể giả định mọi chuỗi Unicode được đưa nguyên dạng trực tiếp vào `Content-Disposition: filename=...` đều tương thích.

### 5.1. RFC 2231 và tham số filename

Một cách mã hóa tham số quốc tế hóa là cú pháp mở rộng theo **RFC 2231**, ví dụ dạng khái niệm:

```text
Content-Disposition: attachment;
 filename*=UTF-8''H%C3%B3a%20%C4%91%C6%A1n%20th%C3%A1ng%2011.pdf
```

Ý nghĩa:

- `filename*` báo đây là tham số mở rộng có charset và encoding.
- `UTF-8` chỉ bộ mã ký tự.
- `''` ở đây là phần phân tách charset với language tag rỗng.
- Các byte không phù hợp để xuất hiện trực tiếp được biểu diễn bằng dạng phần trăm `%HH`.

RFC 2231 còn có cơ chế **chia một tham số dài thành nhiều phần** (*continuation*) khi cần. Đây là cách biểu diễn ở tầng header, không phải tên file mà người dùng nên nhìn thấy sau khi email client giải mã.

**Không được tự thay chuỗi filename bằng URL-encoding chung rồi cho rằng header đã chuẩn.** Cú pháp tham số MIME có những quy tắc riêng; nên để Jakarta Mail xử lý quá trình mã hóa, folding và quoting.

### 5.2. RFC 2047 không giống RFC 2231

**RFC 2047** định nghĩa encoded-word như:

```text
=?UTF-8?B?...?=
```

Nó thường được dùng cho **tên hiển thị trong header địa chỉ** hoặc **Subject**, nơi encoded-word được phép theo quy tắc của header.

**Tham số `filename` trong `Content-Disposition`** có bài toán khác. RFC 2231 là cơ chế được thiết kế cho **tham số MIME** có ký tự quốc tế hóa. Một số ứng dụng và thư viện có cơ chế mã hóa filename kiểu RFC 2047 như một **lựa chọn tương thích với một số email client**, nhưng không nên coi encoded-word là cùng một cú pháp chuẩn với RFC 2231 cho mọi vị trí tham số.

Trong Spring Framework, `MimeMessageHelper` có tùy chọn `setEncodeFilenames(boolean)` ở các phiên bản hỗ trợ, ảnh hưởng đến cách helper xử lý tên tệp. Cần hiểu đây là **quyết định tương thích**; hành vi cuối cùng còn phụ thuộc phiên bản Spring/Jakarta Mail và các thuộc tính MIME của JavaMail provider.

Ví dụ chỉ khi đã kiểm chứng tương thích với đối tượng nhận:

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

// Tùy chọn cho các email client cần cách mã hóa filename riêng.
// Không mặc định bật nếu chưa hiểu hành vi của provider/client.
helper.setEncodeFilenames(true);

helper.addAttachment(
        "Hóa đơn tháng 11.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");
```

**Lưu ý:** bật `setEncodeFilenames(true)` không phải câu trả lời chung cho mọi lỗi Unicode. Khi có vấn đề, xem header thực tế được tạo, phiên bản Jakarta Mail, cấu hình encode parameters và khả năng giải mã của các email client mục tiêu. Với nhu cầu tương thích tối đa mà không phụ thuộc ký tự Unicode trong filename, tên ASCII có nghĩa như `hoa-don-thang-11.pdf` thường là lựa chọn dự phòng hữu ích.

### 5.3. Charset của nội dung body khác charset filename

Cấu hình:

```java
new MimeMessageHelper(message, true, "UTF-8");
```

có ích cho việc tạo nội dung MIME và các trường văn bản tương ứng. Nhưng **nội dung body**, **tên hiển thị người nhận**, **Subject** và **tham số filename** có **quy tắc mã hóa header khác nhau**. Không nên chỉ đặt `charset=UTF-8` cho `text/html` rồi tự ghép tên file Unicode vào `Content-Disposition`.

Khi xử lý lỗi như “người nhận thấy `=?UTF-8?...?=`”, “tên file bị vỡ dấu” hoặc “filename hiển thị nguyên `%C3%A1`”, cần kiểm tra **phần header MIME của attachment**, không chỉ phần body.

## 6. Cách cung cấp Content-Type tường minh

### 6.1. PDF

```java
helper.addAttachment(
        "hoa-don-DH1024.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");
```

Vì hệ thống tạo file hóa đơn PDF và đã biết định dạng, `application/pdf` mô tả đúng ý nghĩa.

### 6.2. CSV

```java
byte[] csvBytes = """
        order_id,total
        DH1024,120000
        DH1025,95000
        """.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "don-hang.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8");
```

Trong ví dụ:

- Dữ liệu được tạo thành byte UTF-8.
- Content type `text/csv` chỉ loại dữ liệu.
- Tham số `charset=UTF-8` mô tả charset của phần text, khi thư viện/recipient xử lý theo quy tắc MIME.

**CSV còn có vấn đề về diễn giải dữ liệu bởi ứng dụng bảng tính**. Nếu có trường do người dùng nhập bắt đầu bằng `=`, `+`, `-` hoặc `@`, phần mềm bảng tính có thể diễn giải như công thức tùy ngữ cảnh. Gửi CSV cần thêm bước xử lý an toàn theo mục tiêu sử dụng, không chỉ đặt content type đúng.

### 6.3. JSON

```java
byte[] jsonBytes = """
        {"orderId":"DH1024","status":"PAID"}
        """.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "order.json",
        new ByteArrayResource(jsonBytes),
        "application/json");
```

JSON được chuẩn hóa theo Unicode/UTF-8 trong những cách trao đổi hiện đại; `application/json` là kiểu MIME được sử dụng phổ biến. Việc file được tạo từ Java string vẫn cần đúng encoding khi chuyển thành byte.

### 6.4. ZIP hoặc dữ liệu chưa nhận diện

```java
helper.addAttachment(
        "documents.zip",
        new FileSystemResource(zipPath),
        "application/zip");
```

Khi định dạng không xác định chắc chắn hoặc chủ động gửi dữ liệu nhị phân chung, `application/octet-stream` có thể thích hợp. Tuy nhiên, chọn kiểu chung không khiến một tệp nguy hiểm tự trở nên an toàn và không bỏ qua được chính sách lọc attachment của hệ thống nhận.

## 7. Ví dụ Spring Boot hoàn chỉnh: tạo tên tệp theo nghiệp vụ

Giả sử ứng dụng gửi hóa đơn PDF:

- File trên server được lưu theo mã bất biến hoặc UUID.
- Người nhận muốn thấy `invoice-DH1024.pdf`.
- MIME type phải là `application/pdf`.
- Không truyền đường dẫn từ client trực tiếp vào bộ gửi.
- Chỉ gửi file do ứng dụng có quyền đọc và đã sinh/kiểm tra.

### 7.1. Dependency và cấu hình SMTP

Ví dụ với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

`application.yml` cho submission cổng 587 với STARTTLS:

```yaml
spring:
  mail:
    host: ${MAIL_HOST}
    port: 587
    username: ${MAIL_USERNAME}
    password: ${MAIL_PASSWORD}
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Các biến môi trường được cấp từ hạ tầng triển khai. Đây là ví dụ cho server hỗ trợ STARTTLS trên 587, không phải cấu hình đúng cho mọi SMTP provider. Nhà cung cấp dùng implicit TLS trên 465 cần cấu hình phù hợp với cơ chế đó.

### 7.2. Service gửi hóa đơn

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

@Service
public class InvoiceMailer {

    private static final long MAX_PDF_BYTES = 12L * 1024 * 1024;
    private final JavaMailSender mailSender;

    public InvoiceMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String customerEmail,
            String orderCode,
            Path storedInvoice)
            throws IOException, MessagingException {

        Objects.requireNonNull(customerEmail, "customerEmail");
        Objects.requireNonNull(orderCode, "orderCode");
        Objects.requireNonNull(storedInvoice, "storedInvoice");

        // File path ở đây do tầng lưu trữ tin cậy cung cấp,
        // KHÔNG nhận Path tùy ý trực tiếp từ người dùng.
        if (!Files.isRegularFile(storedInvoice)
                || !Files.isReadable(storedInvoice)) {
            throw new IllegalArgumentException(
                    "Invoice PDF is not a readable file");
        }

        if (Files.size(storedInvoice) > MAX_PDF_BYTES) {
            throw new IllegalArgumentException("Invoice PDF is too large");
        }

        // orderCode là định danh đã được kiểm soát ở tầng nghiệp vụ,
        // ví dụ chỉ gồm [A-Za-z0-9-] và có giới hạn độ dài.
        if (!orderCode.matches("[A-Za-z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid order code");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("billing@example.com", "Bộ phận thanh toán");
        helper.setTo(customerEmail);
        helper.setSubject("Hóa đơn đơn hàng " + orderCode);
        helper.setText(
                "Vui lòng xem hóa đơn PDF đính kèm cho đơn hàng "
                        + orderCode + ".", false);

        String visibleFilename = "invoice-" + orderCode + ".pdf";

        helper.addAttachment(
                visibleFilename,
                new FileSystemResource(storedInvoice),
                "application/pdf");

        mailSender.send(message);
    }
}
```

Đoạn trên minh họa cách kiểm soát **tên hiển thị attachment** từ dữ liệu nghiệp vụ và **kiểu nội dung tường minh**. Trong triển khai thực tế, cần thêm kiểm tra địa chỉ email, xác thực người yêu cầu, quyền tải hóa đơn, tình trạng đơn hàng, kiểm tra định dạng PDF và xử lý lỗi gửi.

Điều đặc biệt quan trọng: **`Files.isRegularFile(...)` và `Files.size(...)` không chứng minh byte của file là PDF**. Với file do ứng dụng tự tạo qua thư viện PDF đáng tin, định dạng có thể được bảo đảm ở bước sinh file. Với file tải lên, phải có quy trình xác minh và kiểm soát nội dung riêng.

### 7.3. Vì sao chọn tên hiển thị từ mã đơn hàng?

Ví dụ file vật lý:

```text
storage/2026-11/3d8df61b-1b79-4eb2-ae2a.bin
```

File có thể được sinh/đặt tên lại bởi bộ lưu trữ và không mang tên gốc. Phần tên trong email được dựng từ mã đơn hàng đã kiểm soát:

```text
invoice-DH1024.pdf
```

Người nhận thấy tên có ý nghĩa mà ứng dụng không phải tiết lộ tên file vật lý hoặc đường dẫn nội bộ. Nếu sử dụng tên khách hàng hoặc số điện thoại trong filename, cần cân nhắc **quyền riêng tư**, vì tên attachment có thể xuất hiện trong bản xem trước, log mail gateway hoặc các hệ thống quét bảo mật.

## 8. Truyền byte trong bộ nhớ: ByteArrayResource và DataSource

Không phải attachment nào cũng được lưu sẵn thành file vật lý. Báo cáo CSV/JSON hoặc tài liệu nhỏ có thể được sinh ngay trong bộ nhớ.

Ví dụ:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;

String csv = "code,total\\r\\nDH1024,120000\\r\\n";
byte[] bytes = csv.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "summary.csv",
        new ByteArrayResource(bytes),
        "text/csv; charset=UTF-8");
```

`ByteArrayResource` giữ byte trong bộ nhớ và cung cấp **InputStream mới khi được yêu cầu**. Đây là đặc điểm hữu ích vì Jakarta Mail có thể đọc nội dung attachment hơn một lần khi tuần tự hóa/gửi.

Tuy nhiên, cách này có nhược điểm:

- Tất cả byte tồn tại trong heap của JVM.
- File lớn hoặc gửi đồng thời nhiều email có thể làm tăng RAM.
- Nếu bạn vô tình tạo nhiều bản sao byte array, áp lực bộ nhớ còn cao hơn.

Với file lớn, dùng `FileSystemResource` hoặc nguồn dữ liệu có thể đọc lại mà không phải tải hết vào RAM thường phù hợp hơn.

### 8.1. Vì sao không nên dùng InputStream chỉ đọc một lần?

Một nguồn như `InputStreamResource` bọc stream đã mở sẵn có thể chỉ cho phép đọc một lần. Trong nhiều luồng Jakarta Mail, nguồn attachment phải **mở stream lại** để ghi/serialize message. Nếu stream bị tiêu thụ, gửi email có thể lỗi hoặc nội dung file không đầy đủ.

Nguyên tắc:

> Đối tượng truyền vào `addAttachment` dạng `InputStreamSource` phải cung cấp được dữ liệu hợp lệ khi thư viện yêu cầu đọc, kể cả khi quá trình tạo/gửi MIME cần mở stream nhiều lần.

Với file vật lý, `FileSystemResource` thường phù hợp. Với byte nhỏ có sẵn, `ByteArrayResource` phù hợp. Với nội dung remote hoặc stream chỉ đọc được một lần, hãy lưu tạm vào một nguồn **có thể đọc lại**, đồng thời áp giới hạn kích thước và vòng đời lưu trữ.

### 8.2. DataSource khi cần kiểm soát nguồn và MIME type

Jakarta Activation có abstraction `DataSource` với các phương thức liên quan:

```java
String getContentType();
String getName();
InputStream getInputStream() throws IOException;
OutputStream getOutputStream() throws IOException;
```

Một `DataSource` có thể cung cấp kiểu nội dung và byte từ nhiều nguồn. Khi dùng:

```java
helper.addAttachment("export.dat", dataSource);
```

ứng dụng nên bảo đảm `dataSource.getContentType()` mô tả đúng định dạng được phép gửi và `getInputStream()` có thể cung cấp dữ liệu phù hợp mỗi khi được gọi. Tham số `attachmentFilename` vẫn thể hiện **tên muốn gửi**, không nhất thiết bằng `dataSource.getName()`.

## 9. Filename và MIME type không xác minh được file

Giả sử có người tải lên một file tên `invoice.pdf` nhưng byte thực là một chương trình thực thi hoặc một tài liệu có mã độc.

Nếu ứng dụng làm:

```java
helper.addAttachment(
        "invoice.pdf",
        uploadedFileResource,
        "application/pdf");
```

thì nó **chỉ gắn nhãn** phần MIME là PDF; nó không biến dữ liệu thành PDF thật và không loại bỏ nội dung nguy hiểm.

### 9.1. Các lớp bảo vệ cần có với file không tin cậy

1. **Giới hạn loại file:** dựa trên mục đích nghiệp vụ, chỉ cho các định dạng được phép.
2. **Kiểm tra kích thước:** áp dụng giới hạn HTTP upload, lưu trữ và **kích thước message sau MIME encoding**.
3. **Kiểm tra định dạng thực tế:** dùng parser hoặc cơ chế xác minh signature/structure phù hợp; kiểm tra magic bytes đơn giản chỉ là bước đầu, không đủ cho mọi định dạng.
4. **Quét bảo mật khi phù hợp:** dùng công cụ/luồng quét tệp theo yêu cầu an toàn của hệ thống.
5. **Lưu trữ và quyền truy cập:** không dùng đường dẫn do client cung cấp trực tiếp để truy xuất file bất kỳ trên server.
6. **Kiểm soát tên hiển thị:** tránh ký tự điều khiển, separator, tên chứa dữ liệu nhạy cảm hoặc đuôi gây hiểu lầm.
7. **Quan sát và xử lý thất bại:** ghi lỗi ở mức thông tin cần thiết, không log toàn bộ attachment.

**Content-Type là dữ liệu mô tả, không phải lớp bảo mật.** Cả hệ thống gửi và hệ thống nhận phải có chính sách thích hợp với file không tin cậy.

### 9.2. Tên file gắn với đường dẫn: nguy cơ path traversal

Trường tên attachment có thể bị sử dụng sai khi một hệ thống **nhận file và lưu trực tiếp theo tên từ email**:

```text
../../private/secret.txt
..\..\windows\system.ini
```

Đối với bên **gửi**, đừng đưa tên chứa đường dẫn hay separator lên header. Đối với bên **nhận**, **không ghép trực tiếp giá trị filename của MIME vào thư mục lưu trữ**. Bên nhận cần chọn tên an toàn, kiểm soát thư mục đích, chống ghi đè và đặt giới hạn kích thước. Những quy tắc ở hai phía độc lập nhưng bổ sung cho nhau.

### 9.3. Ký tự Unicode dễ gây nhầm lẫn

Một filename có thể chứa ký tự giống chữ Latin nhưng thuộc hệ chữ khác, ký tự điều khiển định hướng văn bản, hoặc những dấu phân cách không rõ ràng. Tên hiển thị như vậy có thể làm người dùng hiểu sai extension hoặc bản chất file.

Để giảm rủi ro, tên file được tạo bởi ứng dụng nên có cấu trúc dự đoán được, ít chứa ký tự tự do, đồng thời có chính sách lọc những ký tự điều khiển/định hướng không cần thiết. **Không nên loại bỏ toàn bộ Unicode một cách máy móc** nếu sản phẩm cần hỗ trợ tên tiếng Việt; thay vào đó cần cân nhắc tương thích client và rủi ro của dữ liệu đầu vào.

## 10. Kiểm tra và xây dựng tên file an toàn

Một utility ví dụ để xử lý tên hiển thị do nghiệp vụ tạo:

```java
import java.text.Normalizer;

public final class AttachmentNames {

    private AttachmentNames() {}

    public static String requireSafeDisplayName(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Attachment name is required");
        }

        String name = Normalizer.normalize(
                raw.strip(), Normalizer.Form.NFC);

        if (name.isBlank()) {
            throw new IllegalArgumentException("Attachment name is blank");
        }
        if (name.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException(
                    "Attachment name contains control characters");
        }
        if (name.indexOf('/') >= 0 || name.indexOf('\\') >= 0) {
            throw new IllegalArgumentException(
                    "Attachment name must not contain path separators");
        }
        if (name.equals(".") || name.equals("..")) {
            throw new IllegalArgumentException("Invalid attachment name");
        }
        if (name.codePointCount(0, name.length()) > 120) {
            throw new IllegalArgumentException("Attachment name is too long");
        }

        return name;
    }
}
```

Hàm này:

- Từ chối tên thiếu hoặc trống.
- Chuẩn hóa Unicode theo **NFC** nhằm giảm các dạng biểu diễn tương đương.
- Loại bỏ ký tự điều khiển, bao gồm CR/LF.
- Từ chối dấu phân cách đường dẫn để chỉ gửi **tên file**, không gửi path.
- Áp giới hạn 120 code point như **chính sách sản phẩm minh họa**.

Hàm **không xác thực loại file**, không phát hiện mọi kiểu spoofing Unicode và không đủ thay thế chính sách file upload/scan. Tùy môi trường và hệ điều hành nhận, có thể cần những quy tắc bổ sung cho tên thiết bị đặc biệt hoặc ký tự bị cấm.

Sử dụng:

```java
String filename = AttachmentNames.requireSafeDisplayName(
        "Hóa đơn tháng 11.pdf");

helper.addAttachment(
        filename,
        new FileSystemResource(invoicePath),
        "application/pdf");
```

### 10.1. Có nên lấy filename từ HTTP upload?

Giả sử người dùng gửi `MultipartFile` lên API. Tên từ `getOriginalFilename()` là **dữ liệu do client cung cấp**, có thể thiếu, không đáng tin hoặc chứa dấu phân cách đường dẫn. Không nên đưa thẳng giá trị này vào file system hoặc `addAttachment` mà không có chính sách.

Với ứng dụng chuyển tiếp attachment, quy trình phù hợp có thể là:

1. Xác thực người dùng và quyền gửi file.
2. Kiểm soát giới hạn HTTP request và kích thước file.
3. Kiểm tra nội dung thực tế và loại file cho phép.
4. Lưu byte dưới **tên nội bộ được tạo bởi server**.
5. Tạo một filename hiển thị đã được làm sạch, hoặc tạo lại tên từ dữ liệu nghiệp vụ.
6. Gắn MIME type chính xác từ kết quả phân loại/định dạng đáng tin.
7. Gửi qua worker, theo dõi lỗi và dọn file tạm theo vòng đời.

**Không coi `getContentType()` từ HTTP upload là nguồn tin cậy tuyệt đối.** Header `Content-Type` của request do phía client gửi có thể sai hoặc bị giả mạo.

## 11. Attachment khác với inline image

Một email có thể có hai hình thức đưa tài nguyên:

### 11.1. Attachment để tải về

```java
helper.addAttachment(
        "company-logo.png",
        new ClassPathResource("mail/logo.png"),
        "image/png");
```

Email client thường hiển thị logo như một file có thể tải về.

### 11.2. Inline để HTML tham chiếu

```java
helper.setText(
        "Thông báo từ công ty.",
        "<p>Thông báo từ công ty.</p>"
                + "<img src=\"cid:company-logo\" alt=\"Logo\">");

helper.addInline(
        "company-logo",
        new ClassPathResource("mail/logo.png"),
        "image/png");
```

Với inline:

- `company-logo` là **Content-ID logic** để HTML tham chiếu bằng `cid:company-logo`.
- `image/png` mô tả **loại nội dung**.
- Hình thường được đặt trong cấu trúc `multipart/related`.
- Tên hiển thị kiểu attachment **không phải mục tiêu chính** của `addInline`.

Nên gọi **`setText(...)` trước `addInline(...)`** để các email client dễ nhận diện quan hệ giữa HTML và hình. Với thư chứa cả inline resources và file đính kèm, chế độ `MULTIPART_MODE_MIXED_RELATED` là một lựa chọn phù hợp.

Ví dụ:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message, MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED, "UTF-8");
```

Không nên nhầm rằng chỉ đổi `Content-Disposition` của một attachment thành `inline` là đã thiết lập đầy đủ tham chiếu CID trong HTML.

## 12. Tên file ảnh hưởng đến cách người nhận sử dụng attachment

Tên file là một phần trải nghiệm sản phẩm, không chỉ là yêu cầu của giao thức.

Ví dụ một người nhận được ba file:

```text
file1.pdf
file2.pdf
file3.pdf
```

so với:

```text
invoice-DH1024.pdf
payment-receipt-DH1024.pdf
delivery-note-DH1024.pdf
```

Nhóm thứ hai dễ hiểu và dễ lưu trữ hơn. Khi đặt tên:

- Dùng thuật ngữ quen thuộc với người nhận, không lộ key nội bộ.
- Bổ sung mã đơn hàng hoặc kỳ báo cáo nếu cần phân biệt.
- Giữ tên ngắn và tránh thông tin cá nhân nhạy cảm.
- Không đặt tên ngụ ý file đã được mã hóa/bảo vệ nếu thực tế chưa có.
- Giữ extension nhất quán với MIME type và nội dung thực tế.
- Tránh ký tự khó tương thích nếu đối tượng nhận dùng nhiều hệ thống email cũ.

### 12.1. Một thư có nhiều attachment

```java
helper.addAttachment(
        "invoice-DH1024.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");

helper.addAttachment(
        "orders-DH1024.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8");
```

Mỗi attachment có **tên**, **nguồn byte** và **content type** riêng. Không được giả định tất cả part của một message sẽ dùng cùng `Content-Type`. Nếu tên trùng nhau, một số client vẫn cho phép lưu nhưng có thể hỏi đổi tên hoặc gây nhầm lẫn; vì vậy nên tạo tên đủ phân biệt.

## 13. Kích thước attachment khác kích thước email

Ngay cả khi tên và content type đúng, email vẫn có thể bị server SMTP từ chối vì quá lớn.

Tệp nhị phân thường được biểu diễn bằng base64 trong MIME. Cứ **3 byte** dữ liệu gốc trở thành **4 ký tự base64**, sau đó còn có ký tự xuống dòng, header và multipart boundary. Với tệp lớn, tổng kích thước base64 MIME thường xấp xỉ **1,37 lần** kích thước byte ban đầu.

Ví dụ minh họa:

| Kích thước file gốc | Dung lượng phần base64 MIME ước tính |
|---:|---:|
| 1 MiB | Khoảng 1,37 MiB |
| 10 MiB | Khoảng 13,68 MiB |
| 20 MiB | Khoảng 27,37 MiB |

Con số chưa cộng toàn bộ header, HTML, text và những MIME part khác. Vì vậy, nhà cung cấp quảng cáo “message tối đa 25 MiB” **không có nghĩa có thể đính kèm file 25 MiB**.

Trong Spring Boot:

- `spring.servlet.multipart.max-file-size` kiểm soát **file upload qua HTTP servlet**, không giới hạn SMTP message.
- `MimeMessageHelper` giúp gắn file vào MIME, **không tự bảo đảm file dưới trần dung lượng của provider**.
- Ứng dụng cần giới hạn file gốc, tổng file, dung lượng MIME dự kiến và số recipient phù hợp.
- Với tài liệu quá lớn, **gửi liên kết tải được phân quyền và có thời hạn** thường thích hợp hơn attachment.

Không cần tự base64-encode file trước khi gọi `addAttachment`: Jakarta Mail xử lý transfer encoding phù hợp khi tạo message. Tự mã hóa trước có thể khiến người nhận tải về nội dung base64 thay vì file gốc hoặc khiến MIME bị mã hóa lặp.

## 14. Chẩn đoán các lỗi về tên và kiểu nội dung

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Người nhận thấy tên như `=?UTF-8?B?...?=` | Cách mã hóa filename không được client giải mã, hoặc mã hóa không đúng ngữ cảnh | Kiểm tra header MIME thực tế, RFC 2231/RFC 2047 và lựa chọn mã hóa của thư viện. |
| Tên file tiếng Việt bị lỗi dấu | Charset/parameter encoding hoặc client không hỗ trợ đúng | Tạo tên logic Unicode, dùng API của thư viện, thử tên ASCII dự phòng khi cần. |
| File hiện tên UUID hoặc đường dẫn nội bộ | Lấy tên file lưu trữ làm tên hiển thị | Truyền `attachmentFilename` từ dữ liệu nghiệp vụ an toàn. |
| File PDF hiện như dữ liệu nhị phân chung | Content type không được xác định hoặc mapping không nhận ra | Đặt `application/pdf` tường minh khi biết file thật là PDF. |
| Email client nhận file nhưng không mở được | Nội dung file hỏng, sai loại dữ liệu hoặc nguồn stream bị tiêu thụ | Kiểm tra byte gốc và nguồn có thể đọc lại; không chỉ đổi extension. |
| Ảnh không xuất hiện trong HTML | Dùng `addAttachment` thay cho `addInline`, `cid:` sai hoặc client chặn ảnh | Kiểm tra Content-ID, `addInline` và cấu trúc related. |
| Attachment thiếu dữ liệu khi gửi | `InputStreamSource` không thể mở lại hoặc file thay đổi trong lúc gửi | Dùng nguồn bất biến có thể đọc lại, bảo đảm vòng đời file. |
| Mail bị từ chối `552 5.3.4` | MIME message vượt giới hạn server | Ước lượng/đo kích thước email sau mã hóa, giảm file hoặc gửi link. |
| Mail bị chặn dù file nhỏ | Chính sách chống phần mềm độc hại, loại file hoặc MIME mismatch | Xem phản hồi SMTP/provider; không cố vượt bộ lọc bằng đổi đuôi. |
| Ghi file nhận về tạo đường dẫn bất thường | Hệ thống nhận dùng filename MIME như đường dẫn | Làm sạch và tạo đường dẫn lưu trữ an toàn ở phía nhận. |

### 14.1. Có nên xem raw MIME header khi chẩn đoán?

Có thể cần trong môi trường kiểm soát, đặc biệt khi tên Unicode hiển thị sai. Những header cần quan sát:

```text
Content-Type
Content-Disposition
Content-Transfer-Encoding
Content-ID
```

Tuy nhiên, bản email MIME có thể chứa **địa chỉ cá nhân, nội dung bí mật, token và attachment**. Không bật chế độ log toàn bộ message trong production một cách thường trực. Chỉ thu thập metadata cần thiết, che thông tin nhạy cảm và hạn chế thời gian lưu trữ.

### 14.2. Thành công ở `send(...)` nói lên điều gì?

`JavaMailSender.send(message)` hoàn thành nghĩa là transport không báo lỗi tại thời điểm gửi. Nó **không bảo đảm email đã tới Inbox**. File có thể bị từ chối ở cổng lọc của hệ thống người nhận sau khi SMTP submission server đã tiếp nhận thư.

Nếu cần theo dõi kết quả cuối, hệ thống phải xử lý **bounce/DSN** hoặc sự kiện provider riêng. Lỗi tên filename trong email client cũng có thể chỉ là vấn đề hiển thị, không đồng nghĩa SMTP đã thất bại.

## 15. Bài tập thực hành

### Bài 1: Tách tên hiển thị và nguồn dữ liệu

Ứng dụng lưu hóa đơn tại:

```text
/srv/files/2026/11/9e2b48dd-3d20-4a4a-9831.pdf
```

Nhưng người dùng cần thấy:

```text
hoa-don-DH1024.pdf
```

Hãy viết lời gọi `addAttachment(...)` dùng `FileSystemResource` với tên và content type chính xác. Giải thích vì sao không nên gửi nguyên đường dẫn lên header.

### Bài 2: Content-Type có phải bằng chứng an toàn?

Một file người dùng upload có tên `invoice.pdf` và HTTP `Content-Type: application/pdf`. Có đủ căn cứ để đính kèm file đó như PDF đáng tin hay chưa? Nêu các bước cần làm trước khi gửi.

### Bài 3: Tên tiếng Việt

Khách hàng muốn nhận file `Hóa đơn tháng 11.pdf`. Hãy giải thích sự khác biệt giữa RFC 2231 và RFC 2047, vì sao chỉ đặt charset của text body là chưa đủ và khi nào nên cân nhắc tên ASCII dự phòng.

### Bài 4: CSV trong bộ nhớ

Hãy tạo một `byte[]` chứa CSV UTF-8, dùng `ByteArrayResource` và truyền content type phù hợp cho `helper.addAttachment(...)`. Vì sao `ByteArrayResource` có thể phù hợp hơn nguồn chỉ cho phép đọc một lần?

### Bài 5: Logo inline và PDF đính kèm

Một thư HTML phải hiển thị logo ở đầu nội dung, trong khi hóa đơn cần xuất hiện dưới dạng tệp tải về. Hãy lựa chọn giữa `addInline` và `addAttachment` cho từng tài nguyên, chỉ rõ `cid:` tương ứng và chọn chế độ multipart.

### Bài 6: File quá lớn

SMTP server công bố giới hạn message 25 MiB, ứng dụng muốn gửi PDF 20 MiB. Hãy ước lượng dung lượng riêng phần base64, giải thích vì sao không thể so sánh trực tiếp 20 MiB với 25 MiB và đề xuất giải pháp phân phối thay thế.

### Bài 7: Tên lấy từ người dùng

Đầu vào tên file chứa `../../records/private.pdf` hoặc ký tự CR/LF. Hãy nêu cách kiểm soát `attachmentFilename` ở phía gửi và tại sao phía nhận cũng phải xử lý filename như dữ liệu không tin cậy.

## 16. Tổng kết

Trong **Spring Framework Mail**, khi dùng `MimeMessageHelper.addAttachment(...)`, hãy chủ động phân biệt:

1. **Tên attachment**: chuỗi hiển thị cho người nhận, không nhất thiết trùng với tên file hoặc đường dẫn lưu trữ nội bộ.
2. **Content-Type**: mô tả loại dữ liệu MIME như `application/pdf`, `text/csv` hoặc `image/png`, nhưng **không xác minh file an toàn**.
3. **Nguồn dữ liệu**: byte thực lấy từ `FileSystemResource`, `ByteArrayResource` hoặc `DataSource`; nguồn phải đọc được đúng lúc tạo/gửi email và có thể đọc lại khi thư viện yêu cầu.
4. **Content-Disposition**: phân biệt phần đính kèm với nội dung hiển thị inline; `addInline` còn liên quan Content-ID và `cid:`.
5. **Encoding và kích thước**: filename Unicode cần mã hóa tham số MIME thích hợp, còn dữ liệu attachment thường được transfer-encode bằng base64, làm tăng dung lượng message.

Đối với hệ thống sản xuất, **tên file nên được tạo/kiểm soát từ nghiệp vụ**, MIME type nên dựa trên định dạng đã xác định, dữ liệu không tin cậy cần được kiểm tra và dung lượng phải phù hợp chính sách SMTP provider. `MimeMessageHelper` giúp tạo cấu trúc MIME, nhưng trách nhiệm xác minh file, giới hạn quyền gửi, quản lý secret và theo dõi chuyển phát vẫn thuộc ứng dụng.

### Tài liệu để đọc sâu

- **Spring Framework API — `MimeMessageHelper`:** `addAttachment`, `addInline`, `setEncodeFilenames`, lựa chọn multipart và quản lý MIME.
- **Spring Framework Reference — Email:** gửi MIME email, tệp đính kèm và tài nguyên inline.
- **Jakarta Mail API:** `MimeMessage`, `MimeBodyPart`, `DataSource`, `FileTypeMap` và các thuộc tính MIME liên quan.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** cấu trúc MIME, body parts và transfer encoding.
- **RFC 2183 — Communicating Presentation Information in Internet Messages:** `Content-Disposition` và tham số filename.
- **RFC 2231 — MIME Parameter Value and Encoded Word Extensions:** encoding và continuation của tham số MIME quốc tế hóa.
- **RFC 2047 — MIME Header Extensions for Non-ASCII Text:** encoded-word trong những ngữ cảnh header cho phép.
- **RFC 5322 — Internet Message Format:** cú pháp header email và folding.

Một email attachment đúng không chỉ là “gắn được file vào mail”: nó cần **tên dễ hiểu, loại MIME phù hợp, dữ liệu đọc được, cấu trúc đúng và chính sách an toàn rõ ràng**.
