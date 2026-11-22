# Chi phí tạo MIME và mã hóa attachment

Khi gửi một email text ngắn, ứng dụng Spring Framework Mail thường chỉ cần tạo `MimeMessage`, đặt địa chỉ, chủ đề, nội dung rồi gọi `JavaMailSender.send(...)`. Nhưng nếu email có HTML, ảnh inline, nhiều tệp PDF hoặc các attachment lớn, chi phí không còn nằm riêng ở một lệnh gửi. Ứng dụng phải dựng cấu trúc MIME, đọc nguồn dữ liệu, mã hóa từng phần để phù hợp giao thức email, truyền lượng byte lớn hơn tệp gốc qua SMTP và chờ mail server tiếp nhận.

**Chi phí tạo MIME và mã hóa attachment** cần được nhìn đồng thời ở bốn nguồn lực: **CPU, bộ nhớ, I/O và thời gian giữ worker**. Ví dụ một PDF 25 MiB, khi được truyền bằng Base64 có xuống dòng chuẩn MIME, có thể tạo khoảng 34,2 MiB nội dung mã hóa chỉ riêng phần attachment. Nếu đồng thời gửi hàng chục email, mỗi email chứa một PDF có kích thước như vậy, bottleneck có thể nằm ở việc tạo PDF, giữ `byte[]`, đọc đĩa, Base64 encoding, băng thông hay giới hạn SMTP server.

Bài học thuộc chương **Hiệu năng và giới hạn** của **Spring Framework Mail** này giải thích vòng đời MIME, cách ước lượng kích thước, sự khác nhau giữa các loại `Resource`, những tình huống phát sinh bản sao dữ liệu trong heap, các chiến lược giới hạn concurrency và phương pháp đo hiệu năng mà không làm lộ nội dung email.

## 1. Mục tiêu học tập

Sau bài này, người học cần có khả năng:

1. Mô tả đường đi từ nội dung ứng dụng đến `MimeMessage` và SMTP `DATA`.
2. Ước lượng độ tăng kích thước khi attachment dùng Base64 và MIME line folding.
3. Phân biệt **kích thước tệp nguồn**, **kích thước MIME serialized** và **lượng byte trên đường truyền**.
4. Giải thích tại sao tạo `MimeMessageHelper` không nhất thiết đã đọc hoặc mã hóa toàn bộ attachment.
5. Chọn giữa `ByteArrayResource`, `FileSystemResource` và `InputStreamSource` theo đặc tính dữ liệu.
6. Tránh giữ nhiều bản sao tệp lớn trong heap hoặc giữ stream không còn sử dụng được.
7. Xác định giới hạn message size, số attachment và concurrency trước khi gửi.
8. Thiết kế đo đạc đủ để phân biệt bottleneck CPU, I/O, SMTP và GC.
9. Nhận biết trade-off khi gửi một message cho nhiều recipient hoặc nhiều message riêng.
10. Tránh các tối ưu làm giảm độ tin cậy, lộ thông tin hoặc phát sinh duplicate email.

## 2. Vòng đời tạo và gửi một MIME message

Một email HTML có attachment thường đi qua những bước:

```text
Business data
    |
    v
Render text / HTML template
    |
    v
Create MimeMessage + MimeMessageHelper
    |
    +--> Create multipart containers
    +--> Set headers / plain text / HTML
    +--> Attach InputStreamSource or Resource
    |
    v
Prepare / serialize MIME
    |
    +--> Read attachment/inline bytes
    +--> Encode (often Base64 for binary)
    +--> Write boundary / headers / CRLF
    |
    v
SMTP connection / EHLO / AUTH / MAIL / RCPT
    |
    v
SMTP DATA: transfer MIME bytes
    |
    v
Wait for final SMTP response
```

Các bước trên có thể bị xen kẽ hoặc được thư viện thực hiện theo cách khác nhau tùy implementation. Đặc biệt, `MimeMessageHelper.addAttachment(...)` chủ yếu **gắn nguồn nội dung vào MIME part**; đừng mặc định ngay tại lệnh này toàn bộ byte đã được tải, Base64 hóa và lưu vào một `String`.

Khi `JavaMailSenderImpl` giao message cho Jakarta Mail transport, MIME được chuẩn bị/serialize để gửi; attachment có thể được đọc lúc phát nội dung ra stream. Cách cấp nguồn dữ liệu vì vậy ảnh hưởng trực tiếp đến bộ nhớ, số lần đọc, độ trễ và khả năng retry.

### Phân biệt các giai đoạn đo hiệu năng

| Giai đoạn | Phần việc chính | Chi phí thường gặp |
| --- | --- | --- |
| **Generate** | Tạo PDF/CSV/ảnh hoặc lấy file từ storage | CPU, heap, đĩa, mạng |
| **Render** | Dựng text và HTML bằng template | CPU, allocation, truy vấn dữ liệu |
| **Compose** | Tạo `MimeMessage`, MIME tree và headers | Object allocation, validation |
| **Encode/serialize** | Đọc bytes, mã hóa attachment, tạo MIME wire representation | CPU, read I/O, output bytes |
| **Submit** | Kết nối và truyền SMTP | Network latency, bandwidth, timeout |
| **Record outcome** | Cập nhật status trong database | Transaction/I/O ngắn |

Nếu chỉ đo thời gian của `new MimeMessageHelper(...)`, sẽ bỏ sót chi phí đọc và mã hóa attachment lúc `send`. Nếu chỉ đo `send`, nó lại có thể gộp cả serialization, I/O mạng và chờ SMTP server.

## 3. MIME là một container, không phải chỉ có HTML

Một email có hai bản nội dung, ảnh inline và attachment thường có cấu trúc:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   ├── image/png; disposition=inline
    │   └── image/jpeg; disposition=inline
    ├── application/pdf; disposition=attachment
    └── text/csv; disposition=attachment
```

Mỗi MIME part có thể mang:

- `Content-Type` và một số parameter như charset hoặc name.
- `Content-Transfer-Encoding`.
- `Content-Disposition` và filename.
- `Content-ID` với phần inline.
- Phần dữ liệu đã được biểu diễn theo encoding phù hợp.
- Boundary và CRLF để phân tách với các part khác.

Như vậy, kích thước message không phải chỉ bằng:

```text
html.length + attachmentFile.length
```

mà còn phụ thuộc charset, transfer encoding, headers, số part, boundary, filenames và cách serialize của thư viện.

## 4. Vì sao attachment nhị phân thường dùng Base64?

MIME phải biểu diễn dữ liệu nhị phân trong một dạng thích hợp với hệ thống thư điện tử. Base64 chuyển từng nhóm ba byte thành bốn ký tự ASCII. Các tệp như PDF, PNG, JPEG, XLSX, ZIP thường có nội dung nhị phân và được gửi dưới dạng một MIME part có:

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64
```

Điểm quan trọng:

- Base64 **là encoding, không phải compression**.
- Base64 **không mã hóa bảo mật**; người có raw MIME có thể giải mã nội dung.
- Base64 **làm tăng kích thước** byte truyền đi.
- Ghi `Content-Type: application/pdf` không có nghĩa file được giảm kích thước hoặc được kiểm tra là PDF hợp lệ.
- Mỗi attachment thường là một MIME part riêng, chịu overhead riêng.

### Công thức kích thước Base64 trước khi xuống dòng

Với `N` byte đầu vào, số ký tự Base64:

\[
B(N) = 4\left\lceil\frac{N}{3}\right\rceil
\]

Ví dụ 3 byte cần 4 ký tự; 4 byte cần 8 ký tự vì nhóm cuối được padding.

Nếu `N` đủ lớn và chia hết cho 3, hệ số xấp xỉ:

\[
\frac{B(N)}{N}\approx\frac{4}{3}=1{,}3333.
\]

Tức là chỉ riêng Base64 đã tăng khoảng **33,3%** so với byte nguồn. Với tệp nhỏ, padding có thể khiến tỷ lệ cao hơn.

## 5. MIME line folding làm kích thước tăng thêm

Base64 trong MIME thường được chia dòng, với độ dài một dòng tối đa 76 ký tự theo cách biểu diễn chuẩn MIME. Dòng được ngăn bằng `CRLF` (2 byte).

Với một nhóm đủ lớn:

```text
57 byte dữ liệu gốc
       |
       v
76 ký tự Base64
       |
       v
76 ký tự + CRLF 2 byte
       |
       v
78 byte nội dung MIME
```

Hệ số gần đúng:

\[
\frac{78}{57}\approx1{,}3684.
\]

Đối với tệp lớn, **kích thước body Base64 có gấp dòng thường lớn hơn khoảng 36,8%** so với tệp gốc. Header và boundary của MIME part còn được cộng thêm.

### Công thức ước lượng thực dụng

Gọi `C=4×ceil(N/3)` là số ký tự Base64. Nếu mỗi dòng tối đa 76 ký tự, số dòng xấp xỉ `L=ceil(C/76)`. Ước lượng có tính cả kết thúc dòng:

\[
E(N)\approx C+2L.
\]

Đây là **ước lượng** vì cách thư viện đặt CRLF cuối part, boundary tiếp theo và những bytes metadata khác có thể làm kích thước thực khác một chút.

### Bảng kích thước tham khảo

| Kích thước nhị phân | Base64 chưa gấp dòng | Base64 MIME có CRLF, xấp xỉ | Phần tăng thêm xấp xỉ |
| --- | ---: | ---: | ---: |
| 1 MiB | 1,33 MiB | 1,37 MiB | 0,37 MiB |
| 5 MiB | 6,67 MiB | 6,84 MiB | 1,84 MiB |
| 10 MiB | 13,33 MiB | 13,68 MiB | 3,68 MiB |
| 20 MiB | 26,67 MiB | 27,37 MiB | 7,37 MiB |
| 25 MiB | 33,33 MiB | 34,21 MiB | 9,21 MiB |

`MiB` là `1.048.576` byte, khác với `MB` bằng `1.000.000` byte. Đây là kích thước **ước lượng của phần nội dung attachment Base64**, chưa bao gồm toàn bộ email, một số header/boundary và SMTP framing.

**Đừng lấy ngưỡng “25 MB attachment” của provider và cho rằng có thể gửi một tệp nguồn đúng 25 MB.** Provider có thể giới hạn kích thước toàn message sau encoding; ngưỡng, cách đo và phần overhead phải xem theo tài liệu provider.

## 6. Một message có nhiều attachment sẽ có bao nhiêu byte?

Giả sử:

- PDF 8 MiB.
- Ảnh PNG 2 MiB.
- Tệp CSV 1 MiB.
- Nội dung text/HTML tổng cộng khoảng 100 KiB trước khi mã hóa.

Ba attachment có tổng 11 MiB nhị phân. Nếu mỗi tệp được Base64 với MIME folding, body attachment đã khoảng:

\[
11\times1{,}3684\approx15{,}05\ \text{MiB}.
\]

Cộng thêm HTML/text, các MIME part headers, boundary, filename, inline data và những gì relay yêu cầu, message có thể vượt 15 MiB.

Khi một message gần ngưỡng server:

1. Đừng chỉ cộng kích thước file gốc.
2. Hãy tính conservative upper bound của các part lớn.
3. Dành một khoảng đệm cho MIME headers/body.
4. Với trường hợp biên, serialize một **message test dùng dữ liệu giả** để đo byte thực, sau đó kiểm tra với SMTP test server.
5. Vẫn phải xử lý lỗi `SIZE` hoặc `552` do provider trả về, vì client estimate không phải cam kết server sẽ chấp nhận.

## 7. Ảnh inline cũng có chi phí như attachment

Một logo được thêm bằng:

```java
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
```

có thể trở thành part nhị phân Base64 trong `multipart/related`. Dù mail client hiển thị logo **bên trong HTML**, byte ảnh vẫn đi cùng message:

```html
<img src="cid:brand-logo" alt="Brand">
```

Nếu cùng một ảnh có kích thước 500 KiB được nhúng vào 20.000 email riêng, lượng byte ở tầng SMTP có thể đáng kể:

```text
500 KiB source image
      x Base64 + folding (~1.368)
      x 20,000 messages
      = khoảng 13.1 GiB encoded inline-image payload
```

Đó mới là riêng ảnh, chưa có body và các part khác. Với email số lượng lớn, tối ưu kích thước ảnh, dùng đúng định dạng và tránh gửi tài nguyên không cần thiết có thể hiệu quả hơn tối ưu vài dòng Java.

**Đổi ảnh inline thành ảnh host bên ngoài** có thể giảm payload SMTP nhưng chuyển chi phí sang request HTTP, phụ thuộc client có tải ảnh hay không và phát sinh vấn đề về quyền riêng tư/tracking, URL có hạn sử dụng, bảo mật host và trải nghiệm offline. Đây là trade-off sản phẩm, không phải tối ưu “miễn phí”.

## 8. Base64 không phải chi phí duy nhất của nội dung text

`text/plain` và `text/html` có thể dùng:

- `7bit`, nếu nội dung phù hợp.
- `quoted-printable`, thường thuận tiện khi phần lớn là ký tự ASCII và chỉ có ít byte cần encode.
- `base64`, tùy nội dung và implementation.
- Những cách biểu diễn khác nếu SMTP capability và cấu hình cho phép.

Một email HTML dài với nhiều ký tự Unicode có thể tạo payload trên wire khác đáng kể so với số ký tự Java `String.length()`. `String.length()` đếm code unit UTF-16, không phải số byte UTF-8, cũng không phải số byte MIME.

Ví dụ:

```java
String text = "Hóa đơn số 123 – cảm ơn bạn";

int utf16CodeUnits = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
```

Hai số có thể khác nhau. MIME encoded bytes lại là con số thứ ba.

Trong đa số email có PDF/ảnh lớn, attachment Base64 chiếm phần lớn payload; nhưng trong chiến dịch hàng trăm nghìn email chỉ có HTML, kích thước template, CSS inline và URL tracking cũng ảnh hưởng đáng kể đến tổng băng thông.

## 9. ByteArrayResource: đơn giản nhưng cần xét heap

Trong Spring, `ByteArrayResource` rất tiện cho dữ liệu đã có trong memory:

```java
byte[] pdfBytes = pdfGenerator.generate(orderId);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Lợi ích:

- Không cần tạo file tạm.
- `getInputStream()` trả một `ByteArrayInputStream` mới, có thể đọc lại dữ liệu.
- Dễ viết unit test với `assertArrayEquals` trên nội dung decoded.
- Phù hợp với attachment nhỏ hoặc API vốn đã trả `byte[]`.

Nhưng trong trường hợp này, **toàn bộ PDF đã nằm trong heap** dưới dạng `byte[]` trước khi thêm vào message.

Nếu mỗi PDF là 20 MiB và có 20 tác vụ gửi đang giữ mỗi tác vụ một mảng riêng, chỉ các mảng PDF gốc đã có thể giữ khoảng 400 MiB heap, chưa tính:

- Dữ liệu đầu vào của bộ tạo PDF.
- Buffer và object dùng trong quá trình tạo PDF.
- HTML/text render và MIME tree.
- Buffer trong quá trình serialize hoặc I/O.
- Các bản sao nếu code dùng `toByteArray()` hoặc copy mảng.
- Dữ liệu của request, DB entity, worker queue và logging.

### ByteArrayResource có luôn nhân đôi byte[] không?

Không nên khẳng định rằng `new ByteArrayResource(pdfBytes)` **luôn** copy toàn bộ mảng. Vấn đề chính là ứng dụng **đã tạo một mảng lớn** để biểu diễn tệp. Các bước khác trước và sau đó có thể tiếp tục tạo buffer hoặc bản sao, tùy cách triển khai.

Ví dụ:

```java
ByteArrayOutputStream output = new ByteArrayOutputStream();
pdfGenerator.writeTo(output);

byte[] pdf = output.toByteArray();
ByteArrayResource resource = new ByteArrayResource(pdf);
```

Ở đây `ByteArrayOutputStream` có buffer nội bộ; `toByteArray()` tạo một mảng mới. Trong thời gian các object còn sống, hai vùng byte có thể cùng tồn tại. Đó là chi phí **do cách tạo dữ liệu**, không phải chứng cứ riêng rằng `MimeMessageHelper` giữ một bản Base64 đầy đủ trong heap.

## 10. FileSystemResource: tránh chủ động giữ toàn bộ tệp trong memory

Khi attachment đã tồn tại trên filesystem, có thể truyền resource thay vì đọc file thành mảng:

```java
Path pdfPath = Paths.get("/safe-mail-temp", "invoice-123.pdf");

helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(pdfPath),
        "application/pdf"
);
```

Với `FileSystemResource`, thư viện có thể mở stream đọc tệp khi cần phát dữ liệu MIME. Cách này **không bắt buộc ứng dụng chủ động giữ toàn bộ tệp trong một `byte[]`**.

### So sánh luồng dữ liệu

```text
ByteArrayResource
-----------------
Generate PDF -> byte[] in heap
                      |
                      v
             ByteArrayResource
                      |
                      v
                MIME serialization
                      |
                      v
                    SMTP

FileSystemResource
------------------
Generate PDF -> file on disk
                      |
                      v
               FileSystemResource
                      |
                      v
           Stream/read during MIME output
                      |
                      v
                    SMTP
```

Sự khác biệt không chỉ là “file nhanh hơn mảng”. Cả hai có trade-off:

| Tiêu chí | `ByteArrayResource` | `FileSystemResource` |
| --- | --- | --- |
| Dữ liệu nguồn | Đã nằm trong `byte[]` | Nằm trên filesystem |
| Heap trước send | Có thể lớn theo kích thước tệp | Thường không cần mảng chứa toàn bộ file |
| I/O thêm | Không cần đọc đĩa khi truyền | Cần đọc filesystem |
| Khả năng đọc lại | Tốt với mảng còn sống | Tốt nếu file còn tồn tại, không bị thay đổi |
| Vòng đời | Theo object/GC | Phải quản lý file và quyền truy cập |
| Phù hợp | Attachment nhỏ, dữ liệu từ memory | Attachment lớn, file đã sinh sẵn hoặc lưu tạm |
| Rủi ro | Heap pressure, giữ nhiều byte[] | Hết dung lượng đĩa, file mất, cleanup sớm |

**Không có loại resource nào luôn tốt hơn.** Nếu nguồn dữ liệu ban đầu đã là một tệp ổn định, đọc toàn bộ vào `byte[]` chỉ để tạo email có thể là một lần cấp phát không cần thiết. Nếu chỉ có một nội dung nhỏ vài KiB, tạo file tạm để tránh mảng lại có thể tăng I/O và độ phức tạp không đáng có.

### File tạm phải còn tồn tại đến khi nào?

`addAttachment(...)` thường không đồng nghĩa attachment đã được đọc hết. Vì vậy:

```java
Path file = generatePdfToTempFile();
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(file),
        "application/pdf"
);
Files.delete(file);  // Sai: có thể xóa trước khi serialize/send.
```

Khi worker chưa gửi, file có thể cần được đọc sau đó. File tạm phải được giữ đủ lâu để quá trình serialize/send hoàn tất hoặc khi hệ thống quyết định không gửi nữa; cách quản lý phụ thuộc vòng đời task và cơ chế retry.

## 11. InputStreamSource: điều kiện quan trọng là đọc lại được

`MimeMessageHelper.addAttachment(...)` hỗ trợ `InputStreamSource`. Giao diện này có method trả `InputStream`, nhưng cần hiểu kỳ vọng của Spring Mail/Jakarta Mail: **nguồn dữ liệu nên cho phép mở một stream mới mỗi lần được yêu cầu**.

Ví dụ một source tạo stream từ file:

```java
InputStreamSource source = () ->
        Files.newInputStream(
                Paths.get("/safe-mail-temp", "invoice-123.pdf")
        );

helper.addAttachment(
        "invoice.pdf",
        source,
        "application/pdf"
);
```

Mỗi lời gọi `getInputStream()` mở một stream mới. Điều đó khác với việc giữ sẵn một stream duy nhất:

```java
InputStream alreadyOpen = Files.newInputStream(path);

InputStreamSource problematic = () -> alreadyOpen;

// Không nên: lần đọc sau có thể nhận stream đã tiêu thụ/đóng.
helper.addAttachment(
        "invoice.pdf",
        problematic,
        "application/pdf"
);
```

### Vì sao Jakarta Mail có thể cần đọc nhiều lần?

Quá trình chuẩn bị MIME, `saveChanges()`, `writeTo(...)` và transport send có thể tương tác với dữ liệu ở các thời điểm khác nhau. Một số trường hợp cần kiểm tra content type, encoding hoặc serialize lặp lại trong test/retry.

Vì thế, một nguồn chỉ đọc một lần có thể:

- Hoạt động ở một đường đi rồi thất bại ở đường đi khác.
- Trả stream đã ở cuối file, tạo attachment rỗng.
- Ném exception do stream đã đóng.
- Khó retry nếu worker đã tiêu thụ dữ liệu.

`InputStreamResource` thường đại diện cho một stream đã mở, có tính chất single-use; không nên coi nó như một resource tự động đọc lại được. Nếu cần stream nhiều lần, hãy dùng `FileSystemResource`, `ByteArrayResource` hoặc một `InputStreamSource` mở stream mới theo yêu cầu.

## 12. Không đồng nhất streaming với “zero memory”

Streaming giúp tránh giữ toàn bộ tệp trong một mảng, nhưng **không có nghĩa SMTP send không dùng bộ nhớ**.

Ngay cả khi dùng `FileSystemResource`:

- Jakarta Mail và Java có thể có buffer đọc/ghi.
- TLS socket có buffer riêng.
- MIME object và headers vẫn tồn tại trên heap.
- Template rendering có thể tạo String lớn.
- Một số provider/layer có thể buffer hoặc transform dữ liệu.
- Thư viện có thể đọc resource nhiều lần tùy đường thực thi.

Mục tiêu thực tế là **giảm bộ nhớ phụ thuộc tuyến tính vào tổng kích thước file đang chờ**:

```text
Không kiểm soát:
heap ~ attachment bytes x số task đồng thời + các buffer khác

Streaming hợp lý:
heap ~ MIME objects + bounded buffers x số task đồng thời
       (attachment được đọc từ nguồn ngoài heap khi cần)
```

Đây là mô hình khái niệm, không phải công thức chính xác về hành vi cấp phát của mọi phiên bản Spring/Jakarta Mail. Hãy đo với workload thật và implementation thực tế.

## 13. Ví dụ MailComposer dùng FileSystemResource

Một cách tổ chức đơn giản là composer dựng nội dung và gắn file đã tồn tại:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public final class InvoiceMailComposer {

    private final JavaMailSender sender;

    public InvoiceMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage compose(
            String recipient,
            String orderCode,
            String plain,
            String escapedHtml,
            Path invoicePdf
    ) throws MessagingException {

        MimeMessage message = sender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn đơn hàng " + orderCode);
        helper.setText(plain, escapedHtml);
        helper.addAttachment(
                "invoice.pdf",
                new FileSystemResource(invoicePdf),
                "application/pdf"
        );

        return message;
    }
}
```

Các tham số `plain` và `escapedHtml` giả định đã được chuẩn bị an toàn. Trong production, nên render HTML bằng template engine với escaping đúng context; đừng ghép raw user input thẳng vào HTML.

### Service gửi và quản lý vòng đời

```java
public final class InvoiceMailService {

    private final JavaMailSender sender;
    private final InvoiceMailComposer composer;

    public InvoiceMailService(
            JavaMailSender sender,
            InvoiceMailComposer composer
    ) {
        this.sender = sender;
        this.composer = composer;
    }

    public void submit(
            String recipient,
            String orderCode,
            String plain,
            String html,
            Path pdfFile
    ) throws MessagingException {

        MimeMessage message = composer.compose(
                recipient, orderCode, plain, html, pdfFile
        );
        sender.send(message);
    }
}
```

Service trên là ví dụ tối giản cho một lần gửi đồng bộ. Nếu file được tạo trong tác vụ, cần xử lý cleanup bằng cơ chế `try/finally` **sau khi đã kết thúc lời gọi cần đọc file** và dự kiến vòng đời retry phù hợp. Nếu gửi bất đồng bộ, không được xóa file ngay sau khi submit task cho executor.

## 14. Tạo attachment lớn: dùng đường ra stream/file khi có thể

Giả sử ứng dụng tạo PDF. Có hai API giả định:

```java
byte[] pdf = pdfGenerator.generateToByteArray(report);
```

và:

```java
pdfGenerator.writeTo(report, outputStream);
```

Nếu bộ tạo tài liệu hỗ trợ ghi ra `OutputStream`, ta có thể cân nhắc:

```java
Path pdfFile = Files.createTempFile(
        "mail-invoice-", ".pdf");

try (OutputStream output =
             Files.newOutputStream(pdfFile)) {
    pdfGenerator.writeTo(report, output);
}

// Worker giữ file cho tới khi hoàn tất send/retry policy.
```

Lợi ích là không bắt buộc giữ toàn bộ PDF trong `byte[]`. Đổi lại, có thêm I/O và trách nhiệm quản lý file tạm.

**Lưu ý vận hành:** đường dẫn file phải nằm trong thư mục được phép, có quyền truy cập hạn chế, quota dung lượng và cleanup khi task thành công/thất bại. Nếu service chạy trong container với ephemeral disk, file có thể mất sau restart; cần lưu trữ bền vững khi yêu cầu gửi phải sống sót qua crash.

## 15. Resource từ object storage hoặc dịch vụ bên ngoài

Khi attachment nằm trong object storage, có thể nghĩ tới:

```java
InputStreamSource source = () ->
        objectStorage.openStream(storageKey);
```

Đây là abstraction minh họa; `objectStorage` và `storageKey` do ứng dụng định nghĩa. Để an toàn:

1. `openStream(...)` phải tạo **stream mới** trên mỗi lời gọi.
2. Dữ liệu phải còn truy cập được tại thời điểm worker serialize.
3. Có timeout, giới hạn kích thước và chính sách retry cho lần tải nội dung.
4. Không lấy một signed URL ngắn hạn làm dependency duy nhất của task sẽ xử lý sau nhiều giờ.
5. Có xác thực/ủy quyền rõ ràng đối với object.
6. Cân nhắc checksum hoặc version ID để tránh file thay đổi giữa hai lần đọc.
7. Không log signed URL/token trong exception hoặc diagnostic.

### Remote stream không tự miễn phí

Dùng remote stream có thể giảm heap nhưng tạo thêm request và độ trễ mạng **trước hoặc trong lúc SMTP send**. Nếu source bị đọc nhiều lần, object storage có thể bị tải nhiều lần. Nếu mạng storage chậm, SMTP worker có thể bị giữ lâu, mặc dù vấn đề không nằm ở mail server.

Hãy đo riêng thời gian **fetch source** và **SMTP submit**. Nếu file dùng lặp lại nhiều lần, cache có giới hạn hoặc bản local được quản lý có thể hữu ích, nhưng cần cân bằng dung lượng, tính nhất quán và yêu cầu bảo mật.

## 16. Khi nào nên đính kèm file, khi nào nên gửi link?

Với báo cáo rất lớn, có thể chọn gửi một link tải file thay vì đính kèm:

| Phương án | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| Attachment MIME | Người nhận có thể lưu file cùng email, thuận tiện offline | Base64 overhead, giới hạn message size, băng thông |
| Link tải qua HTTPS | Email nhỏ; có thể quản lý phiên bản và quyền tải | Phụ thuộc Internet, hạn link, UX và auth |
| Attachment nhỏ + link bản đầy đủ | Vừa có tóm tắt offline vừa giảm kích thước | Tăng phức tạp thiết kế nội dung |

Không tự chuyển một attachment nhạy cảm thành public URL để tối ưu SMTP. Link nên có cơ chế xác thực/ủy quyền, thời hạn sử dụng, khả năng thu hồi, rate limit và log truy cập phù hợp. Email có thể được forward; bearer signed URL trong thư cần được đánh giá theo nguy cơ bị chuyển tiếp.

Nếu quy định nghiệp vụ bắt buộc đính kèm hóa đơn không thể sửa đổi, việc thay bằng link có thể không phù hợp. Hiệu năng không được làm sai yêu cầu lưu trữ và pháp lý của hệ thống.

## 17. Ước lượng kích thước trước khi gọi JavaMailSender

Một ứng dụng cần tránh tạo và gửi những message chắc chắn vượt policy. Có thể kiểm tra:

- Giới hạn một attachment.
- Giới hạn tổng byte attachment nguồn.
- Số lượng attachment.
- Kích thước ước lượng sau MIME encoding.
- Kích thước tối đa mà provider cho phép.
- Kích thước nội dung HTML và inline resources.

Ví dụ một utility ước lượng overhead Base64 theo các dòng tối đa 76 ký tự:

```java
public final class MimeSizeEstimate {

    private MimeSizeEstimate() {}

    public static long base64MimeBytes(long rawBytes) {
        if (rawBytes < 0) {
            throw new IllegalArgumentException(
                    "rawBytes must be non-negative");
        }

        // ceil(rawBytes / 3), không cộng 2 vào rawBytes
        // để tránh overflow ở giá trị lớn.
        long groups = rawBytes / 3;
        if (rawBytes % 3 != 0) {
            groups = Math.addExact(groups, 1);
        }

        long encodedChars = Math.multiplyExact(groups, 4);

        // ceil(encodedChars / 76)
        long lines = encodedChars / 76;
        if (encodedChars % 76 != 0) {
            lines = Math.addExact(lines, 1);
        }

        long lineEndings = Math.multiplyExact(lines, 2);
        return Math.addExact(encodedChars, lineEndings);
    }

    public static long estimateAttachments(
            Collection<Long> fileSizes
    ) {
        long total = 0;
        for (long size : fileSizes) {
            total = Math.addExact(
                    total,
                    base64MimeBytes(size)
            );
        }
        return total;
    }
}
```

Giá trị này **ước tính content của attachment Base64 với một CRLF mỗi dòng**. Nó chưa gồm headers, MIME boundaries, text/HTML, các part khác và framing SMTP. Với message có nhiều tệp, mỗi part có overhead riêng. Đối với tệp được gửi bằng transfer encoding khác, cần mô hình phù hợp thay vì áp Base64 cho mọi part.

### Ví dụ preflight cho file trên disk

```java
long pdfBytes = Files.size(pdfPath);
long logoBytes = Files.size(logoPath);

long encodedAttachmentEstimate =
        MimeSizeEstimate.estimateAttachments(
                List.of(pdfBytes, logoBytes)
        );

long estimatedMessageBytes = Math.addExact(
        encodedAttachmentEstimate,
        configuredOverheadReserveBytes
);

if (estimatedMessageBytes > maxConfiguredMessageBytes) {
    throw new MailPayloadTooLargeException(
            "Estimated MIME message exceeds policy limit"
    );
}
```

`configuredOverheadReserveBytes` và `maxConfiguredMessageBytes` là các giá trị **do ứng dụng tự định nghĩa**; `MailPayloadTooLargeException` cũng là một exception nghiệp vụ minh họa. Không có con số dự trữ MIME cố định nào chính xác cho mọi email.

Một message lớn gần giới hạn nên có lựa chọn xử lý trước khi tạo attachment:

1. Thông báo hoặc áp dụng chính sách từ chối.
2. Chuyển sang gửi link có quyền nếu sản phẩm cho phép.
3. Rút gọn/thay định dạng tài liệu nếu không làm sai nghiệp vụ.
4. Tách thành nhiều notification nếu chính sách cho phép và người nhận hiểu được.

**Không chia file thành nhiều email một cách tự động** nếu người nhận không được thông báo hoặc việc tách làm sai ý nghĩa tài liệu.

## 18. Kiểm tra thực tế kích thước MIME serialized

Ứng dụng có thể đo kích thước một `MimeMessage` khi serialize trong test, nhưng không nên phải giữ toàn bộ raw dump trong memory chỉ để đếm byte.

Một `OutputStream` đếm số byte được ghi:

```java
import java.io.IOException;
import java.io.OutputStream;

public final class CountingOutputStream extends OutputStream {

    private long count;

    @Override
    public void write(int value) throws IOException {
        count = Math.addExact(count, 1);
    }

    @Override
    public void write(byte[] bytes, int offset, int length)
            throws IOException {
        if (bytes == null) {
            throw new NullPointerException("bytes");
        }
        if (offset < 0 || length < 0
                || offset > bytes.length - length) {
            throw new IndexOutOfBoundsException();
        }
        count = Math.addExact(count, length);
    }

    public long count() {
        return count;
    }
}
```

Đo với dữ liệu **fixture giả**:

```java
MimeMessage message = buildTestMessage();
message.saveChanges();

CountingOutputStream counting = new CountingOutputStream();
message.writeTo(counting);

long actualSerializedMimeBytes = counting.count();
System.out.println(
        "Serialized test MIME bytes: "
                + actualSerializedMimeBytes
);
```

`buildTestMessage()` là code tạo message test do ứng dụng cung cấp. Cách này giúp tránh một `ByteArrayOutputStream` lớn, nhưng:

- Nó **vẫn phải đọc attachment và mã hóa MIME**, nên tốn CPU/I/O.
- Nó có thể chạm vào resource và sinh/cập nhật header.
- Không chứng minh server đã chấp nhận message.
- Không tính mọi byte SMTP envelope, command, TLS framing hoặc thay đổi phía relay.
- Nếu gọi trước khi send thật, có thể khiến attachment được đọc **thêm một lần**.

Vì vậy, **đừng serialize toàn bộ email production hai lần chỉ để đo size**. Hãy dùng estimate trong đường gửi thực và đo raw serialized size có chọn mẫu trong test/benchmark.

## 19. Giới hạn từ SMTP server và provider

Các provider có thể giới hạn:

- Kích thước tối đa của message sau khi encode.
- Số recipient mỗi message.
- Số message mỗi kết nối hoặc mỗi khoảng thời gian.
- Số kết nối SMTP đồng thời.
- Tốc độ gửi theo tài khoản, miền hoặc IP.
- Các loại attachment/filename bị hạn chế.
- Thời gian tối đa của kết nối và giao dịch SMTP.

Một số SMTP server quảng bá `SIZE` trong EHLO; tuy nhiên, **cách xử lý giới hạn và response thực tế do server quyết định**. Ứng dụng vẫn phải dự phòng lỗi khi gửi.

Ví dụ:

```text
S: 250-SIZE 26214400
S: 250 8BITMIME
```

Con số trong ví dụ là số byte minh họa của capability, **không phải giới hạn chung của Spring Mail hoặc SMTP**. Trước khi đưa message vào `DATA`, transport/provider có thể từ chối dựa trên giới hạn kích thước đã biết hoặc tính toán của nó. Sau khi nhận dữ liệu, server vẫn có thể từ chối vì policy.

### Không phụ thuộc vào client estimate như cam kết nhận thư

Nếu estimate là 24,9 MiB và provider nói “25 MB”, vẫn có thể vượt vì:

- MB khác MiB.
- MIME headers/boundaries chưa được tính.
- HTML, inline image chưa cộng.
- Message được chuyển đổi hoặc thêm header.
- Provider tính size theo chính sách riêng.

Tốt hơn nên chọn **ngưỡng ứng dụng thấp hơn ngưỡng provider**, đo đạc bằng dữ liệu test và xử lý lỗi server trả về. Khoảng an toàn cụ thể phải do nghiệp vụ/nhà cung cấp quyết định.

## 20. Base64 tốn CPU bao nhiêu?

Để mã hóa một tệp nhị phân, encoder cần đọc các byte đầu vào và tạo biểu diễn Base64. Chi phí CPU thường tăng theo lượng dữ liệu:

\[
\text{Encode work} \propto \text{attachment bytes}.
\]

Ngoài thao tác mã hóa còn có:

- Đọc từ filesystem/object storage.
- Ghi byte encoded ra stream.
- Sao chép qua buffer.
- Định dạng line ending và MIME boundaries.
- TLS encryption khi dùng SMTP/TLS.
- Chi phí hệ điều hành/network stack.

Không nên đưa ra một con số như “Base64 luôn tốn 5 ms/MB” mà không đo trên hệ thống, phiên bản JDK và dữ liệu thực tế. Trên một máy, CPU mã hóa có thể không đáng kể so với network. Trên hệ thống gửi hàng nghìn email có attachment, lượng CPU cộng dồn có thể trở thành bottleneck.

### CPU-bound hay I/O-bound?

| Dấu hiệu | Khả năng nguyên nhân |
| --- | --- |
| CPU cao, SMTP server phản hồi nhanh | Render/encode/format hoặc tạo PDF |
| Đọc disk cao, CPU vừa phải | File attachment nằm trên disk chậm |
| Network egress gần giới hạn | Payload MIME lớn hoặc quá nhiều email |
| Worker bận nhưng CPU thấp | Chờ SMTP/socket/storage I/O |
| GC pause tăng, heap dùng cao | Giữ nhiều `byte[]`, template hoặc buffer |
| Queue tăng dù CPU/heap còn dư | Giới hạn concurrency, SMTP throttling hoặc lock |

Chỉ số cần nhìn đồng thời, không kết luận nguyên nhân từ một metric riêng.

## 21. Tính tổng băng thông của một chiến dịch gửi mail

Một email có 10 MiB attachment nguồn tạo khoảng 13,68 MiB Base64 MIME payload. Nếu gửi cho 100 recipient bằng **100 message riêng**, tổng attachment payload đã gần:

```text
13.68 MiB/message x 100 messages
    = 1,368 MiB
    = khoảng 1.34 GiB
```

Chưa gồm HTML, headers, attachment khác và giao thức. Đó là lý do email gửi riêng theo từng người có thể tiêu tốn nhiều băng thông hơn một message gửi chung cho nhiều recipient.

Nhưng **một message cho nhiều recipient** có trade-off:

- To/Cc có thể làm lộ danh sách nhận.
- Bcc cần được xử lý đúng để giữ riêng tư.
- Một recipient bị lỗi có thể làm cả message thất bại khi không cho partial send.
- Retry theo từng người khó hơn.
- Nội dung cá nhân hóa cho từng người không thể chỉ reuse một message chung.
- Giới hạn số recipient mỗi message vẫn áp dụng.

Không gộp tất cả người nhận vào một email chỉ để tiết kiệm băng thông nếu điều đó làm sai nội dung, mất riêng tư hoặc làm khó xử lý retry.

## 22. Gửi một MimeMessage nhiều recipient so với nhiều MimeMessage

So sánh:

```text
Phương án A: một message, nhiều recipient
  MIME payload được submit một lần trong SMTP transaction
  RCPT TO A
  RCPT TO B
  RCPT TO C
  DATA [MIME]

Phương án B: nhiều message riêng
  RCPT TO A -> DATA [MIME_A]
  RCPT TO B -> DATA [MIME_B]
  RCPT TO C -> DATA [MIME_C]
```

Trong một SMTP transaction, DATA có thể dùng chung cho nhiều envelope recipients mà server chấp nhận. Điều đó **có thể** tiết kiệm byte truyền tới server đầu tiên. Tuy nhiên, khi gửi riêng:

- Có thể cá nhân hóa nội dung.
- Dễ theo dõi `notificationId` và lỗi recipient.
- Không phải hiển thị danh sách người khác.
- Retry riêng ít nguy cơ gây duplicate.

Một kiến trúc tốt không tối ưu chỉ theo byte SMTP mà còn phải tính reliability, privacy và business semantics.

## 23. Batch gửi mail có giảm chi phí MIME không?

`JavaMailSender.send(MimeMessage...)` cho phép gửi nhiều message:

```java
MimeMessage first = buildFirstMessage();
MimeMessage second = buildSecondMessage();
MimeMessage third = buildThirdMessage();

mailSender.send(first, second, third);
```

`JavaMailSenderImpl` có thể tái sử dụng transport SMTP trong một lời gọi batch khi điều kiện cho phép, giảm chi phí kết nối/đăng nhập lặp lại. Nhưng **mỗi message vẫn cần serialize nội dung MIME của nó**. Nếu cả ba chứa cùng một attachment 10 MiB, việc đưa chúng vào một mảng `send(...)` không tự loại bỏ ba lần đọc/encode/truyền attachment.

Trade-off khác:

- Một message thất bại có thể khiến method ném `MailSendException` với các `failedMessages`.
- Một số message trong batch có thể đã được gửi trước khi exception xảy ra.
- Retry nguyên batch có nguy cơ duplicate.
- Giữ nhiều `MimeMessage` đồng thời có thể tăng heap nếu chúng tham chiếu các byte array lớn.
- Giới hạn server về connection và rate vẫn áp dụng.

Batching thích hợp để giảm overhead giao thức khi có ích, nhưng phải kết hợp tracking per-message và giới hạn kích thước/memory.

## 24. Đừng cache nguyên MimeMessage để tiết kiệm CPU

Một ý tưởng dễ phát sinh khi gửi nhiều email cùng template là cache một `MimeMessage` đã dựng rồi đổi recipient:

```java
MimeMessage shared = composeCommonMessage();

for (String recipient : recipients) {
    shared.setRecipients(
            Message.RecipientType.TO,
            recipient
    );
    sender.send(shared);
}
```

Cách này dễ gây lỗi:

- `MimeMessage` là object mutable.
- Header như `Message-ID` và recipient có thể bị thay đổi.
- Task chạy đồng thời có thể tranh chấp cùng instance.
- Bcc/To có thể bị dùng nhầm giữa hai người nhận.
- Nội dung cá nhân hóa và token riêng có thể bị rò sang email khác.
- Retry và trạng thái từng recipient khó tương quan.

**Nên tái sử dụng template đã được parse/cache**, logo/source fixture hợp lệ, cấu hình và dữ liệu bất biến phù hợp; nhưng tạo **MimeMessage riêng cho mỗi notification** khi nội dung/recipient khác nhau. Cache một object MIME gửi đi không phải tối ưu an toàn mặc định.

## 25. Hiệu năng của template và MIME là hai câu chuyện khác nhau

Một email HTML có thể trải qua:

```text
Load template
   |
   v
Parse / cache template representation
   |
   v
Render HTML with model
   |
   v
Build MimeMessage
   |
   v
Encode and send MIME parts
```

Nếu hệ thống mất thời gian trước khi gọi `MimeMessageHelper`, việc thay `ByteArrayResource` bằng `FileSystemResource` có thể không cải thiện latency đáng kể. Nếu thời gian chủ yếu chờ SMTP socket, tối ưu expression trong Thymeleaf cũng có thể không tạo khác biệt rõ ràng.

### Cách tối ưu đúng tầng

- Tải/parse template một cách có cache theo thiết kế của template engine.
- Không nạp lại tài nguyên logo từ mạng cho mọi email khi đã có nguồn local/cache phù hợp.
- Chỉ truy vấn database đúng những trường cần cho notification.
- Chuẩn bị DTO bất biến, không truyền JPA entity đang lazy sang worker.
- Render một lần trên mỗi notification/attempt khi phù hợp.
- Tạo `MimeMessage` sau khi biết rõ recipient và nội dung cuối.
- Không render/encode những attachment mà policy đã biết sẽ vượt giới hạn.

**Không cache HTML đã điền tên, token hoặc thông tin riêng của người dùng** rồi dùng lại cho recipient khác. Cache template structure khác với cache kết quả render đã cá nhân hóa.

## 26. Số worker đồng thời và áp lực bộ nhớ

Nếu có `W` worker và mỗi worker giữ trung bình `M` MiB attachment trong memory, riêng bộ dữ liệu ấy có thể đạt:

\[
\text{Heap attachment working set}\approx W\times M.
\]

Ví dụ:

| Worker đồng thời | Attachment giữ trong heap mỗi worker | Tổng mảng nguồn, chưa tính overhead |
| ---: | ---: | ---: |
| 2 | 10 MiB | 20 MiB |
| 8 | 10 MiB | 80 MiB |
| 16 | 20 MiB | 320 MiB |
| 32 | 20 MiB | 640 MiB |

Đây là phép ước lượng cực kỳ đơn giản, **không phải dự báo RSS/JVM heap chính xác**. Một worker có thể giữ nhiều bản sao tệp, object template, buffer PDF và bộ nhớ của thư viện. Hơn nữa, queue cũng có thể giữ references tới những `byte[]` chưa được xử lý.

### Queue giữ DTO khác queue giữ byte[]

So sánh:

```java
record MailTaskA(
        UUID notificationId,
        String recipient,
        byte[] attachmentBytes
) {}
```

với:

```java
record MailTaskB(
        UUID notificationId,
        String recipient,
        String attachmentStorageKey
) {}
```

Giả sử queue chứa 1.000 task, mỗi task A có mảng 10 MiB độc lập. Tổng attachment được tham chiếu có thể lên tới gần **10.000 MiB (khoảng 9,77 GiB)**, vượt xa heap của nhiều ứng dụng. Queue task B chỉ chứa metadata và khóa lưu trữ, nhưng worker phải tải attachment khi chạy và xử lý khả năng source mất hoặc thay đổi.

**Đừng đưa toàn bộ byte array lớn vào unbounded executor queue.** Tách dữ liệu công việc bền vững khỏi payload, giới hạn queue/concurrency và chỉ tải file khi thực sự đến lượt xử lý.

## 27. Cấu hình một executor riêng cho mail workload

Ví dụ Spring:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.util.concurrent.ThreadPoolExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfig {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("mail-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );
        return executor;
    }
}
```

Các số `2/4/20` là giá trị minh họa, **không phải cấu hình tối ưu chung**. Với attachment nhỏ, bottleneck có thể là SMTP provider; với PDF lớn, disk/heap/bandwidth có thể hạn chế hơn.

### Vì sao không tăng pool vô hạn?

Mỗi worker thêm có thể:

- Đọc tệp.
- Serialize/Base64 hóa.
- Mở và giữ SMTP connection.
- Giữ buffer và network socket.
- Tranh băng thông với worker khác.
- Khiến server throttling hoặc trả `421/4xx`.

Nếu tăng worker từ 4 lên 40 nhưng provider chỉ cho phép 5 kết nối đồng thời, throughput có thể không tăng tương ứng mà chỉ tăng lỗi, retry và áp lực memory.

### Nếu queue đầy

`AbortPolicy` phát lỗi khi executor không nhận thêm task. Điều này tốt hơn việc âm thầm bỏ mail, nhưng application phải **xử lý được rejection**.

`CallerRunsPolicy` có thể khiến task được thực thi ở thread gọi khi quá tải. Nếu thread gọi là HTTP request hoặc đang mở transaction, tác động lên latency và transaction boundary có thể rất lớn. Không dùng policy này một cách máy móc để “tự backpressure”.

`DiscardPolicy` hoặc `DiscardOldestPolicy` có thể làm mất tác vụ nếu không có bản ghi công việc bền vững. Với email nghiệp vụ, phải xem xét hậu quả mất notification trước khi chọn.

## 28. Dùng outbox khi không được mất yêu cầu gửi

Một executor queue trong memory không phải durable queue. Nếu process restart, các task chưa được thực thi có thể mất. Đối với email quan trọng, có thể dùng transactional outbox:

```text
Business transaction
    |
    +-- UPDATE order
    +-- INSERT mail_notification(PENDING,
    |       templateKey, recipientId, storageKey)
    |
    v
COMMIT
    |
    v
Mail worker claim notification
    |
    v
Load/render/build MIME on demand
    |
    v
SMTP submit (không giữ DB TX lâu)
    |
    v
Update outcome in separate short TX
```

Đối với attachment lớn, **không nhét blob Base64 vào outbox row** chỉ để làm queue đơn giản hơn nếu điều đó gây phình database, redo/WAL, backup và network. Có thể lưu metadata và một tham chiếu tới object storage bền vững.

Nhưng cách tham chiếu có hai yêu cầu:

1. Nội dung phải còn tồn tại và truy cập được khi worker chạy, kể cả sau restart.
2. Nội dung phải đúng phiên bản được chấp thuận tại thời điểm sự kiện nghiệp vụ; không tùy tiện đọc phiên bản file đã bị sửa.

Nếu file gốc được tạo cùng với transaction nghiệp vụ, cần thiết kế thứ tự tạo/lưu file và xử lý tình huống DB rollback nhưng object upload đã thành công (hoặc ngược lại). Object storage không tự tham gia database transaction ACID.

## 29. Không giữ transaction database qua SMTP send dài

Một anti-pattern:

```java
@Transactional
public void sendInvoice(UUID notificationId) {
    MailNotification notification =
            repository.findById(notificationId).orElseThrow();

    MimeMessage message = composeWithLargeAttachment(notification);
    javaMailSender.send(message); // I/O mạng trong DB transaction.

    notification.markSubmitted();
}
```

Với attachment lớn, method có thể giữ JDBC connection và lock lâu trong khi đọc file, Base64 encoding, gửi qua mạng và chờ SMTP.

Tách:

1. **Claim transaction ngắn** để chọn notification.
2. **Build/encode/send SMTP** ngoài DB transaction.
3. **Outcome transaction ngắn** để ghi `SUBMITTED`, `RETRY_WAIT`, `FAILED` hoặc `UNKNOWN`.

SMTP không rollback cùng database. Nếu server đã nhận message nhưng worker crash trước khi cập nhật status, retry có thể dẫn tới duplicate. Outbox bảo đảm không mất yêu cầu gửi, nhưng không tạo exactly-once SMTP delivery.

## 30. Độ trễ và băng thông: mô hình ước tính

Nếu một message có `S` byte serialized MIME và kết nối đạt thông lượng ứng dụng thực tế `R` byte/giây, thời gian truyền dữ liệu **tối thiểu gần đúng** là:

\[
T_{\text{transfer}}\approx\frac{S}{R}.
\]

Tổng thời gian gửi:

\[
T_{\text{send}}\approx
T_{\text{connect/auth}}
+T_{\text{read/encode}}
+T_{\text{transfer}}
+T_{\text{server response}}.
\]

Các phần có thể chồng lấn vì serialization và network stream có thể diễn ra tuần tự theo buffer hoặc theo pipeline. Công thức chỉ để **phân tách những nguồn trễ**, không nhất thiết cộng đúng từng millisecond.

### Ví dụ minh họa

Một email có khoảng 20 MiB serialized MIME. Nếu throughput thực đo được là 2 MiB/giây, phần truyền DATA riêng đã có thể cần khoảng 10 giây, chưa tính kết nối, đọc nguồn, mã hóa và server response.

Với một nhóm worker cùng gửi qua một đường uplink giới hạn, mỗi worker có thể nhận phần băng thông nhỏ hơn. Tăng số worker không tạo thêm băng thông vật lý.

## 31. SMTP timeout phải phù hợp với workload lớn

Trong Spring Boot:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 30000
      "[mail.smtp.writetimeout]": 30000
```

Đây là cấu hình ví dụ; thời gian tính bằng millisecond. Chúng có phạm vi khác nhau:

| Property | Ý nghĩa |
| --- | --- |
| `mail.smtp.connectiontimeout` | Giới hạn chờ kết nối |
| `mail.smtp.timeout` | Giới hạn chờ đọc dữ liệu/phản hồi từ socket |
| `mail.smtp.writetimeout` | Giới hạn chờ ghi dữ liệu ra socket |

Đối với attachment lớn, `writetimeout` đặc biệt đáng lưu ý; một timeout quá ngắn so với đặc điểm mạng/server có thể cắt quá trình truyền. Tuy nhiên, tăng timeout vô hạn cũng giữ worker lâu, làm queue tăng và trì hoãn phát hiện sự cố.

**Timeout sau khi SMTP DATA có thể đã tới server tạo kết quả không rõ ràng**. Không tự động retry nguyên message mà không xem nguy cơ duplicate và bằng chứng acceptance.

## 32. Backpressure theo kích thước, không chỉ số task

Hai task khác nhau rất nhiều:

```text
Task A: 20 KiB HTML, không attachment
Task B: 3 PDF x 20 MiB
```

Một pool cho chạy đồng thời 10 task có thể ổn nếu đều là A, nhưng quá tải disk/network/heap nếu đều là B. Chỉ giới hạn số task chưa phản ánh toàn bộ chi phí.

Có thể dùng:

- Queue giới hạn số phần tử.
- Worker class riêng cho mail lớn/nhỏ.
- Semaphore để giới hạn số attachment lớn đang encode.
- Rate limit theo byte/giây hoặc theo quota provider.
- Hàng đợi có priority/fairness để mail rất lớn không giữ hết worker.
- Admission control trước khi tạo file và MIME.

### Ví dụ semaphore cho tác vụ có attachment lớn

```java
public final class LargeMailGate {

    private final Semaphore permits = new Semaphore(2);

    public void runLargeMail(Runnable action)
            throws InterruptedException {

        permits.acquire();
        try {
            action.run();
        } finally {
            permits.release();
        }
    }
}
```

Đây là giới hạn **2 công việc lớn đồng thời trong một process**, không phải quota toàn cluster. Nếu có nhiều instance, cần phối hợp với giới hạn provider và cơ chế phân phối công việc; semaphore cục bộ của mỗi instance không tự tạo rate limit dùng chung.

Không giữ transaction DB hoặc HTTP request lâu trong lúc chờ permit. Nên thực hiện admission/scheduling tại worker và lưu yêu cầu gửi trong queue/outbox có chính sách rõ ràng.

## 33. Khi tệp nguồn thay đổi giữa lúc compose và send

Một `FileSystemResource` hoặc remote `InputStreamSource` thường tham chiếu tới dữ liệu được đọc **khi cần**. Điều này tốt cho memory, nhưng tạo vấn đề nhất quán:

```text
T0  Worker tạo MimeMessage, gắn FileSystemResource(file.pdf)
T1  Một tiến trình khác ghi đè file.pdf
T2  JavaMailSender bắt đầu serialize
T3  Thư nhận nội dung mới, không phải nội dung lúc T0
```

Hoặc file bị xóa ở T1 và send thất bại lúc T2.

Giải pháp:

- Dùng file immutable/unique path cho từng notification.
- Với object storage, tham chiếu version ID thay vì một key có thể bị ghi đè.
- Giữ nguồn còn tồn tại tới khi kết thúc attempt và theo policy retry.
- Dùng checksum/digest khi cần kiểm tra tính nhất quán theo quyền dữ liệu.
- Không cố chia sẻ file temp cùng tên giữa nhiều worker.

**Streaming không loại bỏ nhu cầu snapshot logic của dữ liệu.** Đối với hóa đơn hoặc tài liệu pháp lý, byte phải tương ứng với sự kiện đã được xác nhận. Nếu mọi lần retry đều tạo lại một PDF theo dữ liệu đang thay đổi, người nhận có thể nhận nội dung khác nhau dù cùng notification ID.

## 34. Dọn file tạm phải đúng thời điểm

Khi attachment được tạo trên đĩa:

```text
Generate file
     |
     v
Persist reference / enqueue
     |
     v
Worker open stream and submit
     |
     v
Record outcome
     |
     +-- success -> retention policy -> cleanup
     +-- retry   -> giữ file/source đủ lâu
     +-- fail    -> cleanup theo policy
     +-- unknown -> chưa xóa nếu còn cần reconcile
```

Một file temp có thể bị bỏ lại nếu process crash trước `finally`. Vì vậy, cleanup nên có cơ chế định kỳ theo metadata, không chỉ dựa vào khối `finally` trong một request.

Quy tắc vận hành:

1. Đường dẫn file riêng cho từng notification/attempt.
2. Quyền filesystem hạn chế, tránh cho người dùng khác đọc dữ liệu.
3. Không dùng filename nhận trực tiếp từ user làm path chưa được validate.
4. Có quota disk và cảnh báo khi gần đầy.
5. Có TTL/garbage collection phù hợp với trạng thái notification.
6. Có phương án phục hồi khi worker restart hoặc storage không còn file.
7. Không log đường dẫn chứa ID nhạy cảm hoặc file name riêng tư vào log công khai.

Nếu hệ thống lưu tài liệu ở object storage bền vững, có thể không cần temp file local; nhưng cần xem độ trễ và số lần tải object lúc serialize.

## 35. Quan sát chính xác chi phí của từng bước

Một metric `mail_send_duration` duy nhất khó cho biết lỗi hiệu năng nằm đâu. Nên tách:

| Metric | Đơn vị | Mục đích |
| --- | --- | --- |
| `mail_render_duration` | ms | Chi phí template |
| `mail_attachment_generation_duration` | ms | Tạo PDF/CSV |
| `mail_compose_duration` | ms | Gắn MIME parts và headers |
| `mail_serialize_duration` | ms | Đo trong test/benchmark có chọn mẫu |
| `mail_smtp_submit_duration` | ms | Thời gian `JavaMailSender.send` |
| `mail_attachment_source_bytes` | bytes | Tổng kích thước tệp nguồn |
| `mail_estimated_mime_bytes` | bytes | Upper/approx estimate trước gửi |
| `mail_attachment_count` | count | Số attachment/notification |
| `mail_queue_depth` | count | Tác vụ chờ |
| `mail_inflight_tasks` | count | Tác vụ đang chạy |
| `mail_submission_failure_total` | count | Lỗi gửi theo nhóm |
| `mail_unknown_outcome_total` | count | SMTP outcome mơ hồ |
| `mail_outbox_oldest_age` | seconds | Thời gian task chờ lâu nhất |

`mail_smtp_submit_duration` có thể bao gồm **MIME serialization, đọc attachment và network**. Đừng gọi nó là “network time” nếu chưa instrument riêng các lớp.

### Những nhãn metric nên giới hạn

Có thể nhóm:

- Mail class: `transactional`, `bulk`.
- Attachment size bucket: `0`, `<1MiB`, `1-10MiB`, `>10MiB`.
- Outcome: `submitted`, `failed`, `unknown`.
- SMTP provider alias hoặc route đã được kiểm soát.

Không đưa `recipientEmail`, `notificationId`, `subject`, filename thật hoặc URL token vào metric label. Những trường đó vừa có nguy cơ riêng tư, vừa gây cardinality cao.

## 36. Dùng logging/tracing mà không ghi dữ liệu nhạy cảm

Một log sự kiện đủ để điều tra:

```text
event=mail_submission
notificationId=N-361-A
mailClass=transactional
attachmentCount=2
sourceBytesBucket=10-20MiB
estimatedMimeBytesBucket=20-30MiB
composeDurationMs=12
smtpSubmitDurationMs=8450
attempt=1
outcome=SUBMITTED
```

Đừng log:

```java
logger.info("Message={}", mimeMessage);
message.writeTo(System.out);
```

Raw MIME có thể chứa tên, email, Bcc, reset token, HTML và attachment. Nếu cần raw MIME để điều tra lỗi byte-level, ưu tiên fixture giả trong test; đối với production phải có quy trình riêng về phạm vi, phê duyệt, mã hóa, truy cập và thời hạn lưu.

Kích thước file, đường dẫn storage và MIME type cũng có thể tiết lộ thông tin nghiệp vụ; hãy cân nhắc dạng bucket và mã định danh nội bộ khi xuất ra dashboard.

## 37. Benchmark đúng cách: tách CPU, I/O và SMTP

Một benchmark hữu ích cần định nghĩa rõ phần việc đo:

**Benchmark A — Composer**

- Tạo `MimeMessage` và gắn headers, text, attachment resource.
- Không serialize hoặc gửi SMTP.
- Đo object allocation, CPU time, latency.
- Kết luận chỉ về chi phí dựng object.

**Benchmark B — MIME serialization**

- Dùng fixture giả với attachment kích thước cố định.
- Gọi `message.writeTo(countingOutputStream)`.
- Đo thời gian, CPU, số byte output và lượng đọc nguồn.
- Không dùng SMTP; phân biệt với băng thông mạng.

**Benchmark C — SMTP submit tới server cục bộ**

- Gửi message qua `JavaMailSenderImpl` tới SMTP test server.
- Đo tổng latency từ sender và số byte server nhận.
- Tránh dependency vào provider production.
- Có thể so sánh payload nhỏ/lớn và số message.

**Benchmark D — End-to-end workload**

- Tạo notification, render, load file, gửi tới SMTP sandbox có giới hạn.
- Đo queue lag, throughput, CPU, heap/GC, disk/network, lỗi.
- Dùng dữ liệu thử và quota/permission phù hợp.

Kết quả A, B, C, D có thể khác nhau rất lớn. Nếu chỉ chạy một phép đo rồi quy mọi chi phí cho “Base64 chậm”, kết luận dễ thiếu cơ sở.

## 38. Thiết kế ma trận đo hiệu năng

| Kịch bản | Attachment | Resource | Concurrency | Mục tiêu |
| --- | --- | --- | ---: | --- |
| S01 | Không có | — | 1 | Baseline text/HTML |
| S02 | 1 KiB | ByteArrayResource | 1 | Overhead part/header |
| S03 | 1 MiB | ByteArrayResource | 1 | CPU/heap mức nhỏ |
| S04 | 10 MiB | ByteArrayResource | 1 | Payload Base64 lớn |
| S05 | 10 MiB | FileSystemResource | 1 | So sánh heap và disk I/O |
| S06 | 10 MiB | FileSystemResource | 8 | Concurrent read/encode/send |
| S07 | 2 x 10 MiB | FileSystemResource | 4 | Nhiều attachment |
| S08 | 20 KiB inline image | ClassPathResource | 50 | Chi phí tài nguyên lặp |
| S09 | 10 MiB remote | Fresh InputStreamSource | 4 | Chi phí object-storage fetch |
| S10 | 10 MiB | Mixed attachments | Queue burst | Backpressure và p95/p99 |

Nên đo ít nhất:

- Throughput: message/giây và MIME byte/giây.
- Latency: p50, p95, p99 của render/submit.
- Heap used/peak, allocation rate, GC pause.
- CPU utilization.
- Disk read throughput và network egress.
- Queue depth, rejection và retry count.
- Số lỗi timeout, rate limit và unknown outcomes.

### Điều kiện để phép so sánh có ý nghĩa

- Warm up JVM/JIT trước khi lấy kết quả.
- Sử dụng cùng JDK, thư viện, phần cứng và cấu hình provider/test server.
- Chạy nhiều lượt, không lấy một lần đầu duy nhất làm kết luận.
- Giữ kích thước và nội dung fixture tương đương.
- Đo thực tế resource có nằm trong OS page cache hay phải đọc đĩa.
- Không cho benchmark tạo email tới người dùng thật.
- Phân biệt tải bền vững lâu dài và một burst ngắn.

Với microbenchmark Java, JMH là công cụ phù hợp hơn một vòng `System.nanoTime()` tự viết thiếu warmup và fork. Nhưng benchmark toàn pipeline SMTP cần thêm integration/load test, vì microbenchmark không phản ánh server/network.

## 39. Kiểm thử chi phí encode với attachment ngẫu nhiên giả

Không dùng tài liệu thật để benchmark. Có thể tạo fixture nhị phân giả có kích thước xác định:

```java
byte[] bytes = new byte[1024 * 1024];
new SecureRandom().nextBytes(bytes);

MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom("perf@example.org");
helper.setTo("sink@example.net");
helper.setSubject("Attachment size test");
helper.setText("Synthetic message.");
helper.addAttachment(
        "synthetic.bin",
        new ByteArrayResource(bytes),
        "application/octet-stream"
);

message.saveChanges();
CountingOutputStream output = new CountingOutputStream();
message.writeTo(output);

long mimeBytes = output.count();
```

`SecureRandom` trong ví dụ tạo byte giả. Khi benchmark hiệu năng thuần, việc sinh random phải thực hiện **ngoài đoạn đo serialization**, nếu không kết quả bị cộng thêm chi phí random generation.

Để đo memory của `FileSystemResource`, tạo file fixture với kích thước tương đương trước benchmark và dùng cùng dữ liệu qua các lần chạy. Đừng đo thời gian tạo file tạm chung với `writeTo` trừ khi mục tiêu cố ý là end-to-end.

## 40. Test kích thước Base64 bằng các giá trị biên

Các giá trị nhỏ dễ kiểm tra:

| Byte nguồn `N` | Ký tự Base64 `4×ceil(N/3)` | Ghi chú |
| ---: | ---: | --- |
| 0 | 0 | Không có content |
| 1 | 4 | Có padding |
| 2 | 4 | Có padding |
| 3 | 4 | Một nhóm hoàn chỉnh |
| 4 | 8 | Hai nhóm, nhóm cuối padding |
| 57 | 76 | Một dòng MIME đầy đủ |
| 58 | 80 | Cần thêm dòng |
| 114 | 152 | Hai dòng 76 ký tự |

Trong test có thể assert phần size **estimate** chứ không cố đo đúng số byte SMTP envelope:

```java
assertEquals(
        6L,
        MimeSizeEstimate.base64MimeBytes(1)
);

assertEquals(
        78L,
        MimeSizeEstimate.base64MimeBytes(57)
);

assertEquals(
        84L,
        MimeSizeEstimate.base64MimeBytes(58)
);
```

Với 1 byte, estimate tính 4 ký tự và 2 byte CRLF; raw Base64 encoder có thể tạo chuỗi chỉ 4 ký tự khi không cần CRLF cuối. Với 58 byte, 80 ký tự Base64 được chia thành hai dòng nên estimate bằng 84 byte.

**Đừng suy ra công thức estimate là phép kiểm byte tuyệt đối cho mọi implementation**. Hãy so sánh với `writeTo(...)` bằng fixture theo thư viện đang dùng nếu muốn kiểm chứng mô hình size cụ thể.

## 41. Unit test và integration test bổ trợ nhau

**Unit test** có thể xác minh:

- Composer gắn attachment đúng MIME type và disposition.
- `FileSystemResource` được tham chiếu thay vì tạo `byte[]` nếu kiến trúc yêu cầu.
- Tệp giả được đọc đúng bytes qua `MimeMessage` sau serialization.
- Size estimate và policy từ chối khi vượt quota.
- Retry policy phân loại timeout/oversize/4xx/5xx rõ ràng.

**Integration test** có thể xác minh:

- Message gửi tới SMTP test server được serialize thành công.
- Server từ chối message quá lớn trong kịch bản mô phỏng.
- Timeout và lỗi SMTP được ứng dụng ghi nhận đúng.
- Nhiều attachment trong `multipart/mixed` không bị mất.
- Queue có backpressure và worker không bị đẩy vô hạn.

**Load test** mới cho biết throughput, memory/GC và độ trễ khi có nhiều notification đồng thời. Không dùng một unit test `assertDoesNotThrow(sender.send(...))` để kết luận hệ thống chịu tải lớn.

## 42. Các lỗi thường gặp và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Message vượt giới hạn dù file nguồn chưa quá lớn | Base64 + MIME overhead | Estimate full message và reserve |
| Heap tăng vọt khi queue có nhiều task | Task giữ `byte[]` lớn | Queue metadata/storage key, limit concurrency |
| File tạm bị xóa trước khi send | Resource chỉ được đọc khi serialize | Quản lý lifecycle file đến cuối attempt |
| Attachment trống ở lần gửi thứ hai | Source trả lại stream đã tiêu thụ | Fresh `InputStream` mỗi lần, tránh single-use |
| CPU cao khi gửi file lớn | Tạo PDF/encode/serialize/TLS | Đo riêng từng tầng, tối ưu đúng bottleneck |
| SMTP worker bận nhưng CPU thấp | Chờ network/provider/storage | Kiểm tra latency, timeout, provider quota |
| Thêm worker làm gửi chậm hơn | Throttling, disk/network contention | Giới hạn concurrency, backpressure |
| FileSystemResource không tiết kiệm nhiều heap | Template/PDF builder vẫn giữ buffer lớn | Tối ưu cả pipeline và đo allocations |
| `send(messages)` vẫn tốn nhiều byte | Mỗi message serialize attachment riêng | Cân nhắc payload và recipient semantics |
| Gửi lại email tạo bản sao | Timeout/partial SMTP outcome mơ hồ | Tracking, `UNKNOWN`, provider reconciliation |
| Byte estimate khác size SMTP | Header, boundary, CRLF, framing | Dùng estimate có reserve và test serialization |
| Benchmark lệch giữa hai lần | JIT, page cache, GC, network | Warmup, lặp lại, cô lập biến đo |
| Raw MIME leak trong log | Dump để điều tra performance | Chỉ metric/summary, test fixture giả |
| Outbox quá lớn | Lưu blob/Base64 trực tiếp trong DB row | Metadata + storage bền vững nếu phù hợp |
| File remote thay đổi sau compose | Source mutable | Versioned/immutable object |

## 43. Checklist tối ưu trước khi triển khai

### Kích thước và encoding

- [ ] Có giới hạn byte nguồn cho mỗi attachment.
- [ ] Có giới hạn tổng attachment và số MIME parts.
- [ ] Có estimate Base64 + folding + header/body reserve.
- [ ] Phân biệt MB và MiB khi đối chiếu provider.
- [ ] Xử lý được SMTP rejection vì message size.

### Bộ nhớ và dữ liệu nguồn

- [ ] Không đưa `byte[]` lớn vào queue không giới hạn.
- [ ] Dùng resource phù hợp: byte array nhỏ hoặc file/stream đọc lại được.
- [ ] File/object không bị xóa hoặc ghi đè trước khi send.
- [ ] Có quota cho temp disk và object storage.
- [ ] Có cleanup/retention khi task hoàn thành hoặc thất bại.
- [ ] Có phương án restart/retry cho notification quan trọng.

### Thực thi và throughput

- [ ] Có giới hạn worker/connections theo SMTP provider.
- [ ] Queue bounded và có backpressure/rejection policy.
- [ ] Không giữ DB transaction qua SMTP I/O dài.
- [ ] Có timeout connect/read/write phù hợp.
- [ ] Không retry mù khi kết quả SMTP `UNKNOWN`.
- [ ] Cân nhắc size-based scheduling cho tác vụ lớn.

### Quan sát và bảo mật

- [ ] Phân biệt thời gian render/compose/serialize/send.
- [ ] Đo attachment bytes, MIME estimate, queue và GC.
- [ ] Dùng fixture giả trong benchmark.
- [ ] Không log raw MIME, recipient, Bcc, token hoặc attachment.
- [ ] Có alert khi queue lag, oversize và SMTP throttling tăng.

## 44. Tình huống tự luyện

### Tình huống A — PDF 25 MiB và provider giới hạn 25 MB

Ứng dụng đọc `Files.size(pdfPath)` thấy 25 MiB và quyết định gửi.

**Câu hỏi:** Vì sao có thể thất bại?

**Gợi ý:** Base64 folding có thể nâng phần PDF lên khoảng 34,2 MiB, còn MIME headers/body làm lớn hơn nữa. Ngoài ra, 25 MB và 25 MiB không bằng nhau. Cần preflight size và xử lý từ chối từ server.

### Tình huống B — Queue giữ 500 tệp 10 MiB dưới dạng byte[]

Task được tạo ngay trong HTTP request và đưa vào executor queue.

**Câu hỏi:** Hệ quả là gì?

**Gợi ý:** Riêng mảng file có thể giữ khoảng 5.000 MiB heap, chưa tính object khác. Nên lưu notification metadata/storage key, dùng queue có giới hạn và tải file khi worker chạy.

### Tình huống C — Dùng FileSystemResource nhưng file bị xóa sớm

Controller tạo file temp, gọi một method `@Async` rồi lập tức xóa file.

**Câu hỏi:** Vì sao worker có thể thất bại?

**Gợi ý:** Attachment có thể chỉ được đọc khi serialization/send ở worker. Resource phải còn tồn tại tới khi task thực sự đọc xong.

### Tình huống D — Cùng một PDF gửi cho 10.000 người

Hệ thống tạo 10.000 `MimeMessage`, mỗi message đính kèm PDF giống nhau.

**Câu hỏi:** Có phải Base64 chỉ encode một lần?

**Gợi ý:** Không thể mặc định như vậy. Mỗi message cần serialized MIME và DATA của nó; batch send không tự deduplicate attachment giữa messages. Có thể cân nhắc share nguồn file bất biến nhưng không share mutable `MimeMessage`, đồng thời đánh giá privacy/cá nhân hóa.

### Tình huống E — Tăng worker từ 4 lên 40 nhưng throughput giảm

**Gợi ý:** Provider có thể throttle, socket/network/disk contention tăng, nhiều worker giữ buffer/heap hơn, retry tăng. Đo connection, quota, queue, GC, network và SMTP response.

### Tình huống F — Attachment lỗi ở lần retry

Lần đầu gửi được nhưng lần hai có file rỗng do `InputStreamSource` trả cùng một stream.

**Gợi ý:** Source phải mở stream mới mỗi lần. Dùng `ByteArrayResource` cho dữ liệu nhỏ hoặc `FileSystemResource`/source có thể đọc lại với file ổn định.

### Tình huống G — Timeout sau DATA

Worker đã gửi gần hết email lớn, không nhận được phản hồi cuối.

**Gợi ý:** Không thể khẳng định server chưa nhận; cần `UNKNOWN`, đối chiếu provider khi có và tránh gửi lại nguyên message ngay một cách mù quáng.

### Tình huống H — Chuyển hóa đơn thành URL công khai

Đội kỹ thuật muốn bỏ attachment để giảm băng thông.

**Gợi ý:** Link có thể giảm kích thước SMTP nhưng phải được xác thực/ủy quyền, có TTL, audit và cơ chế thu hồi. Không được đổi thành public object URL nếu tài liệu nhạy cảm hoặc luật/nghiệp vụ yêu cầu lưu file kèm email.

## 45. Nguyên tắc cần nhớ

1. **Tạo MIME object, serialize MIME và gửi SMTP là các giai đoạn khác nhau.** Đừng gom mọi chi phí vào một thao tác.
2. **Base64 làm tăng byte nội dung khoảng 33,3%;** MIME line folding khiến payload tệp lớn thường tăng khoảng **36,8%** trước khi tính headers/boundaries.
3. **ByteArrayResource phù hợp khi dữ liệu đã ở memory; FileSystemResource có thể giảm việc giữ cả tệp trong heap.**
4. **InputStreamSource cần mở được stream mới theo nhu cầu;** stream chỉ đọc một lần làm retry/serialization dễ lỗi.
5. **Streaming không có nghĩa không dùng RAM:** MIME tree, template, network/TLS buffers và thư viện vẫn có allocations.
6. **Preflight size phải tính encoded bytes và reserve**, không chỉ `Files.size()`.
7. **Không giữ file temp ít hơn vòng đời send**, và đừng để file mutable thay đổi giữa compose/send.
8. **Tăng concurrency không đồng nghĩa tăng throughput**, nhất là khi giới hạn SMTP/network hoặc heap/GC.
9. **Batching có thể giảm connection overhead nhưng không tự giảm attachment bytes của từng message.**
10. **Outbox giữ yêu cầu gửi bền vững, không biến SMTP thành exactly-once delivery.**
11. **Không log raw MIME/attachment để đo hiệu năng**; dùng metadata và fixture giả.
12. **Benchmark từng tầng và đo workload tổng thể** trước khi chọn tối ưu.

## 46. Kết luận

Chi phí tạo MIME và mã hóa attachment trong Spring Framework Mail không chỉ là thời gian chạy `MimeMessageHelper`. Khi gửi thư có ảnh, PDF và nhiều tệp đính kèm, ứng dụng phải quản lý MIME parts, đọc nguồn dữ liệu, Base64 hóa và gấp dòng, truyền lượng byte lớn hơn tệp gốc, đồng thời giữ worker hoạt động trong suốt quá trình SMTP submission. Với tệp lớn, **Base64 và MIME folding có thể làm attachment tăng kích thước truyền khoảng 36,8%** trước khi tính phần header và body khác.

Để triển khai hiệu quả, hãy đo riêng render, compose, serialize và send; dùng `ByteArrayResource` khi thực sự cần giữ dữ liệu nhỏ trong memory, còn dữ liệu lớn nên cân nhắc file hoặc stream mở lại được. Trước khi gửi, áp dụng chính sách kiểm tra số lượng/kích thước attachment và ước lượng encoded MIME size có khoảng đệm. Khi có nhiều tác vụ, giới hạn concurrency và queue theo tài nguyên thực tế, quản lý file/object storage ổn định, không xóa nguồn sớm và không giữ database transaction trong lúc SMTP truyền tệp.

Quan trọng nhất, tối ưu performance **không được đánh đổi độ tin cậy hoặc bảo mật**: không reuse mutable message giữa người nhận, không gửi lại mù khi SMTP outcome chưa rõ, không biến file nhạy cảm thành link công khai và không lưu raw MIME trong log. Kết hợp resource phù hợp, preflight policy, observability và benchmark có kiểm soát giúp hệ thống gửi mail có attachment ổn định hơn khi quy mô tăng.
