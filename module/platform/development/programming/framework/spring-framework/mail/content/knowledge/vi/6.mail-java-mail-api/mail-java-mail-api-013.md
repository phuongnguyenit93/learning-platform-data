# Đọc nguyên nhân gốc từ exception chain trong Spring Framework Mail

## 1. Vì sao một lỗi gửi email lại có nhiều lớp exception?

Khi gọi `JavaMailSender.send(...)`, ứng dụng Spring có thể nhận ngoại lệ với thông báo khá chung như “Failed messages” hoặc “Mail server connection failed”. Nếu chỉ xem thông báo ngoài cùng, lập trình viên dễ kết luận rằng **SMTP server bị lỗi**, trong khi nguyên nhân trực tiếp có thể là:

- Không phân giải được DNS của SMTP host.
- Kết nối TCP tới cổng SMTP bị từ chối hoặc hết thời gian chờ.
- TLS handshake thất bại vì chứng chỉ hoặc cấu hình bảo mật.
- Máy chủ từ chối SMTP authentication.
- Địa chỉ người gửi không được tài khoản hiện tại cho phép.
- Một hay nhiều người nhận bị từ chối ở lệnh `RCPT TO`.
- Dữ liệu MIME, tệp đính kèm hoặc nguồn nội dung không đọc được.
- Máy chủ trả lỗi sau khi đã nhận lệnh `DATA`.

Với **Spring Framework Mail**, một lỗi có thể đi qua nhiều tầng:

~~~mermaid
flowchart TD
    A["Service nghiệp vụ"] --> B["JavaMailSender"]
    B --> C["Spring MailException"]
    C --> D["Jakarta Mail MessagingException"]
    D --> E["Ngoại lệ SMTP / TLS / I-O"]
    E --> F["Nguyên nhân cụ thể: mã SMTP, DNS, socket, chứng chỉ..."]
~~~

Sơ đồ này minh họa các lớp **có thể xuất hiện**, không có nghĩa mọi lần lỗi đều chứa đủ chúng. Ví dụ, lỗi tạo MIME có thể xảy ra trước khi kết nối SMTP, còn lỗi xác thực có thể được Spring biểu diễn trực tiếp bằng `MailAuthenticationException`.

**Exception chain** là chuỗi những ngoại lệ biểu diễn cùng một sự cố ở các mức trừu tượng khác nhau. Muốn chẩn đoán chính xác, cần giữ hai loại thông tin:

1. **Bối cảnh ở tầng ngoài**: hoạt động gửi nào thất bại, `JavaMailSender` báo gì, thao tác chuẩn bị hay gửi gặp lỗi.
2. **Nguyên nhân kỹ thuật ở tầng trong**: lỗi mạng, TLS, xác thực, SMTP reply code, recipient hoặc nội dung MIME.

> **Nguyên tắc:** Tìm nguyên nhân sâu có ý nghĩa, nhưng vẫn giữ ngữ cảnh ở các ngoại lệ bên ngoài. “Exception cuối cùng” không nhất thiết giải thích được tình trạng của tất cả người nhận hoặc tất cả thông điệp.

## 2. Java cause chain và Jakarta Mail next exception

Java hỗ trợ cơ chế lồng ngoại lệ chuẩn qua `Throwable.getCause()`: một exception có thể bọc một nguyên nhân khác, và nguyên nhân ấy có thể tiếp tục bọc exception sâu hơn.

Ví dụ minh họa:

~~~text
org.springframework.mail.MailSendException
  └── jakarta.mail.MessagingException
        └── java.net.SocketTimeoutException
              "Read timed out"
~~~

Tuy nhiên, **Jakarta Mail có thêm `MessagingException.getNextException()`**. Đây là liên kết exception riêng của Jakarta Mail, có thể chứa chi tiết không được thu thập đầy đủ nếu một công cụ chỉ duyệt `getCause()` theo một nhánh duy nhất.

~~~text
MessagingException
  ├── getCause()          -> Throwable cause (nếu có)
  └── getNextException()  -> Exception tiếp theo trong cơ chế Jakarta Mail
~~~

Trong một số implementation, `getCause()` và `getNextException()` trỏ đến cùng một đối tượng, hoặc những đối tượng liên quan. Một bộ truy vết vì thế nên **duyệt cả hai đường, khử trùng theo danh tính exception và ngăn vòng lặp**.

Ngoài ra, `MailSendException` có thể chứa **nhiều lỗi gắn với nhiều message**, thay vì một cause tuyến tính. Khi gửi hàng loạt, trạng thái lỗi có thể được mô hình hóa như **đồ thị các exception**:

~~~text
MailSendException
  ├── getCause() -> lỗi tổng quát (nếu có)
  ├── getMessageExceptions() -> lỗi của từng message
  └── getFailedMessages() -> map Message => Exception
                               ├── message A => SendFailedException
                               └── message B => MessagingException
~~~

Chỉ gọi `getRootCause()` hoặc `getMostSpecificCause()` trên ngoại lệ Spring có thể hữu ích đối với **chuỗi `getCause()`**, nhưng chưa thay thế việc kiểm tra `getNextException()` và các nhánh message-level.

## 3. Những loại ngoại lệ cần nhận ra

### 3.1. Ngoại lệ ở tầng Spring Mail

`org.springframework.mail.MailException` là ngoại lệ nền tảng dạng runtime của Spring Mail. Một số lớp con thông dụng:

| Loại exception | Ý nghĩa thường gặp | Nên kiểm tra tiếp |
| --- | --- | --- |
| `MailAuthenticationException` | Xác thực với hệ thống mail thất bại | Credentials, phương thức SMTP AUTH, chính sách provider, TLS |
| `MailSendException` | Không gửi được một hay nhiều message | Cause, lỗi từng message, giao thức SMTP, I/O, recipients |
| `MailParseException` | Không thể phân tích/tạo nội dung mail ở một đường xử lý | MIME, địa chỉ, charset, chi tiết lỗi bên trong |
| `MailPreparationException` | Callback chuẩn bị message thất bại | Code trong `MimeMessagePreparator`, dữ liệu body/attachment |
| `MailException` | Nhóm lỗi gửi mail chung của Spring | Lớp con thực tế và cause |

Không nên mặc định **mọi** lỗi socket đều được Spring bọc bằng cùng một lớp: đường xử lý và implementation quyết định kiểu exception cuối cùng.

### 3.2. Ngoại lệ ở tầng Jakarta Mail

| Loại | Ý nghĩa |
| --- | --- |
| `jakarta.mail.MessagingException` | Lỗi tổng quát Jakarta Mail; hỗ trợ `getNextException()` |
| `jakarta.mail.AuthenticationFailedException` | Lỗi xác thực mail |
| `jakarta.mail.SendFailedException` | Có thể chứa các nhóm địa chỉ hợp lệ/không hợp lệ khi gửi |
| `jakarta.mail.internet.AddressException` | Lỗi phân tích hoặc kiểm tra cú pháp địa chỉ |
| `jakarta.mail.internet.ParseException` và lỗi MIME liên quan | Lỗi cấu trúc, header hoặc dữ liệu thông điệp |

`SendFailedException` có các phương thức đặc biệt hữu ích:

- `getInvalidAddresses()`: những địa chỉ bị xem là không hợp lệ/không được chấp nhận trong lần gửi.
- `getValidSentAddresses()`: địa chỉ mà transport ghi nhận đã gửi thành công theo trạng thái nó theo dõi.
- `getValidUnsentAddresses()`: địa chỉ hợp lệ nhưng chưa được gửi thành công trong lần xử lý này.

Các danh sách có thể là `null`. “Valid sent” là kết quả **ở tầng transport**, không phải chứng cứ người nhận đã mở thư hoặc thư đã xuất hiện trong Inbox.

### 3.3. Ngoại lệ từ provider và hệ thống mạng

| Lớp/nhóm lỗi | Dấu hiệu |
| --- | --- |
| `UnknownHostException` | Không phân giải được SMTP hostname |
| `ConnectException` | Không thiết lập được kết nối TCP, ví dụ bị từ chối |
| `SocketTimeoutException` | Kết nối hoặc thao tác đọc mạng bị timeout |
| `SSLHandshakeException` | Bắt tay TLS không thành công |
| `CertificateException` hoặc lỗi chứng chỉ liên quan | Thường xuất hiện trong cause của lỗi TLS |
| Ngoại lệ SMTP chứa reply code | Server từ chối một lệnh SMTP cụ thể |
| Lỗi I/O/file/stream | Không thể truy cập hoặc đọc dữ liệu attachment |

Tên package của các exception SMTP cụ thể phụ thuộc implementation Jakarta Mail: có thể gặp `SMTPAddressFailedException`, `SMTPSendFailedException` từ **Eclipse Angus Mail** (`org.eclipse.angus.mail.smtp`), hoặc từ implementation dùng tên package cũ. Không nên hard-code giả định package/provider nếu ứng dụng cần chạy với nhiều implementation.

Mã phản hồi như `550 5.1.1`, `535 5.7.8` hoặc `554 5.7.1` là **tín hiệu SMTP server trả về**. Phải kết hợp chúng với lệnh đang thực hiện và chính sách nhà cung cấp; một mã lỗi không luôn tương đương với một nguyên nhân duy nhất.

## 4. Các bước lần theo ngoại lệ

Giả sử service tạo một thư bằng `MimeMessageHelper` và gọi `mailSender.send(message)`. Thay vì dừng ở thông báo:

~~~text
MailSendException: Failed messages
~~~

hãy lần theo:

1. **Kiểu lỗi Spring cụ thể**: `MailAuthenticationException` hay `MailSendException`?
2. **Cause chain**: `getCause()` dẫn tới `MessagingException`, lỗi mạng hay lỗi TLS?
3. **Jakarta Mail chain**: với từng `MessagingException`, `getNextException()` còn chứa thông tin gì?
4. **Message-level failures**: nếu là `MailSendException`, `getFailedMessages()` và `getMessageExceptions()` có bao nhiêu lỗi?
5. **Recipient-level failures**: `SendFailedException` cho biết `invalid`, `validSent`, `validUnsent` ra sao?
6. **SMTP stage/reply**: server từ chối lệnh nào, với mã nào?
7. **Kết quả trước khi lỗi**: kết nối chưa thành công, đã xác thực, đã chấp nhận recipient hay đã nhận DATA?

Ví dụ hai exception ngoài cùng giống nhau nhưng cách xử lý khác biệt:

~~~text
Trường hợp A:
MailSendException
  -> MessagingException "Could not connect to SMTP host"
     -> ConnectException "Connection refused"

Trường hợp B:
MailSendException
  -> SendFailedException
     -> RCPT TO rejected, SMTP reply 550 5.1.1
~~~

Trường hợp A gợi ý kiểm tra endpoint, port, firewall, service lắng nghe. Trường hợp B yêu cầu kiểm tra địa chỉ người nhận và chính sách tiếp nhận. Thay đổi HTML hay charset không giải quyết hai vấn đề này.

## 5. Công cụ Java duyệt exception graph

Đoạn mã dưới đây thu thập **loại exception, số lượng message và số lượng recipient** mà không in nguyên exception message chứa địa chỉ mail, SMTP banner hoặc nội dung thư. Nó duyệt cause, next exception của Jakarta Mail, suppressed exception và lỗi theo message của Spring.

~~~java
package com.example.mail.diagnostics;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

import jakarta.mail.Address;
import jakarta.mail.MessagingException;
import jakarta.mail.SendFailedException;
import org.springframework.mail.MailSendException;

public final class MailFailureInspector {

    private static final int MAX_NODES = 64;

    private MailFailureInspector() {
    }

    public static List<String> summarize(Throwable failure) {
        if (failure == null) {
            return List.of();
        }

        List<String> details = new ArrayList<>();
        Deque<Throwable> pending = new ArrayDeque<>();
        Set<Throwable> seen = Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>());
        pending.addLast(failure);

        while (!pending.isEmpty() && seen.size() < MAX_NODES) {
            Throwable current = pending.removeFirst();
            if (!seen.add(current)) {
                continue;
            }

            details.add("exception=" + current.getClass().getName());

            if (current instanceof MailSendException sendFailure) {
                details.add("failedMessages="
                        + sendFailure.getFailedMessages().size());
                for (Exception nested : sendFailure.getMessageExceptions()) {
                    enqueue(pending, nested);
                }
                for (Exception nested :
                        sendFailure.getFailedMessages().values()) {
                    enqueue(pending, nested);
                }
            }

            if (current instanceof SendFailedException addressFailure) {
                details.add("invalidRecipients="
                        + count(addressFailure.getInvalidAddresses()));
                details.add("validSentRecipients="
                        + count(addressFailure.getValidSentAddresses()));
                details.add("validUnsentRecipients="
                        + count(addressFailure.getValidUnsentAddresses()));
            }

            if (current instanceof MessagingException messagingFailure) {
                enqueue(pending, messagingFailure.getNextException());
            }

            enqueue(pending, current.getCause());
            for (Throwable suppressed : current.getSuppressed()) {
                enqueue(pending, suppressed);
            }
        }

        if (!pending.isEmpty()) {
            details.add("exceptionGraphTruncated=true");
        }
        return details;
    }

    private static void enqueue(Deque<Throwable> pending,
                                Throwable failure) {
        if (failure != null) {
            pending.addLast(failure);
        }
    }

    private static int count(Address[] addresses) {
        return addresses == null ? 0 : addresses.length;
    }
}
~~~

Ví dụ sử dụng:

~~~java
try {
    mailSender.send(message);
} catch (org.springframework.mail.MailException ex) {
    List<String> summary = MailFailureInspector.summarize(ex);
    summary.forEach(System.out::println); // Minh họa, thay bằng logger phù hợp.
    throw ex;
}
~~~

**Vì sao cần nhiều nhánh?**

- `getCause()` là cơ chế chuẩn của Java.
- `getNextException()` là cơ chế của Jakarta Mail.
- `getMessageExceptions()` và `getFailedMessages()` phản ánh lỗi của **nhiều message**, không chỉ một cause.
- `getSuppressed()` chứa ngoại lệ có thể được gắn vào khi xử lý tài nguyên hoặc thao tác phụ.
- `IdentityHashMap` bảo đảm phát hiện **cùng object exception** để tránh lặp hoặc vòng tham chiếu.
- `MAX_NODES` giới hạn dữ liệu chẩn đoán nếu nguồn ngoại lệ có cấu trúc bất thường.

Đoạn mã không ghi trực tiếp `Throwable.getMessage()` vì thông điệp lỗi thư viện có thể chứa dữ liệu nhạy cảm. Trong môi trường được cấp phép, có thể bổ sung trường như **SMTP reply code, command, ID yêu cầu và giai đoạn lỗi** sau khi đã lọc/che dữ liệu. Danh sách được sinh ra là **kết quả duyệt đồ thị**, không có nghĩa phần tử cuối luôn là nguyên nhân gốc duy nhất.

## 6. MailSendException: đọc lỗi theo từng message

Khi gửi:

~~~java
mailSender.send(firstMessage, secondMessage, thirdMessage);
~~~

server hoặc client có thể gặp lỗi ở một message trong lô. `MailSendException` hỗ trợ truy cập thông tin thất bại của từng message:

~~~java
catch (MailSendException ex) {
    for (var entry : ex.getFailedMessages().entrySet()) {
        Object messageObject = entry.getKey();
        Exception reason = entry.getValue();

        // Minh họa, không log messageObject/toString() trong production.
        System.out.println("Message type: "
                + messageObject.getClass().getName());
        System.out.println("Failure type: "
                + reason.getClass().getName());
    }
}
~~~

`getFailedMessages()` trả về ánh xạ từ **đối tượng message** sang **exception tương ứng**. Khóa có thể chứa toàn bộ header, body và attachment, vì vậy không tự động serialize hoặc `toString()` khóa này vào log. `getMessageExceptions()` cho phép lấy tập exception liên quan; hai API có thể cùng tham chiếu một exception nên cần loại trùng khi tổng hợp.

Không mặc định rằng mọi email trong lô đều thất bại khi có một `MailSendException`: một số message có thể đã được server tiếp nhận. Ngược lại, message không xuất hiện trong danh sách thất bại cũng chưa chứng minh người nhận cuối đã đọc thư.

### 6.1. SendFailedException và ba nhóm địa chỉ

Giả sử gửi cho:

~~~text
To:  lan@example.net
Cc:  team@example.net
Bcc: quan@example.org
~~~

Transport có thể chấp nhận một số recipient và từ chối một số khác. `SendFailedException` cung cấp các nhóm:

~~~java
failed.getInvalidAddresses();
failed.getValidSentAddresses();
failed.getValidUnsentAddresses();
~~~

Một thư có thể có recipient được chấp nhận và recipient bị server từ chối. Tùy policy và cấu hình của transport, message có thể đã được gửi cho tập địa chỉ hợp lệ, chưa được gửi cho bất kỳ ai, hoặc có một số địa chỉ cần thử lại.

**Khi retry phải căn cứ vào kết quả thực tế**, tránh gửi lại cho người đã được hệ thống tiếp nhận. “Valid sent” phản ánh kết quả transport báo, không phải chứng cứ email đã vào Inbox.

## 7. Truy vết lỗi theo giai đoạn SMTP

Để gửi một email qua SMTP, client thường kết nối TCP, chào `EHLO`, có thể thực hiện `STARTTLS` và `AUTH`, sau đó gửi `MAIL FROM`, `RCPT TO` và `DATA`. **Lệnh hoặc giai đoạn ngay trước lỗi** quyết định cách diễn giải thông tin từ exception chain.

| Giai đoạn | Dấu hiệu exception | Hướng xác minh |
| --- | --- | --- |
| Mở kết nối TCP | `UnknownHostException`, `ConnectException`, `SocketTimeoutException` | Hostname, DNS, port, firewall, routing, server |
| STARTTLS / TLS | `SSLHandshakeException`, nguyên nhân liên quan certificate | Port/mode TLS, trust chain, tên máy, chứng chỉ |
| SMTP AUTH | `AuthenticationFailedException`, `MailAuthenticationException`, phản hồi `535` hoặc mã khác | Tài khoản, phương thức AUTH, quyền account, chính sách provider |
| `MAIL FROM` | Reply code từ chối địa chỉ gửi | Reverse-path, quyền gửi của tài khoản/miền |
| `RCPT TO` | `SendFailedException`, SMTP reply của từng người nhận | Recipient bị từ chối, relay policy, valid/invalid recipient |
| `DATA` và kết thúc DATA | Lỗi vận chuyển, MIME/stream, reply code từ chối thông điệp | Kích thước, nội dung, dữ liệu attachment, kết quả sau DATA |
| Sau khi server chấp nhận | Bounce/DSN hoặc trạng thái provider đến sau | Trạng thái chuyển phát, không chỉ exception của `send(...)` |

Ví dụ:

~~~text
MailSendException
  └── MessagingException
        └── SSLHandshakeException
              └── CertificateException
~~~

gợi ý kiểm tra **TLS/trust store/chứng chỉ**, không phải sửa HTML hay xóa attachment. Nhưng có những lỗi xảy ra khi gọi `send(...)` mà dữ liệu `MimeMessage` vẫn chưa được serialize xong; do đó phải xem stack trace/nguồn cause cụ thể thay vì đoán theo tên lớp ngoài cùng.

### 7.1. Mã SMTP 4xx và 5xx

Trong SMTP, mã trả lời:

- **`4xx`** biểu thị lỗi tạm thời; có thể cân nhắc thử lại sau theo chính sách.
- **`5xx`** biểu thị từ chối mang tính vĩnh viễn trong ngữ cảnh lệnh hiện tại; thường cần sửa địa chỉ, quyền hoặc cấu hình.

| Reply code minh họa | Ý nghĩa thường gặp | Lưu ý khi xử lý |
| --- | --- | --- |
| `421` | Dịch vụ không sẵn sàng/đóng kết nối | Có thể là tạm thời |
| `450` | Mailbox/recipient tạm không sẵn sàng | Xem policy retry |
| `451` | Lỗi cục bộ tạm thời phía server | Retry có backoff |
| `535` | Xác thực SMTP thất bại ở nhiều server | Kiểm tra AUTH và thông điệp cụ thể |
| `550` | Địa chỉ hoặc thao tác bị từ chối | Không luôn đồng nghĩa mailbox không tồn tại |
| `552` | Có thể liên quan giới hạn dung lượng | Đối chiếu thông điệp và giới hạn server |
| `554` | Nội dung hoặc giao dịch bị từ chối vì nhiều lý do | Cần xem enhanced status code và chính sách |

Mã tăng cường như `5.1.1` hoặc `5.7.1` giúp khoanh vùng nhưng **không thay thế việc đọc command, reply text và cấu hình nhà cung cấp**. Cùng `550` có thể đại diện cho lỗi mailbox hoặc từ chối relay/chính sách.

### 7.2. Khi lỗi timeout không chứng minh được thư đã thất bại

Giả sử phiên đến bước:

~~~text
C: DATA
S: 354 Continue
C: [Headers, dòng trống, body/MIME]
C: .
   [Mất kết nối trước khi client nhận phản hồi cuối]
~~~

Client không biết server đã tiếp nhận và đưa message vào hàng đợi hay chưa. Nếu hệ thống retry vô điều kiện, **có khả năng tạo thư trùng**.

Vì vậy phải phân biệt timeout khi:

1. **Mở TCP connection**: chưa có cơ sở cho rằng server đã nhận giao dịch SMTP.
2. **Chờ EHLO/AUTH**: thông thường chưa có giao dịch mail nào hoàn tất.
3. **Gửi RCPT TO**: cần biết server chấp nhận recipient nào.
4. **Chờ phản hồi cuối DATA**: kết quả chấp nhận nội dung có thể **không xác định**.

Lỗi `SocketTimeoutException` là nguyên nhân kỹ thuật cụ thể, nhưng quyết định retry phải dựa vào **giai đoạn**. Với email nghiệp vụ quan trọng, dùng ID yêu cầu, cơ chế chống gửi trùng ở cấp ứng dụng, retry có giới hạn và khả năng đối chiếu với provider nếu được hỗ trợ.

## 8. Phân tích những tình huống thường gặp

### 8.1. Xác thực SMTP thất bại

Mô hình exception có thể xuất hiện:

~~~text
MailAuthenticationException: Authentication failed
  └── AuthenticationFailedException: 535 ...
~~~

Khi đọc chain:

- Lỗi ở **bước xác thực**; thông thường chưa tới `MAIL FROM`.
- Kiểm tra cách provider yêu cầu đăng nhập: username/password, application password, OAuth2 hoặc cơ chế đặc thù.
- Kiểm tra tài khoản bị tắt quyền SMTP, bị chính sách từ chối, hoặc thiếu TLS.
- Không đưa mật khẩu/token vào log để “chứng minh” đúng cấu hình.

**`535` không đồng nghĩa chắc chắn sai mật khẩu.** Nhà cung cấp có thể từ chối vì quyền, phương thức AUTH hoặc chính sách tài khoản.

### 8.2. Một địa chỉ người nhận bị từ chối

Một nhánh lỗi có thể có nội dung:

~~~text
MailSendException
  └── SendFailedException
        ├── validSentAddresses: lan@example.net
        └── invalidAddresses: old-account@example.net
             └── SMTP RCPT TO reply 550 5.1.1
~~~

Trong tình huống này:

- Lỗi liên quan đến **recipient cụ thể**, không phải lỗi parse HTML.
- Cần xem phản hồi server và địa chỉ đã bị từ chối.
- Không được coi toàn bộ người nhận đều chưa gửi.
- Trước khi thử lại, phải phân biệt địa chỉ nào được transport đánh dấu đã gửi/không gửi.

Các địa chỉ ở đây chỉ là dữ liệu giả. Trong production, nên log ID yêu cầu và thống kê recipient; tránh đưa email cá nhân ra hệ thống log không cần thiết.

### 8.3. Không kết nối được máy chủ SMTP

Ví dụ:

~~~text
MailSendException
  └── MessagingException: Could not connect to SMTP host
        └── ConnectException: Connection refused
~~~

Hướng phân tích:

1. Xem host, port, DNS và endpoint thực sự được cấu hình.
2. Kiểm tra SMTP service có lắng nghe đúng cổng không.
3. Kiểm tra network policy, firewall, routing hoặc proxy của môi trường ứng dụng.
4. Nếu timeout, đọc loại timeout và giai đoạn trước khi quyết định retry.

Thay `MimeMessageHelper.setText(...)` không giúp sửa việc TCP bị từ chối.

### 8.4. TLS handshake lỗi

Ví dụ:

~~~text
MailSendException
  └── MessagingException
        └── SSLHandshakeException
              └── lỗi xây dựng trust chain
~~~

Hướng phân tích:

- Phân biệt **STARTTLS trên cổng 587** và **implicit TLS trên cổng 465** theo provider.
- Kiểm tra certificate chain, trust store, hostname verification và thời hạn certificate.
- Không vô hiệu hóa kiểm tra chứng chỉ hoặc hostname chỉ để cho thao tác gửi thành công.

Đôi khi provider thay đổi chính sách TLS; nếu exception chỉ ra certificate/trust, đó là đường chẩn đoán ưu tiên.

### 8.5. Tệp đính kèm làm thao tác gửi thất bại

Code có thể tạo `MimeMessage` với `MimeMessageHelper.addAttachment(...)`, nhưng nguồn dữ liệu tệp không đọc được, bị xóa, quá lớn hoặc chỉ cho phép mở một lần. Lỗi có thể phát sinh khi:

- **Chuẩn bị part MIME**: ví dụ dữ liệu/tên tệp không hợp lệ.
- **Serialize message**: body part yêu cầu mở lại stream.
- **Transport đọc và truyền nội dung**: nguồn tệp lỗi hoặc vượt chính sách server.

Không mặc định attachment lỗi **luôn** ném exception trước `send(...)`. Phải tìm stack frame, cause, dữ liệu source và giai đoạn thực tế. Khi khắc phục, sử dụng `Resource` có nguồn đọc phù hợp, kiểm soát kích thước và xác nhận quyền truy cập. Không log đường dẫn nội bộ hoặc nội dung attachment nhạy cảm.

### 8.6. Thư gửi được nhưng HTML hiển thị sai

Nếu `send(...)` trả về bình thường nhưng người nhận thấy nguyên các thẻ HTML, ảnh CID hỏng hoặc body bị lặp, **có thể không tồn tại exception chain nào**. Đây thường là vấn đề cần xem MIME tree và khả năng của email client:

- Body HTML được gắn `text/plain` thay vì `text/html`.
- Hai phiên bản body không nằm trong `multipart/alternative` phù hợp.
- `cid:...` trong HTML không trùng `Content-ID` của ảnh inline.
- Charset hoặc `Content-Transfer-Encoding` không đúng với bytes thực.

Trong trường hợp đó, nên kiểm tra `MimeMessage` đã được serialize và bản raw `.eml` người nhận. Không phải mọi vấn đề email đều là lỗi vận chuyển.

## 9. Giữ nguyên cause khi bọc lỗi ở tầng nghiệp vụ

Một service Spring có thể phân loại lỗi ở ranh giới tạo message và gửi message:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportNotificationService {

    private final JavaMailSender mailSender;

    public ReportNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, String reportText) {
        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");
            helper.setFrom("reports@example.com");
            helper.setTo(recipient);
            helper.setSubject("Báo cáo tuần");
            helper.setText(reportText, false);
        } catch (MessagingException ex) {
            throw new MailRequestException(
                    "Không thể chuẩn bị MIME message", ex);
        }

        try {
            mailSender.send(message);
        } catch (MailAuthenticationException ex) {
            throw new MailRequestException(
                    "SMTP authentication failed", ex);
        } catch (MailSendException ex) {
            throw new MailRequestException(
                    "SMTP submission failed", ex);
        } catch (MailException ex) {
            throw new MailRequestException(
                    "Mail service failed", ex);
        }
    }

    private static final class MailRequestException
            extends RuntimeException {
        private MailRequestException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Ví dụ cho thấy hai thời điểm:

1. **Tạo `MimeMessage`**: các API `MimeMessageHelper` có thể ném `MessagingException` (checked). Lỗi được bọc nhưng giữ cause.
2. **Gửi `MimeMessage`**: `JavaMailSender.send(...)` dùng họ `MailException` của Spring. Bọc lại vẫn giữ exception đầy đủ để tầng xử lý khác chẩn đoán.

Việc chia các nhánh lỗi như trên giúp người đọc biết nơi khởi đầu của lỗi, nhưng **chưa phải một thuật toán retry**. Đặc biệt, sau `MailSendException` phải xem các message/recipient đã được transport chấp nhận trước khi gửi lại.

### 9.1. Không làm mất nguyên nhân gốc

Ví dụ không nên dùng:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    throw new IllegalStateException("Không gửi được email");
}
~~~

Vì ngoại lệ mới không giữ cause, người gọi sẽ mất chuỗi chẩn đoán. Cách giữ nguyên nhân:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    throw new IllegalStateException("Không gửi được email", ex);
}
~~~

Chỉ log `ex.getMessage()` cũng có thể bỏ qua cause, `getNextException()` và các lỗi theo message. Nhưng log toàn bộ stack trace không có kiểm soát lại có thể lộ dữ liệu nhạy cảm. Cần chọn mức quan sát phù hợp với môi trường và quyền truy cập.

### 9.2. Khi nào ghi stack trace và SMTP reply?

Trong môi trường phát triển/điều tra được cấp phép, stack trace có thể chỉ rõ vị trí chuyển từ Spring tới Jakarta Mail và lớp mạng. Trong production, exception message hoặc trace có thể chứa SMTP host, địa chỉ email, tên tệp, đường dẫn nội bộ, thông điệp provider hoặc dữ liệu liên quan xác thực.

Thông tin thường đủ để giám sát:

- ID yêu cầu gửi và số lần thử, không dùng subject hoặc recipient thực làm ID.
- Loại ngoại lệ Spring và ngoại lệ cấp sâu.
- Giai đoạn như `CONNECT`, `AUTH`, `MAIL_FROM`, `RCPT_TO`, `DATA` nếu có bằng chứng.
- SMTP reply code và enhanced status code sau khi được lọc.
- Số message/recipient thành công, thất bại hoặc chưa rõ trạng thái.
- Trạng thái retry, thời điểm thử lại và nguồn kiểm chứng từ provider nếu có.

## 10. Quan sát lỗi gửi email có cấu trúc

Một bản ghi chẩn đoán có thể biểu diễn:

~~~text
mail_request_id = req-2026-00123
attempt = 2
phase = SMTP_RCPT
status = FAILED
spring_exception = MailSendException
mail_exception = SendFailedException
smtp_reply_code = 550
smtp_enhanced_code = 5.1.1
recipient_count = 3
failed_recipient_count = 1
~~~

Đây là **ví dụ thiết kế log**, không phải những field được `JavaMailSender` tự động xuất ra. Không được suy luận `phase` chính xác chỉ từ một dòng thông báo mơ hồ; giai đoạn phải đến từ bằng chứng exception, protocol trace hoặc telemetry thích hợp.

| Nhóm lỗi | Cách ứng dụng/vận hành thường xử lý |
| --- | --- |
| Xác thực/cấu hình bị từ chối | Thông báo cho người quản lý tích hợp SMTP |
| DNS/kết nối/timeout trước giao dịch | Kiểm tra hạ tầng và có thể retry có giới hạn |
| TLS/certificate | Sửa kết nối bảo mật và trust; không bỏ verification |
| Recipient bị từ chối vĩnh viễn | Kiểm tra địa chỉ, quyền gửi hoặc chính sách |
| SMTP 4xx | Có thể retry theo backoff/giới hạn của provider |
| Kết quả chưa rõ sau DATA | Đối chiếu provider hoặc dùng cơ chế chống gửi trùng |
| MIME/attachment lỗi | Kiểm tra nguồn dữ liệu, encoding và cấu trúc message |

Nếu dùng metrics, nên phân loại theo những nhãn số lượng thấp như `auth`, `dns`, `network_timeout`, `tls`, `recipient_rejected`, `content`, `unknown`. Không đặt nguyên văn exception message, địa chỉ email hoặc subject làm nhãn metric: cách đó có thể làm lộ dữ liệu và tạo số lượng nhãn quá lớn.

## 11. Nguyên nhân kỹ thuật và quyết định nghiệp vụ là hai tầng khác nhau

Một `SocketTimeoutException` cho biết thao tác mạng chờ quá lâu. Nhưng quyết định retry cần thêm ngữ cảnh:

- Timeout **trước kết nối** khác với timeout **sau khi truyền DATA**.
- Một `SendFailedException` có thể có recipient đã được gửi và recipient chưa được gửi.
- `250` sau DATA chỉ cho biết server đã tiếp nhận để xử lý; thông báo bounce có thể đến muộn.
- Một email hiển thị sai có thể hoàn toàn không tạo exception nào ở `send(...)`.

Do đó, “đã tìm được root cause” nghĩa là xác định được **sự cố kỹ thuật cụ thể và vị trí trong luồng**, chứ chưa tự động quyết định gửi lại cho ai, gửi lại lúc nào hoặc khẳng định tất cả người nhận đều chưa nhận.

## 12. Những nhầm lẫn thường gặp

**“Chỉ gọi getRootCause() đã đủ chưa?”**  
Chưa chắc. Nó hữu ích với `getCause()`, nhưng Jakarta Mail còn có `getNextException()`; `MailSendException` có thể giữ nhiều lỗi của các message. Cần xem các nhánh liên quan.

**“getCause() và getNextException() có thể cùng trả một exception?”**  
Có thể, tùy implementation. Khi duyệt, dùng tập đối tượng đã thăm để tránh đếm trùng hoặc vòng lặp.

**“MailAuthenticationException chắc chắn là sai password?”**  
Không. Nó biểu thị authentication thất bại. Có thể do credentials, chính sách tài khoản, phương thức AUTH hoặc yêu cầu bảo mật của provider.

**“MailSendException có nghĩa mọi recipient đều chưa được gửi?”**  
Không. Gửi nhiều message hoặc một message nhiều recipient có thể thất bại một phần. Cần xem dữ liệu exception gắn với từng message/recipient.

**“SocketTimeoutException là lỗi tạm thời nên retry ngay được không?”**  
Không nên quyết định chỉ từ tên exception. Nếu timeout xảy ra sau DATA, trạng thái thư có thể không xác định và retry có rủi ro gửi trùng.

**“send() không ném ngoại lệ nghĩa là thư đã vào Inbox?”**  
Không. SMTP server có thể mới chỉ nhận thư để chuyển tiếp; tình trạng phân phối và việc đọc thư là các bước khác.

**“Chỉ cần log nguyên stack trace là xong?”**  
Stack trace hữu ích khi điều tra nhưng không tự thay thế `getNextException()`/message-level failures và phải được kiểm soát quyền truy cập, che dữ liệu nhạy cảm.

## 13. Ví dụ kết luận từ exception chain

Giả sử thông tin thu thập được:

~~~text
Spring exception: MailSendException
Jakarta exception: SendFailedException
SMTP detail: RCPT TO rejected
SMTP reply: 550 5.1.1
Valid-sent recipients: 2
Invalid recipients: 1
~~~

Kết luận kỹ thuật phù hợp:

> Transport báo một recipient bị từ chối ở bước `RCPT TO` trong khi hai recipient khác nằm trong nhóm valid-sent. Vấn đề liên quan địa chỉ hoặc chính sách recipient, không phải định dạng HTML. Cần đối chiếu phản hồi server và trạng thái từng recipient; khi retry phải tránh gửi trùng cho những recipient đã được ghi nhận.

Với tình huống:

~~~text
Spring exception: MailSendException
Jakarta exception: MessagingException
Java cause: SSLHandshakeException
Detail: certificate path validation failed
~~~

kết luận sẽ khác:

> Bắt tay TLS thất bại trước khi giao dịch thư hoàn tất. Cần kiểm tra cấu hình cổng/mode TLS, trust store, chuỗi chứng chỉ và hostname của SMTP server. Không có bằng chứng cho thấy lỗi xuất phát từ nội dung `MimeMessage`.

Đọc đầy đủ **`MailException` → `MessagingException` → `getCause()`/`getNextException()` → lỗi SMTP hoặc I/O**, đồng thời kiểm tra các nhánh thất bại theo message và recipient, giúp phân biệt đúng nguyên nhân gốc trong Spring Framework Mail. Giữ nguyên cause khi bọc lỗi, ghi nhận giai đoạn và chỉ diễn giải mức độ thành công mà phản hồi SMTP thực sự chứng minh là nền tảng để xử lý sự cố gửi email hiệu quả.
