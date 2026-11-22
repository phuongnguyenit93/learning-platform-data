# Giới hạn quyền và kiểm tra nội dung thư đến trong Spring Framework Mail

Khi xây dựng ứng dụng xử lý thư đến, ví dụ nhận email hỗ trợ khách hàng, lấy hóa đơn từ một hộp thư kế toán hoặc đọc phản hồi của đối tác, vấn đề không chỉ là **đăng nhập IMAP và lấy nội dung email**. Một thông điệp thư điện tử đến từ bên ngoài là **dữ liệu không tin cậy**, có thể chứa header giả mạo, HTML độc hại, đường dẫn lừa đảo, tệp đính kèm nguy hiểm, cấu trúc MIME phức tạp hoặc kích thước vượt giới hạn hệ thống. Đồng thời, thông tin đăng nhập hộp thư có thể cho phép đọc rất nhiều thư riêng tư, thậm chí xóa, chuyển tiếp hoặc gửi thư nếu được cấp quyền quá rộng.

Vì vậy, bài học này đặt hai yêu cầu bảo vệ song song:

1. **Giới hạn quyền:** tiến trình đọc thư chỉ có quyền tối thiểu cần thiết đối với đúng tài khoản, thư mục và thao tác được phép.
2. **Kiểm tra nội dung:** mọi thư đến phải đi qua một đường xử lý có giới hạn tài nguyên, xác minh nguồn, phân tích MIME, cách ly tệp đính kèm và kiểm tra an toàn trước khi thực hiện tác động nghiệp vụ.

Mục tiêu không phải tạo một bộ lọc “email an toàn tuyệt đối”, mà là thiết kế hệ thống có thể **nhận thư đáng tin cậy, giảm thiểu tác động khi tài khoản bị lộ hoặc email chứa nội dung nguy hiểm, đồng thời tránh mất thư và xử lý trùng**.

> Nguyên tắc quan trọng: **đọc được email không có nghĩa nội dung email được quyền chỉ đạo ứng dụng**. Địa chỉ From, Subject, HTML, filename và thông tin bên trong thư đều phải được coi là input không tin cậy cho tới khi được kiểm tra theo chính sách rõ ràng.

## 1. Phạm vi nhận thư trong hệ sinh thái Spring

Tên “Spring Framework Mail” thường gợi đến `JavaMailSender`, `JavaMailSenderImpl` và `MimeMessageHelper`, nhưng các abstraction này chủ yếu phục vụ **soạn và gửi thư**. Để **nhận thư**, ứng dụng thường sử dụng:

- **Jakarta Mail API:** kết nối `Store`, mở `Folder`, đọc `Message`, `Part`, `Multipart`; dùng IMAP/IMAPS hoặc POP3/POP3S.
- **Spring Integration Mail** (nếu dự án có module tương ứng): hỗ trợ polling hoặc IMAP IDLE, tích hợp thông điệp vào flow xử lý của Spring Integration.
- **API/webhook của nhà cung cấp mail:** nhận metadata hoặc raw message theo hợp đồng provider, cần xác thực webhook/API riêng.

Không giả định `JavaMailSender.receive()` tồn tại. Bài này dùng **Jakarta Mail** để minh họa kết nối hộp thư và nêu các quy tắc tương tự khi triển khai bằng Spring Integration Mail hoặc provider API.

### Sơ đồ luồng xử lý

~~~mermaid
flowchart TD
    A["Mailbox / IMAP or provider event"] --> B["Read-only ingestion identity"]
    B --> C["Bounded retrieval + durable staging"]
    C --> D["Metadata and MIME validation"]
    D --> E["Attachment and malware checks"]
    E --> F{"Allowed to process?"}
    F -- "No" --> G["Quarantine / reject / review"]
    F -- "Yes" --> H["Normalize trusted business data"]
    H --> I["Idempotent business handler"]
    I --> J["Record processing result"]
    J --> K["Acknowledge / move if authorized"]
~~~

Một hệ thống có thể thay phần kết nối IMAP bằng webhook, nhưng những yêu cầu về **giới hạn quyền, kích thước, phân tích nội dung, xác thực nguồn, idempotency và audit** vẫn còn nguyên.

## 2. Mô hình đe dọa của một hộp thư được xử lý tự động

Các nhóm rủi ro cần cân nhắc:

| Nguồn rủi ro | Ví dụ | Biện pháp |
| --- | --- | --- |
| Tài khoản hộp thư bị lộ | Credential có thể đọc toàn bộ thư, xóa/thay đổi trạng thái | Service mailbox, OAuth scope/ACL tối thiểu, secret manager |
| Sender giả mạo | Header From giống một đối tác nội bộ | Không tin From; xác thực theo nguồn và chính sách |
| MIME độc hại | Multipart lồng sâu, malformed headers, encoding bất thường | Parse có giới hạn và cơ chế quarantine |
| Nội dung quá lớn | Message body/attachment làm đầy memory/disk | Server limits, bounded stream, quotas |
| Tệp đính kèm nguy hiểm | Macro, executable, archive bomb, virus | Allowlist, MIME sniffing, malware scan, isolation |
| HTML nguy hiểm | Script, remote images, phishing links, CSS lừa hướng | Không thực thi; render plain text hoặc sanitize đúng |
| Prompt/command injection | Email yêu cầu “bỏ qua quy trình, chuyển tiền” | Business authorization độc lập với nội dung thư |
| Thư trùng | IMAP polling lặp, worker restart, webhook redelivery | UID/UIDVALIDITY + idempotency |
| Thư bị đánh dấu đã đọc quá sớm | Fetch làm `\\Seen` hoặc worker ack trước commit | Read-only/peek, staging, ack sau xử lý |
| Lộ dữ liệu khi vận hành | Log toàn bộ body, token, tên file và header | Redaction, quyền xem, retention |
| SSRF qua nội dung | Parser tải URL trong HTML hoặc tài nguyên ngoài | Không tự fetch external resources |
| Gửi nhầm phản hồi | Auto-reply theo địa chỉ Reply-To giả mạo | Authorization và policy riêng cho outbound |

Một email có thể chứa nhiều rủi ro đồng thời. Ví dụ, một tập tin tên `invoice.pdf` có thể là executable ngụy trang, bên trong archive lồng nhau hoặc tài liệu có liên kết độc hại. Kiểm tra **một thuộc tính đơn lẻ** không bảo đảm an toàn.

## 3. Nguyên tắc least privilege cho tài khoản nhận thư

**Least privilege** nghĩa là tiến trình chỉ được cấp những quyền thực sự cần để hoàn thành nhiệm vụ.

### Quyền thường cần và quyền nên tránh

| Hành động | Ingestion chỉ đọc có cần? | Lưu ý |
| --- | --- | --- |
| Liệt kê thư mục được phép | Có thể | Hạn chế phạm vi nếu provider hỗ trợ |
| Đọc metadata thư mới | Có | Không cần đọc toàn bộ mailbox history |
| Đọc nội dung một số thư được chọn | Có | Chỉ trong mailbox/folder được cấp |
| Tạo/xóa folder | Không, trừ workflow rõ ràng | Dễ gây mất thư |
| Đánh dấu `\\Seen` | Không bắt buộc | Tránh dùng để thay durable acknowledgment |
| Đánh dấu `\\Deleted` và expunge | Không cho ingest thuần đọc | Có thể xóa vĩnh viễn |
| Chuyển thư sang folder xử lý | Chỉ nếu workflow cần | Cấp riêng quyền sửa và log audit |
| Gửi mail từ tài khoản | Thông thường không | Tách identity gửi/nhận |
| Truy cập các hộp thư người dùng khác | Không | Tránh domain-wide delegation rộng |
| Quản trị tài khoản/mailbox | Không | Tách operator identity |

Chỉ mở `Folder.READ_ONLY` ở ứng dụng **không thay thế ACL ở mail server**. Nếu credential thực tế có quyền xóa mọi thư, việc một đoạn code đang đọc read-only không giới hạn tác động khi credential bị đánh cắp hoặc code có lỗi. Cần khóa quyền ở cả **provider/IAM/ACL** và **application**.

### Một mailbox chuyên dụng

Ví dụ nhu cầu nhận hóa đơn:

- Địa chỉ `invoices-inbound@example.org` chỉ nhận các email phục vụ luồng hóa đơn.
- Tài khoản kết nối dùng scope đọc mailbox đó, không đọc mailbox cá nhân của nhân viên.
- Worker chỉ mở folder được định nghĩa, không quét mọi folder.
- Hộp thư gửi phản hồi/từ chối nằm ở một service identity khác nếu cần.
- Quản trị mailbox và thay đổi quyền phải có audit.

Việc tách mailbox không chỉ giúp bảo mật mà còn giảm dữ liệu cá nhân không liên quan bị tải vào hệ thống.

### Phân tách nhiều tenant

Nếu sản phẩm có nhiều khách hàng/tenant, không dùng một token có quyền đọc tất cả mailbox trừ khi có yêu cầu và kiểm soát rất rõ. Với mỗi message, correlation phải gắn `tenantId`, account, folder và identity nguồn; một lỗi routing không được khiến thư của tenant A đi vào processor của tenant B.

## 4. Giới hạn theo thư mục, thao tác và thời gian

Một tài khoản có thể có nhiều folder: INBOX, Sent, Archive, Spam, Trash và các folder tùy chỉnh. Ingestion nên:

1. Chỉ mở một tập folder được cấu hình/allowlist.
2. Chỉ đọc thư phù hợp tiêu chí, ví dụ UID lớn hơn checkpoint hoặc message nhận gần đây.
3. Dùng **READ_ONLY** cho thao tác lấy nội dung nếu không cần sửa flags.
4. Không tự đọc Sent, Trash, Spam hoặc folder người dùng khác.
5. Không tự move/delete email khi parser lỗi hoặc business handler lỗi.
6. Ghi lại quyền cần thiết nếu cần chuyển email sang quarantine/processed folder.

### READ_ONLY không đủ để chỉ đọc một folder

Quyền đọc folder có thể được áp dụng qua IMAP ACL hoặc API/IAM của provider, tùy dịch vụ. Một số provider chỉ cấp scope cấp tài khoản mà không hạn chế chính xác từng folder; khi đó nên dùng tài khoản/mailbox riêng và kiểm soát routing, thay vì tưởng rằng `Folder.READ_ONLY` là security boundary.

### Không quét toàn bộ lịch sử trên mỗi lần poll

Mỗi lần chạy nên xử lý theo batch, checkpoint và backpressure. Nếu cứ tải toàn bộ 100.000 thư, hệ thống có thể bị nghẽn, vượt quota và vô tình xử lý lại thư cũ. Có thể dùng IMAP UID/checkpoint hoặc provider event cursor khi phù hợp.

## 5. Credential và OAuth2: quyền đọc càng ít càng tốt

Tùy nhà cung cấp, ứng dụng nhận thư có thể xác thực qua password, app password, SASL OAuth2 hoặc cơ chế provider-specific.

### Ưu tiên identity riêng

- Không sử dụng mật khẩu mailbox cá nhân của nhân viên trong production.
- Tránh domain-wide delegation hoặc quyền quản trị rộng nếu chỉ cần đọc một mailbox.
- Với OAuth2, yêu cầu scope tối thiểu provider thực sự hỗ trợ cho việc đọc/metadata.
- Tách identity **đọc thư** khỏi identity **gửi thư**, nếu kiến trúc cho phép.
- Rotate/revoke credential theo quy trình, ghi version chứ không log giá trị.
- Bảo vệ refresh token và private key với mức nghiêm ngặt tương đương password.

Không có danh sách OAuth scope chung cho mọi IMAP provider. Một số provider hỗ trợ scope hạn chế đọc thư qua API nhưng với IMAP lại yêu cầu scope rộng hơn. Cần kiểm tra tài liệu **provider và giao thức cụ thể**; không gán tên scope giả định rồi coi là least privilege.

### Secret manager và runtime

Credential nên được inject vào workload bằng secret store/managed identity phù hợp. Không hardcode trong Java, YAML được commit, log, CI output, ticket hoặc URI connection string.

Khi secret bị rotate, tiến trình `Store` hoặc connection pool đang hoạt động có thể vẫn giữ credential/token cũ. Cần thiết kế reconnect/refresh có kiểm soát, tránh đồng thời hàng trăm worker thử login lại và bị khóa account.

### OAuth token hết hạn

Đối với access token ngắn hạn:

- Theo dõi expiry và refresh trước một safety margin.
- Không refresh riêng cho từng email trong cùng một thời điểm.
- Phân biệt token hết hạn với quyền truy cập đã bị thu hồi.
- Nếu không refresh được, tạm dừng polling hoặc đánh dấu degraded; không fallback sang password yếu hơn.
- Không đánh dấu email đã xử lý chỉ vì connection bị ngắt.

## 6. Kết nối IMAPS an toàn: TLS và timeout

IMAP thông thường dùng cổng 143 với STARTTLS (nếu được triển khai), IMAPS thường dùng cổng 993 với TLS ngay từ đầu. Không đoán mode chỉ từ port mà bỏ qua tài liệu provider.

Ví dụ cấu hình Jakarta Mail cho IMAPS bằng Java:

~~~java
import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.Store;

public final class InboundMailConnection {

    public static Store openImaps(
            String host,
            int port,
            String username,
            String secret) throws Exception {

        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.ssl.enable", "true");
        props.put("mail.imaps.ssl.checkserveridentity", "true");
        props.put("mail.imaps.connectiontimeout", "3000");
        props.put("mail.imaps.timeout", "5000");
        props.put("mail.imaps.writetimeout", "5000");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");
        store.connect(host, port, username, secret);
        return store;
    }
}
~~~

Các giá trị timeout theo đơn vị mili giây trong implementation Jakarta Mail thông dụng, chỉ mang tính minh họa. Cần đảm bảo truststore/certificate chain hợp lệ và hostname verification được bật theo policy. Đoạn này mô tả kết nối tài khoản bằng một secret runtime; nó **không tự triển khai OAuth2 token refresh hoặc giới hạn ACL của provider**.

### Nếu dùng IMAP + STARTTLS

Thiết lập khác với IMAPS: dùng protocol `imap` trên port/cấu hình provider phù hợp, yêu cầu STARTTLS qua các thuộc tính `mail.imap.starttls.enable` và `mail.imap.starttls.required` nếu library hỗ trợ. Không cho phép tự hạ xuống plaintext khi provider yêu cầu TLS.

### Không trust-all để xử lý lỗi chứng chỉ

Các mẹo như bỏ hostname verification, chấp nhận mọi certificate hoặc dùng trust-all cho production đều làm yếu bảo mật đường truyền. Khi lỗi handshake, hãy kiểm tra:

- Hostname, SNI và SAN của certificate.
- CA chain và Java truststore.
- TLS mode và port.
- Clock, certificate expiry, TLS protocol/cipher.
- DNS/egress proxy hoặc certificate của relay nội bộ.

**Timeout không phải authentication guarantee.** Một kết nối mở được và tải được thư không đủ chứng minh workload chỉ có quyền đọc những thư được phép; quyền phải được quản lý ở provider.

## 7. Đọc IMAP theo READ_ONLY và UID thay vì số thứ tự

Trong Jakarta Mail, `Store` biểu thị kết nối tới mail server và `Folder` biểu thị một thư mục. Dưới IMAP, mỗi thư có **message sequence number** có thể thay đổi khi thư khác bị xóa hoặc expunge. Do đó, không được dùng `folder.getMessage(5)` làm định danh vĩnh viễn cho một email.

IMAP còn hỗ trợ **UID** gắn với thư trong một folder và **UIDVALIDITY** cho biết phạm vi hiệu lực của các UID đó. Một khóa checkpoint có thể gồm:

~~~text
mailbox account ID
+ folder identity
+ UIDVALIDITY
+ UID
~~~

Không chỉ lưu `UID` làm khóa toàn hệ thống: UID 42 trong folder A không đồng nhất UID 42 trong folder B; khi UIDVALIDITY thay đổi, checkpoint cũ không còn ý nghĩa như trước.

### Ví dụ kết nối và duyệt một batch thư

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Store;
import jakarta.mail.UIDFolder;

public final class InboundImapPoller {

    private final InboundMessageStager stager;

    public InboundImapPoller(InboundMessageStager stager) {
        this.stager = stager;
    }

    public void poll(
            String host,
            int port,
            String username,
            String secret) throws Exception {

        Store store = InboundMailConnection.openImaps(
                host, port, username, secret);

        try {
            Folder folder = store.getFolder("INBOX");
            if (!folder.exists()) {
                throw new IllegalStateException("INBOX unavailable");
            }

            folder.open(Folder.READ_ONLY);
            try {
                if (!(folder instanceof UIDFolder uids)) {
                    throw new IllegalStateException(
                            "UID support required");
                }

                long uidValidity = uids.getUIDValidity();
                int count = folder.getMessageCount();
                int first = Math.max(1, count - 49);

                for (int number = first; number <= count; number++) {
                    Message message = folder.getMessage(number);
                    long uid = uids.getUID(message);

                    if (uid < 0) {
                        continue; // handle with a provider-specific policy
                    }

                    stager.stage(
                            "inbound-account",
                            folder.getFullName(),
                            uidValidity,
                            uid,
                            message);
                }
            } finally {
                folder.close(false); // do not expunge
            }
        } finally {
            store.close();
        }
    }
}
~~~

`InboundMessageStager` là giao diện ứng dụng cần tự triển khai. Ví dụ chỉ lấy **tối đa 50 message cuối theo sequence tại thời điểm chạy** để minh họa resource bound; đây **không phải thuật toán production để đảm bảo không bỏ sót thư**: nếu có hơn 50 email mới giữa hai lần poll, các thư cũ có thể không được duyệt. Trong production, lưu checkpoint UID, truy vấn đầy đủ phạm vi UID chưa xử lý và phân trang/batch cho tới khi hết backlog.

### Những điểm an toàn trong ví dụ

- Mở `Folder.READ_ONLY` để tránh sửa flags trên server.
- Không xóa thư, không gọi expunge.
- Lưu account/folder/UIDVALIDITY/UID vào staging.
- Đóng Folder và Store khi kết thúc hoặc gặp lỗi.
- Không dùng Subject, From hoặc RFC Message-ID làm khóa duy nhất.

### Những giới hạn cần hiểu

- UID và UIDVALIDITY là tính chất của folder hỗ trợ UID; khi chuyển email sang folder khác, UID có thể thay đổi.
- Nếu UIDVALIDITY đổi, phải có kế hoạch reconcile hoặc quét lại có idempotency; không tin checkpoint UID của phiên cũ.
- `getMessageCount()` và các thao tác fetch có thể trả dữ liệu thay đổi dưới tác động đồng thời từ server/người dùng.
- Một message có thể biến mất ngay khi worker đang đọc; phải xử lý lỗi fetch và tiếp tục an toàn.
- Một số provider có quota đối với số request/fetch; cần concurrency/rate limits.
- `Folder.READ_ONLY` là trạng thái mở folder trong client, **không thay thế quyền đọc tối thiểu ở server**.

## 8. Không dùng cờ \\Seen làm durable acknowledgment

Trong IMAP, `\\Seen` là cờ thể hiện thư đã được đánh dấu đọc. Nó **không được thiết kế như transaction marker** của ứng dụng nghiệp vụ.

Ví dụ một luồng lỗi:

~~~text
Worker fetches message
    |
    +--> server marks \\Seen
    |
    v
Application crashes before saving message
    |
    v
Next poll filters only UNSEEN
    |
    v
Message silently skipped
~~~

Nếu ứng dụng chỉ xử lý `UNSEEN`, một thao tác đọc của người dùng hoặc một client khác cũng có thể làm email biến mất khỏi tập xử lý. Nên thiết kế:

1. Duyệt theo UID/cursor hoặc nguồn event bền vững.
2. Kiểm tra inbox ledger đã xử lý hay chưa.
3. Lưu nội dung cần thiết vào vùng staging an toàn.
4. Commit trạng thái `STAGED`.
5. Xử lý bất đồng bộ và cập nhật `PROCESSED` hoặc `QUARANTINED`.
6. Chỉ move/flag sau khi kết quả được lưu và **chỉ khi account được cấp quyền phù hợp**.

Với client IMAP cần giảm thay đổi `\\Seen`, `Folder.READ_ONLY` là lựa chọn cơ bản. Một số Jakarta Mail IMAP implementation còn hỗ trợ thuộc tính `mail.imaps.peek` để fetch body mà không đánh dấu Seen; phải xác minh hành vi theo provider/version, không dựa vào cờ này như cơ chế idempotency.

### Không mark-and-delete để “dọn hộp thư”

Đối với tài khoản chỉ đọc, tránh `setFlag(Flags.Flag.DELETED, true)` và `expunge()`. Nếu cần retention hoặc archive, nên là bước riêng có quyền và audit, sau khi dữ liệu đã persist an toàn, không gắn việc xóa vào một đoạn parser có thể fail giữa chừng.

## 9. IMAP và POP3 khác nhau về phạm vi quyền

IMAP có khái niệm folder, flags và UID. POP3 thường cung cấp danh sách message trong mailbox dạng đơn giản hơn, có lệnh lấy message, UIDL (nếu server hỗ trợ), và cơ chế xóa khi session được kết thúc theo quy định.

| Khía cạnh | IMAP/IMAPS | POP3/POP3S |
| --- | --- | --- |
| Nhiều folder | Phổ biến | Thường không phải mục tiêu |
| Đồng bộ flags | Hỗ trợ | Hạn chế |
| Định danh ổn định | UID + UIDVALIDITY theo folder | UIDL nếu server hỗ trợ |
| Chế độ chỉ đọc ứng dụng | Mở folder READ_ONLY | Tránh DELE; xem quyền server |
| Theo dõi thư mới | Poll/IDLE tùy server | Polling |
| Khả năng xử lý nhiều client | Phù hợp hơn, vẫn cần đồng bộ | Tùy server, có thể hạn chế session |
| Quyền và cấu hình | Provider-specific ACL/scope | Provider-specific |

Nếu dùng POP3:

- Không dựa vào **message number** làm khóa lâu dài vì số có thể thay đổi.
- Dùng UIDL nếu được hỗ trợ và kiểm tra hành vi của provider.
- Không kích hoạt `DELE` khi chưa có quy trình retention.
- Giới hạn quyền mailbox, dữ liệu tải về và retry giống IMAP.
- Không cam kết POP3 UIDL có semantics giống UIDVALIDITY của IMAP.

Trong nhiều hệ thống, IMAP hoặc provider API phù hợp hơn cho xử lý có checkpoint, nhưng lựa chọn phụ thuộc mail server và yêu cầu nghiệp vụ.

## 10. Nhận thư theo hai pha: staging và processing

Để tránh thao tác MIME/virus scanner làm gián đoạn việc fetch và gây mất thư, có thể tách:

**Pha 1 — Ingestion/staging:**

1. Xác định message key từ account/folder/UID.
2. Kiểm tra metadata và giới hạn kích thước sơ bộ.
3. Lưu bản sao thư hoặc những phần cần thiết vào storage cách ly có giới hạn.
4. Tính hash và ghi ledger record trong trạng thái `STAGED`.
5. Acknowledge batch ingestion (không nhất thiết sửa flags ở server).

**Pha 2 — Inspection/processing:**

1. Claim bản ghi staging bằng lease.
2. Kiểm tra MIME structure, kích thước thực, type, attachment.
3. Scan malware theo chính sách.
4. Nếu an toàn và hợp lệ, trích xuất dữ liệu nghiệp vụ ở định dạng giới hạn.
5. Chạy authorization/business validation độc lập.
6. Commit kết quả xử lý có idempotency.
7. Đánh dấu `PROCESSED`, `REJECTED` hoặc `QUARANTINED`.

### Vì sao phải lưu bền vững trước?

Nếu worker đã lấy thư khỏi server hoặc đánh dấu Seen trước khi lưu, process crash có thể làm ứng dụng **không tìm lại được** thư cần xử lý. Với staging bền vững, có thể retry parse/scan khi scanner outage mà không phụ thuộc việc đọc lại mailbox từng lần.

### Idempotency của staging

Một unique key điển hình:

~~~text
tenantId
+ providerAccountId
+ folderId
+ uidValidity
+ uid
~~~

Nếu provider API cung cấp message resource ID ổn định, sử dụng theo hợp đồng API; không áp dụng cứng khóa IMAP cho mọi provider. RFC Message-ID do sender cung cấp **không đáng tin để làm khóa duy nhất** vì có thể thiếu, trùng, giả mạo hoặc thay đổi khi forward.

## 11. State machine cho thư đến

~~~mermaid
flowchart TD
    A["DISCOVERED"] --> B["FETCHING"]
    B --> C{"Staging persisted?"}
    C -- "No" --> D["RETRY_FETCH with backoff"]
    C -- "Yes" --> E["STAGED"]
    E --> F["INSPECTING"]
    F --> G{"Validation + scan"}
    G -- "Unsafe" --> H["QUARANTINED"]
    G -- "Invalid" --> I["REJECTED"]
    G -- "Scanner unavailable" --> J["RETRY_INSPECTION"]
    G -- "Allowed" --> K["READY_FOR_PROCESSING"]
    K --> L["Business handler"]
    L --> M{"Committed?"}
    M -- "No" --> N["RETRY_PROCESSING"]
    M -- "Yes" --> O["PROCESSED"]
~~~

Các trạng thái này là **mô hình ứng dụng tự định nghĩa**; Spring Mail không có sẵn enum `QUARANTINED` hay `STAGED`.

Một bản ghi có thể chứa:

| Trường | Vai trò |
| --- | --- |
| `accountId`, `tenantId` | Phân vùng và quyền truy cập |
| `folderId`, `uidValidity`, `uid` | Correlation IMAP |
| `rfcMessageId` | Thông tin tham khảo/truy vết, không làm khóa duy nhất |
| `receivedAt`, `stagedAt` | Vận hành và retention |
| `rawStorageKey` | Đối tượng cách ly được lưu an toàn |
| `rawSha256` | Phát hiện thay đổi và hỗ trợ audit |
| `status`, `stopReason` | Hành động tiếp theo |
| `attemptCount`, `nextAttemptAt` | Backoff và retry budget |
| `leaseOwner`, `leaseUntil` | Tránh nhiều worker xử lý cùng lúc |
| `inspectionVersion` | Phiên bản chính sách/engine đã kiểm tra |

Không đưa toàn bộ raw MIME hoặc nội dung email vào một cột log dễ đọc nếu không có nhu cầu; có thể lưu đối tượng cách ly với encryption, ACL và TTL rõ ràng.

## 12. Mọi thư đến phải có giới hạn tài nguyên

Email có thể có body ngắn nhưng phần MIME lớn, attachment base64 nhiều lần, nested multipart hoặc archive bung nén khổng lồ. Cần nhiều tầng giới hạn:

| Giới hạn | Rủi ro được giảm |
| --- | --- |
| Số thư fetch mỗi batch | Tránh một poll chiếm hết worker |
| Số connection/pollers đồng thời | Tránh vượt IMAP quota/provider lockout |
| Timeout connect/read/write | Không giữ worker vô hạn |
| Kích thước raw RFC 5322 message | Tránh download lưu trữ quá lớn |
| Tổng decoded bytes | Hạn chế nội dung sau Content-Transfer-Encoding |
| Số MIME parts | Tránh multipart với quá nhiều phần |
| Độ sâu multipart/message/rfc822 | Tránh cấu trúc lồng quá sâu |
| Kích thước mỗi attachment | Giới hạn file riêng lẻ |
| Tổng kích thước attachments | Ngăn nhiều file nhỏ cộng dồn |
| Thời gian parse/scan | Tránh parser/AV worker bị kẹt |
| Tổng file khi giải nén | Giảm nguy cơ archive bomb |
| Tỷ lệ nén tối đa | Giảm nguy cơ archive nhỏ bung rất lớn |
| Số URL/link/headers | Giảm tải parser, ngăn resource abuse |
| Retention/thời gian cách ly | Không tích tụ dữ liệu vô hạn |

**Không có một con số mặc định đúng cho mọi ứng dụng.** Ví dụ hệ thống nhận hóa đơn PDF có thể cho phép attachment lớn hơn hệ thống xử lý phản hồi chăm sóc khách hàng. Giới hạn phải theo nghiệp vụ, tài nguyên, quota mail server và mức độ tin cậy.

### Kích thước khai báo không phải bằng chứng cuối

`Message.getSize()`, `Part.getSize()`, `Content-Length` do provider cung cấp hoặc một header trong MIME có thể thiếu, bằng `-1`, khác kích thước nội dung tải về hoặc không phản ánh kích thước sau giải mã. Dùng chúng làm **bộ lọc sớm**, nhưng phải giới hạn số byte thực sự đọc/ghi ở tầng stream/storage.

### Giới hạn input trước khi parse

Nếu hệ thống có thể đặt giới hạn message size ở ingress/mail gateway hoặc provider, hãy dùng nó. Một đoạn code kiểm tra size sau khi thư đã tải hoàn toàn vào memory **không ngăn OOM trong bước tải**. Đối với thư đến từ IMAP, cách Jakarta Mail fetch và parse MIME có thể nội bộ buffer dữ liệu; cần phối hợp server limits, network/quota, bounded staging và giới hạn process.

## 13. Ví dụ: chặn số byte được ghi vào vùng staging

Một cách triển khai bộ đếm kích thước là wrap `OutputStream` và **ném lỗi ngay khi vượt hạn mức**, thay vì đọc mọi byte vào `byte[]` trước.

~~~java
package com.example.inbound;

import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;

public final class LimitOutputStream extends FilterOutputStream {

    private final long maxBytes;
    private long written;

    public LimitOutputStream(OutputStream out, long maxBytes) {
        super(out);
        if (maxBytes < 0) {
            throw new IllegalArgumentException("Negative size");
        }
        this.maxBytes = maxBytes;
    }

    @Override
    public void write(int value) throws IOException {
        ensureCanWrite(1);
        out.write(value);
        written++;
    }

    @Override
    public void write(byte[] data, int offset, int length)
            throws IOException {
        if (data == null) {
            throw new NullPointerException("data");
        }
        if (offset < 0 || length < 0
                || offset > data.length - length) {
            throw new IndexOutOfBoundsException();
        }
        ensureCanWrite(length);
        out.write(data, offset, length);
        written += length;
    }

    private void ensureCanWrite(long length) throws IOException {
        if (length > maxBytes - written) {
            throw new IOException(
                    "Inbound message exceeds configured limit");
        }
    }

    public long writtenBytes() {
        return written;
    }
}
~~~

Đây là **giới hạn byte đầu ra** cho nơi đang ghi. Nó không tự kiểm soát lượng dữ liệu Jakarta Mail đã tải/buffer trước khi gọi `writeTo`. Vì vậy, cần kết hợp cấu hình gateway/provider size limit, metadata check sớm, memory limit của worker và test với message lớn.

### Staging ra file tạm an toàn

~~~java
package com.example.inbound;

import jakarta.mail.Message;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RawMailStaging {

    public static Path writeBounded(
            Message message,
            Path quarantineDirectory,
            long maxRawBytes) throws Exception {

        // Directory được cấu hình bởi ứng dụng,
        // không lấy từ filename/header của email.
        Files.createDirectories(quarantineDirectory);
        Path temporary = Files.createTempFile(
                quarantineDirectory,
                "mail-stage-",
                ".eml.part");

        boolean completed = false;
        try {
            int declaredSize = message.getSize();
            if (declaredSize > maxRawBytes) {
                throw new IOException("Message too large");
            }

            try (OutputStream file = Files.newOutputStream(temporary);
                 LimitOutputStream limited =
                         new LimitOutputStream(file, maxRawBytes)) {
                message.writeTo(limited);
            }

            completed = true;
            return temporary;
        } finally {
            if (!completed) {
                Files.deleteIfExists(temporary);
            }
        }
    }
}
~~~

`message.writeTo(...)` ghi biểu diễn RFC 5322/MIME mà Jakarta Mail tạo ra từ đối tượng message. Nó **không nhất thiết bảo toàn byte-for-byte bản gốc trên wire** trong mọi tình huống, và thư viện có thể tải hoặc parse dữ liệu trước khi ghi. Nếu ứng dụng cần bằng chứng forensic nguyên vẹn, cần cơ chế raw-fetch của provider, hash nguồn và xử lý lưu trữ tương ứng, không mặc định `writeTo` là bản capture tuyệt đối.

### Những yêu cầu ngoài ví dụ

Trong production, nên:

- Dùng folder trên volume/quarantine có quyền riêng, không cho web server phục vụ trực tiếp.
- Giới hạn dung lượng disk/object store, số file và quota theo tenant.
- Đảm bảo không cho path từ email ảnh hưởng thư mục staging.
- Dùng cơ chế atomic commit/rename và database ledger phù hợp.
- Mã hóa dữ liệu lưu trữ nếu chính sách yêu cầu.
- Tính checksum khi ghi, đồng bộ storage với state record.
- Xử lý cleanup partial file khi process crash.
- Nếu `writeTo` chưa đáp ứng ràng buộc memory, chuyển sang provider raw streaming API/gateway phù hợp.

Hàm minh họa chỉ ghi tạm và trả đường dẫn. Nó **không** tự implement isolation OS/container, virus scanning, xử lý transaction hay retention.

## 14. Phân tích MIME: không tin filename và Content-Type

Một email có thể chứa:

~~~text
message/rfc822
 |
 +-- multipart/mixed
      |
      +-- multipart/alternative
      |    +-- text/plain; charset=UTF-8
      |    +-- text/html; charset=UTF-8
      |
      +-- application/pdf
      +-- application/octet-stream
      +-- message/rfc822
           +-- nested message
~~~

MIME cho phép phần lồng nhau, và `Content-Type` hoặc `Content-Disposition` được cung cấp bởi bên gửi. Một phần có tên `report.pdf` chưa chắc có nội dung PDF; `attachment` chưa chắc an toàn; `inline` cũng có thể chứa nội dung nguy hiểm.

### Các bước kiểm tra cấu trúc

1. Giới hạn tổng kích thước raw trước khi parse.
2. Giới hạn số MIME parts và độ sâu lồng.
3. Giới hạn kích thước dữ liệu sau giải mã transfer encoding.
4. Nhận diện text/plain, text/html, attachment và nested message.
5. Chuẩn hóa filename với Unicode/whitespace rules.
6. Kiểm tra phần mở rộng file theo allowlist nghiệp vụ.
7. Kiểm tra MIME type **dựa trên nội dung** bằng thư viện phù hợp, không chỉ header.
8. Scan malware và áp dụng policy về archive/encryption/macro.
9. Chỉ chuyển dữ liệu an toàn sang business handler.

### Content-Type không đáng tin như bằng chứng

Ví dụ email có thể khai báo:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
~~~

nhưng byte đầu file không phải PDF, hoặc nội dung là polyglot. Một detector như Apache Tika có thể giúp nhận diện định dạng dựa trên magic bytes và cấu trúc, nhưng **không phải anti-virus**. Một PDF đúng định dạng vẫn có thể chứa link/script/embedded object nguy hiểm. Cần policy nhiều lớp.

### Xử lý charset và transfer encoding

`Content-Transfer-Encoding` có thể là base64, quoted-printable hoặc giá trị khác. `Part.getInputStream()` của Jakarta Mail thường cung cấp luồng đã giải mã transfer encoding cho phần body; điều này có nghĩa **kích thước decoded bytes có thể khác raw bytes**. Không lấy con số `Content-Length` của header không tin cậy làm cơ sở cấp phát mảng lớn.

Với text:

- Kiểm tra charset hỗ trợ.
- Giới hạn số ký tự sau decode.
- Xác định chính sách khi charset sai hoặc dữ liệu không hợp lệ.
- Chỉ dùng text cho dữ liệu nghiệp vụ sau normalization/validation.
- Không tự chạy HTML/JavaScript trong client hoặc admin dashboard.

## 15. Ví dụ Java: giới hạn tổng MIME parts và decoded bytes

Sau khi raw message đã đi qua giới hạn staging, có thể duyệt phần MIME có guard. Ví dụ:

~~~java
package com.example.inbound;

import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.InputStream;

public final class MimeLimits {

    public record Policy(
            int maxDepth,
            int maxParts,
            long maxDecodedBytes) {

        public Policy {
            if (maxDepth < 0
                    || maxParts <= 0
                    || maxDecodedBytes <= 0) {
                throw new IllegalArgumentException("Invalid limits");
            }
        }
    }

    private static final class Budget {
        int parts;
        long decodedBytes;
    }

    public static void inspect(Part root, Policy policy)
            throws Exception {
        walk(root, 0, policy, new Budget());
    }

    private static void walk(
            Part part,
            int depth,
            Policy policy,
            Budget budget) throws Exception {

        if (depth > policy.maxDepth()) {
            throw new IllegalArgumentException(
                    "Nested MIME depth exceeded");
        }

        budget.parts++;
        if (budget.parts > policy.maxParts()) {
            throw new IllegalArgumentException(
                    "Too many MIME parts");
        }

        if (part.isMimeType("multipart/*")) {
            Object value = part.getContent();
            if (!(value instanceof Multipart multipart)) {
                throw new IllegalArgumentException(
                        "Malformed multipart content");
            }
            for (int i = 0; i < multipart.getCount(); i++) {
                walk(multipart.getBodyPart(i),
                        depth + 1, policy, budget);
            }
            return;
        }

        if (part.isMimeType("message/rfc822")) {
            Object value = part.getContent();
            if (!(value instanceof Part nested)) {
                throw new IllegalArgumentException(
                        "Malformed nested message");
            }
            walk(nested, depth + 1, policy, budget);
            return;
        }

        try (InputStream stream = part.getInputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                if (count > policy.maxDecodedBytes()
                        - budget.decodedBytes) {
                    throw new IllegalArgumentException(
                            "Decoded MIME size exceeded");
                }
                budget.decodedBytes += count;
                // Ở production: chuyển byte được giới hạn
                // tới quarantine/scanner thay vì bỏ đi.
            }
        }
    }
}
~~~

Ví dụ này trình bày **cách áp dụng budget khi duyệt MIME**; nó không phải bộ lọc MIME production hoàn chỉnh. Trong thực tế:

- `getContent()` có thể đã materialize nội dung trước khi guard duyệt đủ các phần, tùy provider/implementation.
- Một số MIME malformed hoặc nội dung không được xử lý theo đúng kiểu mong đợi có thể ném `MessagingException` hoặc `IOException`.
- `message/rfc822` có thể có các biến thể content representation phải được xử lý theo policy.
- Duyệt rồi đọc lại stream lần hai để scan có thể tiêu tốn tài nguyên và gây TOCTOU; tốt hơn là lưu dữ liệu kiểm tra vào object bất biến và scan đúng object đó.
- Giới hạn tổng decoded bytes không thay thế giới hạn kích thước từng attachment và giới hạn khi giải nén archive.
- Scanner có thể không nhận các byte sau khi chúng bị discard; trong code production cần stream/lưu dữ liệu đã giới hạn vào vùng cách ly.

### Chốt trước khi bàn giao cho business handler

Không nên gọi `businessHandler.handle(message)` từ ngay trong vòng duyệt MIME. Chỉ tạo một **đối tượng dữ liệu đã được normalize** từ những trường được phép, sau khi kiểm tra thành công toàn message và các attachment cần thiết.

## 16. Filename: một chuỗi từ bên gửi, không phải đường dẫn tin cậy

Tên file đính kèm có thể chứa:

- `../` hoặc `..\\` nhằm đi ra khỏi thư mục lưu trữ.
- Đường dẫn tuyệt đối từ Windows/Unix.
- Ký tự điều khiển, NUL, CRLF.
- Unicode confusable, ký tự hai chiều làm ẩn extension.
- Một tên quá dài hoặc có nhiều dấu chấm.
- Tên `invoice.pdf.exe` giả dạng PDF.
- Tên trùng với file khác trong quarantine.

Không làm:

~~~java
// Nguy hiểm: lấy filename từ email làm đường dẫn trực tiếp.
Path target = uploadDir.resolve(part.getFileName());
Files.copy(part.getInputStream(), target);
~~~

Thay vào đó:

1. Sinh **storage key ngẫu nhiên/UUID** không liên quan filename.
2. Lưu filename gốc như metadata đã normalize/escape để hiển thị nếu cần.
3. Kiểm tra extension allowlist chỉ sau khi đã chuẩn hóa.
4. Sniff content type từ byte thực.
5. Chặn ký tự/đường dẫn nguy hiểm.
6. Không đặt file trong thư mục được ứng dụng web phục vụ trực tiếp.
7. Dùng `CREATE_NEW` hoặc object store immutable để tránh ghi đè.

### Không dùng filename để suy ra tin cậy

Một tệp `document.pdf` có thể là tài liệu không hợp lệ hoặc nguy hiểm. Việc lưu bằng một UUID và quét malware giúp giảm rủi ro, nhưng một file sạch theo scanner không có nghĩa mọi nội dung và hành vi macro/script đều an toàn.

## 17. Allowlist định dạng attachment theo nhu cầu nghiệp vụ

Thay vì nhận tất cả file rồi cố chặn mọi đuôi nguy hiểm, nên bắt đầu từ **các định dạng thực sự cần thiết**.

Ví dụ một luồng nhận hóa đơn chỉ cho:

| Định dạng | Có thể cho phép? | Kiểm tra bổ sung |
| --- | --- | --- |
| PDF | Có, nếu nghiệp vụ cần | Signature, cấu trúc, embedded content, scan, giới hạn trang/kích thước khi trích xuất |
| PNG/JPEG | Có, nếu cần hình chứng từ | Decode ảnh trong sandbox, pixel limit, loại metadata không cần thiết |
| CSV | Có, nếu nhập dữ liệu | Encoding, row/column limits, formula injection khi export Excel |
| XML | Có, nếu có schema được kiểm soát | Chặn external entities/DTD tùy parser, schema và depth limits |
| Office document | Chỉ khi được phê duyệt | Macro, external links, ZIP structure, CDR khi cần |
| ZIP/RAR/7z | Chỉ khi thật sự cần | Giới hạn nesting, file count, decoded size, password-encryption policy |
| HTML/SVG | Thường nên chặn hoặc xử lý đặc biệt | Script, active content, external resource |
| EXE/JAR/SCRIPT | Không trong luồng hóa đơn thông thường | Không đưa vào hệ thống thực thi |
| File có password | Có thể chặn hoặc quarantine | Scanner không xem được nội dung nếu không giải mã |

Đây là chính sách ví dụ, không phải một “danh sách định dạng an toàn” chung. Nhu cầu của từng doanh nghiệp khác nhau; **sự cho phép phải được định nghĩa theo luồng**.

### So sánh khai báo và byte thực

Một chuỗi kiểm tra có thể là:

~~~text
Attachment part
  |
  +-- declared Content-Type: application/pdf
  +-- filename extension: .pdf
  +-- actual bytes / parser-detected type
  |
  v
Policy checks consistency and allowed formats
  |
  v
Malware scan + format-specific inspection
  |
  +-- Pass -> release immutable object
  +-- Fail/uncertain -> quarantine
~~~

Không “sửa” extension sai bằng cách đổi tên một file executable thành `.pdf`. Nếu header/extension và detected type mâu thuẫn, xử lý theo chính sách nghi ngờ và giữ bản gốc trong quarantine để điều tra.

## 18. Quét malware và giới hạn scanner

Một pipeline nhận thư có thể sử dụng:

- ClamAV hoặc một scanner nội bộ.
- ICAP gateway.
- Managed malware scanning service.
- Content Disarm and Reconstruction (CDR) cho một số định dạng.
- Sandbox cho những tài liệu/định dạng có rủi ro cao.

Chúng có khả năng và giới hạn khác nhau. **Không coi một nhãn “scan clean” là bảo đảm tuyệt đối.** Scanner có thể chưa có chữ ký mới, không mở được archive mã hóa hoặc không hiểu một cấu trúc file đặc biệt.

### Mô hình kết quả scanner

~~~java
public enum MalwareVerdict {
    CLEAN,
    INFECTED,
    SUSPICIOUS,
    UNSCANNABLE,
    ERROR,
    TIMEOUT
}
~~~

Một policy có thể:

| Verdict | Hành động |
| --- | --- |
| CLEAN | Cho phép chuyển sang kiểm tra tiếp theo, không tự động thực thi |
| INFECTED | Quarantine và chặn sử dụng |
| SUSPICIOUS | Quarantine/review |
| UNSCANNABLE | Quarantine; không giả định clean |
| ERROR | Retry scan có giới hạn; tạm giữ |
| TIMEOUT | Tạm giữ, giới hạn retry và alert khi tăng |

### Fail closed đối với attachment

Nếu scanner không phản hồi, không tự phát hành attachment để “không chậm nghiệp vụ”. Trạng thái đúng có thể là `SCAN_PENDING` hoặc `QUARANTINED` cho tới khi có kết quả được phép. Với luồng chỉ xử lý text/plain và không lưu attachment, policy có thể từ chối attachment ngay mà không cần tải/scan mọi loại.

### Gắn verdict với đúng byte

Để tránh **TOCTOU** (time-of-check/time-of-use):

1. Lưu file vào object bất biến hoặc vùng chỉ quarantine được ghi.
2. Tính SHA-256 và metadata version/object ID.
3. Scanner đọc **đúng object/version đó**.
4. Ghi verdict cùng hash, scanner engine/version/time.
5. Business handler chỉ đọc object có hash/version khớp verdict.
6. Nếu file được thay thế, phải scan lại.

Không scan một file tại đường dẫn A rồi sau đó cho phép process một file khác cùng filename. Dùng immutable storage keys hoặc kiểm tra hash trước khi sử dụng.

## 19. Archive bomb, tài liệu mã hóa và nested attachments

Một file ZIP nhỏ có thể giải nén thành dung lượng rất lớn; một archive có thể chứa hàng chục nghìn file hoặc nhiều lớp archive lồng. Các biện pháp:

- Giới hạn tổng uncompressed bytes.
- Giới hạn từng file và tổng số entries.
- Giới hạn nesting depth.
- Giới hạn tỷ lệ nén nếu phù hợp.
- Chặn đường dẫn `../`, đường dẫn tuyệt đối và symlink nguy hiểm.
- Không giải nén trực tiếp vào thư mục ứng dụng có quyền thực thi.
- Thiết lập CPU/time/memory/disk quota của worker.
- Xác định chính sách cho archive có password và file bị mã hóa.

Một phương án khác đơn giản hơn là **không cho phép archive** nếu nghiệp vụ chỉ cần PDF/JPEG/CSV. Giảm diện tích tấn công thường tốt hơn cố hỗ trợ mọi định dạng.

### Không giải nén file chỉ để “xem có gì” trong web controller

Nếu cần giải nén, giao cho một worker sandbox có giới hạn. Web request/IMAP polling thread nên nhanh chóng lưu staging và rời khỏi tác vụ. Khi phát hiện archive bomb, quarantine và ghi reason, không tiếp tục thử parse bằng các thư viện khác không có giới hạn.

## 20. HTML email: nội dung hiển thị cũng có thể độc hại

Email HTML có thể chứa:

- Link lừa đảo dẫn tới domain có tên gần giống.
- Image pixel truy vết và remote resource.
- `iframe`, `script`, inline event handlers hoặc biểu mẫu.
- CSS che giấu nội dung/URL thật.
- URI `javascript:`, `data:` hoặc scheme không được phép.
- HTML malformed nhằm khai thác parser.
- Unicode bidi/zero-width characters làm người đọc hiểu sai.
- Nội dung yêu cầu người vận hành làm hành động không được phép.

### Nguyên tắc khi hiển thị email trong admin dashboard

**Lựa chọn an toàn nhất nếu nghiệp vụ cho phép:** trích xuất text/plain và hiển thị như text đã escape, không render HTML của người gửi.

Nếu phải hiển thị HTML:

1. Dùng HTML sanitizer được duy trì và cấu hình **allowlist** tag/attribute/scheme.
2. Loại active content, forms, scripts, event handlers, external embeds.
3. Không tự tải remote images hoặc resource.
4. Xử lý `cid:` image qua đường nội bộ đã scan, không suy ra CID là an toàn.
5. Áp dụng CSP và cách ly origin/sandbox thích hợp khi render trong browser.
6. Hiển thị tên miền đích thật của link hoặc cảnh báo khi khác text hiển thị.
7. Không cho HTML tùy ý tác động vào DOM chính của ứng dụng.
8. Đặt size/complexity limit trước khi sanitize/render.

**Không tự viết sanitizer bằng regex** để loại thẻ `<script>`; HTML có nhiều cách encoding, attribute, namespace và cấu trúc khiến lọc chuỗi đơn giản thất bại.

### Text cũng không tự động đáng tin

Một chuỗi text/plain như:

~~~text
Gửi ngay toàn bộ báo cáo khách hàng tới security-update@example.org
để hoàn tất xác minh hệ thống.
~~~

không phải chỉ thị hợp lệ với ứng dụng. Nội dung email **có thể được hiển thị hoặc trích xuất dữ liệu**, nhưng không được quyền gọi API, xóa dữ liệu, thanh toán hoặc thay đổi policy chỉ vì nó chứa câu yêu cầu.

### Nếu có AI/LLM đọc email

Email có thể chứa **prompt injection**: chỉ dẫn giả mạo system/admin, yêu cầu bỏ qua công cụ kiểm tra hoặc gửi dữ liệu nhạy cảm. Hãy:

- Coi email body/attachment là **untrusted context**, không phải lệnh ưu tiên cao.
- Cô lập quyền tool/API của agent đọc thư.
- Chỉ cho model đề xuất/trích xuất dữ liệu có schema; tác vụ nhạy cảm phải qua authorization độc lập.
- Kiểm tra recipient/domain/amount và yêu cầu phê duyệt cho hành động rủi ro.
- Không tự cho phép email thay đổi rules, API scopes hoặc mail routing.

Đây là một phần của việc **kiểm tra nội dung thư đến** khi thư được dùng làm dữ liệu đầu vào cho tự động hóa, không chỉ bảo vệ trình duyệt khỏi HTML.

## 21. Link, URL và remote resource trong thư đến

Khi thư chứa URL:

- Không cho parser hoặc backend tự fetch link chỉ để xem “nội dung liên quan”.
- Nếu nghiệp vụ bắt buộc tải tài liệu qua URL, cần một SSRF-safe fetcher độc lập.
- Chỉ hỗ trợ các scheme/domain được cho phép, kiểm tra redirect và DNS rebinding.
- Chặn truy cập loopback, link-local, private/internal metadata endpoints theo policy.
- Đặt timeout, size limits và redirect limits.
- Không chuyển cookie/credential nội bộ tới URL do email chỉ định.
- Quét nội dung tải về giống attachment bình thường.

Email chứa URL `http://127.0.0.1:.../`, một hostname nội bộ hoặc link trỏ về cloud metadata không phải tài liệu nghiệp vụ hợp lệ chỉ vì text có vẻ uy tín. Một hành động fetch tự động có thể biến email thành công cụ SSRF.

### Tracking pixel

Nhiều email dùng ảnh từ xa để ghi nhận việc mở thư. Nếu admin dashboard tự tải ảnh của người gửi, nó có thể làm lộ IP/hành vi xem thư và kích hoạt tracking. Mặc định nên chặn remote images và chỉ cho phép khi có policy rõ ràng.

## 22. Kiểm tra header, địa chỉ gửi và tính xác thực

RFC 5322 headers như `From`, `Reply-To`, `Subject`, `Date` và `Message-ID` có thể được bên gửi cung cấp hoặc giả mạo; không được dùng chúng như bằng chứng đủ để cấp quyền.

Ví dụ:

~~~text
From: "Finance Director" <director@company.example>
Reply-To: external-billing@example.net
Subject: Urgent payment instruction
~~~

Một đoạn code kiểm tra `message.getFrom()[0]` bằng email nội bộ rồi tự xử lý yêu cầu thanh toán có thể bị tấn công khi header bị giả mạo. Cần **xác minh nguồn độc lập** theo yêu cầu nghiệp vụ.

### Authentication-Results, SPF, DKIM, DMARC

Những cơ chế này giúp đánh giá domain authentication:

- **SPF:** kiểm tra một domain identity và IP gửi theo chính sách SPF.
- **DKIM:** xác minh chữ ký gắn với domain ký.
- **DMARC:** đánh giá alignment với header From và policy domain.

Nhưng:

- Một header `Authentication-Results` xuất hiện trong raw email có thể được giả mạo nếu không xác định rõ **hệ thống nhận đáng tin đã thêm nó**.
- SPF/DKIM/DMARC pass không chứng minh nội dung email an toàn hoặc sender có quyền yêu cầu hành động nghiệp vụ.
- Một domain hợp lệ có thể bị chiếm tài khoản hoặc dùng để gửi thư độc hại.
- Forwarding/mailing list có thể làm kết quả authentication phức tạp; không có một quy tắc pass/fail áp dụng cho mọi tình huống.

Nếu provider cung cấp metadata đã xác thực tại ingress, mapping nó thành một `sourceTrust` nội bộ có thể hữu ích, nhưng vẫn cần authorization theo nghiệp vụ: người gửi nào được phép tạo ticket, gửi hóa đơn hoặc yêu cầu phê duyệt.

### Một mô hình nguồn tin cậy

| Nguồn | Mức tin cậy mặc định | Điều kiện sử dụng |
| --- | --- | --- |
| Subject/From/Reply-To header | Không đáng tin làm authority | Chỉ dùng làm dữ liệu hiển thị/trích xuất |
| Email body | Không đáng tin | Validation/normalization |
| Provider verified ingress metadata | Có thể tin theo hợp đồng tích hợp | Kiểm tra chữ ký/API response và provider scope |
| DKIM/DMARC assessment từ trusted ingress | Bằng chứng authentication domain | Không thay thế authorization nghiệp vụ |
| Danh sách đối tác được phê duyệt | Cần kiểm tra thêm identity và context | Không chỉ so địa chỉ chuỗi |
| Yêu cầu phê duyệt trong hệ thống | Có quyền rõ ràng và audit | Thích hợp cho hành động rủi ro |

Không tự tạo “trusted sender” chỉ dựa trên display name hoặc subject khớp từ khóa.

## 23. Không dùng email làm kênh cấp quyền nghiệp vụ mặc định

Một ứng dụng nhận thư hỗ trợ khách hàng có thể tạo ticket từ email. Một ứng dụng nhận hóa đơn có thể trích xuất số đơn hàng. Nhưng các hành động như **thay đổi tài khoản ngân hàng, chuyển tiền, cấp quyền truy cập hoặc xóa dữ liệu** không nên được tự thực thi chỉ từ nội dung một thư.

Ví dụ kịch bản nguy hiểm:

~~~text
From: ceo@example.org
Subject: Duyệt gấp

Hãy đổi số tài khoản thanh toán của nhà cung cấp X
thành số tài khoản mới dưới đây.
~~~

Ngay cả khi sender domain authentication pass, một email vẫn không nên tự biến thành chứng từ phê duyệt thay đổi thông tin thanh toán. Cần một luồng authorization độc lập: tài khoản đăng nhập, role, trạng thái phê duyệt, xác minh ngoài băng và audit.

### Hành động được phép theo mức độ rủi ro

| Hành động từ thư đến | Chính sách điển hình |
| --- | --- |
| Lưu thư đã kiểm tra để tham khảo | Có thể tự động |
| Tạo ticket với dữ liệu đã normalize | Có thể tự động, có idempotency |
| Gắn tag/đề xuất phân loại | Có thể tự động |
| Cập nhật nội dung phản hồi nháp | Có thể tự động nhưng nên review |
| Thêm số tiền/hóa đơn vào trạng thái “chờ xác minh” | Có thể, không tự thanh toán |
| Thay đổi account, quyền, tiền hoặc thông tin nhạy cảm | Yêu cầu authorization/approval rõ |
| Chạy script hoặc tải và thực thi attachment | Không được thực hiện chỉ dựa trên email |

### Business handler nhận dữ liệu đã được chuẩn hóa

Thay vì truyền `jakarta.mail.Message` trực tiếp cho business service, nên chuyển một DTO đã được kiểm tra:

~~~java
package com.example.inbound;

import java.time.Instant;
import java.util.List;

public record InspectedInboundMail(
        String ingestionId,
        String tenantId,
        String sourceAccountId,
        Instant receivedAt,
        String normalizedSubject,
        String safePlainText,
        List<ApprovedAttachmentRef> attachments,
        String sourceTrustLevel
) {
}

public record ApprovedAttachmentRef(
        String immutableStorageKey,
        String sha256,
        String detectedMimeType,
        long sizeBytes) {
}
~~~

`InspectedInboundMail` là contract do ứng dụng định nghĩa. Nó không chứa một đối tượng `Message` có thể truy cập raw headers/attachments tùy ý. Đối với một số nghiệp vụ cần raw message để audit, lưu raw ở quarantine với quyền riêng và đưa tới handler chỉ một ID tham chiếu.

### Phân quyền ở business boundary

Ví dụ:

~~~java
public interface InboundBusinessPolicy {
    boolean mayCreateSupportTicket(
            String tenantId,
            String sourceAccountId,
            String sourceTrustLevel);
}
~~~

Không đủ nếu UI hoặc email parser xác nhận “sender có vẻ thuộc domain đối tác”. Authorization phải kiểm tra account/tenant/workflow thật, và action handler cần có quyền tối thiểu theo service identity.

## 24. Dữ liệu trích xuất cũng phải được kiểm tra

Một email có thể chứa các trường nghiệp vụ:

~~~text
Order-ID: 1842
Invoice-Amount: 1000000
Currency: VND
Payment-Account: ...
~~~

Không nên:

- Dùng giá trị email làm SQL string nối trực tiếp.
- Đưa vào shell command hoặc file path.
- Dùng làm HTML không escape.
- Tin số tiền/địa chỉ thanh toán khi chưa đối soát.
- Gán một ticket cho tenant dựa duy nhất vào một ID được email tự khai.

### Một pipeline nhập dữ liệu hợp lý

~~~text
Safe text extraction
    |
    v
Schema validation
    |
    v
Field normalization
    |
    v
Business authorization and ownership checks
    |
    v
Idempotent persistence
    |
    v
Manual approval if risk requires it
~~~

**Schema validation** kiểm tra hình dạng dữ liệu (loại, độ dài, định dạng, enum); **business authorization** kiểm tra người/nguồn đó có quyền tạo thay đổi tương ứng. Hai bước không thay thế nhau.

### CSV/Excel formula injection

Nếu một file CSV đính kèm được dùng làm dữ liệu rồi xuất sang spreadsheet, giá trị bắt đầu bằng các ký tự công thức có thể bị ứng dụng bảng tính hiểu như formula tùy phần mềm/cấu hình. Hệ thống cần xử lý công thức theo quy tắc import/export dữ liệu, không đưa trực tiếp input không tin cậy vào worksheet dưới dạng executable formula.

### XML external entity

Nếu email chứa XML và ứng dụng dùng XML parser, cần cấu hình parser ngăn external entities/DTD theo yêu cầu an toàn để tránh đọc file nội bộ hoặc SSRF. Không coi một file `.xml` đã qua malware scan là an toàn với XML parser mặc định.

### PDF/Office extraction

Trích xuất nội dung PDF hoặc Office nên chạy trong worker có quota time/memory; document parser cũng có thể gặp file malformed hoặc khai thác lỗ hổng. Không parse tài liệu không tin cậy ngay trong process chứa quyền quản trị cơ sở dữ liệu hoặc secret store.

## 25. Giới hạn các header và metadata

Header email không chỉ có các trường quen thuộc. Một thư có thể chứa rất nhiều dòng header, header lặp lại, subject quá dài, nội dung encoded-word phức tạp hoặc địa chỉ được khai báo sai.

Những giới hạn cần có:

- Tổng số header và tổng byte header, nếu ingress/parser có thể đo.
- Kích thước Subject/From/Reply-To sau decode.
- Số lượng địa chỉ To/Cc/Bcc phù hợp nghiệp vụ.
- Chiều dài Message-ID và References.
- Số cấp reply chain/nested message nếu có.
- Số lượng MIME boundaries và body parts.
- Chính sách khi headers không parse được hoặc duplicate bất thường.

Không tự viết parser RFC 5322/MIME bằng `split("\\r\\n")` rồi giả định một header luôn nằm trên đúng một dòng. Header có line folding, encoding và nhiều trường hợp biên. Dùng Jakarta Mail hoặc thư viện chuyên dụng được cập nhật, sau đó áp dụng các giới hạn của ứng dụng.

### Header injection khi gửi thông báo phản hồi

Nếu ứng dụng tự động tạo outbound email dựa trên Subject/Reply-To inbound, phải tránh header injection và chỉ dùng API email có validation:

- Không nối nguyên raw `Subject:` vào SMTP transcript.
- Không chấp nhận CRLF tùy ý trong địa chỉ/nội dung header.
- Xác minh Reply-To theo chính sách trước khi gửi.
- Giới hạn số recipient và không gửi tới danh sách do attacker tự thêm.

Việc dùng `MimeMessageHelper` đúng cách giúp tránh một số lỗi tạo MIME thủ công, nhưng không thay thế validation và authorization.

## 26. Auto-reply và vòng lặp email

Một luồng nhận thư có thể tự động gửi email xác nhận “Đã nhận yêu cầu của bạn”. Cần tránh các vòng lặp:

~~~text
System A auto-replies to System B
    |
    v
System B auto-replies to System A
    |
    v
Infinite reply loop
~~~

Trước khi auto-reply:

- Kiểm tra request có thuộc nhóm được phép phản hồi không.
- Không phản hồi tất cả bulk mailing, automated reports hoặc bounces.
- Xem các tín hiệu chuẩn như `Auto-Submitted` (theo cách sử dụng hợp lý), nhưng không coi một header riêng lẻ là bằng chứng hoàn hảo.
- Không trả lời địa chỉ bounce/null reverse-path theo cách tạo vòng lặp.
- Dùng rate limit theo sender, conversation và tenant.
- Đặt `Auto-Submitted` thích hợp trên thư tự động do chính ứng dụng gửi nếu cần.
- Ghi idempotency key để không auto-reply lặp khi IMAP poller xử lý lại một message.

Không tự gửi attachment hoặc trích nguyên nội dung inbound vào reply nếu có thể làm lộ dữ liệu nhạy cảm.

## 27. Phân biệt email hỗ trợ và email lệnh điều khiển

Một địa chỉ `support@example.org` có thể nhận thư từ bất kỳ ai. Một địa chỉ nhận báo cáo máy móc nên giới hạn nhà gửi/đối tác và schema. Hai trường hợp có trust model khác nhau:

| Luồng | Nguồn dự kiến | Xử lý |
| --- | --- | --- |
| Support mailbox | Công khai, sender có thể bất kỳ | Tạo ticket không đặc quyền, anti-spam và attachment quarantine |
| Invoice mailbox | Đối tác đã đăng ký | Kiểm tra partner identity, PO/invoice mapping, approval |
| Automated monitoring inbox | Hệ thống nội bộ | Ưu tiên authenticated API/event thay email nếu có thể |
| HR/application mailbox | PII nhạy cảm | Quyền mailbox/retention chặt, xử lý tài liệu có kiểm soát |
| Security report mailbox | Nội dung rủi ro cao | Sandbox, quarantine, không tự thực thi chỉ dẫn |

### Email không phải kênh lệnh nội bộ có xác thực mạnh

Nếu cần kích hoạt job nhạy cảm, tốt hơn dùng API có authentication/authorization và audit. Email có thể làm **nguồn dữ liệu yêu cầu**, không nên là kênh thực thi lệnh với quyền của service account có thể thay đổi mọi hệ thống.

## 28. Phân quyền dữ liệu sau khi đã nhận thư

Sau khi message được lưu vào staging, quyền truy cập phải tiếp tục được giới hạn. Nếu không, hệ thống đã bảo vệ mailbox nhưng lại sao chép toàn bộ email vào một object store mà mọi service đều đọc được.

Các lớp quyền:

1. **Mailbox identity:** chỉ đọc đúng mailbox/folder.
2. **Ingestion worker:** chỉ ghi vào staging và ledger của tenant tương ứng.
3. **Inspection worker:** chỉ đọc object cách ly, ghi verdict.
4. **Business processor:** chỉ đọc dữ liệu đã release, không có quyền truy cập mọi raw attachment.
5. **Operator:** xem metadata/diagnostics đã làm sạch; raw mail cần quyền đặc biệt.
6. **Retention worker:** xóa theo policy có audit, không dùng chung quyền với business handler.

### Phân vùng theo tenant

Một `storageKey` cần được liên kết với `tenantId` trong database và kiểm tra quyền khi đọc. Không chỉ dựa trên tiền tố đường dẫn như `tenant-a/` nếu endpoint có thể bị gọi với storageKey của tenant khác; authorization phải được thực thi ở API/Storage policy.

### Encryption và vòng đời dữ liệu

Raw email và attachment có thể chứa PII, hợp đồng, số tài khoản hoặc dữ liệu cá nhân khác. Cần:

- Mã hóa in transit và at rest theo yêu cầu.
- Phân quyền và audit raw mail access.
- Retention riêng cho raw staging, quarantine và dữ liệu nghiệp vụ đã trích xuất.
- Cơ chế xóa hoặc giữ lại theo quy định áp dụng.
- Kiểm soát backup, snapshot và diagnostic dumps.
- Không hiển thị raw MIME trong lỗi HTTP hoặc APM.

### Tránh lưu attachment trong database nếu không cần

Một ứng dụng có thể lưu hash/object key và metadata ở database, còn binary data nằm trong object storage cách ly. Việc chọn storage phụ thuộc yêu cầu giao dịch, kích thước và kiến trúc. Quan trọng là không dùng một nơi lưu không kiểm soát quyền để “tạm chứa” attachment trước khi scan.

## 29. Processing idempotency: thư đến có thể được đọc nhiều lần

Các tình huống trùng lặp phổ biến:

- Worker crash sau staging nhưng trước khi ghi `PROCESSED`.
- IMAP poller restart và quét lại UID.
- Provider webhook được redeliver.
- UIDVALIDITY thay đổi khiến phải re-scan folder.
- Người dùng chuyển thư qua folder rồi chuyển lại.
- Hai instance cùng nhận sự kiện “new mail”.
- Một sender thực sự gửi hai email có cùng Message-ID.

Do đó, cần phân biệt:

- **Ingestion identity:** record nguồn (account/folder/UIDVALIDITY/UID).
- **Raw content hash:** giúp đối chiếu, không phải khóa duy nhất nghiệp vụ.
- **Business idempotency key:** ví dụ partner + invoice number + verified account + tenant, hoặc upstream event ID được xác thực.

Không deduplicate mọi email chỉ vì có cùng body hash: hai thư giống nhau có thể là hai yêu cầu hợp lệ. Ngược lại, chỉ dùng RFC Message-ID có thể bị giả mạo hoặc trùng; phải thiết kế theo nghiệp vụ.

### Database constraint minh họa

~~~sql
CREATE TABLE inbound_mail_ledger (
    id                   VARCHAR(100) PRIMARY KEY,
    tenant_id            VARCHAR(100) NOT NULL,
    account_id           VARCHAR(100) NOT NULL,
    folder_key           VARCHAR(250) NOT NULL,
    uid_validity         BIGINT NOT NULL,
    uid                  BIGINT NOT NULL,
    status               VARCHAR(40) NOT NULL,
    storage_key          VARCHAR(500),
    sha256               VARCHAR(64),
    attempts             INTEGER NOT NULL DEFAULT 0,
    next_attempt_at      TIMESTAMP,
    created_at           TIMESTAMP NOT NULL,
    updated_at           TIMESTAMP NOT NULL,
    UNIQUE (tenant_id, account_id, folder_key,
            uid_validity, uid)
);
~~~

Schema rút gọn: cần thêm lease/version, indexes, retention, failure classification, audit và constraints theo database. Nếu UID không có hoặc đang dùng POP3/API, chọn key tương thích với nguồn thay vì ghi UID giả.

### Không dùng sequence number làm unique key

IMAP `Message.getMessageNumber()` là vị trí biến đổi trong folder. Nếu thư đầu bị expunge, các message số 2, 3, 4 có thể chuyển thành 1, 2, 3; checkpoint bằng sequence number sẽ gắn sai nội dung.

### Atomic claim và side effects

Hai worker cùng đọc một staging record phải có cơ chế claim transactionally (optimistic CAS/lease/row locking), và business handler cần idempotent khi gọi dịch vụ khác. Unique key trên ledger giúp chống nhập trùng một nguồn, nhưng **không tự tạo exactly-once side effect** nếu worker chết sau khi đã gọi API ngoài trước khi commit.

## 30. Quy trình retry khi thư đến lỗi

Không phải mọi lỗi đọc thư đều cần retry cùng một cách.

| Nhóm lỗi | Ví dụ | Hành động phù hợp |
| --- | --- | --- |
| Kết nối tạm lỗi | DNS/IMAP server outage/read timeout | Retry fetch với backoff/jitter |
| Credential bị từ chối | OAuth2 token revoke/IMAP AUTH fail | Tạm dừng account, alert, không login storm |
| UID không còn tồn tại | Thư đã bị xóa/chuyển folder | Reconcile, không tự gán vào message khác |
| Raw message quá lớn | Vượt hard limit | Reject/quarantine theo policy, không tải lặp |
| MIME malformed | Parser không thể hiểu cấu trúc | Quarantine và reason; không retry vô hạn |
| Attachment infected | Scanner phát hiện malware | Quarantine, chặn release |
| Scanner timeout/outage | Chưa có verdict | Retry inspection, giữ object cách ly |
| Business input invalid | Thiếu invoice ID/schema sai | Hold/review hoặc reject theo nghiệp vụ |
| Downstream DB tạm lỗi | Transaction không commit | Retry business processing idempotently |
| Permission denied | Worker không được đọc folder | Sửa IAM/ACL, không thử account admin |
| Email đã xử lý | Unique key trùng | Bỏ qua hoặc reconcile trạng thái |

### Exponential backoff và ngân sách

Khi IMAP/provider tạm unavailable, dùng backoff với jitter và giới hạn concurrency. Không để mỗi thư tạo một vòng reconnect/login liên tục. Với scanner outage, retry scan **trên staging object**, không nhất thiết fetch lại email từ mailbox.

### Poison message

Một MIME malformed có thể khiến parser ném exception mỗi lần chạy. Nếu worker cứ xử lý cùng message đầu tiên rồi dừng, toàn bộ hộp thư bị kẹt. Cần:

1. Đếm attempts của từng ingestion record.
2. Phân loại lỗi permanent vs temporary.
3. Quarantine record lỗi sau ngưỡng hoặc khi đã xác định không thể parse.
4. Tiếp tục xử lý các message khác trong batch.
5. Cảnh báo khi số quarantine tăng.

Không “bỏ qua” bằng cách xóa thư gốc khỏi mailbox khi chưa đủ quyền hoặc khi cần lưu chứng cứ cho điều tra.

## 31. Spring Integration Mail: tiện lợi nhưng không bỏ qua quyền và kiểm tra

Nếu hệ thống dùng **Spring Integration**, có thể sử dụng inbound mail receiver/polling hoặc IMAP IDLE adapter để nhận thông điệp trong một integration flow. Những adapter này giúp điều phối kết nối và nhận message, nhưng **không tự biến email thành dữ liệu đáng tin**.

Khi thiết kế flow:

~~~text
Mail inbound adapter (IMAP/POP3)
        |
        v
Authenticated mailbox/source metadata
        |
        v
Inbound staging handler
        |
        v
Asynchronous inspection + quarantine gate
        |
        v
Validated event channel
        |
        v
Business service
~~~

Cần kiểm tra theo **phiên bản Spring Integration đang sử dụng**:

- Receiver hỗ trợ protocol/URL scheme nào, thuộc tính kết nối và TLS gì.
- Adapter dùng polling hay IMAP IDLE và cách reconnect khi mạng lỗi.
- Các tùy chọn auto-close folder, fetch/mark-seen và message conversion.
- Message payload là raw `MimeMessage`, `Message` hay một wrapper khác.
- Logic filter/duplicate được áp dụng trước hay sau fetch body.
- Backpressure, error channel và transaction boundary.
- Hành vi khi application crash trong lúc xử lý một event.

Không suy ra rằng message đã được “ack” bền vững chỉ vì adapter phát nó lên một in-memory channel. Nếu business handler cần bảo đảm xử lý sau restart, lưu staging/outbox-like ledger trước khi xác nhận nguồn theo hợp đồng.

### IMAP IDLE không phải exactly-once

IDLE có thể giúp nhận tín hiệu thư mới nhanh hơn polling, nhưng kết nối có thể bị ngắt, notification trùng hoặc mất trong quá trình reconnect. Vẫn cần UID/cursor reconciliation và ledger idempotent để xử lý những thư chưa hoàn thành.

### Error channel không thay quarantine

Một lỗi parse MIME có thể được đẩy tới error channel, nhưng nếu không có quy trình quarantine và state bền vững, ứng dụng có thể tiếp tục gặp cùng lỗi hoặc bỏ mất thư. Cần giữ source ID, reason và trạng thái xử lý.

## 32. Nhận email qua webhook/API cũng phải giới hạn quyền

Một số provider cung cấp inbound email parsing API hoặc webhook gửi raw message/parsed attachments. Trong trường hợp đó, thay vì IMAP credential, ứng dụng cần bảo vệ:

- Endpoint webhook qua HTTPS.
- Chữ ký hoặc authentication theo provider.
- Raw body theo quy tắc xác minh signature.
- Timestamp/replay defense khi provider hỗ trợ.
- Kích thước request body, số attachment và tổng decoded bytes.
- Provider account/tenant scope.
- Inbound event ID và dedup.
- Object storage URLs/credentials do provider trả.

**Không tin một HTTP POST có JSON giống provider event** nếu chưa xác minh nguồn. Một kẻ tấn công có thể gửi payload chứa attachment URL tới endpoint nội bộ, gây SSRF hoặc kích hoạt xử lý sai tenant.

### Acknowledge sau khi lưu bền vững

Nếu provider redeliver webhook khi không nhận 2xx, nên:

1. Verify signature.
2. Validate envelope/body size.
3. Persist event hoặc enqueue vào durable queue.
4. Chỉ trả ack thành công khi đã lưu chắc chắn.
5. Consumer xử lý với idempotency key.

Không trả 200 rồi chỉ giữ payload trong memory nếu process có thể chết trước khi persist.

### URL tải attachment do provider cung cấp

Một URL được provider gửi qua webhook không tự an toàn nếu webhook chưa được xác thực hoặc URL không có giới hạn domain. Nếu cần tải từ provider storage API, dùng SDK/API client được cấu hình đúng, xác minh resource ID, hạn chế redirect và giới hạn số byte. Không coi URL tùy ý từ email body là provider attachment URL.

## 33. Kiểm thử bảo mật hộp thư và quyền truy cập

Một bộ test cần chứng minh **cả chức năng và quyền hạn**. Những yêu cầu:

| ID | Kịch bản | Kết quả kỳ vọng |
| --- | --- | --- |
| P01 | Credential chỉ đọc mở INBOX | Đọc được metadata/message được phép |
| P02 | Credential chỉ đọc cố xóa/expunge | Server từ chối hoặc quyền được bảo vệ theo policy |
| P03 | Credential bị thử truy cập folder không được phép | Không truy cập được ở cấp server/API |
| P04 | Credential đọc mailbox tenant khác | Bị từ chối |
| P05 | Worker dùng tài khoản không có quyền gửi | Không thể gửi thư theo provider policy |
| P06 | OAuth2 token hết hạn | Refresh theo đúng flow hoặc hold, không log token |
| P07 | Token bị revoke | Không vòng login/retry vô hạn |
| P08 | TLS certificate sai hostname | Không nối qua trust-all |
| P09 | IMAP server read timeout | Retry có backoff, ledger không đánh dấu PROCESSED |
| P10 | UIDVALIDITY đổi | Checkpoint cũ không dùng bừa |
| P11 | Message sequence thay đổi do expunge | Không xử lý nhầm UID khác |
| P12 | Hai worker cùng poll một UID | Một staging logical record |
| P13 | Worker crash trước staging commit | Có thể fetch lại mà không mất thư |
| P14 | Worker crash sau business commit | Idempotency ngăn double side effect |
| P15 | Folder READ_ONLY | Không sửa flags ngoài dự kiến |
| P16 | Header From giả mạo | Không vượt authorization nghiệp vụ |
| P17 | Thư có `Authentication-Results` giả | Không tự coi là trusted ingress |
| P18 | Auto-reply to another auto-reply | Không tạo vòng lặp |

**Đừng chỉ test `Folder.READ_ONLY` bằng mock** rồi tuyên bố server ACL đã an toàn. Cần bài test với mail server/provider test identity thật sự được giới hạn quyền hoặc một môi trường staging tương đương.

### Test trong môi trường cô lập

Có thể dùng GreenMail hoặc một IMAP/SMTP server test có khả năng tạo mailbox/message để kiểm tra fetch, MIME và error handling. Tuy nhiên, cần hiểu server test có thể không mô phỏng đầy đủ OAuth2, provider-specific ACL hoặc quotas. Với những đặc tính đặc thù, dùng staging tenant được phép và dữ liệu tổng hợp.

Không truy cập hộp thư thật của nhân viên hoặc khách hàng để cố tình tạo trường hợp delete/expunge/permission denied.

## 34. Ma trận kiểm thử nội dung thư đến

| ID | Tình huống | Hành vi mong đợi |
| --- | --- | --- |
| C01 | Plain-text message bình thường | Trích xuất dữ liệu, commit một lần |
| C02 | HTML-only message | Không render trực tiếp trong DOM chính |
| C03 | Multipart alternative text + HTML | Chọn nội dung theo policy, không nhân bản side effect |
| C04 | Multipart lồng sâu quá giới hạn | Quarantine/REJECTED |
| C05 | Số MIME parts quá giới hạn | Không parse vô hạn |
| C06 | Message size vượt hạn mức raw | Từ chối staging/điều tra mà không OOM |
| C07 | Declared size nhỏ nhưng thực vượt limit | Bounded stream chặn |
| C08 | Decoded content vượt limit | Chặn dù raw nhỏ |
| C09 | Attachment filename có `../` | Không ghi ra ngoài quarantine |
| C10 | Filename có Unicode bidi/control chars | Normalize/flag theo policy |
| C11 | File `.pdf` có byte không phải PDF | Detected type mismatch, quarantine |
| C12 | EICAR test pattern theo scanner được phép | Verdict INFECTED và không release |
| C13 | Scanner timeout | Giữ nguyên quarantine, retry có budget |
| C14 | Scanner error/unsupported | Không tự gán CLEAN |
| C15 | ZIP có hàng chục nghìn entries | Entry limit chặn |
| C16 | ZIP bomb/cấp lồng lớn | Resource/expansion limits chặn |
| C17 | File mã hóa không scan được | UNSCANNABLE theo policy |
| C18 | HTML có script/event handlers | Sanitizer loại active content hoặc chỉ hiển thị text |
| C19 | HTML có remote images | Không tự tải remote content |
| C20 | Link trỏ localhost/metadata endpoint | Không SSRF fetch |
| C21 | Thư giả mạo “admin yêu cầu chạy lệnh” | Không thực hiện action không được ủy quyền |
| C22 | CSV chứa formula-like values | Export/import được xử lý như dữ liệu |
| C23 | XML có external entity | Parser không truy xuất file/URL nội bộ |
| C24 | PDF malformed | Parser sandbox/timeout, quarantine nếu cần |
| C25 | Header dài bất thường | Limit chặn hoặc safe handling |
| C26 | Message-ID bị trùng | Không gộp nhầm hai source records |
| C27 | UID giống nhau nhưng UIDVALIDITY khác | Ledger phân biệt đúng |
| C28 | Message đã `\\Seen` trước đó | Không bị bỏ sót nếu chưa STAGED |
| C29 | MIME filename/body có PII | Không lộ trong metric/log |
| C30 | Business handler lỗi sau inspection | Retry idempotent, không fetch lại/scan lại vô hạn |

Những kịch bản trên là **bài thử cần thực hiện**, không phải bằng chứng chúng đã chạy. Test security nên dùng file fixture an toàn và bộ test được tổ chức cho scanner/sandbox; không đưa malware thực chưa kiểm soát vào máy lập trình hoặc CI dùng chung.

### Test scanner không cần malware thật

Có thể mock `MalwareScanner` trả INFECTED/ERROR/TIMEOUT để test workflow. Nếu cần tích hợp scanner thật, dùng test pattern/chữ ký được chính công cụ cho phép và chạy trong môi trường cô lập. Mục đích là xác minh trạng thái quarantine và fail-closed, không thử tạo mã độc.

## 35. Unit test policy: thư chưa được scan không đi vào nghiệp vụ

Một lớp gate có thể định nghĩa:

~~~java
package com.example.inbound;

public enum InspectionState {
    NOT_STARTED,
    SCANNING,
    CLEAN_AND_VALIDATED,
    REJECTED,
    QUARANTINED,
    SCANNER_ERROR
}

public final class ProcessingGate {
    public boolean mayProcess(
            InspectionState state,
            boolean sourceAuthorized,
            boolean limitsSatisfied) {

        return state == InspectionState.CLEAN_AND_VALIDATED
                && sourceAuthorized
                && limitsSatisfied;
    }
}
~~~

JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ProcessingGateTest {

    private final ProcessingGate gate = new ProcessingGate();

    @Test
    void onlyValidatedMessageIsReleased() {
        assertTrue(gate.mayProcess(
                InspectionState.CLEAN_AND_VALIDATED,
                true, true));

        assertFalse(gate.mayProcess(
                InspectionState.SCANNING,
                true, true));

        assertFalse(gate.mayProcess(
                InspectionState.SCANNER_ERROR,
                true, true));

        assertFalse(gate.mayProcess(
                InspectionState.QUARANTINED,
                true, true));

        assertFalse(gate.mayProcess(
                InspectionState.CLEAN_AND_VALIDATED,
                false, true));

        assertFalse(gate.mayProcess(
                InspectionState.CLEAN_AND_VALIDATED,
                true, false));
    }
}
~~~

Test này chỉ xác nhận logic gate. Hệ thống thật cần kiểm tra **verdict gắn đúng immutable object/hash**, transaction state và race giữa scanner/processor. Không chỉ dựa vào một boolean do controller hoặc client truyền lên để cho phép xử lý.

## 36. Kiểm thử race giữa scan và sử dụng attachment

Một lỗi TOCTOU có thể diễn ra:

~~~text
Scanner validates object X at version 1
             |
             v
Database says CLEAN
             |
             v
Another process overwrites object X with version 2
             |
             v
Business handler reads version 2 without re-scan
~~~

Test cần chứng minh:

- Object sau staging là immutable hoặc versioned.
- Verdict lưu hash/version của object đã scan.
- Handler yêu cầu đúng hash/version.
- Object bị thay hoặc hash không khớp thì không release.
- Quyền ghi ở quarantine khác quyền đọc của business handler.

Một phép kiểm tra filename extension sau scan không thay thế được invariant này.

## 37. Giám sát và cảnh báo cho hệ thống nhận thư

Một ứng dụng có thể kết nối IMAP thành công nhưng không xử lý được bất kỳ email nào, ví dụ vì scanner outage hoặc một poison message đầu hàng đợi. Vì vậy, monitoring phải có cả chỉ số **kết nối, staging, inspection và business outcome**.

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `inbound_mail_poll_total` | Số lần poll theo account/folder |
| `inbound_mail_poll_failures_total` | Lỗi poll theo DNS/auth/TLS/timeout |
| `inbound_mail_fetch_total` | Số message được fetch |
| `inbound_mail_staged_total` | Số message lưu bền vững |
| `inbound_mail_stage_failures_total` | Số lần staging thất bại |
| `inbound_mail_duplicate_total` | Message nguồn đã có trong ledger |
| `inbound_mail_oversized_total` | Message vượt raw/decoded size limit |
| `inbound_mail_mime_rejected_total` | MIME lỗi depth/parts/format |
| `inbound_mail_attachment_rejected_total` | Attachment không được policy cho phép |
| `inbound_mail_scans_total` | Số lần scan theo verdict |
| `inbound_mail_quarantined_total` | Số message/file bị quarantine |
| `inbound_mail_processing_success_total` | Business handler commit thành công |
| `inbound_mail_processing_failures_total` | Lỗi nghiệp vụ theo reason |
| `inbound_mail_pending_age_seconds` | Tuổi record chờ xử lý |
| `inbound_mail_scanner_latency_seconds` | Độ trễ scanner |
| `inbound_mail_provider_auth_failures_total` | Lỗi xác thực mailbox |
| `inbound_mail_storage_bytes` | Dung lượng staging/quarantine |
| `inbound_mail_lease_expirations_total` | Worker bị mất lease/hết hạn |

Tên các metric là **ví dụ ứng dụng tự triển khai**, không phải metric mặc định của Spring Mail. Có thể dùng Micrometer/Spring Boot Actuator hoặc hệ thống quan sát tương đương, nhưng phải giới hạn label cardinality và quyền truy cập.

### Label hợp lý

- Account key không nhạy cảm.
- Folder type hoặc group, không đưa raw folder name chứa PII nếu không cần.
- Tenant group hoặc region theo chính sách.
- Failure category.
- MIME verdict/reason family.
- Processor type.

Tránh dùng full email address, UID, Message-ID, subject, attachment filename hoặc object storage key làm Prometheus label. Chúng có thể chứa dữ liệu cá nhân và khiến metric cardinality tăng vô hạn.

### Cảnh báo nên tạo hành động

| Tín hiệu | Điều có thể xảy ra | Hành động |
| --- | --- | --- |
| IMAP authentication failures tăng | Token hết hạn, credential revoke, policy đổi | Tạm dừng login storm, kiểm tra identity |
| Poll success nhưng staging count bằng 0 bất thường | Cursor/UID check sai, folder không có thư, filter bỏ sót | Kiểm tra checkpoint và mailbox |
| Pending age tăng | Consumer/scanner/DB lỗi | Điều tra bottleneck, tăng/điều chỉnh có kiểm soát |
| Quarantine spike | Đợt thư độc hại, parser regression hoặc policy thay | Kiểm tra nguồn, reason, mẫu an toàn |
| Scanner timeout tăng | Scanner overload/down | Giữ quarantine, xử lý công suất |
| Raw storage đầy | Retention/cleanup lỗi hoặc lưu lượng tăng | Tạm giới hạn ingestion, bảo vệ nguồn và disk |
| MIME parse failures tăng | Poison-message campaign hoặc dependency issue | Khống chế size, thử fixture cô lập |
| UIDVALIDITY thay đổi | Mailbox reset/migration | Reconciliation và checkpoint reset có kiểm soát |
| Nhiều duplicate attempts | Poller race, worker restart | Kiểm tra lease/idempotency |
| Cross-tenant access denied | Authorization bug hoặc attack | Điều tra bảo mật và metadata |

### Không đóng incident chỉ vì không còn lỗi trong log

Nếu scanner outage làm mọi attachment bị giữ, ứng dụng có thể không ném exception ở IMAP poller, nhưng **business backlog vẫn tăng**. Tiêu chí phục hồi cần gồm pending age giảm, staging/inspection/process throughput trở lại, dữ liệu vẫn được phân vùng đúng và không có record bị bỏ mất.

## 38. Logging có cấu trúc mà không làm lộ email

Một log mẫu:

~~~json
{
  "event": "inbound_mail_inspection",
  "ingestionId": "inbound-582",
  "accountKey": "support-mailbox",
  "folderKey": "INBOX",
  "status": "QUARANTINED",
  "reasonFamily": "DISALLOWED_ATTACHMENT_TYPE",
  "attachmentCount": 1,
  "sourceTrust": "UNVERIFIED"
}
~~~

Không ghi:

- Toàn bộ Subject, body hoặc headers thô.
- Recipient/sender full address nếu không cần.
- OAuth access/refresh token, IMAP password hoặc connection URL có credential.
- Nội dung attachment, tên file nhạy cảm hoặc raw scanner signature.
- Link xác thực, reset password, OTP và secret trong email.

Nếu cần raw message để phân tích sự cố, lưu trong quarantine có phân quyền/retention, và log chỉ ID tham chiếu. Với forensic access, ghi audit ai đã truy cập và vì mục đích gì.

## 39. Runbook: IMAP không thể đọc mailbox

Khi poller mất kết nối:

1. Xác định lỗi là DNS, TCP, TLS, authentication, quyền folder hay provider throttling.
2. Kiểm tra account key, host, port, protocol và TLS mode **không in credential**.
3. Xem secret rotation gần nhất, OAuth token expiry và quyền đọc.
4. Tìm xem mọi pod đều lỗi hay chỉ một vùng mạng.
5. Không retry login với credential sai liên tục.
6. Không fallback sang account admin hoặc mailbox cá nhân để “đọc thay”.
7. Giữ ledger/cursor ở trạng thái an toàn, không đánh dấu mail đã xử lý.
8. Khôi phục với một canary read-only trước khi mở toàn bộ pollers.
9. Poll/scan backlog theo batch và rate limit.
10. Đối soát UID/UIDVALIDITY, xử lý message còn pending và kiểm tra lag.

### Khi provider thay đổi quyền truy cập

Nếu một app từng có quyền đọc mailbox nhưng sau migration gặp permission denied:

- Kiểm tra provider scope/grant và resource ACL.
- Chỉ yêu cầu thêm quyền cần thiết, không xin toàn quyền tenant/domain.
- Ghi audit thay đổi access.
- Xác minh không vô tình cấp quyền gửi/delete.
- Thử lại với identity ít quyền nhất trước khi rollout.

### Khi TLS handshake thất bại

Kiểm tra certificate chain, hostname/SAN, Java truststore, TLS mode và thời gian hệ thống. Không tự tắt certificate verification để phục hồi.

## 40. Runbook: một thư gây lỗi MIME lặp lại

Triệu chứng:

~~~text
mailbox has 200 messages
processor repeatedly fails at UID 8521
pending age keeps increasing
other messages do not progress
~~~

Hướng xử lý:

1. Xác định `ingestionId` và account/folder/UID của message bị lỗi.
2. Kiểm tra error category: oversized, malformed MIME, scanner error hay unsupported file.
3. Không mở attachment trong desktop của người trực để “kiểm tra nhanh”.
4. Đưa message vào quarantine/failed state theo policy.
5. Giữ object có giới hạn quyền và retention.
6. Cho poller/consumer tiếp tục các UID khác.
7. Tạo fixture đã làm sạch để tái hiện bug parser nếu cần.
8. Khi sửa, replay đúng staging object hoặc fetch lại có kiểm soát, không reset toàn mailbox.

### Không để poison message chiếm mọi worker

Nếu một message lỗi parse luôn được retry tức thời, hàng đợi có thể bị kẹt. Cần backoff, dead-letter/quarantine, retry budget và khả năng xử lý những thư khác một cách công bằng.

## 41. Runbook: phát hiện attachment nhiễm hoặc nghi nhiễm

Khi scanner trả INFECTED/SUSPICIOUS:

1. Gắn verdict với hash/object version đã quét.
2. Chặn release attachment ra business processor và UI download thông thường.
3. Không giải nén/chạy file trong environment có quyền truy cập production secrets.
4. Ghi reason/code đã làm sạch và cảnh báo theo severity.
5. Xem nguồn mailbox, số thư liên quan và tenant scope.
6. Kiểm tra có bản cùng hash được release trước đó không; nếu có, xử lý incident theo policy.
7. Xóa hoặc lưu quarantine theo retention, không tự gửi file nghi nhiễm qua email khác.
8. Rà soát logic detection để giảm false positive mà không bỏ qua scan.

Nếu scanner **unavailable** hoặc **unscannable**, đó không phải verdict CLEAN. Giữ tạm và retry hoặc review theo rủi ro.

### Đừng tự mở file bằng phần mềm văn phòng

Một thao tác double-click trong máy người trực có thể kích hoạt macro, active content hoặc exploit. Nếu cần xem nội dung, dùng sandbox/isolated viewer và quy trình phản ứng sự cố đã được phê duyệt.

## 42. Runbook: nghi lộ quyền truy cập mailbox

Một tài khoản ingestion có thể đã lộ credential hoặc token. Các bước:

1. Kích hoạt quy trình security incident và ghi phạm vi tài khoản.
2. Xác định mailbox/folder và quyền thực sự của credential bị ảnh hưởng.
3. Revoke/rotate secret hoặc token theo mức độ khẩn cấp.
4. Kiểm tra provider audit logs về login, read, move, delete, forwarding rules và thay đổi quyền nếu có.
5. Kiểm tra luồng ingestion có bị gián đoạn hoặc bỏ sót thư.
6. Cấp lại quyền **tối thiểu**, không mở rộng để “cho chạy lại”.
7. Rollout connection identity mới và xác minh read-only.
8. Đối soát checkpoint, ledger và thư đã staging.
9. Rà soát log/CI/ticket để xử lý nguồn rò rỉ credential.
10. Xử lý nghĩa vụ bảo mật/dữ liệu cá nhân nếu có theo chính sách tổ chức.

Credential chỉ đọc vẫn có rủi ro **lộ thông tin trong mailbox**. Không đánh giá sự cố là vô hại chỉ vì attacker không thể gửi hoặc xóa thư.

## 43. Những sai lầm thường gặp

### 43.1. Dùng tài khoản cá nhân có quyền toàn bộ mailbox

Tăng phạm vi dữ liệu và rủi ro khi secret bị lộ. Dùng service mailbox/identity chuyên dụng và scope tối thiểu.

### 43.2. Chỉ mở READ_ONLY rồi coi như đã có least privilege

Client mode không thay thế ACL của provider. Credential có thể vẫn có quyền xóa hoặc đọc folder khác.

### 43.3. Sử dụng Message-ID làm khóa duy nhất

Message-ID do sender cung cấp, có thể thiếu/trùng/giả. Dùng source identity phù hợp như account/folder/UIDVALIDITY/UID cho IMAP, kết hợp business idempotency.

### 43.4. Chỉ poll UNSEEN

Một ứng dụng khác hoặc thao tác fetch có thể làm thư thành Seen trước khi business processing commit. Dùng ledger/cursor bền vững.

### 43.5. Dùng message sequence làm checkpoint

Sequence thay đổi khi mailbox expunge hoặc chỉnh sửa. Dùng UID phù hợp trong phạm vi UIDVALIDITY.

### 43.6. Tin `Message.getSize()` là giới hạn vật lý

Size có thể không có hoặc không phản ánh decoded payload. Giới hạn byte thật, gateway quotas và resource worker.

### 43.7. Tin Content-Type và filename

Khai báo từ người gửi không phải bằng chứng format. Sniff content và scan theo policy.

### 43.8. Đưa attachment vào thư mục public trước khi scan

Một file chưa được kiểm tra có thể bị tải/chạy bởi người khác. Lưu quarantine không công khai trước, chỉ release sau khi đủ điều kiện.

### 43.9. Scanner lỗi thì coi là sạch

ERROR/TIMEOUT/UNSCANNABLE không phải CLEAN. Giữ quarantine và retry có giới hạn.

### 43.10. Chỉ giới hạn compressed size

Archive bomb có thể nhỏ khi nén nhưng cực lớn khi giải nén. Cần uncompressed bytes, entries, nesting và resource quotas.

### 43.11. Render HTML raw trong dashboard

Có nguy cơ XSS/active content/tracking. Hiển thị text hoặc sanitizer + isolation được kiểm soát.

### 43.12. Backend tự fetch mọi link trong email

Có thể gây SSRF hoặc lộ credential tới server ngoài. Chỉ fetch nếu có use case được phép và safe fetcher.

### 43.13. Tin From/Reply-To là người dùng đã xác thực

Header dễ giả mạo; authentication result cũng không thay thế business authorization.

### 43.14. Tự động làm theo chỉ dẫn trong email

Nội dung email không được cấp quyền thay đổi dữ liệu, gửi tiền hoặc chạy lệnh. Tách data extraction khỏi hành động.

### 43.15. Xử lý scanner và business handler trong IMAP poll thread

Worker có thể bị chặn lâu, mất kết nối hoặc bỏ sót thư mới. Tách durable staging và asynchronous processing.

### 43.16. Dùng một token đọc toàn bộ tenant cho mọi khách hàng

Vi phạm mục tiêu least privilege và tăng blast radius. Phân vùng identity/account nếu có thể.

### 43.17. Không giới hạn raw storage/quarantine

Một chiến dịch spam có thể làm đầy disk. Cần quota, retention, backpressure và alert.

### 43.18. Không kiểm tra lại quyền khi đọc object đã scan

Một storage key từ tenant A không được cho tenant B đọc dù đã CLEAN. Quét malware và authorization là hai yêu cầu độc lập.

### 43.19. Ghi raw MIME vào log

Email có thể chứa dữ liệu cá nhân, token và attachments. Chỉ log metadata cần thiết, redaction và phân quyền.

### 43.20. Tự động xóa thư gốc khi handler gặp lỗi

Có thể mất dữ liệu không khôi phục được. Chỉ move/delete sau khi staging/processing đã được xác nhận và tài khoản có quyền được phê duyệt.

## 44. Checklist triển khai hệ thống nhận thư an toàn

### Phân quyền và kết nối

- [ ] Sử dụng service account/mailbox chuyên dụng.
- [ ] Chỉ cấp quyền đọc đúng folder/mailbox cần thiết khi provider cho phép.
- [ ] Tách credential đọc thư khỏi credential gửi/thay đổi dữ liệu.
- [ ] Không dùng domain-wide delegation quá rộng khi không cần.
- [ ] Credential/token nằm trong secret manager, có rotation và audit.
- [ ] TLS và hostname verification được bật theo protocol.
- [ ] Có connect/read/write timeout, giới hạn số kết nối và retry.
- [ ] Không fallback sang cơ chế xác thực kém an toàn khi OAuth/token lỗi.
- [ ] Có kiểm tra quyền từ **server ACL**, không chỉ client `READ_ONLY`.

### Ingestion và idempotency

- [ ] Chỉ duyệt folder đã cho phép.
- [ ] Dùng UID/UIDVALIDITY hoặc provider event ID phù hợp làm source identity.
- [ ] Không dùng message sequence number/RFC Message-ID làm khóa duy nhất.
- [ ] Có checkpoint, batch limit và khả năng reconcile khi UIDVALIDITY đổi.
- [ ] Không dùng `\\Seen` như durable acknowledgment duy nhất.
- [ ] Lưu staging bền vững trước xử lý và trước move/delete.
- [ ] Có unique constraint/lease để nhiều worker không xử lý trùng.
- [ ] Có retry budget, backoff, poison-message quarantine.
- [ ] Poller không bị một message lỗi chặn toàn bộ mailbox.

### Kiểm tra nội dung

- [ ] Raw message size có giới hạn trước/đang tải khi khả thi.
- [ ] Tổng decoded size, MIME depth và part count có giới hạn.
- [ ] Filename và header không được dùng trực tiếp làm path/authority.
- [ ] Attachment policy có allowlist theo use case.
- [ ] Declared MIME type được đối chiếu với nội dung thực.
- [ ] Archive có limits về entry count, nesting và uncompressed bytes.
- [ ] Malware scan kết quả ERROR/TIMEOUT/UNSCANNABLE không được coi CLEAN.
- [ ] Scanner verdict gắn với immutable hash/object version.
- [ ] HTML không được render raw hoặc tự fetch external resources.
- [ ] URL fetch nếu có phải có SSRF defense.
- [ ] Text/CSV/XML/PDF được xử lý với các giới hạn riêng.
- [ ] Không tin header From hay yêu cầu thực thi có trong email.

### Business, dữ liệu và vận hành

- [ ] Business handler chỉ nhận DTO đã normalize/validate.
- [ ] Các thao tác nhạy cảm dùng authorization độc lập.
- [ ] Business processing có idempotency và transaction boundary rõ.
- [ ] Storage staging/quarantine có ACL, encryption và retention.
- [ ] Raw email/PII/secret không xuất hiện trong log và metric label.
- [ ] Có dashboard cho poll success, stage, scan, quarantine, pending age.
- [ ] Có runbook cho credential/TLS/DNS, parser, scanner và malware incident.
- [ ] Có test với quyền server thực, MIME malformed, oversized và race.
- [ ] Chỉ move/delete thư gốc qua một workflow được cấp quyền và audit.

Các ô trên là công cụ lập kế hoạch triển khai, không phải bằng chứng một hệ thống cụ thể đã đáp ứng. Cần xác minh bằng kiểm thử và kiểm tra quyền thực tế trước khi dùng cho dữ liệu nhạy cảm.

## 45. Ví dụ hành trình một thư hóa đơn hợp lệ

Giả sử một email được gửi vào mailbox chỉ nhận hóa đơn:

~~~text
IMAP INBOX:
  account = invoices-inbound
  folder = INBOX
  UIDVALIDITY = 308
  UID = 7281
  one attachment = invoice.pdf
~~~

### Bước 1 — Đọc theo quyền tối thiểu

Service identity chỉ có quyền đọc INBOX được phép. Worker mở `Folder.READ_ONLY`, dùng UID key để xác định chưa staging. Không xóa hay move thư gốc.

### Bước 2 — Lưu staging

Worker kiểm tra size metadata, tải với giới hạn byte, lưu một object quarantine không công khai và ghi ledger:

~~~text
ingestionId: in-7281
accountId: invoices-inbound
folder: INBOX
uidValidity: 308
uid: 7281
status: STAGED
rawStorageKey: quarantine/random-id
~~~

### Bước 3 — Phân tích MIME

Worker giới hạn depth/part count, parse subject/text/attachment, kiểm tra rằng `invoice.pdf` đúng định dạng được phép và số byte sau decode không vượt hạn mức. Tên file gốc chỉ là metadata, không phải storage path.

### Bước 4 — Scan và release

Attachment được quét từ đúng immutable object/version. Nếu verdict CLEAN và các checks khác pass, hệ thống ghi record `ApprovedAttachmentRef`. Nếu scanner lỗi, email tiếp tục ở quarantine, không đi thẳng tới business handler.

### Bước 5 — Kiểm tra nghiệp vụ

Ứng dụng trích xuất invoice number, supplier, amount; đối chiếu với supplier đã đăng ký, đơn đặt hàng và quy trình phê duyệt. Không tự thay đổi tài khoản thanh toán chỉ vì email yêu cầu.

### Bước 6 — Commit idempotent

Database ghi invoice draft/ticket theo business idempotency key. Nếu worker crash sau commit, lần chạy lại phát hiện cùng nghiệp vụ đã xử lý, không tạo hai hóa đơn.

### Bước 7 — Ghi kết quả

Ledger chuyển `PROCESSED`, kèm timestamp và audit. Nếu workflow có move email sang folder `Processed`, thao tác đó được thực hiện riêng với credential/permission phù hợp, sau khi commit và có khả năng retry an toàn.

Đây là đường đi thành công; các nhánh lỗi như oversized/virus/invalid supplier được giữ trong state và xử lý theo policy thay vì âm thầm bỏ thư.

## 46. Ví dụ email nguy hiểm và điểm chặn

Một message giả làm hóa đơn:

~~~text
From: accounts@trusted-supplier.example
Subject: New invoice
Content-Type: multipart/mixed

Body: Please update bank account immediately.
Attachment: invoice.pdf.exe
HTML: external tracking image and misleading link
~~~

Quy trình:

1. Header From **không** tự được coi là đã xác thực.
2. HTML không được render hay tải remote tracking image.
3. Filename có double extension bị policy kiểm tra, không lưu dưới tên gốc.
4. Detector xác định actual file type; nếu executable không nằm trong allowlist, chặn.
5. Attachment chưa được CLEAN không release.
6. Business handler không đổi bank account từ một yêu cầu trong body.
7. Email được quarantine/review theo reason và audit.
8. Nguồn thư hoặc provider event được đối soát nếu cần, không tự phản hồi kèm nội dung nhạy cảm.

Điểm mạnh của thiết kế là **nhiều lớp cùng bảo vệ**, không phụ thuộc một bộ lọc duy nhất.

## 47. Câu hỏi tự kiểm tra

**1. `JavaMailSender` có phải là API nhận email của Spring không?**

Không. `JavaMailSender` chủ yếu dùng để gửi. Nhận thư thường dùng Jakarta Mail `Store`/`Folder` hoặc Spring Integration Mail/provider API.

**2. Vì sao chỉ mở `Folder.READ_ONLY` chưa đủ?**

Đó là lựa chọn chế độ truy cập folder của client, không giới hạn tất cả quyền thực tế của credential tại mail server. Cần ACL/scope tối thiểu.

**3. Nên dùng mailbox cá nhân hay service mailbox cho ingestion?**

Ưu tiên mailbox/identity chuyên dụng với phạm vi dữ liệu cần thiết; tránh dùng tài khoản cá nhân hoặc quyền quản trị rộng.

**4. OAuth2 scope đọc thư có giống nhau ở mọi provider không?**

Không. Scope phụ thuộc provider và API/IMAP protocol; cần đọc hợp đồng cụ thể và cấp quyền tối thiểu thực sự được hỗ trợ.

**5. Vì sao không nên dựa vào message sequence number trong IMAP?**

Nó có thể thay đổi khi thư bị xóa/expunge. Dùng UID trong phạm vi account/folder/UIDVALIDITY.

**6. UID có toàn cục và vĩnh viễn không?**

Không. UID gắn với folder và UIDVALIDITY; thay folder hoặc UIDVALIDITY có thể làm UID không còn tương ứng như cũ.

**7. Vì sao không dùng `\\Seen` làm dấu đã xử lý nghiệp vụ?**

Flags có thể bị thay đổi trước khi staging/commit, bởi client khác hoặc thao tác đọc; không phải durable transaction marker.

**8. Điều gì xảy ra nếu scanner mất kết nối?**

Giữ attachment ở quarantine/SCAN_PENDING và retry có giới hạn hoặc đưa vào review. Không mặc định CLEAN.

**9. Một file có extension .pdf và Content-Type application/pdf đã an toàn chưa?**

Chưa. Cả hai đều có thể do sender tự khai. Cần kiểm tra actual type, format-specific risks và malware policy.

**10. Vì sao raw size limit chưa đủ đối với ZIP?**

Archive có thể giải nén cực lớn. Cần giới hạn decoded/uncompressed bytes, nesting, entry count và resource usage.

**11. `Message.getSize()` có luôn chính xác không?**

Không. Có thể không có hoặc không phản ánh decoded content; cần kiểm tra số byte thực ở các bước tiếp nhận/lưu.

**12. Vì sao không được dùng attachment filename làm đường dẫn lưu?**

Filename là input không tin cậy, có thể chứa traversal/absolute path/control chars; dùng storage key do ứng dụng sinh và lưu filename như metadata.

**13. Có thể render HTML của email trực tiếp trong admin dashboard không?**

Không nên. Dùng text đã escape hoặc sanitizer, isolation, chặn active content và remote resources.

**14. Dấu DKIM pass có đủ chứng minh email do đúng người được ủy quyền gửi không?**

Không. Nó là bằng chứng authentication domain/signature trong ngữ cảnh phù hợp, không phải business authorization cho hành động được yêu cầu.

**15. Có được tự tải mọi link xuất hiện trong email để trích xuất dữ liệu không?**

Không. Điều đó có thể gây SSRF/tracking. Chỉ dùng safe fetcher có allowlist, IP/redirect/size/time limits khi nghiệp vụ yêu cầu.

**16. Vì sao phải phân biệt raw message ID và business idempotency key?**

Một thư nguồn có thể được đọc lại nhiều lần, còn một nghiệp vụ có thể đến qua nhiều thư hoặc các luồng khác. Cần khóa chống trùng ở cả hai ranh giới.

**17. Một email từ partner đã xác minh có được phép tự thay đổi tài khoản thanh toán không?**

Không mặc định. Hành động nhạy cảm cần kiểm tra quyền và quy trình phê duyệt độc lập.

**18. Nếu thư có MIME malformed, có nên retry vô hạn để “chờ lúc đọc được” không?**

Không. Phân loại poison message, quarantine/review sau giới hạn, không để kẹt toàn bộ queue.

**19. Khi phát hiện một thư độc hại, có nên tự xóa khỏi server ngay?**

Không mặc định. Cần chính sách retention/forensic và quyền xóa riêng; staging/quarantine trước khi thao tác destructive.

**20. Có nên để business handler mở trực tiếp `Part.getInputStream()` từ mailbox không?**

Không nên khi luồng cần bảo mật cao. Handler chỉ nên nhận dữ liệu đã kiểm tra hoặc reference đến immutable approved object, tránh vượt qua MIME/scan gate.

**21. Vì sao sandbox extraction nên tách khỏi service có nhiều secret?**

Parser tài liệu phức tạp có thể có lỗ hổng hoặc bị quá tải; isolation và quyền hạn thấp giúp giảm tác động khi file không tin cậy gây lỗi.

**22. Spring Integration IMAP IDLE có bảo đảm xử lý mỗi thư đúng một lần không?**

Không. Reconnect, redelivery và crash vẫn cần reconciliation/ledger/idempotency.

**23. Nếu một record đã được scan CLEAN nhưng object sau đó thay đổi thì sao?**

Không dùng verdict cũ cho byte mới. Scanner verdict phải gắn với hash/version, object thay đổi cần scan lại hoặc bị từ chối.

**24. Dữ liệu raw email có nên đưa vào Prometheus label không?**

Không. Nó có thể chứa PII/secret và cardinality cao. Chỉ dùng label hữu hạn, còn nội dung chi tiết nằm ở storage có quyền và retention.

**25. Những điều kiện nào phải đạt trước khi thư được xử lý nghiệp vụ?**

Quyền mailbox hợp lệ; staging bền vững; size/MIME/attachment hợp lệ; verdict scan theo chính sách; dữ liệu trích xuất đã normalize; nguồn và action được authorization; idempotency/transaction đã được thiết kế.

## Kết luận

**Giới hạn quyền và kiểm tra nội dung thư đến là hai lớp bảo vệ không thể tách rời khi dùng Spring Framework Mail cùng Jakarta Mail hoặc Spring Integration Mail.** Tài khoản nhận thư nên có scope/ACL tối thiểu, chỉ đọc mailbox/folder cần thiết, bảo vệ token/secret và không được mặc nhiên có quyền gửi, xóa hoặc quản trị. Việc fetch cần dùng UID/UIDVALIDITY hoặc source ID phù hợp, lưu staging bền vững, có checkpoint/idempotency và tránh dùng cờ `\\Seen` làm acknowledgment duy nhất.

Về nội dung, hãy coi toàn bộ header, body, HTML, URL và attachment là input không tin cậy. Giới hạn raw/decoded bytes, MIME depth và part count; kiểm tra filename, content type thực, archives và malware; xử lý scanner failure theo hướng cách ly; không tự render active HTML hoặc fetch external resources; không cho email cấp quyền thay đổi nghiệp vụ. Chỉ các DTO và immutable attachment đã được kiểm tra mới được đưa tới business handler có authorization độc lập. **Một hệ thống nhận thư an toàn không chỉ “đọc được email”, mà còn bảo đảm quyền truy cập đúng phạm vi, dữ liệu nguy hiểm không thoát khỏi quarantine, thư không bị mất khi worker gặp lỗi và mọi hành động nghiệp vụ đều có cơ sở tin cậy cùng khả năng truy vết.**
