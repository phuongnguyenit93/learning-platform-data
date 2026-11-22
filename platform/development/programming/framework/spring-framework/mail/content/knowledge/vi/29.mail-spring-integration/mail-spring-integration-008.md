# Lọc thư trước khi đưa vào flow

Khi dùng **Spring Integration Mail** để nhận email, ứng dụng không nhất thiết muốn xử lý mọi thư trong mailbox. Hộp thư hỗ trợ khách hàng có thể chứa ticket hợp lệ, phản hồi tự động, newsletter, thông báo lỗi phát thư, thư chưa đúng định dạng, message đã xử lý ở lần polling trước hoặc tệp đính kèm không được phép. Nếu tất cả email đều đi thẳng vào một handler nghiệp vụ, hệ thống dễ tạo ticket không mong muốn, xử lý trùng hóa đơn, làm đầy queue hoặc tải những attachment rất lớn mà không có giá trị.

**Lọc thư trước khi đưa vào flow** là quyết định thư nào đủ điều kiện để đi từ mailbox tới pipeline, và quyết định đó cần được thực hiện ở đúng ranh giới. Trong Spring Integration Mail có các lớp khác nhau:

1. **Mailbox/server-side:** chọn folder và dùng IMAP SearchTerm để thu hẹp những message được fetch.
2. **Receiver/intake:** kiểm tra metadata, kích thước, trạng thái UID, idempotency và eligibility trước khi tạo business job.
3. **Trong IntegrationFlow:** dùng các bước `filter`, `route`, `transform` để điều phối message đã được inbound adapter phát vào flow.
4. **Business validation:** xác minh đối tác, tenant, recipient, token, quyền và nội dung không đáng tin.

Bốn lớp này bổ sung cho nhau chứ không thay thế nhau. Lọc theo subject ngay tại IMAP server có thể giảm số thư phải fetch, nhưng không chứng minh người gửi là đối tác được ủy quyền. Lọc theo `.filter(...)` ở sau inbound adapter có thể chặn downstream handler, nhưng email đã được receiver lấy từ mailbox.

~~~mermaid
flowchart TD
    A["Mailbox / folder"] --> B["IMAP SearchTerm"]
    B --> C["Mail receiver"]
    C --> D["Metadata + size limits"]
    D --> E["UID / idempotency gate"]
    E --> F{"Eligible?"}
    F -->|"No"| G["Skip / quarantine / retry"]
    F -->|"Yes"| H["Durable intake record"]
    H --> I["IntegrationFlow"]
    I --> J["Business validation"]
    J --> K["Business job"]
~~~

Bài này trình bày các cách lọc thư, ví dụ Java DSL, IMAP/POP3, cờ `Seen`, UID, an toàn MIME/attachment, nhiều tenant, xử lý lỗi, monitoring và kiểm thử.

## 1. Những email nào cần được lọc?

Giả sử mailbox có các thư:

~~~text
INBOX
  [Ticket] Khách hàng báo lỗi đăng nhập
  Re: [Ticket] Khách hàng bổ sung log
  Auto-Reply: Out of office
  Delivery Status Notification
  Newsletter từ nhà cung cấp
  [Invoice] Hóa đơn từ đối tác
  Email chứa attachment 100 MiB
  Email đã ingest ở poll trước
~~~

Một ứng dụng ticket chỉ nên chuyển những message phù hợp vào luồng tạo/cập nhật ticket. Một ứng dụng invoice có thể cần một mailbox, folder hoặc route khác.

Nếu không lọc:

- Auto-reply có thể kích hoạt vòng trả lời tự động.
- Thư rác có thể tạo ticket.
- Message được poll lại có thể tạo business record trùng.
- File không liên quan vẫn bị tải và parse.
- Header `From` giả mạo có thể được tin nhầm.
- Một mailbox nhiều tenant có thể dẫn đến sai tuyến dữ liệu.
- Xóa thư quá sớm khiến dữ liệu chưa được persist bị mất.

Nhưng **lọc sai cũng nguy hiểm**. Nếu chỉ đọc `UNSEEN`, nhân viên mở thư trước poller có thể làm thư không còn được ứng dụng nhận. Vì vậy, tiêu chí lọc cần có cơ chế kiểm chứng, audit và phục hồi.

## 2. Message source và inbound channel adapter

Trong Spring Integration Mail:

| Thành phần | Trách nhiệm |
| --- | --- |
| `ImapMailReceiver` | Tìm và nhận email qua IMAP |
| `Pop3MailReceiver` | Nhận email qua POP3 |
| `MailReceivingMessageSource` | Cung cấp email theo giao diện message source |
| Poller | Gọi source theo lịch |
| Inbound channel adapter | Phát dữ liệu từ source vào Spring Integration channel |
| Message channel | Chuyển message tới endpoint |
| `.filter(...)` | Cho phép hoặc loại message ở vị trí trong flow |
| Service activator | Thực hiện một handler |
| Error handling | Điều phối lỗi từ flow/endpoint |

Hai vị trí cần phân biệt:

~~~text
Mailbox
  -> folder selection
  -> IMAP server search
  -> mail receiver
  -> message source
  -> inbound adapter
  --- RANH GIỚI VÀO FLOW ---
  -> integration filter
  -> transformer/router
  -> business handler
~~~

**Lọc ở receiver** giúp giảm tập candidate từ server. **Lọc trong flow** giúp điều phối payload sau khi đã nhận. Nếu yêu cầu của sản phẩm là tiết kiệm băng thông và tránh fetch email lớn, chỉ viết DSL `.filter(...)` không đủ.

## 3. Các tầng lọc nên áp dụng theo chi phí

| Tầng | Điều kiện | Lợi ích | Điều không bảo đảm |
| --- | --- | --- | --- |
| Mailbox/folder | `INBOX/Invoices` | Thu hẹp tập thư | Thư không bị phân loại nhầm |
| IMAP search | Flag, subject, ngày | Server lọc candidate | Người gửi là đáng tin |
| Lightweight metadata | From, To, MIME headers | Bỏ nhanh email không liên quan | Header đã được xác thực |
| Size policy | Giới hạn byte/part | Giảm rủi ro cạn tài nguyên | File an toàn |
| UID gate | Đã ingest hay chưa | Ngăn xử lý lặp | Business side effect exactly once |
| MIME/content validation | Attachment, body schema | Xác định dữ liệu hợp lệ | Người gửi có quyền |
| Business authorization | Tenant, ticket, invoice | Bảo vệ side effect | Mail transport luôn thành công |

Ưu tiên điều kiện rẻ ở trước, điều kiện đắt sau, nhưng không hy sinh tính an toàn. Một filter chưa đủ dữ liệu nên chọn **quarantine/review** thay vì xóa thư không thể khôi phục.

## 4. Khác biệt IMAP và POP3

| Khả năng | IMAP/IMAPS | POP3/POP3S |
| --- | --- | --- |
| Folder | Có nhiều folder | Mô hình hộp thư đơn giản hơn |
| Server-side SEARCH | Có | Không có IMAP SEARCH tương đương |
| Flag `\Seen` | Có | Không có cùng semantics |
| Message UID | UID theo folder + UIDVALIDITY | UIDL theo semantics của POP3 server |
| Chuyển folder/mark | Có thể thực hiện | Hạn chế |
| Loại thư trước fetch body | Có thể tìm theo metadata | Thường hạn chế hơn |

Nếu use case cần tìm thư chưa đọc trong một folder riêng mà không tải tất cả, IMAP thường phù hợp. Với POP3, ứng dụng có thể phải lấy danh sách, xem metadata và lọc ở client theo khả năng server.

Không tự giả định provider hỗ trợ mọi IMAP extension, user flag hay cách search Unicode giống nhau. Cũng không lấy một message index trong POP3 làm định danh bền vững.

## 5. IMAP SearchTerm

Jakarta Mail cung cấp các loại `SearchTerm` trong package `jakarta.mail.search`:

- `FlagTerm`: lọc flag đã bật/tắt.
- `SubjectTerm`: tìm chuỗi trong subject.
- `FromStringTerm`: tìm chuỗi trong From.
- `RecipientStringTerm`: tìm recipient.
- `ReceivedDateTerm` hoặc `SentDateTerm`: tìm theo thời gian.
- `AndTerm`, `OrTerm`, `NotTerm`: kết hợp điều kiện.

Ví dụ logic:

~~~text
UNSEEN
AND subject contains "[Invoice]"
AND receivedDate >= lowerBound
~~~

Khi receiver dùng SearchTerm với IMAP, server có thể giảm số message phải fetch. Nhưng cần nhớ:

- SearchTerm chỉ tìm **candidate**.
- Subject và From có thể bị giả mạo.
- Server có thể xử lý search theo quy tắc riêng.
- Ngày nhận không phải cursor duy nhất đáng tin.
- Điều kiện yêu cầu parse PDF hoặc scan virus không thể được làm hoàn toàn bằng IMAP SEARCH.

## 6. Lọc theo cờ chưa đọc

Ví dụ một term tìm thư chưa mang flag `SEEN`:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.search.FlagTerm;
import jakarta.mail.search.SearchTerm;

SearchTerm unseen =
        new FlagTerm(
                new Flags(Flags.Flag.SEEN),
                false
        );
~~~

Kết hợp với subject:

~~~java
import jakarta.mail.search.AndTerm;
import jakarta.mail.search.SubjectTerm;

SearchTerm term =
        new AndTerm(
                unseen,
                new SubjectTerm("[Invoice]")
        );
~~~

Đây là cách biểu diễn điều kiện bằng Jakarta Mail API. Nhưng **UNSEEN không đồng nghĩa chưa được business xử lý**:

- Người dùng có thể mở email trước poller.
- Receiver có thể không tự đánh dấu đã đọc.
- Email đã persist nhưng acknowledgment thất bại.
- Một ứng dụng khác dùng chung mailbox thay đổi flags.

Nếu cần ngăn mất email, phải có durable ingestion state và một chính sách reconcile, không chỉ tin flag.

## 7. SearchTermStrategy trong ImapMailReceiver

Spring Integration Mail có cơ chế tùy biến chiến lược tạo search term cho IMAP receiver. Một ví dụ cách cấu hình:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Folder;
import jakarta.mail.search.AndTerm;
import jakarta.mail.search.FlagTerm;
import jakarta.mail.search.SearchTerm;
import jakarta.mail.search.SubjectTerm;

import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.SearchTermStrategy;

public ImapMailReceiver createReceiver(
        String mailUrl) {

    ImapMailReceiver receiver =
            new ImapMailReceiver(mailUrl);

    receiver.setSearchTermStrategy(
            new SearchTermStrategy() {

                @Override
                public SearchTerm generateSearchTerm(
                        Flags supportedFlags,
                        Folder folder) {

                    SearchTerm unseen =
                            new FlagTerm(
                                    new Flags(
                                            Flags.Flag.SEEN
                                    ),
                                    false
                            );

                    return new AndTerm(
                            unseen,
                            new SubjectTerm("[Invoice]")
                    );
                }
            }
    );

    receiver.setShouldDeleteMessages(false);
    receiver.setShouldMarkMessagesAsRead(false);

    return receiver;
}
~~~

Đây là ví dụ của **candidate selection trước flow**. API và overload cần phù hợp phiên bản Spring Integration đang dùng. Khi tùy biến search strategy, cần hiểu default search semantics của phiên bản receiver để tránh vô tình bỏ các điều kiện chống lấy lại mail cũ.

`supportedFlags` và `folder` có thể dùng để quyết định điều kiện dựa trên khả năng server/folder. Không nên giả định user-defined flags được mọi server hỗ trợ.

## 8. Lọc subject: hữu ích nhưng dễ bỏ sót

Ví dụ:

~~~java
SearchTerm invoiceTerm =
        new SubjectTerm("[Invoice]");
~~~

Những subject có thể gặp:

~~~text
[Invoice] INV-981
Re: [Invoice] INV-981
Fwd: [Invoice] INV-981
Hóa đơn tháng 11
Invoice INV-981
~~~

Rule chỉ match một prefix cụ thể có thể bỏ qua email hợp lệ khi đối tác thay đổi format, người dùng forward hoặc thêm câu trả lời.

Nếu một đối tác có contract gửi tự động, hãy ưu tiên một **identifier có cấu trúc và được xác minh**, recipient alias hoặc file schema thay vì chỉ dựa vào text subject. Với trường hợp không chắc, có thể chuyển mail sang review thay vì delete.

### Subject không cấp quyền

Người gửi bất kỳ có thể viết `[Ticket-123]`. Không tự động sửa ticket 123 nếu chưa xác minh token/identity và quyền truy cập đúng tenant.

## 9. Lọc theo From

Ví dụ:

~~~java
import jakarta.mail.search.FromStringTerm;

SearchTerm fromPartner =
        new FromStringTerm(
                "invoices@partner.example"
        );
~~~

Đây là heuristic cho candidate. **Header From không phải bằng chứng xác thực**. Nó có thể bị người gửi giả mạo. Nếu nghiệp vụ cần tin cậy nguồn, phải dùng cơ chế có thẩm quyền: thông tin xác thực do provider cung cấp, chữ ký/token của đối tác hoặc một giao thức/boundary đáng tin, kết hợp authorization.

Không dùng phép kiểm:

~~~java
fromAddress.endsWith("partner.example")
~~~

để khẳng định domain hợp lệ. Địa chỉ với domain gần giống có thể qua mặt kiểu so suffix. Phải parse địa chỉ, canonicalize domain và đối chiếu identity được phép. Dù domain đúng, chưa chắc người gửi có quyền ra lệnh nghiệp vụ.

## 10. Recipient và alias routing

Một inbox có thể nhận email gửi tới:

~~~text
support+ticket-123@platform.example
invoice+tenant-a@platform.example
reply@platform.example
~~~

Recipient alias có thể giúp phân loại thư. Nhưng header `To` không nhất thiết là địa chỉ SMTP envelope recipient:

- Một email Bcc có thể không liệt kê alias trong To.
- Forwarding có thể thay đổi recipient.
- Một email có nhiều To/Cc.
- Sender có thể tự điền header không đúng envelope.
- Provider có thể rewrite thông tin.

Nếu muốn tách tenant trước flow, ưu tiên **trusted delivery metadata** hoặc token/alias được platform quản lý. Không chỉ lấy một chuỗi tenant ID từ subject/To rồi cho quyền cập nhật dữ liệu tenant đó.

## 11. Chọn folder trước khi tìm thư

IMAP hỗ trợ mailbox folders:

~~~text
INBOX
INBOX/Support
INBOX/Invoices
INBOX/Notifications
INBOX/Processed
~~~

Một receiver chỉ quét `INBOX/Invoices` có thể giảm traffic so với quét mọi thư. Nhưng folder có thể bị người dùng di chuyển, provider thay spam filter hoặc administrator đổi rule.

Cần có chính sách:

1. Ai được phép thay đổi folder routing?
2. Những thư không nằm trong folder đang poll sẽ được xử lý ra sao?
3. Có reconciliation khi mailbox filter lỗi không?
4. Nếu folder bị xóa/rename, có alert hay fail closed?
5. Có nên archive message sau durable ingestion không?

Folder là kỹ thuật **phân vùng dữ liệu**, không phải bằng chứng business validation.

## 12. Lọc theo ngày nhận

Ví dụ:

~~~java
import java.util.Date;

import jakarta.mail.search.ComparisonTerm;
import jakarta.mail.search.ReceivedDateTerm;

Date lowerBound = /* ngày theo policy */;

SearchTerm since =
        new ReceivedDateTerm(
                ComparisonTerm.GE,
                lowerBound
        );
~~~

Một search window giúp tránh quét lịch sử lớn, nhưng không nên chỉ lưu `lastSeenTimestamp` rồi tìm mọi thư “lớn hơn”:

- Server có thể search theo độ phân giải ngày.
- Timezone/clock khác nhau.
- Nhiều email cùng timestamp.
- Thư được copy/move vào folder muộn.
- Downtime và thay đổi UIDVALIDITY.

Có thể quét chồng lấn một khoảng theo nhu cầu và dùng UID idempotency để bỏ duplicate. Nếu dùng UID watermark, phải gắn với UIDVALIDITY và có resync khi namespace đổi.

## 13. Kết hợp nhiều điều kiện

Ví dụ thư chưa đọc từ một trong hai địa chỉ đối tác:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.search.AndTerm;
import jakarta.mail.search.FlagTerm;
import jakarta.mail.search.FromStringTerm;
import jakarta.mail.search.OrTerm;
import jakarta.mail.search.SearchTerm;

SearchTerm unseen =
        new FlagTerm(
                new Flags(Flags.Flag.SEEN),
                false
        );

SearchTerm partners =
        new OrTerm(
                new FromStringTerm(
                        "invoices@partner-a.example"
                ),
                new FromStringTerm(
                        "billing@partner-b.example"
                )
        );

SearchTerm candidate =
        new AndTerm(
                unseen,
                partners
        );
~~~

Không biến một cây SearchTerm quá phức tạp thành toàn bộ business policy. Search server-side nên càng dễ dự đoán càng tốt. Hãy kiểm thử Unicode, folder flags và behavior của provider thực tế trong integration test.

## 14. Lọc attachment và nội dung: giới hạn của search server

Rule:

> Chỉ chấp nhận email có file PDF hợp lệ, chữ ký hợp đồng và invoice chưa tồn tại.

không thể được thực hiện đầy đủ bằng `SubjectTerm` hoặc `FromStringTerm`.

Pipeline cần:

~~~text
Server candidate search
  -> Fetch metadata
  -> Kiểm tra size và content bounds
  -> Parse MIME
  -> Lưu attachment vào storage có quyền
  -> Malware scan/file validation
  -> Xác thực đối tác/tenant
  -> Kiểm tra invoice idempotency
  -> Business processing
~~~

IMAP search có thể giảm candidate, nhưng không hiểu nội dung PDF, business signature hay tenant ownership. Nếu provider có API lọc attachment riêng, đó là capability provider-specific, không phải mặc định của Spring Integration Mail.

## 15. Filter trong IntegrationFlow khác server-side filter

Một flow có `.filter(...)`:

~~~java
@Bean
IntegrationFlow inboundFlow(
        MailReceivingMessageSource source,
        InboundCandidatePolicy policy,
        MailIntakeService intake) {

    return IntegrationFlow
            .from(
                    source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(
                                    Duration.ofSeconds(30)
                            ).maxMessagesPerPoll(10)
                    )
            )
            .filter(
                    message -> policy.allow(message)
            )
            .handle(intake, "accept")
            .get();
}
~~~

`InboundCandidatePolicy` và `MailIntakeService` là API ứng dụng minh họa. Với các DSL version, các overload/filter/message payload type cần phù hợp.

**Bước filter này xảy ra sau inbound adapter**. Message đã được receiver đưa vào pipeline. Nó hữu ích để chặn business handler hoặc route message, nhưng không giảm số bytes đã được tải qua IMAP trước đó.

Nếu cần biết lý do loại thư, dùng discard path/audit hoặc một decision router, không chỉ trả `false` rồi làm mất thông tin.

## 16. maxMessagesPerPoll không phải size limit

~~~java
Pollers.fixedDelay(
        Duration.ofSeconds(30)
).maxMessagesPerPoll(10)
~~~

`maxMessagesPerPoll` thường giới hạn số lần/message mà poller lấy từ source trong một polling cycle. Nó **không** cam kết:

- Mỗi lần poll chỉ tải tối đa 10 MiB.
- Một MIME attachment được giới hạn kích thước.
- Receiver không fetch nhiều metadata/candidate ở một lần truy vấn.
- Toàn cluster có tối đa 10 jobs.
- Email không được lặp qua các polls.

Một message 200 MiB có thể gây rủi ro heap dù maxMessagesPerPoll bằng một. Cần size policy, giới hạn file/part, streaming và bounded concurrency riêng.

## 17. Unseen, ingested và processed là ba trạng thái

| Trạng thái | Nơi lưu | Ý nghĩa |
| --- | --- | --- |
| `\Seen` | IMAP mailbox | Đã được đánh dấu đọc |
| `\Deleted` | IMAP mailbox | Đã đánh dấu xóa |
| INGESTED | Intake DB | Đã lưu email bền vững |
| FILTERED_OUT | Intake DB/audit | Đã loại theo một rule |
| PROCESSING | Business DB | Đang xử lý |
| PROCESSED | Business DB | Nghiệp vụ hoàn tất |
| RETRY | Job store | Cần xử lý lại |
| QUARANTINED | Storage/DB | Cần cách ly hoặc review |

Một lỗi nguy hiểm:

~~~text
Receiver fetch email
  -> mark Seen hoặc delete
  -> database insert thất bại
  -> lần poll sau chỉ search unseen
  -> email bị bỏ qua
~~~

Hãy tránh acknowledgment loại khỏi search trước khi **đã persist dữ liệu cần thiết**. Nếu ack thất bại sau persist, poll lại và dedupe thường là đường phục hồi mong muốn.

## 18. Cấu hình đánh dấu và xóa trong receiver

Các option hay gặp:

~~~java
receiver.setShouldMarkMessagesAsRead(false);
receiver.setShouldDeleteMessages(false);
~~~

Chúng là lựa chọn có ý nghĩa nghiệp vụ: tránh việc fetch email được xem là đã xử lý hoặc bị xóa quá sớm. Tuy nhiên, nếu không mark read và vẫn tìm Unseen, receiver có thể đưa lại cùng một email ở nhiều lần poll.

Không khắc phục duplicate bằng cách bật delete trước khi lưu database. Hãy xây durable ingestion state cùng chính sách acknowledgment:

~~~text
Discover candidate
  -> Extract identity + permitted content
  -> Persist unique inbox record + job
  -> Commit
  -> Mark/move/ack theo policy
~~~

IMAP và database không nằm trong cùng một giao dịch ACID tự động.

## 19. Idempotency: UID, UIDVALIDITY và mailbox namespace

Một IMAP message không nên được định danh bằng message sequence number vì thứ tự trong folder có thể đổi khi expunge.

**UID** chỉ có nghĩa trong một folder với **UIDVALIDITY** cụ thể. Một khóa inbound tốt:

~~~text
mailboxAccountId
  + folderId
  + uidValidity
  + uid
~~~

~~~java
public record ImapMailKey(
        String mailboxAccountId,
        String folderId,
        long uidValidity,
        long uid) {
}
~~~

Header `Message-ID` hữu ích cho tracing nhưng có thể thiếu/trùng/giả mạo. Nó không thay thế mailbox UID key. Nếu server đổi UIDVALIDITY, namespace mới phải được xem xét lại, không dùng “last UID” cũ một cách mù quáng.

### Hai lớp idempotency

1. **Ingestion:** cùng UID trong cùng namespace chỉ được tạo một inbound record.
2. **Business:** một yêu cầu nghiệp vụ chỉ gây side effect theo contract, ngay cả khi worker retry hoặc hai email khác nhau mô tả cùng yêu cầu.

Không có một thao tác filter duy nhất tự bảo đảm exactly-once end-to-end.

## 20. Database unique constraint quan trọng

Một schema minh họa:

~~~sql
CREATE TABLE inbound_mail (
    id BIGINT PRIMARY KEY,
    mailbox_account_id VARCHAR(128) NOT NULL,
    folder_id VARCHAR(256) NOT NULL,
    uid_validity BIGINT NOT NULL,
    uid BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    first_seen_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_mail_uid UNIQUE (
        mailbox_account_id,
        folder_id,
        uid_validity,
        uid
    )
);
~~~

Đây là schema đơn giản hóa, không đại diện mọi database/dialect. Một test nên xác minh unique constraint thật.

Không chỉ dùng:

~~~java
if (!repository.existsByKey(key)) {
    repository.insert(key);
}
~~~

vì hai thread có thể cùng đọc “chưa tồn tại”. Database unique constraint và cách xử lý duplicate-key result mới là ranh giới chống race.

## 21. Khi nào được đưa message vào business flow?

Một kiến trúc thường dùng:

~~~mermaid
flowchart TD
    A["IMAP candidate"] --> B["Resolve UID + metadata"]
    B --> C["Size/security preflight"]
    C --> D["Persist intake unique key"]
    D --> E["Persist raw content/attachment reference"]
    E --> F["Commit"]
    F --> G["Ack/move mailbox"]
    F --> H["Durable processing queue"]
    H --> I["Business validation"]
    I --> J["Idempotent handler"]
~~~

Tầng intake nên nhanh và có giới hạn tài nguyên, còn nghiệp vụ nặng như OCR, gọi API bên thứ ba hoặc tạo ticket có thể chạy sau từ queue bền vững.

Đừng giữ một `MimeMessage` gắn với IMAP folder/session trong job tồn tại nhiều giờ. Khi folder đóng, lazy content/attachment có thể không đọc lại được. Persist phần content cần thiết trước khi tách khỏi receiver.

## 22. Filter decision không chỉ là boolean

Một predicate trả `true/false` phù hợp với flow đơn giản, nhưng hệ thống thực tế thường cần biết **vì sao** email bị loại.

~~~java
public enum InboundDecisionType {
    ACCEPT,
    SKIP_ALREADY_INGESTED,
    REJECT_PERMANENT,
    RETRY_LATER,
    QUARANTINE
}
~~~

~~~java
public record InboundDecision(
        InboundDecisionType type,
        String reasonCode) {
}
~~~

Ví dụ:

| Decision | Ví dụ | Hành động |
| --- | --- | --- |
| ACCEPT | Hóa đơn đúng format | Persist và enqueue |
| SKIP_ALREADY_INGESTED | UID đã tồn tại | Không tạo job mới, retry ack khi cần |
| REJECT_PERMANENT | Format không nằm trong hợp đồng | Audit/retention theo policy |
| RETRY_LATER | DB hoặc validation service tạm lỗi | Giữ cơ hội đọc lại |
| QUARANTINE | MIME hỏng, file đáng ngờ | Cách ly, review và hạn chế truy cập |

Không nên quy mọi trường hợp `filter=false` thành xóa email. Một DB outage khác hoàn toàn với newsletter gửi nhầm.

## 23. Lọc email tự động và tránh vòng lặp

Một ứng dụng tự gửi email xác nhận có thể nhận phản hồi auto-generated:

~~~text
Application -> gửi acknowledgment
Remote system -> auto-reply
Application -> nhận auto-reply và gửi acknowledgment khác
...
~~~

Một số tín hiệu có thể dùng:

- Header `Auto-Submitted`.
- Delivery Status Notification / bounce content type.
- Header provider-specific.
- Return-path/bounce identity do hệ thống nhận xác minh.
- Rule về recipient và purpose.

Không chỉ search subject `Out of office` vì nội dung/ngôn ngữ rất đa dạng. Thư tự động không nên kích hoạt auto-reply khác trừ trường hợp đã có policy cụ thể. Rate limit và dedupe vẫn cần thiết để ngăn loop nếu metadata bị làm giả.

## 24. Mailbox dùng chung nhiều tenant

Ví dụ:

~~~text
tenant-a+ticket-981@inbound.platform.example
tenant-b+invoice-172@inbound.platform.example
~~~

Một mailbox nhận email cho nhiều tenant phải có **trusted mapping**:

- Recipient envelope hoặc delivery metadata đáng tin cậy.
- Alias/token do platform phát hành.
- Domain/tenant ownership được xác minh.
- Business object nằm đúng tenant.
- Attachment storage key có quyền tương ứng.

Header `To`, `From` và subject đều có thể bị sender đặt hoặc thay đổi khi forwarding. Không dùng chúng làm bằng chứng duy nhất để cập nhật dữ liệu tenant.

Nếu dùng mailbox riêng mỗi tenant, vẫn cần kiểm soát số poller, secret/credential, connection quota, idempotency namespace và khả năng thu hồi account.

## 25. Nhiều instance polling cùng mailbox

~~~text
Pod A -> IMAP search -> UID 123
Pod B -> IMAP search -> UID 123
Pod A -> insert inbox record
Pod B -> insert inbox record
~~~

IMAP không tự chia thư cho nhiều consumer như consumer group. Seen flag không phải distributed lock.

Có thể:

- Chỉ cho một active poller cho mỗi mailbox.
- Distributed lease/leader election.
- Partition mailbox theo worker.
- Unique constraint chống duplicate ingestion.
- Business idempotency cho side effect.
- Reconcile sau crash và lease expiration.

Lease nên có owner, TTL và cơ chế tránh worker cũ ghi sau khi quyền đã chuyển. Một boolean trong memory không phối hợp được nhiều JVM.

## 26. Xử lý lỗi khi filter và acknowledgment

| Điểm lỗi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| IMAP search timeout | Không thấy candidate | Backoff/retry poll |
| Authentication failure | Không đọc được inbox | Refresh credential/alert |
| MIME parse failure | Poison message | Quarantine/reason code |
| Attachment over limit | Heap/disk pressure | Chặn có giới hạn |
| DB insert failure | Không persist được | Không mark/delete |
| Ack failure sau commit | Thư bị fetch lại | Dedupe và retry ack |
| User flag thay đổi | Search bỏ sót | Reconciliation |
| UIDVALIDITY đổi | Cursor không hợp lệ | Resync namespace |
| Rule thay đổi | False negative | Audit và rollback |
| Business validation tạm lỗi | Không hoàn tất | Retry business job |
| Tenant mismatch | Cross-tenant risk | Reject và security audit |

Spring Integration có error channel và error handlers, nhưng error được đưa vào channel **không tự rollback cờ IMAP hoặc transaction database**. Cần xác định side effect nào đã xảy ra và có thể retry bước nào.

## 27. Hiệu năng và backpressure

Nếu inbox nhận 500 mail/phút và business processor xử lý được 100/phút, polling nhanh hơn không làm throughput nghiệp vụ tăng.

Cần:

- Poll interval phù hợp.
- Giới hạn số candidate/batch.
- Kiểm soát số kết nối IMAP.
- Bounded intake/worker concurrency.
- Size limit và attachment streaming.
- Durable queue thay cho giữ MIME objects trong RAM.
- Rate limit theo mailbox/provider.
- Điều tiết khi storage/database gần đầy.
- Monitoring độ tuổi email chưa xử lý.

Một email 100 MiB có thể gây vấn đề dù `maxMessagesPerPoll=1`. Phải phân biệt task count với byte/data budget.

## 28. Monitoring và khả năng giải thích filter

| Metric | Mục đích |
| --- | --- |
| `mail_inbound_poll_total` | Số lần poll |
| `mail_inbound_search_candidates_total` | Số candidate server trả |
| `mail_inbound_fetched_total` | Số message fetch |
| `mail_inbound_accepted_total` | Số được nhận vào intake |
| `mail_inbound_filtered_total` | Số bị loại theo reason |
| `mail_inbound_duplicate_total` | UID đã tồn tại |
| `mail_inbound_quarantined_total` | Số được cách ly |
| `mail_inbound_ack_failure_total` | Ack/move thất bại |
| `mail_inbound_search_duration_seconds` | Search latency |
| `mail_inbound_backlog_age_seconds` | Thời gian chờ xử lý |
| `mail_inbound_resync_total` | Số lần rescan |
| `mail_inbound_lease_conflict_total` | Tranh chấp poller |

Label nên dùng mailbox ID nội bộ, protocol, rule ID và reason code. Không đưa địa chỉ email, subject, Message-ID thô hoặc tên attachment làm label metric vì dễ lộ PII và tạo cardinality lớn.

Alert khi:

- Tỷ lệ filtered tăng đột biến.
- Số candidate giảm bất thường sau deploy.
- Không successful poll vượt SLA.
- Duplicate hoặc quarantine tăng.
- UIDVALIDITY thay đổi mà không resync.
- DB lỗi nhưng mailbox flags vẫn bị thay đổi.
- Thư hợp lệ bị kẹt ngoài folder được poll.
- Backlog tăng và processing latency vượt SLA.

## 29. Thay đổi filter an toàn

Một SearchTerm quá chặt có thể khiến email hợp lệ không còn được ứng dụng phát hiện. Quy trình rollout:

1. Xác định mục tiêu rule: giảm spam, giảm traffic hay validation?
2. Tách metadata heuristic và authorization.
3. Ghi rule ID/version trong ingestion audit.
4. Test trên các fixture hợp lệ và không hợp lệ.
5. Nếu có thể, chạy **shadow evaluation**: ghi nhận quyết định mới nhưng chưa loại thật.
6. Theo dõi candidate/accepted/filtered ratios.
7. Rollout theo mailbox hoặc tenant.
8. Giữ rollback path.
9. Không xóa ngay mail bị loại khi chưa tự tin.
10. Có replay/reconciliation theo policy.

Một log scoped:

~~~text
mailboxId: mailbox-17
uidNamespace: 381
uid: 1062
ruleVersion: 8
decision: QUARANTINE
reasonCode: UNEXPECTED_ATTACHMENT_TYPE
~~~

Không log raw body, token hoặc attachment. Lưu rule version giúp giải thích tại sao một email bị loại tại thời điểm đó.

## 30. Kiểm thử search strategy

Có thể unit test một `SearchTerm` trên `MimeMessage` nhỏ:

~~~java
@Test
void matchesExpectedInvoiceSubject()
        throws Exception {

    MimeMessage message =
            new MimeMessage(
                    Session.getInstance(
                            new Properties()
                    )
            );

    message.setSubject(
            "[Invoice] INV-981",
            "UTF-8"
    );

    SearchTerm term =
            new SubjectTerm("[Invoice]");

    assertTrue(term.match(message));
}
~~~

Các import thường dùng:

~~~java
import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.search.SearchTerm;
import jakarta.mail.search.SubjectTerm;
~~~

Test local của `SearchTerm.match` không bảo đảm server IMAP thực sẽ search Unicode/flags/date y hệt. Cần thêm integration test với server phù hợp khi dùng server-side behavior.

## 31. Kiểm thử filter policy

Ví dụ DTO metadata:

~~~java
public record InboundMailMetadata(
        String mailboxAccountId,
        String folderId,
        String senderAddress,
        String subject,
        long declaredSizeBytes,
        String messageIdHeader) {
}
~~~

Một test quyết định:

~~~java
@Test
void quarantinesOversizedCandidate() {

    InboundMailMetadata candidate =
            new InboundMailMetadata(
                    "account-a",
                    "INBOX",
                    "sender@example.test",
                    "[Invoice] INV-981",
                    50L * 1024 * 1024,
                    "test@example.test"
            );

    InboundDecision decision =
            policy.evaluate(candidate);

    assertEquals(
            InboundDecisionType.QUARANTINE,
            decision.type()
    );
}
~~~

`policy` là component ứng dụng do test tạo. `declaredSizeBytes` là metadata sơ bộ; cần enforce giới hạn bytes thực đọc để không bị lừa bởi thông tin sai.

Các test khác: ACCEPT, duplicate UID, unknown partner, malformed MIME, temporary DB failure và tenant mismatch.

## 32. Integration test với IMAP test server

Một integration test có thể dùng GreenMail hoặc IMAP server thử nghiệm:

~~~text
IMAP test server
  -> seed mail hợp lệ và không hợp lệ
  -> ImapMailReceiver + SearchTermStrategy
  -> polling inbound adapter
  -> intake service + repository
  -> assertions theo UID/correlation
~~~

Các bước:

1. Khởi tạo mailbox test cô lập.
2. Seed một email subject hợp lệ.
3. Seed một email không match.
4. Trigger poll có kiểm soát.
5. Xác nhận candidate phù hợp được ingest.
6. Poll lần hai để kiểm tra duplicate.
7. Mô phỏng DB lỗi và xác nhận không ack mất thư.
8. Kiểm tra Seen flag và UIDVALIDITY.
9. Cleanup server/fixtures thuộc test.

Không dùng inbox production trong automated tests, vì test có thể thay cờ đọc, xóa thư thật hoặc lộ credential.

Với polling async, không dùng `Thread.sleep` cố định. Có thể đợi theo điều kiện bằng Awaitility khi đã thêm dependency test:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            assertTrue(
                    inboundRepository.existsByCorrelationId(
                            correlationId
                    )
            );
        });
~~~

Đây là test helper/repository method minh họa; message ID phải scoped theo test hiện tại.

## 33. Ma trận tình huống

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Inbox trống | Không có business job |
| Subject hợp lệ | Candidate đi vào intake theo policy |
| Subject không match | Không xử lý; reason/retention rõ |
| Header From giả mạo | Không cấp quyền nghiệp vụ |
| Thư đã Seen | Hành vi theo search/reconcile policy |
| Poll lại cùng UID | Không duplicate side effect |
| UIDVALIDITY đổi | Resync namespace |
| Hai replica poll cùng UID | Unique constraint/lease bảo vệ |
| DB lỗi trước commit | Không mark/delete mất thư |
| Ack lỗi sau commit | Poll lại dedupe |
| MIME malformed | Quarantine, không chặn toàn inbox |
| Attachment quá lớn | Không OOM |
| Auto-reply | Không tạo mail loop |
| Tenant alias sai | Không cập nhật tenant khác |
| POP3 không hỗ trợ IMAP SEARCH | Lọc phía client theo capability |
| Thay filter rule | Có audit, rollout và rollback |
| Test chạy song song | Không dùng shared inbox làm nguồn assertion |

**Điểm kiểm chứng:** filter sau adapter có thể chặn downstream nhưng vẫn fetch message. Để xác nhận server-side filter, phải quan sát hành vi search/receiver trong môi trường IMAP tương ứng.

## 34. Những lỗi thường gặp

### 34.1. Gọi IntegrationFlow.filter là server-side filtering

Sai: nó chạy trong flow, sau inbound adapter. Muốn giảm candidate trước fetch cần folder/receiver search.

### 34.2. Chỉ dùng Unseen để chống duplicate

Seen do client khác thay đổi và không phải business acknowledgment. Dùng UID/idempotency.

### 34.3. Xóa email khi filter=false

Có thể xóa mail hợp lệ. Cần decision type, reason và retention policy.

### 34.4. Mark Seen trước DB commit

DB lỗi có thể khiến thư bị bỏ sót ở poll sau.

### 34.5. Dùng Message-ID làm khóa duy nhất

Header có thể thiếu, trùng hoặc bị làm giả. Dùng mailbox UID namespace.

### 34.6. Dùng IMAP message sequence number làm cursor

Sequence có thể thay đổi khi expunge. Dùng UID cùng UIDVALIDITY.

### 34.7. Tin From hoặc subject là authorization

Sender có thể giả metadata. Business policy phải xác minh riêng.

### 34.8. Lọc PDF bằng filename và Content-Type

Đó là metadata không tin cậy. Cần kiểm tra nội dung/scan.

### 34.9. Dùng maxMessagesPerPoll làm memory cap

Một mail rất lớn vẫn có thể làm cạn heap. Cần giới hạn bytes/parts.

### 34.10. Search theo ngày không overlap

Thư đến muộn/trùng ngày có thể bị bỏ qua. Kết hợp rescan và idempotency.

### 34.11. Nhiều pod poll không có unique constraint

Có thể double ingest hoặc tạo job trùng.

### 34.12. Không kiểm tra default search semantics khi custom SearchTermStrategy

Có thể vô tình lấy thư cũ hoặc bỏ thư cần thiết.

### 34.13. Giữ MimeMessage sống trong job dài

IMAP folder/session có thể đóng. Persist dữ liệu cần thiết.

### 34.14. Filter mọi auto-reply chỉ bằng subject

Language/provider khác nhau. Dùng nhiều tín hiệu và loop protection.

### 34.15. Không quan sát số thư bị filter

Có thể âm thầm bỏ nhiều email hợp lệ sau khi đổi rule.

### 34.16. Dùng To header để tách tenant không có xác minh

Forward/Bcc/spoofing có thể gây cross-tenant routing. Cần trusted mapping.

### 34.17. Coi lỗi DB là reject vĩnh viễn

DB outage cần retry, không nên xóa thư.

### 34.18. Dùng inbox production để integration test

Có thể thay flags/delete thư thật. Dùng test server/mailbox riêng.

## 35. Câu hỏi thực hành

**Câu 1.** Muốn giảm số thư IMAP server fetch, nên đặt rule ở đâu?

Folder selection và SearchTermStrategy ở receiver, theo khả năng server.

**Câu 2.** `IntegrationFlow.filter` có làm email không được fetch từ IMAP không?

Không. Nó chỉ chặn đường đi downstream ở vị trí trong flow.

**Câu 3.** Thư Unseen có chắc chưa được business xử lý?

Không. Đây là flag mailbox, không phải trạng thái intake DB.

**Câu 4.** Subject chứa `[Invoice]` có nghĩa là hóa đơn hợp lệ?

Không. Cần xác minh partner, nội dung, tenant và business authorization.

**Câu 5.** Có nên dùng FromStringTerm như kiểm tra danh tính chắc chắn?

Không. From header có thể bị giả mạo.

**Câu 6.** DB đã lưu mail nhưng IMAP mark Seen thất bại, poll lại thì làm gì?

Dùng UID unique key để dedupe, có thể retry ack.

**Câu 7.** UID 100 ở hai UIDVALIDITY khác nhau có chắc cùng một mail không?

Không. UID chỉ có ý nghĩa trong namespace hiện tại.

**Câu 8.** Hai worker cùng poll một thư có tự được IMAP chia việc không?

Không mặc định. Cần lease và/hoặc unique constraint.

**Câu 9.** Attachment quá lớn có thể được kiểm tra hoàn toàn bằng SubjectTerm không?

Không. Cần size limits và parsing/streaming có kiểm soát.

**Câu 10.** Thư reject do DB tạm thời lỗi có nên delete không?

Không. Cần retry, không loại mất dữ liệu.

**Câu 11.** POP3 có hỗ trợ IMAP SEARCH y hệt không?

Không. Phải thiết kế filtering theo capability POP3.

**Câu 12.** Header To luôn cho biết tenant thật của email không?

Không, nhất là với Bcc/forwarding. Cần trusted mapping.

**Câu 13.** Rule mới làm accepted mail giảm 90%. Cần làm gì?

Xem candidate/filtered metrics, reason codes, server behavior, false negatives và rollback/reconciliation.

**Câu 14.** Tại sao không đẩy live MimeMessage vào queue vài giờ?

Vì folder/session có thể đóng và dữ liệu lazy không còn truy cập được.

**Câu 15.** Filter false và quarantine có giống nhau không?

Không. Quarantine là một quyết định có lý do, quyền truy cập và retention; false đơn thuần không mô tả đủ hành động.

## 36. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Mailbox / folder"] --> B["IMAP SearchTerm"]
    B --> C["Receiver / fetch"]
    C --> D["UID + metadata + bounds"]
    D --> E{"Đã ingest?"}
    E -->|"Có"| F["Dedupe / ack policy"]
    E -->|"Chưa"| G["Candidate policy"]
    G --> H{"Decision"}
    H -->|"ACCEPT"| I["Durable intake"]
    H -->|"RETRY"| J["Giữ cơ hội đọc lại"]
    H -->|"QUARANTINE"| K["Lưu reason + cách ly"]
    H -->|"REJECT"| L["Audit + retention"]
    I --> M["Spring Integration flow"]
    M --> N["Business authorization"]
    N --> O["Idempotent processing"]
~~~

Ghi nhớ các nguyên tắc:

1. **Lọc trước adapter khác lọc trong flow**; `.filter(...)` sau adapter không tránh được chi phí fetch từ server.
2. **Server-side search chỉ chọn candidate**, không chứng minh mail an toàn hoặc hợp lệ nghiệp vụ.
3. **IMAP và POP3 có khả năng lọc khác nhau**; POP3 không có IMAP SEARCH đầy đủ.
4. **Seen không phải processed**, cần durable ingestion state.
5. **Không mark/delete trước persist** nếu điều đó khiến thư có thể bị bỏ sót.
6. **Dedupe IMAP bằng mailbox + folder + UIDVALIDITY + UID**, không chỉ Message-ID.
7. **From/To/subject là untrusted metadata**; không làm authorization bằng một search term.
8. **MIME/attachment cần size cap, parsing bounds và scanning**, không chỉ search subject.
9. **Decision cần reason và retryability**, không dùng một boolean cho mọi kết quả.
10. **Nhiều replicas cần lease/idempotency**, không xem IMAP flag là distributed lock.
11. **Search theo ngày cần rescan/overlap** vì có thể bỏ thư.
12. **Không giữ live MimeMessage trong queue dài**, nên persist dữ liệu cần thiết.
13. **Monitoring accepted/filtered/quarantine/duplicates** giúp phát hiện rule quá chặt.
14. **Thay rule nên có version, rollout và rollback**, tránh mất mail hợp lệ.
15. **Kiểm thử search, policy, database idempotency và IMAP integration ở từng ranh giới**.

Trong Spring Integration Mail, lọc thư hiệu quả không chỉ là thêm một phép `subject.contains(...)`. Ứng dụng cần đặt từng quy tắc vào đúng tầng: **IMAP search và folder để giảm candidate, intake để kiểm soát tài nguyên/idempotency, flow để điều phối dữ liệu, business layer để xác minh quyền và side effect**. Khi ranh giới này rõ ràng, hệ thống có thể bỏ qua thư không liên quan mà không đánh mất email quan trọng, đồng thời giải thích được vì sao một message được chấp nhận hoặc bị loại.
