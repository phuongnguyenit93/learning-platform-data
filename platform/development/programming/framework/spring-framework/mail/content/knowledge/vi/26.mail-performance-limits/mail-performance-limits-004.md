# Giới hạn kích thước message và dữ liệu trong bộ nhớ

Trong **Spring Framework Mail**, một email thông báo ngắn thường chỉ chiếm vài KiB. Nhưng email có báo cáo PDF, nhiều ảnh inline, HTML lớn hoặc hàng chục attachment có thể làm ứng dụng tiêu thụ rất nhiều heap, bộ nhớ đĩa tạm và băng thông. Một file gốc 10 MiB không đồng nghĩa với một email MIME 10 MiB: dữ liệu thường được mã hóa Base64, đóng gói thành nhiều MIME part và cộng thêm header, boundary. Khi hàng trăm tác vụ `@Async` cùng giữ attachment trong `byte[]`, ứng dụng có thể cạn bộ nhớ trước khi SMTP relay nhận được bất kỳ thư nào.

Bài toán này có **hai giới hạn độc lập nhưng liên quan**:

1. **Kích thước email được gửi:** giới hạn của ứng dụng, SMTP submission server, mail provider và mail server đích đối với message sau khi đóng gói.
2. **Dữ liệu trong bộ nhớ ứng dụng:** số byte đang được Java giữ trong file upload, string HTML, các mảng attachment, MIME object, buffers, task queue và worker đang chạy.

Không có một con số kích thước tối đa chung cho mọi hệ thống SMTP. `JavaMailSender` và `MimeMessageHelper` không tự động làm thay việc xác định chính sách size, điều tiết nguồn lực và xử lý provider rejection. Bài học này trình bày cách ước tính MIME, kiểm soát attachment, tránh dữ liệu lớn trong heap, thiết kế worker/outbox, đo lường, retry và kiểm thử các giới hạn đó.

## 1. Kích thước file gốc khác kích thước email MIME

Một email có file đính kèm thường có cấu trúc:

~~~text
RFC 5322 message
├── Header: From, To, Subject, Date, Message-ID...
└── MIME body
    └── multipart/mixed
        ├── multipart/alternative
        │   ├── text/plain
        │   └── text/html
        ├── attachment: application/pdf
        │   └── base64 encoded content
        └── inline image: image/png
            └── base64 encoded content
~~~

Tổng kích thước message có thể gồm:

- Header của email và header riêng của từng MIME part.
- Subject/tên file Unicode sau khi được encode.
- Plain text và HTML; nếu gửi cả hai thì đều được tính.
- Attachment gốc sau khi transfer-encode.
- Inline images và những resource khác.
- MIME boundaries, line breaks, Content-Type và Content-Disposition.
- Dữ liệu mà thư viện hoặc transport thêm khi tạo message.

Vì thế **giới hạn attachment gốc** và **giới hạn total serialized MIME message** phải được đặt tên, đo đếm và kiểm tra riêng.

Ví dụ, một bản PDF 8 MiB, một file CSV 3 MiB và logo inline 200 KiB không tạo thành email chỉ lớn khoảng 11,2 MiB. MIME encoding và metadata làm message gửi qua wire lớn hơn.

## 2. Giới hạn có thể xuất hiện ở nhiều tầng

~~~mermaid
flowchart LR
    A["HTTP upload / Report generator"] --> B["Spring Mail application"]
    B --> C["JavaMailSender"]
    C --> D["SMTP submission relay"]
    D --> E["Provider relay"]
    E --> F["Receiving MX"]
    F --> G["Mailbox"]
~~~

| Tầng | Giới hạn thường gặp | Điều xảy ra khi vượt |
| --- | --- | --- |
| Reverse proxy / API gateway | HTTP body size | Request bị chặn trước Spring MVC |
| Spring multipart parser | File size / request size | Upload bị từ chối |
| Business mail policy | File, số attachment, MIME budget | Từ chối trước khi tạo mail job |
| JVM | Heap, thread, queue, file descriptors | GC tăng, OOM, task reject |
| Temporary disk | Upload staging, generated report | Không tạo/đọc file được |
| SMTP submission relay | Max message size | SMTP từ chối gửi |
| Provider | Size, quota, content policy | Reject hoặc defer |
| Server nhận | Message size, mailbox/policy | Bounce hoặc reject downstream |

Một relay có thể chấp nhận message nhưng mail server đích vẫn từ chối vì có giới hạn thấp hơn. Ngược lại, limit của Spring ứng dụng cần đủ bảo thủ để tránh gửi sát giới hạn provider rồi gặp lỗi.

**Không giả định provider cho phép file 25 MiB nghĩa MIME message 25 MiB luôn được chấp nhận.** Một số dịch vụ ghi limit tổng message, dịch vụ khác công bố attachment limit hoặc dùng đơn vị MB khác nhau. Phải xem hợp đồng chính xác của hệ thống đang sử dụng.

## 3. MB, MiB và byte

| Đơn vị | Số byte |
| --- | ---: |
| 1 kB | 1.000 |
| 1 MB | 1.000.000 |
| 1 KiB | 1.024 |
| 1 MiB | 1.048.576 |

Trong code, giới hạn nên dùng `long` và tên rõ nghĩa:

~~~java
private static final long MIB = 1024L * 1024L;

private static final long MAX_RAW_ATTACHMENT_BYTES =
        8L * MIB;

private static final long MAX_ESTIMATED_MIME_BYTES =
        18L * MIB;
~~~

Các giá trị 8 MiB và 18 MiB trong ví dụ chỉ minh họa chính sách ứng dụng; không phải giá trị mặc định hoặc mức được Spring/provider bảo đảm.

Tránh viết tên `maxEmailSize` nếu không biết nó tính file gốc, HTML, toàn bộ MIME hay một request HTTP.

## 4. Base64 làm attachment lớn hơn bao nhiêu?

Nhiều attachment MIME sử dụng **Content-Transfer-Encoding: base64**. Cứ 3 byte dữ liệu gốc được biểu diễn thành 4 ký tự ASCII. Nếu dữ liệu có `N` byte:

\[
\mathrm{Base64Chars}(N)=4\left\lceil \frac{N}{3}\right\rceil
\]

Đây là mức tăng khoảng 33% trước khi cộng ngắt dòng. MIME base64 thường fold thành dòng tối đa 76 ký tự với CRLF. Một công thức ước lượng phần dữ liệu truyền đi:

\[
\mathrm{ApproxWireBytes}(N)
=
4\left\lceil \frac{N}{3}\right\rceil
+
2\left\lceil \frac{4\lceil N/3\rceil}{76}\right\rceil
\]

Đó là **ước lượng cho body của một MIME attachment base64**. Nó chưa cộng boundary, part headers, subject, body HTML và phần khác.

| File gốc | Base64 thuần xấp xỉ | Có CRLF xấp xỉ |
| --- | --- | --- |
| 1 MiB | 1,33 MiB | 1,37 MiB |
| 5 MiB | 6,67 MiB | 6,84 MiB |
| 10 MiB | 13,33 MiB | 13,68 MiB |
| 15 MiB | 20 MiB | 20,53 MiB |

**Hệ quả:** một file gốc 15 MiB có thể vượt giới hạn tổng message 20 MiB ngay sau encoding. Nếu người dùng hỏi “tại sao file 15 MiB không gửi được khi provider nói 20 MiB?”, đây là nguyên nhân đầu tiên cần kiểm tra.

## 5. Tách kích thước trên wire và kích thước trên heap

Một file gốc 10 MiB có thể tạo message SMTP hơn 13 MiB. Tuy nhiên, Java heap không nhất thiết bằng 13 MiB. Nó có thể lớn hoặc nhỏ hơn, tùy đường xử lý.

Ví dụ ứng dụng tự tạo nhiều object:

~~~text
MultipartFile
  -> getBytes(): byte[10 MiB]
  -> Arrays.copyOf(): byte[10 MiB]
  -> Base64 String: encoded content
  -> MimeMessage / DataSource
  -> Mail task queue giữ reference
  -> Jakarta Mail serialization buffers
~~~

Nếu xử lý qua `FileSystemResource`, ứng dụng không bắt buộc tự giữ toàn bộ file trong một mảng byte ngay từ đầu. Nhưng điều này **không cam kết zero-copy**: thư viện, renderer, transport và network stack vẫn có thể buffer.

Điều cần kiểm soát là **peak retained data** trong request, worker và queue, không chỉ kích thước file đầu vào.

## 6. Spring Mail có tự chặn MIME message quá lớn không?

Một đoạn gửi mail:

~~~java
MimeMessage message =
        mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message, true, "UTF-8"
        );

helper.setFrom("reports@example.org");
helper.setTo("recipient@example.org");
helper.setSubject("Báo cáo tháng");

helper.setText(
        "Báo cáo đính kèm.",
        "<p>Báo cáo đính kèm.</p>"
);

helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportFile)
);

mailSender.send(message);
~~~

Mã này không có một dòng nào bảo đảm message cuối cùng dưới giới hạn provider. `MimeMessageHelper` tạo các phần MIME; `JavaMailSender` gửi chúng qua mail transport.

**Không tự giả định một property tên `spring.mail.max-message-size` tồn tại và Spring Boot sẽ enforce size cho mọi SMTP provider.** Ứng dụng phải có policy riêng và vẫn xử lý phản hồi từ provider.

Thông thường nên kiểm tra kích thước từ **metadata attachment và body** trước khi tạo/gửi message, dùng headroom thay vì đợi SMTP từ chối.

## 7. SMTP SIZE extension là gì?

Một số SMTP server quảng bá khả năng **SIZE** khi client gửi `EHLO`:

~~~text
C: EHLO app.example.org
S: 250-mail.provider.example
S: 250-SIZE 20971520
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN
~~~

Đây là phiên trao đổi minh họa. Server có thể thông báo giới hạn theo byte hoặc hỗ trợ extension theo cách phù hợp implementation.

Tuy nhiên:

- Không phải mọi server đều công bố `SIZE`.
- Limit có thể phụ thuộc account/endpoint.
- Một message dưới SIZE vẫn có thể bị từ chối vì policy khác.
- Server đích sau relay có thể có limit nhỏ hơn.
- Client có thể gặp từ chối khi đang gửi nội dung.

Vì vậy, **SMTP SIZE không thay thế validation phía ứng dụng**, cũng không bảo đảm delivery thành công sau khi relay ban đầu chấp nhận.

## 8. Phân loại lỗi kích thước message

Một phản hồi SMTP có thể là:

~~~text
552 5.3.4 Message size exceeds fixed maximum message size
~~~

Đây chỉ là ví dụ minh họa; mã và thông báo chính xác thay đổi theo provider. Một lỗi `5xx` thường cho thấy yêu cầu đó không nên retry mù quáng, trong khi một số lỗi `4xx` có thể tạm thời.

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Hard message size rejection | MIME vượt giới hạn | Không retry cùng payload vô hạn |
| Temporary SMTP failure | Relay tạm không sẵn sàng | Retry sau backoff |
| SMTP timeout | Có thể chưa rõ relay đã nhận chưa | Xử lý outcome unknown |
| Attachment missing | File đã bị xóa hoặc đường dẫn sai | Xử lý storage/lifecycle |
| Attachment IO failure | Không đọc được nguồn dữ liệu | Phân loại IO và retry nếu phù hợp |
| Downstream size bounce | Server đích từ chối sau submit | Xử lý bounce/delivery feedback |

Thư viện `JavaMailSender` có thể ném `MailException` và chứa nguyên nhân từ Jakarta Mail. Không chỉ tìm chuỗi “too large” trong mọi exception; nên phân loại bằng reply code, enhanced status và thông điệp provider theo hợp đồng.

### Đừng biến hard limit thành retry storm

Nếu message được xác định vượt giới hạn cố định, retry mỗi 30 giây với cùng MIME không giúp giảm size. Thay vào đó, cần gửi link tải, giảm attachment, thay đổi nội dung hoặc đánh dấu job cần can thiệp.

## 9. Những nguồn attachment phổ biến

Spring Mail hỗ trợ nhiều nguồn nội dung:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes)
);
~~~

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(verifiedFile)
);
~~~

~~~java
helper.addAttachment(
        "invoice.pdf",
        inputStreamSource,
        "application/pdf"
);
~~~

| Nguồn | Ưu điểm | Điều cần lưu ý |
| --- | --- | --- |
| `ByteArrayResource` | Đơn giản, phù hợp byte[] nhỏ | Giữ toàn bộ file trong heap |
| `FileSystemResource` | Có thể mở stream theo yêu cầu | File phải tồn tại đến lúc gửi |
| `InputStreamSource` | Có thể tự thiết kế cách mở stream | Mỗi lần được gọi phải cung cấp stream hợp lệ |
| Durable storage key | Queue/outbox giữ metadata nhỏ | Worker cần resolve và tải từ storage |
| Temp file | Giảm nhu cầu giữ RAM | Phải quản lý disk quota, TTL, cleanup |

Đổi `ByteArrayResource` sang `FileSystemResource` có thể giảm heap do ứng dụng tự giữ, nhưng chỉ hiệu quả nếu các bước trước và sau không tiếp tục dùng `Files.readAllBytes` hoặc serialize toàn bộ attachment vào RAM.

## 10. ByteArrayResource và getBytes()

Một anti-pattern với file lớn:

~~~java
byte[] uploaded =
        multipartFile.getBytes();

helper.addAttachment(
        multipartFile.getOriginalFilename(),
        new ByteArrayResource(uploaded)
);
~~~

`MultipartFile.getBytes()` đưa toàn bộ upload vào `byte[]`. `ByteArrayResource` giữ reference tới mảng byte đó. Nếu một job còn trong queue hoặc được giữ bởi future/callback, dữ liệu vẫn sống trong heap.

Với file nhỏ được giới hạn rõ, cách làm này có thể hợp lý. Với file nhiều MiB, hàng trăm job và nhiều lần retry, nó là nguồn gây memory pressure.

### Ví dụ capacity

Giả sử 500 job chờ gửi, mỗi job giữ một attachment `byte[]` 12 MiB:

\[
500 \times 12\ \mathrm{MiB} = 6000\ \mathrm{MiB}
\]

Chỉ riêng byte arrays đã xấp xỉ 5,86 GiB, chưa tính String, MIME object, heap overhead hay worker đang hoạt động. Một executor có đúng 4 thread **vẫn có thể hết bộ nhớ do 500 queued payload**.

### Không tự mã hóa Base64 thành String nếu không cần

~~~java
String encoded =
        Base64.getMimeEncoder()
                .encodeToString(pdfBytes);
~~~

Kết quả tạo thêm một object lớn. Khi dùng `MimeMessageHelper.addAttachment`, Jakarta Mail thường thực hiện transfer encoding phù hợp lúc serialize. Tự encode trước có thể tạo copy không cần thiết hoặc double-encode nếu gắn sai.

## 11. InputStreamResource và stream chỉ đọc được một lần

Một lỗi thường gặp:

~~~java
InputStream opened =
        multipartFile.getInputStream();

helper.addAttachment(
        "report.pdf",
        new InputStreamResource(opened),
        "application/pdf"
);
~~~

Nguồn dữ liệu được sử dụng bởi Jakarta Mail có thể cần mở stream nhiều lần, ví dụ khi xử lý MIME rồi serialize/gửi. Một `InputStreamResource` bọc stream đã mở **không đảm bảo stream mới** sau khi stream cũ bị consume hoặc đóng.

Hệ quả có thể là:

- Attachment rỗng hoặc thiếu byte.
- Exception vì stream đã được đọc.
- Lỗi sau khi HTTP request đã kết thúc.
- Retry không thể đọc lại dữ liệu.

Nguồn có khả năng đọc lại:

~~~java
InputStreamSource source = () ->
        Files.newInputStream(
                storedAttachmentPath
        );

helper.addAttachment(
        "report.pdf",
        source,
        "application/pdf"
);
~~~

Ở ví dụ, `storedAttachmentPath` phải là path đã được ứng dụng xác thực và quản lý. Mỗi lần gọi `getInputStream()` tạo một stream mới. Nhưng file vẫn phải tồn tại và không bị thay đổi ngoài ý muốn giữa các lượt đọc.

## 12. FileSystemResource: lợi ích và giới hạn

Một worker có thể tham chiếu file lớn qua filesystem:

~~~java
Path trustedPath =
        storage.resolveAuthorizedPath(attachmentId);

FileSystemResource resource =
        new FileSystemResource(
                trustedPath.toFile()
        );

helper.addAttachment(
        "monthly-report.pdf",
        resource
);
~~~

`storage.resolveAuthorizedPath` là method giả định của ứng dụng, không có sẵn trong Spring. Nó phải kiểm tra tenant/actor có quyền và path không thoát khỏi storage root.

Ưu điểm: không cần tự gọi `Files.readAllBytes`. Giới hạn:

- File vẫn tiêu thụ disk/I/O.
- Jakarta Mail có thể buffer khi xử lý.
- File có thể bị xóa trước khi worker bắt đầu.
- Replica/pod khác có thể không thấy local path.
- File có thể thay đổi giữa validation và gửi.
- Nếu nhiều worker đọc file lớn cùng lúc, disk và network vẫn có thể nghẽn.

**FileSystemResource không tự tạo durability, size limit hay authorization.**

## 13. HTTP upload limit và SMTP limit là hai lớp riêng

Với Spring Boot, có thể giới hạn multipart HTTP request:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 8MB
      max-request-size: 12MB
~~~

Những property này áp dụng cho multipart upload qua HTTP, **không tự giới hạn message do `JavaMailSender` gửi ra**.

Một báo cáo được sinh trực tiếp trên server không đi qua HTTP upload, nhưng vẫn cần mail size policy. Một file upload 8 MiB được HTTP chấp nhận chưa chắc email chứa file đó nằm dưới 12 MiB MIME.

Có thể cần thêm limit ở API gateway, reverse proxy, controller/application layer và managed storage. Không chỉ dựa vào `MultipartFile.getSize()` hoặc `Content-Length` nếu client đang stream dữ liệu và có khả năng báo sai metadata.

## 14. Thiết kế MailSizePolicy nhiều cấp

Một policy nên kiểm tra tối thiểu:

- Số attachment.
- Kích thước từng attachment gốc.
- Tổng attachment gốc.
- Kích thước plain text và HTML.
- Ảnh inline và metadata.
- MIME message dự kiến sau encoding.
- Tổng tài nguyên in-flight.
- Temporary disk quota và retention.

Một ví dụ giả định:

~~~text
Max attachments:           5
Max single attachment:     8 MiB
Max total raw attachments: 12 MiB
Max HTML UTF-8 content:  512 KiB
Estimated MIME budget:    18 MiB
~~~

Các con số chỉ để minh họa. Nếu provider giới hạn tổng message thấp hơn, phải giảm ngân sách. Nếu attachment là report nhạy cảm, chính sách có thể chọn chỉ cho link tải thay vì gửi file.

**Kiểm tra tổng byte và số lượng part đồng thời.** Hàng nghìn file vài byte vẫn tạo ra rất nhiều MIME metadata và overhead.

## 15. Ví dụ tính ước lượng MIME trong Java

~~~java
import java.util.List;

public final class MailSizePolicy {

    private static final long MIB = 1024L * 1024L;
    private static final long MAX_SINGLE = 8 * MIB;
    private static final long MAX_RAW_TOTAL = 12 * MIB;
    private static final long MAX_ESTIMATED = 18 * MIB;
    private static final long MIME_HEADROOM =
            256 * 1024L;
    private static final int MAX_ATTACHMENTS = 5;

    public void requireAllowed(
            List<AttachmentMeta> files,
            long textBytes) {

        if (textBytes < 0 || textBytes > MIB) {
            throw new MailSizeException(
                    "Body vượt giới hạn"
            );
        }

        if (files.size() > MAX_ATTACHMENTS) {
            throw new MailSizeException(
                    "Quá nhiều attachment"
            );
        }

        long rawTotal = 0;
        long estimated = Math.addExact(
                textBytes, MIME_HEADROOM
        );

        for (AttachmentMeta file : files) {
            long raw = file.byteLength();

            if (raw < 0 || raw > MAX_SINGLE) {
                throw new MailSizeException(
                        "Attachment vượt giới hạn"
                );
            }

            rawTotal = Math.addExact(
                    rawTotal, raw
            );

            estimated = Math.addExact(
                    estimated,
                    approximateBase64Bytes(raw)
            );
        }

        if (rawTotal > MAX_RAW_TOTAL
                || estimated > MAX_ESTIMATED) {
            throw new MailSizeException(
                    "Email dự kiến vượt ngân sách MIME"
            );
        }
    }

    private static long approximateBase64Bytes(long n) {
        // n đã bị giới hạn ở MAX_SINGLE.
        long encodedChars = 4L * ((n + 2L) / 3L);
        long lines = (encodedChars + 75L) / 76L;

        return Math.addExact(
                encodedChars,
                Math.multiplyExact(2L, lines)
        );
    }

    public record AttachmentMeta(
            String storageKey,
            String filename,
            long byteLength) {
    }
}
~~~

`MailSizeException` là exception ứng dụng tự định nghĩa. `MIME_HEADROOM` chỉ là **dự phòng minh họa**, không phải một upper bound được chuẩn MIME bảo đảm.

Các giới hạn của cách tính:

- Body text có thể dùng quoted-printable hoặc transfer encoding khác.
- Subject, filename và Unicode header có thể dài hơn bản raw.
- Inline images cần được tính.
- MIME boundary và provider serialization có thể khác.
- File có thể thay đổi sau khi đọc metadata.
- Provider có thể áp limit thấp hơn.

Vì vậy, đây là **preflight estimate**, không phải bằng chứng message luôn được relay chấp nhận. Khi cần hard upper bound, phải xác định cách serialize và kiểm tra phù hợp với pipeline thật, đồng thời vẫn xử lý SMTP rejection.

## 16. String.length() không phải byte length

Trong Java:

~~~java
int chars = html.length();
~~~

`String.length()` đếm UTF-16 code units, không phải số byte UTF-8. Tiếng Việt có dấu, emoji và ký tự khác có thể chiếm nhiều byte.

Với body nhỏ đã có giới hạn:

~~~java
long utf8Bytes =
        html.getBytes(
                StandardCharsets.UTF_8
        ).length;
~~~

Lệnh này tạo mảng byte mới. Với HTML rất lớn, không nên tạo thêm bản sao chỉ để đo; hãy đặt giới hạn input/rendering và dùng streaming encoder/counting khi thực sự cần.

Kích thước UTF-8 raw cũng chưa bằng MIME serialized bytes: transfer encoding, line endings và headers còn làm thay đổi dung lượng.

## 17. Đo MIME serialized size trong test

Với email **nhỏ và có giới hạn**, có thể đếm byte sau serialization:

~~~java
MimeMessage message =
        mailSender.createMimeMessage();

// Dựng message hoàn chỉnh.

message.saveChanges();

ByteArrayOutputStream out =
        new ByteArrayOutputStream();

message.writeTo(out);

long serializedBytes = out.size();
~~~

**Không đưa cách này lên production hot path cho mọi attachment lớn.** `ByteArrayOutputStream` giữ toàn bộ MIME bytes trong RAM, có thể tạo một bản sao lớn trong lúc `MimeMessage`/resources cũng đang tồn tại.

Một counting stream không giữ toàn bộ output:

~~~java
public final class CountingOutputStream
        extends OutputStream {

    private long bytes;

    @Override
    public void write(int value) {
        bytes = Math.addExact(bytes, 1);
    }

    @Override
    public void write(
            byte[] data,
            int off,
            int len) {
        bytes = Math.addExact(bytes, len);
    }

    public long count() {
        return bytes;
    }
}
~~~

~~~java
message.saveChanges();

CountingOutputStream counter =
        new CountingOutputStream();

message.writeTo(counter);

long serializedBytes = counter.count();
~~~

Counting stream không giữ toàn output, nhưng **serialization vẫn đọc dữ liệu** và Jakarta Mail có thể buffer bên trong. Nếu tiếp tục gọi `mailSender.send`, source phải mở lại được; đo có thể làm tăng CPU/disk I/O và chi phí gửi. Header hoặc resource thay đổi giữa đo và gửi cũng có thể làm kích thước khác.

## 18. Không giữ byte[] lớn trong async command

Ví dụ không phù hợp với bulk mail:

~~~java
public record SendReportCommand(
        String recipient,
        byte[] reportPdf) {
}
~~~

~~~java
@Async("mailExecutor")
public void sendReport(SendReportCommand command) {
    helper.addAttachment(
            "report.pdf",
            new ByteArrayResource(
                    command.reportPdf()
            )
    );

    mailSender.send(message);
}
~~~

Nếu 200 command cùng chờ trong executor, queue giữ 200 mảng PDF. `@Async` không làm dữ liệu biến mất; nó chỉ chuyển thao tác gửi sang thread khác khi đi qua Spring proxy.

Thiết kế ít giữ heap hơn:

~~~java
public record SendReportCommand(
        UUID jobId,
        String recipientContactId,
        String attachmentStorageKey) {
}
~~~

Worker tra key từ storage được quản lý và mở stream khi chuẩn bị message. Queue chỉ giữ ID/metadata nhỏ. Khi cần retry hoặc restart, storage cần có độ bền và quyền truy cập phù hợp, không chỉ là file tạm của HTTP request.

## 19. Không trông đợi file tạm sống lâu hơn request

Một race:

~~~text
HTTP request:
  nhận MultipartFile
  lưu file tạm
  schedule @Async send(tempPath)
  request kết thúc
  cleanup xóa file

Mail worker:
  bắt đầu sau khi request kết thúc
  mở tempPath
  FileNotFoundException
~~~

Tương tự, `MultipartFile.getInputStream()` có thể trả một stream không còn hợp lệ khi request kết thúc. Không chuyển raw request/stream cho worker rồi giả định nó có thể sử dụng vô hạn.

Luồng tốt hơn:

~~~mermaid
flowchart TD
    A["HTTP upload / report generated"] --> B["Kiểm tra policy size"]
    B --> C["Lưu vào managed storage"]
    C --> D["Tạo mail job chứa storage key"]
    D --> E["Worker đọc job"]
    E --> F["Mở resource khi gửi"]
    F --> G["JavaMailSender.send"]
    G --> H["Ghi trạng thái / retry"]
    H --> I["Cleanup theo retention"]
~~~

Nếu job có retry trong nhiều giờ, attachment cần tồn tại tới khi job kết thúc theo chính sách. Nếu dùng nhiều replica, object store hoặc storage chung phù hợp hơn local `/tmp` của một container.

## 20. Staging upload theo stream và giới hạn byte

Một ví dụ chuyển file lớn vào khu vực lưu tạm có quản lý mà không giữ toàn bộ nội dung trong heap:

~~~java
public StoredAttachment stage(
        InputStream source,
        String originalName) throws IOException {

    Path target = Files.createTempFile(
            stagingRoot,
            "mail-",
            ".upload"
    );

    long written = 0;

    try (OutputStream out =
            Files.newOutputStream(target)) {

        byte[] buffer = new byte[64 * 1024];
        int n;

        while ((n = source.read(buffer)) != -1) {
            written = Math.addExact(written, n);

            if (written > maxFileBytes) {
                throw new AttachmentTooLargeException();
            }

            out.write(buffer, 0, n);
        }

        return new StoredAttachment(
                target,
                sanitizeFilename(originalName),
                written
        );

    } catch (IOException | RuntimeException error) {
        Files.deleteIfExists(target);
        throw error;
    }
}
~~~

`stagingRoot`, `maxFileBytes`, `StoredAttachment`, `sanitizeFilename` và `AttachmentTooLargeException` thuộc implementation ứng dụng, không phải API tự có của Spring. Caller phải quản lý vòng đời `source` và bảo đảm target thuộc thư mục riêng có permission/space quota phù hợp.

Các nguyên tắc:

- Không chỉ tin `Content-Length` do client gửi.
- Enforce limit trong quá trình đọc.
- Không dùng filename client làm path trực tiếp.
- Cleanup khi thất bại.
- Kiểm tra quyền và loại file theo policy.
- Nếu job phải sống qua restart, promote từ staging sang durable storage trước khi báo accepted.

### ZIP bomb và content validation

Một file ZIP nhỏ có thể nở thành lượng dữ liệu cực lớn khi ứng dụng giải nén. Nếu workflow tự mở archive trước khi gửi, cần giới hạn tổng byte giải nén, số entry, độ sâu thư mục và tài nguyên xử lý. Filename extension không chứng minh nội dung thực sự là PDF/PNG/ZIP.

## 21. Quản lý attachment storage theo retry

Một outbox job có thể chỉ chứa:

~~~json
{
  "mailJobId": "job-123",
  "purpose": "REPORT_READY",
  "recipientContactId": "contact-77",
  "attachmentStorageKey": "reports/tenant-42/report-981",
  "attachmentBytes": 5242880,
  "status": "RETRY"
}
~~~

Không nhét PDF Base64 vào outbox payload. Cơ sở dữ liệu chỉ nên giữ metadata và reference khi phù hợp.

Cần làm rõ:

- Storage object thuộc tenant nào.
- Ai được phép tải hoặc gửi file.
- Có immutable version/checksum để tránh thay nội dung giữa các retry không.
- Worker replica nào có quyền đọc.
- Thời điểm cleanup theo job final status và TTL.
- Xử lý khi storage object mất hoặc không đọc được.
- Cách tránh orphaned attachments khi transaction tạo job rollback.

### Không coi local Path là durable reference

Nếu job được tạo ở pod A nhưng worker xử lý tại pod B, một đường dẫn local có thể vô nghĩa. Với outbox bền vững, storage key phải resolve được trong hạ tầng phù hợp và có lifecycle độc lập với request.

## 22. Executor queue capacity không phải memory capacity

Ví dụ:

~~~java
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
~~~

Các số là ví dụ. `queueCapacity=100` giới hạn **số task đang chờ**, không giới hạn tổng byte dữ liệu mà chúng giữ.

Nếu queue chứa 100 command có `byte[]` 20 MiB, dữ liệu raw có thể xấp xỉ 2.000 MiB. Nếu queue chứa 100 ID và storage key, mức memory khác biệt rất lớn.

### Rejection policy không tự bảo đảm độ trễ

Khi queue đầy, executor có thể reject task. Nếu dùng `CallerRunsPolicy`, task có thể chạy ngay trên caller thread và khiến HTTP request phải chờ SMTP. Cần xác định saturation behavior rõ, không chỉ tăng queue vô hạn.

Với thông báo quan trọng, persisted outbox/job và bounded worker thường phù hợp hơn queue in-memory chứa file bytes.

## 23. Đo và giới hạn tổng memory in-flight

Một mô hình gần đúng:

\[
M_{\mathrm{peak}} \approx
M_{\mathrm{base}}
+ M_{\mathrm{queued}}
+ M_{\mathrm{active}}
+ M_{\mathrm{other}}
\]

Trong đó:

- `M_base`: heap ứng dụng khi chưa gửi email.
- `M_queued`: payload/references đang chờ.
- `M_active`: MIME, encoder, buffers và object của worker đang gửi.
- `M_other`: request, cache và thành phần ứng dụng khác.

Công thức mang tính định hướng. Không bao gồm đầy đủ native/direct memory, thread stacks, file cache hoặc mọi transient allocation.

Nếu 6 worker có thể giữ trung bình 30 MiB object liên quan mỗi lần gửi, riêng active work khoảng 180 MiB. Nếu queue đồng thời giữ 300 file byte arrays 5 MiB, queued raw bytes thêm khoảng 1.500 MiB.

**Giảm payload giữ trong queue thường hữu ích hơn việc tăng heap liên tục.**

### Weighted memory budget

Có thể thiết kế một permit gate:

~~~text
Mail worker resource budget: 256 MiB
Job A expected memory: 32 MiB
Job B expected memory: 64 MiB
Job C expected memory: 16 MiB
~~~

Chỉ dispatch công việc khi tổng resource estimate còn trong budget. Đây là policy ứng dụng, không phải tính năng mặc định của `JavaMailSender`. Estimate phải có headroom vì raw file size không phải peak heap.

## 24. Heap không phải tài nguyên duy nhất

| Tài nguyên | Nguồn tiêu thụ | Triệu chứng |
| --- | --- | --- |
| Java heap | `byte[]`, strings, MIME objects, queue | GC pause, `OutOfMemoryError` |
| Disk tạm | Multipart staging, generated reports | Lỗi hết chỗ, không tạo file |
| File descriptors | File streams, sockets | Không mở thêm resource |
| Threads | Blocking SMTP send | Pool đầy, request chậm |
| Network | Upload, tải object, SMTP transfer | Timeout, throughput giảm |
| CPU | Render report, MIME encoding | Latency tăng |
| Native/direct memory | TLS/socket buffers | Áp lực bộ nhớ process |

Tăng `-Xmx` không giải quyết hard size limit của provider, disk cạn, socket leak hoặc network chậm. Không dùng `OutOfMemoryError` làm cơ chế từ chối file quá lớn; JVM có thể đã mất ổn định.

## 25. Backpressure khi tốc độ sinh mail vượt tốc độ gửi

Giả sử hệ thống tạo 200 mail jobs/phút nhưng provider và network chỉ xử lý được 30/phút:

~~~text
Producer: 200 jobs/phút
Consumer: 30 jobs/phút
Backlog tăng: 170 jobs/phút
~~~

Nếu mỗi job giữ dữ liệu file lớn trong RAM, heap tăng nhanh. Nếu outbox chỉ giữ storage key, heap đỡ nguy hiểm nhưng database/object store vẫn tăng.

Cần kết hợp:

- Bounded queues.
- Worker concurrency limit.
- Rate/quota limiter theo provider.
- Size limit trước enqueue.
- Backpressure/admission control.
- Retry schedule bền vững.
- TTL và cleanup.
- Tách lane cho mail nhỏ/nhạy cảm với report lớn.

Nếu HTTP API trả `202 Accepted`, phải xác định ý định gửi đã được **lưu bền vững** hay chỉ nằm trong executor RAM. Không tuyên bố durable acceptance khi task chưa được persisted.

## 26. Message quá lớn: lựa chọn xử lý

~~~mermaid
flowchart TD
    A["Mail command"] --> B["Kiểm tra file/count/body"]
    B --> C{"Vượt raw policy?"}
    C -->|"Có"| D["Từ chối / link tải"]
    C -->|"Không"| E["Ước tính MIME + headroom"]
    E --> F{"Vượt message budget?"}
    F -->|"Có"| D
    F -->|"Không"| G["Dựng MIME và gửi"]
    G --> H{"SMTP result"}
    H -->|"Accepted"| I["Ghi submission thành công"]
    H -->|"Hard size reject"| J["Dừng retry cùng payload"]
    H -->|"Temporary"| K["Retry theo policy"]
~~~

Các lựa chọn:

1. Từ chối yêu cầu đính kèm quá lớn với lỗi rõ.
2. Cho phép người dùng giảm kích thước hoặc số file.
3. Tối ưu report/ảnh khi không làm sai dữ liệu nghiệp vụ.
4. Gửi **link tải được bảo vệ** thay vì attachment.
5. Dùng dịch vụ truyền file chuyên dụng nếu đó là yêu cầu chính.

Không cắt byte thô của PDF/XLSX để “vừa” giới hạn; file có thể hỏng. Không tự động chia một file thành nhiều email nếu sản phẩm chưa có cơ chế ghép, mã hóa và theo dõi phù hợp.

## 27. Gửi link tải thay attachment

Email có thể thông báo:

~~~text
Báo cáo của bạn đã sẵn sàng.
Vui lòng đăng nhập để tải tại:
https://app.example.org/reports/{reportId}
~~~

Đường dẫn chỉ minh họa. Lợi ích:

- Giảm MIME size.
- Tránh tải toàn file vào mail worker.
- Cho phép kiểm soát quyền và thời hạn.
- Có thể thu hồi hoặc thay đổi quyền truy cập.
- Giảm tỷ lệ size rejection.

Đổi lại phải bảo vệ URL:

- Authentication/authorization theo tenant và user.
- Không để ID dễ đoán tự cấp quyền tải.
- Nếu dùng signed URL, scope và TTL đủ hẹp.
- Không gửi token dài hạn.
- Có file retention và audit.
- Kiểm tra content type và nội dung khi tải.

Đừng giải quyết memory bằng cách đưa file nhạy cảm lên một public URL không giới hạn quyền.

## 28. Inline images và HTML Base64 cũng tiêu thụ dung lượng

Một hình ảnh inline bằng CID:

~~~html
<img src="cid:brandLogo" alt="Logo">
~~~

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Ảnh trở thành MIME part riêng và được tính vào total message. `helper.setText(...)` trước khi thêm inline resource là cách thực hành phù hợp với hướng dẫn sử dụng `MimeMessageHelper`.

Nhúng data URI trực tiếp vào HTML:

~~~html
<img src="data:image/png;base64,...">
~~~

có thể làm HTML String rất lớn, khiến bộ nhớ và transfer size tăng; mail client có thể chặn hoặc xử lý không nhất quán. Không tự coi data URI là giải pháp tối ưu vì không thấy attachment riêng.

Remote image URL không làm MIME body chứa toàn bộ bytes ảnh, nhưng có rủi ro riêng về privacy, tracking và việc mail client không tải ảnh.

## 29. Tạo report PDF hoặc Excel theo stream

Một report generator có thể trả:

~~~java
byte[] pdf =
        reportService.generatePdf(reportId);
~~~

Nếu sau đó thêm `Arrays.copyOf`, Base64 String và ByteArrayResource, có thể có nhiều bản sao lớn của file.

Khi thư viện hỗ trợ, có thể ghi thẳng vào managed file/output stream:

~~~java
try (OutputStream out =
        Files.newOutputStream(reportPath)) {

    reportService.writePdf(
            reportId,
            out
    );
}
~~~

Sau khi file được lưu bền vững và kiểm tra policy, worker có thể dùng resource đọc lại được. Tuy nhiên, không phải thư viện tạo PDF/Excel nào cũng streaming hoàn toàn: có thư viện vẫn giữ document model lớn trong RAM. Cần đo peak heap thực tế và xem API đang dùng, không chỉ tin tên method.

Compression không phải giải pháp mặc định: PDF, JPEG, PNG và XLSX có thể đã được nén; nén lại giảm ít nhưng tăng CPU, đôi khi gây vấn đề quét malware và khả năng mở của người nhận.

## 30. Đảm bảo attachment không đổi qua retry

Giả sử một outbox job gửi report ở attempt đầu, rồi retry sau một giờ. Nếu storage key trỏ tới file mutable, nội dung có thể thay đổi giữa hai lần gửi dù job ID không đổi.

Với email giao dịch quan trọng, nên dùng:

- Immutable object version.
- Checksum/hash của file.
- Metadata về raw bytes và content type.
- Idempotency key của ý định gửi.
- Retention đảm bảo file còn tồn tại qua retry.

Đừng để retry gửi một tài liệu khác rồi vẫn ghi log như cùng một message logic. Nếu nghiệp vụ yêu cầu gửi bản mới, tạo ý định gửi/version mới có chủ đích.

## 31. Monitoring size và bộ nhớ

| Metric | Câu hỏi |
| --- | --- |
| `mail_attachment_raw_bytes` | File gốc lớn bao nhiêu? |
| `mail_attachment_count` | Có bao nhiêu MIME attachments? |
| `mail_estimated_mime_bytes` | Message dự kiến lớn thế nào? |
| `mail_size_rejected_total` | Bao nhiêu request bị policy chặn? |
| `mail_provider_size_rejected_total` | Bao nhiêu SMTP size rejects? |
| `mail_active_send_count` | Có bao nhiêu send đang chạy? |
| `mail_worker_queue_size` | Bao nhiêu task còn chờ? |
| `mail_oldest_pending_age_seconds` | Backlog cũ nhất bao lâu? |
| `jvm_memory_used_bytes` | Heap/memory đang dùng? |
| `mail_temp_storage_bytes` | Disk staging đã dùng bao nhiêu? |
| `mail_send_duration_seconds` | SMTP send chậm đến mức nào? |

Có thể thêm label theo purpose, account và size bucket. Không đưa recipient address, attachment filename hoặc full storage key vào metric label vì dễ lộ dữ liệu và tạo cardinality lớn.

### Cần cảnh báo khi

- Size rejections tăng.
- GC pause/heap tăng cùng bulk email.
- Temporary storage gần đầy.
- SMTP write timeout tăng với mail lớn.
- File attachment orphaned quá TTL.
- Worker queue age của security email tăng.
- Provider thay đổi giới hạn dẫn tới thất bại hàng loạt.

SMTP submission thành công không có nghĩa thư đã vào inbox; một receiving MX có thể từ chối về sau. Cần bounce/delivery tracking nếu nghiệp vụ yêu cầu.

## 32. Kiểm thử chính sách size

Một unit test có thể dùng metadata, không cần tạo file thật nhiều MiB:

~~~java
@Test
void rejectsLargeAttachment() {
    MailSizePolicy policy =
            new MailSizePolicy();

    List<MailSizePolicy.AttachmentMeta> files =
            List.of(
                    new MailSizePolicy.AttachmentMeta(
                            "reports/job-1",
                            "large.pdf",
                            9L * 1024 * 1024
                    )
            );

    assertThrows(
            MailSizeException.class,
            () -> policy.requireAllowed(
                    files,
                    1024L
            )
    );
}
~~~

Nên bao phủ:

- File 0 byte.
- File vừa đúng ngưỡng.
- File vượt 1 byte.
- Nhiều file có tổng vượt ngưỡng.
- Số part vượt giới hạn.
- HTML/plain body quá dài.
- Các giá trị âm, không hợp lệ và overflow.
- Headroom sát tổng MIME budget.
- Inline attachment được tính đúng.

Test policy không cần khởi động SMTP relay.

## 33. Kiểm thử MIME và SMTP rejection

### Unit/component test

Dùng `MimeMessage` thật và mock `JavaMailSender` để xem MIME structure, charset, subject/recipient và attachment metadata. Với fixture nhỏ, có thể serialize để đếm size như đã trình bày.

### SMTP integration test

Sử dụng GreenMail/Mailpit/test server có khả năng mô phỏng size rejection hoặc provider sandbox được kiểm soát. Test cần xác nhận:

- Message nhỏ được chấp nhận.
- Message vượt limit bị từ chối.
- Error classifier nhận đúng nhóm size failure.
- Worker không retry hard rejection vô hạn.
- Job chuyển trạng thái cần can thiệp hoặc đổi payload.
- File source/stream được đóng và cleanup đúng.

Không giả định SMTP test server nào cũng mô phỏng provider quota/size mặc định; có thể phải cấu hình hoặc dùng fake transport để đưa ra response có kiểm soát.

### Load test

Với dữ liệu giả, thử nhiều job có attachment lớn và đo:

- Peak heap/GC.
- Active send concurrency.
- Temporary disk.
- Open descriptors.
- SMTP latency/timeouts.
- Queue depth và oldest job age.

Nếu queue chỉ giữ storage key, heap không nên tăng tuyến tính theo tổng raw attachment bytes của mọi job đang chờ như cách queue giữ `byte[]`.

## 34. Những lỗi triển khai thường gặp

### 34.1. Coi raw file bytes bằng MIME bytes

Base64, CRLF, header và MIME boundary làm tổng message lớn hơn file gốc.

### 34.2. Tin rằng JavaMailSender tự enforce hard size limit

Ứng dụng cần policy và vẫn xử lý provider rejection.

### 34.3. Dùng MultipartFile.getBytes cho mọi file

Nó tạo byte array trong heap. Với file lớn/nhiều request, đây là áp lực đáng kể.

### 34.4. Đặt byte[] trong task @Async hoặc outbox payload

Queue giữ toàn bộ dữ liệu, gây tăng heap/database size. Dùng storage key.

### 34.5. Tự Base64 encode rồi đưa String vào MimeMessage

Có thể tạo copy lớn, double encoding và sai transfer semantics.

### 34.6. Dùng InputStreamResource với stream đã mở sẵn

Không bảo đảm đọc lại được khi Jakarta Mail cần stream nhiều lần.

### 34.7. Xóa HTTP temp file ngay sau khi schedule worker

Worker có thể chưa đọc file. Cần managed storage/lifecycle đúng.

### 34.8. Đo MIME bằng ByteArrayOutputStream cho mọi production message

Tạo một bản serialized copy trong RAM và tăng CPU/I/O.

### 34.9. Chỉ tăng Xmx khi worker chậm

Không giải quyết SMTP size, disk full, network hoặc unlimited queue.

### 34.10. QueueCapacity được coi là tổng memory budget

Task count không nói mỗi task giữ bao nhiêu byte.

### 34.11. Retry permanent size rejection

Cùng payload sẽ tiếp tục quá lớn. Cần giảm size/đổi phương án.

### 34.12. Nhầm HTTP multipart limit với SMTP limit

Hai tầng độc lập, và server-generated files không chịu HTTP multipart parser.

### 34.13. Chỉ giới hạn số file mà không giới hạn total bytes

Nhiều file lớn cộng lại vượt provider size.

### 34.14. Chỉ giới hạn total bytes mà không giới hạn số file

Hàng nghìn part nhỏ vẫn tạo metadata overhead lớn.

### 34.15. Dùng FileSystemResource nhưng không kiểm soát path/permission

Có thể đọc nhầm file, path traversal, file mất hoặc bị đổi.

### 34.16. Coi SMTP SIZE là bảo đảm nhận thư

SIZE advertisement không bảo đảm mọi relay/recipient downstream chấp nhận.

### 34.17. Ghi attachment bytes vào log

Có nguy cơ lộ dữ liệu và làm log storage đầy. Chỉ log metadata tối thiểu.

### 34.18. Cho nhiều báo cáo lớn chiếm toàn bộ worker

Email reset password/transactional có thể bị chậm. Cần bounded concurrency và ưu tiên.

## 35. Tình huống thực hành

**Tình huống A — SMTP provider giới hạn tổng message 20 MiB.** Có nên gửi file PDF gốc 15 MiB không?

Không nên mặc định. Base64 với CRLF đã xấp xỉ 20,53 MiB, chưa tính MIME metadata/body.

**Tình huống B — API upload 8 MiB pass nhưng SMTP từ chối size.** Tại sao?

HTTP multipart limit kiểm soát upload gốc; MIME serialization làm kích thước lớn hơn.

**Tình huống C — 500 queued @Async jobs, mỗi job có byte[] 12 MiB.** Rủi ro?

Có thể giữ khoảng 6.000 MiB raw byte arrays trong heap. Dùng storage key và bounded queue.

**Tình huống D — FileSystemResource báo file không tìm thấy.** Vì sao?

Temp file đã bị xóa, path sai, file không có ở replica khác hoặc permission không hợp lệ.

**Tình huống E — Attachment chỉ gửi được lần đầu, retry lỗi stream.** Nguyên nhân?

InputStreamSource không tạo stream mới; stream cũ đã consume/đóng.

**Tình huống F — Provider báo hard size rejection.** Có nên retry y nguyên?

Không. Cần giảm nội dung, đổi thành link tải hoặc đánh dấu job không retryable.

**Tình huống G — Không có attachment nhưng HTML chứa ảnh Base64 lớn.** Có tính vào message size không?

Có. Data URI phình to HTML và MIME body.

**Tình huống H — 8 workers nhỏ nhưng heap vẫn cạn.** Cần kiểm tra gì?

Queue có thể giữ nhiều byte arrays, ngoài các object và buffers của active workers.

**Tình huống I — Outbox retry ở pod khác, attachment nằm trong /tmp pod trước.** Kết quả?

File có thể không tồn tại. Cần durable shared/object storage.

**Tình huống J — Gửi qua relay thành công nhưng người nhận không thấy file.** Có thể do đâu?

Receiving MX có size/policy thấp hơn và bounce về sau; SMTP accepted chưa phải delivered.

## 36. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Mail request"] --> B["Authorization + recipient policy"]
    B --> C["Kiểm tra file/count/size"]
    C --> D["Lưu attachment trong managed storage"]
    D --> E["Job chỉ giữ storage key"]
    E --> F["Bounded mail worker"]
    F --> G["Ước lượng MIME + headroom"]
    G --> H{"Trong budget?"}
    H -->|"Không"| I["Từ chối / link tải"]
    H -->|"Có"| J["Mở stream có thể đọc lại"]
    J --> K["MimeMessageHelper"]
    K --> L["JavaMailSender"]
    L --> M{"SMTP result"}
    M -->|"Accepted"| N["Mark submitted"]
    M -->|"Hard size rejection"| O["Không retry cùng payload"]
    M -->|"Transient / unknown"| P["Retry / đối soát"]
    N --> Q["Cleanup theo retention"]
    O --> Q
    P --> F
~~~

Những nguyên tắc cốt lõi:

1. **Attachment raw size khác MIME message size.** Base64 thường tăng khoảng một phần ba, còn CRLF/header/HTML cộng thêm.
2. **Không có một SMTP size limit áp dụng cho mọi provider hoặc mailbox.** Đặt policy nội bộ có headroom.
3. **`JavaMailSender` và `MimeMessageHelper` không phải hệ thống kiểm soát memory/size tự động.**
4. **Kiểm tra per-file, total bytes, số attachment, HTML và estimated MIME** trước khi gửi.
5. **Phân biệt wire bytes với heap bytes.** Một file có thể bị giữ nhiều bản sao trong RAM.
6. **Tránh đưa byte[] lớn vào async queue/outbox**; dùng ID và storage reference.
7. **Nguồn attachment phải đọc lại được và tồn tại đủ lâu** qua send/retry.
8. **HTTP upload limit không phải SMTP limit** và không bảo vệ file tạo từ backend.
9. **Đếm MIME bằng ByteArrayOutputStream chỉ phù hợp payload nhỏ/test**, tránh hot path message lớn.
10. **Giới hạn queue, in-flight memory và concurrency**, không chỉ tăng heap.
11. **Hard size rejection không nên retry vô hạn cùng payload**; cân nhắc gửi link tải có quyền.
12. **Theo dõi heap, GC, disk, MIME size, timeouts và queue age** trong vận hành.
13. **SMTP accepted khác delivered**; downstream có thể từ chối vì size/policy.

Trong Spring Framework Mail, hiệu năng của email có attachment phụ thuộc cả **kích thước trên đường gửi** và **cách ứng dụng giữ dữ liệu trong bộ nhớ**. Một pipeline tốt phải từ chối hoặc đổi phương án cho message quá lớn, đọc attachment từ nguồn phù hợp, giữ payload nhỏ trong queue và quản lý storage/worker với giới hạn rõ ràng. Nhờ đó, một vài report nặng không làm cạn heap, nghẽn SMTP hoặc ảnh hưởng đến các email quan trọng của toàn hệ thống.
