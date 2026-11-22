# Chống header injection khi gửi email bằng Spring Framework Mail

Khi ứng dụng gửi email, phần lớn lập trình viên quan tâm đến SMTP host, port, TLS, nội dung HTML và tệp đính kèm. Tuy nhiên, một nhóm lỗi bảo mật xảy ra ngay từ bước **tạo header của thông điệp**: dữ liệu do người dùng kiểm soát bị đưa vào `Subject`, `From`, `To`, `Reply-To` hoặc một header MIME khác mà không được kiểm tra đúng cách.

**Email header injection** là tình huống kẻ tấn công khiến dữ liệu vốn chỉ được phép là **giá trị của một trường** lại được diễn giải thành **một hoặc nhiều trường header mới**, hoặc làm thay đổi ranh giới giữa header và phần thân thông điệp. Kỹ thuật điển hình lợi dụng ký tự xuống dòng `CR` và `LF` trong dữ liệu đầu vào, đôi khi kết hợp với những cú pháp khác của email.

Trong ứng dụng Spring Framework Mail, cách phòng vệ quan trọng nhất là **không tự ghép raw email/SMTP message từ chuỗi không tin cậy**, chỉ sử dụng API có cấu trúc của `MimeMessageHelper`/Jakarta Mail, kiểm tra dữ liệu đầu vào theo **ngữ cảnh header**, giới hạn các trường người dùng được quyền điều khiển và bảo vệ các điểm dùng API mức thấp.

Bài học này giải thích nguyên lý tấn công, các bề mặt thường bị ảnh hưởng, ví dụ Java/Spring Mail, phương án kiểm thử và những giới hạn của các cơ chế bảo vệ liên quan như SPF, DKIM, DMARC và SMTP authentication.

## 1. Header email là gì?

Một email có hai phần logic chính: **header** và **body**, ngăn cách bởi một dòng trống theo định dạng Internet Message.

Ví dụ minh họa:

```text
From: Example <no-reply@example.org>
To: alice@example.net
Subject: Xác nhận đơn hàng
Date: Thu, 12 Nov 2026 09:00:00 +0000
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Cảm ơn bạn đã đặt hàng.
```

Header mô tả ai gửi, ai nhận, chủ đề, thời điểm và cách diễn giải nội dung. Body chứa văn bản, HTML hoặc cấu trúc MIME multipart. Một ứng dụng gửi email có thể phải tạo thêm `Reply-To`, `Cc`, `Bcc`, `Message-ID`, `Content-ID`, `Content-Disposition` và các trường mở rộng.

Các dòng header tuân theo cú pháp riêng của email. Một header thông thường có dạng:

```text
Field-Name: field value
```

Theo quy tắc truyền thống, dòng được kết thúc bằng cặp ký tự `CRLF` (carriage return + line feed). Dòng mới bắt đầu bằng một tên trường và dấu hai chấm có thể được diễn giải thành header khác. Trong khi đó, dòng tiếp theo bắt đầu bằng whitespace có thể là **folded header**; việc folding hợp lệ phải được thực hiện bởi bộ serialize header, không phải do người dùng nhập tùy ý.

### Những header phổ biến và mức ảnh hưởng

| Header | Mục đích | Rủi ro khi bị điều khiển |
|---|---|---|
| `Subject` | Chủ đề thư | Thêm header giả, làm sai chủ đề hoặc thay đổi cấu trúc |
| `From` | Người gửi hiển thị | Giả mạo danh tính gửi hoặc vượt chính sách sender |
| `To` / `Cc` / `Bcc` | Người nhận | Tạo người nhận ngoài dự kiến, rò rỉ hoặc gửi thư không được phép |
| `Reply-To` | Đích nhận thư trả lời | Chuyển phản hồi của khách sang mailbox khác |
| `Content-Type` | Loại nội dung/MIME boundary | Thay đổi cách mail client diễn giải body |
| `Content-Disposition` | Inline hoặc attachment, tên file | Làm sai metadata attachment hoặc đưa header phụ |
| `Content-ID` | ID tài nguyên inline | Tham chiếu sai part hoặc thao túng cấu trúc MIME |
| Header `X-*` tùy chỉnh | Correlation, tracking, routing | Chèn header mới nếu ứng dụng nối chuỗi trực tiếp |

Một số header trên có thể được ứng dụng tạo bằng dữ liệu đã xác thực; phần lớn **không nên cho client tùy ý quyết định**.

## 2. Header injection diễn ra như thế nào?

Xét một đoạn code tự tạo raw header:

```java
// Anti-pattern: tuyệt đối không dùng để dựng email gửi thật.
String rawMessage =
        "To: customer@example.net\r\n"
      + "Subject: " + userSubject + "\r\n"
      + "Content-Type: text/plain; charset=UTF-8\r\n"
      + "\r\n"
      + body;
```

Ở đây, `userSubject` lẽ ra chỉ được coi là nội dung một dòng của Subject. Nếu kẻ tấn công cung cấp chuỗi có ký tự `\r\n`, giá trị đó có thể làm parser chuyển sang một dòng header khác.

Ví dụ payload minh họa:

```text
Xác nhận đơn hàng\r\n
Bcc: unexpected@example.invalid
```

Khi được nối vào raw message, nó có thể tạo thành:

```text
To: customer@example.net
Subject: Xác nhận đơn hàng
Bcc: unexpected@example.invalid
Content-Type: text/plain; charset=UTF-8

Nội dung thư
```

Đây là minh họa nguy cơ khi **tự nối chuỗi vào raw headers**. Một triển khai gửi email cụ thể có thể từ chối header sai cú pháp, hoặc xác định SMTP envelope recipients độc lập với các header hiển thị; vì vậy **không phải việc thêm `Bcc` vào header luôn khiến SMTP gửi đến địa chỉ đó**. Nhưng nếu hệ thống lấy recipient từ header đã bị thao túng, hoặc tự xây SMTP envelope từ dữ liệu nhiễm bẩn, nguy cơ gửi ngoài dự kiến có thể trở thành thực tế.

Kết quả injection phụ thuộc cách ứng dụng tạo message, parser, thư viện và transport. Trong mọi trường hợp, dữ liệu do người dùng kiểm soát **không được có quyền thay đổi cấu trúc header**.

### Phân biệt CR và LF

- `\r` là carriage return (CR, U+000D).
- `\n` là line feed (LF, U+000A).
- `\r\n` là cặp CRLF dùng để kết thúc dòng theo cú pháp Internet Message.
- Một số thư viện/thiết bị cũng có thể chuẩn hóa các newline không đúng chuẩn. Do vậy, bộ kiểm tra đầu vào nên từ chối cả `\r` và `\n` khi chúng xuất hiện trong **giá trị header do người dùng cung cấp**, không chỉ từ chối đúng chuỗi `\r\n`.

Không nên chỉ thay `"\r\n"` bằng chuỗi rỗng rồi cho dữ liệu đi tiếp: đầu vào còn có thể chứa `\r` đơn lẻ, `\n` đơn lẻ, tab, các control character hoặc dạng Unicode gây nhầm lẫn hiển thị.

## 3. Vì sao đây là vấn đề bảo mật SMTP?

Ứng dụng thường được cấp quyền gửi email qua một SMTP account đã xác minh. Nếu đầu vào của người dùng làm thay đổi người nhận hoặc thông tin hiển thị, kẻ tấn công có thể lạm dụng uy tín và quota của account đó.

Hậu quả có thể bao gồm:

1. Gửi thêm thông điệp tới người nhận không được phép nếu luồng tạo recipient bị ảnh hưởng.
2. Gây giả mạo hoặc gây nhầm lẫn `From`/`Reply-To` để chuyển phản hồi đến nơi khác.
3. Thay đổi Content-Type hoặc cấu trúc MIME khiến mail client xử lý nội dung theo cách không mong muốn.
4. Làm phát sinh thư bị server từ chối, phá vỡ pipeline gửi hoặc tạo một hình thức từ chối dịch vụ ở tầng ứng dụng.
5. Lộ thông tin nếu email bị gửi tới mailbox thứ ba hoặc một bản ghi debug chứa headers bị tiêm nhiễm.
6. Làm log và audit không phản ánh chính xác recipient/subject mà nghiệp vụ đã phê duyệt.

Header injection là một dạng **output injection vào cú pháp email**, không đồng nhất với SQL injection hoặc HTML injection. Cả ba đều liên quan đầu vào không tin cậy, nhưng cách biểu diễn và cách phòng vệ khác nhau.

### Điểm tin cậy thường bị bỏ qua

Input không chỉ đến từ ô Subject trên form. Nó còn có thể xuất hiện trong:

- Tên khách hàng được chèn vào display name của `From` hoặc `To`.
- Địa chỉ `Reply-To` do khách hàng nhập.
- Tên file attachment lấy từ upload.
- Tên chiến dịch hoặc tên sản phẩm chèn vào Subject.
- Template variables đến từ database hoặc hệ thống đối tác.
- Metadata được đồng bộ từ CRM, CMS, webhook hoặc hàng đợi.
- Header `X-Correlation-ID` lấy nguyên văn từ HTTP request.
- Content-ID hoặc một phần Content-Type do người dùng cung cấp.

Dữ liệu lưu trong database **không tự nhiên trở thành dữ liệu đáng tin cậy**. Nếu nguồn gốc là người dùng hoặc hệ thống bên ngoài, phải xử lý theo ranh giới sử dụng cuối cùng.

## 4. Nguyên tắc phòng vệ nhiều lớp

Một thiết kế chống header injection tốt thường có các lớp sau:

| Lớp | Biện pháp | Mục đích |
|---|---|---|
| Thiết kế API | Không nhận raw MIME/SMTP header từ client | Giảm bề mặt tấn công |
| Kiểm tra đầu vào | Chặn CR/LF, control chars ở giá trị header | Ngăn chuyển dòng ngoài ý muốn |
| Parse theo kiểu dữ liệu | Dùng `InternetAddress` cho mailbox | Tránh tự tách/ghép địa chỉ |
| Tạo message | Dùng `MimeMessageHelper` và Jakarta Mail | Để thư viện encode, fold, serialize |
| Chính sách người gửi | From cố định/đã xác minh, Reply-To được kiểm soát | Ngăn giả mạo và chuyển hướng |
| MIME handling | Dùng `addInline` / `addAttachment`, không tự viết Content-* | Ngăn sửa cấu trúc part |
| Authorization | Kiểm tra được phép gửi đến ai, theo mục đích gì | Ngăn lạm dụng ngay cả với địa chỉ hợp lệ |
| Rate limiting và quota | Giới hạn số yêu cầu gửi | Giảm spam và DoS |
| Logging an toàn | Ghi ID/nhóm lỗi, không log raw input/header | Tránh phát tán payload và PII |
| Kiểm thử | Thử CR, LF, CRLF và dữ liệu bất thường | Phát hiện regression |

Không lớp nào đủ để thay thế hoàn toàn các lớp khác. `MimeMessageHelper` giúp tránh tự serialize header, nhưng không tự quyết định người dùng có quyền chọn `Reply-To` hay gửi đến một địa chỉ bất kỳ.

## 5. Không tự nối raw email hoặc gửi lệnh SMTP bằng String

Những cách làm sau tiềm ẩn rủi ro:

```java
// Sai: tự ghép raw MIME từ dữ liệu không tin cậy.
String header = "Subject: " + request.subject() + "\r\n";

// Sai: tự ghép địa chỉ SMTP envelope từ input không kiểm soát.
String smtpCommand = "RCPT TO:<" + request.recipient() + ">\r\n";

// Sai: tự xây các header MIME part.
String disposition =
        "Content-Disposition: attachment; filename=\"" +
        request.filename() + "\"\r\n";
```

Ngoài CRLF/header injection, cách này còn dễ sai charset, header folding, MIME boundary, binary transfer encoding và encoding filename.

Thay vào đó, làm việc với API:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom("no-reply@example.org");
helper.setTo(validatedRecipient);
helper.setSubject(validatedSubject);
helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");

mailSender.send(message);
```

Đoạn mã giả định `validatedRecipient` và `validatedSubject` đã qua kiểm tra theo ngữ cảnh. Với multipart, `MimeMessageHelper` tạo cấu trúc MIME cần thiết và Jakarta Mail xử lý việc serialize; ứng dụng không phải tự thêm `\r\n` hoặc viết lệnh SMTP `DATA`.

**Không nên dựa hoàn toàn vào việc “thư viện hiện tại chắc sẽ từ chối input xấu”.** Hành vi kiểm tra/encode có thể khác nhau giữa phiên bản thư viện và các API mức thấp. Hãy từ chối giá trị header chứa control chars trước khi truyền vào thư viện.

## 6. Validation cho giá trị header một dòng

Các giá trị do người dùng cung cấp để đặt vào một trường header thông thường nên được kiểm tra như **single-line text**. Một policy phòng thủ có thể:

- Bắt buộc không null và không rỗng sau khi trim.
- Giới hạn độ dài để giảm lạm dụng và lỗi client.
- Từ chối `CR`, `LF` và control characters.
- Từ chối ký tự phân tách dòng Unicode như `U+2028` và `U+2029` nếu input này được dùng làm trường hiển thị.
- Từ chối các ký tự điều khiển hướng văn bản Unicode khi nguy cơ spoofing liên quan đến sản phẩm.
- Không tự ghi nguyên đầu vào bị từ chối vào log.

### 6.1. Một validator dùng lại được

```java
package com.example.mail.security;

import java.util.Objects;

public final class MailHeaderValues {

    private MailHeaderValues() {
    }

    public static String singleLine(
            String fieldName,
            String raw,
            int maxLength) {

        Objects.requireNonNull(fieldName, "fieldName");
        if (raw == null) {
            throw new IllegalArgumentException(
                    fieldName + " must not be null");
        }

        String value = raw.strip();
        if (value.isEmpty() || value.length() > maxLength) {
            throw new IllegalArgumentException(
                    fieldName + " has invalid length");
        }

        for (int offset = 0; offset < value.length();) {
            int cp = value.codePointAt(offset);

            boolean forbidden =
                    Character.isISOControl(cp)
                    || cp == 0x2028      // LINE SEPARATOR
                    || cp == 0x2029      // PARAGRAPH SEPARATOR
                    || (cp >= 0x202A && cp <= 0x202E)
                    || (cp >= 0x2066 && cp <= 0x2069);

            if (forbidden) {
                throw new IllegalArgumentException(
                        fieldName + " contains unsafe characters");
            }

            offset += Character.charCount(cp);
        }

        return value;
    }
}
```

Policy này cố ý nghiêm ngặt: tab hoặc các ký tự điều khiển ngay trong đầu vào header sẽ bị từ chối. Điều đó không có nghĩa mọi ký tự bị từ chối đều tạo injection trong mọi mail client; nó giảm rủi ro với các giá trị dự kiến chỉ có một dòng.

`Character.isISOControl` bao gồm CR, LF và một số control characters khác. Các ký tự điều khiển hướng văn bản bị chặn thêm để giảm nguy cơ nội dung hiển thị đánh lừa người đọc. Nếu sản phẩm cần hỗ trợ một tập ký tự đặc biệt, hãy thiết kế policy theo trường và yêu cầu nghiệp vụ thay vì bỏ hẳn validation.

### 6.2. Vì sao nên từ chối thay vì tự sửa?

Giả sử input là:

```text
Đơn hàng mới\r\nBcc: audit@example.invalid
```

Nếu code chỉ xóa `\r\n`, giá trị trở thành `Đơn hàng mớiBcc: audit@example.invalid`. Nó không còn mở một header mới, nhưng đã bị thay đổi ngữ nghĩa và có thể xuất hiện trong thông tin gửi cho khách.

Với trường có cấu trúc hoặc dữ liệu có tác dụng bảo mật, **từ chối input sai** và yêu cầu sửa là cách dễ kiểm soát hơn. Trường hợp sản phẩm có yêu cầu chuẩn hóa whitespace (ví dụ thay nhiều khoảng trắng bằng một), phải định nghĩa rõ ràng và vẫn kiểm tra lại sau chuẩn hóa.

Không dùng validator header này để xử lý body email: nội dung `text/plain` và `text/html` hoàn toàn có thể chứa newline hợp lệ. Mỗi nơi đưa dữ liệu vào cần logic bảo vệ theo ngữ cảnh.

## 7. Kiểm tra địa chỉ người nhận bằng InternetAddress

Địa chỉ email có cú pháp riêng, không đơn thuần là “một chuỗi có dấu @”. Jakarta Mail cung cấp `InternetAddress` để parse và kiểm tra cú pháp mailbox.

Ví dụ:

```java
package com.example.mail.security;

import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class MailAddresses {

    private MailAddresses() {
    }

    public static InternetAddress singleMailbox(
            String raw) throws AddressException {

        String value = MailHeaderValues.singleLine(
                "recipient", raw, 320);

        InternetAddress address = new InternetAddress(value, true);
        address.validate();

        if (address.isGroup()
                || address.getAddress() == null
                || !value.equals(address.getAddress())) {
            throw new AddressException(
                    "Expected a single mailbox address");
        }

        return address;
    }
}
```

Trong ví dụ này, policy nhận **một địa chỉ mailbox thuần**, không nhận chuỗi kiểu `"Alice <alice@example.net>"` hoặc một danh sách có nhiều địa chỉ. Nếu API thực sự hỗ trợ display name hoặc danh sách người nhận, hãy parse rõ cấu trúc đó bằng API thích hợp và kiểm tra từng mailbox theo quyền.

`InternetAddress.validate()` là kiểm tra **cú pháp**, không kiểm tra mailbox có tồn tại, domain có thể nhận email hoặc người dùng có được phép gửi tới địa chỉ đó. Policy về danh sách nhận, domain, tenant và consent vẫn do ứng dụng quyết định.

### 7.1. Không cho form Subject quyết định To, Cc, Bcc

Ví dụ API gửi hóa đơn có thể nhận:

```json
{
  "invoiceId": "2f86c36d-028a-47c0-9e7b-9307bb46e14f"
}
```

Ứng dụng lấy recipient đã được xác thực từ bản ghi hóa đơn, thay vì cho client gửi kèm toàn bộ:

```json
{
  "to": "...",
  "cc": "...",
  "bcc": "...",
  "from": "...",
  "replyTo": "...",
  "headers": {"...": "..."}
}
```

Giảm quyền điều khiển input giúp phòng header injection và cả lạm dụng gửi email ngoài phạm vi. Với hệ thống gửi newsletter hoặc email theo danh sách, vẫn cần xác thực quyền, giới hạn số recipient, quota và chính sách consent.

### 7.2. Danh sách người nhận cần được biểu diễn theo kiểu dữ liệu

Nếu ứng dụng được phép gửi tới nhiều địa chỉ, không nhận một chuỗi CSV rồi ghép:

```java
// Tránh tự ghép.
String to = String.join(",", recipientsFromRequest);
```

Thay vào đó, kiểm tra từng phần tử:

```java
List<InternetAddress> parsed = recipients.stream()
        .map(raw -> {
            try {
                return MailAddresses.singleMailbox(raw);
            } catch (AddressException ex) {
                throw new IllegalArgumentException(
                        "Invalid recipient address");
            }
        })
        .toList();

helper.setTo(parsed.toArray(InternetAddress[]::new));
```

Đây là ví dụ Java 17+; `recipients` phải được giới hạn độ dài và kiểm tra quyền trước khi gọi. Cùng một address không nên được thêm nhiều lần nếu nghiệp vụ không yêu cầu.

## 8. Bảo vệ Subject và tên hiển thị Unicode

`Subject` thường kết hợp text cố định với một trường nghiệp vụ:

```java
String subject = "Đơn hàng " + order.getDisplayCode();
```

Nếu `getDisplayCode()` được lấy từ input bên ngoài, cần kiểm tra nó trước khi đưa vào header, dù field đã được lưu ở database.

```java
String orderCode = MailHeaderValues.singleLine(
        "orderCode", order.getDisplayCode(), 80);
String subject = MailHeaderValues.singleLine(
        "subject", "Xác nhận đơn hàng " + orderCode, 200);

helper.setSubject(subject);
```

Nếu mã đơn chỉ được phép gồm chữ số, chữ Latin và dấu gạch ngang, còn tốt hơn là kiểm tra bằng quy tắc domain mạnh hơn. Không dùng một validator text tổng quát thay cho domain validation khi đã có cấu trúc rõ ràng.

### 8.1. Unicode không phải injection

Email subject tiếng Việt như `"Thông báo đã nhận đơn hàng"` là dữ liệu hợp lệ. Đừng xử lý header injection bằng cách loại bỏ toàn bộ ký tự ngoài ASCII; làm vậy sẽ phá nội dung hợp pháp mà không giải quyết gốc rễ của raw string concatenation.

`MimeMessageHelper` cho phép cấu hình charset để Jakarta Mail encode header Unicode theo chuẩn phù hợp:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");
helper.setSubject("Xác nhận đơn hàng của bạn");
```

Ứng dụng không nên tự tạo encoded-word kiểu `=?UTF-8?B?...?=` cho Subject. Cũng không tự chèn newline để gập dòng dài; thư viện sở hữu công việc encoding và folding.

### 8.2. Tên hiển thị của người gửi

Tên hiển thị như “Dịch vụ Khách hàng” nên được kiểm tra một dòng và gắn vào `InternetAddress` qua API:

```java
String displayName = MailHeaderValues.singleLine(
        "senderName", "Dịch vụ Khách hàng", 120);

InternetAddress sender = new InternetAddress(
        "no-reply@example.org",
        displayName,
        "UTF-8");
helper.setFrom(sender);
```

Với các hệ thống nhiều tenant, không cho tenant nhập tùy ý địa chỉ From chưa được xác minh. Địa chỉ gửi cần thuộc các identity/domain mà provider và chính sách doanh nghiệp cho phép.

## 9. Tách quyền điều khiển From và Reply-To

Không nên cho người dùng đổi `From` theo ý muốn chỉ vì email được gửi từ hệ thống. Một thiết kế an toàn hơn:

- `From` lấy từ cấu hình sender đã được xác minh.
- `Reply-To`, nếu có tính năng cho phép, phải được parse và cấp quyền theo mục đích.
- `To` xác định từ người nhận hợp lệ của nghiệp vụ.
- `Cc`/`Bcc` chỉ được thiết lập theo quy tắc rõ ràng, không lấy từ một chuỗi Subject/body.

Ví dụ:

```java
helper.setFrom("support@example.org");
helper.setTo(customerAddress);
helper.setReplyTo("support@example.org");
```

Nếu hệ thống contact form muốn nhận thư trả lời trực tiếp cho người gửi form, có thể có cách cho phép `Reply-To` là địa chỉ đã kiểm tra. Tuy nhiên, cần đánh giá nguy cơ mạo danh, gửi thư tới bên thứ ba hoặc lạm dụng phản hồi tự động.

Một thiết kế thận trọng là đặt `Reply-To` về mailbox hỗ trợ do doanh nghiệp kiểm soát, còn địa chỉ liên hệ của người dùng được lưu trong hệ thống nghiệp vụ có phân quyền. Không phải mọi địa chỉ “đúng cú pháp” đều được phép sử dụng làm reply destination.

### Đừng tự thêm Return-Path

`Return-Path` có quan hệ với envelope/đường xử lý của mail transport và thường được MTA ở phía nhận tạo theo quy tắc của hệ thống gửi. Không nên để client điều khiển `Return-Path` bằng custom header. Với nhu cầu cấu hình envelope sender/bounce address, dùng tính năng chính thức của SMTP provider hoặc Jakarta Mail transport theo chính sách đã kiểm soát.

## 10. Chặn injection qua custom headers

Custom header có thể dùng để ghi correlation ID hoặc metadata hỗ trợ đối soát:

```java
message.setHeader("X-Correlation-ID", jobId.toString());
```

Nếu header name hoặc value lấy nguyên từ request, rủi ro tăng lên:

```java
// Anti-pattern.
message.addHeader(request.headerName(), request.headerValue());
```

`MimeMessage.setHeader(...)` và `addHeader(...)` là API mức thấp. Không nên giả định chúng thực hiện toàn bộ kiểm tra authorization và ngữ nghĩa field cần thiết cho ứng dụng.

### 10.1. Header name phải có danh sách cho phép

Để client không thể tự yêu cầu tạo `Bcc`, `From` hoặc `Content-Type`, đừng mở một API “thêm header tùy ý” cho người dùng. Dùng field name cố định trong mã:

```java
public static final String CORRELATION_HEADER = "X-Correlation-ID";

message.setHeader(
        CORRELATION_HEADER,
        jobId.toString());
```

Nếu thực sự cần nhiều header, cho chúng vào một enum/danh mục cố định do hệ thống quản lý. Header name theo RFC có cú pháp riêng; một regex bảo thủ cho internal custom name có thể là `^[A-Za-z0-9-]+$`, nhưng **allowlist tên trường** vẫn quan trọng hơn một regex chung.

### 10.2. Header value phải đúng kiểu

Ví dụ correlation ID dạng UUID:

```java
UUID correlationId = UUID.fromString(request.correlationId());
message.setHeader("X-Correlation-ID", correlationId.toString());
```

Code không lấy raw string bất kỳ và biến nó thành header. Nếu người dùng gửi một chuỗi chứa newline hoặc thêm trường bất thường, `UUID.fromString(...)` sẽ từ chối.

Nếu custom header có giá trị text tự do, phải dùng bộ kiểm tra single-line và encoding/serialization phù hợp theo API. Không được ghép một chuỗi chứa `\r\n` thành nhiều header thủ công.

### 10.3. Cẩn trọng với Message-ID và Content-ID

Message-ID phục vụ định danh thư; Content-ID dùng để tham chiếu MIME part inline. Không tự tạo từ chuỗi người dùng không đáng tin cậy hoặc nhét payload tùy ý vào giữa dấu `<...>`.

Với ảnh inline, dùng:

```java
helper.setText(
        "<p>Biểu trưng:</p><img src=\"cid:brand-logo\" alt=\"Logo\">",
        true);
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

`brand-logo` là Content-ID do ứng dụng kiểm soát, không phải dữ liệu tùy ý từ client. Nếu cần nhiều ảnh động, tạo identifier an toàn trong ứng dụng và đảm bảo chúng khớp với các giá trị `cid:...` trong HTML.

## 11. Attachment filename và MIME parameter injection

Tên file đính kèm thường được biểu diễn trong các tham số MIME như `filename` của `Content-Disposition`. Nếu một tên file bên ngoài chứa dấu ngoặc kép, dấu chấm phẩy, control characters hoặc đường dẫn, việc tự nối raw header có thể làm hỏng cấu trúc:

```java
// Không tự dựng Content-Disposition như vậy.
String rawHeader = "Content-Disposition: attachment; filename=\""
        + userFilename + "\"\r\n";
```

Một tên file nguy hiểm có thể còn tiết lộ đường dẫn máy chủ hoặc gây lỗi khi người nhận lưu file. Hãy tạo tên hiển thị từ dữ liệu đã được kiểm soát và để API tạo MIME part.

Ví dụ:

```java
String filename = "invoice-" + invoiceNumber + ".pdf";
filename = MailHeaderValues.singleLine(
        "filename", filename, 160);

if (filename.indexOf('/') >= 0
        || filename.indexOf('\\') >= 0) {
    throw new IllegalArgumentException(
            "Filename must not contain path separators");
}

helper.addAttachment(
        filename,
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf");
```

Trong ví dụ, `invoiceNumber` cũng cần được kiểm tra theo domain (chỉ chữ số/chữ cái và dấu phân cách được phép), thay vì chỉ dựa vào bước kiểm tra cuối. Không sử dụng `Path.toString()` hoặc đường dẫn file local như tên attachment.

Nếu filename có Unicode, thư viện mail có thể encode tham số theo cơ chế thích hợp; các mail client có mức tương thích khác nhau. Không nên tự đưa encoded-word hoặc raw CRLF vào tên file để “sửa” vấn đề tương thích.

## 12. Không nhầm header injection với HTML injection

Hai dạng dữ liệu được xử lý ở hai ngữ cảnh khác nhau:

```java
// Header: phải là một giá trị single-line, dùng API mail.
helper.setSubject(validatedSubject);

// HTML body: cần escape theo ngữ cảnh HTML/template.
helper.setText(renderedHtml, true);
```

Chống header injection **không thay thế HTML escaping**. Nếu người dùng nhập:

```html
<img src="https://external.example.invalid/tracker">
```

và ứng dụng chèn thẳng vào HTML, đó là vấn đề của HTML/template content, không phải vì CRLF tạo header mới. Cần dùng template engine có escaping theo ngữ cảnh và kiểm soát URL/HTML được phép.

Ngược lại, HTML escape các ký tự `<`, `>` và `&` trong Subject không đủ chống CR/LF header injection. Hãy áp dụng:

| Dữ liệu | Ranh giới | Biện pháp phù hợp |
|---|---|---|
| Subject | Email header value | Single-line validation + `setSubject` |
| From/To/Reply-To | Mailbox/address | Single-line validation + `InternetAddress` + authorization |
| Display name | Address header phrase | Validation + API encoding tên |
| Tên file | MIME parameter | Filename policy + `addAttachment` |
| Content-ID | MIME identifier | ID do ứng dụng tạo + `addInline` |
| HTML body | HTML markup | Template escaping + URL policy |
| Text body | Plain text | Giới hạn độ dài/nội dung theo nghiệp vụ; newline hợp lệ |
| Raw MIME | Cấu trúc message | Không nhận từ client; thư viện serialize |

Một lệnh “sanitize mọi chuỗi” bằng cách xóa các ký tự đặc biệt vừa có thể phá dữ liệu hợp lệ, vừa không đủ cho từng ngữ cảnh.

## 13. Ví dụ Spring Mail: service xây dựng email an toàn

Giả sử ứng dụng gửi email xác nhận đăng ký. Client chỉ được truyền thông tin cần thiết của đăng ký; người nhận và địa chỉ gửi được lấy từ nguồn đã xác thực. Service không nhận danh sách header tùy ý.

### 13.1. Định nghĩa request và dữ liệu nghiệp vụ

```java
package com.example.mail;

import java.util.UUID;

public record RegistrationMailCommand(
        UUID registrationId,
        String recipientEmail,
        String customerName,
        String confirmationCode) {
}
```

Đoạn record minh họa payload nội bộ do application service tạo, **không phải DTO nên bind trực tiếp toàn bộ từ HTTP request** mà không kiểm tra quyền. Dữ liệu như confirmation code cần có quy tắc định dạng riêng và không được log.

### 13.2. Dịch vụ tạo MimeMessage

```java
package com.example.mail;

import com.example.mail.security.MailAddresses;
import com.example.mail.security.MailHeaderValues;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RegistrationMailService {

    private final JavaMailSender sender;
    private final String verifiedFrom;

    public RegistrationMailService(
            JavaMailSender sender,
            @Value("${app.mail.verified-from}") String verifiedFrom) {
        this.sender = sender;
        this.verifiedFrom = verifiedFrom;
    }

    public void sendConfirmation(RegistrationMailCommand command)
            throws MessagingException {

        InternetAddress to =
                MailAddresses.singleMailbox(command.recipientEmail());
        InternetAddress from =
                MailAddresses.singleMailbox(verifiedFrom);

        String customerName = MailHeaderValues.singleLine(
                "customerName", command.customerName(), 120);

        // Một mã nghiệp vụ có thể có policy chặt hơn.
        String confirmationCode = MailHeaderValues.singleLine(
                "confirmationCode", command.confirmationCode(), 80);
        String subject = MailHeaderValues.singleLine(
                "subject", "Xác nhận đăng ký", 200);

        String plainText = """
                Xin chào %s,

                Mã xác nhận của bạn: %s
                Không chia sẻ mã này với người khác.
                """.formatted(customerName, confirmationCode);

        // Dữ liệu động trong HTML phải được escape riêng.
        String html = """
                <html lang="vi">
                  <body>
                    <p>Xin chào %s,</p>
                    <p>Mã xác nhận: <strong>%s</strong></p>
                    <p>Không chia sẻ mã này với người khác.</p>
                  </body>
                </html>
                """.formatted(
                escapeHtml(customerName),
                escapeHtml(confirmationCode));

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom(from);
        helper.setTo(to);
        helper.setSubject(subject);
        helper.setText(plainText, html);

        sender.send(message);
    }

    private static String escapeHtml(String value) {
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
```

Ở đây:

- `From` lấy từ cấu hình sender đã xác minh.
- `To` được kiểm tra một mailbox có cú pháp phù hợp.
- `Subject` là một dòng do ứng dụng quyết định.
- Tên khách hàng không được đưa vào header tùy ý; ví dụ kiểm tra và escape theo ngữ cảnh body.
- `helper.setText(plainText, html)` tạo các body alternative mà không cần tự ghép raw MIME.
- JavaMailSender chịu trách nhiệm serialize và gửi thông điệp.

Đây là ví dụ giảng giải luồng gửi, không thay thế thiết kế mã xác minh an toàn: confirmation code phải được sinh từ cơ chế đủ mạnh, có hạn sử dụng, giới hạn lần thử, trạng thái thu hồi và không được lộ trong logs. Với HTML phức tạp, nên dùng template engine có auto-escaping thay vì xây HTML bằng `String.formatted(...)`.

**Lưu ý:** `MimeMessageHelper(message, false, charset)` tắt multipart và không phù hợp khi cần gửi cả hai bản `text/plain` và `text/html` bằng `setText(plain, html)`. Ví dụ dùng `true` để tạo cấu trúc multipart; nếu cần kiểm soát cách lồng các phần, hãy chọn multipart mode tường minh như mục tiếp theo.

### 13.3. Chọn multipart mode một cách tường minh

Để gửi cả plain text và HTML, tạo helper ở chế độ multipart:

```java
MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom(from);
helper.setTo(to);
helper.setSubject(subject);
helper.setText(plainText, html);
sender.send(message);
```

`MULTIPART_MODE_MIXED_RELATED` hỗ trợ cấu trúc multipart khi cần body alternative, inline resource và attachment. Với email không cần attachment, có thể chọn một mode khác phù hợp, nhưng không tạo multipart/alternative bằng cách nối chuỗi raw.

## 14. Kiểm soát input tại API boundary

Xác thực tại mail service là một lớp bảo vệ quan trọng, nhưng API nhận dữ liệu cũng cần giới hạn những gì có thể được yêu cầu.

### 14.1. Không nhận một đối tượng có trường headers tùy ý

Tránh API:

```json
{
  "smtpServer": "...",
  "from": "...",
  "to": "...",
  "subject": "...",
  "headers": {
    "Any-Header": "Any-Value"
  },
  "rawMime": "..."
}
```

Trừ khi bạn đang phát triển một dịch vụ mail relay chuyên biệt với kiểm soát nghiêm ngặt, API này trao quá nhiều quyền cho client. Thay vào đó, nhận các trường nghiệp vụ:

```json
{
  "orderId": "31b72f8d-621a-4420-aa06-a3de7fe10c92"
}
```

Application service xác thực quyền truy cập đơn hàng, suy ra recipient được phép và chọn template, subject, From/Reply-To cố định.

### 14.2. Bean Validation chỉ là một lớp

Có thể thêm ràng buộc ở DTO:

```java
public record ContactFormRequest(
        @NotBlank
        @Size(max = 120)
        String displayName,

        @NotBlank
        @Email
        String replyEmail,

        @NotBlank
        @Size(max = 5000)
        String message) {
}
```

Các annotation như `@Email` và `@Size` giúp kiểm tra định dạng và độ dài, nhưng **không tự thay thế bộ kiểm tra một dòng, parse địa chỉ và quyền dùng Reply-To**. Một annotation/regex email có thể cho phép nhiều dạng hợp lệ theo chuẩn nhưng không phù hợp policy nội bộ của sản phẩm.

### 14.3. Chặn input tại nơi nó được dùng

Một trường có thể đi qua nhiều lớp:

```text
HTTP request
   |
   v
Validation DTO
   |
   v
Application service / database
   |
   v
Mail job / event
   |
   v
Mail worker
   |
   v
MimeMessageHelper / Jakarta Mail
```

Validation ở controller giúp trả lỗi sớm, nhưng mail worker vẫn nên kiểm tra dữ liệu header đầu ra vì nó có thể nhận job từ nguồn khác, dữ liệu lưu cũ hoặc event từ hệ thống bên ngoài. Không nên xem dữ liệu từ queue là “đã được tin cậy” chỉ vì đến từ bên trong mạng.

## 15. Xử lý trường hợp lỗi: fail closed và không gửi

Khi phát hiện giá trị header không hợp lệ, cách xử lý chuẩn là **không tạo/gửi message đó**.

Ví dụ:

```java
try {
    String subject = MailHeaderValues.singleLine(
            "subject", userSuppliedSubject, 200);
    helper.setSubject(subject);
} catch (IllegalArgumentException ex) {
    audit.recordRejectedMailInput(mailJobId, "SUBJECT_INVALID");
    throw new InvalidMailInputException(
            "Mail request contains invalid header data");
}
```

Trong API công khai, trả phản hồi validation error phù hợp thay vì trả raw invalid value hoặc stack trace. Trong queue worker, đưa job về trạng thái lỗi vĩnh viễn nếu dữ liệu không thể sửa; đừng retry vô hạn một payload injection không thay đổi.

### Phân biệt lỗi dữ liệu với lỗi SMTP tạm thời

| Loại lỗi | Retry? | Cách xử lý |
|---|---|---|
| Subject chứa newline | Không tự động | Từ chối input, sửa nguồn |
| Recipient chứa control chars | Không tự động | Từ chối/đánh dấu invalid |
| Custom header name không nằm allowlist | Không | Không tạo header |
| MIME part filename sai policy | Không tự động | Từ chối/chuẩn hóa theo chính sách |
| SMTP timeout | Có thể | Retry có backoff/deadline |
| SMTP rate limit 4xx | Có thể | Chậm lại theo provider policy |
| SMTP AUTH failure | Không nên retry mù | Kiểm tra credentials/cấu hình |

Không biến `InvalidMailInputException` thành một lỗi “temporary SMTP” rồi đẩy vào queue vô thời hạn. Đây là lỗi chính sách hoặc dữ liệu, không phải hạ tầng mạng.

## 16. Logging và monitoring khi phát hiện header injection

Đầu vào nghi ngờ injection có thể chứa địa chỉ email, token hoặc thông tin cá nhân. Không nên log nguyên payload:

```java
// Không làm như vậy:
log.warn("Rejected suspicious subject: {}", rawSubject);
```

Ghi một event đã chuẩn hóa:

```java
log.warn(
        "mail_input_rejected jobId={} field={} reason={}",
        jobId,
        "subject",
        "UNSAFE_HEADER_CONTROL_CHARACTER");
```

Có thể đo thêm:

| Metric | Ý nghĩa |
|---|---|
| `mail.header_validation.rejected` | Số lần chặn giá trị header sai |
| `mail.recipient_validation.failed` | Số email address không đáp ứng policy |
| `mail.send.attempts` | Số lần gửi thực sự bắt đầu |
| `mail.send.rejected_by_policy` | Số job bị từ chối trước SMTP |
| `mail.smtp.submit_failed` | Số lần submission lỗi hạ tầng/provider |

Giữ các tag có cardinality thấp: `field=subject/from/to/reply_to` và `reason=control_char/invalid_address/unauthorized_sender`. Không đưa raw subject, recipient, job ID tùy ý, payload hoặc exception message vào metric labels.

Nếu lượng đầu vào bị từ chối tăng đột biến, hệ thống có thể đang bị thử nghiệm injection hoặc có lỗi integration. Việc phát hiện này nên kích hoạt quan sát và giới hạn tốc độ, không phải tự in nguyên payload ra log để phân tích.

## 17. Kiểm thử chống CRLF header injection

Kiểm thử cần xác nhận cả validation và cấu trúc email không xuất hiện trường ngoài dự kiến. Ưu tiên test với giá trị giả, không gửi tới SMTP thật.

### 17.1. Unit test cho giá trị header

Ví dụ JUnit 5:

```java
package com.example.mail.security;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MailHeaderValuesTest {

    @Test
    void rejectsCrLfAndStandaloneNewlines() {
        String[] inputs = {
                "Đơn hàng\r\nBcc: unexpected@example.invalid",
                "Đơn hàng\nBcc: unexpected@example.invalid",
                "Đơn hàng\rBcc: unexpected@example.invalid",
                "Đơn hàng\u2028Bcc: unexpected@example.invalid",
                "Đơn hàng\u2029Bcc: unexpected@example.invalid"
        };

        for (String input : inputs) {
            assertThrows(
                    IllegalArgumentException.class,
                    () -> MailHeaderValues.singleLine(
                            "subject", input, 200));
        }
    }

    @Test
    void acceptsVietnameseSubject() {
        String subject = "Xác nhận đơn hàng tháng Mười Một";

        assertEquals(
                subject,
                MailHeaderValues.singleLine(
                        "subject", subject, 200));
    }

    @Test
    void rejectsNullOrBlank() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailHeaderValues.singleLine(
                        "subject", null, 200));
        assertThrows(
                IllegalArgumentException.class,
                () -> MailHeaderValues.singleLine(
                        "subject", "  ", 200));
    }
}
```

Test này chỉ kiểm tra hàm validator. Một bài kiểm thử tích hợp cần tạo message qua chính mail service của dự án, bảo đảm không có header do input bổ sung được sinh ra.

### 17.2. Unit test cho mailbox

```java
import static org.junit.jupiter.api.Assertions.*;
import jakarta.mail.internet.AddressException;
import org.junit.jupiter.api.Test;

class MailAddressesTest {

    @Test
    void acceptsSingleMailbox() throws Exception {
        assertEquals(
                "alice@example.net",
                MailAddresses.singleMailbox(
                        "alice@example.net").getAddress());
    }

    @Test
    void rejectsInjectedAdditionalHeader() {
        assertThrows(
                IllegalArgumentException.class,
                () -> MailAddresses.singleMailbox(
                        "alice@example.net\r\nBcc: extra@example.invalid"));
    }

    @Test
    void rejectsMailboxListInSingleMailboxField() {
        assertThrows(
                AddressException.class,
                () -> MailAddresses.singleMailbox(
                        "alice@example.net, bob@example.net"));
    }
}
```

Tùy đường đi của parser, exception cụ thể có thể là `AddressException` hoặc exception từ policy; test của ứng dụng nên xác định rõ contract lỗi và không để input chưa kiểm tra lọt đến thư viện gửi.

### 17.3. Kiểm tra header sau khi dựng MimeMessage

Có thể dùng `Session` trong bộ nhớ, không cần kết nối SMTP:

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.springframework.mail.javamail.MimeMessageHelper;

Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);

MimeMessageHelper helper = new MimeMessageHelper(
        message, false, "UTF-8");
helper.setFrom("no-reply@example.org");
helper.setTo("alice@example.net");
helper.setSubject(
        MailHeaderValues.singleLine(
                "subject", "Xác nhận đăng ký", 200));
helper.setText("Nội dung thử nghiệm", false);
message.saveChanges();

// Trong test, duyệt các header do ứng dụng cho phép và
// xác nhận không có header phát sinh từ input sai.
```

Để kiểm thử end-to-end, dùng một fake/recording mail sender hoặc SMTP sink như Mailpit. Không sử dụng tài khoản production để thử payload CRLF và không gửi dữ liệu thử đến hộp thư khách hàng thật.

### 17.4. Các trường hợp cần bao phủ

| Trường hợp | Kỳ vọng |
|---|---|
| Subject chứa `\r\nBcc:...` | Từ chối trước SMTP |
| Subject chứa `\n` hoặc `\r` đơn | Từ chối |
| Subject chứa Unicode line separator | Từ chối theo policy |
| Subject tiếng Việt hợp lệ | Gửi đúng sau encoding |
| Recipient chứa CRLF | Từ chối |
| Recipient chứa nhiều mailbox khi field chỉ cho một | Từ chối |
| Reply-To không thuộc policy | Từ chối |
| Custom header name từ client | Không nhận hoặc bị allowlist chặn |
| Filename chứa CRLF | Từ chối |
| Filename chứa path separator | Từ chối theo policy |
| Plain text body chứa newline | Vẫn hợp lệ |
| HTML body có input người dùng | Escape theo ngữ cảnh HTML |
| Job được replay từ queue với dữ liệu cũ | Validation vẫn chạy ở worker |
| Invalid header phát sinh trong retry | Đánh dấu lỗi dữ liệu, không retry SMTP vô hạn |

## 18. Header injection không được SPF, DKIM, DMARC tự động ngăn chặn

Các cơ chế xác thực email có mục tiêu khác:

| Cơ chế | Giải quyết điều gì? | Có thay validation đầu vào header? |
|---|---|---|
| SMTP AUTH | Client được phép dùng SMTP submission server | Không |
| STARTTLS / implicit TLS | Bảo vệ kết nối SMTP theo cấu hình | Không |
| SPF | Kiểm tra nguồn gửi được ủy quyền cho domain envelope | Không |
| DKIM | Chữ ký xác thực một số header/body theo chính sách ký | Không |
| DMARC | Chính sách alignment dựa trên SPF/DKIM và From domain | Không |
| Header validation + API có cấu trúc | Ngăn input tự mở thêm trường hoặc thay cấu trúc | Có, đúng mục tiêu |

Một message được tạo từ backend đã xác thực SMTP vẫn có thể mang nội dung hoặc headers không được phép nếu ứng dụng đặt chúng vào message. DKIM có thể ký chính message sai đó; chữ ký không tự chứng minh Subject/Reply-To đã được người dùng cho phép.

Vì vậy, chống header injection phải xảy ra **trước khi message được serialize và gửi**, không chỉ ở tầng DNS authentication hoặc mail gateway.

## 19. Phân biệt header injection và SMTP command injection

Hai vấn đề có liên quan nhưng ở hai lớp:

**Header injection** thay đổi cấu trúc hoặc các trường trong Internet Message, ví dụ mở thêm một header từ `Subject`.

**SMTP command injection** cố làm dữ liệu ngoài ý muốn trở thành lệnh giao thức SMTP, ví dụ ảnh hưởng các lệnh `MAIL FROM`, `RCPT TO` hoặc `DATA` khi một ứng dụng tự viết raw socket protocol.

`JavaMailSender`/Jakarta Mail thực hiện SMTP transport theo API, giúp tránh việc ứng dụng tự xây lệnh giao thức từ chuỗi. Tuy nhiên, ứng dụng vẫn phải kiểm tra đầu vào và quyền gửi.

Đừng coi “chỉ dùng một connection SMTP đã xác thực” là ranh giới đủ an toàn. SMTP server không biết người dùng nào trong ứng dụng đã được phép tạo email hay chuyển hướng Reply-To.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Trường `Bcc` xuất hiện ngoài dự kiến | Dữ liệu được ghép vào raw MIME/header | Không nối header, kiểm tra CRLF |
| Subject chứa các dòng lạ | Đầu vào có newline/control chars | Từ chối giá trị single-line |
| Người nhận ngoài phạm vi | To/Cc/Bcc lấy từ client mà thiếu authorization | Chọn recipient từ dữ liệu nghiệp vụ được xác thực |
| Reply-To trỏ sang mailbox không mong muốn | Cho phép người dùng đặt Reply-To tùy ý | Parse địa chỉ và áp policy |
| Header Unicode hiển thị lỗi | Tự mã hóa/fold header | Dùng charset UTF-8 và Jakarta Mail serialization |
| Filename làm hỏng MIME | Tự ghép Content-Disposition | Dùng `addAttachment` và filename policy |
| Nội dung user trở thành header mới | Raw message concat với CRLF | Validation và API typed |
| Không chặn được sau khi xóa `\r\n` | Vẫn có CR/LF đơn hoặc control khác | Kiểm tra code point và fail closed |
| Email đúng cú pháp nhưng sender giả | Không kiểm soát From/Reply-To | Sender verified và authorization |
| Queue retry mãi một job sai header | Phân loại invalid input là lỗi SMTP tạm thời | Đưa job sang permanent validation failure |
| Log chứa nguyên payload injection | Log raw subject/exception | Ghi field/reason code, không ghi input |
| Chỉ kiểm tra ở controller, job replay vẫn lỗi | Bỏ qua validation trong worker | Kiểm tra tại nơi xây MIME |
| Email có DKIM mà vẫn sai header | Nhầm xác thực domain với validation input | Kiểm soát message trước khi ký/gửi |

### Quy trình xử lý khi phát hiện input nghi ngờ

1. Ngừng tạo message từ dữ liệu đã bị xác định không hợp lệ.
2. Ghi event từ chối với `jobId`, tên field và loại lỗi đã chuẩn hóa; không ghi nguyên giá trị.
3. Phân biệt lỗi nhập liệu thông thường với mẫu tấn công lặp lại.
4. Giới hạn tốc độ và kiểm tra quyền của nguồn phát yêu cầu.
5. Kiểm tra các con đường tạo email khác (admin panel, queue worker, import tool, webhook).
6. Nếu đã có email gửi ngoài dự kiến, xử lý như một sự cố gửi thư/lộ dữ liệu phù hợp, kiểm tra provider logs và quyền recipient.
7. Bổ sung test để chặn tái diễn.

## 21. Những nguyên tắc cần nhớ

1. Không cho client gửi raw MIME hoặc một map header tùy ý nếu nghiệp vụ không thực sự yêu cầu.
2. Không nối trực tiếp `Subject`, `From`, `To`, `Reply-To`, Content-Type hoặc Content-Disposition bằng chuỗi.
3. Với giá trị header do người dùng cung cấp, yêu cầu single-line và từ chối CR/LF/control characters.
4. Parse mailbox bằng `InternetAddress`; thêm authorization, sender verification và recipient policy.
5. Dùng `MimeMessageHelper` để đặt header cơ bản, text/html, ảnh inline và attachment.
6. Để Jakarta Mail lo charset encoding và line folding; không tự chèn newline vào Subject Unicode.
7. Với custom header, dùng tên field cố định/allowlist và giá trị có kiểu, không nhận raw string.
8. Coi dữ liệu từ database, queue và đối tác là không tin cậy tại ranh giới tạo MIME.
9. Chặn input sai thay vì cố gửi tiếp; không retry vô hạn lỗi validation.
10. Tránh log dữ liệu injection/recipient/subject và theo dõi số lần từ chối bằng metric an toàn.
11. Kiểm thử cả CRLF, CR/LF đơn, Unicode separators, attachment name và nhiều recipient.
12. Đừng nhầm SPF/DKIM/DMARC, TLS hoặc SMTP AUTH với validation của header.

## 22. Câu hỏi thường gặp

**Header injection là gì?** Là việc dữ liệu đáng lẽ chỉ thuộc một header value bị diễn giải thành một header mới hoặc làm thay đổi ranh giới header/body, thường do CRLF khi ứng dụng tự ghép raw email.

**Chỉ cần chặn chuỗi `\r\n` là đủ không?** Không. Nên từ chối cả CR đơn, LF đơn và các control chars không phù hợp cho giá trị header một dòng. Tránh phụ thuộc vào một phép replace duy nhất.

**Có cần cấm tiếng Việt trong Subject không?** Không. Tiếng Việt là nội dung hợp lệ; hãy dùng UTF-8 và API encode/fold header của Jakarta Mail.

**Nếu đã dùng `MimeMessageHelper` có cần validate không?** Có. Helper cung cấp API có cấu trúc nhưng không quyết định authorization, sender policy, logic Reply-To hoặc độ dài/cú pháp riêng của ứng dụng. Các API mức thấp cũng có thể bỏ qua kiểm tra nghiệp vụ.

**Có nên dùng regex email đơn giản như `.+@.+`?** Không nên coi đó là kiểm tra đầy đủ. Dùng parser mailbox như `InternetAddress`, validation theo chính sách và xác minh quyền.

**Vì sao không nên ghép Subject vào một raw string?** Vì newline từ input có thể bị hiểu thành ranh giới giữa các header. `helper.setSubject(...)` tách giá trị khỏi cấu trúc message tốt hơn.

**Có nên cho khách hàng chọn From email?** Chỉ khi hệ thống có cơ chế xác minh sender/domain và quyền rõ ràng. Thường nên dùng một địa chỉ From đã được xác minh trong cấu hình.

**Reply-To có rủi ro không?** Có. Dù không thêm header mới, một Reply-To sai chính sách có thể khiến người nhận gửi phản hồi chứa thông tin nhạy cảm sang địa chỉ do kẻ tấn công kiểm soát.

**Bcc injection có luôn gửi thêm email không?** Không nhất thiết. SMTP envelope recipients có thể tách khỏi header hiển thị và transport có thể loại hoặc bỏ qua Bcc header. Nhưng không được dựa vào điều này để cho phép thay đổi header trái phép.

**Có thể đặt tên file từ người dùng không?** Có thể nếu đã kiểm tra filename policy, loại bỏ path separator/control chars và dùng `MimeMessageHelper.addAttachment(...)`. Tránh tự xây Content-Disposition.

**Header `X-Correlation-ID` có an toàn không?** Nếu tên do ứng dụng cố định và giá trị là ID có kiểu như UUID được tạo/parse hợp lệ, rủi ro thấp hơn. Không nhận tên/value tùy ý từ request.

**Có thể lưu Subject vào database rồi gửi sau mà không cần validate lại?** Không nên giả định dữ liệu lưu sẵn luôn an toàn. Worker phải kiểm tra đầu ra header khi xây message, đặc biệt khi job có thể đến từ import, webhook hoặc phiên bản code cũ.

**Header injection khác HTML injection thế nào?** Header injection thao túng cú pháp email header; HTML injection thay đổi markup trong phần thân. Cần phương pháp escaping/validation riêng cho từng ngữ cảnh.

**SMTP AUTH hoặc DKIM có chặn header injection không?** Không. Chúng xác thực client gửi hoặc domain/chữ ký, không kiểm chứng input nghiệp vụ đã được đưa vào header đúng cách.

**Khi phát hiện injection nên log toàn bộ payload để điều tra không?** Không theo mặc định. Payload có thể chứa địa chỉ hoặc dữ liệu nhạy cảm; ghi field, loại lỗi, job ID và metadata cần thiết, xử lý chẩn đoán chi tiết qua quy trình có phân quyền.

**Test có cần SMTP server thật không?** Không. Validator có thể unit test thuần Java; MIME có thể được tạo bằng Jakarta Mail Session trong bộ nhớ hoặc dùng fake sender/SMTP sink. Không gửi payload thử đến hộp thư thật.

## 23. Tài liệu kỹ thuật liên quan

- **Spring Framework Mail:** `JavaMailSender` và `MimeMessageHelper`, đặc biệt `setSubject`, `setTo`, `setReplyTo`, `addInline` và `addAttachment`.
- **Jakarta Mail / Angus Mail:** `InternetAddress`, `MimeMessage`, header API và MIME serialization.
- **RFC 5322 — Internet Message Format:** cú pháp các trường header, folding và CRLF.
- **RFC 6532 — Internationalized Email Headers:** xử lý header quốc tế hóa.
- **RFC 2045–2049 — MIME:** media type, encoding và multipart.
- **RFC 2183 — Content-Disposition:** metadata inline/attachment và filename.
- **OWASP Input Validation Cheat Sheet:** validation theo kiểu dữ liệu và allowlist.
- **OWASP Logging Cheat Sheet:** không log secrets, giảm log injection và quản lý dữ liệu nhạy cảm.
- **Spring Boot Validation:** Bean Validation trong DTO và kiểm soát dữ liệu tại application boundary.

---

**Ghi nhớ:** phòng chống header injection là bảo đảm **dữ liệu người dùng không thể trở thành cấu trúc của email**. Không tự nối raw header/SMTP commands; từ chối CR/LF/control characters trong header values; parse địa chỉ bằng `InternetAddress`; giới hạn quyền thay đổi `From`, `To`, `Reply-To` và custom headers; dùng `MimeMessageHelper`/Jakarta Mail để dựng message. Đồng thời kiểm thử đường HTTP, database và queue worker, bởi dữ liệu không tin cậy có thể đi vào mail pipeline từ nhiều nguồn khác nhau.
