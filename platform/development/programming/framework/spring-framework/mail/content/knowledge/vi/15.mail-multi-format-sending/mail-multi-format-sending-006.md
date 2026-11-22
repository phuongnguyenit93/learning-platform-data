# Cấu trúc MIME lồng nhau cần được xác minh

Một ứng dụng Spring Boot gửi email xác nhận đơn hàng với ba thành phần: người nhận cần đọc nội dung văn bản, email có bản HTML trình bày đẹp hơn và trong HTML có logo hiển thị ngay trong thư. Ngoài ra, email còn đính kèm hóa đơn PDF để người nhận tải về. Khi dùng `MimeMessageHelper`, lập trình viên có thể gọi `setText(plain, html)`, `addInline(...)` và `addAttachment(...)` rồi gửi message. Tuy nhiên, việc các lệnh này không ném exception chưa chứng minh email đã có đúng cấu trúc MIME mà ứng dụng mong muốn.

**MIME là cấu trúc phân cấp các phần nội dung của email.** Một message có thể chứa multipart bên trong multipart: lớp ngoài gom các nhóm nội dung, lớp related liên kết HTML với hình inline, còn lớp alternative cung cấp nhiều cách biểu diễn cùng một nội dung. Khi cần gửi nhiều định dạng, phải hiểu và xác minh **cây MIME thực tế** thay vì chỉ kiểm tra một chuỗi HTML hoặc giả định attachment nằm ở một vị trí cố định.

Trong chương **Gửi nhiều định dạng** của Spring Framework Mail, bài học này tập trung vào cách tổ chức multipart lồng nhau, cách Spring tạo cấu trúc qua `MimeMessageHelper` và cách kiểm tra message bằng Jakarta Mail sau khi serialize.

## 1. MIME message là một cây, không phải một chuỗi body duy nhất

Một email đơn giản có thể chỉ có một body part:

```text
Content-Type: text/plain; charset=UTF-8

Xin chào, đây là email thông báo.
```

Khi email có nhiều dạng nội dung, MIME dùng các kiểu `multipart/*` để nhóm nhiều part:

| MIME type | Ý nghĩa |
|---|---|
| `multipart/mixed` | Gom các phần độc lập trong cùng message, thường là nội dung thư và các attachment. |
| `multipart/alternative` | Chứa nhiều cách biểu diễn thay thế cho cùng một nội dung, ví dụ plain text và HTML. |
| `multipart/related` | Gom phần nội dung chính với những tài nguyên liên quan, ví dụ HTML và ảnh được tham chiếu bằng CID. |
| `multipart/parallel` | Mô tả các phần được trình bày song song; ít gặp trong email giao dịch thông thường. |
| `multipart/digest` | Gom nhiều message theo cấu trúc digest. |

Một `multipart` có nhiều child part. Child part có thể là nội dung text, ảnh, PDF hoặc chính một `multipart` khác. Vì thế MIME message là một **cây phân cấp**.

Ví dụ email có plain text, HTML, inline logo và PDF:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain; charset=UTF-8
│   │   └── text/html; charset=UTF-8
│   └── image/png
│       ├── Content-ID: <company-logo>
│       └── Content-Disposition: inline
└── application/pdf
    ├── Content-Disposition: attachment
    └── filename: invoice-DH1024.pdf
```

Đây là cấu trúc điển hình khi dùng chế độ `MULTIPART_MODE_MIXED_RELATED` của Spring và thêm alternative body, inline image cùng attachment. Cấu trúc chính xác có thể thay đổi theo multipart mode và cách dựng message; điều quan trọng là **các quan hệ MIME phải đúng**:

- Plain text và HTML là hai cách biểu diễn của cùng nội dung.
- Hình logo thuộc nhóm related và được HTML tham chiếu bằng CID.
- PDF là attachment độc lập với nội dung HTML.
- Message ngoài cùng chứa các nhóm nội dung cần gửi cùng nhau.

## 2. Hiểu đúng vai trò của từng multipart

### 2.1. multipart/alternative: nhiều cách biểu diễn cùng một nội dung

Ví dụ:

```text
Content-Type: multipart/alternative

--alternative-boundary
Content-Type: text/plain; charset=UTF-8

Đơn hàng DH1024 đã được xác nhận.
Xem chi tiết: https://accounts.example.com/orders/DH1024

--alternative-boundary
Content-Type: text/html; charset=UTF-8

<p>Đơn hàng <strong>DH1024</strong> đã được xác nhận.</p>
<p><a href="https://accounts.example.com/orders/DH1024">Xem chi tiết</a></p>

--alternative-boundary--
```

Hai part **không phải hai thông báo khác nhau**. Chúng truyền đạt cùng nội dung ở hai định dạng. Email client thường chọn định dạng phù hợp nhất mà nó có thể hiển thị.

Theo quy tắc MIME cho `multipart/alternative`, các phần được sắp xếp từ dạng ít ưu tiên/ít đầy đủ hơn tới dạng ưu tiên hơn. Vì vậy, thứ tự phổ biến là:

1. `text/plain`.
2. `text/html`.

HTML thường là lựa chọn giàu định dạng hơn nên được đặt sau plain text. Không đảo thứ tự tùy tiện nếu không có lý do tương thích cụ thể.

### 2.2. multipart/related: nội dung chính và tài nguyên liên quan

Một HTML body tham chiếu hình bằng CID:

```html
<p>Chào mừng bạn đến với Example.</p>
<img src="cid:company-logo" alt="Logo Example">
```

MIME related gom HTML và ảnh:

```text
Content-Type: multipart/related

--related-boundary
Content-Type: text/html; charset=UTF-8

<p>Chào mừng bạn đến với Example.</p>
<img src="cid:company-logo" alt="Logo Example">

--related-boundary
Content-Type: image/png
Content-ID: <company-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

[dữ liệu ảnh]
--related-boundary--
```

Phần HTML là nội dung chính; ảnh là tài nguyên được HTML tham chiếu. CID trong HTML phải khớp với `Content-ID` của body part.

Khi email có cả plain text và HTML cùng ảnh inline, phần nội dung chính của related có thể là một `multipart/alternative`. Khi đó cây related chứa alternative, rồi chứa thêm image part.

### 2.3. multipart/mixed: nội dung và attachment độc lập

Attachment PDF không phải tài nguyên cần HTML tham chiếu. Nó là một phần độc lập của message:

```text
Content-Type: multipart/mixed

--mixed-boundary
Content-Type: text/plain; charset=UTF-8

Vui lòng xem hóa đơn đính kèm.

--mixed-boundary
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

[dữ liệu PDF]
--mixed-boundary--
```

Khi kết hợp nhiều loại multipart, mixed thường là lớp ngoài cùng để gom nội dung thư và attachment. Một body part của mixed có thể lại là related multipart hoặc alternative multipart.

## 3. Cấu trúc MIME điển hình khi kết hợp nhiều định dạng

Với email gồm plain text, HTML, inline image và PDF attachment, cây thường được tổ chức như sau:

```text
multipart/mixed
│
├── multipart/related
│   │
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   │
│   └── image/png (inline, Content-ID: company-logo)
│
└── application/pdf (attachment)
```

Mỗi lớp giải quyết một quan hệ:

| Lớp | Câu hỏi được giải quyết |
|---|---|
| Mixed | Những nhóm nội dung độc lập nào được gửi trong cùng message? |
| Related | Tài nguyên nào thuộc về nội dung HTML chính? |
| Alternative | Người nhận có thể đọc nội dung chính ở những định dạng nào? |

Không nên đưa PDF vào `multipart/related` chỉ vì nó được gửi cùng email. PDF không được HTML tham chiếu bằng CID và có mục đích tải về độc lập, nên thuộc nhóm attachment.

## 4. Chọn multipart mode phù hợp trong MimeMessageHelper

Spring `MimeMessageHelper` cung cấp các chế độ multipart phổ biến:

| Hằng số | Cấu trúc chính | Khi dùng |
|---|---|---|
| `MULTIPART_MODE_NO` | Không tạo multipart | Email chỉ có một body đơn giản, không attachment/inline. |
| `MULTIPART_MODE_MIXED` | Root `multipart/mixed` | Nội dung và attachment; không cần cấu trúc related chuyên biệt. |
| `MULTIPART_MODE_RELATED` | Root `multipart/related` | Nội dung HTML và tài nguyên inline liên quan. |
| `MULTIPART_MODE_MIXED_RELATED` | Root mixed, có nested related | Email có nội dung liên quan/inline và attachment độc lập. |

### 4.1. Chỉ có plain text và HTML

Nếu email chỉ cần hai alternative body, dùng helper multipart:

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(plainText, htmlText);
```

Khi không có attachment hoặc inline resource, helper sẽ tổ chức nội dung theo cấu trúc alternative thích hợp. Cần kiểm tra MIME thực tế nếu ứng dụng phụ thuộc vào một cấu trúc cụ thể.

### 4.2. HTML và inline resource

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8");

helper.setText(plainText, htmlText);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

Related mode phù hợp khi HTML tham chiếu inline resource. Nếu cần attachment độc lập trong cùng message, nên cân nhắc mixed-related để attachment ở lớp mixed ngoài.

### 4.3. HTML, inline image và attachment

Đây là trường hợp phổ biến cần xác minh:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setText(plainText, htmlText);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
helper.addAttachment(
        "invoice-DH1024.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");
```

`MULTIPART_MODE_MIXED_RELATED` tạo root mixed và nested related để gom nội dung chính cùng inline resource. Attachment thông thường được thêm vào root mixed.

**Nên gọi `setText(...)` trước `addInline(...)`.** Thứ tự này giúp helper thiết lập phần nội dung chính trước khi thêm tài nguyên liên quan.

### 4.4. Đừng dựa vào constructor boolean nếu cần cấu trúc rõ ràng

Constructor:

```java
new MimeMessageHelper(message, true, "UTF-8")
```

bật multipart bằng chế độ mặc định của helper. Khi email có nhiều loại part và cấu trúc cần được kiểm tra, chỉ định tường minh `MULTIPART_MODE_MIXED_RELATED` làm ý định rõ hơn cho người đọc và người bảo trì.

## 5. Ví dụ hoàn chỉnh tạo MIME message

Giả sử email có:

- Nội dung plain text.
- Nội dung HTML.
- Logo PNG inline.
- Hóa đơn PDF đính kèm.

Ví dụ:

```java
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.file.Path;

@Service
public class InvoiceMailSender {

    private final JavaMailSender mailSender;

    public InvoiceMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            String orderCode,
            Path invoicePath) throws Exception {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn đơn hàng " + orderCode);

        String plain = """
                CÔNG TY EXAMPLE

                Hóa đơn cho đơn hàng %s đã sẵn sàng.
                Vui lòng xem file PDF đính kèm.

                Xem đơn hàng:
                https://accounts.example.com/orders/%s
                """.formatted(orderCode, orderCode);

        String html = """
                <html>
                  <body>
                    <p><strong>CÔNG TY EXAMPLE</strong></p>
                    <img src="cid:company-logo"
                         alt="Logo Công ty Example"
                         width="160">
                    <h1>Hóa đơn đã sẵn sàng</h1>
                    <p>Đơn hàng <strong>%s</strong>.</p>
                    <p>Vui lòng xem file PDF đính kèm.</p>
                    <p>
                      <a href="https://accounts.example.com/orders/%s">
                        Xem đơn hàng
                      </a>
                    </p>
                  </body>
                </html>
                """.formatted(orderCode, orderCode);

        helper.setText(plain, html);

        helper.addInline(
                "company-logo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");

        helper.addAttachment(
                "invoice-" + orderCode + ".pdf",
                new FileSystemResource(invoicePath),
                "application/pdf");

        mailSender.send(message);
    }
}
```

Đây là ví dụ về cấu trúc MIME, không phải toàn bộ quy trình production. Ứng dụng thật vẫn cần xác thực recipient, kiểm tra quyền truy cập hóa đơn, kiểm tra filename/order code, tạo URL từ base URL tin cậy, bảo đảm file tồn tại và đọc được, cũng như xử lý lỗi gửi.

## 6. Thứ tự các part có ý nghĩa

MIME multipart không phải danh sách tùy ý. Thứ tự part có thể ảnh hưởng cách client diễn giải nội dung.

### 6.1. Alternative: plain text trước, HTML sau

`multipart/alternative` thường đặt bản plain text trước, bản HTML sau:

```text
multipart/alternative
├── text/plain
└── text/html
```

Các alternative biểu diễn cùng một nội dung. Phần sau thường là định dạng giàu hơn/ưu tiên hơn. Đừng đặt một attachment PDF vào alternative với ý định “nếu client không hỗ trợ HTML thì tải PDF”: attachment không phải một alternative representation tương đương của body.

### 6.2. Related: nội dung chính và tài nguyên được tham chiếu

Trong `multipart/related`, part đầu thường là phần nội dung gốc, các part tiếp theo là tài nguyên được nội dung đó tham chiếu:

```text
multipart/related
├── multipart/alternative (main body)
└── image/png (CID resource)
```

Nếu ảnh inline không được đặt trong nhóm related hoặc CID không khớp, client có thể không ánh xạ ảnh vào HTML như mong đợi.

### 6.3. Mixed: attachment là part độc lập

`multipart/mixed` gom nội dung chính và các attachment:

```text
multipart/mixed
├── multipart/related (main body + inline resources)
└── application/pdf (attachment)
```

Attachment thường không cần được tham chiếu từ HTML. Client hiển thị nó trong vùng attachment hoặc cung cấp thao tác tải file.

## 7. Vì sao phải xác minh cây MIME thực tế?

Gọi đúng các phương thức helper chưa đủ để xác nhận kết quả. Những lỗi có thể chỉ lộ ra sau khi message được serialize:

- Attachment không nằm ở lớp mixed như mong muốn.
- HTML và plain text không cùng thuộc alternative body.
- Inline image nằm sai nhóm hoặc CID không khớp.
- MIME type hoặc Content-Disposition không đúng.
- Attachment bị thiếu do resource không đọc được.
- Body part lồng nhau không như test giả định.
- Charset hoặc filename encoding sai.

**Xác minh cây MIME** nghĩa là đọc message sau khi helper đã dựng xong, duyệt các part ở mọi cấp và kiểm tra loại nội dung, disposition, filename, Content-ID và byte dữ liệu.

Không nên chỉ kiểm tra:

```java
assertThat(message.getContent()).isInstanceOf(Multipart.class);
```

Điều đó chỉ xác nhận body ngoài cùng là multipart. Nó không chứng minh nested multipart chứa đủ text/plain, text/html, inline image và PDF.

## 8. Duyệt MIME đệ quy bằng Jakarta Mail

Jakarta Mail cung cấp abstraction `Part` cho message/body part và `Multipart` cho nhóm part. Có thể viết một hàm duyệt đệ quy để in cấu trúc.

### 8.1. Hàm in cây MIME

```java
import jakarta.mail.BodyPart;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.io.IOException;

public final class MimeTreePrinter {

    private MimeTreePrinter() {}

    public static void print(Part part) throws MessagingException, IOException {
        print(part, 0);
    }

    private static void print(Part part, int depth)
            throws MessagingException, IOException {

        String indent = "  ".repeat(depth);
        String disposition = part.getDisposition();
        String filename = part.getFileName();
        String[] contentIds = part.getHeader("Content-ID");

        System.out.printf(
                "%s- type=%s; disposition=%s; filename=%s; contentId=%s%n",
                indent,
                part.getContentType(),
                disposition,
                filename,
                contentIds == null ? "" : String.join(",", contentIds));

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    print(child, depth + 1);
                }
            }
        }
    }
}
```

Hàm trên nhận `Part` nên có thể dùng cho `MimeMessage` (message cũng là một Part) và các `BodyPart` con. Nó:

1. In Content-Type, disposition, filename và Content-ID.
2. Kiểm tra part có phải `multipart/*` không.
3. Lấy nội dung thành `Multipart`.
4. Duyệt từng child part bằng đệ quy.

`getContentType()` có thể chứa tham số như `charset` hoặc `boundary`. Khi kiểm tra loại MIME, nên dùng `part.isMimeType("text/html")` hoặc `part.isMimeType("multipart/related")` thay vì so sánh chuỗi Content-Type đầy đủ.

### 8.2. Kết quả cây dự kiến

Với message ví dụ, output khái niệm có thể giống:

```text
- type=multipart/mixed; disposition=null; filename=null
  - type=multipart/related; disposition=null; filename=null
    - type=multipart/alternative; disposition=null; filename=null
      - type=text/plain; charset=UTF-8; disposition=null
      - type=text/html; charset=UTF-8; disposition=null
    - type=image/png; disposition=inline; filename=null; contentId=<company-logo>
  - type=application/pdf; disposition=attachment;
    filename=invoice-DH1024.pdf
```

Đây là output minh họa. Một số provider/client có thể tạo header hoặc cấu trúc khác, và Content-ID có thể được biểu diễn trong ngoặc nhọn. Điều cần kiểm tra là **các part cần thiết tồn tại và có quan hệ đúng**, không phải mọi chuỗi header phải giống ví dụ từng ký tự.

### 8.3. Duyệt cả message/rfc822 khi cần

Trong một số email digest hoặc email chuyển tiếp, body part có thể là `message/rfc822` chứa một email khác. Nếu ứng dụng cần kiểm tra cả message lồng trong message, có thể mở rộng hàm duyệt để nhận diện kiểu đó và xử lý nội dung trả về khi nó là một `Part`.

Đối với email giao dịch thông thường có mixed/related/alternative, duyệt `multipart/*` thường là đủ. Không cần triển khai xử lý message lồng nhau nếu nghiệp vụ không dùng.

## 9. Xác minh theo đặc tính thay vì vị trí cố định

Một lỗi trong test là giả định:

```java
Multipart root = (Multipart) message.getContent();
BodyPart html = root.getBodyPart(0);
BodyPart pdf = root.getBodyPart(1);
```

Giả định trên chỉ có thể đúng với một cấu trúc cụ thể. Khi helper tạo nested multipart, part đầu tiên có thể là một multipart khác, không phải HTML trực tiếp. Nếu đổi multipart mode, thứ tự và độ sâu có thể thay đổi.

Thay vào đó, kiểm tra **theo cây**:

- Có ít nhất một part `text/plain`.
- Có ít nhất một part `text/html`.
- Có image part với Content-ID dự kiến.
- Có attachment có filename dự kiến.
- Attachment có MIME type phù hợp.
- Nội dung byte của attachment khớp file nguồn.

### 9.1. Hàm tìm MIME type đệ quy

```java
import jakarta.mail.BodyPart;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.io.IOException;

public final class MimePartSearch {

    private MimePartSearch() {}

    public static boolean containsMimeType(
            Part part,
            String expectedMimeType)
            throws MessagingException, IOException {

        if (part.isMimeType(expectedMimeType)) {
            return true;
        }

        if (!part.isMimeType("multipart/*")) {
            return false;
        }

        Object content = part.getContent();
        if (!(content instanceof Multipart multipart)) {
            return false;
        }

        for (int i = 0; i < multipart.getCount(); i++) {
            BodyPart child = multipart.getBodyPart(i);
            if (containsMimeType(child, expectedMimeType)) {
                return true;
            }
        }
        return false;
    }
}
```

Sử dụng:

```java
assertThat(MimePartSearch.containsMimeType(message, "text/plain")).isTrue();
assertThat(MimePartSearch.containsMimeType(message, "text/html")).isTrue();
assertThat(MimePartSearch.containsMimeType(message, "image/png")).isTrue();
assertThat(MimePartSearch.containsMimeType(message, "application/pdf")).isTrue();
```

Đây là kiểm tra sự hiện diện của các loại MIME. Nó chưa chứng minh ảnh có CID đúng hoặc PDF là attachment. Cần kiểm tra thêm header và nội dung.

### 9.2. Tìm attachment theo filename

```java
public static boolean containsFilename(Part part, String expectedFilename)
        throws MessagingException, IOException {

    String filename = part.getFileName();
    if (expectedFilename.equals(filename)) {
        return true;
    }

    if (!part.isMimeType("multipart/*")) {
        return false;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            if (containsFilename(
                    multipart.getBodyPart(i), expectedFilename)) {
                return true;
            }
        }
    }
    return false;
}
```

`getFileName()` là metadata tên file của part. Tùy phiên bản Jakarta Mail và cấu hình MIME, việc decode filename header có thể chịu ảnh hưởng bởi các thuộc tính tương thích. Khi test tên Unicode, hãy kiểm tra kết quả sau serialize/parse trên phiên bản thư viện thực tế.

### 9.3. Tìm Content-ID

```java
public static boolean containsContentId(Part part, String expectedId)
        throws MessagingException, IOException {

    String[] values = part.getHeader("Content-ID");
    if (values != null) {
        for (String value : values) {
            String normalized = value.trim();
            if (normalized.startsWith("<") && normalized.endsWith(">")) {
                normalized = normalized.substring(1, normalized.length() - 1);
            }
            if (expectedId.equals(normalized)) {
                return true;
            }
        }
    }

    if (!part.isMimeType("multipart/*")) {
        return false;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            if (containsContentId(
                    multipart.getBodyPart(i), expectedId)) {
                return true;
            }
        }
    }
    return false;
}
```

Hàm trên minh họa việc chuẩn hóa dấu ngoặc nhọn trong header. Trong ứng dụng thực tế, cần xử lý header theo đúng quy tắc MIME và tránh giả định mọi provider đều dùng một cách biểu diễn giống hệt nhau.

## 10. Kiểm tra attachment có đúng disposition và byte

Chỉ tìm filename chưa đủ. Một part có thể có tên file nhưng disposition là inline, hoặc ngược lại. Khi xác minh PDF attachment:

- `Content-Type` phải phù hợp, ví dụ `application/pdf`.
- `Content-Disposition` nên là `attachment`.
- `filename` phải là tên dự kiến.
- Byte sau khi giải mã transfer encoding phải khớp file nguồn.

Ví dụ hàm tìm part theo filename:

```java
public static Part findPartByFilename(Part part, String expectedFilename)
        throws MessagingException, IOException {

    if (expectedFilename.equals(part.getFileName())) {
        return part;
    }

    if (!part.isMimeType("multipart/*")) {
        return null;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            Part found = findPartByFilename(
                    multipart.getBodyPart(i), expectedFilename);
            if (found != null) {
                return found;
            }
        }
    }
    return null;
}
```

Sau đó:

```java
Part pdfPart = findPartByFilename(message, "invoice-DH1024.pdf");

if (pdfPart == null) {
    throw new AssertionError("PDF attachment is missing");
}

if (!pdfPart.isMimeType("application/pdf")) {
    throw new AssertionError("Unexpected attachment MIME type");
}

if (!Part.ATTACHMENT.equalsIgnoreCase(pdfPart.getDisposition())) {
    throw new AssertionError("PDF is not marked as an attachment");
}
```

Một số email client hoặc provider có thể xử lý disposition linh hoạt, nhưng khi **ứng dụng chủ động tạo attachment**, việc mong đợi `Part.ATTACHMENT` là hợp lý. Nếu test một email nhận từ nguồn ngoài, nên xét cả filename và Content-Disposition vì có client không gắn metadata hoàn toàn giống nhau.

### 10.1. Đọc byte đã giải mã

`Part.getInputStream()` cung cấp nội dung part sau khi Jakarta Mail xử lý Content-Transfer-Encoding:

```java
byte[] receivedBytes;
try (InputStream input = pdfPart.getInputStream()) {
    receivedBytes = input.readAllBytes();
}

byte[] sourceBytes = Files.readAllBytes(invoicePath);
assertThat(receivedBytes).containsExactly(sourceBytes);
```

Đoạn test này đọc toàn bộ byte vào bộ nhớ, nên phù hợp với fixture nhỏ. Với file lớn, dùng stream so sánh theo buffer hoặc tính hash theo luồng để tránh giữ hai bản sao lớn trong heap.

Không cần tự base64-decode lần nữa sau `getInputStream()`. Jakarta Mail đã xử lý transfer encoding của MIME part.

## 11. Serialize và parse lại để xác minh message

Một cách kiểm tra hữu ích là:

1. Dựng message bằng `MimeMessageHelper`.
2. Gọi `saveChanges()` để hoàn tất các header cần thiết.
3. Serialize message ra byte stream bằng `writeTo(...)`.
4. Parse byte stream thành `MimeMessage` mới.
5. Duyệt cây MIME của message mới.

Việc parse lại giúp kiểm tra cấu trúc đã thực sự được serialize, không chỉ trạng thái object trước khi gửi.

### 11.1. Ví dụ round-trip

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;

Session session = Session.getInstance(new Properties());
MimeMessage original = new MimeMessage(session);

// Dựng message và thêm các part bằng MimeMessageHelper ở đây.

original.saveChanges();

ByteArrayOutputStream output = new ByteArrayOutputStream();
original.writeTo(output);

byte[] rawMessage = output.toByteArray();

MimeMessage parsed = new MimeMessage(
        session,
        new ByteArrayInputStream(rawMessage));

assertThat(MimePartSearch.containsMimeType(parsed, "text/plain")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "text/html")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "image/png")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "application/pdf")).isTrue();
```

Ví dụ dùng cùng `Session` để parse message vừa serialize. Trong test thực tế, có thể tạo một Session không cấu hình SMTP vì mục đích chỉ là xây và đọc MIME message.

### 11.2. Vì sao không kiểm tra boundary bằng chuỗi cố định?

Mỗi multipart có boundary được sinh để phân tách part. Boundary có thể khác nhau giữa các lần tạo message. Không nên viết:

```java
assertThat(rawText).contains("--boundary-123");
```

trừ khi test chủ động cấu hình boundary trong một fixture đặc biệt. Hãy dùng Jakarta Mail parser để duyệt MIME tree thay vì phụ thuộc vào chuỗi boundary.

### 11.3. Serialize-roundtrip không mô phỏng email client

Round-trip chứng minh message có thể được serialize và parse thành cấu trúc MIME có thể đọc được. Nó **không chứng minh** Gmail, Outlook, Apple Mail hoặc webmail của doanh nghiệp sẽ render giống nhau. Việc hiển thị còn phụ thuộc client, CSS support, chính sách ảnh, proxy và bộ lọc.

Do đó, nên có hai loại kiểm tra:

- **MIME structural test:** kiểm tra cây part, header và byte.
- **Client rendering test:** kiểm tra trải nghiệm trên những email client mục tiêu.

## 12. Viết một bài kiểm thử MIME có ý nghĩa

Một test có thể tạo message với fixture nhỏ và kiểm tra các đặc tính cần thiết.

### 12.1. Chuẩn bị fixture

```java
Path invoice = Files.createTempFile("invoice-", ".pdf");
byte[] pdfBytes = "%PDF-1.7 test document".getBytes(StandardCharsets.US_ASCII);
Files.write(invoice, pdfBytes);
```

Tạo một ảnh PNG fixture nhỏ hoặc dùng `ClassPathResource` có sẵn trong test resources.

### 12.2. Dựng message

```java
Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn DH1024");
helper.setText(
        "Hóa đơn DH1024 đã sẵn sàng. Xem file đính kèm.",
        "<p>Hóa đơn <strong>DH1024</strong> đã sẵn sàng.</p>"
                + "<img src=\"cid:company-logo\" alt=\"Logo\">");
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
helper.addAttachment(
        "invoice-DH1024.pdf",
        new FileSystemResource(invoice),
        "application/pdf");
```

### 12.3. Serialize và xác minh

```java
message.saveChanges();

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
message.writeTo(buffer);

MimeMessage parsed = new MimeMessage(
        session,
        new ByteArrayInputStream(buffer.toByteArray()));

assertThat(MimePartSearch.containsMimeType(parsed, "text/plain")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "text/html")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "image/png")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "application/pdf")).isTrue();

assertThat(containsContentId(parsed, "company-logo")).isTrue();
assertThat(containsFilename(parsed, "invoice-DH1024.pdf")).isTrue();
```

`containsContentId` và `containsFilename` là các hàm duyệt đệ quy được trình bày ở phần trước. Test cũng nên xác nhận `invoice-DH1024.pdf` có disposition attachment và byte của nó bằng `pdfBytes`.

### 12.4. Kiểm tra quan hệ, không chỉ sự tồn tại

Nếu chỉ xác nhận message có text/plain, text/html, image/png và application/pdf ở đâu đó trong cây, test vẫn có thể bỏ sót trường hợp ảnh nằm ngoài nhóm related hoặc HTML không tham chiếu đúng CID.

Với test cấu trúc chặt hơn:

1. Xác định root là `multipart/mixed` khi dùng `MIXED_RELATED`.
2. Tìm child `multipart/related`.
3. Trong related, xác nhận có main body `multipart/alternative`.
4. Trong alternative, xác nhận có `text/plain` và `text/html`.
5. Trong related, xác nhận có image part với CID khớp HTML.
6. Ở root mixed, xác nhận có PDF attachment độc lập.

Không nên áp dụng các kỳ vọng này cho mọi multipart mode. Test phải khớp với cấu trúc mà ứng dụng đã chủ động chọn.

## 13. Hàm kiểm tra cấu trúc mong đợi cho MIXED_RELATED

Đoạn dưới minh họa cách tìm các cấp multipart theo loại MIME thay vì cố định index. Đây là test helper cho cấu trúc Spring đã chọn `MULTIPART_MODE_MIXED_RELATED`; nếu phiên bản provider hoặc cách dựng message thay đổi, cần điều chỉnh theo MIME tree thực tế.

```java
import jakarta.mail.BodyPart;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MultipartNavigator {

    private MultipartNavigator() {}

    public static List<Part> childrenOf(Part part)
            throws MessagingException, IOException {

        List<Part> children = new ArrayList<>();
        if (!part.isMimeType("multipart/*")) {
            return children;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                children.add(multipart.getBodyPart(i));
            }
        }
        return children;
    }

    public static Part firstChildOfType(Part parent, String mimeType)
            throws MessagingException, IOException {

        for (Part child : childrenOf(parent)) {
            if (child.isMimeType(mimeType)) {
                return child;
            }
        }
        return null;
    }
}
```

Ví dụ kiểm tra cấp:

```java
assertThat(parsed.isMimeType("multipart/mixed")).isTrue();

Part related = MultipartNavigator.firstChildOfType(
        parsed, "multipart/related");
assertThat(related).isNotNull();

Part alternative = MultipartNavigator.firstChildOfType(
        related, "multipart/alternative");
assertThat(alternative).isNotNull();

assertThat(MimePartSearch.containsMimeType(
        alternative, "text/plain")).isTrue();
assertThat(MimePartSearch.containsMimeType(
        alternative, "text/html")).isTrue();
```

Ví dụ trên giả định cấu trúc related là child trực tiếp của root mixed. Trong một cấu trúc khác, có thể cần tìm đệ quy thay vì chỉ tìm child trực tiếp. Đó là lý do **in cây MIME trước khi viết assertion sâu** giúp test phản ánh đúng output thực tế.

## 14. Kiểm tra header và charset

MIME tree không chỉ gồm loại part; mỗi part còn có header riêng.

### 14.1. Content-Type

Ví dụ:

```text
Content-Type: text/html; charset=UTF-8
```

Không so sánh toàn bộ chuỗi vì thứ tự tham số hoặc cách viết có thể khác. Dùng:

```java
part.isMimeType("text/html")
```

và đọc tham số charset khi cần kiểm tra:

```java
String contentType = part.getContentType();
```

Có thể dùng parser MIME type thích hợp để đọc parameter; không nên tự split chuỗi theo dấu chấm phẩy nếu cần xử lý đầy đủ quoting.

### 14.2. Content-Disposition

Attachment thường có:

```text
Content-Disposition: attachment; filename="invoice-DH1024.pdf"
```

Inline resource thường có:

```text
Content-Disposition: inline
```

Disposition là metadata gợi ý cách trình bày. Client vẫn có thể quyết định hiển thị khác; test message gửi ra nên xác nhận metadata mà ứng dụng tạo.

### 14.3. Content-ID

Inline part có header:

```text
Content-ID: <company-logo>
```

HTML tham chiếu:

```html
<img src="cid:company-logo" alt="Logo">
```

Phải kiểm tra sự khớp giữa hai bên. Không chỉ kiểm tra image/png có tồn tại; một hình PNG không có CID phù hợp không thể đáp ứng tham chiếu HTML đó.

### 14.4. Charset và nội dung tiếng Việt

Text body nên dùng charset rõ ràng, thường là UTF-8:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name());
```

Kiểm tra sau serialize/parse rằng nội dung tiếng Việt được giải mã đúng. Đừng chỉ nhìn byte raw rồi kết luận lỗi; MIME transfer encoding và charset có vai trò khác nhau. Với `text/plain` và `text/html`, cần kiểm tra cả header charset lẫn nội dung sau khi Jakarta Mail đọc part.

## 15. Kiểm tra MIME bằng SMTP catcher

Unit test serialize/parse kiểm tra cấu trúc message trong JVM. Integration test với SMTP catcher kiểm tra message thực sự được Spring gửi tới SMTP test server.

Các công cụ thường dùng:

- **GreenMail:** SMTP/IMAP/POP3 server giả lập cho integration test Java.
- **Mailpit:** SMTP server test có giao diện xem email.
- **MailHog:** SMTP sink cho môi trường phát triển/test.

Luồng kiểm thử:

1. Khởi động SMTP catcher.
2. Cấu hình Spring Boot trỏ tới host/port test.
3. Gọi service gửi email.
4. Lấy message từ catcher.
5. Parse message và duyệt MIME tree.
6. Xác nhận text/plain, text/html, inline CID và attachment.

Ví dụ cấu hình test:

```yaml
spring:
  mail:
    host: localhost
    port: 1025
    username: ''
    password: ''
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
```

Đây chỉ là cấu hình minh họa cho SMTP catcher chạy local trên cổng 1025; cấu hình thực tế phụ thuộc công cụ và test environment.

**SMTP catcher không mô phỏng đầy đủ Gmail, Outlook hay Apple Mail.** Nó xác nhận việc gửi tới test server và cho phép kiểm tra raw MIME; để kiểm tra giao diện cuối, vẫn cần kiểm thử client mục tiêu.

## 16. Vì sao không nên kiểm tra bằng cách tìm chuỗi trong raw MIME?

Một test có thể thử:

```java
String raw = new String(rawMessage, StandardCharsets.ISO_8859_1);
assertThat(raw).contains("multipart/related");
assertThat(raw).contains("application/pdf");
```

Cách này có ích cho debug nhanh nhưng yếu khi dùng làm xác minh cấu trúc:

- Header có thể được viết với chữ hoa/thường khác nhau.
- Tham số Content-Type có thể thay đổi thứ tự.
- MIME boundary được sinh động.
- Header có thể bị folding thành nhiều dòng.
- Filename Unicode có thể được encode.
- Nội dung base64 có thể bị xuống dòng.
- Một chuỗi MIME type có thể xuất hiện trong body text chứ không phải header của part.

Hãy dùng Jakarta Mail parser để kiểm tra **cấu trúc và metadata đã parse**, còn raw MIME chỉ dùng khi cần điều tra chi tiết header/serialization.

## 17. Bảo mật và tính toàn vẹn của MIME parts

Xác minh MIME không chỉ nhằm bảo đảm client hiển thị đúng; nó còn giúp ứng dụng phát hiện dữ liệu bị gắn nhầm hoặc thiếu.

### 17.1. Không tin Content-Type do người dùng gửi

Nếu file upload được gửi thành attachment, không lấy `MultipartFile.getContentType()` làm bằng chứng nội dung. MIME type phải được xác định theo định dạng thực tế đã kiểm tra và chính sách ứng dụng.

### 17.2. Kiểm soát filename

Tên file attachment không nên chứa đường dẫn, CR/LF, ký tự điều khiển hoặc thông tin nhạy cảm. Không dùng tên file do client cung cấp trực tiếp trong header.

### 17.3. Không log toàn bộ raw MIME trong production

Raw message có thể chứa:

- Địa chỉ email cá nhân.
- Nội dung giao dịch.
- Token xác minh hoặc reset password.
- Attachment chứa thông tin tài chính/y tế/hồ sơ.

Chỉ log metadata cần thiết như notification ID, template version, số part, MIME type, kích thước và mã lỗi. Khi cần thu thập raw MIME để debug, phải có quyền truy cập hạn chế và thời gian lưu phù hợp.

### 17.4. MIME structure đúng không làm nội dung HTML an toàn

Một message có nested multipart hoàn toàn hợp lệ vẫn có thể chứa HTML injection, URL phishing hoặc nội dung không phù hợp. Cần escape dữ liệu động, kiểm tra URL và kiểm soát template độc lập với việc xác minh MIME tree.

## 18. Các lỗi thường gặp khi tạo và xác minh nested MIME

### 18.1. Nghĩ multipart chỉ có một cấp

Email có thể chứa mixed → related → alternative. Nếu chỉ đọc root multipart, test sẽ bỏ qua part lồng bên trong. Duyệt đệ quy.

### 18.2. Đặt PDF vào alternative

PDF attachment không phải alternative representation của body. Đặt nó trong mixed như một part độc lập.

### 18.3. Đặt inline image ngoài related

HTML có thể không ánh xạ được CID nếu cấu trúc liên quan không được tổ chức đúng. Dùng related mode hoặc mixed-related khi có cả attachment.

### 18.4. CID không khớp

HTML tham chiếu `cid:logo` nhưng helper thêm `brand-logo`. Kiểm tra cả HTML và Content-ID header.

### 18.5. Dựa vào index cố định

Part index có thể thay đổi khi thêm inline resource, attachment hoặc đổi multipart mode. Tìm theo MIME type, filename và Content-ID.

### 18.6. Quên setText trước addInline

Gọi `setText` trước `addInline` theo khuyến nghị của Spring để tạo phần nội dung chính trước khi thêm resource liên quan.

### 18.7. Không bật multipart

Attachment và inline resource cần cấu trúc multipart. Chọn constructor/helper mode phù hợp ngay từ đầu.

### 18.8. So sánh Content-Type bằng chuỗi tuyệt đối

`text/html; charset=UTF-8` và `text/html; charset="UTF-8"` vẫn là cùng MIME type. Dùng `isMimeType("text/html")`.

### 18.9. Kiểm tra raw boundary cố định

Boundary thay đổi theo message. Parse MIME thay vì tìm chuỗi boundary hardcode.

### 18.10. Cho rằng serialize-roundtrip chứng minh client render đúng

Nó chỉ kiểm tra MIME có thể serialize/parse. Cần test client riêng để xác nhận cách hiển thị.

### 18.11. Chỉ kiểm tra MIME type, không kiểm tra quan hệ

Có đủ image/png và text/html chưa chứng minh HTML tham chiếu đúng CID. Kiểm tra Content-ID và quan hệ related.

### 18.12. Chỉ kiểm tra filename, không kiểm tra byte

Filename có thể đúng nhưng file rỗng/hỏng. So sánh byte hoặc hash với nguồn khi test.

### 18.13. Coi attachment inline và attachment thường giống nhau

Content-Disposition và quan hệ CID khác nhau. Inline resource phục vụ HTML; attachment thông thường phục vụ tải file.

## 19. Bài tập thực hành

### Bài 1 — Vẽ MIME tree

Một email có `text/plain`, `text/html`, hai ảnh inline và một PDF attachment. Hãy vẽ cây MIME phù hợp khi dùng `MULTIPART_MODE_MIXED_RELATED`. Chỉ rõ part nào thuộc alternative, related và mixed.

### Bài 2 — Chọn multipart mode

Chọn mode cho các trường hợp:

1. Chỉ có text/plain.
2. HTML và một logo CID.
3. Plain text + HTML + logo CID.
4. Plain text + HTML + logo CID + PDF attachment.

Giải thích vì sao trường hợp thứ tư phù hợp với `MULTIPART_MODE_MIXED_RELATED`.

### Bài 3 — Viết helper

Viết Java dùng `MimeMessageHelper` để tạo email gồm plain text, HTML, logo inline và file PDF. Đảm bảo HTML tham chiếu CID khớp với ID truyền vào `addInline`.

### Bài 4 — Duyệt đệ quy

Viết hàm nhận `Part`, in Content-Type, disposition, filename và Content-ID. Khi part là multipart, duyệt toàn bộ child part. Giải thích vì sao chỉ duyệt root không đủ.

### Bài 5 — Xác minh quan hệ

Một message có `text/html` và `image/png` nhưng logo không hiển thị. Hãy thiết kế kiểm tra xác nhận:

- HTML có `src="cid:company-logo"`.
- Image part có Content-ID `company-logo`.
- Image part thuộc nhóm related.
- Byte ảnh đọc được.

### Bài 6 — Attachment bị thiếu

Test chỉ xác nhận root message là multipart và có `application/pdf`. Tuy nhiên PDF không có filename và disposition là inline. Hãy giải thích vì sao test hiện tại chưa đủ và bổ sung assertion.

### Bài 7 — Serialize-roundtrip

Dựng message, gọi `saveChanges`, `writeTo`, parse thành `MimeMessage` mới và kiểm tra các MIME type. Vì sao không nên so sánh boundary bằng chuỗi cố định?

### Bài 8 — Thứ tự alternative

Giải thích vì sao `text/plain` thường được đặt trước `text/html` trong `multipart/alternative` và tại sao PDF không thuộc alternative.

### Bài 9 — SMTP catcher

Thiết kế integration test gửi message tới Mailpit hoặc GreenMail, sau đó lấy message và kiểm tra MIME tree. Những gì test này chứng minh và những gì nó không chứng minh?

### Bài 10 — Bảo mật

Một attachment được gắn `Content-Type: application/pdf` nhưng byte không phải PDF. Vì sao MIME structure đúng vẫn không bảo đảm file an toàn? Đề xuất kiểm tra ở tầng upload/storage.

## 20. Ghi nhớ và tài liệu tham khảo

Khi **cấu trúc MIME lồng nhau cần được xác minh** trong Spring Framework Mail:

1. Xem message như một cây MIME; multipart có thể chứa multipart khác.
2. Dùng `multipart/alternative` cho text/plain và text/html của cùng nội dung.
3. Dùng `multipart/related` để nhóm HTML với ảnh inline được tham chiếu bằng CID.
4. Dùng `multipart/mixed` để gom nhóm nội dung và attachment độc lập.
5. Với plain + HTML + inline image + attachment, cân nhắc `MULTIPART_MODE_MIXED_RELATED`.
6. Gọi `setText` trước `addInline` và bảo đảm CID trong HTML khớp Content-ID của part.
7. Duyệt MIME đệ quy bằng `Part` và `Multipart`; không dựa vào part index cố định.
8. Kiểm tra MIME type bằng `isMimeType`, đồng thời xác minh disposition, filename, Content-ID và byte dữ liệu.
9. Serialize rồi parse lại message để kiểm tra cấu trúc được tạo thực tế.
10. Phân biệt structural test với kiểm thử hiển thị trên email client.

Tài liệu kỹ thuật nên tham khảo:

- **Spring Framework API — `MimeMessageHelper`:** multipart modes, `setText`, `addInline` và `addAttachment`.
- **Spring Framework Reference — Email:** cách tạo MIME email bằng `JavaMailSender` và `MimeMessageHelper`.
- **Jakarta Mail API — `Part`, `BodyPart`, `Multipart`, `MimeMessage`:** duyệt và thao tác MIME tree.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** cấu trúc MIME, body part và transfer encoding.
- **RFC 2046 — MIME Media Types:** `multipart/mixed`, `multipart/alternative`, `multipart/related` và quy tắc sắp xếp alternative.
- **RFC 2387 — The MIME Multipart/Related Content-type:** nhóm nội dung chính và tài nguyên liên quan.
- **RFC 2392 — Content-ID and Message-ID Uniform Resource Locators:** tham chiếu tài nguyên bằng `cid:`.

**Gửi nhiều định dạng không chỉ là gọi nhiều setter.** Ứng dụng phải tạo đúng quan hệ giữa alternative body, inline resources và attachment; sau đó xác minh cây MIME thực tế bằng parser. Khi kiểm tra theo cấu trúc và metadata thay vì dựa vào vị trí part, test sẽ bền vững hơn trước thay đổi template, multipart mode và provider.
