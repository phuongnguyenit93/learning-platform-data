# Rủi ro khi tạo MIME thủ công trong Spring Framework Mail

Khi gửi email có nhiều định dạng, ảnh inline hoặc tệp đính kèm, ứng dụng phải tạo một thông điệp theo chuẩn MIME (Multipurpose Internet Mail Extensions). MIME mô tả loại nội dung, cách mã hóa dữ liệu, ranh giới giữa các phần và quan hệ giữa các phần trong cùng email.

Một email có thể chứa bản văn bản thuần `text/plain`, bản HTML `text/html`, ảnh inline được HTML tham chiếu qua `cid:...`, tệp đính kèm PDF/CSV/XLSX và nội dung Unicode trong subject hoặc tên file.

Tự nối một chuỗi raw MIME để tạo các phần này có vẻ đơn giản lúc đầu, nhưng rất dễ tạo message sai cấu trúc hoặc chỉ lỗi trên một số mail client. Các lỗi thường nằm ở boundary, CRLF, encoding, header, MIME nesting, dữ liệu nhị phân và cách xử lý dữ liệu không tin cậy.

**Trong Spring Framework Mail, hãy dùng `MimeMessageHelper` và các API của Jakarta Mail để xây dựng message theo object model.** Chỉ tự dựng MIME ở mức thấp khi có yêu cầu cụ thể mà helper không đáp ứng; ngay cả khi đó, nên dùng `MimeBodyPart`, `MimeMultipart` và `DataHandler` thay vì tự nối header, boundary và byte thành một chuỗi.

## 1. MIME giải quyết vấn đề gì?

Email ban đầu chủ yếu truyền văn bản. MIME mở rộng định dạng để một message có thể mô tả nội dung thuộc nhiều loại, chẳng hạn HTML, ảnh, PDF hoặc dữ liệu được mã hóa.

Một part MIME thường có:

- Header mô tả part, ví dụ `Content-Type`.
- Có thể có `Content-Transfer-Encoding` để mô tả cách biểu diễn byte khi truyền.
- Có thể có `Content-Disposition`, `Content-ID` hoặc các header liên quan.
- Một dòng trống phân cách header và body.
- Phần dữ liệu của part.

Ví dụ minh họa một part HTML:

```text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin chào bạn!</p>
```

Một message nhiều part dùng cấu trúc multipart:

```text
Content-Type: multipart/alternative; boundary="example-boundary"

--example-boundary
Content-Type: text/plain; charset=UTF-8

Xin chào bạn!

--example-boundary
Content-Type: text/html; charset=UTF-8

<p>Xin chào <strong>bạn</strong>!</p>

--example-boundary--
```

Trong ví dụ, `boundary` chia message thành các part. Dấu `--` đứng trước boundary mở một part; dấu `--` ở cuối boundary đóng toàn bộ multipart. Đây chỉ là ví dụ để hiểu cấu trúc, không phải cách nên tạo email bằng cách ghép chuỗi trong ứng dụng.

### MIME không chỉ là thêm một header

Đặt `Content-Type: multipart/alternative` ở đầu email chưa đủ để message hợp lệ. Nội dung phải có boundary được khai báo và được dùng nhất quán, mỗi part phải có header/body đúng vị trí, và multipart phải được đóng đúng cách. Tệp nhị phân cần transfer encoding phù hợp; HTML tham chiếu CID cần MIME part có Content-ID tương ứng.

Vì vậy, khi tự tạo MIME, ứng dụng phải chịu trách nhiệm về toàn bộ cấu trúc message. Đây là phần việc mà Jakarta Mail và Spring Mail đã cung cấp API để quản lý.

## 2. Rủi ro 1: boundary không hợp lệ hoặc không nhất quán

Boundary là chuỗi phân cách các part trong `multipart/*`. Header khai báo boundary, còn body dùng đúng chuỗi đó ở các delimiter.

Một số lỗi thường gặp:

- Header khai báo `boundary="abc"` nhưng body lại dùng `--xyz`.
- Quên dấu `--` ở đầu delimiter.
- Quên delimiter đóng `--boundary--`.
- Dùng cùng boundary cho các multipart lồng nhau.
- Boundary xuất hiện nguyên vẹn ở nội dung part khiến parser hiểu nhầm điểm kết thúc.
- Ghép boundary hoặc quote sai khi giá trị có ký tự đặc biệt.

Ví dụ sai:

```text
Content-Type: multipart/alternative; boundary="outer"

--inner
Content-Type: text/plain

Hello

--outer--
```

Header nói boundary là `outer` nhưng delimiter mở lại dùng `inner`. Parser không thể xác định đúng cấu trúc.

### Boundary trong multipart lồng nhau

Một email có body alternative, ảnh inline và attachment có thể có nhiều tầng multipart:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   └── image/png (CID)
└── application/pdf (attachment)
```

Mỗi multipart cần boundary riêng. Nếu tự ghép chuỗi, việc tạo boundary duy nhất, khai báo đúng ở từng tầng và đóng đúng thứ tự rất dễ sai. Khi dùng object model, Jakarta Mail quản lý boundary và serialization.

**Cách tránh:** không tự sinh boundary bằng cách nối chuỗi. Dùng `MimeMultipart` hoặc `MimeMessageHelper` để thư viện tạo boundary và quản lý part.

## 3. Rủi ro 2: sai CRLF và dấu phân cách header/body

Định dạng Internet Message sử dụng quy ước dòng CRLF (`\r\n`). Trong raw MIME, header và body được ngăn cách bằng một dòng trống, tức CRLF kép.

Ví dụ cấu trúc:

```text
Subject: Monthly report\r\n
MIME-Version: 1.0\r\n
Content-Type: text/plain; charset=UTF-8\r\n
\r\n
Report is ready.\r\n
```

Nếu ứng dụng dùng newline kiểu LF (`\n`) một cách tùy tiện, hoặc bỏ mất dòng trống giữa header và body, một số parser có thể không đọc message đúng như mong đợi.

Các lỗi thường thấy:

- Chỉ dùng LF trong raw MIME.
- Dùng CRLF không nhất quán giữa header và delimiter.
- Thêm khoảng trắng hoặc ký tự trước header đầu tiên.
- Quên dòng trống sau header của một part.
- Thêm newline sai vị trí làm nội dung có thêm dòng trắng hoặc boundary bị nhập vào body.
- Tự chuyển newline của nội dung văn bản mà không hiểu tác động tới dữ liệu.

### Đừng tự viết SMTP DATA

Ngoài MIME, SMTP còn có quy tắc truyền dữ liệu, ví dụ dot-stuffing khi dòng dữ liệu bắt đầu bằng dấu chấm. SMTP transport của Jakarta Mail xử lý các quy tắc truyền này. Nếu ứng dụng tự nối MIME rồi tự gửi SMTP bằng socket, còn phải xử lý SMTP command, response code, dot transparency, timeout, TLS và AUTH.

Hãy để `JavaMailSender`/Jakarta Mail thực hiện transport. Ứng dụng nên làm việc với `MimeMessage`, không tự viết phiên SMTP bằng chuỗi lệnh.

## 4. Rủi ro 3: nhầm charset với Content-Transfer-Encoding

Hai header này giải quyết hai vấn đề khác nhau:

| Thuộc tính | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `charset` trong Content-Type | Byte nội dung văn bản được giải mã thành ký tự theo bộ mã nào? | `charset=UTF-8` |
| `Content-Transfer-Encoding` | Byte của part được biểu diễn như thế nào trong MIME? | `quoted-printable`, `base64`, `7bit` |

Ví dụ:

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
```

`UTF-8` xác định cách diễn giải ký tự tiếng Việt. `quoted-printable` xác định cách biểu diễn byte trong body MIME. Chúng không thay thế cho nhau.

### Lỗi khi tự mã hóa nội dung

Nếu Java String đã được mã hóa UTF-8 thành byte nhưng header lại khai báo charset khác, người nhận có thể thấy ký tự lỗi. Nếu nội dung đã được chuyển sang chuỗi base64 nhưng vẫn khai báo `Content-Transfer-Encoding: 8bit`, client sẽ hiển thị chuỗi base64 thay vì nội dung gốc.

Một lỗi khác là tự mã hóa base64 một nội dung rồi truyền vào API vốn sẽ tiếp tục encode part đó. Kết quả là **double encoding**: client giải mã một lớp và nhận lại chuỗi base64 thay vì dữ liệu ban đầu.

### Vì sao không tự đặt Content-Transfer-Encoding?

Jakarta Mail có thể chọn cách transfer encoding phù hợp với loại nội dung và khả năng transport. Nếu tự đặt header nhưng không chuyển dữ liệu tương ứng, header và body sẽ mâu thuẫn.

Với text, dùng API như `setText(text, "UTF-8")` hoặc `MimeMessageHelper`. Với HTML, đặt content type và charset qua helper. Với file, cung cấp resource/`DataHandler` để thư viện đọc dữ liệu và tạo MIME part phù hợp.

Ví dụ Spring:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(
        "Đơn hàng đã được xác nhận.",
        "<p>Đơn hàng <strong>đã được xác nhận</strong>.</p>");
```

Không cần tự chuyển hai chuỗi sang byte, base64 rồi thêm header MIME bằng tay.

## 5. Rủi ro 4: mã hóa sai file nhị phân

PDF, PNG, JPEG, XLSX và các file nhị phân chứa byte tùy ý. Nếu đưa byte trực tiếp vào một chuỗi text MIME mà không có transfer encoding thích hợp, dữ liệu có thể bị thay đổi do chuyển đổi charset, chuẩn hóa newline, loại bỏ ký tự điều khiển hoặc diễn giải sai dữ liệu.

Ví dụ không an toàn:

```java
// Không chuyển byte PDF thành String để ghép vào raw email.
String pdfText = new String(pdfBytes, StandardCharsets.UTF_8);
String rawMessage = "Content-Type: application/pdf\r\n\r\n"
        + pdfText;
```

PDF không phải văn bản UTF-8. Chuyển byte PDF thành String có thể làm hỏng nội dung và không tạo một MIME attachment hợp lệ.

### Dùng Resource/ByteArrayResource

Với Spring Mail:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
```

Jakarta Mail xử lý việc đọc byte và biểu diễn attachment theo MIME. Với ảnh inline:

```java
helper.setText(
        "Báo cáo đã sẵn sàng.",
        "<p>Báo cáo đã sẵn sàng.</p><img src=\"cid:chart\">");
helper.addInline(
        "chart",
        new ByteArrayResource(chartPng),
        "image/png");
```

Không cần tự chuyển ảnh thành chuỗi base64 rồi gắn vào raw body.

## 6. Rủi ro 5: sai cấu trúc multipart

Các subtype multipart có ý nghĩa khác nhau. Chọn sai subtype có thể khiến client hiển thị sai nội dung hoặc xem part như attachment.

| Subtype | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| `multipart/alternative` | Các cách biểu diễn thay thế của cùng nội dung | Plain text và HTML |
| `multipart/related` | Nội dung chính và tài nguyên mà nó tham chiếu | HTML và ảnh CID |
| `multipart/mixed` | Các phần độc lập được gom trong cùng message | Body email và PDF attachment |

### Alternative không phải mixed

`multipart/alternative` dùng cho nhiều phiên bản của cùng nội dung. Ví dụ text/plain và text/html truyền tải cùng thông tin. Các phiên bản thường được sắp xếp từ ít phong phú đến phong phú hơn, nên text/plain trước, text/html sau.

Nếu đưa PDF attachment thành một alternative part, mail client có thể hiểu sai rằng PDF là một phiên bản thay thế của body. PDF cần được tổ chức như một phần độc lập trong cấu trúc mixed.

### Related không phải attachment thông thường

Ảnh mà HTML tham chiếu qua `cid:logo` có quan hệ với phần HTML. `multipart/related` mô tả mối liên hệ này. Nếu chỉ đặt ảnh trong `multipart/mixed` mà HTML tham chiếu CID không đúng cấu trúc, một số client có thể không kết nối được ảnh với body hoặc hiển thị nó như tệp đính kèm.

### Cấu trúc tham khảo

Một message có text, HTML, logo CID và PDF có thể được biểu diễn logic như sau:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png
    │       Content-ID: <logo>
    └── application/pdf
        Content-Disposition: attachment
```

Đây là một cấu trúc minh họa; cách lồng cụ thể phụ thuộc API, multipart mode và thư viện. Khi dùng `MimeMessageHelper`, chọn multipart mode phù hợp thay vì tự dựng các tầng bằng raw string.

## 7. Rủi ro 6: header không hợp lệ và header injection

Email có nhiều header:

- `From`, `To`, `Cc`, `Bcc`.
- `Subject`.
- `Reply-To`.
- `Date`, `Message-ID`.
- `MIME-Version` và các header liên quan đến content.

Header có cú pháp riêng, hỗ trợ folding và encoding. Không nên nối chuỗi dữ liệu người dùng trực tiếp vào raw header.

Ví dụ nguy hiểm:

```java
// Không nối dữ liệu người dùng vào raw header.
String rawHeader = "Subject: " + userSuppliedSubject + "\r\n";
```

Nếu dữ liệu chứa CRLF, nó có thể chèn header mới hoặc làm thay đổi cấu trúc message. Một số API Jakarta Mail từ chối ký tự xuống dòng trong giá trị header, nhưng ứng dụng vẫn cần xác thực dữ liệu đầu vào và không tự ghép header raw.

### Dùng API có kiểu dữ liệu

```java
helper.setSubject(subject);
helper.setFrom(fromAddress);
helper.setTo(recipientAddress);
helper.setReplyTo(replyToAddress);
```

Các API này biết cách đặt header phù hợp hơn việc tự viết `Subject: ...` hoặc `To: ...` vào một chuỗi.

### Kiểm tra địa chỉ email

Nếu địa chỉ người nhận đến từ dữ liệu đầu vào, hãy parse và xác thực bằng API địa chỉ, đồng thời áp dụng chính sách ứng dụng:

```java
import jakarta.mail.internet.InternetAddress;

InternetAddress address = new InternetAddress(recipient, true);
address.validate();
helper.setTo(address);
```

Đoạn này kiểm tra cú pháp địa chỉ ở mức thư viện; nó không chứng minh mailbox tồn tại hoặc người yêu cầu có quyền gửi đến địa chỉ đó. Quyền gửi và quy tắc nghiệp vụ vẫn cần được kiểm tra riêng.

### Không tự thêm Bcc vào nội dung

`Bcc` là header recipient cần được xử lý bởi mail API/transport. Không tự đưa địa chỉ Bcc vào body hoặc tự viết một header Bcc trong raw string rồi kỳ vọng mọi lớp vận chuyển xử lý đúng. Dùng `helper.setBcc(...)` hoặc API tương ứng. Transport có thể loại Bcc header khỏi bản gửi ra theo đúng hành vi của email.

## 8. Rủi ro 7: encoding subject, tên hiển thị và filename

Header email có quy tắc encoding riêng cho ký tự ngoài ASCII. Subject như `"Báo cáo tháng 11 – Nguyễn An"` và tên file `"Hóa đơn tháng 11.pdf"` có thể cần encoded-word hoặc encoded parameter để tương thích với mail client.

Không nên tự base64 toàn bộ subject rồi đặt vào header theo cách tùy ý. Encoding header không giống encoding body.

### Subject và display name

Dùng API:

```java
helper.setSubject("Báo cáo tháng 11 – Nguyễn An", "UTF-8");
helper.setFrom(
        new InternetAddress("notifications@example.org", "Đội ngũ Example", "UTF-8"));
```

Jakarta Mail xử lý encoding phù hợp khi serialize message.

### Tên file attachment

Tên file có thể chứa dấu tiếng Việt, dấu cách hoặc ký tự Unicode. Việc biểu diễn tham số filename có quy tắc riêng, thường liên quan RFC 2231 và khác biệt tương thích giữa client. Dùng:

```java
helper.addAttachment(
        "Hoa-don-thang-11.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
```

Nếu cần filename Unicode, truyền tên file cho API attachment và kiểm thử trên các client mục tiêu. Không tự nối `Content-Disposition: attachment; filename="..."` với chuỗi chưa escape.

Ngoài encoding, filename cần được làm sạch: loại bỏ path separator, ký tự điều khiển và tên đường dẫn nội bộ. Chỉ gửi basename mà người nhận cần nhìn thấy, không đưa đường dẫn server vào filename.

## 9. Rủi ro 8: line length và transfer encoding

Các chuẩn email đặt giới hạn cho độ dài dòng trong header/body. Ví dụ:

- Header có quy tắc folding và độ dài dòng theo Internet Message Format.
- Base64 trong MIME thường được ngắt dòng, tối đa 76 ký tự mỗi dòng theo quy tắc MIME.
- Quoted-printable cũng có giới hạn dòng.

Nếu tự nối một chuỗi base64 rất dài thành một dòng, một số parser hoặc gateway có thể xử lý không đúng. Nếu tự ngắt dòng sai, dữ liệu sau giải mã có thể bị thay đổi.

Không nên tự viết hàm base64 và wrap line nếu Jakarta Mail có thể thực hiện. Cung cấp byte array hoặc resource cho part để thư viện serialize đúng cách.

### Không nhầm 7bit, 8bit và binary

`7bit`, `8bit` và `binary` không phải các từ đồng nghĩa:

- `7bit` giới hạn dữ liệu ở ASCII 7-bit và tuân theo quy tắc dòng.
- `8bit` cho phép byte 8-bit, nhưng việc vận chuyển phụ thuộc khả năng SMTP như 8BITMIME.
- `binary` dành cho dữ liệu nhị phân và yêu cầu hỗ trợ transport tương ứng.
- `base64` và `quoted-printable` biểu diễn dữ liệu theo cách tương thích hơn với nhiều hệ thống email.

Nếu tự khai báo `8bit` nhưng SMTP server hoặc gateway không hỗ trợ, nội dung có thể bị từ chối hoặc biến đổi. Jakarta Mail có thể chọn encoding phù hợp theo cấu hình và transport.

## 10. Rủi ro 9: HTML, CID và Content-ID không khớp

Email có ảnh inline cần đồng bộ giữa:

1. `src="cid:logo"` trong HTML.
2. `Content-ID: <logo>` của part ảnh.
3. `Content-Type` chính xác như `image/png`.
4. Cấu trúc `multipart/related` phù hợp.

Các lỗi phổ biến:

- HTML dùng `cid:logo` nhưng part có ID `brand-logo`.
- Hai ảnh dùng cùng Content-ID.
- Part ảnh khai báo sai MIME type.
- HTML được render sau khi inline resource đã được thêm và cấu trúc multipart bị thay đổi.
- Ảnh được thêm như attachment thông thường thay vì inline resource.

Với Spring:

```java
helper.setText(
        plainText,
        "<p>Logo:</p><img src=\"cid:brand-logo\" alt=\"Logo\">");

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

Gọi `setText` trước `addInline`. Không đưa đường dẫn local vào HTML rồi mong helper tự tìm file. `addInline` nhận resource thực và tạo MIME part để HTML tham chiếu.

## 11. Rủi ro 10: dữ liệu không tin cậy trong MIME và HTML

Khi tạo email từ dữ liệu người dùng, cần phân biệt header values như subject, display name và recipient; nội dung text/plain; nội dung HTML; filename; URL trong `href` và `src`. Mỗi ngữ cảnh có quy tắc xử lý riêng. Một chuỗi đã được HTML-escape không có nghĩa nó an toàn để dùng trong header, URL hay filename.

### HTML injection

Không chèn trực tiếp tên người dùng vào HTML:

```java
// Không ghép dữ liệu chưa escape vào markup.
String html = "<p>Xin chào " + customerName + "</p>";
```

Dùng template engine có auto-escaping hoặc escape theo đúng ngữ cảnh HTML. Với URL trong `href`/`src`, ngoài escaping còn phải xác thực scheme và host. Không để dữ liệu người dùng tùy ý tạo `javascript:` URL hoặc link ra domain giả mạo.

### Header injection

Không ghép CRLF hoặc header fragment từ input vào raw MIME. Dùng API có kiểu dữ liệu và xác thực giá trị.

### Filename injection

Không nhận một đường dẫn như `../../private/secret.pdf` làm tên attachment. Tạo filename từ ID nội bộ an toàn hoặc chỉ giữ basename đã được làm sạch.

### MIME type giả

Không tin phần mở rộng file. Nếu file có tên `report.pdf` nhưng byte thực tế là một định dạng khác, khai báo `application/pdf` không biến nó thành PDF. Kiểm tra định dạng thực tế và chính sách loại file trước khi gửi.

## 12. Rủi ro 11: tự xử lý Bcc, recipient và header không nhất quán

Một message có thể có nhiều người nhận qua To, Cc và Bcc. Nếu tự ghép raw header, có thể hiển thị người nhận Bcc cho các recipient khác, lặp địa chỉ hoặc tạo header không hợp lệ, gửi nhầm dữ liệu riêng tư vì trộn danh sách người nhận.

Hãy dùng API của `MimeMessageHelper`/Jakarta Mail để đặt recipient:

```java
helper.setTo(toAddress);
helper.setCc(ccAddress);
helper.setBcc(bccAddress);
```

SMTP envelope recipients và các header recipient có vai trò khác nhau. Nếu ứng dụng cần gửi đến nhiều địa chỉ mà không tiết lộ danh sách, sử dụng Bcc hoặc gửi message riêng theo chính sách; không tự sửa raw header để che địa chỉ.

## 13. Rủi ro 12: raw MIME không tương thích với mail client

Một MIME message có thể được parser chấp nhận nhưng hiển thị khác nhau giữa Gmail, Outlook, Apple Mail, webmail và ứng dụng di động. Nguyên nhân có thể là cấu trúc multipart lồng nhau không theo ý nghĩa chuẩn, `Content-Disposition` không phù hợp, header encoding hoặc filename encoding khác biệt, HTML/CSS không được hỗ trợ, CID part không được đặt trong related multipart đúng cách, hoặc boundary/transfer encoding không chuẩn.

Không thể dựa vào một lần xem trên trình duyệt để kết luận raw MIME hoạt động trên mọi mail client. Hãy dùng cấu trúc MIME chuẩn và kiểm tra trên những client quan trọng với sản phẩm.

## 14. Cách an toàn hơn: dùng MimeMessageHelper

Với phần lớn email Spring, `MimeMessageHelper` là lựa chọn nên dùng. Ví dụ email có plain text, HTML, logo CID và PDF attachment:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            byte[] invoicePdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("notifications@example.org");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");

        String plainText = """
                Hóa đơn của bạn đã sẵn sàng.
                Vui lòng mở file PDF đính kèm để xem chi tiết.
                Nếu cần hỗ trợ, liên hệ support@example.org.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <p>
                      <img src="cid:invoice-logo"
                           alt="Logo Example"
                           width="130">
                    </p>
                    <h2>Hóa đơn của bạn đã sẵn sàng</h2>
                    <p>Vui lòng mở file PDF đính kèm để xem chi tiết.</p>
                    <p>Cần hỗ trợ? support@example.org</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);
        helper.addInline(
                "invoice-logo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");
        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(invoicePdf),
                "application/pdf");

        mailSender.send(message);
    }
}
```

Ở ví dụ này:

- Multipart mode `MIXED_RELATED` hỗ trợ body, tài nguyên liên quan và attachment.
- `setText(plainText, htmlText)` tạo các phiên bản nội dung thay thế.
- `addInline` thêm ảnh mà HTML tham chiếu qua CID.
- `addAttachment` thêm PDF như một file độc lập.
- Charset UTF-8 được đặt khi tạo helper.
- Jakarta Mail chịu trách nhiệm serialize MIME message.

Trong ứng dụng thật, địa chỉ gửi và người nhận cần được lấy từ cấu hình và dữ liệu đã xác thực; ví dụ chỉ dùng địa chỉ minh họa. Nên giới hạn kích thước `invoicePdf` và kiểm tra artifact trước khi đính kèm.

### Chọn multipart mode phù hợp

`MimeMessageHelper` cung cấp các multipart mode, thường gồm:

| Mode | Ý nghĩa tổng quát | Trường hợp |
|---|---|---|
| `MULTIPART_MODE_NO` | Không bật multipart | Một body đơn giản |
| `MULTIPART_MODE_MIXED` | Dùng multipart/mixed | Body và attachment |
| `MULTIPART_MODE_RELATED` | Dùng multipart/related | HTML và tài nguyên inline |
| `MULTIPART_MODE_MIXED_RELATED` | Kết hợp mixed và related | HTML/CID cùng attachment |

Tên mode và cấu trúc cụ thể cần đối chiếu API của phiên bản Spring Framework đang dùng. Không nên giả định mọi helper constructor đều tạo cùng một cây MIME.

## 15. Khi helper chưa đủ: dùng Jakarta Mail object model

Có trường hợp cần kiểm soát cấu trúc MIME ở mức thấp hơn, ví dụ một hệ thống cần một cách lồng part cụ thể hoặc cần thao tác với các header/part chuyên biệt. Khi đó vẫn nên dùng object model của Jakarta Mail, không tự nối raw MIME string.

### 15.1. Tạo alternative part

```java
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMultipart;

MimeMultipart alternative = new MimeMultipart("alternative");

MimeBodyPart plainPart = new MimeBodyPart();
plainPart.setText(plainText, "UTF-8");
alternative.addBodyPart(plainPart);

MimeBodyPart htmlPart = new MimeBodyPart();
htmlPart.setContent(htmlText, "text/html; charset=UTF-8");
alternative.addBodyPart(htmlPart);
```

Các part được thêm theo thứ tự plain text rồi HTML. Mỗi body part có API riêng để thiết lập nội dung và charset.

### 15.2. Bọc alternative trong related khi có ảnh CID

```java
import jakarta.activation.DataHandler;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMultipart;
import jakarta.mail.util.ByteArrayDataSource;

MimeBodyPart alternativesContainer = new MimeBodyPart();
alternativesContainer.setContent(alternative);

MimeMultipart related = new MimeMultipart("related");
related.addBodyPart(alternativesContainer);

MimeBodyPart logoPart = new MimeBodyPart();
logoPart.setDataHandler(new DataHandler(
        new ByteArrayDataSource(logoBytes, "image/png")));
logoPart.setHeader("Content-ID", "<brand-logo>");
logoPart.setDisposition(MimeBodyPart.INLINE);
related.addBodyPart(logoPart);
```

HTML trong `htmlText` phải dùng `<img src="cid:brand-logo">`. Ví dụ dùng `ByteArrayDataSource` để cung cấp dữ liệu ảnh cho DataHandler.

### 15.3. Bọc related trong mixed khi có attachment

```java
import jakarta.activation.DataHandler;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMultipart;
import jakarta.mail.util.ByteArrayDataSource;

MimeBodyPart relatedContainer = new MimeBodyPart();
relatedContainer.setContent(related);

MimeMultipart mixed = new MimeMultipart("mixed");
mixed.addBodyPart(relatedContainer);

MimeBodyPart pdfPart = new MimeBodyPart();
pdfPart.setDataHandler(new DataHandler(
        new ByteArrayDataSource(invoicePdf, "application/pdf")));
pdfPart.setFileName("invoice.pdf");
pdfPart.setDisposition(MimeBodyPart.ATTACHMENT);
mixed.addBodyPart(pdfPart);

message.setContent(mixed);
message.saveChanges();
```

Đây là cách dựng MIME ở mức thấp bằng object model. Ứng dụng vẫn phải chịu trách nhiệm chọn subtype, thứ tự part, Content-ID, filename, disposition và dữ liệu. Jakarta Mail quản lý việc serialize boundary và encoding khi lưu/gửi.

Với một ứng dụng Spring thông thường, `MimeMessageHelper` ngắn gọn và ít chỗ sai hơn. Chỉ chuyển xuống API thấp hơn khi cần kiểm soát thực sự; tránh viết lại các chức năng mà helper đã cung cấp.

## 16. Vì sao không nên tự ghép raw MIME bằng String?

Ví dụ một cách làm dễ mắc lỗi:

```java
// Ví dụ anti-pattern: không dùng trong ứng dụng.
String boundary = "----my-boundary";

String rawMime =
        "MIME-Version: 1.0\r\n"
        + "Content-Type: multipart/mixed; boundary=" + boundary + "\r\n"
        + "\r\n"
        + "--" + boundary + "\r\n"
        + "Content-Type: text/plain; charset=UTF-8\r\n"
        + "\r\n"
        + plainText + "\r\n"
        + "--" + boundary + "\r\n"
        + "Content-Type: application/pdf\r\n"
        + "\r\n"
        + new String(pdfBytes, StandardCharsets.UTF_8)
        + "\r\n"
        + "--" + boundary + "--\r\n";
```

Ví dụ này minh họa một số vấn đề:

- PDF bị chuyển thành String UTF-8, có thể phá hỏng byte.
- Không có `Content-Transfer-Encoding` phù hợp cho PDF.
- Header filename và disposition không được thiết lập.
- Nếu nội dung text chứa boundary delimiter, parser có thể nhầm cấu trúc.
- Không xử lý đầy đủ multipart lồng nhau, CID và HTML.
- Không có cơ chế chuẩn hóa header/encoding.
- Không xử lý recipient, Bcc và các header message khác.

Ngay cả khi thay PDF bằng base64, người viết vẫn phải xử lý line wrapping, encoding header, boundary, CRLF và mọi loại nội dung. Chi phí bảo trì và nguy cơ lỗi cao hơn nhiều so với dùng API.

## 17. Kiểm tra MIME message được tạo ra

Khi gặp lỗi hiển thị hoặc client không nhận diện attachment, cần xem raw source của message trong môi trường test. SMTP sink như Mailpit hoặc công cụ kiểm thử mail local giúp kiểm tra message mà không gửi ra người nhận thật.

Các điểm nên quan sát:

- Root Content-Type có đúng subtype không.
- Boundary khai báo có khớp với delimiter trong body không.
- Các multipart lồng nhau có đúng vai trò không.
- Text/plain và text/html có charset phù hợp không.
- HTML CID có Content-ID part khớp không.
- PDF có Content-Type và Content-Disposition đúng không.
- Tên file attachment có được encode phù hợp không.
- Message có đủ boundary đóng và không có part rỗng bất thường không.

### Dùng Jakarta Mail để đọc lại cấu trúc

Trong test, có thể parse lại message đã dựng:

```java
MimeMessage message = mailSender.createMimeMessage();
// Thiết lập message bằng helper hoặc Jakarta Mail API.
message.saveChanges();

Object content = message.getContent();
if (content instanceof MimeMultipart multipart) {
    int count = multipart.getCount();
    // Kiểm tra số part và nội dung theo cấu trúc đã thiết kế.
}
```

Đây là phác thảo: tùy multipart mode, root content có thể là multipart lồng nhau. Test nên duyệt đệ quy cây part và xác nhận đúng subtype, Content-ID, filename và MIME type thay vì chỉ giả định root có một số part cố định.

### Kiểm thử trên mail client

MIME source hợp lệ không đảm bảo mọi client hiển thị giống hệt nhau. Với email quan trọng, kiểm tra các trường hợp:

| Kịch bản | Điều cần xem |
|---|---|
| Client chỉ hiển thị plain text | Nội dung nghiệp vụ vẫn đầy đủ |
| Client hiển thị HTML | Layout và link dễ đọc |
| Client chặn remote image | Alt text và nội dung không bị mất |
| Client hiển thị CID | Ảnh inline nằm đúng vị trí |
| Client có attachment viewer | PDF mở được và filename đúng |
| Client dùng locale khác | Subject, tiếng Việt và Unicode không lỗi |

Không dùng một lần gửi thành công qua SMTP làm bằng chứng rằng toàn bộ MIME content đã hiển thị đúng ở thiết bị nhận.

## 18. Cách ghi log và chẩn đoán lỗi MIME

Khi gửi email, nên ghi log theo từng giai đoạn:

1. Render nội dung thành công hay thất bại.
2. Tạo MIME message và thêm part thành công hay thất bại.
3. SMTP submission thành công hay thất bại.
4. Delivery/bounce nếu provider có cung cấp sự kiện.

Các trường có thể log: mail job ID, loại email/template version, số lượng attachment và tổng byte, MIME subtype tổng quát, provider message ID khi có, loại lỗi và exception class.

Tránh log password SMTP, access token, nội dung PDF/ảnh, token reset password hoặc OTP, toàn bộ raw MIME message có dữ liệu cá nhân và đường dẫn local nhạy cảm.

### Phân loại lỗi

| Lỗi | Tầng thường liên quan |
|---|---|
| Invalid boundary / malformed multipart | Tạo MIME |
| Unsupported encoding / malformed header | Tạo MIME hoặc parser phía nhận |
| CID không có part tương ứng | Nội dung và MIME structure |
| Attachment rỗng | Resource lifecycle / MIME part |
| Address rejected | Header/recipient hoặc SMTP policy |
| Authentication failed | SMTP transport |
| Message too large | MIME size / SMTP provider |
| SMTP accepted nhưng email bounce | Delivery sau submission |

Nếu SMTP server đã chấp nhận message, điều đó không chứng minh người nhận đã mở thư hoặc xem được nội dung. Với lỗi delivery, cần xem event từ provider hoặc mail gateway.

## 19. Các nguyên tắc thực hành

1. **Không nối raw MIME bằng String.** Dùng Spring `MimeMessageHelper` hoặc Jakarta Mail object model.
2. **Để thư viện quản lý boundary.** Không tự sinh hoặc ghép boundary cho multipart.
3. **Dùng CRLF và serialization do thư viện quản lý.** Không tự viết SMTP DATA hoặc dot-stuffing.
4. **Phân biệt charset với transfer encoding.** UTF-8 mô tả ký tự; base64/quoted-printable mô tả cách truyền byte.
5. **Không chuyển byte nhị phân thành String.** Dùng Resource, DataHandler hoặc byte array.
6. **Chọn đúng multipart subtype.** Alternative cho các bản nội dung, related cho CID, mixed cho attachment độc lập.
7. **Dùng API có kiểu cho header và recipient.** Không ghép subject, address hoặc Bcc vào raw header.
8. **Để thư viện encode subject và filename.** Không tự tạo encoded-word hay filename parameter bằng chuỗi.
9. **Escape HTML và xác thực URL theo ngữ cảnh.** Không dùng một cơ chế escape cho mọi trường.
10. **Kiểm tra MIME source và mail client.** Submission thành công chưa chứng minh cách hiển thị.

## 20. Câu hỏi thường gặp

**MIME có phải chỉ là header Content-Type không?** Không. MIME gồm cách mô tả part, transfer encoding, multipart boundary, header và body. Với multipart, boundary và cấu trúc lồng nhau phải nhất quán.

**Tại sao không nên tự tạo boundary?** Boundary phải được khai báo và dùng nhất quán ở mọi delimiter, đóng đúng cách và không xung đột với nội dung. Jakarta Mail có thể tạo và serialize chúng tự động.

**Có thể tự tạo MIME bằng String nếu chỉ có text và HTML không?** Vẫn có rủi ro CRLF, boundary, charset, transfer encoding và multipart semantics. Dùng `MimeMessageHelper.setText(plain, html)` đơn giản và an toàn hơn.

**Có nên tự base64 file rồi ghép vào email không?** Không. Dùng `addAttachment` hoặc `DataHandler` để thư viện tạo MIME part và transfer encoding.

**Charset UTF-8 có thay thế base64 không?** Không. Charset xác định cách giải mã ký tự; base64 là một cách biểu diễn byte trong MIME.

**Vì sao PDF bị hỏng khi gửi?** Một nguyên nhân thường gặp là chuyển byte PDF thành String hoặc tự mã hóa/giải mã sai. Dùng `ByteArrayResource` hoặc `FileSystemResource` và MIME type `application/pdf`.

**`multipart/alternative` có thể chứa PDF attachment không?** Không nên. Alternative dành cho các phiên bản thay thế của cùng nội dung. Attachment độc lập nên nằm trong cấu trúc mixed.

**Ảnh CID cần `multipart/related` không?** Đó là cấu trúc MIME dùng để mô tả HTML và các tài nguyên liên quan. Hãy để `MimeMessageHelper` chọn multipart mode thích hợp hoặc dựng related multipart bằng Jakarta Mail object model khi cần.

**Có thể đặt Content-ID bằng cách thêm raw header không?** Có thể ở mức thấp bằng API part header, nhưng cần kiểm soát giá trị và đồng bộ với `cid:` trong HTML. Khi có thể, dùng `MimeMessageHelper.addInline(...)`.

**Header injection xảy ra như thế nào?** Khi dữ liệu không tin cậy chứa CRLF được ghép vào raw header, nó có thể thêm hoặc thay đổi header khác. Dùng API header có kiểu và xác thực dữ liệu.

**Jakarta Mail có tự encode subject tiếng Việt không?** API của Jakarta Mail hỗ trợ encoding header phù hợp khi serialize message. Dùng `setSubject(subject, "UTF-8")` hoặc helper thay vì tự tạo encoded-word.

**Tên file attachment tiếng Việt có hoạt động trên mọi client không?** Hỗ trợ filename Unicode khác nhau theo client và chuẩn được triển khai. Dùng API attachment, kiểm thử client mục tiêu và cân nhắc tên ASCII an toàn nếu cần độ tương thích cao.

**`send()` thành công có nghĩa MIME đã hiển thị đúng không?** Không. Nó thường chỉ cho biết SMTP submission server chấp nhận message. Mail client vẫn có thể chọn alternative khác, chặn ảnh hoặc hiển thị attachment theo chính sách riêng.

**Khi nào nên dùng Jakarta Mail trực tiếp thay vì MimeMessageHelper?** Khi cần cấu trúc MIME hoặc thao tác part chuyên biệt mà helper không cung cấp. Vẫn nên dùng object model thay vì raw MIME string.

## 21. Tài liệu kỹ thuật liên quan

- **Spring Framework Mail — `MimeMessageHelper`:** tạo multipart message, `setText(...)`, `addInline(...)`, `addAttachment(...)`.
- **Spring Framework Mail — `JavaMailSender`:** tạo và gửi `MimeMessage`.
- **Jakarta Mail:** `MimeMessage`, `MimeBodyPart`, `MimeMultipart`, `DataHandler` và serialization MIME.
- **RFC 2045–2049 — MIME:** media type, transfer encoding và multipart.
- **RFC 2046 — MIME Media Types:** các subtype multipart như `mixed`, `alternative` và `related`.
- **RFC 2183 — Content-Disposition:** metadata `inline` và `attachment`.
- **RFC 2231 — MIME Parameter Value and Encoded Word Extensions:** tham số và filename có ký tự ngoài ASCII.
- **RFC 2392 — Content-ID and Message-ID URLs:** tham chiếu tài nguyên qua `cid:`.
- **RFC 5322 — Internet Message Format:** header, folding và cấu trúc message.

---

**Ghi nhớ:** tự ghép raw MIME dễ gây lỗi boundary, CRLF, charset, transfer encoding, binary attachment, multipart nesting, header injection và filename encoding. Trong Spring Framework Mail, ưu tiên `MimeMessageHelper` để tạo body plain text/HTML, inline resource và attachment; khi cần kiểm soát thấp hơn, dùng `MimeBodyPart` và `MimeMultipart` của Jakarta Mail. Hãy để thư viện serialize MIME và SMTP transport, đồng thời kiểm tra raw source cùng mail client mục tiêu trước khi phát hành.
