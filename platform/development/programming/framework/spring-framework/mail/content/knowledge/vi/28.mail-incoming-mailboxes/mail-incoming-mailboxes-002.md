# IMAP và POP3 trong các bài toán nhận thư

## 1. Nhận email là bài toán khác với gửi email

Trong hệ sinh thái **Spring Framework Mail**, phần quen thuộc nhất là **JavaMailSender**, **JavaMailSenderImpl**, **MimeMessage** và **MimeMessageHelper** để tạo, gửi email ra SMTP server. Tuy nhiên, nhiều ứng dụng Java cũng cần **nhận và xử lý email từ hộp thư**: lấy phản hồi của khách hàng, đọc hóa đơn từ đối tác, tiếp nhận đơn hàng gửi qua email, phân loại tài liệu hoặc xử lý một mailbox vận hành.

Việc gửi và nhận dùng các giao thức khác nhau:

- **SMTP**: ứng dụng gửi thông điệp tới một mail server, hoặc các mail server chuyển tiếp cho nhau.
- **IMAP (Internet Message Access Protocol)**: ứng dụng truy cập, tìm kiếm và quản lý thông điệp đang nằm trên mail server; có thư mục, trạng thái và nhiều khả năng đồng bộ.
- **POP3 (Post Office Protocol version 3)**: ứng dụng lấy thông điệp từ một mailbox theo mô hình đơn giản hơn, thường để tải nội dung về xử lý cục bộ.

Điểm quan trọng: **Spring Framework Mail chủ yếu cung cấp abstraction gửi thư**, không có một đối tượng **JavaMailReceiver** đối xứng hoàn toàn với **JavaMailSender** để tự động giải quyết mọi quy trình nhận. Để nhận email, ứng dụng thường dùng **Jakarta Mail API** trực tiếp hoặc **Spring Integration Mail** để xây inbound adapter, polling và flow xử lý.

Bài này giải thích khi nào dùng IMAP hoặc POP3, cách đọc thư trong ứng dụng Spring, thiết kế pipeline nhận thư đáng tin cậy và những vấn đề thực tế về trạng thái, trùng lặp, bảo mật, attachment, retry và hiệu năng.

## 2. Những bài toán nghiệp vụ thường dùng email inbound

| Bài toán | Nguồn email | Yêu cầu nổi bật |
|---|---|---|
| Tiếp nhận yêu cầu hỗ trợ | support@... | Đọc nội dung, người gửi, thread, attachment và tạo ticket |
| Xử lý hóa đơn/chứng từ | invoices@... | Kiểm tra tệp, chống trùng, lưu object storage và phân luồng kế toán |
| Đồng bộ mailbox nhân viên | Hộp thư cá nhân hoặc nhóm | Giữ trạng thái đọc/chưa đọc, folder, UID và đồng bộ nhiều thiết bị |
| Tiếp nhận phản hồi chiến dịch | replies@... | Ghép In-Reply-To/References với notification gốc |
| Xử lý bounce/DSN | bounces@... | Parse delivery status, correlation theo recipient/notification |
| Tự động hóa nhận đơn đặt hàng | orders@... | Xác minh nguồn, parse nội dung, xử lý idempotent |
| Lưu trữ email về kho dữ liệu | Mailbox tích hợp | Snapshot có thể truy vết và retention phù hợp |
| Di chuyển mailbox | Server cũ sang hệ thống mới | Quét số lượng lớn, checkpoint, bảo toàn metadata |

**IMAP** thường hợp với những bài toán cần thư mục, UID, flag và đồng bộ lâu dài. **POP3** phù hợp hơn với luồng đơn giản như tải thư từ một mailbox nhận độc lập rồi đưa vào hệ thống xử lý riêng, khi không cần trạng thái thư mục trên server.

Không nên lựa chọn giao thức chỉ vì IMAP có nhiều tính năng hơn. Hãy xem yêu cầu **trạng thái, mức độ đồng thời, quyền sở hữu mailbox, dung lượng, latency, cách xóa thư và chính sách nhà cung cấp**.

## 3. Kiến trúc tổng quát: từ mailbox tới nghiệp vụ

~~~text
Người gửi hoặc hệ thống bên ngoài
                 |
                 | SMTP
                 v
          Receiving mail server
                 |
           INBOX / folders
                 |
         IMAP hoặc POP3
                 |
                 v
      Spring inbound mail component
        |           |
        |        Parse MIME
        |           |
        v           v
       Validation + Security checks
                 |
                 v
       Dedup / Inbox persistence
                 |
                 v
         Queue / Event pipeline
                 |
                 v
          Business processors
        |         |          |
      Ticket    Invoice     Bounce
                 |
                 v
        State / attachment storage
~~~

Một pipeline tốt nên tách **lấy thư** khỏi **thực hiện nghiệp vụ**. Nếu mỗi lần đọc IMAP đều chạy OCR, gọi API bên ngoài, ghi database, gửi phản hồi rồi mới đọc thư tiếp, một lỗi downstream có thể giữ kết nối mailbox rất lâu hoặc làm worker bỏ sót thông báo.

Khái niệm hữu ích:

- **Poller/listener**: truy cập mail server để phát hiện thư mới.
- **Mail identity/checkpoint**: ghi nhận thư nào đã nhìn thấy hoặc lấy thành công.
- **MIME parser**: diễn giải header, nội dung và attachment.
- **Inbox store**: lưu event nhận email một cách bền vững.
- **Worker**: thực hiện xử lý nghiệp vụ ngoài vòng truy cập mailbox.
- **Dead-letter/quarantine**: giữ các thư chưa thể xử lý để điều tra mà không chặn cả mailbox.

## 4. IMAP là gì?

**IMAP** cho phép một client truy cập và quản lý email còn nằm trên server. Khái niệm nổi bật:

- **Mailbox/folder**: ví dụ INBOX, Sent, Archive, Support/Processed.
- **Message sequence number**: vị trí tương đối của message trong folder tại một thời điểm.
- **UID (Unique Identifier)**: định danh ổn định hơn sequence number trong cùng một mailbox, được dùng cùng **UIDVALIDITY**.
- **Flags**: các trạng thái như **\\Seen**, **\\Answered**, **\\Flagged**, **\\Deleted**.
- **Server-side search**: có thể tìm theo flag, thời gian và các tiêu chí server hỗ trợ.
- **FETCH**: lấy header, body, flag hoặc các phần MIME.
- **IDLE**: tiện ích mở rộng giúp server báo thay đổi gần thời gian thực khi server/client hỗ trợ.

Ví dụ:

~~~text
IMAP server
  |
  +-- INBOX
  |    +-- UID 101: unseen
  |    +-- UID 102: seen
  |    +-- UID 105: flagged
  |
  +-- Archive
  |    +-- UID 203
  |
  +-- Support/Processed
       +-- UID 45
~~~

IMAP là mô hình **mailbox lưu trên server**. Một client có thể đọc và đánh dấu thư, client khác có thể quan sát những thay đổi đó. Đây là điểm mạnh khi nhiều ứng dụng hoặc nhân viên cùng sử dụng hộp thư, nhưng cũng tạo **rủi ro tương tác trạng thái** nếu hệ thống tự động hóa coi flag là checkpoint duy nhất.

## 5. POP3 là gì?

**POP3** tập trung vào việc truy cập một maildrop để lấy thông điệp với giao thức tương đối đơn giản. Một phiên POP3 điển hình có các giai đoạn:

1. Kết nối, xác thực.
2. Liệt kê thông điệp có sẵn.
3. Đọc danh sách/sizes, lấy message.
4. Có thể đánh dấu message để xóa.
5. Thoát phiên để server áp dụng thao tác xóa theo giao thức.

POP3 thường không cung cấp mô hình nhiều folder, trạng thái Seen/Answered/Flagged hoặc đồng bộ thread phong phú như IMAP.

Ví dụ luồng:

~~~text
POP3 server: single maildrop
  |
  +-- message A
  +-- message B
  +-- message C
         |
         v
POP3 client downloads A/B/C
         |
         v
Local archive / processing queue
~~~

**Không mặc định POP3 luôn xóa thư sau khi tải**. Việc xóa hay giữ trên server phụ thuộc client, lệnh giao thức và cấu hình. Ứng dụng cần quyết định rõ chính sách lưu giữ và xử lý trùng.

## 6. IMAP và POP3 khác nhau ở những điểm nào?

| Tiêu chí | IMAP | POP3 |
|---|---|---|
| Mô hình chính | Quản lý mailbox trên server | Tải thư từ maildrop |
| Folder | Hỗ trợ mailbox/folder | Thường chỉ maildrop đơn |
| Flags Seen/Answered | Có | Không có mô hình tương đương đầy đủ |
| UID | UID theo mailbox + UIDVALIDITY | UIDL có thể được server hỗ trợ |
| Đồng bộ nhiều client | Phù hợp | Hạn chế |
| Tìm kiếm server-side | Có lệnh SEARCH | Hạn chế hơn |
| Chỉ tải một phần dữ liệu | Có thể, tùy server/API | Thường tập trung lấy message |
| Cơ chế gần realtime | IMAP IDLE nếu hỗ trợ | Thường polling |
| Chuyển thư qua folder | Có | Không phải chức năng chuẩn của POP3 |
| Triển khai luồng đơn giản | Cần quản lý trạng thái phong phú hơn | Thường dễ hiểu ban đầu |
| Checkpoint | Folder + UIDVALIDITY + UID | UIDL nếu có, hoặc fingerprint có kiểm soát |
| Xóa trên server | Flag + EXPUNGE hoặc phương thức tương ứng | Đánh dấu DELE rồi áp dụng khi QUIT |

Không nên hiểu IMAP là “luôn push, POP3 luôn pull”. IMAP có thể được **poll định kỳ**; IDLE là một cơ chế báo thay đổi, không phải một hàng đợi sự kiện bền vững.

## 7. Port và TLS cho inbound mail

| Giao thức | Port thường gặp | Chế độ bảo vệ |
|---|---:|---|
| IMAP | 143 | Plaintext ban đầu, có thể nâng cấp qua STARTTLS |
| IMAPS / IMAP implicit TLS | 993 | TLS ngay khi kết nối |
| POP3 | 110 | Plaintext ban đầu, có thể nâng cấp TLS qua STLS |
| POP3S / POP3 implicit TLS | 995 | TLS ngay khi kết nối |

Trong ứng dụng production, nên yêu cầu **TLS**, xác minh chuỗi chứng chỉ và hostname. Port chỉ là quy ước phổ biến; endpoint thực tế phải theo hướng dẫn của provider.

**IMAP STARTTLS** và **POP3 STLS** là cơ chế nâng cấp kết nối của từng giao thức. Chúng không phải lệnh SMTP STARTTLS, dù đều phục vụ việc kích hoạt TLS.

Ví dụ:

~~~text
IMAP trên 143:
  TCP -> IMAP greeting -> CAPABILITY -> STARTTLS -> TLS

IMAPS trên 993:
  TCP -> TLS handshake -> IMAP greeting

POP3 trên 110:
  TCP -> POP3 greeting -> STLS -> TLS

POP3S trên 995:
  TCP -> TLS handshake -> POP3 greeting
~~~

Không gửi username/password qua kết nối chưa được bảo vệ khi nhà cung cấp yêu cầu TLS. Không dùng **trust all certificates** để “chữa” lỗi hostname, CA hay truststore.

## 8. Spring Framework Mail hỗ trợ nhận thư như thế nào?

Các lớp chức năng trong hệ sinh thái Spring:

| Thành phần | Mục đích |
|---|---|
| **spring-context-support / JavaMailSender** | Tạo và gửi email bằng SMTP |
| **Jakarta Mail Session, Store, Folder, Message** | Truy cập IMAP/POP3 và đọc MIME |
| **Spring Integration Mail** | Inbound adapters, polling/IMAP IDLE và chuyển email thành message trong integration flow |
| **Spring Scheduling / TaskExecutor** | Lập lịch truy vấn mailbox và thực thi worker |
| **Spring Data / JDBC** | Lưu checkpoint, trạng thái, idempotency và metadata |
| **Spring Security** | Bảo vệ endpoint xử lý, tenant context và secret |

Lựa chọn thường gặp:

**A. Jakarta Mail trực tiếp** khi cần kiểm soát rất chi tiết folder, UIDVALIDITY, search, flags và checkpoint.

**B. Spring Integration Mail** khi quy trình nhận thư phù hợp với mô hình **message channel**, inbound adapter, poller, filter, transformer và các endpoint tích hợp.

Hai hướng không loại trừ nhau. Spring Integration Mail thường xây trên Jakarta Mail, còn một ứng dụng có thể dùng Jakarta Mail trong thành phần kỹ thuật riêng rồi đưa kết quả vào channel/queue của Spring.

## 9. Dependency cho các ví dụ

Trong dự án Spring Boot hiện đại có thể sử dụng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    // Nếu muốn inbound adapters / integration flows:
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Các ví dụ Java trực tiếp phía dưới dùng package **jakarta.mail** và giả định dependency Jakarta Mail implementation đã có qua starter hoặc dependency tương ứng. **Spring Boot 3 / Spring Framework 6** sử dụng Jakarta Mail namespace, khác với **javax.mail** của các thế hệ cũ.

**Không cần thêm Spring Integration Mail** nếu chỉ muốn gọi Jakarta Mail API trực tiếp. Ngược lại, chỉ thêm starter-mail không tự tạo inbound worker cho IMAP hoặc POP3.

Khi chọn dependency và ví dụ DSL, phải dùng các phiên bản **Spring Boot, Spring Integration, Jakarta Mail và JDK** tương thích với nhau theo hệ build của dự án.

## 10. Những đối tượng Jakarta Mail cốt lõi để đọc thư

| API | Vai trò |
|---|---|
| **Session** | Giữ các thuộc tính cấu hình Jakarta Mail và provider |
| **Store** | Kết nối tới kho thư IMAP hoặc POP3 |
| **Folder** | Mở và truy cập một mailbox/maildrop |
| **Message** | Một thông điệp đã nhận |
| **MimeMessage** | Message với MIME headers và multipart body |
| **Multipart** | Container của nhiều body part |
| **Part / BodyPart** | Truy cập Content-Type, content, filename, disposition |
| **FetchProfile** | Gợi ý lấy trước một nhóm metadata của nhiều message |
| **Flags** | Trạng thái Seen/Deleted/Answered và cờ khác khi giao thức hỗ trợ |
| **UIDFolder** | API chung để truy cập UID và UIDVALIDITY trong folder hỗ trợ UID |

Luồng truy cập đơn giản:

~~~text
Session.getInstance(properties)
          |
          v
session.getStore("imaps")
          |
          v
store.connect(...)
          |
          v
store.getFolder("INBOX")
          |
          v
folder.open(READ_ONLY / READ_WRITE)
          |
          v
folder.getMessages(...) / search(...)
          |
          v
read headers, MIME, attachments
          |
          v
folder.close(...) -> store.close()
~~~

**Store, Folder và Message thường gắn với tài nguyên kết nối/phiên**; không nên đưa các object này vào queue rồi mong worker ở process khác có thể sử dụng. Hãy chuyển đổi email thành một bản ghi/đối tượng dữ liệu đã lưu bền vững trước khi đóng phiên.

## 11. Ví dụ đọc INBOX qua IMAPS bằng Jakarta Mail

Ví dụ dưới đây mở **IMAP implicit TLS trên port 993**, lấy tối đa 20 message cuối theo sequence number và đọc metadata cơ bản. Mục tiêu là minh họa kết nối và vòng đời tài nguyên, **chưa phải một consumer có checkpoint**.

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import jakarta.mail.internet.InternetAddress;
import java.util.Properties;

public final class ImapsMailboxReader {

    public void readRecent(
            String host,
            String username,
            String password
    ) throws Exception {

        Properties props = new Properties();
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");
        props.put("mail.imaps.writetimeout", "10000");
        props.put("mail.imaps.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");

        try {
            store.connect(host, 993, username, password);
            Folder inbox = store.getFolder("INBOX");

            try {
                inbox.open(Folder.READ_ONLY);

                int count = inbox.getMessageCount();
                if (count == 0) {
                    return;
                }

                int first = Math.max(1, count - 19);
                Message[] messages = inbox.getMessages(first, count);

                for (Message message : messages) {
                    System.out.println("Subject: "
                            + message.getSubject());

                    InternetAddress[] from =
                            (InternetAddress[]) message.getFrom();

                    if (from != null && from.length > 0) {
                        System.out.println(
                                "From: " + from[0].getAddress()
                        );
                    }
                }
            } finally {
                if (inbox.isOpen()) {
                    inbox.close(false);
                }
            }
        } finally {
            store.close();
        }
    }
}
~~~

Ví dụ dùng các giá trị **host, username, password** lấy từ cấu hình bảo mật của ứng dụng. Không đặt credential thật trong source code hoặc log.

### Những giới hạn của ví dụ này

- Chỉ đọc **20 message có sequence number cuối cùng**; có thể bỏ sót thư nếu mailbox nhận nhiều hơn 20 message giữa các lần chạy.
- Chưa có checkpoint, nên mỗi lần chạy có thể đọc lại cùng email.
- Việc đọc metadata không đồng nghĩa email đã được xử lý nghiệp vụ.
- In địa chỉ người gửi ra stdout chỉ phù hợp để minh họa trong môi trường thử nghiệm; production phải kiểm soát log và PII.
- Cast sang **InternetAddress[]** phù hợp với mailbox Internet mail thông thường, nhưng một implementation có thể trả mảng **Address[]** không phải loại mảng cụ thể; khi triển khai rộng, kiểm tra từng phần tử bằng **instanceof InternetAddress** thay vì cast cả mảng.

Trong pipeline production, hãy đọc theo **UID/checkpoint**, không chỉ lấy N email cuối. Phần tiếp theo giải thích lý do.

## 12. Đọc qua IMAP STARTTLS thay cho implicit TLS

Nếu server yêu cầu dùng IMAP port 143 và nâng cấp TLS, một cấu hình Jakarta Mail có thể là:

~~~java
Properties props = new Properties();

props.put("mail.imap.starttls.enable", "true");
props.put("mail.imap.starttls.required", "true");
props.put("mail.imap.ssl.checkserveridentity", "true");
props.put("mail.imap.connectiontimeout", "5000");
props.put("mail.imap.timeout", "10000");
props.put("mail.imap.writetimeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("imap");

try {
    store.connect(host, 143, username, password);
    // Truy cập Folder sau khi STARTTLS đã được thiết lập.
} finally {
    store.close();
}
~~~

Khác biệt cần nhớ:

~~~text
session.getStore("imaps")
  -> mail.imaps.* properties
  -> implicit TLS, thường port 993

session.getStore("imap")
  -> mail.imap.* properties
  -> STARTTLS nếu enable/required, thường port 143
~~~

**Property prefix phải phù hợp protocol/provider đang dùng.** Nếu cấu hình **mail.imaps.timeout** nhưng lấy **Store("imap")**, timeout có thể không được áp dụng như mong đợi.

Nếu yêu cầu bảo mật, **starttls.required=true** giúp không tiếp tục phiên không mã hóa khi server không hỗ trợ nâng cấp. Đừng sửa lỗi TLS bằng cách bỏ kiểm tra hostname hoặc chấp nhận mọi chứng chỉ.

## 13. IMAP message sequence number không phải checkpoint bền vững

Trong IMAP, **sequence number** cho biết vị trí hiện tại của message trong folder đang được chọn. Nó có thể thay đổi khi thư bị xóa/expunge.

Ví dụ:

~~~text
Lúc 09:00:
  seq 1 -> message A
  seq 2 -> message B
  seq 3 -> message C

Sau khi message A bị EXPUNGE:
  seq 1 -> message B
  seq 2 -> message C
~~~

Nếu ứng dụng lưu **lastSequenceNumber = 3**, lần sau đọc “sequence > 3”, nó có thể bỏ sót những thư mới do số thứ tự đã thay đổi.

Vì vậy:

- **Sequence number** dùng để truy cập vị trí tạm thời trong phiên/folder.
- **UID** là định danh thích hợp hơn để checkpoint trong cùng một mailbox khi được kết hợp với **UIDVALIDITY**.
- **Message-ID** là header do hệ thống gửi tạo ra, không phải khóa định danh folder đáng tin cậy tuyệt đối.

**Đừng dùng message.getMessageNumber() như idempotency key lâu dài**.

## 14. IMAP UID và UIDVALIDITY

Mỗi message trong một IMAP mailbox có thể có **UID** do server cấp. UID có ý nghĩa trong phạm vi mailbox và gắn với **UIDVALIDITY**.

Một checkpoint có thể là:

~~~text
account_id      = mailbox-support-A
folder          = INBOX
uid_validity    = 1836720
last_uid        = 184930
~~~

Ý nghĩa:

- Nếu **UIDVALIDITY vẫn như cũ**, có thể xem UID là phần định danh ổn định trong cùng folder.
- Nếu **UIDVALIDITY thay đổi**, những UID đã lưu có thể không còn ánh xạ tới cùng message. Phải thực hiện quy trình đồng bộ lại có kiểm soát.
- UID không phải định danh toàn cục giữa hai folder, hai account hoặc hai server.
- Khi copy/move giữa folder, bản ở folder mới có thể nhận UID khác.

### API Jakarta Mail

~~~java
import jakarta.mail.Folder;
import jakarta.mail.UIDFolder;
import jakarta.mail.Message;

Folder inbox = store.getFolder("INBOX");
inbox.open(Folder.READ_ONLY);

if (!(inbox instanceof UIDFolder uidFolder)) {
    throw new IllegalStateException(
            "IMAP folder không có UIDFolder API"
    );
}

long uidValidity = uidFolder.getUIDValidity();
long messageUid = uidFolder.getUID(message);
~~~

Đoạn code giả định biến **store** đã kết nối và **message** lấy từ chính folder **inbox** đang mở. Với IMAP provider thông thường của Jakarta Mail, UIDFolder là API phù hợp.

### UIDVALIDITY thay đổi thì làm gì?

Không tiếp tục dùng **last_uid cũ** như bình thường. Một chiến lược:

1. Đánh dấu checkpoint cũ không còn hợp lệ.
2. Lập kế hoạch quét lại mailbox với giới hạn và dedup.
3. Đối chiếu với những message đã lưu bằng key nghiệp vụ phù hợp.
4. Tạo checkpoint mới theo UIDVALIDITY mới sau khi xử lý.
5. Giám sát trường hợp thay đổi để phát hiện migrate/rebuild mailbox hoặc sự cố phía server.

Không có một phép biến đổi đơn giản đáng tin cậy từ UID cũ sang UID mới nếu UIDVALIDITY đã đổi.

## 15. Tìm thư IMAP theo UID thay vì tải toàn bộ INBOX

Với **UIDFolder**, có thể yêu cầu các message trong một khoảng UID:

~~~java
UIDFolder uidFolder = (UIDFolder) inbox;

long fromUid = lastProcessedUid + 1;
Message[] candidates = uidFolder.getMessagesByUID(
        fromUid,
        UIDFolder.LASTUID
);

for (Message message : candidates) {
    long uid = uidFolder.getUID(message);
    // Chuẩn bị dữ liệu và xử lý/checkpoint theo chính sách.
}
~~~

API này minh họa cơ chế lấy theo UID, **chưa đủ để bảo đảm xử lý đúng trong production**:

- Nếu mailbox có lượng thư lớn, một truy vấn UID rộng có thể trả quá nhiều message vào bộ nhớ.
- UID không nhất thiết liên tục; có thể có gap do expunge.
- Cần lưu checkpoint theo **UIDVALIDITY** và account/folder.
- Cần hạn chế số message mỗi batch hoặc thiết kế pagination phù hợp.
- Phải cập nhật checkpoint sau khi đã lưu email bền vững, không phải ngay sau khi thấy UID.
- Nếu thư bị xóa giữa lúc liệt kê và fetch, server có thể trả dữ liệu thiếu hoặc lỗi; cần xử lý riêng.

### Vì sao lastProcessedUid dễ nguy hiểm?

Giả sử:

~~~text
UID 100 -> xử lý thành công
UID 101 -> parse lỗi tạm thời
UID 102 -> xử lý thành công
~~~

Nếu ghi checkpoint **102** ngay, worker lần sau chỉ đọc UID lớn hơn 102, sẽ bỏ qua **101** mãi mãi.

Có hai lựa chọn:

1. **Checkpoint liên tục:** chỉ tăng high-water mark tới UID lớn nhất mà mọi UID nhìn thấy trước đó đã xử lý hoặc được lưu bền vững; lỗi được đưa vào retry queue trước khi tăng.
2. **Lưu trạng thái từng message:** ghi record cho từng UID, cho phép 101 có trạng thái FAILED/RETRY còn checkpoint discovery vẫn có thể tiến.

Đối với hệ thống cần throughput cao và retry riêng, **inbox table có unique key theo mailbox + UIDVALIDITY + UID** thường đáng tin cậy hơn việc chỉ có một biến last UID.

## 16. Phân biệt Seen flag với trạng thái xử lý nghiệp vụ

IMAP có flag **\\Seen** báo message đã được đánh dấu đọc. Nhưng “đã đọc” không đồng nghĩa:

- Đã parse MIME thành công.
- Đã lưu attachment.
- Đã tạo ticket/hóa đơn.
- Đã gửi event vào queue.
- Đã commit database transaction.

Ví dụ lỗi:

~~~text
Worker FETCH message
      |
      v
Set \\Seen
      |
      v
Process crash trước khi tạo ticket

Lần sau chỉ tìm UNSEEN
      |
      v
Message bị bỏ qua vĩnh viễn
~~~

Nếu mailbox còn được nhân viên đọc thủ công hoặc nhiều client truy cập, họ có thể thay đổi Seen flag ngoài ý muốn. Vì vậy **không dùng Seen làm nguồn sự thật duy nhất cho exactly-once processing**.

### Chính sách thực tế

- Có thể mở folder **READ_ONLY** trong bước discovery/fetch để tránh thay đổi state server.
- Lưu **UID/checkpoint** và record xử lý trong database của ứng dụng.
- Chỉ đặt Seen hoặc chuyển folder sang Processed khi nghiệp vụ đã commit theo policy.
- Khi có nhiều consumer, dùng cơ chế claim/lease ở database/queue để không xử lý cùng UID đồng thời.
- Tránh tự chuyển tất cả thư chưa đọc thành Seen khi chưa xác minh nhu cầu của người sử dụng hộp thư.

Một hệ thống shared mailbox có thể cần giữ Seen flag do nhân viên kiểm soát, và chỉ sử dụng **application-specific checkpoint** cho automation.

## 17. IMAP IDLE giúp gì?

**IMAP IDLE** cho phép server thông báo thay đổi trong folder khi client đang chờ, thay vì phải gửi lệnh polling liên tục trong mọi khoảng thời gian.

~~~text
Client                        IMAP server
  | SELECT INBOX                   |
  |------------------------------->|
  | IDLE                           |
  |------------------------------->|
  |                                |
  |<----------- EXISTS update -----|
  | DONE / kết thúc IDLE           |
  |------------------------------->|
  | FETCH/SEARCH message mới      |
  |------------------------------->|
  | IDLE lại                       |
~~~

Những lợi ích có thể có:

- Giảm độ trễ phát hiện email mới.
- Giảm polling liên tục khi mailbox ít thư.
- Phù hợp ticket inbox, phản hồi khách hàng hoặc mailbox có yêu cầu latency ngắn.

Nhưng IDLE **không phải broker đảm bảo lưu sự kiện**:

- TCP connection có thể bị ngắt.
- Server có thể chủ động kết thúc IDLE sau một thời gian.
- Firewall/NAT có thể đóng kết nối nhàn rỗi.
- Trong thời gian reconnect, client có thể bỏ lỡ thông báo EXISTS.
- Server có thể gửi nhiều event nhưng nội dung thực tế vẫn cần fetch.

**Sau reconnect vẫn phải đối chiếu UID/checkpoint**, không chỉ xử lý những sự kiện IDLE vừa nhận.

## 18. Khi nào nên polling, khi nào nên dùng IMAP IDLE?

| Tiêu chí | Polling IMAP | IMAP IDLE |
|---|---|---|
| Cách phát hiện | Truy vấn theo lịch | Server thông báo thay đổi |
| Mức độ triển khai | Dễ kiểm soát bằng scheduler | Cần quản lý kết nối duy trì |
| Độ trễ | Bằng chu kỳ poll cộng xử lý | Thường ngắn hơn nếu server hỗ trợ |
| Tải khi mailbox ít traffic | Có các poll không có thư | Ít truy vấn hơn, nhưng giữ kết nối |
| Ngắt kết nối | Poll sau tự chạy lại | Cần reconnect và đồng bộ bù |
| Yêu cầu UID/checkpoint | Có | Vẫn có |
| Trường hợp phù hợp | Batch định kỳ, tải thấp, SLA phút | Ticket/live reply, SLA gần thời gian thực |

Một kiến trúc bền vững có thể kết hợp:

~~~text
IMAP IDLE -> báo có thay đổi -> trigger incremental UID sync

Periodic reconciliation -> soát UID còn thiếu

Connection broken -> reconnect -> incremental UID sync
~~~

Điểm cốt lõi: **IDLE là tín hiệu đánh thức**, còn **UID reconciliation và inbox persistence** mới là nền tảng tránh bỏ sót dữ liệu. Không nên ghi checkpoint chỉ vì nhận được một thông báo EXISTS, trước khi fetch/lưu thư.

Với ứng dụng có nhiều mailbox, một kết nối IDLE cho mỗi folder có thể tốn socket/thread/tài nguyên server. Cần kiểm tra quota kết nối đồng thời của provider và có chiến lược phân vùng/scheduling, thay vì mở hàng nghìn kết nối cố định.

## 19. Spring Integration Mail: inbound adapters

**Spring Integration** sử dụng mô hình message-driven:

~~~text
IMAP/POP3 server
         |
         v
Mail inbound component
         |
         v
Spring Integration MessageChannel
         |
         v
Filter / Transformer / Service Activator
         |
         v
Business service / Queue / Database
~~~

Trong hệ sinh thái Spring Integration Mail có các khái niệm:

- **ImapMailReceiver**: nhận thư qua IMAP.
- **Pop3MailReceiver**: nhận thư qua POP3.
- **MailReceivingMessageSource**: bridge từ mail receiver thành nguồn message để poll.
- **IMAP IDLE adapter**: thành phần inbound theo cơ chế IDLE, khi cấu hình và server hỗ trợ.
- **Poller**: định thời gian gọi nguồn message, có thể dùng fixed delay hoặc trigger khác.
- **MessageChannel**: tách bước thu thư và bước xử lý phía sau.
- **Service activator / handler**: gọi business logic sau khi nhận message.

Ví dụ kiến trúc:

~~~text
ImapMailReceiver
       |
       v
MailReceivingMessageSource
       |
       v
Poller (every 30 seconds)
       |
       v
Channel
       |
       v
Validate + Persist inbox
       |
       v
Async processing
~~~

Trong hệ thống sử dụng Spring Integration DSL, có thể cấu hình inbound flow bằng các factory tương ứng với phiên bản đang dùng. **Tùy phiên bản Spring Integration, cách khởi tạo adapter, tên DSL method và kiểu trả về có thể khác nhau.** Cần đối chiếu API đúng với dependency của dự án; không sao chép một ví dụ dùng namespace cũ rồi giả định nó hoạt động trên Spring Integration mới.

### Spring Integration có tự bảo đảm exactly-once không?

Không. Inbound adapter có thể nhận lại message sau reconnect, restart hoặc khi chưa đánh dấu trạng thái trên server. **Idempotency, transaction, lưu bền vững và checkpoint theo mailbox** vẫn là trách nhiệm thiết kế của ứng dụng.

Trong nhiều dự án, có thể dùng Spring Integration để điều phối và filter, nhưng vẫn ghi một record **mail_inbox** với unique key trước khi thực hiện tác vụ có side effect.

## 20. Điều cần cấu hình khi dùng Spring Integration Mail

Một inbound adapter thực tế cần làm rõ:

| Nhóm cấu hình | Câu hỏi |
|---|---|
| Protocol | IMAP, IMAPS, POP3 hay POP3S? |
| Mailbox | Host, port, folder/maildrop nào? |
| Authentication | Password/app password/OAuth2 được provider cho phép? |
| TLS | Implicit TLS hay STARTTLS/STLS bắt buộc? |
| Polling | Chu kỳ poll, batch size, concurrency ra sao? |
| Search | Chỉ chọn thư chưa đọc hay dùng UID/checkpoint riêng? |
| Mark-as-read | Khi nào đặt Seen, nếu có? |
| Delete/expunge | Có được phép xóa thư trên server không? |
| MIME output | Giữ nguyên MimeMessage hay chuyển thành payload được chuẩn hóa? |
| Transaction | Khi nào ghi nhận inbox và xác nhận đã nhận? |
| Error channel | Email lỗi parse/validation đi đâu? |
| Reconnect | Trở lại sau timeout, disconnect hoặc credential rotation thế nào? |

Tránh đưa trực tiếp username/password trong một **URL cấu hình receiver** rồi log nguyên URL. Một số API có thể nhận mail URL, nhưng credentials cần lấy từ secret manager và được che khi theo dõi cấu hình.

### Những điểm cần kiểm tra với adapter

Một cấu hình mặc định có thể thay đổi trạng thái thư bằng flag, lọc theo **UNSEEN**, hoặc đặt giới hạn lấy thư. Những hành vi này ảnh hưởng tới retry và dữ liệu đã xử lý, nên phải kiểm tra đặc tính của **receiver/adaptor + phiên bản thư viện** thực tế.

Không sử dụng default behavior như một cam kết nghiệp vụ. Nếu hộp thư được chia sẻ với con người, cấu hình mark-as-read và delete phải được chọn có chủ đích.

## 21. Ví dụ service đọc POP3S qua Jakarta Mail

Với POP3 implicit TLS thường dùng **protocol "pop3s"** trên port 995. Ví dụ đơn giản:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

public final class Pop3sMailboxReader {

    public void readMessages(
            String host,
            String username,
            String password
    ) throws Exception {

        Properties props = new Properties();
        props.put("mail.pop3s.connectiontimeout", "5000");
        props.put("mail.pop3s.timeout", "10000");
        props.put("mail.pop3s.writetimeout", "10000");
        props.put("mail.pop3s.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = session.getStore("pop3s");

        try {
            store.connect(host, 995, username, password);
            Folder inbox = store.getFolder("INBOX");

            try {
                inbox.open(Folder.READ_ONLY);

                int count = inbox.getMessageCount();
                for (int i = 1; i <= count; i++) {
                    Message message = inbox.getMessage(i);
                    String subject = message.getSubject();

                    // Thực tế cần lưu fingerprint/UIDL để chống trùng.
                    processMetadata(subject);
                }
            } finally {
                if (inbox.isOpen()) {
                    inbox.close(false);
                }
            }
        } finally {
            store.close();
        }
    }

    private void processMetadata(String subject) {
        // Ví dụ placeholder cho bước xử lý.
    }
}
~~~

Các caveat:

- Đây là **minh họa đọc**, chưa có UIDL, lưu inbox, retry, quota hoặc chống trùng.
- Mỗi lần chạy có thể đọc lại toàn bộ maildrop.
- Không nên đọc hàng chục nghìn message vào memory mà không batch/limit.
- Một POP3 server có thể đặt giới hạn đồng thời và chính sách xóa/thời gian lưu.
- **READ_ONLY** giúp tránh ý định xóa trong ví dụ này; không có nghĩa POP3 cung cấp bộ flag và folder đầy đủ như IMAP.

Nếu mailbox lớn, ưu tiên server/API có khả năng phân trang hoặc điều chỉnh kiến trúc. POP3 không được thiết kế để thực hiện mọi phép truy vấn/đồng bộ metadata như IMAP.

## 22. POP3 STLS trên port 110

Một provider có thể yêu cầu POP3 thường rồi nâng cấp TLS bằng **STLS**:

~~~java
Properties props = new Properties();

props.put("mail.pop3.starttls.enable", "true");
props.put("mail.pop3.starttls.required", "true");
props.put("mail.pop3.ssl.checkserveridentity", "true");
props.put("mail.pop3.connectiontimeout", "5000");
props.put("mail.pop3.timeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("pop3");

try {
    store.connect(host, 110, username, password);
    // Lấy maildrop từ Store sau khi kết nối an toàn.
} finally {
    store.close();
}
~~~

Các khóa property ở đây thuộc **Jakarta Mail POP3 provider tương thích**. Tương tự IMAP, prefix **mail.pop3** và **mail.pop3s** không thể thay thế tùy tiện.

**Không bật một chế độ TLS chỉ vì port trông quen thuộc.** Địa chỉ endpoint, khả năng STLS và cách xác thực phải khớp hướng dẫn của nhà cung cấp.

## 23. POP3 UIDL: cách nhận diện message đã tải

POP3 có extension **UIDL (Unique-ID Listing)** được nhiều server hỗ trợ, giúp client nhận diện message đã từng tải thay vì dựa vào số thứ tự trong maildrop.

Ví dụ:

~~~text
POP3 session A:
  1 -> UIDL abc-100
  2 -> UIDL abc-101
  3 -> UIDL abc-102

Sau khi một message bị xóa:
POP3 session B:
  1 -> UIDL abc-101
  2 -> UIDL abc-102
~~~

Ở đây số thứ tự message thay đổi nhưng UIDL của các message còn tồn tại vẫn được server giữ theo hợp đồng extension.

Những điều cần lưu ý:

- **Jakarta Mail Folder chuẩn không định nghĩa một API UIDL portable chung** giống UIDFolder của IMAP.
- Các POP3 implementation có thể cung cấp API đặc thù để lấy UIDL (ví dụ kiểu POP3Folder của provider).
- Không nên cast folder sang implementation cụ thể khi chưa xác minh library/version dùng thực tế.
- UIDL có phạm vi và hành vi theo POP3 server; cần lưu cùng account/maildrop identity.
- Nếu server không hỗ trợ UIDL hoặc UIDL không ổn định, cần chiến lược dedup dự phòng.

Một kho checkpoint có thể lưu:

~~~text
pop3_account_id
uidl_value
first_seen_at
processing_status
ingested_message_ref
~~~

Không dùng số thứ tự POP3 message để làm khóa bất biến lâu dài. Với một mailbox có nhiều worker, cần đặc biệt chú ý đến việc một message có thể được lấy bởi hơn một session.

## 24. POP3: xóa thư hay giữ trên server?

POP3 thường cho phép client đánh dấu message để xóa trong phiên. Việc xóa trên server được thực hiện theo hành vi giao thức khi phiên kết thúc phù hợp.

Hai chiến lược:

**Giữ thư trên server**

- Dễ đối chiếu hoặc tải lại khi pipeline chưa ổn định.
- Cần UIDL/dedup để tránh xử lý lặp.
- Maildrop có thể tăng kích thước và quota lưu trữ.

**Xóa sau khi nhận**

- Giảm kích thước maildrop.
- Cần chứng minh dữ liệu đã được lưu bền vững trước khi đánh dấu xóa.
- Nếu xóa trước khi transaction ứng dụng commit, dữ liệu có thể mất.
- POP3 không phải hàng đợi giao dịch có ACK chính xác sau commit database.

Ví dụ quy trình an toàn hơn:

~~~text
POP3 RETR message
       |
       v
Validate size and parser boundaries
       |
       v
Persist raw message + dedup record
       |
       v
Commit inbox transaction
       |
       v
Optional mark for deletion
       |
       v
Close session according to delete policy
       |
       v
Business worker handles persisted inbox item
~~~

Ngay cả khi làm đúng thứ tự, vẫn có trường hợp crash giữa commit database và xóa message, khiến thư tồn tại trên server và xuất hiện lại. **Dedup/idempotency** phải xử lý được việc đó.

Không dùng **folder.close(true)** hoặc flag DELETED một cách máy móc cho mọi mail server hoặc mọi loại inbox. Chính sách xóa IMAP và POP3 khác nhau, và một hộp thư chia sẻ thường không được phép xóa tự động.

## 25. Khi IMAP phù hợp hơn POP3

Chọn IMAP nếu ứng dụng cần:

- Đồng bộ mailbox với thư mục INBOX/Processed/Archive.
- Đánh dấu đã đọc, đã trả lời hoặc đã xử lý theo trạng thái trên server.
- Nhiều client cùng truy cập hoặc người dùng cũng quản lý mailbox.
- Tìm kiếm theo header, ngày, flag, folder.
- UID/checkpoint ổn định theo mailbox.
- Nhận tín hiệu thay đổi gần thời gian thực qua IDLE.
- Chỉ lấy header trước, tải body/attachment sau theo chính sách.
- Lưu trữ và phân loại thư trên server trong thời gian dài.

Ví dụ **support ticket inbox**:

~~~text
support@company.example
       |
       v
IMAP INBOX
       |
       +-- New mail -> create ticket
       +-- Human reads mailbox -> Seen may change
       +-- Automation stores own UID checkpoint
       +-- After durable processing -> optional move to Processed
~~~

Ở mô hình này, IMAP thuận lợi vì có folder và state, nhưng ứng dụng vẫn không được dùng Seen flag thay cho checkpoint nghiệp vụ.

## 26. Khi POP3 có thể phù hợp

Chọn POP3 khi:

- Hệ thống chỉ cần **tải thư xuống**, không cần quản lý nhiều folder.
- Mailbox được dành riêng cho một integration process.
- Thông điệp được đưa vào **inbox database/object store** của ứng dụng ngay sau khi đọc.
- Không cần đồng bộ trạng thái đã đọc giữa nhiều client.
- Lưu lượng và số client thấp, hạn chế tranh chấp.
- Provider cung cấp POP3 nhưng không cung cấp IMAP cho account cụ thể.

Ví dụ mailbox thu tài liệu:

~~~text
receipts@partner.example
        |
        v
POP3 retrieve
        |
        v
Durable inbox + attachment archive
        |
        v
Document processing queue
        |
        v
Accounting workflow
~~~

Với thiết kế này, POP3 chỉ là **cổng lấy dữ liệu**. Trạng thái xử lý, retry và audit được quản lý trong ứng dụng.

Không nên sử dụng POP3 nếu yêu cầu đồng bộ thư mục, thao tác flag phong phú hoặc nhiều client phối hợp trên cùng mailbox mà không có tầng điều phối bổ sung.

## 27. Kiến trúc Inbox Pattern để không làm mất email

Giữa mail server và database ứng dụng **không có transaction ACID chung**. Khi xử lý thư, có thể gặp:

~~~text
Case A:
  Fetch mail OK
  Mark Seen / delete trên server
  DB transaction fail
  -> Mất cơ hội xử lý nếu chỉ tìm unread/đã xóa

Case B:
  Fetch mail OK
  DB commit OK
  Process crash trước khi mark Seen/delete
  -> Lần sau đọc lại cùng email
~~~

Đây là lý do inbound email nên thiết kế theo **at-least-once ingestion + idempotent processing**, thay vì hứa hẹn exactly-once chỉ dựa vào IMAP hoặc POP3.

Một pipeline:

~~~text
IMAP / POP3 fetch
       |
       v
Derive stable identity
       |
       v
BEGIN DB TRANSACTION
  INSERT mail_inbox (unique mail identity)
  INSERT processing_outbox / work item
COMMIT
       |
       v
Advance discovery checkpoint
       |
       v
Optional mark Seen / move / delete on mail server
       |
       v
Business worker processes persisted item
~~~

Nếu process crash trước commit, mail được đọc lại. Nếu crash sau commit nhưng trước checkpoint/server mutation, mail được đọc lại **nhưng unique key chặn việc tạo cùng một inbox item lần nữa**.

### Khi nào checkpoint được phép tăng?

Chỉ khi các message đã được **lưu bền vững hoặc đã có trạng thái lỗi/quarantine bền vững**, để không bỏ qua một UID chưa có dấu vết trong inbox database.

Nếu business worker còn phải gọi dịch vụ bên ngoài, không giữ IMAP Folder mở chờ đến khi toàn bộ quy trình hoàn tất; hãy để worker xử lý từ dữ liệu đã persist.

## 28. Định danh message: IMAP UID, POP3 UIDL và Message-ID

Một email có thể có nhiều định danh:

| Định danh | Nguồn | Độ tin cậy và phạm vi |
|---|---|---|
| **IMAP UID** | IMAP server | Dùng với mailbox/folder và UIDVALIDITY |
| **IMAP UIDVALIDITY** | IMAP server | Xác định thế hệ UID của folder |
| **POP3 UIDL** | POP3 server nếu hỗ trợ | Theo maildrop/provider; không dùng sequence number thay thế |
| **Message-ID header** | Message creator | Không bắt buộc duy nhất toàn cầu, có thể thiếu/giả |
| **SHA-256 raw MIME** | Ứng dụng tính trên dữ liệu đã fetch | Nhận diện nội dung chính xác theo bytes; có thể đổi khi relay/serialize |
| **Provider message ID** | ESP/mail server nếu có | Có ý nghĩa theo provider/account |
| **Business correlation ID** | Ứng dụng tự gắn/ánh xạ | Dùng để liên kết với ticket/notification nghiệp vụ |

Với IMAP, unique key thường là:

~~~text
(mail_account_id, folder_id, uid_validity, uid)
~~~

Với POP3:

~~~text
(mail_account_id, uidl)
~~~

Khi không có UIDL hoặc UIDL không tin cậy, có thể dùng combination của header/size/hash **cùng chính sách dedup cụ thể**. Không nên chỉ dùng **Message-ID** làm khóa tuyệt đối vì hai email khác nhau có thể có Message-ID trùng, bị thiếu hoặc bị nhà cung cấp thay đổi.

### Hai mailbox có cùng một message không nhất thiết là lỗi trùng

Một thư được forward từ mailbox A sang mailbox B có thể cần xử lý ở cả hai pipeline khác nhau. Identity **phải bao gồm mailbox/account scope** hoặc tenant scope theo nghiệp vụ.

Ngược lại, cùng một email được lấy lại từ một mailbox sau restart không nên tạo hai ticket hoặc nhập hóa đơn hai lần.

## 29. Thiết kế bảng mail_inbox

Ví dụ dữ liệu nghiệp vụ có thể gồm:

~~~sql
CREATE TABLE mail_inbox (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id        VARCHAR(120) NOT NULL,
    folder_name       VARCHAR(300),
    uid_validity      BIGINT,
    imap_uid          BIGINT,
    pop3_uidl         VARCHAR(600),
    message_id_header VARCHAR(1000),
    raw_object_key    VARCHAR(1200),
    sender_address    VARCHAR(600),
    subject_preview   VARCHAR(500),
    received_at       TIMESTAMP WITH TIME ZONE,
    ingested_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    status            VARCHAR(40) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0
);
~~~

Ví dụ constraint cho IMAP:

~~~sql
CREATE UNIQUE INDEX uq_imap_mail_identity
ON mail_inbox (
    account_id,
    folder_name,
    uid_validity,
    imap_uid
)
WHERE imap_uid IS NOT NULL;
~~~

Ví dụ cho POP3:

~~~sql
CREATE UNIQUE INDEX uq_pop3_mail_identity
ON mail_inbox (account_id, pop3_uidl)
WHERE pop3_uidl IS NOT NULL;
~~~

Đây là DDL minh họa cho một hệ SQL hỗ trợ **partial index** như PostgreSQL; schema production có thể cần tenantId, mailbox ID ổn định, checksum, state transition và retention.

### Vì sao nên lưu raw MIME ngoài database?

Nếu email có attachment lớn, nhét toàn bộ EML/blob vào một bảng transaction nóng có thể làm tăng database size và ảnh hưởng query. Có thể lưu **raw EML** vào object storage được phân quyền, còn database giữ **object key, checksum, kích thước và metadata**.

Quan trọng: phải có quy trình **staging/commit/reconciliation** giữa object storage và DB vì hai hệ thống không có transaction nguyên tử chung. Không đánh dấu inbox PERSISTED khi EML còn chưa lưu chắc chắn ở storage.

### Không lưu PII nếu không cần

Sender, Subject, attachment name và một số MIME headers có thể chứa dữ liệu cá nhân. Chỉ lưu thông tin phục vụ nghiệp vụ và debug trong thời gian phù hợp. Nếu chỉ cần Message-ID và UID, không nhất thiết lưu toàn bộ body vô thời hạn.

## 30. Lưu trạng thái nhận thư rõ ràng

Một state machine có thể là:

~~~text
DISCOVERED
    |
    v
FETCHING
    |
    +-- transient network error -> FETCH_RETRY
    |
    +-- MIME too large / disallowed -> QUARANTINED
    |
    v
PERSISTED
    |
    v
PROCESSING
    |
    +-- transient business error -> PROCESS_RETRY
    |
    +-- invalid/malicious content -> QUARANTINED
    |
    v
PROCESSED
~~~

Các trạng thái này do ứng dụng định nghĩa; IMAP hoặc POP3 **không tự cung cấp state machine nghiệp vụ**.

Nếu message bị lỗi parse, không nên làm poller liên tục thử lại ngay rồi chặn mọi email phía sau. Có thể lưu raw content vào quarantine, ghi reason code và cho checkpoint discovery tiến theo chính sách.

### Discovery và processing là hai tiến trình khác nhau

**Discovery** xác định message chưa được lưu vào inbox database. **Processing** đọc inbox item đã lưu và thực hiện tác vụ nghiệp vụ.

Việc tách hai bước giúp:

- Ngắt kết nối IMAP nhanh hơn.
- Giới hạn CPU/attachment parsing độc lập với số kết nối mail server.
- Retry business logic mà không tải lại email từ server.
- Xử lý lỗi/quarantine mà không mất dấu mail gốc.
- Điều phối throughput theo tenant, loại hộp thư hoặc loại tác vụ.

## 31. Đọc MIME: email không chỉ là String

Một email nhận được có thể chứa:

~~~text
MimeMessage
  |
  +-- multipart/mixed
       |
       +-- multipart/related
       |    |
       |    +-- multipart/alternative
       |    |    +-- text/plain
       |    |    +-- text/html
       |    |
       |    +-- image/png (inline, Content-ID)
       |
       +-- application/pdf (attachment)
~~~

Tình huống:

- **text/plain** là bản văn bản để đọc/thực hiện một số trích xuất.
- **text/html** là bản HTML có thể có link và tài nguyên inline.
- **multipart/alternative** chứa các bản thay thế, không phải những đoạn nội dung cần nối trực tiếp.
- **multipart/related** nhóm HTML với hình CID/inline resources.
- **multipart/mixed** thường gom nội dung và file đính kèm.

Vì vậy code:

~~~java
String body = (String) message.getContent();
~~~

**không an toàn như một parser tổng quát**. Nếu message là multipart, **getContent()** có thể trả về **Multipart**, không phải String, dẫn đến ClassCastException.

Nên thiết kế **MIME walker** dựa trên **Part**, đọc Content-Type/Content-Disposition và phân loại leaf parts.

## 32. Duyệt multipart bằng Jakarta Mail

Một ví dụ helper giới hạn độ sâu:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

public final class MimePartCollector {

    public record PartRef(
            Part part,
            String mimeType,
            String disposition
    ) {
    }

    public static List<PartRef> collect(Part root)
            throws Exception {
        List<PartRef> found = new ArrayList<>();
        walk(root, 0, found);
        return List.copyOf(found);
    }

    private static void walk(
            Part part,
            int depth,
            List<PartRef> found
    ) throws Exception {
        if (depth > 24 || found.size() > 200) {
            throw new IllegalStateException(
                    "MIME nesting/part count exceeds policy"
            );
        }

        found.add(new PartRef(
                part,
                part.getContentType(),
                part.getDisposition()
        ));

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();

            if (!(content instanceof Multipart multipart)) {
                throw new IllegalStateException(
                        "Expected Multipart content"
                );
            }

            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                walk(child, depth + 1, found);
            }
        }
    }
}
~~~

Đây là **helper minh họa cho các MIME multipart thông thường**, chưa phải parser bảo mật production:

- Nó chưa xử lý riêng **message/rfc822** lồng trong attachment.
- Giới hạn **số part và độ sâu** chưa thay thế giới hạn **tổng byte giải mã**.
- Nó chưa phân biệt text chính và attachment text.
- Nó chưa kiểm tra antivirus, file type thực hoặc HTML nguy hiểm.
- Việc mở **part.getContent()** có thể phát sinh I/O và ngoại lệ.

Trong pipeline nhận thư từ nguồn bên ngoài, hãy áp dụng giới hạn kích thước trước/sau decode, timeout và resource budget cho parser.

## 33. Chọn text/plain hoặc text/html như thế nào?

Nếu có **multipart/alternative**, hai phần thường là các bản trình bày khác nhau của cùng một nội dung:

~~~text
multipart/alternative
  |
  +-- text/plain: "Đơn hàng ORD-100 đã giao"
  |
  +-- text/html: "<p>Đơn hàng ORD-100 đã giao</p>"
~~~

Không nên nối hai bản thành:

~~~text
Đơn hàng ORD-100 đã giao
Đơn hàng ORD-100 đã giao
~~~

vì sẽ tạo nội dung trùng lặp.

Chính sách có thể là:

- **Ưu tiên plain text** nếu chỉ cần phân loại/trích xuất đơn giản và nội dung đủ rõ.
- **Đọc HTML đã sanitize** khi plain text không có hoặc cần cấu trúc bảng/link.
- Lưu cả hai dạng nếu cần phục vụ người dùng hoặc audit.
- Tránh dùng regex đơn giản để “xóa tag HTML” cho những mẫu phức tạp; sử dụng HTML parser được cấu hình an toàn nếu thật sự cần.

Khi lấy text từ MIME, phải kiểm tra **Content-Disposition**: một attachment **text/plain** không nhất thiết là nội dung chính của email.

### Charset

Email có thể sử dụng UTF-8 hoặc các charset khác. Jakarta Mail thường giải mã nội dung text dựa trên MIME headers. Nếu header thiếu hoặc sai, phải có chính sách xử lý lỗi có kiểm soát; không âm thầm đổi mọi byte thành UTF-8 rồi làm hỏng nội dung tiếng Việt.

Giữ lại raw MIME hoặc checksum theo chính sách giúp đối chiếu khi parser xử lý sai charset.

## 34. Xử lý attachment và inline resource

Một attachment có thể được nhận diện qua:

- **Content-Disposition: attachment**.
- **Filename** trong Content-Disposition/Content-Type parameters.
- MIME type như **application/pdf**, **image/png**, **application/vnd...**.
- Ngữ cảnh của part trong multipart tree.

Inline resource thường có **Content-ID** và được HTML tham chiếu qua **cid:**, nhưng Content-Disposition có thể khác nhau theo producer.

Đừng chỉ kiểm tra:

~~~java
if (part.getFileName() != null) {
    // attachment
}
~~~

vì một tài nguyên inline cũng có thể có filename, và một attachment đôi khi thiếu tên.

### Đọc dữ liệu bằng InputStream

~~~java
import jakarta.mail.Part;
import java.io.InputStream;

public void copyAttachment(
        Part part,
        AttachmentObjectStorage storage,
        String tenantId
) throws Exception {

    try (InputStream input = part.getInputStream()) {
        storage.saveBounded(
                tenantId,
                input,
                part.getFileName(),
                part.getContentType()
        );
    }
}
~~~

**AttachmentObjectStorage** là interface minh họa do ứng dụng tự thiết kế. Phương thức **saveBounded** phải giới hạn số bytes, sanitize filename, không tin Content-Type do người gửi khai báo và ghi dữ liệu vào vùng lưu trữ có quyền tenant phù hợp.

Lưu attachment sau khi quét malware và xác định chính sách file được phép, hoặc lưu ở **quarantine storage** trước khi công bố cho downstream. Không tự động thực thi file, macro, script hoặc dùng filename làm đường dẫn filesystem.

## 35. Không tin MIME headers và địa chỉ From

Email là dữ liệu đến từ mạng bên ngoài. Những trường sau **không phải bằng chứng xác thực danh tính tuyệt đối**:

- **From**: có thể bị giả mạo.
- **Reply-To**: có thể dẫn tới địa chỉ khác domain.
- **Subject**: có thể chứa dữ liệu gây nhầm lẫn, thông tin cá nhân hoặc ký tự lạ.
- **Message-ID**: có thể bị thiếu hoặc cố tình tạo trùng.
- **Content-Type**: do người gửi khai báo, có thể không khớp bytes thực.
- **Filename**: có thể chứa path traversal, ký tự điều khiển hoặc extension đánh lừa.
- **Date**: do client gửi tạo ra, không nhất thiết là thời điểm mail server đã nhận.
- **X-... headers**: có thể tự tạo, không mặc nhiên đáng tin.

Ví dụ một email gửi từ:

~~~text
From: accounting@trusted-company.example
Reply-To: attacker@outside.example
Subject: Chuyển tiền gấp
~~~

Không được suy ra email đến từ phòng kế toán chỉ vì From hiển thị quen thuộc.

### Thông tin xác thực bổ trợ

Mail server có thể thêm **Authentication-Results** liên quan SPF, DKIM và DMARC. Những trường này hữu ích trong chính sách xử lý, nhưng ứng dụng cần biết **trust boundary**: header do sender tự thêm không được coi như kết quả xác minh từ mail infrastructure đáng tin cậy.

Với workflow nhạy cảm như duyệt thanh toán, thay đổi tài khoản hoặc kích hoạt quyền, **email inbound chỉ nên là tín hiệu khởi tạo**; tác vụ cần bước xác thực/ủy quyền độc lập.

## 36. HTML và attachment là dữ liệu không tin cậy

Những rủi ro thường gặp:

- HTML có liên kết phishing hoặc hình remote gây tracking.
- Script, form hoặc nội dung tương tác được lưu rồi render thiếu sanitize trong giao diện quản trị.
- ZIP archive có kích thước giải nén rất lớn.
- PDF/Office file có nội dung độc hại.
- Attachment filename chứa **../** hoặc ký tự gây thao tác nhầm filesystem.
- MIME tree sâu và số lượng part lớn gây tiêu thụ CPU/RAM.
- Text cực dài gây nghẽn parser/search index.
- Đường dẫn **cid:** hoặc URL remote bị trình bày/chuẩn hóa sai.

Một inbound service nên:

1. Giới hạn kích thước message trước khi tải nếu protocol/API cho phép.
2. Giới hạn số part, độ sâu MIME và tổng bytes sau decode.
3. Kiểm tra loại file dựa trên nhiều tín hiệu, không chỉ extension/Content-Type.
4. Quét malware hoặc đưa file vào quarantine theo chính sách.
5. Không tự tải URL remote khi parse HTML.
6. Sanitize HTML trước khi render trong web UI.
7. Lưu file với object key do hệ thống tạo, không lấy raw filename làm path.
8. Ghi checksum, nguồn và tenant scope để hỗ trợ audit.
9. Không đưa raw email/attachment vào log lỗi thông thường.

**Đọc email qua IMAP/POP3 không làm nội dung trở nên đáng tin cậy**. TLS chỉ bảo vệ kết nối tới mailbox server, không chứng minh mọi thư trong mailbox là an toàn hoặc hợp lệ.

## 37. Xử lý bounce/DSN khi nhận qua IMAP hoặc POP3

Một ứng dụng Spring Mail có thể gửi email qua SMTP rồi nhận **Delivery Status Notification (DSN)** trong mailbox dành cho bounce.

Ví dụ:

~~~text
Outbound:
  Spring -> SMTP provider
  MAIL FROM:<bounces@bounces.example.com>
  RCPT TO:<customer@recipient.example>

Later:
  Receiving server cannot deliver
       |
       v
  DSN -> bounces@bounces.example.com
       |
       v
  IMAP/POP3 inbound consumer
       |
       v
  DSN parser -> notification outcome
~~~

DSN có thể có cấu trúc:

~~~text
multipart/report; report-type=delivery-status
  |
  +-- text/plain
  +-- message/delivery-status
  +-- message/rfc822-headers (optional)
~~~

Trong phần **message/delivery-status** có thể xuất hiện:

~~~text
Final-Recipient: rfc822; customer@recipient.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

Không phải mọi DSN chứa đầy đủ các trường và không phải mọi lỗi chuyển phát đều tạo DSN. Provider có thể gửi **webhook** thay vì email bounce về mailbox.

### Các nguyên tắc xử lý bounce inbound

- Đối chiếu với **notification/recipient** bằng provider ID, VERP token hoặc metadata đáng tin cậy.
- Không suppress recipient chỉ vì text body chứa “User unknown”.
- Phân loại hard/soft/policy rejection theo enhanced status code và nguồn sự kiện.
- Bảo vệ chống backscatter và bounce giả mạo.
- Coi báo cáo DSN là nguồn bên ngoài; kiểm tra tính hợp lý trước khi cập nhật trạng thái.
- Giữ idempotency vì mail server hoặc poller có thể gửi lại cùng sự kiện.

Nếu ESP cung cấp webhook đáng tin cậy và đầy đủ, có thể không cần triển khai inbox IMAP/POP3 riêng để thu bounce. Lựa chọn dựa trên khả năng provider và yêu cầu lưu trữ/đối soát.

## 38. Xử lý phản hồi: In-Reply-To và References

Một bài toán nhận thư thường gặp là ghép phản hồi của người nhận với email đã gửi trước đó.

Ví dụ thư gốc:

~~~text
Message-ID: <ticket-123@support.example.com>
From: support@example.com
To: customer@example.net
Subject: [TICKET-123] Chúng tôi đã nhận yêu cầu
~~~

Email trả lời có thể chứa:

~~~text
From: customer@example.net
To: support@example.com
In-Reply-To: <ticket-123@support.example.com>
References: <ticket-123@support.example.com>
Subject: Re: [TICKET-123] Chúng tôi đã nhận yêu cầu
~~~

Ứng dụng có thể dùng **In-Reply-To** và **References** để hỗ trợ threading/correlation, nhưng:

- Những header có thể bị thiếu hoặc thay đổi bởi email client.
- Subject có thể bị sửa hoặc bị chuyển tiếp.
- Message-ID không phải bằng chứng identity đã được xác thực.
- Một cuộc hội thoại có thể chứa nhiều recipient, alias hoặc forwarder.

Nên có **ticket ID/opaque correlation token** và kiểm tra người gửi có quyền cập nhật ticket trước khi chấp nhận nội dung. Không tin chỉ một chuỗi trong Subject là đủ để ghi thông tin vào hồ sơ của người khác.

### Không dùng Message-ID làm khóa duy nhất toàn hệ thống

Nếu hai mailbox cùng nhận một message có cùng Message-ID, có thể đó là hai sự kiện inbound khác nhau theo tenant hoặc workflow. Identity ingestion nên giữ phạm vi mailbox; business correlation là bước xử lý phía sau.

## 39. IMAP flags, move và expunge

IMAP có thể hỗ trợ các hành động:

~~~text
INBOX / UID 400
   |
   +-- Set \\Seen
   |
   +-- Add keyword/flag (nếu server hỗ trợ)
   |
   +-- Copy/move to Processed
   |
   +-- Mark \\Deleted
   |
   +-- Expunge
~~~

Các thao tác này **thay đổi mailbox server**, có thể ảnh hưởng người dùng hoặc client khác. Vì vậy:

- Mặc định inbound automation nên dùng READ_ONLY nếu chỉ cần lấy nội dung.
- Nếu cần mark/move, phải có account/permission phù hợp.
- Chỉ thay trạng thái server sau khi thư đã được ghi nhận bền vững theo policy.
- Thư được move sang folder mới có thể thay UID/folder identity.
- Expunge có thể tác động tới nhiều thư đã được đánh dấu Deleted trong cùng folder.
- Tránh expunge toàn bộ folder trong một routine không hiểu trạng thái của client khác.

### Không biến mailbox thành database trạng thái duy nhất

IMAP flag hữu ích để phối hợp ở mức mail client, nhưng không đủ cho trạng thái nghiệp vụ phức tạp như “hóa đơn đã được xác minh”, “ticket đã được giao nhóm”, “document đang chờ retry”. Hãy quản lý những trạng thái đó trong database của ứng dụng.

## 40. Một mailbox, nhiều worker: xử lý cạnh tranh

Giả sử hai pod cùng poll một IMAP INBOX:

~~~text
Pod A: phát hiện UID 200
Pod B: phát hiện UID 200

Pod A: tạo ticket #101
Pod B: tạo ticket #102
~~~

Nếu không có unique key/claim, một email có thể tạo hai tác dụng phụ.

Các chiến lược:

**A. Một active mailbox poller**

- Một worker duy nhất đọc một mailbox tại một thời điểm.
- Có distributed lease/leader election khi chạy nhiều instance.
- Dễ bảo toàn ordering/checkpoint hơn.
- Cần failover nếu worker chết.

**B. Nhiều poller với dedup database**

- Nhiều worker có thể thấy cùng UID.
- Dùng unique key cho inbox và chỉ một worker được quyền ingest.
- Business workers đọc từ queue/outbox đã được dedup.
- Cần tránh gây quá nhiều kết nối mailbox.

**C. Sharding theo mailbox/tenant**

- Mailbox A do partition 1 xử lý, mailbox B do partition 2.
- Có thể mở rộng theo số mailbox mà không tranh chấp trong một folder.
- Cần quản lý phân phối lại khi instance scale.

Khi dùng **lease**, cần TTL, heartbeat và ownership/fencing token để một worker cũ không ghi đè checkpoint sau khi lease đã được chuyển sang worker mới.

**Không dùng flag Seen làm distributed lock**; hai client có thể cùng fetch trước khi một flag được cập nhật, và con người cũng có thể thay trạng thái thư.

## 41. Multi-tenant mailbox isolation

Trong SaaS, mỗi tenant có thể sở hữu mailbox tích hợp riêng:

~~~text
Tenant A -> support-a@tenant-a.example -> IMAPS account A
Tenant B -> support-b@tenant-b.example -> IMAPS account B
Tenant C -> invoices@tenant-c.example  -> POP3S account C
~~~

Cần cô lập:

| Thành phần | Quy tắc |
|---|---|
| Tenant identity | Được xác thực và lưu cùng mailbox configuration |
| Mailbox credential | Không dùng nhầm account/secret giữa tenant |
| Checkpoint | Khóa theo tenant + mailbox + folder + UIDVALIDITY/UID |
| Inbox record | Chỉ tenant tương ứng được truy cập |
| Attachment storage | Object key và quyền truy cập theo tenant |
| Parser policy | Giới hạn byte/file type theo chính sách tenant |
| Worker quota | Một tenant không chiếm hết kết nối/poll slots |
| Delivery/bounce events | Đối chiếu đúng tenant và notification gốc |
| Logs/metrics | Không lộ địa chỉ/Subject/Message-ID của tenant khác |

Khi nhiều mailbox dùng chung một provider, cần xem giới hạn **connections per account**, **request rate**, **API quota** hoặc những chính sách truy cập mà provider quy định.

Không nên tạo một IMAP IDLE connection cho từng folder của hàng chục nghìn tenant nếu hạ tầng/provider không hỗ trợ số lượng kết nối đó. Có thể phân nhóm, giảm concurrency, dùng polling cho mailbox ít traffic hoặc cơ chế webhook/API chính thức của provider khi khả dụng.

## 42. Chính sách xác thực: password, app password và OAuth2

Không phải mail provider nào cũng cho phép username/password truyền thống.

Các lựa chọn:

- **App password** được cấp cho ứng dụng khi provider hỗ trợ.
- **OAuth2 access token** với cơ chế SASL phù hợp, thường được gọi là **XOAUTH2** trong nhiều hệ thống mail.
- **Credential nội bộ** cho mail server thuộc tổ chức, với TLS và quyền tối thiểu.
- **Provider API** thay cho IMAP/POP3 nếu nhà cung cấp định hướng tích hợp theo API.

Không đồng nhất **“Spring có thuộc tính password”** với **“provider cho phép basic auth”**. Việc xác thực thực tế phụ thuộc server và policy tenant.

### OAuth2 cần nhiều hơn một chuỗi token

Nếu dùng access token:

1. Cần scope/permission phù hợp cho đọc mailbox.
2. Cần cơ chế cấp và làm mới token trước khi hết hạn.
3. Cần lưu token/refresh token trong secret storage được bảo vệ.
4. Cần truyền token qua SASL mechanism mà provider/Jakarta Mail implementation hỗ trợ.
5. Cần xử lý lỗi token revoked, tenant disconnect hoặc administrator thay đổi quyền.
6. Cần tránh log SASL exchange và token.

Không đặt access token vào URL mailbox hoặc log exception. Khi server trả authentication failed, không nên retry liên tục với một token đã hết hạn mà không thực hiện refresh hoặc xác minh quyền.

## 43. TLS và xác minh máy chủ inbound

TLS bảo vệ kết nối từ ứng dụng tới IMAP/POP3 server, gồm credential và nội dung email được tải. Cấu hình cần quan tâm:

- Hostname chính thức của provider.
- Port và chế độ TLS đúng.
- Certificate chain do CA được tin cậy ký.
- Hostname verification với chứng chỉ server.
- Protocol versions/ciphers được tổ chức cho phép.
- Connect/read/write timeouts hữu hạn.
- Truststore của JDK/container.

Ví dụ IMAPS:

~~~properties
mail.imaps.connectiontimeout=5000
mail.imaps.timeout=10000
mail.imaps.writetimeout=10000
mail.imaps.ssl.checkserveridentity=true
~~~

Ví dụ POP3S:

~~~properties
mail.pop3s.connectiontimeout=5000
mail.pop3s.timeout=10000
mail.pop3s.writetimeout=10000
mail.pop3s.ssl.checkserveridentity=true
~~~

Các giá trị thời gian tính theo mili giây và chỉ mang tính ví dụ. Khi dùng **getStore("imap")** với STARTTLS hoặc **getStore("pop3")** với STLS, prefix sẽ tương ứng là **mail.imap** hoặc **mail.pop3**.

### Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể |
|---|---|
| Connection refused | Host/port sai, listener không chạy, firewall |
| Connect timeout | Route/egress/network/provider outage |
| SSLHandshakeException | Sai TLS mode, CA, hostname hoặc protocol |
| PKIX path building failed | Truststore không tin cậy chain server |
| AuthenticationFailedException | Credential/token/scope/account policy |
| Read timeout | Server hoặc mạng chậm, kết nối treo |
| Folder not found | Tên folder hoặc quyền truy cập sai |
| Folder closed | Session bị ngắt hoặc object được dùng sau khi đóng |

Không tắt TLS để vượt qua AuthenticationFailedException. Nếu certificate lỗi, phải sửa trust chain/hostname hoặc endpoint, không cấu hình tin mọi chứng chỉ.

## 44. Giới hạn polling và đọc dữ liệu hiệu quả

Một mailbox nhiều năm có thể chứa hàng triệu message. Nếu mỗi lần chạy đều:

~~~java
Message[] all = inbox.getMessages();

for (Message message : all) {
    // Đọc toàn bộ body và attachment...
}
~~~

ứng dụng có thể gặp:

- Tốn bộ nhớ giữ danh sách message/object.
- Nhiều lượt round-trip IMAP để lấy headers.
- Băng thông lớn khi fetch attachment không cần thiết.
- Thời gian mở folder quá lâu.
- Quota requests bị provider giới hạn.
- Worker không kịp nhận thư mới vì quét lại thư cũ.

Thiết kế hiệu quả:

1. Dùng checkpoint UID/UIDL để tránh quét toàn bộ mailbox.
2. Xác định **batch size** theo số message hoặc tổng bytes.
3. Trước tiên fetch **metadata/header** và chỉ tải full MIME khi cần.
4. Dùng **FetchProfile** phù hợp để giảm số round-trip khi provider hỗ trợ.
5. Giới hạn số mailbox/folder poll đồng thời.
6. Không giữ database transaction trong lúc chờ IMAP/POP3.
7. Có timeout và chính sách reconnect.
8. Đo queue latency và mailbox scan duration để biết tầng nào đang nghẽn.

### Ví dụ FetchProfile

~~~java
import jakarta.mail.FetchProfile;
import jakarta.mail.Folder;
import jakarta.mail.Message;

FetchProfile profile = new FetchProfile();
profile.add(FetchProfile.Item.ENVELOPE);
profile.add(FetchProfile.Item.FLAGS);

Message[] batch = inbox.getMessages(start, end);
inbox.fetch(batch, profile);

for (Message message : batch) {
    // Đọc các metadata phù hợp, không nhất thiết tải attachment.
}
~~~

Đoạn code giả định **inbox** đã mở và **start/end** đã được kiểm tra nằm trong phạm vi message sequence hợp lệ. Đây là một cách tối ưu fetch metadata, không tự giải quyết checkpoint hoặc exactly-once.

Với IMAP, có thể dùng UID range và FetchProfile phù hợp, nhưng khả năng tối ưu phụ thuộc server/provider; phải đo thực tế trước khi giả định một batch FETCH luôn nhanh hơn.

## 45. Retry, dead-letter và quarantine

Không phải lỗi nào cũng nên retry giống nhau:

| Lỗi | Hướng xử lý thường phù hợp |
|---|---|
| DNS/network timeout tạm thời | Retry connection có backoff |
| IMAP/POP3 server đóng session | Reconnect rồi đồng bộ lại từ checkpoint |
| Credential/token hết hạn | Refresh/re-authorize, tránh retry nóng |
| Folder không tồn tại | Cảnh báo cấu hình; tạm dừng poll folder đó |
| MIME malformed | Quarantine và lưu diagnostic metadata |
| Email vượt size policy | Quarantine/reject theo chính sách |
| Attachment độc hại | Quarantine, không đưa tới business worker |
| Database tạm thời unavailable | Không mark/delete; retry persist inbox |
| Business API downstream lỗi | Retry từ inbox database, không cần fetch lại email |
| Sender identity không đáng tin | Chuyển sang kiểm tra/quarantine thay vì thực thi lệnh |

### Vì sao phải có dead-letter/quarantine?

Nếu một email malformed luôn khiến poller ném exception, toàn bộ mailbox có thể bị kẹt ở cùng message và không tới những thư sau.

Một phương án:

~~~text
Fetch UID 100 -> OK -> PERSISTED
Fetch UID 101 -> MIME malformed
    |
    +-- Lưu identity và lỗi vào quarantine record
    +-- Lưu raw MIME nếu cho phép và trong giới hạn
    +-- Đánh dấu cần điều tra
    |
Fetch UID 102 -> OK -> PERSISTED
~~~

Với thiết kế này, việc **bỏ qua UID 101 trong lần poll kế tiếp** chỉ an toàn nếu ứng dụng đã giữ được thông tin xử lý/quarantine bền vững. Không chỉ catch exception rồi update lastUID qua 101 mà không lưu dấu vết.

### Retry không đồng nghĩa tải lại từ server

Nếu raw EML đã được persist, business retry nên xử lý từ bản lưu. Điều này giảm tải mail server và tránh trường hợp thư bị xóa khỏi mailbox giữa các lần thử.

## 46. Quan sát và cảnh báo inbound mail

Một pipeline nhận email cần metrics khác với pipeline gửi:

| Metric logic | Ý nghĩa |
|---|---|
| **mail_inbound_poll_total** | Số poll attempts theo account/protocol/result |
| **mail_inbound_poll_duration** | Thời gian một lần poll |
| **mail_inbound_discovered_total** | Số message identity được phát hiện |
| **mail_inbound_persisted_total** | Số unique inbox item lưu thành công |
| **mail_inbound_duplicate_total** | Số message đã có trong inbox store |
| **mail_inbound_parse_failed_total** | Số message lỗi parse |
| **mail_inbound_quarantined_total** | Số message vào quarantine |
| **mail_inbound_processing_failed_total** | Lỗi xử lý nghiệp vụ |
| **mail_inbound_checkpoint_lag** | Độ trễ/UID lag theo cách đã định nghĩa |
| **mail_inbound_queue_oldest_age_seconds** | Tuổi item chưa xử lý lâu nhất |
| **mail_inbound_connection_failures_total** | Lỗi DNS/TCP/TLS/AUTH |

Một số metric nên được tách theo **protocol=imap|pop3**, **result** và **error_category**.

**Không đưa địa chỉ email, Subject, raw Message-ID hoặc UID riêng của từng thư vào Prometheus label** nếu chúng tạo nhiều time series hoặc chứa PII. Với tenant/account lớn, cân nhắc chỉ dùng một **mailbox group/tier** hữu hạn ở metrics, còn chi tiết tra cứu nằm trong database/log có quyền.

### Ba nhóm cảnh báo hữu ích

**A. Không nhận email mới khi dự kiến có traffic.**

Không dựa duy nhất vào “0 mail trong 10 phút”, vì mailbox có thể thật sự không có thư. Nên có heartbeat/poll liveness và đối chiếu với tín hiệu upstream khi có.

**B. Inbox backlog/oldest age tăng.**

Message đã persist nhưng business worker không xử lý kịp, hoặc poller còn kết nối nhưng chưa lưu được.

**C. Lỗi AUTH/TLS/parse tăng.**

Phân loại riêng lỗi cấu hình account, lỗi mail server và dữ liệu email không hợp lệ.

Nếu IMAP IDLE bị ngắt kết nối liên tục, giám sát reconnect count và thời gian không có sync thành công, không chỉ số notification nhận được.

## 47. Runbook khi ứng dụng không nhận được thư

Một quy trình chẩn đoán có thể theo thứ tự:

1. **Có email thật trong mailbox không?** Xác minh bằng một client/admin console được phép.
2. **Đúng account/folder chưa?** INBOX có thể khác với folder mà thư được tự động lọc vào.
3. **DNS và TCP tới host:port** từ chính container/VM chạy ứng dụng có hoạt động không?
4. **TLS mode đúng chưa?** IMAPS 993/POP3S 995 hoặc STARTTLS/STLS theo provider.
5. **Credential/token và scope** còn hiệu lực không?
6. **Quota/rate/concurrent connections** của provider có bị vượt không?
7. **Poller/IDLE listener** có chạy, còn connection và reconnect được không?
8. **UIDVALIDITY/UIDL checkpoint** có hợp lệ hay bị stale?
9. **Search filter/Seen logic** có vô tình loại bỏ thư không?
10. **Inbox persistence** có ghi được, hay DB/object storage đang lỗi?
11. **Worker processing** có bị queue backlog hoặc dead-letter không?
12. **Log/metric** có cho thấy message đã được nhận nhưng đang QUARANTINED không?

Nếu server trả “folder not found”, tăng network timeout thường không có tác dụng. Nếu mailbox có thư nhưng checkpoint UID vượt quá UID hiện tại do UIDVALIDITY đổi, cần đồng bộ lại thay vì xóa dữ liệu ngẫu nhiên.

### Runbook khi nhận trùng

Kiểm tra:

- Cùng email được fetch lại sau restart/reconnect?
- Có nhiều active poller dùng chung mailbox?
- Inbox unique key bao gồm account/folder/UIDVALIDITY đúng không?
- POP3 UIDL có ổn định không?
- Một thư được copy/move sang folder mới và được xử lý lần nữa?
- Event/attachment/business action có idempotency key riêng không?
- Thông điệp thực sự là hai email giống nhau do người gửi gửi lặp?

Không “sửa” vấn đề nhận trùng bằng cách xóa toàn bộ email đã đọc nếu doanh nghiệp còn cần lưu giữ hoặc đối soát.

## 48. Kiểm thử IMAP/POP3 bằng mail server kiểm thử

Trong Spring, một hướng kiểm thử integration là khởi động một **SMTP + IMAP/POP3 test server** (ví dụ một phiên bản GreenMail tương thích Jakarta Mail) rồi:

~~~text
JUnit / Testcontainers
        |
        +-- Start test SMTP + IMAP/POP3 server
        |
        +-- Submit test email vào mailbox
        |
        +-- Call inbound poller/receiver
        |
        +-- Assert inbox DB / captured payload
        |
        +-- Assert attachment/text extraction
        |
        +-- Simulate reconnect/restart and poll again
        |
        +-- Assert no duplicate business action
        |
        +-- Stop test server and clean resources
~~~

Các trường hợp test nên có:

| Trường hợp | Kết quả kỳ vọng |
|---|---|
| INBOX rỗng | Poll không lỗi và không tạo inbox item |
| Một text/plain mail | Đọc subject/from/body đúng |
| Multipart alternative | Chọn plain text/HTML theo policy |
| HTML + CID image + PDF | Phân loại inline/attachment đúng |
| Hai poll liên tiếp cùng mailbox | Không tạo duplicate inbox/business record |
| Process crash sau DB commit | Poll lại nhưng dedup thành công |
| Process crash trước DB commit | Message được phát hiện/lưu lại |
| UIDVALIDITY đổi | Không dùng nhầm UID checkpoint cũ |
| POP3 UIDL tồn tại | Identifies message qua các phiên |
| Server disconnect giữa fetch | Retry/reconnect không đánh dấu sai |
| MIME malformed | Quarantine, không chặn thư phía sau |
| Attachment vượt size | Bị chặn/quarantine theo policy |
| Thư From giả mạo | Không thực thi tác vụ nhạy cảm chỉ dựa vào header |
| Hai mailbox tenant khác nhau | Không trộn nội dung/checkpoint |
| IMAP Seen bị client khác thay đổi | App vẫn dựa vào checkpoint riêng |
| Auth/TLS sai | Không fallback plaintext hoặc ghi secret vào log |

Không gửi email thử đến người dùng thật. Dùng tài khoản và domain thử nghiệm; cấu hình server cục bộ, port động hoặc container isolation để tránh test chạy song song giẫm lên nhau.

### Tại sao unit test với mock chưa đủ?

Unit test có thể chứng minh service gọi receiver hoặc parser, nhưng không chứng minh:

- IMAP/POP3 server trả message như dự kiến.
- UID/UIDVALIDITY/UIDL được đọc đúng từ server.
- Flags và delete semantics hoạt động đúng.
- Reconnect/timeout và session lifecycle được xử lý.
- MIME đã qua transport được parser đọc đúng.

Hãy dùng **unit test cho policy** và **integration test cho protocol/storage behavior**. Không nhất thiết chạy toàn bộ suite qua mail server ngoài Internet.

## 49. Ba kiến trúc tham khảo theo bài toán

### A. Hộp thư support: IMAP và ticket processing

~~~text
Customer replies
       |
       v
support@company.example
       |
       v
IMAP (IDLE + periodic UID reconciliation)
       |
       v
Inbox DB / raw EML archive
       |
       v
Ticket correlation & authorization
       |
       v
Ticket event + attachment scan
       |
       v
Agent UI
~~~

Lý do chọn IMAP:

- Nhiều agent có thể cần xem mailbox trên server.
- Có folder và flags để thao tác mail.
- IDLE giúp giảm độ trễ, nhưng periodic UID reconciliation bảo vệ khi mất kết nối.
- UID+UIDVALIDITY dùng để dedup ingestion.

Điểm cần chú ý: **không dùng Seen làm trạng thái ticket đã hoàn tất**, không tin From để cho phép bất kỳ ai sửa ticket và không tự render HTML thiếu sanitize trong giao diện agent.

### B. Hộp thư chỉ thu tài liệu: POP3 và document archive

~~~text
Partner sends invoices
        |
        v
inbound-invoices@company.example
        |
        v
POP3S scheduled retrieval
        |
        v
UIDL dedup + durable EML storage
        |
        v
Attachment quarantine / antivirus
        |
        v
Document recognition
        |
        v
Review + accounting system
~~~

Lý do POP3 có thể đủ:

- Chỉ một integration consumer.
- Không cần nhiều folder hoặc trạng thái Seen.
- Sau khi tải, ứng dụng có kho dữ liệu riêng làm nguồn sự thật.

Điểm cần chú ý: nếu không có UIDL ổn định, cần fingerprint/dedup phù hợp; không xóa thư trên server trước khi lưu bền vững.

### C. Hộp thư nhận bounce: IMAP hoặc POP3 chỉ là cổng ingestion

~~~text
SMTP MAIL FROM -> bounce mailbox
              |
              v
       IMAP/POP3 fetch
              |
              v
       DSN MIME parser
              |
              v
  Validate + correlate notification
              |
              v
      Delivery state / suppression
~~~

Lý do không cố chọn giao thức phức tạp hơn:

- Giá trị chính nằm ở **đọc DSN chính xác, xác minh nguồn và correlation**, không nằm ở thao tác folder.
- Nếu nhà cung cấp có webhook authenticated, có thể chọn webhook thay vì xây receiver cho một bounce mailbox.

## 50. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Spring Mail có JavaMailReceiver mặc định như JavaMailSender” | Nhận thư thường dùng Jakarta Mail hoặc Spring Integration Mail |
| “SMTP cũng là giao thức đọc Inbox” | SMTP để gửi/chuyển tiếp; IMAP/POP3 để truy cập mailbox |
| “IMAP luôn push, POP3 luôn poll” | IMAP cũng có polling; IDLE chỉ là cơ chế báo thay đổi |
| “IMAP IDLE đảm bảo không bỏ sót mail” | Cần reconnect và UID reconciliation sau gián đoạn |
| “Sequence number là message ID bền vững” | Nó có thể đổi sau expunge; dùng UID+UIDVALIDITY |
| “UID đơn lẻ là duy nhất toàn hệ thống” | UID có scope theo folder/mailbox và UIDVALIDITY |
| “Một thư Seen nghĩa là nghiệp vụ đã xử lý” | Seen là flag mailbox, không phải DB transaction |
| “POP3 luôn xóa email khi tải” | Xóa phụ thuộc lệnh, client và chính sách session |
| “POP3 message number là khóa ổn định” | Thứ tự có thể đổi; dùng UIDL khi hỗ trợ |
| “Message-ID header không thể giả hoặc trùng” | Nó có thể thiếu, bị giả hoặc không unique |
| “Đã lưu UID là exactly-once” | Còn crash, duplicate worker và side effect nghiệp vụ |
| “Một email chỉ có một String body” | Nó có thể là nested multipart/alternative/related/mixed |
| “MIME Content-Type luôn phản ánh bytes thật” | Header do người gửi khai báo, có thể sai |
| “Bản plain text và HTML phải nối lại” | Trong alternative, đó là các bản trình bày thay thế |
| “From chứng minh người gửi đáng tin” | From có thể bị giả; cần chính sách xác thực độc lập |
| “TLS bảo đảm email bên trong an toàn” | TLS bảo vệ chặng kết nối, không kiểm tra malware/phishing |
| “Đã fetch thì nên mark Seen/delete ngay” | Chỉ nên thay server state sau khi persist theo chính sách |
| “Một mailbox nhiều pod tự chia việc” | Có thể đọc trùng; cần lease/dedup/sharding |
| “Tăng polling rate luôn cải thiện throughput” | Có thể tăng provider throttling và chi phí |
| “Mock receiver đủ cho integration” | Không kiểm tra protocol, UID, session, flags và parser thật |
| “Không có mail mới nghĩa là poller khỏe” | Poller có thể ngừng hoạt động; cần heartbeat và liveness |

## 51. Checklist triển khai inbound email trong Spring

**Chọn giao thức và provider**

1. Mailbox cần folder, flags, search và nhiều client không?
2. Có cần latency gần thời gian thực hay polling vài phút là đủ?
3. Provider hỗ trợ IMAP/POP3, IDLE hoặc webhook/API không?
4. Có giới hạn kết nối, quota và policy xác thực nào?
5. Chế độ TLS, hostname verification và credential rotation đã được xác định chưa?

**Nhận diện và lưu trữ**

6. Có định danh mailbox/account và tenant đáng tin cậy không?
7. Với IMAP, checkpoint gồm **folder + UIDVALIDITY + UID** chưa?
8. Với POP3, UIDL có được hỗ trợ và kiểm tra ổn định không?
9. Có unique key chống ingest trùng không?
10. Có lưu message hoặc raw EML bền vững trước khi mark/delete không?
11. Có tách discovery/persistence khỏi business processing không?
12. Có retry, quarantine và dead-letter theo từng message không?

**MIME và bảo mật**

13. Parser có xử lý multipart, charset, text alternative và attachment không?
14. Có giới hạn kích thước, depth, số part và bytes sau decode không?
15. HTML có được sanitize trước khi render không?
16. Attachment có được kiểm tra file type và malware theo policy không?
17. From, Reply-To, Message-ID có bị coi nhầm là bằng chứng identity không?
18. Có tenant-level authorization cho mailbox, storage và business event không?
19. Không ghi credential/raw MIME/PII vào log hoặc metric labels chứ?

**Hiệu năng và phục hồi**

20. Có batch limit và FetchProfile hợp lý không?
21. Có xử lý server disconnect/reconnect và UID reconciliation không?
22. Có giới hạn concurrent polling/IDLE connections không?
23. Có chống duplicate khi nhiều instance cùng chạy không?
24. Có đo mailbox lag, inbox backlog và poll failures không?
25. Khi worker/DB chết giữa fetch và persist, thư có được xử lý lại an toàn không?
26. Khi server-side flag/folder thay đổi, checkpoint còn đúng không?
27. Đã kiểm thử việc mailbox được migrate khiến UIDVALIDITY thay đổi chưa?

**Vận hành**

28. Có runbook riêng cho auth/TLS, folder missing, malformed MIME và server outage không?
29. Có chính sách retention/xóa thư được phê duyệt không?
30. Có kiểm thử integration bằng server mail thử nghiệm, không dùng mailbox production không?

Checklist này không phải yêu cầu triển khai toàn bộ tính năng vào một ứng dụng nhỏ. Nó giúp xác định **ranh giới bảo đảm** trước khi vận hành một pipeline nhận thư có tác động tới dữ liệu nghiệp vụ.

## 52. Ghi nhớ

**IMAP và POP3** đều cho phép ứng dụng truy cập email đã nằm trên mail server, nhưng phục vụ các mô hình khác nhau.

- **IMAP** phù hợp khi cần quản lý mailbox trên server, folder, flags, UID và có thể nhận tín hiệu gần thời gian thực qua IDLE. Checkpoint cần gắn với **UIDVALIDITY**, và việc đọc Seen flag không thay thế trạng thái xử lý nghiệp vụ.
- **POP3** phù hợp với luồng tải thư đơn giản từ một maildrop để ứng dụng lưu và xử lý riêng. Dùng **UIDL** khi server/provider hỗ trợ; không dùng số thứ tự message làm định danh bền vững. Việc xóa trên server phải có chính sách rõ ràng.
- Trong **Spring Framework Mail**, **JavaMailSender** phục vụ gửi SMTP. Để nhận mail có thể dùng **Jakarta Mail Session/Store/Folder/Message** trực tiếp hoặc **Spring Integration Mail** với inbound adapter và polling/IDLE flow.
- **IMAP IDLE và polling đều cần đồng bộ bù** sau lỗi mạng/restart. Không dựa vào một event hoặc flag để khẳng định thư đã được xử lý.
- Một kiến trúc tin cậy nên **ingest at-least-once, persist inbox bền vững, chống trùng bằng identity phù hợp và xử lý nghiệp vụ idempotent**.
- **MIME, HTML và attachment là dữ liệu không tin cậy**. Cần giới hạn dung lượng, depth, sanitize, scan file và giữ tenant authorization.
- Theo dõi **poll liveness, UID/checkpoint lag, duplicate count, parse failures, quarantine và processing backlog**, không chỉ số thư nhận được.

**Bản chất của bài toán nhận email không chỉ là “đọc được một Message từ INBOX”, mà là đưa dữ liệu từ mail server vào hệ thống Spring một cách đúng trạng thái, không mất thư, kiểm soát được trùng lặp và không để nội dung bên ngoài vượt qua ranh giới bảo mật.**






