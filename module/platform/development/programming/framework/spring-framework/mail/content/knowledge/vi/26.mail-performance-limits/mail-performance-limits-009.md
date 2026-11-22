# Tách tác vụ chuẩn bị nội dung khỏi tác vụ gửi trong Spring Framework Mail

Trong ứng dụng Spring, gửi email không chỉ là gọi `JavaMailSender.send(...)`. Trước khi một message được đưa tới SMTP relay, hệ thống có thể phải đọc dữ liệu nghiệp vụ, truy vấn template, render HTML/plain text, tạo PDF, tải ảnh từ object storage, resize ảnh, kiểm tra attachment, dựng MIME và quyết định người nhận có còn đủ điều kiện nhận thư hay không.

Nếu gom tất cả công việc đó vào một lời gọi đồng bộ trên HTTP request hoặc một worker duy nhất, các bước tiêu tốn CPU, RAM, I/O và kết nối SMTP sẽ cạnh tranh cùng tài nguyên. Một file PDF tạo chậm có thể chiếm thread gửi; ngược lại SMTP đang throttling có thể làm tồn đọng hàng nghìn tác vụ dựng nội dung. Khi request timeout hoặc process restart, ứng dụng còn có nguy cơ mất trạng thái đang xử lý hoặc gửi trùng.

**Tách tác vụ chuẩn bị nội dung khỏi tác vụ gửi** là thiết kế phân chia pipeline thành hai nhóm công việc có đặc tính tài nguyên khác nhau:

- **Preparation:** tạo và chuẩn hóa dữ liệu cần để gửi email, gồm template, plain text, HTML, tài liệu và attachment references.
- **Submission:** lấy nội dung đã chuẩn bị, dựng `MimeMessage` khi cần, thực thi chính sách gửi, gọi `JavaMailSender` và ghi nhận kết quả SMTP.

Việc tách này không có nghĩa bắt buộc phải dùng hai microservices. Một ứng dụng Spring có thể dùng hai worker pools, hai loại durable jobs hoặc hai giai đoạn của cùng outbox. Điều quan trọng là **ranh giới trách nhiệm, trạng thái bền vững, giới hạn tài nguyên và chính sách retry** phải rõ ràng.

## 1. Vì sao cần phân tách?

Hãy xét một workflow gửi hóa đơn:

~~~text
HTTP request
     |
     v
Đọc đơn hàng + khách hàng
     |
     v
Render HTML template
     |
     v
Tạo PDF hóa đơn
     |
     v
Đọc logo/ảnh và các attachment
     |
     v
Dựng MimeMessage
     |
     v
SMTP connect / TLS / AUTH / DATA
     |
     v
Ghi kết quả
     |
     v
HTTP response
~~~

Nếu thực hiện tất cả trên request thread, độ trễ cuối cùng bằng tổng thời gian từng bước. SMTP có thể bị timeout ở cuối luồng, khiến người dùng chờ lâu dù thao tác xác nhận đơn hàng đã thành công. Nếu cố retry toàn bộ workflow, hệ thống có thể dựng lại PDF và tải lại ảnh nhiều lần dù chỉ SMTP bị lỗi tạm thời.

Tách hai giai đoạn tạo ra pipeline khác:

~~~text
Business transaction
        |
        v
Durable preparation job
        |
        v
Preparation worker
   - Load snapshot/template
   - Render HTML/plain
   - Generate document
   - Persist stable artifact references
        |
        v
READY_TO_SEND
        |
        v
SMTP submission worker
   - Check eligibility and deadline
   - Build MIME from prepared artifacts
   - Apply provider rate limit
   - JavaMailSender.send(...)
        |
        v
SUBMITTED / RETRY_WAIT / FAILED / AMBIGUOUS
~~~

Khi SMTP gặp sự cố, hệ thống có thể retry bước gửi mà không phải render lại nội dung từ đầu, miễn là các dữ liệu đã chuẩn bị đủ bền vững và có thể đọc lại.

## 2. Hai nhóm công việc có đặc điểm tài nguyên khác nhau

| Thành phần | Chuẩn bị nội dung | Gửi SMTP |
| --- | --- | --- |
| Tác vụ chính | Render template, tạo PDF, xử lý ảnh, đọc storage | Connect, TLS/AUTH, chuyển MIME qua mạng |
| Tài nguyên nổi bật | CPU, RAM, disk/object storage I/O | Socket, network, SMTP quota, timeout |
| Độ trễ | Phụ thuộc kích thước tài liệu/template | Phụ thuộc relay, network, throttling |
| Lỗi phổ biến | Template sai, file không tồn tại, service tạo PDF lỗi | AUTH/TLS, 4xx/5xx, connection/read/write timeout |
| Retry | Có thể thử lại preparation hoặc sửa dữ liệu | Chỉ retry transport khi phù hợp |
| Parallelism | Theo số CPU, memory và storage capacity | Theo provider rate/concurrency |
| Output | Prepared content/manifest và references | Submission outcome và provider ID nếu có |
| Bằng chứng thành công | Artifact đã được lưu bền vững | Server/transport báo đã chấp nhận submission |
| Deadline | Thời điểm nội dung phải sẵn sàng | Thời điểm message còn giá trị gửi |

Nếu dùng cùng executor và concurrency cho mọi tác vụ, một nhóm có thể làm nghẽn nhóm còn lại. Với tách biệt, có thể tăng số preparation workers mà không đồng thời mở thêm SMTP connections, hoặc giảm SMTP send rate khi provider throttling mà không khóa việc chuẩn bị nội dung.

## 3. Ranh giới hợp lý giữa chuẩn bị và gửi

Không có một điểm cắt duy nhất cho mọi hệ thống. Có ba mức phổ biến:

| Kiểu tách | Preparation tạo gì? | Submission làm gì? | Phù hợp |
| --- | --- | --- | --- |
| **Logical separation** | Model + rendered strings trong cùng task | Dựng MIME rồi gửi ngay | Ít email, chi phí chuẩn bị nhỏ |
| **Durable prepared manifest** | Plain/HTML + attachment references ổn định | Dựng MIME ngay trước send và submit | Email quan trọng, retry, file lớn |
| **Prebuilt MIME artifact** | MIME đã serialize thành file `.eml` bền vững | Đọc MIME, cấu hình transport/envelope và gửi | Cần snapshot byte-level, pipeline chuyên biệt |

Bài này dùng **durable prepared manifest** làm ví dụ chính vì dễ tách trách nhiệm và retry. Preparation lưu dữ liệu đủ để một worker khác dựng lại message; bước SMTP không phải gọi lại các tác vụ nặng.

Cần hiểu rằng trong Jakarta Mail, một số công việc MIME và việc đọc stream attachment có thể xảy ra **khi send/serialize**, không chỉ khi gọi `MimeMessageHelper`. Do đó “đã tạo `MimeMessage`” không đồng nghĩa mọi bytes attachment đã được materialize, và việc truyền `MimeMessage` qua queue không phải một cơ chế durability tốt.

## 4. Cách làm đồng bộ đơn giản và giới hạn

Ví dụ service viết trực tiếp:

~~~java
@Service
public class InvoiceMailService {

    private final JavaMailSender sender;
    private final InvoicePdfService pdfService;
    private final InvoiceTemplateService templates;

    public InvoiceMailService(
            JavaMailSender sender,
            InvoicePdfService pdfService,
            InvoiceTemplateService templates) {
        this.sender = sender;
        this.pdfService = pdfService;
        this.templates = templates;
    }

    public void sendInvoice(UUID invoiceId) throws Exception {
        byte[] pdf = pdfService.generate(invoiceId);
        String html = templates.renderHtml(invoiceId);
        String plain = templates.renderPlain(invoiceId);

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo("customer@example.net");
        helper.setSubject("Hóa đơn của bạn");
        helper.setText(plain, html);

        helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdf),
            "application/pdf"
        );

        sender.send(message);
    }
}
~~~

Đây là ví dụ minh họa; các service chuẩn bị hóa đơn là abstraction của ứng dụng. Vấn đề không phải code “sai”, mà là:

- Method giữ thread trong lúc render PDF và chờ network.
- PDF được giữ trong RAM bằng `byte[]`.
- Lỗi SMTP có thể buộc gọi lại cả preparation.
- HTTP request có thể timeout trong khi SMTP vẫn đang xử lý.
- Không có durable state về thời điểm nội dung đã chuẩn bị xong.
- Nếu chạy trong database transaction, có nguy cơ giữ connection/lock lâu.
- Không có chính sách riêng cho concurrency của render và SMTP.

Với vài email nhỏ, cách này vẫn có thể đủ đơn giản và hợp lý. Chỉ đưa pipeline hai giai đoạn vào khi có yêu cầu độ tin cậy, throughput, isolation hoặc chi phí chuẩn bị thực sự cần thiết.

## 5. Đặt chuẩn cho hai loại dữ liệu: intent và prepared content

Một **mail intent** mô tả yêu cầu nghiệp vụ, không phải message SMTP:

~~~java
public record MailIntent(
    UUID notificationId,
    UUID businessEventId,
    String recipientId,
    String recipientAddress,
    MailCategory category,
    String templateKey,
    String templateVersion,
    Instant createdAt,
    Instant expiresAt
) {}
~~~

Ví dụ `MailCategory`:

~~~java
public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    OPERATIONAL,
    MARKETING
}
~~~

Một **prepared content manifest** mô tả kết quả đã chuẩn bị:

~~~java
public record PreparedMail(
    UUID notificationId,
    String recipientAddress,
    String senderAddress,
    String subject,
    String plainText,
    String htmlText,
    List<PreparedAttachment> attachments,
    String templateVersion,
    Instant preparedAt
) {}
~~~

~~~java
public record PreparedAttachment(
    String storageKey,
    String fileName,
    String contentType,
    long sizeBytes,
    String checksumSha256
) {}
~~~

Các records trên là DTO do ứng dụng tự thiết kế, không phải class có sẵn của Spring Mail. Bản thực tế còn có thể cần Reply-To, Cc, language, inline assets, consent snapshot, business version hoặc sensitivity classification.

**Không đưa SMTP password, OAuth token, JavaMailSender, open InputStream hoặc raw MimeMessage vào các records lưu trong queue/outbox.**

## 6. Business transaction chỉ lưu ý định gửi

Một nguyên tắc quan trọng: lưu yêu cầu gửi cùng transaction nghiệp vụ, **không** render tài liệu hoặc gọi SMTP trong transaction đó.

~~~java
@Service
public class OrderConfirmationService {

    private final OrderRepository orders;
    private final MailIntentRepository mailIntents;

    public OrderConfirmationService(
            OrderRepository orders,
            MailIntentRepository mailIntents) {
        this.orders = orders;
        this.mailIntents = mailIntents;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.getRequired(orderId);
        order.confirm();
        orders.save(order);

        mailIntents.insertIfAbsent(
            MailIntentFactory.forOrderConfirmation(order)
        );
    }
}
~~~

`MailIntentRepository` và `MailIntentFactory` là abstraction ứng dụng. `insertIfAbsent` nên dựa trên unique business idempotency key để cùng event không tạo nhiều notification.

~~~text
BEGIN TRANSACTION
    Update order state
    Insert mail intent / outbox row
COMMIT
               |
               v
        Worker thực thi sau
~~~

Không giữ transaction chứa business update trong lúc:

- Tải dữ liệu từ remote storage.
- Render PDF.
- Gọi SMTP.
- Sleep để backoff.
- Chờ rate limiter.

Nếu transaction rollback, outbox record cũng rollback, tránh gửi email cho nghiệp vụ chưa được commit.

## 7. State machine cho hai giai đoạn

Một state machine minh họa:

~~~text
PENDING_PREPARATION
         |
         v
     PREPARING
         |
         +-- success --> READY_TO_SEND
         |
         +-- transient error --> PREP_RETRY_WAIT
         |                           |
         |                           +--> PREPARING
         |
         +-- permanent error --> PREP_FAILED

READY_TO_SEND
         |
         v
       SENDING
         |
         +-- SMTP accepted --> SUBMITTED
         |
         +-- transient error --> SEND_RETRY_WAIT
         |                          |
         |                          +--> SENDING
         |
         +-- permanent error --> SEND_FAILED
         |
         +-- uncertain outcome --> AMBIGUOUS
~~~

Không cần đặt chính xác những tên enum này trong mọi dự án, nhưng phải phân biệt rõ:

- **Chuẩn bị thất bại**: chưa đủ nội dung để gửi.
- **Sẵn sàng gửi**: đã có artifact/reference bền vững.
- **Gửi thất bại**: SMTP transport gặp lỗi.
- **Gửi đã được chấp nhận**: server/transport xác nhận submission.
- **Không rõ kết quả**: có nguy cơ đã submit dù client nhận timeout.

Không dùng một flag `sent=false` cho mọi trạng thái vì operator sẽ không biết cần sửa template, chờ provider hay đối soát duplicate.

## 8. Preparation worker làm gì?

Một preparation worker điển hình:

1. Claim intent ở trạng thái `PENDING_PREPARATION` bằng lease hoặc transaction guard.
2. Đọc snapshot dữ liệu nghiệp vụ phù hợp.
3. Chọn template version, locale và nội dung cần tạo.
4. Render subject, plain text và HTML.
5. Tạo hoặc lấy attachment/inline assets nếu cần.
6. Kiểm tra format, size và kết quả scan theo policy.
7. Lưu file/tài liệu có thể đọc lại sau restart.
8. Ghi `PreparedMail` manifest và trạng thái `READY_TO_SEND`.
9. Commit status và giải phóng lease.
10. Nếu lỗi, ghi category/attempt count và lên lịch preparation retry.

Không yêu cầu preparation worker phải có SMTP credentials hoặc được phép kết nối SMTP relay. Tách quyền hạ tầng này làm giảm bề mặt rủi ro: renderer có thể cần đọc dữ liệu nghiệp vụ/storage, còn sender cần SMTP network/credential.

## 9. Ví dụ contract cho preparation

~~~java
public interface MailPreparationService {
    PreparedMail prepare(MailIntent intent);
}
~~~

~~~java
public interface PreparedMailRepository {
    void saveReady(PreparedMail prepared);
    PreparedMail getReady(UUID notificationId);
}
~~~

~~~java
public interface PreparedArtifactStore {
    String put(
        String proposedKey,
        InputStream input,
        String contentType
    ) throws IOException;

    InputStream open(String key) throws IOException;
}
~~~

Các interface là abstraction để thiết kế ranh giới; không phải API Spring Mail.

Một implementation của `MailPreparationService` có thể sử dụng template engine (Thymeleaf, FreeMarker hoặc giải pháp khác) và service tạo tài liệu. Worker chỉ gọi preparation port, không biết MIME transport.

### Không render từ một model đang thay đổi tùy tiện

Nếu worker đọc dữ liệu “mới nhất” sau vài phút, nội dung email có thể không còn phản ánh business event ban đầu. Với hóa đơn/xác nhận đơn hàng, nên xác định rõ snapshot hoặc version phù hợp ngay khi event được phát sinh.

## 10. Ví dụ preparation service tạo manifest

~~~java
@Service
public class InvoicePreparationService
        implements MailPreparationService {

    private final InvoiceSnapshotRepository invoices;
    private final InvoiceTemplateRenderer renderer;
    private final PdfGenerator pdfGenerator;
    private final PreparedArtifactStore artifacts;

    public InvoicePreparationService(
            InvoiceSnapshotRepository invoices,
            InvoiceTemplateRenderer renderer,
            PdfGenerator pdfGenerator,
            PreparedArtifactStore artifacts) {
        this.invoices = invoices;
        this.renderer = renderer;
        this.pdfGenerator = pdfGenerator;
        this.artifacts = artifacts;
    }

    @Override
    public PreparedMail prepare(MailIntent intent) {
        InvoiceSnapshot snapshot = invoices.getForEvent(
            intent.businessEventId()
        );

        RenderedMail rendered = renderer.render(
            intent.templateKey(),
            intent.templateVersion(),
            snapshot
        );

        GeneratedArtifact generated =
            pdfGenerator.generateInvoice(snapshot);

        // Store persists bytes durably and returns stable reference.
        String key;
        try (InputStream input = generated.openStream()) {
            key = artifacts.put(
                "mail/" + intent.notificationId() + "/invoice.pdf",
                input,
                "application/pdf"
            );
        } catch (IOException exception) {
            throw new MailPreparationException(
                "Cannot persist invoice artifact",
                exception
            );
        }

        PreparedAttachment attachment = new PreparedAttachment(
            key,
            "invoice.pdf",
            "application/pdf",
            generated.sizeBytes(),
            generated.sha256()
        );

        return new PreparedMail(
            intent.notificationId(),
            intent.recipientAddress(),
            "billing@example.com",
            rendered.subject(),
            rendered.plainText(),
            rendered.htmlText(),
            List.of(attachment),
            intent.templateVersion(),
            Instant.now()
        );
    }
}
~~~

`InvoiceSnapshot`, `GeneratedArtifact`, `RenderedMail`, `MailPreparationException` và các repository/renderer classes là ứng dụng tự định nghĩa. `GeneratedArtifact.openStream()` phải trả stream hợp lệ cho lần đọc đó; `PreparedArtifactStore.put` phải hoàn tất durable write trước khi trả key.

Ví dụ nêu rõ logic preparation và storage, không nhằm tạo một thư viện PDF hoàn chỉnh. Trong production, inject `Clock` để test thời gian, lưu snapshot/version nhất quán và validate artifact policy trước khi mark READY.

## 11. Không giữ dữ liệu đã chuẩn bị chỉ trong RAM

Nếu prepare xong rồi truyền `PreparedMail` chứa byte arrays lớn vào một in-memory executor queue, process crash sẽ làm mất kết quả. Nếu cố giữ nhiều attachment bytes trong heap, áp lực garbage collection và out-of-memory có thể tăng.

Một chiến lược bền vững:

~~~text
Preparation worker
   |
   +--> Render plain/HTML
   |
   +--> Persist PDF/inline assets to object storage
   |
   +--> Save manifest + artifact references in DB
   |
   v
READY_TO_SEND
   |
   v
SMTP worker reads manifest
   |
   +--> Opens fresh streams from artifact storage
   |
   +--> Constructs MIME
   |
   +--> Sends over SMTP
~~~

Với nội dung text nhỏ, lưu subject/plain/html ngay trong database có thể hợp lý. Với PDF/ảnh lớn, lưu object có key bất biến, checksum và retention policy sẽ giúp tránh phình database/outbox payload.

Không lưu temporary filesystem path của một container ephemeral rồi kỳ vọng worker trên instance khác sẽ đọc được.

## 12. Artifact phải tồn tại và đọc lại được sau restart

Một prepared reference chỉ an toàn để retry nếu:

- Artifact tồn tại trong storage được worker truy cập.
- Reference không phụ thuộc thread/process đã tạo.
- Quyền truy cập và credential storage phù hợp.
- Stream có thể mở lại nhiều lần.
- File không bị sửa âm thầm sau khi prepare.
- Artifact chưa hết hạn trong suốt retry window.
- Metadata size/checksum đủ để phát hiện sai lệch.
- Cleanup không xóa file trước khi mọi attempt kết thúc.

Với object storage, một key versioned hoặc content-addressed key giúp tránh việc một path bị ghi đè bằng nội dung mới trong khi job cũ đang chờ.

Ví dụ:

~~~text
mail-artifacts/
  tenant-42/
    notification-abc/
      invoice-v1.pdf
      inline-logo-v3.png
~~~

Tên file/key phải được tạo từ ID đã validate và phân quyền. Không ghép tùy ý path từ input người dùng, không lưu URL công khai chứa secret rồi truyền qua outbox.

## 13. DB transaction và object storage không tự atomically commit

Một hệ thống có thể dùng PostgreSQL cho manifest và object storage cho PDF. Hai hệ thống thường không tham gia cùng một ACID transaction.

Các khoảng lỗi:

~~~text
Upload PDF success
       |
       X  Process crash before DB READY
       |
       v
Artifact orphaned in storage
~~~

Hoặc:

~~~text
DB READY stored too early
       |
       X  PDF upload fails
       |
       v
Sender reads missing artifact
~~~

Một chiến lược thực tế:

1. Tạo artifact bằng key gắn với notification/version.
2. Hoàn tất upload, kiểm tra metadata/digest cần thiết.
3. Ghi manifest và `READY_TO_SEND` trong DB transaction.
4. Nếu DB commit thất bại, artifact có thể thành orphan.
5. Có cleanup/reconciler xử lý object không được manifest tham chiếu sau grace period.
6. Không công bố READY trước khi artifact đọc được.

Nếu dùng temporary key rồi promote thành final key, phải hiểu semantics atomicity của storage service. Không tự giả định rename của object storage có transaction tương tự filesystem.

## 14. Tạo MimeMessage ở giai đoạn gửi

Một phương án thuận tiện là **không truyền object `MimeMessage` qua queue**. Thay vào đó, sender nhận `PreparedMail` và dựng message mới cho mỗi SMTP attempt.

~~~java
@Service
public class PreparedMailSmtpAdapter {

    private final JavaMailSender sender;
    private final PreparedArtifactStore artifacts;

    public PreparedMailSmtpAdapter(
            JavaMailSender sender,
            PreparedArtifactStore artifacts) {
        this.sender = sender;
        this.artifacts = artifacts;
    }

    public void send(PreparedMail prepared)
            throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(prepared.senderAddress());
        helper.setTo(prepared.recipientAddress());
        helper.setSubject(prepared.subject());
        helper.setText(
            prepared.plainText(),
            prepared.htmlText()
        );

        for (PreparedAttachment attachment
                : prepared.attachments()) {

            InputStreamSource source = () ->
                artifacts.open(attachment.storageKey());

            helper.addAttachment(
                attachment.fileName(),
                source,
                attachment.contentType()
            );
        }

        message.setHeader(
            "X-App-Notification-ID",
            prepared.notificationId().toString()
        );

        sender.send(message);
    }
}
~~~

Đoạn code dùng `org.springframework.core.io.InputStreamSource`. Với `InputStreamSource`, việc gọi `getInputStream()` cần cung cấp một stream mới, có thể đọc lại. `PreparedArtifactStore.open` trong ví dụ phải thực hiện điều đó. `MimeMessageHelper.addAttachment` có overload nhận `InputStreamSource` và content type.

Đoạn code giả định manifest đã được validate và chỉ mô tả happy path. Khi chạy thật, cần xử lý missing artifact, stream I/O, phân loại lỗi SMTP và giới hạn message size. Việc send thành công chỉ là **SMTP submission**, không phải provider đã giao thư tới Inbox.

## 15. Vì sao resource stream phải repeatable?

Jakarta Mail có thể yêu cầu đọc attachment stream khi serialize message, và một số đường thực thi có thể đọc source nhiều lần. Đây là ví dụ không an toàn:

~~~java
InputStream oneShot = remoteStorage.open(key);

InputStreamSource badSource = () -> oneShot;
helper.addAttachment(
    "report.pdf",
    badSource,
    "application/pdf"
);
~~~

Tất cả lời gọi `getInputStream` trả cùng stream đã bị đọc một phần hoặc đóng. Sau lần đầu, attachment có thể rỗng, bị cắt hoặc ném exception.

Cách phù hợp:

~~~java
InputStreamSource goodSource = () ->
    remoteStorage.open(key);
~~~

Mỗi lần sẽ mở **một stream mới từ cùng artifact bất biến**. Ví dụ trong bộ nhớ cho file nhỏ:

~~~java
byte[] bytes = readSmallFixture();
InputStreamSource source = new ByteArrayResource(bytes);
~~~

`ByteArrayResource` cung cấp stream mới trên byte array đã có; nhưng giữ nhiều file lớn dưới dạng byte arrays làm tốn heap. Với file lớn, ưu tiên storage stream có thể mở lại hoặc file resource bền vững, không phải `InputStreamResource` gắn với một stream đã mở sẵn.

## 16. MimeMessage chưa chắc đã chứa sẵn toàn bộ bytes

Một ngộ nhận phổ biến là sau khi gọi:

~~~java
helper.addAttachment("invoice.pdf", source, "application/pdf");
~~~

thì toàn bộ PDF đã được copy vào `MimeMessage`. Thực tế, với các loại `DataSource`/`InputStreamSource`, nội dung có thể được đọc khi Jakarta Mail serialize/gửi.

Điều này có hai hệ quả:

1. Resource phải còn tồn tại và đọc được cho tới khi send kết thúc.
2. Một phần I/O tải attachment vẫn xảy ra trong **submission phase**, dù phần tạo tài liệu đã kết thúc ở preparation.

Nếu cần tách hoàn toàn network đọc artifact khỏi thời gian SMTP, có thể materialize tài nguyên trong bounded local staging hoặc prebuild MIME vào artifact bền vững. Nhưng cần tính thêm disk, memory và cleanup; không đánh đổi vô hạn tài nguyên chỉ để làm biểu đồ hai giai đoạn đẹp.

## 17. Prebuilt MIME artifact có phù hợp không?

Một số hệ thống muốn preparation xuất ra toàn bộ MIME `.eml` để retry cùng nội dung. Đây là lựa chọn chuyên biệt có ưu và nhược điểm.

**Ưu điểm:**

- Dữ liệu MIME được tạo một lần.
- Có thể đo byte size sau encoding.
- Dễ lưu snapshot của nội dung cuối.
- Sender có thể ít phải render hơn.

**Khó khăn:**

- Envelope recipients là metadata SMTP riêng, không chỉ header To/Cc/Bcc.
- Header Date/Message-ID có thể thay đổi khi dùng API gửi tùy implementation.
- Serialization và load lại MIME phải tương thích.
- Prebuilt MIME file có thể rất lớn.
- Đảm bảo privacy, encryption và retention khó hơn.
- Một bản raw message cũ có thể không còn hợp lệ về consent/deadline.

Nếu chọn hướng này, cần contract rõ về MIME bytes, envelope recipients, transport, queue metadata và idempotency. Không mặc định Java serialization của `MimeMessage` là cách lưu ổn định trong outbox.

Với phần lớn ứng dụng, **prepared manifest + immutable attachment references + dựng MIME tại lúc gửi** là ranh giới dễ quản lý hơn.

## 18. Kích thước email và ngân sách bộ nhớ

Dung lượng email khi gửi qua SMTP không bằng tổng kích thước file gốc. MIME headers, boundaries, content transfer encoding và Base64 có thể tăng kích thước dữ liệu.

Với Base64, phần dữ liệu ảnh/attachment nhị phân sau encoding thường tăng xấp xỉ 4/3 trước overhead dòng và MIME. Vì vậy, một file 12 MiB không đồng nghĩa email gửi qua SMTP chỉ 12 MiB.

Một preparation policy có thể kiểm tra:

- Số attachment.
- Tổng raw bytes.
- MIME encoded size ước tính.
- Kích thước HTML.
- Inline image dimensions và bytes.
- Provider max message size.
- Business-specific budget.

Nếu giới hạn chính xác phụ thuộc provider, có thể cần đo serialized MIME bằng cơ chế đếm bytes ở bước phù hợp. Không lấy `String.length()` của HTML làm kích thước UTF-8 hay SMTP bytes, vì Java String length là số UTF-16 code units.

### Không giữ tất cả attachments trong RAM

Giả sử mỗi email có PDF 8 MiB, còn 50 preparation tasks chạy đồng thời. Nếu mỗi task giữ ít nhất một `byte[]` PDF, riêng chúng đã chiếm khoảng 400 MiB, chưa tính object, template, ảnh, encoded buffers và GC overhead.

Một thiết kế tốt thường:

- Giới hạn concurrency theo memory budget.
- Stream file tới storage thay vì tích lũy hết vào heap khi có thể.
- Lưu file lớn bằng reference.
- Tránh copy byte arrays nhiều lần.
- Theo dõi heap/GC và working-set memory.
- Có per-email size cap trước khi worker SMTP thử gửi.

## 19. Worker pools riêng cho preparation và submission

Nếu hai giai đoạn có đặc tính khác nhau, không nên buộc chúng sử dụng chung executor:

~~~text
Preparation queue
       |
       v
CPU / render worker pool
       |
       v
Durable READY_TO_SEND
       |
       v
SMTP submission queue
       |
       v
Network / provider-limited worker pool
~~~

Spring có thể cấu hình hai executor cho các tác vụ bất đồng bộ ngắn trong process:

~~~java
@Configuration
@EnableAsync
public class MailExecutorsConfiguration {

    @Bean(name = "mailPreparationExecutor")
    public ThreadPoolTaskExecutor preparationExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("mail-prepare-");
        pool.initialize();
        return pool;
    }

    @Bean(name = "mailSubmissionExecutor")
    public ThreadPoolTaskExecutor submissionExecutor() {
        ThreadPoolTaskExecutor pool =
            new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(30);
        pool.setThreadNamePrefix("mail-submit-");
        pool.initialize();
        return pool;
    }
}
~~~

Các giá trị là minh họa, không phải cấu hình tối ưu mặc định. Tính toán theo CPU, memory, SMTP throughput và hạn mức provider.

**Lưu ý:** `ThreadPoolTaskExecutor` là hạ tầng chạy task trong process, không phải durable queue. Process restart có thể làm mất task đang nằm trong executor queue. Đối với email quan trọng, outbox/database hoặc broker vẫn phải là **nguồn công việc bền vững**, còn executor chỉ là tài nguyên xử lý của mỗi worker instance.

## 20. Bounded queue và backpressure

Một cấu hình nguy hiểm là producer tạo hàng nghìn tasks mỗi giây nhưng chỉ có vài sender threads, trong khi in-memory queue không giới hạn. Hậu quả:

- Heap tăng.
- GC pause dài.
- Email quan trọng bị chờ sau chiến dịch.
- Job nằm trong memory và mất khi process crash.
- Queue latency tăng nhưng SMTP vẫn có vẻ không lỗi.
- Executor overload khiến thời gian retry không dự đoán được.

Backpressure nghĩa là tầng trước biết tầng sau chưa sẵn sàng và **không tiếp tục đẩy workload vô hạn**.

Với durable outbox:

1. Poll/claim batch theo capacity thật của pool.
2. Giới hạn số jobs `PROCESSING` đang được giữ lease.
3. Khi pool đầy, không claim thêm hoặc trả job về trạng thái chờ an toàn.
4. Không drop job chỉ vì executor từ chối submit.
5. Không giữ database lock trong thời gian chờ send.
6. Khi provider throttling, giảm concurrency/rate trước khi tăng poll batch.

Tránh vô tình dùng `CallerRunsPolicy` trong HTTP request path khiến tác vụ chuẩn bị/gửi SMTP quay lại chạy đồng bộ trên request thread. Nó có thể hữu ích trong một số worker loop có chủ đích, nhưng phải hiểu tác động lên latency và transaction boundaries.

## 21. Áp dụng giới hạn riêng cho từng nhóm worker

Preparation concurrency thường bị giới hạn bởi:

- Số CPU cores và chi phí render.
- Memory cho template, PDF và ảnh.
- Tốc độ đọc object storage/database.
- Số kết nối tới các dịch vụ nội dung.
- File size và số lượng attachments.

Submission concurrency thường bị giới hạn bởi:

- SMTP provider quota.
- Số kết nối đồng thời được phép.
- Tốc độ send theo account/domain.
- Kích thước MIME và băng thông mạng.
- SMTP timeout và retry backoff.

Một ước lượng sơ bộ có thể dùng quan hệ:

~~~text
concurrency ≈ throughput × average service time
~~~

Ví dụ giả định một SMTP attempt trung bình mất 1 giây; nếu có 10 send slots đang bận, throughput lý thuyết quanh 10 attempts/giây trước khi tính quota, jitter, network và các bottlenecks khác. Đây không phải cam kết provider cho phép gửi 10 emails/giây.

Không nên tăng số threads để vượt provider rate limit. Rate limiting và concurrency phải là hai cơ chế riêng.

## 22. Scheduler claim công việc tới hạn

Một poller có thể chọn job theo status và thời gian:

~~~sql
SELECT id
FROM mail_outbox
WHERE status = 'PENDING_PREPARATION'
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT 20;
~~~

Worker preparation sẽ claim và đặt lease trong transaction ngắn rồi commit trước khi render.

Send poller:

~~~sql
SELECT id
FROM mail_outbox
WHERE status IN ('READY_TO_SEND', 'SEND_RETRY_WAIT')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY next_attempt_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT 20;
~~~

Đây là SQL PostgreSQL minh họa. Query production cần condition cho lease, tenant prioritization, deadline, suppression và các index phù hợp. Các record `PREPARING`/`SENDING` bị worker chết phải được reclaim sau khi lease hết hạn theo chính sách.

`FOR UPDATE SKIP LOCKED` giúp nhiều pollers tránh cùng claim một row đang bị transaction khác khóa. Sau claim, commit nhanh; không giữ database row lock qua network render hoặc SMTP.

## 23. Retry preparation và retry SMTP phải khác nhau

Một lỗi preparation có thể là:

- Template data tạm chưa sẵn sàng.
- Object storage tạm lỗi.
- PDF generator quá tải.
- Template key/version không tồn tại.
- Attachment không được phép.
- Dữ liệu nghiệp vụ bị lỗi định dạng.

Một lỗi SMTP có thể là:

- Connection timeout trước submission.
- SMTP relay tạm bận hoặc throttling.
- Authentication/TLS configuration error.
- Recipient rejection.
- Message size policy rejection.
- Timeout sau DATA với kết quả không rõ.

Không nên dùng một catch-all retry toàn pipeline:

~~~text
Try:
    render PDF
    build MIME
    send SMTP
On any error:
    repeat everything
~~~

Nếu SMTP lỗi sau khi PDF đã được tạo đúng, việc lặp render làm tốn CPU và có thể tạo attachment khác dữ liệu ban đầu. Nếu template invalid vĩnh viễn, retry SMTP không giúp.

Tách policy:

| Lỗi | Stage | Phản ứng thường phù hợp |
| --- | --- | --- |
| Template không tìm thấy | Prepare | PREP_FAILED, sửa cấu hình/dữ liệu |
| Storage timeout | Prepare | PREP_RETRY_WAIT, backoff |
| File quá giới hạn | Prepare | PREP_FAILED hoặc đổi cách gửi |
| SMTP 421 tạm thời | Send | SEND_RETRY_WAIT, backoff + jitter |
| SMTP auth credential sai | Send | Alert, không retry nóng |
| SMTP reject message size | Send | SEND_FAILED; cần thay content |
| Timeout sau DATA | Send | AMBIGUOUS, đối soát trước retry |

Một job phải có max attempts và business deadline riêng theo stage. Retry count của preparation không nhất thiết bằng retry count của SMTP.

## 24. Idempotency khi hai worker cùng xử lý

Có thể xảy ra:

~~~text
Worker A claims N-123
        |
        v
Worker A render PDF và upload
        |
        X  Worker A crash
        |
        v
Lease expires
        |
        v
Worker B reclaims N-123
        |
        v
Worker B render PDF lần nữa
~~~

Để hạn chế side effects trùng:

- Mỗi notification có ID ổn định.
- Artifact keys nên idempotent/versioned.
- Ghi prepared manifest theo conditional update/optimistic version.
- Worker chỉ mark READY khi còn lease/ownership hợp lệ.
- Dọn artifacts orphan hoặc trùng.
- Kiểm tra checksum/content version nếu preparation lặp.

Ở send stage còn khó hơn: SMTP relay có thể nhận message rồi worker crash trước khi ghi SUBMITTED. Một outbox không tự bảo đảm exactly-once gửi email. Cần phân biệt **job idempotency** (không enqueue trùng) với **transport idempotency** (provider có thực sự deduplicate được không).

MIME Message-ID không phải cơ chế idempotency được mọi SMTP server bảo đảm.

## 25. Đảm bảo snapshot nội dung có tính nhất quán

Giả sử khách hàng đổi địa chỉ hoặc đơn hàng được cập nhật sau khi event phát sinh.

Ba lựa chọn:

1. **Snapshot tại business event:** lưu dữ liệu cần thiết cùng intent. Hợp cho chứng từ/xác nhận có ý nghĩa tại thời điểm sự kiện.
2. **Snapshot khi preparation:** lưu snapshot/version đã dùng; nếu phải retry send, không render lại bằng dữ liệu mới.
3. **Tính lại khi send:** hợp một số thông báo cần thông tin mới nhất, nhưng có thể khiến nội dung thay đổi giữa retries.

Với email mang tính xác nhận giao dịch hoặc hóa đơn, nên xác định content version rõ và tránh gửi một phiên bản khác mỗi lần retry chỉ vì dữ liệu nguồn đã đổi.

Với email nhắc lịch có giá trị thay đổi theo thời gian, send worker nên kiểm tra trạng thái nghiệp vụ mới nhất để quyết định cancel/refresh job, chứ không gửi snapshot cũ một cách mù quáng.

### Template version cũng cần cố định

Nếu một job được tạo hôm nay, chuẩn bị sau khi template deploy phiên bản mới, cần quy định job dùng template nào. Lưu `templateKey` và `templateVersion` có thể giúp tái hiện nội dung và điều tra sai lệch.

Không coi việc đổi template là lý do render lại mọi prepared email đang chờ nếu không có một migration hoặc invalidation policy có chủ đích.

## 26. Eligibility có thể thay đổi sau khi chuẩn bị

Một marketing email được chuẩn bị lúc 09:00, nhưng người dùng unsubscribe lúc 09:30 và worker gửi lúc 11:00. Dù đã READY, việc gửi lúc 11:00 có thể không còn được phép.

Vì vậy send worker phải kiểm tra các điều kiện **còn hiệu lực tại thời điểm submit**:

- Consent/preferences và suppression.
- Business deadline/expiry.
- Recipient có còn hợp lệ không.
- Token hoặc workflow có bị thu hồi không.
- Campaign có bị pause/cancel không.
- Provider account có bị disabled/cooldown không.

~~~text
Prepared at 09:00
      |
      v
READY_TO_SEND
      |
      +-- Recipient unsubscribed at 09:30
      |
      v
Send worker at 11:00
      |
      v
Recheck eligibility
      |
      +--> CANCELLED / SUPPRESSED
~~~

Không làm ngược lại bằng cách luôn render mọi thứ lại ngay trước send; chỉ kiểm tra những state mà policy yêu cầu phải mới.

## 27. TTL và business deadline

Có email hết giá trị rất nhanh:

- OTP hoặc reset password token.
- Xác nhận thao tác yêu cầu thực hiện trong một khoảng thời gian.
- Nhắc lịch trước thời điểm sự kiện.
- Coupon hoặc khuyến mãi có ngày hết hạn.

Một job nên có `expiresAt` nếu nghiệp vụ cần. Chuẩn bị hoàn tất không bảo đảm người nhận còn nên nhận email.

Điều kiện trước submission:

~~~text
now < expiresAt
AND job is READY or SEND_RETRY_WAIT
AND recipient remains eligible
AND provider budget is available
AND prepared artifacts are readable
~~~

Nếu next retry nằm sau expiry, dừng thay vì gửi thư quá hạn. Với OTP, không tạo một token mới chỉ vì retry SMTP nếu điều đó làm hỏng flow/xác thực ban đầu.

Hạn lưu artifact nên dài ít nhất bằng retry/reconciliation window được phép, cộng khoảng an toàn cho cleanup. Không để object lifecycle rule xóa attachment khi outbox còn READY/RETRY_WAIT.

## 28. Ưu tiên transactional email khi campaign lớn

Nếu một chiến dịch marketing tạo hàng chục nghìn prepared messages, chúng có thể chiếm hết send pool và khiến OTP hoặc hóa đơn bị trễ.

Các cách tổ chức:

- Queue/batch riêng theo category.
- Rate budgets riêng cho transactional và marketing.
- Priority scheduling có tránh starvation.
- SMTP account/provider phù hợp từng loại email nếu chính sách cho phép.
- Giới hạn preparation jobs mỗi campaign.
- Capacity reservation cho email ưu tiên cao.
- Theo dõi queue age và business deadline theo category.

Không chỉ dựa vào một priority integer nếu worker luôn xử lý queue marketing rất dài. Cần thực thi phân bổ capacity thực và tránh starvation cả hai chiều.

### Không dùng cùng thread pool cho PDF và OTP send

Một tác vụ tạo PDF nặng có thể giữ CPU/heap lâu. Nếu OTP cùng executor, nó phải chờ dù SMTP đang rảnh. Tách pools cho phép OTP send dùng capacity riêng ngay cả khi preparation queue đang quá tải.

## 29. Observability của hai stage

Đo đúng các loại thời gian:

~~~text
Business event
     |
     +--> time waiting for preparation
     |
     +--> preparation duration
     |
     +--> time waiting for SMTP submission
     |
     +--> SMTP duration
     |
     +--> provider delivery delay (if available)
~~~

Các span/metric gợi ý:

| Metric hoặc span | Ý nghĩa |
| --- | --- |
| `mail.prepare.queue_wait` | Chờ để bắt đầu preparation |
| `mail.prepare.duration` | Thời gian dựng nội dung/artifacts |
| `mail.prepare.failures` | Lỗi theo preparation failure class |
| `mail.prepared_artifact.bytes` | Kích thước artifact đã lưu |
| `mail.send.queue_wait` | Thời gian READY tới lúc attempt bắt đầu |
| `mail.smtp.submit.duration` | Thời gian gọi SMTP transport |
| `mail.send.attempts` | Số lần send thực tế |
| `mail.send.retry_wait` | Thời gian dự kiến backoff |
| `mail.outbox.oldest_ready_age` | Tuổi job sẵn sàng lâu nhất |
| `mail.executor.rejected` | Executor overload |
| `mail.storage.open.failures` | Không đọc được prepared artifact |

Đây là tên ví dụ do ứng dụng tự đặt, không phải metric mặc định của Spring Mail.

Logs cần `notificationId` xuyên các stage, `attemptId` riêng cho mỗi SMTP send, `templateVersion`, category, provider, stage/outcome và timestamps. Không log raw SMTP password, recipient email dưới dạng metric tag, HTML body, file bytes hoặc reset token.

### Trace qua async boundary

HTTP request trace và outbox worker trace có thể khác nhau. Dùng stable `notificationId`, `businessEventId` hoặc span link để correlation. Không cần cố giữ HTTP span mở nhiều giờ để đợi send.

## 30. Sample structured logs

Preparation hoàn tất:

~~~json
{
  "event": "mail.preparation.completed",
  "notificationId": "N-123",
  "category": "TRANSACTIONAL",
  "templateVersion": "invoice-v2",
  "attachmentCount": 1,
  "artifactBytes": 245600,
  "preparationMs": 438,
  "status": "READY_TO_SEND"
}
~~~

Send attempt:

~~~json
{
  "event": "mail.smtp.attempt.completed",
  "notificationId": "N-123",
  "attemptId": "N-123-A2",
  "provider": "primary-smtp",
  "smtpDurationMs": 820,
  "outcome": "SUBMITTED",
  "status": "SUBMITTED"
}
~~~

Nếu không biết provider queue ID, không tạo giá trị giả. Với exception, ghi error class/code đã chuẩn hóa và correlation ID, không in raw MIME hoặc stack trace chứa dữ liệu nhạy cảm vào log dễ truy cập.

### Phân biệt accepted và delivered

Khi `JavaMailSender.send(...)` hoàn tất bình thường, ứng dụng có thể đánh dấu SUBMITTED theo hợp đồng transport. Chỉ gọi DELIVERED khi có provider delivery signal đáng tin, không phải từ việc MIME được dựng xong.

## 31. Bảo mật khi chia pipeline

Hai stages có thể cần quyền hạ tầng khác nhau:

| Quyền | Preparation worker | SMTP worker |
| --- | --- | --- |
| Đọc dữ liệu nghiệp vụ | Có, theo nhu cầu | Thường chỉ đọc prepared manifest |
| Render template/PDF | Có | Thường không |
| Ghi prepared artifacts | Có | Thường read-only |
| Đọc attachment đã chuẩn bị | Có khi tạo/kiểm tra | Có khi gửi |
| SMTP credential | Không cần | Có |
| Outbound SMTP network | Không cần | Có |
| Update job status | Chỉ trạng thái preparation | Chỉ trạng thái send |
| Access provider event API | Không nhất thiết | Theo tích hợp riêng |

Không lưu token SMTP trong prepared manifest hoặc queue payload. Cần giới hạn tenant access trên artifact storage và bảo vệ dữ liệu tại rest/transit.

Prepared HTML, PDF và recipients có thể chứa PII; có retention policy, encryption, access control và audit phù hợp. Người dùng có quyền sửa/xóa dữ liệu có thể ảnh hưởng prepared artifacts; cần thiết kế cancellation/cleanup theo yêu cầu pháp lý và nghiệp vụ.

## 32. Khi nào nên dùng @Async?

`@Async` là một công cụ tiện lợi để chạy tác vụ trên thread khác, nhưng không tự tạo một pipeline có durability.

Ví dụ đơn giản:

~~~java
@Service
public class MailPreparationTask {

    private final MailPreparationService preparation;

    public MailPreparationTask(
            MailPreparationService preparation) {
        this.preparation = preparation;
    }

    @Async("mailPreparationExecutor")
    public CompletableFuture<PreparedMail> prepare(
            MailIntent intent) {

        PreparedMail result = preparation.prepare(intent);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Điều này tách thread, nhưng:

- Task queue thường nằm trong RAM.
- Process crash có thể làm mất task.
- Spring proxy/self-invocation có thể ảnh hưởng việc `@Async` thực sự chạy.
- Exception trong async task cần được xử lý và lưu.
- Application vẫn cần trạng thái job nếu muốn retry sau restart.
- Không nên gắn một HTTP transaction dài quanh await result.

Với critical transactional mail, `@Async` có thể là executor cho worker **đã lấy job từ durable store**, chứ không phải nguồn sự thật duy nhất của mail request.

## 33. Submission worker không nên chờ dài bằng Thread.sleep

Một ví dụ không nên dùng cho durable retry:

~~~java
try {
    sender.send(message);
} catch (MailException ex) {
    Thread.sleep(60_000);
    sender.send(message);
}
~~~

Sleep giữ thread và có thể giữ DB transaction nếu được gọi sai ranh giới. Khi SMTP provider đang downtime, nhiều threads cùng sleep sẽ giảm capacity.

Thay vào đó:

~~~text
SMTP temporary error
         |
         v
Classify + compute backoff/jitter
         |
         v
Persist SEND_RETRY_WAIT + nextAttemptAt
         |
         v
Release worker thread
         |
         v
Poller resumes when due
~~~

Nếu provider yêu cầu cooldown, thời điểm retry không được sớm hơn policy đó. Cần max attempts và deadline. Với result `AMBIGUOUS` sau DATA, retry có thể tạo duplicate; phải có quyết định rõ.

## 34. Một ví dụ worker hai giai đoạn

Các orchestration classes ở đây là pseudocode gần Java để minh họa ranh giới transaction và I/O.

Preparation worker:

~~~java
public void processPreparation(UUID notificationId) {
    MailIntent intent = stateService.claimPreparation(
        notificationId
    );

    try {
        // No database transaction is held for rendering/storage I/O.
        PreparedMail prepared = preparation.prepare(intent);

        // Separate short transaction to persist manifest and READY.
        stateService.markReady(notificationId, prepared);
    } catch (TransientPreparationException ex) {
        stateService.schedulePreparationRetry(
            notificationId, ex
        );
    } catch (PermanentPreparationException ex) {
        stateService.markPreparationFailed(
            notificationId, ex
        );
    }
}
~~~

Submission worker:

~~~java
public void processSubmission(UUID notificationId) {
    PreparedMail prepared = stateService.claimReadyForSend(
        notificationId
    );

    if (!eligibility.isAllowedNow(notificationId)) {
        stateService.markSuppressed(notificationId);
        return;
    }

    try {
        // Rendering and durable artifact generation are already done.
        smtpAdapter.send(prepared);

        stateService.markSubmitted(notificationId);
    } catch (TransientSmtpException ex) {
        stateService.scheduleSendRetry(notificationId, ex);
    } catch (AmbiguousSmtpException ex) {
        stateService.markAmbiguous(notificationId, ex);
    } catch (PermanentSmtpException ex) {
        stateService.markSendFailed(notificationId, ex);
    }
}
~~~

Những class `stateService`, `eligibility`, `smtpAdapter` và exception types thuộc thiết kế ứng dụng. Lưu ý `markSubmitted` có thể thất bại sau khi server đã accepted, gây rủi ro retry trùng ở lần reclaim lease. Chính vì vậy SMTP qua outbox thường chỉ có thể đạt at-least-once attempt semantics, không mặc nhiên exactly-once delivery.

Nên triển khai state transitions bằng transaction ngắn và conditional status/version update để worker cũ không ghi đè kết quả worker mới sau khi lease hết hạn.

## 35. Các loại sự cố theo stage

| Sự cố | Preparation | Submission | Cách xử lý |
| --- | --- | --- | --- |
| Template không tồn tại | Lỗi | Chưa chạy | Mark PREP_FAILED, sửa template |
| PDF generator tạm chậm | Retry | Chưa chạy | Backoff tại prepare |
| Storage upload success, DB failed | Artifact mồ côi | Chưa chạy | Cleanup/reconciliation |
| Artifact bị xóa sau READY | Đã xong | Không đọc được | Điều tra retention, có thể reprepare |
| SMTP AUTH sai | Đã xong | Lỗi | Sửa credential, không retry nóng |
| SMTP 421 tạm thời | Đã xong | Retry | Backoff + jitter |
| SMTP size exceeded | Đã xong | Rejected | Chỉnh content; không gửi lại y nguyên |
| SMTP timeout sau DATA | Đã xong | AMBIGUOUS | Provider reconciliation/duplicate policy |
| Process crash khi PREPARING | Có thể chưa xong | Không | Reclaim lease, idempotent artifact |
| Process crash sau SMTP accepted | Đã xong | Kết quả DB chưa lưu | Rủi ro gửi trùng |
| Recipient unsubscribe trước send | Đã xong | Không nên submit | Suppress/cancel |
| Mail quá hạn | Có thể đã xong | Không nên submit | Cancel/expire |

Một failure state có thể cần reprepare khi artifact không còn hợp lệ; nhưng không để preparation retry tự ý tạo lại nội dung khác cho một email giao dịch đã chốt nếu chưa có policy.

## 36. Thử nghiệm hiệu năng và độ tin cậy

Có thể xây các lớp test:

### Unit tests

- Preparation tạo đúng plain/HTML và attachment manifest.
- Template version được cố định.
- Send worker không gọi renderer.
- Sender mở fresh stream cho từng attachment.
- Eligibility/expiry kiểm tra trước SMTP.
- State transitions và retry policy phù hợp từng stage.

### Integration tests với database và object storage

- Intent/outbox được insert cùng transaction nghiệp vụ.
- Transaction rollback không tạo send job.
- Prepared manifest/attachment đọc lại sau khi worker process khác chạy.
- Hai preparation workers không cùng sở hữu một job.
- Upload success nhưng DB commit thất bại không công bố READY.
- Worker crash/lease expiry được reclaim.
- Artifact cleanup không xóa job còn active.
- Concurrent workers không submit vượt giới hạn account.

### SMTP integration tests

Có thể dùng GreenMail hoặc SMTP capture server:

1. Prepare một email có PDF/HTML.
2. Persist manifest và attachment.
3. Gọi submission worker dùng `JavaMailSender` thật.
4. Đọc MIME server nhận được.
5. Kiểm tra subject, recipient, body, attachment filename/bytes.
6. Xác nhận outbox chuyển SUBMITTED.
7. Với transient failure, kiểm tra retry dùng cùng prepared artifact.
8. Với timeout sau DATA, xác nhận policy AMBIGUOUS.
9. Không dùng provider production hay địa chỉ thật trong CI.

### Load/performance tests

Đo riêng preparation throughput, send throughput, queue wait, heap/GC, storage read latency, SMTP duration và backlog. Tạo workload có cả email nhẹ và PDF/ảnh lớn; nếu chỉ test text mail vài KB, khó phát hiện memory pressure của production.

## 37. Các anti-pattern cần tránh

| Anti-pattern | Hệ quả | Cách làm tốt hơn |
| --- | --- | --- |
| Render PDF và gửi SMTP trong HTTP transaction | Giữ thread/DB lock lâu | Intent + worker hai giai đoạn |
| Dùng chung pool cho CPU render và SMTP I/O | Hai loại việc gây nghẽn lẫn nhau | Separate capacity |
| Mỗi SMTP retry render lại mọi nội dung | Lãng phí CPU và có thể đổi dữ liệu | Persist prepared artifact |
| Queue chứa `MimeMessage` sống trong RAM | Không durable, resource lifecycle khó | Serializable manifest + refs |
| Lưu toàn bộ PDF lớn vào DB/outbox JSON | Payload lớn, GC/DB pressure | Durable object reference |
| Lưu path temp của container | Worker khác không đọc được | Shared durable storage |
| Dùng InputStream một lần cho attachment | Attachment rỗng hoặc lỗi khi đọc lại | Repeatable stream source |
| Đánh dấu READY trước khi upload hoàn tất | Missing artifact ở send stage | Persist artifact trước, rồi READY |
| Giả định DB và object store commit atomically | Orphan hoặc missing file | Reconciler/cleanup và status ordering |
| Dùng queue executor như durable queue | Job mất khi restart | Outbox/broker |
| Queue không giới hạn | Heap overflow và latency tăng | Bounded queues/backpressure |
| Claim nhiều jobs hơn executor capacity | Lease hết hạn trước khi chạy | Claim batch theo capacity |
| Tăng SMTP threads không xem quota | Provider throttling | Rate/concurrency limit |
| Retry mọi lỗi ở cả hai stage | Storm, lặp lỗi permanent | Stage-specific classifier |
| Retry timeout sau DATA như chắc chắn chưa gửi | Duplicate email | AMBIGUOUS/reconciliation |
| Không cố định snapshot/template version | Email khác nhau giữa retries | Immutable prepared content |
| Không kiểm tra unsubscribe sau READY | Gửi mail không còn được phép | Recheck tại send |
| Xóa artifact ngay sau lần submit lỗi | Không còn file cho retry | Retention theo job lifecycle |
| Gọi SMTP accepted là delivered | Báo cáo sai | Provider delivery events riêng |
| Log raw HTML/attachment/token | Lộ dữ liệu | Structured IDs và redaction |

## 38. Lộ trình triển khai theo từng bước

Một dự án Spring có thể áp dụng theo thứ tự:

1. **Phân tích đường gửi hiện tại**: xác định thời gian render, file I/O, SMTP và request latency.
2. **Định nghĩa MailIntent** có notification ID và business event ID ổn định.
3. **Lưu intent cùng transaction nghiệp vụ** khi yêu cầu gửi cần durability.
4. **Tách MailPreparationService** khỏi SMTP transport.
5. **Thiết kế PreparedMail manifest** chứa subject/plain/HTML và immutable artifact refs.
6. **Lưu file lớn ở storage bền vững** với checksum, size, version, retention.
7. **Thêm state machine hai giai đoạn** cùng lease/conditional updates.
8. **Tạo preparation workers** với concurrency phù hợp CPU/memory.
9. **Tạo SMTP workers** với capacity/rate limit riêng.
10. **Dựng MimeMessage tại send attempt** từ manifest và repeatable streams.
11. **Áp dụng retry/backoff theo từng stage**, không render lại vô ích khi SMTP tạm lỗi.
12. **Kiểm tra eligibility/deadline trước send** dù content đã chuẩn bị.
13. **Theo dõi queue wait/processing times riêng** để phát hiện bottlenecks.
14. **Kiểm thử crash, retry, storage orphan, SMTP ambiguity và concurrency**.
15. **Bổ sung cleanup và retention** cho các artifacts không còn được job tham chiếu.

Không nhất thiết phải triển khai thành microservices ngay. Một monolith có hai worker pools và một durable outbox có thể đạt phần lớn lợi ích, miễn là job ownership và failure recovery được thiết kế rõ.

## 39. Ghi nhớ

- Preparation và SMTP submission có đặc tính tài nguyên, failure modes và retry policies khác nhau.
- Tách stage giúp render PDF/template không giữ SMTP worker, và SMTP throttling không ép render lại nội dung.
- Không gửi trực tiếp trong database transaction nghiệp vụ khi pipeline cần độ tin cậy cao.
- Outbox/queue bền vững là nguồn sự thật; `@Async` chỉ chuyển thread, không tự cung cấp durability.
- `PreparedMail` nên là manifest với text và artifact references, không phải object `MimeMessage` đang sống trong RAM.
- Attachment resource phải có thể mở stream mới cho từng lần đọc/attempt.
- MIME assembly có thể vẫn đọc attachment trong send stage; cần hiểu lazy stream behavior.
- Artifact và manifest phải được lưu theo thứ tự an toàn, có cleanup cho orphan objects.
- Snapshot và template version cần được quản lý để retry không tự ý thay đổi email.
- Recipient preferences/deadline có thể đổi sau preparation nên phải kiểm tra lại trước send.
- Separate pools, bounded queues, rate limits và backpressure giúp kiểm soát CPU, memory, SMTP quota.
- Preparation retry khác SMTP retry; không lặp cả pipeline khi chỉ network gửi lỗi.
- Timeout sau DATA có thể AMBIGUOUS; retry có nguy cơ duplicate.
- Queue wait, preparation duration, artifact I/O và SMTP duration nên đo riêng.
- SUBMITTED nghĩa relay/transport đã chấp nhận theo kết quả quan sát, không chứng minh DELIVERED.
- Worker crash/restart phải có lease recovery, idempotency và trạng thái có thể đối soát.

**Nguyên tắc cốt lõi:** Hãy để **preparation worker tạo nội dung có thể tái sử dụng và tồn tại sau restart**, còn **submission worker chịu trách nhiệm tạo MIME và giao thư qua SMTP theo quota, deadline và retry policy**. Ranh giới này giúp Spring Framework Mail xử lý email lớn hoặc nhiều email mà không để CPU render, storage I/O và network gửi thư kéo sụp lẫn nhau, đồng thời khiến sự cố dễ quan sát và khôi phục hơn.
