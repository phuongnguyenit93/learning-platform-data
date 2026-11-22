# Session và kết nối đọc mailbox

Trong **Spring Framework Mail**, nhiều ví dụ tập trung vào `JavaMailSender` để **gửi thư**. Nhưng một ứng dụng còn có thể cần **đọc thư đến** từ một hộp thư: nhận phản hồi khách hàng, thu thập email báo lỗi, xử lý yêu cầu gửi đến `support@...` hoặc nhập dữ liệu từ một mailbox chung. Ở chiều đọc, thành phần trung tâm không phải `JavaMailSender` mà là các API **Jakarta Mail** như `Session`, `Store`, `Folder`, `Message` và các provider giao thức **IMAP/POP3**.

Một lỗi thiết kế phổ biến là xem `Session` như kết nối TCP đã mở. Trên thực tế, `Session` là **ngữ cảnh cấu hình của Jakarta Mail**; `Store` mới đại diện cho kết nối truy cập kho thư, `Folder` đại diện cho một thư mục trên mailbox và `Message` đại diện cho thư được truy xuất qua folder. Hiểu đúng ranh giới này sẽ giúp quản lý tài nguyên, xác thực an toàn, đọc MIME chính xác, tránh đánh dấu đã đọc hoặc xóa thư ngoài ý muốn, và xử lý việc ngắt kết nối trong quá trình đồng bộ.

Bài học hướng dẫn đầy đủ vòng đời **tạo Session → kết nối Store → mở Folder → truy xuất Message → xử lý → đóng Folder/Store**, so sánh IMAP và POP3, thiết lập IMAPS/STARTTLS, quản lý UID/flags, thực hiện polling hoặc IDLE, xây dựng service Spring dễ kiểm thử và thiết kế quy trình đọc mailbox an toàn cho production.

## 1. Các mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt `Session`, `Store`, `Folder`, `Message`, `UIDFolder` và `Transport`.
- Giải thích vì sao `JavaMailSender` thường dành cho **outbound SMTP**, không phải API đọc mailbox.
- Chọn IMAP hay POP3 theo yêu cầu ứng dụng, không chỉ theo cổng kết nối.
- Tạo Jakarta Mail `Session` với các properties riêng cho protocol đọc thư.
- Kết nối IMAPS (implicit TLS) hoặc IMAP + STARTTLS bắt buộc, kiểm tra chứng chỉ và hostname.
- Mở folder ở `READ_ONLY` hoặc `READ_WRITE` và hiểu tác động đối với mail flags.
- Đọc danh sách thư với `getMessageCount()`, `getMessages()` và `FetchProfile`.
- Hiểu giới hạn của message sequence number và vai trò của IMAP UID/UIDVALIDITY.
- Đọc phần plain text/HTML và metadata của một `MimeMessage` theo MIME tree.
- Thiết kế polling, cursor, idempotency và xử lý kết nối bị ngắt.
- Đóng tài nguyên đúng cách và tránh giữ `Message` sau khi folder đã đóng.
- Kiểm thử bằng mailbox sandbox, không phụ thuộc tài khoản cá nhân thật.

## 2. Đọc mailbox khác gửi SMTP như thế nào?

```text
                     SPRING APPLICATION
                            |
           +----------------+----------------+
           |                                 |
           v                                 v
  GỬI EMAIL (OUTBOUND)               ĐỌC EMAIL (INBOUND)
           |                                 |
    JavaMailSender                       Jakarta Mail
           |                                 |
    MimeMessageHelper                       Session
           |                                 |
    SMTP Transport                          Store
           |                                 |
    SMTP relay/provider                      Folder
           |                                 |
   Recipient mail server                    Message
```

| Nhu cầu | Giao diện thường dùng | Giao thức |
|---|---|---|
| Gửi xác nhận đơn hàng | `JavaMailSender` / `JavaMailSenderImpl` | SMTP submission |
| Gửi email HTML, attachment | `MimeMessageHelper` và `JavaMailSender` | SMTP |
| Liệt kê thư trong Inbox | `Store` + `Folder` | IMAP, đôi khi POP3 |
| Xem trạng thái unread/seen | `Folder` + `Flags` | Chủ yếu IMAP |
| Đồng bộ thư mới có định danh bền vững | `UIDFolder` khi server hỗ trợ | IMAP |
| Lấy mail mới bằng cơ chế thay đổi | IMAP IDLE hoặc polling | IMAP |
| Tải thư đơn giản ở một hộp thư | POP3 `Store`/`Folder` | POP3 |
| Cung cấp dịch vụ mailbox như Gmail/Graph API | Provider API riêng | HTTPS; không phải Jakarta Mail protocol chung |

**`JavaMailSender` không mặc định cung cấp phương thức `readInbox()`.** Dù `JavaMailSenderImpl` cũng dùng Jakarta Mail `Session` cho mục đích gửi, ứng dụng đọc mailbox nên có cấu hình và service riêng, tránh trộn outbound SMTP credentials với inbound IMAP credentials.

### 2.1. Không nhầm SMTP, IMAP và POP3

- **SMTP:** chuyển hoặc gửi email đi.
- **IMAP:** truy xuất và đồng bộ thư trên server, hỗ trợ folders và flags, thường phù hợp ứng dụng cần trạng thái mailbox.
- **POP3:** chủ yếu tải thư trong một mailbox, ít tính năng đồng bộ và folder so với IMAP.

Một mailbox provider có thể hỗ trợ cả SMTP, IMAP và POP3, nhưng **host, port, TLS mode, cơ chế xác thực và quyền truy cập** có thể khác nhau.

## 3. Mô hình Jakarta Mail Session → Store → Folder → Message

```text
Session (cấu hình và provider registry)
   |
   +--> Properties: host, TLS, timeout, auth mechanism
   |
   v
Store (IMAP/POP3 provider + connection)
   |
   +--> connect(host, port, user, credential)
   |
   v
Folder ("INBOX", "Sent", hoặc thư mục khác)
   |
   +--> open(READ_ONLY / READ_WRITE)
   |
   +--> getMessageCount()
   +--> getMessages(start, end)
   +--> search(SearchTerm)
   |
   v
Message / MimeMessage
   |
   +--> From / To / Subject / Date
   +--> Flags / UID
   +--> Content-Type / Multipart / BodyPart
   +--> Attachment / inline resources
```

### 3.1. Session là gì?

`jakarta.mail.Session` giữ các properties, authenticator và môi trường để tạo `Store` hoặc `Transport`. Nó **không tự mở một TCP socket** chỉ vì bạn gọi:

```java
Session session = Session.getInstance(properties);
```

Session có thể được tạo và dùng lại cho nhiều đợt đồng bộ khi cấu hình không thay đổi. Tránh sửa `Properties` sau khi session đã được chia sẻ giữa nhiều thread; tốt hơn là xem cấu hình đã khởi tạo như một snapshot bất biến.

### 3.2. Store là gì?

`Store` là abstraction của một **message store**. Một Store gắn với protocol provider, ví dụ `imap`, `imaps`, `pop3` hoặc `pop3s`. Khi gọi `connect(...)`, provider thiết lập kết nối và xác thực theo protocol.

Store có thể quản lý tài nguyên network và trạng thái kết nối, nên cần đóng `store.close()` khi không còn sử dụng.

### 3.3. Folder là gì?

`Folder` biểu diễn một thư mục mailbox. Trên IMAP thường có `INBOX` và các folder khác; một số provider dùng namespace/phân cấp đặc thù. Một folder phải được mở trước khi đọc nội dung hoặc thao tác với message theo các API yêu cầu folder ở trạng thái mở.

### 3.4. Message là gì?

`Message` biểu diễn email được đọc từ folder: headers, body, flags và các metadata. Nhiều provider **lazy-load** nội dung khi ứng dụng truy cập `getContent()`, vì vậy đối tượng `Message` có thể còn phụ thuộc vào Store/Folder đang mở.

Không nên đưa một `Message` sống trong session IMAP vào queue hoặc trả về Controller rồi đóng kết nối. Hãy **trích xuất dữ liệu cần thiết thành DTO/snapshot** khi folder còn mở.

### 3.5. Transport ở đâu?

`Transport` dành cho gửi qua SMTP hoặc transport provider khác, **không phải đối tượng để đọc Inbox**. Việc Store và Transport đều được tạo từ `Session` không khiến hai giao thức có cùng connection hoặc credential.

## 4. Chọn IMAP hay POP3

| Tiêu chí | IMAP | POP3 |
|---|---|---|
| Nhiều thư mục | Có, tùy provider | Thông thường không; chủ yếu INBOX |
| Đồng bộ read/unread và flags | Hỗ trợ chuẩn IMAP | Rất hạn chế, không có cùng mô hình |
| UID để theo dõi thư qua các lần polling | IMAP UID kèm UIDVALIDITY | POP3 UIDL nếu server hỗ trợ |
| Tìm kiếm trên server | Có các lệnh và SearchTerm tương ứng | Hạn chế |
| Truy cập đồng thời nhiều clients | Phù hợp hơn | Ít thích hợp khi cần đồng bộ trạng thái |
| Nhận biết thay đổi gần real-time | IMAP IDLE trên server hỗ trợ | Thường polling |
| Tải thư đơn giản | Có | Có |
| Xóa thư | Theo flags/EXPUNGE semantics | Theo POP3 DELE/QUIT semantics |
| Ứng dụng support mailbox nhiều nhân viên | Thường nên chọn | Thường không tối ưu |

**Khuyến nghị thực tế:** Nếu phải đồng bộ Inbox theo trạng thái và tránh xử lý trùng, **IMAP** thường là lựa chọn tốt hơn. Nếu chỉ tải thư từ một hộp đơn giản và provider chỉ cung cấp POP3, cần bổ sung cơ chế theo dõi UIDL hoặc fingerprint riêng, retention và idempotency.

Cả hai protocol đều không thay thế việc xử lý dữ liệu nghiệp vụ an toàn sau khi tải thư.

## 5. Các cổng và TLS mode thường gặp

| Protocol | Port phổ biến | TLS mode | JavaMail Store name |
|---|---|---|---|
| IMAP | 143 | Plain IMAP + STARTTLS nếu server hỗ trợ | `imap` |
| IMAPS | 993 | Implicit TLS, bắt đầu ngay sau TCP connect | `imaps` |
| POP3 | 110 | Plain POP3 + STLS/STARTTLS nếu hỗ trợ | `pop3` |
| POP3S | 995 | Implicit TLS | `pop3s` |

Đây là cổng phổ biến, **không phải cam kết mọi provider dùng đúng cổng đó**. Phải đối chiếu tài liệu cấu hình chính thức của dịch vụ mailbox.

### 5.1. IMAPS khác IMAP STARTTLS

Implicit TLS:

```text
Application                   IMAPS server :993
     |------ TCP connect ---------->|
     |====== TLS handshake ========|
     |      cert/hostname check     |
     |------ IMAP LOGIN/AUTH ------>|
     |------ SELECT INBOX --------->|
     |------ FETCH ---------------->|
```

STARTTLS:

```text
Application                    IMAP server :143
     |------ TCP connect ---------->|
     |<----- server greeting -------|
     |------ CAPABILITY ----------->|
     |------ STARTTLS ------------->|
     |====== TLS handshake ========|
     |      cert/hostname check     |
     |------ LOGIN/AUTH (TLS) ----->|
     |------ SELECT INBOX --------->|
```

Với môi trường cần mã hóa bắt buộc, không fallback về phiên đọc mailbox không TLS chỉ để tránh lỗi handshake.

### 5.2. Đọc mailbox vẫn phải xác minh danh tính server

TLS chỉ có ích nếu ứng dụng kiểm tra:
- certificate chain đến CA đáng tin;
- hostname kết nối khớp SAN của chứng chỉ;
- certificate chưa hết hạn;
- protocol/cipher phù hợp;
- server thực sự là mailbox endpoint dự định tin cậy.

Không dùng cách tắt certificate validation như `mail.imaps.ssl.trust=*` trong production.

## 6. Cấu hình IMAPS qua Jakarta Mail

Ví dụ dùng **IMAPS port 993**, username/password:

```java
import jakarta.mail.Session;
import jakarta.mail.Store;

import java.util.Properties;

public class ImapsConnectionExample {

    public static void connect(
            String host,
            int port,
            String username,
            String credential) throws Exception {

        Properties props = new Properties();

        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.ssl.enable", "true");
        props.put("mail.imaps.ssl.checkserveridentity", "true");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");
        props.put("mail.imaps.writetimeout", "10000");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");

        try {
            store.connect(host, port, username, credential);
            System.out.println("IMAPS connection established");
        } finally {
            if (store.isConnected()) {
                store.close();
            }
        }
    }
}
```

Trong ví dụ này:
- `Session.getInstance` chỉ tạo ngữ cảnh.
- `session.getStore("imaps")` chọn Store provider.
- `store.connect` mới bắt đầu network/TLS/AUTH.
- `isConnected()` cung cấp tín hiệu trạng thái hiện tại, nhưng network có thể ngắt bất kỳ lúc nào.
- `close()` giải phóng kết nối sau khi xong.

**Không hardcode username/password thật vào source code.** Trong production, credential phải đến từ secret manager hoặc cấu hình được bảo vệ.

### 6.1. Tiền tố properties phải đúng protocol

Đối với `imaps`, các socket timeout thường là:

```properties
mail.imaps.connectiontimeout=5000
mail.imaps.timeout=10000
mail.imaps.writetimeout=10000
mail.imaps.ssl.checkserveridentity=true
```

Với `imap`, dùng `mail.imap.*`. Với `pop3s`, dùng `mail.pop3s.*`.

Nếu viết `mail.smtp.timeout` trong service đọc IMAP, đó là thuộc tính của SMTP transport, **không tự điều khiển IMAP socket**.

### 6.2. Timeout và resource limits

- `connectiontimeout`: thời gian chờ thiết lập kết nối.
- `timeout`: giới hạn thời gian đọc socket.
- `writetimeout`: giới hạn thời gian ghi socket.
- Chúng dùng đơn vị **mili giây** theo properties Jakarta Mail tương ứng.

Các timeout này **không đồng nghĩa tổng deadline cho một lần đồng bộ**, vì có thể còn DNS, nhiều FETCH commands, xử lý MIME, attachment và database.

Khi mailbox có hàng chục nghìn thư, cần giới hạn **số thư và số bytes xử lý mỗi batch**, không chỉ tăng read timeout.

### 6.3. Cấu hình TLS protocols

Khi hạ tầng có yêu cầu cụ thể, có thể dùng:

```properties
mail.imaps.ssl.protocols=TLSv1.2 TLSv1.3
```

Tên phiên bản phụ thuộc Java runtime và server. Không bật TLS 1.0/1.1 hoặc cipher yếu chỉ để vượt lỗi, thay vào đó cập nhật server/provider khi có thể.

## 7. Cấu hình IMAP STARTTLS trên port 143

Nếu provider yêu cầu IMAP thường rồi nâng cấp TLS:

```java
Properties props = new Properties();

props.put("mail.store.protocol", "imap");
props.put("mail.imap.starttls.enable", "true");
props.put("mail.imap.starttls.required", "true");
props.put("mail.imap.ssl.checkserveridentity", "true");
props.put("mail.imap.connectiontimeout", "5000");
props.put("mail.imap.timeout", "10000");
props.put("mail.imap.writetimeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("imap");

try {
    store.connect(
        "imap.example.com",
        143,
        "reader@example.com",
        mailboxCredential
    );

    // Chỉ xử lý mailbox sau khi kết nối và TLS hợp lệ.
} finally {
    if (store.isConnected()) {
        store.close();
    }
}
```

`mailboxCredential` là biến chứa credential do lớp cấu hình bảo mật cung cấp, không phải literal placeholder mà Java có sẵn.

Các điểm khác IMAPS:
- Protocol là `imap`, không phải `imaps`.
- TLS bắt đầu **sau lệnh STARTTLS**.
- `starttls.required=true` giúp không tiếp tục nếu server không hỗ trợ bắt buộc nâng cấp.
- `ssl.checkserveridentity=true` vẫn cần thiết.

Không dùng `mail.imap.ssl.enable=true` một cách tùy tiện trên endpoint chỉ hỗ trợ STARTTLS; cần chọn TLS mode đúng theo server.

## 8. Kết nối POP3/POP3S

Để tải email qua POP3S port 995:

```java
Properties props = new Properties();

props.put("mail.store.protocol", "pop3s");
props.put("mail.pop3s.ssl.enable", "true");
props.put("mail.pop3s.ssl.checkserveridentity", "true");
props.put("mail.pop3s.connectiontimeout", "5000");
props.put("mail.pop3s.timeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("pop3s");

try {
    store.connect(
        "pop.example.com",
        995,
        "reader@example.com",
        mailboxCredential
    );

    Folder inbox = store.getFolder("INBOX");
    inbox.open(Folder.READ_ONLY);

    try {
        System.out.println(
            "Messages: " + inbox.getMessageCount()
        );
    } finally {
        if (inbox.isOpen()) {
            inbox.close(false);
        }
    }
} finally {
    if (store.isConnected()) {
        store.close();
    }
}
```

Cần import `jakarta.mail.Folder`.

Với POP3:
- Thường chỉ có INBOX.
- Không có mô hình folders/flags/UID tương đương IMAP.
- Việc xóa thư có semantics khác, cần tránh tự đánh dấu DELETED.
- UIDL hỗ trợ tùy server; nếu cần theo dõi thư qua nhiều lần polling, phải kiểm tra cụ thể khả năng provider.
- Không nên dùng POP3 nếu bài toán cần đồng bộ thư mục và trạng thái nhiều clients.

## 9. Spring Boot không tự biến JavaMailSender thành mailbox reader

Thuộc tính thường thấy:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
```

được dùng chủ yếu cho **mail sending auto-configuration**. Để đọc Inbox, thiết kế cấu hình riêng:

```yaml
app:
  mailbox:
    host: imap.example.com
    port: 993
    protocol: imaps
    username: ${MAILBOX_USERNAME}
    password: ${MAILBOX_PASSWORD}
    folder: INBOX
    batch-size: 100
    poll-interval: 30s
```

Điều này giúp:
- tránh nhầm SMTP host với IMAP host;
- tách credential đọc mailbox và gửi SMTP;
- tách timeout, TLS mode, folder và polling;
- có thể bật/tắt mailbox consumer độc lập;
- kiểm soát quyền của từng thành phần.

`app.mailbox.*` là namespace **do ứng dụng định nghĩa**, không phải thuộc tính Spring Boot có sẵn tự tạo IMAP reader.

### 9.1. ConfigurationProperties

Ví dụ cấu hình dưới dạng record:

```java
package com.example.mailbox;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mailbox")
public record MailboxProperties(
    String host,
    int port,
    String protocol,
    String username,
    String password,
    String folder,
    int batchSize,
    Duration pollInterval
) {}
```

Từ metadata trên, ứng dụng nên kiểm tra:
- `protocol` nằm trong tập cho phép;
- `host` thuộc endpoint được quản trị phê duyệt;
- `port` hợp lệ;
- `batchSize` dương và có giới hạn;
- `folder` được phép truy cập;
- thông tin xác thực có sẵn hoặc OAuth2 được cấu hình theo policy;
- `pollInterval` không quá nhỏ gây tải;
- TLS và certificate validation không bị tắt.

Không log nguyên record cấu hình nếu chứa password.

## 10. Service mở và đọc Inbox cơ bản

Ví dụ dưới đây minh họa một vòng polling với **kết nối IMAPS và Folder READ_ONLY**. Mục đích là hiểu đúng vòng đời và không giữ tài nguyên sau khi kết thúc.

```java
package com.example.mailbox;

import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;

import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

public final class SimpleImapReader {

    private final String host;
    private final int port;
    private final String username;
    private final String password;

    public SimpleImapReader(
            String host,
            int port,
            String username,
            String password) {
        this.host = host;
        this.port = port;
        this.username = username;
        this.password = password;
    }

    public List<MailSummary> readLatest(int limit)
            throws Exception {

        if (limit < 1) {
            throw new IllegalArgumentException(
                "limit must be positive"
            );
        }

        Properties props = new Properties();
        props.put("mail.imaps.ssl.enable", "true");
        props.put("mail.imaps.ssl.checkserveridentity", "true");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");
        Folder inbox = null;

        try {
            store.connect(host, port, username, password);

            inbox = store.getFolder("INBOX");
            inbox.open(Folder.READ_ONLY);

            int count = inbox.getMessageCount();
            if (count == 0) {
                return List.of();
            }

            int first = Math.max(1, count - limit + 1);
            Message[] messages =
                inbox.getMessages(first, count);

            List<MailSummary> result = new ArrayList<>();

            for (Message message : messages) {
                result.add(new MailSummary(
                    message.getMessageNumber(),
                    message.getSubject(),
                    message.getReceivedDate(),
                    message.getContentType()
                ));
            }

            return List.copyOf(result);
        } finally {
            try {
                if (inbox != null && inbox.isOpen()) {
                    inbox.close(false);
                }
            } finally {
                if (store.isConnected()) {
                    store.close();
                }
            }
        }
    }

    public record MailSummary(
        int messageNumber,
        String subject,
        java.util.Date receivedDate,
        String contentType
    ) {}
}
```

Điểm đáng chú ý:

1. `Session` không gọi network khi tạo.
2. `Store.connect` mở kết nối và xác thực.
3. `Folder.open(READ_ONLY)` lấy quyền đọc folder.
4. `getMessageCount` cung cấp số message hiện có.
5. `getMessages(first,count)` trả messages trong đoạn sequence numbers hợp lệ.
6. Chuyển message thành **snapshot DTO** khi folder còn mở.
7. `close(false)` không yêu cầu expunge các message đánh dấu deleted.
8. `Store.close` giải phóng network resources.

Đây là **ví dụ đọc một phần Inbox**, chưa phải đồng bộ bền vững: `messageNumber` chỉ là sequence number tại thời điểm folder đang mở, **không nên dùng làm khóa database lâu dài**.

### 10.1. Nếu Folder hoặc Store.close cũng ném exception?

Đoạn `finally` lồng nhau giúp cố đóng Store nếu đóng Folder lỗi. Trong production, cần có policy ghi nhận lỗi cleanup mà không che mất nguyên nhân chính; có thể dùng helper quản lý tài nguyên với suppressed exceptions hoặc logging kiểm soát.

Không bỏ `close` chỉ vì đoạn code muốn ngắn.

## 11. READ_ONLY và READ_WRITE ảnh hưởng thế nào?

Khi mở folder:

```java
folder.open(Folder.READ_ONLY);
```

ứng dụng yêu cầu chỉ đọc. Đây thường là lựa chọn tốt cho **ingestion worker** khi việc xử lý và trạng thái đã được theo dõi trong database riêng.

Khi cần cập nhật flags:

```java
folder.open(Folder.READ_WRITE);
```

Có thể thực hiện hành động được server/provider hỗ trợ, ví dụ đánh dấu `SEEN` hoặc `DELETED`. READ_WRITE cần được dùng thận trọng, vì tác động có thể nhìn thấy bởi người dùng và client khác.

### 11.1. Không đánh dấu đã đọc chỉ để “lấy email”

Một phương thức đọc body có thể ảnh hưởng `SEEN` tùy protocol, provider và cách FETCH. Đừng mặc định mọi `getContent()` là hoàn toàn không thay đổi trạng thái trong mọi cấu hình.

Đối với ingestion:
- mở folder `READ_ONLY` khi chỉ cần đọc;
- theo dõi xử lý trong DB riêng;
- kiểm tra hành vi `SEEN` trong integration test với provider thực tế;
- nếu cần `READ_WRITE`, áp dụng policy rõ ràng và cập nhật flags sau khi nghiệp vụ đã persist thành công.

### 11.2. Flags thường gặp

```java
import jakarta.mail.Flags;
import jakarta.mail.Message;

boolean seen = message.isSet(Flags.Flag.SEEN);
boolean deleted = message.isSet(Flags.Flag.DELETED);
boolean answered = message.isSet(Flags.Flag.ANSWERED);
```

Một số IMAP servers còn hỗ trợ user-defined flags/keywords. Không giả định mọi flags có thể đọc/ghi giống nhau ở mọi provider.

### 11.3. Đánh dấu đã xử lý không đồng nghĩa đặt SEEN

`\Seen` là trạng thái mailbox hiển thị cho mail client, **không phải ACK giao dịch bền vững** rằng ứng dụng đã parse nội dung, lưu database và hoàn thành business process.

Nếu dùng `SEEN` làm tín hiệu đã xử lý:
- người dùng có thể mở email trước khi worker đọc;
- một client khác có thể đổi flag;
- worker có thể đặt SEEN rồi crash trước khi lưu DB;
- status mailbox có thể bị reset hoặc chuyển thư.

Phù hợp hơn là dùng **IMAP UID + dữ liệu idempotency trong DB** và chỉ đặt SEEN theo yêu cầu UX sau khi xử lý chắc chắn.

## 12. Message sequence number không phải ID bền vững

IMAP `messageNumber` là vị trí của message trong folder ở thời điểm truy cập.

Ví dụ:

```text
INBOX:
  sequence #1 -> Mail A
  sequence #2 -> Mail B
  sequence #3 -> Mail C
```

Nếu Mail B bị expunge, sequence numbers có thể được đánh lại:

```text
INBOX:
  sequence #1 -> Mail A
  sequence #2 -> Mail C
```

Nếu ứng dụng lưu `lastMessageNumber=2` rồi coi mọi thư có số lớn hơn là thư mới, có thể bỏ sót hoặc xử lý sai khi messages bị xóa/chuyển folder.

**Không dùng message sequence number làm cursor đồng bộ bền vững qua nhiều kết nối.**

### 12.1. UID trong IMAP

IMAP cung cấp **UID** để định danh message bền vững hơn **trong phạm vi một folder và một UIDVALIDITY**. Jakarta Mail biểu diễn qua `UIDFolder`:

```java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

Folder folder = store.getFolder("INBOX");
folder.open(Folder.READ_ONLY);

if (folder instanceof UIDFolder uidFolder) {
    long uidValidity = uidFolder.getUIDValidity();

    Message[] messages =
        uidFolder.getMessagesByUID(1L, UIDFolder.LASTUID);

    for (Message message : messages) {
        long uid = uidFolder.getUID(message);

        System.out.println(
            "UIDVALIDITY=" + uidValidity + ", UID=" + uid
        );
    }
}
```

Đoạn ví dụ cho thấy API UID, nhưng gọi từ UID 1 đến UID cuối cho mailbox lớn có thể trả quá nhiều messages. Trong production cần **đọc theo khoảng và batch** dựa trên cursor đã lưu, kết hợp giới hạn kích thước và số lượng.

### 12.2. Khóa xử lý bền vững

Một identity phù hợp cho một email tại vị trí IMAP:

```text
(mailbox_account_id, folder_id, uid_validity, uid)
```

Không chỉ dùng UID đơn lẻ vì:
- UID chỉ unique trong phạm vi một folder tại một giá trị UIDVALIDITY;
- một mailbox account khác có thể dùng cùng UID;
- UIDVALIDITY có thể thay đổi khi server tái tạo folder;
- khi chuyển hoặc copy thư sang folder khác, UID có thể khác.

### 12.3. UIDVALIDITY thay đổi thì sao?

Nếu server trả `UIDVALIDITY` mới, ứng dụng không được tiếp tục dùng cursor UID cũ như thể cùng tập thư. Phải chuyển sang quy trình **resynchronization** theo policy:
- nhận diện UIDVALIDITY đã thay đổi;
- lưu một thế hệ folder mới;
- quét lại theo batch;
- deduplicate ở tầng nghiệp vụ để hạn chế phát sự kiện trùng;
- giữ lịch sử audit.

Không giả định các UID qua hai thế hệ có cùng ý nghĩa.

## 13. Message-ID có thể hỗ trợ nhưng không thay UID

Header `Message-ID` có thể giúp đối chiếu một email logic:

```text
Message-ID: <example-123@mail.example>
```

Nhưng:
- có thư thiếu Message-ID;
- có thư trùng Message-ID do cấu hình lỗi hoặc copy;
- cùng message có thể được chuyển/copy giữa folders;
- Message-ID không phải khóa duy nhất được mọi mailbox server bảo đảm.

Một ingestion pipeline có thể lưu cả:
- mailbox/folder/UIDVALIDITY/UID để đồng bộ;
- Message-ID đã chuẩn hóa ở mức hợp lý;
- hash hoặc business correlation ID khi cần;
- processing status và nguồn phát.

**Không deduplicate mọi email chỉ bằng Message-ID** nếu mục tiêu phải xử lý những thư được gửi riêng cho các accounts hoặc các copies khác nhau.

## 14. FetchProfile giúp giảm round trips nhưng không tải tất cả body

Khi cần liệt kê nhiều emails, gọi từng property có thể gây nhiều network requests tùy provider. `FetchProfile` cho phép provider biết các trường nên lấy trước.

Ví dụ:

```java
import jakarta.mail.FetchProfile;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

Message[] page = folder.getMessages(first, last);

FetchProfile profile = new FetchProfile();
profile.add(FetchProfile.Item.ENVELOPE);
profile.add(FetchProfile.Item.FLAGS);
profile.add(FetchProfile.Item.CONTENT_INFO);
profile.add(UIDFolder.FetchProfileItem.UID);

folder.fetch(page, profile);
```

Các trường prefetched có thể bao gồm:
- metadata From/Subject/Date;
- flags;
- content information;
- UID nếu provider hỗ trợ.

**`FetchProfile` không đảm bảo toàn bộ MIME body/attachments đã được tải**, cũng không tự giới hạn số bytes. Hãy đọc body chỉ khi cần và có ngân sách tài nguyên rõ ràng.

### 14.1. Tránh quét toàn bộ mailbox mỗi vòng

Cách không phù hợp cho mailbox có hàng trăm nghìn thư:

```java
Message[] all = folder.getMessages();
for (Message m : all) {
    process(m);
}
```

Nó có thể tạo mảng rất lớn, nhiều network I/O, thời gian đọc dài và memory pressure.

Cách phù hợp:
- dùng UID cursor;
- lấy một batch nhỏ theo UID range;
- chỉ fetch headers cần thiết trước;
- áp dụng giới hạn attachment/MIME body;
- có giới hạn số thư trên mỗi poll;
- lưu checkpoint sau mỗi record hoặc batch đã xử lý thành công.

### 14.2. SearchTerm không thay ID bền vững

Có thể lọc trên server:

```java
import jakarta.mail.Flags;
import jakarta.mail.search.FlagTerm;

Message[] unseen = folder.search(
    new FlagTerm(
        new Flags(Flags.Flag.SEEN),
        false
    )
);
```

Đây là ví dụ tìm thư **chưa được đánh dấu SEEN**, không phải “chưa được ứng dụng xử lý”. Với mailbox nhiều clients, SEEN thay đổi độc lập với ingestion. Search có thể hữu ích để giảm tập thư, nhưng cursor/idempotency vẫn cần dựa trên cơ chế bền vững hơn.

## 15. Đọc MIME body: plain text, HTML và attachment

Một email nhận về không nhất thiết là `String`:

```text
MimeMessage
   |
   +-- multipart/mixed
       |
       +-- multipart/alternative
       |    |
       |    +-- text/plain
       |    +-- text/html
       |
       +-- application/pdf (attachment)
```

`Message.getContent()` có thể trả:
- `String` đối với text body;
- `Multipart` cho multipart;
- `InputStream` hoặc đối tượng khác tùy MIME type/provider;
- đôi khi `Message` lồng nhau với `message/rfc822`.

Không ép kiểu mù:

```java
String body = (String) message.getContent();
```

vì email multipart sẽ gây lỗi.

### 15.1. MIME content extractor cơ bản

```java
package com.example.mailbox;

import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.util.ArrayList;
import java.util.List;

public final class TextPartExtractor {

    private TextPartExtractor() {}

    public static List<String> collect(
            Part root,
            String mimeType) throws Exception {

        List<String> output = new ArrayList<>();
        visit(root, mimeType, output);
        return List.copyOf(output);
    }

    private static void visit(
            Part part,
            String mimeType,
            List<String> output) throws Exception {

        // Không coi text attachment là email body.
        String disposition = part.getDisposition();
        if (Part.ATTACHMENT.equalsIgnoreCase(disposition)) {
            return;
        }

        if (part.isMimeType(mimeType)) {
            Object content = part.getContent();

            if (content instanceof String text) {
                output.add(text);
            }
            return;
        }

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                visit(
                    multipart.getBodyPart(i),
                    mimeType,
                    output
                );
            }
        }
    }
}
```

Dùng:

```java
List<String> plainTexts =
    TextPartExtractor.collect(message, "text/plain");

List<String> htmlTexts =
    TextPartExtractor.collect(message, "text/html");
```

Đây là **ví dụ minh họa MIME traversal**, chưa phải parser production cho email không đáng tin. Hệ thống thực cần xét:
- MIME lồng sâu, `message/rfc822`;
- `multipart/alternative`: chọn một representation thích hợp thay vì nối tất cả;
- attachment text có disposition thiếu hoặc không chuẩn;
- charset lỗi hoặc content transfer encoding bất thường;
- giới hạn tổng bytes, số parts, depth;
- nội dung HTML độc hại, tracking URLs;
- stream lifecycle và zip bombs.

### 15.2. Ưu tiên plain text khi nghiệp vụ chỉ cần văn bản

Nếu cần trích nội dung ticket:
1. Tìm phần `text/plain` body phù hợp.
2. Nếu không có, có thể chuyển HTML sang plain text bằng parser được kiểm soát.
3. Không render HTML trực tiếp vào admin dashboard nếu chưa sanitize.
4. Cẩn thận với các phần quoted history, signature, forwarded messages.

HTML email là dữ liệu **không tin cậy**, kể cả khi đến từ mailbox nội bộ. Không tự xem `getContent()` là kết quả đã an toàn cho trình duyệt.

### 15.3. Đừng tự tạo network calls khi parse HTML

Khi parse:
- không tự tải ảnh và stylesheet từ URL trong email;
- không resolve `file:`, `http:` hoặc các external entities tùy ý;
- không chạy JavaScript;
- không tự động mở URL chứa token;
- không đưa HTML raw vào template web.

Mục tiêu là trích xuất dữ liệu, không mô phỏng mail client có đầy đủ active content.

## 16. Attachment cần xử lý như dữ liệu không đáng tin

Một mailbox reader có thể nhận PDF, ZIP, hình ảnh hoặc tệp chưa rõ định dạng. Hãy áp dụng:
- giới hạn số attachment;
- giới hạn kích thước từng attachment và toàn message;
- allowlist loại file theo business need;
- kiểm tra MIME type và nội dung thật;
- scan malware/CDR theo chính sách;
- chống path traversal và filename độc hại;
- lưu file vào vị trí quarantine trước khi sử dụng;
- không thực thi hoặc tự mở attachment;
- mã hóa, retention và phân quyền access.

`Part.getFileName()` là dữ liệu từ email, không an toàn để ghép trực tiếp vào đường dẫn filesystem.

### 16.1. Đọc stream có giới hạn

Không dùng `readAllBytes()` vô điều kiện cho một attachment rất lớn. Nếu phải lưu file:
- stream theo chunks;
- đếm bytes;
- từ chối vượt limit;
- đặt filename được sinh bởi server;
- chỉ lưu metadata/scan result cho bước tiếp theo;
- đảm bảo resource được đóng.

Với MIME có nested attachments hoặc dữ liệu nén, giới hạn cần kiểm tra cả kích thước sau giải nén nếu có xử lý archive.

### 16.2. Không giữ MimeMessage sống trong queue

Sau khi folder/Store đóng, những MIME parts lazy-loaded có thể không đọc được nữa. Nếu cần xử lý attachment bất đồng bộ, hãy persist snapshot hoặc object-storage reference trước khi đóng kết nối, có quota và encryption phù hợp.

## 17. Thiết kế đồng bộ IMAP theo UID cursor

Một pipeline bền vững có thể như sau:

```text
Scheduled poll
    |
    v
Connect Store
    |
    v
Open INBOX READ_ONLY
    |
    v
Read UIDVALIDITY
    |
    +--> changed? -> resync strategy
    |
    v
Find UID > last committed UID
    |
    v
Fetch batch headers
    |
    v
Extract & validate content
    |
    v
DB transaction:
  - save mailbox message identity
  - enqueue business processing event
  - update cursor/checkpoint safely
    |
    v
Close Folder and Store
```

### 17.1. Database schema minh họa

```sql
CREATE TABLE mailbox_message (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mailbox_account VARCHAR(120) NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    uid_validity BIGINT NOT NULL,
    uid BIGINT NOT NULL,
    message_id VARCHAR(998),
    received_at TIMESTAMP,
    subject TEXT,
    processing_status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_mailbox_uid
      UNIQUE (
          mailbox_account,
          folder_name,
          uid_validity,
          uid
      )
);

CREATE TABLE mailbox_cursor (
    mailbox_account VARCHAR(120) NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    uid_validity BIGINT NOT NULL,
    last_committed_uid BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (mailbox_account, folder_name)
);
```

Schema chỉ mang tính minh họa:
- Với multi-tenant, account identity phải được kiểm soát và không chứa credential.
- `message_id` là metadata tùy chọn, không phải unique key bắt buộc.
- Cursor chỉ được cập nhật sau khi processing plan đã persist an toàn.
- Nếu một UID fail mà cursor cứ tăng, có nguy cơ bỏ sót. Cần retry/dead-letter và quy tắc checkpoint theo batch.
- Khi UIDVALIDITY đổi, phải xử lý thế hệ mới, không tiếp tục nhầm cursor cũ.

### 17.2. Lưu dữ liệu trước, xác nhận sau

Một quy trình có thể:
1. Read metadata/message.
2. Validate và persist bản ghi với khóa unique.
3. Enqueue work nội bộ trong cùng transaction.
4. Commit.
5. Sau đó tùy policy mới đánh dấu SEEN hoặc move folder.

Nếu crash sau bước 4 nhưng trước bước 5, lần poll tiếp theo có thể gặp lại thư nhưng unique key sẽ ngăn tạo **business event trùng**.

Nếu làm ngược lại (đánh dấu đã xử lý trên mailbox trước khi commit DB), crash có thể làm mất công việc.

### 17.3. Không thể có atomic transaction giữa IMAP và database

IMAP flag update/move và database commit là hai hệ thống độc lập. Không có một transaction đơn giản bảo đảm cả hai hoặc cùng commit hoặc cùng rollback.

Do đó, nên thiết kế **at-least-once observation + idempotent processing**, không tuyên bố exactly-once qua mạng. Mức exactly-once nghiệp vụ phải được xây bằng unique keys, transaction nội bộ và kiểm soát side effects.

## 18. Polling mailbox định kỳ

Polling là cách triển khai dễ hiểu và phổ biến.

Ví dụ Spring scheduler:

```java
package com.example.mailbox;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailboxPollScheduler {

    private final MailboxSyncService syncService;

    public MailboxPollScheduler(
            MailboxSyncService syncService) {
        this.syncService = syncService;
    }

    @Scheduled(
        fixedDelayString = "${app.mailbox.poll-delay-ms:30000}"
    )
    public void poll() {
        syncService.synchronizeOneBatch();
    }
}
```

`MailboxSyncService` là service do ứng dụng định nghĩa để xử lý connect, folder, cursor và persistence. Để sử dụng `@Scheduled`, ứng dụng cần bật scheduling đúng cách, ví dụ `@EnableScheduling`, và quản lý exceptions để không làm mất tín hiệu vận hành.

Ở đây `fixedDelayString` có nghĩa delay được tính **sau khi lần poll trước hoàn thành** trong chế độ scheduling tương ứng. Với nhiều application instances, chỉ dùng `@Scheduled` không đảm bảo mỗi mailbox chỉ có một consumer.

### 18.1. Chọn polling interval

Nếu poll mỗi 2 giây:
- độ trễ phát hiện thư mới có thể thấp;
- nhưng tăng số connect/login và tải IMAP server;
- dễ gặp provider rate limit.

Nếu poll mỗi 5 phút:
- ít tải hơn;
- nhưng ticket/alert đến chậm.

Điều chỉnh dựa trên:
- SLA;
- mailbox arrival rate;
- provider connection quota;
- số accounts/folders;
- thời gian xử lý mỗi batch;
- polling overlap;
- số consumer instances.

Không có interval tối ưu chung.

### 18.2. Không cho nhiều polls chồng lên nhau

Khi một poll kéo dài hơn interval:
- không để hai thread tự ý xử lý cùng folder;
- dùng scheduler config, lock hoặc distributed lease;
- nếu có nhiều pods, dùng single-owner lease cho mỗi mailbox/folder;
- lưu cursor sau commit với optimistic/concurrency controls.

Đừng dựa vào việc một JVM có một thread scheduler để suy ra toàn cluster chỉ có một consumer.

### 18.3. Backpressure

Nếu có 50.000 thư chưa xử lý, một poll không nên nạp tất cả vào heap. Hãy:
- giới hạn batch size;
- giới hạn bytes per batch;
- enqueue vào durable queue;
- tạm dừng/giảm tốc khi downstream backlog cao;
- ưu tiên thư mới hay thư cũ theo policy rõ;
- theo dõi lag và age of oldest unprocessed message.

## 19. IMAP IDLE và thông báo có thay đổi

IMAP hỗ trợ extension **IDLE** trên server phù hợp, cho phép client đợi thông báo mailbox thay đổi mà không phải liên tục hỏi toàn bộ Inbox.

Ý tưởng:

```text
Client                        IMAP server
  |---- SELECT INBOX ---------->|
  |---- IDLE ------------------>|
  |                             |
  |<--- EXISTS / change notice--|
  |---- DONE ------------------>|
  |---- FETCH new UIDs -------->|
  |---- IDLE again ------------>|
```

Tuy nhiên:
- IDLE **không phải một notification queue bền vững**;
- server/proxy có thể ngắt idle connection;
- client vẫn cần reconnect và resync bằng UID;
- thay đổi có thể xuất hiện khi client offline;
- có thể phải định kỳ kết thúc và thiết lập lại IDLE;
- hỗ trợ IDLE và API cụ thể phụ thuộc provider/implementation.

Một số thư viện Jakarta Mail provider có lớp/extension IMAPFolder hỗ trợ `idle()`, nhưng API đó không phải hành vi chung của mọi `Folder` protocol. Khi cần, chọn đúng implementation và phiên bản library, rồi kiểm thử với mailbox provider.

### 19.1. IDLE không thay thế checkpoint

Sau khi nhận notification, vẫn phải:
1. Xác nhận folder connection còn hợp lệ.
2. Tìm UIDs mới từ cursor.
3. Fetch từng batch.
4. Persist idempotent.
5. Commit.
6. Quay lại IDLE.

Nếu process restart, nó phải có thể resync dù không nhận notification nào trong lúc offline.

### 19.2. Chọn polling hay IDLE?

| Tiêu chí | Polling | IDLE |
|---|---|---|
| Dễ triển khai | Cao | Trung bình, thêm lifecycle |
| Gần real-time | Phụ thuộc interval | Thường nhanh hơn khi server hỗ trợ |
| Số kết nối sống lâu | Ít hơn nếu connect per poll | Có thể cao |
| Chịu proxy/ngắt mạng | Kết nối ngắn dễ quản lý | Cần reconnect/refresh liên tục |
| Khôi phục sau restart | Dựa trên cursor | Vẫn phải dùng cursor |
| Server hỗ trợ | Phổ biến | Cần xác minh capability |
| Phù hợp ít mailbox | Có | Có nếu cần độ trễ thấp |
| Phù hợp nhiều mailbox | Cần điều tiết queries | Cần quản lý nhiều sockets/lifecycles |

Nếu mailbox không yêu cầu real-time, polling có thể đơn giản và đáng tin hơn. Nếu cần độ trễ thấp và provider hỗ trợ IDLE ổn định, triển khai IDLE **kèm resync**, không thay thế hoàn toàn cơ chế đồng bộ bền vững.

## 20. Quản lý kết nối: mỗi poll hay kết nối sống lâu?

Hai chiến lược:

**A. Kết nối theo batch**
- Tạo hoặc dùng `Session` cấu hình.
- Mở `Store.connect`.
- Mở Folder.
- Xử lý một batch.
- Đóng Folder/Store.

Ưu điểm: lifecycle rõ, giảm stale connections, phù hợp polling thưa. Nhược điểm: thêm TCP/TLS/AUTH overhead.

**B. Kết nối dài hạn**
- Giữ Store/Folder mở trong một consumer chuyên trách.
- Dùng IDLE hoặc fetch nhiều batches.
- Theo dõi disconnect và reconnect.
- Shutdown đóng tài nguyên.

Ưu điểm: giảm overhead kết nối, có thể giảm latency. Nhược điểm: cần ownership, heartbeat, timeout, reconnect, thread-safety và recovery.

### 20.1. Session reuse không phải Store reuse

`Session` có thể tái sử dụng như cấu hình. `Store`/`Folder` có trạng thái kết nối/selection thật nên cần quản lý riêng.

Không dùng một `Store` static cho nhiều mailbox accounts bằng cách sửa username/password. Cũng không nên chia sẻ một `Folder` đang mở giữa nhiều workers tự ý gọi FETCH/close/expunge cùng lúc.

### 20.2. Cân nhắc connection pool của IMAP provider

Một số Jakarta Mail IMAP provider có cơ chế cache/pool kết nối phục vụ hoạt động của Store/Folder. Nhưng các chi tiết như số kết nối, timeout và cách tái sử dụng phụ thuộc implementation và phiên bản.

Không tự khẳng định một `Session` hay `Store` là connection pool chung có bảo đảm thread-safe. Nếu tối ưu pool:
- xác minh document của implementation đang dùng;
- giới hạn số connections theo mailbox/provider quota;
- đo số socket thực tế;
- test server-side disconnect;
- đảm bảo không có nhiều consumers xử lý cùng UID.

### 20.3. Kết nối bị ngắt giữa lúc fetch

Các trường hợp:
- server đóng idle socket;
- network reset;
- TLS session bị lỗi;
- token hết hạn;
- folder bị đổi/xóa;
- mailbox account bị disable.

Khi lỗi:
1. Không giả định đang giữ một Store khỏe chỉ vì `isConnected()` trước đó là true.
2. Đóng tài nguyên cũ.
3. Reconnect theo backoff có jitter và giới hạn attempts.
4. Reopen folder.
5. Kiểm tra UIDVALIDITY.
6. Tiếp tục từ checkpoint bền vững, không từ message number cũ.
7. Không xử lý trùng business event.

## 21. Xác thực password, app password và OAuth2

Nhiều mailbox providers không còn cho phép username/password thông thường qua IMAP hoặc yêu cầu:
- app password riêng;
- OAuth2/XOAUTH2;
- quyền truy cập mailbox được cấp cho ứng dụng;
- security policy/conditional access;
- account/folder scopes;
- admin consent.

Phải kiểm tra provider thực tế. Một app có quyền gửi SMTP **không mặc nhiên có quyền đọc Inbox**.

### 21.1. Ví dụ cấu hình XOAUTH2 cho IMAPS

Với Jakarta Mail implementation hỗ trợ cơ chế XOAUTH2:

```java
Properties props = new Properties();

props.put("mail.imaps.ssl.enable", "true");
props.put("mail.imaps.ssl.checkserveridentity", "true");
props.put("mail.imaps.auth.mechanisms", "XOAUTH2");
props.put("mail.imaps.connectiontimeout", "5000");
props.put("mail.imaps.timeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");

try {
    store.connect(
        imapHost,
        993,
        mailboxUsername,
        accessToken
    );
} finally {
    if (store.isConnected()) {
        store.close();
    }
}
```

Ở đây `accessToken` được dùng tại vị trí credential của `Store.connect` theo cơ chế XOAUTH2 của provider. **Không phải mọi mailbox provider tự động chấp nhận mẫu này**. Phải bảo đảm:
- provider hỗ trợ IMAP + OAuth2;
- token có đúng audience/scope/permission;
- token còn hiệu lực;
- cơ chế auth không bị fallback sang password không mong muốn;
- provider/API/thư viện tương thích;
- token không bị ghi log.

### 21.2. Token refresh

Không nên tái sử dụng access token hết hạn mãi trong một Store. Một kết nối lâu dài có thể bị server ngắt; khi reconnect, phải lấy token mới từ token provider theo chính sách.

Không hardcode refresh token trong source hoặc lưu plaintext trong log. Secret/token storage, scopes và rotation thuộc ranh giới bảo mật của application.

### 21.3. Quyền tối thiểu

Nếu ứng dụng chỉ đọc Inbox, đừng cấp quyền xóa hoặc gửi thay người dùng nếu provider cho phép tách scopes. Tách các service accounts theo trách nhiệm và giới hạn mailbox/folders được truy cập.

## 22. Cấu hình nhiều mailbox accounts hoặc tenants

Một SaaS có thể cần đọc:
- `support@tenant-a.example`;
- `support@tenant-b.example`;
- một mailbox nội bộ;
- một shared mailbox được ủy quyền.

Không dùng một singleton Store được cấu hình lần lượt bằng credential của từng tenant.

Mô hình an toàn:

```text
MailboxAccountRegistry
  |
  +--> Account A config -> Session/Store A -> Folder A
  |
  +--> Account B config -> Session/Store B -> Folder B
  |
  +--> Internal config -> Session/Store C -> Folder C
          |
          v
Per-mailbox cursor + access policy
```

Các thông số cần cách ly:
- credential/token;
- mailbox account identity;
- allowed folders;
- cursor và UIDVALIDITY;
- rate limit;
- downstream tenant ID;
- file attachment storage;
- audit access.

**Tenant identity phải được lấy từ backend đã xác thực**, không từ một header trong email nhận hoặc request tùy ý rồi dùng để chọn secret.

### 22.1. Không dựa vào From để xác định tenant

Email `From: customer@...` dễ giả mạo. Nếu nội dung nhập vào hệ thống tenant A, tenant phải được xác định theo mailbox account/route được cấu hình, không chỉ theo địa chỉ From trong thư.

SPF/DKIM/DMARC có thể cung cấp tín hiệu xác thực của miền gửi, nhưng không phải bằng chứng người gửi có quyền thao tác trên dữ liệu tenant.

### 22.2. Không mở endpoint IMAP tùy ý từ input

Nếu API cho phép caller cung cấp `host` và `port` để server tự kết nối, ứng dụng có thể bị lợi dụng làm SSRF hoặc truy cập dịch vụ nội bộ. Chỉ dùng account profiles được admin phê duyệt, với chính sách DNS/IP/egress phù hợp.

## 23. Hiệu năng đọc mailbox

Các điểm nghẽn có thể gồm:
- số TCP/TLS logins;
- server-side FETCH round trips;
- số messages/folder;
- kích thước MIME và attachments;
- charset decoding/HTML parsing;
- database writes;
- downstream enrichment;
- mailbox provider throttle;
- chạy polling trên nhiều replicas.

### 23.1. Không tải body trước khi biết cần xử lý

Quy trình hiệu quả:

```text
UID range
   |
   v
FETCH UID + headers + flags
   |
   v
Already processed?
   |
   +-- Yes -> skip
   |
   v
Download necessary body parts
   |
   v
Validate / persist / enqueue
```

Đối với email chỉ cần subject để tạo ticket sơ bộ, có thể chưa cần tải attachment trong vòng đầu. Nhưng nếu business flow yêu cầu lưu nội dung đầy đủ làm snapshot, phải định nghĩa rõ trạng thái `CONTENT_PENDING` và retry tải body, không đánh dấu hoàn tất sớm.

### 23.2. Phân trang bằng UID

Với IMAP, một chiến lược có thể lưu `lastCommittedUid`, tìm các UIDs lớn hơn cursor theo từng cửa sổ (chú ý gaps), dùng `getMessagesByUID(...)` hoặc `getMessageByUID(...)` theo APIs provider.

Không suy ra các UIDs liên tiếp: IMAP UIDs **không cần liên tục**. Khi có khoảng trống, việc đó không tự biểu thị lỗi. Cursor phải tiến tới UID thực sự đã xử lý theo quy tắc bền vững.

### 23.3. Giới hạn kích thước

Có thể đặt:
- maximum messages/poll;
- maximum MIME parts;
- maximum header/body bytes;
- maximum attachment bytes;
- maximum nested MIME depth;
- maximum parsing duration;
- per-mailbox concurrency;
- total in-flight memory budget.

Một email độc hại hoặc bị lỗi định dạng không nên làm một worker giữ toàn bộ heap hoặc chặn tiến độ của tất cả mailbox khác.

### 23.4. Đo thời gian từng giai đoạn

| Metric | Câu hỏi |
|---|---|
| `mailbox_connect_duration_seconds` | TCP/TLS/AUTH chậm ở provider nào? |
| `mailbox_open_folder_duration_seconds` | SELECT folder có bị chậm? |
| `mailbox_fetch_headers_seconds` | Fetch metadata mất bao lâu? |
| `mailbox_fetch_body_seconds` | Message/attachments gây tải? |
| `mailbox_processed_total` | Bao nhiêu thư đã ingest thành công? |
| `mailbox_skipped_duplicate_total` | Bao nhiêu UIDs đã được ghi nhận? |
| `mailbox_sync_lag_seconds` | Trễ bao lâu so với mailbox arrival? |
| `mailbox_reconnect_total` | Số lần rớt kết nối? |
| `mailbox_uidvalidity_changed_total` | Có mailbox bị reset generation? |
| `mailbox_parse_failures_total` | Bao nhiêu thư lỗi MIME/charset? |
| `mailbox_processing_backlog` | Downstream có theo kịp không? |

Không đưa email body, access token hoặc attachment bytes vào metric labels/logs.

## 24. Logging và xử lý lỗi an toàn

Một lỗi có thể xảy ra ở:
1. cấu hình/lookup account;
2. DNS/TCP;
3. TLS và hostname verification;
4. AUTH;
5. open folder;
6. FETCH headers;
7. download/parse MIME;
8. persist/ack trong database;
9. cập nhật flag/move folder;
10. close/reconnect.

Không gom tất cả thành “IMAP connection failed” nếu cần xác định đúng cách xử lý.

### 24.1. Phân nhóm lỗi

| Nhóm | Ví dụ | Hành động |
|---|---|---|
| Network transient | timeout, connection reset | Close/reconnect với backoff |
| TLS/certificate | PKIX, hostname mismatch | Dừng retry dồn dập, sửa endpoint/CA |
| Authentication | sai token, token hết hạn, thiếu scope | Refresh token hoặc sửa quyền/config |
| Folder | folder không tồn tại hoặc không được phép | Kiểm tra cấu hình, không thử liên tục |
| Message missing | message bị expunge giữa list và fetch | Skip/reconcile theo UID, không lỗi toàn pipeline |
| MIME parse | malformed content, charset lỗi | Ghi retry/quarantine per-message |
| Resource limit | attachment quá lớn, nested MIME sâu | Cô lập message theo policy |
| DB outage | không thể persist checkpoint | Giữ cursor cũ, retry an toàn sau khi DB phục hồi |
| UIDVALIDITY changed | folder generation đổi | Resync theo chính sách |

### 24.2. Structured log

Ví dụ:

```json
{
  "event": "mailbox.sync_batch",
  "mailboxKey": "support-a",
  "folder": "INBOX",
  "uidValidity": 4567,
  "fromUid": 12001,
  "toUid": 12100,
  "processed": 72,
  "duplicates": 28,
  "durationMs": 1830,
  "outcome": "SUCCESS"
}
```

Thông tin này giúp điều tra mà không cần log:
- username/password;
- OAuth2 token;
- toàn bộ headers/body;
- recipient/From nếu không cần;
- URL có reset/verification token;
- attachment bytes.

### 24.3. Tránh debug log trong production

Jakarta Mail hỗ trợ bật debug cho `Session` trong mục đích chẩn đoán:

```java
Session session = Session.getInstance(props);
session.setDebug(true);
```

Debug có thể ghi thông tin protocol, account/server metadata và trong một số cấu hình có thể làm lộ dữ liệu. Chỉ bật tạm thời trong môi trường kiểm soát; tránh log credential hoặc raw email.

## 25. Kiểm thử Session và mailbox reader

### 25.1. Unit test không cần IMAP thật

Các thành phần có thể unit test độc lập:
- chọn mailbox account profile;
- validation cấu hình;
- MIME traversal với `MimeMessage` in-memory;
- xử lý charset/Unicode;
- mapping headers vào DTO;
- cursor/resync policy;
- idempotency và retry classifier;
- attachment size/filename rules.

Ví dụ MIME in-memory:

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

MimeMessage message = new MimeMessage(
    Session.getInstance(new Properties())
);

message.setSubject("Yêu cầu hỗ trợ từ Nguyễn Thị Ánh", "UTF-8");
message.setText(
    "Xin chào,\nTôi cần hỗ trợ đơn hàng 123.",
    "UTF-8"
);

message.saveChanges();
```

Có thể test `TextPartExtractor.collect(message,"text/plain")` trả đúng nội dung đã decode. Test này xác minh MIME parser logic nhưng **không** chứng minh Store/Folder kết nối IMAP.

### 25.2. Integration test cần IMAP test server

Dùng mailbox server được kiểm soát như một IMAP/POP3 sandbox hỗ trợ APIs cần thử. Ví dụ một số dự án dùng **GreenMail** cho JavaMail tests; chọn phiên bản tương thích với `jakarta.mail.*` của ứng dụng.

Kiểm tra:
1. Tạo mailbox/test user.
2. Inject một email test vào server.
3. Tạo `Session` và `Store` thật trỏ tới endpoint test.
4. Kết nối, mở INBOX `READ_ONLY`.
5. Fetch message, đọc Subject và body.
6. Kiểm tra đóng folder/store.
7. Test account sai credential, folder thiếu và disconnect.
8. Test UID/UIDVALIDITY khi server có hỗ trợ phù hợp.

Đừng dùng mailbox cá nhân thật hoặc SMTP credentials production trong test suite.

### 25.3. Test TLS riêng

Một local IMAP test server không dùng TLS có thể chứng minh API read, nhưng không chứng minh cấu hình IMAPS production an toàn.

Cần có test khác cho:
- IMAPS hoặc STARTTLS đúng mode;
- certificate chain hợp lệ;
- hostname khớp SAN;
- certificate không tin cậy bị từ chối;
- timeout/reconnect;
- OAuth2 nếu provider hỗ trợ;
- TLS inspection/proxy nếu có trong hạ tầng.

Không dùng `ssl.trust=*` trong test rồi suy ra production sẽ verify certificate đúng.

### 25.4. Test đọc không làm đổi flags ngoài ý muốn

Một test quan trọng:
1. Tạo email chưa đọc trong server test.
2. Mở folder `READ_ONLY`.
3. Fetch header/body theo code ingestion.
4. Đóng folder/store.
5. Kết nối lại và kiểm tra `SEEN` vẫn đúng kỳ vọng.

Đây là integration test vì hành vi flags phụ thuộc server/protocol.

### 25.5. Test idempotency qua reconnect

- Poll lần đầu, lưu UID trong DB.
- Poll lại cùng folder/UIDVALIDITY.
- Assert không tạo thêm business item.
- Giả lập crash sau commit DB nhưng trước flag update.
- Poll lại: unique constraint ngăn duplicate.
- Giả lập UIDVALIDITY đổi: hệ thống resync và không nhầm UID thế hệ cũ.

### 25.6. Test concurrent workers

Dùng hai consumers cho cùng mailbox/folder. Kiểm tra lease/claim trong DB bảo đảm không xử lý side effect trùng. Không dựa vào việc cùng một IMAP server trả số messages khác nhau là cơ chế khóa an toàn.

## 26. Những lỗi thực tế thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `JavaMailSender` không có `getInbox()` | Nhầm API gửi với API nhận | Dùng Jakarta Mail `Store`/`Folder` |
| `Session` tạo xong nhưng không đọc được thư | Chưa tạo hoặc connect Store | Gọi `getStore` và `connect` |
| `AuthenticationFailedException` | Sai credential, token hết hạn, IMAP disabled, thiếu scope | Kiểm tra provider auth policy |
| `SSLHandshakeException` hoặc `PKIX` | CA/chain/hostname/TLS mode không phù hợp | Xác minh cert/endpoint, giữ validation |
| `Connection refused` | Sai host/port, firewall, IMAP bị chặn | Kiểm tra network/provider |
| `FolderClosedException` | Server đóng folder hoặc app đóng quá sớm | Reconnect/reopen, không giữ lazy Message |
| `IllegalStateException` do folder chưa mở | Dùng API đòi open trước khi `open` | Quản lý lifecycle rõ ràng |
| `getContent()` không phải `String` | MIME multipart | Duyệt MIME tree |
| Thư bị đánh dấu đã đọc ngoài ý muốn | READ_WRITE hoặc fetch behavior | Dùng READ_ONLY/peek, test flags |
| Cursor bỏ sót thư | Lưu messageNumber thay UID | Dùng UID + UIDVALIDITY |
| Trùng ticket sau restart | Không có unique key/checkpoint | Persist idempotently |
| UID cũ trỏ thư khác | UIDVALIDITY đã thay đổi | Resync theo folder generation |
| Polling chậm, memory cao | Fetch tất cả messages và attachments | Batch theo UID/size limits |
| POP3 không có folder như IMAP | Khác semantics protocol | Chọn IMAP nếu cần folder/flags |
| Không tìm thấy thư mới từ UNSEEN | Người dùng đã đọc hoặc client khác set SEEN | Dùng UID cursor thay vì chỉ SEEN |
| Consumer treo sau thời gian dài | Stale Store, network/proxy disconnect | Timeout, reconnect, health monitor |
| Đọc thất bại chỉ ở production | JDK/truststore/proxy khác test | Chẩn đoán từ runtime thực tế |
| Attachment lưu sai vị trí | Tin filename của sender | Server-generated filename và validation |
| Email HTML gây XSS trong dashboard | Render HTML thô từ thư nhận | Sanitize/escape, không chạy active content |
| Gmail/hosted provider từ chối password | Yêu cầu OAuth2/app password | Theo chính sách provider |
| Nhiều pod xử lý cùng thư | Không có ownership lease | Distributed lock + DB idempotency |

## 27. Checklist triển khai mailbox reader production

### 27.1. Cấu hình và bảo mật

- [ ] IMAP/POP3 protocol đúng theo provider.
- [ ] Host/port/TLS mode đúng; dùng IMAPS hoặc STARTTLS bắt buộc.
- [ ] Hostname verification và CA trust đúng.
- [ ] Auth credentials/OAuth2 scopes có quyền tối thiểu.
- [ ] Secret rotation và token refresh có kế hoạch.
- [ ] Không log password/token/raw body.
- [ ] Egress allowlist và tenant account registry nếu cần.
- [ ] Không dùng tài khoản email thật trong tests.

### 27.2. Resource lifecycle

- [ ] `Session` không bị nhầm là TCP connection.
- [ ] `Store.connect` được gọi có kiểm soát.
- [ ] `Folder.open` đúng mode.
- [ ] `Folder.close(false)` và `Store.close()` trong finally.
- [ ] Không giữ lazy `Message` ngoài vòng đời folder.
- [ ] Có timeout và reconnect với backoff.
- [ ] Không chia sẻ Store/Folder tùy tiện giữa threads.
- [ ] Server-side connection quota được theo dõi.

### 27.3. Đồng bộ và dữ liệu

- [ ] Khóa unique theo mailbox/folder/UIDVALIDITY/UID.
- [ ] Không dùng messageNumber làm cursor bền vững.
- [ ] UIDVALIDITY change có resync policy.
- [ ] Persist trước khi đánh dấu xử lý trên server.
- [ ] MIME/attachment parsing có byte/depth limits.
- [ ] HTML và URLs được coi là dữ liệu không tin cậy.
- [ ] Polling/IDLE có backpressure và distributed ownership.
- [ ] Có retry/quarantine per-message khi parse fail.
- [ ] Có metrics về lag, errors và duplicates.

### 27.4. Kiểm thử

- [ ] Unit test MIME/Unicode/cursor policy.
- [ ] Integration test với IMAP mailbox sandbox.
- [ ] Test authentication failure/TLS mismatch.
- [ ] Test READ_ONLY không đổi SEEN ngoài dự định.
- [ ] Test UID cursor, duplicate và UIDVALIDITY reset.
- [ ] Test folder bị đóng, connection reset và recovery.
- [ ] Test attachment lớn và message malformed.
- [ ] Test hai consumers cùng một folder.
- [ ] Test IDLE reconnect và poll fallback nếu dùng IDLE.

## 28. Bài tập thực hành

### Bài 1 — Session và Store

Viết hai đoạn code: một đoạn chỉ tạo `Session`, đoạn thứ hai gọi `Store.connect`. Giải thích chính xác lúc nào kết nối mạng được khởi tạo.

### Bài 2 — IMAPS

Cấu hình IMAPS port 993 có TLS hostname verification và ba timeouts. Mở `INBOX` ở `READ_ONLY`, lấy số thư rồi đóng Folder/Store đúng cách.

### Bài 3 — IMAP STARTTLS

Chuyển ví dụ sang IMAP port 143 dùng `starttls.enable=true` và `starttls.required=true`. Nêu vì sao không được fallback plaintext khi server không cho STARTTLS.

### Bài 4 — POP3S

Tạo một `Store` POP3S và đọc số thư từ INBOX. So sánh điểm thiếu so với IMAP về folder, flags và UID.

### Bài 5 — MIME multipart

Tạo một `MimeMessage` multipart có `text/plain`, `text/html` và attachment. Viết hàm duyệt MIME để lấy plain body và bỏ qua attachment text.

### Bài 6 — Flags

Tạo email test chưa đọc. Fetch bằng `READ_ONLY` rồi mở lại kiểm tra `SEEN`. Đề xuất cách tracking business processing mà không dựa hoàn toàn vào mail flags.

### Bài 7 — Message number và UID

Trong mailbox có ba messages A, B, C, xóa/expunge B rồi quan sát sequence number của C. Giải thích vì sao cần UID/UIDVALIDITY cho cursor.

### Bài 8 — UIDVALIDITY reset

Giả lập folder được tái tạo, UIDVALIDITY đổi trong khi app đã lưu last UID. Thiết kế resync không trộn hai thế hệ UIDs và không phát sự kiện trùng.

### Bài 9 — Cursor database

Thiết kế bảng chứa `mailboxAccount`, `folder`, `uidValidity`, `uid` và processing status. Tạo unique constraint và test poll lại cùng message không tạo row thứ hai.

### Bài 10 — Polling batch

Một mailbox có 100.000 thư, app chỉ được xử lý tối đa 100 mỗi poll. Thiết kế `getMessagesByUID` hoặc UID window để không tải tất cả messages vào heap.

### Bài 11 — FetchProfile

Trước khi tải body, fetch envelope/flags/UID của một batch. Đo số round trips/thời gian theo test server và giải thích lợi ích của prefetch.

### Bài 12 — Mất kết nối

Giả lập server đóng IMAP connection giữa lúc fetch. Test app đóng Store cũ, reconnect, mở folder, kiểm tra UIDVALIDITY và tiếp tục từ checkpoint.

### Bài 13 — OAuth2

Provider chỉ cho IMAP XOAUTH2. Thiết kế token provider, xác thực scope và refresh token khi reconnect. Không ghi access token vào log.

### Bài 14 — Polling hay IDLE

So sánh mailbox support ticket cần độ trễ 2 phút với mailbox cảnh báo cần phát hiện gần real-time. Đề xuất polling hoặc IDLE và luôn có resync cursor.

### Bài 15 — Multitenant mailbox

Hai tenants có mailbox credentials và folder riêng. Viết routing/account registry đảm bảo mỗi worker chỉ có quyền đọc đúng mailbox, không dựa vào Header From để xác định tenant.

### Bài 16 — Attachment không an toàn

Thư nhận có ZIP lớn, filename `../../invoice.pdf` và HTML chứa external image URL. Mô tả cách cách ly, giới hạn bytes và tránh tự gọi external resources.

### Bài 17 — Crash sau DB commit

Worker đã persist ticket nhưng crash trước khi cập nhật SEEN. Poll lại cùng UID. Chứng minh DB unique key tránh tạo ticket trùng.

### Bài 18 — Monitoring

Thiết kế dashboard gồm connect latency, poll lag, parse failure, UIDVALIDITY changes, duplicate rate, backlog và reconnect attempts. Không đưa body hoặc token vào metric labels.

## 29. Tổng kết

**Session và kết nối đọc mailbox** trong Spring Framework Mail dựa chủ yếu trên **Jakarta Mail inbound APIs**, không phải `JavaMailSender` outbound.

Những nguyên tắc cần nhớ:

1. **`Session` là cấu hình**, `Store` mới đại diện cho message-store connection, `Folder` cần được mở đúng mode, `Message` có thể lazy-load dữ liệu qua kết nối.
2. **IMAP** phù hợp các bài toán đồng bộ folders, flags và UID; **POP3** chủ yếu phục vụ tải thư đơn giản, ít tính năng trạng thái hơn.
3. Dùng **IMAPS/STARTTLS với certificate và hostname verification**, timeout và credential/OAuth2 theo provider; không fallback plaintext.
4. Quản lý đầy đủ vòng đời **connect → open → fetch → convert to DTO → close**, không giữ `Message` sau khi Folder đóng.
5. `READ_ONLY` thường thích hợp cho ingestion; **SEEN không phải ACK nghiệp vụ**.
6. **Message sequence number không bền vững**; đồng bộ IMAP nên dùng **mailbox + folder + UIDVALIDITY + UID** và cursor được persist an toàn.
7. Đọc MIME theo tree; giới hạn attachment, không render HTML không tin cậy hoặc tự tải external resources.
8. Polling và IDLE đều cần **reconnect/resync, idempotency, backpressure và distributed ownership** nếu có nhiều workers/pods.
9. Lưu tiến độ DB trước khi thay đổi flags trên server, vì IMAP và database không chia sẻ một atomic transaction.
10. Kiểm thử với IMAP sandbox, test TLS/auth/UID/flags/reconnect; tách unit tests của parser và cursor policy khỏi network integration.

Khi hiểu đúng ranh giới giữa Session, Store, Folder và Message, bạn có thể xây dựng một mailbox reader ổn định, bảo mật và có khả năng phục hồi, đồng thời tích hợp dữ liệu email nhận vào ứng dụng Spring mà không bỏ sót thư hoặc vô tình xử lý trùng.
