# Folder, message và đánh dấu đã đọc

Trong ứng dụng sử dụng **Spring Framework Mail**, chúng ta thường quen với việc **gửi thư** qua **JavaMailSender**. Khi cần **nhận và xử lý email** — chẳng hạn đọc hộp thư hỗ trợ khách hàng, nhận phản hồi, kiểm tra mailbox thử nghiệm hoặc tự động phân loại thư đến — bài toán chuyển sang làm việc với giao thức nhận thư và các đối tượng **Store**, **Folder**, **Message** của **Jakarta Mail**.

Một email không chỉ có nội dung, người gửi và thời gian. Trên máy chủ IMAP, nó còn tồn tại trong một **folder/hộp thư**, có số thứ tự tương đối trong folder, có thể mang các **flags** như đã đọc (**SEEN**), đã trả lời (**ANSWERED**), đánh dấu sao (**FLAGGED**) hoặc chờ xóa (**DELETED**). Thay đổi cờ đã đọc thường là **một thao tác ghi trạng thái lên máy chủ**, không chỉ thay đổi một boolean trong Java.

Bài học này trình bày cách mở và duyệt folder, lấy message, đọc các header/body, tìm thư chưa đọc và đánh dấu đã đọc/chưa đọc, cùng các ranh giới về IMAP/POP3, quyền ghi, tác dụng phụ khi đọc body, UID, transaction nghiệp vụ, xử lý đồng thời và kiểm thử. Các ví dụ dùng **Jakarta Mail API**; Spring Mail chủ yếu phục vụ gửi thư và **không tự tạo một dịch vụ inbox đầy đủ** khi chỉ thêm cấu hình JavaMailSender.

> **Nguyên tắc quan trọng:** Đừng nhầm giữa **“ứng dụng đã xử lý thành công thư”** và **“mailbox đã đánh dấu SEEN”**. Đây là hai trạng thái có mục đích khác nhau. Đánh dấu đã đọc quá sớm có thể khiến worker bỏ sót công việc; đánh dấu quá muộn hoặc chỉ dựa vào SEEN có thể khiến xử lý trùng.

## 1. Những đối tượng cần biết khi đọc email

Jakarta Mail cung cấp các khái niệm cơ bản:

| Đối tượng | Trách nhiệm | Thao tác thường dùng |
| --- | --- | --- |
| **Session** | Chứa thuộc tính và cách tạo kết nối mail | Session.getInstance(properties) |
| **Store** | Đại diện kết nối tới server lưu mailbox | connect, getDefaultFolder, getFolder, close |
| **Folder** | Đại diện một hộp thư/thư mục trên Store | exists, list, open, getMessages, search, close |
| **Message** | Đại diện một thông điệp email trong folder | getFrom, getSubject, getContent, getFlags, setFlag |
| **Flags** | Tập hợp trạng thái của message | contains, add, remove |
| **SearchTerm** | Điều kiện tìm kiếm thư | FlagTerm, FromStringTerm, SubjectTerm |
| **UIDFolder** | API truy cập UID IMAP khi provider hỗ trợ | getUID, getMessageByUID, getUIDValidity |

Một mô hình trực quan:

~~~text
Application
    |
    v
Jakarta Mail Session
    |
    v
Store (IMAP/IMAPS)
    |
    +-- INBOX ------------------+
    |                          |
    |                         Message #1  [SEEN]
    |                         Message #2  [UNSEEN]
    |                         Message #3  [FLAGGED]
    |
    +-- Sent -------------------+
    |                         Message ...
    |
    '-- Archive ----------------+
                              Message ...
~~~

**Store** là một kết nối tới tài khoản/mail server; **Folder** chứa hoặc tham chiếu đến các messages; **Message** đại diện email cụ thể, nhiều thông tin có thể được tải **lười (lazy-loaded)** từ server khi code truy cập.

### Session không phải hộp thư

~~~java
Properties properties = new Properties();
Session session = Session.getInstance(properties);
~~~

Đoạn code chỉ tạo **mail session**, chưa kết nối mạng và chưa đọc email. Để nhận mail, cần lấy một **Store** phù hợp với giao thức và gọi **connect(...)**.

### Store không phải SMTP transport

**JavaMailSenderImpl** dùng SMTP để gửi. **Store** qua IMAP hoặc POP3 dùng để đọc mailbox. Không dùng **mailSender.send(...)** để đọc thư, cũng không dùng **Folder** để nộp email tới SMTP. Một ứng dụng có thể cần cả hai, nhưng chúng là hai luồng giao thức khác nhau.

## 2. Chọn IMAP hay POP3?

Hai giao thức nhận thư thường gặp là **IMAP** và **POP3**. Chúng khác nhau đáng kể về mô hình folder và flags.

| Chủ đề | IMAP | POP3 |
| --- | --- | --- |
| Nhiều folders | Có mô hình hộp thư/folder trên server | Chủ yếu là mailbox dạng danh sách, không có mô hình folders tương đương |
| Trạng thái SEEN | Có flag **\Seen** trên server | Không có cơ chế chuẩn tương đương để đồng bộ “đã đọc” giữa clients |
| Tìm kiếm server-side | Có lệnh SEARCH và khả năng tìm theo flags | Không có cùng bộ SEARCH/FLAGS |
| Định danh lâu dài | UID gắn với UIDVALIDITY của folder | UIDL có semantics khác, tùy server |
| Đồng bộ nhiều thiết bị | Thiết kế phù hợp | Hạn chế hơn |
| Xóa/move/copy | Có cơ chế flags/folders theo server | Khác biệt lớn; thường DELETE theo POP3 session |
| Đánh dấu read/unread | IMAP STORE flags | Không thể giả định hỗ trợ giống IMAP |

**Nếu yêu cầu là “xem thư chưa đọc, mở folder và đánh dấu đã đọc trên server”, IMAP/IMAPS thường phù hợp hơn POP3.** Không nên tạo một abstraction nói rằng POP3 có đầy đủ SEEN/UNSEEN giống IMAP rồi để backend thực hiện một hành động không có trong giao thức.

### Dùng kết nối bảo mật

- **IMAPS**: IMAP trên TLS ngay khi kết nối, thường dùng port **993**.
- **IMAP + STARTTLS**: IMAP thường rồi nâng cấp TLS khi server hỗ trợ và client yêu cầu, thường dùng cổng **143**.
- **POP3S**: POP3 qua TLS, thường dùng port **995**.

Các cổng chỉ là thông lệ; cấu hình thực tế do server quyết định. Nếu yêu cầu an toàn, phải xác minh certificate, hostname, cơ chế xác thực và chính sách TLS thay vì chỉ nhìn số cổng.

## 3. Cấu hình Jakarta Mail để kết nối IMAPS

Ví dụ tối giản đọc hộp thư bằng **IMAPS**:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

public class MailboxConnectionExample {

    public void connect(
            String username,
            String password
    ) throws Exception {
        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");
        props.put("mail.imaps.writetimeout", "10000");
        props.put("mail.imaps.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");

        try {
            store.connect(
                    "imap.example.test",
                    993,
                    username,
                    password
            );

            Folder inbox = store.getFolder("INBOX");
            System.out.println(inbox.getFullName());
        } finally {
            store.close();
        }
    }
}
~~~

Host và tài khoản trong ví dụ là placeholder. Trong ứng dụng thật, credentials/OAuth tokens phải được lấy từ nơi lưu secret phù hợp; không đưa password vào Git hoặc log.

### Một số thuộc tính cần lưu ý

| Property minh họa | Ý nghĩa |
| --- | --- |
| **mail.store.protocol=imaps** | Chọn giao thức Store mặc định |
| **mail.imaps.connectiontimeout** | Timeout mở kết nối |
| **mail.imaps.timeout** | Timeout đọc dữ liệu qua socket |
| **mail.imaps.writetimeout** | Timeout ghi dữ liệu |
| **mail.imaps.ssl.checkserveridentity=true** | Kiểm tra hostname trong TLS certificate |
| **mail.imaps.peek=true** | Tùy implementation, yêu cầu fetch body không tự đánh dấu SEEN |

Không nên bật cấu hình trust-all như **mail.imaps.ssl.trust=*** để bỏ qua việc xác minh certificate. Khi phải dùng private CA, cấu hình truststore phù hợp thay vì tắt kiểm tra.

### Giao thức quyết định prefix của properties

Khi dùng **imaps**, nhiều thuộc tính có tiền tố **mail.imaps.**. Với **imap + STARTTLS**, thuộc tính thường thuộc **mail.imap.**. Ví dụ:

~~~properties
mail.imap.starttls.enable=true
mail.imap.starttls.required=true
mail.imap.ssl.checkserveridentity=true
~~~

Không đặt **mail.smtp.starttls.required** rồi kỳ vọng nó bảo vệ IMAP Store; SMTP và IMAP có bộ cấu hình riêng.

### Xác thực không nhất thiết chỉ là mật khẩu thường

Nhiều providers yêu cầu OAuth 2.0 hoặc phương thức authentication cụ thể thay vì mật khẩu đăng nhập thông thường. Việc chọn mechanism và token/refresh policy tùy server, JavaMail implementation và hệ thống identity. Ví dụ trong bài dùng username/password để trình bày API cơ bản, không phải khuyến nghị dùng basic password cho mọi mailbox production.

## 4. Vòng đời Store và Folder

Trước khi thao tác với messages, **Folder** thường phải được mở bằng **open(...)**. Sau khi xử lý, phải đóng folder và store để giải phóng connection/tài nguyên.

~~~java
Store store = session.getStore("imaps");
Folder inbox = null;

try {
    store.connect(host, port, user, secret);

    inbox = store.getFolder("INBOX");
    if (!inbox.exists()) {
        throw new IllegalStateException("INBOX không tồn tại");
    }

    inbox.open(Folder.READ_ONLY);

    int count = inbox.getMessageCount();
    System.out.println("Messages: " + count);
} finally {
    if (inbox != null && inbox.isOpen()) {
        inbox.close(false);
    }
    if (store.isConnected()) {
        store.close();
    }
}
~~~

**close(false)** không thực hiện yêu cầu expunge thư đã được đánh dấu DELETED; nó không có nghĩa rollback tất cả thay đổi flags. Việc cập nhật flags trong phiên READ_WRITE có thể đã được server ghi nhận trước khi folder được đóng.

### Dùng READ_ONLY và READ_WRITE đúng ý định

~~~java
inbox.open(Folder.READ_ONLY);
~~~

Chế độ này phù hợp để quan sát metadata/thư mà ứng dụng **không cần thay đổi flags**. Để đánh dấu SEEN hoặc xóa flag:

~~~java
inbox.open(Folder.READ_WRITE);
~~~

Nếu server hoặc mailbox permissions không cho phép ghi, việc mở READ_WRITE hoặc gọi setFlag có thể thất bại. Không giả định mọi folder đều có quyền ghi chỉ vì Store đã xác thực thành công.

### Folder object không nhất thiết độc lập với Store

Không nên lấy một Message từ Folder, đóng Store rồi kỳ vọng mọi lời gọi **getContent()**, **getFlags()**, **getInputStream()** vẫn chạy bình thường. Nhiều phần dữ liệu được tải từ server theo yêu cầu và có thể sinh **FolderClosedException** hoặc **StoreClosedException** sau khi connection đóng.

Giữ nguyên ranh giới:

~~~text
Connect Store
  -> Open Folder
      -> Fetch metadata/body cần thiết
      -> Lưu kết quả nghiệp vụ / cập nhật flags nếu được phép
  -> Close Folder
-> Close Store
~~~

### Không chia sẻ Folder/Message bừa bãi giữa threads

IMAP Store/Folder có connection state và message sequence numbers có thể thay đổi khi server cập nhật. Không nên dùng cùng một Folder đang mở để nhiều worker thread xử lý và set flags đồng thời nếu chưa có chiến lược synchronization và hiểu rõ implementation. Thông thường hãy giới hạn một owner xử lý một mailbox/partition hoặc tạo session/connection độc lập với kiểm soát concurrency.

## 5. Folder là gì trong IMAP?

Một **Folder** là container được server trình bày cho các messages. Folder có thể có:

- Tên ngắn (**getName**) và tên đầy đủ (**getFullName**).
- Folder cha (**getParent**) và các folder con (**list**).
- Thuộc tính được phép chứa messages (**HOLDS_MESSAGES**).
- Thuộc tính được phép chứa folder con (**HOLDS_FOLDERS**).
- Số message, số thư chưa đọc, trạng thái mở và khả năng ghi.

Ví dụ phân cấp:

~~~text
Mailbox account
  |
  +-- INBOX
  +-- INBOX/Support
  +-- INBOX/Billing
  +-- Sent
  +-- Drafts
  '-- Archive
~~~

Cấu trúc trên chỉ minh họa. Không phải server nào cũng dùng dấu **/** làm separator, không phải tất cả folder đều nằm dưới INBOX và tên folder theo provider có thể được quốc tế hóa hoặc mang semantics đặc biệt.

### INBOX là folder chuẩn đặc biệt

Trong IMAP, **INBOX** là tên mailbox được giao thức xử lý đặc biệt và thường có mặt trong tài khoản. Các tên như Sent, Trash, Spam, Archive có thể khác nhau theo server/localization và special-use attributes. Không hard-code rằng mọi provider có tên folder “Sent” hoặc “Spam” giống nhau.

### Xem metadata folder

~~~java
Folder folder = store.getFolder("INBOX");

if (folder.exists()) {
    System.out.println("Name: " + folder.getName());
    System.out.println("Full name: " + folder.getFullName());
    System.out.println("Type: " + folder.getType());
}
~~~

Một số phép đọc metadata không cần folder open, nhưng các phương thức như getMessages/getMessage/getPermanentFlags yêu cầu trạng thái và hỗ trợ tương ứng. Hãy đọc hợp đồng API cụ thể, bắt lỗi **MessagingException** và không dựa vào việc server nào cũng cung cấp mọi metadata khi folder đang đóng.

## 6. Liệt kê folders và xác định folder mục tiêu

Ví dụ duyệt folders dưới default root:

~~~java
import jakarta.mail.Folder;

Folder root = store.getDefaultFolder();
for (Folder folder : root.list()) {
    System.out.printf(
            "Folder=%s, type=%d%n",
            folder.getFullName(),
            folder.getType()
    );
}
~~~

**getDefaultFolder()** là điểm bắt đầu logical cho cây folders; nó không phải một hộp thư chứa messages mà ứng dụng nhất thiết có thể open và đọc như INBOX.

### Duyệt có giới hạn

Không nên đệ quy vô hạn qua mọi folder hoặc gọi toàn bộ getMessages cho từng folder khi chỉ muốn tìm inbox công việc. Với mailbox doanh nghiệp có hàng trăm folders, nên:

- Dùng folder name/configuration rõ ràng được quản trị xác nhận.
- Lưu folder ID/name được ánh xạ theo account/provider.
- Giới hạn depth hoặc số lượng folder duyệt.
- Không fetch message bodies khi chỉ đang liệt kê folders.
- Xử lý folders bị xóa/đổi tên giữa các lần duyệt.

### Tên folder và delimiter

IMAP có hierarchy delimiter do server cung cấp. Không tự ghép đường dẫn thư mục bằng hệ điều hành **Path.resolve(...)**, vì đây là tên logical trên IMAP server, không phải filesystem path local. Nếu cần truy cập folder con:

~~~java
Folder parent = store.getFolder("INBOX");
Folder child = parent.getFolder("Support");
~~~

Khả năng resolve folder con và tên thực tế phụ thuộc server. Nếu thư mục đã được đổi tên trong lúc worker chạy, xử lý **FolderNotFoundException** hoặc lỗi tương ứng thay vì tự tạo lại thư mục ngoài ý muốn.

## 7. Message number: vị trí trong folder, không phải định danh lâu dài

Khi folder được mở, Jakarta Mail cho phép:

~~~java
int count = inbox.getMessageCount();
Message first = inbox.getMessage(1);
Message last = inbox.getMessage(count);
~~~

Đây là **message sequence number** tính từ 1 trong folder đang mở. Không gọi getMessage(0). Với folder rỗng, count=0 nên cũng không được gọi getMessage(count).

### Vì sao message number không ổn định?

Trên IMAP, khi một message bị xóa/expunge, các sequence numbers của những messages phía sau có thể thay đổi:

~~~text
Trước expunge:
  #1 -> Message A
  #2 -> Message B
  #3 -> Message C

Xóa + expunge Message B:
  #1 -> Message A
  #2 -> Message C
~~~

Vì vậy **số 2 không phải khóa database bền vững**. Không lưu messageNumber=2 để ngày mai quay lại xử lý cùng thư nếu mailbox có thể thay đổi.

### Duyệt trong một snapshot ngắn hạn

~~~java
int total = inbox.getMessageCount();
for (int index = 1; index <= total; index++) {
    Message message = inbox.getMessage(index);
    // Chỉ thao tác trong thời gian folder còn open.
}
~~~

Ví dụ chỉ minh họa API; với mailbox lớn hoặc nhiều clients thay đổi đồng thời, nên dùng **server-side search, batch fetch và UID** thay vì load toàn bộ message hoặc dựa vào index liên tục.

## 8. Đọc thông tin cơ bản của một Message

Một đối tượng **jakarta.mail.Message** có thể cung cấp:

| Thành phần | API thường dùng | Lưu ý |
| --- | --- | --- |
| Người gửi | getFrom() | Có thể có nhiều Address, thiếu hoặc bị giả mạo |
| Người nhận | getRecipients(Message.RecipientType.TO) | Không phải mọi recipient đều có trong To; Bcc có thể không hiện |
| Chủ đề | getSubject() | Thường được thư viện decode từ MIME encoded-words |
| Ngày gửi | getSentDate() | Có thể null hoặc bị sender đặt sai |
| Ngày nhận | getReceivedDate() | Khả năng cung cấp tùy provider |
| Message-ID header | getHeader("Message-ID") | Không phải ID tin cậy/duy nhất toàn hệ thống |
| MIME type | isMimeType("text/plain") | Kiểm tra loại nội dung hiện tại |
| Nội dung | getContent(), getInputStream() | Có thể tải body qua mạng và làm thay đổi SEEN |
| Flags | getFlags(), isSet(flag) | Trạng thái trên mailbox |
| Folder | getFolder() | Liên kết với folder hiện tại |
| Message number | getMessageNumber() | Không phải khóa ổn định |

Ví dụ đọc **chỉ metadata**:

~~~java
import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import java.util.Date;

public record MessageSummary(
        int sequenceNumber,
        String subject,
        String from,
        Date sentDate,
        boolean seen
) {
}

public static MessageSummary toSummary(Message message)
        throws MessagingException {
    Address[] senders = message.getFrom();
    String sender = senders == null || senders.length == 0
            ? "(unknown)"
            : senders[0].toString();

    return new MessageSummary(
            message.getMessageNumber(),
            message.getSubject(),
            sender,
            message.getSentDate(),
            message.isSet(jakarta.mail.Flags.Flag.SEEN)
    );
}
~~~

**Cần phân biệt:** trường From hoặc Message-ID đến từ nội dung/header email, có thể bị bên gửi kiểm soát hoặc giả mạo. Không dùng chúng như bằng chứng xác thực sender khi xử lý lệnh nghiệp vụ quan trọng; cần xác thực sender bằng chính sách phù hợp, có thể gồm kiểm tra nguồn inbox đáng tin, SPF/DKIM/DMARC do hạ tầng nhận cung cấp và xác minh nghiệp vụ.

### Đọc header chưa phải lúc nào cũng đọc body

Các thao tác lấy Subject, From hoặc flags thường ít tốn băng thông hơn lấy toàn bộ body/attachments. Tuy nhiên, điều đó phụ thuộc caching/fetching behavior của implementation và server. Không giả định một lần getSubject() luôn không phát sinh network call; Jakarta Mail có thể fetch dữ liệu lười.

### Đừng in nguyên header và body vào log

Email có thể chứa mã OTP, hóa đơn, token hoặc dữ liệu riêng tư. Với log, ưu tiên folder name, UID, outcome, thời gian xử lý và mã lỗi, không in toàn bộ body hoặc địa chỉ đầy đủ khi không cần thiết.

## 9. Flags: trạng thái gắn với Message

Jakarta Mail sử dụng **Flags** để đại diện trạng thái. Một số system flags thường gặp:

| Flag Jakarta Mail | IMAP flag tương ứng | Ý nghĩa thông dụng |
| --- | --- | --- |
| **Flags.Flag.SEEN** | \Seen | Message đã được đánh dấu là đã đọc |
| **Flags.Flag.ANSWERED** | \Answered | Đã trả lời |
| **Flags.Flag.FLAGGED** | \Flagged | Được đánh dấu quan trọng/star tùy client |
| **Flags.Flag.DELETED** | \Deleted | Được đánh dấu xóa; có thể chưa expunge |
| **Flags.Flag.DRAFT** | \Draft | Bản nháp |
| **Flags.Flag.RECENT** | \Recent | Trạng thái recent do server quản lý, không giống unread |
| **Flags.Flag.USER** | Cơ chế user-defined flags | Dùng/kiểm tra flags do provider hỗ trợ |

**SEEN** không phải cờ do Spring Mail tự định nghĩa; đây là một phần abstraction của Jakarta Mail và IMAP. Client có thể xem message là unread khi flag SEEN không hiện diện.

### Kiểm tra flag

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Message;

boolean read = message.isSet(Flags.Flag.SEEN);
boolean flagged = message.isSet(Flags.Flag.FLAGGED);
boolean deleted = message.isSet(Flags.Flag.DELETED);
~~~

Hoặc:

~~~java
Flags flags = message.getFlags();
boolean read = flags.contains(Flags.Flag.SEEN);
~~~

**Message.isSet(...)** và **getFlags()** có thể cần truy vấn server nếu dữ liệu chưa được cache. Với nhiều messages, nên sử dụng batching/fetch profile hoặc server-side SEARCH.

### Không nhầm RECENT với UNSEEN

**RECENT** không đơn giản nghĩa là “người dùng chưa đọc”. Nó là trạng thái liên quan server/session và không phải tất cả IMAP servers hiện đại cung cấp semantics giống nhau. Nếu mục tiêu là thư chưa đọc, kiểm tra **NOT SEEN**, không thay bằng RECENT.

### Custom flags không phải lúc nào cũng được hỗ trợ

Một số servers hỗ trợ keywords như tên label hoặc custom flags. Trước khi dựa vào custom flag, cần kiểm tra **folder.getPermanentFlags()** hoặc khả năng provider, và phân biệt flag được server lưu bền vững với flag tạm thời trong session.

## 10. Đánh dấu đã đọc bằng Flags.Flag.SEEN

Để thay đổi trạng thái read/unread trên IMAP, mở folder **READ_WRITE**, sau đó gọi **setFlag(...)**:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Store;

Store store = session.getStore("imaps");
Folder inbox = null;

try {
    store.connect(host, port, username, password);
    inbox = store.getFolder("INBOX");
    inbox.open(Folder.READ_WRITE);

    Message message = inbox.getMessage(1);
    message.setFlag(Flags.Flag.SEEN, true);
} finally {
    if (inbox != null && inbox.isOpen()) {
        inbox.close(false);
    }
    if (store.isConnected()) {
        store.close();
    }
}
~~~

**true** nghĩa là thêm flag SEEN; điều đó làm server/client hiển thị thư là đã đọc nếu provider hỗ trợ và thao tác thành công.

### Đánh dấu chưa đọc

~~~java
message.setFlag(Flags.Flag.SEEN, false);
~~~

**false** nghĩa là xóa flag SEEN, cho phép thư trở lại trạng thái chưa đọc. Thao tác này cũng là một phép ghi server-side; cần mở READ_WRITE và kiểm tra quyền mailbox.

### Đặt flag cho nhiều messages

Jakarta Mail cung cấp API folder-level để cập nhật flags cho tập messages:

~~~java
Message[] selected = inbox.getMessages(1, 10);
inbox.setFlags(
        selected,
        new Flags(Flags.Flag.SEEN),
        true
);
~~~

Ví dụ giả định folder có ít nhất 10 messages và được mở READ_WRITE. Không gọi range vượt số message trong folder; với mailbox biến động, tốt hơn là search ra mảng messages phù hợp rồi gọi **setFlags(...)**.

### Không đánh dấu SEEN khi chưa xử lý xong

Một worker đọc mail hỗ trợ khách hàng:

~~~text
1. Tìm thư UNSEEN
2. Đánh dấu SEEN ngay
3. Gọi API tạo support ticket
4. API thất bại
5. Poll lần sau chỉ tìm UNSEEN -> bỏ qua thư
~~~

Đây là lỗi nghiệp vụ. Nếu mailbox flags được dùng như chỉ dấu công việc đã xử lý, cần **đánh dấu sau khi lưu kết quả nghiệp vụ thành công**, và tốt hơn là dùng bảng trạng thái riêng chống trùng. SEEN chỉ là tín hiệu mailbox, không phải transaction liên kết với database nghiệp vụ.

## 11. Đọc message body có thể tự đánh dấu SEEN

Đây là một trong những chi tiết dễ bị bỏ sót nhất khi xây ứng dụng đọc email: một số IMAP implementations/server đánh dấu thư **\Seen** khi client fetch nội dung body theo cách thông thường.

Ví dụ:

~~~java
Object content = message.getContent();
~~~

Với IMAP, việc thực hiện thao tác đọc body có thể khiến flag SEEN được thêm, tùy provider và thuộc tính fetch/peek. Tương tự, truy cập stream nội dung có thể làm thay đổi trạng thái. Vì vậy một ứng dụng chỉ định “xem trước thư chưa đọc” nhưng gọi getContent() có thể khiến thư biến thành đã đọc trước khi xử lý nghiệp vụ.

### Thiết lập peek khi cần đọc mà không thay đổi SEEN

Trong Jakarta Mail IMAP implementations hỗ trợ thuộc tính:

~~~java
Properties props = new Properties();
props.put("mail.store.protocol", "imaps");
props.put("mail.imaps.peek", "true");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");
~~~

**mail.imaps.peek=true** yêu cầu implementation IMAP đọc nội dung bằng cơ chế peek để tránh tự thêm \Seen khi fetch body. Phải xác minh thuộc tính này được hỗ trợ trong phiên bản Jakarta Mail/Angus Mail dùng thực tế và kiểm thử tương tác với server. Với protocol **imap** thay vì **imaps**, tiền tố thường là **mail.imap.peek**.

### Peek không thay thế READ_ONLY

Nếu chỉ cần quan sát, mở **Folder.READ_ONLY** thường phù hợp. Nếu cần xử lý và cuối cùng đánh dấu đã đọc, có thể mở READ_WRITE nhưng dùng peek để tránh thay đổi cờ ngoài thời điểm đã chọn:

~~~text
READ_WRITE Folder + peek
       |
       v
Fetch body -> parse / persist business result
       |
       v
Commit business transaction
       |
       v
Set SEEN explicitly
~~~

Ngay cả khi có peek, phải kiểm tra với server thực tế, nhất là khi thư có multipart/attachments hoặc dùng thao tác copy/move. **Không giả định mọi API đều giữ flags không đổi trong mọi provider**.

### Nếu đọc làm thư thành SEEN ngoài ý muốn?

Không nên chữa bằng cách luôn gọi **setFlag(SEEN, false)** sau khi đọc. Nếu một client khác đã chủ động đánh dấu thư là đã đọc trong lúc worker chạy, việc xóa cờ có thể ghi đè lựa chọn của người dùng. Thay vào đó, cấu hình fetch/peek đúng ngay từ đầu và tách process state khỏi mailbox read state.

## 12. Tìm thư chưa đọc bằng FlagTerm

Jakarta Mail cung cấp **SearchTerm**, trong đó **FlagTerm** giúp tìm các message theo flags.

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Message;
import jakarta.mail.search.FlagTerm;

Message[] unread = inbox.search(
        new FlagTerm(
                new Flags(Flags.Flag.SEEN),
                false
        )
);
~~~

Trong **FlagTerm(flags, false)**, tham số **false** biểu thị tìm các message **không có các flags được chỉ định**. Với một flag SEEN, kết quả thường là messages chưa đọc.

### Kết hợp nhiều điều kiện

Ví dụ chỉ chọn thư chưa đọc và có subject chứa một cụm:

~~~java
import jakarta.mail.search.AndTerm;
import jakarta.mail.search.FlagTerm;
import jakarta.mail.search.SearchTerm;
import jakarta.mail.search.SubjectTerm;

SearchTerm unseen = new FlagTerm(
        new Flags(Flags.Flag.SEEN),
        false
);

SearchTerm matchingSubject = new SubjectTerm(
        "Support"
);

Message[] candidates = inbox.search(
        new AndTerm(unseen, matchingSubject)
);
~~~

Tìm theo subject chỉ là một bộ lọc tiện lợi. Subject do bên gửi kiểm soát, không nên xem nó là bằng chứng xác thực yêu cầu thanh toán, hoàn tiền hoặc thao tác quyền tài khoản.

### Server-side search vẫn cần xác minh điều kiện trước xử lý

Tùy protocol/provider, một số SearchTerm có thể được thực thi trên server hoặc một phần trên client. Kết quả được trả về tại một thời điểm, nhưng mailbox có thể thay đổi ngay sau đó. Một message được trả về là UNSEEN có thể đã được client khác đánh dấu SEEN khi worker chuẩn bị đọc.

Với workflow nhiều worker, không coi kết quả search là **khóa độc quyền**. Cần cơ chế claim/dedup nghiệp vụ nếu mục tiêu là mỗi thư chỉ được xử lý một lần.

### Đừng tìm bằng cách fetch body của toàn mailbox

Với inbox có 100.000 thư, duyệt tất cả getContent() rồi kiểm tra cờ vừa tốn network vừa có thể làm thay đổi trạng thái đọc. Ưu tiên **SEARCH UNSEEN** hoặc tìm theo UID/time windows, batch metadata và chỉ tải body của candidates cần thiết.

## 13. Cờ SEEN có thể được thay đổi bởi nhiều clients

Một hộp thư hỗ trợ có thể đồng thời được mở trên:

- Giao diện webmail của nhân viên.
- Ứng dụng di động.
- Worker Spring dùng IMAP.
- Một service tự động khác.

Các clients này cùng đọc/ghi trạng thái trên server. Ví dụ:

~~~text
10:00 Worker tìm được Message M: UNSEEN
10:01 Nhân viên mở M trong webmail -> SEEN
10:02 Worker xử lý M
10:03 Worker setFlag(SEEN, true)
~~~

Trong ví dụ, không có vấn đề lớn về trạng thái cuối, nhưng nếu quy trình dùng “UNSEEN nghĩa là chưa xử lý”, worker có thể hiểu sai hành động của nhân viên. Ngược lại, nếu nhân viên đánh dấu M UNSEEN để nhắc xử lý lại, worker có thể chạy lặp tác vụ.

### SEEN không phải job-lock

Không có bảo đảm rằng hai workers gọi **search(UNSEEN)** đồng thời sẽ nhận hai tập khác nhau:

~~~text
Worker A: SEARCH UNSEEN -> M
Worker B: SEARCH UNSEEN -> M
Worker A: xử lý M
Worker B: xử lý M
~~~

Đánh dấu SEEN không phải cơ chế atomic claim/lease được thiết kế riêng cho job. Nếu cần tránh xử lý trùng, dùng một **idempotency key** từ mailbox identity + UIDVALIDITY + UID (hoặc định danh bền vững phù hợp server), bảng processed-message và atomic claim/unique constraint ở database.

### Phân biệt trải nghiệm người dùng với tiến độ hệ thống

**SEEN** thuộc trạng thái hộp thư mà người dùng nhìn thấy; trạng thái **PROCESSED** thuộc workflow nghiệp vụ của hệ thống. Một thư có thể:

| SEEN | PROCESSED | Ý nghĩa |
| --- | --- | --- |
| false | false | Chưa ai mở, chưa worker xử lý |
| true | false | Đã đọc nhưng chưa xử lý nghiệp vụ |
| false | true | Đã xử lý nhưng giữ unread theo preference |
| true | true | Đã đọc và đã xử lý |

Không gộp hai chiều này thành một boolean trừ khi nghiệp vụ chấp nhận các giới hạn của sự đồng bộ.

## 14. UID và UIDVALIDITY: định danh ổn định hơn message number

Khi làm việc với IMAP, message sequence number có thể thay đổi sau expunge. Để biết một thư đã được xử lý trong những lần poll trước, giao thức hỗ trợ **UID** (Unique Identifier) của message trong một mailbox.

Nhưng **UID không có nghĩa duy nhất toàn hệ thống**:

- UID gắn với một folder/mailbox cụ thể.
- UID có tính duy nhất trong phạm vi mailbox cùng **UIDVALIDITY**.
- Nếu mailbox được tạo lại/đổi trạng thái khiến UIDVALIDITY đổi, các UID cũ không còn cùng ý nghĩa.
- Một message được copy sang folder khác có thể nhận UID khác.
- UID không thay thế bằng chứng xác thực email sender.

Một định danh logical hữu ích:

~~~text
Account identity
    +
Folder identity
    +
UIDVALIDITY
    +
UID
    =
Source message key
~~~

Trong hệ thống nhiều tenants/mail accounts, hãy dùng một định danh mailbox **do ứng dụng quản lý** (không phải mỗi địa chỉ From) để tránh hai accounts có cùng folder name và UID.

### Sử dụng UIDFolder

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

Folder inbox = store.getFolder("INBOX");
inbox.open(Folder.READ_ONLY);

if (!(inbox instanceof UIDFolder uidFolder)) {
    throw new IllegalStateException(
            "Store không hỗ trợ UIDFolder"
    );
}

long validity = uidFolder.getUIDValidity();
Message candidate = inbox.getMessage(1);
long uid = uidFolder.getUID(candidate);

System.out.println("UIDVALIDITY=" + validity);
System.out.println("UID=" + uid);
~~~

Ví dụ giả định folder có ít nhất một message. **UIDFolder** là interface Jakarta Mail, nhưng không phải mọi provider/folder đều hỗ trợ; cần kiểm tra runtime type. UID có thể có giá trị đặc biệt nếu provider không hỗ trợ định danh cho một Message cụ thể; code production nên kiểm tra hợp đồng của implementation.

### Tìm lại message theo UID

~~~java
Message found = uidFolder.getMessageByUID(savedUid);
if (found == null) {
    // Message có thể đã bị xóa/move hoặc UID không còn tồn tại.
}
~~~

Hàm này phải được gọi trên folder có UIDVALIDITY tương ứng với record trước đó. Nếu UIDVALIDITY đã đổi, **không dùng savedUid một mình** để quyết định thư đã hoặc chưa xử lý.

### Vì sao không dùng Message-ID header thay UID?

Email có thể thiếu Message-ID, dùng Message-ID trùng hoặc bị sender cố tình đặt cùng giá trị cho nhiều thư. Ngoài ra, một thư được chuyển tiếp/copy có thể tạo quan hệ Message-ID khác với bản ghi mailbox. Message-ID hữu ích cho threading/correlation, nhưng **không phải khóa đáng tin cho exactly-once xử lý inbox**.

### UID và thư đã chuyển folder

Nếu ứng dụng xử lý thư ở INBOX rồi chuyển vào Processed folder, UID trong Processed thường khác UID của bản INBOX. Database cần lưu source identity cùng trạng thái processing, và nếu cần biết UID đích thì phải theo dõi thao tác copy/move theo khả năng provider. Không giả định một UID được giữ nguyên ở mọi folder.

## 15. Lấy thư theo UID hoặc theo batch

Trong xử lý theo chu kỳ, thường không cần đọc lại toàn bộ mailbox từ đầu. Có thể lưu **UIDVALIDITY + last observed UID**, sau đó tìm UID mới hơn một mốc đã ghi.

Mẫu truy cập:

~~~java
long lastUid = checkpoint.lastUid();
long currentValidity = uidFolder.getUIDValidity();

if (currentValidity != checkpoint.uidValidity()) {
    // Mailbox identity epoch thay đổi.
    // Không tiếp tục incremental scan bằng UID cũ.
    throw new MailboxCheckpointChangedException();
}

Message[] newer = uidFolder.getMessagesByUID(
        lastUid + 1,
        UIDFolder.LASTUID
);
~~~

**MailboxCheckpointChangedException** và **checkpoint** là thành phần do ứng dụng định nghĩa. **UIDFolder.LASTUID** là hằng được API dùng để đại diện cận trên cuối cùng trong một số thao tác UID.

### Chú ý xử lý khoảng trống UID

UID không bắt buộc liên tiếp. Ví dụ server có các UID 101, 104 và 108 là điều bình thường. Không cần giả định mọi số từ 101 đến 108 phải có message tương ứng.

### Checkpoint không nên đi trước commit nghiệp vụ

Một worker dễ mắc lỗi:

~~~text
1. Tìm UID 104, 108.
2. Ghi checkpoint=108.
3. Xử lý UID 104 -> thành công.
4. Xử lý UID 108 -> thất bại.
5. Lần sau quét từ UID >108 -> bỏ sót UID 108.
~~~

Để tránh bỏ sót:

- Lưu kết quả xử lý từng UID bằng **unique key**.
- Chỉ advance checkpoint cho vùng UID đã xử lý/được ghi nhận an toàn.
- Cho phép scan overlap rồi deduplicate.
- Có retry riêng cho UID xử lý lỗi.
- Khi UIDVALIDITY đổi, chuyển sang full/incremental resynchronization có policy.

### Checkpoint chỉ là tối ưu hóa

Ngay cả khi ứng dụng lưu last UID, email cũ vẫn có thể được gắn lại flag UNSEEN hoặc được chuyển vào folder từ client khác. Nếu yêu cầu xử lý “mọi thư mới đến”, UID checkpoint phù hợp; nếu yêu cầu “mọi thư đang unread”, cần tìm theo SEEN hoặc kết hợp state. Hai bài toán không hoàn toàn giống nhau.

### Đọc theo batch thay vì toàn mailbox

Khi folder có rất nhiều messages:

1. Dùng SEARCH/UID để chọn candidates.
2. Giới hạn batch và concurrency.
3. Prefetch metadata cần thiết.
4. Tải body của từng candidate có kiểm soát.
5. Persist kết quả và checkpoint đúng ranh giới transaction.
6. Đóng folder/Store hoặc tái sử dụng connection theo lifecycle đã thiết kế.

Không tạo một mảng hàng trăm nghìn Message rồi gọi getContent song song không giới hạn: có thể làm đầy heap, socket pool, và khiến server giới hạn truy cập.

## 16. Dùng FetchProfile để lấy metadata hiệu quả

Jakarta Mail có **FetchProfile** hỗ trợ yêu cầu prefetch một số thông tin cho nhiều messages thay vì gọi từng thuộc tính qua nhiều network round trips.

~~~java
import jakarta.mail.FetchProfile;
import jakarta.mail.Message;

Message[] candidates = inbox.search(
        new FlagTerm(
                new Flags(Flags.Flag.SEEN),
                false
        )
);

FetchProfile profile = new FetchProfile();
profile.add(FetchProfile.Item.ENVELOPE);
profile.add(FetchProfile.Item.FLAGS);

inbox.fetch(candidates, profile);

for (Message m : candidates) {
    System.out.println(m.getSubject());
    System.out.println(m.isSet(Flags.Flag.SEEN));
}
~~~

Ví dụ giả định các imports cho **Flags** và **FlagTerm** đã được thêm tương ứng. **ENVELOPE** hỗ trợ các thông tin header thường dùng, **FLAGS** hỗ trợ flags; khả năng tối ưu cụ thể tùy provider. Prefetch không có nghĩa đã tải toàn bộ attachment.

### FetchProfile khác getContent

Thao tác fetch metadata không nên bị nhầm với việc tải toàn bộ body. Đối với mailbox dùng làm queue, hãy ưu tiên metadata trước để kiểm tra:

- UID/UIDVALIDITY.
- Subject/sender/time nếu cần routing.
- Flags và các điều kiện nhanh.
- Kích thước hoặc MIME structure khi provider hỗ trợ.

Sau khi quyết định xử lý, mới tải body và attachments. Điều này giảm chi phí và hạn chế tác dụng phụ không mong muốn lên SEEN.

### Batching không biến IMAP thành transaction database

Ngay cả khi inbox.fetch(candidates, profile) trả về thành công, một client khác vẫn có thể xóa, di chuyển hoặc đổi flags. Không dùng một batch fetch như snapshot isolation mạnh của database; code phải xử lý **MessageRemovedException**, FolderClosedException và kết quả không còn hợp lệ.

## 17. Phân biệt đọc header, text/plain và multipart

Message body có thể là:

- **text/plain** — văn bản thuần.
- **text/html** — nội dung HTML.
- **multipart/alternative** — các lựa chọn biểu diễn (plain/HTML).
- **multipart/mixed** — text cùng attachment.
- **multipart/related** — HTML và các nội dung liên kết như ảnh inline.
- **message/rfc822** — một email khác được đính kèm.

Đoạn code đơn giản:

~~~java
if (message.isMimeType("text/plain")) {
    String text = (String) message.getContent();
    // Xử lý text sau khi giới hạn dung lượng.
}
~~~

Chỉ đúng khi phần gốc của message là text/plain; nhiều email thực tế là multipart. Không dùng:

~~~java
String body = (String) message.getContent();
~~~

cho mọi message, vì getContent() có thể trả về **Multipart**, **InputStream** hoặc kiểu khác.

### Ví dụ duyệt multipart ở mức minh họa

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public static void visitParts(Part part, int depth)
        throws Exception {
    if (depth > 8) {
        throw new IllegalArgumentException(
                "MIME nesting too deep"
        );
    }

    if (part.isMimeType("text/plain")) {
        Object content = part.getContent();
        if (content instanceof String text) {
            System.out.println(
                    "Text length: " + text.length()
            );
        }
    } else if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();
        for (int index = 0;
             index < multipart.getCount();
             index++) {
            BodyPart child = multipart.getBodyPart(index);
            visitParts(child, depth + 1);
        }
    } else {
        System.out.println(
                "Part type: " + part.getContentType()
        );
    }
}
~~~

Ví dụ trên minh họa cấu trúc MIME; không phải parser đầy đủ cho production. Trên thực tế còn cần:

- Giới hạn kích thước message và mỗi part.
- Giới hạn số parts và độ sâu lồng nhau.
- Tránh tải toàn bộ attachment vào RAM.
- Xử lý charset bất thường và malformed MIME.
- Kiểm tra malware/security policy với attachments.
- Không hiển thị HTML chưa được sanitize vào trình duyệt nội bộ.
- Bảo vệ khỏi zip bombs, nội dung quá lớn hoặc URL ảnh bên ngoài gây tracking.

**Đặc biệt:** việc gọi **part.getContent()** trong các ví dụ có thể kéo body về và ảnh hưởng SEEN tùy IMAP implementation. Muốn giữ unread cho đến sau khi xử lý, phải dùng READ_ONLY hoặc peek/fetch behavior đã được kiểm chứng với provider.

## 18. Luồng đọc và đánh dấu SEEN đúng thứ tự

Một service nhận mail dùng để tạo ticket có thể tổ chức như sau:

~~~text
Poll inbox
    |
    v
Find candidates via IMAP search/UID
    |
    v
Read metadata and UIDVALIDITY
    |
    v
Try atomic claim by application message key
    |
    +-- Already processed/in progress -> Skip
    |
    '-- Claim succeeded
            |
            v
        Fetch body using peek policy
            |
            v
        Validate, parse, store attachment safely
            |
            v
        Persist business result in DB transaction
            |
            v
        Mark application record PROCESSED
            |
            v
        Optionally set SEEN via IMAP
            |
            v
        Record flag-sync status/result
~~~

### Vì sao set SEEN sau DB commit?

Nếu đánh dấu SEEN trước khi transaction tạo ticket được commit, khi transaction rollback email sẽ biến thành đã đọc mà không có ticket tương ứng. Nếu set SEEN sau DB commit thất bại, một lần poll sau vẫn có thể thấy thư UNSEEN; bảng processed-message và dedup key ngăn tạo ticket thứ hai.

**Đây là at-least-once + idempotent processing**, không phải transaction atomic bao gồm IMAP và database. Hai hệ thống không tham gia một transaction chung khi chỉ dùng Jakarta Mail và JDBC.

### Nếu người dùng muốn thư vẫn unread?

Một ứng dụng theo dõi support queue có thể không muốn thay đổi trạng thái hộp thư do người dùng quản lý. Khi đó chỉ ghi **PROCESSED** ở database và không đụng SEEN. Không có yêu cầu bắt buộc mọi thư do automation xử lý đều phải được đánh dấu đã đọc.

### Có cần đánh dấu Flagged hoặc chuyển folder?

Một số workflow dùng **FLAGGED** hoặc chuyển thư sang **Processed** folder thay vì SEEN. Điều này có thể hữu ích cho trải nghiệm support, nhưng vẫn cần trạng thái nội bộ bền vững và xử lý move/copy riêng. Không dùng SEEN như cơ chế duy nhất để bảo đảm message được xử lý đúng một lần.

## 19. Thiết kế bảng trạng thái xử lý thư riêng với SEEN

Nếu inbox là nguồn dữ liệu của một quy trình tự động, nên lưu idempotency state trong database. Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE inbound_mail_processing (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    mailbox_id VARCHAR(120) NOT NULL,
    folder_name VARCHAR(500) NOT NULL,
    uid_validity BIGINT NOT NULL,
    message_uid BIGINT NOT NULL,
    status VARCHAR(40) NOT NULL,
    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    received_at TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    flag_sync_status VARCHAR(40),
    last_error_category VARCHAR(80),
    CONSTRAINT uq_inbound_mail_source
        UNIQUE (
            tenant_id,
            mailbox_id,
            folder_name,
            uid_validity,
            message_uid
        )
);
~~~

Đây là bảng do ứng dụng thiết kế, không có sẵn trong Spring Framework Mail hay Jakarta Mail. Một số trạng thái có thể là:

| Status | Ý nghĩa | Hành động |
| --- | --- | --- |
| **DISCOVERED** | UID đã được phát hiện | Chờ claim |
| **PROCESSING** | Worker đang xử lý | Có lease và heartbeat khi cần |
| **PROCESSED** | Kết quả nghiệp vụ đã persist | Không lặp tác vụ, có thể đồng bộ SEEN |
| **RETRY_WAIT** | Lỗi tạm thời | Retry giới hạn |
| **PERMANENT_FAILED** | Dữ liệu không xử lý được | Review hoặc quarantine |
| **NEEDS_REVIEW** | Kết quả nghiệp vụ không rõ | Không tự retry side effect mơ hồ |

**flag_sync_status** là một chiều riêng, chẳng hạn **NOT_REQUESTED**, **PENDING**, **SYNCED**, **FAILED**, để tracking thao tác đánh dấu SEEN sau khi đã xử lý nghiệp vụ.

### Tại sao cần unique constraint?

Hai workers có thể cùng tìm UID 108. Nếu cả hai cùng cố tạo bản ghi nguồn:

~~~text
Worker A INSERT mailbox + UIDVALIDITY + UID
Worker B INSERT mailbox + UIDVALIDITY + UID
~~~

Constraint giúp không tạo hai record nguồn. Tuy nhiên, **unique insert một lần chưa đủ** nếu hai worker đều có thể claim một record đã tồn tại: còn cần atomic claim/lease hoặc row-level locking khi thực hiện business side effect.

### Bản ghi processed không thay thế việc xử lý UIDVALIDITY thay đổi

Nếu UIDVALIDITY của INBOX đổi, cùng UID số 108 có thể đại diện một message khác. Vì vậy **uid_validity** nằm trong khóa unique. Một mailbox reset/restore có thể cần rescan; không dựa vào UID cũ trong epoch mới.

### Không cần lưu nguyên MIME trong bảng theo dõi

Chỉ dùng metadata: mailbox, folder, UID, trạng thái, timestamps, error category. Nội dung email và attachment có thể chứa thông tin nhạy cảm, cần lưu tại nơi được cấp quyền phù hợp, mã hóa và retention theo mục đích nghiệp vụ. Không lưu raw body hoặc access token vào error logs chỉ để tiện debug.

## 20. Claim công việc nhận mail bằng database

Một worker an toàn thường chia hai pha:

1. Poll IMAP để khám phá UID và ghi nhận vào bảng processing.
2. Worker claim các bản ghi DISCOVERED/RETRY_WAIT trong database để xử lý.

Nếu có nhiều workers, claim cần atomic:

~~~sql
WITH next_mail AS (
    SELECT id
    FROM inbound_mail_processing
    WHERE status IN ('DISCOVERED', 'RETRY_WAIT')
      AND (lease_until IS NULL OR lease_until <= CURRENT_TIMESTAMP)
    ORDER BY first_seen_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE inbound_mail_processing AS p
SET
    status = 'PROCESSING',
    lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = p.attempt_count + 1
FROM next_mail
WHERE p.id = next_mail.id
RETURNING
    p.id,
    p.mailbox_id,
    p.folder_name,
    p.uid_validity,
    p.message_uid;
~~~

Câu SQL là minh họa PostgreSQL, không phải API mặc định của Spring Mail. Trong production có thể cần thêm **lease_token/version** để worker đã mất lease không ghi đè kết quả của worker mới. Worker không giữ database row lock trong khi chờ IMAP hoặc gọi API tạo ticket.

### Một vấn đề khó: worker chết sau business side effect

~~~text
T1: Worker đọc Message UID 108
T2: Worker tạo ticket qua một API ngoài
T3: API tạo ticket thành công
T4: Worker chết trước khi mark PROCESSED
T5: Job bị claim lại
~~~

Nếu API tạo ticket không có idempotency key, job bị chạy lại có thể tạo hai tickets. **SEEN không giải quyết được trường hợp này.**

Giải pháp cần ở tầng nghiệp vụ:

- Tạo ticket cùng database transaction với trạng thái processed nếu có thể.
- Hoặc dùng idempotency key của API đích và gửi cùng khóa ở mọi retry.
- Hoặc lưu external request/outcome và làm reconciliation khi không biết side effect đã xảy ra chưa.

Một khóa ví dụ:

~~~text
INBOUND_MAIL:
  tenant-7:
  support-mailbox-1:
  INBOX:
  uidValidity=9192:
  uid=108
~~~

Không dùng **message number**, vốn có thể thay đổi khi expunge.

## 21. Service đọc một UID và đánh dấu SEEN sau commit

Một abstraction đơn giản cho ứng dụng:

~~~java
public record InboundMailKey(
        String mailboxId,
        String folderName,
        long uidValidity,
        long uid
) {
}

public record ReceivedMailData(
        InboundMailKey key,
        String from,
        String subject,
        String plainText
) {
}

public interface InboundMailRepository {
    boolean tryClaim(InboundMailKey key);

    void markProcessed(InboundMailKey key, String businessRecordId);

    void markRetryable(InboundMailKey key, String reason);

    boolean isProcessed(InboundMailKey key);
}

public interface TicketCreationService {
    String createTicketIdempotently(ReceivedMailData mail);
}
~~~

Đây là các interface minh họa do ứng dụng định nghĩa. **tryClaim** cần atomic ở database và phải phân biệt record đang xử lý, đã xử lý và có thể retry. **createTicketIdempotently** phải thực sự dùng định danh mail làm idempotency key hoặc có cơ chế giao dịch phù hợp, không chỉ được đặt một cái tên “idempotent”.

### Tách mailbox I/O khỏi transaction nghiệp vụ

Một tổ chức code:

~~~text
open IMAP folder -> get UID -> fetch content
                  |
                  v
        validate and parse message
                  |
                  v
       database transaction / business service
                  |
                  v
             commit success
                  |
                  v
     IMAP setFlag(SEEN, true) if policy requires
~~~

Không nên mở một **@Transactional** database transaction rồi giữ nó xuyên suốt quá trình kết nối IMAP, đọc attachments và gọi API ngoài; điều đó giữ connection/lock lâu và làm tăng nguy cơ contention.

### Ví dụ xử lý SEEN dựa trên UID

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

public static boolean markReadByUid(
        Folder folder,
        long expectedValidity,
        long uid
) throws Exception {
    if (!folder.isOpen()
            || folder.getMode() != Folder.READ_WRITE) {
        throw new IllegalStateException(
                "Folder phải đang mở READ_WRITE"
        );
    }

    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "Folder không hỗ trợ UID"
        );
    }

    if (uidFolder.getUIDValidity() != expectedValidity) {
        return false; // Không đánh dấu nhầm epoch UID.
    }

    Message message = uidFolder.getMessageByUID(uid);
    if (message == null) {
        return false; // Message đã move/delete.
    }

    message.setFlag(Flags.Flag.SEEN, true);
    return true;
}
~~~

**markReadByUid(...)** chỉ xác nhận lời gọi setFlag thành công, không có nghĩa business record đã commit; hãy gọi nó **sau** khi nghiệp vụ được xử lý an toàn. Tùy yêu cầu, có thể đọc lại **isSet(SEEN)** hoặc thực hiện một lần đồng bộ sau để quan sát server state, vì session/network có thể thay đổi.

### Nếu setFlag thất bại thì sao?

Ứng dụng có thể ghi:

~~~text
Business state: PROCESSED
Flag sync:      FAILED
Error category: FOLDER_READ_ONLY / NETWORK / MESSAGE_REMOVED
~~~

Một worker chuyên đồng bộ flags có thể thử lại theo UIDVALIDITY + UID. Không chạy lại việc tạo ticket chỉ vì cờ SEEN chưa được set thành công.

## 22. Phân biệt flags tự động và flags do business logic set

Khi một IMAP client tải nội dung, server có thể set \Seen. Khi app gọi **setFlag(SEEN, true)**, đó là một yêu cầu ghi trực tiếp. Hai cơ chế có thể cùng ảnh hưởng trạng thái:

~~~text
Message ban đầu: UNSEEN
       |
       +-- FETCH BODY (không peek) -> có thể thành SEEN
       |
       '-- Business processed -> setFlag(SEEN, true) -> SEEN
~~~

Do đó phải xác định rõ **thời điểm mong muốn** thư thành đã đọc:

| Kịch bản | Cách tổ chức phù hợp |
| --- | --- |
| Ứng dụng chỉ hiển thị danh sách | READ_ONLY hoặc metadata fetch, không tự thay SEEN |
| Xem trước body nhưng giữ unread | READ_ONLY hoặc PEEK có test xác minh |
| Người dùng bấm “Mark as read” | READ_WRITE + setFlag(SEEN, true) |
| Người dùng bấm “Mark as unread” | READ_WRITE + setFlag(SEEN, false) |
| Bot tạo ticket từ email | Tách processed state, tùy policy đồng bộ SEEN sau commit |
| Di chuyển email sau xử lý | Phải quản lý UID/folder destination và xử lý copy/move riêng |

Một thiết kế webmail có thể đánh dấu read khi **người dùng mở thư**, trong khi một bot triage chỉ đọc metadata và không đụng SEEN. Đây là quyết định sản phẩm, không phải JavaMail API bắt buộc.

## 23. READ_ONLY, READ_WRITE và quyền thay đổi SEEN

Một folder có thể được mở:

~~~java
folder.open(Folder.READ_ONLY);
~~~

Ở mode này, ứng dụng không được giả định có thể set flags. Khi muốn set SEEN, cần dùng READ_WRITE:

~~~java
folder.open(Folder.READ_WRITE);
~~~

Nếu folder đã open READ_ONLY, không gọi open lần thứ hai trên cùng folder mà không close theo lifecycle; đóng rồi mở lại ở mode phù hợp hoặc tạo một flow khác có quyền ghi.

### Vì sao nên tách read-only worker và flag-sync worker?

Trong hệ thống nhiều consumer:

~~~text
Mailbox Poller (READ_ONLY/peek)
          |
          v
Discover UID -> DB job
          |
          v
Business Worker -> persist result
          |
          v
Flag Sync Worker (READ_WRITE)
          |
          v
Set SEEN / FLAGGED / move if policy
~~~

Lợi ích:

- Poller không vô tình làm thay đổi unread count.
- Không giữ một folder WRITE mở trong các transaction nghiệp vụ dài.
- Retry flag-sync không chạy lại business side effect.
- Có thể phân quyền mailbox access theo chức năng.

Nhược điểm là thêm nhiều bước và trạng thái eventual consistency, nên chỉ cần khi sản phẩm thực sự cần xử lý độc lập và có rủi ro xử lý trùng.

### Có phải close(false) khôi phục SEEN không?

**Không.** Trong IMAP, set SEEN thường là thao tác server-side. **close(false)** chỉ tránh yêu cầu expunge messages đánh dấu DELETED khi đóng, không rollback các thay đổi flags đã thực hiện.

## 24. Đánh dấu nhiều thư và tránh race với người dùng

Giả sử UI có nút **Mark selected as read**. Nhiều thư được chọn phải được xác định bằng UID thay vì message numbers kéo dài qua nhiều request.

Mô hình request:

~~~text
POST /mailboxes/{mailboxId}/folders/{folderId}/mark-read
{
  "uidValidity": 19220,
  "uids": [104, 108, 110]
}
~~~

Ứng dụng cần:

1. Authorization cho mailbox/folder.
2. Giới hạn số UID trong request.
3. Mở folder READ_WRITE.
4. Kiểm tra UIDVALIDITY.
5. Resolve từng UID thành Message còn tồn tại.
6. Set flags trên các Message có quyền.
7. Ghi kết quả cho những UID được đổi và những UID đã bị move/delete.

Không cho client tự truyền hostname/credentials IMAP hoặc tên folder tùy ý nếu API chỉ nên thao tác các mailbox đã được gán cho họ. Mailbox identity và folder scope phải do server kiểm soát.

### Bulk setFlags qua Folder

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Message;

Message[] messages = ...; // Resolve từ các UID hợp lệ.

if (messages.length > 0) {
    folder.setFlags(
            messages,
            new Flags(Flags.Flag.SEEN),
            true
    );
}
~~~

Không dùng mảng chứa null khi UID không còn tồn tại. Phần resolve cần lọc và giới hạn, đặc biệt trên mailbox có nhiều client đồng thời.

### Race giữa Mark Read và Mark Unread

~~~text
T1 Client A: Mark as read
T2 Client B: Mark as unread
T3 Server áp dụng thao tác cuối
~~~

Không có bảo đảm client A hay B “thắng” nếu thao tác đồng thời mà app không có conflict policy. Nếu sản phẩm cần trạng thái đọc riêng từng người dùng, **IMAP \Seen trên shared mailbox không đủ**: cần bảng **user_message_read_state** ở application theo user ID, thay vì dùng một flag shared cho tất cả.

## 25. Shared mailbox: SEEN là trạng thái chung hay riêng người?

Một support mailbox dùng chung cho 20 nhân viên có thể hiển thị SEEN sau khi một nhân viên đọc. Điều đó không tương đương “20 nhân viên đều đã đọc”.

### Hai mô hình trải nghiệm

**Mô hình A — Shared \Seen**:

~~~text
support@example.test / INBOX
Message M: SEEN
~~~

Mọi client kết nối cùng mailbox có thể quan sát trạng thái chung (tùy server/provider). Phù hợp nếu nhóm muốn xem thư đã được ai đó mở, nhưng không đáp ứng yêu cầu per-user.

**Mô hình B — Read state per user ở application**:

~~~text
Message M:
  Alice -> READ
  Bob   -> UNREAD
  Cara  -> READ
~~~

Để hỗ trợ mô hình B, cần một bảng ví dụ:

~~~sql
CREATE TABLE user_mail_read_state (
    user_id VARCHAR(120) NOT NULL,
    mailbox_id VARCHAR(120) NOT NULL,
    folder_name VARCHAR(500) NOT NULL,
    uid_validity BIGINT NOT NULL,
    message_uid BIGINT NOT NULL,
    read_at TIMESTAMPTZ,
    PRIMARY KEY (
        user_id,
        mailbox_id,
        folder_name,
        uid_validity,
        message_uid
    )
);
~~~

Khi đó trạng thái đọc trong app không hoàn toàn đồng bộ với \Seen trên IMAP. Đây có thể là hành vi chủ đích. Phải mô tả rõ trên UI để tránh nhân viên hiểu nhầm.

### Shared mailbox còn có phân công xử lý

**READ/UNREAD** không nên thay cho trạng thái **ASSIGNED, IN_PROGRESS, RESOLVED** của một ticket. Một thư đã đọc nhưng chưa trả lời không được coi là xử lý xong; trạng thái ticket cần được quản lý ở nghiệp vụ riêng.

## 26. Xóa, copy và chuyển folder khác với đánh dấu đã đọc

Các flags có mục đích khác nhau. **SEEN** chỉ ghi nhận trạng thái đã đọc, còn **DELETED** thường là tín hiệu xóa trên IMAP, và thao tác move/copy làm thay đổi vị trí message.

### Đánh dấu DELETED không nhất thiết xóa ngay

~~~java
message.setFlag(Flags.Flag.DELETED, true);
~~~

Message có thể vẫn nằm trong folder và vẫn thấy được cho đến khi server thực hiện **expunge**, tùy chính sách server/client. Đừng dùng DELETED thay cho SEEN.

### close(true) có thể gây mất messages

~~~java
folder.close(true);
~~~

Tham số true yêu cầu expunge những messages đã được đánh dấu DELETED trong folder. Nó không chỉ “đóng sạch connection”; trong một shared mailbox, thao tác này có thể ảnh hưởng cả các messages do client khác đánh dấu DELETED.

Với worker chỉ đánh dấu đọc:

~~~java
folder.close(false);
~~~

và không thực hiện expunge ngoài ý định. Nếu muốn thực sự xóa/move, cần một workflow được phê duyệt, có quyền thích hợp, ghi audit, và test tác động server-specific.

### Copy messages

Jakarta Mail có API **Folder.copyMessages(...)**:

~~~java
Folder destination = store.getFolder("Processed");
if (!destination.exists()) {
    throw new IllegalStateException(
            "Folder đích không tồn tại"
    );
}

inbox.copyMessages(
        new Message[] {message},
        destination
);
~~~

Ví dụ giả định source/destination phù hợp và server hỗ trợ copy. Copy **không tự xóa bản gốc**; thư có thể xuất hiện ở hai folders và có UID khác nhau. Nếu xây “move” bằng copy rồi set DELETED/expunge, cần thừa nhận failure windows: copy thành công nhưng xóa bản cũ thất bại có thể tạo hai bản; xóa quá sớm có thể mất dữ liệu.

### Move extension không phải lúc nào cũng portable

Một số IMAP providers hỗ trợ MOVE extension hoặc API đặc thù. Jakarta Mail Folder core không bảo đảm một thao tác move atomic chung cho mọi backend. Nếu dùng implementation-specific IMAP move API, cần kiểm tra phiên bản và capabilities, đồng thời có fallback phù hợp.

### Khi chuyển thư, dữ liệu UID thay đổi

~~~text
INBOX:
  UIDVALIDITY 100, UID 25
        |
        v
COPY/MOVE
        |
        v
Processed:
  UIDVALIDITY 180, UID 999
~~~

Nếu app lưu trạng thái bằng source UID, hãy giữ mapping và tránh xử lý lại bản copy như một notification nghiệp vụ mới nếu điều đó không được mong đợi.

## 27. Folder counts và unread count

Folder có các phương thức đếm như:

~~~java
int total = folder.getMessageCount();
int unread = folder.getUnreadMessageCount();
~~~

Với IMAP, server/provider có thể cung cấp số liệu về unseen messages. Tuy nhiên:

- Counts có thể thay đổi khi client khác nhận, xóa hoặc đổi flags.
- Một số server/implementations trả về giá trị đặc biệt khi không biết chính xác số lượng hoặc chưa hỗ trợ.
- Counts từ folder mở và đóng có thể có behavior khác nhau.
- Nếu mailbox lớn, việc lấy counts thường xuyên có thể tạo tải.

### Một số đếm không phải snapshot bất biến

Ví dụ:

~~~text
T0 getUnreadMessageCount() -> 10
T1 Client khác đánh dấu 3 thư đã đọc
T2 search(UNSEEN) -> 7 messages
~~~

Không có lỗi logic nếu hai kết quả khác nhau. Nếu UI cần nhất quán mạnh trong một khung thời gian, cần thiết kế cache/versioning hoặc chấp nhận eventual consistency. Không dùng count một mình như bằng chứng xác thực processing progress.

### Không suy ra “chưa xử lý” từ unread count

Một hộp thư hỗ trợ có 0 unread chưa chắc tất cả tickets đã được tạo. Một nhân viên có thể đọc thủ công làm SEEN tăng trong khi bot chưa xử lý. Tương tự, mailbox có 30 unread có thể gồm các thư bot đã xử lý nhưng intentionally giữ unread.

Dashboard nên tách:

~~~text
IMAP unread_count = trạng thái inbox do server cung cấp
App pending_count = các UID chưa xử lý trong DB
App processed_count = các UID đã xử lý nghiệp vụ
Flag_sync_failed_count = kết quả đã xử lý nhưng chưa đổi cờ
~~~

## 28. POP3 và giới hạn của việc đánh dấu đã đọc

POP3 chủ yếu cung cấp các lệnh liệt kê, tải và xóa thư trong mailbox, không cung cấp mô hình folder và **\Seen** chuẩn giống IMAP.

Ví dụ dùng Jakarta Mail:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

Properties props = new Properties();
props.put("mail.store.protocol", "pop3s");
props.put("mail.pop3s.connectiontimeout", "5000");
props.put("mail.pop3s.timeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("pop3s");
Folder inbox = null;

try {
    store.connect(host, 995, username, password);
    inbox = store.getFolder("INBOX");
    inbox.open(Folder.READ_ONLY);

    for (Message message : inbox.getMessages()) {
        System.out.println(message.getSubject());
    }
} finally {
    if (inbox != null && inbox.isOpen()) {
        inbox.close(false);
    }
    if (store.isConnected()) {
        store.close();
    }
}
~~~

Đây là ví dụ đọc qua POP3S; nó không trình bày một API mark read/unread server-side vì POP3 không có hệ cờ IMAP tương đương.

### Nếu nghiệp vụ cần trạng thái đã đọc với POP3

Có thể lưu trạng thái trong database ứng dụng dựa trên định danh message phía POP3 (ví dụ **UIDL** nếu server hỗ trợ và implementation cung cấp), account identity và retention policy. Việc lưu “đã đọc” khi đó là trạng thái **của ứng dụng**, không phải cờ IMAP SEEN có thể đồng bộ với webmail.

Không lấy message number POP3 làm ID ổn định qua mọi lần download nếu mailbox có thể xóa/thay đổi. Nếu mục tiêu là đồng bộ read/unread giữa các thiết bị, cân nhắc dùng IMAP thay vì cố giả lập đầy đủ behavior trên POP3.

## 29. Polling và notification khi inbox thay đổi

Ứng dụng có thể đọc mailbox định kỳ:

~~~text
Every 30 seconds:
  Connect IMAP
  Open INBOX
  Search new/eligible messages
  Process candidates
  Close folder/store
~~~

Hoặc duy trì kết nối chờ thông báo thay đổi bằng tính năng như **IMAP IDLE** khi server/implementation hỗ trợ.

### Polling theo lịch

Ưu điểm:

- Dễ hiểu và tương thích rộng với Jakarta Mail.
- Có thể dễ quản lý timeout, reconnect và batch.
- Không cần duy trì một connection lâu.

Nhược điểm:

- Có độ trễ tối đa xấp xỉ chu kỳ polling.
- Gọi search quá thường xuyên có thể gây tải.
- Phải cẩn thận khi nhiều replicas cùng poll.

Với Spring Boot, có thể dùng **@Scheduled**:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InboxPollingJob {

    private final InboxPollingService service;

    public InboxPollingJob(InboxPollingService service) {
        this.service = service;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.inbox.poll-delay-ms:30000}"
    )
    public void run() {
        service.pollOnce();
    }
}
~~~

**InboxPollingService** là interface/service do ứng dụng xây dựng. Cần bật scheduling trong Spring context, ví dụ **@EnableScheduling**, nếu chưa được bật. Không nên để mỗi replica độc lập xử lý cùng mailbox mà không có atomic claim/dedup.

### IMAP IDLE và các thông báo push

IMAP có cơ chế IDLE, cho phép client chờ thông báo server khi mailbox thay đổi. Tuy nhiên:

- Jakarta Mail **Folder** API chung không quy định một phương thức idle portable cho mọi provider.
- Một số implementations có lớp IMAPFolder với **idle(...)** riêng.
- Connection có thể bị server timeout hoặc network proxy đóng.
- Khi được thông báo có thay đổi, vẫn cần fetch/search/UID để xác định messages thực sự.
- Phải có reconnect/backoff và xử lý lại state sau disconnect.

**IDLE không biến IMAP thành message queue exactly-once.** Nếu một notification bị mất trong lúc mạng đứt, ứng dụng cần quét UID/checkpoint sau reconnect.

### Đừng giữ connection vĩnh viễn mà không kiểm tra sức khỏe

Một worker chạy suốt nhiều ngày cần xử lý StoreClosedException, timeout, connection reset và credentials rotation. Có thể dùng vòng reconnect với backoff/jitter, giới hạn số connections theo account và tách liveness của ứng dụng khỏi trạng thái một mailbox cụ thể.

## 30. Security và giới hạn tài nguyên khi đọc thư

Email đến từ môi trường ngoài và có thể chứa dữ liệu không đáng tin. Dù message đã nằm trong mailbox doanh nghiệp, body/header và attachment vẫn có thể do attacker kiểm soát.

### Nguy cơ cần xử lý

| Nguy cơ | Ví dụ | Biện pháp |
| --- | --- | --- |
| **Spoofed sender** | From giả mạo bộ phận kế toán | Không ủy quyền nghiệp vụ theo From đơn thuần |
| **HTML injection** | HTML body chứa markup độc hại | Không render raw HTML; sanitize/escape theo ngữ cảnh |
| **Unsafe attachment** | Script hoặc archive chứa nội dung nguy hiểm | Allowlist, malware scanning, giới hạn kích thước |
| **Path traversal** | Filename có đường dẫn tương đối | Storage key do server tạo; filename chỉ là metadata |
| **Decompression bomb** | Attachment nén mở ra cực lớn | Giới hạn tài nguyên và loại file |
| **Privacy leak** | Log body chứa OTP/token | Redact, access control, retention |
| **Credential exposure** | In password/OAuth token IMAP | Secrets manager, không bật raw protocol debug |
| **Excessive polling** | Hàng trăm replicas kết nối mailbox mỗi giây | Rate limit/concurrency/scheduling |
| **Race/duplicate** | Hai workers xử lý cùng UID | DB unique key, atomic claim, idempotent side effect |
| **Unwanted read flags** | Preview body tự set SEEN | READ_ONLY/peek, test provider cụ thể |

### Không tin tên file từ Message.getFileName()

Attachment filename có thể là dữ liệu do sender đặt, có encoding bất thường, path separators hoặc ký tự điều khiển. Không dùng trực tiếp làm filesystem path:

~~~java
String suppliedFileName = bodyPart.getFileName();
// Không dùng: uploadDir.resolve(suppliedFileName)
~~~

Thay vào đó, dùng storage key sinh từ server, lưu filename hiển thị đã chuẩn hóa/giới hạn riêng, và áp content-type validation phù hợp với nội dung thực tế.

### Không tải mọi attachment khi chỉ muốn mark read

Nếu chỉ cần thay SEEN, không cần gọi getContent hoặc tải toàn bộ MIME. Chỉ resolve UID → Message → setFlag(SEEN, true), giảm network, CPU và nguy cơ dữ liệu độc hại. Phân tách chức năng “đánh dấu đã đọc” với “phân tích nội dung” giúp API dễ kiểm thử và an toàn hơn.

### Xác thực transport

Để bảo vệ IMAP credentials và nội dung thư trên mạng, dùng TLS với certificate/hostname verification, timeout hữu hạn, policy server/auth phù hợp. Không dùng trust-all trong production, không tắt xác minh certificate để xử lý nhanh một lỗi kết nối.

### Least privilege cho mailbox

Nếu service chỉ cần đọc và lập chỉ mục, ưu tiên cấp quyền đọc nếu provider có cơ chế tách quyền. Một service đánh dấu SEEN cần quyền ghi flags nhưng không nhất thiết cần quyền xóa toàn bộ mailbox. Nếu server không hỗ trợ phân quyền chi tiết, kiểm soát chức năng qua ứng dụng và audit những thao tác destructive như delete/expunge.

## 31. Kiểm thử Folder, Message và SEEN trong môi trường cô lập

Một integration test có giá trị cần làm việc với **IMAP server thực trong môi trường test**, không chỉ mock các methods của Message. Nó nên xác minh được:

1. Message mới xuất hiện trong INBOX.
2. Message ban đầu không có SEEN nếu fixture hỗ trợ điều đó.
3. Search bằng FlagTerm tìm thấy message chưa đọc.
4. Khi mở READ_WRITE và gọi setFlag(SEEN, true), server lưu trạng thái đã đọc.
5. Khi gọi setFlag(SEEN, false), server xóa flag.
6. Đọc body bằng chế độ peek không vô tình set SEEN.
7. READ_ONLY không được dùng để thực hiện thao tác ghi flags.

### Dùng GreenMail cho SMTP nhận thử và IMAP đọc thử

Một fixture chạy hai protocols trên loopback:

~~~text
JUnit test
   |
   +-- JavaMailSender -> SMTP port của GreenMail
   |                        |
   |                        v
   |                  Test mailbox
   |                        |
   '-- Jakarta Mail Store -> IMAP port của GreenMail
                                 |
                                 v
                         Read / set SEEN / search
~~~

Ví dụ JUnit/Jakarta Mail dùng GreenMail (phiên bản phù hợp Jakarta Mail):

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.Flags;
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import jakarta.mail.search.FlagTerm;
import java.util.Properties;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class ImapSeenIntegrationTest {

    private GreenMail mailServer;

    @BeforeEach
    void start() {
        mailServer = new GreenMail(
                new ServerSetup[] {
                        new ServerSetup(
                                0, "127.0.0.1",
                                ServerSetup.PROTOCOL_SMTP
                        ),
                        new ServerSetup(
                                0, "127.0.0.1",
                                ServerSetup.PROTOCOL_IMAP
                        )
                }
        );
        mailServer.start();
        mailServer.setUser(
                "reader@local.test",
                "reader",
                "test-secret"
        );
    }

    @AfterEach
    void stop() {
        if (mailServer != null) {
            mailServer.stop();
        }
    }

    private void deliverTestMessage() throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(mailServer.getSmtp().getPort());

        var mime = sender.createMimeMessage();
        var helper = new MimeMessageHelper(mime, false, "UTF-8");
        helper.setFrom("sender@local.test");
        helper.setTo("reader@local.test");
        helper.setSubject("Message kiểm tra SEEN");
        helper.setText("Nội dung test.");
        sender.send(mime);

        assertTrue(mailServer.waitForIncomingEmail(5000, 1));
    }

    @Test
    void searchUnreadThenMarkReadAndUnread() throws Exception {
        deliverTestMessage();

        Properties props = new Properties();
        props.put("mail.store.protocol", "imap");
        Session session = Session.getInstance(props);

        Store store = session.getStore("imap");
        Folder inbox = null;
        try {
            store.connect(
                    "127.0.0.1",
                    mailServer.getImap().getPort(),
                    "reader",
                    "test-secret"
            );

            inbox = store.getFolder("INBOX");
            inbox.open(Folder.READ_WRITE);

            Message[] unread = inbox.search(
                    new FlagTerm(
                            new Flags(Flags.Flag.SEEN),
                            false
                    )
            );
            assertEquals(1, unread.length);

            Message message = unread[0];
            assertFalse(message.isSet(Flags.Flag.SEEN));

            message.setFlag(Flags.Flag.SEEN, true);
            assertTrue(message.isSet(Flags.Flag.SEEN));

            message.setFlag(Flags.Flag.SEEN, false);
            assertFalse(message.isSet(Flags.Flag.SEEN));
        } finally {
            if (inbox != null && inbox.isOpen()) {
                inbox.close(false);
            }
            if (store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

**Đây là kiểm thử IMAP không TLS trên loopback, chỉ dùng để kiểm tra flags và folder lifecycle.** Không dùng credentials thật hoặc gửi mail ra Internet. Để kiểm thử IMAPS/TLS/hostname, cần một fixture SSL có certificate riêng, test truststore và các trường hợp chứng chỉ không hợp lệ; không dùng test plaintext này làm bằng chứng kết nối production an toàn.

### Tại sao cần thêm test reopen?

Ở bài test trên, **message.isSet(...)** ngay sau setFlag có thể sử dụng cached state trong cùng session. Để xác nhận server thực sự lưu flag, một integration test bổ sung nên:

1. Lấy UID/UIDVALIDITY.
2. Gọi setFlag(SEEN, true).
3. Đóng Folder và Store.
4. Mở một connection mới.
5. Lấy lại Message theo UID và xác nhận SEEN còn tồn tại.

Đây là kiểm thử mạnh hơn cho **server persistence**, đồng thời phát hiện implementation test giả chỉ sửa flags cục bộ.

### Test body peek

Với một message ban đầu UNSEEN:

~~~text
Given:
  IMAP folder READ_WRITE
  mail.imap.peek=true
  message UNSEEN
When:
  getContent() / fetch body
Then:
  server-side SEEN vẫn false
~~~

Test cần mở lại bằng connection khác để quan sát flag độc lập. Behavior của property peek có thể khác giữa Jakarta Mail implementations/versions; dùng test với provider/fixture thực tế thay vì khẳng định bằng mock.

### Test READ_ONLY

~~~text
Given:
  Folder open READ_ONLY
When:
  setFlag(SEEN, true)
Then:
  thao tác ghi không được phép
  server-side SEEN không đổi
~~~

Tùy provider, API có thể ném **IllegalWriteException** hoặc một MessagingException phù hợp; test nên xác nhận trạng thái server vẫn không đổi, không chỉ ép một exception message cụ thể.

## 32. Các test trường hợp rìa cần có

Một bộ test thực tế có thể mở rộng theo ma trận:

| Test | Setup | Kỳ vọng |
| --- | --- | --- |
| Folder không tồn tại | Tên folder sai | Không cố gọi getMessages, báo lỗi có nghĩa |
| Folder rỗng | INBOX count=0 | Không gọi getMessage(0) |
| Read-only folder | READ_ONLY + mark SEEN | Ghi bị từ chối, flag không đổi |
| Read-write folder | READ_WRITE + mark SEEN | Persist SEEN |
| Mark unread | SEEN true rồi set false | UNSEEN |
| Search unread | Một SEEN, một UNSEEN | Chỉ lấy UNSEEN |
| Body preview | Peek + READ_WRITE | Không tự đổi SEEN |
| Fetch without peek | Provider có auto-SEEN | Xác minh tác dụng phụ có thể xảy ra |
| Message deleted/expunged | Message biến mất sau search | Xử lý mất message, không crash cả batch |
| UIDVALIDITY đổi | Mailbox được tạo lại | Không xử lý theo checkpoint cũ |
| Nhiều clients | Hai workers cùng thấy UID | Database dedup chỉ tạo một ticket |
| Business commit fail | Đọc xong nhưng lưu thất bại | Không mark processed/SEEN theo policy |
| Flag-sync fail | Ticket đã lưu, IMAP lỗi | Không tạo ticket trùng khi retry |
| Connection reset | Store/Folder đóng đột ngột | Reconnect/retry an toàn |
| Multipart | Plain/HTML/attachment | Parse có giới hạn, không cast sai |
| Shared read state | User A đọc, user B chưa đọc | Per-user app state nếu yêu cầu |
| POP3 | Message được tải bằng POP3S | Không giả định server có SEEN |

### Kiểm thử commit rồi mới đánh dấu

Một failure injection hữu ích:

~~~text
T1 Poll thấy UID=108
T2 Parse body thành công
T3 Ticket service ném exception trước commit
T4 Worker dừng attempt
Expected:
  inbound_mail_processing chưa PROCESSED
  worker không tự set SEEN
~~~

Nếu mục đích là bảo toàn unread count khi parse thất bại, cần đảm bảo trước T2 body được fetch với **peek hoặc READ_ONLY**; nếu getContent đã làm server set SEEN, đến T4 mới quyết định không gọi setFlag cũng không phục hồi trạng thái ban đầu.

### Kiểm thử replay cùng UID

~~~text
Given:
  UID 108 đã xử lý thành công, ticket #42 tồn tại
When:
  Poll IMAP thấy UID 108 lần nữa
Then:
  không tạo ticket mới
  có thể retry flag-sync nếu trước đó thất bại
~~~

Nếu UIDVALIDITY đổi, test cần xác nhận cùng UID 108 trong epoch mới là một source key khác, không bị suppress nhầm bởi record cũ.

## 33. Quan sát và xử lý sự cố khi đọc mailbox

Một ứng dụng nhận mail cần giám sát cả network/IMAP và tiến độ xử lý nghiệp vụ.

### Metrics gợi ý

| Metric | Ý nghĩa |
| --- | --- |
| **mail_inbox_poll_total{result}** | Số lần polling thành công/thất bại |
| **mail_inbox_poll_duration_seconds** | Thời gian poll/fetch |
| **mail_inbox_discovered_messages_total** | Số UID mới được ghi nhận |
| **mail_inbox_processing_total{outcome}** | Số lần xử lý theo kết quả |
| **mail_inbox_processing_pending** | Số record chưa PROCESSED |
| **mail_inbox_flag_sync_failures_total** | Số lần set SEEN/move lỗi |
| **mail_inbox_unread_messages** | Số unread theo server |
| **mail_inbox_checkpoint_age_seconds** | Độ cũ của checkpoint/poll thành công |
| **mail_inbox_connection_failures_total** | Lỗi kết nối/auth/TLS |
| **mail_inbox_retries_total{reason}** | Số retry của business processing |

Đây là các metric do ứng dụng tự thiết kế, **không có sẵn từ Spring Framework Mail**. Tránh label theo message UID, email address hoặc ticket ID vì tăng cardinality và rủi ro quyền riêng tư.

### Logs có cấu trúc

~~~text
event=inbound_mail_processing_completed
mailbox_id=support-1
folder=INBOX
uid_validity=19220
uid=108
processing_id=opaque-42
outcome=PROCESSED
flag_sync=SYNCED
duration_ms=281
~~~

Thông tin này đủ để liên kết source message và processing record mà không cần in Subject, From, OTP, body hoặc attachments.

### Dashboard tách mailbox flags và app state

Một dashboard tốt có thể hiển thị:

~~~text
IMAP unread:           43
App discovered:        58
App processing:         3
App retry wait:         2
App processed today:  870
Flag sync failed:       5
Last successful poll:   2m ago
UIDVALIDITY changed:    0
~~~

**IMAP unread=43** và **App pending=5** không nhất thiết mâu thuẫn: một phần thư có thể được đọc thủ công hoặc ứng dụng không có policy mark read. Hãy xác định rõ semantics trước khi tạo alert.

### Tình huống thường gặp khi lỗi

| Triệu chứng | Nghi vấn | Hướng xử lý |
| --- | --- | --- |
| Authentication failed | Password/OAuth token hết hạn, mechanism sai | Kiểm tra secret/refresh, không in credentials |
| Certificate validation failed | CA/hostname/TLS config sai | Kiểm tra truststore, không trust-all |
| FolderClosedException | Server đóng folder, timeout, reconnect | Mở lại folder, retry theo UID/dedup |
| MessageRemovedException | Message đã bị expunge | Ghi nhận source không còn tồn tại, xử lý theo policy |
| Không tìm thấy unread | Đã auto-SEEN khi fetch body | Kiểm tra READ_ONLY/peek và client khác |
| Unread count giảm nhưng ticket không tăng | UI/client khác đọc hoặc worker mark quá sớm | Tách processed state và read flag |
| Ticket bị tạo trùng | Dựa vào SEEN làm lock | Unique + atomic claim + idempotent side effect |
| Last UID tăng nhưng bỏ sót | Advance checkpoint trước commit | Scan overlap/record per UID |
| UID quay về thấp | UIDVALIDITY đổi, folder reset | Resynchronization có kiểm soát |
| IMAP connection quá nhiều | Nhiều replicas/poll interval thấp | Giới hạn concurrency/pool và scheduling |
| Parser OOM | Large attachment/decompression | Size limits, streaming, quarantine |

### Runbook ngắn khi “thư có mà bot không xử lý”

1. Kiểm tra kết nối IMAP/TLS/AUTH và last successful poll.
2. Xác minh đúng **mailbox ID + folder name**, không đọc nhầm account/folder.
3. Kiểm tra UIDVALIDITY và checkpoint.
4. Kiểm tra **SEARCH UNSEEN** có còn phù hợp mục tiêu hay thư đã bị user/client khác set SEEN.
5. Kiểm tra bảng processing theo UID, trạng thái, lease và lỗi retry.
6. Nếu business side effect có kết quả mơ hồ, đối soát trước khi retry.
7. Kiểm tra IMAP flag-sync và lỗi Folder READ_ONLY/permission.
8. Đảm bảo sau phục hồi không tạo tickets trùng và không thay đổi flags ngoài ý định.

Không giải quyết nhanh bằng cách reset SEEN của toàn bộ mailbox về false hoặc đánh dấu tất cả true; hai thao tác đó ảnh hưởng trải nghiệm người dùng và có thể tạo một đợt xử lý trùng.

## 34. Những sai lầm phổ biến

### Sai lầm 1 — Dùng JavaMailSender để đọc email

**Vấn đề:** JavaMailSender gửi qua SMTP, không cung cấp Store/Folder để đồng bộ inbox.

**Cách làm:** dùng **Jakarta Mail Session + Store + Folder + Message** với IMAP/POP3 phù hợp, hoặc xây dịch vụ inbound mail có abstraction riêng.

### Sai lầm 2 — Gọi getMessages() mà chưa mở Folder

**Vấn đề:** một số API yêu cầu folder đang open, có thể ném IllegalStateException/MessagingException theo hợp đồng.

**Cách làm:** connect Store, xác minh folder.exists(), open READ_ONLY/READ_WRITE, xử lý, close.

### Sai lầm 3 — Gọi getMessage(0) hoặc getMessage(count) khi count=0

**Vấn đề:** message numbers trong Jakarta Mail bắt đầu từ 1.

**Cách làm:** kiểm tra folder có message rồi mới truy cập, hoặc dùng search trả về mảng rỗng.

### Sai lầm 4 — Lưu sequence number làm ID vĩnh viễn

**Vấn đề:** expunge làm message numbers thay đổi.

**Cách làm:** dùng mailbox + folder + UIDVALIDITY + UID, lưu state ở database.

### Sai lầm 5 — Coi Message-ID header là khóa không thể giả mạo

**Vấn đề:** sender có thể đặt Message-ID, trùng/thiếu header.

**Cách làm:** dùng key từ mailbox/UID cho nguồn thư; Message-ID chỉ hỗ trợ correlation.

### Sai lầm 6 — Đọc body rồi mới nghĩ đến tác dụng phụ SEEN

**Vấn đề:** getContent/getInputStream có thể đánh dấu thư đã đọc.

**Cách làm:** xác định policy từ trước, dùng READ_ONLY/peek khi cần giữ unread, test provider thực.

### Sai lầm 7 — Chỉ setFlag(SEEN, true) khi chưa lưu nghiệp vụ

**Vấn đề:** worker chết sau setFlag nhưng trước tạo ticket, lần poll sau bỏ qua message.

**Cách làm:** persist business result thành công trước, sau đó đồng bộ SEEN; dùng dedup state.

### Sai lầm 8 — Chỉ dựa vào SEEN để chống xử lý trùng

**Vấn đề:** hai workers có thể cùng search UNSEEN và xử lý trước khi một worker đặt cờ.

**Cách làm:** unique key + atomic claim + idempotent side effect.

### Sai lầm 9 — Mặc định READ_ONLY có thể set flags

**Vấn đề:** server không cho phép ghi trong mode READ_ONLY.

**Cách làm:** mở READ_WRITE cho thao tác set SEEN/unseen, xử lý permission failures.

### Sai lầm 10 — Nghĩ close(false) rollback cờ

**Vấn đề:** server có thể đã lưu SEEN trước khi đóng folder.

**Cách làm:** hiểu semantics của close(expunge), không dùng close như database rollback.

### Sai lầm 11 — Gọi close(true) như một thao tác dọn dẹp mặc định

**Vấn đề:** nó có thể expunge messages đã đánh dấu DELETED, gây mất thư ngoài ý định.

**Cách làm:** chỉ expunge theo workflow xóa đã được phê duyệt; thường dùng close(false).

### Sai lầm 12 — Giả định POP3 có SEEN giống IMAP

**Vấn đề:** POP3 không cung cấp hệ thống read/unread server-side tương đương.

**Cách làm:** dùng IMAP hoặc lưu app-level state riêng cho POP3.

### Sai lầm 13 — Dựa vào RECENT để tìm unread

**Vấn đề:** IMAP \Recent không giống \Seen=false.

**Cách làm:** dùng **FlagTerm(SEEN, false)** hoặc SEARCH UNSEEN.

### Sai lầm 14 — Khi setFlag thất bại, tạo lại business record

**Vấn đề:** business side effect có thể đã commit, chỉ phần đồng bộ flags lỗi.

**Cách làm:** tách processing status và flag_sync_status; retry sync riêng.

### Sai lầm 15 — Không kiểm tra UIDVALIDITY sau reconnect

**Vấn đề:** UID cũ có thể trỏ tới message khác khi mailbox epoch đổi.

**Cách làm:** so sánh UIDVALIDITY và chạy resynchronization khi thay đổi.

### Sai lầm 16 — Dùng shared \Seen làm trạng thái đọc cho từng nhân viên

**Vấn đề:** khi một người đọc, những người khác có thể thấy đã đọc dù chưa mở.

**Cách làm:** thêm bảng per-user read state nếu UI cần thông tin riêng.

### Sai lầm 17 — Đồng thời scan body toàn bộ mailbox

**Vấn đề:** network/heap bị quá tải, attachments lớn, unread flags bị đổi ngoài ý muốn.

**Cách làm:** server-side search/UID, fetch metadata theo batch, giới hạn body/attachment.

### Sai lầm 18 — Tin From hoặc Subject để thực hiện giao dịch

**Vấn đề:** header do sender kiểm soát, có thể bị spoof.

**Cách làm:** xác thực sender và quyền nghiệp vụ bằng chính sách riêng; không ủy quyền theo email string.

### Sai lầm 19 — Không đóng Folder/Store khi exception

**Vấn đề:** connection leak, server giới hạn IMAP sessions và worker bị kẹt.

**Cách làm:** finally để close(false) và close Store, có timeout và reconnect/backoff.

### Sai lầm 20 — Giả định một folder name dùng được trên mọi provider

**Vấn đề:** Sent/Trash/Spam có thể đổi tên/localize, delimiter khác nhau.

**Cách làm:** discover/cấu hình folder mapping theo account/provider; không ghép tên như filesystem path.

### Sai lầm 21 — Quên khác biệt giữa đọc thư và xử lý thư

**Vấn đề:** mailbox có unread=0 nhưng backlog nghiệp vụ vẫn lớn.

**Cách làm:** đo **mailbox unread** và **processing pending** riêng; dùng trạng thái business để đánh giá tiến độ.

### Sai lầm 22 — Để một service có quyền expunge không giới hạn

**Vấn đề:** lỗi logic có thể làm mất cả thư khách hàng khác.

**Cách làm:** least privilege, audit và workflow xóa riêng; không ghép xóa với mark-read.

## 35. Các tình huống luyện tập

### Tình huống A — Xem thử email nhưng giữ unread

Nhân viên chỉ muốn preview nội dung thư chưa xử lý.

**Hỏi:** dùng getContent trên Folder.READ_WRITE có an toàn cho unread state không?

**Đáp:** không thể mặc định. Fetch body có thể set SEEN; nên dùng READ_ONLY hoặc IMAP peek được provider hỗ trợ, đồng thời test server-side flag sau khi đọc.

### Tình huống B — Người dùng bấm “Mark as read”

Giao diện muốn đổi trạng thái cho một message cụ thể.

**Hỏi:** dùng thao tác nào?

**Đáp:** mở Folder.READ_WRITE, xác định message bằng UID/UIDVALIDITY và gọi **message.setFlag(Flags.Flag.SEEN, true)**. Phải authorization mailbox/folder và xử lý UID đã bị move/delete.

### Tình huống C — Muốn đánh dấu thư chưa đọc

**Hỏi:** gọi lại setFlag(SEEN, true) có đúng không?

**Đáp:** không. Để bỏ trạng thái đã đọc, dùng **setFlag(Flags.Flag.SEEN, false)** trong folder có quyền ghi.

### Tình huống D — Hộp thư có 0 messages

Code lấy count=0 rồi gọi getMessage(count).

**Hỏi:** điều gì sai?

**Đáp:** message number bắt đầu từ 1; không có message số 0. Cần xử lý folder rỗng trước.

### Tình huống E — Worker đã set SEEN nhưng transaction ticket fail

Sau lỗi, thư không còn trong kết quả SEARCH UNSEEN.

**Hỏi:** cách thiết kế lại?

**Đáp:** đọc bằng peek/READ_ONLY để tránh SEEN sớm, persist nghiệp vụ trước rồi mark read; sử dụng bảng processing độc lập để retry đúng.

### Tình huống F — Hai workers cùng lấy một thư

Cả hai tìm được UID 100 và gọi API tạo ticket.

**Hỏi:** SEEN có làm lock không?

**Đáp:** không. Cần atomic claim trong database và external API idempotency để tránh hai tickets.

### Tình huống G — Folder đã expunge một message

Lúc đầu message #5 là thư A; sau expunge, #5 là thư B.

**Hỏi:** tại sao phải dùng UID?

**Đáp:** message number thay đổi theo cấu trúc folder; UID cùng UIDVALIDITY cho định danh ổn định hơn trong mailbox.

### Tình huống H — UIDVALIDITY đổi

Ứng dụng có checkpoint UID=900, server đổi UIDVALIDITY sau restore.

**Hỏi:** tiếp tục lấy UID >900 có được không?

**Đáp:** không. Phải xử lý epoch mới và đồng bộ lại; UID=900 của epoch cũ không còn nghĩa tương đương.

### Tình huống I — POP3 inbox cần nút unread

Ứng dụng dùng POP3S và muốn đồng bộ \Seen với webmail.

**Hỏi:** có thể dùng POP3 setFlag(SEEN, false) như IMAP không?

**Đáp:** không thể giả định giao thức hỗ trợ. Dùng IMAP nếu cần server-side read state, hoặc quản lý read state riêng ở ứng dụng.

### Tình huống J — Shared mailbox có 20 nhân viên

Alice đọc thư, Bob vẫn muốn thư hiển thị chưa đọc đối với bản thân.

**Hỏi:** shared \Seen đáp ứng không?

**Đáp:** thường không. Cần per-user read state ở application, tách khỏi IMAP shared flag.

### Tình huống K — Mark read nhiều messages

UI gửi 500 UIDs tới API.

**Hỏi:** nên xử lý như thế nào?

**Đáp:** giới hạn số phần tử, kiểm tra authorization, UIDVALIDITY, resolve UID đang tồn tại, batch setFlags và trả kết quả rõ cho UID đã bị xóa hoặc không hợp lệ.

### Tình huống L — Message đã xử lý nhưng set SEEN lỗi

Ticket đã được tạo, IMAP connection bị mất trước khi setFlag thành công.

**Hỏi:** poll lại có tạo ticket thứ hai không?

**Đáp:** không nên. Processing record đánh dấu PROCESSED và idempotency key ngăn tạo ticket trùng; chỉ retry flag-sync.

### Tình huống M — Message-ID giống nhau từ hai thư

Một người gửi hai mail có header Message-ID trùng nhau.

**Hỏi:** có nên coi là cùng một message?

**Đáp:** không tự động. Header không phải khóa nguồn tin cậy; mailbox UID và UIDVALIDITY phân biệt các bản ghi.

### Tình huống N — Đọc toàn bộ getContent gây OOM

Một attachment rất lớn hoặc dữ liệu nén bất thường làm đầy heap.

**Hỏi:** biện pháp nào phù hợp?

**Đáp:** giới hạn body/attachment, stream an toàn, malware policy, limit MIME nesting/parts và không tải mọi message bodies chỉ để kiểm tra unread.

### Tình huống O — close(true) dùng trong finally

Service chỉ đọc thư nhưng luôn gọi folder.close(true).

**Hỏi:** có vấn đề gì?

**Đáp:** true có thể expunge những messages đã DELETED trong folder. Dùng close(false) trừ khi workflow được ủy quyền rõ ràng cần expunge.

### Tình huống P — Poller không thấy email mới khi thư đã SEEN

Một nhân viên mở thư trước khi bot chạy.

**Hỏi:** có nên tìm theo UNSEEN nếu yêu cầu là xử lý mọi mail mới đến?

**Đáp:** có thể không phù hợp. Nếu yêu cầu là “mọi thư mới”, dùng UID discovery/checkpoint và processing state, không phụ thuộc SEEN của các clients khác.

### Tình huống Q — Worker reconnect sau một ngày outage

Mailbox chứa nhiều messages mới và những flags đã thay đổi.

**Hỏi:** có nên quay về message number cuối cùng đã lưu?

**Đáp:** không. Dùng UIDVALIDITY + UID checkpoint, quét overlap/dedup, kiểm tra message còn tồn tại và xử lý từng UID idempotently.

### Tình huống R — Một email bị move sang Processed

UID gốc ở INBOX không còn; folder đích có UID mới.

**Hỏi:** có nên coi message ở folder đích là business event mới?

**Đáp:** không nếu workflow đã xử lý nó; cần mapping/source key hoặc policy phân biệt cùng thư khi xuất hiện ở folder khác.

### Tình huống S — Folder.READ_ONLY báo lỗi khi setFlag

Code mở folder READ_ONLY rồi dùng setFlag(SEEN, true).

**Hỏi:** thay setFlag thành getFlags có giải quyết được không?

**Đáp:** không. getFlags chỉ đọc. Muốn cập nhật phải mở READ_WRITE và được server cho quyền ghi.

### Tình huống T — Hộp thư dùng RECENT để tính unread

Dashboard hiển thị recent=0 dù có nhiều thư chưa đọc.

**Hỏi:** dùng chỉ số nào?

**Đáp:** dùng server unread count hoặc NOT SEEN search, đồng thời hiểu các giới hạn về consistency. RECENT không đại diện trực tiếp cho UNSEEN.

## 36. Quy trình triển khai ứng dụng đọc inbox

~~~text
1. Xác định use case
   |
   +-- Hiển thị webmail?
   +-- Bot tạo ticket?
   +-- Đồng bộ email trong ứng dụng?
   '-- Kiểm thử hộp thư?
   |
   v
2. Chọn giao thức
   |
   +-- IMAP/IMAPS nếu cần folders và SEEN
   '-- POP3/POP3S nếu workflow chỉ tải thư và app tự quản lý state
   |
   v
3. Cấu hình transport và auth an toàn
   |
   +-- TLS/hostname verification
   +-- Credentials/OAuth secrets
   +-- Connection/read/write timeouts
   '-- Rate limit/concurrency
   |
   v
4. Xác định folder/account scope
   |
   +-- Store.connect
   +-- Folder.exists
   +-- Folder.READ_ONLY hoặc READ_WRITE
   '-- UIDFolder/UIDVALIDITY nếu có
   |
   v
5. Tìm candidates
   |
   +-- FlagTerm(SEEN, false) nếu use case = unread
   +-- UID scan nếu use case = new arrivals
   '-- Server-side search + batch metadata
   |
   v
6. Đọc dữ liệu cần thiết
   |
   +-- Subject, From, date, flags
   +-- Body với peek/READ_ONLY nếu cần giữ unread
   '-- Multipart/attachments có giới hạn
   |
   v
7. Persist business result an toàn
   |
   +-- Unique mailbox + folder + UIDVALIDITY + UID
   +-- Atomic claim/idempotency
   '-- Commit success/retry status
   |
   v
8. Đồng bộ mailbox state nếu policy yêu cầu
   |
   +-- Open READ_WRITE
   +-- Recheck UIDVALIDITY
   +-- setFlag(SEEN, true/false)
   '-- Retry flag sync riêng nếu thất bại
   |
   v
9. Close Folder/Store và quan sát kết quả
   |
   +-- Poll/connection health
   +-- Processing lag
   +-- Flag sync failures
   '-- Errors without logging sensitive content
~~~

### Checklist trước khi triển khai

- **Giao thức:** use case thực sự cần IMAP folders/SEEN hay chỉ tải thư bằng POP3?
- **Session/Store:** kết nối tới đúng mailbox, timeout và TLS được cấu hình?
- **Folder mode:** READ_ONLY cho quan sát, READ_WRITE khi cập nhật cờ?
- **UID:** lưu source key đúng account/folder/UIDVALIDITY/UID?
- **Search:** unread workflow có dùng NOT SEEN; new-arrival workflow có dùng UID scan?
- **Body:** có biết getContent có thể set SEEN; peek behavior đã được test?
- **MIME:** phân biệt plain, HTML, multipart; giới hạn kích thước và attachment?
- **Business state:** xử lý trùng bằng unique key/atomic claim, không chỉ SEEN?
- **Flag sync:** cập nhật sau commit, thất bại không làm chạy lại business side effect?
- **Concurrency:** hạn chế số workers/connections và không chia sẻ Folder bừa bãi?
- **Privacy:** không in raw MIME/token/password vào logs?
- **Tests:** GreenMail/IMAP fixture có xác nhận persistence, UID, unread và failure cases?

## 37. Tóm tắt nguyên tắc cốt lõi

~~~text
JavaMailSender                  -> gửi SMTP
Session + Store + Folder       -> nhận/đọc mailbox
Folder.READ_ONLY               -> quan sát, không sửa flags
Folder.READ_WRITE              -> có thể ghi flags nếu server cho phép
Message                        -> thư trong một folder cụ thể
Message number                 -> vị trí, không phải ID bền vững
UID + UIDVALIDITY + folder     -> định danh nguồn IMAP tốt hơn
SEEN=true                      -> đã đọc
SEEN=false                     -> chưa đọc
RECENT                         != UNSEEN
getContent / body fetch        -> có thể tự thêm SEEN
Peek / READ_ONLY               -> bảo vệ trạng thái đọc theo policy
search(FlagTerm(SEEN,false))   -> tìm thư unread
SEEN                           != PROCESSED
SEEN                           != atomic claim
Database unique + lease        -> giảm xử lý trùng
Business commit                -> trước khi optional mark SEEN
close(false)                   != rollback flag writes
close(true)                    -> có thể expunge DELETED
POP3                           != IMAP flags
IMAP accepted/read             != business action completed
~~~

**Folder, message và đánh dấu đã đọc** là nền tảng để xây ứng dụng nhận thư bằng Jakarta Mail trong ngữ cảnh Spring Framework Mail. **Store** tạo kết nối tới mailbox, **Folder** đại diện nơi chứa thư, **Message** cho phép đọc metadata/body và **Flags.Flag.SEEN** diễn tả trạng thái đã đọc trên IMAP. Nhưng unread flag không phải khóa chống xử lý trùng, và đọc body đôi khi có tác dụng phụ thay đổi SEEN. Khi hệ thống cần tự động xử lý email, hãy dùng **UID cùng UIDVALIDITY**, lưu trạng thái nghiệp vụ riêng, kiểm soát transaction/retry và chỉ cập nhật flags khi đúng mục đích. Kết hợp IMAP/POP3 đúng ngữ cảnh, quản lý tài nguyên kết nối, kiểm thử trong hộp thư cô lập và theo dõi những thay đổi từ nhiều clients sẽ giúp tính năng inbox ổn định, tránh bỏ sót thư cũng như tránh đánh dấu đã đọc ngoài ý muốn.
