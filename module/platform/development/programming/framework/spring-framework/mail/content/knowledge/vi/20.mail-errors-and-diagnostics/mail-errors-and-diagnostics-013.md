# Tạo bản sao message hoặc MIME dump an toàn để điều tra

Khi một email gửi bằng Spring Framework Mail gặp lỗi, người phát triển thường muốn giữ lại message đã được tạo hoặc xuất một tệp MIME để kiểm tra. Điều này giúp phát hiện lỗi `Content-Type`, charset, boundary, attachment, ảnh inline và quá trình serialize của Jakarta Mail. Tuy nhiên, **MIME dump có thể chứa toàn bộ nội dung email**, từ địa chỉ To/Cc/Bcc tới token, HTML và file đính kèm. Việc ghi thẳng dump vào log có thể tạo ra một sự cố rò rỉ dữ liệu ngay trong quá trình chẩn đoán.

Bài học hướng dẫn cách **tạo bản sao `MimeMessage`**, hiểu đúng `MimeMessage.writeTo(...)`, ưu tiên **báo cáo cấu trúc MIME an toàn** và chỉ thu thập raw dump khi thật sự cần, trong môi trường được kiểm soát. Trọng tâm là cách giữ bằng chứng đủ hữu ích mà không lưu trữ hoặc lan truyền thông tin cá nhân, bí mật và nội dung email quá mức.

## 1. Vì sao phải chẩn đoán MIME?

Một thông báo email đi qua nhiều tầng:

```text
Business data
     |
     v
Template engine: HTML / plain text
     |
     v
MimeMessageHelper
     |
     v
MimeMessage: headers + MIME parts
     |
     v
JavaMailSender / Jakarta Mail
     |
     v
SMTP submission
     |
     v
Mail server / mailbox / mail client
```

Lỗi có thể xuất hiện tại:

- **Dữ liệu/template:** tên người dùng sai dấu, HTML chưa escape, URL sai.
- **MIME composition:** thiếu `text/html`, sai nesting `multipart`, CID không khớp, attachment nhầm disposition.
- **Serialization:** encoded headers, boundary hoặc content-transfer-encoding không như dự kiến.
- **SMTP:** connection fail, từ chối recipient, message quá lớn hoặc timeout.
- **Delivery/client:** thư đã được SMTP chấp nhận nhưng chưa giao hoặc hiển thị khác nhau giữa mail client.

Không phải lỗi nào cũng cần dump. Ví dụ `MailAuthenticationException` thường cần kiểm tra cấu hình SMTP AUTH; raw MIME của body không giúp sửa sai credential.

## 2. Phân biệt bản sao message, raw dump và safe summary

| Loại artifact | Chứa gì? | Rủi ro | Khi dùng |
| --- | --- | --- | --- |
| **Bản sao logic `MimeMessage`** | Message object có các headers và body parts tương ứng | Vẫn có PII/attachment | Muốn kiểm tra object riêng mà không sửa object gốc |
| **Raw MIME dump** | Bytes biểu diễn headers, MIME boundaries, body, encoding và attachment | Rất cao | Điều tra byte-level trong môi trường hạn chế |
| **Safe MIME summary** | MIME base type, số part, disposition, reported size, cờ có CID/filename | Thấp hơn nếu áp dụng allowlist | Logging và chẩn đoán production mặc định |

Một bản copy `MimeMessage` **không tự động được ẩn danh**. Raw MIME cũng không an toàn chỉ vì trông giống một tệp text hoặc chứa các đoạn base64. Ngược lại, safe summary không thể chứng minh mọi byte được truyền, nhưng thường đủ để tìm lỗi cấu trúc thông thường.

### Thứ tự ưu tiên

1. Bắt đầu bằng notification ID, template version, exception class và trạng thái SMTP.
2. Lấy metadata cấu trúc thay vì đọc nội dung thư.
3. Tái hiện bằng dữ liệu giả và SMTP test server.
4. Chỉ khi vẫn thiếu bằng chứng mới cân nhắc raw MIME thật có phê duyệt, mã hóa, access control và TTL.

## 3. MIME message thực sự chứa những gì?

Ví dụ một thông báo có bản text, HTML, logo inline và PDF:

```text
MimeMessage
├── Headers
│   ├── From / To / Cc / Bcc
│   ├── Subject / Date / Message-ID
│   └── Content-Type / MIME-Version
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   └── image/png; Content-ID:<logo@example.org>
    └── application/pdf; disposition=attachment
```

Đây là sơ đồ minh họa. Cách nesting thực tế phụ thuộc `MimeMessageHelper` và cấu hình multipart mode.

Trong raw MIME có thể có:

- Địa chỉ người nhận, bao gồm Bcc và các mailbox nội bộ.
- Subject có tên khách hàng hoặc mã hồ sơ.
- HTML/text body chứa thông tin cá nhân.
- URL reset password, magic login hoặc unsubscribe có token.
- Attachment chứa PDF/CSV/ảnh/file Office.
- File metadata, tracking query, internal host hoặc định danh giao dịch.
- Header tùy chỉnh do ứng dụng tự thêm.

`Content-Transfer-Encoding: base64` chỉ phục vụ cách truyền byte qua email, **không phải encryption**. Ai đọc dump có thể giải mã và phục hồi file.

## 4. Chọn dữ liệu điều tra theo hiện tượng

| Hiện tượng | Câu hỏi | Dữ liệu tối thiểu |
| --- | --- | --- |
| Sai dấu tiếng Việt | Charset của part và nguồn dữ liệu có đúng không? | Base MIME type, charset chuẩn hóa, template version |
| Không có bản HTML | Có `text/html` part không? | Cây MIME |
| Ảnh CID không hiện | Có inline part và mapping `cid:` không? | Part count, CID presence/mapping ẩn danh |
| Thiếu attachment | Có part attachment và media type không? | Disposition, type, reported size |
| SMTP từ chối vì size | Message lớn bao nhiêu? | Size tổng, SMTP reply code |
| Recipient bị từ chối | SMTP từ chối ở giai đoạn nào? | Transport/provider log |
| Header folding sai | Header bytes đã serialize thế nào? | Raw MIME của fixture test |
| Boundary sai | Multipart serialization có đúng không? | Raw MIME test capture |
| Email vào spam | Delivery/reputation thế nào? | Provider event, không phải raw body mặc định |

Không lấy toàn bộ thư khi chỉ cần biết một file PDF đã được thêm vào message hay chưa.

## 5. Tạo bản sao MimeMessage bằng copy constructor

Jakarta Mail có constructor nhận một `MimeMessage` đã có:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

public MimeMessage createInspectionCopy(MimeMessage source)
        throws MessagingException {
    return new MimeMessage(source);
}
```

Bản sao có thể phục vụ thao tác kiểm tra trên object riêng, nhưng cần hiểu:

- **Không làm sạch dữ liệu:** bản sao vẫn có headers, recipient, body và attachment.
- **Không chứng minh byte identity:** trạng thái object có thể khác serialization cuối cùng.
- **Không chứng minh server đã nhận:** bản sao có thể được tạo trước khi transport xử lý.
- **Không thay đổi tính mutable:** tránh inspect/copy trong khi một thread khác đang sửa hoặc gửi message gốc.
- **Không miễn phí:** tạo copy có thể cần parse/serialize nội dung và truy cập resource, gây tốn CPU/bộ nhớ.

### Thời điểm tạo bản sao

```text
Tạo mail model và render template
             |
             v
Build MimeMessage
             |
             +---- Safe MIME summary: BEFORE_SEND
             |
             +---- Optional controlled copy
             |
             v
JavaMailSender.send(message)
             |
             v
Ghi SMTP result / exception
```

Ghi stage và timestamp cho snapshot. Nếu tạo copy trước khi gọi `addAttachment(...)`, bản copy sẽ không phản ánh attachment được thêm sau đó.

## 6. Copy object không phải bản ghi wire bytes

`MimeMessage` là object có thể được tạo dần. Một số chi tiết như `Date`, `Message-ID`, MIME boundary và encoding có thể được hoàn thiện hoặc thay đổi trong quá trình `saveChanges()` và serialize tùy implementation.

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("notify@example.org");
helper.setTo("test@example.net");
helper.setSubject("Message kiểm thử");
helper.setText("Plain text", "<p>HTML</p>");

MimeMessage snapshot = new MimeMessage(message);
// Snapshot chỉ phản ánh trạng thái ở thời điểm này.
```

Nếu sau đó thêm attachment hoặc sửa subject trên message gốc, snapshot không còn phản ánh message cuối cùng. Nếu `writeTo(...)` trên bản copy kích hoạt bước chuẩn bị message, byte kết quả có thể khác object ngay trước khi gọi.

Khi cần bằng chứng chặt chẽ, ghi lại `snapshotStage`, template version, mã phiên bản ứng dụng, thời điểm và nguồn thu thập. Không gọi một copy object là chứng cứ byte-for-byte từ SMTP server.

## 7. Tạo raw MIME bằng writeTo()

Jakarta Mail có phương thức ghi message ra `OutputStream`:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

public byte[] serializeSyntheticMail(MimeMessage message)
        throws IOException, MessagingException {

    ByteArrayOutputStream output = new ByteArrayOutputStream();
    message.writeTo(output);
    return output.toByteArray();
}
```

**Chỉ dùng ví dụ này với message nhỏ và dữ liệu giả, trong môi trường test.** Hàm trả toàn bộ byte MIME: headers, body và attachment. `ByteArrayOutputStream` và `toByteArray()` có thể tạo thêm các bản sao dữ liệu trên heap.

Không làm:

```java
// Anti-pattern: raw MIME bị ghi vào stdout của ứng dụng.
message.writeTo(System.out);
```

Và không làm:

```java
// Anti-pattern: biến toàn bộ thư thành nội dung log.
logger.debug("MIME={}", new String(
        rawMime, StandardCharsets.UTF_8));
```

Raw MIME có thể gồm nhiều part và encoding khác nhau, không phải một chuỗi UTF-8 thuần nhất. Việc ép toàn bộ byte thành String còn có thể làm thay đổi cách quan sát lỗi byte-level.

## 8. MIME dump không chứa toàn bộ SMTP envelope

Phân biệt:

```text
SMTP envelope:
  MAIL FROM:<bounce@example.org>
  RCPT TO:<recipient@example.net>

MIME message:
  From: Notification <notify@example.org>
  To: recipient@example.net
  Subject: ...
  Content-Type: multipart/alternative; ...
  [body]
```

`writeTo(...)` không ghi toàn bộ lệnh SMTP:

- Không có tất cả `MAIL FROM` và `RCPT TO` như một transcript protocol.
- Không thể hiện SMTP reply code cho từng recipient.
- Không chứa đầy đủ thương lượng `AUTH` và `STARTTLS`.
- Không chứng minh server đã chấp nhận `DATA`.
- Không bao gồm tất cả các header mà downstream relay có thể thêm.

Nếu sự cố là `550 relay denied` hoặc recipient bị từ chối, phải xem transport/provider evidence thay vì chỉ MIME dump.

**Bcc cần bảo vệ đặc biệt:** một object trước gửi hoặc bản copy có thể chứa recipient ẩn dù mailbox người nhận không hiển thị Bcc. Không suy luận ngược từ giao diện mail client rằng dump không có Bcc.

## 9. Thiết kế MIME summary thay thế

Thay vì log body, tạo báo cáo cấu trúc:

```text
notificationId=mail-8a1...
stage=BEFORE_SEND
rootType=multipart/mixed
partCount=6

parts:
  root         multipart/mixed       size=unknown
  root.0       multipart/related     size=unknown
  root.0.0     multipart/alternative size=unknown
  root.0.0.0   text/plain            size=420
  root.0.0.1   text/html             size=1800
  root.0.1     image/png             size=8020 inline
  root.1       application/pdf       size=24200 attachment

hasAnyContentId=true
hasAnyFilename=true
```

Metadata này hỗ trợ xác định:

- Message có bản text và HTML không.
- Part inline có tồn tại không.
- Attachment được thêm đúng type/disposition không.
- Cấu trúc `multipart` có hợp lý không.

Không cần in Subject, To, Cc, Bcc, filename, Content-ID nguyên gốc hoặc attachment bytes.

## 10. Các trường có thể lưu theo allowlist

| Trường | Khuyến nghị | Lưu ý |
| --- | --- | --- |
| Notification ID do ứng dụng tạo | Có | Không chứa PII |
| Template key/version | Có điều kiện | Không đưa dữ liệu người dùng vào key |
| Base MIME type | Có | Bỏ parameter như name/boundary |
| Disposition | Có | Chuẩn hóa inline/attachment/other |
| Reported size | Có | `getSize()` có thể trả -1 |
| Part count / nesting depth | Có | Giới hạn độ sâu và số phần |
| Has filename | Boolean | Không lưu tên file thật |
| Has Content-ID | Boolean/count | Không lưu CID nguyên gốc |
| Charset | Allowlist | UTF-8, US-ASCII, other |
| Transfer encoding | Allowlist | base64, quoted-printable, 7bit, other |
| Subject và addresses | Không mặc định | Có PII |
| Message-ID raw | Hạn chế | Có thể lộ domain/định danh |
| Header tùy chỉnh | Không mặc định | Có thể chứa token/user ID |
| Body/URL/attachment | Không mặc định | Dữ liệu nhạy cảm |

Đừng thu mọi header rồi xóa dần bằng regex. Cách ít rủi ro hơn là **tạo mới báo cáo chỉ chứa các trường được phép**.

## 11. Ví dụ Java: duyệt cây MIME không lấy body text

Utility sau thu thập `path`, MIME base type, disposition, kích thước do API báo và cờ có filename/CID. Nó không đọc nội dung `text/html`, `text/plain` hoặc attachment.

```java
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.ContentType;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.ParseException;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class SafeMimeInspector {

    private static final int MAX_DEPTH = 8;
    private static final int MAX_PARTS = 80;

    public record PartSummary(
            String path,
            String baseType,
            String disposition,
            int reportedSize,
            boolean hasFilename,
            boolean hasContentId
    ) {}

    public List<PartSummary> inspect(MimeMessage message)
            throws MessagingException, IOException {
        List<PartSummary> result = new ArrayList<>();
        visit(message, "root", 0, result);
        return List.copyOf(result);
    }

    private void visit(
            Part part,
            String path,
            int depth,
            List<PartSummary> result
    ) throws MessagingException, IOException {

        if (depth > MAX_DEPTH || result.size() >= MAX_PARTS) {
            return;
        }

        result.add(new PartSummary(
                path,
                safeBaseType(part.getContentType()),
                safeDisposition(part.getDisposition()),
                part.getSize(),
                part.getFileName() != null,
                part.getHeader("Content-ID") != null
        ));

        if (depth >= MAX_DEPTH || !part.isMimeType("multipart/*")) {
            return;
        }

        // Chỉ duyệt các Multipart, không đọc text/attachment.
        Object content = part.getContent();
        if (!(content instanceof Multipart multipart)) {
            return;
        }

        for (int i = 0;
             i < multipart.getCount() && result.size() < MAX_PARTS;
             i++) {
            visit(
                    multipart.getBodyPart(i),
                    path + "." + i,
                    depth + 1,
                    result
            );
        }
    }

    private static String safeBaseType(String raw) {
        try {
            String type = new ContentType(raw)
                    .getBaseType()
                    .toLowerCase(Locale.ROOT);
            return type.matches(
                    "[a-z0-9.+-]{1,64}/[a-z0-9.+-]{1,128}"
            ) ? type : "invalid-or-other";
        } catch (ParseException ex) {
            return "invalid-or-other";
        }
    }

    private static String safeDisposition(String value) {
        if (Part.INLINE.equalsIgnoreCase(value)) {
            return "inline";
        }
        if (Part.ATTACHMENT.equalsIgnoreCase(value)) {
            return "attachment";
        }
        return "unspecified-or-other";
    }
}
```

### Vì sao utility này giới hạn số part?

Một MIME message có thể lồng nhiều `multipart` hoặc có hàng nghìn phần. `MAX_DEPTH` và `MAX_PARTS` hạn chế kích thước output. `safeBaseType` chỉ giữ type/subtype đã chuẩn hóa; `safeDisposition` không log giá trị tùy ý. Hai cờ `hasFilename` và `hasContentId` không lộ giá trị thật.

**Giới hạn kỹ thuật:** `getContent()` để duyệt `multipart/*` vẫn có thể khiến thư viện parse và truy cập resource. Utility này dành cho message do ứng dụng tự tạo, đã có giới hạn kích thước. Với MIME nhận từ nguồn không tin cậy, cần thêm giới hạn tổng byte, thời gian, CPU và tài nguyên ở tầng parser.

`Part.getSize()` có thể trả `-1` nếu không biết kích thước. Hãy biểu diễn “unknown”, không coi `-1` là kích thước thực hoặc dùng nó để tính tổng trực tiếp.

## 12. Bổ sung charset và transfer encoding theo allowlist

Khi chẩn đoán Unicode, có thể phân loại charset mà không log raw header:

```java
private static String safeCharset(String contentType) {
    try {
        String charset = new ContentType(contentType)
                .getParameter("charset");
        if (charset == null) {
            return "unspecified";
        }

        return switch (charset.toLowerCase(Locale.ROOT)) {
            case "utf-8" -> "utf-8";
            case "us-ascii" -> "us-ascii";
            case "iso-8859-1" -> "iso-8859-1";
            case "windows-1252" -> "windows-1252";
            default -> "other";
        };
    } catch (ParseException ex) {
        return "invalid";
    }
}
```

Với `Content-Transfer-Encoding`, có thể chuẩn hóa thành `base64`, `quoted-printable`, `7bit`, `8bit`, `binary` hoặc `other`. Không đưa nguyên chuỗi header từ nguồn tùy ý vào log.

Charset đúng trong MIME không có nghĩa dữ liệu đầu vào không bị hỏng. Nếu Java String đã sai khi lấy từ database hoặc file, `MimeMessageHelper` không sửa được giá trị đó.

## 13. Tích hợp vào Spring Mail service

Một service có thể ghi summary gắn với notification ID ngay trước khi gửi:

```java
@Service
public class MailSubmissionService {

    private final JavaMailSender sender;
    private final SafeMimeInspector inspector;

    public MailSubmissionService(
            JavaMailSender sender,
            SafeMimeInspector inspector
    ) {
        this.sender = sender;
        this.inspector = inspector;
    }

    public void submit(UUID notificationId, MimeMessage message)
            throws MessagingException, IOException {

        var summary = inspector.inspect(message);

        // Lưu chỉ metadata allowlist với stage BEFORE_SEND.
        recordSafeDiagnostic(notificationId, "BEFORE_SEND", summary);

        sender.send(message);
    }
}
```

`recordSafeDiagnostic(...)` là method do ứng dụng triển khai. `SafeMimeInspector` cần được tạo bean hoặc khởi tạo phù hợp. Trong production, chỉ lấy summary theo sampling, feature flag hoặc nhu cầu điều tra; giới hạn retention và record size.

Không để lỗi ghi diagnostic làm hỏng nghiệp vụ gửi mail quan trọng trừ khi chính sách yêu cầu. Không gọi summary này là bằng chứng server đã nhận mail.

## 14. Bản MIME trước gửi khác bằng chứng từ transport

| Nguồn | Có thể chứng minh | Không thể chứng minh |
| --- | --- | --- |
| Message object trước `send` | Cấu trúc tại giai đoạn thu thập | SMTP đã nhận bytes ấy |
| `writeTo(...)` | Serialization tại thời điểm gọi | Toàn bộ SMTP envelope |
| SMTP capture server test | Bytes server test nhận trong môi trường test | Production relay xử lý hoàn toàn giống |
| Provider response/event | Kết quả accepted/delivered theo provider | Mọi mail client hiển thị đúng |
| Mail client test | Hình thức hiển thị trên client đó | Hình thức ở mọi client khác |

Một snapshot trước gửi có thể khác capture sau đó vì `saveChanges`, `Message-ID`, `Date`, boundary hoặc transport. Đừng kết luận có lỗi nếu chưa biết hai bản chụp thuộc giai đoạn nào.

## 15. Vì sao xóa header bằng regex không đủ an toàn?

Một cách làm thiếu an toàn:

```java
// Không phải redaction MIME đầy đủ.
String masked = rawText
        .replaceAll("(?im)^To:.*$", "To: [REDACTED]")
        .replaceAll("(?im)^Subject:.*$", "Subject: [REDACTED]");
```

Nó có thể bỏ sót:

- Header folding qua nhiều dòng.
- `Cc`, `Bcc`, `Reply-To`, `Return-Path`, `Received` và header `X-*`.
- Encoded-word theo RFC 2047 trong subject.
- Encoded parameter/filename.
- Base64 hoặc quoted-printable body.
- URL chứa token trong HTML/text.
- Attachment và metadata file.
- `message/rfc822` lồng một email khác.

**Redaction trên raw string không phải ẩn danh MIME hoàn chỉnh.** Với báo cáo thông thường, hãy tạo object diagnostic mới từ những field đã được allowlist.

## 16. Tại sao attachment cần chú ý đặc biệt?

Attachment có thể là:

- PDF hóa đơn chứa tên, địa chỉ, giao dịch.
- CSV chứa danh sách khách hàng.
- File Office có tác giả, comments và revision history.
- Ảnh chứa EXIF hoặc QR code chứa token.
- ZIP chứa nhiều tài liệu.

Xóa text/plain và text/html nhưng giữ attachment trong dump vẫn có thể làm lộ hầu hết dữ liệu nhạy cảm.

Metadata nên dừng ở:

```text
mimeBaseType=application/pdf
disposition=attachment
hasFilename=true
reportedSize=25700
```

Nếu nghi file bị hỏng, ưu tiên file mẫu giả có cùng type/kích thước. Khi thật sự cần so sánh bytes thực, phải kiểm soát quyền; không đưa raw attachment hoặc digest có thể suy đoán vào metric phổ thông.

## 17. Kiểm tra ảnh inline và Content-ID

Trong HTML, ảnh inline thường dùng `cid:`:

```html
<img src="cid:logo-demo@mail.example.org" alt="Logo">
```

Trong Spring Framework Mail:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("notify@example.org");
helper.setTo("tester@example.net");
helper.setSubject("Email kiểm thử ảnh inline");
helper.setText(
        "Đây là bản text.",
        "<p>Ảnh minh họa:</p>"
                + "<img src=\"cid:logo-demo@mail.example.org\" alt=\"Logo\">"
);

helper.addInline(
        "logo-demo@mail.example.org",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

Giá trị đưa vào `addInline` là Content-ID trần, không kèm `cid:` hoặc dấu ngoặc nhọn. Raw MIME có thể chứa:

```text
Content-Type: image/png
Content-ID: <logo-demo@mail.example.org>
Content-Disposition: inline
```

Nếu client không hiển thị ảnh, hãy phân biệt:

1. HTML có đúng `src="cid:..."` hay không.
2. Có inline part với `Content-ID` tương ứng không.
3. MIME nesting có liên quan tới `multipart/related` không.
4. Content-Type và byte nguồn có hợp lệ không.
5. Mail client có chặn hoặc xử lý inline resource theo cách riêng không.

Safe summary có thể báo số part có CID và số reference không khớp **mà không log giá trị CID thật**. Việc đối chiếu chi tiết có thể thực hiện trong memory với dữ liệu giả. Một cờ `hasContentId=true` không đủ để khẳng định CID trong HTML đã khớp.

## 18. Charset và Content-Transfer-Encoding

Khi email bị lỗi tiếng Việt, cần xem toàn bộ đường đi:

```text
File / Database / API bytes
          |
          v
Java String
          |
          v
Thymeleaf / template render
          |
          v
MimeMessageHelper charset
          |
          v
MIME Content-Type + transfer encoding
          |
          v
Mail client giải mã
```

Ví dụ:

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setSubject("Xác nhận thanh toán");
helper.setText(
        "Cảm ơn bạn đã thanh toán.",
        "<p>Cảm ơn bạn đã thanh toán.</p>"
);
```

Trong diagnostic summary, thông tin cần thiết có thể chỉ là:

```text
text/plain:
  charset=utf-8
  transferEncoding=quoted-printable

text/html:
  charset=utf-8
  transferEncoding=base64
```

Đây là ví dụ minh họa; thư viện chọn transfer encoding tùy nội dung và cách serialize. Không bắt buộc hai part phải dùng đúng loại encoding như sơ đồ.

Nếu MIME khai báo UTF-8 nhưng dữ liệu nguồn đã bị decode sai, việc sửa header không giải quyết được. Dùng fixture chứa chuỗi như `Nguyễn Thị Ánh – 1.250.000 ₫` để thử toàn pipeline mà không cần body email thật.

## 19. Filename và MIME parameter

File đính kèm có thể được tạo:

```java
helper.addAttachment(
        "hoa-don-mau.pdf",
        new ClassPathResource("mail/sample-invoice.pdf"),
        "application/pdf"
);
```

Để điều tra lỗi filename Unicode trên một client:

- Kiểm tra có `Content-Disposition: attachment`.
- Kiểm tra `hasFilename` thay vì log tên file thật.
- Xác nhận `Content-Type` và content encoding.
- Tạo một file mẫu `Hóa đơn thử nghiệm.pdf` để tái hiện.
- Nếu cần kiểm tra encoded parameter ở mức byte, dùng raw MIME của message test.

Không log raw filename từ production. Tên file có thể chứa tên khách hàng, mã định danh hoặc nội dung hồ sơ.

## 20. Các header có thể mang dữ liệu nhạy cảm

| Header | Rủi ro |
| --- | --- |
| `From`, `To`, `Cc`, `Bcc` | Danh tính và danh sách người nhận |
| `Subject` | Tên, mã hồ sơ, thông tin riêng tư |
| `Reply-To`, `Return-Path` | Địa chỉ nội bộ, hệ thống bounce |
| `Message-ID` | Có thể chứa miền hoặc correlation nội bộ |
| `Received` | IP, hostname và đường đi của thư |
| `Authentication-Results` | Thông tin domain và kiểm tra xác thực |
| `DKIM-Signature` | Thông tin chữ ký và domain |
| `List-Unsubscribe` | URL có thể chứa token |
| `X-*` tùy chỉnh | Có thể chứa tenant/user ID hoặc metadata nghiệp vụ |

Không mặc định đưa những header này vào log. Nếu cần biết một header có tồn tại, lưu boolean theo allowlist.

### DKIM và tính toàn vẹn

Thay đổi header/body của một thư đã ký có thể khiến DKIM signature không còn xác thực. Một bản đã thay recipient hoặc xóa nội dung để ẩn danh **không còn là dữ liệu byte-level tương đương bản gốc**.

Khi điều tra DKIM, cần phân biệt:

- Bản gốc được bảo vệ quyền dùng cho kiểm tra tính toàn vẹn, nếu được phép.
- Bản tái hiện hoặc bản đã ẩn danh dùng để thảo luận, không dùng chứng minh chữ ký gốc còn hợp lệ.

## 21. Kết hợp với MailSendException

Trong một batch, Spring có thể ném `MailSendException`. API:

```java
Map<Object, Exception> failed = ex.getFailedMessages();
```

Map chứa những message object được báo lỗi và exception tương ứng. Key **không mặc định là chuỗi email address**.

Không nên:

```java
// Không nên ghi object message thô.
logger.error("Failed message: {}", failedMessage);
```

Thay vào đó, tương quan với notification ID trước khi gửi:

```java
Map<Object, UUID> ids = new IdentityHashMap<>();

MimeMessage m1 = buildMessage(request1);
MimeMessage m2 = buildMessage(request2);

ids.put(m1, request1.notificationId());
ids.put(m2, request2.notificationId());

try {
    mailSender.send(m1, m2);
} catch (MailSendException ex) {
    for (var entry : ex.getFailedMessages().entrySet()) {
        UUID notificationId = ids.get(entry.getKey());
        String type =
                entry.getValue().getClass().getSimpleName();

        // Lưu correlation và exception class,
        // không lưu raw MimeMessage.
        recordFailure(notificationId, type);
    }
}
```

`IdentityHashMap` dùng để nhận diện **cùng object instance** trong một batch hiện tại. Không lưu object identity vào database hoặc dùng nó làm khóa retry sau restart. Notification ID phải là định danh nghiệp vụ bền vững.

### Trường hợp failed map rỗng

Nếu `getFailedMessages()` rỗng, không thể kết luận batch đã thành công. Có thể lỗi xảy ra ở tầng connection hoặc close và không kèm mapping từng message. Dùng exception class, trạng thái transport và danh sách notification ID trong batch để tiếp tục điều tra.

## 22. Không log thông báo exception tùy tiện

Exception từ mail library hoặc SMTP server đôi khi chứa địa chỉ recipient, host, sender hoặc thông tin khác do server tạo. Không nên tự động gửi toàn bộ `ex.getMessage()` và stack trace tới một nơi có quyền truy cập rộng.

Một record an toàn hơn:

```text
notificationId=4b26...
attempt=2
stage=SMTP_SUBMISSION
exceptionClass=MailSendException
rootFailureClass=SendFailedException
classification=RECIPIENT_REJECTION
outcome=FAILED
```

Nếu cần stack trace chi tiết, phải quản lý nó trong kênh diagnostic có quyền, có redaction và retention phù hợp. Đừng gắn raw MIME hoặc recipient list vào exception message của ứng dụng.

### MIME lỗi khác SMTP lỗi

| Exception / tình huống | Cần kiểm tra |
| --- | --- |
| `MailPreparationException` | Template, resource, xử lý MIME trước send |
| `MailAuthenticationException` | Credential, SMTP AUTH, TLS/provider policy |
| `MailSendException` | SMTP stage, reply, failed messages, transport outcome |
| `MessagingException` khi dựng message | Header, MIME part, attachment, charset |
| Timeout sau DATA | Acceptance không rõ, provider event/reconciliation |
| Client render khác nhau | Cấu trúc MIME và client test |

Raw MIME có thể giúp kiểm tra message được dựng ra sao; nó **không chứng minh** SMTP đã chấp nhận hoặc người nhận đã xem thư.

## 23. Một diagnostic record có thể trông như thế nào?

```json
{
  "notificationId": "b9a7...e1",
  "snapshotStage": "BEFORE_SEND",
  "templateKey": "order-confirmation",
  "templateVersion": "v7",
  "topLevelMimeType": "multipart/mixed",
  "partCount": 6,
  "hasTextPart": true,
  "hasHtmlPart": true,
  "inlinePartCount": 1,
  "attachmentCount": 1,
  "charsetCategory": "utf-8",
  "exceptionClass": "MailSendException",
  "outcome": "UNKNOWN"
}
```

Đây là schema minh họa. Các trường trong thực tế nên được tạo từ giá trị đã chuẩn hóa, không copy raw header. Dùng `notificationId` không chứa PII và hạn chế quyền đọc record theo chính sách.

Đừng để field tùy ý như `debugNotes` hoặc `rawHeaders` có thể nhận nội dung của người dùng và vượt qua bộ lọc allowlist.

## 24. Raw dump trong production cần quy trình riêng

Nếu metadata và message test chưa giải thích được lỗi, muốn thu raw từ production cần trả lời:

| Câu hỏi | Điều kiện |
| --- | --- |
| **Mục đích** | Lỗi cụ thể nào cần raw bytes? |
| **Phê duyệt** | Ai được phép yêu cầu và xem dump? |
| **Phạm vi** | Chỉ notification/attempt nào? |
| **Giảm dữ liệu** | Có thể bỏ body/attachment/header nào không? |
| **Lưu trữ** | Kho cách ly có encryption at rest/in transit? |
| **Quyền** | Least privilege và audit truy cập/tải xuống? |
| **Thời hạn** | TTL và quy trình xóa bản sao? |
| **Sự cố** | Nếu dump bị chia sẻ nhầm, quy trình incident response là gì? |

Không tải raw MIME về laptop cá nhân hoặc gửi file `.eml` qua chat, ticket công khai chỉ vì tiện làm việc. Dùng một kho chẩn đoán có kiểm soát và ghi kết luận đã ẩn danh vào ticket.

## 25. Giới hạn bộ nhớ và kích thước capture

Một email có attachment 25 MB có thể gây áp lực bộ nhớ lớn hơn 25 MB khi:

1. Message hoặc resource được dựng và giữ trong heap.
2. `ByteArrayOutputStream` tăng kích thước buffer.
3. `toByteArray()` tạo một bản sao mới.
4. Việc chuyển bytes thành String hoặc JSON tạo thêm dữ liệu.
5. Nhiều worker capture cùng lúc.

Biện pháp:

- Không bật raw capture cho mọi email.
- Đặt giới hạn tổng bytes, thời gian và số lượt capture.
- Giới hạn part count và nesting depth.
- Nếu được phép lưu raw, ưu tiên stream vào storage mã hóa có quyền thay vì ghi log.
- Không tự động thu attachment thật khi chỉ cần metadata.
- Đánh dấu `TRUNCATED` nếu dừng giữa chừng; đừng để người đọc tưởng file gốc bị lỗi MIME.

Gọi `Arrays.fill(bytes, (byte) 0)` trên một mảng không chứng minh toàn bộ bản sao dữ liệu trong JVM đã được xóa. Biện pháp mạnh hơn là **giảm hoặc tránh tạo raw bytes nhạy cảm ngay từ đầu**.

## 26. Hash và checksum: hữu ích nhưng không tự bảo mật

Trong môi trường test:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] hash = digest.digest(rawTestMime);
```

Hash có thể giúp biết hai snapshot bytes có giống nhau hay không. Nhưng:

- Hai dump khác nhau có thể chỉ vì `Date`, `Message-ID` hoặc boundary.
- Hash không nói nguyên nhân khác nhau ở đâu.
- Hash không chứng minh SMTP server đã nhận message.
- Hash của nội dung nhỏ/dễ đoán có thể bị suy ra bằng dictionary.
- Hash của bản đã redact không bằng hash của bản gốc.

Nếu cần correlation nội dung nhạy cảm, cân nhắc HMAC với khóa được quản lý và giới hạn retention; không đưa raw hash của nội dung khách hàng lên metric label công khai.

## 27. Không inspect và gửi cùng mutable message trên nhiều thread

`MimeMessage` là object mutable. Một thiết kế nguy hiểm:

```text
Thread A: build MimeMessage
Thread B: message.writeTo(diagnosticStream)
Thread C: mailSender.send(message)
```

Việc serialize, `saveChanges()`, đọc resource và cập nhật header có thể chồng lấn, làm snapshot không rõ thời điểm hoặc thay đổi timing của lỗi.

Nên:

1. Để một worker sở hữu việc dựng và gửi message.
2. Thu thập safe summary theo thứ tự rõ ràng trước gửi.
3. Chỉ tạo bản copy trong giai đoạn kiểm soát, không đọc/ghi cạnh tranh.
4. Truyền notification ID và DTO vào queue thay vì chia sẻ mutable message.
5. Attachment nên dùng resource có thể đọc lại, không chia sẻ `InputStream` đã đóng.

## 28. Mức thu thập theo môi trường

| Môi trường | Chính sách gợi ý |
| --- | --- |
| Unit test | Raw MIME từ fixture giả để test header/encoding |
| Integration test | SMTP capture server và test account |
| Local development | Dữ liệu giả, giới hạn file và retention |
| Staging | Safe summary mặc định; raw test theo scope |
| Production | Metadata tối thiểu; raw thật có quy trình riêng |
| Support ticket | Kết luận đã ẩn danh; không đính kèm raw thật |

GreenMail, Mailpit và MailHog có thể hữu ích để nhận message test, xem raw MIME hoặc kiểm tra cấu trúc. Không để SMTP test server không kiểm soát nhận thư production chứa PII.

### Quy trình tái hiện bằng test server

```text
Chọn lỗi cần tái hiện
       |
       v
Tạo fixture với tên/địa chỉ/token giả
       |
       v
Build MimeMessage theo cùng code path
       |
       v
JavaMailSender gửi tới SMTP test server
       |
       v
Capture raw MIME của dữ liệu giả
       |
       v
Phân tích MIME headers/parts/encoding
       |
       v
Sửa code và gửi test lại
```

## 29. Tình huống: Outlook không hiển thị PDF

Người dùng báo email có hóa đơn nhưng Outlook không hiện attachment.

**Cách điều tra:**

1. Tìm notification ID và xem trạng thái SMTP.
2. Đọc safe summary xem có `application/pdf` part, `disposition=attachment`, `hasFilename=true` không.
3. Dùng PDF mẫu cùng loại và kích thước để dựng lại.
4. Gửi vào Outlook test và Gmail test.
5. Nếu vẫn cần byte-level, xem raw capture của message test.
6. Chỉ thu raw production nếu có lý do đủ rõ và quyền phù hợp.

Kết luận trong ticket có thể là “template phiên bản X dùng disposition sai”, không cần ghi tên khách hàng hoặc filename thật.

## 30. Tình huống: email lỗi dấu tiếng Việt

Fixture:

```text
Người nhận thử nghiệm: Nguyễn Thị Ánh
Số tiền: 1.250.000 ₫
Thông điệp: Cảm ơn bạn – hẹn gặp lại.
```

Kiểm tra:

- Java String nhận từ database/API đã đúng chưa.
- Template render ra chuỗi gì.
- `text/plain` và `text/html` có charset phù hợp không.
- MIME transfer encoding có hoạt động không.
- Client có render khác nhau không.

Nếu fixture tái hiện lỗi, không cần body email thật để sửa encoding.

## 31. Tình huống: SMTP timeout sau DATA

Worker gửi hết message nhưng mất kết nối trước phản hồi cuối. Dù có full raw MIME, vẫn không biết chắc server đã chấp nhận message hay chưa.

Đây là **kết quả transport mơ hồ**, không phải lỗi MIME nhất thiết:

- Không retry ngay toàn bộ batch theo giả định chưa gửi.
- Ghi `UNKNOWN` và attempt metadata.
- Tra provider event/log nếu có.
- Áp dụng chính sách reconciliation hoặc retry có cân nhắc rủi ro duplicate.

Raw MIME giúp biết nội dung được dựng; không thể tự thay thế bằng chứng SMTP acceptance.

## 32. Tình huống: nghi header injection hoặc lộ token

Nếu nghi input người dùng tác động lên header:

- Không đăng raw header thật lên issue công khai.
- Tạo fixture có CR/LF, ký tự Unicode và nội dung bất thường để tái hiện.
- Kiểm tra validation/escaping khi đặt header.
- Đối chiếu kết quả transport nếu cần biết dữ liệu thực sự đã gửi.
- Nếu có thể đã lộ secret/token, áp dụng quy trình incident response và thu hồi token theo policy.

Đừng biến một lỗi bảo mật thành một vụ lộ dữ liệu thứ hai do quá trình chia sẻ dump.

## 33. Kiểm thử utility diagnostic

Nên kiểm thử bằng dữ liệu nhạy cảm **giả**, không dùng tài khoản thật:

| Input thử | Điều mong đợi trong safe summary |
| --- | --- |
| Subject có mã bí mật giả | Không xuất hiện mã |
| To/Cc/Bcc có email mẫu | Không xuất hiện địa chỉ thật |
| HTML có magic link giả | Không xuất hiện URL/token |
| Filename chứa tên riêng | Chỉ `hasFilename=true` |
| Attachment chứa dữ liệu mẫu | Không xuất hiện base64 hay bytes |
| Content-Type chứa `name` parameter | Chỉ xuất base type |
| Header có CR/LF bất thường | Không log nguyên giá trị |
| MIME lồng rất sâu | Dừng theo MAX_DEPTH |
| Quá nhiều body parts | Dừng theo MAX_PARTS |
| `getSize() == -1` | Thể hiện unknown |
| MIME parsing ném exception | Chỉ ghi loại lỗi an toàn |

Với MIME nhận từ bên ngoài, cần bổ sung quota byte, thời gian và tài nguyên ở tầng parser; chỉ giới hạn số record sau khi đã parse chưa đủ để chống resource exhaustion.

## 34. Anti-pattern: ghi tệp .eml khi xảy ra exception

Ví dụ không nên triển khai ở production:

```java
try {
    mailSender.send(message);
} catch (MailException ex) {
    message.writeTo(new FileOutputStream(
            "last-failed-email.eml"));
    throw ex;
}
```

Rủi ro:

- File có tên cố định bị ghi đè hoặc race giữa nhiều worker.
- Nội dung chứa PII/attachment/token trên ổ đĩa không quản lý quyền.
- Không có TTL, audit hoặc encryption.
- Lỗi khi ghi dump che khuất lỗi SMTP ban đầu.
- Bản dump sau lỗi có thể khác message mà server nhận.

Thay vào đó: ghi notification ID và exception class, lấy safe summary có giới hạn và chỉ yêu cầu raw trong kênh chẩn đoán riêng khi thật sự cần.

## 35. Anti-pattern: replay raw message thật

Không lấy file `.eml` production gửi lại chỉ để tái hiện:

- Có thể gửi trùng email cho khách hàng.
- Có thể gửi token hoặc nội dung cá nhân sang địa chỉ không phù hợp.
- Có thể kích hoạt link/tracking hoặc workflow khác.
- Bản đã thay người nhận, subject hoặc attachment không còn giống byte gốc.

Hãy tạo fixture giả, thay recipient/envelope bằng test mailbox và xác nhận không còn token thật. Ghi rõ artifact này là **message tái hiện** chứ không phải byte-identical evidence.

## 36. Bảng chọn kỹ thuật theo nhu cầu

| Nhu cầu | Cách ưu tiên | Không cần làm |
| --- | --- | --- |
| Xác nhận có bản HTML | MIME structure summary | Dump body |
| Kiểm tra attachment | Part type/disposition/count | Log filename |
| Kiểm tra ảnh inline | CID count/mapping ẩn danh | Log CID thật |
| Kiểm tra charset | Allowlist + fixture Unicode | Dump thư khách hàng |
| Chẩn đoán SMTP AUTH | Config/provider response | Đọc nội dung MIME |
| Chẩn đoán RCPT rejection | SMTP transport evidence | Dựa vào To header |
| Chẩn đoán boundary | Raw MIME test capture | Public raw production |
| Chẩn đoán byte attachment | Test sample hoặc restricted comparison | Log PDF thật |
| Chia sẻ cho support | Safe summary | Đính kèm raw .eml |
| Theo dõi gửi trùng | Notification ID/attempt/provider event | Coi Message-ID là dedup tuyệt đối |

## 37. Checklist triển khai

### Giai đoạn tạo message

- [ ] Có notification ID và template version.
- [ ] Notification ID không chứa thông tin cá nhân.
- [ ] Inspector thu thập các field allowlist và có giới hạn part/depth.
- [ ] Một thread/worker sở hữu mutable message tại từng giai đoạn.
- [ ] Không log Subject, recipient hoặc body.

### Giai đoạn gửi

- [ ] Không gọi `writeTo(System.out)`.
- [ ] Phân biệt lỗi chuẩn bị MIME với lỗi SMTP transport.
- [ ] Gắn stage/timestamp cho snapshot.
- [ ] Không coi before-send dump là SMTP wire capture.
- [ ] Không log exception message chưa được sanitize.

### Giai đoạn điều tra

- [ ] Đã thử tái hiện bằng fixture giả.
- [ ] Nếu cần raw thật, đã có phê duyệt và scope rõ.
- [ ] Có encryption, least privilege, audit, TTL.
- [ ] Không sử dụng regex trên raw MIME như cơ chế ẩn danh duy nhất.
- [ ] Không đưa raw dump vào chat/ticket chung.
- [ ] Không dùng raw MIME để kết luận delivery/Inbox.

### Sau điều tra

- [ ] Kết luận không chứa dữ liệu nhạy cảm.
- [ ] Xóa artifact theo retention.
- [ ] Thu hồi liên kết chia sẻ tạm.
- [ ] Giữ fixture giả phục vụ regression test.

## 38. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| `writeTo(System.out)` | Lộ raw email trong log | Safe MIME summary |
| Coi copy constructor là ẩn danh | Vẫn lộ body/attachment | Bảo vệ copy như message thật |
| Coi copy là exact wire evidence | Sai giai đoạn/byte | Ghi stage và nguồn capture |
| Xóa To/Subject bằng regex | Bỏ sót Bcc, token, encoded body | Tạo report allowlist |
| Coi base64 là encryption | Nội dung dễ giải mã | Quản lý quyền và encryption |
| Log full Content-Type | Parameter có thể chứa thông tin | Chỉ lấy base type |
| Log filename/CID thật | Lộ tên/định danh | Boolean/count |
| Không giới hạn dump | OOM/disk growth | Giới hạn byte và scope |
| Copy đồng thời với send | Snapshot không nhất quán | Ownership và stage rõ |
| Replay thư production | Gửi trùng/lộ token | Fixture test |
| Coi dump là bằng chứng delivered | Báo sai trạng thái | Provider event |
| Lưu dump vô thời hạn | Tăng rủi ro dữ liệu | TTL/audit/delete |
| Truncate không ghi chú | Hiểu nhầm MIME gốc hỏng | Gắn nhãn TRUNCATED |
| Hash nội dung đưa vào metric | Cardinality và privacy risk | Correlation ID |

## 39. Bài tập tình huống

### A. Safe summary cho biết ảnh inline có Content-ID

Điều đó có chứng minh HTML đang tham chiếu đúng CID không?

**Trả lời:** chưa. Summary chỉ biết có header; cần đối chiếu mapping URI `cid:` và Content-ID trong môi trường cho phép, cùng cấu trúc `multipart/related`.

### B. Charset UTF-8 nhưng tên người vẫn sai

Có phải cần raw MIME thật không?

**Trả lời:** chưa chắc. Dữ liệu có thể đã sai từ file hoặc database trước khi tạo message. Hãy tái hiện với chuỗi test có dấu và kiểm tra toàn pipeline.

### C. Raw MIME có địa chỉ To

Có thể khẳng định SMTP đã chấp nhận `RCPT TO` cho địa chỉ đó không?

**Trả lời:** không. MIME header không phải transcript SMTP envelope/reply. Cần provider hoặc transport evidence.

### D. Developer đã xóa To/Subject bằng regex

Có thể chia sẻ file .eml vào issue công khai không?

**Trả lời:** không. Header folding, Bcc, token trong body, base64, filename và attachment có thể vẫn lộ dữ liệu.

### E. SMTP timeout sau DATA

Có raw bytes rồi, có thể retry ngay không?

**Trả lời:** không thể suy ra acceptance từ dump. Cần đánh dấu kết quả mơ hồ và reconcile theo chính sách.

### F. Copy được tạo trước khi thêm PDF

Copy không có attachment có chứng minh message đã gửi thiếu PDF không?

**Trả lời:** không. Phải biết stage của copy; attachment có thể được thêm sau thời điểm snapshot.

## 40. Kết luận

**Bản sao `MimeMessage`** và **raw MIME dump** là công cụ hữu ích để điều tra Spring Framework Mail, nhưng chúng có thể chứa toàn bộ nội dung email và dữ liệu cá nhân. `new MimeMessage(original)` chỉ tạo object riêng, không tự ẩn danh. `MimeMessage.writeTo(...)` ghi bytes của message tại thời điểm serialization, không phải bản tóm tắt an toàn và không chứa toàn bộ SMTP envelope.

Cách tiếp cận nên bắt đầu bằng **notification ID, exception class, template version, transport outcome và MIME structure summary đã chuẩn hóa**. Nếu cần byte-level, ưu tiên tái hiện bằng dữ liệu giả trên SMTP test server. Chỉ khi thật sự cần dữ liệu production mới thu raw theo một quy trình được phê duyệt, giới hạn scope, mã hóa, phân quyền, audit và TTL.

Nhờ phân biệt rõ **message object**, **serialized snapshot**, **SMTP evidence** và **diagnostic metadata**, nhóm phát triển có thể giải thích các lỗi MIME, charset, ảnh inline, attachment và header chính xác hơn mà không biến quá trình debug thành một nguồn rò rỉ dữ liệu mới.
