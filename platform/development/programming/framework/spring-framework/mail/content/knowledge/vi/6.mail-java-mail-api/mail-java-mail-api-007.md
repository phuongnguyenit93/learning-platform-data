# Session, Transport và các đối tượng Jakarta Mail liên quan

Khi xây dựng tính năng gửi email bằng **Spring Framework Mail**, chúng ta thường bắt đầu từ `JavaMailSender`. Dưới lớp API của Spring là **Jakarta Mail**, thư viện cung cấp các đối tượng cốt lõi để cấu hình môi trường email, tạo thông điệp, mở kết nối đến máy chủ gửi/nhận và trao đổi dữ liệu theo những giao thức phù hợp.

Hai tên xuất hiện nhiều nhất là **`Session`** và **`Transport`**. `Session` giữ cấu hình và tạo đối tượng cần thiết; `Transport` đảm nhiệm kết nối và gửi thông điệp. Bên cạnh đó còn có `Message`, `MimeMessage`, `Address`, `Authenticator`, `Store`, `Folder` và các kiểu MIME.

Nắm được vai trò của từng đối tượng giúp đọc mã Spring Mail, tự cấu hình SMTP khi cần, phân biệt lỗi tạo email với lỗi mạng, cũng như hiểu vì sao không phải mỗi lần tạo `Session` đều tạo một phiên SMTP.

## 1. Bức tranh tổng thể: các lớp phối hợp ra sao?

Jakarta Mail là API cho email, thường cần một **implementation/provider** để giao tiếp qua các giao thức như SMTP, IMAP hoặc POP3. Trong ứng dụng Spring dùng SMTP thông thường:

```text
Application service
      |
      v
Spring JavaMailSender
      |
      v
Spring JavaMailSenderImpl
      |
      +-------------------------------------+
      | Jakarta Mail                       |
      |                                     |
      | Session (cấu hình, factory)         |
      |    |                                |
      |    +--> MimeMessage (nội dung thư)  |
      |    |       +--> Address             |
      |    |       +--> Multipart/BodyPart  |
      |    |                                |
      |    +--> Transport (kết nối, gửi)    |
      |             |                       |
      +-------------|-----------------------+
                    |
                    v
                SMTP server
                    |
                    v
            Hạ tầng gửi/nhận thư
```

Để **đọc email**, Jakarta Mail còn có hướng khác:

```text
Session
   |
   +--> Store (IMAP / POP3)
            |
            +--> Folder
                     |
                     +--> Message / MimeMessage
```

Vì vậy, `Session` là điểm xuất phát chung; **`Transport` dùng để gửi**, còn **`Store` và `Folder` dùng để truy xuất thư từ kho hộp thư**.

| Đối tượng | Gói Java thường gặp | Vai trò chính |
|---|---|---|
| `Session` | `jakarta.mail.Session` | Giữ properties, authenticator, cấu hình debug và cung cấp factory để lấy các thành phần giao thức. |
| `Transport` | `jakarta.mail.Transport` | Gửi email đến máy chủ qua provider, thường là SMTP. |
| `Store` | `jakarta.mail.Store` | Kết nối và truy cập hộp thư từ máy chủ, thường qua IMAP hoặc POP3. |
| `Folder` | `jakarta.mail.Folder` | Đại diện một thư mục/hộp thư như `INBOX`; cung cấp thao tác lấy message. |
| `Message` | `jakarta.mail.Message` | Kiểu trừu tượng của thông điệp email, chứa người gửi, người nhận, chủ đề và nội dung. |
| `MimeMessage` | `jakarta.mail.internet.MimeMessage` | Implementation thông điệp dựa trên MIME/RFC Internet mail, dùng phổ biến để gửi SMTP. |
| `Address` / `InternetAddress` | `jakarta.mail.Address` / `jakarta.mail.internet.InternetAddress` | Mô hình địa chỉ, đặc biệt địa chỉ thư Internet. |
| `Authenticator` / `PasswordAuthentication` | `jakarta.mail.*` | Cung cấp thông tin xác thực khi provider cần đăng nhập. |
| `Multipart` / `BodyPart` | `jakarta.mail.*` | Gom nhiều phần nội dung của một email. |
| `MimeMultipart` / `MimeBodyPart` | `jakarta.mail.internet.*` | Các implementation MIME để tạo HTML, ảnh inline, attachment. |
| `MessagingException` | `jakarta.mail.MessagingException` | Nhóm lỗi checked exception khi xử lý thông điệp/kết nối ở tầng Jakarta Mail. |

Các đối tượng có thể phối hợp trong một luồng gửi, nhưng **mỗi loại quản lý một phạm vi trách nhiệm riêng**.

## 2. Session: ngữ cảnh cấu hình của Jakarta Mail

### 2.1. Session là gì?

`Session` tập hợp các tham số mà Jakarta Mail sử dụng để tạo thành phần email. Nó có thể chứa:

- **Properties** xác định host, cổng, giao thức, timeout, TLS, xác thực và các tùy chọn provider.
- **Authenticator** cung cấp thông tin đăng nhập khi provider yêu cầu.
- Cấu hình debug và các thông tin provider có sẵn.
- Phương thức factory như `getTransport(...)`, `getStore(...)` để lấy đối tượng làm việc với giao thức.

Điểm cần phân biệt:

> **`jakarta.mail.Session` không phải kết nối TCP/SMTP đã mở.** Tạo `Session` chưa gửi lệnh SMTP, chưa xác thực với máy chủ và chưa bảo đảm rằng máy chủ tồn tại hoặc có thể kết nối.

Tên `Session` ở đây cũng không có nghĩa là HTTP session của người dùng hoặc một session đăng nhập của hệ thống web.

### 2.2. Tạo Session bằng Properties

Ví dụ sử dụng Jakarta Mail trực tiếp:

```java
import jakarta.mail.Authenticator;
import jakarta.mail.PasswordAuthentication;
import jakarta.mail.Session;
import java.util.Properties;

public class MailSessionFactory {

    public static Session create(String username, String password) {
        Properties properties = new Properties();
        properties.put("mail.transport.protocol", "smtp");
        properties.put("mail.smtp.host", "smtp.example.com");
        properties.put("mail.smtp.port", "587");
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return Session.getInstance(properties, new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                return new PasswordAuthentication(username, password);
            }
        });
    }
}
```

Trong ví dụ:

1. `Properties` mô tả cách client kết nối đến server.
2. `Session.getInstance(...)` tạo một đối tượng `Session` với properties và authenticator tương ứng.
3. `Authenticator` được provider gọi khi cần lấy credential; `PasswordAuthentication` chỉ chứa thông tin đăng nhập, không phải đối tượng thực hiện TLS hoặc gửi dữ liệu.
4. Kết nối SMTP chỉ bắt đầu khi một `Transport` được kết nối hoặc khi thao tác gửi cấp cao tạo kết nối giúp ứng dụng.

Thông tin `username` và `password` nên được lấy từ biến môi trường hoặc hệ thống quản lý bí mật. Tránh ghi cứng credential trong repository và tránh ghi thông tin AUTH vào log.

### 2.3. getInstance và getDefaultInstance

Jakarta Mail cung cấp nhiều cách lấy `Session`:

```java
Session sessionA = Session.getInstance(properties, authenticator);

Session sessionB = Session.getInstance(properties);

Session sharedDefault = Session.getDefaultInstance(properties);
```

`getInstance(...)` tạo một `Session` theo bộ tham số được truyền. `getDefaultInstance(...)` làm việc với **default Session dùng chung** ở cấp môi trường chạy; các lần gọi tiếp theo có thể trả về Session đã được khởi tạo trước đó thay vì áp dụng properties mới.

Trong ứng dụng Spring có nhiều tài khoản, nhiều SMTP provider hoặc nhiều tập cấu hình, thường nên dùng một Session được cấu hình rõ ràng cho từng cấu hình gửi thay vì dựa vào default Session toàn cục. Dùng `getDefaultInstance` chỉ khi hiểu rõ tác động đến cấu hình dùng chung.

### 2.4. Session có thread-safe không?

`Session` thường được dùng như một **đối tượng cấu hình tái sử dụng** ở phạm vi ứng dụng. Bạn không cần tạo Session mới cho mọi email. Tuy nhiên, không nên vì thế mà coi **`MimeMessage`, `Transport` hoặc `Folder`** là những đối tượng có thể bị nhiều luồng thao tác tùy ý cùng lúc.

Thiết kế phổ biến là:

- Tái sử dụng cấu hình `Session` hoặc bean `JavaMailSender`.
- Tạo `MimeMessage` riêng cho mỗi thông điệp.
- Quản lý vòng đời kết nối `Transport` theo thao tác gửi hoặc theo một thành phần gửi được thiết kế rõ ràng.
- Tránh sửa `Properties` và các đối tượng message dùng chung giữa nhiều worker trong lúc gửi.

## 3. Transport: đối tượng thực hiện việc gửi

### 3.1. Transport là gì?

`Transport` là lớp trừu tượng của Jakarta Mail dành cho **gửi thông điệp**. Với cấu hình thông dụng, implementation SMTP chịu trách nhiệm:

- Kết nối tới SMTP server.
- Thương lượng giao thức và các extension cần thiết.
- Bật TLS, xác thực nếu cấu hình yêu cầu.
- Truyền phong bì thư và nội dung email.
- Đọc phản hồi của server và báo lỗi về cho ứng dụng.
- Đóng kết nối khi hoàn tất.

Mối liên hệ:

```text
Session
  |
  | getTransport("smtp")
  v
Transport (chưa kết nối)
  |
  | connect(...)
  v
Transport (đã kết nối)
  |
  | sendMessage(message, recipients)
  v
SMTP server phản hồi
  |
  | close()
  v
Transport (đã đóng)
```

**Không nhầm `Transport` với `Message`:** `Message` giữ nội dung và header; `Transport` là kênh gửi nội dung đó.

### 3.2. Hai cách gửi trong Jakarta Mail

Jakarta Mail có hai kiểu thường gặp:

**Cách A: phương thức tĩnh `Transport.send(...)`**

```java
Transport.send(message);
```

Với cách này, Jakarta Mail thực hiện các bước chuẩn bị message cần thiết (bao gồm `saveChanges()`), kết nối, gửi rồi đóng kết nối theo cơ chế của provider. Đây là phương án đơn giản cho một thông điệp, khi Session đã có cấu hình và credential phù hợp.

**Cách B: tạo Transport rồi điều khiển vòng đời**

```java
Transport transport = session.getTransport("smtp");
try {
    transport.connect(host, username, password);
    message.saveChanges();
    transport.sendMessage(message, message.getAllRecipients());
} finally {
    transport.close();
}
```

Ở cách thứ hai, ứng dụng kiểm soát rõ **lúc kết nối và đóng kết nối**, có thể sử dụng một Transport cho nhiều thao tác `sendMessage(...)` trong cùng một phiên nếu provider và ứng dụng hỗ trợ. Khác với phương thức tĩnh, `sendMessage(...)` trên instance **không tự bảo đảm gọi `saveChanges()` thay bạn**; cần chuẩn bị thông điệp trước.

Không nên dùng lại một đối tượng `Transport` đã đóng hoặc chia sẻ một Transport đang kết nối cho nhiều luồng gửi đồng thời nếu không có cơ chế phối hợp phù hợp.

### 3.3. Ví dụ gửi email bằng Jakarta Mail thuần

Đoạn sau minh họa toàn bộ đường đi từ `Session` đến `Transport`, không yêu cầu Spring. Dùng Jakarta Mail API và một implementation hỗ trợ SMTP ở runtime:

```java
import jakarta.mail.Authenticator;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.PasswordAuthentication;
import jakarta.mail.Session;
import jakarta.mail.Transport;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

public class PlainJakartaMailExample {

    public static void main(String[] args) throws MessagingException {
        String host = "smtp.example.com";
        String username = System.getenv("SMTP_USERNAME");
        String password = System.getenv("SMTP_PASSWORD");

        if (username == null || password == null) {
            throw new IllegalStateException("Thiếu cấu hình SMTP");
        }

        Properties props = new Properties();
        props.put("mail.smtp.host", host);
        props.put("mail.smtp.port", "587");
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        Session session = Session.getInstance(props, new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                return new PasswordAuthentication(username, password);
            }
        });

        MimeMessage message = new MimeMessage(session);
        message.setFrom(new InternetAddress("no-reply@example.com"));
        message.setRecipient(
            Message.RecipientType.TO,
            new InternetAddress("alice@example.net")
        );
        message.setSubject("Xác nhận đăng ký", "UTF-8");
        message.setText(
            "Chào bạn!\nTài khoản của bạn đã được tạo.",
            "UTF-8"
        );

        // Chuẩn bị MIME headers trước khi gửi qua Transport instance.
        message.saveChanges();

        Transport transport = session.getTransport("smtp");
        try {
            transport.connect(host, username, password);
            transport.sendMessage(message, message.getAllRecipients());
        } finally {
            transport.close();
        }
    }
}
```

Ứng dụng thực tế cần thay `smtp.example.com`, địa chỉ gửi/nhận, cổng và cấu hình theo nhà cung cấp. Đoạn code gửi email thật khi chạy với cấu hình hợp lệ; nên thử trên SMTP sandbox hoặc môi trường được cấp phép trước khi sử dụng với người nhận thật.

Điều quan trọng ở ví dụ:

- `Session` được tạo **trước**, nhưng chưa có kết nối mạng.
- `MimeMessage` lưu người gửi, người nhận, tiêu đề, nội dung và header MIME.
- `message.saveChanges()` chuẩn bị các header do Jakarta Mail quản lý; có thể bao gồm `Message-ID`.
- `session.getTransport("smtp")` lấy Transport thuộc provider SMTP.
- `connect(...)` mở phiên gửi, `sendMessage(...)` chuyển thông điệp tới server.
- `close()` giải phóng kết nối dù thao tác gửi thành công hay ném lỗi.

Nếu mục tiêu chỉ là gửi email qua Spring, **không cần tự viết lại đoạn quản lý Transport này**. Spring Mail đã cung cấp lớp API giúp thực hiện thao tác gửi.

## 4. Message và MimeMessage: đối tượng đại diện email

### 4.1. Message là lớp trừu tượng

`jakarta.mail.Message` đại diện cho một thông điệp, bao gồm:

- `From` và các loại người nhận `TO`, `CC`, `BCC`.
- `Subject`, `Date` và các trường header.
- Nội dung thư.
- Một số trạng thái/phương thức hỗ trợ đọc thư trong môi trường Store/Folder.

`Message` là kiểu trừu tượng, nên khi tạo một thư Internet mới, lập trình viên thường dùng `MimeMessage`:

```java
MimeMessage message = new MimeMessage(session);
```

`MimeMessage` biết cách tạo và đọc thông điệp theo cú pháp email Internet và MIME. Nó có các phương thức như `setSubject(...)`, `setText(...)`, `setContent(...)`, `addHeader(...)`, `getMessageID()`, `getAllRecipients()` và `saveChanges()`.

### 4.2. Address, InternetAddress và RecipientType

Jakarta Mail dùng kiểu `Address` trừu tượng, trong email Internet thì `InternetAddress` là implementation phổ biến:

```java
import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;

message.setFrom(new InternetAddress("no-reply@example.com"));

message.setRecipients(
    Message.RecipientType.TO,
    InternetAddress.parse("alice@example.net,bob@example.org", true)
);

message.addRecipient(
    Message.RecipientType.CC,
    new InternetAddress("team@example.com")
);
```

`Message.RecipientType` phân biệt:

| Loại | Thể hiện trong thông điệp | Ý nghĩa |
|---|---|---|
| `TO` | Header `To:` | Người nhận chính. |
| `CC` | Header `Cc:` | Người nhận được biết công khai như bản sao thư. |
| `BCC` | Người nhận theo phong bì, thông thường không lộ trong header ở thư được gửi | Người nhận bản sao ẩn. |

Địa chỉ trong header không phải toàn bộ câu chuyện SMTP: `MAIL FROM` và `RCPT TO` là **phong bì** ở tầng giao thức. Jakarta Mail/provider xác định cách chuyển địa chỉ từ message sang giao dịch SMTP.

Khi địa chỉ đến từ input bên ngoài, cần kiểm tra và xử lý giá trị hợp lệ; `InternetAddress.parse(...)` giúp phân tích cú pháp, nhưng **không bảo đảm** hộp thư thực sự tồn tại hoặc nhận được email.

### 4.3. Header, Date và Message-ID

`MimeMessage` có thể chứa:

```text
From: Example App <no-reply@example.com>
To: alice@example.net
Subject: Xac nhan dang ky
Date: Thu, 12 Nov 2026 08:00:00 +0000
Message-ID: <unique-id@mailer.example.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
```

`Message-ID` là định danh **thông điệp email** trong header, không phải ID giao dịch SMTP, ID hàng đợi server hay ID nghiệp vụ. Thư viện có thể sinh header này trong quá trình `saveChanges()`.

Nếu ứng dụng cần truy vết giao dịch gửi email, nên có **correlation ID hoặc outbox ID riêng** trong database. Giá trị `Message-ID` có thể được sinh muộn hoặc bị hạ tầng mail chỉnh sửa theo chính sách, nên không nên dùng nó làm khóa nghiệp vụ duy nhất.

### 4.4. saveChanges() thực hiện điều gì?

`saveChanges()` báo cho `MimeMessage` rằng đối tượng đã có thay đổi và cần hoàn thiện trạng thái MIME/header trước khi gửi. Đây là thao tác ở **bộ nhớ/định dạng thông điệp**, **không tạo kết nối SMTP và không gửi email**.

Lưu ý:

- Với `Transport.send(message)` dạng tĩnh, Jakarta Mail gọi bước chuẩn bị thông điệp.
- Với `transport.sendMessage(message, recipients)` dạng instance, nên gọi `message.saveChanges()` trước.
- Một số header được Jakarta Mail tự quản lý; việc đọc `getMessageID()` trước khi thông điệp được chuẩn bị có thể trả về `null` hoặc giá trị chưa phải cuối cùng.
- Không nên thay đổi cùng một `MimeMessage` từ nhiều luồng trong khi đang gửi.

## 5. MIME: Multipart, BodyPart và DataHandler

Đối tượng `MimeMessage` không chỉ chứa văn bản đơn giản. Với ảnh inline, HTML và file đính kèm, nội dung thư có thể được cấu thành từ nhiều phần:

```text
MimeMessage
  |
  +-- MimeMultipart (multipart/mixed)
       |
       +-- MimeBodyPart (multipart/related)
       |    |
       |    +-- text/html
       |    +-- image/png (inline, Content-ID)
       |
       +-- MimeBodyPart (application/pdf, attachment)
```

Các đối tượng:

- `Multipart` và `BodyPart` là các kiểu tổng quát.
- `MimeMultipart` và `MimeBodyPart` là implementation cho nội dung MIME.
- `DataHandler` cùng các kiểu `DataSource` của Jakarta Activation hỗ trợ biểu diễn nội dung nhị phân và loại MIME của dữ liệu.
- `Content-Type` xác định loại dữ liệu như `text/plain`, `text/html`, `image/png`, `application/pdf`.
- `Content-Disposition` có thể mô tả một phần là `inline` hay `attachment`.
- `Content-ID` cho phép HTML tham chiếu một phần inline bằng `cid:...`.

### 5.1. Ví dụ MIME thuần: text và HTML thay thế nhau

Với Jakarta Mail, có thể tạo `multipart/alternative` để cung cấp cả plain text và HTML:

```java
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMultipart;

MimeBodyPart plain = new MimeBodyPart();
plain.setText("Chào bạn, cảm ơn đã đăng ký.", "UTF-8");

MimeBodyPart html = new MimeBodyPart();
html.setContent(
    "<html><body><b>Chào bạn</b>, cảm ơn đã đăng ký.</body></html>",
    "text/html; charset=UTF-8"
);

MimeMultipart alternative = new MimeMultipart("alternative");
alternative.addBodyPart(plain);
alternative.addBodyPart(html);

message.setContent(alternative);
message.saveChanges();
```

`multipart/alternative` nghĩa là **nhiều phiên bản của cùng nội dung**. Client chọn phiên bản thích hợp; không phải hai email riêng.

Khi HTML cần hình ảnh inline, dùng `multipart/related` với `Content-ID`; khi cần tệp đính kèm độc lập, có thể dùng `multipart/mixed`. Các container này có thể lồng nhau.

Trong ứng dụng Spring, việc tạo MIME bằng tay thường được thay bằng **`MimeMessageHelper`**, giúp giảm lỗi boundary, encoding, inline resource và attachment.

## 6. Authenticator và các đối tượng xác thực

`Authenticator` là nơi Jakarta Mail lấy thông tin đăng nhập khi provider yêu cầu. Một implementation phổ biến trả về `PasswordAuthentication`:

```java
Authenticator authenticator = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        return new PasswordAuthentication(username, password);
    }
};

Session session = Session.getInstance(props, authenticator);
```

Không nên nhầm:

| Thành phần | Vai trò |
|---|---|
| `Authenticator` | Cấp thông tin xác thực cho provider. |
| `PasswordAuthentication` | Chứa thông tin tên đăng nhập/mật khẩu. |
| `Transport.connect(...)` | Thực hiện kết nối và quá trình đăng nhập phù hợp thông qua provider. |
| TLS / STARTTLS | Bảo vệ kênh truyền, không thay thế credential. |
| Quyền gửi trên SMTP server | Chính sách do máy chủ quyết định, không được bảo đảm chỉ bởi việc có credential. |

Một số SMTP relay nội bộ không yêu cầu đăng nhập mà áp dụng quy tắc mạng hoặc IP; khi đó cấu hình `mail.smtp.auth` phụ thuộc chính sách relay.

Không đưa mật khẩu vào email, `Message-ID`, header tùy biến, log hoặc exception message lưu lâu dài. Bật debug chỉ trong môi trường được kiểm soát.

## 7. Store và Folder: phía đọc email của Jakarta Mail

Dù bài toán Spring Framework Mail chủ yếu là **gửi**, việc biết `Store` và `Folder` giúp hiểu đầy đủ API Jakarta Mail:

- `Transport` dùng cho đường **gửi**.
- `Store` dùng cho đường **truy cập kho thư** từ server.
- `Folder` đại diện hộp thư/thư mục cụ thể trong Store.
- `Message` cũng là kiểu dữ liệu mà ứng dụng nhận được khi đọc thư.

Ví dụ đọc vài metadata từ hộp thư IMAPS:

```java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

public class InboxReader {

    public static void inspectInbox(String username, String password)
            throws Exception {
        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.host", "imap.example.com");
        props.put("mail.imaps.port", "993");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "5000");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");
        Folder inbox = null;

        try {
            store.connect("imap.example.com", username, password);
            inbox = store.getFolder("INBOX");
            inbox.open(Folder.READ_ONLY);

            int count = inbox.getMessageCount();
            int start = Math.max(1, count - 4);

            if (count > 0) {
                Message[] messages = inbox.getMessages(start, count);
                for (Message message : messages) {
                    System.out.println(message.getSubject());
                }
            }
        } finally {
            if (inbox != null && inbox.isOpen()) {
                inbox.close(false);
            }
            store.close();
        }
    }
}
```

Đoạn code chỉ minh họa API; server IMAP cần tồn tại và hỗ trợ cơ chế xác thực tương ứng. Nếu tài khoản yêu cầu OAuth hoặc cơ chế đặc biệt, cần cấu hình provider theo dịch vụ thực tế.

**`Store` không được sử dụng để gửi SMTP.** Tương tự, việc gọi `JavaMailSender.send(...)` không mở hộp thư `INBOX` hoặc đọc thư bằng `Folder`.

Khi đọc thư số lượng lớn, nên chú ý hiệu năng, phân trang, `FetchProfile`, truy vấn/tìm kiếm và cơ chế UID của IMAP. Số thứ tự message trong một folder không phải định danh toàn cục ổn định của email.

## 8. Spring Mail trừu tượng hóa Jakarta Mail thế nào?

Spring Framework Mail có các abstraction nổi bật:

| Spring Mail | Jakarta Mail liên quan | Ghi chú |
|---|---|---|
| `MailSender` | Quy trình gửi thông điệp | API Spring đơn giản cho `SimpleMailMessage`. |
| `JavaMailSender` | `Session`, `MimeMessage`, `Transport` | Interface gửi MIME message và tạo MIME message. |
| `JavaMailSenderImpl` | `Session` và SMTP transport | Implementation Spring thường dùng để kết nối SMTP. |
| `SimpleMailMessage` | Chuyển sang thông điệp gửi | Mô hình text đơn giản của Spring, không phải `MimeMessage`. |
| `MimeMessageHelper` | `MimeMessage`, MIME multipart và resource | Hỗ trợ HTML, attachment, inline, encoding, địa chỉ. |
| `MimeMessagePreparator` | Chuẩn bị `MimeMessage` | Callback để cấu hình thông điệp trước khi gửi. |
| `MailException` | Lỗi được Spring chuyển đổi hoặc bao bọc | Nhóm unchecked exceptions của Spring Mail. |

Trong Spring, ứng dụng thường làm việc qua `JavaMailSender` để tách code nghiệp vụ khỏi chi tiết transport SMTP.

### 8.1. Cấu hình Spring Boot

Spring Boot có thể tự cấu hình `JavaMailSender` khi dependency và thuộc tính phù hợp hiện diện. Ví dụ Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

`application.yml` cho SMTP submission cổng 587:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Trong Spring Boot, các cấu hình `spring.mail.properties.mail.smtp.*` được chuyển đến mail provider tương ứng. Timeout phía socket trong ví dụ tính bằng mili giây. Các biến môi trường cần được cấp qua hệ thống triển khai, không ghi mật khẩu thật vào cấu hình được commit.

Với Spring Framework không dùng Boot, có thể đăng ký bean:

```java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class SmtpMailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
```

Code minh họa giả định runtime đã có Jakarta Mail implementation, có biến môi trường cấu hình, và SMTP host dùng cơ chế STARTTLS phù hợp. Việc quản lý credential, giám sát lỗi và tích hợp secret store cần tuân theo môi trường triển khai thực tế.

### 8.2. Sử dụng MimeMessageHelper

Ví dụ service Spring gửi HTML có phiên bản text:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {

    private final JavaMailSender mailSender;

    public AccountMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");
        helper.setText(
            "Xin chào, chào mừng bạn đến với ứng dụng.",
            "<html><body><h1>Chào mừng!</h1>"
                + "<p>Rất vui vì có bạn tham gia.</p></body></html>"
        );

        mailSender.send(message);
    }
}
```

Ở đây:

- Spring tạo đối tượng `MimeMessage` thích hợp với cấu hình gửi.
- `MimeMessageHelper` đặt header, nội dung và cấu trúc MIME.
- `JavaMailSenderImpl` sử dụng Jakarta Mail để tạo/quản lý kết nối SMTP phù hợp.
- Service không cần tự lấy `Transport`, gọi `connect(...)` hay `close()`.

Sử dụng `MimeMessageHelper(message, true, "UTF-8")` cho phép nội dung nhiều phần. Nếu chỉ gửi text đơn giản, `SimpleMailMessage` có thể là đủ.

### 8.3. MimeMessagePreparator: callback cấu hình thông điệp

Spring cho phép gửi email qua callback `MimeMessagePreparator`:

```java
mailSender.send(mimeMessage -> {
    MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo("alice@example.net");
    helper.setSubject("Thông báo");
    helper.setText("Nội dung thông báo");
});
```

Cách này thích hợp khi phần chuẩn bị MIME được đóng gói vào một thao tác và không cần giữ lại đối tượng message trong service. Spring vẫn chịu trách nhiệm tổ chức quá trình gửi.

## 9. So sánh luồng Jakarta Mail thuần và Spring JavaMailSender

<div>

```text
Jakarta Mail thuần
-------------------------------------------
Properties / Authenticator
      -> Session
      -> MimeMessage
      -> saveChanges()
      -> session.getTransport("smtp")
      -> connect()
      -> sendMessage()
      -> close()

Spring Mail
-------------------------------------------
JavaMailSender (đã cấu hình)
      -> createMimeMessage()
      -> MimeMessageHelper hoặc Preparator
      -> send()
            |
            +--> JavaMailSenderImpl và Jakarta Mail
                 thực hiện thao tác SMTP
```

</div>

Hai đường đi sử dụng các khái niệm nền tảng tương tự. Spring không thay đổi bản chất `Session` hay giao thức SMTP; Spring cung cấp giao diện thuận tiện, tích hợp container, cấu hình và ngoại lệ phù hợp với ứng dụng.

| Tiêu chí | Jakarta Mail trực tiếp | Spring JavaMailSender |
|---|---|---|
| Tạo `Session` | Tự tạo và cấu hình. | Thường do `JavaMailSenderImpl`/Boot quản lý. |
| Tạo nội dung thư | `MimeMessage` và các API MIME. | `SimpleMailMessage` hoặc `MimeMessage` + `MimeMessageHelper`. |
| Gửi | `Transport.send(...)` hoặc `Transport.sendMessage(...)`. | `JavaMailSender.send(...)`. |
| Quản lý kết nối | Có thể tự điều khiển `Transport`. | Thường được implementation xử lý. |
| Xử lý exception | `MessagingException` và các lớp con. | `MailException` và các lớp con; thao tác xây MIME vẫn có thể ném `MessagingException`. |
| Mức phụ thuộc code nghiệp vụ | Gắn trực tiếp API Jakarta Mail. | Có thể phụ thuộc interface Spring để thay implementation dễ hơn. |

**Nếu ứng dụng đã chạy trên Spring**, mặc định nên bắt đầu với `JavaMailSender`. Dùng API Jakarta Mail trực tiếp khi cần thao tác cụ thể mà abstraction Spring không trình bày phù hợp, ví dụ đọc thư qua IMAP/POP3 hoặc quản lý một kết nối Transport theo yêu cầu riêng.

## 10. Vòng đời thực tế và các điểm cần tránh nhầm lẫn

### 10.1. Một Session có bằng một kết nối SMTP không?

**Không.** Có thể tạo một `Session` rồi sinh ra nhiều `MimeMessage` và nhiều `Transport` theo thời gian. Ngược lại, một `Transport` đã kết nối có thể gửi nhiều message trong cùng phiên SMTP nếu được sử dụng đúng cách.

### 10.2. Gọi saveChanges() có gửi mail không?

**Không.** `saveChanges()` cập nhật trạng thái/header MIME. Chỉ thao tác gửi qua `Transport` hoặc abstraction tương ứng mới bắt đầu gửi dữ liệu đến mail server.

### 10.3. Transport gửi thành công nghĩa là người nhận đã đọc?

**Không.** Máy chủ SMTP có thể chấp nhận message rồi xếp hàng chuyển tiếp. Bounce hoặc từ chối ở các chặng sau vẫn có thể xảy ra. Trạng thái giao hàng cần dữ liệu từ nhà cung cấp hoặc hạ tầng email; kết quả `sendMessage(...)` không phải báo cáo lượt mở thư.

### 10.4. Jakarta Mail có tự xử lý retry đúng một lần không?

Không nên giả định. Một timeout xảy ra sau khi client truyền đủ thông điệp nhưng trước khi nhận phản hồi cuối có thể để lại **trạng thái không xác định**: server đã nhận thư hay chưa. Retry ngay có thể gây trùng email. Đối với quy trình quan trọng, sử dụng outbox, queue, backoff, correlation ID và đối soát trạng thái theo khả năng của provider.

### 10.5. Đóng Transport có xóa message không?

**Không.** `Transport.close()` đóng dịch vụ/kết nối truyền tải. `MimeMessage` là đối tượng chứa nội dung thư ở phía ứng dụng; việc đóng Transport không có nghĩa thao tác xóa đối tượng message hay xóa bản đã được SMTP server tiếp nhận.

### 10.6. Có thể chia sẻ MimeMessage giữa nhiều job gửi không?

Thông thường nên tạo một `MimeMessage` riêng cho mỗi thông điệp. Việc nhiều worker cùng chỉnh sửa một message dễ gây lẫn header, người nhận và trạng thái `saveChanges()`. Nếu cần gửi một nội dung đến nhiều người nhận, nên quyết định rõ đó là **một message có nhiều recipient** hay **nhiều message cá nhân hóa**, vì hai lựa chọn ảnh hưởng đến nội dung, Message-ID và quản lý lỗi từng người.

## 11. Xử lý lỗi: Jakarta Mail và Spring Mail

### 11.1. Exception thường gặp của Jakarta Mail

Các loại lỗi điển hình:

| Lỗi | Tình huống ví dụ |
|---|---|
| `MessagingException` | Nhóm lỗi tổng quát khi xử lý message, kết nối hoặc giao thức. |
| `AuthenticationFailedException` | Đăng nhập mail server không thành công. |
| `SendFailedException` | Thao tác gửi gặp lỗi, có thể liên quan người nhận không hợp lệ hoặc gửi một phần. |
| `AddressException` | Cú pháp địa chỉ email không hợp lệ trong quá trình parse. |
| `FolderClosedException` / `StoreClosedException` | Tài nguyên đọc hộp thư bị đóng trong lúc thao tác. |

Khi đọc exception, cần phân biệt **thông điệp có tạo được không**, **kết nối có mở được không**, **server đã xác thực chưa**, **người nhận nào được chấp nhận**, và **server đã tiếp nhận toàn bộ DATA hay chưa**.

Một `SendFailedException` có thể liên quan danh sách người nhận hợp lệ/không hợp lệ ở tầng Jakarta Mail. Không nên giả định mọi trường hợp ném exception đều có nghĩa **không người nhận nào nhận được thư**.

### 11.2. Spring MailException

Khi sử dụng `JavaMailSender`, Spring có thể ném các lỗi như:

- `MailAuthenticationException`: lỗi xác thực với máy chủ gửi.
- `MailSendException`: lỗi thực hiện gửi.
- `MailParseException`: lỗi khi chuẩn bị/diễn giải message.
- `MailPreparationException`: lỗi ở giai đoạn chuẩn bị message.

Các lớp này thuộc nhánh `MailException` của Spring và là unchecked exceptions. Trong khi đó, các thao tác trên `MimeMessage` hoặc `MimeMessageHelper` có thể vẫn khai báo `MessagingException` thuộc Jakarta Mail.

Ví dụ phân loại ở mức service:

```java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;

try {
    mailSender.send(message);
} catch (MailAuthenticationException ex) {
    // Kiểm tra credential, cơ chế AUTH và chính sách máy chủ.
    throw ex;
} catch (MailSendException ex) {
    // Ghi nhận attempt, loại lỗi và khả năng gửi một phần.
    throw ex;
} catch (MailException ex) {
    // Các vấn đề gửi khác của Spring Mail.
    throw ex;
}
```

Mẫu trên là minh họa về **phân loại** chứ không phải retry policy hoàn chỉnh. Không nên retry vô hạn cho lỗi xác thực hoặc địa chỉ người nhận sai.

### 11.3. Cấu hình timeout và TLS

Các property SMTP quan trọng:

| Thuộc tính | Mục đích |
|---|---|
| `mail.smtp.host` | Máy chủ SMTP. |
| `mail.smtp.port` | Cổng SMTP. |
| `mail.smtp.auth` | Bật sử dụng xác thực SMTP khi server yêu cầu. |
| `mail.smtp.starttls.enable` | Cho phép STARTTLS nếu server hỗ trợ. |
| `mail.smtp.starttls.required` | Yêu cầu STARTTLS thành công. |
| `mail.smtp.ssl.enable` | Bật implicit TLS từ đầu kết nối, thường phù hợp cổng 465 theo provider. |
| `mail.smtp.connectiontimeout` | Giới hạn thời gian chờ tạo kết nối. |
| `mail.smtp.timeout` | Giới hạn thời gian chờ đọc socket. |
| `mail.smtp.writetimeout` | Giới hạn thời gian chờ ghi socket. |

Với cổng 587, cấu hình thường dùng STARTTLS; với 465 thường dùng implicit TLS. Không cấu hình sai mô hình TLS so với cổng thực tế.

Khi bật debug:

```java
session.setDebug(true);
```

Chỉ bật trong môi trường thử nghiệm được kiểm soát; dữ liệu giao thức và metadata email có thể chứa thông tin nhạy cảm. Không gửi log debug chứa credential, nội dung thư hoặc token cho nơi không được phép truy cập.

## 12. Những lỗi thiết kế thường gặp

**“Tạo Session đã kiểm tra kết nối SMTP.”** Sai. Session chủ yếu là cấu hình; muốn kiểm tra kết nối cần dùng Transport để thực hiện giao tiếp với server.

**“Transport và Store là hai tên gọi cho cùng thao tác.”** Sai. Transport dùng gửi; Store dùng đọc/quản lý kho thư.

**“MimeMessageHelper là lớp của Jakarta Mail.”** Sai. `MimeMessageHelper` là tiện ích của Spring, xây dựng trên các đối tượng Jakarta Mail.

**“SimpleMailMessage là MimeMessage.”** Sai. `SimpleMailMessage` là kiểu dữ liệu riêng của Spring để mô tả thư văn bản đơn giản; Spring chuyển đổi/phối hợp với tầng Jakarta Mail khi gửi.

**“Gọi getTransport(...) đồng nghĩa đã connect.”** Sai. `getTransport(...)` lấy đối tượng transport; kết nối thường bắt đầu khi gọi `connect(...)` hoặc phương thức gửi cấp cao.

**“saveChanges() giống sendMessage().”** Sai. `saveChanges()` chuẩn bị dữ liệu thông điệp; `sendMessage(...)` gửi qua một Transport đã kết nối.

**“Transport.send trả về không lỗi là thư vào Inbox.”** Sai. Thành công tại chặng SMTP chỉ xác nhận bước tiếp nhận ở tầng máy chủ tương ứng.

**“Để tăng tốc, chia sẻ một MimeMessage cho mọi luồng.”** Không phù hợp. Dễ trộn thông tin người nhận, nội dung và header. Nên tạo message riêng cho từng thông điệp.

**“Dùng javax.mail trong ví dụ Spring Framework 6 là tương đương jakarta.mail.”** Không. Spring Framework 6 và Spring Boot 3 dùng namespace Jakarta; các ứng dụng thế hệ trước có thể còn dùng `javax.mail`. Không trộn hai namespace tùy tiện trong cùng đoạn code.

## 13. Bài tập thực hành

### Bài 1: Xác định trách nhiệm

Cho các nhiệm vụ: (a) giữ SMTP properties; (b) tạo nội dung MIME; (c) mở kết nối và gửi; (d) đọc `INBOX`; (e) đại diện địa chỉ email; (f) tạo nội dung HTML có attachment thuận tiện trong Spring.

Hãy ghép chúng với `Session`, `MimeMessage`, `Transport`, `Store/Folder`, `InternetAddress` và `MimeMessageHelper`.

**Gợi ý:** (a) Session; (b) MimeMessage; (c) Transport; (d) Store/Folder; (e) InternetAddress; (f) MimeMessageHelper.

### Bài 2: Sửa lỗi thiếu saveChanges

Một ứng dụng dùng Jakarta Mail trực tiếp:

```java
MimeMessage message = new MimeMessage(session);
message.setFrom(new InternetAddress("no-reply@example.com"));
message.setRecipient(
    Message.RecipientType.TO,
    new InternetAddress("alice@example.net")
);
message.setSubject("Thong bao");
message.setText("Noi dung");

Transport transport = session.getTransport("smtp");
transport.connect(host, username, password);
transport.sendMessage(message, message.getAllRecipients());
transport.close();
```

Hãy bổ sung thao tác chuẩn bị message trước `sendMessage(...)` và đưa `close()` vào `finally` để tài nguyên được giải phóng cả khi lỗi.

### Bài 3: Chuyển mã Jakarta Mail thuần sang Spring Mail

Cho một hàm gửi text có `Session`, `MimeMessage`, `Transport.connect(...)`, `sendMessage(...)` và `close()`. Hãy viết lại bằng constructor inject `JavaMailSender`, tạo `MimeMessage` từ sender, dùng `MimeMessageHelper` đặt các trường và gọi `mailSender.send(message)`.

Mục tiêu là thay code nghiệp vụ phụ thuộc trực tiếp vòng đời Transport bằng abstraction gửi của Spring.

### Bài 4: Đọc log lỗi

Tình huống: ứng dụng tạo Session bình thường, nhưng đến `transport.connect(...)` thì gặp timeout. Việc tạo Session thành công chứng minh điều gì?

**Đáp án:** Chỉ chứng minh đối tượng cấu hình đã được tạo. Nó không chứng minh SMTP host có thể truy cập hoặc xác thực được. Cần kiểm tra DNS, host, cổng, firewall, TLS và timeout.

### Bài 5: So sánh gửi và đọc

Ứng dụng cần gửi email xác nhận đơn hàng và đọc email phản hồi từ `INBOX`. Hai luồng cần các đối tượng nào?

**Gợi ý:** gửi qua `JavaMailSender` hoặc `Session + Transport + MimeMessage`; đọc qua `Session + Store + Folder + Message`. `JavaMailSender` không phải API đọc hộp thư.

### Bài 6: Đề xuất cách xử lý retry

Worker đã truyền email đến SMTP server nhưng timeout trước khi nhận phản hồi cuối. Có thể coi đây là “chưa gửi” và gọi lại ngay không?

**Gợi ý:** Không thể chắc chắn. Nên lưu trạng thái lần thử là chưa xác định, dùng application/outbox ID để truy vết, retry có giới hạn và đối soát trạng thái khi hạ tầng hỗ trợ. Việc dùng lại Message-ID không tự bảo đảm chống gửi trùng.

## 14. Tổng kết

Trong Jakarta Mail, **`Session` là ngữ cảnh cấu hình và factory**, **`Transport` đảm nhiệm việc gửi**, còn **`Message`/`MimeMessage` biểu diễn nội dung thông điệp**. `Address` mô hình hóa người gửi và người nhận; `Authenticator` hỗ trợ cung cấp credential; `Multipart`/`BodyPart` mô hình hóa nội dung phức tạp. Ở phía đọc thư, `Store` và `Folder` cung cấp truy cập đến các message đã lưu.

Spring Framework Mail xây trên những thành phần đó thông qua **`JavaMailSender`, `JavaMailSenderImpl` và `MimeMessageHelper`**. Hiểu cấu trúc bên dưới giúp dùng đúng API, chẩn đoán theo tầng, quản lý kết nối hợp lý và phân biệt việc máy chủ đã tiếp nhận email với việc thư thực sự được giao cho người nhận.
