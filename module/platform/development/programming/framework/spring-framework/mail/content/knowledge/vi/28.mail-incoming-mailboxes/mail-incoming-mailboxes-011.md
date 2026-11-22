# Xử lý lỗi kết nối khi nhận thư

## 1. Bối cảnh: nhận email khác với gửi email trong Spring

Trong hệ thống sử dụng **Spring Framework Mail**, việc gửi thư thường dùng `JavaMailSender` và SMTP. Nhưng khi ứng dụng cần **nhận thư** — ví dụ đọc hộp thư hỗ trợ khách hàng, lấy hóa đơn gửi tới một địa chỉ chuyên dụng, xử lý yêu cầu đến từ email, hoặc thu thập phản hồi từ một mailbox — bài toán chuyển sang các giao thức như **IMAP** hoặc **POP3**.

Một dịch vụ nhận thư không chỉ gọi API lấy message rồi kết thúc. Nó phải đối mặt với kết nối TCP/TLS bị đứt, mailbox server khởi động lại, token xác thực hết hạn, folder bị đóng, lệnh IMAP timeout, provider giới hạn kết nối và những email được xử lý dở trước khi worker crash.

Nếu không thiết kế phục hồi:

- Worker ngừng nhận thư vĩnh viễn sau một lần mất mạng.
- Scheduler lặp retry liên tục gây tăng tải lên mailbox server.
- Email bị xử lý trùng sau khi kết nối lại.
- Ứng dụng bỏ sót email khi chỉ nhớ chỉ số thứ tự message.
- Một email lỗi khiến toàn bộ batch không thể tiến lên.
- Credential, địa chỉ người nhận và nội dung thư bị in vào log lúc debug.
- Mở quá nhiều kết nối IMAP/POP3 dẫn đến giới hạn của nhà cung cấp.

**Mục tiêu của bài học:** phân loại đúng lỗi kết nối khi đọc mailbox; thiết lập TLS và timeout; phục hồi `Store`/`Folder` an toàn; retry có backoff và jitter; checkpoint theo UID và xử lý idempotent; kiểm thử bằng fake/mocked server; theo dõi để biết worker thật sự đang nhận thư trở lại.

~~~text
Mailbox provider (IMAP / POP3)
             |
             v
       TLS + AUTH + TCP
             |
             v
   Jakarta Mail Store / Folder
             |
             v
      Poller / Mail Receiver
             |
             +----> Retry/reconnect policy
             |
             v
     Message normalization
             |
             v
     Durable processing state
             |
             v
   Business handler / attachment
~~~

## 2. Công cụ nào phụ trách nhận thư?

Phân biệt rõ các thành phần:

| Thành phần | Vai trò | Dùng để nhận email? |
|---|---|---|
| `JavaMailSender` của Spring Mail | Tạo và submit email qua SMTP | Không phải inbound receiver |
| Jakarta Mail `Session` | Chứa cấu hình protocol, tạo `Store` | Có |
| Jakarta Mail `Store` | Xác thực và quản lý kết nối tới mailbox | Có |
| Jakarta Mail `Folder` | Mở inbox, lấy `Message` và flags | Có |
| Jakarta Mail `UIDFolder` | Đọc UID và UIDVALIDITY trên server hỗ trợ | Có, đặc biệt hữu ích với IMAP |
| Spring Integration Mail | Polling/receiving adapters và integration flow | Có, nếu dự án dùng Spring Integration |
| Spring `@Scheduled` | Kích hoạt poller theo lịch | Có thể dùng để tổ chức việc nhận |
| SMTP server | Nhận thư để chuyển đi/gửi tới đích | Không thay thế IMAP/POP3 mailbox reader |

**Không có `JavaMailReceiver` tương đương trực tiếp với `JavaMailSender` trong Spring Framework Mail core**. Để đọc hộp thư có thể dùng **Jakarta Mail** hoặc tích hợp qua **Spring Integration Mail**. Đừng cố gọi `mailSender.send(...)` để “lấy thư”.

Với Spring Boot 3 / Spring Framework 6+, các ví dụ thường dùng namespace `jakarta.mail.*`. Dự án cũ thuộc Spring Framework 5 có thể dùng `javax.mail.*`; cần chọn dependency phù hợp, không trộn hai hệ package.

## 3. IMAP và POP3 có điểm khác biệt ảnh hưởng phục hồi

| Khía cạnh | IMAP | POP3 |
|---|---|---|
| Mục tiêu | Làm việc với mailbox/folder trên server | Thường tải thư từ một hộp thư |
| Folder | Nhiều folder và flags | Không cung cấp folder hierarchy như IMAP |
| Dấu đọc/chưa đọc | `\\Seen` và flags trên server | Không có mô hình tương đương đầy đủ |
| Định danh bền vững | UID trong phạm vi mailbox và UIDVALIDITY | UIDL nếu server hỗ trợ |
| Đồng bộ nhiều thiết bị | Phù hợp hơn | Hạn chế hơn |
| Cách đọc an toàn | Mở `READ_ONLY`, checkpoint UID | Tải thư, giữ UIDL và kiểm soát xóa |
| Kết nối dài hạn | Có thể duy trì nhưng dễ gặp idle timeout | Thường kết nối ngắn cho mỗi phiên lấy thư |

Trong ví dụ của bài, **IMAP** là lựa chọn chính vì hỗ trợ UID và folder. POP3 được thảo luận riêng khi khác biệt về UIDL, xóa thư và khả năng phục hồi.

### Cổng TLS thường gặp

| Giao thức | Cổng phổ biến | Cơ chế |
|---|---|---|
| IMAPS | 993 | TLS ngay từ khi kết nối (implicit TLS) |
| IMAP | 143 | Plain connection có thể nâng cấp qua STARTTLS |
| POP3S | 995 | TLS ngay từ khi kết nối |
| POP3 | 110 | Plain connection có thể nâng cấp qua STLS |

Đây là các cổng quy ước phổ biến; dịch vụ doanh nghiệp có thể sử dụng cổng hoặc endpoint riêng. **Không tự động tắt TLS để “khắc phục” timeout hoặc lỗi chứng chỉ.** Hãy xác minh host, port, cách bắt tay TLS và server certificate phù hợp với provider.

## 4. Một lỗi nhận thư có thể xảy ra tại nhiều giai đoạn

~~~mermaid
flowchart TD
    A[Bắt đầu polling] --> B[DNS và TCP connection]
    B --> C{Kết nối thành công?}
    C -- Không --> D[DNS / firewall / network / connect timeout]
    C -- Có --> E[TLS handshake]
    E --> F{TLS hợp lệ?}
    F -- Không --> G[Certificate / hostname / protocol]
    F -- Có --> H[Authentication]
    H --> I{Đăng nhập thành công?}
    I -- Không --> J[Credential / OAuth scope / policy]
    I -- Có --> K[Select/open mailbox folder]
    K --> L{Folder mở được?}
    L -- Không --> M[Folder permission / state / server BYE]
    L -- Có --> N[Fetch messages / bodies]
    N --> O{Read thành công?}
    O -- Không --> P[Read timeout / closed folder / malformed MIME]
    O -- Có --> Q[Process + checkpoint]
~~~

Đừng gọi mọi exception là “SMTP lỗi” hoặc “sai password”. Mỗi giai đoạn có cách xử lý khác nhau:

| Giai đoạn | Dấu hiệu | Hướng xử lý |
|---|---|---|
| DNS | Không phân giải được host | Kiểm tra tên host, resolver và mạng |
| TCP connect | Connection refused/timed out | Kiểm tra endpoint, port, firewall, egress |
| TLS | `SSLHandshakeException` | Xem trust chain, hostname và TLS policy |
| Auth | `AuthenticationFailedException` | Kiểm tra credential/token/quyền account |
| Open folder | `FolderNotFoundException`, permission denied | Kiểm tra folder name và grants |
| Fetch | `FolderClosedException`, `StoreClosedException`, timeout | Đóng session cũ và kết nối lại |
| Parse/process | `MessagingException`, I/O hoặc business error | Phân biệt lỗi message với lỗi transport |
| Checkpoint | Database/network error | Không đánh dấu thành công nếu chưa durable |

Một vài lỗi có thể chỉ lộ dưới dạng `MessagingException` chứa nested cause. Ví dụ timeout socket có thể nằm trong chuỗi nguyên nhân thay vì là exception được ném trực tiếp.

## 5. Phân loại lỗi để chọn retry đúng

Nên chia thành ít nhất bốn nhóm:

1. **Transient connectivity:** DNS tạm lỗi, mạng chập chờn, server restart, connection timeout. Có thể retry có giới hạn và backoff.
2. **Authentication/authorization:** password sai, token hết hạn, mailbox access bị thu hồi. Không retry dồn dập cùng credential lỗi; token hết hạn có thể kích hoạt refresh đúng cách.
3. **TLS/security/configuration:** hostname/certificate sai, TLS policy không tương thích, folder không được phép. Thường cần sửa cấu hình hoặc quyền; không “fix” bằng trust all.
4. **Data/processing:** email malformed, attachment lỗi, database down. Không mặc định reconnect mail server nếu nguyên nhân nằm ở xử lý message.

Ví dụ phân loại:

~~~text
TRANSIENT_NETWORK       -> reconnect sau backoff
SERVER_THROTTLED        -> provider-specific cooldown
AUTHENTICATION_FAILED   -> refresh once if supported / pause + alert
TLS_OR_TRUST_FAILURE    -> pause + remediation
FOLDER_PERMISSION       -> pause mailbox / review ACL
MESSAGE_PROCESSING      -> quarantine/retry riêng message
CHECKPOINT_UNAVAILABLE  -> retain state / retry durable commit
UNKNOWN                 -> limited retry, no tight loop
~~~

Phân loại phải dựa trên **kiểu exception, cause chain và protocol status** đáng tin cậy, không dựa chỉ vào chuỗi `contains("timeout")` trong message. Provider có thể thay đổi thông báo lỗi và những message đó còn có thể chứa thông tin nhạy cảm.

## 6. Timeout phải có trên cả kết nối và thao tác đọc

Nếu không cấu hình timeout, một polling job có thể bị treo lâu tại bước kết nối, chờ response hoặc write operation. Khi đó:

- Thread scheduler/executor bị giữ.
- Claim/lease mailbox có thể hết hạn.
- Những đợt polling sau chồng lên nhau hoặc bị trễ.
- Hệ thống khó phân biệt “đang đọc” với “đã chết”.

Các timeout quan trọng trong Jakarta Mail provider implementation:

| Property | Ý nghĩa thường gặp |
|---|---|
| `mail.imaps.connectiontimeout` | Thời gian chờ thiết lập TCP connection |
| `mail.imaps.timeout` | Socket read timeout |
| `mail.imaps.writetimeout` | Socket write timeout |
| `mail.imaps.ssl.checkserveridentity` | Bật kiểm tra hostname TLS |
| `mail.imaps.ssl.trust` | Trust tùy biến; không dùng `*` để bỏ xác minh |

Tên property có **prefix theo protocol thực tế**: `mail.imaps.*` khi `getStore("imaps")`, `mail.imap.*` khi `getStore("imap")`; POP3/POP3S có `mail.pop3.*` và `mail.pop3s.*`. Một property đặt nhầm prefix có thể không tác dụng.

Ví dụ dùng IMAPS với cổng 993:

~~~java
import jakarta.mail.Session;
import java.util.Properties;

public final class InboundMailSessionFactory {
    public Session newImapsSession() {
        Properties properties = new Properties();
        properties.put("mail.store.protocol", "imaps");
        properties.put("mail.imaps.connectiontimeout", "5000");
        properties.put("mail.imaps.timeout", "15000");
        properties.put("mail.imaps.writetimeout", "15000");
        properties.put("mail.imaps.ssl.checkserveridentity", "true");
        properties.put("mail.debug", "false");
        return Session.getInstance(properties);
    }
}
~~~

Các giá trị tính bằng mili-giây là **ví dụ vận hành**, không phải quy tắc cho mọi server. Chọn timeout theo latency mạng, kích thước message, khả năng provider và SLA; mailbox có attachment lớn có thể cần read timeout khác.

## 7. IMAPS và STARTTLS: cấu hình đúng loại kết nối

Hai mô hình bảo vệ đường truyền phổ biến:

**Implicit TLS (IMAPS)**: client tạo TLS connection ngay từ đầu. Ví dụ:

~~~java
Session session = Session.getInstance(properties);
Store store = session.getStore("imaps");
store.connect("imap.example.test", 993, username, password);
~~~

**STARTTLS (IMAP)**: client bắt đầu bằng protocol IMAP trên TCP rồi nâng cấp TLS theo khả năng server:

~~~java
Properties properties = new Properties();
properties.put("mail.imap.starttls.enable", "true");
properties.put("mail.imap.starttls.required", "true");
properties.put("mail.imap.ssl.checkserveridentity", "true");

Session session = Session.getInstance(properties);
Store store = session.getStore("imap");
store.connect("imap.example.test", 143, username, password);
~~~

`starttls.required=true` giúp tránh việc âm thầm tiếp tục phiên không mã hóa khi server không hỗ trợ STARTTLS. Không bật đồng thời các lựa chọn trái ngược rồi suy luận rằng IMAP sẽ “tự biết” cơ chế mong muốn.

Với POP3, cách làm tương tự dùng `pop3s`/995 hoặc `pop3`/110 với `mail.pop3.starttls.*`. Cơ chế STARTTLS của POP3 về mặt giao thức thường được gọi là STLS.

### Lỗi chứng chỉ TLS

Khi gặp `SSLHandshakeException` hoặc lỗi hostname verification:

1. Kiểm tra domain trong cấu hình có khớp chứng chỉ không.
2. Kiểm tra certificate chain, CA tin cậy, thời hạn và đồng hồ hệ thống.
3. Xác minh đang kết nối đúng port và đúng implicit TLS/STARTTLS mode.
4. Nếu server doanh nghiệp dùng private CA, cài truststore hợp lệ theo chính sách.
5. Rà proxy/tường lửa đang can thiệp TLS handshake.

Không giải quyết bằng:

~~~properties
# Không dùng trong production để bỏ xác minh.
mail.imaps.ssl.trust=*
~~~

Tin tưởng mọi server làm tăng nguy cơ kết nối đến máy chủ giả mạo hoặc MITM. Credential của mailbox có thể lộ nếu quá trình xác thực đi qua một endpoint không đáng tin cậy.

## 8. Đăng nhập thất bại không phải lỗi mạng có thể retry vô hạn

`AuthenticationFailedException` có thể phản ánh:

- Username/password sai hoặc đã rotate.
- App password bị thu hồi.
- Provider chặn basic authentication hoặc thay đổi chính sách SMTP/IMAP/POP3.
- MFA/conditional access yêu cầu cơ chế khác.
- OAuth2 access token hết hạn hoặc scope/audience sai.
- Mailbox bị khóa hoặc người dùng bị vô hiệu hóa.
- Quyền truy cập giao thức IMAP/POP3 bị tắt riêng trên account.

Nếu cứ lặp lại cùng credential mỗi 100 mili-giây, ứng dụng có thể kích hoạt lockout hoặc quota bảo vệ chống brute-force. Hành vi an toàn hơn:

~~~text
AuthenticationFailedException
          |
          v
Is OAuth token expired and refresh supported?
          |
     +----+-----+
     |          |
    Yes        No
     |          |
     v          v
Refresh token   Pause mailbox receiver
once safely     + alert operator
     |
     v
Retry a bounded authentication attempt
     |
     +-- still unauthorized -> pause + alert
~~~

**Không tự thử nhiều password, không fallback sang tài khoản admin và không tắt MFA**. Việc lấy lại token OAuth phải do một component xác thực chuyên trách thực hiện; token thường có thời hạn ngắn và không nên được đưa vào log.

### OAuth2 và IMAP

Một số provider hỗ trợ cơ chế XOAUTH2 cho IMAP. Cấu hình Jakarta Mail có thể cần:

~~~properties
mail.imaps.auth.mechanisms=XOAUTH2
~~~

Tùy implementation/provider, access token được truyền trong chỗ tham số credential của lời gọi connect, **không phải password truyền thống**. Đây không phải tính năng refresh tự động: ứng dụng cần có token supplier với expiry, scope và refresh lifecycle phù hợp provider.

Không giả định rằng `mail.imaps.auth.mechanisms=XOAUTH2` tự cấp cho client quyền đọc hộp thư. Provider còn kiểm tra consent/grant, account, mailbox scope và chính sách của tenant.

## 9. Kết nối và mở INBOX bằng Jakarta Mail

Ví dụ tối giản nhưng có cleanup để thấy rõ vị trí connection errors:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.Store;

public final class ImapsInboxReader {
    private final Session session;
    private final String host;
    private final String username;
    private final String password;

    public ImapsInboxReader(
            Session session,
            String host,
            String username,
            String password) {
        this.session = session;
        this.host = host;
        this.username = username;
        this.password = password;
    }

    public void readFirstPage() throws MessagingException {
        Store store = null;
        Folder inbox = null;

        try {
            store = session.getStore("imaps");
            store.connect(host, 993, username, password);

            inbox = store.getFolder("INBOX");
            if (!inbox.exists()) {
                throw new MessagingException(
                        "Configured inbox folder not found");
            }

            inbox.open(Folder.READ_ONLY);
            int messageCount = inbox.getMessageCount();
            int first = Math.max(1, messageCount - 19);

            if (messageCount > 0) {
                Message[] recent =
                        inbox.getMessages(first, messageCount);
                for (Message message : recent) {
                    // Chỉ minh họa: production dùng UID/checkpoint.
                    System.out.println(
                            "Fetched MIME type: "
                                    + message.getContentType());
                }
            }
        } finally {
            if (inbox != null && inbox.isOpen()) {
                inbox.close(false);
            }
            if (store != null && store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

Ví dụ mở `READ_ONLY`, không thay flags và không expunge. Chỉ in MIME type, không dump subject, sender, recipient hay body. Các object Jakarta Mail được tạo cho **một lần poll**, không chia sẻ `Folder` giữa nhiều thread.

**Đây là ví dụ học cách kết nối, không phải thuật toán nhận thư production**: lấy 20 message gần nhất theo thứ tự có thể bỏ sót message cũ hoặc xử lý lại message đã đọc. Những phần sau sẽ sử dụng UID và checkpoint bền vững.

### Lưu ý cleanup trong ví dụ

Các lệnh `Folder.close(false)` hoặc `Store.close()` cũng có thể ném `MessagingException`. Khi ứng dụng cần bảo toàn exception gốc và bảo đảm luôn đóng Store dù đóng Folder lỗi, hãy dùng helper cleanup riêng, bắt lỗi đóng từng resource và thêm lỗi đóng như **suppressed exception** thay vì để lỗi cleanup che mất nguyên nhân nhận thư.

Một lỗi cleanup không nhất thiết cần retry toàn bộ message đã được xử lý thành công; cần phân biệt **lỗi đọc** với **lỗi đóng kết nối** và theo dõi checkpoint.

## 10. Không dùng lại Folder/Store đã đóng sau khi kết nối lỗi

Một số exception liên quan vòng đời:

- `FolderClosedException`: folder không còn mở, ví dụ server đóng kết nối khi đang đọc.
- `StoreClosedException`: store/session connection không còn sử dụng được.
- `MessageRemovedException`: message bị xóa/expunge trong khi đang xử lý.
- `MessagingException` với nested `SocketTimeoutException`/`SocketException`: mất dữ liệu mạng hoặc timeout.

Sau khi session bị lỗi, một object `Message` lấy từ folder cũ cũng có thể không còn đọc được body vì Jakarta Mail tải content lazily.

Không làm:

~~~java
try {
    message.getContent();
} catch (MessagingException ex) {
    // Sai: tiếp tục gọi trên cùng Folder/Message đã hỏng.
    message.getContent();
}
~~~

Thay vào đó:

1. Phân loại lỗi; nếu transient connectivity thì đánh dấu session hiện tại không sử dụng được.
2. Cleanup Store/Folder cũ theo từng resource.
3. Chờ theo retry policy, **không lặp vô hạn trong một vòng while nóng**.
4. Tạo Store mới (và Folder mới), connect và open lại.
5. Kiểm tra UIDVALIDITY và load checkpoint.
6. Đọc tiếp các message chưa hoàn tất theo state đã lưu.

### Vì sao `store.isConnected()` chưa đủ?

Kết nối có thể đã bị server hoặc network middlebox đóng nhưng ứng dụng chưa phát hiện. `isConnected()` cung cấp một tín hiệu trạng thái, **không bảo đảm mọi thao tác tiếp theo chắc chắn thành công**. Luôn sẵn sàng xử lý exception tại lệnh `getMessages`, `getContent`, `fetch` hoặc khi đọc attachment.

## 11. Giới hạn thời gian sống và số kết nối

Một app có 10 mailbox accounts và 5 replicas, mỗi replica mở 4 Store cho mỗi mailbox có thể sinh **200 kết nối**. Provider thường có giới hạn connection/session hoặc chính sách throttling riêng.

Lập kế hoạch:

~~~text
Number of mailboxes
  x instances polling same account
  x connections per instance
  = possible concurrent connections
~~~

Giảm rủi ro:

- Chỉ một active poller cho mailbox khi cần single-consumer semantics.
- Dùng leader election hoặc distributed lease nếu có nhiều replica.
- Giới hạn số Store/Folder đang mở theo account.
- Đóng connection không còn dùng; không giữ quá lâu qua idle timeout.
- Không mở một Store mới **cho mỗi message** trong cùng batch nếu có thể tái sử dụng an toàn trong một lần poll.
- Có headroom cho ứng dụng/mail client khác dùng cùng mailbox.
- Tham khảo connection limits và polling guidance của provider đang dùng.

**Nhiều connection không phải lúc nào cũng tăng tốc đọc thư.** Nó có thể làm server throttling, bắt đầu trả BYE hoặc chặn account; đặc biệt khi mọi replica cùng poll INBOX.

## 12. Polling và IMAP IDLE có mô hình lỗi khác nhau

**Polling**: mở/đọc hộp thư theo lịch. Có thể dễ đo timeout, retry và đóng Store sau mỗi lượt.

**IMAP IDLE**: giữ kết nối để server đẩy tín hiệu thay đổi mailbox khi có thư mới. Giảm độ trễ và số lần poll, nhưng connection lâu sống dễ bị NAT/firewall/server idle timeout hoặc bị đóng khi bảo trì.

| Đặc điểm | Polling | IMAP IDLE |
|---|---|---|
| Kết nối | Thường ngắn theo lượt hoặc pool | Thường giữ mở |
| Phát hiện thư mới | Theo poll interval | Có thể gần thời gian thực |
| Phục hồi sau disconnect | Chờ poll sau và reconnect | Cần vòng restart IDLE |
| Dễ test | Khá đơn giản | Cần mô phỏng server BYE/IDLE termination |
| Tránh bỏ sót | Checkpoint UID khi poll | Vẫn phải reconcile UID sau reconnect |

**IDLE chỉ là tín hiệu có thay đổi, không phải durable message queue.** Sau khi IDLE bị ngắt, phải reconcile hộp thư bằng UID để tìm thư đã đến trong khoảng offline. Không dựa vào số lượng IDLE events như một checkpoint.

Nếu dùng **Spring Integration Mail**, có thể chọn inbound polling adapter hoặc IMAP IDLE-driven channel adapter; vẫn cần thiết kế exception handling, backoff, duplicate prevention, mailbox state và observability ở cấp ứng dụng.

## 13. Không dùng message sequence number làm checkpoint bền vững

Trong IMAP, mỗi `Message` có **message sequence number** theo thứ tự hiện tại trong folder. Khi thư bị xóa/expunge hoặc folder thay đổi, các số này có thể dịch chuyển.

Ví dụ:

~~~text
Poll lần 1:
  Seq 1 -> Email A
  Seq 2 -> Email B
  Seq 3 -> Email C

Email A bị expunge

Poll lần 2:
  Seq 1 -> Email B
  Seq 2 -> Email C

Nếu checkpoint = "đã xử lý seq 2":
  app có thể bỏ qua C hoặc xử lý sai.
~~~

Không nên lưu:

~~~text
lastProcessedMessageNumber=2
~~~

để rồi bắt đầu đọc từ 3 ở tất cả các lần kết nối sau. Sequence number chỉ có ý nghĩa trong trạng thái folder hiện tại.

Với IMAP, một lựa chọn phù hợp hơn là **UID**, kết hợp với **UIDVALIDITY**:

~~~text
Mail account + folder + UIDVALIDITY + UID
                  |
                  v
      Định danh message trên server
      trong một giai đoạn hiệu lực của UID
~~~

UID tăng theo quy tắc của mailbox trong cùng UIDVALIDITY, nhưng không có nghĩa UID liên tục. Không suy luận rằng khi UID tăng 100 thì nhất thiết có 100 thư mới.

## 14. UIDVALIDITY giải quyết điều gì?

Một IMAP folder có giá trị `UIDVALIDITY` xác định ngữ cảnh hiệu lực của UID. Khi server tái tạo mailbox hoặc thay đổi cách cấp UID, UIDVALIDITY có thể thay đổi.

Ví dụ:

~~~text
Trước khi mailbox được tái tạo:
  account=SUPPORT
  folder=INBOX
  UIDVALIDITY=100
  UID=2501 -> Email X

Sau khi mailbox được tái tạo:
  account=SUPPORT
  folder=INBOX
  UIDVALIDITY=101
  UID=2501 -> Có thể là Email Y
~~~

Nếu ứng dụng chỉ lưu UID=2501, nó có thể lầm tưởng Email Y đã được xử lý. Vì vậy khóa nhận diện thường gồm:

~~~text
(mailboxAccountId, folderName, uidValidity, uid)
~~~

Trong Jakarta Mail:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.UIDFolder;

Folder folder = store.getFolder("INBOX");
folder.open(Folder.READ_ONLY);

if (!(folder instanceof UIDFolder uidFolder)) {
    throw new IllegalStateException(
            "This mailbox implementation does not expose IMAP UID");
}

long uidValidity = uidFolder.getUIDValidity();
if (uidValidity <= 0) {
    throw new IllegalStateException(
            "Valid UIDVALIDITY is unavailable");
}
~~~

Không giả định mọi `Store`/`Folder` đều hỗ trợ `UIDFolder`. Với IMAP provider thông thường, đây là cơ chế phù hợp; với POP3, cách định danh khác.

### Khi UIDVALIDITY thay đổi thì làm gì?

Không thể tiếp tục so `lastUid` cũ như thể cùng một mailbox:

1. Ghi nhận sự kiện `UIDVALIDITY_CHANGED`.
2. Khởi tạo **thế hệ checkpoint mới** cho folder.
3. Reconcile lại các message hiện có theo policy.
4. Dùng bảng dedup/business idempotency để giảm xử lý trùng thư đã xử lý trước đó.
5. Không xóa lịch sử cũ trước khi có cách đối soát nếu nghiệp vụ cần audit.

**Đừng tự động đặt lại last UID về 0 rồi xử lý hàng triệu thư không giới hạn.** Cần kế hoạch initial scan, batch size, cutoff hoặc rescan theo retention và khả năng vận hành.

## 15. Đọc IMAP từ checkpoint sau khi reconnect

Một mô hình code cấp cao:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.UIDFolder;

public final class ImapBatchProcessor {
    private final MailCheckpointRepository checkpointRepository;
    private final MailBusinessProcessor businessProcessor;

    public ImapBatchProcessor(
            MailCheckpointRepository checkpointRepository,
            MailBusinessProcessor businessProcessor) {
        this.checkpointRepository = checkpointRepository;
        this.businessProcessor = businessProcessor;
    }

    public void processOpenFolder(
            String accountId,
            String folderName,
            Folder folder) throws Exception {

        if (!folder.isOpen()) {
            throw new MessagingException("Folder is not open");
        }
        if (!(folder instanceof UIDFolder uidFolder)) {
            throw new MessagingException(
                    "UID capability required for this processing mode");
        }

        long uidValidity = uidFolder.getUIDValidity();
        if (uidValidity <= 0) {
            throw new MessagingException(
                    "UIDVALIDITY not available");
        }

        MailCheckpoint checkpoint =
                checkpointRepository.loadOrCreate(
                        accountId, folderName, uidValidity);

        if (checkpoint.uidValidity() != uidValidity) {
            // Không sử dụng lastUid thuộc thế hệ cũ.
            throw new IllegalStateException(
                    "Mailbox UIDVALIDITY changed; reconciliation required");
        }

        long lastUid = checkpoint.lastCommittedUid();
        if (lastUid == Long.MAX_VALUE) {
            return;
        }

        // Ví dụ học thuật: production nên phân trang theo UID range.
        Message[] candidates = uidFolder.getMessagesByUID(
                lastUid + 1, UIDFolder.LASTUID);

        for (Message message : candidates) {
            if (message == null) {
                continue;
            }

            long uid = uidFolder.getUID(message);
            if (uid <= lastUid) {
                continue;
            }

            // Trong implementation thật, business side effect và
            // dedup/checkpoint phải theo transaction policy.
            businessProcessor.process(
                    accountId, folderName, uidValidity, uid, message);
            checkpointRepository.commitUid(
                    accountId, folderName, uidValidity, uid);
            lastUid = uid;
        }
    }
}
~~~

`MailCheckpointRepository`, `MailCheckpoint` và `MailBusinessProcessor` là những abstraction **do ứng dụng tự xây dựng**, không phải các class của Spring Mail. `processOpenFolder` yêu cầu folder đã được mở và worker sở hữu quyền poll account/folder tương ứng.

### Những điều ví dụ chưa giải quyết

- `getMessagesByUID` trên hộp thư lớn có thể trả rất nhiều message references. Trong production, phân trang theo dải UID/batch.
- `process(...)` và `commitUid(...)` là hai thao tác riêng. Nếu process thành công rồi app crash trước commit, message có thể được xử lý lại.
- Một message lỗi ở giữa batch có thể khiến các message sau bị hoãn. Đây có thể là lựa chọn đúng nếu giữ checkpoint tuần tự.
- Folder bị đóng trong khi xử lý khiến message lazy-fetch có thể không còn đọc được.
- `loadOrCreate` phải nhận biết UIDVALIDITY cũ và **không âm thầm tạo checkpoint mới khiến lịch sử bị che mất**.
- Nhiều worker xử lý cùng mailbox cần distributed lease và concurrency-safe checkpoint updates.

Ví dụ trên cố ý không hứa **exactly-once processing**. Để đảm bảo không tạo business side effect trùng, phải bổ sung idempotency và transaction.

## 16. Dùng database để ghi nhận message đã xử lý

Ngoài checkpoint cuối cùng, nên có một bảng dedup message:

~~~sql
CREATE TABLE received_mail (
    account_id VARCHAR(100) NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    uid_validity BIGINT NOT NULL,
    imap_uid BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL,
    processed_at TIMESTAMPTZ,
    business_reference VARCHAR(160),
    PRIMARY KEY (
        account_id, folder_name, uid_validity, imap_uid
    )
);

CREATE TABLE mailbox_checkpoint (
    account_id VARCHAR(100) NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    uid_validity BIGINT NOT NULL,
    last_committed_uid BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id, folder_name)
);
~~~

Với bảng `mailbox_checkpoint`, cần một policy khi UIDVALIDITY thay đổi: cập nhật generation trong transaction/điều phối reconcile, không chỉ sử dụng `last_committed_uid` của generation cũ.

### Nguyên tắc về transaction

Nếu xử lý một thư là **ghi record nội bộ**:

~~~text
BEGIN TRANSACTION
  Verify message not processed
  Insert/update business data
  Mark received_mail processed
  Advance checkpoint safely
COMMIT
~~~

Nếu cả bốn thao tác dùng cùng một transactional database, có thể đạt tính nhất quán tốt giữa business state và checkpoint. Nếu xử lý gồm **gọi API bên ngoài**, gửi phản hồi qua SMTP hoặc đẩy event sang hệ thống khác, database transaction **không** bao trùm được side effect đó; cần idempotency key, outbox hoặc cơ chế phối hợp phù hợp.

### Không đánh dấu xử lý thành công quá sớm

Sai:

~~~text
Fetch UID 500
Advance checkpoint to UID 500
Download attachment / business processing
Crash
~~~

Khi restart, checkpoint khiến UID 500 bị bỏ qua dù công việc chưa xong.

Đúng theo nguyên tắc:

~~~text
Fetch UID 500
Validate / process idempotently
Persist success and checkpoint
Only then consider UID 500 committed
~~~

Đối với lỗi tạm thời, giữ message ở trạng thái retry và không tăng checkpoint tuần tự vượt qua một khoảng chưa được xử lý trừ khi ứng dụng có thiết kế gap tracking riêng.

## 17. Chọn at-least-once + idempotency thay vì hứa exactly-once

Một lần poll có thể gặp các điểm crash:

~~~text
Fetch UID 900
    |
    +-- Crash trước xử lý       -> retry UID 900
    |
    +-- Business DB commit
    |      |
    |      +-- Crash trước checkpoint -> có thể xử lý lại
    |
    +-- Checkpoint commit
    |
    +-- Worker tiếp tục UID 901
~~~

Khi pipeline nhận thư làm việc với database và một hệ thống ngoài như CRM, **không có một transaction đồng nhất** bao trùm cả email server, database và API CRM. Vì vậy nên thiết kế:

- **At-least-once fetching**: có thể đọc lại message sau reconnect/restart.
- **Idempotent processing**: các lần đọc lại không tạo trùng record nghiệp vụ.
- **Transactional inbox**: ghi nhận message key trong cùng transaction với thay đổi nghiệp vụ nội bộ.
- **Outbox cho external side effect**: ghi intent chuyển CRM/HTTP response vào DB; worker khác thực thi và retry có idempotency key.
- **Dead-letter/quarantine**: cô lập message không thể xử lý để không chặn mailbox vĩnh viễn.

`Message-ID` trong header email **không được bảo đảm duy nhất hoặc luôn tồn tại**; không nên dùng nó làm khóa dedup duy nhất. Một email có thể được copy sang folder khác hoặc provider tái tạo UIDVALIDITY; với nghiệp vụ quan trọng cần quy tắc correlation/semantic dedup bổ sung như transaction reference từ nội dung đã xác minh.

### Checkpoint và trạng thái theo lỗ hổng (gap)

Nếu message UID 105 lỗi parsing còn UID 106 xử lý thành công, có hai lựa chọn:

1. **Strict sequential cursor:** dừng tại UID 105, không advance qua 105. Đơn giản, có thể làm chậm batch.
2. **Per-message status + gap tracking:** ghi UID 106 completed, UID 105 retry/quarantine, chỉ advance watermark sau khi mọi message trước đó đạt trạng thái terminal được chấp thuận.

Không tăng checkpoint thẳng tới 106 chỉ vì một message mới hơn đã hoàn thành nếu hệ thống không ghi và theo dõi UID 105 đang chờ.

## 18. POP3: UIDL, DELE và nguy cơ mất thư

POP3 có mô hình khác IMAP:

~~~text
POP3 connect/auth
    |
    v
STAT / LIST / UIDL (nếu được hỗ trợ)
    |
    v
RETR n
    |
    v
Process + save checkpoint
    |
    v
Optional DELE n
    |
    v
QUIT
~~~

Trong POP3, một số server cung cấp lệnh **UIDL** để ứng dụng phân biệt message qua các lần kết nối. Tuy nhiên UIDL và khả năng API truy cập khác nhau theo provider. **Không dùng số thứ tự POP3 LIST/RETR làm định danh bền vững**, vì nó thay đổi khi thư bị xóa.

### Cẩn trọng với thao tác xóa

- Nếu đọc thư xong và muốn **giữ bản sao trên server**, không yêu cầu xóa.
- Nếu cần xóa theo chính sách retention, chỉ đánh dấu xóa sau khi payload và trạng thái xử lý đã được lưu chắc chắn.
- Với POP3, các đánh dấu `DELE` thường được server thực hiện tại kết thúc phiên phù hợp (QUIT), nên kết quả có thể không rõ nếu connection mất trước khi hoàn tất.
- Không giả định `Folder.close(true)` có ngữ nghĩa giống nhau trong IMAP và POP3 cho mọi implementation; tìm hiểu provider/connector cụ thể trước khi bật expunge/delete.

Với hệ thống phải phục hồi sau crash và nhiều folder, **IMAP có UID thường dễ xây checkpoint hơn**. Nếu bắt buộc POP3, cần một chiến lược UIDL/dedup và lưu byte message bền vững trước khi thực hiện các thao tác làm biến mất email trên server.

## 19. Retry có exponential backoff và jitter

Nếu hộp thư gặp outage, một ứng dụng không nên cố kết nối lại hàng nghìn lần mỗi giây. **Exponential backoff** tăng dần khoảng đợi theo lần lỗi:

\[
d_n = \min(d_{\max},\, d_0 \cdot 2^{n-1})
\]

Trong đó `d0` là delay cơ bản, `dmax` là trần và `n` là lần thất bại liên tiếp.

Thêm **jitter** để nhiều instance không kết nối lại đồng loạt:

\[
d_{\text{retry}} \sim U(0,d_n)
\]

Đây là *full jitter*. Nếu nghiệp vụ yêu cầu không retry quá sớm, thêm minimum retry interval và giới hạn tổng số lần retry/tuổi outage.

Ví dụ:

| Lỗi thứ | Backoff cap giả định với base 2s | Khoảng full jitter |
|---|---:|---|
| 1 | 2 giây | 0–2 giây |
| 2 | 4 giây | 0–4 giây |
| 3 | 8 giây | 0–8 giây |
| 4 | 16 giây | 0–16 giây |
| 5 | 32 giây | 0–32 giây |
| 6 trở đi | Capped, ví dụ 60 giây | 0–60 giây |

Con số chỉ minh họa, không phải hướng dẫn chính thức của một provider. Nếu nhà cung cấp có chính sách tối thiểu giữa các lần IMAP login hoặc đề nghị chờ lâu hơn, phải tôn trọng.

## 20. Java: tính backoff, không giữ thread ngủ vô hạn

Một lớp nhỏ dễ kiểm thử:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class MailReconnectBackoff {
    private final long baseMillis;
    private final long maxMillis;

    public MailReconnectBackoff(
            Duration base,
            Duration maximum) {
        this.baseMillis = base.toMillis();
        this.maxMillis = maximum.toMillis();
        if (baseMillis <= 0 || maxMillis < baseMillis) {
            throw new IllegalArgumentException(
                    "Invalid reconnect backoff configuration");
        }
    }

    public Duration nextDelay(int consecutiveFailures) {
        if (consecutiveFailures < 1) {
            throw new IllegalArgumentException(
                    "consecutiveFailures must be positive");
        }

        long cap = baseMillis;
        for (int i = 1; i < consecutiveFailures; i++) {
            if (cap >= maxMillis) {
                break;
            }
            cap = cap > maxMillis / 2
                    ? maxMillis
                    : cap * 2;
        }

        long millis = ThreadLocalRandom.current()
                .nextLong(cap + 1);
        return Duration.ofMillis(millis);
    }
}
~~~

Tránh gọi `Thread.sleep(...)` trong một IMAP listener hoặc worker đang giữ DB lease, connection và executor slot. Tốt hơn là **đặt lịch poll lại** bằng scheduler hoặc lưu `nextAttemptAt`, giải phóng thread.

### Retry theo mailbox riêng

Nếu ứng dụng nhận từ 20 mailbox, lỗi của mailbox A không nên khiến toàn bộ mailbox B–T ngừng xử lý. Quản lý các trường sau theo từng account:

~~~text
mailboxId
consecutiveFailures
lastSuccessfulPollAt
nextAttemptAt
lastFailureKind
healthStatus
~~~

Không ghi raw password/token vào bảng trạng thái hay log. Khi A ổn định trở lại, reset bộ đếm lỗi liên tiếp theo policy; không tự xóa lịch sử sự cố cần cho audit.

## 21. Phân loại exception của Jakarta Mail

Các loại cần nhận biết:

| Exception hoặc nested cause | Ý nghĩa thường gặp | Cách ứng xử |
|---|---|---|
| `AuthenticationFailedException` | Auth/token/permission lỗi | Pause và làm mới token theo cơ chế hợp lệ |
| `FolderNotFoundException` | Sai folder/path hoặc folder bị xóa | Kiểm tra cấu hình, không retry nóng |
| `FolderClosedException` | Folder bị server/library đóng | Cleanup và mở folder mới |
| `StoreClosedException` | Store connection đóng | Tạo Store và connect lại |
| `MessageRemovedException` | Message không còn tại vị trí đang đọc | Reconcile UID/checkpoint, không retry trên object cũ |
| `SocketTimeoutException` trong cause | TCP read/write/connect chậm | Transient retry, kiểm tra timeout và server |
| `SocketException`/`ConnectException` | Reset/refused/network error | Kiểm tra mạng/endpoint, retry có backoff |
| `UnknownHostException` | DNS host không phân giải | Có thể transient hoặc cấu hình sai; kiểm tra DNS |
| `SSLHandshakeException` | TLS trust/hostname/protocol | Xác minh certificate và endpoint, không tắt TLS |
| `MessagingException` chung | Không đủ ngữ cảnh | Xem nested cause/type/protocol, phân loại thận trọng |

Một số provider báo sự cố qua protocol response trước khi Java ném exception; tên exception cụ thể tùy Jakarta Mail implementation. **Không thiết kế policy chỉ theo chuỗi message và kỳ vọng áp cho mọi provider**.

### Đừng nhầm IMAP với SMTP status code

- SMTP sử dụng reply code như `421`, `450`, `550`.
- IMAP sử dụng tagged `OK`, `NO`, `BAD` cùng các phản hồi như `BYE` và thông tin server.
- POP3 sử dụng `+OK` và `-ERR`.

Một SMTP retry policy không thể áp nguyên xi cho IMAP login/fetch. Cần phân loại theo giao thức hiện tại.

## 22. Ví dụ Java: phân loại lỗi thành mã nội bộ

Một bộ phân loại giúp poller quyết định retry mà không log nguyên exception chứa địa chỉ email hoặc response server.

~~~java
import jakarta.mail.AuthenticationFailedException;
import jakarta.mail.FolderClosedException;
import jakarta.mail.FolderNotFoundException;
import jakarta.mail.StoreClosedException;
import java.net.ConnectException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import javax.net.ssl.SSLHandshakeException;

public enum ReceiveFailureKind {
    AUTHENTICATION,
    TLS_CONFIGURATION,
    FOLDER_CONFIGURATION,
    CONNECTION_LOST,
    DNS_OR_CONNECTIVITY,
    UNKNOWN
}

public final class MailReceiveFailureClassifier {
    private MailReceiveFailureClassifier() {
    }

    public static ReceiveFailureKind classify(Throwable error) {
        Throwable current = error;
        int depth = 0;

        while (current != null && depth++ < 24) {
            if (current instanceof AuthenticationFailedException) {
                return ReceiveFailureKind.AUTHENTICATION;
            }
            if (current instanceof SSLHandshakeException) {
                return ReceiveFailureKind.TLS_CONFIGURATION;
            }
            if (current instanceof FolderNotFoundException) {
                return ReceiveFailureKind.FOLDER_CONFIGURATION;
            }
            if (current instanceof FolderClosedException
                    || current instanceof StoreClosedException
                    || current instanceof SocketException
                    || current instanceof SocketTimeoutException) {
                return ReceiveFailureKind.CONNECTION_LOST;
            }
            if (current instanceof UnknownHostException
                    || current instanceof ConnectException) {
                return ReceiveFailureKind.DNS_OR_CONNECTIVITY;
            }
            current = current.getCause();
        }
        return ReceiveFailureKind.UNKNOWN;
    }
}
~~~

**Giới hạn quan trọng của ví dụ:**

- Đây là classifier cơ bản cho cause chain, không phải bảng xử lý đầy đủ của mọi provider.
- `SocketTimeoutException` là subclass của `SocketException`, nhưng vẫn được liệt kê để làm rõ ý nghĩa.
- Một `MessagingException` có thể chứa nested exception qua `getNextException()` ngoài cách truy cập cause; hệ thống thực tế nên duyệt đầy đủ **có giới hạn và chống vòng lặp**, không chỉ theo `getCause()`.
- Với lỗi auth do token hết hạn, cách xử lý khác với account bị revoke; cần dùng tín hiệu identity provider.
- `SSLHandshakeException` có thể phản ánh nhiều nguyên nhân, không phải lúc nào cũng chỉ lỗi certificate.
- Một số exception folder là lỗi mailbox state tạm thời, phải đối chiếu server response trước khi quyết định dừng hẳn.

Không tự in `error.getMessage()` hay `error` vào log tập trung; response có thể chứa mailbox name, username, email address hoặc thông tin tài khoản. Chỉ log mã phân loại, mailbox ID không nhạy cảm và job/poll attempt.

## 23. Vòng poll an toàn: không để một outage làm ngừng scheduler

Một mô hình poller cần:

- Bắt đầu khi đã đến `nextAttemptAt`.
- Xác nhận chỉ một worker đang sở hữu mailbox/folder nếu cần serial processing.
- Kết nối Store và mở Folder.
- Xử lý một batch giới hạn số lượng.
- Lưu kết quả thành công và checkpoint.
- Phân loại exception; lên lịch retry hoặc pause.
- Đóng connection.
- Không giữ resource từ lần poll trước trong một vòng lặp bị lỗi.

~~~text
Scheduled tick
    |
    v
Is mailbox paused or not due yet?
    |          |
   Yes         No
    |          |
    v          v
  Skip      Acquire lease
                 |
                 v
           Connect / open
                 |
         +-------+-------+
         |               |
       Success          Failure
         |               |
         v               v
    Process batch      Classify
         |               |
         v               v
    Commit state    Backoff or pause
         |               |
         +-------+-------+
                 |
                 v
            Close / release
~~~

### Ví dụ coordinator với lịch

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class MailboxPollScheduler {
    private final Clock clock;
    private final MailboxPollingCoordinator coordinator;

    public MailboxPollScheduler(
            Clock clock,
            MailboxPollingCoordinator coordinator) {
        this.clock = clock;
        this.coordinator = coordinator;
    }

    @Scheduled(
            fixedDelayString =
                    "${app.mail.receive.poll-delay-ms:30000}")
    public void poll() {
        Instant now = clock.instant();
        coordinator.pollDueMailboxes(now);
    }
}
~~~

`MailboxPollingCoordinator` là service do ứng dụng xây dựng. Nó phải **bắt lỗi riêng cho từng mailbox** và ghi `nextAttemptAt`, thay vì để một mailbox lỗi làm các mailbox còn lại không được poll. Khi dùng `@Scheduled`, cần bật scheduling bằng `@EnableScheduling` theo cấu hình ứng dụng.

Đây chỉ là cách tạo lịch nhắc. Nếu có nhiều replicas, tất cả sẽ chạy scheduler; **cần lease/leader election** trước khi mỗi mailbox được xử lý. Đừng dựa vào `fixedDelay` để nghĩ toàn cụm chỉ có một worker.

### Không retry ngay trong cùng một scheduled tick

Sai:

~~~java
while (true) {
    try {
        readMailbox();
    } catch (Exception ignored) {
        // Tight loop: server down -> hàng nghìn lần connect.
    }
}
~~~

Đúng hơn là ghi một trạng thái `WAITING_RECONNECT` với thời điểm thử tiếp, rồi kết thúc tick. Một lần tick khác sẽ tiếp tục khi đủ thời gian.

## 24. Circuit breaker cho mailbox gặp lỗi kéo dài

Một mailbox có credential sai trong nhiều giờ không nên chiếm toàn bộ hệ thống bằng hàng nghìn login attempts. **Circuit breaker** giúp tạm ngăn các lệnh kết nối mới.

~~~text
CLOSED: bình thường, cho poll
    |
    +-- failures vượt ngưỡng
    v
OPEN: tạm dừng poll, alert/cooldown
    |
    +-- cooldown kết thúc
    v
HALF_OPEN: thử một kết nối có kiểm soát
    |
    +-- success -> CLOSED
    |
    +-- failure -> OPEN
~~~

Phân biệt ba dạng dừng:

| Loại | Ý nghĩa | Thời gian dừng |
|---|---|---|
| Retry backoff | Lỗi transient đơn lẻ | Giây/phút theo policy |
| Circuit breaker | Lỗi liên tiếp làm provider chưa sẵn sàng | Cooldown và probe hạn chế |
| Administrative pause | Credential/TLS/config/permission sai cần can thiệp | Cho đến khi remediation hoặc được phê duyệt resume |

Đừng tự đóng lại circuit liên tục khi có bằng chứng account bị revoke. Ngược lại, đừng biến network hiccup 5 giây thành một pause vô thời hạn mà không có cảnh báo hay cơ chế phục hồi.

### Provider-level throttling

Một số server giới hạn tần suất mở IMAP sessions hoặc số kết nối đồng thời. Nếu nhiều mailbox cùng provider bị throttle, cần giảm **tổng số kết nối/poll rate**, không chỉ backoff riêng một mailbox. Đây là bài toán admission control theo provider/account tương tự quota, nhưng liên quan inbound connection chứ không phải SMTP gửi thư.

## 25. Distributed lease khi nhiều replica đọc cùng hộp thư

Nếu hai application instances cùng poll mailbox:

~~~text
Instance A        Instance B
    |                 |
    +-- Fetch UID 101 +
                      +-- Fetch UID 101
    |                 |
    +-- Process       +-- Process
    |                 |
         Duplicates!
~~~

Có thể dùng **distributed lease** theo khóa:

~~~text
mailbox-receive:{accountId}:{folderName}
~~~

Một owner được quyền poll trong khoảng lease; khi worker chết, lease hết hạn và worker khác tiếp quản.

Điều kiện cần:

- Acquire/renew/release lease nguyên tử tại store được chia sẻ.
- Lease có thời hạn lớn hơn poll segment hoặc được gia hạn đúng cách.
- **Fencing token**/generation giúp worker cũ không ghi checkpoint sau khi mất lease.
- Checkpoint transaction kiểm tra lease ownership.
- Worker luôn đọc checkpoint bền vững, không dùng lại local cursor cũ sau takeover.
- Business handler vẫn phải idempotent vì lease không xóa được mọi cửa sổ race.

### Tại sao lock trong một JVM không đủ?

`synchronized` hoặc `ReentrantLock` chỉ điều phối thread trong một JVM. Trong Kubernetes với 4 pods, có thể có 4 lock khác nhau và cả 4 đều nghĩ mình sở hữu mailbox.

Nếu ứng dụng chỉ có một instance thật sự, local lock có thể đủ về mặt concurrency. Nhưng điều đó phải là giả định triển khai được kiểm soát; rolling deployment có thể tạm thời chạy hai instances.

## 26. Không dùng Seen flag làm điểm kiểm tra duy nhất

Một cách thường gặp:

~~~text
Search UNSEEN
Process message
Set SEEN
~~~

Tưởng đơn giản nhưng không đủ đáng tin:

- Người dùng hoặc một client email khác có thể đánh dấu Seen trước app.
- Sau crash, một thư có thể đã Seen nhưng chưa được business xử lý.
- Một client có thể đánh dấu Unseen lại, khiến app nhận trùng.
- IMAP flags có thể đổi qua đồng bộ nhiều thiết bị.
- Khi READ_ONLY, app không nên trông chờ có thể đổi flags.

**Seen là trạng thái trải nghiệm hộp thư, không phải transaction checkpoint của nghiệp vụ.** Nên kết hợp UID/UIDVALIDITY và bảng xử lý bền vững.

Nếu sản phẩm yêu cầu tự động mark Seen sau xử lý, hãy thực hiện theo policy với quyền `READ_WRITE`, đánh dấu **sau** khi lưu kết quả nghiệp vụ; nhưng vẫn không được coi flag là bằng chứng duy nhất. Nếu thao tác mark Seen lỗi, cần phân biệt với business processing đã thành công để không tạo side effect trùng.

## 27. Message bị xóa hoặc chuyển folder trong khi đọc

Trong hộp thư dùng chung, người dùng có thể xóa/di chuyển email khi worker đang lấy nội dung:

~~~text
Worker lists UID 888
    |
    +-- User moves message to Archive
    |
Worker fetches body for UID 888
    |
    +-- MessageRemovedException / not found
~~~

Cách ứng xử tùy nghiệp vụ:

- Nếu message không còn trong folder, ghi trạng thái `MESSAGE_DISAPPEARED` theo UID, không lặp retry vô hạn trên object cũ.
- Nếu ứng dụng phải xử lý thư dù đã bị move, cần chiến lược theo dõi folder khác, provider API hoặc snapshot đủ sớm.
- Không tự đánh dấu “đã xử lý thành công” chỉ vì message đã biến mất.
- Khi cursor tuần tự gặp gap UID do thư bị xóa, cần xác định gap không phải thư chưa được xử lý đang bị bỏ sót.
- Có thể ghi audit về UID không còn truy xuất, nhưng tránh log nội dung hay địa chỉ người gửi.

**IMAP UID là định danh trong một folder/UIDVALIDITY**, không phải định danh toàn mailbox xuyên qua thao tác move. Một message được copy/move sang folder mới thường có UID khác.

## 28. Tải nội dung thư và attachment an toàn khi kết nối dễ đứt

Lệnh `Message.getContent()` có thể tải dữ liệu khi được gọi, không nhất thiết toàn bộ email đã nằm trong bộ nhớ từ lúc `getMessages()` trả về. Attachment lớn làm read timeout hoặc connection reset có xác suất cao hơn.

Lưu ý:

1. Giới hạn kích thước message/attachment theo chính sách trước khi xử lý nội dung lớn.
2. Không gọi `getContent()` rồi log nguyên nội dung để debug.
3. Nếu cần xử lý lâu, có thể **snapshot MIME bytes** vào kho tạm có bảo vệ rồi xử lý sau khi đóng folder.
4. Đảm bảo snapshot đã được ghi hoàn chỉnh, có checksum/kích thước và một trạng thái bền vững trước khi advance checkpoint.
5. Không đọc stream attachment ngoài vòng đời Store/Folder nếu implementation còn phụ thuộc server.
6. Dùng parser MIME phù hợp và bảo vệ trước file nguy hiểm, path traversal, zip bomb và malware.
7. Không đưa nội dung email không tin cậy trực tiếp vào HTML/web output mà không escape/sanitize.

### Ví dụ lưu bản MIME vào byte array cho fixture nhỏ

~~~java
import jakarta.mail.Message;
import java.io.ByteArrayOutputStream;

public byte[] snapshotSmallMessage(Message message)
        throws Exception {
    ByteArrayOutputStream output =
            new ByteArrayOutputStream();
    message.writeTo(output);
    return output.toByteArray();
}
~~~

**Không dùng `ByteArrayOutputStream` không giới hạn cho email hàng trăm MB**. Với dữ liệu lớn, stream vào storage có giới hạn/quota, đo byte count và checksum, và bảo vệ dữ liệu ở trạng thái lưu trữ. Nếu snapshot là nơi chứa email thật, nó có PII và có thể chứa token/link nhạy cảm; encryption, RBAC và retention phải được xác định.

Nếu `writeTo(...)` lỗi giữa chừng vì mất kết nối, không được đánh dấu message processed chỉ vì đã nhận được một phần bytes.

## 29. Monitoring: “poll không lỗi” chưa đủ chứng minh đã nhận được thư

Một worker có thể kết nối thành công và log `poll_completed` đều đặn nhưng không phát hiện được thư mới vì query sai folder, UID checkpoint bị lệch hoặc filter bỏ qua toàn bộ message.

Nên theo dõi nhiều nhóm tín hiệu:

| Metric | Ý nghĩa |
|---|---|
| `mail_receive_poll_total` | Số lượt polling theo mailbox/provider và outcome |
| `mail_receive_connection_failure_total` | Số lỗi kết nối TCP/TLS/DNS |
| `mail_receive_auth_failure_total` | Số lỗi xác thực |
| `mail_receive_reconnect_total` | Số lần phải mở connection mới sau lỗi |
| `mail_receive_poll_duration_seconds` | Thời gian thực thi một poll |
| `mail_receive_last_success_timestamp_seconds` | Thời điểm gần nhất có poll hoàn tất |
| `mail_receive_last_message_timestamp_seconds` | Thời điểm nhận/hoàn tất message gần nhất |
| `mail_receive_fetched_total` | Số message được lấy từ server |
| `mail_receive_processed_total` | Số message business xử lý thành công |
| `mail_receive_duplicate_total` | Số message đã biết, bỏ qua side effect |
| `mail_receive_processing_failure_total` | Số lỗi parse/business |
| `mail_receive_uidvalidity_change_total` | Số lần mailbox generation đổi |
| `mail_receive_backoff_seconds` | Khoảng cooldown đang áp |
| `mail_receive_pending_messages` | Số message cần xử lý nếu đo được |
| `mail_receive_checkpoint_lag` | Độ trễ giữa thư mới nhất và checkpoint; chỉ đo khi có ngữ nghĩa rõ |

### Giá trị label phải được kiểm soát

Ví dụ:

~~~text
provider=PRIMARY_IMAP
mailbox_profile=SUPPORT_INBOX
phase=FETCH
result=TIMEOUT
~~~

Không dùng địa chỉ email thật, `Message-ID`, subject hoặc UID riêng từng thư làm metrics label — cardinality cao và có thể lộ thông tin. `mailbox_profile` nên là ID nội bộ thuộc danh sách hữu hạn, không chứa username/PII.

### Last successful poll khác last message received

Một mailbox có thể không có thư mới trong nhiều giờ, nhưng polling vẫn hoạt động đúng. Ngược lại, một poll thành công có thể không có message mới vì cấu hình sai.

Để kiểm soát:

- Với mailbox có traffic đều, cảnh báo khi thời gian từ lần xử lý email thành công vượt kỳ vọng.
- Với mailbox lưu lượng thấp, dùng **synthetic test email** trong môi trường được phép để xác nhận end-to-end.
- Khi cần chẩn đoán, xem checkpoint/UID validity, folder name và filter thay vì chỉ nhìn số lỗi connection.

Một watchdog có thể phát hiện worker không hoàn thành poll quá lâu hoặc stuck trong I/O; watchdog không tự bảo đảm message đã được xử lý.

## 30. Log an toàn khi xử lý lỗi nhận thư

Message nhận được có thể chứa:

- Địa chỉ From/To/Cc/Bcc.
- Subject và nội dung thư.
- Link reset mật khẩu, session token hoặc OTP.
- Attachment nhạy cảm.
- Header kỹ thuật và thông tin mailbox account.

Do đó không làm:

~~~java
log.error("IMAP failure user={} message={}",
        username, exception.getMessage());

log.debug("Received email: {}", message);
~~~

Thay bằng:

~~~text
event=mail_receive_poll_failed
mailboxProfile=SUPPORT_INBOX
provider=PRIMARY_IMAP
phase=FETCH
errorKind=CONNECTION_LOST
consecutiveFailures=3
nextRetryBucket=30s_60s
~~~

Nếu cần correlation theo message, dùng một ID nội bộ/UID tuple trong kho audit có quyền phù hợp. UID riêng không phải PII trực tiếp nhưng có thể được liên kết tới nội dung thông qua mailbox access hoặc log khác.

### Jakarta Mail protocol debug

`Session.setDebug(true)` và các cấu hình `mail.debug=true` có thể in dữ liệu giao thức IMAP/POP3. Tuỳ implementation và chế độ, nó có thể lộ usernames, mailbox/folder names và thông tin giao thức nhạy cảm.

**Không bật protocol debug trong production theo mặc định.** Khi cần điều tra:

1. Ưu tiên test account và mail server giả lập.
2. Giới hạn thời gian, instance và quyền truy cập output.
3. Không bật tùy chọn lộ authentication secrets.
4. Làm sạch dữ liệu trước khi đưa vào ticket hoặc chat.
5. Tắt debug và thu hồi dữ liệu theo retention policy.

Tắt DEBUG của application logger chưa chắc ngăn `Session` in ra debug output riêng; cần kiểm soát cả nguồn stdout/stderr và cấu hình library.

## 31. Alert và runbook khi mailbox ngừng nhận thư

Một runbook nên chia theo giai đoạn gặp lỗi:

### A. Không kết nối được server

1. Kiểm tra DNS resolve của host được cấu hình từ đúng môi trường/pod.
2. Xác minh TCP egress, firewall, NAT, proxy và port.
3. Kiểm tra provider status page và giới hạn connection.
4. Đối chiếu implicit TLS/STARTTLS port.
5. Xem `connectiontimeout`, `timeout` có hợp lý không.
6. Nếu provider tạm unavailable, giảm số lần reconnect và giám sát backlog.

**Không dùng việc tắt TLS để phân biệt lỗi trên production**. Nếu cần thí nghiệm, dùng sandbox được kiểm soát.

### B. TLS handshake thất bại

1. Xem certificate chain và hostname.
2. Kiểm tra CA/truststore và ngày giờ hệ thống.
3. Xác minh TLS version và server endpoint.
4. Không bật `mail.imaps.ssl.trust=*` để bỏ xác minh.
5. Chỉ resume sau khi kết nối bảo mật đúng.

### C. Authentication fail liên tục

1. Xác định loại auth: app password, OAuth2, provider-specific.
2. Kiểm tra secret rotation/expiry và scope/grant.
3. Xác minh provider còn bật IMAP/POP3 access cho mailbox.
4. Pause để tránh account lockout.
5. Làm mới credential/token bằng nguồn được phê duyệt và thử lại có giới hạn.
6. Xem audit account cho hoạt động đăng nhập bất thường.

### D. Kết nối được nhưng không đọc được INBOX

1. Kiểm tra folder name, mailbox hierarchy và quyền.
2. Xem folder có `READ_ONLY`/`READ_WRITE` phù hợp không.
3. Kiểm tra UIDVALIDITY và checkpoint.
4. Xác nhận IMAP folder là INBOX đúng account, không phải mailbox/alias khác.
5. Xem app có dùng `UNSEEN` filter làm mất thư đã được client khác đọc hay không.
6. Reconcile bằng UID trong một dải có kiểm soát, không xóa checkpoint bừa bãi.

### E. Đọc được thư nhưng business xử lý không tiến lên

1. Phân biệt parse/MIME error với database error.
2. Xác định UID/message đang blocked.
3. Kiểm tra retry/quarantine per message.
4. Nếu cần reprocess, dùng idempotency và audit.
5. Không mark Seen/delete hoặc advance checkpoint trước khi xử lý thành công.

### F. Sau outage xuất hiện rất nhiều thư trùng

1. Kiểm tra nhiều replica đang poll cùng account.
2. Kiểm tra lease ownership và fencing.
3. Xem UIDVALIDITY đã thay đổi không.
4. Kiểm tra transaction giữa processed state và checkpoint.
5. Xem external side effect có idempotency key không.
6. Ngừng replay thiếu kiểm soát, đối soát dữ liệu trước khi chạy lại.

## 32. Test unit: backoff có deterministic input

Các test chỉ dựa vào `Thread.sleep` có thể flaky trên CI. Một số thuật toán backoff có thể được tách thành bước tính **trần** và bước chọn jitter để test dễ hơn.

Ví dụ một policy thuần tính trần:

~~~java
import java.time.Duration;

public final class ReconnectBackoffCap {
    private final Duration base;
    private final Duration maximum;

    public ReconnectBackoffCap(
            Duration base, Duration maximum) {
        if (base.isZero() || base.isNegative()
                || maximum.compareTo(base) < 0) {
            throw new IllegalArgumentException(
                    "Invalid durations");
        }
        this.base = base;
        this.maximum = maximum;
    }

    public Duration capFor(int consecutiveFailures) {
        if (consecutiveFailures < 1) {
            throw new IllegalArgumentException();
        }
        Duration current = base;
        for (int i = 1; i < consecutiveFailures; i++) {
            if (current.compareTo(maximum) >= 0) {
                return maximum;
            }
            current = current.compareTo(maximum.dividedBy(2)) > 0
                    ? maximum
                    : current.multipliedBy(2);
        }
        return current.compareTo(maximum) > 0
                ? maximum : current;
    }
}
~~~

JUnit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class ReconnectBackoffCapTest {
    @Test
    void growsExponentiallyAndStopsAtMaximum() {
        ReconnectBackoffCap policy =
                new ReconnectBackoffCap(
                        Duration.ofSeconds(2),
                        Duration.ofSeconds(30));

        assertThat(policy.capFor(1))
                .isEqualTo(Duration.ofSeconds(2));
        assertThat(policy.capFor(2))
                .isEqualTo(Duration.ofSeconds(4));
        assertThat(policy.capFor(3))
                .isEqualTo(Duration.ofSeconds(8));
        assertThat(policy.capFor(5))
                .isEqualTo(Duration.ofSeconds(30));
        assertThat(policy.capFor(20))
                .isEqualTo(Duration.ofSeconds(30));
    }
}
~~~

Khi kiểm thử jitter, có thể inject một bộ sinh số ngẫu nhiên giả hoặc một hàm trả số xác định, rồi assert delay nằm trong [minimum, cap]. **Không cần gọi network hoặc ngủ thật** để test công thức.

## 33. Unit test: phân biệt auth, TLS và connection loss

Một vài tình huống dùng JUnit + AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import jakarta.mail.AuthenticationFailedException;
import jakarta.mail.FolderClosedException;
import javax.net.ssl.SSLHandshakeException;
import org.junit.jupiter.api.Test;

class MailReceiveFailureClassifierTest {
    @Test
    void authenticationIsNotTreatedAsTransientNetwork() {
        var error = new AuthenticationFailedException(
                "Fake credentials for unit test");

        assertThat(MailReceiveFailureClassifier.classify(error))
                .isEqualTo(ReceiveFailureKind.AUTHENTICATION);
    }

    @Test
    void tlsFailureIsNotSolvedByBlindReconnect() {
        var error = new SSLHandshakeException(
                "Test certificate mismatch");
        assertThat(MailReceiveFailureClassifier.classify(error))
                .isEqualTo(ReceiveFailureKind.TLS_CONFIGURATION);
    }

    @Test
    void closedFolderCausesReconnectClassification() {
        var error = new FolderClosedException(null);
        assertThat(MailReceiveFailureClassifier.classify(error))
                .isEqualTo(ReceiveFailureKind.CONNECTION_LOST);
    }
}
~~~

Các exception được tạo bằng thông tin giả. Test này kiểm tra classifier cơ bản, không chứng minh nó xử lý mọi exception của một provider. Cần test thêm nested cause/`MessagingException.getNextException()` và trường hợp code không có đủ thông tin.

### Test không được cần credential thật

Unit test classifier/backoff/state machine phải chạy offline. SMTP/IMAP production credential không được đưa vào test hoặc CI. Nếu cần kiểm thử kết nối, sử dụng test server hoặc sandbox mailbox được phê duyệt.

## 34. Integration test với IMAP/POP3 server giả lập

Unit test giúp kiểm tra policy, nhưng **kết nối bị đóng giữa lúc FETCH** và **UIDVALIDITY thay đổi** là tình huống cần kiểm thử integration.

Có thể dùng mail server kiểm thử hỗ trợ IMAP/POP3 như GreenMail hoặc một server/test double tùy dự án. Những kịch bản:

| Kịch bản | Mô phỏng | Kết quả mong đợi |
|---|---|---|
| IT-01 | Kết nối bình thường | Đọc được message, checkpoint tăng |
| IT-02 | Connect refused | Phân loại connectivity, backoff |
| IT-03 | TCP connection reset trong FETCH | Mở Store/Folder mới, không bỏ checkpoint |
| IT-04 | Read timeout | Không giữ worker vô hạn, retry an toàn |
| IT-05 | Wrong password | Pause/alert, không login loop |
| IT-06 | Token expired | Refresh theo policy, retry có giới hạn |
| IT-07 | Certificate hostname mismatch | Reject TLS, không trust all |
| IT-08 | Folder bị đóng | Reconnect và reload state |
| IT-09 | UIDVALIDITY đổi | Reconcile generation; không dùng UID cũ |
| IT-10 | Worker crash trước checkpoint | Re-fetch, business idempotency |
| IT-11 | Worker crash sau business commit | Không tạo side effect trùng |
| IT-12 | Message bị expunge | Không dùng sequence number cũ |
| IT-13 | POP3 UIDL thay đổi/không hỗ trợ | Không dựa vào số thứ tự; policy fallback |
| IT-14 | Hai replicas cùng mailbox | Lease chỉ một poller và dedup an toàn |
| IT-15 | IMAP IDLE bị BYE/timeout | IDLE restart và reconcile UID |
| IT-16 | Một attachment bị lỗi | Message quarantine, không block mọi mailbox |

### Test connection failure cần giả lập đúng giai đoạn

Một server test có thể dừng socket **trước** khi gửi FETCH data, **giữa** stream MIME và **sau** khi message đã tải đủ. Các tình huống khác nhau về việc có thể retry trực tiếp hay cần xóa snapshot tạm, nhưng không được commit checkpoint khi message chưa được xử lý hoàn toàn.

### Ranh giới của test server

Một local server giả lập có thể không có cùng timeout/connection policy với Gmail, Microsoft 365 hoặc mail server doanh nghiệp. Nó hữu ích để kiểm thử logic reconnect, nhưng integration test trên **sandbox provider thật** vẫn cần thiết khi rollout authentication, TLS hoặc IMAP IDLE-specific behavior.

## 35. Spring Integration Mail: retry đặt ở đâu?

Nếu ứng dụng dùng **Spring Integration Mail**, có thể gặp:

- `ImapMailReceiver` để lấy thư qua IMAP.
- `Pop3MailReceiver` để lấy thư qua POP3.
- Polling inbound adapter dùng mail-receiving message source.
- IMAP IDLE-driven channel adapter cho mô hình gần thời gian thực.
- Message channel, poller và error handling trong integration flow.

Thiết kế logic:

~~~text
IMAP / POP3 Provider
        |
        v
Spring Integration Mail receiver
        |
        +-- Polling / IMAP IDLE lifecycle
        |
        v
Spring Integration channel
        |
        v
Message handler / business service
        |
        v
Durable state + checkpoint/dedup
~~~

### Tách lỗi ở inbound adapter với lỗi downstream

Lỗi lúc `connect/open/fetch` xảy ra **trước khi** một Spring Integration message được phát ra channel. Lỗi khi transform/process xảy ra **sau khi** receiver đã lấy message.

Vì vậy:

1. Cấu hình timeout/TLS và authentication của mail receiver đúng provider.
2. Xác định poller hoặc IDLE adapter xử lý connection loss và restart như thế nào trên phiên bản Spring Integration đang dùng.
3. Cấu hình error channel/`ErrorMessage` hoặc error handler ở vị trí thích hợp, **không giả định tất cả lỗi fetch đều tự đến cùng một channel**.
4. Không retry toàn bộ mailbox mỗi khi business handler fail; phân loại và quarantine message lỗi.
5. Xem default flag handling, auto-delete/expunge, message conversion và search filters của receiver; các hành vi này có thể ảnh hưởng việc đọc lại.
6. Tự quyết định checkpoint/dedup bền vững, đặc biệt khi ứng dụng đòi không bỏ sót mail sau restart.

**Spring Integration Mail không tự biến IMAP/POP3 thành một transactional message queue exactly-once.** Adapter giúp kết nối và tích hợp flow; business idempotency, provider auth policy và recovery semantics vẫn phải được thiết kế.

### Poller exception không được dừng vĩnh viễn luồng nhận

Một outage có thể làm scheduler/logging lặp lỗi hoặc khiến một adapter ngừng làm việc tùy cấu hình. Phải kiểm tra:

- Adapter có được restart lại sau `StoreClosedException` không?
- Poller có backoff khi auth hoặc network fail không?
- Có cách đánh dấu mailbox `PAUSED` khi credential sai không?
- Nếu IDLE connection bị đóng, adapter có reconnect và reconcile thư bỏ lỡ không?
- Nhiều instances có cùng đọc mailbox và business handler có idempotent không?

API của Spring Integration thay đổi theo phiên bản; luôn đối chiếu module/version thực tế khi cài đặt poller, advice, retry hoặc error handling, không copy cấu hình của phiên bản cũ mà không kiểm tra.

## 36. Thiết kế mailbox polling configuration theo account

Với nhiều mailbox, tránh một file cấu hình chỉ có `mail.host` và một scheduler không phân biệt accounts. Một profile nên bao gồm:

~~~yaml
app:
  mail:
    receive:
      poll-delay-ms: 30000
      accounts:
        support:
          protocol: imaps
          host: imap-support.example.test
          port: 993
          username: ${SUPPORT_IMAP_USERNAME}
          password: ${SUPPORT_IMAP_PASSWORD}
          folder: INBOX
          connect-timeout-ms: 5000
          read-timeout-ms: 15000
          write-timeout-ms: 15000
          batch-size: 50
          reconnect-base-ms: 2000
          reconnect-max-ms: 60000
          require-valid-tls: true
~~~

`app.mail.receive.*` là namespace **tự xây dựng**; Spring Boot không tự tạo một inbound IMAP consumer chỉ từ YAML này. Code phải bind cấu hình, xây Jakarta Mail Session/receiver, lên lịch, checkpoint và retry.

Các số đều là ví dụ, không đại diện cho giới hạn của provider nào. Một server có latency cao hoặc mailbox chứa thư dung lượng lớn có thể cần timeout/batch size khác.

### Cấu hình không được chứa dữ liệu không tin cậy

Không lấy `protocol`, `host` hoặc `port` từ email/HTTP request tùy ý rồi cho server kết nối vì dễ biến ứng dụng thành SSRF/network probing. Các mailbox profiles phải được phê duyệt, host/port được kiểm soát và credential được cấp qua secret store.

### Tránh Java string có mật khẩu lâu sống khi có thể

Jakarta Mail thường nhận credential qua `String` hoặc token theo API xác thực. Một số bản sao secret không thể xóa triệt để khỏi JVM heap. Hạn chế đường cấp phát/logging, không in cấu hình bean và dùng secret manager/workload identity phù hợp.

## 37. Những anti-pattern cần tránh

### 37.1. Lỗi kết nối nào cũng retry ngay bằng while(true)

Network outage tạo hàng nghìn connect attempts; auth sai có thể khóa account. Dùng backoff, jitter, pause và giới hạn theo provider.

### 37.2. Chỉ đặt connect timeout, bỏ read timeout

TCP connect có thể nhanh nhưng `FETCH` treo lâu vì server hoặc attachment lớn. Thiết lập connect, read và write timeouts đúng protocol.

### 37.3. Trộn `mail.imap.*` với `getStore("imaps")`

Property prefix không đúng có thể khiến timeout/TLS setting không được áp. Kiểm tra session protocol thật và dùng prefix tương ứng.

### 37.4. Giải quyết TLS failure bằng trust all

~~~properties
mail.imaps.ssl.trust=*
~~~

Tắt certificate verification làm giảm an toàn của credential và nội dung thư. Sửa endpoint/certificate/truststore.

### 37.5. Giữ Store/Folder cũ sau timeout

Một object `Message` có thể vẫn tham chiếu connection đã hỏng. Cleanup và tạo Store/Folder mới; tải lại bằng UID.

### 37.6. Dùng sequence number làm ID lâu dài

Sequence number thay đổi sau expunge. Với IMAP, dùng UID + UIDVALIDITY + mailbox identity.

### 37.7. Chỉ dùng UID mà bỏ UIDVALIDITY

Một UID có thể được tái sử dụng sau khi mailbox generation thay đổi. Không đọc từ cursor cũ mà không đối chiếu UIDVALIDITY.

### 37.8. Chỉ xử lý những thư UNSEEN

Người dùng có thể mark Seen trước worker hoặc thư đã được tự đánh dấu Seen. Đây không phải transaction checkpoint tin cậy.

### 37.9. Mark Seen hoặc xóa email trước khi business commit

Nếu processing fail, ứng dụng có thể bỏ qua/đánh mất message. Lưu kết quả trước; điều khiển flags/delete sau theo policy.

### 37.10. Giữ một transaction DB trong suốt IMAP FETCH

Download attachment có thể chậm, khiến lock và DB connection bị giữ lâu. Tách network fetch/snapshot khỏi transaction ngắn cho business state và checkpoint.

### 37.11. Xử lý external API rồi tin rằng checkpoint bảo đảm exactly-once

Crash giữa API success và DB commit có thể tạo side effect trùng. Dùng idempotency key và outbox khi cần.

### 37.12. Hai replicas cùng poll một mailbox không có lease

Mỗi replica có thể nhận và xử lý cùng UID. Dùng distributed lease/fencing hoặc thiết kế multi-consumer có dedup đầy đủ.

### 37.13. Reconnect IMAP IDLE rồi chờ sự kiện mới

Thư đến trong khoảng disconnected có thể không phát thêm IDLE event sau khi reconnect. Reconcile UID từ checkpoint.

### 37.14. Checkpoint vượt qua một message lỗi không có gap tracking

Một UID cũ chưa processed sẽ bị bỏ sót khi cursor tăng. Giữ thứ tự hoặc quản lý per-message status/gaps.

### 37.15. Mỗi lần lỗi đều retry toàn bộ batch đã xử lý

Nếu business handler không idempotent, toàn bộ side effect có thể lặp lại. Checkpoint theo message/transaction và duplicate detection.

### 37.16. Dump raw email/exception để điều tra

Log có thể chứa PII, credential, body, links và attachment. Log mailbox profile, phase, failure kind và attempt count; giữ raw diagnostic ở kênh hạn chế nếu thực sự cần.

### 37.17. Không theo dõi thời điểm xử lý thư thành công gần nhất

Scheduler có thể hoạt động nhưng đọc sai folder hoặc không có quyền fetch. Theo dõi liveness, last success, processed count và synthetic end-to-end mail khi phù hợp.

### 37.18. Coi POP3 UIDL giống IMAP UIDVALIDITY

POP3 UIDL có semantics khác và API có thể phụ thuộc provider. Không dùng logic UIDFolder của IMAP để suy luận về POP3 deletion/migration.

### 37.19. Xóa mọi thư sau khi download một lần

Nếu database commit fail hoặc content snapshot chưa hoàn chỉnh, thư có thể mất. Mọi thao tác xóa phải tuân theo retention, durable processing và khả năng khôi phục.

### 37.20. Chỉ chạy test với inbox không có thư

Test rỗng không thể xác minh xử lý attachment, reconnect giữa FETCH, UIDVALIDITY hay idempotency. Cần fixture giả có message hợp lệ và malformed/large message.

## 38. Lộ trình triển khai cơ chế phục hồi nhận thư

Một lộ trình thực tế với Spring + Jakarta Mail/Spring Integration:

1. **Chọn giao thức:** IMAP nếu cần folder, flags, UID; POP3 nếu bài toán đơn giản và server chỉ hỗ trợ giao thức này.
2. **Phân loại mailbox profiles:** account, folder, provider, mode xác thực và yêu cầu dữ liệu.
3. **Chọn TLS đúng chuẩn:** IMAPS hoặc IMAP STARTTLS bắt buộc; tương tự POP3S/STLS; bật hostname verification.
4. **Cấu hình timeout:** connect, read, write và giới hạn số connection.
5. **Tách authentication lifecycle:** password/app password hoặc OAuth2 token supplier, rotation/revoke và pause khi auth thất bại.
6. **Thiết kế polling/IDLE:** chọn độ trễ cần thiết và cách reconnect khi server đóng session.
7. **Tạo checkpoint bền vững:** IMAP theo account/folder/UIDVALIDITY/UID; POP3 theo UIDL nếu hỗ trợ cùng policy.
8. **Thiết kế idempotent business processor:** message key, transactional inbox và outbox cho side effect bên ngoài.
9. **Chọn cách xử lý message lỗi:** retry, quarantine/dead letter, backoff riêng cho business errors.
10. **Định nghĩa lỗi reconnect:** phân loại transient, auth, TLS, folder và malformed message.
11. **Thêm backoff/jitter và circuit breaker:** tránh login storm khi mailbox server lỗi.
12. **Đặt concurrency/lease:** một poller cho mailbox nếu processing yêu cầu, fencing khi nhiều replica.
13. **Kiểm soát resource:** không giữ Store/Folder lỗi, cleanup an toàn, giới hạn attachment size.
14. **Tạo metrics/logs:** last poll, last processed, auth failure, reconnect, checkpoint health, backlog.
15. **Viết unit/integration tests:** timeout, disconnect, UIDVALIDITY, crash trước/sau commit, malformed mail.
16. **Triển khai sandbox trước:** fake mailbox/test messages, không dùng data khách hàng thật cho kiểm thử.
17. **Lập runbook:** chẩn đoán TLS/auth/network, UID reconciliation, account lockout và replay.
18. **Vận hành định kỳ:** review permissions, secret rotation, folder retention, connection limits và mailbox state.

### Ma trận hành vi khuyến nghị theo lỗi

| Lỗi | Retry connection? | Có được advance checkpoint? | Cần hành động khác? |
|---|---|---|---|
| TCP/connect timeout | Có, sau backoff | Không nếu message chưa commit | Kiểm tra network |
| DNS tạm không resolve | Có giới hạn, backoff | Không | Kiểm tra DNS/config |
| TLS certificate mismatch | Không retry nóng | Không | Sửa trust/certificate |
| Authentication failed | Không thử vô hạn | Không | Refresh hợp lệ hoặc pause |
| IMAP BYE / Store closed | Có, reconnect mới | Chỉ giữ các commit trước đó | Reload UIDVALIDITY/checkpoint |
| Folder not found | Không retry nóng | Không | Sửa folder/path/permission |
| Folder closed trong FETCH | Có, open lại | Không cho message chưa hoàn tất | Refetch theo UID |
| Message removed | Reconcile; không retry object cũ | Theo policy gap/status | Xác định di chuyển/xóa |
| MIME malformed | Không nhất thiết reconnect | Chỉ khi quarantine terminal được ghi chắc chắn | Quarantine/test parser |
| Business DB unavailable | Không nhất thiết reconnect | Không | Retry commit, bảo vệ state |
| UIDVALIDITY changed | Không dùng cursor cũ | Không trước reconcile | Chuyển generation/checkpoint |
| Poll thành công, không có mail | Poll kỳ tiếp | Không cần thay checkpoint | Theo dõi last success |

## 39. Câu hỏi thường gặp

**Spring Mail có thể tự nhận thư từ INBOX không?** `JavaMailSender` chủ yếu dùng SMTP để gửi. Để nhận có thể dùng Jakarta Mail `Store`/`Folder` hoặc Spring Integration Mail inbound adapters.

**IMAP và POP3 nên chọn giao thức nào?** IMAP phù hợp hơn khi cần nhiều folder, UID/flags và đồng bộ. POP3 có thể đủ nếu chỉ cần tải thư từ một mailbox và provider hỗ trợ UIDL theo nhu cầu.

**Mất mạng 10 giây có cần restart cả Spring Boot không?** Không nên. Một receiver được thiết kế đúng sẽ cleanup connection lỗi, chờ backoff rồi tạo Store/Folder mới và tiếp tục từ checkpoint.

**`store.isConnected()` trả true thì fetch chắc chắn thành công chứ?** Không. Kết nối có thể mất sau lần kiểm tra. Mọi lệnh thao tác với mailbox vẫn có thể ném exception.

**Tại sao phải cấu hình cả connect timeout và read timeout?** Connect timeout áp cho giai đoạn tạo TCP connection; read timeout giới hạn thời gian chờ phản hồi trong FETCH/other commands. Một kết nối thành công vẫn có thể bị treo khi đọc.

**Dùng `getStore("imaps")` thì đặt `mail.imap.timeout` được không?** Không nên. Property provider dùng prefix theo protocol, nên với `imaps` cần `mail.imaps.timeout` và các property tương ứng.

**Nên tắt certificate checking khi IMAP không kết nối được?** Không. Kiểm tra host, port, truststore, certificate chain và TLS mode. Trust-all làm mất bảo vệ cho credential và nội dung.

**MFA có đồng nghĩa IMAP password sẽ hoạt động?** Không. Nhiều provider yêu cầu app password/OAuth2, có thể chặn legacy basic auth hoặc vô hiệu hóa IMAP trên account.

**Nếu token OAuth2 hết hạn thì xử lý ra sao?** Lấy token mới bằng cơ chế được hỗ trợ, có cache/expiry/grants hợp lệ; retry có giới hạn. Không tiếp tục dùng token hết hạn trong tight loop.

**Có cần một Store mới cho mỗi message không?** Thường không. Có thể dùng một Store/Folder cho một batch khi còn khỏe. Sau connection failure, cần tạo lại resources mới.

**Có nên giữ một Store IMAP kết nối mãi không?** Có thể với kiến trúc IDLE/long-lived được thiết kế phù hợp, nhưng phải dự kiến server/NAT timeout, reconnect và reconciliate UID. Không có kết nối nào được bảo đảm tồn tại mãi.

**IMAP IDLE có bảo đảm không bỏ sót message không?** Không. IDLE là cơ chế thông báo thay đổi, không phải durable checkpoint. Sau reconnect vẫn cần poll/reconcile message theo UID.

**Có thể lấy 20 email mới nhất mỗi lần rồi xử lý không?** Chỉ khi nghiệp vụ cho phép bỏ qua số lượng vượt ngưỡng. Với hệ thống cần xử lý đầy đủ, dùng UID/checkpoint và batch có kiểm soát.

**Vì sao không dùng message number để ghi nhận thư đã xử lý?** Số thứ tự thay đổi khi message bị expunge. UID cùng UIDVALIDITY ổn định hơn trong một generation mailbox.

**UIDVALIDITY thay đổi có phải dữ liệu bị lỗi không?** Không nhất thiết. Mailbox có thể được tái tạo hoặc thay đổi ở server. Nhưng UID cũ không còn cùng ý nghĩa; phải reconcile theo policy.

**Chỉ dùng header Message-ID để dedup được không?** Không bảo đảm. Message-ID có thể thiếu, bị trùng, thay đổi khi forward hoặc không tương ứng với message trên server. Dùng khóa mailbox UID và business idempotency phù hợp.

**Có thể dựa vào UNSEEN để không xử lý trùng không?** Không đủ. Seen flag có thể bị client khác thay đổi và không gắn atomic với DB commit.

**Lỗi `FolderClosedException` có nên gọi lại `message.getContent()` ngay không?** Không nên dùng lại message/folder cũ đã hỏng. Reconnect, open folder và refetch theo UID.

**Nếu một email malformed khiến handler lỗi mãi thì sao?** Quarantine theo message key và ghi trạng thái terminal/được xử lý rõ ràng để không chặn các thư sau, đồng thời giữ khả năng điều tra/replay theo quyền.

**Nếu DB commit xong nhưng worker chết trước checkpoint thì sao?** Thư có thể được đọc lại. Transactional inbox/idempotent handler giúp không tạo trùng side effect.

**Checkpoint có nên lưu trên RAM?** Chỉ khi mất state sau restart là chấp nhận được. Với nhận thư nghiệp vụ quan trọng, checkpoint cần lưu bền vững và có bảo vệ cạnh tranh.

**Dùng hai replicas đọc một mailbox có nguy hiểm không?** Có thể xử lý trùng hoặc race checkpoint. Cần phân chia ownership, lease/fencing hoặc idempotency đủ mạnh.

**POP3 UIDL có tương đương IMAP UID không?** Không hoàn toàn. UIDL có semantics riêng và hỗ trợ phụ thuộc server/provider; không có cùng UIDVALIDITY/folder model.

**Có nên xóa POP3 message ngay sau RETR?** Không nếu dữ liệu chưa được lưu và xử lý bền vững. Phải xác định chính sách retention và semantics DELE/QUIT của server.

**Có cần retry trong business handler khi lỗi DB?** Có thể, nhưng đó là retry nghiệp vụ/state riêng. Không nhất thiết đóng/mở lại IMAP vì lỗi database.

**Nếu `@Scheduled` vẫn chạy mà không nhận thư, nguyên nhân gì?** Có thể đọc sai folder, checkpoint lệch, filter bỏ qua thư, auth lỗi bị che, hoặc connection đang stuck. Theo dõi last successful poll, fetched/processed counts và test end-to-end.

**Có thể log toàn bộ raw MIME để điều tra không?** Không nên trong log production. Raw message chứa người gửi, người nhận, subject, attachment và token/link. Dùng kênh diagnostic có quyền đặc biệt và retention ngắn khi thật sự cần.

**Unit test cần kết nối Gmail/Outlook thật không?** Không. Unit test classifier, backoff, dedup và scheduler dùng dữ liệu giả. Integration test kết nối dùng fake server hoặc sandbox account được phê duyệt.

**Có nên retry lỗi TLS với exponential backoff?** Một lỗi TLS cấu hình/chứng chỉ cố định thường không tự hết khi retry. Cần pause và xử lý nguyên nhân; backoff có thể dùng cho transient handshake/network failure đã được phân loại phù hợp.

**Provider giới hạn số IMAP connections thì xử lý thế nào?** Giảm poll concurrency, dùng một owner/lease theo mailbox, cân nhắc IDLE hoặc interval lớn hơn và theo dõi policy của account.

## 40. Tổng kết

**Xử lý lỗi kết nối khi nhận thư** trong Spring Framework Mail cần nhìn xa hơn một khối `catch (MessagingException)` và một lần gọi `connect()` lại. Một receiver đáng tin cậy gồm những lớp:

~~~text
Configured mailbox profile
        |
        v
TLS / Authentication / Timeout
        |
        v
Jakarta Mail Store + Folder
        |
        v
Poll / IMAP IDLE (with reconnect policy)
        |
        v
UID + UIDVALIDITY / POP3 UIDL
        |
        v
Durable dedup + processing state
        |
        v
Business transaction / outbox
        |
        v
Checkpoint commit
        |
        v
Observability + alert + recovery
~~~

Năm nguyên tắc quan trọng nhất:

1. **Phân loại trước khi retry:** network timeout có thể phục hồi, còn sai credential, TLS và folder permission thường cần xử lý khác.
2. **Không dùng connection cũ sau failure:** đóng và tạo lại Store/Folder, sau đó tiếp tục theo checkpoint bền vững.
3. **Không dùng sequence number/Seen làm bằng chứng xử lý:** với IMAP, theo dõi UID cùng UIDVALIDITY và account/folder; với POP3, xử lý UIDL theo khả năng server.
4. **Chấp nhận khả năng đọc lại nhưng ngăn side effect trùng:** transactional inbox, business idempotency và checkpoint sau khi xử lý bền vững.
5. **Điều phối reconnect và quan sát:** timeout, backoff/jitter, circuit breaker, lease nhiều replica, last-success metrics và runbook khi mailbox gặp sự cố.

Khi những lớp này phối hợp nhất quán, một đợt mất mạng, server restart hoặc mailbox disconnect không còn đồng nghĩa với việc email bị bỏ sót hay một worker phải được khởi động thủ công. Hệ thống có thể phục hồi đúng dữ liệu chưa hoàn tất, bảo vệ tài khoản trước retry storm, và giúp người vận hành xác định nguyên nhân chính xác mà không làm lộ nội dung thư.
